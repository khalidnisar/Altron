"""Multi-timeframe market structure analysis.

* Candle resampling: M15 → H1 (×4) → H4 (×16)
* Swing mapping (fractal pivots), HH/HL vs LH/LL classification
* BOS (break of structure) / CHoCH (change of character) events
* Premium/discount positioning inside the active range
* Liquidation-pool estimation: swing/equal-highs/lows act as stop &
  liquidation clusters (perp-futures style liquidity magnets)
"""
from __future__ import annotations

import numpy as np

from ..models import Candle
from . import indicators as ind


def resample(candles: list[Candle], factor: int, symbol: str) -> list[Candle]:
    out: list[Candle] = []
    for i in range(0, len(candles) - factor + 1, factor):
        chunk = candles[i: i + factor]
        out.append(Candle(
            symbol=symbol, ts=chunk[0].ts, open=chunk[0].open,
            high=max(c.high for c in chunk), low=min(c.low for c in chunk),
            close=chunk[-1].close, volume=sum(c.volume for c in chunk)))
    return out


def swings(candles: list[Candle], left: int = 2, right: int = 2) -> tuple[list, list]:
    """Fractal pivots → (swing_highs, swing_lows) as (index, price) lists."""
    highs, lows = [], []
    n = len(candles)
    for i in range(left, n - right):
        h = candles[i].high
        l = candles[i].low
        if all(h >= candles[j].high for j in range(i - left, i + right + 1) if j != i):
            highs.append((i, h))
        if all(l <= candles[j].low for j in range(i - left, i + right + 1) if j != i):
            lows.append((i, l))
    return highs, lows


def structure(candles: list[Candle], lookback: int = 60) -> dict:
    """Classify structure of a single timeframe."""
    if len(candles) < 12:
        return {"direction": "FLAT", "bos": None, "choch": None, "premium": 0.5,
                "swing_high": None, "swing_low": None, "hh": 0, "ll": 0}
    recent = candles[-lookback:]
    highs, lows = swings(recent)
    closes = [c.close for c in recent]

    sh = [p for _, p in highs][-2:]
    sl = [p for _, p in lows][-2:]
    hh = int(len(sh) >= 2 and sh[-1] > sh[-2])
    lh = int(len(sh) >= 2 and sh[-1] < sh[-2])
    hl = int(len(sl) >= 2 and sl[-1] > sl[-2])
    ll = int(len(sl) >= 2 and sl[-1] < sl[-2])

    if len(sh) < 2 or len(sl) < 2:
        # Not enough confirmed pivots (near-monotonic drift) — fall back to
        # half-window mean comparison so we never report "FLAT" in a runaway.
        seg = max(len(closes) // 2, 1)
        avg1 = sum(closes[:seg]) / seg
        avg2 = sum(closes[seg:]) / (len(closes) - seg)
        direction = "UP" if avg2 > avg1 else ("DOWN" if avg2 < avg1 else "FLAT")
    elif hh and hl:
        direction = "UP"
    elif lh and ll:
        direction = "DOWN"
    elif hh or hl:
        direction = "UP_BIAS"
    elif ll or lh:
        direction = "DOWN_BIAS"
    else:
        direction = "FLAT"

    # BOS / CHoCH: last close breaking the most recent opposite swing
    bos = choch = None
    if highs and lows:
        last_high, last_low = highs[-1][1], lows[-1][1]
        px = closes[-1]
        prev_dir_up = hh and hl
        prev_dir_dn = lh and ll
        if px > last_high:
            bos = "BULLISH_BOS" if prev_dir_up else None
            choch = "BULLISH_CHoCH" if prev_dir_dn else None
        elif px < last_low:
            bos = "BEARISH_BOS" if prev_dir_dn else None
            choch = "BEARISH_CHoCH" if prev_dir_up else None

    hi_all = max(c.high for c in recent)
    lo_all = min(c.low for c in recent)
    rng = hi_all - lo_all
    premium = (closes[-1] - lo_all) / rng if rng > 0 else 0.5
    return {
        "direction": direction, "bos": bos, "choch": choch,
        "premium": round(float(premium), 3),
        "swing_high": round(highs[-1][1], 6) if highs else None,
        "swing_low": round(lows[-1][1], 6) if lows else None,
        "hh": hh, "ll": ll,
    }


def multi_tf(candles_m15: list[Candle], symbol: str) -> dict:
    """Structure across M15/H1/H4 + HTF alignment diagnostics."""
    h1 = resample(candles_m15, 4, symbol)
    h4 = resample(candles_m15, 16, symbol)
    tfs = {"M15": structure(candles_m15), "H1": structure(h1), "H4": structure(h4)}
    signs = {"UP": 1, "UP_BIAS": 0.5, "FLAT": 0.0, "DOWN_BIAS": -0.5, "DOWN": -1}
    alignment = sum(signs[d["direction"]] for d in tfs.values())
    htf_dir = tfs["H4"]["direction"] if tfs["H4"]["direction"] != "FLAT" else tfs["H1"]["direction"]
    return {"timeframes": tfs, "alignment": round(alignment, 2), "htf_direction": htf_dir,
            "counts": {"h1": len(h1), "h4": len(h4)}}


def liquidation_pools(candles: list[Candle], lookback: int = 90,
                      tolerance_atr_mult: float = 0.35) -> dict:
    """Estimate stop/liquidation clusters above & below price.

    Combines: swing pivots, *equal* highs/lows (stronger magnets), and
    psychological round numbers — weighted by recency. Each pool carries a
    notional strength score (arb. units, 0–100).
    """
    if len(candles) < 20:
        return {"above": [], "below": []}
    recent = candles[-lookback:]
    closes = np.array([c.close for c in recent])
    highs = np.array([c.high for c in recent])
    lows = np.array([c.low for c in recent])
    atr_v = float(ind.atr(highs, lows, closes)[-1])
    tol = atr_v * tolerance_atr_mult
    px = closes[-1]
    piv_hi, piv_lo = swings(recent)

    def cluster(points: list[tuple[int, float]], above: bool) -> list[dict]:
        pts = [p for _, p in points if (p > px) == above]
        pts.sort()
        pools: list[list[float]] = []
        for p in pts:
            for pool in pools:
                if abs(p - np.mean(pool)) <= tol:
                    pool.append(p)
                    break
            else:
                pools.append([p])
        out = []
        for pool in pools:
            level = float(np.mean(pool))
            touches = len(pool)
            strength = min(100.0, touches * 34 + 10)
            # equal highs/lows (≥2 touches within tight tolerance) are prime liq magnets
            equal = touches >= 2 and (max(pool) - min(pool)) <= tol * 0.6
            if equal:
                strength = min(100.0, strength * 1.4)
            out.append({"price": round(level, 6), "touches": touches,
                        "strength": round(strength, 1), "equal": equal,
                        "distance": round(abs(level - px), 6)})
        out.sort(key=lambda x: x["distance"])
        return out[:4]

    return {"above": cluster(piv_hi, above=True), "below": cluster(piv_lo, above=False)}
