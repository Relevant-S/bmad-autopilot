"""Contract-coverage matrix for review_layer_failure_emission_gate (Story 3.3 AC-9).

This docstring IS the contract-coverage checklist required by AC-9 of
Story 3.3. Reviewers verify every row maps to at least one passing
test. The matrix is review-enforced, NOT CI-enforced.

The gate is a structural CI lint that scans the harness source tree +
``agents/review-bmad-wrapper.md`` for forbidden direct emission paths
that bypass the canonical `surface_failed_layers` source-of-truth
function. Three forbidden patterns:
    (a) direct write to ``failed_layers`` envelope field
    (b) literal occurrence of ``"review-layer-failed"`` marker class string
    (c) literal occurrence of the ``review-completeness`` discriminator

AC-9 test-coverage matrix (items i-v):
    [x] (i)   fabricated failed_layers write detected     → test_fabricated_failed_layers_subscript_write_is_detected
    [x] (ii)  fabricated marker literal detected          → test_fabricated_marker_class_string_literal_is_detected
    [x] (iii) fabricated meta-discriminator detected      → test_fabricated_meta_review_completeness_literal_is_detected
    [x] (iv)  canonical sites NOT flagged                 → test_canonical_emission_sites_are_not_flagged
    [x] (v)   post-Story-3.3 source tree exit-0-clean     → test_post_story_3_3_source_tree_is_exit_zero_clean
"""

from __future__ import annotations

import pathlib

import pytest

from loud_fail_harness.review_layer_failure_emission_gate import (
    _ALLOWLIST_FILES,
    ForbiddenEmissionFinding,
    GateResult,
    _scan_file_for_violations,
    main,
    run_gate,
)


# --------------------------------------------------------------------------- #
# Forbidden-pattern detection                                                 #
# --------------------------------------------------------------------------- #


def test_fabricated_failed_layers_subscript_write_is_detected() -> None:
    """AC-9 item (i): a fabricated source file performing a direct
    subscript write to envelope["failed_layers"] is detected as a
    rule (a) violation.
    """
    fake_source = (
        "def buggy_alternative(envelope):\n"
        '    envelope["failed_layers"] = ["edge"]\n'
        "    return envelope\n"
    )
    findings = _scan_file_for_violations("fake/buggy.py", fake_source)
    rule_a_findings = [
        f for f in findings if f.rule == "failed-layers-write"
    ]
    assert len(rule_a_findings) == 1
    assert rule_a_findings[0].line_number == 2
    assert rule_a_findings[0].file_path == "fake/buggy.py"


def test_fabricated_marker_class_string_literal_is_detected() -> None:
    """AC-9 item (ii): a fabricated source file with a literal
    ``"review-layer-failed"`` outside the canonical site is detected
    as a rule (b) violation. Symbolic imports of
    REVIEW_LAYER_FAILED_MARKER would NOT match (the symbol name is
    not the literal string).
    """
    fake_source = (
        "def buggy_emit(registry):\n"
        '    return validate_marker_emission(registry, "review-layer-failed")\n'
    )
    findings = _scan_file_for_violations("fake/buggy.py", fake_source)
    rule_b_findings = [f for f in findings if f.rule == "marker-literal"]
    assert len(rule_b_findings) == 1
    assert rule_b_findings[0].line_number == 2

    # Single-quoted form is also detected.
    fake_source_single = "marker = 'review-layer-failed'\n"
    findings_single = _scan_file_for_violations(
        "fake/buggy_single.py", fake_source_single
    )
    rule_b_single = [f for f in findings_single if f.rule == "marker-literal"]
    assert len(rule_b_single) == 1


def test_fabricated_meta_review_completeness_literal_is_detected() -> None:
    """AC-9 item (iii): a fabricated source file appending a finding
    carrying ``meta: "review-completeness"`` outside the canonical
    site is detected as a rule (c) violation.
    """
    fake_source = (
        "def buggy_append(envelope):\n"
        "    finding = {\n"
        '        "id": "x",\n'
        '        "meta": "review-completeness",\n'
        "    }\n"
        '    envelope["findings"].append(finding)\n'
    )
    findings = _scan_file_for_violations("fake/buggy.py", fake_source)
    rule_c_findings = [
        f for f in findings if f.rule == "meta-discriminator"
    ]
    assert len(rule_c_findings) == 1
    assert rule_c_findings[0].line_number == 4


def test_canonical_emission_sites_are_not_flagged(
    repo_root_fixture: pathlib.Path,
) -> None:
    """AC-9 item (iv): the canonical sites (review_layer_failure.py,
    the gate module itself, and agents/review-bmad-wrapper.md) are in
    the allowlist and so contribute zero findings to the gate's
    output. The fixture-corpus YAML files + marker-taxonomy.yaml are
    out-of-scope by construction (not in the scan scope at all).
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


def test_post_story_3_3_source_tree_is_exit_zero_clean(
    repo_root_fixture: pathlib.Path,
    capsys,
) -> None:
    """AC-9 item (v): running the gate over the post-Story-3.3 actual
    source tree exits 0 (zero forbidden-emission violations).
    """
    exit_code = main(["--repo-root", str(repo_root_fixture)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Summary: 0 forbidden-emission violation(s)." in captured.out


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def repo_root_fixture() -> pathlib.Path:
    from loud_fail_harness._shared import find_repo_root

    return find_repo_root()


def test_gate_result_shape_is_pydantic_frozen() -> None:
    """Determinism + hashability: GateResult must be a frozen Pydantic
    model so its model_dump_json output is byte-stable across runs.
    """
    result = GateResult(scanned_files=[], forbidden_emission_violation=[])
    finding = ForbiddenEmissionFinding(
        file_path="x.py",
        line_number=1,
        rule="failed-layers-write",
        matched_text='["failed_layers"] =',
    )
    # Frozen models reject mutation.
    with pytest.raises((TypeError, ValueError)):
        result.scanned_files = ["mutated"]  # type: ignore[misc]
    with pytest.raises((TypeError, ValueError)):
        finding.line_number = 99  # type: ignore[misc]
