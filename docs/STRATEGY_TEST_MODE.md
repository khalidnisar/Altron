# Fast multi-scenario strategy test mode

Strategy Test mode searches for a **stable parameter sweet spot**, not the single combination that
happened to earn the most in one backtest. It is available in the dashboard under **Sweet spot
test** and from `altron strategy-test`.

## Fast two-stage search

1. **Latin-hypercube coverage** spreads candidate values across every numeric range and categorical
   choice more evenly than naive random combinations.
2. **Parallel baseline screening** runs every candidate using a bounded worker pool.
3. Only the strongest configurable fraction (25% by default, with a minimum candidate count) moves
   to expensive stress testing.
4. Each retained candidate generates strategy signals once. Those signals are reused across all
   execution and market scenarios.
5. Scenario evaluations run in parallel. This reduces repeated indicator calculations and avoids
   running obviously weak combinations through every stress case.

For 1,000 requested candidates with 25% retention and nine scenarios, the system performs 1,000
fast baseline screens plus 2,250 scenario backtests instead of 9,000 full scenario tests. Increase
retention toward 100% when exhaustive validation matters more than latency.

## Scenarios

Every retained candidate is evaluated against:

- Baseline commission and slippage
- Multiplied costs
- Additional execution-delay bars
- Long-only constraints when the base strategy permits shorts
- Sequential chronological market regimes
- The highest-volatility contiguous window
- The worst rolling market-return window

All market windows are selected from price data independently of candidate performance. Scenario
metrics include return, CAGR, Sharpe, Sortino, maximum drawdown, profit factor, and turnover.

## Sweet-spot score

Each scenario score rewards total return, CAGR, Sharpe, and Sortino and penalizes drawdown. The
all-scenario score then adds a worst-scenario term and subtracts cross-scenario instability:

```text
robust score = mean(scenario scores)
             + worst-case weight × minimum scenario score
             - instability penalty × stddev(scenario scores)
```

A parameter set is marked robust only if it also passes all configured gates:

- Worst scenario return
- Worst scenario drawdown
- Minimum fraction of profitable scenarios

Robust candidates rank before non-robust candidates. If none pass, the best fallback is displayed
with a rejection warning and must not be promoted automatically.

The report also calculates a profit/Sharpe/drawdown Pareto frontier and stable ranges from the top
20% of fully tested candidates. Prefer the recommended setting near the middle of a broad stable
range over an isolated edge value.

## CLI

```bash
altron strategy-test \
  --input BTCUSDT_1h.csv \
  --strategy supertrend \
  --trials 500 \
  --workers 8 \
  --retention 0.25 \
  --regime-splits 4 \
  --cost-multiplier 2 \
  --latency-bars 1 \
  --profit-weight 2 \
  --drawdown-penalty 3 \
  --maximum-scenario-drawdown 0.25 \
  --minimum-scenario-return -0.10 \
  --minimum-positive-scenarios 0.70 \
  --symbol BTC/USDT \
  --timeframe 1h \
  --output sweet-spot.json \
  --candidates-output candidates.csv
```

Override a built-in search space with YAML:

```yaml
period: {type: int, low: 5, high: 30}
multiplier: {type: float, low: 1.0, high: 6.0, step: 0.25}
```

Lists represent categorical choices. Numeric spaces support `int` or `float`, `low`, `high`, an
optional `step`, and optional logarithmic sampling.

## Performance guidance

- Start with 100–250 candidates and 20–25% retention.
- Set workers near available physical CPU cores. More workers are not always faster because pandas
  operations and memory bandwidth become limiting.
- Use at least several hundred bars; thousands are preferable across market cycles.
- Narrow stable ranges in a second run after broad discovery.
- Keep cost and latency stress enabled. Disabling them makes results faster but less deployable.
- Run final walk-forward analysis and Monte Carlo after sweet-spot discovery. Scenario optimization
  complements rather than replaces unseen out-of-sample validation.
