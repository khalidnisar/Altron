# AppForge AI

Autonomous platform that discovers viral Google Play apps, mines their weaknesses from
user reviews, and builds improved clones through eight coordinated AI agents — with
human approval gates before anything ships.

Built to the AppForge blueprint. Runs on **Windows via Docker Desktop**.

---

## Quick start (Windows)

**Prerequisite:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) with the
WSL2 backend, set to **Linux containers** (the default).

```powershell
# Double-click start.bat, or from PowerShell:
.\start.ps1 -Seed
```

That verifies Docker, creates `.env`, builds four containers, waits for health, seeds a
full demo pipeline, and opens the dashboard.

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API docs | http://localhost:8000/docs |

```powershell
.\stop.ps1                 # stop, keep data
.\stop.ps1 -RemoveData     # stop and wipe volumes
```

**No API keys are required.** With no credentials configured the platform runs in
*offline mode*: deterministic stub providers replace Play Store scraping, LLM calls,
image generation, device farms, and Play Console submission. The entire pipeline —
discovery through monetization — works end to end. Add keys in `.env` to switch any
individual provider to live.

---

## What it does

```
DISCOVER → ANALYZE → [approve] → DESIGN → BUILD → TEST → [approve] → PUBLISH → MONETIZE → GROW
```

| Agent | Responsibility |
|---|---|
| **Discovery** | Scans 20 niches, scores each app 0–100 for clone potential; >70 auto-queues analysis |
| **Analysis** | Mines reviews for sentiment, clusters issues, competitive matrix, feasibility; returns RECOMMEND / NEEDS_REVIEW / SKIP |
| **Design** | Brand name, palette, logo set, screenshots, design system, WCAG 2.1 AA check |
| **Development** | Generates a real Flutter project with a dedicated code module fixing every identified issue |
| **Testing** | Static analysis, unit/widget/integration/E2E, 10-device matrix, performance gates |
| **Publishing** | Pre-publish checklist, ASO listing, staged rollout (internal → 10% → 100%) |
| **Monetization** | Value-scored pricing model, tiers, regional pricing, ad mediation |
| **Growth** | Daily health checks, anomaly response, rollout advancement, portfolio review |

### The clone score (blueprint §2.4)

| Component | Max |
|---|---|
| Revenue potential | 25 |
| Growth velocity | 20 |
| Improvement opportunity | 25 |
| Market competition | 15 |
| Technical feasibility | 15 |

### Generated code is real

The Development Agent writes a working Flutter tree — models, repositories, Riverpod
providers, screens, tests, CI, and a minimal-permission Android manifest. Each mined
issue produces a purpose-built module:

| Issue type | Generated module |
|---|---|
| Performance | `core/perf/battery_manager.dart` — adaptive quality tiers |
| Privacy | `core/privacy/permission_policy.dart` — denies contacts/location/SMS |
| Intrusive ads | `core/ads/ad_frequency_policy.dart` — ad-free early sessions, capped |
| Data loss | `core/data/safe_migrator.dart` — versioned migrations with backup |
| Accessibility | `core/a11y/accessibility.dart` — 48dp targets, contrast helpers |
| No offline mode | `core/data/offline_cache.dart` — local-first with sync |
| Overpricing | `core/billing/pricing_tiers.dart` — regional multipliers |

---

## Human approval gates

Two gates require a person, and the pipeline **will not** cross them on its own:

1. **After analysis** — approve the clone thesis before design and build begin.
2. **After testing** — try the build in the simulator before Play Store submission.

Approvals are recorded **per stage** in `clone_projects.approvals`. This matters: an
earlier design of this system used a single `approved_at` timestamp for both gates,
which meant approving the analysis silently authorised a Play Store submission. A
gate-1 approval can no longer satisfy gate 2.

The Publishing Agent independently re-checks the pre-publish gate and refuses to submit
without it. Both behaviours are covered by tests that fail if the gate is removed.

### Remediation loop

When tests fail, a crash spike is detected, or a reviewer rejects a build, an
`apply_fixes` task is queued. The Development Agent records the reason, converts it into
a tracked fix item, regenerates, and re-runs testing. After
`MAX_REMEDIATION_ATTEMPTS` (3) the project is parked as `needs_human_intervention`
rather than looping forever. The history is visible on the project page.

---

## Architecture

```
appforge/
├── services/api/          FastAPI + 8 agents + Postgres-backed task queue
│   └── appforge/
│       ├── agents/        one module per agent
│       ├── routers/       REST endpoints
│       ├── services/      providers, scoring, review mining, codegen
│       ├── orchestrator.py  claims and dispatches tasks
│       └── worker.py      long-running queue drainer
├── apps/dashboard/        Next.js 14 App Router + Tailwind + Recharts
├── services/build-agent/  optional Windows-container build agent
├── docker-compose.yml         Linux stack (default)
├── docker-compose.windows.yml Windows-container overlay
└── start.ps1 / start.bat      Windows launchers
```

Containers: `db` (Postgres 16), `api`, `worker`, `dashboard`.

The task queue lives in Postgres and claims work with `FOR UPDATE SKIP LOCKED`, so
multiple workers can run safely without adding Redis or Celery.

---

## Dashboard

| Page | Contents |
|---|---|
| Dashboard | Revenue, pipeline counts, top apps |
| Discover | Filter/sort discovered apps; detail shows score breakdown, loved features, mined issues with fixes, competitors, feasibility |
| Pipeline | Kanban by stage, gates marked; detail shows patches, tests, brand, listing, build log |
| Simulator | Device frame with the build, test metrics, fixes to verify, approve/reject |
| Revenue | Daily trend, stream split, per-app table, CSV export |
| Settings | Health, agent status, provider configuration, legal guardrails |

---

## Windows containers (optional)

Only needed if you must run Windows-native build tooling. Docker Desktop runs Linux
**or** Windows containers, not both at once.

```powershell
& "$Env:ProgramFiles\Docker\Docker\DockerCli.exe" -SwitchDaemon
docker compose -f docker-compose.windows.yml up -d --build
```

The agent polls the API over `host.docker.internal` and writes artifacts to a shared
volume. The base image tag must match your host kernel (`ltsc2022` for Windows 11 /
Server 2022).

---

## Development

```bash
# API
cd services/api
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
export APPFORGE_DATABASE_URL="sqlite:///./dev.db"
uvicorn appforge.main:app --reload
pytest          # 72 tests
ruff check appforge tests

# Dashboard
cd apps/dashboard
npm install && npm run dev
```

### Verification performed

- 110 backend tests pass; `ruff` clean
- Mutation-checked: removing the approval gate or the 10-review corroboration rule makes the relevant tests fail
- All 170 generated Dart files verified for balanced delimiters and no template leakage
- Schema compiles against the PostgreSQL dialect; queue uses `FOR UPDATE SKIP LOCKED`
- TypeScript clean; production build succeeds for all 9 routes
- Live API + dashboard run together: all 12 endpoints return 200, all 6 pages render real data, approve → design → build → test executes, and the publish gate holds
- A post-build audit found and fixed 12 defects (see `docs/AUDIT.md`), each pinned by a regression test that fails against the old behaviour

---

## Legal position

- **No code is copied.** Apps are generated from feature specifications.
- **Original branding.** Every clone gets its own name, logo, and palette.
- **Minimal permissions.** Generated manifests request only `INTERNET`; contacts,
  location, and SMS are explicitly denied.
- **Big tech excluded** from discovery.
- **Human approval required** before any submission.

This is a research and automation platform. You are responsible for trademark
clearance, Play Store policy compliance, and applicable law in your jurisdiction
before publishing anything.
