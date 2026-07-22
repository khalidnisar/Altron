from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from altron.live_trading.models import PaperFill, SignalEvent
from altron.live_trading.paper import PaperBroker


class RuntimeTelemetry:
    """Bounded live state shared by the paper worker, API, and dashboard."""

    def __init__(self, *, capacity: int = 5000) -> None:
        self.capacity = capacity
        self._candles: dict[tuple[str, str], deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=capacity)
        )
        self._equity: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._fills: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._broker: PaperBroker | None = None
        self.started_at = datetime.now(UTC)

    def attach_broker(self, broker: PaperBroker) -> None:
        self._broker = broker
        self.record_equity()

    def record_candle(self, symbol: str, timeframe: str, candle: pd.Series) -> None:
        payload = {
            "timestamp": pd.Timestamp(candle["timestamp"]).isoformat(),
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
            "volume": float(candle["volume"]),
        }
        series = self._candles[(symbol, timeframe)]
        if series and series[-1]["timestamp"] == payload["timestamp"]:
            series[-1] = payload
        else:
            series.append(payload)

    def record_equity(self, timestamp: datetime | None = None) -> None:
        if self._broker is None:
            return
        snapshot = self._broker.snapshot()
        self._equity.append(
            {
                "timestamp": (timestamp or datetime.now(UTC)).isoformat(),
                "equity": snapshot["equity"],
                "cash": snapshot["cash"],
                "drawdown": snapshot["drawdown"],
                "net_pnl": snapshot["net_pnl"],
            }
        )

    def record_fill(self, fill: PaperFill | None) -> None:
        if fill is not None:
            self._fills.append(fill.model_dump(mode="json"))

    def candles(self, symbol: str, timeframe: str, limit: int = 500) -> list[dict[str, Any]]:
        return list(self._candles.get((symbol, timeframe), ()))[-limit:]

    def equity_history(self, limit: int = 1000) -> list[dict[str, Any]]:
        return list(self._equity)[-limit:]

    def fills(self, limit: int = 500) -> list[dict[str, Any]]:
        return list(self._fills)[-limit:]

    def portfolio(self) -> dict[str, Any]:
        if self._broker is None:
            return {
                "connected": False,
                "execution_mode": "virtual",
                "message": "No paper broker is attached to this API process",
            }
        return {"connected": True, "execution_mode": "virtual", **self._broker.snapshot()}

    def overview(self, signals: list[SignalEvent]) -> dict[str, Any]:
        portfolio = self.portfolio()
        return {
            "started_at": self.started_at.isoformat(),
            "signal_count": len(signals),
            "last_signal": signals[-1].model_dump(mode="json") if signals else None,
            "portfolio": portfolio,
            "tracked_markets": [
                {"symbol": symbol, "timeframe": timeframe, "bars": len(values)}
                for (symbol, timeframe), values in self._candles.items()
            ],
        }
