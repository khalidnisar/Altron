# Architecture and promotion gates

```text
REST/websocket vendors -> normalization -> SQLite/Parquet cache
                                      |-> strategy registry / rule engine
                                      |-> configurable-delay backtester -> Optuna/random search
                                      |-> fast multi-scenario sweet spot -> rolling walk-forward
                                      |-> Monte Carlo -> leaderboard
leaderboard robust runs -> correlation filter -> allocator -> closed live candles
                                      |-> signal state machine -> paper broker
                                      |-> REST/WebSocket, Telegram, Discord
                                      |-> runtime telemetry -> detailed dashboard
                                      |-> virtual/demo mode controller -> Tradovate / MT5
public Binance WS / Yahoo polling -> managed feed subscriptions -> chart telemetry
TradingView alerts -> signed FastAPI webhook -> parity comparison only
Dashboard deployment records -> paper worker configuration (never orders by themselves)
```

## Promotion policy

A single optimized backtest is always marked non-robust. Strategy Test mode identifies stable
profit/risk neighborhoods across cost, latency, constraint, and market scenarios, but it still uses
known data. A candidate becomes eligible for paper trading only when the subsequent walk-forward
analyzer has enough folds, its positive OOS Sharpe ratio passes the threshold, and OOS score
degradation is acceptable. Operators should additionally run block
bootstrap Monte Carlo, inspect parameter stability, and account for multiple-hypothesis testing.
No automatic path from research to a live-money broker exists in this release.

## Plugin extension

Subclass `altron.strategies.base.Strategy`, define a unique `name`, and return a `pandas.Series`
containing only -1/0/+1. Register with `@register_strategy`, or publish the class through the
`altron.strategies` Python entry-point group. Inputs are normalized before every plugin call.

## Data contract

Every source produces sorted, de-duplicated UTC `timestamp`, `open`, `high`, `low`, `close`, and
`volume`. Prices must be positive, volume non-negative, and high/low must enclose open and close.
SQLite uses `(source, symbol, timeframe, timestamp)` as its primary key and WAL mode for concurrent
readers. Vendor credentials are environment variables and are never written to the cache.
