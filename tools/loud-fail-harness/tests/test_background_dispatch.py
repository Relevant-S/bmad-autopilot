"""Unit tests for :mod:`loud_fail_harness.background_dispatch` — Story 21.2 / FR-P2-7.

Covers the daemon-backed dispatch seam (AC-5: command builder, flag-gated
``dispatch_run``, re-entrancy guard) and the status reconciliation + loud-fail
marker emission (AC-6: ``reconcile_background_runs`` classification +
``background-primitive-unstable`` emission on the unconfirmable-on-resume path,
Pattern-5 validate-first). Every external-primitive touchpoint is an injected
seam — no live daemon, no real ``claude --bg`` spawned.
"""

from __future__ import annotations

import pathlib
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from pydantic import ValidationError

from loud_fail_harness.background_dispatch import (
    BACKGROUND_PRIMITIVE_UNSTABLE_MARKER,
    BACKGROUND_REENTRY_FLAG,
    BackgroundAgentSession,
    GitGroundTruth,
    build_background_dispatch_command,
    build_background_dispatch_confirmation,
    decide_dispatch_mode,
    dispatch_run,
    is_background_reentry,
    make_git_ground_truth_probe,
    parse_background_agent_sessions,
    reconcile_background_runs,
    render_background_runs_section,
)
from loud_fail_harness.branch_lifecycle import _branch_name_for_story
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
    load_marker_class_registry,
)

_STORY_ID = "21-2"


def _live_registry() -> MarkerClassRegistry:
    """The real taxonomy registry (carries background-primitive-unstable)."""
    return load_marker_class_registry()


class _Recorder:
    """List-appender MarkerRecorder stub capturing (marker_class, context)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    def __call__(self, marker_class: str, context: Mapping[str, Any]) -> None:
        self.calls.append((marker_class, dict(context)))


# --------------------------------------------------------------------------- #
# AC-5 — command builder + re-entrancy + dispatch gate                         #
# --------------------------------------------------------------------------- #


def test_build_command_is_well_formed_claude_bg_argv() -> None:
    cmd = build_background_dispatch_command(_STORY_ID, project_root="/proj/root")
    assert cmd[0] == "claude"
    assert cmd[1] == "--bg"
    assert "--add-dir" in cmd
    assert "/proj/root" in cmd
    # The prompt re-enters the run command carrying the re-entrancy sentinel.
    assert cmd[-1] == f"/bmad-automation run {_STORY_ID} {BACKGROUND_REENTRY_FLAG}"
    # NOT the in-session Agent path: the argv is the daemon `claude --bg` surface.
    assert "run_in_background" not in " ".join(cmd)


def test_build_command_honors_executable_and_extra_args() -> None:
    cmd = build_background_dispatch_command(
        _STORY_ID,
        project_root="/p",
        claude_executable="/usr/local/bin/claude",
        extra_args=("--permission-mode", "bypassPermissions"),
    )
    assert cmd[0] == "/usr/local/bin/claude"
    assert "--permission-mode" in cmd
    assert "bypassPermissions" in cmd


def test_build_command_hardens_story_id() -> None:
    with pytest.raises(ValueError):
        build_background_dispatch_command("bad\nid", project_root="/p")


def test_confirmation_points_at_status() -> None:
    msg = build_background_dispatch_confirmation(_STORY_ID)
    assert "/bmad-automation status" in msg
    assert _STORY_ID in msg


def test_is_background_reentry() -> None:
    assert is_background_reentry(["run", _STORY_ID, BACKGROUND_REENTRY_FLAG]) is True
    assert is_background_reentry(["run", _STORY_ID]) is False


@pytest.mark.parametrize(
    "bg,reentry,expected",
    [
        (True, False, "background"),
        (True, True, "foreground"),
        (False, False, "foreground"),
        (False, True, "foreground"),
    ],
)
def test_decide_dispatch_mode(bg: bool, reentry: bool, expected: str) -> None:
    assert (
        decide_dispatch_mode(background_execution=bg, background_reentry=reentry)
        == expected
    )


def test_dispatch_run_background_does_not_take_foreground_loop() -> None:
    launched: list[Sequence[str]] = []
    fg_calls: list[int] = []

    result = dispatch_run(
        _STORY_ID,
        project_root="/proj",
        background_execution=True,
        launcher=lambda cmd: launched.append(cmd) or "launched",
        foreground_runner=lambda: fg_calls.append(1),
    )

    assert result.mode == "background"
    assert result.command is not None and result.command[:2] == ("claude", "--bg")
    assert result.confirmation is not None
    assert result.launch_result == "launched"
    assert len(launched) == 1
    # The non-blocking-dispatch property: the inline foreground loop is NOT run.
    assert fg_calls == []


def test_dispatch_run_flag_off_is_bit_identical_foreground() -> None:
    launched: list[Sequence[str]] = []
    fg_calls: list[int] = []

    result = dispatch_run(
        _STORY_ID,
        project_root="/proj",
        background_execution=False,
        launcher=lambda cmd: launched.append(cmd),
        foreground_runner=lambda: fg_calls.append(1) or "foreground-result",
    )

    assert result.mode == "foreground"
    assert result.command is None
    assert result.foreground_result == "foreground-result"
    # No background command built; the launcher is never invoked.
    assert launched == []
    assert fg_calls == [1]


def test_dispatch_run_reentrant_child_runs_foreground() -> None:
    launched: list[Sequence[str]] = []
    fg_calls: list[int] = []

    result = dispatch_run(
        _STORY_ID,
        project_root="/proj",
        background_execution=True,
        background_reentry=True,
        launcher=lambda cmd: launched.append(cmd),
        foreground_runner=lambda: fg_calls.append(1),
    )

    assert result.mode == "foreground"
    assert launched == []
    assert fg_calls == [1]


# --------------------------------------------------------------------------- #
# AC-6 — parse + reconcile + marker emission                                   #
# --------------------------------------------------------------------------- #


def test_parse_sessions_extracts_story_id_from_prompt() -> None:
    sessions = parse_background_agent_sessions(
        [
            {
                "id": "job-1",
                "state": "running",
                "prompt": "/bmad-automation run 21-2 --foreground",
            },
            {"id": "job-2", "state": "completed", "story_id": "18-4"},
            {"id": "", "state": "running"},  # malformed → skipped
            {"state": "running"},  # no id → skipped
        ]
    )
    assert [s.session_id for s in sessions] == ["job-1", "job-2"]
    assert sessions[0].story_id == "21-2"
    assert sessions[1].story_id == "18-4"


def test_background_agent_session_hardens_story_id() -> None:
    BackgroundAgentSession(session_id="j", state="running", story_id="21-2")
    with pytest.raises(ValidationError):
        BackgroundAgentSession(session_id="j", state="running", story_id="x\ny")


def _probe_from_map(
    mapping: Mapping[str, GitGroundTruth],
) -> Any:
    def _probe(session: BackgroundAgentSession) -> GitGroundTruth:
        return mapping.get(
            session.session_id,
            GitGroundTruth(branch_exists=False, has_landed_commits=False),
        )

    return _probe


def test_reconcile_in_flight_is_silent() -> None:
    rec = _Recorder()
    roster = reconcile_background_runs(
        [{"id": "job-1", "state": "running", "story_id": "21-2"}],
        git_ground_truth_probe=_probe_from_map({}),
        marker_recorder=rec,
        marker_registry=_live_registry(),
    )
    assert roster.runs[0].classification == "in-flight"
    assert roster.runs[0].marker_emitted is False
    assert rec.calls == []


def test_reconcile_completed_confirmed_is_silent() -> None:
    rec = _Recorder()
    probe = _probe_from_map(
        {"job-1": GitGroundTruth(branch_exists=True, has_landed_commits=True)}
    )
    roster = reconcile_background_runs(
        [{"id": "job-1", "state": "completed", "story_id": "21-2"}],
        git_ground_truth_probe=probe,
        marker_recorder=rec,
        marker_registry=_live_registry(),
    )
    assert roster.runs[0].classification == "completed-confirmed"
    assert roster.runs[0].marker_emitted is False
    assert rec.calls == []


def test_reconcile_unconfirmable_emits_marker() -> None:
    rec = _Recorder()
    # Completed per the agents registry, but git ground-truth shows no landed
    # branch — the #63023 silent-loss signature.
    probe = _probe_from_map(
        {"job-1": GitGroundTruth(branch_exists=False, has_landed_commits=False)}
    )
    roster = reconcile_background_runs(
        [{"id": "job-1", "state": "completed", "story_id": "21-2"}],
        git_ground_truth_probe=probe,
        marker_recorder=rec,
        marker_registry=_live_registry(),
    )
    assert roster.runs[0].classification == "unconfirmable"
    assert roster.runs[0].marker_emitted is True
    assert len(rec.calls) == 1
    marker_class, context = rec.calls[0]
    assert marker_class == BACKGROUND_PRIMITIVE_UNSTABLE_MARKER
    assert context["story_id"] == "21-2"
    assert context["session_id"] == "job-1"


def test_reconcile_unknown_story_id_is_unconfirmable() -> None:
    rec = _Recorder()
    roster = reconcile_background_runs(
        [{"id": "job-x", "state": "completed"}],  # no story_id recoverable
        git_ground_truth_probe=_probe_from_map({}),
        marker_recorder=rec,
        marker_registry=_live_registry(),
    )
    assert roster.runs[0].classification == "unconfirmable"
    assert rec.calls[0][1]["story_id"] == "<unknown>"


def test_reconcile_failed_state_is_unconfirmable() -> None:
    rec = _Recorder()
    roster = reconcile_background_runs(
        [{"id": "job-1", "state": "failed", "story_id": "21-2"}],
        git_ground_truth_probe=_probe_from_map(
            {"job-1": GitGroundTruth(branch_exists=True, has_landed_commits=True)}
        ),
        marker_recorder=rec,
        marker_registry=_live_registry(),
    )
    # "failed" is not in _COMPLETED_STATES — the daemon reported explicit failure.
    # Even if git shows a landed branch, a failed session is unconfirmable: the
    # branch may be from a prior attempt or partial pre-failure work.
    assert roster.runs[0].classification == "unconfirmable"
    assert roster.runs[0].marker_emitted is True
    assert len(rec.calls) == 1
    assert rec.calls[0][0] == BACKGROUND_PRIMITIVE_UNSTABLE_MARKER


def test_reconcile_validate_first_raises_on_empty_registry() -> None:
    rec = _Recorder()
    with pytest.raises(UnknownMarkerClass):
        reconcile_background_runs(
            [{"id": "job-1", "state": "completed", "story_id": "21-2"}],
            git_ground_truth_probe=_probe_from_map({}),
            marker_recorder=rec,
            marker_registry=MarkerClassRegistry(marker_classes=frozenset()),
        )
    # Pattern 5 defence-in-depth: rejection fires BEFORE the recorder is called.
    assert rec.calls == []


def test_render_section_marks_unconfirmable_runs() -> None:
    rec = _Recorder()
    roster = reconcile_background_runs(
        [
            {"id": "job-1", "state": "running", "story_id": "21-2"},
            {"id": "job-2", "state": "completed", "story_id": "18-4"},
        ],
        git_ground_truth_probe=_probe_from_map(
            {"job-2": GitGroundTruth(branch_exists=False, has_landed_commits=False)}
        ),
        marker_recorder=rec,
        marker_registry=_live_registry(),
    )
    section = render_background_runs_section(roster)
    assert "## Background runs" in section
    assert "job-1" in section and "job-2" in section
    # The marker is greppable on the unconfirmable run only.
    assert BACKGROUND_PRIMITIVE_UNSTABLE_MARKER in section
    assert section.count(BACKGROUND_PRIMITIVE_UNSTABLE_MARKER) == 1


def test_render_section_empty_roster() -> None:
    from loud_fail_harness.background_dispatch import BackgroundRunRoster

    section = render_background_runs_section(BackgroundRunRoster(runs=()))
    assert "no background runs registered" in section


# --------------------------------------------------------------------------- #
# Default production git-ground-truth probe (read-only git)                    #
# --------------------------------------------------------------------------- #


def _run_git(*args: str, cwd: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def test_make_git_probe_against_real_repo(tmp_path: Any) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    repo_str = str(repo)
    _run_git("init", "-b", "main", cwd=repo_str)
    _run_git("config", "user.email", "t@t.local", cwd=repo_str)
    _run_git("config", "user.name", "T", cwd=repo_str)
    _run_git("config", "commit.gpgsign", "false", cwd=repo_str)
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=repo_str)
    _run_git("commit", "-m", "init", cwd=repo_str)
    # Create the per-story branch with a commit (landed work).
    branch = _branch_name_for_story(_STORY_ID)
    _run_git("checkout", "-b", branch, cwd=repo_str)
    (repo / "work.txt").write_text("done\n", encoding="utf-8")
    _run_git("add", "work.txt", cwd=repo_str)
    _run_git("commit", "-m", "story work", cwd=repo_str)

    probe = make_git_ground_truth_probe(repo_root=repo)

    landed = probe(
        BackgroundAgentSession(session_id="j", state="completed", story_id=_STORY_ID)
    )
    assert landed.branch_exists is True
    assert landed.has_landed_commits is True

    # A story with no branch → not confirmed.
    absent = probe(
        BackgroundAgentSession(session_id="j", state="completed", story_id="99-9")
    )
    assert absent.branch_exists is False
    assert absent.has_landed_commits is False

    # No story_id → not confirmed (cannot locate work).
    unknown = probe(BackgroundAgentSession(session_id="j", state="completed"))
    assert unknown.branch_exists is False


def test_make_git_probe_empty_story_branch_not_confirmed(tmp_path: pathlib.Path) -> None:
    """A per-story branch freshly cut off main with zero story commits must NOT
    confirm as landed.  This guards against the ``git rev-list --count <branch>``
    false-confirm (the old code counted full ancestry; the fix uses
    ``main..<branch>`` so an empty branch reports 0 story-specific commits).
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    repo_str = str(repo)
    _run_git("init", "-b", "main", cwd=repo_str)
    _run_git("config", "user.email", "t@t.local", cwd=repo_str)
    _run_git("config", "user.name", "T", cwd=repo_str)
    _run_git("config", "commit.gpgsign", "false", cwd=repo_str)
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=repo_str)
    _run_git("commit", "-m", "init", cwd=repo_str)
    # Create the per-story branch off main but add NO new commit.
    branch = _branch_name_for_story(_STORY_ID)
    _run_git("checkout", "-b", branch, cwd=repo_str)

    probe = make_git_ground_truth_probe(repo_root=repo)
    result = probe(
        BackgroundAgentSession(session_id="j", state="completed", story_id=_STORY_ID)
    )
    # Branch exists but carries no story-specific commits → NOT confirmed.
    assert result.branch_exists is True
    assert result.has_landed_commits is False
