from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd


@dataclass(slots=True)
class StrategySleeve:
    name: str
    returns: pd.Series
    enabled: bool = True
    max_weight: float = 1.0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class PortfolioRiskConfig:
    max_pairwise_correlation: float = 0.70
    lookback: int = 100
    minimum_rolling_sharpe: float = -0.50
    max_strategy_drawdown: float = 0.15
    max_portfolio_drawdown: float = 0.20
    annualization_periods: float = 252.0


class PortfolioManager:
    """Select, allocate, and rotate independent strategy return sleeves."""

    def __init__(self, risk: PortfolioRiskConfig | None = None) -> None:
        self.risk = risk or PortfolioRiskConfig()
        self.portfolio_halted = False

    @staticmethod
    def returns_frame(sleeves: list[StrategySleeve]) -> pd.DataFrame:
        active = [sleeve.returns.rename(sleeve.name) for sleeve in sleeves if sleeve.enabled]
        if not active:
            return pd.DataFrame()
        frame = pd.concat(active, axis=1, join="inner").replace([np.inf, -np.inf], np.nan)
        return frame.dropna(how="all").fillna(0.0)

    def correlation_matrix(self, sleeves: list[StrategySleeve]) -> pd.DataFrame:
        return self.returns_frame(sleeves).corr()

    def select_decorrelated(self, sleeves: list[StrategySleeve]) -> list[StrategySleeve]:
        frame = self.returns_frame(sleeves)
        if frame.empty:
            return []
        quality = frame.mean() / frame.std(ddof=1).replace(0, np.nan)
        ranked = quality.fillna(-np.inf).sort_values(ascending=False).index
        selected: list[str] = []
        correlations = frame.corr().abs()
        for candidate in ranked:
            if all(
                pd.isna(correlations.loc[candidate, chosen])
                or correlations.loc[candidate, chosen] < self.risk.max_pairwise_correlation
                for chosen in selected
            ):
                selected.append(candidate)
        by_name = {sleeve.name: sleeve for sleeve in sleeves}
        return [by_name[name] for name in selected]

    def rotate(self, sleeves: list[StrategySleeve]) -> dict[str, str]:
        """Disable a sleeve only from trailing observations, never future returns."""
        changes: dict[str, str] = {}
        annual = np.sqrt(self.risk.annualization_periods)
        for sleeve in sleeves:
            sample = sleeve.returns.dropna().tail(self.risk.lookback)
            if len(sample) < self.risk.lookback:
                continue
            volatility = sample.std(ddof=1)
            sharpe = sample.mean() / volatility * annual if volatility > 0 else -np.inf
            curve = (1 + sample).cumprod()
            drawdown = float(1 - (curve / curve.cummax()).min())
            should_enable = (
                sharpe >= self.risk.minimum_rolling_sharpe
                and drawdown <= self.risk.max_strategy_drawdown
            )
            if sleeve.enabled != should_enable:
                sleeve.enabled = should_enable
                changes[sleeve.name] = "enabled" if should_enable else "disabled"
        return changes

    def allocate(
        self,
        sleeves: list[StrategySleeve],
        method: Literal["equal", "volatility_parity", "sharpe", "min_correlation"] = "equal",
    ) -> pd.Series:
        selected = self.select_decorrelated(sleeves)
        frame = self.returns_frame(selected)
        if frame.empty or self.portfolio_halted:
            return pd.Series(dtype=float, name="weight")
        if method == "equal":
            raw = pd.Series(1.0, index=frame.columns)
        elif method == "volatility_parity":
            raw = 1 / frame.std(ddof=1).replace(0, np.nan)
        elif method == "sharpe":
            raw = (frame.mean() / frame.std(ddof=1).replace(0, np.nan)).clip(lower=0)
        elif method == "min_correlation":
            average_correlation = frame.corr().abs().where(~np.eye(len(frame.columns), dtype=bool)).mean()
            raw = 1 / average_correlation.replace(0, np.nan)
        else:
            raise ValueError(f"Unknown allocation method: {method}")
        if not np.isfinite(raw).any() or raw.fillna(0).sum() <= 0:
            raw = pd.Series(1.0, index=frame.columns)
        base = raw.replace([np.inf, -np.inf], np.nan).fillna(0)
        base /= base.sum()
        limits = pd.Series({sleeve.name: sleeve.max_weight for sleeve in selected})
        if (limits <= 0).any() or (limits > 1).any():
            raise ValueError("Sleeve max_weight values must be in (0, 1]")
        weights = pd.Series(0.0, index=base.index)
        active = list(base.index)
        remaining = 1.0
        while active and remaining > 0:
            active_base = base.loc[active]
            proposal = active_base / active_base.sum() * remaining
            over = [name for name in active if proposal[name] > limits[name]]
            if not over:
                weights.loc[active] = proposal
                break
            for name in over:
                weights[name] = limits[name]
                remaining -= limits[name]
                active.remove(name)
        # If all caps sum below one, the residual remains cash rather than violating limits.
        weights.name = "weight"
        return weights

    def portfolio_returns(self, sleeves: list[StrategySleeve], weights: pd.Series) -> pd.Series:
        frame = self.returns_frame(sleeves)
        common = frame.columns.intersection(weights.index)
        if not len(common):
            return pd.Series(0.0, index=frame.index, name="portfolio_return")
        result = frame[common].mul(weights[common], axis=1).sum(axis=1)
        result.name = "portfolio_return"
        curve = (1 + result).cumprod()
        if not curve.empty and float(1 - (curve / curve.cummax()).min()) >= self.risk.max_portfolio_drawdown:
            self.portfolio_halted = True
        return result

    def reset_circuit_breaker(self, *, explicit_acknowledgement: bool = False) -> None:
        if not explicit_acknowledgement:
            raise ValueError("An explicit acknowledgement is required to reset portfolio risk")
        self.portfolio_halted = False
