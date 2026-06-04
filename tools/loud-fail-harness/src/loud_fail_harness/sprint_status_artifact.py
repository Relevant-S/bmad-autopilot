"""Sprint-status-artifact assembler — Story 16.3 substrate library.

## Substrate-component identity

Substrate **LIBRARY** (sibling of :mod:`loud_fail_harness.bundle_assembly_epic`
one scope down), NOT a sixth substrate component — ADR-003 Consequence 1 keeps
the substrate closed at FIVE. This is composition over the established cache
models + atomic-write primitive + failure-routing seam; no new specialist, no
4th hook, no new marker class.

## What this module emits (AC-1 / AC-2 / AC-3)

A structured, OBJECTIVE-ONLY ``sprint-status-artifact-<sprint-id>.md`` at sprint
close. It is a READ-ONLY aggregate (NFR-R8 / ADR-005) over the durable caches:
the sprint-run-state cache (Story 16.1) + each per-epic ``EpicRunState`` cache
(Story 15.x, addressed via :func:`epic_run_state_path_for`). It RE-DERIVES the
cost / escalation aggregates from those caches (the sprint cache carries neither;
Story 16.2 tracked them transiently). The rollup is factored as a pure
model-returning :func:`build_sprint_status_artifact` so Story 16.4's
``status --sprint`` query reuses the SAME aggregate read without duplicating the
per-epic cache walk; :func:`assemble_sprint_status_artifact` adds the markdown
render + atomic write on top.

## NOT a retrospective (AC-5 — three structural layers, defense in depth)

1. The frozen :class:`SprintStatusArtifact` model is ``extra="forbid"`` — a
   subjective field (``what_went_well``, ``recommendation``, …) is
   UNCONSTRUCTABLE.
2. :func:`assemble_sprint_status_artifact` calls
   :func:`loud_fail_harness.sprint_status_artifact_validator.validate_artifact_data`
   on the model's serialization BEFORE the atomic write — the closed schema
   (``additionalProperties: false`` everywhere) rejects any drift.
3. The rendered markdown carries ONLY the objective sections, scannable by
   :func:`loud_fail_harness.sprint_status_artifact_validator.scan_rendered_markdown`.

The Automator emits objective state; the human runs the SEPARATE ``/retrospective``
workflow with this as input (sensor-not-advisor; PRD-locked retrospective
boundary).

## Failure routing (AC-7 — reuse the EXISTING `bundle-assembly-failed` channel)

:func:`main` mirrors :func:`loud_fail_harness.bundle_assembly_epic.main`:

    * Pre-condition failure (missing sprint cache → :exc:`SprintRunStateNotFound`;
      a ``sprint_id``/``run_id``-mismatched cache → :exc:`SprintRunStateMismatch`;
      a bad path component → :exc:`SprintArtifactPathInvariantViolation`) →
      stderr + exit 1, NO marker (nothing to assemble; remediation-shape
      discipline).
    * Assembler-logic failure (sprint-cache SHAPE mismatch / render crash /
      schema-validation failure on the assembled model → :exc:`SprintArtifactSchemaViolation`)
      → routes through the EXISTING ``surface_assembly_failure`` and exits
      :data:`BUNDLE_ASSEMBLY_FAILED_EXIT_CODE`. ZERO new marker classes; the
      closed-set count is unchanged. Channel 3 (per-story-``RunState``-bound)
      naturally degrades on a ``SprintRunState`` input (the same best-effort
      ``try/except`` ``bundle_assembly_epic.main`` uses).
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.bundle_assembly import _atomic_write_bundle
from loud_fail_harness.bundle_assembly_failure import (
    BUNDLE_ASSEMBLY_FAILED_EXIT_CODE,
    classify_assembly_failure,
    surface_assembly_failure,
)
from loud_fail_harness.epic_run_state import (
    DEFAULT_SPRINT_RUN_STATE_PATH,
    EpicRunState,
    SprintCurrentState,
    SprintRunState,
    epic_run_state_path_for,
)
from loud_fail_harness.sprint_status_artifact_validator import validate_artifact_data

__all__ = [
    "AssembleSprintArtifactResult",
    "SprintActiveMarker",
    "SprintArtifactPathInvariantViolation",
    "SprintArtifactSchemaViolation",
    "SprintEpicRow",
    "SprintEscalationSummary",
    "SprintRetryBudgetSummary",
    "SprintRunStateMismatch",
    "SprintRunStateNotFound",
    "SprintStatusArtifact",
    "SprintStoryRow",
    "assemble_sprint_status_artifact",
    "build_sprint_status_artifact",
    "compute_sprint_status_artifact_path",
    "main",
]

#: Directory (under ``_bmad-output/``) the sprint-status artifact is written to.
#: Created on write (it does not exist yet). Mirrors the per-story ``pr-bundles``
#: / epic ``epic-pr-bundles`` path conventions one + two scopes down.
SPRINT_ARTIFACTS_DIRNAME = "sprints"

#: Explicit row status for a per-epic cache that never materialized (an epic that
#: never dispatched before a pause) / an unassigned story whose per-story cache is
#: not locatable. The loud-fail surface for the missing-cache anomaly — never a
#: silent omission.
_NOT_DISPATCHED: Literal["not-dispatched"] = "not-dispatched"

#: Per-story statuses that count as "reached a terminal status" for the
#: escalation-rate denominator — the same set the sprint loop guards
#: (``TERMINAL_PER_STORY_STATUSES | {"escalated"}``, Story 16.2).
_TERMINAL_STORY_STATUSES: frozenset[str] = frozenset(
    {"merge-ready", "done", "escalated"}
)

#: The epic terminal state that contributes to the escalation NUMERATOR (the epic
#: loop pauses on the FIRST escalation, so at most one escalated story per epic —
#: Story 16.2's ``escalated_count`` semantics, re-derived from the durable cache).
_EPIC_ESCALATION_STATE = "epic-paused-on-escalation"

SprintEpicRowStatus = Literal[
    "epic-in-progress",
    "epic-paused-on-escalation",
    "epic-paused-on-budget",
    "epic-complete",
    "not-dispatched",
]

SprintStoryRowStatus = Literal[
    "ready-for-dev",
    "in-progress",
    "review",
    "qa",
    "done",
    "escalated",
    "merge-ready",
    "not-dispatched",
]


class SprintArtifactPathInvariantViolation(ValueError):
    """``sprint_id`` failed the path-component hardening guard.

    Empty, absolute, ``..``-traversal-bearing, or null-byte-bearing. Mirrors
    :class:`loud_fail_harness.bundle_assembly_epic.EpicBundlePathInvariantViolation`.
    """


class SprintRunStateNotFound(Exception):
    """Pre-condition failure: the sprint-run-state cache file does not exist.

    Mirrors
    :class:`loud_fail_harness.bundle_assembly_epic.EpicRunStateNotFound` — exit 1,
    NO ``bundle-assembly-failed`` marker (nothing to assemble).
    """

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        super().__init__(f"sprint-run-state cache not found at {path}")


class SprintRunStateMismatch(Exception):
    """Pre-condition failure: the loaded cache is for a different sprint/run.

    The sprint-scope sibling of
    :class:`loud_fail_harness.bundle_assembly_epic.EpicRunStateEpicIdMismatch` —
    exit 1, NO marker.
    """

    def __init__(self, *, field: str, expected: str, actual: str) -> None:
        self.field = field
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"sprint-run-state {field} {actual!r} does not match requested "
            f"{expected!r}"
        )


class SprintArtifactSchemaViolation(Exception):
    """Assembler-logic failure: the assembled model failed schema validation.

    Raised by :func:`assemble_sprint_status_artifact`'s defense-in-depth
    ``validate_artifact_data`` (AC-5) — routed through ``surface_assembly_failure``
    by :func:`main` (assembler-logic failure → exit code, NOT a pre-condition).
    """


class SprintActiveMarker(BaseModel):
    """One scoped active loud-fail marker the artifact renders (AC-1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    marker_class: str = Field(min_length=1)
    scope: str = Field(min_length=1)


class SprintEpicRow(BaseModel):
    """One per-epic outcome row (AC-1). Closed shape; field order = schema
    ``required`` order (load-bearing for byte-stable ``model_dump_json()``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    epic_id: str = Field(min_length=1)
    status: SprintEpicRowStatus
    cost_total: float = Field(ge=0)
    retries_consumed: int = Field(ge=0)
    retries_budget: int = Field(ge=0)


class SprintStoryRow(BaseModel):
    """One per-story outcome row (AC-1). ``epic_id`` is ``None`` for an
    unassigned story."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    story_id: str = Field(min_length=1)
    epic_id: str | None
    status: SprintStoryRowStatus
    cost: float = Field(ge=0)


class SprintRetryBudgetSummary(BaseModel):
    """Per-sprint retry-budget consumption summary (AC-1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    consumed: int = Field(ge=0)
    effective_budget: int = Field(ge=0)


class SprintEscalationSummary(BaseModel):
    """Sprint escalation-rate summary, re-derived from the durable caches
    (AC-1 / AC-2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    escalated_stories: int = Field(ge=0)
    stories_completed: int = Field(ge=0)
    rate: float = Field(ge=0)


class SprintStatusArtifact(BaseModel):
    """The structured, OBJECTIVE-ONLY sprint-status artifact (AC-1).

    Mirrors ``schemas/sprint-status-artifact.yaml`` 1:1 (the ``SprintRunState``-
    mirror posture). ``ConfigDict(frozen=True, extra="forbid")`` makes a
    subjective field (``what_went_well``, ``recommendation``, ``lessons_learned``,
    ``sentiment``, …) STRUCTURALLY IMPOSSIBLE to construct — the closed shape IS
    the "no subjective fields" enforcement (AC-5 layer 1). Sequence fields are
    tuple-typed so ``frozen=True`` blocks both reassignment and in-place mutation.
    Field declaration order matches the schema's ``required`` enumeration order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sprint_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    current_state: SprintCurrentState
    generated_at: str = Field(min_length=1)
    per_epic: tuple[SprintEpicRow, ...]
    per_story: tuple[SprintStoryRow, ...]
    aggregate_cost_total: float = Field(ge=0)
    retry_budget: SprintRetryBudgetSummary
    escalation: SprintEscalationSummary
    active_markers: tuple[SprintActiveMarker, ...]


@dataclasses.dataclass(frozen=True)
class AssembleSprintArtifactResult:
    """Return shape of :func:`assemble_sprint_status_artifact` on success."""

    artifact_path: pathlib.Path
    sprint_id: str
    run_id: str
    current_state: str
    artifact: SprintStatusArtifact


def _reject_path_component(value: str, *, name: str) -> None:
    if not value:
        raise SprintArtifactPathInvariantViolation(f"{name} must not be empty")
    if "\x00" in value:
        raise SprintArtifactPathInvariantViolation(
            f"{name} must not contain a null byte; got {value!r}"
        )
    pure = pathlib.PurePosixPath(value)
    if pure.is_absolute():
        raise SprintArtifactPathInvariantViolation(
            f"{name} must not be an absolute path; got {value!r}"
        )
    if ".." in pure.parts:
        raise SprintArtifactPathInvariantViolation(
            f"{name} must not contain '..' path traversal segments; got {value!r}"
        )


def compute_sprint_status_artifact_path(
    *,
    repo_root: pathlib.Path,
    sprint_id: str,
) -> pathlib.Path:
    """Return the deterministic artifact path
    ``{repo_root}/_bmad-output/sprints/sprint-status-artifact-{sprint_id}.md``.

    Pure path computation; does NOT create the directory. Mirrors
    :func:`loud_fail_harness.bundle_assembly_epic.compute_epic_bundle_path`:
    rejects empty / absolute / ``..``-traversal / null-byte ``sprint_id``.

    Raises:
        SprintArtifactPathInvariantViolation: ``sprint_id`` failed the guard.
    """
    _reject_path_component(sprint_id, name="sprint_id")
    return (
        repo_root
        / "_bmad-output"
        / SPRINT_ARTIFACTS_DIRNAME
        / f"sprint-status-artifact-{sprint_id}.md"
    )


def _load_sprint_run_state(sprint_run_state_path: pathlib.Path) -> SprintRunState:
    """Read + Pydantic-validate the sprint-run-state cache YAML.

    A missing file is a PRE-CONDITION failure (:exc:`SprintRunStateNotFound`); a
    present-but-malformed file is an ASSEMBLER-LOGIC failure — the underlying
    error propagates unchanged so ``main`` routes it through
    ``surface_assembly_failure`` (mirrors ``_load_epic_run_state``).
    """
    if not sprint_run_state_path.exists():
        raise SprintRunStateNotFound(sprint_run_state_path)
    raw = yaml.safe_load(sprint_run_state_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(
            f"sprint-run-state file at {sprint_run_state_path} did not parse to "
            "a YAML mapping at top level"
        )
    return SprintRunState.model_validate(dict(raw))


def _load_epic_run_state_best_effort(
    epic_run_state_path: pathlib.Path,
) -> EpicRunState | None:
    """Read + validate a per-epic cache, returning ``None`` when ABSENT.

    Absence is NOT a hard failure (the artifact is a best-effort aggregate over
    whatever the sprint reached — an absent cache surfaces as a
    ``not-dispatched`` row). A present-but-malformed cache is an assembler-logic
    failure: the error propagates (no swallowing).
    """
    if not epic_run_state_path.exists():
        return None
    raw = yaml.safe_load(epic_run_state_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(
            f"epic-run-state file at {epic_run_state_path} did not parse to a "
            "YAML mapping at top level"
        )
    return EpicRunState.model_validate(dict(raw))


def build_sprint_status_artifact(
    sprint_run_state_path: pathlib.Path,
    *,
    repo_root: pathlib.Path | None = None,
    generated_at: datetime,
) -> SprintStatusArtifact:
    """Roll up the sprint-status artifact from the durable caches (AC-2).

    Loads the sprint-run-state cache, then for each ``epic_id`` loads the per-epic
    ``EpicRunState`` cache via :func:`epic_run_state_path_for` and rolls up the
    per-epic table, per-story table, aggregate cost, retry-budget used/total,
    re-derived escalation rate, and the scoped active-markers union. Pure
    (no I/O beyond reading caches; no render/write; no schema validation — kept
    total so Story 16.4's ``status --sprint`` query reuses it directly).

    Args:
        sprint_run_state_path: On-disk path to ``sprint-run-state.yaml``.
        repo_root: Root used to address per-epic caches (defaults to
            :func:`epic_run_state_path_for`'s lazy ``_default_repo_root``).
        generated_at: Timezone-aware UTC timestamp (naive → named
            :exc:`ValueError`, the ``assemble_epic_bundle`` precedent).

    Raises:
        ValueError: ``generated_at`` is naive.
        SprintRunStateNotFound: the sprint cache is absent (pre-condition).
    """
    if generated_at.tzinfo is None:
        raise ValueError(
            "build_sprint_status_artifact: generated_at must be timezone-aware "
            "UTC; got naive datetime — pass datetime.now(timezone.utc) or a "
            "timezone-aware datetime"
        )

    sprint = _load_sprint_run_state(sprint_run_state_path)

    seen_markers: set[tuple[str, str]] = set()
    markers: list[SprintActiveMarker] = []

    def _add_marker(marker_class: str, scope: str) -> None:
        key = (marker_class, scope)
        if key not in seen_markers:
            seen_markers.add(key)
            markers.append(SprintActiveMarker(marker_class=marker_class, scope=scope))

    for marker_class in sprint.active_markers:
        _add_marker(marker_class, "sprint")

    per_epic: list[SprintEpicRow] = []
    per_story: list[SprintStoryRow] = []
    aggregate_cost = 0.0
    escalated_stories = 0
    stories_completed = 0

    for epic_id in sprint.epic_ids:
        epic_path = epic_run_state_path_for(epic_id, repo_root=repo_root)
        cache = _load_epic_run_state_best_effort(epic_path)
        if cache is None:
            per_epic.append(
                SprintEpicRow(
                    epic_id=epic_id,
                    status=_NOT_DISPATCHED,
                    cost_total=0.0,
                    retries_consumed=0,
                    retries_budget=0,
                )
            )
            continue

        per_epic.append(
            SprintEpicRow(
                epic_id=epic_id,
                status=cache.current_state,
                cost_total=cache.per_epic_cost_partition.epic_cost_total,
                retries_consumed=cache.per_epic_retry_budget.consumed,
                retries_budget=cache.per_epic_retry_budget.effective_budget,
            )
        )
        aggregate_cost += cache.per_epic_cost_partition.epic_cost_total

        for story_id in cache.story_ids:
            status = cache.per_story_status.get(story_id, _NOT_DISPATCHED)
            cost = cache.per_epic_cost_partition.per_story_cost.get(story_id, 0.0)
            per_story.append(
                SprintStoryRow(
                    story_id=story_id,
                    epic_id=epic_id,
                    status=status,
                    cost=cost,
                )
            )
            if status in _TERMINAL_STORY_STATUSES:
                stories_completed += 1

        if cache.current_state == _EPIC_ESCALATION_STATE:
            escalated_stories += 1

        for marker_class in cache.active_markers:
            _add_marker(marker_class, f"epic:{epic_id}")

    # Unassigned-story rows: best-effort lower bound. No per-story addressing
    # convention is pinned at this story's scope (Open Question 2 / deferred-
    # work), so an unassigned story surfaces as a `not-dispatched` row with 0.0
    # cost and contributes nothing to the escalation aggregate. In this workspace
    # unassigned_story_ids is empty (every story is epic-grouped), so this is the
    # empty-set common case; the row is loud (never silently omitted) when present.
    for story_id in sprint.unassigned_story_ids:
        per_story.append(
            SprintStoryRow(
                story_id=story_id,
                epic_id=None,
                status=_NOT_DISPATCHED,
                cost=0.0,
            )
        )

    rate = (escalated_stories / stories_completed) if stories_completed > 0 else 0.0

    return SprintStatusArtifact(
        sprint_id=sprint.sprint_id,
        run_id=sprint.run_id,
        current_state=sprint.current_state,
        generated_at=generated_at.isoformat(),
        per_epic=tuple(per_epic),
        per_story=tuple(per_story),
        aggregate_cost_total=aggregate_cost,
        retry_budget=SprintRetryBudgetSummary(
            consumed=sprint.per_sprint_retry_budget.consumed,
            effective_budget=sprint.per_sprint_retry_budget.effective_budget,
        ),
        escalation=SprintEscalationSummary(
            escalated_stories=escalated_stories,
            stories_completed=stories_completed,
            rate=rate,
        ),
        active_markers=tuple(markers),
    )


def _render_per_epic_table(artifact: SprintStatusArtifact) -> str:
    parts = [
        "## Per-epic summary",
        "",
        "| Epic | Status | Cost (USD) | Retries |",
        "| --- | --- | --- | --- |",
    ]
    for row in artifact.per_epic:
        parts.append(
            f"| {row.epic_id} | {row.status} | {row.cost_total:.2f} | "
            f"{row.retries_consumed}/{row.retries_budget} |"
        )
    return "\n".join(parts)


def _render_per_story_table(artifact: SprintStatusArtifact) -> str:
    parts = [
        "## Per-story summary",
        "",
        "| Story | Epic | Status | Cost (USD) |",
        "| --- | --- | --- | --- |",
    ]
    for row in artifact.per_story:
        epic = row.epic_id if row.epic_id is not None else "(unassigned)"
        parts.append(f"| {row.story_id} | {epic} | {row.status} | {row.cost:.2f} |")
    return "\n".join(parts)


def _render_aggregate_cost(artifact: SprintStatusArtifact) -> str:
    parts = [
        "## Aggregate cost",
        "",
        f"Total: {artifact.aggregate_cost_total:.2f} USD.",
    ]
    lower_bound = any(
        row.status == _NOT_DISPATCHED for row in artifact.per_epic
    ) or any(row.epic_id is None for row in artifact.per_story)
    if lower_bound:
        parts.append("")
        parts.append(
            "_The total is a LOWER BOUND: a `not-dispatched` epic contributes "
            "0.00, and unassigned-story cost is counted as 0.00 absent a pinned "
            "per-story cache addressing convention (mirrors the epic-bundle "
            "zero-cost caveat)._"
        )
    return "\n".join(parts)


def _render_retry_budget(artifact: SprintStatusArtifact) -> str:
    budget = artifact.retry_budget
    return "\n".join(
        [
            "## Retry-budget consumption",
            "",
            f"Used {budget.consumed} of {budget.effective_budget}.",
        ]
    )


def _render_escalation(artifact: SprintStatusArtifact) -> str:
    esc = artifact.escalation
    return "\n".join(
        [
            "## Escalation rate",
            "",
            f"Escalated {esc.escalated_stories} of {esc.stories_completed} "
            f"completed = {esc.rate * 100:.1f}%.",
        ]
    )


def _render_active_markers(artifact: SprintStatusArtifact) -> str:
    parts = ["## Active loud-fail markers", ""]
    if not artifact.active_markers:
        parts.append("_No active loud-fail markers across the sprint._")
        return "\n".join(parts)
    parts.append("| Marker | Scope |")
    parts.append("| --- | --- |")
    for marker in artifact.active_markers:
        parts.append(f"| {marker.marker_class} | {marker.scope} |")
    return "\n".join(parts)


def _render_artifact(artifact: SprintStatusArtifact) -> str:
    body_parts = [
        f"# Sprint status artifact — sprint {artifact.sprint_id} "
        f"(run {artifact.run_id})",
        "",
        f"Sprint state: {artifact.current_state}",
        f"Generated: {artifact.generated_at}",
        "",
        _render_per_epic_table(artifact),
        "",
        _render_per_story_table(artifact),
        "",
        _render_aggregate_cost(artifact),
        "",
        _render_retry_budget(artifact),
        "",
        _render_escalation(artifact),
        "",
        _render_active_markers(artifact),
        "",
    ]
    return "\n".join(body_parts)


def assemble_sprint_status_artifact(
    sprint_run_state_path: pathlib.Path,
    *,
    repo_root: pathlib.Path,
    sprint_artifacts_root: pathlib.Path,
    generated_at: datetime | None = None,
    expected_sprint_id: str | None = None,
    expected_run_id: str | None = None,
) -> AssembleSprintArtifactResult:
    """Build, validate, render, and atomic-write the sprint-status artifact
    (AC-3 / AC-5 / AC-7).

    Calls :func:`build_sprint_status_artifact` (AC-2), validates the serialized
    model against the closed schema BEFORE the write (AC-5 defense-in-depth),
    renders plain markdown (NFR-O2), and atomic-writes (Pattern 4 / NFR-R1 via
    the shared ``_atomic_write_bundle``) to
    ``sprint_artifacts_root/sprint-status-artifact-<sprint-id>.md``.

    Args:
        sprint_run_state_path: On-disk path to ``sprint-run-state.yaml``.
        repo_root: Root used to address per-epic caches (build step).
        sprint_artifacts_root: The ``_bmad-output/sprints`` directory the artifact
            is written under (created on write).
        generated_at: Optional tz-aware UTC timestamp; defaults to
            ``datetime.now(timezone.utc)`` (the byte-stable injection point).
        expected_sprint_id / expected_run_id: When supplied, the loaded cache's
            ``sprint_id`` / ``run_id`` must match — else :exc:`SprintRunStateMismatch`
            (pre-condition).

    Raises:
        SprintRunStateNotFound / SprintRunStateMismatch /
        SprintArtifactPathInvariantViolation: pre-condition failures.
        SprintArtifactSchemaViolation: the assembled model failed schema
            validation (assembler-logic failure).
        ValueError: ``generated_at`` is naive.
    """
    rendered_at = (
        generated_at if generated_at is not None else datetime.now(timezone.utc)
    )
    artifact = build_sprint_status_artifact(
        sprint_run_state_path, repo_root=repo_root, generated_at=rendered_at
    )

    if expected_sprint_id is not None and artifact.sprint_id != expected_sprint_id:
        raise SprintRunStateMismatch(
            field="sprint_id", expected=expected_sprint_id, actual=artifact.sprint_id
        )
    if expected_run_id is not None and artifact.run_id != expected_run_id:
        raise SprintRunStateMismatch(
            field="run_id", expected=expected_run_id, actual=artifact.run_id
        )

    _reject_path_component(artifact.sprint_id, name="sprint_id")

    verdict = validate_artifact_data(artifact.model_dump(mode="json"))
    if not verdict.accepted:
        raise SprintArtifactSchemaViolation(verdict.reason)

    body = _render_artifact(artifact)
    artifact_path = (
        sprint_artifacts_root / f"sprint-status-artifact-{artifact.sprint_id}.md"
    )
    _atomic_write_bundle(artifact_path, body)

    return AssembleSprintArtifactResult(
        artifact_path=artifact_path,
        sprint_id=artifact.sprint_id,
        run_id=artifact.run_id,
        current_state=artifact.current_state,
        artifact=artifact,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loud_fail_harness.sprint_status_artifact",
        description=(
            "Assemble the sprint-status artifact at sprint close (Story 16.3). "
            "A structured OBJECTIVE-ONLY artifact — NOT a retrospective. "
            "Invoked by the steps/run-sprint.md sprint-close phase via the "
            "established `python3 -m` substrate-invocation boundary (no sprint "
            "hook)."
        ),
    )
    parser.add_argument("--sprint-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--sprint-run-state-path", required=False, type=pathlib.Path, default=None
    )
    parser.add_argument(
        "--sprint-artifacts-root", required=False, type=pathlib.Path, default=None
    )
    parser.add_argument("--repo-root", required=False, type=pathlib.Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    repo_root: pathlib.Path = (
        args.repo_root if args.repo_root is not None else find_repo_root()
    )
    sprint_run_state_path: pathlib.Path = (
        args.sprint_run_state_path
        if args.sprint_run_state_path is not None
        else repo_root / DEFAULT_SPRINT_RUN_STATE_PATH
    )
    sprint_artifacts_root: pathlib.Path = (
        args.sprint_artifacts_root
        if args.sprint_artifacts_root is not None
        else repo_root / "_bmad-output" / SPRINT_ARTIFACTS_DIRNAME
    )
    try:
        result = assemble_sprint_status_artifact(
            sprint_run_state_path,
            repo_root=repo_root,
            sprint_artifacts_root=sprint_artifacts_root,
            expected_sprint_id=args.sprint_id,
            expected_run_id=args.run_id,
        )
    except (
        SprintArtifactPathInvariantViolation,
        SprintRunStateNotFound,
        SprintRunStateMismatch,
    ) as exc:
        # Pre-condition failures: bad path component, missing cache, or a cache
        # for a different sprint/run. Nothing to assemble; NOT an assembler-logic
        # failure (remediation-shape discipline) — DO NOT emit `bundle-assembly-
        # failed`.
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 1
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 — Story 6.9 outer catchall
        # Assembler-logic failure (sprint-cache shape mismatch, render crash,
        # schema-validation failure on the assembled model). Route through the
        # EXISTING surface_assembly_failure (AC-7 — no new marker class) and exit
        # with the distinct exit code. Channel 3 is per-story-RunState-bound; a
        # SprintRunState does not validate as a RunState, so it degrades — the
        # always-on fallback diagnostic file + stderr line + exit code carry the
        # signal.
        failed_step = classify_assembly_failure(exc, partial_bundle_path=None)
        try:
            surface_assembly_failure(
                story_id=args.sprint_id,
                run_id=args.run_id,
                run_state_path=sprint_run_state_path,
                bundle_root=sprint_artifacts_root,
                exc=exc,
                failed_step=failed_step,
                partial_bundle_path=None,
            )
        except Exception:  # noqa: BLE001 — best-effort; exit-code discriminator still holds
            pass
        return BUNDLE_ASSEMBLY_FAILED_EXIT_CODE
    sys.stdout.write(f"{result.artifact_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
