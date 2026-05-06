"""Contract-coverage matrix for the AC-hash plan-drift library (Story 4.2).

Mirrors the test-file shape established by ``test_review_layer_failure.py``
(Story 3.3 — single-source-of-truth two/three-channel atomic emission)
+ ``test_qa_behavioral_plan.py`` (Story 4.1 — pure-library plan
creation + reuse) + the canonical-fixture regeneration-baseline pattern
from ``test_bundle_assembly.py`` (Story 3.4).

Test enumeration (Story 4.2 AC-7 — 18 tests):
    1.  test_surface_plan_drift_resets_plan_status_to_generated_from_human_reviewed
    2.  test_surface_plan_drift_resets_plan_status_to_generated_from_generated
    3.  test_surface_plan_drift_fresh_plan_ac_hash_matches_current_ac_list
    4.  test_surface_plan_drift_diagnostic_context_carries_four_fields
    5.  test_surface_plan_drift_marker_record_carries_canonical_marker_class
    6.  test_surface_plan_drift_validates_marker_via_registry
    7.  test_surface_plan_drift_with_canonical_registry
    8.  test_surface_plan_drift_regenerated_entries_reflect_new_ac_list
    9.  test_no_drift_path_does_not_call_surface_plan_drift
    10. test_ac_reordering_does_not_trigger_drift
    11. test_substantive_ac_text_change_triggers_drift
    12. test_canonical_plan_drift_bundle_fixture_matches_assembler_output
    13. test_qa_plan_drift_has_lf_line_endings
    14. test_module_all_exports
    15. test_plan_drift_envelope_field_validates_against_schema
    16. test_plan_drift_envelope_field_absent_validates_against_schema
    17. test_bundle_render_emits_marker_when_plan_drift_present
    18. test_bundle_render_silent_when_plan_drift_absent
"""

from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime, timezone
from typing import Any

import pytest
import yaml

from loud_fail_harness import qa_plan_drift
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.bundle_assembly import assemble_bundle
from loud_fail_harness.envelope_validator import validate_envelope
from loud_fail_harness.qa_behavioral_plan import (
    AcEntry,
    QABehavioralPlan,
    QABehavioralPlanEntry,
    compute_ac_hash,
    generate_plan,
    persist_or_reuse_plan,
    render_plan_section,
)
from loud_fail_harness.qa_plan_drift import (
    PLAN_DRIFT_DETECTED_MARKER,
    PlanDriftDiagnosticContext,
    PlanDriftEmission,
    PlanDriftEmissionRecord,
    surface_plan_drift,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
    load_marker_class_registry,
)


# --------------------------------------------------------------------------- #
# Fixtures (resolution at fixture-time only — Epic 1 retro Action #1)         #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def repo_root() -> pathlib.Path:
    """Module-scoped repo-root fixture (Epic 1 retro Action #1: never call
    ``find_repo_root`` at module top-level)."""
    return find_repo_root()


@pytest.fixture(scope="module")
def envelope_schema(repo_root: pathlib.Path) -> dict[str, Any]:
    schema_path = repo_root / "schemas" / "envelope.schema.yaml"
    return yaml.safe_load(schema_path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


_INITIAL_AC_TEXT_BY_ID: dict[str, str] = {
    "1": "User can register with email.",
    "2": "Form rejects invalid email syntax.",
    "3": "Unauthenticated /dashboard redirects.",
}

_DRIFTED_AC_TEXT_BY_ID: dict[str, str] = {
    "1": "User can register with email AND phone number.",  # changed
    "2": "Form rejects invalid email syntax.",
    "3": "Unauthenticated /dashboard redirects to /login.",  # changed
}


def _initial_ac_list() -> list[AcEntry]:
    return [
        AcEntry(ac_id=ac_id, ac_text=text)
        for ac_id, text in _INITIAL_AC_TEXT_BY_ID.items()
    ]


def _drifted_ac_list() -> list[AcEntry]:
    return [
        AcEntry(ac_id=ac_id, ac_text=text)
        for ac_id, text in _DRIFTED_AC_TEXT_BY_ID.items()
    ]


def _make_plan_with_status(
    ac_list: list[AcEntry], status: str
) -> QABehavioralPlan:
    """Build a plan over ``ac_list`` whose ``plan_status`` is the given
    value. Story 4.1's ``generate_plan`` always returns ``"generated"`` —
    we mutate via model_copy to reach ``"human-reviewed"``.
    """
    base = generate_plan(story_id="story-4-2-test", ac_list=ac_list)
    if status == "generated":
        return base
    return base.model_copy(update={"plan_status": status})


def _canonical_registry() -> MarkerClassRegistry:
    """Registry containing exactly the ``plan-drift-detected`` marker class
    (literal frozenset; assertions are independent of the on-disk taxonomy
    per Story 1.4's enumeration test surface).
    """
    return MarkerClassRegistry(
        marker_classes=frozenset({PLAN_DRIFT_DETECTED_MARKER})
    )


# --------------------------------------------------------------------------- #
# AC-7 — pure-library cases                                                   #
# --------------------------------------------------------------------------- #


# 1
def test_surface_plan_drift_resets_plan_status_to_generated_from_human_reviewed() -> None:
    """AC-7 #1 + verbatim epic AC at epics.md line 1845 — even from
    ``human-reviewed`` the fresh plan returns to ``generated``."""
    parsed = _make_plan_with_status(_initial_ac_list(), "human-reviewed")
    new_ac_list = _drifted_ac_list()
    registry = _canonical_registry()

    result = surface_plan_drift(
        parsed_plan=parsed,
        ac_list=new_ac_list,
        story_id="story-4-2-test",
        registry=registry,
    )

    assert result.fresh_plan.plan_status == "generated"
    assert result.diagnostic_context.prior_plan_status == "human-reviewed"


# 2
def test_surface_plan_drift_resets_plan_status_to_generated_from_generated() -> None:
    """AC-7 #2 — reset is unconditional even when prior was ``generated``;
    diagnostic context preserves the prior state regardless."""
    parsed = _make_plan_with_status(_initial_ac_list(), "generated")
    new_ac_list = _drifted_ac_list()
    registry = _canonical_registry()

    result = surface_plan_drift(
        parsed_plan=parsed,
        ac_list=new_ac_list,
        story_id="story-4-2-test",
        registry=registry,
    )

    assert result.fresh_plan.plan_status == "generated"
    assert result.diagnostic_context.prior_plan_status == "generated"


# 3
def test_surface_plan_drift_fresh_plan_ac_hash_matches_current_ac_list() -> None:
    """AC-7 #3 — the regenerated plan's ``ac_hash`` matches
    ``compute_ac_hash(ac_list)`` byte-for-byte."""
    parsed = _make_plan_with_status(_initial_ac_list(), "human-reviewed")
    new_ac_list = _drifted_ac_list()
    registry = _canonical_registry()

    result = surface_plan_drift(
        parsed_plan=parsed,
        ac_list=new_ac_list,
        story_id="story-4-2-test",
        registry=registry,
    )

    assert result.fresh_plan.ac_hash == compute_ac_hash(new_ac_list)
    assert result.diagnostic_context.current_ac_hash == compute_ac_hash(new_ac_list)


# 4
def test_surface_plan_drift_diagnostic_context_carries_four_fields() -> None:
    """AC-7 #4 — all four required diagnostic-context fields are present
    and structurally distinct on a drift case."""
    parsed = _make_plan_with_status(_initial_ac_list(), "human-reviewed")
    new_ac_list = _drifted_ac_list()
    registry = _canonical_registry()

    result = surface_plan_drift(
        parsed_plan=parsed,
        ac_list=new_ac_list,
        story_id="sample-auto-001",
        registry=registry,
    )

    diag = result.diagnostic_context
    assert isinstance(diag, PlanDriftDiagnosticContext)
    assert diag.story_id == "sample-auto-001"
    assert diag.prior_plan_status == "human-reviewed"
    assert len(diag.prior_ac_hash) == 64
    assert len(diag.current_ac_hash) == 64
    # Drift case: prior and current hashes differ.
    assert diag.prior_ac_hash != diag.current_ac_hash
    # The prior hash mirrors the parsed plan's hash byte-for-byte.
    assert diag.prior_ac_hash == parsed.ac_hash


# 5
def test_surface_plan_drift_marker_record_carries_canonical_marker_class() -> None:
    """AC-7 #5 — ``marker_class`` equals the literal ``"plan-drift-detected"``
    byte-for-byte; ``PLAN_DRIFT_DETECTED_MARKER`` symbolic constant matches."""
    parsed = _make_plan_with_status(_initial_ac_list(), "generated")
    new_ac_list = _drifted_ac_list()
    registry = _canonical_registry()

    result = surface_plan_drift(
        parsed_plan=parsed,
        ac_list=new_ac_list,
        story_id="story-4-2-test",
        registry=registry,
    )

    assert PLAN_DRIFT_DETECTED_MARKER == "plan-drift-detected"
    assert isinstance(result.marker_record, PlanDriftEmissionRecord)
    assert result.marker_record.marker_class == "plan-drift-detected"
    assert result.marker_record.diagnostic_context is result.diagnostic_context


# 6
def test_surface_plan_drift_validates_marker_via_registry() -> None:
    """AC-7 #6 — registry rejection raises ``UnknownMarkerClass`` per
    Pattern 5; NO partial state is constructed (atomic-on-failure)."""
    parsed = _make_plan_with_status(_initial_ac_list(), "human-reviewed")
    new_ac_list = _drifted_ac_list()
    empty_registry = MarkerClassRegistry(marker_classes=frozenset())

    with pytest.raises(UnknownMarkerClass):
        surface_plan_drift(
            parsed_plan=parsed,
            ac_list=new_ac_list,
            story_id="story-4-2-test",
            registry=empty_registry,
        )


# 7
def test_surface_plan_drift_with_canonical_registry(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-7 #7 — calling with the on-disk-taxonomy-loaded registry returns
    successfully (no exception); the marker class is enumerated by Story 1.4."""
    parsed = _make_plan_with_status(_initial_ac_list(), "human-reviewed")
    new_ac_list = _drifted_ac_list()

    result = surface_plan_drift(
        parsed_plan=parsed,
        ac_list=new_ac_list,
        story_id="story-4-2-test",
        registry=runtime_marker_registry,
    )

    assert isinstance(result, PlanDriftEmission)
    assert result.fresh_plan.plan_status == "generated"


# 8
def test_surface_plan_drift_regenerated_entries_reflect_new_ac_list() -> None:
    """AC-7 #8 — regenerated entries reflect the new AC list (per-entry
    ``ac_id`` matches; ``assertion_shape`` carries the new AC text)."""
    parsed = _make_plan_with_status(_initial_ac_list(), "human-reviewed")
    new_ac_list = _drifted_ac_list()
    registry = _canonical_registry()

    result = surface_plan_drift(
        parsed_plan=parsed,
        ac_list=new_ac_list,
        story_id="story-4-2-test",
        registry=registry,
    )

    assert len(result.fresh_plan.entries) == len(new_ac_list)
    for entry, ac in zip(result.fresh_plan.entries, new_ac_list, strict=True):
        assert isinstance(entry, QABehavioralPlanEntry)
        assert entry.ac_id == ac.ac_id
        # Story 4.1's `_default_assertion_shape` collapses whitespace and
        # prefixes with `verify: ` — the regenerated entries reflect the
        # new AC text content.
        assert ac.ac_text.strip() in entry.assertion_shape


# --------------------------------------------------------------------------- #
# AC-7 — wrapper-side branch logic exercised via the seam                     #
# --------------------------------------------------------------------------- #


def _wrapper_dispatch_to_surface_plan_drift(
    *,
    story_doc_text: str,
    ac_list: list[AcEntry],
    story_id: str,
    registry: MarkerClassRegistry,
) -> PlanDriftEmission | None:
    """Mimic the QA wrapper's ``drift-suspected`` branch dispatch via the
    seam: call ``persist_or_reuse_plan`` first; ONLY on the
    ``"drift-suspected"`` branch does the wrapper compose
    ``surface_plan_drift``. Returns ``None`` on the other two branches.

    This helper is the unit-of-test for AC-7 #9, #10, #11 — the
    integration-level flow without the wrapper's actual file I/O.
    """
    parsed_plan, action = persist_or_reuse_plan(
        story_doc_text=story_doc_text, story_id=story_id, ac_list=ac_list
    )
    if action != "drift-suspected":
        return None
    return surface_plan_drift(
        parsed_plan=parsed_plan,
        ac_list=ac_list,
        story_id=story_id,
        registry=registry,
    )


def _story_doc_with_existing_plan(plan: QABehavioralPlan) -> str:
    """Compose a minimal story-doc text containing a ``## QA Behavioral Plan``
    section bounded by another H2 below."""
    body = render_plan_section(plan)
    return (
        "# Story 4.2 test\n\n"
        "## Acceptance Criteria\n\n"
        "AC-1: stub\n\n"
        "## QA Behavioral Plan\n\n"
        f"{body}\n"
        "## Tasks / Subtasks\n\n"
        "(none)\n"
    )


# 9
def test_no_drift_path_does_not_call_surface_plan_drift() -> None:
    """AC-7 #9 — when the parsed plan's hash matches
    ``compute_ac_hash(ac_list)``, ``persist_or_reuse_plan`` returns
    ``"reuse-existing"`` and the wrapper-side dispatch never reaches
    ``surface_plan_drift`` (the helper returns ``None``)."""
    initial = _initial_ac_list()
    plan = generate_plan(story_id="story-4-2-test", ac_list=initial)
    story_doc = _story_doc_with_existing_plan(plan)

    result = _wrapper_dispatch_to_surface_plan_drift(
        story_doc_text=story_doc,
        ac_list=initial,
        story_id="story-4-2-test",
        registry=_canonical_registry(),
    )

    assert result is None


# 10
def test_ac_reordering_does_not_trigger_drift() -> None:
    """AC-7 #10 — Story 4.1's order-stable hash decision (architecture.md
    line 1599): same AC content in different order yields the same hash;
    ``persist_or_reuse_plan`` returns ``"reuse-existing"``; the
    wrapper-side dispatch never reaches ``surface_plan_drift``."""
    initial = _initial_ac_list()
    plan = generate_plan(story_id="story-4-2-test", ac_list=initial)
    story_doc = _story_doc_with_existing_plan(plan)

    # Reorder ACs without changing content.
    reordered = [initial[2], initial[0], initial[1]]

    result = _wrapper_dispatch_to_surface_plan_drift(
        story_doc_text=story_doc,
        ac_list=reordered,
        story_id="story-4-2-test",
        registry=_canonical_registry(),
    )

    assert result is None


# 11
def test_substantive_ac_text_change_triggers_drift() -> None:
    """AC-7 #11 — substantive AC-text change yields a different hash;
    ``persist_or_reuse_plan`` returns ``"drift-suspected"``; the wrapper-
    side dispatch reaches ``surface_plan_drift`` and the two-channel
    emission is produced with the four-field diagnostic."""
    initial = _initial_ac_list()
    plan = _make_plan_with_status(initial, "human-reviewed")
    story_doc = _story_doc_with_existing_plan(plan)

    drifted = _drifted_ac_list()
    registry = _canonical_registry()

    result = _wrapper_dispatch_to_surface_plan_drift(
        story_doc_text=story_doc,
        ac_list=drifted,
        story_id="story-4-2-test",
        registry=registry,
    )

    assert result is not None
    assert result.fresh_plan.plan_status == "generated"
    assert result.fresh_plan.ac_hash == compute_ac_hash(drifted)
    assert result.diagnostic_context.prior_plan_status == "human-reviewed"
    assert result.diagnostic_context.prior_ac_hash == plan.ac_hash
    assert result.diagnostic_context.current_ac_hash == compute_ac_hash(drifted)
    assert result.marker_record.marker_class == "plan-drift-detected"


# --------------------------------------------------------------------------- #
# AC-7 — discipline + module-shape tests                                      #
# --------------------------------------------------------------------------- #


# 13
def test_qa_plan_drift_has_lf_line_endings(repo_root: pathlib.Path) -> None:
    """AC-7 #13 — LF-only line endings invariant per Stories 2.8 / 2.9 /
    3.5 / 4.1."""
    module_path = (
        repo_root
        / "tools"
        / "loud-fail-harness"
        / "src"
        / "loud_fail_harness"
        / "qa_plan_drift.py"
    )
    raw = module_path.read_bytes()
    assert b"\r" not in raw


# 14
def test_module_all_exports() -> None:
    """AC-7 #14 — ``qa_plan_drift.__all__`` carries the four required
    public-API symbols from AC-1."""
    expected = {
        "PLAN_DRIFT_DETECTED_MARKER",
        "PlanDriftDiagnosticContext",
        "PlanDriftEmission",
        "surface_plan_drift",
    }
    assert expected.issubset(set(qa_plan_drift.__all__))


# --------------------------------------------------------------------------- #
# AC-7 — schema validation tests                                              #
# --------------------------------------------------------------------------- #


def _qa_envelope_with_plan_drift() -> dict[str, Any]:
    return {
        "status": "pass",
        "artifacts": [
            "_bmad-output/qa-evidence/sample-001/run-2026-04-30-001/ac1-http-200.log"
        ],
        "findings": [],
        "rationale": (
            "AC-1 verified mechanically; drift detected; plan regenerated."
        ),
        "ac_results": [
            {
                "ac_id": "AC-1",
                "status": "pass",
                "assertions": ["HTTP POST /healthz returned status code 200"],
                "evidence_refs": [
                    {
                        "path": "_bmad-output/qa-evidence/sample-001/run-2026-04-30-001/ac1-http-200.log",
                        "tier": "tier-1-mechanical",
                    }
                ],
                "semantic_verification": "not_applicable",
            }
        ],
        "plan_drift": {
            "story_id": "sample-auto-001",
            "prior_plan_status": "human-reviewed",
            "prior_ac_hash": "0123456789abcdef0123456789abcdef"
            "0123456789abcdef0123456789abcdef",
            "current_ac_hash": "fedcba9876543210fedcba9876543210"
            "fedcba9876543210fedcba9876543210",
        },
    }


def _qa_envelope_without_plan_drift() -> dict[str, Any]:
    env = _qa_envelope_with_plan_drift()
    env.pop("plan_drift")
    return env


# 15
def test_plan_drift_envelope_field_validates_against_schema(
    envelope_schema: dict[str, Any],
) -> None:
    """AC-7 #15 — an envelope carrying a non-null ``plan_drift`` validates
    against the bumped schema."""
    envelope = _qa_envelope_with_plan_drift()
    errors = validate_envelope(envelope, envelope_schema)
    assert errors == [], errors


# 16
def test_plan_drift_envelope_field_absent_validates_against_schema(
    envelope_schema: dict[str, Any],
) -> None:
    """AC-7 #16 — an envelope WITHOUT ``plan_drift`` (no-drift run)
    validates against the bumped schema; the field is optional."""
    envelope = _qa_envelope_without_plan_drift()
    errors = validate_envelope(envelope, envelope_schema)
    assert errors == [], errors


# --------------------------------------------------------------------------- #
# AC-7 — bundle-render integration tests                                      #
# --------------------------------------------------------------------------- #


_CANONICAL_STORY_ID = "sample-auto-001"
_CANONICAL_RUN_ID = "run-2026-04-30-001"
_CANONICAL_GENERATED_AT = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)


def _seed_dispatch_log(
    logs_root: pathlib.Path,
    *,
    story_id: str,
    run_id: str,
    specialist: str,
    return_envelope: dict[str, Any],
    attempt_number: int = 1,
) -> pathlib.Path:
    """Mirrors the persist-dispatch-log shape from Story 2.6 (the
    assembler reads only the ``return_envelope`` field)."""
    log_path = (
        logs_root / story_id / run_id / "logs"
        / f"{specialist}-{attempt_number}.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "dispatched_specialist": specialist,
        "story_id": story_id,
        "attempt_number": attempt_number,
        "agent_definition_path": f"agents/{specialist}.md",
        "acceptance_criteria": [{"ac_id": "AC-1", "text": "stub"}],
        "dispatch_timestamp": "2026-04-30T12:00:00+00:00",
        "return_timestamp": "2026-04-30T12:01:00+00:00",
        "return_envelope": return_envelope,
    }
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return log_path


def _write_run_state(rs_path: pathlib.Path, story_id: str) -> pathlib.Path:
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "1.1",
        "story_id": story_id,
        "run_id": _CANONICAL_RUN_ID,
        "current_state": "done",
        "branch_name": f"bmad-automation/story/{story_id}",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": [],
        "active_markers": [],
        "cost_to_date_by_specialist": {},
    }
    rs_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return rs_path


def _canonical_dev_envelope(repo_root: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(
        (repo_root / "examples" / "envelopes" / "dev-pass.yaml").read_text(
            encoding="utf-8"
        )
    )


def _canonical_review_envelope(repo_root: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(
        (
            repo_root
            / "examples"
            / "envelopes"
            / "review-pass-three-layer.yaml"
        ).read_text(encoding="utf-8")
    )


def _seed_canonical_qa_evidence_files(repo_root: pathlib.Path) -> None:
    """Seed BOTH canonical evidence_ref files used by this module's
    fixtures so Story 6.6's bundle-render-time evidence-trace
    linkability validation resolves cleanly:

    * ``_bmad-output/qa-evidence/sample-001/run-2026-04-29-001/ac1-http-200.log``
      (qa-pass-ac1-tier1.yaml — no-drift fixture).
    * ``_bmad-output/qa-evidence/sample-001/run-2026-04-30-001/ac1-http-200.log``
      (qa-pass-with-plan-drift.yaml — drifted fixture).
    """
    for run_dir in ("run-2026-04-29-001", "run-2026-04-30-001"):
        evidence_path = (
            repo_root
            / "_bmad-output"
            / "qa-evidence"
            / "sample-001"
            / run_dir
            / "ac1-http-200.log"
        )
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("HTTP/1.1 200 OK\n", encoding="utf-8")


def _qa_with_plan_drift_envelope(repo_root: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(
        (
            repo_root
            / "examples"
            / "envelopes"
            / "qa-pass-with-plan-drift.yaml"
        ).read_text(encoding="utf-8")
    )


def _qa_without_plan_drift_envelope(repo_root: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(
        (
            repo_root / "examples" / "envelopes" / "qa-pass-ac1-tier1.yaml"
        ).read_text(encoding="utf-8")
    )


def _assemble_drifted_bundle(
    *,
    tmp_path: pathlib.Path,
    repo_root: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> pathlib.Path:
    rs_path = _write_run_state(
        tmp_path / "_bmad" / "automation" / "run-state.yaml",
        _CANONICAL_STORY_ID,
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_dispatch_log(
        logs_root,
        story_id=_CANONICAL_STORY_ID,
        run_id=_CANONICAL_RUN_ID,
        specialist="dev",
        return_envelope=_canonical_dev_envelope(repo_root),
    )
    _seed_dispatch_log(
        logs_root,
        story_id=_CANONICAL_STORY_ID,
        run_id=_CANONICAL_RUN_ID,
        specialist="review-bmad",
        return_envelope=_canonical_review_envelope(repo_root),
    )
    _seed_dispatch_log(
        logs_root,
        story_id=_CANONICAL_STORY_ID,
        run_id=_CANONICAL_RUN_ID,
        specialist="qa",
        return_envelope=_qa_with_plan_drift_envelope(repo_root),
    )
    bundle_root = tmp_path / "pr-bundles"
    # Story 6.6: seed canonical evidence files under tmp_path so the
    # bundle-render-time evidence-trace linkability validation resolves
    # cleanly. Pass repo_root=tmp_path to anchor validation there.
    _seed_canonical_qa_evidence_files(tmp_path)
    result = assemble_bundle(
        story_id=_CANONICAL_STORY_ID,
        run_id=_CANONICAL_RUN_ID,
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        marker_registry=runtime_marker_registry,
        generated_at=_CANONICAL_GENERATED_AT,
        repo_root=tmp_path,
    )
    return result.bundle_path


def _assemble_no_drift_bundle(
    *,
    tmp_path: pathlib.Path,
    repo_root: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> pathlib.Path:
    rs_path = _write_run_state(
        tmp_path / "_bmad" / "automation" / "run-state.yaml",
        _CANONICAL_STORY_ID,
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_dispatch_log(
        logs_root,
        story_id=_CANONICAL_STORY_ID,
        run_id=_CANONICAL_RUN_ID,
        specialist="dev",
        return_envelope=_canonical_dev_envelope(repo_root),
    )
    _seed_dispatch_log(
        logs_root,
        story_id=_CANONICAL_STORY_ID,
        run_id=_CANONICAL_RUN_ID,
        specialist="review-bmad",
        return_envelope=_canonical_review_envelope(repo_root),
    )
    _seed_dispatch_log(
        logs_root,
        story_id=_CANONICAL_STORY_ID,
        run_id=_CANONICAL_RUN_ID,
        specialist="qa",
        return_envelope=_qa_without_plan_drift_envelope(repo_root),
    )
    bundle_root = tmp_path / "pr-bundles"
    # Story 6.6: seed canonical evidence files under tmp_path so the
    # bundle-render-time evidence-trace linkability validation resolves
    # cleanly. Pass repo_root=tmp_path to anchor validation there.
    _seed_canonical_qa_evidence_files(tmp_path)
    result = assemble_bundle(
        story_id=_CANONICAL_STORY_ID,
        run_id=_CANONICAL_RUN_ID,
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        marker_registry=runtime_marker_registry,
        generated_at=_CANONICAL_GENERATED_AT,
        repo_root=tmp_path,
    )
    return result.bundle_path


# 17
def test_bundle_render_emits_marker_when_plan_drift_present(
    tmp_path: pathlib.Path,
    repo_root: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-7 #17 — non-null ``plan_drift`` causes the bundle to carry
    ``<!-- bmad-automation:marker plan-drift-detected -->`` exactly once
    + the ``### Plan drift detected`` H3 sub-section heading."""
    bundle_path = _assemble_drifted_bundle(
        tmp_path=tmp_path,
        repo_root=repo_root,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")

    marker_count = body.count(
        "<!-- bmad-automation:marker plan-drift-detected -->"
    )
    assert marker_count == 1, (
        f"expected exactly one plan-drift-detected marker comment, "
        f"got {marker_count}"
    )
    assert "### Plan drift detected" in body
    # Story 6.1 inversion: the walking-skeleton-bundle marker stops
    # emitting on post-6.1 runs because ``is_loud_fail_block_present()``
    # now returns True via the structural derivation. The plan-drift
    # marker emits independently (its rule is based on the QA
    # envelope's ``plan_drift`` field, not on any thickening flag).
    assert "<!-- bmad-automation:marker walking-skeleton-bundle -->" not in body


# 18
def test_bundle_render_silent_when_plan_drift_absent(
    tmp_path: pathlib.Path,
    repo_root: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-7 #18 — absent ``plan_drift`` causes the bundle to render
    NEITHER the marker comment NOR the ``### Plan drift detected``
    H3 sub-section (silent at the bundle-side path; structural-not-era-
    based emission rule)."""
    bundle_path = _assemble_no_drift_bundle(
        tmp_path=tmp_path,
        repo_root=repo_root,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")

    assert "bmad-automation:marker plan-drift-detected" not in body
    assert "### Plan drift detected" not in body


# --------------------------------------------------------------------------- #
# AC-7 — canonical-fixture regeneration baseline (parallel to Story 3.4)      #
# --------------------------------------------------------------------------- #


# 12
def test_canonical_plan_drift_bundle_fixture_matches_assembler_output(
    tmp_path: pathlib.Path,
    repo_root: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-7 #12 — the committed canonical fixture
    ``examples/pr-bundles/pr-bundle-plan-drift.md`` matches the assembler's
    output byte-for-byte for a fixed input envelope set
    (regeneration-baseline pattern from Story 3.4)."""
    fixture_path = (
        repo_root / "examples" / "pr-bundles" / "pr-bundle-plan-drift.md"
    )
    if not fixture_path.exists():
        pytest.fail(
            "examples/pr-bundles/pr-bundle-plan-drift.md is missing from the "
            "repository — the fixture must be committed; regenerate it via "
            "assemble_bundle against the canonical envelope corpus including "
            "qa-pass-with-plan-drift.yaml"
        )
    fixture_body = fixture_path.read_text(encoding="utf-8")
    body_after_header = re.sub(
        r"^<!--.*?-->\s*", "", fixture_body, count=1, flags=re.DOTALL
    )

    bundle_path = _assemble_drifted_bundle(
        tmp_path=tmp_path,
        repo_root=repo_root,
        runtime_marker_registry=runtime_marker_registry,
    )
    assembled_body = bundle_path.read_text(encoding="utf-8")

    assert assembled_body == body_after_header, (
        "canonical plan-drift bundle fixture must match assembler output "
        "byte-for-byte (modulo contract-header strip); regenerate the "
        "fixture if the assembler's rendering intentionally changed"
    )
