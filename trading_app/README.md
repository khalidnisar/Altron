# ⚡ ALTRON AutoTrade — Advanced Automated Trading App

A standalone, production-shaped implementation of the **Advanced Automated Trading App
blueprint**: an AI-driven trading engine with a multi-layer risk-management core, a
paper-first execution venue, a demo-gated MetaTrader 5 adapter, and a real-time web
command center.

> **Safety posture:** simulated/paper trading by default. The MT5 adapter hard-refuses
> any account that is not positively identified as DEMO. Live-money routing is not
> implemented anywhere in this codebase. Not investment advice.

## Quick start

```bash
pip install -r trading_app/requirements.txt
python -m trading_app.run            # serves http://localhost:8100
```

Environment overrides: `TRADING_PORT`, `TRADING_CONFIG`, `TRADING_BROKER`
(`auto` | `simulated` | `mt5_demo`).

## Architecture (blueprint §System Overview)

```
Dashboard UI (web/)          Risk Engine (risk/)         Monitoring (monitoring/)
       │ WebSocket /ws              │ validate/size/scale         │ alerts + metrics
       └──────────────┬─────────────┴───────────────┬─────────────┘
                      ▼                              ▼
   ┌──────────────────── LangGraph AGENT GRAPH (backend/graph/) ────────────────────┐
   │  market_state ─► research ─► risk_gate ─╮       ╭─► learning ─► END            │
   │  (multi-TF structure,                   ├──PASS─►│    (rejection feedback)      │
   │   liq pools, funding, regime)           │       ▼                              │
   │                                         │   execution ─► END                   │
   │  Side-car learning loop: every closed   └────────► managed by execution engine  │
   │  deal → learn_from_deal(): ML refit, strategy circuit breakers, adaptive        │
   │  confidence threshold, liquidation capture.                                     │
   └─────────────────────────────────────────────────────────────────────────────────┘
              AI Trading Engine (ai/)        Execution Engine (execution/)
       technical · ML ensemble ·         orders · partial TP · BE ·
       sentiment · microstructure ·      trailing · time stops · P&L
       regime-adaptive strategies
                      │
              Broker Layer (brokers/)
        SimulatedBroker (default)  ·  MT5DemoBroker (demo-only gate)
                      ▼
             MetaTrader 5 terminal
```

## Agent graph (LangGraph)

Every closed candle runs one `StateGraph` invocation per symbol:

| Node | Responsibility |
| --- | --- |
| `market_state` | Multi-TF structure (M15/H1/H4 swing maps, HH/HL vs LH/LL, BOS/CHoCH), HTF alignment score, liquidation-pool estimation (swing/equal highs-lows with strength), funding rate, regime |
| `research` | Confluence hypothesis (T/ML/Sentiment/Micro), **RULE 12** counter-HTF guard, strategy circuit-breaker gate, adaptive confidence threshold |
| `risk_gate` | Pass/fail condition node: sizing (fixed-fractional + half-Kelly), hard limits, correlation exposure, R:R, margin, liquidity |
| `execution` | Order placement with mandatory hard SL/TP; broker rejections feed back to learning |
| `learning` | Rejected setups are logged as feedback signal (block-reason histograms) |

The feedback loop closes on every **closed deal** via `learn_from_deal()`:
1. Online ML refit (did price actually move as predicted from the entry features?)
2. Strategy circuit breaker — rolling PF < 0.8 over ≥ 8 trades suspends a strategy for 6 sim-hours, then auto re-enables
3. Adaptive confidence threshold (±5 around the 70 base, tightened further on any captured **liquidation**)

## Merged community-repo features

| Source | What we took | Where |
| --- | --- | --- |
| `peridotfoundation/MT5-Directional-Flow-Dashboard` | Re-implemented its core concepts natively: **Trend Integrity Score** (Kaufman efficiency ratio + momentum consistency + multi-horizon acceleration + counter-trend "heartbeat"), **exhaustion detection** (rejection wicks + RSI/price divergence + vol expansion), **per-asset personality** (vol-ratio confidence bias) | `backend/ai/flow.py`, wired into the graph's `research` node: TIS ≥ 70 aligned entries get a bounded confidence boost; exhaustion ≥ 75 vetoes with-trend entries; dashboard TIS/EXH gauges |
| `Kaltorim/MT5-Trend-Direction-Predictor` | The bridge protocol: direction-alias normalization (`BUY/LONG/BULL/BULLISH/STRONG_BUY → BUY…`), multi-field payload reading (`signal/direction/trend/side/recommendation`), per-symbol filtering | `backend/external.py` + `POST /api/signals/external` — payloads are wrapped with ATR hard stops and forced through `risk_gate → execution` (never blind-executed) |
| `tetratensor/MT4-MT5-Trade-Copier-Backend` | The copier architecture: master/copier role registry, **order-pair contracts**, poll-based reconciliation (open/resize/close/SL-TP sync), proportional / lot-multiplier / fixed-lot sizing with force min/max | `backend/copier/` + copier REST API + dashboard section |
| `khalidnisar/Altron-Sword` | **Strategy pack** (ORB opening-range breakout, ROC momentum, parallel-channel fade + channel detector, order-flow delta imbalance) as regime-validated confluence votes; **session clock** (UTC sydney/tokyo/london/new_york + overlap, liquidity-aware size scaling); **strategy lifecycle plane** (INCUBATION → ACTIVE → PROBATION → SUSPENDED with versioned promotion/demotion gates, staged size scaling, revalidation re-entry); **webhook shared-secret/HMAC auth** | `backend/ai/sword_pack.py`, `backend/ai/sessions.py`, lifecycle upgrade in `backend/graph/nodes.py`, auth in `backend/external.py` |
| `khalidnisar/Altron @ arena/Altron-Quant` | Reviewed — that branch is an unrelated study/flashcard workspace; nothing applicable to the trading engine | — |

Sword components deliberately **not** ported: its full lifecycle registry
(Postgres/alembic stack — our LearningEngine keeps the loop lightweight),
prediction-market adapter (out of FX/MT5 domain), its probabilistic regime
engine (our ADX/EMA/ATR regime + directional-flow engine is already richer),
and its circuit-breaker box (our tiered drawdown ladder is broader).

## Trade copier (up to 10 MT5 accounts)

Every master trade the engine takes is replicated to linked follower accounts
with per-account **sizing modes** (mirror 1:1 · proportional =
`master_lots × follower_equity/master_balance × multiplier` · fixed lot),
**symbol filters**, **reverse copy**, force min/max lot, and a margin
affordability clamp. Replication is event-driven on master order placement and
backstopped by per-tick order-pair reconciliation, so partial closes, stop
modifications and full closes are mirrored even if an event is missed.

* Followers: simulated paper accounts (shadow master feed with per-broker
  spread offset) or MT5 **DEMO** terminals — the same demo-account safety gate
  applies per follower. Live-money followers are not supported anywhere.
* Accounts persist to `data/copier_accounts.json` (git-ignored).
* API: `GET /api/copier` · `POST /api/copier/accounts` · `PATCH/DELETE
  /api/copier/accounts/{id}` · `POST …/connect|disconnect`
* Dashboard: "⇄ TRADE COPIER" section — master strip, 10 account cards with
  connection LED, equity, mirrored positions, W/L and copied P&L, inline
  mode/multiplier editing, enable/connect/remove controls, link form.

```bash
# Fire an external (MT5 EA / TradingView webhook) signal through the full risk stack:
curl -X POST localhost:8100/api/signals/external -H 'Content-Type: application/json' \
  -d '{"symbol":"EURUSD","direction":"STRONG BUY","confidence":82,"confluence":4,"source":"tv"}'
```

## Liquidations & funding

The simulated venue tracks perp-style mechanics: a drifting **funding rate**
(8h accruals, signed to balance, surfaced in the dashboard) and a **margin
stop-out engine** — when margin level breaches 100%, positions are
force-closed largest-first as `LIQUIDATED` deals, which the learning loop
captures and reacts to (threshold tightening + lesson entry). Every open
position shows its estimated liquidation price in real time.


## Module map (blueprint §1)

| Blueprint module | Where | Highlights |
| --- | --- | --- |
| **1A Risk Engine** | `backend/risk/` | fixed-fractional + half-Kelly sizing, ATR stops, multi-level TP, daily/weekly/drawdown hard limits, equity-preservation ladder (5% → ×0.5, 7% → ×0.25, 10% → halt), min-balance & margin guards, currency-correlation exposure cap, R:R ≥ 1:2 validation |
| **1B AI Engine** | `backend/ai/` | EMA/MACD/RSI/Stoch/ATR/Bollinger/ADX/Donchian confluence scoring, logit ensemble with online learning + candlestick patterns, sentiment process with economic-calendar blackouts, spread/flow microstructure, regime detector (trend/range/volatile/illiquid) with adaptive strategy selection, multi-TF structure analysis (`ai/structure.py`: BOS/CHoCH, premium/discount, liquidation pools) |
| **Agent graph** | `backend/graph/` | LangGraph `StateGraph` cycles: market_state → research → risk_gate → execution / learning; self-fixing feedback loop via `LearningEngine` |
| **1C MT5 Layer** | `backend/brokers/` | adapter contract, reconnect/`ensure_connected`, `account_info().trade_mode` demo gate in `MT5DemoBroker`, feature-rich `SimulatedBroker` (regime-switching prices, floating spread, slippage, broker-side SL/TP, margin accounting) |
| **1D Execution** | `backend/execution/` | pre-trade risk gate, partial TPs at 25/50/75/100% of target, breakeven + ATR trailing ratchet, time-based stops, deal ledger, ML feedback loop |
| **§4 Monitoring** | `backend/monitoring/` | CRITICAL/WARNING alert rules with cooldowns; Sharpe/Sortino/PF/win-rate/expectancy/max-DD metrics |
| **Dashboard** | `web/` | zero-dependency SPA: candlestick chart with entry/SL/TP overlays, equity curve, signal radar (T/ML/S/Micro bars + confidence), risk limit bars, positions/deals/signals tables, alert feed, pause/resume/emergency-stop controls |

## Confidence & strategy selection (blueprint §3)

```
Confidence = Technical×0.30 + ML×0.40 + Sentiment×0.20 + Microstructure×0.10
Trade only if Confidence > 70  AND  confluence ≥ 3  AND  R:R ≥ 1:2

Trending  → BREAKOUT strategy (momentum votes, Donchian/EMA/MACD)
Ranging   → MEAN_REVERSION (RSI/Bollinger/Stochastic fades)
Volatile  → DEFENSIVE (halved size), EXTREME → suppressed
Illiquid  → NO_TRADE (RULE 11)
```

## Safety rules (blueprint §8) — all enforced in `risk/engine.py`

1-2% risk per trade · hard SL always · R:R ≥ 1:2 · max 5 positions · daily loss 2% ·
weekly loss 5% · max drawdown 10% (hard halt) · preservation tiers at 5%/7% ·
rolling PF < 1.0 blocks new entries (soft-guard scales at PF < 1.5 / WR < 50%) ·
economic-event blackout · per-currency exposure cap.

## API

| Endpoint | Description |
| --- | --- |
| `GET /api/state` | full engine snapshot (account, positions, risk, analyses, deals, candles, metrics, alerts) |
| `GET /api/config` | public configuration view |
| `POST /api/control` | `{action: pause|resume|emergency_stop|close_all}` |
| `GET /api/trades`, `GET /api/alerts`, `GET /api/health` | ledgers & health |
| `POST /api/signals/external` | external bridge signal → risk_gate → execution |
| `GET /api/copier` | copier state (master pairs, followers, stats) |
| `POST /api/copier/accounts` | link follower account (max 10) |
| `PATCH` / `DELETE /api/copier/accounts/{id}` | update settings / unlink |
| `POST /api/copier/accounts/{id}/connect` · `disconnect` | connection control |
| `WS /ws` | live state push (dashboard uses this) |
| `GET /api/docs` | OpenAPI UI |

## Tests

```bash
python -m pytest trading_app/tests -q     # 34 tests: risk, AI, execution
```

## Simulation clock

The sandboxed engine runs an accelerated market: 1 tick = 1 simulated minute,
15 ticks = one candle, 1440 ticks = a day (daily-loss resets, economic events
at 08:30/13:30/15:00 sim time). Against a real MT5 demo terminal the same loop
consumes live ticks.
