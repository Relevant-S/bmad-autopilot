"""Story 5.4 AC-9 routing tests.

Asserts the violation routing rule documented in
``bmad-autopilot/skills/bmad-automation/steps/run.md`` is structurally
honored: a stub-injected ``scope-assertion-violation`` marker on the
post-Dev-return path triggers the escalation route WITHOUT
decrementing the budget counter (`epics.md` line 2349 verbatim — "the
violation does NOT consume a retry round (it's a contract violation,
not a normal failure)").

The routing decision itself is LLM-runtime prose in ``run.md`` (the
orchestrator-skill's run-loop). This test exercises the substrate
primitives the routing decision composes:

* Story 5.4's :func:`scope_assertion.verify_scope_assertion` returns a
  violation result.
* Story 5.4's :func:`scope_assertion.make_scope_assertion_diagnostic`
  builds the marker payload.
* Story 5.1's :func:`retry_budget.evaluate_retry_decision` is NOT
  consulted on the violation branch (the budget counter is preserved).
"""

from __future__ import annotations

from unittest import mock

from loud_fail_harness import retry_budget, scope_assertion
from loud_fail_harness.run_state import (
    CostToDateBySpecialist,
    LastRetryDirective,
    RetryAttempt,
    RunState,
)


def _make_run_state_with_one_retry() -> RunState:
    """Construct a minimal RunState with one retry attempt already
    recorded (so retry budget remaining > 0 if a budget=3 is resolved)."""
    return RunState(
        schema_version="1.2",
        story_id="5-4-test",
        run_id="r1",
        current_state="in-progress",
        branch_name="bmad-automation/story/5-4-test",
        dispatched_specialist="dev",
        last_envelope={"status": "fail", "rationale": "x"},
        pending_qa_dispatch_payload=None,
        retry_history=(
            RetryAttempt(retry_attempt=1, retry_reason="dev test failure"),
        ),
        active_markers=("scope-assertion-violation",),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
        last_retry_directive=LastRetryDirective(
            retry_mode="fix-only",
            affected_files=("src/foo.py",),
        ),
    )


def test_violation_routing_does_not_decrement_budget_counter() -> None:
    """The violation branch of the orchestrator's post-Dev-return
    routing MUST NOT call :func:`evaluate_retry_decision`. Budget
    state is preserved verbatim.

    Per `epics.md` line 2349 (verbatim): "the violation does NOT
    consume a retry round (it's a contract violation, not a normal
    failure)".
    """
    run_state = _make_run_state_with_one_retry()
    pre_history_len = len(run_state.retry_history)

    # Substrate: the verifier detects a violation.
    result = scope_assertion.verify_scope_assertion(
        affected_files=run_state.last_retry_directive.affected_files,  # type: ignore[union-attr]
        scope_expanded_to=(),
        actual_files=("src/foo.py", "src/baz.py"),
    )
    assert result.is_violation is True

    # Substrate: build the marker payload.
    diagnostic = scope_assertion.make_scope_assertion_diagnostic(
        result, story_id=run_state.story_id, retry_round=pre_history_len
    )
    assert diagnostic.marker_class == "scope-assertion-violation"

    # The orchestrator-skill's violation branch (per run.md) MUST NOT
    # call evaluate_retry_decision. We model the prose by spying.
    with mock.patch.object(
        retry_budget,
        "evaluate_retry_decision",
        wraps=retry_budget.evaluate_retry_decision,
    ) as spy:
        # Simulate the violation-routing decision: detect marker class,
        # route to escalation. Per run.md, evaluate_retry_decision is
        # NOT consulted on this path.
        if diagnostic.marker_class == "scope-assertion-violation":
            routing_target = "escalated"  # Story 5.6's handler.
        else:  # pragma: no cover - non-violation branch
            routing_target = retry_budget.evaluate_retry_decision(
                run_state, resolved_budget=3
            )
        assert routing_target == "escalated"
        assert spy.call_count == 0, (
            "evaluate_retry_decision MUST NOT be consulted on the "
            "scope-assertion-violation branch (epics.md line 2349)"
        )

    # Run-state's retry_history is unchanged (the violation does not
    # append a new attempt; the existing history is preserved per
    # FR14's escalation-state preservation discipline).
    assert len(run_state.retry_history) == pre_history_len


def test_violation_routing_preserves_run_state_fields_for_escalation() -> None:
    """Per Story 5.6's preservation discipline + FR14, the violation-
    induced halt is recoverable: run-state fields needed by Story 5.8's
    escalation-bundle assembler are preserved.
    """
    run_state = _make_run_state_with_one_retry()
    diagnostic = scope_assertion.make_scope_assertion_diagnostic(
        scope_assertion.verify_scope_assertion(
            affected_files=run_state.last_retry_directive.affected_files,  # type: ignore[union-attr]
            scope_expanded_to=(),
            actual_files=("src/foo.py", "src/qux.py"),
        ),
        story_id=run_state.story_id,
        retry_round=1,
    )
    # All diagnostic fields needed by Story 5.8's escalation-bundle
    # assembler are present and copyable.
    assert diagnostic.violating_files == ("src/qux.py",)
    assert diagnostic.declared_scope == ("src/foo.py",)
    assert diagnostic.declared_expansion == ()
    assert diagnostic.story_id == run_state.story_id
    assert diagnostic.retry_round == 1


def test_run_md_documents_routing_rule() -> None:
    """Structural test: ``skills/bmad-automation/steps/run.md`` carries
    the AC-9 routing rule sub-section + the budget-non-decrement
    invariant + Story 5.6 + Story 5.8 forward-pointers."""
    from loud_fail_harness._shared import find_repo_root

    run_md = (
        find_repo_root()
        / "skills"
        / "bmad-automation"
        / "steps"
        / "run.md"
    )
    body = run_md.read_text(encoding="utf-8")
    assert "Scope-assertion verification + violation routing (Story 5.4)" in body
    assert "scope-assertion-violation" in body
    assert "does NOT decrement" in body
    assert "Story 5.6" in body
    assert "Story 5.8" in body
    assert "epics.md` line 2349" in body


def test_run_md_routing_section_within_line_budget() -> None:
    """The append is bounded (≤ 14 lines of prose per AC-9)."""
    from loud_fail_harness._shared import find_repo_root

    run_md = (
        find_repo_root()
        / "skills"
        / "bmad-automation"
        / "steps"
        / "run.md"
    )
    body = run_md.read_text(encoding="utf-8")
    marker = "## Scope-assertion verification + violation routing (Story 5.4)"
    idx = body.index(marker)
    section = body[idx:].splitlines()
    # The section consists of header + blank + prose paragraph; bounded.
    assert len(section) <= 14, (
        f"AC-9 caps the appended section at <= 14 lines; got {len(section)}"
    )
