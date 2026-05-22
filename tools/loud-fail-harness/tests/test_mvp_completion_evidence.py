"""Contract-coverage matrix for the MVP completion evidence validator (Story 8.7).

This docstring IS the contract-coverage checklist required by AC-9. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced (parallel to ``tests/test_status_command.py`` and
``tests/test_no_destructive_resume_lint.py``).

AC-9 — Closed-enumeration invariants (3):
    [x] test_mvp_fr_ids_constant_matches_prd_enumeration
    [x] test_nfr_ids_constant_matches_prd_enumeration
    [x] test_journey_values_constant_is_closed_four_element_set

AC-9 — Parser invariants (3):
    [x] test_parse_coverage_matrix_returns_rows_in_anchor_order
    [x] test_parse_coverage_matrix_raises_when_anchor_markers_missing
    [x] test_parse_coverage_matrix_raises_when_row_fails_pydantic_validation

AC-9 — Audit findings (4):
    [x] test_audit_emits_missing_requirement_row_when_fr_absent
    [x] test_audit_emits_unknown_requirement_id_when_extra_row_present
    [x] test_audit_emits_empty_cell_when_evidence_link_blank
    [x] test_audit_emits_evidence_link_not_resolved_when_relative_path_missing

AC-9 — Audit happy path (1):
    [x] test_audit_returns_zero_findings_on_complete_artifact

AC-9 — CLI smoke (1):
    [x] test_main_exits_zero_on_complete_artifact_and_one_on_findings

AC-4 — Public API + purity (2):
    [x] test_module_exports_documented_public_api
    [x] test_audit_purity_byte_identical_on_repeated_calls

AC-9 — Module collection discipline (1):
    [x] test_no_find_repo_root_calls_at_module_collection_time
"""

from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys

import pytest

from loud_fail_harness import mvp_completion_evidence as module
from loud_fail_harness.mvp_completion_evidence import (
    JOURNEY_VALUES,
    MVP_FR_IDS,
    NFR_IDS,
    ROWS_BEGIN_ANCHOR,
    ROWS_END_ANCHOR,
    MvpCompletionEvidenceError,
    audit,
    main,
    parse_coverage_matrix,
)


_PRD_FR_LINE_RE = re.compile(r"^- \*\*FR(?P<num>\d+[a-z]?)(?: \(Phase 1\.5\))?:\*\*")
_PRD_NFR_LINE_RE = re.compile(r"^- \*\*(?P<id>NFR-[A-Z]\d+):\*\*")


def _resolve_prd_path() -> pathlib.Path | None:
    """Locate ``prd.md`` from a tests-dir-relative starting point.

    Returns ``None`` when the outer workspace is not present (e.g. a CI
    checkout of the inner repo only). Callers must call ``pytest.skip()``
    when ``None`` is returned — the prd.md cross-check is a dev-time drift
    detector that is meaningless without the file.

    Avoids ``find_repo_root()`` calls at module-collection time per
    Epic 1 retro Action #1; the resolution happens inside individual
    tests so collection-time imports stay side-effect-free.
    """
    here = pathlib.Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        prd_path = (
            candidate / "_bmad-output" / "planning-artifacts" / "prd.md"
        )
        if prd_path.is_file():
            return prd_path
    return None


def _parse_prd_fr_ids(prd_path: pathlib.Path) -> tuple[str, ...]:
    """Extract FR IDs from the PRD's MVP-FR enumeration block.

    Reads :file:`prd.md` and returns the ordered tuple of all
    ``- **FR<n>[<sub-letter>]:**`` lines from the MVP block. Stops
    parsing when the Phase-1.5 / Post-MVP section header is reached
    so post-MVP FRs (``FR-P1.5-1``, ``FR-P2-1``, etc.) are excluded.
    """
    text = prd_path.read_text(encoding="utf-8")
    fr_ids: list[str] = []
    # The PRD's MVP FR enumeration runs between the FRs section header
    # (line 805ish) and the explicit `### Post-MVP FRs` divider; the
    # earlier `### Post-MVP Features` at line 770 is in the rejected-
    # ideas table and contains no FR-tagged lines, so the post-MVP-FR
    # block is the canonical stop boundary.
    in_post_mvp_fr_block = False
    for line in text.splitlines():
        if line.startswith("### Post-MVP FRs"):
            in_post_mvp_fr_block = True
            continue
        if in_post_mvp_fr_block:
            continue
        match = _PRD_FR_LINE_RE.match(line)
        if match:
            fr_ids.append("FR" + match.group("num"))
    return tuple(fr_ids)


def _parse_prd_nfr_ids(prd_path: pathlib.Path) -> tuple[str, ...]:
    """Extract NFR IDs from the PRD's NFR enumeration block."""
    text = prd_path.read_text(encoding="utf-8")
    nfr_ids: list[str] = []
    for line in text.splitlines():
        match = _PRD_NFR_LINE_RE.match(line)
        if match:
            nfr_ids.append(match.group("id"))
    return tuple(nfr_ids)


def _make_artifact_text(rows: list[tuple[str, str, str, str, str]]) -> str:
    """Build a minimal artifact body with the coverage-matrix anchors.

    The body has the header row + separator + data rows enclosed by the
    canonical anchor markers. Used by parser + audit synthetic-input
    tests.
    """
    header = (
        "| Requirement ID | Requirement Summary | Exercising Journey | "
        "Observable Behavior Demonstrated | Evidence Link |"
    )
    separator = "| --- | --- | --- | --- | --- |"
    body_lines = [
        "# MVP Completion Evidence — Full Project Surface (Story 8.7)",
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


def _make_complete_rows(
    repo_root: pathlib.Path, evidence_filename: str = "ev.md"
) -> list[tuple[str, str, str, str, str]]:
    """Build a 103-row valid input set + materialize the evidence file.

    All rows reuse the same fixture-evidence path so the resolution
    test is straightforward. The evidence file is created under
    ``repo_root`` so :func:`_resolve_evidence_link` returns ``True``.
    """
    evidence_dir = repo_root / "docs" / "mvp-completion-evidence" / "fixture"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_file = evidence_dir / evidence_filename
    evidence_file.write_text("fixture evidence", encoding="utf-8")
    rel_path = (
        f"docs/mvp-completion-evidence/fixture/{evidence_filename}"
    )
    rows: list[tuple[str, str, str, str, str]] = []
    for fr_id in MVP_FR_IDS:
        rows.append(
            (
                fr_id,
                f"summary for {fr_id}",
                "journey-1-happy-path",
                f"observed behavior for {fr_id}",
                rel_path,
            )
        )
    for nfr_id in NFR_IDS:
        rows.append(
            (
                nfr_id,
                f"summary for {nfr_id}",
                "journey-2-honest-failure",
                f"observed behavior for {nfr_id}",
                rel_path,
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# AC-9 — Closed-enumeration invariants (3)                                     #
# --------------------------------------------------------------------------- #


def test_mvp_fr_ids_constant_matches_prd_enumeration() -> None:
    """The module's MVP_FR_IDS constant equals PRD's FR enumeration minus FR29."""
    prd_path = _resolve_prd_path()
    if prd_path is None:
        pytest.skip("prd.md not available — outer workspace not checked out")
    prd_fr_ids = _parse_prd_fr_ids(prd_path)
    expected = tuple(fr_id for fr_id in prd_fr_ids if fr_id != "FR29")
    assert MVP_FR_IDS == expected, (
        f"MVP_FR_IDS drift: module={MVP_FR_IDS!r} prd-minus-FR29={expected!r}"
    )
    assert len(MVP_FR_IDS) == 69, (
        f"AC-2 expects 69 FR rows; got {len(MVP_FR_IDS)}"
    )
    assert "FR29" not in MVP_FR_IDS, (
        "FR29 is Phase-1.5 per prd.md:849 and must be OMITTED from MVP_FR_IDS"
    )


def test_nfr_ids_constant_matches_prd_enumeration() -> None:
    """The module's NFR_IDS constant equals the NFR IDs parsed from prd.md."""
    prd_path = _resolve_prd_path()
    if prd_path is None:
        pytest.skip("prd.md not available — outer workspace not checked out")
    prd_nfr_ids = _parse_prd_nfr_ids(prd_path)
    assert NFR_IDS == prd_nfr_ids, (
        f"NFR_IDS drift: module={NFR_IDS!r} prd={prd_nfr_ids!r}"
    )
    assert len(NFR_IDS) == 34, (
        f"AC-2 expects 34 NFR rows; got {len(NFR_IDS)}"
    )


def test_journey_values_constant_is_closed_four_element_set() -> None:
    """JOURNEY_VALUES is exactly the four-element closed enumeration per AC-2."""
    assert JOURNEY_VALUES == (
        "journey-1-happy-path",
        "journey-2-honest-failure",
        "journey-3-retry-firewall",
        "journey-4-bail-back",
    )
    # The Pydantic Literal on CoverageRow.exercising_journey enforces the
    # closure structurally; this test pins the order + the content.
    assert len(set(JOURNEY_VALUES)) == 4


# --------------------------------------------------------------------------- #
# AC-9 — Parser invariants (3)                                                 #
# --------------------------------------------------------------------------- #


def test_parse_coverage_matrix_returns_rows_in_anchor_order(
    tmp_path: pathlib.Path,
) -> None:
    """Parser preserves the row order between the anchor markers."""
    rows = [
        ("FR1", "summary FR1", "journey-1-happy-path", "behavior FR1", "ev.md"),
        ("FR2", "summary FR2", "journey-2-honest-failure", "behavior FR2", "ev.md"),
        ("NFR-P3", "summary NFR-P3", "journey-3-retry-firewall", "behavior NFR-P3", "ev.md"),
    ]
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    parsed = parse_coverage_matrix(artifact)
    assert tuple(r.requirement_id for r in parsed) == ("FR1", "FR2", "NFR-P3")
    assert parsed[0].exercising_journey == "journey-1-happy-path"
    assert parsed[2].evidence_link == "ev.md"


def test_parse_coverage_matrix_raises_when_anchor_markers_missing(
    tmp_path: pathlib.Path,
) -> None:
    """Missing anchor markers raise ``anchor-markers-missing``."""
    artifact = tmp_path / "artifact.md"
    artifact.write_text("# header only — no anchors\n", encoding="utf-8")
    with pytest.raises(MvpCompletionEvidenceError) as exc_info:
        parse_coverage_matrix(artifact)
    assert exc_info.value.reason == "anchor-markers-missing"
    assert exc_info.value.artifact_path == artifact


def test_parse_coverage_matrix_raises_when_row_fails_pydantic_validation(
    tmp_path: pathlib.Path,
) -> None:
    """An empty cell triggers ``malformed-row`` (Pydantic min_length=1)."""
    rows = [
        ("FR1", "", "journey-1-happy-path", "behavior FR1", "ev.md"),
    ]
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    with pytest.raises(MvpCompletionEvidenceError) as exc_info:
        parse_coverage_matrix(artifact)
    assert exc_info.value.reason == "malformed-row"


# --------------------------------------------------------------------------- #
# AC-9 — Audit findings (4)                                                    #
# --------------------------------------------------------------------------- #


def test_audit_emits_missing_requirement_row_when_fr_absent(
    tmp_path: pathlib.Path,
) -> None:
    """An expected FR ID absent from the artifact emits ``missing-requirement-row``."""
    repo_root = tmp_path
    rows = _make_complete_rows(repo_root)
    # Drop FR1.
    rows = [r for r in rows if r[0] != "FR1"]
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")

    report = audit(artifact, repo_root)
    findings_by_rule = {
        (f.rule, f.requirement_id) for f in report.findings
    }
    assert ("missing-requirement-row", "FR1") in findings_by_rule
    # Row count is now 102, so we also expect a row-count-mismatch.
    assert any(f.rule == "row-count-mismatch" for f in report.findings)


def test_audit_emits_unknown_requirement_id_when_extra_row_present(
    tmp_path: pathlib.Path,
) -> None:
    """A row with an unrecognized FR ID emits ``unknown-requirement-id``."""
    repo_root = tmp_path
    rows = _make_complete_rows(repo_root)
    rows.append(
        (
            "FR67",
            "summary FR67",
            "journey-1-happy-path",
            "observed behavior FR67",
            "docs/mvp-completion-evidence/fixture/ev.md",
        )
    )
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")

    report = audit(artifact, repo_root)
    findings_by_rule = {
        (f.rule, f.requirement_id) for f in report.findings
    }
    assert ("unknown-requirement-id", "FR67") in findings_by_rule


def test_audit_emits_empty_cell_when_evidence_link_blank(
    tmp_path: pathlib.Path,
) -> None:
    """A row with a blank Evidence Link cell emits ``empty-cell`` for that column."""
    repo_root = tmp_path
    rows = _make_complete_rows(repo_root)
    # Replace FR1's Evidence Link with empty.
    fr1_idx = next(i for i, r in enumerate(rows) if r[0] == "FR1")
    rows[fr1_idx] = (rows[fr1_idx][0], rows[fr1_idx][1], rows[fr1_idx][2], rows[fr1_idx][3], "")
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")

    report = audit(artifact, repo_root)
    matching = [
        f for f in report.findings
        if f.rule == "empty-cell"
        and f.requirement_id == "FR1"
        and f.column == "Evidence Link"
    ]
    assert matching, (
        f"expected empty-cell finding for FR1/Evidence Link; got "
        f"{[(f.rule, f.requirement_id, f.column) for f in report.findings]!r}"
    )


def test_audit_emits_evidence_link_not_resolved_when_relative_path_missing(
    tmp_path: pathlib.Path,
) -> None:
    """A row with an evidence link pointing to a non-existent file fails resolution."""
    repo_root = tmp_path
    rows = _make_complete_rows(repo_root)
    fr1_idx = next(i for i, r in enumerate(rows) if r[0] == "FR1")
    rows[fr1_idx] = (
        rows[fr1_idx][0],
        rows[fr1_idx][1],
        rows[fr1_idx][2],
        rows[fr1_idx][3],
        "docs/mvp-completion-evidence/journey-1/nonexistent.md",
    )
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")

    report = audit(artifact, repo_root)
    matching = [
        f for f in report.findings
        if f.rule == "evidence-link-not-resolved"
        and f.requirement_id == "FR1"
    ]
    assert matching, (
        f"expected evidence-link-not-resolved for FR1; got "
        f"{[(f.rule, f.requirement_id) for f in report.findings]!r}"
    )


# --------------------------------------------------------------------------- #
# AC-9 — Audit happy path (1)                                                  #
# --------------------------------------------------------------------------- #


def test_audit_returns_zero_findings_on_complete_artifact(
    tmp_path: pathlib.Path,
) -> None:
    """A complete 103-row artifact with all evidence links resolving yields 0 findings."""
    repo_root = tmp_path
    rows = _make_complete_rows(repo_root)
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")

    report = audit(artifact, repo_root)
    assert report.findings == (), (
        f"expected 0 findings; got {report.findings!r}"
    )
    assert report.total_rows_observed == 103
    assert report.mvp_fr_count_observed == 69
    assert report.nfr_count_observed == 34


# --------------------------------------------------------------------------- #
# AC-9 — CLI smoke (1)                                                         #
# --------------------------------------------------------------------------- #


def test_main_exits_zero_on_complete_artifact_and_one_on_findings(
    tmp_path: pathlib.Path,
) -> None:
    """``main`` exits 0 on complete input and 1 on any finding."""
    repo_root = tmp_path
    rows = _make_complete_rows(repo_root)
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")

    exit_code = main(
        [
            "--artifact-path",
            str(artifact),
            "--repo-root",
            str(repo_root),
        ]
    )
    assert exit_code == 0

    # Now drop a row and expect exit 1.
    rows = [r for r in rows if r[0] != "FR1"]
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")
    exit_code = main(
        [
            "--artifact-path",
            str(artifact),
            "--repo-root",
            str(repo_root),
        ]
    )
    assert exit_code == 1


# --------------------------------------------------------------------------- #
# AC-4 — Public API + purity                                                   #
# --------------------------------------------------------------------------- #


def test_module_exports_documented_public_api() -> None:
    """Module's ``__all__`` carries the documented public API per AC-4."""
    assert set(module.__all__) == {
        "ARTIFACT_RELATIVE_PATH",
        "CoverageReport",
        "CoverageRow",
        "JOURNEY_VALUES",
        "LintFinding",
        "MVP_FR_IDS",
        "MvpCompletionEvidenceError",
        "NFR_IDS",
        "ROWS_BEGIN_ANCHOR",
        "ROWS_END_ANCHOR",
        "audit",
        "main",
        "parse_coverage_matrix",
        "render_report",
    }


def test_audit_purity_byte_identical_on_repeated_calls(
    tmp_path: pathlib.Path,
) -> None:
    """Repeated audit() calls on identical inputs produce byte-identical reports."""
    repo_root = tmp_path
    rows = _make_complete_rows(repo_root)
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")

    report_a = audit(artifact, repo_root)
    report_b = audit(artifact, repo_root)
    assert report_a == report_b
    assert report_a.model_dump() == report_b.model_dump()


# --------------------------------------------------------------------------- #
# AC-9 — Module collection discipline                                          #
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
    # Top-level expressions / assignments must not call find_repo_root.
    for node in tree.body:
        for descendant in ast.walk(node):
            if isinstance(descendant, ast.Call):
                # A FunctionDef body is fine; we only check *direct*
                # top-level statements (i.e., not inside FunctionDef /
                # ClassDef / AsyncFunctionDef nodes).
                pass
        # Module-top-level Assign / AnnAssign / Expr nodes are flagged
        # if they reference find_repo_root.
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
# Subprocess CLI smoke (defensive — `uv run mvp-completion-evidence` invocation)
# --------------------------------------------------------------------------- #


def test_cli_entry_point_invocation_smoke(tmp_path: pathlib.Path) -> None:
    """Smoke-test ``python -m loud_fail_harness.mvp_completion_evidence``.

    Verifies the CLI entry point is invocable as a script via the
    Python interpreter (mirrors the production
    ``uv run mvp-completion-evidence`` invocation path). Asserts the
    process exits with the expected code AND emits non-empty stdout
    OR stderr so the gate's diagnostic surface is visible to the
    release manager.
    """
    repo_root = tmp_path
    rows = _make_complete_rows(repo_root)
    artifact = tmp_path / "artifact.md"
    artifact.write_text(_make_artifact_text(rows), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from loud_fail_harness.mvp_completion_evidence import main; "
                "import sys; sys.exit(main(sys.argv[1:]))"
            ),
            "--artifact-path",
            str(artifact),
            "--repo-root",
            str(repo_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"expected exit 0 on complete artifact; got {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "mvp-completion-evidence" in result.stdout
    assert "0 findings" in result.stdout
