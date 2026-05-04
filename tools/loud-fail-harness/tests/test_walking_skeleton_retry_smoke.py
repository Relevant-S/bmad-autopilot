"""End-to-end retry-domain smoke runs (Story 5.9 AC-4).

This module is the integration-test consumer that exercises Epic-5's
retry + escalation substrate end-to-end against the three retry-domain
fixtures landed by Story 5.9 — sibling-of and additive-to Story 2.13's
``test_walking_skeleton_smoke.py``. Module-placement rationale (Story
5.9 Subtask 5.1): a separate sibling module keeps the Story 2.13 module
scoped to the Epic-2 happy-path lifecycle while this module covers the
Epic-5-domain paths (retry / scope-violation / budget-exhaustion).

Each test asserts the structural witnesses Story 5.9 AC-4 calls out:

    (a) the lifecycle reaches the expected terminal state — ``done`` for
        the patch-fix path, ``escalated`` for the scope-violation +
        budget-exhaustion paths;
    (b) the rendered bundle on disk contains the expected sections
        (``## Retry history`` + escalation-rationale for the escalation
        variants; the run-state's ``retry_history`` field is populated
        and the on-disk retry-history artifacts exist for the patch-fix
        path);
    (c) the marker-emission set contains ``walking-skeleton-bundle``
        (still emits because ``is_loud_fail_block_present()`` is
        ``False`` per AC-3);
    (d) the per-trigger marker (``scope-assertion-violation`` for the
        violation path; ``retry-budget-exhausted`` for the exhaustion
        path) is present on the diagnostic + the bundle's machine-
        readable payload;
    (e) the rendered Walking Skeleton header does NOT contain the
        ``"No retry"`` sentence — the post-Story-5.9 structural witness
        of the ``is_retry_present()`` flip.

All filesystem writes are scoped under ``tmp_path``; no writes outside
the test sandbox per the Story 2.13 sandboxing convention.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any

import yaml

from loud_fail_harness import bundle_assembly, thickening_flags
from loud_fail_harness.bundle_assembly import assemble_bundle, load_marker_class_registry
from loud_fail_harness.bundle_assembly_escalation import (
    AssembleEscalationBundleResult,
    assemble_escalation_bundle,
    validate_payload_against_schema,
)
from loud_fail_harness.retry_budget_exhaustion import (
    ExhaustionTrigger,
    compute_escalation_bundle_path,
    record_retry_budget_exhaustion,
)
from loud_fail_harness.retry_history import (
    RetryRoundArtifacts,
    persist_retry_round,
)
from loud_fail_harness.run_state import (
    CostToDateBySpecialist,
    LastRetryDirective,
    RetryAttempt,
    RunState,
    StoryDocCallbackResult,
    advance_run_state,
)
from loud_fail_harness.scope_assertion import (
    ScopeAssertionDiagnostic,
    verify_scope_assertion,
)


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
_FIXED_GENERATED_AT = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Shared helpers (reuse the Story 2.13 / 4.10 / 5.6 patterns)                 #
# --------------------------------------------------------------------------- #


def _write_run_state_yaml_with_retry_history(
    rs_path: pathlib.Path,
    *,
    story_id: str,
    branch_name: str,
    current_state: str,
    retry_history: list[dict[str, Any]],
) -> None:
    """Write a run-state YAML with a thickened retry_history field per
    Story 5.5's externalization shape."""
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "1.2",
        "story_id": story_id,
        "run_id": "run-2026-05-05-smoke",
        "current_state": current_state,
        "branch_name": branch_name,
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": retry_history,
        "active_markers": [],
        "cost_to_date_by_specialist": {},
    }
    rs_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _seed_dispatch_log(
    logs_root: pathlib.Path,
    *,
    story_id: str,
    run_id: str,
    specialist: str,
    return_envelope: dict[str, Any],
    attempt_number: int = 1,
) -> pathlib.Path:
    """Mirror of ``test_bundle_assembly._seed_dispatch_log`` — write a
    minimal dispatch log the merge-ready assembler can read.
    """
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
        "dispatch_timestamp": "2026-05-05T12:00:00+00:00",
        "return_timestamp": "2026-05-05T12:01:00+00:00",
        "return_envelope": return_envelope,
    }
    log_path.write_text(json.dumps(log_payload, indent=2), encoding="utf-8")
    return log_path


def _make_canned_envelopes() -> dict[str, dict[str, Any]]:
    """Three canned conformant envelopes: Dev / Review-BMAD / QA."""
    return {
        "dev": {
            "status": "pass",
            "artifacts": ["bmad-autopilot/foo.py"],
            "findings": [],
            "rationale": "Dev fix-only retry round closed the patch-bucket finding",
            "proposed_commit_message": "fix: address review patch finding",
            "scope_expanded_to": [],
        },
        "review-bmad": {
            "status": "pass",
            "artifacts": [],
            "findings": [],
            "rationale": "post-retry review-pass: no findings remain",
            "failed_layers": [],
        },
        "qa": {
            "status": "pass",
            "artifacts": ["bmad-autopilot/foo.py"],
            "findings": [],
            "rationale": "AC-1 verified post-retry",
            "ac_results": [
                {
                    "ac_id": "AC-1",
                    "status": "pass",
                    "assertions": ["the patch-fix output file exists"],
                    "evidence_refs": [
                        {"path": "out.log", "tier": "tier-1-mechanical"}
                    ],
                    "semantic_verification": "not_applicable",
                }
            ],
        },
    }


def _stub_appender(collected: list[dict[str, Any]]) -> Any:
    def _appender(event: dict[str, Any]) -> None:
        collected.append(event)

    return _appender


def _make_capturing_assembler(
    *,
    repo_root: pathlib.Path,
    captured: list[AssembleEscalationBundleResult],
) -> Any:
    """A capturing wrapper around :func:`assemble_escalation_bundle` —
    composes the Story 5.8 production path while exposing the
    :class:`AssembleEscalationBundleResult` to the test for
    marker-set + payload assertions.
    """

    def _assembler(context: Any) -> None:
        result = assemble_escalation_bundle(
            context,
            repo_root=repo_root,
            generated_at=_FIXED_GENERATED_AT,
        )
        captured.append(result)

    return _assembler


# --------------------------------------------------------------------------- #
# AC-4 path 1 — patch-bucket retry that succeeds (merge-ready bundle)         #
# --------------------------------------------------------------------------- #


def test_walking_skeleton_smoke_patch_fix_path(tmp_path: pathlib.Path) -> None:
    """Patch-bucket retry path: a Dev fix-only retry round closes a
    review patch-bucket finding, the lifecycle reaches ``done``, and
    the merge-ready bundle's Walking Skeleton header omits the
    ``"No retry"`` sentence (post-Story-5.9 structural witness).

    Per Story 5.9 AC-4 + the AC-5 ZERO-MODIFICATIONS-to-bundle_assembly
    invariant, the merge-ready bundle's section enumeration is
    Epic-2-shape; the upstream evidence of the retry round is the
    populated ``run_state.retry_history`` field + the on-disk
    ``_bmad-output/retry-history/{story_id}/{round_id}/`` artifact
    landed by Story 5.5's ``persist_retry_round``. THIS test consumes
    BOTH structural surfaces.
    """
    fixture_path = _FIXTURES_DIR / "sample-story-retry-patch-fix.md"
    assert fixture_path.exists(), (
        f"missing Story 5.9 fixture {fixture_path}"
    )

    story_id = "sample-story-retry-patch-fix"
    run_id = "run-2026-05-05-smoke"

    # Persist a retry round to disk under tmp_path-scoped repo_root.
    round_artifacts = RetryRoundArtifacts(
        round_id="round-01",
        retry_attempt=1,
        findings=(
            {
                "id": "F-1",
                "title": "review patch-bucket finding",
                "source": "blind",
                "location": "bmad-autopilot/foo.py:42",
            },
        ),
        scope_affected_files=("bmad-autopilot/foo.py",),
        scope_expanded_to=(),
        actual_diff_files=("bmad-autopilot/foo.py",),
        created_at="2026-05-05T12:00:30+00:00",
    )
    attempt_ref = persist_retry_round(
        round=round_artifacts,
        repo_root=tmp_path,
        story_id=story_id,
        retry_reason="patch-bucket-retry",
    )

    # On-disk artifact from Story 5.5 was written under tmp_path.
    on_disk_artifact = (
        tmp_path
        / "_bmad-output"
        / "retry-history"
        / story_id
        / "round-01"
        / "artifacts.yaml"
    )
    assert on_disk_artifact.is_relative_to(tmp_path)
    assert on_disk_artifact.exists(), (
        f"Story 5.5 persist_retry_round must materialize artifact at "
        f"{on_disk_artifact}"
    )

    # Compose run-state with the thickened retry_history entry.
    rs_path = tmp_path / "_bmad" / "automation" / "run-state.yaml"
    _write_run_state_yaml_with_retry_history(
        rs_path,
        story_id=story_id,
        branch_name=f"bmad-automation/story/{story_id}",
        current_state="done",
        retry_history=[
            {
                "retry_attempt": attempt_ref.retry_attempt,
                "retry_reason": attempt_ref.retry_reason,
                "round_id": attempt_ref.round_id,
                "path": attempt_ref.path,
            }
        ],
    )

    # Seed Dev / Review-BMAD / QA dispatch logs under tmp_path.
    logs_root = tmp_path / "qa-evidence"
    canned = _make_canned_envelopes()
    for specialist, envelope in canned.items():
        _seed_dispatch_log(
            logs_root,
            story_id=story_id,
            run_id=run_id,
            specialist=specialist,
            return_envelope=envelope,
        )

    # Assemble the merge-ready bundle against the production thickening_flags
    # module (post-5.9 substrate state — three flags True, one flag False).
    bundle_root = tmp_path / "pr-bundles"
    result = assemble_bundle(
        story_id=story_id,
        run_id=run_id,
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        marker_registry=load_marker_class_registry(),
        thickening_flags=thickening_flags,
        generated_at=_FIXED_GENERATED_AT,
    )

    # (a) run-state fixture: retry_history populated + on-disk artifact present.
    # Note: assemble_bundle does not write run-state; current_state was pre-seeded
    # to "done" by the test fixture — assertions below verify the YAML round-trip
    # and the on-disk Story 5.5 artifact, not a lifecycle transition.
    on_disk_state = yaml.safe_load(rs_path.read_text(encoding="utf-8"))
    assert len(on_disk_state["retry_history"]) == 1
    persisted_entry = on_disk_state["retry_history"][0]
    assert persisted_entry["retry_attempt"] == 1
    assert persisted_entry["retry_reason"] == "patch-bucket-retry"
    assert persisted_entry["round_id"] == "round-01"
    assert persisted_entry["path"].endswith("artifacts.yaml")
    assert on_disk_artifact.exists()
    persisted_artifact = yaml.safe_load(on_disk_artifact.read_text(encoding="utf-8"))
    assert persisted_artifact["round_id"] == "round-01"
    assert persisted_artifact["retry_attempt"] == 1

    # (c) marker-emission set contains walking-skeleton-bundle.
    bundle_text = result.bundle_path.read_text(encoding="utf-8")
    assert (
        "<!-- bmad-automation:marker walking-skeleton-bundle -->" in bundle_text
    )
    assert "walking-skeleton-bundle" in result.emitted_markers

    # (e) Walking Skeleton header omits the "No retry" sentence — the
    # post-Story-5.9 structural witness of the is_retry_present() flip.
    assert "No retry" not in result.header_text
    assert "No retry" not in bundle_text

    # The other prior-flip invariants are preserved.
    assert "Single-layer review (Epic 3 thickens" not in bundle_text
    assert "Tier-1 evidence only" not in bundle_text

    # Epic 6 still owes its thickening — "No loud-fail block" remains in the
    # rendered header (this is the only bullet at the post-5.9 substrate state).
    assert "No loud-fail block" in result.header_text

    # tmp_path scoping: every emitted artifact lives inside the sandbox.
    assert result.bundle_path.is_relative_to(tmp_path)
    assert rs_path.is_relative_to(tmp_path)
    assert on_disk_artifact.is_relative_to(tmp_path)


# --------------------------------------------------------------------------- #
# AC-4 path 2 — scope-assertion violation (escalation bundle)                 #
# --------------------------------------------------------------------------- #


def test_walking_skeleton_smoke_scope_violation_path(tmp_path: pathlib.Path) -> None:
    """Scope-assertion violation path: a Dev fix-only retry round expands
    ``affected_files`` beyond the contracted scope; ``verify_scope_assertion``
    surfaces the violation; ``record_retry_budget_exhaustion`` fires with
    ``trigger=SCOPE_ASSERTION_VIOLATION``; Story 5.8's escalation-bundle
    assembler renders a scope-assertion-violation bundle.
    """
    fixture_path = _FIXTURES_DIR / "sample-story-retry-scope-violation.md"
    assert fixture_path.exists(), (
        f"missing Story 5.9 fixture {fixture_path}"
    )

    story_id = "sample-story-retry-scope-violation"
    run_id = "run-2026-05-05-smoke"

    # Story 5.4: verify the scope assertion against an out-of-scope expansion.
    scope_result = verify_scope_assertion(
        affected_files=("bmad-autopilot/foo.py",),
        scope_expanded_to=(),
        actual_files=("bmad-autopilot/foo.py", "bmad-autopilot/unrelated.py"),
    )
    assert scope_result.is_violation is True, (
        "fixture invariant: actual_files must violate the declared scope "
        "to exercise the scope-violation escalation path"
    )
    assert scope_result.violating_files == ("bmad-autopilot/unrelated.py",)

    diagnostic = ScopeAssertionDiagnostic(
        story_id=story_id,
        retry_round=1,
        violating_files=scope_result.violating_files,
        declared_scope=scope_result.declared_scope,
        declared_expansion=scope_result.declared_expansion,
    )

    # Compose pre-escalation run-state (in-progress, with a prior retry round).
    state = RunState(
        schema_version="1.2",
        story_id=story_id,
        run_id=run_id,
        current_state="in-progress",
        branch_name=f"bmad-automation/story/{story_id}",
        dispatched_specialist=None,
        last_envelope={
            "status": "fail",
            "findings": [
                {
                    "id": "F-1",
                    "title": "scope-assertion-violation diagnostic",
                    "source": "blind",
                    "location": "bmad-autopilot/unrelated.py:1",
                }
            ],
        },
        pending_qa_dispatch_payload=None,
        retry_history=(
            RetryAttempt(retry_attempt=1, retry_reason="patch-bucket-retry"),
        ),
        active_markers=(),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
        last_retry_directive=LastRetryDirective(
            retry_mode="fix-only", affected_files=("bmad-autopilot/foo.py",)
        ),
    )
    rs_path = tmp_path / "_bmad" / "automation" / "run-state.yaml"
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    advance_run_state(
        run_state_path=rs_path,
        next_state=state,
        story_doc_callback=lambda: StoryDocCallbackResult(accepted=True),
    )

    # Run the Story 5.6 escalation path with a capturing wrapper around
    # the Story 5.8 production assembler.
    captured_results: list[AssembleEscalationBundleResult] = []
    events: list[dict[str, Any]] = []
    record_result = record_retry_budget_exhaustion(
        run_state_path=rs_path,
        current_state=state,
        trigger=ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION,
        escalation_bundle_assembler=_make_capturing_assembler(
            repo_root=tmp_path, captured=captured_results
        ),
        event_log_appender=_stub_appender(events),
        repo_root=tmp_path,
        scope_violation_diagnostic=diagnostic,
    )

    # (a) lifecycle reaches escalated terminal state.
    assert record_result.advance_result.next_state.current_state == "escalated"
    on_disk = yaml.safe_load(rs_path.read_text(encoding="utf-8"))
    assert on_disk["current_state"] == "escalated"
    assert on_disk["branch_name"] == state.branch_name  # FR14 preservation

    # The escalation-fired event is emitted.
    assert len(events) == 1
    assert events[0]["event_class"] == "escalation-fired"
    assert events[0]["escalation_class"] == "retry-budget-exhausted"

    # (b) escalation bundle exists at the deterministic path with the
    # expected sections.
    assert len(captured_results) == 1
    bundle_result = captured_results[0]
    expected_bundle_path = compute_escalation_bundle_path(
        repo_root=tmp_path, story_id=story_id, run_id=run_id
    )
    assert bundle_result.bundle_path == expected_bundle_path
    assert expected_bundle_path.exists()
    body = expected_bundle_path.read_text(encoding="utf-8")
    assert "## ⚠️ Walking Skeleton Mode" in body
    assert "## Escalation rationale" in body
    assert "## Outstanding findings" in body
    assert "## Retry history" in body
    assert "## Deferred-work pointer" in body
    assert "## Preservation" in body
    assert "## Scope-assertion diagnostic" in body
    # The diagnostic's violating-files path is rendered.
    assert "bmad-autopilot/unrelated.py" in body

    # (c) walking-skeleton-bundle marker present on bundle.
    assert "walking-skeleton-bundle" in bundle_result.emitted_markers
    assert (
        "<!-- bmad-automation:marker walking-skeleton-bundle -->" in body
    )

    # (d) per-trigger marker present on the diagnostic + the bundle's
    # machine-readable payload conforms to the scope-assertion-violation
    # schema fragment (Story 5.8 AC-1).
    assert diagnostic.marker_class == "scope-assertion-violation"
    assert bundle_result.bundle_class == "scope-assertion-violation"
    assert bundle_result.payload["marker_class"] == (
        "scope-assertion-violation"
    )
    validate_payload_against_schema(
        payload=bundle_result.payload,
        bundle_class="scope-assertion-violation",
        schemas_root=_REPO_ROOT,
    )

    # (e) rendered Walking Skeleton header does NOT contain "No retry".
    assert "No retry" not in bundle_result.header_text
    assert "No retry" not in body

    # tmp_path scoping.
    assert expected_bundle_path.is_relative_to(tmp_path)
    assert rs_path.is_relative_to(tmp_path)


# --------------------------------------------------------------------------- #
# AC-4 path 3 — retry-budget exhaustion (escalation bundle)                   #
# --------------------------------------------------------------------------- #


def test_walking_skeleton_smoke_budget_exhaustion_path(
    tmp_path: pathlib.Path,
) -> None:
    """Retry-budget-exhaustion escalation path: retry rounds persistently
    fail until Story 5.1's whole-story retry-budget counter is exhausted;
    Story 5.6's ``record_retry_budget_exhaustion`` fires non-advance +
    state-preservation; Story 5.8's escalation-bundle assembler renders a
    retry-budget-exhausted bundle.
    """
    fixture_path = _FIXTURES_DIR / "sample-story-retry-budget-exhaustion.md"
    assert fixture_path.exists(), (
        f"missing Story 5.9 fixture {fixture_path}"
    )

    story_id = "sample-story-retry-budget-exhaustion"
    run_id = "run-2026-05-05-smoke"

    # Persist two retry-history rounds via Story 5.5's externalization.
    round_refs = []
    for round_id, attempt in (("round-01", 1), ("round-02", 2)):
        ra = RetryRoundArtifacts(
            round_id=round_id,
            retry_attempt=attempt,
            findings=(
                {
                    "id": f"F-{attempt}",
                    "title": "persistent-failure finding",
                    "source": "blind",
                    "location": "bmad-autopilot/foo.py:42",
                },
            ),
            scope_affected_files=("bmad-autopilot/foo.py",),
            scope_expanded_to=(),
            actual_diff_files=("bmad-autopilot/foo.py",),
            created_at="2026-05-05T12:00:30+00:00",
        )
        round_refs.append(
            persist_retry_round(
                round=ra,
                repo_root=tmp_path,
                story_id=story_id,
                retry_reason="patch-bucket-retry",
            )
        )

    # Compose pre-escalation run-state with the thickened retry_history.
    state = RunState(
        schema_version="1.2",
        story_id=story_id,
        run_id=run_id,
        current_state="in-progress",
        branch_name=f"bmad-automation/story/{story_id}",
        dispatched_specialist=None,
        last_envelope={
            "status": "fail",
            "findings": [
                {
                    "id": "F-2",
                    "title": "persistent-failure finding",
                    "source": "blind",
                    "location": "bmad-autopilot/foo.py:42",
                }
            ],
        },
        pending_qa_dispatch_payload=None,
        retry_history=tuple(ref.to_retry_attempt() for ref in round_refs),
        active_markers=(),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
        last_retry_directive=LastRetryDirective(
            retry_mode="fix-only", affected_files=("bmad-autopilot/foo.py",)
        ),
    )
    rs_path = tmp_path / "_bmad" / "automation" / "run-state.yaml"
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    advance_run_state(
        run_state_path=rs_path,
        next_state=state,
        story_doc_callback=lambda: StoryDocCallbackResult(accepted=True),
    )

    # Run the Story 5.6 escalation path with a capturing wrapper around
    # the Story 5.8 production assembler.
    captured_results: list[AssembleEscalationBundleResult] = []
    events: list[dict[str, Any]] = []
    record_result = record_retry_budget_exhaustion(
        run_state_path=rs_path,
        current_state=state,
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        escalation_bundle_assembler=_make_capturing_assembler(
            repo_root=tmp_path, captured=captured_results
        ),
        event_log_appender=_stub_appender(events),
        repo_root=tmp_path,
    )

    # (a) lifecycle reaches escalated terminal state; FR14 preservation.
    assert record_result.advance_result.next_state.current_state == "escalated"
    on_disk = yaml.safe_load(rs_path.read_text(encoding="utf-8"))
    assert on_disk["current_state"] == "escalated"
    assert on_disk["branch_name"] == state.branch_name
    assert len(on_disk["retry_history"]) == 2  # preservation invariant
    # On-disk per-round retry-history artifacts are preserved.
    for round_id in ("round-01", "round-02"):
        artifact_path = (
            tmp_path
            / "_bmad-output"
            / "retry-history"
            / story_id
            / round_id
            / "artifacts.yaml"
        )
        assert artifact_path.exists()
        assert artifact_path.is_relative_to(tmp_path)

    # (b) escalation bundle exists with the expected sections.
    assert len(captured_results) == 1
    bundle_result = captured_results[0]
    expected_bundle_path = compute_escalation_bundle_path(
        repo_root=tmp_path, story_id=story_id, run_id=run_id
    )
    assert bundle_result.bundle_path == expected_bundle_path
    assert expected_bundle_path.exists(), (
        f"escalation bundle must exist at {expected_bundle_path}"
    )
    body = expected_bundle_path.read_text(encoding="utf-8")
    assert "## ⚠️ Walking Skeleton Mode" in body
    assert "## Escalation rationale" in body
    assert "## Outstanding findings" in body
    assert "## Retry history" in body
    assert "## Deferred-work pointer" in body
    assert "## Preservation" in body
    # Both retry rounds rendered.
    assert "round-01" in body
    assert "round-02" in body

    # (c) walking-skeleton-bundle marker present on bundle.
    assert (
        bundle_assembly.WALKING_SKELETON_MARKER in bundle_result.emitted_markers
    )
    assert (
        "<!-- bmad-automation:marker walking-skeleton-bundle -->" in body
    )

    # (d) per-trigger marker present on the diagnostic + the bundle's
    # machine-readable payload conforms to the retry-budget-exhausted
    # schema fragment (Story 5.8 AC-1).
    assert record_result.diagnostic.marker_class == "retry-budget-exhausted"
    assert record_result.diagnostic.retry_count == 2
    assert bundle_result.bundle_class == "retry-budget-exhausted"
    assert bundle_result.payload["marker_class"] == (
        "retry-budget-exhausted"
    )
    refs = bundle_result.payload["retry_history_refs"]
    assert len(refs) == 2
    ref_round_ids = {ref["round_id"] for ref in refs}
    assert ref_round_ids == {"round-01", "round-02"}, (
        f"expected retry_history_refs to reference round-01 and round-02; "
        f"got {ref_round_ids!r}"
    )
    validate_payload_against_schema(
        payload=bundle_result.payload,
        bundle_class="retry-budget-exhausted",
        schemas_root=_REPO_ROOT,
    )

    # The escalation-fired event is emitted.
    assert len(events) == 1
    assert events[0]["event_class"] == "escalation-fired"
    assert events[0]["escalation_class"] == "retry-budget-exhausted"

    # (e) rendered Walking Skeleton header does NOT contain "No retry".
    assert "No retry" not in bundle_result.header_text
    assert "No retry" not in body

    # tmp_path scoping.
    assert expected_bundle_path.is_relative_to(tmp_path)
    assert rs_path.is_relative_to(tmp_path)
