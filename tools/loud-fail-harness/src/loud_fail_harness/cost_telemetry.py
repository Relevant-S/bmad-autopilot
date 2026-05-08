"""Per-specialist × per-retry cost telemetry collection — Story 6.4 substrate module.

## Substrate-component identity

THIS module is a substrate **library** sibling of
:mod:`loud_fail_harness.run_state` / :mod:`loud_fail_harness.specialist_dispatch`
/ :mod:`loud_fail_harness.retry_dispatch` per architecture.md lines 311-315.
It is NOT a sixth substrate component beyond ADR-003 Consequence 1's
enumerated five (envelope_validator, event_validator, reconciler,
enumeration_check, fixture_coverage); the count remains FIVE.

## Architectural anchors

- **NFR-P5** (PRD line 938) — Per-specialist × per-retry cost observability:
  the bundle's cost-breakdown section is partitioned by specialist AND by
  retry attempt within each specialist.
- **NFR-O8** (PRD line 987) — In-flight cost observability at each
  specialist completion + 75%-of-ceiling threshold detection (Story 6.5
  consumes this module's :class:`CostAggregation`).
- **ADR-006 Combo 3** (architecture.md lines 543-602):
    * **A3'** — orchestrator-owned ``prompt_id`` correlation; the
      orchestrator records ``(prompt_id, retry_attempt, specialist)``
      per dispatch (already implemented at
      :func:`loud_fail_harness.specialist_dispatch._derive_prompt_id`
      + :class:`SpecialistDispatchPayload.prompt_id`); between
      specialist completions the orchestrator reads OTel events
      filtered by ``prompt_id``; this module aggregates per-specialist
      × per-retry totals.
    * **B1** — operator-managed OTLP backend (Story 7's ``init`` command
      scaffolds collector configuration; out of Story 6.4's scope).
    * **C3** — hybrid persistence: run-state caches in-flight cost
      counters via ``cost_to_date_by_specialist`` (already in schema);
      OTel backend stores full per-(specialist × retry) historical
      detail.
- **Pattern 3** (architecture.md lines 968-971) — OTel-derived attributes
  pass through unchanged: ``prompt.id``, ``claude_code.cost.usage``,
  ``claude_code.token.usage``, ``query_source`` keep their
  dotted/mixed-case OTel naming verbatim while the orchestrator-internal
  snake_case ``prompt_id`` coexists as a distinct named field.
- **Pattern 4** (architecture.md lines 977-981) — All run-state writes
  go through atomic-write helpers; cost-counter writes batch with other
  run-state writes between specialist completions.
  :func:`update_run_state_cost_counters` is a PURE FUNCTIONAL update
  returning a new :class:`RunState` — it does NOT call
  :func:`loud_fail_harness.run_state.advance_run_state`. The orchestrator
  composes the cost-counter update INTO the next-state argument it
  passes to ``advance_run_state``; there is exactly one atomic write
  per seam transition; the cost-counter update rides along.
- **Pattern 5** (architecture.md) — Loud-fail / named invariants:
  unknown OTel-pipeline failure modes re-raise; only the two documented
  sub-classifications translate into a ``cost-telemetry-unavailable``
  marker emission.

## OtelPipelineProtocol — bridge-layer boundary

ADR-006 Consequence 5 verbatim: "OTel metric and attribute names are
host-Bridge per ADR-002's two-axis classification ... the binding to
specific OTel metric/attribute names is the bridge layer." The
:class:`OtelPipelineProtocol` IS the bridge-layer structural boundary.
The harness substrate stays decoupled from ``opentelemetry-api`` at the
type level; the orchestrator skill at runtime instantiates a concrete
protocol implementation against the operator-managed OTLP backend.
This composition pattern follows Story 2.6's sensor-not-advisor +
caller-injected-factory convention (``event_id_factory``,
``dispatch_timestamp_factory``).

## Public API

    * :class:`CostEvent` — frozen dataclass mirroring the
      ``cost-event`` branch at ``schemas/orchestrator-event.yaml``
      lines 375-416. OTel pass-through fields preserved verbatim.
    * :class:`OtelPipelineProtocol` — the single boundary the
      orchestrator dispatches across.
    * :class:`CostAggregation` — frozen dataclass with
      ``per_specialist_totals`` + ``per_specialist_per_retry`` fields.
    * :class:`CollectionResult` — frozen dataclass returned by
      :func:`collect`.
    * :func:`record_cost_event` — composes through
      :func:`loud_fail_harness.specialist_dispatch.make_cost_event`;
      validates against the schema.
    * :func:`aggregate_costs` — pure; idempotent; byte-stable.
    * :func:`update_run_state_cost_counters` — pure functional update
      via Pydantic ``model_copy`` discipline.
    * :func:`derive_cost_telemetry_unavailable_marker` — translates
      OTel-pipeline exceptions into ``(marker_class, context)`` pairs
      per the marker-taxonomy.yaml v1 sub-classifications.
    * :func:`collect` — canonical orchestrator-side entry point
      composing the above.

## Cross-references

    * Story 1.3 ``schemas/orchestrator-event.yaml`` lines 375-416 —
      ``cost-event`` branch (consumed AS-IS; THIS story does NOT
      modify the schema).
    * Story 1.4 ``schemas/marker-taxonomy.yaml`` lines 303-312 —
      ``cost-telemetry-unavailable`` v1 entry with two
      ``sub_classifications`` (``otel-pipeline-unreachable``,
      ``prompt-id-correlation-missing``).
    * Story 2.2 :class:`loud_fail_harness.run_state.RunState` +
      :class:`CostToDateBySpecialist` (consumed AS-IS).
    * Story 2.6 :func:`loud_fail_harness.specialist_dispatch.make_cost_event`
      (added by THIS story; the schema-validating event constructor).
    * Story 6.1 :func:`loud_fail_harness.bundle_assembly._render_loud_fail_block`
      — consumed AS-IS for the ``cost-telemetry-unavailable`` marker
      surface.
    * Story 6.2 ``pointer_context_fields`` empty-context shape — the
      ``cost-telemetry-unavailable`` taxonomy entry has empty
      ``pointer_context_fields: []``; the diagnostic_pointer renders
      verbatim.
    * Story 6.3 ``_data/marker_coverage_surfaces.yaml`` — THIS story
      flips the ``cost-telemetry-unavailable × cost-telemetry-pipeline``
      row from ``scheduled-by-story`` to ``emitted``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from loud_fail_harness.exceptions import (
    OtelPipelineUnreachable,
    PromptIdCorrelationMissing,
)
from loud_fail_harness.run_state import CostToDateBySpecialist, RunState
from loud_fail_harness.specialist_dispatch import (
    EventIdFactory,
    SpecialistDispatchPayload,
    make_cost_event,
)


__all__ = [
    "CostAggregation",
    "CostEvent",
    "CollectionResult",
    "OtelPipelineProtocol",
    "aggregate_costs",
    "collect",
    "derive_cost_telemetry_unavailable_marker",
    "record_cost_event",
    "update_run_state_cost_counters",
]


#: Mapping from kebab-case specialist enum values (per the
#: ``orchestrator-event.yaml`` ``specialist`` enum at line 407 +
#: ``schemas/run-state.yaml`` lines 351-385) to the snake_case field names
#: on :class:`CostToDateBySpecialist`. Pattern 1's structural-keys boundary
#: at architecture.md lines 932-935 — specialist enum stays kebab-case;
#: structural map keys stay snake_case.
_SPECIALIST_TO_RUN_STATE_KEY: Mapping[str, str] = {
    "dev": "dev",
    "review-bmad": "review_bmad",
    "qa": "qa",
    "lad": "lad",
}


@dataclasses.dataclass(frozen=True)
class CostEvent:
    """Frozen mirror of the ``cost-event`` branch at
    ``schemas/orchestrator-event.yaml`` lines 375-416.

    Mirrors the schema 1:1. Snake_case internal fields per Pattern 1;
    the four OTel pass-through attribute keys preserve their original
    dotted/mixed-case naming verbatim per Pattern 3 — they live in the
    ``otel_attributes`` mapping rather than as named dataclass fields
    so the dotted keys (``prompt.id``, ``claude_code.cost.usage``,
    ``claude_code.token.usage``, ``query_source``) remain valid Python
    mapping keys without Python-level transliteration.

    Frozen for determinism + hashability per Epic 1 retro Action #2.
    """

    event_id: str
    timestamp: str
    story_id: str
    prompt_id: str
    retry_attempt: int
    specialist: str
    cost_delta_usd: float
    otel_attributes: Mapping[str, Any] = dataclasses.field(
        default_factory=dict
    )


@dataclasses.dataclass(frozen=True)
class CostAggregation:
    """Pure aggregation of a sequence of :class:`CostEvent`.

    Two read-only mappings:

        * ``per_specialist_totals`` — cumulative cost per specialist
          (snake_case key per Pattern 1's structural-keys boundary —
          ``dev`` / ``review_bmad`` / ``qa`` / ``lad``; specialist enum
          values transliterated to snake_case via
          :data:`_SPECIALIST_TO_RUN_STATE_KEY`).
        * ``per_specialist_per_retry`` — the
          ``(specialist, retry_attempt)`` tuple → cumulative
          ``cost_delta_usd`` map. Specialist key here is the kebab-case
          enum value (``dev`` / ``review-bmad`` / ``qa`` / ``lad``)
          paralleling the schema's ``specialist`` enum at
          ``orchestrator-event.yaml`` line 407 — the bundle renderer
          consumes this surface for the per-retry table.

    Frozen + idempotent + byte-stable per Story 6.1's regression-fixture
    discipline: the same input sequence always yields the same
    aggregation; the aggregation is pure (no I/O; no run-state read).
    """

    per_specialist_totals: Mapping[str, float] = dataclasses.field(
        default_factory=dict
    )
    per_specialist_per_retry: Mapping[tuple[str, int], float] = dataclasses.field(
        default_factory=dict
    )


@dataclasses.dataclass(frozen=True)
class CollectionResult:
    """Return shape of :func:`collect`.

    Field semantics:

        * ``cost_event`` — the schema-valid ``cost-event`` dict
          constructed at the per-dispatch boundary; the orchestrator
          appends this to the orchestrator-event log. ``None`` on the
          graceful-degrade path (the pipeline failed before the event
          could be constructed against the OTel-side payload).
        * ``aggregation`` — the :class:`CostAggregation` computed from
          the OTel-pipeline-returned events. Empty on the
          graceful-degrade path per AC-2.
        * ``marker_classification`` — ``None`` on the green path; the
          ``(marker_class, marker_context)`` pair on the
          graceful-degrade path. The orchestrator uses this to decide
          whether to append to ``run_state.active_markers`` +
          ``run_state.marker_contexts`` per Pattern 4.
    """

    cost_event: dict[str, Any] | None
    aggregation: CostAggregation
    marker_classification: tuple[str, Mapping[str, object]] | None


@runtime_checkable
class OtelPipelineProtocol(Protocol):
    """The single boundary the orchestrator dispatches across.

    Per ADR-006 Consequence 5 the OTel-pipeline binding is the bridge
    layer. The harness substrate stays decoupled from
    ``opentelemetry-api`` at the type level; the orchestrator skill at
    runtime instantiates a concrete protocol implementation against the
    operator-managed OTLP backend.

    Production implementations may also use this protocol as the test
    double: a stub raising :exc:`OtelPipelineUnreachable` /
    :exc:`PromptIdCorrelationMissing` on demand exercises the
    graceful-degrade path; a stub returning a deterministic
    ``Sequence[CostEvent]`` exercises the green path.
    """

    def read_events(self, *, prompt_id: str) -> Sequence["CostEvent"]:
        """Return cost-events the OTel backend has recorded for ``prompt_id``.

        This method serves **two calling conventions** within the substrate:

        1. **Per-dispatch read** (via :func:`collect`) — ``prompt_id`` is
           the orchestrator-internal correlation key for a single specialist
           dispatch (per ADR-006 Combo 3 / A3'). Returns the cost-events
           recorded during that specific invocation.

        2. **Run-scoped read** (via :func:`bundle_assembly._load_cost_aggregation`)
           — ``prompt_id`` is the ``story_id`` of the run. Returns all
           cost-events across all specialist dispatches for that run.
           Concrete implementations must interpret ``prompt_id`` as a
           run-scoped filter in this context.

        Protocol implementers must support both calling conventions.
        The distinction is purely in what the caller passes as
        ``prompt_id``; the method signature is identical.

        Raises :exc:`OtelPipelineUnreachable` if the backend is
        unreachable. Raises :exc:`PromptIdCorrelationMissing` if the
        backend returns events whose ``prompt.id`` attribute is missing
        or does not match the queried ``prompt_id``. The two exceptions
        correspond exactly to the two ``sub_classifications`` of
        ``cost-telemetry-unavailable`` in the v1 marker taxonomy.
        """
        ...


def record_cost_event(
    payload: SpecialistDispatchPayload,
    *,
    return_envelope: dict[str, Any],
    return_timestamp: datetime,
    cost_delta_usd: float,
    otel_attributes: Mapping[str, Any],
    event_id_factory: EventIdFactory,
) -> dict[str, Any]:
    """Construct a schema-valid ``cost-event`` dict (Story 6.4 / AC-1).

    Composes through
    :func:`loud_fail_harness.specialist_dispatch.make_cost_event` —
    that function is the single source of truth for ``cost-event``
    construction and schema validation, mirroring Story 2.6's
    ``make_specialist_dispatched_event`` /
    ``make_specialist_returned_event`` posture.

    Raises :exc:`loud_fail_harness.specialist_dispatch.EventConstructionFailed`
    on schema mismatch.
    """
    return make_cost_event(
        payload,
        return_envelope=return_envelope,
        return_timestamp=return_timestamp,
        cost_delta_usd=cost_delta_usd,
        otel_attributes=otel_attributes,
        event_id_factory=event_id_factory,
    )


def aggregate_costs(events: Sequence[CostEvent]) -> CostAggregation:
    """Aggregate a sequence of cost-events into a :class:`CostAggregation`.

    Pure (no I/O; no run-state read). Idempotent: same input always
    yields the same aggregation byte-for-byte per the byte-stable
    regression-fixture discipline (Story 6.1 / 6.3).

    Per AC-1's verbatim Dev → Review → Dev-retry → Review sequence
    (4 events: ``("dev", 1)``, ``("review-bmad", 1)``, ``("dev", 2)``,
    ``("review-bmad", 2)``), the resulting ``per_specialist_per_retry``
    map has exactly four entries (one per ``(specialist,
    retry_attempt)`` tuple); ``per_specialist_totals`` carries the sum
    per specialist (snake_case key per Pattern 1).
    """
    per_retry: dict[tuple[str, int], float] = {}
    per_specialist: dict[str, float] = {}
    for event in events:
        retry_key = (event.specialist, event.retry_attempt)
        per_retry[retry_key] = per_retry.get(retry_key, 0.0) + event.cost_delta_usd

        run_state_key = _SPECIALIST_TO_RUN_STATE_KEY.get(event.specialist)
        if run_state_key is None:
            # Specialist enum value not in the documented set — silently
            # skipping would violate the loud-fail doctrine, but raising
            # here would mean a malformed event mid-aggregation kills the
            # whole batch. The schema's ``specialist`` enum at
            # ``orchestrator-event.yaml`` line 407 enforces the membership
            # at event-construction time; reaching this branch with a
            # validated event is structurally impossible. We still skip
            # the per-specialist update defensively (the per-retry update
            # records the unknown specialist key for diagnostic visibility).
            continue
        per_specialist[run_state_key] = (
            per_specialist.get(run_state_key, 0.0) + event.cost_delta_usd
        )
    return CostAggregation(
        per_specialist_totals=per_specialist,
        per_specialist_per_retry=per_retry,
    )


def update_run_state_cost_counters(
    state: RunState,
    aggregation: CostAggregation,
) -> RunState:
    """Return a new :class:`RunState` with ``cost_to_date_by_specialist``
    populated from ``aggregation.per_specialist_totals``.

    Pure functional update via Pydantic ``model_copy`` discipline
    (run_state.py:178-184). Does NOT call
    :func:`loud_fail_harness.run_state.advance_run_state` — the
    orchestrator composes this :class:`RunState` INTO the next-state
    argument it already passes to ``advance_run_state`` per Pattern 4's
    "cost-counter writes batch with other run-state writes between
    specialist completions" rule.

    The prior ``state`` instance is unchanged (frozen-tuple immutability
    invariant per Story 2.2's Pydantic frozen-model pattern).
    """
    totals = aggregation.per_specialist_totals
    new_cost_model = CostToDateBySpecialist(
        dev=totals.get("dev"),
        review_bmad=totals.get("review_bmad"),
        qa=totals.get("qa"),
        lad=totals.get("lad"),
    )
    return state.model_copy(update={"cost_to_date_by_specialist": new_cost_model})


def derive_cost_telemetry_unavailable_marker(
    *,
    story_id: str,
    prompt_id: str,
    exc: BaseException,
) -> tuple[str, Mapping[str, object]]:
    """Translate an OTel-pipeline exception into a
    ``(marker_class, marker_context)`` pair per the v1 marker taxonomy
    at ``schemas/marker-taxonomy.yaml`` lines 303-312.

    Returns the literal string ``"cost-telemetry-unavailable"``
    followed by a ``: <sub_class>`` suffix per Pattern 2's
    sub-classification format (architecture.md line 962). The
    ``<sub_class>`` is:

        * ``otel-pipeline-unreachable`` if
          ``isinstance(exc, OtelPipelineUnreachable)``.
        * ``prompt-id-correlation-missing`` if
          ``isinstance(exc, PromptIdCorrelationMissing)``.

    On any other exception type the function **re-raises** the
    original exception unchanged — Pattern 5 / loud-fail doctrine
    forbids silent classification of unknown failure modes; the
    orchestrator's existing top-level error handler is the boundary
    that decides whether to halt or escalate.

    The returned ``marker_context`` is an empty mapping because the
    taxonomy entry's ``pointer_context_fields: []`` — the
    ``cost-telemetry-unavailable`` marker takes zero context fields
    in the v1 taxonomy; the rendered ``- How to enable:`` pointer is
    the diagnostic_pointer text rendered verbatim (per Story 6.2's
    ``pointer_context_fields`` empty-context shape). The
    structural-slot mapping is preserved for forward-compat.

    The ``story_id`` + ``prompt_id`` arguments are accepted for caller-
    side correlation symmetry with
    :exc:`OtelPipelineUnreachable.__str__` / NFR-O5 named-invariant
    diagnostics; they do not flow into the returned marker context
    because the v1 taxonomy entry takes no context fields.
    """
    _ = story_id, prompt_id  # accepted for caller-side NFR-O5 correlation symmetry
    if isinstance(exc, OtelPipelineUnreachable):
        return ("cost-telemetry-unavailable: otel-pipeline-unreachable", {})
    if isinstance(exc, PromptIdCorrelationMissing):
        return ("cost-telemetry-unavailable: prompt-id-correlation-missing", {})
    raise exc


def collect(
    payload: SpecialistDispatchPayload,
    *,
    otel_pipeline: OtelPipelineProtocol,
    return_envelope: dict[str, Any],
    return_timestamp: datetime,
    cost_delta_usd: float,
    otel_attributes: Mapping[str, Any],
    event_id_factory: EventIdFactory,
) -> CollectionResult:
    """Canonical orchestrator-side entry point.

    Composition flow:

        1. Construct the schema-valid ``cost-event`` dict via
           :func:`record_cost_event`.
        2. Read the OTel-recorded events for this dispatch's
           ``prompt_id`` via the protocol.
        3. Aggregate via :func:`aggregate_costs`.
        4. Translate OTel-pipeline exceptions into
           ``marker_classification`` per
           :func:`derive_cost_telemetry_unavailable_marker`.

    Returns:
        :class:`CollectionResult` carrying:

            * ``cost_event`` — the schema-valid event dict on the green
              path; ``None`` on the graceful-degrade path (the dict is
              constructed successfully before the OTel read but discarded —
              logging a cost event without OTel-read confirmation would
              fabricate an unverified record; the orchestrator-event log
              records the failure via the marker instead).
            * ``aggregation`` — populated on the green path; empty on
              the graceful-degrade path per AC-2.
            * ``marker_classification`` — ``None`` on the green path;
              the ``(marker_class, marker_context)`` pair on the
              graceful-degrade path.

    Per AC-2 verbatim, ``collect`` does NOT re-raise on
    :exc:`OtelPipelineUnreachable` / :exc:`PromptIdCorrelationMissing`;
    cost-telemetry failure is graceful-degrade, the loop continues, the
    bundle's cost-breakdown section renders the marker prominently
    rather than fabricating zeros. Unknown exception types still
    propagate (via :func:`derive_cost_telemetry_unavailable_marker`'s
    re-raise) per the loud-fail doctrine.
    """
    cost_event_dict = record_cost_event(
        payload,
        return_envelope=return_envelope,
        return_timestamp=return_timestamp,
        cost_delta_usd=cost_delta_usd,
        otel_attributes=otel_attributes,
        event_id_factory=event_id_factory,
    )
    try:
        events = tuple(otel_pipeline.read_events(prompt_id=payload.prompt_id))
    except (OtelPipelineUnreachable, PromptIdCorrelationMissing) as exc:
        marker = derive_cost_telemetry_unavailable_marker(
            story_id=payload.story_id,
            prompt_id=payload.prompt_id,
            exc=exc,
        )
        return CollectionResult(
            cost_event=None,
            aggregation=CostAggregation(),
            marker_classification=marker,
        )
    aggregation = aggregate_costs(events)
    return CollectionResult(
        cost_event=cost_event_dict,
        aggregation=aggregation,
        marker_classification=None,
    )
