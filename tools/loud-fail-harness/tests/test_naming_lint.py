"""Contract-coverage matrix for naming_lint (Pattern 1 + Pattern 2 lint).

Story 1.12b AC-7 coverage shape (review-enforced, not CI-enforced — parallel
to test_dependencies_validator.py's matrix):

Positive paths (live cell-1 schemas):
    [x] live four cell-1 schemas pass with zero findings  → test_live_schemas_pass_clean
    [x] CLI main([]) on live schemas exits 0              → test_main_no_args_exits_zero

Pattern 1 negative paths (synthetic fixtures):
    [x] dependencies.yaml: snake_case dependency-key      → test_pattern_1_dependency_key_violation
    [x] field-name violation surfaces snake_case message  → test_pattern_1_field_name_violation_message_shape
    [x] entity-identifier-value violation in profile      → test_pattern_1_entity_identifier_value_violation
    [x] OTel pass-through dotted keys are exempted        → test_otel_pass_through_keys_exempted

Pattern 2 negative paths (synthetic fixtures):
    [x] marker_class single-segment rejected              → test_pattern_2_marker_class_single_segment_violation
    [x] marker_class snake_case rejected (≥2 seg fail)    → test_pattern_2_marker_class_snake_case_violation
    [x] sub_classifications uppercase rejected            → test_pattern_2_sub_classification_uppercase_violation
    [x] Pattern 2 finding cites correct remediation       → test_pattern_2_finding_remediation_pointer

Harness-level error paths (CLI exit 2 per Pattern 5):
    [x] broken YAML exits 2 with diagnostic               → test_main_broken_yaml_exits_two
    [x] unreadable file exits 2 with diagnostic           → test_main_unreadable_file_exits_two
    [x] top-level non-mapping exits 2 with diagnostic     → test_main_top_level_non_mapping_exits_two

Not-bailing-after-first-finding (AC-2 / AC-3 / AC-7):
    [x] multiple Pattern-1+Pattern-2 findings co-exist    → test_main_emits_all_findings_without_bailing
    [x] findings deterministic across two invocations     → test_findings_deterministic

ValidationFinding frozen-model discipline:
    [x] ValidationFinding is frozen (assignment raises)   → test_validation_finding_is_frozen

NFR-O5 diagnostic shape:
    [x] finding carries file_path + pointer + message + remediation
        → test_finding_carries_named_invariant_fields
"""

from __future__ import annotations

import pathlib

import pytest
from pydantic import ValidationError

from loud_fail_harness.naming_lint import (
    ValidationFinding,
    _CASING_RULES,
    _KEBAB_CASE_REGEX,
    _MARKER_CLASS_REGEX,
    _PATTERN_1_REMEDIATION,
    _PATTERN_2_REMEDIATION,
    _SNAKE_CASE_REGEX,
    _SUB_CLASSIFICATION_REGEX,
    lint_casing,
    lint_marker_class_naming,
    main,
)


# ---------- Positive paths --------------------------------------------------


def test_live_schemas_pass_clean(capsys: pytest.CaptureFixture[str]) -> None:
    """The four cell-1 schemas at this story's landing time conform to
    Pattern 1 + Pattern 2 (story 1.12b AC-7 positive path)."""
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "OK" in captured.out
    assert "0 findings" in captured.out
    assert captured.err == ""


def test_main_no_args_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """CLI exit-code 0 on the live inner-repo schemas (AC-7 CLI-exit-0 path)."""
    rc = main([])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Pattern 1 + Pattern 2" in captured.out


# ---------- Pattern 1 negative paths ---------------------------------------


def _write_dependencies_fixture(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    """Helper: write a YAML body to a tmp_path file named `dependencies.yaml`
    so _resolve_file_key maps it to the canonical position-table key."""
    p = tmp_path / "dependencies.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def _write_marker_taxonomy_fixture(
    tmp_path: pathlib.Path, body: str
) -> pathlib.Path:
    p = tmp_path / "marker-taxonomy.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_pattern_1_dependency_key_violation(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A dependency key that contains an underscore (e.g. `Claude_Code`) is
    an entity-identifier-key per the position table; it violates kebab-case
    and the lint surfaces a finding with the AC-2 diagnostic shape."""
    fixture = _write_dependencies_fixture(
        tmp_path,
        """\
schema_version: "1.0"
dependencies:
  Claude_Code:
    version_floor: "2.1.32"
    profiles:
      init:
        profile: total-block
        diagnostic: "x"
      runtime:
        profile: total-block
""",
    )
    rc = main([str(fixture)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "Claude_Code" in captured.out
    assert "kebab-case" in captured.out
    assert "/dependencies/Claude_Code" in captured.out
    assert _PATTERN_1_REMEDIATION in captured.out


def test_pattern_1_field_name_violation_message_shape(
    tmp_path: pathlib.Path,
) -> None:
    """A snake_case-violating top-level field name (e.g. `SchemaVersion`
    instead of `schema_version`) surfaces a finding naming the field, the
    snake_case regex, and the Pattern 1 remediation pointer."""
    fixture = _write_dependencies_fixture(
        tmp_path,
        """\
SchemaVersion: "1.0"
dependencies:
  claude-code:
    version_floor: "2.1.32"
    profiles:
      init:
        profile: total-block
        diagnostic: "x"
      runtime:
        profile: total-block
""",
    )
    import yaml

    raw = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    findings = lint_casing("schemas/dependencies.yaml", raw)
    assert any(
        f.pointer == "/SchemaVersion"
        and "snake_case" in f.message
        and f.remediation == _PATTERN_1_REMEDIATION
        for f in findings
    )


def test_pattern_1_entity_identifier_value_violation(
    tmp_path: pathlib.Path,
) -> None:
    """A `profile:` value that doesn't match kebab-case (e.g. `Total_Block`
    with snake-with-uppercase) surfaces a finding."""
    fixture = _write_dependencies_fixture(
        tmp_path,
        """\
schema_version: "1.0"
dependencies:
  claude-code:
    version_floor: "2.1.32"
    profiles:
      init:
        profile: Total_Block
        diagnostic: "x"
      runtime:
        profile: total-block
""",
    )
    import yaml

    raw = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    findings = lint_casing("schemas/dependencies.yaml", raw)
    assert any(
        f.pointer == "/dependencies/claude-code/profiles/init/profile"
        and "Total_Block" in f.message
        and "kebab-case" in f.message
        for f in findings
    )


def test_otel_pass_through_keys_exempted(tmp_path: pathlib.Path) -> None:
    """Field-name positions skip keys containing `.` (Pattern 3 / ADR-006
    Consequence 5 — OTel pass-through). Synthetic envelope-shape fixture
    with a dotted key under properties: must NOT surface a Pattern 1
    finding for that key."""
    fixture = tmp_path / "envelope.schema.yaml"
    fixture.write_text(
        """\
$schema: "https://json-schema.org/draft/2020-12/schema"
title: "test"
type: object
properties:
  status:
    type: string
  "prompt.id": {}
  "claude_code.cost.usage": {}
""",
        encoding="utf-8",
    )
    import yaml

    raw = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    findings = lint_casing("schemas/envelope.schema.yaml", raw)
    # No findings on dotted keys, no findings on `status` (snake_case).
    assert findings == []


# ---------- Pattern 2 negative paths ---------------------------------------


def test_pattern_2_marker_class_single_segment_violation(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `marker_class` value of a single segment (e.g. `singleword`) passes
    Pattern 1's looser kebab regex but fails Pattern 2's ≥-2-segment regex."""
    fixture = _write_marker_taxonomy_fixture(
        tmp_path,
        """\
schema_version: "1.0"
markers:
  - marker_class: singleword
    diagnostic_pointer: "test"
    sub_classifications: []
""",
    )
    rc = main([str(fixture)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "singleword" in captured.out
    assert "marker class" in captured.out
    assert _PATTERN_2_REMEDIATION in captured.out


def test_pattern_2_marker_class_snake_case_violation() -> None:
    """A `marker_class` with underscores (e.g. `state_recovery_drift`) fails
    BOTH Pattern 1 (kebab-case identifier values) AND Pattern 2 (marker
    class regex). Both findings are emitted; the lint does not bail after
    Pattern 1 fires."""
    raw = {
        "schema_version": "1.0",
        "markers": [
            {
                "marker_class": "state_recovery_drift",
                "diagnostic_pointer": "x",
                "sub_classifications": [],
            }
        ],
    }
    pattern_1_findings = lint_casing("schemas/marker-taxonomy.yaml", raw)
    pattern_2_findings = lint_marker_class_naming(raw)
    assert any(
        "state_recovery_drift" in f.message and "kebab-case" in f.message
        for f in pattern_1_findings
    )
    assert any(
        "state_recovery_drift" in f.message and "marker class" in f.message
        for f in pattern_2_findings
    )


def test_pattern_2_sub_classification_uppercase_violation() -> None:
    """A `sub_classifications` label with uppercase letters (e.g.
    `Event-Log-Missing`) fails the strictly-lowercase
    _SUB_CLASSIFICATION_REGEX."""
    raw = {
        "schema_version": "1.0",
        "markers": [
            {
                "marker_class": "state-recovery-drift",
                "diagnostic_pointer": "x",
                "sub_classifications": ["Event-Log-Missing"],
            }
        ],
    }
    findings = lint_marker_class_naming(raw)
    assert any(
        "Event-Log-Missing" in f.message
        and "sub-classification" in f.message
        and f.pointer == "/markers/0/sub_classifications/0"
        for f in findings
    )


def test_pattern_2_finding_remediation_pointer() -> None:
    """Every Pattern-2 finding cites the implementation-patterns.md anchor
    `#pattern-2-marker-class-naming-convention`."""
    raw = {
        "schema_version": "1.0",
        "markers": [
            {
                "marker_class": "singleword",
                "diagnostic_pointer": "x",
                "sub_classifications": [],
            }
        ],
    }
    findings = lint_marker_class_naming(raw)
    assert findings
    for f in findings:
        assert f.remediation == _PATTERN_2_REMEDIATION
        assert "pattern-2-marker-class-naming-convention" in f.remediation


# ---------- Harness-level error paths (exit 2) -----------------------------


def test_main_broken_yaml_exits_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Malformed YAML triggers exit 2 + a named-invariant diagnostic on stderr
    (NFR-O5 distinct from the exit-1 validation-finding path)."""
    broken = tmp_path / "marker-taxonomy.yaml"
    broken.write_text("foo: [bar\n", encoding="utf-8")
    rc = main([str(broken)])
    assert rc == 2
    captured = capsys.readouterr()
    assert "harness-level error" in captured.err
    assert "YAML parse failure" in captured.err


def test_main_unreadable_file_exits_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A path that doesn't resolve to an existing file triggers exit 2."""
    missing = tmp_path / "marker-taxonomy.yaml"  # not created
    rc = main([str(missing)])
    assert rc == 2
    captured = capsys.readouterr()
    assert "harness-level error" in captured.err
    assert "unreadable" in captured.err


def test_main_top_level_non_mapping_exits_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A YAML file whose top level is a sequence (not a mapping) triggers
    exit 2 with the named-invariant diagnostic."""
    bad = tmp_path / "marker-taxonomy.yaml"
    bad.write_text("- foo\n- bar\n", encoding="utf-8")
    rc = main([str(bad)])
    assert rc == 2
    captured = capsys.readouterr()
    assert "harness-level error" in captured.err
    assert "not a YAML mapping" in captured.err


# ---------- Not-bailing + determinism --------------------------------------


def test_main_emits_all_findings_without_bailing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fixture with one Pattern 1 violation + one Pattern 2 violation surfaces
    BOTH findings before exit, sorted by (file_path, pointer, message).
    AC-2 / AC-3 not-bailing + sort-order discipline (story 1.12b AC-7)."""
    # SchemaVersion (wrong-cased top-level field name) → Pattern 1 finding at
    # pointer /SchemaVersion.  singleword (single-segment marker_class) →
    # Pattern 2 finding at pointer /markers/0/marker_class.
    # Sort order: /SchemaVersion < /markers/0/marker_class (S < m in ASCII).
    fixture = _write_marker_taxonomy_fixture(
        tmp_path,
        """\
SchemaVersion: "1.0"
markers:
  - marker_class: singleword
    diagnostic_pointer: "x"
    sub_classifications: []
""",
    )
    rc = main([str(fixture)])
    assert rc == 1
    captured = capsys.readouterr()
    # Pattern 1 field-name finding
    assert "SchemaVersion" in captured.out
    # Pattern 2 marker_class finding
    assert "singleword" in captured.out
    # Both findings counted in the header
    assert "2 finding(s)" in captured.out
    # Sort-order: Pattern 1 finding (/SchemaVersion) precedes Pattern 2
    # finding (/markers/0/marker_class) per (file_path, pointer, message) sort.
    assert captured.out.index("SchemaVersion") < captured.out.index("singleword")


def test_findings_deterministic() -> None:
    """Two calls on the same input return identical sorted finding lists."""
    raw = {
        "schema_version": "1.0",
        "markers": [
            {
                "marker_class": "singleword",
                "diagnostic_pointer": "x",
                "sub_classifications": ["UpperCase"],
            },
            {
                "marker_class": "another-bad_one",
                "diagnostic_pointer": "x",
                "sub_classifications": [],
            },
        ],
    }
    a = lint_marker_class_naming(raw)
    b = lint_marker_class_naming(raw)
    assert a == b
    # Determinism after sorting (parallel to dependencies_validator's
    # sort-by-(file_path, pointer, message) discipline).
    sort_key = lambda f: (f.file_path, f.pointer, f.message)  # noqa: E731
    assert sorted(a, key=sort_key) == sorted(b, key=sort_key)


# ---------- Pydantic v2 frozen-model discipline ----------------------------


def test_validation_finding_is_frozen() -> None:
    """ValidationFinding is hashable + immutable; assignment raises."""
    finding = ValidationFinding(
        file_path="schemas/marker-taxonomy.yaml",
        pointer="/markers/0/marker_class",
        message="test",
        remediation=_PATTERN_2_REMEDIATION,
    )
    with pytest.raises(ValidationError):
        finding.message = "different"  # type: ignore[misc]


# ---------- NFR-O5 diagnostic shape ----------------------------------------


def test_finding_carries_named_invariant_fields() -> None:
    """Every finding has file_path + pointer + message + remediation per
    NFR-O5 (parallel to dependencies_validator's diagnostic shape)."""
    raw = {
        "schema_version": "1.0",
        "markers": [
            {
                "marker_class": "singleword",
                "diagnostic_pointer": "x",
                "sub_classifications": [],
            }
        ],
    }
    findings = lint_marker_class_naming(raw)
    assert findings
    for f in findings:
        assert f.file_path == "schemas/marker-taxonomy.yaml"
        assert f.pointer.startswith("/")
        assert f.message
        assert f.remediation


# ---------- Position-classification table sanity ---------------------------


def test_casing_rules_cover_all_four_cell_one_schemas() -> None:
    """The position-classification table has an entry for each of the four
    cell-1 schema files (story 1.12b AC-2)."""
    expected = {
        "schemas/envelope.schema.yaml",
        "schemas/orchestrator-event.yaml",
        "schemas/marker-taxonomy.yaml",
        "schemas/dependencies.yaml",
    }
    assert set(_CASING_RULES.keys()) == expected


def test_regex_constants_match_existing_taxonomy_entries() -> None:
    """Sanity check: the AC-named existing taxonomy entries match the regex
    constants. Architecture.md line 961 names `LAD-skipped`,
    `Tier-3-not-configured`, `state-recovery-drift`, `cost-near-ceiling` as
    canonical examples."""
    for name in (
        "LAD-skipped",
        "Tier-3-not-configured",
        "state-recovery-drift",
        "cost-near-ceiling",
        "heuristic-skipped",
    ):
        assert _MARKER_CLASS_REGEX.fullmatch(name), name
        assert _KEBAB_CASE_REGEX.fullmatch(name), name
    # Single-word names fail Pattern 2 (≥ 2 segments)
    assert _MARKER_CLASS_REGEX.fullmatch("singleword") is None
    # snake_case structural keys match _SNAKE_CASE_REGEX
    for name in ("schema_version", "marker_class", "sub_classifications"):
        assert _SNAKE_CASE_REGEX.fullmatch(name), name
    # Sub-classification labels (lowercase only)
    for name in ("port-bind-failed", "timeout-exceeded", "missing-binary"):
        assert _SUB_CLASSIFICATION_REGEX.fullmatch(name), name
    # Uppercase rejected by sub-classification regex
    assert _SUB_CLASSIFICATION_REGEX.fullmatch("Event-Log-Missing") is None
