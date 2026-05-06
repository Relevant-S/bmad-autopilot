"""Story 6.7 — Orchestrator-side marker-wiring integration smoke tests.

End-to-end integration tests for the recorder helpers + dispatch-boundary
composition seams + Story 6.1 loud-fail-block rendering with Story 6.7's
alphabetical-iteration normalization. Sibling to
:mod:`tests.test_loud_fail_block_smoke` /
:mod:`tests.test_evidence_linkability_smoke` per the per-feature
integration-test-isolation precedent.

Contract-coverage matrix (Story 6.7 AC-1 + AC-2 + AC-3 + AC-4):

    [x] (k) bundle assembly with seeded specialist-timeout marker
        recorded via :func:`record_specialist_timeout_marker` →
        loud-fail block renders ``specialist-timeout: timeout-exceeded``
        with interpolated actionable pointer
    [x] (l) bundle assembly with three hook-failed markers (one per
        hook) → loud-fail block renders all three in alphabetical
        sub-class order (``session-start`` → ``stop`` → ``subagent-stop``)
    [x] (m) bundle assembly with three context-near-limit markers
        (one per specialist) → loud-fail block renders all three with
        per-specialist sub-classification suffix
    [x] (n) bundle assembly with mixed Story 6.5 / 6.6 / 6.7 markers
        → loud-fail block iterates ALL in alphabetical order across
        base classes uniformly
    [x] (o) idempotency: a second invocation of
        :func:`record_specialist_timeout_marker` for the same
        ``(specialist, sub_cause)`` is a no-op; bundle has ONE not TWO
        H3 entries
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any

import pytest
import yaml

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.bundle_assembly import AssembleBundleResult, assemble_bundle
from loud_fail_harness.marker_wiring import (
    record_context_near_limit_marker,
    record_hook_failure_marker,
    record_specialist_timeout_marker,
)
from loud_fail_harness.run_state import CostToDateBySpecialist, RunState
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)


# --------------------------------------------------------------------------- #
# Fixtures + helpers                                                          #
# --------------------------------------------------------------------------- #


_STORY_ID = "sample-marker-wiring-001"
_RUN_ID = "run-2026-05-06-marker-wiring"
_BRANCH_NAME = f"bmad-automation/story/{_STORY_ID}"
_GENERATED_AT = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)


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
    return yaml.safe_load(
        (envelopes_dir / "dev-pass.yaml").read_text(encoding="utf-8")
    )


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


def _make_seed_run_state() -> RunState:
    """Build a minimal valid :class:`RunState` instance the recorder
    helpers compose against."""
    return RunState(
        schema_version="1.3",
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        current_state="done",
        branch_name=_BRANCH_NAME,
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )


def _write_run_state(rs_path: pathlib.Path, run_state: RunState) -> pathlib.Path:
    """Persist a :class:`RunState` to disk in the YAML form
    :func:`assemble_bundle` reads.

    The recorders return frozen :class:`RunState` instances; this helper
    serialises them via ``model_dump(mode="json")`` and re-keys for
    YAML-stability so the loaded run-state mirrors the in-memory state.
    """
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    payload = run_state.model_dump(mode="json")
    rs_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return rs_path


def _seed_log(
    logs_root: pathlib.Path,
    *,
    specialist: str,
    return_envelope: dict[str, Any],
) -> None:
    log_path = logs_root / _STORY_ID / _RUN_ID / "logs" / f"{specialist}-1.log"
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


def _seed_canonical_qa_evidence_file(repo_root: pathlib.Path) -> pathlib.Path:
    """Seed the canonical QA fixture's evidence_ref file so Story 6.6's
    bundle-render-time evidence-trace linkability validation resolves
    cleanly (parity with :mod:`tests.test_loud_fail_block_smoke`)."""
    evidence_path = (
        repo_root
        / "_bmad-output"
        / "qa-evidence"
        / "sample-001"
        / "run-2026-04-29-001"
        / "ac1-http-200.log"
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("HTTP/1.1 200 OK\n", encoding="utf-8")
    return evidence_path


def _assemble_with_run_state(
    *,
    tmp_path: pathlib.Path,
    run_state: RunState,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> AssembleBundleResult:
    rs_path = _write_run_state(
        tmp_path / "_bmad" / "automation" / "run-state.yaml", run_state
    )
    logs_root = tmp_path / "qa-evidence"
    _seed_log(logs_root, specialist="dev", return_envelope=canonical_dev_envelope)
    _seed_log(
        logs_root,
        specialist="review-bmad",
        return_envelope=canonical_review_envelope,
    )
    _seed_log(logs_root, specialist="qa", return_envelope=canonical_qa_envelope)
    _seed_canonical_qa_evidence_file(tmp_path)
    return assemble_bundle(
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=tmp_path / "pr-bundles",
        marker_registry=runtime_marker_registry,
        generated_at=_GENERATED_AT,
        repo_root=tmp_path,
    )


# --------------------------------------------------------------------------- #
# (k) Specialist-timeout end-to-end                                           #
# --------------------------------------------------------------------------- #


def test_specialist_timeout_marker_renders_with_actionable_pointer(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-1: full bundle assembly with seeded run-state carrying a
    ``specialist-timeout: timeout-exceeded`` marker recorded via
    :func:`record_specialist_timeout_marker` renders the marker in the
    loud-fail block with full Story 6.2 actionable-pointer interpolation
    of ``{specialist}`` + ``{timeout_seconds}``."""
    seed = _make_seed_run_state()
    rs = record_specialist_timeout_marker(
        run_state=seed, specialist="dev", timeout_seconds=900
    )
    result = _assemble_with_run_state(
        tmp_path=tmp_path,
        run_state=rs,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = result.bundle_path.read_text(encoding="utf-8")
    assert "### specialist-timeout: timeout-exceeded" in body
    # Interpolated actionable pointer mentions the run-specific
    # specialist + timeout_seconds (taxonomy
    # pointer_context_fields: [specialist, timeout_seconds]).
    how_lines = [
        line for line in body.splitlines() if line.startswith("- How to enable:")
    ]
    timeout_how_line = next(
        line for line in how_lines if "Specialist dev" in line
    )
    assert "(900s)" in timeout_how_line


# --------------------------------------------------------------------------- #
# (l) Three hook-failed markers in alphabetical sub-class order               #
# --------------------------------------------------------------------------- #


def test_three_hook_failed_markers_render_in_alphabetical_order(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-2 + AC-4: full bundle assembly with three hook-failed markers
    (one per hook) renders all three in alphabetical sub-class order
    (``session-start`` → ``stop`` → ``subagent-stop``)."""
    rs = _make_seed_run_state()
    # Record in REVERSE alphabetical order so the alphabetical-render
    # contract is verifiable.
    for hook_name in ("subagent-stop", "stop", "session-start"):
        rs = record_hook_failure_marker(run_state=rs, hook_name=hook_name)
    result = _assemble_with_run_state(
        tmp_path=tmp_path,
        run_state=rs,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = result.bundle_path.read_text(encoding="utf-8")
    ses_idx = body.index("### hook-failed: session-start")
    stop_idx = body.index("### hook-failed: stop")
    sub_idx = body.index("### hook-failed: subagent-stop")
    assert ses_idx < stop_idx < sub_idx


# --------------------------------------------------------------------------- #
# (m) Three context-near-limit markers per-specialist                         #
# --------------------------------------------------------------------------- #


def test_three_context_near_limit_markers_render_with_per_specialist_suffix(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-3 + AC-4: full bundle assembly with three context-near-limit
    markers (one per specialist) renders all three with per-specialist
    sub-classification suffix; alphabetical sub-class iteration."""
    rs = _make_seed_run_state()
    for specialist in ("review-bmad", "qa", "dev"):
        rs = record_context_near_limit_marker(
            run_state=rs, specialist=specialist
        )
    result = _assemble_with_run_state(
        tmp_path=tmp_path,
        run_state=rs,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = result.bundle_path.read_text(encoding="utf-8")
    dev_idx = body.index("### context-near-limit: dev")
    qa_idx = body.index("### context-near-limit: qa")
    rev_idx = body.index("### context-near-limit: review-bmad")
    assert dev_idx < qa_idx < rev_idx
    # AC-6 — document the known first-emission-wins mismatch (Non-trivial
    # design decisions §2): when multiple specialists hit the limit, all
    # entries share the first specialist's context. The loop above emits
    # "review-bmad" first, but "dev" was the LAST emission; however the
    # FIRST emission into marker_contexts wins. Because "review-bmad" was
    # inserted first, its context ("Specialist review-bmad") is the one
    # stored. Phase 2 thickening (per-sub-classification context keys) is
    # tracked in _bmad-output/implementation-artifacts/deferred-work.md.
    assembled_bundle = body
    qa_lines = assembled_bundle.split("### context-near-limit: qa")[1].split("###")[0]
    assert "Specialist review-bmad" in qa_lines, (
        "qa entry renders first specialist's context — documented first-emission-wins tradeoff"
    )
    rev_lines = assembled_bundle.split("### context-near-limit: review-bmad")[1].split("###")[0]
    assert "Specialist review-bmad" in rev_lines, (
        "review-bmad entry renders first specialist's context — documented first-emission-wins tradeoff"
    )


# --------------------------------------------------------------------------- #
# (n) Cross-story alphabetical ordering                                       #
# --------------------------------------------------------------------------- #


def test_cross_story_alphabetical_ordering_byte_stable(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-4: bundle assembly with markers from THREE Epic-6 stories
    (6.5 cost-near-ceiling; 6.7 specialist-timeout + hook-failed +
    context-near-limit) renders ALL in alphabetical order across base
    classes uniformly."""
    rs = _make_seed_run_state()
    # Story 6.7 markers
    rs = record_specialist_timeout_marker(
        run_state=rs, specialist="dev", timeout_seconds=900
    )
    rs = record_hook_failure_marker(run_state=rs, hook_name="subagent-stop")
    rs = record_context_near_limit_marker(run_state=rs, specialist="dev")
    # Story 6.5 cost-near-ceiling marker (manually appended; the cost-
    # streaming substrate normally produces this via record_cost_streaming
    # but for the cross-story ordering test we synthesise it).
    rs = rs.model_copy(
        update={
            "active_markers": rs.active_markers + ("cost-near-ceiling: ceiling-crossed",),
        }
    )
    result = _assemble_with_run_state(
        tmp_path=tmp_path,
        run_state=rs,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = result.bundle_path.read_text(encoding="utf-8")
    indices = [
        body.index("### context-near-limit: dev"),
        body.index("### cost-near-ceiling: ceiling-crossed"),
        body.index("### hook-failed: subagent-stop"),
        body.index("### specialist-timeout: timeout-exceeded"),
    ]
    assert indices == sorted(indices)


# --------------------------------------------------------------------------- #
# (o) Idempotency — second recording attempt is a no-op                       #
# --------------------------------------------------------------------------- #


def test_specialist_timeout_recorder_idempotent_in_bundle(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-1 + Story 1.4 marker-permanence: a second invocation of
    :func:`record_specialist_timeout_marker` for the SAME
    ``(specialist, sub_cause)`` is a no-op; the assembled bundle has
    EXACTLY ONE ``### specialist-timeout: timeout-exceeded`` H3 entry,
    not two."""
    rs = _make_seed_run_state()
    # Two invocations with the same (specialist, sub_cause).
    rs = record_specialist_timeout_marker(
        run_state=rs, specialist="qa", timeout_seconds=600
    )
    rs = record_specialist_timeout_marker(
        run_state=rs, specialist="qa", timeout_seconds=600
    )
    result = _assemble_with_run_state(
        tmp_path=tmp_path,
        run_state=rs,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    body = result.bundle_path.read_text(encoding="utf-8")
    assert body.count("### specialist-timeout: timeout-exceeded") == 1


# --------------------------------------------------------------------------- #
# Canonical PR-bundle fixture regression test                                 #
# --------------------------------------------------------------------------- #


def test_canonical_marker_wiring_bundle_fixture_matches_assembler_output(
    tmp_path: pathlib.Path,
    canonical_dev_envelope: dict[str, Any],
    canonical_review_envelope: dict[str, Any],
    canonical_qa_envelope: dict[str, Any],
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Story 6.7 AC-6: the canonical PR-bundle fixture
    `examples/pr-bundles/pr-bundle-marker-wiring.md` byte-matches the
    post-6.7 assembler output for its seeded run-state (three Story 6.7
    markers — specialist-timeout, hook-failed, context-near-limit). The
    fixture body (after the contract-header strip) is byte-identical to
    `assemble_bundle`'s output. Mirrors Story 6.1's
    `test_canonical_walking_skeleton_bundle_fixture_matches_assembler_output`
    + Story 6.6's
    `test_canonical_dangling_evidence_ref_bundle_fixture_matches_assembler_output`
    precedents.
    """
    import re

    fixture_path = (
        find_repo_root()
        / "examples"
        / "pr-bundles"
        / "pr-bundle-marker-wiring.md"
    )
    assert fixture_path.exists(), (
        "examples/pr-bundles/pr-bundle-marker-wiring.md is missing from "
        "the repository — the fixture must be committed."
    )
    fixture_body = fixture_path.read_text(encoding="utf-8")
    body_after_header = re.sub(
        r"^<!--.*?-->\s*", "", fixture_body, count=1, flags=re.DOTALL
    )

    seed = _make_seed_run_state()
    rs = record_specialist_timeout_marker(
        run_state=seed, specialist="dev", timeout_seconds=900
    )
    rs = record_hook_failure_marker(run_state=rs, hook_name="subagent-stop")
    rs = record_context_near_limit_marker(run_state=rs, specialist="dev")

    result = _assemble_with_run_state(
        tmp_path=tmp_path,
        run_state=rs,
        canonical_dev_envelope=canonical_dev_envelope,
        canonical_review_envelope=canonical_review_envelope,
        canonical_qa_envelope=canonical_qa_envelope,
        runtime_marker_registry=runtime_marker_registry,
    )
    assembled_body = result.bundle_path.read_text(encoding="utf-8")
    assert assembled_body == body_after_header, (
        "canonical marker-wiring fixture must match assembler output "
        "byte-for-byte (modulo contract-header strip); regenerate the "
        "fixture if the assembler's rendering intentionally changed."
    )
