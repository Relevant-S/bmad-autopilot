"""Epic-21 background-execution reference-run fixture — Story 21.2 / FR-P2-7.

The witness captured for Epic 23 of the reduced ``partial`` surface the Story
21.1 spike selected (verdict ``partially-stable`` → path ``partial``). Mirrors
the Story 18.4 / 15.5 reference-run fixture idiom: ``tmp_path``-scoped, a REAL
git repo via the ``_run_git`` / ``git_repo`` helpers, synthetic non-real story
ids, and INJECTED loop / launcher stubs — no live ``claude --bg`` daemon is
ever spawned (the stand-in posture, per the 20.4 reference-run disclosure
discipline; see ``docs/reference-runs/21-2-background-web/narrative.md``).

Genuinely witnessed here: (a) the non-blocking-dispatch property
(``background_execution: true`` builds a well-formed ``claude --bg`` argv and the
inline foreground loop is NOT taken); (b) the foreground bit-identity on flag-off
(no background command built; the foreground loop runs); (c) the reconciliation
classification + ``background-primitive-unstable`` emission driven through the
REAL ``make_git_ground_truth_probe`` against a real git repo (a landed per-story
branch → ``completed-confirmed`` / silent; an absent branch → ``unconfirmable`` /
marker). A live daemon round-trip is out of scope for a deterministic CI fixture.
"""

from __future__ import annotations

import pathlib
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from loud_fail_harness.background_dispatch import (
    BACKGROUND_PRIMITIVE_UNSTABLE_MARKER,
    BACKGROUND_REENTRY_FLAG,
    dispatch_run,
    make_git_ground_truth_probe,
    reconcile_background_runs,
    render_background_runs_section,
)
from loud_fail_harness.branch_lifecycle import _branch_name_for_story
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)

# Synthetic, non-real story ids (never appear in sprint-status.yaml).
_LANDED_STORY = "auto-021-bg-landed"
_LOST_STORY = "auto-021-bg-lost"
_INFLIGHT_STORY = "auto-021-bg-inflight"


def _run_git(*args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


@pytest.fixture(scope="function")
def git_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    _run_git("init", "-b", "main", cwd=tmp_path)
    _run_git("config", "user.email", "test@bmad-automation.local", cwd=tmp_path)
    _run_git("config", "user.name", "BMAD Test", cwd=tmp_path)
    _run_git("config", "commit.gpgsign", "false", cwd=tmp_path)
    (tmp_path / "README.md").write_text("# initial\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=tmp_path)
    _run_git("commit", "-m", "initial", cwd=tmp_path)
    # The "landed" story's per-story branch with a real commit (work survived).
    branch = _branch_name_for_story(_LANDED_STORY)
    _run_git("checkout", "-b", branch, cwd=tmp_path)
    (tmp_path / "work.txt").write_text("done\n", encoding="utf-8")
    _run_git("add", "work.txt", cwd=tmp_path)
    _run_git("commit", "-m", "landed story work", cwd=tmp_path)
    _run_git("checkout", "main", cwd=tmp_path)
    # NOTE: the "lost" story's branch is intentionally NEVER created (the
    # #63023 silent-loss signature: agents say completed, git shows nothing).
    return tmp_path


@pytest.fixture(scope="function")
def marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    def __call__(self, marker_class: str, context: Mapping[str, Any]) -> None:
        self.calls.append((marker_class, dict(context)))


# --------------------------------------------------------------------------- #
# (a) background_execution: true → non-blocking dispatch; foreground NOT taken #
# --------------------------------------------------------------------------- #


def test_background_true_dispatches_and_skips_foreground_loop(
    git_repo: pathlib.Path,
) -> None:
    launched: list[Sequence[str]] = []
    foreground_calls: list[int] = []

    result = dispatch_run(
        _LANDED_STORY,
        project_root=git_repo,
        background_execution=True,
        launcher=lambda cmd: launched.append(cmd) or "daemon-session-id",
        foreground_runner=lambda: foreground_calls.append(1),
    )

    assert result.mode == "background"
    assert result.command is not None
    assert result.command[0] == "claude" and result.command[1] == "--bg"
    assert (
        result.command[-1]
        == f"/bmad-automation run {_LANDED_STORY} {BACKGROUND_REENTRY_FLAG}"
    )
    assert result.confirmation is not None
    assert "/bmad-automation status" in result.confirmation
    # The non-blocking-dispatch property: the inline foreground loop is NOT run.
    assert foreground_calls == []
    assert len(launched) == 1


# --------------------------------------------------------------------------- #
# (b) background_execution: false → bit-identical foreground loop              #
# --------------------------------------------------------------------------- #


def test_background_false_is_bit_identical_foreground(git_repo: pathlib.Path) -> None:
    launched: list[Sequence[str]] = []
    foreground_calls: list[int] = []

    result = dispatch_run(
        _LANDED_STORY,
        project_root=git_repo,
        background_execution=False,
        launcher=lambda cmd: launched.append(cmd),
        foreground_runner=lambda: foreground_calls.append(1) or "loop-result",
    )

    assert result.mode == "foreground"
    assert result.command is None  # zero claude --bg invocation
    assert result.foreground_result == "loop-result"
    assert launched == []  # zero background-run state
    assert foreground_calls == [1]


# --------------------------------------------------------------------------- #
# (c) reconcile classification + marker emission via the REAL git probe        #
# --------------------------------------------------------------------------- #


def test_reconcile_against_real_git_classifies_and_emits(
    git_repo: pathlib.Path, marker_registry: MarkerClassRegistry
) -> None:
    recorder = _Recorder()
    probe = make_git_ground_truth_probe(repo_root=git_repo)

    agents_json: list[Mapping[str, Any]] = [
        # In-flight: still running — no confirmation owed, silent.
        {
            "id": "job-inflight",
            "state": "running",
            "prompt": f"/bmad-automation run {_INFLIGHT_STORY} --foreground",
        },
        # Completed AND the per-story branch landed with commits → confirmed.
        {
            "id": "job-landed",
            "state": "completed",
            "prompt": f"/bmad-automation run {_LANDED_STORY} --foreground",
        },
        # Completed per the registry, but git shows NO branch → unconfirmable.
        {
            "id": "job-lost",
            "state": "completed",
            "prompt": f"/bmad-automation run {_LOST_STORY} --foreground",
        },
    ]

    roster = reconcile_background_runs(
        agents_json,
        git_ground_truth_probe=probe,
        marker_recorder=recorder,
        marker_registry=marker_registry,
    )

    by_id = {r.session_id: r for r in roster.runs}
    assert by_id["job-inflight"].classification == "in-flight"
    assert by_id["job-landed"].classification == "completed-confirmed"
    assert by_id["job-lost"].classification == "unconfirmable"

    # The marker fires EXACTLY on the unconfirmable case — silent otherwise.
    assert by_id["job-inflight"].marker_emitted is False
    assert by_id["job-landed"].marker_emitted is False
    assert by_id["job-lost"].marker_emitted is True
    assert len(recorder.calls) == 1
    marker_class, context = recorder.calls[0]
    assert marker_class == BACKGROUND_PRIMITIVE_UNSTABLE_MARKER
    assert context["story_id"] == _LOST_STORY

    # The marker is greppable in the rendered status section.
    section = render_background_runs_section(roster)
    assert section.count(BACKGROUND_PRIMITIVE_UNSTABLE_MARKER) == 1
    assert _LOST_STORY in section


def test_reconcile_all_landed_is_silent(
    git_repo: pathlib.Path, marker_registry: MarkerClassRegistry
) -> None:
    recorder = _Recorder()
    probe = make_git_ground_truth_probe(repo_root=git_repo)
    roster = reconcile_background_runs(
        [
            {
                "id": "job-landed",
                "state": "completed",
                "prompt": f"/bmad-automation run {_LANDED_STORY} --foreground",
            }
        ],
        git_ground_truth_probe=probe,
        marker_recorder=recorder,
        marker_registry=marker_registry,
    )
    assert roster.runs[0].classification == "completed-confirmed"
    assert recorder.calls == []
