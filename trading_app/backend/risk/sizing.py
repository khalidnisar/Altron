"""Position sizing: fixed-fractional, Kelly criterion, volatility scaling.

Position Size = (Account Risk % × Account Balance) / (Entry − Stop Loss)
"""
from __future__ import annotations

import math

from ..models import SymbolSpec


def fixed_fractional_lots(
    balance: float,
    risk_pct: float,
    spec: SymbolSpec,
    entry: float,
    stop: float,
) -> float:
    """Lots such that, if the stop is hit, the loss equals risk% of balance."""
    risk_amount = balance * (risk_pct / 100.0)
    per_lot_loss = spec.value_per_lot(entry - stop, entry)
    if per_lot_loss <= 0:
        return 0.0
    return risk_amount / per_lot_loss


def kelly_criterion_pct(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Full-Kelly percentage of capital to risk.

    K = W − (1 − W) / R, with R = average win / average loss.
    Returns 0 when inputs are degenerate or Kelly is negative.
    """
    if avg_loss <= 0 or avg_win <= 0:
        return 0.0
    w = min(max(win_rate / 100.0, 0.0), 1.0)
    r = avg_win / avg_loss
    k = w - (1.0 - w) / r
    return max(0.0, k) * 100.0


def volatility_scale(atr: float, atr_reference: float, lo: float = 0.5, hi: float = 1.25) -> float:
    """Dynamic adjustment: inverse to current volatility vs its norm."""
    if atr <= 0 or atr_reference <= 0:
        return 1.0
    return min(max(atr_reference / atr, lo), hi)


def round_lots(lots: float, min_lot: float, max_lot: float, lot_step: float) -> float:
    lots = min(max(lots, 0.0), max_lot)
    steps = math.floor(lots / lot_step + 1e-9)
    rounded = steps * lot_step
    if 0 < rounded < min_lot:
        return 0.0
    return round(rounded, 4)
