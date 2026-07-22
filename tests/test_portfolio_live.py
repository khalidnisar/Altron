from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from altron.brokers.base import BrokerOrderResult
from altron.live_trading.distribution import SignalHub
from altron.live_trading.engine import LivePaperEngine, LiveStrategy
from altron.live_trading.models import SignalEvent
from altron.live_trading.paper import PaperBroker
from altron.live_trading.state import SignalStateMachine
from altron.live_trading.telemetry import RuntimeTelemetry
from altron.portfolio.manager import PortfolioManager, StrategySleeve
from altron.strategies.registry import get_strategy


def event(signal: int, timestamp: datetime | None = None) -> SignalEvent:
    return SignalEvent(
        timestamp=timestamp or datetime.now(UTC),
        symbol="BTC/USDT",
        timeframe="1h",
        strategy="test",
        signal=signal,
        params={},
        confidence=1,
        entry_price=100,
    )


def test_signal_state_machine_deduplicates_and_rejects_stale() -> None:
    state = SignalStateMachine()
    now = datetime.now(UTC)
    assert state.transition(event(1, now))
    assert not state.transition(event(1, now + timedelta(hours=1)))
    assert not state.transition(event(-1, now))
    assert state.transition(event(-1, now + timedelta(hours=2)))


def test_paper_broker_tracks_position_and_realized_pnl() -> None:
    broker = PaperBroker(initial_cash=10_000, commission_bps=0, slippage_bps=0, max_position_fraction=.1)
    first = broker.apply_signal(event(1))
    assert first and first.side == "buy"
    close = event(0, datetime.now(UTC) + timedelta(hours=1)).model_copy(update={"entry_price": 110.0})
    fill = broker.apply_signal(close)
    assert fill and fill.realized_pnl > 0
    assert broker.equity > 10_000


def test_risk_liquidation_can_close_a_halted_paper_broker() -> None:
    broker = PaperBroker(
        initial_cash=10_000,
        commission_bps=0,
        slippage_bps=0,
        max_position_fraction=1,
        max_drawdown=.1,
    )
    broker.apply_signal(event(1), allocation=1)
    broker.mark("BTC/USDT", 70)
    assert broker.halted
    fills = broker.liquidate_all()
    assert len(fills) == 1
    assert broker.positions[("test", "BTC/USDT")].quantity == pytest.approx(0)
    assert broker.halted


def test_portfolio_filters_highly_correlated_sleeves() -> None:
    index = pd.RangeIndex(200)
    generator = np.random.default_rng(3)
    first = pd.Series(generator.normal(0.001, 0.01, len(index)), index=index)
    sleeves = [
        StrategySleeve("one", first),
        StrategySleeve("copy", first * 1.01),
        StrategySleeve("different", pd.Series(generator.normal(0.001, 0.01, len(index)), index=index)),
    ]
    manager = PortfolioManager()
    selected = manager.select_decorrelated(sleeves)
    assert len(selected) == 2
    weights = manager.allocate(sleeves, "volatility_parity")
    assert weights.sum() == pytest.approx(1)


@pytest.mark.asyncio
async def test_live_engine_ignores_open_bars_and_emits_transitions(candles: pd.DataFrame) -> None:
    hub = SignalHub()
    broker = PaperBroker()
    telemetry = RuntimeTelemetry()
    engine = LivePaperEngine(
        [LiveStrategy(get_strategy("ma_crossover"), {"fast_period": 2, "slow_period": 3})],
        broker,
        hub,
        telemetry=telemetry,
    )
    for row in candles.head(5).to_dict("records"):
        assert await engine.process_candle("BTC/USDT", "1h", row, closed=False) == []
        await engine.process_candle("BTC/USDT", "1h", row, closed=True)
    assert len(hub.recent()) >= 1
    assert len(telemetry.candles("BTC/USDT", "1h")) == 5
    snapshot = telemetry.portfolio()
    assert snapshot["connected"] is True
    assert "equity" in snapshot


class RetryRouter:
    def __init__(self) -> None:
        self.calls = 0
        self.synced = False
        self.halts = 0

    def needs_sync(self, event: SignalEvent) -> bool:
        return not self.synced and event.signal != 0

    async def route(self, event: SignalEvent) -> BrokerOrderResult | None:
        if event.signal == 0:
            return None
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary rejection")
        self.synced = True
        return BrokerOrderResult(backend="retry", accepted=True, status="accepted")

    async def halt(self) -> list[BrokerOrderResult]:
        self.halts += 1
        return []


@pytest.mark.asyncio
async def test_live_engine_retries_uncommitted_broker_transition(candles: pd.DataFrame) -> None:
    hub = SignalHub()
    router = RetryRouter()
    engine = LivePaperEngine(
        [LiveStrategy(get_strategy("ma_crossover"), {"fast_period": 2, "slow_period": 3})],
        PaperBroker(),
        hub,
        execution_router=router,
    )
    for row in candles.head(8).to_dict("records"):
        await engine.process_candle("BTC/USDT", "1h", row, closed=True)
    assert router.calls >= 2
    assert router.synced
    assert hub.recent()
