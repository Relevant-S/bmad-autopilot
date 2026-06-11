"""Regression witness for the concurrent `git worktree add` commondir race.

Distinct-story-id creates run concurrently in a single process (mirroring
``parallel_dispatch.dispatch_stories_parallel``'s ThreadPoolExecutor). Without
serialization of the worktree-admin mutating section, overlapping
``git worktree add`` invocations read a sibling's half-written
``.git/worktrees/<id>/commondir`` and die with the errno-0
``failed to read ... commondir: Success`` fatal. This test stresses that
window and asserts every create succeeds — it fails reliably if the
``_WORKTREE_ADMIN_LOCK`` serialization is removed.
"""

from __future__ import annotations

import concurrent.futures
import pathlib
import subprocess
import threading

import pytest

from loud_fail_harness.branch_lifecycle import DEFAULT_TRUNK_ALLOWLIST
from loud_fail_harness.worktree_lifecycle import (
    WorktreeLifecycleResult,
    create_worktree,
    list_active_worktrees,
)


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
    (tmp_path / "README.md").write_text("# initial commit\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=tmp_path)
    _run_git("commit", "-m", "initial", cwd=tmp_path)
    return tmp_path


def test_concurrent_distinct_story_creates_do_not_race_on_commondir(
    git_repo: pathlib.Path,
) -> None:
    worktrees_root = git_repo / "_bmad" / "automation" / "worktrees"
    # 16 concurrent creates widen the overlap window enough that the
    # pre-fix commondir race surfaces within a single run on CI (Linux);
    # with the _WORKTREE_ADMIN_LOCK serialization in place this is a
    # deterministic pass.
    story_ids = [f"918-{i}-story" for i in range(16)]
    release = threading.Barrier(len(story_ids))

    def _attempt(story_id: str) -> object:
        release.wait(timeout=10.0)
        try:
            return create_worktree(
                story_id,
                base_ref="main",
                trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
                worktrees_root=worktrees_root,
                repo_root=git_repo,
            )
        except BaseException as exc:  # noqa: BLE001 — surface any failure for the assert
            return exc

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(story_ids)) as pool:
        outcomes = list(pool.map(_attempt, story_ids))

    failures = [o for o in outcomes if isinstance(o, BaseException)]
    assert not failures, f"concurrent create_worktree raised: {failures!r}"
    assert all(
        isinstance(o, WorktreeLifecycleResult) and o.created for o in outcomes
    )

    active_paths = {r.worktree_path for r in list_active_worktrees(repo_root=git_repo)}
    for story_id in story_ids:
        assert (worktrees_root / story_id).resolve() in active_paths
