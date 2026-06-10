"""Done-story review-ledger structural gate — Story 24.3 (Epic 24 Action #3).

Build-time gate (NOT a runtime marker — contrast sibling 24.1's dispatcher
marker). Joins ``sprint-status.yaml`` ``done`` status × story-doc
``### Review Findings`` checkboxes and fails when a ``done`` story carries an
unresolved review ledger. Mirrors :mod:`no_destructive_resume_lint` in shape:
``LintFinding`` / ``LintResult`` frozen models + a byte-stable
``format_findings`` + a ``main`` exiting ``0`` (clean) / ``1`` (findings) /
``2`` (harness-level error). The pure parsers live in the sibling library
:mod:`done_story_review_ledger`.

## The three rules

* **R1 — ``unchecked-review-finding``**: a ``done`` story with any unchecked
  ``[ ] [Review][…]`` ledger item. The literal Story 18.3 drift. Unchecked
  dominates — R1 fires regardless of tag (incl. ``[ ] [Review][Defer]``).
* **R2 — ``deferred-finding-missing-pointer``**: a ``done`` story with a
  *checked* ``[x] [Review][Defer…]`` item whose line carries no ``deferred``
  / ``deferred-work`` annotation. **Bound:** the rule checks for the pointer's
  presence on the item line only; it does NOT open ``deferred-work.md`` to
  verify the entry exists. That cross-file existence check is STILL-DEFERRED
  (a distinct, larger mechanism — mirrors how 24.2 bounded its Rule C).
* **R3 — ``done-story-doc-unresolvable``**: a ``done`` story key whose
  ``{artifacts_dir}/{story_key}.md`` does not exist (a ``done`` story with no
  ledger to inspect is itself a traceability gap — loud-fail, not a skip).

## CI posture (Option 1, user-ratified)

The governed surface is the ``_bmad-output/implementation-artifacts/`` story
docs of a target workspace, supplied via ``--artifacts-dir``. The inner-repo
CI working-directory is ``tools/loud-fail-harness`` and those artifacts are
NOT present there, so — exactly the ``story-doc-validator`` posture — the gate
is exercised in inner CI via ``pytest`` over synthetic fixtures, and its real
teeth over live artifacts are a Dev/SM-invoked ``uv run
done-story-review-ledger-gate --sprint-status … --artifacts-dir …``. No new
``ci.yml`` step is added (none is possible inside the inner repo).
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Sequence
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from .done_story_review_ledger import (
    DoneStoryReviewLedgerError,
    iter_done_story_keys,
    iter_review_ledger_items,
)

__all__ = [
    "LintFinding",
    "LintResult",
    "evaluate_done_story_ledgers",
    "format_findings",
    "main",
    "run_done_story_review_ledger_gate",
]

#: Default discovery path for the sprint-status file, relative to a workspace
#: root walked up from cwd. The inner-repo CI never resolves this (the
#: artifacts are absent there); CI invocations come through pytest with
#: explicit paths.
_SPRINT_STATUS_RELATIVE: Final[tuple[str, ...]] = (
    "_bmad-output",
    "implementation-artifacts",
    "sprint-status.yaml",
)


class LintFinding(BaseModel):
    """A single done-story review-ledger violation.

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable dumps. Mirrors
    :class:`no_destructive_resume_lint.LintFinding`'s shape.

    Attributes:
        story_key: The ``done`` story key the finding belongs to.
        story_doc_path: Resolved ``{artifacts_dir}/{story_key}.md`` path
            (carried as :class:`pathlib.Path` for renderer-side
            relative-path normalization).
        line_number: 1-indexed line of the offending ledger item; ``0`` for
            ``done-story-doc-unresolvable`` (no line).
        rule: One of the three rule discriminators.
        diagnostic: Human-readable message naming the violation +
            remediation hint (NFR-O5).
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    story_key: str
    story_doc_path: pathlib.Path
    line_number: int
    rule: Literal[
        "unchecked-review-finding",
        "deferred-finding-missing-pointer",
        "done-story-doc-unresolvable",
    ]
    diagnostic: str


class LintResult(BaseModel):
    """Aggregate gate result.

    Frozen for determinism; field declaration order is load-bearing for
    byte-stable dumps.

    Attributes:
        findings: All findings, ordered by ``(story_key, line_number, rule)``.
        done_stories_scanned: The ``done`` story keys inspected, in
            sprint-status declaration order.
    """

    model_config = ConfigDict(frozen=True)

    findings: tuple[LintFinding, ...]
    done_stories_scanned: tuple[str, ...]


def _has_deferral_pointer(line_text: str) -> bool:
    """True if the ledger line records where the deferral is tracked.

    A ``deferred-work`` substring is subsumed by ``deferred``; both are
    accepted (case-insensitive). The ``[Review][Defer]`` tag itself does NOT
    contain ``deferred``, so it cannot self-satisfy this check.
    """
    return "deferred" in line_text.lower()


def evaluate_done_story_ledgers(
    *, done_story_keys: Sequence[str], artifacts_dir: pathlib.Path
) -> LintResult:
    """Apply rules R1/R2/R3 across the enumerated ``done`` stories.

    Resolves each ``{artifacts_dir}/{story_key}.md``; emits
    ``done-story-doc-unresolvable`` (line 0) when absent, else parses the
    ledger and emits ``unchecked-review-finding`` per unchecked item (R1) and
    ``deferred-finding-missing-pointer`` per checked ``Defer``-tagged item
    lacking a deferral pointer (R2). Findings are sorted by
    ``(story_key, line_number, rule)`` for byte-stable CI diffs.
    """
    findings: list[LintFinding] = []
    for story_key in done_story_keys:
        doc_path = artifacts_dir / f"{story_key}.md"
        if not doc_path.is_file():
            findings.append(
                LintFinding(
                    story_key=story_key,
                    story_doc_path=doc_path,
                    line_number=0,
                    rule="done-story-doc-unresolvable",
                    diagnostic=(
                        f"story `{story_key}` is marked `done` but its story-doc "
                        f"{doc_path.name} does not exist under the artifacts dir — "
                        "a `done` story must have a resolvable review ledger; "
                        "create the doc or revert the status"
                    ),
                )
            )
            continue
        doc_text = doc_path.read_text(encoding="utf-8")
        for item in iter_review_ledger_items(doc_text):
            if item.state == " ":
                findings.append(
                    LintFinding(
                        story_key=story_key,
                        story_doc_path=doc_path,
                        line_number=item.line_number,
                        rule="unchecked-review-finding",
                        diagnostic=(
                            f"story marked `done` with unchecked "
                            f"`[ ] [Review][{item.tag}]` at line {item.line_number} "
                            "— check the box (the fix landed and the ledger should "
                            "record it) or revert the status"
                        ),
                    )
                )
            elif "Defer" in item.tag and not _has_deferral_pointer(item.line_text):
                findings.append(
                    LintFinding(
                        story_key=story_key,
                        story_doc_path=doc_path,
                        line_number=item.line_number,
                        rule="deferred-finding-missing-pointer",
                        diagnostic=(
                            f"story marked `done` carries a resolved "
                            f"`[x] [Review][{item.tag}]` deferral at line "
                            f"{item.line_number} with no deferral pointer — add a "
                            "`deferred`/`deferred-work.md` annotation recording "
                            "where the deferral is tracked"
                        ),
                    )
                )
    findings.sort(key=lambda f: (f.story_key, f.line_number, f.rule))
    return LintResult(
        findings=tuple(findings),
        done_stories_scanned=tuple(done_story_keys),
    )


def run_done_story_review_ledger_gate(
    *, sprint_status_path: pathlib.Path, artifacts_dir: pathlib.Path
) -> LintResult:
    """Read the sprint-status, enumerate ``done`` stories, evaluate the rules.

    Raises :class:`done_story_review_ledger.DoneStoryReviewLedgerError` on a
    malformed sprint-status and :class:`OSError` on an unreadable one — both
    mapped to exit 2 by :func:`main` (loud-fail; never a silent exit-0).
    """
    text = sprint_status_path.read_text(encoding="utf-8")
    done_story_keys = iter_done_story_keys(text)
    return evaluate_done_story_ledgers(
        done_story_keys=done_story_keys, artifacts_dir=artifacts_dir
    )


def _display_path(path: pathlib.Path, artifacts_dir: pathlib.Path | None = None) -> str:
    """Render ``path`` relative to ``artifacts_dir`` if possible; absolute
    otherwise. Mirrors :func:`no_destructive_resume_lint._display_path`."""
    if artifacts_dir is None:
        return str(path.resolve())
    try:
        return str(path.resolve().relative_to(artifacts_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def format_findings(result: LintResult, *, artifacts_dir: str) -> str:
    """Render a :class:`LintResult` for stdout, byte-stable.

    Mirrors :func:`no_destructive_resume_lint.format_findings`: header naming
    inputs + per-finding lines + a summary whose zero-findings shape satisfies
    the success-line contract.
    """
    lines: list[str] = []
    lines.append("Done-story review-ledger gate (story 24.3; Epic 24 Action #3)")
    lines.append(f"  artifacts dir: {artifacts_dir}")
    lines.append(f"  done stories scanned: {len(result.done_stories_scanned)}")
    lines.append("")

    artifacts_dir_path = pathlib.Path(artifacts_dir) if artifacts_dir else None
    for finding in result.findings:
        rendered_path = _display_path(finding.story_doc_path, artifacts_dir_path)
        lines.append(
            f"done-story-review-ledger-gate: {finding.story_key} "
            f"{rendered_path}:{finding.line_number} {finding.rule} "
            f"{finding.diagnostic}"
        )
        lines.append("")

    if not result.findings:
        lines.append(
            f"done-story-review-ledger-gate: 0 findings "
            f"({len(result.done_stories_scanned)} done stories scanned)"
        )
    else:
        lines.append(
            f"done-story-review-ledger-gate: {len(result.findings)} findings"
        )
    return "\n".join(lines)


def _discover_sprint_status(start: pathlib.Path | None = None) -> pathlib.Path | None:
    """Walk up from ``start`` (default cwd) for ``_bmad-output/implementation-
    artifacts/sprint-status.yaml``. Returns ``None`` if no ancestor carries it
    (the inner-repo CI case — handled as harness-level exit 2 by :func:`main`)."""
    here = (start or pathlib.Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        probe = candidate.joinpath(*_SPRINT_STATUS_RELATIVE)
        if probe.is_file():
            return probe
    return None


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="done-story-review-ledger-gate",
        description=(
            "Done-story review-ledger structural gate (story 24.3; Epic 24 "
            "Action #3). Fails when a story is `done` in sprint-status while its "
            "story-doc `### Review Findings` ledger carries an unchecked "
            "`[ ] [Review][…]` item (R1) or a resolved `[Review][Defer]` item "
            "with no deferral pointer (R2), or when a `done` story has no "
            "resolvable story-doc (R3). Build-time gate — no runtime marker."
        ),
    )
    parser.add_argument(
        "--sprint-status",
        type=pathlib.Path,
        default=None,
        help=(
            "Path to sprint-status.yaml (default: discovered by walking up "
            "from cwd for _bmad-output/implementation-artifacts/sprint-status.yaml)."
        ),
    )
    parser.add_argument(
        "--artifacts-dir",
        type=pathlib.Path,
        default=None,
        help=(
            "Path to the implementation-artifacts dir holding the story docs "
            "(default: the parent dir of the resolved --sprint-status)."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Exit codes:
        * ``0`` — ``LintResult.findings == ()`` (full pass).
        * ``1`` — any finding present (invariant violation).
        * ``2`` — harness-level error (inputs unresolvable / unreadable /
          malformed sprint-status). Never a silent exit-0.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    sprint_status_path: pathlib.Path | None = args.sprint_status
    if sprint_status_path is None:
        sprint_status_path = _discover_sprint_status()
    if sprint_status_path is None or not sprint_status_path.is_file():
        print(
            "done-story-review-ledger-gate: harness-level error: "
            "sprint-status.yaml not found "
            f"({sprint_status_path!s} unresolved; pass --sprint-status)",
            file=sys.stderr,
        )
        return 2

    artifacts_dir: pathlib.Path = (
        args.artifacts_dir
        if args.artifacts_dir is not None
        else sprint_status_path.parent
    )
    if not artifacts_dir.is_dir():
        print(
            "done-story-review-ledger-gate: harness-level error: "
            f"artifacts dir not found ({artifacts_dir!s}; pass --artifacts-dir)",
            file=sys.stderr,
        )
        return 2

    try:
        result = run_done_story_review_ledger_gate(
            sprint_status_path=sprint_status_path, artifacts_dir=artifacts_dir
        )
    except (DoneStoryReviewLedgerError, OSError) as exc:
        print(
            f"done-story-review-ledger-gate: harness-level error: {exc}",
            file=sys.stderr,
        )
        return 2

    print(format_findings(result, artifacts_dir=str(artifacts_dir)))
    return 1 if result.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
