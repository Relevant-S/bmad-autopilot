"""Epic-18 parallel-mode reference-run fixture — the parallel-story-execution
cohort driven end-to-end through ``run_epic_loop(parallel_stories=True)``
(Story 18.4).

This module is the Epic-18 analog of Story 15.5's
``test_epic_15_reference_run_fixture.py``, taken one wrinkle further: where 15.5
drove the SEQUENTIAL epic loop, this fixture drives the PARALLEL phase-3
dispatch (``parallel_dispatch.dispatch_stories_parallel`` via
``run_epic_loop``'s ``parallel_stories`` branch) across a synthetic 2-story epic
and witnesses that Stories 18.1–18.3 interoperate at the seams UNDER
CONCURRENCY. It is the EMPIRICAL, CI-witnessed proof that the parallel-story
substrate composes end-to-end BEFORE the 19∥20∥21 cluster (and Epic 23's
``phase-2-completion-evidence.md``) build on top.

It adds NO production ``src/loud_fail_harness/*.py`` module and modifies none —
the substrate-component count stays FIVE per ADR-003 Consequence 1. The fixture
is a pure CONSUMER of the landed runtime; the only new code is this ``tests/``
module (the ``docs/reference-runs/18-4-parallel-web/`` capture is derived from a
clean-run pass of the SAME substrate with a fixed ``generated_at``).

## Determinism under concurrency — the injected runner + the barrier rendezvous

15.5 drove a sequential loop, so determinism was free. 18.4's wrinkle is that
``dispatch_stories_parallel`` runs on a bounded ``ThreadPoolExecutor``. Two
design points keep the witness deterministic AND a genuine concurrency proof
(Story 18.4 Dev Notes § Determinism under concurrency):

1. **The concurrency-overlap proof is a ``threading.Barrier(2)`` inside the
   injected ``parallel_story_loop_runner``.** With ``max_parallel_stories=2``
   and exactly two ``ready-for-dev`` stories, both are admitted in one wave;
   each runner body records its entry, then rendezvous at the barrier. The
   barrier RELEASING is positive proof BOTH bodies executed simultaneously (a
   sequential dispatcher would block forever at the barrier).
2. **The barrier is loud-fail bounded.** ``wait(timeout=_BARRIER_TIMEOUT)``
   raises ``BrokenBarrierError`` (and breaks the barrier) on timeout, so a
   regression to sequential dispatch surfaces as a fast, hard test FAILURE —
   never a CI hang. ``_BARRIER_TIMEOUT`` is a few seconds (5.0); never an
   unbounded ``Barrier.wait()`` (loud-fail doctrine applied to the test
   harness). [Source: docs.python.org/3/library/threading.html#barrier-objects,
   confirmed via web research 2026-06-09.]
3. **Completion order is non-deterministic; assert order-insensitively.**
   ``dispatched_story_ids`` may arrive in either completion order — asserted as
   a ``set``. The cost-partition sums and the terminal state ARE deterministic
   (the folds are commutative + single-writer on the main thread per 18.1).

The chosen witness path is the PREFERRED real-worktree-under-concurrency one
(the Story 14.6 / 15.5 real-artifacts-over-mocks discipline): BOTH stories drive
the real per-story worktree lifecycle the dispatcher owns
(``create_worktree`` → per-worktree ``RunState`` write → ``cleanup_worktree``),
genuinely exercised concurrently. The 15.5 AC-2b fallback (one real + pure-stub
siblings) was NOT needed — concurrent ``git worktree add``/``remove`` against
distinct branches/paths is reliable (empirically 0/40 stress-trial failures
locally; see Completion Notes).

The synthetic epic uses the id ``epic-918`` (NOT the real ``epic-18``) with
stories ``918-1-alpha`` / ``918-2-bravo`` — ``enumerate_epic_stories`` requires
an ``epic-<digits>`` id (``_parse_epic_number``), so the id is numeric and
clearly synthetic, with no collision with the live ``epic-18`` planning slice
(mirroring 15.5's ``epic-915`` decision). The negative witness uses distinct ids
``918-3-charlie`` / ``918-4-delta`` so it never reuses a clean-run worktree path.

## The clean-run no-pollution witness is NON-vacuous (AC-4)

A naive "clean run → no marker" assertion passes equally whether or not the
detector is wired (Story 18.3's review flagged exactly this trap). This fixture
avoids it by construction: the clean run drives the REAL
``run_epic_loop`` parallel branch, which (Story 18.3) constructs the production
``env_provisioning.ParallelEnvClaimProvider`` and passes it as
``claim_provider=`` — so the live ``detect_state_pollution`` IS running, and the
clean run is silent ONLY because the provider's disjointness keeps it silent.
The SEPARATE negative witness drives ``dispatch_stories_parallel`` directly with
a deliberately-colliding provider (two stories handed the same
``allocated_port``) and proves the marker fires. The two together are the
prevention (18.3) ⟷ detection (18.2) composition end-to-end.

Contract-coverage matrix (AC-1 contract; AC-2…AC-5 are CI-witnessed below; AC-6
and AC-9 are review-verified committed artifacts; AC-7 zero-mod / AC-8 CI-green
are gate-verified):

    [x] AC-1 every runtime artifact under tmp_path; zero writes outside sandbox;
        zero production src additions (the no-substrate witness)
        → test_ref_run_lands_under_tmp_path
        → test_no_per_worktree_cost_substrate
    [x] AC-2 clean → epic-complete (set-wise dispatch, no pause, no raise);
        worktree post-condition (zero orphans, no stale-lock persisted);
        ≥2 stories drive the real per-worktree lifecycle (schema-valid writes)
        → test_ref_run_reaches_epic_complete_deterministically
        → test_ref_run_worktree_post_condition_zero_orphans_no_stale_lock
    [x] AC-3 both stories in-flight simultaneously for ≥1 observable interval
        (barrier rendezvous released; peak observed concurrency == 2)
        → test_ref_run_concurrency_overlap_witness
    [x] AC-4 clean-run positive: NO parallel-story-state-pollution marker (the
        live disjoint provider keeps the detector silent); separate negative
        witness: colliding provider trips shared-port-collision + pause + drain
        → test_ref_run_clean_run_emits_no_pollution_marker
        → test_negative_witness_colliding_provider_trips_detector
    [x] AC-5 per-story (= per-worktree) + per-epic cost partition in the bundle;
        epic_cost_total == sum(per_story_cost); byte-stable; path contract;
        no per-specialist re-render at epic scope
        → test_ref_run_cost_partition_per_story_and_epic_total
    [x] AC-6 docs/reference-runs/18-4-parallel-web/ committed (README + narrative
        + verbatim pr-bundle-epic-close.md + epic-run-state.yaml);
        reference-projects.md web-row migrated in-place — review-verified
    [x] AC-9 extension-audit.md row + contract-pair commit split — review-verified

Forward pointers: Story 23.2 (``phase-2-completion-evidence.md``) consumes the
``docs/reference-runs/18-4-parallel-web/`` row this fixture's clean run produced.
The per-epic NFR-P3 latency budget is an Epic 22 H3 deliverable the stand-in run
cannot validate empirically (see ``narrative.md`` § NFR-P3; the existing
``deferred-work.md`` per-epic H3 entry from Story 15.5 already covers the
epic-scope injected-runner latency gap — 18.4 adds only a parallel-mode caveat
to the narrative, not a new deferred-work blocker).
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
import threading
from dataclasses import dataclass
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

import loud_fail_harness
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.branch_lifecycle import DEFAULT_TRUNK_ALLOWLIST
from loud_fail_harness.bundle_assembly_epic import (
    assemble_epic_bundle,
    compute_epic_bundle_path,
)
from loud_fail_harness.epic_lifecycle import (
    RunEpicLoopResult,
    StoryLoopOutcome,
    init_epic_run_state,
    run_epic_loop,
)
from loud_fail_harness.epic_run_state import (
    EpicRunState,
    load_epic_run_state,
    worktree_run_state_path,
)
from loud_fail_harness.parallel_dispatch import dispatch_stories_parallel
from loud_fail_harness.parallel_pollution import (
    PARALLEL_STORY_STATE_POLLUTION_MARKER,
    StoryClaim,
)
from loud_fail_harness.run_state import RunState
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)
from loud_fail_harness.worktree_lifecycle import list_active_worktrees

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

#: Synthetic, clearly-non-real epic id. ``enumerate_epic_stories`` requires an
#: ``epic-<digits>`` id, so the parallel run uses the numeric ``epic-918`` — no
#: collision with the live ``epic-18`` slice (mirrors 15.5's ``epic-915``).
_EPIC_ID = "epic-918"
_STORY_1 = "918-1-alpha"
_STORY_2 = "918-2-bravo"
_STORY_IDS = (_STORY_1, _STORY_2)
_RUN_ID = "run-epic-918-ref-001"

#: The negative witness uses DISTINCT story ids so it never reuses a clean-run
#: worktree path within the shared tmp_path repo.
_NEG_STORY_1 = "918-3-charlie"
_NEG_STORY_2 = "918-4-delta"
_NEG_STORY_IDS = (_NEG_STORY_1, _NEG_STORY_2)
_NEG_RUN_ID = "run-epic-918-neg-001"
#: A single port handed to BOTH negative-witness stories → shared-port-collision.
_COLLIDING_PORT = 9999

#: Non-zero, distinct canned per-story costs → the cost partition is a POSITIVE
#: witness (no degenerate all-zero table; no spurious lower-bound caveat).
_CLEAN_COSTS = {_STORY_1: 1.50, _STORY_2: 2.25}
#: Zero retries → the per-epic budget never exhausts; the clean run reaches
#: ``epic-complete`` (the budget-exhaustion variant is Story 15.5 / 18.x scope).
_CLEAN_RETRIES = {_STORY_1: 0, _STORY_2: 0}
_CLEAN_COST_TOTAL = sum(_CLEAN_COSTS.values())

#: Loud-fail bound on the concurrency rendezvous: a regression to sequential
#: dispatch surfaces as a fast BrokenBarrierError, NEVER a CI hang.
_BARRIER_TIMEOUT = 5.0

#: Fixed UTC timestamp → assemble_epic_bundle output is byte-stable (AC-5).
_FIXED = dt.datetime(2026, 6, 9, 12, 0, 0, tzinfo=dt.timezone.utc)

#: A real BMAD project gitignores ephemeral run-state + the worktrees tree, which
#: keeps each worktree's working tree CLEAN of untracked-non-ignored files so
#: cleanup_worktree's ``git worktree remove`` (no --force) removes each worktree
#: cleanly even though the runner writes a per-worktree run-state INSIDE it.
_GITIGNORE_BODY = "_bmad/\nrun-state.yaml\n*.lock\n"


def _branch_for(story_id: str) -> str:
    return f"bmad-automation/story/{story_id}"


# --------------------------------------------------------------------------- #
# Git + schema helpers (mirror test_epic_15_reference_run_fixture.py)          #
# --------------------------------------------------------------------------- #


def _run_git(*args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


def _init_git_repo(path: pathlib.Path) -> pathlib.Path:
    _run_git("init", "-b", "main", cwd=path)
    _run_git("config", "user.email", "test@bmad-automation.local", cwd=path)
    _run_git("config", "user.name", "BMAD Test", cwd=path)
    _run_git("config", "commit.gpgsign", "false", cwd=path)
    (path / "README.md").write_text("# initial commit\n", encoding="utf-8")
    (path / ".gitignore").write_text(_GITIGNORE_BODY, encoding="utf-8")
    _run_git("add", "README.md", ".gitignore", cwd=path)
    _run_git("commit", "-m", "initial", cwd=path)
    return path


@pytest.fixture(scope="function")
def git_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    return _init_git_repo(tmp_path)


def _load_schema(name: str) -> dict[str, Any]:
    return yaml.safe_load(
        (find_repo_root() / "schemas" / name).read_text(encoding="utf-8")
    )


def _run_state_validator() -> Draft202012Validator:
    """Validator over the UNCHANGED ``schemas/run-state.yaml`` with the cell-1
    ``$ref`` registry populated (mirror of test_epic_15_reference_run_fixture)."""
    registry = Registry().with_resources(
        [
            (
                "envelope.schema.yaml",
                Resource(
                    contents=_load_schema("envelope.schema.yaml"),
                    specification=DRAFT202012,
                ),
            ),
            (
                "tea-handoff-contract.yaml",
                Resource(
                    contents=_load_schema("tea-handoff-contract.yaml"),
                    specification=DRAFT202012,
                ),
            ),
        ]
    )
    return Draft202012Validator(_load_schema("run-state.yaml"), registry=registry)


def _make_worktree_run_state(story_id: str, branch_name: str) -> RunState:
    """A clean per-story RunState (the EXISTING shape; Story 14.4 — per-worktree
    run-state is the existing RunState at a worktree-scoped path, no new model)."""
    return RunState.model_validate(
        {
            "schema_version": "1.3",
            "story_id": story_id,
            "run_id": _RUN_ID,
            "current_state": "in-progress",
            "branch_name": branch_name,
            "dispatched_specialist": None,
            "last_envelope": None,
            "pending_qa_dispatch_payload": None,
            "retry_history": (),
            "active_markers": (),
            "cost_to_date_by_specialist": {},
        }
    )


def _write_run_state_yaml(path: pathlib.Path, run_state: RunState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(run_state.model_dump_json())
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_sprint_status(
    repo_root: pathlib.Path, story_ids: tuple[str, ...]
) -> pathlib.Path:
    """Author the synthetic sprint-status slice under tmp_path: the non-real
    ``epic-918`` with exactly ``max_parallel_stories`` ready-for-dev stories so
    both are admitted in a single wave and genuinely run concurrently (AC-1)."""
    path = repo_root / "_bmad" / "automation" / "sprint-status.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    development_status = {story_id: "ready-for-dev" for story_id in story_ids}
    path.write_text(
        yaml.safe_dump({"development_status": development_status}, sort_keys=False),
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------- #
# Concurrency probe — the loud-fail-bounded rendezvous (AC-3)                  #
# --------------------------------------------------------------------------- #


class _ConcurrencyProbe:
    """Thread-safe observer of the parallel runner bodies. ``barrier`` is the
    rendezvous whose RELEASE proves both bodies executed simultaneously;
    ``peak_in_flight`` is the explicit overlap assertion AC-3 demands (not merely
    a non-hang). The barrier carries a finite timeout (loud-fail bound)."""

    def __init__(self, parties: int) -> None:
        self._lock = threading.Lock()
        self.barrier = threading.Barrier(parties)
        self.entered: list[str] = []
        self.released: list[str] = []
        self.in_flight = 0
        self.peak_in_flight = 0
        self.run_state_errors: dict[str, list[Any]] = {}

    def enter(self, story_id: str) -> None:
        with self._lock:
            self.entered.append(story_id)
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)

    def released_after_barrier(self, story_id: str) -> None:
        with self._lock:
            self.released.append(story_id)

    def record_errors(self, story_id: str, errors: list[Any]) -> None:
        with self._lock:
            self.run_state_errors[story_id] = errors

    def exit(self, story_id: str) -> None:
        with self._lock:
            self.in_flight -= 1


# --------------------------------------------------------------------------- #
# Runners                                                                       #
# --------------------------------------------------------------------------- #


def _fail_if_sequential_dispatched(
    *, story_id: str, index: int, total: int
) -> StoryLoopOutcome:
    """The ``story_loop_runner`` is required by ``run_epic_loop`` but MUST NOT be
    invoked on the parallel path. Raising here is a loud-fail witness that the
    parallel branch (and ``dispatch_stories_parallel``) was genuinely taken."""
    raise AssertionError(
        "sequential story_loop_runner was invoked on the parallel path; "
        "run_epic_loop should have delegated to dispatch_stories_parallel"
    )


def _make_clean_runner(probe: _ConcurrencyProbe):
    def runner(
        *,
        story_id: str,
        index: int,
        total: int,
        worktree_path: pathlib.Path,
        run_state_path: pathlib.Path,
    ) -> StoryLoopOutcome:
        probe.enter(story_id)
        try:
            # The rendezvous: a sequential dispatcher would block forever here;
            # a concurrent one releases both bodies (loud-fail bounded timeout).
            probe.barrier.wait(timeout=_BARRIER_TIMEOUT)
            probe.released_after_barrier(story_id)
            run_state = _make_worktree_run_state(story_id, _branch_for(story_id))
            _write_run_state_yaml(run_state_path, run_state)
            errors = list(
                _run_state_validator().iter_errors(
                    yaml.safe_load(run_state_path.read_text(encoding="utf-8"))
                )
            )
            probe.record_errors(story_id, errors)
        finally:
            probe.exit(story_id)
        return StoryLoopOutcome(
            terminal_status="merge-ready",
            retries_consumed=_CLEAN_RETRIES[story_id],
            cost=_CLEAN_COSTS[story_id],
        )

    return runner


def _negative_runner(
    *,
    story_id: str,
    index: int,
    total: int,
    worktree_path: pathlib.Path,
    run_state_path: pathlib.Path,
) -> StoryLoopOutcome:
    """The admitted negative-witness story drains to merge-ready without a
    rendezvous (only ONE story is admitted before the colliding claim pauses
    admission — a Barrier(2) would deadlock)."""
    return StoryLoopOutcome(
        terminal_status="merge-ready", retries_consumed=0, cost=0.50
    )


# --------------------------------------------------------------------------- #
# Carriers                                                                      #
# --------------------------------------------------------------------------- #


@dataclass
class _CleanRunArtifacts:
    result: RunEpicLoopResult
    close_state: EpicRunState
    close_bundle_text: str
    close_bundle_text_2nd: str
    bundle_path: pathlib.Path
    computed_bundle_path: pathlib.Path
    run_state_errors: dict[str, list[Any]]
    final_active_worktree_story_ids: tuple[str, ...]
    peak_in_flight: int
    released: tuple[str, ...]
    entered: tuple[str, ...]
    sandbox_paths: tuple[pathlib.Path, ...]


def _drive_clean_run(
    repo_root: pathlib.Path, marker_registry: MarkerClassRegistry
) -> _CleanRunArtifacts:
    """Drive the clean parallel epic run to ``epic-complete`` through the REAL
    ``run_epic_loop`` parallel branch (which constructs the production
    ParallelEnvClaimProvider + DisjointPortAllocator and the live pollution
    detector), with both stories exercising the real per-worktree lifecycle
    under a barrier rendezvous, then assemble the epic PR bundle."""
    sprint_status_path = _write_sprint_status(repo_root, _STORY_IDS)
    automation = repo_root / "_bmad" / "automation"
    epic_run_state_path = automation / "epic-run-state.yaml"
    worktrees_root = automation / "worktrees"
    probe = _ConcurrencyProbe(len(_STORY_IDS))

    result = run_epic_loop(
        _EPIC_ID,
        run_id=_RUN_ID,
        sprint_status_path=sprint_status_path,
        epic_run_state_path=epic_run_state_path,
        story_loop_runner=_fail_if_sequential_dispatched,
        parallel_stories=True,
        max_parallel_stories=2,
        parallel_story_loop_runner=_make_clean_runner(probe),
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=repo_root,
    )

    final_worktrees = list_active_worktrees(repo_root=repo_root)
    final_active_worktree_story_ids = tuple(
        wt.story_id for wt in final_worktrees if wt.story_id in _STORY_IDS
    )

    close_state = load_epic_run_state(epic_run_state_path)

    bundle_root = repo_root / "_bmad-output" / "epic-pr-bundles"
    assembled = assemble_epic_bundle(
        _EPIC_ID,
        _RUN_ID,
        epic_run_state_path,
        bundle_root,
        marker_registry=marker_registry,
        generated_at=_FIXED,
    )
    close_bundle_text = assembled.bundle_path.read_text(encoding="utf-8")
    # Idempotent regeneration from the unchanged cache → byte-stable (AC-5).
    assembled_2nd = assemble_epic_bundle(
        _EPIC_ID,
        _RUN_ID,
        epic_run_state_path,
        bundle_root,
        marker_registry=marker_registry,
        generated_at=_FIXED,
    )
    close_bundle_text_2nd = assembled_2nd.bundle_path.read_text(encoding="utf-8")
    computed_bundle_path = compute_epic_bundle_path(
        repo_root=repo_root, epic_id=_EPIC_ID, run_id=_RUN_ID
    )

    per_worktree_rs_paths = tuple(
        worktree_run_state_path(
            sid, worktrees_root=worktrees_root, repo_root=repo_root
        )
        for sid in _STORY_IDS
    )
    sandbox_paths = (
        sprint_status_path,
        epic_run_state_path,
        worktrees_root,
        assembled.bundle_path,
        *per_worktree_rs_paths,
    )

    return _CleanRunArtifacts(
        result=result,
        close_state=close_state,
        close_bundle_text=close_bundle_text,
        close_bundle_text_2nd=close_bundle_text_2nd,
        bundle_path=assembled.bundle_path,
        computed_bundle_path=computed_bundle_path,
        run_state_errors=probe.run_state_errors,
        final_active_worktree_story_ids=final_active_worktree_story_ids,
        peak_in_flight=probe.peak_in_flight,
        released=tuple(probe.released),
        entered=tuple(probe.entered),
        sandbox_paths=sandbox_paths,
    )


@dataclass
class _NegativeWitness:
    result: RunEpicLoopResult
    final_active_worktree_story_ids: tuple[str, ...]


def _drive_negative_witness(repo_root: pathlib.Path) -> _NegativeWitness:
    """Drive ``dispatch_stories_parallel`` directly with a deliberately-colliding
    provider (two stories handed the SAME ``allocated_port``), reusing the landed
    18.2 detector + 18.3 seam — it INJECTS a colliding provider, it does NOT
    re-implement detection. Proves the marker fires + the epic pauses + in-flight
    units drain (sensor-not-advisor — no auto-resolution)."""
    automation = repo_root / "_bmad" / "automation"
    automation.mkdir(parents=True, exist_ok=True)
    epic_run_state_path = automation / "epic-run-state-negative.yaml"
    worktrees_root = automation / "worktrees"
    epic_state = init_epic_run_state(
        _EPIC_ID, _NEG_RUN_ID, _NEG_STORY_IDS, multiplier=2
    )

    def colliding_provider(*, story_id: str) -> StoryClaim:
        return StoryClaim(
            story_id=story_id,
            allocated_port=_COLLIDING_PORT,
            evidence_subpath=f"qa-evidence/{story_id}/{_NEG_RUN_ID}/",
            aggregate_claim_story_id=story_id,
        )

    result = dispatch_stories_parallel(
        _EPIC_ID,
        run_id=_NEG_RUN_ID,
        story_ids=_NEG_STORY_IDS,
        max_parallel_stories=2,
        runner=_negative_runner,
        epic_state=epic_state,
        epic_run_state_path=epic_run_state_path,
        transient_marker_classes=frozenset(),
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=repo_root,
        claim_provider=colliding_provider,
    )

    final_worktrees = list_active_worktrees(repo_root=repo_root)
    final_active_worktree_story_ids = tuple(
        wt.story_id for wt in final_worktrees if wt.story_id in _NEG_STORY_IDS
    )
    return _NegativeWitness(
        result=result,
        final_active_worktree_story_ids=final_active_worktree_story_ids,
    )


@dataclass
class _RefRunResult:
    clean: _CleanRunArtifacts
    negative: _NegativeWitness


# --------------------------------------------------------------------------- #
# Fixtures                                                                      #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="function")
def marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


@pytest.fixture(scope="function")
def ref_run(
    git_repo: pathlib.Path, marker_registry: MarkerClassRegistry
) -> _RefRunResult:
    clean = _drive_clean_run(git_repo, marker_registry)
    negative = _drive_negative_witness(git_repo)
    return _RefRunResult(clean=clean, negative=negative)


# --------------------------------------------------------------------------- #
# Witnesses                                                                     #
# --------------------------------------------------------------------------- #


def test_ref_run_lands_under_tmp_path(
    ref_run: _RefRunResult, tmp_path: pathlib.Path
) -> None:
    """AC-1 — every runtime artifact (sprint-status slice, epic-run-state, the
    per-worktree run-states, worktrees root, assembled bundle) lands under
    tmp_path; the fixture makes zero writes outside the sandbox."""
    for path in ref_run.clean.sandbox_paths:
        assert path.is_relative_to(tmp_path), f"{path} escaped the tmp_path sandbox"
    assert ref_run.clean.result.wrote_path.is_relative_to(tmp_path)
    assert ref_run.clean.bundle_path.is_relative_to(tmp_path)
    assert ref_run.negative.result.wrote_path.is_relative_to(tmp_path)


def test_ref_run_reaches_epic_complete_deterministically(
    ref_run: _RefRunResult,
) -> None:
    """AC-2 — the clean parallel run reaches epic-complete with both synthetic
    stories dispatched (order-insensitive — parallel completion order is
    non-deterministic), no pausing story, and the loop never raised (reaching
    this assertion proves it)."""
    clean = ref_run.clean.result
    assert clean.final_state.current_state == "epic-complete"
    assert set(clean.dispatched_story_ids) == set(_STORY_IDS)
    assert clean.paused_on_story_id is None
    # Both stories drove the real per-worktree lifecycle with a schema-valid
    # per-worktree RunState write (against the byte-unchanged run-state.yaml).
    assert set(ref_run.clean.run_state_errors) == set(_STORY_IDS)
    for story_id, errors in ref_run.clean.run_state_errors.items():
        assert errors == [], f"{story_id} per-worktree run-state failed schema"


def test_ref_run_worktree_post_condition_zero_orphans_no_stale_lock(
    ref_run: _RefRunResult,
) -> None:
    """AC-2 worktree post-condition — zero synthetic-story worktrees remain after
    the clean run (both cleanup_worktree(preserve_on_escalation=False) calls
    removed them — merge-ready policy), and the persisted final state carries NO
    worktree-stale-lock (the transient marker is re-derived/filtered, never
    persisted — the Story 15.1 model; this is the runtime marker exercise the
    deferred-work.md blocker named, now a pure witness)."""
    assert ref_run.clean.final_active_worktree_story_ids == ()
    assert (
        "worktree-stale-lock"
        not in ref_run.clean.result.final_state.active_markers
    )


def test_ref_run_concurrency_overlap_witness(ref_run: _RefRunResult) -> None:
    """AC-3 — both stories were proven in-flight simultaneously for at least one
    observable interval: the Barrier(2) rendezvous RELEASED (both runner bodies
    reached it — a sequential dispatcher would have raised BrokenBarrierError on
    timeout), and the thread-safe peak observed-concurrency counter reached 2 (an
    explicit assertion, not merely a non-hang)."""
    clean = ref_run.clean
    assert clean.peak_in_flight == 2
    assert set(clean.released) == set(_STORY_IDS)
    assert set(clean.entered) == set(_STORY_IDS)


def test_ref_run_clean_run_emits_no_pollution_marker(
    ref_run: _RefRunResult,
) -> None:
    """AC-4 positive (clean) witness — the clean run's final state contains NO
    parallel-story-state-pollution marker (any sub-classification) and no
    pollution marker_context. NON-vacuous: the clean run drove the REAL
    run_epic_loop parallel branch, which constructs the production
    ParallelEnvClaimProvider and passes it as claim_provider (Story 18.3), so the
    detector is LIVE — silent ONLY because the provider hands disjoint claims."""
    final_state = ref_run.clean.result.final_state
    assert not any(
        marker.startswith(PARALLEL_STORY_STATE_POLLUTION_MARKER)
        for marker in final_state.active_markers
    )
    assert PARALLEL_STORY_STATE_POLLUTION_MARKER not in final_state.marker_contexts


def test_negative_witness_colliding_provider_trips_detector(
    ref_run: _RefRunResult,
) -> None:
    """AC-4 negative witness — driving dispatch_stories_parallel directly with a
    colliding provider (two stories → same allocated_port) trips Story 18.2's
    detector: the durable ``parallel-story-state-pollution: shared-port-collision``
    marker is appended, the epic pauses on epic-paused-on-escalation, the conflict
    context (story_id / conflicting_story_id / shared_surface) is carried in
    marker_contexts, and the admitted in-flight unit drains without interruption
    (sensor-not-advisor — no auto-resolution, zero orphan worktrees)."""
    neg = ref_run.negative.result
    assert neg.final_state.current_state == "epic-paused-on-escalation"
    expected_marker = f"{PARALLEL_STORY_STATE_POLLUTION_MARKER}: shared-port-collision"
    assert expected_marker in neg.final_state.active_markers

    context = neg.final_state.marker_contexts[PARALLEL_STORY_STATE_POLLUTION_MARKER]
    assert set(context) == {"story_id", "conflicting_story_id", "shared_surface"}
    assert context["shared_surface"] == "shared-port"
    assert {context["story_id"], context["conflicting_story_id"]} <= set(
        _NEG_STORY_IDS
    )

    # In-flight drain (no interruption): the admitted story completed merge-ready
    # and its worktree was cleaned up — no orphan left behind by the pause.
    assert len(neg.dispatched_story_ids) >= 1
    for story_id in neg.dispatched_story_ids:
        assert neg.final_state.per_story_status[story_id] == "merge-ready"
    assert ref_run.negative.final_active_worktree_story_ids == ()


def test_ref_run_cost_partition_per_story_and_epic_total(
    ref_run: _RefRunResult,
) -> None:
    """AC-5 — the assembled epic PR bundle carries the per-story (= per-worktree,
    under parallel mode) cost partition + the per-epic total: one row per story +
    an Epic total; epic_cost_total == sum(per_story_cost) (fold_story_cost threaded
    end-to-end through the PARALLEL dispatch); positive costs (not a degenerate
    all-zero table); byte-stable on identical input (NFR-R1 idempotence); the
    deterministic path contract holds; and the per-specialist NFR-P5 breakdown is
    NOT re-rendered at epic scope (Story 15.3 pointer-not-projection / NFR-R8)."""
    partition = ref_run.clean.close_state.per_epic_cost_partition
    assert set(partition.per_story_cost) == set(_STORY_IDS)
    assert partition.epic_cost_total == sum(partition.per_story_cost.values())
    assert partition.epic_cost_total == _CLEAN_COST_TOTAL
    assert all(cost > 0 for cost in partition.per_story_cost.values())

    bundle = ref_run.clean.close_bundle_text
    assert "## 💸 Epic Cost Partition" in bundle
    assert bundle.count("## 💸 Epic Cost Partition") == 1
    for story_id in _STORY_IDS:
        assert f"| {story_id} | {_CLEAN_COSTS[story_id]:.2f} |" in bundle
    assert f"| Epic total | {_CLEAN_COST_TOTAL:.2f} |" in bundle
    assert "LOWER BOUND" not in bundle

    # Byte-stable regeneration + deterministic path contract.
    assert ref_run.clean.close_bundle_text == ref_run.clean.close_bundle_text_2nd
    assert ref_run.clean.bundle_path == ref_run.clean.computed_bundle_path

    # Per-story (= per-worktree) totals only at epic scope — the per-specialist
    # breakdown stays canonical in each story's own per-worktree run-state.
    assert "cost_to_date_by_specialist" not in bundle
    assert "per-specialist" not in bundle


def test_no_per_worktree_cost_substrate() -> None:
    """AC-5 / AC-7 — there is NO separate PerWorktreeCostPartition substrate:
    under parallel mode each story runs in exactly one worktree, so the per-story
    cost rows ARE the per-worktree partition. Witness + document; never invent.
    Scans the harness ``src/loud_fail_harness`` tree for the forbidden tokens."""
    src_dir = pathlib.Path(loud_fail_harness.__file__).parent
    for py_file in src_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        assert "PerWorktree" not in text, f"{py_file} introduced PerWorktree"
        assert "per_worktree_cost" not in text, (
            f"{py_file} introduced per_worktree_cost"
        )
