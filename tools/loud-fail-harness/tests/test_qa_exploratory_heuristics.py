"""Contract-coverage matrix for the three exploratory heuristics
substrate (Story 4.9).

Mirrors the test-file shape established by ``test_qa_evidence_tier.py``
(Story 4.8) and ``test_qa_ac_iteration.py`` (Story 4.6) for the
emission-helper + substrate-library tests; extends with the
:func:`evaluate_heuristic_applicability` decision-matrix surface and
the :func:`tag_heuristic_finding` shallow-copy helper.

Test enumeration (Story 4.9 AC-8 — ≥ 14 logical tests):

Type aliases + symbolic constants:
    1.  test_module_all_exports
    2.  test_heuristic_skipped_marker_constant_byte_for_byte
    3.  test_exploratory_heuristic_verification_mode_constant_byte_for_byte
    4.  test_heuristic_kind_literal_value_set_byte_equals_qa_behavioral_plan
    5.  test_verification_mode_literal_value_set_byte_equals_schema_enum

HeuristicSkippedDiagnosticContext + HeuristicSkippedEmissionRecord + HeuristicSkippedEmission models:
    6.  test_diagnostic_context_frozen_guard
    7.  test_emission_record_frozen_guard
    8.  test_emission_frozen_guard
    9.  test_diagnostic_context_required_fields
    10. test_diagnostic_context_story_id_min_length_enforced
    11. test_diagnostic_context_heuristic_kind_enum_enforced
    12. test_emission_record_sub_classification_matches_heuristic_kind
    13. test_emission_co_exposes_diagnostic_context

surface_heuristic_skipped Pattern-5 atomic-on-failure:
    14. test_surface_heuristic_skipped_atomic_on_failure
    15. test_surface_heuristic_skipped_happy_path

tag_heuristic_finding shallow-copy + idempotency-guard:
    16. test_tag_heuristic_finding_input_unchanged
    17. test_tag_heuristic_finding_returns_new_dict_with_field_stamped
    18. test_tag_heuristic_finding_double_tagging_precondition_assert

evaluate_heuristic_applicability decision matrix:
    19. test_evaluate_applicability_empty_plan
    20. test_evaluate_applicability_single_entry_one_kind
    21. test_evaluate_applicability_multi_entry_distinct_kinds
    22. test_evaluate_applicability_all_empty_tuples

LF line endings (optional):
    23. test_qa_exploratory_heuristics_module_has_lf_line_endings
"""

from __future__ import annotations

import pathlib
from typing import get_args

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness import qa_exploratory_heuristics
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.qa_behavioral_plan import (
    HeuristicApplicability,
    QABehavioralPlan,
    QABehavioralPlanEntry,
)
from loud_fail_harness.qa_exploratory_heuristics import (
    EXPLORATORY_HEURISTIC_VERIFICATION_MODE,
    HEURISTIC_SKIPPED_MARKER,
    HeuristicKind,
    HeuristicSkippedDiagnosticContext,
    HeuristicSkippedEmission,
    HeuristicSkippedEmissionRecord,
    VerificationMode,
    evaluate_heuristic_applicability,
    surface_heuristic_skipped,
    tag_heuristic_finding,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
)

REPO_ROOT = find_repo_root()
SCHEMA_PATH = REPO_ROOT / "schemas" / "envelope.schema.yaml"


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _make_registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(marker_classes=frozenset({"heuristic-skipped"}))


def _empty_registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(marker_classes=frozenset())


def _make_plan(
    entries_kinds: list[tuple[HeuristicApplicability, ...]],
) -> QABehavioralPlan:
    """Build a minimal plan with N entries; each entry's
    ``heuristic_applicability`` is the corresponding tuple in
    ``entries_kinds``. Other fields are placeholder values per the
    Story 4.1 MVP defaults."""
    entries = tuple(
        QABehavioralPlanEntry(
            ac_id=f"AC-{i + 1}",
            assertion_shape="placeholder",
            expected_evidence_tier="tier-1-mechanical",
            semantic_verification_requirement="not_applicable",
            heuristic_applicability=kinds,
        )
        for i, kinds in enumerate(entries_kinds)
    )
    return QABehavioralPlan(
        plan_status="generated",
        ac_hash="0" * 64,
        entries=entries,
    )


# --------------------------------------------------------------------------- #
# 1. Type aliases + symbolic constants                                        #
# --------------------------------------------------------------------------- #


def test_module_all_exports() -> None:
    expected = {
        "EXPLORATORY_HEURISTIC_VERIFICATION_MODE",
        "HEURISTIC_SKIPPED_MARKER",
        "HeuristicKind",
        "HeuristicSkippedDiagnosticContext",
        "HeuristicSkippedEmission",
        "HeuristicSkippedEmissionRecord",
        "VerificationMode",
        "evaluate_heuristic_applicability",
        "surface_heuristic_skipped",
        "tag_heuristic_finding",
    }
    assert set(qa_exploratory_heuristics.__all__) == expected


def test_heuristic_skipped_marker_constant_byte_for_byte() -> None:
    assert HEURISTIC_SKIPPED_MARKER == "heuristic-skipped"


def test_exploratory_heuristic_verification_mode_constant_byte_for_byte() -> None:
    assert EXPLORATORY_HEURISTIC_VERIFICATION_MODE == "exploratory-heuristic"


def test_heuristic_kind_literal_value_set_byte_equals_qa_behavioral_plan() -> None:
    """``HeuristicKind`` Literal value set byte-equals
    ``qa_behavioral_plan.HeuristicApplicability`` (cross-module
    duplication contract)."""
    assert get_args(HeuristicKind) == get_args(HeuristicApplicability)
    assert get_args(HeuristicKind) == ("empty-state", "error-state", "auth-boundary")


def test_verification_mode_literal_value_set_byte_equals_schema_enum() -> None:
    """``VerificationMode`` Literal value set byte-equals the schema's
    ``$defs/finding.properties.verification_mode.enum`` (taxonomy-
    freshness pattern)."""
    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_enum = tuple(
        schema["$defs"]["finding"]["properties"]["verification_mode"]["enum"]
    )
    assert get_args(VerificationMode) == schema_enum


# --------------------------------------------------------------------------- #
# 2. Diagnostic context + emission record + emission models                   #
# --------------------------------------------------------------------------- #


def test_diagnostic_context_frozen_guard() -> None:
    ctx = HeuristicSkippedDiagnosticContext(
        story_id="auto-001", heuristic_kind="empty-state"
    )
    with pytest.raises(ValidationError):
        ctx.story_id = "auto-002"  # type: ignore[misc]


def test_emission_record_frozen_guard() -> None:
    record = HeuristicSkippedEmissionRecord(
        marker_class="heuristic-skipped",
        sub_classification="empty-state",
        diagnostic_context=HeuristicSkippedDiagnosticContext(
            story_id="auto-001", heuristic_kind="empty-state"
        ),
    )
    with pytest.raises(ValidationError):
        record.sub_classification = "auth-boundary"  # type: ignore[misc]


def test_emission_frozen_guard() -> None:
    ctx = HeuristicSkippedDiagnosticContext(
        story_id="auto-001", heuristic_kind="empty-state"
    )
    record = HeuristicSkippedEmissionRecord(
        marker_class="heuristic-skipped",
        sub_classification="empty-state",
        diagnostic_context=ctx,
    )
    emission = HeuristicSkippedEmission(marker_record=record, diagnostic_context=ctx)
    with pytest.raises(ValidationError):
        emission.marker_record = record  # type: ignore[misc]


def test_diagnostic_context_required_fields() -> None:
    ctx = HeuristicSkippedDiagnosticContext(
        story_id="auto-001", heuristic_kind="error-state"
    )
    assert ctx.model_dump() == {
        "story_id": "auto-001",
        "heuristic_kind": "error-state",
    }


def test_diagnostic_context_story_id_min_length_enforced() -> None:
    with pytest.raises(ValidationError) as exc_info:
        HeuristicSkippedDiagnosticContext(story_id="", heuristic_kind="empty-state")
    assert "story_id" in str(exc_info.value)


def test_diagnostic_context_heuristic_kind_enum_enforced() -> None:
    with pytest.raises(ValidationError):
        HeuristicSkippedDiagnosticContext(
            story_id="auto-001",
            heuristic_kind="form-validation",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "kind", ["empty-state", "error-state", "auth-boundary"]
)
def test_emission_record_sub_classification_matches_heuristic_kind(
    kind: HeuristicKind,
) -> None:
    ctx = HeuristicSkippedDiagnosticContext(story_id="auto-001", heuristic_kind=kind)
    record = HeuristicSkippedEmissionRecord(
        marker_class="heuristic-skipped",
        sub_classification=kind,
        diagnostic_context=ctx,
    )
    assert record.sub_classification == kind
    assert record.marker_class == "heuristic-skipped"


def test_emission_co_exposes_diagnostic_context() -> None:
    ctx = HeuristicSkippedDiagnosticContext(
        story_id="auto-001", heuristic_kind="empty-state"
    )
    record = HeuristicSkippedEmissionRecord(
        marker_class="heuristic-skipped",
        sub_classification="empty-state",
        diagnostic_context=ctx,
    )
    emission = HeuristicSkippedEmission(
        marker_record=record, diagnostic_context=ctx
    )
    assert emission.marker_record.diagnostic_context == emission.diagnostic_context


# --------------------------------------------------------------------------- #
# 3. surface_heuristic_skipped Pattern-5 atomic-on-failure                    #
# --------------------------------------------------------------------------- #


def test_surface_heuristic_skipped_atomic_on_failure() -> None:
    registry = _empty_registry()
    with pytest.raises(UnknownMarkerClass):
        surface_heuristic_skipped(
            story_id="auto-001",
            heuristic_kind="empty-state",
            registry=registry,
        )


@pytest.mark.parametrize(
    "kind", ["empty-state", "error-state", "auth-boundary"]
)
def test_surface_heuristic_skipped_happy_path(kind: HeuristicKind) -> None:
    registry = _make_registry()
    emission = surface_heuristic_skipped(
        story_id="auto-001", heuristic_kind=kind, registry=registry
    )
    assert isinstance(emission, HeuristicSkippedEmission)
    assert emission.marker_record.marker_class == "heuristic-skipped"
    assert emission.marker_record.sub_classification == kind
    assert emission.diagnostic_context.story_id == "auto-001"
    assert emission.diagnostic_context.heuristic_kind == kind


# --------------------------------------------------------------------------- #
# 4. tag_heuristic_finding shallow-copy + idempotency-guard                   #
# --------------------------------------------------------------------------- #


def test_tag_heuristic_finding_input_unchanged() -> None:
    finding = {
        "id": "f1",
        "source": "qa",
        "title": "t",
        "detail": "d",
        "location": "",
        "bucket": "decision_needed",
        "severity": "MED",
    }
    snapshot = dict(finding)
    tag_heuristic_finding(finding)
    assert finding == snapshot


def test_tag_heuristic_finding_returns_new_dict_with_field_stamped() -> None:
    finding = {
        "id": "f1",
        "source": "qa",
        "title": "t",
        "detail": "d",
        "location": "",
        "bucket": "decision_needed",
        "severity": "MED",
    }
    result = tag_heuristic_finding(finding)
    assert result is not finding
    assert result["verification_mode"] == "exploratory-heuristic"
    for k, v in finding.items():
        assert result[k] == v


def test_tag_heuristic_finding_double_tagging_precondition_assert() -> None:
    finding = {
        "id": "f1",
        "source": "qa",
        "title": "t",
        "detail": "d",
        "location": "",
        "bucket": "decision_needed",
        "severity": "MED",
        "verification_mode": "exploratory-heuristic",
    }
    with pytest.raises(AssertionError):
        tag_heuristic_finding(finding)


# --------------------------------------------------------------------------- #
# 5. evaluate_heuristic_applicability decision matrix                         #
# --------------------------------------------------------------------------- #


def test_evaluate_applicability_empty_plan() -> None:
    plan = _make_plan([])
    for kind in ("empty-state", "error-state", "auth-boundary"):
        assert evaluate_heuristic_applicability(plan, kind) is False  # type: ignore[arg-type]


def test_evaluate_applicability_single_entry_one_kind() -> None:
    plan = _make_plan([("empty-state",)])
    assert evaluate_heuristic_applicability(plan, "empty-state") is True
    assert evaluate_heuristic_applicability(plan, "error-state") is False
    assert evaluate_heuristic_applicability(plan, "auth-boundary") is False


def test_evaluate_applicability_multi_entry_distinct_kinds() -> None:
    plan = _make_plan([("empty-state",), ("error-state", "auth-boundary")])
    assert evaluate_heuristic_applicability(plan, "empty-state") is True
    assert evaluate_heuristic_applicability(plan, "error-state") is True
    assert evaluate_heuristic_applicability(plan, "auth-boundary") is True


def test_evaluate_applicability_all_empty_tuples() -> None:
    plan = _make_plan([(), (), ()])
    for kind in ("empty-state", "error-state", "auth-boundary"):
        assert evaluate_heuristic_applicability(plan, kind) is False  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 6. LF line endings (optional)                                               #
# --------------------------------------------------------------------------- #


def test_qa_exploratory_heuristics_module_has_lf_line_endings() -> None:
    module_path = (
        REPO_ROOT
        / "tools"
        / "loud-fail-harness"
        / "src"
        / "loud_fail_harness"
        / "qa_exploratory_heuristics.py"
    )
    raw = pathlib.Path(module_path).read_bytes()
    assert b"\r" not in raw
