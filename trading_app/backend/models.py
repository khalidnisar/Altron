"""Core domain models shared across backend modules.

All dataclasses serialise cleanly to JSON (str-Enums, plain floats).
Prices are raw floats; symbol metadata (`SymbolSpec`) carries digits/pip size.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


class PreservationMode(str, Enum):
    NORMAL = "NORMAL"        # drawdown < 5%
    CAUTIOUS = "CAUTIOUS"    # drawdown >= 5%  → size × 0.50
    REDUCED = "REDUCED"      # drawdown >= 7%  → size × 0.25
    HALTED = "HALTED"        # drawdown >= 10% → emergency stop


class AlertLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class SymbolSpec:
    name: str
    base_price: float
    digits: int
    point: float
    pip: float
    spread_points: float
    slippage_points: float
    contract_size: float
    tick_sigma: float
    quote_usd: float = 1.0   # 1.0 = quote ccy is USD; -1.0 = convert via 1/price

    def round_price(self, p: float) -> float:
        return round(p, self.digits)

    def quote_to_usd(self, price: float) -> float:
        """Multiply a quote-currency amount by this to get USD."""
        return 1.0 if self.quote_usd >= 0 else 1.0 / max(price, 1e-9)

    def value_per_lot(self, price_distance: float, price: float) -> float:
        """USD value of a price move of `price_distance` for 1.0 lot."""
        return abs(price_distance) * self.contract_size * self.quote_to_usd(price)


@dataclass
class Candle:
    symbol: str
    ts: float          # simulated epoch seconds (candle open time)
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Tick:
    symbol: str
    ts: float
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass
class AccountInfo:
    balance: float
    equity: float
    margin_used: float
    free_margin: float
    margin_level: float      # percent; inf when no margin used
    currency: str
    leverage: int
    trade_mode: str = "demo" # adapter must only ever report demo/simulated


@dataclass
class Position:
    id: int
    symbol: str
    side: Side
    volume: float            # lots
    entry_price: float
    entry_ts: float
    stop_loss: float
    take_profit: float

    def floating_pnl(self, spec: SymbolSpec, bid: float, ask: float) -> float:
        exit_px = bid if self.side is Side.BUY else ask
        dist = (exit_px - self.entry_price) * self.side.sign
        return dist * self.volume * spec.contract_size * spec.quote_to_usd(exit_px)


@dataclass
class Deal:
    """A closed (or partially closed) trade record."""
    id: int
    position_id: int
    symbol: str
    side: Side
    volume: float
    entry_price: float
    exit_price: float
    entry_ts: float
    exit_ts: float
    pnl: float
    reason: str              # SL | TP | PARTIAL_TP{n} | TRAIL | BREAKEVEN | TIME_STOP | MANUAL | EMERGENCY


@dataclass
class Signal:
    symbol: str
    side: Side
    ts: float
    confidence: float
    technical: float
    ml: float
    sentiment: float
    microstructure: float
    confluence: int
    regime: str
    strategy: str
    entry: float
    stop_loss: float
    take_profit: float
    atr: float
    size_hint: float = 1.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class RiskDecision:
    approved: bool
    volume_lots: float
    scale_factor: float
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class AlertEvent:
    ts: float
    level: AlertLevel
    code: str
    message: str
    symbol: Optional[str] = None


@dataclass
class RegimeState:
    trend: str               # UP | DOWN | RANGE
    volatility: str          # NORMAL | HIGH | EXTREME
    liquidity: str           # NORMAL | LOW
    adx: float
    atr_pct: float


@dataclass
class SymbolAnalysis:
    """Dashboard-facing per-symbol analysis snapshot (always produced, even
    when no trade signal fires)."""
    symbol: str
    ts: float
    regime: str
    strategy: str
    technical: float
    ml: float
    sentiment: float
    microstructure: float
    confidence: float
    confluence: int
    stance: str              # BUY | SELL | FLAT
    note: str
    tis: float = 0.0         # trend integrity score (directional flow)
    exhaustion: float = 0.0  # trend exhaustion score (directional flow)
