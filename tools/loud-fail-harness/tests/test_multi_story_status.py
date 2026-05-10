"""Contract-coverage matrix for the multi-story status substrate (Story 8.5).

This docstring IS the contract-coverage checklist required by AC-9. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced (parallel to ``tests/test_status_command.py``,
``tests/test_resume_command.py``, and ``tests/test_cross_state_recovery.py``).

AC-1 — Module-level invariants (2):
    [x] test_module_exports_documented_public_api
    [x] test_multi_story_status_classified_as_shared_substrate_by_pluggability_gate

AC-2 — Discovery walk (4):
    [x] test_enumerate_stories_walks_automation_dir_for_run_state_files
    [x] test_enumerate_stories_walks_sprint_status_for_non_terminal_entries
    [x] test_enumerate_stories_unions_run_state_and_sprint_status_candidates_dedup
    [x] test_enumerate_stories_skips_terminal_sprint_status_entries

AC-2 — Empty listing (2):
    [x] test_enumerate_stories_returns_listing_empty_when_no_candidates
    [x] test_render_listing_empty_message_returns_canonical_string

AC-2 — Single-story projection (3):
    [x] test_enumerate_stories_projects_status_inspection_to_story_row_summary
    [x] test_enumerate_stories_uses_resolve_retry_rounds_false_for_per_story_inspection
    [x] test_enumerate_stories_omits_sprint_status_only_candidate_with_no_run_state

AC-3 — Orphan detection + emission (5):
    [x] test_enumerate_stories_emits_orphan_marker_when_story_doc_missing
    [x] test_enumerate_stories_orphan_context_contains_required_fields
    [x] test_enumerate_stories_orphan_row_has_is_orphan_true
    [x] test_enumerate_stories_does_not_emit_when_story_doc_present
    [x] test_enumerate_stories_does_not_auto_purge_orphan_run_state_file

AC-4 / AC-5 — Render (4):
    [x] test_render_story_listing_human_contains_summary_and_stories_sections
    [x] test_render_story_listing_human_marks_orphan_rows_with_prefix
    [x] test_render_story_listing_human_byte_stable_on_identical_input
    [x] test_render_story_listing_json_round_trip_stable

AC-6 — Write-surface invariant (2):
    [x] test_enumerate_stories_does_not_mutate_run_state_files
    [x] test_multi_story_status_only_writes_orphan_markers

AC-1 / AC-12 — CLI smoke (4):
    [x] test_main_exits_zero_on_listing_found_default_render
    [x] test_main_exits_zero_on_listing_found_with_json_flag
    [x] test_main_exits_zero_on_listing_empty
    [x] test_main_exits_two_on_substrate_error
"""

from __future__ import annotations

import ast
import datetime
import hashlib
import inspect as _inspect
import json
import pathlib
import subprocess
from typing import Any

import pytest

from loud_fail_harness import multi_story_status as multi_story_status_module
from loud_fail_harness.multi_story_status import (
    ListingOutcome,
    ListingRequest,
    MultiStoryStatusError,
    StoryListing,
    StoryRowSummary,
    enumerate_stories,
    main,
    render_listing_empty_message,
    render_story_listing_human,
    render_story_listing_json,
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


def _run_git(*args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture(scope="function")
def tmp_project(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a fresh tmp_path-rooted git repo with the canonical
    BMAD project layout. Mirrors the Story 8.4 ``tmp_project`` fixture.
    """
    _run_git("init", "-b", "main", cwd=tmp_path)
    _run_git("config", "user.email", "test@bmad-automation.local", cwd=tmp_path)
    _run_git("config", "user.name", "BMAD Test", cwd=tmp_path)
    _run_git("config", "commit.gpgsign", "false", cwd=tmp_path)
    (tmp_path / "README.md").write_text("# initial\n", encoding="utf-8")
    _run_git("add", "README.md", cwd=tmp_path)
    _run_git("commit", "-m", "initial", cwd=tmp_path)
    (tmp_path / "_bmad-output" / "implementation-artifacts").mkdir(
        parents=True, exist_ok=True
    )
    (tmp_path / "_bmad" / "automation").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_run_state_yaml(
    project_root: pathlib.Path,
    *,
    story_id: str,
    filename: str = "run-state.yaml",
    current_state: str = "in-progress",
    branch_name: str = "bmad-automation/story/x",
    run_id: str = "r1",
    last_envelope_yaml: str = "null",
    active_markers: tuple[str, ...] = (),
) -> pathlib.Path:
    rs_path = project_root / "_bmad" / "automation" / filename
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    markers_yaml = (
        "[]"
        if not active_markers
        else "[" + ", ".join(f"'{m}'" for m in active_markers) + "]"
    )
    rs_path.write_text(
        f"schema_version: '1.3'\n"
        f"story_id: {story_id}\n"
        f"run_id: {run_id}\n"
        f"current_state: {current_state}\n"
        f"branch_name: {branch_name}\n"
        f"dispatched_specialist: null\n"
        f"last_envelope: {last_envelope_yaml}\n"
        f"retry_history: []\n"
        f"active_markers: {markers_yaml}\n"
        f"cost_to_date_by_specialist: {{}}\n"
        f"pending_qa_dispatch_payload: null\n",
        encoding="utf-8",
    )
    return rs_path


def _write_story_doc(project_root: pathlib.Path, story_id: str) -> pathlib.Path:
    target = (
        project_root
        / "_bmad-output"
        / "implementation-artifacts"
        / f"{story_id}-test-slug.md"
    )
    target.write_text(
        f"# Story {story_id}\n\nStatus: in-progress\n\n"
        "## Acceptance Criteria\n\n**AC-1 — body** placeholder.\n",
        encoding="utf-8",
    )
    return target


def _write_sprint_status(
    project_root: pathlib.Path, development_status: dict[str, str]
) -> pathlib.Path:
    target = (
        project_root / "_bmad-output" / "implementation-artifacts" / "sprint-status.yaml"
    )
    lines = ["development_status:"]
    for key, value in development_status.items():
        lines.append(f"  {key}: {value}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _make_inspection(
    *,
    story_id: str = "8-5-test",
    current_state: str = "in-progress",
    branch_name: str = "bmad-automation/story/8-5",
    run_id: str = "r1",
    last_envelope: dict[str, Any] | None = None,
    active_markers: tuple[str, ...] = (),
    story_doc_path: pathlib.Path | None = None,
    run_state_path: pathlib.Path | None = None,
) -> StoryInspection:
    return StoryInspection(
        story_id=story_id,
        current_state=current_state,  # type: ignore[arg-type]
        branch_name=branch_name,
        run_id=run_id,
        dispatched_specialist=None,
        last_envelope=last_envelope,
        active_markers=active_markers,
        retry_history=(),
        resolved_retry_rounds=None,
        dangling_retry_round_refs=(),
        run_state_path=run_state_path or pathlib.Path("/tmp/run-state.yaml"),
        per_specialist_log_dir=pathlib.Path("/tmp/logs"),
        story_doc_path=story_doc_path,
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )


def _stub_inspect_fn(
    inspections: dict[str, StoryInspection],
    *,
    no_run_state_for: tuple[str, ...] = (),
):
    """Build a stub ``inspect_story_fn`` that returns canned outcomes
    keyed by story_id. Captures the requests for assertion."""
    captured: list[StatusRequest] = []

    def _stub(request: StatusRequest) -> StatusOutcome:
        captured.append(request)
        if request.story_id in no_run_state_for:
            return StatusOutcome(
                action="status-no-run-state",
                inspection=None,
                diagnostic="status: no-in-flight-run-found-for-story-id: stub",
            )
        if request.story_id in inspections:
            return StatusOutcome(
                action="status-found",
                inspection=inspections[request.story_id],
                diagnostic=None,
            )
        # Default: synthesize a fresh status-found inspection.
        return StatusOutcome(
            action="status-found",
            inspection=_make_inspection(story_id=request.story_id),
            diagnostic=None,
        )

    _stub.captured = captured  # type: ignore[attr-defined]
    return _stub


def _list_marker_recorder():
    emissions: list[tuple[str, dict[str, Any]]] = []

    def _recorder(marker_class: str, context):
        emissions.append((marker_class, dict(context)))

    _recorder.emissions = emissions  # type: ignore[attr-defined]
    return _recorder


# --------------------------------------------------------------------------- #
# AC-1 — Module-level invariants                                              #
# --------------------------------------------------------------------------- #


def test_module_exports_documented_public_api() -> None:
    """The module's __all__ enumerates the AC-1 public API."""
    expected = {
        "ListingOutcome",
        "ListingRequest",
        "MultiStoryStatusError",
        "StoryListing",
        "StoryRowSummary",
        "enumerate_stories",
        "main",
        "render_listing_empty_message",
        "render_story_listing_human",
        "render_story_listing_json",
    }
    assert set(multi_story_status_module.__all__) == expected


def test_multi_story_status_classified_as_shared_substrate_by_pluggability_gate(
    tmp_project: pathlib.Path,
) -> None:
    """multi_story_status.py lives under tools/loud-fail-harness/src/ as
    shared substrate AND is therefore NOT enumerated by the
    pluggability gate's diagnostic surface (the gate scans agents/*.md
    only). Mirrors Story 8.4's identical assertion at
    ``tests/test_status_command.py``.
    """
    from loud_fail_harness.pluggability_gate import run_pluggability_gate

    inner_repo = pathlib.Path(__file__).resolve().parents[3]
    agents_dir = inner_repo / "agents"
    if not agents_dir.is_dir():
        pytest.skip("agents/ directory not present in this checkout")
    result = run_pluggability_gate(agents_dir)
    diagnostics_text = "\n".join(getattr(result, "violations", []) or [])
    assert "multi_story_status" not in diagnostics_text


# --------------------------------------------------------------------------- #
# AC-2 — Discovery walk                                                       #
# --------------------------------------------------------------------------- #


def test_enumerate_stories_walks_automation_dir_for_run_state_files(
    tmp_project: pathlib.Path,
) -> None:
    _write_run_state_yaml(tmp_project, story_id="8-5-alpha")
    _write_story_doc(tmp_project, "8-5-alpha")
    inspections = {
        "8-5-alpha": _make_inspection(
            story_id="8-5-alpha",
            story_doc_path=tmp_project
            / "_bmad-output"
            / "implementation-artifacts"
            / "8-5-alpha-test-slug.md",
        )
    }
    stub = _stub_inspect_fn(inspections)
    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=_list_marker_recorder(),
        inspect_story_fn=stub,
    )
    outcome = enumerate_stories(request)
    assert outcome.action == "listing-found"
    assert any(r.story_id == "8-5-alpha" for r in outcome.listing.rows)


def test_enumerate_stories_walks_sprint_status_for_non_terminal_entries(
    tmp_project: pathlib.Path,
) -> None:
    _write_sprint_status(
        tmp_project,
        {
            "8-5-alpha": "in-progress",
            "8-5-beta": "review",
            "8-5-gamma": "qa",
            "8-5-delta": "escalated",
        },
    )
    captured: list[str] = []

    def _stub(request: StatusRequest) -> StatusOutcome:
        captured.append(request.story_id)
        return StatusOutcome(
            action="status-found",
            inspection=_make_inspection(story_id=request.story_id),
            diagnostic=None,
        )

    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=_list_marker_recorder(),
        inspect_story_fn=_stub,
    )
    outcome = enumerate_stories(request)
    assert outcome.action == "listing-found"
    assert sorted(captured) == ["8-5-alpha", "8-5-beta", "8-5-delta", "8-5-gamma"]


def test_enumerate_stories_unions_run_state_and_sprint_status_candidates_dedup(
    tmp_project: pathlib.Path,
) -> None:
    _write_run_state_yaml(tmp_project, story_id="8-5-shared")
    _write_sprint_status(
        tmp_project,
        {"8-5-shared": "in-progress", "8-5-alt": "qa"},
    )
    captured: list[str] = []

    def _stub(request: StatusRequest) -> StatusOutcome:
        captured.append(request.story_id)
        return StatusOutcome(
            action="status-found",
            inspection=_make_inspection(
                story_id=request.story_id,
                story_doc_path=pathlib.Path("/exists"),
            ),
            diagnostic=None,
        )

    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=_list_marker_recorder(),
        inspect_story_fn=_stub,
    )
    enumerate_stories(request)
    # Dedup: shared story-id is not double-inspected.
    assert captured.count("8-5-shared") == 1
    assert sorted(captured) == ["8-5-alt", "8-5-shared"]


def test_enumerate_stories_skips_terminal_sprint_status_entries(
    tmp_project: pathlib.Path,
) -> None:
    _write_sprint_status(
        tmp_project,
        {
            "8-5-done": "done",
            "8-5-rfd": "ready-for-dev",
            "8-5-bl": "backlog",
            "epic-8": "in-progress",
            "epic-8-retrospective": "optional",
            "8-5-active": "in-progress",
        },
    )
    captured: list[str] = []

    def _stub(request: StatusRequest) -> StatusOutcome:
        captured.append(request.story_id)
        return StatusOutcome(
            action="status-found",
            inspection=_make_inspection(story_id=request.story_id),
            diagnostic=None,
        )

    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=_list_marker_recorder(),
        inspect_story_fn=_stub,
    )
    outcome = enumerate_stories(request)
    # Only the in-progress entry survives the filter.
    assert captured == ["8-5-active"]
    assert outcome.action == "listing-found"


# --------------------------------------------------------------------------- #
# AC-2 — Empty listing                                                        #
# --------------------------------------------------------------------------- #


def test_enumerate_stories_returns_listing_empty_when_no_candidates(
    tmp_project: pathlib.Path,
) -> None:
    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=_list_marker_recorder(),
        inspect_story_fn=_stub_inspect_fn({}),
    )
    outcome = enumerate_stories(request)
    assert outcome.action == "listing-empty"
    assert outcome.listing.rows == ()
    assert outcome.listing.orphan_count == 0
    assert outcome.listing.total_count == 0


def test_render_listing_empty_message_returns_canonical_string() -> None:
    msg = render_listing_empty_message()
    assert msg == "(no stories with non-terminal automator state found)"
    # Purity: byte-stable on repeat invocation.
    assert render_listing_empty_message() == msg


# --------------------------------------------------------------------------- #
# AC-2 — Single-story projection                                              #
# --------------------------------------------------------------------------- #


def test_enumerate_stories_projects_status_inspection_to_story_row_summary(
    tmp_project: pathlib.Path,
) -> None:
    _write_run_state_yaml(tmp_project, story_id="8-5-proj")
    _write_story_doc(tmp_project, "8-5-proj")
    inspection = _make_inspection(
        story_id="8-5-proj",
        current_state="qa",
        branch_name="bmad-automation/story/8-5-proj",
        active_markers=("alpha", "beta", "gamma"),
        last_envelope={"timestamp": "2026-05-09T12:00:00+00:00"},
        story_doc_path=tmp_project
        / "_bmad-output"
        / "implementation-artifacts"
        / "8-5-proj-test-slug.md",
    )
    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=_list_marker_recorder(),
        inspect_story_fn=_stub_inspect_fn({"8-5-proj": inspection}),
    )
    outcome = enumerate_stories(request)
    assert len(outcome.listing.rows) == 1
    row = outcome.listing.rows[0]
    assert row.story_id == "8-5-proj"
    assert row.current_state == "qa"
    assert row.marker_count == 3
    assert row.last_activity_timestamp == datetime.datetime.fromisoformat(
        "2026-05-09T12:00:00+00:00"
    )
    assert row.branch_name == "bmad-automation/story/8-5-proj"
    assert row.is_orphan is False


def test_enumerate_stories_uses_resolve_retry_rounds_false_for_per_story_inspection(
    tmp_project: pathlib.Path,
) -> None:
    _write_run_state_yaml(tmp_project, story_id="8-5-cheap")
    _write_story_doc(tmp_project, "8-5-cheap")
    captured: list[StatusRequest] = []

    def _stub(request: StatusRequest) -> StatusOutcome:
        captured.append(request)
        return StatusOutcome(
            action="status-found",
            inspection=_make_inspection(
                story_id=request.story_id,
                story_doc_path=pathlib.Path("/exists"),
            ),
            diagnostic=None,
        )

    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=_list_marker_recorder(),
        inspect_story_fn=_stub,
    )
    enumerate_stories(request)
    # Cheap-default invariant per epics.md:3320 verbatim.
    assert all(r.resolve_retry_rounds is False for r in captured)
    assert len(captured) == 1


def test_enumerate_stories_omits_sprint_status_only_candidate_with_no_run_state(
    tmp_project: pathlib.Path,
) -> None:
    _write_sprint_status(tmp_project, {"8-5-only": "in-progress"})
    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=_list_marker_recorder(),
        inspect_story_fn=_stub_inspect_fn({}, no_run_state_for=("8-5-only",)),
    )
    outcome = enumerate_stories(request)
    # Sprint-status-non-terminal-without-run-state is omitted (NOT an orphan).
    assert outcome.action == "listing-empty"
    assert outcome.listing.rows == ()


# --------------------------------------------------------------------------- #
# AC-3 — Orphan detection + emission                                          #
# --------------------------------------------------------------------------- #


def test_enumerate_stories_emits_orphan_marker_when_story_doc_missing(
    tmp_project: pathlib.Path,
) -> None:
    rs_path = _write_run_state_yaml(tmp_project, story_id="8-5-orphan")
    # Story-doc deliberately NOT written → orphan.
    inspection = _make_inspection(
        story_id="8-5-orphan",
        story_doc_path=None,
        run_state_path=rs_path,
    )
    recorder = _list_marker_recorder()
    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=recorder,
        inspect_story_fn=_stub_inspect_fn({"8-5-orphan": inspection}),
    )
    enumerate_stories(request)
    emissions = recorder.emissions  # type: ignore[attr-defined]
    assert len(emissions) == 1
    marker_class, _ctx = emissions[0]
    assert marker_class == "orphan-run-state-detected"


def test_enumerate_stories_orphan_context_contains_required_fields(
    tmp_project: pathlib.Path,
) -> None:
    rs_path = _write_run_state_yaml(tmp_project, story_id="8-5-orphan-ctx")
    inspection = _make_inspection(
        story_id="8-5-orphan-ctx", story_doc_path=None, run_state_path=rs_path
    )
    recorder = _list_marker_recorder()
    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=recorder,
        inspect_story_fn=_stub_inspect_fn({"8-5-orphan-ctx": inspection}),
    )
    enumerate_stories(request)
    _marker_class, ctx = recorder.emissions[0]  # type: ignore[attr-defined]
    assert ctx["story_id"] == "8-5-orphan-ctx"
    assert ctx["run_state_file_path"] == str(rs_path)
    assert "_bmad-output/implementation-artifacts" in ctx["expected_story_doc_dir"]
    assert "purge orphan run-state" in ctx["remediation"]
    assert "git log --diff-filter=D" in ctx["remediation"]


def test_enumerate_stories_orphan_row_has_is_orphan_true(
    tmp_project: pathlib.Path,
) -> None:
    rs_path = _write_run_state_yaml(tmp_project, story_id="8-5-orphan-row")
    inspection = _make_inspection(
        story_id="8-5-orphan-row", story_doc_path=None, run_state_path=rs_path
    )
    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=_list_marker_recorder(),
        inspect_story_fn=_stub_inspect_fn({"8-5-orphan-row": inspection}),
    )
    outcome = enumerate_stories(request)
    assert len(outcome.listing.rows) == 1
    assert outcome.listing.rows[0].is_orphan is True
    assert outcome.listing.orphan_count == 1


def test_enumerate_stories_does_not_emit_when_story_doc_present(
    tmp_project: pathlib.Path,
) -> None:
    _write_run_state_yaml(tmp_project, story_id="8-5-normal")
    _write_story_doc(tmp_project, "8-5-normal")
    inspection = _make_inspection(
        story_id="8-5-normal",
        story_doc_path=tmp_project
        / "_bmad-output"
        / "implementation-artifacts"
        / "8-5-normal-test-slug.md",
    )
    recorder = _list_marker_recorder()
    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=recorder,
        inspect_story_fn=_stub_inspect_fn({"8-5-normal": inspection}),
    )
    enumerate_stories(request)
    assert recorder.emissions == []  # type: ignore[attr-defined]


def test_enumerate_stories_does_not_auto_purge_orphan_run_state_file(
    tmp_project: pathlib.Path,
) -> None:
    rs_path = _write_run_state_yaml(tmp_project, story_id="8-5-no-purge")
    before_mtime = rs_path.stat().st_mtime_ns
    before_sha = hashlib.sha256(rs_path.read_bytes()).hexdigest()
    inspection = _make_inspection(
        story_id="8-5-no-purge", story_doc_path=None, run_state_path=rs_path
    )
    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=_list_marker_recorder(),
        inspect_story_fn=_stub_inspect_fn({"8-5-no-purge": inspection}),
    )
    enumerate_stories(request)
    assert rs_path.is_file()
    assert rs_path.stat().st_mtime_ns == before_mtime
    assert hashlib.sha256(rs_path.read_bytes()).hexdigest() == before_sha


# --------------------------------------------------------------------------- #
# AC-4 / AC-5 — Render                                                        #
# --------------------------------------------------------------------------- #


def _make_listing(
    rows: tuple[StoryRowSummary, ...],
) -> StoryListing:
    return StoryListing(
        rows=rows,
        orphan_count=sum(1 for r in rows if r.is_orphan),
        total_count=len(rows),
    )


def test_render_story_listing_human_contains_summary_and_stories_sections() -> None:
    rows = (
        StoryRowSummary(
            story_id="8-5-a",
            current_state="in-progress",
            marker_count=2,
            last_activity_timestamp=datetime.datetime.fromisoformat(
                "2026-05-09T01:00:00+00:00"
            ),
            branch_name="branch-a",
            is_orphan=False,
        ),
    )
    listing = _make_listing(rows)
    rendered = render_story_listing_human(listing)
    assert "# /bmad-automation status — multi-story listing" in rendered
    assert "## Summary" in rendered
    assert "total: 1" in rendered
    assert "orphans: 0" in rendered
    assert "## Stories" in rendered
    assert "8-5-a" in rendered
    assert "branch=branch-a" in rendered
    assert "markers=2" in rendered


def test_render_story_listing_human_marks_orphan_rows_with_prefix() -> None:
    rows = (
        StoryRowSummary(
            story_id="8-5-orph",
            current_state="in-progress",
            marker_count=1,
            last_activity_timestamp=None,
            branch_name="(unknown — orphan)",
            is_orphan=True,
        ),
    )
    listing = _make_listing(rows)
    rendered = render_story_listing_human(listing)
    assert "[ORPHAN] 8-5-orph" in rendered
    assert "## Loud-fail markers" in rendered
    assert "### orphan-run-state-detected — story 8-5-orph" in rendered
    assert "diagnostic_pointer:" in rendered
    assert "remediation:" in rendered


def test_render_story_listing_human_byte_stable_on_identical_input() -> None:
    rows = (
        StoryRowSummary(
            story_id="8-5-byte",
            current_state="qa",
            marker_count=0,
            last_activity_timestamp=None,
            branch_name="b",
            is_orphan=False,
        ),
    )
    listing = _make_listing(rows)
    a = render_story_listing_human(listing)
    b = render_story_listing_human(listing)
    assert a == b


def test_render_story_listing_json_round_trip_stable() -> None:
    rows = (
        StoryRowSummary(
            story_id="8-5-json",
            current_state="review",
            marker_count=4,
            last_activity_timestamp=datetime.datetime.fromisoformat(
                "2026-05-09T05:00:00+00:00"
            ),
            branch_name="b-json",
            is_orphan=False,
        ),
    )
    listing = _make_listing(rows)
    rendered = render_story_listing_json(listing)
    parsed = StoryListing.model_validate_json(rendered)
    second = render_story_listing_json(parsed)
    assert rendered == second
    assert json.loads(rendered)["total_count"] == 1


# --------------------------------------------------------------------------- #
# AC-6 — Write-surface invariant                                              #
# --------------------------------------------------------------------------- #


def test_enumerate_stories_does_not_mutate_run_state_files(
    tmp_project: pathlib.Path,
) -> None:
    rs_a = _write_run_state_yaml(
        tmp_project, story_id="8-5-mut-a", filename="run-state.yaml"
    )
    # Capture mtime + sha before the call.
    before = {
        rs_a: (rs_a.stat().st_mtime_ns, hashlib.sha256(rs_a.read_bytes()).hexdigest()),
    }
    _write_story_doc(tmp_project, "8-5-mut-a")
    inspection = _make_inspection(
        story_id="8-5-mut-a",
        story_doc_path=tmp_project
        / "_bmad-output"
        / "implementation-artifacts"
        / "8-5-mut-a-test-slug.md",
        run_state_path=rs_a,
    )
    request = ListingRequest(
        project_root=tmp_project,
        marker_recorder=_list_marker_recorder(),
        inspect_story_fn=_stub_inspect_fn({"8-5-mut-a": inspection}),
    )
    enumerate_stories(request)
    after_mtime = rs_a.stat().st_mtime_ns
    after_sha = hashlib.sha256(rs_a.read_bytes()).hexdigest()
    assert (after_mtime, after_sha) == before[rs_a]


def test_multi_story_status_only_writes_orphan_markers() -> None:
    """AC-6 structural assertion: the multi_story_status module's source
    contains NO write-shaped imports / calls EXCEPT the marker_recorder
    seam invocation for orphan-run-state-detected. Uses AST to inspect
    imports + call expressions so docstring mentions of forbidden
    names do not falsely trip the assertion."""
    src = _inspect.getsource(multi_story_status_module)
    tree = ast.parse(src)

    imported_names: set[str] = set()
    call_attr_names: set[str] = set()
    call_func_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.name)
                if alias.asname:
                    imported_names.add(alias.asname)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                call_attr_names.add(func.attr)
            elif isinstance(func, ast.Name):
                call_func_names.add(func.id)

    # AC-6 forbidden names: must not appear in imports OR as call targets.
    forbidden = {
        "record_marker_with_context",
        "commit_transition",
        "advance_run_state",
        "_default_run_state_writer",
        "default_artifact_writer",
        "make_event_log_appender",
    }
    for name in forbidden:
        assert name not in imported_names, (
            f"multi_story_status must NOT import {name!r} (AC-6 invariant)"
        )
        assert name not in call_attr_names, (
            f"multi_story_status must NOT call .{name}() (AC-6 invariant)"
        )
        assert name not in call_func_names, (
            f"multi_story_status must NOT call {name}() (AC-6 invariant)"
        )

    # No subprocess.run invocations.
    assert "subprocess" not in imported_names, (
        "multi_story_status must not import subprocess (AC-6 invariant)"
    )

    # No write-shaped pathlib operations.
    write_shaped_attrs = {
        "write_text",
        "write_bytes",
        "mkdir",
        "touch",
        "unlink",
    }
    leaked = write_shaped_attrs & call_attr_names
    assert not leaked, (
        f"multi_story_status must NOT invoke write-shaped pathlib operations; "
        f"found: {sorted(leaked)} (AC-6 invariant)"
    )

    # The ONLY emission call site is for orphan-run-state-detected.
    # Walk Call nodes whose attribute name is "marker_recorder" and check
    # the literal first arg.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match `request.marker_recorder(...)` OR `marker_recorder(...)`.
        is_seam_call = False
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "marker_recorder":
            is_seam_call = True
        elif isinstance(func, ast.Name) and func.id == "marker_recorder":
            is_seam_call = True
        if not is_seam_call:
            continue
        # Skip default_factory or DI-seam-default lambdas — only check
        # call-sites that pass a literal first arg.
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            assert first.value == "orphan-run-state-detected", (
                f"marker_recorder call passed unexpected literal "
                f"{first.value!r}; AC-6 invariant requires only "
                "'orphan-run-state-detected'"
            )
        elif isinstance(first, ast.Name) and first.id == "_ORPHAN_MARKER_CLASS":
            # Module-level constant; equivalent to literal.
            pass


# --------------------------------------------------------------------------- #
# AC-1 / AC-12 — CLI smoke                                                    #
# --------------------------------------------------------------------------- #


def test_main_exits_zero_on_listing_found_default_render(
    tmp_project: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_run_state_yaml(tmp_project, story_id="8-5-cli")
    _write_story_doc(tmp_project, "8-5-cli")
    rc = main(["--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "# /bmad-automation status — multi-story listing" in captured.out
    assert "## Summary" in captured.out


def test_main_exits_zero_on_listing_found_with_json_flag(
    tmp_project: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_run_state_yaml(tmp_project, story_id="8-5-cli-json")
    _write_story_doc(tmp_project, "8-5-cli-json")
    rc = main(["--project-root", str(tmp_project), "--json"])
    captured = capsys.readouterr()
    assert rc == 0
    parsed = json.loads(captured.out)
    assert parsed["total_count"] >= 1
    assert "rows" in parsed
    assert "orphan_count" in parsed


def test_main_exits_zero_on_listing_empty(
    tmp_project: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "(no stories with non-terminal automator state found)" in captured.out


def test_main_exits_two_on_substrate_error(
    tmp_project: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raising(_request: ListingRequest) -> ListingOutcome:
        raise MultiStoryStatusError(
            reason="simulated", diagnostic="simulated harness error"
        )

    monkeypatch.setattr(
        multi_story_status_module, "enumerate_stories", _raising
    )
    rc = main(["--project-root", str(tmp_project)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "harness-level error" in captured.err


# --------------------------------------------------------------------------- #
# Epic 1 retro Action #1 — find_repo_root() discipline                        #
# --------------------------------------------------------------------------- #


def test_find_repo_root_not_at_module_collection_time() -> None:
    """The multi_story_status SUBSTRATE module has no find_repo_root() call
    at module top-level (i.e., outside any function/class body)."""
    src = _inspect.getsource(multi_story_status_module)
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else None
            )
            assert name != "find_repo_root", (
                "find_repo_root() must not be called at module collection time"
            )
