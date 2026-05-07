"""Contract-coverage matrix for bundle_assembly_failure_emission_gate (Story 6.9 AC-4).

This docstring IS the contract-coverage checklist required by AC-4 +
AC-6 (g)-(j) of Story 6.9. Reviewers verify every row maps to at least
one passing test. The matrix is review-enforced, NOT CI-enforced.

The gate is a structural CI lint that scans the harness source tree
for forbidden direct emission paths that bypass the canonical
`surface_assembly_failure` source-of-truth function. Two forbidden
patterns:
    (a) literal occurrence of ``"bundle-assembly-failed"`` marker class string
    (b) direct mention of the ``*.assembly-failure.log`` fallback-file suffix

AC-6 (g)-(j) test-coverage matrix:
    [x] (g) clean repo (no violations) → exit 0; empty findings tuple
        → test_post_story_6_9_source_tree_is_exit_zero_clean
    [x] (h) synthetic-violation injection → finding emitted with file_path
        + line number + matched_text; main exits 1
        → test_fabricated_marker_class_string_literal_is_detected,
          test_fabricated_fallback_file_suffix_is_detected,
          test_main_exits_one_on_synthetic_violation
    [x] (i) source-of-truth + gate excluded from scan; allowlist preserved
        → test_canonical_emission_sites_are_not_flagged
    [x] (j) `format_findings` is deterministic with consistent ordering
        → test_format_findings_is_deterministic_alphabetical
"""

from __future__ import annotations

import pathlib

import pytest

from loud_fail_harness.bundle_assembly_failure_emission_gate import (
    _ALLOWLIST_FILES,
    ForbiddenEmissionFinding,
    GateResult,
    _scan_file_for_violations,
    format_findings,
    main,
    run_gate,
)


# --------------------------------------------------------------------------- #
# Forbidden-pattern detection                                                 #
# --------------------------------------------------------------------------- #


def test_fabricated_marker_class_string_literal_is_detected() -> None:
    """AC-4 / AC-6 (h): a fabricated source file with a literal
    ``"bundle-assembly-failed"`` outside the canonical site is detected
    as a rule (a) violation. Symbolic imports of
    BUNDLE_ASSEMBLY_FAILED_MARKER would NOT match (the symbol name is
    not the literal string).
    """
    fake_source = (
        "def buggy_emit(registry):\n"
        '    return validate_marker_emission(registry, "bundle-assembly-failed")\n'
    )
    findings = _scan_file_for_violations("fake/buggy.py", fake_source)
    rule_a_findings = [f for f in findings if f.rule == "marker-literal"]
    assert len(rule_a_findings) == 1
    assert rule_a_findings[0].line_number == 2
    assert rule_a_findings[0].file_path == "fake/buggy.py"

    # Single-quoted form is also detected.
    fake_source_single = "marker = 'bundle-assembly-failed'\n"
    findings_single = _scan_file_for_violations(
        "fake/buggy_single.py", fake_source_single
    )
    rule_a_single = [f for f in findings_single if f.rule == "marker-literal"]
    assert len(rule_a_single) == 1


def test_fabricated_fallback_file_suffix_is_detected() -> None:
    """AC-4 / AC-6 (h): a fabricated source file referencing the
    canonical ``*.assembly-failure.log`` suffix outside the
    source-of-truth module is detected as a rule (b) violation.
    """
    fake_source = (
        "def buggy_writer(bundle_root, story_id, run_id):\n"
        "    path = bundle_root / story_id / f'{run_id}.assembly-failure.log'\n"
        "    path.write_text('hello')\n"
    )
    findings = _scan_file_for_violations("fake/buggy_writer.py", fake_source)
    rule_b_findings = [f for f in findings if f.rule == "fallback-file-suffix"]
    assert len(rule_b_findings) == 1
    assert rule_b_findings[0].line_number == 2


def test_main_exits_one_on_synthetic_violation(
    tmp_path: pathlib.Path, capsys
) -> None:
    """AC-4 / AC-6 (h): when the scanned tree has at least one
    forbidden-emission violation, ``main`` exits 1.
    """
    # Build a synthetic minimal repo with one offending file.
    src_dir = (
        tmp_path / "tools" / "loud-fail-harness" / "src" / "loud_fail_harness"
    )
    src_dir.mkdir(parents=True)
    offending = src_dir / "buggy_module.py"
    offending.write_text(
        '"""Buggy module."""\nLITERAL = "bundle-assembly-failed"\n',
        encoding="utf-8",
    )

    exit_code = main(["--repo-root", str(tmp_path)])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Forbidden-emission violation:" in captured.out


# --------------------------------------------------------------------------- #
# Allowlist preservation                                                      #
# --------------------------------------------------------------------------- #


def test_canonical_emission_sites_are_not_flagged(
    repo_root_fixture: pathlib.Path,
) -> None:
    """AC-4 / AC-6 (i): the canonical sites
    (bundle_assembly_failure.py + the gate module itself) are in the
    allowlist and so contribute zero findings to the gate's output.
    The schemas/marker-taxonomy.yaml file + tests/*.py are out-of-scope
    by construction (not in the scan scope at all).
    """
    result = run_gate(repo_root_fixture)
    # All allowlist files are in scanned_files (they're discovered) but
    # contribute zero findings.
    assert _ALLOWLIST_FILES.issubset(set(result.scanned_files))
    for finding in result.forbidden_emission_violation:
        assert finding.file_path not in _ALLOWLIST_FILES, (
            f"canonical site {finding.file_path} must NOT be flagged "
            f"(it is in the allowlist by design)"
        )


def test_post_story_6_9_source_tree_is_exit_zero_clean(
    repo_root_fixture: pathlib.Path,
    capsys,
) -> None:
    """AC-4 / AC-6 (g): running the gate over the post-Story-6.9 actual
    source tree exits 0 (zero forbidden-emission violations).
    """
    exit_code = main(["--repo-root", str(repo_root_fixture)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Summary: 0 forbidden-emission violation(s)." in captured.out


# --------------------------------------------------------------------------- #
# format_findings determinism                                                  #
# --------------------------------------------------------------------------- #


def test_format_findings_is_deterministic_alphabetical() -> None:
    """AC-6 (j): `format_findings` produces stable, deterministic CI-
    formatted output with consistent ordering (alphabetical by file
    path).
    """
    findings = [
        ForbiddenEmissionFinding(
            file_path="zzz/last.py",
            line_number=10,
            rule="marker-literal",
            matched_text='"bundle-assembly-failed"',
        ),
        ForbiddenEmissionFinding(
            file_path="aaa/first.py",
            line_number=20,
            rule="fallback-file-suffix",
            matched_text=".assembly-failure.log",
        ),
    ]
    findings.sort(key=lambda f: (f.file_path, f.line_number, f.rule))

    result = GateResult(
        scanned_files=["aaa/first.py", "zzz/last.py"],
        forbidden_emission_violation=findings,
    )
    out_first = format_findings(result)
    out_second = format_findings(result)
    assert out_first == out_second
    # Ordering: first-occurring file_path appears before last in the body.
    assert out_first.index("aaa/first.py") < out_first.index("zzz/last.py")


# --------------------------------------------------------------------------- #
# Frozen model invariants                                                     #
# --------------------------------------------------------------------------- #


def test_gate_result_shape_is_pydantic_frozen() -> None:
    """Determinism + hashability: GateResult must be a frozen Pydantic
    model so its model_dump_json output is byte-stable across runs.
    """
    result = GateResult(scanned_files=[], forbidden_emission_violation=[])
    finding = ForbiddenEmissionFinding(
        file_path="x.py",
        line_number=1,
        rule="marker-literal",
        matched_text='"bundle-assembly-failed"',
    )
    # Frozen models reject mutation.
    with pytest.raises((TypeError, ValueError)):
        result.scanned_files = ["mutated"]  # type: ignore[misc]
    with pytest.raises((TypeError, ValueError)):
        finding.line_number = 99  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def repo_root_fixture() -> pathlib.Path:
    from loud_fail_harness._shared import find_repo_root

    return find_repo_root()
