"""MVP completion evidence validator (Story 8.7). FR1-FR66 + 34 NFRs + Pattern 5/6 + ADR-003 substrate-component-count posture.

Architectural placement (Story 8.7 Dev Notes "no new substrate components,
no new marker classes, no new external Python dependencies"): this module
is a CONSUMER LIBRARY parallel to Story 6.3's :mod:`marker_coverage_audit`,
Story 7.6's :mod:`init_non_destructive_guard`, Story 7.8's
:mod:`tea_boundary_orientation`, and Story 7.9's :mod:`onboarding_benchmark`.
It is NOT a sixth substrate component beyond ADR-003's enumerated five
(Architecture View 2 / ADR-003 Consequence 1 keeps the substrate-component
count at FIVE). The entry point is library-as-CLI-aid invoked from
:file:`bmad-autopilot/.github/workflows/ci.yml` per AC-8 — the Step 4
final-validation hook per :file:`epics.md:3444` that blocks Epic 8's
``done`` transition until MVP gaps are remediated.

What this validator asserts (per AC-2 + AC-5 verbatim):
    Walks the canonical MVP requirement enumeration (69 FR IDs +
    34 NFR IDs = 103 closed identifiers) against
    :file:`docs/mvp-completion-evidence.md`'s coverage matrix:
        (a) every FR/NFR ID has exactly one row;
        (b) every row's five columns are non-empty;
        (c) every row's ``Exercising Journey`` is one of the four
            closed journey values;
        (d) every row's ``Evidence Link`` resolves to a real path
            under the inner repo root OR is a syntactically-valid
            ``https://`` URL.

Loud-fail discipline (Pattern 5 — named invariants):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — full pass: ``report.findings == ()``; the artifact is
            complete and Epic 8 is releasable.
        1 — completeness gap: at least one finding present; PR is
            blocked until findings resolve. The dev triages each
            finding into one of three remediation classes per AC-5
            (missing implementation / missing test / missing evidence
            capture).
        2 — substrate-level error: artifact unreadable, anchor markers
            missing, or rows fail Pydantic validation — the validator
            cannot complete its audit. Distinct from exit 1 to surface
            broken-input vs. incomplete-coverage as separate
            diagnostics.

Sensor-not-advisor:
    The validator REPORTS findings; it does NOT auto-edit
    :file:`docs/mvp-completion-evidence.md`, suggest specific evidence
    paths, or rewrite cell contents. The dev interprets findings AND
    chooses remediation manually.

NOT a runtime marker emission surface:
    Per Story 1.11's atomic-vs-aggregated principle (markers signal
    atomic failure surfaces, NOT informational signals), this validator
    is release-time engineering observation. NO call to
    ``record_marker_with_context`` exists in this module; NO new
    entry in :file:`schemas/marker-taxonomy.yaml` is required; NO new
    row in :file:`_data/marker_coverage_surfaces.yaml` is required.

Cross-component reuse posture:
    * :func:`loud_fail_harness._shared.find_repo_root` — REUSED for
      default repo-root resolution.
    * NO other substrate-component imports — the validator is a pure
      markdown-parse + closed-enumeration audit.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections.abc import Sequence
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from loud_fail_harness._shared import find_repo_root

__all__ = [
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
]


# --------------------------------------------------------------------------- #
# Module-level constants (AC-1, AC-2, AC-4)                                    #
# --------------------------------------------------------------------------- #

#: The artifact path resolved relative to the inner repo root (mirrors
#: Story 6.3 / Story 7.9 published-evidence-doc precedent).
ARTIFACT_RELATIVE_PATH: Final[str] = "docs/mvp-completion-evidence.md"

#: Anchor markers delimiting the coverage-matrix rows (AC-1). The parser
#: extracts the markdown table between these markers; mirrors Story 7.9's
#: ``ROWS_BEGIN_ANCHOR`` / ``ROWS_END_ANCHOR`` discipline byte-for-byte.
ROWS_BEGIN_ANCHOR: Final[str] = "<!-- coverage-rows:begin -->"
ROWS_END_ANCHOR: Final[str] = "<!-- coverage-rows:end -->"

#: The closed 69-element MVP FR enumeration (AC-2). FR29 is OMITTED
#: per :file:`prd.md:849` (Phase-1.5 marking). Sub-letters (FR22b /
#: FR22c / FR24a / FR24b / FR48b) are independent rows, NOT compositions of
#: their parent FR. Tests assert this constant equals the FR IDs
#: parsed from :file:`prd.md` minus FR29.
MVP_FR_IDS: Final[tuple[str, ...]] = (
    "FR1", "FR2", "FR3", "FR4", "FR5", "FR6", "FR7", "FR8", "FR9", "FR10",
    "FR11", "FR12", "FR13", "FR14", "FR15", "FR16", "FR17", "FR18", "FR19", "FR20",
    "FR21", "FR22", "FR22b", "FR22c", "FR23", "FR24a", "FR24b", "FR25", "FR26", "FR27", "FR28",
    "FR30", "FR31", "FR32", "FR33", "FR34", "FR35", "FR36", "FR37", "FR38", "FR39",
    "FR40", "FR41", "FR42", "FR43", "FR44", "FR45", "FR46", "FR47", "FR48", "FR48b",
    "FR49", "FR50", "FR51", "FR52", "FR53", "FR54", "FR55", "FR56", "FR57", "FR58",
    "FR59", "FR60", "FR61", "FR62", "FR63", "FR64", "FR65", "FR66",
)

#: The closed 34-element NFR enumeration (AC-2). 6 perf + 8 reliability +
#: 6 interop + 6 security + 8 observability per :file:`prd.md:934-987`.
NFR_IDS: Final[tuple[str, ...]] = (
    "NFR-P1", "NFR-P2", "NFR-P3", "NFR-P4", "NFR-P5", "NFR-P6",
    "NFR-R1", "NFR-R2", "NFR-R3", "NFR-R4", "NFR-R5", "NFR-R6", "NFR-R7", "NFR-R8",
    "NFR-I1", "NFR-I2", "NFR-I3", "NFR-I4", "NFR-I5", "NFR-I6",
    "NFR-S1", "NFR-S2", "NFR-S3", "NFR-S4", "NFR-S5", "NFR-S6",
    "NFR-O1", "NFR-O2", "NFR-O3", "NFR-O4", "NFR-O5", "NFR-O6", "NFR-O7", "NFR-O8",
)

#: The closed four-element journey enumeration (AC-2 + AC-3). Any other
#: value in a row's ``Exercising Journey`` column triggers an
#: ``invalid-journey-value`` finding.
JOURNEY_VALUES: Final[tuple[str, ...]] = (
    "journey-1-happy-path",
    "journey-2-honest-failure",
    "journey-3-retry-firewall",
    "journey-4-bail-back",
)

#: Requirement-ID regex (AC-4). Matches ``FR<digits>[<lowercase-letter>]``
#: OR ``NFR-<single-uppercase-letter><digits>``.
_REQUIREMENT_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"^(FR\d+[a-z]?|NFR-[A-Z]\d+)$"
)

#: Syntactic-validity regex for ``https://`` archive URLs (AC-2 + AC-6).
#: The validator does NOT fetch URLs — fetching would couple CI to
#: network availability per AC-4.
_HTTPS_URL_RE: Final[re.Pattern[str]] = re.compile(r"^https://[^\s]+$")

#: Allowed lint-finding rule discriminators (AC-4).
_LINT_RULES: Final[tuple[str, ...]] = (
    "unknown-requirement-id",
    "missing-requirement-row",
    "duplicate-requirement-row",
    "empty-cell",
    "invalid-journey-value",
    "evidence-link-not-resolved",
    "row-count-mismatch",
    "anchor-markers-missing",
)

#: Canonical column names in left-to-right order (AC-1). Used by the
#: parser AND audit's empty-cell finding column attribution.
_COLUMN_NAMES: Final[tuple[str, ...]] = (
    "Requirement ID",
    "Requirement Summary",
    "Exercising Journey",
    "Observable Behavior Demonstrated",
    "Evidence Link",
)


# --------------------------------------------------------------------------- #
# Structured-error class (AC-4)                                                #
# --------------------------------------------------------------------------- #


class MvpCompletionEvidenceError(Exception):
    """Raised when the validator cannot honor its release-time contract.

    Pattern 5 — loud-fail / named invariants. The exception carries a
    structured ``reason`` discriminator naming the concrete failure
    mode so callers (the CI gate) can route to the correct surface OR
    HALT loudly rather than silently coercing to a sentinel.

    Mirrors the shape of
    :class:`loud_fail_harness.onboarding_benchmark.BenchmarkArtifactError`
    and :class:`loud_fail_harness.init_non_destructive_guard.GuardConfigCorrupted`.

    Attributes:
        reason: Short kebab-case discriminator. Documented values:
            ``"anchor-markers-missing"`` — anchor markers absent or
            out-of-order; ``"malformed-row"`` — a row failed Pydantic
            validation (cell missing, wrong column count, malformed
            requirement_id, invalid journey value); ``"artifact-not-found"``
            — the artifact path does not resolve to an existing file.
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
        message = f"MvpCompletionEvidenceError[{reason}]"
        if artifact_path is not None:
            message += f" artifact_path={artifact_path!s}"
        if diagnostic:
            message += f" {diagnostic}"
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Pydantic models (AC-4)                                                       #
# --------------------------------------------------------------------------- #


class CoverageRow(BaseModel):
    """One row of the coverage matrix (AC-2 + AC-4).

    Pattern 4 — frozen so a parsed row cannot be silently mutated
    between :func:`parse_coverage_matrix` and :func:`audit`. Field
    validators enforce non-empty strings + the requirement-ID regex.

    Attributes:
        requirement_id: One of the 103 IDs in :data:`MVP_FR_IDS` ∪
            :data:`NFR_IDS`. Field validator enforces the regex
            ``^(FR\\d+[a-z]?|NFR-[A-Z]\\d+)$``; cross-enumeration
            membership is checked by :func:`audit`.
        requirement_summary: One-line summary distilled from prd.md;
            min_length=1 (audit emits ``empty-cell`` for blanks).
        exercising_journey: Exactly one of the four closed journey
            values. Pydantic ``Literal`` enforces the closure;
            invalid values raise ``ValidationError`` (parser converts
            to ``malformed-row`` ``MvpCompletionEvidenceError``).
        observable_behavior: One-line description of the concrete
            behavior demonstrated; min_length=1.
        evidence_link: Relative path under the inner repo root OR
            ``https://`` archive URL; min_length=1. Path-resolution
            checked by :func:`audit` (emits ``evidence-link-not-resolved``).
    """

    model_config = ConfigDict(frozen=True)

    requirement_id: str = Field(..., min_length=1)
    requirement_summary: str = Field(..., min_length=1)
    exercising_journey: Literal[
        "journey-1-happy-path",
        "journey-2-honest-failure",
        "journey-3-retry-firewall",
        "journey-4-bail-back",
    ]
    observable_behavior: str = Field(..., min_length=1)
    evidence_link: str = Field(..., min_length=1)

    @field_validator("requirement_id")
    @classmethod
    def _requirement_id_pattern(cls, v: str) -> str:
        if not _REQUIREMENT_ID_RE.match(v):
            raise ValueError(
                f"requirement_id {v!r} does not match "
                "^(FR\\d+[a-z]?|NFR-[A-Z]\\d+)$"
            )
        return v


class LintFinding(BaseModel):
    """A single audit finding (AC-2 + AC-4).

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable rendering. Mirrors
    :class:`no_destructive_resume_lint.LintFinding`'s shape.

    Attributes:
        rule: One of the eight closed rule discriminators. Per AC-4:
            ``unknown-requirement-id``, ``missing-requirement-row``,
            ``duplicate-requirement-row``, ``empty-cell``,
            ``invalid-journey-value``, ``evidence-link-not-resolved``,
            ``row-count-mismatch``, ``anchor-markers-missing``.
        requirement_id: The offending requirement ID when applicable;
            ``None`` for whole-artifact rules
            (``row-count-mismatch`` / ``anchor-markers-missing``).
        column: The offending column name for ``empty-cell`` /
            ``invalid-journey-value`` / ``evidence-link-not-resolved``;
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
        "invalid-journey-value",
        "evidence-link-not-resolved",
        "row-count-mismatch",
        "anchor-markers-missing",
    ]
    requirement_id: str | None = None
    column: str | None = None
    diagnostic: str = Field(..., min_length=1, max_length=500)


class CoverageReport(BaseModel):
    """Aggregate audit result (AC-4).

    Frozen for hashability + determinism. Attributes:
        findings: All findings, ordered by ``(rule, requirement_id)``
            for byte-stable output.
        mvp_fr_count_observed: Count of FR-prefixed rows in the
            artifact; expected ``69``.
        nfr_count_observed: Count of NFR-prefixed rows; expected ``34``.
        total_rows_observed: Total rows in the coverage matrix;
            expected ``103``.
    """

    model_config = ConfigDict(frozen=True)

    findings: tuple[LintFinding, ...]
    mvp_fr_count_observed: int
    nfr_count_observed: int
    total_rows_observed: int


# --------------------------------------------------------------------------- #
# Markdown-table parser (AC-4)                                                 #
# --------------------------------------------------------------------------- #


def _read_artifact_text(artifact_path: pathlib.Path) -> str:
    """Read the artifact text or raise ``artifact-not-found``."""
    try:
        return artifact_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MvpCompletionEvidenceError(
            reason="artifact-not-found",
            artifact_path=artifact_path,
            diagnostic=(
                "MVP completion evidence artifact missing — author "
                "docs/mvp-completion-evidence.md per Story 8.7 AC-1, "
                "OR pass --artifact-path to override the default location."
            ),
        ) from exc
    except OSError as exc:
        raise MvpCompletionEvidenceError(
            reason="artifact-not-found",
            artifact_path=artifact_path,
            diagnostic=(
                f"MVP completion evidence artifact is not readable "
                f"({type(exc).__name__}: {exc}). Check file permissions."
            ),
        ) from exc
    except UnicodeDecodeError as exc:
        raise MvpCompletionEvidenceError(
            reason="artifact-not-found",
            artifact_path=artifact_path,
            diagnostic=(
                f"MVP completion evidence artifact contains invalid UTF-8 "
                f"at byte offset {exc.start}: {exc.reason}. "
                "The file may be corrupted or saved with a non-UTF-8 encoding."
            ),
        ) from exc


def _extract_anchor_block(
    text: str, artifact_path: pathlib.Path
) -> str:
    """Extract the substring between begin and end anchors.

    Raises ``anchor-markers-missing`` if either anchor is absent or
    the end anchor precedes the begin anchor.
    """
    begin_idx = text.find(ROWS_BEGIN_ANCHOR)
    end_idx = text.find(ROWS_END_ANCHOR)
    if begin_idx < 0 or end_idx < 0 or end_idx <= begin_idx:
        raise MvpCompletionEvidenceError(
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
    """Parse the coverage matrix between anchor markers (AC-4).

    Returns a tuple of :class:`CoverageRow` objects in artifact-row
    order. Strict — any row that fails Pydantic validation raises
    :class:`MvpCompletionEvidenceError` with ``reason="malformed-row"``.

    Raises:
        MvpCompletionEvidenceError: ``"artifact-not-found"`` if the
            artifact path does not resolve; ``"anchor-markers-missing"``
            if the anchor markers are absent or out-of-order;
            ``"malformed-row"`` if a row fails CoverageRow validation
            (empty cell, wrong column count, malformed requirement_id,
            invalid journey value).

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
            raise MvpCompletionEvidenceError(
                reason="malformed-row",
                artifact_path=artifact_path,
                diagnostic=(
                    f"row has {len(cells)} cells; expected {len(_COLUMN_NAMES)} "
                    f"({list(_COLUMN_NAMES)!r}). Offending row: {line.strip()!r}"
                ),
            )
        # Skip the header row (first cell == "Requirement ID").
        if cells[0] == _COLUMN_NAMES[0]:
            continue
        try:
            row = CoverageRow(
                requirement_id=cells[0],
                requirement_summary=cells[1],
                exercising_journey=cells[2],  # type: ignore[arg-type]
                observable_behavior=cells[3],
                evidence_link=cells[4],
            )
        except ValidationError as exc:
            raise MvpCompletionEvidenceError(
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
    fewer cells; truncated if more — :func:`audit` emits
    ``empty-cell`` for blanks regardless of source).

    Raises ``MvpCompletionEvidenceError`` only on artifact-not-found
    or anchor-markers-missing — :func:`audit` collects per-row issues
    as ``LintFinding`` objects instead of exceptions so the gate can
    surface ALL findings in one pass.
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
        # Pad short rows to exactly 5 cells (empty strings for missing columns).
        # Long rows (likely from unescaped '|' in cell content) are NOT truncated
        # here — audit() detects and reports wrong-cell-count rows explicitly.
        if len(cells) < expected:
            cells = cells + [""] * (expected - len(cells))
        rows.append(tuple(cells))
    return tuple(rows)


# --------------------------------------------------------------------------- #
# Audit (AC-4)                                                                 #
# --------------------------------------------------------------------------- #


def _resolve_evidence_link(
    link: str, repo_root: pathlib.Path
) -> bool:
    """Return ``True`` iff the link is syntactically valid AND resolves.

    Per AC-4: relative paths must resolve to existing files under
    ``repo_root``; ``https://`` URLs are accepted as syntactically
    valid (NOT fetched — fetching would couple CI to network
    availability).
    """
    if _HTTPS_URL_RE.match(link):
        return True
    candidate = (repo_root / link).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        return False
    return candidate.is_file()


def audit(
    artifact_path: pathlib.Path, repo_root: pathlib.Path
) -> CoverageReport:
    """Walk the coverage matrix and emit findings on any divergence (AC-4).

    Walks the four AC-2 invariants:
        (a) set-equality between (:data:`MVP_FR_IDS` ∪ :data:`NFR_IDS`)
            and the parsed-row IDs (emit ``missing-requirement-row``
            for any expected-but-absent ID; ``unknown-requirement-id``
            for any present-but-not-enumerated ID; ``duplicate-
            requirement-row`` for any ID appearing more than once);
        (b) per-row column-completeness (emit ``empty-cell`` for any
            of the 510 cells that is empty);
        (c) journey-value-closure (emit ``invalid-journey-value`` for
            any row whose ``Exercising Journey`` is not in
            :data:`JOURNEY_VALUES`);
        (d) evidence-link-resolution (emit ``evidence-link-not-resolved``
            for any relative path not resolving to an existing file
            under ``repo_root``);
        plus the row-count invariant (emit ``row-count-mismatch`` if
        ``total_rows_observed != 103``).

    Raises:
        MvpCompletionEvidenceError: only on ``"artifact-not-found"``
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
    valid_id_set: frozenset[str] = frozenset(MVP_FR_IDS) | frozenset(NFR_IDS)

    mvp_fr_count = 0
    nfr_count = 0

    for cells in raw_rows:
        # Rows with extra cells indicate an unescaped '|' in cell content.
        # _iter_raw_rows no longer truncates them — detect and report here.
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
                            "no-empty-evidence discipline per Story 8.7 "
                            "AC-5; populate the cell or remediate the gap "
                            "per AC-5's three-class triage (missing "
                            "implementation / missing test / missing "
                            "evidence capture)."
                        ),
                    )
                )
        # If the requirement_id is missing OR malformed, everything else
        # downstream cannot be cleanly attributed; record the unknown-id
        # finding and continue.
        if not requirement_id.strip():
            continue
        if not _REQUIREMENT_ID_RE.match(requirement_id):
            _id_display = repr(requirement_id[:60])
            findings.append(
                LintFinding(
                    rule="unknown-requirement-id",
                    requirement_id=requirement_id,
                    column=_COLUMN_NAMES[0],
                    diagnostic=(
                        f"requirement_id {_id_display} does not match "
                        "the canonical regex ^(FR\\d+[a-z]?|NFR-[A-Z]\\d+)$ "
                        "— typo or unrecognized requirement family."
                    )[:500],
                )
            )
            continue
        # Track FR vs NFR counts on syntactically-valid IDs.
        if requirement_id.startswith("FR"):
            mvp_fr_count += 1
        elif requirement_id.startswith("NFR-"):
            nfr_count += 1

        # Cross-enumeration membership.
        if requirement_id not in valid_id_set:
            findings.append(
                LintFinding(
                    rule="unknown-requirement-id",
                    requirement_id=requirement_id,
                    column=_COLUMN_NAMES[0],
                    diagnostic=(
                        f"{requirement_id} is not enumerated in MVP_FR_IDS "
                        "or NFR_IDS — typo or out-of-MVP requirement (FR29 "
                        "is Phase-1.5 and OMITTED per prd.md:849)."
                    ),
                )
            )

        # Duplicate-row detection.
        seen_ids[requirement_id] = seen_ids.get(requirement_id, 0) + 1

        # Journey-value-closure on the third column.
        journey_value = cells[2]
        if journey_value.strip() and journey_value not in JOURNEY_VALUES:
            findings.append(
                LintFinding(
                    rule="invalid-journey-value",
                    requirement_id=requirement_id,
                    column=_COLUMN_NAMES[2],
                    diagnostic=(
                        f"{requirement_id}: Exercising Journey "
                        f"{journey_value!r} is not in the closed set "
                        f"{list(JOURNEY_VALUES)!r}; typo or unrecognized "
                        "journey label."
                    ),
                )
            )

        # Evidence-link-resolution on the fifth column (only if non-empty).
        evidence_link = cells[4]
        if evidence_link.strip() and not _resolve_evidence_link(
            evidence_link, repo_root
        ):
            findings.append(
                LintFinding(
                    rule="evidence-link-not-resolved",
                    requirement_id=requirement_id,
                    column=_COLUMN_NAMES[4],
                    diagnostic=(
                        f"{requirement_id}: Evidence Link "
                        f"{evidence_link!r} does not resolve to an "
                        "existing file under the repo root AND is not a "
                        "syntactically-valid https:// URL."
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
                        "matrix — each requirement must have exactly one "
                        "row per Story 8.7 AC-2."
                    ),
                )
            )

    # Missing rows: enumerated ID never appeared.
    for expected_id in (*MVP_FR_IDS, *NFR_IDS):
        if expected_id not in seen_ids:
            findings.append(
                LintFinding(
                    rule="missing-requirement-row",
                    requirement_id=expected_id,
                    column=None,
                    diagnostic=(
                        f"{expected_id} is enumerated in the closed MVP "
                        "FR/NFR set but absent from the coverage matrix "
                        "— add a row OR remediate the implementation gap "
                        "per AC-5's three-class triage."
                    ),
                )
            )

    total_rows = len(raw_rows)
    if total_rows != len(MVP_FR_IDS) + len(NFR_IDS):
        findings.append(
            LintFinding(
                rule="row-count-mismatch",
                requirement_id=None,
                column=None,
                diagnostic=(
                    f"coverage matrix has {total_rows} data rows; "
                    f"expected {len(MVP_FR_IDS) + len(NFR_IDS)} "
                    f"({len(MVP_FR_IDS)} FR + {len(NFR_IDS)} NFR per "
                    "Story 8.7 AC-2)."
                ),
            )
        )

    findings_sorted = tuple(
        sorted(findings, key=lambda f: (f.rule, f.requirement_id or ""))
    )

    return CoverageReport(
        findings=findings_sorted,
        mvp_fr_count_observed=mvp_fr_count,
        nfr_count_observed=nfr_count,
        total_rows_observed=total_rows,
    )


# --------------------------------------------------------------------------- #
# Renderer (AC-4 + AC-8)                                                       #
# --------------------------------------------------------------------------- #


def render_report(report: CoverageReport) -> str:
    """Pure formatter — render a :class:`CoverageReport` for stdout.

    Mirrors :func:`pluggability_gate.format_findings` shape: per-finding
    blocks plus a summary line. The summary line on the zero-findings
    case is:
        ``mvp-completion-evidence: 0 findings (103 rows: 69 FR + 34 NFR;
        4 journeys)``
    per AC-8 verbatim.
    """
    lines: list[str] = []
    if not report.findings:
        lines.append(
            f"mvp-completion-evidence: 0 findings "
            f"({report.total_rows_observed} rows: "
            f"{report.mvp_fr_count_observed} FR + "
            f"{report.nfr_count_observed} NFR; "
            f"{len(JOURNEY_VALUES)} journeys)"
        )
        return "\n".join(lines)

    lines.append("MVP completion evidence validator (story 8.7)")
    lines.append(
        f"  rows observed: {report.total_rows_observed} "
        f"({report.mvp_fr_count_observed} FR + "
        f"{report.nfr_count_observed} NFR)"
    )
    lines.append("")
    for finding in report.findings:
        rid = finding.requirement_id or "—"
        col = finding.column or "—"
        lines.append(
            f"mvp-completion-evidence: {finding.rule} | {rid} | {col} | "
            f"{finding.diagnostic}"
        )
        lines.append("")
    lines.append(f"mvp-completion-evidence: {len(report.findings)} findings")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI entry point (AC-4 + AC-8)                                                #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mvp-completion-evidence",
        description=(
            "MVP completion evidence validator (story 8.7; final-MVP "
            "closing-artifact gate). Asserts docs/mvp-completion-evidence.md "
            "has all 103 rows (69 FR + 34 NFR) populated with non-empty "
            "cells, valid journey values, and resolving evidence links per "
            "epics.md:3410 + 3425-3428. Step 4 final-validation hook per "
            "epics.md:3444."
        ),
    )
    parser.add_argument(
        "--artifact-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to docs/mvp-completion-evidence.md. Default: "
            "<repo-root>/docs/mvp-completion-evidence.md. Test-injection "
            "flag; CI invocations omit it."
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
    """CLI entry point per AC-4 + AC-8.

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
                f"mvp-completion-evidence: substrate-level error: {exc}",
                file=sys.stderr,
            )
            return 2
    else:
        repo_root = args.repo_root

    artifact_path = args.artifact_path or (repo_root / ARTIFACT_RELATIVE_PATH)

    try:
        report = audit(artifact_path, repo_root)
    except MvpCompletionEvidenceError as exc:
        print(
            f"mvp-completion-evidence: substrate-level error: {exc}",
            file=sys.stderr,
        )
        return 2

    print(render_report(report))
    return 1 if report.findings else 0
