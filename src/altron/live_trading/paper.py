from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from altron.live_trading.models import PaperFill, SignalEvent


@dataclass(slots=True)
class PaperPosition:
    quantity: float = 0.0
    average_price: float = 0.0
    realized_pnl: float = 0.0
    entry_commission: float = 0.0


class PaperBroker:
    """In-memory mark-to-market broker. It has no live-order transport by design."""

    def __init__(
        self,
        initial_cash: float = 100_000,
        *,
        commission_bps: float = 5,
        slippage_bps: float = 2,
        max_position_fraction: float = 0.10,
        max_drawdown: float = 0.20,
    ) -> None:
        if initial_cash <= 0 or not 0 < max_position_fraction <= 1:
            raise ValueError("Invalid paper portfolio configuration")
        self.cash = float(initial_cash)
        self.initial_cash = float(initial_cash)
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        self.max_position_fraction = max_position_fraction
        self.max_drawdown = max_drawdown
        self.positions: dict[tuple[str, str], PaperPosition] = {}
        self.marks: dict[str, float] = {}
        self.fills: list[PaperFill] = []
        self.peak_equity = float(initial_cash)
        self.halted = False
        self.win_streak = 0
        self.loss_streak = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0

    @property
    def equity(self) -> float:
        market_value = sum(
            position.quantity * self.marks.get(symbol, position.average_price)
            for (strategy, symbol), position in self.positions.items()
        )
        return self.cash + market_value

    def mark(self, symbol: str, price: float) -> float:
        if price <= 0:
            raise ValueError("Mark price must be positive")
        self.marks[symbol] = float(price)
        equity = self.equity
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = 1 - equity / self.peak_equity if self.peak_equity else 0
        if drawdown >= self.max_drawdown:
            self.halted = True
        return equity

    def apply_signal(
        self,
        event: SignalEvent,
        *,
        allocation: float | None = None,
        _risk_liquidation: bool = False,
    ) -> PaperFill | None:
        self.mark(event.symbol, event.entry_price)
        if self.halted and not _risk_liquidation:
            return None
        fraction = min(
            self.max_position_fraction if allocation is None else allocation,
            self.max_position_fraction,
        )
        if fraction < 0:
            raise ValueError("allocation cannot be negative")
        key = (event.strategy, event.symbol)
        position = self.positions.setdefault(key, PaperPosition())
        target_notional = self.equity * fraction * event.signal
        target_quantity = target_notional / event.entry_price
        delta = target_quantity - position.quantity
        if abs(delta) < 1e-12:
            return None
        side = "buy" if delta > 0 else "sell"
        execution_price = event.entry_price * (
            1 + self.slippage_bps / 10_000 if delta > 0 else 1 - self.slippage_bps / 10_000
        )
        commission = abs(delta * execution_price) * self.commission_bps / 10_000
        realized = 0.0
        net_realized = 0.0
        old_quantity = position.quantity
        opening_commission = commission
        # Realize only the portion that closes an existing side and allocate both
        # its original entry cost and this fill's proportional closing cost.
        if old_quantity and old_quantity * delta < 0:
            closed = min(abs(old_quantity), abs(delta))
            realized = closed * (execution_price - position.average_price) * (
                1 if old_quantity > 0 else -1
            )
            entry_cost = position.entry_commission * closed / abs(old_quantity)
            closing_commission = commission * closed / abs(delta)
            opening_commission = commission - closing_commission
            position.entry_commission -= entry_cost
            net_realized = realized - entry_cost - closing_commission
            position.realized_pnl += net_realized
            if net_realized > 0:
                self.win_streak += 1
                self.loss_streak = 0
                self.winning_trades += 1
                self.gross_profit += net_realized
            elif net_realized < 0:
                self.loss_streak += 1
                self.win_streak = 0
                self.losing_trades += 1
                self.gross_loss += abs(net_realized)
        new_quantity = old_quantity + delta
        if old_quantity == 0 or old_quantity * new_quantity < 0:
            position.average_price = execution_price
            position.entry_commission = opening_commission
        elif old_quantity * delta > 0:
            position.average_price = (
                abs(old_quantity) * position.average_price + abs(delta) * execution_price
            ) / abs(new_quantity)
            position.entry_commission += commission
        elif new_quantity == 0:
            position.average_price = 0.0
            position.entry_commission = 0.0
        self.cash -= delta * execution_price + commission
        position.quantity = new_quantity
        fill = PaperFill(
            timestamp=event.timestamp,
            strategy=event.strategy,
            symbol=event.symbol,
            side=cast(Literal["buy", "sell"], side),
            quantity=abs(delta),
            price=execution_price,
            commission=commission,
            realized_pnl=net_realized - opening_commission,
        )
        self.fills.append(fill)
        self.mark(event.symbol, event.entry_price)
        return fill

    def snapshot(self) -> dict[str, object]:
        """Return JSON-safe live portfolio and trade statistics."""
        equity = self.equity
        drawdown = 1 - equity / self.peak_equity if self.peak_equity else 0.0
        position_rows: list[dict[str, object]] = []
        unrealized_total = 0.0
        for (strategy, symbol), position in self.positions.items():
            if abs(position.quantity) < 1e-12:
                continue
            mark = self.marks.get(symbol, position.average_price)
            unrealized = position.quantity * (mark - position.average_price)
            unrealized_total += unrealized
            position_rows.append(
                {
                    "strategy": strategy,
                    "symbol": symbol,
                    "side": "long" if position.quantity > 0 else "short",
                    "quantity": position.quantity,
                    "average_price": position.average_price,
                    "mark_price": mark,
                    "market_value": position.quantity * mark,
                    "unrealized_pnl": unrealized,
                    "realized_pnl": position.realized_pnl,
                }
            )
        # Preserve realized P&L from already-closed sleeves too.
        realized_total = sum(position.realized_pnl for position in self.positions.values())
        completed = self.winning_trades + self.losing_trades
        return {
            "initial_cash": self.initial_cash,
            "cash": self.cash,
            "equity": equity,
            "peak_equity": self.peak_equity,
            "net_pnl": equity - self.initial_cash,
            "return_pct": equity / self.initial_cash - 1,
            "drawdown": drawdown,
            "halted": self.halted,
            "open_positions": len(position_rows),
            "positions": position_rows,
            "fills": len(self.fills),
            "realized_pnl": realized_total,
            "unrealized_pnl": unrealized_total,
            "total_commission": sum(fill.commission for fill in self.fills),
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.winning_trades / completed if completed else 0.0,
            "profit_factor": self.gross_profit / self.gross_loss if self.gross_loss else None,
            "win_streak": self.win_streak,
            "loss_streak": self.loss_streak,
        }

    def liquidate_all(self, prices: dict[str, float] | None = None) -> list[PaperFill]:
        prices = prices or self.marks
        fills: list[PaperFill] = []
        was_halted = self.halted
        self.halted = False
        for (strategy, symbol), position in list(self.positions.items()):
            if not position.quantity:
                continue
            event = SignalEvent(
                timestamp=datetime.now(UTC), symbol=symbol, timeframe="risk",
                strategy=strategy, signal=0, confidence=1, entry_price=prices[symbol],
                params={"reason": "liquidation"},
            )
            fill = self.apply_signal(event, _risk_liquidation=True)
            if fill:
                fills.append(fill)
        self.halted = was_halted
        return fills
