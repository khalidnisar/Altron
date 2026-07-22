from __future__ import annotations

from altron.backtest.models import BacktestConfig
from altron.optimization.robust import RobustParameterOptimizer, RobustTestConfig
from altron.strategies.registry import get_strategy


def test_fast_robust_optimizer_tests_scenarios_and_returns_sweet_spot(candles) -> None:
    optimizer = RobustParameterOptimizer(
        BacktestConfig(commission_bps=1, slippage_bps=1, position_fraction=.25),
        RobustTestConfig(
            trials=12,
            retention_ratio=.25,
            minimum_full_candidates=4,
            regime_splits=2,
            workers=2,
            maximum_scenario_drawdown=.9,
            minimum_scenario_return=-.9,
            minimum_positive_scenario_ratio=0,
            seed=5,
        ),
    )
    result = optimizer.optimize(
        candles.head(240),
        get_strategy("ma_crossover"),
        parameter_space={
            "fast_period": {"type": "int", "low": 3, "high": 8},
            "slow_period": {"type": "int", "low": 15, "high": 30},
            "ma_type": ["sma", "ema"],
        },
    )
    assert result.screened_candidates >= 8
    assert result.fully_tested_candidates == 4
    assert len(result.scenarios) >= 8
    assert set(result.best.scenario_metrics) == {scenario.name for scenario in result.scenarios}
    assert result.sweet_spot["recommended_params"] == result.best.params
    assert result.pareto_frontier
    assert result.elapsed_seconds > 0
