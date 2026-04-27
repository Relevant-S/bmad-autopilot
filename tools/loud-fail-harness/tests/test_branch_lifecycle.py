"""Contract-coverage matrix for the per-story branch lifecycle module
(story 2.3).

This docstring IS the contract-coverage checklist required by AC-6.
Reviewers verify every row maps to at least one passing test in this
module. The matrix is review-enforced, NOT CI-enforced (parallel to
1.2 / 1.3 / 1.4 / 1.5 / 1.6 / 1.7 / 1.8 / 1.9 / 1.10a / 1.10b / 1.12b /
2.1 / 2.2 AC discipline).

Branch-creation happy path (AC-1, AC-2):
    [x] clean tree → new branch is created and checked out          → test_create_story_branch_creates_new_branch_on_clean_tree
    [x] previous_branch field captures HEAD before checkout         → test_create_story_branch_captures_previous_branch
    [x] BranchLifecycleResult.repo_root reflects resolved path      → test_create_story_branch_result_carries_repo_root

Idempotency on existing branch (AC-1, AC-6; NFR-R2):
    [x] existing branch → checkout (not re-create)                  → test_create_story_branch_checks_out_existing_branch_idempotently
    [x] existing branch → result.created is False                   → test_create_story_branch_existing_branch_created_false

Halt-on-unclean-tree (AC-3):
    [x] live git status detects modified file → halt                → test_create_story_branch_halts_on_unclean_tree
    [x] diagnostic message includes path count + remediation        → test_create_story_branch_unclean_diagnostic_includes_path_count
    [x] no git checkout invoked when probe says unclean             → test_create_story_branch_does_not_invoke_git_when_unclean
    [x] uncommitted_paths attribute populated from probe result     → test_create_story_branch_unclean_exception_carries_paths

Trunk-allowlist rejection (AC-2):
    [x] story_id derives "main" → TrunkBranchWriteRejected           → test_create_story_branch_rejects_main_in_default_allowlist
    [x] story_id="main" does NOT raise (exact-string-match verify)   → test_create_story_branch_story_id_main_does_not_match_default_allowlist
    [x] story_id derives "master" → TrunkBranchWriteRejected         → test_create_story_branch_rejects_master_in_default_allowlist
    [x] story_id derives "trunk" → TrunkBranchWriteRejected          → test_create_story_branch_rejects_trunk_in_default_allowlist
    [x] custom allowlist with "develop" rejects "develop" branch    → test_create_story_branch_respects_custom_allowlist
    [x] empty allowlist allows operation on any branch              → test_create_story_branch_empty_allowlist_allows_any
    [x] no git command invoked on trunk-allowlist match             → test_create_story_branch_no_git_when_trunk_rejected
    [x] TrunkBranchWriteRejected.attempted_branch carries name      → test_trunk_rejected_exception_carries_branch_name

Operation-scope lockdown (AC-2 absence verification):
    [x] no `git push` invocation in any code path                   → test_create_story_branch_does_not_invoke_git_push
    [x] no `git branch -D` / `--delete` / `-d` invocation           → test_create_story_branch_does_not_invoke_git_branch_delete
    [x] no `git rebase` / `git reset --hard` / `git clean`          → test_create_story_branch_does_not_invoke_destructive_commands
    [x] no `git fetch` / `git pull` / `git merge` / `git remote`    → test_create_story_branch_does_not_invoke_remote_commands

API-shape (AC-1):
    [x] trunk_allowlist parameter is keyword-only + non-defaulted   → test_create_story_branch_keyword_only_trunk_allowlist
    [x] working_tree_probe parameter is keyword-only + non-defaulted→ test_create_story_branch_keyword_only_working_tree_probe
    [x] missing trunk_allowlist raises TypeError                    → test_create_story_branch_missing_trunk_allowlist_typeerror
    [x] missing working_tree_probe raises TypeError                 → test_create_story_branch_missing_probe_typeerror
    [x] __all__ exports public surface                              → test_module_all_exports

Working-tree probe factory (AC-3):
    [x] default probe parses porcelain output → uncommitted_paths   → test_default_working_tree_probe_parses_porcelain_output
    [x] default probe returns clean=True for clean repo            → test_default_working_tree_probe_returns_clean_for_clean_repo
    [x] default probe surfaces reason on unclean                    → test_default_working_tree_probe_unclean_reason_format

Branch-name derivation (AC-1; docs/git-hygiene.md convention):
    [x] story_id "2-3" derives "bmad-automation/story/2-3"          → test_branch_name_derivation_uses_story_id
    [x] convention applies across multiple story-id shapes          → test_branch_name_derivation_multiple_story_ids

Marker-class linkage (AC-3, AC-4; sensor-not-advisor):
    [x] GitUncommittedWorkDetected.marker_class matches taxonomy    → test_uncommitted_marker_class_matches_taxonomy_entry
    [x] TrunkBranchWriteRejected.marker_class matches taxonomy      → test_trunk_marker_class_matches_taxonomy_entry

Frozen-tuple immutability (AC-1; Epic 1 retro Action #2):
    [x] WorkingTreeProbeResult is frozen (reassignment raises)      → test_working_tree_probe_result_is_frozen
    [x] BranchLifecycleResult is frozen (reassignment raises)       → test_branch_lifecycle_result_is_frozen
    [x] uncommitted_paths is tuple (no .append method)              → test_uncommitted_paths_is_tuple

Module discipline (AC-1; Epic 1 retro Action #1):
    [x] find_repo_root NOT called at module import time             → test_find_repo_root_not_called_at_import
    [x] repo_root=None resolves lazily via _default_repo_root()     → test_create_story_branch_repo_root_none_resolves_lazily

cause carries WorkingTreeProbeResult (D1 fix; AC-1 type contract):
    [x] GitUncommittedWorkDetected.cause is WorkingTreeProbeResult  → test_git_uncommitted_work_detected_cause_carries_probe_result
"""

from __future__ import annotations

import inspect
import pathlib
import subprocess
from collections.abc import Iterable
from typing import Any
from unittest import mock

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness import branch_lifecycle
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.branch_lifecycle import (
    DEFAULT_TRUNK_ALLOWLIST,
    BranchLifecycleResult,
    GitUncommittedWorkDetected,
    TrunkBranchWriteRejected,
    WorkingTreeProbe,
    WorkingTreeProbeResult,
    create_story_branch,
    default_working_tree_probe,
)
from loud_fail_harness.branch_lifecycle import _branch_name_for_story


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


def _run_git(*args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    """Invoke git in a tmp_path-rooted throwaway repo with deterministic
    user identity. Used by fixtures + assertions; never reaches the live
    repo."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture(scope="function")
def git_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """Bootstrap a tmp_path-rooted git repo with a single commit so HEAD
    is valid. The deterministic user identity prevents commit failures
    when global git config is absent (CI runners). Trunk is `main` to
    match the project's default; tests targeting non-`main` trunks set
    the trunk explicitly via `git checkout -b`."""
    _run_git("init", "-b", "main", cwd=tmp_path)
    _run_git("config", "user.email", "test@bmad-automation.local", cwd=tmp_path)
    _run_git("config", "user.name", "BMAD Test", cwd=tmp_path)
    _run_git("config", "commit.gpgsign", "false", cwd=tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("# initial commit\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=tmp_path)
    _run_git("commit", "-m", "initial", cwd=tmp_path)
    return tmp_path


@pytest.fixture(scope="function")
def git_repo_with_uncommitted_changes(git_repo: pathlib.Path) -> pathlib.Path:
    """Build on `git_repo` and add an unstaged modification so
    `git status --porcelain` returns one line."""
    readme = git_repo / "README.md"
    readme.write_text("# modified\n", encoding="utf-8")
    return git_repo


def _clean_probe() -> WorkingTreeProbeResult:
    return WorkingTreeProbeResult(clean=True)


def _unclean_probe_factory(
    paths: Iterable[str] = ("a.py", "b.py"),
) -> WorkingTreeProbe:
    paths_tuple = tuple(paths)

    def _probe() -> WorkingTreeProbeResult:
        return WorkingTreeProbeResult(
            clean=False,
            uncommitted_paths=paths_tuple,
            reason=f"{len(paths_tuple)} uncommitted path(s) detected",
        )

    return _probe


# --------------------------------------------------------------------------- #
# Branch-creation happy path (AC-1, AC-2)                                     #
# --------------------------------------------------------------------------- #


def test_create_story_branch_creates_new_branch_on_clean_tree(
    git_repo: pathlib.Path,
) -> None:
    result = create_story_branch(
        "2-3",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        working_tree_probe=_clean_probe,
        repo_root=git_repo,
    )
    assert result.branch_name == "bmad-automation/story/2-3"
    assert result.created is True
    head = _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=git_repo).stdout.strip()
    assert head == "bmad-automation/story/2-3"


def test_create_story_branch_captures_previous_branch(
    git_repo: pathlib.Path,
) -> None:
    result = create_story_branch(
        "2-3",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        working_tree_probe=_clean_probe,
        repo_root=git_repo,
    )
    assert result.previous_branch == "main"


def test_create_story_branch_result_carries_repo_root(
    git_repo: pathlib.Path,
) -> None:
    result = create_story_branch(
        "2-3",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        working_tree_probe=_clean_probe,
        repo_root=git_repo,
    )
    assert result.repo_root == git_repo


# --------------------------------------------------------------------------- #
# Idempotency on existing branch (AC-1, AC-6; NFR-R2)                         #
# --------------------------------------------------------------------------- #


def test_create_story_branch_checks_out_existing_branch_idempotently(
    git_repo: pathlib.Path,
) -> None:
    # Pre-create the branch.
    _run_git("checkout", "-b", "bmad-automation/story/2-3", cwd=git_repo)
    _run_git("checkout", "main", cwd=git_repo)
    pre_head = _run_git(
        "rev-parse", "bmad-automation/story/2-3", cwd=git_repo
    ).stdout.strip()

    result = create_story_branch(
        "2-3",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        working_tree_probe=_clean_probe,
        repo_root=git_repo,
    )
    head_after = _run_git(
        "rev-parse", "bmad-automation/story/2-3", cwd=git_repo
    ).stdout.strip()
    assert head_after == pre_head, "existing branch must NOT be re-created"
    assert result.branch_name == "bmad-automation/story/2-3"
    current = _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=git_repo).stdout.strip()
    assert current == "bmad-automation/story/2-3"


def test_create_story_branch_existing_branch_created_false(
    git_repo: pathlib.Path,
) -> None:
    _run_git("checkout", "-b", "bmad-automation/story/2-3", cwd=git_repo)
    _run_git("checkout", "main", cwd=git_repo)
    result = create_story_branch(
        "2-3",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        working_tree_probe=_clean_probe,
        repo_root=git_repo,
    )
    assert result.created is False


# --------------------------------------------------------------------------- #
# Halt-on-unclean-tree (AC-3)                                                 #
# --------------------------------------------------------------------------- #


def test_create_story_branch_halts_on_unclean_tree(
    git_repo_with_uncommitted_changes: pathlib.Path,
) -> None:
    repo = git_repo_with_uncommitted_changes
    probe = default_working_tree_probe(repo)
    with pytest.raises(GitUncommittedWorkDetected) as excinfo:
        create_story_branch(
            "2-3",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            working_tree_probe=probe,
            repo_root=repo,
        )
    assert "README.md" in " ".join(excinfo.value.uncommitted_paths)


def test_create_story_branch_unclean_diagnostic_includes_path_count(
    git_repo: pathlib.Path,
) -> None:
    probe = _unclean_probe_factory(paths=("a.py",))
    with pytest.raises(GitUncommittedWorkDetected) as excinfo:
        create_story_branch(
            "2-3",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            working_tree_probe=probe,
            repo_root=git_repo,
        )
    message = str(excinfo.value)
    assert message.startswith("Working tree has 1 uncommitted")
    assert "stash, commit, or abort" in message
    assert "docs/git-hygiene.md" in message


def test_create_story_branch_does_not_invoke_git_when_unclean(
    git_repo: pathlib.Path,
) -> None:
    probe = _unclean_probe_factory()
    with mock.patch.object(
        branch_lifecycle.subprocess, "run"
    ) as mock_run:
        with pytest.raises(GitUncommittedWorkDetected):
            create_story_branch(
                "2-3",
                trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
                working_tree_probe=probe,
                repo_root=git_repo,
            )
    # Probe is the injected stub, NOT the live `git status` — so when the
    # probe returns clean=False BEFORE any subprocess.run can fire from
    # within `create_story_branch`, the helper must NOT have invoked ANY
    # git command (not just checkout — NFR-R3 invariant: zero git calls).
    assert mock_run.call_count == 0, (
        f"helper invoked git despite unclean tree: {mock_run.call_args_list!r}"
    )


def test_create_story_branch_unclean_exception_carries_paths() -> None:
    probe = _unclean_probe_factory(paths=("a.py", "b.py", "c.py"))
    with pytest.raises(GitUncommittedWorkDetected) as excinfo:
        create_story_branch(
            "2-3",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            working_tree_probe=probe,
            # repo_root won't actually be touched; the halt fires before
            # any git invocation.
            repo_root=pathlib.Path("/nonexistent"),
        )
    assert excinfo.value.uncommitted_paths == ("a.py", "b.py", "c.py")
    assert excinfo.value.attempted_story_id == "2-3"


# --------------------------------------------------------------------------- #
# Trunk-allowlist rejection (AC-2)                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "trunk_name",
    ["main", "master", "trunk"],
)
def test_create_story_branch_rejects_trunk_in_default_allowlist(
    monkeypatch: pytest.MonkeyPatch, trunk_name: str
) -> None:
    """Generic parametrized version of the three rejection tests; named
    individually below for matrix readability."""
    monkeypatch.setattr(
        branch_lifecycle, "_branch_name_for_story", lambda _id: trunk_name
    )
    with pytest.raises(TrunkBranchWriteRejected) as excinfo:
        create_story_branch(
            "test",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            working_tree_probe=_clean_probe,
            repo_root=pathlib.Path("/nonexistent"),
        )
    assert excinfo.value.attempted_branch == trunk_name


def test_create_story_branch_rejects_main_in_default_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        branch_lifecycle, "_branch_name_for_story", lambda _id: "main"
    )
    with pytest.raises(TrunkBranchWriteRejected):
        create_story_branch(
            "test",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            working_tree_probe=_clean_probe,
            repo_root=pathlib.Path("/nonexistent"),
        )


def test_create_story_branch_story_id_main_does_not_match_default_allowlist(
    git_repo: pathlib.Path,
) -> None:
    """AC-6 exact-string-match verification: story_id="main" derives the branch
    name "bmad-automation/story/main", which is NOT in DEFAULT_TRUNK_ALLOWLIST.
    The allowlist comparison is exact-string-match (per AC-2), NOT substring or
    prefix match — the `bmad-automation/story/` prefix prevents false positives.
    """
    result = create_story_branch(
        "main",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        working_tree_probe=_clean_probe,
        repo_root=git_repo,
    )
    assert result.branch_name == "bmad-automation/story/main"
    assert result.created is True


def test_create_story_branch_rejects_master_in_default_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        branch_lifecycle, "_branch_name_for_story", lambda _id: "master"
    )
    with pytest.raises(TrunkBranchWriteRejected):
        create_story_branch(
            "test",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            working_tree_probe=_clean_probe,
            repo_root=pathlib.Path("/nonexistent"),
        )


def test_create_story_branch_rejects_trunk_in_default_allowlist_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        branch_lifecycle, "_branch_name_for_story", lambda _id: "trunk"
    )
    with pytest.raises(TrunkBranchWriteRejected):
        create_story_branch(
            "test",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            working_tree_probe=_clean_probe,
            repo_root=pathlib.Path("/nonexistent"),
        )


def test_create_story_branch_respects_custom_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        branch_lifecycle, "_branch_name_for_story", lambda _id: "develop"
    )
    with pytest.raises(TrunkBranchWriteRejected) as excinfo:
        create_story_branch(
            "test",
            trunk_allowlist=("develop", "release"),
            working_tree_probe=_clean_probe,
            repo_root=pathlib.Path("/nonexistent"),
        )
    assert excinfo.value.attempted_branch == "develop"


def test_create_story_branch_empty_allowlist_allows_any(
    git_repo: pathlib.Path,
) -> None:
    """With trunk_allowlist=() the helper accepts ANY derived branch
    name — verifies the allowlist is the SOLE rejection mechanism (no
    hardcoded fallback)."""
    result = create_story_branch(
        "2-3",
        trunk_allowlist=(),
        working_tree_probe=_clean_probe,
        repo_root=git_repo,
    )
    assert result.branch_name == "bmad-automation/story/2-3"
    assert result.created is True


def test_create_story_branch_no_git_when_trunk_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        branch_lifecycle, "_branch_name_for_story", lambda _id: "main"
    )
    with mock.patch.object(branch_lifecycle.subprocess, "run") as mock_run:
        with pytest.raises(TrunkBranchWriteRejected):
            create_story_branch(
                "test",
                trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
                working_tree_probe=_clean_probe,
                repo_root=pathlib.Path("/nonexistent"),
            )
    assert mock_run.call_count == 0, (
        "no git command must run when trunk-allowlist rejects the branch"
    )


def test_trunk_rejected_exception_carries_branch_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        branch_lifecycle, "_branch_name_for_story", lambda _id: "release"
    )
    with pytest.raises(TrunkBranchWriteRejected) as excinfo:
        create_story_branch(
            "test",
            trunk_allowlist=("release",),
            working_tree_probe=_clean_probe,
            repo_root=pathlib.Path("/nonexistent"),
        )
    assert excinfo.value.attempted_branch == "release"
    assert excinfo.value.attempted_story_id == "test"
    assert "release" in str(excinfo.value)
    assert "NFR-S3" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# Operation-scope lockdown (AC-2 absence verification)                        #
# --------------------------------------------------------------------------- #


def _git_subcommand_args(call: Any) -> list[str]:
    args_list = call.args[0] if call.args else call.kwargs.get("args", [])
    return list(args_list) if args_list else []


def _all_git_invocations(mock_run: mock.MagicMock) -> list[list[str]]:
    return [
        _git_subcommand_args(call)
        for call in mock_run.call_args_list
        if _git_subcommand_args(call) and _git_subcommand_args(call)[0] == "git"
    ]


def test_create_story_branch_does_not_invoke_git_push(
    git_repo: pathlib.Path,
) -> None:
    real_run = subprocess.run
    captured: list[list[str]] = []

    def _capturing_run(*args: Any, **kwargs: Any) -> Any:
        if args and isinstance(args[0], list):
            captured.append(list(args[0]))
        return real_run(*args, **kwargs)

    with mock.patch.object(branch_lifecycle.subprocess, "run", side_effect=_capturing_run):
        create_story_branch(
            "2-3",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            working_tree_probe=_clean_probe,
            repo_root=git_repo,
        )

    for invocation in captured:
        assert not (invocation[:2] == ["git", "push"]), (
            f"git push invoked: {invocation!r}"
        )


def test_create_story_branch_does_not_invoke_git_branch_delete(
    git_repo: pathlib.Path,
) -> None:
    real_run = subprocess.run
    captured: list[list[str]] = []

    def _capturing_run(*args: Any, **kwargs: Any) -> Any:
        if args and isinstance(args[0], list):
            captured.append(list(args[0]))
        return real_run(*args, **kwargs)

    with mock.patch.object(branch_lifecycle.subprocess, "run", side_effect=_capturing_run):
        create_story_branch(
            "2-3",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            working_tree_probe=_clean_probe,
            repo_root=git_repo,
        )

    forbidden_branch_flags = {"-D", "--delete", "-d"}
    for invocation in captured:
        if invocation[:2] == ["git", "branch"] and len(invocation) > 2:
            assert invocation[2] not in forbidden_branch_flags, (
                f"git branch delete invoked: {invocation!r}"
            )


def test_create_story_branch_does_not_invoke_destructive_commands(
    git_repo: pathlib.Path,
) -> None:
    real_run = subprocess.run
    captured: list[list[str]] = []

    def _capturing_run(*args: Any, **kwargs: Any) -> Any:
        if args and isinstance(args[0], list):
            captured.append(list(args[0]))
        return real_run(*args, **kwargs)

    with mock.patch.object(branch_lifecycle.subprocess, "run", side_effect=_capturing_run):
        create_story_branch(
            "2-3",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            working_tree_probe=_clean_probe,
            repo_root=git_repo,
        )

    forbidden_subcommands = {"rebase", "reset", "clean"}
    for invocation in captured:
        if len(invocation) >= 2 and invocation[0] == "git":
            assert invocation[1] not in forbidden_subcommands, (
                f"destructive git subcommand invoked: {invocation!r}"
            )


def test_create_story_branch_does_not_invoke_remote_commands(
    git_repo: pathlib.Path,
) -> None:
    real_run = subprocess.run
    captured: list[list[str]] = []

    def _capturing_run(*args: Any, **kwargs: Any) -> Any:
        if args and isinstance(args[0], list):
            captured.append(list(args[0]))
        return real_run(*args, **kwargs)

    with mock.patch.object(branch_lifecycle.subprocess, "run", side_effect=_capturing_run):
        create_story_branch(
            "2-3",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            working_tree_probe=_clean_probe,
            repo_root=git_repo,
        )

    forbidden_subcommands = {"fetch", "pull", "merge", "remote", "cherry-pick", "tag"}
    for invocation in captured:
        if len(invocation) >= 2 and invocation[0] == "git":
            assert invocation[1] not in forbidden_subcommands, (
                f"forbidden git subcommand invoked: {invocation!r}"
            )


# --------------------------------------------------------------------------- #
# API-shape (AC-1)                                                            #
# --------------------------------------------------------------------------- #


def test_create_story_branch_keyword_only_trunk_allowlist() -> None:
    sig = inspect.signature(create_story_branch)
    param = sig.parameters["trunk_allowlist"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty


def test_create_story_branch_keyword_only_working_tree_probe() -> None:
    sig = inspect.signature(create_story_branch)
    param = sig.parameters["working_tree_probe"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty


def test_create_story_branch_missing_trunk_allowlist_typeerror() -> None:
    with pytest.raises(TypeError):
        create_story_branch(  # type: ignore[call-arg]
            "2-3",
            working_tree_probe=_clean_probe,
        )


def test_create_story_branch_missing_probe_typeerror() -> None:
    with pytest.raises(TypeError):
        create_story_branch(  # type: ignore[call-arg]
            "2-3",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        )


def test_module_all_exports() -> None:
    expected = {
        "BranchLifecycleBlocked",
        "BranchLifecycleResult",
        "DEFAULT_TRUNK_ALLOWLIST",
        "GitUncommittedWorkDetected",
        "TrunkBranchWriteRejected",
        "WorkingTreeProbe",
        "WorkingTreeProbeResult",
        "create_story_branch",
        "default_working_tree_probe",
    }
    assert set(branch_lifecycle.__all__) == expected


# --------------------------------------------------------------------------- #
# Working-tree probe factory (AC-3)                                           #
# --------------------------------------------------------------------------- #


def test_default_working_tree_probe_parses_porcelain_output(
    git_repo_with_uncommitted_changes: pathlib.Path,
) -> None:
    probe = default_working_tree_probe(git_repo_with_uncommitted_changes)
    result = probe()
    assert result.clean is False
    assert any("README.md" in p for p in result.uncommitted_paths)


def test_default_working_tree_probe_returns_clean_for_clean_repo(
    git_repo: pathlib.Path,
) -> None:
    probe = default_working_tree_probe(git_repo)
    result = probe()
    assert result.clean is True
    assert result.uncommitted_paths == ()
    assert result.reason is None


def test_default_working_tree_probe_unclean_reason_format(
    git_repo_with_uncommitted_changes: pathlib.Path,
) -> None:
    probe = default_working_tree_probe(git_repo_with_uncommitted_changes)
    result = probe()
    assert result.reason is not None
    assert "uncommitted path(s) detected" in result.reason


# --------------------------------------------------------------------------- #
# Branch-name derivation (AC-1; docs/git-hygiene.md convention)               #
# --------------------------------------------------------------------------- #


def test_branch_name_derivation_uses_story_id() -> None:
    assert _branch_name_for_story("2-3") == "bmad-automation/story/2-3"


@pytest.mark.parametrize(
    "story_id,expected",
    [
        ("1-1", "bmad-automation/story/1-1"),
        ("1-12a", "bmad-automation/story/1-12a"),
        ("2-3", "bmad-automation/story/2-3"),
        ("4-9", "bmad-automation/story/4-9"),
        ("8-12b", "bmad-automation/story/8-12b"),
    ],
)
def test_branch_name_derivation_multiple_story_ids(
    story_id: str, expected: str
) -> None:
    assert _branch_name_for_story(story_id) == expected


# --------------------------------------------------------------------------- #
# Marker-class linkage (AC-3, AC-4; sensor-not-advisor)                       #
# --------------------------------------------------------------------------- #


def _load_taxonomy_marker_classes() -> set[str]:
    taxonomy_path = (
        find_repo_root() / "schemas" / "marker-taxonomy.yaml"
    )
    data = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    return {entry["marker_class"] for entry in data["markers"]}


def test_uncommitted_marker_class_matches_taxonomy_entry() -> None:
    exc = GitUncommittedWorkDetected(
        attempted_story_id="2-3",
        uncommitted_paths=("a.py",),
    )
    assert exc.marker_class == "git-uncommitted-work-detected"
    assert exc.marker_class in _load_taxonomy_marker_classes(), (
        "marker_class identifier must exist in schemas/marker-taxonomy.yaml"
    )


def test_trunk_marker_class_matches_taxonomy_entry() -> None:
    exc = TrunkBranchWriteRejected(
        attempted_story_id="test",
        attempted_branch="main",
    )
    assert exc.marker_class == "trunk-branch-write-rejected"
    assert exc.marker_class in _load_taxonomy_marker_classes(), (
        "marker_class identifier must exist in schemas/marker-taxonomy.yaml"
    )


# --------------------------------------------------------------------------- #
# Frozen-tuple immutability (AC-1; Epic 1 retro Action #2)                    #
# --------------------------------------------------------------------------- #


def test_working_tree_probe_result_is_frozen() -> None:
    result = WorkingTreeProbeResult(clean=True)
    with pytest.raises(ValidationError):
        result.clean = False  # type: ignore[misc]


def test_branch_lifecycle_result_is_frozen() -> None:
    result = BranchLifecycleResult(
        branch_name="bmad-automation/story/2-3",
        created=True,
        previous_branch="main",
        repo_root=pathlib.Path("/tmp/foo"),
    )
    with pytest.raises(ValidationError):
        result.branch_name = "other"  # type: ignore[misc]


def test_uncommitted_paths_is_tuple() -> None:
    result = WorkingTreeProbeResult(
        clean=False,
        uncommitted_paths=("a.py", "b.py"),
    )
    # tuple has no .append; AttributeError if anyone tries.
    assert not hasattr(result.uncommitted_paths, "append")
    assert isinstance(result.uncommitted_paths, tuple)


# --------------------------------------------------------------------------- #
# Module discipline (AC-1; Epic 1 retro Action #1)                            #
# --------------------------------------------------------------------------- #


def test_find_repo_root_not_called_at_import() -> None:
    """Re-import the module with `find_repo_root` patched to raise; if
    the module called it at import time, the import would fail."""
    import importlib

    with mock.patch(
        "loud_fail_harness._shared.find_repo_root",
        side_effect=RuntimeError("must not be called at import"),
    ):
        importlib.reload(branch_lifecycle)
    # Re-import siblings the test module imported to ensure fresh state.
    importlib.reload(branch_lifecycle)


# --------------------------------------------------------------------------- #
# repo_root=None lazy resolution (AC-1; Epic 1 retro Action #1)               #
# --------------------------------------------------------------------------- #


def test_create_story_branch_repo_root_none_resolves_lazily(
    git_repo: pathlib.Path,
) -> None:
    """When repo_root is omitted, create_story_branch delegates to
    _default_repo_root() at function-call time (NOT import time). Verify
    by patching _default_repo_root to return the tmp_path git repo; the
    call must succeed without an explicit repo_root argument."""
    with mock.patch.object(
        branch_lifecycle, "_default_repo_root", return_value=git_repo
    ):
        result = create_story_branch(
            "2-3",
            trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
            working_tree_probe=_clean_probe,
            # No repo_root — relies on _default_repo_root()
        )
    assert result.branch_name == "bmad-automation/story/2-3"
    assert result.repo_root == git_repo


# --------------------------------------------------------------------------- #
# cause carries WorkingTreeProbeResult (D1 fix; AC-1 type contract)           #
# --------------------------------------------------------------------------- #


def test_git_uncommitted_work_detected_cause_carries_probe_result() -> None:
    """GitUncommittedWorkDetected.cause must be a WorkingTreeProbeResult
    per AC-1's BranchLifecycleBlocked type contract (not None), so callers
    can inspect the structured probe evidence via exc.cause.

    Uses branch_lifecycle.WorkingTreeProbeResult (module attribute) for the
    isinstance check to guard against stale class identity after module
    reloads in test_find_repo_root_not_called_at_import."""
    exc = branch_lifecycle.GitUncommittedWorkDetected(
        attempted_story_id="2-3",
        uncommitted_paths=("a.py", "b.py"),
    )
    assert isinstance(exc.cause, branch_lifecycle.WorkingTreeProbeResult), (
        "cause must be WorkingTreeProbeResult per AC-1 type contract"
    )
    assert exc.cause.clean is False
    assert exc.cause.uncommitted_paths == ("a.py", "b.py")
