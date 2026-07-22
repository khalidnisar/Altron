from __future__ import annotations

import pandas as pd
import pytest
import yaml

from altron.strategies.pine import PineTranslationError, PineTranspiler
from altron.strategies.registry import get_strategy, list_strategies
from altron.strategies.rules import strategy_from_definition


@pytest.mark.parametrize("name", list_strategies())
def test_builtin_strategies_obey_signal_contract(name: str, candles: pd.DataFrame) -> None:
    signals = get_strategy(name)(candles, {})
    assert len(signals) == len(candles)
    assert set(signals.unique()) <= {-1, 0, 1}
    if name == "supertrend":
        assert signals.ne(0).any()


def test_rule_strategy_and_multi_timeframe_alignment(candles: pd.DataFrame) -> None:
    definition = yaml.safe_load(open("examples/rsi_strategy.yaml"))
    strategy = strategy_from_definition(definition)
    signals = strategy(candles, {})
    assert set(signals.unique()) <= {-1, 0, 1}
    # A 4-hour indicator shifted to closed bars cannot be available at startup.
    assert (signals.head(50) == 0).all()


def test_compact_rsi_definition(candles: pd.DataFrame) -> None:
    strategy = strategy_from_definition({"indicator": "rsi", "period": 8, "overbought": 75})
    assert len(strategy(candles, {})) == len(candles)


def test_pine_subset_translation() -> None:
    source = open("examples/ma_crossover.pine").read()
    translation = PineTranspiler().transpile(source)
    assert translation.schema["long_entry"]["operator"] == "crosses_above"
    assert translation.schema["short_entry"]["operator"] == "crosses_below"
    assert "class TranslatedPineStrategy" in translation.to_python()


def test_pine_rejects_security_calls() -> None:
    with pytest.raises(PineTranslationError, match="request.security"):
        PineTranspiler().transpile("x = request.security(syminfo.tickerid, 'D', close)")
