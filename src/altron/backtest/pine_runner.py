from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from altron.backtest.engine import BacktestEngine
from altron.backtest.models import BacktestResult
from altron.backtest.signal_import import import_external_signals
from altron.strategies.pine import PineTranslation, PineTranspiler
from altron.strategies.rules import RuleStrategy


@dataclass(slots=True)
class PineBacktestResult:
    backtest: BacktestResult
    translation: PineTranslation | None
    mode: str
    warnings: list[str]


class PineBacktestRunner:
    """Backtest translated Pine or externally exported target signals.

    Arbitrary Pine cannot execute outside TradingView. For scripts beyond Altron's
    reviewed subset, export timestamped targets/alerts from TradingView and use
    ``run_external``; this preserves the original Pine runtime semantics without
    pretending Python can interpret the whole language.
    """

    def __init__(self, engine: BacktestEngine | None = None) -> None:
        self.engine = engine or BacktestEngine()

    def run_source(self, candles: pd.DataFrame, source: str) -> PineBacktestResult:
        translation = PineTranspiler().transpile(source)
        strategy = RuleStrategy(translation.schema)
        result = self.engine.run(
            candles,
            strategy,
            {},
            metadata={"strategy_source": "pine_subset", "translation_warnings": translation.warnings},
        )
        return PineBacktestResult(
            backtest=result,
            translation=translation,
            mode="translated_subset",
            warnings=translation.warnings,
        )

    def run_external(
        self, candles: pd.DataFrame, exported_signals: pd.DataFrame
    ) -> PineBacktestResult:
        targets = import_external_signals(candles, exported_signals)
        result = self.engine.run(
            candles,
            signals=targets,
            metadata={"strategy_source": "external_pine_signals"},
        )
        return PineBacktestResult(
            backtest=result,
            translation=None,
            mode="external_signals",
            warnings=[
                "External targets are trusted as exported; verify timezone, bar-close settings, "
                "repainting behavior, and TradingView commission assumptions."
            ],
        )
