"""Story 5.6 — Retry-budget-exhaustion non-advance + state preservation + marker.

The SIXTH Epic-5 substrate landing per ``epics.md`` lines 2218-2233 — sibling
of Story 5.1's :mod:`retry_budget`, Story 5.2's :mod:`retry_router`, Story
5.3's :mod:`retry_dispatch`, Story 5.4's :mod:`scope_assertion`, and Story
5.5's :mod:`retry_history`. The FR8 + FR14 substrate-level claim CLOSER
paired with Story 5.1's :class:`RetryDecision.HALT_BUDGET_EXHAUSTED` opener.

Sources (verbatim):
    * **PRD FR8** (``_bmad-output/planning-artifacts/prd.md`` line 819):
      "Orchestrator enforces a configurable whole-story retry budget
      (default: 2; configurable via ``_bmad/automation/config.yaml``)."
    * **PRD FR14** (``prd.md`` line 825): "On retry-budget exhaustion,
      Orchestrator does not auto-advance state, does not auto-retry, and
      preserves the branch and run-state file for human inspection."
    * **PRD FR15** (``prd.md`` line 826): "Orchestrator assembles an
      **escalation bundle** (distinct from merge-ready bundle) on retry-
      budget exhaustion — contains retry history, outstanding findings,
      rationale, and a pointer to ``deferred-work.md``." (Forward-pointer:
      Story 5.8 owns the bundle's content; THIS module computes the path
      and invokes the caller-injected assembler.)
    * **PRD NFR-R5** (``prd.md`` line 949): "Retry history preservation —
      retry history (findings, scope, diff per round) is preserved even
      when retry-budget exhausts and escalation fires; history is
      available via the escalation bundle and via the ``status`` command.
      (Cross-reference: FR13, FR14, FR48.)"
    * **PRD NFR-R8** (``prd.md`` line 952) — cross-state consistency /
      write-ordering. The canonical-write-ordering invariant at the
      escalation level is: assembler-callback success first → run-state
      advance second → event-log-append third (mirrors
      :func:`loud_fail_harness.lifecycle_state_machine.commit_transition`'s
      ordering byte-for-byte).
    * **Story 5.6 verbatim epic AC** at ``epics.md`` lines 2396-2422.
    * **epics.md line 2350** (verbatim, the dual-trigger fan-in
      commitment): "Story 5.4 reuses this exhaustion pathway".
    * **epics.md line 2349** (verbatim, the budget-non-decrement
      invariant): "the violation does NOT consume a retry round (it's a
      contract violation, not a normal failure)".

Marker class:
    The ``retry-budget-exhausted`` marker class is enumerated in
    ``schemas/marker-taxonomy.yaml`` lines 247-252 (Story 1.4 v1 closed
    taxonomy). REUSED here verbatim per the no-introductions discipline.
    The taxonomy entry's ``diagnostic_pointer`` (verbatim from line
    248-251): "FR8 (budget) + FR14 (non-advance + state preservation) +
    FR15 (escalation bundle assembly path). Normal-flow halt event, NOT a
    failure of any single specialist." Surfaced VERBATIM on
    :attr:`RetryBudgetExhaustionDiagnostic.remediation_hint` (whitespace-
    collapsed to a single line per the loud-fail-block format) so an
    operator pasting the diagnostic into chat identifies the remediation
    surface without reading source. Remediation here is human review of
    accumulated retry history, not fixing a contract violation or a hook
    script (epics.md line 2413 verbatim) — the ``retry-budget-exhausted``
    marker is REMEDIATION-SHAPED (Story 1.11) distinct from
    ``scope-assertion-violation`` and ``hook-failed`` because the
    remediation surface differs.

Event class:
    The ``escalation-fired`` orchestrator-event class is enumerated in
    ``schemas/orchestrator-event.yaml`` lines 277-300 (Story 1.3 + Story
    1.4 epic-close event sweep). THIS module is the FIRST runtime emitter;
    the schema commitment is already in place. The ``escalation_class``
    enum at lines 294-297 includes ``retry-budget-exhausted`` (this story
    emits), ``qa-verification-fail``, and ``qa-env-setup-fail`` (Story 4.10
    / Story 5.8 territory — NOT here). The scope-violation-via-exhaustion
    routing reuses ``escalation_class: "retry-budget-exhausted"`` per
    epics.md line 2350's "reuse the exhaustion pathway" framing — the
    pathway is the escalation pathway, NOT a separate event class. The
    trigger discriminator surfaces in
    :attr:`RetryBudgetExhaustionDiagnostic.trigger` only, NOT in the event
    payload's enum field.

Lifecycle state value:
    The ``current_state: "escalated"`` enum value is enumerated in
    ``schemas/run-state.yaml`` lines 180-192 + the
    :data:`loud_fail_harness.run_state.CurrentState` ``Literal`` at
    ``run_state.py:387-394``. The enum value was proactively added by
    Story 2.4; THIS module is the FIRST runtime mutator-to-this-value. The architectural commitment at
    ``lifecycle_state_machine.py:97-105`` (verbatim): "``escalated`` has
    no key AND no value (reached via Story 5.6's ``escalation-fired``
    event, NOT via a state-transition; ...). Adding ``<anything> →
    escalated`` to this map would conflate the lifecycle-transition
    mechanism with the escalation mechanism — two architecturally
    distinct concepts per ADR-005. Story 5.6 introduces the
    ``escalation-fired`` emission alongside the ``current_state`` rewrite
    to ``"escalated"`` via a separate code path; this module does not
    touch that path." THIS module IS that "separate code path". The
    module does NOT call
    :func:`loud_fail_harness.lifecycle_state_machine.commit_transition`
    (which rejects rewrites per its forward-only validation). The module
    DOES compose
    :func:`loud_fail_harness.run_state.advance_run_state` directly
    (path-agnostic; writes whatever ``next_state`` is supplied; lifecycle
    invariants are the caller's responsibility) with
    ``next_state.current_state = "escalated"`` set via
    ``model_copy(update=...)``.

Composition with Story 2.2 :func:`advance_run_state`:
    The "assembler-write-success first → run-state advance second" ordering
    invariant is enforced via the ``story_doc_callback`` parameter. The
    closure :func:`record_retry_budget_exhaustion` constructs invokes the
    caller-injected ``escalation_bundle_assembler`` and returns
    :class:`StoryDocCallbackResult` with ``accepted=True`` on success;
    on assembler exception, raises
    :exc:`loud_fail_harness.run_state.StoryDocCallbackBlocked` with the
    underlying exception as ``cause``. Story 2.2's helper enforces the
    canonical-write-ordering: assembler-callback success first → run-state-
    advance second; on assembler failure, run-state is unchanged
    (FR14 verbatim "preserves the branch and run-state file" is satisfied
    — the file remains at its prior ``current_state``).

Composition with Story 5.1 :class:`RetryDecision`:
    THIS module accepts ``RetryDecision.HALT_BUDGET_EXHAUSTED`` AS DATA via
    the :attr:`ExhaustionTrigger.BUDGET_EXHAUSTED` discriminator. Does NOT
    call :func:`loud_fail_harness.retry_budget.evaluate_retry_decision` —
    the orchestrator-skill performs that evaluation upstream and dispatches
    into THIS module's entry point.

Composition with Story 5.4 :class:`ScopeAssertionViolation`:
    THIS module accepts the violation's ``diagnostic`` attribute
    (a :class:`loud_fail_harness.scope_assertion.ScopeAssertionDiagnostic`)
    as part of the :class:`ExhaustionContext` payload when ``trigger ==
    ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION``. The violation is a
    trigger, NOT an internal computation. Per epics.md line 2349 verbatim
    "the violation does NOT consume a retry round" — THIS module does NOT
    increment any counter; the budget is bypass-routed through this
    handler when the trigger is ``SCOPE_ASSERTION_VIOLATION``.

Composition with Story 5.5 externalized retry-history references:
    THIS module preserves the on-disk
    ``_bmad-output/retry-history/{story_id}/{round_id}/`` artifacts by
    structural omission (it never invokes filesystem operations against
    those paths). The run-state's ``retry_history`` reference array
    (Story 5.5 thickening: ``round_id`` + ``path`` sub-properties) is
    copied into ``next_state`` verbatim via
    ``current_state.model_copy(update={"current_state": "escalated"})``.
    Story 5.8's escalation-bundle assembler resolves the references
    at bundle-render time via
    :func:`loud_fail_harness.retry_history.resolve_retry_round`; THIS
    module's :func:`default_escalation_bundle_assembler` delegates to
    Story 5.8's :func:`bundle_assembly_escalation.assemble_escalation_bundle`
    which renders the references per AC-2 section 4 of Story 5.8.

Composition with Story 5.8 (escalation-bundle assembly):
    The :data:`EscalationBundleAssembler` callable seam is the production-
    wiring boundary. Story 5.8 supplies the FR15-shaped assembler at
    :mod:`loud_fail_harness.bundle_assembly_escalation`; the orchestrator
    skill injects :func:`default_escalation_bundle_assembler` which is
    now a thin delegate to Story 5.8's full assembler. The deterministic
    output path is still computed by :func:`compute_escalation_bundle_path`
    AS-IS (Story 5.8 reuses this helper byte-for-byte).

Forward-pointer: Story 6.1 (loud-fail block):
    :attr:`RetryBudgetExhaustionResult.diagnostic_message` is consumed
    by Story 6.1's loud-fail block per the FR48a / NFR-O5 actionable-
    pointer posture (the message includes the marker class identifier +
    remediation hint substring + retry-history-summary).

Forward-pointer: Story 8.x (resumability):
    SessionStart reattachment reads ``current_state == "escalated"`` and
    routes resume-attempts to the escalation-bundle path NOT to a fresh
    dispatch. THIS module's state mutation is the entry condition for
    that recovery path.

Pluggability invariant (FR62):
    This module lives at ``tools/loud-fail-harness/src/loud_fail_harness/
    retry_budget_exhaustion.py`` (the harness substrate). The FR62
    pluggability gate (:mod:`pluggability_gate`) scans only ``agents/*.md``
    specialist subagent files; it does NOT scan harness substrate.
    Downstream callers compose against THIS module AS DATA per ADR-001's
    portable-surface boundary.

Sensor-not-advisor invariant (FR52 / ADR-002 invariant 1):
    THIS module is FLOW-POLICY territory (orchestrator's job). Specialists
    do not call it; specialists are REPORTED-ON via the persisted
    artifacts. The module RETURNS a :class:`RetryBudgetExhaustionResult`
    carrying the diagnostic; it does NOT log or print. The caller
    (orchestrator skill, Story 6.1's loud-fail block, Story 5.8's bundle
    assembler) decides emission and operator-surface rendering. THIS
    module does NOT mutate ``current_state.active_markers`` — the marker
    payload is delivered via the structured result for the caller to
    enroll on a subsequent advance.

Architectural placement (load-bearing):
    THIS module is a substrate **library**, NOT a sixth-counted substrate
    component. ADR-003 enumerates exactly five substrate components
    (envelope_validator / event_validator / reconciler / enumeration_check
    / fixture_coverage). :mod:`retry_budget_exhaustion` is a sibling of
    :mod:`run_state`, :mod:`retry_dispatch`, :mod:`scope_assertion`,
    :mod:`retry_history` — all substrate libraries that grew the harness
    module count without growing the substrate-component count.

``find_repo_root()`` discipline (Epic 1 retro Action #1):
    No path computation in this module calls ``find_repo_root()`` at
    module import time. All public helpers accept ``repo_root`` as a
    caller-supplied parameter.
"""

from __future__ import annotations

import datetime
import enum
import pathlib
import secrets
from collections.abc import Callable
from typing import Any, ClassVar, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loud_fail_harness.lifecycle_state_machine import EventLogAppender
from loud_fail_harness.run_state import (
    AdvanceResult,
    LastRetryDirective,
    RetryAttempt,
    RunState,
    RunStateAdvanceBlocked,
    StoryDocCallbackBlocked,
    StoryDocCallbackResult,
    advance_run_state,
)
from loud_fail_harness.scope_assertion import ScopeAssertionDiagnostic

__all__ = [
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


#: The marker class identifier sourced VERBATIM from
#: ``schemas/marker-taxonomy.yaml`` line 247. Single-source-of-truth
#: posture mirroring :data:`loud_fail_harness.retry_history.DANGLING_EVIDENCE_REF_MARKER`.
RETRY_BUDGET_EXHAUSTED_MARKER: Final[Literal["retry-budget-exhausted"]] = (
    "retry-budget-exhausted"
)

#: Verbatim remediation-hint substring sourced from
#: ``schemas/marker-taxonomy.yaml`` lines 248-251 (whitespace-collapsed
#: to a single line per the loud-fail-block convention).
_REMEDIATION_HINT: Final[str] = (
    "FR8 (budget) + FR14 (non-advance + state preservation) + FR15 "
    "(escalation bundle assembly path). Normal-flow halt event, NOT a "
    "failure of any single specialist."
)

#: The deterministic on-disk root for escalation bundles. Paired with
#: :data:`loud_fail_harness.retry_history.RETRY_HISTORY_ROOT` per the
#: ``_bmad-output/{kind}/{story-id}/{run-id}/`` path-shape convention.
ESCALATION_BUNDLES_ROOT: Final[str] = "_bmad-output/escalation-bundles"

#: The single-file-per-bundle filename. Story 5.8 may split into
#: ``escalation.md`` + sub-artifacts as additive thickening.
ESCALATION_BUNDLE_FILENAME: Final[str] = "escalation.md"


# --------------------------------------------------------------------------- #
# Trigger discriminator                                                       #
# --------------------------------------------------------------------------- #


class ExhaustionTrigger(str, enum.Enum):
    """Closed-enum trigger discriminator for
    :func:`record_retry_budget_exhaustion`.

    Two members; values are kebab-case identifier strings per Pattern 1
    (precedent: :class:`loud_fail_harness.retry_budget.RetryDecision`).
    The string values intentionally coincide with upstream identifiers:

    * :attr:`BUDGET_EXHAUSTED` — trigger from Story 5.1's
      :attr:`loud_fail_harness.retry_budget.RetryDecision.HALT_BUDGET_EXHAUSTED`.
      The value ``"budget-exhausted"`` is structurally adjacent to the
      RetryDecision member but distinct (no marker emission at this
      surface).
    * :attr:`SCOPE_ASSERTION_VIOLATION` — trigger from Story 5.4's
      :exc:`loud_fail_harness.scope_assertion.ScopeAssertionViolation`.
      The value ``"scope-assertion-violation"`` matches
      ``schemas/marker-taxonomy.yaml`` line 237's ``marker_class`` value
      verbatim — the trigger discriminator and the upstream marker-class
      identifier coincide; this is intentional structural alignment per
      the no-introductions discipline. The trigger value is NOT itself a
      marker emission — it's a typed routing input.
    """

    BUDGET_EXHAUSTED = "budget-exhausted"
    SCOPE_ASSERTION_VIOLATION = "scope-assertion-violation"


# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class ExhaustionContext(BaseModel):
    """The assembler-callable input shape; the full diagnostic payload
    Story 5.8's assembler consumes to render the bundle.

    Frozen + ``extra="forbid"``; field declaration order is load-bearing
    for byte-stable ``model_dump_json()`` output (parallel to
    :class:`loud_fail_harness.run_state.RetryAttempt` discipline).

    ``arbitrary_types_allowed=True`` is required because
    :attr:`scope_violation_diagnostic` is a :mod:`dataclasses`-shaped
    type (Story 5.4's :class:`ScopeAssertionDiagnostic`) consumed AS-IS
    via composition (NOT via re-modeling); the boundary discipline is
    Pydantic at boundaries, dataclasses at flow-policy internals — the
    diagnostic crosses that line and is allowed in arbitrary-types form.

    Co-presence invariant (enforced via ``model_validator(mode="after")``):
    ``trigger == SCOPE_ASSERTION_VIOLATION`` REQUIRES
    ``scope_violation_diagnostic is not None``;
    ``trigger == BUDGET_EXHAUSTED`` REQUIRES
    ``scope_violation_diagnostic is None``. Programmer-error invariant;
    upstream orchestrator-skill composition is responsible for matching
    trigger to diagnostic.
    """

    model_config = ConfigDict(
        frozen=True, extra="forbid", arbitrary_types_allowed=True
    )

    trigger: ExhaustionTrigger
    story_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    branch_name: str = Field(min_length=1)
    retry_history: tuple[RetryAttempt, ...]
    last_envelope: dict[str, Any] | None
    last_retry_directive: LastRetryDirective | None
    scope_violation_diagnostic: ScopeAssertionDiagnostic | None
    bundle_artifact_path: str = Field(min_length=1)
    # Story 6.1: the ``run_state.active_markers`` snapshot for the run,
    # consumed by the escalation-bundle's loud-fail block sub-renderer.
    # Defaults to the empty tuple so existing call sites that do not yet
    # surface ``active_markers`` continue to work; the on-disk run-state
    # IS the source of truth (Story 2.2) and the empty default lands the
    # ``## ✓ Loud-Fail Markers — None`` sentinel per AC-3.
    active_markers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _require_trigger_diagnostic_co_presence(self) -> ExhaustionContext:
        if self.trigger is ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION:
            if self.scope_violation_diagnostic is None:
                raise ValueError(
                    "ExhaustionContext: trigger=SCOPE_ASSERTION_VIOLATION "
                    "requires scope_violation_diagnostic to be set"
                )
        else:
            if self.scope_violation_diagnostic is not None:
                raise ValueError(
                    "ExhaustionContext: trigger=BUDGET_EXHAUSTED requires "
                    "scope_violation_diagnostic to be None"
                )
        return self


class RetryBudgetExhaustionDiagnostic(BaseModel):
    """The marker payload shape; structurally aligned with
    :class:`loud_fail_harness.scope_assertion.ScopeAssertionDiagnostic`
    per the established Epic-5 convention.

    Frozen + ``extra="forbid"``; field declaration order is load-bearing
    for byte-stable ``model_dump_json()`` output. The :attr:`marker_class`
    ``ClassVar`` posture mirrors
    :class:`loud_fail_harness.scope_assertion.ScopeAssertionDiagnostic.marker_class`
    precedent.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    marker_class: ClassVar[Literal["retry-budget-exhausted"]] = (
        "retry-budget-exhausted"
    )

    trigger: ExhaustionTrigger
    story_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    branch_name: str = Field(min_length=1)
    retry_count: int = Field(ge=0)
    bundle_artifact_path: str = Field(min_length=1)
    remediation_hint: str = Field(min_length=1)


class RetryBudgetExhaustionResult(BaseModel):
    """The canonical entry point's structured return value.

    Consumed by the orchestrator skill / Story 6.1's loud-fail block /
    Story 5.8's bundle assembler caller. Frozen for immutability +
    determinism; field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    advance_result: AdvanceResult
    emitted_event: dict[str, Any]
    diagnostic: RetryBudgetExhaustionDiagnostic
    diagnostic_message: str = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Exceptions                                                                  #
# --------------------------------------------------------------------------- #


class RetryBudgetExhaustionError(Exception):
    """Base exception for the :mod:`loud_fail_harness.retry_budget_exhaustion`
    surface. Pattern 5 named-invariant lineage.
    """


class EscalationBundleAssemblerFailed(RetryBudgetExhaustionError):
    """Raised when the caller-injected
    :data:`EscalationBundleAssembler` raises any exception.

    Carries the underlying exception via ``__cause__`` (set by the
    ``raise ... from <orig>`` site) AND a :attr:`bundle_path` attribute
    naming the path the assembler was attempting to write. The
    ``current_state`` advance is BLOCKED in this case (the canonical-
    write-ordering invariant: assembler-write-success-first → run-state-
    advance-second; if the assembler fails, the run-state stays at its
    prior ``current_state`` per Story 2.2's
    :exc:`loud_fail_harness.run_state.RunStateAdvanceBlocked` semantics).
    The orchestrator skill must surface the assembler failure via a
    separate ``bundle-assembly-failed`` marker per Story 6.9 — THIS module
    raises and re-raises; emission of the ``bundle-assembly-failed``
    marker is downstream consumer policy.
    """

    def __init__(self, *, bundle_path: str) -> None:
        self.bundle_path: str = bundle_path
        super().__init__(
            f"escalation bundle assembler failed; bundle_path={bundle_path!r}"
        )


class RetryBudgetExhaustionInvariantViolation(
    RetryBudgetExhaustionError, ValueError
):
    """Raised on programmer-error invariant violations.

    Cases:

    * Calling :func:`record_retry_budget_exhaustion` with
      ``current_state.current_state == "done"`` — escalating from
      ``done`` is meaningless.
    * Calling with ``current_state.current_state == "escalated"`` —
      already-escalated double-call protection.
    * The trigger ↔ diagnostic co-presence invariant from
      :class:`ExhaustionContext`'s ``model_validator`` (raised at the
      pre-condition guard layer BEFORE :class:`ExhaustionContext`
      construction so the diagnostic surface is consistent).
    * ``story_id`` / ``run_id`` empty / absolute / contains ``..`` path-
      traversal segments at :func:`compute_escalation_bundle_path`.

    The ``ValueError`` lineage is load-bearing: callers may catch
    ``ValueError`` for input-shape contract violations without coupling
    to the substrate-specific exception class.
    """


# --------------------------------------------------------------------------- #
# EscalationBundleAssembler type alias                                        #
# --------------------------------------------------------------------------- #


#: Type alias for the assembler-callable interface. Signature:
#: ``(context: ExhaustionContext) -> None``. The assembler writes the
#: escalation bundle file to ``context.bundle_artifact_path`` (the path
#: is repo-root-relative; the assembler's caller is responsible for
#: resolving against ``repo_root``); on success, returns ``None``; on
#: failure, raises any exception (THIS module catches and re-raises as
#: :exc:`EscalationBundleAssemblerFailed`). Story 5.8's full FR15-shaped
#: assembler at :mod:`loud_fail_harness.bundle_assembly_escalation` is
#: the production wiring; :func:`default_escalation_bundle_assembler`
#: is now a thin delegate to that full assembler.
EscalationBundleAssembler = Callable[["ExhaustionContext"], None]


# --------------------------------------------------------------------------- #
# Path helpers                                                                #
# --------------------------------------------------------------------------- #


def compute_escalation_bundle_path(
    *,
    repo_root: pathlib.Path,
    story_id: str,
    run_id: str,
) -> pathlib.Path:
    """Return the deterministic per-run escalation bundle file path
    ``{repo_root}/_bmad-output/escalation-bundles/{story_id}/{run_id}/escalation.md``.

    Pure path computation; does NOT create the directory. Mirrors
    :func:`loud_fail_harness.retry_history.compute_round_dir` +
    :func:`loud_fail_harness.qa_evidence_persistence.compute_run_dir`
    byte-for-byte structure.

    Args:
        repo_root: The repository root the per-run bundle path is
            anchored to. Caller-supplied per the Epic 1 retro Action #1
            discipline.
        story_id: The BMAD story identifier.
        run_id: The per-run identifier.

    Returns:
        ``pathlib.Path`` representing
        ``{repo_root}/_bmad-output/escalation-bundles/{story_id}/{run_id}/escalation.md``.

    Raises:
        RetryBudgetExhaustionInvariantViolation: ``story_id`` empty /
            absolute / contains ``..``; ``run_id`` empty / absolute /
            contains ``..``.
    """
    if not story_id:
        raise RetryBudgetExhaustionInvariantViolation(
            "story_id must not be empty"
        )
    _story_pure = pathlib.PurePosixPath(story_id)
    if _story_pure.is_absolute():
        raise RetryBudgetExhaustionInvariantViolation(
            f"story_id must not be an absolute path; got {story_id!r}"
        )
    if ".." in _story_pure.parts:
        raise RetryBudgetExhaustionInvariantViolation(
            f"story_id must not contain '..' path traversal segments; "
            f"got {story_id!r}"
        )
    if not run_id:
        raise RetryBudgetExhaustionInvariantViolation(
            "run_id must not be empty"
        )
    _run_pure = pathlib.PurePosixPath(run_id)
    if _run_pure.is_absolute():
        raise RetryBudgetExhaustionInvariantViolation(
            f"run_id must not be an absolute path; got {run_id!r}"
        )
    if ".." in _run_pure.parts:
        raise RetryBudgetExhaustionInvariantViolation(
            f"run_id must not contain '..' path traversal segments; "
            f"got {run_id!r}"
        )
    return (
        repo_root
        / ESCALATION_BUNDLES_ROOT
        / story_id
        / run_id
        / ESCALATION_BUNDLE_FILENAME
    )


# --------------------------------------------------------------------------- #
# Default placeholder assembler                                               #
# --------------------------------------------------------------------------- #


def default_escalation_bundle_assembler(
    *, repo_root: pathlib.Path
) -> EscalationBundleAssembler:
    """Return an :data:`EscalationBundleAssembler` callable bound to
    ``repo_root`` that delegates to Story 5.8's
    :func:`loud_fail_harness.bundle_assembly_escalation.assemble_escalation_bundle`.

    Per Story 5.8 (epics.md lines 2460-2491): the previous placeholder
    body is RETIRED — the production assembler now writes a fully
    FR15-shaped escalation-variant bundle conforming to the relevant
    ``schemas/escalation-bundles/{bundle_class}.yaml`` fragment.
    The function's public signature is preserved byte-for-byte so
    Story 5.6's
    :func:`record_retry_budget_exhaustion` callsites are unchanged; the
    return value remains an :data:`EscalationBundleAssembler` callable
    (signature ``(context: ExhaustionContext) -> None``).

    The closure imports :mod:`loud_fail_harness.bundle_assembly_escalation`
    LAZILY at first invocation so the import-time graph is unaffected
    (the assembler module composes :mod:`bundle_assembly`'s rendering
    helpers; importing it eagerly here would tighten the import-time
    coupling between the retry-budget-exhaustion module and the
    bundle-assembly module without runtime benefit).

    The delegate discards the
    :class:`loud_fail_harness.bundle_assembly_escalation.AssembleEscalationBundleResult`
    return value because the :data:`EscalationBundleAssembler` callable
    typedef returns ``None`` per the seam contract; the discarded
    information (bundle path, emitted markers, header text, payload) is
    available to direct callers of
    :func:`assemble_escalation_bundle` but not to
    :func:`record_retry_budget_exhaustion`'s closure-injection seam.

    Args:
        repo_root: The repository root used to resolve schema fragment
            paths AND the deterministic output path computed by
            :func:`compute_escalation_bundle_path`.

    Returns:
        An :data:`EscalationBundleAssembler` callable suitable for
        injection into :func:`record_retry_budget_exhaustion`.
    """

    def _assembler(context: ExhaustionContext) -> None:
        from loud_fail_harness.bundle_assembly_escalation import (
            assemble_escalation_bundle,
        )

        assemble_escalation_bundle(context, repo_root=repo_root)

    return _assembler


# --------------------------------------------------------------------------- #
# Internal helpers                                                            #
# --------------------------------------------------------------------------- #


def _now_isoformat() -> str:
    """UTC ISO-8601 timestamp at function-call time. Indirected so tests
    can monkey-patch via ``mock.patch.object`` without touching
    ``datetime.datetime.now``. Mirrors
    :func:`loud_fail_harness.lifecycle_state_machine._now_isoformat`."""
    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat()


def _generate_event_id(story_id: str) -> str:
    """Generate an opaque event identifier for ``escalation-fired``.
    Mirrors the output format of
    :func:`loud_fail_harness.lifecycle_state_machine._generate_event_id`
    (``ev-{story_id}-{prefix}-{hex4}``); the prefix is fixed at
    ``"escalation"`` here (lifecycle machine version accepts a
    caller-supplied prefix argument)."""
    return f"ev-{story_id}-escalation-{secrets.token_hex(4)}"


def _format_diagnostic_message(diagnostic: RetryBudgetExhaustionDiagnostic) -> str:
    """Single-line stderr-ready loud-fail-block message.

    Format: ``retry-budget-exhausted: trigger=<trigger>, story_id=<id>,
    retry_count=<N>, branch=<branch>, bundle=<path> — <remediation_hint>``.

    Byte-stable for AC-9 golden-string comparison; the em-dash separator
    + verbatim remediation-hint substring satisfy the NFR-O5 actionable-
    pointer posture.
    """
    return (
        f"{diagnostic.marker_class}: "
        f"trigger={diagnostic.trigger.value}, "
        f"story_id={diagnostic.story_id}, "
        f"retry_count={diagnostic.retry_count}, "
        f"branch={diagnostic.branch_name}, "
        f"bundle={diagnostic.bundle_artifact_path} "
        f"— {diagnostic.remediation_hint}"
    )


def _construct_escalation_event(
    *,
    story_id: str,
    bundle_artifact_path: str,
) -> dict[str, Any]:
    """Construct the schema-validated ``escalation-fired`` event payload
    conformant to ``schemas/orchestrator-event.yaml`` lines 277-300.

    The ``escalation_class`` enum value is fixed at ``"retry-budget-exhausted"``
    for both trigger paths per epics.md line 2350's "reuse the exhaustion
    pathway" framing — the trigger discriminator surfaces in
    :class:`RetryBudgetExhaustionDiagnostic.trigger` only, NOT in this
    payload's enum field.
    """
    return {
        "event_class": "escalation-fired",
        "event_id": _generate_event_id(story_id),
        "timestamp": _now_isoformat(),
        "story_id": story_id,
        "escalation_class": "retry-budget-exhausted",
        "bundle_artifact_path": bundle_artifact_path,
    }


# --------------------------------------------------------------------------- #
# Canonical entry point                                                       #
# --------------------------------------------------------------------------- #


def record_retry_budget_exhaustion(
    *,
    run_state_path: pathlib.Path,
    current_state: RunState,
    trigger: ExhaustionTrigger,
    escalation_bundle_assembler: EscalationBundleAssembler,
    event_log_appender: EventLogAppender,
    repo_root: pathlib.Path,
    scope_violation_diagnostic: ScopeAssertionDiagnostic | None = None,
) -> RetryBudgetExhaustionResult:
    """Record a retry-budget exhaustion: invoke the assembler, advance
    run-state to ``"escalated"``, emit the ``escalation-fired`` event,
    return the structured diagnostic.

    Execution order (load-bearing per NFR-R8 + Pattern 4):

        1. Pre-condition guards.
        2. Compute the bundle path; render to repo-relative posix string.
        3. Construct the :class:`ExhaustionContext`.
        4. Construct ``next_state`` via
           ``current_state.model_copy(update={"current_state": "escalated"})``.
        5. Construct the ``escalation-fired`` event payload.
        6. Compose :func:`advance_run_state` with assembler-as-callback
           (closure invokes assembler then returns
           :class:`StoryDocCallbackResult` ``accepted=True``; on
           assembler exception, raises :exc:`StoryDocCallbackBlocked`).
        7. On :exc:`RunStateAdvanceBlocked` (assembler failed), re-raise
           as :exc:`EscalationBundleAssemblerFailed`.
        8. On success, append the event via ``event_log_appender``.
        9. Construct and return the :class:`RetryBudgetExhaustionResult`.

    Args:
        run_state_path: Caller-controlled on-disk path of the run-state
            file. Threaded through to :func:`advance_run_state`.
        current_state: The :class:`RunState` instance before escalation.
            Must NOT be in a terminal state (``"done"`` /
            ``"escalated"``); pre-condition violation raises
            :exc:`RetryBudgetExhaustionInvariantViolation`.
        trigger: One of :attr:`ExhaustionTrigger.BUDGET_EXHAUSTED` or
            :attr:`ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION`.
        escalation_bundle_assembler: Caller-injected assembler. Story
            5.8 supplies the production assembler; until 5.8 lands, the
            orchestrator injects :func:`default_escalation_bundle_assembler`.
        event_log_appender: Caller-injected event-log appender per
            :data:`loud_fail_harness.lifecycle_state_machine.EventLogAppender`.
        repo_root: The repository root for bundle-path computation.
        scope_violation_diagnostic: Required iff ``trigger ==
            SCOPE_ASSERTION_VIOLATION``; forbidden iff ``trigger ==
            BUDGET_EXHAUSTED`` (co-presence invariant).

    Returns:
        :class:`RetryBudgetExhaustionResult` carrying the
        :class:`AdvanceResult`, the emitted event, the diagnostic, and
        the byte-stable single-line diagnostic message.

    Raises:
        RetryBudgetExhaustionInvariantViolation: Pre-condition guard
            failure (terminal state OR co-presence invariant violation).
        EscalationBundleAssemblerFailed: The caller-injected assembler
            raised any exception. ``__cause__`` carries the underlying
            exception. On-disk run-state is unchanged.
    """
    # Step 1: pre-condition guards.
    if current_state.current_state in {"done", "escalated"}:
        raise RetryBudgetExhaustionInvariantViolation(
            f"escalation from terminal state "
            f"{current_state.current_state!r} is meaningless; "
            f"current_state must be one of "
            f"{{'ready-for-dev', 'in-progress', 'review', 'qa'}}"
        )
    if (
        trigger is ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION
        and scope_violation_diagnostic is None
    ):
        raise RetryBudgetExhaustionInvariantViolation(
            "trigger=SCOPE_ASSERTION_VIOLATION requires "
            "scope_violation_diagnostic to be set"
        )
    if (
        trigger is ExhaustionTrigger.BUDGET_EXHAUSTED
        and scope_violation_diagnostic is not None
    ):
        raise RetryBudgetExhaustionInvariantViolation(
            "trigger=BUDGET_EXHAUSTED requires scope_violation_diagnostic "
            "to be None"
        )

    # Step 2: compute the bundle path; render as repo-relative posix string.
    bundle_path = compute_escalation_bundle_path(
        repo_root=repo_root,
        story_id=current_state.story_id,
        run_id=current_state.run_id,
    )
    bundle_artifact_path = bundle_path.relative_to(repo_root).as_posix()

    # Step 3: construct the ExhaustionContext (preservation by copy).
    context = ExhaustionContext(
        trigger=trigger,
        story_id=current_state.story_id,
        run_id=current_state.run_id,
        branch_name=current_state.branch_name,
        retry_history=current_state.retry_history,
        last_envelope=current_state.last_envelope,
        last_retry_directive=current_state.last_retry_directive,
        scope_violation_diagnostic=scope_violation_diagnostic,
        bundle_artifact_path=bundle_artifact_path,
        active_markers=current_state.active_markers,
    )

    # Step 4: construct next_state — only current_state field mutates.
    next_state = current_state.model_copy(
        update={"current_state": "escalated"}
    )

    # Step 5: construct the escalation-fired event payload.
    event = _construct_escalation_event(
        story_id=current_state.story_id,
        bundle_artifact_path=bundle_artifact_path,
    )

    # Step 6: compose advance_run_state with assembler-as-callback.
    def _assembler_callback() -> StoryDocCallbackResult:
        try:
            escalation_bundle_assembler(context)
        except Exception as exc:
            raise StoryDocCallbackBlocked(
                f"escalation bundle assembler raised: {exc!r}"
            ) from exc
        return StoryDocCallbackResult(accepted=True)

    try:
        advance_result = advance_run_state(
            run_state_path=run_state_path,
            next_state=next_state,
            story_doc_callback=_assembler_callback,
        )
    except RunStateAdvanceBlocked as blocked:
        # Step 7: re-raise as EscalationBundleAssemblerFailed.
        underlying: BaseException
        if isinstance(blocked.cause, BaseException):
            underlying = blocked.cause
        else:  # pragma: no cover — unreachable: _assembler_callback always returns accepted=True on success, so advance_run_state never raises RunStateAdvanceBlocked from a non-success-result callback
            underlying = blocked
        raise EscalationBundleAssemblerFailed(
            bundle_path=bundle_artifact_path
        ) from underlying

    # Step 8: emit the escalation-fired event AFTER advance succeeds.
    # event_log_appender failures propagate verbatim (mirrors
    # commit_transition's ordering at lifecycle_state_machine.py:752-756).
    event_log_appender(event)

    # Step 9: construct the diagnostic + result + return.
    diagnostic = RetryBudgetExhaustionDiagnostic(
        trigger=trigger,
        story_id=current_state.story_id,
        run_id=current_state.run_id,
        branch_name=current_state.branch_name,
        retry_count=len(current_state.retry_history),
        bundle_artifact_path=bundle_artifact_path,
        remediation_hint=_REMEDIATION_HINT,
    )
    diagnostic_message = _format_diagnostic_message(diagnostic)
    return RetryBudgetExhaustionResult(
        advance_result=advance_result,
        emitted_event=event,
        diagnostic=diagnostic,
        diagnostic_message=diagnostic_message,
    )
