# Post-build audit

A second review pass after the initial build. Twelve defects were found; all are fixed
and each is pinned by a test in `services/api/tests/test_regressions.py` that fails
against the old behaviour.

## Critical

### 1. The second approval gate could be bypassed

`CloneProject` had a single `approved_at` timestamp, but the blueprint defines **two**
human gates. The Publishing Agent checked `approved_at is not None`, so approving the
*analysis* gate also satisfied the *pre-publish* gate — a project could reach the Play
Store having never been reviewed in the simulator. This was the most serious defect in
the system: the safety property the whole design advertises did not hold.

**Fix.** Approvals are recorded per stage in a JSON `approvals` column via
`record_approval()` / `is_stage_approved()`. Publishing now requires the
`simulation` stage specifically.

*Reproduced before the fix:* approving gate 1, then draining the queue, produced a
populated `play_store_url`. After the fix the same sequence returns
`Blocked: Human approval received (pre-publish gate)`.

### 2. `apply_fixes` was a silent no-op

The Testing Agent (failed gates), Growth Agent (crash spike), and the reject endpoint
all queued `apply_fixes` tasks. `DevelopmentAgent.run()` had no branch for that task
type, so every one of them fell through to a plain rebuild. Failure reasons and
reviewer feedback were discarded, and the same build was regenerated unchanged — the
self-correction loop the architecture depends on did not exist.

**Fix.** A real `_apply_fixes` branch records the request in `remediation_history`,
classifies each reason into a patch category, appends it to `patched_issues` so codegen
responds, regenerates, and re-runs testing. Bounded at three attempts, after which the
project is parked as `needs_human_intervention` instead of looping forever.

## High

### 3. Double-approval duplicated expensive work
A double-click on Approve queued the next agent twice, running full code generation
twice. The endpoint is now idempotent: it returns early if a pending or running task
already exists for that agent and task type.

### 4. Substring matching corrupted the complexity score
`"ai" in text` matched **Em**ai**l**, **Det**ai**led**, and **Av**ai**lable**, flagging
ordinary features as high complexity. That fed the technical-feasibility component of
the clone score and the recommended MVP scope, so it distorted which apps got built.
Single tokens are now matched on word boundaries; only multi-word phrases match as
substrings.

### 5. Negated praise was counted as a complaint
`"This never crashes"` on a 5-star review scored negative, because `crashes` was
counted with no regard for the preceding negator. This inflated the mined issue counts
that justify every clone. Added a negation window; the root cause was that `never`
appeared in *both* the negator list and the complaint vocabulary, so it negated itself.
An assertion now enforces that the two sets stay disjoint.

## Medium

### 6. Staged rollout skipped closed testing
`_advance_rollout` read `auto_advance` from the stage being *entered* rather than the
one being *left*, so a release at internal testing could jump straight past closed
testing. Now reads the flag off the departing stage.

### 7. `niche.app_count` used a nonsense expression
`session.scalar(...) and len(raw_apps) or len(raw_apps)` always evaluated to
`len(raw_apps)` regardless of the query. Replaced with a real `COUNT`.

### 8. Niche saturation was a dead constant
Saturation is worth 15 points of the clone score but was seeded once and never updated,
so the score never reflected observed market structure. Now recomputed after each scan
from download concentration among the top three apps and mean incumbent rating.

## Low

### 9. Remediation history was invisible
The field was persisted but missing from the Pydantic schema, so the API never returned
it and the dashboard could not show why a build was reworked. Added to `ProjectDetail`
and surfaced as a "Fix attempts" panel.

### 10. Dead duplicate query in `seed.py`
`apps_discovered` was computed twice; the first result was immediately overwritten.

### 11. `onChange={undefined}` on a form control
Invalid React on the simulator build selector. Replaced with a plain labelled
submit form.

### 12. Pipeline board hid provenance
Cards showed the clone name but never which app was being cloned. Added
`source_app_name` to the list payload, eager-loaded with a join to avoid an N+1 query.

## Verification

```
110 tests passed, ruff clean, tsc clean, next build clean
```

Mutation-tested: reverting the gate check to `approved_at is not None` fails
`test_analysis_approval_does_not_authorise_publishing`; restoring substring matching
fails three `TestComplexityHeuristic` cases.
