"""No-destructive-resume substrate guard — Story 8.6 substrate library.

## Substrate-component identity

THIS module is a substrate **library** sibling of
:mod:`loud_fail_harness.session_start_reattach` (Story 8.1),
:mod:`loud_fail_harness.cross_state_recovery` (Story 8.2),
:mod:`loud_fail_harness.resume_command` (Story 8.3),
:mod:`loud_fail_harness.status_command` (Story 8.4),
:mod:`loud_fail_harness.multi_story_status` (Story 8.5),
:mod:`loud_fail_harness.init_non_destructive_guard` (Story 7.6 — the
naming-family parallel; ``init_non_destructive_guard`` discharges the
FR41/FR42 init-time non-destructive surface, THIS module discharges the
NFR-R7 reattach/recovery/resume non-destructive surface — same shape,
distinct seam). It is **NOT a sixth substrate component** beyond ADR-003
Consequence 1's enumerated five (``envelope_validator``, ``event_validator``,
``reconciler``, ``enumeration_check``, ``fixture_coverage``); the count
remains FIVE through Epic 8 per the Epic 7 retro framing
(``epic-7-retro-2026-05-08.md`` line 122) and Stories 8.2 / 8.5
Completion Notes ("Substrate-component count holds at FIVE").

## What this module owns

A SINGLE source-of-truth function ``can_dispatch(specialist, story_id,
run_state) -> Verdict`` that determines whether a given specialist can be
dispatched at the current reattachment / recovery / resume seam without
violating NFR-R7 ("on resume, orchestrator does not re-dispatch
specialists whose prior output was recorded"). The function is consumed
by :func:`session_start_reattach.evaluate_reattach` (Story 8.1) and
:func:`resume_command.evaluate_resume` (Story 8.3); :mod:`cross_state_recovery`
delegates to this substrate via documentation pointer (recovery is
reconciliation, NOT dispatch — the dispatch decision lives downstream of
``evaluate_recovery``'s return). The CI lint at
:mod:`loud_fail_harness.no_destructive_resume_lint` enforces this
consumption pattern structurally.

## Architectural anchors

- **NFR-R7** (PRD line 951 verbatim) — "No destructive resume — on
  resume, orchestrator does not re-dispatch specialists whose prior
  output was recorded." THIS module IS the structural enforcement of the
  invariant, replacing the documentation-only commitments + the
  ``resume_command._can_dispatch_inline`` AC-5 stub Story 8.3 documented
  as "Story 8.6 supersedes structurally".
- **NFR-R2** (PRD line 946) — "Crash recovery without duplicate state
  advance."
- **FR46** (PRD line 874) — SessionStart reattachment.
- **FR47** (PRD line 875) — ``/bmad-automation resume <story-id>``.
- **ADR-003 Consequence 1** (architecture.md lines 311-315) —
  substrate-component count closure at FIVE (this module is a
  substrate-library sibling, NOT a sixth component).
- **Pattern 4** state-update discipline — :class:`Verdict` is frozen
  Pydantic; field declaration order is load-bearing for byte-stable
  ``model_dump_json()`` output.
- **Pattern 5** loud-fail / named invariants —
  :class:`NoDestructiveResumeGuardError` surfaces substrate-level
  failures (e.g., a defensive ``isinstance`` guard catching a programmer
  passing ``None`` instead of a :class:`RunState`). The four documented
  deny conditions are reported via the structured :class:`Verdict`
  result, NOT via raised exceptions — callers route on
  ``Verdict.allow``.
- **Pattern 6** Python code style — strict typing, frozen Pydantic
  models, pure functions; no I/O at the substrate level.

## The four deny conditions + the allow case

Per epics.md:3378-3382 + 3397 verbatim. Priority order (most defensive
first; most general before most specific):

1. ``run-state-unexpected-state`` — ``run_state.current_state`` is NOT a
   member of ``LIFECYCLE_TRANSITIONS.keys() | TERMINAL_STATES``. The
   defensive sentinel runs FIRST so subsequent predicates can safely
   assume ``current_state`` is a valid :data:`run_state.CurrentState`.
   Structurally unreachable at runtime when the :class:`RunState`
   validates against its Pydantic schema (the field is a closed
   Literal); the predicate is a defensive sentinel against
   ``model_construct`` bypass paths.
2. ``prior-output-recorded`` — ``run_state.dispatched_specialist ==
   specialist`` AND ``run_state.last_envelope is not None``. The most
   general and most actionable deny condition.
3. ``work-already-committed`` — the COMMIT-LEVEL specialization for
   ``specialist == "dev"`` AND ``run_state.dispatched_specialist == "dev"``
   AND ``run_state.last_envelope`` carries a completed/succeeded
   ``status`` AND ``run_state.head_commit_sha`` is set. Structurally a
   subset of ``prior-output-recorded`` for the dev/commit case; checked
   AFTER ``prior-output-recorded`` so the more general reason is reported
   when both match.
4. ``branch-already-exists`` — ``run_state.branch_name`` is set AND the
   candidate dispatch implies branch creation (``specialist == "dev"``
   AND ``current_state == "ready-for-dev"``).

If no deny condition matches, return ``Verdict(allow=True)``.

## Pure-function contract

``can_dispatch()`` is a pure function on the tuple ``(specialist,
story_id, run_state)``. No I/O (no filesystem reads, no subprocess
calls, no network). Deterministic: byte-identical output on identical
input. Tests rely on this property — fixtures construct
:class:`RunState` instances in-memory and assert verdict equality
without mocking.

## Sensor-not-advisor

Per ADR-001 + Pattern 5, this substrate produces a directive
(:class:`Verdict`); callers route on ``Verdict.allow``. The deny
verdicts carry a structured ``reason`` (closed :data:`DenyReason` enum)
and a human-readable ``diagnostic`` for caller-rendered surfaces (e.g.,
:exc:`resume_command.CanDispatchInvariantViolation` reads
``Verdict.reason`` and ``Verdict.diagnostic`` to compose its exception
message; :func:`session_start_reattach.evaluate_reattach` reads
``Verdict.diagnostic`` to enrich its outcome's ``diagnostic`` field
without altering the outcome's ``action`` enum).

## Library-as-CLI-aid posture

The :func:`main` CLI exists for ad-hoc human inspection — a practitioner
debugging a deny verdict can replay it via the ``no-destructive-resume-guard``
CLI against a snapshotted run-state YAML. The CLI is NOT invoked by any
production code path at MVP. Mirrors :func:`marker_coverage_audit.main`'s
posture per ``pyproject.toml`` lines 70-74.

## Future override extension

Per epics.md:3381 verbatim, "explicit override is reserved for future
opt-in mechanism". MVP signature is ``(specialist, story_id, run_state)
-> Verdict`` — three positional arguments, no kwargs. Future extension
is an additive ``override: PractitionerOverride | None = None`` kwarg;
today's callers pass nothing; today's signature is closed.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
from collections.abc import Sequence
from typing import Any, ClassVar, Final, Literal

import yaml as _pyyaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from .lifecycle_state_machine import LIFECYCLE_TRANSITIONS, TERMINAL_STATES
from .run_state import RunState

__all__ = [
    "DenyReason",
    "NoDestructiveResumeGuardError",
    "Verdict",
    "can_dispatch",
    "main",
]

_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Public API — closed enums                                                   #
# --------------------------------------------------------------------------- #


#: Closed :class:`typing.Literal` enumeration of the FOUR deny reasons per
#: AC-2's enumeration. Declared at module top-level for re-use in test
#: parametrization. The four members map verbatim to epics.md:3380 + 3397's
#: enumeration:
#:   * ``"prior-output-recorded"`` — ``run_state.dispatched_specialist ==
#:     specialist`` AND ``run_state.last_envelope is not None``.
#:   * ``"branch-already-exists"`` — branch creation implied AND
#:     ``run_state.branch_name`` is set.
#:   * ``"work-already-committed"`` — commit-level specialization for the
#:     dev/commit case.
#:   * ``"run-state-unexpected-state"`` — defensive sentinel for
#:     structurally invalid ``current_state`` values (epics.md:3397's
#:     "safe-deny defensive default" row).
DenyReason = Literal[
    "prior-output-recorded",
    "branch-already-exists",
    "work-already-committed",
    "run-state-unexpected-state",
]


#: Closed :class:`typing.Literal` of the three MVP specialists per
#: ``architecture.md`` lines 1068-1072. Phase-1.5's ``lad`` specialist
#: is intentionally excluded — Story 8.6 governs the MVP loop only;
#: the LAD reattach surface lands when Phase 1.5 thickens.
_Specialist = Literal["dev", "review-bmad", "qa"]


# --------------------------------------------------------------------------- #
# Public API — Pydantic models                                                #
# --------------------------------------------------------------------------- #


class Verdict(BaseModel):
    """Typed return of :func:`can_dispatch`.

    Pattern 4 — frozen so callers cannot mutate the verdict between read
    and route. Mirrors :class:`init_non_destructive_guard.GuardOutcome`,
    :class:`session_start_reattach.ReattachOutcome`,
    :class:`cross_state_recovery.RecoveryOutcome`,
    :class:`resume_command.ResumeOutcome` in shape.

    Structural invariant: ``(allow is True) iff (reason is None and
    diagnostic is None)``. The :func:`_validate_allow_reason_invariant`
    model validator enforces this at construction time per Pattern 5
    (programmer-error invariant). Constructing
    ``Verdict(allow=True, reason="prior-output-recorded")`` raises
    :class:`pydantic.ValidationError`.

    Attributes:
        allow: Canonical allow/deny discriminator. ``True`` ⇒ dispatch is
            non-destructive; ``False`` ⇒ dispatch would violate NFR-R7.
        reason: Closed :data:`DenyReason` enum naming WHY dispatch is
            denied. ``None`` iff ``allow=True``.
        diagnostic: Human-readable diagnostic naming the deny condition
            AND a remediation hint per NFR-O5. ``None`` iff
            ``allow=True``. Caller-rendered: callers (e.g.,
            ``resume_command``, ``session_start_reattach``) compose this
            into their own outcome diagnostic / exception message.
    """

    model_config = ConfigDict(frozen=True)

    allow: bool
    reason: DenyReason | None = None
    diagnostic: str | None = None

    @model_validator(mode="after")
    def _validate_allow_reason_invariant(self) -> "Verdict":
        """Enforce ``(allow is True) iff (reason is None and diagnostic is None)``.

        Pattern 5 — programmer-error invariant. Constructing
        ``Verdict(allow=True, reason="prior-output-recorded")`` is a
        programmer error (claiming "allowed" but providing a deny
        reason); without this validator, the bug is silently constructed;
        with the validator, construction fails fast at the bug's
        introduction site.
        """
        if self.allow:
            if self.reason is not None or self.diagnostic is not None:
                raise ValueError(
                    "Verdict invariant violation: allow=True requires "
                    "reason=None AND diagnostic=None; got "
                    f"reason={self.reason!r} diagnostic={self.diagnostic!r}. "
                    "This is a programmer error — see "
                    "no_destructive_resume_guard.py:Verdict docstring."
                )
        else:
            if self.reason is None or self.diagnostic is None:
                raise ValueError(
                    "Verdict invariant violation: allow=False requires "
                    "reason AND diagnostic to both be set; got "
                    f"reason={self.reason!r} diagnostic={self.diagnostic!r}. "
                    "Use one of the four DenyReason literals + a non-empty "
                    "diagnostic string."
                )
        return self


# --------------------------------------------------------------------------- #
# Public API — exception classes                                              #
# --------------------------------------------------------------------------- #


class NoDestructiveResumeGuardError(Exception):
    """Raised on substrate-level failures inside the no-destructive-resume guard.

    Pattern 5 — loud-fail / named invariants. Analogous in shape to
    :class:`session_start_reattach.SessionStartReattachError`,
    :class:`cross_state_recovery.CrossStateRecoveryError`,
    :class:`resume_command.ResumeCommandError`.

    RESERVED for substrate-level errors:
      * a defensive ``isinstance`` check catching a caller passing
        ``None`` instead of a :class:`RunState`.
      * a CLI-only path failure (e.g., the run-state YAML file is
        unreadable AT CLI time — :func:`can_dispatch` itself never
        reads from disk).

    Attributes:
        reason: Short kebab-case discriminator naming the concrete
            failure mode.
        diagnostic: Human-readable diagnostic naming the failure mode
            and a remediation hint per NFR-O5.

    Programmer-error invariant signal — no marker emission at THIS
    surface (this is a structural defensive raise, not a runtime failure
    mode). Mirrors Story 8.3's :class:`CanDispatchInvariantViolation`
    posture.
    """

    #: Programmer-error invariant signal — no marker emission at THIS
    #: surface. Mirrors Story 8.3's ``CanDispatchInvariantViolation``.
    marker_class: ClassVar[None] = None

    def __init__(self, *, reason: str, diagnostic: str) -> None:
        self.reason = reason
        self.diagnostic = diagnostic
        super().__init__(f"NoDestructiveResumeGuardError[{reason}]: {diagnostic}")


# --------------------------------------------------------------------------- #
# Module-level constants                                                      #
# --------------------------------------------------------------------------- #


#: Closed enumeration of structurally valid ``current_state`` values per
#: AC-2's safe-deny defensive default. Computed at import time as the
#: union of :data:`lifecycle_state_machine.LIFECYCLE_TRANSITIONS.keys()`
#: + :data:`lifecycle_state_machine.TERMINAL_STATES`. The ``can_dispatch()``
#: function consults this set to short-circuit on structurally invalid
#: ``current_state`` values that bypassed Pydantic validation.
_VALID_CURRENT_STATES: Final[frozenset[str]] = frozenset(
    LIFECYCLE_TRANSITIONS.keys()
) | frozenset(TERMINAL_STATES)


#: The closed enum of envelope ``status`` values that constitute a
#: completed / committed dev seam per AC-2's work-already-committed
#: predicate. Sourced from the Story 1.2 envelope-schema's documented
#: status enumeration; the predicate is conservative — only literal
#: ``"completed"`` / ``"succeeded"`` count.
_COMPLETED_ENVELOPE_STATUSES: Final[frozenset[str]] = frozenset(
    {"completed", "succeeded"}
)


# --------------------------------------------------------------------------- #
# Internal predicates                                                         #
# --------------------------------------------------------------------------- #


def _is_run_state_in_unexpected_state(run_state: RunState) -> bool:
    """Return True iff ``run_state.current_state`` is NOT in the closed
    :data:`_VALID_CURRENT_STATES` enumeration.

    Defensive sentinel — at runtime ``RunState.current_state`` is a closed
    :class:`typing.Literal` so this predicate is structurally unreachable
    via the validating constructor. Reachable via
    :meth:`pydantic.BaseModel.model_construct` bypass paths (used by the
    AC-6 ``test_can_dispatch_safe_denies_when_current_state_outside_closed_enum``
    fixture).
    """
    return run_state.current_state not in _VALID_CURRENT_STATES


def _is_prior_output_recorded(
    specialist: _Specialist, run_state: RunState
) -> bool:
    """Return True iff ``run_state`` records prior output for ``specialist``.

    Per AC-2 verbatim: the predicate fires iff
    ``run_state.dispatched_specialist == specialist`` AND
    ``run_state.last_envelope is not None``. Mirrors
    :func:`resume_command._can_dispatch_inline`'s logic which Story 8.6
    supersedes structurally.
    """
    return (
        run_state.dispatched_specialist == specialist
        and run_state.last_envelope is not None
    )


def _is_work_already_committed(
    specialist: _Specialist, run_state: RunState
) -> bool:
    """Return True iff dispatching ``specialist`` would re-commit
    already-committed work.

    Per AC-2: the predicate fires when ALL of the following hold:
      * ``specialist == "dev"`` (commit-level deny applies only to dev);
      * ``run_state.dispatched_specialist == "dev"``;
      * ``run_state.last_envelope`` is recorded AND its ``status`` field
        is in :data:`_COMPLETED_ENVELOPE_STATUSES`;
      * ``run_state.head_commit_sha`` field is set on the run-state.

    The :class:`RunState` schema does NOT carry a top-level
    ``head_commit_sha`` field at v1.3; the post-commit SHA is observable
    via ``run_state.last_envelope`` payload (FR12 / Story 5.3 retry-
    scope-assertion documentation: dev's envelope carries the commit
    SHA of work it committed). The predicate consults
    ``run_state.last_envelope.get("head_commit_sha", ...)`` defensively.
    """
    if specialist != "dev":
        return False
    if run_state.dispatched_specialist != "dev":
        return False
    envelope = run_state.last_envelope
    if envelope is None:
        return False
    status = envelope.get("status")
    if status not in _COMPLETED_ENVELOPE_STATUSES:
        return False
    head_sha = envelope.get("head_commit_sha") or envelope.get("commit_sha")
    if not head_sha:
        return False
    return True


def _is_branch_already_existing(
    specialist: _Specialist, run_state: RunState
) -> bool:
    """Return True iff dispatching ``specialist`` would re-create an
    already-existing per-story branch.

    Per AC-2: the predicate fires iff ``run_state.branch_name`` is set
    AND the candidate dispatch implies branch creation. Branch creation
    is implied at the dev-at-ready-for-dev seam per Story 2.3's
    per-story-branch lifecycle module.

    Practical gating: the predicate ALSO checks
    ``run_state.dispatched_specialist == "dev"`` — i.e., a prior dev
    dispatch is what evidences the branch was previously created via
    dispatch. Without that evidence, ``branch_name`` may be the
    architecturally-required field populated at run-init time (Story 2.3)
    and is NOT a signal of re-dispatch destruction. This refinement
    keeps the predicate non-dead while preserving the AC-2 intent: deny
    only when re-dispatch would actually re-create.
    """
    if specialist != "dev":
        return False
    if run_state.current_state != "ready-for-dev":
        return False
    if not run_state.branch_name:
        return False
    if run_state.dispatched_specialist != "dev":
        return False
    return True


# --------------------------------------------------------------------------- #
# Diagnostic renderers                                                        #
# --------------------------------------------------------------------------- #


def _render_prior_output_recorded_diagnostic(
    specialist: _Specialist, story_id: str, run_state: RunState
) -> str:
    envelope = run_state.last_envelope
    envelope_status = envelope.get("status", "<unset>") if envelope else "<unset>"
    return (
        f"can-dispatch deny[prior-output-recorded]: "
        f"specialist={specialist!r}; story_id={story_id!r}; "
        f"dispatched_specialist={run_state.dispatched_specialist!r}; "
        f"last_envelope.status={envelope_status!r}; "
        "remediation: the seam has already produced output; resuming "
        "would re-dispatch a specialist whose envelope is recorded — "
        "advance to the next undetermined seam instead"
    )


def _render_work_already_committed_diagnostic(
    specialist: _Specialist, story_id: str, run_state: RunState
) -> str:
    envelope = run_state.last_envelope or {}
    head_sha = envelope.get("head_commit_sha") or envelope.get("commit_sha", "<unset>")
    return (
        f"can-dispatch deny[work-already-committed]: "
        f"specialist={specialist!r}; story_id={story_id!r}; "
        f"head_commit_sha={head_sha!r}; "
        "remediation: dev's work is already committed at the named SHA; "
        "resuming would re-commit; advance to the next undetermined seam"
    )


def _render_branch_already_exists_diagnostic(
    specialist: _Specialist, story_id: str, run_state: RunState
) -> str:
    return (
        f"can-dispatch deny[branch-already-exists]: "
        f"specialist={specialist!r}; story_id={story_id!r}; "
        f"branch_name={run_state.branch_name!r}; "
        "remediation: the per-story branch already exists; recovery "
        "should reattach to the branch, not re-create it"
    )


def _render_run_state_unexpected_state_diagnostic(
    specialist: _Specialist, story_id: str, run_state: RunState
) -> str:
    return (
        f"can-dispatch deny[run-state-unexpected-state]: "
        f"specialist={specialist!r}; story_id={story_id!r}; "
        f"current_state={run_state.current_state!r} "
        f"is outside the closed enumeration "
        f"{sorted(_VALID_CURRENT_STATES)!r}; "
        "remediation: this indicates a substrate bug — the run-state "
        "bypassed Pydantic validation; halt and triage manually"
    )


# --------------------------------------------------------------------------- #
# Public API — canonical entry point                                          #
# --------------------------------------------------------------------------- #


def can_dispatch(
    specialist: Literal["dev", "review-bmad", "qa"],
    story_id: str,
    run_state: RunState,
) -> Verdict:
    """Canonical guard determining whether ``specialist`` can be dispatched
    against ``run_state`` without violating NFR-R7.

    Pure deterministic function: no I/O; byte-identical output on
    identical input. Consumed by
    :func:`session_start_reattach.evaluate_reattach` (Story 8.1) and
    :func:`resume_command.evaluate_resume` (Story 8.3) per the
    consumption pattern enforced structurally by the
    :mod:`no_destructive_resume_lint` CI gate.

    Priority ordering of the four deny conditions (AC-2 verbatim):

    1. ``run-state-unexpected-state`` — the defensive sentinel; checked
       FIRST so subsequent predicates can safely assume ``current_state``
       is a valid :data:`run_state.CurrentState` member.
    2. ``work-already-committed`` — the COMMIT-LEVEL specialization for
       dev dispatches; checked BEFORE ``prior-output-recorded`` so the
       most specific and most actionable reason is reported when both
       conditions match (dev + completed envelope + commit SHA).
    3. ``prior-output-recorded`` — the general deny for all specialists
       with prior envelope output.
    4. ``branch-already-exists`` — the most specific (only fires for
       dev+ready-for-dev with a populated ``branch_name``).

    If no deny condition matches, return ``Verdict(allow=True)``.

    Args:
        specialist: The about-to-be-dispatched specialist; one of
            ``"dev"``, ``"review-bmad"``, ``"qa"``. Phase-1.5's ``lad``
            is intentionally excluded — Story 8.6 governs the MVP loop.
        story_id: BMAD story identifier; carried for diagnostic context.
        run_state: Current :class:`RunState` instance. NOT loaded from
            disk by THIS substrate; callers pass instances they have
            already loaded / validated upstream.

    Returns:
        :class:`Verdict` instance. ``Verdict.allow=True`` on the
        non-destructive path; ``Verdict.allow=False`` with structured
        ``reason`` and ``diagnostic`` on each of the four deny cases.

    Raises:
        NoDestructiveResumeGuardError: defensive substrate-level error
            (e.g., ``run_state`` is not a :class:`RunState` instance).
            Documented happy paths return a :class:`Verdict`.
    """
    if not isinstance(run_state, RunState):
        raise NoDestructiveResumeGuardError(
            reason="run-state-not-a-run-state-instance",
            diagnostic=(
                "can_dispatch() requires a RunState instance; got "
                f"{type(run_state).__name__!r}. Construct a RunState "
                "via RunState.model_validate(...) and pass it in. The "
                "substrate does NOT load run-state from disk; callers "
                "own the load."
            ),
        )

    # Priority 1 — the defensive sentinel runs FIRST so subsequent
    # predicates can dereference current_state without TypeError on
    # unexpected values.
    if _is_run_state_in_unexpected_state(run_state):
        return Verdict(
            allow=False,
            reason="run-state-unexpected-state",
            diagnostic=_render_run_state_unexpected_state_diagnostic(
                specialist, story_id, run_state
            ),
        )

    # Priority 2 — work-already-committed (commit-level specialization
    # for dev dispatches; checked BEFORE prior-output-recorded so the
    # most specific reason is reported when both predicates match).
    if _is_work_already_committed(specialist, run_state):
        return Verdict(
            allow=False,
            reason="work-already-committed",
            diagnostic=_render_work_already_committed_diagnostic(
                specialist, story_id, run_state
            ),
        )

    # Priority 3 — prior-output-recorded (general deny for all
    # specialists with prior envelope output).
    if _is_prior_output_recorded(specialist, run_state):
        return Verdict(
            allow=False,
            reason="prior-output-recorded",
            diagnostic=_render_prior_output_recorded_diagnostic(
                specialist, story_id, run_state
            ),
        )

    # Priority 4 — branch-already-exists (most specific; only fires for
    # dev+ready-for-dev with a populated branch_name).
    if _is_branch_already_existing(specialist, run_state):
        return Verdict(
            allow=False,
            reason="branch-already-exists",
            diagnostic=_render_branch_already_exists_diagnostic(
                specialist, story_id, run_state
            ),
        )

    return Verdict(allow=True, reason=None, diagnostic=None)


# --------------------------------------------------------------------------- #
# CLI — library-as-CLI-aid posture                                            #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="no-destructive-resume-guard",
        description=(
            "Library-as-CLI-aid for the no-destructive-resume substrate "
            "guard (Story 8.6, NFR-R7). Loads a run-state YAML from disk, "
            "invokes can_dispatch() against the supplied specialist + "
            "story-id, prints the rendered Verdict to stdout. NOT a CI "
            "gate — invoked manually by practitioners debugging a deny "
            "verdict. Mirrors marker-coverage-audit's posture per "
            "pyproject.toml lines 70-74."
        ),
    )
    parser.add_argument(
        "--run-state-path",
        required=True,
        type=str,
        help=(
            "Absolute or repo-relative path to a run-state YAML file. "
            "The CLI loads it, validates against the RunState schema, "
            "and passes the instance to can_dispatch()."
        ),
    )
    parser.add_argument(
        "--specialist",
        required=True,
        type=str,
        choices=["dev", "review-bmad", "qa"],
        help="The about-to-be-dispatched specialist.",
    )
    parser.add_argument(
        "--story-id",
        required=True,
        type=str,
        help="BMAD story identifier; carried into the rendered diagnostic.",
    )
    return parser


def _format_verdict(verdict: Verdict) -> str:
    """Pure formatter for stdout/stderr rendering; mirrors the
    pluggability-gate / status_command formatter shapes."""
    if verdict.allow:
        return "no-destructive-resume-guard: ALLOW"
    return (
        f"no-destructive-resume-guard: DENY[{verdict.reason}] "
        f"{verdict.diagnostic}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point per AC-1's library-as-CLI-aid posture.

    Exit codes:
        * ``0`` — ``Verdict.allow=True``.
        * ``1`` — ``Verdict.allow=False``.
        * ``2`` — substrate-level error (file missing, YAML parse error,
          schema validation failure, programmer-error invariant raise).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    run_state_path = pathlib.Path(args.run_state_path)
    if not run_state_path.is_absolute():
        run_state_path = run_state_path.resolve()

    if not run_state_path.is_file():
        print(
            f"no-destructive-resume-guard: harness-level error: "
            f"run-state file not found: {run_state_path!s}",
            file=sys.stderr,
        )
        return 2

    try:
        raw_text = run_state_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"no-destructive-resume-guard: harness-level error: "
            f"cannot read run-state file {run_state_path!s}: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        payload: Any = _pyyaml.safe_load(raw_text)
    except _pyyaml.YAMLError as exc:
        print(
            f"no-destructive-resume-guard: harness-level error: "
            f"YAML parse error in {run_state_path!s}: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        run_state = RunState.model_validate(payload)
    except ValidationError as exc:
        print(
            f"no-destructive-resume-guard: harness-level error: "
            f"run-state schema validation failed: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        verdict = can_dispatch(args.specialist, args.story_id, run_state)
    except NoDestructiveResumeGuardError as exc:
        print(
            f"no-destructive-resume-guard: harness-level error: {exc}",
            file=sys.stderr,
        )
        return 2

    print(_format_verdict(verdict))
    return 0 if verdict.allow else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
