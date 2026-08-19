"""TradeCopier — master trade replication to up to 10 follower accounts.

Design lifted from tetratensor/MT4-MT5-Trade-Copier-Backend and hardened:
  * order-pair contract: master position id ↔ follower position id
  * poll-based reconciliation every tick (open/resize/close/SL-TP sync)
  * sizing modes: mirror | proportional (balance×multiplier) | fixed_lot
  * force min/max lot, symbol filters, reverse-copy
  * execution events hook for low-latency first fill (reconcile backstop)
"""
from __future__ import annotations

import json
import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..brokers.base import Broker, BrokerError
from ..brokers.simulated import SimulatedBroker
from ..config import AppConfig
from ..models import Position, Side
from ..risk.sizing import round_lots
from .accounts import AccountCfg, MAX_FOLLOWERS, validate_cfg
from .follower import FollowerBroker

log = logging.getLogger("trading_app.copier")
DEFAULT_STORE = Path(__file__).resolve().parents[3] / "data" / "copier_accounts.json"

CLOSE_REASONS = ("SL", "TP", "TIME_STOP", "MANUAL", "EMERGENCY", "LIQUIDATED", "MASTER_CLOSED")


@dataclass
class Pair:
    master_pos_id: int
    master_vol_open: float
    symbol: str
    follower_map: dict[str, dict] = field(default_factory=dict)  # acct_id → {pos_id, vol_open}


@dataclass
class FollowerRuntime:
    cfg: AccountCfg
    broker: Broker | None = None
    connected: bool = False
    error: str = ""
    seen_deals: set[int] = field(default_factory=set)
    stats: dict = field(default_factory=lambda: {
        "copied": 0, "partials": 0, "closes": 0, "sl_syncs": 0,
        "wins": 0, "losses": 0, "copied_pnl": 0.0, "last_copy_ts": 0.0,
        "skipped": {},
    })

    def skip(self, reason: str) -> None:
        sk = self.stats["skipped"]
        sk[reason] = sk.get(reason, 0) + 1


class TradeCopier:
    def __init__(self, cfg: AppConfig, master_broker: Broker,
                 store_path: str | os.PathLike | None = None,
                 seed_balance: float = 25_000.0):
        self.cfg = cfg
        self.master = master_broker
        self.followers: dict[str, FollowerRuntime] = {}
        self.pairs: dict[int, Pair] = {}
        self.on_event = None                       # callback(level, code, message)
        self.store = Path(os.environ.get("TRADING_COPIER_STORE", store_path or DEFAULT_STORE))
        self._seed_balance = seed_balance
        self._load()

    # ------------------------------------------------------------ registry
    def _emit(self, level, code, message) -> None:
        if self.on_event:
            self.on_event(level, code, message)

    def _spawn_broker(self, account: AccountCfg, seed: int) -> Broker:
        if account.broker_type == "mt5_demo":
            from ..brokers.mt5_demo import MT5DemoBroker
            return MT5DemoBroker(self.cfg)
        return FollowerBroker(self.cfg, seed=seed,
                              balance=self._seed_balance, spread_factor=0.9 + (seed % 5) * 0.1)

    def add_account(self, data: dict) -> AccountCfg:
        if len(self.followers) >= MAX_FOLLOWERS:
            raise ValueError(f"maximum of {MAX_FOLLOWERS} linked accounts reached")
        cfg = AccountCfg.from_dict(data)
        if cfg.id in self.followers:
            raise ValueError("duplicate account id")
        rt = FollowerRuntime(cfg=cfg)
        self.followers[cfg.id] = rt
        self._save()
        self.connect(cfg.id)
        self._emit("INFO", "COPIER_ADD", f"Account '{cfg.label}' linked ({cfg.broker_type}, {cfg.mode} ×{cfg.multiplier})")
        return cfg

    def update_account(self, acct_id: str, patch: dict) -> AccountCfg:
        rt = self.followers[acct_id]
        data = rt.cfg.to_dict()
        data.update({k: v for k, v in patch.items() if k in data and k != "id"})
        rt.cfg = AccountCfg.from_dict(data)
        validate_cfg(rt.cfg)
        self._save()
        self._emit("INFO", "COPIER_UPDATE", f"Account '{rt.cfg.label}' updated")
        return rt.cfg

    def remove_account(self, acct_id: str) -> int:
        rt = self.followers.pop(acct_id)
        closed = 0
        if rt.broker and rt.connected:
            for p in list(rt.broker.positions()):
                try:
                    rt.broker.close_position(p.id, reason="MANUAL")
                    closed += 1
                except BrokerError:
                    pass
            rt.broker.disconnect()
        for pair in self.pairs.values():
            pair.follower_map.pop(acct_id, None)
        self._save()
        self._emit("INFO", "COPIER_REMOVE", f"Account '{rt.cfg.label}' unlinked ({closed} mirrored position(s) closed)")
        return closed

    def connect(self, acct_id: str) -> None:
        rt = self.followers[acct_id]
        try:
            if rt.broker is None:
                rt.broker = self._spawn_broker(rt.cfg, seed=abs(hash(acct_id)) % 10_000)
            if isinstance(rt.broker, SimulatedBroker) and isinstance(self.master, SimulatedBroker):
                rt.broker.attach_feed(self.master)
                rt.broker.step(0.0)
            rt.broker.connect()
            rt.connected, rt.error = True, ""
        except Exception as exc:  # noqa: BLE001 - surface connection issue in UI
            rt.connected, rt.error = False, str(exc)
            self._emit("WARNING", "COPIER_CONN",
                       f"Follower '{rt.cfg.label}' offline: {exc}")

    def disconnect(self, acct_id: str) -> None:
        rt = self.followers[acct_id]
        if rt.broker:
            rt.broker.disconnect()
        rt.connected = False
        rt.error = "disconnected by operator"

    # ------------------------------------------------------------- copying
    def _copy_volume(self, rt: FollowerRuntime, master_pos: Position,
                     master_balance: float) -> float:
        cfg = rt.cfg
        spec = self.cfg.symbols[master_pos.symbol]
        if cfg.mode == "mirror":
            vol = master_pos.volume * cfg.multiplier
        elif cfg.mode == "proportional":
            follower_eq = rt.broker.account().equity if rt.broker else self._seed_balance
            vol = master_pos.volume * (follower_eq / max(master_balance, 1e-9)) * cfg.multiplier
        else:  # fixed_lot
            vol = cfg.fixed_lots * cfg.multiplier
        vol = min(vol, cfg.max_lot)
        # affordability clamp (95% of free margin)
        if rt.broker:
            px = rt.broker.tick(master_pos.symbol).mid
            acct = rt.broker.account()
            leverage = acct.leverage
            affordable = acct.free_margin * leverage * 0.95 / (
                px * spec.contract_size * spec.quote_to_usd(px))
            vol = min(vol, affordable)
        return round_lots(vol, self.cfg.f("risk", "min_lot", default=0.01),
                          cfg.max_lot, self.cfg.f("risk", "lot_step", default=0.01))

    def on_master_open(self, master_pos: Position, master_balance: float, ts: float) -> None:
        """Low-latency hook fired the moment the master opens a trade."""
        pair = self.pairs.setdefault(master_pos.id, Pair(master_pos.id, master_pos.volume,
                                                         master_pos.symbol))
        for acct_id, rt in self.followers.items():
            self._copy_to_follower(rt, master_pos, master_balance, pair, ts)

    def _copy_to_follower(self, rt: FollowerRuntime, master_pos: Position,
                          master_balance: float, pair: Pair, ts: float) -> None:
        cfg = rt.cfg
        if not cfg.enabled:
            return rt.skip("disabled")
        if not rt.connected or rt.broker is None:
            return rt.skip("offline")
        if cfg.symbols and master_pos.symbol not in cfg.symbols:
            return rt.skip("symbol_filtered")
        if pair.follower_map.get(cfg.id):
            return
        side = master_pos.side.opposite if cfg.reverse else master_pos.side
        sl, tp = (master_pos.take_profit, master_pos.stop_loss) if cfg.reverse \
            else (master_pos.stop_loss, master_pos.take_profit)
        vol = self._copy_volume(rt, master_pos, master_balance)
        if vol <= 0:
            return rt.skip("volume_below_min")
        try:
            pos = rt.broker.market_order(master_pos.symbol, side, vol, sl, tp)
            pos.entry_ts = master_pos.entry_ts or ts
        except BrokerError as exc:
            return rt.skip(f"broker:{str(exc)[:28]}")
        pair.follower_map[cfg.id] = {"pos_id": pos.id, "vol_open": pos.volume}
        rt.stats["copied"] += 1
        rt.stats["last_copy_ts"] = ts
        self._emit("INFO", f"COPY_{cfg.id}",
                   f"Copied {side.value} {master_pos.symbol} ×{vol:.2f} → '{cfg.label}'")

    # -------------------------------------------------------- reconciliation
    def step(self, ts: float, master_balance: float) -> None:
        """Per-tick reconciliation (backstop for the open hook)."""
        master_positions = {p.id: p for p in self.master.positions()}

        # 1) new master trades missed by the hook
        for p in master_positions.values():
            if p.id not in self.pairs:
                self.on_master_open(p, master_balance, ts)

        # 2) update/close per pair, per follower
        for master_id, pair in list(self.pairs.items()):
            master_pos = master_positions.get(master_id)
            for acct_id, ref in list(pair.follower_map.items()):
                rt = self.followers.get(acct_id)
                if rt is None or not rt.connected or rt.broker is None:
                    continue
                fpos = next((x for x in rt.broker.positions() if x.id == ref["pos_id"]), None)
                if master_pos is None:                      # master closed → close follower
                    if fpos is not None:
                        self._safe_close(rt, fpos, fpos.volume, "MASTER_CLOSED")
                        rt.stats["closes"] += 1
                    del pair.follower_map[acct_id]
                    continue
                if fpos is None:                            # follower closed by own SL/TP
                    del pair.follower_map[acct_id]
                    continue
                self._sync_stops(rt, fpos, master_pos)
                self._sync_partial(rt, fpos, master_pos, pair, ref)
            if not pair.follower_map and master_pos is None:
                del self.pairs[master_id]

        # 3) step follower venues + harvest realized results
        for rt in self.followers.values():
            if not rt.connected or rt.broker is None:
                continue
            if isinstance(rt.broker, FollowerBroker):
                rt.broker.step(ts)
            self._harvest(rt)

    def _sync_stops(self, rt: FollowerRuntime, fpos: Position, master_pos: Position) -> None:
        spec = self.cfg.symbols[master_pos.symbol]
        tol = spec.point
        sl, tp = (master_pos.take_profit, master_pos.stop_loss) if rt.cfg.reverse \
            else (master_pos.stop_loss, master_pos.take_profit)
        if abs(fpos.stop_loss - sl) > tol or abs(fpos.take_profit - tp) > tol:
            try:
                rt.broker.modify_stops(fpos.id, sl, tp)
                rt.stats["sl_syncs"] += 1
            except BrokerError:
                rt.skip("modify_failed")

    def _sync_partial(self, rt: FollowerRuntime, fpos: Position, master_pos: Position,
                      pair: Pair, ref: dict) -> None:
        frac = master_pos.volume / max(pair.master_vol_open, 1e-9)
        target = ref["vol_open"] * frac
        delta = round(fpos.volume - target, 2)
        if delta >= self.cfg.f("risk", "min_lot", default=0.01):
            self._safe_close(rt, fpos, delta, "MASTER_PARTIAL")
            rt.stats["partials"] += 1

    def _safe_close(self, rt: FollowerRuntime, fpos: Position, volume: float, reason: str) -> None:
        try:
            rt.broker.close_position(fpos.id, min(volume, fpos.volume), reason=reason)
        except BrokerError:
            rt.skip("close_failed")

    def _harvest(self, rt: FollowerRuntime) -> None:
        get = getattr(rt.broker, "deals", None)
        if get is None:
            return
        for d in get():
            if d.id in rt.seen_deals:
                continue
            rt.seen_deals.add(d.id)
            if d.reason in CLOSE_REASONS or d.reason.startswith("MASTER"):
                rt.stats["copied_pnl"] = round(rt.stats["copied_pnl"] + d.pnl, 2)
                rt.stats["wins" if d.pnl > 0 else "losses"] += 1

    # ---------------------------------------------------------- persistence
    def _load(self) -> None:
        if not self.store.exists():
            return
        try:
            data = json.loads(self.store.read_text())
        except Exception as exc:
            log.warning("copier store unreadable (%s) — starting fresh", exc)
            return
        for item in data.get("accounts", [])[:MAX_FOLLOWERS]:
            try:
                cfg = AccountCfg.from_dict(item)
            except ValueError as exc:
                log.warning("skipping invalid saved account: %s", exc)
                continue
            rt = FollowerRuntime(cfg=cfg)
            self.followers[cfg.id] = rt
            self.connect(cfg.id)

    def _save(self) -> None:
        try:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            self.store.write_text(json.dumps(
                {"accounts": [rt.cfg.to_dict() for rt in self.followers.values()]}, indent=2))
        except Exception as exc:  # noqa: BLE001
            log.warning("copier store save failed: %s", exc)

    # ---------------------------------------------------------------- views
    def snapshot(self) -> dict:
        out = {"max_followers": MAX_FOLLOWERS, "pairs_open": len(self.pairs), "followers": []}
        for rt in self.followers.values():
            acct = rt.broker.account() if (rt.connected and rt.broker) else None
            open_pos = []
            if rt.connected and rt.broker:
                for p in rt.broker.positions():
                    spec = self.cfg.symbols[p.symbol]
                    t = rt.broker.tick(p.symbol)
                    open_pos.append({
                        "id": p.id, "symbol": p.symbol, "side": p.side.value,
                        "volume": p.volume,
                        "pnl": round(p.floating_pnl(spec, t.bid, t.ask), 2),
                    })
            out["followers"].append({
                **rt.cfg.to_dict(),
                "connected": rt.connected, "error": rt.error,
                "balance": acct.balance if acct else None,
                "equity": acct.equity if acct else None,
                "margin_level": acct.margin_level if acct else None,
                "open_positions": open_pos,
                "stats": rt.stats,
            })
        return out
