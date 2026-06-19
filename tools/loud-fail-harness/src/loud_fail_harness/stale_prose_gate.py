"""Stale-prose gate — Story 22.6 G1 (Epic 19 Action #2 / Epic 20 Action #2; 3rd recurrence).

Build-time gate (NOT a runtime marker — like sibling gates 22.4 / 24.2 / 24.3 it
emits :class:`Finding`s + a nonzero exit, never a persisted run-state marker).
Codifies the stale-prose recurrence the Epic 19 → 20 → 21 retros caught by human
review three times: when the marker taxonomy bumps its ``schema_version`` or its
top-level closed-set class count, a docstring/comment ELSEWHERE retains the old
value, and only human review notices.

## Design (canonical-derivation + anchored scan, NOT blind grep, NOT pure registry)

A pure registry (register each prose site) cannot catch *unregistered* stale
prose — exactly what was forgotten. A blind grep over all prose is false-positive
prone. The robust middle (the codebase-appropriate adaptation of Google's
``LINT.IfChange`` / ``LINT.ThenChange`` drift pattern — "you bump a constant and
forget the docs"):

  1. Derive the **one** live canonical value for each tracked quantity from its
     authoritative file — ``schema_version`` and the top-level ``marker_class``
     count from ``schemas/marker-taxonomy.yaml`` (NOT hardcoded).
  2. Scan a defined fileset (``src/loud_fail_harness/**/*.py`` docstrings +
     comments via :mod:`tokenize`, plus the designated ``docs/*.md`` surfaces
     that mirror these values) for **anchored present-tense** assertions of a
     version / count.
  3. Fail (exit 1) when a matched assertion contradicts the live canonical value.
  4. Honor a ``stale-prose-ok`` suppression pragma (``# stale-prose-ok: <reason>``
     in Python, ``<!-- stale-prose-ok: <reason> -->`` in markdown) on the matched
     line or the line directly above — the ``NO_IFTTT`` escape hatch for
     legitimate historical / changelog references.

## What is "anchored" (the false-positive discipline)

The gate fires only on a PRESENT-TENSE CANONICAL CLAIM about the marker taxonomy,
not on historical lineage. A version claim requires a marker-taxonomy anchor AND
the ``schema_version`` token AND a version literal on the same line, none of which
equals the canonical value, with NO lineage marker (changelog arrow ``->`` / ``→``,
``introduced`` / ``landed`` / ``added`` / ``consumed`` / ``bump`` / ``was`` /
``since`` / ``v1`` / …). A count claim requires ``closed-set`` AND an ``N-class``
token with the same lineage exclusions. The marker-taxonomy anchor is what
disambiguates the taxonomy's ``schema_version`` from the half-dozen OTHER schema
versions (run-state, epic-run-state, …) whose mentions must NOT fire.
"""

from __future__ import annotations

import argparse
import io
import pathlib
import re
import sys
import tokenize
from collections.abc import Iterable, Sequence
from typing import Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from ._shared import find_repo_root

__all__ = [
    "Finding",
    "GateResult",
    "canonical_values",
    "evaluate_prose",
    "format_findings",
    "main",
    "run_stale_prose_gate",
]

_TAXONOMY_REL: Final[str] = "schemas/marker-taxonomy.yaml"
_SRC_REL: Final[str] = "tools/loud-fail-harness/src/loud_fail_harness"
#: Designated docs/*.md surfaces that mirror the canonical taxonomy values. Kept
#: NARROW on purpose — only docs that present-tense-assert the live version/count
#: belong here; large historical/audit docs (extension-audit.md, the per-epic
#: retros) are deliberately excluded (their value mentions are historical record,
#: not a live mirror). Add a doc here ONLY when it carries a live-value claim.
_DESIGNATED_DOCS: Final[tuple[str, ...]] = (
    "docs/implementation-patterns.md",
)

_PRAGMA: Final[str] = "stale-prose-ok"

_VERSION_LITERAL = re.compile(r"\d+\.\d+")
_TAXONOMY_ANCHOR = re.compile(r"marker[- ]taxonomy", re.IGNORECASE)
_SCHEMA_VERSION_TOKEN = re.compile(r"schema[_ ]version", re.IGNORECASE)
_CLOSED_SET = re.compile(r"closed[- ]set", re.IGNORECASE)
_N_CLASS = re.compile(r"\b(\d+)[-\s]class\b", re.IGNORECASE)
#: Lineage / historical markers that mean a value mention is a record of a PAST
#: state, not a present-tense canonical claim — these lines never fire.
_LINEAGE = re.compile(
    r"→|->|\blanded\b|\badded\b|\bconsumed\b|"
    r"\bwas\b|\bbumped?\b|\bprevious\b|\bprior\b|\bhistorical\b|\bsince\b|\bv1\b|"
    r"\bas\s+of\b|\bsupersed\w*\b|\bformer\b|\boriginal\b",
    re.IGNORECASE,
)

FindingRule = Literal["stale-version-claim", "stale-count-claim"]


class Finding(BaseModel):
    """A single stale-prose violation.

    Frozen for determinism; field declaration order is load-bearing for
    byte-stable dumps (mirrors :class:`forward_pointer_drift_gate.LintFinding`).

    Attributes:
        rule: The violation discriminator.
        source_path: The scanned file the stale prose was found in (carried as a
            :class:`pathlib.Path` for renderer-side relative-path normalization).
        line_number: 1-indexed physical line of the offending prose.
        found: The stale literal(s) asserted in the prose.
        canonical: The live canonical value the prose contradicts.
        diagnostic: Human-readable message + remediation hint (NFR-O5).
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    rule: FindingRule
    source_path: pathlib.Path
    line_number: int
    found: str
    canonical: str
    diagnostic: str


class GateResult(BaseModel):
    """Aggregate gate result.

    Frozen for determinism; field declaration order is load-bearing for
    byte-stable dumps.

    Attributes:
        findings: All findings, ordered by ``(source_path, line_number, rule)``.
        canonical_schema_version: The live marker-taxonomy ``schema_version``.
        canonical_closed_set_count: The live top-level ``marker_class`` count.
        files_scanned: Count of files scanned (non-vacuity witness).
    """

    model_config = ConfigDict(frozen=True)

    findings: tuple[Finding, ...]
    canonical_schema_version: str
    canonical_closed_set_count: int
    files_scanned: int


def canonical_values(taxonomy_path: pathlib.Path) -> tuple[str, int]:
    """Derive ``(schema_version, closed_set_count)`` from the marker taxonomy.

    Raises :class:`ValueError` on a malformed taxonomy (mapped to exit 2 by
    :func:`main`); :class:`OSError` / :class:`yaml.YAMLError` propagate the same
    way.
    """
    raw = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"marker taxonomy {taxonomy_path} did not parse to a YAML mapping"
        )
    schema_version = raw.get("schema_version")
    if not isinstance(schema_version, str):
        raise ValueError(
            f"marker taxonomy {taxonomy_path} has no string `schema_version`"
        )
    markers = raw.get("markers")
    if not isinstance(markers, list):
        raise ValueError(
            f"marker taxonomy {taxonomy_path} has no `markers` list"
        )
    count = sum(
        1 for m in markers if isinstance(m, dict) and "marker_class" in m
    )
    return schema_version, count


def _prose_line_numbers(source: str) -> set[int]:
    """Return the 1-indexed physical line numbers inside Python comments and
    string literals (docstrings) — the prose surface, via :mod:`tokenize`."""
    prose: set[int] = set()
    reader = io.StringIO(source).readline
    for tok in tokenize.generate_tokens(reader):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            for lineno in range(tok.start[0], tok.end[0] + 1):
                prose.add(lineno)
    return prose


def _is_suppressed(lines: list[str], index: int) -> bool:
    """The ``stale-prose-ok`` pragma on the matched line or the line above."""
    if _PRAGMA in lines[index]:
        return True
    return index > 0 and _PRAGMA in lines[index - 1]


def _line_findings(
    *,
    source_path: pathlib.Path,
    line_number: int,
    line: str,
    canonical_version: str,
    canonical_count: int,
) -> list[Finding]:
    findings: list[Finding] = []
    if _LINEAGE.search(line):
        return findings

    if (
        _TAXONOMY_ANCHOR.search(line)
        and _SCHEMA_VERSION_TOKEN.search(line)
    ):
        literals = _VERSION_LITERAL.findall(line)
        if literals and canonical_version not in literals:
            findings.append(
                Finding(
                    rule="stale-version-claim",
                    source_path=source_path,
                    line_number=line_number,
                    found=", ".join(literals),
                    canonical=canonical_version,
                    diagnostic=(
                        "prose asserts marker-taxonomy schema_version "
                        f"{', '.join(literals)} but the live canonical value in "
                        f"schemas/marker-taxonomy.yaml is {canonical_version}. "
                        "Update the prose to the live value, or add a "
                        "`stale-prose-ok: <reason>` pragma if this is a "
                        "legitimate historical/changelog reference."
                    ),
                )
            )

    if _CLOSED_SET.search(line):
        for match in _N_CLASS.finditer(line):
            if int(match.group(1)) != canonical_count:
                findings.append(
                    Finding(
                        rule="stale-count-claim",
                        source_path=source_path,
                        line_number=line_number,
                        found=match.group(1),
                        canonical=str(canonical_count),
                        diagnostic=(
                            f"prose asserts a {match.group(1)}-class closed-set but "
                            f"the live marker-taxonomy closed-set count is "
                            f"{canonical_count}. Update the prose to the live value, "
                            "or add a `stale-prose-ok: <reason>` pragma if this is a "
                            "legitimate historical reference."
                        ),
                    )
                )
    return findings


def evaluate_prose(
    *,
    source_path: pathlib.Path,
    prose_line_numbers: set[int] | None,
    text: str,
    canonical_version: str,
    canonical_count: int,
) -> list[Finding]:
    """Scan ``text`` for stale version/count claims. Pure (no I/O).

    ``prose_line_numbers`` restricts the scan to Python comment/docstring lines;
    pass ``None`` to scan every line (markdown).
    """
    lines = text.splitlines()
    findings: list[Finding] = []
    for index, line in enumerate(lines):
        line_number = index + 1
        if prose_line_numbers is not None and line_number not in prose_line_numbers:
            continue
        line_findings = _line_findings(
            source_path=source_path,
            line_number=line_number,
            line=line,
            canonical_version=canonical_version,
            canonical_count=canonical_count,
        )
        if line_findings and not _is_suppressed(lines, index):
            findings.extend(line_findings)
    return findings


def _iter_python_files(src_dir: pathlib.Path) -> Iterable[pathlib.Path]:
    return sorted(p for p in src_dir.rglob("*.py") if p.is_file())


def run_stale_prose_gate(
    *,
    taxonomy_path: pathlib.Path,
    src_dir: pathlib.Path,
    doc_paths: Sequence[pathlib.Path],
) -> GateResult:
    """Read inputs, derive canonical values, scan the fileset.

    Raises :class:`OSError` / :class:`UnicodeDecodeError` / :class:`ValueError` /
    :class:`yaml.YAMLError` / :class:`tokenize.TokenError` — all mapped to exit 2
    by :func:`main` (loud-fail; never a silent exit-0 empty set).
    """
    canonical_version, canonical_count = canonical_values(taxonomy_path)
    findings: list[Finding] = []
    files_scanned = 0

    for py_path in _iter_python_files(src_dir):
        source = py_path.read_text(encoding="utf-8")
        prose = _prose_line_numbers(source)
        findings.extend(
            evaluate_prose(
                source_path=py_path,
                prose_line_numbers=prose,
                text=source,
                canonical_version=canonical_version,
                canonical_count=canonical_count,
            )
        )
        files_scanned += 1

    for doc_path in doc_paths:
        if not doc_path.is_file():
            continue
        text = doc_path.read_text(encoding="utf-8")
        findings.extend(
            evaluate_prose(
                source_path=doc_path,
                prose_line_numbers=None,
                text=text,
                canonical_version=canonical_version,
                canonical_count=canonical_count,
            )
        )
        files_scanned += 1

    findings.sort(key=lambda f: (str(f.source_path), f.line_number, f.rule))
    return GateResult(
        findings=tuple(findings),
        canonical_schema_version=canonical_version,
        canonical_closed_set_count=canonical_count,
        files_scanned=files_scanned,
    )


def _display_path(path: pathlib.Path, base_dir: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(base_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def format_findings(result: GateResult, *, base_dir: pathlib.Path) -> str:
    """Render a :class:`GateResult` for stdout, byte-stable."""
    lines: list[str] = []
    lines.append("stale-prose gate (story 22.6; G1)")
    lines.append(
        f"  canonical marker-taxonomy schema_version: "
        f"{result.canonical_schema_version}"
    )
    lines.append(
        f"  canonical closed-set count: {result.canonical_closed_set_count}"
    )
    lines.append(f"  files scanned: {result.files_scanned}")
    lines.append("")
    for finding in result.findings:
        rendered = _display_path(finding.source_path, base_dir)
        lines.append(
            f"stale-prose-gate: {rendered}:{finding.line_number} "
            f"{finding.rule} {finding.diagnostic}"
        )
        lines.append("")
    if not result.findings:
        lines.append(
            f"stale-prose-gate: 0 findings ({result.files_scanned} files scanned)"
        )
    else:
        lines.append(f"stale-prose-gate: {len(result.findings)} findings")
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stale-prose-gate",
        description=(
            "Stale-prose gate (story 22.6; G1). Fails when prose (a "
            "docstring/comment in src/loud_fail_harness/**/*.py, or a designated "
            "docs/*.md surface) asserts a marker-taxonomy schema_version or "
            "closed-set count that contradicts the live canonical value derived "
            "from schemas/marker-taxonomy.yaml. Honors a `stale-prose-ok: "
            "<reason>` suppression pragma. Build-time gate — no runtime marker."
        ),
    )
    parser.add_argument(
        "--taxonomy",
        type=pathlib.Path,
        default=None,
        help="Path to marker-taxonomy.yaml (default: under the repo root).",
    )
    parser.add_argument(
        "--src-dir",
        type=pathlib.Path,
        default=None,
        help="Path to the harness src package (default: under the repo root).",
    )
    parser.add_argument(
        "--doc",
        dest="docs",
        action="append",
        type=pathlib.Path,
        default=None,
        help=(
            "A docs/*.md surface to scan (repeatable). Defaults to the designated "
            "docs that mirror the canonical values."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Exit codes:
        * ``0`` — ``GateResult.findings == ()`` (full pass).
        * ``1`` — any finding present (stale prose detected).
        * ``2`` — harness-level error (inputs unresolvable / unreadable / a
          malformed taxonomy / an unparseable Python source). Never a silent
          exit-0.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = find_repo_root()
    except RuntimeError as exc:
        print(f"stale-prose-gate: harness-level error: {exc}", file=sys.stderr)
        return 2

    taxonomy_path: pathlib.Path = args.taxonomy or (repo_root / _TAXONOMY_REL)
    src_dir: pathlib.Path = args.src_dir or (repo_root / _SRC_REL)
    doc_paths: list[pathlib.Path] = (
        args.docs
        if args.docs is not None
        else [repo_root / rel for rel in _DESIGNATED_DOCS]
    )

    if not taxonomy_path.is_file():
        print(
            f"stale-prose-gate: harness-level error: marker taxonomy not found "
            f"({taxonomy_path!s})",
            file=sys.stderr,
        )
        return 2
    if not src_dir.is_dir():
        print(
            f"stale-prose-gate: harness-level error: src dir not found "
            f"({src_dir!s})",
            file=sys.stderr,
        )
        return 2

    try:
        result = run_stale_prose_gate(
            taxonomy_path=taxonomy_path,
            src_dir=src_dir,
            doc_paths=doc_paths,
        )
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        yaml.YAMLError,
        tokenize.TokenError,
        SyntaxError,
    ) as exc:
        print(f"stale-prose-gate: harness-level error: {exc}", file=sys.stderr)
        return 2

    print(format_findings(result, base_dir=repo_root))
    return 1 if result.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
