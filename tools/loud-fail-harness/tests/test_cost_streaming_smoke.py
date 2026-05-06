"""End-to-end integration tests for the Story 6.5 in-flight cost streaming surface.

This module is the FIRST integration-test consumer of Story 6.5's
cost-streaming substrate (`cost_streaming.stream_cost_at_boundary`,
`cost_streaming.evaluate_cost_threshold`,
`specialist_dispatch.record_cost_streaming_at_return_boundary`).
Sibling to Story 6.4's `test_cost_telemetry_smoke.py` per the per-feature
integration-test-isolation precedent.

Contract-coverage matrix (Story 6.5 AC-6 (q)-(v)):

    (q) full Dev → Review → Dev-retry → Review boundary sequence with
        mocked OtelPipelineProtocol returning incremental cost events
        that cross 75% on the third boundary (Dev-retry); assert
        cost-near-ceiling is in result.run_state.active_markers AFTER
        the third boundary AND the captured line_appender invocation
        log contains the warning line.
    (r) same sequence with the cost crossing $5 on the fourth boundary
        (Review); assert cost-near-ceiling: ceiling-crossed is in
        active_markers AND BOTH 75% and ceiling-crossed are surfaced
        in the loud-fail block of the assembled bundle.
    (s) same sequence with the cost crossing 75% AND ceiling on the
        same boundary (Dev-retry single-jump scenario); assert BOTH
        markers in active_markers in the documented order.
    (t) no-auto-halt invariant — the integration test runs the full
        sequence to completion AFTER ceiling-crossed; assert the loop
        did not abort; the bundle assembles successfully.
    (u) gap-tolerance — runaway specialist crosses ceiling between
        events; warning fires at next return boundary.
    (v) graceful-degrade gap — second boundary OtelPipelineUnreachable
        skips the streaming half; subsequent green boundary recovers
        and streams normally; the previously-emitted
        cost-telemetry-unavailable marker remains in active_markers
        (markers don't un-emit per Story 1.4's permanence rule).
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import pytest
import yaml

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.bundle_assembly import assemble_bundle
from loud_fail_harness.cost_telemetry import (
    CostEvent,
    OtelPipelineProtocol,
    update_run_state_cost_counters,
)
from loud_fail_harness.exceptions import (
    OtelPipelineUnreachable,
)
from loud_fail_harness.orchestrator_run_entry import (
    AcceptanceCriterion,
    StoryDocResolution,
)
from loud_fail_harness.run_state import (
    CostToDateBySpecialist,
    RunState,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    SpecialistDispatchPayload,
    build_dispatch_payload,
    default_prompt_body_renderer,
    load_marker_class_registry,
    record_cost_streaming_at_return_boundary,
)


# --------------------------------------------------------------------------- #
# Constants + fixtures                                                        #
# --------------------------------------------------------------------------- #


_STORY_ID = "sample-cost-streaming-001"
_RUN_ID = "run-2026-05-06-cost-streaming"
_BRANCH_NAME = f"bmad-automation/story/{_STORY_ID}"
_GENERATED_AT = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
_CEILING = 5.0


@pytest.fixture(scope="module")
def repo_root() -> pathlib.Path:
    return find_repo_root()


@pytest.fixture(scope="module")
def envelopes_dir(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "examples" / "envelopes"


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


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


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _make_event(
    specialist: str, retry_attempt: int, cost_delta_usd: float
) -> CostEvent:
    return CostEvent(
        event_id=f"ev-{specialist}-{retry_attempt}",
        timestamp=_GENERATED_AT.isoformat(),
        story_id=_STORY_ID,
        prompt_id=f"prompt-{_STORY_ID}-{specialist}-{retry_attempt}",
        retry_attempt=retry_attempt,
        specialist=specialist,
        cost_delta_usd=cost_delta_usd,
    )


@dataclasses.dataclass
class _ProgrammableOtelPipeline:
    """Stub returning a per-call indexed event tuple — drives the orchestrator
    sequence by yielding the cumulative events the OTel backend would have
    recorded up to the current boundary."""

    per_call_events: tuple[tuple[CostEvent, ...], ...] = ()
    per_call_exceptions: tuple[BaseException | None, ...] = ()
    _call_index: int = 0

    def read_events(self, *, prompt_id: str) -> Sequence[CostEvent]:
        _ = prompt_id
        idx = self._call_index
        self._call_index += 1
        if idx < len(self.per_call_exceptions):
            exc = self.per_call_exceptions[idx]
            if exc is not None:
                raise exc
        if idx < len(self.per_call_events):
            return self.per_call_events[idx]
        return ()


def _build_payload(
    *, tmp_path: pathlib.Path, specialist: str, attempt_number: int
) -> SpecialistDispatchPayload:
    tmp_path.mkdir(parents=True, exist_ok=True)
    story_path = tmp_path / "story.md"
    story_path.write_text(
        "# Test\n\nStatus: ready-for-dev\n\n## Acceptance Criteria\n",
        encoding="utf-8",
    )
    agent_path = tmp_path / f"{specialist}-agent.md"
    agent_path.write_text(f"# {specialist} agent\n", encoding="utf-8")
    resolution = StoryDocResolution(
        path=story_path,
        current_state="ready-for-dev",
        acceptance_criteria=(AcceptanceCriterion(ac_id="AC-1", text="stub"),),
    )
    return build_dispatch_payload(
        specialist=specialist,
        story_id=_STORY_ID,
        attempt_number=attempt_number,
        story_doc_resolution=resolution,
        agent_definition_path=agent_path,
        prompt_body_renderer=default_prompt_body_renderer,
        dispatch_timestamp_factory=lambda: _GENERATED_AT,
    )


def _ev_id_factory() -> str:
    """Return a unique event ID per call — no shared mutable state (review patch P1)."""
    return f"ev-smoke-{uuid.uuid4().hex[:12]}"


def _initial_run_state() -> RunState:
    return RunState(
        schema_version="1.3",
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        current_state="in-progress",
        branch_name=_BRANCH_NAME,
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        marker_contexts={},
        cost_to_date_by_specialist=CostToDateBySpecialist(),
        last_retry_directive=None,
    )


def _drive_boundary(
    *,
    state: RunState,
    payload: SpecialistDispatchPayload,
    pipeline: OtelPipelineProtocol,
    cost_delta_usd: float,
    appended: list[str],
) -> RunState:
    """Drive a single specialist-return boundary — composes 6.4's cost-counter
    update + 6.5's threshold-marker append into the next-state argument
    per Pattern 4's batch-write rule."""
    collection_result, streaming_result = record_cost_streaming_at_return_boundary(
        payload,
        return_envelope={"status": "pass", "rationale": "ok"},
        return_timestamp=_GENERATED_AT,
        otel_pipeline=pipeline,
        cost_delta_usd=cost_delta_usd,
        otel_attributes={},
        event_id_factory=_ev_id_factory,
        run_state=state,
        ceiling_usd=_CEILING,
        line_appender=appended.append,
    )

    # Compose 6.4's cost-counter update + new markers + (potential)
    # cost-telemetry-unavailable marker INTO the next-state. Pattern 4
    # batch-write rule — exactly one transition per boundary.
    next_state = state
    if collection_result.aggregation.per_specialist_totals:
        next_state = update_run_state_cost_counters(
            next_state, collection_result.aggregation
        )

    new_markers: list[str] = list(next_state.active_markers)
    new_marker_contexts: dict[str, dict[str, str]] = {
        k: dict(v) for k, v in next_state.marker_contexts.items()
    }

    if collection_result.marker_classification is not None:
        marker_class, ctx = collection_result.marker_classification
        if marker_class not in new_markers:
            new_markers.append(marker_class)
            new_marker_contexts[marker_class] = dict(ctx)

    for marker_class, ctx in streaming_result.marker_classifications_to_append:
        if marker_class not in new_markers:
            new_markers.append(marker_class)
            new_marker_contexts[marker_class] = dict(ctx)

    return next_state.model_copy(
        update={
            "active_markers": tuple(new_markers),
            "marker_contexts": new_marker_contexts,
        }
    )


# --------------------------------------------------------------------------- #
# (q) cost-near-ceiling on third boundary (Dev-retry)                         #
# --------------------------------------------------------------------------- #


def test_q_cost_near_ceiling_emits_on_third_boundary(tmp_path: pathlib.Path) -> None:
    """Story 6.5 AC-6 (q): full Dev → Review → Dev-retry → Review boundary
    sequence with mocked OTel pipeline returning incremental cost events that
    cross 75% on the third boundary (Dev-retry); assert cost-near-ceiling is
    in active_markers AFTER the third boundary AND the captured line_appender
    invocation log contains the warning line."""
    # Per-call cumulative event tuples — the OTel backend reports the running
    # series each call. Cumulative totals: $1.0, $2.0, $4.0 (75% on call 3),
    # $4.5.
    pipeline = _ProgrammableOtelPipeline(
        per_call_events=(
            (_make_event("dev", 1, 1.0),),
            (_make_event("dev", 1, 1.0), _make_event("review-bmad", 1, 1.0)),
            (
                _make_event("dev", 1, 1.0),
                _make_event("review-bmad", 1, 1.0),
                _make_event("dev", 2, 2.0),
            ),
            (
                _make_event("dev", 1, 1.0),
                _make_event("review-bmad", 1, 1.0),
                _make_event("dev", 2, 2.0),
                _make_event("review-bmad", 2, 0.5),
            ),
        ),
    )
    state = _initial_run_state()
    appended: list[str] = []

    payloads = [
        ("dev", 1, 1.0),
        ("review-bmad", 1, 1.0),
        ("dev", 2, 2.0),
        ("review-bmad", 2, 0.5),
    ]
    for i, (specialist, attempt, delta) in enumerate(payloads):
        payload = _build_payload(
            tmp_path=tmp_path / f"b{i}", specialist=specialist, attempt_number=attempt
        )
        state = _drive_boundary(
            state=state,
            payload=payload,
            pipeline=pipeline,
            cost_delta_usd=delta,
            appended=appended,
        )
        if i == 2:
            assert "cost-near-ceiling" in state.active_markers
            assert any("[⚠️ cost-near-ceiling]" in line for line in appended)


# --------------------------------------------------------------------------- #
# (r) ceiling-crossed on fourth boundary; bundle loud-fail surfaces both       #
# --------------------------------------------------------------------------- #


def _seed_log(
    logs_root: pathlib.Path, *, specialist: str, return_envelope: dict[str, Any]
) -> None:
    log_path = logs_root / _STORY_ID / _RUN_ID / "logs" / f"{specialist}-1.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_payload = {
        "dispatched_specialist": specialist,
        "story_id": _STORY_ID,
        "attempt_number": 1,
        "agent_definition_path": f"agents/{specialist}.md",
        "acceptance_criteria": [{"ac_id": "AC-1", "text": "stub"}],
        "dispatch_timestamp": _GENERATED_AT.isoformat(),
        "return_timestamp": _GENERATED_AT.isoformat(),
        "return_envelope": return_envelope,
    }
    log_path.write_text(json.dumps(log_payload, indent=2), encoding="utf-8")


def _write_run_state_yaml_from_state(rs_path: pathlib.Path, state: RunState) -> pathlib.Path:
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": state.schema_version,
        "story_id": state.story_id,
        "run_id": state.run_id,
        "current_state": "done",
        "branch_name": state.branch_name,
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": [],
        "active_markers": list(state.active_markers),
        "marker_contexts": {k: dict(v) for k, v in state.marker_contexts.items()},
        "cost_to_date_by_specialist": {
            k: v
            for k, v in {
                "dev": state.cost_to_date_by_specialist.dev,
                "review_bmad": state.cost_to_date_by_specialist.review_bmad,
                "qa": state.cost_to_date_by_specialist.qa,
                "lad": state.cost_to_date_by_specialist.lad,
            }.items()
            if v is not None
        },
    }
    rs_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return rs_path


def test_r_ceiling_crossed_on_fourth_boundary_bundle_surfaces_both(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.5 AC-6 (r): same sequence with cost crossing $5 on fourth
    boundary; assert cost-near-ceiling: ceiling-crossed in active_markers
    AND BOTH markers surfaced in the loud-fail block of the assembled bundle."""
    pipeline = _ProgrammableOtelPipeline(
        per_call_events=(
            (_make_event("dev", 1, 1.0),),
            (_make_event("dev", 1, 1.0), _make_event("review-bmad", 1, 1.0)),
            (
                _make_event("dev", 1, 1.0),
                _make_event("review-bmad", 1, 1.0),
                _make_event("dev", 2, 2.0),
            ),
            (
                _make_event("dev", 1, 1.0),
                _make_event("review-bmad", 1, 1.0),
                _make_event("dev", 2, 2.0),
                _make_event("review-bmad", 2, 1.5),
            ),
        ),
    )
    state = _initial_run_state()
    appended: list[str] = []

    payloads = [
        ("dev", 1, 1.0),
        ("review-bmad", 1, 1.0),
        ("dev", 2, 2.0),
        ("review-bmad", 2, 1.5),
    ]
    for i, (specialist, attempt, delta) in enumerate(payloads):
        payload = _build_payload(
            tmp_path=tmp_path / f"b{i}", specialist=specialist, attempt_number=attempt
        )
        state = _drive_boundary(
            state=state,
            payload=payload,
            pipeline=pipeline,
            cost_delta_usd=delta,
            appended=appended,
        )

    assert "cost-near-ceiling" in state.active_markers
    assert "cost-near-ceiling: ceiling-crossed" in state.active_markers

    # Assemble a real bundle from this terminal state — confirms 6.1's
    # _render_loud_fail_block consumes the new markers automatically.
    rs_path = _write_run_state_yaml_from_state(
        tmp_path / "_bmad" / "automation" / "run-state.yaml", state
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_log(logs_root, specialist="dev", return_envelope=canonical_dev_envelope)
    _seed_log(
        logs_root, specialist="review-bmad", return_envelope=canonical_review_envelope
    )
    _seed_log(logs_root, specialist="qa", return_envelope=canonical_qa_envelope)
    bundle_root = tmp_path / "pr-bundles"
    result = assemble_bundle(
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        marker_registry=runtime_marker_registry,
        generated_at=_GENERATED_AT,
        otel_pipeline=None,
    )
    body = result.bundle_path.read_text(encoding="utf-8")

    assert "## ⚠️ Loud-Fail Markers" in body
    assert "cost-near-ceiling" in body
    assert "ceiling-crossed" in body


# --------------------------------------------------------------------------- #
# (s) same-boundary 75%+100% jump emits BOTH in documented order              #
# --------------------------------------------------------------------------- #


def test_s_same_boundary_75pct_and_100pct_jump_emits_both_markers(
    tmp_path: pathlib.Path,
) -> None:
    """Story 6.5 AC-6 (s): cost crosses 75% AND ceiling on the same boundary
    (Dev-retry single-jump scenario, e.g. cost goes $0 → $6 in one boundary);
    assert BOTH markers in active_markers in the documented order."""
    pipeline = _ProgrammableOtelPipeline(
        per_call_events=(
            (_make_event("dev", 1, 0.0),),
            (_make_event("dev", 1, 0.0), _make_event("review-bmad", 1, 0.0)),
            (
                _make_event("dev", 1, 0.0),
                _make_event("review-bmad", 1, 0.0),
                _make_event("dev", 2, 6.0),  # runaway specialist
            ),
        ),
    )
    state = _initial_run_state()
    appended: list[str] = []

    payloads = [("dev", 1, 0.0), ("review-bmad", 1, 0.0), ("dev", 2, 6.0)]
    for i, (specialist, attempt, delta) in enumerate(payloads):
        payload = _build_payload(
            tmp_path=tmp_path / f"b{i}", specialist=specialist, attempt_number=attempt
        )
        state = _drive_boundary(
            state=state,
            payload=payload,
            pipeline=pipeline,
            cost_delta_usd=delta,
            appended=appended,
        )

    assert state.active_markers.index("cost-near-ceiling") < state.active_markers.index(
        "cost-near-ceiling: ceiling-crossed"
    )


# --------------------------------------------------------------------------- #
# (t) no-auto-halt invariant — loop runs to completion AFTER ceiling crossed  #
# --------------------------------------------------------------------------- #


def test_t_no_auto_halt_loop_runs_to_completion_after_ceiling_crossed(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.5 AC-6 (t): the integration test runs the full sequence to
    completion AFTER ceiling-crossed; assert the loop did not abort; the
    bundle assembles successfully."""
    pipeline = _ProgrammableOtelPipeline(
        per_call_events=(
            (_make_event("dev", 1, 6.0),),  # runaway on FIRST boundary
            (_make_event("dev", 1, 6.0), _make_event("review-bmad", 1, 1.0)),
            (
                _make_event("dev", 1, 6.0),
                _make_event("review-bmad", 1, 1.0),
                _make_event("qa", 1, 0.5),
            ),
        ),
    )
    state = _initial_run_state()
    appended: list[str] = []

    # Loop continues — no exception raised — past the ceiling crossing.
    payloads = [("dev", 1, 6.0), ("review-bmad", 1, 1.0), ("qa", 1, 0.5)]
    for i, (specialist, attempt, delta) in enumerate(payloads):
        payload = _build_payload(
            tmp_path=tmp_path / f"b{i}", specialist=specialist, attempt_number=attempt
        )
        state = _drive_boundary(
            state=state,
            payload=payload,
            pipeline=pipeline,
            cost_delta_usd=delta,
            appended=appended,
        )

    # Assemble bundle to confirm the post-ceiling-crossed state can still
    # be turned into a merge-ready (or escalation) artifact.
    rs_path = _write_run_state_yaml_from_state(
        tmp_path / "_bmad" / "automation" / "run-state.yaml", state
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_log(logs_root, specialist="dev", return_envelope=canonical_dev_envelope)
    _seed_log(
        logs_root, specialist="review-bmad", return_envelope=canonical_review_envelope
    )
    _seed_log(logs_root, specialist="qa", return_envelope=canonical_qa_envelope)
    bundle_root = tmp_path / "pr-bundles"
    result = assemble_bundle(
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        marker_registry=runtime_marker_registry,
        generated_at=_GENERATED_AT,
        otel_pipeline=None,
    )
    assert result.bundle_path.exists()
    assert any("no auto-halt per NFR-O8" in line for line in appended)


# --------------------------------------------------------------------------- #
# (u) gap-tolerance — runaway specialist crosses ceiling between events       #
# --------------------------------------------------------------------------- #


def test_u_gap_tolerance_runaway_specialist_warning_at_next_boundary(
    tmp_path: pathlib.Path,
) -> None:
    """Story 6.5 AC-6 (u): runaway specialist exceeds the ceiling between
    events; warning fires at the next return boundary — gap is bounded by
    NFR-P2's per-specialist timeout (15-min default per Story 2.6)."""
    # Two boundaries: small dev cost → next dev boundary jumps cost to $7.
    pipeline = _ProgrammableOtelPipeline(
        per_call_events=(
            (_make_event("dev", 1, 0.5),),
            (_make_event("dev", 1, 0.5), _make_event("dev", 2, 6.5)),
        ),
    )
    state = _initial_run_state()
    appended: list[str] = []

    payload_1 = _build_payload(
        tmp_path=tmp_path / "b0", specialist="dev", attempt_number=1
    )
    state = _drive_boundary(
        state=state,
        payload=payload_1,
        pipeline=pipeline,
        cost_delta_usd=0.5,
        appended=appended,
    )
    assert "cost-near-ceiling" not in state.active_markers
    assert "cost-near-ceiling: ceiling-crossed" not in state.active_markers

    payload_2 = _build_payload(
        tmp_path=tmp_path / "b1", specialist="dev", attempt_number=2
    )
    state = _drive_boundary(
        state=state,
        payload=payload_2,
        pipeline=pipeline,
        cost_delta_usd=6.5,
        appended=appended,
    )
    assert "cost-near-ceiling" in state.active_markers
    assert "cost-near-ceiling: ceiling-crossed" in state.active_markers


# --------------------------------------------------------------------------- #
# (v) graceful-degrade gap — pipeline failure mid-run                         #
# --------------------------------------------------------------------------- #


def test_v_graceful_degrade_gap_marker_persists_across_recovery(
    tmp_path: pathlib.Path,
) -> None:
    """Story 6.5 AC-6 (v): second boundary OtelPipelineUnreachable skips
    the streaming half; subsequent green boundary recovers and streams
    normally; the previously-emitted cost-telemetry-unavailable marker
    remains in active_markers (markers don't un-emit per Story 1.4's
    permanence rule)."""
    pipeline = _ProgrammableOtelPipeline(
        per_call_events=(
            (_make_event("dev", 1, 1.0),),
            (),  # call 2 raises — events tuple ignored
            (
                _make_event("dev", 1, 1.0),
                _make_event("review-bmad", 1, 1.5),
                _make_event("dev", 2, 0.5),
            ),
        ),
        per_call_exceptions=(
            None,
            OtelPipelineUnreachable(
                prompt_id="prompt-test",
                story_id=_STORY_ID,
                diagnostic="OTLP collector unreachable",
            ),
            None,
        ),
    )
    state = _initial_run_state()
    appended: list[str] = []

    payloads = [("dev", 1, 1.0), ("review-bmad", 1, 1.5), ("dev", 2, 0.5)]
    for i, (specialist, attempt, delta) in enumerate(payloads):
        payload = _build_payload(
            tmp_path=tmp_path / f"b{i}", specialist=specialist, attempt_number=attempt
        )
        state = _drive_boundary(
            state=state,
            payload=payload,
            pipeline=pipeline,
            cost_delta_usd=delta,
            appended=appended,
        )

    # The cost-telemetry-unavailable marker (sub-classified by 6.4) is in
    # active_markers and persists through recovery per Story 1.4
    # marker-permanence rule.
    assert any(
        m.startswith("cost-telemetry-unavailable") for m in state.active_markers
    )
    # Three boundaries: boundary 1 streams cost line; boundary 2 is
    # graceful-degrade (NO line appended); boundary 3 recovers and streams.
    cost_lines = [line for line in appended if "[cost]" in line]
    assert len(cost_lines) == 2  # boundaries 1 + 3 only


def test_v2_recovery_boundary_uses_stale_cost_counter_not_zero(
    tmp_path: pathlib.Path,
) -> None:
    """Story 6.5 review patch P5: after a graceful-degrade boundary,
    cost_to_date_by_specialist retains the pre-degrade values (stale but correct).
    The recovery boundary's previous_running_total_usd is computed from the stale
    counter, not reset to 0.0.

    Scenario:
      Boundary 1: green, dev=$4.00 (80% of $5) → emits cost-near-ceiling,
                  cost_to_date_by_specialist.dev updated to 4.0.
      Boundary 2: degrade (OtelPipelineUnreachable) → NO cost-counter update.
      Expected: state.cost_to_date_by_specialist.dev == 4.0 after boundary 2
               (not reset to 0.0), confirming the stale counter is preserved
               and available for the next boundary's previous_running_total_usd.
    """
    pipeline = _ProgrammableOtelPipeline(
        per_call_events=(
            (_make_event("dev", 1, 4.0),),
            (),  # call 2: exception raised; events tuple ignored
        ),
        per_call_exceptions=(
            None,
            OtelPipelineUnreachable(
                prompt_id="prompt-test",
                story_id=_STORY_ID,
                diagnostic="OTLP collector unreachable",
            ),
        ),
    )
    state = _initial_run_state()
    appended: list[str] = []

    # Boundary 1 — green; crosses 75%, emits cost-near-ceiling.
    payload1 = _build_payload(
        tmp_path=tmp_path / "b1", specialist="dev", attempt_number=1
    )
    state = _drive_boundary(
        state=state,
        payload=payload1,
        pipeline=pipeline,
        cost_delta_usd=4.0,
        appended=appended,
    )
    assert "cost-near-ceiling" in state.active_markers
    assert state.cost_to_date_by_specialist.dev == 4.0

    # Boundary 2 — graceful-degrade; NO cost-counter update, NO streaming line.
    cost_lines_before = len([line for line in appended if "[cost]" in line])
    payload2 = _build_payload(
        tmp_path=tmp_path / "b2", specialist="dev", attempt_number=2
    )
    state = _drive_boundary(
        state=state,
        payload=payload2,
        pipeline=pipeline,
        cost_delta_usd=0.0,
        appended=appended,
    )
    cost_lines_after = len([line for line in appended if "[cost]" in line])
    assert cost_lines_after == cost_lines_before, "degrade boundary must not append a cost line"
    # Critical assertion: stale counter preserved — NOT reset to 0.0.
    assert state.cost_to_date_by_specialist.dev == 4.0


# --------------------------------------------------------------------------- #
# Canonical-fixture regression tests (Story 6.5 AC-6)                         #
# --------------------------------------------------------------------------- #


_FIXTURE_STORY_ID = "sample-cost-near-ceiling-001"
_FIXTURE_RUN_ID = "run-2026-05-06-cost-near-ceiling"


class _StubFixturePipeline:
    def __init__(self, events: tuple[CostEvent, ...]) -> None:
        self.events = events

    def read_events(self, *, prompt_id: str) -> Sequence[CostEvent]:
        _ = prompt_id
        return self.events


def _make_fixture_event(
    specialist: str, retry_attempt: int, cost_delta_usd: float
) -> CostEvent:
    return CostEvent(
        event_id=f"ev-{specialist}-{retry_attempt}",
        timestamp=_GENERATED_AT.isoformat(),
        story_id=_FIXTURE_STORY_ID,
        prompt_id=f"prompt-{_FIXTURE_STORY_ID}-{specialist}-{retry_attempt}",
        retry_attempt=retry_attempt,
        specialist=specialist,
        cost_delta_usd=cost_delta_usd,
    )


def _seed_fixture_log(
    logs_root: pathlib.Path, *, specialist: str, return_envelope: dict[str, Any]
) -> None:
    log_path = (
        logs_root / _FIXTURE_STORY_ID / _FIXTURE_RUN_ID / "logs" / f"{specialist}-1.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_payload = {
        "dispatched_specialist": specialist,
        "story_id": _FIXTURE_STORY_ID,
        "attempt_number": 1,
        "agent_definition_path": f"agents/{specialist}.md",
        "acceptance_criteria": [{"ac_id": "AC-1", "text": "stub"}],
        "dispatch_timestamp": _GENERATED_AT.isoformat(),
        "return_timestamp": _GENERATED_AT.isoformat(),
        "return_envelope": return_envelope,
    }
    log_path.write_text(json.dumps(log_payload, indent=2), encoding="utf-8")


def _assemble_fixture_bundle(
    *,
    tmp_path: pathlib.Path,
    pipeline: OtelPipelineProtocol,
    active_markers: tuple[str, ...],
    cost_to_date_by_specialist: dict[str, float],
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> pathlib.Path:
    rs_path = tmp_path / "_bmad" / "automation" / "run-state.yaml"
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.3",
        "story_id": _FIXTURE_STORY_ID,
        "run_id": _FIXTURE_RUN_ID,
        "current_state": "done",
        "branch_name": f"bmad-automation/story/{_FIXTURE_STORY_ID}",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": [],
        "active_markers": list(active_markers),
        "marker_contexts": {m: {} for m in active_markers},
        "cost_to_date_by_specialist": cost_to_date_by_specialist,
    }
    rs_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    logs_root = tmp_path / "qa-evidence"
    _seed_fixture_log(
        logs_root, specialist="dev", return_envelope=canonical_dev_envelope
    )
    _seed_fixture_log(
        logs_root, specialist="review-bmad", return_envelope=canonical_review_envelope
    )
    _seed_fixture_log(
        logs_root, specialist="qa", return_envelope=canonical_qa_envelope
    )
    bundle_root = tmp_path / "pr-bundles"
    result = assemble_bundle(
        story_id=_FIXTURE_STORY_ID,
        run_id=_FIXTURE_RUN_ID,
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        marker_registry=runtime_marker_registry,
        generated_at=_GENERATED_AT,
        otel_pipeline=pipeline,
    )
    return result.bundle_path


def test_canonical_cost_near_ceiling_bundle_fixture_matches_assembler_output(
    tmp_path: pathlib.Path,
    repo_root: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.5 AC-6: the committed pr-bundle-cost-near-ceiling.md fixture
    matches the assembler output byte-for-byte for the seeded run-state with
    the cost-near-ceiling active marker + 4-event happy-path OTel-pipeline
    mock summing to $4.00 (80% of $5 ceiling)."""
    import re

    fixture_path = (
        repo_root / "examples" / "pr-bundles" / "pr-bundle-cost-near-ceiling.md"
    )
    fixture_body = fixture_path.read_text(encoding="utf-8")
    body_after_header = re.sub(
        r"^<!--.*?-->\s*", "", fixture_body, count=1, flags=re.DOTALL
    )

    pipeline = _StubFixturePipeline(
        events=(
            _make_fixture_event("dev", 1, 1.20),
            _make_fixture_event("review-bmad", 1, 0.80),
            _make_fixture_event("dev", 2, 1.40),
            _make_fixture_event("review-bmad", 2, 0.60),
        )
    )
    bundle_path = _assemble_fixture_bundle(
        tmp_path=tmp_path,
        pipeline=pipeline,
        active_markers=("cost-near-ceiling",),
        cost_to_date_by_specialist={"dev": 2.60, "review_bmad": 1.40},
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    assembled_body = bundle_path.read_text(encoding="utf-8")
    assert assembled_body == body_after_header, (
        "canonical pr-bundle-cost-near-ceiling.md fixture must match assembler "
        "output byte-for-byte (modulo contract-header strip); regenerate the "
        "fixture if the assembler's rendering intentionally changed"
    )


def test_canonical_cost_ceiling_crossed_bundle_fixture_matches_assembler_output(
    tmp_path: pathlib.Path,
    repo_root: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.5 AC-6: the committed pr-bundle-cost-ceiling-crossed.md fixture
    matches the assembler output byte-for-byte for the seeded run-state with
    BOTH cost-near-ceiling AND cost-near-ceiling: ceiling-crossed active markers
    + 4-event OTel-pipeline mock summing to $5.50 (110% of $5 ceiling). Bundle
    assembled successfully — no auto-halt per NFR-O8."""
    import re

    fixture_path = (
        repo_root / "examples" / "pr-bundles" / "pr-bundle-cost-ceiling-crossed.md"
    )
    fixture_body = fixture_path.read_text(encoding="utf-8")
    body_after_header = re.sub(
        r"^<!--.*?-->\s*", "", fixture_body, count=1, flags=re.DOTALL
    )

    pipeline = _StubFixturePipeline(
        events=(
            _make_fixture_event("dev", 1, 1.50),
            _make_fixture_event("review-bmad", 1, 1.00),
            _make_fixture_event("dev", 2, 2.00),
            _make_fixture_event("review-bmad", 2, 1.00),
        )
    )
    bundle_path = _assemble_fixture_bundle(
        tmp_path=tmp_path,
        pipeline=pipeline,
        active_markers=(
            "cost-near-ceiling",
            "cost-near-ceiling: ceiling-crossed",
        ),
        cost_to_date_by_specialist={"dev": 3.50, "review_bmad": 2.00},
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    assembled_body = bundle_path.read_text(encoding="utf-8")
    assert assembled_body == body_after_header, (
        "canonical pr-bundle-cost-ceiling-crossed.md fixture must match assembler "
        "output byte-for-byte (modulo contract-header strip); regenerate the "
        "fixture if the assembler's rendering intentionally changed"
    )
