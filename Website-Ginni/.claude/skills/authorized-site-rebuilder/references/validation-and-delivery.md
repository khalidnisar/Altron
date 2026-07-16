# Validation, Parity, and Delivery

Parity is multi-dimensional. A screenshot match alone does not prove functional, accessible, secure, or backend equivalence.

## Parity dimensions

Score each critical route/state/journey against agreed acceptance criteria:

1. **Content** — authorized copy/media, labels, formatting, metadata.
2. **Visual** — layout, typography, color, spacing, imagery, responsive behavior, motion.
3. **Semantic/accessibility** — landmarks, names, roles, states, focus, keyboard, announcements, contrast/reflow.
4. **Interaction** — controls, validation, overlays, history, deep links, refresh, failure recovery.
5. **Contract** — methods/operations, schemas, statuses, errors, pagination, streaming, side effects.
6. **Authorization** — roles, ownership, tenancy, session expiry, forbidden states.
7. **Data/business rules** — invariants, state transitions, idempotency, concurrency, calculations approved by the owner.
8. **Operational** — performance, resilience, observability, backups, restore, deployment, rollback.
9. **Rights/privacy/security** — asset licenses, consent, retention, secret handling, baseline hardening.

Use status values `not-started`, `in-progress`, `pass`, `partial`, `blocked`, and `out-of-scope`.

## Deterministic comparison setup

- Use synthetic fixture IDs, timestamps, names, images, and API responses.
- Match browser engine/version, viewport, device scale factor, locale, timezone, color scheme, reduced-motion, and font availability.
- Wait on semantic readiness signals, not arbitrary sleeps.
- Disable animations only when the acceptance case is static; validate motion separately.
- Mask only documented nondeterministic regions. Do not mask layout/content merely to make a test pass.
- Store approved baselines separately from actual/diff outputs and require review for baseline updates.

Visual thresholds should be project-specific. Prefer a strict default with small anti-aliasing tolerance and explicit component exceptions; a single generous global threshold hides regressions.

## Test matrix

### Frontend

- Build/type/lint/format checks.
- Unit/component/route integration tests.
- Critical E2E journeys by role.
- Visual snapshots at agreed viewport/state combinations.
- Keyboard and focus behavior.
- Automated accessibility scans plus manual critical-flow checks.
- Cross-browser and responsive/reflow/zoom checks.
- Offline/slow/failure/session-expiry behavior.
- Bundle/image/font budgets and runtime performance.

### Backend

- Unit/domain and contract tests.
- Real dependency integration tests.
- Authentication, role, resource ownership, and tenant isolation matrix.
- Validation/error/pagination/filter/sort/idempotency behavior.
- Job retry/dedup/dead-letter and webhook replay/signature checks.
- Migration, seed, backup, restore, and rollback tests.
- Approved load/resilience tests against the replacement environment only.
- Secret/dependency/static analysis and abuse-case tests.

### Deployment

- Reproducible build from clean checkout.
- Environment schema with no real values committed.
- Health/readiness checks and graceful shutdown.
- Database migration ordering and failure behavior.
- TLS/domain/CDN/caching/security headers.
- Logs/metrics/traces/alerts and sensitive-data redaction.
- Backup schedule plus demonstrated restore.
- Staged rollout, smoke tests, reconciliation, and rollback.

## Defect triage

Fix in this order:

1. Authorization, data integrity, privacy, secret exposure, destructive behavior.
2. Broken critical journeys or API contract.
3. Accessibility blockers and unusable responsive layouts.
4. Systemic design-token/layout/component errors.
5. Performance/reliability budget failures.
6. Local pixel/content differences.

When a visual diff appears, diagnose top-down: environment/font → viewport/container → token → shared component → route override → dynamic data. Avoid one-off CSS until shared causes are ruled out.

## Definition of done

A milestone is done only when:

- Its in-scope inventory rows have acceptance criteria and final status.
- Critical journeys pass with the appropriate role and synthetic data.
- No open critical/high security, authorization, privacy, or data-integrity issue remains.
- Accessibility target and performance budgets have measured results.
- Backend schema/API/jobs/integrations are documented and tested.
- Secrets and raw sensitive evidence are absent from version control.
- Build, setup, tests, migration, backup/restore, deploy, monitoring, and rollback are reproducible.
- Asset rights/attribution are resolved.
- Remaining differences and unobserved behavior are disclosed.

Never state “complete copy” when only observed pages or a subset of roles has been validated. Prefer: “All scoped routes, states, and journeys in parity matrix version X pass; listed items remain out of scope or unobserved.”

## Handoff structure

### 1. Executive status

- Target and mode.
- Scope completed.
- Validation summary.
- Known residual risk.

### 2. Reproducible commands

- Prerequisites.
- Install/setup.
- Local services.
- Migrations/seeds.
- Run frontend/backend/workers.
- Unit/integration/E2E/visual/a11y checks.
- Production build.

### 3. Architecture and operations

- Components and data flow.
- Environments/configuration names.
- Database/files/cache/queue/jobs/integrations.
- Deployment and scaling.
- Monitoring/alerts.
- Backup/restore and rollback.

### 4. Evidence

- Route/state/journey/endpoint/asset inventories.
- Parity matrix and test report.
- Architecture decisions and unknowns register.
- Rights/attribution ledger.

### 5. Limitations

Separate:

- Out of scope by agreement.
- Blocked by missing access/input.
- Inferred rather than owner-specified.
- Not observed for particular roles/locales/devices.
- Deliberately improved rather than matched, such as security/accessibility fixes.

## Final report template

```text
Delivered:
- ...

Validated:
- ...

Parity:
- Passed: N
- Partial: N
- Blocked: N
- Out of scope: N

Security/privacy/rights:
- ...

Known deltas and assumptions:
- ...

Operate:
- setup: ...
- test: ...
- deploy: ...
- rollback: ...

Next recommended action:
- ...
```
