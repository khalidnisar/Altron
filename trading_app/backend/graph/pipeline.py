"""TradingGraph — LangGraph StateGraph orchestrating one decision cycle.

        START
          ▼
    ┌─────────────┐   structure, multi-TF, liq pools, funding, regime
    │ market_state│
    └──────┬──────┘
           ▼
    ┌─────────────┐   confluence hypothesis, ML, RULE-12 HTF guard,
    │   research  │   adaptive threshold, strategy circuit-breaker gate
    └──────┬──────┘
           │ conditional
     setup ┴ no setup
     ▼          └────────────► END (trace: NO_SETUP)
┌───────────┐  risk sizing, hard limits, correlation, RR, margin
│ risk_gate │
└─────┬─────┘
      │ conditional
 pass ┴ fail
 ▼     └────────────► ┌──────────┐    feedback   ┌────────► END
┌──────────┐         │ learning │ ──────────────►│
│execution │         └──────────┘                └ learn_from_deal()
└────┬─────┘                               (called on every closed deal)
     ▼
    END

Every run leaves a node-by-node trace surfaced in the dashboard.
"""
from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from ..ai import sessions, structure as struct
from ..ai.flow import FlowEngine
from ..ai.signals import SignalEngine
from ..brokers.base import Broker, BrokerError
from ..config import AppConfig
from ..execution.engine import ExecutionEngine
from ..models import Signal
from ..risk.engine import RiskEngine
from .nodes import LearningEngine
from .state import GraphState

log = logging.getLogger("trading_app.graph")

NO_SETUP = "no_setup"
SETUP = "setup"
PASS = "pass"
FAIL = "fail"


class TradingGraph:
    def __init__(self, cfg: AppConfig, signals: SignalEngine, risk: RiskEngine,
                 execution: ExecutionEngine, broker: Broker):
        self.cfg = cfg
        self.signals = signals
        self.risk = risk
        self.exec = execution
        self.broker = broker
        self.learning = LearningEngine(cfg.get("lifecycle", default={}) or {})
        self.flow = FlowEngine()
        self.market_views: dict[str, dict] = {}
        self.last_runs: dict[str, dict] = {}        # symbol → {ts, outcome, trace}

        builder = StateGraph(GraphState)
        builder.add_node("market_state", self.market_state_node)
        builder.add_node("research", self.research_node)
        builder.add_node("risk_gate", self.risk_gate_node)
        builder.add_node("execution", self.execution_node)
        builder.add_node("learning", self.learning_node)
        builder.set_entry_point("market_state")
        builder.add_edge("market_state", "research")
        builder.add_conditional_edges("research", self._route_research,
                                      {SETUP: "risk_gate", NO_SETUP: END})
        builder.add_conditional_edges("risk_gate", self._route_gate,
                                      {PASS: "execution", FAIL: "learning"})
        builder.add_edge("execution", END)
        builder.add_edge("learning", END)
        self.graph = builder.compile()

    # ------------------------------------------------------------ run cycle
    def run_cycle(self, symbol: str, ts: float, tick: int, candles: list,
                  spread: float, tick_dir: int, trading_allowed: bool) -> dict:
        init: GraphState = {
            "symbol": symbol, "ts": ts, "tick": tick, "candles": candles,
            "spread": spread, "tick_dir": tick_dir,
            "trading_allowed": trading_allowed, "trace": [],
        }
        try:
            final = self.graph.invoke(init)
        except Exception as exc:                     # the graph must never crash the loop
            log.exception("graph cycle failed for %s", symbol)
            trace = init["trace"] + [{"node": "graph", "verdict": "ERROR", "detail": str(exc)}]
            final = {"trace": trace, "outcome": "ERROR"}
        self.last_runs[symbol] = {
            "ts": ts, "outcome": final.get("outcome", "?"), "trace": final.get("trace", []),
        }
        return final

    # -------------------------------------------------- external signal path
    def execute_external(self, sig: Signal, candles: list, spread: float,
                         ts: float, trading_allowed: bool) -> dict:
        """Bridge payloads enter here (external.py) — always through the
        SAME risk_gate / execution / learning nodes as internal signals."""
        symbol = sig.symbol
        # refresh market view so the dashboard + gates see current structure
        mv_state = self.market_state_node({"symbol": symbol, "candles": candles, "trace": []})
        state: GraphState = {
            "symbol": symbol, "ts": ts, "tick": 0, "candles": candles,
            "spread": spread, "tick_dir": 0, "trading_allowed": trading_allowed,
            "market_view": mv_state["market_view"],
            "signal": sig,
            "trace": [{"node": "external", "verdict": "RECV",
                       "detail": "; ".join(sig.reasons)}],
        }
        state.update(self.risk_gate_node(state))
        if state["gate"]["approved"]:
            state.update(self.execution_node(state))
        else:
            state.update(self.learning_node(state))
        self.last_runs[symbol] = {"ts": ts, "outcome": state.get("outcome", "?"),
                                  "trace": state["trace"]}
        return {"outcome": state.get("outcome"), "trace": state["trace"],
                "gate": state.get("gate"), "execution": state.get("execution")}

    # ------------------------------------------------------------- the nodes
    def market_state_node(self, state: GraphState) -> dict:
        symbol = state["symbol"]
        candles = state["candles"]
        tf = struct.multi_tf(candles, symbol)
        pools = struct.liquidation_pools(candles)
        funding = float(getattr(self.broker, "funding_rate", lambda s: 0.0)(symbol))
        flow = self.flow.analyze(symbol, candles)     # directional-flow diagnostics
        session = sessions.classify(state.get("ts") or candles[-1].ts)
        view = {
            "structure": tf, "liquidation_pools": pools, "funding_rate": funding,
            "flow": flow, "session": session,
        }
        self.market_views[symbol] = view
        s = tf["timeframes"]
        detail = (f"M15 {s['M15']['direction']} · H1 {s['H1']['direction']} · "
                  f"H4 {s['H4']['direction']} | align {tf['alignment']:+.1f} | "
                  f"TIS {flow['tis']:.0f} EXH {flow['exhaustion']:.0f} | "
                  f"{session['label']} session | funding {funding * 100:+.3f}% | "
                  f"{len(pools['above'])} liq above / {len(pools['below'])} below")
        if s["M15"].get("bos"):
            detail += f" | {s['M15']['bos']}"
        if s["M15"].get("choch"):
            detail += f" | {s['M15']['choch']}"
        return {"market_view": view,
                "trace": state["trace"] + [{"node": "market_state", "verdict": "OK", "detail": detail}]}

    def research_node(self, state: GraphState) -> dict:
        symbol = state["symbol"]
        spec = self.cfg.symbols[symbol]
        sig, analysis = self.signals.analyze(
            symbol, spec, state["candles"], state["tick"], state["spread"],
            state["tick_dir"], allow=True)
        trace = state["trace"]
        mv = state["market_view"]
        flow = mv["flow"]
        analysis.tis = flow["tis"]
        analysis.exhaustion = flow["exhaustion"]

        if sig is None:
            return {"signal": None, "outcome": "NO_SETUP",
                    "trace": trace + [{"node": "research", "verdict": "SKIP",
                                       "detail": "no setup (confidence/confluence/regime gates)"}]}

        # strategy circuit breaker (learning loop feedback input)
        allowed, why = self.learning.strategy_allowed(sig.strategy, state["ts"])
        if not allowed:
            self.learning.record_block("strategy_circuit_breaker")
            return {"signal": None, "outcome": "NO_SETUP",
                    "trace": trace + [{"node": "research", "verdict": "GATED",
                                       "detail": why}]}

        # RULE 12: no trades against the major HTF trend without heavy confluence
        htf = mv["structure"]["htf_direction"]
        counter = ((htf.startswith("UP") and sig.side.value == "SELL") or
                   (htf.startswith("DOWN") and sig.side.value == "BUY"))
        if counter and (sig.confluence < 4 or sig.confidence < 78):
            self.learning.record_block("rule12_counter_htf")
            return {"signal": None, "outcome": "NO_SETUP",
                    "trace": trace + [{"node": "research", "verdict": "BLOCKED",
                                       "detail": f"RULE 12: {sig.side.value} vs HTF {htf} "
                                                 f"needs confluence ≥4 & conf ≥78"}]}

        # adaptive confidence threshold (self-tuning) + asset personality bias
        eff_min = (self.learning.effective_min_conf(self.cfg.f("risk", "min_confidence", default=70.0))
                   + flow["personality"]["confidence_bias"])
        if sig.confidence < eff_min:
            self.learning.record_block("adaptive_threshold")
            return {"signal": None, "outcome": "NO_SETUP",
                    "trace": trace + [{"node": "research", "verdict": "BLOCKED",
                                       "detail": f"conf {sig.confidence:.0f} < adaptive min {eff_min:.0f} "
                                                 f"(vol-ratio {flow['personality']['vol_ratio']})"}]}

        # Directional-flow gates (trend integrity / exhaustion)
        with_trend = (flow["trend_dir"] > 0 and sig.side.value == "BUY") or \
                     (flow["trend_dir"] < 0 and sig.side.value == "SELL")
        if flow["exhaustion"] >= 75 and with_trend and sig.confluence < 4:
            self.learning.record_block("trend_exhaustion")
            return {"signal": None, "outcome": "NO_SETUP",
                    "trace": trace + [{"node": "research", "verdict": "BLOCKED",
                                       "detail": f"trend exhaustion {flow['exhaustion']:.0f} — "
                                                 f"weakening heartbeat, entry vetoed"}]}
        boosted = False
        if with_trend and flow["tis"] >= 70 and flow["exhaustion"] < 60:
            # strong, healthy trend: reward integrity with a bounded confidence lift
            boost = min(5.0, (flow["tis"] - 70.0) / 6.0)
            if boost > 0.5:
                sig.confidence = round(sig.confidence + boost, 1)
                boosted = True

        # lifecycle staging (Sword lifecycle plane): incubation/probation trade smaller
        stage = self.learning.stage_of(sig.strategy)
        life_scale = self.learning.size_scale(sig.strategy)
        sess_factor = sessions.size_factor(state["ts"])
        applied_scale = life_scale * sess_factor
        if applied_scale < 1.0:
            sig.size_hint = round(sig.size_hint * applied_scale, 3)
        tags = []
        if stage != "ACTIVE":
            tags.append(f"lifecycle:{stage} ×{life_scale}")
        if sess_factor < 1.0:
            tags.append(f"session ×{sess_factor}")

        thesis = (f"{sig.strategy} {sig.side.value} {symbol}: conf {sig.confidence:.0f}"
                  f"{' ↑TIS-boost' if boosted else ''} "
                  f"(T{sig.technical:.0f}/ML{sig.ml:.0f}/S{sig.sentiment:.0f}/M{sig.microstructure:.0f}) "
                  f"TIS {flow['tis']:.0f} EXH {flow['exhaustion']:.0f} "
                  f"HTF {htf} funding {mv['funding_rate'] * 100:+.3f}%"
                  f"{' [' + '; '.join(tags) + ']' if tags else ''}")
        hypothesis = {"thesis": thesis, "direction": sig.side.value}
        return {"signal": sig, "hypothesis": hypothesis,
                "trace": trace + [{"node": "research", "verdict": "SETUP",
                                   "detail": thesis}]}

    def risk_gate_node(self, state: GraphState) -> dict:
        sig: Signal = state["signal"]
        spec = self.cfg.symbols[state["symbol"]]
        account = self.broker.account()
        decision = self.risk.validate_trade(sig, account, self.broker.positions(),
                                            spec, state["spread"], 1.0)
        blockers = list(decision.blockers)
        if not state.get("trading_allowed", True) and "trading disabled" not in blockers:
            blockers.append("trading disabled / emergency halt")
        gate = {"approved": not blockers, "blockers": blockers,
                "volume": decision.volume_lots, "scale": decision.scale_factor}
        verdict = "PASS" if gate["approved"] else "FAIL"
        detail = (f"size {decision.volume_lots:.2f} lot · scale {decision.scale_factor:.2f}"
                  if gate["approved"] else "; ".join(blockers[:2]))
        return {"gate": gate,
                "trace": state["trace"] + [{"node": "risk_gate", "verdict": verdict, "detail": detail}]}

    def execution_node(self, state: GraphState) -> dict:
        sig: Signal = state["signal"]
        gate = state["gate"]
        try:
            pos = self.exec.open_position(sig, gate["volume"], state["candles"])
            result = {"position_id": pos.id, "entry": pos.entry_price,
                      "sl": pos.stop_loss, "tp": pos.take_profit, "volume": pos.volume}
            verdict, detail = "FILLED", f"#{pos.id} @ {pos.entry_price} SL {pos.stop_loss} TP {pos.take_profit}"
            outcome = "EXECUTED"
        except BrokerError as exc:
            self.exec.record_signal(sig, False, 0.0, [f"broker: {exc}"], [])
            self.learning.record_block("broker_rejection")
            result = {"error": str(exc)}
            verdict, detail, outcome = "REJECTED", str(exc), "BROKER_REJECTED"
        return {"execution": result, "outcome": outcome,
                "trace": state["trace"] + [{"node": "execution", "verdict": verdict, "detail": detail}]}

    def learning_node(self, state: GraphState) -> dict:
        gate = state.get("gate") or {}
        for b in gate.get("blockers", [])[:3]:
            self.learning.record_block(b[:64])
        detail = ("rejection logged for the learning loop — block reasons feed "
                  "threshold/strategy tuning")
        return {"outcome": "GATE_REJECTED",
                "trace": state["trace"] + [{"node": "learning", "verdict": "LOGGED", "detail": detail}]}

    # ------------------------------------------------------------- routing
    @staticmethod
    def _route_research(state: GraphState) -> str:
        return SETUP if state.get("signal") is not None else NO_SETUP

    @staticmethod
    def _route_gate(state: GraphState) -> str:
        return PASS if (state.get("gate") or {}).get("approved") else FAIL

    # ------------------------------------------------- event-driven learning
    def learn_from_deal(self, deal, managed, ts: float) -> list[str]:
        strategy = getattr(managed, "strategy", None) or "UNKNOWN"
        if strategy == "UNKNOWN":
            # fallback: recover the originating strategy from the signal ledger
            for rec in self.exec.recent_signals:
                if rec.get("position_id") == deal.position_id:
                    strategy = rec.get("strategy", "UNKNOWN")
                    break
        return self.learning.learn_from_deal(deal, managed, self.signals.model, strategy, ts)

    # --------------------------------------------------------------- snapshot
    def snapshot(self) -> dict:
        return {
            "last_runs": self.last_runs,
            "market_views": self.market_views,
            "learning": self.learning.snapshot(),
        }
