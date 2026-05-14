"""Contract-coverage matrix for the Phase 1.5 completion evidence validator (Story 11.1).

This docstring IS the contract-coverage checklist required by AC-9. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced (parallel to ``tests/test_mvp_completion_evidence.py``).

AC-9 — Closed-enumeration invariants (2):
    [x] test_phase_1_5_row_ids_is_closed_eleven_element_tuple
    [x] test_status_values_is_three_element_closed_tuple

AC-9 — Parser invariants (2):
    [x] test_parse_coverage_matrix_returns_rows_in_anchor_order
    [x] test_parse_coverage_matrix_raises_anchor_markers_missing

AC-9 — Audit happy path (1):
    [x] test_audit_passes_on_canonical_fixture

AC-9 — Audit findings (8):
    [x] test_audit_emits_missing_requirement_row
    [x] test_audit_emits_unknown_requirement_id
    [x] test_audit_emits_duplicate_requirement_row
    [x] test_audit_emits_empty_cell
    [x] test_audit_emits_invalid_status_value
    [x] test_audit_emits_findings_not_integer
    [x] test_audit_emits_delivered_row_with_open_findings
    [x] test_audit_emits_row_count_mismatch

AC-9 — CLI exit-code dispatch (1):
    [x] test_cli_main_exit_codes

AC-9 — Purity contract (1):
    [x] test_audit_byte_stable_under_repetition

AC-9 — Real-artifact load-bearing (1):
    [x] test_real_artifact_audit_passes

AC-4 — Public API (1):
    [x] test_module_exports_documented_public_api

Module collection discipline (1):
    [x] test_no_find_repo_root_calls_at_module_collection_time
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

from loud_fail_harness import phase_1_5_completion_evidence as module
from loud_fail_harness.phase_1_5_completion_evidence import (
    PHASE_1_5_ROW_IDS,
    ROWS_BEGIN_ANCHOR,
    ROWS_END_ANCHOR,
    STATUS_VALUES,
    Phase15CompletionEvidenceError,
    audit,
    main,
    parse_coverage_matrix,
)


def _make_artifact_text(rows: list[tuple[str, str, str, str, str]]) -> str:
    """Build a minimal artifact body with the coverage-matrix anchors.

    The body has the header row + separator + data rows enclosed by the
    canonical anchor markers. Used by parser + audit synthetic-input
    tests. Each row tuple is ``(requirement_id, requirement_summary,
    status, evidence, findings)``; ``findings`` is a string so tests
    can inject non-integer content for the ``findings-not-integer``
    rule.
    """
    header = (
        "| Requirement ID | Requirement Summary | Status | "
        "Evidence | Findings |"
    )
    separator = "| --- | --- | --- | --- | --- |"
    body_lines = [
        "# Phase 1.5 Completion Evidence (Story 11.1)",
        "",
        "## Coverage matrix",
        "",
        header,
        separator,
        ROWS_BEGIN_ANCHOR,
    ]
    for row in rows:
        body_lines.append(
            f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} |"
        )
    body_lines.append(ROWS_END_ANCHOR)
    return "\n".join(body_lines) + "\n"


def _make_canonical_rows() -> list[tuple[str, str, str, str, str]]:
    """Build the canonical 11-row valid fixture set.

    Each row is ``delivered`` with ``Findings: 0`` and a story-doc-path
    evidence cell so the canonical fixture passes audit with 0 findings.
    Story-doc paths are pure documentation pointers; the validator does
    NOT resolve them against the filesystem (Story 11.1 AC-6).
    """
    canonical_evidence: dict[str, str] = {
        "FR-P1.5-1": (
            "_bmad-output/implementation-artifacts/"
            "10-7-reference-lad-enabled-run-fixture-end-to-end.md"
        ),
        "FR-P1.5-2": (
            "_bmad-output/implementation-artifacts/"
            "9-6-reference-mobile-project-fixture-end-to-end-run.md"
        ),
        "FR29": (
            "_bmad-output/implementation-artifacts/"
            "10-2-lad-wrapper-subagent-scaffold-pluggability-compliant.md"
        ),
        "FR30-LAD-skipped": (
            "_bmad-output/implementation-artifacts/"
            "10-5-api-key-env-var-handling-lad-skipped-marker-emission.md"
        ),
        "FR30-mobile-blocked": (
            "_bmad-output/implementation-artifacts/"
            "9-5-mobile-blocked-marker-emission-init-time-and-mid-run-paths.md"
        ),
        "FR51": (
            "_bmad-output/implementation-artifacts/"
            "10-3-lad-envelope-schema-extension-contract-pair-schema-validator-fixture.md"
        ),
        "FR56": (
            "_bmad-output/implementation-artifacts/"
            "10-4-failed-layers-enum-extension-bmad-code-review-4-layer-integration.md"
        ),
        "FR62": (
            "_bmad-output/implementation-artifacts/"
            "10-6-pluggability-ci-gate-extension-to-review-lad-cost-observability-partition-extension.md"
        ),
        "NFR-S1": (
            "_bmad-output/implementation-artifacts/"
            "10-5-api-key-env-var-handling-lad-skipped-marker-emission.md"
        ),
        "NFR-P5": (
            "_bmad-output/implementation-artifacts/"
            "10-6-pluggability-ci-gate-extension-to-review-lad-cost-observability-partition-extension.md"
        ),
        "NFR-I3": (
            "_bmad-output/implementation-artifacts/"
            "10-1-lad-mcp-server-selection-adr-dependencies-yaml-lad-activation.md"
        ),
    }
    rows: list[tuple[str, str, str, str, str]] = []
    for rid in PHASE_1_5_ROW_IDS:
        rows.append(
            (
                rid,
                f"summary for {rid}",
                "delivered",
                canonical_evidence[rid],
                "0",
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# AC-9 — Closed-enumeration invariants (2)                                     #
# --------------------------------------------------------------------------- #


def test_phase_1_5_row_ids_is_closed_eleven_element_tuple() -> None:
    """PHASE_1_5_ROW_IDS is exactly the 11-element closed enumeration per AC-2."""
    assert PHASE_1_5_ROW_IDS == (
        "FR-P1.5-1",
        "FR-P1.5-2",
        "FR29",
        "FR30-LAD-skipped",
        "FR30-mobile-blocked",
        "FR51",
        "FR56",
        "FR62",
        "NFR-S1",
        "NFR-P5",
        "NFR-I3",
    )
    assert len(PHASE_1_5_ROW_IDS) == 11
    assert len(set(PHASE_1_5_ROW_IDS)) == 11, (
        "PHASE_1_5_ROW_IDS must be a set (no duplicates)"
    )


def test_status_values_is_three_element_closed_tuple() -> None:
    """STATUS_VALUES is exactly the three-element closed enumeration per AC-2."""
    assert STATUS_VALUES == ("delivered", "partial", "not-shipped")
    assert len(set(STATUS_VALUES)) == 3


# --------------------------------------------------------------------------- #
# AC-9 — Parser invariants (2)                                                 #
# --------------------------------------------------------------------------- #


def test_parse_coverage_matrix_returns_rows_in_anchor_order(
    tmp_path: pathlib.Path,
) -> None:
    """Parser preserves the row order between the anchor markers."""
    rows = _make_canonical_rows()
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    parsed = parse_coverage_matrix(artifact)
    assert tuple(r.requirement_id for r in parsed) == PHASE_1_5_ROW_IDS
    assert parsed[0].status == "delivered"
    assert parsed[0].findings == 0


def test_parse_coverage_matrix_raises_anchor_markers_missing(
    tmp_path: pathlib.Path,
) -> None:
    """Missing anchor markers raise ``anchor-markers-missing``."""
    artifact = tmp_path / "artifact.md"
    artifact.write_text("# header only — no anchors\n", encoding="utf-8")
    with pytest.raises(Phase15CompletionEvidenceError) as exc_info:
        parse_coverage_matrix(artifact)
    assert exc_info.value.reason == "anchor-markers-missing"
    assert exc_info.value.artifact_path == artifact


# --------------------------------------------------------------------------- #
# AC-9 — Audit happy path (1)                                                  #
# --------------------------------------------------------------------------- #


def test_audit_passes_on_canonical_fixture(tmp_path: pathlib.Path) -> None:
    """Canonical 11-row fixture (all delivered, all findings 0) → 0 findings."""
    rows = _make_canonical_rows()
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    report = audit(artifact)
    assert report.findings == (), (
        f"expected 0 findings; got {report.findings!r}"
    )
    assert report.rows_observed == 11


# --------------------------------------------------------------------------- #
# AC-9 — Audit findings (8)                                                    #
# --------------------------------------------------------------------------- #


def test_audit_emits_missing_requirement_row(tmp_path: pathlib.Path) -> None:
    """Omitted FR62 emits ``missing-requirement-row`` with requirement_id=FR62."""
    rows = [r for r in _make_canonical_rows() if r[0] != "FR62"]
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    report = audit(artifact)
    findings_by_key = {
        (f.rule, f.requirement_id) for f in report.findings
    }
    assert ("missing-requirement-row", "FR62") in findings_by_key


def test_audit_emits_unknown_requirement_id(tmp_path: pathlib.Path) -> None:
    """Stray ``FR16`` row emits ``unknown-requirement-id``."""
    rows = _make_canonical_rows()
    rows.append(
        (
            "FR16",
            "summary for FR16",
            "delivered",
            "_bmad-output/implementation-artifacts/some-story.md",
            "0",
        )
    )
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    report = audit(artifact)
    findings_by_key = {
        (f.rule, f.requirement_id) for f in report.findings
    }
    assert ("unknown-requirement-id", "FR16") in findings_by_key


def test_audit_emits_duplicate_requirement_row(
    tmp_path: pathlib.Path,
) -> None:
    """Duplicate FR29 row emits ``duplicate-requirement-row``."""
    rows = _make_canonical_rows()
    fr29_row = next(r for r in rows if r[0] == "FR29")
    rows.append(fr29_row)
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    report = audit(artifact)
    findings_by_key = {
        (f.rule, f.requirement_id) for f in report.findings
    }
    assert ("duplicate-requirement-row", "FR29") in findings_by_key


def test_audit_unknown_id_twice_does_not_emit_duplicate_requirement_row(
    tmp_path: pathlib.Path,
) -> None:
    """Unknown ID appearing twice emits unknown-requirement-id twice, NOT duplicate-requirement-row.

    Regression test for the bug where audit() tracked unknown IDs in seen_ids,
    causing a spurious duplicate-requirement-row finding for non-enumerated IDs.
    Unknown IDs are not Phase 1.5 requirements; the duplicate-row rule message
    "each Phase 1.5 requirement must have exactly one row" does not apply to them.
    """
    rows = _make_canonical_rows()
    stray_row = (
        "FR16",
        "summary for FR16",
        "delivered",
        "_bmad-output/implementation-artifacts/some-story.md",
        "0",
    )
    rows.append(stray_row)
    rows.append(stray_row)  # FR16 appears twice
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    report = audit(artifact)
    rules = [f.rule for f in report.findings]
    assert rules.count("unknown-requirement-id") == 2
    assert "duplicate-requirement-row" not in rules, (
        "audit() must not emit duplicate-requirement-row for unknown IDs — "
        "they are not Phase 1.5 requirements and should not contribute to "
        "duplicate-row detection."
    )


def test_audit_emits_empty_cell(tmp_path: pathlib.Path) -> None:
    """Empty Evidence cell for FR51 emits ``empty-cell``."""
    rows = _make_canonical_rows()
    fr51_idx = next(i for i, r in enumerate(rows) if r[0] == "FR51")
    rows[fr51_idx] = (
        rows[fr51_idx][0],
        rows[fr51_idx][1],
        rows[fr51_idx][2],
        "",
        rows[fr51_idx][4],
    )
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    report = audit(artifact)
    matching = [
        f for f in report.findings
        if f.rule == "empty-cell"
        and f.requirement_id == "FR51"
        and f.column == "Evidence"
    ]
    assert matching, (
        f"expected empty-cell finding for FR51/Evidence; got "
        f"{[(f.rule, f.requirement_id, f.column) for f in report.findings]!r}"
    )


def test_audit_emits_invalid_status_value(tmp_path: pathlib.Path) -> None:
    """Status ``shipped`` on FR-P1.5-1 emits ``invalid-status-value``."""
    rows = _make_canonical_rows()
    fr1_idx = next(i for i, r in enumerate(rows) if r[0] == "FR-P1.5-1")
    rows[fr1_idx] = (
        rows[fr1_idx][0],
        rows[fr1_idx][1],
        "shipped",
        rows[fr1_idx][3],
        rows[fr1_idx][4],
    )
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    report = audit(artifact)
    findings_by_key = {
        (f.rule, f.requirement_id) for f in report.findings
    }
    assert ("invalid-status-value", "FR-P1.5-1") in findings_by_key


def test_audit_emits_findings_not_integer(tmp_path: pathlib.Path) -> None:
    """Findings cell ``pending`` on NFR-S1 emits ``findings-not-integer``."""
    rows = _make_canonical_rows()
    nfr_idx = next(i for i, r in enumerate(rows) if r[0] == "NFR-S1")
    rows[nfr_idx] = (
        rows[nfr_idx][0],
        rows[nfr_idx][1],
        rows[nfr_idx][2],
        rows[nfr_idx][3],
        "pending",
    )
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    report = audit(artifact)
    findings_by_key = {
        (f.rule, f.requirement_id) for f in report.findings
    }
    assert ("findings-not-integer", "NFR-S1") in findings_by_key


def test_audit_emits_delivered_row_with_open_findings(
    tmp_path: pathlib.Path,
) -> None:
    """Delivered row with Findings: 3 emits ``delivered-row-with-open-findings``."""
    rows = _make_canonical_rows()
    fr29_idx = next(i for i, r in enumerate(rows) if r[0] == "FR29")
    rows[fr29_idx] = (
        rows[fr29_idx][0],
        rows[fr29_idx][1],
        "delivered",
        rows[fr29_idx][3],
        "3",
    )
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    report = audit(artifact)
    findings_by_key = {
        (f.rule, f.requirement_id) for f in report.findings
    }
    assert ("delivered-row-with-open-findings", "FR29") in findings_by_key


def test_audit_emits_row_count_mismatch(tmp_path: pathlib.Path) -> None:
    """A 10-row artifact (one row missing) emits BOTH row-count-mismatch
    AND missing-requirement-row — the rules are non-overlapping in scope.
    """
    rows = _make_canonical_rows()[:-1]  # drop NFR-I3
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    report = audit(artifact)
    rules_seen = {f.rule for f in report.findings}
    assert "row-count-mismatch" in rules_seen
    assert "missing-requirement-row" in rules_seen
    missing_ids = {
        f.requirement_id
        for f in report.findings
        if f.rule == "missing-requirement-row"
    }
    assert "NFR-I3" in missing_ids


# --------------------------------------------------------------------------- #
# AC-9 — CLI exit-code dispatch (1)                                            #
# --------------------------------------------------------------------------- #


def test_cli_main_exit_codes(tmp_path: pathlib.Path) -> None:
    """main() exits 0 on canonical input, 1 on findings, 2 on anchor-missing."""
    rows = _make_canonical_rows()
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    # Exit 0 — canonical pass.
    exit_code = main(
        ["--artifact-path", str(artifact), "--repo-root", str(tmp_path)]
    )
    assert exit_code == 0

    # Exit 1 — drop one row to trigger findings.
    rows_one_missing = [r for r in rows if r[0] != "FR-P1.5-1"]
    artifact.write_text(_make_artifact_text(rows_one_missing), encoding="utf-8")
    exit_code = main(
        ["--artifact-path", str(artifact), "--repo-root", str(tmp_path)]
    )
    assert exit_code == 1

    # Exit 2 — anchor-missing artifact (substrate-level error).
    broken = tmp_path / "broken.md"
    broken.write_text("# no anchors\n", encoding="utf-8")
    exit_code = main(
        ["--artifact-path", str(broken), "--repo-root", str(tmp_path)]
    )
    assert exit_code == 2


# --------------------------------------------------------------------------- #
# AC-9 — Purity contract (1)                                                   #
# --------------------------------------------------------------------------- #


def test_audit_byte_stable_under_repetition(tmp_path: pathlib.Path) -> None:
    """Repeated audit() calls on identical inputs produce byte-identical reports."""
    rows = _make_canonical_rows()
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    report_a = audit(artifact)
    report_b = audit(artifact)
    assert report_a == report_b
    assert report_a.model_dump() == report_b.model_dump()
    # Also assert render_report is byte-identical on the same input —
    # the AC-9 byte-stability assertion targets render_report output.
    assert module.render_report(report_a) == module.render_report(report_b)


# --------------------------------------------------------------------------- #
# AC-9 — Real-artifact load-bearing (1)                                        #
# --------------------------------------------------------------------------- #


def test_real_artifact_audit_passes() -> None:
    """The actual docs/phase-1.5-completion-evidence.md passes audit() with 0 findings.

    THIS test is the load-bearing assertion that mirrors the CI gate
    invocation. A failure here surfaces a `partial`-row miss OR an
    AC-5 discipline violation BEFORE CI even runs the gate step.
    """
    here = pathlib.Path(__file__).resolve()
    artifact_path: pathlib.Path | None = None
    for candidate in [here, *here.parents]:
        path = candidate / "docs" / "phase-1.5-completion-evidence.md"
        if path.is_file():
            artifact_path = path
            break
    if artifact_path is None:
        pytest.skip(
            "docs/phase-1.5-completion-evidence.md not located — running "
            "from a path that has no docs/ ancestor (unexpected for inner-"
            "repo CI)."
        )
    report = audit(artifact_path)
    assert report.findings == (), (
        f"expected 0 findings on real artifact; got "
        f"{[(f.rule, f.requirement_id, f.column, f.diagnostic) for f in report.findings]!r}"
    )
    assert report.rows_observed == 11


# --------------------------------------------------------------------------- #
# AC-4 — Public API                                                            #
# --------------------------------------------------------------------------- #


def test_module_exports_documented_public_api() -> None:
    """Module's ``__all__`` carries the documented public API per AC-4."""
    assert set(module.__all__) == {
        "ARTIFACT_RELATIVE_PATH",
        "CoverageReport",
        "CoverageRow",
        "LintFinding",
        "PHASE_1_5_ROW_IDS",
        "Phase15CompletionEvidenceError",
        "ROWS_BEGIN_ANCHOR",
        "ROWS_END_ANCHOR",
        "STATUS_VALUES",
        "audit",
        "main",
        "parse_coverage_matrix",
        "render_report",
    }


# --------------------------------------------------------------------------- #
# Module collection discipline                                                 #
# --------------------------------------------------------------------------- #


def test_no_find_repo_root_calls_at_module_collection_time() -> None:
    """Per Epic 1 retro Action #1, no ``find_repo_root()`` calls run at import.

    Walks the AST of THIS test module's source and asserts that every
    ``find_repo_root`` reference is inside a function body (not at
    module-top-level), so pytest collection of this file does not
    invoke the resolver.
    """
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr)):
            for descendant in ast.walk(node):
                if (
                    isinstance(descendant, ast.Name)
                    and descendant.id == "find_repo_root"
                ):
                    raise AssertionError(
                        "find_repo_root referenced at module-top-level "
                        f"on line {descendant.lineno} — Epic 1 retro "
                        "Action #1 forbids this; resolution must happen "
                        "inside test functions."
                    )


# --------------------------------------------------------------------------- #
# Subprocess CLI smoke (defensive — `uv run phase-1-5-completion-evidence`)    #
# --------------------------------------------------------------------------- #


def test_cli_entry_point_invocation_smoke(tmp_path: pathlib.Path) -> None:
    """Smoke-test ``python -m loud_fail_harness.phase_1_5_completion_evidence``.

    Verifies the CLI entry point is invocable as a script via the
    Python interpreter (mirrors the production
    ``uv run phase-1-5-completion-evidence`` invocation path). Asserts
    the process exits with the expected code AND emits non-empty stdout
    OR stderr so the gate's diagnostic surface is visible to the
    release manager.
    """
    rows = _make_canonical_rows()
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from loud_fail_harness.phase_1_5_completion_evidence "
                "import main; import sys; sys.exit(main(sys.argv[1:]))"
            ),
            "--artifact-path",
            str(artifact),
            "--repo-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"expected exit 0 on canonical artifact; got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "phase-1-5-completion-evidence" in result.stdout
    assert "0 findings" in result.stdout
