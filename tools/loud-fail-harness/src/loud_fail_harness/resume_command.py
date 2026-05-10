"""``/bmad-automation resume <story-id>`` substrate library — Story 8.3.

## Substrate-component identity

THIS module is a substrate **library** sibling of
:mod:`loud_fail_harness.session_start_reattach` (Story 8.1),
:mod:`loud_fail_harness.cross_state_recovery` (Story 8.2),
:mod:`loud_fail_harness.init_non_destructive_guard` (Story 7.6),
:mod:`loud_fail_harness.tea_boundary_orientation` (Story 7.8), and
:mod:`loud_fail_harness.story_doc_version_check` (Story 7.7). It is **NOT a
sixth substrate component** beyond ADR-003 Consequence 1's enumerated five
(``envelope_validator``, ``event_validator``, ``reconciler``,
``enumeration_check``, ``fixture_coverage``); the count remains FIVE through
Epic 8 per the Epic 7 retro framing
(``epic-7-retro-2026-05-08.md`` line 122) and Story 8.2's Completion Notes
("Substrate-component count holds at FIVE").

The module is the THIRD Epic-8 runtime-code introduction (after Story 8.1's
SessionStart reattachment substrate AND Story 8.2's cross-state recovery
algorithm). Consumers:

* The orchestrator skill at ``/bmad-automation resume <story-id>`` time
  (the explicit-reattach path; consumes the algorithm against a
  practitioner-named story-id). The skill prose lives at
  ``skills/bmad-automation/steps/resume.md``; THIS module is invoked as the
  ``bmad-automation-resume`` CLI.

This module is the FIRST production-call site of
:func:`cross_state_recovery.evaluate_recovery` (closing the
schedule-vs-actually-called gap from Story 8.2 AC-11; the 8.1 thread-through
remains forward-scoped beyond MVP).

## Architectural anchors

- **FR47** (PRD line 881) — "Practitioner can run ``/bmad-automation resume
  [story-id]`` to explicitly reattach to a suspended or crashed run." THIS
  substrate IS the implementation.
- **NFR-R7** (PRD line 951) — "No destructive resume — on resume,
  orchestrator does not re-dispatch specialists whose prior output was
  recorded." Consumed via
  :func:`no_destructive_resume_guard.can_dispatch` — the canonical
  substrate guard (Story 8.6) — invoked on the dispatch path before
  the orchestrator skill threads through to ``steps/dispatch.md``. The
  Story 8.6 CI lint at :mod:`no_destructive_resume_lint` asserts
  Stories 8.1 / 8.2 / 8.3 ALL route dispatch decisions through it.
- **NFR-R8** (PRD line 952) — "Cross-state consistency" — delegated to
  :func:`cross_state_recovery.evaluate_recovery` for the actual recovery
  decision; THIS substrate consumes the verdict.
- **NFR-R2** (PRD line 946) — "Crash recovery without duplicate state
  advance."
- **ADR-005** (architecture.md lines 429-541) — cross-state consistency
  protocol; THIS substrate's ``ResumeOutcome.recovery_outcome`` field
  carries the Reading-3 verdict.
- **ADR-003 Consequence 1** (architecture.md lines 311-315) — substrate-
  component count closure at FIVE (this module is a substrate-library
  sibling, NOT a sixth component).

## The four ``ResumeOutcome.action`` branches

* ``resume-dispatch`` — recovery succeeded (``recovery-clean`` OR
  ``recovery-rebuilt``); ``final_run_state.current_state`` is non-terminal;
  ``next_specialist`` is populated per the AC-4 closed map; the orchestrator
  skill's ``steps/resume.md`` threads through to ``steps/dispatch.md`` to
  invoke ``Task(<next_specialist-wrapper>)``.
* ``resume-already-terminal`` — recovery succeeded; ``current_state`` is in
  :data:`lifecycle_state_machine.TERMINAL_STATES` (``done`` or
  ``escalated``); no dispatch needed; the practitioner is informed the
  story is terminal.
* ``resume-conflict-halt`` — recovery returned ``recovery-conflict-halt``;
  the ``recovery-state-conflict`` marker IS in
  ``final_run_state.active_markers`` (8.2's emission per its AC-7); THIS
  substrate halts and surfaces 8.2's diagnostic verbatim. NO marker is
  re-emitted at THIS surface (consumer, not emitter).
* ``resume-no-run-state`` — pre-check found NO run-state file at the
  resolved path BEFORE invoking ``evaluate_recovery``; halts with a named-
  invariant diagnostic ``no-in-flight-run-found-for-story-id``; NO marker
  emitted (per ``epics.md:3288`` verbatim — "halts with a named-invariant
  diagnostic"). Distinct from Story 8.2's ``no-run-state-on-disk``
  ``recovery-state-conflict`` sub-case (which is reserved for the
  8.1-reattachment context per Story 8.2's Dev's-call documentation).

## No-destructive-resume invariant

The substrate is read-only against story-doc, sprint-status, and the git
working tree. The only state-mutation is the rebuild-path's run-state write
which is delegated to :func:`cross_state_recovery.evaluate_recovery` via
its ``run_state_writer`` DI seam. THIS substrate does NOT directly write
run-state, story-doc, sprint-status, or events.

The dispatch-eligibility check is delegated to the canonical Story 8.6
substrate :func:`no_destructive_resume_guard.can_dispatch`. When the
canonical guard returns a deny verdict on a path that 8.2's
``evaluate_recovery`` cleared as recoverable,
:class:`CanDispatchInvariantViolation` is raised — a substrate-bug
indicator at 8.2's level. The exception's ``reason`` and ``diagnostic``
fields are sourced from the :class:`Verdict` so downstream consumers
can route on the structured ``DenyReason`` enum.

## Sensor-not-advisor

Per ADR-001 + Pattern 5, this substrate produces a directive
(:class:`ResumeOutcome`); the orchestrator skill's ``steps/resume.md``
runtime protocol parses the directive and threads through to
``steps/dispatch.md``'s LLM-runtime dispatch protocol on
``resume-dispatch``. THIS substrate does NOT invoke the Task tool, does
NOT emit orchestrator events, does NOT advance lifecycle state outside
what ``evaluate_recovery``'s rebuild path does.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .cross_state_recovery import (
    RUN_STATE_RELATIVE_PATH,
    CrossStateRecoveryError,
    RecoveryOutcome,
    RecoveryRequest,
    RunStateWriter,
    _load_run_state_from_disk,
    evaluate_recovery,
)
from .lifecycle_state_machine import LIFECYCLE_TRANSITIONS, TERMINAL_STATES
from .no_destructive_resume_guard import Verdict, can_dispatch
from .orchestrator_run_entry import SprintStatusResolver, StoryDocResolver
from .run_state import CurrentState, RunState

if TYPE_CHECKING:
    from .specialist_dispatch import MarkerClassRegistry

__all__ = [
    "CanDispatchInvariantViolation",
    "ResumeCommandError",
    "ResumeOutcome",
    "ResumeRequest",
    "determine_next_specialist",
    "evaluate_resume",
    "main",
    "render_no_run_state_diagnostic",
]

_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Module-level constants                                                       #
# --------------------------------------------------------------------------- #


#: Closed lifecycle-state-to-specialist map per AC-4. Keys MUST equal
#: ``LIFECYCLE_TRANSITIONS.keys() | TERMINAL_STATES`` — the structural
#: equality is asserted by the AC-9 test
#: ``test_next_specialist_map_keys_equal_lifecycle_union`` so adding a new
#: lifecycle state without updating this map fails the test loud (mirrors
#: Story 2.4's lifecycle-extension protocol).
#:
#: Mapping rationale per the AC-4 table:
#:   * ``ready-for-dev → "dev"`` — dev is the first specialist; resume
#:     re-enters at the dev-dispatch boundary.
#:   * ``in-progress → "review-bmad"`` — dev has run; review is next.
#:   * ``review → "qa"`` — review has run; QA is next.
#:   * ``qa → "qa"`` — QA is in-flight (dispatched but not advanced);
#:     resume re-dispatches QA. The QA wrapper's own retry-routing per
#:     Story 5.2 covers internal retries; resume re-enters at the
#:     QA-dispatch boundary.
#:   * ``done → None`` — terminal; no dispatch needed.
#:   * ``escalated → None`` — terminal; no dispatch needed.
_NEXT_SPECIALIST_BY_STATE: Final[
    dict[CurrentState, Literal["dev", "review-bmad", "qa"] | None]
] = {
    "ready-for-dev": "dev",
    "in-progress": "review-bmad",
    "review": "qa",
    "qa": "qa",
    "done": None,
    "escalated": None,
}

#: Module-import-time structural-equality invariant per AC-4. Adding a
#: new lifecycle state to ``LIFECYCLE_TRANSITIONS`` without updating
#: ``_NEXT_SPECIALIST_BY_STATE`` fails THIS assertion at import time
#: (mirrors Story 2.4's lifecycle-extension protocol).
assert set(_NEXT_SPECIALIST_BY_STATE.keys()) == (
    set(LIFECYCLE_TRANSITIONS.keys()) | TERMINAL_STATES
), (
    "_NEXT_SPECIALIST_BY_STATE keys MUST equal "
    "LIFECYCLE_TRANSITIONS.keys() | TERMINAL_STATES per AC-4"
)


# --------------------------------------------------------------------------- #
# Exception classes                                                           #
# --------------------------------------------------------------------------- #


class ResumeCommandError(Exception):
    """Raised on substrate-level failures inside the resume command.

    Pattern 5 — loud-fail / named invariants. Analogous in shape to
    :class:`cross_state_recovery.CrossStateRecoveryError` and
    :class:`session_start_reattach.SessionStartReattachError`.

    RESERVED for substrate-level errors:
      * :func:`cross_state_recovery.evaluate_recovery` raised
        :class:`CrossStateRecoveryError` (chained via ``from exc``).
      * :class:`MarkerClassRegistry` failed to construct.
      * Any other unexpected exception from the recovery substrate that
        is NOT in the documented :class:`CrossStateRecoveryError` set.

    Cross-state disagreement does NOT raise this — disagreement surfaces
    as the ``recovery-state-conflict`` marker class via Story 8.2's
    ``evaluate_recovery``; THIS substrate consumes the marker via
    :class:`ResumeOutcome.marker_class` ``= "recovery-state-conflict"``
    on the ``resume-conflict-halt`` action.

    Attributes:
        reason: Short kebab-case discriminator naming the concrete failure.
            Documented values: ``"cross-state-recovery-substrate-error"``,
            ``"marker-registry-construction-failure"``.
        diagnostic: Human-readable diagnostic naming the failure mode and
            a remediation hint per NFR-O5.
    """

    def __init__(self, *, reason: str, diagnostic: str) -> None:
        self.reason = reason
        self.diagnostic = diagnostic
        super().__init__(f"ResumeCommandError[{reason}]: {diagnostic}")


class CanDispatchInvariantViolation(ResumeCommandError):
    """Raised when the canonical Story 8.6 substrate guard
    :func:`no_destructive_resume_guard.can_dispatch` denies dispatch on
    a path that 8.2's ``evaluate_recovery`` cleared as recoverable.

    This indicates a Story 8.2 substrate bug — ``evaluate_recovery``
    returned ``recovery-clean`` / ``recovery-rebuilt`` despite a
    structural disagreement that would re-dispatch a specialist whose
    prior output is recorded.

    The exception's ``reason`` and ``diagnostic`` fields are sourced
    from the :class:`Verdict` returned by the canonical guard — so
    downstream consumers can route on the structured ``DenyReason``
    enum (one of ``"prior-output-recorded"``, ``"branch-already-exists"``,
    ``"work-already-committed"``, ``"run-state-unexpected-state"``).

    Programmer-error invariant per Pattern 5.
    """

    #: Programmer-error invariant signal — no marker emission at THIS
    #: surface (this is a structural defensive raise, not a runtime
    #: failure mode). Mirrors Story 8.2's ``CrossStateRecoveryError``
    #: posture.
    marker_class: ClassVar[None] = None


# --------------------------------------------------------------------------- #
# Pydantic models — AC-1 public API                                           #
# --------------------------------------------------------------------------- #


class ResumeRequest(BaseModel):
    """Typed input to :func:`evaluate_resume`.

    Pattern 6 — frozen so callers cannot mutate the request mid-evaluation.
    Mirrors :class:`cross_state_recovery.RecoveryRequest`,
    :class:`session_start_reattach.ReattachRequest`, and
    :class:`init_non_destructive_guard.GuardRequest` in shape.

    Attributes:
        project_root: Practitioner's BMAD project root. The substrate
            inspects ``<project_root>/_bmad/automation/run-state.yaml`` AND
            (via :func:`cross_state_recovery.evaluate_recovery`)
            ``<project_root>/_bmad-output/implementation-artifacts/<story-id>*.md``.
            Required; ``is_absolute`` enforced at validation time.
        story_id: BMAD story identifier the practitioner supplied at
            ``/bmad-automation resume <story-id>``. Required; ``min_length=1``.
        story_doc_resolver: Pattern-6 dependency-injection seam for tests;
            forwarded to :class:`cross_state_recovery.RecoveryRequest`.
            Production runs default to
            :func:`orchestrator_run_entry.default_story_doc_resolver` per
            the Story 2.5 + Story 8.2 precedent.
        sprint_status_resolver: Pattern-6 DI seam; forwarded to
            :class:`cross_state_recovery.RecoveryRequest`. Production
            default = :func:`orchestrator_run_entry.default_sprint_status_resolver`.
            Consumed by the delegated ``evaluate_recovery`` call only —
            THIS substrate does NOT directly consult sprint-status.
        run_state_writer: Pattern-6 DI seam; forwarded to
            :func:`cross_state_recovery.evaluate_recovery` for the
            rebuild-path on-disk write. Production default =
            :func:`cross_state_recovery._default_run_state_writer`.
        run_state_path: Pattern-6 explicit-path injection. ``None``
            resolves to ``project_root / RUN_STATE_RELATIVE_PATH``. CLI
            sets this when ``--run-state-path`` is provided so the
            substrate's pre-check matches the path the recovery substrate
            writes to.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    project_root: pathlib.Path = Field(
        ...,
        description=(
            "Absolute path to the practitioner's project root. Read for "
            "the run-state file and forwarded to the recovery substrate."
        ),
    )
    story_id: str = Field(
        ...,
        min_length=1,
        description=(
            "BMAD story identifier; sourced from /bmad-automation resume "
            "<story-id>."
        ),
    )
    story_doc_resolver: StoryDocResolver | None = Field(
        default=None,
        description=(
            "Optional StoryDocResolver injection for tests. None → "
            "default_story_doc_resolver at evaluate-recovery time."
        ),
    )
    sprint_status_resolver: SprintStatusResolver | None = Field(
        default=None,
        description=(
            "Optional SprintStatusResolver injection for tests. None → "
            "default_sprint_status_resolver at evaluate-recovery time."
        ),
    )
    run_state_writer: RunStateWriter | None = Field(
        default=None,
        description=(
            "Optional RunStateWriter injection for tests. None → "
            "_default_run_state_writer at evaluate-recovery time."
        ),
    )
    run_state_path: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional explicit path to the run-state file. None → "
            "project_root / RUN_STATE_RELATIVE_PATH."
        ),
    )

    @field_validator("project_root")
    @classmethod
    def _project_root_must_be_absolute(cls, v: pathlib.Path) -> pathlib.Path:
        if not v.is_absolute():
            raise ValueError(
                f"project_root must be an absolute path; got {v!r}. "
                "Pass pathlib.Path.cwd() or a CLI-resolved absolute path."
            )
        return v


_ResumeAction = Literal[
    "resume-dispatch",
    "resume-already-terminal",
    "resume-conflict-halt",
    "resume-no-run-state",
]


class ResumeOutcome(BaseModel):
    """Typed return of :func:`evaluate_resume`.

    Pattern 6 — frozen so the orchestrator skill cannot mutate the
    outcome between read and route.

    Attributes:
        action: One of the four canonical actions per AC-1.
        next_specialist: Populated on ``resume-dispatch`` only; the
            specialist to dispatch per the AC-4 closed map. ``None`` on
            the other three actions.
        final_run_state: Post-recovery :class:`RunState` per AC-1's
            tuple-return mirror semantics. Populated on
            ``resume-dispatch`` AND ``resume-already-terminal``.
            Populated on ``resume-conflict-halt`` ONLY when
            ``marker_registry`` was supplied to :func:`evaluate_resume`
            (mirrors 8.2's ``evaluate_recovery`` test-injection seam).
            ``None`` on ``resume-no-run-state``.
        recovery_outcome: Passthrough of the first tuple element from
            :func:`cross_state_recovery.evaluate_recovery`. Populated on
            ``resume-dispatch``, ``resume-already-terminal``,
            ``resume-conflict-halt``. ``None`` on ``resume-no-run-state``
            (the recovery substrate is NOT invoked on this path).
        marker_class: Set to ``"recovery-state-conflict"`` ONLY on
            ``resume-conflict-halt`` (passthrough from
            ``recovery_outcome.marker_class``); ``None`` on the other
            three actions.
        diagnostic: Rendered diagnostic. ``None`` on ``resume-dispatch``
            and ``resume-already-terminal``. Populated on
            ``resume-conflict-halt`` (passthrough of 8.2's
            already-prefixed ``recovery-state-conflict: ...`` text per
            its AC-7). Populated on ``resume-no-run-state`` (rendered
            per AC-2's named-invariant template).
        pre_dispatch_can_dispatch_verdict: Populated on
            ``resume-dispatch``; the projection of
            :class:`Verdict.allow` returned by the canonical
            :func:`no_destructive_resume_guard.can_dispatch` (Story 8.6).
            ``True`` on the normal recoverable-and-clean path; substrate
            raises :class:`CanDispatchInvariantViolation` instead of
            returning ``False``. The structured ``DenyReason`` and
            human-readable diagnostic are surfaced via the rewritten
            exception message — the bool projection is retained for
            backward compatibility with downstream consumers.
            ``None`` on the other three actions.
    """

    model_config = ConfigDict(frozen=True)

    action: _ResumeAction
    next_specialist: Literal["dev", "review-bmad", "qa"] | None = None
    final_run_state: RunState | None = None
    recovery_outcome: RecoveryOutcome | None = None
    marker_class: Literal["recovery-state-conflict"] | None = None
    diagnostic: str | None = None
    pre_dispatch_can_dispatch_verdict: bool | None = None


# --------------------------------------------------------------------------- #
# Pure functions                                                              #
# --------------------------------------------------------------------------- #


def determine_next_specialist(
    current_state: CurrentState,
) -> Literal["dev", "review-bmad", "qa"] | None:
    """Pure deterministic function returning the next specialist for the
    given lifecycle state per AC-4's closed map.

    Pure: no side effects, byte-identical on identical input.

    Source-of-truth derivation: keys are the union of
    ``LIFECYCLE_TRANSITIONS.keys()`` and ``TERMINAL_STATES``; values are
    computed from the lifecycle DAG. The closed map is
    :data:`_NEXT_SPECIALIST_BY_STATE`.

    Args:
        current_state: Lifecycle state from the post-recovery
            ``RunState.current_state`` field.

    Returns:
        The specialist name to dispatch (``"dev"``, ``"review-bmad"``, or
        ``"qa"``) for non-terminal states; ``None`` for ``done`` and
        ``escalated`` (terminal — no dispatch needed).

    Raises:
        KeyError: If ``current_state`` is not in :data:`_NEXT_SPECIALIST_BY_STATE`.
            This is structurally impossible at runtime because the
            ``CurrentState`` Literal is closed; the AC-9
            ``test_next_specialist_map_keys_equal_lifecycle_union`` test
            asserts the structural equality.
    """
    return _NEXT_SPECIALIST_BY_STATE[current_state]


def render_no_run_state_diagnostic(
    request: ResumeRequest, run_state_path: pathlib.Path
) -> str:
    """Pure deterministic formatter producing the AC-2 named-invariant
    diagnostic text.

    Mirrors :func:`cross_state_recovery.render_recovery_state_conflict_diagnostic`
    in shape but is structurally distinct — the no-run-state-resume path
    is NOT a ``recovery-state-conflict`` marker; the diagnostic carries
    no marker-class prefix, just the named invariant + remediation
    pointers.

    Composition (per AC-2 verbatim):

    1. ``resume: `` literal prefix (NOT ``recovery-state-conflict: ``).
    2. ``no-in-flight-run-found-for-story-id`` named-invariant token.
    3. ``story-id: <story-id>`` clause.
    4. ``probed run-state path: <absolute-path>`` clause.
    5. ``remediation:`` clause naming TWO paths per ``epics.md:3289``
       verbatim:
         (a) start a fresh run via ``/bmad-automation run <story-id>``;
         (b) verify the story-id matches the in-flight story (check
         ``_bmad-output/implementation-artifacts/sprint-status.yaml`` for
         stories in ``in-progress`` state).
    6. Pointer-to-status clause: for inspection of all in-flight stories,
       run ``/bmad-automation status`` (Story 8.5 — when landed).
    """
    parts: list[str] = [
        f"resume: no-in-flight-run-found-for-story-id: {request.story_id}",
        f"probed run-state path: {run_state_path!s}",
        (
            "remediation: "
            f"(a) start a fresh run via /bmad-automation run {request.story_id}, "
            "(b) verify the story-id matches the in-flight story "
            "(check _bmad-output/implementation-artifacts/sprint-status.yaml "
            "for stories in 'in-progress' state)"
        ),
        (
            "for inspection of all in-flight stories, run "
            "/bmad-automation status (Story 8.5 — when landed)"
        ),
    ]
    return "; ".join(parts)





# --------------------------------------------------------------------------- #
# evaluate_resume — canonical entry point                                     #
# --------------------------------------------------------------------------- #


def evaluate_resume(
    request: ResumeRequest,
    *,
    marker_registry: "MarkerClassRegistry | None" = None,
) -> tuple[ResumeOutcome, RunState | None]:
    """Composite explicit-reattach decision for ``/bmad-automation resume``.

    No state-advancing actions outside what :func:`evaluate_recovery`'s
    rebuild path does — this substrate is read-only against story-doc,
    sprint-status, and the git working tree.

    The four branches per AC-1:

    1. ``run-state file does NOT exist at the resolved path`` →
       ``resume-no-run-state``. NO marker emitted; named-invariant
       diagnostic produced via :func:`render_no_run_state_diagnostic`.
       :func:`evaluate_recovery` is NOT invoked.
    2. ``recovery-clean`` OR ``recovery-rebuilt`` AND non-terminal
       ``current_state`` → ``resume-dispatch``. ``next_specialist`` is
       computed via :func:`determine_next_specialist`; the canonical
       :func:`no_destructive_resume_guard.can_dispatch` (Story 8.6)
       runs and either returns ``Verdict(allow=True)`` or causes the
       substrate to raise :class:`CanDispatchInvariantViolation` with
       the verdict's structured ``reason`` and ``diagnostic`` populated.
    3. ``recovery-clean`` OR ``recovery-rebuilt`` AND terminal
       ``current_state`` (``done`` / ``escalated``) →
       ``resume-already-terminal``. No dispatch; the orchestrator skill
       informs the practitioner.
    4. ``recovery-conflict-halt`` → ``resume-conflict-halt``. The marker
       is in ``final_run_state.active_markers`` per 8.2's emission;
       diagnostic propagated unchanged. NO marker re-emission at THIS
       surface.

    Args:
        request: The typed input.
        marker_registry: Optional marker-class registry forwarded to
            :func:`evaluate_recovery` for AC-3's marker-emission seam on
            the ``recovery-conflict-halt`` path.

    Returns:
        ``(ResumeOutcome, RunState | None)``. The second element mirrors
        :func:`cross_state_recovery.evaluate_recovery`'s second tuple
        element semantics:
          * ``resume-dispatch`` → post-recovery ``RunState``;
          * ``resume-already-terminal`` → post-recovery ``RunState``;
          * ``resume-conflict-halt`` → 8.2's second-tuple-element
            (run-state with the recovery-state-conflict marker appended
            if registry supplied; otherwise prior run-state unchanged);
          * ``resume-no-run-state`` → ``None``.

    Raises:
        ResumeCommandError: When :func:`evaluate_recovery` raises
            :class:`CrossStateRecoveryError` (chained via ``from exc``).
        CanDispatchInvariantViolation: When the canonical Story 8.6
            :func:`no_destructive_resume_guard.can_dispatch` denies
            dispatch on a path 8.2 cleared as recoverable.
    """
    run_state_path = (
        request.run_state_path
        if request.run_state_path is not None
        else request.project_root / RUN_STATE_RELATIVE_PATH
    )

    # AC-2 — no-run-state pre-check: surface BEFORE invoking
    # evaluate_recovery. NO marker emitted on this path.
    try:
        run_state_file_exists = run_state_path.is_file()
    except OSError as exc:
        raise ResumeCommandError(
            reason="run-state-path-access-error",
            diagnostic=(
                f"resume: harness-level error: cannot probe run-state path "
                f"{run_state_path!s}: {exc}"
            ),
        ) from exc
    if not run_state_file_exists:
        diagnostic = render_no_run_state_diagnostic(request, run_state_path)
        return (
            ResumeOutcome(
                action="resume-no-run-state",
                next_specialist=None,
                final_run_state=None,
                recovery_outcome=None,
                marker_class=None,
                diagnostic=diagnostic,
                pre_dispatch_can_dispatch_verdict=None,
            ),
            None,
        )

    # AC-3 — recovery delegation: load run-state from disk, build
    # RecoveryRequest, invoke evaluate_recovery, route on the returned
    # RecoveryOutcome.action.
    try:
        run_state = _load_run_state_from_disk(run_state_path)
    except CrossStateRecoveryError as exc:
        raise ResumeCommandError(
            reason="cross-state-recovery-substrate-error",
            diagnostic=str(exc),
        ) from exc

    # TOCTOU guard: the file may have been deleted between is_file() and
    # _load_run_state_from_disk; treat a None return as no-run-state rather
    # than passing None to evaluate_recovery (which would misroute to
    # resume-conflict-halt with a spurious recovery-state-conflict marker).
    if run_state is None:
        diagnostic = render_no_run_state_diagnostic(request, run_state_path)
        return (
            ResumeOutcome(
                action="resume-no-run-state",
                next_specialist=None,
                final_run_state=None,
                recovery_outcome=None,
                marker_class=None,
                diagnostic=diagnostic,
                pre_dispatch_can_dispatch_verdict=None,
            ),
            None,
        )

    recovery_request = RecoveryRequest(
        project_root=request.project_root,
        story_id=request.story_id,
        story_doc_resolver=request.story_doc_resolver,
        sprint_status_resolver=request.sprint_status_resolver,
        run_state_writer=request.run_state_writer,
        run_state_path=run_state_path,
    )

    try:
        recovery_outcome, returned_run_state = evaluate_recovery(
            recovery_request,
            run_state=run_state,
            marker_registry=marker_registry,
        )
    except CrossStateRecoveryError as exc:
        raise ResumeCommandError(
            reason="cross-state-recovery-substrate-error",
            diagnostic=str(exc),
        ) from exc

    if recovery_outcome.action == "recovery-conflict-halt":
        return (
            ResumeOutcome(
                action="resume-conflict-halt",
                next_specialist=None,
                final_run_state=returned_run_state,
                recovery_outcome=recovery_outcome,
                marker_class=recovery_outcome.marker_class,
                diagnostic=recovery_outcome.diagnostic,
                pre_dispatch_can_dispatch_verdict=None,
            ),
            returned_run_state,
        )

    # recovery-clean OR recovery-rebuilt: returned_run_state is non-None
    # by 8.2's contract on these branches.
    assert returned_run_state is not None, (
        "evaluate_recovery contract: recovery-clean/recovery-rebuilt MUST "
        "return a non-None run-state as the second tuple element"
    )
    final_run_state = returned_run_state

    # AC-3 — terminal-state branch: resume-already-terminal.
    if final_run_state.current_state in TERMINAL_STATES:
        return (
            ResumeOutcome(
                action="resume-already-terminal",
                next_specialist=None,
                final_run_state=final_run_state,
                recovery_outcome=recovery_outcome,
                marker_class=None,
                diagnostic=None,
                pre_dispatch_can_dispatch_verdict=None,
            ),
            final_run_state,
        )

    # AC-3 + AC-4 — non-terminal-state: resume-dispatch.
    next_specialist = determine_next_specialist(final_run_state.current_state)
    # AC-4: non-terminal states MUST yield a non-None specialist.
    assert next_specialist is not None, (
        f"determine_next_specialist({final_run_state.current_state!r}) "
        "returned None on a non-terminal state; _NEXT_SPECIALIST_BY_STATE "
        "is out of sync with TERMINAL_STATES"
    )

    # AC-5 — canonical Story 8.6 substrate guard; raise on deny. The
    # raised CanDispatchInvariantViolation surfaces the verdict's
    # structured DenyReason and the human-readable diagnostic, so
    # downstream consumers (automated triage tooling, logs) can route
    # on the structured reason rather than parsing free text.
    verdict: Verdict = can_dispatch(
        next_specialist, request.story_id, final_run_state
    )
    if not verdict.allow:
        raise CanDispatchInvariantViolation(
            reason="can-dispatch-deny-on-recovered-state",
            diagnostic=(
                f"can-dispatch denied: reason={verdict.reason}; "
                f"{verdict.diagnostic}; specialist={next_specialist!r}; "
                f"story_id={request.story_id!r}"
            ),
        )

    return (
        ResumeOutcome(
            action="resume-dispatch",
            next_specialist=next_specialist,
            final_run_state=final_run_state,
            recovery_outcome=recovery_outcome,
            marker_class=None,
            diagnostic=None,
            pre_dispatch_can_dispatch_verdict=True,
        ),
        final_run_state,
    )


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bmad-automation-resume",
        description=(
            "/bmad-automation resume <story-id> substrate (Story 8.3, "
            "FR47 + NFR-R7). Composes Story 8.2's cross_state_recovery."
            "evaluate_recovery + the lifecycle-state-to-specialist closed "
            "map for next-specialist determination. Halts on "
            "no-in-flight-run OR recovery-state-conflict; otherwise "
            "advances to the next undetermined seam in the story loop."
        ),
    )
    parser.add_argument(
        "story_id",
        type=str,
        help=(
            "BMAD story identifier (e.g., '8-3'); matches the story-doc "
            "filename prefix under _bmad-output/implementation-artifacts/."
        ),
    )
    parser.add_argument(
        "--project-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Absolute path to the practitioner's project root. Defaults "
            "to the current working directory."
        ),
    )
    parser.add_argument(
        "--run-state-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Optional explicit path to the run-state file. Defaults to "
            "<project_root>/_bmad/automation/run-state.yaml."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point invoked by the orchestrator skill's
    ``steps/resume.md`` runtime protocol per AC-7.

    Exit codes per AC-1 / AC-10:
        * ``0`` — ``resume-dispatch`` OR ``resume-already-terminal``
          (silent successes from a flow-control perspective; the
          orchestrator skill's runtime branches on the parsed exit code +
          the printed ``next_specialist`` line for advance vs
          already-terminal).
        * ``1`` — ``resume-conflict-halt`` OR ``resume-no-run-state``
          (both halts; the skill's runtime surfaces the diagnostic and
          does NOT proceed to dispatch).
        * ``2`` — harness-level error inside the substrate per Pattern 5
          (Pydantic model construction failure, recovery substrate
          unexpected exception, etc.).

    The 0-vs-1 split for advance-vs-halt mirrors Story 8.2's
    ``cross-state-recovery`` CLI semantics (NOT Story 8.1's
    all-zero-on-marker convention — resume is invoked from the
    orchestrator skill, NOT a hook).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    project_root = args.project_root if args.project_root is not None else pathlib.Path.cwd()
    if not project_root.is_absolute():
        project_root = project_root.resolve()

    try:
        request = ResumeRequest(
            project_root=project_root,
            story_id=args.story_id,
            run_state_path=args.run_state_path,
        )
    except (ValueError, ValidationError) as exc:
        print(f"resume: harness-level error: {exc}", file=sys.stderr)
        return 2

    try:
        outcome, _ = evaluate_resume(request, marker_registry=None)
    except ResumeCommandError as exc:
        print(f"resume: harness-level error: {exc}", file=sys.stderr)
        return 2

    if outcome.action == "resume-dispatch":
        if outcome.final_run_state is None:
            print(
                "resume: harness-level error: resume-dispatch outcome has "
                "final_run_state=None — substrate contract violated",
                file=sys.stderr,
            )
            return 2
        print(
            (
                f"resume: resume-dispatch: next_specialist="
                f"{outcome.next_specialist}; "
                f"current_state={outcome.final_run_state.current_state}; "
                f"story_id={request.story_id}"
            ),
            file=sys.stderr,
        )
        return 0

    if outcome.action == "resume-already-terminal":
        if outcome.final_run_state is None:
            print(
                "resume: harness-level error: resume-already-terminal outcome has "
                "final_run_state=None — substrate contract violated",
                file=sys.stderr,
            )
            return 2
        print(
            (
                f"resume: resume-already-terminal: story_id={request.story_id} "
                f"is already at {outcome.final_run_state.current_state}; "
                "nothing to do"
            ),
            file=sys.stderr,
        )
        return 0

    if outcome.action == "resume-conflict-halt":
        # outcome.diagnostic is 8.2's bare "recovery-state-conflict: ..." text
        # (no "resume: " prefix at the library level). The CLI adds the
        # "resume: " prefix here to match the machine-parseable line format
        # in steps/resume.md — two-level: library diagnostic + CLI prefix.
        print(f"resume: {outcome.diagnostic}", file=sys.stderr)
        return 1

    # outcome.action == "resume-no-run-state"
    print(outcome.diagnostic, file=sys.stderr)
    return 1
