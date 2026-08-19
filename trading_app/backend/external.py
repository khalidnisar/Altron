"""External signal ingestion — merged from Kaltorim's
MT5-Trend-Direction-Predictor bridge workflow (direction-alias
normalization + symbol filtering), hardened to our risk-first design:

external payloads NEVER execute directly — they are converted into a Signal
with ATR-derived hard SL/TP and routed through the graph's risk_gate /
execution / learning nodes like any internal hypothesis.
"""
from __future__ import annotations

from .models import Side, Signal
from .config import AppConfig
from .risk.stops import initial_sl_tp
from .ai import indicators as ind
import hashlib
import hmac

import numpy as np

BUY_ALIASES = {"BUY", "LONG", "BULL", "BULLISH", "STRONG_BUY", "STRONG BUY"}
SELL_ALIASES = {"SELL", "SHORT", "BEAR", "BEARISH", "STRONG_SELL", "STRONG SELL"}
DIRECTION_FIELDS = ("signal", "direction", "trend", "side", "recommendation")


class PayloadError(ValueError):
    pass


def verify_secret(provided: str | None, configured: str) -> bool:
    """Shared-secret / HMAC digest check — Altron-Sword webhook receiver pattern.
    Accepts the exact shared secret or the SHA-256 hex digest of it."""
    if not provided:
        return False
    provided = str(provided)
    return hmac.compare_digest(provided, configured) or hmac.compare_digest(
        provided, hashlib.sha256(configured.encode()).hexdigest())


def normalize_direction(value: str | None) -> Side | None:
    if value is None:
        return None
    v = value.strip().upper()
    if v in BUY_ALIASES:
        return Side.BUY
    if v in SELL_ALIASES:
        return Side.SELL
    return None


def _read(payload: dict, *names: str):
    for n in names:
        if n in payload and payload[n] not in (None, ""):
            return payload[n]
    return None


def build_external_signal(payload: dict, cfg: AppConfig, candles: list, ts: float) -> Signal:
    """Validate + convert a raw bridge payload into a risk-wrapped Signal."""
    symbol = str(_read(payload, "symbol", "asset", "instrument") or "").upper().replace("/", "")
    if symbol not in cfg.symbols:
        raise PayloadError(f"unknown/unsupported symbol '{symbol}' (bridge only serves "
                           f"{', '.join(cfg.symbols)})")
    direction_raw = _read(payload, *DIRECTION_FIELDS)
    side = normalize_direction(str(direction_raw) if direction_raw is not None else None)
    if side is None:
        raise PayloadError(f"unrecognised direction '{direction_raw}' "
                           f"(accepted aliases: {sorted(BUY_ALIASES | SELL_ALIASES)})")
    try:
        confidence = float(_read(payload, "confidence", "strength") or 75.0)
    except (TypeError, ValueError):
        confidence = 75.0
    confidence = min(max(confidence, 0.0), 100.0)

    spec = cfg.symbols[symbol]
    price = candles[-1].close if candles else spec.base_price
    if len(candles) > 15:
        atr_now = float(ind.atr(np.array([c.high for c in candles]),
                                np.array([c.low for c in candles]),
                                np.array([c.close for c in candles]))[-1])
    else:
        atr_now = spec.pip * 10
    rk = cfg.data["risk"]
    sl, tp = initial_sl_tp(side, price, atr_now, rk["sl_atr_mult"], rk["tp_rr"], spec)
    source = str(_read(payload, "source", "origin") or "external-bridge")
    return Signal(
        symbol=symbol, side=side, ts=ts, confidence=round(confidence, 1),
        technical=50.0, ml=50.0, sentiment=50.0, microstructure=50.0,
        confluence=int(_read(payload, "confluence") or 3),
        regime="EXTERNAL", strategy="EXTERNAL",
        entry=price, stop_loss=sl, take_profit=tp, atr=round(atr_now, spec.digits),
        size_hint=1.0,
        reasons=[f"external {source} signal ({direction_raw}) — wrapped with ATR hard stops"],
    )
