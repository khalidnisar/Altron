from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, cast

import pandas as pd

from altron.data_layer.normalization import normalize_ohlcv
from altron.live_trading.distribution import SignalSink
from altron.live_trading.models import SignalEvent
from altron.live_trading.paper import PaperBroker
from altron.live_trading.state import SignalStateMachine
from altron.live_trading.telemetry import RuntimeTelemetry
from altron.strategies.base import Strategy

if TYPE_CHECKING:
    from altron.brokers.router import ExecutionRouter

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LiveStrategy:
    strategy: Strategy
    params: dict[str, Any] = field(default_factory=dict)
    allocation: float = 0.05
    enabled: bool = True
    instance_name: str | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.allocation <= 1:
            raise ValueError("Live strategy allocation must be between zero and one")


class LivePaperEngine:
    """Run selected strategy plugins on closed candles and paper-execute transitions."""

    def __init__(
        self,
        strategies: list[LiveStrategy],
        broker: PaperBroker,
        sink: SignalSink,
        *,
        history_limit: int = 5000,
        telemetry: RuntimeTelemetry | None = None,
        execution_router: ExecutionRouter | None = None,
    ) -> None:
        identifiers = [item.instance_name or item.strategy.name for item in strategies]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Live strategy instance names must be unique")
        if history_limit < 2:
            raise ValueError("history_limit must be at least two candles")
        total_allocation = sum(item.allocation for item in strategies if item.enabled)
        if total_allocation > 1 + 1e-12:
            raise ValueError("Enabled live strategy allocations cannot exceed total capital")
        self.strategies = strategies
        self.broker = broker
        self.sink = sink
        self.history_limit = history_limit
        self.telemetry = telemetry
        self.execution_router = execution_router
        self.state = SignalStateMachine()
        self.history: dict[tuple[str, str], pd.DataFrame] = {}
        if self.telemetry is not None:
            self.telemetry.attach_broker(broker)

    async def process_candle(
        self,
        symbol: str,
        timeframe: str,
        candle: dict[str, Any] | pd.Series,
        *,
        closed: bool,
    ) -> list[SignalEvent]:
        """Process only exchange-confirmed closed candles; open bars are ignored."""
        if not closed:
            return []
        row = pd.DataFrame([dict(candle)])
        key = (symbol, timeframe)
        current = self.history.get(key, pd.DataFrame())
        frame = normalize_ohlcv(pd.concat([current, row], ignore_index=True), strict=False)
        if frame.empty:
            return []
        frame = frame.tail(self.history_limit).reset_index(drop=True)
        self.history[key] = frame
        latest = frame.iloc[-1]
        price = float(latest["close"])
        timestamp = latest["timestamp"].to_pydatetime()
        if self.telemetry is not None:
            self.telemetry.record_candle(symbol, timeframe, latest)
        self.broker.mark(symbol, price)
        if self.telemetry is not None:
            self.telemetry.record_equity(timestamp)
        if self.broker.halted:
            if self.execution_router is not None:
                try:
                    await self.execution_router.halt()
                except Exception as exc:
                    logger.critical("External broker risk flatten failed: %s", exc)
            fills = self.broker.liquidate_all()
            if self.telemetry is not None:
                for fill in fills:
                    self.telemetry.record_fill(fill)
                self.telemetry.record_equity(timestamp)
            logger.critical(
                "Portfolio drawdown circuit breaker halted execution; liquidated %d virtual position(s)",
                len(fills),
            )
            return []
        events: list[SignalEvent] = []
        decisions = [
            (specification, int(specification.strategy(frame, specification.params).iloc[-1]))
            for specification in self.strategies
            if specification.enabled
        ]
        agreement = abs(sum(signal for _, signal in decisions)) / len(decisions) if decisions else 0.0
        for specification, signal in decisions:
            event = SignalEvent(
                timestamp=timestamp,
                symbol=symbol,
                timeframe=timeframe,
                strategy=specification.instance_name or specification.strategy.name,
                signal=cast(Literal[-1, 0, 1], signal),
                params=specification.params,
                confidence=float(agreement),
                entry_price=price,
            )
            transition_required = self.state.should_transition(event)
            broker_sync_required = bool(
                self.execution_router is not None
                and self.execution_router.needs_sync(event)
            )
            if not transition_required and not broker_sync_required:
                continue
            if self.execution_router is not None:
                try:
                    result = await self.execution_router.route(event)
                    if result is not None and (
                        not result.accepted or result.status == "partially_filled"
                    ):
                        raise RuntimeError(result.message or result.status)
                except Exception as exc:
                    logger.critical(
                        "External broker route failed for %s; retrying on next closed bar: %s",
                        event.strategy,
                        exc,
                    )
                    continue
            if transition_required:
                fill = self.broker.apply_signal(event, allocation=specification.allocation)
                if self.telemetry is not None:
                    self.telemetry.record_fill(fill)
                    self.telemetry.record_equity(timestamp)
                await self.sink.publish(event)
                self.state.commit(event)
                events.append(event)
        return events
