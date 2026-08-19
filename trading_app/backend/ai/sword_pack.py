"""Sword strategy pack — strategy logic ported from Altron-Sword
(trade_engine.strategies groups A–C) onto our Candle/Side types and
regime meta-strategies. Each pack member contributes a confluence vote:

  breakout.opening_range  → ORB-style range-violation breakout vote
  momentum.roc            → ROC(12) thrust vote
  channel.fade            → parallel-channel rail fade vote (range regimes)
  orderflow.delta_imbalance → tick-flow imbalance vote (Group C)

Upstream concepts credited per Altron-Sword docs/THIRD_PARTY_AUDIT.md
(EarnForex chart-pattern helpers, OrderFlow-Analysis-Pro); independently
re-implemented here — no upstream source was copied verbatim.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..models import Candle, Side
from .structure import swings


@dataclass
class PackSignal:
    name: str
    side: Side
    score: float                       # 0..1 conviction
    valid_strategies: tuple[str, ...]  # meta-strategies this vote applies to
    reason: str


# ---------------------------------------------------------------- ORB
def opening_range(candles: list[Candle], range_bars: int = 8,
                  buffer: float = 0.0002) -> PackSignal | None:
    """breakout.orb → close beyond the previous N-bar range by a buffer."""
    if len(candles) < range_bars + 2:
        return None
    rng = candles[-(range_bars + 1):-1]
    hi = max(c.high for c in rng)
    lo = min(c.low for c in rng)
    width = hi - lo
    last = candles[-1]
    if width <= 0:
        return None
    if last.close > hi + buffer * last.close:
        return PackSignal("orb", Side.BUY, min(1.0, (last.close - hi) / width),
                          ("BREAKOUT", "DEFENSIVE"), f"orb_long +{last.close - hi:.5f}")
    if last.close < lo - buffer * last.close:
        return PackSignal("orb", Side.SELL, min(1.0, (lo - last.close) / width),
                          ("BREAKOUT", "DEFENSIVE"), f"orb_short -{lo - last.close:.5f}")
    return None


# ------------------------------------------------------------- ROC
def roc_momentum(candles: list[Candle], period: int = 12,
                 threshold: float = 0.004) -> PackSignal | None:
    """momentum.roc → rate-of-change beyond threshold."""
    if len(candles) < period + 1:
        return None
    prev = candles[-(period + 1)].close
    roc = (candles[-1].close / prev) - 1.0 if prev else 0.0
    if roc > threshold:
        return PackSignal("roc", Side.BUY, min(1.0, abs(roc) * 40),
                          ("BREAKOUT", "DEFENSIVE"), f"roc_up {roc:+.3%}")
    if roc < -threshold:
        return PackSignal("roc", Side.SELL, min(1.0, abs(roc) * 40),
                          ("BREAKOUT", "DEFENSIVE"), f"roc_down {roc:+.3%}")
    return None


# ------------------------------------------------------ channel fade
@dataclass
class Channel:
    upper_a: float
    upper_b: float
    lower_a: float
    lower_b: float
    position: float
    kind: str          # ascending | descending | horizontal
    slope: float


def detect_channel(candles: list[Candle], lookback: int = 80, min_bars: int = 10,
                   max_bars: int = 150, angle_tol: float = 0.15,
                   pair_ratio: float = 0.5) -> Channel | None:
    """Parallel-channel detector (3-point swing lines, slope/overlap match) —
    ported from Altron-Sword markets/patterns/channels.py onto our swings."""
    window = candles[-min(lookback, len(candles)):]
    if len(window) < max(min_bars, 12):
        return None
    highs, lows = swings(window)
    if len(highs) < 2 or len(lows) < 2:
        return None

    def fit(pts: list[tuple[int, float]]) -> tuple[float, float] | None:
        a, b = pts[0], pts[-1]
        span = b[0] - a[0]
        if span < min_bars or span > max_bars:
            return None
        slope = (b[1] - a[1]) / max(span, 1)
        return a[1] - slope * a[0], slope

    up = fit(highs)
    lo = fit(lows)
    if up is None or lo is None:
        return None
    ua, us = up
    la, ls = lo
    scale = max(abs(window[-1].close), 1e-9)
    if abs(us - ls) / scale > angle_tol:
        return None
    overlap = min(highs[-1][0], lows[-1][0]) - max(highs[0][0], lows[0][0])
    longer = max(highs[-1][0] - highs[0][0], lows[-1][0] - lows[0][0], 1)
    if overlap / longer < pair_ratio:
        return None
    t = len(window) - 1
    upper = ua + us * t
    lower = la + ls * t
    if upper - lower <= 0:
        return None
    pos = (window[-1].close - lower) / (upper - lower)
    slope = (us + ls) / 2
    kind = ("ascending" if slope > 1e-6 * scale
            else "descending" if slope < -1e-6 * scale else "horizontal")
    return Channel(ua, us, la, ls, float(pos), kind, slope)


def channel_fade(candles: list[Candle], lookback: int = 60,
                 edge: float = 0.15) -> PackSignal | None:
    """channel.fade → fade the rails of a detected parallel channel."""
    ch = detect_channel(candles, lookback=lookback)
    if ch is None:
        return None
    if ch.position >= 1 - edge:
        return PackSignal("channel", Side.SELL, ch.position, ("MEAN_REVERSION",),
                          f"channel_upper {ch.kind} pos={ch.position:.2f}")
    if ch.position <= edge:
        return PackSignal("channel", Side.BUY, 1 - ch.position, ("MEAN_REVERSION",),
                          f"channel_lower {ch.kind} pos={ch.position:.2f}")
    return None


# ------------------------------------------------- order-flow imbalance
def delta_imbalance(tick_dirs: list[int], threshold: float = 0.35) -> PackSignal | None:
    """orderflow.delta_imbalance → signed tick-flow imbalance (bid/ask delta
    proxy). Sword consumes a native depth feed; our simulated venue supplies
    signed tick deltas, which map onto the same contract."""
    if len(tick_dirs) < 10:
        return None
    arr = np.asarray(tick_dirs[-60:], dtype=float)
    imb = float(np.mean(arr))                         # -1..+1
    delta = float(np.sum(arr)) / len(arr)
    score = 0.6 * imb + 0.4 * np.sign(delta) * min(1.0, abs(delta))
    if score > threshold:
        return PackSignal("orderflow", Side.BUY, min(1.0, abs(score)),
                          ("BREAKOUT", "DEFENSIVE", "MEAN_REVERSION"),
                          f"of_buy_imbalance {score:+.2f}")
    if score < -threshold:
        return PackSignal("orderflow", Side.SELL, min(1.0, abs(score)),
                          ("BREAKOUT", "DEFENSIVE", "MEAN_REVERSION"),
                          f"of_sell_imbalance {score:+.2f}")
    return None


def pack_votes(candles: list[Candle], tick_dirs: list[int]) -> list[PackSignal]:
    out: list[PackSignal] = []
    for fn, args in ((opening_range, (candles,)), (roc_momentum, (candles,)),
                     (channel_fade, (candles,)), (delta_imbalance, (tick_dirs,))):
        try:
            sig = fn(*args)
        except Exception:
            sig = None
        if sig is not None:
            out.append(sig)
    return out
