from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from altron.data_layer.free_streams import (
    FreeStreamManager,
    FreeStreamRequest,
)
from altron.live_trading.telemetry import RuntimeTelemetry


class OneBarStream:
    async def stream_ohlcv(self, symbol: str, timeframe: str):
        yield pd.Series(
            {
                "timestamp": pd.Timestamp("2026-01-01T00:00:00Z"),
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 10,
            }
        )
        await asyncio.sleep(60)


@pytest.mark.asyncio
async def test_free_stream_catalog_and_subscription_telemetry() -> None:
    telemetry = RuntimeTelemetry()
    manager = FreeStreamManager(
        telemetry,
        factories={"yahoo": lambda request: (OneBarStream(), request.timeframe, None)},
    )
    assert any(item["symbol"] == "AAPL" for item in manager.catalog()["markets"]["stocks"])
    status = manager.subscribe(
        FreeStreamRequest(
            asset_class="stocks", symbol="AAPL", timeframe="1m", provider="yahoo"
        )
    )
    await asyncio.sleep(.01)
    assert manager.statuses()[0].bars_received == 1
    assert len(telemetry.candles("AAPL", "1m")) == 1
    with pytest.raises(ValueError, match="already exists"):
        manager.subscribe(
            FreeStreamRequest(
                asset_class="stocks", symbol="AAPL", timeframe="1m", provider="yahoo"
            )
        )
    stopped = await manager.stop(status.id)
    assert stopped.state == "stopped"
