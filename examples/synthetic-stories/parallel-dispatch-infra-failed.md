---
expected_marker: parallel-dispatch-infra-failed
scenario: An epic dispatched via `/bmad-automation run --epic` with `parallel_stories` enabled hit an infrastructure exception in the parallel dispatcher's admission arm (`claim_provider`) or seed arm (`seed_carrier` then `pre_seed_parallel_env`). The dispatcher folded every already-completed in-flight story terminal into `epic-run-state.yaml` FIRST (status plus per-epic retry-budget `consumed` plus per-epic cost partition), THEN paused the epic on `epic-paused-on-escalation` and appended the durable sub-classified `parallel-dispatch-infra-failed` marker — never propagate-and-drop via `ThreadPoolExecutor` shutdown.
---
# Synthetic story: parallel-dispatch-infra-failed

An Automator epic `epic-24` was dispatched via `/bmad-automation run
--epic epic-24` (Story 15.1 entry) with `parallel_stories: true`
(Epic 18 / FR-P2-4). The dispatcher (`dispatch_stories_parallel`) fanned
out `≤ max_parallel_stories` per-story loops, each worktree-isolated,
folding their terminals into the epic aggregate on the dispatching thread
(single-writer to `epic-run-state.yaml`).

One of the two dispatcher-infra arms raised an infrastructure exception
while ≥1 sibling unit had already completed (or was still in flight):

* **Admission arm (`claim_provider`).** The main-thread claim source
  raised while acquiring the next story's disjoint port/claim, BEFORE the
  unit was admitted (the failing story is left undispatched, never
  registered in the live-claim registry). Sub-classification
  `claim-provider-failed`.
* **Seed arm (`seed_carrier` → `pre_seed_parallel_env`).** The deferred
  per-worktree carrier write raised (e.g. `OSError`) inside the worker,
  surfacing through `future.result()` as a typed
  `ParallelDispatchInfraFailure`. Sub-classification `seed-carrier-failed`.

Per Story 24.1 the dispatcher routed the failure through **fold-then-
surface** (the same mechanism the graceful cross-story pollution path
uses):

* Every already-completed in-flight story terminal was folded into
  `epic-run-state.yaml` FIRST — status, `per_epic_retry_budget.consumed`,
  and `per_epic_cost_partition` — via the SAME
  `fold_story_terminal` / `apply_epic_budget` / `fold_story_cost` /
  `advance_epic_run_state` path the normal completion fold uses
  (fold-BEFORE-surface; NFR-R8 write-ordering at epic altitude).
* THEN the epic transitioned to `epic-paused-on-escalation` with the
  durable `parallel-dispatch-infra-failed` marker appended to
  `active_markers`, carrying `{epic_id}`, `{run_id}`, `{story_id}`, and
  `{failing_arm}` as `pointer_context_fields`. The pause is **sticky**
  (mirrors `pollution_detected`): a draining sibling's fold — which
  recomputes `current_state` from `per_story_status` and is unaware of the
  infra failure — cannot silently downgrade the epic out of
  `epic-paused-on-escalation`.
* The function **returned** a `RunEpicLoopResult` (it did NOT propagate
  the original exception); `paused_on_story_id` names the story whose
  arm failed; no further unit was admitted.

The fold-BEFORE-surface ordering exists so a `claim_provider` /
`seed_carrier` failure can never silently destroy completed work via
`ThreadPoolExecutor` shutdown-drop, and so Epic 17's auto-merge gate —
which reads exactly these folded budget + marker terminals — never makes
a merge decision against a state that lost a completed fold with no
surfaced marker.

The marker is **emitted at parallel-dispatch RUNTIME** by
`parallel_dispatch._emit_infra_failure`. It is scoped to the two named
arms via a typed exception boundary: every OTHER worker exception
(`create_worktree`, `story_file_lock`, or the per-story `runner` itself)
keeps the accepted loud-fail-by-exception path and re-raises after its
batch siblings fold.

This marker is **distinct** from `parallel-story-state-pollution` (a
cross-story shared-surface write COLLISION between two concurrent
worktrees — a conflict, not an infra exception) and from
`worktree-stale-lock` (a single-story filesystem-lock remnant from one
crashed worktree). The substrate does NOT auto-resolve, retry, or
interrupt any in-flight story — visibility-over-enforcement per Pattern 5
+ sensor-not-advisor; the human inspects the failing arm, resolves the
underlying infrastructure fault, then re-dispatches the undispatched
stories (the completed siblings are already folded into the epic
aggregate and preserved).
