# Reconstruction Test Plan

- Target: `{{TARGET_URL}}`
- Mode: `{{MODE}}`
- Initialized UTC: `{{DATE_UTC}}`

## Acceptance environment

| Variable | Reference | Replacement | Notes |
|---|---|---|---|
| Browser/version | TBD | TBD | TBD |
| Viewports/device scale | TBD | TBD | TBD |
| Locale/timezone/theme | TBD | TBD | TBD |
| Fonts | TBD | TBD | Rights/availability |
| Fixture data | approved reference | synthetic deterministic | No production personal data |

## Critical journeys

Link each `J-###` row to E2E, endpoint contract, state, and role-boundary tests.

| Journey | E2E | Visual | A11y/keyboard | Contract | Authorization | Status |
|---|---|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD | TBD | not-started |

## Quality gates

- Build/type/lint/format: `TBD`
- Unit/component/integration: `TBD`
- Visual tolerance/baseline review: `TBD`
- Accessibility target/manual assistive-tech scope: `TBD`
- Browser/device matrix: `TBD`
- Performance budgets: `TBD`
- Security/dependency/secret checks: `TBD`
- Migration/reconciliation: `TBD`
- Backup/restore/rollback: `TBD`

## Nondeterminism policy

- Stable fixture IDs/timestamps/media: `TBD`
- Animation handling: `TBD`
- Allowed masks and justification: `none unless listed`
- Baseline approval owner: `TBD`

## Commands and evidence

| Check | Command | Expected result | Evidence location |
|---|---|---|---|
| TBD | TBD | TBD | TBD |

## Exit criteria

- [ ] All critical journey rows pass.
- [ ] Authorization and tenant boundaries pass.
- [ ] No critical/high security, privacy, or data-integrity issue remains.
- [ ] Accessibility and performance targets have measured results.
- [ ] Raw sensitive evidence and secrets are absent from version control.
- [ ] Clean setup/build/deploy and backup/restore/rollback are demonstrated.
- [ ] Remaining deltas are recorded in `parity-matrix.csv` and handoff.
