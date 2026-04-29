---
purpose: walking-skeleton-smoke-test
audience: epic-2-maintainers
story_id: sample-story-walking-skeleton
created_by_story: 2.13
---

## Test Infrastructure (NOT a User-Facing Sample)

This is test infrastructure for Epic 2's smoke test. It is NOT a user-facing
sample. The user-facing sample is scaffolded by Epic 7's `init` at
`_bmad-output/implementation-artifacts/sample-auto-001.md` (per FR39).

## Story

As an Epic 2 maintainer needing a deterministic smoke run,
I want a single-file write that completes in a single dispatch loop,
So that the Dev → Review → QA → merge-ready-bundle path closes mechanically.

## Acceptance Criteria

1. The file `walking-skeleton-output.txt` exists at the run's working-directory root and contains the literal string `walking-skeleton-loop-completed`.

## Tasks / Subtasks

- [ ] Task 1 — Materialize `walking-skeleton-output.txt` (AC: #1)
  - [ ] Subtask 1.1 — Write the literal string `walking-skeleton-loop-completed` to the file at the run's working-directory root.

## Dev Agent Record

### Agent Model Used

### Completion Notes List

### File List
