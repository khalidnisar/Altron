"""Sentiment analysis (blueprint 1B).

Production wiring would pull news/social feeds and an economic calendar.
This standalone build ships a self-contained stochastic sentiment process
per symbol (mean-reverting random walk in [0,100]) plus a simulated
economic-calendar with scheduled high-impact events; events impose a
no-trade blackout window (15 min before / 15 after) matching the
blueprint's "Upcoming economic events" alert + "No trading" rule.
"""
from __future__ import annotations

import numpy as np

MINUTES_PER_DAY = 1440

# Scheduled high-impact events every simulated day: (minute_of_day, label)
DAILY_EVENTS = [
    (510, "EU CPI Flash Estimate"),
    (810, "US Non-Farm Payrolls / CPI"),
    (900, "US FOMC Minutes / Rates"),
]
BLACKOUT_BEFORE_MIN = 15
BLACKOUT_AFTER_MIN = 15


class SentimentEngine:
    def __init__(self, seed: int = 7):
        self.rng = np.random.default_rng(seed)
        self.scores: dict[str, float] = {}
        self._event_bias: dict[int, float] = {}
        self._last_day = -1

    def _roll_day(self, tick: int) -> None:
        day = tick // MINUTES_PER_DAY
        if day != self._last_day:
            self._last_day = day
            self._event_bias = {m: float(self.rng.uniform(-1.0, 1.0)) for m, _ in DAILY_EVENTS}

    def events_today(self, tick: int) -> list[dict]:
        self._roll_day(tick)
        day_start = (tick // MINUTES_PER_DAY) * MINUTES_PER_DAY
        return [{"tick": day_start + m, "label": lbl, "bias": self._event_bias.get(m, 0.0)}
                for m, lbl in DAILY_EVENTS]

    def blackout_active(self, tick: int) -> dict | None:
        """Return the active event dict when inside a blackout window."""
        for ev in self.events_today(tick):
            if ev["tick"] - BLACKOUT_BEFORE_MIN <= tick <= ev["tick"] + BLACKOUT_AFTER_MIN:
                return ev
        return None

    def upcoming_event(self, tick: int, within_min: int = 60) -> dict | None:
        for ev in self.events_today(tick):
            if 0 <= ev["tick"] - tick <= within_min:
                return ev
        return None

    def score(self, symbol: str, tick: int) -> float:
        self._roll_day(tick)
        s = self.scores.get(symbol, 50.0)
        step = float(self.rng.normal(0.0, 1.6)) + (50.0 - s) * 0.02
        ev = self.blackout_active(tick)
        if ev:  # event shock pushes sentiment by the day's bias
            step += ev["bias"] * 4.0
        s = min(max(s + step, 0.0), 100.0)
        self.scores[symbol] = s
        return s
