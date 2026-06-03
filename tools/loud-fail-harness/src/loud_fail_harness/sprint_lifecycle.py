"""Sprint-lifecycle module: sequential per-unit dispatch + sprint state machine
(story 16.1 / FR-P2-2).

Architectural placement (ADR-003 Consequence 1 + the Epic 14/15/16 substrate
chain): this module is a sibling of :mod:`loud_fail_harness.epic_lifecycle`
(story 15.1, the per-epic loop one scope down) and
:mod:`loud_fail_harness.epic_run_state` (story 14.4 shapes + story 15.1/16.1
write helpers). It is **NOT a sixth substrate component — substrate LIBRARY**
inside the orchestrator-state family. ADR-003 Consequence 1 enumerates exactly
five substrate components; this module adds a sprint-altitude composition
library, not a gate. The substrate-component count stays at FIVE; the harness
library count grows.

What this library provides:
    * **Sprint-unit enumeration** (:func:`enumerate_sprint_units`) — reads the
      ``sprint-status.yaml`` ``development_status`` section and returns, in
      document order, the contained **sprint units**: (a) every ``epic-<N>``
      whose slice holds ≥ 1 ``ready-for-dev`` story, and (b) every
      ``ready-for-dev`` story whose parent ``epic-<N>`` key is **absent** from
      ``development_status`` (an *unassigned* story) (AC-1).
    * **Sprint-run-state initialization** (:func:`init_sprint_run_state`) —
      seeds a :class:`~loud_fail_harness.epic_run_state.SprintRunState` at
      ``sprint-in-progress`` with ``per_epic_status`` seeded ``epic-in-progress``
      per epic (pre-dispatch), ``unassigned_story_ids`` enumerated, and the
      ``per_sprint_retry_budget`` STRUCTURE populated
      (``effective_budget = multiplier × epic_count``, ``consumed = 0``).
    * **Sprint state machine** (:func:`derive_sprint_state` /
      :func:`fold_epic_terminal` / :func:`fold_unassigned_story_terminal`) — the
      pure transition function ``sprint-in-progress`` →
      ``sprint-paused-on-escalation`` (any contained epic
      ``epic-paused-on-escalation`` OR any unassigned story ``escalated``) |
      ``sprint-paused-on-budget`` (any contained epic ``epic-paused-on-budget``)
      | ``sprint-complete`` (every contained epic ``epic-complete`` AND every
      unassigned story ``merge-ready`` / ``done``). Escalation keeps precedence
      over budget when both are present at the same boundary (mirrors
      ``apply_epic_budget``'s precedence one scope down).
    * **Sequential dispatch loop** (:func:`run_sprint_loop`) — drives the
      enumerated units strictly sequentially through TWO injected runner
      Protocols: :class:`EpicLoopRunner` (epic unit → in production composes the
      UNCHANGED ``epic_lifecycle.run_epic_loop`` with a per-epic-addressed path)
      and the reused :class:`~loud_fail_harness.epic_lifecycle.StoryLoopRunner`
      (unassigned story → the UNCHANGED per-story loop). After each unit reaches
      terminal it folds into the sprint aggregate, persists via
      :func:`~loud_fail_harness.epic_run_state.advance_sprint_run_state`, surfaces
      the AC-5 framing line, and STOPS on a pause (sensor-not-advisor — no
      auto-skip).

## Why the epic loop is INJECTED, not imported (AC-2 bit-identity)

The sprint flag is purely additive. This module does NOT import
:mod:`loud_fail_harness.orchestrator_run_entry` and does NOT hard-import
``run_epic_loop`` into its dispatch path: the epic loop is composed through the
:class:`EpicLoopRunner` Protocol injection, mirroring the Story 15.1
``StoryLoopRunner`` seam. Invoking ``/bmad-automation run --epic <epic-id>``
(no ``--sprint``) reaches the epic entry point untouched, and
``/bmad-automation run <story-id>`` reaches the per-story entry point untouched
— the bit-identity invariant (AC-2; precedent Story 15.1 AC-2 / Story 10.4
AC-5) is structural. The structural witness is
``test_sprint_lifecycle_does_not_import_orchestrator_run_entry``.

## Sensor-not-advisor (PRD-level invariant)

The sprint loop HALTS on a contained-unit pause/escalation; it does NOT RESOLVE
it (no auto-skip-and-continue, no auto-hold — that is the human's per AC-4). The
retrospective boundary (AC-6) is the sharpest instance: this module emits the
``sprint-run-state.yaml`` cache and NOTHING else — no retrospective artifact, no
``sprint-status-artifact-*.md`` (Story 16.3), no sprint-level PR bundle (not in
Epic 16's breakdown). The state machine signals state; the human decides
continuation.

## ``find_repo_root()`` discipline (Epic 1 retro Action #1 resolution)

``find_repo_root()`` is NOT called at module import time. Every path is caller-
supplied (``sprint_status_path``, ``sprint_run_state_path``, the optional
``repo_root`` used to address per-epic paths); the only lazy ``find_repo_root()``
reach is inside ``epic_run_state_path_for`` / ``advance_sprint_run_state`` when
the caller omits ``repo_root`` / the transient-class set — which the sprint loop
avoids by resolving the transient-class set ONCE and threading it through every
write.

## FR62 pluggability classification

Substrate-shared library per ADR-003's substrate-vs-specialist boundary;
composes :mod:`loud_fail_harness.epic_run_state` + selected names from
:mod:`loud_fail_harness.epic_lifecycle` (substrate→substrate, permitted). The
FR62 gate audits ``agents/*.md`` specialist-wrapper cross-references, not
substrate libraries.
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Callable, Mapping
from typing import ClassVar, Final, Protocol, get_args

import yaml
from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness.epic_lifecycle import (
    StoryLoopRunner,
    TERMINAL_PER_STORY_STATUSES,
)
from loud_fail_harness.epic_run_state import (
    EpicCurrentState,
    PerSprintRetryBudget,
    PerStoryStatus,
    SprintCurrentState,
    SprintRunState,
    advance_sprint_run_state,
    epic_run_state_path_for,
)
from loud_fail_harness.reconciler import load_marker_lifetimes

#: The per-sprint retry-budget multiplier used to SEED the
#: ``per_sprint_retry_budget`` structure (Story 16.1 Dev Notes scope boundary).
#: ``effective_budget = multiplier × epic_count``. Story 16.1 does NOT enforce a
#: per-sprint cumulative budget — it only reaches ``sprint-paused-on-budget`` via
#: a contained epic's own ``epic-paused-on-budget`` return. The authoritative
#: formula + config resolution (``per_sprint_retry_budget`` in ``config.yaml``)
#: is Story 16.2's deliverable; this constant is the structural seed only.
DEFAULT_PER_SPRINT_RETRY_MULTIPLIER: Final[int] = 2

_VALID_EPIC_STATES: frozenset[str] = frozenset(get_args(EpicCurrentState))
_VALID_PER_STORY_STATUSES: frozenset[str] = frozenset(get_args(PerStoryStatus))

#: Expected terminal returns from the contained epic loop (``run_epic_loop`` can
#: only reach these three at a unit boundary; ``epic-in-progress`` is never a
#: terminal return). Guards the injected runner contract.
_EXPECTED_EPIC_TERMINAL: frozenset[str] = frozenset(
    {"epic-complete", "epic-paused-on-escalation", "epic-paused-on-budget"}
)

#: Expected terminal returns from the contained per-story loop (the same set
#: ``run_epic_loop`` guards one scope down).
_EXPECTED_STORY_TERMINAL: frozenset[str] = TERMINAL_PER_STORY_STATUSES | {
    "escalated"
}

#: ``epic-<N>`` key (NOT ``epic-<N>-retrospective`` — that carries a suffix and
#: is excluded by the end-anchor). Group 1 is the epic ordinal.
_EPIC_KEY_RE: re.Pattern[str] = re.compile(r"^epic-(\d+)$")

#: ``<N>-<M>-…`` story key. Group 1 is the parent epic ordinal. The two-ordinal
#: prefix distinguishes a story key from an ``epic-<N>`` / retrospective key.
_STORY_KEY_RE: re.Pattern[str] = re.compile(r"^(\d+)-\d+(?:-.*)?$")


class SprintUnitEnumerationError(Exception):
    """Raised when the ``--sprint`` entry cannot enumerate a dispatchable unit
    set: the ``sprint-status.yaml`` file is missing or malformed, or it holds
    zero sprint units (no ``epic-<N>`` with a ``ready-for-dev`` story AND no
    unassigned ``ready-for-dev`` story).

    The sprint sibling of
    :class:`~loud_fail_harness.epic_lifecycle.EpicStoryEnumerationError`. An
    entry-time precondition diagnostic, NOT a loud-fail runtime marker —
    ``marker_class: ClassVar[None] = None``. The orchestrator surfaces it in the
    terminal stream verbatim and HALTs; no sprint PR bundle is produced at an
    enumeration halt.
    """

    marker_class: ClassVar[None] = None

    def __init__(self, *, sprint_id: str, reason: str) -> None:
        self.sprint_id: str = sprint_id
        self.reason: str = reason
        super().__init__(
            f"sprint enumeration failed for {sprint_id!r}: {reason}"
        )


class EpicLoopOutcome(BaseModel):
    """The contained epic loop's outcome the sprint loop folds (AC-2 / AC-4).

    The epic-scope analogue of
    :class:`~loud_fail_harness.epic_lifecycle.StoryLoopOutcome`. In production
    the injected :class:`EpicLoopRunner` drives one epic through the UNCHANGED
    ``epic_lifecycle.run_epic_loop`` and returns its terminal
    :data:`~loud_fail_harness.epic_run_state.EpicCurrentState`
    (``run_epic_loop(...).final_state.current_state``). Story 16.2's per-sprint
    budget will extend this envelope additively (mirroring how Story 15.2 grew
    ``StoryLoopOutcome`` with ``retries_consumed``); Story 16.1 needs only the
    terminal state to fold.

    Frozen; field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    terminal_state: EpicCurrentState


class EpicLoopRunner(Protocol):
    """The per-epic driver the sprint loop composes for each contained epic.

    In production the implementation drives one epic through the UNCHANGED
    ``epic_lifecycle.run_epic_loop`` (composing the config-resolved per-epic
    multiplier and the per-epic-addressed ``epic_run_state_path`` the sprint
    loop supplies) and returns an :class:`EpicLoopOutcome` carrying the epic's
    terminal state. Tests inject a deterministic stub.

    ``epic_run_state_path`` is supplied by the sprint loop
    (:func:`~loud_fail_harness.epic_run_state.epic_run_state_path_for`) so each
    sequential epic writes its OWN epic-run-state cache and a completed epic's
    cache survives for ``status --epic`` / ``status --sprint`` (Story 16.4 —
    AC-3 per-epic addressing). Keyword-only + non-defaulted (the project's
    structural-callback discipline; omitting an argument is a ``TypeError`` at
    call time).
    """

    def __call__(
        self,
        *,
        epic_id: str,
        index: int,
        total: int,
        epic_run_state_path: pathlib.Path,
    ) -> EpicLoopOutcome: ...


#: The sprint-progress framing sink (AC-5 / NFR-O1). Receives a formatted
#: "unit K of T" line at each unit-completion boundary. In production it writes
#: to the SAME terminal stream the contained epic/per-story loops render to (the
#: sprint layer ADDS a unit-framing line; it does NOT replace or wrap the per-
#: epic "story M of N" stream or the per-story event stream). ``None`` disables
#: sprint-progress framing (tests).
ProgressSink = Callable[[str], None]


class RunSprintLoopResult(BaseModel):
    """Return shape of :func:`run_sprint_loop`.

    The sprint-scope sibling of
    :class:`~loud_fail_harness.epic_lifecycle.RunEpicLoopResult`. Frozen for
    determinism; field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.

    Field semantics:
        * ``sprint_id`` / ``run_id`` — the sprint dispatch identifiers.
        * ``final_state`` — the PERSISTED (post-filter) terminal
          :class:`~loud_fail_harness.epic_run_state.SprintRunState`.
        * ``dispatched_unit_ids`` — the units actually driven this run, in
          dispatch order. On a pause this is a PREFIX of the enumerated units
          (the downstream units did NOT auto-advance — AC-4).
        * ``paused_on_unit_id`` — the unit (epic-id or story-id) at whose
          completion boundary the sprint paused, or ``None`` on a clean run.
        * ``wrote_path`` — the on-disk sprint-run-state cache path.
    """

    model_config = ConfigDict(frozen=True)

    sprint_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    final_state: SprintRunState
    dispatched_unit_ids: tuple[str, ...]
    paused_on_unit_id: str | None
    wrote_path: pathlib.Path


def _parse_sprint_units(
    sprint_id: str,
    *,
    sprint_status_path: pathlib.Path,
) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...], tuple[str, ...]]:
    """Read + parse ``sprint-status.yaml`` into ordered sprint units (AC-1).

    Returns ``(ordered_units, epic_units, unassigned_story_units)`` where
    ``ordered_units`` is the document-order ``(kind, unit_id)`` dispatch
    sequence (``kind`` ∈ ``{"epic", "unassigned-story"}``) and the latter two
    are the split projections (each in document order) the schema persists as
    ``epic_ids`` / ``unassigned_story_ids``.

    ``<sprint-id>`` is a FREE-FORM run label (Story 16.1 Dev Notes); the sprint
    scope is the ENTIRE ``development_status`` section. BMAD's
    ``sprint-status.yaml`` is a single-sprint artifact with no multi-sprint
    partition field at MVP, so ``sprint_id`` labels the run but does not slice
    the file. The single clearly-commented seam below is where a future BMAD
    per-sprint slice filter would attach.

    Raises:
        SprintUnitEnumerationError: the file is missing, its top-level /
            ``development_status`` shape is malformed.
    """
    if not sprint_status_path.exists():
        raise SprintUnitEnumerationError(
            sprint_id=sprint_id,
            reason=f"sprint-status file not found at {sprint_status_path}",
        )
    try:
        raw = yaml.safe_load(sprint_status_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SprintUnitEnumerationError(
            sprint_id=sprint_id,
            reason=f"sprint-status.yaml is not valid YAML: {exc}",
        ) from exc
    if not isinstance(raw, dict):
        raise SprintUnitEnumerationError(
            sprint_id=sprint_id,
            reason="sprint-status.yaml top-level is not a YAML mapping",
        )
    development_status = raw.get("development_status")
    if not isinstance(development_status, dict):
        raise SprintUnitEnumerationError(
            sprint_id=sprint_id,
            reason="sprint-status.yaml is missing the 'development_status' key",
        )

    # FORWARD-COMPAT SEAM (Story 16.1 Dev Notes): if a future BMAD release adds
    # an explicit per-sprint slice key to the sprint artifact, narrow
    # `development_status` to that slice here. No such partitioning exists at
    # MVP — `sprint_id` is a label, the whole section is the sprint scope.

    present_epic_numbers: set[str] = set()
    ready_by_epic_number: set[str] = set()
    for key, value in development_status.items():
        if not isinstance(key, str):
            continue
        epic_match = _EPIC_KEY_RE.match(key)
        if epic_match:
            present_epic_numbers.add(epic_match.group(1))
            continue
        story_match = _STORY_KEY_RE.match(key)
        if story_match and value == "ready-for-dev":
            ready_by_epic_number.add(story_match.group(1))

    ordered: list[tuple[str, str]] = []
    epic_units: list[str] = []
    unassigned_units: list[str] = []
    # Document order (yaml.safe_load preserves insertion order — the BMAD file-
    # order convention create-story follows). Epic-id-ascending is the
    # deterministic fallback only when document order is ambiguous, which an
    # ordered mapping never is, so it is never reached here.
    for key, value in development_status.items():
        if not isinstance(key, str):
            continue
        epic_match = _EPIC_KEY_RE.match(key)
        if epic_match:
            if epic_match.group(1) in ready_by_epic_number:
                epic_units.append(key)
                ordered.append(("epic", key))
            continue
        story_match = _STORY_KEY_RE.match(key)
        if story_match and value == "ready-for-dev":
            if story_match.group(1) not in present_epic_numbers:
                unassigned_units.append(key)
                ordered.append(("unassigned-story", key))

    return tuple(ordered), tuple(epic_units), tuple(unassigned_units)


def enumerate_sprint_units(
    sprint_id: str,
    *,
    sprint_status_path: pathlib.Path,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Enumerate the sprint units contained in ``sprint-status.yaml`` (AC-1).

    Returns ``(epic_units, unassigned_story_units)`` — both in document order:

        * ``epic_units`` — every ``epic-<N>`` key whose slice holds ≥ 1
          ``ready-for-dev`` story (an epic with zero ready-for-dev stories is
          excluded; an already-``done`` epic simply contributes no such story).
        * ``unassigned_story_units`` — every ``ready-for-dev`` story
          ``<N>-<M>-…`` whose parent ``epic-<N>`` key is **absent** from
          ``development_status`` (assignment is about the PRESENCE of the
          ``epic-<N>`` key, not the epic's status). Possibly empty (a sprint
          whose stories are all epic-assigned is conformant).

    Raises:
        SprintUnitEnumerationError: the sprint-status file is missing or
            malformed.
    """
    _, epic_units, unassigned_units = _parse_sprint_units(
        sprint_id, sprint_status_path=sprint_status_path
    )
    return epic_units, unassigned_units


def init_sprint_run_state(
    sprint_id: str,
    run_id: str,
    epic_ids: tuple[str, ...],
    unassigned_story_ids: tuple[str, ...],
    *,
    multiplier: int = DEFAULT_PER_SPRINT_RETRY_MULTIPLIER,
) -> SprintRunState:
    """Seed a fresh
    :class:`~loud_fail_harness.epic_run_state.SprintRunState` at
    ``sprint-in-progress`` (AC-1).

    ``per_epic_status`` is seeded ``epic-in-progress`` for each epic
    (pre-dispatch); ``unassigned_story_ids`` is recorded in document order
    (possibly empty). ``per_sprint_retry_budget`` is populated as a STRUCTURE
    (``effective_budget = multiplier × epic_count``, ``consumed = 0``); per-
    sprint budget ENFORCEMENT is Story 16.2 (Dev Notes scope boundary).
    ``active_markers`` is empty.
    """
    epic_count = len(epic_ids)
    return SprintRunState(
        schema_version="1.0",
        sprint_id=sprint_id,
        run_id=run_id,
        current_state="sprint-in-progress",
        epic_ids=tuple(epic_ids),
        per_epic_status={epic_id: "epic-in-progress" for epic_id in epic_ids},
        unassigned_story_ids=tuple(unassigned_story_ids),
        per_sprint_retry_budget=PerSprintRetryBudget(
            multiplier=multiplier,
            epic_count=epic_count,
            effective_budget=multiplier * epic_count,
            consumed=0,
        ),
        active_markers=(),
    )


def derive_sprint_state(
    per_epic_status: Mapping[str, str],
    per_unassigned_status: Mapping[str, str],
) -> SprintCurrentState:
    """Pure sprint-lifecycle transition function (AC-4).

    Precedence (escalation over budget, mirroring ``apply_epic_budget`` one
    scope down):

        1. ``sprint-paused-on-escalation`` when ANY contained epic is
           ``epic-paused-on-escalation`` OR ANY unassigned story is
           ``escalated`` (the proximate human-actionable quality signal).
        2. else ``sprint-paused-on-budget`` when ANY contained epic is
           ``epic-paused-on-budget`` (a cost signal).
        3. else ``sprint-complete`` when EVERY contained epic is
           ``epic-complete`` AND EVERY unassigned story is terminal
           (``merge-ready`` / ``done``).
        4. else ``sprint-in-progress``.

    A pure function of the two status maps only (no budget logic leaks in —
    Story 16.1 reaches ``sprint-paused-on-budget`` solely via a contained epic's
    own ``epic-paused-on-budget``, per the scope boundary). Total for the empty-
    maps degenerate case (``run_sprint_loop`` raises
    :exc:`SprintUnitEnumerationError` before reaching a zero-unit sprint).
    """
    epic_states = list(per_epic_status.values())
    story_states = list(per_unassigned_status.values())
    if any(s == "epic-paused-on-escalation" for s in epic_states) or any(
        s == "escalated" for s in story_states
    ):
        return "sprint-paused-on-escalation"
    if any(s == "epic-paused-on-budget" for s in epic_states):
        return "sprint-paused-on-budget"
    epics_done = all(s == "epic-complete" for s in epic_states)
    stories_done = all(
        s in TERMINAL_PER_STORY_STATUSES for s in story_states
    )
    if (epic_states or story_states) and epics_done and stories_done:
        return "sprint-complete"
    return "sprint-in-progress"


def fold_epic_terminal(
    sprint_state: SprintRunState,
    epic_id: str,
    terminal_state: str,
    *,
    per_unassigned_status: Mapping[str, str],
) -> SprintRunState:
    """Fold one epic unit's terminal state into the sprint aggregate (pure).

    Updates ``per_epic_status[epic_id]`` and recomputes ``current_state`` via
    :func:`derive_sprint_state` (threading the current ``per_unassigned_status``
    — that map is NOT a persisted ``SprintRunState`` field; it is re-derivable
    from the per-story story-docs on recovery per ADR-005 / NFR-R8, and is
    tracked transiently by :func:`run_sprint_loop`). Returns a NEW
    :class:`SprintRunState` (frozen-model discipline — the input is never
    mutated). Does NOT persist (the caller composes
    :func:`~loud_fail_harness.epic_run_state.advance_sprint_run_state`).

    Raises:
        ValueError: ``epic_id`` is not a contained epic, OR ``terminal_state``
            is not a valid ``EpicCurrentState`` value (guards the ``model_copy``
            re-validation gap — ``model_copy`` does not re-run field
            validation).
    """
    if epic_id not in sprint_state.per_epic_status:
        raise ValueError(
            f"fold_epic_terminal: {epic_id!r} is not a contained epic of "
            f"sprint {sprint_state.sprint_id!r}"
        )
    if terminal_state not in _EXPECTED_EPIC_TERMINAL:
        raise ValueError(
            f"fold_epic_terminal: {terminal_state!r} is not a terminal epic "
            f"state; expected one of {sorted(_EXPECTED_EPIC_TERMINAL)}"
        )
    new_per_epic: dict[str, str] = dict(sprint_state.per_epic_status)
    new_per_epic[epic_id] = terminal_state
    return sprint_state.model_copy(
        update={
            "per_epic_status": new_per_epic,
            "current_state": derive_sprint_state(
                new_per_epic, per_unassigned_status
            ),
        }
    )


def fold_unassigned_story_terminal(
    sprint_state: SprintRunState,
    story_id: str,
    terminal_status: str,
    *,
    per_unassigned_status: Mapping[str, str],
) -> tuple[SprintRunState, dict[str, str]]:
    """Fold one unassigned-story unit's terminal status into the sprint
    aggregate (pure).

    Returns ``(new_sprint_state, new_per_unassigned_status)``. The unassigned-
    story status map is NOT a persisted ``SprintRunState`` field (the schema
    carries ``unassigned_story_ids`` but no per-story status aggregate — the
    statuses are re-derivable from the per-story story-docs on recovery per
    ADR-005 / NFR-R8), so this helper returns the updated map alongside the new
    state rather than mutating a model field — the (mild) asymmetry with
    :func:`fold_epic_terminal` is the schema shape made explicit. Recomputes
    ``current_state`` via :func:`derive_sprint_state`. Does NOT persist.

    Raises:
        ValueError: ``story_id`` is not a contained unassigned story, OR
            ``terminal_status`` is not a valid ``PerStoryStatus`` value.
    """
    if story_id not in sprint_state.unassigned_story_ids:
        raise ValueError(
            f"fold_unassigned_story_terminal: {story_id!r} is not a contained "
            f"unassigned story of sprint {sprint_state.sprint_id!r}"
        )
    if terminal_status not in _EXPECTED_STORY_TERMINAL:
        raise ValueError(
            f"fold_unassigned_story_terminal: {terminal_status!r} is not a "
            f"terminal per-story status; expected one of "
            f"{sorted(_EXPECTED_STORY_TERMINAL)}"
        )
    new_per_unassigned: dict[str, str] = dict(per_unassigned_status)
    new_per_unassigned[story_id] = terminal_status
    new_state = sprint_state.model_copy(
        update={
            "current_state": derive_sprint_state(
                sprint_state.per_epic_status, new_per_unassigned
            ),
        }
    )
    return new_state, new_per_unassigned


def _format_sprint_progress(
    index: int,
    total: int,
    unit_id: str,
    outcome_state: str,
    sprint_state: str,
) -> str:
    """Format the AC-5 "unit K of T" sprint-progress framing line."""
    return (
        f"[sprint] unit {index} of {total} ({unit_id}) → {outcome_state}; "
        f"sprint now {sprint_state}"
    )


def run_sprint_loop(
    sprint_id: str,
    *,
    run_id: str,
    sprint_status_path: pathlib.Path,
    sprint_run_state_path: pathlib.Path,
    epic_loop_runner: EpicLoopRunner,
    story_loop_runner: StoryLoopRunner,
    repo_root: pathlib.Path | None = None,
    multiplier: int = DEFAULT_PER_SPRINT_RETRY_MULTIPLIER,
    progress_sink: ProgressSink | None = None,
    transient_marker_classes: frozenset[str] | None = None,
    taxonomy_path: pathlib.Path | None = None,
) -> RunSprintLoopResult:
    """Drive a sprint's units (epics + unassigned stories) sequentially in
    document order, advancing sprint-run-state after each (AC-1..AC-8).

    Composition (the canonical sprint loop ``steps/run-sprint.md`` names):

        1. **Enumerate** the sprint units via :func:`_parse_sprint_units`
           (document order; AC-1). Zero units → :exc:`SprintUnitEnumerationError`.
        2. **Initialize** the sprint-run-state cache via
           :func:`init_sprint_run_state` and persist it via
           :func:`~loud_fail_harness.epic_run_state.advance_sprint_run_state`
           (atomic write + transient-marker filter; AC-1 / AC-3 / AC-7).
        3. **Dispatch sequentially** — for each unit in order, drive an EPIC
           unit through the injected ``epic_loop_runner`` (supplying a per-epic-
           addressed ``epic_run_state_path`` via
           :func:`~loud_fail_harness.epic_run_state.epic_run_state_path_for`;
           AC-3) or an UNASSIGNED STORY unit through the injected
           ``story_loop_runner`` (the UNCHANGED per-story loop; AC-2), fold the
           terminal outcome into the sprint aggregate, persist the advance, and
           surface the "unit K of T" framing line via ``progress_sink`` (AC-5).
        4. **Pause on a contained-unit pause/escalation** — when folding a unit
           transitions the sprint to ``sprint-paused-on-escalation`` /
           ``sprint-paused-on-budget``, STOP; the downstream units do NOT auto-
           advance (AC-4; sensor-not-advisor).

    Units run strictly sequentially (parallel is Epic 18 — no concurrent
    dispatch here; AC-2). The transient-class set is resolved ONCE and threaded
    through every ``advance_sprint_run_state`` call so a recovery-recomputed
    transient marker never persists into the aggregate (AC-7). This story emits
    NO retrospective artifact and NO ``sprint-status-artifact-*.md`` (AC-6) —
    the only persisted output is the ``sprint-run-state.yaml`` cache plus the
    per-unit caches the contained loops already write.

    Args:
        sprint_id: Free-form sprint run label (Story 16.1 Dev Notes — it labels
            the run; it does NOT slice ``development_status``).
        run_id: Orchestrator-domain identifier correlating the sprint dispatch
            with the ``sprint-run-state.yaml`` record (ADR-005 Consequence 1).
        sprint_status_path: Caller-controlled path to ``sprint-status.yaml``.
        sprint_run_state_path: Caller-controlled on-disk path for the sprint-
            run-state cache.
        epic_loop_runner: The per-epic driver Protocol (AC-2). Returns an
            :class:`EpicLoopOutcome` carrying the epic's terminal state.
        story_loop_runner: The UNCHANGED per-story driver Protocol reused from
            Epic 15 (AC-2), for unassigned-story units.
        repo_root: Optional root for per-epic ``epic_run_state_path_for``
            addressing (tests pass ``tmp_path``; the orchestrator knows its own
            root). When ``None`` the path helper resolves ``find_repo_root()``
            at call time.
        multiplier: The per-sprint retry-budget multiplier seeding the budget
            STRUCTURE (Story 16.2 owns enforcement + config resolution).
        progress_sink: Optional sprint-progress framing sink (AC-5).
        transient_marker_classes / taxonomy_path: Forwarded to
            ``advance_sprint_run_state`` (AC-7).

    Returns:
        :class:`RunSprintLoopResult` with the terminal sprint state, the
        dispatched prefix, and the pausing unit (if any).

    Raises:
        SprintUnitEnumerationError: enumeration yielded no dispatchable units,
            or the sprint-status section was malformed.
    """
    ordered_units, epic_units, unassigned_units = _parse_sprint_units(
        sprint_id, sprint_status_path=sprint_status_path
    )
    if not ordered_units:
        raise SprintUnitEnumerationError(
            sprint_id=sprint_id,
            reason=(
                "sprint contains no dispatchable units (no epic with a "
                "ready-for-dev story and no unassigned ready-for-dev story)"
            ),
        )

    # Resolve the transient-class set ONCE before the dispatch loop so every
    # advance_sprint_run_state call receives a pre-resolved frozenset rather
    # than triggering a taxonomy file read on each call (the per-call-taxonomy-
    # read pattern Story 15.1's review explicitly corrected; AC-7).
    if transient_marker_classes is None:
        lifetimes = load_marker_lifetimes(taxonomy_path)
        transient_marker_classes = frozenset(
            mc for mc, lt in lifetimes.items() if lt == "transient"
        )

    sprint_state = init_sprint_run_state(
        sprint_id, run_id, epic_units, unassigned_units, multiplier=multiplier
    )
    advance = advance_sprint_run_state(
        sprint_run_state_path,
        sprint_state,
        transient_marker_classes=transient_marker_classes,
    )
    sprint_state = advance.next_state

    # Unassigned-story statuses are tracked transiently here (not a persisted
    # SprintRunState field — re-derivable from the per-story story-docs per
    # ADR-005 / NFR-R8). Seeded ready-for-dev (the enumeration filter).
    per_unassigned_status: dict[str, str] = {
        story_id: "ready-for-dev" for story_id in unassigned_units
    }

    total = len(ordered_units)
    dispatched: list[str] = []
    paused_on: str | None = None

    for index, (kind, unit_id) in enumerate(ordered_units, start=1):
        if kind == "epic":
            epic_path = epic_run_state_path_for(unit_id, repo_root=repo_root)
            epic_outcome = epic_loop_runner(
                epic_id=unit_id,
                index=index,
                total=total,
                epic_run_state_path=epic_path,
            )
            outcome_state: str = epic_outcome.terminal_state
            if outcome_state not in _EXPECTED_EPIC_TERMINAL:
                raise ValueError(
                    f"epic_loop_runner returned non-terminal state "
                    f"{outcome_state!r} for epic {unit_id!r}; expected one of "
                    f"{sorted(_EXPECTED_EPIC_TERMINAL)}"
                )
            sprint_state = fold_epic_terminal(
                sprint_state,
                unit_id,
                outcome_state,
                per_unassigned_status=per_unassigned_status,
            )
        else:
            story_outcome = story_loop_runner(
                story_id=unit_id, index=index, total=total
            )
            outcome_state = story_outcome.terminal_status
            if outcome_state not in _EXPECTED_STORY_TERMINAL:
                raise ValueError(
                    f"story_loop_runner returned non-terminal status "
                    f"{outcome_state!r} for story {unit_id!r}; expected one of "
                    f"{sorted(_EXPECTED_STORY_TERMINAL)}"
                )
            sprint_state, per_unassigned_status = fold_unassigned_story_terminal(
                sprint_state,
                unit_id,
                outcome_state,
                per_unassigned_status=per_unassigned_status,
            )

        advance = advance_sprint_run_state(
            sprint_run_state_path,
            sprint_state,
            transient_marker_classes=transient_marker_classes,
        )
        sprint_state = advance.next_state
        dispatched.append(unit_id)
        if progress_sink is not None:
            progress_sink(
                _format_sprint_progress(
                    index,
                    total,
                    unit_id,
                    outcome_state,
                    sprint_state.current_state,
                )
            )
        if sprint_state.current_state in (
            "sprint-paused-on-escalation",
            "sprint-paused-on-budget",
        ):
            paused_on = unit_id
            break

    return RunSprintLoopResult(
        sprint_id=sprint_id,
        run_id=run_id,
        final_state=sprint_state,
        dispatched_unit_ids=tuple(dispatched),
        paused_on_unit_id=paused_on,
        wrote_path=sprint_run_state_path,
    )


__all__ = [
    "DEFAULT_PER_SPRINT_RETRY_MULTIPLIER",
    "EpicLoopOutcome",
    "EpicLoopRunner",
    "ProgressSink",
    "RunSprintLoopResult",
    "SprintUnitEnumerationError",
    "derive_sprint_state",
    "enumerate_sprint_units",
    "fold_epic_terminal",
    "fold_unassigned_story_terminal",
    "init_sprint_run_state",
    "run_sprint_loop",
]
