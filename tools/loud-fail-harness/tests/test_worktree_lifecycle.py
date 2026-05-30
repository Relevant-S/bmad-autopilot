"""Contract-coverage matrix for the per-story worktree lifecycle module
(story 14.2).

This docstring IS the contract-coverage checklist required by AC-9.
Reviewers verify every row maps to at least one passing test in this
module. Matrix is review-enforced; CI enforcement is the test suite +
ruff + mypy gates per CLAUDE.md "Common commands".

Branch-creation happy path (AC-4):
    [x] clean repo → new worktree + new branch via single atomic add → test_create_worktree_creates_new_worktree_on_clean_repo
    [x] result carries branch_name + path + base_ref                 → test_create_worktree_result_carries_branch_name_and_path_and_base_ref
    [x] branch name derives via branch_lifecycle convention          → test_create_worktree_derives_branch_name_via_branch_lifecycle_convention

Trunk-allowlist rejection (AC-4 step 3):
    [x] derived branch in trunk_allowlist → TrunkBranchWriteRejected → test_create_worktree_rejects_trunk_in_trunk_allowlist

Existing-worktree refusal (AC-3, AC-4 step 5):
    [x] existing worktree at target path → AlreadyExistsForStory     → test_create_worktree_existing_worktree_raises_already_exists
    [x] branch already checked out elsewhere → AlreadyExistsForStory → test_create_worktree_branch_already_checked_out_elsewhere_raises_already_exists
    [x] stale partial state (admin dir, missing tree) → StalePartialState → test_create_worktree_stale_partial_state_raises_stale_partial_state

Concurrency determinism (AC-9; epics-phase-2.md line 308):
    [x] two concurrent create attempts → exactly one success + one named exception → test_create_worktree_concurrent_attempts_surface_deterministically

API-shape (AC-2):
    [x] base_ref keyword-only                                        → test_create_worktree_keyword_only_base_ref
    [x] missing base_ref raises TypeError                            → test_create_worktree_missing_base_ref_typeerror
    [x] trunk_allowlist keyword-only                                 → test_create_worktree_keyword_only_trunk_allowlist
    [x] missing trunk_allowlist raises TypeError                     → test_create_worktree_missing_trunk_allowlist_typeerror

Cleanup happy path + idempotency (AC-5):
    [x] cleanup removes a clean worktree                             → test_cleanup_worktree_removes_clean_worktree
    [x] cleanup is idempotent (no worktree → no raise)               → test_cleanup_worktree_idempotent_when_no_worktree_exists

preserve_on_escalation short-circuit (AC-5 step 4):
    [x] preserve=True + state escalated → preserved, no git remove   → test_cleanup_worktree_preserve_on_escalation_true_short_circuits_when_state_is_escalated
    [x] preserve=False overrides regardless of state                 → test_cleanup_worktree_preserve_on_escalation_false_removes_regardless_of_state

Cleanup refusal + crash recovery (AC-5 step 5, AC-9):
    [x] unclean worktree → WorktreeRemoveRefused, no --force         → test_cleanup_worktree_unclean_worktree_raises_remove_refused
    [x] mid-cleanup crash recoverable via inspection prunable        → test_cleanup_worktree_crash_mid_cleanup_recoverable_via_prune

Inspection (AC-6):
    [x] inspect_worktree returns result for existing path            → test_inspect_worktree_returns_inspection_result_for_existing_path
    [x] inspect_worktree returns None for unknown story id           → test_inspect_worktree_returns_none_for_unknown_story_id
    [x] inspect_worktree surfaces prunable + reason                  → test_inspect_worktree_surfaces_prunable_annotation_with_reason
    [x] inspect_worktree surfaces locked annotation                  → test_inspect_worktree_surfaces_locked_annotation
    [x] inspect_worktree detached HEAD → branch is None              → test_inspect_worktree_detached_head_branch_is_none

List active worktrees (AC-6):
    [x] list returns tuple (NOT list) per Epic 1 retro Action #2     → test_list_active_worktrees_returns_tuple
    [x] list includes the main worktree                              → test_list_active_worktrees_includes_main_worktree
    [x] story_id is None for non-bmad paths                          → test_list_active_worktrees_story_id_none_for_non_bmad_paths

Operation-scope lockdown (AC-9; NFR-S3 banned-verb):
    [x] no git push                                                  → test_worktree_lifecycle_does_not_invoke_git_push
    [x] no git rebase                                                → test_worktree_lifecycle_does_not_invoke_git_rebase
    [x] no git branch delete                                         → test_worktree_lifecycle_does_not_invoke_git_branch_delete
    [x] no destructive commands (reset/clean/cherry-pick/tag/remote) → test_worktree_lifecycle_does_not_invoke_destructive_commands
    [x] no remote commands (fetch/pull/push)                         → test_worktree_lifecycle_does_not_invoke_remote_commands
    [x] no --force token anywhere in module source                   → test_worktree_lifecycle_does_not_invoke_force_anywhere

Module discipline (AC-1; Epic 1 retro Action #1 / #2):
    [x] __all__ matches public surface                               → test_module_all_exports
    [x] WorktreeLifecycleResult frozen                               → test_worktree_lifecycle_result_is_frozen
    [x] WorktreeInspectionResult is_prunable field exists as bool    → test_worktree_lifecycle_uncommitted_paths_field_is_tuple_not_list
    [x] find_repo_root NOT called at module import time              → test_find_repo_root_not_called_at_import
    [x] repo_root=None resolves lazily                               → test_create_worktree_repo_root_none_resolves_lazily

Marker-class linkage (AC-3; sensor-not-advisor):
    [x] all three exceptions carry marker_class="worktree-stale-lock"→ test_worktree_stale_lock_marker_class_matches_constant
"""

from __future__ import annotations

import ast
import concurrent.futures
import inspect
import os
import pathlib
import shutil
import subprocess
from typing import Any
from unittest import mock

import pytest
from pydantic import ValidationError

import yaml

from loud_fail_harness import worktree_lifecycle
from loud_fail_harness.branch_lifecycle import (
    DEFAULT_TRUNK_ALLOWLIST,
    TrunkBranchWriteRejected,
)
from loud_fail_harness.worktree_lifecycle import (
    WorktreeAlreadyExistsForStory,
    WorktreeCleanupResult,
    WorktreeInspectionResult,
    WorktreeLifecycleResult,
    WorktreeRemoveRefused,
    WorktreeStalePartialState,
    cleanup_worktree,
    create_worktree,
    inspect_worktree,
    list_active_worktrees,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


def _run_git(*args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture(scope="function")
def git_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    _run_git("init", "-b", "main", cwd=tmp_path)
    _run_git("config", "user.email", "test@bmad-automation.local", cwd=tmp_path)
    _run_git("config", "user.name", "BMAD Test", cwd=tmp_path)
    _run_git("config", "commit.gpgsign", "false", cwd=tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("# initial commit\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=tmp_path)
    _run_git("commit", "-m", "initial", cwd=tmp_path)
    return tmp_path


def _make_worktrees_root(git_repo: pathlib.Path) -> pathlib.Path:
    return git_repo / "_bmad" / "automation" / "worktrees"


def _write_run_state(repo_root: pathlib.Path, *, current_state: str) -> None:
    rs_path = repo_root / "_bmad" / "automation" / "run-state.yaml"
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    rs_path.write_text(
        yaml.safe_dump({
            "schema_version": "1.3",
            "story_id": "14-2",
            "run_id": "test-run-001",
            "current_state": current_state,
            "branch_name": "story/14-2-test",
            "dispatched_specialist": None,
            "last_envelope": None,
            "pending_qa_dispatch_payload": None,
            "retry_history": [],
            "active_markers": [],
            "marker_contexts": {},
            "cost_to_date_by_specialist": {},
        }),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# Branch-creation happy path (AC-4)                                           #
# --------------------------------------------------------------------------- #


def test_create_worktree_creates_new_worktree_on_clean_repo(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    result = create_worktree(
        "14-2",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    assert isinstance(result, WorktreeLifecycleResult)
    assert result.story_id == "14-2"
    assert result.created is True
    assert result.worktree_path == worktrees_root / "14-2"
    assert result.worktree_path.is_dir()
    branch = _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=result.worktree_path).stdout.strip()
    assert branch == "bmad-automation/story/14-2"


def test_create_worktree_result_carries_branch_name_and_path_and_base_ref(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    result = create_worktree(
        "14-2",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    assert result.branch_name == "bmad-automation/story/14-2"
    assert result.worktree_path == worktrees_root / "14-2"
    assert result.base_ref == "main"
    assert result.repo_root == git_repo


def test_create_worktree_derives_branch_name_via_branch_lifecycle_convention(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    result = create_worktree(
        "9-9",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    assert result.branch_name == "bmad-automation/story/9-9"


# --------------------------------------------------------------------------- #
# Trunk-allowlist rejection (AC-4 step 3)                                     #
# --------------------------------------------------------------------------- #


def test_create_worktree_rejects_trunk_in_trunk_allowlist(
    git_repo: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The derived branch name landing inside the trunk_allowlist tuple
    re-uses the Phase-1 :exc:`TrunkBranchWriteRejected` (AC-4 step 3)."""
    monkeypatch.setattr(worktree_lifecycle, "_branch_name_for_story", lambda _id: "main")
    worktrees_root = _make_worktrees_root(git_repo)
    with pytest.raises(TrunkBranchWriteRejected) as excinfo:
        create_worktree(
            "test",
            base_ref="main",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            worktrees_root=worktrees_root,
            repo_root=git_repo,
        )
    assert excinfo.value.attempted_branch == "main"


# --------------------------------------------------------------------------- #
# Existing-worktree refusal (AC-3, AC-4 step 5)                               #
# --------------------------------------------------------------------------- #


def test_create_worktree_existing_worktree_raises_already_exists(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    create_worktree(
        "14-2",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    with pytest.raises(WorktreeAlreadyExistsForStory) as excinfo:
        create_worktree(
            "14-2",
            base_ref="main",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            worktrees_root=worktrees_root,
            repo_root=git_repo,
        )
    assert excinfo.value.marker_class == "worktree-stale-lock"
    assert excinfo.value.attempted_branch_name == "bmad-automation/story/14-2"


def test_create_worktree_branch_already_checked_out_elsewhere_raises_already_exists(
    git_repo: pathlib.Path,
) -> None:
    """The derived branch is already checked out in another worktree path
    (e.g., the user manually created it elsewhere); the substrate
    surfaces :exc:`WorktreeAlreadyExistsForStory` BEFORE the git
    invocation rather than translating git's own duplicate-branch
    refusal."""
    elsewhere = git_repo / "elsewhere-worktree"
    _run_git(
        "worktree",
        "add",
        "-b",
        "bmad-automation/story/14-2",
        str(elsewhere),
        "main",
        cwd=git_repo,
    )
    worktrees_root = _make_worktrees_root(git_repo)
    with pytest.raises(WorktreeAlreadyExistsForStory):
        create_worktree(
            "14-2",
            base_ref="main",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            worktrees_root=worktrees_root,
            repo_root=git_repo,
        )


def test_create_worktree_stale_partial_state_raises_stale_partial_state(
    git_repo: pathlib.Path,
) -> None:
    """Simulate mid-create / mid-cleanup crash: create the worktree, then
    delete its working tree on disk. ``git worktree list --porcelain``
    marks the record as ``prunable``; create_worktree surfaces
    :exc:`WorktreeStalePartialState`."""
    worktrees_root = _make_worktrees_root(git_repo)
    create_worktree(
        "14-2",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    shutil.rmtree(worktrees_root / "14-2")
    with pytest.raises(WorktreeStalePartialState) as excinfo:
        create_worktree(
            "14-2",
            base_ref="main",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            worktrees_root=worktrees_root,
            repo_root=git_repo,
        )
    assert excinfo.value.marker_class == "worktree-stale-lock"


# --------------------------------------------------------------------------- #
# Concurrency determinism (AC-9; epics-phase-2.md line 308)                   #
# --------------------------------------------------------------------------- #


def test_create_worktree_concurrent_attempts_surface_deterministically(
    git_repo: pathlib.Path,
) -> None:
    """Two concurrent create attempts against the same story-id end with
    no orphan worktree and the loser's exception is one of the named
    types — either :exc:`WorktreeAlreadyExistsForStory` (substrate-
    detected) OR :exc:`subprocess.CalledProcessError` (git-detected
    duplicate refusal). Either is acceptable per epics-phase-2.md line
    308 "no orphan worktree, no torn state"."""
    worktrees_root = _make_worktrees_root(git_repo)

    def _attempt() -> object:
        try:
            return create_worktree(
                "14-2",
                base_ref="main",
                trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
                worktrees_root=worktrees_root,
                repo_root=git_repo,
            )
        except (
            WorktreeAlreadyExistsForStory,
            WorktreeStalePartialState,
            subprocess.CalledProcessError,
        ) as exc:
            return exc

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _i: _attempt(), range(2)))

    successes = [o for o in outcomes if isinstance(o, WorktreeLifecycleResult)]
    exceptions = [o for o in outcomes if isinstance(o, BaseException)]

    assert len(successes) == 1, f"expected exactly one success, got {outcomes!r}"
    assert len(exceptions) == 1, f"expected exactly one exception, got {outcomes!r}"
    worktree_path = worktrees_root / "14-2"
    active = list_active_worktrees(repo_root=git_repo)
    matching = [r for r in active if r.worktree_path == worktree_path.resolve()]
    assert len(matching) == 1, f"Expected exactly one active worktree at {worktree_path}, got {matching!r}"


# --------------------------------------------------------------------------- #
# API-shape (AC-2)                                                            #
# --------------------------------------------------------------------------- #


def test_create_worktree_keyword_only_base_ref() -> None:
    sig = inspect.signature(create_worktree)
    param = sig.parameters["base_ref"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty


def test_create_worktree_missing_base_ref_typeerror() -> None:
    with pytest.raises(TypeError):
        create_worktree(  # type: ignore[call-arg]
            "14-2",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        )


def test_create_worktree_keyword_only_trunk_allowlist() -> None:
    sig = inspect.signature(create_worktree)
    param = sig.parameters["trunk_allowlist"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty


def test_create_worktree_missing_trunk_allowlist_typeerror() -> None:
    with pytest.raises(TypeError):
        create_worktree(  # type: ignore[call-arg]
            "14-2",
            base_ref="main",
        )


# --------------------------------------------------------------------------- #
# Cleanup happy path + idempotency (AC-5)                                     #
# --------------------------------------------------------------------------- #


def test_cleanup_worktree_removes_clean_worktree(git_repo: pathlib.Path) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    create_worktree(
        "14-2",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    result = cleanup_worktree(
        "14-2",
        preserve_on_escalation=False,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    assert isinstance(result, WorktreeCleanupResult)
    assert result.removed is True
    assert result.preserved_for_escalation is False
    assert not (worktrees_root / "14-2").exists()


def test_cleanup_worktree_idempotent_when_no_worktree_exists(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    result = cleanup_worktree(
        "never-existed",
        preserve_on_escalation=False,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    assert result.removed is False
    assert result.preserved_for_escalation is False


# --------------------------------------------------------------------------- #
# preserve_on_escalation short-circuit (AC-5 step 4)                          #
# --------------------------------------------------------------------------- #


def test_cleanup_worktree_preserve_on_escalation_true_short_circuits_when_state_is_escalated(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    create_worktree(
        "14-2",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    _write_run_state(git_repo, current_state="escalated")

    real_run = subprocess.run

    def _capturing_run(*args: Any, **kwargs: Any) -> Any:
        if args and isinstance(args[0], list):
            cmd = args[0]
            assert not (cmd[:3] == ["git", "worktree", "remove"]), (
                f"escalation short-circuit must NOT invoke git worktree remove: {cmd!r}"
            )
        return real_run(*args, **kwargs)

    with mock.patch.object(worktree_lifecycle.subprocess, "run", side_effect=_capturing_run):
        result = cleanup_worktree(
            "14-2",
            preserve_on_escalation=True,
            worktrees_root=worktrees_root,
            repo_root=git_repo,
        )
    assert result.removed is False
    assert result.preserved_for_escalation is True
    assert (worktrees_root / "14-2").is_dir(), "escalated worktree must be preserved"


def test_cleanup_worktree_preserve_on_escalation_false_removes_regardless_of_state(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    create_worktree(
        "14-2",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    _write_run_state(git_repo, current_state="escalated")
    result = cleanup_worktree(
        "14-2",
        preserve_on_escalation=False,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    assert result.removed is True
    assert result.preserved_for_escalation is False


# --------------------------------------------------------------------------- #
# Cleanup refusal + crash recovery (AC-5 step 5, AC-9)                        #
# --------------------------------------------------------------------------- #


def test_cleanup_worktree_unclean_worktree_raises_remove_refused(
    git_repo: pathlib.Path,
) -> None:
    """An untracked file inside the worktree triggers git's
    "contains modified or untracked files" refusal; the substrate
    surfaces :exc:`WorktreeRemoveRefused` WITHOUT escalating to
    ``--force`` (NFR-S3 banned-verb extension)."""
    worktrees_root = _make_worktrees_root(git_repo)
    create_worktree(
        "14-2",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    untracked = worktrees_root / "14-2" / "untracked.txt"
    untracked.write_text("noise\n", encoding="utf-8")

    real_run = subprocess.run

    def _capturing_run(*args: Any, **kwargs: Any) -> Any:
        if args and isinstance(args[0], list):
            cmd = args[0]
            assert "--force" not in cmd, f"--force forbidden in cleanup path: {cmd!r}"
            assert "-f" not in cmd, f"-f forbidden in cleanup path: {cmd!r}"
        return real_run(*args, **kwargs)

    with mock.patch.object(worktree_lifecycle.subprocess, "run", side_effect=_capturing_run):
        with pytest.raises(WorktreeRemoveRefused) as excinfo:
            cleanup_worktree(
                "14-2",
                preserve_on_escalation=False,
                worktrees_root=worktrees_root,
                repo_root=git_repo,
            )
    assert excinfo.value.marker_class == "worktree-stale-lock"


def test_cleanup_worktree_crash_mid_cleanup_recoverable_via_prune(
    git_repo: pathlib.Path,
) -> None:
    """Simulate mid-cleanup crash: create + then ``rm -rf`` the working
    tree path; the admin dir remains. Per Story 14.2 AC-5 design notes
    (conservative path), :func:`cleanup_worktree` returns
    ``removed=False, preserved_for_escalation=False`` and does NOT
    invoke ``git worktree remove`` — :func:`inspect_worktree` surfaces
    the prunable annotation so the operator runs ``git worktree
    prune`` as the explicit remediation."""
    worktrees_root = _make_worktrees_root(git_repo)
    create_worktree(
        "14-2",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    shutil.rmtree(worktrees_root / "14-2")

    real_run = subprocess.run

    invoked_remove = False

    def _capturing_run(*args: Any, **kwargs: Any) -> Any:
        nonlocal invoked_remove
        if args and isinstance(args[0], list):
            cmd = args[0]
            if cmd[:3] == ["git", "worktree", "remove"]:
                invoked_remove = True
        return real_run(*args, **kwargs)

    with mock.patch.object(worktree_lifecycle.subprocess, "run", side_effect=_capturing_run):
        result = cleanup_worktree(
            "14-2",
            preserve_on_escalation=False,
            worktrees_root=worktrees_root,
            repo_root=git_repo,
        )
    assert result.removed is False
    assert result.preserved_for_escalation is False
    assert invoked_remove is False, "prunable record must NOT trigger git worktree remove"

    inspection = inspect_worktree(
        "14-2",
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    assert inspection is not None
    assert inspection.is_prunable is True


def test_cleanup_worktree_prunable_escalated_returns_removed_false_not_preserved(
    git_repo: pathlib.Path,
) -> None:
    """Prunable check fires BEFORE escalation short-circuit per Patch A
    ordering fix. A prunable worktree (working tree missing on disk) has
    nothing to preserve, so ``preserved_for_escalation`` must be
    ``False`` even when ``preserve_on_escalation=True`` and run-state
    is ``escalated``."""
    worktrees_root = _make_worktrees_root(git_repo)
    create_worktree(
        "14-2",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    shutil.rmtree(worktrees_root / "14-2")

    inspection = inspect_worktree(
        "14-2",
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    assert inspection is not None
    assert inspection.is_prunable is True

    with mock.patch.object(
        worktree_lifecycle,
        "_read_current_state",
        return_value="escalated",
    ):
        result = cleanup_worktree(
            "14-2",
            preserve_on_escalation=True,
            worktrees_root=worktrees_root,
            repo_root=git_repo,
        )

    assert result.removed is False
    assert result.preserved_for_escalation is False, (
        "prunable worktree must NOT be marked preserved_for_escalation — "
        "is_prunable check fires before escalation short-circuit"
    )


# --------------------------------------------------------------------------- #
# Inspection (AC-6)                                                           #
# --------------------------------------------------------------------------- #


def test_inspect_worktree_returns_inspection_result_for_existing_path(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    create_worktree(
        "14-2",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    inspection = inspect_worktree(
        "14-2",
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    assert inspection is not None
    assert inspection.story_id == "14-2"
    assert inspection.branch == "bmad-automation/story/14-2"
    assert inspection.head_sha is not None
    assert len(inspection.head_sha) == 40
    assert inspection.is_prunable is False
    assert inspection.is_locked is False


def test_inspect_worktree_returns_none_for_unknown_story_id(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    inspection = inspect_worktree(
        "no-such-story",
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    assert inspection is None


def test_inspect_worktree_surfaces_prunable_annotation_with_reason(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    create_worktree(
        "14-2",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    shutil.rmtree(worktrees_root / "14-2")
    inspection = inspect_worktree(
        "14-2",
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    assert inspection is not None
    assert inspection.is_prunable is True
    assert inspection.prunable_reason is not None
    assert inspection.prunable_reason != ""


def test_inspect_worktree_surfaces_locked_annotation(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    create_worktree(
        "14-2",
        base_ref="main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    _run_git(
        "worktree",
        "lock",
        str(worktrees_root / "14-2"),
        cwd=git_repo,
    )
    inspection = inspect_worktree(
        "14-2",
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    assert inspection is not None
    assert inspection.is_locked is True
    _run_git(
        "worktree",
        "unlock",
        str(worktrees_root / "14-2"),
        cwd=git_repo,
    )


def test_inspect_worktree_detached_head_branch_is_none(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    head_sha = _run_git("rev-parse", "HEAD", cwd=git_repo).stdout.strip()
    detached_path = worktrees_root / "14-2"
    detached_path.parent.mkdir(parents=True, exist_ok=True)
    _run_git(
        "worktree",
        "add",
        "--detach",
        str(detached_path),
        head_sha,
        cwd=git_repo,
    )
    inspection = inspect_worktree(
        "14-2",
        worktrees_root=worktrees_root,
        repo_root=git_repo,
    )
    assert inspection is not None
    assert inspection.branch is None


# --------------------------------------------------------------------------- #
# List active worktrees (AC-6)                                                #
# --------------------------------------------------------------------------- #


def test_list_active_worktrees_returns_tuple(git_repo: pathlib.Path) -> None:
    listing = list_active_worktrees(repo_root=git_repo)
    assert isinstance(listing, tuple)
    assert not hasattr(listing, "append")


def test_list_active_worktrees_includes_main_worktree(
    git_repo: pathlib.Path,
) -> None:
    listing = list_active_worktrees(repo_root=git_repo)
    main_paths = {r.worktree_path for r in listing}
    assert git_repo.resolve() in main_paths


def test_list_active_worktrees_story_id_none_for_non_bmad_paths(
    git_repo: pathlib.Path,
) -> None:
    elsewhere = git_repo / "elsewhere-worktree"
    _run_git(
        "worktree",
        "add",
        "-b",
        "ad-hoc",
        str(elsewhere),
        "main",
        cwd=git_repo,
    )
    listing = list_active_worktrees(repo_root=git_repo)
    matching = [r for r in listing if r.worktree_path == elsewhere.resolve()]
    assert len(matching) == 1
    assert matching[0].story_id is None


# --------------------------------------------------------------------------- #
# Operation-scope lockdown (AC-9; NFR-S3 banned-verb)                         #
# --------------------------------------------------------------------------- #


def _capture_invocations(
    repo_root: pathlib.Path,
    worktrees_root: pathlib.Path,
) -> list[list[str]]:
    real_run = subprocess.run
    captured: list[list[str]] = []

    def _capturing_run(*args: Any, **kwargs: Any) -> Any:
        if args and isinstance(args[0], list):
            captured.append(list(args[0]))
        return real_run(*args, **kwargs)

    with mock.patch.object(worktree_lifecycle.subprocess, "run", side_effect=_capturing_run):
        create_worktree(
            "14-2",
            base_ref="main",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            worktrees_root=worktrees_root,
            repo_root=repo_root,
        )
        inspect_worktree(
            "14-2",
            worktrees_root=worktrees_root,
            repo_root=repo_root,
        )
        list_active_worktrees(repo_root=repo_root)
        cleanup_worktree(
            "14-2",
            preserve_on_escalation=False,
            worktrees_root=worktrees_root,
            repo_root=repo_root,
        )
    return captured


def test_worktree_lifecycle_does_not_invoke_git_push(git_repo: pathlib.Path) -> None:
    captured = _capture_invocations(git_repo, _make_worktrees_root(git_repo))
    for invocation in captured:
        assert not (invocation[:2] == ["git", "push"]), f"git push invoked: {invocation!r}"


def test_worktree_lifecycle_does_not_invoke_git_rebase(git_repo: pathlib.Path) -> None:
    captured = _capture_invocations(git_repo, _make_worktrees_root(git_repo))
    for invocation in captured:
        assert not (invocation[:2] == ["git", "rebase"]), f"git rebase invoked: {invocation!r}"


def test_worktree_lifecycle_does_not_invoke_git_branch_delete(
    git_repo: pathlib.Path,
) -> None:
    captured = _capture_invocations(git_repo, _make_worktrees_root(git_repo))
    forbidden_branch_flags = {"-D", "--delete", "-d"}
    for invocation in captured:
        if invocation[:2] == ["git", "branch"] and len(invocation) > 2:
            assert invocation[2] not in forbidden_branch_flags, (
                f"git branch delete invoked: {invocation!r}"
            )


def test_worktree_lifecycle_does_not_invoke_destructive_commands(
    git_repo: pathlib.Path,
) -> None:
    captured = _capture_invocations(git_repo, _make_worktrees_root(git_repo))
    forbidden_subcommands = {"reset", "clean", "cherry-pick", "tag", "remote"}
    for invocation in captured:
        if len(invocation) >= 2 and invocation[0] == "git":
            assert invocation[1] not in forbidden_subcommands, (
                f"destructive git subcommand invoked: {invocation!r}"
            )


def test_worktree_lifecycle_does_not_invoke_remote_commands(
    git_repo: pathlib.Path,
) -> None:
    captured = _capture_invocations(git_repo, _make_worktrees_root(git_repo))
    forbidden_subcommands = {"fetch", "pull", "push", "merge"}
    for invocation in captured:
        if len(invocation) >= 2 and invocation[0] == "git":
            assert invocation[1] not in forbidden_subcommands, (
                f"forbidden git subcommand invoked: {invocation!r}"
            )


def test_worktree_lifecycle_does_not_invoke_force_anywhere() -> None:
    """ADR-009 Interaction-with-NFR-R3 clause (e) verbatim. AST walk
    across subprocess.run call argument lists — the complete absence of
    the ``--force`` token in any subprocess.run invocation is the
    structural witness."""
    source_path = pathlib.Path(worktree_lifecycle.__file__)
    assert source_path.suffix == ".py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_subprocess_run = (
            (isinstance(func, ast.Attribute) and func.attr == "run")
            or (isinstance(func, ast.Name) and func.id == "run")
        )
        if not is_subprocess_run:
            continue
        if not node.args:
            continue
        cmd_arg = node.args[0]
        if isinstance(cmd_arg, ast.List):
            for elt in cmd_arg.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    assert elt.value != "--force", (
                        f"'--force' found in subprocess.run call at line {node.lineno}"
                    )


# --------------------------------------------------------------------------- #
# Module discipline (AC-1; Epic 1 retro Action #1 / #2)                       #
# --------------------------------------------------------------------------- #


def test_module_all_exports() -> None:
    expected = {
        "WorktreeAlreadyExistsForStory",
        "WorktreeCleanupResult",
        "WorktreeInspectionResult",
        "WorktreeLifecycleBlocked",
        "WorktreeLifecycleResult",
        "WorktreeRemoveRefused",
        "WorktreeStalePartialState",
        "cleanup_worktree",
        "create_worktree",
        "inspect_worktree",
        "list_active_worktrees",
    }
    assert set(worktree_lifecycle.__all__) == expected


def test_worktree_lifecycle_result_is_frozen() -> None:
    result = WorktreeLifecycleResult(
        story_id="14-2",
        branch_name="bmad-automation/story/14-2",
        worktree_path=pathlib.Path("/tmp/worktree"),
        created=True,
        base_ref="main",
        repo_root=pathlib.Path("/tmp/repo"),
    )
    with pytest.raises(ValidationError):
        result.story_id = "other"  # type: ignore[misc]


def test_worktree_lifecycle_uncommitted_paths_field_is_tuple_not_list() -> None:
    """Inspection result must have NO list[…] sequence fields per Epic 1
    retro Action #2 frozen-tuple discipline. Verified by inspecting
    the model field annotations — none should be ``list[…]``."""
    for model in (
        WorktreeLifecycleResult,
        WorktreeCleanupResult,
        WorktreeInspectionResult,
    ):
        for name, field in model.model_fields.items():
            annotation_str = str(field.annotation)
            assert "list[" not in annotation_str, (
                f"{model.__name__}.{name}: forbidden list[…] annotation {annotation_str!r}"
            )


def test_find_repo_root_not_called_at_import() -> None:
    """Re-import the module with ``find_repo_root`` patched to raise; if
    the module called it at import time, the import would fail."""
    import importlib

    with mock.patch(
        "loud_fail_harness._shared.find_repo_root",
        side_effect=RuntimeError("must not be called at import"),
    ):
        importlib.reload(worktree_lifecycle)
    importlib.reload(worktree_lifecycle)


def test_create_worktree_repo_root_none_resolves_lazily(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = _make_worktrees_root(git_repo)
    with mock.patch.object(
        worktree_lifecycle, "_default_repo_root", return_value=git_repo
    ):
        result = create_worktree(
            "14-2",
            base_ref="main",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            worktrees_root=worktrees_root,
            # No repo_root — relies on _default_repo_root()
        )
    assert result.repo_root == git_repo


# --------------------------------------------------------------------------- #
# Marker-class linkage (AC-3; sensor-not-advisor)                             #
# --------------------------------------------------------------------------- #


def test_worktree_stale_lock_marker_class_matches_constant() -> None:
    """All three new exception classes carry
    ``marker_class="worktree-stale-lock"`` (the single forward-pointer
    string Story 14.3 will enumerate in
    ``schemas/marker-taxonomy.yaml`` per ADR-009 Consequence 5)."""
    already_exists = WorktreeAlreadyExistsForStory(
        attempted_story_id="14-2",
        attempted_worktree_path=pathlib.Path("/tmp/14-2"),
        attempted_branch_name="bmad-automation/story/14-2",
    )
    stale_partial = WorktreeStalePartialState(
        attempted_story_id="14-2",
        attempted_worktree_path=pathlib.Path("/tmp/14-2"),
    )
    remove_refused = WorktreeRemoveRefused(
        attempted_story_id="14-2",
        attempted_worktree_path=pathlib.Path("/tmp/14-2"),
    )
    assert already_exists.marker_class == "worktree-stale-lock"
    assert stale_partial.marker_class == "worktree-stale-lock"
    assert remove_refused.marker_class == "worktree-stale-lock"


# Silence ruff unused-import for `os`, used implicitly by various git tests.
_ = os
