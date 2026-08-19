"""FX/CFD session clock — ported from Altron-Sword markets/sessions/calendar.py
(named UTC sessions + overlap detection; concept credited upstream to the
EarnForex session-time model, independently re-implemented here on our clock).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class Session:
    name: str
    start_hour_utc: float
    end_hour_utc: float


SESSIONS: tuple[Session, ...] = (
    Session("sydney", 21.0, 6.0),
    Session("tokyo", 0.0, 9.0),
    Session("london", 7.0, 16.0),
    Session("new_york", 12.0, 21.0),
)


def _in_window(hour: float, start: float, end: float) -> bool:
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def classify(ts_epoch: float) -> dict:
    dt = datetime.fromtimestamp(ts_epoch, tz=UTC)
    hour = dt.hour + dt.minute / 60.0
    active = [s.name for s in SESSIONS if _in_window(hour, s.start_hour_utc, s.end_hour_utc)]
    return {
        "active": active,
        "overlap": len(active) >= 2,
        "label": "+".join(active) if active else "off-hours",
        "hour": round(hour, 2),
        "weekday": dt.weekday(),
    }


def size_factor(ts_epoch: float) -> float:
    """Liquidity-aware size scaling (RULE 11 support):
    full size in overlap / london / NY, reduced in thin sydney-only hours."""
    s = classify(ts_epoch)
    if s["overlap"]:
        return 1.0
    if s["active"] in ([], ["sydney"]):
        return 0.7
    return 0.85 if s["active"] == ["tokyo"] else 1.0
