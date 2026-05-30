---
expected_marker: parallel-story-state-pollution
scenario: Two concurrent per-story worktrees running under Phase 2 parallel mode (Epic 18 / FR-P2-4, parallel_stories=true) wrote conflicting state to a SHARED-state surface (Story 14.5 pre-provision). The collision is detected at parallel-dispatch runtime and sub-classified per surface — shared-port-collision (two worktrees allocate the same port), shared-evidence-root-collision (two worktrees resolve the same evidence subpath), OR aggregate-run-state-cross-write (two worktrees claim the same story-id in the epic/sprint aggregate, or a lost-update interleaving).
---
# Synthetic story: parallel-story-state-pollution

An Automator sprint was dispatched under Phase 2 parallel mode
(Epic 18 / FR-P2-4) with `parallel_stories: true`. Two per-story
worktrees — one for story `15-2-per-epic-retry-budget` and one for
story `18-3-concurrent-env-provisioning-discipline` — ran
concurrently, each owning its own per-story worktree and per-worktree
run-state at `_bmad/automation/worktrees/<story-id>/run-state.yaml`
(byte-isolated per Story 14.4, NOT a shared surface).

During concurrent env provisioning the two worktrees collided on a
SHARED-state surface. Per the ADR-005 Phase-2 extension (Story 14.5),
the shared-state-surface inventory is:

* `shared-port-collision` — both worktrees allocated the same port
  from the shared port pool consumed by concurrent env provisioning
  (FR7 / Epic 18 Story 18.3).
* `shared-evidence-root-collision` — both worktrees resolved the same
  evidence subpath under the shared evidence root and raced to write
  it.
* `aggregate-run-state-cross-write` — both worktrees claimed the same
  story-id in the epic/sprint aggregate run-state
  (`epic-run-state.yaml` / `sprint-run-state.yaml`, Story 14.4), OR a
  write whose pre-image disagreed with the on-disk aggregate produced
  a lost-update interleaving.

Detection happens at **parallel-dispatch RUNTIME** (Epic 18 altitude —
NOT init-time, NOT SessionStart). On detection, the parallel-dispatch
substrate emits the loud-fail `parallel-story-state-pollution` marker
via `record_marker_with_context`, carrying `{story_id}`,
`{conflicting_story_id}`, and `{shared_surface}` as
`pointer_context_fields`, sub-classified per the colliding surface.

The substrate does NOT auto-resolve the collision —
visibility-over-enforcement per Pattern 5 + NFR-R8's
story-doc-canonical recovery posture, mirroring Stories 14.2/14.3's
no-auto-`--force` doctrine. The practitioner inspects the named
surface, resolves the collision (reassign port, separate evidence
subpath, OR reconcile the aggregate run-state), then re-dispatches.

This marker is **pre-provisioned** by Story 14.5 (marker + invariant +
fixtures + docs only); the runtime detection WIRING lands in Epic 18
Story 18.2 (`cross-story-state-pollution-detection-marker-emission`) —
the flip-the-switch property. Distinct from `worktree-stale-lock`
(single-story filesystem-lock remnant from ONE crashed worktree,
Story 14.3), `recovery-state-conflict` (single-run multi-store
recovery disagreement, Story 8.2), and `orphan-run-state-detected`
(run-state for a deleted story-doc): the categorical axis here is
cross-story write-collision under concurrent worktrees.
