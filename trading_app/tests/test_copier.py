"""Trade copier tests: registry limits, sizing modes, open/close/partial/SL
reconciliation, reverse copy, skip tracking, persistence."""
import numpy as np
import pytest

from trading_app.backend.brokers.simulated import SimulatedBroker
from trading_app.backend.config import load_config
from trading_app.backend.copier import TradeCopier
from trading_app.backend.copier.accounts import AccountCfg, MAX_FOLLOWERS
from trading_app.backend.models import Side

CFG = load_config()
EUR = CFG.symbols["EURUSD"]


@pytest.fixture()
def rig(tmp_path):
    master = SimulatedBroker(CFG, seed=5)
    master.price_override["EURUSD"] = 1.0850
    for i in range(20):
        master.step(float(i))
    copier = TradeCopier(CFG, master, store_path=tmp_path / "copier.json")
    return master, copier


def open_master(master, volume=1.0, side=Side.BUY, sl=1.0800, tp=1.0900):
    return master.market_order("EURUSD", side, volume, sl, tp)


class TestRegistry:
    def test_max_ten_accounts(self, rig):
        _, copier = rig
        for i in range(MAX_FOLLOWERS):
            copier.add_account({"label": f"A{i}", "broker_type": "simulated"})
        with pytest.raises(ValueError):
            copier.add_account({"label": "eleven"})

    def test_validation(self, rig):
        _, copier = rig
        with pytest.raises(ValueError):
            copier.add_account({"label": "bad", "mode": "astral"})
        with pytest.raises(ValueError):
            copier.add_account({"label": "bad", "multiplier": 999})

    def test_persistence_roundtrip(self, tmp_path):
        master = SimulatedBroker(CFG, seed=5)
        master.step(0.0)
        store = tmp_path / "copier.json"
        c1 = TradeCopier(CFG, master, store_path=store)
        acc = c1.add_account({"label": "persisted", "mode": "mirror", "multiplier": 2.0})
        c2 = TradeCopier(CFG, master, store_path=store)
        assert acc.id in c2.followers
        assert c2.followers[acc.id].cfg.mode == "mirror"
        assert c2.followers[acc.id].cfg.multiplier == 2.0
        assert c2.followers[acc.id].connected


class TestCopying:
    def test_proportional_sizing(self, rig):
        master, copier = rig
        copier.add_account({"label": "f1", "mode": "proportional", "multiplier": 2.0})
        pos = open_master(master, 1.0)
        copier.on_master_open(pos, master.account().balance, 100.0)
        rt = next(iter(copier.followers.values()))
        fpos = rt.broker.positions()[0]
        # follower equity 25k / master 100k × 1.0 lot × 2.0 mult → 0.5 lot
        assert abs(fpos.volume - 0.50) < 1e-9
        assert fpos.side is Side.BUY
        assert rt.stats["copied"] == 1

    def test_mirror_and_fixed_lot(self, rig):
        master, copier = rig
        copier.add_account({"label": "m", "mode": "mirror", "multiplier": 1.0})
        copier.add_account({"label": "f", "mode": "fixed_lot", "fixed_lots": 0.2, "multiplier": 1.5})
        pos = open_master(master, 2.0)
        copier.on_master_open(pos, master.account().balance, 100.0)
        rts = list(copier.followers.values())
        assert abs(rts[0].broker.positions()[0].volume - 2.0) < 1e-9
        assert abs(rts[1].broker.positions()[0].volume - 0.3) < 1e-9

    def test_master_close_mirrored(self, rig):
        master, copier = rig
        copier.add_account({"label": "f1"})
        pos = open_master(master, 1.0)
        copier.on_master_open(pos, master.account().balance, 100.0)
        rt = next(iter(copier.followers.values()))
        assert len(rt.broker.positions()) == 1
        master.close_position(pos.id, reason="TP")
        copier.step(200.0, master.account().balance)
        assert len(rt.broker.positions()) == 0
        assert rt.stats["closes"] == 1

    def test_partial_close_mirrored_proportionally(self, rig):
        master, copier = rig
        copier.add_account({"label": "f1", "mode": "mirror"})
        pos = open_master(master, 1.0)
        copier.on_master_open(pos, master.account().balance, 100.0)
        rt = next(iter(copier.followers.values()))
        master.close_position(pos.id, 0.4, reason="PARTIAL_TP1")   # 60% remains
        copier.step(200.0, master.account().balance)
        fvols = [p.volume for p in rt.broker.positions()]
        assert fvols and abs(fvols[0] - 0.60) < 1e-6
        assert rt.stats["partials"] == 1

    def test_sl_sync_follows_master(self, rig):
        master, copier = rig
        copier.add_account({"label": "f1"})
        pos = open_master(master, 1.0)
        copier.on_master_open(pos, master.account().balance, 100.0)
        master.modify_stops(pos.id, 1.0840, 1.0950)
        copier.step(200.0, master.account().balance)
        rt = next(iter(copier.followers.values()))
        fpos = rt.broker.positions()[0]
        assert abs(fpos.stop_loss - 1.0840) < 1e-9
        assert abs(fpos.take_profit - 1.0950) < 1e-9
        assert rt.stats["sl_syncs"] >= 1

    def test_reverse_copy(self, rig):
        master, copier = rig
        copier.add_account({"label": "rev", "reverse": True, "mode": "mirror"})
        pos = open_master(master, 1.0, side=Side.BUY, sl=1.0800, tp=1.0900)
        copier.on_master_open(pos, master.account().balance, 100.0)
        rt = next(iter(copier.followers.values()))
        fpos = rt.broker.positions()[0]
        assert fpos.side is Side.SELL
        assert fpos.stop_loss == 1.0900 and fpos.take_profit == 1.0800

    def test_symbol_filter_and_disabled_skips(self, rig):
        master, copier = rig
        copier.add_account({"label": "filt", "symbols": ["XAUUSD"]})
        copier.add_account({"label": "off", "enabled": False})
        pos = open_master(master, 1.0)
        copier.on_master_open(pos, master.account().balance, 100.0)
        rts = list(copier.followers.values())
        assert not rts[0].broker.positions()
        assert rts[0].stats["skipped"].get("symbol_filtered") == 1
        assert not rts[1].broker.positions()
        assert rts[1].stats["skipped"].get("disabled") == 1

    def test_reconcile_catches_missed_open(self, rig):
        master, copier = rig
        copier.add_account({"label": "f1", "mode": "mirror"})
        open_master(master, 0.5)                      # no hook fired
        copier.step(200.0, master.account().balance)  # reconciliation backstop
        rt = next(iter(copier.followers.values()))
        assert len(rt.broker.positions()) == 1
        assert abs(rt.broker.positions()[0].volume - 0.5) < 1e-9

    def test_snapshot_shape(self, rig):
        master, copier = rig
        copier.add_account({"label": "f1"})
        snap = copier.snapshot()
        assert snap["max_followers"] == 10
        assert snap["followers"][0]["cfg" in snap["followers"][0] or "label"]
        assert snap["followers"][0]["connected"]
