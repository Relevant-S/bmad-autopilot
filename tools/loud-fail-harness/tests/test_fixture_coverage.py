"""Contract-coverage matrix for substrate component 5 (fixture_coverage).

This docstring IS the contract-coverage checklist required by AC-6. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to story 1.2 / 1.3 / 1.4 / 1.5
/ 1.6 AC-5/6).

Pure-API classification cases (AC-3, AC-5):
    [x] full coverage (synthetic) → passing == N, uncovered + dangling empty → test_full_coverage_synthetic_pass
    [x] missing fixture (uncovered marker)                          → test_missing_fixture_uncovered_fail
    [x] dangling fixture (declared marker not in taxonomy)          → test_dangling_fixture_fail
    [x] PR adds marker without fixture (Epic AC narrative)          → test_pr_adds_marker_without_fixture
    [x] multiple fixtures per marker class accepted                 → test_multiple_fixtures_per_marker_class_accepted
    [x] empty corpus reports full taxonomy as uncovered             → test_empty_corpus_reports_full_taxonomy_uncovered
    [x] FR65 / ADR-003 skip-class-recognition workflow narrative    → test_skip_class_recognition_workflow_synthetic
    [x] shape-violating fixture excluded from passing (AC-5 "parsed cleanly") → test_shape_violating_fixture_excluded_from_passing

Frontmatter shape rule violations (AC-2, AC-5, AC-6):
    [x] file does not begin with --- delimiter                      → test_malformed_frontmatter_no_opening_delimiter
    [x] file is missing closing --- delimiter                       → test_malformed_frontmatter_no_closing_delimiter
    [x] frontmatter parses to non-mapping (e.g. list)               → test_malformed_frontmatter_non_mapping
    [x] missing required field 'expected_marker'                    → test_malformed_frontmatter_missing_expected_marker
    [x] missing required field 'scenario'                           → test_malformed_frontmatter_missing_scenario
    [x] unknown frontmatter key                                     → test_malformed_frontmatter_unknown_key
    [x] frontmatter YAML parse failure                              → test_malformed_frontmatter_yaml_parse_error
    [x] expected_marker non-string                                  → test_expected_marker_non_string
    [x] scenario non-string                                         → test_scenario_non_string
    [x] optional fields accepted (sub_classification / event_class / notes) → test_optional_fields_accepted

Discovery rules (AC-3, AC-6):
    [x] README.md skipped from coverage walk by literal filename    → test_readme_md_skipped_from_walk
    [x] subdirectory fixture surfaces shape violation (exit-1 path) → test_subdirectory_fixtures_handling

Determinism (AC-6):
    [x] discover + check are byte-identical across two invocations  → test_findings_deterministic
    [x] CoverageResult.model_dump_json byte-identical               → test_coverage_result_json_serialization_stable
    [x] determinism under shuffled fixture-input order              → test_determinism_under_shuffle

Pydantic v2 frozen-model discipline:
    [x] Fixture is frozen (assignment raises)                       → test_fixture_is_frozen
    [x] Reference is frozen (assignment raises)                     → test_reference_is_frozen
    [x] ShapeViolation is frozen (assignment raises)                → test_shape_violation_is_frozen
    [x] CoverageResult is frozen (assignment raises)                → test_coverage_result_is_frozen

CLI / main exit-code matrix (AC-4, AC-6):
    [x] canonical corpus validates → exit 0 + 32/32 Summary line    → test_canonical_corpus_validates
    [x] main exits 1 on uncovered marker                            → test_main_exits_one_on_uncovered_marker
    [x] main exits 1 lists every uncovered (do-not-bail-after-first) → test_main_lists_every_uncovered_class
    [x] main exits 1 on dangling fixture                            → test_main_exits_one_on_dangling_fixture
    [x] main exits 1 on shape violation                             → test_main_exits_one_on_shape_violation
    [x] main exits 0 silent on empty findings                       → test_main_exits_zero_on_full_coverage
    [x] main --help resolves to argparse                            → test_main_help_resolves
    [x] main with no flags resolves canonical files                 → test_main_with_no_flags_resolves_canonical_files

Loud-fail / harness-level errors (AC-4, AC-6, Pattern 5):
    [x] missing fixtures-dir → exit 2 + named path                  → test_loud_fail_on_missing_fixtures_dir
    [x] missing taxonomy file → exit 2                              → test_loud_fail_on_missing_taxonomy
    [x] malformed taxonomy YAML → exit 2                            → test_loud_fail_on_malformed_taxonomy
    [x] taxonomy with non-string marker_class → exit 2              → test_loud_fail_on_taxonomy_non_string_marker_class
    [x] fixtures-dir is a regular file (not a directory) → exit 2   → test_loud_fail_on_fixtures_dir_is_a_file
    [x] non-UTF-8 fixture → exit 1 shape violation (not exit 2)     → test_unicode_decode_error_becomes_shape_violation

Stdout shape:
    [x] header names fixtures_dir + taxonomy_path                   → test_format_findings_header
    [x] passing-summary line present                                → test_format_findings_passing_summary
    [x] uncovered FAIL section names class + remediation            → test_format_findings_uncovered_section
    [x] dangling FAIL section names file + value + remediation      → test_format_findings_dangling_section
    [x] shape-violations FAIL section names pointer + message       → test_format_findings_shape_violations_section
    [x] Summary footer present unconditionally                      → test_format_findings_summary_present

Coverage (AC-6):
    [x] fixture_coverage.py module-level statement coverage ≥ 90% → review-enforced; not a CI gate
"""

from __future__ import annotations

import io
import pathlib
import random
import sys

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness.fixture_coverage import (
    CoverageResult,
    Fixture,
    Reference,
    ShapeViolation,
    check_fixture_coverage,
    discover_fixtures,
    format_findings,
    main,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

CANONICAL_27 = {
    "LAD-skipped",
    "Tier-3-not-configured",
    "heuristic-skipped",
    "mobile-blocked",
    "env-setup-failed",
    "plan-drift-detected",
    "specialist-timeout",
    "context-near-limit",
    "evidence-truncated",
    "hook-failed",
    "undocumented-section-write",
    "orphan-process-cleanup",
    "cost-near-ceiling",
    "smoke-first-abort",
    "dangling-evidence-ref",
    "walking-skeleton-bundle",
    "review-layer-failed",
    "playwright-mcp-unavailable",
    "scope-assertion-violation",
    "retry-budget-exhausted",
    "bundle-assembly-failed",
    "reconciler-mismatch-runtime",
    "cost-telemetry-unavailable",
    "story-doc-version-out-of-window",
    "init-would-destroy-existing-artifact",
    "recovery-state-conflict",
    "orphan-run-state-detected",
}


def _write_taxonomy(path: pathlib.Path, classes: list[str]) -> None:
    """Write a minimal valid marker-taxonomy.yaml at ``path``."""
    entries = [
        {"marker_class": c, "diagnostic_pointer": "synthetic test entry", "sub_classifications": []}
        for c in classes
    ]
    payload = {"schema_version": "1.0", "markers": entries}
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def _write_fixture(
    path: pathlib.Path,
    *,
    expected_marker: str | None = None,
    scenario: str | None = "synthetic scenario",
    extra: dict | None = None,
    raw_content: str | None = None,
    body: str = "# body\n",
) -> None:
    """Write a fixture file at ``path``.

    If ``raw_content`` is provided, it is written verbatim (used for malformed
    cases). Otherwise a frontmatter is built from the keyword args.
    """
    if raw_content is not None:
        path.write_text(raw_content, encoding="utf-8")
        return
    fm: dict = {}
    if expected_marker is not None:
        fm["expected_marker"] = expected_marker
    if scenario is not None:
        fm["scenario"] = scenario
    if extra:
        fm.update(extra)
    text = "---\n" + yaml.safe_dump(fm) + "---\n" + body
    path.write_text(text, encoding="utf-8")


def _make_corpus(
    tmp_path: pathlib.Path,
    *,
    fixtures: dict[str, dict],
    include_readme: bool = False,
) -> pathlib.Path:
    """Build a fixtures directory under tmp_path with the given fixture map.

    ``fixtures`` is ``{filename: kwargs_for__write_fixture}``.
    """
    corpus = tmp_path / "synthetic-stories"
    corpus.mkdir()
    for filename, kwargs in fixtures.items():
        _write_fixture(corpus / filename, **kwargs)
    if include_readme:
        (corpus / "README.md").write_text("# README\n\nIndex.\n", encoding="utf-8")
    return corpus


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


# ---------------------------------------------------------------------------
# Pure-API classification cases
# ---------------------------------------------------------------------------


def test_full_coverage_synthetic_pass(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "alpha.md": {"expected_marker": "alpha"},
            "beta.md": {"expected_marker": "beta"},
            "gamma.md": {"expected_marker": "gamma"},
        },
    )
    fixtures = discover_fixtures(corpus)
    result = check_fixture_coverage(fixtures, {"alpha", "beta", "gamma"})
    assert len(result.passing) == 3
    assert result.uncovered == []
    assert result.dangling == []
    assert result.shape_violations == []


def test_missing_fixture_uncovered_fail(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "alpha.md": {"expected_marker": "alpha"},
            "beta.md": {"expected_marker": "beta"},
        },
    )
    fixtures = discover_fixtures(corpus)
    result = check_fixture_coverage(fixtures, {"alpha", "beta", "gamma"})
    assert result.uncovered == ["gamma"]
    assert {r.marker_class for r in result.passing} == {"alpha", "beta"}
    rendered = format_findings(
        result, fixtures_dir="corpus", taxonomy_path="taxonomy.yaml"
    )
    assert "uncovered marker class 'gamma'" in rendered
    assert "examples/synthetic-stories/gamma.md" in rendered


def test_dangling_fixture_fail(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "alpha.md": {"expected_marker": "alpha"},
            "beta.md": {"expected_marker": "beta"},
            "rogue.md": {"expected_marker": "not-in-taxonomy"},
        },
    )
    fixtures = discover_fixtures(corpus)
    result = check_fixture_coverage(fixtures, {"alpha", "beta"})
    assert len(result.dangling) == 1
    assert result.dangling[0].marker_class == "not-in-taxonomy"
    assert result.dangling[0].file_path.endswith("rogue.md")
    rendered = format_findings(
        result, fixtures_dir="corpus", taxonomy_path="taxonomy.yaml"
    )
    assert "not-in-taxonomy" in rendered
    assert "rogue.md" in rendered
    assert "FR65" in rendered  # remediation pointer


def test_pr_adds_marker_without_fixture(tmp_path: pathlib.Path) -> None:
    """Epic AC narrative: PR that adds a new marker class without a fixture."""
    canonical_fixtures = {f"{c}.md": {"expected_marker": c} for c in CANONICAL_27}
    corpus = _make_corpus(tmp_path, fixtures=canonical_fixtures)
    fixtures = discover_fixtures(corpus)
    extended_taxonomy = CANONICAL_27 | {"fake-new-marker"}
    result = check_fixture_coverage(fixtures, extended_taxonomy)
    assert result.uncovered == ["fake-new-marker"]
    rendered = format_findings(
        result, fixtures_dir="corpus", taxonomy_path="taxonomy.yaml"
    )
    assert "fake-new-marker" in rendered


def test_multiple_fixtures_per_marker_class_accepted(tmp_path: pathlib.Path) -> None:
    """Closure invariant is on deduplicated marker_class set, NOT fixture count."""
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "heuristic-skipped.md": {"expected_marker": "heuristic-skipped"},
            "heuristic-skipped--variant.md": {"expected_marker": "heuristic-skipped"},
        },
    )
    fixtures = discover_fixtures(corpus)
    result = check_fixture_coverage(fixtures, {"heuristic-skipped"})
    assert len(result.passing) == 2
    assert result.uncovered == []
    assert result.dangling == []


def test_empty_corpus_reports_full_taxonomy_uncovered(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(tmp_path, fixtures={}, include_readme=True)
    fixtures = discover_fixtures(corpus)
    assert fixtures == []
    result = check_fixture_coverage(fixtures, CANONICAL_27)
    assert sorted(result.uncovered) == sorted(CANONICAL_27)
    assert result.passing == []
    assert result.dangling == []


def test_skip_class_recognition_workflow_synthetic(tmp_path: pathlib.Path) -> None:
    """FR65 / ADR-003 skip-class-recognition workflow: taxonomy bump, then fixture."""
    fixtures_map = {f"{c}.md": {"expected_marker": c} for c in CANONICAL_27}
    corpus = _make_corpus(tmp_path, fixtures=fixtures_map)
    extended_taxonomy = CANONICAL_27 | {"fake-new-marker"}

    # Step 1: taxonomy bump without fixture → uncovered
    fixtures = discover_fixtures(corpus)
    result = check_fixture_coverage(fixtures, extended_taxonomy)
    assert result.uncovered == ["fake-new-marker"]

    # Step 2: fixture added → exit 0 condition (closure restored)
    _write_fixture(corpus / "fake-new-marker.md", expected_marker="fake-new-marker")
    fixtures = discover_fixtures(corpus)
    result = check_fixture_coverage(fixtures, extended_taxonomy)
    assert result.uncovered == []
    assert result.dangling == []


# ---------------------------------------------------------------------------
# Frontmatter shape rule violations
# ---------------------------------------------------------------------------


def test_malformed_frontmatter_no_opening_delimiter(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "broken.md": {"raw_content": "# Markdown body\n\nNo frontmatter.\n"},
        },
    )
    fixtures = discover_fixtures(corpus)
    assert len(fixtures) == 1
    assert fixtures[0].expected_marker is None
    findings = fixtures[0].frontmatter_findings
    assert any("does not begin with YAML frontmatter delimiter" in f.message for f in findings)


def test_malformed_frontmatter_no_closing_delimiter(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "broken.md": {"raw_content": "---\nexpected_marker: foo\nscenario: bar\n# no closing\n"},
        },
    )
    fixtures = discover_fixtures(corpus)
    assert fixtures[0].expected_marker is None
    findings = fixtures[0].frontmatter_findings
    assert any("missing YAML frontmatter closing delimiter" in f.message for f in findings)


def test_malformed_frontmatter_non_mapping(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "list.md": {"raw_content": "---\n- foo\n- bar\n---\nbody\n"},
        },
    )
    fixtures = discover_fixtures(corpus)
    findings = fixtures[0].frontmatter_findings
    assert any("must be a YAML mapping" in f.message for f in findings)
    assert any(f.pointer == "<root>" for f in findings)


def test_malformed_frontmatter_missing_expected_marker(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "missing-em.md": {"raw_content": "---\nscenario: only scenario\n---\nbody\n"},
        },
    )
    fixtures = discover_fixtures(corpus)
    findings = fixtures[0].frontmatter_findings
    assert any(
        f.pointer == "/expected_marker" and "missing required field" in f.message
        for f in findings
    )


def test_malformed_frontmatter_missing_scenario(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "missing-scenario.md": {"raw_content": "---\nexpected_marker: foo\n---\nbody\n"},
        },
    )
    fixtures = discover_fixtures(corpus)
    findings = fixtures[0].frontmatter_findings
    assert any(
        f.pointer == "/scenario" and "missing required field" in f.message
        for f in findings
    )
    # expected_marker remains extractable even with the scenario shape violation
    assert fixtures[0].expected_marker == "foo"


def test_malformed_frontmatter_unknown_key(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "unknown.md": {
                "raw_content": (
                    "---\nexpected_marker: foo\nscenario: bar\n"
                    "random_field: bogus\n---\nbody\n"
                )
            },
        },
    )
    fixtures = discover_fixtures(corpus)
    findings = fixtures[0].frontmatter_findings
    assert any(
        f.pointer == "/random_field"
        and "unknown frontmatter field 'random_field'" in f.message
        and "allowed:" in f.message
        for f in findings
    )


def test_malformed_frontmatter_yaml_parse_error(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "broken-yaml.md": {
                "raw_content": "---\nexpected_marker: [unclosed\n---\nbody\n"
            },
        },
    )
    fixtures = discover_fixtures(corpus)
    findings = fixtures[0].frontmatter_findings
    assert any("YAML parse failure" in f.message for f in findings)


def test_expected_marker_non_string(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "non-string-em.md": {
                "raw_content": "---\nexpected_marker: 99\nscenario: bar\n---\nbody\n"
            },
        },
    )
    fixtures = discover_fixtures(corpus)
    findings = fixtures[0].frontmatter_findings
    assert any(
        f.pointer == "/expected_marker" and "must be a string" in f.message
        for f in findings
    )
    # Non-string expected_marker → expected_marker stays None
    assert fixtures[0].expected_marker is None


def test_scenario_non_string(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "non-string-scenario.md": {
                "raw_content": "---\nexpected_marker: foo\nscenario: 42\n---\nbody\n"
            },
        },
    )
    fixtures = discover_fixtures(corpus)
    findings = fixtures[0].frontmatter_findings
    assert any(
        f.pointer == "/scenario" and "must be a string" in f.message
        for f in findings
    )


def test_optional_fields_accepted(tmp_path: pathlib.Path) -> None:
    """Optional reserved fields (1.8 placeholders) MUST be accepted without flagging."""
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "rich.md": {
                "expected_marker": "alpha",
                "scenario": "scenario",
                "extra": {
                    "expected_sub_classification": "alpha-sub",
                    "expected_event_class": "alpha-event",
                    "notes": "free-form prose",
                },
            },
        },
    )
    fixtures = discover_fixtures(corpus)
    assert fixtures[0].frontmatter_findings == []
    assert fixtures[0].expected_marker == "alpha"


def test_shape_violating_fixture_excluded_from_passing(tmp_path: pathlib.Path) -> None:
    """AC-5: fixtures with shape violations do NOT count toward passing even when
    expected_marker is extractable and in taxonomy.  The marker class goes to
    uncovered; the file goes to shape_violations.
    """
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            # missing 'scenario' → shape violation, but expected_marker is valid
            "bad.md": {"raw_content": "---\nexpected_marker: alpha\n---\nbody\n"},
        },
    )
    fixtures = discover_fixtures(corpus)
    assert fixtures[0].expected_marker == "alpha"
    assert fixtures[0].frontmatter_findings  # has a violation

    result = check_fixture_coverage(fixtures, {"alpha"})
    assert result.passing == []
    assert result.uncovered == ["alpha"]
    assert len(result.shape_violations) == 1
    assert result.shape_violations[0].pointer == "/scenario"
    assert result.dangling == []


# ---------------------------------------------------------------------------
# Discovery rules
# ---------------------------------------------------------------------------


def test_readme_md_skipped_from_walk(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={"alpha.md": {"expected_marker": "alpha"}},
        include_readme=True,
    )
    fixtures = discover_fixtures(corpus)
    assert len(fixtures) == 1
    assert fixtures[0].expected_marker == "alpha"


def test_subdirectory_fixtures_handling(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path, fixtures={"top.md": {"expected_marker": "alpha"}}
    )
    sub = corpus / "sub"
    sub.mkdir()
    _write_fixture(sub / "nested.md", expected_marker="alpha")

    fixtures = discover_fixtures(corpus)
    # Top-level fixture present + the nested file surfaces as a Fixture with
    # a single shape-violation finding (NOT exit-2).
    assert any(f.file_path.endswith("top.md") for f in fixtures)
    nested = next(f for f in fixtures if f.file_path.endswith("nested.md"))
    assert nested.expected_marker is None
    assert any(
        "subdirectories not permitted" in v.message
        for v in nested.frontmatter_findings
    )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_findings_deterministic(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={f"{c}.md": {"expected_marker": c} for c in ["b", "a", "c"]},
    )
    fixtures1 = discover_fixtures(corpus)
    fixtures2 = discover_fixtures(corpus)
    result1 = check_fixture_coverage(fixtures1, {"a", "b", "c", "d"})
    result2 = check_fixture_coverage(fixtures2, {"a", "b", "c", "d"})
    assert result1 == result2


def test_coverage_result_json_serialization_stable(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "alpha.md": {"expected_marker": "alpha"},
            "beta.md": {"expected_marker": "beta"},
            "rogue.md": {"expected_marker": "rogue-class"},
        },
    )
    fixtures = discover_fixtures(corpus)
    r1 = check_fixture_coverage(fixtures, {"alpha", "beta", "gamma"})
    r2 = check_fixture_coverage(fixtures, {"alpha", "beta", "gamma"})
    assert r1.model_dump_json() == r2.model_dump_json()


def test_determinism_under_shuffle(tmp_path: pathlib.Path) -> None:
    """Shuffling input fixture order MUST NOT change CoverageResult output."""
    corpus = _make_corpus(
        tmp_path,
        fixtures={f"{c}.md": {"expected_marker": c} for c in ["a", "b", "c", "d"]},
    )
    fixtures = discover_fixtures(corpus)
    shuffled = list(fixtures)
    random.Random(42).shuffle(shuffled)
    r_sorted = check_fixture_coverage(fixtures, {"a", "b", "c"})
    r_shuffled = check_fixture_coverage(shuffled, {"a", "b", "c"})
    assert r_sorted.model_dump_json() == r_shuffled.model_dump_json()


# ---------------------------------------------------------------------------
# Pydantic v2 frozen-model discipline
# ---------------------------------------------------------------------------


def test_fixture_is_frozen() -> None:
    fx = Fixture(file_path="x.md", expected_marker="alpha", frontmatter_findings=[])
    with pytest.raises(ValidationError):
        fx.expected_marker = "beta"  # type: ignore[misc]


def test_reference_is_frozen() -> None:
    ref = Reference(file_path="x.md", marker_class="alpha")
    with pytest.raises(ValidationError):
        ref.marker_class = "beta"  # type: ignore[misc]


def test_shape_violation_is_frozen() -> None:
    v = ShapeViolation(file_path="x.md", pointer="<root>", message="m", remediation="r")
    with pytest.raises(ValidationError):
        v.message = "new"  # type: ignore[misc]


def test_coverage_result_is_frozen() -> None:
    result = CoverageResult(passing=[], uncovered=[], dangling=[], shape_violations=[])
    with pytest.raises(ValidationError):
        result.uncovered = ["x"]  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CLI / main exit-code matrix
# ---------------------------------------------------------------------------


def test_canonical_corpus_validates() -> None:
    """The on-disk canonical 37-fixture corpus + canonical taxonomy → exit 0
    (story 2.3 added 2 markers + 2 fixtures, taking the count from 27 → 29;
    story 14.3 added 1 marker + 1 fixture, taking the count from 29 → 30;
    story 14.5 added 1 marker + 1 fixture, taking the count from 30 → 31;
    story 15.2 added 1 marker + 1 fixture, taking the count from 31 → 32;
    story 16.2 added 1 marker + 1 fixture, taking the count from 32 → 33;
    story 24.1 added 1 marker + 1 fixture, taking the count from 33 → 34;
    story 19.3 added 3 markers + 3 fixtures, taking the count from 34 → 37;
    stories 19.5/20.1/20.3 took it 37 → 41; story 21.2 added 1 marker + 1
    fixture (background-primitive-unstable), taking the count from 41 → 42; story 17.2 added 1 marker + 1 fixture (auto-merge-gate-not-met) (42 → 43))."""
    rc, out, err = _capture_main([])
    assert rc == 0, f"stdout: {out}\nstderr: {err}"
    assert "44 passing marker class(es)" in out
    assert "0 uncovered marker class(es)" in out
    assert "0 dangling fixture(s)" in out
    assert "0 shape-violation finding(s)" in out


def test_main_exits_one_on_uncovered_marker(tmp_path: pathlib.Path) -> None:
    taxonomy = tmp_path / "taxonomy.yaml"
    _write_taxonomy(taxonomy, ["alpha", "beta", "gamma"])
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "alpha.md": {"expected_marker": "alpha"},
            "beta.md": {"expected_marker": "beta"},
        },
    )
    rc, out, err = _capture_main(
        ["--fixtures-dir", str(corpus), "--taxonomy-path", str(taxonomy)]
    )
    assert rc == 1
    assert "gamma" in out
    assert "uncovered marker class" in out


def test_main_lists_every_uncovered_class(tmp_path: pathlib.Path) -> None:
    """do-not-bail-after-first: with multiple uncovered, all must surface."""
    taxonomy = tmp_path / "taxonomy.yaml"
    _write_taxonomy(taxonomy, ["alpha", "beta", "gamma", "delta"])
    corpus = _make_corpus(tmp_path, fixtures={"alpha.md": {"expected_marker": "alpha"}})
    rc, out, _ = _capture_main(
        ["--fixtures-dir", str(corpus), "--taxonomy-path", str(taxonomy)]
    )
    assert rc == 1
    for missing in ("beta", "gamma", "delta"):
        assert missing in out


def test_main_exits_one_on_dangling_fixture(tmp_path: pathlib.Path) -> None:
    taxonomy = tmp_path / "taxonomy.yaml"
    _write_taxonomy(taxonomy, ["alpha"])
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "alpha.md": {"expected_marker": "alpha"},
            "rogue.md": {"expected_marker": "not-in-taxonomy"},
        },
    )
    rc, out, _ = _capture_main(
        ["--fixtures-dir", str(corpus), "--taxonomy-path", str(taxonomy)]
    )
    assert rc == 1
    assert "not-in-taxonomy" in out
    assert "dangling fixture" in out


def test_main_exits_one_on_shape_violation(tmp_path: pathlib.Path) -> None:
    taxonomy = tmp_path / "taxonomy.yaml"
    _write_taxonomy(taxonomy, ["alpha"])
    corpus = _make_corpus(
        tmp_path,
        fixtures={
            "alpha.md": {"expected_marker": "alpha"},
            "broken.md": {"raw_content": "no frontmatter at all\n"},
        },
    )
    rc, out, _ = _capture_main(
        ["--fixtures-dir", str(corpus), "--taxonomy-path", str(taxonomy)]
    )
    assert rc == 1
    assert "shape-violation" in out


def test_main_exits_zero_on_full_coverage(tmp_path: pathlib.Path) -> None:
    taxonomy = tmp_path / "taxonomy.yaml"
    _write_taxonomy(taxonomy, ["alpha"])
    corpus = _make_corpus(tmp_path, fixtures={"alpha.md": {"expected_marker": "alpha"}})
    rc, out, _ = _capture_main(
        ["--fixtures-dir", str(corpus), "--taxonomy-path", str(taxonomy)]
    )
    assert rc == 0
    assert "1 passing fixture(s)" in out


def test_main_help_resolves() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_main_with_no_flags_resolves_canonical_files() -> None:
    """main() with no argv resolves canonical examples/ + schemas/ via find_repo_root."""
    rc, out, _ = _capture_main([])
    assert rc == 0
    assert "examples/synthetic-stories" in out
    assert "schemas/marker-taxonomy.yaml" in out


# ---------------------------------------------------------------------------
# Loud-fail / harness-level errors
# ---------------------------------------------------------------------------


def test_loud_fail_on_missing_fixtures_dir(tmp_path: pathlib.Path) -> None:
    taxonomy = tmp_path / "taxonomy.yaml"
    _write_taxonomy(taxonomy, ["alpha"])
    rc, _, err = _capture_main(
        [
            "--fixtures-dir",
            str(tmp_path / "does-not-exist"),
            "--taxonomy-path",
            str(taxonomy),
        ]
    )
    assert rc == 2
    assert "harness-level error" in err
    assert "examples/synthetic-stories/" in err


def test_loud_fail_on_missing_taxonomy(tmp_path: pathlib.Path) -> None:
    corpus = _make_corpus(tmp_path, fixtures={"alpha.md": {"expected_marker": "alpha"}})
    rc, _, err = _capture_main(
        [
            "--fixtures-dir",
            str(corpus),
            "--taxonomy-path",
            str(tmp_path / "missing.yaml"),
        ]
    )
    assert rc == 2
    assert "harness-level error" in err
    assert "marker-taxonomy" in err


def test_loud_fail_on_malformed_taxonomy(tmp_path: pathlib.Path) -> None:
    taxonomy = tmp_path / "broken.yaml"
    taxonomy.write_text("not a mapping\nanother line: [unclosed\n", encoding="utf-8")
    corpus = _make_corpus(tmp_path, fixtures={"alpha.md": {"expected_marker": "alpha"}})
    rc, _, err = _capture_main(
        ["--fixtures-dir", str(corpus), "--taxonomy-path", str(taxonomy)]
    )
    assert rc == 2
    assert "harness-level error" in err or "marker-taxonomy" in err


def test_loud_fail_on_taxonomy_non_string_marker_class(tmp_path: pathlib.Path) -> None:
    taxonomy = tmp_path / "taxonomy.yaml"
    payload = {
        "schema_version": "1.0",
        "markers": [{"marker_class": 99, "diagnostic_pointer": "x", "sub_classifications": []}],
    }
    taxonomy.write_text(yaml.safe_dump(payload), encoding="utf-8")
    corpus = _make_corpus(tmp_path, fixtures={"alpha.md": {"expected_marker": "alpha"}})
    rc, _, err = _capture_main(
        ["--fixtures-dir", str(corpus), "--taxonomy-path", str(taxonomy)]
    )
    assert rc == 2
    assert "non-string marker_class" in err or "marker-taxonomy" in err


def test_loud_fail_on_fixtures_dir_is_a_file(tmp_path: pathlib.Path) -> None:
    """A fixtures-dir argument that points at a regular file → exit 2."""
    taxonomy = tmp_path / "taxonomy.yaml"
    _write_taxonomy(taxonomy, ["alpha"])
    a_file = tmp_path / "not-a-dir.txt"
    a_file.write_text("hello", encoding="utf-8")
    rc, _, err = _capture_main(
        ["--fixtures-dir", str(a_file), "--taxonomy-path", str(taxonomy)]
    )
    assert rc == 2
    assert "examples/synthetic-stories/" in err


def test_unicode_decode_error_becomes_shape_violation(tmp_path: pathlib.Path) -> None:
    """Non-UTF-8 fixture file surfaces as exit-1 shape violation, not exit-2 harness error."""
    corpus = tmp_path / "synthetic-stories"
    corpus.mkdir()
    # Write a file with invalid UTF-8 bytes (0xff is never a valid UTF-8 byte)
    bad = corpus / "bad-encoding.md"
    bad.write_bytes(b"---\nexpected_marker: alpha\n---\n\xff invalid bytes\n")
    taxonomy = tmp_path / "taxonomy.yaml"
    _write_taxonomy(taxonomy, ["alpha"])
    rc, out, err = _capture_main(
        ["--fixtures-dir", str(corpus), "--taxonomy-path", str(taxonomy)]
    )
    assert rc == 1, "non-UTF-8 file is a shape violation (exit 1), not a harness error"
    assert "shape-violation" in out
    assert err == "", "shape violations go to stdout, not stderr"


# ---------------------------------------------------------------------------
# Stdout shape
# ---------------------------------------------------------------------------


def test_format_findings_header() -> None:
    result = CoverageResult(passing=[], uncovered=[], dangling=[], shape_violations=[])
    rendered = format_findings(
        result, fixtures_dir="path/to/fixtures", taxonomy_path="path/to/taxonomy.yaml"
    )
    assert "Fixture coverage check (substrate component 5)" in rendered
    assert "fixtures dir: path/to/fixtures" in rendered
    assert "taxonomy:     path/to/taxonomy.yaml" in rendered


def test_format_findings_passing_summary() -> None:
    result = CoverageResult(
        passing=[
            Reference(file_path="a.md", marker_class="a"),
            Reference(file_path="b.md", marker_class="b"),
        ],
        uncovered=[],
        dangling=[],
        shape_violations=[],
    )
    rendered = format_findings(result, fixtures_dir="x", taxonomy_path="y")
    assert "OK: 2 passing fixture(s)" in rendered
    assert "covering 2 distinct marker class(es)" in rendered


def test_format_findings_uncovered_section() -> None:
    result = CoverageResult(
        passing=[], uncovered=["alpha", "beta"], dangling=[], shape_violations=[]
    )
    rendered = format_findings(result, fixtures_dir="x", taxonomy_path="y")
    assert "FAIL: 2 uncovered marker class(es)" in rendered
    assert "uncovered marker class 'alpha'" in rendered
    assert "examples/synthetic-stories/alpha.md" in rendered


def test_format_findings_dangling_section() -> None:
    result = CoverageResult(
        passing=[],
        uncovered=[],
        dangling=[Reference(file_path="rogue.md", marker_class="bogus")],
        shape_violations=[],
    )
    rendered = format_findings(result, fixtures_dir="x", taxonomy_path="y")
    assert "FAIL: 1 dangling fixture(s)" in rendered
    assert "rogue.md" in rendered
    assert "bogus" in rendered
    assert "FR65" in rendered


def test_format_findings_shape_violations_section() -> None:
    result = CoverageResult(
        passing=[],
        uncovered=[],
        dangling=[],
        shape_violations=[
            ShapeViolation(
                file_path="broken.md",
                pointer="/expected_marker",
                message="missing required field 'expected_marker'",
                remediation="(per AC-2)",
            )
        ],
    )
    rendered = format_findings(result, fixtures_dir="x", taxonomy_path="y")
    assert "FAIL: 1 frontmatter shape-violation finding(s)" in rendered
    assert "broken.md#/expected_marker" in rendered
    assert "missing required field" in rendered


def test_format_findings_summary_present() -> None:
    """The Summary footer line is present unconditionally (Pattern 5)."""
    result = CoverageResult(passing=[], uncovered=[], dangling=[], shape_violations=[])
    rendered = format_findings(result, fixtures_dir="x", taxonomy_path="y")
    assert (
        "Summary: 0 passing marker class(es), "
        "0 uncovered marker class(es), "
        "0 dangling fixture(s), "
        "0 shape-violation finding(s)."
    ) in rendered
