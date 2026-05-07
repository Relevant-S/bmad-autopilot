"""Bundle-assembly-failure single-emission-path CI gate (Story 6.9 AC-4).

Architectural placement (Story 3.3's ``review_layer_failure_emission_gate.py``
precedent): this module is structurally a sibling of the prior CI gates
(``fr33_fixture_gate``, ``hook_budget_gate``, ``pluggability_gate``,
``review_layer_failure_emission_gate``) but it is **NOT a sixth substrate
component**. ADR-003 Consequence 1 enumerates exactly five substrate
components (``architecture.md`` lines 311-315); this gate is a CI **gate**
that enforces Story 6.9's three-channel atomic-emission code-structure
invariant.

What this gate enforces (Story 6.9 AC-1 + AC-4):
    * :func:`surface_assembly_failure` at
      :mod:`loud_fail_harness.bundle_assembly_failure` is the SINGLE
      source-of-truth emission path for the three-channel projection of a
      bundle-assembly logical failure (FR59 + NFR-O5). The atomicity is
      enforced as a code-structure invariant, NOT a per-bundle reconciliation
      gate. This is the SAME pattern Story 3.3 applied to
      ``surface_failed_layers`` and Story 2.2 applied to atomic-write:
      the API shape IS the invariant.

Forbidden patterns (any of the three triggers a lint violation):
    (a) **Quoted string literal of the ``bundle-assembly-failed`` marker
        class** outside the canonical emission site. Regex matches
        ``"bundle-assembly-failed"`` or ``'bundle-assembly-failed'``.
        Files that import :data:`BUNDLE_ASSEMBLY_FAILED_MARKER`
        symbolically from
        :mod:`loud_fail_harness.bundle_assembly_failure` are NOT
        flagged because the symbol name is not the literal string.
    (b) **Direct write to a ``*.assembly-failure.log`` path**
        outside the canonical emission site. Regex matches the literal
        suffix ``.assembly-failure.log`` (the canonical fallback file
        suffix) anywhere in the source — ANY mention of this filename
        suffix outside the source-of-truth module is a bypass attempt.
    (c) **Direct append of a ``bundle-assembly-failed`` entry to
        ``run_state.active_markers``** outside the canonical emission
        site. The narrow form is detected by Rule (a) above (any string
        literal of the marker class is itself a violation), so Rule (c)
        is structurally subsumed by Rule (a) — adopting the same shape as
        Story 3.3's three-rule precedent without creating a redundant
        regex; documented here for AC-4 traceability.

Scan scope (per AC-4 verbatim):
    * **Harness source tree** — every ``.py`` file under
      ``tools/loud-fail-harness/src/loud_fail_harness/``. Test files
      under ``tests/`` are NOT in the scan scope (tests construct
      synthesized failure scenarios + fabricate forbidden patterns to
      exercise the gate; including them would invert the gate's meaning).

Allowlist (canonical emission sites; exempt from the lint scope):
    * ``tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly_failure.py``
      — the canonical emission home (defines :func:`surface_assembly_failure`
      + the :data:`BUNDLE_ASSEMBLY_FAILED_MARKER` constant + the
      structured-text fallback-file format).
    * ``tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly_failure_emission_gate.py``
      — THIS gate file (defines the regex patterns being scanned for;
      naming the patterns is what the gate does).

Files NOT in the scan scope (out of scope by construction):
    * ``schemas/marker-taxonomy.yaml`` — defines the
      ``bundle-assembly-failed`` marker class; out of scope.
    * ``tools/loud-fail-harness/tests/*.py`` — tests fabricate
      forbidden patterns to exercise this gate; out of scope.
    * ``docs/*.md`` — extension-audit, architecture; documentation;
      out of scope.

Loud-fail discipline (Pattern 5):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — full pass: zero violations across the scan scope.
        1 — invariant violation: at least one forbidden pattern
            detected outside the allowlist. The fix is to route the
            offending emission through :func:`surface_assembly_failure`
            (the single source-of-truth function), then re-run the gate.
        2 — harness-level error: scan-scope file unreadable or
            non-UTF-8.

Sensor-not-advisor: the gate REPORTS per-file violations with
remediation pointers; it does NOT auto-edit source files.

Cross-references:
    * Story 1.10a ``pluggability_gate.py`` — the regex-rule precedent.
    * Story 2.2 ``run_state.py`` ``advance_run_state`` — the
      API-shape-enforced-invariant precedent.
    * Story 3.3 :mod:`loud_fail_harness.review_layer_failure_emission_gate`
      — the byte-for-byte structural precedent THIS gate mirrors.
    * Story 6.9 :mod:`loud_fail_harness.bundle_assembly_failure` — the
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
        "tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly_failure.py",
        "tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly_failure_emission_gate.py",
    }
)


#: Rule (a) — quoted string literal of the ``bundle-assembly-failed`` marker
#: class. Catches ``"bundle-assembly-failed"`` and ``'bundle-assembly-failed'``.
#: Importing the symbolic constant
#: :data:`loud_fail_harness.bundle_assembly_failure.BUNDLE_ASSEMBLY_FAILED_MARKER`
#: is NOT flagged because the symbol name is not the literal string.
_PATTERN_MARKER_LITERAL: re.Pattern[str] = re.compile(
    r"""["']bundle-assembly-failed["']"""
)

#: Rule (b) — direct mention of the canonical fallback-file suffix. Catches
#: the literal substring ``.assembly-failure.log`` anywhere in the file
#: (the suffix is itself the structural invariant; any direct mention
#: outside the source-of-truth module is a bypass attempt by construction).
_PATTERN_FALLBACK_FILE_SUFFIX: re.Pattern[str] = re.compile(
    r"\.assembly-failure\.log\b"
)


class ForbiddenEmissionFinding(BaseModel):
    """A Story 6.9 forbidden-emission violation finding.

    One :class:`ForbiddenEmissionFinding` per detected forbidden
    pattern; multiple findings per offending file are emitted (no
    bail-after-first per the loud-fail-doctrine pattern). Sorted by
    ``(file_path, line_number, rule)`` at the gate level.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str
    line_number: int
    rule: Literal["marker-literal", "fallback-file-suffix"]
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
    "(per FR59 + NFR-O5 + Story 6.9 AC-1 + AC-4 three-channel atomicity "
    "invariant: the fallback diagnostic file, the stderr line, and the "
    "persisted run-state marker are atomic — emit them through "
    "surface_assembly_failure (the single source-of-truth function at "
    "tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly_failure.py) "
    "so all three projections agree by construction. Remediation: (a) route "
    "the offending emission through surface_assembly_failure, OR (b) if the "
    "call site is bundle rendering, import BUNDLE_ASSEMBLY_FAILED_MARKER "
    "from loud_fail_harness.bundle_assembly_failure and use the symbolic "
    "constant rather than the string literal — symbol references are "
    "exempt from the lint by construction.)"
)


def _line_number_for_match_start(file_text: str, match_start: int) -> int:
    """Return the 1-indexed line number containing offset ``match_start``."""
    return file_text[:match_start].count("\n") + 1


def _scan_file_for_violations(
    relative_path: str, file_text: str
) -> list[ForbiddenEmissionFinding]:
    """Apply the rules to ``file_text`` and emit findings."""
    findings: list[ForbiddenEmissionFinding] = []
    for match in _PATTERN_MARKER_LITERAL.finditer(file_text):
        findings.append(
            ForbiddenEmissionFinding(
                file_path=relative_path,
                line_number=_line_number_for_match_start(file_text, match.start()),
                rule="marker-literal",
                matched_text=match.group(0),
            )
        )
    for match in _PATTERN_FALLBACK_FILE_SUFFIX.finditer(file_text):
        findings.append(
            ForbiddenEmissionFinding(
                file_path=relative_path,
                line_number=_line_number_for_match_start(file_text, match.start()),
                rule="fallback-file-suffix",
                matched_text=match.group(0),
            )
        )
    return findings


def _discover_scan_targets(repo_root: pathlib.Path) -> list[pathlib.Path]:
    """Return the deterministic scan-target list per the AC-4 scope.

    Scope: every ``.py`` file under
    ``tools/loud-fail-harness/src/loud_fail_harness/``.

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
    targets.sort(key=lambda p: p.relative_to(repo_root).as_posix())
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
    lines.append(
        "Bundle-assembly-failure emission gate (Story 6.9; FR59 + NFR-O5)"
    )
    exempted = sum(1 for f in result.scanned_files if f in _ALLOWLIST_FILES)
    lines.append(
        f"  scanned files: {len(result.scanned_files)} "
        f"(allowlist exempted: {exempted})"
    )
    lines.append(
        "  rules: (a) marker-literal (b) fallback-file-suffix"
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
        prog="bundle-assembly-failure-emission-gate",
        description=(
            "Bundle-assembly-failure single-emission-path CI gate "
            "(Story 6.9 AC-4). Enforces the three-channel atomic-emission "
            "code-structure invariant: surface_assembly_failure is the "
            "only permitted emission path for the bundle-assembly-failed "
            "marker class string literal and the canonical fallback "
            "file suffix .assembly-failure.log. FR59 + NFR-O5 + "
            "Story 6.9 AC-1 + AC-4."
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
