from __future__ import annotations

import os
from typing import Any

from altron.brokers.base import BrokerBackend, BrokerStatus
from altron.brokers.mt5 import MT5Backend
from altron.brokers.tradovate import TradovateBackend


class BrokerRegistry:
    """Runtime registry used by the API and dashboard connectivity panel."""

    def __init__(self, backends: list[BrokerBackend] | None = None) -> None:
        self._backends = {backend.name: backend for backend in backends or []}

    def register(self, backend: BrokerBackend, *, replace: bool = False) -> None:
        if backend.name in self._backends and not replace:
            raise ValueError(f"Broker backend {backend.name!r} is already registered")
        self._backends[backend.name] = backend

    def names(self) -> list[str]:
        return sorted(self._backends)

    def get(self, name: str) -> BrokerBackend:
        try:
            return self._backends[name]
        except KeyError:
            raise KeyError(f"Broker backend {name!r} is not configured") from None

    def statuses(self) -> list[BrokerStatus]:
        return [self._backends[name].status for name in self.names()]

    async def connect(self, name: str) -> BrokerStatus:
        return await self.get(name).connect()

    async def disconnect(self, name: str) -> BrokerStatus:
        backend = self.get(name)
        await backend.disconnect()
        return backend.status

    async def account_snapshot(self, name: str) -> dict[str, Any]:
        return await self.get(name).account_snapshot()


def registry_from_environment(*, execution_enabled: bool = False) -> BrokerRegistry:
    """Build configured connectors without connecting or validating credentials."""
    backends: list[BrokerBackend] = []
    tradovate_token = os.getenv("TRADOVATE_ACCESS_TOKEN")
    tradovate_username = os.getenv("TRADOVATE_USERNAME")
    if tradovate_token or tradovate_username:
        cid = os.getenv("TRADOVATE_CID")
        account_id = os.getenv("TRADOVATE_ACCOUNT_ID")
        backends.append(
            TradovateBackend(
                environment="live" if os.getenv("TRADOVATE_ENV", "demo") == "live" else "demo",
                access_token=tradovate_token,
                username=tradovate_username,
                password=os.getenv("TRADOVATE_PASSWORD"),
                app_id=os.getenv("TRADOVATE_APP_ID"),
                app_version=os.getenv("TRADOVATE_APP_VERSION", "1.0"),
                client_id=int(cid) if cid else None,
                client_secret=os.getenv("TRADOVATE_SEC"),
                device_id=os.getenv("TRADOVATE_DEVICE_ID"),
                account_id=int(account_id) if account_id else None,
                account_spec=os.getenv("TRADOVATE_ACCOUNT_SPEC"),
                execution_enabled=execution_enabled,
            )
        )
    if os.getenv("MT5_ENABLE_CONNECTOR", "false").lower() == "true":
        login = os.getenv("MT5_LOGIN")
        backends.append(
            MT5Backend(
                terminal_path=os.getenv("MT5_TERMINAL_PATH"),
                login=int(login) if login else None,
                password=os.getenv("MT5_PASSWORD"),
                server=os.getenv("MT5_SERVER"),
                execution_enabled=execution_enabled,
            )
        )
    return BrokerRegistry(backends)
