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
      current lifecycle state, the ``per_epic_retry_budget`` populated
      (``effective_budget = multiplier × story_count``, ``consumed = 0``), and the ``per_epic_cost_partition`` zeroed
      (AC-1).
    * **Epic state machine** (:func:`derive_epic_state` / :func:`fold_story_terminal`)
      — the pure transition function ``epic-in-progress`` →
      ``epic-paused-on-escalation`` (any contained story ``escalated``) |
      ``epic-complete`` (all contained stories terminal); ``epic-paused-on-budget``
      when the cumulative per-epic retry budget is exhausted with undispatched stories
      remaining (layered on top by :func:`apply_epic_budget`).
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
from typing import TYPE_CHECKING, ClassVar, Final, Literal, Protocol, get_args

import yaml
from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness.epic_run_state import (
    EpicCurrentState,
    EpicRunState,
    PerEpicCostPartition,
    PerEpicRetryBudget,
    PerStoryStatus,
    advance_epic_run_state,
    load_epic_run_state,
    reconstruct_budget_on_resume,
)
from loud_fail_harness.reconciler import load_marker_lifetimes
from loud_fail_harness.retry_budget import (
    DEFAULT_MAX_PARALLEL_STORIES,
    DEFAULT_PER_EPIC_RETRY_MULTIPLIER,
)

if TYPE_CHECKING:
    from loud_fail_harness.parallel_dispatch import ParallelStoryLoopRunner

#: Per-story statuses that count as terminal-and-successful for the
#: ``epic-complete`` transition (Story 15.3 line 423 + AC-3). ``escalated`` is
#: terminal-but-PAUSED — handled separately (it drives
#: ``epic-paused-on-escalation``, NOT ``epic-complete``).
TERMINAL_PER_STORY_STATUSES: frozenset[str] = frozenset({"merge-ready", "done"})


#: The marker class identifier sourced VERBATIM from
#: ``schemas/marker-taxonomy.yaml`` (entry ``epic-budget-exhausted``).
#: Single-source-of-truth posture mirroring
#: :data:`loud_fail_harness.retry_budget_exhaustion.RETRY_BUDGET_EXHAUSTED_MARKER`.
EPIC_BUDGET_EXHAUSTED_MARKER: Final[Literal["epic-budget-exhausted"]] = (
    "epic-budget-exhausted"
)

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


class StoryLoopOutcome(BaseModel):
    """The per-story driver's outcome the epic loop folds (Story 15.2 AC-3).

    Story 15.1 had the :class:`StoryLoopRunner` return a bare terminal-status
    string. Story 15.2's per-epic budget consumes the SUM of per-story retries
    across the epic, so the runner now surfaces ``retries_consumed`` alongside
    the terminal status. The injected runner already drives the per-story loop
    and owns where that story's per-story ``RunState`` lives, so it is the
    natural place to read ``len(retry_history)`` — chosen over having the epic
    loop read ``DEFAULT_RUN_STATE_PATH`` (which Epic 18 relocates per-worktree;
    see the story's "Consumption-surfacing decision"). This is an additive
    evolution of the epic-layer seam WITHIN Epic 15; Story 15.1 AC-2's
    bit-identity invariant is about ``orchestrator_run_entry.py`` + the per-story
    ``RunState`` shape, NOT this injected Protocol.

    Frozen; field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    terminal_status: PerStoryStatus
    retries_consumed: int = Field(ge=0)
    # Story 15.3 (AC-3 / NFR-P5): the per-epic cost partition consumes the SUM of
    # per-story costs. The injected runner sources this from the per-story cost
    # aggregation it already owns (Epic-18-worktree-safe — the epic loop never
    # reads a per-story cost path the worktree relocation would break; mirrors the
    # 15.2 ``retries_consumed`` rationale). Default ``0.0`` keeps the 15.1/15.2
    # test stubs valid (additive within the Epic-15 epic-layer seam).
    cost: float = Field(default=0.0, ge=0)


class StoryLoopRunner(Protocol):
    """The per-story driver the epic loop composes for each contained story.

    In production the implementation drives one story through the UNCHANGED
    per-story loop (``run_story_loop_entry`` → Dev → review-seam → QA → merge-
    ready/escalated per ``steps/run.md``, reusing the per-story
    ``event_log_appender`` within the story per AC-5) and returns a
    :class:`StoryLoopOutcome` carrying the story's terminal
    :data:`~loud_fail_harness.epic_run_state.PerStoryStatus` AND the number of
    retries that story consumed (read from the per-story ``RunState``'s
    ``retry_history``; Story 15.2 AC-3). Tests inject a deterministic stub.
    Keyword-only + non-defaulted (the project's structural-callback discipline;
    omitting an argument is a ``TypeError`` at call time).
    """

    def __call__(
        self, *, story_id: str, index: int, total: int
    ) -> StoryLoopOutcome: ...


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
        * ``paused_on_story_id`` — the story at whose completion boundary the
          epic paused (``escalated`` → ``epic-paused-on-escalation``, OR the
          per-epic budget exhausted with undispatched stories remaining →
          ``epic-paused-on-budget``), or ``None`` on a clean run.
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
    per-story story-docs). ``per_epic_retry_budget`` is populated
    (``effective_budget = multiplier × story_count``, ``consumed = 0``);
    budget enforcement is applied per-boundary by :func:`apply_epic_budget` in
    :func:`run_epic_loop`. ``per_epic_cost_partition`` is zeroed;
    ``active_markers`` is empty.
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
    ``epic-paused-on-budget`` is NOT produced here — budget enforcement is a
    separate layer applied by :func:`apply_epic_budget` AFTER calling this
    function. ``derive_epic_state`` stays a pure function of
    ``per_story_status`` only.
    """
    statuses = list(per_story_status.values())
    if any(status == "escalated" for status in statuses):
        return "epic-paused-on-escalation"
    if statuses and all(
        status in TERMINAL_PER_STORY_STATUSES for status in statuses
    ):
        return "epic-complete"
    return "epic-in-progress"


def apply_epic_budget(
    base_state: EpicCurrentState,
    consumed: int,
    effective_budget: int,
    *,
    has_undispatched: bool,
) -> tuple[EpicCurrentState, bool]:
    """Layer per-epic budget enforcement ON TOP of :func:`derive_epic_state`
    (AC-4 + AC-6).

    ``derive_epic_state`` stays a PURE function of ``per_story_status`` (budget
    logic does NOT leak into it). This helper takes its result (``base_state``)
    plus the cumulative budget figures and returns the resolved
    ``current_state`` and whether to emit the ``epic-budget-exhausted`` marker.

    Returns ``(resolved_state, emit_marker)`` where:

    * ``emit_marker`` is ``True`` iff the budget is exhausted
      (``effective_budget > 0`` AND ``consumed >= effective_budget``) AND
      undispatched stories remain — i.e. the exhaustion would guard FUTURE
      dispatch. The marker is additive: it emits regardless of ``base_state``
      (so an escalation that masks the single-valued ``current_state`` does NOT
      silently lose the budget overage — AC-6). Exhausting the budget exactly on
      the final story (no undispatched stories) is NOT an exhaustion event — the
      pause guards future dispatch, not a completed epic (AC-4).
    * ``resolved_state`` is ``epic-paused-on-budget`` ONLY when ``base_state``
      is ``epic-in-progress`` AND ``emit_marker`` (escalation precedence:
      ``epic-paused-on-escalation`` is the proximate human-actionable signal and
      wins the single-valued state; ``epic-complete`` is preserved — a completed
      epic never pauses). Otherwise ``base_state`` is returned unchanged.

    The ``effective_budget > 0`` guard keeps the helper total for the degenerate
    zero-budget case (a zero-story epic never enumerates — ``run_epic_loop``
    raises :exc:`EpicStoryEnumerationError` first — but the pure helper must not
    report a never-approached budget as instantly exhausted).
    """
    exhausted = effective_budget > 0 and consumed >= effective_budget
    emit_marker = exhausted and has_undispatched
    if base_state == "epic-in-progress" and emit_marker:
        return "epic-paused-on-budget", True
    return base_state, emit_marker


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


def fold_story_cost(
    partition: PerEpicCostPartition,
    story_id: str,
    cost: float,
) -> PerEpicCostPartition:
    """Fold one story's aggregated cost into the per-epic cost partition (pure).

    Returns a NEW :class:`~loud_fail_harness.epic_run_state.PerEpicCostPartition`
    with ``per_story_cost[story_id]`` accumulated (cumulative — added to any
    existing contribution; the partition is seeded at ``0.0`` per story by
    :func:`init_epic_run_state`) and ``epic_cost_total`` recomputed as the sum of
    all per-story costs (the rolled-up lower bound). Does NOT persist (the caller
    composes :func:`~loud_fail_harness.epic_run_state.advance_epic_run_state`);
    does NOT leak into :func:`derive_epic_state`, which stays a pure function of
    ``per_story_status`` (Story 15.3 AC-3 — layer alongside ``fold_story_terminal``
    / the budget fold).

    Stays a TOTAL function (defined for every input) per Story 15.3 Dev Notes
    "Input-hardening": a negative contribution is the sole rejection
    (``StoryLoopOutcome.cost`` is ``ge=0``; this guards the fold helper's own
    unit-tested surface). When per-story cost telemetry is unavailable the
    contribution is ``0.0`` (``cost-telemetry-unavailable`` already surfaced at
    the per-story boundary, Story 6.4) and the epic total is a lower bound.

    Raises:
        ValueError: ``cost`` is negative.
    """
    if cost < 0:
        raise ValueError(
            f"fold_story_cost: cost must be non-negative; got {cost!r}"
        )
    new_per_story: dict[str, float] = dict(partition.per_story_cost)
    new_per_story[story_id] = new_per_story.get(story_id, 0.0) + cost
    return partition.model_copy(
        update={
            "per_story_cost": new_per_story,
            "epic_cost_total": sum(new_per_story.values()),
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
    multiplier: int = DEFAULT_PER_EPIC_RETRY_MULTIPLIER,
    progress_sink: ProgressSink | None = None,
    transient_marker_classes: frozenset[str] | None = None,
    taxonomy_path: pathlib.Path | None = None,
    parallel_stories: bool = False,
    max_parallel_stories: int = DEFAULT_MAX_PARALLEL_STORIES,
    parallel_story_loop_runner: ParallelStoryLoopRunner | None = None,
    base_ref: str = "main",
    trunk_allowlist: tuple[str, ...] = (),
    worktrees_root: pathlib.Path | None = None,
    repo_root: pathlib.Path | None = None,
) -> RunEpicLoopResult:
    """Drive an epic's ``ready-for-dev`` stories sequentially through the
    per-story loop, advancing epic-run-state after each (AC-1..AC-6).

    Composition (the canonical epic loop ``steps/run-epic.md`` names):

        1. **Enumerate** the contained ``ready-for-dev`` stories via
           :func:`enumerate_epic_stories` (key-ascending order; AC-1).
        2. **Initialize** the epic-run-state cache via
           :func:`init_epic_run_state` (threading the config-resolved
           ``multiplier`` so ``effective_budget = multiplier × story_count``;
           AC-2) and persist it via
           :func:`~loud_fail_harness.epic_run_state.advance_epic_run_state`
           (atomic write + transient-marker filter; AC-1 / AC-3 / AC-6).
        3. **Dispatch sequentially** — for each story in order, invoke the
           injected ``story_loop_runner`` (the UNCHANGED per-story loop; AC-2),
           fold its terminal status into the aggregate
           (:func:`fold_story_terminal`), fold its ``retries_consumed`` into
           ``per_epic_retry_budget.consumed`` (AC-3), apply the per-epic budget
           (:func:`apply_epic_budget`; AC-4 / AC-6), persist the advance, and
           surface the "story M of N" framing line via ``progress_sink`` (AC-5).
        4. **Pause on escalation OR budget exhaustion** — if folding a story's
           terminal status transitions the epic to
           ``epic-paused-on-escalation`` (a contained story escalated) OR the
           cumulative retries exhaust the per-epic budget with undispatched
           stories remaining (``epic-paused-on-budget``), STOP; the downstream
           stories do NOT auto-advance (AC-4; sensor-not-advisor). The budget is
           checked AFTER the boundary story reaches terminal — the in-flight
           story is never interrupted.

    When ``parallel_stories`` is false (the default), stories run strictly
    sequentially (AC-4 bit-identical path). When true, phase-3 dispatch
    delegates to ``parallel_dispatch.dispatch_stories_parallel`` (Story 18.1
    — AC-3). The transient-class set is resolved ONCE and threaded
    through every ``advance_epic_run_state`` call so a recovery-recomputed
    transient marker never persists into the aggregate (AC-6). The durable
    ``epic-budget-exhausted`` marker is NOT transient and survives the filter.

    Args:
        epic_id: The ``epic-<N>`` identifier the practitioner passed at
            ``/bmad-automation run --epic <epic-id>``.
        run_id: Orchestrator-domain identifier correlating the epic dispatch
            with the ``epic-run-state.yaml`` record (ADR-005 Consequence 1).
        sprint_status_path: Caller-controlled path to ``sprint-status.yaml``.
        epic_run_state_path: Caller-controlled on-disk path for the epic-run-
            state cache.
        story_loop_runner: The per-story driver Protocol (AC-2). Returns a
            :class:`StoryLoopOutcome` carrying the terminal status + the
            per-story retries consumed (AC-3).
        multiplier: The per-epic retry-budget multiplier (AC-2). Production
            callers resolve it from ``_bmad/automation/config.yaml`` via
            :func:`~loud_fail_harness.retry_budget.resolve_per_epic_retry_budget_multiplier`;
            defaults to :data:`DEFAULT_PER_EPIC_RETRY_MULTIPLIER`.
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

    epic_state = init_epic_run_state(
        epic_id, run_id, story_ids, multiplier=multiplier
    )

    # Resume budget reconstruction (Story 16.5 AC-5/7/8/9). A pre-existing cache
    # at epic_run_state_path means this is a re-invocation after a pause: carry
    # the cumulative per-epic budget (the ORIGINAL epic-sized effective_budget
    # AND the already-consumed count) + durable markers forward, instead of
    # letting init_epic_run_state's consumed=0 / re-narrowed effective_budget
    # silently hand a runaway retry sequence a fresh budget. Gated SOLELY on
    # cache presence + run_id match: a first invocation finds no file (the first
    # advance_epic_run_state below creates it), so the clean path is byte-for-
    # byte unchanged (AC-9). Only the budget sub-model + durable markers are
    # carried; per-story-status / cost-partition re-derivation is OUT of scope
    # (re-derived via enumerate-narrowing + canonical stores — AC-5 boundary).
    if epic_run_state_path.is_file():
        epic_state = reconstruct_budget_on_resume(
            epic_state,
            persisted=load_epic_run_state(epic_run_state_path),
            run_id=run_id,
            cache_path=epic_run_state_path,
            budget_field="per_epic_retry_budget",
            transient_marker_classes=transient_marker_classes,
        )

    # Pre-dispatch budget admission (Story 16.5 review). A quota guard is an
    # ADMISSION invariant checked BEFORE the guarded action, not only after it.
    # On a resume that reconstructed an already-exhausted budget
    # (``consumed >= effective_budget``) with stories still to dispatch, pause
    # IMMEDIATELY without dispatching a further story — so the guard holds
    # strictly across resume boundaries (a runaway sequence cannot buy one extra
    # story per re-invocation). No-op on a fresh run: ``consumed`` starts at 0,
    # so this never fires before the post-dispatch fold has accrued past the
    # ceiling (by which point the loop has already broken). Epic 18's parallel
    # dispatcher MUST apply this same admission gate per concurrent unit.
    budget = epic_state.per_epic_retry_budget
    admission_state, admission_marker = apply_epic_budget(
        epic_state.current_state,
        budget.consumed,
        budget.effective_budget,
        has_undispatched=bool(story_ids),
    )
    if admission_state == "epic-paused-on-budget":
        admission_markers = epic_state.active_markers
        if (
            admission_marker
            and EPIC_BUDGET_EXHAUSTED_MARKER not in admission_markers
        ):
            admission_markers = (*admission_markers, EPIC_BUDGET_EXHAUSTED_MARKER)
        epic_state = epic_state.model_copy(
            update={
                "current_state": admission_state,
                "active_markers": admission_markers,
            }
        )

    advance = advance_epic_run_state(
        epic_run_state_path,
        epic_state,
        transient_marker_classes=transient_marker_classes,
    )
    epic_state = advance.next_state

    if epic_state.current_state == "epic-paused-on-budget":
        return RunEpicLoopResult(
            epic_id=epic_id,
            run_id=run_id,
            final_state=epic_state,
            dispatched_story_ids=(),
            paused_on_story_id=None,
            wrote_path=epic_run_state_path,
        )

    # Phase-3 dispatch: ONE guarded branch (Story 18.1 AC-3). When
    # parallel_stories is resolved true, delegate to the worktree-isolated
    # parallel dispatcher; the same pre-dispatch admission gate (above) already
    # ran, so an already-exhausted resume never reaches here. When false (the
    # default), the EXISTING sequential body below runs verbatim — bit-identical
    # to the Epic-15/16 posture (AC-4). The import is function-local so
    # parallel_dispatch (which imports this module) introduces no import cycle.
    if parallel_stories:
        if parallel_story_loop_runner is None:
            raise ValueError(
                "parallel_stories is enabled but no parallel_story_loop_runner "
                "was provided; the parallel path requires a "
                "ParallelStoryLoopRunner (the worktree-aware per-story driver) "
                "— see loud_fail_harness.parallel_dispatch"
            )
        from loud_fail_harness.env_provisioning import (
            DisjointPortAllocator,
            DisjointPortExhausted,
            ParallelEnvClaimProvider,
        )
        from loud_fail_harness.parallel_dispatch import dispatch_stories_parallel

        # Supplying the production claim provider is what BOTH enforces the FR7
        # concurrent-provisioning discipline (each story is handed a disjoint
        # pre-flight port + a distinct env namespace) AND activates Story 18.2's
        # pollution detector at runtime — Story 18.1 left ``claim_provider``
        # injectable but unfilled, so detection was inert in production until
        # now (Story 18.3). Constructed ONLY on this parallel branch; the
        # sequential path below never touches them (AC-6 bit-identity).
        port_allocator = DisjointPortAllocator()
        claim_provider = ParallelEnvClaimProvider(
            run_id=run_id,
            allocator=port_allocator,
            worktrees_root=worktrees_root,
            repo_root=repo_root,
        )

        try:
            return dispatch_stories_parallel(
                epic_id,
                run_id=run_id,
                story_ids=story_ids,
                max_parallel_stories=max_parallel_stories,
                runner=parallel_story_loop_runner,
                epic_state=epic_state,
                epic_run_state_path=epic_run_state_path,
                transient_marker_classes=transient_marker_classes,
                base_ref=base_ref,
                trunk_allowlist=trunk_allowlist,
                worktrees_root=worktrees_root,
                repo_root=repo_root,
                progress_sink=progress_sink,
                claim_provider=claim_provider,
                claim_release=port_allocator.release,
                claim_seed=claim_provider.seed_carrier,
            )
        except DisjointPortExhausted:
            # Impossibility-class signal (Story 18.3 AC-1): the OS ephemeral
            # range dwarfs any realistic max_parallel_stories, so exhaustion
            # means allocate_ephemeral_port is stuck or mis-stubbed — never
            # genuine pressure. Transition to the existing escalation state so
            # the epic run-state is persisted and inspectable via status --epic
            # rather than crashing with no structured signal (loud-fail doctrine).
            paused = epic_state.model_copy(
                update={"current_state": "epic-paused-on-escalation"}
            )
            adv = advance_epic_run_state(
                epic_run_state_path,
                paused,
                transient_marker_classes=transient_marker_classes,
            )
            return RunEpicLoopResult(
                epic_id=epic_id,
                run_id=run_id,
                final_state=adv.next_state,
                dispatched_story_ids=(),
                paused_on_story_id=None,
                wrote_path=epic_run_state_path,
            )

    total = len(story_ids)
    dispatched: list[str] = []
    paused_on: str | None = None
    _expected_terminal = TERMINAL_PER_STORY_STATUSES | {"escalated"}

    for index, story_id in enumerate(story_ids, start=1):
        outcome = story_loop_runner(
            story_id=story_id, index=index, total=total
        )
        terminal_status = outcome.terminal_status
        if terminal_status not in _expected_terminal:
            raise ValueError(
                f"story_loop_runner returned non-terminal status "
                f"{terminal_status!r} for story {story_id!r}; "
                f"expected one of {sorted(_expected_terminal)}"
            )
        epic_state = fold_story_terminal(epic_state, story_id, terminal_status)

        # Fold this story's per-story retries into the cumulative per-epic budget
        # AFTER the story reached terminal (sensor-not-advisor: the in-flight
        # story is never interrupted — AC-3 / AC-4). apply_epic_budget layers the
        # budget decision ON TOP of the pure derive_epic_state result; escalation
        # keeps current_state precedence while the marker emits additively (AC-6).
        budget = epic_state.per_epic_retry_budget
        new_consumed = budget.consumed + outcome.retries_consumed
        resolved_state, emit_marker = apply_epic_budget(
            epic_state.current_state,
            new_consumed,
            budget.effective_budget,
            has_undispatched=index < total,
        )
        active_markers = epic_state.active_markers
        if emit_marker and EPIC_BUDGET_EXHAUSTED_MARKER not in active_markers:
            active_markers = (*active_markers, EPIC_BUDGET_EXHAUSTED_MARKER)
        # Fold this story's aggregated cost into the per-epic cost partition
        # (AC-3 / NFR-P5) alongside the terminal + budget folds. The runner
        # surfaces the cost through the SAME StoryLoopOutcome channel as
        # retries_consumed (Epic-18-worktree-safe); the mutation rides the
        # existing advance_epic_run_state call below (no inline writes).
        new_partition = fold_story_cost(
            epic_state.per_epic_cost_partition, story_id, outcome.cost
        )
        epic_state = epic_state.model_copy(
            update={
                "per_epic_retry_budget": budget.model_copy(
                    update={"consumed": new_consumed}
                ),
                "current_state": resolved_state,
                "active_markers": active_markers,
                "per_epic_cost_partition": new_partition,
            }
        )

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
        if epic_state.current_state in (
            "epic-paused-on-escalation",
            "epic-paused-on-budget",
        ):
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
    "EPIC_BUDGET_EXHAUSTED_MARKER",
    "EpicStoryEnumerationError",
    "ProgressSink",
    "RunEpicLoopResult",
    "StoryLoopOutcome",
    "StoryLoopRunner",
    "TERMINAL_PER_STORY_STATUSES",
    "apply_epic_budget",
    "derive_epic_state",
    "enumerate_epic_stories",
    "fold_story_cost",
    "fold_story_terminal",
    "init_epic_run_state",
    "run_epic_loop",
]
