"""End-to-end integration tests for the Story 6.1 loud-fail block surface.

This module is the FIRST integration-test consumer of Story 6.1's
loud-fail-block sub-renderer wired into BOTH variants (merge-ready via
:func:`loud_fail_harness.bundle_assembly.assemble_bundle` and escalation
via :func:`loud_fail_harness.bundle_assembly_escalation.assemble_escalation_bundle`).
Sibling to the Story 2.13 ``test_walking_skeleton_smoke.py`` per the
retro-of-5.5 separation-of-concerns precedent (the loud-fail block is
its own integration concern; folding the tests into the existing smoke
module would conflate concerns).

Contract-coverage matrix (Story 6.1 AC-1 + AC-3 + AC-4 + AC-5 + AC-6):

    [x] merge-ready bundle with active markers renders the H2 block
        with one entry per marker (AC-1 four-element shape)
        → test_merge_ready_bundle_renders_loud_fail_block_with_active_markers
    [x] merge-ready bundle with zero active markers renders the
        ``## ✓ Loud-Fail Markers — None`` sentinel (AC-3)
        → test_merge_ready_bundle_renders_loud_fail_none_sentinel_with_zero_markers
    [x] merge-ready bundle with multiple markers renders entries in
        active_markers tuple order (AC-1)
        → test_merge_ready_bundle_renders_multiple_loud_fail_markers_in_order
    [x] escalation bundle with active markers renders the loud-fail
        block at the same structural position as merge-ready (AC-5)
        → test_escalation_bundle_renders_loud_fail_block_at_same_position
    [x] escalation bundle with zero active markers renders the
        ``## ✓ Loud-Fail Markers — None`` sentinel (AC-3 + AC-5)
        → test_escalation_bundle_renders_loud_fail_none_sentinel_with_zero_markers
    [x] ``walking-skeleton-bundle`` is absent from new merge-ready
        runs as a structural consequence of ``is_loud_fail_block_present()``
        returning True (AC-4)
        → test_walking_skeleton_marker_absent_from_new_merge_ready_runs_after_loud_fail_block_lands
    [x] block's structural shape is byte-identical across variants for
        the same active_markers set (AC-5 single-rendering-core)
        → test_loud_fail_block_byte_identical_across_variants
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any

import pytest
import yaml

from loud_fail_harness import bundle_assembly
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.bundle_assembly import (
    AssembleBundleResult,
    assemble_bundle,
)
from loud_fail_harness.bundle_assembly_escalation import assemble_escalation_bundle
from loud_fail_harness.retry_budget_exhaustion import (
    ExhaustionContext,
    ExhaustionTrigger,
)
from loud_fail_harness.run_state import RetryAttempt
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


_STORY_ID = "sample-loud-fail-001"
_RUN_ID = "run-2026-05-05-loud-fail"
_BRANCH_NAME = f"bmad-automation/story/{_STORY_ID}"
_GENERATED_AT = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def repo_root() -> pathlib.Path:
    return find_repo_root()


@pytest.fixture(scope="module")
def envelopes_dir(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "examples" / "envelopes"


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


@pytest.fixture(scope="module")
def canonical_dev_envelope(envelopes_dir: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load((envelopes_dir / "dev-pass.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def canonical_review_envelope(envelopes_dir: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(
        (envelopes_dir / "review-pass-three-layer.yaml").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def canonical_qa_envelope(envelopes_dir: pathlib.Path) -> dict[str, Any]:
    return yaml.safe_load(
        (envelopes_dir / "qa-pass-ac1-tier1.yaml").read_text(encoding="utf-8")
    )


# --------------------------------------------------------------------------- #
# Helpers (mirror test_bundle_assembly.py's _seed_three_logs / _assemble)     #
# --------------------------------------------------------------------------- #


def _write_run_state(
    rs_path: pathlib.Path,
    *,
    active_markers: tuple[str, ...],
    story_id: str = _STORY_ID,
) -> pathlib.Path:
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "1.1",
        "story_id": story_id,
        "run_id": _RUN_ID,
        "current_state": "done",
        "branch_name": _BRANCH_NAME,
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": [],
        "active_markers": list(active_markers),
        "cost_to_date_by_specialist": {},
    }
    rs_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return rs_path


def _seed_log(
    logs_root: pathlib.Path,
    *,
    specialist: str,
    return_envelope: dict[str, Any],
) -> None:
    log_path = (
        logs_root / _STORY_ID / _RUN_ID / "logs" / f"{specialist}-1.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_payload = {
        "dispatched_specialist": specialist,
        "story_id": _STORY_ID,
        "attempt_number": 1,
        "agent_definition_path": f"agents/{specialist}.md",
        "acceptance_criteria": [{"ac_id": "AC-1", "text": "stub"}],
        "dispatch_timestamp": _GENERATED_AT.isoformat(),
        "return_timestamp": _GENERATED_AT.isoformat(),
        "return_envelope": return_envelope,
    }
    log_path.write_text(json.dumps(log_payload, indent=2), encoding="utf-8")


def _assemble_merge_ready(
    *,
    tmp_path: pathlib.Path,
    active_markers: tuple[str, ...],
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> AssembleBundleResult:
    rs_path = _write_run_state(
        tmp_path / "_bmad" / "automation" / "run-state.yaml",
        active_markers=active_markers,
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_log(logs_root, specialist="dev", return_envelope=canonical_dev_envelope)
    _seed_log(
        logs_root, specialist="review-bmad", return_envelope=canonical_review_envelope
    )
    _seed_log(logs_root, specialist="qa", return_envelope=canonical_qa_envelope)
    bundle_root = tmp_path / "pr-bundles"
    return assemble_bundle(
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        marker_registry=runtime_marker_registry,
        generated_at=_GENERATED_AT,
    )


def _build_exhaustion_context(
    *, active_markers: tuple[str, ...]
) -> ExhaustionContext:
    return ExhaustionContext(
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        branch_name=_BRANCH_NAME,
        retry_history=(
            RetryAttempt(
                retry_attempt=1,
                retry_reason="dev-rejected: change-request bucket",
            ),
        ),
        last_envelope=None,
        last_retry_directive=None,
        scope_violation_diagnostic=None,
        bundle_artifact_path="_bmad-output/escalation-bundles/x/y/escalation.md",
        active_markers=active_markers,
    )


# --------------------------------------------------------------------------- #
# Story 6.1 AC-1 / AC-3 / AC-6 — merge-ready variant                          #
# --------------------------------------------------------------------------- #


def test_merge_ready_bundle_renders_loud_fail_block_with_active_markers(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-1 + AC-6 (a): seed ``run_state.active_markers`` with one
    marker, assert the rendered bundle has the H2 + one H3 entry with
    the four-element shape (H3 header + three bullets) at the
    structural position contract — first content section after the
    title metadata block + Walking Skeleton header.
    """
    result = _assemble_merge_ready(
        tmp_path=tmp_path,
        active_markers=("Tier-3-not-configured",),
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = result.bundle_path.read_text(encoding="utf-8")

    # H2 block + one H3 entry.
    assert "## ⚠️ Loud-Fail Markers" in body
    assert "### Tier-3-not-configured" in body

    # Four-element shape: H3 + three bullets.
    assert "- Sub-classification: none" in body
    assert "- Diagnostic pointer:" in body
    assert "- How to enable:" in body

    # Structural position: loud-fail H2 appears AFTER walking-skeleton
    # H2 + header_text and BEFORE Per-AC results / Review findings / Dev.
    walking_idx = body.index("## ⚠️ Walking Skeleton Mode")
    loud_fail_idx = body.index("## ⚠️ Loud-Fail Markers")
    per_ac_idx = body.index("## Per-AC results")
    review_idx = body.index("## Review findings")
    dev_idx = body.index("## Dev")
    assert walking_idx < loud_fail_idx < per_ac_idx < review_idx < dev_idx


def test_merge_ready_bundle_renders_loud_fail_none_sentinel_with_zero_markers(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-3: zero active markers → ``## ✓ Loud-Fail Markers — None``
    sentinel; the block's *presence* is structural per AC-3.
    """
    result = _assemble_merge_ready(
        tmp_path=tmp_path,
        active_markers=(),
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = result.bundle_path.read_text(encoding="utf-8")
    assert "## ✓ Loud-Fail Markers — None" in body
    assert "No loud-fail markers are active on this run." in body
    # The non-sentinel H2 is NOT in the body when active_markers == ().
    assert "## ⚠️ Loud-Fail Markers\n" not in body


def test_merge_ready_bundle_renders_multiple_loud_fail_markers_in_order(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-1: multiple markers render in active_markers tuple order
    (preserved as emitted; not re-sorted alphabetically).
    """
    result = _assemble_merge_ready(
        tmp_path=tmp_path,
        # Tier-3-not-configured comes BEFORE plan-drift-detected in tuple
        # order, but AFTER it alphabetically — alphabetic sort would put
        # plan-drift-detected first.
        active_markers=("Tier-3-not-configured", "plan-drift-detected"),
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = result.bundle_path.read_text(encoding="utf-8")
    tier3_idx = body.index("### Tier-3-not-configured")
    plan_drift_idx = body.index("### plan-drift-detected")
    assert tier3_idx < plan_drift_idx


# --------------------------------------------------------------------------- #
# Story 6.1 AC-4 — walking-skeleton marker structural inversion               #
# --------------------------------------------------------------------------- #


def test_walking_skeleton_marker_absent_from_new_merge_ready_runs_after_loud_fail_block_lands(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-4: with the post-6.1 production thickening_flags
    (``is_loud_fail_block_present()`` returns True via the structural
    derivation), the structural rule
    ``if flags.is_loud_fail_block_present(): return ()`` at
    :func:`_emit_walking_skeleton_marker` fires; the
    ``walking-skeleton-bundle`` marker stops emitting on new runs as a
    structural consequence — NOT a special-case suppression branch.
    """
    result = _assemble_merge_ready(
        tmp_path=tmp_path,
        active_markers=(),
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = result.bundle_path.read_text(encoding="utf-8")
    assert "<!-- bmad-automation:marker walking-skeleton-bundle -->" not in body
    assert "walking-skeleton-bundle" not in result.emitted_markers
    assert result.emitted_markers == ()


# --------------------------------------------------------------------------- #
# Story 6.1 AC-5 — escalation variant + single-rendering-core invariant       #
# --------------------------------------------------------------------------- #


def test_escalation_bundle_renders_loud_fail_block_at_same_position(
    tmp_path: pathlib.Path,
    repo_root: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-5: escalation bundles emit the loud-fail block at the SAME
    structural position as merge-ready (after the title metadata block
    + Walking Skeleton header, BEFORE ``## Escalation rationale`` /
    other escalation-specific H2s). The block's structural shape is
    byte-identical for the same active_markers set (single-rendering-
    core invariant per Story 5.8 AC-4).
    """
    context = _build_exhaustion_context(
        active_markers=("retry-budget-exhausted", "Tier-3-not-configured")
    )
    result = assemble_escalation_bundle(
        context,
        repo_root=tmp_path,
        schemas_root=repo_root,
        marker_registry=runtime_marker_registry,
        generated_at=_GENERATED_AT,
    )
    body = result.bundle_path.read_text(encoding="utf-8")

    # H2 block + per-marker H3 entries.
    assert "## ⚠️ Loud-Fail Markers" in body
    assert "### retry-budget-exhausted" in body
    assert "### Tier-3-not-configured" in body

    # Structural position: loud-fail H2 appears AFTER walking-skeleton
    # header and BEFORE the escalation-specific sections per AC-5.
    walking_idx = body.index("## ⚠️ Walking Skeleton Mode")
    loud_fail_idx = body.index("## ⚠️ Loud-Fail Markers")
    rationale_idx = body.index("## Escalation rationale")
    outstanding_idx = body.index("## Outstanding findings")
    retry_history_idx = body.index("## Retry history")
    deferred_idx = body.index("## Deferred-work pointer")
    preservation_idx = body.index("## Preservation")
    assert walking_idx < loud_fail_idx < rationale_idx
    assert loud_fail_idx < outstanding_idx
    assert loud_fail_idx < retry_history_idx
    assert loud_fail_idx < deferred_idx
    assert loud_fail_idx < preservation_idx


def test_escalation_bundle_renders_loud_fail_none_sentinel_with_zero_markers(
    tmp_path: pathlib.Path,
    repo_root: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-3 + AC-5: escalation variant with zero active markers
    renders the same ``## ✓ Loud-Fail Markers — None`` sentinel as
    merge-ready (the block's *presence* is structural across
    variants).
    """
    context = _build_exhaustion_context(active_markers=())
    result = assemble_escalation_bundle(
        context,
        repo_root=tmp_path,
        schemas_root=repo_root,
        marker_registry=runtime_marker_registry,
        generated_at=_GENERATED_AT,
    )
    body = result.bundle_path.read_text(encoding="utf-8")
    assert "## ✓ Loud-Fail Markers — None" in body
    assert "No loud-fail markers are active on this run." in body


def test_loud_fail_block_byte_identical_across_variants(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-5 single-rendering-core invariant: both variants invoke the
    SAME :func:`_render_loud_fail_block` sub-renderer; the rendered
    block is byte-identical for the same active_markers set
    regardless of which variant invokes the helper. The function is
    defined exactly ONCE in :mod:`loud_fail_harness.bundle_assembly`;
    :mod:`loud_fail_harness.bundle_assembly_escalation` imports it.
    """
    from loud_fail_harness import bundle_assembly_escalation

    # Identity assertion: the escalation module's symbol IS the
    # merge-ready module's symbol (same object identity).
    assert (
        bundle_assembly_escalation._render_loud_fail_block
        is bundle_assembly._render_loud_fail_block
    )

    markers = ("Tier-3-not-configured",)
    rendered_via_merge_ready = bundle_assembly._render_loud_fail_block(
        markers, marker_registry=runtime_marker_registry
    )
    rendered_via_escalation = bundle_assembly_escalation._render_loud_fail_block(
        markers, marker_registry=runtime_marker_registry
    )
    assert rendered_via_merge_ready == rendered_via_escalation
