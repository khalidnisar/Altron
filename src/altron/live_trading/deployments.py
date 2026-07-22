from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DeploymentSpec(BaseModel):
    """Persisted strategy deployment intent; creation does not place an order."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    strategy: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(pattern=r"^[1-9]\d*[mhd]$")
    data_source: str = "binance"
    execution_backend: Literal["paper", "tradovate", "mt5"] = "paper"
    environment: Literal["paper", "demo", "live"] = "paper"
    allocation: float = Field(default=0.05, gt=0, le=1)
    enabled: bool = False
    leaderboard_id: int | None = None

    @model_validator(mode="after")
    def backend_matches_environment(self) -> DeploymentSpec:
        if self.execution_backend == "paper" and self.environment != "paper":
            raise ValueError("Paper backend requires the paper environment")
        if self.execution_backend != "paper" and self.environment == "paper":
            raise ValueError("Tradovate and MT5 backends require demo or live environment")
        return self


class DeploymentRecord(DeploymentSpec):
    id: int
    created_at: datetime
    updated_at: datetime


class DeploymentStore:
    def __init__(self, path: str | Path = "data/deployments.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS deployments (
                    id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    name TEXT NOT NULL UNIQUE,
                    strategy TEXT NOT NULL,
                    params_json TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    data_source TEXT NOT NULL,
                    execution_backend TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    allocation REAL NOT NULL,
                    enabled INTEGER NOT NULL,
                    leaderboard_id INTEGER
                )
                """
            )

    @staticmethod
    def _row(row: sqlite3.Row) -> DeploymentRecord:
        return DeploymentRecord(
            id=row["id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            name=row["name"],
            strategy=row["strategy"],
            params=json.loads(row["params_json"]),
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            data_source=row["data_source"],
            execution_backend=row["execution_backend"],
            environment=row["environment"],
            allocation=row["allocation"],
            enabled=bool(row["enabled"]),
            leaderboard_id=row["leaderboard_id"],
        )

    def create(self, spec: DeploymentSpec, *, allow_live: bool = False) -> DeploymentRecord:
        if spec.environment == "live" and spec.enabled:
            raise ValueError(
                "Live deployment records must be created disabled and require an explicitly "
                "authorized execution process before activation"
            )
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            cursor = connection.execute(
                "INSERT INTO deployments(created_at, updated_at, name, strategy, params_json, "
                "symbol, timeframe, data_source, execution_backend, environment, allocation, "
                "enabled, leaderboard_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    now,
                    now,
                    spec.name,
                    spec.strategy,
                    json.dumps(spec.params, sort_keys=True),
                    spec.symbol,
                    spec.timeframe,
                    spec.data_source,
                    spec.execution_backend,
                    spec.environment,
                    spec.allocation,
                    int(spec.enabled),
                    spec.leaderboard_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM deployments WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        return self._row(row)

    def list(self) -> list[DeploymentRecord]:
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM deployments ORDER BY updated_at DESC").fetchall()
        return [self._row(row) for row in rows]

    def set_enabled(self, deployment_id: int, enabled: bool, *, allow_live: bool = False) -> DeploymentRecord:
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM deployments WHERE id=?", (deployment_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Deployment {deployment_id} does not exist")
            if enabled and row["environment"] == "live" and not allow_live:
                raise ValueError("Live deployment activation is not authorized in this API process")
            connection.execute(
                "UPDATE deployments SET enabled=?, updated_at=? WHERE id=?",
                (int(enabled), datetime.now(UTC).isoformat(), deployment_id),
            )
            row = connection.execute(
                "SELECT * FROM deployments WHERE id=?", (deployment_id,)
            ).fetchone()
        return self._row(row)

    def delete(self, deployment_id: int) -> bool:
        with sqlite3.connect(self.path) as connection:
            cursor = connection.execute("DELETE FROM deployments WHERE id=?", (deployment_id,))
        return bool(cursor.rowcount)
