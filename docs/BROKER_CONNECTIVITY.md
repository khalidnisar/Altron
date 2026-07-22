# Tradovate and MetaTrader 5 connectivity

Altron separates **connectivity** from **execution**. Linking initially reads account and position
data. Broker adapters default to `execution_enabled=False`, credentials remain in process memory,
and dashboard deployment records are configuration—not orders. The dashboard may enable order
routing only through its **Broker paper/demo** toggle after the adapter positively identifies a
demo account; live and contest accounts are rejected.

## Tradovate

`TradovateBackend` supports the demo and live REST domains. Demo is the default. It obtains an
access token from `auth/accesstokenrequest` when credentials are supplied, sends the token through
the Bearer authorization scheme, discovers accounts with `account/list`, reads `position/list`,
and implements the vendor `order/placeorder` payload behind Altron's explicit execution gate.

Official references:

- [Tradovate access-token request](https://partner.tradovate.com/api/rest-api-endpoints/authentication/access-token-request)
- [Tradovate authentication overview](https://partner.tradovate.com/overview/quick-setup/auth-overview)
- [Tradovate websocket management](https://partner.tradovate.com/overview/conformance-testing/stage-2-websocket-management)

Configure read-only connectivity:

```bash
export TRADOVATE_ENV=demo
export TRADOVATE_ACCESS_TOKEN='short-lived-token'
# Or supply username/password/app credentials through the variables in .env.example.
altron serve
```

Open **Brokers** in the dashboard and click **Connect**. Tokens remain in process memory and are
not written to SQLite. Tradovate access tokens expire; long-running deployments should supply
renewable credentials or use an operator-managed token service. Confirm API entitlements,
automated-order permissions, device approval, contract symbols, account IDs, market-data
subscriptions, and exchange rules with Tradovate before considering execution.

## MetaTrader 5

`MT5Backend` lazily loads MetaQuotes' `MetaTrader5` Python package and communicates with a locally
installed terminal. This is normally a Windows deployment. It calls `initialize`, `account_info`,
`positions_get`, `symbol_info`, `symbol_info_tick`, `order_check`, and—only after the execution
gate—`order_send`.

Official references:

- [MetaTrader 5 Python integration](https://www.mql5.com/en/docs/python_metatrader5)
- [initialize](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py)
- [order_send](https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py)

```powershell
pip install -e ".[mt5,api,dashboard]"
$env:MT5_ENABLE_CONNECTOR="true"
$env:MT5_TERMINAL_PATH="C:\Program Files\MetaTrader 5\terminal64.exe"
$env:MT5_LOGIN="12345678"
$env:MT5_SERVER="Broker-Demo"
altron serve
```

Store the password in a secret manager or process environment. The terminal must be running,
logged into the intended account, and configured to permit Python connectivity. Symbol suffixes,
minimum/maximum lot size, volume step, filling mode, hedging/netting behavior, and market hours are
broker-specific. Altron validates symbol visibility and volume bounds, runs `order_check`, and
checks the final `order_send` return code; these checks still do not guarantee a fill.

## Explicit execution integration

The standard API exposes no arbitrary order endpoint. The paper worker's mode controller may
temporarily enable an adapter only after it is connected and reports `environment=demo`; it routes
strategy target deltas for one explicit symbol/quantity and mirrors them in the virtual portfolio.
Switching to virtual or disconnecting disables that gate.

A custom **live-money** execution process must instead:

1. Call `Settings.authorize_live_trading(explicit_flag=True)` and satisfy its environment
   acknowledgement.
2. Construct exactly one live backend with `execution_enabled=True` outside the dashboard mode
   controller.
3. Provide explicit per-symbol quantity and symbol mappings to `BrokerExecutionRouter`.
4. Reconcile broker positions before routing the first signal and after every rejection or partial
   fill.
5. Implement contract expiry/roll rules, lot and tick validation, idempotent client order IDs,
   session calendars, kill switches, and external monitoring.
6. Start in Tradovate demo or an MT5 demo account and complete broker conformance testing.

The included router tracks accepted target deltas in process memory. It is not a complete
production order-management system and must not be treated as one without durable reconciliation.
