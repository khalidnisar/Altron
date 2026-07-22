from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from altron.brokers.base import BrokerOrder, BrokerOrderResult
from altron.brokers.registry import BrokerRegistry
from altron.live_trading.models import SignalEvent


class TradingModeStatus(BaseModel):
    mode: Literal["virtual", "broker_paper", "live"] = "virtual"
    backend: str | None = None
    symbol: str | None = None
    broker_symbol: str | None = None
    quantity: float | None = None
    max_orders_per_minute: int | None = None
    max_daily_loss: float | None = None
    message: str = "Local virtual fills only"
    changed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TradingModeController:
    """Runtime switch between local virtual fills and verified broker demo routing.

    Live accounts are categorically rejected. Switching modes never persists a
    credential and returns to virtual mode whenever the selected backend disconnects.
    """

    CONFIRMATION = "ENABLE_DEMO_ORDERS"
    LIVE_CONFIRMATION = "ENABLE_LIVE_ORDERS"

    def __init__(self, brokers: BrokerRegistry) -> None:
        self.brokers = brokers
        self._status = TradingModeStatus()
        self._targets: dict[tuple[str, str], float] = {}
        self._order_times: deque[datetime] = deque()
        self._starting_equity: float | None = None
        self._lock = asyncio.Lock()

    @property
    def status(self) -> TradingModeStatus:
        if self._status.mode != "virtual" and self._status.backend:
            try:
                backend = self.brokers.get(self._status.backend)
            except KeyError:
                self.use_virtual("Selected broker was removed")
            else:
                expected_environment = (
                    "demo" if self._status.mode == "broker_paper" else "live"
                )
                if (
                    not backend.status.connected
                    or backend.status.environment != expected_environment
                ):
                    self.use_virtual(
                        "Broker disconnected or account environment no longer matches mode"
                    )
        return self._status

    def use_virtual(self, message: str = "Local virtual fills only") -> TradingModeStatus:
        if self._status.backend:
            try:
                backend = self.brokers.get(self._status.backend)
                if backend.status.environment == "live":
                    backend.set_live_execution(False)
                else:
                    backend.set_demo_execution(False)
            except KeyError:
                pass
        self._targets.clear()
        self._order_times.clear()
        self._starting_equity = None
        self._status = TradingModeStatus(mode="virtual", message=message)
        return self._status

    async def _flatten_locked(self) -> list[BrokerOrderResult]:
        status = self.status
        results: list[BrokerOrderResult] = []
        if status.mode == "virtual" or not status.backend:
            return results
        backend = self.brokers.get(status.backend)
        if backend.status.connected and backend.execution_enabled:
            for (strategy, symbol), target in list(self._targets.items()):
                if abs(target) < 1e-12:
                    continue
                result = await backend.place_order(
                    BrokerOrder(
                        symbol=status.broker_symbol or symbol,
                        side="sell" if target > 0 else "buy",
                        quantity=abs(target),
                        order_type="market",
                        client_order_id=(
                            f"altron-demo-flat:{strategy}:"
                            f"{int(datetime.now(UTC).timestamp())}"
                        ),
                    )
                )
                results.append(result)
                if not result.accepted:
                    raise RuntimeError(
                        "Demo flatten order was rejected; broker-paper mode remains enabled: "
                        + result.message
                    )
                self._targets[(strategy, symbol)] = 0.0
        return results

    async def return_to_virtual(self) -> TradingModeStatus:
        """Flatten tracked demo targets, then disable broker-paper routing."""
        async with self._lock:
            await self._flatten_locked()
            return self.use_virtual("Demo targets flattened; local virtual fills only")

    async def halt(self) -> list[BrokerOrderResult]:
        """Risk halt: flatten the demo account and return to virtual mode."""
        async with self._lock:
            results = await self._flatten_locked()
            self.use_virtual("Risk halt flattened demo targets")
            return results

    async def use_broker_paper(
        self,
        *,
        backend: str,
        symbol: str,
        quantity: float,
        broker_symbol: str | None = None,
        confirmation: str,
    ) -> TradingModeStatus:
        async with self._lock:
            if confirmation != self.CONFIRMATION:
                raise ValueError(
                    f"Broker-paper mode requires confirmation={self.CONFIRMATION!r}"
                )
            if quantity <= 0:
                raise ValueError("Broker-paper quantity must be positive")
            if self._status.mode == "broker_paper" and any(
                abs(target) > 1e-12 for target in self._targets.values()
            ):
                raise ValueError(
                    "Switch to virtual and flatten tracked demo targets before changing routing"
                )
            selected = self.brokers.get(backend)
            if not selected.status.connected:
                raise ValueError("Connect the broker before enabling broker-paper mode")
            if selected.status.environment != "demo":
                raise ValueError(
                    "Broker-paper mode only accepts accounts positively identified as demo"
                )
            selected_symbol = broker_symbol or symbol
            observed = await selected.net_position(selected_symbol)
            if abs(observed) > 1e-9:
                raise ValueError(
                    f"Broker symbol {selected_symbol} is not flat (observed {observed}). "
                    "Flatten or reconcile it before enabling automated routing."
                )
            if self._status.backend and self._status.backend != backend:
                self.brokers.get(self._status.backend).set_demo_execution(False)
            selected.set_demo_execution(True)
            self._targets.clear()
            self._status = TradingModeStatus(
                mode="broker_paper",
                backend=backend,
                symbol=symbol,
                broker_symbol=broker_symbol or symbol,
                quantity=quantity,
                message=(
                    "Signals route to the connected demo account and remain mirrored virtually"
                ),
            )
            return self._status

    @staticmethod
    def _extract_equity(snapshot: dict[str, Any]) -> float | None:
        candidates = [snapshot, snapshot.get("account", {})]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            for name in ("equity", "netLiq", "netLiquidatingValue", "balance"):
                value = candidate.get(name)
                if value is not None:
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        continue
        return None

    async def use_live(
        self,
        *,
        backend: str,
        symbol: str,
        quantity: float,
        broker_symbol: str | None,
        max_orders_per_minute: int,
        max_daily_loss: float,
        confirmation: str,
        authorized: bool,
    ) -> TradingModeStatus:
        async with self._lock:
            if confirmation != self.LIVE_CONFIRMATION or not authorized:
                raise ValueError("Live mode requires both system and typed authorization")
            if quantity <= 0 or max_orders_per_minute < 1 or max_daily_loss <= 0:
                raise ValueError("Live risk limits and quantity must be positive")
            selected = self.brokers.get(backend)
            if not selected.status.connected or selected.status.environment != "live":
                raise ValueError("Live mode requires a connected backend identified as live")
            selected_symbol = broker_symbol or symbol
            observed = await selected.net_position(selected_symbol)
            if abs(observed) > 1e-9:
                raise ValueError(
                    f"Live symbol {selected_symbol} is not flat (observed {observed})"
                )
            starting_equity = self._extract_equity(await selected.account_snapshot())
            if starting_equity is None:
                raise ValueError("Cannot enable live mode without broker equity telemetry")
            selected.set_live_execution(True, authorized=True)
            self._targets.clear()
            self._order_times.clear()
            self._starting_equity = starting_equity
            self._status = TradingModeStatus(
                mode="live",
                backend=backend,
                symbol=symbol,
                broker_symbol=selected_symbol,
                quantity=quantity,
                max_orders_per_minute=max_orders_per_minute,
                max_daily_loss=max_daily_loss,
                message="LIVE routing enabled with reconciliation and hard risk limits",
            )
            return self._status

    def needs_sync(self, event: SignalEvent) -> bool:
        status = self.status
        if (
            status.mode == "virtual"
            or event.symbol != status.symbol
            or status.quantity is None
        ):
            return False
        desired = float(event.signal) * status.quantity
        return self._targets.get((event.strategy, event.symbol)) != desired

    async def route(self, event: SignalEvent) -> BrokerOrderResult | None:
        async with self._lock:
            status = self.status
            if status.mode == "virtual" or event.symbol != status.symbol:
                return None
            if not status.backend or status.quantity is None or not status.broker_symbol:
                raise RuntimeError("Broker-paper routing state is incomplete")
            key = (event.strategy, event.symbol)
            previous = self._targets.get(key, 0.0)
            desired = float(event.signal) * status.quantity
            delta = desired - previous
            if abs(delta) < 1e-12:
                return None
            selected = self.brokers.get(status.backend)
            if status.mode == "live":
                now = datetime.now(UTC)
                cutoff = now - timedelta(minutes=1)
                while self._order_times and self._order_times[0] < cutoff:
                    self._order_times.popleft()
                if len(self._order_times) >= (status.max_orders_per_minute or 0):
                    raise RuntimeError("Live order-rate circuit breaker is active")
                current_equity = self._extract_equity(await selected.account_snapshot())
                if current_equity is None or self._starting_equity is None:
                    raise RuntimeError("Live equity telemetry is unavailable")
                if self._starting_equity - current_equity >= (status.max_daily_loss or 0):
                    raise RuntimeError("Live daily-loss circuit breaker is active")
            observed = await selected.net_position(status.broker_symbol)
            expected = sum(self._targets.values())
            if abs(observed - expected) > 1e-9:
                raise RuntimeError(
                    f"Broker position drift: observed={observed}, expected={expected}. "
                    "Automation is paused until reconciliation."
                )
            result = await selected.place_order(
                BrokerOrder(
                    symbol=status.broker_symbol,
                    side="buy" if delta > 0 else "sell",
                    quantity=abs(delta),
                    order_type="market",
                    client_order_id=(
                        f"altron-demo:{event.strategy}:{int(event.timestamp.timestamp())}"
                    ),
                )
            )
            if result.accepted and result.status != "partially_filled":
                self._targets[key] = desired
                self._order_times.append(datetime.now(UTC))
            return result

    def as_dict(self) -> dict[str, Any]:
        return self.status.model_dump(mode="json")
