from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from altron.backtest.metrics import calculate_metrics, drawdown_series
from altron.backtest.models import BacktestConfig, BacktestResult, Trade
from altron.data_layer.normalization import normalize_ohlcv
from altron.strategies.base import Strategy


def _kelly_sizes(
    target: pd.Series,
    asset_returns: pd.Series,
    lookback: int,
    cap: float,
) -> pd.Series:
    historical = (target * asset_returns).shift(1)
    output = pd.Series(0.0, index=target.index)
    for position in range(lookback, len(target)):
        sample = historical.iloc[position - lookback : position].dropna()
        wins = sample[sample > 0]
        losses = sample[sample < 0]
        if wins.empty or losses.empty:
            continue
        probability = len(wins) / len(sample)
        payoff = wins.mean() / abs(losses.mean())
        fraction = probability - (1 - probability) / payoff if payoff > 0 else 0.0
        output.iloc[position] = min(cap, max(0.0, float(fraction)))
    return output


def _extract_trades(
    frame: pd.DataFrame,
    target: pd.Series,
    exposure: pd.Series,
    asset_returns: pd.Series,
    equity: pd.Series,
    initial_capital: float,
    cost_rate: float,
) -> list[Trade]:
    """Build cost-complete trades from position intervals.

    Target row ``t`` earns the close-to-close return ending at ``t``, so its fill is
    reported at the prior close. Entry, resizing, and exit turnover are allocated to
    the appropriate trade, including both legs of a reversal.
    """
    trades: list[Trade] = []
    directions = np.sign(target.to_numpy()).astype(int)
    start = 0
    while start < len(target):
        direction = directions[start]
        if direction == 0:
            start += 1
            continue
        end = start + 1
        while end < len(target) and directions[end] == direction:
            end += 1

        period_returns: list[float] = []
        for position in range(start, end):
            previous_exposure = 0.0 if position == start else float(exposure.iloc[position - 1])
            turnover = abs(float(exposure.iloc[position]) - previous_exposure)
            period_returns.append(
                float(exposure.iloc[position]) * float(asset_returns.iloc[position])
                - turnover * cost_rate
            )
        if end < len(target):
            period_returns.append(-abs(float(exposure.iloc[end - 1])) * cost_rate)
        factor = float(np.prod(1 + np.clip(period_returns, -0.999999, None)))
        trade_return = factor - 1
        before = initial_capital if start == 0 else float(equity.iloc[start - 1])
        entry_index = max(0, start - 1)
        exit_index = max(entry_index, end - 1)
        trades.append(
            Trade(
                entry_time=pd.Timestamp(frame["timestamp"].iloc[entry_index]),
                exit_time=pd.Timestamp(frame["timestamp"].iloc[exit_index]),
                direction=int(direction),
                entry_price=float(frame["close"].iloc[entry_index]),
                exit_price=float(frame["close"].iloc[exit_index]),
                return_pct=trade_return,
                pnl=before * trade_return,
                bars=end - start,
            )
        )
        start = end
    return trades


class BacktestEngine:
    """Dependency-light vectorized backtester with next-bar signal execution.

    Signals are desired positions, not one-shot orders. Signal ``t`` affects the
    return ending at ``t+1`` by default, with configurable additional delay for
    latency stress tests. This prevents using a candle's close before it exists.
    Commission and slippage are applied to every unit of turnover, so a
    long-to-short reversal costs twice as much as entering from flat.
    """

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run(
        self,
        data: pd.DataFrame,
        strategy: Strategy | None = None,
        params: dict[str, Any] | None = None,
        *,
        signals: pd.Series | None = None,
        metadata: dict[str, object] | None = None,
    ) -> BacktestResult:
        frame = normalize_ohlcv(data)
        if frame.empty:
            raise ValueError("Cannot backtest an empty data set")
        if signals is None:
            if strategy is None:
                raise ValueError("Provide either a strategy or signals")
            signals = strategy(frame, params or {})
        if len(signals) != len(frame):
            raise ValueError("Signal length does not match market data")
        signals = pd.Series(signals.to_numpy(), index=frame.index, name="signal").fillna(0).clip(-1, 1)
        if not self.config.allow_short:
            signals = signals.clip(lower=0)
        delay = self.config.execution_delay_bars if self.config.execute_next_bar else 0
        target = signals.shift(delay).fillna(0) if delay else signals.copy()
        asset_returns = frame["close"].pct_change().fillna(0.0)
        if self.config.position_sizing == "kelly":
            sizes = _kelly_sizes(
                target,
                asset_returns,
                self.config.kelly_lookback,
                min(self.config.max_kelly_fraction, self.config.max_leverage),
            )
        else:
            sizes = pd.Series(self.config.position_fraction, index=frame.index)
        exposure = target * sizes
        cost_rate = (self.config.commission_bps + self.config.slippage_bps) / 10_000

        def returns_for(current_exposure: pd.Series) -> tuple[pd.Series, pd.Series]:
            turnover = current_exposure.diff().abs()
            turnover.iloc[0] = abs(current_exposure.iloc[0])
            strategy_returns = current_exposure * asset_returns - turnover * cost_rate
            return strategy_returns.clip(lower=-0.999999), turnover

        strategy_returns, turnover = returns_for(exposure)
        equity = self.config.initial_capital * (1 + strategy_returns).cumprod()
        if self.config.max_drawdown_stop is not None:
            breached = drawdown_series(equity, self.config.initial_capital) <= -self.config.max_drawdown_stop
            if breached.any():
                first = int(np.flatnonzero(breached.to_numpy())[0])
                exposure.iloc[first + 1 :] = 0.0
                target.iloc[first + 1 :] = 0.0
                strategy_returns, turnover = returns_for(exposure)
                equity = self.config.initial_capital * (1 + strategy_returns).cumprod()
                metadata = {**(metadata or {}), "circuit_breaker_bar": first}
        equity.name = "equity"
        strategy_returns.name = "returns"
        exposure.name = "position"
        trades = _extract_trades(
            frame,
            target,
            exposure,
            asset_returns,
            equity,
            self.config.initial_capital,
            cost_rate,
        )
        metrics = calculate_metrics(
            strategy_returns,
            equity,
            frame["timestamp"],
            trades,
            risk_free_rate=self.config.risk_free_rate,
            annualization_periods=self.config.annualization_periods,
            turnover=float(turnover.sum()),
            initial_equity=self.config.initial_capital,
        )
        return BacktestResult(
            equity=equity,
            returns=strategy_returns,
            positions=exposure,
            trades=trades,
            metrics=metrics,
            signals=signals,
            config=self.config,
            metadata=metadata or {},
        )
