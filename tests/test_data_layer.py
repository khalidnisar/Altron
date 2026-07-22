from __future__ import annotations

import pandas as pd
import pytest

from altron.data_layer.cache import MarketDataCache
from altron.data_layer.normalization import normalize_ohlcv, resample_ohlcv
from altron.data_layer.stream import ClosedCandleAggregator
from altron.exceptions import DataValidationError


def test_normalization_sorts_deduplicates_and_converts_milliseconds() -> None:
    rows = [
        [1_700_000_060_000, 10, 12, 9, 11, 5],
        [1_700_000_000_000, 9, 11, 8, 10, 4],
        [1_700_000_060_000, 10, 13, 9, 12, 6],
    ]
    frame = normalize_ohlcv(rows)
    assert list(frame.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(frame) == 2
    assert str(frame["timestamp"].dt.tz) == "UTC"
    assert frame.iloc[-1]["close"] == 12


def test_invalid_bar_fails_closed() -> None:
    with pytest.raises(DataValidationError):
        normalize_ohlcv([[1_700_000_000, 10, 9, 8, 10, 1]])


def test_resampling_uses_ohlcv_aggregations(candles: pd.DataFrame) -> None:
    result = resample_ohlcv(candles.head(8), "4h")
    assert len(result) == 2
    assert result.iloc[0]["open"] == candles.iloc[0]["open"]
    assert result.iloc[0]["volume"] == pytest.approx(candles.iloc[:4]["volume"].sum())


def test_live_aggregator_emits_only_after_bucket_closes(candles: pd.DataFrame) -> None:
    aggregator = ClosedCandleAggregator("4h")
    completed = [aggregator.update(row) for row in candles.head(5).to_dict("records")]
    assert completed[:4] == [None, None, None, None]
    assert completed[4] is not None
    assert completed[4]["volume"] == pytest.approx(candles.iloc[:4]["volume"].sum())


def test_sqlite_cache_is_idempotent(tmp_path, candles: pd.DataFrame) -> None:
    cache = MarketDataCache(tmp_path / "market.sqlite")
    assert cache.put("binance", "BTC/USDT", "1h", candles.head(20)) == 20
    updated = candles.head(20).copy()
    updated.loc[5, "close"] = updated.loc[5, "open"]
    cache.put("binance", "BTC/USDT", "1h", updated)
    result = cache.get(
        "binance",
        "BTC/USDT",
        "1h",
        start=candles["timestamp"].iloc[3],
        end=candles["timestamp"].iloc[8],
    )
    assert len(result) == 6
    assert result.iloc[2]["close"] == updated.loc[5, "close"]
