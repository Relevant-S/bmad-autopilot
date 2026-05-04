"""Tests for ``loud_fail_harness.scope_assertion`` (Story 5.4).

AC mapping:

* AC-3 — :func:`verify_scope_assertion` correctly classifies the
  canonical comparison cases (clean, violation, edge cases, ordering).
* AC-4 — :func:`make_scope_assertion_diagnostic` correctly builds
  emission-ready diagnostics with precondition enforcement.
* AC-5 — :func:`default_actual_diff_probe` correctly shells out to
  ``git diff --name-only`` and surfaces failures via
  :exc:`ScopeAssertionProbeError`.
* AC-7 — CLI entry-point (``scope-assertion-verify``) smoke (the full
  hook integration is in ``tests/test_hooks.py``).
* AC-11 — test count >= 25 post-parametrize-expansion.

Per epics.md verbatim discipline, this test module exercises ONLY the
substrate under :mod:`loud_fail_harness.scope_assertion`; it does NOT
import :mod:`loud_fail_harness.retry_dispatch` (the substrate is
consumed AS-IS at the orchestrator-skill layer; the verifier accepts
already-extracted tuples).
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import subprocess
from typing import Any

import pytest

from loud_fail_harness.scope_assertion import (
    ActualDiffProbe,
    ScopeAssertionDiagnostic,
    ScopeAssertionProbeError,
    ScopeAssertionResult,
    ScopeAssertionViolation,
    _main,
    default_actual_diff_probe,
    make_scope_assertion_diagnostic,
    verify_scope_assertion,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _make_violation_result(
    *,
    violating_files: tuple[str, ...] = ("src/baz.py",),
    declared_scope: tuple[str, ...] = ("src/foo.py",),
    declared_expansion: tuple[str, ...] = (),
    actual_files: tuple[str, ...] = ("src/foo.py", "src/baz.py"),
) -> ScopeAssertionResult:
    return ScopeAssertionResult(
        is_violation=True,
        violating_files=violating_files,
        declared_scope=declared_scope,
        declared_expansion=declared_expansion,
        actual_files=actual_files,
        verified_at="2026-05-04T00:00:00+00:00",
    )


def _run_git(*args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def _init_git_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """Initialize a git repo at ``tmp_path`` with a single seed commit."""
    _run_git("init", "-b", "main", cwd=tmp_path)
    _run_git("config", "user.email", "test@bmad-automation.local", cwd=tmp_path)
    _run_git("config", "user.name", "BMAD Test", cwd=tmp_path)
    _run_git("config", "commit.gpgsign", "false", cwd=tmp_path)
    (tmp_path / "README.md").write_text("# initial\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=tmp_path)
    _run_git("commit", "-m", "initial", cwd=tmp_path)
    return tmp_path


def _commit_files(
    repo: pathlib.Path, files: dict[str, str], message: str
) -> None:
    for relpath, content in files.items():
        target = repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        _run_git("add", relpath, cwd=repo)
    _run_git("commit", "-m", message, cwd=repo)


def _write_run_state(
    repo: pathlib.Path,
    *,
    story_id: str = "5-4-test",
    affected_files: list[str] | None = None,
    scope_expanded_to: list[str] | None = None,
    last_retry_directive_present: bool = True,
    retry_history: list[dict[str, Any]] | None = None,
) -> pathlib.Path:
    """Synthesize ``_bmad/automation/run-state.yaml`` under ``repo``."""
    rs_dir = repo / "_bmad" / "automation"
    rs_dir.mkdir(parents=True, exist_ok=True)
    rs_path = rs_dir / "run-state.yaml"
    if affected_files is None:
        affected_files = ["src/foo.py"]
    if scope_expanded_to is None:
        scope_expanded_to = []
    if retry_history is None:
        retry_history = [{"retry_attempt": 1, "retry_reason": "dev test failure"}]
    if last_retry_directive_present:
        directive_block = (
            "last_retry_directive:\n"
            "  retry_mode: fix-only\n"
            "  affected_files: ["
            + ",".join(repr(p) for p in affected_files)
            + "]\n"
        )
    else:
        directive_block = "last_retry_directive: null\n"
    scope_line = (
        "  scope_expanded_to: ["
        + ",".join(repr(p) for p in scope_expanded_to)
        + "]\n"
    )
    rh_block = "retry_history:\n"
    for entry in retry_history:
        rh_block += (
            f"- retry_attempt: {entry['retry_attempt']}\n"
            f"  retry_reason: {entry['retry_reason']!r}\n"
        )
    rs_path.write_text(
        f"schema_version: '1.2'\n"
        f"story_id: {story_id}\n"
        f"run_id: r1\n"
        f"current_state: in-progress\n"
        f"branch_name: bmad-automation/story/{story_id}\n"
        f"dispatched_specialist: dev\n"
        "last_envelope:\n"
        "  status: fail\n"
        "  rationale: x\n"
        "  proposed_commit_message: 'fix: x'\n"
        + scope_line
        + rh_block
        + "active_markers: []\n"
        + "cost_to_date_by_specialist: {}\n"
        + "pending_qa_dispatch_payload: null\n"
        + directive_block,
        encoding="utf-8",
    )
    return rs_path


# --------------------------------------------------------------------------- #
# AC-3 — verify_scope_assertion                                                #
# --------------------------------------------------------------------------- #


def test_verify_scope_assertion_clean_no_expansion() -> None:
    result = verify_scope_assertion(
        affected_files=("src/foo.py",),
        scope_expanded_to=(),
        actual_files=("src/foo.py",),
    )
    assert result.is_violation is False
    assert result.violating_files == ()
    assert result.declared_scope == ("src/foo.py",)
    assert result.declared_expansion == ()
    assert result.actual_files == ("src/foo.py",)


def test_verify_scope_assertion_clean_with_declared_expansion() -> None:
    result = verify_scope_assertion(
        affected_files=("src/foo.py",),
        scope_expanded_to=("src/bar.py",),
        actual_files=("src/foo.py", "src/bar.py"),
    )
    assert result.is_violation is False
    assert result.violating_files == ()


def test_verify_scope_assertion_violation_undeclared_expansion() -> None:
    result = verify_scope_assertion(
        affected_files=("src/foo.py",),
        scope_expanded_to=(),
        actual_files=("src/foo.py", "src/baz.py"),
    )
    assert result.is_violation is True
    assert result.violating_files == ("src/baz.py",)


def test_verify_scope_assertion_violation_incomplete_declaration() -> None:
    result = verify_scope_assertion(
        affected_files=("src/foo.py",),
        scope_expanded_to=("src/bar.py",),
        actual_files=("src/foo.py", "src/bar.py", "src/baz.py"),
    )
    assert result.is_violation is True
    assert result.violating_files == ("src/baz.py",)


def test_verify_scope_assertion_empty_actual_files_is_clean() -> None:
    result = verify_scope_assertion(
        affected_files=("src/foo.py",),
        scope_expanded_to=(),
        actual_files=(),
    )
    assert result.is_violation is False
    assert result.violating_files == ()


def test_verify_scope_assertion_actual_subset_of_declared_is_clean() -> None:
    result = verify_scope_assertion(
        affected_files=("src/foo.py", "src/bar.py"),
        scope_expanded_to=(),
        actual_files=("src/foo.py",),
    )
    assert result.is_violation is False
    assert result.violating_files == ()


def test_verify_scope_assertion_preserves_first_occurrence_order() -> None:
    result = verify_scope_assertion(
        affected_files=(),
        scope_expanded_to=("b",),
        actual_files=("a", "b", "c", "d"),
    )
    assert result.violating_files == ("a", "c", "d")


def test_verify_scope_assertion_non_string_actual_raises_value_error() -> None:
    with pytest.raises(ValueError, match="actual_files"):
        verify_scope_assertion(
            affected_files=("src/foo.py",),
            scope_expanded_to=(),
            actual_files=(123, "src/foo.py"),  # type: ignore[arg-type]
        )


def test_verify_scope_assertion_non_string_affected_raises_value_error() -> None:
    with pytest.raises(ValueError, match="affected_files"):
        verify_scope_assertion(
            affected_files=(123,),  # type: ignore[arg-type]
            scope_expanded_to=(),
            actual_files=("src/foo.py",),
        )


def test_verify_scope_assertion_verified_at_is_iso8601_parseable() -> None:
    import datetime as _dt

    result = verify_scope_assertion(
        affected_files=(),
        scope_expanded_to=(),
        actual_files=(),
    )
    parsed = _dt.datetime.fromisoformat(result.verified_at)
    assert parsed.tzinfo is not None  # UTC-aware


def test_verify_scope_assertion_accepts_iterable_inputs() -> None:
    """Runtime-permissive on iterable inputs to keep CLI integration robust."""
    result = verify_scope_assertion(
        affected_files=["src/foo.py"],  # type: ignore[arg-type]
        scope_expanded_to=[],  # type: ignore[arg-type]
        actual_files=["src/foo.py"],  # type: ignore[arg-type]
    )
    assert result.is_violation is False


def test_verify_scope_assertion_result_is_frozen() -> None:
    result = verify_scope_assertion(
        affected_files=(),
        scope_expanded_to=(),
        actual_files=(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.is_violation = True  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# AC-4 — make_scope_assertion_diagnostic                                       #
# --------------------------------------------------------------------------- #


def test_make_scope_assertion_diagnostic_basic() -> None:
    result = _make_violation_result()
    diagnostic = make_scope_assertion_diagnostic(
        result, story_id="5-4-test", retry_round=2
    )
    assert isinstance(diagnostic, ScopeAssertionDiagnostic)
    assert diagnostic.marker_class == "scope-assertion-violation"
    assert diagnostic.story_id == "5-4-test"
    assert diagnostic.retry_round == 2
    assert diagnostic.violating_files == ("src/baz.py",)
    assert diagnostic.declared_scope == ("src/foo.py",)
    assert diagnostic.declared_expansion == ()


def test_make_scope_assertion_diagnostic_rejects_non_violation() -> None:
    result = ScopeAssertionResult(
        is_violation=False,
        violating_files=(),
        declared_scope=(),
        declared_expansion=(),
        actual_files=(),
        verified_at="2026-05-04T00:00:00+00:00",
    )
    with pytest.raises(ValueError, match="precondition"):
        make_scope_assertion_diagnostic(
            result, story_id="5-4-test", retry_round=1
        )


def test_make_scope_assertion_diagnostic_rejects_zero_retry_round() -> None:
    with pytest.raises(ValueError, match="retry_round"):
        make_scope_assertion_diagnostic(
            _make_violation_result(), story_id="5-4-test", retry_round=0
        )


def test_make_scope_assertion_diagnostic_rejects_empty_story_id() -> None:
    with pytest.raises(ValueError, match="story_id"):
        make_scope_assertion_diagnostic(
            _make_violation_result(), story_id="", retry_round=1
        )


def test_make_scope_assertion_diagnostic_is_json_serializable() -> None:
    diagnostic = make_scope_assertion_diagnostic(
        _make_violation_result(), story_id="5-4-test", retry_round=1
    )
    payload = dataclasses.asdict(diagnostic)
    # Round-trip through JSON; tuples → lists.
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["story_id"] == "5-4-test"
    assert decoded["violating_files"] == ["src/baz.py"]


def test_make_scope_assertion_diagnostic_marker_class_classvar() -> None:
    """marker_class is a ClassVar — not an instance field; matches taxonomy."""
    assert ScopeAssertionDiagnostic.marker_class == "scope-assertion-violation"
    diagnostic = make_scope_assertion_diagnostic(
        _make_violation_result(), story_id="5-4-test", retry_round=1
    )
    # ClassVar is not in dataclass fields.
    field_names = {f.name for f in dataclasses.fields(diagnostic)}
    assert "marker_class" not in field_names


# --------------------------------------------------------------------------- #
# AC-5 — default_actual_diff_probe                                             #
# --------------------------------------------------------------------------- #


def test_default_actual_diff_probe_returns_files_modified_between_commits(
    tmp_path: pathlib.Path,
) -> None:
    repo = _init_git_repo(tmp_path)
    _commit_files(
        repo,
        {"src/foo.py": "x = 1\n", "src/bar.py": "y = 2\n"},
        "feat: add foo + bar",
    )
    probe = default_actual_diff_probe(repo_root=repo)
    diff = probe()
    assert set(diff) == {"src/foo.py", "src/bar.py"}


def test_default_actual_diff_probe_raises_on_missing_head_tilde_one(
    tmp_path: pathlib.Path,
) -> None:
    """A repo with only one commit (no HEAD~1) raises ScopeAssertionProbeError."""
    repo = _init_git_repo(tmp_path)
    probe = default_actual_diff_probe(repo_root=repo)
    with pytest.raises(ScopeAssertionProbeError, match="HEAD~1"):
        probe()


def test_default_actual_diff_probe_raises_on_not_a_git_repo(
    tmp_path: pathlib.Path,
) -> None:
    probe = default_actual_diff_probe(repo_root=tmp_path)
    with pytest.raises(ScopeAssertionProbeError):
        probe()


def test_default_actual_diff_probe_raises_on_timeout(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_git_repo(tmp_path)
    _commit_files(repo, {"a.py": "1\n"}, "feat: a")

    def _raise_timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=10.0)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    probe = default_actual_diff_probe(repo_root=repo)
    with pytest.raises(ScopeAssertionProbeError, match="timed out"):
        probe()


def test_default_actual_diff_probe_default_timeout_is_ten_seconds() -> None:
    """The default timeout is documented as 10.0s; verify by inspection."""
    import inspect

    src = inspect.getsource(default_actual_diff_probe)
    assert "timeout=10.0" in src


def test_default_actual_diff_probe_accepts_custom_refs(
    tmp_path: pathlib.Path,
) -> None:
    repo = _init_git_repo(tmp_path)
    _commit_files(repo, {"a.py": "1\n"}, "feat: a")
    _commit_files(repo, {"b.py": "1\n"}, "feat: b")
    _commit_files(repo, {"c.py": "1\n"}, "feat: c")
    probe = default_actual_diff_probe(
        repo_root=repo, base_ref="HEAD~2", head_ref="HEAD"
    )
    diff = probe()
    # Files added in last 2 commits.
    assert set(diff) == {"b.py", "c.py"}


def test_stub_probe_injection_works_pure_in_memory() -> None:
    """Document the sensor-not-advisor injection contract (AC-5)."""

    def stub_probe() -> tuple[str, ...]:
        return ("src/foo.py",)

    probe: ActualDiffProbe = stub_probe
    actual = probe()
    result = verify_scope_assertion(
        affected_files=("src/foo.py",),
        scope_expanded_to=(),
        actual_files=actual,
    )
    assert result.is_violation is False


# --------------------------------------------------------------------------- #
# AC-7 — _main CLI smoke (unit-level; full integration in test_hooks.py)       #
# --------------------------------------------------------------------------- #


def test_main_clean_path_exit_zero(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _init_git_repo(tmp_path)
    _commit_files(repo, {"src/foo.py": "x = 1\n"}, "feat: foo")
    rs = _write_run_state(repo, affected_files=["src/foo.py"])
    rc = _main([
        "--run-state", str(rs),
        "--repo-root", str(repo),
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "scope-assertion: clean" in captured.out


def test_main_violation_path_exit_one(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _init_git_repo(tmp_path)
    _commit_files(
        repo,
        {"src/foo.py": "x = 1\n", "src/baz.py": "z = 3\n"},
        "feat: foo + undeclared baz",
    )
    rs = _write_run_state(repo, affected_files=["src/foo.py"])
    rc = _main([
        "--run-state", str(rs),
        "--repo-root", str(repo),
    ])
    captured = capsys.readouterr()
    assert rc == 1
    assert "scope-assertion-violation" in captured.err
    assert "src/baz.py" in captured.err
    assert "review Dev's diff vs. declared scope" in captured.err


def test_main_no_retry_in_flight_short_circuits_to_exit_zero(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _init_git_repo(tmp_path)
    _commit_files(repo, {"src/foo.py": "x = 1\n"}, "feat: foo")
    rs = _write_run_state(repo, last_retry_directive_present=False)
    rc = _main([
        "--run-state", str(rs),
        "--repo-root", str(repo),
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "scope-assertion: clean" in captured.out


def test_main_missing_run_state_exits_zero(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _init_git_repo(tmp_path)
    rc = _main([
        "--run-state", str(repo / "no-such-file.yaml"),
        "--repo-root", str(repo),
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "not found" in captured.err


def test_main_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _main(["--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "scope-assertion-verify" in captured.out


# --------------------------------------------------------------------------- #
# Module-level invariants                                                     #
# --------------------------------------------------------------------------- #


def test_module_all_exports_alphabetically_sorted() -> None:
    from loud_fail_harness import scope_assertion as mod

    assert list(mod.__all__) == sorted(mod.__all__)
    expected = {
        "ActualDiffProbe",
        "ScopeAssertionDiagnostic",
        "ScopeAssertionProbeError",
        "ScopeAssertionResult",
        "ScopeAssertionViolation",
        "default_actual_diff_probe",
        "make_scope_assertion_diagnostic",
        "verify_scope_assertion",
    }
    assert set(mod.__all__) == expected


def test_scope_assertion_violation_carries_diagnostic() -> None:
    diagnostic = make_scope_assertion_diagnostic(
        _make_violation_result(), story_id="5-4-test", retry_round=1
    )
    exc = ScopeAssertionViolation(diagnostic)
    assert exc.diagnostic is diagnostic
    assert exc.marker_class == "scope-assertion-violation"
    assert "src/baz.py" in str(exc)
    assert "review Dev's diff vs. declared scope" in str(exc)


def test_scope_assertion_probe_error_is_value_error() -> None:
    """ProbeError is value-domain (ValueError lineage); Violation is flow-domain."""
    assert issubclass(ScopeAssertionProbeError, ValueError)
    assert not issubclass(ScopeAssertionViolation, ValueError)
