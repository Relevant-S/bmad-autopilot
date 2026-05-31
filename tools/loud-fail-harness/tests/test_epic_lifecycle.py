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

from loud_fail_harness import epic_lifecycle as epic_lifecycle_module
from loud_fail_harness.epic_lifecycle import (
    EpicStoryEnumerationError,
    derive_epic_state,
    enumerate_epic_stories,
    fold_story_terminal,
    init_epic_run_state,
    run_epic_loop,
)
from loud_fail_harness.epic_run_state import EpicRunState

_NO_TRANSIENT: frozenset[str] = frozenset()


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

    def runner(*, story_id: str, index: int, total: int) -> str:
        dispatched.append(story_id)
        return "merge-ready"

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

    def runner(*, story_id: str, index: int, total: int) -> str:
        return "done"

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

    def runner(*, story_id: str, index: int, total: int) -> str:
        dispatched.append(story_id)
        return next(outcomes)

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

    def runner(*, story_id: str, index: int, total: int) -> str:
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

    def runner(*, story_id: str, index: int, total: int) -> str:
        return "merge-ready"

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

    def runner(*, story_id: str, index: int, total: int) -> str:
        return "merge-ready"

    result = run_epic_loop(
        "epic-15",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=tmp_path / "e.yaml",
        story_loop_runner=runner,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert isinstance(result.final_state, EpicRunState)
