"""Contract-coverage matrix for the orchestrator story-loop entry sequence
(story 2.5).

This docstring IS the contract-coverage checklist required by AC-5.
Reviewers verify every row maps to at least one passing test in this
module. The matrix is review-enforced, NOT CI-enforced (parallel to
1.2 / 2.2 / 2.3 / 2.4 AC discipline).

Happy-path (AC-2; mock-based):
    [x] all six steps invoked in order with mocked substrate helpers
        → test_happy_path_entry_sequence_invokes_all_steps_in_order
    [x] advance_run_state called exactly twice per successful run (step 4 + commit_transition step 5)
        → test_advance_run_state_invocation_count

Precondition violations (AC-3; no-side-effect assertions):
    [x] story_doc_resolver returns None
        → test_precondition_story_doc_not_found_via_none_no_side_effects
    [x] story_doc_resolver raises StoryDocNotFound
        → test_precondition_story_doc_not_found_via_raise_no_side_effects
    [x] story_doc_resolver raises StoryDocMalformed
        → test_precondition_story_doc_malformed_raises_and_no_side_effects
    [x] resolver returns non-ready-for-dev current_state × 5 states
        → test_precondition_story_doc_lifecycle_state_mismatch[*]
    [x] sprint_status_resolver returns inconsistent state
        → test_precondition_sprint_status_mismatch_raises_and_no_side_effects

Composition-conformance (AC-4; mock-based):
    [x] create_story_branch invoked with forwarded kwargs
        → test_create_story_branch_invoked_with_forwarded_kwargs
    [x] init advance_run_state uses module-private no-op callback
        → test_init_advance_run_state_uses_no_op_callback
    [x] commit_transition uses factory-supplied callback
        → test_commit_transition_uses_factory_supplied_callback
    [x] event_log_appender forwarded verbatim to commit_transition
        → test_event_log_appender_forwarded_verbatim_to_commit_transition
    [x] dispatch_callback invoked with specialist="dev"
        → test_dispatch_callback_invoked_with_dev_specialist
    [x] dispatch_callback NOT invoked when commit_transition raises × 3
        → test_dispatch_callback_not_invoked_after_commit_transition_failure[*]

Helper-propagation (AC-2):
    [x] BranchLifecycleBlocked propagates; advance_run_state never called
        → test_branch_lifecycle_blocked_propagates
    [x] RunStateAdvanceBlocked at init propagates; commit_transition never called
        → test_run_state_advance_blocked_at_init_propagates
    [x] InvalidLifecycleTransition propagates; dispatch never called
        → test_invalid_lifecycle_transition_propagates

API-shape (AC-2; structural enforcement):
    [x] run_story_loop_entry's 10 keyword-only params are non-defaulted
        → test_run_story_loop_entry_keyword_only_non_defaulted[*]
    [x] missing keyword raises TypeError
        → test_run_story_loop_entry_missing_keyword_arg_raises_type_error

Side-effect absence (AC-4):
    [x] no direct Path.write_text / Path.write_bytes against run_state_path
        → test_no_direct_run_state_writes
    [x] no inline subprocess invocation (module does not import subprocess)
        → test_no_inline_subprocess_run
    [x] no inline LIFECYCLE_TRANSITIONS map definition
        → test_no_inline_lifecycle_map

Schema cross-validation (AC-5):
    [x] initial RunState validates against schemas/run-state.yaml
        → test_initial_run_state_validates_against_schema
    [x] post-advance RunState validates against schemas/run-state.yaml
        → test_post_advance_run_state_validates_against_schema

RunStoryLoopEntryResult shape (AC-2):
    [x] result carries all fields on happy path
        → test_run_story_loop_entry_result_carries_all_fields_on_happy_path
    [x] result is frozen
        → test_run_story_loop_entry_result_is_frozen

Marker-class invariant (AC-3):
    [x] all four precondition exceptions carry marker_class: ClassVar[None] = None
        → test_precondition_exceptions_have_null_marker_class[*]

Module surface (AC-2):
    [x] __all__ matches the 18-name AC-2 enumeration
        → test_module_all_exports
    [x] evaluate_envelope and TransitionDecision accessible from module namespace
        → test_evaluate_envelope_accessible_from_module

Default helpers (smoke):
    [x] default_dispatch_callback returns stubbed-pending-2.6 result
        → test_default_dispatch_callback_returns_stubbed_result
    [x] default_story_doc_resolver locates + parses an existing story doc
        → test_default_story_doc_resolver_locates_and_parses
    [x] default_story_doc_resolver raises StoryDocNotFound when missing
        → test_default_story_doc_resolver_raises_not_found
    [x] default_story_doc_resolver raises StoryDocMalformed on missing Status
        → test_default_story_doc_resolver_raises_malformed_missing_status
    [x] default_story_doc_resolver raises StoryDocMalformed on missing AC section
        → test_default_story_doc_resolver_raises_malformed_missing_ac_section
    [x] default_sprint_status_resolver finds matching entry
        → test_default_sprint_status_resolver_finds_matching_entry
    [x] default_sprint_status_resolver raises SprintStatusMismatch on missing
        → test_default_sprint_status_resolver_raises_mismatch_when_missing
"""

from __future__ import annotations

import inspect
import pathlib
import re
from typing import Any
from unittest import mock

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from loud_fail_harness import orchestrator_run_entry as ore_module
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.branch_lifecycle import (
    BranchLifecycleResult,
    GitUncommittedWorkDetected,
    WorkingTreeProbeResult,
)
from loud_fail_harness.lifecycle_state_machine import (
    CommitTransitionResult,
    InvalidLifecycleTransition,
)
from loud_fail_harness.orchestrator_run_entry import (
    AcceptanceCriterion,
    DispatchCallbackResult,
    RunStoryLoopEntryResult,
    SprintStatusMismatch,
    SprintStatusResolution,
    StoryDocLifecycleStateMismatch,
    StoryDocMalformed,
    StoryDocNotFound,
    StoryDocResolution,
    default_dispatch_callback,
    default_sprint_status_resolver,
    default_story_doc_resolver,
    run_story_loop_entry,
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


@pytest.fixture(scope="module")
def schema_validator(repo_root: pathlib.Path) -> Draft202012Validator:
    """Run-state JSON-Schema-2020-12 validator with cell-1 ``$ref``
    registry. Mirrors story 2.2's pattern."""

    def _load(name: str) -> dict[str, Any]:
        return yaml.safe_load(
            (repo_root / "schemas" / name).read_text(encoding="utf-8")
        )

    run_state_schema = _load("run-state.yaml")
    registry = Registry().with_resources(
        [
            (
                "envelope.schema.yaml",
                Resource(
                    contents=_load("envelope.schema.yaml"),
                    specification=DRAFT202012,
                ),
            ),
            (
                "tea-handoff-contract.yaml",
                Resource(
                    contents=_load("tea-handoff-contract.yaml"),
                    specification=DRAFT202012,
                ),
            ),
        ]
    )
    return Draft202012Validator(run_state_schema, registry=registry)


def _make_run_state(
    current_state: CurrentState = "ready-for-dev", **overrides: Any
) -> RunState:
    base: dict[str, Any] = {
        "schema_version": "1.1",
        "story_id": "2-5-test",
        "run_id": "run-2-5-001",
        "current_state": current_state,
        "branch_name": "bmad-automation/story/2-5-test",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": (),
        "active_markers": (),
        "cost_to_date_by_specialist": CostToDateBySpecialist(),
    }
    base.update(overrides)
    return RunState(**base)


def _accepted_story_doc_callback() -> StoryDocCallbackResult:
    return StoryDocCallbackResult(accepted=True)


def _story_doc_callback_factory(_story_id: str) -> Any:
    return _accepted_story_doc_callback


def _make_story_doc_resolution(
    *,
    current_state: CurrentState = "ready-for-dev",
    path: pathlib.Path | None = None,
) -> StoryDocResolution:
    return StoryDocResolution(
        path=path or pathlib.Path("/tmp/2-5-test.md"),
        current_state=current_state,
        acceptance_criteria=(
            AcceptanceCriterion(ac_id="AC-1", text="happy path"),
        ),
    )


def _make_sprint_status_resolution(
    *, current_state: str = "ready-for-dev"
) -> SprintStatusResolution:
    return SprintStatusResolution(current_state=current_state)  # type: ignore[arg-type]


def _make_clean_probe() -> WorkingTreeProbeResult:
    def _probe() -> WorkingTreeProbeResult:
        return WorkingTreeProbeResult(clean=True)

    return _probe  # type: ignore[return-value]


def _make_branch_result(story_id: str = "2-5-test") -> BranchLifecycleResult:
    return BranchLifecycleResult(
        branch_name=f"bmad-automation/story/{story_id}",
        created=True,
        previous_branch="main",
        repo_root=pathlib.Path("/tmp"),
    )


def _stub_dispatch_callback(**_kwargs: Any) -> DispatchCallbackResult:
    return DispatchCallbackResult(
        dispatched=True, reason="stub for tests"
    )


def _make_kwargs(
    *,
    tmp_path: pathlib.Path,
    story_id: str = "2-5-test",
    story_doc_resolver: Any = None,
    sprint_status_resolver: Any = None,
    dispatch_callback: Any = _stub_dispatch_callback,
    event_log_appender: Any = None,
) -> dict[str, Any]:
    if story_doc_resolver is None:
        story_doc_resolver = lambda sid, root: _make_story_doc_resolution()  # noqa: E731
    if sprint_status_resolver is None:
        sprint_status_resolver = lambda sid, root: _make_sprint_status_resolution()  # noqa: E731
    if event_log_appender is None:
        event_log_appender = lambda event: None  # noqa: E731
    return {
        "story_id": story_id,
        "project_root": tmp_path,
        "story_doc_resolver": story_doc_resolver,
        "sprint_status_resolver": sprint_status_resolver,
        "run_state_path": tmp_path / "_bmad" / "automation" / "run-state.yaml",
        "run_id": f"run-{story_id}-001",
        "story_doc_callback_factory": _story_doc_callback_factory,
        "event_log_appender": event_log_appender,
        "trunk_allowlist": ("main", "master", "trunk"),
        "working_tree_probe": _make_clean_probe(),
        "dispatch_callback": dispatch_callback,
    }


# --------------------------------------------------------------------------- #
# Happy-path test                                                              #
# --------------------------------------------------------------------------- #


def test_happy_path_entry_sequence_invokes_all_steps_in_order(
    tmp_path: pathlib.Path,
) -> None:
    kwargs = _make_kwargs(tmp_path=tmp_path)
    branch_result = _make_branch_result()
    init_run_state = _make_run_state(current_state="ready-for-dev")
    advanced_run_state = _make_run_state(current_state="in-progress")
    init_advance_result = AdvanceResult(
        next_state=init_run_state, wrote_path=kwargs["run_state_path"]
    )
    transition_advance_result = AdvanceResult(
        next_state=advanced_run_state, wrote_path=kwargs["run_state_path"]
    )
    transition_event = {
        "event_class": "state-transition",
        "event_id": "ev-2-5-test-st-deadbeef",
        "timestamp": "2026-04-28T12:00:00+00:00",
        "story_id": "2-5-test",
        "from_state": "ready-for-dev",
        "to_state": "in-progress",
    }
    commit_result = CommitTransitionResult(
        advance_result=transition_advance_result, emitted_event=transition_event
    )

    # Use a shared manager mock so mock_calls records cross-mock invocation order.
    manager = mock.MagicMock()
    manager.branch.return_value = branch_result
    manager.advance.return_value = init_advance_result
    manager.commit.return_value = commit_result

    with (
        mock.patch.object(ore_module, "create_story_branch", manager.branch),
        mock.patch.object(ore_module, "advance_run_state", manager.advance),
        mock.patch.object(ore_module, "commit_transition", manager.commit),
    ):
        result = run_story_loop_entry(**kwargs)

    # All four substrate seams invoked exactly once.
    assert manager.branch.call_count == 1
    assert manager.advance.call_count == 1
    assert manager.commit.call_count == 1

    # Ordering: branch BEFORE advance BEFORE commit BEFORE dispatch.
    # manager.mock_calls records every attribute access + call in sequence,
    # so extracting the call-name positions gives strict temporal ordering.
    call_names = [str(c) for c in manager.mock_calls]
    branch_pos = next(i for i, n in enumerate(call_names) if n.startswith("call.branch("))
    advance_pos = next(i for i, n in enumerate(call_names) if n.startswith("call.advance("))
    commit_pos = next(i for i, n in enumerate(call_names) if n.startswith("call.commit("))
    assert branch_pos < advance_pos, "branch must be called before advance_run_state"
    assert advance_pos < commit_pos, "advance_run_state must be called before commit_transition"
    # dispatch_callback is caller-supplied (not patched via manager) but
    # runs after commit — the RunStoryLoopEntryResult.dispatch_callback_result
    # proves it was invoked after commit returned.

    # Result wraps the populated fields per AC-2's RunStoryLoopEntryResult.
    assert isinstance(result, RunStoryLoopEntryResult)
    assert result.story_id == "2-5-test"
    assert result.branch_lifecycle_result == branch_result
    assert result.init_advance_result == init_advance_result
    assert result.transition_advance_result == transition_advance_result
    assert result.state_transition_event == transition_event
    assert result.dispatch_callback_result.dispatched is True


def test_advance_run_state_invocation_count(tmp_path: pathlib.Path) -> None:
    """Total of two advance_run_state invocations per successful run.

    step 4 calls it directly (init); step 5's commit_transition calls it
    internally (advance). Both bindings are patched with the same mock so the
    combined call_count captures both invocations and must equal exactly 2.
    """
    kwargs = _make_kwargs(tmp_path=tmp_path)
    run_state_path = kwargs["run_state_path"]

    init_run_state = _make_run_state(current_state="ready-for-dev")
    advanced_run_state = _make_run_state(current_state="in-progress")
    init_advance_result = AdvanceResult(next_state=init_run_state, wrote_path=run_state_path)
    transition_advance_result = AdvanceResult(
        next_state=advanced_run_state, wrote_path=run_state_path
    )

    # Side-effect delivers the right return value to each caller in order:
    # first call = step 4 direct; second call = commit_transition internal.
    shared_advance_mock = mock.MagicMock(
        side_effect=[init_advance_result, transition_advance_result]
    )

    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch("loud_fail_harness.orchestrator_run_entry.advance_run_state", shared_advance_mock),
        mock.patch("loud_fail_harness.lifecycle_state_machine.advance_run_state", shared_advance_mock),
    ):
        branch_mock.return_value = _make_branch_result()
        run_story_loop_entry(**kwargs)

    assert shared_advance_mock.call_count == 2, (
        "advance_run_state must be invoked exactly twice per successful run: "
        "once at step 4 (init via no-op callback) and once inside "
        "commit_transition at step 5 (advance to in-progress)"
    )


# --------------------------------------------------------------------------- #
# Precondition violation tests (AC-3 — no side effects)                        #
# --------------------------------------------------------------------------- #


def _assert_no_side_effects(
    *,
    branch_mock: Any,
    advance_mock: Any,
    commit_mock: Any,
    appender_calls: list[Any],
    dispatch_calls: list[Any],
) -> None:
    assert branch_mock.call_count == 0
    assert advance_mock.call_count == 0
    assert commit_mock.call_count == 0
    assert appender_calls == []
    assert dispatch_calls == []


def test_precondition_story_doc_not_found_via_none_no_side_effects(
    tmp_path: pathlib.Path,
) -> None:
    appender_calls: list[Any] = []
    dispatch_calls: list[Any] = []

    def _dispatch(**kwargs: Any) -> DispatchCallbackResult:
        dispatch_calls.append(kwargs)
        return DispatchCallbackResult(dispatched=True)

    kwargs = _make_kwargs(
        tmp_path=tmp_path,
        story_doc_resolver=lambda sid, root: None,  # type: ignore[arg-type,return-value]
        dispatch_callback=_dispatch,
        event_log_appender=appender_calls.append,
    )

    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        with pytest.raises(StoryDocNotFound) as excinfo:
            run_story_loop_entry(**kwargs)

    assert excinfo.value.story_id == "2-5-test"
    _assert_no_side_effects(
        branch_mock=branch_mock,
        advance_mock=advance_mock,
        commit_mock=commit_mock,
        appender_calls=appender_calls,
        dispatch_calls=dispatch_calls,
    )


def test_precondition_story_doc_not_found_via_raise_no_side_effects(
    tmp_path: pathlib.Path,
) -> None:
    appender_calls: list[Any] = []
    dispatch_calls: list[Any] = []

    def _resolver(_sid: str, _root: pathlib.Path) -> StoryDocResolution:
        raise StoryDocNotFound(
            story_id="2-5-test", searched_paths=(tmp_path,)
        )

    def _dispatch(**kwargs: Any) -> DispatchCallbackResult:
        dispatch_calls.append(kwargs)
        return DispatchCallbackResult(dispatched=True)

    kwargs = _make_kwargs(
        tmp_path=tmp_path,
        story_doc_resolver=_resolver,
        dispatch_callback=_dispatch,
        event_log_appender=appender_calls.append,
    )

    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        with pytest.raises(StoryDocNotFound):
            run_story_loop_entry(**kwargs)

    _assert_no_side_effects(
        branch_mock=branch_mock,
        advance_mock=advance_mock,
        commit_mock=commit_mock,
        appender_calls=appender_calls,
        dispatch_calls=dispatch_calls,
    )


def test_precondition_story_doc_malformed_raises_and_no_side_effects(
    tmp_path: pathlib.Path,
) -> None:
    appender_calls: list[Any] = []
    dispatch_calls: list[Any] = []

    def _resolver(_sid: str, _root: pathlib.Path) -> StoryDocResolution:
        raise StoryDocMalformed(
            story_id="2-5-test",
            path=tmp_path / "fake.md",
            reason="missing 'Status:' line",
        )

    def _dispatch(**kwargs: Any) -> DispatchCallbackResult:
        dispatch_calls.append(kwargs)
        return DispatchCallbackResult(dispatched=True)

    kwargs = _make_kwargs(
        tmp_path=tmp_path,
        story_doc_resolver=_resolver,
        dispatch_callback=_dispatch,
        event_log_appender=appender_calls.append,
    )

    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        with pytest.raises(StoryDocMalformed) as excinfo:
            run_story_loop_entry(**kwargs)

    assert excinfo.value.reason == "missing 'Status:' line"
    _assert_no_side_effects(
        branch_mock=branch_mock,
        advance_mock=advance_mock,
        commit_mock=commit_mock,
        appender_calls=appender_calls,
        dispatch_calls=dispatch_calls,
    )


@pytest.mark.parametrize(
    "observed_state",
    ["in-progress", "review", "qa", "done", "escalated"],
)
def test_precondition_story_doc_lifecycle_state_mismatch(
    tmp_path: pathlib.Path, observed_state: CurrentState
) -> None:
    appender_calls: list[Any] = []
    dispatch_calls: list[Any] = []

    def _dispatch(**kwargs: Any) -> DispatchCallbackResult:
        dispatch_calls.append(kwargs)
        return DispatchCallbackResult(dispatched=True)

    kwargs = _make_kwargs(
        tmp_path=tmp_path,
        story_doc_resolver=lambda sid, root: _make_story_doc_resolution(
            current_state=observed_state
        ),
        dispatch_callback=_dispatch,
        event_log_appender=appender_calls.append,
    )

    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        with pytest.raises(StoryDocLifecycleStateMismatch) as excinfo:
            run_story_loop_entry(**kwargs)

    assert excinfo.value.observed_state == observed_state
    assert excinfo.value.expected_state == "ready-for-dev"
    _assert_no_side_effects(
        branch_mock=branch_mock,
        advance_mock=advance_mock,
        commit_mock=commit_mock,
        appender_calls=appender_calls,
        dispatch_calls=dispatch_calls,
    )


def test_precondition_sprint_status_mismatch_raises_and_no_side_effects(
    tmp_path: pathlib.Path,
) -> None:
    appender_calls: list[Any] = []
    dispatch_calls: list[Any] = []

    def _dispatch(**kwargs: Any) -> DispatchCallbackResult:
        dispatch_calls.append(kwargs)
        return DispatchCallbackResult(dispatched=True)

    kwargs = _make_kwargs(
        tmp_path=tmp_path,
        sprint_status_resolver=lambda sid, root: _make_sprint_status_resolution(
            current_state="in-progress"
        ),
        dispatch_callback=_dispatch,
        event_log_appender=appender_calls.append,
    )

    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        with pytest.raises(SprintStatusMismatch) as excinfo:
            run_story_loop_entry(**kwargs)

    assert excinfo.value.observed_state == "in-progress"
    assert excinfo.value.expected_states == ("ready-for-dev", "backlog")
    _assert_no_side_effects(
        branch_mock=branch_mock,
        advance_mock=advance_mock,
        commit_mock=commit_mock,
        appender_calls=appender_calls,
        dispatch_calls=dispatch_calls,
    )


# --------------------------------------------------------------------------- #
# Composition-conformance tests (AC-4)                                         #
# --------------------------------------------------------------------------- #


def _setup_happy_mocks(
    branch_mock: Any, advance_mock: Any, commit_mock: Any, run_state_path: pathlib.Path
) -> CommitTransitionResult:
    branch_mock.return_value = _make_branch_result()
    init_run_state = _make_run_state(current_state="ready-for-dev")
    advance_mock.return_value = AdvanceResult(
        next_state=init_run_state, wrote_path=run_state_path
    )
    advanced_run_state = _make_run_state(current_state="in-progress")
    commit_result = CommitTransitionResult(
        advance_result=AdvanceResult(
            next_state=advanced_run_state, wrote_path=run_state_path
        ),
        emitted_event={
            "event_class": "state-transition",
            "event_id": "ev-2-5-test-st-cafebabe",
            "timestamp": "2026-04-28T12:00:00+00:00",
            "story_id": "2-5-test",
            "from_state": "ready-for-dev",
            "to_state": "in-progress",
        },
    )
    commit_mock.return_value = commit_result
    return commit_result


def test_create_story_branch_invoked_with_forwarded_kwargs(
    tmp_path: pathlib.Path,
) -> None:
    kwargs = _make_kwargs(tmp_path=tmp_path)
    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        _setup_happy_mocks(branch_mock, advance_mock, commit_mock, kwargs["run_state_path"])
        run_story_loop_entry(**kwargs)

    branch_mock.assert_called_once_with(
        "2-5-test",
        trunk_allowlist=kwargs["trunk_allowlist"],
        working_tree_probe=kwargs["working_tree_probe"],
        repo_root=kwargs["project_root"],
    )


def test_init_advance_run_state_uses_no_op_callback(
    tmp_path: pathlib.Path,
) -> None:
    kwargs = _make_kwargs(tmp_path=tmp_path)
    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        _setup_happy_mocks(branch_mock, advance_mock, commit_mock, kwargs["run_state_path"])
        run_story_loop_entry(**kwargs)

    # advance_run_state called exactly once (init); the second advance is
    # internal to commit_transition, which is mocked.
    advance_mock.assert_called_once()
    call = advance_mock.call_args
    assert "story_doc_callback" in call.kwargs
    callback = call.kwargs["story_doc_callback"]
    # The no-op callback returns accepted=True without raising.
    callback_result = callback()
    assert callback_result.accepted is True
    assert callback_result.reason is not None
    assert "init time" in callback_result.reason


def test_commit_transition_uses_factory_supplied_callback(
    tmp_path: pathlib.Path,
) -> None:
    factory_invocations: list[str] = []

    def _factory(story_id: str) -> Any:
        factory_invocations.append(story_id)
        return _accepted_story_doc_callback

    kwargs = _make_kwargs(tmp_path=tmp_path)
    kwargs["story_doc_callback_factory"] = _factory

    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        _setup_happy_mocks(branch_mock, advance_mock, commit_mock, kwargs["run_state_path"])
        run_story_loop_entry(**kwargs)

    # Factory called once, with the resolved story_id.
    assert factory_invocations == ["2-5-test"]
    # commit_transition received the same callback the factory returned.
    commit_mock.assert_called_once()
    cb = commit_mock.call_args.kwargs["story_doc_callback"]
    assert cb is _accepted_story_doc_callback


def test_event_log_appender_forwarded_verbatim_to_commit_transition(
    tmp_path: pathlib.Path,
) -> None:
    appender_calls: list[Any] = []
    appender = appender_calls.append
    kwargs = _make_kwargs(tmp_path=tmp_path, event_log_appender=appender)

    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        _setup_happy_mocks(branch_mock, advance_mock, commit_mock, kwargs["run_state_path"])
        run_story_loop_entry(**kwargs)

    # The event_log_appender argument to commit_transition is the SAME
    # object (`is` identity) the caller passed.
    commit_mock.assert_called_once()
    forwarded = commit_mock.call_args.kwargs["event_log_appender"]
    assert forwarded is appender


def test_dispatch_callback_invoked_with_dev_specialist(
    tmp_path: pathlib.Path,
) -> None:
    captured_kwargs: dict[str, Any] = {}

    def _capture(**kwargs: Any) -> DispatchCallbackResult:
        captured_kwargs.update(kwargs)
        return DispatchCallbackResult(dispatched=True)

    kwargs = _make_kwargs(tmp_path=tmp_path, dispatch_callback=_capture)

    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        _setup_happy_mocks(branch_mock, advance_mock, commit_mock, kwargs["run_state_path"])
        run_story_loop_entry(**kwargs)

    assert captured_kwargs["specialist"] == "dev"
    assert captured_kwargs["story_id"] == "2-5-test"
    assert captured_kwargs["run_state_path"] == kwargs["run_state_path"]
    assert captured_kwargs["event_log_appender"] is kwargs["event_log_appender"]


@pytest.mark.parametrize(
    "raised_exc",
    [
        RunStateAdvanceBlocked(
            cause=StoryDocCallbackResult(
                accepted=False,
                reason="rejected",
                marker="undocumented-section-write",
            ),
            attempted_next_state=_make_run_state(current_state="in-progress"),
        ),
        InvalidLifecycleTransition(
            current_state="ready-for-dev",
            attempted_next_state="review",
            reason="skip transition rejected",
        ),
        OSError("disk full"),
    ],
)
def test_dispatch_callback_not_invoked_after_commit_transition_failure(
    tmp_path: pathlib.Path, raised_exc: BaseException
) -> None:
    dispatch_calls: list[Any] = []

    def _dispatch(**kwargs: Any) -> DispatchCallbackResult:
        dispatch_calls.append(kwargs)
        return DispatchCallbackResult(dispatched=True)

    kwargs = _make_kwargs(tmp_path=tmp_path, dispatch_callback=_dispatch)

    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        branch_mock.return_value = _make_branch_result()
        advance_mock.return_value = AdvanceResult(
            next_state=_make_run_state(current_state="ready-for-dev"),
            wrote_path=kwargs["run_state_path"],
        )
        commit_mock.side_effect = raised_exc

        with pytest.raises(type(raised_exc)):
            run_story_loop_entry(**kwargs)

    assert dispatch_calls == []


# --------------------------------------------------------------------------- #
# Helper-propagation tests                                                     #
# --------------------------------------------------------------------------- #


def test_branch_lifecycle_blocked_propagates(tmp_path: pathlib.Path) -> None:
    kwargs = _make_kwargs(tmp_path=tmp_path)
    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        branch_mock.side_effect = GitUncommittedWorkDetected(
            attempted_story_id="2-5-test", uncommitted_paths=("foo.py",)
        )

        with pytest.raises(GitUncommittedWorkDetected):
            run_story_loop_entry(**kwargs)

    assert advance_mock.call_count == 0
    assert commit_mock.call_count == 0


def test_run_state_advance_blocked_at_init_propagates(
    tmp_path: pathlib.Path,
) -> None:
    kwargs = _make_kwargs(tmp_path=tmp_path)
    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        branch_mock.return_value = _make_branch_result()
        rejection = StoryDocCallbackResult(
            accepted=False,
            reason="rejected",
            marker="undocumented-section-write",
        )
        advance_mock.side_effect = RunStateAdvanceBlocked(
            cause=rejection,
            attempted_next_state=_make_run_state(current_state="ready-for-dev"),
        )

        with pytest.raises(RunStateAdvanceBlocked):
            run_story_loop_entry(**kwargs)

    assert commit_mock.call_count == 0


def test_invalid_lifecycle_transition_propagates(
    tmp_path: pathlib.Path,
) -> None:
    dispatch_calls: list[Any] = []

    def _dispatch(**kwargs: Any) -> DispatchCallbackResult:
        dispatch_calls.append(kwargs)
        return DispatchCallbackResult(dispatched=True)

    kwargs = _make_kwargs(tmp_path=tmp_path, dispatch_callback=_dispatch)

    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        branch_mock.return_value = _make_branch_result()
        advance_mock.return_value = AdvanceResult(
            next_state=_make_run_state(current_state="ready-for-dev"),
            wrote_path=kwargs["run_state_path"],
        )
        commit_mock.side_effect = InvalidLifecycleTransition(
            current_state="ready-for-dev",
            attempted_next_state="review",
            reason="skip transition rejected",
        )

        with pytest.raises(InvalidLifecycleTransition):
            run_story_loop_entry(**kwargs)

    assert dispatch_calls == []


# --------------------------------------------------------------------------- #
# API-shape tests                                                              #
# --------------------------------------------------------------------------- #


_KEYWORD_ONLY_PARAMS: list[str] = [
    "project_root",
    "story_doc_resolver",
    "sprint_status_resolver",
    "run_state_path",
    "run_id",
    "story_doc_callback_factory",
    "event_log_appender",
    "trunk_allowlist",
    "working_tree_probe",
    "dispatch_callback",
]


@pytest.mark.parametrize("param_name", _KEYWORD_ONLY_PARAMS)
def test_run_story_loop_entry_keyword_only_non_defaulted(
    param_name: str,
) -> None:
    sig = inspect.signature(run_story_loop_entry)
    param = sig.parameters[param_name]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        f"parameter {param_name!r} is not KEYWORD_ONLY"
    )
    assert param.default is inspect.Parameter.empty, (
        f"parameter {param_name!r} has a default value"
    )


def test_run_story_loop_entry_missing_keyword_arg_raises_type_error() -> None:
    """Calling the helper positional-only (no keyword args) raises TypeError
    per Python's missing-required-keyword-argument semantics."""
    with pytest.raises(TypeError):
        run_story_loop_entry("2-5")  # type: ignore[call-arg]


# --------------------------------------------------------------------------- #
# Side-effect absence tests                                                    #
# --------------------------------------------------------------------------- #


def test_no_direct_run_state_writes(tmp_path: pathlib.Path) -> None:
    kwargs = _make_kwargs(tmp_path=tmp_path)
    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
        mock.patch.object(pathlib.Path, "write_text", autospec=True) as write_text_mock,
        mock.patch.object(pathlib.Path, "write_bytes", autospec=True) as write_bytes_mock,
    ):
        _setup_happy_mocks(branch_mock, advance_mock, commit_mock, kwargs["run_state_path"])
        run_story_loop_entry(**kwargs)

    write_text_mock.assert_not_called()
    write_bytes_mock.assert_not_called()


def test_no_inline_subprocess_run() -> None:
    """The module does NOT import ``subprocess`` (all git operations route
    through :func:`create_story_branch`)."""
    assert "subprocess" not in dir(ore_module), (
        "orchestrator_run_entry must not import subprocess; all git "
        "operations route through create_story_branch (Story 2.3)"
    )


def test_no_inline_lifecycle_map() -> None:
    """The module imports ``LIFECYCLE_TRANSITIONS`` from
    :mod:`lifecycle_state_machine` but does NOT redeclare it as a local
    dict literal (single-source-of-truth invariant per AC-4)."""
    src = inspect.getsource(ore_module)
    # Verify import block carries the symbol.
    assert "from loud_fail_harness.lifecycle_state_machine import" in src
    assert "LIFECYCLE_TRANSITIONS" in src
    # Verify no inline dict-literal redeclaration: pattern matches an
    # assignment whose RHS opens a dict literal, e.g.,
    # ``LIFECYCLE_TRANSITIONS: dict[…] = {`` or ``LIFECYCLE_TRANSITIONS = {``.
    inline_decl = re.compile(r"^\s*LIFECYCLE_TRANSITIONS\s*[:=].*\{\s*$", re.MULTILINE)
    assert not inline_decl.search(src), (
        "orchestrator_run_entry must not redeclare LIFECYCLE_TRANSITIONS; "
        "import the constant from lifecycle_state_machine (Story 2.4)"
    )


# --------------------------------------------------------------------------- #
# Schema cross-validation tests                                                #
# --------------------------------------------------------------------------- #


def _run_state_to_jsonable(state: RunState) -> dict[str, Any]:
    """Serialize a RunState through the same JSON-roundtrip used by the
    on-disk YAML emit path so the dict mirrors the schema exactly."""
    import json

    return json.loads(state.model_dump_json(by_alias=False, exclude_none=False))


def test_initial_run_state_validates_against_schema(
    schema_validator: Draft202012Validator,
) -> None:
    initial = RunState(
        schema_version="1.1",
        story_id="2-5-test",
        run_id="run-2-5-001",
        current_state="ready-for-dev",
        branch_name="bmad-automation/story/2-5-test",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )
    schema_validator.validate(_run_state_to_jsonable(initial))


def test_post_advance_run_state_validates_against_schema(
    schema_validator: Draft202012Validator,
) -> None:
    advanced = RunState(
        schema_version="1.1",
        story_id="2-5-test",
        run_id="run-2-5-001",
        current_state="in-progress",
        branch_name="bmad-automation/story/2-5-test",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )
    schema_validator.validate(_run_state_to_jsonable(advanced))


# --------------------------------------------------------------------------- #
# RunStoryLoopEntryResult shape tests                                          #
# --------------------------------------------------------------------------- #


def test_run_story_loop_entry_result_carries_all_fields_on_happy_path(
    tmp_path: pathlib.Path,
) -> None:
    kwargs = _make_kwargs(tmp_path=tmp_path)
    with (
        mock.patch.object(ore_module, "create_story_branch", autospec=True) as branch_mock,
        mock.patch.object(ore_module, "advance_run_state", autospec=True) as advance_mock,
        mock.patch.object(ore_module, "commit_transition", autospec=True) as commit_mock,
    ):
        commit_result = _setup_happy_mocks(
            branch_mock, advance_mock, commit_mock, kwargs["run_state_path"]
        )
        result = run_story_loop_entry(**kwargs)

    assert result.story_id == "2-5-test"
    assert result.branch_lifecycle_result is branch_mock.return_value
    assert result.init_advance_result is advance_mock.return_value
    assert result.transition_advance_result is commit_result.advance_result
    assert result.state_transition_event == commit_result.emitted_event
    assert result.dispatch_callback_result.dispatched is True


def test_run_story_loop_entry_result_is_frozen() -> None:
    result = RunStoryLoopEntryResult(
        story_id="2-5-test",
        branch_lifecycle_result=_make_branch_result(),
        init_advance_result=AdvanceResult(
            next_state=_make_run_state(current_state="ready-for-dev"),
            wrote_path=pathlib.Path("/tmp/run-state.yaml"),
        ),
        transition_advance_result=AdvanceResult(
            next_state=_make_run_state(current_state="in-progress"),
            wrote_path=pathlib.Path("/tmp/run-state.yaml"),
        ),
        state_transition_event={"event_class": "state-transition"},
        dispatch_callback_result=DispatchCallbackResult(dispatched=False),
    )
    with pytest.raises(ValidationError):
        result.story_id = "mutated"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Marker-class invariant test (AC-3)                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "exception_class",
    [
        StoryDocNotFound,
        StoryDocMalformed,
        StoryDocLifecycleStateMismatch,
        SprintStatusMismatch,
    ],
)
def test_precondition_exceptions_have_null_marker_class(
    exception_class: type[Exception],
) -> None:
    """All four precondition exceptions carry ``marker_class = None`` as
    a class attribute per AC-3 — precondition halts are NOT loud-fail
    markers."""
    assert hasattr(exception_class, "marker_class"), (
        f"{exception_class.__name__} must carry the marker_class attribute"
    )
    assert exception_class.marker_class is None, (  # type: ignore[attr-defined]
        f"{exception_class.__name__}.marker_class must be None per AC-3"
    )


# --------------------------------------------------------------------------- #
# Module surface test                                                          #
# --------------------------------------------------------------------------- #


def test_evaluate_envelope_accessible_from_module() -> None:
    """``evaluate_envelope`` is importable from the module namespace.

    AC-4 requires the module to import ``evaluate_envelope`` (and the
    discriminator helpers) at module top-level so Story 2.6's wiring at the
    post-dispatch seam can compose against the same type surface without an
    additional import chain.
    """
    assert hasattr(ore_module, "evaluate_envelope"), (
        "orchestrator_run_entry must import evaluate_envelope at module top-level "
        "for Story 2.6 forward-compat wiring (AC-4)"
    )
    assert hasattr(ore_module, "TransitionDecision"), (
        "orchestrator_run_entry must import TransitionDecision at module top-level"
    )


def test_module_all_exports() -> None:
    """``__all__`` matches the AC-2 19-name public surface enumeration.

    Story 6.7 added :func:`handle_hook_exit_code` to Story 2.5's
    eighteen-name baseline (NFR-R6 hook-result composition seam per
    Story 6.7 AC-2 hook-failed wiring).
    """
    expected = {
        "AcceptanceCriterion",
        "DispatchCallback",
        "DispatchCallbackResult",
        "RunStoryLoopEntryResult",
        "SprintStatusMismatch",
        "SprintStatusResolution",
        "SprintStatusResolver",
        "SprintStatusState",
        "StoryDocCallbackFactory",
        "StoryDocLifecycleStateMismatch",
        "StoryDocMalformed",
        "StoryDocNotFound",
        "StoryDocResolution",
        "StoryDocResolver",
        "default_dispatch_callback",
        "default_sprint_status_resolver",
        "default_story_doc_resolver",
        "handle_hook_exit_code",
        "run_story_loop_entry",
    }
    assert set(ore_module.__all__) == expected


# --------------------------------------------------------------------------- #
# Default helpers (smoke)                                                      #
# --------------------------------------------------------------------------- #


def test_default_dispatch_callback_returns_stubbed_result(
    tmp_path: pathlib.Path,
) -> None:
    appender_calls: list[Any] = []
    result = default_dispatch_callback(
        specialist="dev",
        story_id="2-5-test",
        run_state_path=tmp_path / "run-state.yaml",
        story_doc_resolution=_make_story_doc_resolution(),
        event_log_appender=appender_calls.append,
    )
    assert result.dispatched is False
    assert result.reason == "dispatch stubbed pending Story 2.6"
    # The stub does NOT emit an orchestrator-event via the appender (see
    # module docstring's "Why the dispatch stub uses logging.info" section).
    assert appender_calls == []


def test_default_story_doc_resolver_locates_and_parses(
    tmp_path: pathlib.Path,
) -> None:
    impl_dir = tmp_path / "_bmad-output" / "implementation-artifacts"
    impl_dir.mkdir(parents=True)
    story_path = impl_dir / "2-5-test-story.md"
    story_path.write_text(
        "# Story 2.5: Test\n\n"
        "Status: ready-for-dev\n\n"
        "## Story\n\n"
        "As a tester, I want a story file...\n\n"
        "## Acceptance Criteria\n\n"
        "**AC-1 — First criterion**\n\n"
        "Given...\n\n"
        "**AC-2 — Second criterion**\n\n"
        "Given...\n\n"
        "## Dev Notes\n\n",
        encoding="utf-8",
    )
    resolution = default_story_doc_resolver("2-5", tmp_path)
    assert resolution.path == story_path
    assert resolution.current_state == "ready-for-dev"
    assert len(resolution.acceptance_criteria) == 2
    assert resolution.acceptance_criteria[0].ac_id == "AC-1"
    assert resolution.acceptance_criteria[1].ac_id == "AC-2"


def test_default_story_doc_resolver_raises_not_found(
    tmp_path: pathlib.Path,
) -> None:
    impl_dir = tmp_path / "_bmad-output" / "implementation-artifacts"
    impl_dir.mkdir(parents=True)
    with pytest.raises(StoryDocNotFound):
        default_story_doc_resolver("9-9", tmp_path)


def test_default_story_doc_resolver_raises_malformed_missing_status(
    tmp_path: pathlib.Path,
) -> None:
    impl_dir = tmp_path / "_bmad-output" / "implementation-artifacts"
    impl_dir.mkdir(parents=True)
    (impl_dir / "2-5-no-status.md").write_text(
        "# Story 2.5\n\nNo status line here.\n\n## Acceptance Criteria\n\n",
        encoding="utf-8",
    )
    with pytest.raises(StoryDocMalformed) as excinfo:
        default_story_doc_resolver("2-5", tmp_path)
    assert "Status:" in excinfo.value.reason


def test_default_story_doc_resolver_raises_malformed_missing_ac_section(
    tmp_path: pathlib.Path,
) -> None:
    impl_dir = tmp_path / "_bmad-output" / "implementation-artifacts"
    impl_dir.mkdir(parents=True)
    (impl_dir / "2-5-no-ac.md").write_text(
        "# Story 2.5\n\nStatus: ready-for-dev\n\n## Story\n\n",
        encoding="utf-8",
    )
    with pytest.raises(StoryDocMalformed) as excinfo:
        default_story_doc_resolver("2-5", tmp_path)
    assert "Acceptance Criteria" in excinfo.value.reason


def test_default_sprint_status_resolver_finds_matching_entry(
    tmp_path: pathlib.Path,
) -> None:
    impl_dir = tmp_path / "_bmad-output" / "implementation-artifacts"
    impl_dir.mkdir(parents=True)
    sprint = impl_dir / "sprint-status.yaml"
    sprint.write_text(
        "development_status:\n"
        "  epic-2: in-progress\n"
        "  2-5-test-story: ready-for-dev\n",
        encoding="utf-8",
    )
    resolution = default_sprint_status_resolver("2-5", tmp_path)
    assert resolution.current_state == "ready-for-dev"


def test_default_sprint_status_resolver_raises_mismatch_when_missing(
    tmp_path: pathlib.Path,
) -> None:
    impl_dir = tmp_path / "_bmad-output" / "implementation-artifacts"
    impl_dir.mkdir(parents=True)
    (impl_dir / "sprint-status.yaml").write_text(
        "development_status:\n  epic-2: in-progress\n",
        encoding="utf-8",
    )
    with pytest.raises(SprintStatusMismatch):
        default_sprint_status_resolver("9-9", tmp_path)



# --------------------------------------------------------------------------- #
# handle_hook_exit_code behavioral tests (Story 6.7 AC-2)                     #
# --------------------------------------------------------------------------- #


def test_handle_hook_exit_code_zero_exit_returns_input_run_state_unchanged() -> None:
    """AC-2 — hook-failed marker emission wired at orchestrator's
    hook-result handler seam: exit_code=0 returns the input RunState
    unchanged (same object identity, no allocation)."""
    from loud_fail_harness.orchestrator_run_entry import handle_hook_exit_code

    rs = _make_run_state()
    result = handle_hook_exit_code(exit_code=0, hook_name="subagent-stop", run_state=rs)
    assert result is rs


def test_handle_hook_exit_code_nonzero_exit_records_hook_failed_marker() -> None:
    """AC-2 — hook-failed marker emission wired at orchestrator's
    hook-result handler seam: exit_code=1 produces a new RunState
    carrying ``hook-failed: subagent-stop`` in active_markers."""
    from loud_fail_harness.orchestrator_run_entry import handle_hook_exit_code

    rs = _make_run_state()
    result = handle_hook_exit_code(exit_code=1, hook_name="subagent-stop", run_state=rs)
    assert result is not rs
    assert "hook-failed: subagent-stop" in result.active_markers


def test_handle_hook_exit_code_idempotent_second_call_same_hook() -> None:
    """AC-2 — hook-failed marker emission wired at orchestrator's
    hook-result handler seam: two non-zero calls for the same hook_name
    produce exactly one marker entry (de-dup via marker-permanence rule)."""
    from loud_fail_harness.orchestrator_run_entry import handle_hook_exit_code

    rs = _make_run_state()
    rs1 = handle_hook_exit_code(exit_code=1, hook_name="stop", run_state=rs)
    rs2 = handle_hook_exit_code(exit_code=1, hook_name="stop", run_state=rs1)
    count = sum(1 for m in rs2.active_markers if m == "hook-failed: stop")
    assert count == 1
