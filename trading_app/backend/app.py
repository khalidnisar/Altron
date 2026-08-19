"""FastAPI surface: REST + WebSocket state feed + static dashboard."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import os

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import AppConfig, load_config
from .engine import TradingApplication
from .external import PayloadError, build_external_signal, verify_secret
from .models import AlertLevel

log = logging.getLogger("trading_app")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class ControlRequest(BaseModel):
    action: str            # pause | resume | emergency_stop | reset_emergency
    reason: str | None = None


def create_app(cfg: AppConfig | None = None) -> FastAPI:
    cfg = cfg or load_config()
    core = TradingApplication(cfg)
    clients: set[WebSocket] = set()

    async def broadcast() -> None:
        if not clients:
            return
        payload = json.dumps(core.snapshot(), default=str)
        dead = []
        for ws in list(clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.discard(ws)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(core.run_forever(on_update=broadcast))
        log.info("TradingApplication started (broker=%s, port=%s)", core.broker_mode, cfg.port)
        yield
        task.cancel()

    app = FastAPI(title="ALTRON AutoTrade", version="0.1.0",
                  docs_url="/api/docs", openapi_url="/api/openapi.json",
                  lifespan=lifespan)

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "broker": core.broker_mode, "tick": core.tick_id}

    @app.get("/api/state")
    async def state() -> JSONResponse:
        return JSONResponse(core.snapshot(), media_type="application/json")

    @app.get("/api/config")
    async def get_config() -> dict:
        return cfg.public_dict()

    @app.get("/api/trades")
    async def trades() -> dict:
        return {"deals": core.exec.snapshot()["deals"]}

    @app.get("/api/alerts")
    async def alerts() -> dict:
        return {"alerts": core.alerts.snapshot()}

    @app.post("/api/signals/external")
    async def external_signal(request: Request) -> JSONResponse:
        """External signal bridge (MT5 EA / TradingView alerts / other bots).
        Payload: {symbol, direction(BUY|LONG|BULLISH|...), confidence?,
                  confluence?, source?}. Converted to a Signal with ATR hard
        stops and routed through risk_gate → execution (never blind).
        When TRADING_WEBHOOK_SECRET / webhook.external_secret is configured,
        payloads must carry `secret` or the X-Webhook-Secret header matching
        the secret (or its SHA-256 digest) — Sword webhook-receiver pattern."""
        payload = await request.json()
        configured = os.environ.get("TRADING_WEBHOOK_SECRET") or \
            str(cfg.get("webhook", "external_secret", default="") or "")
        if configured:
            provided = request.headers.get("x-webhook-secret") or payload.get("secret")
            if not verify_secret(provided, configured):
                return JSONResponse({"ok": False, "error": "invalid webhook secret"},
                                    status_code=403)
        try:
            symbol_guess = str(payload.get("symbol", "")).upper().replace("/", "")
            candles = list(core.candles.get(symbol_guess, []))
            sig = build_external_signal(payload, cfg, candles, ts=core._sim_ts())
        except PayloadError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=422)
        spread = core.broker.tick(sig.symbol).spread
        allow = core.trading_enabled and not core.risk.trading_blocked
        result = core.graph.execute_external(sig, candles, spread, core._sim_ts(), allow)
        core.alerts.fire(core._sim_ts(), AlertLevel.INFO, f"EXT_{sig.symbol}",
                         f"External {sig.side.value} {sig.symbol} → {result['outcome']}",
                         symbol=sig.symbol, force=True)
        return {"ok": result["outcome"] == "EXECUTED", **result}

    # ------------------------------------------------------------ trade copier
    @app.get("/api/copier")
    async def copier_state() -> dict:
        return core.copier.snapshot()

    @app.post("/api/copier/accounts")
    async def copier_add(payload: dict) -> JSONResponse:
        try:
            cfg_ = core.copier.add_account(payload)
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=422)
        return JSONResponse({"ok": True, "account": cfg_.to_dict()})

    @app.patch("/api/copier/accounts/{acct_id}")
    async def copier_update(acct_id: str, payload: dict) -> JSONResponse:
        if acct_id not in core.copier.followers:
            return JSONResponse({"ok": False, "error": "unknown account"}, status_code=404)
        try:
            cfg_ = core.copier.update_account(acct_id, payload)
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=422)
        return JSONResponse({"ok": True, "account": cfg_.to_dict()})

    @app.delete("/api/copier/accounts/{acct_id}")
    async def copier_remove(acct_id: str) -> JSONResponse:
        if acct_id not in core.copier.followers:
            return JSONResponse({"ok": False, "error": "unknown account"}, status_code=404)
        closed = core.copier.remove_account(acct_id)
        return JSONResponse({"ok": True, "closed_positions": closed})

    @app.post("/api/copier/accounts/{acct_id}/connect")
    async def copier_connect(acct_id: str) -> JSONResponse:
        if acct_id not in core.copier.followers:
            return JSONResponse({"ok": False, "error": "unknown account"}, status_code=404)
        core.copier.connect(acct_id)
        rt = core.copier.followers[acct_id]
        return JSONResponse({"ok": rt.connected, "error": rt.error})

    @app.post("/api/copier/accounts/{acct_id}/disconnect")
    async def copier_disconnect(acct_id: str) -> JSONResponse:
        if acct_id not in core.copier.followers:
            return JSONResponse({"ok": False, "error": "unknown account"}, status_code=404)
        core.copier.disconnect(acct_id)
        return JSONResponse({"ok": True})

    @app.post("/api/control")
    async def control(req: ControlRequest) -> dict:
        action = req.action.lower()
        if action == "pause":
            core.pause_trading()
            core.alerts.fire(core._sim_ts(), AlertLevel.INFO,
                             "OPERATOR_PAUSE", "Trading paused by operator", force=True)
        elif action == "resume":
            core.resume_trading()
            core.alerts.fire(core._sim_ts(), AlertLevel.INFO,
                             "OPERATOR_RESUME", "Trading resumed by operator", force=True)
        elif action == "emergency_stop":
            core.emergency_stop(req.reason or "operator kill-switch")
        elif action == "close_all":
            n = core.exec.close_all("MANUAL")
            return {"ok": True, "closed": n}
        else:
            return {"ok": False, "error": f"unknown action '{req.action}'"}
        return {"ok": True, "action": action, "trading_enabled": core.trading_enabled,
                "emergency": core.risk.emergency}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        clients.add(websocket)
        try:
            await websocket.send_text(json.dumps(core.snapshot(), default=str))
            while True:
                await websocket.receive_text()   # keep-alive / client pings
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            clients.discard(websocket)

    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
    return app


app = create_app()
