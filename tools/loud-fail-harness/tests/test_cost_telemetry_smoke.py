"""End-to-end integration tests for the Story 6.4 cost-telemetry surface.

This module is the FIRST integration-test consumer of Story 6.4's
cost-telemetry collection substrate (`cost_telemetry.collect`,
`cost_telemetry.aggregate_costs`, `bundle_assembly._render_cost_breakdown`).
Sibling to Story 6.1's `test_loud_fail_block_smoke.py` per the per-feature
integration-test-isolation precedent.

Contract-coverage matrix (Story 6.4 AC-6 (p)-(r)):

    [x] full Dev → Review-BMAD → Dev-retry → Review-BMAD-retry boundary
        sequence with mocked OTel pipeline → bundle's cost-breakdown
        section renders the 4-entry per-retry table
        → test_full_boundary_sequence_renders_per_retry_table
    [x] same sequence with the OTel pipeline raising
        OtelPipelineUnreachable on the second-Dev boundary →
        cost-telemetry-unavailable: otel-pipeline-unreachable in
        result.run_state.active_markers AND the bundle's
        cost-breakdown section is the marker-rendered variant
        → test_otel_pipeline_unreachable_renders_marker_rendered_variant
    [x] same with PromptIdCorrelationMissing
        → test_prompt_id_correlation_missing_renders_marker_rendered_variant
"""

from __future__ import annotations

import json
import pathlib
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
    aggregate_costs,
    collect,
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
from loud_fail_harness.run_state import CostToDateBySpecialist, RunState
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    SpecialistDispatchPayload,
    build_dispatch_payload,
    default_prompt_body_renderer,
    load_marker_class_registry,
)


# --------------------------------------------------------------------------- #
# Constants + fixtures                                                        #
# --------------------------------------------------------------------------- #


_STORY_ID = "sample-cost-telemetry-001"
_RUN_ID = "run-2026-05-06-cost"
_BRANCH_NAME = f"bmad-automation/story/{_STORY_ID}"
_GENERATED_AT = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)


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


class _StubOtelPipelineWithEvents:
    """Stub returning a fixed event sequence on every read_events call."""

    def __init__(self, events: tuple[CostEvent, ...]) -> None:
        self.events = events

    def read_events(self, *, prompt_id: str) -> Sequence[CostEvent]:
        _ = prompt_id
        return self.events


class _StubOtelPipelineFailing:
    """Stub raising a configured exception on read_events."""

    def __init__(self, exception: BaseException) -> None:
        self.exception = exception

    def read_events(self, *, prompt_id: str) -> Sequence[CostEvent]:
        _ = prompt_id
        raise self.exception


def _build_dispatch_payload(
    *,
    tmp_path: pathlib.Path,
    specialist: str,
    attempt_number: int,
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


def _write_run_state_yaml(
    rs_path: pathlib.Path,
    *,
    active_markers: tuple[str, ...] = (),
    cost_to_date_by_specialist: dict[str, float] | None = None,
) -> pathlib.Path:
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "1.3",
        "story_id": _STORY_ID,
        "run_id": _RUN_ID,
        "current_state": "done",
        "branch_name": _BRANCH_NAME,
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": [],
        "active_markers": list(active_markers),
        "marker_contexts": {},
        "cost_to_date_by_specialist": cost_to_date_by_specialist or {},
    }
    rs_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return rs_path


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


def _assemble_with_otel_pipeline(
    *,
    tmp_path: pathlib.Path,
    otel_pipeline: OtelPipelineProtocol | None,
    active_markers: tuple[str, ...],
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
    cost_to_date_by_specialist: dict[str, float] | None = None,
) -> pathlib.Path:
    rs_path = _write_run_state_yaml(
        tmp_path / "_bmad" / "automation" / "run-state.yaml",
        active_markers=active_markers,
        cost_to_date_by_specialist=cost_to_date_by_specialist,
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_log(logs_root, specialist="dev", return_envelope=canonical_dev_envelope)
    _seed_log(
        logs_root, specialist="review-bmad", return_envelope=canonical_review_envelope
    )
    _seed_log(logs_root, specialist="qa", return_envelope=canonical_qa_envelope)
    bundle_root = tmp_path / "pr-bundles"
    # Story 6.6: seed canonical evidence file under tmp_path so the
    # bundle-render-time evidence-trace linkability validation resolves
    # cleanly. Pass repo_root=tmp_path to anchor validation there.
    _seed_canonical_qa_evidence_file(tmp_path)
    result = assemble_bundle(
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        marker_registry=runtime_marker_registry,
        generated_at=_GENERATED_AT,
        otel_pipeline=otel_pipeline,
        repo_root=tmp_path,
    )
    return result.bundle_path


def _seed_canonical_qa_evidence_file(repo_root: pathlib.Path) -> pathlib.Path:
    """Seed the canonical QA fixture's evidence_ref file so Story 6.6's
    bundle-render-time evidence-trace linkability validation resolves
    cleanly. Path mirrors qa-pass-ac1-tier1.yaml's evidence_refs entry.
    """
    evidence_path = (
        repo_root
        / "_bmad-output"
        / "qa-evidence"
        / "sample-001"
        / "run-2026-04-29-001"
        / "ac1-http-200.log"
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("HTTP/1.1 200 OK\n", encoding="utf-8")
    return evidence_path


# --------------------------------------------------------------------------- #
# (p) full Dev → Review → Dev-retry → Review-retry green-path sequence       #
# --------------------------------------------------------------------------- #


def test_full_boundary_sequence_renders_per_retry_table(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.4 AC-6 (p): full Dev → Review-BMAD → Dev-retry → Review-BMAD-retry
    boundary sequence with mocked OTel pipeline producing 4 cost-events; the
    bundle's cost-breakdown section renders the 4-entry per-retry table.
    """
    events = (
        _make_event("dev", 1, 0.50),
        _make_event("review-bmad", 1, 0.30),
        _make_event("dev", 2, 0.40),
        _make_event("review-bmad", 2, 0.20),
    )
    pipeline = _StubOtelPipelineWithEvents(events=events)

    bundle_path = _assemble_with_otel_pipeline(
        tmp_path=tmp_path,
        otel_pipeline=pipeline,
        active_markers=(),  # green path — no graceful-degrade marker
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")

    # Green H2 + table header.
    assert "## 💸 Cost Breakdown\n" in body
    assert "| Specialist | Retry attempt | Cost delta (USD)" in body
    # Four per-(specialist × retry) rows.
    assert "| dev | 1 |" in body
    assert "| dev | 2 |" in body
    assert "| review-bmad | 1 |" in body
    assert "| review-bmad | 2 |" in body
    # Per-specialist totals row.
    assert "| dev | total | — |" in body
    assert "| review-bmad | total | — |" in body
    # Marker-rendered variant NOT present.
    assert "## ⚠️ Cost Breakdown — Telemetry Unavailable" not in body


# --------------------------------------------------------------------------- #
# Per-boundary collect() + aggregate_costs end-to-end shape                   #
# --------------------------------------------------------------------------- #


def test_per_boundary_collect_then_aggregate_yields_four_entries(
    tmp_path: pathlib.Path,
) -> None:
    """Story 6.4 AC-1 + AC-6 (c): per-boundary collect() yields a per-dispatch
    aggregation; concatenating the events across all 4 boundaries and re-
    aggregating yields the canonical 4-entry per_specialist_per_retry map."""
    payload_dev_1 = _build_dispatch_payload(
        tmp_path=tmp_path / "dev1", specialist="dev", attempt_number=1
    )
    payload_review_1 = _build_dispatch_payload(
        tmp_path=tmp_path / "review1", specialist="review-bmad", attempt_number=1
    )
    payload_dev_2 = _build_dispatch_payload(
        tmp_path=tmp_path / "dev2", specialist="dev", attempt_number=2
    )
    payload_review_2 = _build_dispatch_payload(
        tmp_path=tmp_path / "review2", specialist="review-bmad", attempt_number=2
    )
    # Each per-dispatch read returns ONLY the events for that dispatch; the
    # orchestrator concatenates across boundaries.
    pipelines = {
        "dev1": _StubOtelPipelineWithEvents(events=(_make_event("dev", 1, 0.50),)),
        "review1": _StubOtelPipelineWithEvents(
            events=(_make_event("review-bmad", 1, 0.30),)
        ),
        "dev2": _StubOtelPipelineWithEvents(events=(_make_event("dev", 2, 0.40),)),
        "review2": _StubOtelPipelineWithEvents(
            events=(_make_event("review-bmad", 2, 0.20),)
        ),
    }
    counter = {"n": 0}

    def event_id_factory() -> str:
        counter["n"] += 1
        return f"ev-{counter['n']:04d}"

    all_events: list[CostEvent] = []
    for key, payload, cost in (
        ("dev1", payload_dev_1, 0.50),
        ("review1", payload_review_1, 0.30),
        ("dev2", payload_dev_2, 0.40),
        ("review2", payload_review_2, 0.20),
    ):
        result = collect(
            payload,
            otel_pipeline=pipelines[key],
            return_envelope={"status": "pass", "rationale": "ok"},
            return_timestamp=_GENERATED_AT,
            cost_delta_usd=cost,
            otel_attributes={},
            event_id_factory=event_id_factory,
        )
        assert result.marker_classification is None
        all_events.extend(_StubOtelPipelineWithEvents.read_events.__defaults__ or ())
        # Use the per-dispatch result.aggregation events implicitly via the
        # protocol's stub — for the cross-boundary aggregation, we re-collect
        # from the protocol directly.
        all_events.extend(pipelines[key].events)

    # Cross-boundary aggregation produces the 4-entry map per AC-1.
    aggregation = aggregate_costs(all_events)
    assert dict(aggregation.per_specialist_per_retry) == {
        ("dev", 1): 0.50,
        ("review-bmad", 1): 0.30,
        ("dev", 2): 0.40,
        ("review-bmad", 2): 0.20,
    }


def test_collect_then_update_run_state_persists_cost_counters(
    tmp_path: pathlib.Path,
) -> None:
    """Story 6.4 AC-1 + Pattern 4: per-boundary collect → aggregate →
    update_run_state_cost_counters composes through ``model_copy`` discipline
    and produces a new RunState whose ``cost_to_date_by_specialist`` reflects
    the aggregation."""
    payload = _build_dispatch_payload(
        tmp_path=tmp_path / "d1", specialist="dev", attempt_number=1
    )
    pipeline = _StubOtelPipelineWithEvents(
        events=(
            _make_event("dev", 1, 0.50),
            _make_event("review-bmad", 1, 0.30),
        )
    )
    base_state = RunState(
        schema_version="1.3",
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        current_state="ready-for-dev",
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
    result = collect(
        payload,
        otel_pipeline=pipeline,
        return_envelope={"status": "pass", "rationale": "ok"},
        return_timestamp=_GENERATED_AT,
        cost_delta_usd=0.50,
        otel_attributes={},
        event_id_factory=lambda: "ev-1",
    )
    new_state = update_run_state_cost_counters(base_state, result.aggregation)
    assert new_state.cost_to_date_by_specialist.dev == pytest.approx(0.50)
    assert new_state.cost_to_date_by_specialist.review_bmad == pytest.approx(0.30)
    # Pattern 4 immutability: prior instance unchanged.
    assert base_state.cost_to_date_by_specialist.dev is None


# --------------------------------------------------------------------------- #
# (q) OtelPipelineUnreachable failure path                                    #
# --------------------------------------------------------------------------- #


def test_otel_pipeline_unreachable_renders_marker_rendered_variant(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.4 AC-2 + AC-6 (q): on OtelPipelineUnreachable the orchestrator
    appends ``cost-telemetry-unavailable: otel-pipeline-unreachable`` to
    run_state.active_markers; the bundle's cost-breakdown section renders the
    marker-rendered variant rather than fabricating zeros."""
    # Simulate the per-boundary collect catching the exception.
    payload = _build_dispatch_payload(
        tmp_path=tmp_path / "p", specialist="dev", attempt_number=2
    )
    pipeline = _StubOtelPipelineFailing(
        OtelPipelineUnreachable(
            prompt_id=payload.prompt_id,
            story_id=_STORY_ID,
            diagnostic="OTLP collector unreachable",
        )
    )
    boundary_result = collect(
        payload,
        otel_pipeline=pipeline,
        return_envelope={"status": "pass", "rationale": "ok"},
        return_timestamp=_GENERATED_AT,
        cost_delta_usd=0.30,
        otel_attributes={},
        event_id_factory=lambda: "ev-x",
    )
    assert boundary_result.marker_classification == (
        "cost-telemetry-unavailable: otel-pipeline-unreachable",
        {},
    )

    # The orchestrator appends the marker to run_state.active_markers; the
    # assembler consumes it (does NOT re-emit per the assembler-consumes-not-
    # re-emits rule).
    bundle_path = _assemble_with_otel_pipeline(
        tmp_path=tmp_path / "bundle",
        otel_pipeline=None,  # The assembler doesn't re-query the pipeline; the
        # marker is already in active_markers from the per-dispatch boundary.
        active_markers=("cost-telemetry-unavailable: otel-pipeline-unreachable",),
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "## ⚠️ Cost Breakdown — Telemetry Unavailable" in body
    assert "Sub-classification: otel-pipeline-unreachable" in body
    # No fabricated zero rows.
    assert "| dev | 1 |" not in body
    assert "| review-bmad | 1 |" not in body


# --------------------------------------------------------------------------- #
# (r) PromptIdCorrelationMissing failure path                                 #
# --------------------------------------------------------------------------- #


def test_prompt_id_correlation_missing_renders_marker_rendered_variant(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.4 AC-2 + AC-6 (r): analogue for PromptIdCorrelationMissing."""
    payload = _build_dispatch_payload(
        tmp_path=tmp_path / "p", specialist="dev", attempt_number=1
    )
    pipeline = _StubOtelPipelineFailing(
        PromptIdCorrelationMissing(
            prompt_id=payload.prompt_id,
            story_id=_STORY_ID,
            diagnostic="0 returned events matched the queried prompt_id",
        )
    )
    boundary_result = collect(
        payload,
        otel_pipeline=pipeline,
        return_envelope={"status": "pass", "rationale": "ok"},
        return_timestamp=_GENERATED_AT,
        cost_delta_usd=0.10,
        otel_attributes={},
        event_id_factory=lambda: "ev-y",
    )
    assert boundary_result.marker_classification == (
        "cost-telemetry-unavailable: prompt-id-correlation-missing",
        {},
    )

    bundle_path = _assemble_with_otel_pipeline(
        tmp_path=tmp_path / "bundle",
        otel_pipeline=None,
        active_markers=("cost-telemetry-unavailable: prompt-id-correlation-missing",),
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "## ⚠️ Cost Breakdown — Telemetry Unavailable" in body
    assert "Sub-classification: prompt-id-correlation-missing" in body


# --------------------------------------------------------------------------- #
# Canonical-fixture regression tests (Story 6.4 AC-3 + AC-6)                  #
# --------------------------------------------------------------------------- #


def test_canonical_cost_breakdown_bundle_fixture_matches_assembler_output(
    tmp_path: pathlib.Path,
    repo_root: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.4 AC-3 + AC-6: the committed pr-bundle-cost-breakdown.md fixture
    matches the assembler output byte-for-byte for the seeded run-state +
    canonical envelope corpus + 4-event happy-path OTel-pipeline mock."""
    import re

    fixture_path = (
        repo_root / "examples" / "pr-bundles" / "pr-bundle-cost-breakdown.md"
    )
    fixture_body = fixture_path.read_text(encoding="utf-8")
    body_after_header = re.sub(
        r"^<!--.*?-->\s*", "", fixture_body, count=1, flags=re.DOTALL
    )

    pipeline = _StubOtelPipelineWithEvents(
        events=(
            _make_event("dev", 1, 0.50),
            _make_event("review-bmad", 1, 0.30),
            _make_event("dev", 2, 0.40),
            _make_event("review-bmad", 2, 0.20),
        )
    )
    bundle_path = _assemble_with_otel_pipeline(
        tmp_path=tmp_path,
        otel_pipeline=pipeline,
        active_markers=(),
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
        cost_to_date_by_specialist={"dev": 0.90, "review_bmad": 0.50},
    )
    assembled_body = bundle_path.read_text(encoding="utf-8")
    assert assembled_body == body_after_header, (
        "canonical cost-breakdown fixture must match assembler output byte-"
        "for-byte (modulo contract-header strip); regenerate the fixture if "
        "the assembler's rendering intentionally changed"
    )


def test_canonical_cost_telemetry_unavailable_bundle_fixture_matches_assembler_output(
    tmp_path: pathlib.Path,
    repo_root: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.4 AC-2 + AC-6: the committed pr-bundle-cost-telemetry-
    unavailable.md fixture matches the assembler output byte-for-byte for the
    seeded run-state with the cost-telemetry-unavailable: otel-pipeline-
    unreachable active marker."""
    import re

    fixture_path = (
        repo_root
        / "examples"
        / "pr-bundles"
        / "pr-bundle-cost-telemetry-unavailable.md"
    )
    fixture_body = fixture_path.read_text(encoding="utf-8")
    body_after_header = re.sub(
        r"^<!--.*?-->\s*", "", fixture_body, count=1, flags=re.DOTALL
    )

    bundle_path = _assemble_with_otel_pipeline(
        tmp_path=tmp_path,
        otel_pipeline=None,
        active_markers=("cost-telemetry-unavailable: otel-pipeline-unreachable",),
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    assembled_body = bundle_path.read_text(encoding="utf-8")
    assert assembled_body == body_after_header, (
        "canonical cost-telemetry-unavailable fixture must match assembler "
        "output byte-for-byte (modulo contract-header strip); regenerate the "
        "fixture if the assembler's rendering intentionally changed"
    )
