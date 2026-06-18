---
expected_marker: auto-merge-skipped
scenario: At Stop-hook time (per-story scope) the auto-merge execution actuator (Story 17.3 / FR-P2-3) was ARMED — auto_merge.enabled is true (Story 17.1) AND the bundle was merge-ready (current_state equals "done") — but the merge did NOT complete. Either the 17.2 gate was not green (gate-not-met, so `gh pr merge` was never attempted) or `gh pr merge --squash <per-story-branch>` exited non-zero / the `gh` CLI was absent (merge-conflict / gh-unavailable / merge-failed). The actuator surfaced the INFORMATIONAL `auto-merge-skipped` marker carrying the skip_reason sub-classification and (for execution failures) the captured `gh` exit/stderr in gh_detail — WITHOUT merging into `main`, advancing state, or flipping any wrapper status (sensor-not-advisor; the PR remains in draft for human handling).
---
# Synthetic story: auto-merge-skipped

On this Stop-hook invocation the per-story bundle-assembly substrate ran the
Epic 17 auto-merge execution actuator (Story 17.3 / FR-P2-3). The orchestrator-
domain decision in `bundle_assembly.main()` evaluated the AC-2 conjunction:
`auto_merge.enabled is True` (Story 17.1, consumed read-only) **AND** the Story
17.2 `AutoMergeGateDecision.status == "green"` **AND** the bundle is merge-ready
(`run_state.current_state == "done"` — the non-`escalated` terminal). The merge
fires **only** when all three hold.

Here auto-merge was **armed** (`enabled: true` on a merge-ready `done` bundle)
but did **not** complete, so the substrate surfaced `auto-merge-skipped`. The
`skip_reason` sub-classification names why: `gate-not-met` (the 17.2 gate was not
green, so `gh pr merge` was never attempted), `merge-conflict` (gh reported the
PR could not be cleanly merged), `gh-unavailable` (the `gh` CLI is absent / not
on PATH), or `merge-failed` (any other non-zero `gh` exit — no open PR, the PR is
still in draft, branch protection / required checks pending, or an auth/network
failure). For execution failures the `gh_detail` `pointer_context_fields` entry
carries the captured `gh` exit code + stderr.

The actuator runs `gh pr merge --squash <per-story-branch>` — a GitHub-side PR
merge on the story's own branch. `main` / `master` / trunk is **never** a direct
write/push target, and there is **no** `git push` / `--force` / `--rebase` /
`--delete-branch` (NFR-S3 / NFR-R3). A failed merge is **data, not an
exception**: the PR remains in **draft for human handling** — failure is loud,
never silent (NFR-R6).

When `auto_merge.enabled` is **false** (the shipped default) auto-merge is simply
**not engaged**: there is no merge attempt and **no** marker (no per-run noise on
default installs), exactly as `auto-merge-gate-not-met` stays silent on the
unconfigured default.

The marker is **INFORMATIONAL** (sensor-not-advisor, mirroring
`auto-merge-gate-not-met` / `flakiness-threshold-exceeded`): emitting it does NOT
flip a wrapper status, does NOT change `current_state` (the story is already
`done`), and does NOT itself retry the merge. This is an **orchestrator-domain
runtime observability marker** (orphan, tolerated by enumeration-check), emitted
by `auto_merge_execution.surface_auto_merge_skipped` and rendered into the
per-story PR bundle by `bundle_assembly`.
