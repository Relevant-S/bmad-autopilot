"""Story 6.7 — Orchestrator-side marker-wiring substrate tests.

Witnesses NFR-P2 + NFR-P4 + NFR-R6 + the verbatim Story 6.7 ACs at
``epics.md`` lines 2739-2771.

Each test docstring cites the specific AC (or sub-claim) it witnesses
verbatim per Pattern 5's named-invariant convention (precedent: every
test in :mod:`tests.test_evidence_linkability` /
:mod:`tests.test_cost_streaming` / :mod:`tests.test_retry_history`).
"""

from __future__ import annotations

from typing import Any

import pytest

from loud_fail_harness.marker_wiring import (
    CONTEXT_NEAR_LIMIT_MARKER,
    HOOK_FAILED_MARKER,
    HOOK_NAMES,
    SPECIALIST_NAMES,
    SPECIALIST_TIMEOUT_MARKER,
    compute_alphabetical_marker_order,
    record_context_near_limit_marker,
    record_hook_failure_marker,
    record_marker_with_context,
    record_specialist_timeout_marker,
)
from loud_fail_harness.run_state import CostToDateBySpecialist, RunState
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
)


# --------------------------------------------------------------------------- #
# Test fixtures                                                               #
# --------------------------------------------------------------------------- #


def _make_run_state(**overrides: Any) -> RunState:
    """Build a minimal valid :class:`RunState` instance for tests."""
    base: dict[str, Any] = {
        "schema_version": "1.1",
        "story_id": "6-7-test",
        "run_id": "run-001",
        "current_state": "in-progress",
        "branch_name": "bmad-automation/story/6-7-test",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": (),
        "active_markers": (),
        "cost_to_date_by_specialist": CostToDateBySpecialist(),
    }
    base.update(overrides)
    return RunState(**base)


# --------------------------------------------------------------------------- #
# (a) record_specialist_timeout_marker — NFR-P2 / AC-1                        #
# --------------------------------------------------------------------------- #


def test_record_specialist_timeout_marker_happy_path() -> None:
    """AC-1: input run-state with empty active_markers → output run-state
    with ``("specialist-timeout: timeout-exceeded",)`` AND
    ``marker_contexts == {"specialist-timeout": {"specialist": "dev",
    "timeout_seconds": "900"}}``."""
    rs = _make_run_state()
    out = record_specialist_timeout_marker(
        run_state=rs, specialist="dev", timeout_seconds=900
    )
    assert out.active_markers == ("specialist-timeout: timeout-exceeded",)
    assert out.marker_contexts == {
        "specialist-timeout": {"specialist": "dev", "timeout_seconds": "900"}
    }


def test_record_specialist_timeout_marker_idempotent_same_sub_cause() -> None:
    """AC-1: a second call with the SAME sub_cause for an already-emitted
    marker returns the input run-state unchanged (Story 1.4
    marker-permanence rule)."""
    rs = _make_run_state()
    once = record_specialist_timeout_marker(
        run_state=rs, specialist="qa", timeout_seconds=600
    )
    twice = record_specialist_timeout_marker(
        run_state=once, specialist="qa", timeout_seconds=600
    )
    assert twice is once
    assert twice.active_markers == ("specialist-timeout: timeout-exceeded",)


def test_record_specialist_timeout_marker_explicit_context_budget_sub_cause() -> None:
    """AC-1: explicit ``sub_cause="context-budget-exceeded"`` is supported
    for the future thickening Story 2.6's docstring at
    ``specialist_dispatch.py`` reserves for Epic 6."""
    rs = _make_run_state()
    out = record_specialist_timeout_marker(
        run_state=rs,
        specialist="review-bmad",
        timeout_seconds=900,
        sub_cause="context-budget-exceeded",
    )
    assert out.active_markers == (
        "specialist-timeout: context-budget-exceeded",
    )


def test_record_specialist_timeout_marker_first_context_wins() -> None:
    """AC-1: marker_contexts FIRST-emission wins. A second call with a
    DIFFERENT sub_cause appends a new active_markers entry but does NOT
    overwrite marker_contexts["specialist-timeout"] (the FIRST emission's
    context is preserved per the marker-permanence rule)."""
    rs = _make_run_state()
    once = record_specialist_timeout_marker(
        run_state=rs, specialist="dev", timeout_seconds=900
    )
    twice = record_specialist_timeout_marker(
        run_state=once,
        specialist="qa",
        timeout_seconds=600,
        sub_cause="context-budget-exceeded",
    )
    assert twice.active_markers == (
        "specialist-timeout: timeout-exceeded",
        "specialist-timeout: context-budget-exceeded",
    )
    # First emission's context wins.
    assert twice.marker_contexts == {
        "specialist-timeout": {"specialist": "dev", "timeout_seconds": "900"}
    }


# --------------------------------------------------------------------------- #
# (b) record_hook_failure_marker — NFR-R6 / AC-2                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("hook_name", HOOK_NAMES)
def test_record_hook_failure_marker_happy_path(hook_name: str) -> None:
    """AC-2: each of the three hook names produces a
    ``hook-failed: <hook-name>`` marker entry; marker_contexts is
    UNCHANGED (taxonomy ``pointer_context_fields: []``)."""
    rs = _make_run_state()
    out = record_hook_failure_marker(run_state=rs, hook_name=hook_name)
    assert out.active_markers == (f"hook-failed: {hook_name}",)
    assert out.marker_contexts == {}


def test_record_hook_failure_marker_idempotent_per_hook_name() -> None:
    """AC-2: per-hook-name de-dup. A second call for the SAME hook
    returns the input run-state unchanged (Story 1.4 marker-permanence
    rule)."""
    rs = _make_run_state()
    once = record_hook_failure_marker(run_state=rs, hook_name="stop")
    twice = record_hook_failure_marker(run_state=once, hook_name="stop")
    assert twice is once
    assert twice.active_markers == ("hook-failed: stop",)


def test_record_hook_failure_marker_three_distinct_hooks_three_entries() -> None:
    """AC-2: THREE distinct calls for ``subagent-stop`` + ``stop`` +
    ``session-start`` produce three entries (none de-duplicated against
    each other)."""
    rs = _make_run_state()
    out = rs
    for hook_name in ("subagent-stop", "stop", "session-start"):
        out = record_hook_failure_marker(run_state=out, hook_name=hook_name)
    assert set(out.active_markers) == {
        "hook-failed: subagent-stop",
        "hook-failed: stop",
        "hook-failed: session-start",
    }
    assert len(out.active_markers) == 3


# --------------------------------------------------------------------------- #
# (c) record_context_near_limit_marker — NFR-P4 / AC-3                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("specialist", SPECIALIST_NAMES)
def test_record_context_near_limit_marker_happy_path(specialist: str) -> None:
    """AC-3: each of the three specialist names produces a
    ``context-near-limit: <specialist>`` marker entry; marker_contexts
    is populated with ``{"specialist": <name>}`` per the post-6.7
    taxonomy ``pointer_context_fields: [specialist]`` extension."""
    rs = _make_run_state()
    out = record_context_near_limit_marker(run_state=rs, specialist=specialist)
    assert out.active_markers == (f"context-near-limit: {specialist}",)
    assert out.marker_contexts == {
        "context-near-limit": {"specialist": specialist}
    }


def test_record_context_near_limit_marker_idempotent_per_specialist() -> None:
    """AC-3: per-specialist de-dup. A second call for the same specialist
    returns the input run-state unchanged (Story 1.4 marker-permanence
    rule)."""
    rs = _make_run_state()
    once = record_context_near_limit_marker(run_state=rs, specialist="dev")
    twice = record_context_near_limit_marker(
        run_state=once, specialist="dev"
    )
    assert twice is once


def test_record_context_near_limit_marker_three_distinct_specialists() -> None:
    """AC-3: THREE distinct calls for ``dev`` + ``qa`` + ``review-bmad``
    produce three entries; the FIRST specialist's context wins per the
    documented base-class-keyed marker_contexts convention (see
    architecture.md § Orchestrator-side marker wiring)."""
    rs = _make_run_state()
    out = rs
    for specialist in ("dev", "qa", "review-bmad"):
        out = record_context_near_limit_marker(
            run_state=out, specialist=specialist
        )
    assert set(out.active_markers) == {
        "context-near-limit: dev",
        "context-near-limit: qa",
        "context-near-limit: review-bmad",
    }
    assert len(out.active_markers) == 3
    # FIRST specialist's context wins.
    assert out.marker_contexts == {"context-near-limit": {"specialist": "dev"}}


# --------------------------------------------------------------------------- #
# (d) record_marker_with_context — generic helper / D-6.2-1 discharge         #
# --------------------------------------------------------------------------- #


def test_record_marker_with_context_no_registry_no_validation() -> None:
    """AC-5: the generic helper accepts an optional ``marker_registry``;
    when ``None`` (default) registry validation is skipped and the
    marker is appended unconditionally."""
    rs = _make_run_state()
    out = record_marker_with_context(
        run_state=rs,
        marker_class="Tier-3-not-configured",
        context={"ac_id": "AC-1"},
    )
    assert out.active_markers == ("Tier-3-not-configured",)
    assert out.marker_contexts == {
        "Tier-3-not-configured": {"ac_id": "AC-1"}
    }


def test_record_marker_with_context_with_registry_rejects_unknown() -> None:
    """AC-5: when ``marker_registry`` is supplied, unknown classes raise
    :exc:`UnknownMarkerClass` per Pattern 5."""
    rs = _make_run_state()
    registry = MarkerClassRegistry(marker_classes=frozenset({"specialist-timeout"}))
    with pytest.raises(UnknownMarkerClass):
        record_marker_with_context(
            run_state=rs,
            marker_class="not-a-real-marker-class",
            marker_registry=registry,
        )


def test_record_marker_with_context_with_registry_accepts_known() -> None:
    """AC-5: when ``marker_registry`` is supplied and the class is known,
    the helper proceeds normally."""
    rs = _make_run_state()
    registry = MarkerClassRegistry(
        marker_classes=frozenset({"playwright-mcp-unavailable"})
    )
    out = record_marker_with_context(
        run_state=rs,
        marker_class="playwright-mcp-unavailable",
        context={"project_type": "web", "version_range": ">=0.1,<0.2"},
        marker_registry=registry,
    )
    assert out.active_markers == ("playwright-mcp-unavailable",)
    assert out.marker_contexts == {
        "playwright-mcp-unavailable": {
            "project_type": "web",
            "version_range": ">=0.1,<0.2",
        }
    }


def test_record_marker_with_context_sub_classification_suffix() -> None:
    """AC-5: ``sub_classification`` parameter composes Pattern 2's
    ``: <cause>`` suffix verbatim."""
    rs = _make_run_state()
    out = record_marker_with_context(
        run_state=rs,
        marker_class="hook-failed",
        sub_classification="subagent-stop",
    )
    assert out.active_markers == ("hook-failed: subagent-stop",)


# --------------------------------------------------------------------------- #
# (e) compute_alphabetical_marker_order — render-time normalization / AC-4    #
# --------------------------------------------------------------------------- #


def test_compute_alphabetical_marker_order_empty() -> None:
    """AC-4: empty input → empty output."""
    assert compute_alphabetical_marker_order(()) == ()


def test_compute_alphabetical_marker_order_single_entry() -> None:
    """AC-4: one entry → unchanged single-element tuple."""
    assert compute_alphabetical_marker_order(("specialist-timeout",)) == (
        "specialist-timeout",
    )


def test_compute_alphabetical_marker_order_three_target_classes() -> None:
    """AC-4: input ``("specialist-timeout: timeout-exceeded",
    "context-near-limit: dev", "hook-failed: subagent-stop")`` (non-
    alphabetical input order) → output iterates in alphabetical order:
    ``context-near-limit`` FIRST → ``hook-failed`` SECOND →
    ``specialist-timeout`` THIRD."""
    actual = compute_alphabetical_marker_order(
        (
            "specialist-timeout: timeout-exceeded",
            "context-near-limit: dev",
            "hook-failed: subagent-stop",
        )
    )
    assert actual == (
        "context-near-limit: dev",
        "hook-failed: subagent-stop",
        "specialist-timeout: timeout-exceeded",
    )


def test_compute_alphabetical_marker_order_within_base_class_sub_sort() -> None:
    """AC-4: multiple sub-classifications of the SAME base class
    (e.g., ``hook-failed: stop`` + ``hook-failed: subagent-stop`` +
    ``hook-failed: session-start``) appear in alphabetical sub-class
    order (``session-start`` → ``stop`` → ``subagent-stop``)."""
    actual = compute_alphabetical_marker_order(
        (
            "hook-failed: subagent-stop",
            "hook-failed: stop",
            "hook-failed: session-start",
        )
    )
    assert actual == (
        "hook-failed: session-start",
        "hook-failed: stop",
        "hook-failed: subagent-stop",
    )


def test_compute_alphabetical_marker_order_cross_story_mixed() -> None:
    """AC-4: mixed Story 6.5 / 6.6 / 6.7 markers in a single run sort
    alphabetically across base classes uniformly."""
    actual = compute_alphabetical_marker_order(
        (
            "specialist-timeout: timeout-exceeded",
            "dangling-evidence-ref: qa-evidence",
            "cost-near-ceiling: ceiling-crossed",
            "context-near-limit: dev",
        )
    )
    assert actual == (
        "context-near-limit: dev",
        "cost-near-ceiling: ceiling-crossed",
        "dangling-evidence-ref: qa-evidence",
        "specialist-timeout: timeout-exceeded",
    )


def test_compute_alphabetical_marker_order_idempotent() -> None:
    """AC-4: same input always yields the same output (pure +
    byte-stable)."""
    given = (
        "context-near-limit: qa",
        "hook-failed: stop",
        "specialist-timeout: timeout-exceeded",
    )
    once = compute_alphabetical_marker_order(given)
    twice = compute_alphabetical_marker_order(given)
    assert once == twice


# --------------------------------------------------------------------------- #
# (f) Recorder return-type discipline (frozen RunState; no in-place mutation) #
# --------------------------------------------------------------------------- #


def test_record_specialist_timeout_returns_new_runstate() -> None:
    """AC-1: the recorder returns a NEW :class:`RunState` (frozen
    Pydantic ``model_copy(update=...)``); the input is unchanged."""
    rs = _make_run_state()
    out = record_specialist_timeout_marker(
        run_state=rs, specialist="dev", timeout_seconds=900
    )
    assert out is not rs
    assert rs.active_markers == ()  # input unchanged
    assert out.active_markers != rs.active_markers


def test_record_hook_failure_returns_new_runstate() -> None:
    """AC-2: the recorder returns a NEW :class:`RunState`; the input is
    unchanged."""
    rs = _make_run_state()
    out = record_hook_failure_marker(run_state=rs, hook_name="subagent-stop")
    assert out is not rs
    assert rs.active_markers == ()
    assert out.active_markers != rs.active_markers


def test_record_context_near_limit_returns_new_runstate() -> None:
    """AC-3: the recorder returns a NEW :class:`RunState`; the input is
    unchanged."""
    rs = _make_run_state()
    out = record_context_near_limit_marker(run_state=rs, specialist="dev")
    assert out is not rs
    assert rs.active_markers == ()
    assert out.active_markers != rs.active_markers


# --------------------------------------------------------------------------- #
# Module-shape / public-surface tests                                         #
# --------------------------------------------------------------------------- #


def test_marker_class_constants_match_taxonomy() -> None:
    """AC-1 + AC-2 + AC-3: the three module-level marker-class constants
    are byte-identical to their ``schemas/marker-taxonomy.yaml``
    declarations."""
    assert SPECIALIST_TIMEOUT_MARKER == "specialist-timeout"
    assert HOOK_FAILED_MARKER == "hook-failed"
    assert CONTEXT_NEAR_LIMIT_MARKER == "context-near-limit"


def test_hook_names_alphabetical() -> None:
    """AC-2: ``HOOK_NAMES`` enumerates the three canonical hook-name
    sub-classifications alphabetically (parity with the rendered
    loud-fail block's iteration order via
    :func:`compute_alphabetical_marker_order`)."""
    assert HOOK_NAMES == ("session-start", "stop", "subagent-stop")
    assert list(HOOK_NAMES) == sorted(HOOK_NAMES)


def test_specialist_names_alphabetical() -> None:
    """AC-3: ``SPECIALIST_NAMES`` enumerates the three canonical
    specialist-name sub-classifications alphabetically."""
    assert SPECIALIST_NAMES == ("dev", "qa", "review-bmad")
    assert list(SPECIALIST_NAMES) == sorted(SPECIALIST_NAMES)


def test_marker_wiring_all_enumerates_expected_public_surface() -> None:
    """AC-6 — marker_wiring.__all__ guards public surface against accidental additions or omissions."""
    from loud_fail_harness import marker_wiring
    expected = {
        "CONTEXT_NEAR_LIMIT_MARKER",
        "HOOK_FAILED_MARKER",
        "HOOK_NAMES",
        "HookName",
        "SPECIALIST_NAMES",
        "SPECIALIST_TIMEOUT_MARKER",
        "SpecialistName",
        "SpecialistTimeoutSubCause",
        "compute_alphabetical_marker_order",
        "record_context_near_limit_marker",
        "record_hook_failure_marker",
        "record_marker_with_context",
        "record_specialist_timeout_marker",
    }
    assert set(marker_wiring.__all__) == expected
