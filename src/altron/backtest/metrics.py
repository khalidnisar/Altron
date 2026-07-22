from __future__ import annotations

import math

import numpy as np
import pandas as pd

from altron.backtest.models import Trade


def periods_per_year(timestamps: pd.Series, override: float | None = None) -> float:
    if override:
        return float(override)
    values = pd.to_datetime(timestamps, utc=True)
    if len(values) < 2:
        return 252.0
    seconds = values.diff().dropna().dt.total_seconds().median()
    return 365.25 * 24 * 3600 / seconds if seconds and seconds > 0 else 252.0


def drawdown_series(equity: pd.Series, initial_equity: float | None = None) -> pd.Series:
    peaks = equity.cummax()
    if initial_equity is not None:
        peaks = peaks.clip(lower=float(initial_equity))
    return equity / peaks - 1.0


def calculate_metrics(
    returns: pd.Series,
    equity: pd.Series,
    timestamps: pd.Series,
    trades: list[Trade],
    *,
    risk_free_rate: float = 0.0,
    annualization_periods: float | None = None,
    turnover: float = 0.0,
    initial_equity: float | None = None,
) -> dict[str, float]:
    clean = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    annual_periods = periods_per_year(timestamps, annualization_periods)
    annual_risk_free = (1 + risk_free_rate) ** (1 / annual_periods) - 1
    excess = clean - annual_risk_free
    volatility = clean.std(ddof=1)
    sharpe = excess.mean() / volatility * math.sqrt(annual_periods) if volatility > 0 else 0.0
    downside = clean[clean < 0].std(ddof=1)
    sortino = excess.mean() / downside * math.sqrt(annual_periods) if downside and downside > 0 else 0.0
    drawdowns = drawdown_series(equity, initial_equity)
    max_drawdown = float(-drawdowns.min()) if not drawdowns.empty else 0.0
    elapsed_years = 0.0
    if len(timestamps) > 1:
        elapsed_years = (pd.Timestamp(timestamps.iloc[-1]) - pd.Timestamp(timestamps.iloc[0])).total_seconds() / (365.25 * 86400)
    starting_equity = float(initial_equity if initial_equity is not None else equity.iloc[0])
    total_return = float(equity.iloc[-1] / starting_equity - 1) if len(equity) else 0.0
    if elapsed_years > 0 and equity.iloc[-1] > 0:
        cagr = float((equity.iloc[-1] / starting_equity) ** (1 / elapsed_years) - 1)
    else:
        cagr = 0.0
    calmar = cagr / max_drawdown if max_drawdown > 0 else 0.0
    trade_returns = np.asarray([trade.return_pct for trade in trades], dtype=float)
    wins = trade_returns[trade_returns > 0]
    losses = trade_returns[trade_returns < 0]
    win_rate = float(len(wins) / len(trade_returns)) if len(trade_returns) else 0.0
    profit_factor = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() else (float("inf") if len(wins) else 0.0)
    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "calmar": float(calmar),
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "annual_volatility": float(volatility * math.sqrt(annual_periods)),
        "turnover": float(turnover),
        "final_equity": float(equity.iloc[-1]) if len(equity) else 0.0,
    }
