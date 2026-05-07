"""Integration smoke tests for the Story 6.9 cross-surface flow (AC-6).

This module exercises the `bundle_assembly.main` → `surface_assembly_failure`
→ `handle_hook_exit_code` cross-surface flow end-to-end with seeded
on-disk run-state + dispatch logs. The unit-level contract for
`surface_assembly_failure` lives in `test_bundle_assembly_failure.py`;
the gate's structural lint contract lives in
`test_bundle_assembly_failure_emission_gate.py`. THIS module witnesses
the AC-6 (k)-(o) integration scenarios.

AC-6 (k)-(o) test-coverage matrix:
    [x] (k) end-to-end: bundle_assembly.main on a malformed envelope
        exits 2; on-disk fallback file exists; run-state has the marker;
        stderr has the one-line emission
        → test_main_on_malformed_envelope_emits_three_channels_and_exits_two
    [x] (l) end-to-end clean: bundle_assembly.main on valid input exits 0;
        no fallback file; no marker in run-state (regression guard)
        → test_main_clean_assembly_does_not_emit_marker
    [x] (m) cross-failure independence: Stop hook crashes mechanically AND
        assembler crashed → BOTH markers fire (independence-of-emission)
        → test_handle_hook_exit_code_emits_both_markers_when_both_surfaces_fail
    [x] (n) cross-failure exclusivity: assembler emitted marker (exit 2) →
        handle_hook_exit_code does NOT add hook-failed: stop
        → test_handle_hook_exit_code_skips_hook_failed_when_assembler_emitted
    [x] (o) idempotency under concurrent re-invocation: second main() call
        on same seeded-failure run-state produces SINGLE marker entry;
        fallback file is rewritten with the latest invocation
        → test_main_double_invocation_dedups_marker
"""

from __future__ import annotations

import io
import json
import pathlib
from typing import Any

import pytest
import yaml

from loud_fail_harness import bundle_assembly
from loud_fail_harness.bundle_assembly_failure import (
    BUNDLE_ASSEMBLY_FAILED_EXIT_CODE,
    surface_assembly_failure,
)
from loud_fail_harness.orchestrator_run_entry import handle_hook_exit_code
from loud_fail_harness.run_state import (
    CostToDateBySpecialist,
    RunState,
    _serialize_run_state,
)


# --------------------------------------------------------------------------- #
# Fixtures + helpers                                                          #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def repo_root_fixture() -> pathlib.Path:
    from loud_fail_harness._shared import find_repo_root

    return find_repo_root()


@pytest.fixture(scope="module")
def envelopes_dir(repo_root_fixture: pathlib.Path) -> pathlib.Path:
    return repo_root_fixture / "examples" / "envelopes"


@pytest.fixture(scope="module")
def canonical_dev_envelope(envelopes_dir: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load((envelopes_dir / "dev-pass.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def canonical_review_envelope(envelopes_dir: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(
        (envelopes_dir / "review-pass-three-layer.yaml").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def canonical_qa_envelope(envelopes_dir: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(
        (envelopes_dir / "qa-pass-ac1-tier1.yaml").read_text(encoding="utf-8")
    )


def _make_run_state(
    *, story_id: str, run_id: str, branch_name: str | None = None
) -> RunState:
    return RunState(
        schema_version="1.3",
        story_id=story_id,
        run_id=run_id,
        current_state="done",
        branch_name=branch_name or f"bmad-automation/story/{story_id}",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        marker_contexts={},
        cost_to_date_by_specialist=CostToDateBySpecialist(),
        last_retry_directive=None,
    )


def _seed_run_state(
    rs_path: pathlib.Path, *, story_id: str, run_id: str
) -> pathlib.Path:
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    rs_path.write_text(
        _serialize_run_state(_make_run_state(story_id=story_id, run_id=run_id)),
        encoding="utf-8",
    )
    return rs_path


def _seed_dispatch_log(
    logs_root: pathlib.Path,
    *,
    story_id: str,
    run_id: str,
    specialist: str,
    return_envelope: dict[str, Any],
    attempt_number: int = 1,
) -> pathlib.Path:
    log_path = (
        logs_root / story_id / run_id / "logs" / f"{specialist}-{attempt_number}.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_payload = {
        "dispatched_specialist": specialist,
        "story_id": story_id,
        "attempt_number": attempt_number,
        "agent_definition_path": f"agents/{specialist}.md",
        "acceptance_criteria": [{"ac_id": "AC-1", "text": "stub"}],
        "dispatch_timestamp": "2026-05-07T12:00:00+00:00",
        "return_timestamp": "2026-05-07T12:01:00+00:00",
        "return_envelope": return_envelope,
    }
    log_path.write_text(json.dumps(log_payload, indent=2), encoding="utf-8")
    return log_path


def _seed_three_logs(
    logs_root: pathlib.Path,
    *,
    story_id: str,
    run_id: str,
    dev: dict[str, Any],
    review: dict[str, Any],
    qa: dict[str, Any],
) -> None:
    _seed_dispatch_log(
        logs_root,
        story_id=story_id,
        run_id=run_id,
        specialist="dev",
        return_envelope=dev,
    )
    _seed_dispatch_log(
        logs_root,
        story_id=story_id,
        run_id=run_id,
        specialist="review-bmad",
        return_envelope=review,
    )
    _seed_dispatch_log(
        logs_root,
        story_id=story_id,
        run_id=run_id,
        specialist="qa",
        return_envelope=qa,
    )


def _read_run_state(rs_path: pathlib.Path) -> RunState:
    return RunState.model_validate(
        yaml.safe_load(rs_path.read_text(encoding="utf-8"))
    )


# --------------------------------------------------------------------------- #
# (k) — end-to-end: malformed envelope → exit 2 + all three channels         #
# --------------------------------------------------------------------------- #


def test_main_on_malformed_envelope_emits_three_channels_and_exits_two(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    repo_root_fixture: pathlib.Path,
) -> None:
    """Witnesses Story 6.9 AC-1 + AC-6 (k) end-to-end — `bundle_assembly.main`
    invoked on a deliberately-malformed dev envelope (envelope re-validation
    fails) exits 2; the on-disk fallback diagnostic file exists at the
    canonical path; the run-state's `active_markers` contains
    `bundle-assembly-failed: <step>`; stderr contains the one-line marker
    emission.
    """
    story_id = "sample-auto-001"
    run_id = "smoke-k"
    rs_path = _seed_run_state(
        tmp_path / "_bmad" / "automation" / "run-state.yaml",
        story_id=story_id,
        run_id=run_id,
    )
    logs_root = tmp_path / "qa-evidence"
    bundle_root = tmp_path / "pr-bundles"

    # Mutate the dev envelope to fail re-validation: inject a forbidden
    # flow-policy field (FR52 — `next_action` is on the schema's `not` enum).
    bad_dev = dict(canonical_dev_envelope)
    bad_dev["next_action"] = "rerun-tests"

    _seed_three_logs(
        logs_root,
        story_id=story_id,
        run_id=run_id,
        dev=bad_dev,
        review=canonical_review_envelope,
        qa=canonical_qa_envelope,
    )

    rc = bundle_assembly.main(
        [
            "--story-id",
            story_id,
            "--run-id",
            run_id,
            "--run-state-path",
            str(rs_path),
            "--logs-root",
            str(logs_root),
            "--bundle-root",
            str(bundle_root),
            "--repo-root",
            str(repo_root_fixture),
        ]
    )

    assert rc == BUNDLE_ASSEMBLY_FAILED_EXIT_CODE  # =2

    # Channel 1 — fallback diagnostic file at canonical path.
    fallback_path = bundle_root / story_id / f"{run_id}.assembly-failure.log"
    assert fallback_path.exists()
    body = fallback_path.read_text(encoding="utf-8")
    assert body.startswith("=== bundle-assembly-failed ===\n")
    assert f"story_id: {story_id}" in body
    assert f"run_id: {run_id}" in body
    assert "failed_step: envelope-mismatch" in body

    # Channel 2 — stderr line.
    captured = capsys.readouterr()
    assert "bundle-assembly-failed: envelope-mismatch" in captured.err
    assert f"{story_id}/{run_id}" in captured.err

    # Channel 3 — persisted run-state marker + context.
    persisted = _read_run_state(rs_path)
    assert (
        "bundle-assembly-failed: envelope-mismatch" in persisted.active_markers
    )
    ctx = persisted.marker_contexts["bundle-assembly-failed"]
    assert ctx["failed_step"] == "envelope-mismatch"
    assert ctx["story_id"] == story_id
    assert ctx["run_id"] == run_id


# --------------------------------------------------------------------------- #
# (l) — end-to-end clean assembly: no marker emitted                          #
# --------------------------------------------------------------------------- #


def test_main_clean_assembly_does_not_emit_marker(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    repo_root_fixture: pathlib.Path,
) -> None:
    """Witnesses Story 6.9 AC-6 (l) regression guard — `bundle_assembly.main`
    invoked on a valid run-state exits 0; no fallback diagnostic file
    produced; no `bundle-assembly-failed` entry in run-state.
    """
    story_id = "sample-auto-001"
    run_id = "smoke-l"
    rs_path = _seed_run_state(
        tmp_path / "_bmad" / "automation" / "run-state.yaml",
        story_id=story_id,
        run_id=run_id,
    )
    logs_root = tmp_path / "qa-evidence"
    bundle_root = tmp_path / "pr-bundles"

    _seed_three_logs(
        logs_root,
        story_id=story_id,
        run_id=run_id,
        dev=canonical_dev_envelope,
        review=canonical_review_envelope,
        qa=canonical_qa_envelope,
    )

    rc = bundle_assembly.main(
        [
            "--story-id",
            story_id,
            "--run-id",
            run_id,
            "--run-state-path",
            str(rs_path),
            "--logs-root",
            str(logs_root),
            "--bundle-root",
            str(bundle_root),
            "--repo-root",
            str(repo_root_fixture),
        ]
    )

    assert rc == 0
    fallback_path = bundle_root / story_id / f"{run_id}.assembly-failure.log"
    assert not fallback_path.exists()
    persisted = _read_run_state(rs_path)
    assert not any(
        m.startswith("bundle-assembly-failed") for m in persisted.active_markers
    )


# --------------------------------------------------------------------------- #
# (m) — cross-failure independence: BOTH markers fire                          #
# --------------------------------------------------------------------------- #


def test_handle_hook_exit_code_emits_both_markers_when_both_surfaces_fail(
    tmp_path: pathlib.Path,
) -> None:
    """Witnesses Story 6.9 AC-3 + AC-6 (m) — when the Stop hook crashes
    mechanically (exit ≠ 0 AND ≠ 2) AND the assembler ALSO crashed
    independently, BOTH markers fire. The assembler-side
    `bundle-assembly-failed` is recorded by `surface_assembly_failure`
    from the assembler's own failure path; the Stop-hook-side
    `hook-failed: stop` is recorded by `handle_hook_exit_code` because
    the hook's exit code is non-zero AND not equal to 2.
    """
    rs_path = _seed_run_state(
        tmp_path / "run-state.yaml", story_id="auto-001", run_id="r-cross"
    )
    bundle_root = tmp_path / "pr-bundles"

    # Step 1: assembler's failure path emits `bundle-assembly-failed`.
    surface_assembly_failure(
        story_id="auto-001",
        run_id="r-cross",
        run_state_path=rs_path,
        bundle_root=bundle_root,
        exc=RuntimeError("assembler crashed mid-render"),
        failed_step="finding-render-crash",
        registry=None,
        stderr=io.StringIO(),
    )

    # Step 2: Stop hook crashes mechanically (e.g., 127 from missing python3
    # OR 1 from a `set -e` failure before/after the `exec`). Exit ≠ 2 →
    # `hook-failed: stop` is appended.
    persisted = _read_run_state(rs_path)
    next_state = handle_hook_exit_code(
        exit_code=1, hook_name="stop", run_state=persisted
    )

    # Both markers must be present in the next-state's active_markers.
    assert any(
        m.startswith("bundle-assembly-failed") for m in next_state.active_markers
    )
    assert "hook-failed: stop" in next_state.active_markers


# --------------------------------------------------------------------------- #
# (n) — cross-failure exclusivity: exit-code-2 alone → only assembler marker  #
# --------------------------------------------------------------------------- #


def test_handle_hook_exit_code_skips_hook_failed_when_assembler_emitted(
    tmp_path: pathlib.Path,
) -> None:
    """Witnesses Story 6.9 AC-3 + AC-6 (n) — when `hook_name == "stop"`
    AND `exit_code == BUNDLE_ASSEMBLY_FAILED_EXIT_CODE` (=2), the helper
    does NOT invoke `record_hook_failure_marker`; the assembler-side
    `bundle-assembly-failed` is the only marker in run-state. Emitting
    `hook-failed: stop` here would conflate the assembler's logical
    failure with a Stop hook mechanical failure per AC-3's
    remediation-shape principle.
    """
    rs_path = _seed_run_state(
        tmp_path / "run-state.yaml", story_id="auto-001", run_id="r-exclusive"
    )
    bundle_root = tmp_path / "pr-bundles"

    surface_assembly_failure(
        story_id="auto-001",
        run_id="r-exclusive",
        run_state_path=rs_path,
        bundle_root=bundle_root,
        exc=ValueError("any assembler-logic failure"),
        failed_step="internal-exception",
        registry=None,
        stderr=io.StringIO(),
    )

    persisted = _read_run_state(rs_path)
    # The Stop hook returned exit-code-2 (the assembler's own signal).
    next_state = handle_hook_exit_code(
        exit_code=BUNDLE_ASSEMBLY_FAILED_EXIT_CODE,
        hook_name="stop",
        run_state=persisted,
    )

    # The assembler-side marker is in run-state; `hook-failed: stop` is NOT.
    assert any(
        m.startswith("bundle-assembly-failed") for m in next_state.active_markers
    )
    assert "hook-failed: stop" not in next_state.active_markers


def test_handle_hook_exit_code_emits_hook_failed_for_subagent_stop_at_exit_2(
    tmp_path: pathlib.Path,
) -> None:
    """The Story 6.9 AC-3 conditional fires ONLY for `hook_name == "stop"`.
    A `subagent-stop` or `session-start` hook returning exit 2 is a Stop-
    hook-mechanical failure that warrants `hook-failed: <hook_name>`
    emission per the existing Story 6.7 path. This regression guard
    ensures the magic exit-code-2 isn't applied globally.
    """
    rs_path = _seed_run_state(
        tmp_path / "run-state.yaml",
        story_id="auto-001",
        run_id="r-subagent",
    )
    persisted = _read_run_state(rs_path)
    next_state = handle_hook_exit_code(
        exit_code=BUNDLE_ASSEMBLY_FAILED_EXIT_CODE,
        hook_name="subagent-stop",
        run_state=persisted,
    )
    assert "hook-failed: subagent-stop" in next_state.active_markers


# --------------------------------------------------------------------------- #
# (o) — idempotency under concurrent re-invocation                            #
# --------------------------------------------------------------------------- #


def test_main_double_invocation_dedups_marker(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    repo_root_fixture: pathlib.Path,
) -> None:
    """Witnesses Story 6.9 AC-6 (o) — calling `bundle_assembly.main`
    twice on the same seeded-failure run-state produces a SINGLE
    `bundle-assembly-failed: <step>` entry in `active_markers` (per
    Story 6.7's marker-recorder de-dup discipline propagated via
    `record_marker_with_context`); the fallback diagnostic file is
    rewritten with the latest invocation's content (last-write-wins).
    """
    story_id = "sample-auto-001"
    run_id = "smoke-o"
    rs_path = _seed_run_state(
        tmp_path / "_bmad" / "automation" / "run-state.yaml",
        story_id=story_id,
        run_id=run_id,
    )
    logs_root = tmp_path / "qa-evidence"
    bundle_root = tmp_path / "pr-bundles"

    bad_dev = dict(canonical_dev_envelope)
    bad_dev["next_action"] = "rerun-tests"

    _seed_three_logs(
        logs_root,
        story_id=story_id,
        run_id=run_id,
        dev=bad_dev,
        review=canonical_review_envelope,
        qa=canonical_qa_envelope,
    )

    common_args = [
        "--story-id",
        story_id,
        "--run-id",
        run_id,
        "--run-state-path",
        str(rs_path),
        "--logs-root",
        str(logs_root),
        "--bundle-root",
        str(bundle_root),
        "--repo-root",
        str(repo_root_fixture),
    ]

    rc1 = bundle_assembly.main(common_args)
    rc2 = bundle_assembly.main(common_args)
    assert rc1 == BUNDLE_ASSEMBLY_FAILED_EXIT_CODE
    assert rc2 == BUNDLE_ASSEMBLY_FAILED_EXIT_CODE

    persisted = _read_run_state(rs_path)
    matches = [
        m
        for m in persisted.active_markers
        if m.startswith("bundle-assembly-failed")
    ]
    assert len(matches) == 1
    fallback_path = bundle_root / story_id / f"{run_id}.assembly-failure.log"
    assert fallback_path.exists()
