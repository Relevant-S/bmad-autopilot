"""Contract-coverage matrix for the hook-budget CI gate (story 1.9).

This docstring IS the contract-coverage checklist required by AC-9. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to story 1.2 / 1.3 / 1.4 / 1.5
/ 1.6 / 1.7 / 1.8 AC discipline).

Baseline-zero classification cases (AC-2, AC-4, AC-5):
    [x] hooks/ does not exist                                     → test_baseline_zero_hooks_dir_does_not_exist
    [x] hooks/ exists but is empty                                → test_baseline_zero_hooks_dir_empty
    [x] one under-budget hook                                     → test_one_under_budget_hook
    [x] two under-budget hooks                                    → test_two_under_budget_hooks
    [x] exactly-three under-budget hooks (story-2.7 forward)      → test_exactly_three_under_budget_hooks

Count-violation cases (AC-2, AC-4, AC-5, AC-6):
    [x] four hooks → FR60 violation                               → test_four_hooks_fr60_violation
    [x] five hooks → FR60 violation                               → test_five_hooks_fr60_violation
    [x] count-finding lists ALL discovered names                  → test_count_finding_enumerates_all_names

Line-violation cases (AC-3, AC-4, AC-5, AC-6):
    [x] one over-budget hook (25 lines) → FR61 violation          → test_one_over_budget_hook_fr61_violation
    [x] two over-budget hooks → FR61 violations                   → test_two_over_budget_hooks_fr61_violations
    [x] over-budget at exactly 21 lines (boundary)                → test_line_violation_boundary_21_lines
    [x] under-budget at exactly 20 lines (boundary)               → test_passing_boundary_20_lines

Mixed-precedence (AC-5):
    [x] 4 hooks with one over-budget → BOTH fire, exit 1          → test_mixed_fr60_and_fr61_both_fire

Counting-rule edge cases (AC-3, AC-9):
    [x] shebang on line 1 skipped                                 → test_counting_rule_shebang_line1_skipped
    [x] no shebang, line 1 counted                                → test_counting_rule_no_shebang_line1_counted
    [x] line 1 looks like comment but not shebang                 → test_counting_rule_line1_comment_not_shebang
    [x] blank lines skipped                                       → test_counting_rule_blank_lines_skipped
    [x] whitespace-only lines skipped                             → test_counting_rule_whitespace_only_lines_skipped
    [x] comment-only lines skipped                                → test_counting_rule_comment_only_lines_skipped
    [x] indented comment-only lines skipped                       → test_counting_rule_indented_comment_only_skipped
    [x] code # inline comment counted as code                     → test_counting_rule_inline_comment_counted_as_code
    [x] heredoc body counted                                      → test_counting_rule_heredoc_body_counted
    [x] control-flow keywords counted                             → test_counting_rule_control_flow_keywords_counted
    [x] continuation backslash counted                            → test_counting_rule_continuation_backslash_counted
    [x] mid-file `#!/bin/sh`-shaped line treated as comment       → test_counting_rule_midfile_shebang_treated_as_comment
    [x] UTF-8 BOM before shebang still skipped (utf-8-sig read)  → test_counting_rule_bom_shebang_skipped

Hook-discovery edge cases (AC-2, AC-9):
    [x] subdirectory hook NOT discovered                          → test_subdirectory_hook_not_discovered
    [x] non-`.sh` file ignored                                    → test_non_sh_file_ignored
    [x] non-`.sh` substring file ignored (foo.shell)              → test_non_sh_substring_file_ignored
    [x] empty file (0 lines)                                      → test_empty_file_zero_lines
    [x] file with only shebang                                    → test_file_with_only_shebang_zero_lines
    [x] file with only comments and blanks                        → test_file_with_only_comments_and_blanks_zero_lines

Loud-fail / harness-level errors (AC-5, AC-9, Pattern 5):
    [x] unreadable file (chmod 000)                               → test_loud_fail_on_unreadable_file
    [x] non-UTF-8 file                                            → test_loud_fail_on_non_utf8_file
    [x] hooks_dir exists but unreadable (chmod 000)               → test_loud_fail_on_unreadable_hooks_dir

Doc-vs-implementation sync (AC-7, AC-9):
    [x] counting-rule doc worked-examples round-trip              → test_counting_rule_doc_in_sync

Determinism (AC-9):
    [x] run_hook_budget_gate is byte-identical across runs        → test_findings_deterministic
    [x] GateResult.model_dump_json byte-identical                 → test_gate_result_json_serialization_stable

Pydantic v2 frozen-model discipline (AC-9):
    [x] Reference frozen + hashable                               → test_reference_is_frozen_and_hashable
    [x] CountFinding frozen; not hashable (list[str] field)       → test_count_finding_frozen_not_hashable
    [x] LineFinding frozen + hashable                             → test_line_finding_is_frozen_and_hashable
    [x] GateResult frozen; not hashable (list fields)             → test_gate_result_frozen_not_hashable

CLI / main exit-code matrix (AC-5, AC-9):
    [x] canonical corpus baseline-zero (real hooks/ dir)          → test_canonical_corpus_baseline_zero
    [x] main --help resolves to argparse                          → test_main_help_resolves
    [x] main with custom --hooks-dir test-injection               → test_main_with_custom_hooks_dir

Coverage (AC-9):
    [x] hook_budget_gate.py module-level statement coverage ≥ 90% → review-enforced; not a CI gate
"""

from __future__ import annotations

import io
import os
import pathlib
import re
import sys

import pytest
from pydantic import ValidationError

from loud_fail_harness.hook_budget_gate import (
    CountFinding,
    GateResult,
    LineFinding,
    Reference,
    count_effective_lines,
    discover_hooks,
    main,
    run_hook_budget_gate,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _write_hook(
    path: pathlib.Path,
    *,
    body: str = "#!/bin/bash\necho hello\n",
) -> pathlib.Path:
    """Write ``body`` as UTF-8 to ``path``. Returns ``path`` for chaining."""
    path.write_text(body, encoding="utf-8")
    return path


def _make_hooks_dir(
    tmp_path: pathlib.Path,
    *,
    hooks: dict[str, str],
    create_dir: bool = True,
) -> pathlib.Path:
    """Create ``tmp_path/hooks/`` populated with ``{filename: body}``."""
    hooks_dir = tmp_path / "hooks"
    if create_dir:
        hooks_dir.mkdir(parents=True, exist_ok=True)
    for filename, body in hooks.items():
        # Allow callers to declare nested filenames (e.g. "subdir/foo.sh") by
        # creating intermediate directories.
        target = hooks_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_hook(target, body=body)
    return hooks_dir


def _capture_main(args: list[str]) -> tuple[int, str, str]:
    """Run ``main(args)`` capturing stdout + stderr."""
    out = io.StringIO()
    err = io.StringIO()
    saved_stdout = sys.stdout
    saved_stderr = sys.stderr
    sys.stdout = out
    sys.stderr = err
    try:
        rc = main(args)
    finally:
        sys.stdout = saved_stdout
        sys.stderr = saved_stderr
    return rc, out.getvalue(), err.getvalue()


def _under_budget_body(line_count: int) -> str:
    """Synthesize a hook body with ``line_count`` effective lines.

    Body shape: shebang on line 1 (skipped), then ``line_count`` lines each
    of the form ``echo lineN``. The shebang ensures the test exercises the
    line-1-skip path; the tail provides the requested effective-line count.
    """
    body_lines = ["#!/bin/bash"]
    for i in range(1, line_count + 1):
        body_lines.append(f"echo line{i}")
    return "\n".join(body_lines) + "\n"


# ---------------------------------------------------------------------------
# Baseline-zero classification cases (AC-2, AC-4, AC-5)
# ---------------------------------------------------------------------------


def test_baseline_zero_hooks_dir_does_not_exist(tmp_path: pathlib.Path) -> None:
    """No hooks/ directory → 0 passing, 0 violations, exit 0."""
    hooks_dir = tmp_path / "hooks"  # NOT created
    assert not hooks_dir.exists()
    rc, out, _ = _capture_main(["--hooks-dir", str(hooks_dir)])
    assert rc == 0
    assert (
        "Summary: 0 passing hook(s), 0 count-violation finding(s), "
        "0 line-violation finding(s)."
    ) in out


def test_baseline_zero_hooks_dir_empty(tmp_path: pathlib.Path) -> None:
    """Empty hooks/ directory → 0 passing, 0 violations, exit 0."""
    hooks_dir = _make_hooks_dir(tmp_path, hooks={})
    rc, out, _ = _capture_main(["--hooks-dir", str(hooks_dir)])
    assert rc == 0
    assert "Summary: 0 passing hook(s)" in out


def test_one_under_budget_hook(tmp_path: pathlib.Path) -> None:
    """1 under-budget hook → passing has 1 entry, no violations."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={"foo.sh": _under_budget_body(5)},
    )
    result = run_hook_budget_gate(hooks_dir)
    assert len(result.passing) == 1
    assert result.passing[0] == Reference(file_name="foo.sh", effective_line_count=5)
    assert result.count_violation == []
    assert result.line_violation == []


def test_two_under_budget_hooks(tmp_path: pathlib.Path) -> None:
    """2 under-budget hooks → passing sorted by file_name."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={
            "foo.sh": _under_budget_body(5),
            "bar.sh": _under_budget_body(15),
        },
    )
    result = run_hook_budget_gate(hooks_dir)
    assert [r.file_name for r in result.passing] == ["bar.sh", "foo.sh"]
    assert [r.effective_line_count for r in result.passing] == [15, 5]
    assert result.count_violation == []
    assert result.line_violation == []


def test_exactly_three_under_budget_hooks(tmp_path: pathlib.Path) -> None:
    """Story 2.7 forward simulation: canonical 3-hook set passes cleanly."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={
            "subagent-stop.sh": _under_budget_body(15),
            "stop.sh": _under_budget_body(10),
            "session-start.sh": _under_budget_body(5),
        },
    )
    result = run_hook_budget_gate(hooks_dir)
    assert [r.file_name for r in result.passing] == [
        "session-start.sh",
        "stop.sh",
        "subagent-stop.sh",
    ]
    assert result.count_violation == []
    assert result.line_violation == []


# ---------------------------------------------------------------------------
# Count-violation cases (AC-2, AC-4, AC-5, AC-6)
# ---------------------------------------------------------------------------


def test_four_hooks_fr60_violation(tmp_path: pathlib.Path) -> None:
    """4 under-budget .sh files → count_violation fires; line_violation empty."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={
            "alpha.sh": _under_budget_body(3),
            "beta.sh": _under_budget_body(3),
            "gamma.sh": _under_budget_body(3),
            "delta.sh": _under_budget_body(3),
        },
    )
    rc, out, _ = _capture_main(["--hooks-dir", str(hooks_dir)])
    assert rc == 1
    assert "Hook count exceeds budget: discovered 4 .sh files" in out
    assert "budget: 3 per FR60" in out
    assert "alpha.sh" in out
    assert "beta.sh" in out
    assert "gamma.sh" in out
    assert "delta.sh" in out
    # AC-6 row-1 remediation pointer (verbatim substring check).
    assert "≤3 hook budget is NOT revisitable" in out
    assert "0 line-violation finding(s)" in out


def test_five_hooks_fr60_violation(tmp_path: pathlib.Path) -> None:
    """5 under-budget .sh files → count_violation enumerates all 5 names."""
    names = [f"hook{i}.sh" for i in range(1, 6)]
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={n: _under_budget_body(2) for n in names},
    )
    result = run_hook_budget_gate(hooks_dir)
    assert len(result.count_violation) == 1
    cf = result.count_violation[0]
    assert cf.discovered_count == 5
    assert cf.discovered_names == sorted(names)
    assert cf.budget == 3


def test_count_finding_enumerates_all_names(tmp_path: pathlib.Path) -> None:
    """Discovered names are sorted lexicographically (determinism)."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={
            "z.sh": _under_budget_body(1),
            "a.sh": _under_budget_body(1),
            "m.sh": _under_budget_body(1),
            "b.sh": _under_budget_body(1),
        },
    )
    result = run_hook_budget_gate(hooks_dir)
    assert len(result.count_violation) == 1
    cf = result.count_violation[0]
    assert cf.discovered_names == ["a.sh", "b.sh", "m.sh", "z.sh"]


# ---------------------------------------------------------------------------
# Line-violation cases (AC-3, AC-4, AC-5, AC-6)
# ---------------------------------------------------------------------------


def test_one_over_budget_hook_fr61_violation(tmp_path: pathlib.Path) -> None:
    """1 over-budget hook (25 lines) → line_violation fires."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={"foo.sh": _under_budget_body(25)},
    )
    rc, out, _ = _capture_main(["--hooks-dir", str(hooks_dir)])
    assert rc == 1
    assert "Hook script exceeds line budget: foo.sh has 25 effective lines" in out
    assert "budget: 20 per FR61" in out
    assert "tools/loud-fail-harness/docs/hook-counting-rules.md" in out
    # AC-6 row-2 remediation pointer.
    assert "20-line bound is the hook-script-trust-model" in out
    assert "0 count-violation finding(s)" in out


def test_two_over_budget_hooks_fr61_violations(tmp_path: pathlib.Path) -> None:
    """2 over-budget hooks → line_violation has 2 entries sorted."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={
            "foo.sh": _under_budget_body(25),
            "bar.sh": _under_budget_body(30),
        },
    )
    result = run_hook_budget_gate(hooks_dir)
    assert len(result.line_violation) == 2
    assert [lf.file_name for lf in result.line_violation] == ["bar.sh", "foo.sh"]
    assert [lf.effective_line_count for lf in result.line_violation] == [30, 25]
    # Only 2 files → FR60 satisfied.
    assert result.count_violation == []


def test_line_violation_boundary_21_lines(tmp_path: pathlib.Path) -> None:
    """21 effective lines is over budget; emits a line_violation finding."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={"foo.sh": _under_budget_body(21)},
    )
    result = run_hook_budget_gate(hooks_dir)
    assert len(result.line_violation) == 1
    assert result.line_violation[0].effective_line_count == 21


def test_passing_boundary_20_lines(tmp_path: pathlib.Path) -> None:
    """20 effective lines is exactly at budget; passes cleanly."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={"foo.sh": _under_budget_body(20)},
    )
    result = run_hook_budget_gate(hooks_dir)
    assert len(result.passing) == 1
    assert result.passing[0].effective_line_count == 20
    assert result.line_violation == []


# ---------------------------------------------------------------------------
# Mixed-precedence (AC-5)
# ---------------------------------------------------------------------------


def test_mixed_fr60_and_fr61_both_fire(tmp_path: pathlib.Path) -> None:
    """4 hooks with one over-budget → BOTH FR60 + FR61 fire; exit 1."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={
            "alpha.sh": _under_budget_body(3),
            "beta.sh": _under_budget_body(3),
            "gamma.sh": _under_budget_body(25),
            "delta.sh": _under_budget_body(3),
        },
    )
    rc, out, _ = _capture_main(["--hooks-dir", str(hooks_dir)])
    assert rc == 1, "mixed violations must NOT promote to exit 2"
    assert "Hook count exceeds budget" in out
    assert "Hook script exceeds line budget: gamma.sh has 25 effective lines" in out
    assert "1 count-violation finding(s)" in out
    assert "1 line-violation finding(s)" in out


# ---------------------------------------------------------------------------
# Counting-rule edge cases (AC-3, AC-9)
# ---------------------------------------------------------------------------


def test_counting_rule_shebang_line1_skipped(tmp_path: pathlib.Path) -> None:
    p = _write_hook(tmp_path / "foo.sh", body="#!/bin/bash\necho foo\n")
    assert count_effective_lines(p) == 1


def test_counting_rule_no_shebang_line1_counted(tmp_path: pathlib.Path) -> None:
    p = _write_hook(tmp_path / "foo.sh", body="echo foo\necho bar\n")
    assert count_effective_lines(p) == 2


def test_counting_rule_line1_comment_not_shebang(tmp_path: pathlib.Path) -> None:
    """Line 1 starts with `#` but not `#!` → comment-only, NOT shebang."""
    p = _write_hook(tmp_path / "foo.sh", body="# regular comment\necho foo\n")
    assert count_effective_lines(p) == 1


def test_counting_rule_blank_lines_skipped(tmp_path: pathlib.Path) -> None:
    body = "\n\n\necho a\necho b\n\n\n\n"
    p = _write_hook(tmp_path / "foo.sh", body=body)
    assert count_effective_lines(p) == 2


def test_counting_rule_whitespace_only_lines_skipped(tmp_path: pathlib.Path) -> None:
    body = "\t\t\n   \n\necho only\n"
    p = _write_hook(tmp_path / "foo.sh", body=body)
    assert count_effective_lines(p) == 1


def test_counting_rule_comment_only_lines_skipped(tmp_path: pathlib.Path) -> None:
    body = (
        "# comment a\n# comment b\n# comment c\n# comment d\n# comment e\n"
        "echo a\necho b\necho c\n"
    )
    p = _write_hook(tmp_path / "foo.sh", body=body)
    assert count_effective_lines(p) == 3


def test_counting_rule_indented_comment_only_skipped(tmp_path: pathlib.Path) -> None:
    body = "    # nested comment\necho one\n"
    p = _write_hook(tmp_path / "foo.sh", body=body)
    assert count_effective_lines(p) == 1


def test_counting_rule_inline_comment_counted_as_code(tmp_path: pathlib.Path) -> None:
    body = "echo foo # this is an inline comment\n"
    p = _write_hook(tmp_path / "foo.sh", body=body)
    assert count_effective_lines(p) == 1


def test_counting_rule_heredoc_body_counted(tmp_path: pathlib.Path) -> None:
    body = "cat <<EOF\nline one\nline two\nline three\nEOF\n"
    p = _write_hook(tmp_path / "foo.sh", body=body)
    # 5 effective lines: `cat <<EOF`, three body lines, `EOF`.
    assert count_effective_lines(p) == 5


def test_counting_rule_control_flow_keywords_counted(tmp_path: pathlib.Path) -> None:
    body = "if true; then\n    echo a\nfi\nfor x in 1 2; do\n    echo $x\ndone\n"
    p = _write_hook(tmp_path / "foo.sh", body=body)
    # 6 effective lines (if/then, body, fi, for, body, done).
    assert count_effective_lines(p) == 6


def test_counting_rule_continuation_backslash_counted(tmp_path: pathlib.Path) -> None:
    body = "some_command \\\n    --flag value\n"
    p = _write_hook(tmp_path / "foo.sh", body=body)
    assert count_effective_lines(p) == 2


def test_counting_rule_midfile_shebang_treated_as_comment(
    tmp_path: pathlib.Path,
) -> None:
    """A `#!`-shaped line at line 2+ is a comment-only line, not a shebang."""
    body = "echo foo\n#!/bin/sh\necho bar\n"
    p = _write_hook(tmp_path / "foo.sh", body=body)
    assert count_effective_lines(p) == 2


def test_counting_rule_bom_shebang_skipped(tmp_path: pathlib.Path) -> None:
    """UTF-8 BOM before shebang is stripped by utf-8-sig; shebang is still skipped."""
    target = tmp_path / "foo.sh"
    # Write BOM (0xEF 0xBB 0xBF) followed by the shebang and one code line.
    target.write_bytes(b"\xef\xbb\xbf#!/bin/bash\necho foo\n")
    assert count_effective_lines(target) == 1


# ---------------------------------------------------------------------------
# Hook-discovery edge cases (AC-2, AC-9)
# ---------------------------------------------------------------------------


def test_subdirectory_hook_not_discovered(tmp_path: pathlib.Path) -> None:
    """hooks/subdir/foo.sh is NOT discovered (top-level glob only)."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={"subdir/foo.sh": _under_budget_body(3)},
    )
    discovered = discover_hooks(hooks_dir)
    assert discovered == []
    rc, out, _ = _capture_main(["--hooks-dir", str(hooks_dir)])
    assert rc == 0
    assert "0 passing hook(s)" in out


def test_non_sh_file_ignored(tmp_path: pathlib.Path) -> None:
    """Non-`.sh` files are silently ignored (top-level glob filters by suffix)."""
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "README.md").write_text("# README\n", encoding="utf-8")
    _write_hook(hooks_dir / "foo.sh", body=_under_budget_body(15))
    result = run_hook_budget_gate(hooks_dir)
    assert [r.file_name for r in result.passing] == ["foo.sh"]


def test_non_sh_substring_file_ignored(tmp_path: pathlib.Path) -> None:
    """`*.sh` is exact-suffix; `foo.shell` is NOT discovered."""
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    _write_hook(hooks_dir / "foo.shell", body="echo foo\n")
    _write_hook(hooks_dir / "bar.sh", body=_under_budget_body(2))
    discovered = discover_hooks(hooks_dir)
    assert [p.name for p in discovered] == ["bar.sh"]


def test_empty_file_zero_lines(tmp_path: pathlib.Path) -> None:
    """Empty file → 0 effective lines; passes."""
    hooks_dir = _make_hooks_dir(tmp_path, hooks={"foo.sh": ""})
    result = run_hook_budget_gate(hooks_dir)
    assert len(result.passing) == 1
    assert result.passing[0].effective_line_count == 0


def test_file_with_only_shebang_zero_lines(tmp_path: pathlib.Path) -> None:
    hooks_dir = _make_hooks_dir(tmp_path, hooks={"foo.sh": "#!/bin/bash\n"})
    result = run_hook_budget_gate(hooks_dir)
    assert result.passing[0].effective_line_count == 0


def test_file_with_only_comments_and_blanks_zero_lines(
    tmp_path: pathlib.Path,
) -> None:
    body = "#!/bin/bash\n# comment\n\n# another\n"
    hooks_dir = _make_hooks_dir(tmp_path, hooks={"foo.sh": body})
    result = run_hook_budget_gate(hooks_dir)
    assert result.passing[0].effective_line_count == 0


# ---------------------------------------------------------------------------
# Loud-fail / harness-level errors (AC-5, AC-9, Pattern 5)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "getuid") and os.getuid() == 0),
    reason="chmod 000 doesn't deny read on Windows or when running as root",
)
def test_loud_fail_on_unreadable_file(tmp_path: pathlib.Path) -> None:
    """A `.sh` file with chmod 000 → exit 2 with named stderr message."""
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    target = hooks_dir / "foo.sh"
    _write_hook(target, body=_under_budget_body(2))
    os.chmod(target, 0o000)
    try:
        rc, _, err = _capture_main(["--hooks-dir", str(hooks_dir)])
    finally:
        os.chmod(target, 0o644)  # restore so tmp_path cleanup succeeds
    assert rc == 2
    assert "harness-level error: hook file unreadable" in err
    assert str(target) in err


def test_loud_fail_on_non_utf8_file(tmp_path: pathlib.Path) -> None:
    """Non-UTF-8 bytes in a `.sh` file → exit 2 with named stderr message."""
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    target = hooks_dir / "foo.sh"
    target.write_bytes(b"\xff\xfe\x00invalid")
    rc, _, err = _capture_main(["--hooks-dir", str(hooks_dir)])
    assert rc == 2
    assert "harness-level error: hook file not UTF-8" in err
    assert str(target) in err


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "getuid") and os.getuid() == 0),
    reason="chmod 000 doesn't deny read on Windows or when running as root",
)
def test_loud_fail_on_unreadable_hooks_dir(tmp_path: pathlib.Path) -> None:
    """hooks/ with chmod 000 → exit 2 with `hooks/ directory unreadable`."""
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    _write_hook(hooks_dir / "foo.sh", body=_under_budget_body(2))
    os.chmod(hooks_dir, 0o000)
    try:
        rc, _, err = _capture_main(["--hooks-dir", str(hooks_dir)])
    finally:
        os.chmod(hooks_dir, 0o755)  # restore so tmp_path cleanup succeeds
    assert rc == 2
    assert "harness-level error: hooks/ directory unreadable" in err


# ---------------------------------------------------------------------------
# Doc-vs-implementation sync (AC-7, AC-9)
# ---------------------------------------------------------------------------


def _doc_path() -> pathlib.Path:
    """Resolve the canonical hook-counting-rules.md from disk."""
    from loud_fail_harness._shared import find_repo_root

    return (
        find_repo_root()
        / "tools"
        / "loud-fail-harness"
        / "docs"
        / "hook-counting-rules.md"
    )


def _parse_doc_examples(doc_text: str) -> list[tuple[str, int]]:
    """Extract (snippet, expected_count) pairs from the doc's worked examples.

    Uses a single regex that anchors each ```bash block to its immediately
    following ``Expected count: N`` line so that unrelated bash blocks
    elsewhere in the doc (e.g. cross-references, future prose additions)
    are not accidentally paired with an ``Expected count:`` line.

    Avoids introducing a markdown-parser dependency (Dev Notes hint:
    "a simple regex is sufficient; do NOT add a markdown-parser dependency").
    """
    pairs = re.findall(
        r"```bash\n(.*?)```\s+Expected count:\s*(\d+)",
        doc_text,
        flags=re.DOTALL,
    )
    assert pairs, (
        "no (snippet, expected_count) pairs found in hook-counting-rules.md; "
        "check that each ```bash block is immediately followed by "
        "'Expected count: N'"
    )
    return [(snippet, int(count)) for snippet, count in pairs]


def test_counting_rule_doc_in_sync(tmp_path: pathlib.Path) -> None:
    """Each (snippet, expected) pair in the doc round-trips through count_effective_lines."""
    doc = _doc_path()
    assert doc.is_file(), f"doc not found: {doc}"
    examples = _parse_doc_examples(doc.read_text(encoding="utf-8"))
    # AC-7 requires ≥ 6 examples; we author with at least 6 and assert the
    # contract here so future doc edits can't accidentally drop the floor.
    assert len(examples) >= 6, (
        f"hook-counting-rules.md must contain ≥6 worked examples; found "
        f"{len(examples)}"
    )
    for idx, (snippet, expected) in enumerate(examples):
        target = tmp_path / f"example_{idx}.sh"
        target.write_text(snippet, encoding="utf-8")
        actual = count_effective_lines(target)
        assert actual == expected, (
            f"example #{idx}: snippet={snippet!r} expected={expected} "
            f"actual={actual} — doc and count_effective_lines have drifted"
        )


# ---------------------------------------------------------------------------
# Determinism (AC-9)
# ---------------------------------------------------------------------------


def test_findings_deterministic(tmp_path: pathlib.Path) -> None:
    """Two invocations on the same input produce identical results."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={
            "z.sh": _under_budget_body(25),
            "a.sh": _under_budget_body(5),
            "m.sh": _under_budget_body(30),
            "b.sh": _under_budget_body(10),
            "c.sh": _under_budget_body(15),
        },
    )
    first = run_hook_budget_gate(hooks_dir)
    second = run_hook_budget_gate(hooks_dir)
    assert first == second


def test_gate_result_json_serialization_stable(tmp_path: pathlib.Path) -> None:
    """``model_dump_json()`` is byte-identical across runs on the same input."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={
            "alpha.sh": _under_budget_body(5),
            "beta.sh": _under_budget_body(25),
            "gamma.sh": _under_budget_body(30),
            "delta.sh": _under_budget_body(3),
        },
    )
    first = run_hook_budget_gate(hooks_dir).model_dump_json()
    second = run_hook_budget_gate(hooks_dir).model_dump_json()
    assert first == second
    # Sanity-check field order in the serialized form (load-bearing for
    # determinism per AC-4).
    passing_idx = first.index('"passing"')
    count_idx = first.index('"count_violation"')
    line_idx = first.index('"line_violation"')
    assert passing_idx < count_idx < line_idx


# ---------------------------------------------------------------------------
# Pydantic v2 frozen-model discipline (AC-9)
# ---------------------------------------------------------------------------


def test_reference_is_frozen_and_hashable() -> None:
    ref = Reference(file_name="foo.sh", effective_line_count=5)
    with pytest.raises(ValidationError):
        ref.file_name = "bar.sh"  # type: ignore[misc]
    assert hash(ref) == hash(Reference(file_name="foo.sh", effective_line_count=5))


def test_count_finding_frozen_not_hashable() -> None:
    """CountFinding is frozen (assignment raises) but NOT hashable (list[str] field).

    ``frozen=True`` prevents field reassignment; it does NOT make models with
    ``list[str]`` fields hashable — ``hash([...])`` raises ``TypeError``.
    The frozen-assignment invariant is the load-bearing determinism guarantee.
    """
    cf = CountFinding(discovered_count=4, discovered_names=["a.sh", "b.sh"])
    with pytest.raises(ValidationError):
        cf.discovered_count = 5  # type: ignore[misc]
    assert cf.budget == 3
    with pytest.raises(TypeError):
        hash(cf)


def test_line_finding_is_frozen_and_hashable() -> None:
    lf = LineFinding(file_name="foo.sh", effective_line_count=25)
    with pytest.raises(ValidationError):
        lf.effective_line_count = 26  # type: ignore[misc]
    assert lf.budget == 20
    assert hash(lf) == hash(
        LineFinding(file_name="foo.sh", effective_line_count=25)
    )


def test_gate_result_frozen_not_hashable() -> None:
    """GateResult is frozen (assignment raises) but NOT hashable (three list fields).

    Same posture as ``CountFinding``: frozen prevents field reassignment;
    list-bearing models are not hashable.
    """
    result = GateResult(passing=[], count_violation=[], line_violation=[])
    with pytest.raises(ValidationError):
        result.passing = [Reference(file_name="x.sh", effective_line_count=1)]  # type: ignore[misc]
    with pytest.raises(TypeError):
        hash(result)


# ---------------------------------------------------------------------------
# CLI / main exit-code matrix (AC-5, AC-9)
# ---------------------------------------------------------------------------


def test_canonical_corpus_baseline_zero() -> None:
    """At story 2.7's landing time the canonical hooks/ dir contains the
    three architecturally documented hook scripts (subagent-stop.sh,
    stop.sh, session-start.sh) per architecture.md View 1 lines
    1073-1076. The gate's CORRECT POSTURE on the canonical corpus is
    exit 0 with 3 passing hooks, 0 count violations, 0 line violations.

    The test does NOT use ``tmp_path``; it uses the actual canonical
    ``hooks/`` directory via ``find_repo_root``.
    """
    rc, out, err = _capture_main([])
    assert rc == 0, f"stdout: {out}\nstderr: {err}"
    assert "3 passing hook(s)" in out
    assert "0 count-violation finding(s)" in out
    assert "0 line-violation finding(s)" in out


def test_main_help_resolves(capsys: pytest.CaptureFixture[str]) -> None:
    """``main(['--help'])`` raises SystemExit(0) and prints expected help text."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--hooks-dir" in captured.out
    assert "tools/loud-fail-harness/docs/hook-counting-rules.md" in captured.out


def test_main_with_custom_hooks_dir(tmp_path: pathlib.Path) -> None:
    """``main(['--hooks-dir', X])`` uses the custom path, not ``find_repo_root``."""
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={"foo.sh": _under_budget_body(7)},
    )
    rc, out, _ = _capture_main(["--hooks-dir", str(hooks_dir)])
    assert rc == 0
    assert "1 passing hook(s)" in out
    # The display path may render absolute (tmp_path is outside the repo);
    # verify the header at least mentions the directory in some form.
    assert str(hooks_dir.resolve()) in out or "hooks" in out


# ---------------------------------------------------------------------------
# Discover-hooks unit tests (AC-2 directly — fine-grained vs. CLI tests)
# ---------------------------------------------------------------------------


def test_discover_hooks_returns_empty_for_missing_dir(
    tmp_path: pathlib.Path,
) -> None:
    """Missing dir → []; this is the loud-fail-correct response, not a raise."""
    missing = tmp_path / "nonexistent"
    assert discover_hooks(missing) == []


def test_discover_hooks_sorts_lexicographically(tmp_path: pathlib.Path) -> None:
    hooks_dir = _make_hooks_dir(
        tmp_path,
        hooks={
            "z.sh": _under_budget_body(1),
            "a.sh": _under_budget_body(1),
            "m.sh": _under_budget_body(1),
        },
    )
    discovered = discover_hooks(hooks_dir)
    assert [p.name for p in discovered] == ["a.sh", "m.sh", "z.sh"]
