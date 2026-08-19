"""Market regime detection (blueprint 3) and adaptive strategy selection."""
from __future__ import annotations

from collections import deque

import numpy as np

from ..config import AppConfig
from ..models import RegimeState
from . import indicators as ind


class RegimeDetector:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self._atr_hist: dict[str, deque] = {}

    def detect(self, symbol: str, candles: list, spread: float, median_spread: float) -> RegimeState:
        closes = np.array([c.close for c in candles])
        highs = np.array([c.high for c in candles])
        lows = np.array([c.low for c in candles])
        adx_now = float(ind.adx(highs, lows, closes)[-1]) if closes.size > 30 else 0.0
        atr_ser = ind.atr(highs, lows, closes)
        atr_now = float(atr_ser[-1]) if closes.size > 15 else 0.0
        atr_pct = (atr_now / closes[-1] * 100.0) if closes[-1] else 0.0

        hist = self._atr_hist.setdefault(symbol, deque(maxlen=self.cfg.i("volatility", "lookback", default=120)))
        high_pct = self.cfg.f("volatility", "high_percentile", default=0.80)
        if len(hist) > 30:
            thresh = float(np.quantile(np.array(hist), high_pct))
        else:
            thresh = float("inf")
        hist.append(atr_pct)

        # Trend: ADX strength + EMA stack alignment
        e20 = float(ind.ema(closes, 20)[-1])
        e50 = float(ind.ema(closes, 50)[-1])
        slope = float((ind.ema(closes, 20)[-1] - ind.ema(closes, 20)[-4])) if closes.size > 60 else 0.0
        if adx_now >= 25 and e20 >= e50 and slope > 0:
            trend = "UP"
        elif adx_now >= 25 and e20 <= e50 and slope < 0:
            trend = "DOWN"
        else:
            trend = "RANGE"

        if atr_pct > thresh * 1.6 and len(hist) > 30:
            volatility = "EXTREME"
        elif atr_pct > thresh and len(hist) > 30:
            volatility = "HIGH"
        elif len(hist) <= 30 and atr_pct > np.median(np.array(hist)) * 1.8 and len(hist) > 5:
            volatility = "HIGH"
        else:
            volatility = "NORMAL"

        liquidity = "LOW" if (median_spread > 0 and spread > median_spread * 2.5) else "NORMAL"
        return RegimeState(trend=trend, volatility=volatility, liquidity=liquidity,
                           adx=round(adx_now, 1), atr_pct=round(atr_pct, 5))

    @staticmethod
    def strategy_for(regime: RegimeState) -> str:
        """Adaptive strategy selection (blueprint 3)."""
        if regime.liquidity == "LOW":
            return "NO_TRADE"
        if regime.volatility in ("HIGH", "EXTREME"):
            return "DEFENSIVE"
        if regime.trend in ("UP", "DOWN"):
            return "BREAKOUT"
        return "MEAN_REVERSION"
