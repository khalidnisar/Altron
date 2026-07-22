# Free/public streaming data and dashboard trading modes

## Trading-mode toggle

Run `altron paper ...` and point the dashboard at that worker's API before using broker-paper
routing; standalone `altron serve` can link/read accounts but has no strategy signal loop.

The dashboard sidebar exposes two modes:

- **Virtual simulator** — the default. Signals generate local synthetic fills in `PaperBroker`.
  No external broker receives an order.
- **Broker paper/demo** — signals remain mirrored in the virtual portfolio and may also route to one
  connected account that the adapter has positively identified as **demo**. The operator must map
  the strategy symbol to the broker symbol, set an explicit quantity, check the demo confirmation,
  and apply the toggle.

The controller rejects Tradovate live connections and MT5 accounts identified as live or contest.
Switching back to virtual first submits market orders to flatten every target tracked by this
process; only after all are accepted does it disable the demo execution gate and clear state. A
rejected flatten leaves broker-paper mode enabled for operator intervention. A broker disconnect
forces virtual mode but may require manual broker reconciliation.
The setting is intentionally not persisted across process restarts.

Use the **Brokers** dashboard tab to link an account. Credentials are sent to the API process,
retained only in memory, and never stored in SQLite. Use TLS/HTTPS whenever dashboard and API are
on separate hosts. Set the same `ALTRON_OPERATOR_TOKEN` in the API and dashboard environments to
protect account linking, mode changes, deployment mutations, and stream controls.

## Public and free-account feeds

The **Free market data** tab provides a curated symbol catalog and starts feed subscriptions in the
API process. Closed candles are written to bounded runtime telemetry and become available to the
chart through `/candles`.

### Crypto

Binance public websocket candles through `ccxt.pro` need no API key. Common presets include
BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT, ADA/USDT, DOGE/USDT and AVAX/USDT.
Exchange availability and regional restrictions still apply.

### Stocks and ETFs

No-key mode polls Yahoo through `yfinance` for common symbols such as AAPL, MSFT, NVDA, AMZN,
GOOGL, META, TSLA, SPY, QQQ and DIA. This is delayed research/display data without a streaming SLA;
it must not drive execution. Respect Yahoo's terms and rate limits.

Alpaca's IEX websocket is also supported for users with free-account API keys. Entitlements and
coverage depend on the account and feed selection.

### Forex

No-key mode polls Yahoo's common currency symbols, including EURUSD=X, GBPUSD=X, USDJPY=X,
AUDUSD=X, USDCAD=X, USDCHF=X and NZDUSD=X. It is delayed chart/research data rather than an
execution-grade FX stream. For execution, consume the linked MT5 broker's own prices in a dedicated
broker adapter after validating symbol names and account permissions.

## API

```text
GET    /market/catalog
GET    /market/subscriptions
POST   /market/subscriptions
DELETE /market/subscriptions/{id}
GET    /candles?symbol=AAPL&timeframe=1m

GET    /runtime/mode
PATCH  /runtime/mode
POST   /brokers/tradovate/link
POST   /brokers/mt5/link
```

Example no-key crypto subscription:

```bash
curl -X POST http://localhost:8000/market/subscriptions \
  -H 'Content-Type: application/json' \
  -d '{"asset_class":"crypto","symbol":"BTC/USDT","timeframe":"1m","provider":"auto"}'
```

Example stock polling subscription:

```bash
curl -X POST http://localhost:8000/market/subscriptions \
  -H 'Content-Type: application/json' \
  -d '{"asset_class":"stocks","symbol":"AAPL","timeframe":"5m","provider":"yahoo"}'
```
