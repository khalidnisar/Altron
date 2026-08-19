"""Risk engine tests: sizing, limits, preservation tiers, validation gates."""
from trading_app.backend.config import load_config
from trading_app.backend.models import AccountInfo, Position, PreservationMode, Side, Signal
from trading_app.backend.risk import RiskEngine
from trading_app.backend.risk.sizing import fixed_fractional_lots, kelly_criterion_pct, round_lots

CFG = load_config()
EUR = CFG.symbols["EURUSD"]


def account(equity=100_000.0, balance=100_000.0, margin_used=0.0, margin_level=99999.0):
    return AccountInfo(balance=balance, equity=equity, margin_used=margin_used,
                       free_margin=equity - margin_used, margin_level=margin_level,
                       currency="USD", leverage=100)


def signal(side=Side.BUY, entry=1.0850, sl=1.0835, tp=1.0885, conf=80.0, symbol="EURUSD"):
    return Signal(symbol=symbol, side=side, ts=0.0, confidence=conf,
                  technical=80, ml=80, sentiment=80, microstructure=80,
                  confluence=4, regime="UP/NORMAL/NORMAL", strategy="BREAKOUT",
                  entry=entry, stop_loss=sl, take_profit=tp, atr=0.001)


class TestSizing:
    def test_fixed_fractional_math(self):
        # $100,000 × 1% risk, 50-pip stop on EURUSD ($10/pip/lot) → 2.0 lots
        lots = fixed_fractional_lots(100_000, 1.0, EUR, 1.0850, 1.0800)
        assert abs(lots - 2.0) < 1e-9

    def test_zero_stop_distance_gives_zero(self):
        assert fixed_fractional_lots(100_000, 1.0, EUR, 1.0850, 1.0850) == 0.0

    def test_kelly(self):
        assert kelly_criterion_pct(55, 200, 100) > 0
        assert kelly_criterion_pct(30, 100, 200) == 0.0   # negative expectancy
        assert kelly_criterion_pct(0, 200, 100) == 0.0

    def test_round_lots_min(self):
        assert round_lots(0.004, 0.01, 20, 0.01) == 0.0
        assert round_lots(1.234, 0.01, 20, 0.01) == 1.23


class TestPreservation:
    def test_drawdown_tiers(self):
        r = RiskEngine(CFG)
        r.peak_equity = 100_000
        r.update(10, 96_000, 0.0)
        assert r.mode == PreservationMode.NORMAL
        r.update(11, 94_500, 0.0)
        assert r.mode == PreservationMode.CAUTIOUS
        r.update(12, 92_500, 0.0)
        assert r.mode == PreservationMode.REDUCED
        r.update(13, 89_500, 0.0)
        assert r.mode == PreservationMode.HALTED
        assert r.trading_blocked

    def test_halted_needs_recovery_below_7pct(self):
        r = RiskEngine(CFG)
        r.peak_equity = 100_000
        r.update(10, 89_000, 0.0)
        assert r.mode == PreservationMode.HALTED
        r.update(11, 93_500, 0.0)          # 6.5% dd — recovers to CAUTIOUS, not NORMAL
        assert r.mode == PreservationMode.CAUTIOUS

    def test_daily_loss_halt_and_reset(self):
        r = RiskEngine(CFG)
        r.update(10, 98_300, 0.0)
        r.day_start_balance = 100_000      # loss from day start = 2%
        r.update(100, 98_000, 0.0)
        assert r.daily_loss_halt
        assert r.trading_blocked
        r.update(1440, 98_000, 0.0)        # next sim-day rolls
        assert not r.daily_loss_halt

    def test_scale_factors(self):
        r = RiskEngine(CFG)
        r.peak_equity = 100_000
        r.update(1, 94_000, 0.0)
        scale, notes = r.size_scale()
        assert scale == 0.5 and notes
        r.update(2, 92_000, 0.0)
        scale, _ = r.size_scale()
        assert scale == 0.25


class TestValidation:
    def test_valid_trade_approved(self):
        r = RiskEngine(CFG)
        r.update(1, 100_000, 0.0)
        d = r.validate_trade(signal(), account(), [], EUR, spread_price=EUR.point * 12)
        assert d.approved and d.volume_lots > 0

    def test_rr_rejected(self):
        r = RiskEngine(CFG)
        r.update(1, 100_000, 0.0)
        bad = signal(tp=1.0865)            # 15-pip TP vs 15-pip SL → R:R 1:1
        d = r.validate_trade(bad, account(), [], EUR, spread_price=EUR.point * 12)
        assert not d.approved
        assert any("R:R" in b for b in d.blockers)

    def test_no_stop_rejected(self):
        r = RiskEngine(CFG)
        r.update(1, 100_000, 0.0)
        d = r.validate_trade(signal(sl=0.0), account(), [], EUR, spread_price=0.0)
        assert not d.approved
        assert any("RULE 2" in b for b in d.blockers)

    def test_max_positions(self):
        r = RiskEngine(CFG)
        r.update(1, 100_000, 0.0)
        pos = [Position(id=i, symbol="GBPUSD", side=Side.BUY, volume=1.0,
                        entry_price=1.27, entry_ts=0, stop_loss=1.26, take_profit=1.29)
               for i in range(1, 6)]
        d = r.validate_trade(signal(), account(), pos, EUR, spread_price=EUR.point * 12)
        assert not d.approved and any("max concurrent" in b for b in d.blockers)

    def test_duplicate_symbol_blocked(self):
        r = RiskEngine(CFG)
        r.update(1, 100_000, 0.0)
        pos = [Position(id=1, symbol="EURUSD", side=Side.BUY, volume=1.0,
                        entry_price=1.08, entry_ts=0, stop_loss=1.07, take_profit=1.10)]
        d = r.validate_trade(signal(), account(), pos, EUR, spread_price=EUR.point * 12)
        assert not d.approved and any("already open" in b for b in d.blockers)

    def test_correlation_exposure_blocked(self):
        r = RiskEngine(CFG)
        r.update(1, 100_000, 0.0)
        # Already long EURUSD + long GBPUSD (both short-USD) → a third short-USD trade breaches cap 2
        pos = [
            Position(id=1, symbol="EURUSD", side=Side.BUY, volume=1.0, entry_price=1.08,
                     entry_ts=0, stop_loss=1.07, take_profit=1.10),
            Position(id=2, symbol="GBPUSD", side=Side.BUY, volume=1.0, entry_price=1.27,
                     entry_ts=0, stop_loss=1.26, take_profit=1.29),
        ]
        d = r.validate_trade(signal(side=Side.SELL, symbol="USDJPY", entry=152.30,
                                    sl=152.60, tp=151.70), account(), pos, EUR,
                             spread_price=EUR.point * 12)
        assert not d.approved and any("correlation" in b for b in d.blockers)

    def test_emergency_blocks_everything(self):
        r = RiskEngine(CFG)
        r.update(1, 100_000, 0.0)
        r.emergency_stop("test")
        d = r.validate_trade(signal(), account(), [], EUR, spread_price=0.0)
        assert not d.approved and any("EMERGENCY" in b for b in d.blockers)

    def test_wide_spread_liquidity_block(self):
        r = RiskEngine(CFG)
        r.update(1, 100_000, 0.0)
        d = r.validate_trade(signal(), account(), [], EUR, spread_price=0.001)  # 10 pips vs 15-pip stop
        assert not d.approved and any("liquidity" in b for b in d.blockers)
