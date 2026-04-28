"""Contract-coverage matrix for the BMAD lifecycle state machine
(story 2.4).

This docstring IS the contract-coverage checklist required by AC-5.
Reviewers verify every row maps to at least one passing test in this
module. The matrix is review-enforced, NOT CI-enforced (parallel to
1.2 / 2.2 / 2.3 AC discipline).

Pure-decision (AC-1; no mocks):
    [x] forward × 4 (ready-for-dev → in-progress → review → qa → done)
        → test_evaluate_envelope_advances_*_on_pass
    [x] halt-on-fail × 4 states                → test_evaluate_envelope_halts_on_fail[*]
    [x] halt-on-decision-needed × 4 states     → test_evaluate_envelope_halts_on_decision_needed[*]
    [x] halt-on-blocked × 4 states             → test_evaluate_envelope_halts_on_blocked[*]
    [x] terminal-rejection × 2 states × 4 outcomes (done, escalated on any outcome)
        → test_evaluate_envelope_raises_on_terminal_with_any_outcome[*]

commit_transition (AC-2, AC-3; mock-based):
    [x] happy-path: invokes advance_run_state with the supplied callback verbatim
        → test_commit_transition_invokes_advance_run_state_with_callback
    [x] happy-path: emits state-transition event AFTER advance succeeds
        → test_commit_transition_emits_state_transition_event_after_advance
    [x] propagates RunStateAdvanceBlocked unchanged; no event emitted
        → test_commit_transition_propagates_run_state_advance_blocked
    [x] propagates OSError; no event emitted
        → test_commit_transition_does_not_emit_event_on_advance_failure
    [x] no direct Path.write_text on run_state_path
        → test_commit_transition_does_not_write_run_state_directly
    [x] rejects backward × 4
        → test_commit_transition_rejects_backward_transition[*]
    [x] rejects skip × 3
        → test_commit_transition_rejects_skip_transition[*]
    [x] rejects terminal × 2 (done, escalated)
        → test_commit_transition_rejects_terminal_*

record_halt (AC-2, AC-3; mock-based):
    [x] emits state-transition-halted event       → test_record_halt_emits_state_transition_halted_event
    [x] does NOT call advance_run_state             → test_record_halt_does_not_call_advance_run_state
    [x] does NOT write run_state_path directly      → test_record_halt_does_not_write_run_state_directly
    [x] includes triggering_specialist when set     → test_record_halt_includes_triggering_specialist_when_supplied
    [x] omits triggering_specialist when None       → test_record_halt_omits_triggering_specialist_when_none
    [x] includes last_envelope_status when set      → test_record_halt_includes_last_envelope_status_when_supplied
    [x] omits last_envelope_status when None        → test_record_halt_omits_last_envelope_status_when_none

API-shape (AC-1; structural enforcement):
    [x] commit_transition.story_doc_callback keyword-only + non-defaulted
        → test_commit_transition_keyword_only_story_doc_callback
    [x] commit_transition.event_log_appender keyword-only + non-defaulted
        → test_commit_transition_keyword_only_event_log_appender
    [x] record_halt.event_log_appender keyword-only + non-defaulted
        → test_record_halt_keyword_only_event_log_appender
    [x] __all__ exports match AC-1 surface
        → test_module_all_exports

Discriminator + closed-enum invariants (AC-1; cross-schema):
    [x] LIFECYCLE_TRANSITIONS keys ∪ values ⊆ run-state.current_state enum AND ⊆ orchestrator-event from/to_state enum
        → test_lifecycle_transitions_dict_matches_schema_enum
    [x] TERMINAL_STATES == {"done", "escalated"}
        → test_terminal_states_includes_done_and_escalated
    [x] HaltReason Literal values == orchestrator-event.yaml halt_reason enum values
        → test_halt_reason_literal_matches_schema_enum
"""

from __future__ import annotations

import inspect
import pathlib
from typing import Any
from unittest import mock

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness import lifecycle_state_machine as lsm_module
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.lifecycle_state_machine import (
    LIFECYCLE_TRANSITIONS,
    TERMINAL_STATES,
    CommitTransitionResult,
    EnvelopeOutcome,
    EventLogAppender,
    HaltReason,
    InvalidLifecycleTransition,
    RecordHaltResult,
    TransitionDecision,
    commit_transition,
    evaluate_envelope,
    record_halt,
)
from loud_fail_harness.run_state import (
    AdvanceResult,
    CostToDateBySpecialist,
    CurrentState,
    RunState,
    RunStateAdvanceBlocked,
    StoryDocCallbackResult,
)


# --------------------------------------------------------------------------- #
# Fixtures + helpers                                                           #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def repo_root() -> pathlib.Path:
    """Module-scoped repo-root resolution.

    ``find_repo_root()`` is called at fixture-setup time, NOT at module
    import time — Epic 1 retro Action #1 discipline.
    """
    return find_repo_root()


def _make_run_state(current_state: CurrentState = "ready-for-dev", **overrides: Any) -> RunState:
    """Build a minimal valid :class:`RunState` instance for tests."""
    base: dict[str, Any] = {
        "schema_version": "1.0",
        "story_id": "2-4-test",
        "run_id": "run-001",
        "current_state": current_state,
        "branch_name": "bmad-automation/story/2-4-test",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": (),
        "active_markers": (),
        "cost_to_date_by_specialist": CostToDateBySpecialist(),
    }
    base.update(overrides)
    return RunState(**base)


def _accepted_callback() -> StoryDocCallbackResult:
    return StoryDocCallbackResult(accepted=True)


# --------------------------------------------------------------------------- #
# evaluate_envelope — pure-decision tests                                      #
# --------------------------------------------------------------------------- #


def test_evaluate_envelope_advances_ready_for_dev_to_in_progress_on_pass() -> None:
    decision = evaluate_envelope("ready-for-dev", "dev", "pass")
    assert decision.type == "advance"
    assert decision.next_state == "in-progress"


def test_evaluate_envelope_advances_in_progress_to_review_on_pass() -> None:
    decision = evaluate_envelope("in-progress", "dev", "pass")
    assert decision.type == "advance"
    assert decision.next_state == "review"


def test_evaluate_envelope_advances_review_to_qa_on_pass() -> None:
    decision = evaluate_envelope("review", "review-bmad", "pass")
    assert decision.type == "advance"
    assert decision.next_state == "qa"


def test_evaluate_envelope_advances_qa_to_done_on_pass() -> None:
    decision = evaluate_envelope("qa", "qa", "pass")
    assert decision.type == "advance"
    assert decision.next_state == "done"


_NON_TERMINAL_STATES: list[CurrentState] = ["ready-for-dev", "in-progress", "review", "qa"]


@pytest.mark.parametrize("current_state", _NON_TERMINAL_STATES)
def test_evaluate_envelope_halts_on_fail(current_state: CurrentState) -> None:
    decision = evaluate_envelope(current_state, "dev", "fail")
    assert decision.type == "halt"
    assert decision.halted_at_state == current_state
    assert decision.halt_reason == "non-pass-envelope"
    assert decision.last_envelope_status == "fail"


@pytest.mark.parametrize("current_state", _NON_TERMINAL_STATES)
def test_evaluate_envelope_halts_on_decision_needed(current_state: CurrentState) -> None:
    decision = evaluate_envelope(current_state, "review-bmad", "decision-needed")
    assert decision.type == "halt"
    assert decision.halted_at_state == current_state
    assert decision.halt_reason == "non-pass-envelope"
    assert decision.last_envelope_status == "decision-needed"


@pytest.mark.parametrize("current_state", _NON_TERMINAL_STATES)
def test_evaluate_envelope_halts_on_blocked(current_state: CurrentState) -> None:
    decision = evaluate_envelope(current_state, "qa", "blocked")
    assert decision.type == "halt"
    assert decision.halted_at_state == current_state
    assert decision.halt_reason == "non-pass-envelope"
    assert decision.last_envelope_status == "blocked"


@pytest.mark.parametrize("current_state", ["done", "escalated"])
@pytest.mark.parametrize("outcome", ["pass", "fail", "decision-needed", "blocked"])
def test_evaluate_envelope_raises_on_terminal_with_any_outcome(
    current_state: CurrentState, outcome: EnvelopeOutcome
) -> None:
    """Terminal states raise regardless of envelope outcome (D1 fix): the
    terminal guard fires before the non-pass branch to prevent schema-invalid
    ``state-transition-halted`` events (``halted_at_state`` enum excludes
    ``"escalated"``)."""
    with pytest.raises(InvalidLifecycleTransition) as excinfo:
        evaluate_envelope(current_state, "dev", outcome)
    assert excinfo.value.current_state == current_state
    assert excinfo.value.attempted_next_state is None
    assert "terminal" in excinfo.value.reason


# --------------------------------------------------------------------------- #
# commit_transition — happy-path mock-based tests                              #
# --------------------------------------------------------------------------- #


def test_commit_transition_invokes_advance_run_state_with_callback(tmp_path: pathlib.Path) -> None:
    """The helper invokes ``advance_run_state`` with the supplied
    ``story_doc_callback`` keyword-passed verbatim, plus the supplied
    ``run_state_path`` and ``next_state``."""
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="ready-for-dev")
    next_state = _make_run_state(current_state="in-progress")
    sentinel_advance_result = AdvanceResult(
        next_state=next_state, wrote_path=run_state_path
    )
    appender_calls: list[dict[str, Any]] = []

    with mock.patch.object(
        lsm_module, "advance_run_state", autospec=True
    ) as advance_mock:
        advance_mock.return_value = sentinel_advance_result
        result = commit_transition(
            run_state_path,
            current,
            next_state,
            story_doc_callback=_accepted_callback,
            event_log_appender=appender_calls.append,
        )

    advance_mock.assert_called_once_with(
        run_state_path=run_state_path,
        next_state=next_state,
        story_doc_callback=_accepted_callback,
    )
    assert isinstance(result, CommitTransitionResult)
    assert result.advance_result == sentinel_advance_result


def test_commit_transition_emits_state_transition_event_after_advance(tmp_path: pathlib.Path) -> None:
    """On the happy path, the appender is invoked exactly once with a
    schema-shaped ``state-transition`` event."""
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="in-progress", story_id="2-4-x")
    next_state = _make_run_state(current_state="review", story_id="2-4-x")
    appender_calls: list[dict[str, Any]] = []

    with mock.patch.object(
        lsm_module, "advance_run_state", autospec=True
    ) as advance_mock:
        advance_mock.return_value = AdvanceResult(
            next_state=next_state, wrote_path=run_state_path
        )
        result = commit_transition(
            run_state_path,
            current,
            next_state,
            story_doc_callback=_accepted_callback,
            event_log_appender=appender_calls.append,
        )

    assert len(appender_calls) == 1
    event = appender_calls[0]
    assert event["event_class"] == "state-transition"
    assert event["from_state"] == "in-progress"
    assert event["to_state"] == "review"
    assert event["story_id"] == "2-4-x"
    assert event["event_id"]
    assert event["timestamp"]
    # Result wraps the same event
    assert result.emitted_event == event


def test_commit_transition_propagates_run_state_advance_blocked(tmp_path: pathlib.Path) -> None:
    """When ``advance_run_state`` raises ``RunStateAdvanceBlocked``,
    the exception propagates unchanged AND the appender is NOT
    invoked."""
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="ready-for-dev")
    next_state = _make_run_state(current_state="in-progress")
    appender_calls: list[dict[str, Any]] = []
    rejection = StoryDocCallbackResult(
        accepted=False, reason="rejected", marker="undocumented-section-write"
    )
    blocked_exc = RunStateAdvanceBlocked(
        cause=rejection, attempted_next_state=next_state
    )

    with mock.patch.object(
        lsm_module, "advance_run_state", autospec=True
    ) as advance_mock:
        advance_mock.side_effect = blocked_exc
        with pytest.raises(RunStateAdvanceBlocked) as excinfo:
            commit_transition(
                run_state_path,
                current,
                next_state,
                story_doc_callback=_accepted_callback,
                event_log_appender=appender_calls.append,
            )

    assert excinfo.value is blocked_exc
    assert appender_calls == []


def test_commit_transition_does_not_emit_event_on_advance_failure(tmp_path: pathlib.Path) -> None:
    """When ``advance_run_state`` raises ``OSError``, the exception
    propagates AND the appender is NOT invoked."""
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="review")
    next_state = _make_run_state(current_state="qa")
    appender_calls: list[dict[str, Any]] = []

    with mock.patch.object(
        lsm_module, "advance_run_state", autospec=True
    ) as advance_mock:
        advance_mock.side_effect = OSError("disk full")
        with pytest.raises(OSError, match="disk full"):
            commit_transition(
                run_state_path,
                current,
                next_state,
                story_doc_callback=_accepted_callback,
                event_log_appender=appender_calls.append,
            )

    assert appender_calls == []


def test_commit_transition_does_not_write_run_state_directly(tmp_path: pathlib.Path) -> None:
    """The helper does NOT call ``Path.write_text`` or ``Path.write_bytes``
    against ``run_state_path`` (AC-3: ``advance_run_state`` is the SOLE
    write path; ``advance_run_state`` is also mocked so no I/O occurs
    through it either)."""
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="ready-for-dev")
    next_state = _make_run_state(current_state="in-progress")
    appender_calls: list[dict[str, Any]] = []

    with (
        mock.patch.object(lsm_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(pathlib.Path, "write_text", autospec=True) as write_text_mock,
        mock.patch.object(pathlib.Path, "write_bytes", autospec=True) as write_bytes_mock,
    ):
        advance_mock.return_value = AdvanceResult(
            next_state=next_state, wrote_path=run_state_path
        )
        commit_transition(
            run_state_path,
            current,
            next_state,
            story_doc_callback=_accepted_callback,
            event_log_appender=appender_calls.append,
        )

    write_text_mock.assert_not_called()
    write_bytes_mock.assert_not_called()


# --------------------------------------------------------------------------- #
# commit_transition — backward / skip / terminal rejection tests               #
# --------------------------------------------------------------------------- #


_BACKWARD_PAIRS: list[tuple[CurrentState, CurrentState]] = [
    ("in-progress", "ready-for-dev"),
    ("review", "in-progress"),
    ("qa", "review"),
    ("done", "qa"),
]


@pytest.mark.parametrize("current,next_", _BACKWARD_PAIRS)
def test_commit_transition_rejects_backward_transition(
    tmp_path: pathlib.Path, current: CurrentState, next_: CurrentState
) -> None:
    run_state_path = tmp_path / "run-state.yaml"
    current_rs = _make_run_state(current_state=current)
    next_rs = _make_run_state(current_state=next_)
    appender_calls: list[dict[str, Any]] = []

    with mock.patch.object(
        lsm_module, "advance_run_state", autospec=True
    ) as advance_mock:
        with pytest.raises(InvalidLifecycleTransition) as excinfo:
            commit_transition(
                run_state_path,
                current_rs,
                next_rs,
                story_doc_callback=_accepted_callback,
                event_log_appender=appender_calls.append,
            )

    assert excinfo.value.current_state == current
    assert excinfo.value.attempted_next_state == next_
    # 'done' is terminal; rejection reason cites terminal, not backward.
    if current == "done":
        assert "terminal" in excinfo.value.reason
    else:
        assert "backward" in excinfo.value.reason
    advance_mock.assert_not_called()
    assert appender_calls == []


_SKIP_PAIRS: list[tuple[CurrentState, CurrentState]] = [
    ("ready-for-dev", "review"),
    ("in-progress", "qa"),
    ("review", "done"),
]


@pytest.mark.parametrize("current,next_", _SKIP_PAIRS)
def test_commit_transition_rejects_skip_transition(
    tmp_path: pathlib.Path, current: CurrentState, next_: CurrentState
) -> None:
    run_state_path = tmp_path / "run-state.yaml"
    current_rs = _make_run_state(current_state=current)
    next_rs = _make_run_state(current_state=next_)
    appender_calls: list[dict[str, Any]] = []

    with mock.patch.object(
        lsm_module, "advance_run_state", autospec=True
    ) as advance_mock:
        with pytest.raises(InvalidLifecycleTransition) as excinfo:
            commit_transition(
                run_state_path,
                current_rs,
                next_rs,
                story_doc_callback=_accepted_callback,
                event_log_appender=appender_calls.append,
            )

    assert excinfo.value.current_state == current
    assert excinfo.value.attempted_next_state == next_
    assert "skip" in excinfo.value.reason
    advance_mock.assert_not_called()
    assert appender_calls == []


def test_commit_transition_rejects_terminal_done_to_anything(tmp_path: pathlib.Path) -> None:
    run_state_path = tmp_path / "run-state.yaml"
    current_rs = _make_run_state(current_state="done")
    next_rs = _make_run_state(current_state="qa")
    appender_calls: list[dict[str, Any]] = []

    with mock.patch.object(
        lsm_module, "advance_run_state", autospec=True
    ) as advance_mock:
        with pytest.raises(InvalidLifecycleTransition) as excinfo:
            commit_transition(
                run_state_path,
                current_rs,
                next_rs,
                story_doc_callback=_accepted_callback,
                event_log_appender=appender_calls.append,
            )

    assert excinfo.value.current_state == "done"
    assert "terminal" in excinfo.value.reason
    advance_mock.assert_not_called()
    assert appender_calls == []


def test_commit_transition_rejects_terminal_escalated_to_anything(tmp_path: pathlib.Path) -> None:
    run_state_path = tmp_path / "run-state.yaml"
    current_rs = _make_run_state(current_state="escalated")
    next_rs = _make_run_state(current_state="review")
    appender_calls: list[dict[str, Any]] = []

    with mock.patch.object(
        lsm_module, "advance_run_state", autospec=True
    ) as advance_mock:
        with pytest.raises(InvalidLifecycleTransition) as excinfo:
            commit_transition(
                run_state_path,
                current_rs,
                next_rs,
                story_doc_callback=_accepted_callback,
                event_log_appender=appender_calls.append,
            )

    assert excinfo.value.current_state == "escalated"
    assert "terminal" in excinfo.value.reason
    advance_mock.assert_not_called()
    assert appender_calls == []


# --------------------------------------------------------------------------- #
# record_halt — mock-based tests                                               #
# --------------------------------------------------------------------------- #


def test_record_halt_emits_state_transition_halted_event(tmp_path: pathlib.Path) -> None:
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="review", story_id="2-4-h")
    appender_calls: list[dict[str, Any]] = []

    result = record_halt(
        run_state_path,
        current,
        "review-bmad",
        "non-pass-envelope",
        event_log_appender=appender_calls.append,
        last_envelope_status="fail",
    )

    assert isinstance(result, RecordHaltResult)
    assert len(appender_calls) == 1
    event = appender_calls[0]
    assert event["event_class"] == "state-transition-halted"
    assert event["halted_at_state"] == "review"
    assert event["halt_reason"] == "non-pass-envelope"
    assert event["story_id"] == "2-4-h"
    assert event["triggering_specialist"] == "review-bmad"
    assert event["last_envelope_status"] == "fail"


def test_record_halt_does_not_call_advance_run_state(tmp_path: pathlib.Path) -> None:
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="in-progress")
    appender_calls: list[dict[str, Any]] = []

    with mock.patch.object(
        lsm_module, "advance_run_state", autospec=True
    ) as advance_mock:
        record_halt(
            run_state_path,
            current,
            "dev",
            "non-pass-envelope",
            event_log_appender=appender_calls.append,
            last_envelope_status="fail",
        )

    advance_mock.assert_not_called()


def test_record_halt_does_not_write_run_state_directly(tmp_path: pathlib.Path) -> None:
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="qa")
    appender_calls: list[dict[str, Any]] = []

    with mock.patch.object(pathlib.Path, "write_text", autospec=True) as write_text_mock:
        record_halt(
            run_state_path,
            current,
            "qa",
            "non-pass-envelope",
            event_log_appender=appender_calls.append,
            last_envelope_status="blocked",
        )

    write_text_mock.assert_not_called()


def test_record_halt_includes_triggering_specialist_when_supplied(tmp_path: pathlib.Path) -> None:
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="review")
    appender_calls: list[dict[str, Any]] = []

    record_halt(
        run_state_path,
        current,
        "review-bmad",
        "non-pass-envelope",
        event_log_appender=appender_calls.append,
        last_envelope_status="decision-needed",
    )
    event = appender_calls[0]
    assert event["triggering_specialist"] == "review-bmad"


def test_record_halt_omits_triggering_specialist_when_none(tmp_path: pathlib.Path) -> None:
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="review")
    appender_calls: list[dict[str, Any]] = []

    record_halt(
        run_state_path,
        current,
        None,
        "attempted-backward-transition",
        event_log_appender=appender_calls.append,
    )
    event = appender_calls[0]
    assert "triggering_specialist" not in event


def test_record_halt_includes_last_envelope_status_when_supplied(tmp_path: pathlib.Path) -> None:
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="qa")
    appender_calls: list[dict[str, Any]] = []

    record_halt(
        run_state_path,
        current,
        "qa",
        "non-pass-envelope",
        event_log_appender=appender_calls.append,
        last_envelope_status="blocked",
    )
    event = appender_calls[0]
    assert event["last_envelope_status"] == "blocked"


def test_record_halt_omits_last_envelope_status_when_none(tmp_path: pathlib.Path) -> None:
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="in-progress")
    appender_calls: list[dict[str, Any]] = []

    record_halt(
        run_state_path,
        current,
        None,
        "attempted-skip-transition",
        event_log_appender=appender_calls.append,
    )
    event = appender_calls[0]
    assert "last_envelope_status" not in event


# --------------------------------------------------------------------------- #
# API-shape tests                                                              #
# --------------------------------------------------------------------------- #


def test_commit_transition_keyword_only_story_doc_callback() -> None:
    sig = inspect.signature(commit_transition)
    param = sig.parameters["story_doc_callback"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty


def test_commit_transition_keyword_only_event_log_appender() -> None:
    sig = inspect.signature(commit_transition)
    param = sig.parameters["event_log_appender"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty


def test_record_halt_keyword_only_event_log_appender() -> None:
    sig = inspect.signature(record_halt)
    param = sig.parameters["event_log_appender"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty


def test_commit_transition_missing_keyword_raises_typeerror(tmp_path: pathlib.Path) -> None:
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="ready-for-dev")
    next_state = _make_run_state(current_state="in-progress")
    with pytest.raises(TypeError):
        commit_transition(  # type: ignore[call-arg]
            run_state_path, current, next_state
        )


def test_record_halt_missing_keyword_raises_typeerror(tmp_path: pathlib.Path) -> None:
    run_state_path = tmp_path / "run-state.yaml"
    current = _make_run_state(current_state="ready-for-dev")
    with pytest.raises(TypeError):
        record_halt(  # type: ignore[call-arg]
            run_state_path, current, "dev", "non-pass-envelope"
        )


def test_module_all_exports() -> None:
    """``__all__`` enumerates the public surface per AC-1."""
    expected = {
        "evaluate_envelope",
        "commit_transition",
        "record_halt",
        "LIFECYCLE_TRANSITIONS",
        "TERMINAL_STATES",
        "TransitionDecision",
        "EnvelopeOutcome",
        "HaltReason",
        "EventLogAppender",
        "CommitTransitionResult",
        "RecordHaltResult",
        "InvalidLifecycleTransition",
    }
    assert set(lsm_module.__all__) == expected


# --------------------------------------------------------------------------- #
# Discriminator + closed-enum invariants (cross-schema validation)             #
# --------------------------------------------------------------------------- #


def test_lifecycle_transitions_dict_matches_schema_enum(repo_root: pathlib.Path) -> None:
    """The set of states named in :data:`LIFECYCLE_TRANSITIONS` (keys ∪
    values) is a subset of:

      * ``schemas/run-state.yaml``'s ``current_state.enum`` (the
        canonical lifecycle vocabulary), AND
      * ``schemas/orchestrator-event.yaml``'s
        ``state-transition.from_state`` / ``to_state`` enum.

    This prevents drift between the Python module and the YAML
    schemas.
    """
    run_state_schema = yaml.safe_load(
        (repo_root / "schemas" / "run-state.yaml").read_text(encoding="utf-8")
    )
    event_schema = yaml.safe_load(
        (repo_root / "schemas" / "orchestrator-event.yaml").read_text(encoding="utf-8")
    )

    run_state_enum = set(run_state_schema["properties"]["current_state"]["enum"])

    state_transition_branch = next(
        b for b in event_schema["oneOf"]
        if b["properties"]["event_class"].get("const") == "state-transition"
    )
    from_to_enum = set(state_transition_branch["properties"]["from_state"]["enum"])

    transition_states = set(LIFECYCLE_TRANSITIONS.keys()) | set(LIFECYCLE_TRANSITIONS.values())
    assert transition_states <= run_state_enum, (
        f"LIFECYCLE_TRANSITIONS references states not in run-state schema: "
        f"{transition_states - run_state_enum}"
    )
    assert transition_states <= from_to_enum, (
        f"LIFECYCLE_TRANSITIONS references states not in orchestrator-event schema: "
        f"{transition_states - from_to_enum}"
    )


def test_terminal_states_includes_done_and_escalated() -> None:
    assert TERMINAL_STATES == frozenset({"done", "escalated"})


def test_halt_reason_literal_matches_schema_enum(repo_root: pathlib.Path) -> None:
    """The ``HaltReason`` Literal values match the schema's
    ``state-transition-halted.halt_reason`` enum exactly."""
    event_schema = yaml.safe_load(
        (repo_root / "schemas" / "orchestrator-event.yaml").read_text(encoding="utf-8")
    )
    halted_branch = next(
        b for b in event_schema["oneOf"]
        if b["properties"]["event_class"].get("const") == "state-transition-halted"
    )
    schema_enum = set(halted_branch["properties"]["halt_reason"]["enum"])

    # The HaltReason Literal's __args__ enumerates its values.
    literal_values: set[str] = set(HaltReason.__args__)  # type: ignore[attr-defined]
    assert literal_values == schema_enum


def test_lifecycle_transitions_keys_disjoint_from_terminal_states() -> None:
    """The forward map's key set does NOT intersect TERMINAL_STATES;
    terminal states are unreachable as advance sources."""
    assert set(LIFECYCLE_TRANSITIONS.keys()).isdisjoint(TERMINAL_STATES)


def test_transition_decision_models_are_frozen() -> None:
    """The discriminated-union branches are frozen Pydantic models."""
    advance_decision = evaluate_envelope("ready-for-dev", "dev", "pass")
    halt_decision = evaluate_envelope("review", "review-bmad", "fail")
    with pytest.raises(ValidationError):
        advance_decision.next_state = "qa"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        halt_decision.halt_reason = "attempted-skip-transition"  # type: ignore[misc]


def test_evaluate_envelope_decision_type_discriminator() -> None:
    """The ``type`` field on the discriminated-union branches reads as
    ``"advance"`` and ``"halt"`` respectively."""
    adv: TransitionDecision = evaluate_envelope("ready-for-dev", "dev", "pass")
    halt: TransitionDecision = evaluate_envelope("in-progress", "dev", "fail")
    assert adv.type == "advance"
    assert halt.type == "halt"


# --------------------------------------------------------------------------- #
# Type aliases sanity (smoke)                                                  #
# --------------------------------------------------------------------------- #


def test_envelope_outcome_literal_values() -> None:
    """``EnvelopeOutcome`` Literal enumerates the four known statuses."""
    assert set(EnvelopeOutcome.__args__) == {"pass", "fail", "decision-needed", "blocked"}  # type: ignore[attr-defined]


def test_event_log_appender_callable_protocol() -> None:
    """``EventLogAppender`` is a Callable[[dict], None] alias."""
    # Smoke: a stub appender is callable with the expected shape.
    captured: list[dict[str, Any]] = []
    appender: EventLogAppender = captured.append
    appender({"event_class": "smoke"})
    assert captured == [{"event_class": "smoke"}]
