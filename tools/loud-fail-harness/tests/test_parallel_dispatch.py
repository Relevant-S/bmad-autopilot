"""Contract-coverage matrix for the parallel-dispatch substrate (Story 18.1).

AC mapping (verbatim from
``_bmad-output/implementation-artifacts/18-1-...md``):

    * AC-2 — module is a substrate-LIBRARY; ``__all__`` is exactly the public
      surface; no marker class; no module-import-time side effect.
    * AC-3 — bounded fan-out (<= max_parallel_stories in flight); per-unit
      worktree create/cleanup; story-file lock acquire/release; per-worktree
      run-state path threaded to the runner; specialists serial within a story;
      cleanup preserves on escalation.
    * AC-4 — ``parallel_stories: false`` creates NO worktree / NO lock (the
      false path never touches the substrate) and is byte-stable.
    * AC-5 — per-concurrent-unit admission invariant: an exhausted budget admits
      zero further units; an under-budget run admits all.
    * AC-6 — no new specialist / no 4th hook / within-story serial.
"""

from __future__ import annotations

import contextlib
import pathlib
import threading
import time
from collections.abc import Iterator

import pytest
import yaml

from loud_fail_harness import parallel_dispatch
from loud_fail_harness.epic_lifecycle import (
    EPIC_BUDGET_EXHAUSTED_MARKER,
    StoryLoopOutcome,
    init_epic_run_state,
    run_epic_loop,
)
from loud_fail_harness.parallel_dispatch import dispatch_stories_parallel

_NO_TRANSIENT: frozenset[str] = frozenset()


class _FakeWorktree:
    def __init__(self, worktree_path: pathlib.Path) -> None:
        self.worktree_path = worktree_path


class _SubstrateSpy:
    """Records the substrate-primitive calls the dispatcher makes, thread-safely.

    Patches the four composed seams in :mod:`loud_fail_harness.parallel_dispatch`
    so tests run without real git: ``create_worktree`` / ``cleanup_worktree``
    (on the imported ``worktree_lifecycle`` module), ``story_file_lock`` (on the
    imported ``story_file_lock_module``), and the pure ``worktree_run_state_path``
    (imported by name into the dispatcher's namespace).
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
        self._lock = threading.Lock()
        self.created: list[str] = []
        self.cleaned: list[tuple[str, bool]] = []
        self.lock_acquired: list[str] = []
        self.lock_released: list[str] = []
        self.in_flight = 0
        self.peak_in_flight = 0
        self._tmp = tmp_path

        def _create_worktree(
            story_id: str,
            *,
            base_ref: str,
            trunk_allowlist: tuple[str, ...],
            worktrees_root: pathlib.Path | None = None,
            repo_root: pathlib.Path | None = None,
        ) -> _FakeWorktree:
            with self._lock:
                self.created.append(story_id)
            return _FakeWorktree(tmp_path / "wt" / story_id)

        def _cleanup_worktree(
            story_id: str,
            *,
            preserve_on_escalation: bool = True,
            worktrees_root: pathlib.Path | None = None,
            repo_root: pathlib.Path | None = None,
        ) -> None:
            with self._lock:
                self.cleaned.append((story_id, preserve_on_escalation))

        @contextlib.contextmanager
        def _story_file_lock(
            story_id: str,
            *,
            worktree_path: pathlib.Path,
            repo_root: pathlib.Path | None = None,
            **_: object,
        ) -> Iterator[None]:
            with self._lock:
                self.lock_acquired.append(story_id)
            try:
                yield None
            finally:
                with self._lock:
                    self.lock_released.append(story_id)

        def _worktree_run_state_path(
            story_id: str,
            *,
            worktrees_root: pathlib.Path | None = None,
            repo_root: pathlib.Path | None = None,
        ) -> pathlib.Path:
            return tmp_path / "rs" / f"{story_id}.yaml"

        monkeypatch.setattr(
            parallel_dispatch.worktree_lifecycle, "create_worktree", _create_worktree
        )
        monkeypatch.setattr(
            parallel_dispatch.worktree_lifecycle, "cleanup_worktree", _cleanup_worktree
        )
        monkeypatch.setattr(
            parallel_dispatch.story_file_lock_module,
            "story_file_lock",
            _story_file_lock,
        )
        monkeypatch.setattr(
            parallel_dispatch, "worktree_run_state_path", _worktree_run_state_path
        )

    def enter_unit(self) -> None:
        with self._lock:
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)

    def exit_unit(self) -> None:
        with self._lock:
            self.in_flight -= 1


def _make_runner(
    spy: _SubstrateSpy,
    *,
    retries: dict[str, int] | None = None,
    statuses: dict[str, str] | None = None,
    seen: list[tuple[str, pathlib.Path, pathlib.Path]] | None = None,
    overlap_seconds: float = 0.0,
) -> parallel_dispatch.ParallelStoryLoopRunner:
    retries = retries or {}
    statuses = statuses or {}

    def runner(
        *,
        story_id: str,
        index: int,
        total: int,
        worktree_path: pathlib.Path,
        run_state_path: pathlib.Path,
    ) -> StoryLoopOutcome:
        spy.enter_unit()
        try:
            if seen is not None:
                with spy._lock:
                    seen.append((story_id, worktree_path, run_state_path))
            if overlap_seconds:
                time.sleep(overlap_seconds)
        finally:
            spy.exit_unit()
        return StoryLoopOutcome(
            terminal_status=statuses.get(story_id, "merge-ready"),  # type: ignore[arg-type]
            retries_consumed=retries.get(story_id, 0),
        )

    return runner


def _epic_state(story_ids: tuple[str, ...], *, multiplier: int = 2):
    return init_epic_run_state("epic-18", "run-1", story_ids, multiplier=multiplier)


# ---------------------------------------------------------------------------
# AC-2 — module surface
# ---------------------------------------------------------------------------


def test_module_all_is_exact_public_surface() -> None:
    assert parallel_dispatch.__all__ == [
        "ParallelStoryLoopRunner",
        "dispatch_stories_parallel",
    ]


def test_module_is_taxonomy_neutral() -> None:
    """AC-2 / AC-7: the dispatcher declares NO new marker class and never
    references ``parallel-story-state-pollution`` (Story 18.2 owns that emitter).
    Re-using the existing ``EPIC_BUDGET_EXHAUSTED_MARKER`` (imported, not
    declared) is explicitly endorsed by AC-5."""
    source = pathlib.Path(parallel_dispatch.__file__).read_text(encoding="utf-8")
    assert "parallel-story-state-pollution" not in source
    # The only marker constant in scope is the imported (reused) epic-budget one;
    # the module assigns no marker literal of its own.
    assert "_MARKER" not in source.replace("EPIC_BUDGET_EXHAUSTED_MARKER", "")


# ---------------------------------------------------------------------------
# AC-3 — bounded fan-out + per-unit substrate wrap
# ---------------------------------------------------------------------------


def test_dispatch_wraps_each_unit_in_worktree_lock_and_run_state(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _SubstrateSpy(monkeypatch, tmp_path)
    story_ids = ("18-1-a", "18-2-b", "18-3-c")
    seen: list[tuple[str, pathlib.Path, pathlib.Path]] = []
    runner = _make_runner(spy, seen=seen)

    result = dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=2,
        runner=runner,
        epic_state=_epic_state(story_ids),
        epic_run_state_path=tmp_path / "epic-run-state.yaml",
        transient_marker_classes=_NO_TRANSIENT,
        base_ref="main",
        trunk_allowlist=("main",),
    )

    assert result.final_state.current_state == "epic-complete"
    assert set(result.dispatched_story_ids) == set(story_ids)
    # Every unit got a worktree created + cleaned, and a lock acquired+released.
    assert sorted(spy.created) == sorted(story_ids)
    assert sorted(s for s, _ in spy.cleaned) == sorted(story_ids)
    assert all(preserve is False for _, preserve in spy.cleaned)
    assert sorted(spy.lock_acquired) == sorted(story_ids)
    assert sorted(spy.lock_released) == sorted(story_ids)
    # The per-worktree run-state path (NOT the shared default) reached the runner.
    for story_id, worktree_path, run_state_path in seen:
        assert worktree_path == tmp_path / "wt" / story_id
        assert run_state_path == tmp_path / "rs" / f"{story_id}.yaml"


def test_dispatch_bounds_concurrency_to_max_parallel_stories(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _SubstrateSpy(monkeypatch, tmp_path)
    story_ids = tuple(f"18-{i}-x" for i in range(1, 6))
    runner = _make_runner(spy, overlap_seconds=0.03)

    result = dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=2,
        runner=runner,
        epic_state=_epic_state(story_ids),
        epic_run_state_path=tmp_path / "e.yaml",
        transient_marker_classes=_NO_TRANSIENT,
        base_ref="main",
        trunk_allowlist=(),
    )

    assert set(result.dispatched_story_ids) == set(story_ids)
    # The bound holds: peak simultaneous in-flight never exceeds the ceiling.
    assert 1 <= spy.peak_in_flight <= 2


def test_dispatch_clean_run_persists_epic_complete(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _SubstrateSpy(monkeypatch, tmp_path)
    story_ids = ("18-1-a", "18-2-b")
    erp = tmp_path / "epic-run-state.yaml"
    dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=2,
        runner=_make_runner(spy),
        epic_state=_epic_state(story_ids),
        epic_run_state_path=erp,
        transient_marker_classes=_NO_TRANSIENT,
        base_ref="main",
        trunk_allowlist=(),
    )
    on_disk = yaml.safe_load(erp.read_text(encoding="utf-8"))
    assert on_disk["current_state"] == "epic-complete"
    assert on_disk["per_story_status"] == {
        "18-1-a": "merge-ready",
        "18-2-b": "merge-ready",
    }


# ---------------------------------------------------------------------------
# AC-5 — per-concurrent-unit admission invariant
# ---------------------------------------------------------------------------


def test_admission_gate_stops_admitting_when_budget_exhausts(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-5: with max_parallel_stories=1 the gate is checked between each unit;
    a unit that exhausts the per-epic budget stops all further admission — the
    runner is never called for the undispatched stories."""
    spy = _SubstrateSpy(monkeypatch, tmp_path)
    story_ids = ("18-1-a", "18-2-b", "18-3-c", "18-4-d")
    # multiplier=1, story_count=4 → effective_budget=4. First story consumes 4 →
    # exhausted with undispatched remaining → no further admission.
    runner = _make_runner(spy, retries={"18-1-a": 4})

    result = dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=1,
        runner=runner,
        epic_state=_epic_state(story_ids, multiplier=1),
        epic_run_state_path=tmp_path / "e.yaml",
        transient_marker_classes=_NO_TRANSIENT,
        base_ref="main",
        trunk_allowlist=(),
    )

    assert result.dispatched_story_ids == ("18-1-a",)
    assert result.paused_on_story_id == "18-1-a"
    assert result.final_state.current_state == "epic-paused-on-budget"
    assert EPIC_BUDGET_EXHAUSTED_MARKER in result.final_state.active_markers
    assert result.final_state.per_epic_retry_budget.consumed == 4
    # Only the first unit ran; the rest were never admitted (gate, not interrupt).
    assert spy.created == ["18-1-a"]


def test_admission_gate_is_noop_under_budget(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _SubstrateSpy(monkeypatch, tmp_path)
    story_ids = ("18-1-a", "18-2-b", "18-3-c")
    # multiplier=5, story_count=3 → effective_budget=15; total retries 3 << 15.
    runner = _make_runner(spy, retries={"18-1-a": 1, "18-2-b": 1, "18-3-c": 1})

    result = dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=2,
        runner=runner,
        epic_state=_epic_state(story_ids, multiplier=5),
        epic_run_state_path=tmp_path / "e.yaml",
        transient_marker_classes=_NO_TRANSIENT,
        base_ref="main",
        trunk_allowlist=(),
    )

    assert set(result.dispatched_story_ids) == set(story_ids)
    assert result.final_state.current_state == "epic-complete"
    assert EPIC_BUDGET_EXHAUSTED_MARKER not in result.final_state.active_markers


def test_escalation_pauses_and_stops_admission(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _SubstrateSpy(monkeypatch, tmp_path)
    story_ids = ("18-1-a", "18-2-b", "18-3-c")
    # max=1 → 18-1-a escalates before any further admission; downstream do NOT
    # auto-advance (Story 15.1 AC-4). cleanup preserves on escalation.
    runner = _make_runner(spy, statuses={"18-1-a": "escalated"})

    result = dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=1,
        runner=runner,
        epic_state=_epic_state(story_ids),
        epic_run_state_path=tmp_path / "e.yaml",
        transient_marker_classes=_NO_TRANSIENT,
        base_ref="main",
        trunk_allowlist=(),
    )

    assert result.dispatched_story_ids == ("18-1-a",)
    assert result.paused_on_story_id == "18-1-a"
    assert result.final_state.current_state == "epic-paused-on-escalation"
    assert spy.created == ["18-1-a"]
    assert spy.cleaned == []  # escalated worktree is preserved (cleanup skipped)


def test_runner_exception_cleanup_worktree_still_called(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1 (review): when runner() raises, the try/finally in _run_unit ensures
    cleanup_worktree is still called — the created worktree is not orphaned."""
    spy = _SubstrateSpy(monkeypatch, tmp_path)
    story_ids = ("18-1-a",)

    def _failing_runner(
        *,
        story_id: str,
        index: int,
        total: int,
        worktree_path: pathlib.Path,
        run_state_path: pathlib.Path,
    ) -> StoryLoopOutcome:
        raise RuntimeError("simulated runner failure")

    with pytest.raises(RuntimeError, match="simulated runner failure"):
        dispatch_stories_parallel(
            "epic-18",
            run_id="run-1",
            story_ids=story_ids,
            max_parallel_stories=1,
            runner=_failing_runner,
            epic_state=_epic_state(story_ids),
            epic_run_state_path=tmp_path / "e.yaml",
            transient_marker_classes=_NO_TRANSIENT,
            base_ref="main",
            trunk_allowlist=(),
        )

    # Worktree was created; cleanup was called despite the runner exception.
    assert spy.created == ["18-1-a"]
    assert spy.cleaned == [("18-1-a", False)]


def test_escalated_worktree_preserved_cleanup_not_called(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2 (review): escalated worktree is preserved by skipping cleanup_worktree
    entirely. cleanup_worktree reads the SHARED run-state which is absent in
    parallel mode; the fix uses outcome.terminal_status directly."""
    spy = _SubstrateSpy(monkeypatch, tmp_path)
    story_ids = ("18-1-a",)
    runner = _make_runner(spy, statuses={"18-1-a": "escalated"})

    result = dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=1,
        runner=runner,
        epic_state=_epic_state(story_ids),
        epic_run_state_path=tmp_path / "e.yaml",
        transient_marker_classes=_NO_TRANSIENT,
        base_ref="main",
        trunk_allowlist=(),
    )

    assert result.final_state.current_state == "epic-paused-on-escalation"
    assert spy.created == ["18-1-a"]
    assert spy.cleaned == []  # escalated → cleanup skipped, worktree preserved


def test_budget_enforced_when_all_stories_admitted_simultaneously(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P3 (review): budget exhaustion fires even when story_count <=
    max_parallel_stories (all stories admitted at once, pending empties
    immediately). has_undispatched=bool(pending) or bool(in_flight) ensures
    the fold of an exhausting story sees the still-running sibling as
    "undispatched work remaining".

    18-1-a returns instantly with retries=2; 18-2-b sleeps 50ms so 18-1-a
    is guaranteed to complete first in a separate cf.wait batch — making the
    test deterministic (18-2-b is in in_flight when 18-1-a's fold runs)."""
    spy = _SubstrateSpy(monkeypatch, tmp_path)
    story_ids = ("18-1-a", "18-2-b")

    def _ordered_runner(
        *,
        story_id: str,
        index: int,
        total: int,
        worktree_path: pathlib.Path,
        run_state_path: pathlib.Path,
    ) -> StoryLoopOutcome:
        spy.enter_unit()
        try:
            if story_id == "18-2-b":
                time.sleep(0.05)  # slow sibling — still in-flight when 18-1-a folds
        finally:
            spy.exit_unit()
        return StoryLoopOutcome(
            terminal_status="merge-ready",  # type: ignore[arg-type]
            retries_consumed=2 if story_id == "18-1-a" else 0,
        )

    # multiplier=1, story_count=2 → effective_budget=2.
    # max_parallel_stories=2 → both admitted simultaneously (pending → empty).
    result = dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=2,
        runner=_ordered_runner,
        epic_state=_epic_state(story_ids, multiplier=1),
        epic_run_state_path=tmp_path / "e.yaml",
        transient_marker_classes=_NO_TRANSIENT,
        base_ref="main",
        trunk_allowlist=(),
    )

    # 18-1-a completed while 18-2-b was still in-flight → in_flight was
    # non-empty at fold time → has_undispatched=True → budget marker emitted.
    assert EPIC_BUDGET_EXHAUSTED_MARKER in result.final_state.active_markers
    assert result.final_state.per_epic_retry_budget.consumed == 2


def test_non_terminal_runner_status_raises(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _SubstrateSpy(monkeypatch, tmp_path)
    story_ids = ("18-1-a",)
    runner = _make_runner(spy, statuses={"18-1-a": "in-progress"})
    with pytest.raises(ValueError, match="non-terminal status"):
        dispatch_stories_parallel(
            "epic-18",
            run_id="run-1",
            story_ids=story_ids,
            max_parallel_stories=1,
            runner=runner,
            epic_state=_epic_state(story_ids),
            epic_run_state_path=tmp_path / "e.yaml",
            transient_marker_classes=_NO_TRANSIENT,
            base_ref="main",
            trunk_allowlist=(),
        )


# ---------------------------------------------------------------------------
# AC-3 / AC-4 — run_epic_loop wiring + bit-identical false path
# ---------------------------------------------------------------------------


def _write_sprint_status(
    tmp_path: pathlib.Path, development_status: dict[str, str]
) -> pathlib.Path:
    path = tmp_path / "sprint-status.yaml"
    path.write_text(
        yaml.safe_dump({"development_status": development_status}, sort_keys=False),
        encoding="utf-8",
    )
    return path


def test_run_epic_loop_parallel_branch_delegates(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3: parallel_stories=True drives the worktree-isolated parallel path."""
    spy = _SubstrateSpy(monkeypatch, tmp_path)
    sprint = _write_sprint_status(
        tmp_path,
        {"18-1-a": "ready-for-dev", "18-2-b": "ready-for-dev"},
    )
    result = run_epic_loop(
        "epic-18",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=tmp_path / "e.yaml",
        story_loop_runner=lambda **_: pytest.fail("sequential runner must not run"),
        transient_marker_classes=_NO_TRANSIENT,
        parallel_stories=True,
        max_parallel_stories=2,
        parallel_story_loop_runner=_make_runner(spy),
    )
    assert result.final_state.current_state == "epic-complete"
    assert sorted(spy.created) == ["18-1-a", "18-2-b"]


def test_run_epic_loop_parallel_without_runner_raises(
    tmp_path: pathlib.Path,
) -> None:
    sprint = _write_sprint_status(tmp_path, {"18-1-a": "ready-for-dev"})

    def _unused_runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        raise AssertionError("runner must not run")

    with pytest.raises(ValueError, match="parallel_story_loop_runner"):
        run_epic_loop(
            "epic-18",
            run_id="run-1",
            sprint_status_path=sprint,
            epic_run_state_path=tmp_path / "e.yaml",
            story_loop_runner=_unused_runner,
            transient_marker_classes=_NO_TRANSIENT,
            parallel_stories=True,
        )


def test_false_path_creates_no_worktree_and_is_byte_stable(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4: parallel_stories=False (the default) touches NO substrate primitive
    and produces a byte-stable epic-run-state.yaml."""

    def _boom(*_: object, **__: object) -> object:
        raise AssertionError("the false path must not create a worktree")

    monkeypatch.setattr(parallel_dispatch.worktree_lifecycle, "create_worktree", _boom)
    monkeypatch.setattr(
        parallel_dispatch.story_file_lock_module, "story_file_lock", _boom
    )

    sprint = _write_sprint_status(
        tmp_path,
        {"18-1-a": "ready-for-dev", "18-2-b": "ready-for-dev"},
    )

    def _seq_runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        return StoryLoopOutcome(terminal_status="merge-ready", retries_consumed=0)  # type: ignore[arg-type]

    erp_a = tmp_path / "a.yaml"
    erp_b = tmp_path / "b.yaml"
    for erp in (erp_a, erp_b):
        run_epic_loop(
            "epic-18",
            run_id="run-1",
            sprint_status_path=sprint,
            epic_run_state_path=erp,
            story_loop_runner=_seq_runner,
            transient_marker_classes=_NO_TRANSIENT,
            # parallel_stories defaults to False
        )
    assert erp_a.read_bytes() == erp_b.read_bytes()
