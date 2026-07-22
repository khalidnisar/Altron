from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import datetime

import pandas as pd


class HistoricalDataSource(ABC):
    """Common async interface for market-data vendors."""

    name: str

    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        raise NotImplementedError


class LiveDataSource(ABC):
    name: str

    @abstractmethod
    def stream_ohlcv(self, symbol: str, timeframe: str) -> AsyncIterator[pd.Series]:
        raise NotImplementedError
