from __future__ import annotations

import copy
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
import pandas as pd

from altron.backtest.engine import BacktestEngine
from altron.backtest.models import BacktestConfig
from altron.data_layer.normalization import normalize_ohlcv
from altron.exceptions import StrategyError
from altron.strategies.base import Strategy


@dataclass(slots=True)
class RobustScoreWeights:
    """Profit/risk objective used to choose the robust sweet spot."""

    total_return: float = 2.0
    cagr: float = 0.20
    sharpe: float = 0.45
    sortino: float = 0.15
    drawdown_penalty: float = 2.75
    worst_scenario_weight: float = 0.75
    instability_penalty: float = 0.20


@dataclass(slots=True)
class RobustTestConfig:
    trials: int = 100
    retention_ratio: float = 0.25
    minimum_full_candidates: int = 12
    regime_splits: int = 3
    workers: int = field(default_factory=lambda: max(1, min(32, (os.cpu_count() or 2) - 1)))
    seed: int = 42
    cost_multiplier: float = 2.0
    latency_bars: int = 1
    maximum_scenario_drawdown: float = 0.30
    minimum_scenario_return: float = -0.15
    minimum_positive_scenario_ratio: float = 0.60
    score: RobustScoreWeights = field(default_factory=RobustScoreWeights)

    def __post_init__(self) -> None:
        if self.trials < 2:
            raise ValueError("trials must be at least two")
        if not 0 < self.retention_ratio <= 1:
            raise ValueError("retention_ratio must be in (0, 1]")
        if self.minimum_full_candidates < 1 or self.workers < 1:
            raise ValueError("minimum_full_candidates and workers must be positive")
        if self.regime_splits < 1:
            raise ValueError("regime_splits must be positive")
        if self.cost_multiplier < 1 or self.latency_bars < 0:
            raise ValueError("Stress costs must be >= 1 and latency cannot be negative")
        if not 0 <= self.minimum_positive_scenario_ratio <= 1:
            raise ValueError("minimum_positive_scenario_ratio must be between zero and one")


@dataclass(slots=True)
class ScenarioDefinition:
    name: str
    start: int
    end: int
    config: BacktestConfig
    category: str

    @property
    def bars(self) -> int:
        return self.end - self.start

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "start_bar": self.start,
            "end_bar": self.end,
            "bars": self.bars,
            "commission_bps": self.config.commission_bps,
            "slippage_bps": self.config.slippage_bps,
            "execution_delay_bars": self.config.execution_delay_bars,
            "allow_short": self.config.allow_short,
        }


@dataclass(slots=True)
class CandidateEvaluation:
    params: dict[str, Any]
    robust_score: float
    baseline_score: float
    mean_return: float
    median_return: float
    worst_return: float
    mean_sharpe: float
    worst_drawdown: float
    score_instability: float
    positive_scenario_ratio: float
    robust: bool
    scenario_metrics: dict[str, dict[str, float]] = field(repr=False)
    error: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "params": self.params,
            "robust_score": self.robust_score,
            "baseline_score": self.baseline_score,
            "mean_return": self.mean_return,
            "median_return": self.median_return,
            "worst_return": self.worst_return,
            "mean_sharpe": self.mean_sharpe,
            "worst_drawdown": self.worst_drawdown,
            "score_instability": self.score_instability,
            "positive_scenario_ratio": self.positive_scenario_ratio,
            "robust": self.robust,
            "error": self.error,
        }


@dataclass(slots=True)
class RobustOptimizationResult:
    best: CandidateEvaluation
    candidates: list[CandidateEvaluation]
    scenarios: list[ScenarioDefinition]
    pareto_frontier: list[CandidateEvaluation]
    sweet_spot: dict[str, Any]
    elapsed_seconds: float
    screened_candidates: int
    fully_tested_candidates: int
    workers: int
    warnings: list[str]

    def summary(self) -> dict[str, Any]:
        return {
            "best": self.best.summary(),
            "sweet_spot": self.sweet_spot,
            "scenarios": [scenario.summary() for scenario in self.scenarios],
            "pareto_frontier": [candidate.summary() for candidate in self.pareto_frontier],
            "elapsed_seconds": self.elapsed_seconds,
            "screened_candidates": self.screened_candidates,
            "fully_tested_candidates": self.fully_tested_candidates,
            "workers": self.workers,
            "warnings": self.warnings,
        }


def _value_from_unit(specification: Any, unit: float) -> Any:
    unit = min(1 - np.finfo(float).eps, max(0.0, unit))
    if isinstance(specification, list):
        if not specification:
            raise ValueError("Categorical parameter has no choices")
        return specification[min(len(specification) - 1, int(unit * len(specification)))]
    if isinstance(specification, tuple) and len(specification) == 2:
        low, high = specification
        if isinstance(low, int) and isinstance(high, int):
            return int(low + math.floor(unit * (high - low + 1)))
        return float(low) + unit * (float(high) - float(low))
    if isinstance(specification, dict):
        kind = specification.get("type")
        if kind == "categorical":
            return _value_from_unit(list(specification.get("choices", [])), unit)
        low, high = specification.get("low"), specification.get("high")
        if low is None or high is None or float(low) > float(high):
            raise ValueError(f"Invalid parameter bounds: {specification!r}")
        if kind == "int":
            step = int(specification.get("step", 1))
            if step < 1:
                raise ValueError("Integer parameter step must be positive")
            values = list(range(int(low), int(high) + 1, step))
            if specification.get("log"):
                if int(low) <= 0 or step != 1:
                    raise ValueError("Log integer spaces require low > 0 and step=1")
                raw = math.exp(math.log(float(low)) + unit * (math.log(float(high)) - math.log(float(low))))
                return min(int(high), max(int(low), int(round(raw))))
            return values[min(len(values) - 1, int(unit * len(values)))]
        if kind == "float":
            low_float, high_float = float(low), float(high)
            if specification.get("log"):
                if low_float <= 0 or specification.get("step") is not None:
                    raise ValueError("Log float spaces require low > 0 and no step")
                return math.exp(math.log(low_float) + unit * (math.log(high_float) - math.log(low_float)))
            step = specification.get("step")
            if step is not None:
                float_values = np.arange(low_float, high_float + float(step) / 2, float(step))
                return float(
                    float_values[
                        min(len(float_values) - 1, int(unit * len(float_values)))
                    ]
                )
            return low_float + unit * (high_float - low_float)
    raise ValueError(f"Unsupported parameter specification: {specification!r}")


def _latin_hypercube_candidates(
    space: dict[str, Any], trials: int, seed: int
) -> list[dict[str, Any]]:
    if not space:
        return [{}]
    generator = np.random.default_rng(seed)
    units: dict[str, np.ndarray] = {}
    for name in space:
        values = (np.arange(trials) + generator.random(trials)) / trials
        generator.shuffle(values)
        units[name] = values
    candidates = [
        {
            name: _value_from_unit(specification, float(units[name][trial]))
            for name, specification in space.items()
        }
        for trial in range(trials)
    ]
    # Include the strategy defaults as a benchmark without increasing requested work.
    candidates[0] = {}
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = json.dumps(candidate, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _metric_score(metrics: dict[str, float], weights: RobustScoreWeights) -> float:
    total_return = float(np.clip(metrics.get("total_return", 0.0), -0.99, 5.0))
    cagr = float(np.clip(metrics.get("cagr", 0.0), -1.0, 3.0))
    sharpe = float(np.clip(metrics.get("sharpe", 0.0), -8.0, 8.0))
    sortino = float(np.clip(metrics.get("sortino", 0.0), -12.0, 12.0))
    drawdown = float(np.clip(metrics.get("max_drawdown", 0.0), 0.0, 1.0))
    return (
        weights.total_return * total_return
        + weights.cagr * cagr
        + weights.sharpe * sharpe
        + weights.sortino * sortino
        - weights.drawdown_penalty * drawdown
    )


def _window_start(values: pd.Series, window: int, mode: str) -> int:
    if mode == "volatility":
        statistic = values.pct_change().rolling(window).std()
        endpoint = statistic.idxmax()
    else:
        statistic = values / values.shift(window) - 1
        endpoint = statistic.idxmin()
    if pd.isna(endpoint):
        return 0
    return max(0, int(endpoint) - window + 1)


def build_scenarios(
    data: pd.DataFrame,
    base_config: BacktestConfig,
    config: RobustTestConfig,
) -> list[ScenarioDefinition]:
    frame = normalize_ohlcv(data)
    count = len(frame)
    if count < 80:
        raise ValueError("Robust strategy testing requires at least 80 candles")
    scenarios = [
        ScenarioDefinition("baseline", 0, count, base_config, "reference"),
        ScenarioDefinition(
            f"costs_x{config.cost_multiplier:g}",
            0,
            count,
            replace(
                base_config,
                commission_bps=base_config.commission_bps * config.cost_multiplier,
                slippage_bps=base_config.slippage_bps * config.cost_multiplier,
            ),
            "execution_stress",
        ),
        ScenarioDefinition(
            f"latency_plus_{config.latency_bars}_bars",
            0,
            count,
            replace(
                base_config,
                execute_next_bar=True,
                execution_delay_bars=(
                    base_config.execution_delay_bars if base_config.execute_next_bar else 0
                )
                + config.latency_bars,
            ),
            "execution_stress",
        ),
    ]
    if base_config.allow_short:
        scenarios.append(
            ScenarioDefinition(
                "long_only_constraint",
                0,
                count,
                replace(base_config, allow_short=False),
                "portfolio_constraint",
            )
        )

    splits = min(config.regime_splits, max(1, count // 80))
    boundaries = np.linspace(0, count, splits + 1, dtype=int)
    for index in range(splits):
        start, end = int(boundaries[index]), int(boundaries[index + 1])
        scenarios.append(
            ScenarioDefinition(
                f"chronological_regime_{index + 1}",
                start,
                end,
                base_config,
                "market_regime",
            )
        )

    window = max(60, count // max(3, splits))
    window = min(window, count)
    high_vol_start = _window_start(frame["close"], window, "volatility")
    worst_start = _window_start(frame["close"], window, "return")
    scenarios.extend(
        [
            ScenarioDefinition(
                "highest_volatility_window",
                high_vol_start,
                min(count, high_vol_start + window),
                base_config,
                "market_stress",
            ),
            ScenarioDefinition(
                "worst_market_window",
                worst_start,
                min(count, worst_start + window),
                base_config,
                "market_stress",
            ),
        ]
    )
    return scenarios


class RobustParameterOptimizer:
    """Two-stage, parallel parameter search for a stable profit/risk sweet spot.

    Stage one screens all Latin-hypercube candidates on the baseline. Stage two runs
    only the strongest candidates through every cost, latency, constraint, and market
    regime scenario. Strategy signals are generated once per full-stage candidate and
    reused across scenario backtests.
    """

    def __init__(
        self,
        base_config: BacktestConfig | None = None,
        test_config: RobustTestConfig | None = None,
    ) -> None:
        self.base_config = base_config or BacktestConfig()
        self.test_config = test_config or RobustTestConfig()

    def _screen(
        self, frame: pd.DataFrame, strategy: Strategy, params: dict[str, Any]
    ) -> tuple[dict[str, Any], float, str | None]:
        try:
            isolated_strategy = copy.deepcopy(strategy)
            signals = isolated_strategy(frame, params)
            result = BacktestEngine(self.base_config).run(frame, signals=signals)
            return params, _metric_score(result.metrics, self.test_config.score), None
        except (ValueError, StrategyError, FloatingPointError) as exc:
            return params, -1e12, str(exc)

    def _evaluate(
        self,
        frame: pd.DataFrame,
        strategy: Strategy,
        params: dict[str, Any],
        baseline_score: float,
        scenarios: list[ScenarioDefinition],
    ) -> CandidateEvaluation:
        try:
            isolated_strategy = copy.deepcopy(strategy)
            signals = isolated_strategy(frame, params)
            scenario_metrics: dict[str, dict[str, float]] = {}
            scenario_scores: list[float] = []
            for scenario in scenarios:
                subset = frame.iloc[scenario.start : scenario.end].reset_index(drop=True)
                subset_signals = signals.iloc[scenario.start : scenario.end].reset_index(drop=True)
                result = BacktestEngine(scenario.config).run(subset, signals=subset_signals)
                scenario_metrics[scenario.name] = result.metrics
                scenario_scores.append(_metric_score(result.metrics, self.test_config.score))
            returns = np.asarray(
                [metrics.get("total_return", 0.0) for metrics in scenario_metrics.values()],
                dtype=float,
            )
            sharpes = np.asarray(
                [metrics.get("sharpe", 0.0) for metrics in scenario_metrics.values()], dtype=float
            )
            drawdowns = np.asarray(
                [metrics.get("max_drawdown", 0.0) for metrics in scenario_metrics.values()],
                dtype=float,
            )
            scores = np.asarray(scenario_scores, dtype=float)
            instability = float(scores.std(ddof=0))
            robust_score = float(
                scores.mean()
                + self.test_config.score.worst_scenario_weight * scores.min()
                - self.test_config.score.instability_penalty * instability
            )
            positive_ratio = float(np.mean(returns > 0))
            robust = bool(
                returns.min() >= self.test_config.minimum_scenario_return
                and drawdowns.max() <= self.test_config.maximum_scenario_drawdown
                and positive_ratio >= self.test_config.minimum_positive_scenario_ratio
            )
            return CandidateEvaluation(
                params=params,
                robust_score=robust_score,
                baseline_score=baseline_score,
                mean_return=float(returns.mean()),
                median_return=float(np.median(returns)),
                worst_return=float(returns.min()),
                mean_sharpe=float(sharpes.mean()),
                worst_drawdown=float(drawdowns.max()),
                score_instability=instability,
                positive_scenario_ratio=positive_ratio,
                robust=robust,
                scenario_metrics=scenario_metrics,
            )
        except (ValueError, StrategyError, FloatingPointError) as exc:
            return CandidateEvaluation(
                params=params,
                robust_score=-1e12,
                baseline_score=baseline_score,
                mean_return=-1.0,
                median_return=-1.0,
                worst_return=-1.0,
                mean_sharpe=-8.0,
                worst_drawdown=1.0,
                score_instability=1e6,
                positive_scenario_ratio=0.0,
                robust=False,
                scenario_metrics={},
                error=str(exc),
            )

    @staticmethod
    def _pareto(candidates: list[CandidateEvaluation]) -> list[CandidateEvaluation]:
        valid = [candidate for candidate in candidates if candidate.error is None]
        frontier: list[CandidateEvaluation] = []
        for candidate in valid:
            dominated = any(
                other is not candidate
                and other.mean_return >= candidate.mean_return
                and other.mean_sharpe >= candidate.mean_sharpe
                and other.worst_drawdown <= candidate.worst_drawdown
                and (
                    other.mean_return > candidate.mean_return
                    or other.mean_sharpe > candidate.mean_sharpe
                    or other.worst_drawdown < candidate.worst_drawdown
                )
                for other in valid
            )
            if not dominated:
                frontier.append(candidate)
        return sorted(frontier, key=lambda item: item.robust_score, reverse=True)

    @staticmethod
    def _sweet_spot(
        best: CandidateEvaluation, candidates: list[CandidateEvaluation]
    ) -> dict[str, Any]:
        ordered = sorted(
            [candidate for candidate in candidates if candidate.error is None],
            key=lambda item: item.robust_score,
            reverse=True,
        )
        stable_count = max(1, min(len(ordered), max(3, math.ceil(len(ordered) * 0.20))))
        neighborhood = ordered[:stable_count]
        ranges: dict[str, Any] = {}
        names = sorted({name for candidate in neighborhood for name in candidate.params})
        for name in names:
            values = [candidate.params[name] for candidate in neighborhood if name in candidate.params]
            if values and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
                ranges[name] = {
                    "recommended": best.params.get(name),
                    "stable_min": min(values),
                    "stable_max": max(values),
                    "stable_median": float(np.median(values)),
                }
            elif values:
                counts = {value: values.count(value) for value in set(values)}
                ranges[name] = {
                    "recommended": best.params.get(name),
                    "stable_choices": sorted(counts, key=counts.get, reverse=True),
                }
        return {
            "recommended_params": best.params,
            "stable_ranges": ranges,
            "neighborhood_candidates": stable_count,
            "selection_rule": "highest all-scenario profit/risk score with worst-case and instability penalties",
        }

    def optimize(
        self,
        data: pd.DataFrame,
        strategy: Strategy,
        *,
        parameter_space: dict[str, Any] | None = None,
    ) -> RobustOptimizationResult:
        started = time.perf_counter()
        frame = normalize_ohlcv(data)
        space = parameter_space or strategy.parameter_space
        candidates = _latin_hypercube_candidates(
            space, self.test_config.trials, self.test_config.seed
        )
        scenarios = build_scenarios(frame, self.base_config, self.test_config)

        screened: list[tuple[dict[str, Any], float, str | None]] = []
        with ThreadPoolExecutor(max_workers=self.test_config.workers) as executor:
            screen_futures = [
                executor.submit(self._screen, frame, strategy, params) for params in candidates
            ]
            for screen_future in as_completed(screen_futures):
                screened.append(screen_future.result())
        valid_screened = [item for item in screened if item[1] > -1e11]
        if not valid_screened:
            errors = sorted({error for _, _, error in screened if error})
            raise ValueError("No valid parameter candidates. " + "; ".join(errors[:3]))
        valid_screened.sort(
            key=lambda item: (item[1], json.dumps(item[0], sort_keys=True)), reverse=True
        )
        retained_count = min(
            len(valid_screened),
            max(
                self.test_config.minimum_full_candidates,
                math.ceil(len(valid_screened) * self.test_config.retention_ratio),
            ),
        )
        retained = valid_screened[:retained_count]

        evaluations: list[CandidateEvaluation] = []
        with ThreadPoolExecutor(max_workers=self.test_config.workers) as executor:
            evaluation_futures = [
                executor.submit(
                    self._evaluate, frame, strategy, params, baseline_score, scenarios
                )
                for params, baseline_score, _ in retained
            ]
            for evaluation_future in as_completed(evaluation_futures):
                evaluations.append(evaluation_future.result())
        valid = [candidate for candidate in evaluations if candidate.error is None]
        if not valid:
            raise ValueError("Every retained parameter candidate failed scenario evaluation")
        robust_candidates = [candidate for candidate in valid if candidate.robust]
        ranking_pool = robust_candidates or valid
        best = max(
            ranking_pool,
            key=lambda item: (item.robust_score, json.dumps(item.params, sort_keys=True)),
        )
        warnings: list[str] = []
        if not robust_candidates:
            warnings.append(
                "No candidate passed every robustness gate; the highest-scoring fallback is shown "
                "but should not be promoted to paper deployment."
            )
        warnings.append(
            f"Fast two-stage screening ran all {len(candidates)} candidates once and only "
            f"{len(retained)} candidates through {len(scenarios)} full scenarios."
        )
        evaluations.sort(
            key=lambda item: (
                item.robust,
                item.robust_score,
                json.dumps(item.params, sort_keys=True),
            ),
            reverse=True,
        )
        return RobustOptimizationResult(
            best=best,
            candidates=evaluations,
            scenarios=scenarios,
            pareto_frontier=self._pareto(valid),
            sweet_spot=self._sweet_spot(best, valid),
            elapsed_seconds=time.perf_counter() - started,
            screened_candidates=len(candidates),
            fully_tested_candidates=len(retained),
            workers=self.test_config.workers,
            warnings=warnings,
        )
