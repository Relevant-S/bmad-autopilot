# /bmad-automation run --sprint — sprint-loop entry sequence

When the practitioner invokes `/bmad-automation run --sprint <sprint-id>`, execute the sequential sprint loop per Story 16.1. The canonical Python composition is `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/sprint_lifecycle.py`'s `run_sprint_loop` function — that function structurally encodes the four phases below; this prose IS the LLM-runtime protocol that names what each phase is for and what to surface to the practitioner. It mirrors `steps/run-epic.md`'s prose-names-the-Python-composition style one scope up (sprint, not epic).

The sprint loop drives each contained **sprint unit** sequentially: an *epic* unit through the **UNCHANGED** epic loop (`steps/run-epic.md` → `run_epic_loop`), and an *unassigned story* unit through the **UNCHANGED** per-story loop (`steps/run.md`'s six-step sequence). The `--sprint` flag is purely additive: invoking `/bmad-automation run --epic <epic-id>` (no `--sprint`) reaches the epic entry point bit-identically to Epic 15, and `/bmad-automation run <story-id>` reaches the per-story entry point bit-identically to Phase 1 (Story 16.1 AC-2; precedent Story 15.1 AC-2 / Story 10.4 AC-5). No new specialist is introduced (the 4-specialist set Dev / Review-BMAD / QA / Review-LAD is PRD-locked); no 4th hook is added.

## `<sprint-id>` semantics

`<sprint-id>` is a **free-form run label**, not a slice key. BMAD's `sprint-status.yaml` is a single-sprint artifact — one `development_status` map of epics + stories with no explicit multi-sprint partition field. The sprint scope is therefore the **entire `development_status` section**: all `epic-<N>` units with ≥ 1 `ready-for-dev` story + all unassigned `ready-for-dev` stories, in document order. The label correlates the run with its `sprint-run-state.yaml` record; it does NOT narrow the file. (Forward-compat: if a future BMAD release adds explicit per-sprint partitioning, `enumerate_sprint_units` narrows to that slice at the single commented seam — not built here.)

## The four-phase sprint loop

### (1) Enumerate the contained sprint units

Invoke `enumerate_sprint_units(sprint_id, sprint_status_path=...)`. It reads the `sprint-status.yaml` `development_status` section and returns, in document order, the contained **sprint units**:

- **epic units** — every `epic-<N>` key whose slice holds ≥ 1 `ready-for-dev` story (an epic with zero ready-for-dev stories — e.g. an already-`done` epic — contributes none and is skipped).
- **unassigned story units** — every `ready-for-dev` story `<N>-<M>-…` whose parent `epic-<N>` key is **absent** from `development_status` (assignment is about the PRESENCE of the `epic-<N>` key, not the epic's status). Possibly empty — a sprint whose stories are all epic-assigned is conformant (in this workspace every story is epic-grouped, so the unassigned set is empty; the mechanism exists for BMAD sprints with loose standalone stories).

Sprint order is `development_status` document order (top-to-bottom — the BMAD file-order convention `create-story` follows), with epic-id-ascending as the deterministic fallback when document order is ambiguous (an ordered mapping never is).

If enumeration yields zero sprint units, OR `sprint-status.yaml` is missing/malformed: `SprintUnitEnumerationError` is raised. Surface its diagnostic verbatim to the terminal stream and HALT. This is an **entry-time precondition diagnostic** (`marker_class = None`), NOT a loud-fail runtime marker — the same posture as `steps/run-epic.md`'s `EpicStoryEnumerationError` and `steps/run.md`'s pre-flight `StoryDocNotFound` / `SprintStatusMismatch` family; **no sprint PR bundle is produced when the sprint entry halts at enumeration**.

### (2) Initialize the sprint-run-state cache

Invoke `init_sprint_run_state(sprint_id, run_id, epic_ids, unassigned_story_ids, multiplier=<resolved>, per_story_budget=<resolved>, effective_budget_override=<resolved>)` to seed a `SprintRunState` at `current_state="sprint-in-progress"`, with `per_epic_status` seeded `epic-in-progress` per epic (pre-dispatch), `unassigned_story_ids` recorded in document order, the `per_sprint_retry_budget` structure populated, and `active_markers=()`. (`run_sprint_loop` threads the resolved config values into `init_sprint_run_state` for you.)

**Per-sprint budget (Story 16.2 — the authoritative formula + config).** `effective_budget = compute_per_sprint_effective_budget(multiplier, epic_count, per_story_budget, unassigned_story_count)` = `per_sprint_retry_budget_multiplier × epic_count + retry_budget × unassigned_story_count`. The leading term reuses `DEFAULT_PER_SPRINT_RETRY_MULTIPLIER = 2` (resolvable via config); the trailing term reuses the per-story `retry_budget` for each unassigned story. The config field `per_sprint_retry_budget` (read via `resolve_per_sprint_retry_budget_override` / `read_per_sprint_retry_budget_from_config_file`) is an **absolute override** of the computed `effective_budget` (omit it to auto-compute; `0` = no per-sprint retries) — contrast `per_epic_retry_budget_multiplier`, which is a multiplier. `consumed` starts at 0; the cumulative fold happens in phase (3).

Persist the seed via `advance_sprint_run_state(sprint_run_state_path, sprint_state, transient_marker_classes=..., taxonomy_path=...)` (Story 16.1's sprint-scope atomic-write helper — the sprint sibling of `advance_epic_run_state`). The canonical on-disk path is `_bmad/automation/sprint-run-state.yaml` (`epic_run_state.DEFAULT_SPRINT_RUN_STATE_PATH`), co-located with the epic-run-state + per-story run-state caches per ADR-009's `_bmad/automation/` umbrella.

**The sprint-run-state is a CACHE, not a fifth canonical store (NFR-R8 / ADR-005).** It is an aggregate over the per-epic epic-run-state documents (+ the per-story run-state documents for unassigned stories) + `sprint-status.yaml`, reconstructable from them on recovery; `advance_sprint_run_state` performs the cache write only — there is NO story-doc callback at sprint scope (the canonical story-doc writes happen two scopes down, inside each per-story loop). Recovery tiebreak: the story-doc wins.

**Resolve the transient-class set ONCE** (the loop threads it through every `advance_sprint_run_state` call). See the re-derivation model below.

### (3) Dispatch each unit sequentially

For each unit in enumerated (document) order, the loop:

1. **Epic unit** — addresses a **per-epic** `epic_run_state_path` via `epic_run_state_path_for(epic_id, repo_root=...)` (`_bmad/automation/epic-run-state-<epic-id>.yaml`) so sequential epics in one sprint do NOT clobber each other's epic-run-state cache and each completed epic's cache survives for `status --epic` / `status --sprint` (Story 16.4) — NOT the single per-story-scope `DEFAULT_EPIC_RUN_STATE_PATH`. It then drives the epic through the **UNCHANGED** `run_epic_loop` (resolving the per-epic retry-budget multiplier from config + reusing the per-epic "story M of N" framing and the per-story `event_log_appender` UNCHANGED within the epic) and folds the epic's terminal `EpicCurrentState` into the sprint aggregate via `fold_epic_terminal`.
   **Unassigned story unit** — drives the story through the **UNCHANGED** per-story loop (`run_story_loop_entry` → Dev → review-seam → QA → merge-ready/escalated per `steps/run.md`, reusing the per-story `event_log_appender` UNCHANGED) and folds the story's terminal `PerStoryStatus` into the sprint aggregate via `fold_unassigned_story_terminal`. **NO change to `orchestrator_run_entry.py`'s public composition, NO change to the per-story `RunState` shape; NO change to `epic_lifecycle.py`'s public composition or the per-epic `EpicRunState` shape.**
2. Recomputes the sprint `current_state` via the PURE `derive_sprint_state(per_epic_status, per_unassigned_status)` (folded in step 1; budget/rate logic never leaks into it).
3. **Folds the unit's retry consumption into the cumulative `per_sprint_retry_budget.consumed`** (Story 16.2) — for an *epic* unit the count is the epic's `RunEpicLoopResult.final_state.per_epic_retry_budget.consumed`, surfaced via `EpicLoopOutcome.retries_consumed`; for an *unassigned story* unit it is `StoryLoopOutcome.retries_consumed`. Then applies the per-sprint budget pause via the PURE `apply_sprint_budget(base_state, consumed, effective_budget, has_undispatched=index < total)` (the sprint sibling of `apply_epic_budget`).
4. **Updates the running escalation tally and emits the informational `sprint-escalation-rate-exceeded` marker** (Story 16.2) — accumulates `stories_completed` (an epic contributes `len(dispatched_story_ids)` via `EpicLoopOutcome.stories_completed`; an unassigned story contributes `1`) and `escalated_stories` (an epic contributes `EpicLoopOutcome.escalated_count` = `1` iff it returned `epic-paused-on-escalation`; an unassigned story contributes `1` iff terminal `escalated`). When `escalated_stories / stories_completed > sprint_escalation_rate_threshold` (config-resolved; default 0.25) and the marker is not already present, append `SPRINT_ESCALATION_RATE_EXCEEDED_MARKER` to `active_markers` (idempotent). **This marker is INFORMATIONAL: it does NOT change `current_state` and does NOT pause the sprint** (sensor-not-advisor — the practitioner decides whether to pause manually).
5. Persists the advance via `advance_sprint_run_state` (durable markers — both `sprint-escalation-rate-exceeded` and any contained-scope durable markers — survive the transient write-back filter).
6. Surfaces the AC-5 per-sprint framing line (see streaming below) via the `progress_sink`.

Units run **strictly sequentially** in sprint-defined order — at most one unit (epic or story) in flight. Parallel dispatch is Epic 18 (`parallel_stories: true`) — there is no concurrent dispatch here. (Git worktrees share `.git/`; concurrent `git add`/`commit` race on `.git/index.lock` — sequential dispatch holds at most one in-flight unit and sidesteps that contention class entirely.)

### (4) Pause on a contained-unit pause/escalation (sensor-not-advisor)

If folding a unit (or the per-sprint budget fold) transitions the sprint to `sprint-paused-on-escalation` **OR** `sprint-paused-on-budget`, the loop STOPS: the downstream units do NOT auto-advance (AC-4). The transitions are:

- a contained epic returning `epic-paused-on-escalation` → `sprint-paused-on-escalation`;
- an unassigned story reaching `escalated` → `sprint-paused-on-escalation`;
- a contained epic returning `epic-paused-on-budget` → `sprint-paused-on-budget`;
- **the CUMULATIVE per-sprint budget exhausting** (`consumed >= effective_budget` with undispatched units remaining) → `sprint-paused-on-budget` (Story 16.2). This is the COMMON budget path: the per-sprint ceiling (`~2 × epic_count`) is far tighter than the summed per-epic ceilings, so the sprint typically pauses on the cumulative ceiling before any single epic exhausts. The in-flight unit that triggered exhaustion is allowed to FINISH (the budget is checked AFTER it reaches terminal — sensor-not-advisor); exhausting exactly on the final unit is `sprint-complete`, not a pause.

Escalation keeps **precedence** over budget when both are present at the same boundary (`apply_sprint_budget` only upgrades `sprint-in-progress`, never overriding an escalation pause — mirroring `apply_epic_budget` one scope down). The two pause states are **distinct, two axes, two remediation paths**: `sprint-paused-on-escalation` = a *quality* issue (inspect the paused unit); `sprint-paused-on-budget` = a *cost* issue (raise `per_sprint_retry_budget` in config or split the sprint, then re-dispatch). Note the **third surface, the `sprint-escalation-rate-exceeded` marker (phase 3 step 4), is a quality-axis SIGNAL that does NOT pause** — distinct from the `sprint-paused-on-budget` cost-axis STATE. Story 16.2 adds NO `sprint-budget-exhausted` marker: the cumulative-budget pause is self-surfacing via the `sprint-paused-on-budget` state (visible in the run-state cache + `status --sprint` + the 16.3 artifact), whereas the rate signal needs a marker precisely because it does NOT change state. The orchestrator records the pause and surfaces it, but does NOT decide whether to skip the paused unit or hold the sprint — **that decision is the human's**.

On a clean run (every contained epic `epic-complete` AND every unassigned story `merge-ready` / `done`) the sprint transitions to `sprint-complete`.

## AC-6 boundary — NO retrospective, NO sprint-status artifact (PRD-locked)

The sprint loop's ONLY persisted output is the `sprint-run-state.yaml` cache + the per-unit epic/per-story canonical artifacts the contained loops already write. It MUST NOT emit:

- a **retrospective artifact** of any kind — reflection on what went well/badly is a human responsibility (Phase 2 Journey Pointer 2 "retrospective stays user-managed"; automating it would violate sensor-not-advisor at sprint scope). BMAD's `/retrospective` is a separate, explicitly human-run workflow.
- a **`sprint-status-artifact-<sprint-id>.md`** — that structured (non-retrospective) sprint-close artifact is Story 16.3's deliverable, not 16.1's. (Even 16.3's artifact is explicitly NOT a retrospective — this boundary holds across the whole epic.)

## Transient-marker re-derivation model (AC-7 — reused, no taxonomy change)

The re-derivation model Story 15.1 ratified at epic scope is reused UNCHANGED at sprint scope. `advance_sprint_run_state` filters out every marker class whose taxonomy `lifetime` is `transient` before the atomic rename — reusing the EXISTING `epic_run_state.filter_transient_markers` + `reconciler.load_marker_lifetimes` machinery; the transient-class set is resolved ONCE and threaded through every `advance_sprint_run_state` call (the per-call-taxonomy-read pattern Story 15.1's review corrected). `active_markers` in the persisted sprint-run-state carries ONLY durable markers; transient condition-markers are recomputed each cycle by the UNCHANGED `evaluate_reattach`.

Story 16.2 adds **ONE** new durable marker class — `sprint-escalation-rate-exceeded` (taxonomy PATCH bump 1.10 → 1.11, closed-set 32 → 33) — sourced verbatim as `SPRINT_ESCALATION_RATE_EXCEEDED_MARKER`. Being `durable` (default lifetime by omission), it survives the transient write-back filter and is never stripped. The cumulative per-sprint budget pause adds NO marker (it is surfaced via the `sprint-paused-on-budget` STATE — see phase 4).

## Sprint-scope SessionStart recovery (no 4th hook)

Sprint-scope reattachment reuses the existing SessionStart hook + `evaluate_reattach` UNCHANGED — no 4th hook, no recovery-path edit. The sprint loop's write-back (phases 2 + 3 above) is where the transient-marker filter prevents stickiness; recovery re-derives the live verdict as it does today. There is no sprint-level PR bundle and therefore no Stop-hook extension in 16.1 (Epic 16 has no sprint-PR-bundle story — the sprint's observability surface is the `sprint-run-state.yaml` cache + (16.4) `status --sprint` + (16.3) the sprint-status artifact). The contained epic/per-story loops' own hook-driven progressions (Stop / SessionStart) are unchanged within each unit.

## Scope boundaries

- **Per-sprint budget enforcement + escalation-rate marker → Story 16.2 (landed here).** The cumulative budget folds `consumed` and pauses on `sprint-paused-on-budget`; the escalation-rate threshold emits the informational `sprint-escalation-rate-exceeded` marker (non-blocking).
- **`sprint-status-artifact-*.md` → Story 16.3** (not a retrospective; not written here).
- **`status --sprint <sprint-id>` → Story 16.4** (no read-only sprint-status query command here).
- **Sprint-level PR bundle → not in Epic 16's breakdown** (do NOT extend the Stop hook in 16.1; a sprint-PR-bundle need would be a correct-course addition, not silent scope creep).
- **Parallel dispatch → Epic 18** (sequential only).
- **No new specialist, no 4th hook, substrate stays at FIVE components.**

## Loud-fail discipline

- Enumeration failures surface via `SprintUnitEnumerationError` (`marker_class = None` — entry-time precondition diagnostic; terminal stream, no PR bundle).
- Contained-unit failures surface via the UNCHANGED epic loop / per-story loop named exceptions + loud-fail markers (`steps/run-epic.md` / `steps/run.md` / `steps/dispatch.md`); the sprint layer does not intercept them.
- Sprint-run-state writes propagate `OSError` (temp-write / atomic-rename failure) unchanged from `advance_sprint_run_state`; the prior cache is left intact (never a partial-state file).
- An `EpicLoopRunner` / `StoryLoopRunner` exception inside `run_sprint_loop` propagates with no sprint-scope error marker (the sprint scope inherits Story 15.1's deferred `run_epic_loop` runner-exception posture — recovery via the canonical stores, ADR-005; see `deferred-work.md`). 16.1 does NOT invent a sprint-error-marker class.

## Per-sprint terminal streaming (AC-5 / NFR-O1)

The terminal stream surfaces per-sprint progress as `[sprint] unit K of T (<epic-id> | <story-id>) → <outcome-state>; sprint now <sprint-state>` at each unit-completion boundary, reusing the contained epic loop's existing per-epic "story M of N" framing and the per-story `event_log_appender` UNCHANGED within each unit — the sprint layer ADDS a unit-progress framing line at each unit-completion boundary; it does NOT replace or wrap the per-epic or per-story streams.

## Cross-references

- Canonical Python composition: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/sprint_lifecycle.py` (`run_sprint_loop`, `enumerate_sprint_units`, `init_sprint_run_state`, `compute_per_sprint_effective_budget`, `derive_sprint_state`, `apply_sprint_budget`, `fold_epic_terminal`, `fold_unassigned_story_terminal`, `EpicLoopRunner`, `EpicLoopOutcome`, `SprintUnitEnumerationError`, `DEFAULT_PER_SPRINT_RETRY_MULTIPLIER`, `DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD`, `SPRINT_ESCALATION_RATE_EXCEEDED_MARKER`).
- Sprint-scope atomic-write helper + per-epic path addressing: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/epic_run_state.py` (`advance_sprint_run_state`, `epic_run_state_path_for`, `filter_transient_markers`, `DEFAULT_SPRINT_RUN_STATE_PATH`).
- Contained epic loop (UNCHANGED, composed per epic unit): `bmad-autopilot/skills/bmad-automation/steps/run-epic.md` + `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/epic_lifecycle.py` (`run_epic_loop`).
- Contained per-story loop (UNCHANGED, composed per unassigned-story unit): `bmad-autopilot/skills/bmad-automation/steps/run.md` + `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/orchestrator_run_entry.py` (`run_story_loop_entry`).
- Per-epic budget resolver (threaded into each contained `run_epic_loop`): `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/retry_budget.py` (`resolve_per_epic_retry_budget_multiplier`).
- Per-sprint budget + escalation-rate config resolvers (Story 16.2): `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/retry_budget.py` (`resolve_per_sprint_retry_budget_override`, `read_per_sprint_retry_budget_from_config_file`, `resolve_sprint_escalation_rate_threshold`, `read_sprint_escalation_rate_threshold_from_config_file`, `DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD`).
- Taxonomy lifetime source: `bmad-autopilot/schemas/marker-taxonomy.yaml` (`lifetime` field) + `loud_fail_harness.reconciler.load_marker_lifetimes`.
- Sprint-run-state schema: `bmad-autopilot/schemas/sprint-run-state.yaml` (schema_version 1.0; states sprint-in-progress / sprint-paused-on-escalation / sprint-paused-on-budget / sprint-complete).
- Architectural commitments: `bmad-autopilot/docs/architecture.md` (ADR-005 three-store / NFR-R8 story-doc-canonical; ADR-009 worktree umbrella; NFR-R1 atomic-write; NFR-R2 transient-not-sticky; NFR-O1 terminal streaming).
- SessionStart recovery (UNCHANGED): `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/session_start_reattach.py` (`evaluate_reattach`).
