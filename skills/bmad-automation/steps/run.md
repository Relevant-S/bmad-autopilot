# /bmad-automation run — story-loop entry sequence

When the practitioner invokes `/bmad-automation run <story-id>`, execute the six-step entry sequence verbatim per AC-2 of Story 2.5. The canonical Python composition is `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/orchestrator_run_entry.py`'s `run_story_loop_entry` function — that function structurally encodes the steps below; this prose IS the LLM-runtime protocol that names what each step is for and what to surface to the practitioner.

## The six-step entry sequence

The entry sequence has two phases:

1. **Pre-flight phase** (steps a–b): NO side effects. Surfaces precondition violations via named-invariant diagnostics BEFORE any commit-phase step runs. The four named-invariant exceptions (`StoryDocNotFound`, `StoryDocMalformed`, `StoryDocLifecycleStateMismatch`, `SprintStatusMismatch`) carry `marker_class: None` — these are NOT loud-fail markers; they are programmer-or-state-misalignment diagnostics surfaced in the orchestrator's terminal stream per NFR-O1 (no PR bundle is produced when the entry sequence halts at pre-flight).
2. **Commit phase** (steps c–f): side effects in the documented order. Each step composes a substrate helper exclusively (no inline duplication; no direct `run-state.yaml` writes; no inline `git` invocations).

### (a) Locate the story doc

Invoke `default_story_doc_resolver(story_id, project_root)` (or the caller-supplied `story_doc_resolver`). The resolver globs `_bmad-output/implementation-artifacts/{story_id}*.md` under `project_root` and parses the matched file's `Status:` line + `## Acceptance Criteria` section into a `StoryDocResolution`.

If the resolver returns `None` OR raises `StoryDocNotFound`: surface the diagnostic message verbatim to the terminal stream and HALT. Do NOT advance to step (b).

If the resolver raises `StoryDocMalformed`: surface the diagnostic and HALT. The story doc exists but is structurally invalid for orchestration (missing `Status:` line OR missing `## Acceptance Criteria` section); the practitioner must fix the story doc per the BMAD story template before retrying.

### (b) Validate the lifecycle state and sprint-status

Two independent checks:

- Assert `story_doc_resolution.current_state == "ready-for-dev"`. If not, raise `StoryDocLifecycleStateMismatch` and HALT — surface the diagnostic verbatim. Common observed states: `"in-progress"` (a previous run is in flight or was abandoned), `"review"` / `"qa"` / `"done"` (the story is past entry; running again would duplicate work).
- Invoke `default_sprint_status_resolver(story_id, project_root)` (or the caller-supplied resolver). Verify the returned `current_state` is in `{"ready-for-dev", "backlog"}`. If not, raise `SprintStatusMismatch` and HALT — `sprint-status.yaml` may have been left stale by a prior crashed run; the practitioner should reset the entry to `"ready-for-dev"` (or `"backlog"`) before retrying.

The two checks are independent: the file-level lifecycle state and the sprint-tracking entry may legitimately diverge during transitions, so the entry sequence is the seam where they reconcile.

### (c) Create the per-story branch

Invoke `create_story_branch(story_id, trunk_allowlist=..., working_tree_probe=..., repo_root=project_root)` (Story 2.3's helper). The helper enforces:

- NFR-S3 — git operation scope: branch creation, checkout, commit, local branch management only; no `git push`, no `git rebase`, no operations on `main` / `master` / `trunk`.
- NFR-R3 — destructive-operation halt: if the working-tree probe detects uncommitted changes, the helper raises `GitUncommittedWorkDetected` BEFORE invoking any `git` command.

Propagate `BranchLifecycleBlocked` (and its subclasses `GitUncommittedWorkDetected` / `TrunkBranchWriteRejected`) unchanged. The helper carries the `marker_class` identifier; the orchestrator emits the marker via the orchestrator-event log per Pattern 5.

### (d) Initialize run-state

Construct an initial `RunState` instance with `current_state="ready-for-dev"`, `branch_name=branch_lifecycle_result.branch_name`, and the remaining fields at their canonical empty defaults (`dispatched_specialist=None`, `last_envelope=None`, `pending_qa_dispatch_payload=None`, `retry_history=()`, `active_markers=()`, `cost_to_date_by_specialist=CostToDateBySpecialist()`).

Invoke `advance_run_state(run_state_path=..., next_state=initial_run_state, story_doc_callback=_no_op_story_doc_callback)` (Story 2.2's helper). The no-op callback is correct here because the story doc already exists per step (a)'s locate — no story-doc write is structurally needed at init time. The atomic-rename writes a fresh `run-state.yaml`.

### (e) Advance to in-progress

Construct a `next_state` `RunState` with `current_state="in-progress"` (all other fields identical to the initial state). Invoke `commit_transition(run_state_path=..., current_state=initial_run_state, next_state=next_state, story_doc_callback=story_doc_callback_factory(story_id), event_log_appender=...)` (Story 2.4's helper).

The factory is invoked HERE (not at module top-level; not at step (d)) because step (e) is the first step where a story-doc write is structurally required — the story-doc's lifecycle field transitions from `ready-for-dev` to `in-progress`, and the callback performs that write per Pattern 4 / NFR-R8 (story-doc canonical write first via callback; then atomic run-state advance).

Propagate `RunStateAdvanceBlocked`, `InvalidLifecycleTransition`, `OSError` unchanged.

### (f) Dispatch the first specialist (Dev)

Invoke `dispatch_callback(specialist="dev", story_id=story_id, run_state_path=..., story_doc_resolution=..., event_log_appender=...)`. The callback returns a `DispatchCallbackResult`.

At Story 2.5's landing, the default `dispatch_callback` is `default_dispatch_callback` — a no-op stub that returns `DispatchCallbackResult(dispatched=False, reason="dispatch stubbed pending Story 2.6")` and emits a `dispatch-stubbed` diagnostic via Python's standard `logging.info`. Story 2.6 (Task-tool dispatch with marker emission — `bmad-autopilot/docs/architecture.md`'s ADR-004 binding) replaces the stub at the call site with a real `TaskToolDispatchCallback` that constructs the specialist envelope, dispatches via the Task tool, validates the return, and feeds the envelope back through `evaluate_envelope` for the next state-transition decision.

When the stub returns, the entry sequence is complete: surface the `RunStoryLoopEntryResult` summary to the practitioner — story_id, branch_name, the `state-transition` event id, the dispatch result. Story 2.6 will replace the stubbed-dispatch reason with a real `specialist-dispatched` event in the orchestrator-event log.

## Loud-fail discipline

Errors at every step surface via named exceptions; the substrate does NOT silently swallow:

- Step (a): `StoryDocNotFound`, `StoryDocMalformed`.
- Step (b): `StoryDocLifecycleStateMismatch`, `SprintStatusMismatch`.
- Step (c): `BranchLifecycleBlocked`, `GitUncommittedWorkDetected`, `TrunkBranchWriteRejected` — these CARRY `marker_class` per Pattern 5 (loud-fail markers at runtime).
- Step (d) / (e): `RunStateAdvanceBlocked`, `InvalidLifecycleTransition`, `OSError` — propagated unchanged from the substrate helpers.
- Step (f): the `dispatch_callback` may raise; propagate unchanged. Story 2.6 codifies the dispatch-time error envelope.

The four pre-flight named-invariant exceptions (`StoryDocNotFound` / `StoryDocMalformed` / `StoryDocLifecycleStateMismatch` / `SprintStatusMismatch`) carry `marker_class: None` — they are entry-time precondition diagnostics, NOT runtime degradation markers. The orchestrator's terminal-stream output surfaces these per NFR-O1; no PR bundle is produced when the entry sequence halts at pre-flight (the bundle is built from successful runs only).

## Cross-references

- Canonical Python composition: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/orchestrator_run_entry.py`
- Architectural commitment: `bmad-autopilot/docs/architecture.md` (ADR-001 / ADR-002 / ADR-003 / ADR-005 / Pattern 4 / Pattern 5)
- Story-doc section allowlist: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/story_doc_validator.py`
- Branch-lifecycle helper: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/branch_lifecycle.py`
- Run-state atomic-write helper: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/run_state.py`
- Lifecycle state-machine helper: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/lifecycle_state_machine.py`
