"""Contract-coverage matrix for the sprint-lifecycle module (story 16.1).

This docstring IS the contract-coverage checklist (review-enforced, parallel to
``test_epic_lifecycle.py``).

Enumeration (AC-1):
    [x] epic with >=1 ready-for-dev story is an epic unit                  → test_enumerate_includes_epic_with_ready_story
    [x] epic with zero ready-for-dev stories is excluded                   → test_enumerate_excludes_epic_with_no_ready_story
    [x] unassigned story (parent epic key absent) is a story unit          → test_enumerate_detects_unassigned_story
    [x] epic-assigned story (parent epic key present) is NOT unassigned    → test_enumerate_epic_assigned_story_not_unassigned
    [x] document order is preserved across epic + unassigned units         → test_enumerate_preserves_document_order
    [x] epic / retrospective keys are not mistaken for story units         → test_enumerate_excludes_epic_and_retro_keys
    [x] missing sprint-status raises SprintUnitEnumerationError            → test_enumerate_missing_sprint_status_raises
    [x] malformed development_status raises                                → test_enumerate_malformed_development_status_raises

Init (AC-1):
    [x] init seeds sprint-in-progress + epic-in-progress per-epic seed     → test_init_seeds_in_progress
    [x] init populates the per-sprint retry-budget STRUCTURE               → test_init_populates_retry_budget_structure
    [x] init records unassigned_story_ids (possibly empty)                 → test_init_records_unassigned_story_ids

State machine (AC-4):
    [x] all epics complete + all stories terminal → sprint-complete        → test_derive_sprint_state_complete
    [x] any epic paused-on-escalation → sprint-paused-on-escalation        → test_derive_sprint_state_epic_escalation
    [x] any unassigned story escalated → sprint-paused-on-escalation       → test_derive_sprint_state_story_escalation
    [x] any epic paused-on-budget → sprint-paused-on-budget                → test_derive_sprint_state_epic_budget
    [x] escalation keeps precedence over budget                            → test_derive_sprint_state_escalation_precedence
    [x] mixed / in-progress → sprint-in-progress                           → test_derive_sprint_state_in_progress
    [x] fold_epic_terminal updates + recomputes                            → test_fold_epic_terminal_updates_and_recomputes
    [x] fold_epic_terminal does not mutate the input                       → test_fold_epic_terminal_does_not_mutate_input
    [x] fold_epic_terminal rejects unknown epic                            → test_fold_epic_terminal_rejects_unknown_epic
    [x] fold_epic_terminal rejects invalid epic state                      → test_fold_epic_terminal_rejects_invalid_state
    [x] fold_unassigned_story_terminal updates + recomputes                → test_fold_unassigned_story_terminal_updates_and_recomputes
    [x] fold_unassigned_story_terminal rejects unknown story               → test_fold_unassigned_story_terminal_rejects_unknown_story
    [x] fold_unassigned_story_terminal rejects invalid status              → test_fold_unassigned_story_terminal_rejects_invalid_status

Sequential loop (AC-2, AC-3, AC-4, AC-5, AC-6, AC-7):
    [x] clean run dispatches all units → sprint-complete + persists        → test_run_sprint_loop_clean_run_completes
    [x] epic-paused-on-budget unit → sprint-paused-on-budget + prefix      → test_run_sprint_loop_pauses_on_epic_budget
    [x] escalated unassigned story → sprint-paused-on-escalation + prefix  → test_run_sprint_loop_pauses_on_story_escalation
    [x] epic-paused-on-escalation unit → sprint-paused-on-escalation       → test_run_sprint_loop_pauses_on_epic_escalation
    [x] per-epic path addressing witnessed (distinct path per epic unit)   → test_run_sprint_loop_addresses_per_epic_paths
    [x] progress_sink fires "unit K of T" per completion boundary          → test_run_sprint_loop_streams_unit_progress
    [x] empty sprint raises SprintUnitEnumerationError                     → test_run_sprint_loop_empty_sprint_raises
    [x] loop resolves the taxonomy default without error                   → test_run_sprint_loop_default_taxonomy_path
    [x] NEGATIVE-SURFACE: no retrospective + no sprint-status-artifact      → test_run_sprint_loop_writes_no_retrospective_or_artifact

Loud-fail + bit-identity (AC-2, AC-8):
    [x] SprintUnitEnumerationError carries marker_class None               → test_enumeration_error_marker_class_is_none
    [x] sprint_lifecycle does NOT import orchestrator_run_entry (additive) → test_sprint_lifecycle_does_not_import_orchestrator_run_entry
    [x] final_state is a SprintRunState                                    → test_final_state_is_sprint_run_state
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from loud_fail_harness import sprint_lifecycle as sprint_lifecycle_module
from loud_fail_harness.epic_lifecycle import StoryLoopOutcome
from loud_fail_harness.epic_run_state import (
    ResumeBudgetReconstructionConflict,
    SprintRunState,
)
from loud_fail_harness.sprint_lifecycle import (
    DEFAULT_PER_SPRINT_RETRY_MULTIPLIER,
    DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD,
    SPRINT_ESCALATION_RATE_EXCEEDED_MARKER,
    EpicLoopOutcome,
    RunSprintLoopResult,
    SprintUnitEnumerationError,
    apply_sprint_budget,
    compute_per_sprint_effective_budget,
    derive_sprint_state,
    enumerate_sprint_units,
    fold_epic_terminal,
    fold_unassigned_story_terminal,
    init_sprint_run_state,
    run_sprint_loop,
)

_NO_TRANSIENT: frozenset[str] = frozenset()


def _epic_outcome(terminal_state: str) -> EpicLoopOutcome:
    return EpicLoopOutcome(terminal_state=terminal_state)  # type: ignore[arg-type]


def _story_outcome(terminal_status: str) -> StoryLoopOutcome:
    return StoryLoopOutcome(
        terminal_status=terminal_status,  # type: ignore[arg-type]
        retries_consumed=0,
    )


def _write_sprint_status(
    tmp_path: pathlib.Path, development_status: dict[str, str]
) -> pathlib.Path:
    path = tmp_path / "sprint-status.yaml"
    path.write_text(
        yaml.safe_dump(
            {"development_status": development_status}, sort_keys=False
        ),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Enumeration (AC-1)
# ---------------------------------------------------------------------------


def test_enumerate_includes_epic_with_ready_story(tmp_path: pathlib.Path) -> None:
    path = _write_sprint_status(
        tmp_path,
        {"epic-16": "in-progress", "16-1-a": "ready-for-dev"},
    )
    epics, unassigned = enumerate_sprint_units("s1", sprint_status_path=path)
    assert epics == ("epic-16",)
    assert unassigned == ()


def test_enumerate_excludes_epic_with_no_ready_story(
    tmp_path: pathlib.Path,
) -> None:
    path = _write_sprint_status(
        tmp_path,
        {"epic-16": "done", "16-1-a": "done", "16-2-b": "backlog"},
    )
    with pytest.raises(SprintUnitEnumerationError):
        run_sprint_loop(
            "s1",
            run_id="r1",
            sprint_status_path=path,
            sprint_run_state_path=tmp_path / "srs.yaml",
            epic_loop_runner=_unused_epic_runner,
            story_loop_runner=_unused_story_runner,
            repo_root=tmp_path,
            transient_marker_classes=_NO_TRANSIENT,
        )
    epics, unassigned = enumerate_sprint_units("s1", sprint_status_path=path)
    assert epics == ()
    assert unassigned == ()


def test_enumerate_detects_unassigned_story(tmp_path: pathlib.Path) -> None:
    path = _write_sprint_status(
        tmp_path,
        {
            "epic-16": "in-progress",
            "16-1-a": "ready-for-dev",
            "99-1-loose": "ready-for-dev",
        },
    )
    epics, unassigned = enumerate_sprint_units("s1", sprint_status_path=path)
    assert epics == ("epic-16",)
    assert unassigned == ("99-1-loose",)


def test_enumerate_epic_assigned_story_not_unassigned(
    tmp_path: pathlib.Path,
) -> None:
    """A story whose parent epic key IS present is epic-assigned, never
    unassigned — even if that epic is itself already done (assignment is about
    the PRESENCE of the epic-<N> key, not the epic's status)."""
    path = _write_sprint_status(
        tmp_path,
        {
            "epic-16": "done",
            "16-1-a": "ready-for-dev",
            "epic-17": "in-progress",
            "17-1-b": "ready-for-dev",
        },
    )
    epics, unassigned = enumerate_sprint_units("s1", sprint_status_path=path)
    assert epics == ("epic-16", "epic-17")
    assert unassigned == ()


def test_enumerate_preserves_document_order(tmp_path: pathlib.Path) -> None:
    path = _write_sprint_status(
        tmp_path,
        {
            "0-1-loose-first": "ready-for-dev",
            "epic-16": "in-progress",
            "16-1-a": "ready-for-dev",
            "0-2-loose-second": "ready-for-dev",
        },
    )
    ordered, epics, unassigned = sprint_lifecycle_module._parse_sprint_units(
        "s1", sprint_status_path=path
    )
    assert ordered == (
        ("unassigned-story", "0-1-loose-first"),
        ("epic", "epic-16"),
        ("unassigned-story", "0-2-loose-second"),
    )
    assert epics == ("epic-16",)
    assert unassigned == ("0-1-loose-first", "0-2-loose-second")


def test_enumerate_excludes_epic_and_retro_keys(tmp_path: pathlib.Path) -> None:
    path = _write_sprint_status(
        tmp_path,
        {
            "epic-16": "in-progress",
            "epic-16-retrospective": "optional",
            "16-1-a": "ready-for-dev",
        },
    )
    epics, unassigned = enumerate_sprint_units("s1", sprint_status_path=path)
    assert epics == ("epic-16",)
    assert unassigned == ()


def test_enumerate_missing_sprint_status_raises(tmp_path: pathlib.Path) -> None:
    with pytest.raises(SprintUnitEnumerationError, match="not found"):
        enumerate_sprint_units(
            "s1", sprint_status_path=tmp_path / "nope.yaml"
        )


def test_enumerate_invalid_yaml_raises(tmp_path: pathlib.Path) -> None:
    """A syntactically-invalid sprint-status.yaml raises SprintUnitEnumerationError
    (not a raw yaml.YAMLError) — the function's docstring contracts this."""
    path = tmp_path / "sprint-status.yaml"
    path.write_text("{ invalid: yaml: [\n", encoding="utf-8")
    with pytest.raises(SprintUnitEnumerationError, match="not valid YAML"):
        enumerate_sprint_units("s1", sprint_status_path=path)


def test_enumerate_malformed_development_status_raises(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "sprint-status.yaml"
    path.write_text("development_status: not-a-mapping\n", encoding="utf-8")
    with pytest.raises(SprintUnitEnumerationError, match="development_status"):
        enumerate_sprint_units("s1", sprint_status_path=path)


# ---------------------------------------------------------------------------
# Init (AC-1)
# ---------------------------------------------------------------------------


def test_init_seeds_in_progress() -> None:
    state = init_sprint_run_state("s1", "r1", ("epic-15", "epic-16"), ())
    assert state.current_state == "sprint-in-progress"
    assert state.epic_ids == ("epic-15", "epic-16")
    assert state.per_epic_status == {
        "epic-15": "epic-in-progress",
        "epic-16": "epic-in-progress",
    }
    assert state.active_markers == ()


def test_init_populates_retry_budget_structure() -> None:
    state = init_sprint_run_state(
        "s1", "r1", ("epic-15", "epic-16", "epic-17"), ()
    )
    budget = state.per_sprint_retry_budget
    assert budget.multiplier == DEFAULT_PER_SPRINT_RETRY_MULTIPLIER
    assert budget.epic_count == 3
    assert budget.effective_budget == DEFAULT_PER_SPRINT_RETRY_MULTIPLIER * 3
    assert budget.consumed == 0


def test_init_records_unassigned_story_ids() -> None:
    state = init_sprint_run_state(
        "s1", "r1", ("epic-15",), ("99-1-loose", "99-2-loose")
    )
    assert state.unassigned_story_ids == ("99-1-loose", "99-2-loose")
    # An empty unassigned set is conformant.
    empty = init_sprint_run_state("s1", "r1", ("epic-15",), ())
    assert empty.unassigned_story_ids == ()


# ---------------------------------------------------------------------------
# State machine (AC-4)
# ---------------------------------------------------------------------------


def test_derive_sprint_state_complete() -> None:
    assert (
        derive_sprint_state(
            {"epic-15": "epic-complete", "epic-16": "epic-complete"},
            {"99-1": "merge-ready"},
        )
        == "sprint-complete"
    )


def test_derive_sprint_state_epic_escalation() -> None:
    assert (
        derive_sprint_state(
            {"epic-15": "epic-complete", "epic-16": "epic-paused-on-escalation"},
            {},
        )
        == "sprint-paused-on-escalation"
    )


def test_derive_sprint_state_story_escalation() -> None:
    assert (
        derive_sprint_state(
            {"epic-15": "epic-complete"},
            {"99-1": "escalated"},
        )
        == "sprint-paused-on-escalation"
    )


def test_derive_sprint_state_epic_budget() -> None:
    assert (
        derive_sprint_state(
            {"epic-15": "epic-complete", "epic-16": "epic-paused-on-budget"},
            {},
        )
        == "sprint-paused-on-budget"
    )


def test_derive_sprint_state_escalation_precedence() -> None:
    """Escalation keeps precedence over budget when both present (mirror
    apply_epic_budget precedence one scope down)."""
    assert (
        derive_sprint_state(
            {
                "epic-15": "epic-paused-on-escalation",
                "epic-16": "epic-paused-on-budget",
            },
            {},
        )
        == "sprint-paused-on-escalation"
    )


def test_derive_sprint_state_in_progress() -> None:
    assert (
        derive_sprint_state(
            {"epic-15": "epic-complete", "epic-16": "epic-in-progress"},
            {},
        )
        == "sprint-in-progress"
    )
    # A still-running unassigned story also keeps the sprint in progress.
    assert (
        derive_sprint_state(
            {"epic-15": "epic-complete"},
            {"99-1": "in-progress"},
        )
        == "sprint-in-progress"
    )


def test_fold_epic_terminal_updates_and_recomputes() -> None:
    state = init_sprint_run_state("s1", "r1", ("epic-15", "epic-16"), ())
    folded = fold_epic_terminal(
        state, "epic-15", "epic-complete", per_unassigned_status={}
    )
    assert folded.per_epic_status["epic-15"] == "epic-complete"
    assert folded.per_epic_status["epic-16"] == "epic-in-progress"
    assert folded.current_state == "sprint-in-progress"
    both = fold_epic_terminal(
        folded, "epic-16", "epic-complete", per_unassigned_status={}
    )
    assert both.current_state == "sprint-complete"


def test_fold_epic_terminal_does_not_mutate_input() -> None:
    state = init_sprint_run_state("s1", "r1", ("epic-15",), ())
    fold_epic_terminal(
        state, "epic-15", "epic-paused-on-escalation", per_unassigned_status={}
    )
    assert state.per_epic_status["epic-15"] == "epic-in-progress"
    assert state.current_state == "sprint-in-progress"


def test_fold_epic_terminal_rejects_unknown_epic() -> None:
    state = init_sprint_run_state("s1", "r1", ("epic-15",), ())
    with pytest.raises(ValueError, match="not a contained epic"):
        fold_epic_terminal(
            state, "epic-99", "epic-complete", per_unassigned_status={}
        )


def test_fold_epic_terminal_rejects_invalid_state() -> None:
    state = init_sprint_run_state("s1", "r1", ("epic-15",), ())
    with pytest.raises(ValueError, match="not a terminal epic"):
        fold_epic_terminal(
            state, "epic-15", "totally-bogus", per_unassigned_status={}
        )


def test_fold_epic_terminal_rejects_non_terminal_state() -> None:
    """fold_epic_terminal only accepts states in _EXPECTED_EPIC_TERMINAL;
    non-terminal values like 'epic-in-progress' are rejected at the API
    boundary, not silently folded into the aggregate."""
    state = init_sprint_run_state("s1", "r1", ("epic-15",), ())
    with pytest.raises(ValueError, match="not a terminal epic"):
        fold_epic_terminal(
            state, "epic-15", "epic-in-progress", per_unassigned_status={}
        )


def test_fold_unassigned_story_terminal_updates_and_recomputes() -> None:
    state = init_sprint_run_state(
        "s1", "r1", ("epic-15",), ("99-1-loose",)
    )
    state = fold_epic_terminal(
        state, "epic-15", "epic-complete", per_unassigned_status={"99-1-loose": "ready-for-dev"}
    )
    folded, per_unassigned = fold_unassigned_story_terminal(
        state,
        "99-1-loose",
        "merge-ready",
        per_unassigned_status={"99-1-loose": "ready-for-dev"},
    )
    assert per_unassigned["99-1-loose"] == "merge-ready"
    assert folded.current_state == "sprint-complete"


def test_fold_unassigned_story_terminal_rejects_unknown_story() -> None:
    state = init_sprint_run_state("s1", "r1", ("epic-15",), ("99-1-loose",))
    with pytest.raises(ValueError, match="not a contained unassigned story"):
        fold_unassigned_story_terminal(
            state, "99-9-nope", "done", per_unassigned_status={}
        )


def test_fold_unassigned_story_terminal_rejects_invalid_status() -> None:
    state = init_sprint_run_state("s1", "r1", ("epic-15",), ("99-1-loose",))
    with pytest.raises(ValueError, match="not a terminal per-story status"):
        fold_unassigned_story_terminal(
            state,
            "99-1-loose",
            "totally-bogus",
            per_unassigned_status={"99-1-loose": "ready-for-dev"},
        )


def test_fold_unassigned_story_terminal_rejects_non_terminal_status() -> None:
    """fold_unassigned_story_terminal only accepts statuses in
    _EXPECTED_STORY_TERMINAL; non-terminal values like 'in-progress' are
    rejected so they cannot silently prevent sprint-complete."""
    state = init_sprint_run_state("s1", "r1", ("epic-15",), ("99-1-loose",))
    with pytest.raises(ValueError, match="not a terminal per-story status"):
        fold_unassigned_story_terminal(
            state,
            "99-1-loose",
            "in-progress",
            per_unassigned_status={"99-1-loose": "ready-for-dev"},
        )


# ---------------------------------------------------------------------------
# Sequential loop (AC-2, AC-3, AC-4, AC-5, AC-6, AC-7)
# ---------------------------------------------------------------------------


def _unused_epic_runner(
    *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
) -> EpicLoopOutcome:
    raise AssertionError("epic_loop_runner must not be called")


def _unused_story_runner(
    *, story_id: str, index: int, total: int
) -> StoryLoopOutcome:
    raise AssertionError("story_loop_runner must not be called")


def test_run_sprint_loop_clean_run_completes(tmp_path: pathlib.Path) -> None:
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-16": "in-progress",
            "16-1-a": "ready-for-dev",
            "99-1-loose": "ready-for-dev",
        },
    )
    srs = tmp_path / "sprint-run-state.yaml"
    dispatched: list[str] = []

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        dispatched.append(epic_id)
        return _epic_outcome("epic-complete")

    def story_runner(
        *, story_id: str, index: int, total: int
    ) -> StoryLoopOutcome:
        dispatched.append(story_id)
        return _story_outcome("merge-ready")

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert dispatched == ["epic-16", "99-1-loose"]
    assert result.dispatched_unit_ids == ("epic-16", "99-1-loose")
    assert result.final_state.current_state == "sprint-complete"
    assert result.paused_on_unit_id is None
    on_disk = yaml.safe_load(srs.read_text(encoding="utf-8"))
    assert on_disk["current_state"] == "sprint-complete"
    assert on_disk["per_epic_status"] == {"epic-16": "epic-complete"}


def test_run_sprint_loop_pauses_on_epic_budget(tmp_path: pathlib.Path) -> None:
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-15": "in-progress",
            "15-1-a": "ready-for-dev",
            "epic-16": "in-progress",
            "16-1-b": "ready-for-dev",
        },
    )
    srs = tmp_path / "sprint-run-state.yaml"
    dispatched: list[str] = []
    outcomes = {"epic-15": "epic-paused-on-budget", "epic-16": "epic-complete"}

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        dispatched.append(epic_id)
        return _epic_outcome(outcomes[epic_id])

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    # epic-16 did NOT auto-advance (sensor-not-advisor; downstream prefix stops).
    assert dispatched == ["epic-15"]
    assert result.dispatched_unit_ids == ("epic-15",)
    assert result.paused_on_unit_id == "epic-15"
    assert result.final_state.current_state == "sprint-paused-on-budget"
    on_disk = yaml.safe_load(srs.read_text(encoding="utf-8"))
    assert on_disk["current_state"] == "sprint-paused-on-budget"
    # The downstream epic stays at its seeded state on disk.
    assert on_disk["per_epic_status"]["epic-16"] == "epic-in-progress"


def test_run_sprint_loop_pauses_on_story_escalation(
    tmp_path: pathlib.Path,
) -> None:
    sprint = _write_sprint_status(
        tmp_path,
        {
            "0-1-loose": "ready-for-dev",
            "epic-16": "in-progress",
            "16-1-b": "ready-for-dev",
        },
    )
    srs = tmp_path / "sprint-run-state.yaml"
    dispatched: list[str] = []

    def story_runner(
        *, story_id: str, index: int, total: int
    ) -> StoryLoopOutcome:
        dispatched.append(story_id)
        return _story_outcome("escalated")

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=_unused_epic_runner,
        story_loop_runner=story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    # 0-1-loose is first in document order; it escalates → pause before epic-16.
    assert dispatched == ["0-1-loose"]
    assert result.dispatched_unit_ids == ("0-1-loose",)
    assert result.paused_on_unit_id == "0-1-loose"
    assert result.final_state.current_state == "sprint-paused-on-escalation"


def test_run_sprint_loop_pauses_on_epic_escalation(
    tmp_path: pathlib.Path,
) -> None:
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-15": "in-progress",
            "15-1-a": "ready-for-dev",
            "epic-16": "in-progress",
            "16-1-b": "ready-for-dev",
        },
    )
    srs = tmp_path / "sprint-run-state.yaml"

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return _epic_outcome("epic-paused-on-escalation")

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert result.paused_on_unit_id == "epic-15"
    assert result.final_state.current_state == "sprint-paused-on-escalation"


def test_run_sprint_loop_addresses_per_epic_paths(
    tmp_path: pathlib.Path,
) -> None:
    """AC-3: each epic unit is dispatched with a DISTINCT per-epic-addressed
    epic_run_state_path (NOT the single per-story-scope default)."""
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-15": "in-progress",
            "15-1-a": "ready-for-dev",
            "epic-16": "in-progress",
            "16-1-b": "ready-for-dev",
        },
    )
    captured: dict[str, pathlib.Path] = {}

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        captured[epic_id] = epic_run_state_path
        return _epic_outcome("epic-complete")

    run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=tmp_path / "srs.yaml",
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert set(captured) == {"epic-15", "epic-16"}
    assert captured["epic-15"] != captured["epic-16"]
    assert captured["epic-15"] == (
        tmp_path / "_bmad" / "automation" / "epic-run-state-epic-15.yaml"
    )
    assert captured["epic-16"] == (
        tmp_path / "_bmad" / "automation" / "epic-run-state-epic-16.yaml"
    )


def test_run_sprint_loop_streams_unit_progress(tmp_path: pathlib.Path) -> None:
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-16": "in-progress",
            "16-1-a": "ready-for-dev",
            "99-1-loose": "ready-for-dev",
        },
    )
    lines: list[str] = []

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return _epic_outcome("epic-complete")

    def story_runner(
        *, story_id: str, index: int, total: int
    ) -> StoryLoopOutcome:
        return _story_outcome("merge-ready")

    run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=tmp_path / "srs.yaml",
        epic_loop_runner=epic_runner,
        story_loop_runner=story_runner,
        repo_root=tmp_path,
        progress_sink=lines.append,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert len(lines) == 2
    assert lines[0].startswith("[sprint] unit 1 of 2")
    assert "epic-16" in lines[0]
    assert "sprint now" in lines[0]
    assert lines[1].startswith("[sprint] unit 2 of 2")
    assert "99-1-loose" in lines[1]


def test_run_sprint_loop_epic_runner_returns_non_terminal_raises(
    tmp_path: pathlib.Path,
) -> None:
    """run_sprint_loop raises ValueError if the injected EpicLoopRunner returns
    a non-terminal state (e.g. 'epic-in-progress') — guards the runner contract
    so a buggy runner cannot silently corrupt the sprint aggregate."""
    sprint = _write_sprint_status(
        tmp_path,
        {"epic-16": "in-progress", "16-1-a": "ready-for-dev"},
    )

    def bad_epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return EpicLoopOutcome(terminal_state="epic-in-progress")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="non-terminal state"):
        run_sprint_loop(
            "s1",
            run_id="r1",
            sprint_status_path=sprint,
            sprint_run_state_path=tmp_path / "srs.yaml",
            epic_loop_runner=bad_epic_runner,
            story_loop_runner=_unused_story_runner,
            repo_root=tmp_path,
            transient_marker_classes=_NO_TRANSIENT,
        )


def test_run_sprint_loop_story_runner_returns_non_terminal_raises(
    tmp_path: pathlib.Path,
) -> None:
    """run_sprint_loop raises ValueError if the injected StoryLoopRunner returns
    a non-terminal status — guards the runner contract for unassigned stories."""
    sprint = _write_sprint_status(
        tmp_path,
        {"0-1-loose": "ready-for-dev"},
    )

    def bad_story_runner(
        *, story_id: str, index: int, total: int
    ) -> StoryLoopOutcome:
        return StoryLoopOutcome(
            terminal_status="in-progress",  # type: ignore[arg-type]
            retries_consumed=0,
        )

    with pytest.raises(ValueError, match="non-terminal status"):
        run_sprint_loop(
            "s1",
            run_id="r1",
            sprint_status_path=sprint,
            sprint_run_state_path=tmp_path / "srs.yaml",
            epic_loop_runner=_unused_epic_runner,
            story_loop_runner=bad_story_runner,
            repo_root=tmp_path,
            transient_marker_classes=_NO_TRANSIENT,
        )


def test_run_sprint_loop_all_unassigned_sprint(tmp_path: pathlib.Path) -> None:
    """A sprint with ONLY unassigned stories (no epic-<N> keys) is a valid
    dispatch target: epic_units=(), per_epic_status={}, effective_budget=0,
    and derive_sprint_state({}, {...}) reaches sprint-complete via the
    vacuously-true epics_done path."""
    sprint = _write_sprint_status(
        tmp_path,
        {
            "99-1-loose": "ready-for-dev",
            "99-2-loose": "ready-for-dev",
        },
    )
    srs = tmp_path / "sprint-run-state.yaml"
    dispatched: list[str] = []

    def story_runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        dispatched.append(story_id)
        return _story_outcome("merge-ready")

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=_unused_epic_runner,
        story_loop_runner=story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert dispatched == ["99-1-loose", "99-2-loose"]
    assert result.final_state.current_state == "sprint-complete"
    assert result.final_state.epic_ids == ()
    # Story 16.2: effective_budget = multiplier × epic_count (0) +
    # per_story_budget × unassigned_count = 2 × 0 + 2 × 2 = 4 (was 0 under the
    # 16.1 structure-only seed, which ignored the unassigned-story term).
    assert result.final_state.per_sprint_retry_budget.effective_budget == 4
    assert result.paused_on_unit_id is None
    on_disk = yaml.safe_load(srs.read_text(encoding="utf-8"))
    assert on_disk["current_state"] == "sprint-complete"
    assert on_disk["epic_ids"] == []


def test_run_sprint_loop_empty_sprint_raises(tmp_path: pathlib.Path) -> None:
    sprint = _write_sprint_status(tmp_path, {"epic-16": "done", "16-1-a": "done"})
    with pytest.raises(SprintUnitEnumerationError, match="no dispatchable units"):
        run_sprint_loop(
            "s1",
            run_id="r1",
            sprint_status_path=sprint,
            sprint_run_state_path=tmp_path / "srs.yaml",
            epic_loop_runner=_unused_epic_runner,
            story_loop_runner=_unused_story_runner,
            repo_root=tmp_path,
            transient_marker_classes=_NO_TRANSIENT,
        )


def test_run_sprint_loop_default_taxonomy_path(tmp_path: pathlib.Path) -> None:
    """No injected transient set → the loop resolves the on-disk taxonomy
    (find_repo_root at call time) without error. Smoke for the default path."""
    sprint = _write_sprint_status(
        tmp_path, {"epic-16": "in-progress", "16-1-a": "ready-for-dev"}
    )

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return _epic_outcome("epic-complete")

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=tmp_path / "srs.yaml",
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
    )
    assert result.final_state.current_state == "sprint-complete"


def test_run_sprint_loop_writes_no_retrospective_or_artifact(
    tmp_path: pathlib.Path,
) -> None:
    """AC-6 negative-surface witness: a full clean run writes ONLY the
    sprint-run-state cache — NO retrospective file and NO
    sprint-status-artifact-*.md anywhere under the run root."""
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-16": "in-progress",
            "16-1-a": "ready-for-dev",
            "99-1-loose": "ready-for-dev",
        },
    )
    srs = tmp_path / "sprint-run-state.yaml"

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return _epic_outcome("epic-complete")

    def story_runner(
        *, story_id: str, index: int, total: int
    ) -> StoryLoopOutcome:
        return _story_outcome("merge-ready")

    run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert srs.is_file()
    # The fake runners write no per-unit caches, so the ONLY artifact the sprint
    # loop itself produces is the sprint-run-state cache — never a retrospective
    # or a sprint-status-artifact (Story 16.3 owns the latter).
    assert list(tmp_path.rglob("*retro*")) == []
    assert list(tmp_path.rglob("sprint-status-artifact-*.md")) == []
    assert list(tmp_path.rglob("*retrospective*")) == []


# ---------------------------------------------------------------------------
# Loud-fail + bit-identity (AC-2, AC-8)
# ---------------------------------------------------------------------------


def test_enumeration_error_marker_class_is_none() -> None:
    assert SprintUnitEnumerationError.marker_class is None
    err = SprintUnitEnumerationError(sprint_id="s1", reason="x")
    assert err.sprint_id == "s1"
    assert err.reason == "x"


def test_sprint_lifecycle_does_not_import_orchestrator_run_entry() -> None:
    """AC-2 bit-identity: the sprint flag is purely additive — the
    sprint-lifecycle module composes the epic loop through the injected
    EpicLoopRunner Protocol and the per-story loop through the reused
    StoryLoopRunner, NOT by importing orchestrator_run_entry (nor by hard-
    importing run_epic_loop into its dispatch path). Structural witness."""
    source = pathlib.Path(sprint_lifecycle_module.__file__).read_text(
        encoding="utf-8"
    )
    import_lines = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from "))
        and "orchestrator_run_entry" in line
    ]
    assert import_lines == []
    run_epic_loop_imports = [
        line
        for line in source.splitlines()
        if line.startswith(("import ", "from ")) and "run_epic_loop" in line
    ]
    assert run_epic_loop_imports == []


def test_final_state_is_sprint_run_state(tmp_path: pathlib.Path) -> None:
    sprint = _write_sprint_status(
        tmp_path, {"epic-16": "in-progress", "16-1-a": "ready-for-dev"}
    )

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return _epic_outcome("epic-complete")

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=tmp_path / "srs.yaml",
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert isinstance(result.final_state, SprintRunState)
    assert isinstance(result, RunSprintLoopResult)


# ===========================================================================
# Story 16.2 — per-sprint budget + escalation-rate marker
# ===========================================================================


def _epic_outcome_full(
    terminal_state: str,
    *,
    retries_consumed: int = 0,
    stories_completed: int = 0,
    escalated_count: int = 0,
) -> EpicLoopOutcome:
    return EpicLoopOutcome(
        terminal_state=terminal_state,  # type: ignore[arg-type]
        retries_consumed=retries_consumed,
        stories_completed=stories_completed,
        escalated_count=escalated_count,
    )


def _story_outcome_full(
    terminal_status: str, *, retries_consumed: int = 0
) -> StoryLoopOutcome:
    return StoryLoopOutcome(
        terminal_status=terminal_status,  # type: ignore[arg-type]
        retries_consumed=retries_consumed,
    )


# --- compute_per_sprint_effective_budget (AC-2) ----------------------------


def test_compute_budget_zero_unassigned_reduces_to_multiplier_times_epics() -> None:
    assert compute_per_sprint_effective_budget(2, 3, 2, 0) == 6


def test_compute_budget_adds_unassigned_per_story_term() -> None:
    # 2*3 + 2*4 = 6 + 8 = 14
    assert compute_per_sprint_effective_budget(2, 3, 2, 4) == 14


def test_compute_budget_total_for_empty_sprint() -> None:
    assert compute_per_sprint_effective_budget(2, 0, 2, 0) == 0


# --- init_sprint_run_state budget wiring (AC-2) ----------------------------


def test_init_default_path_bit_identical_to_story_16_1_seed() -> None:
    # Zero unassigned + default multiplier + no override → multiplier × epic_count.
    state = init_sprint_run_state("s1", "r1", ("epic-1", "epic-2"), ())
    budget = state.per_sprint_retry_budget
    assert budget.multiplier == DEFAULT_PER_SPRINT_RETRY_MULTIPLIER
    assert budget.epic_count == 2
    assert budget.effective_budget == 2 * 2
    assert budget.consumed == 0


def test_init_folds_unassigned_term_into_effective_budget() -> None:
    state = init_sprint_run_state(
        "s1", "r1", ("epic-1",), ("9-1-a", "9-2-b"), multiplier=2, per_story_budget=3
    )
    # 2*1 + 3*2 = 8
    assert state.per_sprint_retry_budget.effective_budget == 8


def test_init_override_replaces_computed_budget() -> None:
    state = init_sprint_run_state(
        "s1",
        "r1",
        ("epic-1", "epic-2", "epic-3"),
        (),
        multiplier=2,
        effective_budget_override=1,
    )
    # multiplier/epic_count still record the formula inputs for observability.
    assert state.per_sprint_retry_budget.multiplier == 2
    assert state.per_sprint_retry_budget.epic_count == 3
    assert state.per_sprint_retry_budget.effective_budget == 1


# --- apply_sprint_budget truth table (AC-4 / AC-7) -------------------------


def test_apply_sprint_budget_under_budget_unchanged() -> None:
    assert (
        apply_sprint_budget("sprint-in-progress", 1, 4, has_undispatched=True)
        == "sprint-in-progress"
    )


def test_apply_sprint_budget_exhausted_with_undispatched_pauses() -> None:
    assert (
        apply_sprint_budget("sprint-in-progress", 4, 4, has_undispatched=True)
        == "sprint-paused-on-budget"
    )


def test_apply_sprint_budget_exhausted_on_final_unit_not_a_pause() -> None:
    assert (
        apply_sprint_budget("sprint-complete", 4, 4, has_undispatched=False)
        == "sprint-complete"
    )


def test_apply_sprint_budget_escalation_precedence_preserved() -> None:
    # Escalation already won current_state; budget must NOT override it.
    assert (
        apply_sprint_budget(
            "sprint-paused-on-escalation", 9, 4, has_undispatched=True
        )
        == "sprint-paused-on-escalation"
    )


def test_apply_sprint_budget_zero_budget_degenerate_total() -> None:
    assert (
        apply_sprint_budget("sprint-in-progress", 0, 0, has_undispatched=True)
        == "sprint-in-progress"
    )


# --- run_sprint_loop budget enforcement (AC-3 / AC-4) ----------------------


def test_run_sprint_loop_accumulates_consumed(tmp_path: pathlib.Path) -> None:
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-15": "in-progress",
            "15-1-a": "ready-for-dev",
            "epic-16": "in-progress",
            "16-1-b": "ready-for-dev",
        },
    )
    srs = tmp_path / "srs.yaml"

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return _epic_outcome_full(
            "epic-complete", retries_consumed=1, stories_completed=1
        )

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        # 2 epics × multiplier 2 = effective 4; consumed 1+1 = 2 < 4 → complete.
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert result.final_state.current_state == "sprint-complete"
    assert result.final_state.per_sprint_retry_budget.consumed == 2
    on_disk = yaml.safe_load(srs.read_text(encoding="utf-8"))
    assert on_disk["per_sprint_retry_budget"]["consumed"] == 2


def test_run_sprint_loop_pauses_on_cumulative_budget(
    tmp_path: pathlib.Path,
) -> None:
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-15": "in-progress",
            "15-1-a": "ready-for-dev",
            "epic-16": "in-progress",
            "16-1-b": "ready-for-dev",
            "epic-17": "in-progress",
            "17-1-c": "ready-for-dev",
        },
    )
    srs = tmp_path / "srs.yaml"
    dispatched: list[str] = []

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        dispatched.append(epic_id)
        # 3 epics × multiplier 2 = effective 6. Each epic consumes 3:
        # after epic-15 consumed=3 (<6, continue); after epic-16 consumed=6
        # (>=6) with epic-17 undispatched → pause on budget.
        return _epic_outcome_full(
            "epic-complete", retries_consumed=3, stories_completed=1
        )

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert result.final_state.current_state == "sprint-paused-on-budget"
    assert result.paused_on_unit_id == "epic-16"
    # epic-17 was NOT dispatched (downstream prefix-stopped).
    assert dispatched == ["epic-15", "epic-16"]
    assert result.dispatched_unit_ids == ("epic-15", "epic-16")
    assert result.final_state.per_sprint_retry_budget.consumed == 6


def test_run_sprint_loop_exact_on_final_unit_completes(
    tmp_path: pathlib.Path,
) -> None:
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-15": "in-progress",
            "15-1-a": "ready-for-dev",
            "epic-16": "in-progress",
            "16-1-b": "ready-for-dev",
        },
    )
    srs = tmp_path / "srs.yaml"

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        # effective 4; each epic consumes 2 → exactly 4 on the FINAL epic with
        # no undispatched units remaining → sprint-complete, NOT a pause.
        return _epic_outcome_full(
            "epic-complete", retries_consumed=2, stories_completed=1
        )

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert result.final_state.current_state == "sprint-complete"
    assert result.final_state.per_sprint_retry_budget.consumed == 4


def test_run_sprint_loop_override_tightens_budget(tmp_path: pathlib.Path) -> None:
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-15": "in-progress",
            "15-1-a": "ready-for-dev",
            "epic-16": "in-progress",
            "16-1-b": "ready-for-dev",
        },
    )
    srs = tmp_path / "srs.yaml"
    dispatched: list[str] = []

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        dispatched.append(epic_id)
        return _epic_outcome_full(
            "epic-complete", retries_consumed=1, stories_completed=1
        )

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        effective_budget_override=1,
        transient_marker_classes=_NO_TRANSIENT,
    )
    # override 1: after epic-15 consumed=1>=1 with epic-16 undispatched → pause.
    assert result.final_state.current_state == "sprint-paused-on-budget"
    assert dispatched == ["epic-15"]


# --- run_sprint_loop escalation-rate marker (AC-5 / AC-7) ------------------


def test_run_sprint_loop_emits_escalation_rate_marker(
    tmp_path: pathlib.Path,
) -> None:
    # Two unassigned stories; the first escalates → 1/1 = 1.0 > 0.25 threshold
    # → marker emits. The story-escalation also pauses the sprint, so only the
    # first unit dispatches; the marker is present on the paused state.
    sprint = _write_sprint_status(
        tmp_path,
        {
            "9-1-a": "ready-for-dev",
            "9-2-b": "ready-for-dev",
        },
    )
    srs = tmp_path / "srs.yaml"

    def story_runner(
        *, story_id: str, index: int, total: int
    ) -> StoryLoopOutcome:
        return _story_outcome_full("escalated")

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=_unused_epic_runner,
        story_loop_runner=story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert SPRINT_ESCALATION_RATE_EXCEEDED_MARKER in result.final_state.active_markers
    on_disk = yaml.safe_load(srs.read_text(encoding="utf-8"))
    assert SPRINT_ESCALATION_RATE_EXCEEDED_MARKER in on_disk["active_markers"]


def test_run_sprint_loop_rate_marker_does_not_pause_and_coexists_with_complete(
    tmp_path: pathlib.Path,
) -> None:
    # Epic reports 4 completed stories, 1 escalated INTERNALLY but returns
    # epic-complete (escalated_count surfaced for the rate; terminal is clean).
    # 1/4 = 0.25 is NOT > 0.25; bump to 2/4 = 0.5 > 0.25 with escalated_count=2.
    sprint = _write_sprint_status(
        tmp_path,
        {"epic-16": "in-progress", "16-1-a": "ready-for-dev"},
    )
    srs = tmp_path / "srs.yaml"

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return _epic_outcome_full(
            "epic-complete",
            retries_consumed=0,
            stories_completed=4,
            escalated_count=2,
        )

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    # Rate 2/4 = 0.5 > 0.25 → marker emits; epic terminal clean → sprint-complete.
    assert result.final_state.current_state == "sprint-complete"
    assert SPRINT_ESCALATION_RATE_EXCEEDED_MARKER in result.final_state.active_markers


def test_run_sprint_loop_rate_below_threshold_no_marker(
    tmp_path: pathlib.Path,
) -> None:
    sprint = _write_sprint_status(
        tmp_path,
        {"epic-16": "in-progress", "16-1-a": "ready-for-dev"},
    )
    srs = tmp_path / "srs.yaml"

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        # 1/5 = 0.2 < 0.25 → no marker.
        return _epic_outcome_full(
            "epic-complete", stories_completed=5, escalated_count=1
        )

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert result.final_state.current_state == "sprint-complete"
    assert (
        SPRINT_ESCALATION_RATE_EXCEEDED_MARKER
        not in result.final_state.active_markers
    )


def test_run_sprint_loop_rate_marker_idempotent_single_append(
    tmp_path: pathlib.Path,
) -> None:
    # Two epics both with high escalation; the marker must be appended once.
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-15": "in-progress",
            "15-1-a": "ready-for-dev",
            "epic-16": "in-progress",
            "16-1-b": "ready-for-dev",
        },
    )
    srs = tmp_path / "srs.yaml"

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return _epic_outcome_full(
            "epic-complete", stories_completed=2, escalated_count=1
        )

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    markers = result.final_state.active_markers
    assert markers.count(SPRINT_ESCALATION_RATE_EXCEEDED_MARKER) == 1


def test_run_sprint_loop_rate_marker_durable_survives_transient_filter(
    tmp_path: pathlib.Path,
) -> None:
    # Even with a non-empty transient-class set, the durable rate marker must
    # NOT be stripped (it is durable by taxonomy default).
    sprint = _write_sprint_status(
        tmp_path,
        {"9-1-a": "ready-for-dev"},
    )
    srs = tmp_path / "srs.yaml"

    def story_runner(
        *, story_id: str, index: int, total: int
    ) -> StoryLoopOutcome:
        return _story_outcome_full("escalated")

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=_unused_epic_runner,
        story_loop_runner=story_runner,
        repo_root=tmp_path,
        transient_marker_classes=frozenset({"worktree-stale-lock"}),
    )
    assert (
        SPRINT_ESCALATION_RATE_EXCEEDED_MARKER in result.final_state.active_markers
    )


def test_run_sprint_loop_default_threshold_is_resolved_default() -> None:
    assert DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD == 0.25


def test_apply_sprint_budget_exhausted_without_undispatched_not_a_pause() -> None:
    # All units dispatched (has_undispatched=False): no future dispatch to guard,
    # so budget pause does NOT fire even when the budget is exhausted.
    assert (
        apply_sprint_budget("sprint-in-progress", 4, 4, has_undispatched=False)
        == "sprint-in-progress"
    )


def test_run_sprint_loop_budget_pause_and_rate_marker_coexist(
    tmp_path: pathlib.Path,
) -> None:
    # 3 epics, effective_budget = 3 × 2 = 6. Each epic: 3 retries consumed,
    # 1 story completed, 1 escalated (rate 1/1 = 1.0 > 0.25 threshold).
    # After epic-15: consumed=3 < 6, rate=1.0 → marker emits, sprint continues.
    # After epic-16: consumed=6 >= 6, epic-17 undispatched → sprint-paused-on-budget.
    # Marker already present (idempotent). Both conditions coexist.
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-15": "in-progress",
            "15-1-a": "ready-for-dev",
            "epic-16": "in-progress",
            "16-1-b": "ready-for-dev",
            "epic-17": "in-progress",
            "17-1-c": "ready-for-dev",
        },
    )
    srs = tmp_path / "srs.yaml"

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return _epic_outcome_full(
            "epic-complete",
            retries_consumed=3,
            stories_completed=1,
            escalated_count=1,
        )

    result = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert result.final_state.current_state == "sprint-paused-on-budget"
    assert SPRINT_ESCALATION_RATE_EXCEEDED_MARKER in result.final_state.active_markers


# ---------------------------------------------------------------------------
# Resume budget reconstruction (Story 16.5 AC-6/7/8/9/10)
# ---------------------------------------------------------------------------


def test_run_sprint_loop_resume_exhausted_dispatches_zero(
    tmp_path: pathlib.Path,
) -> None:
    """AC-6/AC-10 + review admission invariant: a re-invocation against a
    persisted sprint cache (same run_id) carries the cumulative per-sprint
    ``consumed`` forward (NOT reset to 0), and because the reconstructed budget
    is already exhausted at entry the pre-dispatch admission gate pauses WITHOUT
    dispatching any further unit — the guard holds strictly across resume."""
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-15": "in-progress",
            "15-1-a": "ready-for-dev",
            "epic-16": "in-progress",
            "16-1-b": "ready-for-dev",
        },
    )
    srs = tmp_path / "sprint-run-state.yaml"
    budget = DEFAULT_PER_SPRINT_RETRY_MULTIPLIER * 2  # 2 epics, no unassigned.

    # First run: epic-15 alone consumes the full per-sprint budget →
    # sprint-paused-on-budget after the first unit, epic-16 undispatched.
    def first_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        consumed = budget if epic_id == "epic-15" else 0
        return EpicLoopOutcome(
            terminal_state="epic-complete",  # type: ignore[arg-type]
            retries_consumed=consumed,
            stories_completed=1,
        )

    first = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=first_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert first.final_state.current_state == "sprint-paused-on-budget"
    assert first.final_state.per_sprint_retry_budget.consumed == budget
    assert first.dispatched_unit_ids == ("epic-15",)

    # Re-invoke with the SAME run_id. The budget was already exhausted at entry,
    # so the admission gate pauses BEFORE dispatching — the runner must never be
    # called (zero re-dispatch).
    def _must_not_dispatch(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        raise AssertionError(
            f"no unit may be dispatched on an exhausted resume; got {epic_id!r}"
        )

    resumed = run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=_must_not_dispatch,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    assert resumed.final_state.per_sprint_retry_budget.consumed == budget
    assert resumed.final_state.per_sprint_retry_budget.effective_budget == budget
    assert resumed.final_state.current_state == "sprint-paused-on-budget"
    assert resumed.dispatched_unit_ids == ()
    assert resumed.paused_on_unit_id is None


def test_run_sprint_loop_resume_run_id_mismatch_raises(
    tmp_path: pathlib.Path,
) -> None:
    """AC-8: a persisted sprint cache whose run_id differs from the loop's is a
    stale cache from a different run at the same address — the loop fails loudly
    with ``ResumeBudgetReconstructionConflict`` (recovery-state-conflict)."""
    sprint = _write_sprint_status(
        tmp_path,
        {
            "epic-15": "in-progress",
            "15-1-a": "ready-for-dev",
            "epic-16": "in-progress",
            "16-1-b": "ready-for-dev",
        },
    )
    srs = tmp_path / "sprint-run-state.yaml"

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return _epic_outcome("epic-complete")

    run_sprint_loop(
        "s1",
        run_id="r1",
        sprint_status_path=sprint,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=tmp_path,
        transient_marker_classes=_NO_TRANSIENT,
    )
    with pytest.raises(ResumeBudgetReconstructionConflict) as excinfo:
        run_sprint_loop(
            "s1",
            run_id="r2",
            sprint_status_path=sprint,
            sprint_run_state_path=srs,
            epic_loop_runner=epic_runner,
            story_loop_runner=_unused_story_runner,
            repo_root=tmp_path,
            transient_marker_classes=_NO_TRANSIENT,
        )
    err = excinfo.value
    assert err.marker_class == "recovery-state-conflict"
    assert err.cache_run_id == "r1"
    assert err.loop_run_id == "r2"
    assert str(srs) in str(err)
