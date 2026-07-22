from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from altron.exceptions import LiveTradingDisabled


class BrokerOrder(BaseModel):
    """Vendor-neutral order request used by execution adapters."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    order_type: Literal["market", "limit", "stop"] = "market"
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    time_in_force: Literal["day", "gtc", "ioc"] = "day"
    client_order_id: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("A limit order requires limit_price")
        if self.order_type == "stop" and self.stop_price is None:
            raise ValueError("A stop order requires stop_price")


class BrokerOrderResult(BaseModel):
    backend: str
    accepted: bool
    order_id: str | None = None
    status: str
    message: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class BrokerStatus(BaseModel):
    backend: str
    connected: bool = False
    environment: str = "unknown"
    execution_enabled: bool = False
    account_id: str | None = None
    message: str = "not connected"
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BrokerBackend(ABC):
    """Async broker contract with a hard execution gate."""

    name: str

    def __init__(self, *, execution_enabled: bool = False) -> None:
        self.execution_enabled = execution_enabled
        self._status = BrokerStatus(
            backend=self.name,
            execution_enabled=execution_enabled,
        )

    @property
    def status(self) -> BrokerStatus:
        return self._status.model_copy(update={"checked_at": datetime.now(UTC)})

    def require_execution_enabled(self) -> None:
        if not self.execution_enabled:
            raise LiveTradingDisabled(
                f"{self.name} order submission is disabled. Connectivity and account reads do not "
                "enable execution. Enable only a verified demo account for broker-paper mode, or "
                "pass the separate live-trading authorization gates in a custom execution service."
            )

    def set_demo_execution(self, enabled: bool) -> None:
        """Enable order routing only for a connected, vendor-verified demo account."""
        if enabled and (not self._status.connected or self._status.environment != "demo"):
            raise LiveTradingDisabled(
                f"{self.name} demo routing requires a connected backend positively identified as demo"
            )
        self.execution_enabled = enabled
        self._status = self._status.model_copy(update={"execution_enabled": enabled})

    def set_live_execution(self, enabled: bool, *, authorized: bool = False) -> None:
        """Enable a live backend only after the application-level authorization gate."""
        if enabled and (
            not authorized
            or not self._status.connected
            or self._status.environment != "live"
        ):
            raise LiveTradingDisabled(
                f"{self.name} live routing requires explicit authorization and a verified live account"
            )
        self.execution_enabled = enabled
        self._status = self._status.model_copy(update={"execution_enabled": enabled})

    @abstractmethod
    async def connect(self) -> BrokerStatus:
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def account_snapshot(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def net_position(self, symbol: str) -> float:
        """Return the broker-observed signed net position for ``symbol``."""
        raise NotImplementedError

    @abstractmethod
    async def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        raise NotImplementedError
