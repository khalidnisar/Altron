"""Graph orchestration, multi-TF structure, funding & liquidation capture tests."""
import numpy as np

from trading_app.backend.ai import structure as struct
from trading_app.backend.brokers.simulated import SimulatedBroker
from trading_app.backend.config import load_config
from trading_app.backend.execution.engine import ExecutionEngine
from trading_app.backend.graph.nodes import LearningEngine
from trading_app.backend.graph.pipeline import TradingGraph
from trading_app.backend.models import Candle, Side
from trading_app.backend.ai.signals import SignalEngine
from trading_app.backend.risk.engine import RiskEngine

CFG = load_config()
EUR = CFG.symbols["EURUSD"]


def candles(n=80, start=1.0850, drift=0.0002, vol=0.0004, seed=5):
    rng = np.random.default_rng(seed)
    px = start
    out = []
    for i in range(n):
        px += drift + rng.normal(0, vol)
        h = px + abs(rng.normal(0, vol))
        l = px - abs(rng.normal(0, vol))
        out.append(Candle("EURUSD", float(i * 900), px - drift / 2, max(h, px), min(l, px), px, 10))
    return out


def make_graph(seed=11):
    broker = SimulatedBroker(CFG, seed=seed)
    for i in range(10):                       # warm the tick cache
        broker.step(float(i))
    risk = RiskEngine(CFG)
    risk.update(1, 100_000, 0.0)
    sig_eng = SignalEngine(CFG)
    exe = ExecutionEngine(CFG, broker, risk)
    g = TradingGraph(CFG, sig_eng, risk, exe, broker)
    return g, broker, risk, sig_eng, exe


class TestStructure:
    def test_uptrend_structure_up(self):
        s = struct.structure(candles(drift=0.0008, vol=0.0001))
        assert s["direction"] in ("UP", "UP_BIAS")

    def test_downtrend_structure_down(self):
        s = struct.structure(candles(drift=-0.0008, vol=0.0001, seed=9))
        assert s["direction"] in ("DOWN", "DOWN_BIAS")

    def test_resample_counts(self):
        m15 = candles(n=64)
        assert len(struct.resample(m15, 4, "EURUSD")) == 16
        assert len(struct.resample(m15, 16, "EURUSD")) == 4

    def test_multi_tf_alignment(self):
        mt = struct.multi_tf(candles(n=96, drift=0.0006, vol=0.0001), "EURUSD")
        assert set(mt["timeframes"]) == {"M15", "H1", "H4"}
        assert mt["htf_direction"] != ""
        assert -3.0 <= mt["alignment"] <= 3.0

    def test_liquidation_pools_detected(self):
        pools = struct.liquidation_pools(candles(n=90, vol=0.0006))
        assert set(pools) == {"above", "below"}
        for side in pools.values():
            for p in side:
                assert 0 <= p["strength"] <= 100
                assert p["price"] > 0


class TestFundingAndLiquidation:
    def test_funding_accrues(self):
        broker = SimulatedBroker(CFG, seed=3)
        broker.price_override["EURUSD"] = 1.0850
        broker.step(60.0)
        broker.market_order("EURUSD", Side.BUY, 1.0, 1.0800, 1.1000)
        bal_before = broker.balance
        broker.step(480 * 60.0 + 120.0)   # crosses the 8h funding bucket
        assert broker.funding_events()
        assert broker.balance != bal_before

    def test_liquidation_stopout(self):
        broker = SimulatedBroker(CFG, seed=3)
        broker.balance = 1_000.0                       # tiny account
        broker.price_override["EURUSD"] = 1.0850
        broker.step(60.0)
        broker.market_order("EURUSD", Side.BUY, 0.8, 1.0600, 1.1000)
        assert broker.positions()
        # 150-pip crash ≈ −$1,200 ⇒ equity below margin (SL intentionally far away)
        broker.price_override["EURUSD"] = 1.0700
        broker.step(600.0)
        assert not broker.positions()
        assert broker.liquidations >= 1
        assert broker.deals()[-1].reason == "LIQUIDATED"

    def test_liquidation_price_estimate(self):
        broker = SimulatedBroker(CFG, seed=3)
        broker.price_override["EURUSD"] = 1.0850
        broker.step(60.0)
        pos = broker.market_order("EURUSD", Side.BUY, 1.0, 1.0700, 1.1000)
        liq = broker.liquidation_price(pos)
        assert liq < pos.entry_price          # long liquidates below entry


class TestGraphPipeline:
    def test_cycle_produces_trace(self):
        g, broker, *_ = make_graph()
        out = g.run_cycle("EURUSD", 1000.0, 100, candles(), EUR.point * 12, 1, True)
        nodes = [t["node"] for t in out["trace"]]
        assert nodes[:2] == ["market_state", "research"]
        assert out["outcome"] in ("NO_SETUP", "EXECUTED", "GATE_REJECTED", "BROKER_REJECTED")
        assert "EURUSD" in g.market_views

    def test_market_state_contents(self):
        g, *_ = make_graph()
        g.run_cycle("EURUSD", 1000.0, 100, candles(), EUR.point * 12, 0, True)
        mv = g.market_views["EURUSD"]
        assert "structure" in mv and "liquidation_pools" in mv and "funding_rate" in mv
        assert mv["structure"]["htf_direction"] in ("UP", "UP_BIAS", "FLAT", "DOWN", "DOWN_BIAS")

    def test_risk_gate_fail_routes_to_learning(self):
        g, broker, risk, *_ = make_graph()
        risk.emergency_stop("test halt")
        out = g.run_cycle("EURUSD", 1000.0, 100, candles(drift=0.001, vol=0.0001),
                          EUR.point * 12, 1, True)
        if out.get("signal") is not None:              # only meaningful if a setup existed
            assert any(t["node"] == "learning" for t in out["trace"])
            assert out["outcome"] == "GATE_REJECTED"

    def test_learn_from_deal_updates_model_and_stats(self):
        from trading_app.backend.execution.engine import ManagedState

        g, broker, risk, sig_eng, exe = make_graph()
        broker.price_override["EURUSD"] = 1.0850
        broker.step(60.0)
        pos = broker.market_order("EURUSD", Side.BUY, 1.0, 1.0800, 1.0900)
        exe.managed[pos.id] = ManagedState(
            position_id=pos.id, symbol=pos.symbol, side=pos.side, entry=pos.entry_price,
            initial_sl=pos.stop_loss, initial_tp=pos.take_profit, atr=0.001,
            initial_volume=pos.volume, entry_candle=0.0,
            features_candles=candles())
        broker.price_override["EURUSD"] = 1.0910        # trades through TP (1.0900)
        broker.step(600.0)
        deals = [d for d in broker.deals() if d.position_id == pos.id]
        assert deals and deals[-1].reason == "TP"
        before = sig_eng.model.trained_updates
        g.learn_from_deal(deals[-1], exe.managed.get(pos.id), 700.0)
        assert sig_eng.model.trained_updates == before + 1
        assert g.learning.deals_learned == 1

    def test_strategy_circuit_breaker(self):
        learn = LearningEngine()
        for i in range(10):
            learn.learn_from_deal(
                deal=type("D", (), {"pnl": -50.0, "reason": "SL", "symbol": "EURUSD",
                                    "position_id": i, "exit_price": 1.0, "entry_price": 1.1})(),
                managed=None, model=type("M", (), {"learn": lambda *a: None})(),
                strategy="BREAKOUT", ts=1000.0 + i)
        ok, why = learn.strategy_allowed("BREAKOUT", 2000.0)
        assert not ok and "suspended" in why
        ok, _ = learn.strategy_allowed("BREAKOUT", 2000.0 + LearningEngine.BREAKER_COOLDOWN_S + 1)
        assert ok                                    # auto re-enable after cooldown
        assert any(l["kind"] == "auto-fix" for l in learn.lessons)

    def test_adaptive_threshold_tightens(self):
        learn = LearningEngine()
        for i in range(12):
            learn.learn_from_deal(
                deal=type("D", (), {"pnl": -10.0, "reason": "SL", "symbol": "EURUSD",
                                    "position_id": i, "exit_price": 1.0, "entry_price": 1.1})(),
                managed=None, model=type("M", (), {"learn": lambda *a: None})(),
                strategy="MEAN_REVERSION", ts=1000.0 + i)
        assert learn.threshold_delta > 0             # conf threshold tightened

    def test_liquidation_lesson_and_tighten(self):
        learn = LearningEngine()
        learn.learn_from_deal(
            deal=type("D", (), {"pnl": -5000.0, "reason": "LIQUIDATED", "symbol": "XAUUSD",
                                "position_id": 1, "exit_price": 1.0, "entry_price": 1.1})(),
            managed=None, model=type("M", (), {"learn": lambda *a: None})(),
            strategy="BREAKOUT", ts=1000.0)
        assert learn.liquidations_seen == 1
        assert learn.threshold_delta >= 1.5
        assert any(l["kind"] == "liquidation" for l in learn.lessons)
