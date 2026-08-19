"""Broker adapter contract — every adapter (simulated / MT5 demo) implements this."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import AccountInfo, Deal, Position, Side, Tick


class BrokerError(Exception):
    pass


class SafetyViolation(BrokerError):
    """Raised when a safety invariant is violated (e.g. non-demo account)."""


class Broker(ABC):
    name: str = "abstract"

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def connected(self) -> bool: ...

    @abstractmethod
    def account(self) -> AccountInfo: ...

    @abstractmethod
    def tick(self, symbol: str) -> Tick: ...

    @abstractmethod
    def positions(self) -> list[Position]: ...

    @abstractmethod
    def market_order(self, symbol: str, side: Side, volume: float,
                     stop_loss: float, take_profit: float) -> Position:
        """RULE 2: stop loss is mandatory."""

    @abstractmethod
    def modify_stops(self, position_id: int, stop_loss: float, take_profit: float) -> None: ...

    @abstractmethod
    def close_position(self, position_id: int, volume: float | None = None,
                       reason: str = "MANUAL") -> Deal: ...
