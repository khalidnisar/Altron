# Architecture

## Flow

```
                    ┌──────────── Next.js dashboard (:3000) ────────────┐
                    │  Dashboard · Discover · Pipeline · Simulator      │
                    │  Revenue · Settings                               │
                    └───────────────────────┬───────────────────────────┘
                                            │ REST
                    ┌───────────────────────▼───────────────────────────┐
                    │            FastAPI (:8000)                        │
                    │  /apps /projects /pipeline /revenue /artifacts    │
                    └───────────────────────┬───────────────────────────┘
                                            │
              ┌─────────────────────────────▼─────────────────────────────┐
              │      PostgreSQL: data + agent_tasks queue                 │
              │      claimed with FOR UPDATE SKIP LOCKED                  │
              └─────────────────────────────┬─────────────────────────────┘
                                            │
                    ┌───────────────────────▼───────────────────────────┐
                    │  Worker: orchestrator dispatches to 8 agents      │
                    └───────────────────────────────────────────────────┘
```

## Why the queue lives in Postgres

The blueprint suggests Redis + Celery. Postgres was chosen instead because:

- One fewer container and no broker to operate on a developer's Windows laptop.
- `FOR UPDATE SKIP LOCKED` gives safe concurrent claiming across many workers.
- Task history, inputs, outputs, and errors are queryable with ordinary SQL, which is
  what the Settings page and `/api/agents/status` use.

The `BaseAgent` contract does not depend on the transport, so swapping in Celery later
requires no agent changes.

## Provider abstraction

Every external dependency sits behind an adapter in `services/providers.py` with two
implementations:

- **Live** — used when credentials are present.
- **Offline** — deterministic, seeded from a hash of its inputs.

This keeps the test suite hermetic and lets the whole product be evaluated with no paid
accounts. `/api/health` reports which mode is active.

## Pipeline stages

`discovery → analysis → awaiting_approval → design → development → testing →
simulation → publishing → monetization → growth → live`

Two stages are human gates: `awaiting_approval` and `simulation`. Agents queue the next
task on success, but never across a gate — only an operator action does that.

## Data model

| Table | Purpose |
|---|---|
| `niches` | 20 monitored categories with saturation |
| `viral_apps` | Discovered apps, metrics, mined issues, clone score |
| `app_analyses` | Full analysis report and recommendation |
| `clone_projects` | Pipeline state, assets, patches, tests, listing, revenue |
| `pipeline_events` | Append-only audit log |
| `earnings` | Daily revenue by stream |
| `user_feedback` | Post-launch review signal |
| `agent_tasks` | Work queue |
| `live_monitors` | Health snapshots for live apps |

## Code generation

`services/codegen.py` emits a Flutter project: `pubspec.yaml`, theme derived from the
design system, localization, routing, and per-feature models/repositories/providers/
screens plus tests. Each mined issue selects a patch generator that writes a dedicated
module and names its regression tests.

Patch bodies are plain (non-format) strings so Dart braces and `$` interpolation survive
verbatim; provenance comments are substituted afterwards via markers. Tests assert that
no template artifacts leak and that every generated file has balanced delimiters.
