from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

import pandas as pd

from altron.data_layer.normalization import normalize_ohlcv
from altron.exceptions import StrategyError


class Strategy(ABC):
    """Plugin contract. Signals represent desired position: long, short, or flat."""

    name: str
    parameter_space: ClassVar[dict[str, Any]] = {}

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame, params: dict[str, Any]) -> pd.Series:
        """Return target positions: +1 long, -1 short, or 0 flat.

        Zero never means "no action" in this interface. Sparse order events must be
        converted to persistent targets before entering the strategy engine.
        """
        raise NotImplementedError

    def __call__(self, df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.Series:
        frame = normalize_ohlcv(df)
        signals = self.generate_signals(frame, params or {})
        if not isinstance(signals, pd.Series) or len(signals) != len(frame):
            raise StrategyError(f"{self.name} returned a malformed signal series")
        signals = pd.to_numeric(signals, errors="coerce").fillna(0).astype("int8")
        invalid = ~signals.isin([-1, 0, 1])
        if invalid.any():
            raise StrategyError(f"{self.name} returned values outside -1, 0, +1")
        signals.index = frame.index
        signals.name = "signal"
        return signals
