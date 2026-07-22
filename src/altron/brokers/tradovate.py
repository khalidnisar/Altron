from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from altron.brokers.base import BrokerBackend, BrokerOrder, BrokerOrderResult, BrokerStatus


class TradovateBackend(BrokerBackend):
    """Tradovate REST connectivity with demo-by-default routing.

    Tokens and credentials remain in memory. The adapter authenticates through
    ``auth/accesstokenrequest`` and uses Bearer authentication for account and order
    endpoints. It does not open a websocket or submit an order during ``connect``.
    """

    name = "tradovate"

    def __init__(
        self,
        *,
        environment: Literal["demo", "live"] = "demo",
        access_token: str | None = None,
        username: str | None = None,
        password: str | None = None,
        app_id: str | None = None,
        app_version: str = "1.0",
        client_id: int | None = None,
        client_secret: str | None = None,
        device_id: str | None = None,
        account_id: int | None = None,
        account_spec: str | None = None,
        execution_enabled: bool = False,
    ) -> None:
        super().__init__(execution_enabled=execution_enabled)
        self.environment = environment
        self.base_url = f"https://{environment}.tradovateapi.com/v1"
        self.websocket_url = f"wss://{environment}.tradovateapi.com/v1/websocket"
        self.access_token = access_token
        self.username = username
        self.password = password
        self.app_id = app_id
        self.app_version = app_version
        self.client_id = client_id
        self.client_secret = client_secret
        self.device_id = device_id
        self.account_id = account_id
        self.account_spec = account_spec or username
        self.expiration_time: datetime | None = None
        self._accounts: list[dict[str, Any]] = []
        self._status = BrokerStatus(
            backend=self.name,
            environment=environment,
            execution_enabled=execution_enabled,
            account_id=str(account_id) if account_id is not None else None,
        )

    def _request_sync(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> Any:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if authenticated:
            if not self.access_token:
                raise RuntimeError("Tradovate access token is unavailable")
            headers["Authorization"] = f"Bearer {self.access_token}"
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}/{path.lstrip('/')}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed vendor base
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            # Do not include request headers, credentials, or the token in errors.
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Tradovate HTTP {exc.code}: {detail}") from None

    async def _request(self, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(self._request_sync, *args, **kwargs)

    async def _authenticate(self) -> None:
        if self.access_token:
            token_is_current = (
                self.expiration_time is None
                or self.expiration_time > datetime.now(UTC) + timedelta(minutes=10)
            )
            if token_is_current or not self.username:
                return
            self.access_token = None
        required = {
            "username": self.username,
            "password": self.password,
            "app_id": self.app_id,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                "Tradovate requires an access token or credentials: " + ", ".join(missing)
            )
        payload: dict[str, Any] = {
            "name": self.username,
            "password": self.password,
            "appId": self.app_id,
            "appVersion": self.app_version,
        }
        if self.client_id is not None:
            payload["cid"] = self.client_id
        if self.client_secret:
            payload["sec"] = self.client_secret
        if self.device_id:
            payload["deviceId"] = self.device_id
        response = await self._request(
            "auth/accesstokenrequest",
            method="POST",
            payload=payload,
            authenticated=False,
        )
        if response.get("errorText") or not response.get("accessToken"):
            raise RuntimeError(f"Tradovate authentication failed: {response.get('errorText', 'no token')}")
        self.access_token = str(response["accessToken"])
        expiration = response.get("expirationTime")
        if expiration:
            self.expiration_time = datetime.fromisoformat(str(expiration).replace("Z", "+00:00"))

    async def connect(self) -> BrokerStatus:
        try:
            await self._authenticate()
            self._accounts = list(await self._request("account/list"))
            if self.account_id is None and self._accounts:
                selected = next(
                    (account for account in self._accounts if account.get("active") is not False),
                    self._accounts[0],
                )
                self.account_id = int(selected["id"])
                self.account_spec = str(selected.get("name") or self.account_spec or "")
            if self.account_id is None:
                raise RuntimeError("Tradovate returned no selectable account")
            self._status = BrokerStatus(
                backend=self.name,
                connected=True,
                environment=self.environment,
                execution_enabled=self.execution_enabled,
                account_id=str(self.account_id),
                message="connected (orders remain gated)" if not self.execution_enabled else "connected",
            )
        except Exception as exc:
            self._status = BrokerStatus(
                backend=self.name,
                connected=False,
                environment=self.environment,
                execution_enabled=self.execution_enabled,
                account_id=str(self.account_id) if self.account_id else None,
                message=str(exc),
            )
        return self.status

    async def disconnect(self) -> None:
        # REST is stateless; retain the in-memory token for a later reconnect until
        # its natural expiration. No websocket is left open by this adapter.
        self._status = self._status.model_copy(
            update={"connected": False, "message": "disconnected", "checked_at": datetime.now(UTC)}
        )

    async def account_snapshot(self) -> dict[str, Any]:
        if not self._status.connected:
            raise RuntimeError("Tradovate backend is not connected")
        accounts = await self._request("account/list")
        selected: dict[str, Any] = next(
            (account for account in accounts if int(account.get("id", -1)) == self.account_id),
            {},
        )
        return {
            "backend": self.name,
            "environment": self.environment,
            "account": selected,
            "positions": await self.positions(),
            "token_expiration": self.expiration_time.isoformat() if self.expiration_time else None,
        }

    async def positions(self) -> list[dict[str, Any]]:
        if not self._status.connected:
            raise RuntimeError("Tradovate backend is not connected")
        values = await self._request("position/list")
        output: list[dict[str, Any]] = []
        for position in values:
            raw_account_id = position.get("accountId")
            if self.account_id is None or (
                raw_account_id is not None and int(raw_account_id) == self.account_id
            ):
                output.append(dict(position))
        return output

    async def net_position(self, symbol: str) -> float:
        net = 0.0
        for position in await self.positions():
            position_symbol = position.get("symbol") or position.get("contractName")
            if position_symbol != symbol:
                continue
            value = position.get("netPos", position.get("netPosition", 0.0))
            net += float(value or 0.0)
        return net

    async def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        self.require_execution_enabled()
        if not self._status.connected or self.account_id is None or not self.account_spec:
            raise RuntimeError("Tradovate backend is not connected to an account")
        if not float(order.quantity).is_integer():
            raise ValueError("Tradovate futures order quantity must be a whole contract count")
        order_types = {"market": "Market", "limit": "Limit", "stop": "Stop"}
        times = {"day": "Day", "gtc": "GTC", "ioc": "IOC"}
        payload: dict[str, Any] = {
            "accountSpec": self.account_spec,
            "accountId": self.account_id,
            "action": "Buy" if order.side == "buy" else "Sell",
            "symbol": order.symbol,
            "orderQty": int(order.quantity),
            "orderType": order_types[order.order_type],
            "timeInForce": times[order.time_in_force],
            "isAutomated": True,
        }
        if order.limit_price is not None:
            payload["price"] = order.limit_price
        if order.stop_price is not None:
            payload["stopPrice"] = order.stop_price
        if order.client_order_id:
            payload["text"] = order.client_order_id[:64]
        response = dict(await self._request("order/placeorder", method="POST", payload=payload))
        failure = response.get("failureReason") or response.get("errorText")
        order_id = response.get("orderId")
        return BrokerOrderResult(
            backend=self.name,
            accepted=not bool(failure) and order_id is not None,
            order_id=str(order_id) if order_id is not None else None,
            status="accepted" if not failure else "rejected",
            message=str(failure or "submitted"),
            raw={key: value for key, value in response.items() if key not in {"accessToken"}},
        )
