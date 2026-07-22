from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from altron.brokers.base import BrokerBackend, BrokerOrder, BrokerOrderResult, BrokerStatus


class MT5Backend(BrokerBackend):
    """MetaTrader 5 terminal bridge.

    MetaQuotes' Python package communicates with a locally installed MT5 terminal.
    The package is loaded lazily so research and Linux containers remain usable.
    All terminal calls run in worker threads because the vendor API is synchronous.
    """

    name = "mt5"

    def __init__(
        self,
        *,
        terminal_path: str | Path | None = None,
        login: int | None = None,
        password: str | None = None,
        server: str | None = None,
        timeout_ms: int = 60_000,
        portable: bool = False,
        magic: int = 910_001,
        deviation_points: int = 20,
        execution_enabled: bool = False,
    ) -> None:
        super().__init__(execution_enabled=execution_enabled)
        self.terminal_path = str(terminal_path) if terminal_path else None
        self.login = login
        self.password = password
        self.server = server
        self.timeout_ms = timeout_ms
        self.portable = portable
        self.magic = magic
        self.deviation_points = deviation_points
        self._mt5: Any = None
        self._status = BrokerStatus(
            backend=self.name,
            environment="terminal",
            execution_enabled=execution_enabled,
            account_id=str(login) if login else None,
        )

    def _module(self) -> Any:
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError(
                    "MetaTrader5 Python package and a local MT5 terminal are required. "
                    "The official package is normally run on Windows."
                ) from exc
            self._mt5 = mt5
        return self._mt5

    def _connect_sync(self) -> BrokerStatus:
        mt5 = self._module()
        kwargs: dict[str, Any] = {"timeout": self.timeout_ms, "portable": self.portable}
        if self.login is not None:
            kwargs["login"] = self.login
        if self.password:
            kwargs["password"] = self.password
        if self.server:
            kwargs["server"] = self.server
        initialized = (
            mt5.initialize(self.terminal_path, **kwargs)
            if self.terminal_path
            else mt5.initialize(**kwargs)
        )
        if not initialized:
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        account = mt5.account_info()
        if account is None:
            mt5.shutdown()
            raise RuntimeError(f"MT5 account_info failed: {mt5.last_error()}")
        account_id = str(getattr(account, "login", self.login or ""))
        trade_mode = getattr(account, "trade_mode", None)
        if trade_mode == getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0):
            environment = "demo"
        elif trade_mode == getattr(mt5, "ACCOUNT_TRADE_MODE_CONTEST", 1):
            environment = "contest"
        else:
            environment = "live"
        self._status = BrokerStatus(
            backend=self.name,
            connected=True,
            environment=environment,
            execution_enabled=self.execution_enabled,
            account_id=account_id,
            message="connected (orders remain gated)" if not self.execution_enabled else "connected",
        )
        return self.status

    async def connect(self) -> BrokerStatus:
        try:
            return await asyncio.to_thread(self._connect_sync)
        except Exception as exc:
            self._status = BrokerStatus(
                backend=self.name,
                connected=False,
                environment="terminal",
                execution_enabled=self.execution_enabled,
                account_id=str(self.login) if self.login else None,
                message=str(exc),
            )
            return self.status

    async def disconnect(self) -> None:
        if self._mt5 is not None:
            await asyncio.to_thread(self._mt5.shutdown)
        self._status = self._status.model_copy(
            update={"connected": False, "message": "disconnected", "checked_at": datetime.now(UTC)}
        )

    async def account_snapshot(self) -> dict[str, Any]:
        if not self._status.connected:
            raise RuntimeError("MT5 backend is not connected")

        def read() -> dict[str, Any]:
            account = self._module().account_info()
            if account is None:
                raise RuntimeError(f"MT5 account_info failed: {self._module().last_error()}")
            values = dict(account._asdict())
            values.pop("password", None)
            return {"backend": self.name, "account": values}

        snapshot = await asyncio.to_thread(read)
        snapshot["positions"] = await self.positions()
        return snapshot

    async def positions(self) -> list[dict[str, Any]]:
        if not self._status.connected:
            raise RuntimeError("MT5 backend is not connected")

        def read() -> list[dict[str, Any]]:
            positions = self._module().positions_get()
            if positions is None:
                raise RuntimeError(f"MT5 positions_get failed: {self._module().last_error()}")
            return [dict(position._asdict()) for position in positions]

        return await asyncio.to_thread(read)

    async def net_position(self, symbol: str) -> float:
        mt5 = self._module()
        net = 0.0
        for position in await self.positions():
            if position.get("symbol") != symbol:
                continue
            volume = float(position.get("volume", 0.0) or 0.0)
            net += volume if position.get("type") == mt5.POSITION_TYPE_BUY else -volume
        return net

    def _normalize_volume(self, requested: float, info: Any) -> float:
        minimum = float(info.volume_min)
        maximum = float(info.volume_max)
        step = float(info.volume_step)
        if requested < minimum or requested > maximum:
            raise ValueError(f"MT5 volume must be between {minimum} and {maximum}")
        steps = round((requested - minimum) / step)
        normalized = minimum + steps * step
        decimals = max(0, int(round(-math.log10(step)))) if step < 1 else 0
        return round(normalized, decimals)

    async def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        self.require_execution_enabled()
        if not self._status.connected:
            raise RuntimeError("MT5 backend is not connected")

        def submit() -> BrokerOrderResult:
            mt5 = self._module()
            info = mt5.symbol_info(order.symbol)
            if info is None:
                raise ValueError(f"Unknown MT5 symbol: {order.symbol}")
            if not info.visible and not mt5.symbol_select(order.symbol, True):
                raise RuntimeError(f"MT5 could not select symbol {order.symbol}: {mt5.last_error()}")
            tick = mt5.symbol_info_tick(order.symbol)
            if tick is None:
                raise RuntimeError(f"MT5 has no current tick for {order.symbol}")
            volume = self._normalize_volume(order.quantity, info)
            side_type = mt5.ORDER_TYPE_BUY if order.side == "buy" else mt5.ORDER_TYPE_SELL
            price = float(tick.ask if order.side == "buy" else tick.bid)
            request: dict[str, Any] = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": order.symbol,
                "volume": volume,
                "type": side_type,
                "price": price,
                "deviation": self.deviation_points,
                "magic": self.magic,
                "comment": (order.client_order_id or "altron")[:31],
                "type_time": mt5.ORDER_TIME_GTC if order.time_in_force == "gtc" else mt5.ORDER_TIME_DAY,
                "type_filling": mt5.ORDER_FILLING_RETURN,
            }
            if order.limit_price is not None:
                request["price"] = order.limit_price
                request["action"] = mt5.TRADE_ACTION_PENDING
                request["type"] = (
                    mt5.ORDER_TYPE_BUY_LIMIT if order.side == "buy" else mt5.ORDER_TYPE_SELL_LIMIT
                )
            if order.stop_price is not None:
                request["price"] = order.stop_price
                request["action"] = mt5.TRADE_ACTION_PENDING
                request["type"] = (
                    mt5.ORDER_TYPE_BUY_STOP if order.side == "buy" else mt5.ORDER_TYPE_SELL_STOP
                )
            checked = mt5.order_check(request)
            if checked is None:
                raise RuntimeError(f"MT5 order_check failed: {mt5.last_error()}")
            successful_checks = {0, getattr(mt5, "TRADE_RETCODE_DONE", 10009)}
            if checked.retcode not in successful_checks:
                return BrokerOrderResult(
                    backend=self.name,
                    accepted=False,
                    status="check_rejected",
                    message=str(checked.comment),
                    raw=dict(checked._asdict()),
                )
            result = mt5.order_send(request)
            if result is None:
                raise RuntimeError(f"MT5 order_send failed: {mt5.last_error()}")
            accepted = result.retcode in {
                mt5.TRADE_RETCODE_DONE,
                getattr(mt5, "TRADE_RETCODE_PLACED", 10008),
                getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010),
            }
            raw = dict(result._asdict())
            raw.pop("request", None)
            return BrokerOrderResult(
                backend=self.name,
                accepted=accepted,
                order_id=str(result.order) if result.order else None,
                status="accepted" if accepted else "rejected",
                message=str(result.comment),
                raw=raw,
            )

        return await asyncio.to_thread(submit)
