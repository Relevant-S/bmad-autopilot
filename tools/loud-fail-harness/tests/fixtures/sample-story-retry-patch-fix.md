---
purpose: walking-skeleton-retry-patch-fix-smoke-test
audience: epic-5-maintainers
story_id: sample-story-retry-patch-fix
created_by_story: "5.9"
---

## Test Infrastructure (NOT a User-Facing Sample)

This is test infrastructure for Epic 5's smoke test (Story 5.9 AC-4). It is NOT a
user-facing sample. The user-facing sample is scaffolded by Epic 7's `init` at
`_bmad-output/implementation-artifacts/sample-auto-001.md` (per FR39).

This fixture exercises the `patch`-bucket retry path: a Review-BMAD envelope that
returns one `patch`-bucket finding routed via Story 5.2's `retry_router` to a Dev
fix-only retry round per Story 5.3's contract pair, where the retry round
succeeds and the run reaches `done` with retry history rendered in the
merge-ready bundle.

## Story

As an Epic 5 maintainer needing a deterministic patch-bucket retry smoke run,
I want a single-AC story whose Dev → Review-BMAD path triggers exactly one
patch-bucket finding, then a Dev fix-only retry round that closes the finding,
So that the full retry-then-merge-ready path closes mechanically.

## Acceptance Criteria

1. The file `walking-skeleton-retry-patch-fix-output.txt` exists at the run's working-directory root and contains the literal string `walking-skeleton-retry-patch-fix-completed`.

## Tasks / Subtasks

- [ ] Task 1 — Materialize `walking-skeleton-retry-patch-fix-output.txt` (AC: #1)
  - [ ] Subtask 1.1 — Write the literal string `walking-skeleton-retry-patch-fix-completed` to the file at the run's working-directory root.

## Dev Agent Record

### Agent Model Used

### Completion Notes List

### File List
