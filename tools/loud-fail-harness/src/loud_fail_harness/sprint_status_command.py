"""``/bmad-automation status --sprint <sprint-id>`` substrate library — Story 16.4.

## Substrate-component identity

THIS module is a substrate **library** sibling of
:mod:`loud_fail_harness.status_command` (Story 8.4),
:mod:`loud_fail_harness.multi_story_status` (Story 8.5), and
:mod:`loud_fail_harness.epic_status_command` (Story 15.4) — in the
status / orchestrator-state family. It is **NOT a sixth substrate component**
beyond ADR-003 Consequence 1's enumerated five (``envelope_validator``,
``event_validator``, ``reconciler``, ``enumeration_check``,
``fixture_coverage``). The count holds at FIVE; the harness-library count
grows. NO new specialist, NO 4th hook.

The module is the read-only SPRINT-scope analogue of Story 15.4's
``inspect_epic``: it renders a VIEW over the sprint-state-tree the EXISTING
:func:`loud_fail_harness.sprint_status_artifact.build_sprint_status_artifact`
already rolls up from the durable caches (the sprint-run-state cache plus each
per-epic ``EpicRunState`` cache). It does NOT re-walk those caches — Story 16.3
AC-2 factored ``build_sprint_status_artifact`` as a pure, total,
model-returning rollup EXPLICITLY so this query reuses it (NFR-R8 — no fourth
canonical store). Its upstream caller is the orchestrator skill's
``/bmad-automation status --sprint`` branch (prose at
``skills/bmad-automation/steps/status.md``); THIS module is invoked as the
``bmad-automation-status-sprint`` CLI.

## Read-only invariant (FR48 + NFR-O4 at sprint scope)

The ``--sprint`` path has ZERO write surface. NO ``assemble_sprint_status_artifact``
(the sprint-close writer), NO atomic write to ``_bmad-output/sprints/``, NO
``advance_sprint_run_state``, NO ``cross_state_recovery``, NO marker emission,
NO specialist dispatch, NO git touch. ``inspect_sprint`` calls
``build_sprint_status_artifact`` (write-free — Story 16.3 kept it total) and
renders the returned model to stdout. Even the injected ``generated_at`` lands
only on the in-memory rendered model — nothing reaches disk. A structural
witness asserts the sprint-run-state file's AND every per-epic cache file's
mtime + sha256 are byte-identical before/after (AC-4).

## The three ``SprintStatusOutcome.action`` branches

* ``sprint-status-found`` — sprint cache present at the resolved path and its
  ``sprint_id`` matches the requested ``--sprint``; ``artifact`` is populated;
  ``diagnostic`` is ``None``; exit 0.
* ``sprint-status-no-run-state`` — NO sprint cache at the resolved path; halts
  with a named-invariant diagnostic ``no-in-flight-sprint-run-found-for-sprint-id``
  (NOT a marker — the Story 15.4 ``no-in-flight-epic-run-found-for-epic-id``
  precedent); exit 1.
* ``sprint-id-mismatch`` — sprint cache present but its ``sprint_id`` does NOT
  match the requested ``--sprint`` (a single cache exists per project at Epic 16
  scope; the practitioner queried a sprint that is not the in-flight one);
  named-invariant diagnostic, exit 1.

A harness-level error inside the substrate (Pydantic validation failure,
malformed cache parse, naive-``generated_at`` ``ValueError``, unexpected
exception) raises :class:`SprintStatusCommandError` (Pattern 5 chained-
exception), routed to exit 2.

## Marker-surfacing scope decision (AC-3 — pointer-not-projection)

The sprint render surfaces the AGGREGATE scoped active-markers union (sprint ∪
per-epic) ``build_sprint_status_artifact`` already carries, de-duped on
``(marker_class, scope)`` — it does NOT project Story 8.4's ``inspect_story``
per contained story at sprint scale (O(all-stories-across-all-epics) reads on a
read-only query does not compose up; NFR-R8). The render POINTS the
practitioner to ``status --epic <epic-id>`` and ``status <story-id>`` for
per-story drill-down — the multi-scope observability chain
(``status --sprint`` → ``status --epic`` → ``status <story-id>``) composes,
each layer surfacing its own scope's markers without re-aggregating the layer
below (the Story 15.3 pointer-not-projection decision, applied one scope up).

## Sensor-not-advisor

Per ADR-001 + Pattern 5, this substrate produces a directive
(:class:`SprintStatusOutcome` carrying the rendered
:class:`loud_fail_harness.sprint_status_artifact.SprintStatusArtifact`); the
orchestrator skill's ``steps/status.md`` runtime protocol parses the directive
and surfaces the rendered output verbatim. THIS substrate does NOT invoke the
Task tool, does NOT emit orchestrator events, does NOT advance lifecycle state,
does NOT mutate any persisted state.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .epic_run_state import DEFAULT_SPRINT_RUN_STATE_PATH
from .sprint_status_artifact import (
    SprintRunStateNotFound,
    SprintStatusArtifact,
    SprintStoryRow,
    build_sprint_status_artifact,
    compute_sprint_status_artifact_path,
)

__all__ = [
    "SprintStatusCommandError",
    "SprintStatusOutcome",
    "SprintStatusRequest",
    "inspect_sprint",
    "main",
    "render_no_sprint_run_state_diagnostic",
    "render_sprint_id_mismatch_diagnostic",
    "render_sprint_inspection_human",
    "render_sprint_inspection_json",
]

_logger = logging.getLogger(__name__)

_UNASSIGNED_GROUP_LABEL: str = "(unassigned)"


# --------------------------------------------------------------------------- #
# Exception classes                                                           #
# --------------------------------------------------------------------------- #


class SprintStatusCommandError(Exception):
    """Raised on substrate-level failures inside the sprint-status command.

    Pattern 5 — loud-fail / named invariants. Analogous in shape to
    :class:`epic_status_command.EpicStatusCommandError`. Programmer-error
    invariant — no marker emission at THIS surface (the ``--sprint`` path has
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
        super().__init__(f"SprintStatusCommandError[{reason}]: {diagnostic}")


# --------------------------------------------------------------------------- #
# Pydantic models — AC-1 public API                                           #
# --------------------------------------------------------------------------- #


class SprintStatusRequest(BaseModel):
    """Typed input to :func:`inspect_sprint`.

    Pattern 6 — frozen so callers cannot mutate the request mid-evaluation.
    Mirrors :class:`epic_status_command.EpicStatusRequest` in shape.

    Attributes:
        sprint_id: BMAD sprint identifier the practitioner supplied at
            ``/bmad-automation status --sprint <sprint-id>``. Required;
            ``min_length=1``.
        project_root: Practitioner's BMAD project root. Required;
            ``is_absolute`` enforced at validation time.
        sprint_run_state_path: Pattern-6 explicit-path injection. ``None``
            resolves to ``project_root / DEFAULT_SPRINT_RUN_STATE_PATH``.
        repo_root: Pattern-6 explicit-path injection threaded to
            ``build_sprint_status_artifact``'s ``repo_root`` so the per-epic
            caches are addressed correctly. ``None`` defaults to
            ``project_root``.
        generated_at: Pattern-6 DI seam for the rendered model's timestamp.
            ``None`` resolves to ``datetime.now(timezone.utc)`` at the ``main``
            boundary; tests pin it for byte-stability.
    """

    model_config = ConfigDict(frozen=True)

    sprint_id: str = Field(
        ...,
        min_length=1,
        description=(
            "BMAD sprint identifier; sourced from /bmad-automation status "
            "--sprint <sprint-id>."
        ),
    )
    project_root: pathlib.Path = Field(
        ...,
        description=(
            "Absolute path to the practitioner's project root. Anchors the "
            "sprint-run-state cache path + the per-epic cache addressing."
        ),
    )
    sprint_run_state_path: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional explicit path to the sprint-run-state cache. None → "
            "project_root / _bmad/automation/sprint-run-state.yaml."
        ),
    )
    repo_root: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional explicit repo_root threaded to "
            "build_sprint_status_artifact for per-epic cache addressing + the "
            "sprint-status-artifact pointer. None defaults to project_root."
        ),
    )
    generated_at: datetime | None = Field(
        default=None,
        description=(
            "Pattern-6 DI seam for the rendered model's timestamp. None → "
            "datetime.now(timezone.utc) at the main boundary; tests pin it."
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


_SprintStatusAction = Literal[
    "sprint-status-found", "sprint-status-no-run-state", "sprint-id-mismatch"
]


class SprintStatusOutcome(BaseModel):
    """Typed return of :func:`inspect_sprint`.

    Pattern 6 — frozen so the orchestrator skill cannot mutate the outcome
    between read and route.

    Attributes:
        action: One of three canonical actions per AC-1 / AC-6.
        artifact: Populated on ``sprint-status-found``; ``None`` otherwise.
        diagnostic: ``None`` on ``sprint-status-found``; populated on
            ``sprint-status-no-run-state`` / ``sprint-id-mismatch`` (the named-
            invariant diagnostic per AC-6 — the Story 15.4 P6 no-silent-exit-1
            fix).
    """

    model_config = ConfigDict(frozen=True)

    action: _SprintStatusAction
    artifact: SprintStatusArtifact | None = None
    diagnostic: str | None = None


# --------------------------------------------------------------------------- #
# Diagnostics (pure deterministic formatters)                                 #
# --------------------------------------------------------------------------- #


def render_no_sprint_run_state_diagnostic(
    request: SprintStatusRequest, sprint_run_state_path: pathlib.Path
) -> str:
    """Pure deterministic formatter producing the AC-6 named-invariant
    diagnostic text for the no-sprint-run-state pre-condition.

    Mirrors :func:`epic_status_command.render_no_epic_run_state_diagnostic` in
    shape (the named-invariant ``no-in-flight-sprint-run-found-for-sprint-id``
    token, NOT a marker) with sprint-scoped remediation pointers: start a fresh
    sprint run via ``/bmad-automation run --sprint <sprint-id>``; list all
    in-flight stories/epics/sprints via the no-args ``/bmad-automation status``.
    """
    parts = [
        (
            "status --sprint: no-in-flight-sprint-run-found-for-sprint-id: "
            f"{request.sprint_id}"
        ),
        f"probed sprint-run-state path: {sprint_run_state_path!s}",
        (
            "remediation: "
            "(a) start a fresh sprint run via /bmad-automation run --sprint "
            f"{request.sprint_id}, "
            "(b) list all in-flight stories/epics/sprints via "
            "/bmad-automation status"
        ),
    ]
    return "; ".join(parts)


def render_sprint_id_mismatch_diagnostic(
    request: SprintStatusRequest,
    *,
    cached_sprint_id: str,
    sprint_run_state_path: pathlib.Path,
) -> str:
    """Pure deterministic formatter producing the AC-6 ``sprint-id-mismatch``
    named-invariant diagnostic.

    A single sprint-run-state cache exists per project at Epic 16 scope; a
    mismatch means the practitioner queried a sprint that is not the in-flight
    one. NOT a marker, NOT a crash — surfaced as the requested-vs-cached
    sprint-id with the no-args-status remediation pointer (mirrors
    :func:`epic_status_command.render_epic_id_mismatch_diagnostic`).
    """
    parts = [
        f"status --sprint: sprint-id-mismatch: requested {request.sprint_id}",
        f"in-flight sprint-run-state cache is for sprint {cached_sprint_id}",
        f"probed sprint-run-state path: {sprint_run_state_path!s}",
        (
            "remediation: query the in-flight sprint via /bmad-automation "
            f"status --sprint {cached_sprint_id}, OR list all in-flight "
            "stories/epics/sprints via /bmad-automation status"
        ),
    ]
    return "; ".join(parts)


# --------------------------------------------------------------------------- #
# inspect_sprint — canonical entry point                                      #
# --------------------------------------------------------------------------- #


def inspect_sprint(request: SprintStatusRequest) -> SprintStatusOutcome:
    """Canonical read-only sprint-status inspection per FR48 + NFR-O4 at sprint
    scope.

    Obtains the sprint-state-tree by CALLING
    :func:`loud_fail_harness.sprint_status_artifact.build_sprint_status_artifact`
    (the Story 16.3 pure rollup) — it does NOT re-walk the caches and does NOT
    write the ``.md`` artifact. The only side effect is the cache reads
    ``build_sprint_status_artifact`` performs (themselves read-only). NEVER
    mutates the sprint-run-state, per-epic caches, story-docs, sprint-status,
    per-specialist logs, events.jsonl, deferred-work.md, or the git working
    tree, and emits NO marker class (the AC-4 read-only invariant).

    The three branches per AC-1 / AC-6:

    1. NO sprint cache at the resolved path → ``sprint-status-no-run-state``
       (named-invariant diagnostic; exit 1).
    2. Cache present but ``sprint_id`` mismatch → ``sprint-id-mismatch``
       (named-invariant diagnostic; exit 1). Detected by comparing the
       requested ``sprint_id`` against the ``SprintStatusArtifact.sprint_id``
       the build returns (reusing the build — no second loader; Open Question 1
       default).
    3. Cache present + matching ``sprint_id`` → ``sprint-status-found`` (the
       rendered artifact; exit 0).

    Args:
        request: The typed input.

    Returns:
        :class:`SprintStatusOutcome`.

    Raises:
        SprintStatusCommandError: When the cache is present-but-malformed, the
            ``generated_at`` is naive, a per-epic cache is malformed, or any
            unexpected error occurs inside ``build_sprint_status_artifact``
            (Pattern 5; chained via ``from exc``).
    """
    sprint_run_state_path = (
        request.sprint_run_state_path
        if request.sprint_run_state_path is not None
        else request.project_root / DEFAULT_SPRINT_RUN_STATE_PATH
    )
    repo_root = (
        request.repo_root if request.repo_root is not None else request.project_root
    )
    generated_at = (
        request.generated_at
        if request.generated_at is not None
        else datetime.now(timezone.utc)
    )

    try:
        artifact = build_sprint_status_artifact(
            sprint_run_state_path,
            repo_root=repo_root,
            generated_at=generated_at,
        )
    except SprintRunStateNotFound:
        diagnostic = render_no_sprint_run_state_diagnostic(
            request, sprint_run_state_path
        )
        return SprintStatusOutcome(
            action="sprint-status-no-run-state",
            artifact=None,
            diagnostic=diagnostic,
        )
    except SprintStatusCommandError:
        raise
    except Exception as exc:  # noqa: BLE001 — loud-fail boundary per Pattern 5
        raise SprintStatusCommandError(
            reason="sprint-status-build-error",
            diagnostic=(
                "status --sprint: build_sprint_status_artifact raised an "
                f"unexpected error for sprint_run_state_path="
                f"{sprint_run_state_path!s}: {exc!r}"
            ),
        ) from exc

    if artifact.sprint_id != request.sprint_id:
        diagnostic = render_sprint_id_mismatch_diagnostic(
            request,
            cached_sprint_id=artifact.sprint_id,
            sprint_run_state_path=sprint_run_state_path,
        )
        return SprintStatusOutcome(
            action="sprint-id-mismatch",
            artifact=None,
            diagnostic=diagnostic,
        )

    return SprintStatusOutcome(
        action="sprint-status-found",
        artifact=artifact,
        diagnostic=None,
    )


# --------------------------------------------------------------------------- #
# Renderers (pure deterministic formatters)                                   #
# --------------------------------------------------------------------------- #


def render_sprint_inspection_human(
    artifact: SprintStatusArtifact,
    *,
    sprint_run_state_path: pathlib.Path,
    repo_root: pathlib.Path,
) -> str:
    """Pure deterministic formatter producing the AC-2 human-readable terminal
    output. Byte-stable on identical input incl. a pinned ``generated_at`` (the
    Story 8.5 AC-9 purity contract).

    Sections (in order): ``## Sprint lifecycle state``; ``## Sprint state tree``
    (per-epic rows with their per-story rows nested by ``epic_id``, plus an
    ``(unassigned)`` group for ``epic_id is None``); ``## Aggregate cost``;
    ``## Per-sprint retry budget`` (``used N of M``); ``## Escalation rate``;
    ``## Active loud-fail markers`` (the scoped union inline WITH ``scope``,
    ``(no active markers)`` placeholder when empty); ``## Pointers`` (the
    resolved sprint-run-state path + the sprint-status-artifact path via
    :func:`compute_sprint_status_artifact_path` + the AC-3 drill-down command
    pointers).
    """
    lines: list[str] = []
    lines.append(
        f"# /bmad-automation status --sprint — sprint {artifact.sprint_id}"
    )
    lines.append("")

    lines.append("## Sprint lifecycle state")
    lines.append("")
    lines.append(f"state: {artifact.current_state}")
    lines.append(f"sprint_id: {artifact.sprint_id}")
    lines.append(f"run_id: {artifact.run_id}")
    lines.append(f"generated_at: {artifact.generated_at}")
    lines.append("")

    lines.append("## Sprint state tree")
    lines.append("")
    stories_by_epic: dict[str | None, list[SprintStoryRow]] = {}
    for story in artifact.per_story:
        stories_by_epic.setdefault(story.epic_id, []).append(story)
    if not artifact.per_epic:
        lines.append("(no epics dispatched in this sprint)")
        lines.append("")
    else:
        for epic in artifact.per_epic:
            lines.append(
                f"- {epic.epic_id} → {epic.status} "
                f"(cost={epic.cost_total:.2f} USD, "
                f"retries={epic.retries_consumed}/{epic.retries_budget})"
            )
            epic_stories = stories_by_epic.get(epic.epic_id, [])
            if not epic_stories:
                lines.append(
                    "  - (no per-story rows for this epic)"
                )
            else:
                for story in epic_stories:
                    lines.append(
                        f"  - {story.story_id} → {story.status} "
                        f"(cost={story.cost:.2f} USD)"
                    )
        lines.append("")
    unassigned = stories_by_epic.get(None, [])
    if unassigned:
        lines.append(f"- {_UNASSIGNED_GROUP_LABEL}")
        for story in unassigned:
            lines.append(
                f"  - {story.story_id} → {story.status} "
                f"(cost={story.cost:.2f} USD)"
            )
        lines.append("")

    lines.append("## Aggregate cost")
    lines.append("")
    lines.append(f"Total: {artifact.aggregate_cost_total:.2f} USD.")
    lines.append("")

    budget = artifact.retry_budget
    lines.append("## Per-sprint retry budget")
    lines.append("")
    lines.append(f"Used {budget.consumed} of {budget.effective_budget}.")
    lines.append("")

    esc = artifact.escalation
    lines.append("## Escalation rate")
    lines.append("")
    lines.append(
        f"Escalated {esc.escalated_stories} of {esc.stories_completed} "
        f"completed = {esc.rate * 100:.1f}%."
    )
    lines.append("")

    lines.append("## Active loud-fail markers")
    lines.append("")
    if not artifact.active_markers:
        lines.append("(no active markers)")
    else:
        for marker in artifact.active_markers:
            lines.append(f"- {marker.marker_class} [{marker.scope}]")
    lines.append("")

    artifact_path = compute_sprint_status_artifact_path(
        repo_root=repo_root, sprint_id=artifact.sprint_id
    )
    lines.append("## Pointers")
    lines.append("")
    lines.append(f"sprint_run_state_path: {sprint_run_state_path!s}")
    lines.append(f"sprint_status_artifact_path: {artifact_path!s}")
    lines.append(
        "per-epic marker detail: /bmad-automation status --epic <epic-id>"
    )
    lines.append(
        "per-story marker + retry-history detail: "
        "/bmad-automation status <story-id>"
    )

    return "\n".join(lines)


def render_sprint_inspection_json(artifact: SprintStatusArtifact) -> str:
    """Pure deterministic JSON formatter producing the AC-2 machine-consumable
    output.

    Uses :meth:`SprintStatusArtifact.model_dump_json` with ``indent=2`` per
    Pydantic v2's canonical serialization. Field declaration order is
    load-bearing for byte-stable output (the Story 8.4 ``StoryInspection``
    discipline).
    """
    return artifact.model_dump_json(indent=2)


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bmad-automation-status-sprint",
        description=(
            "/bmad-automation status --sprint <sprint-id> substrate (Story "
            "16.4, FR48 + NFR-O4 at sprint scope). Read-only sprint-status "
            "inspection: REUSES Story 16.3's build_sprint_status_artifact "
            "aggregate read (the sprint-state-tree rollup over the sprint-run-"
            "state cache + each per-epic EpicRunState cache) and renders the "
            "returned model to stdout — it does NOT re-walk the caches and "
            "does NOT write the .md artifact. Halts on no-sprint-run-state / "
            "sprint-id-mismatch with a named-invariant diagnostic (NOT a "
            "marker). Zero write surface."
        ),
    )
    parser.add_argument(
        "--sprint",
        dest="sprint_id",
        type=str,
        required=True,
        help=(
            "BMAD sprint identifier (e.g., 'sprint-1'); matches the sprint-"
            "run-state cache's sprint_id."
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
        "--sprint-run-state-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Optional explicit path to the sprint-run-state cache. Defaults to "
            "<project_root>/_bmad/automation/sprint-run-state.yaml."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Optional explicit repo_root threaded to "
            "build_sprint_status_artifact for per-epic cache addressing + the "
            "sprint-status-artifact pointer. Defaults to --project-root."
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
    """CLI entry point invoked by the orchestrator skill's ``steps/status.md``
    ``--sprint`` runtime protocol per AC-9.

    Exit codes per AC-1 / AC-6 (mirroring Story 15.4's 0/1/2 split):
        * ``0`` — ``sprint-status-found`` (the rendered inspection to stdout).
        * ``1`` — ``sprint-status-no-run-state`` OR ``sprint-id-mismatch``
          (halt with named-invariant diagnostic to stderr).
        * ``2`` — harness-level error inside the substrate per Pattern 5.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    project_root = (
        args.project_root if args.project_root is not None else pathlib.Path.cwd()
    )
    if not project_root.is_absolute():
        project_root = project_root.resolve()
    sprint_run_state_path = args.sprint_run_state_path
    if sprint_run_state_path is not None and not sprint_run_state_path.is_absolute():
        sprint_run_state_path = sprint_run_state_path.resolve()
    repo_root = args.repo_root
    if repo_root is not None and not repo_root.is_absolute():
        repo_root = repo_root.resolve()

    try:
        request = SprintStatusRequest(
            sprint_id=args.sprint_id,
            project_root=project_root,
            sprint_run_state_path=sprint_run_state_path,
            repo_root=repo_root,
        )
    except (ValueError, ValidationError) as exc:
        print(f"status --sprint: harness-level error: {exc}", file=sys.stderr)
        return 2

    try:
        outcome = inspect_sprint(request)
    except SprintStatusCommandError as exc:
        print(f"status --sprint: harness-level error: {exc}", file=sys.stderr)
        return 2

    if outcome.action == "sprint-status-found":
        if outcome.artifact is None:
            print(
                "status --sprint: harness-level error: sprint-status-found "
                "outcome has artifact=None — substrate contract violated",
                file=sys.stderr,
            )
            return 2
        try:
            if args.json_flag:
                print(render_sprint_inspection_json(outcome.artifact))
            else:
                resolved_sprint_run_state_path = (
                    request.sprint_run_state_path
                    if request.sprint_run_state_path is not None
                    else request.project_root / DEFAULT_SPRINT_RUN_STATE_PATH
                )
                resolved_repo_root = (
                    request.repo_root
                    if request.repo_root is not None
                    else request.project_root
                )
                print(
                    render_sprint_inspection_human(
                        outcome.artifact,
                        sprint_run_state_path=resolved_sprint_run_state_path,
                        repo_root=resolved_repo_root,
                    )
                )
        except Exception as exc:  # noqa: BLE001 — loud-fail boundary per Pattern 5
            print(
                f"status --sprint: harness-level error: render failed: {exc}",
                file=sys.stderr,
            )
            return 2
        return 0

    # sprint-status-no-run-state OR sprint-id-mismatch — exit 1.
    print(
        outcome.diagnostic or f"status --sprint: {outcome.action}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
