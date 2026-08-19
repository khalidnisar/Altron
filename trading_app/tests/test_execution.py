"""Execution + simulated broker tests: fills, SL/TP, partials, P&L, trailing."""
import pytest

from trading_app.backend.brokers.simulated import SimulatedBroker
from trading_app.backend.brokers.base import BrokerError
from trading_app.backend.config import load_config
from trading_app.backend.execution.engine import ExecutionEngine
from trading_app.backend.models import Side, Signal
from trading_app.backend.risk.engine import RiskEngine

CFG = load_config()
EUR = CFG.symbols["EURUSD"]


def setup_engine():
    broker = SimulatedBroker(CFG, seed=3)
    risk = RiskEngine(CFG)
    eng = ExecutionEngine(CFG, broker, risk)
    broker.price_override["EURUSD"] = 1.0850
    for _ in range(20):          # warm the tick cache
        broker.step(0.0)
    return broker, risk, eng


def sig(side=Side.BUY, sl=1.0840, tp=1.0870):
    return Signal(symbol="EURUSD", side=side, ts=0.0, confidence=85.0,
                  technical=85, ml=85, sentiment=85, microstructure=85, confluence=4,
                  regime="UP/NORMAL/NORMAL", strategy="BREAKOUT",
                  entry=1.0850, stop_loss=sl, take_profit=tp, atr=0.0008)


class TestBrokerBasics:
    def test_market_order_requires_stop(self):
        broker, _, _ = setup_engine()
        with pytest.raises(BrokerError):
            broker.market_order("EURUSD", Side.BUY, 1.0, 0.0, 1.10)

    def test_floating_pnl_sign(self):
        broker = SimulatedBroker(CFG, seed=3)
        broker.price_override["EURUSD"] = 1.0850
        broker.step(0.0)
        pos = broker.market_order("EURUSD", Side.BUY, 1.0, 1.0800, 1.0900)
        broker.price_override["EURUSD"] = 1.0860      # +100 pips move up
        broker.step(1.0)
        floating = broker.account().equity - broker.account().balance
        assert floating > 0
        broker.price_override["EURUSD"] = 1.0840
        broker.step(2.0)
        floating = broker.account().equity - broker.account().balance
        assert floating < 0
        assert pos.id in [p.id for p in broker.positions()]

    def test_stop_loss_fills_broker_side(self):
        broker = SimulatedBroker(CFG, seed=3)
        broker.price_override["EURUSD"] = 1.0850
        broker.step(0.0)
        broker.market_order("EURUSD", Side.BUY, 1.0, 1.0840, 1.0900)
        broker.price_override["EURUSD"] = 1.0830      # crashes through SL
        broker.step(1.0)
        assert broker.positions() == []
        assert broker.deals()[-1].reason == "SL"
        assert broker.deals()[-1].pnl < 0

    def test_take_profit_fills(self):
        broker = SimulatedBroker(CFG, seed=3)
        broker.price_override["EURUSD"] = 1.0850
        broker.step(0.0)
        broker.market_order("EURUSD", Side.BUY, 1.0, 1.0840, 1.0860)
        broker.price_override["EURUSD"] = 1.0865
        broker.step(1.0)
        assert broker.positions() == []
        assert broker.deals()[-1].reason == "TP"
        assert broker.deals()[-1].pnl > 0


class TestExecutionEngine:
    def test_signal_opens_position(self):
        broker, risk, eng = setup_engine()
        risk.update(1, 100_000, 0.0)
        pos = eng.process_signal(sig(), spread_price=EUR.point * 12, vol_scale=1.0,
                                 current_candles=[])
        assert pos is not None
        assert broker.positions()
        assert eng.recent_signals[0]["approved"]

    def test_partial_tp_and_breakeven(self):
        broker, risk, eng = setup_engine()
        risk.update(1, 100_000, 0.0)
        # 10-pip SL, 20-pip TP → TP25% hits at +5 pips, TP50% at +10
        pos = eng.process_signal(sig(sl=1.0840, tp=1.0870), spread_price=EUR.point * 12,
                                 vol_scale=1.0, current_candles=[])
        full_vol = pos.volume
        broker.price_override["EURUSD"] = 1.0857      # past TP1 (+5p) → partial + arm
        broker.step(10.0)
        eng.manage_positions(10.0, {"EURUSD": 1.0})
        p = broker.positions()[0]
        assert p.volume < full_vol
        assert any(d.reason.startswith("PARTIAL_TP") for d in broker.deals())
        broker.price_override["EURUSD"] = 1.0863      # past TP2 (+10p) → BE/trailing
        broker.step(20.0)
        eng.manage_positions(20.0, {"EURUSD": 2.0})
        p = broker.positions()[0]
        assert p.stop_loss > 1.0840                  # stop ratcheted up
        assert eng.managed[p.id].breakeven_moved

    def test_time_stop_closes_dead_trade(self):
        broker, risk, eng = setup_engine()
        risk.update(1, 100_000, 0.0)
        eng.process_signal(sig(), spread_price=EUR.point * 12, vol_scale=1.0,
                           current_candles=[])
        broker.price_override["EURUSD"] = 1.0851      # flat — within time-stop R band
        broker.step(10.0)
        eng.manage_positions(10.0, {"EURUSD": 200.0})  # very old position
        assert broker.positions() == []
        assert broker.deals()[-1].reason == "TIME_STOP"

    def test_close_all(self):
        broker, risk, eng = setup_engine()
        risk.update(1, 100_000, 0.0)
        eng.process_signal(sig(), spread_price=EUR.point * 12, vol_scale=1.0, current_candles=[])
        n = eng.close_all("EMERGENCY")
        assert n == 1 and broker.positions() == []
        assert risk.rolling_stats()[0] == 1          # result registered

    def test_blocked_signal_records_blockers(self):
        broker, risk, eng = setup_engine()
        risk.emergency_stop("unit test")
        pos = eng.process_signal(sig(), spread_price=EUR.point * 12, vol_scale=1.0,
                                 current_candles=[])
        assert pos is None
        assert eng.recent_signals[0]["approved"] is False
