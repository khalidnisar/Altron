"""Stop-loss / take-profit machinery (blueprint 1A).

* Hard stops (never exceeded) — placed broker-side at order time.
* Volatility-based initial stops — ATR multiples.
* Multi-level take profit — 25% / 50% / 75% / 100% of the final TP distance.
* Breakeven protection, ATR trailing stops, time-based stops.
"""
from __future__ import annotations

from ..models import Side, SymbolSpec


def initial_sl_tp(
    side: Side, entry: float, atr: float, sl_mult: float, rr: float, spec: SymbolSpec
) -> tuple[float, float]:
    sl_dist = max(atr * sl_mult, spec.pip * 5)          # never tighter than 5 pips
    tp_dist = sl_dist * rr
    if side is Side.BUY:
        return spec.round_price(entry - sl_dist), spec.round_price(entry + tp_dist)
    return spec.round_price(entry + sl_dist), spec.round_price(entry - tp_dist)


def tp_prices(side: Side, entry: float, final_tp: float, fractions: list[float]) -> list[float]:
    """Intermediate TP prices at each fraction of the total TP distance."""
    dist = final_tp - entry
    return [entry + dist * f for f in fractions]


def risk_distance(side: Side, entry: float, sl: float) -> float:
    return (entry - sl) * side.sign


def profit_in_r(side: Side, entry: float, sl: float, price: float) -> float:
    r = risk_distance(side, entry, sl)
    if r <= 0:
        return 0.0
    return ((price - entry) * side.sign) / r


def breakeven_stop(side: Side, entry: float, buffer: float) -> float:
    off = buffer  # small profit-lock buffer in the trade's favour
    return entry + off if side is Side.BUY else entry - off


def trailing_stop(side: Side, price: float, atr: float, mult: float) -> float:
    dist = atr * mult
    return price - dist if side is Side.BUY else price + dist


def improves_stop(side: Side, candidate: float, current: float) -> bool:
    return candidate > current if side is Side.BUY else candidate < current


def time_stop_due(age_candles: float, max_age: float, pnl_r: float, lo: float, hi: float) -> bool:
    """Close stale 'dead' trades: aged positions that never moved decisively."""
    return age_candles >= max_age and lo <= pnl_r <= hi
