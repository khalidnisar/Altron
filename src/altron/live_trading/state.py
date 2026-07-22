from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from altron.live_trading.models import SignalEvent


@dataclass(slots=True)
class _SignalState:
    committed_timestamp: pd.Timestamp | None = None
    committed_signal: int = 0
    seen_timestamp: pd.Timestamp | None = None


class SignalStateMachine:
    """Two-phase transition state.

    ``should_transition`` records only the observed candle timestamp. The desired
    signal is committed separately after required broker routing succeeds. This
    permits a failed broker transition to retry on the next closed candle without
    executing twice for a duplicate update of the same candle.
    """

    def __init__(self) -> None:
        self._states: dict[tuple[str, str, str], _SignalState] = {}

    @staticmethod
    def _key(event: SignalEvent) -> tuple[str, str, str]:
        return event.symbol, event.timeframe, event.strategy

    def should_transition(self, event: SignalEvent) -> bool:
        key = self._key(event)
        timestamp = pd.Timestamp(event.timestamp)
        state = self._states.setdefault(key, _SignalState())
        if state.seen_timestamp is not None and timestamp <= state.seen_timestamp:
            return False
        state.seen_timestamp = timestamp
        return event.signal != state.committed_signal

    def commit(self, event: SignalEvent) -> None:
        key = self._key(event)
        timestamp = pd.Timestamp(event.timestamp)
        state = self._states.setdefault(key, _SignalState())
        if state.committed_timestamp is not None and timestamp < state.committed_timestamp:
            raise ValueError("Cannot commit an out-of-order signal")
        state.committed_timestamp = timestamp
        state.seen_timestamp = max(timestamp, state.seen_timestamp or timestamp)
        state.committed_signal = event.signal

    def transition(self, event: SignalEvent) -> bool:
        """Compatibility helper for non-broker callers."""
        if not self.should_transition(event):
            return False
        self.commit(event)
        return True

    def current(self, symbol: str, timeframe: str) -> dict[str, int]:
        return {
            strategy: state.committed_signal
            for (state_symbol, state_timeframe, strategy), state in self._states.items()
            if state_symbol == symbol and state_timeframe == timeframe
        }
