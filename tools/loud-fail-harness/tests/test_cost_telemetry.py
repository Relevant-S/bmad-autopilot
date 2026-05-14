"""Story 6.4 — per-specialist × per-retry cost telemetry collection tests.

Coverage map (per AC-6):
    (a) CostEvent dataclass round-trips with frozen + OTel pass-through
    (b) make_cost_event positive + negative (composed via record_cost_event)
    (c) aggregate_costs deterministic — Dev → Review-BMAD → Dev-retry → Review-BMAD-retry
    (d) aggregate_costs empty input → empty aggregation
    (e) aggregate_costs byte-stable round-trip
    (f) update_run_state_cost_counters produces a new frozen RunState
    (g) derive_cost_telemetry_unavailable_marker correct sub-classification +
        re-raise on unknown exception types
    (h) collect happy path → CollectionResult with marker_classification=None
    (i) collect failure path with OtelPipelineUnreachable
    (j) collect failure path with PromptIdCorrelationMissing
    (k) aggregate_costs four-layer LAD-enabled — lad partition present (Story 10.6 AC-5)
    (l) aggregate_costs four-specialist no-LAD — lad partition absent (Story 10.6 AC-5)
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

import pytest

from loud_fail_harness.cost_telemetry import (
    CostAggregation,
    CostEvent,
    CollectionResult,
    OtelPipelineProtocol,
    aggregate_costs,
    collect,
    derive_cost_telemetry_unavailable_marker,
    record_cost_event,
    update_run_state_cost_counters,
)
from loud_fail_harness.exceptions import (
    OtelPipelineUnreachable,
    PromptIdCorrelationMissing,
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
    EventConstructionFailed,
    SpecialistDispatchPayload,
    build_dispatch_payload,
    default_prompt_body_renderer,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def fixed_timestamp() -> datetime:
    return datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def acceptance_criteria() -> tuple[AcceptanceCriterion, ...]:
    return (AcceptanceCriterion(ac_id="AC-1", text="First criterion."),)


@pytest.fixture
def story_doc_resolution(
    tmp_path: pathlib.Path, acceptance_criteria: tuple[AcceptanceCriterion, ...]
) -> StoryDocResolution:
    story_path = tmp_path / "6-4-cost-telemetry-test.md"
    story_path.write_text(
        "# Test\n\nStatus: ready-for-dev\n\n## Acceptance Criteria\n", encoding="utf-8"
    )
    return StoryDocResolution(
        path=story_path,
        current_state="ready-for-dev",
        acceptance_criteria=acceptance_criteria,
    )


@pytest.fixture
def agent_definition_path(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "dev-wrapper.md"
    p.write_text("# Dev specialist\n", encoding="utf-8")
    return p


@pytest.fixture
def dispatch_payload(
    fixed_timestamp: datetime,
    story_doc_resolution: StoryDocResolution,
    agent_definition_path: pathlib.Path,
) -> SpecialistDispatchPayload:
    return build_dispatch_payload(
        specialist="dev",
        story_id="6.4",
        attempt_number=1,
        story_doc_resolution=story_doc_resolution,
        agent_definition_path=agent_definition_path,
        prompt_body_renderer=default_prompt_body_renderer,
        dispatch_timestamp_factory=lambda: fixed_timestamp,
    )


@pytest.fixture
def deterministic_event_id_factory() -> Callable[[], str]:
    counter = {"n": 0}

    def factory() -> str:
        counter["n"] += 1
        return f"ev-6-4-cost-{counter['n']:04d}"

    return factory


@pytest.fixture
def base_run_state() -> RunState:
    """Minimal valid RunState mirroring Story 2.2's MVP shape."""
    return RunState(
        schema_version="1.3",
        story_id="6.4",
        run_id="run-6-4-test-001",
        current_state="ready-for-dev",
        branch_name="bmad-automation/story/6.4",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        marker_contexts={},
        cost_to_date_by_specialist=CostToDateBySpecialist(),
        last_retry_directive=None,
    )


# --------------------------------------------------------------------------- #
# (a) CostEvent dataclass round-trips                                         #
# --------------------------------------------------------------------------- #


def test_cost_event_is_frozen_dataclass() -> None:
    """Story 6.4 AC-1: CostEvent is frozen per Epic 1 retro Action #2."""
    event = CostEvent(
        event_id="ev-1",
        timestamp="2026-04-29T12:00:00+00:00",
        story_id="6.4",
        prompt_id="prompt-6.4-dev-1-abc",
        retry_attempt=1,
        specialist="dev",
        cost_delta_usd=0.42,
        otel_attributes={"prompt.id": "otel-id-1"},
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.cost_delta_usd = 99.0  # type: ignore[misc]


def test_cost_event_otel_attributes_preserve_dotted_keys_verbatim() -> None:
    """Story 6.4 AC-1 + Pattern 3: dotted/mixed-case OTel keys remain valid."""
    event = CostEvent(
        event_id="ev-1",
        timestamp="2026-04-29T12:00:00+00:00",
        story_id="6.4",
        prompt_id="prompt-1",
        retry_attempt=1,
        specialist="dev",
        cost_delta_usd=0.10,
        otel_attributes={
            "prompt.id": "otel-id",
            "claude_code.cost.usage": 0.10,
            "claude_code.token.usage": {"input": 100},
            "query_source": "user",
        },
    )
    assert event.otel_attributes["prompt.id"] == "otel-id"
    assert event.otel_attributes["claude_code.cost.usage"] == 0.10


# --------------------------------------------------------------------------- #
# (b) record_cost_event positive + negative                                   #
# --------------------------------------------------------------------------- #


def test_record_cost_event_produces_schema_valid_dict(
    dispatch_payload: SpecialistDispatchPayload,
    deterministic_event_id_factory: Callable[[], str],
    fixed_timestamp: datetime,
) -> None:
    """Story 6.4 AC-1: record_cost_event composes through make_cost_event and
    returns a schema-valid dict (positive case)."""
    event = record_cost_event(
        dispatch_payload,
        return_envelope={"status": "pass", "rationale": "ok"},
        return_timestamp=fixed_timestamp,
        cost_delta_usd=0.42,
        otel_attributes={"prompt.id": "otel-1"},
        event_id_factory=deterministic_event_id_factory,
    )
    assert event["event_class"] == "cost-event"
    assert event["cost_delta_usd"] == 0.42


def test_record_cost_event_raises_on_invalid_input(
    dispatch_payload: SpecialistDispatchPayload,
    fixed_timestamp: datetime,
) -> None:
    """Story 6.4 AC-1: record_cost_event raises EventConstructionFailed when
    the constructed dict fails schema validation (synthetic via empty event_id)."""
    with pytest.raises(EventConstructionFailed):
        record_cost_event(
            dispatch_payload,
            return_envelope={"status": "pass", "rationale": "ok"},
            return_timestamp=fixed_timestamp,
            cost_delta_usd=0.5,
            otel_attributes={},
            event_id_factory=lambda: "",
        )


# --------------------------------------------------------------------------- #
# (c) aggregate_costs Dev → Review → Dev-retry → Review-retry                 #
# --------------------------------------------------------------------------- #


def _make_event(specialist: str, retry_attempt: int, cost: float) -> CostEvent:
    return CostEvent(
        event_id=f"ev-{specialist}-{retry_attempt}",
        timestamp="2026-04-29T12:00:00+00:00",
        story_id="6.4",
        prompt_id=f"prompt-6.4-{specialist}-{retry_attempt}",
        retry_attempt=retry_attempt,
        specialist=specialist,
        cost_delta_usd=cost,
    )


def test_aggregate_costs_dev_review_retry_sequence_produces_four_entries() -> None:
    """Story 6.4 AC-1 + AC-6: Dev → Review-BMAD → Dev-retry → Review-BMAD-retry
    produces exactly 4 entries: dev/1, review-bmad/1, dev/2, review-bmad/2 per
    AC verbatim ``epics.md`` lines 2671-2673."""
    events: Sequence[CostEvent] = (
        _make_event("dev", 1, 0.50),
        _make_event("review-bmad", 1, 0.30),
        _make_event("dev", 2, 0.40),
        _make_event("review-bmad", 2, 0.20),
    )
    aggregation = aggregate_costs(events)
    assert dict(aggregation.per_specialist_per_retry) == {
        ("dev", 1): 0.50,
        ("review-bmad", 1): 0.30,
        ("dev", 2): 0.40,
        ("review-bmad", 2): 0.20,
    }
    # per_specialist_totals key uses snake_case per Pattern 1's structural-keys
    # boundary (run_state.py:342-379's CostToDateBySpecialist field names).
    assert aggregation.per_specialist_totals["dev"] == pytest.approx(0.90)
    assert aggregation.per_specialist_totals["review_bmad"] == pytest.approx(0.50)


def test_aggregate_costs_four_layer_review_sequence_includes_lad_partition() -> None:
    """Story 10.6 AC-5: Phase-1.5 4-layer-review per-attempt LAD partition.

    Canonical Phase-1.5 four-layer-review retry sequence: six cost-events
    across ``(dev, 1)`` / ``(review-bmad, 1)`` / ``(lad, 1)`` /
    ``(dev, 2)`` / ``(review-bmad, 2)`` / ``(lad, 2)`` — Review-LAD as a
    first-class peer of Dev + Review-BMAD at the NFR-P5 per-specialist ×
    per-retry resolution. The `lad` partition lands as `per_specialist_per_retry`
    entries plus a `per_specialist_totals["lad"]` sum. The `_SPECIALIST_TO_RUN_STATE_KEY`
    mapping `"lad" → "lad"` (kebab-case-to-snake-case identity at the
    single-word slug) keeps the totals key flat.
    """
    events: Sequence[CostEvent] = (
        _make_event("dev", 1, 0.50),
        _make_event("review-bmad", 1, 0.30),
        _make_event("lad", 1, 0.40),
        _make_event("dev", 2, 0.45),
        _make_event("review-bmad", 2, 0.28),
        _make_event("lad", 2, 0.38),
    )
    aggregation = aggregate_costs(events)
    assert len(aggregation.per_specialist_per_retry) == 6
    assert aggregation.per_specialist_per_retry[("lad", 1)] == pytest.approx(0.40)
    assert aggregation.per_specialist_per_retry[("lad", 2)] == pytest.approx(0.38)
    assert aggregation.per_specialist_totals["lad"] == pytest.approx(0.78)
    assert set(aggregation.per_specialist_totals.keys()) == {
        "dev",
        "review_bmad",
        "lad",
    }


def test_aggregate_costs_lad_disabled_no_lad_partition() -> None:
    """Story 10.6 AC-5: LAD-disabled run produces no `lad` partition entries.

    Silence-unless-configured at the cost-partition surface: when zero
    `specialist="lad"` cost-events flow into `aggregate_costs`, the
    resulting `CostAggregation.per_specialist_totals` does NOT contain
    a `"lad"` key. NFR-I3 silence-unless-configured discipline mirrored
    at the cost-observability boundary.
    """
    events: Sequence[CostEvent] = (
        _make_event("dev", 1, 0.50),
        _make_event("review-bmad", 1, 0.30),
        _make_event("dev", 2, 0.40),
        _make_event("review-bmad", 2, 0.20),
    )
    aggregation = aggregate_costs(events)
    assert len(aggregation.per_specialist_per_retry) == 4
    assert "lad" not in aggregation.per_specialist_totals


# --------------------------------------------------------------------------- #
# (d) aggregate_costs empty input                                             #
# --------------------------------------------------------------------------- #


def test_aggregate_costs_empty_input_returns_empty_aggregation() -> None:
    """Story 6.4 AC-1: empty events sequence → empty CostAggregation."""
    aggregation = aggregate_costs(())
    assert dict(aggregation.per_specialist_totals) == {}
    assert dict(aggregation.per_specialist_per_retry) == {}


# --------------------------------------------------------------------------- #
# (e) aggregate_costs byte-stable round-trip                                  #
# --------------------------------------------------------------------------- #


def test_aggregate_costs_byte_stable_for_repeated_invocation() -> None:
    """Story 6.4 AC-1 + Story 6.1 / 6.3 byte-stable regression-fixture
    discipline: same input always yields the same aggregation."""
    events = (
        _make_event("dev", 1, 0.10),
        _make_event("review-bmad", 1, 0.05),
    )
    a1 = aggregate_costs(events)
    a2 = aggregate_costs(events)
    serialized_1 = json.dumps(
        {
            "per_specialist_totals": dict(a1.per_specialist_totals),
            "per_specialist_per_retry": [
                [list(k), v] for k, v in sorted(a1.per_specialist_per_retry.items())
            ],
        },
        sort_keys=True,
    )
    serialized_2 = json.dumps(
        {
            "per_specialist_totals": dict(a2.per_specialist_totals),
            "per_specialist_per_retry": [
                [list(k), v] for k, v in sorted(a2.per_specialist_per_retry.items())
            ],
        },
        sort_keys=True,
    )
    assert serialized_1 == serialized_2


# --------------------------------------------------------------------------- #
# (f) update_run_state_cost_counters new frozen RunState                      #
# --------------------------------------------------------------------------- #


def test_update_run_state_cost_counters_produces_new_frozen_runstate(
    base_run_state: RunState,
) -> None:
    """Story 6.4 AC-1 + Pattern 4: pure functional update via Pydantic
    model_copy (run_state.py:178-184); prior instance is unchanged."""
    aggregation = CostAggregation(
        per_specialist_totals={"dev": 1.50, "review_bmad": 0.75},
        per_specialist_per_retry={("dev", 1): 1.50, ("review-bmad", 1): 0.75},
    )
    new_state = update_run_state_cost_counters(base_run_state, aggregation)
    # Prior instance unchanged (frozen-tuple immutability invariant).
    assert base_run_state.cost_to_date_by_specialist.dev is None
    # New instance carries the populated cost counters.
    assert new_state.cost_to_date_by_specialist.dev == pytest.approx(1.50)
    assert new_state.cost_to_date_by_specialist.review_bmad == pytest.approx(0.75)


# --------------------------------------------------------------------------- #
# (g) derive_cost_telemetry_unavailable_marker                                #
# --------------------------------------------------------------------------- #


def test_derive_marker_otel_pipeline_unreachable_sub_classification() -> None:
    """Story 6.4 AC-2: OtelPipelineUnreachable → 'cost-telemetry-unavailable:
    otel-pipeline-unreachable' per marker-taxonomy.yaml:303-312."""
    exc = OtelPipelineUnreachable(
        prompt_id="prompt-x", story_id="6.4", diagnostic="connection refused"
    )
    marker, ctx = derive_cost_telemetry_unavailable_marker(
        story_id="6.4", prompt_id="prompt-x", exc=exc
    )
    assert marker == "cost-telemetry-unavailable: otel-pipeline-unreachable"
    assert ctx == {}


def test_derive_marker_prompt_id_correlation_missing_sub_classification() -> None:
    """Story 6.4 AC-2: PromptIdCorrelationMissing → 'cost-telemetry-unavailable:
    prompt-id-correlation-missing' per marker-taxonomy.yaml:303-312."""
    exc = PromptIdCorrelationMissing(
        prompt_id="prompt-x", story_id="6.4", diagnostic="0 events matched"
    )
    marker, ctx = derive_cost_telemetry_unavailable_marker(
        story_id="6.4", prompt_id="prompt-x", exc=exc
    )
    assert marker == "cost-telemetry-unavailable: prompt-id-correlation-missing"
    assert ctx == {}


def test_derive_marker_re_raises_on_unknown_exception_type() -> None:
    """Story 6.4 AC-2 + Pattern 5 / loud-fail: unknown exception types re-raise
    rather than silently classifying."""
    exc = RuntimeError("something else broke")
    with pytest.raises(RuntimeError, match="something else broke"):
        derive_cost_telemetry_unavailable_marker(
            story_id="6.4", prompt_id="prompt-x", exc=exc
        )


# --------------------------------------------------------------------------- #
# (h) collect happy path                                                      #
# --------------------------------------------------------------------------- #


@dataclasses.dataclass
class _StubOtelPipeline:
    """Test double satisfying :class:`OtelPipelineProtocol`."""

    events: tuple[CostEvent, ...] = ()
    raise_exception: BaseException | None = None

    def read_events(self, *, prompt_id: str) -> Sequence[CostEvent]:
        _ = prompt_id
        if self.raise_exception is not None:
            raise self.raise_exception
        return self.events


def test_collect_happy_path_returns_populated_aggregation(
    dispatch_payload: SpecialistDispatchPayload,
    deterministic_event_id_factory: Callable[[], str],
    fixed_timestamp: datetime,
) -> None:
    """Story 6.4 AC-1 + AC-6 (h): green pipeline → CollectionResult with
    populated aggregation + marker_classification=None."""
    pipeline = _StubOtelPipeline(
        events=(
            _make_event("dev", 1, 0.30),
            _make_event("review-bmad", 1, 0.20),
        )
    )
    result = collect(
        dispatch_payload,
        otel_pipeline=pipeline,
        return_envelope={"status": "pass", "rationale": "ok"},
        return_timestamp=fixed_timestamp,
        cost_delta_usd=0.30,
        otel_attributes={"prompt.id": "otel-id"},
        event_id_factory=deterministic_event_id_factory,
    )
    assert result.marker_classification is None
    assert result.cost_event is not None
    assert result.cost_event["event_class"] == "cost-event"
    assert dict(result.aggregation.per_specialist_per_retry) == {
        ("dev", 1): 0.30,
        ("review-bmad", 1): 0.20,
    }


# --------------------------------------------------------------------------- #
# (i) collect failure path — OtelPipelineUnreachable                          #
# --------------------------------------------------------------------------- #


def test_collect_otel_pipeline_unreachable_returns_marker_and_empty_aggregation(
    dispatch_payload: SpecialistDispatchPayload,
    deterministic_event_id_factory: Callable[[], str],
    fixed_timestamp: datetime,
) -> None:
    """Story 6.4 AC-2 + AC-6 (i): graceful-degrade — collect catches the
    exception; the loop continues; empty aggregation; correct marker."""
    pipeline = _StubOtelPipeline(
        raise_exception=OtelPipelineUnreachable(
            prompt_id=dispatch_payload.prompt_id,
            story_id=dispatch_payload.story_id,
            diagnostic="OTLP collector at localhost:4317 refused connection",
        ),
    )
    result = collect(
        dispatch_payload,
        otel_pipeline=pipeline,
        return_envelope={"status": "pass", "rationale": "ok"},
        return_timestamp=fixed_timestamp,
        cost_delta_usd=0.30,
        otel_attributes={},
        event_id_factory=deterministic_event_id_factory,
    )
    assert result.marker_classification == (
        "cost-telemetry-unavailable: otel-pipeline-unreachable",
        {},
    )
    assert dict(result.aggregation.per_specialist_per_retry) == {}
    assert dict(result.aggregation.per_specialist_totals) == {}
    assert result.cost_event is None


# --------------------------------------------------------------------------- #
# (j) collect failure path — PromptIdCorrelationMissing                       #
# --------------------------------------------------------------------------- #


def test_collect_prompt_id_correlation_missing_returns_correct_marker(
    dispatch_payload: SpecialistDispatchPayload,
    deterministic_event_id_factory: Callable[[], str],
    fixed_timestamp: datetime,
) -> None:
    """Story 6.4 AC-2 + AC-6 (j): graceful-degrade for the second sub-class."""
    pipeline = _StubOtelPipeline(
        raise_exception=PromptIdCorrelationMissing(
            prompt_id=dispatch_payload.prompt_id,
            story_id=dispatch_payload.story_id,
            diagnostic="0 returned events matched the queried prompt_id",
        ),
    )
    result = collect(
        dispatch_payload,
        otel_pipeline=pipeline,
        return_envelope={"status": "pass", "rationale": "ok"},
        return_timestamp=fixed_timestamp,
        cost_delta_usd=0.30,
        otel_attributes={},
        event_id_factory=deterministic_event_id_factory,
    )
    assert result.marker_classification == (
        "cost-telemetry-unavailable: prompt-id-correlation-missing",
        {},
    )
    assert dict(result.aggregation.per_specialist_per_retry) == {}


def test_collect_unknown_exception_propagates(
    dispatch_payload: SpecialistDispatchPayload,
    deterministic_event_id_factory: Callable[[], str],
    fixed_timestamp: datetime,
) -> None:
    """Story 6.4 AC-2 + Pattern 5: unknown exception types propagate (loud-fail
    doctrine forbids silent classification)."""
    pipeline = _StubOtelPipeline(
        raise_exception=RuntimeError("unexpected pipeline failure"),
    )
    with pytest.raises(RuntimeError, match="unexpected pipeline failure"):
        collect(
            dispatch_payload,
            otel_pipeline=pipeline,
            return_envelope={"status": "pass", "rationale": "ok"},
            return_timestamp=fixed_timestamp,
            cost_delta_usd=0.30,
            otel_attributes={},
            event_id_factory=deterministic_event_id_factory,
        )


def test_otel_pipeline_protocol_runtime_checkable() -> None:
    """Story 6.4: OtelPipelineProtocol is a runtime-checkable Protocol."""
    assert isinstance(_StubOtelPipeline(events=()), OtelPipelineProtocol)


def test_collection_result_is_frozen() -> None:
    """Story 6.4: CollectionResult is frozen for determinism."""
    result = CollectionResult(
        cost_event=None,
        aggregation=CostAggregation(),
        marker_classification=None,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.cost_event = {}  # type: ignore[misc]
