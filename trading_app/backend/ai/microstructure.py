"""Market microstructure scoring (blueprint 1B).

* Spread quality — tight vs recent median spread (liquidity proxy).
* Order-flow proxy — signed tick imbalance over the recent window
  (bid/ask update cadence standing in for a real depth feed).
"""
from __future__ import annotations

from collections import deque


class MicrostructureEngine:
    def __init__(self, window: int = 60):
        self.spreads: dict[str, deque] = {}
        self.tick_dirs: dict[str, deque] = {}
        self.window = window

    def observe(self, symbol: str, spread: float, tick_dir: int) -> None:
        self.spreads.setdefault(symbol, deque(maxlen=240)).append(spread)
        self.tick_dirs.setdefault(symbol, deque(maxlen=self.window)).append(tick_dir)

    def median_spread(self, symbol: str) -> float:
        s = self.spreads.get(symbol)
        if not s:
            return 0.0
        arr = sorted(s)
        n = len(arr)
        return arr[n // 2] if n % 2 else (arr[n // 2 - 1] + arr[n // 2]) / 2

    def liquidity_score(self, symbol: str, spread: float) -> float:
        med = self.median_spread(symbol)
        if med <= 0 or spread <= 0:
            return 60.0
        ratio = spread / med
        # ratio 1.0 → 100, ratio ≥ 3 → 0
        return max(0.0, min(100.0, (3.0 - ratio) / 2.0 * 100.0))

    def flow_score(self, symbol: str, want_up: bool) -> float:
        dirs = self.tick_dirs.get(symbol)
        if not dirs:
            return 50.0
        net = sum(dirs) / len(dirs)      # −1 … +1
        aligned = net if want_up else -net
        return (aligned + 1.0) / 2.0 * 100.0
