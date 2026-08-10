# Backend Migration and Clean-Room Rebuild

A hidden backend cannot be downloaded from a URL. Choose either an owner-source migration or a new implementation derived from authorized requirements and external contracts.

## Track A: source-assisted migration

### Inventory before change

- Repository/commit, runtime and package versions, build artifacts and registries.
- Services, processes, ports, domains, health checks, and dependencies.
- Databases, replicas, extensions, migrations, collations, timezones, and connection topology.
- Object storage, file volumes, search, cache, queues/topics, workers, cron/scheduled jobs.
- Identity provider, email/SMS/push, payment, maps, analytics, webhooks, feature flags.
- DNS, TLS, CDN/WAF, load balancing, networking, firewall, containers/functions, autoscaling.
- Environment-variable names, secret ownership/rotation, certificates, and KMS usage.
- Logs, metrics, traces, alerts, backup retention, RPO/RTO, compliance, and incident procedures.

Do not copy secret values into documentation. Create a secret-name matrix and reissue values in the destination.

### Migration sequence

1. Reproduce the source build and tests in an isolated environment.
2. Take consistent, checksummed backups and prove restore into a disposable environment.
3. Provision destination infrastructure through repeatable configuration/IaC.
4. Apply schema migrations and restore a sanitized staging dataset.
5. Transfer object storage with checksums and metadata.
6. Configure workers, queues, schedules, integrations, domains, TLS, observability, and backups.
7. Run contract, integration, permission, performance, and recovery tests.
8. Rehearse cutover and rollback, including data freeze/read-only window and reconciliation.
9. Rotate all secrets, cut over gradually where possible, monitor, reconcile, and retain rollback until acceptance.

Never call a file copy a complete migration without database, jobs, integrations, recovery, and cutover validation.

## Track B: contract-assisted or black-box clean-room rebuild

### 1. Specify the contract

Convert owner documentation and sanitized observations into a versioned API/event schema. For each operation define:

- Purpose and linked journey IDs.
- Method/path or operation/event name.
- Authentication and authorization policy by role and resource ownership.
- Path/query/header/body schema and validation.
- Response schema, status codes, errors, pagination, sorting, filtering, search.
- Idempotency, side effects, consistency, concurrency, caching, and rate limits.
- File limits/types, webhook signatures, streaming/reconnect behavior, and versioning where applicable.
- Source and confidence: `owner-specified`, `observed`, or `assumed`.

Never infer “the same internal algorithm.” Specify only externally required outcomes. Ask the owner to resolve policy-sensitive unknowns such as pricing, permissions, ranking, fraud, or retention.

### 2. Mock first

Create deterministic synthetic fixtures and a contract-validating mock server:

- Happy, empty, partial, validation, unauthorized, forbidden, conflict, rate-limit, timeout, and server-error examples.
- Stable IDs/timestamps for visual tests.
- No copied personal/customer data.
- No network dependency on the target.

Use mocks to validate the frontend and contract before choosing persistence details.

### 3. Model the domain

Define aggregates/entities, value objects, relationships, invariants, state transitions, ownership/tenancy, audit needs, and retention/deletion rules. Then design:

- Database tables/collections with primary/foreign/unique/check constraints.
- Migration ordering and rollback/forward-fix policy.
- Indexes based on required access patterns.
- Transactions, optimistic/pessimistic concurrency, and idempotency records.
- File/object metadata, lifecycle, antivirus/content scanning where needed.
- Search indexing and source-of-truth/rebuild strategy.
- Cache keys, invalidation, TTL, stampede control, and safe degradation.

Do not model directly from one sample JSON response; distinguish API representations from durable domain entities.

### 4. Authentication and authorization

Use a new, supported identity system. Define:

- Registration/invite/account-recovery policy from owner requirements.
- Session/token lifetime, refresh/revocation, CSRF protection, cookie flags, device/session management, and MFA if required.
- Role/permission/resource-ownership checks enforced server-side on every operation.
- Tenant isolation and administrative audit trails.
- Reauthentication for sensitive operations.
- Safe errors that do not leak account existence or internal details.

Test horizontal and vertical authorization boundaries with synthetic users. Never replay sessions from the observed site or reproduce weak observed security behavior.

### 5. Service structure

Keep framework details subordinate to clear boundaries:

- Transport/controllers: parse, authenticate, validate, map responses.
- Application services/use cases: orchestration and authorization intent.
- Domain: invariants and state transitions.
- Repositories/adapters: database, queue, files, external providers.
- Workers: retryable asynchronous work with deduplication and dead-letter handling.
- Observability: correlation IDs, structured logs without secrets/PII, metrics, traces, and audit events.

Use generated clients/types from the contract when useful, but review generated code and keep business rules explicit.

### 6. External integrations

For email, SMS, payment, maps, storage, identity, analytics, or other providers:

- Use owner-approved provider accounts and sandbox mode.
- Store credentials in the destination secret manager.
- Set explicit timeouts and bounded retries with jitter.
- Make writes idempotent and reconcile uncertain outcomes.
- Verify webhook signatures, timestamps, replay resistance, ordering, and deduplication.
- Handle provider rate limits/outages and expose safe degraded behavior.
- Keep provider-specific objects behind adapters.
- Do not copy target account IDs, analytics IDs, webhook secrets, or payment tokens.

### 7. Security baseline

Apply current framework guidance and threat-model the system. At minimum:

- Strict input validation and output encoding.
- Parameterized database access.
- Server-side authorization and tenant isolation.
- Secure headers, CORS allowlist, CSRF protection where relevant, and TLS.
- Upload size/type/content controls and private-by-default storage.
- SSRF protections for server-side URL fetches.
- Rate limiting and abuse controls for auth and expensive operations.
- Secret scanning, dependency scanning, patching, and minimal privileges.
- Sensitive-field redaction in logs/errors/traces.
- Encrypted backups and tested restore.

Do not intentionally reproduce an observed vulnerability for parity.

### 8. Backend test pyramid

- Unit tests for domain rules and state transitions.
- Contract tests generated from API/event schemas.
- Integration tests against real database/cache/queue containers or controlled services.
- Authorization matrix and tenant-isolation tests.
- Migration tests from empty and representative previous schema versions.
- Idempotency/concurrency/retry/webhook tests.
- Backup/restore and disaster-recovery rehearsal.
- Performance/load tests sized to owner requirements, never against the observed target without separate authorization.
- End-to-end critical journeys with synthetic data.
- Security tests for abuse cases and common web risks.

## Unknowns register

Use this structure for each gap:

```text
U-###
Question:
Why it matters:
Source/evidence:
Current assumption:
Confidence: high | medium | low
Owner decision needed by:
Fallback behavior:
Affected routes/APIs/tests:
```

A safe explicit assumption is better than pretending browser observation revealed a hidden rule.
