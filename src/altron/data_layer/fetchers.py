from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from altron.data_layer.base import HistoricalDataSource
from altron.data_layer.normalization import normalize_ohlcv
from altron.data_layer.rate_limit import AsyncRateLimiter
from altron.data_layer.timeframes import timeframe_to_milliseconds


def _utc_milliseconds(value: datetime | None) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1000)


def _json_request(url: str, headers: dict[str, str] | None = None) -> Any:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - configured vendor URL
        return json.loads(response.read().decode("utf-8"))


class CCXTFetcher(HistoricalDataSource):
    """Paginated crypto OHLCV fetcher for any ccxt exchange.

    ``ccxt`` is imported lazily. Exchange rate limiting remains enabled and this
    adapter additionally bounds every historical page by the requested end time.
    """

    def __init__(self, exchange: str = "binance", **exchange_options: Any) -> None:
        self.name = exchange.lower()
        self.exchange_id = exchange.lower()
        self.exchange_options = {"enableRateLimit": True, **exchange_options}

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        try:
            import ccxt.async_support as ccxt  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Install market-data adapters with: pip install '.[data]'") from exc
        exchange_type = getattr(ccxt, self.exchange_id, None)
        if exchange_type is None:
            raise ValueError(f"Unknown ccxt exchange: {self.exchange_id}")
        exchange = exchange_type(self.exchange_options)
        since = _utc_milliseconds(start)
        until = _utc_milliseconds(end)
        page_size = min(limit or 1000, 1000)
        target = limit
        rows: list[list[float]] = []
        try:
            while True:
                page = await exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=page_size)
                if not page:
                    break
                accepted = [row[:6] for row in page if until is None or int(row[0]) <= until]
                rows.extend(accepted)
                if target is not None and len(rows) >= target:
                    rows = rows[:target]
                    break
                last = int(page[-1][0])
                next_since = last + timeframe_to_milliseconds(timeframe)
                if next_since <= (since or -1) or len(page) < page_size or (until and next_since > until):
                    break
                since = next_since
        finally:
            await exchange.close()
        return normalize_ohlcv(rows)


class YFinanceFetcher(HistoricalDataSource):
    name = "yfinance"

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        try:
            import yfinance as yf  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Install market-data adapters with: pip install '.[data]'") from exc
        intervals = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "1h", "1d": "1d"}
        if timeframe not in intervals:
            raise ValueError(f"yfinance does not support {timeframe!r}")

        def download() -> pd.DataFrame:
            kwargs: dict[str, Any] = {
                "interval": intervals[timeframe],
                "auto_adjust": False,
                "progress": False,
                "multi_level_index": False,
            }
            if start is not None or end is not None:
                kwargs.update({"start": start, "end": end})
            else:
                kwargs["period"] = "7d" if timeframe != "1d" else "6mo"
            return yf.download(symbol, **kwargs)

        raw = await asyncio.to_thread(download)
        if raw.empty:
            return normalize_ohlcv([])
        frame = raw.reset_index().rename(columns={column: str(column).lower() for column in raw.reset_index().columns})
        if "adj close" in frame:
            frame = frame.drop(columns=["adj close"])
        result = normalize_ohlcv(frame)
        if timeframe == "4h":
            from altron.data_layer.normalization import resample_ohlcv

            result = resample_ohlcv(result, "4h")
        return result.tail(limit).reset_index(drop=True) if limit else result


class AlpacaFetcher(HistoricalDataSource):
    name = "alpaca"

    def __init__(self, api_key: str, api_secret: str, base_url: str = "https://data.alpaca.markets") -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}
        self.rate_limiter = AsyncRateLimiter(3)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        interval = {"1m": "1Min", "5m": "5Min", "15m": "15Min", "1h": "1Hour", "4h": "4Hour", "1d": "1Day"}.get(timeframe)
        if not interval:
            raise ValueError(f"Unsupported Alpaca timeframe: {timeframe}")
        params: dict[str, Any] = {"timeframe": interval, "limit": min(limit or 10000, 10000), "adjustment": "raw", "feed": "iex"}
        if start:
            params["start"] = start.astimezone(UTC).isoformat() if start.tzinfo else start.replace(tzinfo=UTC).isoformat()
        if end:
            params["end"] = end.astimezone(UTC).isoformat() if end.tzinfo else end.replace(tzinfo=UTC).isoformat()
        rows: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            if page_token:
                params["page_token"] = page_token
            url = f"{self.base_url}/v2/stocks/{urllib.parse.quote(symbol)}/bars?{urllib.parse.urlencode(params)}"
            async with self.rate_limiter:
                payload = await asyncio.to_thread(_json_request, url, self.headers)
            rows.extend(payload.get("bars", []))
            page_token = payload.get("next_page_token")
            if not page_token or (limit and len(rows) >= limit):
                break
        mapped = [{"timestamp": row["t"], "open": row["o"], "high": row["h"], "low": row["l"], "close": row["c"], "volume": row["v"]} for row in rows[:limit]]
        return normalize_ohlcv(mapped)


class PolygonFetcher(HistoricalDataSource):
    name = "polygon"

    def __init__(self, api_key: str, base_url: str = "https://api.polygon.io") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = AsyncRateLimiter(4)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        units = {"m": "minute", "h": "hour", "d": "day"}
        multiplier, unit = int(timeframe[:-1]), units.get(timeframe[-1])
        if unit is None:
            raise ValueError(f"Unsupported Polygon timeframe: {timeframe}")
        start_date = (start or datetime(1970, 1, 1, tzinfo=UTC)).date().isoformat()
        end_date = (end or datetime.now(UTC)).date().isoformat()
        params = urllib.parse.urlencode({"adjusted": "false", "sort": "asc", "limit": min(limit or 50000, 50000), "apiKey": self.api_key})
        url = f"{self.base_url}/v2/aggs/ticker/{urllib.parse.quote(symbol)}/range/{multiplier}/{unit}/{start_date}/{end_date}?{params}"
        rows: list[dict[str, Any]] = []
        while url:
            async with self.rate_limiter:
                payload = await asyncio.to_thread(_json_request, url)
            rows.extend(payload.get("results", []))
            next_url = payload.get("next_url")
            url = f"{next_url}&apiKey={urllib.parse.quote(self.api_key)}" if next_url else ""
            if limit and len(rows) >= limit:
                break
        mapped = [{"timestamp": row["t"], "open": row["o"], "high": row["h"], "low": row["l"], "close": row["c"], "volume": row.get("v", 0)} for row in rows[:limit]]
        return normalize_ohlcv(mapped)
