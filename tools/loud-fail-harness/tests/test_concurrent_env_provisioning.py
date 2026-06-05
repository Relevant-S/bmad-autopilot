"""Contract-coverage matrix for the concurrent-provisioning discipline
(Story 18.3 — the FR7 extension that composes with Story 18.2's detection).

AC mapping (verbatim from
``_bmad-output/implementation-artifacts/18-3-...md``):

    * AC-1 — ``DisjointPortAllocator`` guarantees no two concurrently-live
      stories share a port (re-roll over ``allocate_ephemeral_port``); released
      ports are re-allocatable; exhaustion raises a typed loud-fail.
    * AC-2 — ``story_env_namespace`` is a deterministic, collision-free,
      grammar-valid env-var prefix; per-story PID isolation is witnessed.
    * AC-3 — the production ``ParallelEnvClaimProvider`` sources a disjoint port
      + namespace + evidence subpath + aggregate-claim id, pre-seeds the carrier,
      and (driven through the dispatcher) keeps Story 18.2's detector silent on a
      clean run; the ``claim_release`` seam frees ports at terminal cleanup.
    * AC-4 — per-story teardown tears down ONLY that story's env; A's released
      port does not affect B's held port.
    * AC-5 — per-story orphan cleanup emits one ``orphan-process-cleanup`` record
      per orphan port, scoped to that story's per-worktree run-state.
    * AC-6 — ``parallel_stories: false`` constructs no allocator/provider and the
      sequential env-provisioning primitive is unchanged (regression guard).
"""

from __future__ import annotations

import contextlib
import pathlib
import re
import threading
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
import yaml

from loud_fail_harness import env_provisioning, parallel_dispatch
from loud_fail_harness.env_provisioning import (
    ORPHAN_PROCESS_CLEANUP_MARKER,
    DisjointPortAllocator,
    DisjointPortExhausted,
    ParallelEnvClaimProvider,
    ProvisionedEnv,
    cleanup_orphan_processes,
    pre_seed_parallel_env,
    provision_env,
    story_env_namespace,
    teardown_env,
)
from loud_fail_harness.epic_lifecycle import StoryLoopOutcome, init_epic_run_state
from loud_fail_harness.parallel_pollution import (
    PARALLEL_STORY_STATE_POLLUTION_MARKER,
    StoryClaim,
)
from loud_fail_harness.specialist_dispatch import MarkerClassRegistry

_POSIX_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIXED_NOW = datetime(2026, 6, 5, 12, 0, 0, tzinfo=timezone.utc)


class _ScriptedAlloc:
    """Deterministic ``allocate_ephemeral_port`` stub returning a fixed sequence
    (the AC-1 colliding-then-free injection)."""

    def __init__(self, ports: list[int]) -> None:
        self._it = iter(ports)

    def __call__(self) -> int:
        return next(self._it)


# --------------------------------------------------------------------------- #
# AC-1 — DisjointPortAllocator                                                #
# --------------------------------------------------------------------------- #


def test_disjoint_allocator_distinct_ports_across_live_allocations() -> None:
    alloc = DisjointPortAllocator(allocate=_ScriptedAlloc([7001, 7002, 7003, 7004]))
    ports = [alloc.allocate() for _ in range(4)]
    assert ports == [7001, 7002, 7003, 7004]
    assert len(set(ports)) == 4


def test_disjoint_allocator_real_primitive_yields_distinct_live_ports() -> None:
    """The same disjointness holds over the REAL stdlib primitive — the live
    set prevents a repeat even if the kernel hands one back."""
    alloc = DisjointPortAllocator()
    ports = [alloc.allocate() for _ in range(5)]
    assert len(set(ports)) == 5


def test_disjoint_allocator_released_port_is_reallocatable() -> None:
    alloc = DisjointPortAllocator(allocate=_ScriptedAlloc([8001, 8001]))
    first = alloc.allocate()
    assert first == 8001
    alloc.release(8001)
    # A freed port is reusable by a later wave (Story 18.2 AC-2 semantics).
    assert alloc.allocate() == 8001


def test_disjoint_allocator_rerolls_past_held_port() -> None:
    alloc = DisjointPortAllocator(allocate=_ScriptedAlloc([5000, 5000, 5001]))
    assert alloc.allocate() == 5000
    # Second allocate re-rolls past the already-held 5000 and lands on 5001.
    assert alloc.allocate() == 5001


def test_disjoint_allocator_exhaustion_raises_typed_loud_fail() -> None:
    # Always returns the same already-held port → bounded re-rolls exhaust.
    alloc = DisjointPortAllocator(allocate=lambda: 6000, max_rerolls=3)
    assert alloc.allocate() == 6000
    with pytest.raises(DisjointPortExhausted):
        alloc.allocate()


# --------------------------------------------------------------------------- #
# AC-2 — story_env_namespace + per-story PID isolation                        #
# --------------------------------------------------------------------------- #


def test_namespace_distinct_ids_yield_distinct_prefixes() -> None:
    ids = (
        "18-3-concurrent-env-provisioning-discipline-fr7-extension",
        "18-2-cross-story-state-pollution-detection",
        "4-3-full-env-provisioning-lifecycle",
        "9-3-qa-wrapper-mobile",
    )
    prefixes = {story_env_namespace(sid) for sid in ids}
    assert len(prefixes) == len(ids)


def test_namespace_is_deterministic() -> None:
    sid = "18-3-concurrent-env-provisioning-discipline-fr7-extension"
    assert story_env_namespace(sid) == story_env_namespace(sid)


def test_namespace_matches_posix_env_grammar() -> None:
    for sid in ("18-3-a", "1-1-harness", "9-3-qa-wrapper-mobile-mcp"):
        assert _POSIX_ENV_NAME.match(story_env_namespace(sid))


def test_namespace_matches_ac_example() -> None:
    assert (
        story_env_namespace(
            "18-3-concurrent-env-provisioning-discipline-fr7-extension"
        )
        == "BMAD_AUTOMATION_STORY_18_3_CONCURRENT_ENV_PROVISIONING_"
        "DISCIPLINE_FR7_EXTENSION_"
    )


def test_namespace_rejects_empty_story_id() -> None:
    with pytest.raises(ValueError, match="story_id must be non-empty"):
        story_env_namespace("")


class _FixedPidProvisioner:
    """Provisioner returning a ProvisionedEnv with a caller-fixed pid (so two
    concurrent stories' PIDs are observably distinct)."""

    def __init__(self, *, pid: int) -> None:
        self._pid = pid

    def provision(
        self, story_id: str, project_type: str, port: int
    ) -> ProvisionedEnv:
        return ProvisionedEnv(
            env_kind="web", port=port, pid=self._pid, started_at=_FIXED_NOW
        )


def _seed_run_state(path: pathlib.Path, story_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.1",
                "story_id": story_id,
                "run_id": "run-18-3",
                "current_state": "review",
                "branch_name": f"story/{story_id}",
                "dispatched_specialist": None,
                "last_envelope": None,
                "pending_qa_dispatch_payload": None,
                "retry_history": [],
                "active_markers": [],
                "cost_to_date_by_specialist": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _read(path: pathlib.Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _env_setup_registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(
        marker_classes=frozenset({env_provisioning.ENV_SETUP_FAILED_MARKER})
    )


def _orphan_registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(
        marker_classes=frozenset({ORPHAN_PROCESS_CLEANUP_MARKER})
    )


def test_per_story_pid_isolation_across_worktree_run_states(
    tmp_path: pathlib.Path,
) -> None:
    """Two concurrent stories' provisioned-env PIDs land in their OWN
    per-worktree run-states and never cross-write (AC-2)."""
    rs_a = tmp_path / "a" / "run-state.yaml"
    rs_b = tmp_path / "b" / "run-state.yaml"
    _seed_run_state(rs_a, "18-3-a")
    _seed_run_state(rs_b, "18-3-b")
    registry = _env_setup_registry()

    provision_env(
        story_id="18-3-a",
        project_type="web",
        provisioner=_FixedPidProvisioner(pid=4101),  # type: ignore[arg-type]
        port=5101,
        run_state_path=rs_a,
        registry=registry,
        event_appender=lambda _e: None,
        timestamp_factory=lambda: _FIXED_NOW,
    )
    provision_env(
        story_id="18-3-b",
        project_type="web",
        provisioner=_FixedPidProvisioner(pid=4202),  # type: ignore[arg-type]
        port=5202,
        run_state_path=rs_b,
        registry=registry,
        event_appender=lambda _e: None,
        timestamp_factory=lambda: _FIXED_NOW,
    )

    assert _read(rs_a)["provisioned_env"]["pid"] == 4101
    assert _read(rs_b)["provisioned_env"]["pid"] == 4202
    # B's provisioning never perturbed A's record.
    assert _read(rs_a)["provisioned_env"]["port"] == 5101


# --------------------------------------------------------------------------- #
# AC-3 — ParallelEnvClaimProvider + dispatcher wiring                         #
# --------------------------------------------------------------------------- #


def test_provider_returns_disjoint_claim_and_preseeds_carrier(
    tmp_path: pathlib.Path,
) -> None:
    provider = ParallelEnvClaimProvider(
        run_id="run-18-3",
        allocator=DisjointPortAllocator(),
        repo_root=tmp_path,
    )
    claim_a = provider(story_id="18-3-a")
    claim_b = provider(story_id="18-3-b")

    assert claim_a.allocated_port != claim_b.allocated_port
    assert claim_a.evidence_subpath == "qa-evidence/18-3-a/run-18-3/"
    assert claim_a.aggregate_claim_story_id == "18-3-a"
    assert claim_b.evidence_subpath == "qa-evidence/18-3-b/run-18-3/"
    assert claim_b.aggregate_claim_story_id == "18-3-b"

    base = tmp_path / "_bmad" / "automation" / "worktrees"
    # The carrier: BOTH stories' per-worktree run-states are pre-seeded with
    # their own disjoint port + env namespace (Story 14.4 path).
    rs_a = base / "18-3-a" / "run-state.yaml"
    seeded_a = _read(rs_a)
    assert seeded_a["allocated_port"] == claim_a.allocated_port
    assert seeded_a["env_namespace"] == story_env_namespace("18-3-a")

    rs_b = base / "18-3-b" / "run-state.yaml"
    seeded_b = _read(rs_b)
    assert seeded_b["allocated_port"] == claim_b.allocated_port
    assert seeded_b["env_namespace"] == story_env_namespace("18-3-b")


class _Spy:
    """Patches the dispatcher's four substrate seams so it runs without git."""

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
            parallel_dispatch.story_file_lock_module, "story_file_lock", _story_file_lock
        )
        monkeypatch.setattr(
            parallel_dispatch, "worktree_run_state_path", _worktree_run_state_path
        )


def _epic_state(story_ids: tuple[str, ...]):
    return init_epic_run_state("epic-18", "run-1", story_ids, multiplier=2)


def _clean_runner(
    *,
    story_id: str,
    index: int,
    total: int,
    worktree_path: pathlib.Path,
    run_state_path: pathlib.Path,
) -> StoryLoopOutcome:
    return StoryLoopOutcome(terminal_status="merge-ready", retries_consumed=0)  # type: ignore[arg-type]


def test_production_provider_clean_run_emits_no_pollution_marker(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The provider's disjointness keeps Story 18.2's detector silent — the
    positive composition witness proving the provider->detector wiring is live
    (AC-3)."""
    spy = _Spy(monkeypatch, tmp_path)
    story_ids = ("18-3-a", "18-3-b")
    allocator = DisjointPortAllocator()
    provider = ParallelEnvClaimProvider(
        run_id="run-1", allocator=allocator, repo_root=tmp_path
    )
    result = parallel_dispatch.dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=2,
        runner=_clean_runner,
        epic_state=_epic_state(story_ids),
        epic_run_state_path=tmp_path / "e.yaml",
        transient_marker_classes=frozenset(),
        base_ref="main",
        trunk_allowlist=(),
        repo_root=tmp_path,
        claim_provider=provider,
        claim_release=allocator.release,
    )
    assert result.final_state.current_state == "epic-complete"
    assert all(
        not m.startswith(PARALLEL_STORY_STATE_POLLUTION_MARKER)
        for m in result.final_state.active_markers
    )
    assert set(spy.created) == set(story_ids)

    # Disjointness witness: the two stories pre-seeded DISTINCT ports.
    base = tmp_path / "_bmad" / "automation" / "worktrees"
    port_a = _read(base / "18-3-a" / "run-state.yaml")["allocated_port"]
    port_b = _read(base / "18-3-b" / "run-state.yaml")["allocated_port"]
    assert port_a != port_b


def test_claim_release_seam_frees_ports_at_terminal_cleanup(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dispatcher invokes claim_release at the SAME terminal-cleanup point
    it drops the story from the live registry (AC-3)."""
    _Spy(monkeypatch, tmp_path)
    released: list[int] = []
    story_ids = ("18-3-a", "18-3-b")
    ports = {"18-3-a": 4317, "18-3-b": 4318}

    def _provider(*, story_id: str) -> StoryClaim:
        return StoryClaim(
            story_id=story_id,
            allocated_port=ports[story_id],
            evidence_subpath=f"qa-evidence/{story_id}/run-1",
            aggregate_claim_story_id=story_id,
        )

    parallel_dispatch.dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=2,
        runner=_clean_runner,
        epic_state=_epic_state(story_ids),
        epic_run_state_path=tmp_path / "e.yaml",
        transient_marker_classes=frozenset(),
        base_ref="main",
        trunk_allowlist=(),
        claim_provider=_provider,
        claim_release=released.append,
    )
    assert sorted(released) == [4317, 4318]


# --------------------------------------------------------------------------- #
# AC-4 — per-story teardown isolation                                         #
# --------------------------------------------------------------------------- #


class _RecordingTeardown:
    def __init__(self) -> None:
        self.calls: list[ProvisionedEnv] = []

    def teardown(self, provisioned_env: ProvisionedEnv) -> None:
        self.calls.append(provisioned_env)


def test_per_story_teardown_tears_down_only_that_story(
    tmp_path: pathlib.Path,
) -> None:
    rs_a = tmp_path / "a" / "run-state.yaml"
    rs_b = tmp_path / "b" / "run-state.yaml"
    _seed_run_state(rs_a, "18-3-a")
    _seed_run_state(rs_b, "18-3-b")
    registry = _env_setup_registry()
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()

    pe_a = ProvisionedEnv(env_kind="web", port=5101, pid=4101, started_at=_FIXED_NOW)
    pe_b = ProvisionedEnv(env_kind="web", port=5202, pid=4202, started_at=_FIXED_NOW)
    for path, pe in ((rs_a, pe_a), (rs_b, pe_b)):
        provision_env(
            story_id=path.parent.name,
            project_type="web",
            provisioner=_FixedPidProvisioner(pid=pe.pid),  # type: ignore[arg-type]
            port=pe.port,
            run_state_path=path,
            registry=registry,
            event_appender=lambda _e: None,
            timestamp_factory=lambda: _FIXED_NOW,
        )

    teardown_a = _RecordingTeardown()
    teardown_env(
        provisioned_env=pe_a,
        teardown_fn=teardown_a,  # type: ignore[arg-type]
        run_state_path=rs_a,
        evidence_root=evidence_root,
        registry=registry,
        event_appender=lambda _e: None,
        story_id="18-3-a",
        timestamp_factory=lambda: _FIXED_NOW,
    )

    # A's env is torn down (cleared + its PID terminated); B is fully intact.
    assert teardown_a.calls == [pe_a]
    assert "provisioned_env" not in _read(rs_a)
    assert _read(rs_b)["provisioned_env"]["pid"] == 4202
    assert _read(rs_b)["provisioned_env"]["port"] == 5202


def test_released_port_does_not_affect_sibling_held_port() -> None:
    """Releasing A's port leaves B's port held (AC-4): a re-roll still skips the
    still-live B and lands on a fresh port, while A's freed value is reusable."""
    alloc = DisjointPortAllocator(allocate=_ScriptedAlloc([4001, 4002, 4002, 4003]))
    port_a = alloc.allocate()  # 4001
    port_b = alloc.allocate()  # 4002
    alloc.release(port_a)
    # Next allocate sees 4002 (B, still held) -> re-rolls -> 4003.
    assert alloc.allocate() == 4003
    assert port_b == 4002


# --------------------------------------------------------------------------- #
# AC-5 — per-story orphan cleanup under parallel mode                         #
# --------------------------------------------------------------------------- #


class _StaticOrphanProbe:
    def __init__(self, orphans: tuple[tuple[int, int], ...]) -> None:
        self._orphans = orphans

    def probe(self) -> tuple[tuple[int, int], ...]:
        return self._orphans


class _RecordingOrphanTerminator:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def terminate(self, port: int, pid: int) -> None:
        self.calls.append((port, pid))


def test_per_story_orphan_cleanup_emits_marker_per_orphan_scoped_to_story(
    tmp_path: pathlib.Path,
) -> None:
    rs_a = tmp_path / "a" / "run-state.yaml"
    rs_b = tmp_path / "b" / "run-state.yaml"
    _seed_run_state(rs_a, "18-3-a")
    _seed_run_state(rs_b, "18-3-b")
    # Both stories carry a stale provisioned_env from a prior crashed run.
    for path, port, pid in ((rs_a, 5101, 4101), (rs_b, 5202, 4202)):
        d = _read(path)
        d["provisioned_env"] = {
            "env_kind": "web",
            "port": port,
            "pid": pid,
            "started_at": "2026-06-05T10:00:00+00:00",
        }
        path.write_text(yaml.safe_dump(d, sort_keys=False), encoding="utf-8")

    registry = _orphan_registry()
    terminator_a = _RecordingOrphanTerminator()
    emissions = cleanup_orphan_processes(
        rs_a,
        _StaticOrphanProbe(((5101, 4101), (5301, 4301))),  # type: ignore[arg-type]
        terminator_a,  # type: ignore[arg-type]
        registry,
        lambda _e: None,
        story_id="18-3-a",
        env_kind="web",
    )

    # Exactly N orphan-process-cleanup records, one per orphan port (port+pid).
    assert len(emissions) == 2
    assert [e.marker_class for e in emissions] == [ORPHAN_PROCESS_CLEANUP_MARKER] * 2
    assert [e.context for e in emissions] == [
        {"port": 5101, "pid": 4101},
        {"port": 5301, "pid": 4301},
    ]
    assert terminator_a.calls == [(5101, 4101), (5301, 4301)]

    # Scoped to A's per-worktree run-state: A's stale env cleared, B untouched.
    assert "provisioned_env" not in _read(rs_a)
    assert _read(rs_b)["provisioned_env"]["pid"] == 4202


# --------------------------------------------------------------------------- #
# AC-6 — sequential-mode bit-identity regression guard                       #
# --------------------------------------------------------------------------- #


def test_sequential_mode_constructs_no_allocator_or_provider(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """parallel_stories: false constructs NO DisjointPortAllocator and NO
    ParallelEnvClaimProvider — the parallel substrate is reached only on the
    parallel branch (AC-6)."""
    from loud_fail_harness.epic_lifecycle import run_epic_loop

    def _boom(*_a: object, **_k: object) -> object:
        raise AssertionError("the sequential path must not construct this")

    monkeypatch.setattr(env_provisioning, "DisjointPortAllocator", _boom)
    monkeypatch.setattr(env_provisioning, "ParallelEnvClaimProvider", _boom)

    sprint = tmp_path / "sprint-status.yaml"
    sprint.write_text(
        yaml.safe_dump(
            {"development_status": {"18-3-a": "ready-for-dev"}}, sort_keys=False
        ),
        encoding="utf-8",
    )

    def _seq_runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        return StoryLoopOutcome(terminal_status="merge-ready", retries_consumed=0)  # type: ignore[arg-type]

    result = run_epic_loop(
        "epic-18",
        run_id="run-1",
        sprint_status_path=sprint,
        epic_run_state_path=tmp_path / "e.yaml",
        story_loop_runner=_seq_runner,
        transient_marker_classes=frozenset(),
        parallel_stories=False,
    )
    assert result.final_state.current_state == "epic-complete"


def test_sequential_allocate_ephemeral_port_unchanged() -> None:
    """The pre-18.3 ephemeral-port primitive the sequential path calls is
    untouched — still a valid single bind(0) allocation (AC-6)."""
    port = env_provisioning.allocate_ephemeral_port()
    assert 1024 < port <= 65535


def test_pre_seed_parallel_env_writes_only_additive_keys(
    tmp_path: pathlib.Path,
) -> None:
    """The carrier writes ONLY additive top-level keys, preserving every existing
    run-state field (the byte-stability discipline behind AC-6)."""
    rs = tmp_path / "run-state.yaml"
    _seed_run_state(rs, "18-3-a")
    before = _read(rs)
    pre_seed_parallel_env(rs, allocated_port=5151, env_namespace="BMAD_X_")
    after = _read(rs)
    assert after["allocated_port"] == 5151
    assert after["env_namespace"] == "BMAD_X_"
    # Every pre-existing field is preserved unchanged.
    for key, value in before.items():
        assert after[key] == value


# --------------------------------------------------------------------------- #
# AC-3 negative composition witness                                           #
# --------------------------------------------------------------------------- #


def test_colliding_provider_trips_pollution_detector(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deliberately-colliding provider (same port for two stories) trips
    Story 18.2's detector — the negative composition witness proving the
    provider->detector wiring is live (AC-3).

    The positive witness (disjoint provider keeps detector silent) is in
    test_production_provider_clean_run_emits_no_pollution_marker above.
    Both witnesses together prove the wiring is live: the detector fires when
    it should and stays silent when it should not.
    """
    _Spy(monkeypatch, tmp_path)
    story_ids = ("18-3-a", "18-3-b")
    colliding_port = 9999

    def _colliding_provider(*, story_id: str) -> StoryClaim:
        return StoryClaim(
            story_id=story_id,
            allocated_port=colliding_port,
            evidence_subpath=f"qa-evidence/{story_id}/run-1/",
            aggregate_claim_story_id=story_id,
        )

    result = parallel_dispatch.dispatch_stories_parallel(
        "epic-18",
        run_id="run-1",
        story_ids=story_ids,
        max_parallel_stories=2,
        runner=_clean_runner,
        epic_state=_epic_state(story_ids),
        epic_run_state_path=tmp_path / "e.yaml",
        transient_marker_classes=frozenset(),
        base_ref="main",
        trunk_allowlist=(),
        claim_provider=_colliding_provider,
    )
    assert result.final_state.current_state == "epic-paused-on-escalation"
    assert any(
        m.startswith(PARALLEL_STORY_STATE_POLLUTION_MARKER)
        for m in result.final_state.active_markers
    )


# --------------------------------------------------------------------------- #
# AC-5 orphan-sweep independence — B→A symmetry                              #
# --------------------------------------------------------------------------- #


def test_per_story_orphan_cleanup_is_symmetric_b_sweep_leaves_a_intact(
    tmp_path: pathlib.Path,
) -> None:
    """B's sweep clears only B's stale env, leaving A's run-state fully intact
    — the converse of test_per_story_orphan_cleanup_emits_marker_per_orphan_scoped_to_story
    (which proves A's sweep leaves B intact). Together they prove full symmetry (AC-5)."""
    rs_a = tmp_path / "a" / "run-state.yaml"
    rs_b = tmp_path / "b" / "run-state.yaml"
    _seed_run_state(rs_a, "18-3-a")
    _seed_run_state(rs_b, "18-3-b")
    for path, port, pid in ((rs_a, 5101, 4101), (rs_b, 5202, 4202)):
        d = _read(path)
        d["provisioned_env"] = {
            "env_kind": "web",
            "port": port,
            "pid": pid,
            "started_at": "2026-06-05T10:00:00+00:00",
        }
        path.write_text(yaml.safe_dump(d, sort_keys=False), encoding="utf-8")

    registry = _orphan_registry()
    cleanup_orphan_processes(
        rs_b,
        _StaticOrphanProbe(((5202, 4202),)),  # type: ignore[arg-type]
        _RecordingOrphanTerminator(),  # type: ignore[arg-type]
        registry,
        lambda _e: None,
        story_id="18-3-b",
        env_kind="web",
    )
    assert "provisioned_env" not in _read(rs_b)
    assert _read(rs_a)["provisioned_env"]["pid"] == 4101
