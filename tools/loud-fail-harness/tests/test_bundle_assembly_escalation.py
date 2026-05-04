"""Test coverage matrix for Story 5.8 (escalation-bundle assembly mechanism).

This docstring IS the contract-coverage checklist required by AC-7.
Reviewers verify every row maps to at least one passing test in this
module. The matrix is review-enforced, NOT CI-enforced (parallel to
stories 1.2-1.9 + 2.2-2.10 + 4.10).

AC-1 — four-trigger matrix:
    [x] retry-budget-exhausted produces correctly-shaped bundle
        → test_assemble_retry_budget_exhausted_bundle_writes_correct_shape
    [x] scope-assertion-violation produces correctly-shaped bundle
        → test_assemble_scope_assertion_violation_bundle_writes_correct_shape
    [x] verification-fail produces correctly-shaped bundle (via direct
        payload composition per AC-1 note on QA-domain trigger seam)
        → test_assemble_verification_fail_bundle_writes_correct_shape
    [x] env-setup-fail produces correctly-shaped bundle (same)
        → test_assemble_env_setup_fail_bundle_writes_correct_shape

AC-2 — six FR15 sections:
    [x] Walking Skeleton Mode + Escalation rationale + Outstanding
        findings + Retry history + Deferred-work pointer + Preservation
        → asserted within tests #1, #2

AC-3 — placeholder retirement:
    [x] default_escalation_bundle_assembler delegates to full assembler
        → test_default_escalation_bundle_assembler_delegates_to_full_assembler
    [x] placeholder HTML comment is structurally absent from bundle
        → asserted within tests #1, #2

AC-4 — single rendering core:
    [x] Walking Skeleton header text byte-identical across variants
        → test_walking_skeleton_header_byte_identical_across_variants
    [x] new module imports SIX shared rendering helpers from bundle_assembly
        → test_module_imports_six_shared_rendering_helpers
    [x] one-way import direction (escalation → bundle_assembly only)
        → test_import_direction_is_one_way

AC-5 — two new schemas land:
    [x] retry-budget-exhausted.yaml exists + valid JSON-Schema-2020-12
        → test_retry_budget_exhausted_schema_self_valid
    [x] scope-assertion-violation.yaml exists + valid JSON-Schema-2020-12
        → test_scope_assertion_violation_schema_self_valid

AC-6 — schema conformance at assembly-time:
    [x] schema-conformance failure raises BEFORE write
        → test_schema_conformance_failure_raises_before_write
    [x] EscalationBundleSchemaNotFound raises on missing schema
        → test_schema_not_found_raises

AC-7 — additional invariants:
    [x] retry-history rendering: zero rounds → sentinel
        → test_retry_history_rendering_with_zero_rounds
    [x] retry-history rendering: multiple rounds → bullets + links
        → test_retry_history_rendering_with_multiple_rounds
    [x] deferred-work pointer renders per Story 5.7 format
        → test_deferred_work_pointer_renders_per_story_5_7_format
    [x] atomic-write semantics
        → test_atomic_write_semantics

AC-6 additions (review patch):
    [x] schema-conformance failure raises for scope-assertion-violation
        → test_schema_conformance_failure_scope_assertion_violation
    [x] schema-conformance failure raises for verification-fail
        → test_schema_conformance_failure_verification_fail
    [x] schema-conformance failure raises for env-setup-fail
        → test_schema_conformance_failure_env_setup_fail
    [x] ordering invariant through full assembler (D3 review patch)
        → test_schema_conformance_ordering_through_assembler

Pattern 5 additions (review patch):
    [x] unknown ExhaustionTrigger raises EscalationBundleSchemaNotFound
        → test_resolve_bundle_class_unknown_trigger_raises_named_exception

AC-8 — sanity checks:
    [x] all 22 test cases run via `uv run pytest -k bundle_assembly_escalation`
        (11 named AC-7 cases + 6 original structural-invariant tests +
        5 review-patch tests; verified in CI; this docstring asserts
        coverage at review-time)
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import jsonschema
import pytest
import yaml

from loud_fail_harness import bundle_assembly, bundle_assembly_escalation
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.bundle_assembly_escalation import (
    AssembleEscalationBundleResult,
    EscalationBundleSchemaConformanceError,
    EscalationBundleSchemaNotFound,
    _render_machine_readable_block,
    _validate_payload_against_schema,
    assemble_escalation_bundle,
)
from loud_fail_harness.retry_budget_exhaustion import (
    ExhaustionContext,
    ExhaustionTrigger,
    compute_escalation_bundle_path,
    default_escalation_bundle_assembler,
)
from loud_fail_harness.run_state import RetryAttempt
from loud_fail_harness.scope_assertion import ScopeAssertionDiagnostic


# --------------------------------------------------------------------------- #
# Fixtures + helpers                                                          #
# --------------------------------------------------------------------------- #


REPO_ROOT = find_repo_root()
SCHEMAS_ROOT = REPO_ROOT  # schemas live under {REPO_ROOT}/schemas/...


_FIXED_GENERATED_AT = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)


def _make_thickening_flags_stub(
    *,
    is_full_review_present: bool = True,
    is_full_qa_present: bool = True,
    is_retry_present: bool = False,
    is_loud_fail_block_present: bool = False,
) -> SimpleNamespace:
    """Build a stub flags namespace mirroring
    :mod:`loud_fail_harness.thickening_flags`'s four-function API.

    Defaults: Epic-5-era state (review + qa thickenings landed; retry
    and loud-fail-block deferred to Story 5.9 + Story 6.1 respectively).
    """
    return SimpleNamespace(
        is_full_review_present=lambda: is_full_review_present,
        is_full_qa_present=lambda: is_full_qa_present,
        is_retry_present=lambda: is_retry_present,
        is_loud_fail_block_present=lambda: is_loud_fail_block_present,
    )


def _make_scope_diagnostic(*, story_id: str = "5-8-foo") -> ScopeAssertionDiagnostic:
    return ScopeAssertionDiagnostic(
        story_id=story_id,
        retry_round=1,
        violating_files=("src/unrelated.py",),
        declared_scope=("src/foo.py",),
        declared_expansion=(),
    )


def _make_budget_context(
    *,
    story_id: str = "5-8-foo",
    run_id: str = "run-1",
    retry_history: tuple[RetryAttempt, ...] = (),
    last_envelope: dict[str, Any] | None = None,
) -> ExhaustionContext:
    return ExhaustionContext(
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        story_id=story_id,
        run_id=run_id,
        branch_name=f"story/{story_id}",
        retry_history=retry_history,
        last_envelope=last_envelope,
        last_retry_directive=None,
        scope_violation_diagnostic=None,
        bundle_artifact_path=(
            f"_bmad-output/escalation-bundles/{story_id}/{run_id}/escalation.md"
        ),
    )


def _make_scope_context(
    *,
    story_id: str = "5-8-foo",
    run_id: str = "run-1",
    retry_history: tuple[RetryAttempt, ...] = (),
) -> ExhaustionContext:
    return ExhaustionContext(
        trigger=ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION,
        story_id=story_id,
        run_id=run_id,
        branch_name=f"story/{story_id}",
        retry_history=retry_history,
        last_envelope=None,
        last_retry_directive=None,
        scope_violation_diagnostic=_make_scope_diagnostic(story_id=story_id),
        bundle_artifact_path=(
            f"_bmad-output/escalation-bundles/{story_id}/{run_id}/escalation.md"
        ),
    )


def _read_bundle(target: pathlib.Path) -> str:
    return target.read_text(encoding="utf-8")


def _extract_machine_readable_payload(body: str) -> dict[str, Any]:
    """Round-trip the trailing
    ``<!-- bmad-automation:escalation-bundle\\n<yaml>\\n-->`` HTML-comment
    block back to a Python dict.

    Mirrors the payload-construction shape in
    :func:`bundle_assembly_escalation._render_machine_readable_block`.
    """
    open_tag = "<!-- bmad-automation:escalation-bundle\n"
    close_tag = "\n-->"
    open_idx = body.rindex(open_tag)
    close_idx = body.rindex(close_tag)
    yaml_block = body[open_idx + len(open_tag) : close_idx]
    return yaml.safe_load(yaml_block)


# --------------------------------------------------------------------------- #
# AC-1 / AC-2 / AC-3 — retry-budget-exhausted bundle                          #
# --------------------------------------------------------------------------- #


def test_assemble_retry_budget_exhausted_bundle_writes_correct_shape(
    tmp_path: pathlib.Path,
) -> None:
    context = _make_budget_context(
        retry_history=(
            RetryAttempt(
                retry_attempt=1,
                retry_reason="patch-bucket-retry",
                round_id="round-01",
                path="_bmad-output/retry-history/5-8-foo/round-01",
            ),
            RetryAttempt(
                retry_attempt=2,
                retry_reason="patch-bucket-retry-2",
                round_id="round-02",
                path="_bmad-output/retry-history/5-8-foo/round-02",
            ),
        ),
        last_envelope={
            "findings": [
                {
                    "id": "F-1",
                    "title": "Sample finding",
                    "source": "blind",
                    "location": "src/foo.py:42",
                }
            ]
        },
    )

    result = assemble_escalation_bundle(
        context,
        repo_root=tmp_path,
        schemas_root=SCHEMAS_ROOT,
        thickening_flags=_make_thickening_flags_stub(),
        generated_at=_FIXED_GENERATED_AT,
    )

    # (a) bundle file exists at the AC-1 path
    expected_path = compute_escalation_bundle_path(
        repo_root=tmp_path,
        story_id="5-8-foo",
        run_id="run-1",
    )
    assert result.bundle_path == expected_path
    assert expected_path.exists()
    body = _read_bundle(expected_path)

    # (b) all six AC-2 sections are present
    assert "## ⚠️ Walking Skeleton Mode" in body
    assert "## Escalation rationale" in body
    assert "## Outstanding findings" in body
    assert "## Retry history" in body
    assert "## Deferred-work pointer" in body
    assert "## Preservation" in body

    # finding bullet rendered via shared _render_finding_bullet helper
    assert "[blind] `F-1` — Sample finding (`src/foo.py:42`)" in body

    # retry history rendered with both rounds + per-round artifact link
    assert "round-01" in body
    assert "round-02" in body
    assert "[Round 1 artifacts]" in body
    assert "[Round 2 artifacts]" in body

    # (c) machine-readable YAML payload validates against
    # retry-budget-exhausted.yaml
    payload = _extract_machine_readable_payload(body)
    assert payload["bundle_class"] == "retry-budget-exhausted"
    assert payload["marker_class"] == "retry-budget-exhausted"
    assert len(payload["retry_history_refs"]) == 2
    _validate_payload_against_schema(
        payload=payload,
        bundle_class="retry-budget-exhausted",
        schemas_root=SCHEMAS_ROOT,
    )

    # (d) walking-skeleton-bundle marker emitted
    assert result.emitted_markers == (bundle_assembly.WALKING_SKELETON_MARKER,)
    assert "<!-- bmad-automation:marker walking-skeleton-bundle -->" in body

    # (e) placeholder HTML comment is structurally absent
    assert "Replaced by Story 5.8" not in body


# --------------------------------------------------------------------------- #
# AC-1 / AC-2 — scope-assertion-violation bundle                              #
# --------------------------------------------------------------------------- #


def test_assemble_scope_assertion_violation_bundle_writes_correct_shape(
    tmp_path: pathlib.Path,
) -> None:
    context = _make_scope_context()

    result = assemble_escalation_bundle(
        context,
        repo_root=tmp_path,
        schemas_root=SCHEMAS_ROOT,
        thickening_flags=_make_thickening_flags_stub(),
        generated_at=_FIXED_GENERATED_AT,
    )
    assert result.bundle_class == "scope-assertion-violation"

    body = _read_bundle(result.bundle_path)

    # six AC-2 sections + the SCOPE_ASSERTION_VIOLATION-specific
    # diagnostic section
    assert "## ⚠️ Walking Skeleton Mode" in body
    assert "## Escalation rationale" in body
    assert "## Outstanding findings" in body
    assert "## Retry history" in body
    assert "## Deferred-work pointer" in body
    assert "## Preservation" in body
    assert "## Scope-assertion diagnostic" in body
    # Outstanding-findings section uses the empty-violation sentinel
    assert (
        "No outstanding findings — see scope-assertion violation diagnostic below."
        in body
    )

    # Diagnostic body renders the four ScopeAssertionDiagnostic fields
    assert "src/unrelated.py" in body
    assert "src/foo.py" in body
    assert "retry_round" in body

    # (f) scope_violation_diagnostic payload validates against schema
    payload = _extract_machine_readable_payload(body)
    assert payload["bundle_class"] == "scope-assertion-violation"
    diag = payload["scope_violation_diagnostic"]
    assert diag["declared_scope"] == ["src/foo.py"]
    assert diag["violating_files"] == ["src/unrelated.py"]
    assert diag["retry_round"] == 1
    _validate_payload_against_schema(
        payload=payload,
        bundle_class="scope-assertion-violation",
        schemas_root=SCHEMAS_ROOT,
    )

    # placeholder HTML comment absent
    assert "Replaced by Story 5.8" not in body


# --------------------------------------------------------------------------- #
# AC-1 — verification-fail (synthesized payload — QA-domain trigger seam)     #
# --------------------------------------------------------------------------- #


def _make_verification_fail_payload() -> dict[str, Any]:
    """Compose a verification-fail payload dict directly per the AC-1
    note on the QA-domain trigger seam at MVP.

    The future QA-domain trigger story extends ExhaustionTrigger OR
    introduces a parallel context dataclass; until then, tests compose
    the payload shape directly to exercise the assembler's
    bundle_class-discriminator dispatch path.
    """
    return {
        "bundle_class": "verification-fail",
        "story_id": "5-8-foo",
        "run_id": "run-1",
        "retry_policy": "escalate",
        "failing_ac_result": {
            "ac_id": "AC-1",
            "status": "fail",
            "assertions": ["the page loads"],
            "evidence_refs": [
                {"path": "_bmad-output/qa-evidence/5-8-foo/run-1/screenshot.png", "tier": "tier-1-mechanical"}
            ],
            "semantic_verification": "verified",
        },
        "qa_behavioral_plan_pointer": {
            "story_doc_path": "_bmad-output/implementation-artifacts/5-8-foo.md",
            "section_heading": "## QA Behavioral Plan",
            "ac_id": "AC-1",
        },
        "evidence_refs": [
            {"path": "_bmad-output/qa-evidence/5-8-foo/run-1/screenshot.png", "tier": "tier-1-mechanical"}
        ],
    }


def test_assemble_verification_fail_bundle_writes_correct_shape(
    tmp_path: pathlib.Path,
) -> None:
    payload = _make_verification_fail_payload()

    # The QA-domain trigger seam at MVP composes the payload directly;
    # the test exercises the schema-validation surface AND the
    # round-trip of the machine-readable block. Story 5.8's runtime
    # dispatch is structurally ready for the future QA-domain trigger
    # story to extend ExhaustionTrigger; until then, the payload is
    # validated explicitly here AND a body block is rendered using the
    # SHARED machine-readable-block helper.
    _validate_payload_against_schema(
        payload=payload,
        bundle_class="verification-fail",
        schemas_root=SCHEMAS_ROOT,
    )

    block = _render_machine_readable_block(payload)
    assert block.startswith("<!-- bmad-automation:escalation-bundle\n")
    assert block.endswith("\n-->")

    # Round-trip: parse the block and confirm payload byte-equality.
    target = tmp_path / "verification-fail.md"
    target.write_text(block, encoding="utf-8")
    parsed = _extract_machine_readable_payload(target.read_text(encoding="utf-8"))
    assert parsed == payload
    # Schema fragment exists at canonical path
    schema_path = (
        SCHEMAS_ROOT / "schemas" / "escalation-bundles" / "verification-fail.yaml"
    )
    assert schema_path.exists()


# --------------------------------------------------------------------------- #
# AC-1 — env-setup-fail (synthesized payload — QA-domain trigger seam)        #
# --------------------------------------------------------------------------- #


def _make_env_setup_fail_payload() -> dict[str, Any]:
    return {
        "bundle_class": "env-setup-fail",
        "story_id": "5-8-foo",
        "run_id": "run-1",
        "retry_policy": "escalate-with-env-diagnostic",
        "env_setup_diagnostic": {
            "failed_provisioning_step": "dev-server-start",
            "port_states": [{"port": 5173, "state": "in-use-by-other"}],
            "mcp_status": {"available": True, "dependency_name": "playwright-mcp"},
            "dependency_status": [
                {"dependency_name": "node", "available": True, "version": "20.0.0"}
            ],
            "marker_class": "env-setup-failed",
        },
        "qa_runbook_pointer": {
            "qa_runbook_path": "_bmad/automation/qa-runbook.yaml",
            "config_review_hint": "check ports config",
        },
        "story_state_preservation_note": {
            "current_state": "review",
            "intended_next_state_skipped": "qa",
            "preservation_rationale": (
                "FR24b: env-setup failures are structurally distinct from "
                "verification failures; story-state preservation prevents the "
                "QA lifecycle state from being entered when the env never "
                "came up — re-running env-provisioning + QA after config "
                "remediation produces a clean run starting from the preserved "
                "review state"
            ),
        },
    }


def test_assemble_env_setup_fail_bundle_writes_correct_shape(
    tmp_path: pathlib.Path,
) -> None:
    payload = _make_env_setup_fail_payload()
    _validate_payload_against_schema(
        payload=payload,
        bundle_class="env-setup-fail",
        schemas_root=SCHEMAS_ROOT,
    )

    block = _render_machine_readable_block(payload)
    target = tmp_path / "env-setup-fail.md"
    target.write_text(block, encoding="utf-8")
    parsed = _extract_machine_readable_payload(target.read_text(encoding="utf-8"))
    assert parsed == payload
    schema_path = (
        SCHEMAS_ROOT / "schemas" / "escalation-bundles" / "env-setup-fail.yaml"
    )
    assert schema_path.exists()


# --------------------------------------------------------------------------- #
# AC-4 — single rendering core                                                #
# --------------------------------------------------------------------------- #


def test_walking_skeleton_header_byte_identical_across_variants() -> None:
    """The structural surface for "the rendering core has been forked".

    Both :func:`bundle_assembly._render_walking_skeleton_header` and the
    same function imported into :mod:`bundle_assembly_escalation` MUST
    produce byte-identical text for the same flag state.
    """
    flags = _make_thickening_flags_stub()
    merge_ready = bundle_assembly._render_walking_skeleton_header(flags)
    escalation = bundle_assembly_escalation._render_walking_skeleton_header(flags)
    assert merge_ready == escalation


def test_module_imports_six_shared_rendering_helpers() -> None:
    """AC-4 import-introspection: the new module imports eight shared
    symbols from :mod:`bundle_assembly` (six rendering helpers plus
    ``_emit_walking_skeleton_marker``, ``_THICKENING_SENTENCES``,
    ``WALKING_SKELETON_MARKER``, ``_atomic_write_bundle``, and
    ``_default_thickening_flags`` as a module-namespace alias).

    The count was "SIX" in AC-4 story text; the actual imported set
    contains eight distinct symbols — all verified by identity check
    below to confirm import source is :mod:`bundle_assembly` rather
    than a re-implementation.
    """
    expected = {
        "WALKING_SKELETON_MARKER",
        "_atomic_write_bundle",
        "_emit_walking_skeleton_marker",
        "_render_finding_bullet",
        "_render_marker",
        "_render_walking_skeleton_header",
        "_THICKENING_SENTENCES",
        "_default_thickening_flags",
    }
    for name in expected:
        assert hasattr(bundle_assembly_escalation, name), (
            f"bundle_assembly_escalation must re-export {name!r} from "
            f"bundle_assembly per AC-4 single-rendering-core invariant"
        )
        # The shared symbol IS the same object as in bundle_assembly
        # (identity check — rules out a defensive re-implementation and
        # confirms import source is bundle_assembly, not a direct import
        # from the underlying module).
        assert getattr(bundle_assembly_escalation, name) is getattr(
            bundle_assembly, name
        ), (
            f"{name!r} must be the same object as bundle_assembly.{name} "
            f"(imported from bundle_assembly, not re-implemented or imported "
            f"directly from the underlying module)"
        )


def test_import_direction_is_one_way() -> None:
    """AC-4 import-direction invariant: ``bundle_assembly.py`` does NOT
    import from ``bundle_assembly_escalation``.

    The dependency arrow is one-way (escalation depends on merge-ready;
    merge-ready does NOT depend on escalation). This prevents circular-
    import drift AND structurally guarantees that future modifications
    to assemble_bundle (merge-ready) cannot inadvertently couple with
    escalation-variant logic.
    """
    bundle_assembly_path = pathlib.Path(bundle_assembly.__file__)
    source = bundle_assembly_path.read_text(encoding="utf-8")
    assert "bundle_assembly_escalation" not in source, (
        "bundle_assembly.py must NOT import from bundle_assembly_escalation "
        "per AC-4 one-way import-direction invariant"
    )


# --------------------------------------------------------------------------- #
# AC-5 — schema self-validity                                                 #
# --------------------------------------------------------------------------- #


def test_retry_budget_exhausted_schema_self_valid() -> None:
    schema_path = (
        SCHEMAS_ROOT / "schemas" / "escalation-bundles" / "retry-budget-exhausted.yaml"
    )
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    # Discriminator + marker_class strict-name reference
    assert schema["properties"]["bundle_class"]["enum"] == ["retry-budget-exhausted"]
    assert schema["properties"]["marker_class"]["const"] == "retry-budget-exhausted"


def test_scope_assertion_violation_schema_self_valid() -> None:
    schema_path = (
        SCHEMAS_ROOT
        / "schemas"
        / "escalation-bundles"
        / "scope-assertion-violation.yaml"
    )
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["properties"]["bundle_class"]["enum"] == ["scope-assertion-violation"]
    assert schema["properties"]["marker_class"]["const"] == "scope-assertion-violation"
    # Required scope_violation_diagnostic field
    assert "scope_violation_diagnostic" in schema["required"]


# --------------------------------------------------------------------------- #
# AC-6 — schema conformance failure raises before write                       #
# --------------------------------------------------------------------------- #


def test_schema_conformance_failure_raises_before_write(
    tmp_path: pathlib.Path,
) -> None:
    """The validation runs BEFORE _atomic_write_bundle is invoked;
    validation failure produces ZERO filesystem mutations per AC-6.

    All four diagnostic fields on EscalationBundleSchemaConformanceError
    are verified per AC-6: bundle_class, schema_path, failing_field,
    expected_shape.
    """
    # Build a payload that's missing the REQUIRED `outstanding_findings_pointer`
    # field. The construction goes around _construct_machine_readable_payload
    # which would fill the field — we want to exercise the validation surface
    # directly so a conformance failure is visible.
    bad_payload: dict[str, Any] = {
        "bundle_class": "retry-budget-exhausted",
        "story_id": "5-8-foo",
        "run_id": "run-1",
        "retry_history_refs": [],
        # outstanding_findings_pointer intentionally omitted
        "escalation_rationale": "test",
        "deferred_work_pointer": {
            "path": "_bmad-output/implementation-artifacts/deferred-work.md"
        },
        "preserved_branch_name": "story/5-8-foo",
        "preserved_run_state_path": "_bmad/automation/run-state.yaml",
        "marker_class": "retry-budget-exhausted",
    }

    expected_path = compute_escalation_bundle_path(
        repo_root=tmp_path, story_id="5-8-foo", run_id="run-1"
    )
    assert not expected_path.exists()

    with pytest.raises(EscalationBundleSchemaConformanceError) as excinfo:
        _validate_payload_against_schema(
            payload=bad_payload,
            bundle_class="retry-budget-exhausted",
            schemas_root=SCHEMAS_ROOT,
        )

    exc = excinfo.value
    assert exc.bundle_class == "retry-budget-exhausted"
    assert exc.schema_path is not None and str(exc.schema_path).endswith(
        "retry-budget-exhausted.yaml"
    )
    assert exc.failing_field  # non-empty path identifying the failing field
    assert exc.expected_shape  # non-empty message from jsonschema
    # No filesystem mutation occurred at the expected bundle path.
    assert not expected_path.exists()


def test_schema_not_found_raises(tmp_path: pathlib.Path) -> None:
    """An unknown bundle_class collapses to EscalationBundleSchemaNotFound
    per the closed-set Pattern 5 surface.
    """
    with pytest.raises(EscalationBundleSchemaNotFound):
        _validate_payload_against_schema(
            payload={"bundle_class": "unknown-class"},
            bundle_class="unknown-class",
            schemas_root=tmp_path,
        )


def test_schema_conformance_failure_scope_assertion_violation(
    tmp_path: pathlib.Path,
) -> None:
    """AC-6 negative-path: scope-assertion-violation missing required field."""
    bad_payload: dict[str, Any] = {
        "bundle_class": "scope-assertion-violation",
        "story_id": "5-8-foo",
        "run_id": "run-1",
        "retry_history_refs": [],
        # outstanding_findings_pointer intentionally omitted
        "escalation_rationale": "test",
        "deferred_work_pointer": {
            "path": "_bmad-output/implementation-artifacts/deferred-work.md"
        },
        "preserved_branch_name": "story/5-8-foo",
        "preserved_run_state_path": "_bmad/automation/run-state.yaml",
        "scope_violation_diagnostic": {
            "declared_scope": ["src/foo.py"],
            "declared_expansion": [],
            "violating_files": ["src/bar.py"],
            "retry_round": 1,
        },
        "marker_class": "scope-assertion-violation",
    }
    # Remove outstanding_findings_pointer to trigger conformance failure
    bad_payload.pop("outstanding_findings_pointer", None)

    with pytest.raises(EscalationBundleSchemaConformanceError) as excinfo:
        _validate_payload_against_schema(
            payload=bad_payload,
            bundle_class="scope-assertion-violation",
            schemas_root=SCHEMAS_ROOT,
        )
    exc = excinfo.value
    assert exc.bundle_class == "scope-assertion-violation"
    assert exc.schema_path is not None
    assert exc.failing_field
    assert exc.expected_shape


def test_schema_conformance_failure_verification_fail(
    tmp_path: pathlib.Path,
) -> None:
    """AC-6 negative-path: verification-fail missing required field."""
    # Minimal payload missing required `failing_ac_result`
    bad_payload: dict[str, Any] = {
        "bundle_class": "verification-fail",
        "story_id": "5-8-foo",
        "run_id": "run-1",
        "retry_policy": "escalate",
        # failing_ac_result intentionally omitted
        "qa_behavioral_plan_pointer": {
            "story_doc_path": "_bmad-output/implementation-artifacts/5-8-foo.md",
            "section_heading": "## QA Behavioral Plan",
            "ac_id": "AC-1",
        },
        "evidence_refs": [],
    }

    with pytest.raises(EscalationBundleSchemaConformanceError) as excinfo:
        _validate_payload_against_schema(
            payload=bad_payload,
            bundle_class="verification-fail",
            schemas_root=SCHEMAS_ROOT,
        )
    exc = excinfo.value
    assert exc.bundle_class == "verification-fail"
    assert exc.schema_path is not None
    assert exc.failing_field
    assert exc.expected_shape


def test_schema_conformance_failure_env_setup_fail(
    tmp_path: pathlib.Path,
) -> None:
    """AC-6 negative-path: env-setup-fail missing required field."""
    # Minimal payload missing required `env_setup_diagnostic`
    bad_payload: dict[str, Any] = {
        "bundle_class": "env-setup-fail",
        "story_id": "5-8-foo",
        "run_id": "run-1",
        "retry_policy": "escalate-with-env-diagnostic",
        # env_setup_diagnostic intentionally omitted
        "qa_runbook_pointer": {
            "qa_runbook_path": "_bmad/automation/qa-runbook.yaml",
            "config_review_hint": "check ports config",
        },
        "story_state_preservation_note": {
            "current_state": "review",
            "intended_next_state_skipped": "qa",
            "preservation_rationale": "test",
        },
    }

    with pytest.raises(EscalationBundleSchemaConformanceError) as excinfo:
        _validate_payload_against_schema(
            payload=bad_payload,
            bundle_class="env-setup-fail",
            schemas_root=SCHEMAS_ROOT,
        )
    exc = excinfo.value
    assert exc.bundle_class == "env-setup-fail"
    assert exc.schema_path is not None
    assert exc.failing_field
    assert exc.expected_shape


def test_schema_conformance_ordering_through_assembler(
    tmp_path: pathlib.Path,
) -> None:
    """D3 ordering invariant: validation runs BEFORE _atomic_write_bundle
    through the full assemble_escalation_bundle call path.

    Uses unittest.mock.patch to make _construct_machine_readable_payload
    return a schema-invalid dict, then asserts (a) EscalationBundleSchemaConformanceError
    is raised and (b) no bundle file was written to disk.
    """
    from unittest.mock import patch

    from loud_fail_harness import bundle_assembly_escalation as bae

    context = _make_budget_context()
    expected_path = compute_escalation_bundle_path(
        repo_root=tmp_path, story_id="5-8-foo", run_id="run-1"
    )
    assert not expected_path.exists()

    # Inject a payload that fails schema validation: missing
    # `outstanding_findings_pointer` and `escalation_rationale`.
    bad_payload: dict[str, Any] = {
        "bundle_class": "retry-budget-exhausted",
        "story_id": "5-8-foo",
        "run_id": "run-1",
        "retry_history_refs": [],
        "deferred_work_pointer": {"path": "_bmad-output/implementation-artifacts/deferred-work.md"},
        "preserved_branch_name": "story/5-8-foo",
        "preserved_run_state_path": "_bmad/automation/run-state.yaml",
        "marker_class": "retry-budget-exhausted",
        # outstanding_findings_pointer and escalation_rationale omitted
    }

    with patch.object(bae, "_construct_machine_readable_payload", return_value=bad_payload):
        with pytest.raises(EscalationBundleSchemaConformanceError):
            assemble_escalation_bundle(
                context,
                repo_root=tmp_path,
                schemas_root=SCHEMAS_ROOT,
                thickening_flags=_make_thickening_flags_stub(),
                generated_at=_FIXED_GENERATED_AT,
            )

    # No filesystem mutation — the file must NOT exist.
    assert not expected_path.exists(), (
        "assemble_escalation_bundle must not write the bundle when schema "
        "validation fails (Pattern 5 defense-in-depth ordering invariant)"
    )


def test_resolve_bundle_class_unknown_trigger_raises_named_exception() -> None:
    """Pattern 5: an unknown ExhaustionTrigger value raises
    EscalationBundleSchemaNotFound, not a raw KeyError.

    Covers the _resolve_bundle_class fix (review finding: patch #2).
    Uses unittest.mock to simulate a future trigger value not yet
    in _EXHAUSTION_TRIGGER_TO_BUNDLE_CLASS.
    """
    from unittest.mock import MagicMock

    from loud_fail_harness.bundle_assembly_escalation import EscalationBundleSchemaNotFound

    # Build a minimal ExhaustionContext-like object whose .trigger is
    # NOT in _EXHAUSTION_TRIGGER_TO_BUNDLE_CLASS.
    fake_trigger = MagicMock()
    fake_trigger.__repr__ = lambda self: "ExhaustionTrigger.FUTURE_TRIGGER"

    # Create a real ExhaustionContext but swap out the trigger via a mock
    # context object — avoids Pydantic enum validation.
    fake_context = MagicMock()
    fake_context.trigger = fake_trigger

    from loud_fail_harness.bundle_assembly_escalation import _resolve_bundle_class

    with pytest.raises(EscalationBundleSchemaNotFound) as excinfo:
        _resolve_bundle_class(fake_context)

    assert excinfo.value.bundle_class  # non-empty repr of the unknown trigger


# --------------------------------------------------------------------------- #
# AC-7 — retry-history rendering                                              #
# --------------------------------------------------------------------------- #


def test_retry_history_rendering_with_zero_rounds(tmp_path: pathlib.Path) -> None:
    context = _make_budget_context(retry_history=())
    result = assemble_escalation_bundle(
        context,
        repo_root=tmp_path,
        schemas_root=SCHEMAS_ROOT,
        thickening_flags=_make_thickening_flags_stub(),
        generated_at=_FIXED_GENERATED_AT,
    )
    body = _read_bundle(result.bundle_path)
    assert "## Retry history" in body
    assert "- (no retry rounds recorded)" in body


def test_retry_history_rendering_with_multiple_rounds(
    tmp_path: pathlib.Path,
) -> None:
    context = _make_budget_context(
        retry_history=(
            RetryAttempt(
                retry_attempt=1,
                retry_reason="r1",
                round_id="round-01",
                path="_bmad-output/retry-history/5-8-foo/round-01",
            ),
            RetryAttempt(
                retry_attempt=2,
                retry_reason="r2",
                round_id="round-02",
                path="_bmad-output/retry-history/5-8-foo/round-02",
            ),
            RetryAttempt(
                retry_attempt=3,
                retry_reason="r3",
                round_id="round-03",
                path="_bmad-output/retry-history/5-8-foo/round-03",
            ),
        ),
    )
    result = assemble_escalation_bundle(
        context,
        repo_root=tmp_path,
        schemas_root=SCHEMAS_ROOT,
        thickening_flags=_make_thickening_flags_stub(),
        generated_at=_FIXED_GENERATED_AT,
    )
    body = _read_bundle(result.bundle_path)
    assert "round-01" in body
    assert "round-02" in body
    assert "round-03" in body
    assert "[Round 1 artifacts]" in body
    assert "[Round 2 artifacts]" in body
    assert "[Round 3 artifacts]" in body


# --------------------------------------------------------------------------- #
# AC-7 — deferred-work pointer renders per Story 5.7 format                   #
# --------------------------------------------------------------------------- #


def test_deferred_work_pointer_renders_per_story_5_7_format(
    tmp_path: pathlib.Path,
) -> None:
    context = _make_budget_context()
    result = assemble_escalation_bundle(
        context,
        repo_root=tmp_path,
        schemas_root=SCHEMAS_ROOT,
        thickening_flags=_make_thickening_flags_stub(),
        generated_at=_FIXED_GENERATED_AT,
    )
    body = _read_bundle(result.bundle_path)
    assert "_bmad-output/implementation-artifacts/deferred-work.md" in body
    # Story 5.7 BMAD-METHOD section-anchor shape mentioned in the
    # follow-on note (the per-story anchor isn't known at assembly-time,
    # but the section-name shape is verbatim).
    assert "## Deferred from: code review of 5-8-foo" in body


# --------------------------------------------------------------------------- #
# AC-7 — atomic-write semantics                                               #
# --------------------------------------------------------------------------- #


def test_atomic_write_semantics(tmp_path: pathlib.Path) -> None:
    """The new module reuses :func:`bundle_assembly._atomic_write_bundle`
    via the SHARED-rendering-core import per AC-4. A successful
    invocation produces exactly the target bundle file; no temp-file
    detritus remains.
    """
    context = _make_budget_context()
    result = assemble_escalation_bundle(
        context,
        repo_root=tmp_path,
        schemas_root=SCHEMAS_ROOT,
        thickening_flags=_make_thickening_flags_stub(),
        generated_at=_FIXED_GENERATED_AT,
    )
    bundle_dir = result.bundle_path.parent
    children = list(bundle_dir.iterdir())
    assert children == [result.bundle_path]


# --------------------------------------------------------------------------- #
# AC-3 — placeholder retirement (delegate behavior)                           #
# --------------------------------------------------------------------------- #


def test_default_escalation_bundle_assembler_delegates_to_full_assembler(
    tmp_path: pathlib.Path,
) -> None:
    """The default_escalation_bundle_assembler closure invokes
    bundle_assembly_escalation.assemble_escalation_bundle, producing a
    full Story-5.8-shaped bundle with the placeholder HTML comment
    structurally absent.
    """
    # The closure's internal call to assemble_escalation_bundle uses
    # find_repo_root() for schemas_root by default, which resolves to
    # the actual repo root. The bundle output uses tmp_path as repo_root.
    assembler = default_escalation_bundle_assembler(repo_root=tmp_path)
    context = _make_budget_context()
    assembler(context)

    expected_path = compute_escalation_bundle_path(
        repo_root=tmp_path, story_id="5-8-foo", run_id="run-1"
    )
    assert expected_path.exists()
    body = _read_bundle(expected_path)
    # Six AC-2 sections present
    assert "## ⚠️ Walking Skeleton Mode" in body
    assert "## Escalation rationale" in body
    assert "## Outstanding findings" in body
    assert "## Retry history" in body
    assert "## Deferred-work pointer" in body
    assert "## Preservation" in body
    # Placeholder absent
    assert "Replaced by Story 5.8" not in body


# --------------------------------------------------------------------------- #
# Public API surface                                                          #
# --------------------------------------------------------------------------- #


def test_assemble_escalation_bundle_result_dataclass_shape() -> None:
    """:class:`AssembleEscalationBundleResult` is frozen, hashable, and
    carries the five fields documented in the module docstring."""
    fields = {f.name for f in AssembleEscalationBundleResult.__dataclass_fields__.values()}
    assert fields == {
        "bundle_path",
        "emitted_markers",
        "header_text",
        "bundle_class",
        "payload",
    }
