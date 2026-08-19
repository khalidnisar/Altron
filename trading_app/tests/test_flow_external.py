"""Tests for merged repo features: Directional Flow (TIS/exhaustion) and
external signal ingestion (alias normalization + risk-wrapped routing)."""
import numpy as np
import pytest

from trading_app.backend.ai.flow import FlowEngine, efficiency_ratio
from trading_app.backend.brokers.simulated import SimulatedBroker
from trading_app.backend.config import load_config
from trading_app.backend.execution.engine import ExecutionEngine
from trading_app.backend.external import (PayloadError, build_external_signal,
                                          normalize_direction)
from trading_app.backend.graph.pipeline import TradingGraph
from trading_app.backend.models import Candle, Side
from trading_app.backend.ai.signals import SignalEngine
from trading_app.backend.risk.engine import RiskEngine

CFG = load_config()
EUR = CFG.symbols["EURUSD"]


def mk_candles(n=90, start=1.0850, step=0.0005, vol=0.0002, seed=7):
    rng = np.random.default_rng(seed)
    px, out = start, []
    for i in range(n):
        px += step + rng.normal(0, vol)
        o = px - step / 2
        h, l = px + vol / 2, px - vol / 2
        out.append(Candle("EURUSD", float(i * 900), o, max(h, o, px), min(l, o, px), px, 10))
    return out


class TestFlow:
    def test_er_high_in_strong_trend(self):
        closes = np.linspace(1.0, 1.1, 60)
        assert efficiency_ratio(closes) > 0.9

    def test_er_low_in_chop(self):
        rng = np.random.default_rng(0)
        closes = 1.0 + rng.normal(0, 0.001, 60).cumsum() * 0.1
        assert efficiency_ratio(closes) < 0.4

    def test_tis_rewards_clean_uptrend(self):
        eng = FlowEngine()
        res = eng.analyze("EURUSD", mk_candles(step=0.0006, vol=0.00008))
        assert res["trend_dir"] == 1
        assert res["tis"] > 55
        assert res["exhaustion"] < 75

    def test_exhaustion_on_weak_trend_with_rejection(self):
        # grind up then print big upper-wick rejection candles
        candles = mk_candles(n=80, step=0.0002, vol=0.0001)
        px = candles[-1].close
        for i in range(14):
            c = Candle("EURUSD", float((80 + i) * 900), px, px + 0.0008, px - 0.00002, px + 0.00002, 10)
            candles.append(c)
            px += 0.00005
        res = FlowEngine().analyze("EURUSD", candles)
        assert res["wick_rejection"] > 60
        assert res["exhaustion"] > 45

    def test_personality_bias_fields(self):
        res = FlowEngine().analyze("EURUSD", mk_candles())
        assert "confidence_bias" in res["personality"]
        assert "vol_ratio" in res["personality"]


class TestExternal:
    def test_alias_normalization(self):
        assert normalize_direction("LONG") is Side.BUY
        assert normalize_direction("strong_buy") is Side.BUY
        assert normalize_direction("Bullish") is Side.BUY
        assert normalize_direction("SHORT") is Side.SELL
        assert normalize_direction("bear") is Side.SELL
        assert normalize_direction("???") is None
        assert normalize_direction(None) is None

    def test_unknown_symbol_rejected(self):
        with pytest.raises(PayloadError):
            build_external_signal({"symbol": "DOGE", "signal": "BUY"}, CFG, [], 0.0)

    def test_unknown_direction_rejected(self):
        with pytest.raises(PayloadError):
            build_external_signal({"symbol": "EURUSD", "signal": "MOON"}, CFG, [], 0.0)

    def test_signal_wrapped_with_hard_stops(self):
        sig = build_external_signal({"symbol": "EURUSD", "direction": "LONG",
                                     "confidence": 80, "source": "tv-webhook"},
                                    CFG, mk_candles(), 100.0)
        assert sig.strategy == "EXTERNAL"
        assert sig.side is Side.BUY
        assert sig.stop_loss < sig.entry < sig.take_profit      # hard stops mandatory
        rr = (sig.take_profit - sig.entry) / (sig.entry - sig.stop_loss)
        assert rr >= 1.99                                        # blueprint R:R enforced


class TestExternalThroughGraph:
    def _mk(self, seed=21):
        broker = SimulatedBroker(CFG, seed=seed)
        for i in range(10):                      # warm the tick cache
            broker.step(float(i))
        risk = RiskEngine(CFG)
        risk.update(1, 100_000, 0.0)
        exe = ExecutionEngine(CFG, broker, risk)
        g = TradingGraph(CFG, SignalEngine(CFG), risk, exe, broker)
        return g, broker, exe

    def test_external_routed_via_risk_gate(self):
        g, broker, _ = self._mk()
        candles = mk_candles()
        sig = build_external_signal({"symbol": "EURUSD", "signal": "STRONG BUY",
                                     "confidence": 82}, CFG, candles, 100.0)
        out = g.execute_external(sig, candles, EUR.point * 12, 100.0, True)
        nodes = [t["node"] for t in out["trace"]]
        assert nodes[0] == "external" and "risk_gate" in nodes
        if out["gate"]["approved"]:
            assert nodes[-1] == "execution" and broker.positions()
        else:
            assert nodes[-1] == "learning"

    def test_external_blocked_when_emergency(self):
        g, broker, exe = self._mk()
        g.risk.emergency_stop("kill switch test")
        candles = mk_candles()
        sig = build_external_signal({"symbol": "EURUSD", "signal": "BUY"}, CFG, candles, 100.0)
        out = g.execute_external(sig, candles, EUR.point * 12, 100.0, True)
        assert out["outcome"] == "GATE_REJECTED"
        assert not broker.positions()
        assert any("EMERGENCY" in b for b in out["gate"]["blockers"])
