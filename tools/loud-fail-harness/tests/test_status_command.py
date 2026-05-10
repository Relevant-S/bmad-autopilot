"""Contract-coverage matrix for the status-command substrate (Story 8.4).

This docstring IS the contract-coverage checklist required by AC-9. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced (parallel to ``tests/test_resume_command.py`` and
``tests/test_cross_state_recovery.py``).

AC-1 — Module-level invariants:
    [x] test_module_exports_documented_public_api
    [x] test_status_command_classified_as_shared_substrate_by_pluggability_gate

AC-2 — No-run-state pre-check (3):
    [x] test_inspect_story_no_run_state_returns_status_no_run_state
    [x] test_no_run_state_diagnostic_contains_required_clauses
    [x] test_no_run_state_does_not_invoke_load_run_state_from_disk

AC-2 — TOCTOU + OSError guards (2):
    [x] test_inspect_story_toctou_returns_status_no_run_state
    [x] test_inspect_story_oserror_on_is_file_raises_status_command_error

AC-3 — Inspection assembly (5):
    [x] test_inspect_story_status_found_basic_fields
    [x] test_inspect_story_resolve_retry_rounds_false_returns_none
    [x] test_inspect_story_resolve_retry_rounds_true_resolves_populated_refs
    [x] test_inspect_story_resolve_retry_rounds_skips_pre_5_5_entries
    [x] test_inspect_story_dangling_refs_surface_structurally

AC-3 — Story-doc resolver graceful-degrade (1):
    [x] test_inspect_story_resolver_failure_yields_none_story_doc_path

AC-4 — Human render (3):
    [x] test_render_story_inspection_human_contains_required_sections
    [x] test_render_human_byte_stable_on_identical_input
    [x] test_render_human_handles_empty_markers_and_retries

AC-5 — JSON render (2):
    [x] test_render_story_inspection_json_round_trip_stable
    [x] test_render_json_byte_stable_on_identical_input

AC-6 — Read-only invariant (2):
    [x] test_inspect_story_does_not_mutate_run_state_file
    [x] test_status_command_has_no_write_surfaces

AC-9 — CLI smoke (4):
    [x] test_main_exits_zero_on_status_found
    [x] test_main_exits_zero_on_status_found_with_json_flag
    [x] test_main_exits_one_on_status_no_run_state
    [x] test_main_exits_two_on_substrate_error

AC-3 — Substrate-error propagation (1):
    [x] test_inspect_story_wraps_cross_state_recovery_error_as_status_command_error

AC-9 — Story 8.5 projection-discipline contract (1):
    [x] test_story_inspection_payload_supports_8_5_projection_shape
"""

from __future__ import annotations

import ast
import hashlib
import inspect as _inspect
import json
import pathlib
import subprocess
from typing import Any

import pytest

from loud_fail_harness import status_command as status_command_module
from loud_fail_harness.cross_state_recovery import (
    RUN_STATE_RELATIVE_PATH,
    CrossStateRecoveryError,
)
from loud_fail_harness.orchestrator_run_entry import (
    AcceptanceCriterion,
    StoryDocNotFound,
    StoryDocResolution,
)
from loud_fail_harness.retry_history import (
    RetryAttemptRef,
    RetryRoundArtifacts,
    persist_retry_round,
)
from loud_fail_harness.run_state import CostToDateBySpecialist, RunState
from loud_fail_harness.status_command import (
    StatusCommandError,
    StatusRequest,
    StoryInspection,
    inspect_story,
    main,
    render_no_run_state_diagnostic,
    render_story_inspection_human,
    render_story_inspection_json,
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
    """Create a fresh tmp_path-rooted git repo with the canonical
    BMAD project layout. Mirrors ``tests/test_resume_command.py``'s
    ``tmp_project`` fixture (Story 8.3 precedent — same Epic 8 cohort).
    """
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


def _write_run_state_yaml(
    project_root: pathlib.Path,
    *,
    story_id: str = "8-4-test-slug",
    current_state: str = "in-progress",
    branch_name: str = "bmad-automation/story/8-4",
    run_id: str = "r1",
    dispatched_specialist: str | None = None,
    last_envelope_yaml: str = "null",
    active_markers: tuple[str, ...] = (),
    retry_history_yaml: str = "[]",
) -> pathlib.Path:
    rs_path = project_root / RUN_STATE_RELATIVE_PATH
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    dispatched_yaml = (
        f"'{dispatched_specialist}'" if dispatched_specialist is not None else "null"
    )
    markers_yaml = (
        "[]"
        if not active_markers
        else "[" + ", ".join(f"'{m}'" for m in active_markers) + "]"
    )
    rs_path.write_text(
        f"schema_version: '1.3'\n"
        f"story_id: {story_id}\n"
        f"run_id: {run_id}\n"
        f"current_state: {current_state}\n"
        f"branch_name: {branch_name}\n"
        f"dispatched_specialist: {dispatched_yaml}\n"
        f"last_envelope: {last_envelope_yaml}\n"
        f"retry_history: {retry_history_yaml}\n"
        f"active_markers: {markers_yaml}\n"
        f"cost_to_date_by_specialist: {{}}\n"
        f"pending_qa_dispatch_payload: null\n",
        encoding="utf-8",
    )
    return rs_path


def _write_story_doc(
    project_root: pathlib.Path, story_id: str
) -> pathlib.Path:
    target = (
        project_root
        / "_bmad-output"
        / "implementation-artifacts"
        / f"{story_id}-test-slug.md"
    )
    target.write_text(
        f"# Story {story_id}\n\nStatus: in-progress\n\n"
        "## Acceptance Criteria\n\n**AC-1 — body** placeholder.\n",
        encoding="utf-8",
    )
    return target


def _make_resolution(
    project_root: pathlib.Path, story_id: str
) -> StoryDocResolution:
    path = (
        project_root
        / "_bmad-output"
        / "implementation-artifacts"
        / f"{story_id}-test-slug.md"
    )
    return StoryDocResolution(
        path=path,
        current_state="in-progress",
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


def _make_inspection(
    *,
    story_id: str = "8-4-test",
    current_state: str = "in-progress",
    branch_name: str = "bmad-automation/story/8-4",
    run_id: str = "r1",
    dispatched_specialist: str | None = None,
    last_envelope: dict[str, Any] | None = None,
    active_markers: tuple[str, ...] = (),
    retry_history: tuple[Any, ...] = (),
    resolved_retry_rounds: tuple[RetryRoundArtifacts, ...] | None = None,
    dangling_retry_round_refs: tuple[RetryAttemptRef, ...] = (),
    run_state_path: pathlib.Path | None = None,
    per_specialist_log_dir: pathlib.Path | None = None,
    story_doc_path: pathlib.Path | None = None,
    cost: CostToDateBySpecialist | None = None,
) -> StoryInspection:
    return StoryInspection(
        story_id=story_id,
        current_state=current_state,  # type: ignore[arg-type]
        branch_name=branch_name,
        run_id=run_id,
        dispatched_specialist=dispatched_specialist,  # type: ignore[arg-type]
        last_envelope=last_envelope,
        active_markers=active_markers,
        retry_history=retry_history,  # type: ignore[arg-type]
        resolved_retry_rounds=resolved_retry_rounds,
        dangling_retry_round_refs=dangling_retry_round_refs,
        run_state_path=run_state_path or pathlib.Path("/tmp/run-state.yaml"),
        per_specialist_log_dir=(
            per_specialist_log_dir or pathlib.Path("/tmp/logs")
        ),
        story_doc_path=story_doc_path,
        cost_to_date_by_specialist=cost or CostToDateBySpecialist(),
    )


# --------------------------------------------------------------------------- #
# AC-1 — Module-level invariants                                              #
# --------------------------------------------------------------------------- #


def test_module_exports_documented_public_api() -> None:
    """The module's __all__ enumerates the AC-1 public API."""
    expected = {
        "StatusCommandError",
        "StatusOutcome",
        "StatusRequest",
        "StoryInspection",
        "inspect_story",
        "main",
        "render_no_run_state_diagnostic",
        "render_story_inspection_human",
        "render_story_inspection_json",
    }
    assert set(status_command_module.__all__) == expected


def test_status_command_classified_as_shared_substrate_by_pluggability_gate(
    tmp_project: pathlib.Path,
) -> None:
    """Status_command.py lives under tools/loud-fail-harness/src/ as
    shared substrate AND is therefore NOT enumerated by the
    pluggability gate's diagnostic surface (the gate scans agents/*.md
    only). Mirrors Story 8.3's identical assertion at
    ``tests/test_resume_command.py``.
    """
    from loud_fail_harness.pluggability_gate import run_pluggability_gate

    inner_repo = pathlib.Path(__file__).resolve().parents[3]
    agents_dir = inner_repo / "agents"
    if not agents_dir.is_dir():
        pytest.skip("agents/ directory not present in this checkout")
    result = run_pluggability_gate(agents_dir)
    diagnostics_text = "\n".join(getattr(result, "violations", []) or [])
    assert "status_command" not in diagnostics_text


# --------------------------------------------------------------------------- #
# AC-2 — No-run-state pre-check                                               #
# --------------------------------------------------------------------------- #


def test_inspect_story_no_run_state_returns_status_no_run_state(
    tmp_project: pathlib.Path,
) -> None:
    request = StatusRequest(project_root=tmp_project, story_id="8-4-missing")
    outcome = inspect_story(request)
    assert outcome.action == "status-no-run-state"
    assert outcome.inspection is None
    assert outcome.diagnostic is not None


def test_no_run_state_diagnostic_contains_required_clauses(
    tmp_project: pathlib.Path,
) -> None:
    request = StatusRequest(project_root=tmp_project, story_id="8-4-needle")
    run_state_path = tmp_project / RUN_STATE_RELATIVE_PATH
    diagnostic = render_no_run_state_diagnostic(request, run_state_path)
    assert diagnostic.startswith("status: ")
    assert "no-in-flight-run-found-for-story-id" in diagnostic
    assert "8-4-needle" in diagnostic
    assert str(run_state_path) in diagnostic
    assert "remediation:" in diagnostic
    assert "/bmad-automation run 8-4-needle" in diagnostic
    assert "/bmad-automation status" in diagnostic
    # NOT a recovery-state-conflict marker prefix; NOT resume's prefix.
    assert not diagnostic.startswith("recovery-state-conflict: ")
    assert not diagnostic.startswith("resume: ")


def test_no_run_state_does_not_invoke_load_run_state_from_disk(
    tmp_project: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asserts the no-run-state pre-check short-circuits BEFORE the
    private load helper is invoked. We monkeypatch
    ``_load_run_state_from_disk`` (as referenced by ``status_command``)
    to raise on any call."""
    invocations: list[Any] = []

    def _exploding(*args: Any, **kwargs: Any) -> Any:
        invocations.append((args, kwargs))
        raise AssertionError(
            "_load_run_state_from_disk must NOT be invoked on the "
            "no-run-state pre-check path"
        )

    monkeypatch.setattr(
        status_command_module, "_load_run_state_from_disk", _exploding
    )
    request = StatusRequest(project_root=tmp_project, story_id="8-4-no-rs")
    outcome = inspect_story(request)
    assert outcome.action == "status-no-run-state"
    assert invocations == []


# --------------------------------------------------------------------------- #
# AC-2 — TOCTOU + OSError guards                                              #
# --------------------------------------------------------------------------- #


def test_inspect_story_toctou_returns_status_no_run_state(
    tmp_project: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """File deleted between is_file() and _load_run_state_from_disk
    returning None → status-no-run-state (TOCTOU guard per AC-2;
    mirrors Story 8.3's resume_command.py:~656 pattern)."""
    _write_run_state_yaml(tmp_project)

    def _toctou_load(_path: pathlib.Path) -> RunState | None:
        # Simulate the file being deleted between is_file() and
        # the load — _load_run_state_from_disk returns None per its
        # contract for the absent-file branch.
        return None

    monkeypatch.setattr(
        status_command_module, "_load_run_state_from_disk", _toctou_load
    )
    request = StatusRequest(project_root=tmp_project, story_id="8-4-toctou")
    outcome = inspect_story(request)
    assert outcome.action == "status-no-run-state"
    assert outcome.inspection is None
    assert outcome.diagnostic is not None


def test_inspect_story_oserror_on_is_file_raises_status_command_error(
    tmp_project: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Permission denied on the is_file() probe → StatusCommandError →
    CLI exit 2 (mirrors Story 8.3's identical OSError guard at
    resume_command.py:~610)."""

    class _ExplodingPath(type(pathlib.Path())):
        def is_file(self) -> bool:  # type: ignore[override]
            raise PermissionError("simulated EACCES")

    request = StatusRequest(
        project_root=tmp_project,
        story_id="8-4-os",
        run_state_path=_ExplodingPath(tmp_project / RUN_STATE_RELATIVE_PATH),
    )
    with pytest.raises(StatusCommandError) as exc_info:
        inspect_story(request)
    assert exc_info.value.reason == "run-state-path-access-error"
    assert isinstance(exc_info.value.__cause__, OSError)


# --------------------------------------------------------------------------- #
# AC-3 — Inspection assembly                                                  #
# --------------------------------------------------------------------------- #


def test_inspect_story_status_found_basic_fields(
    tmp_project: pathlib.Path,
) -> None:
    _write_story_doc(tmp_project, "8-4")
    rs_path = _write_run_state_yaml(
        tmp_project,
        story_id="8-4",
        current_state="in-progress",
        branch_name="bmad-automation/story/8-4",
        run_id="r1",
        dispatched_specialist="dev",
        last_envelope_yaml='{status: "completed", note: "x"}',
        active_markers=("review-layer-failed",),
    )
    request = StatusRequest(
        project_root=tmp_project,
        story_id="8-4",
        story_doc_resolver=_stub_story_doc_resolver(
            _make_resolution(tmp_project, "8-4")
        ),
    )
    outcome = inspect_story(request)
    assert outcome.action == "status-found"
    assert outcome.diagnostic is None
    inspection = outcome.inspection
    assert inspection is not None
    assert inspection.story_id == "8-4"
    assert inspection.current_state == "in-progress"
    assert inspection.branch_name == "bmad-automation/story/8-4"
    assert inspection.run_id == "r1"
    assert inspection.dispatched_specialist == "dev"
    assert inspection.last_envelope == {"status": "completed", "note": "x"}
    assert inspection.active_markers == ("review-layer-failed",)
    assert inspection.run_state_path == rs_path
    expected_log_dir = (
        tmp_project / "_bmad-output" / "qa-evidence" / "8-4" / "r1" / "logs"
    )
    assert inspection.per_specialist_log_dir == expected_log_dir
    assert inspection.story_doc_path is not None
    assert inspection.story_doc_path.name == "8-4-test-slug.md"


def test_inspect_story_resolve_retry_rounds_false_returns_none(
    tmp_project: pathlib.Path,
) -> None:
    _write_run_state_yaml(tmp_project)
    request = StatusRequest(
        project_root=tmp_project,
        story_id="8-4-test-slug",
        resolve_retry_rounds=False,
        story_doc_resolver=_stub_story_doc_resolver(
            raises=StoryDocNotFound(story_id="8-4-test-slug", searched_paths=())
        ),
    )
    outcome = inspect_story(request)
    assert outcome.action == "status-found"
    assert outcome.inspection is not None
    assert outcome.inspection.resolved_retry_rounds is None
    assert outcome.inspection.dangling_retry_round_refs == ()


def test_inspect_story_resolve_retry_rounds_true_resolves_populated_refs(
    tmp_project: pathlib.Path,
) -> None:
    """A populated retry_history entry whose on-disk artifact exists
    is resolved into a RetryRoundArtifacts."""
    # Persist a real retry-round artifact on disk.
    round_artifacts = RetryRoundArtifacts(
        round_id="round-01",
        retry_attempt=1,
        findings=({"id": "patch-1", "severity": "med"},),
        scope_affected_files=("src/foo.py",),
        scope_expanded_to=(),
        actual_diff_files=("src/foo.py",),
        created_at="2026-05-09T00:00:00+00:00",
    )
    ref = persist_retry_round(
        round=round_artifacts,
        repo_root=tmp_project,
        story_id="8-4",
        retry_reason="patch-bucket-retry",
    )
    # Compose run-state with one populated retry-history entry.
    retry_history_yaml = (
        "[{retry_attempt: 1, retry_reason: 'patch-bucket-retry', "
        f"round_id: 'round-01', path: '{ref.path}'}}]"
    )
    _write_run_state_yaml(tmp_project, retry_history_yaml=retry_history_yaml)
    request = StatusRequest(
        project_root=tmp_project,
        story_id="8-4-test-slug",
        resolve_retry_rounds=True,
        story_doc_resolver=_stub_story_doc_resolver(
            raises=StoryDocNotFound(story_id="8-4-test-slug", searched_paths=())
        ),
    )
    outcome = inspect_story(request)
    assert outcome.action == "status-found"
    inspection = outcome.inspection
    assert inspection is not None
    assert inspection.resolved_retry_rounds is not None
    assert len(inspection.resolved_retry_rounds) == 1
    assert inspection.resolved_retry_rounds[0].round_id == "round-01"
    assert inspection.resolved_retry_rounds[0].retry_attempt == 1
    assert inspection.dangling_retry_round_refs == ()


def test_inspect_story_resolve_retry_rounds_skips_pre_5_5_entries(
    tmp_project: pathlib.Path,
) -> None:
    """A retry_history entry where round_id and path are both None
    (pre-Story-5.5 sparse entry) is SKIPPED for ref-construction; it
    remains visible in inspection.retry_history but does NOT appear
    in resolved_retry_rounds."""
    # Pre-5.5 entry: bare retry_attempt + retry_reason, no thickened fields.
    retry_history_yaml = (
        "[{retry_attempt: 1, retry_reason: 'patch-bucket-retry'}]"
    )
    _write_run_state_yaml(tmp_project, retry_history_yaml=retry_history_yaml)
    request = StatusRequest(
        project_root=tmp_project,
        story_id="8-4-test-slug",
        resolve_retry_rounds=True,
        story_doc_resolver=_stub_story_doc_resolver(
            raises=StoryDocNotFound(story_id="8-4-test-slug", searched_paths=())
        ),
    )
    outcome = inspect_story(request)
    inspection = outcome.inspection
    assert inspection is not None
    # Pre-5.5 entry is preserved in the raw passthrough field.
    assert len(inspection.retry_history) == 1
    assert inspection.retry_history[0].round_id is None
    assert inspection.retry_history[0].path is None
    # Resolved tuple is empty (entry was skipped).
    assert inspection.resolved_retry_rounds == ()
    assert inspection.dangling_retry_round_refs == ()


def test_inspect_story_dangling_refs_surface_structurally(
    tmp_project: pathlib.Path,
) -> None:
    """A populated retry_history entry whose on-disk artifact is missing
    surfaces as dangling_retry_round_refs — NO marker emission, NO
    exception raised (per AC-10)."""
    retry_history_yaml = (
        "[{retry_attempt: 1, retry_reason: 'patch-bucket-retry', "
        "round_id: 'round-01', "
        "path: '_bmad-output/retry-history/8-4/round-01/missing.yaml'}]"
    )
    _write_run_state_yaml(tmp_project, retry_history_yaml=retry_history_yaml)
    request = StatusRequest(
        project_root=tmp_project,
        story_id="8-4-test-slug",
        resolve_retry_rounds=True,
        story_doc_resolver=_stub_story_doc_resolver(
            raises=StoryDocNotFound(story_id="8-4-test-slug", searched_paths=())
        ),
    )
    # Should NOT raise.
    outcome = inspect_story(request)
    inspection = outcome.inspection
    assert inspection is not None
    assert len(inspection.dangling_retry_round_refs) == 1
    assert inspection.dangling_retry_round_refs[0].round_id == "round-01"
    # Resolved tuple is empty (the only ref was dangling).
    assert inspection.resolved_retry_rounds == ()


# --------------------------------------------------------------------------- #
# AC-3 — Story-doc resolver graceful-degrade                                  #
# --------------------------------------------------------------------------- #


def test_inspect_story_resolver_failure_yields_none_story_doc_path(
    tmp_project: pathlib.Path,
) -> None:
    _write_run_state_yaml(tmp_project)
    request = StatusRequest(
        project_root=tmp_project,
        story_id="8-4-test-slug",
        story_doc_resolver=_stub_story_doc_resolver(
            raises=StoryDocNotFound(story_id="8-4-test-slug", searched_paths=())
        ),
    )
    outcome = inspect_story(request)
    assert outcome.action == "status-found"
    assert outcome.inspection is not None
    assert outcome.inspection.story_doc_path is None


# --------------------------------------------------------------------------- #
# AC-3 — Substrate-error propagation                                          #
# --------------------------------------------------------------------------- #


def test_inspect_story_wraps_cross_state_recovery_error_as_status_command_error(
    tmp_project: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When _load_run_state_from_disk raises CrossStateRecoveryError,
    the status substrate re-raises it as StatusCommandError per Pattern 5
    chained-exception discipline."""
    _write_run_state_yaml(tmp_project)

    def _raising(_path: pathlib.Path) -> RunState | None:
        raise CrossStateRecoveryError(
            reason="run-state-parse-failure",
            diagnostic="simulated YAML parse error",
            path=tmp_project / RUN_STATE_RELATIVE_PATH,
        )

    monkeypatch.setattr(
        status_command_module, "_load_run_state_from_disk", _raising
    )
    request = StatusRequest(project_root=tmp_project, story_id="8-4-broken")
    with pytest.raises(StatusCommandError) as exc_info:
        inspect_story(request)
    assert exc_info.value.reason == "cross-state-recovery-substrate-error"
    assert isinstance(exc_info.value.__cause__, CrossStateRecoveryError)


# --------------------------------------------------------------------------- #
# AC-4 — Human render                                                         #
# --------------------------------------------------------------------------- #


def test_render_story_inspection_human_contains_required_sections() -> None:
    inspection = _make_inspection(
        active_markers=("review-layer-failed", "bundle-assembly-failed"),
        last_envelope={"status": "completed", "note": "x"},
        dispatched_specialist="dev",
    )
    rendered = render_story_inspection_human(inspection)
    # AC-4 required headings (in order).
    headings = [
        "# /bmad-automation status — story 8-4-test",
        "## Lifecycle state",
        "## Active loud-fail markers",
        "## Retry history",
        "## Latest specialist envelope",
        "## Cost-to-date by specialist",
    ]
    last_idx = -1
    for heading in headings:
        idx = rendered.find(heading)
        assert idx > last_idx, (
            f"heading {heading!r} not found in order; rendered=\n{rendered}"
        )
        last_idx = idx
    # Lifecycle state fields.
    assert "state: in-progress" in rendered
    assert "branch: bmad-automation/story/8-4" in rendered
    assert "run_id: r1" in rendered
    assert "run_state_path: " in rendered
    assert "story_doc: (unresolved)" in rendered
    # Markers rendered alphabetically.
    bundle_idx = rendered.index("bundle-assembly-failed")
    review_idx = rendered.index("review-layer-failed")
    assert bundle_idx < review_idx, (
        "markers must render in alphabetical order via "
        "compute_alphabetical_marker_order"
    )
    # Latest specialist envelope.
    assert "dispatched_specialist: dev" in rendered
    assert "envelope_status: completed" in rendered
    assert "per_specialist_log_dir: " in rendered
    # Cost-to-date.
    assert "- dev: " in rendered
    assert "- review-bmad: " in rendered
    assert "- qa: " in rendered
    assert "- lad: " in rendered


def test_render_human_byte_stable_on_identical_input() -> None:
    inspection = _make_inspection(
        active_markers=("a", "b"),
        last_envelope={"status": "ok"},
    )
    a = render_story_inspection_human(inspection)
    b = render_story_inspection_human(inspection)
    assert a == b


def test_render_human_handles_empty_markers_and_retries() -> None:
    inspection = _make_inspection(active_markers=(), retry_history=())
    rendered = render_story_inspection_human(inspection)
    assert "(no active markers)" in rendered
    assert "(no retries — story has not entered the retry seam)" in rendered


# --------------------------------------------------------------------------- #
# AC-5 — JSON render                                                          #
# --------------------------------------------------------------------------- #


def test_render_story_inspection_json_round_trip_stable() -> None:
    inspection = _make_inspection(
        active_markers=("a", "b"),
        last_envelope={"status": "ok"},
    )
    rendered = render_story_inspection_json(inspection)
    parsed = json.loads(rendered)
    assert parsed["story_id"] == inspection.story_id
    assert parsed["current_state"] == inspection.current_state
    assert parsed["active_markers"] == list(inspection.active_markers)
    # Re-serialize via the same renderer (the second pass is via
    # Pydantic-driven serialization on a re-constructed model — round-
    # trip stability is the AC-5 invariant).
    rebuilt = StoryInspection.model_validate_json(rendered)
    re_rendered = render_story_inspection_json(rebuilt)
    assert rendered == re_rendered


def test_render_json_byte_stable_on_identical_input() -> None:
    inspection = _make_inspection(active_markers=("x",))
    a = render_story_inspection_json(inspection)
    b = render_story_inspection_json(inspection)
    assert a == b


# --------------------------------------------------------------------------- #
# AC-6 — Read-only invariant                                                  #
# --------------------------------------------------------------------------- #


def test_inspect_story_does_not_mutate_run_state_file(
    tmp_project: pathlib.Path,
) -> None:
    rs_path = _write_run_state_yaml(tmp_project)
    before_mtime = rs_path.stat().st_mtime_ns
    before_sha = hashlib.sha256(rs_path.read_bytes()).hexdigest()
    request = StatusRequest(
        project_root=tmp_project,
        story_id="8-4-test-slug",
        resolve_retry_rounds=True,
        story_doc_resolver=_stub_story_doc_resolver(
            raises=StoryDocNotFound(story_id="8-4-test-slug", searched_paths=())
        ),
    )
    inspect_story(request)
    after_mtime = rs_path.stat().st_mtime_ns
    after_sha = hashlib.sha256(rs_path.read_bytes()).hexdigest()
    assert before_mtime == after_mtime
    assert before_sha == after_sha


def test_status_command_has_no_write_surfaces() -> None:
    """AC-6 structural assertion: the status_command module's source
    contains NO write-shaped imports / calls. Uses AST to inspect
    imports + call expressions so docstring mentions of forbidden
    names (which legitimately enumerate the read-only invariant) do
    not falsely trip the assertion."""
    src = _inspect.getsource(status_command_module)
    tree = ast.parse(src)

    # Walk every node, collect imported names + call-attribute names.
    imported_names: set[str] = set()
    call_attr_names: set[str] = set()
    call_func_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.name)
                if alias.asname:
                    imported_names.add(alias.asname)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                call_attr_names.add(func.attr)
            elif isinstance(func, ast.Name):
                call_func_names.add(func.id)

    # AC-6 forbidden names: must not appear in imports OR as call
    # targets (function or method).
    forbidden = {
        "record_marker_with_context",
        "commit_transition",
        "advance_run_state",
        "_default_run_state_writer",
        "default_artifact_writer",
        "make_event_log_appender",
    }
    for name in forbidden:
        assert name not in imported_names, (
            f"status_command must NOT import {name!r} (AC-6 read-only "
            "invariant)"
        )
        assert name not in call_attr_names, (
            f"status_command must NOT call .{name}() (AC-6 read-only "
            "invariant)"
        )
        assert name not in call_func_names, (
            f"status_command must NOT call {name}() (AC-6 read-only "
            "invariant)"
        )

    # No subprocess.run invocations under any code path.
    assert "subprocess" not in imported_names, (
        "status_command must not import subprocess (AC-6 read-only "
        "invariant)"
    )

    # No write-shaped pathlib operations under any code path.
    write_shaped_attrs = {
        "write_text",
        "write_bytes",
        "mkdir",
        "touch",
        "unlink",
    }
    leaked = write_shaped_attrs & call_attr_names
    assert not leaked, (
        f"status_command must NOT invoke write-shaped pathlib operations; "
        f"found: {sorted(leaked)} (AC-6 read-only invariant)"
    )

    # AC-1's __all__ does not leak any write-shaped name.
    expected_all = {
        "StatusCommandError",
        "StatusOutcome",
        "StatusRequest",
        "StoryInspection",
        "inspect_story",
        "main",
        "render_no_run_state_diagnostic",
        "render_story_inspection_human",
        "render_story_inspection_json",
    }
    assert set(status_command_module.__all__) == expected_all


# --------------------------------------------------------------------------- #
# AC-9 — CLI smoke                                                            #
# --------------------------------------------------------------------------- #


def test_main_exits_zero_on_status_found(
    tmp_project: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_story_doc(tmp_project, "8-4")
    _write_run_state_yaml(
        tmp_project, story_id="8-4", current_state="in-progress"
    )
    rc = main(["8-4", "--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "# /bmad-automation status — story 8-4" in captured.out
    assert "## Lifecycle state" in captured.out


def test_main_exits_zero_on_status_found_with_json_flag(
    tmp_project: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_run_state_yaml(tmp_project, story_id="8-4")
    rc = main(["8-4", "--project-root", str(tmp_project), "--json"])
    captured = capsys.readouterr()
    assert rc == 0
    parsed = json.loads(captured.out)
    assert parsed["story_id"] == "8-4"
    # --json IMPLIES --resolve-retry-rounds: resolved_retry_rounds is
    # NOT None on this path (it's an empty tuple given empty
    # retry_history).
    assert parsed["resolved_retry_rounds"] == []


def test_main_exits_one_on_status_no_run_state(
    tmp_project: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["8-4-absent", "--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "status: " in captured.err
    assert "no-in-flight-run-found-for-story-id" in captured.err


def test_main_exits_two_on_substrate_error(
    tmp_project: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_run_state_yaml(tmp_project)

    def _raising(_path: pathlib.Path) -> RunState | None:
        raise CrossStateRecoveryError(
            reason="run-state-parse-failure",
            diagnostic="simulated parse failure",
            path=tmp_project / RUN_STATE_RELATIVE_PATH,
        )

    monkeypatch.setattr(
        status_command_module, "_load_run_state_from_disk", _raising
    )
    rc = main(["8-4", "--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "harness-level error" in captured.err


# --------------------------------------------------------------------------- #
# AC-9 — Story 8.5 projection-discipline contract                             #
# --------------------------------------------------------------------------- #


def test_story_inspection_payload_supports_8_5_projection_shape() -> None:
    """Synthesizes a StoryInspection AND projects it to a row-summary
    shape per epics.md:3342:
        (story_id, current_state, marker_count, last_activity_timestamp,
         branch_name)

    Asserts the projection compiles using ONLY StoryInspection's public
    fields — no parallel inspection logic in the projection lambda.
    THIS test documents Story 8.4's commitment to the
    projection-not-duplication invariant Story 8.5 will rely on per
    epics.md:3318-3320 verbatim.
    """
    inspection = _make_inspection(
        story_id="8-4-projection",
        current_state="qa",
        branch_name="bmad-automation/story/8-4-projection",
        active_markers=("a", "b", "c"),
        last_envelope={"timestamp": "2026-05-09T12:00:00+00:00"},
    )
    # The projection: StoryInspection → row-summary tuple shape.
    # Pure projection — no I/O, no parallel inspection logic.
    last_activity = (
        inspection.last_envelope.get("timestamp")
        if inspection.last_envelope is not None
        else None
    )
    row = (
        inspection.story_id,
        inspection.current_state,
        len(inspection.active_markers),
        last_activity,
        inspection.branch_name,
    )
    assert row == (
        "8-4-projection",
        "qa",
        3,
        "2026-05-09T12:00:00+00:00",
        "bmad-automation/story/8-4-projection",
    )


# --------------------------------------------------------------------------- #
# Epic 1 retro Action #1 — find_repo_root() discipline                        #
# --------------------------------------------------------------------------- #


def test_find_repo_root_not_at_module_collection_time() -> None:
    """The test module's TOP-LEVEL imports do NOT call find_repo_root.

    Epic 1 retro Action #1: find_repo_root() raises RuntimeError when
    invoked outside a repo, so calling it at module import time breaks
    pytest collection in alien environments.
    """
    src = _inspect.getsource(status_command_module)
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else None
            )
            assert name != "find_repo_root", (
                "find_repo_root() must not be called at module collection "
                "time; use a fixture per Epic 1 retro Action #1"
            )
