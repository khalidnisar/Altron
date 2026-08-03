"""Tiny SQLite layer for the monitor: state, alerts, runs.

Three tables, three responsibilities:

- ``state``     one row per monitor with the last seen hash, text excerpt, and
                the last extracted selector/keyword/regex values (JSON blob)
- ``alerts``    every alert that was dispatched (or suppressed by cooldown)
- ``runs``      one row per scheduled run — useful for cron health monitoring
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

DEFAULT_DB_PATH = "data/monitor.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS state (
    name TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    last_hash TEXT,
    last_text TEXT,
    last_status INTEGER,
    last_error TEXT,
    last_run_at TEXT,
    last_change_at TEXT,
    last_values_json TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    details_json TEXT,
    urgent INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_name ON alerts(name, detected_at DESC);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    run_at TEXT NOT NULL,
    ok INTEGER NOT NULL,
    message TEXT,
    alert_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_runs_name ON runs(name, run_at DESC);
"""


class MonitorStore:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as cx:
            cx.executescript(SCHEMA)
            cx.commit()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        cx = sqlite3.connect(self.path)
        cx.row_factory = sqlite3.Row
        try:
            yield cx
        finally:
            cx.close()

    # ---- state -----------------------------------------------------------

    def get_state(self, name: str) -> dict[str, Any] | None:
        with self._conn() as cx:
            row = cx.execute("SELECT * FROM state WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def save_state(
        self,
        *,
        name: str,
        url: str,
        last_hash: str | None,
        last_text: str | None,
        last_status: int | None,
        last_error: str | None,
        last_values: dict[str, Any] | None = None,
        changed: bool = False,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self._conn() as cx:
            cx.execute(
                """
                INSERT INTO state (name, url, last_hash, last_text, last_status,
                                   last_error, last_run_at, last_change_at,
                                   last_values_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    url = excluded.url,
                    last_hash = excluded.last_hash,
                    last_text = excluded.last_text,
                    last_status = excluded.last_status,
                    last_error = excluded.last_error,
                    last_run_at = excluded.last_run_at,
                    last_change_at = COALESCE(excluded.last_change_at, state.last_change_at),
                    last_values_json = excluded.last_values_json
                """,
                (
                    name,
                    url,
                    last_hash,
                    last_text,
                    last_status,
                    last_error,
                    now,
                    now if changed else None,
                    json.dumps(last_values or {}, sort_keys=True, default=str),
                ),
            )
            cx.commit()

    # ---- alerts ----------------------------------------------------------

    def record_alert(
        self,
        *,
        name: str,
        kind: str,
        summary: str,
        details: dict[str, Any] | None = None,
        urgent: bool = False,
    ) -> int:
        with self._conn() as cx:
            cur = cx.execute(
                "INSERT INTO alerts (name, detected_at, kind, summary, details_json, urgent) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    name,
                    datetime.now(UTC).isoformat(),
                    kind,
                    summary,
                    json.dumps(details or {}, default=str),
                    int(urgent),
                ),
            )
            cx.commit()
            return int(cur.lastrowid)

    def recent_alerts(self, name: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as cx:
            rows = cx.execute(
                "SELECT * FROM alerts WHERE name = ? ORDER BY detected_at DESC LIMIT ?",
                (name, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def last_alert_at(self, name: str, kind: str) -> datetime | None:
        with self._conn() as cx:
            row = cx.execute(
                "SELECT detected_at FROM alerts WHERE name = ? AND kind = ? "
                "ORDER BY detected_at DESC LIMIT 1",
                (name, kind),
            ).fetchone()
        return datetime.fromisoformat(row["detected_at"]) if row else None

    # ---- runs ------------------------------------------------------------

    def record_run(self, *, name: str, ok: bool, message: str, alert_count: int) -> None:
        with self._conn() as cx:
            cx.execute(
                "INSERT INTO runs (name, run_at, ok, message, alert_count) VALUES (?, ?, ?, ?, ?)",
                (name, datetime.now(UTC).isoformat(), int(ok), message, alert_count),
            )
            cx.commit()

    def clear_monitor(self, name: str) -> None:
        with self._conn() as cx:
            cx.execute("DELETE FROM state WHERE name = ?", (name,))
            cx.execute("DELETE FROM alerts WHERE name = ?", (name,))
            cx.execute("DELETE FROM runs WHERE name = ?", (name,))
            cx.commit()
