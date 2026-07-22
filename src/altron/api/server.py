from __future__ import annotations

import os

from altron.api.app import create_app
from altron.brokers.registry import registry_from_environment
from altron.live_trading.deployments import DeploymentStore

# Read-only connectivity adapters are configured from environment variables but
# never connected automatically. Standalone API mode has no order endpoint.
app = create_app(
    webhook_secret=os.getenv("TRADINGVIEW_WEBHOOK_SECRET"),
    brokers=registry_from_environment(execution_enabled=False),
    deployment_store=DeploymentStore(os.getenv("ALTRON_DEPLOYMENTS", "data/deployments.sqlite")),
    operator_token=os.getenv("ALTRON_OPERATOR_TOKEN"),
)
