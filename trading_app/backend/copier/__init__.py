"""Trade copier — master → up to 10 follower accounts (MT4/MT5-copier pattern).

Reconciliation architecture (per tetratensor's backend): the copier polls the
master's open positions every engine tick and diffs them against its own
order-pair map, so partial closes, stop moves and new/closing trades are all
mirrored even if a discrete event is ever missed. A direct open-position hook
provides low-latency first fill on new master trades.

Followers can be:
  * simulated paper accounts (default — share the master's price feed with a
    per-follower spread offset), or
  * MetaTrader 5 DEMO terminals (demo-gated MT5DemoBroker per account).
"""
from .copier import TradeCopier
from .accounts import AccountCfg

__all__ = ["TradeCopier", "AccountCfg"]
