"""Signal generation (blueprint 1B / 3 / 9 steps 1–2).

Confidence = Technical×0.30 + ML×0.40 + Sentiment×0.20 + Microstructure×0.10
Trade only when Confidence > MIN_CONFIDENCE (70) and confluence ≥ 3 signals.

Adaptive strategy selection:
  Trend UP/DOWN  → BREAKOUT (momentum-following)
  RANGE          → MEAN_REVERSION (fade Bollinger/RSI extremes)
  HIGH vol       → DEFENSIVE (same logic, size_hint = 0.5)
  LOW liquidity  → NO_TRADE
"""
from __future__ import annotations

import numpy as np

from ..config import AppConfig
from ..models import Signal, Side, SymbolAnalysis
from . import indicators as ind
from . import sword_pack
from .ml_model import EnsembleModel
from .regime import RegimeDetector
from .sentiment import SentimentEngine
from .microstructure import MicrostructureEngine

W_TECH, W_ML, W_SENT, W_MICRO = 0.30, 0.40, 0.20, 0.10


class SignalEngine:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.regimes = RegimeDetector(cfg)
        self.model = EnsembleModel()
        self.sentiment = SentimentEngine()
        self.micro = MicrostructureEngine()
        self.latest: dict[str, SymbolAnalysis] = {}

    # ------------------------------------------------------------- technical
    def _technical_votes(self, symbol: str, candles: list, strategy: str) -> tuple[Side, int, float, dict]:
        """Return (dominant side, confluence count, raw technical score, detail)."""
        c = np.array([x.close for x in candles])
        h = np.array([x.high for x in candles])
        l = np.array([x.low for x in candles])
        price = c[-1]
        rsi_v = float(ind.rsi(c)[-1])
        macd_line, macd_sig, hist = ind.macd(c)
        e20 = float(ind.ema(c, 20)[-1]); e50 = float(ind.ema(c, 50)[-1])
        mid, up, lo = ind.bollinger(c)
        k_line, d_line = ind.stochastic(h, l, c)
        du, dl = ind.donchian(h, l)
        votes_up, votes_dn, detail = 0, 0, {}

        def vote(up: bool, name: str, cond: bool):
            nonlocal votes_up, votes_dn
            if cond:
                detail[name] = up
                if up:
                    votes_up += 1
                else:
                    votes_dn += 1

        macd_up = float(hist[-1]) > 0 and float(hist[-1]) > float(hist[-2])
        macd_dn = float(hist[-1]) < 0 and float(hist[-1]) < float(hist[-2])
        if strategy == "MEAN_REVERSION":
            vote(True, "rsi_oversold", rsi_v < 30)
            vote(False, "rsi_overbought", rsi_v > 70)
            vote(True, "bb_lower_touch", not np.isnan(lo[-1]) and price <= lo[-1] * 1.001)
            vote(False, "bb_upper_touch", not np.isnan(up[-1]) and price >= up[-1] * 0.999)
            vote(True, "stoch_cross_up", k_line[-1] > d_line[-1] and k_line[-2] <= d_line[-2] and k_line[-1] < 35)
            vote(False, "stoch_cross_dn", k_line[-1] < d_line[-1] and k_line[-2] >= d_line[-2] and k_line[-1] > 65)
            vote(macd_up, "macd_momentum", macd_up or macd_dn)
            detail.setdefault("regime", True)
        else:  # BREAKOUT / DEFENSIVE momentum
            vote(True, "ema_stack_up", e20 > e50 and price > e20)
            vote(False, "ema_stack_dn", e20 < e50 and price < e20)
            vote(True, "macd_up", macd_up)
            vote(False, "macd_dn", macd_dn)
            vote(True, "donchian_breakout", not np.isnan(du[-1]) and price > du[-1])
            vote(False, "donchian_breakdown", not np.isnan(dl[-1]) and price < dl[-1])
            vote(True, "rsi_momentum_up", 50 < rsi_v < 72)
            vote(False, "rsi_momentum_dn", 28 < rsi_v < 50)
            vote(True, "stoch_up", k_line[-1] > d_line[-1] and k_line[-1] < 80)
            vote(False, "stoch_dn", k_line[-1] < d_line[-1] and k_line[-1] > 20)

        # Sword pack votes (regime-validated) — ORB / ROC / channel / order-flow
        pack_hits = []
        for ps in sword_pack.pack_votes(candles, list(self.micro.tick_dirs.get(symbol, []))):
            if strategy in ps.valid_strategies:
                vote(ps.side is Side.BUY, f"pack_{ps.name}", True)
                pack_hits.append(ps.reason)

        detail["_pack"] = pack_hits

        if votes_up == votes_dn:
            side = Side.BUY if votes_up > 0 and float(hist[-1]) > 0 else Side.SELL
            dominant = votes_up
        elif votes_up > votes_dn:
            side, dominant = Side.BUY, votes_up
        else:
            side, dominant = Side.SELL, votes_dn
        total = votes_up + votes_dn
        raw = 50.0 + (dominant - (total - dominant)) * 10.0  # margins widen score
        return side, dominant, min(max(raw, 5.0), 100.0), detail

    # --------------------------------------------------------------- analyse
    def analyze(self, symbol: str, spec, candles: list, tick_id: int,
                spread: float, tick_dir: int, allow: bool = True) -> tuple[Signal | None, SymbolAnalysis]:
        self.micro.observe(symbol, spread, tick_dir)
        regime = self.regimes.detect(symbol, candles, spread, self.micro.median_spread(symbol))
        strategy = self.regimes.strategy_for(regime)
        price = candles[-1].close

        side, confluence, tech, detail = self._technical_votes(symbol, candles, strategy)
        p_up = self.model.predict_proba_up(candles)
        ml = p_up * 100.0 if side is Side.BUY else (1.0 - p_up) * 100.0
        sent_raw = self.sentiment.score(symbol, tick_id)
        sent = sent_raw if side is Side.BUY else 100.0 - sent_raw
        liq = self.micro.liquidity_score(symbol, spread)
        flow = self.micro.flow_score(symbol, want_up=side is Side.BUY)
        micro_score = 0.5 * liq + 0.5 * flow

        confidence = W_TECH * tech + W_ML * ml + W_SENT * sent + W_MICRO * micro_score
        ev = self.sentiment.blackout_active(tick_id)

        note_parts: list[str] = []
        if strategy == "NO_TRADE":
            note_parts.append("low liquidity — no trading (RULE 11)")
        if ev:
            note_parts.append(f"high-impact event blackout: {ev['label']}")
        if regime.volatility == "EXTREME":
            note_parts.append("extreme volatility — signals suppressed")
        if not allow:
            note_parts.append("trading disabled")
        if detail.get("_pack"):
            note_parts.append("pack: " + ", ".join(detail["_pack"]))

        snapshot = SymbolAnalysis(
            symbol=symbol, ts=candles[-1].ts,
            regime=f"{regime.trend}/{regime.volatility}/{regime.liquidity} (ADX {regime.adx})",
            strategy=strategy, technical=round(tech, 1), ml=round(ml, 1),
            sentiment=round(sent_raw, 1), microstructure=round(micro_score, 1),
            confidence=round(confidence, 1), confluence=confluence,
            stance=side.value, note="; ".join(note_parts) or "scanning",
        )
        self.latest[symbol] = snapshot

        min_conf = self.cfg.f("risk", "min_confidence", default=70.0)
        min_conf_n = self.cfg.i("risk", "min_confluence", default=3)
        if (not allow or strategy == "NO_TRADE" or ev or regime.volatility == "EXTREME"
                or confidence <= min_conf or confluence < min_conf_n):
            return None, snapshot

        atr_ser = ind.atr(np.array([x.high for x in candles]),
                          np.array([x.low for x in candles]),
                          np.array([x.close for x in candles]))
        atr_now = float(atr_ser[-1])
        from ..risk.stops import initial_sl_tp
        rk = self.cfg.data["risk"]
        sl, tp = initial_sl_tp(side, price, atr_now, rk["sl_atr_mult"], rk["tp_rr"], spec)
        size_hint = self.cfg.f("volatility", "high_vol_size_factor", default=0.5) \
            if regime.volatility == "HIGH" else 1.0
        sig = Signal(
            symbol=symbol, side=side, ts=candles[-1].ts, confidence=round(confidence, 1),
            technical=round(tech, 1), ml=round(ml, 1), sentiment=round(sent, 1),
            microstructure=round(micro_score, 1), confluence=confluence,
            regime=snapshot.regime, strategy=strategy,
            entry=price, stop_loss=sl, take_profit=tp, atr=round(atr_now, spec.digits),
            size_hint=size_hint,
            reasons=[f"{strategy} {side.value} | conf {confidence:.0f} | confluence {confluence}"],
        )
        return sig, snapshot
