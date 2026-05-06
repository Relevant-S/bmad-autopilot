"""Story 6.5 — In-flight cost streaming + cost-near-ceiling 75% threshold tests.

Coverage map (per AC-6):

    (a) resolve_per_story_cost_ceiling_usd mirrors resolve_retry_budget shape
        for every input branch (None, empty mapping, missing key, valid
        int, valid float, None value, bool, negative, zero, string,
        float-coerced-to-int, dict, list).
    (b) evaluate_cost_threshold returns marker_classification=None on
        below-threshold; ("cost-near-ceiling", {}) on first 75% crossing;
        None on subsequent boundaries after 75% already emitted (no
        re-emission); ("cost-near-ceiling: ceiling-crossed", {}) on
        first 100% crossing; None on subsequent after ceiling-crossed
        already emitted; BOTH classifications when same boundary
        crosses both (the function returns the higher-severity
        classification AND the caller receives is_first_75pct_crossing=True).
    (c) format_cost_stream_line byte-stable / deterministic.
    (d) format_cost_stream_line percentage edge cases (0%, 1%, 99%, 100%, 150%).
    (e) format_cost_near_ceiling_warning_line byte-stable; covers both
        marker_class values; carries the literal "no auto-halt per NFR-O8".
    (f) stream_cost_at_boundary happy path (below-threshold) — appends one
        line; returns empty marker_classifications_to_append.
    (g) stream_cost_at_boundary first-75% crossing — appends two lines.
    (h) stream_cost_at_boundary first-100% crossing — appends two lines.
    (i) stream_cost_at_boundary BOTH 75% AND 100% crossed in one boundary.
    (j) stream_cost_at_boundary no-auto-halt invariant.
    (k) stream_cost_at_boundary already-emitted marker check.
    (l) stream_cost_at_boundary runaway-specialist gap behavior.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import pytest

from loud_fail_harness.cost_streaming import (
    DEFAULT_PER_STORY_COST_CEILING_USD,
    THRESHOLD_FRACTION_NEAR_CEILING,
    CostStreamingResult,
    CostThresholdDecision,
    evaluate_cost_threshold,
    format_cost_near_ceiling_warning_line,
    format_cost_stream_line,
    resolve_per_story_cost_ceiling_usd,
    stream_cost_at_boundary,
)
from loud_fail_harness.cost_telemetry import CostAggregation
from loud_fail_harness.exceptions import (
    ContractViolation,
    PerStoryCostCeilingConfigError,
)


# --------------------------------------------------------------------------- #
# Module surface smoke                                                         #
# --------------------------------------------------------------------------- #


def test_module_exports_constants_with_named_invariant_values() -> None:
    """Story 6.5 AC-2: NFR-P1 default $5 + NFR-O8 75% threshold pinned."""
    assert DEFAULT_PER_STORY_COST_CEILING_USD == 5.0
    assert THRESHOLD_FRACTION_NEAR_CEILING == 0.75


def test_per_story_cost_ceiling_config_error_inherits_value_error_and_contract_violation() -> None:
    """Story 6.5 AC-2: PerStoryCostCeilingConfigError dual lineage per Pattern 5
    + RetryBudgetConfigError ValueError-compat precedent."""
    assert issubclass(PerStoryCostCeilingConfigError, ValueError)
    assert issubclass(PerStoryCostCeilingConfigError, ContractViolation)


# --------------------------------------------------------------------------- #
# (a) resolve_per_story_cost_ceiling_usd — input contract matrix              #
# --------------------------------------------------------------------------- #


def test_resolve_returns_default_for_none_config() -> None:
    """Story 6.5 AC-2: config is None → default (pre-Story-7.5 case)."""
    assert resolve_per_story_cost_ceiling_usd(None) == 5.0


def test_resolve_returns_default_for_empty_dict_config() -> None:
    """Story 6.5 AC-2: empty dict → default."""
    assert resolve_per_story_cost_ceiling_usd({}) == 5.0


def test_resolve_returns_default_for_missing_field() -> None:
    """Story 6.5 AC-2: config without per_story_cost_ceiling_usd key → default."""
    assert resolve_per_story_cost_ceiling_usd({"other_field": 7}) == 5.0


def test_resolve_returns_default_for_none_value() -> None:
    """Story 6.5 AC-2: None-valued field → default (YAML empty-value case)."""
    assert resolve_per_story_cost_ceiling_usd({"per_story_cost_ceiling_usd": None}) == 5.0


@pytest.mark.parametrize("value", [1, 2, 5, 10, 100])
def test_resolve_returns_value_for_positive_int(value: int) -> None:
    """Story 6.5 AC-2: positive int → that value (coerced to float)."""
    assert resolve_per_story_cost_ceiling_usd(
        {"per_story_cost_ceiling_usd": value}
    ) == float(value)


@pytest.mark.parametrize("value", [0.5, 2.5, 5.0, 10.0, 99.99])
def test_resolve_returns_value_for_positive_float(value: float) -> None:
    """Story 6.5 AC-2: positive float → that value (per-story ceiling is fractional)."""
    assert resolve_per_story_cost_ceiling_usd(
        {"per_story_cost_ceiling_usd": value}
    ) == value


def test_resolve_default_keyword_override() -> None:
    """Story 6.5 AC-2: default keyword override permitted for test-side."""
    assert resolve_per_story_cost_ceiling_usd(None, default=12.5) == 12.5


def test_resolve_rejects_bool_true() -> None:
    """Story 6.5 AC-2: bool True → raise (Python bool ⊆ int ambiguity)."""
    with pytest.raises(PerStoryCostCeilingConfigError, match="positive number"):
        resolve_per_story_cost_ceiling_usd({"per_story_cost_ceiling_usd": True})


def test_resolve_rejects_bool_false() -> None:
    """Story 6.5 AC-2: bool False → raise (same bool ⊆ int rationale)."""
    with pytest.raises(PerStoryCostCeilingConfigError, match="positive number"):
        resolve_per_story_cost_ceiling_usd({"per_story_cost_ceiling_usd": False})


def test_resolve_rejects_zero() -> None:
    """Story 6.5 AC-2: zero → raise (strictly positive invariant)."""
    with pytest.raises(PerStoryCostCeilingConfigError, match="strictly positive"):
        resolve_per_story_cost_ceiling_usd({"per_story_cost_ceiling_usd": 0})


def test_resolve_rejects_negative_int() -> None:
    """Story 6.5 AC-2: negative int → raise."""
    with pytest.raises(PerStoryCostCeilingConfigError, match="strictly positive"):
        resolve_per_story_cost_ceiling_usd({"per_story_cost_ceiling_usd": -1})


def test_resolve_rejects_negative_float() -> None:
    """Story 6.5 AC-2: negative float → raise."""
    with pytest.raises(PerStoryCostCeilingConfigError, match="strictly positive"):
        resolve_per_story_cost_ceiling_usd({"per_story_cost_ceiling_usd": -2.5})


def test_resolve_rejects_string() -> None:
    """Story 6.5 AC-2: string-form numeric → raise (YAML number form required)."""
    with pytest.raises(PerStoryCostCeilingConfigError, match="YAML int or float"):
        resolve_per_story_cost_ceiling_usd({"per_story_cost_ceiling_usd": "5"})


@pytest.mark.parametrize(
    "junk_value",
    [
        [1, 2],  # list
        {"nested": "mapping"},  # dict
        object(),  # arbitrary object
    ],
)
def test_resolve_rejects_arbitrary_non_numeric(junk_value: Any) -> None:
    """Story 6.5 AC-2: arbitrary non-numeric → raise (loud-fail doctrine)."""
    with pytest.raises(PerStoryCostCeilingConfigError):
        resolve_per_story_cost_ceiling_usd(
            {"per_story_cost_ceiling_usd": junk_value}
        )


def test_resolve_diagnostic_carries_offending_value_and_field_name() -> None:
    """Story 6.5 AC-2: NFR-O5 named-invariant — diagnostic enumerates the
    offending value, the field name, and a remediation hint pointing at
    _bmad/automation/config.yaml."""
    with pytest.raises(PerStoryCostCeilingConfigError) as exc_info:
        resolve_per_story_cost_ceiling_usd({"per_story_cost_ceiling_usd": -3.0})
    assert exc_info.value.value == -3.0
    assert "per_story_cost_ceiling_usd" in exc_info.value.diagnostic
    assert "_bmad/automation/config.yaml" in exc_info.value.diagnostic


# --------------------------------------------------------------------------- #
# (b) evaluate_cost_threshold — threshold-detection matrix                     #
# --------------------------------------------------------------------------- #


def test_evaluate_below_threshold_returns_no_marker() -> None:
    """Story 6.5 AC-2: running total below 75% → marker_classification=None."""
    decision = evaluate_cost_threshold(
        running_total_usd=2.0,
        previous_running_total_usd=1.0,
        ceiling_usd=5.0,
        already_emitted_markers=(),
    )
    assert decision.marker_classification is None
    assert decision.is_first_75pct_crossing is False
    assert decision.is_first_100pct_crossing is False


def test_evaluate_first_75pct_crossing_returns_cost_near_ceiling() -> None:
    """Story 6.5 AC-2: first crossing of 75% → ('cost-near-ceiling', {})."""
    decision = evaluate_cost_threshold(
        running_total_usd=4.0,
        previous_running_total_usd=3.0,
        ceiling_usd=5.0,
        already_emitted_markers=(),
    )
    assert decision.marker_classification == ("cost-near-ceiling", {})
    assert decision.is_first_75pct_crossing is True
    assert decision.is_first_100pct_crossing is False


def test_evaluate_subsequent_boundary_after_75pct_does_not_re_emit() -> None:
    """Story 6.5 AC-2: 75% already emitted → no re-emission per Story 1.4
    marker-permanence rule."""
    decision = evaluate_cost_threshold(
        running_total_usd=4.5,
        previous_running_total_usd=4.0,
        ceiling_usd=5.0,
        already_emitted_markers=("cost-near-ceiling",),
    )
    assert decision.marker_classification is None


def test_evaluate_75pct_guard_prevents_re_emit_when_math_would_also_cross() -> None:
    """Story 6.5 review patch P4: verifies the already_emitted_markers guard is the
    mechanism preventing 75% re-emission when previous < threshold (guard is needed,
    not just math). Contrasts with
    test_evaluate_subsequent_boundary_after_75pct_does_not_re_emit where previous=4.0
    already exceeds threshold=3.75, so math alone prevents re-crossing. Here
    previous=3.5 < threshold=3.75, so crosses_75pct_now is True by arithmetic, and
    the guard (already_emitted_markers lookup) is what sets is_first_75pct to False.
    """
    decision = evaluate_cost_threshold(
        running_total_usd=5.5,
        previous_running_total_usd=3.5,
        ceiling_usd=5.0,
        already_emitted_markers=("cost-near-ceiling",),
    )
    # Math would cross 75%: previous (3.5) < threshold (3.75) AND running (5.5) >= (3.75)
    # The guard (already_emitted_markers) prevents is_first_75pct from being True.
    assert decision.is_first_75pct_crossing is False
    # 100% is crossed for the first time (ceiling-crossed not yet in emitted markers).
    assert decision.is_first_100pct_crossing is True
    assert decision.marker_classification == ("cost-near-ceiling: ceiling-crossed", {})


def test_evaluate_first_100pct_crossing_returns_ceiling_crossed() -> None:
    """Story 6.5 AC-3: first crossing of 100% → ('cost-near-ceiling:
    ceiling-crossed', {})."""
    decision = evaluate_cost_threshold(
        running_total_usd=5.5,
        previous_running_total_usd=4.0,
        ceiling_usd=5.0,
        already_emitted_markers=("cost-near-ceiling",),
    )
    assert decision.marker_classification == ("cost-near-ceiling: ceiling-crossed", {})
    assert decision.is_first_100pct_crossing is True


def test_evaluate_subsequent_boundary_after_ceiling_crossed_does_not_re_emit() -> None:
    """Story 6.5 AC-3: ceiling-crossed already emitted → no re-emission."""
    decision = evaluate_cost_threshold(
        running_total_usd=6.0,
        previous_running_total_usd=5.5,
        ceiling_usd=5.0,
        already_emitted_markers=(
            "cost-near-ceiling",
            "cost-near-ceiling: ceiling-crossed",
        ),
    )
    assert decision.marker_classification is None


def test_evaluate_same_boundary_75pct_and_100pct_jump_returns_higher_severity() -> None:
    """Story 6.5 AC-3: same-boundary 75%+100% jump (runaway-specialist
    gap-tolerance scenario) → higher-severity classification + the
    is_first_75pct_crossing flag set so the caller knows to append both."""
    decision = evaluate_cost_threshold(
        running_total_usd=6.0,
        previous_running_total_usd=0.0,
        ceiling_usd=5.0,
        already_emitted_markers=(),
    )
    assert decision.marker_classification == ("cost-near-ceiling: ceiling-crossed", {})
    assert decision.is_first_75pct_crossing is True
    assert decision.is_first_100pct_crossing is True


def test_evaluate_threshold_decision_is_frozen() -> None:
    """Story 6.5 AC-3: CostThresholdDecision is frozen for determinism."""
    decision = CostThresholdDecision(
        marker_classification=None,
        is_first_75pct_crossing=False,
        is_first_100pct_crossing=False,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.is_first_75pct_crossing = True  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# (c) format_cost_stream_line — byte-stable + deterministic                    #
# --------------------------------------------------------------------------- #


def _ts(hour: int = 12, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 5, 6, hour, minute, second, tzinfo=timezone.utc)


def test_format_cost_stream_line_canonical_shape() -> None:
    """Story 6.5 AC-1: format mirrors event_streaming's timestamp-bracketed
    convention; [cost] token; specialist; retry; delta; total; pct of ceiling."""
    line = format_cost_stream_line(
        timestamp=_ts(12, 30, 45),
        specialist="dev",
        retry_attempt=1,
        cost_delta_usd=1.25,
        running_total_usd=2.50,
        ceiling_usd=5.0,
    )
    assert line == (
        "12:30:45 [cost] specialist=dev retry=1 delta=$1.25 total=$2.50 (50% of $5.00)"
    )


def test_format_cost_stream_line_byte_stable_for_repeated_invocation() -> None:
    """Story 6.5 AC-6 (c): same input always yields byte-identical output."""
    args = {
        "timestamp": _ts(),
        "specialist": "review-bmad",
        "retry_attempt": 2,
        "cost_delta_usd": 0.42,
        "running_total_usd": 3.75,
        "ceiling_usd": 5.0,
    }
    first = format_cost_stream_line(**args)  # type: ignore[arg-type]
    second = format_cost_stream_line(**args)  # type: ignore[arg-type]
    assert first == second


# --------------------------------------------------------------------------- #
# (d) format_cost_stream_line — percentage edge cases                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("running_total", "ceiling", "expected_pct"),
    [
        (0.00, 5.00, "0%"),  # 0%
        (0.05, 5.00, "1%"),  # rounds-down to 1%
        (4.99, 5.00, "99%"),  # 99% just below ceiling
        (5.00, 5.00, "100%"),  # exact ceiling
        (7.50, 5.00, "150%"),  # over ceiling
    ],
)
def test_format_cost_stream_line_percentage_rendering(
    running_total: float, ceiling: float, expected_pct: str
) -> None:
    """Story 6.5 AC-1 + AC-6 (d): integer-percent rendering, rounded down,
    covers boundary edge cases."""
    line = format_cost_stream_line(
        timestamp=_ts(),
        specialist="dev",
        retry_attempt=1,
        cost_delta_usd=0.0,
        running_total_usd=running_total,
        ceiling_usd=ceiling,
    )
    assert f"({expected_pct} of " in line


# --------------------------------------------------------------------------- #
# (e) format_cost_near_ceiling_warning_line — both classifications             #
# --------------------------------------------------------------------------- #


def test_format_warning_line_75pct_classification_carries_no_auto_halt_substring() -> None:
    """Story 6.5 AC-2 + AC-3: 75% warning line carries 'no auto-halt per NFR-O8'
    literal substring per the documented streaming-output convention."""
    line = format_cost_near_ceiling_warning_line(
        timestamp=_ts(12, 30, 45),
        marker_class="cost-near-ceiling",
        running_total_usd=3.80,
        ceiling_usd=5.0,
    )
    assert "no auto-halt per NFR-O8" in line
    assert "[⚠️ cost-near-ceiling]" in line
    assert "$3.80" in line
    assert "$5.00" in line


def test_format_warning_line_ceiling_crossed_classification() -> None:
    """Story 6.5 AC-3: ceiling-crossed warning carries the sub-classified marker class."""
    line = format_cost_near_ceiling_warning_line(
        timestamp=_ts(12, 30, 45),
        marker_class="cost-near-ceiling: ceiling-crossed",
        running_total_usd=5.50,
        ceiling_usd=5.0,
    )
    assert "[⚠️ cost-near-ceiling: ceiling-crossed]" in line
    assert "no auto-halt per NFR-O8" in line


def test_format_warning_line_byte_stable_for_repeated_invocation() -> None:
    """Story 6.5 AC-6 (e): byte-stable output for same input."""
    args: Mapping[str, Any] = {
        "timestamp": _ts(),
        "marker_class": "cost-near-ceiling",
        "running_total_usd": 3.75,
        "ceiling_usd": 5.0,
    }
    first = format_cost_near_ceiling_warning_line(**args)
    second = format_cost_near_ceiling_warning_line(**args)
    assert first == second


# --------------------------------------------------------------------------- #
# (f-l) stream_cost_at_boundary — composition matrix                           #
# --------------------------------------------------------------------------- #


def _make_aggregation(**totals: float) -> CostAggregation:
    return CostAggregation(
        per_specialist_totals=dict(totals),
        per_specialist_per_retry={(k, 1): v for k, v in totals.items()},
    )


def test_stream_at_boundary_below_threshold_appends_one_line() -> None:
    """Story 6.5 AC-1 + AC-6 (f): below-threshold happy path —
    cost-stream line only; empty marker_classifications_to_append."""
    appended: list[str] = []
    result = stream_cost_at_boundary(
        aggregation=_make_aggregation(dev=2.0),
        specialist="dev",
        retry_attempt=1,
        cost_delta_usd=2.0,
        ceiling_usd=5.0,
        previous_running_total_usd=0.0,
        already_emitted_markers=(),
        boundary_timestamp=_ts(),
        line_appender=appended.append,
    )
    assert len(appended) == 1
    assert "[cost]" in appended[0]
    assert result.marker_classifications_to_append == ()
    assert result.running_total_usd == 2.0


def test_stream_at_boundary_first_75pct_crossing_appends_two_lines() -> None:
    """Story 6.5 AC-2 + AC-6 (g): first 75%-crossing — appends cost-stream
    line + warning line; returns ('cost-near-ceiling', {}) tuple."""
    appended: list[str] = []
    result = stream_cost_at_boundary(
        aggregation=_make_aggregation(dev=2.0, review_bmad=2.0),
        specialist="review-bmad",
        retry_attempt=1,
        cost_delta_usd=2.0,
        ceiling_usd=5.0,
        previous_running_total_usd=2.0,
        already_emitted_markers=(),
        boundary_timestamp=_ts(),
        line_appender=appended.append,
    )
    assert len(appended) == 2
    assert "[cost]" in appended[0]
    assert "[⚠️ cost-near-ceiling]" in appended[1]
    assert result.marker_classifications_to_append == (("cost-near-ceiling", {}),)


def test_stream_at_boundary_first_100pct_crossing_appends_two_lines() -> None:
    """Story 6.5 AC-3 + AC-6 (h): first 100%-crossing — appends cost-stream
    line + ceiling-crossed warning; returns
    ('cost-near-ceiling: ceiling-crossed', {}) tuple."""
    appended: list[str] = []
    result = stream_cost_at_boundary(
        aggregation=_make_aggregation(dev=3.0, review_bmad=2.5),
        specialist="review-bmad",
        retry_attempt=1,
        cost_delta_usd=2.5,
        ceiling_usd=5.0,
        previous_running_total_usd=4.0,
        already_emitted_markers=("cost-near-ceiling",),
        boundary_timestamp=_ts(),
        line_appender=appended.append,
    )
    assert len(appended) == 2
    assert "[cost]" in appended[0]
    assert "[⚠️ cost-near-ceiling: ceiling-crossed]" in appended[1]
    assert result.marker_classifications_to_append == (
        ("cost-near-ceiling: ceiling-crossed", {}),
    )


def test_stream_at_boundary_same_boundary_75pct_and_100pct_jump_appends_three_lines() -> None:
    """Story 6.5 AC-3 + AC-6 (i): same-boundary 75%+100% jump
    (runaway-specialist gap-tolerance) — appends cost-stream + 75% warning +
    ceiling-crossed warning; returns BOTH classifications in ascending order."""
    appended: list[str] = []
    result = stream_cost_at_boundary(
        aggregation=_make_aggregation(dev=6.0),
        specialist="dev",
        retry_attempt=1,
        cost_delta_usd=6.0,
        ceiling_usd=5.0,
        previous_running_total_usd=0.0,
        already_emitted_markers=(),
        boundary_timestamp=_ts(),
        line_appender=appended.append,
    )
    assert len(appended) == 3
    assert "[cost]" in appended[0]
    assert "[⚠️ cost-near-ceiling]" in appended[1]
    assert "[⚠️ cost-near-ceiling: ceiling-crossed]" in appended[2]
    assert result.marker_classifications_to_append == (
        ("cost-near-ceiling", {}),
        ("cost-near-ceiling: ceiling-crossed", {}),
    )


def test_stream_at_boundary_no_auto_halt_invariant() -> None:
    """Story 6.5 AC-3 + AC-6 (j): the function NEVER raises on a ceiling
    crossing per NFR-O8 verbatim — the loop continues."""
    appended: list[str] = []
    # Crosses ceiling — function returns normally; no RuntimeError; no SystemExit.
    result = stream_cost_at_boundary(
        aggregation=_make_aggregation(dev=10.0),
        specialist="dev",
        retry_attempt=1,
        cost_delta_usd=10.0,
        ceiling_usd=5.0,
        previous_running_total_usd=0.0,
        already_emitted_markers=(),
        boundary_timestamp=_ts(),
        line_appender=appended.append,
    )
    assert any("no auto-halt per NFR-O8" in line for line in appended)
    assert result.threshold_decision.is_first_100pct_crossing is True


def test_stream_at_boundary_already_emitted_marker_check_skips_re_append() -> None:
    """Story 6.5 AC-2 + AC-6 (k): subsequent boundary after marker already
    emitted does NOT re-append the marker classification."""
    appended: list[str] = []
    result = stream_cost_at_boundary(
        aggregation=_make_aggregation(dev=4.5),
        specialist="dev",
        retry_attempt=2,
        cost_delta_usd=0.5,
        ceiling_usd=5.0,
        previous_running_total_usd=4.0,
        already_emitted_markers=("cost-near-ceiling",),
        boundary_timestamp=_ts(),
        line_appender=appended.append,
    )
    assert len(appended) == 1  # cost-stream line only; no warning
    assert result.marker_classifications_to_append == ()


def test_stream_at_boundary_runaway_specialist_gap_behavior() -> None:
    """Story 6.5 AC-6 (l): when previous_running_total_usd is well below
    threshold AND aggregation summed produces a running_total well above
    ceiling (single-boundary jump), the function appends both warnings AND
    the cost-stream line shows the actual running total (not a fabricated
    intermediate value)."""
    appended: list[str] = []
    result = stream_cost_at_boundary(
        aggregation=_make_aggregation(dev=8.5),  # runaway specialist
        specialist="dev",
        retry_attempt=1,
        cost_delta_usd=8.5,
        ceiling_usd=5.0,
        previous_running_total_usd=0.0,
        already_emitted_markers=(),
        boundary_timestamp=_ts(),
        line_appender=appended.append,
    )
    assert "$8.50" in appended[0]  # actual running total — not fabricated
    assert "170% of $5.00" in appended[0]
    assert len(result.marker_classifications_to_append) == 2


def test_cost_streaming_result_is_frozen() -> None:
    """Story 6.5 AC-1: CostStreamingResult is frozen for determinism."""
    result = CostStreamingResult(
        running_total_usd=0.0,
        marker_classifications_to_append=(),
        threshold_decision=CostThresholdDecision(
            marker_classification=None,
            is_first_75pct_crossing=False,
            is_first_100pct_crossing=False,
        ),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.running_total_usd = 99.0  # type: ignore[misc]
