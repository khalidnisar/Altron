from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


class Leaderboard:
    def __init__(self, path: str | Path = "data/leaderboard.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS leaderboard (
                    id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    score REAL NOT NULL,
                    robust INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_leaders ON leaderboard(symbol, timeframe, score DESC)"
            )

    def add(
        self,
        *,
        source: str,
        symbol: str,
        timeframe: str,
        strategy: str,
        params: dict[str, Any],
        metrics: dict[str, Any],
        score: float,
        robust: bool,
    ) -> int:
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute(
                "INSERT INTO leaderboard(created_at, source, symbol, timeframe, strategy, "
                "params_json, metrics_json, score, robust) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    datetime.now(UTC).isoformat(), source, symbol, timeframe, strategy,
                    json.dumps(params, sort_keys=True), json.dumps(metrics, sort_keys=True),
                    float(score), int(robust),
                ),
            )
            return int(cursor.lastrowid)

    def top(self, *, symbol: str | None = None, timeframe: str | None = None, limit: int = 20) -> pd.DataFrame:
        clauses: list[str] = ["robust = 1"]
        params: list[object] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if timeframe:
            clauses.append("timeframe = ?")
            params.append(timeframe)
        params.append(limit)
        with sqlite3.connect(self.path) as connection:
            return pd.read_sql_query(
                "SELECT * FROM leaderboard WHERE " + " AND ".join(clauses) + " ORDER BY score DESC LIMIT ?",
                connection,
                params=params,
            )
