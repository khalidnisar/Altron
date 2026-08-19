"""MetaTrader 5 terminal adapter — DEMO ACCOUNTS ONLY (blueprint 1C).

Safety posture (hard-coded, cannot be toggled off):
  * connect() inspects `account_info().trade_mode`; anything other than
    ACCOUNT_TRADE_MODE_DEMO raises SafetyViolation and refuses to proceed.
  * Live-money order routing is never constructed here.

Requires a local MT5 terminal with the `MetaTrader5` python package
(Windows-only), matching the parent repo's `mt5` extra. All methods degrade
with BrokerError on RPC failure; the orchestrator's supervisor will alert and
attempt reconnection with backoff.
"""
from __future__ import annotations

import itertools
import time

from ..config import AppConfig
from ..models import AccountInfo, Deal, Position, Side, Tick
from .base import Broker, BrokerError, SafetyViolation

try:
    import MetaTrader5 as mt5  # type: ignore

    _MT5_OK = True
    _DEMO_MODE = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
except Exception:  # noqa: BLE001 - package only exists beside a terminal
    mt5 = None
    _MT5_OK = False
    _DEMO_MODE = 0


class MT5DemoBroker(Broker):
    name = "mt5_demo"
    MAX_RECONNECT_ATTEMPTS = 5
    RECONNECT_BACKOFF_S = 5

    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self._connected = False
        self._deal_ids = itertools.count(1)

    # -------------------------------------------------------------- connect
    def connect(self) -> None:
        if not _MT5_OK:
            raise BrokerError("MetaTrader5 package not available (needs a local MT5 terminal)")
        if not mt5.initialize():
            raise BrokerError(f"mt5.initialize() failed: {mt5.last_error()}")
        info = mt5.account_info()
        if info is None:
            mt5.shutdown()
            raise BrokerError("terminal connected but no trading account is logged in")
        if info.trade_mode != _DEMO_MODE:                       # HARD SAFETY GATE
            mt5.shutdown()
            raise SafetyViolation(
                f"Refusing to trade: account {info.login} is not a DEMO account "
                f"(trade_mode={info.trade_mode}). Live routing is disabled by design.")
        self._connected = True

    def disconnect(self) -> None:
        if _MT5_OK:
            mt5.shutdown()
        self._connected = False

    def connected(self) -> bool:
        return self._connected

    def ensure_connected(self) -> None:
        """Auto-reconnection with backoff (blueprint 1C connection management)."""
        if self._connected:
            return
        for _ in range(self.MAX_RECONNECT_ATTEMPTS):
            try:
                self.connect()
                return
            except BrokerError:
                time.sleep(self.RECONNECT_BACKOFF_S)
        raise BrokerError("could not re-establish MT5 connection")

    # -------------------------------------------------------------- account
    def account(self) -> AccountInfo:
        self.ensure_connected()
        a = mt5.account_info()
        if a is None:
            raise BrokerError("account_info() unavailable")
        level = (a.equity / a.margin * 100.0) if a.margin > 0 else 99999.0
        return AccountInfo(balance=float(a.balance), equity=float(a.equity),
                           margin_used=float(a.margin), free_margin=float(a.margin_free),
                           margin_level=round(min(level, 99999.0), 1),
                           currency=a.currency, leverage=a.leverage, trade_mode="demo")

    def tick(self, symbol: str) -> Tick:
        self.ensure_connected()
        t = mt5.symbol_info_tick(symbol)
        if t is None:
            raise BrokerError(f"no tick for {symbol}")
        return Tick(symbol=symbol, ts=float(t.time), bid=float(t.bid), ask=float(t.ask))

    def positions(self) -> list[Position]:
        self.ensure_connected()
        raw = mt5.positions_get() or []
        out = []
        for p in raw:
            side = Side.BUY if p.type == mt5.POSITION_TYPE_BUY else Side.SELL
            out.append(Position(id=int(p.ticket), symbol=p.symbol, side=side,
                                volume=float(p.volume), entry_price=float(p.price_open),
                                entry_ts=float(p.time), stop_loss=float(p.sl),
                                take_profit=float(p.tp)))
        return out

    # ---------------------------------------------------------------- orders
    def market_order(self, symbol: str, side: Side, volume: float,
                     stop_loss: float, take_profit: float) -> Position:
        self.ensure_connected()
        if stop_loss <= 0:
            raise BrokerError("RULE 2: stop loss is mandatory")
        t = self.tick(symbol)
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": mt5.ORDER_TYPE_BUY if side is Side.BUY else mt5.ORDER_TYPE_SELL,
            "price": t.ask if side is Side.BUY else t.bid,
            "sl": float(stop_loss),
            "tp": float(take_profit),
            "deviation": 20,
            "magic": 20260812,
            "comment": "altron-autotrade",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            code = getattr(res, "retcode", "RPC-ERROR")
            raise BrokerError(f"order rejected: retcode {code}")
        return Position(id=int(res.order), symbol=symbol, side=side, volume=volume,
                        entry_price=float(res.price), entry_ts=float(t.ts),
                        stop_loss=stop_loss, take_profit=take_profit)

    def modify_stops(self, position_id: int, stop_loss: float, take_profit: float) -> None:
        self.ensure_connected()
        pos = next((p for p in self.positions() if p.id == position_id), None)
        if pos is None:
            raise BrokerError(f"position {position_id} not found")
        req = {"action": mt5.TRADE_ACTION_SLTP, "position": position_id, "symbol": pos.symbol,
               "sl": float(stop_loss), "tp": float(take_profit)}
        res = mt5.order_send(req)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            raise BrokerError(f"SL/TP modify rejected: retcode {getattr(res, 'retcode', 'RPC-ERROR')}")

    def close_position(self, position_id: int, volume: float | None = None,
                       reason: str = "MANUAL") -> Deal:
        self.ensure_connected()
        pos = next((p for p in self.positions() if p.id == position_id), None)
        if pos is None:
            raise BrokerError(f"position {position_id} not found")
        vol = float(volume or pos.volume)
        t = self.tick(pos.symbol)
        req = {
            "action": mt5.TRADE_ACTION_DEAL, "position": position_id, "symbol": pos.symbol,
            "volume": vol, "type": mt5.ORDER_TYPE_SELL if pos.side is Side.BUY else mt5.ORDER_TYPE_BUY,
            "price": t.bid if pos.side is Side.BUY else t.ask, "deviation": 20,
            "magic": 20260812, "comment": f"altron-close:{reason}", "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            raise BrokerError(f"close rejected: retcode {getattr(res, 'retcode', 'RPC-ERROR')}")
        return Deal(id=next(self._deal_ids), position_id=position_id, symbol=pos.symbol,
                    side=pos.side, volume=vol, entry_price=pos.entry_price,
                    exit_price=float(res.price), entry_ts=pos.entry_ts, exit_ts=float(t.ts),
                    pnl=float(getattr(res, "profit", 0.0) or 0.0), reason=reason)
