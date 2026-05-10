"""Contract-coverage matrix for the resume-command substrate (Story 8.3).

This docstring IS the contract-coverage checklist required by AC-9. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced (parallel to ``tests/test_cross_state_recovery.py`` and
``tests/test_session_start_reattach.py``).

AC-1 — Substrate library shape:
    [x] public API exposes ResumeRequest, ResumeOutcome, ResumeCommandError,
        CanDispatchInvariantViolation, evaluate_resume,
        determine_next_specialist, render_no_run_state_diagnostic, main
    [x] test_module_exports_documented_public_api
    [x] test_resume_command_classified_as_shared_substrate_by_pluggability_gate

AC-2 — No-run-state pre-check (3):
    [x] test_evaluate_resume_no_run_state_returns_resume_no_run_state
    [x] test_no_run_state_diagnostic_contains_required_clauses
    [x] test_no_run_state_does_not_invoke_evaluate_recovery

AC-3 — Recovery delegation (4):
    [x] test_evaluate_resume_clean_recovery_returns_resume_dispatch
    [x] test_evaluate_resume_rebuilt_recovery_returns_resume_dispatch
    [x] test_evaluate_resume_conflict_halt_propagates_marker
    [x] test_evaluate_resume_clean_recovery_with_terminal_state_returns_resume_already_terminal

AC-4 — Next-specialist determination (6):
    [x] test_determine_next_specialist_ready_for_dev_returns_dev
    [x] test_determine_next_specialist_in_progress_returns_review_bmad
    [x] test_determine_next_specialist_review_returns_qa
    [x] test_determine_next_specialist_qa_returns_qa
    [x] test_determine_next_specialist_terminal_returns_none
    [x] test_next_specialist_map_keys_equal_lifecycle_union

AC-5 — No-destructive guard (Story 8.6 canonical substrate consumption) (3):
    [x] test_evaluate_resume_consumes_can_dispatch_on_dispatch_path
    [x] test_evaluate_resume_raises_can_dispatch_invariant_violation_on_deny
    [x] test_evaluate_resume_carries_verdict_diagnostic_into_exception_message

AC-6 — Idempotency (3):
    [x] test_evaluate_resume_idempotent_on_clean_recovery
    [x] test_evaluate_resume_idempotent_on_no_run_state
    [x] test_evaluate_resume_rebuild_then_clean_on_subsequent_call

AC-9 — CLI smoke (3):
    [x] test_main_exits_zero_on_resume_dispatch_or_already_terminal
    [x] test_main_exits_one_on_resume_conflict_halt_or_no_run_state
    [x] test_main_exits_two_on_substrate_error

AC-3 — Substrate-error propagation (1):
    [x] test_evaluate_resume_wraps_cross_state_recovery_error_as_resume_command_error
"""

from __future__ import annotations

import pathlib
import subprocess
from typing import Any

import pytest

from loud_fail_harness import resume_command as resume_command_module
from loud_fail_harness.cross_state_recovery import (
    RUN_STATE_RELATIVE_PATH,
    CrossStateRecoveryError,
    RecoveryOutcome,
)
from loud_fail_harness.lifecycle_state_machine import (
    LIFECYCLE_TRANSITIONS,
    TERMINAL_STATES,
)
from loud_fail_harness.orchestrator_run_entry import (
    AcceptanceCriterion,
    SprintStatusResolution,
    StoryDocResolution,
)
from loud_fail_harness.no_destructive_resume_guard import Verdict
from loud_fail_harness.resume_command import (
    CanDispatchInvariantViolation,
    ResumeCommandError,
    ResumeRequest,
    _NEXT_SPECIALIST_BY_STATE,
    determine_next_specialist,
    evaluate_resume,
    main,
    render_no_run_state_diagnostic,
)
from loud_fail_harness.run_state import CostToDateBySpecialist, RunState
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
        "story_id": "8-3-test",
        "run_id": "r1",
        "current_state": "in-progress",
        "branch_name": "bmad-automation/story/8-3-test",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": (),
        "active_markers": (),
        "cost_to_date_by_specialist": CostToDateBySpecialist(),
    }
    base.update(overrides)
    return RunState.model_validate(base)


def _write_run_state_yaml(
    project_root: pathlib.Path,
    *,
    story_id: str = "8-3-test-slug",
    current_state: str = "in-progress",
    branch_name: str = "bmad-automation/story/8-3",
    run_id: str = "r1",
    dispatched_specialist: str | None = None,
    active_markers: tuple[str, ...] = (),
) -> pathlib.Path:
    rs_path = project_root / RUN_STATE_RELATIVE_PATH
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    dispatched_yaml = (
        f"'{dispatched_specialist}'" if dispatched_specialist is not None else "null"
    )
    markers_yaml = "[]" if not active_markers else (
        "[" + ", ".join(f"'{m}'" for m in active_markers) + "]"
    )
    rs_path.write_text(
        f"schema_version: '1.3'\n"
        f"story_id: {story_id}\n"
        f"run_id: {run_id}\n"
        f"current_state: {current_state}\n"
        f"branch_name: {branch_name}\n"
        f"dispatched_specialist: {dispatched_yaml}\n"
        f"last_envelope: null\n"
        f"retry_history: []\n"
        f"active_markers: {markers_yaml}\n"
        f"cost_to_date_by_specialist: {{}}\n"
        f"pending_qa_dispatch_payload: null\n",
        encoding="utf-8",
    )
    return rs_path


def _make_resolution(
    project_root: pathlib.Path, story_id: str, current_state: str
) -> StoryDocResolution:
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
    def _resolver(story_id: str, project_root: pathlib.Path) -> StoryDocResolution:
        if raises is not None:
            raise raises
        assert resolution is not None
        return resolution

    return _resolver


def _stub_sprint_status_resolver(
    state: str | None = None, raises: BaseException | None = None
):
    def _resolver(
        story_id: str, project_root: pathlib.Path
    ) -> SprintStatusResolution:
        if raises is not None:
            raise raises
        assert state is not None
        return SprintStatusResolution(current_state=state)  # type: ignore[arg-type]

    return _resolver


# --------------------------------------------------------------------------- #
# AC-1 — Module-level invariants                                              #
# --------------------------------------------------------------------------- #


def test_module_exports_documented_public_api() -> None:
    """The module's __all__ enumerates the documented AC-1 public API."""
    expected = {
        "CanDispatchInvariantViolation",
        "ResumeCommandError",
        "ResumeOutcome",
        "ResumeRequest",
        "determine_next_specialist",
        "evaluate_resume",
        "main",
        "render_no_run_state_diagnostic",
    }
    assert set(resume_command_module.__all__) == expected


def test_can_dispatch_invariant_violation_marker_class_is_none() -> None:
    """CanDispatchInvariantViolation.marker_class is None per Pattern 5
    (programmer-error invariant; no marker emission on substrate bugs)."""
    assert CanDispatchInvariantViolation.marker_class is None


def test_resume_command_classified_as_shared_substrate_by_pluggability_gate(
    tmp_project: pathlib.Path,
) -> None:
    """The pluggability gate scans agents/*.md only; resume_command.py lives
    under tools/loud-fail-harness/src/ as shared substrate AND is therefore
    NOT enumerated by the gate's diagnostic surface.

    Mirrors Story 8.1 / 8.2 substrate-library posture: the gate's
    no-cross-references rule applies to specialist subagents under
    ``agents/``; substrate libraries under ``tools/`` are out-of-scope by
    construction.
    """
    from loud_fail_harness.pluggability_gate import run_pluggability_gate

    inner_repo = pathlib.Path(__file__).resolve().parents[3]
    agents_dir = inner_repo / "agents"
    if not agents_dir.is_dir():
        pytest.skip("agents/ directory not present in this checkout")
    result = run_pluggability_gate(agents_dir)
    # The gate result MAY contain diagnostics about specialist subagents
    # depending on epic-state, but MUST NOT mention resume_command.
    diagnostics_text = "\n".join(getattr(result, "violations", []) or [])
    assert "resume_command" not in diagnostics_text


# --------------------------------------------------------------------------- #
# AC-2 — No-run-state pre-check                                               #
# --------------------------------------------------------------------------- #


def test_evaluate_resume_no_run_state_returns_resume_no_run_state(
    tmp_project: pathlib.Path,
) -> None:
    request = ResumeRequest(project_root=tmp_project, story_id="8-3-missing")
    outcome, returned = evaluate_resume(request, marker_registry=None)
    assert outcome.action == "resume-no-run-state"
    assert outcome.next_specialist is None
    assert outcome.final_run_state is None
    assert outcome.recovery_outcome is None
    assert outcome.marker_class is None
    assert outcome.diagnostic is not None
    assert outcome.pre_dispatch_can_dispatch_verdict is None
    assert returned is None


def test_no_run_state_diagnostic_contains_required_clauses(
    tmp_project: pathlib.Path,
) -> None:
    request = ResumeRequest(project_root=tmp_project, story_id="8-3-needle")
    run_state_path = tmp_project / RUN_STATE_RELATIVE_PATH
    diagnostic = render_no_run_state_diagnostic(request, run_state_path)
    assert diagnostic.startswith("resume: ")
    assert "no-in-flight-run-found-for-story-id" in diagnostic
    assert "8-3-needle" in diagnostic
    assert str(run_state_path) in diagnostic
    assert "remediation:" in diagnostic
    assert "/bmad-automation run 8-3-needle" in diagnostic
    assert "sprint-status.yaml" in diagnostic
    assert "/bmad-automation status" in diagnostic
    # NOT a recovery-state-conflict marker prefix.
    assert not diagnostic.startswith("recovery-state-conflict: ")


def test_no_run_state_does_not_invoke_evaluate_recovery(
    tmp_project: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asserts the no-run-state pre-check short-circuits BEFORE the recovery
    substrate is invoked. We monkeypatch ``evaluate_recovery`` (as referenced
    by ``resume_command``) to raise on any call."""
    invocations: list[Any] = []

    def _exploding_evaluate_recovery(*args: Any, **kwargs: Any) -> Any:
        invocations.append((args, kwargs))
        raise AssertionError("evaluate_recovery must NOT be invoked on the "
                             "no-run-state pre-check path")

    monkeypatch.setattr(
        resume_command_module,
        "evaluate_recovery",
        _exploding_evaluate_recovery,
    )
    request = ResumeRequest(project_root=tmp_project, story_id="8-3-no-rs")
    outcome, _ = evaluate_resume(request, marker_registry=None)
    assert outcome.action == "resume-no-run-state"
    assert invocations == []


# --------------------------------------------------------------------------- #
# AC-3 — Recovery delegation                                                  #
# --------------------------------------------------------------------------- #


def test_evaluate_resume_clean_recovery_returns_resume_dispatch(
    tmp_project: pathlib.Path,
) -> None:
    _write_story_doc(tmp_project, "8-3", status="ready-for-dev", sections=())
    _write_run_state_yaml(
        tmp_project,
        story_id="8-3-test-slug",
        current_state="ready-for-dev",
    )
    request = ResumeRequest(
        project_root=tmp_project,
        story_id="8-3",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-3", "ready-for-dev")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="ready-for-dev"),
    )
    outcome, returned = evaluate_resume(request, marker_registry=None)
    assert outcome.action == "resume-dispatch"
    assert outcome.next_specialist == "dev"
    assert outcome.final_run_state is not None
    assert outcome.recovery_outcome is not None
    assert outcome.recovery_outcome.action == "recovery-clean"
    assert outcome.marker_class is None
    assert outcome.diagnostic is None
    assert outcome.pre_dispatch_can_dispatch_verdict is True
    assert returned is outcome.final_run_state


def test_evaluate_resume_rebuilt_recovery_returns_resume_dispatch(
    tmp_project: pathlib.Path,
) -> None:
    """run-state says in-progress; story-doc-implied is review → rebuild;
    next_specialist follows the rebuilt current_state (review → qa)."""
    _write_story_doc(
        tmp_project,
        "8-3",
        status="review",
        sections=("## Dev Agent Record", "## Senior Developer Review (AI)"),
    )
    _write_run_state_yaml(
        tmp_project,
        story_id="8-3-test-slug",
        current_state="in-progress",
    )
    captured_writes: list[Any] = []

    def stub_writer(p: pathlib.Path, s: RunState) -> None:
        captured_writes.append((p, s))

    request = ResumeRequest(
        project_root=tmp_project,
        story_id="8-3",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-3", "review")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="review"),
        run_state_writer=stub_writer,
    )
    outcome, _ = evaluate_resume(request, marker_registry=None)
    assert outcome.action == "resume-dispatch"
    assert outcome.next_specialist == "qa"
    assert outcome.recovery_outcome is not None
    assert outcome.recovery_outcome.action == "recovery-rebuilt"
    assert "lifecycle-state-mismatch" in outcome.recovery_outcome.disagreements
    # Writer DI seam threaded through.
    assert len(captured_writes) == 1
    assert outcome.pre_dispatch_can_dispatch_verdict is True


def test_evaluate_resume_conflict_halt_propagates_marker(
    tmp_project: pathlib.Path, marker_registry: MarkerClassRegistry
) -> None:
    """Story-doc resolver raises StoryDocNotFound → unsalvageable
    recovery-state-conflict; the resume substrate propagates the verdict."""
    from loud_fail_harness.orchestrator_run_entry import StoryDocNotFound

    _write_run_state_yaml(tmp_project, story_id="8-3-conflict")
    request = ResumeRequest(
        project_root=tmp_project,
        story_id="8-3-conflict",
        story_doc_resolver=_stub_story_doc_resolver(
            raises=StoryDocNotFound(story_id="8-3-conflict", searched_paths=())
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="in-progress"),
    )
    outcome, returned = evaluate_resume(
        request, marker_registry=marker_registry
    )
    assert outcome.action == "resume-conflict-halt"
    assert outcome.next_specialist is None
    assert outcome.marker_class == "recovery-state-conflict"
    assert outcome.diagnostic is not None
    assert outcome.diagnostic.startswith("recovery-state-conflict: ")
    assert outcome.pre_dispatch_can_dispatch_verdict is None
    assert returned is not None
    # Marker carried in run-state by 8.2's emission (registry was supplied).
    assert "recovery-state-conflict" in returned.active_markers


def test_evaluate_resume_clean_recovery_with_terminal_state_returns_resume_already_terminal(
    tmp_project: pathlib.Path,
) -> None:
    _write_story_doc(
        tmp_project,
        "8-3",
        status="done",
        sections=(
            "## Dev Agent Record",
            "## Senior Developer Review (AI)",
            "## QA Behavioral Plan",
        ),
    )
    _write_run_state_yaml(
        tmp_project, story_id="8-3-test-slug", current_state="done"
    )
    request = ResumeRequest(
        project_root=tmp_project,
        story_id="8-3",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-3", "done")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="done"),
    )
    outcome, _ = evaluate_resume(request, marker_registry=None)
    assert outcome.action == "resume-already-terminal"
    assert outcome.next_specialist is None
    assert outcome.final_run_state is not None
    assert outcome.final_run_state.current_state == "done"
    assert outcome.recovery_outcome is not None
    assert outcome.recovery_outcome.action == "recovery-clean"
    assert outcome.pre_dispatch_can_dispatch_verdict is None


# --------------------------------------------------------------------------- #
# AC-4 — Next-specialist determination                                        #
# --------------------------------------------------------------------------- #


def test_determine_next_specialist_ready_for_dev_returns_dev() -> None:
    assert determine_next_specialist("ready-for-dev") == "dev"


def test_determine_next_specialist_in_progress_returns_review_bmad() -> None:
    assert determine_next_specialist("in-progress") == "review-bmad"


def test_determine_next_specialist_review_returns_qa() -> None:
    assert determine_next_specialist("review") == "qa"


def test_determine_next_specialist_qa_returns_qa() -> None:
    assert determine_next_specialist("qa") == "qa"


def test_determine_next_specialist_terminal_returns_none() -> None:
    assert determine_next_specialist("done") is None
    assert determine_next_specialist("escalated") is None


def test_next_specialist_map_keys_equal_lifecycle_union() -> None:
    """Structural-equality assertion: adding a new lifecycle state to
    ``LIFECYCLE_TRANSITIONS`` without updating ``_NEXT_SPECIALIST_BY_STATE``
    fails THIS test loud. Mirrors Story 2.4's lifecycle-extension protocol."""
    assert set(_NEXT_SPECIALIST_BY_STATE.keys()) == (
        set(LIFECYCLE_TRANSITIONS.keys()) | TERMINAL_STATES
    )
    # Each non-None value is a member of the closed specialist enum.
    for value in _NEXT_SPECIALIST_BY_STATE.values():
        if value is not None:
            assert value in {"dev", "review-bmad", "qa"}


# --------------------------------------------------------------------------- #
# AC-5 — No-destructive guard (Story 8.6 canonical substrate consumption)     #
# --------------------------------------------------------------------------- #


def test_evaluate_resume_consumes_can_dispatch_on_dispatch_path(
    tmp_project: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert ``evaluate_resume`` consumes the canonical
    :func:`no_destructive_resume_guard.can_dispatch` on the dispatch
    path. We monkeypatch ``can_dispatch`` (as referenced by
    ``resume_command``) and capture the call arguments."""
    _write_story_doc(tmp_project, "8-3", status="ready-for-dev", sections=())
    _write_run_state_yaml(
        tmp_project,
        story_id="8-3-test-slug",
        current_state="ready-for-dev",
    )

    captured: list[tuple[Any, ...]] = []

    def _spy_can_dispatch(specialist: Any, story_id: Any, run_state: Any) -> Verdict:
        captured.append((specialist, story_id, run_state))
        return Verdict(allow=True)

    monkeypatch.setattr(resume_command_module, "can_dispatch", _spy_can_dispatch)

    request = ResumeRequest(
        project_root=tmp_project,
        story_id="8-3",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-3", "ready-for-dev")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="ready-for-dev"),
    )
    outcome, _ = evaluate_resume(request, marker_registry=None)

    assert outcome.action == "resume-dispatch"
    assert outcome.pre_dispatch_can_dispatch_verdict is True
    # Exactly one consumption with (next_specialist, request.story_id, final_run_state).
    assert len(captured) == 1
    spec_arg, story_arg, run_state_arg = captured[0]
    assert spec_arg == "dev"
    assert story_arg == "8-3"
    assert run_state_arg.current_state == "ready-for-dev"


def test_evaluate_resume_raises_can_dispatch_invariant_violation_on_deny(
    tmp_project: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the canonical guard returns ``Verdict(allow=False, ...)``
    on a path 8.2's evaluate_recovery cleared, the resume substrate
    raises CanDispatchInvariantViolation per AC-4's raise-site rewrite."""
    _write_run_state_yaml(tmp_project, story_id="8-3-conflict-stub")

    rebuilt_run_state = _make_run_state(
        story_id="8-3-conflict-stub",
        current_state="ready-for-dev",
        dispatched_specialist="dev",
        last_envelope={"specialist": "dev", "status": "completed"},
    )

    def _stub_evaluate_recovery(*_args: Any, **_kwargs: Any):  # noqa: ANN202
        return (
            RecoveryOutcome(
                action="recovery-clean",
                disagreements=(),
                prior_run_state=rebuilt_run_state,
                rebuilt_run_state=rebuilt_run_state,
                story_doc_implied_state="ready-for-dev",
                sprint_status_observed="ready-for-dev",
            ),
            rebuilt_run_state,
        )

    monkeypatch.setattr(
        resume_command_module, "evaluate_recovery", _stub_evaluate_recovery
    )

    request = ResumeRequest(
        project_root=tmp_project,
        story_id="8-3-conflict-stub",
    )
    with pytest.raises(CanDispatchInvariantViolation) as exc_info:
        evaluate_resume(request, marker_registry=None)
    # Per AC-4 the raise-site rewrite uses
    # reason="can-dispatch-deny-on-recovered-state".
    assert exc_info.value.reason == "can-dispatch-deny-on-recovered-state"


def test_evaluate_resume_carries_verdict_diagnostic_into_exception_message(
    tmp_project: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The canonical guard's structured DenyReason and human-readable
    diagnostic are surfaced via the rewritten exception message — so
    automated triage tooling can parse Verdict.reason as enum + the
    diagnostic without re-running the guard."""
    _write_run_state_yaml(tmp_project, story_id="8-3-deny")

    rebuilt_run_state = _make_run_state(
        story_id="8-3-deny",
        current_state="ready-for-dev",
        dispatched_specialist="dev",
        last_envelope={"specialist": "dev", "status": "completed"},
    )

    def _stub_evaluate_recovery(*_args: Any, **_kwargs: Any):  # noqa: ANN202
        return (
            RecoveryOutcome(
                action="recovery-clean",
                disagreements=(),
                prior_run_state=rebuilt_run_state,
                rebuilt_run_state=rebuilt_run_state,
                story_doc_implied_state="ready-for-dev",
                sprint_status_observed="ready-for-dev",
            ),
            rebuilt_run_state,
        )

    monkeypatch.setattr(
        resume_command_module, "evaluate_recovery", _stub_evaluate_recovery
    )

    request = ResumeRequest(project_root=tmp_project, story_id="8-3-deny")
    with pytest.raises(CanDispatchInvariantViolation) as exc_info:
        evaluate_resume(request, marker_registry=None)
    diagnostic = exc_info.value.diagnostic
    # The rewritten exception surfaces the verdict's reason (one of the
    # four DenyReason literals) AND the verdict's diagnostic.
    assert "reason=prior-output-recorded" in diagnostic
    assert "8-3-deny" in diagnostic
    assert "'dev'" in diagnostic


# --------------------------------------------------------------------------- #
# AC-6 — Idempotency                                                          #
# --------------------------------------------------------------------------- #


def test_evaluate_resume_idempotent_on_clean_recovery(
    tmp_project: pathlib.Path,
) -> None:
    _write_story_doc(tmp_project, "8-3", status="ready-for-dev", sections=())
    _write_run_state_yaml(
        tmp_project, story_id="8-3-test-slug", current_state="ready-for-dev"
    )

    def make_request() -> ResumeRequest:
        return ResumeRequest(
            project_root=tmp_project,
            story_id="8-3",
            story_doc_resolver=_stub_story_doc_resolver(
                _make_resolution(tmp_project, "8-3", "ready-for-dev")
            ),
            sprint_status_resolver=_stub_sprint_status_resolver(
                state="ready-for-dev"
            ),
        )

    first, _ = evaluate_resume(make_request(), marker_registry=None)
    second, _ = evaluate_resume(make_request(), marker_registry=None)
    assert first.action == second.action == "resume-dispatch"
    assert first.next_specialist == second.next_specialist == "dev"
    assert first.marker_class == second.marker_class is None
    assert (
        first.final_run_state is not None
        and second.final_run_state is not None
        and first.final_run_state.current_state
        == second.final_run_state.current_state
    )


def test_evaluate_resume_idempotent_on_no_run_state(
    tmp_project: pathlib.Path,
) -> None:
    request = ResumeRequest(project_root=tmp_project, story_id="8-3-absent")
    first, _ = evaluate_resume(request, marker_registry=None)
    second, _ = evaluate_resume(request, marker_registry=None)
    assert first.action == second.action == "resume-no-run-state"
    assert first.diagnostic == second.diagnostic


def test_evaluate_resume_rebuild_then_clean_on_subsequent_call(
    tmp_project: pathlib.Path,
) -> None:
    """First call rebuilds (run-state lifecycle != story-doc); the writer
    persists the rebuilt run-state to disk; the second call against the
    same disk state yields recovery-clean."""
    _write_story_doc(
        tmp_project,
        "8-3",
        status="review",
        sections=("## Dev Agent Record", "## Senior Developer Review (AI)"),
    )
    _write_run_state_yaml(
        tmp_project, story_id="8-3-test-slug", current_state="in-progress"
    )

    # Capture rebuilt state so we can re-write it (simulating the writer's
    # on-disk persistence).
    captured_writes: list[RunState] = []

    def stub_writer(p: pathlib.Path, s: RunState) -> None:
        captured_writes.append(s)

    request = ResumeRequest(
        project_root=tmp_project,
        story_id="8-3",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-3", "review")
        ),
        sprint_status_resolver=_stub_sprint_status_resolver(state="review"),
        run_state_writer=stub_writer,
    )
    first, _ = evaluate_resume(request, marker_registry=None)
    assert first.action == "resume-dispatch"
    assert first.recovery_outcome is not None
    assert first.recovery_outcome.action == "recovery-rebuilt"
    assert len(captured_writes) == 1

    # Persist the rebuilt run-state to disk so the second call observes
    # the rebuilt cache (parallels the production writer's invariant).
    rebuilt = captured_writes[0]
    rs_path = tmp_project / RUN_STATE_RELATIVE_PATH
    # Render minimal YAML for the rebuilt instance.
    rs_path.write_text(
        f"schema_version: '{rebuilt.schema_version}'\n"
        f"story_id: {rebuilt.story_id}\n"
        f"run_id: {rebuilt.run_id}\n"
        f"current_state: {rebuilt.current_state}\n"
        f"branch_name: {rebuilt.branch_name}\n"
        f"dispatched_specialist: null\n"
        f"last_envelope: null\n"
        f"retry_history: []\n"
        f"active_markers: []\n"
        f"cost_to_date_by_specialist: {{}}\n"
        f"pending_qa_dispatch_payload: null\n",
        encoding="utf-8",
    )

    second, _ = evaluate_resume(request, marker_registry=None)
    assert second.action == "resume-dispatch"
    assert second.next_specialist == first.next_specialist
    assert second.recovery_outcome is not None
    assert second.recovery_outcome.action == "recovery-clean"


# --------------------------------------------------------------------------- #
# AC-3 — Substrate-error propagation                                          #
# --------------------------------------------------------------------------- #


def test_evaluate_resume_wraps_cross_state_recovery_error_as_resume_command_error(
    tmp_project: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``evaluate_recovery`` raises ``CrossStateRecoveryError``, the
    resume substrate re-raises it as ``ResumeCommandError`` per Pattern 5
    chained-exception discipline."""
    _write_run_state_yaml(tmp_project, story_id="8-3-error")

    def _raising_evaluate_recovery(*_args: Any, **_kwargs: Any) -> Any:
        raise CrossStateRecoveryError(
            reason="story-doc-resolver-unexpected-exception",
            diagnostic="story_doc_resolver raised KeyError('test')",
        )

    monkeypatch.setattr(
        resume_command_module, "evaluate_recovery", _raising_evaluate_recovery
    )

    request = ResumeRequest(project_root=tmp_project, story_id="8-3-error")
    with pytest.raises(ResumeCommandError) as exc_info:
        evaluate_resume(request, marker_registry=None)
    assert exc_info.value.reason == "cross-state-recovery-substrate-error"
    assert isinstance(exc_info.value.__cause__, CrossStateRecoveryError)


# --------------------------------------------------------------------------- #
# AC-9 — CLI smoke                                                            #
# --------------------------------------------------------------------------- #


def test_main_exits_zero_on_resume_dispatch_or_already_terminal(
    tmp_project: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end: real story-doc + real run-state → main() exits 0 on
    resume-dispatch."""
    target = (
        tmp_project
        / "_bmad-output"
        / "implementation-artifacts"
        / "8-3-test-slug.md"
    )
    target.write_text(
        "# Story 8-3\n\nStatus: ready-for-dev\n\n"
        "## Acceptance Criteria\n\n**AC-1 — placeholder**\n",
        encoding="utf-8",
    )
    (
        tmp_project / "_bmad-output" / "implementation-artifacts" / "sprint-status.yaml"
    ).write_text(
        "development_status:\n  8-3-test-slug: ready-for-dev\n",
        encoding="utf-8",
    )
    _write_run_state_yaml(
        tmp_project,
        story_id="8-3-test-slug",
        current_state="ready-for-dev",
    )
    rc = main(["8-3", "--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "resume: resume-dispatch:" in captured.err
    assert "next_specialist=dev" in captured.err

    # Terminal-state path: same fixture but advance current_state to done.
    target.write_text(
        "# Story 8-3\n\nStatus: done\n\n"
        "## Acceptance Criteria\n\n**AC-1 — placeholder**\n\n"
        "## Dev Agent Record\n\nbody.\n\n"
        "## Senior Developer Review (AI)\n\nbody.\n\n"
        "## QA Behavioral Plan\n\nbody.\n",
        encoding="utf-8",
    )
    (
        tmp_project / "_bmad-output" / "implementation-artifacts" / "sprint-status.yaml"
    ).write_text(
        "development_status:\n  8-3-test-slug: done\n",
        encoding="utf-8",
    )
    _write_run_state_yaml(
        tmp_project,
        story_id="8-3-test-slug",
        current_state="done",
    )
    rc = main(["8-3", "--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "resume: resume-already-terminal:" in captured.err


def test_main_exits_one_on_resume_conflict_halt_or_no_run_state(
    tmp_project: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # No run-state → resume-no-run-state, exit 1.
    rc = main(["8-3-absent", "--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "resume:" in captured.err
    assert "no-in-flight-run-found-for-story-id" in captured.err

    # Run-state present + no story-doc → recovery-conflict-halt → exit 1.
    _write_run_state_yaml(tmp_project, story_id="8-3-noop", current_state="in-progress")
    rc = main(["8-3-noop", "--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "resume: recovery-state-conflict:" in captured.err


def test_main_exits_two_on_substrate_error(
    tmp_project: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_run_state_yaml(tmp_project, story_id="8-3-fail")

    def _raising_evaluate_recovery(*_args: Any, **_kwargs: Any) -> Any:
        raise CrossStateRecoveryError(
            reason="story-doc-resolver-unexpected-exception",
            diagnostic="resolver raised TypeError",
        )

    monkeypatch.setattr(
        resume_command_module, "evaluate_recovery", _raising_evaluate_recovery
    )
    rc = main(["8-3-fail", "--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "harness-level error" in captured.err
