"""``/bmad-automation status --epic <epic-id>`` substrate library — Story 15.4.

## Substrate-component identity

THIS module is a substrate **library** sibling of
:mod:`loud_fail_harness.status_command` (Story 8.4),
:mod:`loud_fail_harness.multi_story_status` (Story 8.5), and
:mod:`loud_fail_harness.bundle_assembly_epic` (Story 15.3) — in the
status / orchestrator-state family. It is **NOT a sixth substrate
component** beyond ADR-003 Consequence 1's enumerated five
(``envelope_validator``, ``event_validator``, ``reconciler``,
``enumeration_check``, ``fixture_coverage``). The count holds at FIVE;
the harness-library count grows. NO new specialist, NO 4th hook.

The module is the read-only EPIC-scope analogue of Story 8.4's single-story
``inspect_story``: it renders a VIEW over the EXISTING ``EpicRunState`` cache
(Stories 15.1–15.3) plus a per-story marker-presence projection of Story
8.4's ``inspect_story`` (NFR-R8 — no fourth canonical store; per-story
markers stay canonical in the per-story run-state / artifacts). Its upstream
caller is the orchestrator skill's ``/bmad-automation status --epic`` branch
(prose at ``skills/bmad-automation/steps/status.md``); THIS module is invoked
as the ``bmad-automation-status-epic`` CLI.

## Read-only invariant (FR48 + NFR-O4 at epic scope)

The ``--epic`` path has ZERO write surface — even less than Story 8.5's
no-args listing, which emits ``orphan-run-state-detected``. NO
``advance_epic_run_state``, NO ``cross_state_recovery``, NO marker emission,
NO specialist dispatch, NO git touch. ``inspect_epic`` reads the
epic-run-state cache (via :func:`epic_run_state.load_epic_run_state`) and
projects Story 8.4's read-only ``inspect_story`` per contained story; both
loads are read-only. The structural witness asserts the epic-run-state file's
mtime + sha256 are byte-identical before/after (AC-4).

## The three ``EpicStatusOutcome.action`` branches

* ``epic-status-found`` — cache present at the resolved path and its
  ``epic_id`` matches the requested ``--epic``; ``inspection`` is populated;
  ``diagnostic`` is ``None``; exit 0.
* ``epic-status-no-run-state`` — NO cache at the resolved path; halts with a
  named-invariant diagnostic ``no-in-flight-epic-run-found-for-epic-id`` (NOT
  a marker — the Story 8.4 ``no-in-flight-run-found-for-story-id`` precedent);
  exit 1.
* ``epic-id-mismatch`` — cache present but its ``epic_id`` does NOT match the
  requested ``--epic`` (a single cache exists per project at Epic 15 scope;
  the practitioner queried an epic that is not the in-flight one); named-
  invariant diagnostic, exit 1.

A harness-level error inside the substrate (Pydantic validation failure,
malformed cache parse, unexpected exception) raises
:class:`EpicStatusCommandError` (Pattern 5 chained-exception), routed to
exit 2.

## Sensor-not-advisor

Per ADR-001 + Pattern 5, this substrate produces a directive
(:class:`EpicStatusOutcome` carrying :class:`EpicInspection`); the
orchestrator skill's ``steps/status.md`` runtime protocol parses the
directive and surfaces the rendered output verbatim. THIS substrate does NOT
invoke the Task tool, does NOT emit orchestrator events, does NOT advance
lifecycle state, does NOT mutate any persisted state.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
from collections.abc import Callable, Sequence
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .bundle_assembly_epic import compute_epic_bundle_path
from .epic_run_state import (
    DEFAULT_EPIC_RUN_STATE_PATH,
    EpicCurrentState,
    EpicRunStateNotFound,
    EpicRunStateParseError,
    PerEpicRetryBudget,
    load_epic_run_state,
)
from .marker_wiring import compute_alphabetical_marker_order
from .status_command import StatusOutcome, StatusRequest, inspect_story

__all__ = [
    "EpicInspection",
    "EpicStatusCommandError",
    "EpicStatusOutcome",
    "EpicStatusRequest",
    "EpicStoryRow",
    "inspect_epic",
    "main",
    "render_epic_id_mismatch_diagnostic",
    "render_epic_inspection_human",
    "render_epic_inspection_json",
    "render_no_epic_run_state_diagnostic",
]

_logger = logging.getLogger(__name__)

#: Type alias for the Pattern-6 DI seam injecting Story 8.4's inspect_story.
InspectStoryFn = Callable[[StatusRequest], StatusOutcome]

_UNDISPATCHED_ANNOTATION: str = "(not yet dispatched — no per-story run-state)"


# --------------------------------------------------------------------------- #
# Exception classes                                                           #
# --------------------------------------------------------------------------- #


class EpicStatusCommandError(Exception):
    """Raised on substrate-level failures inside the epic-status command.

    Pattern 5 — loud-fail / named invariants. Analogous in shape to
    :class:`status_command.StatusCommandError` and
    :class:`multi_story_status.MultiStoryStatusError`. Programmer-error
    invariant — no marker emission at THIS surface (the ``--epic`` path has
    zero emission surface per AC-4).

    Attributes:
        reason: Short kebab-case discriminator naming the concrete failure.
        diagnostic: Human-readable diagnostic naming the failure mode.
    """

    #: Programmer-error invariant signal — no marker emission at THIS surface.
    marker_class: ClassVar[None] = None

    def __init__(self, *, reason: str, diagnostic: str) -> None:
        self.reason = reason
        self.diagnostic = diagnostic
        super().__init__(f"EpicStatusCommandError[{reason}]: {diagnostic}")


# --------------------------------------------------------------------------- #
# Pydantic models — AC-1 public API                                           #
# --------------------------------------------------------------------------- #


class EpicStatusRequest(BaseModel):
    """Typed input to :func:`inspect_epic`.

    Pattern 6 — frozen so callers cannot mutate the request mid-evaluation.
    Mirrors :class:`status_command.StatusRequest` in shape.

    Attributes:
        epic_id: BMAD epic identifier the practitioner supplied at
            ``/bmad-automation status --epic <epic-id>``. Required;
            ``min_length=1``.
        project_root: Practitioner's BMAD project root. Required;
            ``is_absolute`` enforced at validation time. Forwarded to the
            per-story :class:`StatusRequest.project_root` for the AC-3
            marker projection.
        epic_run_state_path: Pattern-6 explicit-path injection. ``None``
            resolves to ``project_root / DEFAULT_EPIC_RUN_STATE_PATH``.
        repo_root: Pattern-6 explicit-path injection used to compute the
            epic-PR-bundle pointer + forwarded to the per-story
            :class:`StatusRequest.repo_root`. ``None`` defaults to
            ``project_root``.
        inspect_story_fn: Pattern-6 DI seam for
            :func:`status_command.inspect_story`. ``None`` resolves to the
            live function; tests inject canned :class:`StatusOutcome` stubs.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    epic_id: str = Field(
        ...,
        min_length=1,
        description=(
            "BMAD epic identifier; sourced from /bmad-automation status "
            "--epic <epic-id>."
        ),
    )
    project_root: pathlib.Path = Field(
        ...,
        description=(
            "Absolute path to the practitioner's project root. Read for the "
            "epic-run-state cache + the per-story inspect_story projection."
        ),
    )
    epic_run_state_path: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional explicit path to the epic-run-state cache. None → "
            "project_root / _bmad/automation/epic-run-state.yaml."
        ),
    )
    repo_root: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional explicit repo_root for the epic-PR-bundle pointer + "
            "per-story retry-round resolution. None defaults to project_root."
        ),
    )
    inspect_story_fn: InspectStoryFn | None = Field(
        default=None,
        description=(
            "Pattern-6 DI seam for status_command.inspect_story. None → the "
            "live function; tests inject canned StatusOutcome stubs."
        ),
    )

    @field_validator("project_root")
    @classmethod
    def _project_root_must_be_absolute(cls, v: pathlib.Path) -> pathlib.Path:
        if not v.is_absolute():
            raise ValueError(
                f"project_root must be an absolute path; got {v!r}. "
                "Pass pathlib.Path.cwd() or a CLI-resolved absolute path."
            )
        return v


class EpicStoryRow(BaseModel):
    """One per-story row of the epic-status render.

    Pattern 4 — frozen; field declaration order is load-bearing for
    byte-stable :meth:`model_dump_json` output.

    ``per_story_status`` is the epic-cache-recorded status (the
    ``PerStoryStatus`` value, or ``"unknown"`` defensively when a
    ``story_ids`` entry is absent from the cache's ``per_story_status`` map —
    mirroring :func:`bundle_assembly_epic._render_story_table`'s ``.get``
    default). ``marker_count`` is the per-story active-marker count projected
    from Story 8.4's ``inspect_story`` (``None`` when the story has no
    in-flight per-story run-state — AC-3 graceful degrade). ``dispatched`` is
    ``True`` when ``inspect_story`` returned ``status-found``.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str
    per_story_status: str
    marker_count: int | None
    dispatched: bool


class EpicInspection(BaseModel):
    """The canonical epic-status inspection payload (AC-2).

    Frozen per Pattern 4. Field declaration order is load-bearing for
    byte-stable :meth:`model_dump_json` output (the Story 8.4
    :class:`StoryInspection` discipline). The render is a VIEW over the
    EXISTING ``EpicRunState`` cache shape (NFR-R8 — no fourth canonical
    store): per-epic fields passthrough from the cache; per-story
    ``marker_count`` projects from ``inspect_story`` (AC-3).
    """

    model_config = ConfigDict(frozen=True)

    epic_id: str
    run_id: str
    current_state: EpicCurrentState
    per_story_rows: tuple[EpicStoryRow, ...]
    per_epic_retry_budget: PerEpicRetryBudget
    active_markers: tuple[str, ...]
    epic_run_state_path: pathlib.Path
    epic_pr_bundle_path: pathlib.Path


_EpicStatusAction = Literal[
    "epic-status-found", "epic-status-no-run-state", "epic-id-mismatch"
]


class EpicStatusOutcome(BaseModel):
    """Typed return of :func:`inspect_epic`.

    Pattern 6 — frozen so the orchestrator skill cannot mutate the outcome
    between read and route.

    Attributes:
        action: One of three canonical actions per AC-1 / AC-6.
        inspection: Populated on ``epic-status-found``; ``None`` otherwise.
        diagnostic: ``None`` on ``epic-status-found``; populated on
            ``epic-status-no-run-state`` / ``epic-id-mismatch`` (the named-
            invariant diagnostic per AC-6).
    """

    model_config = ConfigDict(frozen=True)

    action: _EpicStatusAction
    inspection: EpicInspection | None = None
    diagnostic: str | None = None


# --------------------------------------------------------------------------- #
# Diagnostics (pure deterministic formatters)                                 #
# --------------------------------------------------------------------------- #


def render_no_epic_run_state_diagnostic(
    request: EpicStatusRequest, epic_run_state_path: pathlib.Path
) -> str:
    """Pure deterministic formatter producing the AC-6 named-invariant
    diagnostic text for the no-epic-run-state pre-condition.

    Mirrors :func:`status_command.render_no_run_state_diagnostic` in shape
    (the named-invariant ``no-in-flight-epic-run-found-for-epic-id`` token,
    NOT a marker) but the remediation pointers are epic-scoped: start a fresh
    epic run via ``/bmad-automation run --epic <epic-id>``; list all in-flight
    stories/epics via the no-args ``/bmad-automation status``.
    """
    parts = [
        (
            "status --epic: no-in-flight-epic-run-found-for-epic-id: "
            f"{request.epic_id}"
        ),
        f"probed epic-run-state path: {epic_run_state_path!s}",
        (
            "remediation: "
            "(a) start a fresh epic run via /bmad-automation run --epic "
            f"{request.epic_id}, "
            "(b) list all in-flight stories/epics via /bmad-automation status"
        ),
    ]
    return "; ".join(parts)


def render_epic_id_mismatch_diagnostic(
    request: EpicStatusRequest,
    *,
    cached_epic_id: str,
    epic_run_state_path: pathlib.Path,
) -> str:
    """Pure deterministic formatter producing the AC-6 ``epic-id-mismatch``
    named-invariant diagnostic.

    A single epic-run-state cache exists per project at Epic 15 scope; a
    mismatch means the practitioner queried an epic that is not the in-flight
    one. NOT a marker, NOT a crash — surfaced as the requested-vs-cached
    epic-id with the no-args-status remediation pointer.
    """
    parts = [
        f"status --epic: epic-id-mismatch: requested {request.epic_id}",
        f"in-flight epic-run-state cache is for epic {cached_epic_id}",
        f"probed epic-run-state path: {epic_run_state_path!s}",
        (
            "remediation: query the in-flight epic via /bmad-automation status "
            f"--epic {cached_epic_id}, OR list all in-flight stories/epics via "
            "/bmad-automation status"
        ),
    ]
    return "; ".join(parts)


# --------------------------------------------------------------------------- #
# inspect_epic — canonical entry point                                        #
# --------------------------------------------------------------------------- #


def inspect_epic(request: EpicStatusRequest) -> EpicStatusOutcome:
    """Canonical read-only epic-status inspection per FR48 + NFR-O4 at epic
    scope.

    Pure-function-shaped (the only side effects are filesystem reads via
    :func:`epic_run_state.load_epic_run_state` and the per-story
    :func:`status_command.inspect_story` projection). NEVER mutates the
    epic-run-state, per-story run-state, story-docs, sprint-status,
    per-specialist logs, events.jsonl, deferred-work.md, or the git working
    tree, and emits NO marker class (the AC-4 read-only invariant).

    The three branches per AC-1 / AC-6:

    1. NO cache at the resolved path → ``epic-status-no-run-state`` (named-
       invariant diagnostic; exit 1).
    2. Cache present but ``epic_id`` mismatch → ``epic-id-mismatch`` (named-
       invariant diagnostic; exit 1).
    3. Cache present + matching ``epic_id`` → ``epic-status-found`` (the
       rendered inspection; exit 0).

    Args:
        request: The typed input.

    Returns:
        :class:`EpicStatusOutcome`.

    Raises:
        EpicStatusCommandError: When the cache is present-but-malformed
            (chained from :class:`epic_run_state.EpicRunStateParseError`) OR
            when the per-story ``inspect_story`` projection raised an
            unexpected error (Pattern 5; chained via ``from exc``).
    """
    epic_run_state_path = (
        request.epic_run_state_path
        if request.epic_run_state_path is not None
        else request.project_root / DEFAULT_EPIC_RUN_STATE_PATH
    )
    repo_root = (
        request.repo_root if request.repo_root is not None else request.project_root
    )
    inspect_fn = (
        request.inspect_story_fn
        if request.inspect_story_fn is not None
        else inspect_story
    )

    # AC-6 — no-cache pre-condition + malformed-cache harness error.
    try:
        cache = load_epic_run_state(epic_run_state_path)
    except EpicRunStateNotFound:
        diagnostic = render_no_epic_run_state_diagnostic(
            request, epic_run_state_path
        )
        return EpicStatusOutcome(
            action="epic-status-no-run-state",
            inspection=None,
            diagnostic=diagnostic,
        )
    except EpicRunStateParseError as exc:
        raise EpicStatusCommandError(
            reason="epic-run-state-parse-error",
            diagnostic=str(exc),
        ) from exc

    # AC-6 — epic-id-mismatch pre-condition (exit 1, no marker).
    if cache.epic_id != request.epic_id:
        diagnostic = render_epic_id_mismatch_diagnostic(
            request,
            cached_epic_id=cache.epic_id,
            epic_run_state_path=epic_run_state_path,
        )
        return EpicStatusOutcome(
            action="epic-id-mismatch",
            inspection=None,
            diagnostic=diagnostic,
        )

    # AC-3 — per-story marker projection via Story 8.4's inspect_story,
    # ordered by the cache's story_ids (the epic-defined order Story 15.1
    # seeded). Graceful per-story degrade on status-no-run-state.
    rows: list[EpicStoryRow] = []
    for story_id in cache.story_ids:
        per_story_status = cache.per_story_status.get(story_id, "unknown")
        status_request = StatusRequest(
            project_root=request.project_root,
            story_id=story_id,
            repo_root=repo_root,
            resolve_retry_rounds=False,
        )
        try:
            outcome = inspect_fn(status_request)
        except Exception as exc:  # noqa: BLE001 — loud-fail boundary per P5
            raise EpicStatusCommandError(
                reason="inspect-story-error",
                diagnostic=(
                    "status --epic: per-story inspect_story raised an "
                    f"unexpected error for story_id={story_id!r}: {exc!r}"
                ),
            ) from exc

        if outcome.action == "status-found":
            if outcome.inspection is None:
                raise EpicStatusCommandError(
                    reason="inspect-story-contract-violated",
                    diagnostic=(
                        "status --epic: status-found outcome with inspection=None "
                        f"for story_id={story_id!r} — substrate contract violated"
                    ),
                )
            rows.append(
                EpicStoryRow(
                    story_id=story_id,
                    per_story_status=per_story_status,
                    marker_count=len(outcome.inspection.active_markers),
                    dispatched=True,
                )
            )
        else:
            # AC-3 graceful degrade: no in-flight per-story run-state (the
            # epic loop has not dispatched this story yet). Render the cache
            # status; omit marker_count. NOT a crash, NOT a halt.
            rows.append(
                EpicStoryRow(
                    story_id=story_id,
                    per_story_status=per_story_status,
                    marker_count=None,
                    dispatched=False,
                )
            )

    epic_pr_bundle_path = compute_epic_bundle_path(
        repo_root=repo_root, epic_id=cache.epic_id, run_id=cache.run_id
    )

    inspection = EpicInspection(
        epic_id=cache.epic_id,
        run_id=cache.run_id,
        current_state=cache.current_state,
        per_story_rows=tuple(rows),
        per_epic_retry_budget=cache.per_epic_retry_budget,
        active_markers=cache.active_markers,
        epic_run_state_path=epic_run_state_path,
        epic_pr_bundle_path=epic_pr_bundle_path,
    )
    return EpicStatusOutcome(
        action="epic-status-found",
        inspection=inspection,
        diagnostic=None,
    )


# --------------------------------------------------------------------------- #
# Renderers (pure deterministic formatters)                                   #
# --------------------------------------------------------------------------- #


def render_epic_inspection_human(inspection: EpicInspection) -> str:
    """Pure deterministic formatter producing the AC-2 human-readable
    terminal output. Byte-stable on identical input (the Story 8.5 AC-9
    purity contract).

    Sections (in order): ``## Epic lifecycle state``; ``## Per-story
    status``; ``## Per-epic retry budget`` (mirroring the epic bundle's
    ``_render_retry_budget``); ``## Active loud-fail markers`` (alphabetical
    via :func:`marker_wiring.compute_alphabetical_marker_order`,
    ``(no active markers)`` placeholder when empty); ``## Pointers``.
    """
    lines: list[str] = []
    lines.append(f"# /bmad-automation status --epic — epic {inspection.epic_id}")
    lines.append("")

    # --- Epic lifecycle state ---
    lines.append("## Epic lifecycle state")
    lines.append("")
    lines.append(f"state: {inspection.current_state}")
    lines.append(f"epic_id: {inspection.epic_id}")
    lines.append(f"run_id: {inspection.run_id}")
    lines.append("")

    # --- Per-story status ---
    lines.append("## Per-story status")
    lines.append("")
    if not inspection.per_story_rows:
        lines.append("(no stories in this epic)")
    else:
        for row in inspection.per_story_rows:
            if row.dispatched:
                lines.append(
                    f"- {row.story_id} → {row.per_story_status} "
                    f"(markers={row.marker_count})"
                )
            else:
                lines.append(
                    f"- {row.story_id} → {row.per_story_status} "
                    f"{_UNDISPATCHED_ANNOTATION}"
                )
    lines.append("")

    # --- Per-epic retry budget ---
    budget = inspection.per_epic_retry_budget
    lines.append("## Per-epic retry budget")
    lines.append("")
    lines.append(
        f"Consumed {budget.consumed} of {budget.effective_budget} "
        f"(multiplier {budget.multiplier} × {budget.story_count} stories)."
    )
    lines.append("")

    # --- Active loud-fail markers ---
    lines.append("## Active loud-fail markers")
    lines.append("")
    if not inspection.active_markers:
        lines.append("(no active markers)")
    else:
        for marker in compute_alphabetical_marker_order(inspection.active_markers):
            lines.append(f"- {marker}")
    lines.append("")

    # --- Pointers ---
    lines.append("## Pointers")
    lines.append("")
    lines.append(f"epic_run_state_path: {inspection.epic_run_state_path!s}")
    lines.append(f"epic_pr_bundle_path: {inspection.epic_pr_bundle_path!s}")

    return "\n".join(lines)


def render_epic_inspection_json(inspection: EpicInspection) -> str:
    """Pure deterministic JSON formatter producing the AC-2
    machine-consumable output.

    Uses :meth:`EpicInspection.model_dump_json` with ``indent=2`` per
    Pydantic v2's canonical serialization. Field declaration order is
    load-bearing for byte-stable output (the Story 8.4 ``StoryInspection``
    discipline). :class:`pathlib.Path` fields serialize as posix-style
    strings on POSIX hosts.
    """
    return inspection.model_dump_json(indent=2)


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bmad-automation-status-epic",
        description=(
            "/bmad-automation status --epic <epic-id> substrate (Story 15.4, "
            "FR48 + NFR-O4 at epic scope). Read-only epic-status inspection: "
            "loads the epic-run-state cache via "
            "epic_run_state.load_epic_run_state, projects Story 8.4's "
            "status_command.inspect_story per contained story for per-story "
            "marker presence, computes the epic-PR-bundle pointer. Halts on "
            "no-epic-run-state / epic-id-mismatch with a named-invariant "
            "diagnostic (NOT a marker). Zero write surface."
        ),
    )
    parser.add_argument(
        "--epic",
        dest="epic_id",
        type=str,
        required=True,
        help=(
            "BMAD epic identifier (e.g., 'epic-15'); matches the epic-run-"
            "state cache's epic_id."
        ),
    )
    parser.add_argument(
        "--project-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Absolute path to the practitioner's project root. Defaults to "
            "the current working directory."
        ),
    )
    parser.add_argument(
        "--epic-run-state-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Optional explicit path to the epic-run-state cache. Defaults to "
            "<project_root>/_bmad/automation/epic-run-state.yaml."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Optional explicit repo_root for the epic-PR-bundle pointer + "
            "per-story retry-round resolution. Defaults to --project-root."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_flag",
        help=(
            "Emit machine-consumable JSON instead of the human-readable "
            "render."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point invoked by the orchestrator skill's
    ``steps/status.md`` ``--epic`` runtime protocol per AC-7.

    Exit codes per AC-1 / AC-6 (mirroring Story 8.4's 0/1/2 split):
        * ``0`` — ``epic-status-found`` (silent success; the rendered
          inspection is printed to stdout).
        * ``1`` — ``epic-status-no-run-state`` OR ``epic-id-mismatch`` (halt
          with named-invariant diagnostic to stderr).
        * ``2`` — harness-level error inside the substrate per Pattern 5.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    project_root = (
        args.project_root if args.project_root is not None else pathlib.Path.cwd()
    )
    if not project_root.is_absolute():
        project_root = project_root.resolve()
    epic_run_state_path = args.epic_run_state_path
    if epic_run_state_path is not None and not epic_run_state_path.is_absolute():
        epic_run_state_path = epic_run_state_path.resolve()
    repo_root = args.repo_root
    if repo_root is not None and not repo_root.is_absolute():
        repo_root = repo_root.resolve()

    try:
        request = EpicStatusRequest(
            epic_id=args.epic_id,
            project_root=project_root,
            epic_run_state_path=epic_run_state_path,
            repo_root=repo_root,
        )
    except (ValueError, ValidationError) as exc:
        print(f"status --epic: harness-level error: {exc}", file=sys.stderr)
        return 2

    try:
        outcome = inspect_epic(request)
    except EpicStatusCommandError as exc:
        print(f"status --epic: harness-level error: {exc}", file=sys.stderr)
        return 2

    if outcome.action == "epic-status-found":
        if outcome.inspection is None:
            print(
                "status --epic: harness-level error: epic-status-found "
                "outcome has inspection=None — substrate contract violated",
                file=sys.stderr,
            )
            return 2
        if args.json_flag:
            print(render_epic_inspection_json(outcome.inspection))
        else:
            print(render_epic_inspection_human(outcome.inspection))
        return 0

    # epic-status-no-run-state OR epic-id-mismatch — exit 1.
    print(
        outcome.diagnostic or f"status --epic: {outcome.action}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
