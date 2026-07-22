from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC
from importlib.util import find_spec
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from altron.data_layer.fetchers import YFinanceFetcher
from altron.data_layer.stream import (
    AlpacaBarStream,
    CCXTProCandleStream,
    ClosedCandleAggregator,
    reconnecting_stream,
)
from altron.data_layer.timeframes import timeframe_to_seconds
from altron.live_trading.telemetry import RuntimeTelemetry

COMMON_MARKETS: dict[str, list[dict[str, str]]] = {
    "stocks": [
        {"symbol": "AAPL", "name": "Apple", "provider": "yahoo"},
        {"symbol": "MSFT", "name": "Microsoft", "provider": "yahoo"},
        {"symbol": "NVDA", "name": "NVIDIA", "provider": "yahoo"},
        {"symbol": "AMZN", "name": "Amazon", "provider": "yahoo"},
        {"symbol": "GOOGL", "name": "Alphabet", "provider": "yahoo"},
        {"symbol": "META", "name": "Meta Platforms", "provider": "yahoo"},
        {"symbol": "TSLA", "name": "Tesla", "provider": "yahoo"},
        {"symbol": "SPY", "name": "S&P 500 ETF", "provider": "yahoo"},
        {"symbol": "QQQ", "name": "Nasdaq 100 ETF", "provider": "yahoo"},
        {"symbol": "DIA", "name": "Dow Jones ETF", "provider": "yahoo"},
    ],
    "forex": [
        {"symbol": "EURUSD=X", "name": "EUR/USD", "provider": "yahoo"},
        {"symbol": "GBPUSD=X", "name": "GBP/USD", "provider": "yahoo"},
        {"symbol": "USDJPY=X", "name": "USD/JPY", "provider": "yahoo"},
        {"symbol": "AUDUSD=X", "name": "AUD/USD", "provider": "yahoo"},
        {"symbol": "USDCAD=X", "name": "USD/CAD", "provider": "yahoo"},
        {"symbol": "USDCHF=X", "name": "USD/CHF", "provider": "yahoo"},
        {"symbol": "NZDUSD=X", "name": "NZD/USD", "provider": "yahoo"},
    ],
    "crypto": [
        {"symbol": "BTC/USDT", "name": "Bitcoin", "provider": "binance"},
        {"symbol": "ETH/USDT", "name": "Ethereum", "provider": "binance"},
        {"symbol": "SOL/USDT", "name": "Solana", "provider": "binance"},
        {"symbol": "BNB/USDT", "name": "BNB", "provider": "binance"},
        {"symbol": "XRP/USDT", "name": "XRP", "provider": "binance"},
        {"symbol": "ADA/USDT", "name": "Cardano", "provider": "binance"},
        {"symbol": "DOGE/USDT", "name": "Dogecoin", "provider": "binance"},
        {"symbol": "AVAX/USDT", "name": "Avalanche", "provider": "binance"},
    ],
}


class FreeStreamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_class: Literal["stocks", "forex", "crypto"]
    symbol: str
    timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "1m"
    provider: Literal["auto", "yahoo", "binance", "alpaca"] = "auto"
    poll_seconds: float = Field(default=60.0, ge=30, le=3600)


class FreeStreamStatus(BaseModel):
    id: str
    asset_class: str
    symbol: str
    timeframe: str
    provider: str
    state: Literal["starting", "running", "stopped", "error"] = "starting"
    bars_received: int = 0
    last_timestamp: str | None = None
    message: str = "starting"


class YahooPollingCandleStream:
    """No-key delayed polling feed for research charts, not execution."""

    name = "yahoo"

    def __init__(self, poll_seconds: float = 60.0) -> None:
        self.poll_seconds = poll_seconds
        self.fetcher = YFinanceFetcher()

    async def _poll(self, symbol: str, timeframe: str) -> AsyncIterator[pd.Series]:
        last_timestamp: pd.Timestamp | None = None
        while True:
            frame = await self.fetcher.fetch_ohlcv(symbol, timeframe, limit=10)
            if not frame.empty:
                cutoff = pd.Timestamp.now(tz=UTC) - pd.Timedelta(
                    seconds=timeframe_to_seconds(timeframe)
                )
                closed = frame.loc[frame["timestamp"] <= cutoff]
                if not closed.empty:
                    latest = closed.iloc[-1]
                    timestamp = pd.Timestamp(latest["timestamp"])
                    if last_timestamp is None or timestamp > last_timestamp:
                        last_timestamp = timestamp
                        yield latest
            await asyncio.sleep(self.poll_seconds)

    async def stream_ohlcv(self, symbol: str, timeframe: str) -> AsyncIterator[pd.Series]:
        async for candle in reconnecting_stream(
            lambda: self._poll(symbol, timeframe),
            initial_delay=max(5, self.poll_seconds),
            maximum_delay=300,
        ):
            yield candle


StreamFactory = Callable[[FreeStreamRequest], tuple[Any, str, ClosedCandleAggregator | None]]


class FreeStreamManager:
    """Manage bounded public/research market streams feeding dashboard telemetry."""

    def __init__(
        self,
        telemetry: RuntimeTelemetry,
        *,
        factories: dict[str, StreamFactory] | None = None,
    ) -> None:
        self.telemetry = telemetry
        self._statuses: dict[str, FreeStreamStatus] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._factories = factories or {}

    @staticmethod
    def catalog() -> dict[str, Any]:
        return {
            "markets": COMMON_MARKETS,
            "providers": {
                "binance": {
                    "asset_classes": ["crypto"],
                    "transport": "public websocket",
                    "credentials": "none",
                    "quality": "real-time public exchange feed",
                },
                "yahoo": {
                    "asset_classes": ["stocks", "forex"],
                    "transport": "delayed polling",
                    "credentials": "none",
                    "quality": "research/display only; no streaming SLA",
                },
                "alpaca": {
                    "asset_classes": ["stocks"],
                    "transport": "IEX websocket",
                    "credentials": "free account API keys",
                    "quality": "exchange websocket subject to account entitlements",
                },
            },
        }

    def _source(
        self, request: FreeStreamRequest, provider: str
    ) -> tuple[Any, str, ClosedCandleAggregator | None]:
        if provider in self._factories:
            return self._factories[provider](request)
        if provider == "binance":
            if request.asset_class != "crypto":
                raise ValueError("Binance public streaming is configured for crypto symbols")
            if find_spec("ccxt") is None:
                raise RuntimeError("Install public crypto streaming with: pip install '.[data]'")
            return CCXTProCandleStream("binance"), request.timeframe, None
        if provider == "yahoo":
            if request.asset_class == "crypto":
                raise ValueError("Use Binance for public crypto websocket data")
            if find_spec("yfinance") is None:
                raise RuntimeError("Install Yahoo polling with: pip install '.[data]'")
            return YahooPollingCandleStream(request.poll_seconds), request.timeframe, None
        if provider == "alpaca":
            key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_API_SECRET")
            if not key or not secret:
                raise ValueError("Alpaca streaming requires ALPACA_API_KEY and ALPACA_API_SECRET")
            aggregator = (
                ClosedCandleAggregator(request.timeframe) if request.timeframe != "1m" else None
            )
            return AlpacaBarStream(key, secret), "1m", aggregator
        raise ValueError(f"Unsupported free stream provider: {provider}")

    async def _consume(
        self,
        subscription_id: str,
        request: FreeStreamRequest,
        source: Any,
        source_timeframe: str,
        aggregator: ClosedCandleAggregator | None,
    ) -> None:
        status = self._statuses[subscription_id]
        status.state = "running"
        status.message = "stream active"
        try:
            async for candle in source.stream_ohlcv(request.symbol, source_timeframe):
                if aggregator is not None:
                    candle = aggregator.update(candle)
                    if candle is None:
                        continue
                self.telemetry.record_candle(request.symbol, request.timeframe, candle)
                status.bars_received += 1
                status.last_timestamp = pd.Timestamp(candle["timestamp"]).isoformat()
        except asyncio.CancelledError:
            status.state = "stopped"
            status.message = "stopped by operator"
            raise
        except Exception as exc:
            status.state = "error"
            status.message = f"{type(exc).__name__}: {exc}"

    def subscribe(self, request: FreeStreamRequest) -> FreeStreamStatus:
        provider = request.provider
        if provider == "auto":
            provider = "binance" if request.asset_class == "crypto" else "yahoo"
        duplicate = next(
            (
                status
                for status in self._statuses.values()
                if status.symbol == request.symbol
                and status.timeframe == request.timeframe
                and status.provider == provider
                and status.state in {"starting", "running"}
            ),
            None,
        )
        if duplicate is not None:
            raise ValueError(
                f"An active {provider} subscription already exists for "
                f"{request.symbol} {request.timeframe}: {duplicate.id}"
            )
        source, source_timeframe, aggregator = self._source(request, provider)
        subscription_id = uuid.uuid4().hex[:12]
        status = FreeStreamStatus(
            id=subscription_id,
            asset_class=request.asset_class,
            symbol=request.symbol,
            timeframe=request.timeframe,
            provider=provider,
        )
        self._statuses[subscription_id] = status
        self._tasks[subscription_id] = asyncio.create_task(
            self._consume(
                subscription_id,
                request,
                source,
                source_timeframe,
                aggregator,
            )
        )
        return status

    def statuses(self) -> list[FreeStreamStatus]:
        return list(self._statuses.values())

    async def stop(self, subscription_id: str) -> FreeStreamStatus:
        if subscription_id not in self._statuses:
            raise KeyError(f"Stream subscription {subscription_id!r} does not exist")
        task = self._tasks.get(subscription_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        status = self._statuses[subscription_id]
        status.state = "stopped"
        status.message = "stopped by operator"
        return status

    async def close(self) -> None:
        for subscription_id in list(self._tasks):
            await self.stop(subscription_id)
