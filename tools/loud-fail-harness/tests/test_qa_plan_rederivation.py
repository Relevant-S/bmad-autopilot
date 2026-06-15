"""Contract-coverage matrix for the per-run plan re-derivation cross-check
library (Story 20.1 / FR-P2-9).

Sibling of ``test_qa_plan_drift.py`` (Story 4.2). The cross-check is an
independent, read-only drift surface layered ON TOP of FR23's AC-hash
channel: it fires on the ``reuse-existing`` path (``ac_hash`` unchanged)
when the persisted and re-derived plans differ at one of the three
non-AC-hash per-AC content surfaces.
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
import yaml

from loud_fail_harness import qa_plan_rederivation
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.bundle_assembly import _render_per_ac_section
from loud_fail_harness.envelope_validator import validate_envelope
from loud_fail_harness.qa_behavioral_plan import (
    FlowBranch,
    QABehavioralPlan,
    QABehavioralPlanEntry,
)
from loud_fail_harness.qa_plan_rederivation import (
    PLAN_REDERIVATION_DRIFT_DETECTED_MARKER,
    PlanRederivationCrossCheck,
    PlanRederivationDiagnosticContext,
    PlanRederivationEmissionRecord,
    surface_plan_rederivation_cross_check,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
    load_marker_class_registry,
)

_STORY_ID = "20-1-test"


@pytest.fixture(scope="module")
def repo_root() -> pathlib.Path:
    return find_repo_root()


@pytest.fixture(scope="module")
def envelope_schema(repo_root: pathlib.Path) -> dict[str, Any]:
    schema_path = repo_root / "schemas" / "envelope.schema.yaml"
    return yaml.safe_load(schema_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


def _canonical_registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(
        marker_classes=frozenset({PLAN_REDERIVATION_DRIFT_DETECTED_MARKER})
    )


def _entry(
    ac_id: str,
    *,
    heuristics: tuple[str, ...] = (),
    flow_branches: tuple[FlowBranch, ...] = (),
    tier: str = "tier-1-mechanical",
    semantic: str = "not_applicable",
) -> QABehavioralPlanEntry:
    return QABehavioralPlanEntry(
        ac_id=ac_id,
        assertion_shape=f"{ac_id} holds",
        expected_evidence_tier=tier,  # type: ignore[arg-type]
        semantic_verification_requirement=semantic,  # type: ignore[arg-type]
        heuristic_applicability=heuristics,  # type: ignore[arg-type]
        flow_branches=flow_branches,
    )


def _plan(entries: tuple[QABehavioralPlanEntry, ...]) -> QABehavioralPlan:
    return QABehavioralPlan(
        plan_status="generated",
        ac_hash="a" * 64,
        entries=entries,
    )


# --------------------------------------------------------------------------- #
# Green path                                                                  #
# --------------------------------------------------------------------------- #


def test_identical_plans_return_green() -> None:
    plan = _plan((_entry("AC-1", heuristics=("empty-state",)),))
    other = _plan((_entry("AC-1", heuristics=("empty-state",)),))

    result = surface_plan_rederivation_cross_check(
        plan, other, _STORY_ID, _canonical_registry()
    )

    assert result.cross_check_status == "green"
    assert result.emission_record is None


def test_assertion_shape_difference_is_not_drift() -> None:
    """AC-text-derived fields (assertion_shape) are EXCLUDED — a difference
    there does NOT fire the cross-check (FR23's channel)."""
    persisted = _plan((_entry("AC-1"),))
    rederived = _plan(
        (
            QABehavioralPlanEntry(
                ac_id="AC-1",
                assertion_shape="totally different shape",
                expected_evidence_tier="tier-1-mechanical",
                semantic_verification_requirement="not_applicable",
            ),
        )
    )

    result = surface_plan_rederivation_cross_check(
        persisted, rederived, _STORY_ID, _canonical_registry()
    )

    assert result.cross_check_status == "green"


# --------------------------------------------------------------------------- #
# Drift surfaces (AC-2)                                                        #
# --------------------------------------------------------------------------- #


def test_heuristic_applicability_drift() -> None:
    persisted = _plan((_entry("AC-1", heuristics=("empty-state",)),))
    rederived = _plan(
        (_entry("AC-1", heuristics=("empty-state", "error-state")),)
    )

    result = surface_plan_rederivation_cross_check(
        persisted, rederived, _STORY_ID, _canonical_registry()
    )

    assert result.cross_check_status == "drift-detected"
    diag = result.emission_record.diagnostic_context
    assert diag.drift_surfaces == ("heuristic_applicability",)
    assert diag.drifted_ac_ids == ("AC-1",)


def test_flow_branches_drift() -> None:
    branch = FlowBranch(branch_id="b1", description="optional path")
    persisted = _plan((_entry("AC-1"),))
    rederived = _plan((_entry("AC-1", flow_branches=(branch,)),))

    result = surface_plan_rederivation_cross_check(
        persisted, rederived, _STORY_ID, _canonical_registry()
    )

    assert result.cross_check_status == "drift-detected"
    assert result.emission_record.diagnostic_context.drift_surfaces == (
        "flow_branches",
    )


def test_semantic_verification_requirement_drift() -> None:
    persisted = _plan((_entry("AC-1", semantic="not_applicable"),))
    rederived = _plan((_entry("AC-1", semantic="required"),))

    result = surface_plan_rederivation_cross_check(
        persisted, rederived, _STORY_ID, _canonical_registry()
    )

    assert result.cross_check_status == "drift-detected"
    assert result.emission_record.diagnostic_context.drift_surfaces == (
        "semantic_verification_tier",
    )


def test_expected_evidence_tier_drift_folds_into_semantic_surface() -> None:
    persisted = _plan((_entry("AC-1", tier="tier-1-mechanical"),))
    rederived = _plan((_entry("AC-1", tier="tier-3-semantic"),))

    result = surface_plan_rederivation_cross_check(
        persisted, rederived, _STORY_ID, _canonical_registry()
    )

    assert result.cross_check_status == "drift-detected"
    assert result.emission_record.diagnostic_context.drift_surfaces == (
        "semantic_verification_tier",
    )


def test_multiple_surfaces_reported_in_canonical_order() -> None:
    branch = FlowBranch(branch_id="b1", description="optional path")
    persisted = _plan((_entry("AC-1"),))
    rederived = _plan(
        (
            _entry(
                "AC-1",
                heuristics=("error-state",),
                flow_branches=(branch,),
                semantic="required",
            ),
        )
    )

    result = surface_plan_rederivation_cross_check(
        persisted, rederived, _STORY_ID, _canonical_registry()
    )

    assert result.emission_record.diagnostic_context.drift_surfaces == (
        "heuristic_applicability",
        "flow_branches",
        "semantic_verification_tier",
    )


def test_drift_matched_by_ac_id_across_multiple_acs() -> None:
    persisted = _plan(
        (_entry("AC-1"), _entry("AC-2", heuristics=("empty-state",)))
    )
    rederived = _plan(
        (_entry("AC-1"), _entry("AC-2", heuristics=("auth-boundary",)))
    )

    result = surface_plan_rederivation_cross_check(
        persisted, rederived, _STORY_ID, _canonical_registry()
    )

    diag = result.emission_record.diagnostic_context
    assert diag.drifted_ac_ids == ("AC-2",)
    assert diag.drift_surfaces == ("heuristic_applicability",)


# --------------------------------------------------------------------------- #
# Atomic-on-failure + marker linkage                                          #
# --------------------------------------------------------------------------- #


def test_empty_registry_raises_before_any_state(
) -> None:
    persisted = _plan((_entry("AC-1", heuristics=("empty-state",)),))
    rederived = _plan((_entry("AC-1", heuristics=("error-state",)),))

    with pytest.raises(UnknownMarkerClass):
        surface_plan_rederivation_cross_check(
            persisted,
            rederived,
            _STORY_ID,
            MarkerClassRegistry(marker_classes=frozenset()),
        )


def test_green_path_also_validates_marker_first() -> None:
    """The marker is validated on EVERY call (green AND drift) — a registry
    that cannot support the marker fails loud even on a no-drift run."""
    plan = _plan((_entry("AC-1"),))
    with pytest.raises(UnknownMarkerClass):
        surface_plan_rederivation_cross_check(
            plan, plan, _STORY_ID, MarkerClassRegistry(marker_classes=frozenset())
        )


def test_canonical_registry_from_disk(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    persisted = _plan((_entry("AC-1", heuristics=("empty-state",)),))
    rederived = _plan((_entry("AC-1", heuristics=("error-state",)),))

    result = surface_plan_rederivation_cross_check(
        persisted, rederived, _STORY_ID, runtime_marker_registry
    )

    assert result.cross_check_status == "drift-detected"
    assert (
        result.emission_record.marker_class
        == PLAN_REDERIVATION_DRIFT_DETECTED_MARKER
    )


# --------------------------------------------------------------------------- #
# Model coherence + module hygiene                                            #
# --------------------------------------------------------------------------- #


def test_drift_status_requires_emission_record() -> None:
    with pytest.raises(ValueError):
        PlanRederivationCrossCheck(cross_check_status="drift-detected")


def test_green_status_forbids_emission_record() -> None:
    record = PlanRederivationEmissionRecord(
        marker_class=PLAN_REDERIVATION_DRIFT_DETECTED_MARKER,
        diagnostic_context=PlanRederivationDiagnosticContext(
            story_id=_STORY_ID,
            drift_surfaces=("flow_branches",),
            drifted_ac_ids=("AC-1",),
        ),
    )
    with pytest.raises(ValueError):
        PlanRederivationCrossCheck(
            cross_check_status="green", emission_record=record
        )


def test_diagnostic_context_rejects_whitespace_story_id() -> None:
    with pytest.raises(ValueError):
        PlanRederivationDiagnosticContext(
            story_id="   ",
            drift_surfaces=("flow_branches",),
            drifted_ac_ids=("AC-1",),
        )


def test_diagnostic_context_requires_nonempty_surfaces() -> None:
    with pytest.raises(ValueError):
        PlanRederivationDiagnosticContext(
            story_id=_STORY_ID, drift_surfaces=(), drifted_ac_ids=("AC-1",)
        )


def test_module_all_exports() -> None:
    expected = {
        "PLAN_REDERIVATION_DRIFT_DETECTED_MARKER",
        "PlanRederivationCrossCheck",
        "PlanRederivationDiagnosticContext",
        "PlanRederivationEmissionRecord",
        "surface_plan_rederivation_cross_check",
    }
    assert expected.issubset(set(qa_plan_rederivation.__all__))


def test_module_has_lf_line_endings(repo_root: pathlib.Path) -> None:
    module_path = (
        repo_root
        / "tools"
        / "loud-fail-harness"
        / "src"
        / "loud_fail_harness"
        / "qa_plan_rederivation.py"
    )
    assert b"\r" not in module_path.read_bytes()


# --------------------------------------------------------------------------- #
# Envelope schema (Task 3)                                                     #
# --------------------------------------------------------------------------- #


def _qa_envelope_base() -> dict[str, Any]:
    return {
        "status": "pass",
        "artifacts": [
            "_bmad-output/qa-evidence/s/r/ac1.log"
        ],
        "findings": [],
        "rationale": "AC-1 verified; reuse-existing cross-check ran.",
        "ac_results": [
            {
                "ac_id": "AC-1",
                "status": "pass",
                "assertions": ["assertion"],
                "evidence_refs": [
                    {
                        "path": "_bmad-output/qa-evidence/s/r/ac1.log",
                        "tier": "tier-1-mechanical",
                    }
                ],
                "semantic_verification": "not_applicable",
            }
        ],
    }


def test_envelope_green_field_validates(envelope_schema: dict[str, Any]) -> None:
    env = _qa_envelope_base()
    env["plan_rederivation"] = {"cross_check_status": "green"}
    assert validate_envelope(env, envelope_schema) == []


def test_envelope_drift_field_validates(envelope_schema: dict[str, Any]) -> None:
    env = _qa_envelope_base()
    env["plan_rederivation"] = {
        "cross_check_status": "drift-detected",
        "story_id": _STORY_ID,
        "drift_surfaces": ["heuristic_applicability", "semantic_verification_tier"],
        "drifted_ac_ids": ["AC-1"],
    }
    assert validate_envelope(env, envelope_schema) == []


def test_envelope_absent_field_validates(envelope_schema: dict[str, Any]) -> None:
    assert validate_envelope(_qa_envelope_base(), envelope_schema) == []


def test_envelope_drift_without_required_fields_fails(
    envelope_schema: dict[str, Any],
) -> None:
    env = _qa_envelope_base()
    env["plan_rederivation"] = {"cross_check_status": "drift-detected"}
    assert validate_envelope(env, envelope_schema) != []


def test_envelope_unknown_surface_fails(envelope_schema: dict[str, Any]) -> None:
    env = _qa_envelope_base()
    env["plan_rederivation"] = {
        "cross_check_status": "drift-detected",
        "story_id": _STORY_ID,
        "drift_surfaces": ["ac_hash"],
        "drifted_ac_ids": ["AC-1"],
    }
    assert validate_envelope(env, envelope_schema) != []


# --------------------------------------------------------------------------- #
# Bundle render (Task 6)                                                       #
# --------------------------------------------------------------------------- #


def test_bundle_renders_green_line(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    env = _qa_envelope_base()
    env["plan_rederivation"] = {"cross_check_status": "green"}
    rendered = _render_per_ac_section(env, marker_registry=runtime_marker_registry)
    assert "FR-P2-9 cross-check: green" in rendered
    assert PLAN_REDERIVATION_DRIFT_DETECTED_MARKER not in rendered


def test_bundle_renders_drift_marker_and_subsection(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    env = _qa_envelope_base()
    env["plan_rederivation"] = {
        "cross_check_status": "drift-detected",
        "story_id": _STORY_ID,
        "drift_surfaces": ["heuristic_applicability"],
        "drifted_ac_ids": ["AC-1"],
    }
    rendered = _render_per_ac_section(env, marker_registry=runtime_marker_registry)
    assert "FR-P2-9 cross-check: drift detected" in rendered
    assert "### Plan re-derivation drift detected" in rendered
    assert (
        f"<!-- bmad-automation:marker {PLAN_REDERIVATION_DRIFT_DETECTED_MARKER} -->"
        in rendered
    )


def test_bundle_absent_field_silent(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    rendered = _render_per_ac_section(
        _qa_envelope_base(), marker_registry=runtime_marker_registry
    )
    assert "FR-P2-9 cross-check" not in rendered
    assert PLAN_REDERIVATION_DRIFT_DETECTED_MARKER not in rendered
