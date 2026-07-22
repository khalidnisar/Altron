from __future__ import annotations

import pandas as pd
import pytest

from altron.backtest.engine import BacktestEngine
from altron.backtest.pine_runner import PineBacktestRunner
from altron.backtest.signal_import import import_external_signals


def test_sparse_external_pine_targets_are_aligned_and_carried(candles: pd.DataFrame) -> None:
    exported = pd.DataFrame(
        {
            "timestamp": [candles.timestamp.iloc[10], candles.timestamp.iloc[20], candles.timestamp.iloc[30]],
            "signal": ["buy", "flat", "sell"],
        }
    )
    targets = import_external_signals(candles.head(50), exported)
    assert targets.iloc[9] == 0
    assert (targets.iloc[10:20] == 1).all()
    assert (targets.iloc[20:30] == 0).all()
    assert (targets.iloc[30:] == -1).all()
    result = PineBacktestRunner(BacktestEngine()).run_external(candles.head(50), exported)
    assert result.mode == "external_signals"
    assert len(result.backtest.trades) == 2


def test_external_signal_timestamp_must_match_candle_grid(candles: pd.DataFrame) -> None:
    exported = pd.DataFrame(
        {"timestamp": [candles.timestamp.iloc[2] + pd.Timedelta(minutes=1)], "signal": [1]}
    )
    with pytest.raises(ValueError, match="do not match"):
        import_external_signals(candles.head(20), exported)
