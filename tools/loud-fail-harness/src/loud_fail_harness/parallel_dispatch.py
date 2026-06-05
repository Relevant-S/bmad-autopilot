"""Story 18.1 — Parallel-story dispatch substrate (FR-P2-4).

Architectural placement (ADR-009 + ADR-003 Consequence 1 + epics-phase-2.md
Story 18.1): this module is the *activation* of the Epic 14 worktree-isolation
substrate. It is a substrate **LIBRARY**, NOT a sixth substrate component —
ADR-003 Consequence 1 enumerates exactly five substrate components
(``envelope_validator`` / ``event_validator`` / ``reconciler`` /
``enumeration_check`` / ``fixture_coverage``); this module is a sibling of the
substrate libraries ``epic_lifecycle.py`` / ``worktree_lifecycle.py`` /
``story_file_lock.py`` / ``epic_run_state.py`` (Story 14.2 AC-11's
library-not-component precedent). The substrate-component count stays at FIVE;
the harness library count grows by one.

What this library provides:
    * :class:`ParallelStoryLoopRunner` — the per-story driver Protocol the
      parallel path injects; the worktree-aware sibling of
      :class:`~loud_fail_harness.epic_lifecycle.StoryLoopRunner` (adds
      ``worktree_path`` + ``run_state_path``).
    * :func:`dispatch_stories_parallel` — fan out ``<= max_parallel_stories``
      per-story loops concurrently, each isolated in its own worktree +
      story-file lock + per-worktree run-state, folding terminals on the
      dispatching thread; returns the SAME
      :class:`~loud_fail_harness.epic_lifecycle.RunEpicLoopResult` shape
      ``run_epic_loop`` returns (so the epic loop's callers + the sprint
      adapter are unaffected).

What this library enforces:
    * **FR-P2-4 worktree-isolation + story-file-locking** — each concurrent
      unit is wrapped in ``create_worktree`` → ``story_file_lock`` →
      per-worktree run-state → outcome-driven cleanup (``cleanup_worktree``
      skipped for escalated stories; called with
      ``preserve_on_escalation=False`` otherwise). The cleanup is guarded by
      a ``try/finally`` so a lock or runner exception does not orphan a
      created worktree.
    * **The per-concurrent-unit admission invariant (Story 16.5 obligation)** —
      the per-epic budget is evaluated as an admission gate *before each unit is
      launched*, reusing the SAME :func:`apply_epic_budget` pure function the
      sequential path uses. A post-only check would admit N units past the
      ceiling (one per in-flight slot); the per-unit gate admits exactly the
      stories the cumulative budget covers.
    * **The PRD 4-specialist / <=3-hook lock** — concurrency is at the per-STORY
      level only; this library introduces no new specialist and no 4th hook.
    * **Sensor-not-advisor** — the dispatcher describes/persists what happened
      (terminals, budget pauses, escalations); it never interrupts an in-flight
      story and never decides remediation.

Concurrency model:
    Concurrency is at the per-STORY level: ``dispatch_stories_parallel`` runs at
    most ``max_parallel_stories`` per-story loops simultaneously via a bounded
    :class:`concurrent.futures.ThreadPoolExecutor`. WITHIN a story the per-story
    loop is UNCHANGED — Dev / Review-BMAD / QA / Review-LAD run serially (no
    within-story specialist parallelism, no 5th specialist;
    epics-phase-2.md line 599). Threads (not processes) because the per-story
    loop is I/O-bound (Task-tool subagent dispatch + git/filesystem); the GIL is
    released during IO so threads give real concurrency without
    ``ProcessPoolExecutor``'s spawn/pickling cost. The epic-aggregate folds
    (``fold_story_terminal`` / ``apply_epic_budget`` / ``fold_story_cost`` /
    ``advance_epic_run_state``) run on the dispatching (main) thread as futures
    complete — single-writer to ``epic-run-state.yaml``; workers only do the
    isolated per-worktree work.

What this library does NOT do:
    * **No cross-story state-pollution detection** — Story 18.2 owns the
      cross-story state-pollution detector + emitter against the OTHER shared
      surfaces (port pool, evidence root, lost-update predicate). This library
      emits no cross-story state-pollution marker (the taxonomy class
      pre-provisioned by Story 14.5 stays scheduled-by-18.2; this module is
      taxonomy-neutral — AC-7).
    * **No concurrent-env-provisioning discipline** — Story 18.3 owns the FR7
      extension (ephemeral per-story ports, distinct namespaces).
    * **No new reference fixture** — Story 18.4 owns the end-to-end parallel-mode
      reference run.

FR62 pluggability classification:
    Substrate-shared library per ADR-003's substrate-vs-specialist boundary; it
    imports ONLY other substrate libraries (``epic_lifecycle`` /
    ``worktree_lifecycle`` / ``story_file_lock`` / ``epic_run_state``) and
    references NO ``agents/*.md`` specialist-wrapper path. The FR62 gate audits
    specialist-wrapper cross-references, not substrate libraries.

``find_repo_root()`` discipline (Epic 1 retro Action #1):
    ``find_repo_root()`` is NOT called at module import time. Every path is
    caller-supplied or lazily resolved by the composed substrate helpers
    (``worktree_lifecycle`` / ``epic_run_state``) at call time. No module-level
    side effects at import.
"""

from __future__ import annotations

import collections
import concurrent.futures as cf
import pathlib
from typing import Protocol

from loud_fail_harness import story_file_lock as story_file_lock_module
from loud_fail_harness import worktree_lifecycle
from loud_fail_harness.epic_lifecycle import (
    EPIC_BUDGET_EXHAUSTED_MARKER,
    ProgressSink,
    RunEpicLoopResult,
    StoryLoopOutcome,
    TERMINAL_PER_STORY_STATUSES,
    _format_epic_progress,
    apply_epic_budget,
    fold_story_cost,
    fold_story_terminal,
)
from loud_fail_harness.epic_run_state import (
    EpicRunState,
    advance_epic_run_state,
    worktree_run_state_path,
)

_PAUSED_EPIC_STATES: frozenset[str] = frozenset(
    {"epic-paused-on-escalation", "epic-paused-on-budget"}
)
_EXPECTED_TERMINAL: frozenset[str] = TERMINAL_PER_STORY_STATUSES | frozenset(
    {"escalated"}
)


class ParallelStoryLoopRunner(Protocol):
    """The worktree-aware per-story driver the parallel path composes.

    The sibling of :class:`~loud_fail_harness.epic_lifecycle.StoryLoopRunner`
    (which is preserved verbatim — load-bearing for Story 18.1 AC-4's
    bit-identity of the sequential path). The sequential Protocol carries no
    worktree context; this one adds ``worktree_path`` (the per-story filesystem
    isolation ``create_worktree`` produced) and ``run_state_path`` (the
    per-worktree run-state path ``worktree_run_state_path`` derived) so the
    production runner can drive the UNCHANGED per-story loop with
    ``cwd=worktree_path`` and the byte-isolated per-worktree run-state, returning
    the SAME :class:`~loud_fail_harness.epic_lifecycle.StoryLoopOutcome` (so the
    epic-aggregate folds are unchanged).

    A distinct Protocol (rather than extending ``StoryLoopRunner`` with optional
    ``worktree_path=None`` kwargs) keeps the two seams non-confusable: the
    sequential path cannot silently accept a parallel-shaped call and vice
    versa. Keyword-only + non-defaulted (the project's structural-callback
    discipline; omitting an argument is a ``TypeError`` at call time). Tests
    inject a deterministic stub.
    """

    def __call__(
        self,
        *,
        story_id: str,
        index: int,
        total: int,
        worktree_path: pathlib.Path,
        run_state_path: pathlib.Path,
    ) -> StoryLoopOutcome: ...


def dispatch_stories_parallel(
    epic_id: str,
    *,
    run_id: str,
    story_ids: tuple[str, ...],
    max_parallel_stories: int,
    runner: ParallelStoryLoopRunner,
    epic_state: EpicRunState,
    epic_run_state_path: pathlib.Path,
    transient_marker_classes: frozenset[str],
    base_ref: str,
    trunk_allowlist: tuple[str, ...],
    worktrees_root: pathlib.Path | None = None,
    repo_root: pathlib.Path | None = None,
    progress_sink: ProgressSink | None = None,
) -> RunEpicLoopResult:
    """Fan out the enumerated stories concurrently, each worktree-isolated, and
    fold their terminals into the epic aggregate on the dispatching thread.

    The parallel sibling of ``run_epic_loop``'s sequential phase-3 dispatch. It
    is invoked by ``run_epic_loop`` ONLY when the resolved ``parallel_stories``
    is true, AFTER the shared enumerate / init / resume-reconstruction /
    pre-dispatch-admission phases (so an already-exhausted resume never reaches
    this function — ``run_epic_loop`` returns ``epic-paused-on-budget`` first).

    Per-unit wrap (the order ADR-009 mandates under ``parallel_stories: true``):

        1. ``worktree_lifecycle.create_worktree(story_id, base_ref=...,
           trunk_allowlist=...)`` — per-story filesystem isolation.
        2. ``story_file_lock.story_file_lock(story_id, worktree_path=...)`` —
           guards the per-story BMAD-state writes against concurrent story-doc
           writes (Story 14.3).
        3. drive the per-story loop with the per-worktree run-state addressed via
           ``epic_run_state.worktree_run_state_path(story_id)`` (Story 14.4 —
           each worktree owns its byte-isolated run-state, NOT the shared
           ``DEFAULT_RUN_STATE_PATH``).
        4. Cleanup is outcome-driven: ``cleanup_worktree(story_id,
           preserve_on_escalation=False)`` for non-escalated stories (removes
           the worktree; branch preserved per NFR-R3). For escalated stories,
           ``cleanup_worktree`` is skipped entirely so the worktree is preserved
           for human inspection (ADR-009 cleanup-on-merge-ready policy). The
           decision is derived from the known ``outcome.terminal_status`` rather
           than ``cleanup_worktree``'s internal shared-run-state read, which is
           absent in parallel mode (each story writes a per-worktree run-state,
           not the shared ``DEFAULT_RUN_STATE_PATH``). The cleanup call is
           guarded by a ``try/finally`` so a lock-acquire or runner exception
           does not orphan a created worktree.

    The admission invariant (Story 16.5 obligation; AC-5): before launching each
    unit, the per-epic budget is evaluated via :func:`apply_epic_budget` (the
    SAME pure function the sequential path uses). Once the cumulative
    ``consumed >= effective_budget`` with undispatched stories remaining, no
    further unit is admitted — the in-flight units finish (never interrupted),
    their terminals fold, and the epic transitions to ``epic-paused-on-budget``
    with the durable ``epic-budget-exhausted`` marker. An escalated terminal
    likewise stops further admission (``epic-paused-on-escalation``; downstream
    stories do NOT auto-advance — Story 15.1 AC-4).

    Returns a :class:`~loud_fail_harness.epic_lifecycle.RunEpicLoopResult` with
    the terminal epic state, the dispatched stories (submission order, filtered
    to those that completed), and the pausing story (if any).
    """
    total = len(story_ids)
    index_by_story = {sid: i for i, sid in enumerate(story_ids, start=1)}
    pending: collections.deque[str] = collections.deque(story_ids)
    admitted_order: list[str] = []
    completed: set[str] = set()
    paused_on: str | None = None

    def _admit_ok() -> bool:
        # Reuse apply_epic_budget as the admission decision (the budget decision
        # is shared, never re-implemented — flow policy stays singular). Once the
        # epic is paused (escalation or budget) no further unit is admitted.
        if epic_state.current_state in _PAUSED_EPIC_STATES:
            return False
        budget = epic_state.per_epic_retry_budget
        admission_state, _ = apply_epic_budget(
            epic_state.current_state,
            budget.consumed,
            budget.effective_budget,
            has_undispatched=bool(pending),
        )
        return admission_state != "epic-paused-on-budget"

    def _run_unit(
        *, story_id: str, index: int, total: int
    ) -> StoryLoopOutcome:
        worktree = worktree_lifecycle.create_worktree(
            story_id,
            base_ref=base_ref,
            trunk_allowlist=trunk_allowlist,
            worktrees_root=worktrees_root,
            repo_root=repo_root,
        )
        outcome: StoryLoopOutcome | None = None
        try:
            run_state_path = worktree_run_state_path(
                story_id, worktrees_root=worktrees_root, repo_root=repo_root
            )
            with story_file_lock_module.story_file_lock(
                story_id, worktree_path=worktree.worktree_path, repo_root=repo_root
            ):
                outcome = runner(
                    story_id=story_id,
                    index=index,
                    total=total,
                    worktree_path=worktree.worktree_path,
                    run_state_path=run_state_path,
                )
        finally:
            # cleanup_worktree reads the SHARED run-state to determine whether
            # to preserve on escalation; in parallel mode each story writes to
            # its per-worktree run-state (not the shared path), so that check
            # always falls through and would remove every worktree. Use the
            # known outcome directly: skip cleanup for escalated stories
            # (preserve the worktree for human inspection per ADR-009); clean
            # up in all other cases, including exception paths (outcome is
            # None — no meaningful escalation state, always clean up).
            is_escalated = (
                outcome is not None and outcome.terminal_status == "escalated"
            )
            if not is_escalated:
                worktree_lifecycle.cleanup_worktree(
                    story_id,
                    preserve_on_escalation=False,
                    worktrees_root=worktrees_root,
                    repo_root=repo_root,
                )
        assert outcome is not None
        return outcome

    with cf.ThreadPoolExecutor(max_workers=max_parallel_stories) as executor:
        in_flight: dict[cf.Future[StoryLoopOutcome], str] = {}

        def _try_admit() -> None:
            while (
                pending
                and len(in_flight) < max_parallel_stories
                and _admit_ok()
            ):
                story_id = pending.popleft()
                future = executor.submit(
                    _run_unit,
                    story_id=story_id,
                    index=index_by_story[story_id],
                    total=total,
                )
                in_flight[future] = story_id
                admitted_order.append(story_id)

        _try_admit()

        while in_flight:
            done, _ = cf.wait(
                set(in_flight), return_when=cf.FIRST_COMPLETED
            )
            worker_errors: list[tuple[str, BaseException]] = []
            for future in done:
                story_id = in_flight.pop(future)
                try:
                    outcome = future.result()
                except BaseException as exc:
                    # Collect; fold all sibling completions in this batch
                    # first (never leave successfully-completed stories
                    # unrecorded because of a sibling failure), then re-raise.
                    worker_errors.append((story_id, exc))
                    continue
                if outcome.terminal_status not in _EXPECTED_TERMINAL:
                    raise ValueError(
                        f"parallel story runner returned non-terminal status "
                        f"{outcome.terminal_status!r} for story {story_id!r}; "
                        f"expected one of {sorted(_EXPECTED_TERMINAL)}"
                    )

                epic_state = fold_story_terminal(
                    epic_state, story_id, outcome.terminal_status
                )
                budget = epic_state.per_epic_retry_budget
                new_consumed = budget.consumed + outcome.retries_consumed
                resolved_state, emit_marker = apply_epic_budget(
                    epic_state.current_state,
                    new_consumed,
                    budget.effective_budget,
                    # Count in-flight stories (already admitted, not yet folded)
                    # as undispatched so budget exhaustion fires even when all
                    # stories were admitted simultaneously (pending is empty).
                    has_undispatched=bool(pending) or bool(in_flight),
                )
                active_markers = epic_state.active_markers
                if (
                    emit_marker
                    and EPIC_BUDGET_EXHAUSTED_MARKER not in active_markers
                ):
                    active_markers = (
                        *active_markers,
                        EPIC_BUDGET_EXHAUSTED_MARKER,
                    )
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
                completed.add(story_id)
                if progress_sink is not None:
                    progress_sink(
                        _format_epic_progress(
                            index_by_story[story_id],
                            total,
                            story_id,
                            outcome.terminal_status,
                            epic_state.current_state,
                        )
                    )
                if (
                    paused_on is None
                    and epic_state.current_state in _PAUSED_EPIC_STATES
                ):
                    paused_on = story_id

            if worker_errors:
                raise worker_errors[0][1]

            _try_admit()

    dispatched = tuple(sid for sid in admitted_order if sid in completed)
    return RunEpicLoopResult(
        epic_id=epic_id,
        run_id=run_id,
        final_state=epic_state,
        dispatched_story_ids=dispatched,
        paused_on_story_id=paused_on,
        wrote_path=epic_run_state_path,
    )


__all__ = [
    "ParallelStoryLoopRunner",
    "dispatch_stories_parallel",
]
