from __future__ import annotations

import re

SUPPORTED_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d")
_TIMEFRAME_RE = re.compile(r"^(?P<count>[1-9]\d*)(?P<unit>[mhd])$")


def timeframe_to_seconds(timeframe: str) -> int:
    match = _TIMEFRAME_RE.fullmatch(timeframe)
    if not match:
        raise ValueError(f"Invalid timeframe {timeframe!r}; expected values such as 1m, 4h, 1d")
    factors = {"m": 60, "h": 3600, "d": 86400}
    return int(match.group("count")) * factors[match.group("unit")]


def timeframe_to_pandas(timeframe: str) -> str:
    match = _TIMEFRAME_RE.fullmatch(timeframe)
    if not match:
        raise ValueError(f"Invalid timeframe {timeframe!r}")
    units = {"m": "min", "h": "h", "d": "D"}
    return f"{match.group('count')}{units[match.group('unit')]}"


def timeframe_to_milliseconds(timeframe: str) -> int:
    return timeframe_to_seconds(timeframe) * 1000
