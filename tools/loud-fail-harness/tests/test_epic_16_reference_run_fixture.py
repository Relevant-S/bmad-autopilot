"""Epic-16 reference-run fixture — the sprint-orchestration cohort driven
end-to-end through ``run_sprint_loop`` (Story 16.4).

This module is the Epic-16 analog of Story 15.5's
``test_epic_15_reference_run_fixture.py``, one scope up: where 15.5 drove the
EPIC Orchestrator (``epic_lifecycle.run_epic_loop``) across a synthetic
multi-story epic, this fixture drives the SPRINT Orchestrator
(``sprint_lifecycle.run_sprint_loop``) across a synthetic multi-epic sprint and
witnesses that Stories 16.1–16.4 interoperate at the seams. It is the EMPIRICAL,
CI-witnessed proof that the sprint-orchestration substrate composes end-to-end
BEFORE Epic 17 (auto-merge) builds on the sprint surface.

It adds NO production ``src/loud_fail_harness/*.py`` module and modifies none —
the substrate-component count stays FIVE per ADR-003 Consequence 1. The fixture
is a pure CONSUMER of the landed runtime (Stories 16.1–16.3 + this story's
``sprint_status_command``); the only new code is this ``tests/`` module (the
``docs/reference-runs/16-4-sprint-web/`` capture is derived from a clean-run pass
of the SAME substrate with a fixed ``generated_at``).

## Determinism seam — the injected ``EpicLoopRunner`` (the ratified 16.1 posture)

``run_sprint_loop`` injects an ``epic_loop_runner`` (keyword-only, non-defaulted).
In production it drives the UNCHANGED ``epic_lifecycle.run_epic_loop``; here the
escalation / budget-exhaustion / escalation-rate runs use deterministic stub
``EpicLoopOutcome`` envelopes (the architecturally-ratified Story 16.1 AC-2
determinism seam — NOT a mock-instead-of-real shortcut). The ONE place the CLEAN
run goes BEYOND a pure stub (AC-7) is the ≥-1-real-lifecycle discipline: BOTH
epic units drive a REAL nested ``run_epic_loop`` (with their own injected
``StoryLoopRunner`` stub, writing a genuine per-epic ``epic-run-state-<id>.yaml``
cache that SURVIVES for the ``status --sprint`` read), so the sprint↔epic seam is
a genuine integration witness, not a model-level tautology. **Path chosen: the
REAL nested ``run_epic_loop`` (not the pure-stub fallback) — it proved stable on
CI.** Canned per-story costs are non-zero so the aggregate cost partition is a
POSITIVE witness, not a degenerate all-zero table.

The synthetic sprint uses the non-real label ``sprint-916-ref`` with non-real
epics ``epic-916`` / ``epic-917`` and stories ``916-1-alpha`` / ``916-2-bravo`` /
``917-1-charlie`` (≥ 2 epics so a genuine mid-sprint boundary exists distinct
from sprint-close; ≥ 3 stories total) — no collision with the live planning slice.

Contract-coverage matrix (AC-7 contract; AC-8 is a review-verified committed
artifact, not CI-testable):

    [x] AC-7 every runtime artifact under tmp_path; zero writes outside sandbox
        → test_ref_run_lands_under_tmp_path
    [x] AC-7 clean → sprint-complete (full dispatch, no pause); escalation →
        sprint-paused-on-escalation (strict prefix); budget → sprint-paused-on-
        budget; rate → sprint-escalation-rate-exceeded marker (no pause); no raise
        → test_ref_run_drives_all_terminal_variants
    [x] AC-7 ≥ 1 epic unit drives a REAL nested run_epic_loop writing a surviving
        per-epic cache → test_ref_run_exercises_real_nested_epic_loop
    [x] AC-7 status --sprint render over the persisted terminal caches: tree +
        aggregate cost = Σ per-epic + retry-budget + escalation + scoped markers
        → test_ref_run_status_sprint_render_over_terminal_caches
    [x] AC-7 the 16.3 assemble_sprint_status_artifact at sprint close — both
        rendered from the SAME caches (the read path composes)
        → test_ref_run_sprint_status_artifact_assembly_composes
    [x] AC-7/AC-10 the full composed sprint lifecycle proves 16.1–16.3 interop
        → test_ref_run_composes_full_sprint_16_lifecycle
    [x] AC-7 docs/reference-runs/16-4-sprint-web/ committed (README + narrative +
        status-sprint-output.md + sprint-status-artifact-*.md + sprint-run-state
        snapshot); reference-projects.md web-row migrated in-place — review-verified
    [x] AC-8 deferred-work.md NFR-P3 per-sprint-latency H3-input entry appended;
        narrative.md stand-in caveat explicit — review-verified

Forward pointers (AC-10): Epic 17 (auto-merge) composes THIS sprint surface;
Story 23.2 consumes the ``docs/reference-runs/16-4-sprint-web/`` row this
fixture's clean run produced when populating ``phase-2-completion-evidence.md``.
The per-sprint NFR-P3 latency budget is an Epic 22 H3 deliverable that this
stand-in run cannot validate empirically (see ``narrative.md`` + ``deferred-work.md``).
"""

from __future__ import annotations

import datetime as dt
import pathlib
from dataclasses import dataclass

import pytest
import yaml

from loud_fail_harness.epic_lifecycle import StoryLoopOutcome, run_epic_loop
from loud_fail_harness.sprint_lifecycle import (
    SPRINT_ESCALATION_RATE_EXCEEDED_MARKER,
    EpicLoopOutcome,
    EpicLoopRunnerAdapter,
    RunSprintLoopResult,
    run_sprint_loop,
)
from loud_fail_harness.sprint_status_artifact import (
    AssembleSprintArtifactResult,
    assemble_sprint_status_artifact,
)
from loud_fail_harness.sprint_status_command import (
    SprintStatusRequest,
    inspect_sprint,
    render_sprint_inspection_human,
)

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

#: Synthetic, clearly-non-real sprint + epic ids (no collision with the live
#: planning slice). ``run_epic_loop`` requires ``epic-<digits>`` ids.
_SPRINT_ID = "sprint-916-ref"
_RUN_ID = "run-sprint-916-ref-001"
_EPIC_A = "epic-916"
_EPIC_B = "epic-917"
_STORY_A1 = "916-1-alpha"
_STORY_A2 = "916-2-bravo"
_STORY_B1 = "917-1-charlie"

#: Non-zero canned per-story costs → the aggregate cost partition is a POSITIVE
#: witness (no degenerate all-zero table). Retries land on story A1 so the
#: per-sprint retry-budget consumption line is positive.
_COSTS = {_STORY_A1: 1.50, _STORY_A2: 2.25, _STORY_B1: 0.75}
_RETRIES = {_STORY_A1: 1, _STORY_A2: 0, _STORY_B1: 0}
_COST_TOTAL = sum(_COSTS.values())

#: No transient classes filtered — the ratified unit-test posture (the durable
#: sprint-escalation-rate-exceeded marker must survive for the rate-run witness).
_NO_TRANSIENT: frozenset[str] = frozenset()

#: Fixed UTC timestamp → the status --sprint render + 16.3 artifact are
#: byte-stable (the docs capture is derived from this).
_FIXED = dt.datetime(2026, 6, 4, 12, 0, 0, tzinfo=dt.timezone.utc)


# --------------------------------------------------------------------------- #
# Synthetic sprint slice + outcome helpers                                     #
# --------------------------------------------------------------------------- #


def _write_sprint_status(repo_root: pathlib.Path) -> pathlib.Path:
    """Author the synthetic multi-epic sprint-status slice under tmp_path: two
    non-real epics with three ready-for-dev stories total (AC-7)."""
    path = repo_root / "_bmad" / "automation" / "sprint-status.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    development_status = {
        _EPIC_A: "in-progress",
        _STORY_A1: "ready-for-dev",
        _STORY_A2: "ready-for-dev",
        _EPIC_B: "in-progress",
        _STORY_B1: "ready-for-dev",
    }
    path.write_text(
        yaml.safe_dump({"development_status": development_status}, sort_keys=False),
        encoding="utf-8",
    )
    return path


def _epic_outcome(
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


def _canned_story_runner(
    *, story_id: str, index: int, total: int
) -> StoryLoopOutcome:
    """The per-story runner the clean run injects: canned non-zero per-story
    retries + costs so the per-epic budget consumption and cost partition are
    POSITIVE witnesses. Keyed by ``story_id`` so it serves either epic."""
    return StoryLoopOutcome(
        terminal_status="merge-ready",  # type: ignore[arg-type]
        retries_consumed=_RETRIES[story_id],
        cost=_COSTS[story_id],
    )


def _real_epic_runner(repo_root: pathlib.Path, sprint_status_path: pathlib.Path):
    """The PRIOR test-local ``EpicLoopRunner`` that hand-rolled the REAL nested
    ``run_epic_loop`` drive + ``RunEpicLoopResult`` → ``EpicLoopOutcome`` mapping.

    Retained as the reference the production :class:`EpicLoopRunnerAdapter` is
    proven byte-identical to (Story 16.5 AC-10
    ``test_clean_run_adapter_matches_prior_mapping``); the clean run itself now
    drives the production adapter (see :func:`_drive_clean_run`)."""

    def runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        result = run_epic_loop(
            epic_id,
            run_id=_RUN_ID,
            sprint_status_path=sprint_status_path,
            epic_run_state_path=epic_run_state_path,
            story_loop_runner=_canned_story_runner,
            transient_marker_classes=_NO_TRANSIENT,
        )
        terminal = result.final_state.current_state
        return _epic_outcome(
            terminal,
            retries_consumed=result.final_state.per_epic_retry_budget.consumed,
            stories_completed=len(result.dispatched_story_ids),
            escalated_count=1 if terminal == "epic-paused-on-escalation" else 0,
        )

    return runner


def _unused_story_runner(
    *, story_id: str, index: int, total: int
) -> StoryLoopOutcome:
    raise AssertionError("story_loop_runner must not be called (no unassigned units)")


# --------------------------------------------------------------------------- #
# Run carrier                                                                  #
# --------------------------------------------------------------------------- #


@dataclass
class _CleanRunArtifacts:
    result: RunSprintLoopResult
    status_sprint_human: str
    artifact_assembly: AssembleSprintArtifactResult
    sprint_run_state_path: pathlib.Path
    epic_cache_paths: tuple[pathlib.Path, ...]
    sandbox_paths: tuple[pathlib.Path, ...]


def _drive_clean_run(repo_root: pathlib.Path) -> _CleanRunArtifacts:
    """Drive the clean sprint run to ``sprint-complete`` via BOTH epics' REAL
    nested ``run_epic_loop``, then witness the ``status --sprint`` read + the
    16.3 artifact assembly over the persisted terminal caches."""
    sprint_status_path = _write_sprint_status(repo_root)
    automation = repo_root / "_bmad" / "automation"
    sprint_run_state_path = automation / "sprint-run-state.yaml"

    # AC-10: the clean-run path now drives the PRODUCTION EpicLoopRunnerAdapter
    # (the same RunEpicLoopResult → EpicLoopOutcome mapping the test-local
    # _real_epic_runner previously hand-rolled), so the ≥-1-real-nested-loop
    # witness flows through production code.
    result = run_sprint_loop(
        _SPRINT_ID,
        run_id=_RUN_ID,
        sprint_status_path=sprint_status_path,
        sprint_run_state_path=sprint_run_state_path,
        epic_loop_runner=EpicLoopRunnerAdapter(
            run_id=_RUN_ID,
            sprint_status_path=sprint_status_path,
            story_loop_runner=_canned_story_runner,
            transient_marker_classes=_NO_TRANSIENT,
        ),
        story_loop_runner=_unused_story_runner,
        repo_root=repo_root,
        transient_marker_classes=_NO_TRANSIENT,
    )

    epic_cache_paths = (
        automation / f"epic-run-state-{_EPIC_A}.yaml",
        automation / f"epic-run-state-{_EPIC_B}.yaml",
    )

    request = SprintStatusRequest(
        sprint_id=_SPRINT_ID,
        project_root=repo_root,
        sprint_run_state_path=sprint_run_state_path,
        repo_root=repo_root,
        generated_at=_FIXED,
    )
    outcome = inspect_sprint(request)
    assert outcome.action == "sprint-status-found"
    assert outcome.artifact is not None
    status_sprint_human = render_sprint_inspection_human(
        outcome.artifact,
        sprint_run_state_path=sprint_run_state_path,
        repo_root=repo_root,
    )

    artifact_assembly = assemble_sprint_status_artifact(
        sprint_run_state_path,
        repo_root=repo_root,
        sprint_artifacts_root=repo_root / "_bmad-output" / "sprints",
        generated_at=_FIXED,
    )

    sandbox_paths = (
        sprint_status_path,
        sprint_run_state_path,
        *epic_cache_paths,
        artifact_assembly.artifact_path,
    )
    return _CleanRunArtifacts(
        result=result,
        status_sprint_human=status_sprint_human,
        artifact_assembly=artifact_assembly,
        sprint_run_state_path=sprint_run_state_path,
        epic_cache_paths=epic_cache_paths,
        sandbox_paths=sandbox_paths,
    )


def _drive_escalation_run(repo_root: pathlib.Path) -> RunSprintLoopResult:
    """epic-916 escalates → sprint-paused-on-escalation; epic-917 does NOT
    auto-advance (sensor-not-advisor; strict prefix)."""
    sprint_status_path = _write_sprint_status(repo_root)
    srs = repo_root / "_bmad" / "automation" / "sprint-run-state-escalation.yaml"

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return _epic_outcome(
            "epic-paused-on-escalation",
            retries_consumed=1,
            stories_completed=2,
            escalated_count=1,
        )

    return run_sprint_loop(
        _SPRINT_ID,
        run_id=_RUN_ID,
        sprint_status_path=sprint_status_path,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=repo_root,
        transient_marker_classes=_NO_TRANSIENT,
    )


def _drive_budget_run(repo_root: pathlib.Path) -> RunSprintLoopResult:
    """Cumulative retries exhaust the per-sprint budget (multiplier 2 × 2 epics =
    4) at the epic-916 boundary with epic-917 undispatched → sprint-paused-on-
    budget."""
    sprint_status_path = _write_sprint_status(repo_root)
    srs = repo_root / "_bmad" / "automation" / "sprint-run-state-budget.yaml"

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return _epic_outcome(
            "epic-complete", retries_consumed=4, stories_completed=2
        )

    return run_sprint_loop(
        _SPRINT_ID,
        run_id=_RUN_ID,
        sprint_status_path=sprint_status_path,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=repo_root,
        transient_marker_classes=_NO_TRANSIENT,
    )


def _drive_rate_marker_run(repo_root: pathlib.Path) -> RunSprintLoopResult:
    """epic-916 surfaces 2 of 4 stories escalated INTERNALLY but returns
    epic-complete → rate 0.5 > 0.25 threshold → the informational
    sprint-escalation-rate-exceeded marker fires WITHOUT pausing; both epics
    complete → sprint-complete + marker present."""
    sprint_status_path = _write_sprint_status(repo_root)
    srs = repo_root / "_bmad" / "automation" / "sprint-run-state-rate.yaml"
    outcomes = {
        _EPIC_A: _epic_outcome(
            "epic-complete", stories_completed=4, escalated_count=2
        ),
        _EPIC_B: _epic_outcome("epic-complete", stories_completed=1),
    }

    def epic_runner(
        *, epic_id: str, index: int, total: int, epic_run_state_path: pathlib.Path
    ) -> EpicLoopOutcome:
        return outcomes[epic_id]

    return run_sprint_loop(
        _SPRINT_ID,
        run_id=_RUN_ID,
        sprint_status_path=sprint_status_path,
        sprint_run_state_path=srs,
        epic_loop_runner=epic_runner,
        story_loop_runner=_unused_story_runner,
        repo_root=repo_root,
        transient_marker_classes=_NO_TRANSIENT,
    )


@dataclass
class _RefRunResult:
    clean: _CleanRunArtifacts
    escalation: RunSprintLoopResult
    budget: RunSprintLoopResult
    rate: RunSprintLoopResult


def _drive_ref_run(repo_root: pathlib.Path) -> _RefRunResult:
    # The clean run lands first so its REAL per-epic caches survive for the
    # status --sprint read; the stub runs use DISTINCT sprint-run-state paths so
    # they never clobber the canonical terminal cache.
    clean = _drive_clean_run(repo_root)
    escalation = _drive_escalation_run(repo_root)
    budget = _drive_budget_run(repo_root)
    rate = _drive_rate_marker_run(repo_root)
    return _RefRunResult(
        clean=clean, escalation=escalation, budget=budget, rate=rate
    )


@pytest.fixture(scope="function")
def ref_run(tmp_path: pathlib.Path) -> _RefRunResult:
    return _drive_ref_run(tmp_path)


# --------------------------------------------------------------------------- #
# Witnesses                                                                     #
# --------------------------------------------------------------------------- #


def test_ref_run_lands_under_tmp_path(
    ref_run: _RefRunResult, tmp_path: pathlib.Path
) -> None:
    """AC-7 — every runtime artifact (sprint-status slice, sprint-run-state, the
    per-epic caches, the assembled artifact) lands under tmp_path; the fixture
    makes zero writes outside the sandbox."""
    for path in ref_run.clean.sandbox_paths:
        assert path.is_relative_to(tmp_path), f"{path} escaped the tmp_path sandbox"
    assert ref_run.escalation.wrote_path.is_relative_to(tmp_path)
    assert ref_run.budget.wrote_path.is_relative_to(tmp_path)
    assert ref_run.rate.wrote_path.is_relative_to(tmp_path)


def test_ref_run_drives_all_terminal_variants(ref_run: _RefRunResult) -> None:
    """AC-7 — clean → sprint-complete (full dispatch, no pause); escalation →
    sprint-paused-on-escalation (strict prefix, sensor-not-advisor); budget →
    sprint-paused-on-budget; rate → sprint-escalation-rate-exceeded marker
    (informational, does NOT pause). No run raised (reaching here proves it)."""
    clean = ref_run.clean.result
    assert clean.final_state.current_state == "sprint-complete"
    assert clean.dispatched_unit_ids == (_EPIC_A, _EPIC_B)
    assert clean.paused_on_unit_id is None

    esc = ref_run.escalation
    assert esc.final_state.current_state == "sprint-paused-on-escalation"
    assert esc.dispatched_unit_ids == (_EPIC_A,)
    assert esc.paused_on_unit_id == _EPIC_A
    # epic-917 did NOT auto-advance.
    assert esc.final_state.per_epic_status[_EPIC_B] == "epic-in-progress"

    bud = ref_run.budget
    assert bud.final_state.current_state == "sprint-paused-on-budget"
    assert bud.dispatched_unit_ids == (_EPIC_A,)
    assert bud.paused_on_unit_id == _EPIC_A

    rate = ref_run.rate
    assert rate.final_state.current_state == "sprint-complete"
    assert rate.paused_on_unit_id is None
    assert (
        SPRINT_ESCALATION_RATE_EXCEEDED_MARKER in rate.final_state.active_markers
    )


def test_ref_run_exercises_real_nested_epic_loop(ref_run: _RefRunResult) -> None:
    """AC-7 ≥-1-real-lifecycle — BOTH epic units drove a REAL nested
    run_epic_loop, each writing a genuine per-epic epic-run-state cache that
    SURVIVES on disk (epic-complete, positive cost) for the status --sprint read.
    The chosen witness path is the REAL nested loop, not the pure-stub fallback."""
    for path in ref_run.clean.epic_cache_paths:
        assert path.is_file()
        cache = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert cache["current_state"] == "epic-complete"
        assert cache["per_epic_cost_partition"]["epic_cost_total"] > 0.0


def test_ref_run_status_sprint_render_over_terminal_caches(
    ref_run: _RefRunResult,
) -> None:
    """AC-7 — the status --sprint render over the persisted terminal sprint cache
    + per-epic caches: the sprint-state tree is present; aggregate cost = Σ
    per-epic totals; the retry-budget used/total + escalation-rate + scoped
    active-markers sections render."""
    rendered = ref_run.clean.status_sprint_human
    assert "## Sprint state tree" in rendered
    # tree: epic header + nested per-story rows.
    assert f"- {_EPIC_A} → epic-complete" in rendered
    assert f"  - {_STORY_A1} → merge-ready" in rendered
    assert f"- {_EPIC_B} → epic-complete" in rendered
    assert f"  - {_STORY_B1} → merge-ready" in rendered
    # aggregate cost = Σ per-epic totals.
    assert f"Total: {_COST_TOTAL:.2f} USD." in rendered
    # retry-budget used 1 (story A1's retry) of 4 (multiplier 2 × 2 epics).
    assert "Used 1 of 4." in rendered
    # escalation rate 0% on the clean run; no active markers.
    assert "Escalated 0 of 3 completed = 0.0%." in rendered
    assert "(no active markers)" in rendered
    # AC-3 drill-down pointers present.
    assert "/bmad-automation status --epic <epic-id>" in rendered


def test_ref_run_sprint_status_artifact_assembly_composes(
    ref_run: _RefRunResult,
) -> None:
    """AC-7 — the 16.3 assemble_sprint_status_artifact at sprint close renders
    from the SAME terminal caches the status --sprint read used (the read path
    composes): aggregate cost matches; the artifact landed on disk."""
    assembly = ref_run.clean.artifact_assembly
    assert assembly.artifact_path.is_file()
    assert assembly.sprint_id == _SPRINT_ID
    assert assembly.current_state == "sprint-complete"
    assert assembly.artifact.aggregate_cost_total == pytest.approx(_COST_TOTAL)
    # The status --sprint render and the artifact agree on the aggregate.
    assert f"Total: {_COST_TOTAL:.2f} USD." in ref_run.clean.status_sprint_human


def test_ref_run_composes_full_sprint_16_lifecycle(ref_run: _RefRunResult) -> None:
    """AC-7 / AC-10 — the full composed sprint lifecycle proves Stories 16.1–16.3
    interoperate at the seams: enumerate sprint units → init_sprint_run_state →
    sequential dispatch via the injected EpicLoopRunner (with REAL nested
    run_epic_loop) → fold_epic_terminal / apply_sprint_budget / escalation-rate
    tally → advance_sprint_run_state atomic writes → terminal sprint-complete /
    sprint-paused-on-escalation / sprint-paused-on-budget → the status --sprint
    read + the 16.3 artifact assembly."""
    clean = ref_run.clean
    assert clean.result.final_state.current_state == "sprint-complete"
    assert clean.result.final_state.per_epic_status == {
        _EPIC_A: "epic-complete",
        _EPIC_B: "epic-complete",
    }
    assert clean.result.final_state.per_sprint_retry_budget.consumed == 1
    assert clean.result.final_state.per_sprint_retry_budget.effective_budget == 4
    assert clean.artifact_assembly.artifact.aggregate_cost_total == pytest.approx(
        _COST_TOTAL
    )
    assert ref_run.escalation.final_state.current_state == "sprint-paused-on-escalation"
    assert ref_run.budget.final_state.current_state == "sprint-paused-on-budget"
    assert (
        SPRINT_ESCALATION_RATE_EXCEEDED_MARKER
        in ref_run.rate.final_state.active_markers
    )


def test_clean_run_adapter_matches_prior_mapping(tmp_path: pathlib.Path) -> None:
    """AC-10 — the production ``EpicLoopRunnerAdapter`` produces an
    ``EpicLoopOutcome`` identical to the prior test-local ``_real_epic_runner``
    mapping for the same epic unit, proving the adapter IS the mapping the
    fixture previously hand-rolled (both drive the SAME nested run_epic_loop into
    distinct per-epic caches)."""
    sprint_status_path = _write_sprint_status(tmp_path)

    adapter = EpicLoopRunnerAdapter(
        run_id=_RUN_ID,
        sprint_status_path=sprint_status_path,
        story_loop_runner=_canned_story_runner,
        transient_marker_classes=_NO_TRANSIENT,
    )
    adapter_outcome = adapter(
        epic_id=_EPIC_A,
        index=1,
        total=2,
        epic_run_state_path=tmp_path / "adapter-epic-916.yaml",
    )

    prior_outcome = _real_epic_runner(tmp_path, sprint_status_path)(
        epic_id=_EPIC_A,
        index=1,
        total=2,
        epic_run_state_path=tmp_path / "prior-epic-916.yaml",
    )

    assert adapter_outcome == prior_outcome
    assert adapter_outcome.terminal_state == "epic-complete"
    assert adapter_outcome.stories_completed == 2
    assert adapter_outcome.retries_consumed == (
        _RETRIES[_STORY_A1] + _RETRIES[_STORY_A2]
    )
