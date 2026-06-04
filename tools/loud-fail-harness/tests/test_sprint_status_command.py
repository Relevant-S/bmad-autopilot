"""Tests for the ``/bmad-automation status --sprint`` substrate (Story 16.4).

Contract-coverage matrix (review-enforced; parallel to
``test_epic_status_command.py`` one scope down):

Public API (AC-1):
    [x] __all__ enumerates the public surface                          → test_module_exports_documented_public_api
    [x] SprintStatusRequest rejects a relative project_root            → test_request_rejects_relative_project_root

inspect_sprint (AC-1 / AC-2 / AC-3 / AC-4 / AC-6):
    [x] sprint-status-found payload reuses build_sprint_status_artifact → test_inspect_sprint_found_payload
    [x] sprint-status-no-run-state when no cache at the path           → test_inspect_sprint_no_run_state
    [x] sprint-id-mismatch when the cache is for another sprint        → test_inspect_sprint_id_mismatch
    [x] malformed cache raises SprintStatusCommandError (exit-2 shape) → test_inspect_sprint_parse_error_raises
    [x] naive generated_at raises SprintStatusCommandError            → test_inspect_sprint_naive_generated_at_raises
    [x] inspect_sprint does NOT mutate the caches (AC-4)              → test_inspect_sprint_does_not_mutate_caches

Renderers (AC-2 / AC-3):
    [x] human render carries the AC-2 sections + sprint-state tree     → test_render_human_sections_present
    [x] per-story rows nest under their epic_id (the tree)            → test_render_human_tree_nesting
    [x] unassigned (epic_id null) stories under (unassigned)          → test_render_human_unassigned_group
    [x] AC-3 drill-down pointers + scoped markers inline              → test_render_human_drilldown_and_scoped_markers
    [x] (no active markers) placeholder when empty                    → test_render_human_no_markers_placeholder
    [x] human render is byte-stable (pinned generated_at)             → test_render_human_byte_stable
    [x] JSON render is byte-stable + field-order stable               → test_render_json_byte_stable

main CLI (AC-1 / AC-6 / AC-9):
    [x] --sprint is required                                          → test_main_sprint_arg_required
    [x] exit 0 on sprint-status-found (human)                         → test_main_exit_0_human
    [x] exit 0 on sprint-status-found (--json)                        → test_main_exit_0_json
    [x] exit 1 on sprint-status-no-run-state                          → test_main_exit_1_no_run_state
    [x] exit 1 on sprint-id-mismatch                                  → test_main_exit_1_id_mismatch
    [x] exit 2 on malformed cache                                     → test_main_exit_2_parse_error
"""

from __future__ import annotations

import hashlib
import pathlib
from datetime import datetime, timezone

import pytest

from loud_fail_harness import sprint_status_command as sprint_status_command_module
from loud_fail_harness.sprint_status_artifact import SprintStatusArtifact
from loud_fail_harness.sprint_status_command import (
    SprintStatusCommandError,
    SprintStatusRequest,
    inspect_sprint,
    main,
    render_sprint_inspection_human,
    render_sprint_inspection_json,
)

_FIXED = datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc)

_CLEAN_SPRINT = """schema_version: "1.0"
sprint_id: "sprint-1"
run_id: "run-1"
current_state: "sprint-complete"
epic_ids:
  - "epic-16"
  - "epic-17"
per_epic_status:
  "epic-16": "epic-complete"
  "epic-17": "epic-complete"
unassigned_story_ids: []
per_sprint_retry_budget:
  multiplier: 2
  epic_count: 2
  effective_budget: 4
  consumed: 1
active_markers: []
"""

_EPIC_16_COMPLETE = """schema_version: "1.0"
epic_id: "epic-16"
run_id: "run-1"
current_state: "epic-complete"
story_ids:
  - "16-1-a"
  - "16-2-b"
per_story_status:
  "16-1-a": "merge-ready"
  "16-2-b": "done"
per_epic_retry_budget:
  multiplier: 2
  story_count: 2
  effective_budget: 4
  consumed: 1
per_epic_cost_partition:
  per_story_cost:
    "16-1-a": 1.50
    "16-2-b": 2.00
  epic_cost_total: 3.50
active_markers: []
"""

_EPIC_17_COMPLETE = """schema_version: "1.0"
epic_id: "epic-17"
run_id: "run-1"
current_state: "epic-complete"
story_ids:
  - "17-1-a"
per_story_status:
  "17-1-a": "done"
per_epic_retry_budget:
  multiplier: 2
  story_count: 1
  effective_budget: 2
  consumed: 0
per_epic_cost_partition:
  per_story_cost:
    "17-1-a": 1.00
  epic_cost_total: 1.00
active_markers: []
"""

_PAUSED_SPRINT = """schema_version: "1.0"
sprint_id: "sprint-2"
run_id: "run-2"
current_state: "sprint-paused-on-escalation"
epic_ids:
  - "epic-16"
unassigned_story_ids: []
per_epic_status:
  "epic-16": "epic-paused-on-escalation"
per_sprint_retry_budget:
  multiplier: 2
  epic_count: 1
  effective_budget: 2
  consumed: 2
active_markers:
  - "sprint-escalation-rate-exceeded"
"""

_EPIC_16_ESCALATED = """schema_version: "1.0"
epic_id: "epic-16"
run_id: "run-2"
current_state: "epic-paused-on-escalation"
story_ids:
  - "16-1-a"
  - "16-2-b"
  - "16-3-c"
per_story_status:
  "16-1-a": "merge-ready"
  "16-2-b": "escalated"
  "16-3-c": "in-progress"
per_epic_retry_budget:
  multiplier: 2
  story_count: 3
  effective_budget: 6
  consumed: 4
per_epic_cost_partition:
  per_story_cost:
    "16-1-a": 1.25
    "16-2-b": 0.80
    "16-3-c": 0.0
  epic_cost_total: 2.05
active_markers:
  - "epic-budget-exhausted"
"""


def _automation_dir(repo_root: pathlib.Path) -> pathlib.Path:
    path = repo_root / "_bmad" / "automation"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_sprint(repo_root: pathlib.Path, body: str) -> pathlib.Path:
    path = _automation_dir(repo_root) / "sprint-run-state.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _write_epic(repo_root: pathlib.Path, epic_id: str, body: str) -> pathlib.Path:
    path = _automation_dir(repo_root) / f"epic-run-state-{epic_id}.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _clean_workspace(repo_root: pathlib.Path) -> list[pathlib.Path]:
    return [
        _write_sprint(repo_root, _CLEAN_SPRINT),
        _write_epic(repo_root, "epic-16", _EPIC_16_COMPLETE),
        _write_epic(repo_root, "epic-17", _EPIC_17_COMPLETE),
    ]


def _paused_workspace(repo_root: pathlib.Path) -> list[pathlib.Path]:
    return [
        _write_sprint(repo_root, _PAUSED_SPRINT),
        _write_epic(repo_root, "epic-16", _EPIC_16_ESCALATED),
    ]


def _found_artifact(
    tmp_path: pathlib.Path, *, paused: bool = False
) -> SprintStatusArtifact:
    if paused:
        _paused_workspace(tmp_path)
        sprint_id = "sprint-2"
    else:
        _clean_workspace(tmp_path)
        sprint_id = "sprint-1"
    request = SprintStatusRequest(
        sprint_id=sprint_id, project_root=tmp_path, generated_at=_FIXED
    )
    outcome = inspect_sprint(request)
    assert outcome.action == "sprint-status-found"
    assert outcome.artifact is not None
    return outcome.artifact


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def test_module_exports_documented_public_api() -> None:
    expected = {
        "SprintStatusCommandError",
        "SprintStatusOutcome",
        "SprintStatusRequest",
        "inspect_sprint",
        "main",
        "render_no_sprint_run_state_diagnostic",
        "render_sprint_id_mismatch_diagnostic",
        "render_sprint_inspection_human",
        "render_sprint_inspection_json",
    }
    assert set(sprint_status_command_module.__all__) == expected


def test_request_rejects_relative_project_root() -> None:
    with pytest.raises(ValueError):
        SprintStatusRequest(sprint_id="sprint-1", project_root=pathlib.Path("rel"))


# --------------------------------------------------------------------------- #
# inspect_sprint                                                              #
# --------------------------------------------------------------------------- #


def test_inspect_sprint_found_payload(tmp_path: pathlib.Path) -> None:
    _clean_workspace(tmp_path)
    request = SprintStatusRequest(
        sprint_id="sprint-1", project_root=tmp_path, generated_at=_FIXED
    )
    outcome = inspect_sprint(request)
    assert outcome.action == "sprint-status-found"
    assert outcome.diagnostic is None
    art = outcome.artifact
    assert isinstance(art, SprintStatusArtifact)
    assert art.sprint_id == "sprint-1"
    assert art.run_id == "run-1"
    assert art.current_state == "sprint-complete"
    # The aggregate read was reused: Σ per-epic cost = 3.50 + 1.00.
    assert art.aggregate_cost_total == pytest.approx(4.50)
    assert art.retry_budget.consumed == 1
    assert art.retry_budget.effective_budget == 4
    assert [(r.epic_id, r.status) for r in art.per_epic] == [
        ("epic-16", "epic-complete"),
        ("epic-17", "epic-complete"),
    ]
    assert art.generated_at == _FIXED.isoformat()


def test_inspect_sprint_no_run_state(tmp_path: pathlib.Path) -> None:
    request = SprintStatusRequest(sprint_id="sprint-1", project_root=tmp_path)
    outcome = inspect_sprint(request)
    assert outcome.action == "sprint-status-no-run-state"
    assert outcome.artifact is None
    assert outcome.diagnostic is not None
    assert "no-in-flight-sprint-run-found-for-sprint-id" in outcome.diagnostic
    assert "run --sprint sprint-1" in outcome.diagnostic


def test_inspect_sprint_id_mismatch(tmp_path: pathlib.Path) -> None:
    _clean_workspace(tmp_path)
    request = SprintStatusRequest(sprint_id="sprint-99", project_root=tmp_path)
    outcome = inspect_sprint(request)
    assert outcome.action == "sprint-id-mismatch"
    assert outcome.artifact is None
    assert outcome.diagnostic is not None
    assert "sprint-id-mismatch" in outcome.diagnostic
    assert "requested sprint-99" in outcome.diagnostic
    assert "for sprint sprint-1" in outcome.diagnostic


def test_inspect_sprint_parse_error_raises(tmp_path: pathlib.Path) -> None:
    _write_sprint(tmp_path, "- not a mapping\n")
    request = SprintStatusRequest(sprint_id="sprint-1", project_root=tmp_path)
    with pytest.raises(SprintStatusCommandError) as excinfo:
        inspect_sprint(request)
    assert excinfo.value.reason == "sprint-status-build-error"


def test_inspect_sprint_naive_generated_at_raises(tmp_path: pathlib.Path) -> None:
    _clean_workspace(tmp_path)
    request = SprintStatusRequest(
        sprint_id="sprint-1",
        project_root=tmp_path,
        generated_at=datetime(2026, 6, 4, 12, 0, 0),
    )
    with pytest.raises(SprintStatusCommandError) as excinfo:
        inspect_sprint(request)
    assert excinfo.value.reason == "sprint-status-build-error"


def test_inspect_sprint_does_not_mutate_caches(tmp_path: pathlib.Path) -> None:
    """AC-4 structural witness: the sprint-run-state file's AND every per-epic
    cache file's mtime + sha256 are byte-identical before/after inspect_sprint
    (read-only invariant)."""
    cache_paths = _clean_workspace(tmp_path)
    before = {
        p: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in cache_paths
    }
    request = SprintStatusRequest(
        sprint_id="sprint-1", project_root=tmp_path, generated_at=_FIXED
    )
    inspect_sprint(request)
    after = {
        p: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in cache_paths
    }
    assert after == before


# --------------------------------------------------------------------------- #
# Renderers                                                                   #
# --------------------------------------------------------------------------- #


def _render(
    tmp_path: pathlib.Path, artifact: SprintStatusArtifact
) -> str:
    return render_sprint_inspection_human(
        artifact,
        sprint_run_state_path=(
            tmp_path / "_bmad" / "automation" / "sprint-run-state.yaml"
        ),
        repo_root=tmp_path,
    )


def test_render_human_sections_present(tmp_path: pathlib.Path) -> None:
    artifact = _found_artifact(tmp_path)
    rendered = _render(tmp_path, artifact)
    assert "## Sprint lifecycle state" in rendered
    assert "## Sprint state tree" in rendered
    assert "## Aggregate cost" in rendered
    assert "## Per-sprint retry budget" in rendered
    assert "## Escalation rate" in rendered
    assert "## Active loud-fail markers" in rendered
    assert "## Pointers" in rendered
    assert "state: sprint-complete" in rendered
    assert "Total: 4.50 USD." in rendered
    assert "Used 1 of 4." in rendered
    assert "sprint_status_artifact_path:" in rendered
    assert "sprint-status-artifact-sprint-1.md" in rendered


def test_render_human_tree_nesting(tmp_path: pathlib.Path) -> None:
    artifact = _found_artifact(tmp_path)
    rendered = _render(tmp_path, artifact)
    # The epic header precedes its nested per-story rows.
    idx_epic16 = rendered.index("- epic-16 → epic-complete")
    idx_story_a = rendered.index("  - 16-1-a → merge-ready")
    idx_epic17 = rendered.index("- epic-17 → epic-complete")
    assert idx_epic16 < idx_story_a < idx_epic17
    # epic-17's story nests under it.
    assert "  - 17-1-a → done" in rendered


def test_render_human_unassigned_group(tmp_path: pathlib.Path) -> None:
    _write_sprint(
        tmp_path,
        _CLEAN_SPRINT.replace(
            "unassigned_story_ids: []",
            'unassigned_story_ids:\n  - "99-1-loose"',
        ),
    )
    _write_epic(tmp_path, "epic-16", _EPIC_16_COMPLETE)
    _write_epic(tmp_path, "epic-17", _EPIC_17_COMPLETE)
    request = SprintStatusRequest(
        sprint_id="sprint-1", project_root=tmp_path, generated_at=_FIXED
    )
    outcome = inspect_sprint(request)
    assert outcome.artifact is not None
    rendered = _render(tmp_path, outcome.artifact)
    assert "- (unassigned)" in rendered
    assert "  - 99-1-loose → not-dispatched" in rendered


def test_render_human_drilldown_and_scoped_markers(tmp_path: pathlib.Path) -> None:
    artifact = _found_artifact(tmp_path, paused=True)
    rendered = _render(tmp_path, artifact)
    # AC-3: scoped active-markers union rendered inline with their scope.
    assert "- sprint-escalation-rate-exceeded [sprint]" in rendered
    assert "- epic-budget-exhausted [epic:epic-16]" in rendered
    # AC-3: drill-down pointers to the lower scopes.
    assert "/bmad-automation status --epic <epic-id>" in rendered
    assert "/bmad-automation status <story-id>" in rendered


def test_render_human_no_markers_placeholder(tmp_path: pathlib.Path) -> None:
    artifact = _found_artifact(tmp_path)
    rendered = _render(tmp_path, artifact)
    assert "(no active markers)" in rendered


def test_render_human_byte_stable(tmp_path: pathlib.Path) -> None:
    artifact = _found_artifact(tmp_path)
    assert _render(tmp_path, artifact) == _render(tmp_path, artifact)


def test_render_json_byte_stable(tmp_path: pathlib.Path) -> None:
    artifact = _found_artifact(tmp_path)
    first = render_sprint_inspection_json(artifact)
    assert first == render_sprint_inspection_json(artifact)
    reloaded = SprintStatusArtifact.model_validate_json(first)
    assert render_sprint_inspection_json(reloaded) == first


# --------------------------------------------------------------------------- #
# main CLI                                                                     #
# --------------------------------------------------------------------------- #


def test_main_sprint_arg_required(tmp_path: pathlib.Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--project-root", str(tmp_path)])
    assert excinfo.value.code == 2  # argparse usage error


def test_main_exit_0_human(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _clean_workspace(tmp_path)
    rc = main(["--sprint", "sprint-1", "--project-root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "## Sprint lifecycle state" in out
    assert "## Sprint state tree" in out
    assert "sprint-1" in out


def test_main_exit_0_json(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _clean_workspace(tmp_path)
    rc = main(["--sprint", "sprint-1", "--project-root", str(tmp_path), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"sprint_id": "sprint-1"' in out


def test_main_exit_1_no_run_state(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["--sprint", "sprint-1", "--project-root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "no-in-flight-sprint-run-found-for-sprint-id" in err


def test_main_exit_1_id_mismatch(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _clean_workspace(tmp_path)
    rc = main(["--sprint", "sprint-99", "--project-root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "sprint-id-mismatch" in err


def test_main_exit_2_parse_error(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_sprint(tmp_path, "- not a mapping\n")
    rc = main(["--sprint", "sprint-1", "--project-root", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "harness-level error" in err


def test_main_exit_2_render_error(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P1 review patch: render exceptions (e.g. SprintArtifactPathInvariantViolation
    from compute_sprint_status_artifact_path on a pathological sprint_id) route to
    exit 2 + stderr via the Pattern-5 loud-fail boundary in main, not an unhandled
    traceback with OS exit-code 1."""
    _clean_workspace(tmp_path)

    import loud_fail_harness.sprint_status_command as _mod

    def _raising_render(*args: object, **kwargs: object) -> str:
        raise ValueError("simulated path-invariant render failure")

    monkeypatch.setattr(_mod, "render_sprint_inspection_human", _raising_render)
    rc = main(["--sprint", "sprint-1", "--project-root", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "harness-level error" in err
    assert "render failed" in err
