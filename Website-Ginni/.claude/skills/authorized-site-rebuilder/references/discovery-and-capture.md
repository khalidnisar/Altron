# Discovery and Evidence Capture

Goal: create the smallest authorized evidence set that describes reachable routes, states, journeys, design primitives, and external contracts. Do not turn discovery into unrestricted crawling.

## 1. Establish the observation envelope

Write down:

- Canonical origin and explicitly allowed subdomains.
- Included/excluded path patterns and query handling.
- Public pages versus approved authenticated roles.
- Locale, timezone, geolocation, feature flags, and theme.
- Desktop/mobile browsers and viewport matrix.
- Request delay, concurrency, depth, page cap, and time window.
- Whether screenshots, DOM snapshots, accessibility trees, network metadata, HAR, video, or traces are permitted.
- Actions that must be mocked or stopped before submission.

Prefer staging/test environments and synthetic accounts. If production is the only target, keep observation read-only unless the exact write action is approved.

## 2. Discover routes in low-risk order

1. Owner-provided route inventory, analytics export, CMS export, router config, or source manifest.
2. `sitemap.xml`, sitemap index, navigation/footer links, canonical/hreflang links, and documented redirects.
3. A manual representative journey through the approved UI.
4. A bounded same-origin link crawl only if gaps remain and it is approved.

Do not guess admin routes, enumerate IDs, brute force slugs, fuzz parameters, follow logout/delete links, or crawl faceted/search combinations without explicit bounds.

Normalize inventory entries by:

- Replacing record identifiers with route parameters, such as `/products/:id`.
- Recording meaningful query variants separately, such as sort/filter/page.
- Tracking redirect source and destination.
- Recording auth role, locale, theme, viewport class, and feature-flag prerequisites.
- Assigning `R-###` IDs and confidence: `owner`, `observed`, or `inferred`.

## 3. Model states, not only pages

For each route, inventory relevant states:

- Initial/loading/skeleton.
- Success with short, long, empty, and overflow content.
- Empty/filter-no-result.
- Validation and field-level errors.
- API/server/network timeout/offline.
- Permission denied, unauthenticated, expired session.
- Disabled, hover, focus-visible, active/pressed, selected, expanded.
- Modal, drawer, tooltip, dropdown, toast, banner, cookie/consent UI.
- Pagination/infinite loading/end state.
- Upload progress/failure, if safely testable in a sandbox.
- Not found and global failure boundary.
- Mobile keyboard, zoom, orientation, and reduced-motion behavior where relevant.

Assign `S-###` IDs. Link each state to its route, trigger, evidence, and expected exit behavior.

## 4. Capture visual and semantic evidence

For each high-priority route/state:

- Record exact URL pattern, date/time, viewport width/height, device scale factor, browser/version, color scheme, locale, timezone, reduced-motion preference, login role, and data fixture label.
- Capture full-page and component screenshots only when needed.
- Record semantic structure: landmarks, heading outline, labels, roles, names, descriptions, live regions, focus order, and keyboard controls.
- Record computed design values for representative elements rather than every DOM node: font family/size/weight/line-height, colors, spacing, borders, radii, shadows, widths, breakpoints, and motion duration/easing.
- Note sticky/fixed behavior, overflow, scroll snapping, lazy loading, image aspect ratios, and responsive content changes.
- Record layout at stable widths around observed breakpoints, not dozens of arbitrary devices.

Avoid copying framework-generated class names into the new architecture. Infer reusable tokens and components.

## 5. Capture safe interactions

Build a journey inventory with `J-###` IDs:

- Preconditions and role.
- Start route.
- User actions using accessible names.
- Expected intermediate states.
- Expected URL/history/storage changes.
- Network contract IDs.
- Final state.
- Side-effect classification: `none`, `sandbox-write`, or `production-write`.
- Cleanup procedure.

Safe default journeys are navigation, open/close UI, filtering synthetic/local data, validation before submission, and read-only detail views. Stub the final request for destructive or external side effects.

Record focus movement, escape behavior, browser back/forward, refresh/deep link, double submission, slow network, and failure recovery.

## 6. Derive an endpoint contract

Capture only what the browser legitimately uses in approved journeys. For each `API-###` entry record:

- Protocol: HTTP, GraphQL, WebSocket, SSE, or third-party SDK.
- Method and parameterized path/operation name/event type.
- Purpose and linked journey/state IDs.
- Required role/scopes, without token values.
- Request content type and minimal schema.
- Response schema and representative synthetic example.
- Status/error codes and error envelope.
- Pagination/filter/sort/search semantics.
- Caching headers, ETag behavior, polling or streaming cadence.
- Idempotency and side effects.
- Rate-limit behavior only if documented or naturally observed; do not provoke limits.
- Evidence reference, confidence, and unknowns.

Do not retain authorization headers, cookies, signed URLs, personal bodies, telemetry identifiers, or unrelated third-party traffic. When a response schema is unclear, use optional/unknown fields rather than manufacturing a rule.

## 7. Create a design and asset inventory

Group observations into:

- Foundations: color roles, typography scale, spacing scale, radii, elevation, opacity, borders, icon sizing, z-index layers, motion.
- Primitives: button, input, select, checkbox, radio, switch, chip, link, avatar, icon, image.
- Composites: form field, search, nav item, card, table, list item, pagination, tabs, dialog, toast.
- Sections: header, footer, side nav, hero, pricing, dashboard panels.
- Templates: marketing, auth, list/detail, settings, checkout-like flows.

For every media/font/icon asset, record source, purpose, dimensions/formats, rights status, desired replacement, and optimization needs. Never assume browser availability implies republication rights.

## 8. Evidence storage

Recommended layout:

```text
.site-rebuild/
├── authorization.md
├── project-brief.md
├── inventories/
│   ├── routes.csv
│   ├── states.csv
│   ├── journeys.csv
│   ├── endpoints.csv
│   └── assets.csv
├── design/
│   └── tokens.md
├── contracts/
│   └── openapi.yaml
├── evidence/
│   ├── public/       # safe, minimal references
│   ├── sanitized/    # reviewed artifacts
│   └── raw/          # ignored; ideally outside repo
├── parity-matrix.csv
├── test-plan.md
└── handoff.md
```

Use filenames such as `R-003--S-014--desktop-1440x900.png`. Maintain a small evidence index rather than relying on filenames alone.

## 9. Capture completion check

Discovery is sufficient to blueprint when:

- Every critical journey has routes, states, endpoint contracts, and acceptance criteria.
- Representative responsive breakpoints and component variants are covered.
- All captures identify role, environment, and fixture.
- Secrets/personal data are absent from the checked-in evidence.
- Unknowns and unreachable states are explicit.
- Further crawling would add volume rather than resolve a priority unknown.

Discovery is never proof that all hidden behavior has been found.
