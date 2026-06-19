"""BMAD lifecycle state-transition logic (story 2.4). FR5 + FR6 + NFR-R8.

Architectural placement (story 1.10b precedent + story 2.2 precedent + story
2.3 precedent): this module is a sibling of
:mod:`loud_fail_harness.story_doc_validator`,
:mod:`loud_fail_harness.run_state`, and
:mod:`loud_fail_harness.branch_lifecycle` — the substrate-library cohort.
It is **NOT a sixth substrate component**. ADR-003 Consequence 1 enumerates
exactly five substrate components (architecture.md lines 311-315); this
module is a substrate **library** consumed by Epic 2/3/5/6/7/8 specialist
subagents at runtime to perform schema-validated, NFR-R8-ordered, forward-
only lifecycle-state transitions against ``_bmad/automation/run-state.yaml``
(View 3 line 1171). The substrate-component count stays at FIVE; the harness
module count grows.

Closer in shape to ``run_state.py`` and ``branch_lifecycle.py`` than to the
directory-scanning CI gates: there is no canonical filesystem surface to
scan because state-transitions happen at orchestrator runtime in Epic 2+,
not as committed filesystem artifacts on disk.

What this library provides:
    * **Closed lifecycle map** :data:`LIFECYCLE_TRANSITIONS` — the four
      forward transitions encoded as a plain ``dict`` (read-only by
      convention; ``MappingProxyType`` wrapping deferred per AC-1 type
      annotation).
      (``ready-for-dev → in-progress → review → qa → done``). ``done``
      is intentionally absent from the keys (terminal); ``escalated`` is
      intentionally absent from BOTH keys and values (reachable only via
      Story 5.6's ``escalation-fired`` event class — NOT a state-
      transition target).
    * **Terminal-states predicate** :data:`TERMINAL_STATES` — the
      ``frozenset({"done", "escalated"})`` Story 2.7's Stop hook
      consumes to choose merge-ready vs escalation bundle.
    * **Pure-decision function** :func:`evaluate_envelope` — sensor-not-
      advisor in the most literal sense; reads ``(current_state,
      specialist, envelope_outcome)``, returns a :class:`TransitionDecision`
      naming either the next state (advance) or the halt. No I/O. No
      side effects.
    * **Forward-only commit function** :func:`commit_transition` — the
      SOLE API path that writes a forward transition; composes
      :func:`loud_fail_harness.run_state.advance_run_state` exclusively
      (no direct ``run-state.yaml`` writes; no API path that bypasses
      the helper); rejects backward / skip / from-terminal at the
      module level via :exc:`InvalidLifecycleTransition` BEFORE any
      I/O.
    * **Halt-recording function** :func:`record_halt` — the SOLE API
      path that surfaces a non-pass halt; emits the new
      ``state-transition-halted`` orchestrator-event via the caller-
      injected ``event_log_appender``; does NOT call
      :func:`advance_run_state` (FR6: "halts at the current state —
      does not advance"); the on-disk run-state's ``current_state`` is
      unchanged after a halt.

What this library enforces:
    * **FR5** (PRD line 813) — orchestrator transitions the story
      through BMAD lifecycle states (``ready-for-dev → in-progress →
      review → qa → done``) at each successful seam. Encoded
      structurally as :data:`LIFECYCLE_TRANSITIONS`.
    * **FR6** (PRD line 814) — orchestrator halts state advancement
      when a specialist returns non-pass status. Encoded structurally
      as :func:`evaluate_envelope`'s halt branch +
      :func:`record_halt`'s no-advance contract.
    * **FR62** (PRD line 897) — pluggability no-cross-references; this
      module is substrate, not specialist (see "FR62 pluggability
      classification" below).
    * **NFR-R8** (PRD line 952) — cross-state consistency: story-doc
      writes complete before run-state advances. Encoded structurally
      via :func:`commit_transition`'s exclusive composition of
      :func:`advance_run_state` (whose own keyword-only-non-defaulted
      ``story_doc_callback`` enforces the ordering at the substrate
      layer).
    * **Pattern 4** (architecture.md lines 973-981) — "All run-state
      writes go through atomic-write helpers. No direct writes to
      run-state.yaml outside the helper layer." This module composes
      that helper layer; it does not bypass it.
    * **Pattern 5** (architecture.md lines 983-991) — named-invariant
      diagnostic. :exc:`InvalidLifecycleTransition` carries
      ``current_state``, ``attempted_next_state``, and ``reason`` so
      programmer-error halts are surfaced loudly.
    * **ADR-001 Consequence 2** — every transition produces a schema-
      validated event written to run-state, surfaced in the terminal
      stream, and aggregated into the PR bundle. The
      ``event_log_appender`` callback is the substrate's expression of
      this contract; the caller (Story 2.5+) owns the persistence
      mechanism.

## The closed lifecycle map

:data:`LIFECYCLE_TRANSITIONS` is a plain ``dict`` (four entries), read-only
by convention. The map is closed by construction:

    ready-for-dev → in-progress
    in-progress  → review
    review       → qa
    qa           → done

``done`` has no key (terminal). ``escalated`` has no key AND no value
(reached via Story 5.6's ``escalation-fired`` event, NOT via a state-
transition; see ``schemas/orchestrator-event.yaml`` line 254). Adding
``<anything> → escalated`` to this map would conflate the lifecycle-
transition mechanism with the escalation mechanism — two architecturally
distinct concepts per ADR-005. Story 5.6 introduces the
``escalation-fired`` emission alongside the ``current_state`` rewrite to
``"escalated"`` via a separate code path; this module does not touch
that path.

## Why the halt path does not call advance_run_state

FR6 (PRD line 814) verbatim — "Orchestrator halts state advancement
when a specialist returns non-pass status and routes per flow policy."
Halts do NOT advance state; the on-disk ``current_state`` is unchanged
after a halt.

:func:`record_halt` writes only the orchestrator-event log (via the
caller-injected ``event_log_appender``); it does NOT touch
``run_state_path``, does NOT call
:func:`loud_fail_harness.run_state.advance_run_state`, does NOT modify
on-disk run-state in any way. The visibility is via the event log, not
by moving the lifecycle pointer (Pattern 5 + ADR-005 Consequence 1's
"story-doc canonical for tiebreak on recovery disagreement").

## Why event_log_appender is caller-injected

Sensor-not-advisor (Pattern 5; ADR-001 multi-writer story-doc model):
the caller (Story 2.5's orchestrator skill, eventually Story 2.12's
streaming wrapper) owns the actual log path and append mechanism. The
substrate accepts an :data:`EventLogAppender` callable and invokes it
once per emitted event; tests inject deterministic stubs via
``appender = lambda event: collected.append(event)`` without monkey-
patching.

The append mechanism (sync vs async, file-write vs streaming-emit,
bundled vs per-event) is the caller's policy; the substrate's
contract is just "give me a callable that takes a dict; I'll call it
once per event, AFTER the run-state advance has succeeded".

## Composition with Story 2.2's advance_run_state

:func:`commit_transition`'s execution order (load-bearing per AC-3):

    1. Validate ``next_state.current_state ==
       LIFECYCLE_TRANSITIONS[current_state.current_state]``; raise
       :exc:`InvalidLifecycleTransition` if not (rejects backward,
       skip, or from-terminal).
    2. Construct the ``state-transition`` orchestrator-event payload.
    3. Invoke
       :func:`loud_fail_harness.run_state.advance_run_state` with the
       supplied ``run_state_path``, ``next_state``, and
       ``story_doc_callback``. This composes the NFR-R8 ordering
       (story-doc canonical write first via callback, then run-state
       advance via atomic rename).
    4. On success of ``advance_run_state``, invoke
       ``event_log_appender(state_transition_event)`` to append the
       schema-validated event to the orchestrator-event log.
    5. Return :class:`CommitTransitionResult` carrying the
       ``advance_result`` and the ``emitted_event``.

If ``advance_run_state`` raises (whether
:exc:`loud_fail_harness.run_state.RunStateAdvanceBlocked`,
:exc:`OSError`, or any other exception), the event log appender is
NOT invoked — the state-transition event is NOT emitted on failed
transitions.

The exception propagation is verbatim: ``RunStateAdvanceBlocked``
propagates through :func:`commit_transition` unchanged; the caller
(Story 2.5) catches and emits the corresponding marker per Story
2.2's documented integration pattern.

## FR62 pluggability classification

This module is *substrate-shared library* per Story 1.10b's precedent
(``story_doc_validator.py``), Story 2.2's precedent (``run_state.py``),
Story 2.3's precedent (``branch_lifecycle.py``), and ADR-003's
substrate-vs-specialist boundary; consumed by Stories 2.5, 2.6, 2.7,
2.11 and Phase 1.5+ successors. The FR62 gate (Story 1.10a's
:mod:`loud_fail_harness.pluggability_gate`) does NOT flag substrate
cross-imports; specialist subagents (Dev, Review-BMAD, QA, LAD) live
in ``agents/*.md`` and the gate's no-cross-references rule applies to
*that* surface, not this one.

## Forward-compat consumers

Stories that will consume the public API of this module:

    * Story 2.5 — orchestrator skill scaffold (epics.md lines
      1278-1308): ``/bmad-automation run <story-id>`` calls
      :func:`evaluate_envelope` after each specialist return, then
      :func:`commit_transition` on pass or :func:`record_halt` on
      non-pass.
    * Story 2.6 — Task-tool dispatch with marker emission (epics.md
      lines 1309-1346): feeds specialist envelopes back through the
      state machine.
    * Story 2.7 — three hooks scaffolded (epics.md line 1347): Stop
      hook consumes :data:`TERMINAL_STATES` to choose merge-ready vs
      escalation bundle; SessionStart consumes the recovered
      ``current_state`` per FR46.
    * Story 2.11 — PR bundle assembly (epics.md lines 1482-1530):
      reads ``state-transition`` and ``state-transition-halted``
      events from the event log to render the "what happened"
      section.
    * Story 5.1 / 5.2 / 5.6 — retry budget + bucket-driven retry
      routing + retry-budget-exhaustion non-advance (epics.md lines
      2236-2422): extends :func:`record_halt`'s downstream consumers
      to add retry routing without rewriting the halt path itself;
      the state machine's halt API stays stable.
    * Story 8.1 / 8.2 / 8.3 — SessionStart reattachment + cross-state
      consistency recovery + resume command (epics.md lines
      3203-3300): recovery-time read of ``current_state``;
      :func:`evaluate_envelope` and :func:`commit_transition` consume
      the recovered state per the same forward-only invariants.
    * Phase 1.5+ — any future story that mutates lifecycle state
      consumes this primitive rather than re-implementing the
      lifecycle map + halt-on-non-pass + advance-via-2.2-helper
      protocol.

## Sensor-not-advisor (PRD-level invariant + Pattern 5)

The library RETURNS decisions (:class:`TransitionDecision`) and RAISES
typed exceptions (:exc:`InvalidLifecycleTransition`); it does NOT
embed flow policy, does NOT auto-retry, does NOT auto-escalate, does
NOT log, does NOT print. Retry routing is Story 5.2's responsibility;
escalation triggering is Story 5.6's responsibility. Same posture as
1.10b / 2.2 / 2.3.

## ``find_repo_root()`` discipline (Epic 1 retro Action #1)

Epic 1 retrospective Challenge #1 (line 55) flagged
``find_repo_root()`` called at module import time. This module honors
the discipline by construction: there is no filesystem surface to
compute (the helper consumes caller-supplied ``run_state_path`` and
``event_log_appender``); ``find_repo_root()`` is NOT called anywhere
in this module under any code path.
"""

from __future__ import annotations

import datetime
import pathlib
import secrets
from collections.abc import Callable
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict

from loud_fail_harness.run_state import (
    AdvanceResult,
    CurrentState,
    DispatchedSpecialist,
    RunState,
    StoryDocCallback,
    advance_run_state,
)


#: Closed enum for envelope statuses sourced from
#: ``schemas/envelope.schema.yaml`` (the ``status`` property's enum) PLUS
#: ``decision-needed`` per the state-machine contract: review-BMAD's
#: review-stage outcome is one of pass / fail / decision-needed / blocked.
#: ``pass`` is the only outcome that advances; the other three halt per
#: FR6. Kebab-case identifier values per Pattern 1.
EnvelopeOutcome = Literal["pass", "fail", "decision-needed", "blocked"]


#: Closed enum of structural halt reasons surfaced through
#: :class:`TransitionDecision` (halt branch) and the
#: ``state-transition-halted`` orchestrator-event class. Mirrors the
#: ``halt_reason`` enum in ``schemas/orchestrator-event.yaml``'s
#: ``state-transition-halted`` ``oneOf:`` branch verbatim per Pattern 1's
#: identifier-value kebab-case rule.
HaltReason = Literal[
    "non-pass-envelope",
    "attempted-backward-transition",
    "attempted-skip-transition",
]


#: The closed forward-transition map. Four entries; ``done`` is
#: intentionally absent from the keys (terminal); ``escalated`` is
#: intentionally absent from BOTH keys and values (reached via Story
#: 5.6's ``escalation-fired`` event class, NOT via a state-transition).
#: Source-of-truth for the lifecycle vocabulary;
#: :data:`schemas/run-state.yaml` and
#: :data:`schemas/orchestrator-event.yaml` enums must remain a
#: superset.
LIFECYCLE_TRANSITIONS: dict[CurrentState, CurrentState] = {
    "ready-for-dev": "in-progress",
    "in-progress": "review",
    "review": "qa",
    "qa": "done",
}


#: States from which no forward transition exists. ``done`` is the
#: lifecycle's natural leaf; ``escalated`` is the retry-budget-
#: exhaustion non-advance state per FR14, reached via
#: ``escalation-fired`` (Story 5.6), not via :func:`commit_transition`.
#: Story 2.7's Stop hook consumes this predicate to choose merge-ready
#: vs escalation bundle.
TERMINAL_STATES: frozenset[CurrentState] = frozenset({"done", "escalated"})


#: Closed lifecycle-state → next-specialist map. Keys MUST equal
#: ``LIFECYCLE_TRANSITIONS.keys() | TERMINAL_STATES`` — enforced by the
#: module-import-time assertion below and re-checked by
#: ``test_next_specialist_map_keys_equal_lifecycle_union`` so adding a new
#: lifecycle state without updating this map fails loud (Story 2.4's
#: lifecycle-extension protocol). Consolidated here in Story 22.5 (the H1
#: cleanup-window promotion) from two byte-identical private copies in
#: ``session_start_reattach`` and ``resume_command`` — the third-consumer
#: threshold the ``session_start_reattach`` TODO named.
#:
#: Mapping rationale (resume/reattach re-enter at the named dispatch boundary):
#:   * ``ready-for-dev → "dev"`` — dev is the first specialist.
#:   * ``in-progress → "review-bmad"`` — dev has run; review is next.
#:   * ``review → "qa"`` — review has run; QA is next.
#:   * ``qa → "qa"`` — QA is in-flight (dispatched but not advanced); re-dispatch.
#:   * ``done`` / ``escalated → None`` — terminal; no dispatch needed.
NEXT_SPECIALIST_BY_STATE: Final[
    dict[CurrentState, Literal["dev", "review-bmad", "qa"] | None]
] = {
    "ready-for-dev": "dev",
    "in-progress": "review-bmad",
    "review": "qa",
    "qa": "qa",
    "done": None,
    "escalated": None,
}

#: Module-import-time structural-equality invariant per AC-4 (the cross-module
#: consistency witness preserved from the former ``resume_command`` copy).
assert set(NEXT_SPECIALIST_BY_STATE.keys()) == (
    set(LIFECYCLE_TRANSITIONS.keys()) | TERMINAL_STATES
), (
    "NEXT_SPECIALIST_BY_STATE keys MUST equal "
    "LIFECYCLE_TRANSITIONS.keys() | TERMINAL_STATES per AC-4"
)


#: Type alias for the orchestrator-event log appender callback. A
#: callable accepting one schema-validated event dict and persisting
#: it to whatever log surface the caller owns. The substrate invokes
#: this callable once per emitted event AFTER any composed
#: :func:`advance_run_state` has succeeded; on failure paths the
#: callable is NOT invoked (the state-transition event is not emitted
#: on failed transitions).
EventLogAppender = Callable[[dict[str, Any]], None]


class _AdvanceDecision(BaseModel):
    """Advance branch of :class:`TransitionDecision` discriminated union.

    The state machine produced an ``advance`` decision: the caller MUST
    invoke :func:`commit_transition` to execute the transition (which
    will validate and write through :func:`advance_run_state`).
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["advance"] = "advance"
    next_state: CurrentState


class _HaltDecision(BaseModel):
    """Halt branch of :class:`TransitionDecision` discriminated union.

    The state machine produced a ``halt`` decision: the caller MUST
    invoke :func:`record_halt` (NOT :func:`commit_transition`) to
    record the halt; on-disk run-state is unchanged.

    ``last_envelope_status`` is non-None only when ``halt_reason ==
    "non-pass-envelope"``; structural halts (backward / skip /
    from-terminal) carry no envelope context and surface the field as
    ``None``.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["halt"] = "halt"
    halted_at_state: CurrentState
    halt_reason: HaltReason
    last_envelope_status: EnvelopeOutcome | None = None


#: Discriminated union of :func:`evaluate_envelope`'s return shape.
#: ``type: Literal["advance"]`` carries ``next_state``; ``type:
#: Literal["halt"]`` carries ``halted_at_state``, ``halt_reason``, and
#: ``last_envelope_status``.
TransitionDecision = _AdvanceDecision | _HaltDecision


class CommitTransitionResult(BaseModel):
    """Return shape of a successful :func:`commit_transition` call.

    Frozen for hashability + determinism. Carries the wrapped
    :class:`AdvanceResult` from Story 2.2's helper (so the caller has
    the wrote_path + serialized next_state in hand) and the
    ``state-transition`` event dict that was emitted via the
    ``event_log_appender`` (so the caller has the event_id + timestamp
    for correlation).

    Field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    advance_result: AdvanceResult
    emitted_event: dict[str, Any]


class RecordHaltResult(BaseModel):
    """Return shape of a successful :func:`record_halt` call.

    Frozen for hashability + determinism. Carries the
    ``state-transition-halted`` event dict that was emitted via the
    ``event_log_appender`` (so the caller has the event_id + timestamp
    for correlation). Does NOT carry an :class:`AdvanceResult` because
    no advance occurs — :func:`record_halt` does not invoke
    :func:`advance_run_state`.
    """

    model_config = ConfigDict(frozen=True)

    emitted_event: dict[str, Any]


class InvalidLifecycleTransition(Exception):
    """Raised by :func:`evaluate_envelope` (from-terminal advance) and
    :func:`commit_transition` (backward / skip / from-terminal) BEFORE
    any I/O.

    Pattern 5 named-invariant diagnostic (architecture.md lines
    983-991). Programmer error: the caller asked the state machine to
    advance in a direction the closed :data:`LIFECYCLE_TRANSITIONS`
    map does not permit.

    Distinct from ``RunStateAdvanceBlocked`` (Story 2.2's diagnostic
    for story-doc-callback rejection) and ``BranchLifecycleBlocked``
    (Story 2.3's diagnostic for trunk-allowlist / unclean-tree halts):
    those are runtime-state failures; this exception is a structural
    contract violation.

    Attributes:
        current_state: The state the caller was attempting to leave.
        attempted_next_state: The state the caller was attempting to
            advance to. ``None`` only when the rejection happened in
            :func:`evaluate_envelope` (pure-decision path) where no
            ``next_state`` argument was supplied.
        reason: Human-readable explanation distinguishing backward /
            skip / from-terminal halts. The string includes the
            actionable-fix-pointer for the diagnostic envelope.
    """

    def __init__(
        self,
        *,
        current_state: CurrentState,
        attempted_next_state: CurrentState | None,
        reason: str,
    ) -> None:
        self.current_state: CurrentState = current_state
        self.attempted_next_state: CurrentState | None = attempted_next_state
        self.reason: str = reason
        super().__init__(
            f"invalid lifecycle transition from {current_state!r} to "
            f"{attempted_next_state!r}: {reason}"
        )


def _now_isoformat() -> str:
    """Generate a UTC ISO-8601 timestamp at function-call time.

    Indirected so tests can monkey-patch via ``mock.patch.object``
    without touching ``datetime.datetime.now``. Matches the
    ``orchestrator-event.yaml`` ``timestamp`` field's ``format:
    date-time`` constraint.
    """
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _generate_event_id(prefix: str, story_id: str) -> str:
    """Generate an opaque event identifier scoped to a story.

    Format: ``ev-<story_id>-<prefix>-<token_hex>``. The
    ``token_hex(4)`` suffix gives 32 bits of collision resistance per
    event, sufficient for the per-story event volume the orchestrator
    emits. Story 1.3's seed-fixture convention (``ev-1-3-seed-0001``)
    is for hand-authored fixtures; runtime-emitted events use this
    randomized form so concurrent emissions cannot collide.
    """
    return f"ev-{story_id}-{prefix}-{secrets.token_hex(4)}"


def _construct_state_transition_event(
    *,
    current_state: RunState,
    next_state: RunState,
) -> dict[str, Any]:
    """Build a ``state-transition`` event payload.

    Required fields per ``schemas/orchestrator-event.yaml`` lines
    176-205: ``event_class``, ``event_id``, ``timestamp``,
    ``story_id``, ``from_state``, ``to_state``. The ``story_id`` is
    derived from the ``next_state`` (the post-transition canonical
    record).
    """
    return {
        "event_class": "state-transition",
        "event_id": _generate_event_id("st", next_state.story_id),
        "timestamp": _now_isoformat(),
        "story_id": next_state.story_id,
        "from_state": current_state.current_state,
        "to_state": next_state.current_state,
    }


def _construct_state_transition_halted_event(
    *,
    current_state: RunState,
    halt_reason: HaltReason,
    triggering_specialist: DispatchedSpecialist | None,
    last_envelope_status: EnvelopeOutcome | None,
) -> dict[str, Any]:
    """Build a ``state-transition-halted`` event payload.

    Required fields per ``schemas/orchestrator-event.yaml``'s
    ``state-transition-halted`` ``oneOf:`` branch (added by AC-4 of
    this story): ``event_class``, ``event_id``, ``timestamp``,
    ``story_id``, ``halted_at_state``, ``halt_reason``. Optional
    fields: ``triggering_specialist``, ``last_envelope_status``;
    omitted from the payload when the corresponding parameter is
    ``None`` (matches the schema's ``oneOf: […, { type: "null" }]``
    nullable form by simply absenting the key, which the
    ``additionalProperties: false`` per-branch contract permits since
    the field is not in the ``required`` list).
    """
    payload: dict[str, Any] = {
        "event_class": "state-transition-halted",
        "event_id": _generate_event_id("sth", current_state.story_id),
        "timestamp": _now_isoformat(),
        "story_id": current_state.story_id,
        "halted_at_state": current_state.current_state,
        "halt_reason": halt_reason,
    }
    if triggering_specialist is not None:
        payload["triggering_specialist"] = triggering_specialist
    if last_envelope_status is not None:
        payload["last_envelope_status"] = last_envelope_status
    return payload


def evaluate_envelope(
    current_state: CurrentState,
    specialist: DispatchedSpecialist,
    envelope_outcome: EnvelopeOutcome,
) -> TransitionDecision:
    """Decide whether to advance or halt given a current state and a
    specialist envelope outcome.

    Pure decision; no I/O; no side effects. The caller (Story 2.5+)
    invokes this AFTER a specialist returns, switches on the
    discriminator, and routes to :func:`commit_transition` (advance
    branch) or :func:`record_halt` (halt branch).

    Decision logic:
        * If ``current_state`` is in :data:`TERMINAL_STATES` — raise
          :exc:`InvalidLifecycleTransition` regardless of outcome.
          Calling this function from a terminal state is always
          programmer error: AC-4 states "halts at ``escalated`` are
          not state-machine halts" and ``done`` has no remaining
          specialist work. The terminal guard fires first to prevent
          schema-invalid ``state-transition-halted`` events (the
          schema's ``halted_at_state`` enum excludes ``escalated``).
        * If ``envelope_outcome == "pass"`` AND ``current_state`` is a
          key in :data:`LIFECYCLE_TRANSITIONS` — return advance branch
          with ``next_state = LIFECYCLE_TRANSITIONS[current_state]``.
        * If ``envelope_outcome != "pass"`` — return halt branch with
          ``halt_reason="non-pass-envelope"`` and
          ``last_envelope_status=envelope_outcome``.

    Args:
        current_state: The lifecycle state the orchestrator is
            currently at (read from ``run_state.current_state``).
            Must NOT be a terminal state (``"done"`` or
            ``"escalated"``); passing a terminal state is programmer
            error and raises immediately.
        specialist: The specialist whose envelope is being evaluated.
            Surfaced for caller-side correlation; the decision logic
            does NOT branch on specialist identity.
        envelope_outcome: The envelope's ``status`` field. One of
            ``pass``, ``fail``, ``decision-needed``, ``blocked``.

    Returns:
        :class:`TransitionDecision` (discriminated union): advance
        branch on pass; halt branch on non-pass.

    Raises:
        InvalidLifecycleTransition: ``current_state`` is a terminal
            state. Calling from a terminal state is always programmer
            error regardless of envelope outcome.
    """
    # ``specialist`` is unused in the decision logic but accepted
    # in the signature so callers can pass envelope context
    # through uniformly (sensor-not-advisor: the substrate doesn't
    # branch on specialist identity).
    _ = specialist

    # Terminal guard fires first — before the non-pass branch — so
    # that a non-pass envelope from a terminal state raises rather
    # than producing a schema-invalid halt event (the schema's
    # halted_at_state enum excludes "escalated").
    if current_state in TERMINAL_STATES:
        raise InvalidLifecycleTransition(
            current_state=current_state,
            attempted_next_state=None,
            reason=(
                f"terminal state has no forward transition: "
                f"{current_state!r} is a leaf — evaluate_envelope "
                f"must not be called from terminal states"
            ),
        )

    if envelope_outcome != "pass":
        return _HaltDecision(
            halted_at_state=current_state,
            halt_reason="non-pass-envelope",
            last_envelope_status=envelope_outcome,
        )

    # current_state is non-terminal AND outcome is pass.
    # Closed map guarantees a hit since TERMINAL_STATES is the
    # complement of LIFECYCLE_TRANSITIONS.keys().
    return _AdvanceDecision(next_state=LIFECYCLE_TRANSITIONS[current_state])


def commit_transition(
    run_state_path: pathlib.Path,
    current_state: RunState,
    next_state: RunState,
    *,
    story_doc_callback: StoryDocCallback,
    event_log_appender: EventLogAppender,
) -> CommitTransitionResult:
    """Commit a forward lifecycle transition: validate → advance run-
    state via Story 2.2's helper → emit state-transition event.

    Execution order (load-bearing per AC-3):

        1. Validate ``next_state.current_state ==
           LIFECYCLE_TRANSITIONS[current_state.current_state]``.
           Raise :exc:`InvalidLifecycleTransition` if not (rejects
           backward, skip, from-terminal). NO I/O is performed
           before this check passes.
        2. Construct the ``state-transition`` event payload.
        3. Invoke :func:`advance_run_state` with the supplied
           ``run_state_path``, ``next_state``, and
           ``story_doc_callback``. This is the SOLE write path to
           ``run_state_path``; the substrate does NOT call
           :func:`pathlib.Path.write_text`, ``open()`` for write,
           ``os.replace``, ``os.fsync``, or any low-level I/O against
           the path under any code path.
        4. On success of ``advance_run_state``, invoke
           ``event_log_appender(state_transition_event)`` to append
           the event to the orchestrator-event log. If
           ``advance_run_state`` raises (whether
           :exc:`loud_fail_harness.run_state.RunStateAdvanceBlocked`,
           :exc:`OSError`, or any other exception), the event is NOT
           emitted; the exception propagates to the caller unchanged.
        5. Return :class:`CommitTransitionResult` with the
           ``advance_result`` and the ``emitted_event``.

    The ``story_doc_callback`` and ``event_log_appender`` parameters
    are **keyword-only** (the ``*,`` separator) AND **non-defaulted**
    (no ``= None`` fallback) so omitting either is a ``TypeError`` at
    call time per Python's missing-required-keyword-argument
    semantics. There is no API path that writes a transition without
    supplying both callbacks — the protocol is structural, not
    documented-only.

    Args:
        run_state_path: Caller-controlled on-disk path of the run-
            state file. Passed through to :func:`advance_run_state`.
        current_state: The :class:`RunState` instance representing
            the pre-transition state. Read for ``story_id`` (event-
            payload field) and ``current_state`` (forward-validation
            check).
        next_state: The :class:`RunState` instance representing the
            post-transition state. The ``current_state`` field MUST
            equal ``LIFECYCLE_TRANSITIONS[current_state.current_state]``
            or :exc:`InvalidLifecycleTransition` is raised.
        story_doc_callback: Forwarded verbatim to
            :func:`advance_run_state` per Story 2.2's contract; see
            its docstring for the canonical pattern. The substrate
            does NOT wrap, decorate, transform, or replace this
            callback.
        event_log_appender: The orchestrator-event log appender. The
            substrate invokes this exactly once on the success path
            (after :func:`advance_run_state` returns); never on the
            failure path.

    Returns:
        :class:`CommitTransitionResult` carrying the
        :class:`AdvanceResult` from Story 2.2's helper and the
        ``state-transition`` event dict that was emitted.

    Raises:
        InvalidLifecycleTransition: The proposed forward transition
            does not appear in :data:`LIFECYCLE_TRANSITIONS`
            (backward / skip / from-terminal). Run-state on disk is
            unchanged; no event is emitted.
        loud_fail_harness.run_state.RunStateAdvanceBlocked: The
            story-doc callback failed (raised OR returned
            ``accepted=False``). Run-state on disk is unchanged; no
            event is emitted. The exception's ``cause`` carries the
            upstream signal for the caller's marker emission.
        OSError: The temp-write or atomic-rename inside
            :func:`advance_run_state` failed at the OS layer. Run-
            state on disk is unchanged (per :func:`advance_run_state`
            cleanup semantics); no event is emitted.
    """
    expected_next = LIFECYCLE_TRANSITIONS.get(current_state.current_state)

    if expected_next is None:
        # current_state is terminal; no forward transition exists.
        raise InvalidLifecycleTransition(
            current_state=current_state.current_state,
            attempted_next_state=next_state.current_state,
            reason=(
                "terminal state has no forward transition: state machine "
                "is at a leaf"
            ),
        )

    if next_state.current_state != expected_next:
        # Either backward, skip, or an invalid target; distinguish for
        # the diagnostic.
        chain = ["ready-for-dev", "in-progress", "review", "qa", "done"]
        if next_state.current_state in chain:
            # next_state is somewhere in the linear lifecycle vocabulary;
            # decide backward vs skip by index.
            cur_ix = chain.index(current_state.current_state)
            nxt_ix = chain.index(next_state.current_state)
            if nxt_ix <= cur_ix:
                reason = (
                    "backward transition rejected: lifecycle is "
                    "forward-only"
                )
            else:
                reason = (
                    "skip transition rejected: only adjacent forward "
                    "transitions allowed"
                )
        else:
            # next_state is outside the linear lifecycle chain.
            # "escalated" is the primary example: reachable only via
            # the escalation-fired event class in Story 5.6, NOT via
            # commit_transition.
            reason = (
                f"invalid target state {next_state.current_state!r}: "
                f"not a valid state-transition target; "
                f"'escalated' is reachable only via the "
                f"escalation-fired event class (Story 5.6)"
            )

        raise InvalidLifecycleTransition(
            current_state=current_state.current_state,
            attempted_next_state=next_state.current_state,
            reason=reason,
        )

    # Forward-validation passed. Construct the event payload BEFORE
    # invoking advance_run_state so the same wall-clock timestamp
    # roughly correlates with the on-disk write (the helper's
    # internal fsync may take milliseconds; any slop is acceptable
    # for diagnostic correlation).
    event = _construct_state_transition_event(
        current_state=current_state, next_state=next_state
    )

    advance_result = advance_run_state(
        run_state_path=run_state_path,
        next_state=next_state,
        story_doc_callback=story_doc_callback,
    )

    # advance_run_state succeeded; emit the event AFTER the state is
    # on disk so a downstream consumer reading the event log can
    # rely on run-state being already advanced.
    event_log_appender(event)

    return CommitTransitionResult(
        advance_result=advance_result, emitted_event=event
    )


def record_halt(
    run_state_path: pathlib.Path,
    current_state: RunState,
    specialist: DispatchedSpecialist | None,
    halt_reason: HaltReason,
    *,
    event_log_appender: EventLogAppender,
    last_envelope_status: EnvelopeOutcome | None = None,
) -> RecordHaltResult:
    """Record a non-pass / structural halt: emit the
    ``state-transition-halted`` event; DO NOT touch run-state.

    Execution order:

        1. Construct the ``state-transition-halted`` event payload.
        2. Invoke ``event_log_appender(halt_event)``.
        3. Return :class:`RecordHaltResult` with the emitted event.

    The function does NOT call :func:`advance_run_state`, does NOT
    write to ``run_state_path``, does NOT modify on-disk run-state in
    any way. FR6 verbatim: "halts state advancement when a specialist
    returns non-pass status" — halts do not advance. The on-disk
    ``current_state`` remains as the caller passed in
    ``current_state.current_state``; the visibility of the halt is
    via the event log, not by moving the lifecycle pointer.

    The ``run_state_path`` parameter is accepted but UNUSED (the
    helper performs no I/O against it); it is preserved in the
    signature for symmetry with :func:`commit_transition` and so that
    future Story 8.x recovery extensions can repurpose the parameter
    without breaking the existing caller contract.

    The ``event_log_appender`` parameter is **keyword-only** AND
    **non-defaulted** so omitting it is a ``TypeError`` at call time.
    The ``last_envelope_status`` parameter is keyword-only with
    ``None`` default (acceptable because structural halts —
    ``halt_reason="attempted-backward-transition"`` and
    ``"attempted-skip-transition"`` — legitimately have no envelope
    context, so a non-defaulted required keyword would be the wrong
    shape).

    Args:
        run_state_path: Accepted for signature symmetry; unused
            internally (no I/O performed against the path).
        current_state: The :class:`RunState` instance representing
            the lifecycle state the halt is recorded at. Read for
            ``story_id`` and ``current_state`` (event-payload
            fields).
        specialist: The specialist whose envelope (if any) triggered
            the halt. ``None`` for structural halts (backward /
            skip) where no specialist is the proximate cause.
        halt_reason: One of ``non-pass-envelope`` /
            ``attempted-backward-transition`` /
            ``attempted-skip-transition``. The structural-vs-runtime
            distinction is encoded here.
        event_log_appender: The orchestrator-event log appender.
            Invoked exactly once with the halt event payload.
        last_envelope_status: The envelope ``status`` field that
            triggered the halt; ``None`` for structural halts.

    Returns:
        :class:`RecordHaltResult` carrying the emitted event dict.
    """
    _ = run_state_path  # accepted for signature symmetry; unused.

    halt_event = _construct_state_transition_halted_event(
        current_state=current_state,
        halt_reason=halt_reason,
        triggering_specialist=specialist,
        last_envelope_status=last_envelope_status,
    )
    event_log_appender(halt_event)

    return RecordHaltResult(emitted_event=halt_event)


__all__ = [
    "evaluate_envelope",
    "commit_transition",
    "record_halt",
    "LIFECYCLE_TRANSITIONS",
    "NEXT_SPECIALIST_BY_STATE",
    "TERMINAL_STATES",
    "TransitionDecision",
    "EnvelopeOutcome",
    "HaltReason",
    "EventLogAppender",
    "CommitTransitionResult",
    "RecordHaltResult",
    "InvalidLifecycleTransition",
]
