from __future__ import annotations

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from altron.api.app import create_app
from altron.live_trading.deployments import DeploymentStore


def test_health_and_signed_tradingview_webhook(tmp_path) -> None:
    secret = "test-secret"
    client = TestClient(
        create_app(
            webhook_secret=secret,
            deployment_store=DeploymentStore(tmp_path / "deployments.sqlite"),
        )
    )
    assert client.get("/health").json()["execution_mode"] == "virtual"
    payload = {
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "strategy": "supertrend",
        "signal": "buy",
        "price": 100,
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    assert client.post(
        "/webhooks/tradingview", content=body, headers={"Content-Type": "application/json"}
    ).status_code == 401
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    response = client.post(
        "/webhooks/tradingview",
        content=body,
        headers={"Content-Type": "application/json", "X-Altron-Signature": f"sha256={signature}"},
    )
    assert response.status_code == 202
    assert response.json()["comparison"] == "no_python_signal"
    assert (
        client.post(
            "/webhooks/tradingview",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Altron-Signature": f"sha256={signature}",
            },
        ).status_code
        == 409
    )
    assert client.get("/signals").json()[0]["source"] == "tradingview"
    assert client.get("/portfolio").json()["execution_mode"] == "virtual"
    assert client.get("/brokers").json()[0]["backend"] == "paper"
    assert client.get("/runtime/mode").json()["mode"] == "virtual"
    assert "crypto" in client.get("/market/catalog").json()["markets"]


def test_operator_token_protects_runtime_mutations(tmp_path) -> None:
    client = TestClient(
        create_app(
            deployment_store=DeploymentStore(tmp_path / "secure.sqlite"),
            operator_token="operator-secret",
        )
    )
    assert client.patch("/runtime/mode", json={"mode": "virtual"}).status_code == 401
    assert client.get("/portfolio").status_code == 401
    assert (
        client.patch(
            "/runtime/mode",
            json={"mode": "virtual"},
            headers={"X-Altron-Operator-Token": "operator-secret"},
        ).status_code
        == 200
    )


def test_deployment_api_is_paper_safe(tmp_path) -> None:
    client = TestClient(
        create_app(deployment_store=DeploymentStore(tmp_path / "deployments.sqlite"))
    )
    response = client.post(
        "/deployments",
        json={
            "name": "rsi-paper",
            "strategy": "rsi_mean_reversion",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "enabled": True,
        },
    )
    assert response.status_code == 201
    deployment_id = response.json()["id"]
    assert client.get("/deployments").json()[0]["enabled"] is True
    assert client.patch(f"/deployments/{deployment_id}", json={"enabled": False}).status_code == 200
    assert client.delete(f"/deployments/{deployment_id}").status_code == 204
