"""Orchestrator story-loop entry sequence (story 2.5). FR1 + FR4 + FR5 + NFR-R8.

Architectural placement (story 1.10b precedent + story 2.2 precedent + story
2.3 precedent + story 2.4 precedent): this module is a sibling of
:mod:`loud_fail_harness.story_doc_validator`,
:mod:`loud_fail_harness.run_state`,
:mod:`loud_fail_harness.branch_lifecycle`, and
:mod:`loud_fail_harness.lifecycle_state_machine` — the substrate-library
cohort. It is **NOT a sixth substrate component**. ADR-003 Consequence 1
enumerates exactly five substrate components (architecture.md lines 311-315);
this module is a substrate **library** consumed by Stories 2.6, 2.7, 2.11,
2.12, 2.13 and Phase 1.5+ specialist subagents at runtime to compose the
six-step ``/bmad-automation run <story-id>`` entry sequence per
:doc:`epics.md#Story-2.5` line 1293. The substrate-component count stays at
FIVE; the harness module count grows.

Closer in shape to :mod:`run_state` and :mod:`lifecycle_state_machine` than
to the directory-scanning CI gates (``pluggability_gate.py``,
``hook_budget_gate.py``): there is no canonical filesystem surface to scan
because the entry sequence runs at orchestrator runtime in Epic 2+, not as
committed filesystem artifacts on disk.

What this library provides:
    * **Public function** :func:`run_story_loop_entry` — the SOLE entry
      seam for ``/bmad-automation run <story-id>``; structurally encodes
      the six-step AC-2 entry sequence (locate → validate → branch → init
      run-state → commit transition → dispatch); composes Story 2.2's
      :func:`advance_run_state` + Story 2.3's :func:`create_story_branch` +
      Story 2.4's :func:`commit_transition` exclusively (no direct
      ``run-state.yaml`` writes; no inline ``git`` invocations; no inline
      lifecycle-transition map duplication).
    * **Default resolvers** :func:`default_story_doc_resolver` and
      :func:`default_sprint_status_resolver` — the canonical resolvers the
      orchestrator skill at user runtime hands to
      :func:`run_story_loop_entry`; tests inject deterministic stubs.
    * **Default dispatch stub** :func:`default_dispatch_callback` — a no-op
      stub that returns ``DispatchCallbackResult(dispatched=False,
      reason="dispatch stubbed pending Story 2.6")`` and emits a
      ``dispatch-stubbed`` diagnostic via the standard library logging
      module (NOT via the event_log_appender — see "Why the dispatch stub
      uses logging.info" below). Story 2.6 replaces the stub at the call
      site with a real ``TaskToolDispatchCallback``; the entry sequence
      stays unchanged.
    * **Pydantic v2 frozen models** :class:`StoryDocResolution`,
      :class:`AcceptanceCriterion`, :class:`SprintStatusResolution`,
      :class:`DispatchCallbackResult`, :class:`RunStoryLoopEntryResult` —
      Pattern 4 state-update discipline + Epic 1 retro Action #2 (sequence
      fields are ``tuple[…]``, NOT ``list[…]``).
    * **Named-invariant exception classes** :class:`StoryDocNotFound`,
      :class:`StoryDocMalformed`, :class:`StoryDocLifecycleStateMismatch`,
      :class:`SprintStatusMismatch` — Pattern 5 named-invariant diagnostic
      per architecture.md lines 983-991. Each class pins
      ``marker_class: ClassVar[None] = None`` as a structural commitment
      that precondition halts are NOT loud-fail markers (see "Precondition
      halts vs. runtime markers" below).

What this library enforces:
    * **FR1** (PRD line 809) — "Practitioner can run a ready-for-dev story
      through the complete Dev → Review → QA → merge-ready loop via a
      single slash command (``/bmad-automation run <story-id>``)." This
      module IS the structural realization of FR1's entry mechanism; the
      post-dispatch loop (Stories 2.6+) realizes the rest.
    * **FR4** (PRD line 812) — orchestrator manages a per-story branch
      with a documented naming convention. Encoded structurally as
      :func:`run_story_loop_entry` step (3) composing
      :func:`create_story_branch` exclusively.
    * **FR5** (PRD line 813) — orchestrator transitions through BMAD
      lifecycle states. Encoded structurally as step (5) composing
      :func:`commit_transition` for the
      ``ready-for-dev → in-progress`` transition.
    * **FR45** (PRD line 873) — orchestrator persists ephemeral run state
      at ``_bmad/automation/run-state.yaml``. Step (4) initializes the
      run-state via :func:`advance_run_state` (with a no-op story-doc
      callback per "Why init uses a no-op story-doc callback" below).
    * **FR62** (PRD line 897) — pluggability no-cross-references. See
      "FR62 pluggability classification" below.
    * **NFR-R8** (PRD line 952) — cross-state consistency: story-doc
      writes complete before run-state advances. Step (5)'s
      :func:`commit_transition` composes :func:`advance_run_state` (whose
      keyword-only-non-defaulted ``story_doc_callback`` enforces the
      ordering at the substrate layer); inherited verbatim.
    * **NFR-S3** (PRD line 971) — git operation scope. Step (3) composes
      :func:`create_story_branch`; trunk-allowlist + clean-tree-probe
      protocol inherited verbatim. The entry sequence does NOT call
      ``subprocess`` directly under any code path.
    * **NFR-O5** (PRD line 984) — named diagnostic per failure class. The
      four named-invariant exceptions discharge precondition violations
      with structured ``story_id`` + ``observed_state`` + ``path`` +
      ``expected_state`` fields.
    * **Pattern 4** (architecture.md lines 973-981) — "All run-state
      writes go through atomic-write helpers. No direct writes to
      ``run-state.yaml`` outside the helper layer." This module composes
      that helper layer exclusively; it does not bypass it.
    * **Pattern 5** (architecture.md lines 983-991) — named-invariant
      diagnostic. The four precondition exceptions surface up-front
      state-misalignment halts; runtime-degradation markers fire from
      downstream seams (Story 2.6+), NOT from this entry sequence.
    * **ADR-001** (architecture.md lines 31-95) — the orchestrator skill
      IS the binding to Claude Code's skill primitive; the portable
      orchestrator surface is ``(orchestrator-prompt-logic, run-state.yaml
      schema, orchestrator-event.yaml, specialist-envelope schema)``. This
      module IS the canonical Python composition the orchestrator skill's
      ``workflow.md`` + ``steps/run.md`` prose names verbatim.
    * **ADR-005 Sub-decision (c)** (architecture.md lines 429-541) — the
      story doc + event log are the recovery sources of truth; run-state
      is reconstructable. This module's step (4) initializes run-state
      with a no-op story-doc callback because the story doc already
      exists per step (1)'s locate; the post-recovery scenario is NOT
      this story's concern (lands in Story 8.1's SessionStart
      reattachment).

## The six-step entry sequence

:func:`run_story_loop_entry` executes in two phases per AC-3:

**Pre-flight phase** (steps 1-2: locate + validate). Performs ZERO side
effects (no branch creation, no file writes, no event emissions, no
dispatch). Surfaces precondition violations via the four named-invariant
exceptions BEFORE any commit-phase step runs.

**Commit phase** (steps 3-6: branch + init run-state + advance + dispatch).
Performs side effects in the documented order; each step composes a
substrate helper exclusively (no inline duplication).

Step-by-step (load-bearing per AC-2):

    1. **Locate** — invoke ``story_doc_resolver(story_id, project_root)``
       returning :class:`StoryDocResolution`. If the resolver returns
       ``None`` OR raises :class:`StoryDocNotFound`, propagate
       :class:`StoryDocNotFound` BEFORE invoking ANY other step.
    2. **Validate** — assert ``resolution.current_state ==
       "ready-for-dev"``; raise :class:`StoryDocLifecycleStateMismatch` if
       not. Also invoke
       ``sprint_status_resolver(story_id, project_root)`` returning
       :class:`SprintStatusResolution`; raise
       :class:`SprintStatusMismatch` if its ``current_state`` is not in
       ``{"ready-for-dev", "backlog"}``. Both checks BEFORE any
       commit-phase step.
    3. **Branch** — invoke :func:`create_story_branch` (Story 2.3's
       helper). Propagate :class:`BranchLifecycleBlocked` (and its
       subclasses) unchanged.
    4. **Init run-state** — construct an initial :class:`RunState` with
       ``current_state="ready-for-dev"``; invoke :func:`advance_run_state`
       with the module-private :func:`_no_op_story_doc_callback` (the
       canonical "init from nothing" composition; the story doc already
       exists per step (1) so no story-doc write is needed at init time).
    5. **Advance to in-progress** — construct ``next_state`` with
       ``current_state="in-progress"``; invoke :func:`commit_transition`
       (Story 2.4's helper) with the supplied
       ``story_doc_callback_factory(story_id)`` (NOT the no-op — the
       lifecycle transition requires a real story-doc write per Pattern 4
       / NFR-R8) and the supplied ``event_log_appender``. Propagate
       :class:`RunStateAdvanceBlocked`,
       :class:`InvalidLifecycleTransition`, :class:`OSError` unchanged.
    6. **Dispatch** — invoke ``dispatch_callback(specialist="dev",
       story_id=..., run_state_path=..., story_doc_resolution=...,
       event_log_appender=...)`` returning
       :class:`DispatchCallbackResult`. Story 2.6 replaces the default
       stub with a real ``TaskToolDispatchCallback``; the entry
       sequence's call site does NOT change.

## Composition with Story 2.2 / 2.3 / 2.4 substrates

Per AC-4, composition is *exclusive*:

    * :func:`create_story_branch` invoked exactly once at step 3; the
      ``trunk_allowlist`` and ``working_tree_probe`` parameters are
      forwarded VERBATIM from :func:`run_story_loop_entry`'s caller (no
      wrapping, no decoration, no transformation).
    * :func:`advance_run_state` invoked exactly once at step 4 (the init
      call) AND exactly once internally inside :func:`commit_transition`
      at step 5 (the advance call) — for a total of two invocations per
      successful run.
    * :func:`commit_transition` invoked exactly once at step 5; the
      ``event_log_appender`` parameter is forwarded VERBATIM from the
      caller.
    * :func:`evaluate_envelope` invoked ZERO times — the entry sequence
      is one-time-per-run and goes from ``ready-for-dev`` directly to
      ``in-progress``; there is no envelope to evaluate at this point.
      Future Stories 2.6+ wire :func:`evaluate_envelope` at the
      post-dispatch seam.

The module does NOT call ``pathlib.Path.write_text``, ``open`` for write,
``os.replace``, ``os.fsync``, or any other direct file-write primitive
against ``run_state_path`` under any code path; verified by AC-5 mock-
based absence assertions.

The module does NOT import ``subprocess``; all git operations route
through :func:`create_story_branch`. Verified by AC-5's
``test_no_inline_subprocess_run``.

The module does NOT redeclare or duplicate the lifecycle-transition map
(:data:`LIFECYCLE_TRANSITIONS` from :mod:`lifecycle_state_machine` is the
single source of truth); the import is referenced in diagnostic strings
to satisfy the no-inline-lifecycle-map invariant. Verified by AC-5's
``test_no_inline_lifecycle_map``.

## Why init uses a no-op story-doc callback

Pattern 4 (architecture.md line 977) verbatim — "All run-state writes go
through atomic-write helpers." The init at step 4 must therefore route
through :func:`advance_run_state`. But :func:`advance_run_state` requires
a non-defaulted ``story_doc_callback`` per its keyword-only API surface
(NFR-R8 enforcement: callback first → run-state second).

At the entry-sequence's init seam, there is no story-doc edit to perform
— the story doc already exists per step (1)'s locate; the lifecycle field
in the doc is being read (``ready-for-dev``), not written. The story-doc
write happens at step (5)'s advance (``ready-for-dev → in-progress``),
where the ``commit_transition`` call uses the caller-supplied
``story_doc_callback_factory(story_id)`` callback to perform the field
update.

Solution: a module-private :func:`_no_op_story_doc_callback` returning
``StoryDocCallbackResult(accepted=True, reason="initial run-state write
— no story-doc edit needed at init time")``. This preserves the
structural invariant that ALL run-state writes route through
:func:`advance_run_state` (Pattern 4 verbatim) while accommodating the
specific case where there is no story-doc edit at init time.

The no-op callback is **module-private** (underscore-prefixed; NOT in
:data:`__all__`) — it is an internal composition detail, NOT a
generalized API. Future stories that need a similar pattern (e.g.,
Story 8.1's SessionStart reattachment may construct an in-memory
``RunState`` from story-doc + event-log per ADR-005's recovery
algorithm) compose :func:`advance_run_state` themselves with their own
no-op callback rather than depending on this module's internal symbol;
this prevents the no-op pattern from leaking as a generalized API.

## Why ``_no_op_story_doc_callback`` is module-private

Two considered alternatives (story 2.5 design notes):

    * **Alternative A — Export ``no_op_story_doc_callback`` as a
      generalized "init from nothing" helper.** Rejected: future
      stories that need a similar pattern should think through whether
      their case really needs a no-op or a real callback; an exported
      helper makes the no-op feel like the default, which it is not.
    * **Alternative B (chosen) — Module-private
      ``_no_op_story_doc_callback`` documented in this section.** Keeps
      the no-op pattern scoped to this story's specific composition;
      future callers fork the pattern intentionally rather than
      inheriting it accidentally.

## Precondition halts vs. runtime markers

The loud-fail doctrine (Pattern 5; ADR-003 substrate-component closure)
distinguishes two failure surfaces:

    * **Runtime degradation markers** — fire at runtime when a known
      dependency is unavailable, a heuristic is skipped, a layer fails,
      a hook fails, a specialist times out. Every entry in
      ``schemas/marker-taxonomy.yaml`` is a runtime marker. They surface
      in the PR bundle's loud-fail block per FR31 / FR32.
    * **Up-front precondition diagnostics** — fire at the entry seam
      when the practitioner's command cannot proceed because the
      project's state doesn't match the contract. They surface in the
      orchestrator skill's terminal stream per NFR-O1 (the practitioner
      sees the diagnostic immediately); they do NOT surface in a PR
      bundle (no PR bundle is produced when the entry sequence halts at
      pre-flight).

The four precondition exceptions (:class:`StoryDocNotFound`,
:class:`StoryDocMalformed`, :class:`StoryDocLifecycleStateMismatch`,
:class:`SprintStatusMismatch`) carry ``marker_class: ClassVar[None] =
None`` as a structural commitment that future Stories 6.x do NOT scan
these exception classes when assembling the loud-fail block.

This distinction prevents conflating two architecturally distinct
failure modes (Pattern 5 sensor-not-advisor + ADR-003 closure):
synthesizing marker classes for precondition violations would (a)
require adding entries to ``marker-taxonomy.yaml`` with no FR/NFR
backing, (b) require synthetic-story fixtures (Layer C coverage per
ADR-003) for failure modes that are not really runtime failures, (c)
confuse Stories 6.x's loud-fail-block consumer about whether to render
the marker (no PR bundle is produced when the entry sequence halts).

## Consuming TransitionDecision's discriminator

(Story 2.4 deferred-work item #5 honored verbatim per
``deferred-work.md`` line 131.)

Callers of :func:`evaluate_envelope` (Stories 2.6+) MUST switch on
``decision.type`` (``Literal["advance"]`` or ``Literal["halt"]``), NOT
use ``isinstance(decision, _AdvanceDecision)`` or
``isinstance(decision, _HaltDecision)`` — the union-branch classes are
private (``_``-prefixed) per :mod:`lifecycle_state_machine`'s
convention; only ``decision.type`` is part of the stable public API. The
canonical pattern::

    from loud_fail_harness.lifecycle_state_machine import evaluate_envelope

    decision = evaluate_envelope(current_state, specialist, envelope_outcome)
    if decision.type == "advance":
        # decision.next_state available; route to commit_transition
        ...
    elif decision.type == "halt":
        # decision.halted_at_state, decision.halt_reason,
        # decision.last_envelope_status available; route to record_halt
        ...

This module does NOT consume the discriminator at this story's seam (the
entry sequence has no envelope to evaluate); the documentation lives
here to be the canonical reference for Story 2.6's wiring at the
post-dispatch seam.

## Why ``story_id`` consistency is structurally enforced

(Story 2.4 deferred-work item #4 honored verbatim per
``deferred-work.md`` line 130.)

:func:`run_story_loop_entry` threads the ``story_id`` parameter into
BOTH the initial :class:`RunState` (step 4) AND the post-advance
:class:`RunState` (step 5) via the same variable reference (no implicit
conversion, no string transformation). A defensive assertion immediately
before invoking :func:`commit_transition` at step 5 verifies
``initial_run_state.story_id == next_state.story_id == story_id``.

The ``assert`` form is acceptable here because this is a programmer-
error invariant — the assertion firing at runtime would mean the
substrate's own composition is broken, NOT a user-facing failure mode.
A failed assertion is a developer-of-the-substrate bug, not a
practitioner bug; the existing
:exc:`InvalidLifecycleTransition` does NOT cover this case (it covers
backward / skip / from-terminal, not story-id mismatch), so a separate
named-invariant exception would over-engineer for an unreachable code
path.

## Why ``dispatch_callback`` is caller-injected

Two considered alternatives (story 2.5 design notes):

    * **Alternative A — Hardcode the dispatch logic into
      :func:`run_story_loop_entry` directly (e.g., invoke the Task tool
      inline at step 6).** Rejected: couples the substrate to the Claude
      Code Task-tool primitive; tests can't simulate dispatch without
      monkey-patching the Task-tool surface; violates sensor-not-advisor
      (the substrate would be deciding HOW to dispatch, not just
      composing the entry sequence).
    * **Alternative B (chosen) — ``dispatch_callback`` is caller-
      injected; :func:`default_dispatch_callback` is a no-op stub that
      emits a diagnostic via ``logging.info``.** Chosen: the caller
      (Story 2.6's orchestrator skill at runtime) supplies the real
      ``TaskToolDispatchCallback``; tests inject deterministic stubs;
      the substrate's protocol is just "give me a callable that takes
      the dispatch context and returns a DispatchCallbackResult; I'll
      call it once at step 6". The dispatch primitive (Task tool vs.
      Agent SDK vs. future host primitives) is the caller's policy; the
      substrate's protocol stays stable. Story 2.6 replaces the stub
      with a real wrapper without touching the entry sequence's call
      site.

## Why the dispatch stub uses ``logging.info`` (and not the event log)

The default :func:`default_dispatch_callback` emits a ``dispatch-stubbed``
diagnostic via the standard library ``logging`` module rather than via
``event_log_appender``. Rationale: ``dispatch-stubbed`` is NOT an
orchestrator-event class (the schema's ``event_class`` enum lists ten
classes per ``schemas/orchestrator-event.yaml`` lines 86-94 — none is
``dispatch-stubbed``). Emitting a synthetic event with this class would
require either:

    (a) adding a new event class to the schema (out of scope per AC-8 —
        no schema modifications in this story), OR
    (b) reusing an existing class with an out-of-band ``note`` field
        (would violate the schema's ``additionalProperties: false`` per-
        branch contract), OR
    (c) emitting a ``state-transition`` event with a ``trigger: "dispatch-
        stubbed"`` field (would conflate two architecturally distinct
        signals).

``logging.info`` keeps the diagnostic visible to the practitioner (NFR-O1
terminal stream is the canonical surface for the dispatch-stub message)
without requiring schema changes. Story 2.6 replaces the stub with a
real ``TaskToolDispatchCallback`` that emits the proper
``specialist-dispatched`` event class; the stub's ``logging`` posture is
strictly a phase-2.5-of-Epic-2 trade-off.

## FR62 pluggability classification

This module is *substrate-shared library* per Story 1.10b's precedent
(``story_doc_validator.py``), Story 2.2's precedent (``run_state.py``),
Story 2.3's precedent (``branch_lifecycle.py``), Story 2.4's precedent
(``lifecycle_state_machine.py``), and ADR-003's substrate-vs-specialist
boundary; consumed by Stories 2.6, 2.7, 2.11, 2.12, 2.13, 5.1-5.9,
7.1-7.9, 8.1-8.5, and Phase 1.5+ successors. The FR62 gate (Story 1.10a's
:mod:`loud_fail_harness.pluggability_gate`) does NOT flag substrate
cross-imports; specialist subagents (Dev, Review-BMAD, QA, LAD) live in
``agents/*.md`` and the gate's no-cross-references rule applies to *that*
surface, not this one. The orchestrator skill at ``skills/bmad-automation/``
is also outside the gate's scope — it is the orchestrator-binding artifact
per ADR-001, NOT a specialist.

## Forward-compat consumers

Stories that will consume :func:`run_story_loop_entry` and the supporting
public surface:

    * Story 2.6 — Task-tool dispatch with marker emission (epics.md lines
      1309-1346): replaces :func:`default_dispatch_callback` with a real
      ``TaskToolDispatchCallback`` that constructs the specialist
      envelope, dispatches via the Task tool, validates the return, and
      feeds the envelope back through :func:`evaluate_envelope` for the
      next state-transition decision.
    * Story 2.7 — three hooks scaffolded (epics.md lines 1347-1391): Stop
      hook reads ``current_state`` from run-state via :data:`TERMINAL_STATES`
      to choose merge-ready vs escalation bundle; SubagentStop hook reads
      the run-state's ``last_envelope`` via the schema this entry sequence
      produces.
    * Story 2.11 — basic merge-ready PR bundle assembly (epics.md lines
      1482-1530): reads the orchestrator-event log this entry sequence
      produces (specifically the ``state-transition: ready-for-dev →
      in-progress`` event at step 5) to render the "what happened"
      section.
    * Story 2.12 — per-seam state streaming + per-specialist log
      persistence (epics.md lines 1532-1557): thickens the streaming
      primitive that this entry sequence emits via the
      ``event_log_appender`` callback; the callback IS the substrate seam.
    * Story 2.13 — walking-skeleton sample-story fixture (epics.md lines
      1559-1590): exercises this entry sequence end-to-end against
      ``tools/loud-fail-harness/tests/fixtures/sample-story-walking-
      skeleton.md`` once 2.6 + 2.8 land.
    * Stories 5.1 / 5.2 / 5.6 — retry budget + bucket-driven retry
      routing + retry-budget-exhaustion non-advance (epics.md lines
      2236-2422): extend the post-dispatch loop without rewriting the
      entry sequence (which is one-time-per-run from ``ready-for-dev``
      directly to ``in-progress``).
    * Stories 7.1-7.9 — installation & onboarding: thicken the ``init``
      slash-command stub from this story's literal stub into a full
      plugin-install / precondition-check / sample-scaffold flow per
      FR35-FR44.
    * Stories 8.1 / 8.3 / 8.4 / 8.5 — resumability + multi-story
      inspection: thicken the ``status`` and ``resume`` slash-command
      stubs.

## Sensor-not-advisor (PRD-level invariant + Pattern 5)

The library RAISES typed exceptions (:exc:`StoryDocNotFound`,
:exc:`StoryDocMalformed`, :exc:`StoryDocLifecycleStateMismatch`,
:exc:`SprintStatusMismatch`); it does NOT emit markers itself, does NOT
auto-correct state, does NOT log (except :func:`default_dispatch_callback`
which emits a diagnostic via ``logging.info`` per "Why the dispatch stub
uses ``logging.info``" above), does NOT print. Same posture as 1.10b /
2.2 / 2.3 / 2.4.

## ``find_repo_root()`` discipline (Epic 1 retro Action #1 resolution)

This module is **substrate-library**: callers supply ``project_root`` and
``run_state_path`` explicitly. The default resolvers
(:func:`default_story_doc_resolver`,
:func:`default_sprint_status_resolver`) accept ``project_root`` from
their caller, so neither computes :func:`find_repo_root` internally. The
module's top-level imports do NOT call :func:`find_repo_root`; tests use
fixture-time resolution per the Epic 1 retro Action #1 discipline.

## Determinism

    * All Pydantic models use ``frozen=True`` configuration; field
      declaration order is load-bearing for byte-stable
      ``model_dump_json()`` output (parallel to 2.2 / 2.3 / 2.4
      discipline).
    * Sequence-typed fields (``acceptance_criteria``) are tuple-typed
      (NOT list-typed) so ``frozen=True`` blocks BOTH attribute
      reassignment AND in-place mutation structurally per Epic 1 retro
      Action #2.
"""

from __future__ import annotations

import logging
import pathlib
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from loud_fail_harness.branch_lifecycle import (
    BranchLifecycleResult,
    WorkingTreeProbe,
    create_story_branch,
)
from loud_fail_harness.lifecycle_state_machine import (
    LIFECYCLE_TRANSITIONS,
    EventLogAppender,
    TransitionDecision,  # noqa: F401 — forward-compat for Story 2.6 (AC-4)
    _AdvanceDecision,  # noqa: F401 — forward-compat for Story 2.6 (AC-4)
    _HaltDecision,  # noqa: F401 — forward-compat for Story 2.6 (AC-4)
    commit_transition,
    evaluate_envelope,  # noqa: F401 — forward-compat for Story 2.6 (AC-4)
)
from loud_fail_harness.run_state import (
    AdvanceResult,
    CostToDateBySpecialist,
    CurrentState,
    RunState,
    StoryDocCallback,
    StoryDocCallbackResult,
    advance_run_state,
)
# Story 7.7 — type-only references at module-import time (the runtime
# imports happen lazily inside ``run_story_loop_entry`` to avoid a
# circular import: ``story_doc_version_check`` → ``marker_wiring`` →
# ``specialist_dispatch`` → ``orchestrator_run_entry``).
if TYPE_CHECKING:
    from loud_fail_harness.specialist_dispatch import MarkerClassRegistry
    from loud_fail_harness.story_doc_version_check import VersionCheckOutcome

#: Module-level logger for the dispatch-stub diagnostic. The substrate
#: emits diagnostics via ``logging.info`` only from
#: :func:`default_dispatch_callback`; the rest of the module uses
#: typed-exception raise-paths only (sensor-not-advisor — same posture
#: as 1.10b / 2.2 / 2.3 / 2.4). The logger NAME is the module's
#: ``__name__`` per stdlib convention; callers can tune verbosity via
#: standard logging configuration without monkey-patching the module.
_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Closed enums + Pydantic models                                              #
# --------------------------------------------------------------------------- #


#: Sprint-status taxonomy enum. Mirrors the ``development_status`` value
#: vocabulary documented in ``_bmad-output/implementation-artifacts/
#: sprint-status.yaml``'s header comment block (lines 9-29). Kebab-case
#: identifiers per Pattern 1.
SprintStatusState = Literal[
    "backlog",
    "ready-for-dev",
    "in-progress",
    "review",
    "done",
    "optional",
]


class AcceptanceCriterion(BaseModel):
    """One acceptance-criterion entry parsed from a story doc's
    ``## Acceptance Criteria`` section.

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``ac_id`` — the AC identifier exactly as it appears in the
          story doc heading, e.g., ``"AC-1"``, ``"AC-12a"``. Free-form
          string (BMAD convention; not regex-constrained here).
        * ``text`` — the AC heading line's text portion (everything after
          the AC identifier and the em-dash separator). Free-form string;
          surfaced for caller convenience (e.g., diagnostic rendering).
    """

    model_config = ConfigDict(frozen=True)

    ac_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class StoryDocResolution(BaseModel):
    """Result shape of :data:`StoryDocResolver` invocation.

    Frozen; sequence field is tuple-typed per Epic 1 retro Action #2.

    Field semantics:
        * ``path`` — absolute path to the story-doc markdown file as
          located by the resolver. Surfaced for caller convenience
          (e.g., diagnostic rendering, story-doc-callback construction).
        * ``current_state`` — lifecycle state parsed from the story doc's
          ``Status:`` line. The resolver normalizes the value to the
          :data:`CurrentState` taxonomy or raises :exc:`StoryDocMalformed`
          if the line is missing or unparseable.
        * ``acceptance_criteria`` — tuple of :class:`AcceptanceCriterion`
          entries parsed from the ``## Acceptance Criteria`` section.
          Possibly empty if the section exists but contains no
          identifiable AC headings (the resolver does NOT raise on empty
          AC list — that is a story-doc-content question, NOT a story-
          doc-shape question).
    """

    model_config = ConfigDict(frozen=True)

    path: pathlib.Path
    current_state: CurrentState
    acceptance_criteria: tuple[AcceptanceCriterion, ...]


class SprintStatusResolution(BaseModel):
    """Result shape of :data:`SprintStatusResolver` invocation.

    Frozen.

    Field semantics:
        * ``current_state`` — the ``development_status`` entry's value
          for the resolved story key in
          ``_bmad-output/implementation-artifacts/sprint-status.yaml``.
          Members are the kebab-case entries documented in the file's
          STATUS DEFINITIONS header (lines 9-29).
    """

    model_config = ConfigDict(frozen=True)

    current_state: SprintStatusState


class DispatchCallbackResult(BaseModel):
    """Return shape of :data:`DispatchCallback` invocation.

    Frozen.

    Field semantics:
        * ``dispatched`` — the canonical decision. ``True`` if the
          callback dispatched a specialist (Story 2.6+ real wrappers);
          ``False`` if the callback is the no-op stub
          (:func:`default_dispatch_callback` at this story's landing).
        * ``reason`` — human-readable explanation of the outcome. Free-
          form; the no-op stub emits ``"dispatch stubbed pending Story
          2.6"`` per AC-2 step (6).
    """

    model_config = ConfigDict(frozen=True)

    dispatched: bool
    reason: str | None = None


class RunStoryLoopEntryResult(BaseModel):
    """Return shape of :func:`run_story_loop_entry` on the success path.

    Frozen for hashability + determinism. Carries the wrapped results
    from each substrate composition so the caller (the orchestrator
    skill at runtime, OR Story 2.13's smoke-test fixture) has the
    "what happened" record in hand.

    Field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.

    Field semantics:
        * ``story_id`` — the BMAD story identifier the run was scoped
          to. Forwarded verbatim from :func:`run_story_loop_entry`'s
          ``story_id`` argument.
        * ``branch_lifecycle_result`` — the
          :class:`BranchLifecycleResult` returned by step (3)'s
          :func:`create_story_branch` invocation.
        * ``init_advance_result`` — the :class:`AdvanceResult` returned
          by step (4)'s direct :func:`advance_run_state` invocation.
        * ``transition_advance_result`` — the :class:`AdvanceResult`
          returned by step (5)'s :func:`commit_transition` invocation
          (extracted from the
          :class:`~loud_fail_harness.lifecycle_state_machine.CommitTransitionResult`'s
          ``advance_result`` field).
        * ``state_transition_event`` — the ``state-transition``
          orchestrator-event payload emitted by step (5)'s
          :func:`commit_transition` invocation (extracted from the
          :class:`~loud_fail_harness.lifecycle_state_machine.CommitTransitionResult`'s
          ``emitted_event`` field).
        * ``dispatch_callback_result`` — the
          :class:`DispatchCallbackResult` returned by step (6)'s
          ``dispatch_callback`` invocation.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    branch_lifecycle_result: BranchLifecycleResult
    init_advance_result: AdvanceResult
    transition_advance_result: AdvanceResult
    state_transition_event: dict[str, Any]
    dispatch_callback_result: DispatchCallbackResult


# --------------------------------------------------------------------------- #
# Resolver / factory / callback type aliases                                  #
# --------------------------------------------------------------------------- #


#: Resolver callable signature for the story-doc lookup at step 1.
#: Accepts ``(story_id, project_root)`` and returns
#: :class:`StoryDocResolution` (or raises :exc:`StoryDocNotFound` /
#: :exc:`StoryDocMalformed`).
StoryDocResolver = Callable[[str, pathlib.Path], StoryDocResolution]

#: Resolver callable signature for the sprint-status lookup at step 2.
#: Accepts ``(story_id, project_root)`` and returns
#: :class:`SprintStatusResolution` (or raises :exc:`SprintStatusMismatch`
#: when the entry is missing).
SprintStatusResolver = Callable[[str, pathlib.Path], SprintStatusResolution]

#: Factory callable signature: accepts a ``story_id`` and returns a
#: :class:`StoryDocCallback` closing over the specific story-doc path.
#: The factory shape lets the caller construct callbacks that close over
#: the resolved story-doc path rather than a globally-scoped path; the
#: factory is invoked at step 5 (NOT at module top-level; NOT at step 4)
#: because step 5 is the first step where a story-doc write is
#: structurally required.
StoryDocCallbackFactory = Callable[[str], StoryDocCallback]

#: Dispatch-callback callable signature for the specialist-dispatch seam
#: at step 6. The keyword-only signature lets future Stories 2.6+ extend
#: the kwargs without breaking the existing call site. Returns a
#: :class:`DispatchCallbackResult`.
DispatchCallback = Callable[..., DispatchCallbackResult]


# --------------------------------------------------------------------------- #
# Named-invariant exception classes                                           #
# --------------------------------------------------------------------------- #


class StoryDocNotFound(Exception):
    """Raised by :func:`run_story_loop_entry` when the
    ``story_doc_resolver`` returns ``None`` OR raises this class.

    Pattern 5 named-invariant diagnostic (architecture.md lines
    983-991): the practitioner's ``<story-id>`` doesn't match any story
    file under ``_bmad-output/implementation-artifacts/``. The
    ``__str__`` form names the failure class + an actionable-fix-pointer.

    Class attribute ``marker_class: ClassVar[None] = None`` per AC-3:
    precondition halts are NOT loud-fail markers (see "Precondition
    halts vs. runtime markers" in the module docstring).
    """

    marker_class: ClassVar[None] = None

    def __init__(
        self,
        *,
        story_id: str,
        searched_paths: tuple[pathlib.Path, ...],
    ) -> None:
        self.story_id: str = story_id
        self.searched_paths: tuple[pathlib.Path, ...] = searched_paths
        message = (
            f"StoryDocNotFound: story-id {story_id!r} did not match any "
            f"story file (searched {len(searched_paths)} path(s)); verify "
            f"the story-id matches a file under "
            f"_bmad-output/implementation-artifacts/, OR run "
            f"/bmad-automation init (Story 7) to scaffold a sample story"
        )
        super().__init__(message)


class StoryDocMalformed(Exception):
    """Raised by :func:`run_story_loop_entry` when the
    ``story_doc_resolver`` found the file but couldn't parse the
    ``Status:`` line OR the ``## Acceptance Criteria`` section was
    missing.

    Pattern 5 named-invariant diagnostic. The story-doc file is
    structurally invalid for orchestration. The ``__str__`` form names
    the failure class + an actionable-fix-pointer.

    Class attribute ``marker_class: ClassVar[None] = None`` per AC-3.
    """

    marker_class: ClassVar[None] = None

    def __init__(
        self,
        *,
        story_id: str,
        path: pathlib.Path,
        reason: str,
    ) -> None:
        self.story_id: str = story_id
        self.path: pathlib.Path = path
        self.reason: str = reason
        message = (
            f"StoryDocMalformed: story-id {story_id!r} at {path} cannot be "
            f"parsed: {reason}; verify the story-doc has a 'Status:' line "
            f"and a '## Acceptance Criteria' section per the BMAD story "
            f"template"
        )
        super().__init__(message)


class StoryDocLifecycleStateMismatch(Exception):
    """Raised by :func:`run_story_loop_entry` when the story doc parsed
    cleanly but the lifecycle state is not ``ready-for-dev``.

    Pattern 5 named-invariant diagnostic. The story is not at the
    entry-sequence's expected lifecycle state; could be ``in-progress``
    (a duplicate-run attempt), ``review`` / ``qa`` / ``done`` (the story
    is past entry), or any other state. The ``__str__`` form names the
    failure class + an actionable-fix-pointer.

    Class attribute ``marker_class: ClassVar[None] = None`` per AC-3.
    """

    marker_class: ClassVar[None] = None

    def __init__(
        self,
        *,
        story_id: str,
        observed_state: str,
        expected_state: Literal["ready-for-dev"] = "ready-for-dev",
    ) -> None:
        self.story_id: str = story_id
        self.observed_state: str = observed_state
        self.expected_state: Literal["ready-for-dev"] = expected_state
        # Reference LIFECYCLE_TRANSITIONS in the diagnostic so the import is
        # used (the no-inline-lifecycle-map invariant requires the import
        # but does NOT forbid usage in diagnostic strings).
        next_state = LIFECYCLE_TRANSITIONS.get(expected_state, "<unknown>")
        message = (
            f"StoryDocLifecycleStateMismatch: story-id {story_id!r} has "
            f"lifecycle state {observed_state!r}, expected {expected_state!r} "
            f"(would advance to {next_state!r}); if a previous run is in "
            f"flight, run /bmad-automation status {story_id} (Story 8.4) or "
            f"inspect _bmad/automation/run-state.yaml directly per NFR-O2; "
            f"if the run was abandoned, manually reset the story-doc Status "
            f"field to 'ready-for-dev' and remove the run-state file before "
            f"re-running"
        )
        super().__init__(message)


class SprintStatusMismatch(Exception):
    """Raised by :func:`run_story_loop_entry` when the story-doc
    validates but the sprint-status entry is in an inconsistent state
    (most likely a stale run that wasn't cleaned up).

    Pattern 5 named-invariant diagnostic. The two checks (story-doc
    Status line, sprint-status.yaml development_status entry) are
    independent; the entry sequence is the seam where they reconcile.
    The ``__str__`` form names the failure class + an actionable-fix-
    pointer.

    Class attribute ``marker_class: ClassVar[None] = None`` per AC-3.
    """

    marker_class: ClassVar[None] = None

    def __init__(
        self,
        *,
        story_id: str,
        observed_state: str,
        expected_states: tuple[str, ...] = ("ready-for-dev", "backlog"),
    ) -> None:
        self.story_id: str = story_id
        self.observed_state: str = observed_state
        self.expected_states: tuple[str, ...] = expected_states
        message = (
            f"SprintStatusMismatch: story-id {story_id!r} has sprint-status "
            f"{observed_state!r}, expected one of {expected_states}; "
            f"sprint-status.yaml may have been left stale by a prior crashed "
            f"run; inspect _bmad-output/implementation-artifacts/sprint-"
            f"status.yaml and reset the development_status entry to "
            f"'ready-for-dev' (or 'backlog') before re-running"
        )
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Internal composition primitives                                             #
# --------------------------------------------------------------------------- #


def _no_op_story_doc_callback() -> StoryDocCallbackResult:
    """Module-private no-op story-doc callback used at step 4's init.

    Returns ``StoryDocCallbackResult(accepted=True, reason=...)`` without
    performing any I/O. The rationale is documented in the module
    docstring's "Why init uses a no-op story-doc callback" section: the
    story doc already exists per step (1)'s locate; no story-doc write
    is structurally needed at init time; using
    :func:`advance_run_state` with a no-op callback is the canonical
    "init from nothing" composition that preserves the structural
    invariant that ALL run-state writes route through
    :func:`advance_run_state` (Pattern 4 verbatim).

    The callback is **module-private** (underscore-prefixed; NOT in
    :data:`__all__`) — see the module docstring's "Why
    ``_no_op_story_doc_callback`` is module-private" section for the
    full rationale.
    """
    return StoryDocCallbackResult(
        accepted=True,
        reason="initial run-state write — no story-doc edit needed at init time",
    )


# --------------------------------------------------------------------------- #
# Default resolvers                                                           #
# --------------------------------------------------------------------------- #


_STORY_DOC_DIR = pathlib.Path("_bmad-output") / "implementation-artifacts"
_SPRINT_STATUS_FILENAME = "sprint-status.yaml"

_STATUS_LINE_RE = re.compile(r"^Status:\s*(?P<state>\S.*?)\s*$", re.MULTILINE)
# Strip fenced code blocks (``` or ~~~) before applying _STATUS_LINE_RE so
# that `Status: in-progress` inside a code example does not trigger a false
# StoryDocLifecycleStateMismatch on a valid ready-for-dev doc.
_FENCED_CODE_BLOCK_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_AC_HEADING_RE = re.compile(
    r"^\*\*(?P<ac_id>AC-[A-Za-z0-9-]+)\s*[—–-]\s*(?P<text>.+?)\*\*\s*$",
    re.MULTILINE,
)
_AC_SECTION_HEADING = "## Acceptance Criteria"


def default_story_doc_resolver(
    story_id: str,
    project_root: pathlib.Path,
) -> StoryDocResolution:
    """Default :data:`StoryDocResolver` implementation for production.

    Globs ``<project_root>/_bmad-output/implementation-artifacts/{story_id}*.md``
    and parses the first match's ``Status:`` line + ``## Acceptance Criteria``
    section. The glob pattern uses prefix-match against the BMAD
    convention ``<epic>-<story>-<slug>.md`` so the practitioner can pass
    the short ``<epic>-<story>`` form (e.g., ``"2-5"``) at the slash
    command and the resolver finds the longer slug-based filename.

    Tests inject deterministic stubs rather than calling this default —
    the production-pathway file-system reads are unwanted in unit tests.

    Args:
        story_id: The BMAD story identifier the practitioner passed at
            ``/bmad-automation run <story-id>``. Free-form by BMAD
            convention; the resolver does not validate the format
            (validation happens at step 2's lifecycle-state check).
        project_root: Root directory under which to look for the story
            doc. Caller-supplied; the resolver does NOT compute this
            via :func:`find_repo_root`.

    Returns:
        :class:`StoryDocResolution` carrying the resolved path,
        parsed lifecycle state, and AC tuple.

    Raises:
        StoryDocNotFound: No story file matched the glob.
        StoryDocMalformed: A file matched but the ``Status:`` line could
            not be located OR the ``## Acceptance Criteria`` section
            was missing.
    """
    search_dir = project_root / _STORY_DOC_DIR
    try:
        candidates = sorted(search_dir.glob(f"{story_id}*.md"))
    except OSError:
        raise StoryDocNotFound(
            story_id=story_id,
            searched_paths=(search_dir,),
        )
    # Prefer entries matching the canonical hyphen separator (story_id-...)
    # so a short prefix like "2-5" doesn't accidentally match
    # "2-50-something.md"; the canonical naming is "<epic>-<story>-<slug>.md".
    hyphen_prefix = f"{story_id}-"
    primary = [c for c in candidates if c.name.startswith(hyphen_prefix)]
    if len(primary) > 1:
        raise StoryDocMalformed(
            story_id=story_id,
            path=primary[0],
            reason=(
                f"ambiguous: multiple story docs match '{hyphen_prefix}*': "
                f"{[c.name for c in primary]}"
            ),
        )
    canonical = primary or [
        c for c in candidates if c.name == f"{story_id}.md"
    ]
    if not canonical:
        raise StoryDocNotFound(
            story_id=story_id,
            searched_paths=(search_dir,),
        )
    path = canonical[0]
    text = path.read_text(encoding="utf-8")

    # Strip fenced code blocks before searching for the Status: line so
    # that `Status:` values inside code examples do not cause false mismatches.
    text_without_code = _FENCED_CODE_BLOCK_RE.sub("", text)
    status_match = _STATUS_LINE_RE.search(text_without_code)
    if status_match is None:
        raise StoryDocMalformed(
            story_id=story_id,
            path=path,
            reason="missing 'Status:' line",
        )
    raw_state = status_match.group("state").strip()
    # The `Status:` value is expected to be one of the CurrentState enum
    # members; any other value is malformed (the lifecycle-state check at
    # step 2 will reject non-ready-for-dev states with
    # StoryDocLifecycleStateMismatch — so this resolver only validates
    # that the value is structurally a known state).
    known_states: tuple[str, ...] = (
        "ready-for-dev",
        "in-progress",
        "review",
        "qa",
        "done",
        "escalated",
    )
    if raw_state not in known_states:
        raise StoryDocMalformed(
            story_id=story_id,
            path=path,
            reason=f"unrecognized Status value {raw_state!r}",
        )

    if _AC_SECTION_HEADING not in text:
        raise StoryDocMalformed(
            story_id=story_id,
            path=path,
            reason=f"missing {_AC_SECTION_HEADING!r} section",
        )
    # Slice out the AC section's body (heading-to-next-heading or EOF).
    section_start = text.index(_AC_SECTION_HEADING) + len(_AC_SECTION_HEADING)
    rest = text[section_start:]
    next_section_match = re.search(r"^## ", rest, re.MULTILINE)
    section_body = (
        rest if next_section_match is None else rest[: next_section_match.start()]
    )
    ac_entries: list[AcceptanceCriterion] = []
    for ac_match in _AC_HEADING_RE.finditer(section_body):
        ac_entries.append(
            AcceptanceCriterion(
                ac_id=ac_match.group("ac_id"),
                text=ac_match.group("text").strip(),
            )
        )

    return StoryDocResolution(
        path=path,
        current_state=raw_state,  # type: ignore[arg-type]
        acceptance_criteria=tuple(ac_entries),
    )


def default_sprint_status_resolver(
    story_id: str,
    project_root: pathlib.Path,
) -> SprintStatusResolution:
    """Default :data:`SprintStatusResolver` implementation for production.

    Reads ``<project_root>/_bmad-output/implementation-artifacts/sprint-status.yaml``,
    parses the YAML, and resolves the ``development_status`` entry whose
    key matches ``story_id`` (prefix match against the BMAD convention
    ``<epic>-<story>-<slug>``).

    Tests inject deterministic stubs rather than calling this default.

    Args:
        story_id: The BMAD story identifier passed by the practitioner.
        project_root: Root directory under which to find
            ``_bmad-output/implementation-artifacts/sprint-status.yaml``.

    Returns:
        :class:`SprintStatusResolution` carrying the parsed
        ``current_state`` for the matching entry.

    Raises:
        SprintStatusMismatch: The sprint-status file is missing OR the
            ``development_status`` map has no entry matching
            ``story_id``.
        StoryDocMalformed: The sprint-status file exists but is not
            parseable as YAML OR is missing the ``development_status``
            key.
    """
    sprint_status_path = (
        project_root / _STORY_DOC_DIR / _SPRINT_STATUS_FILENAME
    )
    if not sprint_status_path.exists():
        raise SprintStatusMismatch(
            story_id=story_id,
            observed_state="<sprint-status.yaml not found>",
        )
    raw = yaml.safe_load(sprint_status_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise StoryDocMalformed(
            story_id=story_id,
            path=sprint_status_path,
            reason="sprint-status.yaml top-level is not a YAML mapping",
        )
    development_status = raw.get("development_status")
    if not isinstance(development_status, dict):
        raise StoryDocMalformed(
            story_id=story_id,
            path=sprint_status_path,
            reason="sprint-status.yaml is missing the 'development_status' key",
        )
    hyphen_prefix = f"{story_id}-"
    matches = [
        (key, value)
        for key, value in development_status.items()
        if isinstance(key, str)
        and (key == story_id or key.startswith(hyphen_prefix))
    ]
    # Skip epic-level keys (they look like "epic-N" and might match the
    # prefix test for short story_ids; the canonical story-key form
    # always has a slug after the second hyphen).
    matches = [
        (k, v) for k, v in matches if not k.startswith("epic-")
    ]
    if not matches:
        raise SprintStatusMismatch(
            story_id=story_id,
            observed_state="<no entry in development_status>",
        )
    # Prefer the longest matching key (most specific) on the rare
    # collision case. Sprint-status.yaml's structure is flat, so this
    # matters only when story-id is itself a prefix of multiple keys.
    matches.sort(key=lambda pair: len(pair[0]), reverse=True)
    _, observed_state = matches[0]
    if not isinstance(observed_state, str):
        raise StoryDocMalformed(
            story_id=story_id,
            path=sprint_status_path,
            reason=(
                f"sprint-status entry value {observed_state!r} is not a "
                f"string"
            ),
        )
    # Cast at the boundary; catch unknown state values before they produce
    # an untyped Pydantic ValidationError that escapes named-invariant discipline.
    try:
        return SprintStatusResolution(current_state=observed_state)  # type: ignore[arg-type]
    except ValidationError as exc:
        raise StoryDocMalformed(
            story_id=story_id,
            path=sprint_status_path,
            reason=(
                f"sprint-status entry for {story_id!r} has unrecognized state "
                f"value {observed_state!r}"
            ),
        ) from exc


# --------------------------------------------------------------------------- #
# Default dispatch stub                                                       #
# --------------------------------------------------------------------------- #


def default_dispatch_callback(
    *,
    specialist: str,
    story_id: str,
    run_state_path: pathlib.Path,
    story_doc_resolution: StoryDocResolution,
    event_log_appender: EventLogAppender,
) -> DispatchCallbackResult:
    """Default :data:`DispatchCallback` — no-op stub pending Story 2.6.

    Returns ``DispatchCallbackResult(dispatched=False, reason=...)``
    without invoking the Task tool, without writing run-state, without
    emitting an orchestrator event. Emits a single ``logging.info``
    diagnostic naming the dispatch-stub posture so the practitioner has
    confirmation that the entry sequence reached step (6).

    Story 2.6 (Task-tool dispatch with marker emission — epics.md lines
    1309-1346) replaces this stub at the call site with a real
    ``TaskToolDispatchCallback`` that constructs the specialist
    envelope, dispatches via the Task tool, validates the return, and
    feeds the envelope back through :func:`evaluate_envelope` for the
    next state-transition decision.

    The kwargs `run_state_path`, `story_doc_resolution`, and
    `event_log_appender` are accepted for signature symmetry with
    Story 2.6's eventual real callback (which will read run-state to
    populate the envelope's prompt-id correlation, read the story-doc
    resolution to render the prompt body, and emit a
    ``specialist-dispatched`` event via the appender). The stub
    references them only via the diagnostic message; it does NOT touch
    run-state or emit any event.

    Args:
        specialist: The specialist identifier the entry sequence
            requested (always ``"dev"`` at this story's seam per
            AC-2 step (6)).
        story_id: The BMAD story identifier from the entry sequence.
        run_state_path: Accepted for signature symmetry; the stub does
            NOT read or write the path.
        story_doc_resolution: Accepted for signature symmetry; the stub
            does NOT inspect the resolution beyond logging the path.
        event_log_appender: Accepted for signature symmetry; the stub
            does NOT invoke the appender (no synthetic
            ``dispatch-stubbed`` event is added to the orchestrator-
            event log — the schema's ``event_class`` enum does not
            include ``dispatch-stubbed``; see the module docstring's
            "Why the dispatch stub uses ``logging.info``" section for
            the rationale).

    Returns:
        :class:`DispatchCallbackResult` with ``dispatched=False`` and
        ``reason="dispatch stubbed pending Story 2.6"``.
    """
    # Reference the unused parameters explicitly so ruff/mypy/F841 do
    # not flag them as unused in the diagnostic message.
    _logger.info(
        "dispatch-stubbed: specialist=%s story_id=%s run_state_path=%s "
        "story_doc_path=%s event_log_appender_type=%s",
        specialist,
        story_id,
        run_state_path,
        story_doc_resolution.path,
        type(event_log_appender).__name__,
    )
    return DispatchCallbackResult(
        dispatched=False,
        reason="dispatch stubbed pending Story 2.6",
    )


# --------------------------------------------------------------------------- #
# Story 6.7 — hook-result composition helper (AC-2)                           #
# --------------------------------------------------------------------------- #


def handle_hook_exit_code(
    *,
    exit_code: int,
    hook_name: str,
    run_state: RunState,
) -> RunState:
    """Compose a hook-result into an updated RunState on non-zero exit.

    Story 6.7 AC-2 composition seam: when the orchestrator's hook-result
    handler reads a non-zero exit code from one of the three hook
    scripts (``subagent-stop`` / ``stop`` / ``session-start``), it
    invokes this helper to produce an updated :class:`RunState` carrying
    a ``hook-failed: <hook_name>`` marker. The caller composes the
    returned :class:`RunState` INTO the next-state argument it passes
    to :func:`loud_fail_harness.run_state.advance_run_state` per
    Pattern 4's batch-write rule (this helper does NOT call
    ``advance_run_state``; one atomic write per seam transition).

    Story 6.9 AC-3 cross-failure-matrix conditional:
        When ``hook_name == "stop"`` AND
        ``exit_code == BUNDLE_ASSEMBLY_FAILED_EXIT_CODE`` (=2), the
        helper returns the input run-state UNCHANGED — no
        ``hook-failed: stop`` marker is appended. This exit code is
        emitted exclusively by ``bundle_assembly.main``'s outer
        try/except after :func:`surface_assembly_failure` has already
        recorded ``bundle-assembly-failed: <step>`` (Channel 3); the
        Stop hook itself ran cleanly and merely propagated the
        assembler's exit. Emitting ``hook-failed: stop`` here would
        conflate the assembler's logical failure with a Stop hook
        mechanical failure per AC-3's remediation-shape principle.
        For ANY other non-zero exit code under ``hook_name == "stop"``
        — and for non-zero exits under ``subagent-stop`` /
        ``session-start`` regardless of code — the helper invokes
        :func:`record_hook_failure_marker` per the existing path. Both
        markers may fire independently when both surfaces fail (Stop
        hook crashes mechanically AND the assembler also crashed):
        ``bundle-assembly-failed`` is emitted by
        :func:`surface_assembly_failure` from the assembler's own
        failure path; ``hook-failed: stop`` is emitted here when the
        Stop hook's exit code is non-zero AND not equal to
        :data:`BUNDLE_ASSEMBLY_FAILED_EXIT_CODE`.

    Pure function (no I/O). The lazy import of
    :func:`loud_fail_harness.marker_wiring.record_hook_failure_marker`
    avoids the circular import that would otherwise arise from the cycle:
    ``orchestrator_run_entry`` → ``marker_wiring`` (lazy) →
    ``specialist_dispatch`` (top-level) → ``orchestrator_run_entry``
    (top-level). The lazy import in THIS module breaks the cycle by
    deferring the ``marker_wiring`` import until call time. The
    :data:`BUNDLE_ASSEMBLY_FAILED_EXIT_CODE` import is similarly lazy
    to avoid the cycle through ``bundle_assembly_failure`` →
    ``marker_wiring``.

    Marker-permanence rule (Story 1.4): a second non-zero exit for the
    SAME ``hook_name`` returns the input run-state unchanged via the
    recorder's per-hook-name de-dup; the FIRST emission wins.

    Happy-path (zero exit): the helper returns the input run-state
    unchanged — no marker is appended, no allocation occurs. Callers
    can invoke this helper for every hook return without checking
    ``exit_code`` upstream.

    Args:
        exit_code: The hook script's exit code as reported by the
            shell (``0`` for success; any non-zero per NFR-R6 for
            failure).
        hook_name: Canonical hook-name suffix (one of
            :data:`loud_fail_harness.marker_wiring.HOOK_NAMES`:
            ``"subagent-stop"``, ``"stop"``, ``"session-start"``).
        run_state: The :class:`RunState` BEFORE the marker append.

    Returns:
        A new :class:`RunState` carrying the
        ``hook-failed: <hook_name>`` marker entry; or the input
        run-state unchanged on zero-exit / Story-6.9 exit-code-2 under
        ``stop`` / de-dup.
    """
    if exit_code == 0:
        return run_state
    from loud_fail_harness.bundle_assembly_failure import (
        BUNDLE_ASSEMBLY_FAILED_EXIT_CODE,
    )

    if hook_name == "stop" and exit_code == BUNDLE_ASSEMBLY_FAILED_EXIT_CODE:
        # Story 6.9 AC-3: assembler-logic failure already emitted
        # `bundle-assembly-failed` via `surface_assembly_failure`; do
        # NOT emit `hook-failed: stop` for the same run.
        return run_state

    from loud_fail_harness.marker_wiring import HookName, record_hook_failure_marker

    return record_hook_failure_marker(
        run_state=run_state, hook_name=cast(HookName, hook_name)
    )


# --------------------------------------------------------------------------- #
# Public entry-sequence helper                                                #
# --------------------------------------------------------------------------- #


def run_story_loop_entry(
    story_id: str,
    *,
    project_root: pathlib.Path,
    story_doc_resolver: StoryDocResolver,
    sprint_status_resolver: SprintStatusResolver,
    run_state_path: pathlib.Path,
    run_id: str,
    story_doc_callback_factory: StoryDocCallbackFactory,
    event_log_appender: EventLogAppender,
    trunk_allowlist: tuple[str, ...],
    working_tree_probe: WorkingTreeProbe,
    dispatch_callback: DispatchCallback,
    marker_registry: MarkerClassRegistry | None = None,
) -> RunStoryLoopEntryResult:
    """Execute the six-step ``/bmad-automation run <story-id>`` entry
    sequence.

    Composition is exclusive per AC-4: this function does NOT inline any
    substrate-helper's logic; does NOT write ``run_state_path``
    directly; does NOT call ``subprocess`` (no inline ``git``); does NOT
    redeclare the lifecycle-transition map.

    Execution order (load-bearing per AC-2):

        1. **Locate** — ``story_doc_resolver(story_id, project_root)``.
        2. **Validate** — assert
           ``resolution.current_state == "ready-for-dev"``;
           ``sprint_status_resolver(...)`` validates the sprint-status
           entry is in ``{"ready-for-dev", "backlog"}``.
        3. **Branch** — :func:`create_story_branch`.
        4. **Init run-state** — :func:`advance_run_state` with the
           module-private :func:`_no_op_story_doc_callback`.
        5. **Advance to in-progress** — :func:`commit_transition` with
           ``story_doc_callback_factory(story_id)`` and
           ``event_log_appender``.
        6. **Dispatch** — ``dispatch_callback(specialist="dev", ...)``.

    Each keyword-only parameter is **non-defaulted**; omitting any
    raises ``TypeError`` at call time per Python's missing-required-
    keyword-argument semantics. mypy strict mode (when enabled) catches
    the omission at type-check time. Structural enforcement is verified
    by the AC-5 API-shape tests.

    Args:
        story_id: The BMAD story identifier the practitioner passed at
            ``/bmad-automation run <story-id>``.
        project_root: Root directory the resolvers search under (and
            the repo root for the branch operation).
        story_doc_resolver: :data:`StoryDocResolver` for step 1.
        sprint_status_resolver: :data:`SprintStatusResolver` for the
            independent sprint-status check at step 2.
        run_state_path: Caller-controlled on-disk path for the run-state
            file. Forwarded verbatim to :func:`advance_run_state` and
            :func:`commit_transition`.
        run_id: Orchestrator-domain identifier correlating dispatch with
            the run-state.yaml record per ADR-005 Consequence 1.
        story_doc_callback_factory: :data:`StoryDocCallbackFactory` for
            step 5's ``commit_transition`` call. Invoked HERE (not at
            module top-level; not at step 4) because step 5 is the
            first step where a story-doc write is structurally required
            (the ``ready-for-dev → in-progress`` transition).
        event_log_appender: Forwarded verbatim to
            :func:`commit_transition` per AC-4. The substrate does NOT
            wrap, decorate, transform, or replace the appender.
        trunk_allowlist: Forwarded verbatim to :func:`create_story_branch`
            per AC-4.
        working_tree_probe: Forwarded verbatim to
            :func:`create_story_branch` per AC-4.
        dispatch_callback: :data:`DispatchCallback` for step 6.
            :func:`default_dispatch_callback` is a module-public no-op
            stub callers can pass when Story 2.6's real callback is not
            yet wired.

    Returns:
        :class:`RunStoryLoopEntryResult` carrying the wrapped results
        from steps (3)-(6) on the success path.

    Raises:
        StoryDocNotFound: Step 1 — the resolver returned ``None`` or
            raised this class. No commit-phase step ran.
        StoryDocMalformed: Step 1 — the resolver found the file but
            could not parse it. No commit-phase step ran.
        StoryDocLifecycleStateMismatch: Step 2 — the lifecycle state is
            not ``ready-for-dev``. No commit-phase step ran.
        SprintStatusMismatch: Step 2 — the sprint-status entry is not in
            ``{"ready-for-dev", "backlog"}``. No commit-phase step ran.
        loud_fail_harness.branch_lifecycle.BranchLifecycleBlocked: Step
            3 — propagated unchanged from :func:`create_story_branch`.
        loud_fail_harness.run_state.RunStateAdvanceBlocked: Step 4 OR
            step 5 — propagated unchanged.
        loud_fail_harness.lifecycle_state_machine.InvalidLifecycleTransition:
            Step 5 — propagated unchanged from
            :func:`commit_transition`.
        OSError: Step 4 OR step 5 — temp-write or atomic-rename failure
            inside :func:`advance_run_state`.
        loud_fail_harness.story_doc_version_check.StoryDocVersionDetectionError:
            Step 1b — detection failed (neither inline marker nor manifest
            fallback yielded a parseable version), OR the tolerance-window
            config-file value is non-integer or negative
            (``reason="tolerance-window-not-an-integer"``), OR the config
            file contains non-UTF-8 bytes or invalid YAML
            (``reason="config-yaml-parse-error"``). Only raised when
            ``marker_registry is not None``; bypassed otherwise.
    """
    # ===================================================================== #
    # Pre-flight phase (steps 1-2): NO side effects; named-invariant       #
    # exception raises before ANY commit-phase step runs.                  #
    # ===================================================================== #

    # Step 1: Locate the story doc.
    story_doc_resolution = story_doc_resolver(story_id, project_root)
    if story_doc_resolution is None:  # type: ignore[unreachable]
        # Defensive: a resolver returning None instead of raising still
        # halts the entry sequence with the named-invariant diagnostic.
        raise StoryDocNotFound(  # type: ignore[unreachable]
            story_id=story_id,
            searched_paths=(project_root,),
        )

    # Step 1b (Story 7.7 — FR43 + NFR-I5): preflight version-check.
    # Pure-decision detection at preflight per AC-8 Option A — exceptions
    # surface BEFORE any commit-phase step runs (Pattern 5). Marker
    # emission deferred to step 5b so the marker folds into ``next_state``
    # and persists across the lifecycle transition. The check is gated
    # on ``marker_registry is not None`` so existing tests that use
    # stub resolvers (and don't provide a registry) bypass the check
    # entirely. Imports are lazy here to break the circular module
    # dependency through marker_wiring → specialist_dispatch.
    from loud_fail_harness.story_doc_version_check import (
        VersionCheckRequest,
        check_story_doc_version,
    )

    version_check_outcome: VersionCheckOutcome | None = None
    if marker_registry is not None:
        version_check_outcome, _ = check_story_doc_version(
            VersionCheckRequest(
                story_doc_path=story_doc_resolution.path,
                project_root=project_root,
            ),
            run_state=None,
            marker_registry=None,
        )

    # Step 2a: Validate the story-doc lifecycle state.
    if story_doc_resolution.current_state != "ready-for-dev":
        raise StoryDocLifecycleStateMismatch(
            story_id=story_id,
            observed_state=story_doc_resolution.current_state,
        )

    # Step 2b: Independently validate the sprint-status entry.
    sprint_status_resolution = sprint_status_resolver(story_id, project_root)
    expected_sprint_states: tuple[str, ...] = ("ready-for-dev", "backlog")
    if sprint_status_resolution.current_state not in expected_sprint_states:
        raise SprintStatusMismatch(
            story_id=story_id,
            observed_state=sprint_status_resolution.current_state,
            expected_states=expected_sprint_states,
        )

    # ===================================================================== #
    # Commit phase (steps 3-6): side effects in documented order.           #
    # ===================================================================== #

    # Step 3: Create (or idempotently checkout) the per-story branch via
    # Story 2.3's helper. Trunk-allowlist + working-tree-probe
    # enforcement is INSIDE the helper; the entry sequence is a thin
    # composition layer per sensor-not-advisor.
    branch_lifecycle_result = create_story_branch(
        story_id,
        trunk_allowlist=trunk_allowlist,
        working_tree_probe=working_tree_probe,
        repo_root=project_root,
    )

    # Step 4: Initialize run-state via Story 2.2's helper with the
    # module-private no-op story-doc callback. The story doc already
    # exists per step (1)'s locate; no story-doc write is structurally
    # needed at init time.
    initial_run_state = RunState(
        schema_version="1.1",
        story_id=story_id,
        run_id=run_id,
        current_state="ready-for-dev",
        branch_name=branch_lifecycle_result.branch_name,
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )
    init_advance_result = advance_run_state(
        run_state_path=run_state_path,
        next_state=initial_run_state,
        story_doc_callback=_no_op_story_doc_callback,
    )

    # Step 5: Advance to in-progress via Story 2.4's commit_transition.
    # The factory is invoked HERE (not at module top-level; not at step
    # 4) so the callback closes over the resolved story_id specifically.
    next_state = RunState(
        schema_version="1.1",
        story_id=story_id,
        run_id=run_id,
        current_state="in-progress",
        branch_name=branch_lifecycle_result.branch_name,
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )
    # Defensive runtime story_id consistency assertion (Story 2.4 deferred-
    # work item #4 honored at this integration site per AC-4). The
    # ``assert`` form is acceptable because a firing assertion would mean
    # the substrate's own composition is broken — programmer error, not
    # a user-facing failure mode.
    assert (
        initial_run_state.story_id == next_state.story_id == story_id
    ), (
        f"story_id consistency invariant violated: "
        f"initial_run_state.story_id={initial_run_state.story_id!r}, "
        f"next_state.story_id={next_state.story_id!r}, "
        f"story_id={story_id!r}"
    )
    # Step 5b (Story 7.7): fold the version-check marker into next_state.
    # The marker class ``story-doc-version-out-of-window`` is the v1
    # closed-taxonomy entry consumed AS-IS; emission goes through the
    # canonical ``record_marker_with_context`` path inside
    # ``check_story_doc_version`` itself. A second call is required
    # here (rather than at step 1b) so the marker folds into the
    # post-transition ``next_state`` rather than being lost.
    # ``StoryDocVersionDetectionError``, ``check_story_doc_version``
    # and ``VersionCheckRequest`` are already in scope from the lazy
    # import at step 1b above.
    if (
        version_check_outcome is not None
        and version_check_outcome.action == "proceed-with-marker"
        and marker_registry is not None
    ):
        # Step 5b: emit the version-check marker into next_state. Any
        # StoryDocVersionDetectionError here (e.g., manifest disappeared
        # between step 1b and 5b) propagates unchanged — consistent with
        # step 1b's posture and satisfying NFR-I5's loud-fail requirement.
        _, maybe_updated_next_state = check_story_doc_version(
            VersionCheckRequest(
                story_doc_path=story_doc_resolution.path,
                project_root=project_root,
            ),
            run_state=next_state,
            marker_registry=marker_registry,
        )
        if maybe_updated_next_state is not None:
            next_state = maybe_updated_next_state

    commit_result = commit_transition(
        run_state_path,
        initial_run_state,
        next_state,
        story_doc_callback=story_doc_callback_factory(story_id),
        event_log_appender=event_log_appender,
    )

    # Step 6: Dispatch the first specialist (Dev). Story 2.6 replaces
    # the default no-op stub at the call site with a real
    # TaskToolDispatchCallback; this story stubs the call.
    dispatch_callback_result = dispatch_callback(
        specialist="dev",
        story_id=story_id,
        run_state_path=run_state_path,
        story_doc_resolution=story_doc_resolution,
        event_log_appender=event_log_appender,
    )

    return RunStoryLoopEntryResult(
        story_id=story_id,
        branch_lifecycle_result=branch_lifecycle_result,
        init_advance_result=init_advance_result,
        transition_advance_result=commit_result.advance_result,
        state_transition_event=commit_result.emitted_event,
        dispatch_callback_result=dispatch_callback_result,
    )


__all__ = [
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
]
