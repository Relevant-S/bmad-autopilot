"""Git-ground-truth-probe verification — Story 22.6 G3 (closes the Epic 21 Significant Discovery).

The Epic 21 Significant Discovery was a *loud-fail sensor whose own ground-truth
probe silently mis-classified the exact signature it was built to detect*: the
original ``make_git_ground_truth_probe`` counted FULL ancestry
(``git rev-list --count refs/heads/<branch>``), so a per-story branch freshly cut
off ``main`` with zero story commits false-confirmed as "landed". Story 21.2
fixed it (to the ``main..<branch>`` range form) and added a single in-band test;
this fixture GENERALIZES that test so it covers **every** git-ground-truth
*completion* probe, present and future.

## What is a "completion" probe (in scope)

A completion probe answers "did this story's work land?" — its contract is a
:class:`~loud_fail_harness.background_dispatch.GitGroundTruth`
(``branch_exists`` / ``has_landed_commits``). Today the sole completion probe is
``make_git_ground_truth_probe`` (``background_dispatch.py``). Enumeration is
**convention-driven**: every package-level ``make_*_ground_truth_probe`` factory
is discovered and parametrized, so a future completion probe added to this
package's top-level modules is covered WITHOUT editing this test.

## What is out of scope (orthogonal — context / working-tree inspection)

``_probe_current_branch`` + ``_probe_branch_exists`` (``session_start_reattach``)
and ``default_working_tree_probe`` (``branch_lifecycle``) inspect the CURRENT
checkout / working tree — they do NOT answer "did the work land?" and are
deliberately excluded. They do not return :class:`GitGroundTruth`.

## The invariant + the negative witness ("verify the verifier")

Invariant: against a real git repo whose per-story branch was cut off ``main``
with ZERO story commits, every completion probe MUST classify
``branch_exists=True, has_landed_commits=False`` — never ``completed-confirmed``.

Negative witness (mutation-testing's "never trust a test you haven't seen
fail"): a deliberately-buggy probe using the *original* full-ancestry
``git rev-list --count refs/heads/<branch>`` form makes the invariant assertion
FAIL — proving the verification is sensitive to the exact 21.2 regression. A gate
that cannot demonstrate it fails on the bad input is itself unverified.
"""

from __future__ import annotations

import importlib
import pathlib
import pkgutil
import re
import subprocess
from typing import Callable

import pytest

import loud_fail_harness
from loud_fail_harness.background_dispatch import (
    BackgroundAgentSession,
    GitGroundTruth,
    GitGroundTruthProbe,
)
from loud_fail_harness.branch_lifecycle import _branch_name_for_story

_STORY_ID = "22-6"

#: Convention: a completion-probe FACTORY is a package-level callable named
#: ``make_<name>_ground_truth_probe``. Discovered by source scan so a future
#: probe in ANY package module is auto-covered without editing this test.
_FACTORY_NAME_RE = re.compile(r"^def\s+(make_\w*ground_truth_probe)\s*\(", re.MULTILINE)


def _discover_completion_probe_factories() -> dict[str, Callable[..., GitGroundTruthProbe]]:
    package_dir = pathlib.Path(loud_fail_harness.__file__).resolve().parent
    factories: dict[str, Callable[..., GitGroundTruthProbe]] = {}
    for module_info in pkgutil.iter_modules([str(package_dir)]):
        module_path = package_dir / f"{module_info.name}.py"
        if not module_path.is_file():
            continue
        source = module_path.read_text(encoding="utf-8")
        for factory_name in _FACTORY_NAME_RE.findall(source):
            module = importlib.import_module(
                f"loud_fail_harness.{module_info.name}"
            )
            factory = getattr(module, factory_name, None)
            if callable(factory):
                factories[f"{module_info.name}.{factory_name}"] = factory
    return factories


_FACTORIES = _discover_completion_probe_factories()


def _run_git(*args: str, cwd: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _make_empty_story_branch_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A real git repo: one commit on ``main``, the per-story branch cut off it
    with ZERO new commits (the precise 21.2 false-confirm signature)."""
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
    _run_git("checkout", "-b", _branch_name_for_story(_STORY_ID), cwd=repo_str)
    return repo


def _assert_empty_branch_not_confirmed(
    probe: GitGroundTruthProbe, *, story_id: str
) -> None:
    """The load-bearing invariant: an empty story branch is NOT confirmed landed.

    Raises :class:`AssertionError` (the verifier's teeth) when a probe classifies
    a zero-commit branch as ``has_landed_commits=True`` — the 21.2 regression.
    """
    result = probe(
        BackgroundAgentSession(session_id="j", state="completed", story_id=story_id)
    )
    assert result.branch_exists is True
    assert result.has_landed_commits is False


def test_at_least_one_completion_probe_discovered() -> None:
    """Non-vacuity: the convention-driven discovery must find the known probe so
    the parametrized suite below is never silently empty."""
    assert any(name.endswith("make_git_ground_truth_probe") for name in _FACTORIES)


@pytest.mark.parametrize("factory_key", sorted(_FACTORIES))
def test_completion_probe_empty_story_branch_not_confirmed(
    factory_key: str, tmp_path: pathlib.Path
) -> None:
    repo = _make_empty_story_branch_repo(tmp_path)
    probe = _FACTORIES[factory_key](repo_root=repo)
    _assert_empty_branch_not_confirmed(probe, story_id=_STORY_ID)


def _buggy_full_ancestry_probe(*, repo_root: pathlib.Path) -> GitGroundTruthProbe:
    """The ORIGINAL 21.2 bug, reconstructed: counts FULL ancestry
    (``refs/heads/<branch>``) instead of the ``main..<branch>`` range, so an
    empty story branch false-confirms as landed."""

    def _probe(session: BackgroundAgentSession) -> GitGroundTruth:
        if session.story_id is None:
            return GitGroundTruth(branch_exists=False, has_landed_commits=False)
        branch = _branch_name_for_story(session.story_id)
        verify = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if verify.returncode != 0:
            return GitGroundTruth(branch_exists=False, has_landed_commits=False)
        count = subprocess.run(
            ["git", "rev-list", "--count", f"refs/heads/{branch}"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        has_commits = count.returncode == 0 and int(count.stdout.strip()) > 0
        return GitGroundTruth(branch_exists=True, has_landed_commits=has_commits)

    return _probe


def test_negative_witness_buggy_probe_fails_the_verification(
    tmp_path: pathlib.Path,
) -> None:
    """Verify-the-verifier: the deliberately-buggy full-ancestry probe (the exact
    21.2 regression) MUST make the invariant assertion fail — proving the
    verification actually has teeth."""
    repo = _make_empty_story_branch_repo(tmp_path)
    buggy = _buggy_full_ancestry_probe(repo_root=repo)
    with pytest.raises(AssertionError):
        _assert_empty_branch_not_confirmed(buggy, story_id=_STORY_ID)
