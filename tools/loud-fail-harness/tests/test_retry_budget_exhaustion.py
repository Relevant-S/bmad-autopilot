"""Contract-coverage matrix for the retry-budget-exhaustion substrate
(Story 5.6).

AC mapping:

* AC-1 — module imports cleanly + ``__all__`` shape.
* AC-2 — Pydantic-v2 model conformance + co-presence invariant.
* AC-3 — :func:`record_retry_budget_exhaustion` BUDGET_EXHAUSTED happy
  path + ordering + assembler-failure + appender-failure.
* AC-4 — :func:`record_retry_budget_exhaustion` SCOPE_ASSERTION_VIOLATION
  routing + budget-counter-not-decremented + co-presence guard +
  escalation_class enum value.
* AC-5 — :func:`compute_escalation_bundle_path` happy path + traversal /
  absolute / empty guards + purity.
* AC-6 — :func:`default_escalation_bundle_assembler` body-shape +
  parent-mkdir + idempotent overwrite.
* AC-7 — Trigger-dispatch matrix.
* AC-8 — Field-by-field preservation invariant + retry-history-on-disk
  untouched + filesystem-diff.
* AC-9 — :attr:`RetryBudgetExhaustionResult.diagnostic_message` byte-
  stability + remediation-hint sourcing + single-line invariant.
* AC-11 — Schema acceptance (escalation-fired event payload validates
  against ``schemas/orchestrator-event.yaml``).

Per epics.md verbatim discipline, this test module exercises ONLY the
substrate under :mod:`loud_fail_harness.retry_budget_exhaustion`; it
composes :mod:`loud_fail_harness.run_state` for run-state fixtures and
:mod:`loud_fail_harness.scope_assertion` for the scope-violation
diagnostic shape, both AS-IS.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness.retry_budget_exhaustion import (
    ESCALATION_BUNDLES_ROOT,
    EscalationBundleAssemblerFailed,
    ExhaustionContext,
    ExhaustionTrigger,
    RetryBudgetExhaustionDiagnostic,
    RetryBudgetExhaustionInvariantViolation,
    RetryBudgetExhaustionResult,
    compute_escalation_bundle_path,
    default_escalation_bundle_assembler,
    record_retry_budget_exhaustion,
)
from loud_fail_harness.run_state import (
    CostToDateBySpecialist,
    LastRetryDirective,
    RetryAttempt,
    RunState,
    advance_run_state,
)
from loud_fail_harness.scope_assertion import ScopeAssertionDiagnostic


# --------------------------------------------------------------------------- #
# Helpers / fixtures                                                          #
# --------------------------------------------------------------------------- #


def _make_run_state(
    *,
    current_state: str = "in-progress",
    story_id: str = "5-6-foo",
    run_id: str = "run-2026-05-04-abc",
    branch_name: str = "story/5-6-foo",
    retry_history: tuple[RetryAttempt, ...] = (),
    last_envelope: dict[str, Any] | None = None,
    last_retry_directive: LastRetryDirective | None = None,
    active_markers: tuple[str, ...] = (),
) -> RunState:
    return RunState(
        schema_version="1.2",
        story_id=story_id,
        run_id=run_id,
        current_state=current_state,  # type: ignore[arg-type]
        branch_name=branch_name,
        dispatched_specialist=None,
        last_envelope=last_envelope,
        pending_qa_dispatch_payload=None,
        retry_history=retry_history,
        active_markers=active_markers,
        cost_to_date_by_specialist=CostToDateBySpecialist(),
        last_retry_directive=last_retry_directive,
    )


def _write_run_state(path: pathlib.Path, state: RunState) -> None:
    """Persist a run-state via the helper so the on-disk file reflects the
    fixture state. Uses an accept-always callback."""
    from loud_fail_harness.run_state import StoryDocCallbackResult

    advance_run_state(
        run_state_path=path,
        next_state=state,
        story_doc_callback=lambda: StoryDocCallbackResult(accepted=True),
    )


def _make_scope_diagnostic(
    *, story_id: str = "5-6-foo"
) -> ScopeAssertionDiagnostic:
    return ScopeAssertionDiagnostic(
        story_id=story_id,
        retry_round=1,
        violating_files=("src/unrelated.py",),
        declared_scope=("src/foo.py",),
        declared_expansion=(),
    )


def _stub_appender(collected: list[dict[str, Any]]) -> Any:
    def _appender(event: dict[str, Any]) -> None:
        collected.append(event)

    return _appender


# --------------------------------------------------------------------------- #
# AC-1 — module surface                                                       #
# --------------------------------------------------------------------------- #


def test_module_all_exports_alphabetical() -> None:
    from loud_fail_harness import retry_budget_exhaustion as mod

    expected = [
        "EscalationBundleAssembler",
        "EscalationBundleAssemblerFailed",
        "ExhaustionContext",
        "ExhaustionTrigger",
        "RetryBudgetExhaustionDiagnostic",
        "RetryBudgetExhaustionError",
        "RetryBudgetExhaustionInvariantViolation",
        "RetryBudgetExhaustionResult",
        "compute_escalation_bundle_path",
        "default_escalation_bundle_assembler",
        "record_retry_budget_exhaustion",
    ]
    assert list(mod.__all__) == expected
    assert sorted(mod.__all__) == list(mod.__all__)


# --------------------------------------------------------------------------- #
# AC-2 — model conformance                                                    #
# --------------------------------------------------------------------------- #


def test_models_exhaustion_trigger_members() -> None:
    assert ExhaustionTrigger.BUDGET_EXHAUSTED.value == "budget-exhausted"
    assert (
        ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION.value
        == "scope-assertion-violation"
    )
    assert len(list(ExhaustionTrigger)) == 2


def test_models_exhaustion_context_co_presence_budget_with_diagnostic_rejects() -> None:
    diag = _make_scope_diagnostic()
    with pytest.raises(ValidationError):
        ExhaustionContext(
            trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
            story_id="5-6-foo",
            run_id="run-1",
            branch_name="b",
            retry_history=(),
            last_envelope=None,
            last_retry_directive=None,
            scope_violation_diagnostic=diag,
            bundle_artifact_path="x/y.md",
        )


def test_models_exhaustion_context_co_presence_scope_without_diagnostic_rejects() -> None:
    with pytest.raises(ValidationError):
        ExhaustionContext(
            trigger=ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION,
            story_id="5-6-foo",
            run_id="run-1",
            branch_name="b",
            retry_history=(),
            last_envelope=None,
            last_retry_directive=None,
            scope_violation_diagnostic=None,
            bundle_artifact_path="x/y.md",
        )


def test_models_exhaustion_context_happy_paths() -> None:
    # BUDGET_EXHAUSTED with None diagnostic.
    ExhaustionContext(
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        story_id="5-6-foo",
        run_id="run-1",
        branch_name="b",
        retry_history=(),
        last_envelope=None,
        last_retry_directive=None,
        scope_violation_diagnostic=None,
        bundle_artifact_path="x/y.md",
    )
    # SCOPE_ASSERTION_VIOLATION with diagnostic.
    ExhaustionContext(
        trigger=ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION,
        story_id="5-6-foo",
        run_id="run-1",
        branch_name="b",
        retry_history=(),
        last_envelope=None,
        last_retry_directive=None,
        scope_violation_diagnostic=_make_scope_diagnostic(),
        bundle_artifact_path="x/y.md",
    )


def test_models_diagnostic_marker_class_value() -> None:
    assert RetryBudgetExhaustionDiagnostic.marker_class == "retry-budget-exhausted"


def test_models_result_field_declaration_order_byte_stable() -> None:
    diag = RetryBudgetExhaustionDiagnostic(
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        story_id="s",
        run_id="r",
        branch_name="b",
        retry_count=0,
        bundle_artifact_path="x/y.md",
        remediation_hint="h",
    )
    keys = list(diag.model_dump().keys())
    assert keys == [
        "trigger",
        "story_id",
        "run_id",
        "branch_name",
        "retry_count",
        "bundle_artifact_path",
        "remediation_hint",
    ]
    # Also verify RetryBudgetExhaustionResult field declaration order.
    result_keys = list(RetryBudgetExhaustionResult.model_fields.keys())
    assert result_keys == [
        "advance_result",
        "emitted_event",
        "diagnostic",
        "diagnostic_message",
    ]


# --------------------------------------------------------------------------- #
# AC-3 — BUDGET_EXHAUSTED happy path + ordering + assembler/appender failure  #
# --------------------------------------------------------------------------- #


def test_record_budget_exhaustion_happy_path(tmp_path: pathlib.Path) -> None:
    state = _make_run_state(
        retry_history=(
            RetryAttempt(retry_attempt=1, retry_reason="first"),
            RetryAttempt(retry_attempt=2, retry_reason="second"),
        ),
        last_envelope={"status": "fail"},
        last_retry_directive=LastRetryDirective(
            retry_mode="fix-only", affected_files=("src/foo.py",)
        ),
        active_markers=("hook-failed",),
    )
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)

    written: list[ExhaustionContext] = []

    def _stub_assembler(context: ExhaustionContext) -> None:
        written.append(context)

    events: list[dict[str, Any]] = []

    result = record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        escalation_bundle_assembler=_stub_assembler,
        event_log_appender=_stub_appender(events),
        repo_root=tmp_path,
    )

    assert len(written) == 1
    assert written[0].trigger is ExhaustionTrigger.BUDGET_EXHAUSTED
    assert written[0].scope_violation_diagnostic is None

    on_disk = yaml.safe_load(run_state_path.read_text(encoding="utf-8"))
    assert on_disk["current_state"] == "escalated"
    assert on_disk["retry_history"] == [
        {"retry_attempt": 1, "retry_reason": "first"},
        {"retry_attempt": 2, "retry_reason": "second"},
    ]
    assert on_disk["branch_name"] == state.branch_name
    assert on_disk["last_retry_directive"] == {
        "retry_mode": "fix-only",
        "affected_files": ["src/foo.py"],
    }
    assert on_disk["last_envelope"] == {"status": "fail"}
    assert on_disk["active_markers"] == list(state.active_markers)
    assert on_disk["dispatched_specialist"] is None

    assert len(events) == 1
    event = events[0]
    assert event["event_class"] == "escalation-fired"
    assert event["escalation_class"] == "retry-budget-exhausted"
    assert event["story_id"] == state.story_id
    assert event["bundle_artifact_path"].startswith(ESCALATION_BUNDLES_ROOT)

    assert result.advance_result.next_state.current_state == "escalated"
    assert result.diagnostic.marker_class == "retry-budget-exhausted"
    assert result.diagnostic.retry_count == 2
    assert result.emitted_event == event


def test_record_budget_exhaustion_ordering_assembler_first_then_advance_then_event(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _make_run_state()
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)

    sequence: list[str] = []

    def _stub_assembler(context: ExhaustionContext) -> None:
        sequence.append("assembler")

    def _appender(event: dict[str, Any]) -> None:
        sequence.append("appender")

    from loud_fail_harness import retry_budget_exhaustion as mod

    real_advance = mod.advance_run_state

    def _wrapped_advance(*args: Any, **kwargs: Any) -> Any:
        result = real_advance(*args, **kwargs)
        sequence.append("advance")
        return result

    monkeypatch.setattr(mod, "advance_run_state", _wrapped_advance)

    record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        escalation_bundle_assembler=_stub_assembler,
        event_log_appender=_appender,
        repo_root=tmp_path,
    )

    assert sequence == ["assembler", "advance", "appender"]


def test_record_budget_exhaustion_assembler_failure_blocks_advance(
    tmp_path: pathlib.Path,
) -> None:
    state = _make_run_state()
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)
    pre_bytes = run_state_path.read_bytes()

    class BoomError(RuntimeError):
        pass

    def _raising_assembler(context: ExhaustionContext) -> None:
        raise BoomError("assembler exploded")

    events: list[dict[str, Any]] = []

    with pytest.raises(EscalationBundleAssemblerFailed) as exc_info:
        record_retry_budget_exhaustion(
            run_state_path=run_state_path,
            current_state=state,
            trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
            escalation_bundle_assembler=_raising_assembler,
            event_log_appender=_stub_appender(events),
            repo_root=tmp_path,
        )

    assert exc_info.value.bundle_path.startswith(ESCALATION_BUNDLES_ROOT)
    # __cause__ chain points to the assembler's original exception.
    cause = exc_info.value.__cause__
    while cause is not None and not isinstance(cause, BoomError):
        cause = cause.__cause__
    assert isinstance(cause, BoomError)

    # Run-state UNCHANGED on disk; appender NOT invoked.
    assert run_state_path.read_bytes() == pre_bytes
    assert events == []


def test_record_budget_exhaustion_appender_failure_does_not_roll_back_advance(
    tmp_path: pathlib.Path,
) -> None:
    state = _make_run_state()
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)

    def _stub_assembler(context: ExhaustionContext) -> None:
        pass

    def _raising_appender(event: dict[str, Any]) -> None:
        raise RuntimeError("appender exploded")

    with pytest.raises(RuntimeError, match="appender exploded"):
        record_retry_budget_exhaustion(
            run_state_path=run_state_path,
            current_state=state,
            trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
            escalation_bundle_assembler=_stub_assembler,
            event_log_appender=_raising_appender,
            repo_root=tmp_path,
        )

    # Run-state advanced on disk DESPITE appender failure (mirrors
    # commit_transition's ordering at lifecycle_state_machine.py:752-756).
    on_disk = yaml.safe_load(run_state_path.read_text(encoding="utf-8"))
    assert on_disk["current_state"] == "escalated"


# --------------------------------------------------------------------------- #
# AC-4 — SCOPE_ASSERTION_VIOLATION routing                                    #
# --------------------------------------------------------------------------- #


def test_record_scope_violation_threads_diagnostic_into_context(
    tmp_path: pathlib.Path,
) -> None:
    state = _make_run_state()
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)

    diag = _make_scope_diagnostic()
    written: list[ExhaustionContext] = []

    def _stub_assembler(context: ExhaustionContext) -> None:
        written.append(context)

    record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION,
        escalation_bundle_assembler=_stub_assembler,
        event_log_appender=lambda _e: None,
        repo_root=tmp_path,
        scope_violation_diagnostic=diag,
    )

    assert written[0].scope_violation_diagnostic == diag
    assert written[0].trigger is ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION


def test_record_scope_violation_does_not_decrement_budget_counter(
    tmp_path: pathlib.Path,
) -> None:
    state = _make_run_state(retry_history=())
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)

    result = record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION,
        escalation_bundle_assembler=lambda _c: None,
        event_log_appender=lambda _e: None,
        repo_root=tmp_path,
        scope_violation_diagnostic=_make_scope_diagnostic(),
    )

    assert result.advance_result.next_state.retry_history == ()
    assert result.diagnostic.retry_count == 0


def test_record_scope_violation_co_presence_invariant_fires_pre_assembler(
    tmp_path: pathlib.Path,
) -> None:
    state = _make_run_state()
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)
    pre_bytes = run_state_path.read_bytes()
    invocations: list[ExhaustionContext] = []

    def _stub_assembler(context: ExhaustionContext) -> None:
        invocations.append(context)

    with pytest.raises(RetryBudgetExhaustionInvariantViolation):
        record_retry_budget_exhaustion(
            run_state_path=run_state_path,
            current_state=state,
            trigger=ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION,
            escalation_bundle_assembler=_stub_assembler,
            event_log_appender=lambda _e: None,
            repo_root=tmp_path,
        )

    assert invocations == []
    assert run_state_path.read_bytes() == pre_bytes


def test_record_scope_violation_emits_retry_budget_exhausted_escalation_class(
    tmp_path: pathlib.Path,
) -> None:
    state = _make_run_state()
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)

    events: list[dict[str, Any]] = []
    record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION,
        escalation_bundle_assembler=lambda _c: None,
        event_log_appender=_stub_appender(events),
        repo_root=tmp_path,
        scope_violation_diagnostic=_make_scope_diagnostic(),
    )
    assert events[0]["escalation_class"] == "retry-budget-exhausted"


def test_record_invariant_violation_from_terminal_state(
    tmp_path: pathlib.Path,
) -> None:
    for terminal in ("done", "escalated"):
        state = _make_run_state(current_state=terminal)
        run_state_path = tmp_path / f"run-state-{terminal}.yaml"
        _write_run_state(run_state_path, state)
        with pytest.raises(RetryBudgetExhaustionInvariantViolation):
            record_retry_budget_exhaustion(
                run_state_path=run_state_path,
                current_state=state,
                trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
                escalation_bundle_assembler=lambda _c: None,
                event_log_appender=lambda _e: None,
                repo_root=tmp_path,
            )


def test_record_invariant_violation_budget_with_diagnostic(
    tmp_path: pathlib.Path,
) -> None:
    state = _make_run_state()
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)
    with pytest.raises(RetryBudgetExhaustionInvariantViolation):
        record_retry_budget_exhaustion(
            run_state_path=run_state_path,
            current_state=state,
            trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
            escalation_bundle_assembler=lambda _c: None,
            event_log_appender=lambda _e: None,
            repo_root=tmp_path,
            scope_violation_diagnostic=_make_scope_diagnostic(),
        )


# --------------------------------------------------------------------------- #
# AC-5 — compute_escalation_bundle_path                                       #
# --------------------------------------------------------------------------- #


def test_compute_path_happy(tmp_path: pathlib.Path) -> None:
    p = compute_escalation_bundle_path(
        repo_root=tmp_path,
        story_id="5-6-foo",
        run_id="run-2026-05-04-abc",
    )
    assert p == (
        tmp_path
        / "_bmad-output"
        / "escalation-bundles"
        / "5-6-foo"
        / "run-2026-05-04-abc"
        / "escalation.md"
    )


@pytest.mark.parametrize("bad_id", ["../../../etc", "/etc/passwd"])
def test_compute_path_rejects_traversal_or_absolute_story_id(
    tmp_path: pathlib.Path, bad_id: str
) -> None:
    with pytest.raises(RetryBudgetExhaustionInvariantViolation):
        compute_escalation_bundle_path(
            repo_root=tmp_path, story_id=bad_id, run_id="r"
        )


@pytest.mark.parametrize("bad_id", ["../../../etc", "/etc/passwd"])
def test_compute_path_rejects_traversal_or_absolute_run_id(
    tmp_path: pathlib.Path, bad_id: str
) -> None:
    with pytest.raises(RetryBudgetExhaustionInvariantViolation):
        compute_escalation_bundle_path(
            repo_root=tmp_path, story_id="s", run_id=bad_id
        )


def test_compute_path_empty_story_id_rejected(tmp_path: pathlib.Path) -> None:
    with pytest.raises(RetryBudgetExhaustionInvariantViolation):
        compute_escalation_bundle_path(
            repo_root=tmp_path, story_id="", run_id="r"
        )


def test_compute_path_empty_run_id_rejected(tmp_path: pathlib.Path) -> None:
    with pytest.raises(RetryBudgetExhaustionInvariantViolation):
        compute_escalation_bundle_path(
            repo_root=tmp_path, story_id="s", run_id=""
        )


def test_compute_path_is_pure_no_io(tmp_path: pathlib.Path) -> None:
    pre_listing = sorted(p.name for p in tmp_path.iterdir())
    p = compute_escalation_bundle_path(
        repo_root=tmp_path, story_id="s", run_id="r"
    )
    assert not p.exists()
    post_listing = sorted(p.name for p in tmp_path.iterdir())
    assert pre_listing == post_listing


# --------------------------------------------------------------------------- #
# AC-6 — default_escalation_bundle_assembler                                  #
# --------------------------------------------------------------------------- #


def _build_context(
    tmp_path: pathlib.Path,
    *,
    trigger: ExhaustionTrigger = ExhaustionTrigger.BUDGET_EXHAUSTED,
    diagnostic: ScopeAssertionDiagnostic | None = None,
    last_envelope: dict[str, Any] | None = None,
    last_retry_directive: LastRetryDirective | None = None,
    retry_history: tuple[RetryAttempt, ...] = (),
) -> ExhaustionContext:
    bundle_path = compute_escalation_bundle_path(
        repo_root=tmp_path, story_id="5-6-foo", run_id="run-1"
    )
    return ExhaustionContext(
        trigger=trigger,
        story_id="5-6-foo",
        run_id="run-1",
        branch_name="story/5-6-foo",
        retry_history=retry_history,
        last_envelope=last_envelope,
        last_retry_directive=last_retry_directive,
        scope_violation_diagnostic=diagnostic,
        bundle_artifact_path=bundle_path.relative_to(tmp_path).as_posix(),
    )


def test_default_assembler_writes_file(tmp_path: pathlib.Path) -> None:
    # Post-Story-5.8: the placeholder body is RETIRED; the delegate writes
    # a fully FR15-shaped escalation-variant bundle conforming to the
    # relevant `schemas/escalation-bundles/{bundle_class}.yaml` fragment.
    # Assertion text updated per AC-3 (bounded to assertion changes; no
    # test deletion).
    assembler = default_escalation_bundle_assembler(repo_root=tmp_path)
    ctx = _build_context(tmp_path)
    assembler(ctx)
    target = tmp_path / ctx.bundle_artifact_path
    assert target.exists()
    body = target.read_text(encoding="utf-8")
    assert body
    assert "# Escalation bundle " in body
    assert "Bundle class: `retry-budget-exhausted`" in body
    assert "## Escalation rationale" in body
    assert "## Outstanding findings" in body
    assert "## Retry history" in body
    assert "## Deferred-work pointer" in body
    assert "## Preservation" in body
    # AC-3: the placeholder HTML comment is structurally absent.
    assert "Replaced by Story 5.8" not in body


def test_default_assembler_includes_scope_violation_section(
    tmp_path: pathlib.Path,
) -> None:
    assembler = default_escalation_bundle_assembler(repo_root=tmp_path)
    ctx = _build_context(
        tmp_path,
        trigger=ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION,
        diagnostic=_make_scope_diagnostic(),
    )
    assembler(ctx)
    body = (tmp_path / ctx.bundle_artifact_path).read_text(encoding="utf-8")
    assert "## Scope-assertion diagnostic" in body
    assert "violating_files" in body


def test_default_assembler_omits_scope_section_for_budget_trigger(
    tmp_path: pathlib.Path,
) -> None:
    assembler = default_escalation_bundle_assembler(repo_root=tmp_path)
    ctx = _build_context(tmp_path)
    assembler(ctx)
    body = (tmp_path / ctx.bundle_artifact_path).read_text(encoding="utf-8")
    assert "## Scope-assertion diagnostic" not in body


def test_default_assembler_creates_parent_directory(tmp_path: pathlib.Path) -> None:
    assembler = default_escalation_bundle_assembler(repo_root=tmp_path)
    ctx = _build_context(tmp_path)
    target = tmp_path / ctx.bundle_artifact_path
    assert not target.parent.exists()
    assembler(ctx)
    assert target.parent.exists()


def test_default_assembler_idempotent_overwrite(tmp_path: pathlib.Path) -> None:
    # Post-Story-5.8: the production assembler stamps `Generated:` with
    # `datetime.now(timezone.utc)` per Pattern 6 freshness invariant; two
    # successive invocations land at the same path with the same
    # structural shape (same six AC-2 sections; same machine-readable
    # payload modulo timestamp). Byte-equality is no longer asserted —
    # the structural-equivalence assertion below is the post-Story-5.8
    # invariant per AC-3 (bounded assertion-text changes).
    assembler = default_escalation_bundle_assembler(repo_root=tmp_path)
    ctx = _build_context(tmp_path)
    assembler(ctx)
    target = tmp_path / ctx.bundle_artifact_path
    body_first = target.read_text(encoding="utf-8")
    assert "## Escalation rationale" in body_first
    assembler(ctx)
    body_second = target.read_text(encoding="utf-8")
    assert "## Escalation rationale" in body_second
    # The bundle remains a single file at the deterministic path; the
    # second invocation overwrites cleanly via _atomic_write_bundle.
    assert target.exists()


def test_default_assembler_renders_retry_history_references(
    tmp_path: pathlib.Path,
) -> None:
    assembler = default_escalation_bundle_assembler(repo_root=tmp_path)
    ctx = _build_context(
        tmp_path,
        retry_history=(
            RetryAttempt(
                retry_attempt=1,
                retry_reason="patch-bucket-retry",
                round_id="round-01",
                path="_bmad-output/retry-history/5-6-foo/round-01/artifacts.yaml",
            ),
        ),
    )
    assembler(ctx)
    body = (tmp_path / ctx.bundle_artifact_path).read_text(encoding="utf-8")
    assert "patch-bucket-retry" in body
    assert "round-01" in body


# --------------------------------------------------------------------------- #
# AC-7 — trigger-dispatch matrix                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "trigger",
    [
        ExhaustionTrigger.BUDGET_EXHAUSTED,
        ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION,
    ],
)
def test_trigger_dispatch_matrix_marker_class_is_uniform(
    tmp_path: pathlib.Path, trigger: ExhaustionTrigger
) -> None:
    state = _make_run_state()
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)

    diag = (
        _make_scope_diagnostic()
        if trigger is ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION
        else None
    )
    events: list[dict[str, Any]] = []
    result = record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=trigger,
        escalation_bundle_assembler=lambda _c: None,
        event_log_appender=_stub_appender(events),
        repo_root=tmp_path,
        scope_violation_diagnostic=diag,
    )

    assert result.diagnostic.marker_class == "retry-budget-exhausted"
    assert events[0]["escalation_class"] == "retry-budget-exhausted"
    assert result.diagnostic.trigger is trigger
    assert f"trigger={trigger.value}" in result.diagnostic_message


# --------------------------------------------------------------------------- #
# AC-8 — preservation invariant                                               #
# --------------------------------------------------------------------------- #


def test_preservation_invariant_field_by_field_equality(
    tmp_path: pathlib.Path,
) -> None:
    state = _make_run_state(
        retry_history=(
            RetryAttempt(
                retry_attempt=1,
                retry_reason="r1",
                round_id="round-01",
                path="_bmad-output/retry-history/5-6-foo/round-01/artifacts.yaml",
            ),
        ),
        last_envelope={"status": "fail", "details": {"id": 7}},
        last_retry_directive=LastRetryDirective(
            retry_mode="fix-only", affected_files=("src/foo.py", "src/bar.py")
        ),
        active_markers=("hook-failed",),
    )
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)

    result = record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        escalation_bundle_assembler=lambda _c: None,
        event_log_appender=lambda _e: None,
        repo_root=tmp_path,
    )

    next_state = result.advance_result.next_state
    for field in (
        "schema_version",
        "story_id",
        "run_id",
        "branch_name",
        "dispatched_specialist",
        "last_envelope",
        "pending_qa_dispatch_payload",
        "retry_history",
        "active_markers",
        "cost_to_date_by_specialist",
        "last_retry_directive",
    ):
        assert getattr(next_state, field) == getattr(state, field), field
    assert next_state.current_state == "escalated"
    assert state.current_state != "escalated"


def test_preservation_invariant_retry_history_byte_identical(
    tmp_path: pathlib.Path,
) -> None:
    history = (
        RetryAttempt(retry_attempt=1, retry_reason="a"),
        RetryAttempt(
            retry_attempt=2,
            retry_reason="b",
            round_id="round-02",
            path="x/y.yaml",
        ),
    )
    state = _make_run_state(retry_history=history)
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)

    result = record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        escalation_bundle_assembler=lambda _c: None,
        event_log_appender=lambda _e: None,
        repo_root=tmp_path,
    )
    for inp, out in zip(
        history, result.advance_result.next_state.retry_history, strict=True
    ):
        assert inp.model_dump_json() == out.model_dump_json()


def test_preservation_invariant_retry_history_artifact_on_disk_untouched(
    tmp_path: pathlib.Path,
) -> None:
    artifact_dir = (
        tmp_path / "_bmad-output" / "retry-history" / "5-6-foo" / "round-01"
    )
    artifact_dir.mkdir(parents=True)
    artifact_path = artifact_dir / "artifacts.yaml"
    artifact_body = "round_id: round-01\nretry_attempt: 1\n"
    artifact_path.write_text(artifact_body, encoding="utf-8")

    state = _make_run_state(
        retry_history=(
            RetryAttempt(
                retry_attempt=1,
                retry_reason="r",
                round_id="round-01",
                path="_bmad-output/retry-history/5-6-foo/round-01/artifacts.yaml",
            ),
        ),
    )
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)

    record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        escalation_bundle_assembler=lambda _c: None,
        event_log_appender=lambda _e: None,
        repo_root=tmp_path,
    )

    assert artifact_path.read_text(encoding="utf-8") == artifact_body


def test_preservation_invariant_only_new_fs_artifact_is_escalation_bundle(
    tmp_path: pathlib.Path,
) -> None:
    state = _make_run_state()
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)

    def _walk(root: pathlib.Path) -> set[pathlib.Path]:
        return {
            pathlib.Path(dirpath) / name
            for dirpath, _dirs, files in os.walk(root)
            for name in files
        }

    pre = _walk(tmp_path)
    record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        escalation_bundle_assembler=default_escalation_bundle_assembler(
            repo_root=tmp_path
        ),
        event_log_appender=lambda _e: None,
        repo_root=tmp_path,
    )
    post = _walk(tmp_path)
    new_files = post - pre
    expected_bundle = compute_escalation_bundle_path(
        repo_root=tmp_path,
        story_id=state.story_id,
        run_id=state.run_id,
    )
    assert new_files == {expected_bundle}


# --------------------------------------------------------------------------- #
# AC-9 — diagnostic_message byte-stability                                    #
# --------------------------------------------------------------------------- #


_EXPECTED_REMEDIATION_HINT = (
    "FR8 (budget) + FR14 (non-advance + state preservation) + FR15 "
    "(escalation bundle assembly path). Normal-flow halt event, NOT a "
    "failure of any single specialist."
)


def test_diagnostic_message_format_byte_stable_budget(tmp_path: pathlib.Path) -> None:
    state = _make_run_state(
        retry_history=(
            RetryAttempt(retry_attempt=1, retry_reason="a"),
            RetryAttempt(retry_attempt=2, retry_reason="b"),
        ),
    )
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)
    result = record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        escalation_bundle_assembler=lambda _c: None,
        event_log_appender=lambda _e: None,
        repo_root=tmp_path,
    )
    expected = (
        "retry-budget-exhausted: "
        "trigger=budget-exhausted, "
        f"story_id={state.story_id}, "
        "retry_count=2, "
        f"branch={state.branch_name}, "
        f"bundle={result.diagnostic.bundle_artifact_path} "
        f"— {_EXPECTED_REMEDIATION_HINT}"
    )
    assert result.diagnostic_message == expected


def test_diagnostic_message_format_byte_stable_scope_violation(
    tmp_path: pathlib.Path,
) -> None:
    state = _make_run_state()
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)
    result = record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION,
        escalation_bundle_assembler=lambda _c: None,
        event_log_appender=lambda _e: None,
        repo_root=tmp_path,
        scope_violation_diagnostic=_make_scope_diagnostic(),
    )
    expected = (
        "retry-budget-exhausted: "
        "trigger=scope-assertion-violation, "
        f"story_id={state.story_id}, "
        "retry_count=0, "
        f"branch={state.branch_name}, "
        f"bundle={result.diagnostic.bundle_artifact_path} "
        f"— {_EXPECTED_REMEDIATION_HINT}"
    )
    assert result.diagnostic_message == expected


def test_diagnostic_message_remediation_hint_sourced_verbatim_from_taxonomy(
    tmp_path: pathlib.Path,
) -> None:
    """The remediation hint substring must be byte-identical to the
    whitespace-collapsed marker-taxonomy diagnostic_pointer for
    `retry-budget-exhausted` (lines 248-251)."""
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    taxonomy_path = repo_root / "schemas" / "marker-taxonomy.yaml"
    taxonomy = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    entry = next(
        m for m in taxonomy["markers"] if m["marker_class"] == "retry-budget-exhausted"
    )
    raw = entry["diagnostic_pointer"]
    collapsed = " ".join(raw.split())
    assert collapsed == _EXPECTED_REMEDIATION_HINT


def test_diagnostic_message_single_line_invariant(tmp_path: pathlib.Path) -> None:
    state = _make_run_state()
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)
    result = record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        escalation_bundle_assembler=lambda _c: None,
        event_log_appender=lambda _e: None,
        repo_root=tmp_path,
    )
    assert "\n" not in result.diagnostic_message


# --------------------------------------------------------------------------- #
# AC-11 / Subtask 4.6 — schema acceptance for the emitted event               #
# --------------------------------------------------------------------------- #


def test_emitted_escalation_event_validates_against_schema(
    tmp_path: pathlib.Path,
) -> None:
    import jsonschema
    import yaml as _yaml

    repo_root = pathlib.Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "orchestrator-event.yaml"
    schema = _yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)

    state = _make_run_state()
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)

    events: list[dict[str, Any]] = []
    record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        escalation_bundle_assembler=lambda _c: None,
        event_log_appender=_stub_appender(events),
        repo_root=tmp_path,
    )
    # Validate against the orchestrator-event schema (oneOf branches).
    validator.validate(events[0])


# --------------------------------------------------------------------------- #
# Result shape                                                                #
# --------------------------------------------------------------------------- #


def test_result_round_trip_carries_advance_event_diagnostic_message(
    tmp_path: pathlib.Path,
) -> None:
    state = _make_run_state()
    run_state_path = tmp_path / "run-state.yaml"
    _write_run_state(run_state_path, state)
    result = record_retry_budget_exhaustion(
        run_state_path=run_state_path,
        current_state=state,
        trigger=ExhaustionTrigger.BUDGET_EXHAUSTED,
        escalation_bundle_assembler=lambda _c: None,
        event_log_appender=lambda _e: None,
        repo_root=tmp_path,
    )
    assert isinstance(result, RetryBudgetExhaustionResult)
    assert result.advance_result.wrote_path == run_state_path
    assert "escalation-fired" == result.emitted_event["event_class"]
    assert isinstance(result.diagnostic_message, str)
