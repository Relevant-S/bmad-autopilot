"""Phase 2 completion evidence validator (Story 23.1). FR-P2-1…10 + Phase 2 NFR extensions + Phase 2-touched MVP FRs + Pattern 5/6 + ADR-003 substrate-component-count posture.

Architectural placement (Story 23.1 Dev Notes "no new substrate
components, no new marker classes, no new external Python dependencies"):
this module is a CONSUMER LIBRARY parallel to Story 8.7's
:mod:`mvp_completion_evidence`, Story 11.1's
:mod:`phase_1_5_completion_evidence` (the closest sibling in shape —
THIS module mirrors it), Story 6.3's :mod:`marker_coverage_audit`,
Story 7.6's :mod:`init_non_destructive_guard`, Story 7.8's
:mod:`tea_boundary_orientation`, and Story 7.9's
:mod:`onboarding_benchmark`. It is NOT a sixth substrate component
beyond ADR-003's enumerated five (Architecture View 2 / ADR-003
Consequence 1 keeps the substrate-component count at FIVE). The entry
point is library-as-CLI-aid invoked from
:file:`bmad-autopilot/.github/workflows/ci.yml` per Story 23.1 AC-8 —
the Phase 2 release-readiness gate that blocks Epic 23's ``done``
transition until Phase 2 gaps are remediated. Sibling, not replacement
of the Phase 1 :mod:`mvp_completion_evidence` + Phase 1.5
:mod:`phase_1_5_completion_evidence` validators — all three gates run
side-by-side: Phase 1's 102-row gate continues to enforce MVP coverage;
Phase 1.5's 11-row gate continues to enforce Phase-1.5-additive
coverage; THIS gate enforces Phase-2-additive coverage.

What this validator asserts (per Story 23.1 AC-2 + AC-4 verbatim):
    Walks the closed Phase 2 row enumeration (29 IDs: 10 net-new
    Phase 2 FRs + 7 Phase 2 NFR extensions + 12 Phase 2-touched MVP
    FRs, per :file:`epics-phase-2.md:999`) against
    :file:`docs/phase-2-completion-evidence.md`'s coverage matrix:
        (a) every Phase 2 row ID has exactly one row;
        (b) every row's five columns are non-empty;
        (c) every row's ``Status`` is one of the four closed values
            (``delivered`` / ``partial`` / ``not-shipped`` /
            ``deferred-to-phase-3``);
        (d) every row's ``Findings`` cell parses as a non-negative
            integer;
        (e) no ``delivered`` row carries ``Findings > 0`` (integrity
            invariant — a row is not delivered while findings remain;
            ``partial`` / ``not-shipped`` / ``deferred-to-phase-3``
            rows are exempt).

Divergence from :mod:`phase_1_5_completion_evidence` (Story 23.1
AC-2 + AC-3): the SINGLE deliberate delta is the extended four-value
status vocabulary — the new ``deferred-to-phase-3`` value records a
requirement whose surface intentionally carries to Phase 3. It flows
through exactly three places: :data:`STATUS_VALUES`,
:class:`CoverageRow`'s ``status`` ``Literal``, and the
``delivered-row-with-open-findings`` exemption in :func:`audit`. No
new lint rule, no new column, no anchor-name collision. The nine
:class:`LintFinding` rules are IDENTICAL to the Phase 1.5 set.

Divergence from :mod:`mvp_completion_evidence` (Story 23.1 AC-6
verbatim, inherited from Phase 1.5): Phase 2 ``Evidence`` cells admit
broader shapes than Phase 1 — story-doc paths, commit SHA + short
title, test paths or pytest test IDs, and reference-run record paths
under :file:`docs/reference-runs/`. The validator does NOT resolve the
cell against the filesystem (deliberate purity-vs-validation trade-off
— Phase 2 evidence pointers include git-commit SHA strings and pytest
test IDs that are not always filesystem paths). The :class:`LintFinding`
rule set therefore OMITS Phase 1's ``evidence-link-not-resolved`` rule.

Loud-fail discipline (Pattern 5 — named invariants):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — full pass: ``report.findings == ()``; the artifact is
            complete and Epic 23 is releasable.
        1 — completeness gap: at least one finding present; PR is
            blocked until findings resolve. The dev triages each
            finding into one of three remediation classes per AC-5
            (evidence-forward-deferred / reduced-surface-shipped /
            documentation-partial).
        2 — substrate-level error: artifact unreadable, anchor markers
            missing, or rows fail Pydantic validation — the validator
            cannot complete its audit. Distinct from exit 1 to surface
            broken-input vs. incomplete-coverage as separate
            diagnostics.

Sensor-not-advisor:
    The validator REPORTS findings; it does NOT auto-edit
    :file:`docs/phase-2-completion-evidence.md`, suggest specific
    evidence paths, or rewrite cell contents. The dev interprets
    findings AND chooses remediation manually.

NOT a runtime marker emission surface:
    Per Story 1.11's atomic-vs-aggregated principle (markers signal
    atomic failure surfaces, NOT release-time observations; ratified
    in Story 8.7 AC-4 + Story 11.1 AC-4 for the prior-phase siblings),
    this validator is release-time engineering observation. NO call to
    ``record_marker_with_context`` exists in this module; NO new entry
    in :file:`schemas/marker-taxonomy.yaml` is required; NO new row in
    :file:`_data/marker_coverage_surfaces.yaml` is required.

Cross-component reuse posture:
    * :func:`loud_fail_harness._shared.find_repo_root` — REUSED for
      default repo-root resolution (called INSIDE :func:`main`, not at
      module-collection time).
    * NO other substrate-component imports — the validator is a pure
      markdown-parse + closed-enumeration audit, mirroring
      :mod:`phase_1_5_completion_evidence`'s purity contract.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Sequence
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from loud_fail_harness._shared import find_repo_root

__all__ = [
    "ARTIFACT_RELATIVE_PATH",
    "CoverageReport",
    "CoverageRow",
    "LintFinding",
    "PHASE_2_ROW_IDS",
    "Phase2CompletionEvidenceError",
    "ROWS_BEGIN_ANCHOR",
    "ROWS_END_ANCHOR",
    "STATUS_VALUES",
    "audit",
    "main",
    "parse_coverage_matrix",
    "render_report",
]


# --------------------------------------------------------------------------- #
# Module-level constants (AC-2, AC-4)                                          #
# --------------------------------------------------------------------------- #

#: The artifact path resolved relative to the inner repo root (mirrors
#: Story 8.7 + 11.1 published-evidence-doc precedent; Story 1.12a
#: documentation-promotion-boundary published-evidence-doc category).
ARTIFACT_RELATIVE_PATH: Final[str] = "docs/phase-2-completion-evidence.md"

#: Anchor markers delimiting the coverage-matrix rows (Story 23.1 AC-1).
#: The parser extracts the markdown table between these markers. Names
#: are intentionally distinct from Story 8.7's ``<!-- coverage-rows:* -->``
#: and Story 11.1's ``<!-- phase-1-5-coverage-rows:* -->`` anchors so a
#: future tool that scans all three artifacts does not confuse them.
ROWS_BEGIN_ANCHOR: Final[str] = "<!-- phase-2-coverage-rows:begin -->"
ROWS_END_ANCHOR: Final[str] = "<!-- phase-2-coverage-rows:end -->"

#: The closed 29-element Phase 2 row enumeration (Story 23.1 AC-2).
#: Order per AC-2's deterministic order: Phase 2 net-new FRs in numeric
#: order, then Phase 2 NFR extensions in planning-text order, then
#: Phase 2-touched MVP FRs in planning-text order. Authoritative source:
#: :file:`_bmad-output/planning-artifacts/epics-phase-2.md:999`.
PHASE_2_ROW_IDS: Final[tuple[str, ...]] = (
    "FR-P2-1",
    "FR-P2-2",
    "FR-P2-3",
    "FR-P2-4",
    "FR-P2-5",
    "FR-P2-6",
    "FR-P2-7",
    "FR-P2-8",
    "FR-P2-9",
    "FR-P2-10",
    "NFR-P3",
    "NFR-P5",
    "NFR-R1",
    "NFR-R3",
    "NFR-R8",
    "NFR-S3",
    "NFR-I3",
    "FR3",
    "FR4",
    "FR5",
    "FR6",
    "FR7",
    "FR8",
    "FR15",
    "FR22",
    "FR23-25",
    "FR30",
    "FR45",
    "FR48",
)

#: The closed four-element status enumeration (Story 23.1 AC-2 + AC-3).
#: Extends the Phase 1.5 three-value vocabulary with
#: ``deferred-to-phase-3`` per :file:`epics-phase-2.md:1000` verbatim.
#: Any other value in a row's ``Status`` column triggers an
#: ``invalid-status-value`` finding.
STATUS_VALUES: Final[tuple[str, ...]] = (
    "delivered",
    "partial",
    "not-shipped",
    "deferred-to-phase-3",
)

#: Allowed lint-finding rule discriminators (Story 23.1 AC-4). IDENTICAL
#: to the Phase 1.5 set — the status-vocabulary extension does NOT add a
#: lint rule. Note the deliberate divergence from
#: :mod:`mvp_completion_evidence`'s rule set: ``evidence-link-not-resolved``
#: is OMITTED (per AC-6).
_LINT_RULES: Final[tuple[str, ...]] = (
    "unknown-requirement-id",
    "missing-requirement-row",
    "duplicate-requirement-row",
    "empty-cell",
    "invalid-status-value",
    "findings-not-integer",
    "delivered-row-with-open-findings",
    "row-count-mismatch",
    "anchor-markers-missing",
)

#: Canonical column names in left-to-right order (Story 23.1 AC-1).
#: Used by the parser AND audit's empty-cell finding column attribution.
_COLUMN_NAMES: Final[tuple[str, ...]] = (
    "Requirement ID",
    "Requirement Summary",
    "Status",
    "Evidence",
    "Findings",
)


# --------------------------------------------------------------------------- #
# Structured-error class (AC-4)                                                #
# --------------------------------------------------------------------------- #


class Phase2CompletionEvidenceError(Exception):
    """Raised when the validator cannot honor its release-time contract.

    Pattern 5 — loud-fail / named invariants. The exception carries a
    structured ``reason`` discriminator naming the concrete failure
    mode so callers (the CI gate) can route to the correct surface OR
    HALT loudly rather than silently coercing to a sentinel.

    Mirrors the shape of
    :class:`loud_fail_harness.phase_1_5_completion_evidence.Phase15CompletionEvidenceError`
    byte-for-byte.

    Attributes:
        reason: Short kebab-case discriminator. Documented values:
            ``"anchor-markers-missing"`` — anchor markers absent or
            out-of-order; ``"malformed-row"`` — a row failed Pydantic
            validation (cell missing, wrong column count, malformed
            requirement_id, invalid status value, non-integer
            findings); ``"artifact-not-found"`` — the artifact path
            does not resolve to an existing file.
        artifact_path: The resolved on-disk path the parser attempted
            to read; ``None`` when failure pre-dates path resolution.
        diagnostic: Human-readable message naming the concrete defect
            + remediation pointer.
    """

    def __init__(
        self,
        *,
        reason: Literal[
            "anchor-markers-missing", "malformed-row", "artifact-not-found"
        ],
        artifact_path: pathlib.Path | None = None,
        diagnostic: str = "",
    ) -> None:
        self.reason = reason
        self.artifact_path = artifact_path
        self.diagnostic = diagnostic
        message = f"Phase2CompletionEvidenceError[{reason}]"
        if artifact_path is not None:
            message += f" artifact_path={artifact_path!s}"
        if diagnostic:
            message += f" {diagnostic}"
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Pydantic models (AC-4)                                                       #
# --------------------------------------------------------------------------- #


class CoverageRow(BaseModel):
    """One row of the Phase 2 coverage matrix (Story 23.1 AC-2 + AC-4).

    Pattern 4 — frozen so a parsed row cannot be silently mutated
    between :func:`parse_coverage_matrix` and :func:`audit`. Field
    validators enforce non-empty strings + closed-enum membership for
    ``requirement_id`` against :data:`PHASE_2_ROW_IDS`.

    Attributes:
        requirement_id: One of the 29 IDs in :data:`PHASE_2_ROW_IDS`.
            Field validator enforces closed-enum membership; rows
            with out-of-set IDs trigger ``ValidationError`` at parse
            time (raised as ``Phase2CompletionEvidenceError`` with
            ``reason="malformed-row"`` by the parser; surfaced as
            ``unknown-requirement-id`` lint findings by :func:`audit`'s
            raw-row pass).
        requirement_summary: One-line summary distilled from
            :file:`prd.md` / :file:`epics-phase-2.md`; min_length=1
            (audit emits ``empty-cell`` for blanks).
        status: Exactly one of the four closed Phase 2 status values.
            Pydantic ``Literal`` enforces the closure; invalid values
            raise ``ValidationError`` (parser converts to
            ``malformed-row`` ``Phase2CompletionEvidenceError``; audit
            emits ``invalid-status-value``).
        evidence: Non-empty pointer to a story / commit SHA / test /
            reference-run record; min_length=1. NOT resolved against
            the filesystem (Story 23.1 AC-6 — deliberate divergence
            from :mod:`mvp_completion_evidence` which DOES resolve).
        findings: Integer count of outstanding findings. ``ge=0``;
            ``delivered`` rows carrying ``findings > 0`` trigger
            ``delivered-row-with-open-findings`` lint findings by
            :func:`audit` (``partial`` / ``not-shipped`` /
            ``deferred-to-phase-3`` rows are exempt).
    """

    model_config = ConfigDict(frozen=True)

    requirement_id: str = Field(..., min_length=1)
    requirement_summary: str = Field(..., min_length=1)
    status: Literal["delivered", "partial", "not-shipped", "deferred-to-phase-3"]
    evidence: str = Field(..., min_length=1)
    findings: int = Field(..., ge=0)

    @field_validator("requirement_id")
    @classmethod
    def _requirement_id_in_closed_set(cls, v: str) -> str:
        if v not in PHASE_2_ROW_IDS:
            raise ValueError(
                f"requirement_id {v!r} is not in the closed Phase 2 "
                f"row enumeration {list(PHASE_2_ROW_IDS)!r}"
            )
        return v


class LintFinding(BaseModel):
    """A single audit finding (Story 23.1 AC-2 + AC-4).

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable rendering. Mirrors
    :class:`phase_1_5_completion_evidence.LintFinding`'s shape and rule
    set byte-for-byte (the status-vocabulary extension adds no rule).

    Attributes:
        rule: One of the nine closed rule discriminators per AC-4:
            ``unknown-requirement-id``, ``missing-requirement-row``,
            ``duplicate-requirement-row``, ``empty-cell``,
            ``invalid-status-value``, ``findings-not-integer``,
            ``delivered-row-with-open-findings``,
            ``row-count-mismatch``, ``anchor-markers-missing``.
        requirement_id: The offending requirement ID when applicable;
            ``None`` for whole-artifact rules
            (``row-count-mismatch`` / ``anchor-markers-missing``).
        column: The offending column name for ``empty-cell`` /
            ``invalid-status-value`` / ``findings-not-integer``;
            ``None`` for row-level / artifact-level rules.
        diagnostic: Human-readable message naming the violation +
            remediation pointer per NFR-O5.
    """

    model_config = ConfigDict(frozen=True)

    rule: Literal[
        "unknown-requirement-id",
        "missing-requirement-row",
        "duplicate-requirement-row",
        "empty-cell",
        "invalid-status-value",
        "findings-not-integer",
        "delivered-row-with-open-findings",
        "row-count-mismatch",
        "anchor-markers-missing",
    ]
    requirement_id: str | None = None
    column: str | None = None
    diagnostic: str = Field(..., min_length=1, max_length=500)


class CoverageReport(BaseModel):
    """Aggregate audit result (Story 23.1 AC-4).

    Frozen for hashability + determinism. Attributes:
        findings: All findings, ordered by ``(rule, requirement_id)``
            for byte-stable output.
        rows_observed: Total rows in the coverage matrix; expected
            ``29`` per :data:`PHASE_2_ROW_IDS`.
    """

    model_config = ConfigDict(frozen=True)

    findings: tuple[LintFinding, ...]
    rows_observed: int


# --------------------------------------------------------------------------- #
# Markdown-table parser (AC-4)                                                 #
# --------------------------------------------------------------------------- #


def _read_artifact_text(artifact_path: pathlib.Path) -> str:
    """Read the artifact text or raise ``artifact-not-found``."""
    try:
        return artifact_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise Phase2CompletionEvidenceError(
            reason="artifact-not-found",
            artifact_path=artifact_path,
            diagnostic=(
                "Phase 2 completion evidence artifact missing — author "
                "docs/phase-2-completion-evidence.md per Story 23.1 AC-1, "
                "OR pass --artifact-path to override the default location."
            ),
        ) from exc
    except OSError as exc:
        raise Phase2CompletionEvidenceError(
            reason="artifact-not-found",
            artifact_path=artifact_path,
            diagnostic=(
                f"Phase 2 completion evidence artifact is not readable "
                f"({type(exc).__name__}: {exc}). Check file permissions."
            ),
        ) from exc
    except UnicodeDecodeError as exc:
        raise Phase2CompletionEvidenceError(
            reason="artifact-not-found",
            artifact_path=artifact_path,
            diagnostic=(
                f"Phase 2 completion evidence artifact contains invalid "
                f"UTF-8 at byte offset {exc.start}: {exc.reason}. "
                "The file may be corrupted or saved with a non-UTF-8 "
                "encoding."
            ),
        ) from exc


def _extract_anchor_block(text: str, artifact_path: pathlib.Path) -> str:
    """Extract the substring between begin and end anchors.

    Raises ``anchor-markers-missing`` if either anchor is absent or
    the end anchor precedes the begin anchor.
    """
    begin_idx = text.find(ROWS_BEGIN_ANCHOR)
    end_idx = text.find(ROWS_END_ANCHOR)
    if begin_idx < 0 or end_idx < 0 or end_idx <= begin_idx:
        raise Phase2CompletionEvidenceError(
            reason="anchor-markers-missing",
            artifact_path=artifact_path,
            diagnostic=(
                f"Anchor markers absent or out-of-order. Expected "
                f"{ROWS_BEGIN_ANCHOR!r} before {ROWS_END_ANCHOR!r} in "
                f"{artifact_path!s}; the parser cannot locate the "
                "coverage-matrix rows."
            ),
        )
    block_start = begin_idx + len(ROWS_BEGIN_ANCHOR)
    return text[block_start:end_idx]


def _split_table_row(line: str) -> list[str] | None:
    """Split one markdown table row into cell strings.

    Returns ``None`` if the line is not a recognizable table row
    (no leading/trailing pipe, blank, or separator row). Cells are
    stripped of surrounding whitespace.
    """
    stripped = line.strip()
    if not stripped or not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    inner = stripped[1:-1]
    cells = [cell.strip() for cell in inner.split("|")]
    # Reject separator rows (e.g., "| --- | --- | ... |").
    if all(_is_separator_cell(cell) for cell in cells):
        return None
    return cells


def _is_separator_cell(cell: str) -> bool:
    if not cell:
        return False
    return all(ch in "-:" for ch in cell)


def parse_coverage_matrix(
    artifact_path: pathlib.Path,
) -> tuple[CoverageRow, ...]:
    """Parse the coverage matrix between anchor markers (Story 23.1 AC-4).

    Returns a tuple of :class:`CoverageRow` objects in artifact-row
    order. Strict — any row that fails Pydantic validation raises
    :class:`Phase2CompletionEvidenceError` with
    ``reason="malformed-row"``.

    Raises:
        Phase2CompletionEvidenceError: ``"artifact-not-found"`` if the
            artifact path does not resolve; ``"anchor-markers-missing"``
            if the anchor markers are absent or out-of-order;
            ``"malformed-row"`` if a row fails CoverageRow validation
            (empty cell, wrong column count, out-of-enum requirement_id,
            invalid status value, non-integer findings).

    Pure — no side effects.
    """
    text = _read_artifact_text(artifact_path)
    block = _extract_anchor_block(text, artifact_path)
    rows: list[CoverageRow] = []
    for line in block.splitlines():
        cells = _split_table_row(line)
        if cells is None:
            continue
        if len(cells) != len(_COLUMN_NAMES):
            raise Phase2CompletionEvidenceError(
                reason="malformed-row",
                artifact_path=artifact_path,
                diagnostic=(
                    f"row has {len(cells)} cells; expected "
                    f"{len(_COLUMN_NAMES)} ({list(_COLUMN_NAMES)!r}). "
                    f"Offending row: {line.strip()!r}"
                ),
            )
        # Skip the header row (first cell == "Requirement ID").
        if cells[0] == _COLUMN_NAMES[0]:
            continue
        try:
            findings_int = int(cells[4])
        except ValueError as exc:
            raise Phase2CompletionEvidenceError(
                reason="malformed-row",
                artifact_path=artifact_path,
                diagnostic=(
                    f"row's Findings cell {cells[4]!r} is not a base-10 "
                    f"integer. Offending row: {line.strip()!r}"
                ),
            ) from exc
        try:
            row = CoverageRow(
                requirement_id=cells[0],
                requirement_summary=cells[1],
                status=cells[2],  # type: ignore[arg-type]
                evidence=cells[3],
                findings=findings_int,
            )
        except ValidationError as exc:
            raise Phase2CompletionEvidenceError(
                reason="malformed-row",
                artifact_path=artifact_path,
                diagnostic=(
                    f"row failed Pydantic validation: {exc.errors()!r}. "
                    f"Offending row: {line.strip()!r}"
                ),
            ) from exc
        rows.append(row)
    return tuple(rows)


def _iter_raw_rows(
    artifact_path: pathlib.Path,
) -> tuple[tuple[str, ...], ...]:
    """Loose row iterator for :func:`audit` (no Pydantic strictness).

    Returns a tuple of cell-tuples. Each cell-tuple has exactly five
    string entries (padded with empty strings if the source row had
    fewer cells; longer rows are passed through verbatim so
    :func:`audit` can attribute the wrong-cell-count diagnostic).

    Raises :class:`Phase2CompletionEvidenceError` only on
    ``artifact-not-found`` or ``anchor-markers-missing`` —
    :func:`audit` collects per-row issues as :class:`LintFinding`
    objects instead of exceptions so the gate can surface ALL
    findings in one pass.
    """
    text = _read_artifact_text(artifact_path)
    block = _extract_anchor_block(text, artifact_path)
    rows: list[tuple[str, ...]] = []
    expected = len(_COLUMN_NAMES)
    for line in block.splitlines():
        cells = _split_table_row(line)
        if cells is None:
            continue
        # Skip the header row (first cell exactly matches the header).
        if cells and cells[0] == _COLUMN_NAMES[0]:
            continue
        # Pad short rows to exactly 5 cells (empty strings for missing
        # columns). Long rows (likely from unescaped '|' in cell content)
        # are NOT truncated — audit() detects and reports wrong-cell-count
        # rows explicitly.
        if len(cells) < expected:
            cells = cells + [""] * (expected - len(cells))
        rows.append(tuple(cells))
    return tuple(rows)


# --------------------------------------------------------------------------- #
# Audit (AC-4)                                                                 #
# --------------------------------------------------------------------------- #


def audit(artifact_path: pathlib.Path) -> CoverageReport:
    """Walk the coverage matrix and emit findings on any divergence.

    Per Story 23.1 AC-4. Walks the five AC-2 invariants:
        (a) set-equality between :data:`PHASE_2_ROW_IDS` and the
            parsed-row IDs (emit ``missing-requirement-row`` for any
            expected-but-absent ID; ``unknown-requirement-id`` for any
            present-but-not-enumerated ID; ``duplicate-requirement-row``
            for any ID appearing more than once);
        (b) per-row column-completeness (emit ``empty-cell`` for any
            of the 145 cells that is empty);
        (c) status-value-closure (emit ``invalid-status-value`` for
            any row whose ``Status`` is not in :data:`STATUS_VALUES`);
        (d) findings-integer (emit ``findings-not-integer`` for any
            row whose ``Findings`` cell does not parse as a
            non-negative base-10 integer);
        (e) delivered-row open-findings invariant (emit
            ``delivered-row-with-open-findings`` if a row's ``Status``
            is ``delivered`` AND ``Findings`` > 0 — ``partial`` /
            ``not-shipped`` / ``deferred-to-phase-3`` rows are exempt);
        plus the row-count invariant (emit ``row-count-mismatch`` if
        ``rows_observed != 29``).

    The validator does NOT resolve the ``Evidence`` cell against the
    filesystem (Story 23.1 AC-6 — deliberate divergence from
    :mod:`mvp_completion_evidence`).

    Raises:
        Phase2CompletionEvidenceError: only on ``"artifact-not-found"``
            or ``"anchor-markers-missing"`` (the validator cannot
            operate without input). Per-row issues are collected as
            findings, not raised, so the gate surfaces ALL findings
            in one pass.

    Returns:
        A frozen :class:`CoverageReport`. ``findings`` is sorted by
        ``(rule, requirement_id or "")`` for byte-stable output.

    Pure — no side effects.
    """
    raw_rows = _iter_raw_rows(artifact_path)

    findings: list[LintFinding] = []
    seen_ids: dict[str, int] = {}
    valid_id_set: frozenset[str] = frozenset(PHASE_2_ROW_IDS)

    for cells in raw_rows:
        # Rows with extra cells indicate an unescaped '|' in cell content.
        if len(cells) > len(_COLUMN_NAMES):
            findings.append(
                LintFinding(
                    rule="unknown-requirement-id",
                    requirement_id=cells[0].strip() or None,
                    column=_COLUMN_NAMES[0],
                    diagnostic=(
                        f"row has {len(cells)} cells, expected "
                        f"{len(_COLUMN_NAMES)} — likely an unescaped pipe "
                        "character '|' in a cell value; escape as '\\|' or "
                        "rephrase the cell content to avoid the character."
                    )[:500],
                )
            )
            continue

        requirement_id = cells[0]
        # Per-cell empty checks — applies to all five columns.
        for column_idx, cell_value in enumerate(cells):
            if not cell_value.strip():
                findings.append(
                    LintFinding(
                        rule="empty-cell",
                        requirement_id=requirement_id or None,
                        column=_COLUMN_NAMES[column_idx],
                        diagnostic=(
                            f"{requirement_id or '<missing-id>'}: "
                            f"{_COLUMN_NAMES[column_idx]} is empty — "
                            "no-empty-evidence discipline per Story 23.1 "
                            "AC-2; populate the cell or move the row's "
                            "Status to `not-shipped`."
                        ),
                    )
                )
        # If the requirement_id is missing, downstream attribution is
        # impossible; record nothing further for this row (the empty-cell
        # finding above already captured the defect).
        if not requirement_id.strip():
            continue

        # Cross-enumeration membership.
        if requirement_id not in valid_id_set:
            findings.append(
                LintFinding(
                    rule="unknown-requirement-id",
                    requirement_id=requirement_id,
                    column=_COLUMN_NAMES[0],
                    diagnostic=(
                        f"{requirement_id} is not enumerated in "
                        "PHASE_2_ROW_IDS — typo or out-of-Phase-2 "
                        "requirement (Phase 1 / Phase 1.5 MVP FRs that did "
                        "NOT extend in Phase 2 are OUT OF SCOPE; the "
                        "validator rejects them to prevent Phase-2 / "
                        "prior-phase row drift)."
                    ),
                )
            )
            # Skip further checks for unknown IDs — status / findings
            # attribution against an out-of-set ID is not actionable.
            # Do not track unknown IDs in seen_ids — they are not Phase 2
            # requirements and should not contribute to duplicate-row
            # detection (Story 11.1 review-fix carried forward).
            continue

        # Duplicate-row detection.
        seen_ids[requirement_id] = seen_ids.get(requirement_id, 0) + 1

        # Status-value-closure on the third column.
        status_value = cells[2]
        if status_value.strip() and status_value not in STATUS_VALUES:
            findings.append(
                LintFinding(
                    rule="invalid-status-value",
                    requirement_id=requirement_id,
                    column=_COLUMN_NAMES[2],
                    diagnostic=(
                        f"{requirement_id}: Status {status_value!r} is not "
                        f"in the closed set {list(STATUS_VALUES)!r}; typo "
                        "or unrecognized status label."
                    ),
                )
            )

        # Findings-integer parse on the fifth column.
        findings_cell = cells[4].strip()
        findings_int: int | None = None
        if findings_cell:
            try:
                findings_int = int(findings_cell)
                if findings_int < 0:
                    raise ValueError("negative")
            except ValueError:
                findings.append(
                    LintFinding(
                        rule="findings-not-integer",
                        requirement_id=requirement_id,
                        column=_COLUMN_NAMES[4],
                        diagnostic=(
                            f"{requirement_id}: Findings cell "
                            f"{findings_cell!r} does not parse as a "
                            "non-negative base-10 integer. Acceptable "
                            "values: `0` for delivered rows; positive "
                            "integers for partial / deferred-to-phase-3 "
                            "rows (the open-work count tracked in the cell "
                            "content OR forward-pointed to Story 23.2 / "
                            "Story 23.3 / Phase 3)."
                        ),
                    )
                )
                findings_int = None

        # Delivered-row open-findings invariant. `partial` /
        # `not-shipped` / `deferred-to-phase-3` rows are exempt — only
        # `delivered` rows must carry Findings == 0.
        if (
            status_value == "delivered"
            and findings_int is not None
            and findings_int > 0
        ):
            findings.append(
                LintFinding(
                    rule="delivered-row-with-open-findings",
                    requirement_id=requirement_id,
                    column=None,
                    diagnostic=(
                        f"{requirement_id}: Status is `delivered` but "
                        f"Findings is {findings_int} (> 0). A row is not "
                        "delivered while findings remain — either resolve "
                        "the open findings (set Findings to 0) OR move "
                        "Status to `partial` / `deferred-to-phase-3`."
                    ),
                )
            )

    # Duplicate findings (one per duplicate ID).
    for rid, count in seen_ids.items():
        if count > 1:
            findings.append(
                LintFinding(
                    rule="duplicate-requirement-row",
                    requirement_id=rid,
                    column=None,
                    diagnostic=(
                        f"{rid} appears {count} times in the coverage "
                        "matrix — each Phase 2 requirement must have "
                        "exactly one row per Story 23.1 AC-2."
                    ),
                )
            )

    # Missing rows: enumerated ID never appeared.
    for expected_id in PHASE_2_ROW_IDS:
        if expected_id not in seen_ids:
            findings.append(
                LintFinding(
                    rule="missing-requirement-row",
                    requirement_id=expected_id,
                    column=None,
                    diagnostic=(
                        f"{expected_id} is enumerated in the closed "
                        "Phase 2 row set but absent from the coverage "
                        "matrix — add a row OR remediate the gap per "
                        "AC-5's three-class triage (evidence-forward-"
                        "deferred / reduced-surface-shipped / "
                        "documentation-partial)."
                    ),
                )
            )

    total_rows = len(raw_rows)
    if total_rows != len(PHASE_2_ROW_IDS):
        findings.append(
            LintFinding(
                rule="row-count-mismatch",
                requirement_id=None,
                column=None,
                diagnostic=(
                    f"coverage matrix has {total_rows} data rows; "
                    f"expected {len(PHASE_2_ROW_IDS)} (the closed "
                    "Phase 2 row set per Story 23.1 AC-2)."
                ),
            )
        )

    findings_sorted = tuple(
        sorted(findings, key=lambda f: (f.rule, f.requirement_id or ""))
    )

    return CoverageReport(
        findings=findings_sorted,
        rows_observed=total_rows,
    )


# --------------------------------------------------------------------------- #
# Renderer (AC-4 + AC-8)                                                       #
# --------------------------------------------------------------------------- #


def render_report(report: CoverageReport) -> str:
    """Pure formatter — render a :class:`CoverageReport` for stdout.

    Mirrors :func:`phase_1_5_completion_evidence.render_report` shape:
    per-finding blocks plus a summary line. The summary line on the
    zero-findings case is:
        ``phase-2-completion-evidence: 0 findings (29 rows;
        4 status values)``
    per Story 23.1 AC-8 spirit.
    """
    lines: list[str] = []
    if not report.findings:
        lines.append(
            f"phase-2-completion-evidence: 0 findings "
            f"({report.rows_observed} rows; "
            f"{len(STATUS_VALUES)} status values)"
        )
        return "\n".join(lines)

    lines.append("Phase 2 completion evidence validator (story 23.1)")
    lines.append(f"  rows observed: {report.rows_observed}")
    lines.append("")
    for finding in report.findings:
        rid = finding.requirement_id or "—"
        col = finding.column or "—"
        lines.append(
            f"phase-2-completion-evidence: {finding.rule} | {rid} | "
            f"{col} | {finding.diagnostic}"
        )
        lines.append("")
    lines.append(
        f"phase-2-completion-evidence: {len(report.findings)} findings"
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI entry point (AC-4 + AC-8)                                                #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phase-2-completion-evidence",
        description=(
            "Phase 2 completion evidence validator (story 23.1; "
            "Phase-2-additive closing-artifact gate). Asserts "
            "docs/phase-2-completion-evidence.md has all 29 rows "
            "(the closed Phase 2 enumeration per epics-phase-2.md:999) "
            "populated with non-empty cells, valid Status values (the "
            "four-value vocabulary delivered|partial|not-shipped|"
            "deferred-to-phase-3), integer Findings, and the "
            "delivered-row open-findings integrity invariant per "
            "Story 23.1 AC-2. Sibling, not replacement of Story 8.7's "
            "mvp-completion-evidence + Story 11.1's "
            "phase-1-5-completion-evidence gates — all three run "
            "side-by-side."
        ),
    )
    parser.add_argument(
        "--artifact-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to docs/phase-2-completion-evidence.md. "
            "Default: <repo-root>/docs/phase-2-completion-evidence.md. "
            "Test-injection flag; CI invocations omit it."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to the inner repo root. Default: resolved "
            "via find_repo_root (.github ancestor walk). Test-injection "
            "flag; CI invocations omit it."
        ),
    )
    parser.add_argument(
        "--re-validate",
        action="store_true",
        help=(
            "Read-only validation alias for the default behavior. The "
            "validator is read-only by construction; this flag exists "
            "for parity with the artifact's `## Regeneration` section "
            "and has no behavioral effect."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point per Story 23.1 AC-4 + AC-8.

    Exit codes:
        * ``0`` — ``report.findings == ()`` (full pass).
        * ``1`` — any finding present (completeness gap).
        * ``2`` — substrate-level error (artifact missing, anchor
          markers missing, malformed row, repo-root unresolvable).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.repo_root is None:
        try:
            repo_root = find_repo_root()
        except (RuntimeError, OSError) as exc:
            print(
                f"phase-2-completion-evidence: substrate-level error: {exc}",
                file=sys.stderr,
            )
            return 2
    else:
        repo_root = args.repo_root

    artifact_path = args.artifact_path or (repo_root / ARTIFACT_RELATIVE_PATH)

    try:
        report = audit(artifact_path)
    except Phase2CompletionEvidenceError as exc:
        print(
            f"phase-2-completion-evidence: substrate-level error: {exc}",
            file=sys.stderr,
        )
        return 2

    print(render_report(report))
    return 1 if report.findings else 0
