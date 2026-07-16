# Approach Matrix: What “Copy a Website” Can Mean

Use precise language. “Copy” can mean a static archive, a visual reimplementation, a behavioral clean-room rebuild, or an owner-authorized migration. They have different inputs and ceilings.

## Feasibility matrix

| Method | Required inputs | Can reproduce | Cannot recover | Best use |
|---|---|---|---|---|
| Static snapshot | Authorized public URL | Delivered HTML/CSS/JS/images for visited pages at one moment | Server code, databases, dynamic state, private routes, jobs | Archival, content preservation, static brochure sites |
| Browser-observed frontend rebuild | Authorized URL, route scope, approved roles | Layout, responsive states, accessible semantics, browser-visible interactions | Unvisited states, hidden business rules, original source quality | High-fidelity maintainable frontend |
| Contract-assisted clean-room rebuild | Above plus API docs, fixtures, business rules | API-compatible behavior and a new backend implementation | Undocumented internal algorithms unless specified | Replatforming when old source is unavailable |
| Export-assisted CMS/e-commerce migration | Owner exports, media, configuration, integration inventory | Content, catalog, customers/orders where legally permitted, redirects | Missing plugins/custom code or provider-only behavior | Platform migration |
| Source-assisted full migration | Source, database/object-store exports, runtime config inventory, queues/jobs, infrastructure and third-party setup | The actual application and backend, subject to dependency availability | External provider internals and any omitted resources | Backup, disaster recovery, hosting migration |
| Inspiration-only original build | Public examples, no reproduction permission | General interaction/design patterns with distinct implementation and brand | Exact protected expression, brand assets/content | Competitive research and original product design |

## URL-only ceiling

A browser receives responses produced by the server. It does not receive the server's source files, database, internal configuration, secret keys, queue state, private object storage, cron jobs, or deployment topology. Even a comprehensive browser trace shows only requests and responses for the exercised journeys and roles.

Therefore:

- **Frontend:** high visual and behavioral fidelity is possible for observed states, but completeness depends on route/role/state coverage.
- **Backend:** only the observable external contract can be inferred. Build a new backend from that contract; do not describe it as recovered or copied.
- **Data:** only owner-provided exports should be migrated. Browser scraping is not a substitute for a database export and may omit private, historical, or relational data.
- **Secrets:** must be newly issued for the rebuilt system.
- **Third parties:** their behavior can be integrated through supported APIs and sandbox accounts, not copied.

## Recommended decision tree

1. **Does the owner have source and infrastructure access?**
   - Yes: use source-assisted migration. Do not waste time reverse engineering browser output.
   - No: continue.
2. **Are official exports, API schemas, design files, analytics route lists, and business rules available?**
   - Yes: use contract/export-assisted reconstruction.
   - No: continue.
3. **Is black-box observation explicitly authorized for the named origins, roles, and actions?**
   - Yes: use a bounded authorized black-box clean-room rebuild and label all unknowns.
   - No: use inspiration-only mode.
4. **Is the target mostly static?**
   - Yes: an authorized static archive may be enough, followed by a maintainable static-site rebuild.
   - No: plan a new application implementation.

## Completeness checklist for a true owner migration

Request these from the owner through secure channels, never chat:

- Source repositories, submodules, package registries, build artifacts, and version history.
- Database engines/versions, schema dumps, consistent data backups, encryption/key-management procedure, and restore test.
- Object/file storage export, metadata, access policies, and checksums.
- Environment-variable **names** and configuration map; secrets should be reissued in the destination secret manager.
- DNS, certificates, CDN/WAF, load balancers, containers/functions, networks, and infrastructure-as-code.
- Queues/topics, scheduled jobs, workers, search indexes, caches, webhooks, email/SMS/push providers, payment providers, and identity provider.
- Observability dashboards, alerts, logs/retention, analytics/consent, backup policy, RPO/RTO, incident runbooks, and compliance constraints.
- Domain ownership, licensing, fonts/media rights, privacy notices, data-processing agreements, and retention/deletion requirements.
- Cutover plan, read-only/freeze window, reconciliation, rollback, and post-cutover validation.

If any item is missing, record the resulting fidelity or operational risk rather than silently inferring it.
