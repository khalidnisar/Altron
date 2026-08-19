"""Altron-Sword integration tests: strategy pack, sessions, lifecycle plane,
webhook secret verification."""
import numpy as np
import pytest

from trading_app.backend.ai import sessions, sword_pack
from trading_app.backend.ai.signals import SignalEngine
from trading_app.backend.config import load_config
from trading_app.backend.external import verify_secret
from trading_app.backend.graph.nodes import LearningEngine
from trading_app.backend.models import Candle, Side

CFG = load_config()


def mk(n=90, start=1.0850, step=0.0, vol=0.0003, seed=3):
    rng = np.random.default_rng(seed)
    px, out = start, []
    for i in range(n):
        px += step + rng.normal(0, vol)
        h, l = px + abs(rng.normal(0, vol / 2)), px - abs(rng.normal(0, vol / 2))
        out.append(Candle("EURUSD", float(i * 900), px - step, max(h, px), min(l, px), px, 10))
    return out


class TestSessions:
    def test_overlap_classification(self):
        # 13:30 UTC → london + new_york overlap
        import datetime
        ts = datetime.datetime(2026, 8, 19, 13, 30, tzinfo=datetime.UTC).timestamp()
        s = sessions.classify(ts)
        assert "london" in s["active"] and "new_york" in s["active"]
        assert s["overlap"]

    def test_sydney_only_hours(self):
        import datetime
        ts = datetime.datetime(2026, 8, 19, 23, 0, tzinfo=datetime.UTC).timestamp()
        s = sessions.classify(ts)
        assert s["active"] == ["sydney"]
        assert sessions.size_factor(ts) == 0.7

    def test_overlap_full_size(self):
        import datetime
        ts = datetime.datetime(2026, 8, 19, 14, 0, tzinfo=datetime.UTC).timestamp()
        assert sessions.size_factor(ts) == 1.0


class TestSwordPack:
    def test_orb_fires_on_range_break(self):
        candles = mk(step=0.0, vol=0.0001)            # tight range
        last = candles[-1]
        candles.append(Candle("EURUSD", last.ts + 900, last.close,
                              last.close + 0.002, last.close, last.close + 0.0015, 10))
        ps = sword_pack.opening_range(candles)
        assert ps is not None and ps.side is Side.BUY and "orb_long" in ps.reason

    def test_orb_silent_inside_range(self):
        assert sword_pack.opening_range(mk(step=0.0, vol=0.0004)) is None

    def test_roc_momentum(self):
        candles = mk(step=0.0006, vol=0.00005, n=40)
        ps = sword_pack.roc_momentum(candles)
        assert ps is not None and ps.side is Side.BUY
        assert "roc_up" in ps.reason
        assert ps.side is Side.BUY

    def test_channel_fade_at_rails(self):
        # zig-zag in a horizontal corridor → channel detect; rail touch → fade vote
        px, candles = 1.0850, []
        for i in range(80):
            phase = i % 8
            px = 1.0850 + (phase if phase < 4 else 8 - phase) * 0.0010
            o = 1.0850 + ((phase - 1) % 8 if (phase - 1) % 8 < 4 else 8 - (phase - 1) % 8) * 0.0010
            candles.append(Candle("EURUSD", float(i * 900), o, px + 0.0002, px - 0.0002, px, 10))
        ch = sword_pack.detect_channel(candles, lookback=70, min_bars=8)
        assert ch is not None and ch.kind == "horizontal"
        candles.append(Candle("EURUSD", 80000, 1.089, 1.0895, 1.0885, 1.0891, 10))  # upper rail
        ps = sword_pack.channel_fade(candles, lookback=70)
        assert ps is not None and ps.side is Side.SELL
        assert "MEAN_REVERSION" in ps.valid_strategies

    def test_delta_imbalance(self):
        ps = sword_pack.delta_imbalance([1] * 50)
        assert ps is not None and ps.side is Side.BUY
        assert sword_pack.delta_imbalance([1, -1] * 30) is None

    def test_pack_votes_merge_into_confluence(self):
        eng = SignalEngine(CFG)
        candles = mk(step=0.0008, vol=0.0001, n=100)   # strong thrust
        candles[-9:] = [Candle("EURUSD", c.ts, c.open, c.open + 0.0001, c.open, c.open + 0.00005, 10)
                        for c in candles[-9:]]          # compressed opening range
        candles.append(Candle("EURUSD", 999999, candles[-1].close, candles[-1].close + 0.003,
                              candles[-1].close, candles[-1].close + 0.0025, 10))
        eng.micro.observe("EURUSD", EUR := CFG.symbols["EURUSD"].point * 12, 1)
        for _ in range(40):
            eng.micro.observe("EURUSD", EUR, 1)
        side, conf, _, detail = eng._technical_votes("EURUSD", candles, "BREAKOUT")
        assert side is Side.BUY
        assert conf >= 3
        assert any(k.startswith("pack_") for k in detail)


class TestLifecycle:
    def deal(self, pnl, strat="BREAKOUT", i=0):
        return type("D", (), {"pnl": pnl, "reason": "TP" if pnl > 0 else "SL",
                              "symbol": "EURUSD", "position_id": i,
                              "exit_price": 1.0, "entry_price": 0.9})()

    def model(self):
        return type("M", (), {"learn": lambda *a: None})()

    def test_incubation_scale_then_promotion(self):
        learn = LearningEngine()
        assert learn.stage_of("BREAKOUT") == "INCUBATION"
        assert learn.size_scale("BREAKOUT") == learn.lc["incubation_scale"]
        for i in range(12):
            learn.learn_from_deal(self.deal(50.0, i=i), None, self.model(), "BREAKOUT", 1000.0 + i)
        assert learn.stage_of("BREAKOUT") == "ACTIVE"
        assert learn.size_scale("BREAKOUT") == 1.0
        assert any("INCUBATION→ACTIVE" in l["message"] for l in learn.lessons)

    def test_probation_then_suspend(self):
        learn = LearningEngine()
        for i in range(12):
            learn.learn_from_deal(self.deal(50.0, i=i), None, self.model(), "BREAKOUT", 1000.0 + i)
        assert learn.stage_of("BREAKOUT") == "ACTIVE"
        for i in range(8):
            learn.consec_losses["BREAKOUT"] = 0     # isolate PF-driven path
            learn.learn_from_deal(self.deal(-60.0, i=i), None, self.model(), "BREAKOUT", 2000.0 + i)
        assert learn.stage_of("BREAKOUT") in ("PROBATION", "SUSPENDED")
        # keep sinking → SUSPENDED
        for i in range(7):
            learn.consec_losses["BREAKOUT"] = 0
            learn.learn_from_deal(self.deal(-100.0, i=i), None, self.model(), "BREAKOUT", 3000.0 + i)
        assert learn.stage_of("BREAKOUT") == "SUSPENDED"
        ok, why = learn.strategy_allowed("BREAKOUT", 4000.0)
        assert not ok

    def test_consec_losses_suspend_and_revalidate(self):
        learn = LearningEngine()
        for i in range(5):
            learn.learn_from_deal(self.deal(-10.0, i=i), None, self.model(), "ORB", 1000.0 + i)
        assert learn.stage_of("ORB") == "SUSPENDED"
        # suspension timestamped at the 5th loss (ts 1004) → expires after cooldown from then
        ok, _ = learn.strategy_allowed("ORB", 1004.0 + LearningEngine.BREAKER_COOLDOWN_S + 1)
        assert ok
        assert learn.stage_of("ORB") == "INCUBATION"   # revalidation, not instant full size


class TestWebhookSecret:
    def test_verify(self):
        import hashlib
        assert verify_secret("s3cret", "s3cret")
        assert verify_secret(hashlib.sha256(b"s3cret").hexdigest(), "s3cret")
        assert not verify_secret("wrong", "s3cret")
        assert not verify_secret(None, "s3cret")
