"""Contract-coverage matrix for the no-destructive-resume substrate guard (Story 8.6).

This docstring IS the contract-coverage checklist required by AC-6. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced (parallel to ``tests/test_resume_command.py`` and
``tests/test_status_command.py``).

AC-1 — Substrate library shape (1):
    [x] test_module_exports_documented_public_api

AC-2 — Allow path (3):
    [x] test_can_dispatch_returns_allow_when_no_prior_output_recorded
    [x] test_can_dispatch_returns_allow_when_dispatched_specialist_differs_from_candidate
    [x] test_can_dispatch_returns_allow_when_dispatched_matches_but_envelope_none

AC-2 — Deny: prior-output-recorded (3):
    [x] test_can_dispatch_denies_with_prior_output_recorded_when_dispatched_matches_and_envelope_present
    [x] test_can_dispatch_diagnostic_names_recorded_specialist
    [x] test_can_dispatch_diagnostic_names_envelope_status_field

AC-2 — Deny: work-already-committed (2):
    [x] test_can_dispatch_denies_with_work_already_committed_when_dev_with_completed_envelope_and_head_commit_sha
    [x] test_can_dispatch_priority_orders_work_already_committed_over_prior_output_recorded_when_both_match

AC-2 — Deny: branch-already-exists (2):
    [x] test_can_dispatch_denies_with_branch_already_exists_when_dev_dispatch_at_ready_for_dev_with_branch_name
    [x] test_can_dispatch_does_not_deny_branch_for_non_dev_dispatch

AC-2 — Deny: run-state-unexpected-state (1):
    [x] test_can_dispatch_safe_denies_when_current_state_outside_closed_enum

AC-1 — Verdict model invariants (2):
    [x] test_verdict_validator_rejects_allow_true_with_reason
    [x] test_verdict_is_frozen_and_byte_stable

AC-1 — Defensive guard (1):
    [x] test_can_dispatch_raises_substrate_error_when_run_state_not_a_run_state_instance

AC-1 — Purity contract (1):
    [x] test_can_dispatch_is_byte_identical_on_identical_inputs

AC-1 — CLI smoke (3):
    [x] test_main_exits_zero_on_allow_verdict
    [x] test_main_exits_one_on_deny_verdict
    [x] test_main_exits_two_on_substrate_error
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
from pydantic import ValidationError

from loud_fail_harness import no_destructive_resume_guard as guard_module
from loud_fail_harness.no_destructive_resume_guard import (
    DenyReason,
    NoDestructiveResumeGuardError,
    Verdict,
    can_dispatch,
    main,
)
from loud_fail_harness.run_state import CostToDateBySpecialist, RunState


# --------------------------------------------------------------------------- #
# Fixtures + helpers                                                          #
# --------------------------------------------------------------------------- #


def _make_run_state(**overrides: Any) -> RunState:
    """Build a clean :class:`RunState` instance for guard tests."""
    base: dict[str, Any] = {
        "schema_version": "1.3",
        "story_id": "8-6-test",
        "run_id": "r1",
        "current_state": "in-progress",
        "branch_name": "bmad-automation/story/8-6-test",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": (),
        "active_markers": (),
        "cost_to_date_by_specialist": CostToDateBySpecialist(),
    }
    base.update(overrides)
    return RunState.model_validate(base)


def _make_run_state_with_unexpected_current_state() -> RunState:
    """Construct a RunState with a structurally-invalid ``current_state``
    via Pydantic's ``model_construct`` bypass path. Reachable only by tests
    that deliberately bypass the validating constructor."""
    return RunState.model_construct(
        schema_version="1.3",
        story_id="8-6-test",
        run_id="r1",
        current_state="hypothetically-invalid",  # type: ignore[arg-type]
        branch_name="bmad-automation/story/8-6-test",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        marker_contexts={},
        cost_to_date_by_specialist=CostToDateBySpecialist(),
        last_retry_directive=None,
    )


def _completed_envelope(
    *,
    head_commit_sha: str | None = "abc123def456",
    status: str = "completed",
) -> dict[str, Any]:
    """Synthesize a dev envelope payload carrying a commit SHA per FR12."""
    payload: dict[str, Any] = {
        "specialist": "dev",
        "status": status,
    }
    if head_commit_sha is not None:
        payload["head_commit_sha"] = head_commit_sha
    return payload


# --------------------------------------------------------------------------- #
# AC-1 — Module-level invariants                                              #
# --------------------------------------------------------------------------- #


def test_module_exports_documented_public_api() -> None:
    """The module's __all__ enumerates the documented AC-1 public API."""
    expected = {
        "DenyReason",
        "NoDestructiveResumeGuardError",
        "Verdict",
        "can_dispatch",
        "main",
    }
    assert set(guard_module.__all__) == expected


# --------------------------------------------------------------------------- #
# AC-2 — Allow path                                                           #
# --------------------------------------------------------------------------- #


def test_can_dispatch_returns_allow_when_no_prior_output_recorded() -> None:
    """Fresh run-state: no specialist dispatched, no envelope recorded.
    The first dispatch is non-destructive."""
    rs = _make_run_state(
        dispatched_specialist=None,
        last_envelope=None,
    )
    verdict = can_dispatch("dev", "8-6-test", rs)
    assert verdict.allow is True
    assert verdict.reason is None
    assert verdict.diagnostic is None


def test_can_dispatch_returns_allow_when_dispatched_specialist_differs_from_candidate() -> None:
    """Run-state shows review-bmad was last dispatched; the candidate is qa.
    Dispatching qa is fresh — non-destructive — even with envelope recorded."""
    rs = _make_run_state(
        dispatched_specialist="review-bmad",
        last_envelope={"specialist": "review-bmad", "status": "completed"},
    )
    verdict = can_dispatch("qa", "8-6-test", rs)
    assert verdict.allow is True


def test_can_dispatch_returns_allow_when_dispatched_matches_but_envelope_none() -> None:
    """In-flight dispatch: the specialist was dispatched but the envelope
    has not yet been recorded (the seam is mid-execution). Resuming
    re-enters the same seam — non-destructive (the prior dispatch never
    completed)."""
    rs = _make_run_state(
        dispatched_specialist="dev",
        last_envelope=None,
    )
    verdict = can_dispatch("dev", "8-6-test", rs)
    assert verdict.allow is True


# --------------------------------------------------------------------------- #
# AC-2 — Deny: prior-output-recorded                                          #
# --------------------------------------------------------------------------- #


def test_can_dispatch_denies_with_prior_output_recorded_when_dispatched_matches_and_envelope_present() -> None:
    """The seam already produced output; resuming would re-dispatch."""
    rs = _make_run_state(
        current_state="in-progress",
        dispatched_specialist="review-bmad",
        last_envelope={"specialist": "review-bmad", "status": "completed"},
    )
    verdict = can_dispatch("review-bmad", "8-6-test", rs)
    assert verdict.allow is False
    assert verdict.reason == "prior-output-recorded"
    assert verdict.diagnostic is not None


def test_can_dispatch_diagnostic_names_recorded_specialist() -> None:
    rs = _make_run_state(
        current_state="in-progress",
        dispatched_specialist="review-bmad",
        last_envelope={"specialist": "review-bmad", "status": "completed"},
    )
    verdict = can_dispatch("review-bmad", "8-6-needle", rs)
    assert verdict.diagnostic is not None
    assert "review-bmad" in verdict.diagnostic
    assert "8-6-needle" in verdict.diagnostic


def test_can_dispatch_diagnostic_names_envelope_status_field() -> None:
    rs = _make_run_state(
        current_state="qa",
        dispatched_specialist="qa",
        last_envelope={"specialist": "qa", "status": "completed"},
    )
    verdict = can_dispatch("qa", "8-6-test", rs)
    assert verdict.diagnostic is not None
    assert "completed" in verdict.diagnostic


# --------------------------------------------------------------------------- #
# AC-2 — Deny: work-already-committed                                         #
# --------------------------------------------------------------------------- #


def test_can_dispatch_denies_with_work_already_committed_when_dev_with_completed_envelope_and_head_commit_sha() -> None:
    """The work-already-committed predicate fires only when prior-output-
    recorded does NOT also fire — i.e., when the dev envelope is recorded
    but its specialist marker was advanced past dev (e.g., the
    dispatched_specialist field was nulled but the envelope retained).
    Test the predicate via direct internal predicate call to avoid the
    priority-ordering interaction (which is covered by the next test)."""
    from loud_fail_harness.no_destructive_resume_guard import (
        _is_work_already_committed,
    )

    rs = _make_run_state(
        current_state="in-progress",
        dispatched_specialist="dev",
        last_envelope=_completed_envelope(head_commit_sha="deadbeefcafebabe"),
    )
    assert _is_work_already_committed("dev", rs) is True

    # Negative case — non-dev specialist.
    assert _is_work_already_committed("qa", rs) is False
    # Negative case — no head_commit_sha.
    rs_no_sha = _make_run_state(
        current_state="in-progress",
        dispatched_specialist="dev",
        last_envelope={"specialist": "dev", "status": "completed"},
    )
    assert _is_work_already_committed("dev", rs_no_sha) is False
    # Negative case — non-completed status.
    rs_in_flight = _make_run_state(
        current_state="in-progress",
        dispatched_specialist="dev",
        last_envelope=_completed_envelope(status="in-flight"),
    )
    assert _is_work_already_committed("dev", rs_in_flight) is False


def test_can_dispatch_priority_orders_work_already_committed_over_prior_output_recorded_when_both_match() -> None:
    """When BOTH work-already-committed AND prior-output-recorded predicates
    match, the more specific reason — work-already-committed — is reported
    per the revised priority ordering (commit-level specialization checked
    first for dev dispatches so callers receive the actionable SHA diagnostic)."""
    rs = _make_run_state(
        current_state="in-progress",
        dispatched_specialist="dev",
        last_envelope=_completed_envelope(head_commit_sha="deadbeef"),
    )
    verdict = can_dispatch("dev", "8-6-test", rs)
    assert verdict.allow is False
    # Both predicates would match individually; priority ordering picks
    # work-already-committed (commit-level specialization, more specific).
    assert verdict.reason == "work-already-committed"


# --------------------------------------------------------------------------- #
# AC-2 — Deny: branch-already-exists                                          #
# --------------------------------------------------------------------------- #


def test_can_dispatch_denies_with_branch_already_exists_when_dev_dispatch_at_ready_for_dev_with_branch_name() -> None:
    """Branch creation is implied at the dev+ready-for-dev seam when a
    prior dev dispatch evidences the branch already exists from
    dispatch (rather than from run-init's bookkeeping). The
    branch-already-exists deny condition fires when:
      - specialist == "dev"
      - current_state == "ready-for-dev"
      - branch_name is set
      - dispatched_specialist == "dev" (evidence of prior dispatch)
      - last_envelope is None (no envelope yet — avoid prior-output-recorded)
    """
    rs = _make_run_state(
        current_state="ready-for-dev",
        branch_name="bmad-automation/story/8-6-test",
        dispatched_specialist="dev",
        last_envelope=None,
    )
    verdict = can_dispatch("dev", "8-6-test", rs)
    assert verdict.allow is False
    assert verdict.reason == "branch-already-exists"
    assert verdict.diagnostic is not None
    assert "bmad-automation/story/8-6-test" in verdict.diagnostic


def test_can_dispatch_does_not_deny_branch_for_non_dev_dispatch() -> None:
    """The branch-already-exists predicate is gated on dev+ready-for-dev.
    QA dispatch at any state with a populated branch_name does NOT trigger
    this deny condition."""
    rs = _make_run_state(
        current_state="qa",
        branch_name="bmad-automation/story/8-6-test",
        dispatched_specialist=None,
        last_envelope=None,
    )
    verdict = can_dispatch("qa", "8-6-test", rs)
    assert verdict.allow is True


def test_can_dispatch_does_not_deny_branch_on_first_dev_dispatch_with_run_init_branch() -> None:
    """A fresh run-state at ready-for-dev with branch_name populated by
    Story 2.3's run-init (NOT by a prior dev dispatch) must NOT trigger
    branch-already-exists — dispatched_specialist=None is the signal that
    no prior dispatch occurred."""
    rs = _make_run_state(
        current_state="ready-for-dev",
        branch_name="bmad-automation/story/8-6-test",
        dispatched_specialist=None,
        last_envelope=None,
    )
    verdict = can_dispatch("dev", "8-6-test", rs)
    assert verdict.allow is True


# --------------------------------------------------------------------------- #
# AC-2 — Deny: run-state-unexpected-state (defensive sentinel)                #
# --------------------------------------------------------------------------- #


def test_can_dispatch_safe_denies_when_current_state_outside_closed_enum() -> None:
    """The defensive sentinel fires on a structurally-invalid current_state
    that bypassed Pydantic validation. Constructed via model_construct."""
    rs = _make_run_state_with_unexpected_current_state()
    verdict = can_dispatch("dev", "8-6-test", rs)
    assert verdict.allow is False
    assert verdict.reason == "run-state-unexpected-state"
    assert verdict.diagnostic is not None
    assert "hypothetically-invalid" in verdict.diagnostic


# --------------------------------------------------------------------------- #
# AC-1 — Verdict model invariants                                             #
# --------------------------------------------------------------------------- #


def test_verdict_validator_rejects_allow_true_with_reason() -> None:
    """The model_validator rejects ``Verdict(allow=True,
    reason='prior-output-recorded')`` at construction; the inverse
    (allow=False without reason) is also rejected."""
    with pytest.raises(ValidationError):
        Verdict(allow=True, reason="prior-output-recorded", diagnostic="x")
    with pytest.raises(ValidationError):
        Verdict(allow=True, reason=None, diagnostic="x")
    with pytest.raises(ValidationError):
        Verdict(allow=False, reason=None, diagnostic=None)
    with pytest.raises(ValidationError):
        Verdict(allow=False, reason="prior-output-recorded", diagnostic=None)


def test_verdict_is_frozen_and_byte_stable() -> None:
    """Frozen Pydantic + deterministic JSON serialization."""
    v1 = Verdict(allow=True)
    with pytest.raises(ValidationError):
        v1.allow = False  # type: ignore[misc]
    # Byte-identical JSON serialization across two constructions of the
    # same logical verdict.
    v2 = Verdict(allow=False, reason="prior-output-recorded", diagnostic="d")
    v2_again = Verdict(allow=False, reason="prior-output-recorded", diagnostic="d")
    assert v2.model_dump_json() == v2_again.model_dump_json()


# --------------------------------------------------------------------------- #
# AC-1 — Defensive substrate guard                                            #
# --------------------------------------------------------------------------- #


def test_can_dispatch_raises_substrate_error_when_run_state_not_a_run_state_instance() -> None:
    """Defensive isinstance guard catches programmer errors at the
    function-call boundary."""
    with pytest.raises(NoDestructiveResumeGuardError) as exc_info:
        can_dispatch("dev", "8-6-test", "not-a-run-state")  # type: ignore[arg-type]
    assert exc_info.value.reason == "run-state-not-a-run-state-instance"
    # Marker-class invariant signal — substrate error, not runtime failure.
    assert NoDestructiveResumeGuardError.marker_class is None


# --------------------------------------------------------------------------- #
# AC-1 — Purity contract                                                      #
# --------------------------------------------------------------------------- #


def test_can_dispatch_is_byte_identical_on_identical_inputs() -> None:
    """Pure-function contract: byte-identical output on identical input
    across multiple invocations (defensive against accidental in-memory
    caching; mirrors 8.1 / 8.2 / 8.3 / 8.4 / 8.5 purity contracts)."""
    rs = _make_run_state(
        current_state="qa",
        dispatched_specialist="qa",
        last_envelope={"specialist": "qa", "status": "completed"},
    )
    v1 = can_dispatch("qa", "8-6-test", rs)
    v2 = can_dispatch("qa", "8-6-test", rs)
    assert v1.model_dump_json() == v2.model_dump_json()


# --------------------------------------------------------------------------- #
# CLI smoke                                                                   #
# --------------------------------------------------------------------------- #


def _write_run_state_yaml(
    run_state_path: pathlib.Path,
    *,
    current_state: str = "in-progress",
    dispatched_specialist: str | None = None,
    last_envelope_yaml: str = "null",
) -> None:
    """Synthesize a minimal run-state YAML at the named path."""
    run_state_path.parent.mkdir(parents=True, exist_ok=True)
    dispatched_yaml = (
        "null" if dispatched_specialist is None else f"'{dispatched_specialist}'"
    )
    run_state_path.write_text(
        "schema_version: '1.3'\n"
        "story_id: 8-6-test\n"
        "run_id: r1\n"
        f"current_state: {current_state}\n"
        "branch_name: bmad-automation/story/8-6-test\n"
        f"dispatched_specialist: {dispatched_yaml}\n"
        f"last_envelope: {last_envelope_yaml}\n"
        "retry_history: []\n"
        "active_markers: []\n"
        "cost_to_date_by_specialist: {}\n"
        "pending_qa_dispatch_payload: null\n",
        encoding="utf-8",
    )


def test_main_exits_zero_on_allow_verdict(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rs_path = tmp_path / "run-state.yaml"
    _write_run_state_yaml(rs_path)
    rc = main(
        [
            "--run-state-path",
            str(rs_path),
            "--specialist",
            "dev",
            "--story-id",
            "8-6-test",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "ALLOW" in captured.out


def test_main_exits_one_on_deny_verdict(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rs_path = tmp_path / "run-state.yaml"
    _write_run_state_yaml(
        rs_path,
        current_state="in-progress",
        dispatched_specialist="review-bmad",
        last_envelope_yaml="{specialist: review-bmad, status: completed}",
    )
    rc = main(
        [
            "--run-state-path",
            str(rs_path),
            "--specialist",
            "review-bmad",
            "--story-id",
            "8-6-test",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert "DENY[prior-output-recorded]" in captured.out


def test_main_exits_two_on_substrate_error(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        [
            "--run-state-path",
            str(tmp_path / "missing.yaml"),
            "--specialist",
            "dev",
            "--story-id",
            "8-6-test",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2
    assert "harness-level error" in captured.err


# --------------------------------------------------------------------------- #
# DenyReason invariants                                                       #
# --------------------------------------------------------------------------- #


def test_deny_reason_literal_membership() -> None:
    """The DenyReason Literal enumerates exactly the four documented members."""
    from typing import get_args

    assert set(get_args(DenyReason)) == {
        "prior-output-recorded",
        "branch-already-exists",
        "work-already-committed",
        "run-state-unexpected-state",
    }
