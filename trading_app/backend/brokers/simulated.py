"""Simulated broker — paper-first trading venue (blueprint 1C stand-in).

* Regime-switching price generator (trend / range / chop) per symbol.
* Floating-spread ticks with slippage on market fills.
* Broker-side SL/TP execution (fills at level − slippage when crossed),
  margin accounting (`notional / leverage`), equity tracking.
* `price_override` hook lets tests drive deterministic paths.
"""
from __future__ import annotations

import itertools

import numpy as np

from ..config import AppConfig
from ..models import AccountInfo, Deal, Position, Side, SymbolSpec, Tick
from .base import Broker, BrokerError

_EPS = 1e-12


class _SymbolState:
    def __init__(self, spec: SymbolSpec, rng: np.random.Generator):
        self.spec = spec
        self.mid = spec.base_price
        self.spread = spec.spread_points * spec.point
        self.median_spread = self.spread
        self.regime = rng.choice(["trend", "range", "chop"])
        self.drift_dir = float(rng.choice([-1.0, 1.0]))
        self.regime_ticks = 0
        self.last_tick: Tick | None = None


class SimulatedBroker(Broker):
    name = "simulated"

    def __init__(self, cfg: AppConfig, seed: int = 42):
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)
        self.leverage = cfg.i("account", "leverage", default=100)
        self.currency = str(cfg.get("account", "currency", default="USD"))
        self.balance = cfg.f("account", "starting_balance", default=100000.0)
        self.states = {name: _SymbolState(spec, self.rng) for name, spec in cfg.symbols.items()}
        self._positions: dict[int, Position] = {}
        self._deals: list[Deal] = []
        self._ids = itertools.count(1)
        self._deal_ids = itertools.count(1)
        self._connected = True
        self.price_override: dict[str, float] = {}   # test hook: symbol → forced mid
        self.order_reject_reason: str | None = None  # test hook
        self.rejected_orders = 0
        # ── perpetual-style funding engine ─────────────────────────────
        self.funding_rates: dict[str, float] = {
            n: float(self.rng.uniform(-0.0001, 0.0001)) for n in cfg.symbols}
        self.funding_interval_min = 480              # every 8 sim-hours
        self._last_funding_bucket = -1
        self._funding_events: list[dict] = []
        self.liquidations = 0                        # margin stop-out counter

    # ------------------------------------------------------------- plumbing
    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def connected(self) -> bool:
        return self._connected

    # -------------------------------------------------------------- pricing
    def _step_symbol(self, st: _SymbolState) -> None:
        spec = st.spec
        st.regime_ticks += 1
        if st.regime_ticks > 55 and self.rng.random() < 0.03:
            st.regime = self.rng.choice(["trend", "trend", "range", "chop"])
            st.drift_dir = float(self.rng.choice([-1.0, 1.0]))
            st.regime_ticks = 0
        sigma = spec.tick_sigma
        if st.regime == "trend":
            drift = st.drift_dir * sigma * 0.42
            vol = sigma
        elif st.regime == "range":
            drift = (spec.base_price - st.mid) * 0.004
            vol = sigma * 0.75
        else:
            drift = float(self.rng.normal(0, sigma * 0.15))
            vol = sigma * 1.5
        st.mid = max(st.mid + drift + float(self.rng.normal(0, vol)), spec.point * 100)
        # floating spread with occasional liquidity gaps
        widen = 1.0 + (4.0 if self.rng.random() < 0.015 else 0.0) + abs(self.rng.normal(0, 0.15))
        st.spread = spec.spread_points * spec.point * max(widen, 0.8)
        st.median_spread = spec.spread_points * spec.point
        half = st.spread / 2
        st.last_tick = Tick(spec.name, 0.0,
                            spec.round_price(st.mid - half), spec.round_price(st.mid + half))

    def step(self, ts: float) -> dict[str, int]:
        """Advance all prices one tick, fill SL/TP, return per-symbol tick dir."""
        dirs: dict[str, int] = {}
        for name, st in self.states.items():
            prev = st.mid
            if name in self.price_override:
                st.mid = self.price_override[name]
                half = st.spread / 2
                st.last_tick = Tick(name, 0.0, st.mid - half, st.mid + half)
            else:
                self._step_symbol(st)
            st.last_tick.ts = ts
            dirs[name] = 1 if st.mid > prev else (-1 if st.mid < prev else 0)
            self._update_funding(st)
        self._process_stops(ts)
        self._accrue_funding(ts)
        self._process_liquidations(ts)
        return dirs

    # -------------------------------------------------------------- funding
    def _update_funding(self, st: _SymbolState) -> None:
        """Funding rate tracks positioning pressure (perp convention)."""
        target = st.drift_dir * (0.00008 if st.regime == "trend" else 0.00002)
        rate = self.funding_rates[st.spec.name]
        rate += (target - rate) * 0.03 + float(self.rng.normal(0, 0.000008))
        self.funding_rates[st.spec.name] = float(min(max(rate, -0.0005), 0.0005))

    def funding_rate(self, symbol: str) -> float:
        return self.funding_rates.get(symbol, 0.0)

    def funding_events(self) -> list[dict]:
        return list(self._funding_events)

    def _accrue_funding(self, ts: float) -> None:
        bucket = int(ts // (60 * self.funding_interval_min))
        if bucket == self._last_funding_bucket or ts <= 0:
            return
        self._last_funding_bucket = bucket
        for p in list(self._positions.values()):
            spec = self.cfg.symbols[p.symbol]
            px = self.tick(p.symbol).mid
            notional = p.volume * spec.contract_size * px * spec.quote_to_usd(px)
            rate = self.funding_rates[p.symbol]
            payment = notional * rate * p.side.sign    # +rate: longs pay shorts
            self.balance -= payment
            self._funding_events.append({
                "ts": ts, "symbol": p.symbol, "position_id": p.id,
                "rate": round(rate, 6), "payment": round(-payment, 2),  # account view
            })
            if len(self._funding_events) > 300:
                self._funding_events = self._funding_events[-300:]

    # ---------------------------------------------------------- liquidations
    def _process_liquidations(self, ts: float) -> None:
        """Margin stop-out: below 100% margin level the venue force-closes
        largest-first until the account recovers (broker liquidation engine)."""
        while self._positions:
            acct = self.account()
            if acct.margin_used <= 0 or acct.margin_level >= 100.0:
                break
            biggest = max(self._positions.values(), key=lambda p: p.volume)
            st = self.states[biggest.symbol]
            exit_px = st.last_tick.bid if biggest.side is Side.BUY else st.last_tick.ask
            self._make_deal(biggest, exit_px, biggest.volume, ts, "LIQUIDATED")
            del self._positions[biggest.id]
            self.liquidations += 1

    def liquidation_price(self, p: Position) -> float:
        """Approx. liquidation price for a position (cross-margin estimate):
        the level where equity would reach ~100% margin level."""
        spec = self.cfg.symbols[p.symbol]
        px = self.tick(p.symbol).mid
        acct = self.account()
        # equity buffer available to this position before 100% margin level
        buffer = acct.equity - acct.margin_used
        move = buffer / (p.volume * spec.contract_size * spec.quote_to_usd(px))
        liq = p.entry_price - move if p.side is Side.BUY else p.entry_price + move
        return spec.round_price(max(liq, 0.0))

    def tick(self, symbol: str) -> Tick:
        st = self.states[symbol]
        if st.last_tick is None:
            self._step_symbol(st)
        return st.last_tick

    def spread(self, symbol: str) -> float:
        return self.states[symbol].spread

    def median_spread(self, symbol: str) -> float:
        return self.states[symbol].median_spread

    # -------------------------------------------------------------- account
    def _floating(self) -> float:
        total = 0.0
        for p in self._positions.values():
            t = self.tick(p.symbol)
            total += p.floating_pnl(self.cfg.symbols[p.symbol], t.bid, t.ask)
        return total

    def _margin_used(self) -> float:
        total = 0.0
        for p in self._positions.values():
            spec = self.cfg.symbols[p.symbol]
            px = self.tick(p.symbol).mid
            total += p.volume * spec.contract_size * px * spec.quote_to_usd(px) / self.leverage
        return total

    def account(self) -> AccountInfo:
        floating = self._floating()
        equity = self.balance + floating
        margin = self._margin_used()
        level = (equity / margin * 100.0) if margin > 0 else 99999.0
        return AccountInfo(balance=round(self.balance, 2), equity=round(equity, 2),
                           margin_used=round(margin, 2),
                           free_margin=round(equity - margin, 2),
                           margin_level=round(min(level, 99999.0), 1),
                           currency=self.currency, leverage=self.leverage,
                           trade_mode="simulated")

    # ---------------------------------------------------------------- orders
    def positions(self) -> list[Position]:
        return list(self._positions.values())

    def _slippage(self, spec: SymbolSpec) -> float:
        return float(self.rng.uniform(0, spec.slippage_points) ) * spec.point

    def market_order(self, symbol: str, side: Side, volume: float,
                     stop_loss: float, take_profit: float) -> Position:
        if not self._connected:
            raise BrokerError("broker disconnected")
        if stop_loss <= 0:
            raise BrokerError("RULE 2: stop loss is mandatory")
        if self.order_reject_reason:
            self.rejected_orders += 1
            raise BrokerError(self.order_reject_reason)
        spec = self.cfg.symbols[symbol]
        st = self.states[symbol]
        if st.last_tick is None:                 # venue not stepped yet — init pricing
            self._step_symbol(st)
        slip = self._slippage(spec)
        fill = (st.last_tick.ask + slip) if side is Side.BUY else (st.last_tick.bid - slip)
        # margin check mirrors a real broker
        need = volume * spec.contract_size * fill * spec.quote_to_usd(fill) / self.leverage
        if need > self.account().free_margin:
            self.rejected_orders += 1
            raise BrokerError("retcode 10019: not enough money")
        pos = Position(id=next(self._ids), symbol=symbol, side=side, volume=volume,
                       entry_price=spec.round_price(fill), entry_ts=0.0,
                       stop_loss=spec.round_price(stop_loss), take_profit=spec.round_price(take_profit))
        self._positions[pos.id] = pos
        return pos

    def modify_stops(self, position_id: int, stop_loss: float, take_profit: float) -> None:
        p = self._positions[position_id]
        p.stop_loss = self.cfg.symbols[p.symbol].round_price(stop_loss)
        p.take_profit = self.cfg.symbols[p.symbol].round_price(take_profit)

    def _make_deal(self, p: Position, exit_price: float, volume: float, ts: float,
                   reason: str) -> Deal:
        spec = self.cfg.symbols[p.symbol]
        dist = (exit_price - p.entry_price) * p.side.sign
        pnl = dist * volume * spec.contract_size * spec.quote_to_usd(exit_price)
        deal = Deal(id=next(self._deal_ids), position_id=p.id, symbol=p.symbol, side=p.side,
                    volume=volume, entry_price=p.entry_price,
                    exit_price=spec.round_price(exit_price), entry_ts=p.entry_ts,
                    exit_ts=ts, pnl=round(pnl, 2), reason=reason)
        self._deals.append(deal)
        self.balance += deal.pnl
        return deal

    def close_position(self, position_id: int, volume: float | None = None,
                       reason: str = "MANUAL") -> Deal:
        p = self._positions[position_id]
        spec = self.cfg.symbols[p.symbol]
        st = self.states[p.symbol]
        vol = min(volume if volume is not None else p.volume, p.volume)
        slip = self._slippage(spec)
        exit_px = (st.last_tick.bid - slip) if p.side is Side.BUY else (st.last_tick.ask + slip)
        deal = self._make_deal(p, exit_px, vol, st.last_tick.ts, reason)
        p.volume = round(p.volume - vol, 8)
        if p.volume <= _EPS:
            del self._positions[p.id]
        return deal

    def _process_stops(self, ts: float) -> None:
        for pid in list(self._positions):
            p = self._positions[pid]
            spec = self.cfg.symbols[p.symbol]
            st = self.states[p.symbol]
            bid, ask = st.last_tick.bid, st.last_tick.ask
            slip = self._slippage(spec)
            if p.side is Side.BUY:
                if bid <= p.stop_loss:
                    self._make_deal(p, p.stop_loss - slip, p.volume, ts, "SL")
                    del self._positions[pid]
                elif bid >= p.take_profit > 0:
                    self._make_deal(p, p.take_profit, p.volume, ts, "TP")
                    del self._positions[pid]
            else:
                if ask >= p.stop_loss:
                    self._make_deal(p, p.stop_loss + slip, p.volume, ts, "SL")
                    del self._positions[pid]
                elif ask <= p.take_profit > 0 and p.take_profit:
                    self._make_deal(p, p.take_profit, p.volume, ts, "TP")
                    del self._positions[pid]

    # ------------------------------------------------------------------ misc
    def deals(self) -> list[Deal]:
        return list(self._deals)

    def set_order_rejection(self, reason: str | None) -> None:
        self.order_reject_reason = reason
