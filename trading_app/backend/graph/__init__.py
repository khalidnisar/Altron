"""Agent graph orchestration (LangGraph).

Graph topology (per closed candle, per symbol):

    market_state ──► research ──┬─► risk_gate ──┬─► execution ──► END
        │                       │               │
     structure/MTF/liq/         └─► END         └─► learning ──► END
     funding/regime            (no setup)      (rejected ⇒ feedback)

Plus an event-driven learning loop: every closed deal feeds
learn_from_deal() which updates the ML model, per-strategy circuit
breakers, and the adaptive confidence threshold (self-fixing).
"""
from .pipeline import TradingGraph
from .nodes import LearningEngine

__all__ = ["TradingGraph", "LearningEngine"]
