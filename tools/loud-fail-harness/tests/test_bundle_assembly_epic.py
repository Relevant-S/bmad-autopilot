"""Tests for the epic-level PR-bundle assembler (Story 15.3).

Coverage map (per the story's Task 5):
    [x] rendering — status table tags + per-story-artifact pointers          → test_renders_*_pointer
    [x] rendering — per-story + per-epic cost partition                       → test_renders_cost_partition
    [x] rendering — retry-budget-consumption line                            → test_renders_retry_budget
    [x] rendering — per-epic loud-fail block incl. epic-budget-exhausted     → test_renders_epic_budget_exhausted_marker
    [x] rendering — no-markers sentinel                                       → test_renders_loud_fail_none_sentinel
    [x] idempotency — render twice from same cache → byte-identical (AC-4)    → test_regeneration_is_byte_identical
    [x] generated_at naive rejection                                         → test_naive_generated_at_rejected
    [x] compute_epic_bundle_path happy + empty/absolute/.. rejection         → test_compute_epic_bundle_path_*
    [x] main: missing epic-run-state → exit 1, NO marker (pre-condition)      → test_main_missing_epic_run_state_exit_1
    [x] main: epic_id mismatch → exit 1, NO marker (pre-condition)            → test_main_epic_id_mismatch_exit_1
    [x] main: shape mismatch → surface_assembly_failure + exit 2 (AC-6)       → test_main_shape_mismatch_routes_assembly_failure
    [x] main: happy path → exit 0 + writes bundle                            → test_main_happy_path
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone

import pytest

from loud_fail_harness import bundle_assembly_epic
from loud_fail_harness.bundle_assembly_epic import (
    EpicBundlePathInvariantViolation,
    assemble_epic_bundle,
    compute_epic_bundle_path,
)
from loud_fail_harness.bundle_assembly_failure import (
    BUNDLE_ASSEMBLY_FAILED_EXIT_CODE,
    BUNDLE_ASSEMBLY_FAILED_MARKER,
)

_FIXED = datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)

_VALID_EPIC_RUN_STATE = """schema_version: "1.0"
epic_id: "epic-15"
run_id: "run-1"
current_state: "epic-paused-on-escalation"
story_ids:
  - "15-1-a"
  - "15-2-b"
  - "15-3-c"
per_story_status:
  "15-1-a": "merge-ready"
  "15-2-b": "escalated"
  "15-3-c": "in-progress"
per_epic_retry_budget:
  multiplier: 2
  story_count: 3
  effective_budget: 6
  consumed: 4
per_epic_cost_partition:
  per_story_cost:
    "15-1-a": 1.25
    "15-2-b": 0.80
    "15-3-c": 0.0
  epic_cost_total: 2.05
active_markers: []
"""

_BUDGET_PAUSED_EPIC_RUN_STATE = """schema_version: "1.0"
epic_id: "epic-15"
run_id: "run-1"
current_state: "epic-paused-on-budget"
story_ids:
  - "15-1-a"
  - "15-2-b"
per_story_status:
  "15-1-a": "done"
  "15-2-b": "in-progress"
per_epic_retry_budget:
  multiplier: 2
  story_count: 2
  effective_budget: 4
  consumed: 4
per_epic_cost_partition:
  per_story_cost:
    "15-1-a": 3.00
    "15-2-b": 1.50
  epic_cost_total: 4.50
active_markers:
  - "epic-budget-exhausted"
"""


def _write_ers(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    path = tmp_path / "epic-run-state.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _assemble(
    tmp_path: pathlib.Path,
    body: str,
    *,
    epic_id: str = "epic-15",
    run_id: str = "run-1",
) -> str:
    ers = _write_ers(tmp_path, body)
    result = assemble_epic_bundle(
        epic_id=epic_id,
        run_id=run_id,
        epic_run_state_path=ers,
        bundle_root=tmp_path / "_bmad-output" / "epic-pr-bundles",
        generated_at=_FIXED,
    )
    return result.bundle_path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Rendering                                                                   #
# --------------------------------------------------------------------------- #


def test_renders_header_and_path(tmp_path: pathlib.Path) -> None:
    ers = _write_ers(tmp_path, _VALID_EPIC_RUN_STATE)
    result = assemble_epic_bundle(
        epic_id="epic-15",
        run_id="run-1",
        epic_run_state_path=ers,
        bundle_root=tmp_path / "_bmad-output" / "epic-pr-bundles",
        generated_at=_FIXED,
    )
    assert result.bundle_path == (
        tmp_path / "_bmad-output" / "epic-pr-bundles" / "epic-15" / "run-1.md"
    )
    body = result.bundle_path.read_text(encoding="utf-8")
    assert body.startswith("# Epic PR bundle — epic epic-15 (run run-1)")
    assert "Epic state: epic-paused-on-escalation" in body
    assert f"Generated: {_FIXED.isoformat()}" in body


def test_renders_merge_ready_pointer(tmp_path: pathlib.Path) -> None:
    body = _assemble(tmp_path, _VALID_EPIC_RUN_STATE)
    assert "| 15-1-a | merge-ready | _bmad-output/pr-bundles/15-1-a/ |" in body


def test_renders_escalated_pointer(tmp_path: pathlib.Path) -> None:
    body = _assemble(tmp_path, _VALID_EPIC_RUN_STATE)
    assert (
        "| 15-2-b | escalated | _bmad-output/escalation-bundles/15-2-b/ |" in body
    )


def test_renders_in_progress_live_state_link(tmp_path: pathlib.Path) -> None:
    body = _assemble(tmp_path, _VALID_EPIC_RUN_STATE)
    assert "| 15-3-c | in-progress | _bmad-output/qa-evidence/15-3-c/ |" in body


def test_renders_done_pointer_as_completed(tmp_path: pathlib.Path) -> None:
    body = _assemble(tmp_path, _BUDGET_PAUSED_EPIC_RUN_STATE)
    assert "| 15-1-a | done | _bmad-output/pr-bundles/15-1-a/ |" in body


def test_renders_cost_partition(tmp_path: pathlib.Path) -> None:
    body = _assemble(tmp_path, _VALID_EPIC_RUN_STATE)
    assert "## 💸 Epic Cost Partition" in body
    assert "| 15-1-a | 1.25 |" in body
    assert "| 15-2-b | 0.80 |" in body
    assert "| 15-3-c | 0.00 |" in body
    assert "| Epic total | 2.05 |" in body


def test_renders_cost_lower_bound_note_when_any_zero(tmp_path: pathlib.Path) -> None:
    body = _assemble(tmp_path, _VALID_EPIC_RUN_STATE)
    assert "LOWER BOUND" in body
    assert "cost-telemetry-unavailable" in body


def test_omits_lower_bound_note_when_all_costs_present(
    tmp_path: pathlib.Path,
) -> None:
    body = _assemble(tmp_path, _BUDGET_PAUSED_EPIC_RUN_STATE)
    assert "LOWER BOUND" not in body


def test_renders_retry_budget(tmp_path: pathlib.Path) -> None:
    body = _assemble(tmp_path, _VALID_EPIC_RUN_STATE)
    assert "## Retry budget" in body
    assert "Consumed 4 of 6 (multiplier 2 × 3 stories)." in body


def test_renders_loud_fail_none_sentinel(tmp_path: pathlib.Path) -> None:
    body = _assemble(tmp_path, _VALID_EPIC_RUN_STATE)
    assert "## ✓ Loud-Fail Markers — None" in body


def test_renders_epic_budget_exhausted_marker(tmp_path: pathlib.Path) -> None:
    """AC-2: the per-epic `epic-budget-exhausted` marker renders via the SAME
    Story 6.1 loud-fail-block structure; the assembler SYNTHESIZES the
    pointer-context fields (epic_id / run_id / consumed / effective_budget)
    from the EpicRunState since the cache does not persist marker_contexts.
    """
    body = _assemble(tmp_path, _BUDGET_PAUSED_EPIC_RUN_STATE)
    assert "## ⚠️ Loud-Fail Markers" in body
    assert "### epic-budget-exhausted" in body
    # The synthesized context interpolates into the actionable pointer.
    assert "consumed `4` of `4`" in body
    assert "epic `epic-15` (run `run-1`)" in body


def test_section_order_is_deterministic(tmp_path: pathlib.Path) -> None:
    body = _assemble(tmp_path, _BUDGET_PAUSED_EPIC_RUN_STATE)
    h2 = [line for line in body.splitlines() if line.startswith("## ")]
    assert h2 == [
        "## Stories",
        "## 💸 Epic Cost Partition",
        "## Retry budget",
        "## ⚠️ Loud-Fail Markers",
    ]


# --------------------------------------------------------------------------- #
# Idempotency (AC-4)                                                          #
# --------------------------------------------------------------------------- #


def test_regeneration_is_byte_identical(tmp_path: pathlib.Path) -> None:
    """AC-4: re-rendering from an UNCHANGED cache with the same deterministic
    `generated_at` produces byte-identical output at the SAME path."""
    ers = _write_ers(tmp_path, _VALID_EPIC_RUN_STATE)
    bundle_root = tmp_path / "_bmad-output" / "epic-pr-bundles"
    first = assemble_epic_bundle(
        epic_id="epic-15",
        run_id="run-1",
        epic_run_state_path=ers,
        bundle_root=bundle_root,
        generated_at=_FIXED,
    )
    first_bytes = first.bundle_path.read_bytes()
    second = assemble_epic_bundle(
        epic_id="epic-15",
        run_id="run-1",
        epic_run_state_path=ers,
        bundle_root=bundle_root,
        generated_at=_FIXED,
    )
    assert second.bundle_path == first.bundle_path
    assert second.bundle_path.read_bytes() == first_bytes


def test_naive_generated_at_rejected(tmp_path: pathlib.Path) -> None:
    ers = _write_ers(tmp_path, _VALID_EPIC_RUN_STATE)
    with pytest.raises(ValueError, match="timezone-aware"):
        assemble_epic_bundle(
            epic_id="epic-15",
            run_id="run-1",
            epic_run_state_path=ers,
            bundle_root=tmp_path / "b",
            generated_at=datetime(2026, 6, 2, 12, 0, 0),  # naive
        )


# --------------------------------------------------------------------------- #
# compute_epic_bundle_path                                                    #
# --------------------------------------------------------------------------- #


def test_compute_epic_bundle_path_happy(tmp_path: pathlib.Path) -> None:
    path = compute_epic_bundle_path(
        repo_root=tmp_path, epic_id="epic-15", run_id="run-1"
    )
    assert path == (
        tmp_path / "_bmad-output" / "epic-pr-bundles" / "epic-15" / "run-1.md"
    )


@pytest.mark.parametrize("bad", ["", "/abs/epic", "../escape", "a/../b"])
def test_compute_epic_bundle_path_rejects_bad_epic_id(
    tmp_path: pathlib.Path, bad: str
) -> None:
    with pytest.raises(EpicBundlePathInvariantViolation):
        compute_epic_bundle_path(repo_root=tmp_path, epic_id=bad, run_id="run-1")


@pytest.mark.parametrize("bad", ["", "/abs/run", "../escape", "a/../b"])
def test_compute_epic_bundle_path_rejects_bad_run_id(
    tmp_path: pathlib.Path, bad: str
) -> None:
    with pytest.raises(EpicBundlePathInvariantViolation):
        compute_epic_bundle_path(repo_root=tmp_path, epic_id="epic-15", run_id=bad)


# --------------------------------------------------------------------------- #
# main() failure routing (AC-6)                                              #
# --------------------------------------------------------------------------- #


def _main_argv(
    *, epic_run_state_path: pathlib.Path, bundle_root: pathlib.Path,
    epic_id: str = "epic-15", run_id: str = "run-1",
) -> list[str]:
    return [
        "--epic-id", epic_id,
        "--run-id", run_id,
        "--epic-run-state-path", str(epic_run_state_path),
        "--bundle-root", str(bundle_root),
    ]


def test_main_happy_path(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    ers = _write_ers(tmp_path, _VALID_EPIC_RUN_STATE)
    bundle_root = tmp_path / "_bmad-output" / "epic-pr-bundles"
    rc = bundle_assembly_epic.main(
        _main_argv(epic_run_state_path=ers, bundle_root=bundle_root)
    )
    assert rc == 0
    assert (bundle_root / "epic-15" / "run-1.md").exists()


def test_main_missing_epic_run_state_exit_1(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pre-condition failure: missing cache → exit 1, NO bundle-assembly-failed
    marker, NO diagnostic file (remediation-shape discipline; AC-6)."""
    bundle_root = tmp_path / "_bmad-output" / "epic-pr-bundles"
    rc = bundle_assembly_epic.main(
        _main_argv(
            epic_run_state_path=tmp_path / "absent.yaml", bundle_root=bundle_root
        )
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "EpicRunStateNotFound" in err
    assert BUNDLE_ASSEMBLY_FAILED_MARKER not in err
    assert not (bundle_root / "epic-15" / "run-1.assembly-failure.log").exists()


def test_main_epic_id_mismatch_exit_1(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mismatched epic-run-state (valid, but for a different epic) → exit 1,
    NO marker (mirrors RunStateStoryIdMismatch; AC-6)."""
    ers = _write_ers(tmp_path, _VALID_EPIC_RUN_STATE)  # epic_id == epic-15
    bundle_root = tmp_path / "_bmad-output" / "epic-pr-bundles"
    rc = bundle_assembly_epic.main(
        _main_argv(
            epic_run_state_path=ers, bundle_root=bundle_root, epic_id="epic-99"
        )
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "EpicRunStateEpicIdMismatch" in err
    assert BUNDLE_ASSEMBLY_FAILED_MARKER not in err


def test_main_invalid_epic_id_exit_1(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """EpicBundlePathInvariantViolation (empty epic_id) is a pre-condition failure
    → exit 1, NO bundle-assembly-failed marker (remediation-shape discipline;
    regression for the review-found fix)."""
    ers = _write_ers(tmp_path, _VALID_EPIC_RUN_STATE)
    bundle_root = tmp_path / "_bmad-output" / "epic-pr-bundles"
    rc = bundle_assembly_epic.main(
        _main_argv(epic_run_state_path=ers, bundle_root=bundle_root, epic_id="")
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "EpicBundlePathInvariantViolation" in err
    assert BUNDLE_ASSEMBLY_FAILED_MARKER not in err
    assert not (bundle_root / "" / "run-1.assembly-failure.log").exists()


def test_main_shape_mismatch_routes_assembly_failure(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Assembler-logic failure: an epic-run-state that parses as YAML but does
    NOT validate as EpicRunState (shape mismatch / enum unresolved) → routes
    through surface_assembly_failure (Channel 1 file + Channel 2 stderr) and
    exits with the Story 6.9 distinct exit code (AC-6)."""
    ers = _write_ers(
        tmp_path,
        # current_state carries an out-of-enum value → ValidationError.
        _VALID_EPIC_RUN_STATE.replace(
            'current_state: "epic-paused-on-escalation"',
            'current_state: "epic-not-a-real-state"',
        ),
    )
    bundle_root = tmp_path / "_bmad-output" / "epic-pr-bundles"
    rc = bundle_assembly_epic.main(
        _main_argv(epic_run_state_path=ers, bundle_root=bundle_root)
    )
    assert rc == BUNDLE_ASSEMBLY_FAILED_EXIT_CODE
    err = capsys.readouterr().err
    assert BUNDLE_ASSEMBLY_FAILED_MARKER in err
    # Channel 1 fallback diagnostic file materialized under the epic_id dir.
    log = bundle_root / "epic-15" / "run-1.assembly-failure.log"
    assert log.exists()


def test_main_is_callable() -> None:
    assert callable(bundle_assembly_epic.main)
