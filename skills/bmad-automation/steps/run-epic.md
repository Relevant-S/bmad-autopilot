# /bmad-automation run --epic — epic-loop entry sequence

When the practitioner invokes `/bmad-automation run --epic <epic-id>`, execute the sequential epic loop per Story 15.1. The canonical Python composition is `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/epic_lifecycle.py`'s `run_epic_loop` function — that function structurally encodes the four phases below; this prose IS the LLM-runtime protocol that names what each phase is for and what to surface to the practitioner. It mirrors `steps/run.md`'s prose-names-the-Python-composition style one scope up (epic, not story).

The epic loop drives each contained `ready-for-dev` story through the **UNCHANGED** per-story loop (`steps/run.md`'s six-step sequence → Dev → review-seam → QA → merge-ready/escalated). The `--epic` flag is purely additive: invoking `/bmad-automation run <story-id>` (no `--epic`) reaches the per-story entry point bit-identically to Phase 1 (Story 15.1 AC-2; precedent Story 10.4 AC-5). No new specialist is introduced (the 4-specialist set Dev / Review-BMAD / QA / Review-LAD is PRD-locked); no 4th hook is added.

## The four-phase epic loop

### (1) Enumerate the contained stories

Invoke `enumerate_epic_stories(epic_id, sprint_status_path=...)`. It reads the `sprint-status.yaml` `development_status` slice for `<epic-id>` (e.g. `epic-15` → every `15-*` story key; the `epic-15` / `epic-15-retrospective` keys are excluded by the `<N>-` prefix test), keeps only entries whose status is `ready-for-dev`, and returns them in epic-defined (key-ascending, numeric-ordinal) order so `15-2-*` precedes `15-10-*`.

If enumeration yields zero `ready-for-dev` stories, OR the sprint-status file is missing/malformed, OR `<epic-id>` is not of the form `epic-<N>`: `EpicStoryEnumerationError` is raised. Surface its diagnostic verbatim to the terminal stream and HALT. This is an **entry-time precondition diagnostic** (`marker_class = None`), NOT a loud-fail runtime marker — the same posture as `steps/run.md`'s pre-flight `StoryDocNotFound` / `SprintStatusMismatch` family; no PR bundle is produced when the epic entry halts at enumeration.

### (2) Initialize the epic-run-state cache

Resolve the per-epic retry-budget multiplier from `_bmad/automation/config.yaml` via `retry_budget.resolve_per_epic_retry_budget_multiplier` (or `read_per_epic_retry_budget_multiplier_from_config_file`) — an integer ≥ 1, default 2 (Story 15.2 AC-1; the per-story `retry_budget` is resolved the same way one scope down in `steps/run.md`). A malformed value raises `RetryBudgetConfigError` with the field name + remediation hint (loud-fail; surface verbatim).

Invoke `init_epic_run_state(epic_id, run_id, story_ids, multiplier=<resolved>)` to seed an `EpicRunState` at `current_state="epic-in-progress"`, with `per_story_status` seeded from each story's current lifecycle state (`ready-for-dev` for the enumerated stories), the `per_epic_retry_budget` **structure** populated (`effective_budget = multiplier × story_count`, `consumed = 0`), the `per_epic_cost_partition` zeroed, and `active_markers=()`. (`run_epic_loop` threads the resolved multiplier into `init_epic_run_state` for you.)

Persist it via `advance_epic_run_state(epic_run_state_path, epic_state, transient_marker_classes=..., taxonomy_path=...)` (Story 15.1's epic-scope atomic-write helper — the epic sibling of `run-state.py`'s `advance_run_state`). The canonical on-disk path is `_bmad/automation/epic-run-state.yaml` (`epic_run_state.DEFAULT_EPIC_RUN_STATE_PATH`), co-located with the per-story `_bmad/automation/run-state.yaml` per ADR-009's `_bmad/automation/` umbrella.

**The epic-run-state is a CACHE, not a fourth canonical store (NFR-R8 / ADR-005).** It is an aggregate over the per-story story-docs + `sprint-status.yaml` and is reconstructable from them on recovery; `advance_epic_run_state` performs the cache write only — there is NO story-doc callback at epic scope (the canonical story-doc writes happen one scope down, inside each story's per-story loop). Recovery tiebreak: the story-doc wins.

**Resolve the transient-class set ONCE** (the loop threads it through every `advance_epic_run_state` call). See the re-derivation model below.

### (3) Dispatch each story sequentially

For each story in enumerated order, the loop:

1. Invokes the per-story driver `story_loop_runner(story_id=..., index=M, total=N)`. In production this drives the story through the UNCHANGED per-story loop per `steps/run.md` (locate → validate → branch → init run-state → in-progress → dispatch Dev, then the hook-driven Dev → review-seam → QA progression across resume invocations) and returns a `StoryLoopOutcome` carrying the story's terminal per-story status (`merge-ready` / `done` / `escalated`) **AND** the number of per-story retries that story consumed (read from the per-story `RunState`'s `retry_history`; Story 15.2 AC-3 — chosen over the epic loop reading `DEFAULT_RUN_STATE_PATH` because Epic 18 relocates the per-story run-state per-worktree). **NO change to `orchestrator_run_entry.py`'s public composition, NO change to the per-story `RunState` shape.** The per-story `event_log_appender` (from `steps/run.md` step (e)) is reused UNCHANGED within each story — the epic layer does NOT replace or wrap the per-story stream.
2. Folds the story's terminal status into the epic aggregate via `fold_story_terminal` (updates `per_story_status`, recomputes `current_state` via the PURE `derive_epic_state`).
3. Folds the story's `retries_consumed` into the cumulative `per_epic_retry_budget.consumed`, then applies the per-epic budget via the pure `apply_epic_budget(base_state, consumed, effective_budget, has_undispatched=...)` — layered ON TOP of `derive_epic_state` (budget logic never leaks into `derive_epic_state`). The budget is checked **AFTER** the boundary story reaches terminal — the in-flight story is never interrupted (sensor-not-advisor). If the cumulative `consumed >= effective_budget` with undispatched stories remaining, the epic transitions to `epic-paused-on-budget` and `epic-budget-exhausted` is appended to `active_markers`; escalation keeps `current_state` precedence (the marker still emits additively — AC-6); exhausting the budget exactly on the final story is `epic-complete`, not a pause.
4. Persists the advance via `advance_epic_run_state` (the durable `epic-budget-exhausted` marker survives the transient-marker write-back filter).
5. Surfaces the AC-5 per-epic framing line ("story M of N (`<story-id>`) → `<status>`; epic now `<epic-state>`") via the `progress_sink` — written to the SAME terminal stream the per-story events render to (NFR-O1 live streaming; the epic layer ADDS a framing line at each per-story completion boundary, it does not replace the per-story stream).

Stories run **strictly sequentially** in epic-defined order. Parallel dispatch is Epic 18 (`parallel_stories: true`) — there is no concurrent dispatch here. (Git worktrees share `.git/`; concurrent `git add`/`commit` race on `.git/index.lock` — sequential dispatch holds at most one in-flight story and sidesteps that contention class entirely.)

### (4) Pause on escalation OR budget exhaustion (sensor-not-advisor)

If folding a story's terminal status transitions the epic to `epic-paused-on-escalation` (the story reached `escalated`) **OR** the cumulative per-epic retries exhaust the budget with undispatched stories remaining (`epic-paused-on-budget`), the loop STOPS: the downstream stories do NOT auto-advance (Story 15.1 AC-4 / Story 15.2 AC-4). The orchestrator records the pause (terminal stream + the persisted epic-run-state, including the `epic-budget-exhausted` marker on a budget pause; the running epic-level PR bundle is Story 15.3) and surfaces it, but does NOT itself decide remediation — **that decision is the human's**. The two pauses drive DIFFERENT remediation: `epic-paused-on-escalation` is a *quality* issue (inspect the escalated story); `epic-paused-on-budget` is a *cost* issue (raise `per_epic_retry_budget_multiplier` or split the epic, then re-dispatch). When a boundary story BOTH escalated AND exhausted the budget, `current_state` is `epic-paused-on-escalation` (the proximate human-actionable signal) and the `epic-budget-exhausted` marker still emits additively (the cost overage is never silently lost). Flow policy that *halts* is in scope; flow policy that *resolves* a pause is not.

On a clean run (every contained story terminal: `merge-ready` / `done`), the epic transitions to `epic-complete` — including the case where the budget is exhausted exactly on the final story (no undispatched stories remain to guard, so it is NOT a pause).

## Transient-marker re-derivation model (AC-6 — the ratified blocker decision)

This is the first story to persist a run-state and re-feed it on the next SessionStart. To keep a recovery-recomputed `worktree-stale-lock` marker from going **sticky** (contradicting NFR-R2 "transient signal, not sticky state"), Story 15.1 ratifies the **re-derivation model**:

- The Orchestrator MUST NOT persist transient condition-markers into any run-state it writes back to disk. `active_markers` in a persisted (epic OR per-worktree) run-state carries ONLY durable markers.
- Transient condition-markers are recomputed each cycle from live state by `evaluate_reattach`, which is left **UNCHANGED** (honoring Story 14.6 AC-7). Epic-scope SessionStart recovery reuses the existing SessionStart hook + `evaluate_reattach` — there is no 4th hook and no recovery-path edit.
- The transient/durable axis is sourced **structurally from the marker taxonomy** (`marker-taxonomy.yaml`'s `lifetime` field: `transient` | `durable`, default `durable`), NOT a hardcoded code-level enumeration. `advance_epic_run_state` (and `advance_worktree_run_state` for any per-worktree write-back the epic loop performs) filters out every marker class whose taxonomy `lifetime` is `transient` before the atomic rename. The filter consults the taxonomy at runtime, so a future transient marker is covered with zero filter edits.

The structural primitive is `epic_run_state.filter_transient_markers`, fed by `reconciler.load_marker_lifetimes`. `worktree-stale-lock` is the sole `transient` entry at this story; durable markers are never stripped (preserving the Story 1.4 marker-permanence rule).

## Epic-scope SessionStart recovery (no 4th hook)

Epic-scope reattachment reuses the existing SessionStart hook + `evaluate_reattach` UNCHANGED. The epic loop's write-back (phase 2 + 3 above) is where the transient-marker filter prevents stickiness; recovery re-derives the live `worktree-stale-lock` verdict as it does today (the marker is a derived view of live filesystem-lock state, not durable history). Epic-level PR bundle assembly is Story 15.3's Stop-hook extension, not this story.

## Scope boundaries

- **Budget ENFORCEMENT landed in Story 15.2** (this protocol): the resolved `per_epic_retry_budget_multiplier` is threaded into init, per-story retries fold into `per_epic_retry_budget.consumed`, exhaustion reaches `epic-paused-on-budget` and emits the durable `epic-budget-exhausted` marker into `active_markers`. The per-story retry budget (`retry_budget` / `evaluate_retry_decision`) is UNCHANGED — the per-epic budget is a SEPARATE, cumulative, additive ceiling on top of it.
- **Epic-level PR bundle is Story 15.3.** Surfacing the pause here means terminal-stream + epic-run-state `active_markers` only; do NOT extend the Stop hook.
- **`status --epic` is Story 15.4.**
- **Parallel dispatch is Epic 18.** Sequential only.

## Loud-fail discipline

- Enumeration failures surface via `EpicStoryEnumerationError` (`marker_class = None` — entry-time precondition diagnostic; terminal stream, no PR bundle).
- Per-story failures surface via the UNCHANGED per-story loop's named exceptions + loud-fail markers (`steps/run.md` / `steps/dispatch.md`); the epic layer does not intercept them.
- Epic-run-state writes propagate `OSError` (temp-write / atomic-rename failure) unchanged from `advance_epic_run_state`; the prior cache is left intact (never a partial-state file).

## Cross-references

- Canonical Python composition: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/epic_lifecycle.py` (`run_epic_loop`, `enumerate_epic_stories`, `init_epic_run_state`, `derive_epic_state`, `fold_story_terminal`, `apply_epic_budget`, `StoryLoopOutcome`, `EPIC_BUDGET_EXHAUSTED_MARKER`).
- Per-epic budget resolver: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/retry_budget.py` (`resolve_per_epic_retry_budget_multiplier`, `read_per_epic_retry_budget_multiplier_from_config_file`, `DEFAULT_PER_EPIC_RETRY_MULTIPLIER`, `RetryBudgetConfigError`).
- Epic-scope atomic-write helper + transient-marker filter: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/epic_run_state.py` (`advance_epic_run_state`, `advance_worktree_run_state`, `filter_transient_markers`, `DEFAULT_EPIC_RUN_STATE_PATH`).
- Taxonomy lifetime source: `bmad-autopilot/schemas/marker-taxonomy.yaml` (`lifetime` field) + `loud_fail_harness.reconciler.load_marker_lifetimes`.
- Per-story loop (UNCHANGED, composed per story): `bmad-autopilot/skills/bmad-automation/steps/run.md` + `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/orchestrator_run_entry.py`.
- Architectural commitments: `bmad-autopilot/docs/architecture.md` (ADR-005 three-store / NFR-R8 story-doc-canonical; ADR-009 worktree umbrella; NFR-R1 atomic-write; NFR-R2 transient-not-sticky; NFR-O1 terminal streaming).
- SessionStart recovery (UNCHANGED): `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/session_start_reattach.py` (`evaluate_reattach`).
