"""Alert engine (blueprint section 4).

CRITICAL: margin < 150%, daily loss > 1.5%-2%, drawdown ≥ 7%/10%, connection
lost, order rejection.
WARNING:  upcoming economic events, high volatility, correlation risk,
unusual conditions, strategy underperformance.
Each rule has a cooldown so the feed stays actionable.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict

from ..models import AlertEvent, AlertLevel


class AlertEngine:
    def __init__(self, cooldown_minutes: int = 60, maxlen: int = 120):
        self.events: deque[AlertEvent] = deque(maxlen=maxlen)
        self._last_fired: dict[str, float] = {}
        self.cooldown_s = cooldown_minutes * 60.0

    def fire(self, ts: float, level: AlertLevel, code: str, message: str,
             symbol: str | None = None, force: bool = False) -> bool:
        last = self._last_fired.get(code, -1e18)
        if not force and ts - last < self.cooldown_s:
            return False
        self._last_fired[code] = ts
        self.events.appendleft(AlertEvent(ts=ts, level=level, code=code,
                                          message=message, symbol=symbol))
        return True

    def evaluate(self, ts: float, ctx: dict) -> None:
        """ctx keys: account, risk(dict), connected(bool), analyses(dict), upcoming_event."""
        acc = ctx["account"]
        rk: dict = ctx["risk"]
        lim = rk.get("limits", {})

        if not ctx.get("connected", True):
            self.fire(ts, AlertLevel.CRITICAL, "CONNECTION_LOST",
                      "Broker connection lost — attempting reconnect", force=True)
        if acc.margin_level < lim.get("min_margin_level_pct", 150) and acc.margin_used > 0:
            self.fire(ts, AlertLevel.CRITICAL, "MARGIN_LOW",
                      f"Margin level {acc.margin_level:.0f}% below "
                      f"{lim.get('min_margin_level_pct', 150)}% — reduce positions")
        if rk["daily_loss_pct"] > 0.75 * lim.get("max_daily_loss_pct", 2.0):
            self.fire(ts, AlertLevel.CRITICAL, "DAILY_LOSS_WARN",
                      f"Daily loss {rk['daily_loss_pct']:.2f}% approaching "
                      f"{lim.get('max_daily_loss_pct', 2.0)}% limit")
        dd = rk["drawdown_pct"]
        if dd >= lim.get("dd_reduce_75_pct", 7.0):
            self.fire(ts, AlertLevel.CRITICAL, "DD_HIGH",
                      f"Drawdown {dd:.2f}% ≥ {lim.get('dd_reduce_75_pct', 7.0)}% — position size reduced / halt imminent")
        elif dd >= lim.get("dd_reduce_50_pct", 5.0):
            self.fire(ts, AlertLevel.WARNING, "DD_ELEVATED",
                      f"Drawdown {dd:.2f}% — equity preservation active")
        for sym, a in (ctx.get("analyses") or {}).items():
            if "HIGH" in a.regime or "EXTREME" in a.regime:
                self.fire(ts, AlertLevel.WARNING, f"HIGH_VOL_{sym}",
                          f"High volatility detected on {sym}", symbol=sym)
        ev = ctx.get("upcoming_event")
        if ev:
            self.fire(ts, AlertLevel.WARNING, f"EVENT_{ev['label']}",
                      f"Upcoming high-impact event in {int(ev['tick'] - ctx['tick'])} min: {ev['label']}")

    def snapshot(self) -> list[dict]:
        return [
            {"ts": e.ts, "level": e.level.value, "code": e.code,
             "message": e.message, "symbol": e.symbol}
            for e in self.events
        ]
