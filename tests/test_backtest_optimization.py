from __future__ import annotations

import pandas as pd
import pytest

from altron.backtest.engine import BacktestEngine
from altron.backtest.models import BacktestConfig
from altron.backtest.monte_carlo import block_bootstrap
from altron.optimization.search import StrategyOptimizer
from altron.optimization.walk_forward import WalkForwardAnalyzer, WalkForwardConfig
from altron.strategies.registry import get_strategy


def test_next_bar_execution_and_turnover_costs() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC"),
            "open": [100, 100, 110],
            "high": [101, 111, 122],
            "low": [99, 99, 109],
            "close": [100, 110, 121],
            "volume": [1, 1, 1],
        }
    )
    signals = pd.Series([1, 0, 0])
    no_cost = BacktestEngine(BacktestConfig(initial_capital=100, commission_bps=0, slippage_bps=0))
    result = no_cost.run(frame, signals=signals)
    assert result.equity.tolist() == pytest.approx([100, 110, 110])
    assert result.metrics["turnover"] == 2
    assert result.trades[0].entry_time == frame.timestamp.iloc[0]
    assert result.trades[0].exit_time == frame.timestamp.iloc[1]
    assert result.trades[0].entry_price == 100
    assert result.trades[0].exit_price == 110
    assert result.trades[0].return_pct == pytest.approx(.10)

    with_cost = BacktestEngine(BacktestConfig(initial_capital=100, commission_bps=10, slippage_bps=0))
    cost_result = with_cost.run(frame, signals=signals)
    assert cost_result.equity.iloc[-1] < 110
    assert cost_result.trades[0].return_pct < .10  # entry and exit costs are both attributed
    delayed = BacktestEngine(
        BacktestConfig(
            initial_capital=100,
            commission_bps=0,
            slippage_bps=0,
            execution_delay_bars=2,
        )
    )
    assert delayed.run(frame, signals=signals).equity.tolist() == pytest.approx([100, 100, 110])


def test_monte_carlo_is_seeded(candles: pd.DataFrame) -> None:
    result = BacktestEngine().run(candles, get_strategy("ma_crossover"), {})
    first = block_bootstrap(result.returns, simulations=20, block_size=10, seed=4)
    second = block_bootstrap(result.returns, simulations=20, block_size=10, seed=4)
    assert first.ending_equity.tolist() == second.ending_equity.tolist()
    assert 0 <= first.percentiles()["probability_of_loss"] <= 1


def test_mapped_yaml_search_space_works_without_optuna(candles: pd.DataFrame) -> None:
    result = StrategyOptimizer(BacktestEngine(), seed=8).optimize(
        candles.head(150),
        get_strategy("ma_crossover"),
        parameter_space={
            "fast_period": {"type": "int", "low": 3, "high": 6},
            "slow_period": {"type": "int", "low": 12, "high": 20, "step": 2},
            "ma_type": ["sma", "ema"],
        },
        trials=4,
        use_optuna=False,
    )
    assert 3 <= result.best.params["fast_period"] <= 6
    assert result.best.params["slow_period"] % 2 == 0


def test_walk_forward_has_disjoint_train_and_test_windows(candles: pd.DataFrame) -> None:
    analyzer = WalkForwardAnalyzer(
        BacktestEngine(BacktestConfig(commission_bps=0, slippage_bps=0)),
        WalkForwardConfig(
            train_bars=150,
            test_bars=50,
            trials=2,
            minimum_folds=3,
            use_optuna=False,
        ),
    )
    space = {"fast_period": [5], "slow_period": [20], "ma_type": ["sma"]}
    result = analyzer.run(candles, get_strategy("ma_crossover"), parameter_space=space)
    assert len(result.folds) == 7
    assert all(fold.train_end < fold.test_start for fold in result.folds)
    assert result.aggregate_metrics["folds"] == 7
