from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(slots=True)
class MonteCarloResult:
    ending_equity: np.ndarray
    max_drawdown: np.ndarray

    def percentiles(self) -> dict[str, float]:
        return {
            "ending_equity_p05": float(np.percentile(self.ending_equity, 5)),
            "ending_equity_median": float(np.percentile(self.ending_equity, 50)),
            "ending_equity_p95": float(np.percentile(self.ending_equity, 95)),
            "max_drawdown_p95": float(np.percentile(self.max_drawdown, 95)),
            "probability_of_loss": float(np.mean(self.ending_equity < 1.0)),
        }


def block_bootstrap(
    returns: pd.Series,
    *,
    simulations: int = 1000,
    block_size: int = 20,
    seed: int | None = None,
) -> MonteCarloResult:
    """Stationary-order block bootstrap preserving short-range autocorrelation."""
    values = returns.dropna().to_numpy(dtype=float)
    if len(values) < block_size:
        raise ValueError("Return history must be at least one block long")
    if simulations < 1 or block_size < 1:
        raise ValueError("simulations and block_size must be positive")
    generator = np.random.default_rng(seed)
    endings = np.empty(simulations)
    drawdowns = np.empty(simulations)
    blocks_needed = int(np.ceil(len(values) / block_size))
    maximum_start = len(values) - block_size
    for simulation in range(simulations):
        starts = generator.integers(0, maximum_start + 1, blocks_needed)
        sample = np.concatenate([values[start : start + block_size] for start in starts])[: len(values)]
        curve = np.cumprod(1 + np.clip(sample, -0.999999, None))
        peak = np.maximum.accumulate(np.r_[1.0, curve])
        drawdown = 1 - np.r_[1.0, curve] / peak
        endings[simulation] = curve[-1]
        drawdowns[simulation] = drawdown.max()
    return MonteCarloResult(endings, drawdowns)
