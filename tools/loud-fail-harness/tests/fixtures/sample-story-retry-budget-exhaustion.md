---
purpose: walking-skeleton-retry-budget-exhaustion-smoke-test
audience: epic-5-maintainers
story_id: sample-story-retry-budget-exhaustion
created_by_story: "5.9"
---

## Test Infrastructure (NOT a User-Facing Sample)

This is test infrastructure for Epic 5's smoke test (Story 5.9 AC-4). It is NOT a
user-facing sample. The user-facing sample is scaffolded by Epic 7's `init` at
`_bmad-output/implementation-artifacts/sample-auto-001.md` (per FR39).

This fixture exercises the retry-budget-exhaustion escalation-path: retry rounds
persistently fail until Story 5.1's whole-story retry-budget counter is
exhausted; the run terminates per Story 5.6's `record_retry_budget_exhaustion`
non-advance + state-preservation logic, producing a retry-budget-exhausted
escalation bundle assembled by Story 5.8's `assemble_escalation_bundle` (via the
post-Story-5.8 production `default_escalation_bundle_assembler` body).

## Story

As an Epic 5 maintainer needing a deterministic retry-budget-exhaustion smoke run,
I want a single-AC story whose retry rounds persistently fail until the
whole-story retry-budget counter is exhausted,
So that Story 5.6's record_retry_budget_exhaustion fires non-advance +
state-preservation, and Story 5.8's escalation-bundle assembler renders a
retry-budget-exhausted bundle.

## Acceptance Criteria

1. The file `walking-skeleton-retry-budget-exhaustion-output.txt` exists at the run's working-directory root and contains the literal string `walking-skeleton-retry-budget-exhaustion-completed`.

## Tasks / Subtasks

- [ ] Task 1 — Materialize `walking-skeleton-retry-budget-exhaustion-output.txt` (AC: #1)
  - [ ] Subtask 1.1 — Write the literal string `walking-skeleton-retry-budget-exhaustion-completed` to the file at the run's working-directory root.

## Dev Agent Record

### Agent Model Used

### Completion Notes List

### File List
