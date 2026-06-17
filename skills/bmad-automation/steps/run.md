# /bmad-automation run — story-loop entry sequence

When the practitioner invokes `/bmad-automation run <story-id>`, execute the six-step entry sequence verbatim per AC-2 of Story 2.5. The canonical Python composition is `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/orchestrator_run_entry.py`'s `run_story_loop_entry` function — that function structurally encodes the steps below; this prose IS the LLM-runtime protocol that names what each step is for and what to surface to the practitioner.

## Pre-flight: background-execution branch (Story 21.2 / FR-P2-7)

BEFORE the six-step entry sequence, resolve the background-execution gate. Read `background_execution` from `_bmad/automation/config.yaml` via `retry_budget.resolve_background_execution` (or `read_background_execution_from_config_file`) — the same place `run-epic.md` reads `parallel_stories`. Then check whether THIS invocation is the re-entrant background child by testing the invocation arguments with `background_dispatch.is_background_reentry` (the dispatched child carries the `--foreground` sentinel; see below).

Compose the gate via `background_dispatch.dispatch_run(story_id, project_root=..., background_execution=<resolved flag>, background_reentry=<is_background_reentry(args)>, launcher=<argv launcher>, foreground_runner=<thunk that runs the six-step loop below>)`. The pure decision is `background_dispatch.decide_dispatch_mode`:

- **`background_execution: false` (the default) → mode `foreground`.** The dispatch path is **bit-identical** to the pre-Story-21.2 behavior: NO `claude --bg` argv is built, NO background-run state is created, and the six-step entry sequence below runs inline exactly as before. Zero behavioral change.
- **`background_execution: true` AND not a re-entrant child → mode `background`.** Do **NOT** run the inline six-step loop. Instead `dispatch_run` builds the `claude --bg …` argv via `background_dispatch.build_background_dispatch_command` and hands it to the injected launcher, which dispatches the whole story loop as a **detached, daemon-backed Claude Code background session** (`claude --bg "/bmad-automation run <story-id> --foreground"`). The terminal is NOT blocked; surface the non-blocking confirmation (`build_background_dispatch_confirmation`) directing the operator to `/bmad-automation status <story-id>`.
- **Re-entrant child (`is_background_reentry(args)` true) → mode `foreground`.** The detached child re-enters `/bmad-automation run <story-id>` carrying the `--foreground` sentinel; `dispatch_run` therefore runs the real six-step loop with background dispatch disabled, so the detached session executes the actual story loop and does NOT recurse.

**CRITICAL — the in-session `Agent run_in_background` subagent path is explicitly NOT used.** That is the `anthropics/claude-code#63023` silent-data-loss path the Story 21.1 spike rejected (background agents terminated on session pause with no completion notification). Background dispatch uses ONLY the daemon-backed `claude --bg` / `claude agents` surface the spike verified functional at Claude Code 2.1.179. If you find yourself wiring `Agent run_in_background` for the orchestrator dispatch, stop — you have left the `partial` surface.

The unconfirmable-on-resume loud-fail marker (`background-primitive-unstable`) fires from `/bmad-automation status`, NOT from this dispatch step — see `steps/status.md`.

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

## Review-seam 4-layer dispatch (Story 10.4)

The review-seam dispatch site is NOT in `steps/run.md` step (f) — step (f) dispatches Dev (the first specialist in the BMAD lifecycle). The review-seam dispatch fires via `steps/resume.md`'s `resume-dispatch` branch when `next_specialist=review-bmad` (the practitioner re-invokes `/bmad-automation resume <story-id>` after Dev returns and the lifecycle state advances from `in-progress` to `review` per Story 2.4). The authoritative composition prose lives at `steps/resume.md`'s "Review-seam composition (Story 10.4)" sub-section; this section restates the contract for reviewers reading `run.md` end-to-end.

At the review-seam dispatch site, the orchestrator composes `loud_fail_harness.four_layer_review_dispatch.dispatch_four_layer_review` rather than invoking `dispatch_callback(specialist="review-bmad", ...)` directly. The substrate function decides at runtime — per the `lad_enabled: bool` parameter sourced from `_bmad/automation/config.yaml#review_lad.enabled` per Story 10.4 AC-1 — whether to also dispatch `specialist="lad"` as the 4th parallel reviewer per FR-P1.5-1 / FR29.

**Config-conditional fan-out semantics.** When `lad_enabled=False` (the default opt-in posture), dispatch is bit-identical to Phase 1: the substrate invokes `dispatch_callback(specialist="review-bmad", ...)` exactly once and short-circuits — zero LAD Task-tool invocation, zero LAD dispatch log, zero `Review-LAD` cost row, zero `lad` entry in the merged `failed_layers` (Story 10.4 AC-5 bit-identity invariant). When `lad_enabled=True`, the substrate invokes `dispatch_callback` twice from the same orchestrator-side seam (one `specialist="review-bmad"`, one `specialist="lad"`); both wrapper envelopes flow into `four_layer_review_dispatch.merge_review_envelopes`. The merged envelope is what's persisted to `run-state.yaml`'s `last_envelope` field — the downstream Epic-5 retry router + Story 2.11 bundle assembler consume the merged envelope, NOT the per-wrapper envelopes individually.

**LAD-layer graceful-degradation (FR28 strict-superset).** When LAD's dispatch raises `SpecialistTimeoutExceeded` / `EnvelopeValidationFailed` / `UnknownMarkerClass` (Story 2.6's three named-invariant exceptions), the substrate catches the structural failure (does NOT propagate — graceful-degradation per FR28); the merge surfaces `failed_layers: [..., "lad"]` via the existing `surface_failed_layers` substrate (Story 3.3's three-channel atomic emission path); the synthetic `decision_needed: HIGH` finding carrying the `META_REVIEW_COMPLETENESS` discriminator + the `REVIEW_LAYER_FAILED_MARKER` marker emission record fire automatically. No new marker class is introduced (marker-taxonomy v1 27-class closed-set preserved per Story 10.4 AC-3). The 4-of-4 total-failure case (all three Review-BMAD layers AND the LAD layer fail) sets merged `status: blocked`; otherwise the surviving layer(s) carry the verdict per FR28.

**Lifecycle-state-machine transparency.** The existing post-review state-transition prose (`commit_transition` from `review` to `ready-for-qa` per Story 2.4) is UNCHANGED in semantics — the lifecycle state-machine sees one `review` seam regardless of layer count; the 4-layer composition is internal to the review-dispatch substrate per ADR-001 (orchestrator-as-skill composes substrate) + ADR-002 cell 5 (Specialist Wrapper Binding extended to 4-layer scope). `steps/resume.md`'s `next_specialist=<dev|review-bmad|qa>` enumeration is UNCHANGED at this story — the resume-protocol's `next_specialist` token reflects the BMAD-lifecycle-state-determined NEXT specialist, NOT the layer count; resuming at `current_state=in-progress` dispatches the SAME orchestrator-side review seam that fans out to 4 layers when LAD is enabled.

## Retry-routing seam (Stories 5.1 + 5.2)

At the retry-routing seam the orchestrator composes two Epic-5 substrate modules in this exact order: `loud_fail_harness.retry_router` (Story 5.2) classifies the non-pass envelope first, then `loud_fail_harness.retry_budget` (Story 5.1) gates the retry on `RoutingOutcome.RETRY_DEV`. Step 1 — `outcome = route_envelope(run_state.last_envelope)` emits one of `RETRY_DEV` / `ESCALATE` / `DEFER_AND_ADVANCE` / `DISMISS_AND_ADVANCE` per the four-bucket routing rule (FR9 + FR27). Step 2 — branch on the outcome: `RETRY_DEV` → `decision = evaluate_retry_decision(run_state, resolved_budget)`; on `DISPATCH_RETRY`, `action_items = derive_action_items(run_state.last_envelope)` and dispatch Dev with `affected_files = [item.location for item in action_items]` (Story 5.3 thickens the wrapper-side `retry_mode: fix-only` contract pair); on `HALT_BUDGET_EXHAUSTED`, route to Story 5.6's exhaustion handler. `ESCALATE` → route to Story 5.8's escalation handler directly (no budget check). `DEFER_AND_ADVANCE` → call `derive_deferred_findings(env, source_story_id=story_id)` + `record_defer_findings(deferred, deferred_work_path, story_id=story_id)` (format-MVP; Story 5.7 may tighten the `deferred-work.md` format) + advance state via Story 2.4's `commit_transition`. `DISMISS_AND_ADVANCE` → advance state directly. The route-first / budget-second ordering is load-bearing per FR8 + FR9 — `evaluate_retry_decision` is consulted only when the envelope warrants a retry, so escalate/defer/dismiss outcomes skip the budget check entirely.

## Scope-assertion verification + violation routing (Story 5.4)

When the SubagentStop hook exits 1 with the `scope-assertion-violation` marker on stderr (Story 5.4's `scope-assertion-verify` CLI surface, composing `loud_fail_harness.scope_assertion.{verify_scope_assertion, ScopeAssertionResult, ScopeAssertionDiagnostic, default_actual_diff_probe}`), the orchestrator-skill's run-loop: (1) does NOT decrement `retry_budget` (the violation is a contract halt, NOT a normal-flow retry — `evaluate_retry_decision` is NOT consulted; per `epics.md` line 2349 verbatim "the violation does NOT consume a retry round (it's a contract violation, not a normal failure)"); (2) routes directly to Story 5.6's exhaustion handler (the `escalated` lifecycle state per `run-state.yaml` `current_state` enum); (3) surfaces the violation marker prominently in the escalation bundle (Story 5.8 owns assembly; the diagnostic context — `violating_files`, `declared_scope`, `declared_expansion`, `retry_round`, `story_id` — is consumed verbatim from the marker stderr or, post-Epic-6, from the active markers list in run-state); (4) preserves the per-story branch + run-state per Story 5.6's preservation discipline (the violation-induced halt is recoverable for human inspection per FR14). The composition order is: hook fires → exit 1 → orchestrator detects marker class → route to Story 5.6 exhaustion-handler-equivalent path → escalation bundle assembly via Story 5.8.

## Retry-history externalization + reference resolution (Story 5.5)

After the orchestrator's retry-router (Story 5.2) selects a `patch`-bucket retry round AND before the run-state advances, the orchestrator persists the round's artifacts to disk via `loud_fail_harness.retry_history.persist_retry_round`. The function returns a `RetryAttemptRef` carrying the on-disk path; the orchestrator threads this ref into a thickened `RetryAttempt` entry on `next_state.retry_history` (the `round_id` + `path` fields populated). Story 2.2's `advance_run_state` is then invoked with the thickened state; the canonical-write-ordering invariant (per-round artifacts first → run-state advance second) is enforced by the wrapping `StoryDocCallback`.

Downstream consumers (`/bmad-automation status`, Story 5.8's escalation-bundle assembler, Story 8.x's resumability) lazy-load round content on demand via `loud_fail_harness.retry_history.resolve_retry_round`; dangling references emit `dangling-evidence-ref` (taxonomy line 199 REUSED — same diagnostic shape as evidence-ref dangling). The `retry-history-resolve` CLI is the canonical inspection entry point.

## Retry-budget-exhaustion routing (Story 5.6)

After the orchestrator's retry-decision evaluator (Story 5.1) returns `RetryDecision.HALT_BUDGET_EXHAUSTED` OR Dev's SubagentStop hook (Story 5.4) raises `ScopeAssertionViolation`, the orchestrator routes through `loud_fail_harness.retry_budget_exhaustion.record_retry_budget_exhaustion` with the appropriate `ExhaustionTrigger` and (for scope-violations) the `ScopeAssertionDiagnostic`. The function computes the bundle path via `compute_escalation_bundle_path`, invokes the caller-injected `EscalationBundleAssembler` (Story 5.8 supplies the production assembler; until 5.8 lands, the orchestrator injects `default_escalation_bundle_assembler`), composes Story 2.2's `advance_run_state` to rewrite `current_state` to `"escalated"` (preserving every other run-state field — `retry_history`, `branch_name`, `last_retry_directive`, `last_envelope`, `cost_to_date_by_specialist`, `active_markers`, `dispatched_specialist`), then emits the `escalation-fired` orchestrator event via the caller-injected appender. The retry budget counter is NOT decremented on either trigger path (per `epics.md` line 2349 verbatim for the scope-violation case; the budget-exhausted case has already reached the cap upstream). The `retry-budget-exhausted` marker class fires as part of the returned `RetryBudgetExhaustionResult.diagnostic` for downstream consumers (Story 6.1's loud-fail block, Story 5.8's bundle-rendering surface) to surface. The on-disk `_bmad-output/retry-history/{story_id}/{round_id}/` artifacts (Story 5.5) survive escalation by structural omission — THIS handler never invokes filesystem operations against retry-history paths. The `escalated` lifecycle state mutation is via `advance_run_state` directly, NOT via `commit_transition` (per the architectural commitment in `lifecycle_state_machine.py:97-105` that escalation is a "separate code path"). On `EscalationBundleAssemblerFailed`, run-state is unchanged (FR14 preservation invariant) and the orchestrator-skill caller is responsible for surfacing the assembler failure separately via Story 6.9's `bundle-assembly-failed` marker.
