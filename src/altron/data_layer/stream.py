from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import AsyncIterator, Callable
from typing import Any

import pandas as pd

from altron.data_layer.normalization import normalize_ohlcv
from altron.data_layer.timeframes import timeframe_to_pandas

logger = logging.getLogger(__name__)


class ClosedCandleAggregator:
    """Aggregate a base stream and emit a candle only when its next bucket starts."""

    def __init__(self, timeframe: str) -> None:
        self.rule = timeframe_to_pandas(timeframe)
        self._current: dict[str, Any] | None = None

    def update(self, candle: pd.Series | dict[str, Any]) -> pd.Series | None:
        frame = normalize_ohlcv([dict(candle)])
        if frame.empty:
            return None
        row = frame.iloc[0]
        bucket = pd.Timestamp(row["timestamp"]).floor(self.rule)
        if self._current is None:
            self._current = {
                "timestamp": bucket,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
            return None
        current_timestamp = pd.Timestamp(self._current["timestamp"])
        if bucket < current_timestamp:
            return None
        if bucket == current_timestamp:
            self._current["high"] = max(float(self._current["high"]), float(row["high"]))
            self._current["low"] = min(float(self._current["low"]), float(row["low"]))
            self._current["close"] = float(row["close"])
            self._current["volume"] = float(self._current["volume"]) + float(row["volume"])
            return None
        completed = pd.Series(self._current)
        self._current = {
            "timestamp": bucket,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        return completed


async def reconnecting_stream(
    connect: Callable[[], AsyncIterator[Any]],
    *,
    initial_delay: float = 1.0,
    maximum_delay: float = 60.0,
    jitter: float = 0.25,
    stop_event: asyncio.Event | None = None,
) -> AsyncIterator[Any]:
    """Reconnect an async stream forever with capped exponential backoff."""
    delay = initial_delay
    while stop_event is None or not stop_event.is_set():
        try:
            async for item in connect():
                delay = initial_delay
                yield item
                if stop_event is not None and stop_event.is_set():
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # vendor exceptions vary
            wait = min(maximum_delay, delay) * random.uniform(1 - jitter, 1 + jitter)
            logger.warning("Market stream disconnected (%s); reconnecting in %.1fs", exc, wait)
            if stop_event is None:
                await asyncio.sleep(wait)
            else:
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=wait)
                except TimeoutError:
                    pass
                if stop_event.is_set():
                    return
            delay = min(maximum_delay, delay * 2)


class CCXTProCandleStream:
    """Exchange-native websocket candles through the optional ccxt.pro package."""

    def __init__(self, exchange: str = "binance", **exchange_options: Any) -> None:
        self.name = exchange.lower()
        self.exchange_id = exchange.lower()
        self.exchange_options = {"enableRateLimit": True, **exchange_options}
        self._exchange: Any = None

    async def _watch(self, symbol: str, timeframe: str) -> AsyncIterator[pd.Series]:
        try:
            import ccxt.pro as ccxtpro  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("ccxt.pro is required for websocket market data") from exc
        exchange_type = getattr(ccxtpro, self.exchange_id, None)
        if exchange_type is None:
            raise ValueError(f"Unknown ccxt.pro exchange: {self.exchange_id}")
        self._exchange = exchange_type(self.exchange_options)
        last_emitted: pd.Timestamp | None = None
        try:
            while True:
                rows = await self._exchange.watch_ohlcv(symbol, timeframe)
                frame = normalize_ohlcv(rows)
                if len(frame) < 2:
                    continue
                # The final ccxt candle is normally still forming. Emit the prior
                # candle once a newer timestamp proves that it has closed.
                closed = frame.iloc[-2]
                timestamp = pd.Timestamp(closed["timestamp"])
                if last_emitted is None or timestamp > last_emitted:
                    last_emitted = timestamp
                    yield closed
        finally:
            await self._exchange.close()
            self._exchange = None

    async def stream_ohlcv(self, symbol: str, timeframe: str) -> AsyncIterator[pd.Series]:
        async for candle in reconnecting_stream(lambda: self._watch(symbol, timeframe)):
            yield candle


class AlpacaBarStream:
    """Alpaca's exchange-native minute-bar websocket with automatic reconnects.

    Alpaca emits one-minute stock bars. Build larger closed candles with
    :func:`resample_ohlcv` after persisting the minute stream.
    """

    name = "alpaca"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        endpoint: str = "wss://stream.data.alpaca.markets/v2/iex",
    ) -> None:
        if not endpoint.startswith("wss://"):
            raise ValueError("Alpaca websocket endpoint must use WSS")
        self.api_key = api_key
        self.api_secret = api_secret
        self.endpoint = endpoint

    async def _watch(self, symbol: str) -> AsyncIterator[pd.Series]:
        try:
            import websockets  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Install websocket adapters with: pip install '.[data]'") from exc
        async with websockets.connect(self.endpoint, ping_interval=20, ping_timeout=20) as socket:
            await socket.send(
                json.dumps({"action": "auth", "key": self.api_key, "secret": self.api_secret})
            )
            authentication = json.loads(await socket.recv())
            if not any(message.get("msg") == "authenticated" for message in authentication):
                raise PermissionError("Alpaca websocket authentication failed")
            await socket.send(json.dumps({"action": "subscribe", "bars": [symbol]}))
            async for payload in socket:
                for message in json.loads(payload):
                    if message.get("T") != "b" or message.get("S") != symbol:
                        continue
                    frame = normalize_ohlcv(
                        [
                            {
                                "timestamp": message["t"],
                                "open": message["o"],
                                "high": message["h"],
                                "low": message["l"],
                                "close": message["c"],
                                "volume": message["v"],
                            }
                        ]
                    )
                    yield frame.iloc[0]

    async def stream_ohlcv(self, symbol: str, timeframe: str = "1m") -> AsyncIterator[pd.Series]:
        if timeframe != "1m":
            raise ValueError("Alpaca websocket emits 1m bars; resample closed bars downstream")
        async for candle in reconnecting_stream(lambda: self._watch(symbol)):
            yield candle
