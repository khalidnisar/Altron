from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from altron.data_layer.timeframes import timeframe_to_pandas
from altron.exceptions import DataValidationError

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
PRICE_COLUMNS = ["open", "high", "low", "close"]

_COMMON_ALIASES = {
    "date": "timestamp",
    "datetime": "timestamp",
    "time": "timestamp",
    "t": "timestamp",
    "o": "open",
    "h": "high",
    "l": "low",
    "c": "close",
    "v": "volume",
    "vol": "volume",
}


def _timestamp_series(values: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(values):
        finite = pd.to_numeric(values, errors="coerce").dropna()
        magnitude = float(finite.abs().median()) if not finite.empty else 0.0
        unit = "ns" if magnitude > 1e17 else "us" if magnitude > 1e14 else "ms" if magnitude > 1e11 else "s"
        return pd.to_datetime(values, unit=unit, utc=True, errors="coerce")
    return pd.to_datetime(values, utc=True, errors="coerce")


def normalize_ohlcv(
    data: pd.DataFrame | Iterable[Iterable[Any]] | Iterable[Mapping[str, Any]],
    *,
    strict: bool = True,
) -> pd.DataFrame:
    """Return canonical, sorted UTC OHLCV data.

    The canonical contract uses a timezone-aware ``timestamp`` column and float64
    open/high/low/close/volume columns. Duplicate timestamps keep the latest row.
    Sequence input follows the CCXT order: timestamp, open, high, low, close, volume.
    """
    if isinstance(data, pd.DataFrame):
        frame = data.copy()
    else:
        records = list(data)
        if not records:
            return pd.DataFrame(columns=OHLCV_COLUMNS).astype(
                {name: "float64" for name in OHLCV_COLUMNS if name != "timestamp"}
            )
        frame = pd.DataFrame(records)
        if all(isinstance(column, int) for column in frame.columns):
            if frame.shape[1] < 6:
                raise DataValidationError("OHLCV sequence rows require at least six values")
            frame = frame.iloc[:, :6]
            frame.columns = OHLCV_COLUMNS

    frame.columns = [str(column).strip().lower() for column in frame.columns]
    frame = frame.rename(columns={key: value for key, value in _COMMON_ALIASES.items() if key in frame})
    missing = set(OHLCV_COLUMNS) - set(frame.columns)
    if missing:
        raise DataValidationError(f"Missing OHLCV columns: {sorted(missing)}")

    frame = frame[OHLCV_COLUMNS].copy()
    frame["timestamp"] = _timestamp_series(frame["timestamp"])
    for column in PRICE_COLUMNS + ["volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")

    invalid = frame[OHLCV_COLUMNS].isna().any(axis=1)
    invalid |= (frame[PRICE_COLUMNS] <= 0).any(axis=1)
    invalid |= frame["volume"] < 0
    invalid |= frame["high"] < frame[["open", "close", "low"]].max(axis=1)
    invalid |= frame["low"] > frame[["open", "close", "high"]].min(axis=1)
    if strict and invalid.any():
        examples = frame.index[invalid].tolist()[:5]
        raise DataValidationError(
            f"Found {int(invalid.sum())} invalid OHLCV row(s), example indices: {examples}"
        )
    frame = frame.loc[~invalid]
    return (
        frame.sort_values("timestamp")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )


def resample_ohlcv(data: pd.DataFrame, timeframe: str, *, drop_incomplete: bool = False) -> pd.DataFrame:
    """Aggregate canonical candles without inventing volume or prices."""
    frame = normalize_ohlcv(data)
    if frame.empty:
        return frame
    rule = timeframe_to_pandas(timeframe)
    indexed = frame.set_index("timestamp")
    result = indexed.resample(rule, label="left", closed="left", origin="epoch").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    result = result.dropna(subset=PRICE_COLUMNS)
    if drop_incomplete and not result.empty:
        source_delta = frame["timestamp"].diff().dropna().median()
        if pd.notna(source_delta) and source_delta > pd.Timedelta(0):
            expected = max(1, int(pd.Timedelta(rule) / source_delta))
            counts = indexed["close"].resample(rule, origin="epoch").count()
            result = result.loc[counts >= expected]
    return normalize_ohlcv(result.reset_index())


def assert_regular(data: pd.DataFrame, timeframe: str) -> None:
    """Raise when timestamps contain gaps; useful before strict research runs."""
    frame = normalize_ohlcv(data)
    if len(frame) < 2:
        return
    expected = pd.Timedelta(timeframe_to_pandas(timeframe))
    gaps = frame["timestamp"].diff().dropna()
    if not bool((gaps == expected).all()):
        values = sorted({str(value) for value in gaps[gaps != expected].head(5)})
        raise DataValidationError(f"Irregular {timeframe} candles; unexpected deltas: {values}")
