# Journey 4 — Bail-Back / AC-drift (narrative)

## Dual-framing note (per Story 8.7 AC-3 + preamble Section-3 rationale)

This journey carries TWO simultaneous framings:

- **Epic-narrower framing** (`epics.md:3418` — canonical row-level discriminator):
  AC drift → plan-drift-detected → plan re-derivation → semantic verification surface.
- **PRD-broader framing** (`prd.md:293-326` — secondary sub-narrative for
  FR34 / FR43 / FR65 / NFR-I5 row-coverage): existing-project compatibility /
  TEA-boundary orientation / N-2 story-doc tolerance.

Both framings are exercised under journey-4 in this artifact. Future
correct-course MAY reconcile the two framings into a single canonical
journey-4 description; for THIS MVP cut, both are honored.

## Reference project

Stand-in reference project per Story 8.7 AC-3 option (b). Two
sub-references:

- For the epic-AC-drift framing: synthetic mutation of `sample-auto-001`
  where the AC text is edited between QA round 1 and QA round 2 to
  trigger the AC-hash drift detection (Story 4.2).
- For the PRD-existing-project framing: the `bmad-autopilot/` workspace
  itself plus the N-2-version story-doc fixture set covering the
  `story-doc-version-out-of-window` marker contract pair (Story 7.7).

## Narrative — epic framing (AC drift)

A story's QA round 1 generates a Behavioral Plan (Story 4.1 / FR23)
hashed against the AC text. Between round 1 and round 2 (e.g.,
during a clean-retry that re-runs QA), the AC text changes — a
practitioner edited the story doc. QA detects the AC-hash drift on
round 2; the plan's `plan_status` resets from `human-reviewed` to
`generated` (Story 4.2). The orchestrator emits the
`plan-drift-detected` loud-fail marker; the PR bundle's loud-fail
block lists it with the how-to-enable pointer (FR31). QA re-derives
the plan against the current AC and re-runs verification.

This exercises the semantic-verification surface — even when
mechanical / outcome verification passes, the plan-drift signal
ensures the practitioner sees that the contract has shifted under
the test.

## Narrative — PRD framing (existing-project / TEA-boundary / N-2)

The PRD framing exercises three orthogonal compatibility surfaces
on an existing BMAD project install:

- **Existing-project init**: `/bmad-automation init` runs on a
  project that already has BMAD content under `_bmad-output/`.
  The non-destructive guard (Story 7.6 / FR41) verifies that no
  user-owned content is overwritten; the explicit-override path
  is exercised on intentional override (no marker emitted).
- **TEA-boundary orientation**: First run emits the one-time
  TEA-boundary orientation message in terminal output (Story 7.8 /
  FR34) — distinguishing what TEA validates from what the
  Automator exercises.
- **N-2 story-doc version tolerance**: An older story doc (using
  a story-doc template ≤ N-2 minor versions) is read without
  failing (Story 7.7 / FR43 / NFR-I5). Out-of-window versions
  emit the `story-doc-version-out-of-window` loud-fail marker
  with upgrade guidance per Story 7.7's marker contract pair.

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

- **Missing implementation**: none. Stories 4.1, 4.2 (AC-hash plan
  drift), 7.6 (non-destructive guard), 7.7 (N-2 version tolerance),
  7.8 (TEA-boundary orientation) are all done.
- **Missing test**: none. `test_qa_behavioral_plan.py`,
  `test_qa_plan_drift.py`, `test_init_non_destructive_guard.py`,
  `test_story_doc_version_check.py`, `test_tea_boundary_orientation.py`
  cover the matrix.
- **Missing evidence capture**: same option (b) posture as the
  prior journeys.
