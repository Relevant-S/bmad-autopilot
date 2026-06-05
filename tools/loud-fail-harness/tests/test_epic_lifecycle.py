"""Contract-coverage matrix for the epic-lifecycle module (story 15.1).

This docstring IS the contract-coverage checklist (review-enforced, parallel to
``test_epic_run_state.py`` / ``test_orchestrator_run_entry.py``).

Enumeration (AC-1):
    [x] ready-for-dev stories returned in numeric key-ascending order      → test_enumerate_orders_by_numeric_ordinal
    [x] only ready-for-dev entries are included                            → test_enumerate_filters_non_ready_for_dev
    [x] epic / retrospective keys are excluded                            → test_enumerate_excludes_epic_and_retro_keys
    [x] a different epic's stories are excluded                           → test_enumerate_excludes_other_epics
    [x] non epic-<N> id raises EpicStoryEnumerationError                  → test_enumerate_rejects_malformed_epic_id
    [x] missing sprint-status raises                                      → test_enumerate_missing_sprint_status_raises
    [x] malformed development_status raises                               → test_enumerate_malformed_development_status_raises

Init (AC-1):
    [x] init seeds epic-in-progress + ready-for-dev per-story seed        → test_init_seeds_in_progress
    [x] init populates the retry-budget STRUCTURE (enforcement is 15.2)   → test_init_populates_retry_budget_structure
    [x] init zeroes the cost partition                                    → test_init_zeroes_cost_partition

State machine (AC-3, AC-4):
    [x] all-terminal → epic-complete                                      → test_derive_epic_state_complete
    [x] any escalated → epic-paused-on-escalation                         → test_derive_epic_state_paused_on_escalation
    [x] mixed → epic-in-progress                                          → test_derive_epic_state_in_progress
    [x] epic-paused-on-budget is NOT reachable here (Story 15.2)          → test_derive_epic_state_never_budget
    [x] fold updates per-story status + recomputes current_state          → test_fold_story_terminal_updates_and_recomputes
    [x] fold does not mutate the input (frozen discipline)                → test_fold_story_terminal_does_not_mutate_input
    [x] fold rejects an unknown story_id                                  → test_fold_story_terminal_rejects_unknown_story
    [x] fold rejects an invalid per-story status                         → test_fold_story_terminal_rejects_invalid_status

Sequential loop (AC-2, AC-3, AC-4, AC-5):
    [x] clean run dispatches all stories → epic-complete + persists       → test_run_epic_loop_clean_run_completes
    [x] progress_sink fires once per completion boundary                  → test_run_epic_loop_streams_progress_per_story
    [x] escalation pauses + downstream stories do NOT auto-advance        → test_run_epic_loop_pauses_on_escalation
    [x] empty epic raises EpicStoryEnumerationError                       → test_run_epic_loop_empty_epic_raises
    [x] loop resolves the taxonomy default without error                  → test_run_epic_loop_default_taxonomy_path

Loud-fail + bit-identity (AC-2, AC-8):
    [x] EpicStoryEnumerationError carries marker_class None               → test_enumeration_error_marker_class_is_none
    [x] epic_lifecycle does NOT import orchestrator_run_entry (additive)  → test_epic_lifecycle_does_not_import_orchestrator_run_entry
"""

from __future__ import annotations

import pathlib

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness import epic_lifecycle as epic_lifecycle_module
from loud_fail_harness.epic_lifecycle import (
    DEFAULT_PER_EPIC_RETRY_MULTIPLIER,
    EPIC_BUDGET_EXHAUSTED_MARKER,
    EpicStoryEnumerationError,
    StoryLoopOutcome,
    StoryLoopRunner,
    apply_epic_budget,
    derive_epic_state,
    enumerate_epic_stories,
    fold_story_cost,
    fold_story_terminal,
    init_epic_run_state,
    run_epic_loop,
)
from loud_fail_harness.epic_run_state import (
    EpicRunState,
    PerEpicCostPartition,
    ResumeBudgetReconstructionConflict,
)

_NO_TRANSIENT: frozenset[str] = frozenset()


def _outcome(terminal_status: str, retries_consumed: int = 0) -> StoryLoopOutcome:
    """Build a :class:`StoryLoopOutcome` stub return (Story 15.2 — the runner
    Protocol now carries the per-story retry count alongside the terminal
    status). Default ``retries_consumed=0`` keeps the Story 15.1 parity tests
    budget-neutral."""
    return StoryLoopOutcome(
        terminal_status=terminal_status,  # type: ignore[arg-type]
        retries_consumed=retries_consumed,
    )


def _write_sprint_status(tmp_path: pathlib.Path, development_status: dict[str, str]) -> pathlib.Path:
    path = tmp_path / "sprint-status.yaml"
    path.write_text(
        yaml.safe_dump({"development_status": development_status}, sort_keys=False),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Enumeration (AC-1)
# ---------------------------------------------------------------------------


def test_enumerate_orders_by_numeric_ordinal(tmp_path: pathlib.Path) -> None:
    path = _write_sprint_status(
        tmp_path,
        {
            "15-2-b": "ready-for-dev",
            "15-10-j": "ready-for-dev",
            "15-1-a": "ready-for-dev",
        },
    )
    assert enumerate_epic_stories("epic-15", sprint_status_path=path) == (
        "15-1-a",
        "15-2-b",
        "15-10-j",
    )


def test_enumerate_filters_non_ready_for_dev(tmp_path: pathlib.Path) -> None:
    path = _write_sprint_status(
        tmp_path,
        {
            "15-1-a": "done",
            "15-2-b": "ready-for-dev",
            "15-3-c": "backlog",
            "15-4-d": "ready-for-dev",
        },
    )
    assert enumerate_epic_stories("epic-15", sprint_status_path=path) == (
        "15-2-b",
        "15-4-d",
    )


def test_enumerate_excludes_epic_and_retro_keys(tmp_path: pathlib.Path) -> None:
    path = _write_sprint_status(
        tmp_path,
        {
            "epic-15": "in-progress",
            "epic-15-retrospective": "optional",
            "15-1-a": "ready-for-dev",
        },
    )
    assert enumerate_epic_stories("epic-15", sprint_status_path=path) == ("15-1-a",)


def test_enumerate_excludes_other_epics(tmp_path: pathlib.Path) -> None:
    path = _write_sprint_status(
        tmp_path,
        {
            "15-1-a": "ready-for-dev",
            "1-1-x": "ready-for-dev",
            "16-1-y": "ready-for-dev",
            "150-1-z": "ready-for-dev",
        },
    )
    assert enumerate_epic_stories("epic-15", sprint_status_path=path) == ("15-1-a",)


def test_enumerate_rejects_malformed_epic_id(tmp_path: pathlib.Path) -> None:
    path = _write_sprint_status(tmp_path, {"15-1-a": "ready-for-dev"})
    with pytest.raises(EpicStoryEnumerationError, match="epic-<N>"):
        enumerate_epic_stories("15", sprint_status_path=path)


def test_enumerate_missing_sprint_status_raises(tmp_path: pathlib.Path) -> None:
    with pytest.raises(EpicStoryEnumerationError, match="not found"):
        enumerate_epic_stories(
            "epic-15", sprint_status_path=tmp_path / "nope.yaml"
        )


def test_enumerate_malformed_development_status_raises(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "sprint-status.yaml"
    path.write_text("development_status: not-a-mapping\n", encoding="utf-8")
    with pytest.raises(EpicStoryEnumerationError, match="development_status"):
        enumerate_epic_stories("epic-15", sprint_status_path=path)


# ---------------------------------------------------------------------------
# Init (AC-1)
# ---------------------------------------------------------------------------


def test_init_seeds_in_progress() -> None:
    state = init_epic_run_state("epic-15", "run-1", ("15-1-a", "15-2-b"))
    assert state.current_state == "epic-in-progress"
    assert state.story_ids == ("15-1-a", "15-2-b")
    assert state.per_story_status == {
        "15-1-a": "ready-for-dev",
        "15-2-b": "ready-for-dev",
    }
    assert state.active_markers == ()


def test_init_populates_retry_budget_structure() -> None:
    state = init_epic_run_state("epic-15", "run-1", ("15-1-a", "15-2-b", "15-3-c"))
    budget = state.per_epic_retry_budget
    assert budget.multiplier == 2
    assert budget.story_count == 3
    assert budget.effective_budget == 6
    assert budget.consumed == 0


def test_init_zeroes_cost_partition() -> None:
    state = init_epic_run_state("epic-15", "run-1", ("15-1-a", "15-2-b"))
    assert state.per_epic_cost_partition.epic_cost_total == 0.0
    assert dict(state.per_epic_cost_partition.per_story_cost) == {
        "15-1-a": 0.0,
        "15-2-b": 0.0,
    }


# ---------------------------------------------------------------------------
# State machine (AC-3, AC-4)
# ---------------------------------------------------------------------------


def test_derive_epic_state_complete() -> None:
    assert derive_epic_state({"a": "merge-ready", "b": "done"}) == "epic-complete"


def test_derive_epic_state_paused_on_escalation() -> None:
    assert (
        derive_epic_state({"a": "merge-ready", "b": "escalated"})
        == "epic-paused-on-escalation"
    )


def test_derive_epic_state_in_progress() -> None:
    assert (
        derive_epic_state({"a": "merge-ready", "b": "in-progress"})
        == "epic-in-progress"
    )


def test_derive_epic_state_never_budget() -> None:
    """Story 15.1 scope boundary: budget enforcement (and therefore
    ``epic-paused-on-budget``) is Story 15.2. No status combination reaches it
    here."""
    for statuses in (
        {"a": "merge-ready", "b": "done"},
        {"a": "escalated"},
        {"a": "in-progress"},
        {},
    ):
        assert derive_epic_state(statuses) != "epic-paused-on-budget"


def test_fold_story_terminal_updates_and_recomputes() -> None:
    state = init_epic_run_state("epic-15", "run-1", ("15-1-a", "15-2-b"))
    folded = fold_story_terminal(state, "15-1-a", "merge-ready")
    assert folded.per_story_status["15-1-a"] == "merge-ready"
    assert folded.per_story_status["15-2-b"] == "ready-for-dev"
    assert folded.current_state == "epic-in-progress"
    both = fold_story_terminal(folded, "15-2-b", "done")
    assert both.current_state == "epic-complete"


def test_fold_story_terminal_does_not_mutate_input() -> None:
    state = init_epic_run_state("epic-15", "run-1", ("15-1-a",))
    fold_story_terminal(state, "15-1-a", "escalated")
    assert state.per_story_status["15-1-a"] == "ready-for-dev"
    assert state.current_state == "epic-in-progress"


def test_fold_story_terminal_rejects_unknown_story() -> None:
    state = init_epic_run_state("epic-15", "run-1", ("15-1-a",))
    with pytest.raises(ValueError, match="not a contained story"):
        fold_story_terminal(state, "15-9-z", "done")


def test_fold_story_terminal_rejects_invalid_status() -> None:
    state = init_epic_run_state("epic-15", "run-1", ("15-1-a",))
    with pytest.raises(ValueError, match="not a valid"):
        fold_story_terminal(state, "15-1-a", "totally-bogus")


# ---------------------------------------------------------------------------
# Sequential loop (AC-2, AC-3, AC-4, AC-5)
# ---------------------------------------------------------------------------


def test_run_epic_loop_clean_run_completes(tmp_path: pathlib.Path) -> None:
    sprint = _write_sprint_status(
        tmp_path,
        {"15-1-a": "ready-for-dev", "15-2-b": "ready-for-dev"},
    )
    erp = tmp_path / "epic-run-state.yaml"
    dispatched: list[str] = []

    def runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        dispatched.append(story_id)
        return _outcome("merge-ready")

    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=runner,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert dispatched == ["15-1-a", "15-2-b"]
    assert result.dispatched_story_ids == ("15-1-a", "15-2-b")
    assert result.final_state.current_state == "epic-complete"
    assert result.paused_on_story_id is None
    on_disk = yaml.safe_load(erp.read_text(encoding="utf-8"))
    assert on_disk["current_state"] == "epic-complete"
    assert on_disk["per_story_status"] == {
        "15-1-a": "merge-ready",
        "15-2-b": "merge-ready",
    }


def test_run_epic_loop_streams_progress_per_story(tmp_path: pathlib.Path) -> None:
    sprint = _write_sprint_status(
        tmp_path,
        {"15-1-a": "ready-for-dev", "15-2-b": "ready-for-dev"},
    )
    lines: list[str] = []

    def runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        return _outcome("done")

    run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=tmp_path / "e.yaml",
        story_loop_runner=runner,
        progress_sink=lines.append,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert len(lines) == 2
    assert "story 1 of 2" in lines[0]
    assert "15-1-a" in lines[0]
    assert "story 2 of 2" in lines[1]


def test_run_epic_loop_pauses_on_escalation(tmp_path: pathlib.Path) -> None:
    sprint = _write_sprint_status(
        tmp_path,
        {
            "15-1-a": "ready-for-dev",
            "15-2-b": "ready-for-dev",
            "15-3-c": "ready-for-dev",
        },
    )
    erp = tmp_path / "epic-run-state.yaml"
    dispatched: list[str] = []
    outcomes = iter(["merge-ready", "escalated", "merge-ready"])

    def runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        dispatched.append(story_id)
        return _outcome(next(outcomes))

    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=runner,
        transient_marker_classes=_NO_TRANSIENT,
    )
    # 15-3-c did NOT auto-advance (sensor-not-advisor; AC-4).
    assert dispatched == ["15-1-a", "15-2-b"]
    assert result.dispatched_story_ids == ("15-1-a", "15-2-b")
    assert result.paused_on_story_id == "15-2-b"
    assert result.final_state.current_state == "epic-paused-on-escalation"
    on_disk = yaml.safe_load(erp.read_text(encoding="utf-8"))
    assert on_disk["current_state"] == "epic-paused-on-escalation"
    # The downstream story stays at its seeded state on disk.
    assert on_disk["per_story_status"]["15-3-c"] == "ready-for-dev"


def test_run_epic_loop_empty_epic_raises(tmp_path: pathlib.Path) -> None:
    sprint = _write_sprint_status(tmp_path, {"15-1-a": "done"})

    def runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        raise AssertionError("runner must not be called for an empty epic")

    with pytest.raises(EpicStoryEnumerationError, match="no ready-for-dev"):
        run_epic_loop(
            "epic-15",
            run_id="run-1",
            sprint_status_path=sprint,
            epic_run_state_path=tmp_path / "e.yaml",
            story_loop_runner=runner,
            transient_marker_classes=_NO_TRANSIENT,
        )


def test_run_epic_loop_default_taxonomy_path(tmp_path: pathlib.Path) -> None:
    """No injected transient set → the loop resolves the on-disk taxonomy
    (find_repo_root at call time) without error. Smoke for the default path."""
    sprint = _write_sprint_status(tmp_path, {"15-1-a": "ready-for-dev"})

    def runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        return _outcome("merge-ready")

    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=tmp_path / "e.yaml",
        story_loop_runner=runner,
    )
    assert result.final_state.current_state == "epic-complete"


# ---------------------------------------------------------------------------
# Loud-fail + bit-identity (AC-2, AC-8)
# ---------------------------------------------------------------------------


def test_enumeration_error_marker_class_is_none() -> None:
    assert EpicStoryEnumerationError.marker_class is None
    err = EpicStoryEnumerationError(epic_id="epic-15", reason="x")
    assert err.epic_id == "epic-15"
    assert err.reason == "x"


def test_epic_lifecycle_does_not_import_orchestrator_run_entry() -> None:
    """AC-2 bit-identity: the epic flag is purely additive — the epic-lifecycle
    module composes the per-story loop through the injected ``StoryLoopRunner``
    Protocol, NOT by importing/wrapping ``orchestrator_run_entry``. Structural
    witness that the per-story entry path is untouched.
    """
    source = pathlib.Path(epic_lifecycle_module.__file__).read_text(encoding="utf-8")
    # Allow the substring inside prose/docstrings? No — assert no import line.
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
        and "orchestrator_run_entry" in line
    ]
    assert import_lines == []


def test_final_state_is_epic_run_state(tmp_path: pathlib.Path) -> None:
    sprint = _write_sprint_status(tmp_path, {"15-1-a": "ready-for-dev"})

    def runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        return _outcome("merge-ready")

    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=tmp_path / "e.yaml",
        story_loop_runner=runner,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert isinstance(result.final_state, EpicRunState)


# ---------------------------------------------------------------------------
# Per-epic budget: StoryLoopOutcome shape (AC-3)
# ---------------------------------------------------------------------------


def test_story_loop_outcome_rejects_negative_retries() -> None:
    with pytest.raises(ValidationError):
        StoryLoopOutcome(terminal_status="merge-ready", retries_consumed=-1)


def test_story_loop_outcome_is_frozen() -> None:
    outcome = StoryLoopOutcome(terminal_status="done", retries_consumed=0)
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        outcome.retries_consumed = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Per-epic cost partition: StoryLoopOutcome.cost shape + fold_story_cost (AC-3)
# ---------------------------------------------------------------------------


def test_story_loop_outcome_cost_defaults_to_zero() -> None:
    """Additive 0.0 default keeps the 15.1/15.2 stubs valid (backward-compat)."""
    outcome = StoryLoopOutcome(terminal_status="merge-ready", retries_consumed=0)
    assert outcome.cost == 0.0


def test_story_loop_outcome_cost_is_frozen() -> None:
    outcome = StoryLoopOutcome(
        terminal_status="done", retries_consumed=0, cost=1.5
    )
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        outcome.cost = 2.0  # type: ignore[misc]


def test_story_loop_outcome_rejects_negative_cost() -> None:
    with pytest.raises(ValidationError):
        StoryLoopOutcome(
            terminal_status="merge-ready", retries_consumed=0, cost=-0.01
        )


def _seed_partition(per_story_cost: dict[str, float]) -> PerEpicCostPartition:
    return PerEpicCostPartition(
        per_story_cost=dict(per_story_cost),
        epic_cost_total=sum(per_story_cost.values()),
    )


def test_fold_story_cost_sets_per_story_and_recomputes_total() -> None:
    partition = _seed_partition({"15-1-a": 0.0, "15-2-b": 0.0})
    folded = fold_story_cost(partition, "15-1-a", 1.25)
    assert folded.per_story_cost["15-1-a"] == 1.25
    assert folded.per_story_cost["15-2-b"] == 0.0
    assert folded.epic_cost_total == 1.25


def test_fold_story_cost_is_cumulative_per_story() -> None:
    partition = _seed_partition({"15-1-a": 1.0, "15-2-b": 0.5})
    folded = fold_story_cost(partition, "15-1-a", 0.75)
    assert folded.per_story_cost["15-1-a"] == 1.75
    assert folded.epic_cost_total == 2.25


def test_fold_story_cost_zero_contribution_keeps_total() -> None:
    partition = _seed_partition({"15-1-a": 2.0, "15-2-b": 0.0})
    folded = fold_story_cost(partition, "15-2-b", 0.0)
    assert folded.per_story_cost["15-2-b"] == 0.0
    assert folded.epic_cost_total == 2.0


def test_fold_story_cost_empty_partition_total() -> None:
    partition = _seed_partition({})
    folded = fold_story_cost(partition, "15-1-a", 3.5)
    assert dict(folded.per_story_cost) == {"15-1-a": 3.5}
    assert folded.epic_cost_total == 3.5


def test_fold_story_cost_does_not_mutate_input() -> None:
    partition = _seed_partition({"15-1-a": 0.0})
    fold_story_cost(partition, "15-1-a", 1.0)
    assert partition.per_story_cost["15-1-a"] == 0.0
    assert partition.epic_cost_total == 0.0


def test_fold_story_cost_rejects_negative() -> None:
    partition = _seed_partition({"15-1-a": 0.0})
    with pytest.raises(ValueError, match="non-negative"):
        fold_story_cost(partition, "15-1-a", -1.0)


def test_run_epic_loop_accumulates_cost_partition(tmp_path: pathlib.Path) -> None:
    """Integration: per-story costs surfaced via StoryLoopOutcome.cost fold into
    per_epic_cost_partition and persist on disk; the cost fold composes with the
    existing retry/terminal folds (AC-3)."""
    sprint = _write_sprint_status(
        tmp_path,
        {"15-1-a": "ready-for-dev", "15-2-b": "ready-for-dev"},
    )
    erp = tmp_path / "epic-run-state.yaml"
    costs = {"15-1-a": 1.25, "15-2-b": 0.75}
    retries = {"15-1-a": 1, "15-2-b": 0}

    def runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        return StoryLoopOutcome(
            terminal_status="merge-ready",  # type: ignore[arg-type]
            retries_consumed=retries[story_id],
            cost=costs[story_id],
        )

    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=runner,
        transient_marker_classes=_NO_TRANSIENT,
    )
    partition = result.final_state.per_epic_cost_partition
    assert partition.per_story_cost["15-1-a"] == 1.25
    assert partition.per_story_cost["15-2-b"] == 0.75
    assert partition.epic_cost_total == 2.0
    # The cost fold rode the existing advance — persisted on disk (AC-3).
    on_disk = yaml.safe_load(erp.read_text(encoding="utf-8"))
    assert on_disk["per_epic_cost_partition"]["epic_cost_total"] == 2.0
    assert on_disk["per_epic_cost_partition"]["per_story_cost"] == {
        "15-1-a": 1.25,
        "15-2-b": 0.75,
    }
    # Cost fold composes with the retry fold (15-1-a consumed 1 retry).
    assert result.final_state.per_epic_retry_budget.consumed == 1


def test_run_epic_loop_default_cost_zero_backward_compat(
    tmp_path: pathlib.Path,
) -> None:
    """A runner that returns the 15.2-shaped outcome (no cost) keeps the
    partition zeroed — additive default holds end-to-end."""
    sprint = _write_sprint_status(tmp_path, {"15-1-a": "ready-for-dev"})
    erp = tmp_path / "epic-run-state.yaml"

    def runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        return _outcome("merge-ready")

    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=runner,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert result.final_state.per_epic_cost_partition.epic_cost_total == 0.0


# ---------------------------------------------------------------------------
# Per-epic budget: apply_epic_budget truth table (AC-4, AC-6)
# ---------------------------------------------------------------------------


def test_apply_epic_budget_under_budget_continues() -> None:
    # in-progress, consumed < effective_budget → unchanged, no marker.
    assert apply_epic_budget(
        "epic-in-progress", 3, 6, has_undispatched=True
    ) == ("epic-in-progress", False)


def test_apply_epic_budget_exhausted_with_undispatched_pauses_and_emits() -> None:
    assert apply_epic_budget(
        "epic-in-progress", 6, 6, has_undispatched=True
    ) == ("epic-paused-on-budget", True)


def test_apply_epic_budget_exhausted_on_final_story_is_complete_no_marker() -> None:
    # The last story completed within total budget (no undispatched left) →
    # epic-complete, NOT a pause; the pause guards FUTURE dispatch (AC-4).
    assert apply_epic_budget(
        "epic-complete", 6, 6, has_undispatched=False
    ) == ("epic-complete", False)


def test_apply_epic_budget_escalation_precedence_marker_additive() -> None:
    # Escalation wins the single-valued current_state; the budget marker still
    # emits additively when the budget would have paused future dispatch (AC-6).
    assert apply_epic_budget(
        "epic-paused-on-escalation", 6, 6, has_undispatched=True
    ) == ("epic-paused-on-escalation", True)


def test_apply_epic_budget_escalation_on_final_story_no_marker() -> None:
    # Escalated boundary story is the last one — no undispatched dispatch to
    # guard, so the budget marker does NOT emit (escalation still pauses).
    assert apply_epic_budget(
        "epic-paused-on-escalation", 6, 6, has_undispatched=False
    ) == ("epic-paused-on-escalation", False)


def test_apply_epic_budget_zero_effective_budget_is_total() -> None:
    # Degenerate effective_budget == 0 (a zero-story epic never enumerates, but
    # the pure helper must be total) → never reported as exhausted.
    assert apply_epic_budget(
        "epic-in-progress", 0, 0, has_undispatched=True
    ) == ("epic-in-progress", False)


# ---------------------------------------------------------------------------
# Per-epic budget: multiplier threading + run_epic_loop enforcement
# (AC-2, AC-3, AC-4, AC-5, AC-6)
# ---------------------------------------------------------------------------


def _retry_runner(
    retries_by_story: dict[str, int],
    *,
    status_by_story: dict[str, str] | None = None,
    dispatched: list[str] | None = None,
) -> StoryLoopRunner:
    statuses = status_by_story or {}

    def runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        if dispatched is not None:
            dispatched.append(story_id)
        return _outcome(
            statuses.get(story_id, "merge-ready"),
            retries_by_story.get(story_id, 0),
        )

    return runner


def test_run_epic_loop_threads_resolved_multiplier(tmp_path: pathlib.Path) -> None:
    """AC-2: the resolved multiplier is threaded into init so
    ``effective_budget = multiplier × story_count``."""
    sprint = _write_sprint_status(
        tmp_path,
        {"15-1-a": "ready-for-dev", "15-2-b": "ready-for-dev"},
    )
    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=tmp_path / "e.yaml",
        story_loop_runner=_retry_runner({}),
        multiplier=5,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert result.final_state.per_epic_retry_budget.effective_budget == 10
    assert result.final_state.per_epic_retry_budget.multiplier == 5


def test_run_epic_loop_pauses_on_budget_at_boundary(tmp_path: pathlib.Path) -> None:
    """AC-3 / AC-4 / AC-5: cumulative retries exhaust the per-epic budget →
    pause at the NEXT completion boundary, in-flight story finishes, marker
    persisted, downstream prefix stops, consumed accumulated."""
    sprint = _write_sprint_status(
        tmp_path,
        {
            "15-1-a": "ready-for-dev",
            "15-2-b": "ready-for-dev",
            "15-3-c": "ready-for-dev",
        },
    )
    erp = tmp_path / "epic-run-state.yaml"
    dispatched: list[str] = []
    # multiplier=1, story_count=3 → effective_budget=3. story1=2 (cumulative 2,
    # continue), story2=2 (cumulative 4 >= 3, undispatched remain → pause).
    runner = _retry_runner(
        {"15-1-a": 2, "15-2-b": 2, "15-3-c": 99},
        dispatched=dispatched,
    )
    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=runner,
        multiplier=1,
        transient_marker_classes=_NO_TRANSIENT,
    )
    # 15-3-c did NOT dispatch (sensor-not-advisor; downstream prefix stops).
    assert dispatched == ["15-1-a", "15-2-b"]
    assert result.dispatched_story_ids == ("15-1-a", "15-2-b")
    assert result.paused_on_story_id == "15-2-b"
    assert result.final_state.current_state == "epic-paused-on-budget"
    # The in-flight boundary story FINISHED (not interrupted) — terminal.
    assert result.final_state.per_story_status["15-2-b"] == "merge-ready"
    assert EPIC_BUDGET_EXHAUSTED_MARKER in result.final_state.active_markers
    assert result.final_state.per_epic_retry_budget.consumed == 4
    on_disk = yaml.safe_load(erp.read_text(encoding="utf-8"))
    assert on_disk["current_state"] == "epic-paused-on-budget"
    assert EPIC_BUDGET_EXHAUSTED_MARKER in on_disk["active_markers"]
    assert on_disk["per_epic_retry_budget"]["consumed"] == 4
    assert on_disk["per_story_status"]["15-3-c"] == "ready-for-dev"


def test_run_epic_loop_exhaust_on_final_story_completes(
    tmp_path: pathlib.Path,
) -> None:
    """AC-4: exhausting the budget exactly on the final story is NOT a pause —
    the epic completes and the marker does NOT emit."""
    sprint = _write_sprint_status(
        tmp_path,
        {"15-1-a": "ready-for-dev", "15-2-b": "ready-for-dev"},
    )
    erp = tmp_path / "epic-run-state.yaml"
    # multiplier=1, story_count=2 → effective_budget=2. 1 + 1 == 2 on the final
    # story, no undispatched remain.
    runner = _retry_runner({"15-1-a": 1, "15-2-b": 1})
    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=runner,
        multiplier=1,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert result.final_state.current_state == "epic-complete"
    assert result.paused_on_story_id is None
    assert EPIC_BUDGET_EXHAUSTED_MARKER not in result.final_state.active_markers
    assert result.final_state.per_epic_retry_budget.consumed == 2


def test_run_epic_loop_escalation_precedence_marker_additive(
    tmp_path: pathlib.Path,
) -> None:
    """AC-6: a boundary story that BOTH escalated AND exhausted the budget →
    current_state is epic-paused-on-escalation, marker still emitted."""
    sprint = _write_sprint_status(
        tmp_path,
        {
            "15-1-a": "ready-for-dev",
            "15-2-b": "ready-for-dev",
            "15-3-c": "ready-for-dev",
        },
    )
    erp = tmp_path / "epic-run-state.yaml"
    # multiplier=1, story_count=3 → effective_budget=3. story1 escalates AND
    # consumes 3 (cumulative 3 >= 3, undispatched remain).
    runner = _retry_runner(
        {"15-1-a": 3},
        status_by_story={"15-1-a": "escalated"},
    )
    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=runner,
        multiplier=1,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert result.final_state.current_state == "epic-paused-on-escalation"
    assert result.paused_on_story_id == "15-1-a"
    assert EPIC_BUDGET_EXHAUSTED_MARKER in result.final_state.active_markers


def test_run_epic_loop_budget_marker_survives_transient_filter(
    tmp_path: pathlib.Path,
) -> None:
    """AC-5: the durable epic-budget-exhausted marker is NEVER stripped by the
    transient write-back filter, even when a transient class IS being filtered."""
    sprint = _write_sprint_status(
        tmp_path,
        {"15-1-a": "ready-for-dev", "15-2-b": "ready-for-dev"},
    )
    erp = tmp_path / "epic-run-state.yaml"
    runner = _retry_runner({"15-1-a": 2})
    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=runner,
        multiplier=1,
        transient_marker_classes=frozenset({"worktree-stale-lock"}),
    )
    assert result.final_state.current_state == "epic-paused-on-budget"
    assert EPIC_BUDGET_EXHAUSTED_MARKER in result.final_state.active_markers


def test_run_epic_loop_zero_retries_completes_unchanged(
    tmp_path: pathlib.Path,
) -> None:
    """AC-7 regression: an epic that consumes zero retries reaches epic-complete
    exactly as in Story 15.1 (no behaviour change when the budget is never
    approached); consumed stays 0; no marker."""
    sprint = _write_sprint_status(
        tmp_path,
        {"15-1-a": "ready-for-dev", "15-2-b": "ready-for-dev"},
    )
    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=tmp_path / "e.yaml",
        story_loop_runner=_retry_runner({}),
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert result.final_state.current_state == "epic-complete"
    assert result.final_state.per_epic_retry_budget.consumed == 0
    assert result.final_state.active_markers == ()
    # Default multiplier is the single-sourced DEFAULT_PER_EPIC_RETRY_MULTIPLIER.
    assert (
        result.final_state.per_epic_retry_budget.multiplier
        == DEFAULT_PER_EPIC_RETRY_MULTIPLIER
    )


# ---------------------------------------------------------------------------
# Resume budget reconstruction (Story 16.5 AC-5/7/8/9/10)
# ---------------------------------------------------------------------------


def test_run_epic_loop_resume_exhausted_dispatches_zero(
    tmp_path: pathlib.Path,
) -> None:
    """AC-5/AC-10 + review admission invariant: a re-invocation against a
    persisted cache (same run_id) carries the cumulative ``consumed`` forward
    (NOT reset to 0), and because the reconstructed budget is already exhausted
    at entry the pre-dispatch admission gate pauses WITHOUT dispatching any
    further story — the guard holds strictly across the resume boundary (a
    runaway sequence cannot buy one extra story per re-invocation)."""
    sprint = _write_sprint_status(
        tmp_path,
        {
            "15-1-a": "ready-for-dev",
            "15-2-b": "ready-for-dev",
            "15-3-c": "ready-for-dev",
        },
    )
    erp = tmp_path / "epic-run-state.yaml"

    # First run: 15-1-a alone consumes the full epic budget (2 × 3 = 6) →
    # epic-paused-on-budget after the first story, 15-2-b / 15-3-c undispatched.
    first = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=_retry_runner({"15-1-a": 6}),
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert first.final_state.current_state == "epic-paused-on-budget"
    assert first.final_state.per_epic_retry_budget.consumed == 6
    assert first.dispatched_story_ids == ("15-1-a",)
    assert EPIC_BUDGET_EXHAUSTED_MARKER in first.final_state.active_markers

    # Re-invoke against the persisted cache with the SAME run_id. The budget was
    # already exhausted at entry, so the admission gate pauses BEFORE dispatching
    # — the runner must never be called (zero re-dispatch).
    def _must_not_dispatch(
        *, story_id: str, index: int, total: int
    ) -> StoryLoopOutcome:
        raise AssertionError(
            f"no story may be dispatched on an exhausted resume; got {story_id!r}"
        )

    resumed = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=_must_not_dispatch,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert resumed.final_state.per_epic_retry_budget.consumed == 6
    assert resumed.final_state.per_epic_retry_budget.effective_budget == 6
    assert resumed.final_state.current_state == "epic-paused-on-budget"
    assert resumed.dispatched_story_ids == ()
    assert resumed.paused_on_story_id is None
    # The pre-pause durable marker survived the resume boundary (AC-7).
    assert EPIC_BUDGET_EXHAUSTED_MARKER in resumed.final_state.active_markers


def test_run_epic_loop_resume_under_budget_still_dispatches(
    tmp_path: pathlib.Path,
) -> None:
    """Admission gate is a no-op when the reconstructed budget is NOT exhausted:
    a resumed run whose carried ``consumed`` is below ``effective_budget`` keeps
    dispatching (the gate must not over-pause an under-budget resume)."""
    sprint = _write_sprint_status(
        tmp_path,
        {"15-1-a": "ready-for-dev", "15-2-b": "ready-for-dev"},
    )
    erp = tmp_path / "epic-run-state.yaml"

    # First run completes cleanly consuming 1 of 4 (2 × 2) → cache persisted.
    first = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=_retry_runner({"15-1-a": 1}),
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert first.final_state.current_state == "epic-complete"
    assert first.final_state.per_epic_retry_budget.consumed == 1

    # Resume (same run_id): consumed=1 < effective=4, so the admission gate is a
    # no-op and the loop dispatches the still-ready stories.
    dispatched: list[str] = []
    resumed = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=_retry_runner({}, dispatched=dispatched),
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert dispatched == ["15-1-a", "15-2-b"]
    assert resumed.final_state.current_state == "epic-complete"
    # consumed carried forward (1), no new retries this run.
    assert resumed.final_state.per_epic_retry_budget.consumed == 1


def test_run_epic_loop_resume_run_id_mismatch_raises(
    tmp_path: pathlib.Path,
) -> None:
    """AC-8: a persisted cache whose run_id differs from the loop's run_id is a
    stale cache from a different run at the same per-unit address — the loop
    fails loudly with ``ResumeBudgetReconstructionConflict`` (recovery-state-
    conflict), naming both run_ids and the cache path."""
    sprint = _write_sprint_status(
        tmp_path,
        {"15-1-a": "ready-for-dev", "15-2-b": "ready-for-dev"},
    )
    erp = tmp_path / "epic-run-state.yaml"
    run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=_retry_runner({}),
        transient_marker_classes=_NO_TRANSIENT,
    )
    with pytest.raises(ResumeBudgetReconstructionConflict) as excinfo:
        run_epic_loop(
            "epic-15",
            run_id="run-2",
            sprint_status_path=sprint,
            epic_run_state_path=erp,
            story_loop_runner=_retry_runner({}),
            transient_marker_classes=_NO_TRANSIENT,
        )
    err = excinfo.value
    assert err.marker_class == "recovery-state-conflict"
    assert err.cache_run_id == "run-1"
    assert err.loop_run_id == "run-2"
    assert str(erp) in str(err)


def test_run_epic_loop_first_invocation_no_reconstruction(
    tmp_path: pathlib.Path,
) -> None:
    """AC-9: on a first invocation no cache exists at loop entry, so the init
    seeding path runs unchanged (consumed starts at 0, effective_budget from the
    formula) — reconstruction is additive and gated solely on cache presence."""
    sprint = _write_sprint_status(
        tmp_path,
        {"15-1-a": "ready-for-dev", "15-2-b": "ready-for-dev"},
    )
    erp = tmp_path / "epic-run-state.yaml"
    assert not erp.exists()
    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp,
        story_loop_runner=_retry_runner({"15-1-a": 1}),
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert result.final_state.current_state == "epic-complete"
    assert result.final_state.per_epic_retry_budget.consumed == 1
    assert result.final_state.per_epic_retry_budget.effective_budget == 4


# ---------------------------------------------------------------------------
# Story 18.1 AC-4 — parallel_stories: false is bit-identical to the sequential
# Epic-15/16 posture (the parallel branch is additive, gated solely on the flag)
# ---------------------------------------------------------------------------


def test_default_mode_is_byte_identical_to_explicit_false(
    tmp_path: pathlib.Path,
) -> None:
    """AC-4: omitting the new parallel params (the default) and passing
    ``parallel_stories=False`` explicitly produce a byte-for-byte identical
    epic-run-state.yaml — the parallel branch is purely additive and the
    sequential body runs verbatim."""
    sprint = _write_sprint_status(
        tmp_path,
        {"15-1-a": "ready-for-dev", "15-2-b": "ready-for-dev", "15-3-c": "ready-for-dev"},
    )
    erp_default = tmp_path / "default.yaml"
    erp_explicit = tmp_path / "explicit.yaml"

    run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp_default,
        story_loop_runner=_retry_runner({"15-1-a": 1, "15-2-b": 1}),
        multiplier=2,
        transient_marker_classes=_NO_TRANSIENT,
    )
    run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=erp_explicit,
        story_loop_runner=_retry_runner({"15-1-a": 1, "15-2-b": 1}),
        multiplier=2,
        transient_marker_classes=_NO_TRANSIENT,
        parallel_stories=False,
    )
    assert erp_default.read_bytes() == erp_explicit.read_bytes()
