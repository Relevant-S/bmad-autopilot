"""Epic-15 reference-run fixture — the epic-orchestration cohort driven
end-to-end through ``run_epic_loop`` (Story 15.5).

This module is the Epic-15 analog of Story 14.6's
``test_epic_14_substrate_smoke.py``, deepened one layer: where 14.6 exercised the
Epic-14 *substrate primitives* directly, this fixture drives the actual epic
Orchestrator (``epic_lifecycle.run_epic_loop``) across a synthetic multi-story
epic and witnesses that Stories 15.1–15.4 interoperate at the seams. It is the
EMPIRICAL, CI-witnessed proof that the epic-orchestration substrate composes
end-to-end BEFORE Epic 16 (sprint orchestration) builds sprint flow on top.

It adds NO production ``src/loud_fail_harness/*.py`` module and modifies none —
the substrate-component count stays FIVE per ADR-003 Consequence 1. The fixture
is a pure CONSUMER of the landed runtime; the only new code is this ``tests/``
module (the ``docs/reference-runs/15-5-epic-web/`` capture is derived from a
clean-run pass of the SAME substrate with a fixed ``generated_at``).

## Determinism seam — the injected ``StoryLoopRunner`` (the ratified 15.1 posture)

``run_epic_loop`` injects a ``story_loop_runner`` (keyword-only, non-defaulted).
In production it drives the UNCHANGED per-story loop; here it is a deterministic
stub returning a canned ``StoryLoopOutcome`` (terminal_status + retries_consumed
+ cost). This is NOT a mock-instead-of-real shortcut — it is the
architecturally-ratified Epic-15 determinism seam (Story 15.1 AC-2). Canned costs
are non-zero so the per-epic cost partition is a POSITIVE witness, not a
degenerate all-zero table. The ONE place the clean run goes beyond a pure stub is
AC-2b: story 1's runner ALSO performs a real ``worktree_lifecycle`` create →
per-worktree run-state write → cleanup (reusing the 14.6 ``git_repo`` real-git
idiom) before returning, so the epic↔worktree "no orphan worktree / no stale
lock" seam is a genuine integration witness, not a model-level tautology.

The synthetic epic uses the id ``epic-915`` (NOT the real ``epic-15``) so there
is no collision with the live planning slice. ``enumerate_epic_stories`` requires
an ``epic-<digits>`` id (``_parse_epic_number``), so the AC-1 illustrative
``epic-ref15`` shape is rendered as the numeric, clearly-synthetic ``epic-915``
with stories ``915-1-alpha`` / ``915-2-bravo`` / ``915-3-charlie`` — three
stories so a genuine mid-epic boundary exists distinct from epic-close.

Contract-coverage matrix (AC-1 contract; AC-2…AC-4 + AC-10 are CI-witnessed
below; AC-5 and AC-6 are review-verified committed artifacts, not CI-testable):

    [x] AC-1 every runtime artifact under tmp_path; zero writes outside sandbox
        → test_ref_run_lands_under_tmp_path
    [x] AC-2 clean → epic-complete; escalation → epic-paused-on-escalation
        (prefix dispatch); budget → epic-paused-on-budget + marker; no raise;
        worktree post-condition (zero orphans, no stale lock persisted)
        → test_ref_run_drives_all_terminal_variants
        → test_ref_run_worktree_post_condition_zero_orphans_no_stale_lock
    [x] AC-2b ≥1 story exercises the real worktree lifecycle end-to-end
        → test_ref_run_exercises_real_worktree_lifecycle
    [x] AC-3 mid-epic + epic-close bundle snapshots; per-epic cost partition;
        byte-stability; mid-vs-close difference
        → test_ref_run_cost_partition_close_snapshot
        → test_ref_run_bundle_byte_stable_and_mid_differs_from_close
    [x] AC-4 per-story-total + epic-total scoping (no per-specialist breakdown
        re-rendered at epic scope)
        → test_ref_run_cost_scoping_per_story_total_not_per_specialist
    [x] AC-10 the full composed epic lifecycle proves 15.1–15.4 interoperate
        → test_ref_run_composes_full_epic_15_lifecycle
    [x] AC-5 docs/reference-runs/15-5-epic-web/ committed (README + narrative +
        pr-bundle-mid-epic.md + pr-bundle-epic-close.md + epic-run-state.yaml);
        reference-projects.md web-row migrated in-place — review-verified
    [x] AC-6 deferred-work.md NFR-P3 per-epic-latency H3-input entry appended;
        narrative.md stand-in caveat explicit — review-verified

Forward pointers (AC-10): Epic 16 (sprint orchestration) composes THIS epic loop
one scope up; Story 23.2 consumes the ``docs/reference-runs/15-5-epic-web/`` row
this fixture's clean run produced when populating ``phase-2-completion-evidence.md``.
The per-epic NFR-P3 latency budget is an Epic 22 H3 deliverable that this
stand-in run cannot validate empirically (see ``narrative.md`` + ``deferred-work.md``).
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
from dataclasses import dataclass
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.branch_lifecycle import DEFAULT_TRUNK_ALLOWLIST
from loud_fail_harness.bundle_assembly_epic import assemble_epic_bundle
from loud_fail_harness.epic_lifecycle import (
    EPIC_BUDGET_EXHAUSTED_MARKER,
    RunEpicLoopResult,
    StoryLoopOutcome,
    run_epic_loop,
)
from loud_fail_harness.epic_run_state import (
    EpicRunState,
    load_epic_run_state,
    worktree_run_state_path,
)
from loud_fail_harness.run_state import RunState
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)
from loud_fail_harness.worktree_lifecycle import (
    WorktreeCleanupResult,
    WorktreeLifecycleResult,
    cleanup_worktree,
    create_worktree,
    list_active_worktrees,
)

# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #

#: Synthetic, clearly-non-real epic id. ``enumerate_epic_stories`` requires an
#: ``epic-<digits>`` id, so the AC-1 ``epic-ref15`` illustration is rendered as
#: the numeric ``epic-915`` — no collision with the live ``epic-15`` slice.
_EPIC_ID = "epic-915"
_STORY_1 = "915-1-alpha"
_STORY_2 = "915-2-bravo"
_STORY_3 = "915-3-charlie"
_STORY_IDS = (_STORY_1, _STORY_2, _STORY_3)
_RUN_ID = "run-epic-915-ref-001"

#: AC-2b — the real-worktree-lifecycle story (story 1). Its derived branch
#: ``bmad-automation/story/915-1-alpha`` is NOT in DEFAULT_TRUNK_ALLOWLIST.
_WORKTREE_STORY = _STORY_1
_WORKTREE_BRANCH = f"bmad-automation/story/{_WORKTREE_STORY}"

#: Non-zero canned per-story costs → the cost partition is a POSITIVE witness (no
#: degenerate all-zero table; no spurious cost-telemetry-unavailable caveat).
_CLEAN_COSTS = {_STORY_1: 1.50, _STORY_2: 2.25, _STORY_3: 0.75}
#: Retries land on story 1 AND story 2 so mid-epic (consumed 1) and epic-close
#: (consumed 2) differ on the budget-consumption line (AC-3 mid-vs-close).
_CLEAN_RETRIES = {_STORY_1: 1, _STORY_2: 1, _STORY_3: 0}
_CLEAN_COST_TOTAL = sum(_CLEAN_COSTS.values())

#: Fixed UTC timestamp → assemble_epic_bundle output is byte-stable (AC-3).
_FIXED = dt.datetime(2026, 6, 2, 12, 0, 0, tzinfo=dt.timezone.utc)

#: A real BMAD project gitignores ephemeral run-state + the worktrees tree, which
#: keeps each worktree's working tree CLEAN of untracked-non-ignored files so
#: cleanup_worktree's `git worktree remove` (no --force) removes story 1 cleanly
#: even though the runner writes a per-worktree run-state INSIDE the worktree
#: (the 14.6 idiom).
_GITIGNORE_BODY = "_bmad/\nrun-state.yaml\n*.lock\n"


# --------------------------------------------------------------------------- #
# Git + schema helpers (mirror test_epic_14_substrate_smoke.py)               #
# --------------------------------------------------------------------------- #


def _run_git(*args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


def _init_git_repo(path: pathlib.Path) -> pathlib.Path:
    """Initialise a throwaway git repo at ``path`` (plain function so the
    docs-capture generator can reuse it outside pytest)."""
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
    ``$ref`` registry populated (mirror of test_epic_14_substrate_smoke.py)."""
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


def _write_sprint_status(repo_root: pathlib.Path) -> pathlib.Path:
    """Author the synthetic sprint-status slice under tmp_path: a non-real epic
    with three ready-for-dev stories (AC-1)."""
    path = repo_root / "_bmad" / "automation" / "sprint-status.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    development_status = {story_id: "ready-for-dev" for story_id in _STORY_IDS}
    path.write_text(
        yaml.safe_dump({"development_status": development_status}, sort_keys=False),
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------- #
# Clean-run carrier                                                            #
# --------------------------------------------------------------------------- #


@dataclass
class _CleanRunArtifacts:
    result: RunEpicLoopResult
    mid_state: EpicRunState
    close_state: EpicRunState
    mid_bundle_text: str
    close_bundle_text: str
    close_bundle_text_2nd: str
    create_worktree_result: WorktreeLifecycleResult
    cleanup_worktree_result: WorktreeCleanupResult
    per_worktree_run_state_errors: list[Any]
    per_worktree_run_state_path: pathlib.Path
    final_active_worktree_story_ids: tuple[str, ...]
    sandbox_paths: tuple[pathlib.Path, ...]


def _drive_clean_run(
    repo_root: pathlib.Path, marker_registry: MarkerClassRegistry
) -> _CleanRunArtifacts:
    """Drive the clean epic run to ``epic-complete``, with story 1's runner
    exercising the real worktree lifecycle and capturing the persisted mid-epic
    snapshot at the first per-story completion boundary."""
    sprint_status_path = _write_sprint_status(repo_root)
    automation = repo_root / "_bmad" / "automation"
    epic_run_state_path = automation / "epic-run-state.yaml"
    mid_state_path = automation / "epic-run-state-mid.yaml"
    worktrees_root = repo_root / "_bmad" / "automation" / "worktrees"
    per_worktree_rs_path = worktree_run_state_path(
        _WORKTREE_STORY, worktrees_root=worktrees_root, repo_root=repo_root
    )

    captured: dict[str, Any] = {}

    def runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        if story_id == _WORKTREE_STORY:
            # AC-2b — genuinely exercise the epic↔worktree seam.
            create = create_worktree(
                _WORKTREE_STORY,
                base_ref="main",
                trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
                worktrees_root=worktrees_root,
                repo_root=repo_root,
            )
            run_state = _make_worktree_run_state(_WORKTREE_STORY, create.branch_name)
            _write_run_state_yaml(per_worktree_rs_path, run_state)
            validator = _run_state_validator()
            errors = list(
                validator.iter_errors(
                    yaml.safe_load(per_worktree_rs_path.read_text(encoding="utf-8"))
                )
            )
            cleanup = cleanup_worktree(
                _WORKTREE_STORY,
                preserve_on_escalation=False,
                worktrees_root=worktrees_root,
                repo_root=repo_root,
            )
            captured["create"] = create
            captured["cleanup"] = cleanup
            captured["per_worktree_errors"] = errors
        if index == 2:
            # The on-disk epic-run-state now reflects story 1 folded + advanced
            # (epic-in-progress) — the genuine mid-epic boundary snapshot.
            mid_state_path.write_bytes(epic_run_state_path.read_bytes())
        return StoryLoopOutcome(
            terminal_status="merge-ready",  # type: ignore[arg-type]
            retries_consumed=_CLEAN_RETRIES[story_id],
            cost=_CLEAN_COSTS[story_id],
        )

    result = run_epic_loop(
        _EPIC_ID,
        run_id=_RUN_ID,
        sprint_status_path=sprint_status_path,
        epic_run_state_path=epic_run_state_path,
        story_loop_runner=runner,
    )

    final_worktrees = list_active_worktrees(repo_root=repo_root)
    final_active_worktree_story_ids = tuple(
        wt.story_id for wt in final_worktrees if wt.story_id in _STORY_IDS
    )

    mid_state = load_epic_run_state(mid_state_path)
    close_state = load_epic_run_state(epic_run_state_path)

    mid_bundle_root = repo_root / "_bmad-output" / "epic-pr-bundles-mid"
    close_bundle_root = repo_root / "_bmad-output" / "epic-pr-bundles"
    mid_assembled = assemble_epic_bundle(
        _EPIC_ID,
        _RUN_ID,
        mid_state_path,
        mid_bundle_root,
        marker_registry=marker_registry,
        generated_at=_FIXED,
    )
    close_assembled = assemble_epic_bundle(
        _EPIC_ID,
        _RUN_ID,
        epic_run_state_path,
        close_bundle_root,
        marker_registry=marker_registry,
        generated_at=_FIXED,
    )
    mid_bundle_text = mid_assembled.bundle_path.read_text(encoding="utf-8")
    close_bundle_text = close_assembled.bundle_path.read_text(encoding="utf-8")
    # Idempotent regeneration from the unchanged cache → byte-stable (AC-3).
    close_assembled_2nd = assemble_epic_bundle(
        _EPIC_ID,
        _RUN_ID,
        epic_run_state_path,
        close_bundle_root,
        marker_registry=marker_registry,
        generated_at=_FIXED,
    )
    close_bundle_text_2nd = close_assembled_2nd.bundle_path.read_text(encoding="utf-8")

    sandbox_paths = (
        sprint_status_path,
        epic_run_state_path,
        mid_state_path,
        per_worktree_rs_path,
        mid_assembled.bundle_path,
        close_assembled.bundle_path,
        worktrees_root,
    )

    return _CleanRunArtifacts(
        result=result,
        mid_state=mid_state,
        close_state=close_state,
        mid_bundle_text=mid_bundle_text,
        close_bundle_text=close_bundle_text,
        close_bundle_text_2nd=close_bundle_text_2nd,
        create_worktree_result=captured["create"],
        cleanup_worktree_result=captured["cleanup"],
        per_worktree_run_state_errors=captured["per_worktree_errors"],
        per_worktree_run_state_path=per_worktree_rs_path,
        final_active_worktree_story_ids=final_active_worktree_story_ids,
        sandbox_paths=sandbox_paths,
    )


def _drive_escalation_run(repo_root: pathlib.Path) -> RunEpicLoopResult:
    """Story 2 escalates → epic-paused-on-escalation; story 3 does NOT
    auto-advance (sensor-not-advisor)."""
    sprint_status_path = _write_sprint_status(repo_root)
    epic_run_state_path = (
        repo_root / "_bmad" / "automation" / "epic-run-state-escalation.yaml"
    )
    statuses = {_STORY_1: "merge-ready", _STORY_2: "escalated"}

    def runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        return StoryLoopOutcome(
            terminal_status=statuses[story_id],  # type: ignore[arg-type]
            retries_consumed=0,
            cost=_CLEAN_COSTS[story_id],
        )

    return run_epic_loop(
        _EPIC_ID,
        run_id=_RUN_ID,
        sprint_status_path=sprint_status_path,
        epic_run_state_path=epic_run_state_path,
        story_loop_runner=runner,
    )


def _drive_budget_run(repo_root: pathlib.Path) -> RunEpicLoopResult:
    """Cumulative retries exhaust the per-epic budget (multiplier 1 × 3 = 3) at
    the story-2 boundary with story 3 undispatched → epic-paused-on-budget +
    epic-budget-exhausted marker."""
    sprint_status_path = _write_sprint_status(repo_root)
    epic_run_state_path = (
        repo_root / "_bmad" / "automation" / "epic-run-state-budget.yaml"
    )
    retries = {_STORY_1: 2, _STORY_2: 2, _STORY_3: 99}

    def runner(*, story_id: str, index: int, total: int) -> StoryLoopOutcome:
        return StoryLoopOutcome(
            terminal_status="merge-ready",  # type: ignore[arg-type]
            retries_consumed=retries[story_id],
            cost=_CLEAN_COSTS[story_id],
        )

    return run_epic_loop(
        _EPIC_ID,
        run_id=_RUN_ID,
        sprint_status_path=sprint_status_path,
        epic_run_state_path=epic_run_state_path,
        story_loop_runner=runner,
        multiplier=1,
    )


@dataclass
class _RefRunResult:
    clean: _CleanRunArtifacts
    escalation: RunEpicLoopResult
    budget: RunEpicLoopResult


def _drive_ref_run(
    repo_root: pathlib.Path, marker_registry: MarkerClassRegistry
) -> _RefRunResult:
    clean = _drive_clean_run(repo_root, marker_registry)
    escalation = _drive_escalation_run(repo_root)
    budget = _drive_budget_run(repo_root)
    return _RefRunResult(clean=clean, escalation=escalation, budget=budget)


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
    return _drive_ref_run(git_repo, marker_registry)


# --------------------------------------------------------------------------- #
# Witnesses                                                                     #
# --------------------------------------------------------------------------- #


def test_ref_run_lands_under_tmp_path(
    ref_run: _RefRunResult, tmp_path: pathlib.Path
) -> None:
    """AC-1 — every runtime artifact (sprint-status slice, epic-run-state, mid
    snapshot, per-worktree run-state, assembled bundles, worktrees root) lands
    under tmp_path; the fixture makes zero writes outside the sandbox."""
    for path in ref_run.clean.sandbox_paths:
        assert path.is_relative_to(tmp_path), f"{path} escaped the tmp_path sandbox"
    assert ref_run.clean.result.wrote_path.is_relative_to(tmp_path)
    assert ref_run.escalation.wrote_path.is_relative_to(tmp_path)
    assert ref_run.budget.wrote_path.is_relative_to(tmp_path)


def test_ref_run_drives_all_terminal_variants(ref_run: _RefRunResult) -> None:
    """AC-2 — clean → epic-complete (full dispatch, no pause); escalation →
    epic-paused-on-escalation (strict prefix, sensor-not-advisor); budget →
    epic-paused-on-budget + epic-budget-exhausted marker. No run raised
    (deterministic termination — reaching this assertion proves it)."""
    clean = ref_run.clean.result
    assert clean.final_state.current_state == "epic-complete"
    assert clean.dispatched_story_ids == _STORY_IDS
    assert clean.paused_on_story_id is None

    esc = ref_run.escalation
    assert esc.final_state.current_state == "epic-paused-on-escalation"
    assert esc.dispatched_story_ids == (_STORY_1, _STORY_2)
    assert esc.dispatched_story_ids == _STORY_IDS[: len(esc.dispatched_story_ids)]
    assert esc.paused_on_story_id == _STORY_2
    # Downstream story did NOT auto-advance.
    assert esc.final_state.per_story_status[_STORY_3] == "ready-for-dev"

    bud = ref_run.budget
    assert bud.final_state.current_state == "epic-paused-on-budget"
    assert bud.dispatched_story_ids == (_STORY_1, _STORY_2)
    assert bud.paused_on_story_id == _STORY_2
    assert EPIC_BUDGET_EXHAUSTED_MARKER in bud.final_state.active_markers


def test_ref_run_exercises_real_worktree_lifecycle(ref_run: _RefRunResult) -> None:
    """AC-2b — story 1's runner performed a REAL create_worktree → schema-valid
    per-worktree run-state write → cleanup_worktree(removed=True), so the
    epic↔worktree seam is genuinely exercised (the chosen witness path is the
    REAL worktree lifecycle, not the model-level fallback)."""
    clean = ref_run.clean
    assert clean.create_worktree_result.created is True
    assert clean.create_worktree_result.branch_name == _WORKTREE_BRANCH
    assert clean.per_worktree_run_state_errors == []
    assert clean.cleanup_worktree_result.removed is True
    assert clean.cleanup_worktree_result.preserved_for_escalation is False


def test_ref_run_worktree_post_condition_zero_orphans_no_stale_lock(
    ref_run: _RefRunResult,
) -> None:
    """AC-2 worktree post-condition — zero synthetic-story worktrees remain
    after the clean run, and the persisted final state carries NO
    worktree-stale-lock (the transient marker is re-derived/filtered, never
    persisted — the 15.1 model; reuses the test_epic_15_transient_marker_smoke.py
    witness posture)."""
    assert ref_run.clean.final_active_worktree_story_ids == ()
    assert "worktree-stale-lock" not in ref_run.clean.result.final_state.active_markers


def test_ref_run_cost_partition_close_snapshot(ref_run: _RefRunResult) -> None:
    """AC-3 — the epic-close bundle carries the load-bearing per-epic cost
    partition: one row per story + an Epic total; epic_cost_total == sum of
    per-story costs (fold_story_cost threaded end-to-end); positive costs;
    retry-budget-consumption line present; loud-fail (active-markers) section
    present."""
    close_state = ref_run.clean.close_state
    partition = close_state.per_epic_cost_partition
    assert set(partition.per_story_cost.keys()) == set(_STORY_IDS)
    assert partition.epic_cost_total == sum(partition.per_story_cost.values())
    assert partition.epic_cost_total == _CLEAN_COST_TOTAL
    assert all(cost > 0 for cost in partition.per_story_cost.values())

    bundle = ref_run.clean.close_bundle_text
    assert "## 💸 Epic Cost Partition" in bundle
    for story_id in _STORY_IDS:
        assert f"| {story_id} | {_CLEAN_COSTS[story_id]:.2f} |" in bundle
    assert f"| Epic total | {_CLEAN_COST_TOTAL:.2f} |" in bundle
    # No degenerate all-zero table → no lower-bound caveat.
    assert "LOWER BOUND" not in bundle
    assert "## Retry budget" in bundle
    assert f"Consumed {close_state.per_epic_retry_budget.consumed} of " in bundle
    assert "Loud-Fail Markers" in bundle


def test_ref_run_bundle_byte_stable_and_mid_differs_from_close(
    ref_run: _RefRunResult,
) -> None:
    """AC-3 — assembling the close bundle twice from the unchanged cache yields
    byte-identical output (idempotent regeneration); the mid-epic vs epic-close
    snapshots DIFFER on epic state + cost completeness + budget consumption
    (proving the running bundle regenerates rather than being static)."""
    clean = ref_run.clean
    assert clean.close_bundle_text == clean.close_bundle_text_2nd
    assert clean.mid_bundle_text != clean.close_bundle_text

    # epic state.
    assert clean.mid_state.current_state == "epic-in-progress"
    assert clean.close_state.current_state == "epic-complete"
    assert "Epic state: epic-in-progress" in clean.mid_bundle_text
    assert "Epic state: epic-complete" in clean.close_bundle_text

    # cost-partition completeness (mid carries only story 1's non-zero cost).
    assert clean.mid_state.per_epic_cost_partition.epic_cost_total == _CLEAN_COSTS[
        _STORY_1
    ]
    assert (
        clean.close_state.per_epic_cost_partition.epic_cost_total > _CLEAN_COST_TOTAL - 0.01
    )
    assert clean.mid_state.per_epic_cost_partition.per_story_cost[_STORY_2] == 0.0
    assert clean.close_state.per_epic_cost_partition.per_story_cost[_STORY_2] > 0.0

    # budget consumption (mid 1, close 2).
    assert clean.mid_state.per_epic_retry_budget.consumed == 1
    assert clean.close_state.per_epic_retry_budget.consumed == 2


def test_ref_run_cost_scoping_per_story_total_not_per_specialist(
    ref_run: _RefRunResult,
) -> None:
    """AC-4 — the epic bundle renders per-story TOTALS + epic total (NFR-P5
    per-epic extension); it does NOT re-render the per-specialist (Dev /
    Review-BMAD / QA / Review-LAD) + per-retry breakdown — that stays canonical
    in each story's own bundle (Story 15.3 pointer-not-projection, NFR-R8)."""
    bundle = ref_run.clean.close_bundle_text
    # The epic cache carries per-story totals only — no per-specialist field.
    partition = ref_run.clean.close_state.per_epic_cost_partition
    assert set(partition.per_story_cost.keys()) == set(_STORY_IDS)
    # The epic bundle points DOWN to each story's canonical artifact (the
    # per-specialist breakdown lives there), it does not re-aggregate it.
    assert "_bmad-output/pr-bundles/" in bundle
    assert "cost_to_date_by_specialist" not in bundle
    assert "per-specialist" not in bundle
    # No per-specialist cost rows at epic scope — the only cost section is the
    # per-story-total + epic-total partition.
    assert bundle.count("## 💸 Epic Cost Partition") == 1


def test_ref_run_composes_full_epic_15_lifecycle(ref_run: _RefRunResult) -> None:
    """AC-10 — the full composed epic lifecycle proves Stories 15.1–15.4
    interoperate at the seams: enumerate → init → sequential dispatch (with a
    real worktree create→cleanup) → fold cost/terminal/budget → advance atomic
    writes (transient filter applied) → terminal epic-complete /
    epic-paused-on-escalation / epic-paused-on-budget → running + close
    epic-PR-bundle assembly with the per-epic cost partition rendered."""
    clean = ref_run.clean
    assert clean.result.final_state.current_state == "epic-complete"
    assert clean.create_worktree_result.created is True
    assert clean.cleanup_worktree_result.removed is True
    assert clean.final_active_worktree_story_ids == ()
    assert clean.mid_state.current_state == "epic-in-progress"
    assert clean.close_state.current_state == "epic-complete"
    assert clean.close_state.per_epic_cost_partition.epic_cost_total == _CLEAN_COST_TOTAL
    assert ref_run.escalation.final_state.current_state == "epic-paused-on-escalation"
    assert ref_run.budget.final_state.current_state == "epic-paused-on-budget"
    assert EPIC_BUDGET_EXHAUSTED_MARKER in ref_run.budget.final_state.active_markers
