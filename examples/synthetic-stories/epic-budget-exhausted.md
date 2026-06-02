---
expected_marker: epic-budget-exhausted
scenario: An epic dispatched via `/bmad-automation run --epic` exhausted its cumulative per-epic retry budget (`per_epic_retry_budget_multiplier × story_count`, separate from and additive on top of the per-story `retry_budget`) while undispatched stories remained. The budget was checked AFTER the boundary story reached terminal (sensor-not-advisor — the in-flight story was never interrupted); the epic paused at the next story-completion boundary (`epic-paused-on-budget`) and the loud-fail `epic-budget-exhausted` marker was appended to the epic-run-state `active_markers`.
---
# Synthetic story: epic-budget-exhausted

An Automator epic `epic-15` was dispatched via `/bmad-automation run
--epic epic-15` (Story 15.1 entry). The epic enumerated three
`ready-for-dev` stories and seeded a per-epic retry budget (Story 15.2):
`effective_budget = per_epic_retry_budget_multiplier × story_count`,
with the multiplier resolved from `_bmad/automation/config.yaml`
(default 2, integer ≥ 1) and `consumed` starting at 0.

The epic drove its stories strictly sequentially through the UNCHANGED
per-story loop. After each story reached a terminal state, the number
of per-story retries that story consumed (read from its per-story
`RunState.retry_history`, surfaced on the `StoryLoopOutcome`) was folded
into the cumulative `per_epic_retry_budget.consumed` and persisted via
`advance_epic_run_state` (atomic write; no inline edits — NFR-R1).

At the second story's completion boundary the cumulative `consumed`
reached `effective_budget` while a third, undispatched story remained.
Per Story 15.2 AC-4, the epic transitioned to `epic-paused-on-budget`:

* The budget is checked **AFTER** the boundary story reaches terminal —
  the Orchestrator never interrupts an in-flight story
  (sensor-not-advisor). The story that triggered exhaustion was allowed
  to FINISH.
* The loop STOPPED; the downstream undispatched story did NOT
  auto-advance.
* The durable `epic-budget-exhausted` marker (default `durable`
  lifetime, so it survives the Story 15.1 transient write-back filter)
  was appended to the epic-run-state `active_markers`, carrying
  `{epic_id}`, `{run_id}`, `{consumed}`, and `{effective_budget}` as
  `pointer_context_fields`, and surfaced on the terminal stream.

The marker is **emitted at epic-loop RUNTIME** by
`epic_lifecycle.run_epic_loop` (via `apply_epic_budget` layered on top of
the pure `derive_epic_state`); budget logic never leaks into
`derive_epic_state`. Exhausting the budget exactly on the FINAL story
(no undispatched stories remaining) is `epic-complete`, NOT a pause — the
pause guards future dispatch, not a completed epic.

This marker is **distinct** from `retry-budget-exhausted` (the per-story
budget governing ONE story's loop, Story 5.6) and from
`epic-paused-on-escalation` (a quality issue — a contained story
escalated; escalation takes single-valued `current_state` precedence
while this cost marker still emits additively per AC-6). The two epic
pauses drive different remediation: the human raises
`per_epic_retry_budget_multiplier` or splits the epic for a budget
pause, versus inspecting the escalated story for an escalation pause.
The substrate does NOT auto-resolve — visibility-over-enforcement per
Pattern 5 + sensor-not-advisor.
