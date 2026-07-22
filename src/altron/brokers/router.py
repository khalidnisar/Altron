from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from altron.brokers.base import BrokerBackend, BrokerOrder, BrokerOrderResult
from altron.live_trading.models import SignalEvent


class ExecutionRouter(Protocol):
    def needs_sync(self, event: SignalEvent) -> bool: ...

    async def route(self, event: SignalEvent) -> BrokerOrderResult | None: ...

    async def halt(self) -> list[BrokerOrderResult]: ...


@dataclass(slots=True)
class BrokerExecutionRouter:
    """Translate target-position transitions into reconciled quantity deltas."""

    backend: BrokerBackend
    quantities: dict[str, float]
    symbol_map: dict[str, str] = field(default_factory=dict)
    _targets: dict[tuple[str, str], float] = field(default_factory=dict, init=False)

    def needs_sync(self, event: SignalEvent) -> bool:
        if event.symbol not in self.quantities:
            return False
        desired = float(event.signal) * self.quantities[event.symbol]
        return self._targets.get((event.strategy, event.symbol)) != desired

    async def route(self, event: SignalEvent) -> BrokerOrderResult | None:
        if event.symbol not in self.quantities:
            raise ValueError(f"No execution quantity configured for {event.symbol}")
        key = (event.strategy, event.symbol)
        previous = self._targets.get(key, 0.0)
        desired = float(event.signal) * self.quantities[event.symbol]
        delta = desired - previous
        if abs(delta) < 1e-12:
            return None
        broker_symbol = self.symbol_map.get(event.symbol, event.symbol)
        observed = await self.backend.net_position(broker_symbol)
        aggregate_expected = sum(
            target
            for (strategy_name, target_symbol), target in self._targets.items()
            if target_symbol == event.symbol
        )
        if abs(observed - aggregate_expected) > 1e-9:
            raise RuntimeError(
                f"Broker position drift for {broker_symbol}: observed={observed}, "
                f"expected={aggregate_expected}. Reconcile manually before routing."
            )
        result = await self.backend.place_order(
            BrokerOrder(
                symbol=broker_symbol,
                side="buy" if delta > 0 else "sell",
                quantity=abs(delta),
                order_type="market",
                client_order_id=f"altron:{event.strategy}:{int(event.timestamp.timestamp())}",
            )
        )
        if result.accepted and result.status != "partially_filled":
            self._targets[key] = desired
        return result

    async def halt(self) -> list[BrokerOrderResult]:
        results: list[BrokerOrderResult] = []
        for (strategy, symbol), target in list(self._targets.items()):
            if abs(target) < 1e-12:
                continue
            result = await self.backend.place_order(
                BrokerOrder(
                    symbol=self.symbol_map.get(symbol, symbol),
                    side="sell" if target > 0 else "buy",
                    quantity=abs(target),
                    client_order_id=f"altron-halt:{strategy}:{symbol}",
                )
            )
            results.append(result)
            if not result.accepted:
                raise RuntimeError(f"Broker halt order rejected: {result.message}")
            self._targets[(strategy, symbol)] = 0.0
        return results
