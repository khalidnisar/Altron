from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from altron.backtest.engine import BacktestEngine
from altron.optimization.search import StrategyOptimizer, composite_score
from altron.strategies.base import Strategy


@dataclass(slots=True)
class WalkForwardConfig:
    train_bars: int = 1000
    test_bars: int = 250
    step_bars: int | None = None
    anchored: bool = False
    trials: int = 50
    minimum_folds: int = 3
    minimum_positive_fold_ratio: float = 0.50
    minimum_mean_oos_score: float = 0.0
    minimum_oos_is_score_ratio: float = 0.20
    use_optuna: bool = True

    def __post_init__(self) -> None:
        if self.train_bars < 2 or self.test_bars < 1:
            raise ValueError("Walk-forward windows must be positive")
        if self.step_bars is not None and self.step_bars < 1:
            raise ValueError("step_bars must be positive")
        if not 0 <= self.minimum_positive_fold_ratio <= 1:
            raise ValueError("minimum_positive_fold_ratio must be between zero and one")
        if self.minimum_oos_is_score_ratio < 0:
            raise ValueError("minimum_oos_is_score_ratio cannot be negative")


@dataclass(slots=True)
class WalkForwardFold:
    fold: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    params: dict[str, Any]
    train_score: float
    test_score: float
    train_metrics: dict[str, float]
    test_metrics: dict[str, float]
    test_returns: pd.Series = field(repr=False)


@dataclass(slots=True)
class WalkForwardResult:
    folds: list[WalkForwardFold]
    robust: bool
    rejection_reasons: list[str]
    aggregate_metrics: dict[str, float]

    @property
    def best_parameters(self) -> dict[str, Any]:
        """Return the most recent fold's train-selected parameters.

        Selecting the best OOS fold would itself leak test performance into deployment.
        Callers may re-optimize on all data after the walk-forward process is accepted.
        """
        return self.folds[-1].params if self.folds else {}


class WalkForwardAnalyzer:
    """Optimize on each training window and evaluate only its unseen next window."""

    def __init__(self, engine: BacktestEngine, config: WalkForwardConfig | None = None) -> None:
        self.engine = engine
        self.config = config or WalkForwardConfig()

    def run(
        self,
        data: pd.DataFrame,
        strategy: Strategy,
        *,
        parameter_space: dict[str, Any] | None = None,
    ) -> WalkForwardResult:
        frame = data.reset_index(drop=True)
        config = self.config
        step = config.step_bars or config.test_bars
        folds: list[WalkForwardFold] = []
        test_start = config.train_bars
        fold_number = 0
        while test_start + config.test_bars <= len(frame):
            train_start = 0 if config.anchored else test_start - config.train_bars
            test_end = test_start + config.test_bars
            train = frame.iloc[train_start:test_start].reset_index(drop=True)
            optimizer = StrategyOptimizer(self.engine, seed=42 + fold_number)
            search = optimizer.optimize(
                train,
                strategy,
                parameter_space=parameter_space,
                trials=config.trials,
                use_optuna=config.use_optuna,
            )
            # Include the training history as indicator warm-up, then score test bars only.
            context = frame.iloc[train_start:test_end].reset_index(drop=True)
            all_signals = strategy(context, search.best.params)
            local_test_start = test_start - train_start
            # Keep the final training candle so its close signal can be executed over
            # the first OOS return. The warm-up row itself has zero return in the engine.
            evaluation_start = local_test_start - 1
            test = context.iloc[evaluation_start : test_end - train_start].reset_index(drop=True)
            test_signals = all_signals.iloc[evaluation_start : test_end - train_start].reset_index(drop=True)
            test_result = self.engine.run(test, signals=test_signals)
            folds.append(
                WalkForwardFold(
                    fold=fold_number,
                    train_start=pd.Timestamp(train["timestamp"].iloc[0]),
                    train_end=pd.Timestamp(train["timestamp"].iloc[-1]),
                    test_start=pd.Timestamp(frame["timestamp"].iloc[test_start]),
                    test_end=pd.Timestamp(frame["timestamp"].iloc[test_end - 1]),
                    params=search.best.params,
                    train_score=search.best.score,
                    test_score=composite_score(test_result.metrics),
                    train_metrics=search.best.metrics,
                    test_metrics=test_result.metrics,
                    test_returns=test_result.returns.iloc[1:].reset_index(drop=True),
                )
            )
            fold_number += 1
            test_start += step

        reasons: list[str] = []
        if len(folds) < config.minimum_folds:
            reasons.append(f"only {len(folds)} fold(s); at least {config.minimum_folds} required")
        if folds:
            positive_ratio = np.mean([fold.test_metrics.get("sharpe", 0) > 0 for fold in folds])
            if positive_ratio < config.minimum_positive_fold_ratio:
                reasons.append(
                    f"positive OOS Sharpe in {positive_ratio:.0%} of folds; "
                    f"requires {config.minimum_positive_fold_ratio:.0%}"
                )
            in_sample = np.mean([fold.train_score for fold in folds])
            out_sample_score = np.mean([fold.test_score for fold in folds])
            out_sample_sharpe = np.mean([fold.test_metrics.get("sharpe", 0.0) for fold in folds])
            if out_sample_score < config.minimum_mean_oos_score:
                reasons.append(
                    f"mean OOS score {out_sample_score:.3f} is below "
                    f"{config.minimum_mean_oos_score:.3f}"
                )
            if in_sample > 0 and out_sample_score < in_sample * config.minimum_oos_is_score_ratio:
                reasons.append("out-of-sample score degraded beyond the configured overfit threshold")
            aggregate = {
                "folds": float(len(folds)),
                "mean_train_score": float(in_sample),
                "mean_oos_score": float(out_sample_score),
                "mean_oos_sharpe": float(out_sample_sharpe),
                "median_oos_sharpe": float(np.median([fold.test_metrics.get("sharpe", 0) for fold in folds])),
                "mean_oos_sortino": float(np.mean([fold.test_metrics.get("sortino", 0) for fold in folds])),
                "worst_oos_drawdown": float(max(fold.test_metrics.get("max_drawdown", 0) for fold in folds)),
                "positive_fold_ratio": float(positive_ratio),
            }
        else:
            aggregate = {"folds": 0.0}
        return WalkForwardResult(folds, robust=not reasons, rejection_reasons=reasons, aggregate_metrics=aggregate)
