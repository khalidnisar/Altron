"""TradingApplication — orchestrates the full trade flow (blueprint section 9):

1. MARKET ANALYSIS    (per closed candle, per symbol)
2. SIGNAL GENERATION  (confidence > 70%, regime, correlation)
3. RISK VALIDATION    (sizing, R:R, margin, limits)
4. ORDER EXECUTION    (entry + hard SL/TP)
5. POSITION MANAGEMENT (trailing, breakeven, partial TP, time stop)
6. TRADE CLOSURE      (metrics, stats, alerts, ML feedback)
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import asdict

from . import brokers
from .ai.signals import SignalEngine
from .brokers.base import Broker
from .config import AppConfig
from .execution.engine import ExecutionEngine
from .copier.copier import TradeCopier
from .graph.pipeline import TradingGraph
from .models import Candle, Deal
from .monitoring.alerts import AlertEngine
from .monitoring.metrics import compute_metrics
from .models import AlertLevel
from .risk.engine import RiskEngine

log = logging.getLogger("trading_app")


class TradingApplication:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.broker: Broker
        self.broker, self.broker_mode = brokers.create_broker(cfg)
        self.risk = RiskEngine(cfg)
        self.signals = SignalEngine(cfg)
        self.exec = ExecutionEngine(cfg, self.broker, self.risk)
        self.alerts = AlertEngine(cfg.i("alerts", "cooldown_minutes", default=60))
        self.trading_enabled = True
        self.tick_id = 0
        self.sim_minutes = cfg.i("engine", "sim_minutes_per_tick", default=1)
        self.ticks_per_candle = cfg.i("engine", "ticks_per_candle", default=15)
        self.hist_n = cfg.i("engine", "history_candles", default=240)
        self.base_ts = int(time.time())
        self.candles = {n: deque(maxlen=self.hist_n) for n in cfg.symbols}
        self.current: dict[str, dict] = {}
        self.started_at = time.time()
        self.errors: deque[str] = deque(maxlen=20)
        self.exec.on_deal = self._on_deal
        self.exec.on_block = self._on_block
        self.graph = TradingGraph(cfg, self.signals, self.risk, self.exec, self.broker)
        self.copier = TradeCopier(cfg, self.broker)
        self.copier.on_event = self._copier_event
        self.exec.on_position_opened = self.copier.on_master_open
        self._seed_history()

    # ---------------------------------------------------------------- helpers
    def _sim_ts(self, tick: int | None = None) -> float:
        return float(self.base_ts + (tick or self.tick_id) * 60 * self.sim_minutes)

    def _seed_history(self) -> None:
        """Pre-roll candles so indicators are warm at first paint."""
        warm = min(self.hist_n - 20, 180)
        for _ in range(warm * self.ticks_per_candle):
            self.tick_id += 1
            ts = self._sim_ts()
            dirs = self._advance_market(ts)
            self._aggregate(ts, dirs, record_only=True)

    def _advance_market(self, ts: float) -> dict[str, int]:
        step = getattr(self.broker, "step", None)
        if callable(step):
            return step(ts)
        dirs = {}
        for name in self.cfg.symbols:
            t = self.broker.tick(name)  # MT5: live tick read
            prev = self.current.get(name, {}).get("close", t.mid)
            dirs[name] = 1 if t.mid > prev else (-1 if t.mid < prev else 0)
        return dirs

    def _aggregate(self, ts: float, dirs: dict[str, int], record_only: bool = False) -> bool:
        """Roll ticks into candles; returns True when candles closed this tick."""
        closed = self.tick_id % self.ticks_per_candle == 0
        for name in self.cfg.symbols:
            tick = self.broker.tick(name)
            mid = tick.mid
            cur = self.current.get(name)
            if cur is None or (closed and cur is not None):
                if cur is not None:
                    spec = self.cfg.symbols[name]
                    self.candles[name].append(Candle(
                        symbol=name, ts=cur["ts"], open=spec.round_price(cur["open"]),
                        high=spec.round_price(cur["high"]), low=spec.round_price(cur["low"]),
                        close=spec.round_price(cur["close"]), volume=round(cur["volume"], 1)))
                cur = {"ts": ts, "open": mid, "high": mid, "low": mid, "close": mid, "volume": 0.0}
                self.current[name] = cur
            cur["high"] = max(cur["high"], mid)
            cur["low"] = min(cur["low"], mid)
            cur["close"] = mid
            cur["volume"] += 1.0 + abs(dirs.get(name, 0))
        return closed

    # --------------------------------------------------------------- stepping
    def step(self) -> None:
        self.tick_id += 1
        ts = self._sim_ts()
        try:
            dirs = self._advance_market(ts)
        except Exception as exc:  # broker/connection failure path (blueprint 1C)
            self.errors.append(f"{ts:.0f}: market step failed: {exc}")
            self.alerts.fire(ts, AlertLevel.CRITICAL, "CONNECTION_LOST",
                             f"Market data/order connection error: {exc}", force=True)
            return
        candle_closed = self._aggregate(ts, dirs)

        if candle_closed:
            self._analyze_all(ts, dirs)
        self.exec.manage_positions(ts, self._candle_ages(ts))

        try:
            acct = self.broker.account()
        except Exception as exc:
            self.errors.append(f"{ts:.0f}: account read failed: {exc}")
            return

        for level, code, msg in self.risk.update(self.tick_id, acct.equity, ts):
            self.alerts.fire(ts, level, code, msg, force=True)

        # Margin emergency: forced deleveraging below the reduce threshold
        lim = self.cfg.f("risk", "margin_reduce_pct", default=120.0)
        positions = self.broker.positions()
        if acct.margin_used > 0 and acct.margin_level < lim and positions:
            worst = max(positions, key=lambda p: self._pos_pnl(p))
            if self._pos_pnl(worst) < 0:
                try:
                    self.broker.close_position(worst.id, reason="EMERGENCY")
                    self.alerts.fire(ts, AlertLevel.CRITICAL, "MARGIN_REDUCE",
                                     f"Margin level {acct.margin_level:.0f}% — closed worst position "
                                     f"#{worst.id} {worst.symbol}", force=True)
                    self.exec._harvest_deals()
                except Exception as exc:
                    self.errors.append(f"{ts:.0f}: forced reduce failed: {exc}")

        self.alerts.evaluate(ts, {
            "account": acct, "risk": self.risk.snapshot(), "tick": self.tick_id,
            "connected": self.broker.connected(),
            "analyses": {s: a for s, a in self.signals.latest.items()},
            "upcoming_event": self.signals.sentiment.upcoming_event(self.tick_id),
        })
        # trade copier: replicate master trades to linked follower accounts
        try:
            self.copier.step(ts, acct.balance)
        except Exception as exc:
            self.errors.append(f"{ts:.0f}: copier step failed: {exc}")

    def _analyze_all(self, ts: float, dirs: dict[str, int]) -> None:
        """Run the LangGraph decision cycle per symbol on candle close."""
        allow = self.trading_enabled and not self.risk.trading_blocked
        for name in self.cfg.symbols:
            candles = list(self.candles[name])
            if len(candles) < 60:
                continue
            spread = self.broker.tick(name).spread
            try:
                self.graph.run_cycle(name, ts, self.tick_id, candles,
                                     spread, dirs.get(name, 0), allow)
            except Exception as exc:
                self.errors.append(f"{ts:.0f}: graph cycle failed for {name}: {exc}")

    def _candle_ages(self, ts: float) -> dict[str, float]:
        candle_s = self.ticks_per_candle * 60 * self.sim_minutes
        ages: dict[str, float] = {}
        for p in self.broker.positions():
            ages[p.symbol] = max(ages.get(p.symbol, 0.0), (ts - p.entry_ts) / candle_s)
        return ages

    def _pos_pnl(self, p) -> float:
        t = self.broker.tick(p.symbol)
        return p.floating_pnl(self.cfg.symbols[p.symbol], t.bid, t.ask)

    # ------------------------------------------------------------- callbacks
    def _on_deal(self, deal: Deal, ms) -> None:
        ts = self._sim_ts()
        # feed the learning & enhancement loop (graph side-car path)
        emitted = self.graph.learn_from_deal(deal, ms, ts)
        if emitted and self.graph.learning.lessons:
            lesson = self.graph.learning.lessons[0]
            self.alerts.fire(ts, AlertLevel.WARNING, f"LESSON_{self.graph.learning.deals_learned}",
                             f"🧠 LEARN: {lesson['message']}", force=True)
        if deal.pnl > 0:
            msg = f"WIN  +${deal.pnl:,.2f}  {deal.symbol} {deal.side.value} ({deal.reason})"
        else:
            msg = f"LOSS −${abs(deal.pnl):,.2f}  {deal.symbol} {deal.side.value} ({deal.reason})"
        level = AlertLevel.CRITICAL if deal.reason == "LIQUIDATED" else AlertLevel.INFO
        self.alerts.fire(ts, level, f"DEAL_{deal.id}", msg, force=True)

    def _copier_event(self, level, code, message) -> None:
        lvl = level if isinstance(level, AlertLevel) else AlertLevel(str(level))
        self.alerts.fire(self._sim_ts(), lvl, code, message, force=True)

    def _on_block(self, signal, decision) -> None:
        ts = self._sim_ts()
        joined = "; ".join(decision.blockers[:2])
        if any("margin" in b or "EMERGENCY" in b or "HALT" in b.upper() for b in decision.blockers):
            self.alerts.fire(ts, AlertLevel.WARNING, f"BLOCK_{signal.symbol}",
                             f"{signal.symbol} {signal.side.value} blocked: {joined}", symbol=signal.symbol)

    # ---------------------------------------------------------------- control
    def pause_trading(self) -> None:
        self.trading_enabled = False

    def resume_trading(self) -> None:
        self.trading_enabled = True
        self.risk.resume()

    def emergency_stop(self, reason: str = "operator") -> int:
        self.trading_enabled = False
        self.risk.emergency_stop(reason)
        n = self.exec.close_all("EMERGENCY")
        self.alerts.fire(self._sim_ts(), AlertLevel.CRITICAL, "EMERGENCY_STOP",
                         f"Emergency stop ({reason}) — closed {n} position(s), trading disabled",
                         force=True)
        return n

    # --------------------------------------------------------------- snapshot
    def snapshot(self) -> dict:
        acct = self.broker.account()
        positions = []
        for p in self.broker.positions():
            spec = self.cfg.symbols[p.symbol]
            t = self.broker.tick(p.symbol)
            ms = self.exec.managed.get(p.id)
            base_sl = ms.initial_sl if ms else p.stop_loss
            r_dist = abs(p.entry_price - base_sl) or 1e-12
            exit_px = t.bid if p.side.value == "BUY" else t.ask
            pnl_r = ((exit_px - p.entry_price) * (1 if p.side.value == "BUY" else -1)) / r_dist
            liq_fn = getattr(self.broker, "liquidation_price", None)
            positions.append({
                "id": p.id, "symbol": p.symbol, "side": p.side.value, "volume": p.volume,
                "entry": p.entry_price, "entry_ts": p.entry_ts, "sl": p.stop_loss,
                "tp": p.take_profit, "floating_pnl": round(self._pos_pnl(p), 2),
                "pnl_r": round(pnl_r, 2), "bid": t.bid, "ask": t.ask,
                "liq_price": liq_fn(p) if callable(liq_fn) else None,
                "initial_volume": ms.initial_volume if ms else p.volume,
                "levels_done": sorted(ms.levels_done) if ms else [],
                "breakeven": ms.breakeven_moved if ms else False,
            })
        risk_snap = self.risk.snapshot()
        exec_snap = self.exec.snapshot()
        event = self.signals.sentiment.upcoming_event(self.tick_id, within_min=240)
        blackout = self.signals.sentiment.blackout_active(self.tick_id)
        candles_out = {}
        for name, dq in self.candles.items():
            candles_out[name] = [
                {"ts": c.ts, "o": c.open, "h": c.high, "l": c.low, "c": c.close, "v": c.volume}
                for c in list(dq)[-160:]
            ]
        metrics = compute_metrics(exec_snap["deals"], risk_snap["equity_curve"],
                                  self.risk.start_balance)
        return {
            "engine": {
                "trading_enabled": self.trading_enabled,
                "broker_mode": self.broker_mode,
                "connected": self.broker.connected(),
                "tick": self.tick_id,
                "sim_ts": self._sim_ts(),
                "candle_minutes": self.ticks_per_candle,
                "uptime_s": round(time.time() - self.started_at, 1),
                "errors": list(self.errors)[-5:],
            },
            "account": asdict(acct),
            "positions": positions,
            "risk": risk_snap,
            "analyses": {s: asdict(a) for s, a in self.signals.latest.items()},
            "recent_signals": exec_snap["recent_signals"],
            "deals": exec_snap["deals"],
            "metrics": metrics,
            "alerts": self.alerts.snapshot()[:40],
            "candles": candles_out,
            "symbols": {
                n: {"bid": self.broker.tick(n).bid, "ask": self.broker.tick(n).ask,
                    "spread_pips": round(self.broker.tick(n).spread / self.cfg.symbols[n].pip, 1)}
                for n in self.cfg.symbols
            },
            "ml": self.signals.model.snapshot(),
            "graph": self.graph.snapshot(),
            "copier": self.copier.snapshot(),
            "calendar": {
                "blackout": blackout, "next_event": event,
                "events_today": self.signals.sentiment.events_today(self.tick_id),
            },
        }

    # ------------------------------------------------------------------- loop
    async def run_forever(self, on_update=None) -> None:
        interval = self.cfg.f("engine", "tick_interval_seconds", default=0.5)
        while True:
            try:
                self.step()
            except Exception as exc:  # never let the loop die
                log.exception("engine step failed")
                self.errors.append(f"engine step: {exc}")
            if on_update is not None:
                try:
                    await on_update()
                except Exception:
                    log.exception("broadcast failed")
            await asyncio.sleep(interval)
