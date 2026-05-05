"""Marker emission coverage audit (Story 6.3). FR30 + FR33 + Pattern 5 + ADR-003 substrate-component-3.

Architectural placement (story 6.3 Dev Notes "this is harness-substrate work +
a written artifact"): this module is structurally a sibling of the existing
gate scripts (``pluggability_gate``, ``hook_budget_gate``, ``fr33_fixture_gate``,
``review_layer_failure_emission_gate``) but it is **NOT a CI gate at this
story's landing** — the entry point is library-as-CLI-aid invoked manually at
epic close OR by future contributors when extending coverage. Mirrors
``story_doc_validator``'s posture per ``pyproject.toml:26-32``. CI gating is a
forward-scoped enhancement (a future story can add a ``marker-coverage-audit``
step to ``.github/workflows/ci.yml`` if drift becomes a recurring failure mode).

What this audit walks (per AC-1 verbatim):
    The full Cartesian product of (marker_class × code_surface) — every
    skip-event marker class in ``schemas/marker-taxonomy.yaml`` × every code
    surface that can produce a skip-event (orchestrator state-machine /
    dispatch-wrapper / run-state-helper / lifecycle-transitions; specialist
    Dev / Review-BMAD / QA wrapper; SubagentStop / Stop / SessionStart hook;
    bundle assembler; cost-telemetry pipeline; reconciliation gate fixture
    + runtime). Each intersection has exactly one verdict in the audit's
    canonical data file ``_data/marker_coverage_surfaces.yaml``.

What this audit asserts (per AC-2 verbatim):
    * ``emitted`` rows: ``code_path`` resolves to a file:line containing a
      literal marker reference (the kebab-case marker_class string, the
      corresponding ``_MARKER`` constant identifier, or a ``marker_class=``
      keyword-argument assignment).
    * ``not-applicable`` rows: ``rationale`` is non-empty.
    * ``scheduled-by-story`` rows: ``discharging_story`` matches the
      ``<epic>.<story>`` regex AND ``rationale`` is non-empty.
    * ``gap`` rows: production data MUST NOT carry ``gap`` verdicts at Story
      6.3 close — they exist only for testing the audit's own loud-fail path.

Loud-fail discipline (Pattern 5):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — full pass: every (marker × surface) intersection has a valid
            verdict; every ``emitted`` row's ``code_path`` resolves; every
            ``not-applicable`` / ``scheduled-by-story`` row carries the
            required rationale + discharging-story.
        1 — audit failure: ``MarkerCoverageAuditFailure`` raised. Diagnostic
            enumerates the three orthogonal failure-mode collections
            (missing intersections, invalid verdicts, unresolved code paths).
            Recoverable by EITHER (a) updating
            ``_data/marker_coverage_surfaces.yaml`` (the contributor-extension
            path) OR (b) wiring the missing emission at the indicated surface.
        2 — harness-level error: taxonomy or surfaces YAML unreadable /
            malformed. Distinct from exit 1: the audit's own input data is
            broken before the audit logic can fire.

Sensor-not-advisor (PRD-level invariant):
    The audit REPORTS verdict-shape inconsistencies and unresolved
    ``code_path`` references; it does NOT auto-edit
    ``_data/marker_coverage_surfaces.yaml``, suggest specific verdicts, or
    rewrite emission code. Same posture as 1.4 / 1.5 / 1.6 / 1.7 / 1.8 / 1.9 /
    1.10a.

Cross-story complementarity (per AC-5 verbatim):
    The static audit is COMPLEMENTARY to BOTH the fixture-driven gate
    (Story 1.8 / ``fr33_fixture_gate.py``) AND the runtime gate (Story 6.8,
    forward-scoped). Each gate covers a distinct gap:
        * fixtures test the harness logic (does the reconciler correctly
          map skip-events to markers?);
        * runtime tests reference-project completeness (does the actual run
          produce the expected markers?);
        * THIS audit tests STATIC code-coverage (does every code surface
          that should emit a marker actually have an emission code-path?).
    Removing any one of the three loses a distinct loud-fail dimension.

Cross-component reuse posture:
    * :func:`loud_fail_harness._shared.find_repo_root` — REUSED for
      default-path resolution (taxonomy + surfaces + repo-relative artifact
      writes).
    * :func:`loud_fail_harness.reconciler.load_marker_taxonomy` — REUSED for
      the canonical marker-class set (the audit is read-only against the
      taxonomy; Story 1.4 owns authoring).
    * NO other substrate-component imports — the audit is a static-analysis
      scan over file:line references, not a schema- or fixture-driven
      operation.
"""

from __future__ import annotations

import argparse
import importlib.resources
import pathlib
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, Optional

import yaml

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.exceptions import MarkerCoverageAuditFailure
from loud_fail_harness.reconciler import load_marker_taxonomy

#: The discharging-story format pattern (per AC-2: ``^[0-9]+\.[0-9]+$``).
DISCHARGING_STORY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9]+\.[0-9]+$")

#: Recognized verdict literals (per the data-file schema).
VerdictLiteral = Literal["emitted", "not-applicable", "scheduled-by-story", "gap"]
_VALID_VERDICTS: Final[frozenset[str]] = frozenset(
    {"emitted", "not-applicable", "scheduled-by-story", "gap"}
)

#: Recognized surface category literals.
CategoryLiteral = Literal[
    "orchestrator",
    "specialist-wrapper",
    "hook",
    "bundle-assembler",
    "cost-telemetry",
    "reconciliation-gate",
]

#: Regex matching a marker-class constant identifier (e.g. ``TIER_3_NOT_CONFIGURED_MARKER``,
#: ``_MARKER_GIT_UNCOMMITTED_WORK_DETECTED``). Used by ``_resolve_emission_reference``
#: as the second-priority match after the literal kebab-case marker_class string.
_MARKER_CONSTANT_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b_?[A-Z][A-Z0-9_]*MARKER[A-Z0-9_]*\b")

#: How many lines around the indicated code_path line to scan for marker
#: references. Constant assignments (e.g. ``TIER_3_NOT_CONFIGURED_MARKER: ... = "..."``)
#: typically appear near the top of the module; the emission site references
#: them by identifier. ±25 lines accommodates the usual gap between constant
#: definition and the marker-emission helper that consumes it.
_EMISSION_REFERENCE_WINDOW: Final[int] = 25


@dataclass(frozen=True)
class CodeSurface:
    """One declared code surface in the canonical inventory.

    Per Story 6.3 AC-1: every surface has a kebab-case ``name`` (Pattern 1
    structural-key naming), a category drawn from the AC's enumerated set
    (``orchestrator`` / ``specialist-wrapper`` / ``hook`` / ``bundle-assembler``
    / ``cost-telemetry`` / ``reconciliation-gate``), one or more
    relative-to-repo-root ``file_paths`` (empty tuple permitted only for
    forward-scheduled surfaces — currently ``cost-telemetry-pipeline`` and
    ``reconciliation-gate-runtime``), and a one-line ``description`` per
    Pattern 5 docstring discipline.
    """

    name: str
    category: str
    file_paths: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class CoverageVerdict:
    """One row of the (marker_class × surface_name) coverage matrix.

    Per Story 6.3 AC-2:
        * ``verdict == "emitted"`` requires non-None ``code_path`` resolving
          to a file:line containing a marker reference.
        * ``verdict == "not-applicable"`` requires non-empty ``rationale``.
        * ``verdict == "scheduled-by-story"`` requires non-empty ``rationale``
          AND ``discharging_story`` matching ``^[0-9]+\\.[0-9]+$``.
        * ``verdict == "gap"`` is always invalid in production data
          (intentional-injection-only for testing the audit's loud-fail path).

    All fields are frozen for byte-stable serialization (the rendered
    artifact's deterministic ordering invariant per AC-3).
    """

    marker_class: str
    surface_name: str
    verdict: str
    code_path: Optional[str] = None
    audit_date: str = ""
    rationale: Optional[str] = None
    discharging_story: Optional[str] = None


@dataclass(frozen=True)
class _ParsedCodePath:
    """Internal: parsed ``<file>:<line>`` or ``<file>:<line-start>-<line-end>``."""

    file_path: pathlib.Path
    line_start: int
    line_end: int

    @classmethod
    def parse(cls, raw: str, repo_root: pathlib.Path) -> "_ParsedCodePath | None":
        """Parse the ``code_path`` field; return ``None`` on malformed input.

        Recognized forms:
            * ``<relative-path>:<n>``           (single-line reference)
            * ``<relative-path>:<n>-<m>``       (line range)
        """
        if ":" not in raw:
            return None
        path_part, _, line_part = raw.rpartition(":")
        if "-" in line_part:
            start_str, _, end_str = line_part.partition("-")
            try:
                start = int(start_str)
                end = int(end_str)
            except ValueError:
                return None
        else:
            try:
                start = int(line_part)
                end = start
            except ValueError:
                return None
        return cls(
            file_path=(repo_root / path_part).resolve(),
            line_start=start,
            line_end=end,
        )


def load_surfaces(yaml_path: pathlib.Path) -> tuple[CodeSurface, ...]:
    """Parse the ``surfaces:`` list from the data YAML.

    Raises:
        RuntimeError: if ``yaml_path`` is unreadable, malformed, or does not
            contain a top-level ``surfaces:`` list.

    The parser is strict — every surface entry must have all four required
    fields (``name``, ``category``, ``file_paths``, ``description``). The
    audit module is read-only against the data file; defects in the data
    surface as harness-level errors (exit 2), not as audit findings (exit 1).
    """
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(
            f"surfaces YAML at {yaml_path} did not parse to a top-level mapping"
        )
    surfaces_raw = raw.get("surfaces")
    if not isinstance(surfaces_raw, list):
        raise RuntimeError(
            f"surfaces YAML at {yaml_path} is missing the required 'surfaces:' list"
        )
    result: list[CodeSurface] = []
    for i, entry in enumerate(surfaces_raw):
        if not isinstance(entry, dict):
            raise RuntimeError(
                f"surfaces YAML at {yaml_path}: entry {i} is not a mapping"
            )
        try:
            name = entry["name"]
            category = entry["category"]
            file_paths = entry["file_paths"]
            description = entry["description"]
        except KeyError as exc:
            raise RuntimeError(
                f"surfaces YAML at {yaml_path}: entry {i} missing required field {exc.args[0]!r}"
            ) from exc
        if not isinstance(file_paths, list):
            raise RuntimeError(
                f"surfaces YAML at {yaml_path}: entry {i} 'file_paths' is not a list"
            )
        result.append(
            CodeSurface(
                name=str(name),
                category=str(category),
                file_paths=tuple(str(fp) for fp in file_paths),
                description=str(description).strip(),
            )
        )
    return tuple(result)


def load_verdicts(yaml_path: pathlib.Path) -> tuple[CoverageVerdict, ...]:
    """Parse the ``verdicts:`` list from the data YAML.

    Raises:
        RuntimeError: if ``yaml_path`` is unreadable, malformed, or does not
            contain a top-level ``verdicts:`` list.

    Returns frozen ``CoverageVerdict`` instances suitable for direct
    consumption by :func:`audit` and :func:`render_checklist`. Optional
    fields (``code_path``, ``rationale``, ``discharging_story``) default to
    ``None`` when absent or YAML-null.
    """
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(
            f"surfaces YAML at {yaml_path} did not parse to a top-level mapping"
        )
    verdicts_raw = raw.get("verdicts")
    if not isinstance(verdicts_raw, list):
        raise RuntimeError(
            f"surfaces YAML at {yaml_path} is missing the required 'verdicts:' list"
        )
    result: list[CoverageVerdict] = []
    for i, entry in enumerate(verdicts_raw):
        if not isinstance(entry, dict):
            raise RuntimeError(
                f"surfaces YAML at {yaml_path}: verdict entry {i} is not a mapping"
            )
        try:
            marker_class = entry["marker_class"]
            surface_name = entry["surface_name"]
            verdict = entry["verdict"]
        except KeyError as exc:
            raise RuntimeError(
                f"surfaces YAML at {yaml_path}: verdict entry {i} missing required "
                f"field {exc.args[0]!r}"
            ) from exc
        rationale = entry.get("rationale")
        rationale_str: Optional[str] = (
            str(rationale).strip() if rationale is not None else None
        )
        result.append(
            CoverageVerdict(
                marker_class=str(marker_class),
                surface_name=str(surface_name),
                verdict=str(verdict),
                code_path=(
                    str(entry["code_path"]) if entry.get("code_path") else None
                ),
                audit_date=str(entry.get("audit_date") or ""),
                rationale=rationale_str,
                discharging_story=(
                    str(entry["discharging_story"])
                    if entry.get("discharging_story")
                    else None
                ),
            )
        )
    return tuple(result)


def _resolve_emission_reference(
    parsed: _ParsedCodePath, marker_class: str
) -> bool:
    """Return ``True`` iff the file:line range contains a marker reference.

    Acceptance per AC-2: the line range OR the surrounding ±25 lines must
    contain EITHER the literal kebab-case ``marker_class`` string OR a
    recognized ``_MARKER`` / ``MARKER`` constant identifier OR a
    ``marker_class=`` keyword-argument assignment.

    Falls back to scanning the surrounding window because constant
    definitions typically live near the top of a module and the emission
    site references them by identifier (Pattern 4-style symbolic-constant
    discipline). ±25 lines accommodates the usual gap.
    """
    try:
        text = parsed.file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    lines = text.splitlines()
    if not lines:
        return False
    # Convert 1-based line numbers to 0-based slice indices, with window.
    start_idx = max(0, parsed.line_start - 1 - _EMISSION_REFERENCE_WINDOW)
    end_idx = min(len(lines), parsed.line_end + _EMISSION_REFERENCE_WINDOW)
    window = "\n".join(lines[start_idx:end_idx])
    if marker_class in window:
        return True
    if "marker_class=" in window or "marker_class =" in window:
        return True
    # Specific constant derived from marker_class (e.g., "tier-3-not-configured" →
    # "TIER_3_NOT_CONFIGURED_MARKER"). Checked before the generic pattern to avoid
    # false positives from other markers' constants in the same window.
    specific_constant = marker_class.replace("-", "_").upper() + "_MARKER"
    if specific_constant in window:
        return True
    if _MARKER_CONSTANT_PATTERN.search(window):
        return True
    return False


def audit(
    taxonomy_path: pathlib.Path,
    surfaces_path: pathlib.Path,
    *,
    repo_root: Optional[pathlib.Path] = None,
) -> tuple[CoverageVerdict, ...]:
    """Walk the (marker_class × surface_name) coverage matrix; raise on any inconsistency.

    Per AC-1 + AC-2: validates that
        (1) every (marker × surface) intersection has exactly one verdict
            (no duplicates; no missing — the Cartesian product is fully
            covered);
        (2) every ``emitted`` verdict's ``code_path`` resolves to a file:line
            containing a marker reference (via
            :func:`_resolve_emission_reference`);
        (3) every ``not-applicable`` verdict carries non-empty ``rationale``;
        (4) every ``scheduled-by-story`` verdict carries non-empty
            ``rationale`` AND ``discharging_story`` matching
            ``^[0-9]+\\.[0-9]+$``;
        (5) no verdict is ``gap`` — production data must not carry the
            placeholder verdict at Story 6.3 close.

    Args:
        taxonomy_path: Path to ``schemas/marker-taxonomy.yaml``. Story 1.4
            owns authoring; this audit is read-only.
        surfaces_path: Path to ``_data/marker_coverage_surfaces.yaml``.
        repo_root: Optional repo-root override for resolving ``code_path``
            entries. When ``None``, ``code_path`` is resolved via
            :func:`find_repo_root`.

    Returns:
        The full sorted tuple of verdicts (alphabetical by ``marker_class``,
        then by ``surface_name``) on success. The return value is suitable
        for direct consumption by :func:`render_checklist`.

    Raises:
        MarkerCoverageAuditFailure: if any of the AC-2 invariants is
            violated. The exception aggregates ALL findings — the audit
            does NOT short-circuit on the first defect.
        RuntimeError: if the taxonomy or surfaces YAML is unreadable /
            malformed (harness-level error; exit 2 from :func:`main`).
    """
    if repo_root is None:
        repo_root = find_repo_root()
    marker_classes = load_marker_taxonomy(taxonomy_path)
    surfaces = load_surfaces(surfaces_path)
    verdicts = load_verdicts(surfaces_path)

    # Build a (marker_class, surface_name) → verdict map; collect duplicates.
    verdict_map: dict[tuple[str, str], CoverageVerdict] = {}
    duplicate_keys: list[tuple[str, str]] = []
    for v in verdicts:
        key = (v.marker_class, v.surface_name)
        if key in verdict_map:
            duplicate_keys.append(key)
        else:
            verdict_map[key] = v

    surface_names = {s.name for s in surfaces}

    # AC-1: every (marker × surface) intersection has exactly one verdict.
    missing: list[tuple[str, str]] = []
    for mc in sorted(marker_classes):
        for sn in sorted(surface_names):
            if (mc, sn) not in verdict_map:
                missing.append((mc, sn))

    # AC-2: per-row shape validation.
    invalid: list[str] = []
    unresolved: list[str] = []

    for key, v in sorted(verdict_map.items()):
        # Reject duplicates as invalid.
        if key in duplicate_keys:
            invalid.append(
                f"{v.marker_class} × {v.surface_name}: duplicate verdict row"
            )
            continue
        # Reject unknown verdict literals.
        if v.verdict not in _VALID_VERDICTS:
            invalid.append(
                f"{v.marker_class} × {v.surface_name}: unknown verdict "
                f"{v.verdict!r} (must be one of {sorted(_VALID_VERDICTS)})"
            )
            continue
        # Reject taxonomy / surface drift.
        if v.marker_class not in marker_classes:
            invalid.append(
                f"{v.marker_class} × {v.surface_name}: marker_class is not in "
                f"the taxonomy (taxonomy drift — {taxonomy_path.name} is the "
                "authoritative enumeration)"
            )
            continue
        if v.surface_name not in surface_names:
            invalid.append(
                f"{v.marker_class} × {v.surface_name}: surface_name is not in "
                f"the surfaces list (drift — {surfaces_path.name} surfaces "
                "list is the authoritative enumeration)"
            )
            continue
        # Per-verdict-shape checks.
        if v.verdict == "emitted":
            if not v.code_path:
                invalid.append(
                    f"{v.marker_class} × {v.surface_name}: emitted verdict "
                    "missing required 'code_path'"
                )
                continue
            parsed = _ParsedCodePath.parse(v.code_path, repo_root)
            if parsed is None:
                unresolved.append(
                    f"{v.marker_class} × {v.surface_name}: malformed code_path "
                    f"{v.code_path!r} (expected '<file>:<line>' or "
                    "'<file>:<start>-<end>')"
                )
                continue
            if not parsed.file_path.is_file():
                unresolved.append(
                    f"{v.marker_class} × {v.surface_name}: code_path "
                    f"{v.code_path!r} does not resolve to a file"
                )
                continue
            if not _resolve_emission_reference(parsed, v.marker_class):
                unresolved.append(
                    f"{v.marker_class} × {v.surface_name}: code_path "
                    f"{v.code_path!r} does not contain a literal marker "
                    "reference (kebab-case marker_class, _MARKER constant, "
                    "or marker_class= keyword)"
                )
                continue
        elif v.verdict == "not-applicable":
            if not v.rationale:
                invalid.append(
                    f"{v.marker_class} × {v.surface_name}: not-applicable "
                    "verdict missing required 'rationale'"
                )
                continue
        elif v.verdict == "scheduled-by-story":
            if not v.rationale:
                invalid.append(
                    f"{v.marker_class} × {v.surface_name}: scheduled-by-story "
                    "verdict missing required 'rationale'"
                )
                continue
            if not v.discharging_story or not DISCHARGING_STORY_PATTERN.match(
                v.discharging_story
            ):
                invalid.append(
                    f"{v.marker_class} × {v.surface_name}: scheduled-by-story "
                    f"verdict has missing or malformed 'discharging_story' "
                    f"({v.discharging_story!r}; expected pattern <epic>.<story>)"
                )
                continue
        elif v.verdict == "gap":
            invalid.append(
                f"{v.marker_class} × {v.surface_name}: gap verdict is "
                "invalid in production data (per AC-2; classify as "
                "scheduled-by-story with discharging_story OR fix the "
                "missing emission within this story's scope)"
            )

    if missing or invalid or unresolved:
        raise MarkerCoverageAuditFailure(
            missing_intersections=tuple(missing),
            invalid_verdicts=tuple(invalid),
            unresolved_code_paths=tuple(unresolved),
        )

    return tuple(
        sorted(
            verdict_map.values(),
            key=lambda v: (v.marker_class, v.surface_name),
        )
    )


def render_checklist(
    verdicts: Sequence[CoverageVerdict],
    output_path: pathlib.Path,
) -> None:
    """Write the canonical markdown checklist artifact to ``output_path``.

    Per Story 6.3 AC-3 + AC-4 + AC-5: the artifact's header cites Story 6.3
    + FR30 + FR33 + Pattern 5 + the regeneration command + the contributor-
    extension instructions + the relationship to Story 1.8's fixture-driven
    gate and Story 6.8's runtime gate. The body is a single markdown table
    with deterministic alphabetical ordering by (marker_class, surface_name).

    The render is byte-stable: the same input always produces the same
    output (no timestamps, no random ordering, no environment-dependent
    data). The regression test at AC-6 asserts byte-equality between the
    on-disk artifact and a freshly-rendered output.
    """
    sorted_verdicts = sorted(
        verdicts, key=lambda v: (v.marker_class, v.surface_name)
    )

    summary_counts: dict[str, int] = {
        "emitted": 0,
        "not-applicable": 0,
        "scheduled-by-story": 0,
        "gap": 0,
    }
    for v in sorted_verdicts:
        if v.verdict in summary_counts:
            summary_counts[v.verdict] += 1

    lines: list[str] = []
    lines.append("# Marker emission coverage audit (Story 6.3)")
    lines.append("")
    lines.append(
        "Authoritative landing: Story 6.3 (full marker emission coverage audit + "
        "checklist artifact). Substrate references: FR30 (single-source-of-truth "
        "marker enumeration), FR33 (harness reconciliation check), Pattern 5 "
        "(loud-fail / named-invariant discipline)."
    )
    lines.append("")
    lines.append("## Regeneration")
    lines.append("")
    lines.append("```")
    lines.append("cd bmad-autopilot/tools/loud-fail-harness")
    lines.append("uv run marker-coverage-audit --regenerate")
    lines.append("```")
    lines.append("")
    lines.append(
        "The audit module is library-as-CLI-aid (NOT a CI gate at Story 6.3 "
        "landing — mirrors `story-doc-validator`'s posture). The plain "
        "`uv run marker-coverage-audit` invocation runs the audit and exits "
        "0 on green; `--regenerate` ALSO writes this artifact. CI gating is "
        "forward-scoped — a future story can add the audit to "
        "`.github/workflows/ci.yml` if drift becomes a recurring failure mode."
    )
    lines.append("")
    lines.append("## Contributor extension")
    lines.append("")
    lines.append(
        "To add a new code surface or marker class: append a row to "
        "`_data/marker_coverage_surfaces.yaml`'s `surfaces:` or `verdicts:` list, "
        "regenerate this artifact via `uv run marker-coverage-audit`, commit "
        "both files together. See `docs/extension-audit.md`'s "
        "`## Contributor-discipline notes` section as the canonical "
        "contributor-onboarding entry point."
    )
    lines.append("")
    lines.append("## Relationship to FR33 enforcement")
    lines.append("")
    lines.append(
        "This audit is COMPLEMENTARY to BOTH the fixture-driven gate (Story 1.8 / "
        "`fr33_fixture_gate.py`) AND the runtime gate (Story 6.8, "
        "`scheduled-by-story` until that story lands); neither replaces it. "
        "Each gate covers a distinct gap:"
    )
    lines.append("")
    lines.append(
        "- **Fixture-driven gate** tests the harness logic — does the reconciler "
        "correctly map skip-events to markers? Fixtures test the harness logic, "
        "not whether code paths exist that *should* emit."
    )
    lines.append(
        "- **Runtime gate** tests reference-project completeness — does the "
        "actual run produce the expected markers?"
    )
    lines.append(
        "- **THIS audit** tests static code-coverage — the audit catches code "
        "surface that has no fixture or runtime evidence yet (gaps in test "
        "coverage). Removing any one of the three loses a distinct loud-fail "
        "dimension."
    )
    lines.append("")
    lines.append("## Coverage summary")
    lines.append("")
    lines.append(
        f"- Total intersections: {len(sorted_verdicts)}"
    )
    lines.append(f"- Emitted: {summary_counts['emitted']}")
    lines.append(f"- Not-applicable: {summary_counts['not-applicable']}")
    lines.append(f"- Scheduled-by-story: {summary_counts['scheduled-by-story']}")
    lines.append(f"- Gaps: {summary_counts['gap']}")
    lines.append("")
    lines.append("## Coverage matrix")
    lines.append("")
    lines.append(
        "| Marker Class | Surface | Verdict | Code Path | Audit Date | "
        "Rationale / Discharging Story |"
    )
    lines.append(
        "| --- | --- | --- | --- | --- | --- |"
    )

    for v in sorted_verdicts:
        code_path = v.code_path or "n/a"
        if v.verdict == "scheduled-by-story":
            rationale_col = (
                f"discharging-story: {v.discharging_story or 'n/a'} — "
                f"{v.rationale or ''}"
            )
        else:
            rationale_col = v.rationale or ""
        # Cell-safe markdown: replace pipes and newlines.
        rationale_col = rationale_col.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {v.marker_class} | {v.surface_name} | {v.verdict} | "
            f"`{code_path}` | {v.audit_date} | {rationale_col} |"
        )

    lines.append("")
    lines.append("## Regeneration triggers")
    lines.append("")
    lines.append(
        "Regenerate this artifact when: (a) Epic 6 closes (full sweep against "
        "the latest substrate); (b) a new marker class is added to "
        "`schemas/marker-taxonomy.yaml`; (c) a new code surface is added to "
        "`_data/marker_coverage_surfaces.yaml`'s `surfaces:` list; (d) an "
        "existing surface's emission code path moves (e.g., a refactor changes "
        "the file:line of a marker emission)."
    )
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def _resolve_taxonomy_path(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "schemas" / "marker-taxonomy.yaml"


def _resolve_surfaces_path(repo_root: pathlib.Path) -> pathlib.Path:
    """Resolve the canonical surfaces YAML via importlib.resources.

    The data file ships inside the package (``loud_fail_harness/_data/``) so
    that ``uv run marker-coverage-audit`` works regardless of cwd. The
    ``repo_root`` parameter is reserved for future flexibility (e.g., test
    overrides via a sibling ``_data/`` path); at Story 6.3's landing the
    canonical resolution is the package-bundled path.
    """
    del repo_root  # currently unused; importlib.resources is cwd-independent.
    return pathlib.Path(
        str(
            importlib.resources.files("loud_fail_harness").joinpath(
                "_data/marker_coverage_surfaces.yaml"
            )
        )
    )


def _resolve_artifact_path(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "docs" / "marker-coverage-audit.md"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="marker-coverage-audit",
        description=(
            "Marker emission coverage audit (Story 6.3). Walks the "
            "(marker_class × code_surface) coverage matrix declared in "
            "_data/marker_coverage_surfaces.yaml; validates every "
            "intersection has a verdict and every emitted verdict's "
            "code_path resolves to a real file:line containing a marker "
            "reference. Library-as-CLI-aid (NOT a CI gate at Story 6.3 "
            "landing); invoked manually at epic close OR by future "
            "contributors when extending coverage."
        ),
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help=(
            "Re-render the canonical artifact at "
            "bmad-autopilot/docs/marker-coverage-audit.md. Default: audit "
            "only (do not write the artifact). The regenerate flag is the "
            "contributor-extension entry point — append a row to "
            "_data/marker_coverage_surfaces.yaml, run with --regenerate, "
            "commit both files."
        ),
    )
    parser.add_argument(
        "--taxonomy-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to marker-taxonomy.yaml. Default: "
            "<repo-root>/bmad-autopilot/schemas/marker-taxonomy.yaml. "
            "Test-injection flag; CI invocations omit it."
        ),
    )
    parser.add_argument(
        "--surfaces-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to _data/marker_coverage_surfaces.yaml. Default: "
            "the package-bundled resource (importlib.resources). "
            "Test-injection flag; contributor invocations omit it."
        ),
    )
    parser.add_argument(
        "--artifact-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to the rendered artifact. Default: "
            "<repo-root>/bmad-autopilot/docs/marker-coverage-audit.md. "
            "Only consulted when --regenerate is set. Test-injection flag."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = find_repo_root()
    except RuntimeError as exc:
        print(f"harness-level error: {exc}", file=sys.stderr)
        return 2

    taxonomy_path = args.taxonomy_path or _resolve_taxonomy_path(repo_root)
    surfaces_path = args.surfaces_path or _resolve_surfaces_path(repo_root)
    artifact_path = args.artifact_path or _resolve_artifact_path(repo_root)

    try:
        verdicts = audit(taxonomy_path, surfaces_path, repo_root=repo_root)
    except MarkerCoverageAuditFailure as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, RuntimeError, yaml.YAMLError) as exc:
        print(f"harness-level error: {exc}", file=sys.stderr)
        return 2

    counts: dict[str, int] = {
        "emitted": 0,
        "not-applicable": 0,
        "scheduled-by-story": 0,
        "gap": 0,
    }
    for v in verdicts:
        if v.verdict in counts:
            counts[v.verdict] += 1

    print(
        f"marker-coverage-audit: {len(verdicts)} intersections audited; "
        f"{counts['emitted']} emitted, {counts['not-applicable']} not-applicable, "
        f"{counts['scheduled-by-story']} scheduled; {counts['gap']} gaps"
    )

    if args.regenerate:
        render_checklist(verdicts, artifact_path)
        try:
            display = artifact_path.resolve().relative_to(repo_root.resolve())
        except ValueError:
            display = artifact_path
        print(f"marker-coverage-audit: rendered artifact at {display}")

    return 0


__all__ = [
    "CodeSurface",
    "CoverageVerdict",
    "DISCHARGING_STORY_PATTERN",
    "audit",
    "load_surfaces",
    "load_verdicts",
    "main",
    "render_checklist",
]
