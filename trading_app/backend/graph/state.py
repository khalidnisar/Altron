"""Shared graph state — one invocation per (symbol, closed candle)."""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class GraphState(TypedDict, total=False):
    # inputs
    symbol: str
    ts: float
    tick: int
    candles: list
    spread: float
    tick_dir: int
    trading_allowed: bool
    # market_state node output
    market_view: dict          # structure, liquidation pools, funding, regime
    # research node output
    signal: Optional[Any]      # models.Signal
    hypothesis: Optional[dict]
    # risk gate output
    gate: Optional[dict]       # {approved, blockers, volume, scale}
    # execution output
    execution: Optional[dict]
    # observability
    trace: list[dict]          # [{node, verdict, detail}]
    outcome: str
