"""Specialist dispatch substrate library (Story 2.6).

Architectural placement (story 1.10b precedent — story 2.2's
``run_state.py`` Dev Notes "Why ``run_state.py`` is a substrate library
(not a sixth substrate component)"; story 2.3's ``branch_lifecycle.py``;
story 2.4's ``lifecycle_state_machine.py``; story 2.5's
``orchestrator_run_entry.py``): this module is a **substrate library
NOT a sixth substrate component**. ADR-003 Consequence 1 enumerates
exactly five substrate components (architecture.md lines 311-315); this
module is a substrate **library** consumed by Stories 2.7-2.13 and Phase
1.5+ retry / scope / loud-fail-block / cost-telemetry stories at
orchestrator runtime to perform Task-tool-backed specialist dispatch
with marker emission sourced from the canonical taxonomy. The
substrate-component count stays at FIVE; the harness module count
grows from 17 to 18.

What this library provides:
    * **Marker-class registry** (:class:`MarkerClassRegistry`,
      :func:`load_marker_class_registry`, :func:`validate_marker_emission`,
      :exc:`UnknownMarkerClass`) — the runtime fail-fast that prevents
      a typo'd or stale marker_class from ever reaching the
      orchestrator-event log. Loaded from
      ``schemas/marker-taxonomy.yaml`` at function-call time per Epic 1
      retro Action #1; complements Story 1.5's ``enumeration_check``
      (POST-emission validation) by closing the gap with PRE-emission
      validation per epics.md line 1335.
    * **Dispatch payload construction** (:class:`SpecialistDispatchPayload`,
      :func:`build_dispatch_payload`, :func:`default_prompt_body_renderer`)
      — the canonical "what gets handed to Task tool" record. The agent
      definition file is read AS DATA via ``Path.read_text()`` per
      FR62 + ADR-004's "Task tool's prompt format is the dispatch
      contract surface".
    * **Diagnostic log persistence** (:data:`LOG_PATH_TEMPLATE`,
      :func:`persist_dispatch_log`) — NFR-O3's structured log per
      specialist invocation. Atomic-write via
      ``tempfile.NamedTemporaryFile`` + ``os.replace`` mirroring
      Story 2.2's ``advance_run_state`` precedent.
    * **Return envelope validation** (:class:`ReturnEnvelopeValidation`,
      :func:`validate_return_envelope`,
      :func:`validate_return_envelope_strict`,
      :exc:`EnvelopeValidationFailed`) — composes Story 1.2's
      ``validate_envelope`` + ``format_errors`` exclusively; no
      reimplementation of envelope validation logic.
    * **Wall-clock timeout exception** (:exc:`SpecialistTimeoutExceeded`)
      — the named-invariant runtime-degradation marker the LLM raises
      when the orchestrator's per-specialist wall-clock timer fires;
      carries ``marker_class="specialist-timeout"`` +
      ``sub_cause="timeout-exceeded"`` sourced verbatim from
      ``marker-taxonomy.yaml`` entry 7.
    * **Orchestrator-event emission helpers**
      (:func:`make_specialist_dispatched_event`,
      :func:`make_specialist_returned_event`,
      :func:`default_event_id_factory`, :exc:`EventConstructionFailed`)
      — schema-valid event payloads conforming to
      ``schemas/orchestrator-event.yaml`` lines 113-176. Composes
      Story 1.3's ``validate_event`` exclusively; defensive validation
      before return.
    * **Task-tool dispatch callback factory**
      (:class:`TaskToolDispatchCallback` Protocol,
      :func:`make_task_tool_dispatch_callback`) — the runtime closure
      that the orchestrator skill at LLM-runtime invokes via
      :data:`loud_fail_harness.orchestrator_run_entry.DispatchCallback`'s
      caller-injected seam. The Python factory is the structural
      contract; the actual Task-tool invocation lives in the LLM-
      runtime prose at ``skills/bmad-automation/steps/dispatch.md`` per
      ADR-004's substrate-vs-LLM-runtime split.

Contract anchors:
    FR3, FR50, FR51, FR52, FR53, FR54, FR55, FR56, FR62, NFR-O1,
    NFR-O3, NFR-O5, NFR-O6, NFR-P2, NFR-R8, ADR-001, ADR-003, ADR-004,
    ADR-005, ADR-006, Pattern 1, Pattern 2, Pattern 3, Pattern 5,
    Pattern 6.

Cross-story seam contracts (forward-compat consumers):
    Stories 2.7 (three hooks; SubagentStop reads ``last_envelope``),
    2.8 / 2.9 / 2.10 (Dev / Review-BMAD / QA wrappers — agent-definition
    files this substrate reads as DATA), 2.11 (PR bundle assembly reads
    ``specialist-dispatched`` + ``specialist-returned`` events), 2.12
    (per-seam streaming + per-specialist log persistence — thickens
    streaming on top of THIS story's ``event_log_appender`` seam +
    extends ``LOG_PATH_TEMPLATE`` if streaming requires more
    structure), 2.13 (walking-skeleton fixture exercises the entire
    dispatch wrapper end-to-end), 5.1 / 5.2 / 5.3 (retry-loop wires
    ``attempt_number`` above the substrate without changing the API
    surface), 6.4 (per-specialist × per-retry cost telemetry hooks
    into the existing ``(prompt_id, retry_attempt, specialist)``
    correlation triple per ADR-006 Combo 3 / A3'), 6.7 (specialist-
    timeout markers fully wired into PR bundle).

## FR62 pluggability classification

This module is *substrate-shared library* per Story 1.10b's precedent
and ADR-003's substrate-vs-specialist boundary. The FR62 pluggability
gate at :mod:`loud_fail_harness.pluggability_gate` scans ``agents/*.md``
only (lines 11 + 64 + 102 + 116-121); the substrate at
``tools/loud-fail-harness/`` is OUTSIDE the gate's scope by
construction. The gate's existing seam-contract enumeration at
``pluggability_gate.py`` lines 45-66 explicitly recognizes Story 2.6's
substrate placement: "Story 2.6 (specialist dispatch wrapper treats
agent files as data, not as code — the wrapper lives outside
``agents/`` and is therefore substrate by construction)". No gate edit
required at this story's site.

The substrate does NOT import any module from a ``agents.`` namespace;
agent-definition files are read AS DATA via ``Path.read_text()``
(NEVER via ``import``). See the "Why agent-definition files are read
as DATA" section below.

## Forward-compat consumers

Stories that will consume this substrate library at orchestrator
runtime via the LLM-runtime dispatch protocol prose at
``skills/bmad-automation/steps/dispatch.md``:

    * Story 2.7 — three hooks (SubagentStop / Stop / SessionStart):
      ``subagent-stop.sh`` reads the ``last_envelope`` field on
      ``RunState`` populated by THIS story's dispatch wrapper via
      ``event_log_appender``; the ``specialist-returned`` event's
      ``envelope_artifact_path`` field points at the on-disk envelope
      artifact the hook reads.
    * Stories 2.8 / 2.9 / 2.10 — minimal Dev / Review-BMAD / QA
      wrapper subagents: each lands one of ``agents/{dev,
      review-bmad, qa}-wrapper.md`` files that THIS story's
      ``build_dispatch_payload`` reads as DATA via
      ``agent_definition_path.read_text()`` at orchestrator runtime.
    * Story 2.11 — PR bundle assembly with machine-readable
      walking-skeleton header: reads the orchestrator-event log THIS
      story populates with ``specialist-dispatched`` +
      ``specialist-returned`` events.
    * Story 2.12 — per-seam state streaming + per-specialist log
      persistence: thickens the streaming primitive on top of THIS
      story's ``event_log_appender`` seam; MAY extend
      :data:`LOG_PATH_TEMPLATE` if the streaming format requires
      additional structure.
    * Story 2.13 — walking-skeleton sample-story fixture +
      test-infrastructure: exercises this dispatch wrapper end-to-end
      against a sample story.
    * Stories 5.1 / 5.2 / 5.3 — retry budget + bucket-driven retry
      routing + Dev fix-only retry: the ``attempt_number`` parameter
      iterates per retry budget without changing this substrate's
      API.
    * Story 6.4 — per-specialist × per-retry cost telemetry: hooks
      into the ``(prompt_id, retry_attempt, specialist)``
      correlation triple THIS story emits via
      :func:`_derive_prompt_id` + the orchestrator-event fields.
    * Story 6.7 — specialist-timeout / hook-failed / context-near-
      limit markers fully wired into PR bundle: reads the
      ``specialist-timeout`` markers THIS story emits and renders
      them in the PR bundle's loud-fail block.

## ADR-004 dispatch primitive — what's substrate, what's LLM-runtime

The dispatch seam splits architecturally into two layers:

**Substrate Python (this module)** owns the load-bearing structural
concerns: registry validation + envelope validation + log shape +
event shape. These are testable, type-checkable, and CI-enforceable
through the AC-9 contract-coverage matrix.

**LLM-runtime prose** (``skills/bmad-automation/steps/dispatch.md``)
owns the actual Task-tool invocation, the wall-clock timer, and the
return-text parsing. The substrate Python CANNOT directly invoke Task
tool — Task tool is a Claude-Code-skill primitive, NOT a Python API.
ADR-004 explicitly rejects the Agent SDK route as "incompatible with
orchestrator-as-skill" (architecture.md line 363). Inlining a
``subprocess``-based Task-tool wrapper would (a) violate ADR-004's
architectural commitment, (b) introduce a process-spawn dependency,
(c) silently regress the substrate-vs-LLM-runtime boundary.

The :func:`make_task_tool_dispatch_callback` factory's returned
closure raises ``NotImplementedError`` if invoked from pure Python
without the LLM-runtime context — a deliberate substrate-vs-LLM-
runtime boundary marker that prevents tests from accidentally
bypassing the LLM-runtime protocol.

## Why marker-class registry loads at function-call time, not module import time

Epic 1 retrospective Action #1 (epic-1-retro-2026-04-27.md lines
105-106) targets the risk of ``find_repo_root()`` called at module
import time, raising ``RuntimeError`` when pytest is invoked outside
the repo root. This module honors the discipline:

    * :func:`load_marker_class_registry` resolves the taxonomy path at
      function-call time only.
    * :func:`_load_event_schema` (private helper for AC-7's
      event-construction helpers) resolves the schema path at
      function-call time only.
    * :func:`validate_return_envelope` resolves the envelope schema
      path at function-call time only when ``schema=None``.
    * Module top-level imports do NOT call :func:`find_repo_root`;
      tests use fixture-time resolution.

The registry is conceptually a runtime singleton at LLM-runtime: the
orchestrator skill loads the registry once at the start of a
``/bmad-automation run`` invocation; passes the registry to every
emission-validation call. But the loading is structurally deferred
to function-call time so the substrate is import-safe even outside
the repo. The on-disk taxonomy file IS the single source of truth
and the registry is its in-memory mirror — no compile-time-baked
enum, no inline registry literal, no enumeration-equivalence drift
between the registry and the taxonomy file.

## Why precondition exceptions carry ``marker_class: None`` and timeout exceptions carry ``marker_class: "specialist-timeout"``

The asymmetry encodes the architectural distinction between runtime
degradation markers and programmer-or-state-misalignment diagnostics.

**Programmer-error invariants** (:exc:`UnknownMarkerClass`,
:exc:`EventConstructionFailed`) carry ``marker_class: None``. The
substrate's own structural invariants are broken; the loop CANNOT
continue. These surface in the orchestrator's terminal stream per
NFR-O1, NOT via the PR bundle's loud-fail block.

**Up-front validation diagnostics** (:exc:`EnvelopeValidationFailed`)
carry ``marker_class: None``. The specialist returned a
structurally-invalid envelope; the loop halts at the seam; no PR
bundle is produced. These map to ADR-004's ``silent-corruption``
sub-cause but the current ``marker-taxonomy.yaml`` 1.1 enumeration
does NOT include a ``specialist-envelope-invalid`` marker class;
adding one would require a taxonomy MINOR bump + a corresponding
``examples/synthetic-stories/`` Layer C fixture per ADR-003 substrate
component 5 — both are out of scope for THIS story per AC-10's "no
taxonomy bump" scope discipline. Future Stories 6.x or an Epic-3
marker-bump may add the marker class with the corresponding fixture.

**Runtime degradation markers** (:exc:`SpecialistTimeoutExceeded`)
carry ``marker_class="specialist-timeout"``. The loop CONTINUES with
degraded behavior + a marker that surfaces in the PR bundle. This is
the loud-fail doctrine's canonical scope: the orchestrator's wall-
clock timeout fired, the specialist did NOT return within the
budget, the dispatch is treated as failed, and the PR bundle's
loud-fail block carries the marker per Pattern 5 + NFR-P2.

## Why agent-definition files are read as DATA

The substrate at ``tools/loud-fail-harness/`` is OUTSIDE the FR62
pluggability gate's ``agents/*.md`` scope by construction; agent-
definition files are read AS DATA via ``Path.read_text()``, NEVER via
``import``. Two considered alternatives:

**Alternative A (rejected) — Import the agent definition.**
A hypothetical ``from agents{dot}dev_wrapper import PROMPT_BODY``
form. Violates FR62's pluggability invariant: specialist code cannot
import or reference another specialist (PRD line 897). Forces agent
definitions to be Python modules instead of markdown files.

**Alternative B (chosen) — Read the agent definition as text.**
``agent_definition_path.read_text(encoding="utf-8")``. Aligns with
FR62 + ADR-004's "Task tool's prompt format is the dispatch contract
surface" (architecture.md line 412) — the agent definition is part
of the prompt format, not part of the dispatch primitive's
executable code. Aligns with the BMAD agent-definition shape
(markdown files at ``agents/*.md`` per Story 2.5's View 1 source-
repo location).

## Why envelope validation composes Story 1.2's validator exclusively

The substrate at :func:`validate_return_envelope` does NOT
reimplement envelope validation logic. The entire validation flows
through :func:`loud_fail_harness.envelope_validator.validate_envelope`
+ :func:`loud_fail_harness.envelope_validator.format_errors`.
Reimplementation would (a) duplicate the envelope schema's parsing
logic, (b) bypass ``format_errors``'s UX-aligned message rewriting
per Story 1.2 AC-2, (c) silently regress the FR53 CI gate's contract.
Substrate-to-substrate composition is allowed by FR62 and is the
canonical pattern.

## Why event_id_factory is caller-injected

Sensor-not-advisor (Pattern 5; ADR-001's portable-surface
enumeration): the substrate doesn't pick the id-generation strategy.
The orchestrator skill at runtime supplies the factory; tests inject
deterministic factories for replay scenarios; production callers MAY
substitute a deterministic factory for replay-correlation work. The
:func:`default_event_id_factory` is the canonical factory tests +
smoke runs use — a UUID-derived opaque identifier with the
``"ev-2-6-dispatch-"`` story-scoped prefix.

## Configuration source for ``timeout_seconds``

NFR-P2 (PRD line 935): "Hard cap: individual specialist invocations
exceeding a configurable timeout (default: 15 minutes per specialist
invocation, configurable in ``_bmad/automation/config.yaml``;
revisit per release against reference-project specialist runtime
distributions) signal a hang and surface a loud-fail marker
(``specialist-timeout: {specialist}``)".

The :func:`make_task_tool_dispatch_callback` factory accepts
``timeout_seconds: int = 900`` (15 minutes) at construction time;
configurable per-callable but NOT per-call (per-call configurability
is Epic 5's retry-loop responsibility, NOT this story). The
``_bmad/automation/config.yaml`` plumbing lands in Story 7.5; THIS
story exposes the parameter, Story 7.5 wires the config-file source.

## Sensor-not-advisor (PRD-level invariant + ADR-001)

The substrate RETURNS structural primitives (registry, payload, log,
envelope-validator, event-emitter helpers); it does NOT decide flow
policy (retry routing, escalation triggering, dispatch sequencing,
scope-assertion enforcement). Flow policy lives in the orchestrator
skill prompt + downstream Epic 5 stories. The substrate does NOT
auto-emit markers from inside exception ``__init__``; emission is the
caller's responsibility per the AC-6 "Emission protocol" docstring
section.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import tempfile
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    Protocol,
    runtime_checkable,
)

from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness._shared import find_repo_root, load_schema
from loud_fail_harness.exceptions import ContractViolation
from loud_fail_harness.envelope_validator import format_errors, validate_envelope
from loud_fail_harness.event_validator import validate_event
from loud_fail_harness.orchestrator_run_entry import (
    AcceptanceCriterion,
    DispatchCallbackResult,
    StoryDocResolution,
)
from loud_fail_harness.reconciler import load_marker_taxonomy

if TYPE_CHECKING:
    from loud_fail_harness.cost_streaming import CostStreamingResult
    from loud_fail_harness.cost_telemetry import (
        CollectionResult,
        OtelPipelineProtocol,
    )
    from loud_fail_harness.run_state import RunState

#: Module-level logger. The substrate does NOT use ``print`` (Pattern 5);
#: ``logging`` is reserved for the dispatch-stub-replaced posture
#: parallel to :mod:`loud_fail_harness.orchestrator_run_entry`.
_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Marker-class registry (AC-2)                                                #
# --------------------------------------------------------------------------- #


class MarkerClassRegistry(BaseModel):
    """In-memory mirror of ``schemas/marker-taxonomy.yaml``'s enumeration.

    Frozen Pydantic model carrying a single field ``marker_classes:
    frozenset[str]``. ``frozenset`` is the structurally-immutable
    sequence type chosen for unordered membership-lookup collections
    per Epic 1 retro Action #2 (parallel to the ``tuple[…]`` discipline
    for ordered sequences in Story 2.5's
    :class:`AcceptanceCriterion` and Story 2.4's
    :class:`CommitTransitionResult`).

    The registry is conceptually a runtime singleton at LLM-runtime
    (the orchestrator skill loads the registry once at the start of a
    ``/bmad-automation run`` invocation; passes the registry to every
    emission-validation call). The on-disk taxonomy file IS the single
    source of truth; this in-memory mirror exists to provide O(1)
    membership lookup at every emission site without re-reading the
    file.
    """

    model_config = ConfigDict(frozen=True)

    marker_classes: frozenset[str]

    def __contains__(self, marker_class: object) -> bool:
        """Delegate to the frozenset for ergonomic ``marker_class in registry`` checks."""
        return marker_class in self.marker_classes


def load_marker_class_registry(
    taxonomy_path: pathlib.Path | None = None,
) -> MarkerClassRegistry:
    """Load the marker-class registry from the on-disk taxonomy YAML.

    Composes :func:`loud_fail_harness.reconciler.load_marker_taxonomy`
    exclusively; does NOT reimplement taxonomy parsing.

    Args:
        taxonomy_path: Optional explicit path to the taxonomy YAML. If
            ``None``, resolves via
            :func:`loud_fail_harness._shared.find_repo_root` at
            function-call time (Epic 1 retro Action #1; NEVER at
            module import time).

    Returns:
        :class:`MarkerClassRegistry` instance whose ``marker_classes``
        field is a ``frozenset`` mirroring the taxonomy file's
        ``markers: [...]`` ``marker_class:`` values.
    """
    if taxonomy_path is None:
        taxonomy_path = find_repo_root() / "schemas" / "marker-taxonomy.yaml"
    marker_classes = load_marker_taxonomy(taxonomy_path)
    return MarkerClassRegistry(marker_classes=frozenset(marker_classes))


def validate_marker_emission(
    registry: MarkerClassRegistry, marker_class: str
) -> None:
    """Raise :exc:`UnknownMarkerClass` when ``marker_class`` is not in the registry.

    Returns ``None`` on success — the validation is structural; success
    is the absence of an exception.

    This CI check complements (not replaces) Story 1.5's
    enumeration_check: 1.5 covers events emitted into event logs
    (post-emission validation); this registry covers the dispatch
    wrapper's PRE-emission validation — closing the gap where a runtime
    fail-fast would prevent the unknown marker from ever reaching event
    logs (per epics.md line 1335 verbatim).
    """
    if marker_class not in registry.marker_classes:
        raise UnknownMarkerClass(
            marker_class=marker_class,
            known_classes=registry.marker_classes,
        )


class UnknownMarkerClass(ContractViolation):
    """Raised by :func:`validate_marker_emission` when the candidate marker
    class is not in the registry's enumeration.

    Pattern 5 named-invariant diagnostic. ``marker_class:
    ClassVar[None] = None`` — the meta-constraint that prevents an
    infinite recursion of "the marker-validator emitting markers about
    marker validation". The substrate that VALIDATES marker emissions
    cannot itself emit a loud-fail marker because the very registry it
    depends on hasn't loaded the would-be marker class.

    Attributes:
        marker_class_name: The candidate marker class string the caller
            attempted to emit. (Named ``marker_class_name`` to avoid
            shadowing the class-level ``marker_class: ClassVar[None]``
            attribute, which is part of the Pattern 5 named-invariant
            contract.)
        known_classes: The registry's known set at emission time.
    """

    marker_class: ClassVar[None] = None

    def __init__(
        self,
        *,
        marker_class: str,
        known_classes: frozenset[str],
    ) -> None:
        self.marker_class_name: str = marker_class
        self.known_classes: frozenset[str] = known_classes
        super().__init__(
            f"UnknownMarkerClass: marker_class={marker_class!r} not found in "
            f"marker-taxonomy.yaml's enumerated set ({len(known_classes)} known); "
            "this likely indicates either (a) a typo in the emission call, OR "
            "(b) a stale registry that wasn't reloaded after a "
            "marker-taxonomy.yaml edit, OR (c) an attempt to emit a marker "
            "class that hasn't been added to the taxonomy yet (add it via the "
            "Story 1.4 bump rule before emitting)"
        )


# --------------------------------------------------------------------------- #
# Dispatch payload construction (AC-3)                                        #
# --------------------------------------------------------------------------- #


#: Specialist identifier enum mirroring
#: ``schemas/orchestrator-event.yaml`` lines 130-132's ``specialist``
#: enum verbatim. Single source of truth via copy-and-pin per the
#: existing precedent in :mod:`loud_fail_harness.lifecycle_state_machine`'s
#: :data:`EnvelopeOutcome` literal.
SpecialistId = Literal["dev", "review-bmad", "qa", "lad"]


#: Type alias for the prompt-body renderer parameter of
#: :func:`build_dispatch_payload`. A callable accepting
#: ``(agent_definition_text, story_doc_resolution, attempt_number)``
#: and returning the rendered LLM-runtime prompt body string.
PromptBodyRenderer = Callable[[str, StoryDocResolution, int], str]


#: Type alias for the dispatch-timestamp factory parameter of
#: :func:`build_dispatch_payload`. A zero-arg callable returning a
#: timezone-aware UTC :class:`datetime` instance. Tests inject
#: deterministic factories for byte-stable assertions.
DispatchTimestampFactory = Callable[[], datetime]


class SpecialistDispatchPayload(BaseModel):
    """Canonical "what gets handed to Task tool" record.

    Frozen Pydantic model. Field declaration order is load-bearing for
    byte-stable ``model_dump_json()`` output; sequence fields use
    ``tuple[…]`` per Epic 1 retro Action #2.

    Field semantics:
        * ``specialist`` — one of ``"dev" | "review-bmad" | "qa" | "lad"``
          mirroring the orchestrator-event schema's enum.
        * ``story_id`` — the BMAD story identifier the dispatch is
          scoped to.
        * ``attempt_number`` — retry-attempt counter; ``0`` means
          "first dispatch / never retried"; Epic 5 thickens the retry
          loop above the substrate.
        * ``acceptance_criteria`` — tuple of :class:`AcceptanceCriterion`
          imported from Story 2.5's substrate library.
        * ``agent_definition_path`` — on-disk path to the markdown
          agent definition the substrate read via
          :meth:`pathlib.Path.read_text` at construction time;
          preserved on the model for log-shape provenance.
        * ``prompt_body`` — the rendered LLM-runtime prompt fragment
          (the result of :data:`PromptBodyRenderer`).
        * ``dispatch_timestamp`` — timezone-aware UTC datetime captured
          at :func:`build_dispatch_payload` construction time; sourced
          for the ``specialist-dispatched`` event's ``timestamp`` field
          per AC-7.
        * ``prompt_id`` — orchestrator-internal correlation key per
          ADR-006 Combo 3 / A3'; computed ONCE in
          :func:`build_dispatch_payload` and stored here so that both
          ``specialist-dispatched`` and ``specialist-returned`` events
          for the same dispatch carry the identical value.
    """

    model_config = ConfigDict(frozen=True)

    specialist: SpecialistId
    story_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=0)
    acceptance_criteria: tuple[AcceptanceCriterion, ...]
    agent_definition_path: pathlib.Path
    prompt_body: str
    dispatch_timestamp: datetime
    prompt_id: str


def _default_dispatch_timestamp_factory() -> datetime:
    """Return a timezone-aware UTC :class:`datetime` at function-call time.

    Module-private; tests inject deterministic factories via the
    ``dispatch_timestamp_factory`` parameter on
    :func:`build_dispatch_payload`.
    """
    return datetime.now(timezone.utc)


def build_dispatch_payload(
    *,
    specialist: SpecialistId,
    story_id: str,
    attempt_number: int,
    story_doc_resolution: StoryDocResolution,
    agent_definition_path: pathlib.Path,
    prompt_body_renderer: PromptBodyRenderer,
    dispatch_timestamp_factory: DispatchTimestampFactory | None = None,
) -> SpecialistDispatchPayload:
    """Construct the dispatch payload by composing the agent definition + story context.

    Execution order (load-bearing):

        1. Read ``agent_definition_path`` AS DATA via
           :meth:`pathlib.Path.read_text` (NEVER via ``import`` —
           FR62 + ADR-004's pluggability invariant).
        2. Render the prompt body via the caller-supplied
           ``prompt_body_renderer``.
        3. Capture the dispatch timestamp via
           ``dispatch_timestamp_factory`` (or
           :func:`_default_dispatch_timestamp_factory` when ``None``).
        4. Return a frozen :class:`SpecialistDispatchPayload`.

    If ``agent_definition_path`` does not exist,
    :exc:`FileNotFoundError` propagates unchanged (caller-contract;
    the orchestrator skill at runtime supplies the path it knows the
    file lives at — the substrate doesn't substitute defaults).
    """
    agent_definition_text = agent_definition_path.read_text(encoding="utf-8")
    prompt_body = prompt_body_renderer(
        agent_definition_text, story_doc_resolution, attempt_number
    )
    factory = dispatch_timestamp_factory or _default_dispatch_timestamp_factory
    dispatch_timestamp = factory()
    assert dispatch_timestamp.tzinfo is not None, (
        "build_dispatch_payload: dispatch_timestamp must be timezone-aware UTC; "
        "got naive datetime — programmer-error invariant"
    )
    prompt_id = _derive_prompt_id(story_id, specialist, attempt_number)
    return SpecialistDispatchPayload(
        specialist=specialist,
        story_id=story_id,
        attempt_number=attempt_number,
        acceptance_criteria=story_doc_resolution.acceptance_criteria,
        agent_definition_path=agent_definition_path,
        prompt_body=prompt_body,
        dispatch_timestamp=dispatch_timestamp,
        prompt_id=prompt_id,
    )


def default_prompt_body_renderer(
    agent_definition_text: str,
    story_doc_resolution: StoryDocResolution,
    attempt_number: int,
) -> str:
    """Canonical Task-tool-prompt renderer used by tests + smoke runs.

    Returns a structured string with four labeled sections; the
    section structure is the canonical Task-tool-prompt shape per
    ADR-004's "Task tool's prompt format is the dispatch contract
    surface". Intentionally plain and unfussy — complex template
    engines (Jinja2, Mustache) are out of scope. Future stories MAY
    introduce a richer renderer via the caller-injected
    ``prompt_body_renderer`` parameter on
    :func:`build_dispatch_payload`.
    """
    ac_lines = "\n".join(
        f"{ac.ac_id}: {ac.text}" for ac in story_doc_resolution.acceptance_criteria
    )
    return (
        "# Specialist instructions (from agent definition)\n"
        "\n"
        f"{agent_definition_text}\n"
        "\n"
        "# Story context\n"
        "\n"
        f"story_id: {story_doc_resolution.path.stem}\n"
        f"story_doc_path: {story_doc_resolution.path}\n"
        f"attempt_number: {attempt_number}\n"
        "\n"
        "# Acceptance criteria\n"
        "\n"
        f"{ac_lines}\n"
        "\n"
        "# Return contract\n"
        "\n"
        "Return a YAML envelope conforming to envelope.schema.yaml. Required "
        "fields: status, artifacts, findings, rationale. Specialist-specific "
        "fields per FR54/FR55/FR56 as applicable. NO flow-policy fields "
        "(next_action, recommendation, etc.) per FR52 / sensor-not-advisor."
    )


# --------------------------------------------------------------------------- #
# Diagnostic log persistence (AC-4)                                           #
# --------------------------------------------------------------------------- #


#: Log path template for NFR-O3 structured diagnostic logs. Encoded as
#: a ``str.format``-shaped template; the ``log_root`` argument to
#: :func:`persist_dispatch_log` provides the prefix at runtime. The
#: orchestrator skill at user runtime resolves ``log_root`` to
#: ``_bmad-output/qa-evidence/`` per the canonical user-installation
#: path (View 3 line 1171); tests use ``tmp_path``-rooted log roots.
LOG_PATH_TEMPLATE: str = "{story_id}/{run_id}/logs/{specialist}-{attempt_number}.log"


def persist_dispatch_log(
    payload: SpecialistDispatchPayload,
    return_envelope: dict,
    return_timestamp: datetime,
    log_root: pathlib.Path,
    *,
    run_id: str,
) -> pathlib.Path:
    """Write a structured JSON-serialized log to the canonical NFR-O3 path.

    JSON (NOT YAML) for log files: structured-logging convention; YAML
    is reserved for human-edited artifacts (run-state, schemas,
    fixtures); JSON is for machine-emitted artifacts (logs,
    telemetry).

    Atomic write via ``tempfile.NamedTemporaryFile`` + ``os.replace``
    mirroring Story 2.2's :func:`advance_run_state` precedent verbatim
    per Pattern 4 + NFR-R1.

    Pattern 5 loud-fail discipline: ``OSError`` from ``mkdir`` /
    ``tempfile`` / ``os.replace`` / ``os.fsync`` is propagated
    unchanged; the caller (the orchestrator skill at runtime) catches
    and surfaces via the orchestrator-event log.

    JSON payload fields (NFR-O3 + Story 2.12 AC-5):
        * ``dispatched_specialist`` — ``payload.specialist`` (kebab-case).
        * ``story_id`` — ``payload.story_id``.
        * ``attempt_number`` — 0-indexed retry counter.
        * ``agent_definition_path`` — string form of the agent file
          read AS DATA per FR62 + ADR-004.
        * ``acceptance_criteria`` — list of ``{ac_id, text}`` dicts.
        * ``dispatch_timestamp`` — ISO-8601 UTC.
        * ``return_timestamp`` — ISO-8601 UTC.
        * ``return_envelope`` — the validated envelope dict.
        * ``runtime_duration_ms`` — milliseconds elapsed between
          ``dispatch_timestamp`` and ``return_timestamp`` (``int``;
          additive per Story 2.12 AC-5; existing readers including
          Story 2.11's :func:`bundle_assembly.assemble_bundle` per
          its AC-5 read ONLY ``return_envelope`` and are unaffected).

    Args:
        payload: The :class:`SpecialistDispatchPayload` constructed by
            :func:`build_dispatch_payload`.
        return_envelope: The validated envelope dict the specialist
            returned (post :func:`validate_return_envelope`).
        return_timestamp: Timezone-aware UTC datetime at which the
            specialist's return text was captured. The defensive
            assertion ``return_timestamp.tzinfo is not None`` fires on
            naive datetimes — programmer-error invariant; firing means
            the caller passed a naive datetime, distinct from a
            user-facing failure mode.
        log_root: Caller-controlled prefix for the canonical
            :data:`LOG_PATH_TEMPLATE` resolution.
        run_id: Orchestrator-domain run identifier correlating
            dispatch with the run-state.yaml record per ADR-005
            Consequence 1.

    Returns:
        :class:`pathlib.Path` pointing at the written log file.
    """
    assert return_timestamp.tzinfo is not None, (
        "persist_dispatch_log: return_timestamp must be timezone-aware UTC; "
        "got naive datetime — programmer-error invariant"
    )

    duration_ms = int(
        (return_timestamp - payload.dispatch_timestamp).total_seconds() * 1000
    )
    if duration_ms < 0:
        raise ValueError(
            "persist_dispatch_log: negative runtime_duration_ms "
            f"({duration_ms} ms) — return_timestamp "
            f"({return_timestamp.isoformat()}) precedes dispatch_timestamp "
            f"({payload.dispatch_timestamp.isoformat()}); clock skew or "
            "monotonicity violation. Pattern 5 loud-fail: a negative duration "
            "is a programmer-error / NTP-step invariant violation, not a "
            "value to clamp silently."
        )

    log_path = log_root / LOG_PATH_TEMPLATE.format(
        story_id=payload.story_id,
        run_id=run_id,
        specialist=payload.specialist,
        attempt_number=payload.attempt_number,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)

    log_payload: dict[str, Any] = {
        "dispatched_specialist": payload.specialist,
        "story_id": payload.story_id,
        "attempt_number": payload.attempt_number,
        "agent_definition_path": str(payload.agent_definition_path),
        "acceptance_criteria": [
            {"ac_id": ac.ac_id, "text": ac.text}
            for ac in payload.acceptance_criteria
        ],
        "dispatch_timestamp": payload.dispatch_timestamp.isoformat(),
        "return_timestamp": return_timestamp.isoformat(),
        "return_envelope": return_envelope,
        # Story 2.12 AC-5: additive ``runtime_duration_ms`` field
        # (milliseconds elapsed between dispatch and return). Negative
        # values are loud-fail-rejected above per Pattern 5 — clock
        # skew / NTP backwards step is a programmer-error invariant,
        # not a value to silently clamp. Additive: existing readers
        # (Story 2.11's ``bundle_assembly`` per its AC-5 reads ONLY
        # ``return_envelope``) are unaffected.
        "runtime_duration_ms": duration_ms,
    }

    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        dir=log_path.parent,
        delete=False,
        encoding="utf-8",
        suffix=".tmp",
    )
    tmp_path = pathlib.Path(tmp.name)
    try:
        try:
            json.dump(log_payload, tmp, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        os.replace(tmp_path, log_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    return log_path


# --------------------------------------------------------------------------- #
# Return envelope validation (AC-5)                                           #
# --------------------------------------------------------------------------- #


class ReturnEnvelopeValidation(BaseModel):
    """Result of :func:`validate_return_envelope`.

    Frozen; sequence field is tuple-typed per Epic 1 retro Action #2.

    Field semantics:
        * ``valid`` — ``True`` iff ``errors`` is empty.
        * ``errors`` — tuple of human-readable per-error messages
          rendered by Story 1.2's ``format_errors`` for the
          validator's UX-aligned output shape.
        * ``validated_envelope`` — the input ``envelope_dict`` when
          ``valid=True``; ``None`` when ``valid=False``.
    """

    model_config = ConfigDict(frozen=True)

    valid: bool
    errors: tuple[str, ...]
    validated_envelope: dict[str, Any] | None


def validate_return_envelope(
    envelope_dict: dict[str, Any],
    schema: dict[str, Any] | None = None,
) -> ReturnEnvelopeValidation:
    """Validate a specialist return envelope against ``envelope.schema.yaml``.

    Composes :func:`loud_fail_harness.envelope_validator.validate_envelope`
    + :func:`loud_fail_harness.envelope_validator.format_errors`
    exclusively — no reimplementation of envelope validation logic.

    Args:
        envelope_dict: The dict-shape envelope the specialist returned
            (already YAML-parsed).
        schema: Optional pre-loaded envelope schema dict. When
            ``None``, the substrate resolves
            ``<repo-root>/schemas/envelope.schema.yaml`` via
            :func:`find_repo_root` at function-call time only (Epic 1
            retro Action #1).

    Returns:
        :class:`ReturnEnvelopeValidation` carrying ``valid``,
        ``errors``, and ``validated_envelope``.
    """
    if schema is None:
        schema = load_schema(find_repo_root() / "schemas" / "envelope.schema.yaml")
    errors = validate_envelope(envelope_dict, schema)
    if not errors:
        return ReturnEnvelopeValidation(
            valid=True, errors=(), validated_envelope=envelope_dict
        )
    error_strings = tuple(format_errors([err]).strip() for err in errors)
    return ReturnEnvelopeValidation(
        valid=False, errors=error_strings, validated_envelope=None
    )


def validate_return_envelope_strict(
    envelope_dict: dict[str, Any],
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Exception-flow variant of :func:`validate_return_envelope`.

    Returns the validated envelope dict on success; raises
    :exc:`EnvelopeValidationFailed` on failure. The variant exists for
    callers that prefer exception-based flow over result-object
    inspection; both shapes are first-class API.
    """
    result = validate_return_envelope(envelope_dict, schema)
    if not result.valid:
        raise EnvelopeValidationFailed(
            errors=result.errors, envelope_dict=envelope_dict
        )
    assert result.validated_envelope is not None
    return result.validated_envelope


class EnvelopeValidationFailed(Exception):
    """Raised by :func:`validate_return_envelope_strict` when the envelope fails validation.

    Pattern 5 named-invariant diagnostic. ``marker_class:
    ClassVar[None] = None`` — envelope validation failures are NOT
    loud-fail markers at MVP. Maps to ADR-004's ``silent-corruption``
    sub-cause but the current ``marker-taxonomy.yaml`` 1.1 enumeration
    does not include a ``specialist-envelope-invalid`` marker class;
    adding one would require a taxonomy MINOR bump per the file's
    documented bump rule + a corresponding
    ``examples/synthetic-stories/`` Layer C fixture per ADR-003
    substrate component 5 — both out of scope for THIS story per
    AC-10's "no taxonomy bump" scope discipline. Future Stories 6.x
    or an Epic-3 marker-bump may add the marker class.

    Attributes:
        errors: Tuple of human-readable per-error messages from
            :func:`validate_return_envelope`.
        envelope_dict: The envelope dict the caller passed; preserved
            for diagnostic correlation.
    """

    marker_class: ClassVar[None] = None

    def __init__(
        self,
        *,
        errors: tuple[str, ...],
        envelope_dict: dict[str, Any],
    ) -> None:
        self.errors: tuple[str, ...] = errors
        self.envelope_dict: dict[str, Any] = envelope_dict
        first_error = errors[0] if errors else "<no error messages>"
        more = f" ...({len(errors) - 1} more)" if len(errors) > 1 else ""
        super().__init__(
            f"EnvelopeValidationFailed: specialist envelope failed validation "
            f"against envelope.schema.yaml ({len(errors)} error(s)): "
            f"{first_error}{more}; the specialist's return text was "
            "structurally invalid for the orchestrator to consume; "
            "remediation targets the specialist's prompt or its "
            "agent-definition file's return-contract instructions — see "
            "_bmad-output/qa-evidence/{story_id}/{run_id}/logs/"
            "{specialist}-{attempt}.log for the verbatim return envelope"
        )


# --------------------------------------------------------------------------- #
# Wall-clock timeout exception (AC-6)                                         #
# --------------------------------------------------------------------------- #


class SpecialistTimeoutExceeded(Exception):
    """Raised when the orchestrator's per-specialist wall-clock timer fires.

    Pattern 5 named-invariant diagnostic carrying loud-fail marker
    class + sub-cause sourced VERBATIM from
    ``schemas/marker-taxonomy.yaml`` entry 7
    (``marker_class: specialist-timeout``,
    ``sub_classifications: [timeout-exceeded, context-budget-exceeded]``).

    THIS story emits ONLY ``timeout-exceeded``; ``context-budget-
    exceeded`` is reserved for context-tracking work in Epic 6 /
    Story 6.7 — NOT this story.

    .. note::
        If a future taxonomy MAJOR bump renames ``specialist-timeout``
        to a different identifier, the ``Literal[...]`` annotations on
        :attr:`marker_class` AND :attr:`sub_cause` MUST be updated in
        lockstep. The AC-9 test
        ``test_specialist_timeout_exceeded_marker_class_in_registry``
        fires if the taxonomy is edited without updating this
        exception.

    ## Emission protocol

    When this exception is raised at LLM-runtime (the orchestrator
    skill or :func:`make_task_tool_dispatch_callback`'s closure
    detects the wall-clock timeout has fired), the caller MUST:

        (1) Call ``validate_marker_emission(registry,
            SpecialistTimeoutExceeded.marker_class)`` per AC-2 — fail-
            fast at runtime if the registry doesn't carry the marker
            class (which would only happen if the taxonomy was
            tampered with mid-run).
        (2) Construct a ``specialist-returned`` orchestrator-event
            with ``status='fail'`` per
            :func:`make_specialist_returned_event` per AC-7 — the
            event's ``envelope_artifact_path`` field SHOULD point at
            a synthetic 'timeout-fail' envelope record (the substrate
            provides no helper for synthesizing this — it's the
            caller's call).
        (3) Emit the event via ``event_log_appender``.
        (4) Propagate or convert the exception per the orchestrator's
            flow policy (NOT the substrate's — sensor-not-advisor).
    """

    marker_class: ClassVar[Literal["specialist-timeout"]] = "specialist-timeout"
    sub_cause: ClassVar[Literal["timeout-exceeded"]] = "timeout-exceeded"

    def __init__(
        self,
        *,
        timeout_seconds: int,
        specialist: str,
        story_id: str,
        attempt_number: int,
    ) -> None:
        self.timeout_seconds: int = timeout_seconds
        self.specialist: str = specialist
        self.story_id: str = story_id
        self.attempt_number: int = attempt_number
        super().__init__(
            f"SpecialistTimeoutExceeded: specialist={specialist!r} "
            f"(story_id={story_id!r}, attempt={attempt_number}) exceeded the "
            f"wall-clock timeout of {timeout_seconds}s; the orchestrator MUST "
            f"emit the marker class {self.marker_class!r} (sub_classifications: "
            f"{self.sub_cause!r}) per marker-taxonomy.yaml entry 7 + NFR-P2; "
            "remediation targets the specialist's prompt size or evidence "
            "handling per the marker's diagnostic_pointer (see "
            "schemas/marker-taxonomy.yaml lines 122-131 for the actionable-"
            "fix-pointer)"
        )


# --------------------------------------------------------------------------- #
# Orchestrator-event emission helpers (AC-7)                                  #
# --------------------------------------------------------------------------- #


#: Type alias for the event-id factory parameter of the event-construction
#: helpers. A zero-arg callable returning a unique opaque identifier.
EventIdFactory = Callable[[], str]


def default_event_id_factory() -> str:
    """Canonical event-id factory used by tests + smoke runs.

    Returns a UUID-derived opaque identifier with the
    ``"ev-2-6-dispatch-"`` story-scoped prefix, paralleling Story 1.3's
    ``"ev-1-3-seed-0001"`` shape. Production callers (the orchestrator
    skill at runtime) MAY substitute a deterministic factory for
    replay-correlation work via the ``event_id_factory`` parameter on
    :func:`make_specialist_dispatched_event` /
    :func:`make_specialist_returned_event`.
    """
    return f"ev-2-6-dispatch-{uuid.uuid4().hex[:12]}"


def _derive_prompt_id(
    story_id: str,
    specialist: str,
    attempt_number: int,
) -> str:
    """Compute the orchestrator-internal correlation key for one dispatch.

    Called ONCE in :func:`build_dispatch_payload`; the result is stored
    on :class:`SpecialistDispatchPayload` so that both
    ``specialist-dispatched`` and ``specialist-returned`` events carry
    the identical value, satisfying ADR-006 Combo 3 / A3'.

    Snake_case prefix per Pattern 1; uniqueness enforced by the uuid
    suffix.
    """
    return (
        f"prompt-{story_id}-{specialist}-"
        f"{attempt_number}-{uuid.uuid4().hex[:8]}"
    )


def _load_event_schema() -> dict[str, Any]:
    """Resolve and load the orchestrator-event schema at function-call time.

    Module-private; Epic 1 retro Action #1 — NEVER at module import
    time.
    """
    return load_schema(find_repo_root() / "schemas" / "orchestrator-event.yaml")


def make_specialist_dispatched_event(
    payload: SpecialistDispatchPayload,
    *,
    event_id_factory: EventIdFactory,
    dispatch_seq: int | None = None,
) -> dict[str, Any]:
    """Construct a schema-valid ``specialist-dispatched`` event payload.

    Composes :func:`loud_fail_harness.event_validator.validate_event`
    exclusively for the defensive validation pass before return.
    Raises :exc:`EventConstructionFailed` if the constructed event
    does not validate against the live schema (firing means the
    substrate has a bug, not the caller).

    Args:
        payload: The :class:`SpecialistDispatchPayload` constructed by
            :func:`build_dispatch_payload`.
        event_id_factory: Caller-injected event-id factory (sensor-
            not-advisor — the substrate doesn't pick the id strategy).
        dispatch_seq: Optional sequence number for the dispatch
            (orchestrator-domain ordering hint).

    Returns:
        Schema-valid dict conforming to
        ``schemas/orchestrator-event.yaml``'s
        ``specialist-dispatched`` branch.
    """
    event_dict: dict[str, Any] = {
        "event_class": "specialist-dispatched",
        "event_id": event_id_factory(),
        "timestamp": payload.dispatch_timestamp.isoformat(),
        "story_id": payload.story_id,
        "specialist": payload.specialist,
        "prompt_id": payload.prompt_id,
        "retry_attempt": payload.attempt_number,
    }
    if dispatch_seq is not None:
        event_dict["dispatch_seq"] = dispatch_seq

    schema = _load_event_schema()
    errors = validate_event(event_dict, schema)
    if errors:
        raise EventConstructionFailed(
            event_class="specialist-dispatched",
            errors=tuple(str(err.message) for err in errors),
            event_dict=event_dict,
        )
    return event_dict


def make_specialist_returned_event(
    payload: SpecialistDispatchPayload,
    return_envelope: dict[str, Any],
    *,
    event_id_factory: EventIdFactory,
    return_timestamp: datetime,
    envelope_artifact_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Construct a schema-valid ``specialist-returned`` event payload.

    Composes :func:`loud_fail_harness.event_validator.validate_event`
    exclusively for the defensive validation pass before return.
    Raises :exc:`EventConstructionFailed` if the constructed event
    does not validate against the live schema.

    Args:
        payload: The :class:`SpecialistDispatchPayload` originally
            constructed at dispatch time.
        return_envelope: The validated envelope dict the specialist
            returned (post :func:`validate_return_envelope`). The
            ``status`` field is sourced from ``return_envelope["status"]``
            (defaulting to ``"fail"`` if missing).
        event_id_factory: Caller-injected event-id factory.
        return_timestamp: Timezone-aware UTC datetime at which the
            specialist's return text was captured.
        envelope_artifact_path: Optional on-disk path to the persisted
            envelope artifact (e.g., the path returned by
            :func:`persist_dispatch_log`).

    Returns:
        Schema-valid dict conforming to
        ``schemas/orchestrator-event.yaml``'s
        ``specialist-returned`` branch (post-bump 1.2 — includes
        ``decision-needed`` in the status enum per AC-8).
    """
    event_dict: dict[str, Any] = {
        "event_class": "specialist-returned",
        "event_id": event_id_factory(),
        "timestamp": return_timestamp.isoformat(),
        "story_id": payload.story_id,
        "specialist": payload.specialist,
        "prompt_id": payload.prompt_id,
        "retry_attempt": payload.attempt_number,
        "status": return_envelope.get("status", "fail"),
    }
    if envelope_artifact_path is not None:
        event_dict["envelope_artifact_path"] = str(envelope_artifact_path)

    schema = _load_event_schema()
    errors = validate_event(event_dict, schema)
    if errors:
        raise EventConstructionFailed(
            event_class="specialist-returned",
            errors=tuple(str(err.message) for err in errors),
            event_dict=event_dict,
        )
    return event_dict



def make_cost_event(
    payload: SpecialistDispatchPayload,
    *,
    return_envelope: dict[str, Any],
    return_timestamp: datetime,
    cost_delta_usd: float,
    otel_attributes: Mapping[str, Any],
    event_id_factory: EventIdFactory,
) -> dict[str, Any]:
    """Construct a schema-valid ``cost-event`` event payload (Story 6.4 / AC-1).

    Composes :func:`loud_fail_harness.event_validator.validate_event`
    exclusively for the defensive validation pass before return.
    Raises :exc:`EventConstructionFailed` if the constructed event
    does not validate against the live schema (firing means the
    substrate has a bug, not the caller).

    The function mirrors :func:`make_specialist_dispatched_event` /
    :func:`make_specialist_returned_event` byte-for-byte in shape per
    the dispatch-event-grouping convention. The four OTel pass-through
    attribute keys (``prompt.id``, ``claude_code.cost.usage``,
    ``claude_code.token.usage``, ``query_source``) are passed through
    from the caller-supplied ``otel_attributes`` mapping unchanged per
    Pattern 3 — the OTel-derived attributes preserve their dotted/mixed-
    case naming verbatim while the orchestrator-internal ``prompt_id``
    coexists as a distinct snake_case named field per the schema's
    documented dual-name boundary at
    ``schemas/orchestrator-event.yaml`` lines 376-381.

    Per ADR-006 Combo 3 / A3' the orchestrator-internal ``prompt_id``
    is read directly from ``payload.prompt_id`` — :func:`_derive_prompt_id`
    at module lines 1015-1033 is the single source of truth for the
    correlation key; ``make_cost_event`` does NOT re-derive it.

    Args:
        payload: The :class:`SpecialistDispatchPayload` originally
            constructed at dispatch time.
        return_envelope: The validated envelope dict the specialist
            returned (preserved for caller-side correlation; not
            consumed in the cost-event dict shape per the schema).
        return_timestamp: Timezone-aware UTC datetime at which the
            cost-event is recorded (typically the dispatch's return
            timestamp from :func:`make_specialist_returned_event`).
        cost_delta_usd: Cost incurred during this invocation in USD;
            must be ``>= 0`` per the schema's ``minimum: 0`` constraint.
        otel_attributes: Mapping of OTel-derived attribute keys (with
            their original dotted/mixed-case naming) to their values.
            Caller (orchestrator runtime) reads these from the OTel
            telemetry source and passes them through unchanged per
            Pattern 3. Keys present in the mapping flow through to the
            event dict verbatim; absent keys are omitted (the schema
            does not require any of the four OTel pass-through keys).
        event_id_factory: Caller-injected event-id factory (sensor-
            not-advisor — the substrate doesn't pick the id strategy).

    Returns:
        Schema-valid dict conforming to
        ``schemas/orchestrator-event.yaml``'s ``cost-event`` branch
        (lines 375-416). Required fields: ``event_class``, ``event_id``,
        ``timestamp``, ``story_id``, ``prompt_id``, ``retry_attempt``,
        ``specialist``, ``cost_delta_usd``. Optional OTel pass-through
        attribute keys are included iff present in ``otel_attributes``.

    Raises:
        EventConstructionFailed: The constructed dict does not validate
            against the schema. Pattern 5 named-invariant diagnostic;
            firing indicates a substrate bug (a malformed
            ``cost_delta_usd`` magnitude or a typo in the OTel attribute
            key set), NOT a caller error.
    """
    _ = return_envelope  # preserved on signature for caller-side correlation
    event_dict: dict[str, Any] = {
        "event_class": "cost-event",
        "event_id": event_id_factory(),
        "timestamp": return_timestamp.isoformat(),
        "story_id": payload.story_id,
        "prompt_id": payload.prompt_id,
        "retry_attempt": payload.attempt_number,
        "specialist": payload.specialist,
        "cost_delta_usd": cost_delta_usd,
    }
    # Pattern 3 OTel pass-through — keys preserve their dotted/mixed-case
    # naming verbatim. Only the four documented attribute keys are admitted;
    # other entries in ``otel_attributes`` are silently ignored (the schema
    # forbids ``additionalProperties`` so smuggling unknown keys would fail
    # validation loudly anyway).
    for otel_key in (
        "prompt.id",
        "claude_code.cost.usage",
        "claude_code.token.usage",
        "query_source",
    ):
        if otel_key in otel_attributes:
            event_dict[otel_key] = otel_attributes[otel_key]

    schema = _load_event_schema()
    errors = validate_event(event_dict, schema)
    if errors:
        raise EventConstructionFailed(
            event_class="cost-event",
            errors=tuple(str(err.message) for err in errors),
            event_dict=event_dict,
        )
    return event_dict


def record_cost_streaming_at_return_boundary(
    payload: SpecialistDispatchPayload,
    *,
    return_envelope: dict[str, Any],
    return_timestamp: datetime,
    otel_pipeline: "OtelPipelineProtocol",
    cost_delta_usd: float,
    otel_attributes: Mapping[str, Any],
    event_id_factory: EventIdFactory,
    run_state: "RunState",
    ceiling_usd: float,
    line_appender: Callable[[str], None],
) -> tuple["CollectionResult", "CostStreamingResult"]:
    """Compose Story 6.4's cost-telemetry collect with Story 6.5's
    in-flight cost streaming + threshold detection at a specialist-return
    boundary (Story 6.5 / AC-1, AC-2, AC-3).

    Composition flow (the seam-transition boundary helper):

        1. Call :func:`loud_fail_harness.cost_telemetry.collect` to
           produce the :class:`CollectionResult` carrying the
           ``cost_event`` + ``aggregation`` +
           ``marker_classification`` (the latter is non-``None`` on
           OTel-pipeline failure per Story 6.4's graceful-degrade
           contract).
        2. On ``CollectionResult.marker_classification is not None``
           (cost-telemetry-unavailable from 6.4) the function SKIPS
           the cost-streaming half — degraded telemetry cannot drive a
           meaningful threshold check. The aggregation is empty in the
           degraded case; an empty per-boundary stream line would
           fabricate a false ``total=$0.00`` signal violating AC-2's
           "no fabricated zero values" intent inherited from 6.4 AC-3.
           ``line_appender`` is NOT called; the returned
           :class:`CostStreamingResult.marker_classifications_to_append`
           is empty.
        3. On a green :class:`CollectionResult` the function reads
           ``run_state.cost_to_date_by_specialist`` (sum across non-
           ``None`` per-specialist values BEFORE the cost-counter
           update) for ``previous_running_total_usd``; reads
           ``run_state.active_markers`` for ``already_emitted_markers``;
           calls :func:`loud_fail_harness.cost_streaming.stream_cost_at_boundary`
           which appends the cost-line via ``line_appender``, detects
           threshold crossings, and (on first-crossings) appends the
           prominent-warning line(s).

    Pattern 4 batch-write rule (architecture.md lines 977-981): this
    function does NOT call
    :func:`loud_fail_harness.run_state.advance_run_state`. The
    orchestrator caller composes the returned
    ``CollectionResult.aggregation`` (via
    :func:`loud_fail_harness.cost_telemetry.update_run_state_cost_counters`)
    + ``CostStreamingResult.marker_classifications_to_append`` INTO
    the next-state argument it passes to ``advance_run_state``;
    there is exactly one atomic write per seam transition.

    Args:
        payload: The :class:`SpecialistDispatchPayload` originally
            constructed at dispatch time.
        return_envelope: The validated envelope dict the specialist
            returned (passed through to :func:`cost_telemetry.collect`
            for caller-side correlation).
        return_timestamp: Timezone-aware UTC datetime at which the
            specialist returned (used as the cost-event timestamp AND
            the boundary timestamp the cost-stream line is rendered
            from).
        otel_pipeline: The bridge-layer
            :class:`OtelPipelineProtocol` implementation backing the
            OTLP cost-event read.
        cost_delta_usd: Cost incurred during this invocation in USD;
            forwarded to :func:`cost_telemetry.collect` for the
            cost-event dict construction AND to
            :func:`cost_streaming.stream_cost_at_boundary` for the
            cost-stream-line ``delta=$<x.xx>`` field.
        otel_attributes: Mapping of OTel-derived attribute keys (per
            Pattern 3 dotted/mixed-case naming).
        event_id_factory: Caller-injected event-id factory.
        run_state: The :class:`RunState` BEFORE the cost-counter
            update + marker append. Read for
            ``previous_running_total_usd`` (from
            ``cost_to_date_by_specialist``) and
            ``already_emitted_markers`` (from ``active_markers``).
        ceiling_usd: Per-story cost ceiling (typically resolved from
            ``_bmad/automation/config.yaml`` via
            :func:`loud_fail_harness.cost_streaming.resolve_per_story_cost_ceiling_usd`).
        line_appender: I/O boundary the caller injects per the
            sensor-not-advisor / caller-injected-factory convention.
            Called once for the cost-stream line and additionally
            once or twice for warning line(s) on threshold-crossing
            boundaries.

    Returns:
        Tuple of (:class:`CollectionResult`,
        :class:`CostStreamingResult`). The first is the unchanged
        return value of :func:`cost_telemetry.collect`; the second
        is the streaming-half result (empty + no-crossing on the
        graceful-degrade path; populated otherwise).

    Raises:
        Never raises on a ceiling crossing per NFR-O8 verbatim — the
        loop continues; the practitioner decides whether to abort.
        Underlying exceptions from
        :func:`cost_telemetry.collect` (e.g.,
        :exc:`EventConstructionFailed` on schema mismatch; unknown
        OTel-pipeline exceptions per Pattern 5) propagate per the
        loud-fail doctrine.
    """
    from loud_fail_harness.cost_streaming import (
        CostStreamingResult,
        CostThresholdDecision,
        stream_cost_at_boundary,
    )
    from loud_fail_harness.cost_telemetry import collect

    collection_result = collect(
        payload,
        otel_pipeline=otel_pipeline,
        return_envelope=return_envelope,
        return_timestamp=return_timestamp,
        cost_delta_usd=cost_delta_usd,
        otel_attributes=otel_attributes,
        event_id_factory=event_id_factory,
    )

    if collection_result.marker_classification is not None:
        # Graceful-degrade: cost-telemetry-unavailable from Story 6.4.
        # Skip the streaming half — empty aggregation cannot drive a
        # meaningful threshold check; emitting total=$0.00 would
        # fabricate a false zero per AC-2's "no fabricated zero values"
        # intent inherited from 6.4 AC-3. The cost-telemetry-unavailable
        # marker is already in the CollectionResult for the orchestrator
        # to append.
        return collection_result, CostStreamingResult(
            running_total_usd=0.0,
            marker_classifications_to_append=(),
            threshold_decision=CostThresholdDecision(
                marker_classification=None,
                is_first_75pct_crossing=False,
                is_first_100pct_crossing=False,
            ),
        )

    cost_to_date = run_state.cost_to_date_by_specialist
    previous_running_total_usd = sum(
        v
        for v in (
            cost_to_date.dev,
            cost_to_date.review_bmad,
            cost_to_date.qa,
            cost_to_date.lad,
        )
        if v is not None
    )

    streaming_result = stream_cost_at_boundary(
        aggregation=collection_result.aggregation,
        specialist=payload.specialist,
        retry_attempt=payload.attempt_number,
        cost_delta_usd=cost_delta_usd,
        ceiling_usd=ceiling_usd,
        previous_running_total_usd=previous_running_total_usd,
        already_emitted_markers=tuple(run_state.active_markers),
        boundary_timestamp=return_timestamp,
        line_appender=line_appender,
    )

    return collection_result, streaming_result


class EventConstructionFailed(Exception):
    """Raised by event-construction helpers when the constructed event fails schema validation.

    Pattern 5 named-invariant diagnostic. ``marker_class:
    ClassVar[None] = None`` — the substrate's event-construction
    failure is a programmer-error invariant (the substrate built an
    event that doesn't validate against its own schema; firing means
    the substrate has a bug, not the caller); not a runtime-degradation
    marker.

    Attributes:
        event_class_name: Which event class the helper was trying to
            construct (``"specialist-dispatched"`` or
            ``"specialist-returned"``). Named ``event_class_name`` to
            avoid shadowing the class-level ``marker_class`` attribute
            convention.
        errors: Tuple of schema-validation error messages.
        event_dict: The dict the helper built; preserved for
            diagnostic correlation.
    """

    marker_class: ClassVar[None] = None

    def __init__(
        self,
        *,
        event_class: str,
        errors: tuple[str, ...],
        event_dict: dict[str, Any],
    ) -> None:
        self.event_class_name: str = event_class
        self.errors: tuple[str, ...] = errors
        self.event_dict: dict[str, Any] = event_dict
        first_error = errors[0] if errors else "<no error messages>"
        more = f" ...({len(errors) - 1} more)" if len(errors) > 1 else ""
        super().__init__(
            f"EventConstructionFailed: substrate built an invalid "
            f"{event_class!r} event ({len(errors)} schema validation "
            f"error(s)): {first_error}{more}; this indicates a substrate "
            "bug — file an issue against the bmad-autopilot repo with the "
            "failing event_dict + the schemas/orchestrator-event.yaml version"
        )


# --------------------------------------------------------------------------- #
# Task-tool dispatch callback Protocol + factory (AC-10)                      #
# --------------------------------------------------------------------------- #


#: Type alias for the orchestrator-event log appender callback. Mirrors
#: :data:`loud_fail_harness.lifecycle_state_machine.EventLogAppender` verbatim
#: (a callable accepting one schema-validated event dict and persisting it to
#: whatever log surface the caller owns). Defined locally rather than imported
#: from ``lifecycle_state_machine`` to keep this substrate's intra-package
#: import set pinned to the documented allowlist
#: (envelope_validator, reconciler, _shared, event_validator,
#: orchestrator_run_entry) per Task 2's implementation guide. The two type
#: aliases are structurally identical; Story 2.5's wildcard
#: ``DispatchCallback = Callable[..., DispatchCallbackResult]`` accepts both
#: forms structurally.
EventLogAppender = Callable[[dict[str, Any]], None]


@runtime_checkable
class TaskToolDispatchCallback(Protocol):
    """Formal Protocol for the Task-tool dispatch callback.

    Names the keyword-only call shape that
    :func:`loud_fail_harness.orchestrator_run_entry.run_story_loop_entry`
    invokes at step (6). Structurally compatible with Story 2.5's
    wildcard
    :data:`loud_fail_harness.orchestrator_run_entry.DispatchCallback`
    so NO edit to ``orchestrator_run_entry.py`` is required at this
    story's site (Story 2.5's wildcard accepts any callable matching
    the keyword surface; this Protocol is the named-form that
    downstream tests can use for type-strict assertions).

    The Protocol is :func:`typing.runtime_checkable` so callers may
    assert instances structurally with ``isinstance(closure,
    TaskToolDispatchCallback)``.

    Honors Story 2.5's deferred-work item (2026-04-28) verbatim:
    "DispatchCallback uses Callable[..., DispatchCallbackResult]
    wildcard — can be tightened to a named Protocol in Story 2.6 when
    the real callback signature is known." The named form lands HERE;
    the upstream wildcard at ``orchestrator_run_entry.py`` is left
    unchanged because tightening it would couple the two modules
    (creating a circular-import risk via the
    ``StoryDocResolution`` / ``AcceptanceCriterion`` /
    ``DispatchCallbackResult`` round-trip). Defer the upstream
    tightening to a future cleanup story.
    """

    def __call__(
        self,
        *,
        specialist: str,
        story_id: str,
        run_state_path: pathlib.Path,
        story_doc_resolution: StoryDocResolution,
        event_log_appender: EventLogAppender,
    ) -> DispatchCallbackResult:
        ...


def make_task_tool_dispatch_callback(
    *,
    registry: MarkerClassRegistry,
    log_root: pathlib.Path,
    agent_definition_dir: pathlib.Path,
    payload_builder: Callable[..., SpecialistDispatchPayload] | None = None,
    envelope_validator: Callable[[dict[str, Any]], ReturnEnvelopeValidation] | None = None,
    event_id_factory: EventIdFactory | None = None,
    timeout_seconds: int = 900,
) -> TaskToolDispatchCallback:
    """Factory returning a :class:`TaskToolDispatchCallback` closure.

    The closure closes over the configured registry / log root / agent
    dir / timeout (default 15 min per NFR-P2 line 935). The
    ``timeout_seconds`` parameter is configurable per-callable but NOT
    per-call (per-call configurability is Epic 5's retry-loop
    responsibility). Configurable parameter — config.yaml plumbing
    lands in Story 7.5's ``_bmad/automation/config.yaml`` scaffold,
    NOT this story.

    .. note::
        The closure's body is a thin Python shim that REQUIRES the
        LLM at runtime to invoke Task tool externally. The closure
        itself raises :exc:`NotImplementedError` if invoked from pure
        Python without LLM context — a deliberate substrate-vs-LLM-
        runtime boundary marker per ADR-004's substrate-vs-LLM-
        runtime split. The LLM-runtime invocation is the canonical
        path per ``skills/bmad-automation/steps/dispatch.md``; tests
        mock the closure's body at the call site rather than invoking
        it directly.

    Args:
        registry: The pre-loaded :class:`MarkerClassRegistry` (the
            orchestrator skill loads this once per ``/bmad-automation
            run`` invocation).
        log_root: Caller-controlled prefix for the canonical
            :data:`LOG_PATH_TEMPLATE` resolution (typically
            ``_bmad-output/qa-evidence/`` per View 3 line 1171).
        agent_definition_dir: Directory under which the agent-definition
            files live (typically ``agents/`` per Stories 2.8 / 2.9 /
            2.10's landing).
        payload_builder: Optional override for the payload-construction
            helper. Defaults to :func:`build_dispatch_payload`.
        envelope_validator: Optional override for the envelope-validation
            helper. Defaults to :func:`validate_return_envelope`.
        event_id_factory: Optional override for the event-id factory.
            Defaults to :func:`default_event_id_factory`.
        timeout_seconds: Wall-clock timeout per dispatch in seconds.
            Default 900 (15 min) per NFR-P2.

    Returns:
        A :class:`TaskToolDispatchCallback` closure structurally
        compatible with Story 2.5's wildcard
        :data:`DispatchCallback`.
    """
    # The substrate-injected helpers (used by tests via mock-patching
    # at the substrate's import site, OR by the LLM-runtime protocol
    # via direct invocation per ``steps/dispatch.md``). Reading the
    # parameters once at factory-construction time captures the
    # configuration in the closure's lexical scope.
    _registry = registry
    _log_root = log_root
    _agent_definition_dir = agent_definition_dir
    _payload_builder = payload_builder or build_dispatch_payload
    _envelope_validator = envelope_validator or validate_return_envelope
    _event_id_factory = event_id_factory or default_event_id_factory
    _timeout_seconds = timeout_seconds

    def _closure(
        *,
        specialist: str,
        story_id: str,
        run_state_path: pathlib.Path,
        story_doc_resolution: StoryDocResolution,
        event_log_appender: EventLogAppender,
    ) -> DispatchCallbackResult:
        """Closed-over Task-tool-dispatch callback.

        See ``skills/bmad-automation/steps/dispatch.md`` for the
        canonical LLM-runtime invocation protocol; the closure raises
        :exc:`NotImplementedError` if invoked from pure Python without
        the LLM-runtime context.
        """
        # Reference closure-captured config so static analyzers do not
        # flag the parameters as unused; this also documents which
        # configuration the LLM-runtime protocol must apply.
        _logger.debug(
            "task-tool-dispatch-callback invoked: specialist=%s story_id=%s "
            "run_state_path=%s story_doc_path=%s appender_type=%s "
            "registry_size=%d log_root=%s agent_dir=%s timeout_s=%d",
            specialist,
            story_id,
            run_state_path,
            story_doc_resolution.path,
            type(event_log_appender).__name__,
            len(_registry.marker_classes),
            _log_root,
            _agent_definition_dir,
            _timeout_seconds,
        )
        # Reference the substrate-injected helpers so they aren't
        # flagged as unused; the LLM-runtime protocol composes them at
        # the appropriate seam per skills/bmad-automation/steps/dispatch.md.
        _ = _payload_builder
        _ = _envelope_validator
        _ = _event_id_factory
        raise NotImplementedError(
            "Task tool invocation is LLM-runtime; see "
            "skills/bmad-automation/steps/dispatch.md for the protocol"
        )

    return _closure


__all__ = [
    "MarkerClassRegistry",
    "load_marker_class_registry",
    "validate_marker_emission",
    "UnknownMarkerClass",
    "SpecialistDispatchPayload",
    "build_dispatch_payload",
    "LOG_PATH_TEMPLATE",
    "persist_dispatch_log",
    "ReturnEnvelopeValidation",
    "validate_return_envelope",
    "EnvelopeValidationFailed",
    "SpecialistTimeoutExceeded",
    "make_specialist_dispatched_event",
    "make_specialist_returned_event",
    "default_event_id_factory",
    "TaskToolDispatchCallback",
    "make_task_tool_dispatch_callback",
]
