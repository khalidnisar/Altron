"""ExecutionEngine — order placement and live position management (blueprint 1D).

Pre-trade:   risk validation flows from RiskEngine before any order.
Management:  multi-level partial TPs (25/50/75/100% of TP distance),
             breakeven protection, ATR trailing stops, time-based stops.
Post-trade:  deal ledger, ML feedback, risk-engine result registration.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

from ..brokers.base import Broker, BrokerError
from ..config import AppConfig
from ..models import Deal, Position, RiskDecision, Side, Signal
from ..risk import stops as st
from ..risk.engine import RiskEngine

log = logging.getLogger("trading_app.execution")


@dataclass
class ManagedState:
    position_id: int
    symbol: str
    side: Side
    entry: float
    initial_sl: float
    initial_tp: float
    atr: float
    initial_volume: float
    entry_candle: float
    strategy: str = "UNKNOWN"
    levels_done: set[int] = field(default_factory=set)
    breakeven_moved: bool = False
    features_candles: list = field(default_factory=list)   # candle snapshot for ML learning


class ExecutionEngine:
    def __init__(self, cfg: AppConfig, broker: Broker, risk: RiskEngine):
        self.cfg = cfg
        self.broker = broker
        self.risk = risk
        self.rk = cfg.data["risk"]
        self.managed: dict[int, ManagedState] = {}
        self.deals: deque[Deal] = deque(maxlen=500)
        self.recent_signals: deque[dict] = deque(maxlen=50)
        self._seen_deal_ids: set[int] = set()
        self.on_deal = None        # callback(deal, ManagedState | None)
        self.on_block = None       # callback(signal, RiskDecision)
        self.on_position_opened = None  # callback(position, balance) — trade copier hook

    # ------------------------------------------------------------ pre-trade
    def record_signal(self, signal: Signal, approved: bool, volume: float,
                      blockers: list[str], notes: list[str]) -> dict:
        record = {
            "ts": signal.ts, "symbol": signal.symbol, "side": signal.side.value,
            "confidence": signal.confidence, "confluence": signal.confluence,
            "strategy": signal.strategy, "approved": approved,
            "volume": volume, "blockers": blockers,
            "notes": notes, "regime": signal.regime,
        }
        self.recent_signals.appendleft(record)
        return record

    def open_position(self, signal: Signal, volume: float,
                      current_candles: list) -> Position:
        """Place the order with broker + register managed state.
        Only call AFTER the risk gate has approved."""
        pos = self.broker.market_order(signal.symbol, signal.side, volume,
                                       signal.stop_loss, signal.take_profit)
        pos.entry_ts = signal.ts
        self.managed[pos.id] = ManagedState(
            position_id=pos.id, symbol=pos.symbol, side=pos.side, entry=pos.entry_price,
            initial_sl=pos.stop_loss, initial_tp=pos.take_profit, atr=signal.atr,
            initial_volume=pos.volume, entry_candle=signal.ts, strategy=signal.strategy,
            features_candles=list(current_candles[-60:]),
        )
        rec = self.record_signal(signal, True, volume, [], [f"position #{pos.id} opened"])
        rec["position_id"] = pos.id
        if self.on_position_opened:
            try:
                self.on_position_opened(pos, self.broker.account().balance, signal.ts)
            except Exception:
                log.exception("on_position_opened callback failed")
        return pos

    def process_signal(self, signal: Signal, spread_price: float,
                       vol_scale: float, current_candles: list) -> Position | None:
        spec = self.cfg.symbols[signal.symbol]
        account = self.broker.account()
        decision = self.risk.validate_trade(
            signal, account, self.broker.positions(), spec, spread_price, vol_scale)
        if not decision.approved:
            self.record_signal(signal, False, 0.0, decision.blockers, decision.notes)
            if self.on_block:
                self.on_block(signal, decision)
            return None
        try:
            return self.open_position(signal, decision.volume_lots, current_candles)
        except BrokerError as exc:
            self.record_signal(signal, False, 0.0, [f"broker: {exc}"], decision.notes)
            if self.on_block:
                self.on_block(signal, RiskDecision(False, 0.0, 1.0, [str(exc)]))
            return None

    # -------------------------------------------------------- in-trade manage
    def manage_positions(self, sim_ts: float, candle_age: dict[str, float]) -> None:
        positions = {p.id: p for p in self.broker.positions()}
        # harvest broker-side closures (SL/TP hits) FIRST — the learning loop
        # needs the ManagedState (features/strategy) before it is pruned
        self._harvest_deals()
        for pid, mstate in list(self.managed.items()):
            if pid not in positions:
                del self.managed[pid]

        for p in positions.values():
            ms = self.managed.get(p.id)
            if ms is None:
                continue
            spec = self.cfg.symbols[p.symbol]
            tick = self.broker.tick(p.symbol)
            price = tick.bid if p.side is Side.BUY else tick.ask
            r_dist = max(st.risk_distance(p.side, ms.entry, ms.initial_sl), 1e-12)
            pnl_r = (price - ms.entry) * p.side.sign / r_dist
            tp_dist = abs(ms.initial_tp - ms.entry)

            # 1) multi-level partial take profits (25/50/75/100% of TP distance)
            for idx, frac in enumerate(self.rk["tp_levels"][:-1], start=1):
                level_px = ms.entry + (ms.initial_tp - ms.entry) * frac
                hit = price >= level_px if p.side is Side.BUY else price <= level_px
                if hit and idx not in ms.levels_done:
                    ms.levels_done.add(idx)
                    close_vol = round(ms.initial_volume * self.rk["partial_close_pct"] / 100.0, 2)
                    close_vol = min(close_vol, max(p.volume - self.rk["min_lot"], 0.0))
                    if close_vol >= self.rk["min_lot"]:
                        try:
                            self.broker.close_position(p.id, close_vol, reason=f"PARTIAL_TP{idx}")
                        except BrokerError as exc:
                            log.warning("partial close failed: %s", exc)
                        self._harvest_deals()

            # 2) breakeven protection after level N
            be_level = self.rk["breakeven_after_level"]
            if not ms.breakeven_moved and be_level in ms.levels_done:
                buffer = self.rk["breakeven_buffer_pips"] * spec.pip
                new_sl = st.breakeven_stop(p.side, ms.entry, buffer)
                if st.improves_stop(p.side, new_sl, p.stop_loss):
                    self._safe_modify(p, new_sl, p.take_profit)
                    ms.breakeven_moved = True

            # 3) ATR trailing stop once trailing level reached
            if self.rk["trailing_after_level"] in ms.levels_done:
                trail = st.trailing_stop(p.side, price, ms.atr, self.rk["trailing_atr_mult"])
                if st.improves_stop(p.side, trail, p.stop_loss):
                    self._safe_modify(p, trail, p.take_profit)

            # 4) time-based stop for dead trades
            age = candle_age.get(p.symbol, 0.0)
            if st.time_stop_due(age, self.rk["time_stop_candles"], pnl_r,
                                self.rk["time_stop_min_r"], self.rk["time_stop_max_r"]):
                try:
                    self.broker.close_position(p.id, reason="TIME_STOP")
                except BrokerError as exc:
                    log.warning("time stop close failed: %s", exc)
                self._harvest_deals()

    def _safe_modify(self, p: Position, sl: float, tp: float) -> None:
        try:
            self.broker.modify_stops(p.id, sl, tp)
        except BrokerError as exc:
            log.warning("stop modify failed for #%s: %s", p.id, exc)

    def close_all(self, reason: str) -> int:
        n = 0
        for p in list(self.broker.positions()):
            try:
                self.broker.close_position(p.id, reason=reason)
                n += 1
            except BrokerError as exc:
                log.warning("close_all failed for #%s: %s", p.id, exc)
        self._harvest_deals()
        return n

    # ------------------------------------------------------------ bookkeeping
    def _harvest_deals(self) -> None:
        get = getattr(self.broker, "deals", None)
        if get is None:
            return
        for d in get():
            if d.id in self._seen_deal_ids:
                continue
            self._seen_deal_ids.add(d.id)
            self.deals.appendleft(d)
            ms = self.managed.get(d.position_id)
            if d.reason in ("SL", "TP", "TIME_STOP", "MANUAL", "EMERGENCY", "LIQUIDATED"):
                self.risk.register_result(d.pnl)
                if self.on_deal:
                    self.on_deal(d, ms)
                if d.position_id in self.managed and not any(
                        p.id == d.position_id for p in self.broker.positions()):
                    self.managed.pop(d.position_id, None)

    def snapshot(self) -> dict:
        return {
            "recent_signals": list(self.recent_signals)[:20],
            "deals": [
                {"id": d.id, "position_id": d.position_id, "symbol": d.symbol,
                 "side": d.side.value, "volume": d.volume,
                 "entry": d.entry_price, "exit": d.exit_price,
                 "entry_ts": d.entry_ts, "exit_ts": d.exit_ts,
                 "pnl": d.pnl, "reason": d.reason}
                for d in list(self.deals)[:50]
            ],
        }
