"""Contract-coverage matrix for the no-destructive-resume CI lint gate (Story 8.6).

This docstring IS the contract-coverage checklist required by AC-9. Reviewers
verify every row maps to at least one passing test in this module. The matrix
mirrors :mod:`tests.test_pluggability_gate`'s synthesized-fixture posture but
synthesizes Python source modules instead of markdown agents.

AC-3 — Rule A (import-missing) (3):
    [x] test_lint_emits_a_finding_when_import_missing_in_resume_command
    [x] test_lint_emits_a_finding_when_import_missing_in_session_start_reattach
    [x] test_lint_does_not_emit_a_for_cross_state_recovery_since_excluded_from_rule_a

AC-3 — Rule B (callsite-missing) (3):
    [x] test_lint_emits_b_finding_when_evaluate_resume_lacks_can_dispatch_call
    [x] test_lint_emits_b_finding_when_evaluate_reattach_lacks_can_dispatch_call
    [x] test_lint_does_not_emit_b_for_evaluate_recovery_since_not_in_rule_b_allowlist

AC-3 — Rule C (inline-reintroduced) (3):
    [x] test_lint_emits_c_finding_when_underscore_can_dispatch_inline_function_def_present
    [x] test_lint_emits_c_finding_when_underscore_can_dispatch_inline_call_site_present
    [x] test_lint_scans_all_files_under_loud_fail_harness_for_rule_c

AC-3 / AC-9 — Happy path + CLI (4):
    [x] test_lint_returns_zero_findings_on_clean_repo
    [x] test_main_exits_zero_on_no_findings
    [x] test_main_exits_one_on_findings
    [x] test_governed_modules_constant_equals_documented_three_element_tuple
"""

from __future__ import annotations

import pathlib

import pytest

from loud_fail_harness.no_destructive_resume_lint import (
    _GOVERNED_MODULES,
    main,
    run_no_destructive_resume_lint,
)


# --------------------------------------------------------------------------- #
# Synthesized-fixture helpers                                                 #
# --------------------------------------------------------------------------- #


_CONFORMANT_RESUME_COMMAND = '''\
"""Synthesized resume_command.py — conformant for Rules A and B."""
from .no_destructive_resume_guard import Verdict, can_dispatch


def evaluate_resume(request, *, marker_registry=None):
    """Mock evaluate_resume that consumes can_dispatch."""
    run_state = None
    verdict = can_dispatch("dev", request.story_id, run_state)
    return verdict
'''


_CONFORMANT_SESSION_START_REATTACH = '''\
"""Synthesized session_start_reattach.py — conformant for Rules A and B."""
from .no_destructive_resume_guard import Verdict, can_dispatch


def evaluate_reattach(request):
    """Mock evaluate_reattach that consumes can_dispatch."""
    run_state = None
    verdict = can_dispatch("dev", request.story_id, run_state)
    return verdict
'''


_CONFORMANT_CROSS_STATE_RECOVERY = '''\
"""Synthesized cross_state_recovery.py — docstring-only delegation, NO import,
NO callsite per AC-4."""


def evaluate_recovery(request):
    """Reconciliation only; dispatch is downstream — no can_dispatch needed."""
    return None
'''


_CONFORMANT_GUARD_STUB = '''\
"""Synthesized no_destructive_resume_guard.py — minimal stub for fixture."""
from typing import Literal


class Verdict:
    pass


def can_dispatch(specialist, story_id, run_state):
    return Verdict()
'''


def _write_conformant_harness(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a tmp_path-rooted harness mirror with all three governed
    modules conformant per Story 8.6's post-landing expected state.
    Returns the harness root (suitable for ``run_no_destructive_resume_lint``).
    """
    src = tmp_path / "src" / "loud_fail_harness"
    src.mkdir(parents=True)
    (src / "no_destructive_resume_guard.py").write_text(
        _CONFORMANT_GUARD_STUB, encoding="utf-8"
    )
    (src / "resume_command.py").write_text(
        _CONFORMANT_RESUME_COMMAND, encoding="utf-8"
    )
    (src / "session_start_reattach.py").write_text(
        _CONFORMANT_SESSION_START_REATTACH, encoding="utf-8"
    )
    (src / "cross_state_recovery.py").write_text(
        _CONFORMANT_CROSS_STATE_RECOVERY, encoding="utf-8"
    )
    return tmp_path


# --------------------------------------------------------------------------- #
# AC-3 — Rule A (import-missing)                                              #
# --------------------------------------------------------------------------- #


def test_lint_emits_a_finding_when_import_missing_in_resume_command(
    tmp_path: pathlib.Path,
) -> None:
    harness_root = _write_conformant_harness(tmp_path)
    src = harness_root / "src" / "loud_fail_harness"
    # Strip the Rule-A import.
    (src / "resume_command.py").write_text(
        '"""resume_command.py without canonical import."""\n'
        "def evaluate_resume(request, *, marker_registry=None):\n"
        "    return None\n",
        encoding="utf-8",
    )

    result = run_no_destructive_resume_lint(harness_root)
    a_findings = [f for f in result.findings if f.rule == "A-import-missing"]
    assert any(
        f.file_path.name == "resume_command.py" for f in a_findings
    ), result.findings


def test_lint_emits_a_finding_when_import_missing_in_session_start_reattach(
    tmp_path: pathlib.Path,
) -> None:
    harness_root = _write_conformant_harness(tmp_path)
    src = harness_root / "src" / "loud_fail_harness"
    (src / "session_start_reattach.py").write_text(
        '"""session_start_reattach.py without canonical import."""\n'
        "def evaluate_reattach(request):\n"
        "    return None\n",
        encoding="utf-8",
    )

    result = run_no_destructive_resume_lint(harness_root)
    a_findings = [f for f in result.findings if f.rule == "A-import-missing"]
    assert any(
        f.file_path.name == "session_start_reattach.py" for f in a_findings
    ), result.findings


def test_lint_does_not_emit_a_for_cross_state_recovery_since_excluded_from_rule_a(
    tmp_path: pathlib.Path,
) -> None:
    """``cross_state_recovery.py`` per AC-4 has a docstring-only update —
    NO import, NO callsite. Rule A's allowlist excludes it; the gate
    must NOT emit an A-finding for cross_state_recovery."""
    harness_root = _write_conformant_harness(tmp_path)
    # The conformant fixture deliberately omits the import in
    # cross_state_recovery.py; assert no A-finding fires.

    result = run_no_destructive_resume_lint(harness_root)
    a_findings = [
        f
        for f in result.findings
        if f.rule == "A-import-missing"
        and f.file_path.name == "cross_state_recovery.py"
    ]
    assert a_findings == []


# --------------------------------------------------------------------------- #
# AC-3 — Rule B (callsite-missing)                                            #
# --------------------------------------------------------------------------- #


def test_lint_emits_b_finding_when_evaluate_resume_lacks_can_dispatch_call(
    tmp_path: pathlib.Path,
) -> None:
    harness_root = _write_conformant_harness(tmp_path)
    src = harness_root / "src" / "loud_fail_harness"
    # Import present BUT body lacks the call.
    (src / "resume_command.py").write_text(
        '"""resume_command.py with import but no callsite."""\n'
        "from .no_destructive_resume_guard import can_dispatch\n\n\n"
        "def evaluate_resume(request, *, marker_registry=None):\n"
        "    return None\n",
        encoding="utf-8",
    )

    result = run_no_destructive_resume_lint(harness_root)
    b_findings = [f for f in result.findings if f.rule == "B-callsite-missing"]
    assert any(
        "evaluate_resume" in f.diagnostic for f in b_findings
    ), result.findings


def test_lint_emits_b_finding_when_evaluate_reattach_lacks_can_dispatch_call(
    tmp_path: pathlib.Path,
) -> None:
    harness_root = _write_conformant_harness(tmp_path)
    src = harness_root / "src" / "loud_fail_harness"
    (src / "session_start_reattach.py").write_text(
        '"""session_start_reattach.py with import but no callsite."""\n'
        "from .no_destructive_resume_guard import can_dispatch\n\n\n"
        "def evaluate_reattach(request):\n"
        "    return None\n",
        encoding="utf-8",
    )

    result = run_no_destructive_resume_lint(harness_root)
    b_findings = [f for f in result.findings if f.rule == "B-callsite-missing"]
    assert any(
        "evaluate_reattach" in f.diagnostic for f in b_findings
    ), result.findings


def test_lint_does_not_emit_b_for_evaluate_recovery_since_not_in_rule_b_allowlist(
    tmp_path: pathlib.Path,
) -> None:
    """Rule B's allowlist is ``{"evaluate_resume", "evaluate_reattach"}``.
    ``evaluate_recovery`` is intentionally excluded — recovery is
    reconciliation, NOT dispatch. Adding a function named evaluate_recovery
    that does NOT call can_dispatch must NOT trigger Rule B."""
    harness_root = _write_conformant_harness(tmp_path)
    # The conformant cross_state_recovery fixture defines evaluate_recovery
    # without can_dispatch — assert no B-finding for it.

    result = run_no_destructive_resume_lint(harness_root)
    b_findings = [
        f
        for f in result.findings
        if f.rule == "B-callsite-missing"
        and "evaluate_recovery" in f.diagnostic
    ]
    assert b_findings == []


# --------------------------------------------------------------------------- #
# AC-3 — Rule C (inline-reintroduced)                                         #
# --------------------------------------------------------------------------- #


def test_lint_emits_c_finding_when_underscore_can_dispatch_inline_function_def_present(
    tmp_path: pathlib.Path,
) -> None:
    """Rule C — regression guard against re-introduction of the inline
    FunctionDef in any module under loud_fail_harness/."""
    harness_root = _write_conformant_harness(tmp_path)
    src = harness_root / "src" / "loud_fail_harness"
    # Add an extra module that re-introduces the forbidden FunctionDef.
    (src / "experimental_module.py").write_text(
        '"""Experimental module — regression: forbidden inline def."""\n\n\n'
        "def _can_dispatch_inline(specialist, story_id, run_state):\n"
        "    return True\n",
        encoding="utf-8",
    )

    result = run_no_destructive_resume_lint(harness_root)
    c_findings = [f for f in result.findings if f.rule == "C-inline-reintroduced"]
    assert any(
        f.file_path.name == "experimental_module.py" for f in c_findings
    ), result.findings


def test_lint_emits_c_finding_when_underscore_can_dispatch_inline_call_site_present(
    tmp_path: pathlib.Path,
) -> None:
    """Rule C — regression guard against re-introduction of the inline
    Call site in any module under loud_fail_harness/."""
    harness_root = _write_conformant_harness(tmp_path)
    src = harness_root / "src" / "loud_fail_harness"
    (src / "experimental_module.py").write_text(
        '"""Experimental module — regression: forbidden call site."""\n\n\n'
        "def something(rs):\n"
        "    return _can_dispatch_inline('dev', '8-6', rs)\n",
        encoding="utf-8",
    )

    result = run_no_destructive_resume_lint(harness_root)
    c_findings = [f for f in result.findings if f.rule == "C-inline-reintroduced"]
    assert any(
        f.file_path.name == "experimental_module.py" for f in c_findings
    ), result.findings


def test_lint_scans_all_files_under_loud_fail_harness_for_rule_c(
    tmp_path: pathlib.Path,
) -> None:
    """Rule C must scan EVERY ``.py`` file under
    ``src/loud_fail_harness/`` — not just the governed-modules allowlist.
    The forbidden inline pattern in a NEW module (not in
    ``_GOVERNED_MODULES``) MUST be detected."""
    harness_root = _write_conformant_harness(tmp_path)
    src = harness_root / "src" / "loud_fail_harness"
    # Add module not in _GOVERNED_MODULES.
    (src / "completely_unrelated.py").write_text(
        '"""Module not in _GOVERNED_MODULES — Rule C must still detect."""\n\n\n'
        "def _can_dispatch_inline(specialist, story_id, run_state):\n"
        "    return True\n",
        encoding="utf-8",
    )

    result = run_no_destructive_resume_lint(harness_root)
    c_findings = [f for f in result.findings if f.rule == "C-inline-reintroduced"]
    file_names = {f.file_path.name for f in c_findings}
    assert "completely_unrelated.py" in file_names


# --------------------------------------------------------------------------- #
# AC-3 / AC-9 — Happy path + CLI                                              #
# --------------------------------------------------------------------------- #


def test_lint_returns_zero_findings_on_clean_repo(
    tmp_path: pathlib.Path,
) -> None:
    """The conformant fixture matches the post-Story-8.6 expected state —
    all three governed modules conformant; assert findings=()."""
    harness_root = _write_conformant_harness(tmp_path)
    result = run_no_destructive_resume_lint(harness_root)
    assert result.findings == ()
    assert result.governed_modules_scanned == _GOVERNED_MODULES


def test_main_exits_zero_on_no_findings(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    harness_root = _write_conformant_harness(tmp_path)
    rc = main(["--harness-root", str(harness_root)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "0 findings" in captured.out
    assert "3 governed modules scanned" in captured.out


def test_main_exits_one_on_findings(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    harness_root = _write_conformant_harness(tmp_path)
    src = harness_root / "src" / "loud_fail_harness"
    # Drop the import to force a Rule-A finding.
    (src / "resume_command.py").write_text(
        '"""no import."""\ndef evaluate_resume(r):\n    return None\n',
        encoding="utf-8",
    )
    rc = main(["--harness-root", str(harness_root)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "no-destructive-resume-lint:" in captured.out
    assert "A-import-missing" in captured.out


def test_governed_modules_constant_equals_documented_three_element_tuple() -> None:
    """The closed allowlist invariant per AC-3: exactly the three
    epics.md:3384-enumerated modules. Adding a fourth governed module is
    a future-story extension."""
    assert _GOVERNED_MODULES == (
        "session_start_reattach",
        "cross_state_recovery",
        "resume_command",
    )


# --------------------------------------------------------------------------- #
# Substrate-error behavior                                                    #
# --------------------------------------------------------------------------- #


def test_main_exits_two_when_governed_module_missing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """If a governed module is absent under
    ``<harness_root>/src/loud_fail_harness/``, surface a harness-level
    error (exit 2)."""
    src = tmp_path / "src" / "loud_fail_harness"
    src.mkdir(parents=True)
    # Only create one of the three governed modules; the lint MUST
    # detect the absence.
    (src / "no_destructive_resume_guard.py").write_text(
        _CONFORMANT_GUARD_STUB, encoding="utf-8"
    )
    (src / "resume_command.py").write_text(
        _CONFORMANT_RESUME_COMMAND, encoding="utf-8"
    )
    # Intentionally omit session_start_reattach.py and cross_state_recovery.py.
    rc = main(["--harness-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "harness-level error" in captured.err


def test_lint_finding_carries_line_number_for_b_findings(
    tmp_path: pathlib.Path,
) -> None:
    """Rule B finding's line_number matches the offending FunctionDef's
    lineno (so CI logs point at the violating function)."""
    harness_root = _write_conformant_harness(tmp_path)
    src = harness_root / "src" / "loud_fail_harness"
    body = (
        '"""resume_command.py with import but no callsite — three blank lines."""\n'
        "from .no_destructive_resume_guard import can_dispatch\n"
        "\n"
        "\n"
        "def evaluate_resume(request, *, marker_registry=None):\n"
        "    return None\n"
    )
    (src / "resume_command.py").write_text(body, encoding="utf-8")

    result = run_no_destructive_resume_lint(harness_root)
    b_findings = [f for f in result.findings if f.rule == "B-callsite-missing"]
    assert len(b_findings) >= 1
    # The function def is at line 5 (1: docstring; 2: import; 3-4: blanks; 5: def).
    assert b_findings[0].line_number == 5


def test_lint_findings_are_sorted_deterministically(
    tmp_path: pathlib.Path,
) -> None:
    """LintResult.findings ordered by (file_path, line_number, rule)
    for byte-stable output (parallel to pluggability_gate's sort)."""
    harness_root = _write_conformant_harness(tmp_path)
    src = harness_root / "src" / "loud_fail_harness"
    # Inject violations in two files at distinct positions.
    (src / "resume_command.py").write_text(
        '"""no import; no callsite."""\n'
        "def evaluate_resume(r):\n"
        "    return None\n",
        encoding="utf-8",
    )
    (src / "session_start_reattach.py").write_text(
        '"""no import; no callsite."""\n'
        "def evaluate_reattach(r):\n"
        "    return None\n",
        encoding="utf-8",
    )

    result = run_no_destructive_resume_lint(harness_root)
    keys = [(str(f.file_path), f.line_number, f.rule) for f in result.findings]
    assert keys == sorted(keys)


# --------------------------------------------------------------------------- #
# Defensive — find_repo_root() is never called at module collection time     #
# --------------------------------------------------------------------------- #


def test_no_find_repo_root_call_at_module_collection_time() -> None:
    """Epic 1 retro Action #1 discipline: ``find_repo_root()`` MUST NOT be
    invoked at module collection time. THIS test module's import MUST
    succeed even when the cwd is a tmp_path that is NOT a git repo;
    pytest's collection is the smoke-check."""
    # Reaching this point means the module imported cleanly under
    # pytest's collection — that IS the assertion.
    assert run_no_destructive_resume_lint is not None
