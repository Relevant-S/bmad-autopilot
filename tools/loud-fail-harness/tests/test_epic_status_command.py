"""Tests for the ``/bmad-automation status --epic`` substrate (Story 15.4).

Contract-coverage matrix (review-enforced; parallel to
``test_status_command.py`` / ``test_multi_story_status.py``):

Public API (AC-1):
    [x] __all__ enumerates the public surface                              → test_module_exports_documented_public_api
    [x] EpicStatusRequest rejects a relative project_root                  → test_request_rejects_relative_project_root

inspect_epic (AC-1 / AC-2 / AC-3 / AC-4 / AC-6):
    [x] epic-status-found payload from a fixture cache                     → test_inspect_epic_found_payload
    [x] per-story marker_count projection (dispatched)                     → test_inspect_epic_projects_per_story_marker_count
    [x] AC-3 graceful degrade on an undispatched story                    → test_inspect_epic_undispatched_story_degrades
    [x] per-story rows preserve the cache story_ids order                 → test_inspect_epic_rows_follow_cache_order
    [x] epic-status-no-run-state when no cache at the path                → test_inspect_epic_no_run_state
    [x] epic-id-mismatch when the cache is for another epic               → test_inspect_epic_id_mismatch
    [x] malformed cache raises EpicStatusCommandError (exit-2 shape)      → test_inspect_epic_parse_error_raises
    [x] a per-story inspect error raises EpicStatusCommandError           → test_inspect_epic_per_story_error_raises
    [x] inspect_epic does NOT mutate the epic-run-state file (AC-4)       → test_inspect_epic_does_not_mutate_cache
    [x] status-found with inspection=None raises EpicStatusCommandError (P3) → test_inspect_epic_status_found_none_inspection_raises

Renderers (AC-2):
    [x] human render carries the AC-2 sections + pointers                 → test_render_human_sections_present
    [x] active-markers rendered in alphabetical order                     → test_render_human_markers_alphabetical
    [x] (no active markers) placeholder when empty                        → test_render_human_no_markers_placeholder
    [x] merge-ready and escalated per_story_status tags pass through      → test_render_human_per_story_status_tags
    [x] human render is byte-stable (render twice → identical)            → test_render_human_byte_stable
    [x] JSON render is byte-stable + field-order stable                   → test_render_json_byte_stable

main CLI (AC-1 / AC-6 / AC-7):
    [x] --epic is required                                                → test_main_epic_arg_required
    [x] exit 0 on epic-status-found (human)                               → test_main_exit_0_human
    [x] exit 0 on epic-status-found (--json)                              → test_main_exit_0_json
    [x] exit 1 on epic-status-no-run-state                               → test_main_exit_1_no_run_state
    [x] exit 1 on epic-id-mismatch                                        → test_main_exit_1_id_mismatch
    [x] exit 2 on malformed cache                                         → test_main_exit_2_parse_error
"""

from __future__ import annotations

import hashlib
import pathlib
from typing import Any

import pytest

from loud_fail_harness import epic_status_command as epic_status_command_module
from loud_fail_harness.epic_run_state import (
    EpicRunState,
    PerEpicCostPartition,
    PerEpicRetryBudget,
)
from loud_fail_harness.epic_status_command import (
    EpicInspection,
    EpicStatusCommandError,
    EpicStatusRequest,
    inspect_epic,
    main,
    render_epic_inspection_human,
    render_epic_inspection_json,
)
from loud_fail_harness.run_state import CostToDateBySpecialist
from loud_fail_harness.status_command import (
    StatusOutcome,
    StatusRequest,
    StoryInspection,
)


# --------------------------------------------------------------------------- #
# Fixtures + helpers                                                          #
# --------------------------------------------------------------------------- #


_STORY_A = "15-1-foo"
_STORY_B = "15-2-bar"


def _make_epic_run_state(
    *,
    epic_id: str = "epic-15",
    run_id: str = "run-epic-15-001",
    current_state: str = "epic-in-progress",
    story_ids: tuple[str, ...] = (_STORY_A, _STORY_B),
    per_story_status: dict[str, str] | None = None,
    consumed: int = 1,
    effective_budget: int = 4,
    multiplier: int = 2,
    story_count: int = 2,
    active_markers: tuple[str, ...] = (),
) -> EpicRunState:
    if per_story_status is None:
        per_story_status = {_STORY_A: "in-progress", _STORY_B: "ready-for-dev"}
    return EpicRunState(
        schema_version="1.0",
        epic_id=epic_id,
        run_id=run_id,
        current_state=current_state,  # type: ignore[arg-type]
        story_ids=story_ids,
        per_story_status=per_story_status,  # type: ignore[arg-type]
        per_epic_retry_budget=PerEpicRetryBudget(
            multiplier=multiplier,
            story_count=story_count,
            effective_budget=effective_budget,
            consumed=consumed,
        ),
        per_epic_cost_partition=PerEpicCostPartition(
            per_story_cost={sid: 0.0 for sid in story_ids},
            epic_cost_total=0.0,
        ),
        active_markers=active_markers,
    )


def _write_epic_run_state(
    project_root: pathlib.Path, state: EpicRunState
) -> pathlib.Path:
    path = project_root / "_bmad" / "automation" / "epic-run-state.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(), encoding="utf-8")
    return path


def _make_inspection(
    *,
    story_id: str,
    active_markers: tuple[str, ...] = (),
) -> StoryInspection:
    return StoryInspection(
        story_id=story_id,
        current_state="in-progress",
        branch_name="bmad-automation/story/x",
        run_id="r1",
        dispatched_specialist=None,
        last_envelope=None,
        active_markers=active_markers,
        retry_history=(),
        resolved_retry_rounds=None,
        dangling_retry_round_refs=(),
        run_state_path=pathlib.Path("/tmp/run-state.yaml"),
        per_specialist_log_dir=pathlib.Path("/tmp/logs"),
        story_doc_path=None,
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )


def _stub_inspect_fn(
    *,
    found: dict[str, tuple[str, ...]] | None = None,
    no_run_state_for: tuple[str, ...] = (),
):
    """Build a stub ``inspect_story_fn``. ``found`` maps story_id → its
    active_markers tuple (status-found); ``no_run_state_for`` lists ids that
    return status-no-run-state. Anything else defaults to status-found with
    no markers."""
    found = found or {}
    captured: list[StatusRequest] = []

    def _stub(request: StatusRequest) -> StatusOutcome:
        captured.append(request)
        if request.story_id in no_run_state_for:
            return StatusOutcome(
                action="status-no-run-state",
                inspection=None,
                diagnostic="status: no-in-flight-run-found-for-story-id: stub",
            )
        markers = found.get(request.story_id, ())
        return StatusOutcome(
            action="status-found",
            inspection=_make_inspection(
                story_id=request.story_id, active_markers=markers
            ),
            diagnostic=None,
        )

    _stub.captured = captured  # type: ignore[attr-defined]
    return _stub


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def test_module_exports_documented_public_api() -> None:
    expected = {
        "EpicInspection",
        "EpicStatusCommandError",
        "EpicStatusOutcome",
        "EpicStatusRequest",
        "EpicStoryRow",
        "inspect_epic",
        "main",
        "render_epic_id_mismatch_diagnostic",
        "render_epic_inspection_human",
        "render_epic_inspection_json",
        "render_no_epic_run_state_diagnostic",
    }
    assert set(epic_status_command_module.__all__) == expected


def test_request_rejects_relative_project_root() -> None:
    with pytest.raises(ValueError):
        EpicStatusRequest(epic_id="epic-15", project_root=pathlib.Path("rel"))


# --------------------------------------------------------------------------- #
# inspect_epic                                                                #
# --------------------------------------------------------------------------- #


def test_inspect_epic_found_payload(tmp_path: pathlib.Path) -> None:
    state = _make_epic_run_state(active_markers=("epic-budget-exhausted",))
    _write_epic_run_state(tmp_path, state)
    request = EpicStatusRequest(
        epic_id="epic-15",
        project_root=tmp_path,
        inspect_story_fn=_stub_inspect_fn(),
    )
    outcome = inspect_epic(request)
    assert outcome.action == "epic-status-found"
    assert outcome.diagnostic is None
    insp = outcome.inspection
    assert isinstance(insp, EpicInspection)
    assert insp.epic_id == "epic-15"
    assert insp.run_id == "run-epic-15-001"
    assert insp.current_state == "epic-in-progress"
    assert insp.active_markers == ("epic-budget-exhausted",)
    assert insp.per_epic_retry_budget.consumed == 1
    assert insp.per_epic_retry_budget.effective_budget == 4
    assert tuple(r.story_id for r in insp.per_story_rows) == (_STORY_A, _STORY_B)
    assert insp.per_story_rows[0].per_story_status == "in-progress"
    # Pointers.
    assert insp.epic_run_state_path == (
        tmp_path / "_bmad" / "automation" / "epic-run-state.yaml"
    )
    assert insp.epic_pr_bundle_path == (
        tmp_path
        / "_bmad-output"
        / "epic-pr-bundles"
        / "epic-15"
        / "run-epic-15-001.md"
    )


def test_inspect_epic_projects_per_story_marker_count(
    tmp_path: pathlib.Path,
) -> None:
    _write_epic_run_state(tmp_path, _make_epic_run_state())
    request = EpicStatusRequest(
        epic_id="epic-15",
        project_root=tmp_path,
        inspect_story_fn=_stub_inspect_fn(
            found={_STORY_A: ("review-layer-failed", "context-near-limit")}
        ),
    )
    outcome = inspect_epic(request)
    assert outcome.inspection is not None
    rows = {r.story_id: r for r in outcome.inspection.per_story_rows}
    assert rows[_STORY_A].dispatched is True
    assert rows[_STORY_A].marker_count == 2


def test_inspect_epic_undispatched_story_degrades(tmp_path: pathlib.Path) -> None:
    _write_epic_run_state(tmp_path, _make_epic_run_state())
    request = EpicStatusRequest(
        epic_id="epic-15",
        project_root=tmp_path,
        inspect_story_fn=_stub_inspect_fn(no_run_state_for=(_STORY_B,)),
    )
    outcome = inspect_epic(request)
    assert outcome.inspection is not None
    rows = {r.story_id: r for r in outcome.inspection.per_story_rows}
    # AC-3: undispatched story degrades gracefully — no crash, no halt.
    assert rows[_STORY_B].dispatched is False
    assert rows[_STORY_B].marker_count is None
    assert rows[_STORY_B].per_story_status == "ready-for-dev"


def test_inspect_epic_rows_follow_cache_order(tmp_path: pathlib.Path) -> None:
    state = _make_epic_run_state(
        story_ids=("15-3-zeta", "15-1-alpha", "15-2-mid"),
        per_story_status={
            "15-3-zeta": "in-progress",
            "15-1-alpha": "merge-ready",
            "15-2-mid": "escalated",
        },
        story_count=3,
    )
    _write_epic_run_state(tmp_path, state)
    request = EpicStatusRequest(
        epic_id="epic-15",
        project_root=tmp_path,
        inspect_story_fn=_stub_inspect_fn(),
    )
    outcome = inspect_epic(request)
    assert outcome.inspection is not None
    # Ordered by cache story_ids (epic-defined order), NOT lexicographic.
    assert tuple(r.story_id for r in outcome.inspection.per_story_rows) == (
        "15-3-zeta",
        "15-1-alpha",
        "15-2-mid",
    )


def test_inspect_epic_no_run_state(tmp_path: pathlib.Path) -> None:
    request = EpicStatusRequest(epic_id="epic-15", project_root=tmp_path)
    outcome = inspect_epic(request)
    assert outcome.action == "epic-status-no-run-state"
    assert outcome.inspection is None
    assert outcome.diagnostic is not None
    assert "no-in-flight-epic-run-found-for-epic-id" in outcome.diagnostic
    assert "run --epic epic-15" in outcome.diagnostic


def test_inspect_epic_id_mismatch(tmp_path: pathlib.Path) -> None:
    _write_epic_run_state(tmp_path, _make_epic_run_state(epic_id="epic-15"))
    request = EpicStatusRequest(epic_id="epic-99", project_root=tmp_path)
    outcome = inspect_epic(request)
    assert outcome.action == "epic-id-mismatch"
    assert outcome.inspection is None
    assert outcome.diagnostic is not None
    assert "epic-id-mismatch" in outcome.diagnostic
    assert "requested epic-99" in outcome.diagnostic
    assert "for epic epic-15" in outcome.diagnostic


def test_inspect_epic_parse_error_raises(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "_bmad" / "automation" / "epic-run-state.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("- not a mapping\n", encoding="utf-8")
    request = EpicStatusRequest(epic_id="epic-15", project_root=tmp_path)
    with pytest.raises(EpicStatusCommandError) as excinfo:
        inspect_epic(request)
    assert excinfo.value.reason == "epic-run-state-parse-error"


def test_inspect_epic_per_story_error_raises(tmp_path: pathlib.Path) -> None:
    _write_epic_run_state(tmp_path, _make_epic_run_state())

    def _boom(request: StatusRequest) -> StatusOutcome:
        raise RuntimeError("boom")

    request = EpicStatusRequest(
        epic_id="epic-15", project_root=tmp_path, inspect_story_fn=_boom
    )
    with pytest.raises(EpicStatusCommandError) as excinfo:
        inspect_epic(request)
    assert excinfo.value.reason == "inspect-story-error"


def test_inspect_epic_does_not_mutate_cache(tmp_path: pathlib.Path) -> None:
    """AC-4 structural witness: the epic-run-state file's mtime + sha256 are
    byte-identical before/after inspect_epic (read-only invariant)."""
    path = _write_epic_run_state(tmp_path, _make_epic_run_state())
    before = (
        path.stat().st_mtime_ns,
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    # Use the LIVE inspect_story (no stub) — per-story run-state is absent, so
    # it returns status-no-run-state, exercising the real read path.
    request = EpicStatusRequest(epic_id="epic-15", project_root=tmp_path)
    inspect_epic(request)
    after = (
        path.stat().st_mtime_ns,
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    assert after == before


def test_inspect_epic_status_found_none_inspection_raises(
    tmp_path: pathlib.Path,
) -> None:
    """P3: status-found with inspection=None raises EpicStatusCommandError
    (contract violation — not silently classified as undispatched)."""
    _write_epic_run_state(tmp_path, _make_epic_run_state())

    def _bad_fn(request: StatusRequest) -> StatusOutcome:
        return StatusOutcome(action="status-found", inspection=None, diagnostic=None)

    request = EpicStatusRequest(
        epic_id="epic-15", project_root=tmp_path, inspect_story_fn=_bad_fn
    )
    with pytest.raises(EpicStatusCommandError) as excinfo:
        inspect_epic(request)
    assert excinfo.value.reason == "inspect-story-contract-violated"


# --------------------------------------------------------------------------- #
# Renderers                                                                   #
# --------------------------------------------------------------------------- #


def _found_inspection(tmp_path: pathlib.Path, **kwargs: Any) -> EpicInspection:
    _write_epic_run_state(tmp_path, _make_epic_run_state(**kwargs))
    request = EpicStatusRequest(
        epic_id="epic-15",
        project_root=tmp_path,
        inspect_story_fn=_stub_inspect_fn(
            found={_STORY_A: ("review-layer-failed",)},
            no_run_state_for=(_STORY_B,),
        ),
    )
    outcome = inspect_epic(request)
    assert outcome.inspection is not None
    return outcome.inspection


def test_render_human_sections_present(tmp_path: pathlib.Path) -> None:
    insp = _found_inspection(tmp_path, active_markers=("epic-budget-exhausted",))
    rendered = render_epic_inspection_human(insp)
    assert "## Epic lifecycle state" in rendered
    assert "## Per-story status" in rendered
    assert "## Per-epic retry budget" in rendered
    assert "## Active loud-fail markers" in rendered
    assert "## Pointers" in rendered
    # per-story rows: dispatched marker count + undispatched annotation.
    assert f"{_STORY_A} → in-progress (markers=1)" in rendered
    assert "(not yet dispatched — no per-story run-state)" in rendered
    # retry-budget line mirrors the epic-bundle render.
    assert "Consumed 1 of 4 (multiplier 2 × 2 stories)." in rendered
    # pointers.
    assert "epic_run_state_path:" in rendered
    assert "epic_pr_bundle_path:" in rendered


def test_render_human_markers_alphabetical(tmp_path: pathlib.Path) -> None:
    insp = _found_inspection(
        tmp_path, active_markers=("epic-budget-exhausted", "context-near-limit")
    )
    rendered = render_epic_inspection_human(insp)
    idx_context = rendered.index("- context-near-limit")
    idx_budget = rendered.index("- epic-budget-exhausted")
    assert idx_context < idx_budget


def test_render_human_no_markers_placeholder(tmp_path: pathlib.Path) -> None:
    insp = _found_inspection(tmp_path, active_markers=())
    rendered = render_epic_inspection_human(insp)
    assert "(no active markers)" in rendered


def test_render_human_per_story_status_tags(tmp_path: pathlib.Path) -> None:
    """AC-2 — merge-ready and escalated per_story_status tags pass through
    intact in the human render (not just in-progress)."""
    state = _make_epic_run_state(
        per_story_status={_STORY_A: "merge-ready", _STORY_B: "escalated"},
    )
    _write_epic_run_state(tmp_path, state)
    request = EpicStatusRequest(
        epic_id="epic-15",
        project_root=tmp_path,
        inspect_story_fn=_stub_inspect_fn(),
    )
    outcome = inspect_epic(request)
    assert outcome.inspection is not None
    rendered = render_epic_inspection_human(outcome.inspection)
    assert f"{_STORY_A} → merge-ready" in rendered
    assert f"{_STORY_B} → escalated" in rendered


def test_render_human_byte_stable(tmp_path: pathlib.Path) -> None:
    insp = _found_inspection(tmp_path, active_markers=("epic-budget-exhausted",))
    assert render_epic_inspection_human(insp) == render_epic_inspection_human(insp)


def test_render_json_byte_stable(tmp_path: pathlib.Path) -> None:
    insp = _found_inspection(tmp_path, active_markers=("epic-budget-exhausted",))
    first = render_epic_inspection_json(insp)
    assert first == render_epic_inspection_json(insp)
    # Field-order stability: round-trip through the model preserves bytes.
    reloaded = EpicInspection.model_validate_json(first)
    assert render_epic_inspection_json(reloaded) == first


# --------------------------------------------------------------------------- #
# main CLI                                                                     #
# --------------------------------------------------------------------------- #


def test_main_epic_arg_required(tmp_path: pathlib.Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--project-root", str(tmp_path)])
    assert excinfo.value.code == 2  # argparse usage error


def test_main_exit_0_human(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_epic_run_state(tmp_path, _make_epic_run_state())
    rc = main(["--epic", "epic-15", "--project-root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "## Epic lifecycle state" in out
    assert "epic-15" in out


def test_main_exit_0_json(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_epic_run_state(tmp_path, _make_epic_run_state())
    rc = main(["--epic", "epic-15", "--project-root", str(tmp_path), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"epic_id": "epic-15"' in out


def test_main_exit_1_no_run_state(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["--epic", "epic-15", "--project-root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "no-in-flight-epic-run-found-for-epic-id" in err


def test_main_exit_1_id_mismatch(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_epic_run_state(tmp_path, _make_epic_run_state(epic_id="epic-15"))
    rc = main(["--epic", "epic-99", "--project-root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "epic-id-mismatch" in err


def test_main_exit_2_parse_error(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "_bmad" / "automation" / "epic-run-state.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("- not a mapping\n", encoding="utf-8")
    rc = main(["--epic", "epic-15", "--project-root", str(tmp_path)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "harness-level error" in err
