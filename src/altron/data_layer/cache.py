from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from threading import RLock

import pandas as pd

from altron.data_layer.normalization import OHLCV_COLUMNS, normalize_ohlcv


class MarketDataCache:
    """SQLite candle cache keyed by vendor, symbol, timeframe, and timestamp.

    SQLite is the source of truth and uses WAL for safe concurrent readers. Parquet
    export is deliberately explicit so missing optional parquet engines never break
    ingestion.
    """

    def __init__(self, path: str | Path = "data/market_data.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ohlcv (
                    source TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL,
                    close REAL NOT NULL, volume REAL NOT NULL,
                    PRIMARY KEY (source, symbol, timeframe, timestamp)
                ) WITHOUT ROWID
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ohlcv_lookup "
                "ON ohlcv(source, symbol, timeframe, timestamp)"
            )

    def put(self, source: str, symbol: str, timeframe: str, data: pd.DataFrame) -> int:
        frame = normalize_ohlcv(data)
        if frame.empty:
            return 0
        rows = [
            (
                source.lower(),
                symbol.upper(),
                timeframe,
                int(timestamp.value // 1_000_000),
                float(open_), float(high), float(low), float(close), float(volume),
            )
            for timestamp, open_, high, low, close, volume in frame.itertuples(index=False, name=None)
        ]
        sql = (
            "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source, symbol, timeframe, timestamp) DO UPDATE SET "
            "open=excluded.open, high=excluded.high, low=excluded.low, "
            "close=excluded.close, volume=excluded.volume"
        )
        with self._lock, self._connection() as connection:
            connection.executemany(sql, rows)
        return len(rows)

    def get(
        self,
        source: str,
        symbol: str,
        timeframe: str,
        *,
        start: datetime | pd.Timestamp | None = None,
        end: datetime | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        clauses = ["source = ?", "symbol = ?", "timeframe = ?"]
        params: list[object] = [source.lower(), symbol.upper(), timeframe]
        if start is not None:
            clauses.append("timestamp >= ?")
            params.append(int(pd.Timestamp(start).timestamp() * 1000))
        if end is not None:
            clauses.append("timestamp <= ?")
            params.append(int(pd.Timestamp(end).timestamp() * 1000))
        query = (
            "SELECT timestamp, open, high, low, close, volume FROM ohlcv WHERE "
            + " AND ".join(clauses)
            + " ORDER BY timestamp"
        )
        with self._connection() as connection:
            frame = pd.read_sql_query(query, connection, params=params)
        if frame.empty:
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        return normalize_ohlcv(frame)

    def bounds(self, source: str, symbol: str, timeframe: str) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT MIN(timestamp), MAX(timestamp) FROM ohlcv "
                "WHERE source=? AND symbol=? AND timeframe=?",
                (source.lower(), symbol.upper(), timeframe),
            ).fetchone()
        if not row or row[0] is None:
            return None, None
        return (pd.to_datetime(row[0], unit="ms", utc=True), pd.to_datetime(row[1], unit="ms", utc=True))

    def export_parquet(
        self, source: str, symbol: str, timeframe: str, destination: str | Path
    ) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.get(source, symbol, timeframe).to_parquet(destination, index=False)
        return destination
