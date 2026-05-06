"""Contract-coverage matrix for the three-tier evidence hierarchy
substrate (Story 4.8).

Mirrors the test-file shape established by ``test_qa_ac_iteration.py``
(Story 4.6), ``test_qa_plan_drift.py`` (Story 4.2), and
``test_qa_behavioral_plan.py`` (Story 4.1) for the emission-helper +
substrate-library tests; extends with the
:func:`evaluate_semantic_verification` decision-matrix surface.

Test enumeration (Story 4.8 AC-11 — ≥ 12 logical tests):

Type aliases + symbolic constants:
    1.  test_module_all_exports
    2.  test_tier_3_not_configured_marker_constant_byte_for_byte
    3.  test_evidence_tier_literal_value_set_byte_equals_schema_enum
    4.  test_semantic_verification_result_literal_value_set_byte_equals_schema_enum
    5.  test_semantic_verification_requirement_literal_value_set

EvidenceRef model contract:
    6.  test_evidence_ref_frozen_guard
    7.  test_evidence_ref_model_dump_shape
    8.  test_evidence_ref_path_min_length_enforced
    9.  test_evidence_ref_tier_enum_enforced
    10. test_evidence_ref_dump_validates_against_schema_evidence_ref

Tier-3 diagnostic + emission models:
    11. test_tier_3_not_configured_diagnostic_context_frozen
    12. test_tier_3_not_configured_diagnostic_context_required_fields
    13. test_tier_3_not_configured_emission_record_frozen
    14. test_tier_3_not_configured_emission_co_exposes_diagnostic_context
    15. test_how_to_enable_pointer_carries_canonical_taxonomy_text

surface_tier_3_not_configured Pattern-5 atomic-on-failure:
    16. test_surface_tier_3_not_configured_atomic_on_failure
    17. test_surface_tier_3_not_configured_happy_path

evaluate_semantic_verification decision matrix (FR20 + FR21):
    18. test_evaluate_semantic_verification_not_applicable_branch
    19. test_evaluate_semantic_verification_optional_configured_branch
    20. test_evaluate_semantic_verification_optional_not_configured_branch
    21. test_evaluate_semantic_verification_required_configured_branch
    22. test_evaluate_semantic_verification_required_not_configured_branch

Taxonomy freshness:
    23. test_how_to_enable_pointer_byte_equals_marker_taxonomy_diagnostic_pointer

LF line endings:
    24. test_qa_evidence_tier_module_has_lf_line_endings
"""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness import qa_evidence_tier
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.qa_evidence_tier import (
    TIER_3_NOT_CONFIGURED_MARKER,
    EvidenceRef,
    Tier3NotConfiguredDiagnosticContext,
    Tier3NotConfiguredEmission,
    Tier3NotConfiguredEmissionRecord,
    _HOW_TO_ENABLE_POINTER,
    evaluate_semantic_verification,
    surface_tier_3_not_configured,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
)

REPO_ROOT = find_repo_root()
SCHEMA_PATH = REPO_ROOT / "schemas" / "envelope.schema.yaml"
MARKER_TAXONOMY_PATH = REPO_ROOT / "schemas" / "marker-taxonomy.yaml"


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _make_registry() -> MarkerClassRegistry:
    """Registry containing exactly the ``Tier-3-not-configured`` marker
    class."""
    return MarkerClassRegistry(
        marker_classes=frozenset({"Tier-3-not-configured"})
    )


def _empty_registry() -> MarkerClassRegistry:
    """Registry with no marker classes (consumed by the atomic-on-failure
    test)."""
    return MarkerClassRegistry(marker_classes=frozenset())


# --------------------------------------------------------------------------- #
# 1. Type aliases + symbolic constants                                        #
# --------------------------------------------------------------------------- #


def test_module_all_exports() -> None:
    """The module's ``__all__`` enumerates every public symbol the
    wrapper-side composition + downstream Story 4.13 consumers depend
    on."""
    expected = {
        "EvidenceRef",
        "EvidenceTier",
        "PlanAndConfigForEvaluation",
        "SemanticVerificationRequirement",
        "SemanticVerificationResult",
        "TIER_3_NOT_CONFIGURED_MARKER",
        "Tier3NotConfiguredDiagnosticContext",
        "Tier3NotConfiguredEmission",
        "Tier3NotConfiguredEmissionRecord",
        "evaluate_semantic_verification",
        "record_tier_3_not_configured_in_run_state",
        "surface_tier_3_not_configured",
    }
    assert set(qa_evidence_tier.__all__) == expected


def test_tier_3_not_configured_marker_constant_byte_for_byte() -> None:
    """The symbolic constant is the canonical marker class string from
    ``schemas/marker-taxonomy.yaml`` line 78."""
    assert TIER_3_NOT_CONFIGURED_MARKER == "Tier-3-not-configured"


def test_evidence_tier_literal_value_set_byte_equals_schema_enum() -> None:
    """``EvidenceTier`` Literal value set mirrors
    ``$defs/evidence_ref.tier.enum`` byte-for-byte."""
    from typing import get_args

    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_enum = tuple(schema["$defs"]["evidence_ref"]["properties"]["tier"]["enum"])
    literal_values = get_args(qa_evidence_tier.EvidenceTier)
    assert literal_values == schema_enum
    # Also byte-equal to qa_behavioral_plan.ExpectedEvidenceTier (the
    # plan-side counterpart): same values, different field semantics.
    from loud_fail_harness import qa_behavioral_plan
    assert get_args(qa_behavioral_plan.ExpectedEvidenceTier) == literal_values


def test_semantic_verification_result_literal_value_set_byte_equals_schema_enum() -> None:
    """``SemanticVerificationResult`` Literal value set mirrors
    ``$defs/ac_result.semantic_verification.enum`` byte-for-byte."""
    from typing import get_args

    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_enum = tuple(
        schema["$defs"]["ac_result"]["properties"]["semantic_verification"]["enum"]
    )
    assert get_args(qa_evidence_tier.SemanticVerificationResult) == schema_enum


def test_semantic_verification_requirement_literal_value_set() -> None:
    """``SemanticVerificationRequirement`` Literal value set is the
    PLAN-side enum: ``required | optional | not_applicable``. Mirrors
    ``qa_behavioral_plan.SemanticVerificationRequirement``."""
    from typing import get_args

    from loud_fail_harness import qa_behavioral_plan
    assert get_args(qa_evidence_tier.SemanticVerificationRequirement) == (
        "required",
        "optional",
        "not_applicable",
    )
    assert get_args(qa_behavioral_plan.SemanticVerificationRequirement) == get_args(
        qa_evidence_tier.SemanticVerificationRequirement
    )


# --------------------------------------------------------------------------- #
# 2. EvidenceRef model contract                                               #
# --------------------------------------------------------------------------- #


def test_evidence_ref_frozen_guard() -> None:
    ref = EvidenceRef(path="evidence/x.txt", tier="tier-1-mechanical")
    with pytest.raises(ValidationError):
        ref.path = "evidence/y.txt"  # type: ignore[misc]


def test_evidence_ref_model_dump_shape() -> None:
    ref = EvidenceRef(path="evidence/x.txt", tier="tier-2-outcome")
    assert ref.model_dump() == {
        "path": "evidence/x.txt",
        "tier": "tier-2-outcome",
    }


def test_evidence_ref_path_min_length_enforced() -> None:
    with pytest.raises(ValidationError) as exc_info:
        EvidenceRef(path="", tier="tier-1-mechanical")
    assert "path" in str(exc_info.value)


def test_evidence_ref_tier_enum_enforced() -> None:
    with pytest.raises(ValidationError) as exc_info:
        EvidenceRef(path="evidence/x.txt", tier="tier-4-formal-proof")  # type: ignore[arg-type]
    assert "tier" in str(exc_info.value)


def test_evidence_ref_dump_validates_against_schema_evidence_ref() -> None:
    """``EvidenceRef.model_dump()`` JSON shape validates against the
    schema's ``$defs/evidence_ref`` byte-for-byte."""
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    schema = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    evidence_ref_schema = schema["$defs"]["evidence_ref"]
    # Inline the $defs context so any future cross-ref keeps working.
    resource = Resource.from_contents(schema, default_specification=DRAFT202012)
    registry = Registry().with_resource(uri=schema["$id"], resource=resource)
    validator = Draft202012Validator(evidence_ref_schema, registry=registry)
    ref = EvidenceRef(path="evidence/x.txt", tier="tier-3-semantic")
    errors = list(validator.iter_errors(ref.model_dump(mode="json")))
    assert errors == [], f"EvidenceRef dump failed schema validation: {errors}"


# --------------------------------------------------------------------------- #
# 3. Tier-3 diagnostic + emission models                                      #
# --------------------------------------------------------------------------- #


def test_tier_3_not_configured_diagnostic_context_frozen() -> None:
    ctx = Tier3NotConfiguredDiagnosticContext(
        story_id="sample-001",
        ac_id="AC-2",
        how_to_enable_pointer="x",
    )
    with pytest.raises(ValidationError):
        ctx.story_id = "other"  # type: ignore[misc]


def test_tier_3_not_configured_diagnostic_context_required_fields() -> None:
    """Each of the three fields is required (min_length=1 enforced)."""
    with pytest.raises(ValidationError):
        Tier3NotConfiguredDiagnosticContext(
            story_id="",
            ac_id="AC-2",
            how_to_enable_pointer="x",
        )
    with pytest.raises(ValidationError):
        Tier3NotConfiguredDiagnosticContext(
            story_id="sample",
            ac_id="",
            how_to_enable_pointer="x",
        )
    with pytest.raises(ValidationError):
        Tier3NotConfiguredDiagnosticContext(
            story_id="sample",
            ac_id="AC-2",
            how_to_enable_pointer="",
        )


def test_tier_3_not_configured_emission_record_frozen() -> None:
    ctx = Tier3NotConfiguredDiagnosticContext(
        story_id="sample-001",
        ac_id="AC-2",
        how_to_enable_pointer="x",
    )
    record = Tier3NotConfiguredEmissionRecord(
        marker_class="Tier-3-not-configured",
        diagnostic_context=ctx,
    )
    with pytest.raises(ValidationError):
        record.marker_class = "other-marker"  # type: ignore[misc]


def test_tier_3_not_configured_emission_co_exposes_diagnostic_context() -> None:
    """Mirrors Story 4.6's ``SmokeFirstAbortEmission`` co-exposure: the
    ``diagnostic_context`` is the same object as
    ``marker_record.diagnostic_context``."""
    ctx = Tier3NotConfiguredDiagnosticContext(
        story_id="sample-001",
        ac_id="AC-2",
        how_to_enable_pointer="x",
    )
    record = Tier3NotConfiguredEmissionRecord(
        marker_class="Tier-3-not-configured",
        diagnostic_context=ctx,
    )
    emission = Tier3NotConfiguredEmission(
        marker_record=record,
        diagnostic_context=ctx,
    )
    assert emission.diagnostic_context is emission.marker_record.diagnostic_context


def test_how_to_enable_pointer_carries_canonical_taxonomy_text() -> None:
    """The constant carries the canonical FR31-shaped diagnostic
    pointer."""
    assert "Tier-3" in _HOW_TO_ENABLE_POINTER
    assert "qa-runbook.yaml" in _HOW_TO_ENABLE_POINTER
    assert "Remediation" in _HOW_TO_ENABLE_POINTER
    assert _HOW_TO_ENABLE_POINTER.endswith("\n")


# --------------------------------------------------------------------------- #
# 4. surface_tier_3_not_configured Pattern-5 atomic-on-failure                #
# --------------------------------------------------------------------------- #


def test_surface_tier_3_not_configured_atomic_on_failure() -> None:
    """Registry rejection raises ``UnknownMarkerClass`` BEFORE any
    partial state is constructed (Pattern 5; mirrors Story 4.6)."""
    registry = _empty_registry()
    with pytest.raises(UnknownMarkerClass):
        surface_tier_3_not_configured(
            story_id="sample-001",
            ac_id="AC-2",
            registry=registry,
        )


def test_surface_tier_3_not_configured_happy_path() -> None:
    """Happy path: the emission carries the correct marker_class,
    story_id, ac_id, and the canonical how_to_enable_pointer."""
    registry = _make_registry()
    emission = surface_tier_3_not_configured(
        story_id="sample-001",
        ac_id="AC-2",
        registry=registry,
    )
    assert isinstance(emission, Tier3NotConfiguredEmission)
    assert emission.marker_record.marker_class == "Tier-3-not-configured"
    assert emission.diagnostic_context.story_id == "sample-001"
    assert emission.diagnostic_context.ac_id == "AC-2"
    assert (
        emission.diagnostic_context.how_to_enable_pointer
        == _HOW_TO_ENABLE_POINTER
    )


# --------------------------------------------------------------------------- #
# 5. evaluate_semantic_verification decision matrix (FR20 + FR21)             #
# --------------------------------------------------------------------------- #


def test_evaluate_semantic_verification_not_applicable_branch() -> None:
    """``plan_requirement == "not_applicable"`` → no marker, no
    `not_configured` collapse — explicit non-applicability is not a
    gap (epics.md line 2047)."""
    registry = _make_registry()
    for tier_3_configured in (True, False):
        result, marker = evaluate_semantic_verification(
            plan_requirement="not_applicable",
            tier_3_configured=tier_3_configured,
            story_id="sample-001",
            ac_id="AC-1",
            registry=registry,
        )
        assert result == "not_applicable"
        assert marker is None


def test_evaluate_semantic_verification_optional_configured_branch() -> None:
    """``plan_requirement == "optional"`` AND ``tier_3_configured`` →
    ``("verified", None)`` (Tier-3 ran successfully)."""
    registry = _make_registry()
    result, marker = evaluate_semantic_verification(
        plan_requirement="optional",
        tier_3_configured=True,
        story_id="sample-001",
        ac_id="AC-1",
        registry=registry,
    )
    assert result == "verified"
    assert marker is None


def test_evaluate_semantic_verification_optional_not_configured_branch() -> None:
    """``plan_requirement == "optional"`` AND NOT ``tier_3_configured``
    → ``("not_applicable", None)`` (optional-without-config collapses
    to non-applicability per the doctrine extension; NO marker)."""
    registry = _make_registry()
    result, marker = evaluate_semantic_verification(
        plan_requirement="optional",
        tier_3_configured=False,
        story_id="sample-001",
        ac_id="AC-1",
        registry=registry,
    )
    assert result == "not_applicable"
    assert marker is None


def test_evaluate_semantic_verification_required_configured_branch() -> None:
    """``plan_requirement == "required"`` AND ``tier_3_configured`` →
    ``("verified", None)`` per epics.md line 2042."""
    registry = _make_registry()
    result, marker = evaluate_semantic_verification(
        plan_requirement="required",
        tier_3_configured=True,
        story_id="sample-001",
        ac_id="AC-1",
        registry=registry,
    )
    assert result == "verified"
    assert marker is None


def test_evaluate_semantic_verification_required_not_configured_branch() -> None:
    """``plan_requirement == "required"`` AND NOT ``tier_3_configured``
    → ``("not_configured", emission.marker_record)`` per epics.md
    lines 2036-2038. The emission carries the canonical
    ``how_to_enable_pointer``."""
    registry = _make_registry()
    result, marker = evaluate_semantic_verification(
        plan_requirement="required",
        tier_3_configured=False,
        story_id="sample-001",
        ac_id="AC-2",
        registry=registry,
    )
    assert result == "not_configured"
    assert marker is not None
    assert marker.marker_class == "Tier-3-not-configured"
    assert marker.diagnostic_context.story_id == "sample-001"
    assert marker.diagnostic_context.ac_id == "AC-2"
    assert (
        marker.diagnostic_context.how_to_enable_pointer
        == _HOW_TO_ENABLE_POINTER
    )


def test_evaluate_semantic_verification_required_not_configured_propagates_unknown_marker() -> None:
    """``required + not_configured`` calls ``surface_tier_3_not_configured``
    which raises ``UnknownMarkerClass`` if the registry is empty —
    propagates UNCHANGED per Pattern 5."""
    registry = _empty_registry()
    with pytest.raises(UnknownMarkerClass):
        evaluate_semantic_verification(
            plan_requirement="required",
            tier_3_configured=False,
            story_id="sample-001",
            ac_id="AC-2",
            registry=registry,
        )


# --------------------------------------------------------------------------- #
# 6. Taxonomy freshness                                                       #
# --------------------------------------------------------------------------- #


def test_how_to_enable_pointer_byte_equals_marker_taxonomy_diagnostic_pointer() -> None:
    """Freshness guard: ``_HOW_TO_ENABLE_POINTER`` byte-equals the YAML's
    ``diagnostic_pointer`` value for the ``Tier-3-not-configured`` entry.
    Whitespace-normalized comparison (both sides stripped) — fails LOUDLY
    if the taxonomy is edited without updating the substrate constant.
    Normalization guards against YAML block-scalar chomp-indicator
    differences (``|`` vs ``|-``) affecting trailing newlines.
    """
    taxonomy = yaml.safe_load(MARKER_TAXONOMY_PATH.read_text(encoding="utf-8"))
    entries = taxonomy["markers"]
    [target] = [
        e for e in entries if e["marker_class"] == "Tier-3-not-configured"
    ]
    yaml_pointer = target["diagnostic_pointer"]
    assert yaml_pointer.strip() == _HOW_TO_ENABLE_POINTER.strip(), (
        "Tier-3-not-configured diagnostic_pointer drifted: marker-taxonomy.yaml "
        "and qa_evidence_tier._HOW_TO_ENABLE_POINTER are out of sync"
    )


# --------------------------------------------------------------------------- #
# 7. LF line endings                                                          #
# --------------------------------------------------------------------------- #


def test_qa_evidence_tier_module_has_lf_line_endings() -> None:
    """The new module file does NOT contain CR characters (mirrors the
    Stories 2.8 / 2.9 / 3.5 / 4.1-4.7 LF-discipline test)."""
    module_path = (
        REPO_ROOT
        / "tools"
        / "loud-fail-harness"
        / "src"
        / "loud_fail_harness"
        / "qa_evidence_tier.py"
    )
    raw = module_path.read_bytes()
    assert b"\r" not in raw, (
        "qa_evidence_tier.py contains CR characters; expected pure LF endings"
    )



def test_record_tier_3_not_configured_in_run_state_populates_marker_contexts() -> None:
    """AC-5 — D-6.2-1 deferred-work discharge: calling
    record_tier_3_not_configured_in_run_state with a RunState and ac_id
    produces a new RunState with the Tier-3-not-configured marker in
    active_markers and marker_contexts["Tier-3-not-configured"] == {"ac_id": <value>}."""
    from loud_fail_harness.qa_evidence_tier import record_tier_3_not_configured_in_run_state
    from loud_fail_harness.run_state import CostToDateBySpecialist, RunState

    rs = RunState(
        schema_version="1.1",
        story_id="6-7-test",
        run_id="run-6-7-001",
        current_state="in-progress",
        branch_name="bmad-automation/story/6-7-test",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )
    result = record_tier_3_not_configured_in_run_state(
        run_state=rs,
        ac_id="AC-5",
    )
    assert result is not rs
    assert TIER_3_NOT_CONFIGURED_MARKER in result.active_markers
    assert result.marker_contexts.get(TIER_3_NOT_CONFIGURED_MARKER) == {"ac_id": "AC-5"}
