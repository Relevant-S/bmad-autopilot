"""Contract-coverage matrix for Story 2.11 (basic merge-ready PR bundle assembly).

This docstring IS the contract-coverage checklist required by AC-8.
Reviewers verify every row maps to at least one passing test in this
module. The matrix is review-enforced, NOT CI-enforced (parallel to
stories 1.2-1.9 + 2.2-2.10).

AC-1 — substrate module identity + API surface:
    [x] assemble_bundle public function exists                     → test_assemble_bundle_public_api_exposed
    [x] AssembleBundleResult dataclass with required fields        → test_assemble_bundle_result_dataclass_shape
    [x] CLI entry point (python3 -m) parses required args          → test_cli_entry_point_parses_required_args
    [x] module docstring documents substrate-component identity    → test_assembler_module_docstring_documents_substrate_component_identity
    [x] atomic-write via tempfile + os.replace                     → test_bundle_atomic_write_via_tempfile_and_os_replace

AC-3 — bundle markdown shape:
    [x] happy path: full bundle from three envelopes               → test_assemble_bundle_happy_path_full_bundle_from_three_envelopes
    [x] H1 title + metadata block render                            → test_assemble_bundle_renders_h1_title_and_metadata_block
    [x] Walking Skeleton Mode is the first H2                       → test_assemble_bundle_renders_walking_skeleton_mode_header_at_first_h2
    [x] header body enumerates all four missing thickenings         → test_walking_skeleton_mode_body_enumerates_all_four_missing_thickenings_at_epic_2_substrate_state
    [x] Per-AC table renders Story 2.10's exactly-one-entry shape   → test_per_ac_section_renders_qa_envelope_exactly_one_entry_at_epic_2
    [x] Review findings empty placeholder                           → test_review_findings_section_renders_empty_placeholder_on_zero_findings
    [x] Review findings render non-empty array shape                → test_review_findings_section_renders_non_empty_findings
    [x] failed_layers empty surfaces                                → test_review_findings_section_renders_failed_layers_empty_at_epic_2
    [x] failed_layers non-empty renders marker comment (Story 3.3) → test_review_findings_section_renders_failed_layers_non_empty_with_marker_comments
    [x] two failed_layers render two marker comments (Story 3.3)   → test_review_findings_section_renders_two_failed_layers_with_two_marker_comments
    [x] Dev section renders proposed_commit_message verbatim        → test_dev_section_renders_proposed_commit_message_verbatim
    [x] scope_expanded_to empty surfaces                            → test_dev_section_renders_scope_expanded_to_empty_at_epic_2
    [x] bundle does NOT contain loud-fail / cost / retry sections   → test_bundle_does_not_contain_loud_fail_block_section
                                                                    → test_bundle_does_not_contain_cost_breakdown_section
                                                                    → test_bundle_does_not_contain_retry_history_section
    [x] H2 ordering: walking-skeleton → per-ac → review → dev       → test_h2_section_ordering_is_canonical

AC-4 — marker emission:
    [x] marker emitted when is_loud_fail_block_present == False     → test_walking_skeleton_marker_emitted_when_loud_fail_block_absent
    [x] marker suppressed when is_loud_fail_block_present == True   → test_walking_skeleton_marker_suppressed_when_loud_fail_block_present
    [x] marker in AssembleBundleResult.emitted_markers              → test_walking_skeleton_marker_in_emitted_markers_tuple
    [x] structured form, NOT legacy placeholder                     → test_walking_skeleton_marker_uses_structured_form_not_legacy_placeholder
    [x] UnknownMarkerClass on registry rejection                    → test_unknown_marker_class_raises_per_pattern_5
    [x] docstring documents marker emission rule                    → test_assembler_module_docstring_documents_marker_emission_rule

AC-5 — input source (three dispatch logs):
    [x] reads three specialist logs                                 → test_assemble_bundle_reads_three_specialist_logs
    [x] missing dev log raises                                      → test_assemble_bundle_raises_on_missing_dev_log
    [x] missing review log raises                                   → test_assemble_bundle_raises_on_missing_review_log
    [x] missing qa log raises                                       → test_assemble_bundle_raises_on_missing_qa_log
    [x] envelope re-validation failure raises                       → test_assemble_bundle_raises_on_envelope_revalidation_failure
    [x] does NOT consult run_state.last_envelope                    → test_assemble_bundle_does_not_consult_run_state_last_envelope
    [x] run_state.story_id mismatch raises                          → test_assemble_bundle_raises_on_run_state_story_id_mismatch
    [x] does NOT mutate run-state                                   → test_assembler_does_not_mutate_run_state

AC-7 — canonical example bundle fixture:
    [x] canonical fixture matches assembler output                  → test_canonical_walking_skeleton_bundle_fixture_matches_assembler_output

Review patches (2026-04-29):
    [x] dynamic fence prevents triple-backtick commit msg breakage  → test_dev_section_renders_backtick_containing_commit_message_without_breaking_fence

Story 3.4 — bucket × severity grouped review-section rendering:
    [x] groups by bucket then severity in fixed order; elides empties → test_review_findings_section_groups_by_bucket_then_severity
    [x] tags each finding with its source layer                       → test_review_findings_section_tags_each_finding_with_source_layer
    [x] segregates synthetic meta-findings from layer findings       → test_review_findings_section_segregates_meta_findings_from_layer_findings
    [x] meta-only envelope renders only meta sub-section              → test_review_findings_section_meta_only_envelope_renders_only_meta_subsection
    [x] header drops "Single-layer review" sentence at Epic 3        → test_walking_skeleton_header_drops_single_layer_review_sentence_at_epic_3
    [x] walking-skeleton-bundle marker still emits at Epic 3         → test_walking_skeleton_marker_still_emitted_at_epic_3_substrate_state
    [x] per-layer review-layer-failed marker emission preserved      → test_review_findings_section_per_layer_marker_emission_preserved

Exploratory heuristic findings sub-section render (Story 4.9):
    [x] sub-section with findings only                               → test_exploratory_heuristic_findings_subsection_with_findings_only
    [x] sub-section with emissions only                              → test_exploratory_heuristic_findings_subsection_with_emissions_only
    [x] sub-section with both findings and emissions                 → test_exploratory_heuristic_findings_subsection_with_findings_and_emissions
    [x] sub-section omitted when both empty                          → test_exploratory_heuristic_findings_subsection_omitted_when_both_empty
    [x] validate_marker_emission called per emission                 → test_exploratory_heuristic_findings_subsection_marker_validate_emission_called_per_emission
    [x] AC-driven findings not rendered by per-AC section            → test_ac_driven_findings_not_rendered_by_per_ac_section_render_at_story_4_9
    [x] ordering: per-AC → plan-drift → heuristic findings           → test_ordering_per_ac_then_plan_drift_then_heuristic_findings
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import yaml

from loud_fail_harness import bundle_assembly, thickening_flags
from loud_fail_harness.bundle_assembly import (
    AssembleBundleResult,
    EnvelopeReValidationFailed,
    RunStateStoryIdMismatch,
    SpecialistDispatchLogNotFound,
    assemble_bundle,
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
    from loud_fail_harness._shared import find_repo_root

    return find_repo_root()


@pytest.fixture(scope="module")
def envelopes_dir(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "examples" / "envelopes"


@pytest.fixture(scope="module")
def canonical_dev_envelope(envelopes_dir: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load((envelopes_dir / "dev-pass.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def canonical_review_envelope(envelopes_dir: pathlib.Path) -> dict[str, Any]:
    # Story 3.4 AC-5: canonical review envelope is now the Story-3.1
    # three-layer-pass shape (four findings sourced from blind / edge /
    # auditor / merged); the Story-2.9 single-layer fixture
    # `review-pass-acceptance-auditor.yaml` is preserved as a corpus
    # entry but is no longer the canonical bundle-fixture input.
    return yaml.safe_load(
        (envelopes_dir / "review-pass-three-layer.yaml").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def canonical_qa_envelope(envelopes_dir: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(
        (envelopes_dir / "qa-pass-ac1-tier1.yaml").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _write_run_state_yaml(
    rs_path: pathlib.Path,
    *,
    story_id: str = "sample-auto-001",
    branch_name: str = "bmad-automation/story/sample-auto-001",
    current_state: str = "done",
    last_envelope: dict[str, Any] | None = None,
) -> pathlib.Path:
    """Write a minimal-valid run-state YAML the bundle assembler can load."""
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "1.1",
        "story_id": story_id,
        "run_id": "run-2026-04-29-001",
        "current_state": current_state,
        "branch_name": branch_name,
        "dispatched_specialist": None,
        "last_envelope": last_envelope,
        "pending_qa_dispatch_payload": None,
        "retry_history": [],
        "active_markers": [],
        "cost_to_date_by_specialist": {},
    }
    rs_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return rs_path


def _seed_dispatch_log(
    logs_root: pathlib.Path,
    *,
    story_id: str,
    run_id: str,
    specialist: str,
    return_envelope: dict[str, Any],
    attempt_number: int = 1,
) -> pathlib.Path:
    """Write a JSON dispatch log mirroring Story 2.6's `persist_dispatch_log`
    payload shape (the assembler only reads the `return_envelope` field)."""
    log_path = (
        logs_root / story_id / run_id / "logs" / f"{specialist}-{attempt_number}.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_payload = {
        "dispatched_specialist": specialist,
        "story_id": story_id,
        "attempt_number": attempt_number,
        "agent_definition_path": f"agents/{specialist}.md",
        "acceptance_criteria": [{"ac_id": "AC-1", "text": "stub"}],
        "dispatch_timestamp": "2026-04-29T12:00:00+00:00",
        "return_timestamp": "2026-04-29T12:01:00+00:00",
        "return_envelope": return_envelope,
    }
    log_path.write_text(json.dumps(log_payload, indent=2), encoding="utf-8")
    return log_path


def _seed_three_logs(
    logs_root: pathlib.Path,
    *,
    story_id: str,
    run_id: str,
    dev: dict[str, Any],
    review: dict[str, Any],
    qa: dict[str, Any],
) -> dict[str, pathlib.Path]:
    return {
        "dev": _seed_dispatch_log(
            logs_root,
            story_id=story_id,
            run_id=run_id,
            specialist="dev",
            return_envelope=dev,
        ),
        "review-bmad": _seed_dispatch_log(
            logs_root,
            story_id=story_id,
            run_id=run_id,
            specialist="review-bmad",
            return_envelope=review,
        ),
        "qa": _seed_dispatch_log(
            logs_root,
            story_id=story_id,
            run_id=run_id,
            specialist="qa",
            return_envelope=qa,
        ),
    }


def _flags_namespace(
    *,
    full_review: bool = False,
    full_qa: bool = False,
    retry: bool = False,
    loud_fail_block: bool = False,
) -> ModuleType | SimpleNamespace:
    """Build a namespace mimicking thickening_flags with caller-supplied
    return values."""
    return SimpleNamespace(
        is_full_review_present=lambda: full_review,
        is_full_qa_present=lambda: full_qa,
        is_retry_present=lambda: retry,
        is_loud_fail_block_present=lambda: loud_fail_block,
    )


def _assemble(
    *,
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
    story_id: str = "sample-auto-001",
    run_id: str = "run-2026-04-29-001",
    flags: ModuleType | SimpleNamespace | None = None,
    marker_registry: MarkerClassRegistry | None = None,
    last_envelope_in_run_state: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> tuple[AssembleBundleResult, pathlib.Path]:
    """Convenience wrapper that seeds run-state + three logs and invokes
    the assembler, returning (result, bundle_path)."""
    rs_path = _write_run_state_yaml(
        tmp_path / "_bmad" / "automation" / "run-state.yaml",
        story_id=story_id,
        last_envelope=last_envelope_in_run_state,
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_three_logs(
        logs_root,
        story_id=story_id,
        run_id=run_id,
        dev=canonical_dev_envelope,
        review=canonical_review_envelope,
        qa=canonical_qa_envelope,
    )
    bundle_root = tmp_path / "pr-bundles"
    result = assemble_bundle(
        story_id=story_id,
        run_id=run_id,
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        marker_registry=marker_registry or runtime_marker_registry,
        thickening_flags=flags,
        generated_at=generated_at
        or datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc),
    )
    return result, result.bundle_path


# --------------------------------------------------------------------------- #
# AC-1 — substrate module identity + API surface                              #
# --------------------------------------------------------------------------- #


def test_assemble_bundle_public_api_exposed() -> None:
    assert callable(bundle_assembly.assemble_bundle)
    # CLI entry point (`if __name__ == "__main__":`) lives at module bottom;
    # the `main` function is testable directly.
    assert callable(bundle_assembly.main)


def test_assemble_bundle_result_dataclass_shape() -> None:
    assert dataclasses.is_dataclass(AssembleBundleResult)
    field_names = {f.name for f in dataclasses.fields(AssembleBundleResult)}
    assert {"bundle_path", "emitted_markers", "header_text", "included_specialists"}.issubset(
        field_names
    )


def test_cli_entry_point_parses_required_args(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
) -> None:
    rs_path = _write_run_state_yaml(
        tmp_path / "_bmad" / "automation" / "run-state.yaml"
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_three_logs(
        logs_root,
        story_id="sample-auto-001",
        run_id="run-cli-001",
        dev=canonical_dev_envelope,
        review=canonical_review_envelope,
        qa=canonical_qa_envelope,
    )
    bundle_root = tmp_path / "pr-bundles"
    rc = bundle_assembly.main(
        [
            "--story-id",
            "sample-auto-001",
            "--run-id",
            "run-cli-001",
            "--run-state-path",
            str(rs_path),
            "--logs-root",
            str(logs_root),
            "--bundle-root",
            str(bundle_root),
        ]
    )
    assert rc == 0
    bundle_path = bundle_root / "sample-auto-001" / "run-cli-001.md"
    assert bundle_path.exists()


def test_assembler_module_docstring_documents_substrate_component_identity() -> None:
    doc = bundle_assembly.__doc__ or ""
    assert "cell-1" in doc or "cell 1" in doc, (
        "module docstring must reference the cell-1 contract boundary"
    )
    assert "Stop hook" in doc, "module docstring must reference the Stop hook"
    assert "marker-taxonomy" in doc, (
        "module docstring must reference marker-taxonomy.yaml"
    )
    assert "SIXTH substrate component" in doc or "sixth substrate component" in doc, (
        "module docstring must name the substrate-component-six identity"
    )


def test_bundle_atomic_write_via_tempfile_and_os_replace(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Atomic-write discipline: the bundle write path goes through
    `tempfile.NamedTemporaryFile` + `os.replace`. Mid-write crash leaves
    no partial bundle file at the canonical path.
    """
    real_replace = bundle_assembly.os.replace
    saw_replace_call: list[bool] = []

    def _spy_replace(src: str | pathlib.Path, dst: str | pathlib.Path) -> None:
        saw_replace_call.append(True)
        real_replace(src, dst)

    monkeypatch.setattr(bundle_assembly.os, "replace", _spy_replace)
    _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    assert saw_replace_call, "bundle write must invoke os.replace (atomic-rename)"

    # Mid-write crash leaves no partial bundle. Inject a failure in the
    # temp file's write path to validate cleanup.
    def _broken_replace(_src: object, _dst: object) -> None:
        raise OSError("simulated atomic-rename failure")

    monkeypatch.setattr(bundle_assembly.os, "replace", _broken_replace)
    rs_path = _write_run_state_yaml(
        tmp_path / "_bmad-2" / "automation" / "run-state.yaml"
    )
    logs_root = tmp_path / "qa-evidence-2"
    _seed_three_logs(
        logs_root,
        story_id="sample-auto-001",
        run_id="run-broken",
        dev=canonical_dev_envelope,
        review=canonical_review_envelope,
        qa=canonical_qa_envelope,
    )
    bundle_root = tmp_path / "pr-bundles-broken"
    with pytest.raises(OSError, match="simulated atomic-rename failure"):
        assemble_bundle(
            story_id="sample-auto-001",
            run_id="run-broken",
            run_state_path=rs_path,
            logs_root=logs_root,
            bundle_root=bundle_root,
            marker_registry=runtime_marker_registry,
        )
    bundle_dir = bundle_root / "sample-auto-001"
    if bundle_dir.exists():
        # No final bundle.md; only at most a tmp file (which we expect to be
        # cleaned up on the failure path).
        leftover = list(bundle_dir.glob("*.md"))
        assert leftover == [], (
            f"atomic-write discipline violated; partial bundle left: {leftover}"
        )


# --------------------------------------------------------------------------- #
# AC-3 — bundle markdown shape                                                #
# --------------------------------------------------------------------------- #


def test_assemble_bundle_happy_path_full_bundle_from_three_envelopes(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    result, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    assert bundle_path.exists()
    body = bundle_path.read_text(encoding="utf-8")
    assert "## Per-AC results" in body
    assert "## Review findings" in body
    assert "## Dev" in body
    assert result.included_specialists == frozenset({"dev", "review-bmad", "qa"})


def test_assemble_bundle_renders_h1_title_and_metadata_block(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert body.startswith("# PR bundle — story sample-auto-001 (run run-2026-04-29-001)")
    assert "Branch: bmad-automation/story/sample-auto-001" in body
    assert "Final state: done" in body
    assert "Generated: 2026-04-29T12:00:00+00:00" in body


def test_assemble_bundle_renders_walking_skeleton_mode_header_at_first_h2(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    h2_lines = [line for line in body.splitlines() if line.startswith("## ")]
    assert h2_lines, "bundle must contain at least one H2"
    assert h2_lines[0] == "## ⚠️ Walking Skeleton Mode"


def test_walking_skeleton_mode_body_enumerates_all_four_missing_thickenings_at_epic_2_substrate_state(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Structural test: with ALL FOUR flags returning ``False`` (the
    Epic-2 substrate state), the renderer enumerates all four missing
    thickenings. Story 3.4 AC-3 flipped ``is_full_review_present`` to
    ``True`` in production ``thickening_flags``, so this test now
    injects an explicit all-False namespace via ``_flags_namespace()``
    to cover the structural-not-era-based emission path. The
    post-3.4-substrate-state behavior is covered by the companion test
    ``test_walking_skeleton_header_drops_single_layer_review_sentence_at_epic_3``.
    """
    result, _ = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
        flags=_flags_namespace(),  # all four return False — Epic-2 baseline
    )
    header = result.header_text
    assert "Tier-1 evidence only" in header
    assert "Epic 4" in header
    assert "Single-layer review" in header
    assert "Epic 3" in header
    assert "No retry" in header
    assert "Epic 5" in header
    assert "No loud-fail block" in header
    assert "Epic 6" in header


def test_per_ac_section_renders_qa_envelope_exactly_one_entry_at_epic_2(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "AC-1" in body
    assert "HTTP POST /healthz returned status code 200" in body
    assert "qa-evidence/sample-001/run-2026-04-29-001/ac1-http-200.log" in body
    assert "not_applicable" in body
    # Exactly one AC entry at Epic 2 scope per Story 2.10's AC-2.
    ac_entries = [line for line in body.splitlines() if line.startswith("### AC-")]
    assert len(ac_entries) == 1


def test_review_findings_section_renders_empty_placeholder_on_zero_findings(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    review_no_findings: dict[str, Any] = {
        "status": "pass",
        "artifacts": ["bmad-autopilot/x.md"],
        "findings": [],
        "rationale": "no findings",
        "failed_layers": [],
    }
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=review_no_findings,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "_(no findings)_" in body


def test_review_findings_section_renders_non_empty_findings(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 3.4 AC-1 relaxation: this test, originally written against
    the flat-list rendering shape (Story 2.11 era), is updated in place
    to assert the new bucket × severity grouped shape against the
    canonical three-layer envelope (Story 3.1; AC-5 swap). The
    layer-attribution invariant is covered in
    ``test_review_findings_section_tags_each_finding_with_source_layer``
    below.
    """
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    # Canonical three-layer review envelope has four findings; all four
    # are bucket: defer with severities {MED, LOW, LOW, LOW}.
    assert "review-001" in body
    assert "review-004" in body
    # New bucket × severity grouped sub-headers.
    assert "### bucket: defer" in body
    assert "**MED:**" in body
    assert "**LOW:**" in body
    # Old flat-list rendering shape is gone (Story 3.4 AC-1 relaxation).
    assert "_(bucket: `defer`, severity: `LOW`)_" not in body


def test_review_findings_section_renders_failed_layers_empty_at_epic_2(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "Failed layers: (none)" in body


def test_review_findings_section_renders_failed_layers_non_empty_with_marker_comments(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 3.3 AC-4: a single failed layer renders one HTML-comment marker
    co-located with the 'Failed layers: ...' prose.

    This test exercises the non-empty failed_layers branch added to
    _render_review_findings_section at Story 3.3 AC-4 — the branch that
    emits <!-- bmad-automation:marker review-layer-failed: <layer> -->.
    """
    review_with_failed_layer: dict[str, Any] = {
        "status": "pass",
        "artifacts": ["bmad-autopilot/some-file.md"],
        "findings": [],
        "rationale": "edge layer failed; surviving layers passed",
        "failed_layers": ["edge"],
    }
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=review_with_failed_layer,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "review-layer-failed: edge" in body
    assert "Failed layers: `edge`" in body
    assert "<!--" in body


def test_review_findings_section_renders_two_failed_layers_with_two_marker_comments(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 3.3 AC-4: two failed layers render two HTML-comment markers (one per layer)."""
    review_two_failed: dict[str, Any] = {
        "status": "blocked",
        "artifacts": [],
        "findings": [],
        "rationale": "blind and edge layers failed",
        "failed_layers": ["blind", "edge"],
    }
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=review_two_failed,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "review-layer-failed: blind" in body
    assert "review-layer-failed: edge" in body


def test_dev_section_renders_proposed_commit_message_verbatim(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    expected = canonical_dev_envelope["proposed_commit_message"]
    assert expected in body


def test_dev_section_renders_scope_expanded_to_empty_at_epic_2(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "Scope expanded to: (none)" in body


def test_bundle_does_not_contain_loud_fail_block_section(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "## Loud-fail" not in body
    assert "## Loud-Fail Block" not in body


def test_bundle_does_not_contain_cost_breakdown_section(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "## Cost breakdown" not in body
    assert "## Per-specialist cost" not in body


def test_bundle_does_not_contain_retry_history_section(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "## Retry history" not in body


def test_h2_section_ordering_is_canonical(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    h2_lines = [line for line in body.splitlines() if line.startswith("## ")]
    assert h2_lines == [
        "## ⚠️ Walking Skeleton Mode",
        "## Per-AC results",
        "## Review findings",
        "## Dev",
    ]


# --------------------------------------------------------------------------- #
# AC-4 — marker emission                                                      #
# --------------------------------------------------------------------------- #


def test_walking_skeleton_marker_emitted_when_loud_fail_block_absent(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    flags = _flags_namespace(loud_fail_block=False)
    result, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
        flags=flags,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "<!-- bmad-automation:marker walking-skeleton-bundle -->" in body
    assert "walking-skeleton-bundle" in result.emitted_markers


def test_walking_skeleton_marker_suppressed_when_loud_fail_block_present(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Structural-NOT-era-based emission rule. With
    is_loud_fail_block_present() returning True, the marker MUST NOT
    appear — even though Epic-2 era flags would emit it.
    """
    flags = _flags_namespace(loud_fail_block=True)
    result, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
        flags=flags,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "<!-- bmad-automation:marker walking-skeleton-bundle -->" not in body
    assert "walking-skeleton-bundle" not in result.emitted_markers


def test_walking_skeleton_marker_in_emitted_markers_tuple(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    result, _ = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    assert result.emitted_markers == ("walking-skeleton-bundle",)


def test_walking_skeleton_marker_uses_structured_form_not_legacy_placeholder(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    # Structured form present.
    assert "<!-- bmad-automation:marker walking-skeleton-bundle -->" in body
    # Legacy fragile-prose-heuristic form forbidden.
    assert "<!-- walking-skeleton-bundle: marker_class -->" not in body
    # Greppability — exactly one structured marker.
    assert (
        len(re.findall(r"bmad-automation:marker walking-skeleton-bundle", body))
        == 1
    )


def test_unknown_marker_class_raises_per_pattern_5(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
) -> None:
    """Empty registry rejects 'walking-skeleton-bundle' →
    UnknownMarkerClass; the failure surfaces BEFORE the bundle file is
    written (defense-in-depth).
    """
    rs_path = _write_run_state_yaml(
        tmp_path / "_bmad" / "automation" / "run-state.yaml"
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_three_logs(
        logs_root,
        story_id="sample-auto-001",
        run_id="run-empty-reg",
        dev=canonical_dev_envelope,
        review=canonical_review_envelope,
        qa=canonical_qa_envelope,
    )
    bundle_root = tmp_path / "pr-bundles"
    empty_registry = MarkerClassRegistry(marker_classes=frozenset())
    with pytest.raises(UnknownMarkerClass):
        assemble_bundle(
            story_id="sample-auto-001",
            run_id="run-empty-reg",
            run_state_path=rs_path,
            logs_root=logs_root,
            bundle_root=bundle_root,
            marker_registry=empty_registry,
        )
    bundle_dir = bundle_root / "sample-auto-001"
    assert not bundle_dir.exists() or list(bundle_dir.glob("*.md")) == [], (
        "no bundle file should be written when the registry rejects the marker"
    )


def test_assembler_module_docstring_documents_marker_emission_rule() -> None:
    doc = bundle_assembly.__doc__ or ""
    assert "is_loud_fail_block_present" in doc
    assert "structural" in doc.lower()
    assert "1527" in doc, (
        "module docstring must cite the verbatim epic AC line range (1527-1528)"
    )


# --------------------------------------------------------------------------- #
# AC-5 — input source (three dispatch logs)                                   #
# --------------------------------------------------------------------------- #


def test_assemble_bundle_reads_three_specialist_logs(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    result, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    # Dev surface (proposed_commit_message)
    assert canonical_dev_envelope["proposed_commit_message"] in body
    # Review surface (finding id; the post-3.4 three-layer fixture carries
    # review-001 through review-004, all sourced from the four layer
    # identifiers — see Story 3.4 AC-5).
    assert "review-001" in body
    # QA surface (AC-1 assertion)
    assert "HTTP POST /healthz returned status code 200" in body
    assert result.included_specialists == frozenset({"dev", "review-bmad", "qa"})


def test_assemble_bundle_raises_on_missing_dev_log(
    tmp_path: pathlib.Path,
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    rs_path = _write_run_state_yaml(
        tmp_path / "_bmad" / "automation" / "run-state.yaml"
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_dispatch_log(
        logs_root,
        story_id="sample-auto-001",
        run_id="run-missing-dev",
        specialist="review-bmad",
        return_envelope=canonical_review_envelope,
    )
    _seed_dispatch_log(
        logs_root,
        story_id="sample-auto-001",
        run_id="run-missing-dev",
        specialist="qa",
        return_envelope=canonical_qa_envelope,
    )
    bundle_root = tmp_path / "pr-bundles"
    with pytest.raises(SpecialistDispatchLogNotFound) as excinfo:
        assemble_bundle(
            story_id="sample-auto-001",
            run_id="run-missing-dev",
            run_state_path=rs_path,
            logs_root=logs_root,
            bundle_root=bundle_root,
            marker_registry=runtime_marker_registry,
        )
    assert excinfo.value.specialist == "dev"
    assert not (bundle_root / "sample-auto-001" / "run-missing-dev.md").exists()


def test_assemble_bundle_raises_on_missing_review_log(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    rs_path = _write_run_state_yaml(
        tmp_path / "_bmad" / "automation" / "run-state.yaml"
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_dispatch_log(
        logs_root,
        story_id="sample-auto-001",
        run_id="run-missing-rev",
        specialist="dev",
        return_envelope=canonical_dev_envelope,
    )
    _seed_dispatch_log(
        logs_root,
        story_id="sample-auto-001",
        run_id="run-missing-rev",
        specialist="qa",
        return_envelope=canonical_qa_envelope,
    )
    bundle_root = tmp_path / "pr-bundles"
    with pytest.raises(SpecialistDispatchLogNotFound) as excinfo:
        assemble_bundle(
            story_id="sample-auto-001",
            run_id="run-missing-rev",
            run_state_path=rs_path,
            logs_root=logs_root,
            bundle_root=bundle_root,
            marker_registry=runtime_marker_registry,
        )
    assert excinfo.value.specialist == "review-bmad"


def test_assemble_bundle_raises_on_missing_qa_log(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    rs_path = _write_run_state_yaml(
        tmp_path / "_bmad" / "automation" / "run-state.yaml"
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_dispatch_log(
        logs_root,
        story_id="sample-auto-001",
        run_id="run-missing-qa",
        specialist="dev",
        return_envelope=canonical_dev_envelope,
    )
    _seed_dispatch_log(
        logs_root,
        story_id="sample-auto-001",
        run_id="run-missing-qa",
        specialist="review-bmad",
        return_envelope=canonical_review_envelope,
    )
    bundle_root = tmp_path / "pr-bundles"
    with pytest.raises(SpecialistDispatchLogNotFound) as excinfo:
        assemble_bundle(
            story_id="sample-auto-001",
            run_id="run-missing-qa",
            run_state_path=rs_path,
            logs_root=logs_root,
            bundle_root=bundle_root,
            marker_registry=runtime_marker_registry,
        )
    assert excinfo.value.specialist == "qa"


def test_assemble_bundle_raises_on_envelope_revalidation_failure(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    rs_path = _write_run_state_yaml(
        tmp_path / "_bmad" / "automation" / "run-state.yaml"
    )
    logs_root = tmp_path / "qa-evidence"
    # Seed a tampered dev log: missing the required `rationale` field.
    tampered_dev = dict(canonical_dev_envelope)
    tampered_dev.pop("rationale", None)
    _seed_dispatch_log(
        logs_root,
        story_id="sample-auto-001",
        run_id="run-tampered",
        specialist="dev",
        return_envelope=tampered_dev,
    )
    _seed_dispatch_log(
        logs_root,
        story_id="sample-auto-001",
        run_id="run-tampered",
        specialist="review-bmad",
        return_envelope=canonical_review_envelope,
    )
    _seed_dispatch_log(
        logs_root,
        story_id="sample-auto-001",
        run_id="run-tampered",
        specialist="qa",
        return_envelope=canonical_qa_envelope,
    )
    bundle_root = tmp_path / "pr-bundles"
    with pytest.raises(EnvelopeReValidationFailed) as excinfo:
        assemble_bundle(
            story_id="sample-auto-001",
            run_id="run-tampered",
            run_state_path=rs_path,
            logs_root=logs_root,
            bundle_root=bundle_root,
            marker_registry=runtime_marker_registry,
        )
    assert excinfo.value.specialist == "dev"


def test_assemble_bundle_does_not_consult_run_state_last_envelope(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Sanity check: even if run-state.yaml's last_envelope carries
    arbitrary content, the assembler reads the three dispatch logs
    (canonical multi-specialist source) — not the run-state's in-flight
    cache.
    """
    bogus_last_envelope: dict[str, Any] = {
        "status": "blocked",
        "artifacts": [],
        "findings": [],
        "rationale": "BOGUS — should not appear in bundle",
        "proposed_commit_message": "BOGUS COMMIT MESSAGE",
    }
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
        last_envelope_in_run_state=bogus_last_envelope,
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "BOGUS" not in body
    assert canonical_dev_envelope["proposed_commit_message"] in body


def test_assemble_bundle_raises_on_run_state_story_id_mismatch(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    rs_path = _write_run_state_yaml(
        tmp_path / "_bmad" / "automation" / "run-state.yaml",
        story_id="some-other-story",
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_three_logs(
        logs_root,
        story_id="sample-auto-001",
        run_id="run-2026-04-29-001",
        dev=canonical_dev_envelope,
        review=canonical_review_envelope,
        qa=canonical_qa_envelope,
    )
    bundle_root = tmp_path / "pr-bundles"
    with pytest.raises(RunStateStoryIdMismatch):
        assemble_bundle(
            story_id="sample-auto-001",
            run_id="run-2026-04-29-001",
            run_state_path=rs_path,
            logs_root=logs_root,
            bundle_root=bundle_root,
            marker_registry=runtime_marker_registry,
        )


def test_assembler_does_not_mutate_run_state(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    rs_path = _write_run_state_yaml(
        tmp_path / "_bmad" / "automation" / "run-state.yaml"
    )
    pre_bytes = rs_path.read_bytes()
    _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    post_bytes = rs_path.read_bytes()
    assert post_bytes == pre_bytes, "run-state must NOT be mutated by the assembler"


def test_bundle_assembly_unaffected_by_runtime_duration_ms_addition(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 2.12 AC-5: adding ``runtime_duration_ms`` to the dispatch log
    payload does NOT affect bundle assembly output.

    The assembler reads ONLY the ``return_envelope`` field from each
    log file (per AC-5 of Story 2.11); the new ``runtime_duration_ms``
    field is invisible. This test seeds three logs WITH the new field
    populated and asserts the rendered bundle is byte-identical to the
    canonical baseline produced by the standard ``_seed_dispatch_log``
    helper (which does NOT include the field).
    """
    # Baseline: assemble bundle WITHOUT the new field.
    _, baseline_bundle = _assemble(
        tmp_path=tmp_path / "baseline",
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    baseline_body = baseline_bundle.read_text(encoding="utf-8")

    # With-field run: hand-author logs that include runtime_duration_ms
    # then run the assembler against them.
    run_root = tmp_path / "with-field"
    run_root.mkdir()
    rs_path = _write_run_state_yaml(
        run_root / "_bmad" / "automation" / "run-state.yaml"
    )
    logs_root = run_root / "qa-evidence"
    bundle_root = run_root / "pr-bundles"

    for specialist, envelope in (
        ("dev", canonical_dev_envelope),
        ("review-bmad", canonical_review_envelope),
        ("qa", canonical_qa_envelope),
    ):
        log_path = (
            logs_root
            / "sample-auto-001"
            / "run-2026-04-29-001"
            / "logs"
            / f"{specialist}-1.log"
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Same payload shape as _seed_dispatch_log PLUS the new
        # runtime_duration_ms field — proves the assembler ignores it.
        payload = {
            "dispatched_specialist": specialist,
            "story_id": "sample-auto-001",
            "attempt_number": 1,
            "agent_definition_path": f"agents/{specialist}.md",
            "acceptance_criteria": [{"ac_id": "AC-1", "text": "stub"}],
            "dispatch_timestamp": "2026-04-29T12:00:00+00:00",
            "return_timestamp": "2026-04-29T12:01:00+00:00",
            "return_envelope": envelope,
            "runtime_duration_ms": 60_000,  # Story 2.12 AC-5 additive field
        }
        log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with_field_bundle = assemble_bundle(
        story_id="sample-auto-001",
        run_id="run-2026-04-29-001",
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        marker_registry=runtime_marker_registry,
        generated_at=datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc),
    ).bundle_path
    with_field_body = with_field_bundle.read_text(encoding="utf-8")

    assert with_field_body == baseline_body, (
        "bundle output must be byte-identical regardless of runtime_duration_ms presence "
        "(AC-5: assembler reads only return_envelope from each log)"
    )


# --------------------------------------------------------------------------- #
# AC-7 — canonical example bundle fixture                                     #
# --------------------------------------------------------------------------- #


def test_canonical_walking_skeleton_bundle_fixture_matches_assembler_output(
    tmp_path: pathlib.Path,
    repo_root: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Regenerate the bundle in tmp_path against the canonical envelope
    fixtures; assert the committed example fixture's body matches.

    The assembler's body is deterministic given identical (story_id,
    run_id, generated_at, envelopes); the fixture pins these inputs so
    rendering drift is caught by this regression test.
    """
    fixture_path = (
        repo_root / "examples" / "pr-bundles" / "pr-bundle-walking-skeleton.md"
    )
    if not fixture_path.exists():
        pytest.fail(
            "examples/pr-bundles/pr-bundle-walking-skeleton.md is missing from "
            "the repository — the fixture must be committed; regenerate it via "
            "assemble_bundle against the canonical envelope corpus"
        )
    fixture_body = fixture_path.read_text(encoding="utf-8")
    # Strip the contract-header HTML comment block from the fixture before
    # comparing — the assembler does not (and should not) emit the
    # contract-header; the comment is fixture-only metadata. The marker
    # appears AFTER the strip.
    body_after_header = re.sub(
        r"^<!--.*?-->\s*", "", fixture_body, count=1, flags=re.DOTALL
    )
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
        story_id="sample-auto-001",
        run_id="run-2026-04-29-001",
        generated_at=datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc),
    )
    assembled_body = bundle_path.read_text(encoding="utf-8")
    assert assembled_body == body_after_header, (
        "canonical fixture must match assembler output byte-for-byte "
        "(modulo contract-header strip); regenerate the fixture if the "
        "assembler's rendering intentionally changed"
    )


def test_dev_section_renders_backtick_containing_commit_message_without_breaking_fence(
    tmp_path: pathlib.Path,
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Dynamic fence length prevents triple-backtick content in the commit
    message from closing the code fence prematurely (review patch for
    _fenced_code_block using CommonMark spec §4.5 dynamic-length fences).
    """
    dev_with_backticks: dict[str, Any] = {
        "status": "pass",
        "artifacts": ["bmad-autopilot/x.py"],
        "findings": [],
        "rationale": "adds feature with code example",
        "proposed_commit_message": "feat: add example\n\n```python\ncode here\n```",
        "scope_expanded_to": [],
    }
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=dev_with_backticks,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    # The ## Dev H2 must be followed by the ## marker comment at end of bundle —
    # if the code fence broke early, the ``` inside the commit message would have
    # closed the fence, and the remaining content (including "## Dev" itself) would
    # render as raw markdown rather than structured sections.
    assert "## Dev" in body, "Dev H2 section must be present"
    assert "feat: add example" in body, "commit message must appear in bundle"
    # The fence wrapping the commit message must use 4+ backticks so the ``` inside
    # the commit message does not close it.
    assert "````" in body, (
        "_fenced_code_block must use a 4-backtick fence when content contains ```"
    )
    # Structured marker must still appear after the Dev section (bundle is intact).
    assert "<!-- bmad-automation:marker walking-skeleton-bundle -->" in body


# --------------------------------------------------------------------------- #
# Story 3.4 — bucket × severity grouped review-section rendering              #
# --------------------------------------------------------------------------- #


def _synthesize_finding(
    *,
    fid: str,
    source: str,
    bucket: str,
    severity: str,
    title: str = "synth title",
    detail: str = "synth detail",
    location: str = "agents/x.md:1",
    meta: str | None = None,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "id": fid,
        "source": source,
        "title": title,
        "detail": detail,
        "location": location,
        "bucket": bucket,
        "severity": severity,
    }
    if meta is not None:
        finding["meta"] = meta
    return finding


def test_review_findings_section_groups_by_bucket_then_severity(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 3.4 AC-1: findings spanning all four buckets × three
    severities render under bucket sub-headers in fixed order
    (decision_needed, patch, defer, dismiss); within each non-empty
    bucket, severity sub-headers appear in fixed order (HIGH, MED,
    LOW); empty bucket × severity slots are elided.
    """
    review_envelope: dict[str, Any] = {
        "status": "pass",
        "artifacts": ["bmad-autopilot/x.md"],
        "findings": [
            _synthesize_finding(
                fid="f-dn-h",
                source="auditor",
                bucket="decision_needed",
                severity="HIGH",
            ),
            _synthesize_finding(
                fid="f-pa-m",
                source="blind",
                bucket="patch",
                severity="MED",
            ),
            _synthesize_finding(
                fid="f-de-l",
                source="edge",
                bucket="defer",
                severity="LOW",
            ),
            _synthesize_finding(
                fid="f-di-l",
                source="merged",
                bucket="dismiss",
                severity="LOW",
            ),
        ],
        "rationale": "synthesized for grouping test",
        "failed_layers": [],
    }
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")

    # Each non-empty bucket renders a sub-header.
    for bucket in ("decision_needed", "patch", "defer", "dismiss"):
        assert f"### bucket: {bucket}" in body, f"missing bucket sub-header: {bucket}"

    # Bucket sub-headers appear in fixed canonical order.
    bucket_positions = [
        body.index(f"### bucket: {bucket}")
        for bucket in ("decision_needed", "patch", "defer", "dismiss")
    ]
    assert bucket_positions == sorted(bucket_positions), (
        "bucket sub-headers must render in fixed canonical order "
        "(decision_needed, patch, defer, dismiss)"
    )

    # Empty severity slots are elided — there is no `**MED:**` under
    # `decision_needed` (which only contains HIGH), no `**HIGH:**`
    # under `patch` (which only contains MED), etc. Validate by
    # counting that exactly four severity sub-headers render in total.
    severity_header_counts = sum(
        body.count(f"**{sev}:**") for sev in ("HIGH", "MED", "LOW")
    )
    assert severity_header_counts == 4, (
        f"expected 4 severity sub-headers (one per finding); got {severity_header_counts}"
    )


def test_review_findings_section_tags_each_finding_with_source_layer(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 3.4 AC-1: each finding bullet carries a `[<source-layer>]`
    tag identifying its origin. The canonical three-layer fixture
    carries one finding from each of {blind, edge, auditor, merged}.
    """
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    for source in ("blind", "edge", "auditor", "merged"):
        assert f"[{source}]" in body, (
            f"source-layer tag [{source}] missing from rendered review section"
        )


def test_review_findings_section_segregates_meta_findings_from_layer_findings(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.4 AC-1: synthetic findings carrying `meta:
    review-completeness` (Story 3.3 channel-3 surface) render in a
    dedicated sub-section visually distinct from layer-produced
    content findings. The meta finding is NOT rendered in the
    `decision_needed` bucket section even though its bucket value is
    decision_needed.
    """
    review_envelope = yaml.safe_load(
        (envelopes_dir / "review-pass-partial-layer-failure-with-meta.yaml").read_text(
            encoding="utf-8"
        )
    )
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")

    # Layer-produced content findings appear in bucket sections.
    assert "### bucket: defer" in body
    assert "review-001" in body  # source: blind, bucket: defer, sev: LOW
    assert "review-002" in body  # source: auditor, bucket: defer, sev: LOW

    # Synthetic meta finding renders in dedicated sub-section.
    assert "### Review-completeness meta-findings" in body
    assert "review-layer-failed-edge" in body

    # The meta finding is NOT placed in the decision_needed bucket
    # section: there is no `### bucket: decision_needed` header
    # because no NON-meta finding has that bucket.
    assert "### bucket: decision_needed" not in body


def test_review_findings_section_meta_only_envelope_renders_only_meta_subsection(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.4 AC-1 (d) edge case: an envelope whose findings are
    ONLY synthetic meta findings (the Story 3.3 all-three-layers-failed
    shape) renders the meta sub-section as the sole content; bucket
    × severity sub-headers are elided (no orphan `### bucket:` headers);
    `failed_layers` prose + per-layer markers ARE rendered (the Story
    3.3 AC-4 invariant is preserved through the rendering thickening).
    """
    review_envelope = yaml.safe_load(
        (envelopes_dir / "review-blocked-three-layer-failure-with-meta.yaml").read_text(
            encoding="utf-8"
        )
    )
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")

    # No bucket sub-headers (no orphan headers; no layer-produced findings).
    for bucket in ("decision_needed", "patch", "defer", "dismiss"):
        assert f"### bucket: {bucket}" not in body, (
            f"bucket sub-header `{bucket}` rendered with no layer findings"
        )

    # Meta sub-section IS rendered with all three meta findings.
    assert "### Review-completeness meta-findings" in body
    assert "review-layer-failed-auditor" in body
    assert "review-layer-failed-blind" in body
    assert "review-layer-failed-edge" in body

    # failed_layers prose + per-layer marker comments preserved.
    assert "Failed layers:" in body
    assert "review-layer-failed: auditor" in body
    assert "review-layer-failed: blind" in body
    assert "review-layer-failed: edge" in body


def test_walking_skeleton_header_drops_single_layer_review_sentence_at_epic_3(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 3.4 AC-3: with the post-3.4 production thickening_flags
    (`is_full_review_present` returns ``True``), the Walking Skeleton
    Mode body enumerates EXACTLY THREE missing-thickening sentences;
    the "Single-layer review (Epic 3 thickens to 3-layer adversarial
    pass)." sentence is OMITTED.
    """
    result, _ = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
        flags=thickening_flags,  # production module — post-3.4 substrate state
    )
    header = result.header_text

    # Bullet count: exactly three sentences (lines beginning with `- `).
    bullets = [line for line in header.splitlines() if line.startswith("- ")]
    assert len(bullets) == 3, (
        f"expected 3 missing-thickening bullets at post-3.4 substrate state; "
        f"got {len(bullets)}: {bullets!r}"
    )

    # The dropped sentence is the structural witness of the flag flip.
    assert "Single-layer review (Epic 3 thickens" not in header

    # The remaining three sentences are present.
    assert "Tier-1 evidence only" in header
    assert "No retry" in header
    assert "No loud-fail block" in header


def test_walking_skeleton_marker_still_emitted_at_epic_3_substrate_state(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 3.4 AC-4 regression baseline: with the post-3.4 production
    thickening_flags (``is_loud_fail_block_present`` continues to
    return ``False``), the ``walking-skeleton-bundle`` marker continues
    to emit. The emission rule is structural (`absent loud-fail block
    triggers the marker`), NOT era-based; Epic 3 is NOT the era that
    triggers suppression — Epic 6 / Story 6.1 owns the loud-fail block
    landing that flips the flag. This test guards against accidental
    pre-emption of Epic 6's responsibility in the Epic 3 / 4 / 5
    timeframes.
    """
    result, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
        flags=thickening_flags,  # production module — post-3.4 substrate state
    )
    body = bundle_path.read_text(encoding="utf-8")
    assert "<!-- bmad-automation:marker walking-skeleton-bundle -->" in body
    assert "walking-skeleton-bundle" in result.emitted_markers


def test_review_findings_section_per_layer_marker_emission_preserved(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.4 AC-1 + Story 3.3 AC-4 preservation: the per-layer
    ``<!-- bmad-automation:marker review-layer-failed: <layer> -->``
    emission and the per-layer ``validate_marker_emission`` defense-in-depth
    call are preserved verbatim through the rendering thickening. With
    one failed layer (edge) in the partial-failure-with-meta fixture,
    exactly one review-layer-failed marker comment renders.
    """
    review_envelope = yaml.safe_load(
        (envelopes_dir / "review-pass-partial-layer-failure-with-meta.yaml").read_text(
            encoding="utf-8"
        )
    )
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    # Exactly one review-layer-failed marker (one failed layer).
    assert (
        len(re.findall(r"bmad-automation:marker review-layer-failed: edge", body))
        == 1
    )
    # The marker is co-located with the failed_layers prose.
    assert "Failed layers: `edge`" in body


# --------------------------------------------------------------------------- #
# Exploratory heuristic findings sub-section render (Story 4.9)               #
# --------------------------------------------------------------------------- #


def _qa_envelope_with_one_ac() -> dict[str, Any]:
    return {
        "status": "pass",
        "artifacts": ["evidence/x.txt"],
        "findings": [],
        "rationale": "ok",
        "ac_results": [
            {
                "ac_id": "AC-1",
                "status": "pass",
                "assertions": ["verify: x"],
                "evidence_refs": [
                    {"path": "evidence/x.txt", "tier": "tier-1-mechanical"}
                ],
                "semantic_verification": "not_applicable",
            }
        ],
    }


def _heuristic_finding_dict(
    *, fid: str, title: str, location: str = ""
) -> dict[str, Any]:
    return {
        "id": fid,
        "source": "qa",
        "title": title,
        "detail": "exploratory observation",
        "location": location,
        "bucket": "decision_needed",
        "severity": "MED",
        "verification_mode": "exploratory-heuristic",
    }


def _heuristic_skipped_emission_dict(sub_classification: str) -> dict[str, Any]:
    return {
        "marker_class": "heuristic-skipped",
        "sub_classification": sub_classification,
        "story_id": "auto-001",
    }


@pytest.fixture
def heuristic_registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(
        marker_classes=frozenset(
            {"heuristic-skipped", "plan-drift-detected", "review-layer-failed"}
        )
    )


def test_exploratory_heuristic_findings_subsection_with_findings_only(
    heuristic_registry: MarkerClassRegistry,
) -> None:
    envelope = _qa_envelope_with_one_ac()
    envelope["findings"] = [
        _heuristic_finding_dict(
            fid="heuristic-empty-state-001",
            title="empty-state heuristic",
            location="src/x.tsx:1",
        ),
        _heuristic_finding_dict(
            fid="heuristic-error-state-001", title="error-state heuristic"
        ),
    ]
    body = bundle_assembly._render_per_ac_section(
        envelope, marker_registry=heuristic_registry
    )
    assert "### Exploratory heuristic findings" in body
    assert "[qa] `heuristic-empty-state-001`" in body
    assert "[qa] `heuristic-error-state-001`" in body
    assert "bmad-automation:marker heuristic-skipped" not in body


def test_exploratory_heuristic_findings_subsection_with_emissions_only(
    heuristic_registry: MarkerClassRegistry,
) -> None:
    envelope = _qa_envelope_with_one_ac()
    envelope["heuristic_skipped_emissions"] = [
        _heuristic_skipped_emission_dict("auth-boundary")
    ]
    body = bundle_assembly._render_per_ac_section(
        envelope, marker_registry=heuristic_registry
    )
    assert "### Exploratory heuristic findings" in body
    assert "Heuristic auth-boundary skipped" in body
    assert "<!-- bmad-automation:marker heuristic-skipped: auth-boundary -->" in body


def test_exploratory_heuristic_findings_subsection_with_findings_and_emissions(
    heuristic_registry: MarkerClassRegistry,
) -> None:
    envelope = _qa_envelope_with_one_ac()
    envelope["findings"] = [
        _heuristic_finding_dict(
            fid="heuristic-empty-state-001", title="empty-state observation"
        )
    ]
    envelope["heuristic_skipped_emissions"] = [
        _heuristic_skipped_emission_dict("error-state"),
        _heuristic_skipped_emission_dict("auth-boundary"),
    ]
    body = bundle_assembly._render_per_ac_section(
        envelope, marker_registry=heuristic_registry
    )
    finding_idx = body.index("[qa] `heuristic-empty-state-001`")
    error_emission_idx = body.index("Heuristic error-state skipped")
    auth_emission_idx = body.index("Heuristic auth-boundary skipped")
    assert finding_idx < error_emission_idx < auth_emission_idx


def test_exploratory_heuristic_findings_subsection_omitted_when_both_empty(
    heuristic_registry: MarkerClassRegistry,
) -> None:
    envelope = _qa_envelope_with_one_ac()
    body = bundle_assembly._render_per_ac_section(
        envelope, marker_registry=heuristic_registry
    )
    assert "### Exploratory heuristic findings" not in body


def test_exploratory_heuristic_findings_subsection_marker_validate_emission_called_per_emission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The per-emission ``validate_marker_emission`` defense-in-depth
    call fires once per emission."""

    calls: list[str] = []

    def _counting_validate(registry: object, marker_class: str) -> None:
        calls.append(marker_class)

    monkeypatch.setattr(
        bundle_assembly, "validate_marker_emission", _counting_validate
    )
    registry = MarkerClassRegistry(marker_classes=frozenset({"heuristic-skipped"}))
    envelope = _qa_envelope_with_one_ac()
    envelope["heuristic_skipped_emissions"] = [
        _heuristic_skipped_emission_dict("empty-state"),
        _heuristic_skipped_emission_dict("error-state"),
        _heuristic_skipped_emission_dict("auth-boundary"),
    ]
    bundle_assembly._render_per_ac_section(envelope, marker_registry=registry)
    assert calls == ["heuristic-skipped"] * 3


def test_ac_driven_findings_not_rendered_by_per_ac_section_render_at_story_4_9(
    heuristic_registry: MarkerClassRegistry,
) -> None:
    """An AC-driven finding (no `verification_mode`) is NOT rendered
    in any AC-driven-findings sub-section at Story 4.9 (Story 4.13 may
    add that surface; THIS story explicitly does NOT preempt it)."""
    envelope = _qa_envelope_with_one_ac()
    envelope["findings"] = [
        {
            "id": "ac-driven-001",
            "source": "qa",
            "title": "AC-driven finding",
            "detail": "...",
            "location": "",
            "bucket": "patch",
            "severity": "LOW",
        }
    ]
    body = bundle_assembly._render_per_ac_section(
        envelope, marker_registry=heuristic_registry
    )
    assert "### Exploratory heuristic findings" not in body
    assert "ac-driven-001" not in body
    assert "AC-driven finding" not in body


def test_ordering_per_ac_then_plan_drift_then_heuristic_findings(
    heuristic_registry: MarkerClassRegistry,
) -> None:
    envelope = _qa_envelope_with_one_ac()
    envelope["findings"] = [
        _heuristic_finding_dict(
            fid="heuristic-empty-state-001", title="empty-state obs"
        )
    ]
    envelope["plan_drift"] = {
        "story_id": "auto-001",
        "prior_plan_status": "generated",
        "prior_ac_hash": "0" * 64,
        "current_ac_hash": "1" * 64,
    }
    envelope["heuristic_skipped_emissions"] = [
        {
            "marker_class": "heuristic-skipped",
            "sub_classification": "auth-boundary",
            "story_id": "auto-001",
        }
    ]
    body = bundle_assembly._render_per_ac_section(
        envelope, marker_registry=heuristic_registry
    )
    ac_idx = body.index("### AC-1")
    plan_drift_idx = body.index("### Plan drift detected")
    heuristic_idx = body.index("### Exploratory heuristic findings")
    assert ac_idx < plan_drift_idx < heuristic_idx
