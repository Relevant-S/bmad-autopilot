"""Review-layer-failure single-emission-path CI gate (Story 3.3 AC-9).

Architectural placement (story 1.10a's ``pluggability_gate.py`` precedent):
this module is structurally a sibling of the prior CI gates
(``fr33_fixture_gate``, ``hook_budget_gate``, ``pluggability_gate``) but
it is **NOT a sixth substrate component**. ADR-003 Consequence 1
enumerates exactly five substrate components (architecture.md lines
311-315); this gate is a CI **gate** that enforces Story 3.3's
three-channel atomic-emission code-structure invariant.

What this gate enforces (Story 3.3 AC-1 + AC-9):
    * `surface_failed_layers` at
      :mod:`loud_fail_harness.review_layer_failure` is the SINGLE
      source-of-truth emission path for the three-channel projection of
      a per-layer review failure (FR28 + FR56). The atomicity is enforced
      as a code-structure invariant, NOT a per-bundle reconciliation
      gate. This is the SAME pattern Story 2.2 applied to atomic-write:
      the API shape IS the invariant.

Forbidden patterns (any of the three triggers a lint violation):
    (a) **Direct write to ``failed_layers``** outside the canonical
        emission site. Regex matches assignment forms:
        ``envelope["failed_layers"] =``,
        ``envelope['failed_layers'] =``,
        ``.failed_layers =``.
        Does NOT match bare local-variable assignment
        (``failed_layers = envelope.get(...)`` reads the field into a
        local var — not a mutation of an envelope field).
    (b) **Quoted string literal of the ``review-layer-failed`` marker
        class** outside the canonical emission site. Regex matches
        ``"review-layer-failed"`` or ``'review-layer-failed'``. Files
        that import :data:`REVIEW_LAYER_FAILED_MARKER` symbolically
        from :mod:`loud_fail_harness.review_layer_failure` are NOT
        flagged because the symbol name is not the literal string.
    (c) **Append of a finding carrying ``meta: review-completeness``**
        outside the canonical emission site. Regex matches the
        ``review-completeness`` literal anywhere in the file (the
        narrow enum value is itself the discriminator; any
        non-canonical occurrence is a violation by construction).

Scan scope (per AC-9 verbatim):
    * **Harness source tree** — every ``.py`` file under
      ``tools/loud-fail-harness/src/loud_fail_harness/``. Test files
      under ``tests/`` are NOT in the scan scope (tests construct
      synthesized envelopes + fabricate forbidden patterns to exercise
      the gate; including them would invert the gate's meaning).
    * **Agent definition** — ``agents/review-bmad-wrapper.md``. The
      wrapper IS the named-contract documentation for the three-channel
      surface (Story 3.3 AC-3); the file is read AS DATA by the
      dispatch substrate, never imported as code (FR62 + ADR-004). The
      wrapper is in the scan scope so any direct emission paths in
      its prose are caught, but the wrapper file is in the
      ``_ALLOWLIST_FILES`` because its prose documents the canonical
      identifiers (the `meta: review-completeness` discriminator name
      itself, the marker class identifier, etc.) — without naming them
      the contract is undocumented.

Allowlist (canonical emission sites; exempt from the lint scope):
    * ``tools/loud-fail-harness/src/loud_fail_harness/review_layer_failure.py``
      — the canonical emission home (defines `surface_failed_layers`
      + the marker class constant + the synthetic-finding builder).
    * ``tools/loud-fail-harness/src/loud_fail_harness/review_layer_failure_emission_gate.py``
      — THIS gate file (defines the regex patterns being scanned for;
      naming the patterns is what the gate does).
    * ``agents/review-bmad-wrapper.md`` — the named-contract
      documentation; the wrapper is data, not code; its prose
      documents the three-channel contract via the canonical
      identifiers.

Files NOT in the scan scope (out of scope by construction):
    * ``schemas/marker-taxonomy.yaml`` — defines the
      `review-layer-failed` marker class; out of scope.
    * ``examples/envelopes/*.yaml`` — fixtures carrying synthetic
      meta-findings; out of scope.
    * ``tools/loud-fail-harness/tests/*.py`` — tests fabricate
      forbidden patterns to exercise this gate; out of scope.
    * ``docs/*.md`` — extension-audit, architecture; documentation;
      out of scope.

Loud-fail discipline (Pattern 5):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — full pass: zero violations across the scan scope.
        1 — invariant violation: at least one forbidden pattern
            detected outside the allowlist. The fix is to route the
            offending emission through `surface_failed_layers` (the
            single source-of-truth function), then re-run the gate.
        2 — harness-level error: scan-scope file unreadable or
            non-UTF-8.

Sensor-not-advisor: the gate REPORTS per-file violations with
remediation pointers; it does NOT auto-edit source files.

Cross-references:
    * Story 1.10a ``pluggability_gate.py`` — the regex-rule precedent
      THIS gate mirrors.
    * Story 2.2 ``run_state.py`` `RunStateAtomicWriter.write` — the
      API-shape-enforced-invariant precedent.
    * Story 3.3 :mod:`loud_fail_harness.review_layer_failure` — the
      single source-of-truth function this gate enforces.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from loud_fail_harness._shared import find_repo_root


#: Per-file-relative paths that are exempt from the forbidden-pattern
#: scan. Stored as POSIX-style relative paths from the inner repo root
#: for stable cross-platform comparison.
_ALLOWLIST_FILES: frozenset[str] = frozenset(
    {
        "tools/loud-fail-harness/src/loud_fail_harness/review_layer_failure.py",
        "tools/loud-fail-harness/src/loud_fail_harness/review_layer_failure_emission_gate.py",
        "agents/review-bmad-wrapper.md",
    }
)


#: Rule (a) — direct write TO an envelope's ``failed_layers`` field.
#: Catches subscript assignment (``envelope["failed_layers"] =``) and
#: attribute assignment (``.failed_layers =``). Does NOT match
#: dict-literal initialization (``"failed_layers": []`` is a key:value
#: pair, not an assignment) and does NOT match bare local-variable
#: read-assignment (``failed_layers = envelope.get(...)`` is a read
#: from the envelope into a local var, not a write to the envelope).
#: The narrow form is what enforces the AC-9 invariant: only
#: surface_failed_layers is permitted to MUTATE the envelope's
#: failed_layers field; reading it into a local variable for
#: rendering is a non-mutation and is allowed.
_PATTERN_FAILED_LAYERS_WRITE: re.Pattern[str] = re.compile(
    r"""(?x)
    (?:
      \[\s*["']failed_layers["']\s*\]\s*=     # subscript: ["failed_layers"] =
    | \.failed_layers\s*=                     # attribute: .failed_layers =
    )
    """
)

#: Rule (b) — quoted string literal of the ``review-layer-failed`` marker
#: class. Catches ``"review-layer-failed"`` and ``'review-layer-failed'``.
#: Importing the symbolic constant
#: :data:`loud_fail_harness.review_layer_failure.REVIEW_LAYER_FAILED_MARKER`
#: is NOT flagged because the symbol name is not the literal string.
_PATTERN_MARKER_LITERAL: re.Pattern[str] = re.compile(
    r"""["']review-layer-failed["']"""
)

#: Rule (c) — the ``review-completeness`` discriminator literal. Any
#: non-canonical occurrence is a violation by construction since the
#: enum is single-valued at this story's scope.
_PATTERN_META_REVIEW_COMPLETENESS: re.Pattern[str] = re.compile(
    r"\breview-completeness\b"
)


class ForbiddenEmissionFinding(BaseModel):
    """A Story 3.3 forbidden-emission violation finding.

    One :class:`ForbiddenEmissionFinding` per detected forbidden
    pattern; multiple findings per offending file are emitted (no
    bail-after-first per the loud-fail-doctrine pattern). Sorted by
    ``(file_path, line_number, rule)`` at the gate level.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str
    line_number: int
    rule: Literal["failed-layers-write", "marker-literal", "meta-discriminator"]
    matched_text: str


class GateResult(BaseModel):
    """Two-bucket forbidden-emission gate output.

    * ``scanned_files`` — the relative paths the gate scanned.
    * ``forbidden_emission_violation`` — one
      :class:`ForbiddenEmissionFinding` per detected forbidden pattern;
      empty when the source tree is clean.
    """

    model_config = ConfigDict(frozen=True)

    scanned_files: list[str]
    forbidden_emission_violation: list[ForbiddenEmissionFinding]


_REMEDIATION: str = (
    "(per FR28 + FR56 + Story 3.3 AC-1 three-channel atomicity invariant: "
    "the failed_layers envelope field, the review-layer-failed marker "
    "emission, and the synthetic meta-finding append are atomic — emit "
    "them through surface_failed_layers (the single source-of-truth "
    "function at tools/loud-fail-harness/src/loud_fail_harness/"
    "review_layer_failure.py) so all three projections agree by "
    "construction. Remediation: (a) route the offending emission "
    "through surface_failed_layers, OR (b) if the call site is bundle "
    "rendering, import REVIEW_LAYER_FAILED_MARKER from "
    "loud_fail_harness.review_layer_failure and use the symbolic "
    "constant rather than the string literal — symbol references are "
    "exempt from the lint by construction.)"
)


def _line_number_for_match_start(file_text: str, match_start: int) -> int:
    """Return the 1-indexed line number containing offset ``match_start``."""
    return file_text[:match_start].count("\n") + 1


def _scan_file_for_violations(
    relative_path: str, file_text: str
) -> list[ForbiddenEmissionFinding]:
    """Apply the three rules to ``file_text`` and emit findings."""
    findings: list[ForbiddenEmissionFinding] = []
    for match in _PATTERN_FAILED_LAYERS_WRITE.finditer(file_text):
        findings.append(
            ForbiddenEmissionFinding(
                file_path=relative_path,
                line_number=_line_number_for_match_start(file_text, match.start()),
                rule="failed-layers-write",
                matched_text=match.group(0),
            )
        )
    for match in _PATTERN_MARKER_LITERAL.finditer(file_text):
        findings.append(
            ForbiddenEmissionFinding(
                file_path=relative_path,
                line_number=_line_number_for_match_start(file_text, match.start()),
                rule="marker-literal",
                matched_text=match.group(0),
            )
        )
    for match in _PATTERN_META_REVIEW_COMPLETENESS.finditer(file_text):
        findings.append(
            ForbiddenEmissionFinding(
                file_path=relative_path,
                line_number=_line_number_for_match_start(file_text, match.start()),
                rule="meta-discriminator",
                matched_text=match.group(0),
            )
        )
    return findings


def _discover_scan_targets(repo_root: pathlib.Path) -> list[pathlib.Path]:
    """Return the deterministic scan-target list per the AC-9 scope.

    Scope:
        * every ``.py`` file under
          ``tools/loud-fail-harness/src/loud_fail_harness/``;
        * ``agents/review-bmad-wrapper.md`` if it exists.

    Sorted by relative POSIX path for deterministic stdout.
    """
    src_dir = (
        repo_root
        / "tools"
        / "loud-fail-harness"
        / "src"
        / "loud_fail_harness"
    )
    targets: list[pathlib.Path] = []
    if src_dir.is_dir():
        for entry in src_dir.rglob("*.py"):
            if entry.is_file():
                targets.append(entry)
    wrapper = repo_root / "agents" / "review-bmad-wrapper.md"
    if wrapper.is_file():
        targets.append(wrapper)
    targets.sort(
        key=lambda p: p.relative_to(repo_root).as_posix()
    )
    return targets


def run_gate(repo_root: pathlib.Path) -> GateResult:
    """Execute the gate and produce a :class:`GateResult`."""
    targets = _discover_scan_targets(repo_root)
    scanned_files: list[str] = []
    violations: list[ForbiddenEmissionFinding] = []

    for path in targets:
        relative_path = path.relative_to(repo_root).as_posix()
        scanned_files.append(relative_path)
        if relative_path in _ALLOWLIST_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                f"file not UTF-8: {relative_path}"
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f"file unreadable: {relative_path}"
            ) from exc
        violations.extend(_scan_file_for_violations(relative_path, text))

    violations.sort(key=lambda f: (f.file_path, f.line_number, f.rule))

    return GateResult(
        scanned_files=scanned_files,
        forbidden_emission_violation=violations,
    )


def format_findings(result: GateResult) -> str:
    """Render a :class:`GateResult` for stdout."""
    lines: list[str] = []
    lines.append("Review-layer-failure emission gate (Story 3.3; FR28 + FR56)")
    exempted = sum(1 for f in result.scanned_files if f in _ALLOWLIST_FILES)
    lines.append(
        f"  scanned files: {len(result.scanned_files)} "
        f"(allowlist exempted: {exempted})"
    )
    lines.append(
        "  rules: (a) failed-layers-write (b) marker-literal "
        "(c) meta-discriminator"
    )
    lines.append("")

    for finding in result.forbidden_emission_violation:
        lines.append(
            f"Forbidden-emission violation: {finding.file_path}:"
            f"{finding.line_number} (rule {finding.rule}): "
            f'matched "{finding.matched_text}".'
        )
        lines.append(_REMEDIATION)
        lines.append("")

    lines.append(
        f"Summary: {len(result.forbidden_emission_violation)} "
        f"forbidden-emission violation(s)."
    )
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="review-layer-failure-emission-gate",
        description=(
            "Review-layer-failure single-emission-path CI gate (Story 3.3 "
            "AC-9). Enforces the three-channel atomic-emission code-"
            "structure invariant: surface_failed_layers is the only "
            "permitted emission path for the failed_layers envelope field, "
            "the review-layer-failed marker class string literal, and the "
            "meta: review-completeness synthetic-finding discriminator. "
            "FR28 + FR56 + Story 3.3 AC-1."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to inner repo root (default: resolved via "
            "find_repo_root()). Test-injection flag; CI invocations omit it."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    repo_root: pathlib.Path
    if args.repo_root is None:
        try:
            repo_root = find_repo_root()
        except RuntimeError as exc:
            print(f"harness-level error: {exc}", file=sys.stderr)
            return 2
    else:
        repo_root = args.repo_root

    try:
        result = run_gate(repo_root)
    except RuntimeError as exc:
        print(f"harness-level error: {exc}", file=sys.stderr)
        return 2

    print(format_findings(result))

    if result.forbidden_emission_violation:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
