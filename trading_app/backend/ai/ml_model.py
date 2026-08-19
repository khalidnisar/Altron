"""Lightweight predictive ensemble (blueprint 1B: ML models).

A full LSTM/GBM stack needs heavy training infrastructure; this module
implements the same contract with deployable-anything components:

  1. LogisticRegression-style scorer over engineered features, with
     hand-seeded weights and **online SGD learning** from closed-trade outcomes.
  2. Candlestick pattern recognizer (engulfing / pin-bar / doji, plus
     3-candle momentum) acting as the pattern-recognition ensemble member.

P(UP) = 0.65 × logistic + 0.35 × pattern_score, direction-adjusted by caller.
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np

from . import indicators as ind

FEATURES = [
    "rsi_norm",        # rsi/100 − 0.5
    "macd_hist_norm",  # macd histogram / price
    "ema_spread_norm", # (ema20−ema50)/price
    "bb_pctb",         # bollinger %b − 0.5
    "stoch_norm",      # %k/100 − 0.5
    "atr_change",      # atr vs 10-bar-ago, normalised
    "momentum_5",      # 5-bar return
    "range_ratio",     # last bar range / atr
]


class EnsembleModel:
    def __init__(self):
        # Hand-seeded weights (directional priors), then refined online.
        self.w = np.array([1.4, 900.0, 2600.0, 0.9, 1.1, 0.6, 60.0, -0.15])
        self.bias = 0.0
        self.lr = 0.35
        self.trained_updates = 0
        self.recent_outcomes: deque[int] = deque(maxlen=50)

    # ------------------------------------------------------------- features
    @staticmethod
    def extract(candles: list) -> np.ndarray | None:
        if len(candles) < 60:
            return None
        c = np.array([x.close for x in candles])
        h = np.array([x.high for x in candles])
        l = np.array([x.low for x in candles])
        o = np.array([x.open for x in candles])
        price = c[-1]
        if price <= 0:
            return None
        mid, up, lo = ind.bollinger(c)
        atr_ser = ind.atr(h, l, c)
        rsi_v = float(ind.rsi(c)[-1])
        macd_line, macd_sig, hist = ind.macd(c)
        e20 = ind.ema(c, 20)[-1]
        e50 = ind.ema(c, 50)[-1]
        k_line, _ = ind.stochastic(h, l, c)
        bb_pctb = 0.5 if any(np.isnan(x) for x in (up[-1], lo[-1], mid[-1])) or up[-1] == lo[-1] \
            else float((price - lo[-1]) / (up[-1] - lo[-1]))
        atr_now = atr_ser[-1]
        atr_ref = atr_ser[-11] if len(atr_ser) > 11 else atr_now
        mom5 = (price - c[-6]) / price if c.size > 6 else 0.0
        rng = (h[-1] - l[-1]) / atr_now if atr_now > 0 else 0.0
        return np.array([
            rsi_v / 100.0 - 0.5,
            float(hist[-1]) / price,
            float(e20 - e50) / price,
            bb_pctb - 0.5,
            float(k_line[-1]) / 100.0 - 0.5,
            (atr_now / atr_ref - 1.0) if atr_ref > 0 else 0.0,
            mom5,
            min(rng, 2.0) - 0.5,
        ])

    # -------------------------------------------------------------- patterns
    @staticmethod
    def pattern_score(candles: list) -> float:
        """Return P(UP) in [0,1] from the last three candles."""
        if len(candles) < 3:
            return 0.5
        a, b, x = candles[-3], candles[-2], candles[-1]
        score = 0.5
        body = lambda cd: cd.close - cd.open
        rng = max(x.high - x.low, 1e-12)
        # engulfing
        if body(x) > 0 and body(b) < 0 and x.close >= b.open and x.open <= b.close:
            score += 0.18
        if body(x) < 0 and body(b) > 0 and x.close <= b.open and x.open >= b.close:
            score -= 0.18
        # pin bars
        lower_wick = min(x.open, x.close) - x.low
        upper_wick = x.high - max(x.open, x.close)
        if lower_wick > 2 * abs(body(x)) and lower_wick > 0.6 * rng:
            score += 0.12
        if upper_wick > 2 * abs(body(x)) and upper_wick > 0.6 * rng:
            score -= 0.12
        # doji → indecision pull to 0.5
        if abs(body(x)) < 0.1 * rng:
            score = score * 0.6 + 0.5 * 0.4
        # 3-candle momentum
        if a.close < b.close < x.close:
            score += 0.08
        elif a.close > b.close > x.close:
            score -= 0.08
        return min(max(score, 0.0), 1.0)

    # --------------------------------------------------------------- predict
    def predict_proba_up(self, candles: list) -> float:
        x = self.extract(candles)
        if x is None:
            return 0.5
        z = float(np.dot(self.w, x) + self.bias)
        p_log = 1.0 / (1.0 + math.exp(-max(min(z, 8.0), -8.0)))
        p_pat = self.pattern_score(candles)
        return 0.65 * p_log + 0.35 * p_pat

    # ----------------------------------------------------------------- learn
    def learn(self, candles_at_entry: list, bar_outcome_up: bool, weight: float = 1.0) -> None:
        """Online SGD update from a resolved trade (blueprint: adaptive models)."""
        x = self.extract(candles_at_entry)
        if x is None:
            return
        z = float(np.dot(self.w, x) + self.bias)
        p = 1.0 / (1.0 + math.exp(-max(min(z, 8.0), -8.0)))
        y = 1.0 if bar_outcome_up else 0.0
        err = (y - p) * self.lr * weight
        self.w += err * x
        self.bias += err
        self.trained_updates += 1

    def snapshot(self) -> dict:
        return {
            "features": FEATURES,
            "weights": [round(float(w), 3) for w in self.w],
            "bias": round(self.bias, 3),
            "online_updates": self.trained_updates,
        }
