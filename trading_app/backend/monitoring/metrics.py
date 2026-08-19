"""Performance metrics (blueprint section 5)."""
from __future__ import annotations

import math


def compute_metrics(deals: list, equity_curve: list[list[float]], start_balance: float) -> dict:
    closed = [d for d in deals if d.get("reason") in
              ("SL", "TP", "TIME_STOP", "MANUAL", "EMERGENCY", "LIQUIDATED")]
    pnls = [float(d["pnl"]) for d in closed]
    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    net = sum(pnls)
    total_ret = ((equity_curve[-1][1] - start_balance) / start_balance * 100.0) if equity_curve else 0.0

    # Sharpe / Sortino on equity-curve deltas (annualisation skipped: intraday sim)
    sharpe = sortino = 0.0
    if len(equity_curve) > 3:
        rets = [equity_curve[i][1] - equity_curve[i - 1][1] for i in range(1, len(equity_curve))]
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
        sd = math.sqrt(var)
        downside = [r for r in rets if r < 0]
        dsd = math.sqrt(sum(r * r for r in downside) / max(len(downside), 1))
        sharpe = mean / sd if sd > 0 else 0.0
        sortino = mean / dsd if dsd > 0 else 0.0

    # drawdown from curve
    peak = start_balance
    max_dd = dd_dur = cur_dur = 0.0
    for _, eq in equity_curve:
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100.0 if peak else 0.0
        if dd > 0:
            cur_dur += 1
        else:
            cur_dur = 0
        max_dd = max(max_dd, dd)
        dd_dur = max(dd_dur, cur_dur)

    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    return {
        "trades": n,
        "net_pnl": round(net, 2),
        "total_return_pct": round(total_ret, 3),
        "win_rate_pct": round(len(wins) / n * 100.0, 1) if n else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else (999.0 if gross_win > 0 else 0.0),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_win_loss_ratio": round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0,
        "expectancy": round(net / n, 2) if n else 0.0,
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "max_drawdown_pct": round(max_dd, 3),
        "drawdown_duration_bars": int(dd_dur),
    }
