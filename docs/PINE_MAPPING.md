# Pine Script to Python mapping

Altron does **not** execute Pine Script. Pine is a TradingView language with broker-emulator,
bar-state, and repainting semantics that cannot safely be reproduced by executing arbitrary
source. `altron pine` translates a small, reviewable Pine v5 subset into the declarative rule
schema. Unsupported constructs fail closed.

## Supported mapping

| Pine v5 | Altron |
|---|---|
| `ta.sma(close, n)` | `moving_average(close, n, "sma")` |
| `ta.ema(close, n)` | `moving_average(close, n, "ema")` |
| `ta.rsi(close, n)` | Wilder-smoothed `rsi(close, n)` |
| `ta.crossover(a, b)` | `crosses_above` (current and prior bar) |
| `ta.crossunder(a, b)` | `crosses_below` (current and prior bar) |
| `strategy.entry(..., strategy.long)` | desired position `+1` |
| `strategy.entry(..., strategy.short)` | desired position `-1` |
| `strategy.close(...)` | desired position `0` |

Simple `>`, `>=`, `<`, and `<=` conditions are supported. See
[`examples/ma_crossover.pine`](../examples/ma_crossover.pine).

```bash
altron pine examples/ma_crossover.pine --format schema -o generated.yaml
altron pine examples/ma_crossover.pine --format python -o generated_strategy.py
```

## Testing any Pine strategy through exported targets

Pine's complete runtime cannot be embedded in Python. For scripts outside the supported subset,
export timestamped target positions or alert events from TradingView:

```csv
timestamp,signal
2025-01-02T10:00:00Z,buy
2025-01-02T14:00:00Z,flat
2025-01-03T09:00:00Z,sell
```

Then use the dashboard **Pine lab** or:

```bash
altron pine-backtest --input candles.csv --signals tradingview-signals.csv \
  --commission-bps 5 --slippage-bps 2 --trades-output pine-trades.csv
```

Sparse targets are carried forward. Every signal timestamp must exactly match a candle timestamp;
Altron does not silently round, shift, or guess timezones. This external-signal route works with
any Pine strategy because TradingView remains the interpreter. It also means exported signals may
already contain repainting, look-ahead, bar-magnifier, or intrabar assumptions; review those
settings before comparing results.

## Semantic differences to review

1. Altron signals are target positions and execute one bar later in backtests by default.
2. TradingView's intrabar order-fill assumptions are not translated.
3. Higher-timeframe values in Altron are shifted until the higher candle has closed.
4. `request.security`, arrays/matrices, `strategy.order`, custom loops, and arbitrary Pine
   functions are rejected. Translate these manually and add parity tests.
5. Compare at least several hundred timestamped signals against TradingView before research
   promotion. The webhook API reports `match`, `mismatch`, or `no_python_signal` for side-by-side
   checks.

Indicator implementations intentionally use pandas rather than requiring TA-Lib. Small seed and
warm-up differences can occur. Capture fixtures exported through a ToS-compliant route and set an
explicit tolerance when validating numerical parity.
