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

BEFORE invoking `commit_transition`, construct the per-run streaming substrate per Story 2.12. The `event_log_appender` is the SAME closure reused at every seam in this run (here at step (e), again at step (f)'s dispatch protocol per `steps/dispatch.md`, and at every subsequent specialist return); construct it ONCE so all events flow into the same events.jsonl file AND the same terminal stream:

1. Resolve the canonical event-log path via `event_log_path = default_event_log_path(qa_evidence_root=pathlib.Path("_bmad-output/qa-evidence"), story_id=story_id, run_id=run_id)` (Story 2.12's `loud_fail_harness.event_streaming` substrate library).
2. Construct the appender via `event_log_appender = make_event_log_appender(event_log_path, stream=sys.stdout, fsync=True)`. The closure conforms to Story 2.4's `EventLogAppender = Callable[[dict[str, Any]], None]` type alias verbatim — signature `(event: dict[str, Any]) -> None`. It performs JSONL persistence FIRST, terminal render SECOND per Story 2.12 AC-4's durability invariant.

Construct a `next_state` `RunState` with `current_state="in-progress"` (all other fields identical to the initial state). Invoke `commit_transition(run_state_path=..., current_state=initial_run_state, next_state=next_state, story_doc_callback=story_doc_callback_factory(story_id), event_log_appender=event_log_appender)` (Story 2.4's helper) — the appender variable from step (1) above is passed in; the substrate invokes it once on the success path AFTER `advance_run_state` returns.

The factory is invoked HERE (not at module top-level; not at step (d)) because step (e) is the first step where a story-doc write is structurally required — the story-doc's lifecycle field transitions from `ready-for-dev` to `in-progress`, and the callback performs that write per Pattern 4 / NFR-R8 (story-doc canonical write first via callback; then atomic run-state advance).

Propagate `RunStateAdvanceBlocked`, `InvalidLifecycleTransition`, `OSError` unchanged. `OSError` raised by the streaming appender (disk-full / permission-denied / etc. on the events.jsonl write) propagates verbatim per Pattern 5; the durability invariant is "every line in events.jsonl is durable; the terminal stream is best-effort visibility".

### (f) Dispatch the first specialist (Dev)

Invoke `dispatch_callback(specialist="dev", story_id=story_id, run_state_path=..., story_doc_resolution=..., event_log_appender=event_log_appender)` — REUSE the same `event_log_appender` closure constructed at step (e) so every dispatch / return event in this run flows into the same events.jsonl + terminal stream. The callback returns a `DispatchCallbackResult`.

At Story 2.6's landing, the canonical `dispatch_callback` is constructed via `make_task_tool_dispatch_callback(registry=..., log_root=..., agent_definition_dir=..., timeout_seconds=900)` (the substrate factory at `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/specialist_dispatch.py`). The factory's returned closure is structurally compatible with Story 2.5's wildcard `DispatchCallback = Callable[..., DispatchCallbackResult]` — no edit to `orchestrator_run_entry.py` is required. The closure's body is the LLM-runtime protocol per `steps/dispatch.md`: pre-dispatch substrate composition (build the payload, emit the `specialist-dispatched` event), Task-tool invocation with wall-clock timeout monitoring, post-dispatch substrate composition (validate the return envelope, persist the diagnostic log, emit the `specialist-returned` event).

The dispatch protocol's full LLM-runtime instructions live in `steps/dispatch.md`; read that file in full BEFORE executing step (f). The protocol covers: payload construction via `build_dispatch_payload`; pre-dispatch event emission via `make_specialist_dispatched_event` + `event_log_appender`; Task-tool invocation; the wall-clock timeout protocol (raise `SpecialistTimeoutExceeded` carrying `marker_class="specialist-timeout"` + `sub_cause="timeout-exceeded"` sourced verbatim from `marker-taxonomy.yaml` entry 7; validate against the registry per AC-2; emit a synthetic `specialist-returned` event with `status="fail"`); return-envelope parsing + validation via `validate_return_envelope` (composes Story 1.2's validator exclusively); diagnostic-log persistence via `persist_dispatch_log` per NFR-O3; `specialist-returned` event emission via `make_specialist_returned_event` + `event_log_appender`.

When the dispatch returns, surface the `RunStoryLoopEntryResult` summary to the practitioner — story_id, branch_name, the `state-transition` event id, and the dispatch result (the `specialist-returned` event id + envelope status). The orchestrator's flow-policy decision (advance vs. retry vs. escalate) is driven by the envelope's `status` field via `evaluate_envelope` (Story 2.4's helper), composed at the orchestrator's next-step-loop site (NOT inside the dispatch callback — sensor-not-advisor).

## Loud-fail discipline

Errors at every step surface via named exceptions; the substrate does NOT silently swallow:

- Step (a): `StoryDocNotFound`, `StoryDocMalformed`.
- Step (b): `StoryDocLifecycleStateMismatch`, `SprintStatusMismatch`.
- Step (c): `BranchLifecycleBlocked`, `GitUncommittedWorkDetected`, `TrunkBranchWriteRejected` — these CARRY `marker_class` per Pattern 5 (loud-fail markers at runtime).
- Step (d) / (e): `RunStateAdvanceBlocked`, `InvalidLifecycleTransition`, `OSError` — propagated unchanged from the substrate helpers.
- Step (f): the `dispatch_callback` raises `SpecialistTimeoutExceeded` (carries `marker_class="specialist-timeout"` per Pattern 5 — runtime degradation marker; surfaces in PR bundle's loud-fail block per Story 6.7), `EnvelopeValidationFailed` (carries `marker_class: ClassVar[None] = None` — up-front validation diagnostic; surfaces in NFR-O1's terminal stream), `UnknownMarkerClass` (carries `marker_class: ClassVar[None] = None` — programmer-error invariant), `EventConstructionFailed` (carries `marker_class: ClassVar[None] = None` — substrate-bug indicator). The asymmetric `marker_class` posture distinguishes runtime degradation markers from programmer-or-state-misalignment diagnostics per Story 2.6's AC-6 emission protocol; see `steps/dispatch.md`'s Loud-fail discipline section for the per-exception breakdown.

The four pre-flight named-invariant exceptions (`StoryDocNotFound` / `StoryDocMalformed` / `StoryDocLifecycleStateMismatch` / `SprintStatusMismatch`) carry `marker_class: None` — they are entry-time precondition diagnostics, NOT runtime degradation markers. The orchestrator's terminal-stream output surfaces these per NFR-O1; no PR bundle is produced when the entry sequence halts at pre-flight (the bundle is built from successful runs only).

## Cross-references

- Canonical Python composition: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/orchestrator_run_entry.py`
- Per-seam streaming substrate (Story 2.12): `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/event_streaming.py` — exports `make_event_log_appender(event_log_path, *, stream=sys.stdout, fsync=True)` + `default_event_log_path(qa_evidence_root, story_id, run_id)` + `format_event_for_stream(event)`; the `EventLogAppender` closure persists JSONL FIRST to `_bmad-output/qa-evidence/{story_id}/{run_id}/events.jsonl`, then renders one line per event to `stream`.
- Specialist-dispatch substrate library + LLM-runtime protocol: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/specialist_dispatch.py` + `bmad-autopilot/skills/bmad-automation/steps/dispatch.md`
- Architectural commitment: `bmad-autopilot/docs/architecture.md` (ADR-001 / ADR-002 / ADR-003 / ADR-004 / ADR-005 / Pattern 4 / Pattern 5)
- Story-doc section allowlist: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/story_doc_validator.py`
- Branch-lifecycle helper: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/branch_lifecycle.py`
- Run-state atomic-write helper: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/run_state.py`
- Lifecycle state-machine helper: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/lifecycle_state_machine.py`

## Retry-routing seam (Stories 5.1 + 5.2)

At the retry-routing seam the orchestrator composes two Epic-5 substrate modules in this exact order: `loud_fail_harness.retry_router` (Story 5.2) classifies the non-pass envelope first, then `loud_fail_harness.retry_budget` (Story 5.1) gates the retry on `RoutingOutcome.RETRY_DEV`. Step 1 — `outcome = route_envelope(run_state.last_envelope)` emits one of `RETRY_DEV` / `ESCALATE` / `DEFER_AND_ADVANCE` / `DISMISS_AND_ADVANCE` per the four-bucket routing rule (FR9 + FR27). Step 2 — branch on the outcome: `RETRY_DEV` → `decision = evaluate_retry_decision(run_state, resolved_budget)`; on `DISPATCH_RETRY`, `action_items = derive_action_items(run_state.last_envelope)` and dispatch Dev with `affected_files = [item.location for item in action_items]` (Story 5.3 thickens the wrapper-side `retry_mode: fix-only` contract pair); on `HALT_BUDGET_EXHAUSTED`, route to Story 5.6's exhaustion handler. `ESCALATE` → route to Story 5.8's escalation handler directly (no budget check). `DEFER_AND_ADVANCE` → call `derive_deferred_findings(env, source_story_id=story_id)` + `record_defer_findings(deferred, deferred_work_path, story_id=story_id)` (format-MVP; Story 5.7 may tighten the `deferred-work.md` format) + advance state via Story 2.4's `commit_transition`. `DISMISS_AND_ADVANCE` → advance state directly. The route-first / budget-second ordering is load-bearing per FR8 + FR9 — `evaluate_retry_decision` is consulted only when the envelope warrants a retry, so escalate/defer/dismiss outcomes skip the budget check entirely.

## Scope-assertion verification + violation routing (Story 5.4)

When the SubagentStop hook exits 1 with the `scope-assertion-violation` marker on stderr (Story 5.4's `scope-assertion-verify` CLI surface, composing `loud_fail_harness.scope_assertion.{verify_scope_assertion, ScopeAssertionResult, ScopeAssertionDiagnostic, default_actual_diff_probe}`), the orchestrator-skill's run-loop: (1) does NOT decrement `retry_budget` (the violation is a contract halt, NOT a normal-flow retry — `evaluate_retry_decision` is NOT consulted; per `epics.md` line 2349 verbatim "the violation does NOT consume a retry round (it's a contract violation, not a normal failure)"); (2) routes directly to Story 5.6's exhaustion handler (the `escalated` lifecycle state per `run-state.yaml` `current_state` enum); (3) surfaces the violation marker prominently in the escalation bundle (Story 5.8 owns assembly; the diagnostic context — `violating_files`, `declared_scope`, `declared_expansion`, `retry_round`, `story_id` — is consumed verbatim from the marker stderr or, post-Epic-6, from the active markers list in run-state); (4) preserves the per-story branch + run-state per Story 5.6's preservation discipline (the violation-induced halt is recoverable for human inspection per FR14). The composition order is: hook fires → exit 1 → orchestrator detects marker class → route to Story 5.6 exhaustion-handler-equivalent path → escalation bundle assembly via Story 5.8.

## Retry-history externalization + reference resolution (Story 5.5)

After the orchestrator's retry-router (Story 5.2) selects a `patch`-bucket retry round AND before the run-state advances, the orchestrator persists the round's artifacts to disk via `loud_fail_harness.retry_history.persist_retry_round`. The function returns a `RetryAttemptRef` carrying the on-disk path; the orchestrator threads this ref into a thickened `RetryAttempt` entry on `next_state.retry_history` (the `round_id` + `path` fields populated). Story 2.2's `advance_run_state` is then invoked with the thickened state; the canonical-write-ordering invariant (per-round artifacts first → run-state advance second) is enforced by the wrapping `StoryDocCallback`.

Downstream consumers (`/bmad-automation status`, Story 5.8's escalation-bundle assembler, Story 8.x's resumability) lazy-load round content on demand via `loud_fail_harness.retry_history.resolve_retry_round`; dangling references emit `dangling-evidence-ref` (taxonomy line 199 REUSED — same diagnostic shape as evidence-ref dangling). The `retry-history-resolve` CLI is the canonical inspection entry point.
