from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

import pandas as pd


@dataclass(slots=True)
class BacktestConfig:
    initial_capital: float = 100_000.0
    commission_bps: float = 5.0
    slippage_bps: float = 2.0
    position_sizing: Literal["fixed_fractional", "kelly"] = "fixed_fractional"
    position_fraction: float = 1.0
    kelly_lookback: int = 100
    max_kelly_fraction: float = 0.25
    max_leverage: float = 1.0
    allow_short: bool = True
    execute_next_bar: bool = True
    execution_delay_bars: int = 1
    max_drawdown_stop: float | None = None
    annualization_periods: float | None = None
    risk_free_rate: float = 0.0

    def __post_init__(self) -> None:
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if not 0 < self.position_fraction <= self.max_leverage:
            raise ValueError("position_fraction must be positive and no larger than max_leverage")
        if self.commission_bps < 0 or self.slippage_bps < 0:
            raise ValueError("trading costs cannot be negative")
        if self.execution_delay_bars < 0:
            raise ValueError("execution_delay_bars cannot be negative")
        if self.max_drawdown_stop is not None and not 0 < self.max_drawdown_stop < 1:
            raise ValueError("max_drawdown_stop must be between zero and one")


@dataclass(slots=True)
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: int
    entry_price: float
    exit_price: float
    return_pct: float
    pnl: float
    bars: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class BacktestResult:
    equity: pd.Series
    returns: pd.Series
    positions: pd.Series
    trades: list[Trade]
    metrics: dict[str, float]
    signals: pd.Series
    config: BacktestConfig
    metadata: dict[str, object] = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        return {**self.metadata, **self.metrics, "trades": len(self.trades)}
