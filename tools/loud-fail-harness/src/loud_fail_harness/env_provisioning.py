"""Orchestrator-owned env-lifecycle primitives (Story 4.3).

FR7 + NFR-S6 + Pattern 5 + ADR-001 cell-1 portable surface. Pure-library
substrate consumed by the orchestrator skill at the ``review → qa``
seam. Composes Story 2.6's marker-class registry, Story 2.2's atomic-
write discipline, and Story 1.3's event-validation contract verbatim.

Architectural placement (parallel to Story 4.2's
:mod:`loud_fail_harness.qa_plan_drift` and Story 2.4's
:mod:`loud_fail_harness.lifecycle_state_machine`): this module is a
**substrate library NOT a sixth substrate component**. ADR-003
Consequence 1 enumerates exactly five substrate components
(architecture.md lines 311-315); THIS module is a substrate
**library** consumed by the orchestrator skill at the
``review → qa`` seam to provision a deterministic env BEFORE QA
dispatch and tear it down AFTER QA completion. It is structurally a
pure-library sibling of Story 4.1's
:mod:`loud_fail_harness.qa_behavioral_plan` and Story 4.2's
:mod:`loud_fail_harness.qa_plan_drift`. The substrate-component count
stays at FIVE; the harness module count grows by one.

Procedural checklist (verbatim epic AC at epics.md lines 1858-1885):

    1. Orchestrator reaches ``current_state="review"`` AND latest
       specialist envelope's ``status="pass"`` (the BMAD-lifecycle
       precondition for ``review → qa``).
    2. Orchestrator reads the story's ``project_type`` from
       ``_bmad/automation/qa-runbook.yaml`` (the practitioner's
       runbook stub Story 7.5 will scaffold; THIS story consumes
       the runbook AS DATA).
    3. Orchestrator calls :func:`cleanup_orphan_processes` to sweep
       stale ports/PIDs from prior crashed runs FIRST (orphan
       cleanup is BEFORE fresh provisioning per epics.md line
       1874-1878).
    4. Orchestrator calls :func:`allocate_ephemeral_port` to claim a
       fresh ephemeral port (NFR-S6: ports are allocated dynamically;
       no hardcoded port numbers).
    5. Orchestrator calls :func:`provision_env` — on success the
       run-state's ``provisioned_env`` field is populated AND an
       ``env-provisioned`` event is appended to the events log; on
       failure :exc:`EnvProvisioningFailed` carries the structured
       :class:`EnvSetupFailureEmission`.
    6. On :exc:`EnvProvisioningFailed`, the orchestrator MUST leave
       ``current_state`` at ``"review"`` per the verbatim epic AC at
       epics.md line 1881 ("the story does NOT enter the ``qa``
       state — remains in ``review``"); ``commit_transition`` is
       NEVER called; the env-setup-failed marker is surfaced via the
       existing terminal-stream + bundle-render paths; Story 4.10's
       escalation routing consumes the structured emission.
    7. On success, the orchestrator dispatches QA via Story 2.6's
       existing ``make_task_tool_dispatch_callback`` path WITH the
       run-state's ``provisioned_env`` field surfaced into the QA
       dispatch payload (so QA can observe the env it has been
       handed without ever provisioning it itself, preserving FR7's
       invariant).
    8. After QA return (regardless of pass / fail / blocked), the
       orchestrator calls :func:`teardown_env` BEFORE making the
       next BMAD-lifecycle decision — teardown is unconditional
       after QA completion per epics.md line 1869.

Marker-class linkage:
    The ``env-setup-failed`` marker class exists in
    ``schemas/marker-taxonomy.yaml`` line 102 with the three
    sub-classifications at lines 110-113 (``port-bind-failed``,
    ``playwright-launch-failed``, ``dev-server-not-ready``);
    THIS module's :data:`EnvSetupFailureSubCause` mirrors that enum
    byte-for-byte. The ``orphan-process-cleanup`` marker class
    exists at line 172. Both are consumed AS-IS — Story 4.3 does
    NOT bump :file:`marker-taxonomy.yaml`.

Orchestrator-event linkage:
    The ``env-provisioned`` and ``env-torn-down`` event classes
    exist in ``schemas/orchestrator-event.yaml`` from the Story 1.3
    / 2.4 era at lines 92-94 (event_class enum) + lines 302-346
    (per-class ``oneOf`` branches); THIS module composes those event
    classes AS-IS. Story 4.3 does NOT bump
    :file:`orchestrator-event.yaml`.

Upstream-consumer linkage:
    ``skills/bmad-automation/steps/env-provisioning.md`` (NEW in
    THIS story) is the LLM-runtime protocol that the orchestrator
    follows at the ``review → qa`` seam. It composes the public-API
    symbols enumerated below — :func:`allocate_ephemeral_port`,
    :func:`provision_env`, :func:`teardown_env`,
    :func:`cleanup_orphan_processes`, :func:`surface_env_setup_failure`
    — by symbol name + path-form citation discipline.

Downstream-consumer linkage:
    * Story 4.4 (web Playwright provisioner) implements the
      :class:`Provisioner` Protocol against the actual
      ``subprocess.Popen``-of-dev-server + Playwright-MCP-availability-check
      path; it is a sibling pure-library module, NOT an extension of
      THIS module.
    * Story 4.5 (API HTTP provisioner) implements the
      :class:`Provisioner` Protocol against the actual
      ``subprocess.Popen``-of-API-server + HTTP-availability-check
      path.
    * Story 4.10 (env-setup-fail escalation routing) consumes the
      :class:`EnvSetupFailureEmission` returned by
      :func:`surface_env_setup_failure` and routes it through the
      verification-fail / env-setup-fail escalation contracts. THIS
      module emits + structures; Story 4.10 routes.
    * Story 4.12 (evidence-persistence size budgets) reads the QA
      evidence root after QA return to enforce truncation; the
      :func:`teardown_env` invariant ("evidence root is NEVER opened,
      listed, mutated, or referenced") is what makes Story 4.12's
      composition possible.

Structural-not-era-based emission rule:
    The ``env-setup-failed`` marker emits iff :func:`provision_env`
    raises :exc:`EnvProvisioningFailed`. Story 4.10's escalation
    routing thickens visibility further per the verbatim epic AC at
    epics.md line 1882 without modifying THIS module's emission
    code — same posture Story 3.4 codified for
    ``walking-skeleton-bundle`` at architecture.md line 1581.

QA-independence-from-TEA-artifacts invariant (FR16, PRD line 830):
    Env provisioning reads ONLY the ``project_type`` field from
    ``qa-runbook.yaml`` (consumed by the LLM-runtime protocol, NOT
    by this library) and the run-state's ``story_id`` (consumed via
    the explicit function arguments). Env provisioning does NOT
    read TEA test files, dev tests, review findings, or commit
    diffs. The invariant is structurally encoded by the function
    signatures: every public function accepts a story_id +
    project_type explicitly; no TEA-artifact channel exists.

Cross-component reuse posture (Story 1.10b precedent):
    * Pydantic v2 :class:`pydantic.BaseModel` + :class:`pydantic.ConfigDict`
      — REUSED (already pinned by stories 1.1 / 1.2 / 1.10b / 4.1
      / 4.2).
    * Story 2.6's :mod:`loud_fail_harness.specialist_dispatch` —
      REUSED for :class:`MarkerClassRegistry` +
      :func:`validate_marker_emission` + :exc:`UnknownMarkerClass`.
    * Story 1.3's :mod:`loud_fail_harness.event_validator` —
      REUSED for :func:`validate_event` (defensive event-validation
      composition per AC-3).
    * Story 1.1's :mod:`loud_fail_harness._shared` — REUSED for
      :func:`load_schema` (the schema-load primitive shared with
      Story 2.6's dispatch helpers).
    * No new runtime dependencies. No file I/O on configs. No
      subprocess invocation (project-type-specific provisioners are
      Stories 4.4 / 4.5).

The four orchestrator-owned env-lifecycle primitives:

    * :func:`allocate_ephemeral_port` — socket-bind-and-close
      ephemeral allocation (the OS picks a free port from its
      ephemeral range; the function trusts the OS's ephemeral
      range; the race-condition window between port-release and
      provisioner-bind is inherent to the pattern and is the
      provisioner's responsibility to handle).
    * :func:`provision_env` — composes the project-type-keyed
      provisioner callable, persists the resulting
      :class:`ProvisionedEnv` to ``run-state.yaml``'s NEW
      ``provisioned_env`` top-level field via an atomic-write
      helper that mirrors Story 2.2's tempfile + os.replace
      discipline byte-for-byte, constructs and emits the
      ``env-provisioned`` orchestrator event.
    * :func:`teardown_env` — calls the teardown callable to
      terminate spawned processes cleanly, asserts the evidence
      root is NOT touched by teardown (Story 4.12 owns evidence
      persistence), clears ``provisioned_env`` from run-state,
      emits the ``env-torn-down`` event with ``outcome="clean"``.
    * :func:`cleanup_orphan_processes` — consumes a project-type-
      agnostic orphan probe + terminator pair, terminates each
      orphan, emits one
      :class:`MarkerEmissionRecord` per cleaned-up port via the
      registry, emits a single ``env-torn-down`` event with
      ``outcome="orphan-process-cleanup"`` summarizing the sweep.

Plus the two-channel atomic-emission helper:

    * :func:`surface_env_setup_failure` — atomic-on-failure
      registry validation + marker-record construction +
      diagnostic structuring (parallel to Story 4.2's
      :func:`loud_fail_harness.qa_plan_drift.surface_plan_drift`
      shape verbatim).

Sensor-not-advisor (PRD-level invariant + Pattern 5):
    The library COMPOSES the env-lifecycle primitives + RETURNS
    the structured emissions; it does NOT decide flow policy
    (Story 4.10's escalation contract is the consumer; THIS module
    produces the structured emission, that module routes it). It
    does NOT log, does NOT print, does NOT advance the run-state's
    ``current_state`` field — the BMAD-lifecycle ``current_state``
    is owned by Story 2.4's :mod:`lifecycle_state_machine`'s
    :func:`commit_transition` exclusively.

Atomic-on-failure invariant (Pattern 5; mirrors Stories 3.3 / 4.2):
    Every public function in this module is atomic-on-failure: on
    any internal step's exception, no partial run-state is left,
    no partial event is appended, no partial marker is constructed.
    The caller observes either complete success OR a single named-
    invariant exception (no side effects committed beyond the
    exception's structured payload).

``find_repo_root()`` discipline (Epic 1 retro Action #1 resolution):
    :func:`_load_event_schema` resolves the schema path at
    function-call time via :func:`loud_fail_harness._shared.find_repo_root`;
    NEVER at module import time. The
    :func:`_set_provisioned_env` and :func:`_clear_provisioned_env`
    helpers take ``run_state_path: pathlib.Path`` from the caller
    (caller-controlled location is the right default — the
    orchestrator skill knows where its run-state lives; tests use
    ``tmp_path`` fixtures).

Determinism:
    * :class:`ProvisionedEnv`, :class:`EnvSetupFailureDiagnostic`,
      :class:`EnvSetupFailureEmission`, and
      :class:`MarkerEmissionRecord` use Pydantic v2 frozen
      configuration; field declaration order is load-bearing for
      byte-stable ``model_dump_json()`` output (parallel to 1.4 /
      1.5 / 1.6 / 1.7 / 1.8 / 1.9 / 1.10a / 1.10b / 4.1 / 4.2
      discipline).
    * :func:`_atomic_write_run_state_dict` writes a deterministic
      YAML body (``yaml.safe_dump(..., sort_keys=False)`` preserves
      Python-dict-insertion order) so two calls against equal
      arguments produce byte-identical files modulo the temp-file
      path collision-resistance suffix.
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import socket
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, cast, runtime_checkable

import yaml
from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness._shared import find_repo_root, load_schema
from loud_fail_harness.event_validator import validate_event
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

#: The marker-class string identifier emitted on env-provisioning
#: failure (Story 1.4 enumeration; ``schemas/marker-taxonomy.yaml``
#: line 102). Consumed AS-IS; THIS module is the FIRST runtime
#: emitter of the marker for the env-provisioning surface. Mirrors
#: Story 3.3's :data:`REVIEW_LAYER_FAILED_MARKER` and Story 4.2's
#: :data:`PLAN_DRIFT_DETECTED_MARKER` symbolic-constant discipline.
ENV_SETUP_FAILED_MARKER: str = "env-setup-failed"

#: The marker-class string identifier emitted per cleaned-up orphan
#: process (Story 1.4 enumeration; ``schemas/marker-taxonomy.yaml``
#: line 172). Consumed AS-IS.
ORPHAN_PROCESS_CLEANUP_MARKER: str = "orphan-process-cleanup"

#: The orchestrator-event class identifier for successful env
#: provisioning (``schemas/orchestrator-event.yaml`` line 92 + the
#: per-class ``oneOf`` branch at lines 302-325). Consumed AS-IS.
_ENV_PROVISIONED_EVENT_CLASS: str = "env-provisioned"

#: The orchestrator-event class identifier for env teardown
#: (``schemas/orchestrator-event.yaml`` line 93 + the per-class
#: ``oneOf`` branch at lines 326-346). Consumed AS-IS.
_ENV_TORN_DOWN_EVENT_CLASS: str = "env-torn-down"

#: The run-state.yaml top-level field name added by THIS story's
#: AC-6 schema bump. The :func:`_set_provisioned_env` and
#: :func:`_clear_provisioned_env` helpers mutate this field
#: atomically; ``current_state``, ``story_id``, and other top-level
#: fields are never touched by THIS module.
_PROVISIONED_ENV_FIELD: str = "provisioned_env"


#: Closed enum for the ``project_type`` parameter and the
#: :class:`ProvisionedEnv` ``env_kind`` field. Mirrors
#: ``schemas/orchestrator-event.yaml`` lines 318 + 343's
#: ``env_kind`` enum byte-for-byte. Kebab-case identifiers per
#: Pattern 1's identifier boundary (architecture.md lines 932-935).
EnvKind = Literal["web", "api"]


#: Closed enum for :class:`MarkerEmissionRecord.sub_cause` when
#: ``marker_class == "env-setup-failed"``. Mirrors
#: ``schemas/marker-taxonomy.yaml`` lines 110-113's
#: ``env-setup-failed.sub_classifications`` enum byte-for-byte;
#: kebab-case identifiers per Pattern 1.
EnvSetupFailureSubCause = Literal[
    "port-bind-failed",
    "playwright-launch-failed",
    "dev-server-not-ready",
]


#: Closed enum for the :class:`make_env_torn_down_event` ``outcome``
#: parameter. Mirrors ``schemas/orchestrator-event.yaml`` line 346's
#: ``outcome`` enum byte-for-byte; kebab-case identifiers per
#: Pattern 1.
EnvTeardownOutcome = Literal["clean", "orphan-process-cleanup"]


#: Type alias for the orchestrator-event log appender callback.
#: Caller-controlled per Story 2.4's
#: :data:`loud_fail_harness.lifecycle_state_machine.EventLogAppender`
#: type alias verbatim — kept local to avoid an inter-module
#: dependency on lifecycle_state_machine (Story 4.3 is structurally
#: distinct from the BMAD-lifecycle-state-transition seam).
EventLogAppender = Callable[[dict[str, Any]], None]


# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class ProvisionedEnv(BaseModel):
    """The orchestrator-domain canonical record of a provisioned QA env.

    Persisted to ``run-state.yaml``'s NEW ``provisioned_env`` top-
    level field (AC-6 schema bump) by :func:`provision_env`'s
    successful path; cleared by :func:`teardown_env`'s successful
    path. The four-field shape mirrors AC-6's ``$defs/provisioned_env``
    schema definition byte-for-byte.

    Frozen for hashability + determinism per Epic 1 retro Action #2.
    Field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.

    Field semantics:
        * ``env_kind`` — one of ``web | api`` mirroring the
          orchestrator-event schema's existing ``env_kind`` enum at
          ``orchestrator-event.yaml`` lines 318 + 343 byte-for-byte.
        * ``port`` — the integer ephemeral TCP port the dev/API
          server is bound to. Matches the event schema's ``port``
          field at line 320; integer in ``[1, 65535]``.
        * ``pid`` — the integer process ID of the dev/API server
          spawned by the project-type-specific provisioner.
          Matches the event schema's ``pid`` field at line 322.
        * ``started_at`` — ISO-8601 timestamp marking when
          provisioning completed. Mirrors the orchestrator-event
          schema's ``timestamp`` field's ``format: date-time``
          discipline at line 110.
    """

    model_config = ConfigDict(frozen=True)

    env_kind: EnvKind
    port: int = Field(ge=1, le=65535)
    pid: int = Field(ge=1)
    started_at: datetime


class EnvSetupFailureDiagnostic(BaseModel):
    """The structured diagnostic context carried on the
    ``env-setup-failed`` marker emission AND surfaced through Story
    4.10's escalation routing.

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``story_id`` — the BMAD story identifier the env-provisioning
          attempt is scoped to.
        * ``project_type`` — the ``web | api`` project type read from
          ``_bmad/automation/qa-runbook.yaml`` by the LLM-runtime
          protocol; threaded into the diagnostic for downstream
          visibility (Story 4.10 may route differently per project
          type).
        * ``failure_step`` — the named step of the env-provisioning
          procedure that failed; one of the three
          :data:`EnvSetupFailureSubCause` values.
        * ``failure_diagnostic`` — free-form human-readable diagnostic
          string typically derived from the underlying exception
          (``str(exc)``); surfaces the actionable detail the
          practitioner needs to remediate.
        * ``qa_runbook_pointer`` — the on-disk path of the runbook
          stub the practitioner is expected to inspect (Story 7.5
          will scaffold this stub; Story 4.3 reads it AS DATA).
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    project_type: EnvKind
    failure_step: EnvSetupFailureSubCause
    failure_diagnostic: str
    qa_runbook_pointer: str = Field(min_length=1)


class MarkerEmissionRecord(BaseModel):
    """One marker-emission record local to the env-provisioning seam.

    Local to Story 4.3 — NOT a reuse of Story 3.3's
    :class:`loud_fail_harness.review_layer_failure.MarkerEmissionRecord`
    (which carries ``failed_layer``) nor of Story 4.2's
    :class:`loud_fail_harness.qa_plan_drift.PlanDriftEmissionRecord`
    (which carries ``diagnostic_context``) — the env-provisioning
    payload shape differs from both. Cross-story coupling avoidance —
    same posture Story 4.2 took vs reusing Story 3.3's
    :class:`MarkerEmissionRecord`.

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``marker_class`` — the canonical marker class identifier
          from ``schemas/marker-taxonomy.yaml``. One of
          ``"env-setup-failed"`` (verified by
          :data:`ENV_SETUP_FAILED_MARKER`) or
          ``"orphan-process-cleanup"`` (verified by
          :data:`ORPHAN_PROCESS_CLEANUP_MARKER`).
        * ``sub_cause`` — the marker's sub-classification. For
          ``env-setup-failed`` markers, one of the three
          :data:`EnvSetupFailureSubCause` values. For
          ``orphan-process-cleanup`` markers, ``None`` (the marker
          taxonomy at line 178 has empty
          ``sub_classifications: []``).
        * ``context`` — structured payload fields the bundle assembler
          and Story 4.10's escalation routing read. For
          ``env-setup-failed`` markers, the
          :func:`EnvSetupFailureDiagnostic.model_dump` projection.
          For ``orphan-process-cleanup`` markers, ``{"port": int,
          "pid": int}`` per the verbatim epic AC at epics.md line
          1878 ("an ``orphan-process-cleanup: {port}`` marker is
          emitted").
    """

    model_config = ConfigDict(frozen=True)

    marker_class: str
    sub_cause: str | None = None
    context: Mapping[str, Any] = Field(default_factory=dict)


class EnvSetupFailureEmission(BaseModel):
    """The two-channel atomic-emission return shape of
    :func:`surface_env_setup_failure`.

    Channels are paired by construction — both ``marker_record`` and
    ``diagnostic`` are present on a successful env-setup-failure
    emission; registry rejection raises :exc:`UnknownMarkerClass`
    BEFORE either is constructed (atomic-on-failure per Pattern 5;
    mirrors Story 4.2's :class:`PlanDriftEmission` shape verbatim).

    Frozen for determinism + hashability per Epic 1 retro Action #2.
    Field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.

    Field semantics:
        * ``marker_record`` — the :class:`MarkerEmissionRecord`
          carrying ``marker_class="env-setup-failed"`` + the
          ``sub_cause`` from :data:`EnvSetupFailureSubCause` + the
          diagnostic-projected ``context``. Bundle-assembler and
          escalation-routing consumers read this record to render
          the env-setup-failed marker comment + the per-failure
          diagnostic sub-section.
        * ``diagnostic`` — the :class:`EnvSetupFailureDiagnostic`
          carrying the five-field structured context. Co-exposed for
          ergonomic access without unwrapping ``marker_record``
          (same payload object as
          ``EnvSetupFailureDiagnostic(**marker_record.context)``).
    """

    model_config = ConfigDict(frozen=True)

    marker_record: MarkerEmissionRecord
    diagnostic: EnvSetupFailureDiagnostic


# --------------------------------------------------------------------------- #
# Protocols (project-type-specific provisioner / teardown / orphan-probe)     #
# --------------------------------------------------------------------------- #


@runtime_checkable
class Provisioner(Protocol):
    """Project-type-specific env provisioner.

    Story 4.4 (web Playwright provisioner) and Story 4.5 (API HTTP
    provisioner) implement this protocol against the actual
    ``subprocess.Popen``-of-dev-server + availability-check paths.
    THIS story ships only the protocol + a dummy :class:`NoOpProvisioner`
    reference impl for the test suite.

    Implementations MAY raise any exception on provisioning failure;
    :func:`provision_env` catches the exception, derives the
    ``failure_step`` from a ``failure_step`` attribute on the
    exception (if present) or defaults to ``"dev-server-not-ready"``,
    and re-raises as :exc:`EnvProvisioningFailed` carrying the
    structured emission.
    """

    def provision(
        self,
        story_id: str,
        project_type: EnvKind,
        port: int,
    ) -> ProvisionedEnv:
        """Spawn the dev/API server bound to ``port``; return the
        :class:`ProvisionedEnv` record.
        """


@runtime_checkable
class Teardown(Protocol):
    """Project-type-specific env teardown.

    Implementations terminate the spawned process via
    ``os.kill(pid, signal.SIGTERM)`` then a bounded-wait + ``SIGKILL``
    escalation per the dev's discretion. THIS story's teardown
    callable is project-type-agnostic at the protocol layer; web/API-
    specific teardown logic lands in Stories 4.4 / 4.5.
    """

    def teardown(self, provisioned_env: ProvisionedEnv) -> None:
        """Terminate the process referenced by
        ``provisioned_env.pid``.
        """


@runtime_checkable
class OrphanProbe(Protocol):
    """Project-type-agnostic orphan probe.

    Returns the list of port + PID pairs from prior crashed runs
    that should be cleaned up before fresh provisioning. The probe's
    detection mechanism is implementation-specific (Stories 4.4 / 4.5
    may walk ``/proc`` on Linux, query ``ps`` on macOS, query running
    processes via the OS API, etc.). THIS story's protocol surface
    is the (port, pid) tuple shape only.
    """

    def probe(self) -> tuple[tuple[int, int], ...]:
        """Return a tuple of ``(port, pid)`` pairs from prior crashed
        runs. Empty tuple = no orphans to clean up.
        """


@runtime_checkable
class OrphanTerminator(Protocol):
    """Project-type-agnostic orphan terminator.

    Called once per orphan returned by :class:`OrphanProbe.probe`;
    implementations terminate the orphan process via
    ``os.kill(pid, signal.SIGTERM)`` (or equivalent OS-portable
    termination primitive).
    """

    def terminate(self, port: int, pid: int) -> None:
        """Terminate the orphan process bound to ``port`` with
        process id ``pid``.
        """


class NoOpProvisioner:
    """Reference :class:`Provisioner` implementation for the test
    suite ONLY.

    Returns a deterministic dummy :class:`ProvisionedEnv` whose
    ``pid`` and ``started_at`` are fixed constants so the test
    suite's byte-equality assertions are stable across runs.

    NOT for production use — Story 4.4 (web) and Story 4.5 (API)
    ship the real project-type-specific provisioners.
    """

    #: Deterministic dummy PID for the test suite. High value chosen
    #: to avoid collision with real processes; if a test accidentally
    #: routes a teardown here, ``os.kill(99999, 0)`` fails loudly.
    _DUMMY_PID: int = 99999

    #: Deterministic dummy started_at for the test suite. Fixed UTC
    #: timestamp so two construct-and-dump round-trips are byte-equal.
    _DUMMY_STARTED_AT: datetime = datetime(
        2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc
    )

    def provision(
        self,
        story_id: str,
        project_type: EnvKind,
        port: int,
    ) -> ProvisionedEnv:
        """Return a dummy :class:`ProvisionedEnv` with the supplied
        ``project_type`` + ``port`` and the class-level deterministic
        ``pid`` + ``started_at``.
        """
        _ = story_id  # Sensor-not-advisor: signature-symmetric with the real provisioners.
        return ProvisionedEnv(
            env_kind=project_type,
            port=port,
            pid=self._DUMMY_PID,
            started_at=self._DUMMY_STARTED_AT,
        )


# --------------------------------------------------------------------------- #
# Exceptions                                                                  #
# --------------------------------------------------------------------------- #


class EnvProvisioningFailed(Exception):
    """Raised by :func:`provision_env` when the provisioner callable
    fails AND :func:`surface_env_setup_failure` has constructed the
    structured emission.

    Pattern 5 named-invariant diagnostic. Carries the
    :class:`EnvSetupFailureEmission` so the LLM-runtime protocol's
    catch site has the marker_record + diagnostic in hand for
    Story 4.10's escalation routing without unwrapping the exception
    further.

    Distinct from :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
    (Story 2.6's diagnostic for registry-rejection at marker emission
    time): :exc:`EnvProvisioningFailed` is a runtime env-provisioning
    failure (the provisioner could not bring up the dev/API server);
    :exc:`UnknownMarkerClass` is a programmer-error invariant (the
    registry doesn't carry the would-be marker class).

    Attributes:
        emission: The :class:`EnvSetupFailureEmission` carrying the
            marker_record + diagnostic. Surfaces both the marker
            class identifier (for the bundle assembler) AND the
            five-field diagnostic (for Story 4.10's escalation
            routing).
    """

    def __init__(self, emission: EnvSetupFailureEmission) -> None:
        self.emission: EnvSetupFailureEmission = emission
        super().__init__(
            f"env provisioning failed: marker_class="
            f"{emission.marker_record.marker_class!r}; "
            f"sub_cause={emission.marker_record.sub_cause!r}; "
            f"diagnostic={emission.diagnostic.failure_diagnostic!r}"
        )


# --------------------------------------------------------------------------- #
# Internal helpers                                                            #
# --------------------------------------------------------------------------- #


def _load_event_schema() -> dict[str, Any]:
    """Resolve and load the orchestrator-event schema at function-
    call time.

    Module-private; Epic 1 retro Action #1 — NEVER at module import
    time. Mirrors :func:`loud_fail_harness.specialist_dispatch._load_event_schema`
    verbatim.
    """
    return load_schema(find_repo_root() / "schemas" / "orchestrator-event.yaml")


def _default_event_id_factory(prefix: str) -> str:
    """Generate an opaque event identifier scoped to the env-
    provisioning seam.

    Format: ``ev-4-3-<prefix>-<token_hex>``. Mirrors Story 2.4's
    :func:`loud_fail_harness.lifecycle_state_machine._generate_event_id`
    convention; the ``token_hex(12)`` suffix gives 48 bits of
    collision resistance per event.
    """
    return f"ev-4-3-{prefix}-{secrets.token_hex(12)}"


def _atomic_write_run_state_dict(
    run_state_path: pathlib.Path,
    data: Mapping[str, Any],
) -> None:
    """Write ``data`` atomically to ``run_state_path`` via the
    canonical tempfile + ``os.fsync`` + ``os.replace`` pattern.

    Mirrors Story 2.2's
    :func:`loud_fail_harness.run_state.advance_run_state` write
    sequence byte-for-byte; THIS helper does NOT consume
    :class:`loud_fail_harness.run_state.RunState` because the AC-6
    schema bump's ``provisioned_env`` field is NOT yet on the
    Pydantic model (Story 4.3 is forbidden from modifying
    ``run_state.py`` per AC-10's scope discipline). The helper
    operates at the YAML-dict layer so the full document
    round-trips through ``yaml.safe_load`` + ``yaml.safe_dump``
    preserving every existing top-level field unchanged.

    NFR-R1 atomicity invariant: on crash mid-rename, either the
    prior version or the new version is on disk — never a
    partial-state file.
    """
    body = yaml.safe_dump(
        dict(data), sort_keys=False, default_flow_style=False
    )
    temp_path = run_state_path.with_name(
        f"{run_state_path.name}.tmp.{os.getpid()}.{secrets.token_hex(4)}"
    )
    try:
        fd = os.open(
            temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, run_state_path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _set_provisioned_env(
    run_state_path: pathlib.Path,
    provisioned: ProvisionedEnv,
) -> None:
    """Set the ``provisioned_env`` top-level field in run-state.yaml
    to the dump of ``provisioned``; preserve every other field
    unchanged.

    Atomic per :func:`_atomic_write_run_state_dict`. Reads the
    current YAML body, mutates the dict in memory, writes back via
    tempfile + ``os.replace``.
    """
    current_text = run_state_path.read_text(encoding="utf-8")
    current_dict: dict[str, Any] = yaml.safe_load(current_text) or {}
    # Round-trip through JSON to canonicalize datetime and other
    # Pydantic-internal types into JSON-Schema-compatible primitives
    # (parallel to run_state.py's _serialize_run_state pipeline).
    provisioned_payload: dict[str, Any] = json.loads(
        provisioned.model_dump_json()
    )
    current_dict[_PROVISIONED_ENV_FIELD] = provisioned_payload
    _atomic_write_run_state_dict(run_state_path, current_dict)


def _clear_provisioned_env(run_state_path: pathlib.Path) -> None:
    """Remove the ``provisioned_env`` top-level field from
    run-state.yaml; preserve every other field unchanged.

    Atomic per :func:`_atomic_write_run_state_dict`. The
    ``dev's-call`` choice (per AC-6 of Story 4.3) is REMOVAL of the
    key (rather than setting to ``null``) — recorded in
    ``docs/extension-audit.md`` per the no-introductions principle.
    The bumped schema's optional shape accepts both forms (absent OR
    null); removal produces cleaner YAML on inspection by the
    practitioner per NFR-O2.
    """
    current_text = run_state_path.read_text(encoding="utf-8")
    current_dict: dict[str, Any] = yaml.safe_load(current_text) or {}
    current_dict.pop(_PROVISIONED_ENV_FIELD, None)
    _atomic_write_run_state_dict(run_state_path, current_dict)


# --------------------------------------------------------------------------- #
# Public API — env-lifecycle primitives                                       #
# --------------------------------------------------------------------------- #


def allocate_ephemeral_port() -> int:
    """Return an OS-allocated ephemeral TCP port via the canonical
    ``socket.bind(("localhost", 0))`` + ``getsockname()`` + ``close``
    pattern.

    Behavior (AC-2):
        1. Open a TCP socket via :class:`socket.socket`.
        2. Bind to ``("localhost", 0)`` — the OS picks a free port
           from its ephemeral range (the range varies by OS — Linux
           defaults to ``32768-60999``; macOS to ``49152-65535``;
           Windows to ``49152-65535``; the kernel-managed allocation
           is what makes the function OS-portable).
        3. Read the port from ``socket.getsockname()[1]``.
        4. Close the socket; the port is released back to the OS but
           reserved-by-convention for the immediately-following
           provisioning call.

    The function does NOT cache or pool ports across calls — each
    invocation is independent. The function does NOT promise the
    port stays free — the race-condition window between port-release
    and provisioner-bind is inherent to ephemeral allocation; the
    provisioner is expected to handle "port suddenly bound" by
    raising an exception that flows through
    :func:`surface_env_setup_failure` with
    ``sub_cause="port-bind-failed"``. THIS function's responsibility
    ends at returning a recently-free port.

    The function does NOT block, sleep, or retry — a single bind +
    getsockname + close sequence per invocation.

    Returns:
        Integer TCP port number in the range ``[1, 65535]``. The OS
        empirically returns a port above the privileged-port range
        (``> 1023``) because its ephemeral-range allocation never
        descends into the reserved-for-services region; THIS
        function trusts the OS and does NOT enforce the bound (the
        test suite verifies it empirically per AC-9 test #1).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    finally:
        sock.close()
    return int(port)


def surface_env_setup_failure(
    story_id: str,
    project_type: EnvKind,
    failure_step: EnvSetupFailureSubCause,
    failure_diagnostic: str,
    qa_runbook_pointer: str,
    registry: MarkerClassRegistry,
) -> EnvSetupFailureEmission:
    """Surface env-setup failure across both channels atomically.

    THIS function is the SINGLE source-of-truth emission path for
    the two-channel projection of an env-provisioning failure
    (FR7 + NFR-S6). Composes Story 2.6's
    :func:`validate_marker_emission`. Pure: no file I/O, no
    run-state writes, no event emissions (the marker record is
    data the caller consumes; it is NOT emitted to the
    orchestrator-event log by THIS function).

    Behavior (parallel to Story 4.2's
    :func:`loud_fail_harness.qa_plan_drift.surface_plan_drift`
    verbatim):
        * **Step 1 — Validate marker emission FIRST**. Calls
          :func:`validate_marker_emission(registry, ENV_SETUP_FAILED_MARKER)`.
          On registry rejection
          :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
          propagates per Pattern 5; NO partial state is constructed
          (atomic-on-failure; mirrors Story 4.2 AC-1 +
          Story 3.3 AC-7).
        * **Step 2 — Construct the diagnostic context** carrying
          the five required fields.
        * **Step 3 — Construct the marker emission record** with
          ``marker_class="env-setup-failed"``, the supplied
          ``failure_step`` as ``sub_cause``, and the
          diagnostic-projected ``context``.
        * **Step 4 — Return the** :class:`EnvSetupFailureEmission`
          carrying both projections.

    Args:
        story_id: BMAD story identifier (mirrors Story 4.2's
            :func:`surface_plan_drift` parameter; threaded into the
            diagnostic context).
        project_type: ``web`` or ``api`` per the runbook stub Story
            7.5 will scaffold; threaded into the diagnostic context.
        failure_step: One of the three :data:`EnvSetupFailureSubCause`
            values; named verbatim per the marker-taxonomy enum at
            ``schemas/marker-taxonomy.yaml`` lines 110-113.
        failure_diagnostic: Free-form human-readable diagnostic
            string typically derived from the underlying exception
            (``str(exc)``).
        qa_runbook_pointer: On-disk path of the runbook stub the
            practitioner should inspect; threaded into the
            diagnostic for downstream visibility.
        registry: The runtime :class:`MarkerClassRegistry` from
            :func:`loud_fail_harness.specialist_dispatch.load_marker_class_registry`;
            must contain the ``env-setup-failed`` marker class.

    Returns:
        :class:`EnvSetupFailureEmission` carrying ``marker_record``
        + ``diagnostic``.

    Raises:
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
        registry does not contain ``"env-setup-failed"``.
    """
    validate_marker_emission(registry, ENV_SETUP_FAILED_MARKER)
    diagnostic = EnvSetupFailureDiagnostic(
        story_id=story_id,
        project_type=project_type,
        failure_step=failure_step,
        failure_diagnostic=failure_diagnostic,
        qa_runbook_pointer=qa_runbook_pointer,
    )
    marker_record = MarkerEmissionRecord(
        marker_class=ENV_SETUP_FAILED_MARKER,
        sub_cause=failure_step,
        context=diagnostic.model_dump(mode="json"),
    )
    return EnvSetupFailureEmission(
        marker_record=marker_record,
        diagnostic=diagnostic,
    )


def make_env_provisioned_event(
    story_id: str,
    env_kind: EnvKind,
    port: int,
    pid: int,
    *,
    timestamp: datetime,
    env_diagnostic: str = "",
    event_id_factory: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Construct a schema-valid ``env-provisioned`` event payload.

    Composes :func:`loud_fail_harness.event_validator.validate_event`
    exclusively for the defensive validation pass before return.
    Raises :class:`ValueError` if the constructed event does not
    validate against the live schema (firing means THIS module has
    a bug, not the caller).

    Args:
        story_id: BMAD story identifier; bound to the event's
            ``story_id`` field per the orchestrator-event schema's
            top-level required fields.
        env_kind: ``web`` or ``api`` per the schema's ``env_kind``
            enum at orchestrator-event.yaml line 318.
        port: The integer ephemeral TCP port the dev/API server is
            bound to.
        pid: The integer process ID of the spawned server.
        timestamp: Timezone-aware UTC datetime at which provisioning
            completed; rendered via :func:`datetime.isoformat`.
        env_diagnostic: Optional free-form diagnostic string; defaults
            to the empty string per the schema's optional-string
            shape at line 323-324.
        event_id_factory: Optional caller-injected event-id factory.
            If ``None``, defaults to :func:`_default_event_id_factory`
            with the ``"env-prov"`` prefix (sensor-not-advisor —
            production callers MAY substitute a deterministic
            factory for replay-correlation work).

    Returns:
        Schema-valid dict conforming to
        ``schemas/orchestrator-event.yaml``'s ``env-provisioned``
        ``oneOf`` branch (lines 302-325).

    Raises:
        ValueError: The constructed event does not validate against
            the live orchestrator-event schema. Programmer-error
            invariant; firing means THIS module has a bug.
    """
    factory = event_id_factory or (
        lambda: _default_event_id_factory("env-prov")
    )
    event_dict: dict[str, Any] = {
        "event_class": _ENV_PROVISIONED_EVENT_CLASS,
        "event_id": factory(),
        "timestamp": timestamp.isoformat(),
        "story_id": story_id,
        "env_kind": env_kind,
        "port": port,
        "pid": pid,
        "env_diagnostic": env_diagnostic,
    }
    schema = _load_event_schema()
    errors = validate_event(event_dict, schema)
    if errors:
        raise ValueError(
            f"env-provisioned event failed schema validation: "
            f"{[str(err.message) for err in errors]}"
        )
    return event_dict


def make_env_torn_down_event(
    story_id: str,
    env_kind: EnvKind,
    outcome: EnvTeardownOutcome,
    *,
    timestamp: datetime,
    event_id_factory: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Construct a schema-valid ``env-torn-down`` event payload.

    Composes :func:`loud_fail_harness.event_validator.validate_event`
    exclusively for the defensive validation pass before return.

    Args:
        story_id: BMAD story identifier.
        env_kind: ``web`` or ``api`` per the schema's ``env_kind``
            enum at orchestrator-event.yaml line 343.
        outcome: ``clean`` or ``orphan-process-cleanup`` per the
            schema's ``outcome`` enum at line 346.
        timestamp: Timezone-aware UTC datetime at which teardown
            completed.
        event_id_factory: Optional caller-injected event-id factory;
            defaults to :func:`_default_event_id_factory` with
            ``"env-tear"`` prefix.

    Returns:
        Schema-valid dict conforming to
        ``schemas/orchestrator-event.yaml``'s ``env-torn-down``
        ``oneOf`` branch (lines 326-346).

    Raises:
        ValueError: The constructed event does not validate against
            the live schema (programmer-error invariant).
    """
    factory = event_id_factory or (
        lambda: _default_event_id_factory("env-tear")
    )
    event_dict: dict[str, Any] = {
        "event_class": _ENV_TORN_DOWN_EVENT_CLASS,
        "event_id": factory(),
        "timestamp": timestamp.isoformat(),
        "story_id": story_id,
        "env_kind": env_kind,
        "outcome": outcome,
    }
    schema = _load_event_schema()
    errors = validate_event(event_dict, schema)
    if errors:
        raise ValueError(
            f"env-torn-down event failed schema validation: "
            f"{[str(err.message) for err in errors]}"
        )
    return event_dict


def provision_env(
    story_id: str,
    project_type: EnvKind,
    provisioner: Provisioner,
    port: int,
    run_state_path: pathlib.Path,
    registry: MarkerClassRegistry,
    event_appender: EventLogAppender,
    *,
    qa_runbook_pointer: str = "_bmad/automation/qa-runbook.yaml",
    timestamp_factory: Callable[[], datetime] = lambda: datetime.now(
        timezone.utc
    ),
) -> ProvisionedEnv:
    """Compose the orchestrator-owned env-provisioning seam (AC-3).

    Behavior (load-bearing per AC-3 + epics.md lines 1862-1865):

        1. Call ``provisioner.provision(story_id, project_type, port)``
           — on success this returns a :class:`ProvisionedEnv`
           instance.
        2. On any exception from the provisioner, derive
           ``failure_step`` from a ``failure_step`` attribute on
           the exception (if present) or default to
           ``"dev-server-not-ready"``; call
           :func:`surface_env_setup_failure` with the structured
           inputs; raise :exc:`EnvProvisioningFailed` carrying the
           emission. Atomic-on-failure — no run-state mutation, no
           event appended.
        3. On successful provision, atomically write the
           ``provisioned_env`` field into ``run-state.yaml`` via
           :func:`_set_provisioned_env` (mirrors Story 2.2's
           tempfile + ``os.replace`` discipline byte-for-byte).
        4. Construct the ``env-provisioned`` orchestrator event via
           :func:`make_env_provisioned_event`, validate it against
           ``schemas/orchestrator-event.yaml``, and append it via
           ``event_appender``.

    The function is atomic-on-failure: on any step's exception
    (provisioner failure, run-state write failure, event-emit
    failure), no ``provisioned_env`` field is left mid-write AND no
    partial event is appended; the caller observes either complete
    success (run-state populated + event appended) or a single
    :exc:`EnvProvisioningFailed` exception (with no other side
    effects).

    Write-ordering invariant (per AC-3): the run-state write happens
    BEFORE the event emit (state must be persisted before the event
    references it — mirrors Story 2.2 / 2.4's existing ordering).

    Args:
        story_id: BMAD story identifier; bound to both the
            run-state's existing ``story_id`` field AND the
            event's ``story_id`` field.
        project_type: ``web`` or ``api`` from the runbook stub.
        provisioner: The :class:`Provisioner` implementation; THIS
            story's tests use :class:`NoOpProvisioner`; production
            callers (Story 4.4 / 4.5) supply real implementations.
        port: The integer ephemeral port allocated by
            :func:`allocate_ephemeral_port`.
        run_state_path: Caller-controlled on-disk path of the
            run-state file.
        registry: The runtime :class:`MarkerClassRegistry`; must
            contain the ``env-setup-failed`` marker class for the
            failure path's :func:`surface_env_setup_failure` call.
        event_appender: Caller-injected event-log appender callable
            (typically :func:`loud_fail_harness.event_streaming.make_event_log_appender`'s
            return value).
        qa_runbook_pointer: Path of the runbook stub for the
            diagnostic; defaults to the View 3 user-runtime path
            ``_bmad/automation/qa-runbook.yaml``.
        timestamp_factory: Callable returning the timestamp for the
            event's ``timestamp`` field; defaults to
            ``datetime.now(timezone.utc)``. Tests inject deterministic
            stubs.

    Returns:
        The :class:`ProvisionedEnv` instance the provisioner
        returned (for caller convenience — the field is also
        persisted in run-state).

    Raises:
        :exc:`EnvProvisioningFailed`: The provisioner raised any
            exception; the structured emission carries the
            marker_record + diagnostic.
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
            The registry does not contain ``"env-setup-failed"``;
            raised BEFORE any provisioner call or side effect.
    """
    # Atomic-on-failure: validate registry BEFORE any side effect so
    # an unknown marker class never leaves partial state.
    validate_marker_emission(registry, ENV_SETUP_FAILED_MARKER)

    try:
        provisioned = provisioner.provision(story_id, project_type, port)
    except Exception as exc:
        raw_failure_step = getattr(exc, "failure_step", "dev-server-not-ready")
        failure_step: EnvSetupFailureSubCause
        if raw_failure_step in (
            "port-bind-failed",
            "playwright-launch-failed",
            "dev-server-not-ready",
        ):
            failure_step = cast(EnvSetupFailureSubCause, raw_failure_step)
        else:
            failure_step = "dev-server-not-ready"
        emission = surface_env_setup_failure(
            story_id=story_id,
            project_type=project_type,
            failure_step=failure_step,
            failure_diagnostic=str(exc),
            qa_runbook_pointer=qa_runbook_pointer,
            registry=registry,
        )
        raise EnvProvisioningFailed(emission) from exc

    # State first (write-ordering invariant per AC-3) ...
    _set_provisioned_env(run_state_path, provisioned)
    # ... then the event reference. On failure, roll back the
    # run-state write so the caller sees no partial state.
    try:
        event_appender(
            make_env_provisioned_event(
                story_id=story_id,
                env_kind=provisioned.env_kind,
                port=provisioned.port,
                pid=provisioned.pid,
                timestamp=timestamp_factory(),
            )
        )
    except Exception:
        _clear_provisioned_env(run_state_path)
        raise
    return provisioned


def teardown_env(
    provisioned_env: ProvisionedEnv,
    teardown_fn: Teardown,
    run_state_path: pathlib.Path,
    evidence_root: pathlib.Path,
    registry: MarkerClassRegistry,
    event_appender: EventLogAppender,
    *,
    story_id: str,
    timestamp_factory: Callable[[], datetime] = lambda: datetime.now(
        timezone.utc
    ),
) -> None:
    """Compose the orchestrator-owned env-teardown seam (AC-4).

    Behavior (load-bearing per AC-4 + epics.md lines 1869-1873):

        1. Call ``teardown_fn.teardown(provisioned_env)`` — terminates
           the spawned process via the project-type-specific termination
           primitive (web/API-specific logic is Stories 4.4 / 4.5).
        2. Clear the ``provisioned_env`` field from run-state via
           :func:`_clear_provisioned_env` — even if the teardown
           callable raised (teardown is idempotent from the
           orchestrator's perspective).
        3. Emit one ``env-torn-down`` orchestrator event with
           ``outcome="clean"`` via :func:`make_env_torn_down_event`.

    The ``evidence_root`` directory is NEVER opened, listed, mutated,
    or referenced by THIS function — the verbatim epic AC at
    epics.md line 1872 ("evidence already captured by QA is preserved
    (teardown does not destroy evidence — Story 4.12 owns
    persistence)") is structurally enforced via the function's
    complete absence of any evidence-root file-system interaction.
    The ``evidence_root`` parameter exists ONLY for the test suite to
    assert non-touching via a sentinel file (per AC-9 test #6).

    Args:
        provisioned_env: The :class:`ProvisionedEnv` instance to
            tear down.
        teardown_fn: The :class:`Teardown` implementation.
        run_state_path: Caller-controlled on-disk path of the
            run-state file.
        evidence_root: Caller-controlled on-disk path of the QA
            evidence root (per FR49). NEVER touched by THIS function.
        registry: The runtime :class:`MarkerClassRegistry`. Reserved
            for symmetry with :func:`provision_env` and
            :func:`cleanup_orphan_processes`; not used by the
            ``clean``-teardown path because no marker is emitted on
            clean teardown (the markers attach to the
            ``orphan-process-cleanup`` outcome only).
        event_appender: Caller-injected event-log appender callable.
        story_id: BMAD story identifier; bound to the event's
            ``story_id`` field.
        timestamp_factory: Callable returning the timestamp for the
            event's ``timestamp`` field.

    Raises:
        Whatever exception ``teardown_fn.teardown`` raised
        (propagated unchanged after the run-state field is cleared
        and the ``env-torn-down`` event with ``outcome="clean"`` is
        emitted — teardown is idempotent from the orchestrator's
        perspective per AC-4's epics.md line 1873 invariant).
    """
    _ = registry  # Reserved for symmetry; clean-teardown emits no marker.
    _ = evidence_root  # Structurally untouched per epics.md line 1872.

    teardown_exc: BaseException | None = None
    try:
        teardown_fn.teardown(provisioned_env)
    except BaseException as exc:
        teardown_exc = exc

    try:
        _clear_provisioned_env(run_state_path)
        event_appender(
            make_env_torn_down_event(
                story_id=story_id,
                env_kind=provisioned_env.env_kind,
                outcome="clean",
                timestamp=timestamp_factory(),
            )
        )
    finally:
        if teardown_exc is not None:
            raise teardown_exc


def cleanup_orphan_processes(
    run_state_path: pathlib.Path,
    orphan_probe: OrphanProbe,
    orphan_terminator: OrphanTerminator,
    registry: MarkerClassRegistry,
    event_appender: EventLogAppender,
    *,
    story_id: str,
    env_kind: EnvKind,
    timestamp_factory: Callable[[], datetime] = lambda: datetime.now(
        timezone.utc
    ),
) -> tuple[MarkerEmissionRecord, ...]:
    """Compose the orchestrator-owned orphan-cleanup seam (AC-5).

    Behavior (load-bearing per AC-5 + epics.md lines 1874-1878):

        1. Call ``orphan_probe.probe()`` — returns a tuple of
           ``(port, pid)`` pairs from prior crashed runs. If empty,
           the function returns an empty tuple AND emits no events.
        2. **Atomic-on-failure registry validation** — call
           :func:`validate_marker_emission(registry,
           ORPHAN_PROCESS_CLEANUP_MARKER)` ONCE BEFORE any side
           effect; on rejection
           :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
           propagates per Pattern 5; NO terminator calls happen, NO
           markers are constructed, NO events are emitted.
        3. For each ``(port, pid)`` pair, call
           ``orphan_terminator.terminate(port, pid)``.
        4. Construct one :class:`MarkerEmissionRecord` per
           cleaned-up orphan with
           ``marker_class="orphan-process-cleanup"``,
           ``sub_cause=None`` (the marker taxonomy at line 178 has
           empty ``sub_classifications: []``), and
           ``context={"port": port, "pid": pid}`` per the verbatim
           epic AC at epics.md line 1878.
        5. Emit a SINGLE ``env-torn-down`` event with
           ``outcome="orphan-process-cleanup"`` summarizing the
           sweep — NOT one event per orphan; the sweep is a single
           seam event per the orchestrator-event schema's atomic-
           event discipline.
        6. Clear any stale ``provisioned_env`` field from run-state
           that the orphan probe surfaces evidence of (defensive
           cleanup — orphans by definition mean a prior run crashed
           leaving stale state).

    Args:
        run_state_path: Caller-controlled on-disk path of the
            run-state file.
        orphan_probe: The :class:`OrphanProbe` implementation.
        orphan_terminator: The :class:`OrphanTerminator` implementation.
        registry: The runtime :class:`MarkerClassRegistry`; must
            contain the ``orphan-process-cleanup`` marker class.
        event_appender: Caller-injected event-log appender callable.
        story_id: BMAD story identifier.
        env_kind: ``web`` or ``api``; bound to the
            ``env-torn-down`` summary event's ``env_kind`` field.
            The dev's-call here (per AC-5) is a single per-sweep
            ``env_kind``; the orchestrator-event schema's per-class
            shape requires ``env_kind`` so a single value is
            mandatory at this seam. Recorded in extension-audit.md.
        timestamp_factory: Callable returning the timestamp.

    Returns:
        Tuple of :class:`MarkerEmissionRecord` instances — one per
        cleaned-up orphan in the probe's order. Empty tuple when
        the probe returns no orphans.

    Raises:
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
            The registry does not contain
            ``"orphan-process-cleanup"``; raised BEFORE any side
            effect.
    """
    orphans = orphan_probe.probe()
    if not orphans:
        return ()

    # Atomic-on-failure: registry validation BEFORE any side effect.
    validate_marker_emission(registry, ORPHAN_PROCESS_CLEANUP_MARKER)

    emissions: list[MarkerEmissionRecord] = []
    try:
        for port, pid in orphans:
            orphan_terminator.terminate(port, pid)
            emissions.append(
                MarkerEmissionRecord(
                    marker_class=ORPHAN_PROCESS_CLEANUP_MARKER,
                    sub_cause=None,
                    context={"port": port, "pid": pid},
                )
            )
    finally:
        if emissions:
            # Defensive run-state cleanup — orphans by definition mean a
            # prior run crashed leaving the field stale; THIS sweep clears
            # it. The clear is a no-op if the field is already absent.
            _clear_provisioned_env(run_state_path)

            # Single sweep-summary event (NOT one per orphan).
            event_appender(
                make_env_torn_down_event(
                    story_id=story_id,
                    env_kind=env_kind,
                    outcome="orphan-process-cleanup",
                    timestamp=timestamp_factory(),
                )
            )

    return tuple(emissions)


__all__ = [
    "ENV_SETUP_FAILED_MARKER",
    "ORPHAN_PROCESS_CLEANUP_MARKER",
    "EnvKind",
    "EnvSetupFailureSubCause",
    "EnvTeardownOutcome",
    "ProvisionedEnv",
    "EnvSetupFailureDiagnostic",
    "MarkerEmissionRecord",
    "EnvSetupFailureEmission",
    "Provisioner",
    "Teardown",
    "OrphanProbe",
    "OrphanTerminator",
    "NoOpProvisioner",
    "EnvProvisioningFailed",
    "allocate_ephemeral_port",
    "surface_env_setup_failure",
    "make_env_provisioned_event",
    "make_env_torn_down_event",
    "provision_env",
    "teardown_env",
    "cleanup_orphan_processes",
]
