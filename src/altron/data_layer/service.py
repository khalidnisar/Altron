from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from altron.data_layer.base import HistoricalDataSource
from altron.data_layer.cache import MarketDataCache
from altron.data_layer.timeframes import timeframe_to_seconds


class MarketDataService:
    """Coordinates vendor fetches and an idempotent local cache."""

    def __init__(self, source: HistoricalDataSource, cache: MarketDataCache) -> None:
        self.source = source
        self.cache = cache

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
        refresh: bool = False,
    ) -> pd.DataFrame:
        cached = self.cache.get(self.source.name, symbol, timeframe, start=start, end=end)
        bounds = self.cache.bounds(self.source.name, symbol, timeframe)

        def utc_timestamp(value: datetime) -> pd.Timestamp:
            timestamp = pd.Timestamp(value)
            return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")

        fresh_without_end = bool(
            bounds[1] is not None
            and (pd.Timestamp.now(tz=UTC) - bounds[1]).total_seconds()
            <= 2 * timeframe_to_seconds(timeframe)
        )
        range_has_expected_count = True
        if (
            start is not None
            and end is not None
            and self.source.name not in {"yfinance", "alpaca", "polygon"}
        ):
            elapsed = (utc_timestamp(end) - utc_timestamp(start)).total_seconds()
            expected = max(0, int(elapsed // timeframe_to_seconds(timeframe)) + 1)
            range_has_expected_count = len(cached) >= expected
        requested_covered = bool(
            not refresh
            and not cached.empty
            and (start is None or (bounds[0] is not None and bounds[0] <= utc_timestamp(start)))
            and (
                (end is not None and bounds[1] is not None and bounds[1] >= utc_timestamp(end))
                or (end is None and fresh_without_end)
            )
            and (limit is None or len(cached) >= limit)
            and range_has_expected_count
        )
        if requested_covered:
            return cached.tail(limit).reset_index(drop=True) if limit else cached
        fetched = await self.source.fetch_ohlcv(
            symbol, timeframe, start=start, end=end, limit=limit
        )
        self.cache.put(self.source.name, symbol, timeframe, fetched)
        merged = self.cache.get(self.source.name, symbol, timeframe, start=start, end=end)
        return merged.tail(limit).reset_index(drop=True) if limit else merged
