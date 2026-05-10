"""No-destructive-resume CI lint gate — Story 8.6.

## What this gate enforces

Per epics.md:3389-3393 verbatim: "no code surface in 8.1 / 8.2 / 8.3 makes
a dispatch decision without calling ``can_dispatch()`` ... new state-
mutating paths added in future epics are required to consume
``can_dispatch()`` rather than implementing parallel logic ... violations
fail CI with a diagnostic naming the offending file and code path".

Mirrors :mod:`pluggability_gate` byte-for-byte in *shape* (LintFinding +
LintResult frozen Pydantic models + format_findings deterministic
formatter + main CLI exiting 0/1/2 per finding-presence /
substrate-error). The IMPLEMENTATION technique differs: pluggability_gate
uses regex-based scanning of agents' markdown text (specialists are
markdown subagents); THIS gate uses AST-based scanning of Python source
(the governed modules are Python).

## The three structural rules

* **Rule A — import-missing**: a top-level
  ``from .no_destructive_resume_guard import can_dispatch`` (or any
  equivalent ``from .no_destructive_resume_guard import ...
  can_dispatch ...``) is present in the governed module. Allowlist for
  Rule A is the SUBSET ``{"session_start_reattach", "resume_command"}``
  — ``cross_state_recovery`` is governed (per AC-3's three-element
  governed-modules list) but excluded from Rule A because per AC-4 it
  has a docstring-only update (NO callsite, NO import).
* **Rule B — callsite-missing**: each ``ast.FunctionDef`` whose name is
  in the closed dispatch-decision-pattern set
  ``{"evaluate_resume", "evaluate_reattach"}`` (intentionally EXCLUDES
  ``evaluate_recovery`` since recovery does NOT dispatch — its job is
  reconciliation) contains at least one descendant ``ast.Call`` whose
  ``func`` is either ``ast.Name(id="can_dispatch")`` OR
  ``ast.Attribute(attr="can_dispatch")`` (covering both the
  from-import path and the attribute-access path).
* **Rule C — inline-reintroduced**: the regression guard. Walks EVERY
  ``.py`` file under ``harness_root / "src/loud_fail_harness/"`` (NOT
  just the governed-modules allowlist — the guard fires against any
  re-introduction of the inline pattern in any module under the
  harness substrate). Asserts NO ``ast.FunctionDef`` named
  ``_can_dispatch_inline`` AND NO ``ast.Call`` whose ``func`` resolves
  to that name.

## Forward-resilience

When a future epic's story introduces a NEW Python module needing
dispatch decisions, the AC-3 lint's *governed-modules list* (a closed
allowlist enumerated in :data:`_GOVERNED_MODULES`) is extended to
include the new module's stem; if the developer forgets to extend the
list, the new module IS NOT scanned (false-negative for Rule A/B) — the
secondary defense is Rule C, which runs against ALL files under
``loud_fail_harness/``, catching any re-introduction of the inline
pattern even in unscanned modules.

## Loud-fail discipline (Pattern 5)

Exit codes distinguish failure classes so CI logs are diagnosable.
    0 — full pass: ``LintResult.findings == ()``.
    1 — invariant violation: any finding present. Recoverable by
        following each finding's ``diagnostic`` remediation hint.
    2 — harness-level error: a governed module file is unreadable
        OR not valid UTF-8 OR not parseable as Python. Practitioners
        disambiguate via the stderr prefix
        ``"no-destructive-resume-lint: harness-level error: ..."``.

## Sensor-not-advisor (PRD-level invariant)

The gate REPORTS findings with remediation pointers; it does NOT
auto-edit governed modules, suggest specific refactors, or rewrite
imports. Same posture as 1.4 / 1.5 / 1.6 / 1.7 / 1.8 / 1.9 / 1.10a.

## Library-import-time invariant

The :data:`_GOVERNED_MODULES` constant is enforced at the test level
(``tests/test_no_destructive_resume_lint.py::test_governed_modules_constant_equals_documented_three_element_tuple``).
Adding a fourth governed module is a CI-driven future extension per
epics.md:3392 — extension shape is a single-line edit to the constant
plus the corresponding callsite + import in the new module.
"""

from __future__ import annotations

import argparse
import ast
import logging
import pathlib
import sys
from collections.abc import Sequence
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from ._shared import find_repo_root

__all__ = [
    "LintFinding",
    "LintResult",
    "format_findings",
    "main",
    "run_no_destructive_resume_lint",
]

_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Module-level constants                                                      #
# --------------------------------------------------------------------------- #


#: Closed allowlist of governed module file-stems (under
#: ``src/loud_fail_harness/``). Per AC-3, exactly the three modules
#: epics.md:3384 enumerates: 8.1's session_start_reattach, 8.2's
#: cross_state_recovery, 8.3's resume_command. Adding a fourth governed
#: module is a future-story extension (epics.md:3392 verbatim).
_GOVERNED_MODULES: Final[tuple[str, ...]] = (
    "session_start_reattach",
    "cross_state_recovery",
    "resume_command",
)


#: SUBSET of :data:`_GOVERNED_MODULES` for Rule A — the modules expected
#: to carry a top-level import of ``can_dispatch``. ``cross_state_recovery``
#: per AC-4 has a docstring-only update (NO callsite, NO import).
_RULE_A_MODULES: Final[tuple[str, ...]] = (
    "session_start_reattach",
    "resume_command",
)


#: Closed set of ``ast.FunctionDef`` names that compute a dispatch
#: decision per AC-3 Rule B. Intentionally EXCLUDES ``evaluate_recovery``
#: since recovery is reconciliation, not dispatch.
_DISPATCH_DECISION_FUNCTIONS: Final[frozenset[str]] = frozenset(
    {"evaluate_resume", "evaluate_reattach"}
)


#: The forbidden inline name. Rule C asserts no FunctionDef of this name
#: exists and no Call to this name exists under any module in the harness
#: substrate. The post-Story-8.6 grep MUST return zero hits.
_FORBIDDEN_INLINE_NAME: Final[str] = "_can_dispatch_inline"


#: Module name (relative-import target) the governed modules' Rule A
#: import points at.
_GUARD_MODULE_NAME: Final[str] = "no_destructive_resume_guard"


#: The canonical entry function from the guard module.
_CAN_DISPATCH_NAME: Final[str] = "can_dispatch"


#: AC-3 remediation pointer for Rule A.
_RULE_A_REMEDIATION: str = (
    "(per Story 8.6 AC-3 Rule A: governed modules under {session_start_reattach, "
    "resume_command} MUST import can_dispatch from no_destructive_resume_guard. "
    "Remediation: add `from .no_destructive_resume_guard import can_dispatch` at "
    "module top-level.)"
)


#: AC-3 remediation pointer for Rule B.
_RULE_B_REMEDIATION: str = (
    "(per Story 8.6 AC-3 Rule B: dispatch-decision functions {evaluate_resume, "
    "evaluate_reattach} MUST call can_dispatch() within their body. Remediation: "
    "wire the canonical guard per Story 8.6 AC-4's callsite-rewrite enumeration.)"
)


#: AC-3 remediation pointer for Rule C — the regression guard.
_RULE_C_REMEDIATION: str = (
    "(per Story 8.6 AC-3 Rule C: NO module under loud_fail_harness/ may reintroduce "
    "the _can_dispatch_inline function or callsite — Story 8.6 superseded it with "
    "no_destructive_resume_guard.can_dispatch(). Remediation: remove the inline "
    "and route the dispatch decision through the canonical guard.)"
)


# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class LintFinding(BaseModel):
    """A single AC-3 structural-rule violation.

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable JSON dumps. Mirrors
    :class:`pluggability_gate.CrossReferenceFinding`'s shape.

    Attributes:
        file_path: Path to the offending file. Carried as a
            :class:`pathlib.Path` for renderer-side relative-path
            normalization.
        line_number: 1-indexed line number of the offending AST node;
            matches ``ast.AST.lineno``. For Rule A (import-missing), the
            line number is 1 (the absent import would land at the top
            of the file).
        rule: One of the three AC-3 rule discriminators.
        diagnostic: Human-readable message naming the violation +
            remediation hint.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    file_path: pathlib.Path
    line_number: int
    rule: Literal["A-import-missing", "B-callsite-missing", "C-inline-reintroduced"]
    diagnostic: str


class LintResult(BaseModel):
    """Aggregate gate result.

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable JSON dumps.

    Attributes:
        findings: All findings, ordered by ``(file_path, line_number,
            rule)`` for byte-stable output.
        governed_modules_scanned: The closed allowlist of governed
            module file-stems scanned. Tests assert this equals
            :data:`_GOVERNED_MODULES`.
    """

    model_config = ConfigDict(frozen=True)

    findings: tuple[LintFinding, ...]
    governed_modules_scanned: tuple[str, ...]


# --------------------------------------------------------------------------- #
# AST-walking primitives                                                      #
# --------------------------------------------------------------------------- #


def _parse_module(file_path: pathlib.Path) -> ast.Module:
    """Read + parse the Python source at ``file_path``. Raises
    :class:`RuntimeError` on UTF-8 / OSError / SyntaxError so callers
    surface them as harness-level errors (exit 2)."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"file not UTF-8: {file_path}") from exc
    except OSError as exc:
        raise RuntimeError(f"file unreadable: {file_path}") from exc
    try:
        return ast.parse(text, filename=str(file_path))
    except SyntaxError as exc:
        raise RuntimeError(f"file not parseable as Python: {file_path}: {exc}") from exc


def _has_canonical_import(tree: ast.Module) -> bool:
    """Rule A predicate: a top-level
    ``from .no_destructive_resume_guard import ... can_dispatch ...``
    is present."""
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != _GUARD_MODULE_NAME or node.level != 1:
            continue
        for alias in node.names:
            if alias.name == _CAN_DISPATCH_NAME:
                return True
    return False


def _function_calls_can_dispatch(func: ast.FunctionDef) -> bool:
    """Rule B predicate: at least one descendant ``ast.Call`` whose
    ``func`` is either ``ast.Name(id="can_dispatch")`` OR
    ``ast.Attribute(attr="can_dispatch")``."""
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name) and callee.id == _CAN_DISPATCH_NAME:
            return True
        if (
            isinstance(callee, ast.Attribute)
            and callee.attr == _CAN_DISPATCH_NAME
        ):
            return True
    return False


def _find_dispatch_decision_functions(
    tree: ast.Module,
) -> list[ast.FunctionDef]:
    """Return every top-level ``ast.FunctionDef`` whose ``name`` is in
    the :data:`_DISPATCH_DECISION_FUNCTIONS` set. Top-level only:
    nested functions / methods are out of scope."""
    return [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in _DISPATCH_DECISION_FUNCTIONS
    ]


def _find_inline_reintroductions(
    tree: ast.Module,
) -> list[ast.AST]:
    """Rule C predicate: walk the AST and return every offending node
    (FunctionDef of the forbidden name OR Call whose func resolves to
    the forbidden name). Multiple findings per file are emitted (do-not-
    bail-after-first per the pluggability-gate precedent)."""
    offenders: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == _FORBIDDEN_INLINE_NAME:
            offenders.append(node)
            continue
        if isinstance(node, ast.Call):
            callee = node.func
            if (
                isinstance(callee, ast.Name)
                and callee.id == _FORBIDDEN_INLINE_NAME
            ):
                offenders.append(node)
            elif (
                isinstance(callee, ast.Attribute)
                and callee.attr == _FORBIDDEN_INLINE_NAME
            ):
                offenders.append(node)
    return offenders


# --------------------------------------------------------------------------- #
# Per-rule scanners                                                           #
# --------------------------------------------------------------------------- #


def _scan_rule_a(
    file_path: pathlib.Path, tree: ast.Module, module_stem: str
) -> list[LintFinding]:
    """Apply Rule A — import-missing. Only fires for modules in
    :data:`_RULE_A_MODULES`."""
    if module_stem not in _RULE_A_MODULES:
        return []
    if _has_canonical_import(tree):
        return []
    return [
        LintFinding(
            file_path=file_path,
            line_number=1,
            rule="A-import-missing",
            diagnostic=(
                f"{module_stem}: missing top-level import of can_dispatch "
                f"from no_destructive_resume_guard — add "
                f"`from .no_destructive_resume_guard import can_dispatch`. "
                f"{_RULE_A_REMEDIATION}"
            ),
        )
    ]


def _scan_rule_b(
    file_path: pathlib.Path, tree: ast.Module, module_stem: str
) -> list[LintFinding]:
    """Apply Rule B — callsite-missing. Walks every dispatch-decision
    function in the module and asserts each contains at least one call
    to ``can_dispatch``."""
    findings: list[LintFinding] = []
    for func in _find_dispatch_decision_functions(tree):
        if _function_calls_can_dispatch(func):
            continue
        findings.append(
            LintFinding(
                file_path=file_path,
                line_number=func.lineno,
                rule="B-callsite-missing",
                diagnostic=(
                    f"{module_stem}::{func.name}: function performs dispatch "
                    f"decision but does NOT call can_dispatch() — "
                    f"wire the canonical guard. {_RULE_B_REMEDIATION}"
                ),
            )
        )
    return findings


def _scan_rule_c(
    file_path: pathlib.Path, tree: ast.Module
) -> list[LintFinding]:
    """Apply Rule C — inline-reintroduced. Walks the entire AST for
    forbidden FunctionDef + Call nodes."""
    findings: list[LintFinding] = []
    for offender in _find_inline_reintroductions(tree):
        offender_name = (
            offender.name
            if isinstance(offender, ast.FunctionDef)
            else _FORBIDDEN_INLINE_NAME
        )
        # FunctionDef and Call nodes both carry ``lineno``; the
        # _find_inline_reintroductions narrowing to those two kinds
        # makes the attribute-access safe but mypy's view of the union
        # via ast.AST drops the attribute. ``getattr`` keeps the
        # access strict-clean without a precarious cast.
        offender_lineno = getattr(offender, "lineno", 1)
        findings.append(
            LintFinding(
                file_path=file_path,
                line_number=offender_lineno,
                rule="C-inline-reintroduced",
                diagnostic=(
                    f"{file_path.name}: forbidden re-introduction of "
                    f"inline {offender_name} — Story 8.6 superseded this "
                    f"with no_destructive_resume_guard.can_dispatch(). "
                    f"{_RULE_C_REMEDIATION}"
                ),
            )
        )
    return findings


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #


def run_no_destructive_resume_lint(harness_root: pathlib.Path) -> LintResult:
    """Execute the gate over the harness substrate rooted at ``harness_root``.

    ``harness_root`` MUST point at the loud-fail-harness package root
    (i.e., the directory containing ``src/loud_fail_harness/``). The
    gate scans:

        * ``harness_root / "src/loud_fail_harness/<governed>.py"`` for
          each member of :data:`_GOVERNED_MODULES` (Rules A and B);
        * every ``.py`` file under ``harness_root / "src/loud_fail_harness/"``
          recursively for Rule C.

    Raises :class:`RuntimeError` if any governed module is missing OR
    any scanned file is unreadable / non-UTF-8 / non-parseable.
    """
    src_dir = harness_root / "src" / "loud_fail_harness"
    findings: list[LintFinding] = []

    # Governed-modules pass: Rules A and B.
    for stem in _GOVERNED_MODULES:
        target = src_dir / f"{stem}.py"
        if not target.is_file():
            raise RuntimeError(
                f"governed module not found: {target} "
                f"(expected per Story 8.6 AC-3 _GOVERNED_MODULES)"
            )
        tree = _parse_module(target)
        findings.extend(_scan_rule_a(target, tree, stem))
        findings.extend(_scan_rule_b(target, tree, stem))

    # Rule C pass: every .py file under src/loud_fail_harness/ (recursive).
    # Rule C's regression-guard scope per AC-3 is the harness substrate
    # source tree only. The forbidden name is a STRING literal in this
    # gate's source (``_FORBIDDEN_INLINE_NAME = "_can_dispatch_inline"``);
    # Python's AST treats it as a Constant node, NOT a Name(id=...) or
    # FunctionDef(name=...) node — so this gate's source does not self-
    # fire. Tests under ``tests/`` are outside ``src_dir`` by construction
    # and therefore out of scope.
    for py_file in sorted(src_dir.rglob("*.py")):
        tree = _parse_module(py_file)
        findings.extend(_scan_rule_c(py_file, tree))

    findings.sort(
        key=lambda f: (str(f.file_path), f.line_number, f.rule)
    )
    return LintResult(
        findings=tuple(findings),
        governed_modules_scanned=_GOVERNED_MODULES,
    )


# --------------------------------------------------------------------------- #
# Formatter                                                                   #
# --------------------------------------------------------------------------- #


def _display_path(
    path: pathlib.Path, harness_root: pathlib.Path | None = None
) -> str:
    """Render ``path`` relative to harness_root if possible; absolute otherwise.

    Mirrors :func:`pluggability_gate._display_path`'s shape so canonical
    CI invocations produce stable diff-friendly relative paths and
    ``tmp_path``-rooted invocations fall back to absolute.
    """
    if harness_root is None:
        return str(path.resolve())
    try:
        return str(path.resolve().relative_to(harness_root.resolve()))
    except ValueError:
        return str(path.resolve())


def format_findings(result: LintResult, *, harness_root: str) -> str:
    """Render a :class:`LintResult` for stdout.

    Mirrors :func:`pluggability_gate.format_findings`'s shape: header
    naming inputs + per-finding finding lines + summary. The summary line
    matches ``no-destructive-resume-lint: <N> findings (3 governed modules
    scanned)`` so AC-3's success-line shape is satisfied on the zero-
    findings case.
    """
    lines: list[str] = []
    lines.append("No-destructive-resume lint gate (story 8.6; NFR-R7)")
    lines.append(f"  harness root: {harness_root}")
    lines.append(
        f"  governed modules: {list(result.governed_modules_scanned)!r}"
    )
    lines.append("")

    harness_root_path = pathlib.Path(harness_root) if harness_root else None
    for finding in result.findings:
        rendered_path = _display_path(finding.file_path, harness_root=harness_root_path)
        message = (
            f"no-destructive-resume-lint: {rendered_path}:"
            f"{finding.line_number} {finding.rule} {finding.diagnostic}"
        )
        lines.append(message)
        lines.append("")

    if not result.findings:
        lines.append(
            f"no-destructive-resume-lint: 0 findings "
            f"({len(result.governed_modules_scanned)} governed modules scanned)"
        )
    else:
        lines.append(
            f"no-destructive-resume-lint: {len(result.findings)} findings"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="no-destructive-resume-lint",
        description=(
            "No-destructive-resume CI lint gate (story 8.6; NFR-R7). "
            "Asserts Stories 8.1 / 8.2 / 8.3 ALL route dispatch decisions "
            "through no_destructive_resume_guard.can_dispatch() per "
            "epics.md:3389-3393. AST-based scanner (parallel in shape to "
            "pluggability-gate but operating on Python source instead of "
            "markdown). Three structural rules: A-import-missing, "
            "B-callsite-missing, C-inline-reintroduced."
        ),
    )
    parser.add_argument(
        "--harness-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to the loud-fail-harness package root (default: "
            "<repo-root>/tools/loud-fail-harness/). Test-injection flag; "
            "CI invocations omit it."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point per AC-3.

    Exit codes:
        * ``0`` — ``LintResult.findings == ()`` (full pass).
        * ``1`` — any finding present (invariant violation).
        * ``2`` — harness-level error (governed module missing,
          unreadable, non-UTF-8, or non-parseable).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    harness_root: pathlib.Path
    if args.harness_root is None:
        try:
            repo_root = find_repo_root()
        except RuntimeError as exc:
            print(
                f"no-destructive-resume-lint: harness-level error: {exc}",
                file=sys.stderr,
            )
            return 2
        harness_root = repo_root / "tools" / "loud-fail-harness"
    else:
        harness_root = args.harness_root

    if not (harness_root / "src" / "loud_fail_harness").is_dir():
        print(
            "no-destructive-resume-lint: harness-level error: "
            f"src/loud_fail_harness/ not found under {harness_root!s}",
            file=sys.stderr,
        )
        return 2

    try:
        result = run_no_destructive_resume_lint(harness_root)
    except RuntimeError as exc:
        print(
            f"no-destructive-resume-lint: harness-level error: {exc}",
            file=sys.stderr,
        )
        return 2

    print(
        format_findings(
            result,
            harness_root=_display_path(harness_root, harness_root=None),
        )
    )

    return 1 if result.findings else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
