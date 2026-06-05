"""Story 18.2 — cross-story state-pollution detector + emitter contract matrix.

AC mapping (verbatim from
``_bmad-output/implementation-artifacts/18-2-...md``):

    * AC-1 — pure ``detect_state_pollution`` over the three ADR-005 Phase-2
      surfaces: per-surface matrix, None-skip, order-independence, canonical
      ordering; ``PollutionConflict`` fields == the marker's
      ``pointer_context_fields``; lost-update pre-image guard.
    * AC-4 — durable sub-classified marker emission + ``epic-paused-on-escalation``
      pause + drain-without-interruption at the dispatcher.
    * AC-5 — conflict context reaches ``EpicRunState.marker_contexts`` so the
      ``diagnostic_pointer`` placeholders resolve.
    * AC-7 — the 14.5 clean/polluted fixtures drive the LIVE detector; the
      evidence-root + aggregate arms (14.5 Review-Defer #2) are exercised.
    * AC-8 — taxonomy-neutral: the detector imports the pre-provisioned marker
      string; it declares no new class.
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
from loud_fail_harness.epic_lifecycle import StoryLoopOutcome, init_epic_run_state
from loud_fail_harness.parallel_pollution import (
    PARALLEL_STORY_STATE_POLLUTION_MARKER,
    PollutionConflict,
    StoryClaim,
    detect_aggregate_preimage_conflict,
    detect_state_pollution,
)

_TESTS_DIR = pathlib.Path(__file__).resolve().parent
_FIXTURE_DIR = _TESTS_DIR / "fixtures" / "parallel-state-pollution"
_TAXONOMY_PATH = _TESTS_DIR.parents[2] / "schemas" / "marker-taxonomy.yaml"

_NO_TRANSIENT: frozenset[str] = frozenset()


def _load_yaml(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _claims_from_fixture(name: str) -> tuple[StoryClaim, ...]:
    fixture = _load_yaml(_FIXTURE_DIR / name)
    return tuple(StoryClaim(**wt) for wt in fixture["worktrees"])


# ---------------------------------------------------------------------------
# AC-1 — pure detector: per-surface matrix
# ---------------------------------------------------------------------------


def test_pollution_conflict_fields_are_the_marker_pointer_context_fields() -> None:
    """AC-1: PollutionConflict carries exactly the marker's
    pointer_context_fields (so emission is a mechanical projection)."""
    taxonomy = _load_yaml(_TAXONOMY_PATH)
    entry = next(
        e
        for e in taxonomy["markers"]
        if e["marker_class"] == PARALLEL_STORY_STATE_POLLUTION_MARKER
    )
    model_fields = set(PollutionConflict.model_fields)
    assert set(entry["pointer_context_fields"]) <= model_fields
    assert model_fields == {
        "sub_classification",
        "story_id",
        "conflicting_story_id",
        "shared_surface",
    }


def test_detect_shared_port_collision() -> None:
    claims = (
        StoryClaim(
            story_id="b-story", allocated_port=4317, aggregate_claim_story_id="b-story"
        ),
        StoryClaim(
            story_id="a-story", allocated_port=4317, aggregate_claim_story_id="a-story"
        ),
    )
    (conflict,) = detect_state_pollution(claims)
    assert conflict.sub_classification == "shared-port-collision"
    assert conflict.shared_surface == "shared-port"
    # Canonical story-id ordering (smaller id first), order-independent.
    assert conflict.story_id == "a-story"
    assert conflict.conflicting_story_id == "b-story"


def test_detect_shared_evidence_root_collision() -> None:
    claims = (
        StoryClaim(
            story_id="a-story",
            evidence_subpath="evidence/shared",
            aggregate_claim_story_id="a-story",
        ),
        StoryClaim(
            story_id="b-story",
            evidence_subpath="evidence/shared",
            aggregate_claim_story_id="b-story",
        ),
    )
    (conflict,) = detect_state_pollution(claims)
    assert conflict.sub_classification == "shared-evidence-root-collision"
    assert conflict.shared_surface == "shared-evidence-root"


def test_detect_aggregate_cross_write_collision() -> None:
    """Two distinct stories claiming the SAME aggregate story-id (one story-id
    owned by two live worktrees) — closes 14.5 Review-Defer #2."""
    claims = (
        StoryClaim(story_id="a-story", aggregate_claim_story_id="shared-claim"),
        StoryClaim(story_id="b-story", aggregate_claim_story_id="shared-claim"),
    )
    (conflict,) = detect_state_pollution(claims)
    assert conflict.sub_classification == "aggregate-run-state-cross-write"
    assert conflict.shared_surface == "aggregate-run-state"


def test_none_surface_contributes_no_conflict() -> None:
    """A story that has not provisioned a port cannot collide on the port
    pool (None-skip)."""
    claims = (
        StoryClaim(story_id="a", allocated_port=None, aggregate_claim_story_id="a"),
        StoryClaim(story_id="b", allocated_port=None, aggregate_claim_story_id="b"),
    )
    assert detect_state_pollution(claims) == ()


def test_detector_is_order_independent() -> None:
    a = StoryClaim(story_id="a", allocated_port=5000, aggregate_claim_story_id="a")
    b = StoryClaim(story_id="b", allocated_port=5000, aggregate_claim_story_id="b")
    assert detect_state_pollution((a, b)) == detect_state_pollution((b, a))


def test_same_story_id_is_not_a_cross_story_collision() -> None:
    """A single story appearing once never self-collides; identical surface
    values across the SAME story-id are not cross-story."""
    claims = (
        StoryClaim(story_id="a", allocated_port=5000, aggregate_claim_story_id="a"),
    )
    assert detect_state_pollution(claims) == ()


def test_canonical_ordering_across_multiple_surfaces() -> None:
    claims = (
        StoryClaim(
            story_id="b",
            allocated_port=4000,
            evidence_subpath="ev/shared",
            aggregate_claim_story_id="b",
        ),
        StoryClaim(
            story_id="a",
            allocated_port=4000,
            evidence_subpath="ev/shared",
            aggregate_claim_story_id="a",
        ),
    )
    conflicts = detect_state_pollution(claims)
    keys = [
        (c.sub_classification, c.story_id, c.conflicting_story_id) for c in conflicts
    ]
    assert keys == sorted(keys)
    assert {c.sub_classification for c in conflicts} == {
        "shared-port-collision",
        "shared-evidence-root-collision",
    }


# ---------------------------------------------------------------------------
# AC-1 — lost-update pre-image guard
# ---------------------------------------------------------------------------


def _epic_state(story_ids: tuple[str, ...], *, multiplier: int = 2):
    return init_epic_run_state("epic-18", "run-1", story_ids, multiplier=multiplier)


def test_preimage_guard_absent_file_is_no_conflict(tmp_path: pathlib.Path) -> None:
    state = _epic_state(("18-1-a",))
    assert (
        detect_aggregate_preimage_conflict(
            tmp_path / "absent.yaml", state, story_id="18-1-a"
        )
        is None
    )


def test_preimage_guard_matching_on_disk_is_no_conflict(
    tmp_path: pathlib.Path,
) -> None:
    from loud_fail_harness.epic_run_state import advance_epic_run_state

    state = _epic_state(("18-1-a",))
    path = tmp_path / "epic-run-state.yaml"
    advance_epic_run_state(path, state, transient_marker_classes=_NO_TRANSIENT)
    persisted = advance_epic_run_state(
        path, state, transient_marker_classes=_NO_TRANSIENT
    ).next_state
    assert (
        detect_aggregate_preimage_conflict(path, persisted, story_id="18-1-a") is None
    )


def test_preimage_guard_divergent_on_disk_fires(tmp_path: pathlib.Path) -> None:
    """An out-of-band write (on-disk disagrees with the in-memory pre-image)
    surfaces an aggregate-run-state-cross-write conflict."""
    from loud_fail_harness.epic_run_state import advance_epic_run_state

    state = _epic_state(("18-1-a", "18-2-b"))
    path = tmp_path / "epic-run-state.yaml"
    advance_epic_run_state(path, state, transient_marker_classes=_NO_TRANSIENT)
    diverged = state.model_copy(update={"current_state": "epic-complete"})
    conflict = detect_aggregate_preimage_conflict(path, diverged, story_id="18-1-a")
    assert conflict is not None
    assert conflict.sub_classification == "aggregate-run-state-cross-write"
    assert conflict.story_id == "18-1-a"


# ---------------------------------------------------------------------------
# AC-7 — fixture-driven witness (clean → 0, polluted → 1 + declared context)
# ---------------------------------------------------------------------------


def test_clean_fixture_yields_zero_conflicts() -> None:
    assert detect_state_pollution(_claims_from_fixture("clean-parallel-state.yaml")) == ()


def test_polluted_fixture_yields_declared_conflict() -> None:
    fixture = _load_yaml(_FIXTURE_DIR / "polluted-parallel-state.yaml")
    (conflict,) = detect_state_pollution(
        _claims_from_fixture("polluted-parallel-state.yaml")
    )
    assert conflict.sub_classification == fixture["expected_sub_classification"]
    ctx = fixture["collision_context"]
    # Modulo the canonical story-id ordering from AC-1.
    assert {conflict.story_id, conflict.conflicting_story_id} == {
        ctx["story_id"],
        ctx["conflicting_story_id"],
    }
    assert conflict.shared_surface == ctx["shared_surface"]


# ---------------------------------------------------------------------------
# AC-4 / AC-5 — dispatcher emit + pause + drain + context
# ---------------------------------------------------------------------------


class _Spy:
    """Patches the four composed substrate seams so the dispatcher runs without
    real git (mirrors test_parallel_dispatch._SubstrateSpy)."""

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        self._lock = threading.Lock()
        self.created: list[str] = []

        class _FakeWorktree:
            def __init__(self, worktree_path: pathlib.Path) -> None:
                self.worktree_path = worktree_path

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

        def _cleanup_worktree(story_id: str, **_: object) -> None:
            return None

        @contextlib.contextmanager
        def _story_file_lock(
            story_id: str, *, worktree_path: pathlib.Path, **_: object
        ) -> Iterator[None]:
            yield None

        def _worktree_run_state_path(story_id: str, **_: object) -> pathlib.Path:
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


def _runner(*, sleep: dict[str, float] | None = None):
    sleep = sleep or {}

    def runner(
        *,
        story_id: str,
        index: int,
        total: int,
        worktree_path: pathlib.Path,
        run_state_path: pathlib.Path,
    ) -> StoryLoopOutcome:
        if story_id in sleep:
            time.sleep(sleep[story_id])
        return StoryLoopOutcome(terminal_status="merge-ready", retries_consumed=0)  # type: ignore[arg-type]

    return runner


def _port_provider(ports: dict[str, int]):
    def provider(*, story_id: str) -> StoryClaim:
        return StoryClaim(
            story_id=story_id,
            allocated_port=ports[story_id],
            evidence_subpath=f"evidence/{story_id}",
            aggregate_claim_story_id=story_id,
        )

    return provider


_POLLUTION_MARKER = f"{PARALLEL_STORY_STATE_POLLUTION_MARKER}: shared-port-collision"


def test_clean_parallel_run_emits_no_pollution_marker(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = _Spy(monkeypatch, tmp_path)
    story_ids = ("18-1-a", "18-2-b")
    result = parallel_dispatch.dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=2,
        runner=_runner(),
        epic_state=_epic_state(story_ids),
        epic_run_state_path=tmp_path / "e.yaml",
        transient_marker_classes=_NO_TRANSIENT,
        base_ref="main",
        trunk_allowlist=(),
        claim_provider=_port_provider({"18-1-a": 4317, "18-2-b": 4318}),
    )
    assert result.final_state.current_state == "epic-complete"
    assert _POLLUTION_MARKER not in result.final_state.active_markers
    assert set(spy.created) == set(story_ids)


def test_colliding_parallel_run_emits_durable_marker_and_pauses(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4: a colliding claim emits the durable sub-classified marker, pauses
    the epic on epic-paused-on-escalation, never auto-resolves, and drains the
    in-flight unit without interruption. AC-5: the conflict context reaches
    EpicRunState.marker_contexts so the diagnostic_pointer placeholders resolve."""
    spy = _Spy(monkeypatch, tmp_path)
    story_ids = ("18-1-a", "18-2-b")
    erp = tmp_path / "e.yaml"
    result = parallel_dispatch.dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=2,
        # 18-1-a sleeps so it is in-flight when 18-2-b's pre-admission conflict
        # fires — proves the in-flight unit drains (is never interrupted).
        runner=_runner(sleep={"18-1-a": 0.05}),
        epic_state=_epic_state(story_ids),
        epic_run_state_path=erp,
        transient_marker_classes=_NO_TRANSIENT,
        base_ref="main",
        trunk_allowlist=(),
        claim_provider=_port_provider({"18-1-a": 4317, "18-2-b": 4317}),
    )

    assert result.final_state.current_state == "epic-paused-on-escalation"
    assert _POLLUTION_MARKER in result.final_state.active_markers
    # No auto-resolution: 18-2-b was never admitted (the collision paused
    # admission); 18-1-a drained and completed.
    assert spy.created == ["18-1-a"]
    assert result.dispatched_story_ids == ("18-1-a",)
    assert result.paused_on_story_id in story_ids

    # AC-5: the marker context carries the two colliding story-ids + the surface.
    ctx = result.final_state.marker_contexts[PARALLEL_STORY_STATE_POLLUTION_MARKER]
    assert {ctx["story_id"], ctx["conflicting_story_id"]} == set(story_ids)
    assert ctx["shared_surface"] == "shared-port"

    # Durable: the pause + marker + context survived the atomic write to disk.
    on_disk = yaml.safe_load(erp.read_text(encoding="utf-8"))
    assert on_disk["current_state"] == "epic-paused-on-escalation"
    assert _POLLUTION_MARKER in on_disk["active_markers"]
    assert (
        on_disk["marker_contexts"][PARALLEL_STORY_STATE_POLLUTION_MARKER][
            "shared_surface"
        ]
        == "shared-port"
    )


def test_no_claim_provider_keeps_18_1_behaviour(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Detection is inert when no claim_provider is injected — the parallel path
    behaves exactly as Story 18.1 shipped it (no pollution marker, no pause)."""
    spy = _Spy(monkeypatch, tmp_path)
    story_ids = ("18-1-a", "18-2-b")
    result = parallel_dispatch.dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=2,
        runner=_runner(),
        epic_state=_epic_state(story_ids),
        epic_run_state_path=tmp_path / "e.yaml",
        transient_marker_classes=_NO_TRANSIENT,
        base_ref="main",
        trunk_allowlist=(),
    )
    assert result.final_state.current_state == "epic-complete"
    assert result.final_state.active_markers == ()
    assert set(spy.created) == set(story_ids)


def test_fold_boundary_preimage_conflict_emits_aggregate_marker(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cadence-2 coverage (P2 review fix): an out-of-band aggregate write
    detected at the completion-fold boundary emits the durable
    ``aggregate-run-state-cross-write`` marker even though cadence-1
    (pre-admission claim checks) found no collision — disjoint ports mean
    ``detect_state_pollution`` returns nothing; only the monkeypatched
    ``detect_aggregate_preimage_conflict`` fires at the fold boundary.

    Also validates that the P1 reorder (cadence-2 runs BEFORE
    ``if worker_errors: raise``) keeps this path reachable.
    """
    from loud_fail_harness import parallel_pollution as pp

    def _fake_preimage(
        path: pathlib.Path,
        state: object,
        *,
        story_id: str,
    ) -> PollutionConflict:
        return PollutionConflict(
            sub_classification="aggregate-run-state-cross-write",
            story_id=story_id,
            conflicting_story_id=story_id,
            shared_surface="aggregate-run-state",
        )

    monkeypatch.setattr(pp, "detect_aggregate_preimage_conflict", _fake_preimage)

    spy = _Spy(monkeypatch, tmp_path)
    story_ids = ("18-1-a", "18-2-b")
    erp = tmp_path / "e.yaml"
    result = parallel_dispatch.dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=2,
        runner=_runner(),
        epic_state=_epic_state(story_ids),
        epic_run_state_path=erp,
        transient_marker_classes=_NO_TRANSIENT,
        base_ref="main",
        trunk_allowlist=(),
        claim_provider=_port_provider({"18-1-a": 4317, "18-2-b": 4318}),
    )

    _AGGREGATE_MARKER = (
        f"{PARALLEL_STORY_STATE_POLLUTION_MARKER}: aggregate-run-state-cross-write"
    )
    assert result.final_state.current_state == "epic-paused-on-escalation"
    assert _AGGREGATE_MARKER in result.final_state.active_markers

    ctx = result.final_state.marker_contexts.get(PARALLEL_STORY_STATE_POLLUTION_MARKER)
    assert ctx is not None
    assert ctx["shared_surface"] == "aggregate-run-state"

    on_disk = yaml.safe_load(erp.read_text(encoding="utf-8"))
    assert on_disk["current_state"] == "epic-paused-on-escalation"
    assert _AGGREGATE_MARKER in on_disk["active_markers"]
    _ = spy
