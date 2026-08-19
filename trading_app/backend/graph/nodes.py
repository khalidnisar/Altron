"""LearningEngine — the self-learning & self-fixing component.

Three adaptive mechanisms, all persisted into `lessons` for the dashboard:

1. **Online model learning** — every closed deal refits the ML ensemble
   (supervised: did price actually go up from the entry features?).
2. **Strategy circuit breakers** — a strategy whose rolling profit factor
   over its last N trades collapses (< 0.8) is automatically suspended for
   a cooldown window; the suspension and re-enable both emit lessons.
3. **Adaptive confidence threshold** — recent poor aggregate performance
   tightens the entry threshold (70 → 72/75), strong performance eases it
   (bounded ±5). Liquidations additionally force the tightest setting.
"""
from __future__ import annotations

from collections import deque
from typing import Any


STAGES = ("INCUBATION", "ACTIVE", "PROBATION", "SUSPENDED")

# Versioned lifecycle thresholds (Altron-Sword promotion-gates pattern:
# constants live in one place, promotion is strictly easier than re-entry).
LC_DEFAULTS = {
    "min_trades_promote": 12,     # INCUBATION → ACTIVE gate
    "promote_pf": 1.05,
    "promote_wr_pct": 45.0,
    "probation_pf": 0.8,          # ACTIVE → PROBATION
    "recover_pf": 1.05,           # PROBATION → ACTIVE
    "suspend_pf": 0.5,            # PROBATION → SUSPENDED
    "incubation_fail_pf": 0.6,    # INCUBATION → SUSPENDED fast-fail
    "max_consec_losses": 5,
    "incubation_scale": 0.5,      # reduced size while unproven
    "probation_scale": 0.5,
}


class LearningEngine:
    STRATEGY_WINDOW = 15
    BREAKER_MIN_TRADES = 8
    BREAKER_PF = 0.8
    BREAKER_COOLDOWN_S = 6 * 3600          # 6 sim-hours
    OVERALL_WINDOW = 20

    def __init__(self, lifecycle_cfg: dict | None = None):
        self.strategy_pnl: dict[str, deque] = {}
        self.overall_pnl: deque[float] = deque(maxlen=self.OVERALL_WINDOW)
        self.gates: dict[str, float] = {}            # strategy → resume_ts
        self.threshold_delta = 0.0                    # added to min confidence
        self.lessons: deque[dict] = deque(maxlen=80)  # [{ts, kind, message}]
        self.block_counts: dict[str, int] = {}
        self.deals_learned = 0
        self.liquidations_seen = 0
        # ── strategy lifecycle (ported pattern from Altron-Sword lifecycle plane)
        self.lc = {**LC_DEFAULTS, **(lifecycle_cfg or {})}
        self.stages: dict[str, str] = {}             # strategy → STAGES entry
        self.consec_losses: dict[str, int] = {}

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _pf(pnls: list[float]) -> float:
        gp = sum(p for p in pnls if p > 0)
        gl = abs(sum(p for p in pnls if p < 0))
        return gp / gl if gl > 0 else (10.0 if gp > 0 else 0.0)

    def _lesson(self, ts: float, kind: str, message: str) -> None:
        self.lessons.appendleft({"ts": ts, "kind": kind, "message": message})

    # ----------------------------------------------------------- gating API
    def strategy_allowed(self, strategy: str, ts: float) -> tuple[bool, str]:
        resume = self.gates.get(strategy)
        if resume is None:
            return True, ""
        if ts >= resume:
            del self.gates[strategy]
            self.stages[strategy] = "INCUBATION"     # re-enter via incubation (revalidation)
            self._lesson(ts, "auto-fix",
                         f"{strategy} re-enabled after cooldown → back to INCUBATION "
                         f"(reduced size until re-validated)")
            self.threshold_delta = max(-5.0, self.threshold_delta - 1.0)
            return True, ""
        return False, f"{strategy} suspended by learning loop until ts {resume:.0f}"

    # ---------------------------------------------------------------- stages
    def stage_of(self, strategy: str) -> str:
        return self.stages.get(strategy, "INCUBATION")

    def size_scale(self, strategy: str) -> float:
        stage = self.stage_of(strategy)
        if stage == "ACTIVE":
            return 1.0
        if stage == "PROBATION":
            return self.lc["probation_scale"]
        if stage == "SUSPENDED":
            return 0.0
        return self.lc["incubation_scale"]

    def _wr(self, pnls: list[float]) -> float:
        if not pnls:
            return 0.0
        return sum(1 for p in pnls if p > 0) / len(pnls) * 100.0

    def _lifecycle_update(self, strategy: str, ts: float) -> None:
        lc = self.lc
        bucket = list(self.strategy_pnl.get(strategy, ()))
        n = len(bucket)
        pf = self._pf(bucket) if bucket else 0.0
        wr = self._wr(bucket)
        losses = self.consec_losses.get(strategy, 0)
        stage = self.stage_of(strategy)

        if losses >= lc["max_consec_losses"] and stage not in ("SUSPENDED",):
            self.stages[strategy] = "SUSPENDED"
            self.gates[strategy] = ts + self.BREAKER_COOLDOWN_S
            self._lesson(ts, "auto-fix",
                         f"LIFECYCLE: {strategy} {stage}→SUSPENDED ({losses} consecutive losses)")
            return
        if stage == "SUSPENDED":
            return
        if stage == "INCUBATION":
            if n >= 8 and pf < lc["incubation_fail_pf"]:
                self.stages[strategy] = "SUSPENDED"
                self.gates[strategy] = ts + self.BREAKER_COOLDOWN_S
                self._lesson(ts, "auto-fix",
                             f"LIFECYCLE: {strategy} failed incubation (PF {pf:.2f} < "
                             f"{lc['incubation_fail_pf']}) → SUSPENDED 6h")
            elif n >= lc["min_trades_promote"] and pf >= lc["promote_pf"] and wr >= lc["promote_wr_pct"]:
                self.stages[strategy] = "ACTIVE"
                self._lesson(ts, "auto-fix",
                             f"LIFECYCLE: {strategy} INCUBATION→ACTIVE "
                             f"(promotion gate passed: {n} trades, PF {pf:.2f}, WR {wr:.0f}%) — full size")
        elif stage == "ACTIVE":
            if n >= self.BREAKER_MIN_TRADES and pf < lc["probation_pf"]:
                self.stages[strategy] = "PROBATION"
                self._lesson(ts, "auto-fix",
                             f"LIFECYCLE: {strategy} ACTIVE→PROBATION (PF {pf:.2f} < "
                             f"{lc['probation_pf']}) — size ×{lc['probation_scale']}")
        elif stage == "PROBATION":
            if pf >= lc["recover_pf"]:
                self.stages[strategy] = "ACTIVE"
                self._lesson(ts, "auto-fix",
                             f"LIFECYCLE: {strategy} PROBATION→ACTIVE (PF recovered to {pf:.2f})")
            elif pf < lc["suspend_pf"]:
                self.stages[strategy] = "SUSPENDED"
                self.gates[strategy] = ts + self.BREAKER_COOLDOWN_S
                self._lesson(ts, "auto-fix",
                             f"LIFECYCLE: {strategy} PROBATION→SUSPENDED (PF {pf:.2f} < "
                             f"{lc['suspend_pf']})")

    def effective_min_conf(self, base: float) -> float:
        return base + self.threshold_delta

    # -------------------------------------------------------------- learning
    def learn_from_deal(self, deal: Any, managed: Any, model: Any, strategy: str,
                        ts: float) -> list[str]:
        """Called for every closed deal. Returns emitted lesson messages."""
        emitted: list[str] = []
        # 1) online ML update
        if managed is not None and getattr(managed, "features_candles", None):
            model.learn(managed.features_candles, deal.exit_price > deal.entry_price)
        self.deals_learned += 1

        # liquidation capture
        if deal.reason == "LIQUIDATED":
            self.liquidations_seen += 1
            self.threshold_delta = min(5.0, self.threshold_delta + 1.5)
            self._lesson(ts, "liquidation",
                         f"LIQUIDATION captured on {deal.symbol} #{deal.position_id} "
                         f"(${deal.pnl:,.2f}) — confidence threshold tightened to prevent recurrence")
            emitted.append("liquidation")
        self.strategy_pnl.setdefault(strategy or "UNKNOWN", deque(maxlen=self.STRATEGY_WINDOW)).append(deal.pnl)
        self.overall_pnl.append(deal.pnl)
        key = strategy or "UNKNOWN"
        self.consec_losses[key] = self.consec_losses.get(key, 0) + 1 if deal.pnl <= 0 else 0
        self._lifecycle_update(key, ts)

        # 2) strategy circuit breaker
        bucket = list(self.strategy_pnl[strategy or "UNKNOWN"])
        if len(bucket) >= self.BREAKER_MIN_TRADES and (strategy or "UNKNOWN") not in self.gates:
            pf = self._pf(bucket)
            if pf < self.BREAKER_PF:
                self.gates[strategy or "UNKNOWN"] = ts + self.BREAKER_COOLDOWN_S
                self._lesson(ts, "auto-fix",
                             f"Strategy circuit breaker: {strategy} PF {pf:.2f} < {self.BREAKER_PF} "
                             f"over last {len(bucket)} trades → suspended 6h")
                emitted.append("breaker")

        # 3) adaptive confidence threshold (bounded ±5)
        overall = list(self.overall_pnl)
        if len(overall) >= 10:
            pf = self._pf(overall)
            if pf < 1.0 and self.threshold_delta < 5.0:
                self.threshold_delta = min(5.0, self.threshold_delta + 1.0)
                self._lesson(ts, "auto-fix",
                             f"Rolling PF {pf:.2f} < 1.0 — confidence threshold tightened "
                             f"(+{self.threshold_delta:.0f})")
                emitted.append("tighten")
            elif pf > 2.0 and self.threshold_delta > -5.0:
                self.threshold_delta = max(-5.0, self.threshold_delta - 1.0)
                self._lesson(ts, "auto-fix",
                             f"Rolling PF {pf:.2f} > 2.0 — confidence threshold eased "
                             f"({self.threshold_delta:+.0f})")
                emitted.append("ease")
        return emitted

    def record_block(self, reason: str) -> None:
        self.block_counts[reason] = self.block_counts.get(reason, 0) + 1

    def snapshot(self) -> dict:
        now_gates = {k: v for k, v in self.gates.items()}
        return {
            "deals_learned": self.deals_learned,
            "liquidations_seen": self.liquidations_seen,
            "threshold_delta": round(self.threshold_delta, 1),
            "gates": now_gates,
            "strategy_stats": {
                s: {"trades": len(list(p)), "pf": round(self._pf(list(p)), 2),
                    "wr": round(self._wr(list(p)), 1), "stage": self.stage_of(s),
                    "consec_losses": self.consec_losses.get(s, 0)}
                for s, p in self.strategy_pnl.items()
            },
            "block_counts": self.block_counts,
            "lessons": list(self.lessons)[:25],
        }
