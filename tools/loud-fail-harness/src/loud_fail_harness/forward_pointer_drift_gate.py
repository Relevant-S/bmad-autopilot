"""Forward-pointer-drift unified gate — Story 22.4 (H6 conditional landing).

Build-time gate (NOT a runtime marker — like sibling gates 24.2 / 24.3, it
emits ``LintFinding``s + a nonzero exit, never a persisted run-state marker).
Joins the ``deferred-work.md`` carry surface × ``sprint-status.yaml``
``done`` ground truth and fails when a still-pending forward-pointer binds a
target story that has already reached ``done`` (the flip that was never
performed — stale drift). Mirrors :mod:`no_destructive_resume_lint` /
:mod:`done_story_review_ledger_gate` in shape: ``LintFinding`` / ``LintResult``
frozen models + a byte-stable ``format_findings`` + a ``main`` exiting ``0``
(clean) / ``1`` (findings) / ``2`` (harness-level error). The pure parsers
live in the sibling library :mod:`forward_pointer_drift`.

## The rule (R1 — ``stale-forward-pointer``)

For each forward-pointer parsed from the carry surface (a structured
``<!-- forward-pointer: … -->`` annotation or a closed-set inline carry-
binding — see :mod:`forward_pointer_drift`) whose status is still pending,
emit a finding when its ``target_key`` resolves to a ``done`` story. The
``diagnostic`` names the stale pointer + a flip-or-reroute remediation hint
(NFR-O5).

## CI posture (the Story 24.3 / story-doc-validator precedent)

The governed surface (``deferred-work.md`` + ``sprint-status.yaml``) lives in
the OUTER planning workspace (``_bmad-output/implementation-artifacts/``),
which is NOT present in the inner-repo CI working-directory
(``tools/loud-fail-harness``). So — exactly like ``done-story-review-ledger-
gate`` (24.3) and ``story-doc-validator`` (1.10b) — the gate is exercised in
inner CI via ``pytest`` over synthetic fixtures, and its real teeth over the
live workspace are a Dev/SM-invoked ``uv run forward-pointer-drift-gate
--carry-surface … --sprint-status …``. No new ``ci.yml``-over-real-
``_bmad-output/`` step is added (none is possible inside the inner repo).
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Sequence
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from .forward_pointer_drift import (
    CarryPointer,
    ForwardPointerDriftError,
    iter_carry_pointers,
    iter_done_story_keys,
    resolve_done_target,
)

__all__ = [
    "LintFinding",
    "LintResult",
    "evaluate_forward_pointer_drift",
    "format_findings",
    "main",
    "run_forward_pointer_drift_gate",
]

#: Default discovery path for the implementation-artifacts dir, relative to a
#: workspace root walked up from cwd. The inner-repo CI never resolves this
#: (the artifacts are absent there); CI invocations come through pytest with
#: explicit paths.
_ARTIFACTS_RELATIVE: Final[tuple[str, ...]] = (
    "_bmad-output",
    "implementation-artifacts",
)
_CARRY_SURFACE_NAME: Final[str] = "deferred-work.md"
_SPRINT_STATUS_NAME: Final[str] = "sprint-status.yaml"


class LintFinding(BaseModel):
    """A single stale-forward-pointer violation.

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable dumps. Mirrors
    :class:`done_story_review_ledger_gate.LintFinding`'s shape.

    Attributes:
        source_path: The carry-surface file the stale pointer was parsed from
            (carried as :class:`pathlib.Path` for renderer-side relative-path
            normalization).
        line_number: 1-indexed line of the offending forward-pointer.
        rule: The single rule discriminator (left as a ``Literal`` so a future
            rule extension is a one-token edit, not a type change).
        diagnostic: Human-readable message naming the stale pointer + the
            ``done`` target it binds + remediation hint (NFR-O5).
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    source_path: pathlib.Path
    line_number: int
    rule: Literal["stale-forward-pointer"]
    diagnostic: str


class LintResult(BaseModel):
    """Aggregate gate result.

    Frozen for determinism; field declaration order is load-bearing for
    byte-stable dumps.

    Attributes:
        findings: All findings, ordered by ``(source_path, line_number,
            rule)``.
        done_stories_scanned: The ``done`` story keys joined against, in
            sprint-status declaration order.
        carry_pointers_scanned: Count of forward-pointers parsed from the
            carry surface (the gate's non-vacuity witness in the summary line).
    """

    model_config = ConfigDict(frozen=True)

    findings: tuple[LintFinding, ...]
    done_stories_scanned: tuple[str, ...]
    carry_pointers_scanned: int


def evaluate_forward_pointer_drift(
    *,
    carry_pointers: Sequence[CarryPointer],
    done_story_keys: Sequence[str],
    carry_surface_path: pathlib.Path,
) -> LintResult:
    """Apply rule R1 across the parsed forward-pointers.

    Resolves each pointer's ``target_key`` against the ``done`` set; emits a
    ``stale-forward-pointer`` finding (the target landed but the pointer was
    never flipped) for each pending pointer that binds a ``done`` story.
    Findings are sorted by ``(source_path, line_number, rule)`` for byte-stable
    CI diffs.
    """
    done_set = frozenset(done_story_keys)
    findings: list[LintFinding] = []
    for pointer in carry_pointers:
        resolved = resolve_done_target(pointer.target_key, done_set)
        if resolved is None:
            continue
        findings.append(
            LintFinding(
                source_path=carry_surface_path,
                line_number=pointer.line_number,
                rule="stale-forward-pointer",
                diagnostic=(
                    f"{pointer.source_kind} forward-pointer at line "
                    f"{pointer.line_number} binds target `{pointer.target_key}` "
                    f"(status `{pointer.status}`), but `{resolved}` has reached "
                    "`done` in sprint-status.yaml — the target landed and the "
                    "pointer was never flipped. Flip the pointer to its "
                    "landed/retired state, or re-route the carry if it is still "
                    "genuinely open."
                ),
            )
        )
    findings.sort(key=lambda f: (str(f.source_path), f.line_number, f.rule))
    return LintResult(
        findings=tuple(findings),
        done_stories_scanned=tuple(done_story_keys),
        carry_pointers_scanned=len(carry_pointers),
    )


def run_forward_pointer_drift_gate(
    *, carry_surface_path: pathlib.Path, sprint_status_path: pathlib.Path
) -> LintResult:
    """Read both inputs, parse the pointers + ``done`` set, evaluate the rule.

    Raises :class:`forward_pointer_drift.ForwardPointerDriftError` on a
    malformed sprint-status and :class:`OSError` / :class:`UnicodeDecodeError`
    on an unreadable / non-UTF-8 input — all mapped to exit 2 by :func:`main`
    (loud-fail; never a silent exit-0 empty set).
    """
    carry_text = carry_surface_path.read_text(encoding="utf-8")
    sprint_text = sprint_status_path.read_text(encoding="utf-8")
    carry_pointers = iter_carry_pointers(carry_text)
    done_story_keys = iter_done_story_keys(sprint_text)
    return evaluate_forward_pointer_drift(
        carry_pointers=carry_pointers,
        done_story_keys=done_story_keys,
        carry_surface_path=carry_surface_path,
    )


def _display_path(path: pathlib.Path, base_dir: pathlib.Path | None = None) -> str:
    """Render ``path`` relative to ``base_dir`` if possible; absolute
    otherwise. Mirrors :func:`done_story_review_ledger_gate._display_path`."""
    if base_dir is None:
        return str(path.resolve())
    try:
        return str(path.resolve().relative_to(base_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def format_findings(result: LintResult, *, carry_surface: str) -> str:
    """Render a :class:`LintResult` for stdout, byte-stable.

    Mirrors :func:`done_story_review_ledger_gate.format_findings`: header
    naming inputs + per-finding lines + a summary whose zero-findings shape
    satisfies the success-line contract.
    """
    lines: list[str] = []
    lines.append("Forward-pointer-drift gate (story 22.4; H6)")
    lines.append(f"  carry surface: {carry_surface}")
    lines.append(f"  forward-pointers scanned: {result.carry_pointers_scanned}")
    lines.append(f"  done stories scanned: {len(result.done_stories_scanned)}")
    lines.append("")

    base_dir = pathlib.Path(carry_surface).parent if carry_surface else None
    for finding in result.findings:
        rendered_path = _display_path(finding.source_path, base_dir)
        lines.append(
            f"forward-pointer-drift-gate: {rendered_path}:"
            f"{finding.line_number} {finding.rule} {finding.diagnostic}"
        )
        lines.append("")

    if not result.findings:
        lines.append(
            f"forward-pointer-drift-gate: 0 findings "
            f"({result.carry_pointers_scanned} forward-pointers scanned, "
            f"{len(result.done_stories_scanned)} done stories)"
        )
    else:
        lines.append(
            f"forward-pointer-drift-gate: {len(result.findings)} findings"
        )
    return "\n".join(lines)


def _discover_artifacts_dir(start: pathlib.Path | None = None) -> pathlib.Path | None:
    """Walk up from ``start`` (default cwd) for ``_bmad-output/implementation-
    artifacts/``. Returns ``None`` if no ancestor carries it (the inner-repo CI
    case — handled as harness-level exit 2 by :func:`main`)."""
    here = (start or pathlib.Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        probe = candidate.joinpath(*_ARTIFACTS_RELATIVE)
        if probe.is_dir():
            return probe
    return None


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forward-pointer-drift-gate",
        description=(
            "Forward-pointer-drift unified gate (story 22.4; H6). Fails when a "
            "still-pending forward-pointer in the carry surface "
            "(deferred-work.md) binds a target story that has already reached "
            "`done` in sprint-status.yaml — the flip that was never performed. "
            "Recognizes the structured `<!-- forward-pointer: target=…; "
            "status=… -->` annotation + a closed set of explicit inline "
            "carry-bindings. Build-time gate — no runtime marker."
        ),
    )
    parser.add_argument(
        "--carry-surface",
        type=pathlib.Path,
        default=None,
        help=(
            "Path to the carry surface (default: deferred-work.md under the "
            "discovered/--artifacts-dir implementation-artifacts dir)."
        ),
    )
    parser.add_argument(
        "--sprint-status",
        type=pathlib.Path,
        default=None,
        help=(
            "Path to sprint-status.yaml (default: sprint-status.yaml under the "
            "discovered/--artifacts-dir implementation-artifacts dir)."
        ),
    )
    parser.add_argument(
        "--artifacts-dir",
        type=pathlib.Path,
        default=None,
        help=(
            "Path to the implementation-artifacts dir holding both inputs "
            "(default: discovered by walking up from cwd for "
            "_bmad-output/implementation-artifacts/). Overridden per-file by "
            "--carry-surface / --sprint-status."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Exit codes:
        * ``0`` — ``LintResult.findings == ()`` (full pass).
        * ``1`` — any finding present (stale forward-pointer detected).
        * ``2`` — harness-level error (inputs unresolvable / unreadable /
          malformed sprint-status). Never a silent exit-0.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    artifacts_dir: pathlib.Path | None = args.artifacts_dir
    if artifacts_dir is None and (args.carry_surface is None or args.sprint_status is None):
        artifacts_dir = _discover_artifacts_dir()

    carry_surface_path: pathlib.Path | None = args.carry_surface
    if carry_surface_path is None:
        if artifacts_dir is None:
            print(
                "forward-pointer-drift-gate: harness-level error: carry surface "
                "not found (no _bmad-output/implementation-artifacts/ above cwd; "
                "pass --carry-surface or --artifacts-dir)",
                file=sys.stderr,
            )
            return 2
        carry_surface_path = artifacts_dir / _CARRY_SURFACE_NAME

    sprint_status_path: pathlib.Path | None = args.sprint_status
    if sprint_status_path is None:
        if artifacts_dir is None:
            print(
                "forward-pointer-drift-gate: harness-level error: sprint-status "
                "not found (no _bmad-output/implementation-artifacts/ above cwd; "
                "pass --sprint-status or --artifacts-dir)",
                file=sys.stderr,
            )
            return 2
        sprint_status_path = artifacts_dir / _SPRINT_STATUS_NAME

    for label, probe in (
        ("carry surface", carry_surface_path),
        ("sprint-status", sprint_status_path),
    ):
        if not probe.is_file():
            print(
                f"forward-pointer-drift-gate: harness-level error: {label} not "
                f"found ({probe!s})",
                file=sys.stderr,
            )
            return 2

    try:
        result = run_forward_pointer_drift_gate(
            carry_surface_path=carry_surface_path,
            sprint_status_path=sprint_status_path,
        )
    except (ForwardPointerDriftError, OSError, UnicodeDecodeError) as exc:
        print(
            f"forward-pointer-drift-gate: harness-level error: {exc}",
            file=sys.stderr,
        )
        return 2

    print(format_findings(result, carry_surface=str(carry_surface_path)))
    return 1 if result.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
