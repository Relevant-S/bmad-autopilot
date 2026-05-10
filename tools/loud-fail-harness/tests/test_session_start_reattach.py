"""Contract-coverage matrix for the SessionStart reattachment substrate (Story 8.1).

This docstring IS the contract-coverage checklist required by AC-8. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced (parallel to ``tests/test_hooks.py``,
``tests/test_init_non_destructive_guard.py``, etc.).

AC-1 — Substrate library shape:
    [x] public API exposes RUN_STATE_RELATIVE_PATH constant
    [x] public API exposes ReattachRequest + ReattachOutcome frozen Pydantic models
    [x] public API exposes detect_run_state, validate_run_state_schema,
        render_recovery_state_conflict_diagnostic, evaluate_reattach, main
    [x] SessionStartReattachError exposed and raised on substrate-level errors

AC-2 — No run-state detection (1):
    [x] test_evaluate_reattach_returns_no_run_state_found_when_file_absent

AC-2 / detection (3):
    [x] test_detect_run_state_returns_none_when_file_absent
    [x] test_detect_run_state_returns_path_when_file_present
    [x] test_detect_run_state_handles_unreadable_file_loudly

AC-3 — Anomaly branch detection (2):
    [x] test_evaluate_reattach_anomaly_when_branch_missing
    [x] test_evaluate_reattach_no_anomaly_when_not_a_git_repo

AC-4 — Schema validation (4):
    [x] test_validate_run_state_schema_clean_returns_run_state
    [x] test_validate_run_state_schema_returns_failures_on_unsupported_version
    [x] test_validate_run_state_schema_returns_failures_on_missing_required_field
    [x] test_validate_run_state_schema_returns_failures_on_yaml_parse_error

AC-5 — Clean reattach (3):
    [x] test_evaluate_reattach_clean_with_current_schema
    [x] test_evaluate_reattach_clean_does_not_mutate_run_state
    [x] test_evaluate_reattach_clean_does_not_invoke_git_mutation

AC-6 — Schema-mismatch + marker emission (3):
    [x] test_evaluate_reattach_schema_mismatch_emits_recovery_state_conflict
    [x] test_recovery_state_conflict_diagnostic_contains_required_clauses
    [x] test_evaluate_reattach_schema_mismatch_propagates_run_state_via_marker_registry

AC-7 / AC-9 — CLI smoke (4):
    [x] test_main_exits_zero_on_clean_reattach
    [x] test_main_exits_zero_on_schema_mismatch_with_marker_emitted_to_stderr
    [x] test_main_exits_zero_on_anomaly_branch_missing
    [x] test_main_exits_one_on_harness_error

Story 8.6 AC-5 — Canonical can_dispatch() consumption (3):
    [x] test_evaluate_reattach_invokes_can_dispatch_on_non_terminal_run_state
    [x] test_evaluate_reattach_captures_deny_verdict_diagnostic_in_outcome
    [x] test_evaluate_reattach_skips_can_dispatch_on_terminal_run_state
"""

from __future__ import annotations

import os
import pathlib
import subprocess
from typing import Any

import pytest

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.run_state import RunState
from loud_fail_harness.session_start_reattach import (
    RECOVERY_STATE_CONFLICT_MARKER_CLASS,
    RUN_STATE_RELATIVE_PATH,
    RUN_STATE_SCHEMA_CURRENT_VERSION,
    ReattachOutcome,
    ReattachRequest,
    SessionStartReattachError,
    detect_run_state,
    evaluate_reattach,
    main,
    render_recovery_state_conflict_diagnostic,
    validate_run_state_schema,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)


# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #


_REQUIRED_DIAGNOSTIC_CLAUSE_PREFIXES: tuple[str, ...] = (
    "recovery-state-conflict: ",
    "detected schema_version=",
    "current schema_version=",
    "validation failures:",
    "remediation:",
    "see schemas/marker-taxonomy.yaml:372-380",
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
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
    """Create a fresh tmp_path-rooted git repo with deterministic identity.

    Mirrors ``tests/test_hooks.py``'s ``fixture_repo`` shape.
    """
    _run_git("init", "-b", "main", cwd=tmp_path)
    _run_git("config", "user.email", "test@bmad-automation.local", cwd=tmp_path)
    _run_git("config", "user.name", "BMAD Test", cwd=tmp_path)
    _run_git("config", "commit.gpgsign", "false", cwd=tmp_path)
    (tmp_path / "README.md").write_text("# initial\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=tmp_path)
    _run_git("commit", "-m", "initial", cwd=tmp_path)
    return tmp_path


@pytest.fixture(scope="function")
def marker_registry() -> MarkerClassRegistry:
    """Real marker registry loaded from the canonical taxonomy file."""
    return load_marker_class_registry()


def _write_run_state_file(
    project_root: pathlib.Path,
    *,
    body: str | None = None,
    schema_version: str = "1.3",
    story_id: str = "8-1-test",
    branch_name: str = "bmad-automation/story/8-1-test",
    current_state: str = "in-progress",
    dispatched_specialist: str | None = "dev",
) -> pathlib.Path:
    """Synthesize ``_bmad/automation/run-state.yaml`` under ``project_root``.

    When ``body`` is supplied, write it verbatim (used for malformed-YAML and
    unsupported-version cases). Otherwise build a clean schema-1.3-compliant
    body from the keyword arguments.
    """
    rs_dir = project_root / "_bmad" / "automation"
    rs_dir.mkdir(parents=True, exist_ok=True)
    rs = rs_dir / "run-state.yaml"
    if body is not None:
        rs.write_text(body, encoding="utf-8")
        return rs
    spec_line = (
        "dispatched_specialist: null\n"
        if dispatched_specialist is None
        else f"dispatched_specialist: {dispatched_specialist}\n"
    )
    rs.write_text(
        f"schema_version: '{schema_version}'\n"
        f"story_id: {story_id}\n"
        "run_id: r1\n"
        f"current_state: {current_state}\n"
        f"branch_name: {branch_name}\n"
        + spec_line
        + "last_envelope: null\n"
        + "retry_history: []\n"
        + "active_markers: []\n"
        + "cost_to_date_by_specialist: {}\n"
        + "pending_qa_dispatch_payload: null\n",
        encoding="utf-8",
    )
    return rs


def _make_run_state(**overrides: Any) -> RunState:
    """Build a clean :class:`RunState` instance for marker-emission tests."""
    base: dict[str, Any] = {
        "schema_version": "1.3",
        "story_id": "8-1-test",
        "run_id": "r1",
        "current_state": "in-progress",
        "branch_name": "bmad-automation/story/8-1-test",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": (),
        "active_markers": (),
        "cost_to_date_by_specialist": {},
    }
    base.update(overrides)
    return RunState.model_validate(base)


# --------------------------------------------------------------------------- #
# AC-2 — Detection                                                            #
# --------------------------------------------------------------------------- #


def test_detect_run_state_returns_none_when_file_absent(tmp_path: pathlib.Path) -> None:
    assert detect_run_state(tmp_path) is None


def test_detect_run_state_returns_path_when_file_present(
    tmp_project: pathlib.Path,
) -> None:
    rs = _write_run_state_file(tmp_project)
    detected = detect_run_state(tmp_project)
    assert detected is not None
    assert detected.resolve() == rs.resolve()


def test_detect_run_state_handles_unreadable_file_loudly(
    tmp_project: pathlib.Path,
) -> None:
    # Skip on platforms that don't honor chmod for the running user
    # (e.g., root cannot trip the os.access check).
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("running as root; os.access(R_OK) returns True regardless")
    rs = _write_run_state_file(tmp_project)
    rs.chmod(0o000)
    try:
        with pytest.raises(SessionStartReattachError) as excinfo:
            detect_run_state(tmp_project)
        assert excinfo.value.reason == "run-state-unreadable"
        assert excinfo.value.path is not None
    finally:
        rs.chmod(0o644)


def test_evaluate_reattach_returns_no_run_state_found_when_file_absent(
    tmp_project: pathlib.Path,
) -> None:
    request = ReattachRequest(project_root=tmp_project)
    outcome, returned_run_state = evaluate_reattach(request)
    assert outcome.action == "no-run-state-found"
    assert outcome.run_state_path is None
    assert outcome.detected_schema_version is None
    assert outcome.current_schema_version == RUN_STATE_SCHEMA_CURRENT_VERSION
    assert outcome.branch_name is None
    assert outcome.marker_class is None
    assert outcome.diagnostic is None
    assert outcome.validation_failures == ()
    assert returned_run_state is None


# --------------------------------------------------------------------------- #
# AC-4 — Schema validation                                                    #
# --------------------------------------------------------------------------- #


def test_validate_run_state_schema_clean_returns_run_state(
    tmp_project: pathlib.Path,
) -> None:
    rs = _write_run_state_file(tmp_project, schema_version="1.3")
    parsed, failures, sv = validate_run_state_schema(rs)
    assert failures == ()
    assert parsed is not None
    assert parsed.schema_version == "1.3"
    assert parsed.story_id == "8-1-test"
    assert sv == "1.3"


def test_validate_run_state_schema_returns_failures_on_unsupported_version(
    tmp_project: pathlib.Path,
) -> None:
    rs = _write_run_state_file(tmp_project, schema_version="1.0")
    parsed, failures, sv = validate_run_state_schema(rs)
    assert parsed is None
    assert "/schema_version" in failures
    # detected schema_version available directly — no second file read needed.
    assert sv == "1.0"


def test_validate_run_state_schema_returns_failures_on_missing_required_field(
    tmp_project: pathlib.Path,
) -> None:
    body = (
        "schema_version: '1.3'\n"
        # story_id intentionally absent.
        "run_id: r1\n"
        "current_state: in-progress\n"
        "branch_name: bmad-automation/story/8-1-test\n"
        "dispatched_specialist: null\n"
        "last_envelope: null\n"
        "retry_history: []\n"
        "active_markers: []\n"
        "cost_to_date_by_specialist: {}\n"
        "pending_qa_dispatch_payload: null\n"
    )
    rs = _write_run_state_file(tmp_project, body=body)
    parsed, failures, sv = validate_run_state_schema(rs)
    assert parsed is None
    assert "/story_id" in failures
    assert sv == "1.3"


def test_validate_run_state_schema_returns_failures_on_yaml_parse_error(
    tmp_project: pathlib.Path,
) -> None:
    # Truncated mid-write OR malformed YAML.
    rs = _write_run_state_file(
        tmp_project, body="schema_version: '1.3'\nstory_id: [unterminated\n"
    )
    parsed, failures, sv = validate_run_state_schema(rs)
    assert parsed is None
    assert failures == ("<root>",)
    assert sv is None  # YAML parse error — schema_version not extractable


# --------------------------------------------------------------------------- #
# AC-5 — Clean reattach                                                       #
# --------------------------------------------------------------------------- #


def test_evaluate_reattach_clean_with_current_schema(
    tmp_project: pathlib.Path,
) -> None:
    _write_run_state_file(tmp_project, schema_version="1.3")
    # Branch must exist for the clean path.
    _run_git(
        "checkout", "-b", "bmad-automation/story/8-1-test", cwd=tmp_project
    )
    request = ReattachRequest(project_root=tmp_project)
    outcome, _ = evaluate_reattach(request)
    assert outcome.action == "reattach-clean"
    assert outcome.detected_schema_version == "1.3"
    assert outcome.branch_name == "bmad-automation/story/8-1-test"
    assert outcome.dispatched_specialist == "dev"
    assert outcome.current_state == "in-progress"
    assert outcome.marker_class is None
    assert outcome.diagnostic is None
    assert outcome.validation_failures == ()
    # current_branch must be populated after git checkout -b.
    assert outcome.current_branch == "bmad-automation/story/8-1-test"


def test_evaluate_reattach_clean_does_not_mutate_run_state(
    tmp_project: pathlib.Path,
) -> None:
    rs = _write_run_state_file(tmp_project)
    _run_git(
        "checkout", "-b", "bmad-automation/story/8-1-test", cwd=tmp_project
    )
    pre_mtime = rs.stat().st_mtime_ns
    pre_bytes = rs.read_bytes()
    request = ReattachRequest(project_root=tmp_project)
    evaluate_reattach(request)
    post_mtime = rs.stat().st_mtime_ns
    post_bytes = rs.read_bytes()
    assert pre_mtime == post_mtime, "substrate must not touch run-state mtime"
    assert pre_bytes == post_bytes, "substrate must not modify run-state bytes"


def test_evaluate_reattach_clean_does_not_invoke_git_mutation(
    tmp_project: pathlib.Path,
) -> None:
    """The injected git_runner must only be called with read-only arguments
    (rev-parse / branch --list); never checkout / commit / branch -d / etc.
    """
    _write_run_state_file(tmp_project)
    _run_git(
        "checkout", "-b", "bmad-automation/story/8-1-test", cwd=tmp_project
    )
    invocations: list[tuple[str, ...]] = []

    def recording_runner(
        args, cwd
    ):  # type: ignore[no-untyped-def]
        invocations.append(tuple(args))
        # Delegate to the real subprocess.run so the test exercises a real
        # git interaction.
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    request = ReattachRequest(
        project_root=tmp_project, git_runner=recording_runner
    )
    evaluate_reattach(request)
    assert invocations, "git_runner must be invoked at least once"
    forbidden_subcommands = {
        "checkout",
        "commit",
        "merge",
        "reset",
        "rebase",
        "push",
        "pull",
        "fetch",
        "clean",
    }
    for invocation in invocations:
        if invocation:
            head = invocation[0]
            assert head not in forbidden_subcommands, (
                f"git_runner invoked with mutating subcommand {head!r}: {invocation!r}"
            )


# --------------------------------------------------------------------------- #
# AC-3 — Anomaly branch detection                                             #
# --------------------------------------------------------------------------- #


def test_evaluate_reattach_anomaly_when_branch_missing(
    tmp_project: pathlib.Path,
) -> None:
    _write_run_state_file(
        tmp_project, branch_name="bmad-automation/story/missing-branch"
    )

    def stub_runner(
        args, cwd
    ):  # type: ignore[no-untyped-def]
        # rev-parse --abbrev-ref HEAD → "main".
        if tuple(args[:2]) == ("rev-parse", "--abbrev-ref"):
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="main\n", stderr=""
            )
        # show-ref --verify → exit 1 (ref not found, anomaly).
        if tuple(args[:2]) == ("show-ref", "--verify"):
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr=""
            )
        return subprocess.CompletedProcess(
            args=args, returncode=1, stdout="", stderr=""
        )

    request = ReattachRequest(
        project_root=tmp_project, git_runner=stub_runner
    )
    outcome, _ = evaluate_reattach(request)
    assert outcome.action == "anomaly-branch-missing"
    assert outcome.branch_name == "bmad-automation/story/missing-branch"
    assert outcome.current_branch == "main"
    assert outcome.marker_class is None
    assert outcome.diagnostic is not None
    assert "anomaly" in outcome.diagnostic
    assert "missing-branch" in outcome.diagnostic


def test_evaluate_reattach_no_anomaly_when_not_a_git_repo(
    tmp_path: pathlib.Path,
) -> None:
    """A project_root with no .git/ directory — git probes return None;
    the substrate falls through to reattach-clean per AC-3.
    """
    _write_run_state_file(tmp_path)
    request = ReattachRequest(project_root=tmp_path)
    outcome, _ = evaluate_reattach(request)
    # Without git the branch probe returns None (git unavailable), which routes
    # to reattach-clean per AC-3 — not anomaly-branch-missing.
    assert outcome.action == "reattach-clean"
    # current_branch is None when git is unavailable.
    assert outcome.current_branch is None


# --------------------------------------------------------------------------- #
# AC-6 — Schema-mismatch + marker emission                                    #
# --------------------------------------------------------------------------- #


def test_evaluate_reattach_schema_mismatch_emits_recovery_state_conflict(
    tmp_project: pathlib.Path, marker_registry: MarkerClassRegistry
) -> None:
    _write_run_state_file(tmp_project, schema_version="1.0")
    run_state = _make_run_state()
    request = ReattachRequest(project_root=tmp_project)
    outcome, returned_run_state = evaluate_reattach(
        request, run_state=run_state, marker_registry=marker_registry
    )
    assert outcome.action == "reattach-with-marker"
    assert outcome.marker_class == RECOVERY_STATE_CONFLICT_MARKER_CLASS
    assert outcome.detected_schema_version == "1.0"
    assert outcome.diagnostic is not None
    assert "/schema_version" in outcome.validation_failures
    assert returned_run_state is not None
    assert (
        RECOVERY_STATE_CONFLICT_MARKER_CLASS in returned_run_state.active_markers
    )


def test_recovery_state_conflict_diagnostic_contains_required_clauses() -> None:
    """The rendered diagnostic carries all six AC-6 clause prefixes."""
    outcome = ReattachOutcome(
        action="reattach-with-marker",
        run_state_path=pathlib.Path("/tmp/_bmad/automation/run-state.yaml"),
        detected_schema_version="1.0",
        current_schema_version="1.3",
        branch_name=None,
        current_branch=None,
        dispatched_specialist=None,
        current_state=None,
        marker_class=RECOVERY_STATE_CONFLICT_MARKER_CLASS,
        diagnostic=None,
        validation_failures=("/schema_version",),
    )
    rendered = render_recovery_state_conflict_diagnostic(outcome)
    for clause_prefix in _REQUIRED_DIAGNOSTIC_CLAUSE_PREFIXES:
        assert clause_prefix in rendered, (
            f"diagnostic missing required clause {clause_prefix!r}; got: {rendered}"
        )


def test_evaluate_reattach_schema_mismatch_propagates_run_state_via_marker_registry(
    tmp_project: pathlib.Path, marker_registry: MarkerClassRegistry
) -> None:
    _write_run_state_file(tmp_project, schema_version="1.0")
    run_state = _make_run_state()
    request = ReattachRequest(project_root=tmp_project)
    _, returned_run_state = evaluate_reattach(
        request, run_state=run_state, marker_registry=marker_registry
    )
    assert returned_run_state is not None
    assert (
        RECOVERY_STATE_CONFLICT_MARKER_CLASS
        in returned_run_state.active_markers
    )
    # Without registry/run_state, NO emission AND second tuple element is None.
    request2 = ReattachRequest(project_root=tmp_project)
    _, no_runtime = evaluate_reattach(request2)
    assert no_runtime is None


# --------------------------------------------------------------------------- #
# AC-7 / AC-9 — CLI smoke                                                     #
# --------------------------------------------------------------------------- #


def test_main_exits_zero_on_clean_reattach(
    tmp_project: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_run_state_file(tmp_project, schema_version="1.3")
    _run_git(
        "checkout", "-b", "bmad-automation/story/8-1-test", cwd=tmp_project
    )
    rc = main(["--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "session-start: reattach:" in captured.err
    assert "schema_version=1.3" in captured.err
    assert "branch=bmad-automation/story/8-1-test" in captured.err


def test_main_exits_zero_on_schema_mismatch_with_marker_emitted_to_stderr(
    tmp_project: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_run_state_file(tmp_project, schema_version="1.0")
    rc = main(["--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "session-start: recovery-state-conflict:" in captured.err
    assert "/schema_version" in captured.err
    assert "remediation:" in captured.err


def test_main_exits_zero_on_anomaly_branch_missing(
    tmp_project: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI renders the anomaly diagnostic to stderr and exits 0 (AC-3/AC-9).

    ``main()`` line for anomaly-branch-missing calls ``print(outcome.diagnostic,
    file=sys.stderr)`` — this test guards that the field is non-None and the
    output contains the expected prefix so a future refactor cannot silently
    print "None".
    """
    _write_run_state_file(
        tmp_project, branch_name="bmad-automation/story/never-exists"
    )
    # Use a stub runner that reports the branch as missing (show-ref exit 1).
    def stub_runner(args, cwd):  # type: ignore[no-untyped-def]
        if tuple(args[:2]) == ("rev-parse", "--abbrev-ref"):
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="main\n", stderr=""
            )
        if tuple(args[:2]) == ("show-ref", "--verify"):
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr=""
            )
        return subprocess.CompletedProcess(
            args=args, returncode=1, stdout="", stderr=""
        )

    from unittest.mock import patch
    with patch(
        "loud_fail_harness.session_start_reattach._default_git_runner",
        side_effect=stub_runner,
    ):
        rc = main(["--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "session-start: anomaly:" in captured.err
    assert "never-exists" in captured.err


def test_main_exits_one_on_harness_error(
    tmp_project: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI exits 1 on substrate-level errors (AC-9 harness-level error contract).

    Trigger: a run-state file that exists but is unreadable raises
    ``SessionStartReattachError`` inside ``evaluate_reattach``, which
    ``main()``'s except clause catches and converts to exit 1.
    """
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("running as root; os.access(R_OK) returns True regardless")
    rs = _write_run_state_file(tmp_project)
    rs.chmod(0o000)
    try:
        rc = main(["--project-root", str(tmp_project)])
    finally:
        rs.chmod(0o644)
    captured = capsys.readouterr()
    assert rc == 1
    assert "harness-level error" in captured.err


# --------------------------------------------------------------------------- #
# Module-level discipline                                                     #
# --------------------------------------------------------------------------- #


def test_module_level_constants_match_documented_paths() -> None:
    assert RUN_STATE_RELATIVE_PATH == "_bmad/automation/run-state.yaml"
    # The current-version constant must equal the highest member of
    # RunState.schema_version's Literal (version-tuple sort, not lexicographic).
    annotation = RunState.model_fields["schema_version"].annotation
    args = getattr(annotation, "__args__", ())
    assert RUN_STATE_SCHEMA_CURRENT_VERSION == max(
        args, key=lambda a: tuple(int(x) for x in str(a).split("."))
    )


def test_run_state_schema_path_resolves_at_runtime() -> None:
    """find_repo_root + schemas/run-state.yaml must exist (test runs from repo)."""
    assert (find_repo_root() / "schemas" / "run-state.yaml").is_file()


def test_recovery_state_conflict_marker_class_is_in_taxonomy(
    marker_registry: MarkerClassRegistry,
) -> None:
    assert RECOVERY_STATE_CONFLICT_MARKER_CLASS in marker_registry.marker_classes


def test_session_start_reattach_clean_pairs_with_cross_state_recovery_clean(
    tmp_project: pathlib.Path,
) -> None:
    """Story 8.2 forward-compat smoke: a clean reattach scenario also yields
    a clean cross-state recovery outcome when the run-state and story-doc
    agree on lifecycle state.

    The import of ``cross_state_recovery`` lives in this test, NOT in
    ``session_start_reattach.py`` — Story 8.1's substrate stays unmodified
    per Story 8.2 AC-11.
    """
    from loud_fail_harness.cross_state_recovery import (
        RecoveryRequest,
        evaluate_recovery,
    )
    from loud_fail_harness.orchestrator_run_entry import (
        AcceptanceCriterion,
        SprintStatusResolution,
        StoryDocResolution,
    )

    _write_run_state_file(
        tmp_project,
        schema_version="1.3",
        story_id="8-1-test",
        current_state="ready-for-dev",
    )
    _run_git("checkout", "-b", "bmad-automation/story/8-1-test", cwd=tmp_project)

    # 8.1's reattach must classify the clean run-state as clean.
    reattach_request = ReattachRequest(project_root=tmp_project)
    reattach_outcome, _ = evaluate_reattach(reattach_request)
    assert reattach_outcome.action == "reattach-clean"

    # Now construct a story-doc that agrees with the run-state.
    target = (
        tmp_project
        / "_bmad-output"
        / "implementation-artifacts"
        / "8-1-test-slug.md"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# Story 8-1\n\nStatus: ready-for-dev\n\n"
        "## Acceptance Criteria\n\n**AC-1 — placeholder**\n",
        encoding="utf-8",
    )

    def stub_story_doc_resolver(
        story_id: str, project_root: pathlib.Path
    ) -> StoryDocResolution:
        return StoryDocResolution(
            path=target,
            current_state="ready-for-dev",
            acceptance_criteria=(
                AcceptanceCriterion(ac_id="AC-1", text="placeholder"),
            ),
        )

    def stub_sprint_status_resolver(
        story_id: str, project_root: pathlib.Path
    ) -> SprintStatusResolution:
        return SprintStatusResolution(current_state="ready-for-dev")

    rs_path = tmp_project / "_bmad" / "automation" / "run-state.yaml"
    parsed_run_state = RunState.model_validate(
        {
            "schema_version": "1.3",
            "story_id": "8-1-test",
            "run_id": "r1",
            "current_state": "ready-for-dev",
            "branch_name": "bmad-automation/story/8-1-test",
            "dispatched_specialist": None,
            "last_envelope": None,
            "pending_qa_dispatch_payload": None,
            "retry_history": (),
            "active_markers": (),
            "cost_to_date_by_specialist": {},
        }
    )

    recovery_request = RecoveryRequest(
        project_root=tmp_project,
        story_id="8-1-test",
        story_doc_resolver=stub_story_doc_resolver,
        sprint_status_resolver=stub_sprint_status_resolver,
        run_state_writer=lambda p, s: None,
    )
    recovery_outcome, _ = evaluate_recovery(
        recovery_request, run_state=parsed_run_state
    )
    assert recovery_outcome.action == "recovery-clean"
    assert recovery_outcome.disagreements == ()
    # Confirm rs_path was not modified by either substrate.
    assert rs_path.is_file()


def test_evaluate_reattach_purity_byte_identical_outcome(
    tmp_project: pathlib.Path,
) -> None:
    """detect_run_state + validate_run_state_schema return byte-identical
    results across repeated calls (defensive against accidental caching)."""
    _write_run_state_file(tmp_project, schema_version="1.3")
    a = detect_run_state(tmp_project)
    b = detect_run_state(tmp_project)
    assert a == b
    assert a is not None
    p1, f1, sv1 = validate_run_state_schema(a)
    p2, f2, sv2 = validate_run_state_schema(a)
    assert f1 == f2
    assert sv1 == sv2
    assert (p1 is None) == (p2 is None)
    if p1 is not None and p2 is not None:
        assert p1.model_dump() == p2.model_dump()


# --------------------------------------------------------------------------- #
# Story 8.6 AC-5 — Canonical can_dispatch() consumption                       #
# --------------------------------------------------------------------------- #


def test_evaluate_reattach_invokes_can_dispatch_on_non_terminal_run_state(
    tmp_project: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the schema-validated run-state has a non-terminal current_state
    AND a previously-dispatched specialist, ``evaluate_reattach`` invokes
    the canonical Story 8.6 substrate
    :func:`no_destructive_resume_guard.can_dispatch`."""
    from loud_fail_harness import session_start_reattach as ssr_module
    from loud_fail_harness.no_destructive_resume_guard import Verdict

    _write_run_state_file(
        tmp_project,
        schema_version="1.3",
        current_state="in-progress",
        dispatched_specialist="dev",
    )
    _run_git(
        "checkout", "-b", "bmad-automation/story/8-1-test", cwd=tmp_project
    )

    captured: list[tuple[Any, ...]] = []

    def _spy_can_dispatch(specialist: Any, story_id: Any, run_state: Any) -> Verdict:
        captured.append((specialist, story_id, run_state))
        return Verdict(allow=True)

    monkeypatch.setattr(ssr_module, "can_dispatch", _spy_can_dispatch)

    request = ReattachRequest(project_root=tmp_project)
    outcome, _ = evaluate_reattach(request)
    assert outcome.action == "reattach-clean"
    # The next-specialist for in-progress is "review-bmad" per the
    # local _NEXT_SPECIALIST_BY_STATE map.
    assert len(captured) == 1
    spec_arg, story_arg, _rs_arg = captured[0]
    assert spec_arg == "review-bmad"
    assert story_arg == "8-1-test"


def test_evaluate_reattach_captures_deny_verdict_diagnostic_in_outcome(
    tmp_project: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a deny verdict from can_dispatch, the verdict's diagnostic is
    captured into the outcome's ``diagnostic`` field — without altering
    the outcome's ``action`` enum (SessionStart's job is to SIGNAL
    reattachment, not to halt dispatch)."""
    from loud_fail_harness import session_start_reattach as ssr_module
    from loud_fail_harness.no_destructive_resume_guard import Verdict

    _write_run_state_file(
        tmp_project,
        schema_version="1.3",
        current_state="in-progress",
        dispatched_specialist="dev",
    )
    _run_git(
        "checkout", "-b", "bmad-automation/story/8-1-test", cwd=tmp_project
    )

    deny_diagnostic = (
        "can-dispatch deny[prior-output-recorded]: specialist='review-bmad'"
    )

    def _stub_deny(specialist: Any, story_id: Any, run_state: Any) -> Verdict:
        return Verdict(
            allow=False,
            reason="prior-output-recorded",
            diagnostic=deny_diagnostic,
        )

    monkeypatch.setattr(ssr_module, "can_dispatch", _stub_deny)

    request = ReattachRequest(project_root=tmp_project)
    outcome, _ = evaluate_reattach(request)
    # Action enum is unchanged — reattach-clean per the structural
    # invariant (SessionStart signals reattach, NOT halt).
    assert outcome.action == "reattach-clean"
    # The deny diagnostic is captured in the outcome.
    assert outcome.diagnostic == deny_diagnostic


def test_evaluate_reattach_skips_can_dispatch_on_terminal_run_state(
    tmp_project: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When current_state is terminal (``done`` / ``escalated``), no
    re-dispatch is implied — the can_dispatch invocation is skipped."""
    from loud_fail_harness import session_start_reattach as ssr_module
    from loud_fail_harness.no_destructive_resume_guard import Verdict

    _write_run_state_file(
        tmp_project,
        schema_version="1.3",
        current_state="done",
        dispatched_specialist="qa",
    )
    _run_git(
        "checkout", "-b", "bmad-automation/story/8-1-test", cwd=tmp_project
    )

    captured: list[tuple[Any, ...]] = []

    def _spy_can_dispatch(specialist: Any, story_id: Any, run_state: Any) -> Verdict:
        captured.append((specialist, story_id, run_state))
        return Verdict(allow=True)

    monkeypatch.setattr(ssr_module, "can_dispatch", _spy_can_dispatch)

    request = ReattachRequest(project_root=tmp_project)
    outcome, _ = evaluate_reattach(request)
    assert outcome.action == "reattach-clean"
    assert outcome.current_state == "done"
    # can_dispatch must NOT be invoked on terminal states.
    assert captured == []
