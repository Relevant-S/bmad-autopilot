"""Tests for the sprint-status-artifact assembler (Story 16.3).

Coverage map (per the story's Task 6):
    [x] build rollup — per-epic table / per-story table / aggregate cost          → test_build_rollup_*
    [x] build rollup — escalation re-derivation matching 16.2's tally             → test_build_escalation_rate_rederived
    [x] build rollup — scoped active-markers union + de-dup                        → test_build_active_markers_union_deduped
    [x] build rollup — missing per-epic cache → not-dispatched row                 → test_build_missing_epic_cache_not_dispatched
    [x] build rollup — unassigned story → epic_id null, not-dispatched             → test_build_unassigned_story_row
    [x] compute path happy + empty/absolute/.. rejection                          → test_compute_path_*
    [x] naive generated_at rejected                                               → test_naive_generated_at_rejected
    [x] render byte-stability via fixed generated_at                              → test_regeneration_is_byte_identical
    [x] assemble writes to _bmad-output/sprints/ + no temp residue                → test_assemble_writes_to_sprints_dir
    [x] atomic-write — prior file intact on simulated (pre-write) failure          → test_prior_artifact_intact_on_validation_failure
    [x] NEGATIVE-SURFACE (AC-5) — clean + paused carry no subjective heading       → test_negative_surface_no_subjective_headings
    [x] NEGATIVE-SURFACE (AC-5) — subjective field unconstructable / schema reject → test_subjective_field_*
    [x] main: missing cache → exit 1 NO marker (pre-condition)                     → test_main_missing_cache_exit_1
    [x] main: sprint_id mismatch → exit 1 NO marker (pre-condition)                → test_main_mismatch_exit_1
    [x] main: shape mismatch → surface_assembly_failure + exit code (AC-7)         → test_main_shape_mismatch_routes_assembly_failure
    [x] main: happy path → exit 0 + writes artifact                               → test_main_happy_path
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone

import pytest

from loud_fail_harness import sprint_status_artifact
from loud_fail_harness.bundle_assembly_failure import BUNDLE_ASSEMBLY_FAILED_EXIT_CODE
from loud_fail_harness.sprint_status_artifact import (
    SprintArtifactPathInvariantViolation,
    SprintStatusArtifact,
    assemble_sprint_status_artifact,
    build_sprint_status_artifact,
    compute_sprint_status_artifact_path,
)
from loud_fail_harness.sprint_status_artifact_validator import (
    _SUBJECTIVE_HEADING_DENYLIST,
    validate_artifact_data,
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


def _write_epic(repo_root: pathlib.Path, epic_id: str, body: str) -> None:
    (_automation_dir(repo_root) / f"epic-run-state-{epic_id}.yaml").write_text(
        body, encoding="utf-8"
    )


def _clean_workspace(repo_root: pathlib.Path) -> pathlib.Path:
    srs = _write_sprint(repo_root, _CLEAN_SPRINT)
    _write_epic(repo_root, "epic-16", _EPIC_16_COMPLETE)
    _write_epic(repo_root, "epic-17", _EPIC_17_COMPLETE)
    return srs


def _paused_workspace(repo_root: pathlib.Path) -> pathlib.Path:
    srs = _write_sprint(repo_root, _PAUSED_SPRINT)
    _write_epic(repo_root, "epic-16", _EPIC_16_ESCALATED)
    return srs


# --------------------------------------------------------------------------- #
# build_sprint_status_artifact rollup
# --------------------------------------------------------------------------- #


def test_build_rollup_per_epic_and_aggregate_cost(tmp_path: pathlib.Path) -> None:
    srs = _clean_workspace(tmp_path)
    artifact = build_sprint_status_artifact(srs, repo_root=tmp_path, generated_at=_FIXED)

    assert artifact.sprint_id == "sprint-1"
    assert artifact.run_id == "run-1"
    assert artifact.current_state == "sprint-complete"
    assert [(r.epic_id, r.status) for r in artifact.per_epic] == [
        ("epic-16", "epic-complete"),
        ("epic-17", "epic-complete"),
    ]
    assert artifact.per_epic[0].cost_total == pytest.approx(3.50)
    assert artifact.per_epic[0].retries_consumed == 1
    assert artifact.per_epic[0].retries_budget == 4
    # Σ epic_cost_total
    assert artifact.aggregate_cost_total == pytest.approx(4.50)
    # retry-budget from the SPRINT cache, not the epic caches
    assert artifact.retry_budget.consumed == 1
    assert artifact.retry_budget.effective_budget == 4


def test_build_rollup_per_story_table(tmp_path: pathlib.Path) -> None:
    srs = _clean_workspace(tmp_path)
    artifact = build_sprint_status_artifact(srs, repo_root=tmp_path, generated_at=_FIXED)
    rows = [(r.story_id, r.epic_id, r.status, r.cost) for r in artifact.per_story]
    assert rows == [
        ("16-1-a", "epic-16", "merge-ready", pytest.approx(1.50)),
        ("16-2-b", "epic-16", "done", pytest.approx(2.00)),
        ("17-1-a", "epic-17", "done", pytest.approx(1.00)),
    ]


def test_build_escalation_rate_rederived(tmp_path: pathlib.Path) -> None:
    """AC-2: numerator = epics paused-on-escalation; denominator = terminal
    stories across epic caches. epic-16 paused-on-escalation with merge-ready +
    escalated + in-progress → 2 terminal, 1 escalation → rate 0.5."""
    srs = _paused_workspace(tmp_path)
    artifact = build_sprint_status_artifact(srs, repo_root=tmp_path, generated_at=_FIXED)
    assert artifact.escalation.escalated_stories == 1
    assert artifact.escalation.stories_completed == 2
    assert artifact.escalation.rate == pytest.approx(0.5)


def test_build_active_markers_union_deduped(tmp_path: pathlib.Path) -> None:
    srs = _paused_workspace(tmp_path)
    artifact = build_sprint_status_artifact(srs, repo_root=tmp_path, generated_at=_FIXED)
    pairs = [(m.marker_class, m.scope) for m in artifact.active_markers]
    assert ("sprint-escalation-rate-exceeded", "sprint") in pairs
    assert ("epic-budget-exhausted", "epic:epic-16") in pairs
    # de-dup on (marker_class, scope)
    assert len(pairs) == len(set(pairs))


def test_build_missing_epic_cache_not_dispatched(tmp_path: pathlib.Path) -> None:
    srs = _write_sprint(
        tmp_path,
        _CLEAN_SPRINT.replace('  - "epic-17"', '  - "epic-99"').replace(
            '  "epic-17": "epic-complete"', '  "epic-99": "epic-in-progress"'
        ),
    )
    _write_epic(tmp_path, "epic-16", _EPIC_16_COMPLETE)
    # epic-99 cache deliberately NOT written
    artifact = build_sprint_status_artifact(srs, repo_root=tmp_path, generated_at=_FIXED)
    epic_99 = next(r for r in artifact.per_epic if r.epic_id == "epic-99")
    assert epic_99.status == "not-dispatched"
    assert epic_99.cost_total == 0.0
    assert epic_99.retries_consumed == 0
    assert epic_99.retries_budget == 0
    # missing cache contributes no per-story rows and zero cost
    assert all(r.epic_id != "epic-99" for r in artifact.per_story)
    assert artifact.aggregate_cost_total == pytest.approx(3.50)


def test_build_unassigned_story_row(tmp_path: pathlib.Path) -> None:
    srs = _write_sprint(
        tmp_path,
        _CLEAN_SPRINT.replace(
            "unassigned_story_ids: []",
            'unassigned_story_ids:\n  - "99-1-loose"',
        ),
    )
    _write_epic(tmp_path, "epic-16", _EPIC_16_COMPLETE)
    _write_epic(tmp_path, "epic-17", _EPIC_17_COMPLETE)
    artifact = build_sprint_status_artifact(srs, repo_root=tmp_path, generated_at=_FIXED)
    loose = next(r for r in artifact.per_story if r.story_id == "99-1-loose")
    assert loose.epic_id is None
    assert loose.status == "not-dispatched"
    assert loose.cost == 0.0


# --------------------------------------------------------------------------- #
# path computation + generated_at
# --------------------------------------------------------------------------- #


def test_compute_path_happy(tmp_path: pathlib.Path) -> None:
    path = compute_sprint_status_artifact_path(repo_root=tmp_path, sprint_id="sprint-1")
    assert path == (
        tmp_path / "_bmad-output" / "sprints" / "sprint-status-artifact-sprint-1.md"
    )


@pytest.mark.parametrize("bad", ["", "/abs/sprint", "../escape", "a\x00b"])
def test_compute_path_rejects_bad_component(
    tmp_path: pathlib.Path, bad: str
) -> None:
    with pytest.raises(SprintArtifactPathInvariantViolation):
        compute_sprint_status_artifact_path(repo_root=tmp_path, sprint_id=bad)


def test_naive_generated_at_rejected(tmp_path: pathlib.Path) -> None:
    srs = _clean_workspace(tmp_path)
    with pytest.raises(ValueError, match="timezone-aware"):
        build_sprint_status_artifact(
            srs, repo_root=tmp_path, generated_at=datetime(2026, 6, 4, 12, 0, 0)
        )


# --------------------------------------------------------------------------- #
# assemble: render + atomic write
# --------------------------------------------------------------------------- #


def test_regeneration_is_byte_identical(tmp_path: pathlib.Path) -> None:
    srs = _clean_workspace(tmp_path)
    root = tmp_path / "_bmad-output" / "sprints"
    r1 = assemble_sprint_status_artifact(
        srs, repo_root=tmp_path, sprint_artifacts_root=root, generated_at=_FIXED
    )
    first = r1.artifact_path.read_text(encoding="utf-8")
    r2 = assemble_sprint_status_artifact(
        srs, repo_root=tmp_path, sprint_artifacts_root=root, generated_at=_FIXED
    )
    assert r2.artifact_path.read_text(encoding="utf-8") == first


def test_assemble_writes_to_sprints_dir(tmp_path: pathlib.Path) -> None:
    srs = _clean_workspace(tmp_path)
    root = tmp_path / "_bmad-output" / "sprints"
    result = assemble_sprint_status_artifact(
        srs, repo_root=tmp_path, sprint_artifacts_root=root, generated_at=_FIXED
    )
    assert result.artifact_path == root / "sprint-status-artifact-sprint-1.md"
    assert result.artifact_path.is_file()
    body = result.artifact_path.read_text(encoding="utf-8")
    assert body.startswith("# Sprint status artifact — sprint sprint-1 (run run-1)")
    assert "## Per-epic summary" in body
    assert "## Escalation rate" in body
    # no temp residue
    assert list(root.rglob("*.tmp")) == []


def test_prior_artifact_intact_on_validation_failure(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    srs = _clean_workspace(tmp_path)
    root = tmp_path / "_bmad-output" / "sprints"
    result = assemble_sprint_status_artifact(
        srs, repo_root=tmp_path, sprint_artifacts_root=root, generated_at=_FIXED
    )
    original = result.artifact_path.read_text(encoding="utf-8")

    def _reject(*_a: object, **_k: object) -> object:
        from loud_fail_harness.sprint_status_artifact_validator import (
            ArtifactValidationResult,
        )

        return ArtifactValidationResult(
            accepted=False, reason="simulated drift", offending="<root>"
        )

    monkeypatch.setattr(sprint_status_artifact, "validate_artifact_data", _reject)
    with pytest.raises(sprint_status_artifact.SprintArtifactSchemaViolation):
        assemble_sprint_status_artifact(
            srs, repo_root=tmp_path, sprint_artifacts_root=root, generated_at=_FIXED
        )
    # the pre-write failure leaves the prior artifact intact + no temp residue
    assert result.artifact_path.read_text(encoding="utf-8") == original
    assert list(root.rglob("*.tmp")) == []


# --------------------------------------------------------------------------- #
# NEGATIVE-SURFACE (AC-5): NOT a retrospective
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("workspace", ["clean", "paused"])
def test_negative_surface_no_subjective_headings(
    tmp_path: pathlib.Path, workspace: str
) -> None:
    srs = _clean_workspace(tmp_path) if workspace == "clean" else _paused_workspace(
        tmp_path
    )
    root = tmp_path / "_bmad-output" / "sprints"
    result = assemble_sprint_status_artifact(
        srs, repo_root=tmp_path, sprint_artifacts_root=root, generated_at=_FIXED
    )
    body = result.artifact_path.read_text(encoding="utf-8").lower()
    headings = [
        line.lstrip("#").strip()
        for line in body.splitlines()
        if line.strip().startswith("#")
    ]
    for heading in headings:
        for phrase in _SUBJECTIVE_HEADING_DENYLIST:
            assert phrase not in heading, f"subjective heading leaked: {heading!r}"


def test_subjective_field_unconstructable() -> None:
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError (extra=forbid)
        SprintStatusArtifact(
            sprint_id="s",
            run_id="r",
            current_state="sprint-complete",
            generated_at="2026-06-04T12:00:00+00:00",
            per_epic=(),
            per_story=(),
            aggregate_cost_total=0.0,
            retry_budget={"consumed": 0, "effective_budget": 0},
            escalation={"escalated_stories": 0, "stories_completed": 0, "rate": 0.0},
            active_markers=(),
            what_went_well="great sprint",  # type: ignore[call-arg]
        )


def test_subjective_field_rejected_by_schema() -> None:
    payload = {
        "sprint_id": "s",
        "run_id": "r",
        "current_state": "sprint-complete",
        "generated_at": "2026-06-04T12:00:00+00:00",
        "per_epic": [],
        "per_story": [],
        "aggregate_cost_total": 0.0,
        "retry_budget": {"consumed": 0, "effective_budget": 0},
        "escalation": {"escalated_stories": 0, "stories_completed": 0, "rate": 0.0},
        "active_markers": [],
        "recommendation": "ship faster",
    }
    verdict = validate_artifact_data(payload, schema_path=_repo_schema_path())
    assert not verdict.accepted


def _repo_schema_path() -> pathlib.Path:
    return (
        pathlib.Path(__file__).resolve().parents[3]
        / "schemas"
        / "sprint-status-artifact.yaml"
    )


# --------------------------------------------------------------------------- #
# main: failure routing + happy path
# --------------------------------------------------------------------------- #


def test_main_missing_cache_exit_1(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = sprint_status_artifact.main(
        [
            "--sprint-id",
            "sprint-1",
            "--run-id",
            "run-1",
            "--sprint-run-state-path",
            str(tmp_path / "_bmad" / "automation" / "sprint-run-state.yaml"),
            "--sprint-artifacts-root",
            str(tmp_path / "_bmad-output" / "sprints"),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "SprintRunStateNotFound" in err
    # pre-condition: NO bundle-assembly-failed diagnostic written
    assert list(tmp_path.rglob("*.assembly-failure.log")) == []


def test_main_mismatch_exit_1(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    srs = _clean_workspace(tmp_path)
    rc = sprint_status_artifact.main(
        [
            "--sprint-id",
            "WRONG",
            "--run-id",
            "run-1",
            "--sprint-run-state-path",
            str(srs),
            "--sprint-artifacts-root",
            str(tmp_path / "_bmad-output" / "sprints"),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 1
    assert "SprintRunStateMismatch" in capsys.readouterr().err


def test_main_shape_mismatch_routes_assembly_failure(
    tmp_path: pathlib.Path,
) -> None:
    # present-but-malformed sprint cache (missing required fields) → assembler-
    # logic failure → surface_assembly_failure + distinct exit code.
    srs = _write_sprint(tmp_path, "sprint_id: oops\n")
    artifacts_root = tmp_path / "_bmad-output" / "sprints"
    rc = sprint_status_artifact.main(
        [
            "--sprint-id",
            "oops",
            "--run-id",
            "run-1",
            "--sprint-run-state-path",
            str(srs),
            "--sprint-artifacts-root",
            str(artifacts_root),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == BUNDLE_ASSEMBLY_FAILED_EXIT_CODE
    # Channel 1 fallback diagnostic was written (always-on)
    assert list(artifacts_root.rglob("*.assembly-failure.log"))


def test_main_happy_path(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    srs = _clean_workspace(tmp_path)
    artifacts_root = tmp_path / "_bmad-output" / "sprints"
    rc = sprint_status_artifact.main(
        [
            "--sprint-id",
            "sprint-1",
            "--run-id",
            "run-1",
            "--sprint-run-state-path",
            str(srs),
            "--sprint-artifacts-root",
            str(artifacts_root),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("sprint-status-artifact-sprint-1.md")
    assert (artifacts_root / "sprint-status-artifact-sprint-1.md").is_file()
