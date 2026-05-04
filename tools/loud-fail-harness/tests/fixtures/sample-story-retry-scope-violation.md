---
purpose: walking-skeleton-retry-scope-violation-smoke-test
audience: epic-5-maintainers
story_id: sample-story-retry-scope-violation
created_by_story: "5.9"
---

## Test Infrastructure (NOT a User-Facing Sample)

This is test infrastructure for Epic 5's smoke test (Story 5.9 AC-4). It is NOT a
user-facing sample. The user-facing sample is scaffolded by Epic 7's `init` at
`_bmad-output/implementation-artifacts/sample-auto-001.md` (per FR39).

This fixture exercises the scope-assertion-violation negative-path: a Dev fix-only
retry round whose envelope's `affected_files` expands beyond the contracted
`scope_expanded_to` per Story 5.3's contract pair, causing
`scope_assertion.verify_scope_assertion` to surface a violation per Story 5.4's
loud-fail surface, and the run terminates with a scope-assertion-violation
escalation bundle assembled by Story 5.8's `assemble_escalation_bundle`.

## Story

As an Epic 5 maintainer needing a deterministic scope-violation smoke run,
I want a single-AC story whose Dev fix-only retry round expands `affected_files`
beyond the contracted scope,
So that Story 5.4's verify_scope_assertion surfaces the violation and Story 5.8's
escalation-bundle assembler renders a scope-assertion-violation bundle.

## Acceptance Criteria

1. The file `walking-skeleton-retry-scope-violation-output.txt` exists at the run's working-directory root and contains the literal string `walking-skeleton-retry-scope-violation-completed`.

## Tasks / Subtasks

- [ ] Task 1 — Materialize `walking-skeleton-retry-scope-violation-output.txt` (AC: #1)
  - [ ] Subtask 1.1 — Write the literal string `walking-skeleton-retry-scope-violation-completed` to the file at the run's working-directory root.

## Dev Agent Record

### Agent Model Used

### Completion Notes List

### File List
