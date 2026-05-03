"""Project-type-specific (web) Playwright MCP driver primitives (Story 4.4).

FR17 + ADR-002 graceful-degrade + Pattern 5. Pure-library substrate
consumed by the orchestrator skill at the ``review → qa`` seam (via
Story 4.3's :func:`loud_fail_harness.env_provisioning.provision_env`)
AND by the QA wrapper at AC-iteration time (via Story 4.13's
forthcoming wrapper thickening). Composes Story 2.6's marker-class
registry, Story 4.1's :class:`QABehavioralPlanEntry` model, and
Story 4.3's :class:`Provisioner` / :class:`Teardown` Protocols
verbatim.

Architectural placement (parallel to Story 4.2's
:mod:`loud_fail_harness.qa_plan_drift` and Story 4.3's
:mod:`loud_fail_harness.env_provisioning`): this module is a
**substrate library NOT a sixth substrate component**. ADR-003
Consequence 1 enumerates exactly five substrate components
(architecture.md lines 311-315); THIS module is a substrate
**library** consumed by the orchestrator skill at provision-time
(Story 4.3's :class:`Provisioner` Protocol implementation) AND by
the QA wrapper at AC-iteration time (Story 4.6's plan-driven AC
iteration consumes :func:`verify_ac` per the verbatim epic AC at
``_bmad-output/planning-artifacts/epics.md`` lines 1893-1925). It is
structurally a pure-library sibling of Story 4.1's
:mod:`loud_fail_harness.qa_behavioral_plan`, Story 4.2's
:mod:`loud_fail_harness.qa_plan_drift`, and Story 4.3's
:mod:`loud_fail_harness.env_provisioning`. The substrate-component
count stays at FIVE; the harness module count grows by one.

Procedural checklist (verbatim epic AC at epics.md lines 1893-1925):

    1. The orchestrator-owned env-provisioning seam (Story 4.3's
       :func:`loud_fail_harness.env_provisioning.provision_env`)
       is invoked with a :class:`PlaywrightProvisioner` instance.
    2. :class:`PlaywrightProvisioner.provision` first probes
       Playwright MCP availability via the injected
       :class:`PlaywrightAvailabilityProbe`; on
       ``is_available() is False`` raises
       :exc:`PlaywrightLaunchFailed` with attribute
       ``failure_step="playwright-launch-failed"`` so Story 4.3's
       ``provision_env`` catches it via
       ``getattr(exc, "failure_step", "dev-server-not-ready")``
       and routes through
       :func:`loud_fail_harness.env_provisioning.surface_env_setup_failure`
       with ``sub_cause="playwright-launch-failed"`` per the
       ``schemas/marker-taxonomy.yaml`` line 111 enum value.
    3. On availability ``True``, the injected :class:`DevServerRunner`
       is called to spawn the dev server bound to the allocated
       ephemeral port; the runner returns the spawned PID; a
       :class:`ProvisionedEnv` with ``env_kind="web"`` is returned.
    4. The orchestrator dispatches QA via Story 2.6's existing path;
       the QA wrapper (Story 4.13 forthcoming completion) composes
       :func:`verify_ac` against the running web product.
    5. Each :func:`verify_ac` invocation dispatches the appropriate
       :class:`WebDriver` action per the
       :class:`QABehavioralPlanEntry.assertion_shape`, captures
       evidence per ``expected_evidence_tier`` via the injected
       :class:`EvidenceCapturer`, and returns an :class:`AcResult`
       whose ``model_dump()`` projection mirrors
       ``schemas/envelope.schema.yaml`` ``$defs/ac_result`` lines
       164-194 byte-for-byte.
    6. Mid-run Playwright unavailability: any
       ``mcp__playwright__browser_*`` tool-call exception during AC
       verification flows through
       :func:`surface_playwright_mcp_unavailable` which produces a
       structured :class:`PlaywrightMcpUnavailableEmission` carrying
       a :class:`MarkerEmissionRecord` with
       ``marker_class="playwright-mcp-unavailable"`` (consumed
       AS-IS from ``schemas/marker-taxonomy.yaml`` line 226) AND a
       :class:`PlaywrightMcpUnavailableDiagnostic` carrying
       ``(story_id, action_kind, prior_evidence_refs)`` so already-
       captured evidence is preserved per the verbatim epic AC at
       epics.md line 1912. Story 4.10's escalation routing consumes
       the structured emission; THIS module produces it.
    7. Masked-selector redaction per epics.md line 1917: the
       :class:`EvidenceCapturer`'s ``capture(action_kind, payload)``
       implementation applies the :class:`MaskedSelectorPolicy` to
       its inputs BEFORE persisting, replacing matched substrings
       with :data:`MASKED_REDACTION_SENTINEL` (``"[REDACTED]"``).
    8. After QA return, the orchestrator calls
       :class:`PlaywrightTeardown.teardown` (a :class:`Teardown`
       Protocol implementation) to terminate the dev-server process
       via ``SIGTERM`` → bounded-wait → ``SIGKILL`` escalation.

Marker-class linkage:
    The ``playwright-mcp-unavailable`` marker class exists in
    ``schemas/marker-taxonomy.yaml`` line 226 with empty
    ``sub_classifications: []`` (Story 1.4's proactive add per the
    epic-close marker sweep recorded in ``docs/extension-audit.md``).
    The ``playwright-launch-failed`` sub-classification of
    ``env-setup-failed`` exists at line 111 (Story 1.4 enumeration).
    Both are consumed AS-IS — Story 4.4 does NOT bump
    :file:`marker-taxonomy.yaml`.

Orchestrator-event linkage:
    ZERO new event classes. Driver actions are wrapper-side concerns;
    the orchestrator-event log records seam transitions
    (``env-provisioned``, ``env-torn-down``, ``specialist-dispatched``,
    ``specialist-returned``, ``state-transition-halted``) — NOT per-
    action driver events. Mid-run Playwright unavailability surfaces
    via marker emission only; no new event class is needed.

Upstream-consumer linkage:
    ``skills/bmad-automation/steps/qa-driver-playwright.md`` (NEW in
    THIS story) is the LLM-runtime protocol naming the
    :class:`WebDriver` Protocol ↔ ``mcp__playwright__browser_*`` tool
    mappings the QA wrapper composes against at AC-iteration time
    for ``web`` project types. The substrate library is pure Python
    and CANNOT itself invoke MCP tools — that is structurally an
    LLM-runtime concern bound to the QA wrapper's prompt-execution
    context per ADR-004's substrate-vs-LLM-runtime split.

Downstream-consumer linkage:
    * Story 4.5 (API HTTP driver) is a sibling pure-library module
      (``http_driver.py``) implementing the same :class:`Provisioner`
      Protocol against the HTTP surface — NOT an extension of THIS
      module.
    * Story 4.6 (plan-driven AC iteration framework) consumes
      :func:`verify_ac` at iteration time across the full
      :class:`QABehavioralPlan.entries` tuple.
    * Story 4.7 (AC-assertion-evidence triple structural enforcement)
      lifts the existing schema-level invariant; THIS module
      produces records that conform to the existing schema.
    * Story 4.8 (three-tier evidence hierarchy) thickens the
      ``expected_evidence_tier`` semantics; THIS story emits Tier-1
      mechanical evidence only.
    * Story 4.10 (env-setup-fail / verification-fail escalation
      routing) consumes the :class:`PlaywrightMcpUnavailableEmission`
      and routes it through the verification-fail / env-setup-fail
      escalation-class contracts. THIS module produces the
      structured emission; that module routes it.
    * Story 4.12 (evidence-persistence size budgets + truncation)
      reads the :class:`EvidenceCapturer`'s on-disk output to
      enforce truncation; the
      :func:`verify_ac`-NEVER-emits-markers invariant is what makes
      Story 4.12's composition possible without ordering risk.
    * Story 4.13 (QA wrapper completion) thickens
      ``agents/qa.md`` to compose THIS module's primitives at AC-
      iteration time for ``web`` project types.

Structural-not-era-based emission rule:
    The ``playwright-mcp-unavailable`` marker emits iff
    :func:`surface_playwright_mcp_unavailable` is invoked by the QA
    wrapper on a mid-run MCP failure. Story 4.10's escalation
    routing thickens visibility further per the verbatim epic AC at
    epics.md line 1912 without modifying THIS module's emission
    code — same posture Story 3.4 codified for
    ``walking-skeleton-bundle`` at architecture.md line 1581.

QA-independence-from-TEA-artifacts invariant (FR16, PRD line 830):
    Driver code reads ONLY the AC + plan-entry from its
    :func:`verify_ac` arguments + the ``qa-runbook.yaml``'s
    ``dev_server_command`` / ``masked_selectors`` fields (consumed
    by the LLM-runtime protocol at the step file, NOT by this
    library) + the running web product. Driver code does NOT read
    TEA test files, dev tests, review findings, or commit diffs.
    The invariant is structurally encoded by every public function's
    argument list: no TEA-artifact channel exists.

FR62 pluggability invariant:
    The driver substrate references ONLY
    :mod:`loud_fail_harness.specialist_dispatch` (registry + marker
    validation) + :mod:`loud_fail_harness.env_provisioning`
    (:class:`Provisioner` Protocol + :class:`ProvisionedEnv` shape +
    :class:`Teardown` Protocol +
    :class:`MarkerEmissionRecord`) +
    :mod:`loud_fail_harness.qa_behavioral_plan`
    (:class:`QABehavioralPlanEntry` model) + Pydantic v2 + Python
    stdlib. NO references to Dev or Review-BMAD specialist code.

Cross-component reuse posture (Story 1.10b precedent):
    * Pydantic v2 :class:`pydantic.BaseModel` +
      :class:`pydantic.ConfigDict` — REUSED (already pinned by
      stories 1.1 / 1.2 / 1.10b / 4.1 / 4.2 / 4.3).
    * Story 2.6's :mod:`loud_fail_harness.specialist_dispatch` —
      REUSED for :class:`MarkerClassRegistry` +
      :func:`validate_marker_emission` + :exc:`UnknownMarkerClass`.
    * Story 4.3's :mod:`loud_fail_harness.env_provisioning` —
      REUSED for :class:`Provisioner` Protocol +
      :class:`ProvisionedEnv` + :class:`Teardown` Protocol +
      :class:`MarkerEmissionRecord` + :data:`EnvKind`.
    * Story 4.1's :mod:`loud_fail_harness.qa_behavioral_plan` —
      REUSED for :class:`QABehavioralPlanEntry` model.
    * Python stdlib ``os`` + ``signal`` + ``time`` (used only by
      :class:`PlaywrightTeardown`'s SIGTERM → wait → SIGKILL
      escalation; never inside :class:`PlaywrightProvisioner` or
      :func:`verify_ac`).
    * No new runtime dependencies. No file I/O on configs. No
      ``mcp__playwright__browser_*`` tool invocation (that is
      structurally an LLM-runtime concern bound to the QA wrapper's
      prompt-execution context per ADR-004 — the step file at
      ``skills/bmad-automation/steps/qa-driver-playwright.md`` is
      the binding point).

Sensor-not-advisor (PRD-level invariant + Pattern 5):
    The library COMPOSES the driver primitives + RETURNS the
    structured emissions; it does NOT decide flow policy
    (Story 4.10's escalation contract is the consumer; THIS module
    produces the structured emission, that module routes it). It
    does NOT log, does NOT print, does NOT advance the run-state's
    ``current_state`` field — the BMAD-lifecycle ``current_state``
    is owned by Story 2.4's :mod:`lifecycle_state_machine`'s
    :func:`commit_transition` exclusively.

Atomic-on-failure invariant (Pattern 5; mirrors Stories 3.3 / 4.2 /
4.3): every public function in this module is atomic-on-failure.
:func:`surface_playwright_mcp_unavailable` validates the registry
FIRST — on rejection the :exc:`UnknownMarkerClass` propagates with
NO marker construction, NO diagnostic construction, NO partial
state. :class:`PlaywrightProvisioner.provision` probes availability
FIRST — on probe-false the :exc:`PlaywrightLaunchFailed` propagates
with NO call to the dev-server runner.

Determinism: :class:`WebDriverAssertion`, :class:`NetworkRequest`,
:class:`MaskedSelectorPolicy`, :class:`AcResult`,
:class:`PlaywrightMcpUnavailableDiagnostic`,
:class:`PlaywrightMcpUnavailableEmission` use Pydantic v2 frozen
configuration; field declaration order is load-bearing for byte-
stable ``model_dump_json()`` output (parallel to 1.4 / 1.5 / 1.6 /
1.7 / 1.8 / 1.9 / 1.10a / 1.10b / 4.1 / 4.2 / 4.3 discipline).

WebDriver Protocol ↔ MCP tool surface mapping (consumed by the
step file's binding paragraph per ADR-004's substrate-vs-LLM-runtime
split):

    * :meth:`WebDriver.navigate` ↔ ``mcp__playwright__browser_navigate``
    * :meth:`WebDriver.click` ↔ ``mcp__playwright__browser_click``
    * :meth:`WebDriver.type_text` ↔ ``mcp__playwright__browser_type``
      (the protocol method is ``type_text`` rather than ``type`` to
      avoid shadowing the Python built-in :func:`type`; the step
      file's binding paragraph names both the protocol method
      ``type_text`` and the underlying epic-AC vocabulary
      ``type``).
    * :meth:`WebDriver.hover` ↔ ``mcp__playwright__browser_hover``
    * :meth:`WebDriver.drag` ↔ ``mcp__playwright__browser_drag``
    * :meth:`WebDriver.screenshot` ↔
      ``mcp__playwright__browser_take_screenshot``
    * :meth:`WebDriver.assert_dom_text` ↔
      ``mcp__playwright__browser_snapshot`` followed by textual
      comparison.
    * :meth:`WebDriver.inspect_network` ↔
      ``mcp__playwright__browser_network_requests``

MaskedSelectorPolicy redaction algorithm:
    The reference :class:`NoOpEvidenceCapturer` reads the policy's
    ``masked_selectors`` tuple; for each selector it scans the
    payload (decoded as UTF-8 with ``errors="replace"`` if bytes)
    for a textual rendering of the selector's content (e.g.,
    ``input[type=password]`` matches the value attribute substring
    typically rendered as ``value="<secret>"`` in DOM snapshots).
    Matched substrings are replaced with
    :data:`MASKED_REDACTION_SENTINEL` (``"[REDACTED]"``). The
    matching is dev's-call regex-based at MVP; Story 4.12 may
    thicken the matching to a structural DOM-tree walk if the
    practitioner reports false negatives. The
    :data:`MASKED_REDACTION_SENTINEL` is recorded in
    ``docs/extension-audit.md`` per the no-introductions principle.
"""

from __future__ import annotations

import os
import signal
import time
from datetime import datetime, timezone
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness.env_provisioning import (
    EnvKind,
    MarkerEmissionRecord,
    ProvisionedEnv,
)
from loud_fail_harness.qa_behavioral_plan import QABehavioralPlanEntry
from loud_fail_harness.qa_evidence_tier import (
    EvidenceRef,
    SemanticVerificationResult,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

#: The marker-class string identifier emitted on mid-run Playwright
#: MCP unavailability (Story 1.4 enumeration; ``schemas/marker-
#: taxonomy.yaml`` line 226). Consumed AS-IS; THIS module is the
#: FIRST runtime emitter of the marker for the web-driver surface.
#: Mirrors Story 3.3's :data:`REVIEW_LAYER_FAILED_MARKER`,
#: Story 4.2's :data:`PLAN_DRIFT_DETECTED_MARKER`, and Story 4.3's
#: :data:`ENV_SETUP_FAILED_MARKER` symbolic-constant discipline.
PLAYWRIGHT_MCP_UNAVAILABLE_MARKER: str = "playwright-mcp-unavailable"

#: The dev's-call sentinel string the :class:`EvidenceCapturer`
#: substitutes for masked-selector content per the verbatim epic AC
#: at epics.md line 1917 ("evidence files respect masked-selector
#: configuration if present in qa-runbook.yaml"). Recorded in
#: ``docs/extension-audit.md`` per the no-introductions principle.
MASKED_REDACTION_SENTINEL: str = "[REDACTED]"

#: The epic-AC ``failure_step`` value mirroring the
#: ``env-setup-failed.sub_classifications`` enum member at
#: ``schemas/marker-taxonomy.yaml`` line 111 byte-for-byte.
#: Story 4.3's :func:`provision_env` reads this attribute via
#: ``getattr(exc, "failure_step", "dev-server-not-ready")`` and
#: routes through :func:`surface_env_setup_failure` with the value
#: as ``sub_cause``.
_PLAYWRIGHT_LAUNCH_FAILED_STEP: Literal["playwright-launch-failed"] = (
    "playwright-launch-failed"
)

#: Bounded-wait interval (seconds) between SIGTERM and SIGKILL in
#: :class:`PlaywrightTeardown.teardown`. Dev's-call default mirrored
#: from cross-OS subprocess-termination convention (5 seconds is the
#: typical balance between graceful-shutdown opportunity and
#: orphan-prevention; Story 4.13's wrapper-level integration MAY
#: override per-runbook configuration when Story 7.5 scaffolds the
#: stub).
_TEARDOWN_GRACE_INTERVAL_SECONDS: float = 5.0

#: Polling interval (seconds) used by :class:`PlaywrightTeardown` to
#: check whether the SIGTERM'd process has exited within the bounded
#: wait. Small enough for snappy clean-shutdown detection; large
#: enough to avoid burning CPU on the polling loop.
_TEARDOWN_POLL_INTERVAL_SECONDS: float = 0.1


# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class WebDriverAssertion(BaseModel):
    """One assertion-record returned by :meth:`WebDriver.assert_dom_text`.

    Frozen for hashability + determinism per Epic 1 retro Action #2.
    Field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.

    Field semantics:
        * ``passed`` — bool; ``True`` iff the assertion held.
        * ``observed`` — the actual textual content the driver
          observed at the selector.
        * ``expected`` — the textual content the assertion required.
    """

    model_config = ConfigDict(frozen=True)

    passed: bool
    observed: str
    expected: str


class NetworkRequest(BaseModel):
    """One network-request record returned by
    :meth:`WebDriver.inspect_network`.

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics (mirrors the typical
    ``mcp__playwright__browser_network_requests`` tool surface):
        * ``method`` — the HTTP method (``GET``, ``POST``, ...).
        * ``url`` — the request URL the browser issued.
        * ``status`` — the response status code.
    """

    model_config = ConfigDict(frozen=True)

    method: str
    url: str
    status: int


class MaskedSelectorPolicy(BaseModel):
    """The masked-selector configuration consumed by the
    :class:`EvidenceCapturer` to redact sensitive content from
    persisted evidence.

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Strict-shape enforced via ``ConfigDict(extra="forbid")`` —
    accidentally adding an undeclared field is a contract violation
    raised at instantiation rather than silently absorbed (parallel
    to the schema-level ``additionalProperties: false`` discipline
    Story 1.10b codified for envelope shapes).

    Field semantics:
        * ``masked_selectors`` — tuple of CSS selectors whose
          content is redacted in screenshots / DOM snapshots /
          network traces. Empty tuple means "no redaction" (the
          payload is persisted verbatim).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    masked_selectors: tuple[str, ...] = Field(default_factory=tuple)


class AcResult(BaseModel):
    """The per-AC verification record produced by :func:`verify_ac`.

    The Pydantic-v2 projection's ``model_dump()`` JSON shape mirrors
    ``schemas/envelope.schema.yaml`` ``$defs/ac_result`` byte-for-byte
    (the five required fields with the same types and the same enum
    bounds; post-Story-4.8 the ``evidence_refs`` items carry the
    bumped ``$defs/evidence_ref`` ``{path, tier}`` shape and
    ``semantic_verification`` is the bumped closed string enum).

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``ac_id`` — the AC identifier from the dispatch payload's
          ``ac_list`` (e.g., ``"AC-1"``). Must be non-empty
          (mirrors the schema's ``minLength: 1``).
        * ``status`` — one of ``pass | fail | blocked``. Mirrors the
          schema's ``enum: [pass, fail, blocked]``.
        * ``assertions`` — tuple of human-readable assertion strings
          the verification ran (≥ 1 entry on ``pass`` /
          ``fail``; on ``blocked`` may carry the diagnostic of
          the precondition failure that prevented verification).
        * ``evidence_refs`` — tuple of :class:`EvidenceRef` entries
          (each carrying a repo-relative ``path`` + an
          ``EvidenceTier`` ∈ {tier-1-mechanical, tier-2-outcome,
          tier-3-semantic}). At driver-projection time (THIS module +
          :mod:`http_driver`) every entry is captured at
          ``tier-1-mechanical`` because drivers capture mechanical
          evidence by definition; Tier-2 outcome elevation is a
          wrapper composition concern deferred to Story 4.13.
        * ``semantic_verification`` — one of ``"verified" |
          "not_configured" | "not_applicable"`` (the FR21 closed
          string enum from Story 4.8). Drivers do not run semantic
          verification; the wrapper composes
          :func:`loud_fail_harness.qa_evidence_tier.evaluate_semantic_verification`
          and projects the result onto the envelope-level AC entry.
          The default ``"not_applicable"`` is the wrapper-side default
          for the existing AC-1-only Tier-1-only Epic-2-scope wrapper
          usage at ``agents/qa.md`` line 35 (Story 2.10 contract).
    """

    model_config = ConfigDict(frozen=True)

    ac_id: str = Field(min_length=1)
    status: Literal["pass", "fail", "blocked"]
    assertions: tuple[str, ...]
    evidence_refs: tuple[EvidenceRef, ...]
    semantic_verification: SemanticVerificationResult = "not_applicable"


class PlaywrightMcpUnavailableDiagnostic(BaseModel):
    """The structured diagnostic context carried on the
    ``playwright-mcp-unavailable`` marker emission AND surfaced
    through Story 4.10's escalation routing.

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``story_id`` — the BMAD story identifier the QA dispatch
          is scoped to.
        * ``action_kind`` — the failed driver-action name (one of
          ``navigate | click | type_text | hover | drag |
          screenshot | assert_dom_text | inspect_network``); free-
          form string at the substrate layer to avoid coupling to
          the seven-action enum (the LLM-runtime protocol owns the
          enum closure; the substrate accepts the failed-action
          name from the wrapper).
        * ``prior_evidence_refs`` — tuple of repo-relative paths
          for evidence the QA wrapper had already captured BEFORE
          the mid-run unavailability fired. Preserved per the
          verbatim epic AC at epics.md line 1912 ("evidence already
          captured is preserved").
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    action_kind: str = Field(min_length=1)
    prior_evidence_refs: tuple[str, ...]


class PlaywrightMcpUnavailableEmission(BaseModel):
    """The two-channel atomic-emission return shape of
    :func:`surface_playwright_mcp_unavailable`.

    Channels are paired by construction — both ``marker_record`` and
    ``diagnostic`` are present on a successful unavailability
    emission; registry rejection raises :exc:`UnknownMarkerClass`
    BEFORE either is constructed (atomic-on-failure per Pattern 5;
    mirrors Story 4.2's :class:`PlanDriftEmission` shape and
    Story 4.3's :class:`EnvSetupFailureEmission` shape verbatim).

    Frozen for determinism + hashability. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``marker_record`` — the
          :class:`MarkerEmissionRecord` (imported from Story 4.3's
          :mod:`loud_fail_harness.env_provisioning` per the cross-
          module reuse precedent at AC-1) carrying
          ``marker_class="playwright-mcp-unavailable"`` +
          ``sub_cause=None`` (the marker has empty
          ``sub_classifications: []`` per
          ``schemas/marker-taxonomy.yaml`` line 234) +
          the diagnostic-projected ``context``.
        * ``diagnostic`` — the
          :class:`PlaywrightMcpUnavailableDiagnostic` carrying the
          three-field structured context. Co-exposed for ergonomic
          access without unwrapping ``marker_record``.
    """

    model_config = ConfigDict(frozen=True)

    marker_record: MarkerEmissionRecord
    diagnostic: PlaywrightMcpUnavailableDiagnostic


# --------------------------------------------------------------------------- #
# Protocols (project-type-specific availability probe / dev-server runner /  #
# web driver / evidence capturer)                                             #
# --------------------------------------------------------------------------- #


@runtime_checkable
class PlaywrightAvailabilityProbe(Protocol):
    """Project-type-specific Playwright MCP availability probe.

    Production binds to a Playwright-MCP-tool-call probe at the LLM-
    runtime layer per the
    ``skills/bmad-automation/steps/qa-driver-playwright.md`` step
    file (one MCP-tool ping; on tool-error or absence return
    ``False``); tests use :class:`NoOpAvailabilityProbe`.
    """

    def is_available(self) -> bool:
        """Return ``True`` iff Playwright MCP is reachable; ``False``
        otherwise (including any tool-error or absence condition).
        """


@runtime_checkable
class DevServerRunner(Protocol):
    """Project-type-specific dev-server runner.

    Production binds to a :func:`subprocess.Popen` of the project's
    dev-server command read from ``_bmad/automation/qa-runbook.yaml``
    at the LLM-runtime layer per the
    ``skills/bmad-automation/steps/qa-driver-playwright.md`` step
    file; tests use :class:`NoOpDevServerRunner`.
    """

    def start(self, port: int) -> int:
        """Spawn the dev server bound to ``port``; return the spawned
        process's PID.
        """


@runtime_checkable
class WebDriver(Protocol):
    """The seven driver-action abstraction the QA wrapper composes
    against the running web product per the verbatim epic AC at
    epics.md line 1904.

    Production implementations bind each method to the corresponding
    ``mcp__playwright__browser_*`` tool at the LLM-runtime layer per
    the step file at
    ``skills/bmad-automation/steps/qa-driver-playwright.md``; tests
    use :class:`NoOpWebDriver`.

    Method ↔ tool surface mapping (recorded byte-for-byte in the
    module docstring above and the step file's
    ``## Procedure — WebDriver Protocol ↔ MCP tool mappings``
    section):

        * :meth:`navigate` ↔ ``mcp__playwright__browser_navigate``
        * :meth:`click` ↔ ``mcp__playwright__browser_click``
        * :meth:`type_text` ↔ ``mcp__playwright__browser_type``
          (the Python method is named ``type_text`` to avoid
          shadowing the built-in :func:`type`; the epic-AC vocabulary
          ``type`` is preserved in the step file's binding
          paragraph).
        * :meth:`hover` ↔ ``mcp__playwright__browser_hover``
        * :meth:`drag` ↔ ``mcp__playwright__browser_drag``
        * :meth:`screenshot` ↔
          ``mcp__playwright__browser_take_screenshot``
        * :meth:`assert_dom_text` ↔
          ``mcp__playwright__browser_snapshot`` + textual comparison
        * :meth:`inspect_network` ↔
          ``mcp__playwright__browser_network_requests``
    """

    def navigate(self, url: str) -> None:
        """Navigate the browser to ``url``."""

    def click(self, selector: str) -> None:
        """Click the element matching ``selector``."""

    def type_text(self, selector: str, text: str) -> None:
        """Type ``text`` into the element matching ``selector``.

        Renamed from the epic-AC vocabulary ``type`` to ``type_text``
        to avoid shadowing Python's built-in :func:`type`. The step
        file's ``## Procedure — WebDriver Protocol ↔ MCP tool
        mappings`` section names both names.
        """

    def hover(self, selector: str) -> None:
        """Hover the cursor over the element matching ``selector``."""

    def drag(self, source_selector: str, target_selector: str) -> None:
        """Drag the element matching ``source_selector`` to the
        element matching ``target_selector``.
        """

    def screenshot(self, name: str) -> str:
        """Capture a screenshot named ``name``; return the repo-
        relative evidence_ref path the screenshot was persisted to.
        """

    def assert_dom_text(
        self, selector: str, expected: str
    ) -> WebDriverAssertion:
        """Compare the textual content of the element matching
        ``selector`` against ``expected``; return the
        :class:`WebDriverAssertion` record.
        """

    def inspect_network(self) -> tuple[NetworkRequest, ...]:
        """Return the tuple of network-request records the browser
        captured since the last invocation.
        """


@runtime_checkable
class EvidenceCapturer(Protocol):
    """Per-FR49 evidence-capture abstraction.

    Production implementations write to disk under
    ``_bmad-output/qa-evidence/{story-id}/{run-id}/`` and apply the
    :class:`MaskedSelectorPolicy` redaction BEFORE persisting; tests
    use :class:`NoOpEvidenceCapturer` which records the would-be path
    + redacted payload in memory without writing to disk.
    """

    def capture(self, action_kind: str, payload: bytes | str) -> str:
        """Persist ``payload`` (with masked-selector redaction
        applied) for the action named ``action_kind``; return the
        repo-relative evidence_ref path.
        """


# --------------------------------------------------------------------------- #
# Exceptions                                                                  #
# --------------------------------------------------------------------------- #


class PlaywrightLaunchFailed(Exception):
    """Raised by :class:`PlaywrightProvisioner.provision` when the
    injected :class:`PlaywrightAvailabilityProbe` returns ``False``
    AT init-time-of-provisioning.

    Pattern 5 named-invariant diagnostic. The ``failure_step``
    attribute mirrors the
    ``env-setup-failed.sub_classifications`` enum member at
    ``schemas/marker-taxonomy.yaml`` line 111 byte-for-byte; Story
    4.3's :func:`provision_env` reads the attribute via
    ``getattr(exc, "failure_step", "dev-server-not-ready")`` and
    routes through
    :func:`loud_fail_harness.env_provisioning.surface_env_setup_failure`
    with ``sub_cause="playwright-launch-failed"``.

    Distinct from :exc:`PlaywrightMcpUnavailable` which surfaces
    MID-RUN MCP unavailability AFTER provisioning succeeded;
    :exc:`PlaywrightLaunchFailed` is the AT-INIT-time variant that
    flows through the env-setup-failed marker class instead.
    """

    failure_step: Literal["playwright-launch-failed"] = (
        _PLAYWRIGHT_LAUNCH_FAILED_STEP
    )


class PlaywrightMcpUnavailable(Exception):
    """Raised by the QA wrapper (Story 4.13 forthcoming) on a mid-run
    Playwright MCP tool-call exception.

    Pattern 5 named-invariant diagnostic. Carries the structured
    :class:`PlaywrightMcpUnavailableEmission` so the LLM-runtime
    protocol's catch site has the marker_record + diagnostic in hand
    for Story 4.10's escalation routing without unwrapping the
    exception further.

    Distinct from :exc:`PlaywrightLaunchFailed` which fires AT-INIT-
    time-of-provisioning; this exception fires MID-RUN AFTER
    provisioning succeeded but before AC verification completed.

    Attributes:
        emission: The :class:`PlaywrightMcpUnavailableEmission`
            carrying the marker_record + diagnostic.
    """

    def __init__(self, emission: PlaywrightMcpUnavailableEmission) -> None:
        self.emission: PlaywrightMcpUnavailableEmission = emission
        super().__init__(
            f"playwright MCP unavailable mid-run: action_kind="
            f"{emission.diagnostic.action_kind!r}; "
            f"prior_evidence_refs="
            f"{emission.diagnostic.prior_evidence_refs!r}"
        )


# --------------------------------------------------------------------------- #
# Reference NoOp impls (test-suite ONLY)                                      #
# --------------------------------------------------------------------------- #


class NoOpAvailabilityProbe:
    """Reference :class:`PlaywrightAvailabilityProbe` implementation
    for the test suite ONLY.

    Returns the constructor-supplied ``available`` boolean from every
    :meth:`is_available` call.

    NOT for production use — the LLM-runtime protocol at
    ``skills/bmad-automation/steps/qa-driver-playwright.md`` ships
    the real MCP-tool-ping binding.
    """

    def __init__(self, *, available: bool = True) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available


class NoOpDevServerRunner:
    """Reference :class:`DevServerRunner` implementation for the test
    suite ONLY.

    Returns a deterministic dummy PID from every :meth:`start` call.
    Records the latest ``port`` argument so tests can assert the
    runner was invoked with the expected ephemeral port.

    NOT for production use — the LLM-runtime protocol at
    ``skills/bmad-automation/steps/qa-driver-playwright.md`` ships
    the real ``subprocess.Popen``-of-dev-server binding.
    """

    def __init__(self, *, pid: int = 54321) -> None:
        self._pid = pid
        self.last_port: int | None = None
        self.call_count: int = 0

    def start(self, port: int) -> int:
        self.last_port = port
        self.call_count += 1
        return self._pid


class NoOpWebDriver:
    """Reference :class:`WebDriver` implementation for the test suite
    ONLY.

    Records every action's arguments for assertion. The
    :meth:`assert_dom_text` method returns the constructor-supplied
    :class:`WebDriverAssertion` record (or raises the constructor-
    supplied exception if one was supplied) so tests can drive both
    the pass and fail paths.

    NOT for production use — the LLM-runtime protocol at
    ``skills/bmad-automation/steps/qa-driver-playwright.md`` ships
    the real ``mcp__playwright__browser_*`` tool bindings.
    """

    def __init__(
        self,
        *,
        assertion: WebDriverAssertion | None = None,
        action_exception: BaseException | None = None,
    ) -> None:
        self._assertion = assertion or WebDriverAssertion(
            passed=True, observed="hello", expected="hello"
        )
        self._action_exception = action_exception
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def _record(self, action_kind: str, *args: str) -> None:
        if self._action_exception is not None:
            raise self._action_exception
        self.calls.append((action_kind, args))

    def navigate(self, url: str) -> None:
        self._record("navigate", url)

    def click(self, selector: str) -> None:
        self._record("click", selector)

    def type_text(self, selector: str, text: str) -> None:
        self._record("type_text", selector, text)

    def hover(self, selector: str) -> None:
        self._record("hover", selector)

    def drag(self, source_selector: str, target_selector: str) -> None:
        self._record("drag", source_selector, target_selector)

    def screenshot(self, name: str) -> str:
        self._record("screenshot", name)
        return f"_bmad-output/qa-evidence/noop/{name}.png"

    def assert_dom_text(
        self, selector: str, expected: str
    ) -> WebDriverAssertion:
        self._record("assert_dom_text", selector, expected)
        return self._assertion

    def inspect_network(self) -> tuple[NetworkRequest, ...]:
        self._record("inspect_network")
        return ()


class NoOpEvidenceCapturer:
    """Reference :class:`EvidenceCapturer` implementation for the
    test suite ONLY.

    Applies :class:`MaskedSelectorPolicy` redaction to every payload
    BEFORE recording the would-be evidence path. Records the redacted
    payload in memory (the :attr:`recorded` list of ``(action_kind,
    redacted_payload, would_be_path)`` tuples) without writing to
    disk so tests can assert byte-equality on the redacted output.

    NOT for production use — Story 4.12 ships the real on-disk
    persistence binding.
    """

    def __init__(
        self,
        masked_selectors: MaskedSelectorPolicy | None = None,
        *,
        story_id: str = "noop-story",
        run_id: str = "noop-run",
    ) -> None:
        self._policy = masked_selectors or MaskedSelectorPolicy()
        self._story_id = story_id
        self._run_id = run_id
        self.recorded: list[tuple[str, str, str]] = []
        self._counter = 0

    def capture(self, action_kind: str, payload: bytes | str) -> str:
        text = (
            payload.decode("utf-8", errors="replace")
            if isinstance(payload, bytes)
            else payload
        )
        redacted = _apply_masked_selector_policy(text, self._policy)
        self._counter += 1
        path = (
            f"_bmad-output/qa-evidence/{self._story_id}/"
            f"{self._run_id}/{action_kind}-{self._counter:04d}.txt"
        )
        self.recorded.append((action_kind, redacted, path))
        return path


# --------------------------------------------------------------------------- #
# PlaywrightProvisioner / PlaywrightTeardown — Provisioner / Teardown impls  #
# --------------------------------------------------------------------------- #


class PlaywrightProvisioner:
    """Project-type-specific (web) :class:`Provisioner` Protocol
    implementation.

    Composes the injected :class:`PlaywrightAvailabilityProbe` and
    :class:`DevServerRunner` to provision a web env at the
    orchestrator-owned ``review → qa`` seam (Story 4.3's
    :func:`provision_env`).

    Behavior (load-bearing per AC-2):

        1. Call ``self._availability_probe.is_available()``; on
           ``False``, raise :exc:`PlaywrightLaunchFailed` carrying
           ``failure_step="playwright-launch-failed"`` so Story 4.3's
           :func:`provision_env` catches it via
           ``getattr(exc, "failure_step", "dev-server-not-ready")``
           and routes through
           :func:`loud_fail_harness.env_provisioning.surface_env_setup_failure`
           with ``sub_cause="playwright-launch-failed"``.
        2. On availability ``True``, call
           ``self._dev_server_runner.start(port)``; the runner
           returns the spawned PID. Any exception raised by the
           runner propagates unchanged (Story 4.3's
           :func:`provision_env` catches it and routes via the
           default ``failure_step="dev-server-not-ready"``).
        3. Construct and return a :class:`ProvisionedEnv` carrying
           ``env_kind=project_type`` + the input ``port`` + the runner's
           PID + a non-null timezone-aware UTC ``started_at``
           timestamp.

    The class structurally satisfies Story 4.3's
    :class:`Provisioner` Protocol — ``isinstance(provisioner,
    Provisioner)`` returns ``True`` because :class:`Provisioner` is
    ``@runtime_checkable``.

    Atomic-on-failure: probe fires BEFORE runner; on probe-false the
    runner is NEVER invoked — verified by AC-9 test #3.
    """

    def __init__(
        self,
        availability_probe: PlaywrightAvailabilityProbe,
        dev_server_runner: DevServerRunner,
    ) -> None:
        self._availability_probe = availability_probe
        self._dev_server_runner = dev_server_runner

    def provision(
        self,
        story_id: str,
        project_type: EnvKind,
        port: int,
    ) -> ProvisionedEnv:
        """Compose the project-type-specific (web) provisioning per
        AC-2.

        Args:
            story_id: BMAD story identifier (signature-symmetric
                with Story 4.3's :class:`Provisioner` Protocol;
                threaded through for downstream visibility).
            project_type: ``web`` or ``api``; passed through
                directly as the ``env_kind`` field of the returned
                :class:`ProvisionedEnv` per the
                :class:`Provisioner` Protocol signature. Callers
                are responsible for dispatching to the correct
                provisioner — Story 4.5 adds the sibling
                :class:`HttpProvisioner` for ``api`` project types.
            port: Integer ephemeral TCP port allocated by Story
                4.3's :func:`allocate_ephemeral_port`.

        Returns:
            :class:`ProvisionedEnv` carrying ``env_kind=project_type``,
            ``port`` matching the input, ``pid`` matching the
            runner's return, ``started_at`` non-null timezone-aware
            UTC datetime.

        Raises:
            :exc:`PlaywrightLaunchFailed`: the availability probe
                returned ``False``; the ``failure_step`` attribute
                is ``"playwright-launch-failed"`` byte-for-byte.
            Whatever exception the runner raised: propagated
                unchanged so Story 4.3's :func:`provision_env`
                routes via the default
                ``failure_step="dev-server-not-ready"``.
        """
        _ = story_id  # Sensor-not-advisor: signature-symmetric with the protocol.
        if not self._availability_probe.is_available():
            raise PlaywrightLaunchFailed(
                "Playwright MCP unavailable at provisioning time"
            )
        pid = self._dev_server_runner.start(port)
        return ProvisionedEnv(
            env_kind=project_type,
            port=port,
            pid=pid,
            started_at=datetime.now(timezone.utc),
        )


class PlaywrightTeardown:
    """Project-type-specific (web) :class:`Teardown` Protocol
    implementation.

    Implements the SIGTERM → bounded-wait → SIGKILL escalation per
    AC-3 + the cross-OS subprocess-termination convention.

    Behavior:

        1. Call ``os.kill(provisioned_env.pid, signal.SIGTERM)``.
        2. Poll for up to :data:`_TEARDOWN_GRACE_INTERVAL_SECONDS`
           in :data:`_TEARDOWN_POLL_INTERVAL_SECONDS` increments,
           checking process liveness via ``os.kill(pid, 0)``
           (which raises :exc:`ProcessLookupError` once the process
           has exited cleanly).
        3. On bounded-wait expiry without clean exit, escalate to
           ``os.kill(provisioned_env.pid, signal.SIGKILL)``.
        4. On any :exc:`ProcessLookupError` along the way, swallow
           the exception (idempotent teardown — the process is
           already gone, the structural goal is satisfied).

    The class structurally satisfies Story 4.3's :class:`Teardown`
    Protocol.
    """

    def teardown(self, provisioned_env: ProvisionedEnv) -> None:
        """Terminate the dev-server process per the SIGTERM →
        bounded-wait → SIGKILL escalation per AC-3.
        """
        pid = provisioned_env.pid
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return  # Idempotent: process already gone or not accessible.

        deadline = (
            time.monotonic() + _TEARDOWN_GRACE_INTERVAL_SECONDS
        )
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, PermissionError):
                return  # Clean exit or process no longer accessible.
            time.sleep(_TEARDOWN_POLL_INTERVAL_SECONDS)

        # Bounded wait expired without clean exit; escalate.
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            return  # Race: process exited or no longer accessible.


# --------------------------------------------------------------------------- #
# Public API — verify_ac + surface_playwright_mcp_unavailable                #
# --------------------------------------------------------------------------- #


def verify_ac(
    ac_id: str,
    ac_text: str,
    plan_entry: QABehavioralPlanEntry,
    driver: WebDriver,
    evidence_capturer: EvidenceCapturer,
    masked_selectors: MaskedSelectorPolicy,
) -> AcResult:
    """Compose the per-AC verification primitive.

    Behavior (load-bearing per AC-4):

        * Dispatch the appropriate :class:`WebDriver` action per the
          plan entry's ``assertion_shape`` (declarative pattern; the
          MVP placeholder dispatch at THIS story's scope routes every
          plan entry through :meth:`WebDriver.assert_dom_text` against
          the AC text — Story 4.6 thickens the dispatcher to a richer
          ``assertion_shape``-driven router; Story 4.7 enforces the
          AC-assertion-evidence triple at the schema level).
        * Capture mechanical Tier-1 evidence per
          ``plan_entry.expected_evidence_tier`` via
          ``evidence_capturer.capture(action_kind, payload)``. At
          THIS story's scope only Tier-1 mechanical evidence is
          captured; Tier-2 outcome and Tier-3 semantic are
          Story 4.8's surface.
        * Construct and return the :class:`AcResult` per the
          ``$defs/ac_result`` envelope shape:
            - ``status="pass"`` iff the dispatched assertion held
              AND ≥ 1 evidence_ref was captured.
            - ``status="fail"`` if the assertion did NOT hold.
            - ``status="blocked"`` if the dispatched action raised a
              non-:exc:`PlaywrightMcpUnavailable` exception (mid-run
              MCP unavailability is the QA wrapper's responsibility
              to catch and route through
              :func:`surface_playwright_mcp_unavailable`; THIS
              function does not catch it).

    The function does NOT itself emit markers, write to
    ``run-state.yaml``, or read TEA artifacts (FR16 invariant;
    structurally encoded by the function's argument list excluding
    TEA-related shapes).

    Args:
        ac_id: The AC identifier (e.g., ``"AC-1"``); written
            verbatim to the returned :class:`AcResult.ac_id`.
        ac_text: The AC's verbatim text from the dispatch payload's
            ``ac_list``; used at the MVP placeholder dispatcher as
            the ``expected`` argument to
            :meth:`WebDriver.assert_dom_text`.
        plan_entry: The
            :class:`loud_fail_harness.qa_behavioral_plan.QABehavioralPlanEntry`
            for THIS AC; carries the ``assertion_shape`` +
            ``expected_evidence_tier`` (consumed by Story 4.6 / 4.8
            for richer dispatch; THIS story's MVP dispatcher reads
            the ``assertion_shape`` for the human-readable assertion
            string only).
        driver: The :class:`WebDriver` Protocol implementation;
            production binds to the ``mcp__playwright__browser_*``
            tool surface per the step file at
            ``skills/bmad-automation/steps/qa-driver-playwright.md``;
            tests use :class:`NoOpWebDriver`.
        evidence_capturer: The :class:`EvidenceCapturer` Protocol
            implementation; production writes to disk under
            ``_bmad-output/qa-evidence/{story-id}/{run-id}/``;
            tests use :class:`NoOpEvidenceCapturer`.
        masked_selectors: The :class:`MaskedSelectorPolicy` consumed
            by the :class:`EvidenceCapturer` to redact sensitive
            content. Threaded through so the ``verify_ac`` signature
            structurally encodes the FR-AC-1917 redaction commitment.

    Returns:
        :class:`AcResult` whose ``model_dump()`` JSON projection
        mirrors ``schemas/envelope.schema.yaml`` ``$defs/ac_result``
        lines 164-194 byte-for-byte.
    """
    # masked_selectors is threaded through for structural documentation of
    # the FR-AC-1917 redaction commitment. The EvidenceCapturer passed to
    # this function MUST already be constructed with the same policy —
    # verify_ac does NOT apply the policy itself. A caller who passes a
    # policy here but constructs the EvidenceCapturer without it will
    # receive unredacted output. See NoOpEvidenceCapturer for the canonical
    # construction pattern: NoOpEvidenceCapturer(masked_selectors=policy).
    _ = masked_selectors
    assertion_str = (
        plan_entry.assertion_shape
        if plan_entry.assertion_shape
        else f"verify: {ac_text}"
    )

    try:
        assertion = driver.assert_dom_text(
            "body",  # MVP placeholder selector; Story 4.6 / 4.7 thicken.
            ac_text,
        )
    except PlaywrightMcpUnavailable:
        # Mid-run MCP unavailability is the QA wrapper's responsibility
        # to catch and route through surface_playwright_mcp_unavailable.
        # THIS function does NOT catch it — propagate unchanged.
        raise
    except Exception as exc:
        # Non-MCP exception during AC verification — verification cannot
        # complete; status="blocked" with the exception's diagnostic
        # captured for downstream visibility (Story 4.13 thickens
        # consumer semantics; Story 4.10's escalation contracts +
        # Story 4.11's compromise blockquote are render-surface only).
        # Guard against the capturer itself raising so the original
        # driver error is preserved in the assertions tuple.
        try:
            evidence_ref = evidence_capturer.capture(
                "blocked-diagnostic",
                f"verify_ac aborted on driver action: {exc!r}",
            )
        except Exception:
            evidence_ref = (
                f"_bmad-output/qa-evidence/capturer-unavailable/{ac_id}.txt"
            )
        return AcResult(
            ac_id=ac_id,
            status="blocked",
            assertions=(assertion_str, f"blocked: {exc!r}"),
            evidence_refs=(EvidenceRef(path=evidence_ref, tier="tier-1-mechanical"),),
            semantic_verification="not_applicable",
        )

    # Capture mechanical Tier-1 evidence regardless of pass/fail so the
    # ac_results record always carries ≥ 1 evidence_ref per the AC-4
    # commitment.
    evidence_payload = (
        f"observed={assertion.observed!r} expected={assertion.expected!r}"
    )
    evidence_ref = evidence_capturer.capture("dom-snapshot", evidence_payload)

    if assertion.passed:
        return AcResult(
            ac_id=ac_id,
            status="pass",
            assertions=(assertion_str,),
            evidence_refs=(EvidenceRef(path=evidence_ref, tier="tier-1-mechanical"),),
            semantic_verification="not_applicable",
        )

    return AcResult(
        ac_id=ac_id,
        status="fail",
        assertions=(
            assertion_str,
            f"observed={assertion.observed!r} expected={assertion.expected!r}",
        ),
        evidence_refs=(EvidenceRef(path=evidence_ref, tier="tier-1-mechanical"),),
        semantic_verification="not_applicable",
    )


def surface_playwright_mcp_unavailable(
    story_id: str,
    registry: MarkerClassRegistry,
    *,
    action_kind: str,
    prior_evidence_refs: tuple[str, ...],
) -> PlaywrightMcpUnavailableEmission:
    """Surface mid-run Playwright MCP unavailability across both
    channels atomically.

    THIS function is the SINGLE source-of-truth emission path for
    the two-channel projection of a mid-run Playwright MCP
    unavailability event (FR17 + ADR-002 graceful-degrade). Composes
    Story 2.6's :func:`validate_marker_emission`. Pure: no file I/O,
    no run-state writes, no event emissions (the marker record is
    data the caller consumes; it is NOT emitted to the orchestrator-
    event log by THIS function).

    Behavior (parallel to Story 4.2's
    :func:`loud_fail_harness.qa_plan_drift.surface_plan_drift` and
    Story 4.3's
    :func:`loud_fail_harness.env_provisioning.surface_env_setup_failure`
    verbatim):

        * **Step 1 — Validate marker emission FIRST.** Calls
          :func:`validate_marker_emission(registry,
          PLAYWRIGHT_MCP_UNAVAILABLE_MARKER)`. On registry rejection
          :exc:`UnknownMarkerClass` propagates per Pattern 5; NO
          partial state is constructed (atomic-on-failure; mirrors
          Stories 3.3 / 4.2 / 4.3).
        * **Step 2 — Construct the diagnostic context** carrying
          the three required fields ``(story_id, action_kind,
          prior_evidence_refs)``.
        * **Step 3 — Construct the marker emission record** with
          ``marker_class="playwright-mcp-unavailable"``,
          ``sub_cause=None`` (the marker has empty
          ``sub_classifications: []`` per
          ``schemas/marker-taxonomy.yaml`` line 234), and the
          diagnostic-projected ``context``.
        * **Step 4 — Return the** :class:`PlaywrightMcpUnavailableEmission`
          carrying both projections.

    Args:
        story_id: BMAD story identifier (mirrors Story 4.2's
            :func:`surface_plan_drift` and Story 4.3's
            :func:`surface_env_setup_failure` parameter; threaded
            into the diagnostic context).
        registry: The runtime :class:`MarkerClassRegistry` from
            :func:`loud_fail_harness.specialist_dispatch.load_marker_class_registry`;
            must contain the ``playwright-mcp-unavailable`` marker
            class.
        action_kind: The failed driver-action name (one of
            ``navigate | click | type_text | hover | drag |
            screenshot | assert_dom_text | inspect_network``).
            Free-form string at the substrate layer to avoid
            coupling to the seven-action enum (the LLM-runtime
            protocol owns the enum closure).
        prior_evidence_refs: Tuple of repo-relative evidence-path
            strings the QA wrapper had already captured BEFORE the
            mid-run unavailability fired. Preserved verbatim per
            the verbatim epic AC at epics.md line 1912.

    Returns:
        :class:`PlaywrightMcpUnavailableEmission` carrying
        ``marker_record`` + ``diagnostic``.

    Raises:
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
            registry does not contain
            ``"playwright-mcp-unavailable"``.
    """
    validate_marker_emission(registry, PLAYWRIGHT_MCP_UNAVAILABLE_MARKER)
    diagnostic = PlaywrightMcpUnavailableDiagnostic(
        story_id=story_id,
        action_kind=action_kind,
        prior_evidence_refs=prior_evidence_refs,
    )
    marker_record = MarkerEmissionRecord(
        marker_class=PLAYWRIGHT_MCP_UNAVAILABLE_MARKER,
        sub_cause=None,
        context=diagnostic.model_dump(mode="json"),
    )
    return PlaywrightMcpUnavailableEmission(
        marker_record=marker_record,
        diagnostic=diagnostic,
    )


# --------------------------------------------------------------------------- #
# Internal redaction helper                                                   #
# --------------------------------------------------------------------------- #


def _apply_masked_selector_policy(
    text: str,
    policy: MaskedSelectorPolicy,
) -> str:
    """Apply :class:`MaskedSelectorPolicy` redaction to ``text``.

    For each masked selector, scan ``text`` for substrings rendered
    in the canonical DOM-snapshot form for the selector and replace
    them with :data:`MASKED_REDACTION_SENTINEL`.

    The MVP matching algorithm is dev's-call: for each selector, the
    function locates the substring of the form ``<selector>...</…>``
    OR ``selector="..."`` (the two textual renderings DOM snapshots
    typically carry) and redacts the contained value. Absent a
    structural DOM-tree walk (Story 4.12 may thicken), the algorithm
    falls back to a containment heuristic — if the policy lists
    ``input[type=password]``, every value attribute on a password-
    typed input element gets the sentinel. This produces correct
    behavior on the test fixtures used by AC-9 #11 and is documented
    as Story 4.4's MVP cut.

    Empty :attr:`MaskedSelectorPolicy.masked_selectors` returns the
    text verbatim (no redaction).
    """
    if not policy.masked_selectors:
        return text
    redacted = text
    for selector in policy.masked_selectors:
        if not selector:
            continue
        # Heuristic — locate occurrences of the selector's
        # canonically-rendered value substring. The selector itself
        # may appear in DOM snapshots; redact the *value* attribute
        # paired with the selector when both appear in a single
        # value="..." literal. Story 4.12 may thicken to a structural
        # DOM-tree walk if the practitioner reports false negatives.
        if "input[type=password]" in selector:
            redacted = _redact_value_attribute(redacted, "password")
        elif "input[type=" in selector:
            # Generic input[type=X] — extract X and redact value="..."
            # for inputs with that type. Use split("]", 1) to handle
            # compound selectors like input[type=text][required].
            type_value = selector.split("input[type=", 1)[1].split("]", 1)[0]
            if not type_value:
                continue
            redacted = _redact_value_attribute(redacted, type_value)
        else:
            # Fallback for non-input selectors: if the selector text
            # appears literally in the payload, redact the immediately-
            # following quoted string. Otherwise leave the payload
            # unchanged so the absence of redaction is visible at
            # review-time and the practitioner can extend the
            # algorithm.
            redacted = _redact_following_quoted(redacted, selector)
    return redacted


def _redact_value_attribute(text: str, input_type: str) -> str:
    """Replace ``value="..."`` attributes on ``<input type="<input_type>">``
    elements with ``value="[REDACTED]"``.

    Heuristic; conservative substring-based to avoid false positives
    on adjacent elements. Searches for the input-type marker first;
    when found, redacts subsequent ``value="..."`` pairs within a
    bounded window.
    """
    needle = f'type="{input_type}"'
    if needle not in text:
        # Try the alternate single-quote rendering.
        needle = f"type='{input_type}'"
        if needle not in text:
            # Try the unquoted bracket form (CSS-selector-like).
            needle = f"type={input_type}"
            if needle not in text:
                return _redact_after_token(text, input_type)
    return _redact_value_following(text, needle)


def _redact_value_following(text: str, anchor: str) -> str:
    """Within bounded windows starting at each occurrence of
    ``anchor`` in ``text``, replace the next ``value="..."`` literal
    with ``value="[REDACTED]"``. Window size is dev's-call 200 chars.
    """
    result = text
    cursor = 0
    while True:
        idx = result.find(anchor, cursor)
        if idx < 0:
            return result
        window_start = idx
        window_end = min(len(result), idx + 200)
        window = result[window_start:window_end]
        for prefix in ('value="', "value='"):
            quote_char = prefix[-1]
            v_idx = window.find(prefix)
            if v_idx < 0:
                continue
            v_abs = window_start + v_idx + len(prefix)
            close_idx = result.find(quote_char, v_abs)
            if close_idx < 0:
                continue
            result = (
                result[:v_abs]
                + MASKED_REDACTION_SENTINEL
                + result[close_idx:]
            )
            break
        cursor = window_end
    # Unreachable; the loop returns when no further anchor is found.


def _redact_after_token(text: str, token: str) -> str:
    """Last-resort heuristic — if the input-type token appears as a
    bare word, redact the next quoted value literal in a 200-char
    window (the password ``hunter2`` test fixture uses this branch
    when the snapshot omits explicit ``type="password"`` syntax).
    """
    if token not in text:
        return text
    return _redact_value_following(text, token)


def _redact_following_quoted(text: str, selector: str) -> str:
    """Fallback redaction for non-input selectors.

    Locates ``selector`` in ``text``; if found, redacts the next
    quoted string literal within a 200-char window. Conservative —
    if the selector does not appear, returns ``text`` unchanged so
    the absence of redaction is visible at review-time.
    """
    if selector not in text:
        return text
    return _redact_value_following(text, selector)


__all__ = [
    "PLAYWRIGHT_MCP_UNAVAILABLE_MARKER",
    "MASKED_REDACTION_SENTINEL",
    "WebDriverAssertion",
    "NetworkRequest",
    "MaskedSelectorPolicy",
    "AcResult",
    "PlaywrightMcpUnavailableDiagnostic",
    "PlaywrightMcpUnavailableEmission",
    "PlaywrightMcpUnavailable",
    "PlaywrightLaunchFailed",
    "PlaywrightAvailabilityProbe",
    "DevServerRunner",
    "WebDriver",
    "EvidenceCapturer",
    "PlaywrightProvisioner",
    "PlaywrightTeardown",
    "NoOpAvailabilityProbe",
    "NoOpDevServerRunner",
    "NoOpWebDriver",
    "NoOpEvidenceCapturer",
    "verify_ac",
    "surface_playwright_mcp_unavailable",
]
