# Journey 2 — First Honest Failure (narrative)

## Reference project

Stand-in reference project per Story 8.7 AC-3 option (b): the
`bmad-autopilot/` development workspace. The retry-budget exhaustion
case is exercised against the synthetic-story fixture
`tests/fixtures/sample-story-retry-budget-exhaustion.md` (committed
to the repo per Story 1.7 / Story 5.6 fixture-driven coverage).

## Narrative

The first-honest-failure path lands a story that genuinely fails QA
verification (the AC implementation drifts from the AC text — a
real defect, not a flaky test). The orchestrator dispatches Dev
which returns clean; Review-BMAD's three-layer pass is clean; QA's
behavioral verification finds the AC doesn't hold (HTTP response
shape diverges from the AC's stated contract). QA's
`semantic_verification: not_required` policy applies; QA returns
`status: fail` (not the env-setup-failed escalation class — this
is a verification failure per FR24a).

The orchestrator routes the QA-fail finding to Dev for retry-1
(Story 5.2 bucket-driven retry-routing; the retry-budget consumes
1/2 default per FR8 / Story 5.1). Dev attempts a fix with
`retry_mode: fix-only` (Story 5.3) and `scope_expanded_to: [src/greeter.py]`
(FR11). Dev's fix doesn't actually resolve the AC — the underlying
spec interpretation is ambiguous. QA fails again on retry-1; the
orchestrator routes back to Dev for retry-2.

Dev's retry-2 attempt also fails QA verification. The retry-budget
is exhausted (2/2 consumed per Story 5.6). The orchestrator does
NOT auto-advance state; does NOT auto-retry; preserves the
per-story branch (`bmad-autopilot/sample-story-retry-budget-exhaustion`)
and the run-state file (FR14 / NFR-R5). The Stop hook (FR59 /
Story 6.1) assembles the ESCALATION bundle (Story 5.8), distinct
from merge-ready, with retry history, outstanding findings,
rationale, and a pointer to `deferred-work.md` (FR15 / Story 5.7).

The escalation bundle's loud-fail block lists
`retry-budget-exhausted` (Story 5.6 / Story 6.1 / FR32). The
practitioner can run `/bmad-automation status sample-story-...`
(Story 8.4 / FR48) to inspect retry history without advancing state
(NFR-O4). The story remains in `review` lifecycle state (NOT auto-
advanced to `done`); the practitioner triages the failing AC
manually.

## Environment notes (Story 7.9 EnvironmentNotes shape)

```yaml
claude_code_version: "2.1.32"
os_label: "darwin-25.3.0"
hardware_tier: "developer-laptop"
python_version: "3.12.5"
```

## Execution date

2026-05-10 (ISO-8601).

## Discovered gaps

Per Story 8.7 AC-5's three-class triage discipline:

- **Missing implementation**: none. Stories 5.1-5.9 (Epic 5 retry
  discipline) are all done.
- **Missing test**: none. The fixture
  `tests/fixtures/sample-story-retry-budget-exhaustion.md` exists;
  `test_retry_budget_exhaustion.py` covers the exhaustion flow;
  `test_escalation_bundle_contracts.py` covers the bundle shape.
- **Missing evidence capture**: same option (b) posture as
  journey-1 — captures here describe the journey conceptually and
  cite the test fixtures + completed-story artifacts.
