"""RiskEngine — the safety core (blueprint sections 1A, 2, 8).

Hard stops that cannot be overridden:
  · max daily loss      (RULE 5)
  · max weekly loss     (RULE 6)
  · max drawdown        (RULE 7 → emergency halt)
  · min account balance
  · max concurrent positions / per-symbol / per-currency exposure
  · R:R validation, hard SL requirement (RULES 2, 3)

Equity preservation ladder (RULE 10):
  DD ≥ 5%  → CAUTIOUS  (size × 0.50)
  DD ≥ 7%  → REDUCED   (size × 0.25)
  DD ≥ 10% → HALTED    (all trading stops until DD recovers < 7%)
"""
from __future__ import annotations

from collections import deque
from typing import Iterable

from ..config import AppConfig
from ..models import (
    AccountInfo,
    AlertLevel,
    Position,
    PreservationMode,
    RiskDecision,
    Signal,
    SymbolSpec,
)
from . import sizing

TICKS_PER_DAY = 1440  # one sim-minute per tick
DAYS_PER_WEEK = 5


def _ccys(symbol: str) -> tuple[str, str]:
    s = symbol.replace("/", "").upper()
    return (s[:3], s[-3:]) if len(s) >= 6 else (symbol, "")


class RiskEngine:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        rk = cfg.data["risk"]
        self.rk = rk
        self.start_balance = cfg.f("account", "starting_balance", default=100000.0)
        self.peak_equity = self.start_balance
        self.day_start_balance = self.start_balance
        self.week_start_balance = self.start_balance
        self.day_key: int = -1
        self.week_key: int = -1
        self.mode = PreservationMode.NORMAL
        self.daily_loss_halt = False
        self.weekly_loss_halt = False
        self.balance_halt = False
        self.margin_block = False
        self.emergency = False
        self.emergency_reason = ""
        self.last_equity = self.start_balance
        self.results: deque[float] = deque(maxlen=rk.get("rolling_window", 20) * 10)
        self.equity_curve: deque[tuple[float, float]] = deque(
            maxlen=cfg.i("engine", "equity_curve_points", default=720)
        )

    # ------------------------------------------------------------------ state
    def _roll_periods(self, tick: int) -> list[tuple]:
        events = []
        day = tick // TICKS_PER_DAY
        week = tick // (TICKS_PER_DAY * DAYS_PER_WEEK)
        if self.day_key == -1:
            self.day_key, self.week_key = day, week
        if day != self.day_key:
            self.day_key = day
            self.day_start_balance = self.last_equity
            if self.daily_loss_halt:
                self.daily_loss_halt = False
                events.append((AlertLevel.INFO, "DAY_ROLL", "New trading day — daily loss limit reset"))
        if week != self.week_key:
            self.week_key = week
            self.week_start_balance = self.last_equity
            if self.weekly_loss_halt:
                self.weekly_loss_halt = False
                events.append((AlertLevel.INFO, "WEEK_ROLL", "New trading week — weekly loss limit reset"))
        return events

    @property
    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.last_equity) / self.peak_equity * 100.0)

    @property
    def daily_loss_pct(self) -> float:
        return max(0.0, (self.day_start_balance - self.last_equity) /
                   max(self.day_start_balance, 1e-9) * 100.0)

    @property
    def weekly_loss_pct(self) -> float:
        return max(0.0, (self.week_start_balance - self.last_equity) /
                   max(self.week_start_balance, 1e-9) * 100.0)

    def update(self, tick: int, equity: float, ts: float) -> list[tuple]:
        """Feed equity each engine tick; returns (level, code, message) events."""
        events = self._roll_periods(tick)
        self.last_equity = equity
        self.equity_curve.append((ts, round(equity, 2)))
        if equity > self.peak_equity:
            self.peak_equity = equity

        rk = self.rk
        dd = self.drawdown_pct
        prev_mode = self.mode
        if dd >= rk["max_drawdown_pct"]:
            self.mode = PreservationMode.HALTED
        elif dd >= rk["dd_reduce_75_pct"]:
            self.mode = PreservationMode.REDUCED
        elif dd >= rk["dd_reduce_50_pct"]:
            self.mode = PreservationMode.CAUTIOUS
        else:
            self.mode = PreservationMode.NORMAL
        # HALTED needs equity to recover below the 75%-reduction tier to clear.
        if prev_mode is PreservationMode.HALTED and dd >= rk["dd_reduce_75_pct"]:
            self.mode = PreservationMode.HALTED

        if self.mode is not prev_mode:
            events.append((AlertLevel.CRITICAL if self.mode is PreservationMode.HALTED else AlertLevel.WARNING,
                           f"MODE_{self.mode.value}",
                           f"Equity preservation → {self.mode.value} (drawdown {dd:.2f}%)"))

        if equity < rk["min_account_balance"]:
            if not self.balance_halt:
                self.balance_halt = True
                events.append((AlertLevel.CRITICAL, "MIN_BALANCE",
                               f"Equity ${equity:,.0f} below minimum account balance "
                               f"${rk['min_account_balance']:,.0f} — trading halted"))
        elif self.balance_halt:
            self.balance_halt = False
            events.append((AlertLevel.INFO, "BALANCE_RESTORED", "Equity back above minimum balance"))

        if self.daily_loss_pct >= rk["max_daily_loss_pct"] and not self.daily_loss_halt:
            self.daily_loss_halt = True
            events.append((AlertLevel.CRITICAL, "DAILY_LOSS_LIMIT",
                           f"Daily loss {self.daily_loss_pct:.2f}% ≥ {rk['max_daily_loss_pct']}% "
                           "— no new trades until tomorrow"))
        if self.weekly_loss_pct >= rk["max_weekly_loss_pct"] and not self.weekly_loss_halt:
            self.weekly_loss_halt = True
            events.append((AlertLevel.CRITICAL, "WEEKLY_LOSS_LIMIT",
                           f"Weekly loss {self.weekly_loss_pct:.2f}% ≥ {rk['max_weekly_loss_pct']}% "
                           "— no new trades this week"))
        return events

    # ------------------------------------------------------------- sizing path
    def size_scale(self, volatility_scale: float = 1.0) -> tuple[float, list[str]]:
        """Multiplicative position scale from preservation tier + guards."""
        notes: list[str] = []
        if self.mode is PreservationMode.CAUTIOUS:
            scale, notes = 0.5, ["drawdown ≥5% — size halved (equity preservation)"]
        elif self.mode is PreservationMode.REDUCED:
            scale, notes = 0.25, ["drawdown ≥7% — size quartered (equity preservation)"]
        else:
            scale = 1.0

        n, wins, pf = self.rolling_stats()
        if n >= self.rk.get("rolling_window", 20):
            if wins < self.rk.get("min_win_rate_pct", 50.0) or pf < self.rk.get("min_profit_factor", 1.5):
                scale *= 0.75
                notes.append(f"rolling performance soft guard (win rate {wins:.0f}%, PF {pf:.2f})")
        return scale * volatility_scale, notes

    def risk_pct(self) -> tuple[float, list[str]]:
        """Effective % risk per trade (Kelly-blended when enabled)."""
        base = self.rk["risk_per_trade_pct"]
        notes: list[str] = []
        if self.rk.get("kelly_enabled"):
            n, wins, pf = self.rolling_stats()
            if n >= self.rk.get("kelly_min_trades", 20):
                aw, al = self.avg_win_loss()
                kelly = sizing.kelly_criterion_pct(wins, aw, al) * self.rk.get("kelly_fraction", 0.5)
                kelly = min(kelly, self.rk.get("kelly_cap_pct", 2.0))
                if kelly > 0:
                    notes.append(f"half-Kelly risk {kelly:.2f}% (base {base}%)")
                    return max(0.1, min(kelly, base)), notes
        return base, notes

    # --------------------------------------------------------------- validation
    def validate_trade(
        self,
        signal: Signal,
        account: AccountInfo,
        positions: Iterable[Position],
        spec: SymbolSpec,
        spread_price: float,
        vol_scale: float = 1.0,
    ) -> RiskDecision:
        """Full pre-trade gate. Returns approved volume + reasons."""
        blk: list[str] = []
        notes: list[str] = []
        positions = list(positions)
        rk = self.rk

        if self.emergency:
            blk.append(f"EMERGENCY STOP active ({self.emergency_reason})")
        if self.mode is PreservationMode.HALTED:
            blk.append("equity preservation HALTED (drawdown ≥10%)")
        if self.daily_loss_halt:
            blk.append("daily loss limit reached")
        if self.weekly_loss_halt:
            blk.append("weekly loss limit reached")
        if self.balance_halt:
            blk.append("equity below minimum account balance")
        if account.margin_level < rk["min_margin_level_pct"] and positions:
            blk.append(f"margin level {account.margin_level:.0f}% < {rk['min_margin_level_pct']}%")

        if len(positions) >= rk["max_positions"]:
            blk.append(f"max concurrent positions ({rk['max_positions']}) reached")
        same_sym = [p for p in positions if p.symbol == signal.symbol]
        if len(same_sym) >= rk["max_positions_per_symbol"]:
            blk.append(f"position already open on {signal.symbol}")

        # RULE 2: hard SL, RULE 3: R:R ≥ 1:2
        if signal.stop_loss <= 0 or signal.stop_loss == signal.entry:
            blk.append("signal has no hard stop loss (RULE 2)")
        rr = abs(signal.take_profit - signal.entry) / max(abs(signal.entry - signal.stop_loss), 1e-12)
        # ε tolerance: digit-rounding of entry/SL/TP can shift an exactly-built 2.0
        # ratio to 1.9998 — that is not a real RULE 3 violation
        if rr < rk["min_rr_ratio"] - 0.01:
            blk.append(f"R:R {rr:.3f} < {rk['min_rr_ratio']} (RULE 3)")

        # Liquidity verification: spread vs stop distance
        stop_dist = abs(signal.entry - signal.stop_loss)
        if stop_dist > 0 and spread_price / stop_dist * 100 > rk["max_spread_to_stop_pct"]:
            blk.append("spread too wide relative to stop (liquidity check)")

        # Correlation / currency exposure check
        exposure, problem = self._exposure_check(positions, signal)
        if problem:
            blk.append(f"correlation risk: {problem}")
        notes.extend(exposure)

        # Rolling performance guard — refuse to feed a losing regime
        n, wins, pf = self.rolling_stats()
        if n >= rk.get("rolling_window", 20) and pf < 1.0:
            blk.append(f"rolling profit factor {pf:.2f} < 1.0 — strategy underperformance")

        scale, scale_notes = self.size_scale(vol_scale)
        notes.extend(scale_notes)
        pct, kelly_notes = self.risk_pct()
        notes.extend(kelly_notes)

        raw = sizing.fixed_fractional_lots(
            account.balance, pct * scale * signal.size_hint, spec, signal.entry, signal.stop_loss
        )
        lots = sizing.round_lots(raw, rk["min_lot"], rk["max_lot"], rk["lot_step"])
        if 0 < raw and lots == 0:
            blk.append("sized volume below minimum lot")
        if raw <= 0:
            blk.append("invalid position size")

        if not blk:
            need = (signal.entry * spec.contract_size * lots * spec.quote_to_usd(signal.entry)
                    / max(account.equity * 0 + (self.cfg.i("account", "leverage", default=100)), 1))
            if need > account.free_margin:
                blk.append(f"insufficient free margin (need ${need:,.0f})")

        return RiskDecision(approved=not blk, volume_lots=lots if not blk else 0.0,
                            scale_factor=scale, blockers=blk, notes=notes)

    def _exposure_check(self, positions: list[Position], signal: Signal) -> tuple[list[str], str | None]:
        cap = self.rk.get("max_currency_exposure", 2)
        net: dict[str, int] = {}
        for p in positions:
            b, q = _ccys(p.symbol)
            net[b] = net.get(b, 0) + 1 * p.side.sign
            net[q] = net.get(q, 0) - 1 * p.side.sign
        b, q = _ccys(signal.symbol)
        net[b] = net.get(b, 0) + 1 * signal.side.sign
        net[q] = net.get(q, 0) - 1 * signal.side.sign
        offenders = [c for c, v in net.items() if abs(v) > cap]
        notes = [f"currency exposure {c}:{v:+d}" for c, v in net.items() if v]
        if offenders:
            return notes, f"net {offenders[0]} exposure would exceed {cap}"
        return notes, None

    # ------------------------------------------------------------- statistics
    def register_result(self, pnl: float) -> None:
        self.results.append(float(pnl))

    def rolling_stats(self) -> tuple[int, float, float]:
        n = len(self.results)
        if n == 0:
            return 0, 0.0, 0.0
        wins = [p for p in self.results if p > 0]
        losses = [p for p in self.results if p < 0]
        wr = len(wins) / n * 100.0
        gp = sum(wins)
        gl = abs(sum(losses))
        pf = (gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0)
        return n, wr, pf

    def avg_win_loss(self) -> tuple[float, float]:
        wins = [p for p in self.results if p > 0]
        losses = [p for p in self.results if p < 0]
        aw = sum(wins) / len(wins) if wins else 0.0
        al = abs(sum(losses) / len(losses)) if losses else 0.0
        return aw, al

    # ----------------------------------------------------------------- control
    def emergency_stop(self, reason: str) -> None:
        self.emergency = True
        self.emergency_reason = reason

    def resume(self) -> None:
        self.emergency = False
        self.emergency_reason = ""

    @property
    def trading_blocked(self) -> bool:
        return (self.emergency or self.mode is PreservationMode.HALTED
                or self.daily_loss_halt or self.weekly_loss_halt or self.balance_halt)

    def snapshot(self) -> dict:
        n, wr, pf = self.rolling_stats()
        return {
            "mode": self.mode.value,
            "drawdown_pct": round(self.drawdown_pct, 3),
            "daily_loss_pct": round(self.daily_loss_pct, 3),
            "weekly_loss_pct": round(self.weekly_loss_pct, 3),
            "peak_equity": round(self.peak_equity, 2),
            "daily_loss_halt": self.daily_loss_halt,
            "weekly_loss_halt": self.weekly_loss_halt,
            "balance_halt": self.balance_halt,
            "emergency": self.emergency,
            "emergency_reason": self.emergency_reason,
            "rolling_trades": n,
            "rolling_win_rate": round(wr, 1),
            "rolling_profit_factor": round(pf, 2) if pf != float("inf") else 999.0,
            "limits": {
                "max_daily_loss_pct": self.rk["max_daily_loss_pct"],
                "max_weekly_loss_pct": self.rk["max_weekly_loss_pct"],
                "max_drawdown_pct": self.rk["max_drawdown_pct"],
                "dd_reduce_50_pct": self.rk["dd_reduce_50_pct"],
                "dd_reduce_75_pct": self.rk["dd_reduce_75_pct"],
                "max_positions": self.rk["max_positions"],
                "min_rr_ratio": self.rk["min_rr_ratio"],
                "min_margin_level_pct": self.rk["min_margin_level_pct"],
                "risk_per_trade_pct": self.rk["risk_per_trade_pct"],
                "kelly_enabled": bool(self.rk.get("kelly_enabled")),
            },
            "equity_curve": [[t, e] for t, e in self.equity_curve],
        }
