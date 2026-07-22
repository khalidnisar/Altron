from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from altron.data_layer.normalization import normalize_ohlcv, resample_ohlcv
from altron.strategies.base import Strategy
from altron.strategies.indicators import (
    atr,
    bollinger_bands,
    donchian,
    macd,
    moving_average,
    rsi,
    session_vwap,
    supertrend,
)


class IndicatorDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    indicator: Literal[
        "sma", "ema", "rsi", "macd", "macd_signal", "macd_histogram",
        "bollinger_lower", "bollinger_middle", "bollinger_upper",
        "donchian_lower", "donchian_middle", "donchian_upper", "atr",
        "supertrend", "supertrend_direction", "vwap",
    ]
    source: Literal["open", "high", "low", "close", "volume"] = "close"
    period: int | None = Field(default=None, ge=1)
    timeframe: str | None = None
    params: dict[str, float | int | str] = Field(default_factory=dict)


class RuleStrategyDefinition(BaseModel):
    """Validated representation of a no-code strategy rule tree."""

    model_config = ConfigDict(extra="forbid")

    name: str = "rule_strategy"
    indicators: list[IndicatorDefinition]
    long_entry: dict[str, Any]
    long_exit: dict[str, Any]
    short_entry: dict[str, Any] | None = None
    short_exit: dict[str, Any] | None = None

    @model_validator(mode="after")
    def names_are_unique(self) -> RuleStrategyDefinition:
        names = [item.name for item in self.indicators]
        if len(names) != len(set(names)):
            raise ValueError("indicator names must be unique")
        return self


def _indicator(frame: pd.DataFrame, definition: IndicatorDefinition) -> pd.Series:
    params = dict(definition.params)
    period = definition.period or int(params.pop("period", 14))
    source = frame[definition.source]
    indicator = definition.indicator
    if indicator in {"sma", "ema"}:
        return moving_average(source, period, indicator)
    if indicator == "rsi":
        return rsi(source, period)
    if indicator.startswith("macd"):
        line, signal_line, histogram = macd(
            source,
            int(params.get("fast", 12)),
            int(params.get("slow", 26)),
            int(params.get("signal", 9)),
        )
        return {"macd": line, "macd_signal": signal_line, "macd_histogram": histogram}[indicator]
    if indicator.startswith("bollinger"):
        lower, middle, upper = bollinger_bands(source, period, float(params.get("stddev", 2)))
        return {"bollinger_lower": lower, "bollinger_middle": middle, "bollinger_upper": upper}[indicator]
    if indicator.startswith("donchian"):
        lower, middle, upper = donchian(frame, period)
        return {"donchian_lower": lower, "donchian_middle": middle, "donchian_upper": upper}[indicator]
    if indicator == "atr":
        return atr(frame, period)
    if indicator.startswith("supertrend"):
        line, direction = supertrend(frame, period, float(params.get("multiplier", 3)))
        return line if indicator == "supertrend" else direction
    if indicator == "vwap":
        return session_vwap(frame)
    raise ValueError(f"Unsupported indicator: {indicator}")


def _operand(value: Any, context: dict[str, pd.Series], index: pd.Index) -> pd.Series:
    if isinstance(value, (int, float)):
        return pd.Series(float(value), index=index)
    if isinstance(value, str) and value in context:
        return context[value]
    raise ValueError(f"Unknown rule operand: {value!r}")


def evaluate_condition(rule: dict[str, Any], context: dict[str, pd.Series], index: pd.Index) -> pd.Series:
    """Evaluate a validated rule tree without eval/exec."""
    if set(rule) == {"all"}:
        children = rule["all"]
        if not isinstance(children, list) or not children:
            raise ValueError("'all' requires a non-empty list")
        return pd.concat([evaluate_condition(child, context, index) for child in children], axis=1).all(axis=1)
    if set(rule) == {"any"}:
        children = rule["any"]
        if not isinstance(children, list) or not children:
            raise ValueError("'any' requires a non-empty list")
        return pd.concat([evaluate_condition(child, context, index) for child in children], axis=1).any(axis=1)
    if set(rule) == {"not"}:
        return ~evaluate_condition(rule["not"], context, index)
    if not {"left", "operator", "right"}.issubset(rule):
        raise ValueError("A condition needs left, operator, and right")
    left = _operand(rule["left"], context, index)
    right = _operand(rule["right"], context, index)
    operator = rule["operator"]
    operations = {
        ">": lambda: left > right,
        ">=": lambda: left >= right,
        "<": lambda: left < right,
        "<=": lambda: left <= right,
        "==": lambda: left == right,
        "crosses_above": lambda: (left > right) & (left.shift(1) <= right.shift(1)),
        "crosses_below": lambda: (left < right) & (left.shift(1) >= right.shift(1)),
    }
    if operator not in operations:
        raise ValueError(f"Unsupported operator {operator!r}")
    return operations[operator]().fillna(False)


class RuleStrategy(Strategy):
    name = "rule_strategy"

    def __init__(self, definition: RuleStrategyDefinition | dict[str, Any]) -> None:
        self.definition = (
            definition
            if isinstance(definition, RuleStrategyDefinition)
            else RuleStrategyDefinition.model_validate(definition)
        )
        self.name = self.definition.name

    def _context(self, frame: pd.DataFrame) -> dict[str, pd.Series]:
        context = {column: frame[column] for column in ["open", "high", "low", "close", "volume"]}
        for definition in self.definition.indicators:
            if definition.timeframe:
                higher = resample_ohlcv(frame, definition.timeframe)
                values = _indicator(higher, definition).shift(1)
                available = pd.DataFrame({"timestamp": higher["timestamp"], "value": values})
                aligned = pd.merge_asof(
                    frame[["timestamp"]].sort_values("timestamp"),
                    available.dropna().sort_values("timestamp"),
                    on="timestamp",
                    direction="backward",
                )["value"]
                aligned.index = frame.index
                context[definition.name] = aligned
            else:
                context[definition.name] = _indicator(frame, definition)
        return context

    def generate_signals(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        frame = normalize_ohlcv(df)
        context = self._context(frame)
        index = frame.index
        long_entry = evaluate_condition(self.definition.long_entry, context, index)
        long_exit = evaluate_condition(self.definition.long_exit, context, index)
        short_entry = (
            evaluate_condition(self.definition.short_entry, context, index)
            if self.definition.short_entry else pd.Series(False, index=index)
        )
        short_exit = (
            evaluate_condition(self.definition.short_exit, context, index)
            if self.definition.short_exit else pd.Series(False, index=index)
        )
        state = 0
        signals = np.zeros(len(frame), dtype=np.int8)
        for position in range(len(frame)):
            if state == 1 and long_exit.iloc[position]:
                state = 0
            elif state == -1 and short_exit.iloc[position]:
                state = 0
            if long_entry.iloc[position]:
                state = 1
            elif short_entry.iloc[position]:
                state = -1
            signals[position] = state
        return pd.Series(signals, index=index, name="signal")


def strategy_from_definition(definition: dict[str, Any]) -> RuleStrategy:
    """Build a rule strategy, including the compact RSI shorthand from the docs."""
    if "indicators" not in definition and definition.get("indicator") == "rsi":
        period = int(definition.get("period", 14))
        overbought = float(definition.get("overbought", 70))
        oversold = float(definition.get("oversold", 30))
        definition = {
            "name": definition.get("name", "rsi_rule"),
            "indicators": [{"name": "rsi", "indicator": "rsi", "period": period}],
            "long_entry": {"left": "rsi", "operator": "<", "right": oversold},
            "long_exit": {"left": "rsi", "operator": ">=", "right": 50},
            "short_entry": {"left": "rsi", "operator": ">", "right": overbought},
            "short_exit": {"left": "rsi", "operator": "<=", "right": 50},
        }
    return RuleStrategy(definition)
