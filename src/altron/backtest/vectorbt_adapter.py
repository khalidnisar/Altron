from __future__ import annotations

import pandas as pd

from altron.backtest.models import BacktestConfig


class VectorBTAdapter:
    """Optional vectorbt portfolio builder for researchers needing its analytics."""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run(self, close: pd.Series, signals: pd.Series):
        try:
            import vectorbt as vbt  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Install vectorbt support with: pip install '.[vectorbt]'") from exc
        target = signals.shift(1).fillna(0)
        return vbt.Portfolio.from_orders(
            close,
            size=target,
            size_type="targetpercent",
            fees=self.config.commission_bps / 10_000,
            slippage=self.config.slippage_bps / 10_000,
            init_cash=self.config.initial_capital,
        )
