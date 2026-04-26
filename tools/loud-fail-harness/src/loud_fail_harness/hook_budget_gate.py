"""Hook-budget CI gate (story 1.9). FR60 (≤3 hooks count) + FR61 (≤20 lines bash per hook).

Architectural placement (story 1.8 precedent — story 1.9 Dev Notes "Do not add
a 6th substrate component slot"): this module is structurally a sibling of the
five substrate-component modules (envelope_validator, event_validator,
reconciler, enumeration_check, fixture_coverage) and the prior CI gate
(fr33_fixture_gate, story 1.8) but it is **NOT a sixth substrate component**.
ADR-003 Consequence 1 enumerates exactly five substrate components
(architecture.md line 311-315); this gate is a CI **gate** that enforces FR60
+ FR61 against the inner repo's ``hooks/`` directory. The substrate-component
count stays at FIVE; the harness gate count grows to SEVEN at this story's
landing (envelope-validator, event-validator, dependencies-validator,
enumeration-check, fixture-coverage, fr33-fixture-gate, hook-budget-gate).

What this gate enforces:
    * **FR60** (PRD line 895; architecture.md line 1031) — ≤3 hooks budget at
      the top level of ``hooks/``. "Any PR adding a 4th hook without removing
      an existing one fails CI." Per PRD line 729, "the ≤3 hook budget is NOT
      revisitable as a relaxation; budget may be renegotiated only by replacing
      one hook with another."
    * **FR61** (PRD line 896; architecture.md line 1031) — ≤20 effective lines
      of bash per hook script. The counting rule is documented canonically in
      ``tools/loud-fail-harness/docs/hook-counting-rules.md`` and implemented in
      :func:`count_effective_lines`; the doc-vs-implementation seam is enforced
      by AC-9's ``test_counting_rule_doc_in_sync``.

NFR-S4 rationale (PRD line 972 — hook-script trust model):
    "Hook scripts are part of the installed Automator (plugin or git-clone);
    they run with the user's shell privileges. The 20-lines-of-bash heuristic
    + CI enforcement bounds the hook attack surface." This gate IS the "CI
    enforcement" the NFR references — without it, the 20-line bound would be
    review-discipline only.

Cross-story seam contract (1.9 ↔ 2.7):
    Story 2.7 lands the canonical three hook scripts at
    ``hooks/subagent-stop.sh`` (FR58 — Dev commit handler),
    ``hooks/stop.sh`` (FR59 — PR bundle assembly),
    ``hooks/session-start.sh`` (FR46 — resumability) per architecture.md lines
    1073-1076. This gate is invariant-pinned BEFORE 2.7 lands so adding the
    canonical 3-hook set at 2.7's landing requires NO gate edit. The
    baseline-zero pass (no ``hooks/`` directory at story 1.9's landing time) is
    the gate's correct posture: 0 hooks ≤ 3 (FR60 satisfied), 0 over-budget
    files (FR61 satisfied), exit 0.

Loud-fail discipline (Pattern 5):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — full pass: ``count_violation`` empty AND ``line_violation`` empty.
            Includes the baseline-zero case (``hooks/`` does not exist OR
            contains zero ``.sh`` files).
        1 — invariant violation: ``count_violation`` non-empty OR
            ``line_violation`` non-empty (or both). Recoverable by EITHER
            (a) removing one or more hooks to reach ≤3, OR (b) reducing the
            over-budget hook script's effective line count to ≤20, OR (c)
            replacing one hook with another (per PRD line 729 — the budget is
            not revisitable as a relaxation).
        2 — harness-level error: ``hooks/`` exists but is unreadable
            (permission-denied), OR a discovered ``.sh`` file is unreadable,
            OR a discovered ``.sh`` file is non-UTF-8. Practitioners
            disambiguate via the stderr prefix ``"harness-level error: ..."``.

    Mixed-finding precedence (AC-5 final clause): when both
    ``count_violation`` AND ``line_violation`` are non-empty, exit 1 fires
    (both diagnostics print to stdout; neither finding promotes to exit 2 —
    FR60 + FR61 are equivalent invariant-tier signals). This is unlike
    ``fr33_fixture_gate``'s harness-bug-wins mixed-precedence rule: there
    ``harness_bug`` is higher-severity because it suspects gate correctness;
    here both finding classes are equally severe build-failers.

Sensor-not-advisor (PRD-level invariant):
    The gate REPORTS over-budget hook count and over-budget hook files with
    remediation pointers; it does NOT auto-edit hook scripts, suggest specific
    cuts, rewrite the counting rule, or add ``.sh`` files to ``hooks/``. Same
    posture as 1.4 / 1.5 / 1.6 / 1.7 / 1.8.

Cross-component reuse posture (story 1.9 do-not-do matrix
"do not import from other validator/gate modules"):
    * :func:`loud_fail_harness._shared.find_repo_root` — REUSED for
      default-path resolution (the canonical ``hooks/`` directory under
      the inner repo root). NO other substrate-component imports — hook
      discovery is a directory glob, not a schema- or fixture-driven
      operation.

Counting rule (canonical algorithm — co-versioned with hook-counting-rules.md):

    See :func:`count_effective_lines`. The rule has TWO authoritative forms:

        1. Machine-readable — ``count_effective_lines`` in this module.
        2. Human-readable — the prose rule in
           ``tools/loud-fail-harness/docs/hook-counting-rules.md``.

    Both forms MUST be byte-for-byte equivalent in their behavior. AC-9's
    ``test_counting_rule_doc_in_sync`` test parses the doc's "Worked
    examples" subsection (snippet → expected count pairs) and runs each
    snippet through ``count_effective_lines``; the test fails LOUDLY if any
    pair drifts.

Determinism (parallel to 1.4 / 1.5 / 1.6 / 1.7 / 1.8):
    * ``discover_hooks`` returns a list sorted by ``pathlib.Path.name`` —
      explicit sort, never relying on filesystem iteration order.
    * ``GateResult.passing`` is sorted by ``file_name``;
      ``GateResult.line_violation`` is sorted by
      ``(file_name, effective_line_count)``;
      ``GateResult.count_violation`` is at most one entry.
    * ``GateResult`` is a Pydantic v2 frozen model with field-declaration-
      order JSON serialization (load-bearing for byte-stable
      ``model_dump_json()``).
    * No use of ``set`` for stdout-observed collections.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Sequence
from typing import Optional

from pydantic import BaseModel, ConfigDict

from loud_fail_harness._shared import find_repo_root

#: FR60 architectural constant. The ≤3 hooks budget is non-revisitable as a
#: relaxation per PRD line 729; budget may be renegotiated only by replacing
#: one hook with another. NOT exposed as a CLI flag — the budget is an
#: architectural invariant, not a runtime knob.
_HOOK_COUNT_BUDGET: int = 3

#: FR61 architectural constant. The ≤20 effective-line bound is the hook-
#: script-trust-model attack-surface bound (NFR-S4, PRD line 972). NOT
#: exposed as a CLI flag — same reasoning as ``_HOOK_COUNT_BUDGET``.
_HOOK_LINE_BUDGET: int = 20

#: Path to the canonical counting-rule reference, embedded in module
#: docstring AND CLI ``--help`` output AND ``line_violation`` diagnostic
#: prose so practitioners debugging a CI failure find the rule's prose form
#: within ONE click of the gate's CI log.
_COUNTING_RULE_DOC_PATH: str = (
    "tools/loud-fail-harness/docs/hook-counting-rules.md"
)

#: AC-6 row-1 remediation pointer (count_violation). Verbatim per the
#: validator-contract table in story 1.9's Dev Notes.
_COUNT_VIOLATION_REMEDIATION: str = (
    "(per FR60 + PRD line 729: the ≤3 hook budget is NOT revisitable as a "
    "relaxation; remove one or more hooks to reach ≤3, OR replace one hook "
    "with another. Adding a 4th hook outside the three architecturally "
    "defined — SubagentStop, Stop, SessionStart — would violate the "
    "architecture per architecture.md line 1073-1076 + PRD line 644.)"
)

#: AC-6 row-2 remediation pointer (line_violation). Verbatim per the
#: validator-contract table in story 1.9's Dev Notes.
_LINE_VIOLATION_REMEDIATION: str = (
    "(per FR61 + NFR-S4: the 20-line bound is the hook-script-trust-model "
    "attack-surface bound; reduce the script to ≤20 effective lines OR "
    "factor logic into a non-hook artifact. Counting rule excludes shebang, "
    "blank lines, and comment-only lines; see hook-counting-rules.md for "
    "examples.)"
)


class Reference(BaseModel):
    """A passing hook-file reference (file_name + effective_line_count).

    Frozen for hashability + determinism; field declaration order is load-
    bearing for byte-stable JSON dumps. Mirrors story 1.7 / 1.8's
    :class:`Reference` shape; declared locally per the within-module-only-
    coupling discipline (DO NOT import cross-module Pydantic models).
    """

    model_config = ConfigDict(frozen=True)

    file_name: str
    effective_line_count: int


class CountFinding(BaseModel):
    """A FR60 count-budget violation finding.

    The bucket is logically a singleton — there is one count, it's either
    over budget or not. Discovered names are enumerated in full so the
    diagnostic is debuggable (practitioner sees the entire over-budget set
    at a glance).

    The ``budget`` field is a constant default (``3``); it is stored on the
    model so the renderer accesses ``finding.budget`` directly and so
    persisted finding records are self-describing for post-hoc audits. NOT
    constructor-injected: callers construct
    ``CountFinding(discovered_count=N, discovered_names=names)`` and the
    budget defaults to 3.
    """

    model_config = ConfigDict(frozen=True)

    discovered_count: int
    discovered_names: list[str]
    budget: int = _HOOK_COUNT_BUDGET


class LineFinding(BaseModel):
    """A FR61 per-file line-budget violation finding.

    One ``LineFinding`` per over-budget hook file; the gate emits all of
    them (do-not-bail-after-first within the line-violation bucket). Sorted
    by ``(file_name, effective_line_count)`` at the gate level.

    The ``budget`` field is a constant default (``20``); same posture as
    :class:`CountFinding.budget`.
    """

    model_config = ConfigDict(frozen=True)

    file_name: str
    effective_line_count: int
    budget: int = _HOOK_LINE_BUDGET


class GateResult(BaseModel):
    """Triple-classification hook-budget gate output.

    * ``passing`` — hook files under both budgets. One :class:`Reference`
      per file; sorted by ``file_name``. Empty when ``hooks/`` does not
      exist or has zero ``.sh`` files.
    * ``count_violation`` — at most one :class:`CountFinding` (the bucket
      is logically a singleton). Empty when discovered count ≤ 3; length 1
      when discovered count > 3.
    * ``line_violation`` — one :class:`LineFinding` per over-budget hook
      file. Sorted by ``(file_name, effective_line_count)``.

    Field declaration order matches Pydantic v2's JSON-serialization order
    (load-bearing for byte-stable ``model_dump_json()``; parallel to 1.4 /
    1.5 / 1.6 / 1.7 / 1.8).

    Classification completeness: every discovered hook file appears in
    exactly one of ``passing`` (under-budget) or ``line_violation``
    (over-budget). The ``count_violation`` bucket is orthogonal — it fires
    regardless of any individual file's line count when the total count
    exceeds 3.
    """

    model_config = ConfigDict(frozen=True)

    passing: list[Reference]
    count_violation: list[CountFinding]
    line_violation: list[LineFinding]


def discover_hooks(hooks_dir: pathlib.Path) -> list[pathlib.Path]:
    """Return a sorted list of ``.sh`` files at the top level of ``hooks_dir``.

    Top-level only: ``hooks/subdir/foo.sh`` is NOT discovered. Per
    architecture.md line 1073-1076 the canonical layout is flat. Recursive
    discovery would (a) silently allow practitioners to "hide" hooks in
    subdirectories to bypass the count budget, (b) surface unrelated
    helper scripts that are never invoked as Claude Code hooks. The
    top-level-only rule mirrors Claude Code's hook-discovery behavior
    (hooks are referenced from ``settings.json`` by exact path).

    Returns ``[]`` if ``hooks_dir`` does not exist OR exists but contains
    zero matching ``.sh`` files (the baseline-zero pass case at story
    1.9's landing time, before story 2.7 creates the directory). Raises
    ``OSError`` only on permission-denied or other filesystem errors
    distinct from ``FileNotFoundError`` — the caller surfaces those as
    harness-level errors (exit 2).
    """
    if not hooks_dir.exists():
        return []
    discovered: list[pathlib.Path] = []
    for entry in hooks_dir.glob("*.sh"):
        # Defensive: glob may include directories whose names happen to
        # end in `.sh` on some filesystems. The top-level-only rule is
        # also enforced by `glob` (vs. `rglob`).
        if entry.is_file():
            discovered.append(entry)
    discovered.sort(key=lambda p: p.name)
    return discovered


def count_effective_lines(path: pathlib.Path) -> int:
    """Count effective bash lines per the FR61 rule.

    Skips:
        * line 1 if it starts with the literal ``#!`` (shebang skip — line-1-only)
        * blank lines (``str.strip() == ""``)
        * comment-only lines (``str.strip().startswith("#")``)

    Counts everything else, including ``code # inline comment`` lines,
    continuation backslashes, heredoc bodies, control-flow keywords, and
    closing braces.

    Co-versioned with ``tools/loud-fail-harness/docs/hook-counting-rules.md``.
    The doc is the human-readable canonical form; this function is the
    machine-readable implementation. AC-9's
    ``test_counting_rule_doc_in_sync`` enforces the seam.

    Raises ``RuntimeError`` if the file is unreadable (``OSError``) or
    not valid UTF-8 (``UnicodeDecodeError``); the caller surfaces these
    as harness-level errors (exit 2).
    """
    try:
        # utf-8-sig strips the UTF-8 BOM (﻿) if present so that a BOM-prefixed
        # shebang (﻿#!/bin/bash) is still correctly skipped by the line-1 check.
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"hook file not UTF-8: {path}") from exc
    except OSError as exc:
        raise RuntimeError(f"hook file unreadable: {path}") from exc

    lines = text.splitlines()
    count = 0
    for idx, line in enumerate(lines):
        if idx == 0 and line.startswith("#!"):
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        count += 1
    return count


def run_hook_budget_gate(hooks_dir: pathlib.Path) -> GateResult:
    """Execute the gate over ``hooks_dir`` and produce a :class:`GateResult`.

    Discovers hooks, line-counts each, partitions results into the three
    buckets per AC-4. Never bails after the first finding within a
    category (parallel to 1.5 / 1.6 / 1.7 / 1.8).

    Raises ``RuntimeError`` if any discovered ``.sh`` file is unreadable
    or non-UTF-8 (propagated from :func:`count_effective_lines`); the
    caller surfaces this as exit 2. ``OSError`` from a permission-denied
    ``hooks_dir`` is also propagated for the same reason.
    """
    discovered = discover_hooks(hooks_dir)

    passing: list[Reference] = []
    line_violation: list[LineFinding] = []
    count_violation: list[CountFinding] = []

    for hook_path in discovered:
        effective = count_effective_lines(hook_path)
        if effective > _HOOK_LINE_BUDGET:
            line_violation.append(
                LineFinding(
                    file_name=hook_path.name,
                    effective_line_count=effective,
                )
            )
        else:
            passing.append(
                Reference(
                    file_name=hook_path.name,
                    effective_line_count=effective,
                )
            )

    if len(discovered) > _HOOK_COUNT_BUDGET:
        count_violation.append(
            CountFinding(
                discovered_count=len(discovered),
                discovered_names=[p.name for p in discovered],
            )
        )

    passing.sort(key=lambda r: r.file_name)
    line_violation.sort(
        key=lambda lf: (lf.file_name, lf.effective_line_count)
    )

    return GateResult(
        passing=passing,
        count_violation=count_violation,
        line_violation=line_violation,
    )


def format_findings(result: GateResult, *, hooks_dir: str) -> str:
    """Render a :class:`GateResult` for stdout.

    Header naming inputs; passing-summary line; per-bucket finding lists
    with AC-6 distinct-shape diagnostics; footer Summary line. Mirrors
    the "name the offending entity + remediation pointer" discipline
    from 1.5 / 1.6 / 1.7 / 1.8. The Summary footer's bucket order
    matches :class:`GateResult`'s field declaration order.
    """
    lines: list[str] = []
    lines.append("Hook-budget gate (story 1.9; FR60 + FR61)")
    lines.append(f"  hooks dir:     {hooks_dir}")
    lines.append(f"  counting rule: {_COUNTING_RULE_DOC_PATH}")
    lines.append("")

    has_findings = bool(result.count_violation or result.line_violation)
    passing_line = (
        f"OK: {len(result.passing)} passing hook(s) under budget"
    )
    if has_findings:
        passing_line += " (but findings below)"
    lines.append(passing_line + ".")

    if result.count_violation:
        lines.append("")
        lines.append(
            f"FAIL: {len(result.count_violation)} count-violation finding(s)."
        )
        for cf in result.count_violation:
            names_csv = ", ".join(cf.discovered_names)
            message = (
                f"Hook count exceeds budget: discovered "
                f"{cf.discovered_count} .sh files at top level of hooks/ "
                f"(budget: {cf.budget} per FR60). Discovered hooks: "
                f"{names_csv}."
            )
            lines.append(f"  {message}")
            lines.append(f"  {_COUNT_VIOLATION_REMEDIATION}")

    if result.line_violation:
        lines.append("")
        lines.append(
            f"FAIL: {len(result.line_violation)} line-violation finding(s)."
        )
        for lf in result.line_violation:
            message = (
                f"Hook script exceeds line budget: {lf.file_name} has "
                f"{lf.effective_line_count} effective lines (budget: "
                f"{lf.budget} per FR61). Counting rule per "
                f"{_COUNTING_RULE_DOC_PATH}."
            )
            lines.append(f"  {message}")
            lines.append(f"  {_LINE_VIOLATION_REMEDIATION}")

    lines.append("")
    lines.append(
        f"Summary: {len(result.passing)} passing hook(s), "
        f"{len(result.count_violation)} count-violation finding(s), "
        f"{len(result.line_violation)} line-violation finding(s)."
    )
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hook-budget-gate",
        description=(
            "Hook-budget CI gate (story 1.9). Enforces FR60 (≤3 hooks at "
            "the top level of hooks/) and FR61 (≤20 effective lines of "
            "bash per hook script). Counting rule: "
            f"{_COUNTING_RULE_DOC_PATH}. ADR-003 + FR60 + FR61 + NFR-S4."
        ),
    )
    parser.add_argument(
        "--hooks-dir",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to hooks/ directory (default: <repo-root>/hooks/). "
            "Test-injection flag; CI invocations omit it."
        ),
    )
    return parser


def _display_path(
    path: pathlib.Path, repo_root: Optional[pathlib.Path] = None
) -> str:
    """Render ``path`` relative to repo root if possible; absolute otherwise.

    Mirrors the pattern in ``fixture_coverage._display_path`` /
    ``fr33_fixture_gate._display_path`` so canonical CI invocations
    produce stable diff-friendly relative paths and ``tmp_path``
    invocations fall back to absolute (still informative in stdout).
    """
    try:
        rr = repo_root if repo_root is not None else find_repo_root()
        return str(path.resolve().relative_to(rr.resolve()))
    except (RuntimeError, ValueError):
        return str(path.resolve())


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    hooks_dir: pathlib.Path
    repo_root: Optional[pathlib.Path] = None
    if args.hooks_dir is None:
        try:
            repo_root = find_repo_root()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        hooks_dir = repo_root / "hooks"
    else:
        hooks_dir = args.hooks_dir

    # Guard the readability of `hooks_dir` BEFORE the gate runs so a
    # permission-denied directory surfaces as exit 2 with a precise
    # message — distinct from `discover_hooks`'s graceful-absence path
    # (returning [] for non-existent dirs is exit 0, not exit 2).
    if hooks_dir.exists():
        try:
            # Triggering a directory scan is the cheapest readability check;
            # we discard the iterator to avoid materializing entries twice.
            next(iter(hooks_dir.iterdir()), None)
        except PermissionError as exc:
            print(
                "harness-level error: hooks/ directory unreadable: "
                f"{hooks_dir}: {exc}",
                file=sys.stderr,
            )
            return 2
        except OSError as exc:
            print(
                "harness-level error: hooks/ directory unreadable: "
                f"{hooks_dir}: {exc}",
                file=sys.stderr,
            )
            return 2

    try:
        result = run_hook_budget_gate(hooks_dir)
    except RuntimeError as exc:
        # Loud-fail (Pattern 5): unreadable / non-UTF-8 hook files surface
        # as exit 2 with a `harness-level error:` stderr prefix mirroring
        # 1.5 / 1.6 / 1.7 / 1.8.
        print(f"harness-level error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        # Defensive: a permission-denied iteration mid-discover would
        # propagate here even after the upfront iterdir check above (e.g.
        # a TOCTOU window). Surface identically to the upfront check.
        print(
            "harness-level error: hooks/ directory unreadable: "
            f"{hooks_dir}: {exc}",
            file=sys.stderr,
        )
        return 2

    print(
        format_findings(
            result,
            hooks_dir=_display_path(hooks_dir, repo_root=repo_root),
        )
    )

    # Mixed-precedence rule (AC-5 final clause): both finding classes are
    # equivalent invariant-tier signals; either fires exit 1; neither
    # promotes to exit 2.
    if result.count_violation or result.line_violation:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
