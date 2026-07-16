# Frontend Rebuild Playbook

Build a maintainable frontend that matches approved observable behavior. Do not paste captured production bundles into a new repository.

## Architecture selection

Prefer the destination repository's established stack. If greenfield, choose based on requirements rather than guessing the target's framework:

- Static content: static-site generation with a content source.
- Search/SEO-heavy dynamic content: server rendering or hybrid rendering.
- Authenticated application: client/server framework with typed data boundaries.
- Highly interactive widgets embedded elsewhere: isolated component bundle or web components when appropriate.

Document routing/rendering strategy, state ownership, data fetching/cache, form handling, validation, styling/tokens, accessibility, localization, analytics/consent, error reporting, and testing.

## Implementation order

1. **Foundation** — build/run/lint/test, TypeScript or equivalent strictness, formatting, environment schema, error boundaries.
2. **Tokens** — semantic color roles, typography, spacing, radius, elevation, breakpoints, z-index, motion.
3. **App shell** — document metadata, routes, header/nav/footer/sidebar, responsive containers, skip links.
4. **Primitives** — controls with consistent states and accessibility.
5. **Composites/templates** — shared patterns before route duplication.
6. **Critical routes and journeys** — vertical slices backed by mocks.
7. **Secondary routes/states** — prioritized by inventory.
8. **Real API integration** — switch adapters from deterministic mocks to the replacement backend.
9. **Hardening** — error/offline/empty states, cross-browser, performance, security, analytics, localization.
10. **Parity convergence** — visual and behavioral diff loop.

## Design token extraction

Translate measured values into semantic roles. Avoid a list of one-off pixel values.

Example:

```css
:root {
  --color-bg-canvas: #ffffff;
  --color-bg-surface: #f7f8fa;
  --color-text-primary: #17191c;
  --color-text-muted: #626a73;
  --color-action-primary: #2457e6;
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --radius-control: 0.5rem;
  --shadow-overlay: 0 1rem 3rem rgb(0 0 0 / 0.16);
  --motion-fast: 120ms;
  --motion-normal: 200ms;
}
```

Use observed values as evidence, then consolidate near-duplicates. Preserve contrast and forced-colors behavior. If exact fonts are not licensed, choose a metrically suitable licensed alternative and document the expected visual delta.

## Responsive reconstruction

- Implement mobile-first constraints and intrinsic layouts.
- Identify behavioral breakpoints where navigation, columns, density, ordering, or content changes—not only where a screenshot happens to differ.
- Use container queries when a component responds to its parent; media queries for viewport-level behavior.
- Test narrow widths, long labels, 200% zoom, large text, landscape, touch targets, notches/safe areas, and virtual keyboard overlap where applicable.
- Preserve readable line lengths and avoid fixed heights for content containers unless behavior requires them.
- Optimize images with dimensions, aspect ratio, responsive sources, lazy loading, and appropriate formats.

## State completeness

Every data-backed component should intentionally handle:

```text
idle → loading → success
               ↘ empty
               ↘ partial
               ↘ recoverable error → retry
               ↘ terminal error
```

Forms should cover pristine, dirty, validating, field error, form error, submitting, success, duplicate submit, and session expiry. Interactive controls need default, hover where applicable, focus-visible, active, selected, disabled, and busy states.

Do not invent backend behavior to fill gaps. Add a documented assumption or ask the owner.

## Accessibility baseline

Target WCAG 2.2 AA unless the brief specifies more:

- Semantic HTML and logical heading/landmark structure.
- Unique accessible names; labels and descriptions tied to controls.
- Complete keyboard operation with visible focus.
- Predictable focus placement/restoration for routes, dialogs, drawers, menus, and errors.
- Escape/arrow/tab behavior appropriate to the component pattern.
- Status/error updates exposed through suitable live regions without excessive announcements.
- Contrast, non-color cues, reflow, zoom, text spacing, target size, reduced motion, and high-contrast/forced-colors support.
- No unnecessary ARIA where native controls suffice.

Automated checks catch only part of accessibility. Add manual keyboard and screen-reader smoke tests for critical journeys.

## Motion

Record trigger, property, duration, easing, delay, interruption behavior, and reduced-motion fallback. Animate transform/opacity where possible. Do not block input on decorative motion. Avoid recreating distracting or inaccessible motion merely for pixel parity.

## Content, SEO, and localization

- Separate content from view components where practical.
- Use original/owner-authorized copy and media.
- Preserve canonical URLs, titles, descriptions, social metadata, structured data, robots directives, sitemap behavior, and redirects when in scope.
- Do not concatenate translated fragments. Support locale-aware numbers, currency, dates, pluralization, directionality, and longer strings.
- Define consent before loading nonessential analytics/advertising scripts.

## Data boundary

Create typed clients/adapters against the replacement contract:

- Runtime validation at untrusted boundaries where appropriate.
- Central auth/session, timeout, retry, cancellation, and error mapping.
- Do not leak server secrets into browser bundles.
- Keep target-site endpoints out of the final application; all production traffic should point to the new backend or approved third parties.
- Use local mocks and synthetic fixtures for deterministic development and visual tests.

## Frontend tests

- Unit tests for pure state/format/validation logic.
- Component tests for variants, accessibility, and interactions.
- Route integration tests for data and error boundaries.
- End-to-end tests for each critical `J-###` journey.
- Visual snapshots for stable `R-###`/`S-###` combinations.
- Keyboard/focus tests and automated accessibility scans.
- Cross-browser checks for agreed browsers.
- Performance budgets for JavaScript/CSS/image weight, core user metrics, and critical interactions.

Use resilient locators based on role, label, and stable test IDs. Avoid selectors copied from the target's generated class names.

## Anti-patterns

- A full-page screenshot used as the interface.
- Absolute-positioning every element to match one viewport.
- One component per page with no reusable primitives.
- Hardcoded target HTML or minified CSS/JS pasted into the project.
- Production target APIs called by the clone.
- Missing loading/error/empty/auth states.
- Visual diff masks large enough to hide real regressions.
- Reusing unlicensed fonts/assets or target analytics IDs.
- Claiming accessibility based only on an automated score.
