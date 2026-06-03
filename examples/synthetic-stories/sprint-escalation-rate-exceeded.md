---
expected_marker: sprint-escalation-rate-exceeded
scenario: A sprint dispatched via `/bmad-automation run --sprint` accumulated an escalation rate (`escalated_stories / stories_completed`) above the configured `sprint_escalation_rate_threshold` (default 0.25). The Orchestrator appended the INFORMATIONAL `sprint-escalation-rate-exceeded` marker to the sprint-run-state `active_markers` and surfaced it on the terminal stream — WITHOUT changing `current_state` and WITHOUT pausing the sprint (sensor-not-advisor; the practitioner decides whether to pause manually).
---
# Synthetic story: sprint-escalation-rate-exceeded

An Automator sprint `sprint-2026q3` was dispatched via
`/bmad-automation run --sprint sprint-2026q3` (Story 16.1 entry). The
sprint loop enumerated its units (epics with `ready-for-dev` stories +
unassigned `ready-for-dev` stories) and drove them strictly
sequentially through the UNCHANGED per-epic loop (`run_epic_loop`) and
per-story loop. Story 16.2 added a per-sprint cumulative retry budget
(cost axis) AND an escalation-rate threshold (quality axis).

As each unit reached a terminal state, the sprint loop folded its story
tally into a running aggregate: an epic unit contributed
`stories_completed = len(dispatched_story_ids)` and `escalated_count = 1`
when it returned `epic-paused-on-escalation` (the epic loop pauses on the
FIRST escalation, so at most one escalated story is observable per epic —
consistent with sensor-not-advisor); an unassigned story unit
contributed `stories_completed = 1` and `escalated_count = 1` when its
terminal status was `escalated`.

After a unit completed, the cumulative escalation rate
`escalated_stories / stories_completed` exceeded the configured
`sprint_escalation_rate_threshold` (default 0.25, calibrated from the
PRD's 15–25% retry-budget-exhaustion target band). Per Story 16.2 AC-5:

* The durable `sprint-escalation-rate-exceeded` marker (default
  `durable` lifetime, so it survives the Story 16.1 transient
  write-back filter) was appended to the sprint-run-state
  `active_markers` exactly once (idempotent — never duplicated on
  subsequent boundaries), carrying `{sprint_id}`, `{run_id}`,
  `{escalated_stories}`, `{stories_completed}`, and `{threshold}` as
  `pointer_context_fields`, and surfaced on the terminal stream.
* The marker is **INFORMATIONAL, not blocking** (sensor-not-advisor):
  emitting it does NOT change `current_state`, and the sprint
  CONTINUED dispatching its remaining units. The practitioner decides
  whether to pause the sprint manually.

The marker is **emitted at sprint-loop RUNTIME** by
`sprint_lifecycle.run_sprint_loop`; the pure `derive_sprint_state`
stays a function of the two status maps only (the rate signal never
leaks into it).

This marker is **distinct** from `sprint-paused-on-budget` — the
cost-axis surface, a cumulative per-sprint retry-budget pause that DOES
change `current_state` (different remediation: the human raises
`per_sprint_retry_budget` or splits the sprint). It is also distinct
from `epic-paused-on-escalation` one scope down (a single contained
epic's escalation). The two sprint surfaces compose: a sprint may carry
the `sprint-escalation-rate-exceeded` marker additively alongside ANY
`current_state`, including a clean `sprint-complete`. The substrate does
NOT auto-resolve — visibility-over-enforcement per Pattern 5 +
sensor-not-advisor.
