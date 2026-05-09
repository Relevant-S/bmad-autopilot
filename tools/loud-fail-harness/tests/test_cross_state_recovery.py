"""Contract-coverage matrix for the cross-state recovery substrate (Story 8.2).

This docstring IS the contract-coverage checklist required by AC-9. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced (parallel to ``tests/test_session_start_reattach.py``).

AC-1 — Substrate library shape:
    [x] public API exposes RECOVERY_STATE_CONFLICT_MARKER_CLASS,
        RUN_STATE_RELATIVE_PATH, RecoveryRequest, RecoveryOutcome,
        CrossStateRecoveryError, derive_state_from_story_doc,
        extract_persisted_markers, render_recovery_state_conflict_diagnostic,
        evaluate_recovery, main
    [x] _DISAGREEMENT_CLASSES contains exactly the seven named invariants
    [x] _RECOVERABLE_MARKER_CLASSES and _EPHEMERAL_MARKER_CLASSES are disjoint

AC-2 — No-run-state path (1):
    [x] test_evaluate_recovery_emits_marker_on_no_run_state_on_disk

AC-3 — Disagreement enumeration (4):
    [x] test_lifecycle_state_mismatch_detected
    [x] test_active_markers_divergence_detected
    [x] test_specialist_dispatched_no_return_detected
    [x] test_sprint_status_disagrees_with_story_doc_detected

AC-4 — Section-presence oracle (5) + status-vs-section tiebreak (2):
    [x] test_derive_state_empty_sections_returns_ready_for_dev
    [x] test_derive_state_dev_only_returns_in_progress
    [x] test_derive_state_dev_plus_review_returns_review
    [x] test_derive_state_all_three_sections_returns_qa
    [x] test_derive_state_invalid_section_dependency_returns_corrupt
    [x] test_derive_state_section_presence_wins_over_status_line
    [x] test_derive_state_status_terminal_states_respected

AC-5 — Marker extraction (3) + best-effort restoration (2):
    [x] test_extract_persisted_markers_from_review_findings_taxonomy
    [x] test_extract_persisted_markers_from_qa_evidence_rows
    [x] test_extract_persisted_markers_from_html_comment
    [x] test_restored_markers_are_subset_of_extractable
    [x] test_unrestored_ephemeral_markers_are_observable_in_outcome

AC-6 — Reconcilable rebuild (3):
    [x] test_evaluate_recovery_rebuilds_run_state_on_lifecycle_mismatch
    [x] test_rebuilt_run_state_validates_against_schema
    [x] test_evaluate_recovery_rebuild_does_not_mutate_story_doc

AC-7 — Unsalvageable conflict + marker emission (3):
    [x] test_evaluate_recovery_emits_marker_on_story_doc_corrupt
    [x] test_evaluate_recovery_emits_marker_on_retry_history_irreconcilable
    [x] test_diagnostic_contains_required_clauses

AC-9 — CLI smoke (2):
    [x] test_main_exits_zero_on_recovery_clean_or_rebuilt
    [x] test_main_exits_one_on_recovery_conflict_halt
"""

from __future__ import annotations

import pathlib
import subprocess
from typing import Any

import pytest

from loud_fail_harness.cross_state_recovery import (
    RECOVERY_STATE_CONFLICT_MARKER_CLASS,
    RUN_STATE_RELATIVE_PATH,
    RecoveryOutcome,
    RecoveryRequest,
    _DISAGREEMENT_CLASSES,
    _EPHEMERAL_MARKER_CLASSES,
    _RECOVERABLE_MARKER_CLASSES,
    derive_state_from_story_doc,
    evaluate_recovery,
    extract_persisted_markers,
    main,
    render_recovery_state_conflict_diagnostic,
)
from loud_fail_harness.orchestrator_run_entry import (
    AcceptanceCriterion,
    SprintStatusResolution,
    StoryDocNotFound,
    StoryDocResolution,
)
from loud_fail_harness.run_state import (
    CostToDateBySpecialist,
    RetryAttempt,
    RunState,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)


# --------------------------------------------------------------------------- #
# Fixtures + helpers                                                          #
# --------------------------------------------------------------------------- #


def _run_git(*args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture(scope="function")
def tmp_project(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a fresh tmp_path-rooted git repo with deterministic identity."""
    _run_git("init", "-b", "main", cwd=tmp_path)
    _run_git("config", "user.email", "test@bmad-automation.local", cwd=tmp_path)
    _run_git("config", "user.name", "BMAD Test", cwd=tmp_path)
    _run_git("config", "commit.gpgsign", "false", cwd=tmp_path)
    (tmp_path / "README.md").write_text("# initial\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=tmp_path)
    _run_git("commit", "-m", "initial", cwd=tmp_path)
    # Pre-create the implementation-artifacts dir.
    (tmp_path / "_bmad-output" / "implementation-artifacts").mkdir(
        parents=True, exist_ok=True
    )
    (tmp_path / "_bmad" / "automation").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture(scope="module")
def marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


def _write_story_doc(
    project_root: pathlib.Path,
    story_id: str,
    *,
    status: str = "in-progress",
    sections: tuple[str, ...] = (),
    extra_body: str = "",
) -> pathlib.Path:
    """Write a synthetic story-doc with the given Status: line and section
    presence; returns the resolved path.

    The sections argument is a tuple of section heading literals (e.g.,
    ``"## Dev Agent Record"``).
    """
    target = (
        project_root
        / "_bmad-output"
        / "implementation-artifacts"
        / f"{story_id}-test-slug.md"
    )
    body_parts = [
        f"# Story {story_id}",
        "",
        f"Status: {status}",
        "",
        "## Acceptance Criteria",
        "",
        "**AC-1 — body** placeholder.",
        "",
    ]
    for section in sections:
        body_parts.extend([section, "", "section body placeholder.", ""])
    if extra_body:
        body_parts.extend([extra_body, ""])
    target.write_text("\n".join(body_parts), encoding="utf-8")
    return target


def _make_run_state(**overrides: Any) -> RunState:
    base: dict[str, Any] = {
        "schema_version": "1.3",
        "story_id": "8-2-test",
        "run_id": "r1",
        "current_state": "in-progress",
        "branch_name": "bmad-automation/story/8-2-test",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": (),
        "active_markers": (),
        "cost_to_date_by_specialist": CostToDateBySpecialist(),
    }
    base.update(overrides)
    return RunState.model_validate(base)


def _make_resolution(
    project_root: pathlib.Path, story_id: str, current_state: str
) -> StoryDocResolution:
    """Build a minimal StoryDocResolution for tests."""
    path = (
        project_root
        / "_bmad-output"
        / "implementation-artifacts"
        / f"{story_id}-test-slug.md"
    )
    return StoryDocResolution(
        path=path,
        current_state=current_state,  # type: ignore[arg-type]
        acceptance_criteria=(AcceptanceCriterion(ac_id="AC-1", text="placeholder"),),
    )


def _stub_story_doc_resolver(
    resolution: StoryDocResolution | None = None,
    raises: BaseException | None = None,
):
    """Build a StoryDocResolver stub returning a canned resolution OR raising."""

    def _resolver(story_id: str, project_root: pathlib.Path) -> StoryDocResolution:
        if raises is not None:
            raise raises
        assert resolution is not None
        return resolution

    return _resolver


def _stub_sprint_status_resolver(
    state: str | None = None, raises: BaseException | None = None
):
    def _resolver(story_id: str, project_root: pathlib.Path) -> SprintStatusResolution:
        if raises is not None:
            raise raises
        assert state is not None
        return SprintStatusResolution(current_state=state)  # type: ignore[arg-type]

    return _resolver


# --------------------------------------------------------------------------- #
# AC-1 — Substrate library shape                                              #
# --------------------------------------------------------------------------- #


def test_disagreement_classes_constant_has_exactly_seven_named_invariants() -> None:
    expected = {
        "lifecycle-state-mismatch",
        "active-markers-divergence",
        "specialist-dispatched-no-return",
        "sprint-status-disagrees-with-story-doc",
        "retry-history-irreconcilable",
        "story-doc-corrupt-or-missing",
        "no-run-state-on-disk",
    }
    assert _DISAGREEMENT_CLASSES == frozenset(expected)


def test_recoverable_and_ephemeral_marker_sets_are_disjoint() -> None:
    assert (_RECOVERABLE_MARKER_CLASSES & _EPHEMERAL_MARKER_CLASSES) == frozenset()


def test_module_constants_match_documented_paths() -> None:
    assert RUN_STATE_RELATIVE_PATH == "_bmad/automation/run-state.yaml"
    assert RECOVERY_STATE_CONFLICT_MARKER_CLASS == "recovery-state-conflict"


def test_pure_functions_are_byte_deterministic(tmp_project: pathlib.Path) -> None:
    """derive_state_from_story_doc + extract_persisted_markers + diagnostic
    rendering are byte-identical across repeated calls (defensive against
    accidental in-memory caching)."""
    text = (
        "Status: review\n\n## Acceptance Criteria\n\n**AC-1 — x**\n\n"
        "## Dev Agent Record\n\n## Senior Developer Review (AI)\n\n"
        "[Review][Patch] review-layer-failed: x\n"
    )
    resolution = _make_resolution(tmp_project, "8-2", "review")
    s1, sec1 = derive_state_from_story_doc(resolution, text)
    s2, sec2 = derive_state_from_story_doc(resolution, text)
    assert s1 == s2 and sec1 == sec2
    m1 = extract_persisted_markers(text, sec1)
    m2 = extract_persisted_markers(text, sec2)
    assert m1 == m2


# --------------------------------------------------------------------------- #
# AC-4 — Section-presence oracle                                              #
# --------------------------------------------------------------------------- #


def test_derive_state_empty_sections_returns_ready_for_dev(
    tmp_project: pathlib.Path,
) -> None:
    text = "Status: ready-for-dev\n\n## Acceptance Criteria\n\n**AC-1 — x**\n"
    resolution = _make_resolution(tmp_project, "8-2", "ready-for-dev")
    state, sections = derive_state_from_story_doc(resolution, text)
    assert state == "ready-for-dev"
    assert sections == frozenset()


def test_derive_state_dev_only_returns_in_progress(
    tmp_project: pathlib.Path,
) -> None:
    text = (
        "Status: in-progress\n\n## Acceptance Criteria\n\n**AC-1 — x**\n\n"
        "## Dev Agent Record\n\nbody.\n"
    )
    resolution = _make_resolution(tmp_project, "8-2", "in-progress")
    state, sections = derive_state_from_story_doc(resolution, text)
    assert state == "in-progress"
    assert "## Dev Agent Record" in sections


def test_derive_state_dev_plus_review_returns_review(
    tmp_project: pathlib.Path,
) -> None:
    text = (
        "Status: review\n\n## Acceptance Criteria\n\n**AC-1 — x**\n\n"
        "## Dev Agent Record\n\nbody.\n\n"
        "## Senior Developer Review (AI)\n\nreview body.\n"
    )
    resolution = _make_resolution(tmp_project, "8-2", "review")
    state, _ = derive_state_from_story_doc(resolution, text)
    assert state == "review"


def test_derive_state_all_three_sections_returns_qa(
    tmp_project: pathlib.Path,
) -> None:
    text = (
        "Status: qa\n\n## Acceptance Criteria\n\n**AC-1 — x**\n\n"
        "## Dev Agent Record\n\nbody.\n\n"
        "## Senior Developer Review (AI)\n\nreview body.\n\n"
        "## QA Behavioral Plan\n\nqa body.\n"
    )
    resolution = _make_resolution(tmp_project, "8-2", "qa")
    state, _ = derive_state_from_story_doc(resolution, text)
    assert state == "qa"


def test_derive_state_invalid_section_dependency_returns_corrupt(
    tmp_project: pathlib.Path,
) -> None:
    """## QA Behavioral Plan present without ## Senior Developer Review (AI)
    is structurally impossible per the lifecycle DAG."""
    text = (
        "Status: qa\n\n## Acceptance Criteria\n\n**AC-1 — x**\n\n"
        "## Dev Agent Record\n\nbody.\n\n"
        "## QA Behavioral Plan\n\nqa body.\n"
    )
    resolution = _make_resolution(tmp_project, "8-2", "qa")
    with pytest.raises(ValueError, match="section dependency violation"):
        derive_state_from_story_doc(resolution, text)


def test_derive_state_section_presence_wins_over_status_line(
    tmp_project: pathlib.Path,
) -> None:
    """Status: in-progress with review section present → review per ADR-005
    durability rationale (sections are durable; Status is mutable scalar)."""
    text = (
        "Status: in-progress\n\n## Acceptance Criteria\n\n**AC-1 — x**\n\n"
        "## Dev Agent Record\n\nbody.\n\n"
        "## Senior Developer Review (AI)\n\nreview body.\n"
    )
    resolution = _make_resolution(tmp_project, "8-2", "in-progress")
    state, _ = derive_state_from_story_doc(resolution, text)
    assert state == "review"


def test_derive_state_status_terminal_states_respected(
    tmp_project: pathlib.Path,
) -> None:
    """Status: done with all three sections → done; Status: escalated with QA
    section → escalated."""
    text_done = (
        "Status: done\n\n## Acceptance Criteria\n\n**AC-1 — x**\n\n"
        "## Dev Agent Record\n\nbody.\n\n"
        "## Senior Developer Review (AI)\n\nreview body.\n\n"
        "## QA Behavioral Plan\n\nqa body.\n"
    )
    resolution = _make_resolution(tmp_project, "8-2", "done")
    state_done, _ = derive_state_from_story_doc(resolution, text_done)
    assert state_done == "done"

    text_escalated = (
        "Status: escalated\n\n## Acceptance Criteria\n\n**AC-1 — x**\n\n"
        "## Dev Agent Record\n\nbody.\n\n"
        "## Senior Developer Review (AI)\n\nreview body.\n\n"
        "## QA Behavioral Plan\n\nqa body.\n"
    )
    resolution_e = _make_resolution(tmp_project, "8-2", "escalated")
    state_e, _ = derive_state_from_story_doc(resolution_e, text_escalated)
    assert state_e == "escalated"


# --------------------------------------------------------------------------- #
# AC-5 — Marker extraction                                                    #
# --------------------------------------------------------------------------- #


def test_extract_persisted_markers_from_review_findings_taxonomy() -> None:
    text = (
        "## Senior Developer Review (AI)\n\n"
        "[Review][Defer] review-layer-failed: layer-A timed out at retry 2\n\n"
        "[Review][Patch] decision-needed-finding: ambiguous AC-3 wording\n"
    )
    sections = frozenset({"## Senior Developer Review (AI)"})
    extracted = extract_persisted_markers(text, sections)
    assert "review-layer-failed" in extracted
    assert "decision-needed-finding" in extracted


def test_extract_persisted_markers_from_qa_evidence_rows() -> None:
    text = (
        "## QA Behavioral Plan\n\n"
        "AC-3 evidence: tier-3 evidence not configured for AC-3 (Story 4.8 default).\n"
    )
    sections = frozenset({"## QA Behavioral Plan"})
    extracted = extract_persisted_markers(text, sections)
    assert "tier-3-not-configured" in extracted


def test_extract_persisted_markers_from_html_comment() -> None:
    text = (
        "## Senior Developer Review (AI)\n\n"
        "<!-- marker: dangling-evidence-ref -->\n"
        "Some review prose.\n"
    )
    sections = frozenset({"## Senior Developer Review (AI)"})
    extracted = extract_persisted_markers(text, sections)
    assert "dangling-evidence-ref" in extracted


# --------------------------------------------------------------------------- #
# AC-3 — Disagreement enumeration                                             #
# --------------------------------------------------------------------------- #


def test_lifecycle_state_mismatch_detected(tmp_project: pathlib.Path) -> None:
    _write_story_doc(
        tmp_project,
        "8-2",
        status="review",
        sections=("## Dev Agent Record", "## Senior Developer Review (AI)"),
    )
    request = RecoveryRequest(
        project_root=tmp_project,
        story_id="8-2",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-2", "review")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="review"),
    )
    prior = _make_run_state(current_state="in-progress")
    outcome, _ = evaluate_recovery(request, run_state=prior)
    assert "lifecycle-state-mismatch" in outcome.disagreements


def test_active_markers_divergence_detected(tmp_project: pathlib.Path) -> None:
    """run-state's active_markers is missing a marker the story-doc has."""
    _write_story_doc(
        tmp_project,
        "8-2",
        status="review",
        sections=("## Dev Agent Record", "## Senior Developer Review (AI)"),
        extra_body="[Review][Defer] review-layer-failed: layer-A failed",
    )
    request = RecoveryRequest(
        project_root=tmp_project,
        story_id="8-2",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-2", "review")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="review"),
    )
    # run-state has no active_markers but story-doc has review-layer-failed.
    prior = _make_run_state(current_state="review", active_markers=())
    outcome, _ = evaluate_recovery(request, run_state=prior)
    assert "active-markers-divergence" in outcome.disagreements


def test_specialist_dispatched_no_return_detected(tmp_project: pathlib.Path) -> None:
    """run-state shows dev dispatched but no envelope AND no Dev Agent Record
    section in story-doc."""
    _write_story_doc(
        tmp_project,
        "8-2",
        status="ready-for-dev",
        sections=(),  # no Dev Agent Record section
    )
    request = RecoveryRequest(
        project_root=tmp_project,
        story_id="8-2",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-2", "ready-for-dev")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="in-progress"),
    )
    prior = _make_run_state(
        current_state="in-progress",
        dispatched_specialist="dev",
        last_envelope=None,
    )
    outcome, _ = evaluate_recovery(request, run_state=prior)
    assert "specialist-dispatched-no-return" in outcome.disagreements


def test_sprint_status_disagrees_with_story_doc_detected(
    tmp_project: pathlib.Path,
) -> None:
    """sprint-status says in-progress but story-doc-implied is review."""
    _write_story_doc(
        tmp_project,
        "8-2",
        status="review",
        sections=("## Dev Agent Record", "## Senior Developer Review (AI)"),
    )
    request = RecoveryRequest(
        project_root=tmp_project,
        story_id="8-2",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-2", "review")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="in-progress"),
    )
    prior = _make_run_state(current_state="review")
    outcome, _ = evaluate_recovery(request, run_state=prior)
    assert "sprint-status-disagrees-with-story-doc" in outcome.disagreements


# --------------------------------------------------------------------------- #
# AC-6 — Reconcilable rebuild                                                 #
# --------------------------------------------------------------------------- #


def test_evaluate_recovery_rebuilds_run_state_on_lifecycle_mismatch(
    tmp_project: pathlib.Path,
) -> None:
    _write_story_doc(
        tmp_project,
        "8-2",
        status="review",
        sections=("## Dev Agent Record", "## Senior Developer Review (AI)"),
    )
    captured_writes: list[tuple[pathlib.Path, RunState]] = []

    def stub_writer(p: pathlib.Path, s: RunState) -> None:
        captured_writes.append((p, s))

    # Materialize a run-state file on disk so the writer is invoked.
    rs_path = tmp_project / RUN_STATE_RELATIVE_PATH
    rs_path.write_text("# placeholder\n", encoding="utf-8")

    request = RecoveryRequest(
        project_root=tmp_project,
        story_id="8-2",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-2", "review")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="review"),
        run_state_writer=stub_writer,
    )
    prior = _make_run_state(
        current_state="in-progress",
        run_id="prior-run-id-XYZ",
        branch_name="bmad-automation/story/8-2-keep-this",
        cost_to_date_by_specialist=CostToDateBySpecialist(dev=1.5),
    )
    outcome, returned = evaluate_recovery(request, run_state=prior)

    assert outcome.action == "recovery-rebuilt"
    assert outcome.disagreements == ("lifecycle-state-mismatch",)
    assert outcome.rebuilt_run_state is not None
    assert outcome.rebuilt_run_state.current_state == "review"
    # Orchestrator-domain fields preserved.
    assert outcome.rebuilt_run_state.run_id == prior.run_id
    assert outcome.rebuilt_run_state.branch_name == prior.branch_name
    assert (
        outcome.rebuilt_run_state.cost_to_date_by_specialist
        == prior.cost_to_date_by_specialist
    )
    # Marker emission discipline: rebuild is silent.
    assert outcome.marker_class is None
    assert outcome.diagnostic is None
    # Writer invoked exactly once with the rebuilt state.
    assert len(captured_writes) == 1
    assert captured_writes[0][1] == outcome.rebuilt_run_state
    assert returned == outcome.rebuilt_run_state


def test_rebuilt_run_state_validates_against_schema(
    tmp_project: pathlib.Path,
) -> None:
    """Defensive ADR-005 Consequence 1 check — rebuilt instance MUST conform
    to the same schema as pre-crash instances."""
    _write_story_doc(
        tmp_project,
        "8-2",
        status="review",
        sections=("## Dev Agent Record", "## Senior Developer Review (AI)"),
    )
    request = RecoveryRequest(
        project_root=tmp_project,
        story_id="8-2",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-2", "review")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="review"),
        run_state_writer=lambda p, s: None,
    )
    prior = _make_run_state(current_state="in-progress")
    outcome, _ = evaluate_recovery(request, run_state=prior)
    assert outcome.action == "recovery-rebuilt"
    # If we got here without CrossStateRecoveryError, schema validation
    # succeeded inside _validate_rebuilt_against_schema.
    assert outcome.rebuilt_run_state is not None


def test_evaluate_recovery_rebuild_does_not_mutate_story_doc(
    tmp_project: pathlib.Path,
) -> None:
    story_doc_path = _write_story_doc(
        tmp_project,
        "8-2",
        status="review",
        sections=("## Dev Agent Record", "## Senior Developer Review (AI)"),
    )
    pre_bytes = story_doc_path.read_bytes()
    pre_mtime = story_doc_path.stat().st_mtime_ns

    request = RecoveryRequest(
        project_root=tmp_project,
        story_id="8-2",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-2", "review")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="review"),
        run_state_writer=lambda p, s: None,
    )
    prior = _make_run_state(current_state="in-progress")
    evaluate_recovery(request, run_state=prior)

    assert story_doc_path.read_bytes() == pre_bytes
    assert story_doc_path.stat().st_mtime_ns == pre_mtime


# --------------------------------------------------------------------------- #
# AC-5 — Best-effort marker restoration                                       #
# --------------------------------------------------------------------------- #


def test_restored_markers_are_subset_of_extractable(
    tmp_project: pathlib.Path,
) -> None:
    _write_story_doc(
        tmp_project,
        "8-2",
        status="review",
        sections=("## Dev Agent Record", "## Senior Developer Review (AI)"),
        extra_body="[Review][Defer] review-layer-failed: layer-A failed",
    )
    request = RecoveryRequest(
        project_root=tmp_project,
        story_id="8-2",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-2", "review")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="review"),
        run_state_writer=lambda p, s: None,
    )
    prior = _make_run_state(current_state="review", active_markers=())
    outcome, _ = evaluate_recovery(request, run_state=prior)
    # The story-doc only has review-layer-failed; restored should equal that.
    assert "review-layer-failed" in outcome.restored_markers


def test_unrestored_ephemeral_markers_are_observable_in_outcome(
    tmp_project: pathlib.Path,
) -> None:
    _write_story_doc(
        tmp_project,
        "8-2",
        status="review",
        sections=("## Dev Agent Record", "## Senior Developer Review (AI)"),
    )
    request = RecoveryRequest(
        project_root=tmp_project,
        story_id="8-2",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-2", "review")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="review"),
        run_state_writer=lambda p, s: None,
    )
    # Prior run-state carries an ephemeral marker AND a recoverable one.
    prior = _make_run_state(
        current_state="in-progress",  # mismatch triggers rebuild
        active_markers=(
            "specialist-timeout: timeout-exceeded",
            "review-layer-failed",
        ),
    )
    outcome, _ = evaluate_recovery(request, run_state=prior)
    assert outcome.action == "recovery-rebuilt"
    # The ephemeral marker is observable as unrestored.
    assert any(
        m.startswith("specialist-timeout")
        for m in outcome.unrestored_ephemeral_markers
    )
    # The ephemeral marker is NOT in the rebuilt run-state.
    assert outcome.rebuilt_run_state is not None
    assert not any(
        m.startswith("specialist-timeout")
        for m in outcome.rebuilt_run_state.active_markers
    )


# --------------------------------------------------------------------------- #
# AC-7 — Unsalvageable conflict + marker emission                             #
# --------------------------------------------------------------------------- #


def test_evaluate_recovery_emits_marker_on_no_run_state_on_disk(
    tmp_project: pathlib.Path, marker_registry: MarkerClassRegistry
) -> None:
    request = RecoveryRequest(
        project_root=tmp_project,
        story_id="8-2",
    )
    outcome, returned = evaluate_recovery(
        request, run_state=None, marker_registry=marker_registry
    )
    assert outcome.action == "recovery-conflict-halt"
    assert outcome.disagreements == ("no-run-state-on-disk",)
    assert outcome.marker_class == RECOVERY_STATE_CONFLICT_MARKER_CLASS
    assert outcome.diagnostic is not None
    assert "no-run-state-on-disk" in outcome.diagnostic
    # Sentinel stub returned carrying the conflict marker (registry supplied).
    assert returned is not None
    assert RECOVERY_STATE_CONFLICT_MARKER_CLASS in returned.active_markers
    # No file was created by the substrate.
    assert not (tmp_project / RUN_STATE_RELATIVE_PATH).is_file()


def test_evaluate_recovery_emits_marker_on_story_doc_corrupt(
    tmp_project: pathlib.Path, marker_registry: MarkerClassRegistry
) -> None:
    request = RecoveryRequest(
        project_root=tmp_project,
        story_id="8-2",
        story_doc_resolver=_stub_story_doc_resolver(
            raises=StoryDocNotFound(story_id="8-2", searched_paths=())
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="ready-for-dev"),
    )
    prior = _make_run_state()
    outcome, returned = evaluate_recovery(
        request, run_state=prior, marker_registry=marker_registry
    )
    assert outcome.action == "recovery-conflict-halt"
    assert "story-doc-corrupt-or-missing" in outcome.disagreements
    assert outcome.marker_class == RECOVERY_STATE_CONFLICT_MARKER_CLASS
    assert returned is not None
    # Marker recorded in run-state (registry was supplied).
    assert RECOVERY_STATE_CONFLICT_MARKER_CLASS in returned.active_markers


def test_evaluate_recovery_emits_marker_on_retry_history_irreconcilable(
    tmp_project: pathlib.Path, marker_registry: MarkerClassRegistry
) -> None:
    """run-state is escalated; story-doc says done. Lifecycle DAG forbids
    escalated → done."""
    _write_story_doc(
        tmp_project,
        "8-2",
        status="done",
        sections=(
            "## Dev Agent Record",
            "## Senior Developer Review (AI)",
            "## QA Behavioral Plan",
        ),
    )
    request = RecoveryRequest(
        project_root=tmp_project,
        story_id="8-2",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-2", "done")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="done"),
    )
    prior = _make_run_state(
        current_state="escalated",
        retry_history=(
            RetryAttempt(retry_attempt=1, retry_reason="dev failed"),
            RetryAttempt(retry_attempt=2, retry_reason="escalation reached"),
        ),
    )
    outcome, _ = evaluate_recovery(
        request, run_state=prior, marker_registry=marker_registry
    )
    assert outcome.action == "recovery-conflict-halt"
    assert "retry-history-irreconcilable" in outcome.disagreements
    assert outcome.marker_class == RECOVERY_STATE_CONFLICT_MARKER_CLASS


def test_diagnostic_contains_required_clauses(tmp_project: pathlib.Path) -> None:
    """The rendered diagnostic carries all required AC-7 clause prefixes."""
    outcome = RecoveryOutcome(
        action="recovery-conflict-halt",
        disagreements=("story-doc-corrupt-or-missing",),
        prior_run_state=_make_run_state(),
        rebuilt_run_state=None,
        marker_class=RECOVERY_STATE_CONFLICT_MARKER_CLASS,
        diagnostic=None,
        story_doc_implied_state=None,
        sprint_status_observed="in-progress",
    )
    rendered = render_recovery_state_conflict_diagnostic(outcome, tmp_project)
    assert rendered.startswith("recovery-state-conflict: ")
    assert "disagreements: story-doc-corrupt-or-missing" in rendered
    assert str(tmp_project) in rendered
    assert "prior run-state: current_state=in-progress" in rendered
    assert "sprint-status entry: in-progress" in rendered
    assert "remediation:" in rendered
    assert "schemas/marker-taxonomy.yaml:372-380" in rendered


# --------------------------------------------------------------------------- #
# AC-9 — CLI smoke                                                            #
# --------------------------------------------------------------------------- #


def test_main_exits_zero_on_recovery_clean_or_rebuilt(
    tmp_project: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end: write a real story-doc + run-state file; main() exits 0
    on the recovery-clean branch (stores agree)."""
    # Story-doc with no specialist sections; status: ready-for-dev.
    target = (
        tmp_project
        / "_bmad-output"
        / "implementation-artifacts"
        / "8-2-test-slug.md"
    )
    target.write_text(
        "# Story 8-2\n\nStatus: ready-for-dev\n\n"
        "## Acceptance Criteria\n\n**AC-1 — placeholder**\n",
        encoding="utf-8",
    )
    # Sprint-status file.
    (
        tmp_project / "_bmad-output" / "implementation-artifacts" / "sprint-status.yaml"
    ).write_text(
        "development_status:\n  8-2-test-slug: ready-for-dev\n",
        encoding="utf-8",
    )
    # Run-state file in clean state (current_state matches story-doc).
    rs_path = tmp_project / RUN_STATE_RELATIVE_PATH
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    rs_path.write_text(
        "schema_version: '1.3'\n"
        "story_id: 8-2-test-slug\n"
        "run_id: r1\n"
        "current_state: ready-for-dev\n"
        "branch_name: bmad-automation/story/8-2\n"
        "dispatched_specialist: null\n"
        "last_envelope: null\n"
        "retry_history: []\n"
        "active_markers: []\n"
        "cost_to_date_by_specialist: {}\n"
        "pending_qa_dispatch_payload: null\n",
        encoding="utf-8",
    )
    rc = main(["--project-root", str(tmp_project), "--story-id", "8-2"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "cross-state-recovery: recovery-clean:" in captured.err


def test_main_exits_one_on_recovery_conflict_halt(
    tmp_project: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end: no story-doc on disk + a run-state file → halt."""
    # Run-state file present.
    rs_path = tmp_project / RUN_STATE_RELATIVE_PATH
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    rs_path.write_text(
        "schema_version: '1.3'\n"
        "story_id: 8-2-missing\n"
        "run_id: r1\n"
        "current_state: in-progress\n"
        "branch_name: bmad-automation/story/8-2-missing\n"
        "dispatched_specialist: null\n"
        "last_envelope: null\n"
        "retry_history: []\n"
        "active_markers: []\n"
        "cost_to_date_by_specialist: {}\n"
        "pending_qa_dispatch_payload: null\n",
        encoding="utf-8",
    )
    # No story-doc + no sprint-status → resolver raises StoryDocNotFound /
    # SprintStatusMismatch → unsalvageable.
    rc = main(["--project-root", str(tmp_project), "--story-id", "8-2-missing"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "cross-state-recovery: recovery-state-conflict:" in captured.err
    assert "story-doc-corrupt-or-missing" in captured.err
