"""AI engine tests: indicators, regime detection, confidence weighting, ML model."""
import numpy as np

from trading_app.backend.ai import indicators as ind
from trading_app.backend.ai.ml_model import EnsembleModel
from trading_app.backend.ai.signals import W_TECH, W_ML, W_SENT, W_MICRO
from trading_app.backend.config import load_config
from trading_app.backend.models import Candle

CFG = load_config()


def make_candles(n=80, start=1.0850, drift=0.0, vol=0.001, seed=1):
    rng = np.random.default_rng(seed)
    px = start
    out = []
    for i in range(n):
        px += drift + rng.normal(0, vol)
        o = px - drift / 2
        h = px + abs(rng.normal(0, vol / 2))
        l = px - abs(rng.normal(0, vol / 2))
        out.append(Candle("EURUSD", ts=float(i), open=o, high=max(h, o, px), low=min(l, o, px),
                          close=px, volume=10))
    return out


class TestIndicators:
    def test_rsi_rises_in_uptrend(self):
        closes = np.linspace(1.0, 1.2, 60)
        assert ind.rsi(closes)[-1] > 70

    def test_rsi_bounded(self):
        candles = make_candles()
        closes = np.array([c.close for c in candles])
        r = ind.rsi(closes)
        assert 0 <= r[-1] <= 100

    def test_atr_positive(self):
        candles = make_candles()
        h = np.array([c.high for c in candles]); l = np.array([c.low for c in candles])
        c = np.array([c.close for c in candles])
        assert ind.atr(h, l, c)[-1] > 0

    def test_macd_cross_meta(self):
        closes = np.linspace(1.0, 1.05, 80)
        line, sig, hist = ind.macd(closes)
        assert line[-1] > 0 and line.shape == closes.shape

    def test_adx_strong_in_trend(self):
        n = 80
        closes = np.linspace(1.0, 1.1, n)
        highs = closes + 0.001
        lows = closes - 0.001
        assert ind.adx(highs, lows, closes)[-1] > 25


class TestEnsembleModel:
    def test_proba_in_range(self):
        m = EnsembleModel()
        p = m.predict_proba_up(make_candles(drift=0.0005))
        assert 0.0 <= p <= 1.0
        p2 = m.predict_proba_up(make_candles(drift=-0.0005, seed=2))
        assert 0.0 <= p2 <= 1.0

    def test_online_learning_moves_weights(self):
        m = EnsembleModel()
        w0 = m.w.copy()
        candles = make_candles(drift=0.0005)
        for _ in range(5):
            m.learn(candles, bar_outcome_up=True)
        assert not np.allclose(m.w, w0)
        assert m.trained_updates == 5

    def test_pattern_engulfing(self):
        m = EnsembleModel()
        candles = make_candles(n=5)
        candles[-2] = Candle("EURUSD", 3, 1.0860, 1.0865, 1.0845, 1.0848, 10)   # bearish
        candles[-1] = Candle("EURUSD", 4, 1.0846, 1.0875, 1.0846, 1.0872, 10)   # bullish engulf
        assert m.pattern_score(candles) > 0.5


class TestConfidenceWeighting:
    def test_weights_match_blueprint(self):
        assert (W_TECH, W_ML, W_SENT, W_MICRO) == (0.30, 0.40, 0.20, 0.10)
        assert abs(W_TECH + W_ML + W_SENT + W_MICRO - 1.0) < 1e-12
