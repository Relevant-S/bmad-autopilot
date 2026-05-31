"""Story 15.1 AC-7 — transient-marker strip-witness smoke.

This smoke closes the Story 14.6 *vacuous-witness* gap. Story 14.6's smoke could
only witness "cleared on recovery" as NON-RE-EMISSION from an already-clean
on-disk state (it could not witness active stripping of a *persisted* marker
without an AC-7-forbidden ``session_start_reattach`` change). AC-7 here closes
that gap from the OTHER end — the Story 15.1 epic write-back path:

    construct a run-state whose ``active_markers`` DOES carry
    ``worktree-stale-lock`` (simulating the dangerous persist AC-6 forbids) plus
    at least one DURABLE marker → feed it through the epic write-back →
    assert the persisted / re-read state's ``active_markers`` does NOT contain
    ``worktree-stale-lock`` (ACTIVE exclusion witnessed — not merely
    non-re-emission from a clean state) AND the durable marker survives.

The strip is sourced STRUCTURALLY from the on-disk ``marker-taxonomy.yaml``
``lifetime`` field (these tests inject NO transient-class set — they exercise
the real taxonomy load), so the witness also proves the taxonomy-sourced axis
(AC-6) end-to-end. Resolving AC-6 + AC-7 closes the ``deferred-work.md`` line
845 blocker for BOTH Epic 15 and Epic 18.
"""

from __future__ import annotations

import pathlib

import yaml

from loud_fail_harness.epic_run_state import (
    EpicRunState,
    PerEpicCostPartition,
    PerEpicRetryBudget,
    advance_epic_run_state,
    advance_worktree_run_state,
)
from loud_fail_harness.run_state import (
    CostToDateBySpecialist,
    RunState,
    StoryDocCallbackResult,
)

_TRANSIENT = "worktree-stale-lock"
_TRANSIENT_SUBCLASSED = "worktree-stale-lock: pid-not-alive"
_DURABLE = "retry-budget-exhausted"


def _marker_bearing_epic_state() -> EpicRunState:
    """An epic-run-state that DOES carry the transient ``worktree-stale-lock``
    marker (both bare and sub-classified) AND a durable marker — the dangerous
    persist AC-6 forbids."""
    return EpicRunState(
        schema_version="1.0",
        epic_id="epic-15",
        run_id="run-15-001",
        current_state="epic-in-progress",
        story_ids=("15-1-a",),
        per_story_status={"15-1-a": "in-progress"},
        per_epic_retry_budget=PerEpicRetryBudget(
            multiplier=2, story_count=1, effective_budget=2, consumed=0
        ),
        per_epic_cost_partition=PerEpicCostPartition(
            per_story_cost={"15-1-a": 0.0}, epic_cost_total=0.0
        ),
        active_markers=(_TRANSIENT, _DURABLE, _TRANSIENT_SUBCLASSED),
    )


def _marker_bearing_worktree_state() -> RunState:
    """A per-worktree run-state carrying the same transient + durable markers."""
    return RunState(
        schema_version="1.1",
        story_id="15-1-a",
        run_id="run-15-001",
        current_state="in-progress",
        branch_name="story/15-1-a",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(_TRANSIENT, _DURABLE),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )


def test_epic_write_back_strips_persisted_transient_marker(
    tmp_path: pathlib.Path,
) -> None:
    """AC-7 epic write-back witness — ACTIVE exclusion of a PERSISTED transient
    marker (the input state carries it), durable marker survives, taxonomy-
    sourced (no injected transient set)."""
    path = tmp_path / "epic-run-state.yaml"
    state = _marker_bearing_epic_state()
    # Precondition: the INPUT genuinely carries the transient marker — this is
    # what makes the witness non-vacuous (vs Story 14.6's clean-state input).
    assert _TRANSIENT in state.active_markers

    result = advance_epic_run_state(path, state)

    # In-memory persisted state: transient GONE (both bare + sub-classified),
    # durable SURVIVES.
    assert _TRANSIENT not in result.next_state.active_markers
    assert _TRANSIENT_SUBCLASSED not in result.next_state.active_markers
    assert _DURABLE in result.next_state.active_markers
    assert set(result.filtered_markers) == {_TRANSIENT, _TRANSIENT_SUBCLASSED}

    # Re-read from disk (the "re-fed on next SessionStart" surface): the
    # persisted document carries ONLY the durable marker.
    on_disk = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert _TRANSIENT not in on_disk["active_markers"]
    assert _TRANSIENT_SUBCLASSED not in on_disk["active_markers"]
    assert on_disk["active_markers"] == [_DURABLE]


def test_worktree_write_back_strips_persisted_transient_marker(
    tmp_path: pathlib.Path,
) -> None:
    """AC-6 second witness site — a per-worktree RunState write-back applies the
    SAME filter, so a recovery-recomputed ``worktree-stale-lock`` never persists
    into a per-worktree run-state and goes sticky."""
    path = tmp_path / "run-state.yaml"
    state = _marker_bearing_worktree_state()
    assert _TRANSIENT in state.active_markers

    advance_worktree_run_state(
        path,
        state,
        story_doc_callback=lambda: StoryDocCallbackResult(accepted=True),
    )

    on_disk = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert _TRANSIENT not in on_disk["active_markers"]
    assert on_disk["active_markers"] == [_DURABLE]


def test_durable_marker_not_stripped_in_isolation(tmp_path: pathlib.Path) -> None:
    """Negative control — a state carrying ONLY durable markers round-trips
    unchanged (the filter never touches durable markers; Story 1.4
    marker-permanence rule)."""
    path = tmp_path / "epic-run-state.yaml"
    state = _marker_bearing_epic_state().model_copy(
        update={"active_markers": (_DURABLE,)}
    )
    result = advance_epic_run_state(path, state)
    assert result.next_state.active_markers == (_DURABLE,)
    assert result.filtered_markers == ()
