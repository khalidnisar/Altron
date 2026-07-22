from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from altron.data_layer.normalization import normalize_ohlcv


def import_external_signals(
    candles: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    timestamp_column: str = "timestamp",
    signal_column: str = "signal",
) -> pd.Series:
    """Align exported Pine/TradingView target signals to canonical candles.

    Accepted signal values are -1/0/+1 or buy/long, sell/short, flat/close.
    ``hold`` and blank values preserve the prior target. Sparse event exports are
    forward-filled only after an exact candle timestamp match; off-grid timestamps
    fail instead of being silently rounded.
    """
    frame = normalize_ohlcv(candles)
    external = signals.copy()
    external.columns = [str(column).strip().lower() for column in external.columns]
    timestamp_column = timestamp_column.lower()
    signal_column = signal_column.lower()
    if timestamp_column not in external or signal_column not in external:
        raise ValueError(
            f"External signals require {timestamp_column!r} and {signal_column!r} columns"
        )
    external[timestamp_column] = pd.to_datetime(
        external[timestamp_column], utc=True, errors="coerce"
    )
    if external[timestamp_column].isna().any():
        raise ValueError("External signals contain invalid timestamps")
    duplicates = external[timestamp_column].duplicated(keep=False)
    if duplicates.any():
        raise ValueError("External signals contain duplicate timestamps")
    aliases: Mapping[Any, float] = {
        "buy": 1.0,
        "long": 1.0,
        "sell": -1.0,
        "short": -1.0,
        "flat": 0.0,
        "close": 0.0,
        "exit": 0.0,
        "hold": np.nan,
        "": np.nan,
    }

    def convert(value: Any) -> float:
        if pd.isna(value):
            return np.nan
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in aliases:
                return aliases[normalized]
            value = normalized
        number = float(value)
        if number not in {-1.0, 0.0, 1.0}:
            raise ValueError(f"External signal value must be -1/0/+1, got {value!r}")
        return number

    external[signal_column] = external[signal_column].map(convert)
    candle_times = pd.Index(frame["timestamp"])
    off_grid = ~external[timestamp_column].isin(candle_times)
    if off_grid.any():
        examples = external.loc[off_grid, timestamp_column].astype(str).head(3).tolist()
        raise ValueError(f"Signal timestamps do not match candle closes/labels: {examples}")
    aligned = external.set_index(timestamp_column)[signal_column].reindex(candle_times)
    result = aligned.ffill().fillna(0).astype("int8")
    result.index = frame.index
    result.name = "signal"
    return result
