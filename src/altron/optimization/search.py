from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from altron.backtest.engine import BacktestEngine
from altron.backtest.models import BacktestResult
from altron.exceptions import StrategyError
from altron.strategies.base import Strategy


@dataclass(slots=True)
class ScoreWeights:
    sharpe: float = 1.0
    sortino: float = 0.25
    cagr: float = 0.10
    drawdown_penalty: float = 2.0


def composite_score(metrics: dict[str, float], weights: ScoreWeights | None = None) -> float:
    weights = weights or ScoreWeights()
    score = (
        weights.sharpe * metrics.get("sharpe", 0.0)
        + weights.sortino * metrics.get("sortino", 0.0)
        + weights.cagr * metrics.get("cagr", 0.0)
        - weights.drawdown_penalty * metrics.get("max_drawdown", 0.0)
    )
    return float(score) if math.isfinite(score) else -1e12


def _random_parameters(space: dict[str, Any], generator: np.random.Generator) -> dict[str, Any]:
    parameters: dict[str, Any] = {}
    for name, specification in space.items():
        if isinstance(specification, list):
            parameters[name] = specification[int(generator.integers(0, len(specification)))]
        elif isinstance(specification, tuple) and len(specification) == 2:
            low, high = specification
            if isinstance(low, int) and isinstance(high, int):
                parameters[name] = int(generator.integers(low, high + 1))
            else:
                parameters[name] = float(generator.uniform(float(low), float(high)))
        elif isinstance(specification, dict):
            kind = specification.get("type")
            if kind == "categorical":
                choices = specification.get("choices", [])
                if not choices:
                    raise ValueError(f"Categorical parameter {name} has no choices")
                parameters[name] = choices[int(generator.integers(0, len(choices)))]
            elif kind == "int":
                low, high = int(specification["low"]), int(specification["high"])
                step = int(specification.get("step", 1))
                if low > high or step < 1:
                    raise ValueError(f"Invalid integer bounds for {name}")
                if specification.get("log"):
                    if low <= 0 or step != 1:
                        raise ValueError(f"Log-integer parameter {name} requires low > 0 and step=1")
                    parameters[name] = min(
                        high, max(low, int(round(np.exp(generator.uniform(np.log(low), np.log(high))))))
                    )
                else:
                    choices = np.arange(low, high + 1, step)
                    parameters[name] = int(choices[int(generator.integers(0, len(choices)))])
            elif kind == "float":
                low, high = float(specification["low"]), float(specification["high"])
                step = specification.get("step")
                if low > high or (specification.get("log") and low <= 0):
                    raise ValueError(f"Invalid float bounds for {name}")
                if specification.get("log"):
                    if step is not None:
                        raise ValueError(f"Log-float parameter {name} cannot also define step")
                    parameters[name] = float(np.exp(generator.uniform(np.log(low), np.log(high))))
                elif step is not None:
                    choices = np.arange(low, high + float(step) / 2, float(step))
                    parameters[name] = float(choices[int(generator.integers(0, len(choices)))])
                else:
                    parameters[name] = float(generator.uniform(low, high))
            else:
                raise ValueError(f"Invalid mapped parameter specification for {name}: {specification!r}")
        else:
            raise ValueError(f"Invalid parameter specification for {name}: {specification!r}")
    return parameters


def _optuna_parameter(trial: Any, name: str, specification: Any) -> Any:
    if isinstance(specification, list):
        return trial.suggest_categorical(name, specification)
    if isinstance(specification, tuple) and len(specification) == 2:
        low, high = specification
        if isinstance(low, int) and isinstance(high, int):
            return trial.suggest_int(name, low, high)
        return trial.suggest_float(name, float(low), float(high))
    if isinstance(specification, dict):
        kind = specification.get("type")
        if kind == "categorical":
            choices = specification.get("choices", [])
            if not choices:
                raise ValueError(f"Categorical parameter {name} has no choices")
            return trial.suggest_categorical(name, choices)
        if kind == "int":
            return trial.suggest_int(
                name,
                int(specification["low"]),
                int(specification["high"]),
                step=int(specification.get("step", 1)),
                log=bool(specification.get("log", False)),
            )
        if kind == "float":
            step = specification.get("step")
            return trial.suggest_float(
                name,
                float(specification["low"]),
                float(specification["high"]),
                step=float(step) if step is not None else None,
                log=bool(specification.get("log", False)),
            )
    raise ValueError(f"Invalid parameter specification for {name}: {specification!r}")


@dataclass(slots=True)
class TrialResult:
    params: dict[str, Any]
    score: float
    metrics: dict[str, float]


@dataclass(slots=True)
class SearchResult:
    best: TrialResult
    trials: list[TrialResult] = field(default_factory=list)


class StrategyOptimizer:
    def __init__(
        self,
        engine: BacktestEngine,
        *,
        weights: ScoreWeights | None = None,
        seed: int = 42,
    ) -> None:
        self.engine = engine
        self.weights = weights or ScoreWeights()
        self.seed = seed

    def optimize(
        self,
        data: pd.DataFrame,
        strategy: Strategy,
        *,
        parameter_space: dict[str, Any] | None = None,
        trials: int = 50,
        use_optuna: bool = True,
    ) -> SearchResult:
        if trials < 1:
            raise ValueError("trials must be positive")
        space = parameter_space or strategy.parameter_space
        if not space:
            result = self.engine.run(data, strategy, {})
            item = TrialResult({}, composite_score(result.metrics, self.weights), result.metrics)
            return SearchResult(item, [item])
        history: list[TrialResult] = []

        def evaluate(params: dict[str, Any]) -> float:
            try:
                backtest: BacktestResult = self.engine.run(data, strategy, params)
                score = composite_score(backtest.metrics, self.weights)
                metrics = backtest.metrics
            except (ValueError, FloatingPointError, StrategyError):
                score, metrics = -1e12, {}
            history.append(TrialResult(dict(params), score, dict(metrics)))
            return score

        if use_optuna:
            try:
                import optuna  # type: ignore[import-not-found]
            except ImportError:
                use_optuna = False
        if use_optuna:
            optuna.logging.set_verbosity(optuna.logging.WARNING)
            study = optuna.create_study(
                direction="maximize", sampler=optuna.samplers.TPESampler(seed=self.seed)
            )

            def objective(trial: Any) -> float:
                params = {
                    name: _optuna_parameter(trial, name, specification)
                    for name, specification in space.items()
                }
                return evaluate(params)

            study.optimize(objective, n_trials=trials, n_jobs=1, show_progress_bar=False)
        else:
            generator = np.random.default_rng(self.seed)
            for _ in range(trials):
                evaluate(_random_parameters(space, generator))
        best = max(history, key=lambda item: item.score)
        if best.score <= -1e11:
            raise ValueError("No valid parameter combination was evaluated")
        return SearchResult(best=best, trials=history)
