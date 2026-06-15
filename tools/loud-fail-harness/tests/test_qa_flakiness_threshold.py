"""Story 20.3 — flakiness threshold + ``flakiness-threshold-exceeded`` marker."""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.bundle_assembly import _render_per_ac_section
from loud_fail_harness.envelope_validator import validate_envelope
from loud_fail_harness.qa_flakiness_log import FlakinessAcHistory, FlakinessRunRecord
from loud_fail_harness.qa_flakiness_threshold import (
    DEFAULT_THRESHOLD_CONSECUTIVE_RUNS,
    DEFAULT_THRESHOLD_TRANSIENT_FAIL_COUNT,
    FLAKINESS_THRESHOLD_EXCEEDED_MARKER,
    FlakinessThresholdConfig,
    FlakinessThresholdDecision,
    FlakinessThresholdDiagnosticContext,
    FlakinessThresholdEmissionRecord,
    evaluate_ac_flakiness,
    load_flakiness_threshold_config,
    surface_flakiness_threshold_exceeded,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
    load_marker_class_registry,
)

_STORY_ID = "20-3-test"


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


def _canonical_registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(
        marker_classes=frozenset({FLAKINESS_THRESHOLD_EXCEEDED_MARKER})
    )


def _record(retry: int, *, status: str = "pass", n: int = 0) -> FlakinessRunRecord:
    return FlakinessRunRecord(
        run_id=f"run-{n}-{retry}-{status}",
        timestamp="2026-06-15T12:00:00Z",
        status=status,  # type: ignore[arg-type]
        retry_count_within_run=retry,
        evidence_ref=f"_bmad-output/qa-evidence/{_STORY_ID}/run-{n}/AC-1",
    )


def _history(retries: tuple[int, ...], *, ac_id: str = "AC-1") -> FlakinessAcHistory:
    return FlakinessAcHistory(
        ac_id=ac_id,
        runs=tuple(_record(r, n=i) for i, r in enumerate(retries)),
    )


# --------------------------------------------------------------------------- #
# Config + load_flakiness_threshold_config (AC-1)                              #
# --------------------------------------------------------------------------- #


def test_config_defaults_match_prd() -> None:
    cfg = FlakinessThresholdConfig()
    assert cfg.threshold_consecutive_runs == DEFAULT_THRESHOLD_CONSECUTIVE_RUNS == 3
    assert cfg.threshold_transient_fail_count == DEFAULT_THRESHOLD_TRANSIENT_FAIL_COUNT == 1


def test_load_config_none_runbook_is_defaults() -> None:
    assert load_flakiness_threshold_config(None) == FlakinessThresholdConfig()


def test_load_config_absent_block_is_defaults() -> None:
    # AC-1: absence is NOT a marker — it means "defaults apply".
    assert load_flakiness_threshold_config({"masked_selectors": []}) == (
        FlakinessThresholdConfig()
    )


def test_load_config_present_block_tunes_knobs() -> None:
    cfg = load_flakiness_threshold_config(
        {"flakiness": {"threshold_consecutive_runs": 5, "threshold_transient_fail_count": 2}}
    )
    assert cfg.threshold_consecutive_runs == 5
    assert cfg.threshold_transient_fail_count == 2


def test_load_config_partial_block_defaults_the_rest() -> None:
    cfg = load_flakiness_threshold_config({"flakiness": {"threshold_consecutive_runs": 4}})
    assert cfg.threshold_consecutive_runs == 4
    assert cfg.threshold_transient_fail_count == DEFAULT_THRESHOLD_TRANSIENT_FAIL_COUNT


def test_load_config_non_mapping_block_loud_fails() -> None:
    with pytest.raises(ValueError, match="must be a mapping"):
        load_flakiness_threshold_config({"flakiness": [1, 2]})


@pytest.mark.parametrize("knob", ["threshold_consecutive_runs", "threshold_transient_fail_count"])
def test_load_config_below_floor_raises(knob: str) -> None:
    with pytest.raises(ValidationError):
        load_flakiness_threshold_config({"flakiness": {knob: 0}})


def test_config_is_frozen() -> None:
    cfg = FlakinessThresholdConfig()
    with pytest.raises(ValidationError):
        cfg.threshold_consecutive_runs = 9  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# evaluate_ac_flakiness (AC-3)                                                 #
# --------------------------------------------------------------------------- #


def test_exceeded_when_last_three_runs_all_transient() -> None:
    decision = evaluate_ac_flakiness(_history((1, 1, 1)), FlakinessThresholdConfig())
    assert decision == FlakinessThresholdDecision(
        ac_id="AC-1", exceeded=True, consecutive_transient_fail_runs=3
    )


def test_not_exceeded_with_fewer_than_threshold_runs() -> None:
    decision = evaluate_ac_flakiness(_history((1, 1)), FlakinessThresholdConfig())
    assert decision.exceeded is False
    assert decision.consecutive_transient_fail_runs == 2


def test_clean_deterministic_fail_does_not_qualify() -> None:
    # status=fail but retry 0 → breakage, NOT flakiness (AC-3). The most-recent
    # run breaks the streak even though earlier runs were transient.
    decision = evaluate_ac_flakiness(
        _history((1, 1, 0)), FlakinessThresholdConfig()
    )
    assert decision.exceeded is False
    assert decision.consecutive_transient_fail_runs == 0


def test_pass_with_retry_is_a_transient_fail() -> None:
    # status is irrelevant: a pass that needed an action-level retry IS transient.
    history = FlakinessAcHistory(
        ac_id="AC-1",
        runs=(
            _record(1, status="pass", n=0),
            _record(2, status="pass", n=1),
            _record(1, status="fail", n=2),
        ),
    )
    decision = evaluate_ac_flakiness(history, FlakinessThresholdConfig())
    assert decision.exceeded is True
    assert decision.consecutive_transient_fail_runs == 3


def test_only_trailing_streak_counts() -> None:
    # An interrupting clean run resets the streak; the trailing three qualify.
    decision = evaluate_ac_flakiness(_history((1, 1, 0, 1, 1, 1)), FlakinessThresholdConfig())
    assert decision.exceeded is True
    assert decision.consecutive_transient_fail_runs == 3


def test_threshold_transient_fail_count_predicate() -> None:
    # With threshold_transient_fail_count=2, a single-retry run is NOT transient.
    cfg = FlakinessThresholdConfig(threshold_consecutive_runs=3, threshold_transient_fail_count=2)
    assert evaluate_ac_flakiness(_history((2, 2, 1)), cfg).exceeded is False
    assert evaluate_ac_flakiness(_history((2, 2, 2)), cfg).exceeded is True


def test_empty_history_not_exceeded() -> None:
    decision = evaluate_ac_flakiness(_history(()), FlakinessThresholdConfig())
    assert decision.exceeded is False
    assert decision.consecutive_transient_fail_runs == 0


def test_decision_carries_ac_id() -> None:
    decision = evaluate_ac_flakiness(_history((1, 1, 1), ac_id="AC-7"), FlakinessThresholdConfig())
    assert decision.ac_id == "AC-7"


# --------------------------------------------------------------------------- #
# surface_flakiness_threshold_exceeded (AC-5, Pattern 5)                       #
# --------------------------------------------------------------------------- #


def test_surface_returns_emission_with_record_and_context() -> None:
    emission = surface_flakiness_threshold_exceeded(
        _STORY_ID, "AC-1", _canonical_registry(), 3
    )
    assert emission.marker_record.marker_class == FLAKINESS_THRESHOLD_EXCEEDED_MARKER
    assert emission.marker_record.ac_id == "AC-1"
    assert emission.diagnostic_context.story_id == _STORY_ID
    assert emission.diagnostic_context.ac_id == "AC-1"
    assert emission.diagnostic_context.consecutive_transient_fail_runs == 3


def test_surface_empty_registry_raises_before_state() -> None:
    with pytest.raises(UnknownMarkerClass):
        surface_flakiness_threshold_exceeded(
            _STORY_ID, "AC-1", MarkerClassRegistry(marker_classes=frozenset()), 3
        )


def test_surface_validates_against_disk_registry(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    emission = surface_flakiness_threshold_exceeded(
        _STORY_ID, "AC-1", runtime_marker_registry, 4
    )
    assert emission.marker_record.marker_class == FLAKINESS_THRESHOLD_EXCEEDED_MARKER


@pytest.mark.parametrize("hostile", ["   ", "a\nb", "a\x00b"])
def test_diagnostic_context_hardens_identifiers(hostile: str) -> None:
    with pytest.raises(ValidationError):
        FlakinessThresholdDiagnosticContext(
            story_id=hostile, ac_id="AC-1", consecutive_transient_fail_runs=3
        )
    with pytest.raises(ValidationError):
        FlakinessThresholdDiagnosticContext(
            story_id=_STORY_ID, ac_id=hostile, consecutive_transient_fail_runs=3
        )


def test_emission_record_marker_class_is_pinned() -> None:
    with pytest.raises(ValidationError):
        FlakinessThresholdEmissionRecord(marker_class="something-else", ac_id="AC-1")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Envelope byte-mirror + bundle render (AC-5)                                  #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def envelope_schema() -> dict[str, Any]:
    schema_path: pathlib.Path = find_repo_root() / "schemas" / "envelope.schema.yaml"
    return yaml.safe_load(schema_path.read_text(encoding="utf-8"))


def _minimal_qa_envelope() -> dict[str, Any]:
    return {
        "specialist": "qa",
        "status": "pass",
        "ac_results": [
            {
                "ac_id": "AC-1",
                "status": "pass",
                "assertions": ["holds"],
                "evidence_refs": [],
                "semantic_verification": "not_applicable",
            }
        ],
        "findings": [],
    }


_SCHEMA_BASE: dict[str, Any] = {
    "status": "pass",
    "artifacts": ["x"],
    "findings": [],
    "rationale": "ok",
}


def test_emission_record_validates_as_envelope_item(envelope_schema: dict[str, Any]) -> None:
    emission = surface_flakiness_threshold_exceeded(
        _STORY_ID, "AC-1", _canonical_registry(), 3
    )
    record = emission.marker_record.model_dump(mode="json")
    envelope = _SCHEMA_BASE | {"flakiness_emissions": [record]}
    assert validate_envelope(envelope, envelope_schema) == []


def test_envelope_flakiness_emission_requires_ac_id(envelope_schema: dict[str, Any]) -> None:
    envelope = _SCHEMA_BASE | {
        "flakiness_emissions": [{"marker_class": FLAKINESS_THRESHOLD_EXCEEDED_MARKER}]
    }
    assert validate_envelope(envelope, envelope_schema) != []


def test_envelope_flakiness_emission_rejects_additional_property(
    envelope_schema: dict[str, Any],
) -> None:
    envelope = _SCHEMA_BASE | {
        "flakiness_emissions": [
            {
                "marker_class": FLAKINESS_THRESHOLD_EXCEEDED_MARKER,
                "ac_id": "AC-1",
                "next_action": "retry",
            }
        ]
    }
    assert validate_envelope(envelope, envelope_schema) != []


def test_bundle_renders_greppable_marker_comment(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    envelope = _minimal_qa_envelope() | {
        "flakiness_emissions": [
            {"marker_class": FLAKINESS_THRESHOLD_EXCEEDED_MARKER, "ac_id": "AC-1"},
            {"marker_class": FLAKINESS_THRESHOLD_EXCEEDED_MARKER, "ac_id": "AC-2"},
        ]
    }
    rendered = _render_per_ac_section(envelope, marker_registry=runtime_marker_registry)
    assert rendered.count("bmad-automation:marker flakiness-threshold-exceeded") == 2
    assert "### Flakiness threshold exceeded" in rendered
    assert "AC `AC-1`" in rendered
    assert "AC `AC-2`" in rendered


def test_bundle_silent_without_emissions(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    rendered = _render_per_ac_section(
        _minimal_qa_envelope(), marker_registry=runtime_marker_registry
    )
    assert "flakiness-threshold-exceeded" not in rendered
