"""Directional Flow Engine — merged from peridotfoundation's
MT5-Directional-Flow-Dashboard concepts (Trend Integrity Score, exhaustion
detection, per-asset personality) re-implemented natively in our stack.

A trend is treated as a living entity: healthy trends "breathe" (orderly
counter-moves), while a weakening heartbeat — deteriorating efficiency,
acceleration decay, rejection wicks, fading momentum consistency — flags
exhaustion before the price turn.

Outputs feed the research node (confidence boosts / exhaustion blocks) and
the dashboard (per-symbol TIS / exhaustion gauges).
"""
from __future__ import annotations

import numpy as np

from ..models import Candle
from . import indicators as ind


def _trend_dir(closes: np.ndarray) -> int:
    if closes.size < 60:
        return 0
    e20 = float(ind.ema(closes, 20)[-1])
    e50 = float(ind.ema(closes, 50)[-1])
    if e20 > e50 and closes[-1] > e20:
        return 1
    if e20 < e50 and closes[-1] < e20:
        return -1
    return 0


def efficiency_ratio(closes: np.ndarray, period: int = 20) -> float:
    """Kaufman ER: net directional progress / total path length, 0..1."""
    if closes.size < period + 1:
        return 0.0
    seg = closes[-period - 1:]
    net = abs(seg[-1] - seg[0])
    path = float(np.sum(np.abs(np.diff(seg))))
    return net / path if path > 0 else 0.0


def momentum_consistency(closes: np.ndarray, direction: int,
                         windows: tuple = (10, 20, 40)) -> float:
    """% of bars moving in the trend direction across several lookbacks."""
    if direction == 0 or closes.size < 12:
        return 50.0
    scores = []
    for w in windows:
        if closes.size < w + 1:
            continue
        seg = closes[-w - 1:]
        moves = np.diff(seg)
        scores.append(float(np.mean(moves * direction > 0)) * 100.0)
    return float(np.mean(scores)) if scores else 50.0


def acceleration(closes: np.ndarray, direction: int) -> float:
    """ROC alignment across 5/15/30-bar horizons, 0..100.

    Aligned, growing momentum in the trend direction scores high; decaying
    or conflicting horizons score low ("trend acceleration/deceleration
    across multiple lookback periods").
    """
    if direction == 0:
        return 50.0
    rocs = []
    for p in (5, 15, 30):
        if closes.size < p + 1:
            continue
        rocs.append(float((closes[-1] / closes[-p - 1] - 1.0)) * direction)
    if not rocs:
        return 50.0
    aligned = sum(1 for r in rocs if r > 0) / len(rocs)
    short_vs_long = 1.0 if len(rocs) >= 2 and rocs[0] >= rocs[-1] else 0.0
    return round((0.7 * aligned + 0.3 * short_vs_long) * 100.0, 1)


def heartbeat(candles: list[Candle], direction: int, window: int = 30) -> float:
    """Counter-trend breathing ratio: share of bars closing against the
    trend. Healthy trends breathe (0.25–0.5); <0.2 (grinding, fragile) or
    >0.65 (losing control) both warn. Returns a health score 0..100."""
    if direction == 0 or len(candles) < window + 2:
        return 60.0
    seg = candles[-window:]
    contra = sum(1 for c in seg if (c.close - c.open) * direction < 0) / len(seg)
    if 0.25 <= contra <= 0.5:
        return 100.0
    if contra < 0.25:
        return max(30.0, contra / 0.25 * 100.0)          # over-grinding
    return max(0.0, (0.75 - contra) / 0.25 * 100.0)      # losing control


def rejection_wicks(candles: list[Candle], direction: int, window: int = 14) -> float:
    """Rejection wicks AGAINST the trend (selling tails in uptrend) — an
    exhaustion tell. Returns wick pressure 0..100 (higher = more rejection)."""
    if direction == 0 or len(candles) < window:
        return 0.0
    seg = candles[-window:]
    hits = 0
    for c in seg:
        rng = max(c.high - c.low, 1e-12)
        body_top = max(c.open, c.close)
        body_bot = min(c.open, c.close)
        against = (c.high - body_top) if direction > 0 else (body_bot - c.low)
        if against > 0.5 * rng:
            hits += 1
    return hits / len(seg) * 100.0


def momentum_divergence(candles: list[Candle], direction: int) -> float:
    """Price makes a new extreme but RSI fails to confirm → 0..100."""
    if direction == 0 or len(candles) < 40:
        return 0.0
    closes = np.array([c.close for c in candles])
    highs = np.array([c.high for c in candles])
    lows = np.array([c.low for c in candles])
    rsi_v = ind.rsi(closes)
    half = 20
    if direction > 0:
        px_now, px_prev = float(np.max(highs[-half:])), float(np.max(highs[-2 * half:-half]))
        rs_now, rs_prev = float(np.max(rsi_v[-half:])), float(np.max(rsi_v[-2 * half:-half]))
        return 90.0 if (px_now > px_prev and rs_now < rs_prev - 4) else 0.0
    px_now, px_prev = float(np.min(lows[-half:])), float(np.min(lows[-2 * half:-half]))
    rs_now, rs_prev = float(np.min(rsi_v[-half:])), float(np.min(rsi_v[-2 * half:-half]))
    return 90.0 if (px_now < px_prev and rs_now > rs_prev + 4) else 0.0


class FlowEngine:
    """Per-symbol directional-flow state with asset 'personality' adjustment."""

    def __init__(self):
        self._atr_pct_hist: dict[str, list[float]] = {}

    def analyze(self, symbol: str, candles: list[Candle]) -> dict:
        closes = np.array([c.close for c in candles])
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])
        direction = _trend_dir(closes)

        er = efficiency_ratio(closes)
        consist = momentum_consistency(closes, direction)
        acc = acceleration(closes, direction)
        hb = heartbeat(candles, direction)
        # Trend Integrity Score: consistency of momentum vs volatility
        tis = 0.35 * (er * 100) + 0.30 * consist + 0.20 * acc + 0.15 * hb
        tis = round(min(max(tis, 0.0), 100.0), 1)

        # Exhaustion: wick rejection + RSI divergence + degraded integrity/heartbeat
        atr_ser = ind.atr(highs, lows, closes)
        atr_pct = float(atr_ser[-1] / closes[-1]) if closes[-1] else 0.0
        hist = self._atr_pct_hist.setdefault(symbol, [])
        hist.append(atr_pct)
        del hist[:-240]
        med = float(np.median(hist)) if len(hist) > 10 else atr_pct or 1e-9
        vol_expansion = atr_pct / med if med > 0 else 1.0

        wick = rejection_wicks(candles, direction)
        div = momentum_divergence(candles, direction)
        exhaustion = min(100.0, 0.4 * wick + 0.35 * div
                         + 0.25 * max(0.0, (100.0 - hb) * 0.8)
                         + 0.2 * max(0.0, (vol_expansion - 1.6) * 40))
        exhaustion = round(exhaustion, 1)

        # Asset personality: calmer instruments get a bonus, wild ones stricter
        personality = {
            "vol_ratio": round(vol_expansion, 2),
            "confidence_bias": -2.0 if vol_expansion < 0.75 else (2.5 if vol_expansion > 1.5 else 0.0),
        }
        return {
            "trend_dir": direction,
            "tis": tis,
            "exhaustion": exhaustion,
            "efficiency_ratio": round(er, 3),
            "consistency": round(consist, 1),
            "acceleration": acc,
            "heartbeat": round(hb, 1),
            "wick_rejection": round(wick, 1),
            "divergence": div,
            "personality": personality,
        }
