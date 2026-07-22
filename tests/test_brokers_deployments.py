from __future__ import annotations

import pytest

from altron.brokers.base import (
    BrokerBackend,
    BrokerOrder,
    BrokerOrderResult,
    BrokerStatus,
)
from altron.brokers.registry import BrokerRegistry
from altron.brokers.tradovate import TradovateBackend
from altron.exceptions import LiveTradingDisabled
from altron.live_trading.deployments import DeploymentSpec, DeploymentStore
from altron.live_trading.models import SignalEvent
from altron.live_trading.modes import TradingModeController


class DemoBackend(BrokerBackend):
    name = "demo"

    def __init__(self) -> None:
        super().__init__()
        self.orders: list[BrokerOrder] = []
        self._status = BrokerStatus(
            backend=self.name,
            connected=True,
            environment="demo",
            execution_enabled=False,
            account_id="demo-1",
            message="connected",
        )

    async def connect(self) -> BrokerStatus:
        return self.status

    async def disconnect(self) -> None:
        self._status = self._status.model_copy(update={"connected": False})

    async def account_snapshot(self) -> dict[str, object]:
        return {"demo": True}

    async def positions(self) -> list[dict[str, object]]:
        return []

    async def net_position(self, symbol: str) -> float:
        return sum(
            order.quantity if order.side == "buy" else -order.quantity
            for order in self.orders
            if order.symbol == symbol
        )

    async def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        self.require_execution_enabled()
        self.orders.append(order)
        return BrokerOrderResult(
            backend=self.name,
            accepted=True,
            order_id=str(len(self.orders)),
            status="accepted",
        )


@pytest.mark.asyncio
async def test_tradovate_order_gate_precedes_connectivity() -> None:
    backend = TradovateBackend(access_token="not-used", environment="demo")
    with pytest.raises(LiveTradingDisabled):
        await backend.place_order(BrokerOrder(symbol="MESZ6", side="buy", quantity=1))
    registry = BrokerRegistry([backend])
    assert registry.statuses()[0].execution_enabled is False


def test_deployment_store_forces_live_records_disabled(tmp_path) -> None:
    store = DeploymentStore(tmp_path / "deployments.sqlite")
    paper = store.create(
        DeploymentSpec(
            name="paper-supertrend",
            strategy="supertrend",
            symbol="BTC/USDT",
            timeframe="1h",
            enabled=True,
        )
    )
    assert paper.enabled
    with pytest.raises(ValueError, match="Live deployment"):
        store.create(
            DeploymentSpec(
                name="live-mt5",
                strategy="supertrend",
                symbol="EURUSD",
                timeframe="1h",
                execution_backend="mt5",
                environment="live",
                enabled=True,
            )
        )
    disabled_live = store.create(
        DeploymentSpec(
            name="disabled-live",
            strategy="supertrend",
            symbol="EURUSD",
            timeframe="1h",
            execution_backend="mt5",
            environment="live",
            enabled=False,
        ),
        allow_live=True,
    )
    with pytest.raises(ValueError, match="not authorized"):
        store.set_enabled(disabled_live.id, True)


@pytest.mark.asyncio
async def test_mode_toggle_routes_only_to_verified_demo_backend() -> None:
    backend = DemoBackend()
    controller = TradingModeController(BrokerRegistry([backend]))
    event = SignalEvent(
        timestamp="2026-01-01T00:00:00Z",
        symbol="BTC/USDT",
        timeframe="1h",
        strategy="test",
        signal=1,
        confidence=1,
        entry_price=100,
    )
    assert await controller.route(event) is None
    with pytest.raises(ValueError, match="confirmation"):
        await controller.use_broker_paper(
            backend="demo", symbol="BTC/USDT", quantity=2, confirmation="wrong"
        )
    await controller.use_broker_paper(
        backend="demo",
        symbol="BTC/USDT",
        broker_symbol="BTCUSD.demo",
        quantity=2,
        confirmation="ENABLE_DEMO_ORDERS",
    )
    result = await controller.route(event)
    assert result and result.accepted
    assert backend.orders[0].symbol == "BTCUSD.demo"
    assert backend.orders[0].quantity == 2
    await controller.return_to_virtual()
    assert backend.execution_enabled is False
    assert len(backend.orders) == 2
    assert backend.orders[-1].side == "sell"
