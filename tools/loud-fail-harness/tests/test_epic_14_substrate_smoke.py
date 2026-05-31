"""Epic-14 substrate smoke — the worktree-isolation cohort composed end-to-end
(Story 14.6).

This module is the FIRST integration-test consumer that exercises all four
Epic-14 runtime substrate surfaces simultaneously against ONE real throwaway
git repo under ``tmp_path``:

    * ``worktree_lifecycle`` — create / cleanup / inspect / list (Story 14.2)
    * ``story_file_lock`` — acquire / release + the stale-lock primitive (14.3)
    * ``session_start_reattach`` — ``evaluate_reattach`` fifth branch
      (``worktree-stale-lock-detected``) + recovery (Story 14.3)
    * ``epic_run_state`` — ``EpicRunState`` aggregate + ``worktree_run_state_path``
      per-worktree addressing (Story 14.4)

It is the Epic-14 analog of Story 2.13's ``test_walking_skeleton_smoke.py`` (the
first integration consumer of the Epic-2 substrate cohort): structurally a
run-once ``smoke`` fixture that drives the full composed lifecycle, with one
assertion-bearing test per contract row. It is the EMPIRICAL, CI-witnessed proof
that the Epic-14 substrate composes at the seams BEFORE Epic 15 (sequential
epic orchestration) and Epic 18 (parallel dispatch) build runtime flow on top.

It adds NO production ``src/loud_fail_harness/*.py`` module and modifies none —
the substrate-component count stays FIVE per ADR-003 Consequence 1. The whole
witness is real artifacts (real ``git worktree add``/``remove``/``prune``, real
on-disk lock files, real run-state files); the only seam is the deterministic
dead-PID + back-dated stale lock (no ``story_file_lock_probe`` DI injection —
the real ``_probe_story_file_lock`` path runs end-to-end).

Contract-coverage matrix (AC-1; reviewers verify every AC-3…AC-6 row maps to a
passing function here):

    [x] AC-1 every artifact under tmp_path; zero writes outside the sandbox
        → test_smoke_lands_as_epic_14_witness_under_tmp_path
    [x] AC-2 two worktrees + per-worktree run-state (14.4 addressing) + clean
        lock acquisition
        → test_smoke_creates_two_worktrees_with_per_worktree_run_state_and_locks
    [x] AC-3 crash → worktree-stale-lock emitted, cleared on recovery
        (NFR-R2); story-A clean negative control
        → test_smoke_crash_emits_worktree_stale_lock_then_clears_on_recovery
    [x] AC-4 clean cleanup of A + crashed-then-pruned cleanup of B; zero
        orphan worktrees (NFR-R3 — prune, never --force)
        → test_smoke_clean_and_crashed_then_pruned_cleanup_zero_orphans
    [x] AC-5 epic-run-state schema-valid throughout + per-worktree run-state
        schema-valid throughout
        → test_smoke_epic_run_state_schema_valid_throughout
    [x] AC-6 Story 14.5 marker is taxonomy-coherent only (NOT runtime-exercised)
        → test_smoke_parallel_pollution_marker_enumerated_not_exercised
    [x] AC-10 the full composed lifecycle proves the four surfaces interoperate
        → test_smoke_composes_full_epic_14_lifecycle

Forward pointers (AC-6, AC-10): Story 14.5 pre-provisioned a parallel-mode
marker class with NO runtime emitter (flip-the-switch property). This smoke
does NOT emit or detect it — there is no detector to call and parallel dispatch
is Epic 18. The smoke asserts ONLY that the class is enumerated in
``schemas/marker-taxonomy.yaml`` (taxonomy-coherence witness that 14.5's
pre-provision is in place). The marker's runtime exercise is deferred to Epic
18's reference fixture (Story 18.4); sequential epic orchestration consuming this
substrate is Epic 15.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import pathlib
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from unittest import mock

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from loud_fail_harness import worktree_lifecycle
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.branch_lifecycle import DEFAULT_TRUNK_ALLOWLIST
from loud_fail_harness.epic_run_state import (
    EpicRunState,
    PerEpicCostPartition,
    PerEpicRetryBudget,
    worktree_run_state_path,
)
from loud_fail_harness.run_state import RunState
from loud_fail_harness.session_start_reattach import (
    WORKTREE_STALE_LOCK_MARKER_CLASS,
    ReattachOutcome,
    ReattachRequest,
    evaluate_reattach,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)
from loud_fail_harness.story_file_lock import (
    DEFAULT_STALE_THRESHOLD_SECONDS,
    LockAcquisitionResult,
    LockRecord,
    acquire_lock,
    inspect_lock,
    release_lock,
)
from loud_fail_harness.worktree_lifecycle import (
    WorktreeCleanupResult,
    WorktreeInspectionResult,
    WorktreeLifecycleResult,
    cleanup_worktree,
    create_worktree,
    inspect_worktree,
    list_active_worktrees,
)


# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #


# Two non-trunk story-ids of one BMAD epic. Their derived branches
# (`bmad-automation/story/14-A`, `bmad-automation/story/14-B`) are NOT in
# DEFAULT_TRUNK_ALLOWLIST, so create_worktree accepts them (AC-2).
_STORY_A = "14-A"
_STORY_B = "14-B"
_EPIC_ID = "epic-14"
_RUN_ID = "run-epic-14-smoke-001"

# Guaranteed-dead PID: os.kill(999999, 0) raises ProcessLookupError on the
# SessionStart default pid-probe, so the stale-lock verdict is deterministic
# (pid-not-alive) without depending on wall-clock skew. Back-dating started_at
# is belt-and-suspenders (age-exceeded would fire too).
_DEAD_PID = 999999

# A real BMAD project gitignores ephemeral run-state + locks + the worktrees
# tree (see the inner repo .gitignore: `_bmad/automation/worktrees/`). Mirroring
# that here keeps every worktree's working tree CLEAN of untracked-non-ignored
# files, so cleanup_worktree's `git worktree remove` (which has no --force path)
# can remove story A cleanly (AC-4) even though the smoke writes ephemeral
# run-state + lock files INSIDE each worktree.
_GITIGNORE_BODY = "_bmad/\nrun-state.yaml\n*.lock\n"


# --------------------------------------------------------------------------- #
# Git + schema helpers                                                         #
# --------------------------------------------------------------------------- #


def _run_git(*args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


@contextlib.contextmanager
def _capture_substrate_git_runs() -> Iterator[list[list[str]]]:
    """Record every argv the substrate passes to ``subprocess.run`` while the
    context is active, so NFR-R3's "no ``--force``" doctrine is witnessed over
    what ``cleanup_worktree`` ACTUALLY invokes — not a test-authored literal.

    The wrapper delegates to the real ``subprocess.run`` (observe-only) and is
    patched onto the ``worktree_lifecycle`` module attribute the substrate calls.
    """
    captured: list[list[str]] = []
    real_run = subprocess.run

    def _run(*args: Any, **kwargs: Any) -> Any:
        if args and isinstance(args[0], list):
            captured.append(list(args[0]))
        return real_run(*args, **kwargs)

    with mock.patch.object(worktree_lifecycle.subprocess, "run", side_effect=_run):
        yield captured


@pytest.fixture(scope="function")
def git_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A throwaway git repo at ``tmp_path`` (mirrors test_worktree_lifecycle.py's
    ``git_repo`` fixture) with an additional committed ``.gitignore`` so the
    ephemeral per-worktree artifacts the smoke writes do not block clean
    worktree removal (AC-4)."""
    _run_git("init", "-b", "main", cwd=tmp_path)
    _run_git("config", "user.email", "test@bmad-automation.local", cwd=tmp_path)
    _run_git("config", "user.name", "BMAD Test", cwd=tmp_path)
    _run_git("config", "commit.gpgsign", "false", cwd=tmp_path)
    (tmp_path / "README.md").write_text("# initial commit\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(_GITIGNORE_BODY, encoding="utf-8")
    _run_git("add", "README.md", ".gitignore", cwd=tmp_path)
    _run_git("commit", "-m", "initial", cwd=tmp_path)
    return tmp_path


def _make_worktrees_root(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "_bmad" / "automation" / "worktrees"


def _session_run_state_path(worktree_path: pathlib.Path) -> pathlib.Path:
    """The SessionStart project run-state path (8.1 / 14.3 addressing) that
    ``evaluate_reattach`` reads — distinct from the 14.4 per-worktree path."""
    return worktree_path / "_bmad" / "automation" / "run-state.yaml"


def _locks_root(worktree_path: pathlib.Path) -> pathlib.Path:
    """The locks directory ``_probe_story_file_lock`` resolves by default from
    its ``project_root`` argument."""
    return worktree_path / "_bmad" / "automation" / "locks"


def _load_schema(name: str) -> dict[str, Any]:
    return yaml.safe_load(
        (find_repo_root() / "schemas" / name).read_text(encoding="utf-8")
    )


def _run_state_validator() -> Draft202012Validator:
    """Validator over the UNCHANGED ``schemas/run-state.yaml`` with the cell-1
    ``$ref`` registry populated — mirrors test_epic_run_state.py's
    ``run_state_validator`` fixture (AC-5)."""
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


# --------------------------------------------------------------------------- #
# Substrate-shape builders                                                      #
# --------------------------------------------------------------------------- #


def _make_run_state(story_id: str, branch_name: str) -> RunState:
    """A clean per-story ``RunState`` (the existing shape; Story 14.4 KEY
    INSIGHT — per-worktree run-state is the EXISTING RunState at a worktree-
    scoped path, no new model). ``dispatched_specialist=None`` keeps
    ``evaluate_reattach`` off the can_dispatch path so the smoke isolates the
    stale-lock branch."""
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


def _stale_lock_record(story_id: str, worktree_path: pathlib.Path) -> LockRecord:
    """A real on-disk stale ``LockRecord`` — dead PID AND back-dated
    ``started_at`` — so the production ``_probe_story_file_lock`` path detects
    staleness deterministically (AC-3)."""
    backdated = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(
        seconds=DEFAULT_STALE_THRESHOLD_SECONDS + 3600
    )
    return LockRecord(
        schema_version="1.0",
        story_id=story_id,
        pid=_DEAD_PID,
        started_at=backdated,
        worktree_path=worktree_path,
        hostname="crashed-host",
    )


def _epic_run_state(
    current_state: str,
    per_story_status: dict[str, str],
    active_markers: tuple[str, ...],
    *,
    consumed: int,
) -> EpicRunState:
    return EpicRunState(
        schema_version="1.0",
        epic_id=_EPIC_ID,
        run_id=_RUN_ID,
        current_state=current_state,  # type: ignore[arg-type]
        story_ids=(_STORY_A, _STORY_B),
        per_story_status=per_story_status,  # type: ignore[arg-type]
        per_epic_retry_budget=PerEpicRetryBudget(
            multiplier=2, story_count=2, effective_budget=4, consumed=consumed
        ),
        per_epic_cost_partition=PerEpicCostPartition(
            per_story_cost={_STORY_A: 0.0, _STORY_B: 0.0}, epic_cost_total=0.0
        ),
        active_markers=active_markers,
    )


def _epic_validation_errors(epic_state: EpicRunState) -> list[Any]:
    schema = _load_schema("epic-run-state.yaml")
    payload = json.loads(epic_state.model_dump_json())
    return list(Draft202012Validator(schema).iter_errors(payload))


# --------------------------------------------------------------------------- #
# Smoke-run carrier                                                             #
# --------------------------------------------------------------------------- #


@dataclass
class _SmokeResult:
    """Carrier for the composed-lifecycle smoke's terminal artifacts
    (assertion-friendly; mirrors test_walking_skeleton_smoke.py's
    ``_SmokeRunResult``)."""

    repo_root: pathlib.Path
    worktrees_root: pathlib.Path

    create_a: WorktreeLifecycleResult
    create_b: WorktreeLifecycleResult
    acquire_a: LockAcquisitionResult
    acquire_b: LockAcquisitionResult

    # Existence observed mid-run (the smoke fixture drives the FULL lifecycle,
    # so the worktrees + per-worktree run-state files are gone by assert time).
    worktree_a_is_dir: bool
    worktree_b_is_dir: bool
    per_worktree_a_is_file: bool
    per_worktree_b_is_file: bool

    per_worktree_path_a: pathlib.Path
    per_worktree_path_b: pathlib.Path
    per_worktree_errors_a: list[Any]
    per_worktree_errors_b: list[Any]
    per_worktree_errors_a_pre_cleanup: list[Any]

    stale_outcome_b: ReattachOutcome
    stale_next_markers_b: tuple[str, ...]
    stale_lock_parsed_clean_b: bool
    stale_lock_pid_b: int | None
    clean_outcome_a: ReattachOutcome
    recovered_outcome_b: ReattachOutcome

    cleanup_a: WorktreeCleanupResult
    cleanup_b: WorktreeCleanupResult
    cleanup_a_invoked_remove: bool
    cleanup_a_used_force: bool
    invoked_remove_for_b: bool
    cleanup_b_used_force: bool
    inspect_b_after_crash: WorktreeInspectionResult | None
    final_worktrees: tuple[WorktreeInspectionResult, ...]

    epic_errors_before_crash: list[Any]
    epic_errors_after_crash: list[Any]
    epic_errors_after_recovery: list[Any]

    sandbox_paths: tuple[pathlib.Path, ...]


def _drive_smoke(
    repo_root: pathlib.Path, marker_registry: MarkerClassRegistry
) -> _SmokeResult:
    worktrees_root = _make_worktrees_root(repo_root)

    # AC-2 — create two per-story worktrees of one epic.
    create_a = create_worktree(
        _STORY_A,
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=repo_root,
    )
    create_b = create_worktree(
        _STORY_B,
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=repo_root,
    )
    wt_a = create_a.worktree_path
    wt_b = create_b.worktree_path

    run_state_a = _make_run_state(_STORY_A, create_a.branch_name)
    run_state_b = _make_run_state(_STORY_B, create_b.branch_name)

    # AC-2 / AC-5 — per-worktree run-state (14.4 addressing) + the SessionStart
    # project run-state (8.1/14.3 addressing); both validate against the
    # byte-unchanged run-state schema.
    per_worktree_path_a = worktree_run_state_path(
        _STORY_A, worktrees_root=worktrees_root, repo_root=repo_root
    )
    per_worktree_path_b = worktree_run_state_path(
        _STORY_B, worktrees_root=worktrees_root, repo_root=repo_root
    )
    _write_run_state_yaml(per_worktree_path_a, run_state_a)
    _write_run_state_yaml(per_worktree_path_b, run_state_b)
    _write_run_state_yaml(_session_run_state_path(wt_a), run_state_a)
    _write_run_state_yaml(_session_run_state_path(wt_b), run_state_b)

    worktree_a_is_dir = wt_a.is_dir()
    worktree_b_is_dir = wt_b.is_dir()
    per_worktree_a_is_file = per_worktree_path_a.is_file()
    per_worktree_b_is_file = per_worktree_path_b.is_file()

    validator = _run_state_validator()
    per_worktree_errors_a = list(
        validator.iter_errors(yaml.safe_load(per_worktree_path_a.read_text()))
    )
    per_worktree_errors_b = list(
        validator.iter_errors(yaml.safe_load(per_worktree_path_b.read_text()))
    )

    # AC-2 — clean per-story lock acquisition.
    locks_root_a = _locks_root(wt_a)
    locks_root_b = _locks_root(wt_b)
    acquire_a = acquire_lock(
        _STORY_A, worktree_path=wt_a, locks_root=locks_root_a, repo_root=repo_root
    )
    acquire_b = acquire_lock(
        _STORY_B, worktree_path=wt_b, locks_root=locks_root_b, repo_root=repo_root
    )

    # AC-5 — epic-run-state schema-valid BEFORE crash.
    epic_errors_before_crash = _epic_validation_errors(
        _epic_run_state(
            "epic-in-progress",
            {_STORY_A: "in-progress", _STORY_B: "in-progress"},
            (),
            consumed=0,
        )
    )

    # AC-3 — simulate the crashed worktree (story B) by replacing its lock with
    # a real stale on-disk record, then drive the REAL probe path.
    stale_record = _stale_lock_record(_STORY_B, wt_b)
    acquire_b.lock_path.write_text(
        yaml.safe_dump(json.loads(stale_record.model_dump_json()), sort_keys=False),
        encoding="utf-8",
    )
    stale_outcome_b, stale_next_b = evaluate_reattach(
        ReattachRequest(project_root=wt_b),
        run_state=run_state_b,
        marker_registry=marker_registry,
    )
    assert stale_next_b is not None
    stale_next_markers_b = tuple(stale_next_b.active_markers)

    # P1 (review) — prove the stale verdict came from the genuine parseable-lock
    # pid/age arm, NOT the corrupted-lock fallback that _probe_story_file_lock
    # also maps to "stale". A clean parse + the dead PID we wrote means the probe
    # inside evaluate_reattach read the same parseable record and fired the
    # pid-not-alive arm. Captured before recovery releases the lock (after
    # release the file is gone).
    stale_inspection_b = inspect_lock(
        _STORY_B, locks_root=locks_root_b, repo_root=repo_root
    )
    stale_lock_parsed_clean_b = (
        stale_inspection_b is not None
        and stale_inspection_b.record is not None
        and stale_inspection_b.parse_error is None
    )
    stale_lock_pid_b = (
        stale_inspection_b.record.pid
        if stale_inspection_b is not None and stale_inspection_b.record is not None
        else None
    )

    # AC-5 — epic-run-state schema-valid AFTER crash-detection (B carries the
    # transient marker; NFR-R2 — it is a signal, not sticky state).
    epic_errors_after_crash = _epic_validation_errors(
        _epic_run_state(
            "epic-in-progress",
            {_STORY_A: "in-progress", _STORY_B: "escalated"},
            (WORKTREE_STALE_LOCK_MARKER_CLASS,),
            consumed=1,
        )
    )

    # AC-3 negative control — story A's lock is fresh → reattach-clean.
    clean_outcome_a, _ = evaluate_reattach(
        ReattachRequest(project_root=wt_a),
        run_state=run_state_a,
        marker_registry=marker_registry,
    )

    # AC-3 recovery — operator clears the stale lock; a fresh evaluate_reattach
    # returns clean with the marker ABSENT (cleared on recovery, NFR-R2).
    release_lock(_STORY_B, locks_root=locks_root_b, repo_root=repo_root)
    recovered_outcome_b, recovered_next_b = evaluate_reattach(
        ReattachRequest(project_root=wt_b),
        run_state=run_state_b,
        marker_registry=marker_registry,
    )
    # reattach-clean returns its input run_state UNCHANGED (it neither adds nor
    # strips markers), so given a non-None input it never returns None here.
    assert recovered_next_b is not None

    # AC-5 — story A's per-worktree run-state still validates green right before
    # its worktree is removed ("throughout").
    per_worktree_errors_a_pre_cleanup = list(
        validator.iter_errors(yaml.safe_load(per_worktree_path_a.read_text()))
    )

    # AC-4 — clean cleanup of story A, observing the substrate's real git argvs
    # so NFR-R3's "no --force" is witnessed on the path that ACTUALLY removes.
    with _capture_substrate_git_runs() as captured_a_argv:
        cleanup_a = cleanup_worktree(
            _STORY_A,
            preserve_on_escalation=False,
            worktrees_root=worktrees_root,
            repo_root=repo_root,
        )
    cleanup_a_invoked_remove = any(
        argv[:3] == ["git", "worktree", "remove"] for argv in captured_a_argv
    )
    cleanup_a_used_force = any("--force" in argv for argv in captured_a_argv)

    # AC-4 — crashed-then-pruned cleanup of story B. The mid-cleanup-crash state
    # is the working tree gone with the git admin record intact.
    shutil.rmtree(wt_b)
    with _capture_substrate_git_runs() as captured_b_argv:
        cleanup_b = cleanup_worktree(
            _STORY_B,
            preserve_on_escalation=False,
            worktrees_root=worktrees_root,
            repo_root=repo_root,
        )
    invoked_remove_for_b = any(
        argv[:3] == ["git", "worktree", "remove"] for argv in captured_b_argv
    )
    cleanup_b_used_force = any("--force" in argv for argv in captured_b_argv)
    inspect_b_after_crash = inspect_worktree(
        _STORY_B, worktrees_root=worktrees_root, repo_root=repo_root
    )

    # AC-4 — documented OPERATOR remediation: `git worktree prune` is run by the
    # harness (the substrate has no prune entry point), NEVER --force / NEVER
    # `git worktree remove --force`. The substrate's own no-force behavior is
    # witnessed above via captured_{a,b}_argv; this prune just clears the admin
    # record so the zero-orphan list_active_worktrees check below is meaningful.
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )

    final_worktrees = list_active_worktrees(repo_root=repo_root)

    # AC-5 — epic-run-state schema-valid AFTER recovery + cleanup (marker
    # cleared; both stories terminal).
    epic_errors_after_recovery = _epic_validation_errors(
        _epic_run_state(
            "epic-complete",
            {_STORY_A: "done", _STORY_B: "done"},
            (),
            consumed=1,
        )
    )

    sandbox_paths = (
        worktrees_root,
        wt_a,
        wt_b,
        per_worktree_path_a,
        per_worktree_path_b,
        _session_run_state_path(wt_a),
        _session_run_state_path(wt_b),
        acquire_a.lock_path,
        acquire_b.lock_path,
    )

    return _SmokeResult(
        repo_root=repo_root,
        worktrees_root=worktrees_root,
        create_a=create_a,
        create_b=create_b,
        acquire_a=acquire_a,
        acquire_b=acquire_b,
        worktree_a_is_dir=worktree_a_is_dir,
        worktree_b_is_dir=worktree_b_is_dir,
        per_worktree_a_is_file=per_worktree_a_is_file,
        per_worktree_b_is_file=per_worktree_b_is_file,
        per_worktree_path_a=per_worktree_path_a,
        per_worktree_path_b=per_worktree_path_b,
        per_worktree_errors_a=per_worktree_errors_a,
        per_worktree_errors_b=per_worktree_errors_b,
        per_worktree_errors_a_pre_cleanup=per_worktree_errors_a_pre_cleanup,
        stale_outcome_b=stale_outcome_b,
        stale_next_markers_b=stale_next_markers_b,
        stale_lock_parsed_clean_b=stale_lock_parsed_clean_b,
        stale_lock_pid_b=stale_lock_pid_b,
        clean_outcome_a=clean_outcome_a,
        recovered_outcome_b=recovered_outcome_b,
        cleanup_a=cleanup_a,
        cleanup_b=cleanup_b,
        cleanup_a_invoked_remove=cleanup_a_invoked_remove,
        cleanup_a_used_force=cleanup_a_used_force,
        invoked_remove_for_b=invoked_remove_for_b,
        cleanup_b_used_force=cleanup_b_used_force,
        inspect_b_after_crash=inspect_b_after_crash,
        final_worktrees=final_worktrees,
        epic_errors_before_crash=epic_errors_before_crash,
        epic_errors_after_crash=epic_errors_after_crash,
        epic_errors_after_recovery=epic_errors_after_recovery,
        sandbox_paths=sandbox_paths,
    )


# --------------------------------------------------------------------------- #
# Fixtures                                                                      #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="function")
def marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


@pytest.fixture(scope="function")
def smoke(
    git_repo: pathlib.Path, marker_registry: MarkerClassRegistry
) -> _SmokeResult:
    return _drive_smoke(git_repo, marker_registry)


# --------------------------------------------------------------------------- #
# Witnesses                                                                     #
# --------------------------------------------------------------------------- #


def test_smoke_lands_as_epic_14_witness_under_tmp_path(
    smoke: _SmokeResult, tmp_path: pathlib.Path
) -> None:
    """AC-1 — every worktree / lock / run-state artifact lands under tmp_path;
    the smoke makes zero writes outside the sandbox."""
    assert smoke.repo_root == tmp_path
    for path in smoke.sandbox_paths:
        assert path.is_relative_to(tmp_path), f"{path} escaped the tmp_path sandbox"


def test_smoke_creates_two_worktrees_with_per_worktree_run_state_and_locks(
    smoke: _SmokeResult,
) -> None:
    """AC-2 — two per-story worktrees, per-worktree run-state at the 14.4
    address, clean lock acquisition (no stale takeover)."""
    assert smoke.create_a.created is True
    assert smoke.create_b.created is True
    assert smoke.create_a.branch_name == "bmad-automation/story/14-A"
    assert smoke.create_b.branch_name == "bmad-automation/story/14-B"
    assert smoke.worktree_a_is_dir is True
    assert smoke.worktree_b_is_dir is True

    # 14.4 per-worktree addressing: <worktrees_root>/<story_id>/run-state.yaml.
    assert smoke.per_worktree_path_a == smoke.worktrees_root / _STORY_A / "run-state.yaml"
    assert smoke.per_worktree_path_b == smoke.worktrees_root / _STORY_B / "run-state.yaml"
    assert smoke.per_worktree_a_is_file is True
    assert smoke.per_worktree_b_is_file is True

    assert smoke.acquire_a.acquired is True
    assert smoke.acquire_b.acquired is True
    assert smoke.acquire_a.was_stale_takeover is False
    assert smoke.acquire_b.was_stale_takeover is False


def test_smoke_crash_emits_worktree_stale_lock_then_clears_on_recovery(
    smoke: _SmokeResult,
) -> None:
    """AC-3 — the real ``_probe_story_file_lock`` path emits
    ``worktree-stale-lock`` on the crashed worktree, and the SAME on-disk
    run-state stops emitting once the lock is released (NFR-R2 idempotent
    recovery); story A is the clean negative control.

    Recovery is witnessed under the marker's RE-DERIVATION model:
    ``evaluate_reattach`` recomputes the verdict from the live lock each call
    (``record_marker_with_context`` adds the marker to a COPY; the
    ``reattach-clean`` branch returns its input ``run_state`` UNCHANGED). So
    "cleared on recovery" here means NON-RE-EMISSION once the lock is healthy —
    asserted via the OUTCOME, which genuinely constrains (a still-stale lock
    would yield ``worktree-stale-lock-detected``). Active-marker STRIPPING of a
    *persisted* marker is a distinct property that only bites once an
    Orchestrator persists marker-bearing run-state (Epic 15/18); it is tracked
    as the [Review][Decision] invariant in the story doc and deliberately NOT
    asserted here (it would require a ``session_start_reattach`` change AC-7
    forbids)."""
    # P1 (review) — the stale verdict took the genuine parseable-lock pid/age
    # arm, NOT the corrupted-lock fallback (which _probe_story_file_lock also
    # maps to "stale"): the lock parsed cleanly and carried the dead PID.
    assert smoke.stale_lock_parsed_clean_b is True
    assert smoke.stale_lock_pid_b == _DEAD_PID

    # Emission witness (mirrors test_session_start_reattach.py:944): detection
    # added the marker to the returned copy of the (clean) input run-state.
    assert smoke.stale_outcome_b.action == "worktree-stale-lock-detected"
    assert smoke.stale_outcome_b.marker_class == "worktree-stale-lock"
    assert smoke.stale_outcome_b.marker_class == WORKTREE_STALE_LOCK_MARKER_CLASS
    assert "worktree-stale-lock" in smoke.stale_next_markers_b

    # Non-re-emission witness: after the operator releases the lock, re-evaluating
    # the SAME on-disk run-state flips to reattach-clean with no marker_class.
    assert smoke.recovered_outcome_b.action == "reattach-clean"
    assert smoke.recovered_outcome_b.marker_class is None

    # Negative control — story A's fresh lock never emits.
    assert smoke.clean_outcome_a.action == "reattach-clean"
    assert smoke.clean_outcome_a.marker_class is None


def test_smoke_clean_and_crashed_then_pruned_cleanup_zero_orphans(
    smoke: _SmokeResult,
) -> None:
    """AC-4 — story A removed cleanly (real `git worktree remove`, never
    --force); story B's mid-cleanup-crash residue is left for prune (never
    escalated to remove/--force); zero Epic-14 orphan worktrees remain."""
    # Story A: clean removal actually ran `git worktree remove` and never --force
    # (NFR-R3 / ADR-009), observed over the substrate's real argvs.
    assert smoke.cleanup_a.removed is True
    assert smoke.cleanup_a.preserved_for_escalation is False
    assert smoke.cleanup_a_invoked_remove is True
    assert smoke.cleanup_a_used_force is False

    # Story B: prunable residue must NOT escalate to `git worktree remove`, and
    # the substrate must never pass --force on any git call.
    assert smoke.cleanup_b.removed is False
    assert smoke.cleanup_b.preserved_for_escalation is False
    assert smoke.invoked_remove_for_b is False, (
        "prunable residue must NOT trigger git worktree remove"
    )
    assert smoke.cleanup_b_used_force is False
    assert smoke.inspect_b_after_crash is not None
    assert smoke.inspect_b_after_crash.is_prunable is True

    epic_worktrees = [
        wt for wt in smoke.final_worktrees if wt.story_id in {_STORY_A, _STORY_B}
    ]
    assert epic_worktrees == [], "zero orphan Epic-14 worktrees expected post-cleanup"


def test_smoke_epic_run_state_schema_valid_throughout(smoke: _SmokeResult) -> None:
    """AC-5 — the epic-run-state aggregate schema-validates green at every
    observation point, and the per-worktree run-state documents validate green
    against the byte-unchanged run-state schema throughout."""
    assert smoke.epic_errors_before_crash == []
    assert smoke.epic_errors_after_crash == []
    assert smoke.epic_errors_after_recovery == []

    assert smoke.per_worktree_errors_a == []
    assert smoke.per_worktree_errors_b == []
    assert smoke.per_worktree_errors_a_pre_cleanup == []


def test_smoke_parallel_pollution_marker_enumerated_not_exercised(
    marker_registry: MarkerClassRegistry,
) -> None:
    """AC-6 — Story 14.5's pre-provisioned parallel-mode marker is enumerated in
    the taxonomy (coherence witness for Epic 18's flip-the-switch); the smoke
    neither emits nor detects it (no detector exists until Epic 18 Story 18.2)."""
    assert "parallel-story-state-pollution" in marker_registry.marker_classes


def test_smoke_composes_full_epic_14_lifecycle(smoke: _SmokeResult) -> None:
    """AC-10 — the four substrate surfaces interoperate at the seams across one
    composed lifecycle: create ×2 → per-worktree run-state ×2 → acquire ×2 →
    crash (stale lock) → detect+emit → recover → clean → clean cleanup of A +
    crashed-then-pruned cleanup of B → zero orphans → epic-run-state valid
    throughout."""
    assert smoke.create_a.created and smoke.create_b.created
    assert smoke.acquire_a.was_stale_takeover is False
    assert smoke.acquire_b.was_stale_takeover is False
    assert smoke.stale_outcome_b.action == "worktree-stale-lock-detected"
    assert smoke.recovered_outcome_b.action == "reattach-clean"
    assert smoke.cleanup_a.removed is True
    assert smoke.cleanup_b.removed is False
    assert smoke.inspect_b_after_crash is not None
    assert smoke.inspect_b_after_crash.is_prunable is True
    assert [wt for wt in smoke.final_worktrees if wt.story_id in {_STORY_A, _STORY_B}] == []
    assert smoke.epic_errors_before_crash == []
    assert smoke.epic_errors_after_crash == []
    assert smoke.epic_errors_after_recovery == []
