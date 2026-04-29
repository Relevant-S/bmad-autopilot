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
    return yaml.safe_load(
        (envelopes_dir / "review-pass-acceptance-auditor.yaml").read_text(encoding="utf-8")
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
        "schema_version": "1.0",
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
    result, _ = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
        flags=thickening_flags,  # default — all four return False
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
    _, bundle_path = _assemble(
        tmp_path=tmp_path,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = bundle_path.read_text(encoding="utf-8")
    # Canonical review envelope has a single 'review-001' finding.
    assert "review-001" in body
    assert "Story doc references epics.md line numbers verbatim" in body
    assert "bucket: `defer`" in body
    assert "severity: `LOW`" in body


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
    # Review surface (finding id)
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
