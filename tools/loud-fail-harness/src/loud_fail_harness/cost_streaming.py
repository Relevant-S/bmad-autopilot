"""Story 6.5 — In-flight cost streaming + cost-near-ceiling 75% threshold.

Substrate library sibling of :mod:`loud_fail_harness.cost_telemetry` /
:mod:`loud_fail_harness.event_streaming` / :mod:`loud_fail_harness.run_state`
per architecture.md lines 311-315. NOT a sixth substrate component beyond
ADR-003 Consequence 1's enumerated five (envelope_validator, event_validator,
reconciler, enumeration_check, fixture_coverage); the count remains FIVE.

Architectural anchors:

* **NFR-O1** (PRD line 980) — "main-session output streams per-seam
  transitions, specialist dispatch and return events, and loud-fail
  markers live"; this module produces the per-boundary cost-stream line.
* **NFR-O8** (PRD line 987) — "running per-story cost is visible in the
  streaming terminal output at each specialist completion"; "When running
  cost crosses 75% of the per-story ceiling ... a ``cost-near-ceiling``
  warning emits in the stream and is recorded in run-state"; "Crossing
  the ceiling does not auto-halt the loop; the practitioner decides
  whether to abort".
* **NFR-P1** (PRD line 932) — Per-story cost ceiling default ``$5``,
  configurable via ``_bmad/automation/config.yaml``'s
  ``per_story_cost_ceiling_usd`` field.
* **Pattern 2** (architecture.md line 962) — Sub-classification via
  ``: <cause>`` suffix; this module emits ``cost-near-ceiling`` and
  ``cost-near-ceiling: ceiling-crossed`` per the marker-taxonomy.yaml
  ``cost-near-ceiling`` entry's post-Story-6.5 ``sub_classifications:
  [ceiling-crossed]``.
* **Pattern 4** (architecture.md lines 977-981) — Cost-counter writes
  batch with other run-state writes between specialist completions;
  this module does NOT introduce a parallel atomic-write helper —
  :func:`stream_cost_at_boundary` returns
  :class:`CostStreamingResult.marker_classifications_to_append` which
  the orchestrator caller composes INTO the next-state argument it
  passes to :func:`loud_fail_harness.run_state.advance_run_state`.
* **Pattern 5** (architecture.md) — Loud-fail / named invariants: a
  malformed ``per_story_cost_ceiling_usd`` config value raises
  :exc:`PerStoryCostCeilingConfigError` per NFR-O5.

Boundary-cadence MVP semantics:

    "in-flight" is explicitly framed as **at specialist-return
    boundaries during a multi-specialist run**, NOT during specialist
    execution. The gap between specialist-return boundaries is bounded
    by NFR-P2's per-specialist timeout (15-min default per Story 2.6 /
    ``specialist_dispatch.py:1382-1383``). A runaway specialist
    exceeding the ceiling between events surfaces the warning at the
    next return boundary (gap-tolerance is the MVP tradeoff). Phase 2
    in-flight intra-specialist sampling is a forward-looking FR-P2
    candidate revisited when Claude Code's cost-event cadence
    stabilizes; cross-references the parallel rationale 6.4 documented
    for cost-telemetry collection.

Public API:

    * :data:`DEFAULT_PER_STORY_COST_CEILING_USD` — NFR-P1 default $5.
    * :data:`THRESHOLD_FRACTION_NEAR_CEILING` — NFR-O8 verbatim 0.75.
    * :func:`resolve_per_story_cost_ceiling_usd` — config resolver
      mirroring :func:`loud_fail_harness.retry_budget.resolve_retry_budget`.
    * :class:`CostThresholdDecision` — frozen dataclass; the
      threshold-evaluation result.
    * :class:`CostStreamingResult` — frozen dataclass; the per-boundary
      streaming + marker-emission result.
    * :func:`evaluate_cost_threshold` — pure threshold-detection.
    * :func:`format_cost_stream_line` — pure renderer for the cost-line.
    * :func:`format_cost_near_ceiling_warning_line` — pure renderer for
      the warning-line; text contains ``"no auto-halt per NFR-O8"``.
    * :func:`stream_cost_at_boundary` — orchestrator-side composition
      entry point.

Cross-references:

    * Story 1.4 ``schemas/marker-taxonomy.yaml`` lines 201-208 —
      ``cost-near-ceiling`` v1 entry; ``pointer_context_fields: []``;
      Story 6.5 extends ``sub_classifications`` from ``[]`` to
      ``[ceiling-crossed]``.
    * Story 6.1 :func:`loud_fail_harness.bundle_assembly._render_loud_fail_block`
      — consumed AS-IS for the ``cost-near-ceiling`` marker surface.
    * Story 6.2 ``pointer_context_fields: []`` empty-context shape;
      diagnostic_pointer text renders verbatim, no template
      interpolation needed.
    * Story 6.4 :class:`loud_fail_harness.cost_telemetry.CostAggregation`
      ``per_specialist_totals`` — Story 6.5 READS this surface to
      compute the running total; ZERO modifications to
      ``cost_telemetry.py``.
    * Story 5.1 :func:`loud_fail_harness.retry_budget.resolve_retry_budget`
      — byte-stable input contract this module's
      :func:`resolve_per_story_cost_ceiling_usd` mirrors.
    * Story 2.6 ``specialist_dispatch.py:1382-1383`` — the 15-min
      per-specialist timeout default this module's gap-tolerance
      bounds against.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from loud_fail_harness.cost_telemetry import CostAggregation
from loud_fail_harness.exceptions import PerStoryCostCeilingConfigError


__all__ = [
    "CostStreamingResult",
    "CostThresholdDecision",
    "DEFAULT_PER_STORY_COST_CEILING_USD",
    "THRESHOLD_FRACTION_NEAR_CEILING",
    "evaluate_cost_threshold",
    "format_cost_near_ceiling_warning_line",
    "format_cost_stream_line",
    "resolve_per_story_cost_ceiling_usd",
    "stream_cost_at_boundary",
]


#: Default per-story cost ceiling per NFR-P1 ($5.00 USD).
DEFAULT_PER_STORY_COST_CEILING_USD: float = 5.0

#: 75% near-ceiling fraction per NFR-O8 verbatim.
THRESHOLD_FRACTION_NEAR_CEILING: float = 0.75

#: Canonical config-file field name. Snake_case per Pattern 1.
_PER_STORY_COST_CEILING_FIELD: str = "per_story_cost_ceiling_usd"

#: Marker class for the 75% near-ceiling warning (v1 taxonomy entry
#: at ``schemas/marker-taxonomy.yaml`` lines 201-208).
_MARKER_CLASS_NEAR_CEILING: str = "cost-near-ceiling"

#: Marker class with the ``ceiling-crossed`` sub-classification suffix
#: per Pattern 2's ``: <cause>`` format. Post-Story-6.5
#: ``sub_classifications: [ceiling-crossed]``.
_MARKER_CLASS_CEILING_CROSSED: str = "cost-near-ceiling: ceiling-crossed"


def resolve_per_story_cost_ceiling_usd(
    config: Mapping[str, Any] | None = None,
    *,
    default: float = DEFAULT_PER_STORY_COST_CEILING_USD,
) -> float:
    """Resolve the ``per_story_cost_ceiling_usd`` value from a config mapping.

    Pure function (no I/O). Mirrors
    :func:`loud_fail_harness.retry_budget.resolve_retry_budget`'s
    byte-stable input contract; the per-input shape semantics are:

    * ``config is None`` → return ``default`` (covers the pre-Story-7.5
      "config.yaml not yet scaffolded" case).
    * ``config={}`` → return ``default`` (config exists but the
      ``per_story_cost_ceiling_usd`` key is omitted).
    * ``config={"per_story_cost_ceiling_usd": <positive int|float>}`` →
      return that value (coerced to ``float``).
    * ``config={"per_story_cost_ceiling_usd": None}`` → return
      ``default`` (the YAML loader parses
      ``per_story_cost_ceiling_usd:`` with no value as :data:`None`;
      treat as field-absent).
    * Any other value (``bool``, negative, zero, non-numeric) → raise
      :exc:`PerStoryCostCeilingConfigError` with an NFR-O5
      named-invariant diagnostic naming the offending value, the field
      name, and a remediation hint pointing at
      ``_bmad/automation/config.yaml``.

    Witnesses AC-2 verbatim — "ceiling configurable via
    ``_bmad/automation/config.yaml``'s ``per_story_cost_ceiling_usd``
    field".
    """
    if config is None:
        return float(default)

    if _PER_STORY_COST_CEILING_FIELD not in config:
        return float(default)

    value = config[_PER_STORY_COST_CEILING_FIELD]

    if value is None:
        return float(default)

    # bool is a subclass of int in Python; explicit reject before the
    # numeric-type check so True/False don't slip through as 1.0/0.0.
    # Loud-fail posture per Pattern 5: an operator typo
    # (``per_story_cost_ceiling_usd: yes`` parses to True) must surface,
    # not silently coerce.
    if isinstance(value, bool):
        raise PerStoryCostCeilingConfigError(
            value=value,
            diagnostic=(
                f"{_PER_STORY_COST_CEILING_FIELD} must be a positive number; "
                f"got {value!r} ({type(value).__name__}) — booleans are "
                f"rejected to avoid YAML truthy-coercion ambiguity — write "
                f"the value as an unquoted positive number in "
                f"_bmad/automation/config.yaml (e.g., "
                f"'per_story_cost_ceiling_usd: 5')"
            ),
        )

    # Reject everything that is not strictly int or float. Strings
    # (``"5"``), arbitrary types (``dict``, ``list``) are config-shape
    # violations per the YAML number-form contract.
    if type(value) is not int and type(value) is not float:
        raise PerStoryCostCeilingConfigError(
            value=value,
            diagnostic=(
                f"{_PER_STORY_COST_CEILING_FIELD} must be a YAML int or float; "
                f"got {value!r} ({type(value).__name__}) — write the value "
                f"as an unquoted positive number in "
                f"_bmad/automation/config.yaml (e.g., "
                f"'per_story_cost_ceiling_usd: 5', not "
                f"'per_story_cost_ceiling_usd: \"5\"')"
            ),
        )

    if value <= 0:
        raise PerStoryCostCeilingConfigError(
            value=value,
            diagnostic=(
                f"{_PER_STORY_COST_CEILING_FIELD} must be strictly positive; "
                f"got {value!r} ({type(value).__name__}) — set "
                f"per_story_cost_ceiling_usd to a positive number "
                f"(e.g., 'per_story_cost_ceiling_usd: 5') in "
                f"_bmad/automation/config.yaml"
            ),
        )

    return float(value)


@dataclasses.dataclass(frozen=True)
class CostThresholdDecision:
    """Pure threshold-evaluation result returned by :func:`evaluate_cost_threshold`.

    Field semantics:

        * ``marker_classification`` — ``None`` on no-crossing;
          ``("cost-near-ceiling", {})`` on first 75%-crossing;
          ``("cost-near-ceiling: ceiling-crossed", {})`` on first
          100%-crossing (or same-boundary 75%+100% jump — in that case
          the higher-severity classification is returned and the
          ``is_first_75pct_crossing`` flag is set so the caller knows
          to also append the 75% marker).
        * ``is_first_75pct_crossing`` — ``True`` iff this boundary
          first crosses 75% of ceiling AND the 75% marker has not
          previously been emitted.
        * ``is_first_100pct_crossing`` — ``True`` iff this boundary
          first crosses 100% of ceiling AND the ceiling-crossed marker
          has not previously been emitted.

    Frozen + idempotent + byte-stable per Story 6.1's regression-fixture
    discipline.
    """

    marker_classification: tuple[str, Mapping[str, str]] | None
    is_first_75pct_crossing: bool
    is_first_100pct_crossing: bool


@dataclasses.dataclass(frozen=True)
class CostStreamingResult:
    """Per-boundary streaming + marker-emission result returned by
    :func:`stream_cost_at_boundary`.

    Field semantics:

        * ``running_total_usd`` — sum of
          ``aggregation.per_specialist_totals.values()`` at this
          boundary (the running total reported on the cost-stream
          line).
        * ``marker_classifications_to_append`` — the ordered tuple the
          orchestrator appends to ``run_state.active_markers`` +
          ``run_state.marker_contexts`` per Story 6.2's contract;
          possibly empty (no crossings; or already-emitted skip; or
          graceful-degrade skip).
        * ``threshold_decision`` — the
          :class:`CostThresholdDecision` produced by
          :func:`evaluate_cost_threshold` for this boundary.
    """

    running_total_usd: float
    marker_classifications_to_append: tuple[tuple[str, Mapping[str, str]], ...]
    threshold_decision: CostThresholdDecision


def evaluate_cost_threshold(
    *,
    running_total_usd: float,
    previous_running_total_usd: float,
    ceiling_usd: float,
    already_emitted_markers: tuple[str, ...],
) -> CostThresholdDecision:
    """Detect whether this boundary crosses the 75% / 100% thresholds.

    Pure function (no I/O). Idempotent + byte-stable: same input always
    yields the same decision.

    A "first crossing this boundary" is detected by comparing
    ``previous_running_total_usd < threshold AND
    running_total_usd >= threshold``. The
    ``already_emitted_markers`` tuple is consulted to avoid re-emitting
    on subsequent boundaries (75% emits once per run; ceiling-crossed
    emits once per run per Story 1.4's marker-permanence rule).

    Same-boundary 75%+100% jump (the runaway-specialist gap-tolerance
    scenario, e.g. ``previous_running_total_usd=$0.00`` and
    ``running_total_usd=$6.00`` with ``ceiling_usd=$5.00``): the
    function returns ``marker_classification=("cost-near-ceiling:
    ceiling-crossed", {})`` (the higher-severity classification) AND
    ``is_first_75pct_crossing=True`` so the caller can append BOTH
    markers in order per AC-3 verbatim.

    Witnesses AC-2 (75% crossing emission) + AC-3 (100% crossing
    sub-classification + same-boundary-jump) verbatim.
    """
    threshold_75pct = THRESHOLD_FRACTION_NEAR_CEILING * ceiling_usd

    crosses_75pct_now = (
        previous_running_total_usd < threshold_75pct
        and running_total_usd >= threshold_75pct
    )
    crosses_100pct_now = (
        previous_running_total_usd < ceiling_usd
        and running_total_usd >= ceiling_usd
    )

    is_first_75pct = (
        crosses_75pct_now
        and _MARKER_CLASS_NEAR_CEILING not in already_emitted_markers
    )
    is_first_100pct = (
        crosses_100pct_now
        and _MARKER_CLASS_CEILING_CROSSED not in already_emitted_markers
    )

    if is_first_100pct:
        # Same-boundary 75%+100% jump: prefer higher-severity
        # classification; caller reads is_first_75pct_crossing to know
        # whether to append the 75% marker too.
        return CostThresholdDecision(
            marker_classification=(_MARKER_CLASS_CEILING_CROSSED, {}),
            is_first_75pct_crossing=is_first_75pct,
            is_first_100pct_crossing=True,
        )

    if is_first_75pct:
        return CostThresholdDecision(
            marker_classification=(_MARKER_CLASS_NEAR_CEILING, {}),
            is_first_75pct_crossing=True,
            is_first_100pct_crossing=False,
        )

    return CostThresholdDecision(
        marker_classification=None,
        is_first_75pct_crossing=False,
        is_first_100pct_crossing=False,
    )


def format_cost_stream_line(
    *,
    timestamp: datetime,
    specialist: str,
    retry_attempt: int,
    cost_delta_usd: float,
    running_total_usd: float,
    ceiling_usd: float,
) -> str:
    """Render the per-boundary cost-stream line.

    Pure function (no I/O). Deterministic given the same input.

    Format per AC-1 verbatim::

        <HH:MM:SS> [cost] specialist=<kebab> retry=<n> delta=$<x.xx> total=$<y.yy> (<pct>% of $<ceiling.2f>)

    Mirrors :func:`loud_fail_harness.event_streaming.format_event_for_stream`'s
    ``<HH:MM:SS> [<event_class>] <brief_detail>`` convention from
    ``event_streaming.py:215-243``. The bracketed ``[cost]`` token is a
    non-event-class diagnostic identifier (the cost-line is NOT an
    orchestrator-event; it is a derived per-boundary observability
    render so the ``[cost]`` token stays distinct from the
    schema-validated ``event_class`` enum).

    Witnesses AC-1 verbatim — "format includes specialist name, retry
    attempt, cost delta for this invocation, running total, and
    percentage of NFR-P1 per-story ceiling consumed".
    """
    hhmmss = timestamp.strftime("%H:%M:%S")
    pct = int((running_total_usd / ceiling_usd) * 100)
    return (
        f"{hhmmss} [cost] specialist={specialist} retry={retry_attempt} "
        f"delta=${cost_delta_usd:.2f} total=${running_total_usd:.2f} "
        f"({pct}% of ${ceiling_usd:.2f})"
    )


def format_cost_near_ceiling_warning_line(
    *,
    timestamp: datetime,
    marker_class: str,
    running_total_usd: float,
    ceiling_usd: float,
) -> str:
    """Render the prominent-warning line that follows the cost-stream
    line on a threshold-crossing boundary.

    Pure function (no I/O). The format is::

        <HH:MM:SS> [⚠️ <marker_class>] running cost $<total.2f> crossed <pct>% of $<ceiling.2f> ceiling — practitioner decides whether to abort (no auto-halt per NFR-O8)

    The ``⚠️`` emoji prefix mirrors Story 6.1's
    ``## ⚠️ Loud-Fail Markers`` block convention. Visible-color framing
    is a render-time concern of the orchestrator's terminal-output
    adapter (the substrate produces the line text; ANSI-color wrapping
    is a downstream concern out of substrate scope per the
    sensor-not-advisor posture).

    The literal substring ``"no auto-halt per NFR-O8"`` is REQUIRED in
    the rendered text per AC-3 verbatim — it ensures the no-auto-halt
    invariant is identifiable in non-color terminal contexts and via
    grep-based regression checks.

    Witnesses AC-2 (75% warning, separate line) + AC-3 (100%
    ceiling-crossed warning, no-auto-halt substring) verbatim.
    """
    hhmmss = timestamp.strftime("%H:%M:%S")
    pct = int((running_total_usd / ceiling_usd) * 100)
    return (
        f"{hhmmss} [⚠️ {marker_class}] running cost ${running_total_usd:.2f} "
        f"crossed {pct}% of ${ceiling_usd:.2f} ceiling — practitioner "
        f"decides whether to abort (no auto-halt per NFR-O8)"
    )


def stream_cost_at_boundary(
    *,
    aggregation: CostAggregation,
    specialist: str,
    retry_attempt: int,
    cost_delta_usd: float,
    ceiling_usd: float,
    previous_running_total_usd: float,
    already_emitted_markers: tuple[str, ...],
    boundary_timestamp: datetime,
    line_appender: Callable[[str], None],
) -> CostStreamingResult:
    """Canonical orchestrator-side composition entry point.

    Composition flow:

        1. Compute ``running_total_usd`` as
           ``sum(aggregation.per_specialist_totals.values())``.
        2. Format the cost-stream line via
           :func:`format_cost_stream_line` and append via
           ``line_appender``.
        3. Detect threshold crossings via
           :func:`evaluate_cost_threshold`.
        4. On 75% first-crossing: format + append the warning line.
        5. On 100% first-crossing: format + append the warning line
           (same-boundary 75%+100% jump appends both warnings in
           ascending-severity order — 75% first, then ceiling-crossed).
        6. Return :class:`CostStreamingResult` carrying the running
           total, the ordered ``marker_classifications_to_append``
           tuple the orchestrator appends to ``run_state.active_markers``
           via the existing ``advance_run_state`` seam-transition write
           (Pattern 4 batch-write rule), and the threshold decision.

    The ``line_appender`` Callable is the I/O boundary the caller
    injects per the sensor-not-advisor / caller-injected-factory
    convention from Story 2.6. The function NEVER raises on a ceiling
    crossing — the loop continues per NFR-O8 verbatim ("the
    practitioner decides whether to abort"; "Crossing the ceiling does
    not auto-halt the loop").

    Witnesses AC-1 + AC-2 + AC-3 verbatim.
    """
    running_total_usd = sum(aggregation.per_specialist_totals.values())

    cost_line = format_cost_stream_line(
        timestamp=boundary_timestamp,
        specialist=specialist,
        retry_attempt=retry_attempt,
        cost_delta_usd=cost_delta_usd,
        running_total_usd=running_total_usd,
        ceiling_usd=ceiling_usd,
    )
    line_appender(cost_line)

    decision = evaluate_cost_threshold(
        running_total_usd=running_total_usd,
        previous_running_total_usd=previous_running_total_usd,
        ceiling_usd=ceiling_usd,
        already_emitted_markers=already_emitted_markers,
    )

    markers_to_append: list[tuple[str, Mapping[str, str]]] = []

    # Same-boundary 75%+100% jump: append the 75% warning first
    # (ascending-severity order) then the ceiling-crossed warning.
    if decision.is_first_75pct_crossing and decision.is_first_100pct_crossing:
        warning_75pct = format_cost_near_ceiling_warning_line(
            timestamp=boundary_timestamp,
            marker_class=_MARKER_CLASS_NEAR_CEILING,
            running_total_usd=running_total_usd,
            ceiling_usd=ceiling_usd,
        )
        line_appender(warning_75pct)
        markers_to_append.append((_MARKER_CLASS_NEAR_CEILING, {}))

        warning_ceiling = format_cost_near_ceiling_warning_line(
            timestamp=boundary_timestamp,
            marker_class=_MARKER_CLASS_CEILING_CROSSED,
            running_total_usd=running_total_usd,
            ceiling_usd=ceiling_usd,
        )
        line_appender(warning_ceiling)
        markers_to_append.append((_MARKER_CLASS_CEILING_CROSSED, {}))
    elif decision.is_first_100pct_crossing:
        warning_ceiling = format_cost_near_ceiling_warning_line(
            timestamp=boundary_timestamp,
            marker_class=_MARKER_CLASS_CEILING_CROSSED,
            running_total_usd=running_total_usd,
            ceiling_usd=ceiling_usd,
        )
        line_appender(warning_ceiling)
        markers_to_append.append((_MARKER_CLASS_CEILING_CROSSED, {}))
    elif decision.is_first_75pct_crossing:
        warning_75pct = format_cost_near_ceiling_warning_line(
            timestamp=boundary_timestamp,
            marker_class=_MARKER_CLASS_NEAR_CEILING,
            running_total_usd=running_total_usd,
            ceiling_usd=ceiling_usd,
        )
        line_appender(warning_75pct)
        markers_to_append.append((_MARKER_CLASS_NEAR_CEILING, {}))

    return CostStreamingResult(
        running_total_usd=running_total_usd,
        marker_classifications_to_append=tuple(markers_to_append),
        threshold_decision=decision,
    )
