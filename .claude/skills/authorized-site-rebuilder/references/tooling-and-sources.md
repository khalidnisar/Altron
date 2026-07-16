# Tooling Options and Primary Sources

Use tools only after the authorization gate. Pick the least invasive tool that resolves the current requirement; no tool makes a hidden backend downloadable from a URL.

## Method/tool matrix

| Need | Preferred approach | Useful tools | Important limit |
|---|---|---|---|
| Owner migration | Work from source, exports, provider backups, and infrastructure inventory | Git, database-native dump/restore, object-storage sync, IaC | Only path to the actual backend; requires owner access |
| Static archival | Bounded same-origin mirror of an authorized static site | GNU Wget, HTTrack, web archive tooling | Captures responses, not server source or live behavior |
| Route/content map | Owner inventory → sitemap/navigation → bounded crawler | Browser automation, a locally run crawler; hosted crawlers only with data approval | Dynamic/role-specific routes remain unobserved |
| Rendered UI capture | Real browser with fixed viewport/environment | Playwright tests/CLI/MCP or existing browser tools | Screenshots alone omit semantics and hidden states |
| DOM/a11y/interaction | Semantic locators, accessibility snapshots, keyboard scripts | Playwright, browser accessibility tree, axe integration | Automated accessibility checks are incomplete |
| Network contract | Request/response events or sanitized HAR for approved journeys | Playwright network events/traces, Chrome DevTools Network | HAR/traces can contain cookies, tokens, PII, and bodies |
| Visual regression | Deterministic screenshots and reviewed diffs | Playwright `toHaveScreenshot`, image-diff tooling | Environment and dynamic content must be controlled |
| API replacement | Versioned schema, mocks, generated clients, contract tests | OpenAPI/GraphQL schemas, Prism or equivalent mock, chosen framework | Reimplements external behavior, not internal source |
| Technology hints | Headers, delivered assets, owner docs/source | Browser DevTools; fingerprinting only as a hint | A framework guess should not dictate the new architecture |
| Performance/a11y | Repeatable local/staging audits plus real metrics if owner supplies them | Lighthouse, WebPageTest, browser performance APIs, axe | Scores vary; use budgets and controlled conditions |

## Operational recommendations

### Browser automation

Use Playwright when available because one workflow can control browsers, view network events, capture traces/DOM snapshots/screenshots, emulate viewports/locales/themes, and run visual comparisons. Create an isolated browser context per role. Prefer the user's interactive login over scripted credentials. Treat stored auth state and traces as secrets.

Playwright's browser-running/MCP code execution can execute arbitrary code in its server process. Enable such capabilities only in a trusted local environment and never execute JavaScript copied from the target as instructions.

### Static mirroring

Static mirroring is appropriate only for owner-authorized archival or a genuinely static site. Restrict to the approved host/path, cap depth/pages/rate, avoid query traps, and review license/privacy requirements. Rebuild the result into a maintainable source project rather than deploying a raw mirror blindly. A mirror does not preserve database-driven search, forms, authentication, personalization, jobs, or admin behavior.

### Hosted crawlers and AI extraction

Hosted services can render JavaScript and map/crawl pages, but sending pages or authenticated content to a third party changes the privacy/security model. Use them only if the owner approves the processor, data region, retention, authentication method, and target terms. Default to local tools for authenticated or confidential sites.

### HAR/DevTools

Prefer endpoint metadata assembled from browser events. If exporting HAR, use the non-sensitive export mode, capture synthetic test data, sanitize, scan, and manually review. Chrome DevTools explicitly distinguishes normal HAR export from export with sensitive data; do not enable the latter for this workflow.

### Contract-first replacement

Normalize the approved contract into OpenAPI, GraphQL schema, AsyncAPI, or a small equivalent document. Use a local mock to decouple frontend work, then write contract tests against the new backend. Generated code is scaffolding; authorization and domain rules require review.

## Primary documentation

These sources describe the formats and tool capabilities used by this blueprint. Check current versions before implementing because command-line flags and product behavior change.

### Claude Code and Agent Skills

- Claude Code, **Extend Claude with skills**: https://code.claude.com/docs/en/slash-commands
- Agent Skills, **Specification**: https://agentskills.io/specification
- Anthropic, **The Complete Guide to Building Skills for Claude**: https://resources.anthropic.com/hubfs/The-Complete-Guide-to-Building-Skill-for-Claude.pdf

Key design implications: a skill is a directory with `SKILL.md`; use progressive disclosure and supporting `references/`, `scripts/`, and `assets/`; keep `SKILL.md` under 500 lines; descriptions determine discovery; `allowed-tools` pre-approves tools rather than acting as a security sandbox.

### Browser observation and visual tests

- Playwright, **Network**: https://playwright.dev/docs/network
- Playwright, **Authentication / storage state**: https://playwright.dev/docs/auth
- Playwright, **Trace viewer**: https://playwright.dev/docs/trace-viewer
- Playwright, **Screenshots**: https://playwright.dev/docs/screenshots
- Playwright, **Visual comparisons**: https://playwright.dev/docs/test-snapshots
- Playwright, **Accessibility testing**: https://playwright.dev/docs/accessibility-testing
- Playwright, **Emulation**: https://playwright.dev/docs/emulation
- Playwright, **MCP security note and capabilities**: https://playwright.dev/docs/getting-started-mcp
- Chrome DevTools, **Network features reference / HAR**: https://developer.chrome.com/docs/devtools/network/reference/

### Static retrieval and crawling policy

- GNU Wget manual: https://www.gnu.org/software/wget/manual/wget.html
- HTTrack documentation: https://www.httrack.com/html/index.html
- RFC 9309, **Robots Exclusion Protocol**: https://www.rfc-editor.org/rfc/rfc9309
- Sitemaps protocol: https://www.sitemaps.org/protocol.html

Robots directives guide crawler behavior but do not grant copyright, account access, or owner authorization.

### Contracts, quality, and security

- OpenAPI Specification: https://spec.openapis.org/oas/latest.html
- AsyncAPI Specification: https://www.asyncapi.com/docs/reference/specification/latest
- GraphQL Specification: https://spec.graphql.org/
- W3C, **Web Content Accessibility Guidelines 2.2**: https://www.w3.org/TR/WCAG22/
- WAI-ARIA Authoring Practices: https://www.w3.org/WAI/ARIA/apg/
- Chrome, **Lighthouse overview**: https://developer.chrome.com/docs/lighthouse/overview/
- web.dev, **Core Web Vitals**: https://web.dev/articles/vitals
- OWASP, **Application Security Verification Standard**: https://owasp.org/www-project-application-security-verification-standard/
- OWASP, **Web Security Testing Guide**: https://owasp.org/www-project-web-security-testing-guide/
- OWASP, **Secrets Management Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html

Security references are for hardening the replacement and testing environments the user owns, not probing the observed target beyond the explicit scope.
