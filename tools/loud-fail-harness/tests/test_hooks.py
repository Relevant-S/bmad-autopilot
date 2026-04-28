"""Contract-coverage matrix for the three Story 2.7 hook scripts.

This docstring IS the contract-coverage checklist required by AC-7. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to stories 1.2-1.9 + 2.2-2.6).

subagent-stop.sh (AC-2, AC-3):
    [x] happy path: commit created with NFR-O6 tag                → test_subagent_stop_happy_path_creates_commit
    [x] commit message ends with [bmad-automation story/<id>]      → test_subagent_stop_appends_commit_tag_per_nfr_o6
    [x] non-Dev dispatched_specialist → exit 0, no commit          → test_subagent_stop_no_op_on_non_dev_dispatched_specialist
    [x] missing proposed_commit_message → exit 1                   → test_subagent_stop_exits_one_on_missing_proposed_commit_message
    [x] non-empty scope_expanded_to → exit 1, scope-assertion-violation, no commit → test_subagent_stop_exits_one_on_nonempty_scope_expanded_to
    [x] HEAD branch != run-state.branch_name → exit 1              → test_subagent_stop_exits_one_on_branch_mismatch
    [x] trunk branch in run-state → exit 1                          → test_subagent_stop_exits_one_on_trunk_branch_in_run_state

stop.sh (AC-4):
    [x] writes bundle to documented path with shape                → test_stop_writes_walking_skeleton_bundle_to_documented_path
    [x] mkdir -p creates parent directories idempotently           → test_stop_creates_parent_directories_idempotently
    [x] bundle includes walking-skeleton-bundle HTML anchor        → test_stop_bundle_content_includes_walking_skeleton_anchor

session-start.sh (AC-5):
    [x] byte-stable verbatim 5-line literal stub                   → test_session_start_is_byte_stable_literal_stub
    [x] exit 0 on any invocation shape                             → test_session_start_exits_zero_on_any_invocation
    [x] count_effective_lines == 1                                 → test_session_start_effective_line_count_is_one

Cross-hook structural invariants (AC-1):
    [x] hooks/ contains exactly the canonical three filenames      → test_hooks_directory_contains_exactly_three_files
    [x] all three hooks executable                                  → test_all_three_hooks_are_executable
    [x] all three hooks LF line endings                             → test_all_three_hooks_have_lf_line_endings
    [x] all three hooks start with `#!/usr/bin/env bash`            → test_all_three_hooks_start_with_env_bash_shebang
"""

from __future__ import annotations

import os
import pathlib
import subprocess

import pytest

from loud_fail_harness.hook_budget_gate import count_effective_lines


# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #


CANONICAL_HOOK_FILENAMES = {"subagent-stop.sh", "stop.sh", "session-start.sh"}

SESSION_START_VERBATIM = (
    "#!/usr/bin/env bash\n"
    "# Stub: full SessionStart reattachment lands in Epic 8 (FR46, Story 8.1).\n"
    "# Until then, after a session restart, run /bmad-automation status to see\n"
    "# in-flight stories. Resume capability arrives in Epic 8.\n"
    "exit 0\n"
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


def _hooks_dir() -> pathlib.Path:
    """Resolve the canonical hooks/ directory at fixture-time only."""
    from loud_fail_harness._shared import find_repo_root

    return find_repo_root() / "hooks"


@pytest.fixture(scope="function")
def hooks_dir() -> pathlib.Path:
    return _hooks_dir()


@pytest.fixture(scope="function")
def fixture_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """tmp_path-rooted git repo on the per-story branch with deterministic identity."""
    _run_git("init", "-b", "main", cwd=tmp_path)
    _run_git("config", "user.email", "test@bmad-automation.local", cwd=tmp_path)
    _run_git("config", "user.name", "BMAD Test", cwd=tmp_path)
    _run_git("config", "commit.gpgsign", "false", cwd=tmp_path)
    (tmp_path / "README.md").write_text("# initial\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=tmp_path)
    _run_git("commit", "-m", "initial", cwd=tmp_path)
    _run_git("checkout", "-b", "bmad-automation/story/2-7-test", cwd=tmp_path)
    return tmp_path


def _write_run_state(
    repo: pathlib.Path,
    *,
    story_id: str = "2-7-test",
    branch_name: str = "bmad-automation/story/2-7-test",
    current_state: str = "review",
    dispatched_specialist: str | None = "dev",
    proposed_commit_message: str | None = "feat: walking-skeleton commit",
    scope_expanded_to: list[str] | None = None,
) -> pathlib.Path:
    """Synthesize _bmad/automation/run-state.yaml under ``repo``."""
    rs_dir = repo / "_bmad" / "automation"
    rs_dir.mkdir(parents=True, exist_ok=True)
    rs = rs_dir / "run-state.yaml"
    if dispatched_specialist is None:
        spec_line = "dispatched_specialist: null\n"
    else:
        spec_line = f"dispatched_specialist: {dispatched_specialist}\n"
    if proposed_commit_message is None and (scope_expanded_to is None):
        envelope = "last_envelope: null\n"
    else:
        msg_line = (
            "" if proposed_commit_message is None
            else f"  proposed_commit_message: {proposed_commit_message!r}\n"
        )
        scope_items = scope_expanded_to or []
        scope_line = "  scope_expanded_to: [" + ",".join(repr(p) for p in scope_items) + "]\n"
        envelope = "last_envelope:\n  status: green\n  rationale: x\n" + msg_line + scope_line
    rs.write_text(
        f"schema_version: '1.0'\n"
        f"story_id: {story_id}\n"
        f"run_id: r1\n"
        f"current_state: {current_state}\n"
        f"branch_name: {branch_name}\n"
        + spec_line
        + envelope
        + "retry_history: []\n"
        + "active_markers: []\n"
        + "cost_to_date_by_specialist: {}\n"
        + "pending_qa_dispatch_payload: null\n",
        encoding="utf-8",
    )
    return rs


def _invoke_hook(hook_path: pathlib.Path, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(hook_path)],
        cwd=cwd,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


# --------------------------------------------------------------------------- #
# subagent-stop.sh                                                            #
# --------------------------------------------------------------------------- #


def test_subagent_stop_happy_path_creates_commit(fixture_repo: pathlib.Path, hooks_dir: pathlib.Path) -> None:
    _write_run_state(fixture_repo, proposed_commit_message="feat: test commit")
    result = _invoke_hook(hooks_dir / "subagent-stop.sh", fixture_repo)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    log = _run_git("log", "-1", "--format=%s", cwd=fixture_repo)
    assert log.stdout.strip() == "feat: test commit [bmad-automation story/2-7-test]"


def test_subagent_stop_appends_commit_tag_per_nfr_o6(fixture_repo: pathlib.Path, hooks_dir: pathlib.Path) -> None:
    _write_run_state(fixture_repo, story_id="9-9-foo", proposed_commit_message="chore: x")
    result = _invoke_hook(hooks_dir / "subagent-stop.sh", fixture_repo)
    assert result.returncode == 0
    log = _run_git("log", "-1", "--format=%s", cwd=fixture_repo)
    assert log.stdout.strip().endswith("[bmad-automation story/9-9-foo]")


def test_subagent_stop_no_op_on_non_dev_dispatched_specialist(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    _write_run_state(fixture_repo, dispatched_specialist="review-bmad")
    initial_head = _run_git("rev-parse", "HEAD", cwd=fixture_repo).stdout.strip()
    result = _invoke_hook(hooks_dir / "subagent-stop.sh", fixture_repo)
    assert result.returncode == 0
    final_head = _run_git("rev-parse", "HEAD", cwd=fixture_repo).stdout.strip()
    assert initial_head == final_head, "no-op must not create a commit"


def test_subagent_stop_exits_one_on_missing_proposed_commit_message(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    _write_run_state(fixture_repo, proposed_commit_message=None)
    initial_head = _run_git("rev-parse", "HEAD", cwd=fixture_repo).stdout.strip()
    result = _invoke_hook(hooks_dir / "subagent-stop.sh", fixture_repo)
    assert result.returncode == 1
    assert "missing proposed_commit_message" in result.stderr
    final_head = _run_git("rev-parse", "HEAD", cwd=fixture_repo).stdout.strip()
    assert initial_head == final_head


def test_subagent_stop_exits_one_on_nonempty_scope_expanded_to(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    _write_run_state(
        fixture_repo,
        proposed_commit_message="feat: x",
        scope_expanded_to=["src/foo.py"],
    )
    initial_head = _run_git("rev-parse", "HEAD", cwd=fixture_repo).stdout.strip()
    result = _invoke_hook(hooks_dir / "subagent-stop.sh", fixture_repo)
    assert result.returncode == 1
    assert "subagent-stop: scope-assertion-violation" in result.stderr
    assert "Story 5.4" in result.stderr
    final_head = _run_git("rev-parse", "HEAD", cwd=fixture_repo).stdout.strip()
    assert initial_head == final_head


def test_subagent_stop_exits_one_on_branch_mismatch(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    _write_run_state(fixture_repo, branch_name="bmad-automation/story/9-9-other")
    result = _invoke_hook(hooks_dir / "subagent-stop.sh", fixture_repo)
    assert result.returncode == 1
    assert "branch mismatch" in result.stderr


def test_subagent_stop_exits_one_on_trunk_branch_in_run_state(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    _write_run_state(fixture_repo, branch_name="main")
    result = _invoke_hook(hooks_dir / "subagent-stop.sh", fixture_repo)
    assert result.returncode == 1
    assert "trunk branch" in result.stderr


# --------------------------------------------------------------------------- #
# stop.sh                                                                     #
# --------------------------------------------------------------------------- #


def test_stop_writes_walking_skeleton_bundle_to_documented_path(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    _write_run_state(fixture_repo, story_id="2-7-test", current_state="done")
    result = _invoke_hook(hooks_dir / "stop.sh", fixture_repo)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    bundles_dir = fixture_repo / "_bmad-output" / "pr-bundles" / "2-7-test"
    files = list(bundles_dir.glob("*.md"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert body.startswith("# PR bundle — story 2-7-test")
    assert "Branch: bmad-automation/story/2-7-test" in body
    assert "Final state: done" in body
    assert "## ⚠️ Walking Skeleton Mode" in body


def test_stop_creates_parent_directories_idempotently(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    _write_run_state(fixture_repo, story_id="2-7-idem")
    # Pre-create the directory; mkdir -p must remain idempotent.
    (fixture_repo / "_bmad-output" / "pr-bundles" / "2-7-idem").mkdir(parents=True)
    result = _invoke_hook(hooks_dir / "stop.sh", fixture_repo)
    assert result.returncode == 0


def test_stop_bundle_content_includes_walking_skeleton_anchor(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    _write_run_state(fixture_repo, story_id="2-7-anchor")
    result = _invoke_hook(hooks_dir / "stop.sh", fixture_repo)
    assert result.returncode == 0
    bundle = next((fixture_repo / "_bmad-output" / "pr-bundles" / "2-7-anchor").glob("*.md"))
    assert "<!-- walking-skeleton-bundle: marker_class -->" in bundle.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# session-start.sh                                                            #
# --------------------------------------------------------------------------- #


def test_session_start_is_byte_stable_literal_stub(hooks_dir: pathlib.Path) -> None:
    body = (hooks_dir / "session-start.sh").read_text(encoding="utf-8")
    assert body == SESSION_START_VERBATIM


def test_session_start_exits_zero_on_any_invocation(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    hook = hooks_dir / "session-start.sh"
    # No-arg invocation.
    r = _invoke_hook(hook, fixture_repo)
    assert r.returncode == 0
    # One-arg invocation.
    r2 = subprocess.run(
        ["bash", str(hook), "some-arg"],
        cwd=fixture_repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert r2.returncode == 0
    # stdin-fed invocation.
    r3 = subprocess.run(
        ["bash", str(hook)],
        cwd=fixture_repo,
        input="some stdin content",
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert r3.returncode == 0


def test_session_start_effective_line_count_is_one(hooks_dir: pathlib.Path) -> None:
    assert count_effective_lines(hooks_dir / "session-start.sh") == 1


# --------------------------------------------------------------------------- #
# Cross-hook structural invariants                                            #
# --------------------------------------------------------------------------- #


def test_hooks_directory_contains_exactly_three_files(hooks_dir: pathlib.Path) -> None:
    entries = {p.name for p in hooks_dir.glob("*")}
    assert entries == CANONICAL_HOOK_FILENAMES


def test_all_three_hooks_are_executable(hooks_dir: pathlib.Path) -> None:
    for name in CANONICAL_HOOK_FILENAMES:
        path = hooks_dir / name
        assert path.stat().st_mode & 0o111 != 0, f"{name} is not executable"


def test_all_three_hooks_have_lf_line_endings(hooks_dir: pathlib.Path) -> None:
    for name in CANONICAL_HOOK_FILENAMES:
        raw = (hooks_dir / name).read_bytes()
        assert b"\r" not in raw, f"{name} contains CR characters"


def test_all_three_hooks_start_with_env_bash_shebang(hooks_dir: pathlib.Path) -> None:
    for name in CANONICAL_HOOK_FILENAMES:
        first_line = (hooks_dir / name).read_text(encoding="utf-8").splitlines()[0]
        assert first_line == "#!/usr/bin/env bash", f"{name} has wrong shebang: {first_line!r}"
