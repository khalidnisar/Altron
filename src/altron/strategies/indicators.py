from __future__ import annotations

import numpy as np
import pandas as pd


def moving_average(series: pd.Series, period: int, kind: str = "sma") -> pd.Series:
    if period < 1:
        raise ValueError("period must be positive")
    kind = kind.lower()
    if kind == "sma":
        return series.rolling(period, min_periods=period).mean()
    if kind == "ema":
        return series.ewm(span=period, adjust=False, min_periods=period).mean()
    raise ValueError("moving average kind must be 'sma' or 'ema'")


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = gain / loss.replace(0, np.nan)
    result = 100 - (100 / (1 + relative_strength))
    result = result.mask((loss == 0) & (gain > 0), 100.0)
    return result.mask((loss == 0) & (gain == 0), 50.0)


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    if fast >= slow:
        raise ValueError("MACD fast period must be shorter than slow period")
    line = moving_average(series, fast, "ema") - moving_average(series, slow, "ema")
    signal_line = moving_average(line, signal, "ema")
    return line, signal_line, line - signal_line


def bollinger_bands(
    series: pd.Series, period: int = 20, stddev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    middle = series.rolling(period, min_periods=period).mean()
    deviation = series.rolling(period, min_periods=period).std(ddof=0)
    return middle - stddev * deviation, middle, middle + stddev * deviation


def true_range(frame: pd.DataFrame) -> pd.Series:
    previous_close = frame["close"].shift(1)
    return pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(frame).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def donchian(
    frame: pd.DataFrame, period: int = 20, *, exclude_current: bool = True
) -> tuple[pd.Series, pd.Series, pd.Series]:
    high = frame["high"].shift(1) if exclude_current else frame["high"]
    low = frame["low"].shift(1) if exclude_current else frame["low"]
    upper = high.rolling(period, min_periods=period).max()
    lower = low.rolling(period, min_periods=period).min()
    return lower, (upper + lower) / 2, upper


def supertrend(
    frame: pd.DataFrame, period: int = 10, multiplier: float = 3.0
) -> tuple[pd.Series, pd.Series]:
    average_range = atr(frame, period)
    midpoint = (frame["high"] + frame["low"]) / 2
    basic_upper = midpoint + multiplier * average_range
    basic_lower = midpoint - multiplier * average_range
    final_upper = pd.Series(np.nan, index=frame.index)
    final_lower = pd.Series(np.nan, index=frame.index)
    trend = pd.Series(1.0, index=frame.index)
    line = pd.Series(np.nan, index=frame.index)
    valid = np.flatnonzero(average_range.notna().to_numpy())
    if not len(valid):
        return line, trend
    first = int(valid[0])
    final_upper.iloc[first] = basic_upper.iloc[first]
    final_lower.iloc[first] = basic_lower.iloc[first]
    line.iloc[first] = final_lower.iloc[first]

    for position in range(first + 1, len(frame)):
        previous = position - 1
        final_upper.iloc[position] = (
            basic_upper.iloc[position]
            if basic_upper.iloc[position] < final_upper.iloc[previous]
            or frame["close"].iloc[previous] > final_upper.iloc[previous]
            else final_upper.iloc[previous]
        )
        final_lower.iloc[position] = (
            basic_lower.iloc[position]
            if basic_lower.iloc[position] > final_lower.iloc[previous]
            or frame["close"].iloc[previous] < final_lower.iloc[previous]
            else final_lower.iloc[previous]
        )
        if trend.iloc[previous] < 0 and frame["close"].iloc[position] > final_upper.iloc[position]:
            trend.iloc[position] = 1
        elif trend.iloc[previous] > 0 and frame["close"].iloc[position] < final_lower.iloc[position]:
            trend.iloc[position] = -1
        else:
            trend.iloc[position] = trend.iloc[previous]
        line.iloc[position] = final_lower.iloc[position] if trend.iloc[position] > 0 else final_upper.iloc[position]
    return line, trend


def ichimoku(
    frame: pd.DataFrame,
    conversion_period: int = 9,
    base_period: int = 26,
    span_b_period: int = 52,
    displacement: int = 26,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    conversion = (
        frame["high"].rolling(conversion_period).max()
        + frame["low"].rolling(conversion_period).min()
    ) / 2
    base = (
        frame["high"].rolling(base_period).max() + frame["low"].rolling(base_period).min()
    ) / 2
    span_a = ((conversion + base) / 2).shift(displacement)
    span_b = (
        (
            frame["high"].rolling(span_b_period).max()
            + frame["low"].rolling(span_b_period).min()
        )
        / 2
    ).shift(displacement)
    return conversion, base, span_a, span_b


def session_vwap(frame: pd.DataFrame) -> pd.Series:
    if "timestamp" not in frame:
        raise ValueError("VWAP requires a timestamp column")
    timestamp = pd.to_datetime(frame["timestamp"], utc=True)
    session = timestamp.dt.floor("D")
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3
    cumulative_value = (typical * frame["volume"]).groupby(session).cumsum()
    cumulative_volume = frame["volume"].groupby(session).cumsum()
    return cumulative_value / cumulative_volume.replace(0, np.nan)
