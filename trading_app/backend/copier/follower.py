"""Follower broker — a simulated account that shadows the master's price feed
(with a small per-follower spread offset, resembling a different brokerage)
while keeping its own positions, margin, funding and liquidation engine."""
from __future__ import annotations

from ..brokers.simulated import SimulatedBroker, _SymbolState
from ..config import AppConfig
from ..models import Tick


class FollowerBroker(SimulatedBroker):
    name = "follower-sim"

    def __init__(self, cfg: AppConfig, seed: int, balance: float,
                 spread_factor: float = 1.0):
        super().__init__(cfg, seed=seed)
        self.balance = float(balance)
        self.spread_factor = spread_factor
        self.master: SimulatedBroker | None = None

    def attach_feed(self, master_broker) -> None:
        self.master = master_broker

    def step(self, ts: float) -> dict[str, int]:
        dirs: dict[str, int] = {}
        if self.master is not None:
            for name, st in self.states.items():
                mstate: _SymbolState = self.master.states[name]
                prev = st.mid
                st.mid = mstate.mid
                st.spread = mstate.spread * self.spread_factor
                st.median_spread = st.spread
                st.last_tick = Tick(name, ts, st.spec.round_price(st.mid - st.spread / 2),
                                    st.spec.round_price(st.mid + st.spread / 2))
                self._update_funding(st)
                dirs[name] = 1 if st.mid > prev else (-1 if st.mid < prev else 0)
        self._process_stops(ts)
        self._accrue_funding(ts)
        self._process_liquidations(ts)
        return dirs
