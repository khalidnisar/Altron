from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from altron.strategies.base import Strategy
from altron.strategies.indicators import (
    atr,
    bollinger_bands,
    donchian,
    ichimoku,
    macd,
    moving_average,
    rsi,
    session_vwap,
    supertrend,
)
from altron.strategies.registry import register_strategy


def _positions_from_events(
    long_entry: pd.Series,
    long_exit: pd.Series,
    short_entry: pd.Series | None = None,
    short_exit: pd.Series | None = None,
) -> pd.Series:
    state = 0
    output = np.zeros(len(long_entry), dtype=np.int8)
    short_entry = short_entry if short_entry is not None else pd.Series(False, index=long_entry.index)
    short_exit = short_exit if short_exit is not None else pd.Series(False, index=long_entry.index)
    for position in range(len(output)):
        if state == 1 and bool(long_exit.iloc[position]):
            state = 0
        elif state == -1 and bool(short_exit.iloc[position]):
            state = 0
        if bool(long_entry.iloc[position]):
            state = 1
        elif bool(short_entry.iloc[position]):
            state = -1
        output[position] = state
    return pd.Series(output, index=long_entry.index, name="signal")


@register_strategy
class MovingAverageCrossover(Strategy):
    name = "ma_crossover"
    parameter_space = {
        "fast_period": (5, 50), "slow_period": (20, 250), "ma_type": ["sma", "ema"]
    }

    def generate_signals(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        fast_period = int(params.get("fast_period", 20))
        slow_period = int(params.get("slow_period", 50))
        if fast_period >= slow_period:
            raise ValueError("fast_period must be less than slow_period")
        kind = str(params.get("ma_type", "sma"))
        fast = moving_average(df["close"], fast_period, kind)
        slow = moving_average(df["close"], slow_period, kind)
        return pd.Series(np.where(fast > slow, 1, -1), index=df.index).mask(slow.isna(), 0)


@register_strategy
class RSIMeanReversion(Strategy):
    name = "rsi_mean_reversion"
    parameter_space = {"period": (5, 30), "oversold": (15, 40), "overbought": (60, 85)}

    def generate_signals(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        value = rsi(df["close"], int(params.get("period", 14)))
        oversold = float(params.get("oversold", 30))
        overbought = float(params.get("overbought", 70))
        if oversold >= overbought:
            raise ValueError("oversold must be lower than overbought")
        return _positions_from_events(
            value < oversold,
            value >= 50,
            value > overbought,
            value <= 50,
        ).mask(value.isna(), 0)


@register_strategy
class MACDMomentum(Strategy):
    name = "macd_momentum"
    parameter_space = {"fast": (6, 18), "slow": (19, 40), "signal": (4, 15)}

    def generate_signals(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        line, signal_line, _ = macd(
            df["close"],
            int(params.get("fast", 12)),
            int(params.get("slow", 26)),
            int(params.get("signal", 9)),
        )
        return pd.Series(np.where(line > signal_line, 1, -1), index=df.index).mask(signal_line.isna(), 0)


@register_strategy
class BollingerBands(Strategy):
    name = "bollinger_bands"
    parameter_space = {"period": (10, 50), "stddev": (1.0, 3.5), "mode": ["reversion", "breakout"]}

    def generate_signals(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        lower, middle, upper = bollinger_bands(
            df["close"], int(params.get("period", 20)), float(params.get("stddev", 2.0))
        )
        mode = params.get("mode", "reversion")
        if mode == "reversion":
            result = _positions_from_events(
                df["close"] < lower, df["close"] >= middle,
                df["close"] > upper, df["close"] <= middle,
            )
        elif mode == "breakout":
            result = _positions_from_events(
                df["close"] > upper, df["close"] < middle,
                df["close"] < lower, df["close"] > middle,
            )
        else:
            raise ValueError("mode must be 'reversion' or 'breakout'")
        return result.mask(middle.isna(), 0)


@register_strategy
class DonchianBreakout(Strategy):
    name = "donchian_breakout"
    parameter_space = {"period": (10, 100), "exit_period": (3, 50)}

    def generate_signals(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        period = int(params.get("period", 20))
        exit_period = int(params.get("exit_period", 10))
        lower, _, upper = donchian(df, period)
        exit_lower, exit_middle, exit_upper = donchian(df, exit_period)
        result = _positions_from_events(
            df["close"] > upper,
            df["close"] < exit_middle,
            df["close"] < lower,
            df["close"] > exit_middle,
        )
        return result.mask(upper.isna() | exit_upper.isna() | exit_lower.isna(), 0)


@register_strategy
class SupertrendStrategy(Strategy):
    name = "supertrend"
    parameter_space = {"period": (5, 30), "multiplier": (1.0, 6.0)}

    def generate_signals(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        line, trend = supertrend(
            df, int(params.get("period", 10)), float(params.get("multiplier", 3.0))
        )
        return trend.astype("int8").mask(line.isna(), 0)


@register_strategy
class IchimokuStrategy(Strategy):
    name = "ichimoku"
    parameter_space = {"conversion_period": (5, 15), "base_period": (16, 40), "span_b_period": (41, 80)}

    def generate_signals(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        conversion, base, span_a, span_b = ichimoku(
            df,
            int(params.get("conversion_period", 9)),
            int(params.get("base_period", 26)),
            int(params.get("span_b_period", 52)),
            int(params.get("displacement", 26)),
        )
        cloud_top = pd.concat([span_a, span_b], axis=1).max(axis=1)
        cloud_bottom = pd.concat([span_a, span_b], axis=1).min(axis=1)
        long = (df["close"] > cloud_top) & (conversion > base)
        short = (df["close"] < cloud_bottom) & (conversion < base)
        return pd.Series(np.select([long, short], [1, -1], default=0), index=df.index).mask(span_b.isna(), 0)


@register_strategy
class VWAPReversal(Strategy):
    name = "vwap_reversal"
    parameter_space = {"deviation": (0.002, 0.05), "atr_period": (5, 30), "atr_filter": (0.0, 3.0)}

    def generate_signals(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        vwap = session_vwap(df)
        deviation = float(params.get("deviation", 0.01))
        average_range = atr(df, int(params.get("atr_period", 14)))
        atr_filter = float(params.get("atr_filter", 0.0))
        distance = (df["close"] - vwap) / vwap
        eligible = distance.abs() >= atr_filter * average_range / df["close"]
        new_session = pd.to_datetime(df["timestamp"], utc=True).dt.date.ne(
            pd.to_datetime(df["timestamp"], utc=True).dt.date.shift(1)
        )
        result = _positions_from_events(
            (distance < -deviation) & eligible & ~new_session,
            (df["close"] >= vwap) | new_session,
            (distance > deviation) & eligible & ~new_session,
            (df["close"] <= vwap) | new_session,
        )
        return result.mask(vwap.isna() | new_session, 0)
