"""Substrate component 5: Marker-taxonomy ↔ fixture-coverage enumerator (Layer C completeness mitigation).

See ADR-003.

This module is Layer C's *completeness mitigation* — the closure invariant
that every marker class enumerated in ``schemas/marker-taxonomy.yaml`` (story
1.4's v1 closed enum of 27 classes) has at least one synthetic-story fixture
exercising its emission path under ``examples/synthetic-stories/``. Story
1.8's FR33 fixture-driven gate consumes the same fixture corpus and replays
each fixture's expected marker through ``reconciler.py``; this story validates
COVERAGE (≥1 fixture per class) — story 1.8 validates RECONCILIATION-OF-
COVERED. Separate concerns; separate gates; separate stories.

Quad-classification (parallel to substrate component 4 / story 1.5's triple):

    passing          — every taxonomy class C with ≥1 fixture declaring
                       ``expected_marker == C`` AND whose frontmatter
                       parsed cleanly (no shape violations); one
                       ``Reference`` per matching fixture.
    uncovered        — every taxonomy class C with NO fixture declaring
                       ``expected_marker == C`` (FAIL — Layer C completeness
                       violation).
    dangling         — every fixture whose declared ``expected_marker`` is
                       NOT in the taxonomy (FAIL — closure-equivalence
                       violation).
    shape_violations — every fixture whose YAML frontmatter is structurally
                       malformed (missing delimiter, non-mapping, missing
                       required keys, unknown keys, non-string values).

Loud-fail discipline (Pattern 5):

    Exit code matrix:
        0 — full coverage; no findings of any class.
        1 — at least one of {uncovered, dangling, shape_violation}.
        2 — harness-level error (fixtures-dir doesn't exist; taxonomy
            unreadable / malformed). Per-fixture shape violations surface
            as exit 1 findings (NOT exit 2): the fixture is shape-broken;
            the gate fails the build.

    "Do not bail after first finding within a category" — every category
    is collected end-to-end before output (parallel to enumeration_check).
    Findings stream to stdout; harness-level errors stream to stderr.

FR65 / ADR-003 skip-class-recognition workflow (CI half):

    A new skip-class arrives via the audit-doc workflow. The FR65 step 3 is
    "add a fixture / synthetic story"; THIS GATE is the CI half of that
    step: a taxonomy entry without a matching fixture (or vice versa) fails
    the build with the unmatched marker class named in the diagnostic. The
    README under ``examples/synthetic-stories/`` documents the
    practitioner-side workflow.

Sensor-not-advisor (PRD-level invariant): the validator REPORTS what
classification each fixture / marker falls into and where, with remediation
pointers; it does NOT auto-write fixtures, suggest specific scenario prose,
or auto-add markers to the taxonomy. Same posture as 1.4 / 1.5 / 1.6.

Cross-story seam contract (1.7 ↔ 1.8): story 1.8 may extend the optional
frontmatter fields (``expected_sub_classification``, ``expected_event_class``)
into required fields for the reconciler-replay gate's purposes. This story
makes them OPTIONAL and forward-compatibly accepted so 1.8 can extend
without breaking changes.

Public surface mirrors 1.5 / 1.6's validator-module pattern:

    * :class:`Fixture` / :class:`Reference` / :class:`ShapeViolation` /
      :class:`CoverageResult` — Pydantic v2 frozen models. Field declaration
      order is load-bearing for ``model_dump_json()`` byte-stability.
    * :func:`discover_fixtures` — pure: walks the directory, parses each
      file's frontmatter, returns one :class:`Fixture` per ``*.md`` file.
    * :func:`check_fixture_coverage` — pure: produces the quad-classification.
    * :func:`format_findings` — renders a result for stdout.
    * :func:`main` — CLI entry; resolves defaults via
      :func:`loud_fail_harness._shared.find_repo_root`; reuses
      :func:`loud_fail_harness.reconciler.load_marker_taxonomy` (the third
      consumer of that helper after reconciler itself + enumeration_check).
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Sequence
from typing import Any, Optional

import yaml
from pydantic import BaseModel, ConfigDict

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.reconciler import load_marker_taxonomy

#: README filename, skipped by literal match during fixture discovery
#: (Dev Notes "README skipped from coverage walk"; brittle-heuristic
#: avoidance per the do-not-do matrix — do NOT use a "no-frontmatter →
#: README" heuristic).
_README_FILENAME = "README.md"

#: Required frontmatter keys per AC-2.
_REQUIRED_KEYS: tuple[str, ...] = ("expected_marker", "scenario")

#: All allowed frontmatter keys (required + optional reserved for story 1.8).
_ALLOWED_KEYS: tuple[str, ...] = (
    "expected_marker",
    "scenario",
    "expected_sub_classification",
    "expected_event_class",
    "notes",
)

#: AC-2 remediation suffix referenced from validator-contract diagnostics.
_FRONTMATTER_SHAPE_REMEDIATION = (
    "(per AC-2; see examples/synthetic-stories/README.md frontmatter shape section)"
)

#: Subdirectory remediation pointer (Dev Notes "Flat directory; no
#: subdirectories" — recommended exit-1 behavior).
_SUBDIR_REMEDIATION = (
    "(per Dev Notes 'Flat directory; no subdirectories'; "
    "move the file to examples/synthetic-stories/<filename>.md)"
)


class Reference(BaseModel):
    """A passing or dangling fixture reference (file_path + marker_class).

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable JSON dumps.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str
    marker_class: str


class ShapeViolation(BaseModel):
    """A single per-fixture frontmatter shape rule violation.

    NFR-O5 named-invariant diagnostic shape: every finding names

    * ``file_path``  — display path of the offending fixture (relative to
      repo root via :func:`loud_fail_harness._shared.find_repo_root`).
    * ``pointer``    — JSON-pointer-style path inside the frontmatter
      (``/expected_marker``, ``/scenario``, ``<root>`` for whole-file
      violations).
    * ``message``    — the violated invariant verbatim.
    * ``remediation`` — one-line NFR-O5 pointer naming AC-2 / Dev-Notes.

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable JSON dumps.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str
    pointer: str
    message: str
    remediation: str


class Fixture(BaseModel):
    """A single discovered fixture file.

    ``file_path`` is the display path relative to repo root.
    ``expected_marker`` is None when the frontmatter is malformed and the
    shape violation has already been recorded; in that case
    ``frontmatter_findings`` is non-empty. When the frontmatter parses
    cleanly, ``expected_marker`` carries the canonical ``marker_class``
    identifier and ``frontmatter_findings`` is empty.

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` (parallel to
    1.4 / 1.5 / 1.6 frozen-model discipline).
    """

    model_config = ConfigDict(frozen=True)

    file_path: str
    expected_marker: Optional[str]
    frontmatter_findings: list[ShapeViolation]


class CoverageResult(BaseModel):
    """Quad-classification fixture-coverage output.

    * ``passing`` — one :class:`Reference` per fixture whose
      ``expected_marker`` resolves to a taxonomy entry; sorted by
      ``(file_path, marker_class)``.
    * ``uncovered`` — taxonomy classes with zero matching fixtures;
      lex-sorted.
    * ``dangling`` — fixtures whose ``expected_marker`` is NOT in the
      taxonomy; sorted by ``(file_path, marker_class)``.
    * ``shape_violations`` — per-fixture frontmatter rule violations;
      sorted by ``(file_path, pointer)``.

    Field declaration order matches Pydantic v2's JSON-serialization order
    (load-bearing for byte-stable dumps).
    """

    model_config = ConfigDict(frozen=True)

    passing: list[Reference]
    uncovered: list[str]
    dangling: list[Reference]
    shape_violations: list[ShapeViolation]


def _type_name(value: Any) -> str:
    """Render a YAML-load-time Python value's type for diagnostic prose."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, dict):
        return "mapping"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def _make_violation(
    file_path: str,
    pointer: str,
    message: str,
    remediation: str = _FRONTMATTER_SHAPE_REMEDIATION,
) -> ShapeViolation:
    return ShapeViolation(
        file_path=file_path,
        pointer=pointer,
        message=message,
        remediation=remediation,
    )


def _split_frontmatter(text: str) -> tuple[Optional[str], Optional[str]]:
    """Split a fixture's text into ``(frontmatter_yaml, body)``.

    Returns ``(None, None)`` if the file does not begin with the ``---``
    opening delimiter. Returns ``("", None)`` (or ``(<text>, None)``) if
    the opening delimiter is present but the closing delimiter is missing.
    Otherwise returns the literal frontmatter region (the lines between the
    two ``---`` delimiters) and the body (every line after the closing
    delimiter).

    The opening delimiter MUST be exactly ``---`` on its own line (line 1).
    The closing delimiter MUST be exactly ``---`` on its own line.
    """
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != "---":
        return (None, None)
    fm_end_idx: Optional[int] = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r") == "---":
            fm_end_idx = i
            break
    if fm_end_idx is None:
        return ("", None)
    frontmatter = "\n".join(lines[1:fm_end_idx])
    body = "\n".join(lines[fm_end_idx + 1 :])
    return (frontmatter, body)


def _parse_frontmatter(
    content: str, file_path: str
) -> tuple[Optional[dict], list[ShapeViolation]]:
    """Parse a fixture's frontmatter into ``(parsed_dict, findings_list)``.

    The dict is None when the frontmatter is structurally unparseable
    (no opening / closing delimiter, YAML parse failure, non-mapping). When
    parsing succeeds, the dict is returned alongside any per-rule findings
    (missing required keys, unknown keys, non-string values) so callers can
    still extract ``expected_marker`` (if present and string-typed) even
    from a partially-malformed frontmatter — keeping the "do not bail after
    first finding" discipline (1.5 / 1.6) intact.
    """
    findings: list[ShapeViolation] = []
    fm_text, body = _split_frontmatter(content)

    if fm_text is None:
        findings.append(
            _make_violation(
                file_path,
                "<root>",
                "fixture file does not begin with YAML frontmatter delimiter ('---')",
            )
        )
        return (None, findings)

    if body is None:
        findings.append(
            _make_violation(
                file_path,
                "<root>",
                "fixture file is missing YAML frontmatter closing delimiter ('---')",
            )
        )
        return (None, findings)

    try:
        parsed = yaml.safe_load(fm_text) if fm_text.strip() else {}
    except yaml.YAMLError as exc:
        findings.append(
            _make_violation(
                file_path,
                "<root>",
                f"frontmatter YAML parse failure: {exc}",
            )
        )
        return (None, findings)

    if not isinstance(parsed, dict):
        findings.append(
            _make_violation(
                file_path,
                "<root>",
                f"frontmatter must be a YAML mapping; got {_type_name(parsed)}",
            )
        )
        return (None, findings)

    for required in _REQUIRED_KEYS:
        if required not in parsed:
            findings.append(
                _make_violation(
                    file_path,
                    f"/{required}",
                    f"missing required field '{required}'",
                )
            )

    if "expected_marker" in parsed and not isinstance(parsed["expected_marker"], str):
        findings.append(
            _make_violation(
                file_path,
                "/expected_marker",
                f"'expected_marker' must be a string; "
                f"got {_type_name(parsed['expected_marker'])}",
            )
        )
    if "scenario" in parsed and not isinstance(parsed["scenario"], str):
        findings.append(
            _make_violation(
                file_path,
                "/scenario",
                f"'scenario' must be a string; got {_type_name(parsed['scenario'])}",
            )
        )

    for key in parsed:
        if key not in _ALLOWED_KEYS:
            findings.append(
                _make_violation(
                    file_path,
                    f"/{key}",
                    f"unknown frontmatter field '{key}' "
                    f"(allowed: {', '.join(_ALLOWED_KEYS)})",
                )
            )

    return (parsed, findings)


def _display_path(
    path: pathlib.Path, repo_root: Optional[pathlib.Path] = None
) -> str:
    """Render ``path`` relative to repo root if possible; absolute otherwise.

    Test invocations pass tmp_path files outside the repo — for those the
    relative resolution fails and the absolute path is returned, which is
    still informative in stdout. Canonical CI invocations use the in-repo
    fixture corpus and produce stable relative paths like
    ``examples/synthetic-stories/heuristic-skipped.md``.
    """
    try:
        rr = repo_root if repo_root is not None else find_repo_root()
        return str(path.resolve().relative_to(rr.resolve()))
    except (RuntimeError, ValueError):
        return str(path.resolve())


def discover_fixtures(
    synthetic_stories_dir: pathlib.Path,
    *,
    repo_root: Optional[pathlib.Path] = None,
) -> list[Fixture]:
    """Enumerate ``*.md`` files under ``synthetic_stories_dir`` (flat —
    NOT recursive), skip ``README.md`` by literal filename, parse each
    fixture's frontmatter, and return one :class:`Fixture` per file.

    Sorted lexicographically by ``file_path`` for determinism.

    A ``*.md`` file found inside any subdirectory of
    ``synthetic_stories_dir`` is surfaced as a :class:`Fixture` with
    ``expected_marker=None`` and a single ``frontmatter_findings`` entry
    declaring the subdirectory rule violation (Dev Notes "Flat directory;
    no subdirectories" — recommended exit-1 behavior, NOT exit-2). The
    fixture is NOT parsed for frontmatter — the rule violation alone is
    sufficient signal.

    Raises ``FileNotFoundError`` if ``synthetic_stories_dir`` does not
    exist; other ``OSError`` subclasses propagate as well. Both surface as
    exit 2 from :func:`main`.
    """
    if not synthetic_stories_dir.is_dir():
        raise FileNotFoundError(
            f"examples/synthetic-stories/ does not exist at {synthetic_stories_dir}"
        )

    fixtures: list[Fixture] = []

    for entry in sorted(synthetic_stories_dir.iterdir(), key=lambda p: p.name):
        if entry.is_dir():
            for sub in sorted(entry.rglob("*.md"), key=lambda p: str(p)):
                display = _display_path(sub, repo_root=repo_root)
                violation = _make_violation(
                    display,
                    "<root>",
                    "fixture file outside the flat fixture directory; "
                    "subdirectories not permitted",
                    remediation=_SUBDIR_REMEDIATION,
                )
                fixtures.append(
                    Fixture(
                        file_path=display,
                        expected_marker=None,
                        frontmatter_findings=[violation],
                    )
                )
            continue
        if not entry.is_file():
            continue
        if entry.name == _README_FILENAME:
            continue
        if entry.suffix != ".md":
            continue

        display = _display_path(entry, repo_root=repo_root)
        try:
            text = entry.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            violation = _make_violation(
                display,
                "<root>",
                f"fixture file is not valid UTF-8: {exc}",
            )
            fixtures.append(
                Fixture(
                    file_path=display,
                    expected_marker=None,
                    frontmatter_findings=[violation],
                )
            )
            continue
        parsed, findings = _parse_frontmatter(text, display)
        expected_marker: Optional[str] = None
        if parsed is not None:
            raw = parsed.get("expected_marker")
            if isinstance(raw, str):
                expected_marker = raw
        fixtures.append(
            Fixture(
                file_path=display,
                expected_marker=expected_marker,
                frontmatter_findings=findings,
            )
        )

    fixtures.sort(key=lambda f: f.file_path)
    return fixtures


def check_fixture_coverage(
    fixtures: list[Fixture], taxonomy: set[str]
) -> CoverageResult:
    """Partition ``fixtures`` against ``taxonomy`` into the four classes.

    See module docstring + AC-5 for the rule. Pure function; deterministic
    output; sorted lists.

    The closure invariant is on the deduplicated set of marker classes
    (``len(distinct_passing) == len(taxonomy)`` AND ``uncovered == []``),
    NOT on the fixture count: multiple fixtures may declare the same
    ``expected_marker`` (e.g. canonical + per-sub_classification variant);
    each contributes a distinct ``passing`` entry.
    """
    passing: list[Reference] = []
    dangling: list[Reference] = []
    shape_violations: list[ShapeViolation] = []
    covered: set[str] = set()

    for fx in fixtures:
        shape_violations.extend(fx.frontmatter_findings)
        if fx.expected_marker is None:
            continue
        if fx.expected_marker in taxonomy:
            if not fx.frontmatter_findings:
                # AC-5: only cleanly-parsed fixtures count toward passing.
                # A fixture with shape violations (e.g. missing 'scenario')
                # does not cover its marker class; the class goes to uncovered.
                passing.append(
                    Reference(file_path=fx.file_path, marker_class=fx.expected_marker)
                )
                covered.add(fx.expected_marker)
        else:
            dangling.append(
                Reference(file_path=fx.file_path, marker_class=fx.expected_marker)
            )

    uncovered = sorted(taxonomy - covered)
    passing.sort(key=lambda r: (r.file_path, r.marker_class))
    dangling.sort(key=lambda r: (r.file_path, r.marker_class))
    shape_violations.sort(key=lambda v: (v.file_path, v.pointer))

    return CoverageResult(
        passing=passing,
        uncovered=uncovered,
        dangling=dangling,
        shape_violations=shape_violations,
    )


def format_findings(
    result: CoverageResult,
    *,
    fixtures_dir: str,
    taxonomy_path: str,
) -> str:
    """Render the validator result for stdout.

    Header naming inputs; passing-summary line; uncovered + dangling +
    shape-violation bullet lists (each FAIL); footer Summary line. Mirrors
    the "name the offending entity + remediation pointer" discipline from
    1.5 / 1.6.
    """
    lines: list[str] = []
    lines.append("Fixture coverage check (substrate component 5)")
    lines.append(f"  fixtures dir: {fixtures_dir}")
    lines.append(f"  taxonomy:     {taxonomy_path}")
    lines.append("")

    distinct_passing = sorted({r.marker_class for r in result.passing})
    has_findings = bool(
        result.uncovered or result.dangling or result.shape_violations
    )
    if not has_findings:
        lines.append(
            f"OK: {len(result.passing)} passing fixture(s) covering "
            f"{len(distinct_passing)} distinct marker class(es)."
        )
    else:
        lines.append(
            f"OK: {len(result.passing)} passing fixture(s) covering "
            f"{len(distinct_passing)} distinct marker class(es) "
            "(but findings below)."
        )

    if result.uncovered:
        lines.append("")
        lines.append(
            f"FAIL: {len(result.uncovered)} uncovered marker class(es) "
            "(no fixture exercises this class — Layer C completeness violation)."
        )
        for marker_class in result.uncovered:
            lines.append(
                f"  - uncovered marker class '{marker_class}' "
                f"(per AC-1; add a fixture at "
                f"examples/synthetic-stories/{marker_class}.md "
                f"with frontmatter 'expected_marker: {marker_class}')"
            )

    if result.dangling:
        lines.append("")
        lines.append(
            f"FAIL: {len(result.dangling)} dangling fixture(s) "
            "(declared expected_marker is NOT in schemas/marker-taxonomy.yaml)."
        )
        for ref in result.dangling:
            lines.append(
                f"  - dangling fixture: {ref.file_path}: "
                f"declared expected_marker '{ref.marker_class}' is not in "
                "schemas/marker-taxonomy.yaml "
                "(per AC-2; either fix the fixture's expected_marker, OR add "
                "the new class to schemas/marker-taxonomy.yaml via the "
                "FR65 / ADR-003 skip-class-recognition workflow)"
            )

    if result.shape_violations:
        lines.append("")
        lines.append(
            f"FAIL: {len(result.shape_violations)} "
            "frontmatter shape-violation finding(s)."
        )
        for v in result.shape_violations:
            lines.append(
                f"  - {v.file_path}#{v.pointer}: {v.message} {v.remediation}"
            )

    lines.append("")
    lines.append(
        f"Summary: {len(distinct_passing)} passing marker class(es), "
        f"{len(result.uncovered)} uncovered marker class(es), "
        f"{len(result.dangling)} dangling fixture(s), "
        f"{len(result.shape_violations)} shape-violation finding(s)."
    )
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fixture-coverage",
        description=(
            "Validate that every marker class enumerated in "
            "schemas/marker-taxonomy.yaml has at least one synthetic-story "
            "fixture under examples/synthetic-stories/, and that every "
            "fixture's expected_marker resolves to an entry in the taxonomy. "
            "Substrate component 5; ADR-003 Layer C completeness mitigation."
        ),
    )
    parser.add_argument(
        "--fixtures-dir",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to examples/synthetic-stories/ (default: "
            "<repo-root>/examples/synthetic-stories/). Test-injection flag; "
            "CI invocations omit it."
        ),
    )
    parser.add_argument(
        "--taxonomy-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to marker-taxonomy.yaml (default: "
            "<repo-root>/schemas/marker-taxonomy.yaml). Test-injection flag; "
            "CI invocations omit it."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    fixtures_dir: pathlib.Path
    taxonomy_path: pathlib.Path
    repo_root: Optional[pathlib.Path] = None
    if args.fixtures_dir is None or args.taxonomy_path is None:
        try:
            repo_root = find_repo_root()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        fixtures_dir = (
            args.fixtures_dir or repo_root / "examples" / "synthetic-stories"
        )
        taxonomy_path = (
            args.taxonomy_path or repo_root / "schemas" / "marker-taxonomy.yaml"
        )
    else:
        fixtures_dir = args.fixtures_dir
        taxonomy_path = args.taxonomy_path

    try:
        taxonomy = load_marker_taxonomy(taxonomy_path)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print(
            "harness-level error: marker-taxonomy unreadable: "
            f"{taxonomy_path}: {exc}",
            file=sys.stderr,
        )
        return 2
    except yaml.YAMLError as exc:
        print(
            "harness-level error: marker-taxonomy YAML parse failure: "
            f"{taxonomy_path}: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        fixtures = discover_fixtures(fixtures_dir, repo_root=repo_root)
    except FileNotFoundError as exc:
        print(f"harness-level error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(
            "harness-level error: examples/synthetic-stories/ unreadable: "
            f"{fixtures_dir}: {exc}",
            file=sys.stderr,
        )
        return 2

    result = check_fixture_coverage(fixtures, taxonomy)
    print(
        format_findings(
            result,
            fixtures_dir=_display_path(fixtures_dir, repo_root=repo_root),
            taxonomy_path=_display_path(taxonomy_path, repo_root=repo_root),
        )
    )
    if result.uncovered or result.dangling or result.shape_violations:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
