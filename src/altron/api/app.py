import hashlib
import hmac
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from altron.brokers.mt5 import MT5Backend
from altron.brokers.registry import BrokerRegistry
from altron.brokers.tradovate import TradovateBackend
from altron.config import Settings
from altron.data_layer.free_streams import FreeStreamManager, FreeStreamRequest
from altron.live_trading.deployments import DeploymentSpec, DeploymentStore
from altron.live_trading.distribution import SignalHub
from altron.live_trading.models import SignalEvent
from altron.live_trading.modes import TradingModeController
from altron.live_trading.telemetry import RuntimeTelemetry


class TradingViewAlert(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    symbol: str
    timeframe: str
    strategy: str
    signal: Literal[-1, 0, 1, "buy", "sell", "hold"]
    price: float = Field(gt=0)
    confidence: float = Field(default=1.0, ge=0, le=1)


class DeploymentStateUpdate(BaseModel):
    enabled: bool


class TradingModeUpdate(BaseModel):
    mode: Literal["virtual", "broker_paper", "live"]
    backend: str | None = None
    symbol: str | None = None
    broker_symbol: str | None = None
    quantity: float | None = Field(default=None, gt=0)
    max_orders_per_minute: int = Field(default=5, ge=1, le=60)
    max_daily_loss: float = Field(default=100.0, gt=0)
    confirmation: str | None = None
    explicit_live_flag: bool = False


class TradovateLinkRequest(BaseModel):
    environment: Literal["demo", "live"] = "demo"
    access_token: str | None = None
    username: str | None = None
    password: str | None = None
    app_id: str | None = None
    app_version: str = "1.0"
    client_id: int | None = None
    client_secret: str | None = None
    device_id: str | None = None
    account_id: int | None = None
    account_spec: str | None = None


class MT5LinkRequest(BaseModel):
    terminal_path: str | None = None
    login: int | None = None
    password: str | None = None
    server: str | None = None
    portable: bool = False


def _signal_number(value: int | str) -> Literal[-1, 0, 1]:
    if isinstance(value, int):
        return cast(Literal[-1, 0, 1], value)
    return cast(Literal[-1, 0, 1], {"buy": 1, "sell": -1, "hold": 0}[value])


def create_app(
    hub: SignalHub | None = None,
    *,
    webhook_secret: str | None = None,
    telemetry: RuntimeTelemetry | None = None,
    brokers: BrokerRegistry | None = None,
    deployment_store: DeploymentStore | None = None,
    mode_controller: TradingModeController | None = None,
    market_streams: FreeStreamManager | None = None,
    operator_token: str | None = None,
    webhook_max_age_seconds: int = 300,
    allow_live_deployments: bool = False,
):
    """Create the signal, telemetry, deployment, and connectivity API.

    Broker connect endpoints perform account reads only. Order submission is not
    exposed by this API and every backend remains execution-gated by default.
    """
    try:
        from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
    except ImportError as exc:
        raise RuntimeError("Install API dependencies with: pip install '.[api]'") from exc

    signal_hub = hub or SignalHub()
    runtime = telemetry or RuntimeTelemetry()
    broker_registry = brokers or BrokerRegistry()
    deployments = deployment_store or DeploymentStore()
    trading_mode = mode_controller or TradingModeController(broker_registry)
    streams = market_streams or FreeStreamManager(runtime)
    webhook_replay_cache: dict[str, datetime] = {}

    @asynccontextmanager
    async def lifespan(_: object):
        yield
        await streams.close()

    app = FastAPI(
        title="Altron Quant API",
        version="0.2.0",
        description="Research telemetry, paper signals, deployments, and broker connectivity",
        lifespan=lifespan,
    )
    app.state.signal_hub = signal_hub
    app.state.telemetry = runtime
    app.state.brokers = broker_registry
    app.state.deployments = deployments
    app.state.trading_mode = trading_mode
    app.state.market_streams = streams

    def require_operator(supplied: str | None) -> None:
        if operator_token and not hmac.compare_digest(operator_token, supplied or ""):
            raise HTTPException(status_code=401, detail="Invalid operator token")

    @app.middleware("http")
    async def protect_sensitive_reads(request: Request, call_next):
        public_paths = {
            "/health",
            "/openapi.json",
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
            "/market/catalog",
            "/webhooks/tradingview",
        }
        if operator_token and request.url.path not in public_paths:
            supplied = request.headers.get("X-Altron-Operator-Token")
            if not hmac.compare_digest(operator_token, supplied or ""):
                from fastapi.responses import JSONResponse

                return JSONResponse(status_code=401, content={"detail": "Invalid operator token"})
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "execution_mode": trading_mode.status.mode,
            "paper_broker_attached": bool(runtime.portfolio().get("connected")),
            "trading_mode": trading_mode.status.mode,
            "configured_brokers": broker_registry.names(),
            "live_deployment_activation": allow_live_deployments,
        }

    @app.get("/overview")
    async def overview() -> dict[str, object]:
        return runtime.overview(signal_hub.recent(1000))

    @app.get("/signals")
    async def signals(limit: int = 100) -> list[dict[str, object]]:
        limit = min(1000, max(1, limit))
        return [event.model_dump(mode="json") for event in signal_hub.recent(limit)]

    @app.get("/portfolio")
    async def portfolio() -> dict[str, object]:
        return runtime.portfolio()

    @app.get("/equity")
    async def equity(limit: int = 1000) -> list[dict[str, object]]:
        return runtime.equity_history(min(5000, max(1, limit)))

    @app.get("/fills")
    async def fills(limit: int = 500) -> list[dict[str, object]]:
        return runtime.fills(min(5000, max(1, limit)))

    @app.get("/candles")
    async def candles(symbol: str, timeframe: str, limit: int = 500) -> list[dict[str, object]]:
        return runtime.candles(symbol, timeframe, min(5000, max(1, limit)))

    @app.get("/runtime/mode")
    async def runtime_mode() -> dict[str, object]:
        return trading_mode.as_dict()

    @app.patch("/runtime/mode")
    async def update_runtime_mode(
        update: TradingModeUpdate,
        x_altron_operator_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        require_operator(x_altron_operator_token)
        try:
            if update.mode == "virtual":
                status = await trading_mode.return_to_virtual()
            elif update.mode == "broker_paper":
                if not update.backend or not update.symbol or update.quantity is None:
                    raise ValueError(
                        "Broker-paper mode requires backend, symbol, and quantity"
                    )
                status = await trading_mode.use_broker_paper(
                    backend=update.backend,
                    symbol=update.symbol,
                    broker_symbol=update.broker_symbol,
                    quantity=update.quantity,
                    confirmation=update.confirmation or "",
                )
            else:
                if not update.backend or not update.symbol or update.quantity is None:
                    raise ValueError("Live mode requires backend, symbol, and quantity")
                settings = Settings()
                settings.authorize_live_trading(update.explicit_live_flag)
                status = await trading_mode.use_live(
                    backend=update.backend,
                    symbol=update.symbol,
                    broker_symbol=update.broker_symbol,
                    quantity=update.quantity,
                    max_orders_per_minute=update.max_orders_per_minute,
                    max_daily_loss=update.max_daily_loss,
                    confirmation=update.confirmation or "",
                    authorized=not settings.paper_trading,
                )
        except (ValueError, KeyError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return status.model_dump(mode="json")

    @app.get("/market/catalog")
    async def market_catalog() -> dict[str, object]:
        return streams.catalog()

    @app.get("/market/subscriptions")
    async def market_subscriptions() -> list[dict[str, object]]:
        return [status.model_dump(mode="json") for status in streams.statuses()]

    @app.post("/market/subscriptions", status_code=201)
    async def subscribe_market(
        request: FreeStreamRequest,
        x_altron_operator_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        require_operator(x_altron_operator_token)
        try:
            return streams.subscribe(request).model_dump(mode="json")
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.delete("/market/subscriptions/{subscription_id}")
    async def stop_market_subscription(
        subscription_id: str,
        x_altron_operator_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        require_operator(x_altron_operator_token)
        try:
            status = await streams.stop(subscription_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return status.model_dump(mode="json")

    @app.get("/brokers")
    async def broker_statuses() -> list[dict[str, object]]:
        paper = runtime.portfolio()
        values: list[dict[str, object]] = [
            {
                "backend": "paper",
                "connected": bool(paper.get("connected")),
                "environment": "paper",
                "execution_enabled": True,
                "account_id": None,
                "message": "simulation only",
                "checked_at": datetime.now(UTC).isoformat(),
            }
        ]
        values.extend(status.model_dump(mode="json") for status in broker_registry.statuses())
        return values

    @app.post("/brokers/tradovate/link")
    async def link_tradovate(
        request: TradovateLinkRequest,
        x_altron_operator_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        require_operator(x_altron_operator_token)
        if (
            trading_mode.status.mode != "virtual"
            and trading_mode.status.backend == "tradovate"
        ):
            raise HTTPException(
                status_code=409,
                detail="Switch to virtual and reconcile positions before relinking Tradovate",
            )
        backend = TradovateBackend(
            environment=request.environment,
            access_token=request.access_token,
            username=request.username,
            password=request.password,
            app_id=request.app_id,
            app_version=request.app_version,
            client_id=request.client_id,
            client_secret=request.client_secret,
            device_id=request.device_id,
            account_id=request.account_id,
            account_spec=request.account_spec,
            execution_enabled=False,
        )
        status = await backend.connect()
        if status.connected:
            try:
                previous = broker_registry.get("tradovate")
            except KeyError:
                pass
            else:
                await previous.disconnect()
            broker_registry.register(backend, replace=True)
        return status.model_dump(mode="json")

    @app.post("/brokers/mt5/link")
    async def link_mt5(
        request: MT5LinkRequest,
        x_altron_operator_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        require_operator(x_altron_operator_token)
        if trading_mode.status.mode != "virtual" and trading_mode.status.backend == "mt5":
            raise HTTPException(
                status_code=409,
                detail="Switch to virtual and reconcile positions before relinking MT5",
            )
        backend = MT5Backend(
            terminal_path=request.terminal_path,
            login=request.login,
            password=request.password,
            server=request.server,
            portable=request.portable,
            execution_enabled=False,
        )
        status = await backend.connect()
        if status.connected:
            try:
                previous = broker_registry.get("mt5")
            except KeyError:
                pass
            else:
                await previous.disconnect()
            broker_registry.register(backend, replace=True)
        return status.model_dump(mode="json")

    @app.post("/brokers/{name}/connect")
    async def connect_broker(
        name: str, x_altron_operator_token: str | None = Header(default=None)
    ) -> dict[str, object]:
        require_operator(x_altron_operator_token)
        try:
            status = await broker_registry.connect(name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return status.model_dump(mode="json")

    @app.post("/brokers/{name}/disconnect")
    async def disconnect_broker(
        name: str, x_altron_operator_token: str | None = Header(default=None)
    ) -> dict[str, object]:
        require_operator(x_altron_operator_token)
        try:
            status = await broker_registry.disconnect(name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return status.model_dump(mode="json")

    @app.get("/brokers/{name}/account")
    async def broker_account(name: str) -> dict[str, object]:
        try:
            return await broker_registry.account_snapshot(name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None

    @app.get("/deployments")
    async def list_deployments() -> list[dict[str, object]]:
        return [record.model_dump(mode="json") for record in deployments.list()]

    @app.post("/deployments", status_code=201)
    async def create_deployment(
        spec: DeploymentSpec,
        x_altron_operator_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        require_operator(x_altron_operator_token)
        try:
            record = deployments.create(spec, allow_live=allow_live_deployments)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except Exception as exc:
            if "UNIQUE constraint" in str(exc):
                raise HTTPException(status_code=409, detail="Deployment name already exists") from None
            raise
        return record.model_dump(mode="json")

    @app.patch("/deployments/{deployment_id}")
    async def update_deployment(
        deployment_id: int,
        update: DeploymentStateUpdate,
        x_altron_operator_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        require_operator(x_altron_operator_token)
        try:
            record = deployments.set_enabled(
                deployment_id, update.enabled, allow_live=allow_live_deployments
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        return record.model_dump(mode="json")

    @app.delete("/deployments/{deployment_id}", status_code=204)
    async def delete_deployment(
        deployment_id: int,
        x_altron_operator_token: str | None = Header(default=None),
    ) -> None:
        require_operator(x_altron_operator_token)
        if not deployments.delete(deployment_id):
            raise HTTPException(status_code=404, detail="Deployment does not exist")

    @app.post("/webhooks/tradingview", status_code=202)
    async def tradingview(
        payload: TradingViewAlert,
        request: Request,
        x_altron_signature: str | None = Header(default=None),
    ) -> dict[str, object]:
        if webhook_secret:
            body = await request.body()
            expected = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
            supplied = (x_altron_signature or "").removeprefix("sha256=")
            if not hmac.compare_digest(expected, supplied):
                raise HTTPException(status_code=401, detail="Invalid webhook signature")
            now = datetime.now(UTC)
            if abs((now - payload.timestamp.astimezone(UTC)).total_seconds()) > webhook_max_age_seconds:
                raise HTTPException(status_code=408, detail="TradingView alert is stale")
            replay_key = hashlib.sha256(body).hexdigest()
            cutoff = now.timestamp() - webhook_max_age_seconds
            for key, seen in list(webhook_replay_cache.items()):
                if seen.timestamp() < cutoff:
                    webhook_replay_cache.pop(key, None)
            if replay_key in webhook_replay_cache:
                raise HTTPException(status_code=409, detail="TradingView alert replay rejected")
            webhook_replay_cache[replay_key] = now
        event = SignalEvent(
            timestamp=payload.timestamp,
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            strategy=payload.strategy,
            signal=_signal_number(payload.signal),
            params={},
            confidence=payload.confidence,
            entry_price=payload.price,
            source="tradingview",
        )
        python_matches = [
            candidate
            for candidate in reversed(signal_hub.recent(500))
            if candidate.source == "python"
            and candidate.symbol == event.symbol
            and candidate.timeframe == event.timeframe
            and candidate.strategy == event.strategy
        ]
        comparison = "no_python_signal"
        if python_matches:
            comparison = "match" if python_matches[0].signal == event.signal else "mismatch"
        await signal_hub.publish(event)
        return {
            "accepted": True,
            "comparison": comparison,
            "event": event.model_dump(mode="json"),
        }

    @app.websocket("/ws/signals")
    async def signal_socket(websocket: WebSocket) -> None:
        if operator_token:
            supplied = websocket.headers.get("X-Altron-Operator-Token") or websocket.query_params.get(
                "token"
            )
            if not hmac.compare_digest(operator_token, supplied or ""):
                await websocket.close(code=1008, reason="Invalid operator token")
                return
        await websocket.accept()
        queue = signal_hub.subscribe()
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        finally:
            signal_hub.unsubscribe(queue)

    return app
