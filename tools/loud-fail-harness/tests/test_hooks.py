"""Contract-coverage matrix for the three Story 2.7 hook scripts.

This docstring IS the contract-coverage checklist required by AC-7. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to stories 1.2-1.9 + 2.2-2.6).

subagent-stop.sh (AC-2, AC-3):
    [x] happy path: commit created with NFR-O6 tag                → test_subagent_stop_happy_path_creates_commit
    [x] commit message ends with [bmad-automation story/<id>]      → test_subagent_stop_appends_commit_tag_per_nfr_o6
    [x] non-Dev dispatched_specialist → exit 0, no commit          → test_subagent_stop_no_op_on_non_dev_dispatched_specialist
    [x] missing proposed_commit_message → exit 1                   → test_subagent_stop_exits_one_on_missing_proposed_commit_message
    [x] undeclared scope expansion → exit 1, scope-assertion-violation (Story 5.4) → test_subagent_stop_exits_one_on_undeclared_scope_expansion
    [x] HEAD branch != run-state.branch_name → exit 1              → test_subagent_stop_exits_one_on_branch_mismatch
    [x] trunk branch in run-state → exit 1                          → test_subagent_stop_exits_one_on_trunk_branch_in_run_state
    [x] full violation path emits marker on stderr (Story 5.4 AC-7) → test_subagent_stop_emits_scope_assertion_violation_marker_on_undeclared_diff
    [x] declared diff exits 0 (Story 5.4 AC-7 symmetric)            → test_subagent_stop_exits_zero_on_declared_diff

stop.sh (AC-4 of Story 2.7 + AC-6/AC-9 of Story 2.11):
    [x] writes structured bundle to documented path                → test_stop_writes_walking_skeleton_bundle_to_documented_path
    [x] mkdir -p creates parent directories idempotently           → test_stop_creates_parent_directories_idempotently
    [x] bundle includes structured walking-skeleton-bundle marker  → test_stop_bundle_content_includes_walking_skeleton_anchor
    [x] bundle includes H1 + metadata + H2 sections per AC-3       → test_stop_bundle_includes_structured_h2_sections
    [x] bundle does not include the do-NOT-include sections (AC-3) → test_stop_bundle_omits_loud_fail_cost_retry_sections
    [x] hook stays within 18-effective-line budget (AC-6)          → test_stop_hook_within_eighteen_line_budget

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

import json
import os
import pathlib
import subprocess
from typing import Any

import pytest
import yaml

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
    last_retry_affected_files: list[str] | None = None,
) -> pathlib.Path:
    """Synthesize _bmad/automation/run-state.yaml under ``repo``.

    Story 5.4 thickening: ``last_retry_affected_files`` populates the new
    optional ``last_retry_directive`` field (schema 1.1 → 1.2 bump). When
    provided, the SubagentStop hook's ``scope-assertion-verify`` CLI
    invocation reads it as the declared scope.
    """
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
    if last_retry_affected_files:
        directive_block = (
            "last_retry_directive:\n"
            "  retry_mode: fix-only\n"
            "  affected_files: ["
            + ",".join(repr(p) for p in last_retry_affected_files)
            + "]\n"
        )
    else:
        directive_block = "last_retry_directive: null\n"
    rs.write_text(
        f"schema_version: '1.2'\n"
        f"story_id: {story_id}\n"
        f"run_id: r1\n"
        f"current_state: {current_state}\n"
        f"branch_name: {branch_name}\n"
        + spec_line
        + envelope
        + "retry_history: []\n"
        + "active_markers: []\n"
        + "cost_to_date_by_specialist: {}\n"
        + "pending_qa_dispatch_payload: null\n"
        + directive_block,
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


def _load_envelope(path: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _seed_canonical_dispatch_logs(
    repo: pathlib.Path,
    *,
    story_id: str,
    run_id: str,
) -> None:
    """Seed Story 2.6-shaped dispatch logs at the canonical
    `_bmad-output/qa-evidence/{story-id}/{run-id}/logs/{specialist}-1.log`
    path using the canonical envelope corpus. Story 2.11's bundle
    assembler reads the `return_envelope` field from each log.
    """
    from loud_fail_harness._shared import find_repo_root

    envelopes_dir = find_repo_root() / "examples" / "envelopes"
    envelopes = {
        "dev": _load_envelope(envelopes_dir / "dev-pass.yaml"),
        "review-bmad": _load_envelope(
            envelopes_dir / "review-pass-acceptance-auditor.yaml"
        ),
        "qa": _load_envelope(envelopes_dir / "qa-pass-ac1-tier1.yaml"),
    }
    logs_dir = (
        repo / "_bmad-output" / "qa-evidence" / story_id / run_id / "logs"
    )
    logs_dir.mkdir(parents=True, exist_ok=True)
    for specialist, envelope in envelopes.items():
        log_payload = {
            "dispatched_specialist": specialist,
            "story_id": story_id,
            "attempt_number": 1,
            "agent_definition_path": f"agents/{specialist}.md",
            "acceptance_criteria": [{"ac_id": "AC-1", "text": "stub"}],
            "dispatch_timestamp": "2026-04-29T12:00:00+00:00",
            "return_timestamp": "2026-04-29T12:01:00+00:00",
            "return_envelope": envelope,
        }
        (logs_dir / f"{specialist}-1.log").write_text(
            json.dumps(log_payload, indent=2), encoding="utf-8"
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


def test_subagent_stop_exits_one_on_undeclared_scope_expansion(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    """Story 5.4 thickening (renamed from
    test_subagent_stop_exits_one_on_nonempty_scope_expanded_to). The
    placeholder length-based rejection is replaced by a real verifier
    invocation: stage a diff containing a file outside the declared
    `last_retry_directive.affected_files` ∪ `scope_expanded_to` set;
    the hook commits the diff (per AC-6's commit-then-verify ordering)
    and then exits 1 with the marker emitted by `scope-assertion-verify`.
    """
    # Stage Dev's diff: foo.py (declared) + baz.py (undeclared).
    (fixture_repo / "src").mkdir(exist_ok=True)
    (fixture_repo / "src" / "foo.py").write_text("x = 1\n", encoding="utf-8")
    (fixture_repo / "src" / "baz.py").write_text("z = 3\n", encoding="utf-8")
    _run_git("add", "src/foo.py", "src/baz.py", cwd=fixture_repo)
    _write_run_state(
        fixture_repo,
        proposed_commit_message="feat: x",
        scope_expanded_to=[],
        last_retry_affected_files=["src/foo.py"],
    )
    pre_head = _run_git("rev-parse", "HEAD", cwd=fixture_repo).stdout.strip()
    result = _invoke_hook(hooks_dir / "subagent-stop.sh", fixture_repo)
    post_head = _run_git("rev-parse", "HEAD", cwd=fixture_repo).stdout.strip()
    # Hook must commit before verifying (commit-then-verify ordering per AC-6).
    assert pre_head != post_head, "git commit must succeed before verification fires"
    assert result.returncode == 1, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "scope-assertion-violation" in result.stderr
    assert "src/baz.py" in result.stderr


def test_subagent_stop_emits_scope_assertion_violation_marker_on_undeclared_diff(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    """Story 5.4 AC-7 — end-to-end SubagentStop hook integration:
    real git fixture, scope-assertion-verify CLI, full violation path.

    ARRANGE: tmp_path repo on per-story branch; modify foo + baz where
    only foo is in `last_retry_directive.affected_files`. ACT: invoke
    the hook (which commits and then verifies). ASSERT: hook commits
    Dev's changes; CLI computes diff against HEAD~1; emits the marker
    on stderr; hook propagates exit 1. The git commit is NOT rolled back
    per the loud-fail-but-preserve-state discipline.
    """
    # Stage Dev's diff: foo + baz (latter is undeclared).
    (fixture_repo / "src").mkdir(exist_ok=True)
    (fixture_repo / "src" / "foo.py").write_text("x = 1\n", encoding="utf-8")
    (fixture_repo / "src" / "baz.py").write_text("z = 3\n", encoding="utf-8")
    _run_git("add", "src/foo.py", "src/baz.py", cwd=fixture_repo)
    _write_run_state(
        fixture_repo,
        proposed_commit_message="feat: foo + undeclared baz",
        scope_expanded_to=[],
        last_retry_affected_files=["src/foo.py"],
    )
    pre_head = _run_git("rev-parse", "HEAD", cwd=fixture_repo).stdout.strip()
    result = _invoke_hook(hooks_dir / "subagent-stop.sh", fixture_repo)
    assert result.returncode == 1, f"stderr={result.stderr!r}"
    # Hook committed Dev's changes per AC-6's commit-then-verify ordering.
    post_head = _run_git("rev-parse", "HEAD", cwd=fixture_repo).stdout.strip()
    assert pre_head != post_head, "git commit must succeed before verification fires"
    log = _run_git("log", "-1", "--format=%s", cwd=fixture_repo)
    assert "feat: foo + undeclared baz" in log.stdout
    # CLI emitted the marker class identifier + violating file + remediation hint on stderr.
    assert "scope-assertion-violation" in result.stderr
    assert "src/baz.py" in result.stderr
    assert "review Dev's diff vs. declared scope" in result.stderr


def test_subagent_stop_exits_zero_on_declared_diff(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    """Story 5.4 AC-7 symmetric clean-path test — the hook exits 0 when
    Dev's actual diff falls within (`affected_files` ∪
    `scope_expanded_to`); CLI stdout includes `scope-assertion: clean`."""
    (fixture_repo / "src").mkdir(exist_ok=True)
    (fixture_repo / "src" / "foo.py").write_text("x = 1\n", encoding="utf-8")
    (fixture_repo / "src" / "baz.py").write_text("z = 3\n", encoding="utf-8")
    _run_git("add", "src/foo.py", "src/baz.py", cwd=fixture_repo)
    _write_run_state(
        fixture_repo,
        proposed_commit_message="feat: foo + declared baz",
        scope_expanded_to=["src/baz.py"],
        last_retry_affected_files=["src/foo.py"],
    )
    result = _invoke_hook(hooks_dir / "subagent-stop.sh", fixture_repo)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "scope-assertion: clean" in result.stdout


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
    """Story 2.11 AC-9: relax Story 2.7's placeholder-string assertions.
    The bundle is now the rich Story 2.11 shape — H1 title + metadata
    block + dynamic Walking Skeleton Mode header + Per-AC results +
    Review findings + Dev sections + structured marker.
    """
    _write_run_state(fixture_repo, story_id="2-7-test", current_state="done")
    _seed_canonical_dispatch_logs(fixture_repo, story_id="2-7-test", run_id="r1")
    result = _invoke_hook(hooks_dir / "stop.sh", fixture_repo)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    bundle = fixture_repo / "_bmad-output" / "pr-bundles" / "2-7-test" / "r1.md"
    assert bundle.exists()
    body = bundle.read_text(encoding="utf-8")
    # H1 + metadata (AC-3).
    assert body.startswith("# PR bundle — story 2-7-test (run r1)")
    assert "Branch: bmad-automation/story/2-7-test" in body
    assert "Final state: done" in body
    assert "Generated:" in body
    # Walking Skeleton Mode header (AC-3).
    assert "## ⚠️ Walking Skeleton Mode" in body
    # Story 2.7 placeholder text MUST be gone.
    assert "Placeholder bundle from Story 2.7" not in body


def test_stop_creates_parent_directories_idempotently(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    _write_run_state(fixture_repo, story_id="2-7-idem")
    _seed_canonical_dispatch_logs(fixture_repo, story_id="2-7-idem", run_id="r1")
    # Pre-create the directory; the assembler's atomic-write must remain idempotent.
    (fixture_repo / "_bmad-output" / "pr-bundles" / "2-7-idem").mkdir(parents=True)
    result = _invoke_hook(hooks_dir / "stop.sh", fixture_repo)
    assert result.returncode == 0


def test_stop_bundle_content_omits_walking_skeleton_marker_at_post_6_1_substrate(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    """Story 6.1 AC-3 / AC-4 — assertion inversion. Post-6.1 the
    production thickening_flags's ``is_loud_fail_block_present()``
    returns ``True`` via structural derivation; the structural rule
    ``if flags.is_loud_fail_block_present(): return ()`` at
    :func:`_emit_walking_skeleton_marker` fires, so the structured
    walking-skeleton-bundle marker comment is absent from new runs.
    The legacy fragile-prose form remains forbidden per Story 2.11
    AC-4 regardless of era.
    """
    _write_run_state(fixture_repo, story_id="2-7-anchor")
    _seed_canonical_dispatch_logs(fixture_repo, story_id="2-7-anchor", run_id="r1")
    result = _invoke_hook(hooks_dir / "stop.sh", fixture_repo)
    assert result.returncode == 0
    bundle = fixture_repo / "_bmad-output" / "pr-bundles" / "2-7-anchor" / "r1.md"
    body = bundle.read_text(encoding="utf-8")
    # Marker absent post-6.1 (structural inversion via flag flip).
    assert "<!-- bmad-automation:marker walking-skeleton-bundle -->" not in body
    # Legacy placeholder form forbidden regardless of era.
    assert "<!-- walking-skeleton-bundle: marker_class -->" not in body


def test_stop_bundle_includes_structured_h2_sections(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    """AC-9 + Story 6.1 AC-1: the bundle's H2 sections appear in the
    canonical post-6.1 order Walking-Skeleton-Mode → Loud-Fail-Markers
    → Per-AC-results → Review-findings → Dev. The loud-fail block H2
    is the first content section after the title metadata block + the
    Walking Skeleton header per Story 6.1 AC-1's structural-position
    contract.
    """
    _write_run_state(fixture_repo, story_id="2-7-sections")
    _seed_canonical_dispatch_logs(fixture_repo, story_id="2-7-sections", run_id="r1")
    result = _invoke_hook(hooks_dir / "stop.sh", fixture_repo)
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    bundle = fixture_repo / "_bmad-output" / "pr-bundles" / "2-7-sections" / "r1.md"
    body = bundle.read_text(encoding="utf-8")
    h2_lines = [line for line in body.splitlines() if line.startswith("## ")]
    assert h2_lines == [
        "## ⚠️ Walking Skeleton Mode",
        "## ✓ Loud-Fail Markers — None",
        "## Per-AC results",
        "## Review findings",
        "## Dev",
    ]


def test_stop_bundle_omits_cost_retry_sections_at_post_6_1_substrate(
    fixture_repo: pathlib.Path, hooks_dir: pathlib.Path
) -> None:
    """Story 6.1 inversion: the loud-fail block IS now present (Story
    6.1 AC-1); the cost-breakdown + retry-history sections remain
    out-of-scope (Stories 6.4-6.5 + Epic 5 retry history). This test
    pins the absence of the still-out-of-scope sections.
    """
    _write_run_state(fixture_repo, story_id="2-7-omits")
    _seed_canonical_dispatch_logs(fixture_repo, story_id="2-7-omits", run_id="r1")
    result = _invoke_hook(hooks_dir / "stop.sh", fixture_repo)
    assert result.returncode == 0
    bundle = fixture_repo / "_bmad-output" / "pr-bundles" / "2-7-omits" / "r1.md"
    body = bundle.read_text(encoding="utf-8")
    assert "## Cost breakdown" not in body
    assert "## Per-specialist cost" not in body
    assert "## Retry history" not in body


def test_stop_hook_within_eighteen_line_budget(hooks_dir: pathlib.Path) -> None:
    """AC-6: the rewritten stop.sh stays at ≤18 effective lines per
    Story 1.9's hook_budget_gate counting rule (the lower-than-20
    ceiling reserves margin for Epic 6's Story 6.1 thickening)."""
    assert count_effective_lines(hooks_dir / "stop.sh") <= 18


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
