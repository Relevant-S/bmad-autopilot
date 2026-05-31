"""Epic-lifecycle module: sequential per-story dispatch + epic state machine
(story 15.1 / FR-P2-1).

Architectural placement (ADR-003 Consequence 1 + the Epic 14/15 substrate
chain): this module is a sibling of :mod:`loud_fail_harness.orchestrator_run_entry`
(story 2.5, the per-story entry sequence) and :mod:`loud_fail_harness.epic_run_state`
(story 14.4 shapes + story 15.1 ``advance_epic_run_state``). It is **NOT a sixth
substrate component — substrate LIBRARY** inside the orchestrator-state family.
ADR-003 Consequence 1 enumerates exactly five substrate components; this module
adds an epic-altitude composition library, not a gate. The substrate-component
count stays at FIVE; the harness library count grows.

What this library provides:
    * **Story enumeration** (:func:`enumerate_epic_stories`) — reads the
      ``sprint-status.yaml`` ``development_status`` slice for an ``epic-id``
      and returns the contained ``ready-for-dev`` story keys in epic-defined
      (key-ascending) order (AC-1).
    * **Epic-run-state initialization** (:func:`init_epic_run_state`) — seeds an
      :class:`~loud_fail_harness.epic_run_state.EpicRunState` at
      ``epic-in-progress`` with ``per_story_status`` seeded from each story's
      current lifecycle state, the ``per_epic_retry_budget`` STRUCTURE populated
      (enforcement is Story 15.2), and the ``per_epic_cost_partition`` zeroed
      (AC-1).
    * **Epic state machine** (:func:`derive_epic_state` / :func:`fold_story_terminal`)
      — the pure transition function ``epic-in-progress`` →
      ``epic-paused-on-escalation`` (any contained story ``escalated``) |
      ``epic-complete`` (all contained stories terminal). ``epic-paused-on-budget``
      is reachable only once Story 15.2 lands — NOT implemented here (scope
      boundary).
    * **Sequential dispatch loop** (:func:`run_epic_loop`) — drives the
      enumerated stories strictly sequentially through an INJECTED per-story
      ``story_loop_runner`` (in production the unchanged Phase-1 + 1.5
      ``run_story_loop_entry`` → Dev → review-seam → QA → merge-ready/escalated
      sequence; in tests a deterministic stub), folding each story's terminal
      status into the epic aggregate and persisting via
      :func:`~loud_fail_harness.epic_run_state.advance_epic_run_state` after each
      story. On escalation it STOPS (sensor-not-advisor — no auto-skip).

## Why the per-story loop is INJECTED, not imported (AC-2 bit-identity)

The epic flag is purely additive: this module does NOT import
:mod:`loud_fail_harness.orchestrator_run_entry`, does NOT wrap, decorate, or
re-shape ``run_story_loop_entry``, and does NOT touch the per-story
:class:`~loud_fail_harness.run_state.RunState`. It composes the per-story loop
through the :class:`StoryLoopRunner` Protocol injection. Invoking
``/bmad-automation run <story-id>`` (no ``--epic``) reaches the per-story entry
point untouched — the bit-identity invariant (AC-2; precedent Story 10.4 AC-5)
is structural, not asserted-by-diff. The structural witness is
``test_epic_lifecycle_does_not_import_orchestrator_run_entry``.

## Sensor-not-advisor (PRD-level invariant)

The epic loop HALTS on escalation; it does NOT RESOLVE the escalation (no
auto-skip-and-continue, no auto-hold decision — that is the human's per AC-4).
Flow policy that *halts* is in scope; flow policy that *resolves an escalation*
is not. The state machine signals state; the human decides continuation.

## ``find_repo_root()`` discipline (Epic 1 retro Action #1 resolution)

``find_repo_root()`` is NOT called at module import time. Every path is caller-
supplied (``sprint_status_path``, ``epic_run_state_path``); the only lazy
``find_repo_root()`` reach is inside ``advance_epic_run_state`` when neither a
``transient_marker_classes`` set nor a ``taxonomy_path`` is supplied — which the
epic loop avoids by resolving the transient-class set ONCE and threading it
through every write.

## FR62 pluggability classification

Substrate-shared library per ADR-003's substrate-vs-specialist boundary;
composes :mod:`loud_fail_harness.epic_run_state` (substrate→substrate, permitted).
The FR62 gate audits ``agents/*.md`` specialist-wrapper cross-references, not
substrate libraries.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable, Mapping
from typing import ClassVar, Protocol, get_args

import yaml
from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness.epic_run_state import (
    EpicCurrentState,
    EpicRunState,
    PerEpicCostPartition,
    PerEpicRetryBudget,
    PerStoryStatus,
    advance_epic_run_state,
)
from loud_fail_harness.reconciler import load_marker_lifetimes

#: Per-story statuses that count as terminal-and-successful for the
#: ``epic-complete`` transition (Story 15.3 line 423 + AC-3). ``escalated`` is
#: terminal-but-PAUSED — handled separately (it drives
#: ``epic-paused-on-escalation``, NOT ``epic-complete``).
TERMINAL_PER_STORY_STATUSES: frozenset[str] = frozenset({"merge-ready", "done"})

#: Default per-epic retry-budget multiplier (Story 15.2's
#: ``per_epic_retry_budget_multiplier``; effective budget = multiplier ×
#: story_count). The STRUCTURE is populated here; ENFORCEMENT is Story 15.2.
DEFAULT_PER_EPIC_RETRY_MULTIPLIER: int = 2

_VALID_PER_STORY_STATUSES: frozenset[str] = frozenset(get_args(PerStoryStatus))


class EpicStoryEnumerationError(Exception):
    """Raised when the ``--epic`` entry cannot enumerate a dispatchable story
    set: the ``sprint-status.yaml`` file is missing or malformed, the
    ``epic-id`` is not a parseable ``epic-<N>`` identifier, or the epic
    contains zero ``ready-for-dev`` stories.

    Entry-time precondition diagnostic, NOT a loud-fail runtime marker —
    ``marker_class: ClassVar[None] = None`` mirrors the per-story entry's
    ``StoryDocNotFound`` / ``SprintStatusMismatch`` family (``steps/run.md``
    pre-flight phase). The orchestrator surfaces it in the terminal stream;
    no PR bundle is produced when the epic entry halts at enumeration.
    """

    marker_class: ClassVar[None] = None

    def __init__(self, *, epic_id: str, reason: str) -> None:
        self.epic_id: str = epic_id
        self.reason: str = reason
        super().__init__(f"epic enumeration failed for {epic_id!r}: {reason}")


class StoryLoopRunner(Protocol):
    """The per-story driver the epic loop composes for each contained story.

    In production the implementation drives one story through the UNCHANGED
    per-story loop (``run_story_loop_entry`` → Dev → review-seam → QA → merge-
    ready/escalated per ``steps/run.md``, reusing the per-story
    ``event_log_appender`` within the story per AC-5) and returns the story's
    terminal :data:`~loud_fail_harness.epic_run_state.PerStoryStatus`. Tests
    inject a deterministic stub. Keyword-only + non-defaulted (the project's
    structural-callback discipline; omitting an argument is a ``TypeError`` at
    call time).
    """

    def __call__(self, *, story_id: str, index: int, total: int) -> str: ...


#: The epic-progress framing sink (AC-5 / NFR-O1). Receives a formatted
#: "story M of N" line at each per-story completion boundary. In production it
#: writes to the SAME terminal stream the per-story ``event_log_appender``
#: renders to (the epic layer ADDS a framing line; it does NOT replace or wrap
#: the per-story stream). ``None`` disables epic-progress framing (tests).
ProgressSink = Callable[[str], None]


class RunEpicLoopResult(BaseModel):
    """Return shape of :func:`run_epic_loop`.

    Frozen for hashability + determinism; field declaration order is load-
    bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``epic_id`` / ``run_id`` — the epic dispatch identifiers.
        * ``final_state`` — the PERSISTED (post-filter) terminal
          :class:`~loud_fail_harness.epic_run_state.EpicRunState`. Its
          ``current_state`` is ``epic-complete`` on a clean run OR
          ``epic-paused-on-escalation`` when a contained story escalated.
        * ``dispatched_story_ids`` — the stories actually driven this run, in
          dispatch order. On escalation this is a PREFIX of ``story_ids`` (the
          downstream stories did NOT auto-advance — AC-4).
        * ``paused_on_story_id`` — the story whose escalation paused the epic,
          or ``None`` on a clean run.
        * ``wrote_path`` — the on-disk epic-run-state cache path.
    """

    model_config = ConfigDict(frozen=True)

    epic_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    final_state: EpicRunState
    dispatched_story_ids: tuple[str, ...]
    paused_on_story_id: str | None
    wrote_path: pathlib.Path


def _parse_epic_number(epic_id: str) -> str:
    """Extract the numeric epic ordinal from an ``epic-<N>`` identifier.

    Raises :exc:`EpicStoryEnumerationError` when ``epic_id`` is not of the
    ``epic-<N>`` shape (loud-fail at the entry boundary).
    """
    prefix = "epic-"
    suffix = epic_id[len(prefix):]
    if not epic_id.startswith(prefix) or not suffix or not suffix.isdigit():
        raise EpicStoryEnumerationError(
            epic_id=epic_id,
            reason="epic_id must be of the form 'epic-<N>' (e.g. 'epic-15')",
        )
    return suffix


def _story_sort_key(story_key: str, epic_number: str) -> tuple[int, str]:
    """Sort key for "key-ascending" story order (AC-1).

    Sorts by the integer story ordinal (the segment after ``<epic_number>-``)
    so ``15-2-*`` precedes ``15-10-*`` (a plain lexical sort would invert
    them). Falls back to a large sentinel + the raw key for non-numeric
    ordinals so the sort is total and deterministic.
    """
    remainder = story_key[len(epic_number) + 1:]
    ordinal_text = remainder.split("-", 1)[0]
    ordinal = int(ordinal_text) if ordinal_text.isdigit() else (1 << 62)
    return (ordinal, story_key)


def enumerate_epic_stories(
    epic_id: str,
    *,
    sprint_status_path: pathlib.Path,
) -> tuple[str, ...]:
    """Enumerate the ``ready-for-dev`` stories contained in ``epic_id`` from
    the ``sprint-status.yaml`` ``development_status`` slice (AC-1).

    The slice for ``epic-15`` is every ``development_status`` key matching
    ``15-*`` (e.g. ``15-1-...``) — epic/retrospective keys (``epic-15`` /
    ``epic-15-retrospective``) start with ``epic-`` and are excluded by the
    ``<N>-`` prefix test. Only entries whose status is ``ready-for-dev`` are
    returned, in key-ascending (numeric-ordinal) order.

    Raises:
        EpicStoryEnumerationError: ``epic_id`` is not ``epic-<N>``; the
            sprint-status file is missing; or its top-level / ``development_status``
            shape is malformed.
    """
    epic_number = _parse_epic_number(epic_id)
    if not sprint_status_path.exists():
        raise EpicStoryEnumerationError(
            epic_id=epic_id,
            reason=f"sprint-status file not found at {sprint_status_path}",
        )
    raw = yaml.safe_load(sprint_status_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise EpicStoryEnumerationError(
            epic_id=epic_id,
            reason="sprint-status.yaml top-level is not a YAML mapping",
        )
    development_status = raw.get("development_status")
    if not isinstance(development_status, dict):
        raise EpicStoryEnumerationError(
            epic_id=epic_id,
            reason="sprint-status.yaml is missing the 'development_status' key",
        )
    story_prefix = f"{epic_number}-"
    matched = [
        key
        for key, value in development_status.items()
        if isinstance(key, str)
        and key.startswith(story_prefix)
        and value == "ready-for-dev"
    ]
    matched.sort(key=lambda key: _story_sort_key(key, epic_number))
    return tuple(matched)


def init_epic_run_state(
    epic_id: str,
    run_id: str,
    story_ids: tuple[str, ...],
    *,
    per_story_status_seed: Mapping[str, str] | None = None,
    multiplier: int = DEFAULT_PER_EPIC_RETRY_MULTIPLIER,
) -> EpicRunState:
    """Seed a fresh :class:`~loud_fail_harness.epic_run_state.EpicRunState`
    at ``epic-in-progress`` (AC-1).

    ``per_story_status`` is seeded from each story's current lifecycle state —
    the enumerated stories are all ``ready-for-dev`` (the enumeration filter),
    so the default seed is ``ready-for-dev`` per story; callers may override via
    ``per_story_status_seed`` (e.g. a resumed epic re-deriving statuses from the
    per-story story-docs). ``per_epic_retry_budget`` is populated as a STRUCTURE
    (effective_budget = multiplier × story_count, consumed = 0) — ENFORCEMENT is
    Story 15.2. ``per_epic_cost_partition`` is zeroed; ``active_markers`` is
    empty.
    """
    if per_story_status_seed is not None:
        seed = dict(per_story_status_seed)
        extra = set(seed.keys()) - set(story_ids)
        missing = set(story_ids) - set(seed.keys())
        if extra or missing:
            raise ValueError(
                f"per_story_status_seed keys do not match story_ids: "
                f"extra={sorted(extra)!r}, missing={sorted(missing)!r}"
            )
    else:
        seed = {story_id: "ready-for-dev" for story_id in story_ids}
    story_count = len(story_ids)
    return EpicRunState(
        schema_version="1.0",
        epic_id=epic_id,
        run_id=run_id,
        current_state="epic-in-progress",
        story_ids=tuple(story_ids),
        per_story_status=seed,  # type: ignore[arg-type]
        per_epic_retry_budget=PerEpicRetryBudget(
            multiplier=multiplier,
            story_count=story_count,
            effective_budget=multiplier * story_count,
            consumed=0,
        ),
        per_epic_cost_partition=PerEpicCostPartition(
            per_story_cost={story_id: 0.0 for story_id in story_ids},
            epic_cost_total=0.0,
        ),
        active_markers=(),
    )


def derive_epic_state(
    per_story_status: Mapping[str, str],
) -> EpicCurrentState:
    """Pure epic-lifecycle transition function (AC-3 + AC-4).

    ``epic-paused-on-escalation`` when ANY contained story is ``escalated``
    (sensor-not-advisor — the epic halts, the human decides continuation);
    else ``epic-complete`` when EVERY contained story is terminal
    (``merge-ready`` / ``done``); else ``epic-in-progress``.
    ``epic-paused-on-budget`` is NOT reachable here (Story 15.2 owns budget
    enforcement; the enum member is left unreached per the scope boundary).
    """
    statuses = list(per_story_status.values())
    if any(status == "escalated" for status in statuses):
        return "epic-paused-on-escalation"
    if statuses and all(
        status in TERMINAL_PER_STORY_STATUSES for status in statuses
    ):
        return "epic-complete"
    return "epic-in-progress"


def fold_story_terminal(
    epic_state: EpicRunState,
    story_id: str,
    terminal_status: str,
) -> EpicRunState:
    """Fold one story's terminal status into the epic aggregate (pure).

    Updates ``per_story_status[story_id]`` and recomputes ``current_state`` via
    :func:`derive_epic_state`; returns a NEW :class:`EpicRunState` (frozen-model
    discipline — the input is never mutated). Does NOT persist (the caller
    composes :func:`~loud_fail_harness.epic_run_state.advance_epic_run_state`).

    Raises:
        ValueError: ``story_id`` is not a contained story, OR ``terminal_status``
            is not a valid ``PerStoryStatus`` value (guards the
            ``model_copy`` re-validation gap — ``model_copy`` does not re-run
            field validation).
    """
    if story_id not in epic_state.per_story_status:
        raise ValueError(
            f"fold_story_terminal: {story_id!r} is not a contained story of "
            f"epic {epic_state.epic_id!r}"
        )
    if terminal_status not in _VALID_PER_STORY_STATUSES:
        raise ValueError(
            f"fold_story_terminal: {terminal_status!r} is not a valid "
            f"per-story status"
        )
    new_status: dict[str, str] = dict(epic_state.per_story_status)
    new_status[story_id] = terminal_status
    return epic_state.model_copy(
        update={
            "per_story_status": new_status,
            "current_state": derive_epic_state(new_status),
        }
    )


def _format_epic_progress(
    index: int,
    total: int,
    story_id: str,
    terminal_status: str,
    epic_state: str,
) -> str:
    """Format the AC-5 "story M of N" epic-progress framing line."""
    return (
        f"[epic] story {index} of {total} ({story_id}) → {terminal_status}; "
        f"epic now {epic_state}"
    )


def run_epic_loop(
    epic_id: str,
    *,
    run_id: str,
    sprint_status_path: pathlib.Path,
    epic_run_state_path: pathlib.Path,
    story_loop_runner: StoryLoopRunner,
    progress_sink: ProgressSink | None = None,
    transient_marker_classes: frozenset[str] | None = None,
    taxonomy_path: pathlib.Path | None = None,
) -> RunEpicLoopResult:
    """Drive an epic's ``ready-for-dev`` stories sequentially through the
    per-story loop, advancing epic-run-state after each (AC-1..AC-5).

    Composition (the canonical epic loop ``steps/run-epic.md`` names):

        1. **Enumerate** the contained ``ready-for-dev`` stories via
           :func:`enumerate_epic_stories` (key-ascending order; AC-1).
        2. **Initialize** the epic-run-state cache via
           :func:`init_epic_run_state` and persist it via
           :func:`~loud_fail_harness.epic_run_state.advance_epic_run_state`
           (atomic write + transient-marker filter; AC-1 / AC-3 / AC-6).
        3. **Dispatch sequentially** — for each story in order, invoke the
           injected ``story_loop_runner`` (the UNCHANGED per-story loop;
           AC-2), fold its terminal status into the aggregate
           (:func:`fold_story_terminal`), persist the advance, and surface the
           "story M of N" framing line via ``progress_sink`` (AC-5).
        4. **Pause on escalation** — if folding a story's terminal status
           transitions the epic to ``epic-paused-on-escalation``, STOP; the
           downstream stories do NOT auto-advance (AC-4; sensor-not-advisor).

    Stories run strictly sequentially (parallel is Epic 18 — no concurrent
    dispatch here; AC-2). The transient-class set is resolved ONCE and threaded
    through every ``advance_epic_run_state`` call so a recovery-recomputed
    transient marker never persists into the aggregate (AC-6).

    Args:
        epic_id: The ``epic-<N>`` identifier the practitioner passed at
            ``/bmad-automation run --epic <epic-id>``.
        run_id: Orchestrator-domain identifier correlating the epic dispatch
            with the ``epic-run-state.yaml`` record (ADR-005 Consequence 1).
        sprint_status_path: Caller-controlled path to ``sprint-status.yaml``.
        epic_run_state_path: Caller-controlled on-disk path for the epic-run-
            state cache.
        story_loop_runner: The per-story driver Protocol (AC-2).
        progress_sink: Optional epic-progress framing sink (AC-5).
        transient_marker_classes / taxonomy_path: Forwarded to
            ``advance_epic_run_state`` (AC-6).

    Returns:
        :class:`RunEpicLoopResult` with the terminal epic state, the dispatched
        prefix, and the pausing story (if any).

    Raises:
        EpicStoryEnumerationError: enumeration yielded no dispatchable stories,
            or the sprint-status slice was malformed.
    """
    story_ids = enumerate_epic_stories(
        epic_id, sprint_status_path=sprint_status_path
    )
    if not story_ids:
        raise EpicStoryEnumerationError(
            epic_id=epic_id,
            reason="epic contains no ready-for-dev stories to dispatch",
        )

    # Resolve the transient-class set ONCE before the dispatch loop so every
    # advance_epic_run_state call receives a pre-resolved frozenset rather than
    # triggering a taxonomy file read on each call (doc invariant, AC-6).
    if transient_marker_classes is None:
        lifetimes = load_marker_lifetimes(taxonomy_path)
        transient_marker_classes = frozenset(
            mc for mc, lt in lifetimes.items() if lt == "transient"
        )

    epic_state = init_epic_run_state(epic_id, run_id, story_ids)
    advance = advance_epic_run_state(
        epic_run_state_path,
        epic_state,
        transient_marker_classes=transient_marker_classes,
    )
    epic_state = advance.next_state

    total = len(story_ids)
    dispatched: list[str] = []
    paused_on: str | None = None
    _expected_terminal = TERMINAL_PER_STORY_STATUSES | {"escalated"}

    for index, story_id in enumerate(story_ids, start=1):
        terminal_status = story_loop_runner(
            story_id=story_id, index=index, total=total
        )
        if terminal_status not in _expected_terminal:
            raise ValueError(
                f"story_loop_runner returned non-terminal status "
                f"{terminal_status!r} for story {story_id!r}; "
                f"expected one of {sorted(_expected_terminal)}"
            )
        epic_state = fold_story_terminal(epic_state, story_id, terminal_status)
        advance = advance_epic_run_state(
            epic_run_state_path,
            epic_state,
            transient_marker_classes=transient_marker_classes,
        )
        epic_state = advance.next_state
        dispatched.append(story_id)
        if progress_sink is not None:
            progress_sink(
                _format_epic_progress(
                    index,
                    total,
                    story_id,
                    terminal_status,
                    epic_state.current_state,
                )
            )
        if epic_state.current_state == "epic-paused-on-escalation":
            paused_on = story_id
            break

    return RunEpicLoopResult(
        epic_id=epic_id,
        run_id=run_id,
        final_state=epic_state,
        dispatched_story_ids=tuple(dispatched),
        paused_on_story_id=paused_on,
        wrote_path=epic_run_state_path,
    )


__all__ = [
    "DEFAULT_PER_EPIC_RETRY_MULTIPLIER",
    "EpicStoryEnumerationError",
    "ProgressSink",
    "RunEpicLoopResult",
    "StoryLoopRunner",
    "TERMINAL_PER_STORY_STATUSES",
    "derive_epic_state",
    "enumerate_epic_stories",
    "fold_story_terminal",
    "init_epic_run_state",
    "run_epic_loop",
]
