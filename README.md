# Altron Quant

A modular Python 3.11 platform for normalized multi-asset market data, plugin strategies,
look-ahead-safe backtesting, walk-forward optimization, portfolio construction, and **paper-first**
real-time signal distribution.

> **Status:** research and simulated-trading foundation. This software is not investment advice.
> Local virtual mode is the default; linked broker routing is restricted to accounts positively
> identified as demo. Live-money routing is not exposed by the dashboard or standard API.

## What is implemented

- **Data layer:** canonical UTC OHLCV validation, 1m/5m/15m/1h/4h/1d resampling, idempotent
  SQLite WAL cache, optional Parquet export, ccxt, yfinance, Alpaca, and Polygon adapters, rate
  limiting, reconnecting streams, plus dashboard-managed no-key Binance crypto websockets and
  delayed no-key stock/forex polling with curated common-symbol catalogs.
- **Strategy plugins:** registry plus MA crossover, RSI mean reversion, MACD momentum, Bollinger
  breakout/reversion, Donchian breakout, Supertrend, Ichimoku, and session VWAP reversal.
- **No-code rules:** validated JSON/YAML strategy model, nested `all`/`any`/`not` expressions,
  common indicators, and closed-bar multi-timeframe alignment.
- **Pine migration:** fail-closed translator for an auditable Pine v5 subset (`sma`, `ema`, `rsi`,
  crosses, comparisons, entries, and closes), plus timestamped external-signal backtesting for any
  Pine strategy that remains executed by TradingView.
- **Research:** configurable-delay target-position backtester, costs, fixed-fractional/Kelly sizing,
  complete metrics, Monte Carlo, Optuna, and walk-forward analysis; plus a fast parallel two-stage
  Strategy Test mode that searches broad parameter combinations and validates the strongest across
  cost, latency, constraint, chronological, volatility, and worst-market scenarios.
- **Portfolio:** return correlation filter, equal/volatility-parity/Sharpe/min-correlation weights,
  allocation limits, trailing performance rotation, and strategy/portfolio drawdown gates.
- **Paper signals:** closed-candle strategy engine, transition state machine, multi-sleeve virtual
  broker, P&L/streak tracking, Telegram/Discord/log sinks, REST/WebSocket feed, and a signed
  TradingView alert webhook with Python-signal parity status.
- **Broker connectivity:** execution-gated Tradovate demo/live REST and local MetaTrader 5 terminal
  adapters, account/position telemetry, explicit symbol/quantity routing, and dashboard connection
  controls. Connectivity is read-only by default.
- **Operations:** detailed Streamlit command center with candlestick/volume/signal charts, backtest
  and Pine labs, deployment control, equity/P&L/position/fill statistics and broker status; plus
  Docker Compose, Grafana starter provisioning, rotating logs, tests, schema, and a notebook.

## Architecture

```text
ccxt / Alpaca / Polygon / Yahoo       native websocket bars
              |                               |
              v                               v
       normalize + validate  <------ closed-candle gate
              |
       SQLite / Parquet cache
          /             \
 strategy registry       declarative rules / Pine subset
          \             /
 delayed backtest -> sweet spot -> walk-forward gates -> leaderboard
          |                                      |
 Monte Carlo / metrics             correlation + allocation
                                                 |
                            signal state machine + virtual mirror
                              /                  \
                  local virtual fills       verified demo broker
                              \                  /
                    FastAPI / feeds / Telegram / dashboard
```

See [architecture and promotion gates](docs/ARCHITECTURE.md).

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[all,dev]'
cp .env.example .env                 # optional; never commit real keys
pytest
```

Core rule/backtest functionality requires only NumPy, pandas, Pydantic, and PyYAML. Vendor,
Optuna, FastAPI, vectorbt, and dashboard packages are optional extras:

```bash
pip install -e '.[data,optimize]'     # market vendors + Optuna
pip install -e '.[api,dashboard]'     # API + UI
pip install -e '.[vectorbt]'          # optional vectorbt adapter
```

## CLI quickstart

The requested compatibility command works after installation:

```bash
python optimizer.py --strategy supertrend --symbol BTC/USDT --timeframe 1h --optimize
```

For rigorous model selection, use rolling out-of-sample windows rather than a single in-sample
optimization:

```bash
altron --strategy ma_crossover --symbol BTC/USDT --source binance \
  --timeframe 1h --start 2023-01-01T00:00:00+00:00 \
  --walk-forward --train-bars 2000 --test-bars 500 --trials 100
```

Offline data is supported and avoids API credentials:

```bash
altron --input candles.csv --strategy rsi_mean_reversion \
  --params '{period: 14, oversold: 28, overbought: 72}' --monte-carlo 1000
altron --input candles.csv --strategy-file examples/rsi_strategy.yaml --walk-forward \
  --train-bars 1000 --test-bars 250
```

Other commands:

```bash
altron list-strategies
altron pine examples/ma_crossover.pine --format schema -o generated.yaml
altron pine-backtest --input candles.csv --pine examples/ma_crossover.pine
altron pine-backtest --input candles.csv --signals exported-pine-signals.csv
altron strategy-test --input candles.csv --strategy supertrend --trials 500 --workers 8
altron serve                       # telemetry/connectivity FastAPI on :8000
altron dashboard                   # detailed Streamlit command center
altron paper --symbol BTC/USDT --timeframe 1h --source binance --top 5
altron paper --symbol BTC/USDT --timeframe 1h --source binance --use-deployments
```

Optimization uses each strategy's declared search space. `--params` sets fixed parameters for a
plain backtest; `--space` accepts a JSON/YAML search-space override such as
`'{fast_period: {type: int, low: 5, high: 30}, slow_period: {type: int, low: 40, high: 150}, ma_type: [sma, ema]}'`.
Lists are categorical choices; mapped `int`/`float` spaces accept `low`, `high`, optional `step`,
and optional `log`. Every run is recorded in `data/leaderboard.sqlite`; only accepted walk-forward
runs have `robust=1`.

## Fast Strategy Test and parameter sweet spot

```bash
altron strategy-test \
  --input candles.csv \
  --strategy supertrend \
  --trials 500 --workers 8 --retention 0.25 \
  --regime-splits 4 --cost-multiplier 2 --latency-bars 1 \
  --maximum-scenario-drawdown 0.25 \
  --output sweet-spot.json --candidates-output candidates.csv
```

The optimizer first screens every Latin-hypercube candidate in parallel, retains only the strongest
fraction, generates signals once per retained parameter set, and reuses them across all stress
scenarios. It ranks robust candidates using profit, Sharpe/Sortino, worst-case return, drawdown, and
cross-scenario stability—not raw profit alone. The report includes recommended parameters, stable
parameter ranges, a Pareto frontier, every scenario result, and warnings when no candidate passes
all risk gates. The same workflow is available in the dashboard's **Sweet spot test** tab.

See [Strategy Test mode](docs/STRATEGY_TEST_MODE.md) for the scoring model and speed controls.

## Python API

```python
from altron.backtest.engine import BacktestEngine
from altron.backtest.models import BacktestConfig
from altron.strategies.registry import get_strategy

strategy = get_strategy("ma_crossover")
result = BacktestEngine(BacktestConfig(
    commission_bps=5,
    slippage_bps=2,
    position_fraction=0.25,
)).run(candles, strategy, {"fast_period": 20, "slow_period": 80, "ma_type": "ema"})

print(result.metrics)
print([trade.as_dict() for trade in result.trades[-5:]])
```

Signals are **desired positions**: `+1` long, `-1` short, and `0` flat. The default backtester
shifts each signal one bar so a close-derived signal cannot earn that same candle's return.

### Data fetch and cache

```python
from altron.data_layer.cache import MarketDataCache
from altron.data_layer.fetchers import CCXTFetcher
from altron.data_layer.service import MarketDataService

service = MarketDataService(CCXTFetcher("bybit"), MarketDataCache())
candles = await service.get_ohlcv("BTC/USDT", "15m", start=start, end=end)
```

For Alpaca set `ALPACA_API_KEY` and `ALPACA_API_SECRET`; for Polygon set `POLYGON_API_KEY`.
Exchange options can receive ccxt credentials at runtime. Keys are never persisted by Altron.
Yahoo data has interval/lookback restrictions and is best treated as a convenience fallback, not
an execution-grade feed. TradingView scraping is not implemented.

## Rule strategies and Pine migration

The schema is in [`schemas/strategy.schema.json`](schemas/strategy.schema.json), with a complete
example at [`examples/rsi_strategy.yaml`](examples/rsi_strategy.yaml). Rules use named operands:

```yaml
indicators:
  - {name: rsi14, indicator: rsi, period: 14}
long_entry: {left: rsi14, operator: "<", right: 30}
long_exit:  {left: rsi14, operator: ">=", right: 50}
```

Read the [strategy schema guide](docs/STRATEGY_SCHEMA.md) and
[Pine mapping/parity guide](docs/PINE_MAPPING.md). The translator rejects unsupported or
repainting-sensitive features instead of silently producing different trades.

## Paper engine

```python
from altron.live_trading.distribution import CompositeSink, LoggingSink, SignalHub
from altron.live_trading.engine import LivePaperEngine, LiveStrategy
from altron.live_trading.paper import PaperBroker

hub = SignalHub()
engine = LivePaperEngine(
    [LiveStrategy(get_strategy("supertrend"), {"period": 10, "multiplier": 3}, allocation=.05)],
    PaperBroker(max_position_fraction=.10, max_drawdown=.20),
    CompositeSink(LoggingSink(), hub),
)
await engine.process_candle("BTC/USDT", "1h", closed_candle, closed=True)
```

Open/incomplete bars are ignored. Signals are emitted only when a strategy's target state changes;
stale timestamps and duplicate transitions are rejected. `PaperBroker` has no method capable of
sending an exchange order.

`altron paper` loads only `robust=1` leaderboard rows, warms each plugin from cached history, then
consumes the exchange websocket. ccxt streams emit the penultimate candle only after the next bar
proves it closed; Alpaca minute bars are aggregated to the requested timeframe. The worker exposes
its shared signal hub on port 8000 unless `--no-api` is passed, and enables Telegram/Discord sinks
when their environment variables are present. A portfolio drawdown breach liquidates virtual
positions and leaves the broker halted.

## Dashboard, deployments, and live statistics

```bash
altron paper --symbol BTC/USDT --timeframe 1h --source binance --top 5
# In another terminal:
altron dashboard --server.port 8501
```

The command center includes system KPIs, a dark candlestick/volume chart with Python and
TradingView markers, local built-in/declarative backtests, Pine parity, fast sweet-spot testing,
deployments, live statistics, direct in-memory Tradovate/MT5 account linking, a virtual versus
verified broker-demo toggle, and managed free/public market-data subscriptions. `altron paper` exposes the shared runtime API;
set the dashboard API URL to that worker when it is not `http://localhost:8000`.

Deployment records do not place orders. Run the paper worker with `--use-deployments` to load
enabled records whose backend and environment are both paper-compatible. Live records must be
created disabled and cannot be activated by the standard API process.

The sidebar trading toggle distinguishes **Virtual** local synthetic fills from **Broker paper**
demo-account routing. Broker-paper mode requires a connected account positively identified as demo,
an explicit symbol mapping and per-strategy quantity, and the `ENABLE_DEMO_ORDERS` confirmation.
Live and contest accounts are rejected. Set `ALTRON_OPERATOR_TOKEN` on both API and dashboard when
network-exposed. See [trading modes and free feeds](docs/MARKET_DATA_STREAMS.md).

## Tradovate and MetaTrader 5

Read-only connectors are configured from the variables in `.env.example` and shown in the
**Brokers** dashboard tab. Connecting performs authentication, account discovery, and position
reads only. The dashboard and API expose no order endpoint. MetaTrader 5 requires MetaQuotes'
Python package and a local terminal, normally on Windows:

```bash
pip install -e '.[mt5,api,dashboard]'
```

See the [broker connectivity and execution-gate guide](docs/BROKER_CONNECTIVITY.md) before using
either backend. The standard process can temporarily route to a verified demo account through the
explicit dashboard toggle; it rejects live and contest accounts.

## API and TradingView webhook

```bash
export TRADINGVIEW_WEBHOOK_SECRET='use-a-random-secret'
altron serve
```

- `GET /health`, `/overview`, `/portfolio`, `/equity`, `/fills`
- `GET /candles?symbol=BTC%2FUSDT&timeframe=1h`, `/signals`
- `GET|POST|PATCH|DELETE /deployments`
- `GET /brokers`, broker link/connect/account endpoints
- `GET|PATCH /runtime/mode` for virtual versus verified broker-demo routing
- `GET /market/catalog`, `GET|POST|DELETE /market/subscriptions`
- `WS /ws/signals`
- `POST /webhooks/tradingview`

When a secret is set, webhook bodies require
`X-Altron-Signature: sha256=<HMAC-SHA256(raw-body)>`. Alerts are recorded as comparison inputs,
not orders. TradingView alerts require an appropriate TradingView plan and must comply with its
terms.

## Containers

```bash
docker compose up --build api
docker compose --profile dashboard up --build
# Optional starter operations view (configure a metrics datasource for production):
docker compose --profile monitoring up grafana
```

Persistent runtime state uses the `altron-data` volume. Grafana is available on port 3000 and the
Streamlit research dashboard on 8501 when their profiles are enabled.

## Safety and limitations

1. Local virtual execution is the restart-safe default. Broker-paper mode requires a connected,
   adapter-verified demo account and explicit confirmation. Live-money routing remains outside the
   dashboard and requires the separate `Settings.authorize_live_trading` gates in a custom service.
2. Backtest costs are models, not guarantees. Model spread, market impact, funding, borrow fees,
   corporate actions, delistings, partial fills, and exchange-specific lot/notional rules before
   any production deployment.
3. Walk-forward and Monte Carlo reduce, but do not eliminate, overfitting. Correct for the number
   of strategies and parameter sets tested.
4. SQLite is suitable for candle research and a single-node paper service. Use a managed
   TimescaleDB/InfluxDB deployment for high-volume tick storage.
5. The reconnecting stream handles transient failures, but production deployments still need
   vendor sequence-gap detection, backfill, clock monitoring, and operational alerting.

## Native Windows desktop

Install and launch the native PySide6 application:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\pip.exe install -e ".[desktop,data,optimize,mt5]"
.\.venv\Scripts\altron-desktop.exe
```

The desktop keeps non-secret settings under the Windows user profile and stores broker passwords
through Windows Credential Manager. It embeds research, charting, strategy tests, virtual/demo/live
mode controls, public feeds, and broker connectivity in one local process. Local virtual mode is
the restart-safe default. Guarded live mode additionally requires
`ALTRON_ENABLE_LIVE_TRADING=I_UNDERSTAND_THE_RISKS`, typed confirmation, a flat reconciled broker
position, account equity telemetry, maximum order rate, and maximum daily loss.

Build a standalone Windows executable from PowerShell:

```powershell
.\packaging\windows\build.ps1
```

The unrelated legacy Android prototype was removed from this quantitative-trading repository.

## License

MIT. See [LICENSE](LICENSE).
