"""Project-type-specific (api) HTTP driver primitives (Story 4.5).

FR17 + ADR-002 graceful-degrade + Pattern 5. Pure-library substrate
consumed by the orchestrator skill at the ``review → qa`` seam (via
Story 4.3's :func:`loud_fail_harness.env_provisioning.provision_env`)
AND by the QA wrapper at AC-iteration time (via Story 4.13's
forthcoming wrapper thickening). Composes Story 2.6's marker-class
registry, Story 4.1's :class:`QABehavioralPlanEntry` model, and
Story 4.3's :class:`Provisioner` / :class:`Teardown` Protocols
verbatim. Cross-module-reuses Story 4.4's project-type-agnostic
primitives (:class:`AcResult`, :class:`MaskedSelectorPolicy`,
:data:`MASKED_REDACTION_SENTINEL`, :class:`EvidenceCapturer`,
:class:`NoOpEvidenceCapturer`) AS-IS — these are project-type-
agnostic primitives whose canonical declaration site happens to be
``playwright_driver.py`` because Story 4.4 landed first in build
order.

Architectural placement (parallel to Story 4.2's
:mod:`loud_fail_harness.qa_plan_drift`, Story 4.3's
:mod:`loud_fail_harness.env_provisioning`, and Story 4.4's
:mod:`loud_fail_harness.playwright_driver`): this module is a
**substrate library NOT a sixth substrate component**. ADR-003
Consequence 1 enumerates exactly five substrate components
(architecture.md lines 311-315); THIS module is a substrate
**library** consumed by the orchestrator skill at provision-time
(Story 4.3's :class:`Provisioner` Protocol implementation) AND by
the QA wrapper at AC-iteration time (Story 4.6's plan-driven AC
iteration consumes :func:`verify_ac` per the verbatim epic AC at
``_bmad-output/planning-artifacts/epics.md`` lines 1927-1956). The
substrate-component count stays at FIVE; the harness module count
grows by one.

Procedural checklist (verbatim epic AC at epics.md lines 1927-1956):

    1. The orchestrator-owned env-provisioning seam (Story 4.3's
       :func:`loud_fail_harness.env_provisioning.provision_env`) is
       invoked with an :class:`HttpProvisioner` instance for ``api``
       project types.
    2. :class:`HttpProvisioner.provision` first invokes the injected
       :class:`ApiServerRunner` to spawn the API server (returning
       the spawned PID); THEN probes API service availability via
       the injected :class:`ApiAvailabilityProbe`. The runner-then-
       probe ordering is the OPPOSITE of Story 4.4's
       :class:`PlaywrightProvisioner` (which probes BEFORE running)
       because Playwright-MCP availability is a gating precondition
       independent of the dev-server, but the API server itself must
       be up before the smoke probe can succeed.
    3. On ``is_available() is False`` the provisioner raises
       :exc:`ApiServerNotReady` with attribute
       ``failure_step="dev-server-not-ready"`` so Story 4.3's
       ``provision_env`` catches it via
       ``getattr(exc, "failure_step", "dev-server-not-ready")`` and
       routes through
       :func:`loud_fail_harness.env_provisioning.surface_env_setup_failure`
       with ``sub_cause="dev-server-not-ready"`` per the
       ``schemas/marker-taxonomy.yaml`` line 112 enum value. The
       provisioner ALSO performs a best-effort
       ``os.kill(pid, signal.SIGTERM)`` cleanup of the orphan PID
       BEFORE raising (swallowing ``ProcessLookupError`` /
       ``PermissionError``) so the orphan-process surface does not
       accumulate.
    4. On availability ``True``, a :class:`ProvisionedEnv` with
       ``env_kind="api"`` is returned. The orchestrator dispatches
       QA via Story 2.6's existing path; the QA wrapper (Story 4.13
       forthcoming completion) composes :func:`verify_ac` against
       the running API product.
    5. Each :func:`verify_ac` invocation dispatches the appropriate
       :class:`ApiDriver` action sequence per the
       :class:`QABehavioralPlanEntry.assertion_shape`, captures
       evidence per ``expected_evidence_tier`` via the injected
       :class:`EvidenceCapturer`, and returns an :class:`AcResult`
       whose ``model_dump()`` projection mirrors
       ``schemas/envelope.schema.yaml`` ``$defs/ac_result`` lines
       164-194 byte-for-byte. The :class:`AcResult` shape is REUSED
       AS-IS from Story 4.4's :mod:`playwright_driver` because the
       envelope shape is project-type-agnostic.
    6. Mid-run "API broken" routing (epics.md lines 1945-1948 — the
       distinction between "API broken" env-setup-fail and "AC
       unverified" verification-fail): when an :class:`ApiDriver`
       method raises an exception classified as service-broken
       (connection-refused, timeout, 5xx-unrelated-to-AC-content),
       the substrate exposes the routing-shape signal via the
       :exc:`ApiServiceBroken` exception class. Production
       :class:`ApiDriver` impls raise :exc:`ApiServiceBroken` on
       these conditions; tests' :class:`NoOpApiDriver` accepts a
       configured exception. The QA wrapper's ``except
       ApiServiceBroken as exc`` clause calls Story 4.3's
       :func:`surface_env_setup_failure` AS-IS with
       ``failure_step=exc.failure_step`` and
       ``failure_diagnostic=exc.failure_diagnostic`` — THIS module
       does NOT introduce a new emission helper because the
       marker class re-used is the existing ``env-setup-failed``
       from Story 1.4 / Story 4.3, NOT a new class. The asymmetry
       vs Story 4.4 (which DID introduce
       ``surface_playwright_mcp_unavailable`` because its mid-run
       path needed a structurally distinct
       ``playwright-mcp-unavailable`` marker class — the remediation
       differs: "transient MCP-tool-surface connectivity loss" vs
       "API server not responding") is recorded in
       ``docs/extension-audit.md``.
    7. AC verification-fail routing (FR24a): an :class:`ApiAssertion`
       returning ``passed=False`` produces an :class:`AcResult` with
       ``status="fail"`` carrying the failed assertion + the captured
       :class:`NetworkTraceRecord` evidence — NO marker emission;
       the wrapper-side ``status: fail`` envelope is the
       verification-fail signal Story 4.10 routes per FR24a (distinct
       from the API-broken path above).
    8. Masked-selector redaction per epics.md line 1942 ("request/
       response traces (with optional sensitive-field masking per
       Story 4.4's :class:`MaskedSelectorPolicy` ``masked_selectors``
       field) are persisted"; Story 4.12 documents the AS-IS reuse
       posture without modifying the policy class): the
       :class:`EvidenceCapturer`'s ``capture(action_kind, payload)``
       implementation applies the :class:`MaskedSelectorPolicy` to
       its inputs BEFORE persisting, replacing matched substrings
       with :data:`MASKED_REDACTION_SENTINEL` (``"[REDACTED]"``).
       The api-side matching algorithm extends Story 4.4's algorithm
       (CSS-selector-style ``input[type=...]`` patterns) with plain-
       text-selector matching for HTTP header names (case-
       insensitive), JSON-body field-name patterns, and query-string
       parameter names — the api-side wrapper
       :func:`_apply_api_masked_selector_policy` DELEGATES to Story
       4.4's helpers for the CSS-selector branch AND ADDS the
       api-specific plain-text matchers without modifying Story
       4.4's algorithm.
    9. After QA return, the orchestrator calls
       :class:`HttpTeardown.teardown` (a :class:`Teardown` Protocol
       implementation) to terminate the spawned API-server PID via
       ``os.kill(pid, signal.SIGTERM)`` then a bounded-wait +
       ``SIGKILL`` escalation — identical SIGTERM-then-SIGKILL
       behaviour to Story 4.4's :class:`PlaywrightTeardown`.

The substrate library reads ONLY the AC + plan-entry from its
:func:`verify_ac` arguments + ``qa-runbook.yaml``'s
``api_server_command`` / ``masked_selectors`` fields (consumed at
THIS module's runtime binding via the LLM-runtime step file at
``skills/bmad-automation/steps/qa-driver-http.md``, NOT by the
substrate library directly) + the running API product. Driver code
does NOT read TEA test files, dev tests, review findings, or commit
diffs (FR16 invariant; structurally encoded by the substrate
library's argument lists excluding TEA-related shapes).

The driver substrate references ONLY
:mod:`loud_fail_harness.specialist_dispatch` (registry + marker
validation) + :mod:`loud_fail_harness.env_provisioning`
(:class:`Provisioner` Protocol + :class:`ProvisionedEnv` shape +
:class:`Teardown` Protocol + :data:`EnvKind` +
:func:`surface_env_setup_failure` for AS-IS reuse) +
:mod:`loud_fail_harness.playwright_driver` (:class:`AcResult` +
:class:`MaskedSelectorPolicy` + :data:`MASKED_REDACTION_SENTINEL` +
:class:`EvidenceCapturer` + :class:`NoOpEvidenceCapturer` for AS-IS
cross-driver reuse — :mod:`playwright_driver` is the canonical
declaration site for these project-type-agnostic primitives because
Story 4.4 landed first in build order; a future refactor MAY
relocate them to a shared module, but THIS story does NOT perform
that refactor) + :mod:`loud_fail_harness.qa_behavioral_plan`
(:class:`QABehavioralPlanEntry` model — :func:`verify_ac` consumes
the plan entry's ``assertion_shape`` + ``expected_evidence_tier``)
+ Pydantic v2 + Python stdlib (``http.client``, ``subprocess``,
``os``, ``signal``, ``time``, ``datetime``). NO references to Dev
or Review-BMAD specialist code (FR62 pluggability invariant).

Re-export pattern: the cross-module reuse of :class:`AcResult`,
:class:`MaskedSelectorPolicy`, :data:`MASKED_REDACTION_SENTINEL`,
:class:`EvidenceCapturer`, :class:`NoOpEvidenceCapturer` is via
direct import at module-import time so downstream consumers reading
``from loud_fail_harness.http_driver import AcResult`` resolve
symbolically. These re-exports are NOT in :data:`__all__` to avoid
double-publishing the symbols.

Cross-story precedent for AS-IS reuse: Story 4.4's
:mod:`playwright_driver` imports :class:`MarkerEmissionRecord` from
Story 4.3's :mod:`env_provisioning` AS-IS for the cross-module
emission-record-shape invariant. THIS module extends the precedent
to :class:`AcResult` + :class:`MaskedSelectorPolicy` +
:class:`EvidenceCapturer` + :class:`NoOpEvidenceCapturer` because
the envelope shape and redaction primitives are project-type-
agnostic.

Forward consumers:

    * Story 4.6 — plan-driven AC iteration framework consumes
      :func:`verify_ac` at iteration time across both web and api
      drivers (the smoke-first ordering routes ACs through the
      per-AC primitive THIS story ships for ``api`` project types).
    * Story 4.7 — AC-assertion-evidence triple structural enforcement
      lifts the schema-level invariant; THIS story produces
      :class:`AcResult` records that conform to the existing
      ``$defs/ac_result`` shape byte-for-byte.
    * Story 4.8 — three-tier evidence hierarchy thickens the
      ``expected_evidence_tier`` semantics; THIS story emits Tier-1
      mechanical evidence only.
    * Story 4.9 — three exploratory heuristics thickens the per-AC
      verification with the ``verification_mode`` field; THIS
      story's :func:`verify_ac` produces the mechanical baseline.
    * Story 4.10 — env-setup-fail / verification-fail escalation
      routing consumes the :class:`EnvSetupFailureEmission` (the
      mid-run service-broken path AS-IS via
      :func:`surface_env_setup_failure`) AND the wrapper-side
      ``status: fail`` envelope.
    * Story 4.11 — plan-persistence-compromise blockquote prepended
      at PR-bundle render time. Story 4.13 thickens consumer semantics
      for structured per-AC emissions.
    * Story 4.12 — evidence-persistence size budgets are enforced
      by
      :func:`loud_fail_harness.qa_evidence_persistence.evaluate_size_budget`;
      THIS story's :data:`_TRACE_BODY_EXCERPT_MAX_CHARS` constant
      bounds the per-trace-record body excerpt size (distinct from
      the file-level size budget Story 4.12 owns at
      :func:`evaluate_size_budget`).
    * Story 4.13 — QA wrapper completion thickens ``agents/qa.md``
      to compose THIS module's step file at AC-iteration time for
      ``api`` project types.
"""

from __future__ import annotations

import os
import re
import signal
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from loud_fail_harness.env_provisioning import (
    EnvKind,
    ProvisionedEnv,
)
from loud_fail_harness.playwright_driver import (
    AcResult,
    EvidenceCapturer,
    MASKED_REDACTION_SENTINEL,
    MaskedSelectorPolicy,
    NoOpEvidenceCapturer as NoOpEvidenceCapturer,
    _apply_masked_selector_policy,
)
from loud_fail_harness.qa_evidence_tier import EvidenceRef
from loud_fail_harness.qa_behavioral_plan import QABehavioralPlanEntry

# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #

#: The epic-AC ``failure_step`` value mirroring the
#: ``env-setup-failed.sub_classifications`` enum member at
#: ``schemas/marker-taxonomy.yaml`` line 112 byte-for-byte.
#: Story 4.3's :func:`provision_env` reads this attribute via
#: ``getattr(exc, "failure_step", "dev-server-not-ready")`` and
#: routes through :func:`surface_env_setup_failure` with the value
#: as ``sub_cause``. Mirrors Story 4.4's
#: :data:`_PLAYWRIGHT_LAUNCH_FAILED_STEP` symbolic-constant
#: discipline; published as a public constant here because the
#: same string is consumed by BOTH the at-init
#: :exc:`ApiServerNotReady` AND the mid-run :exc:`ApiServiceBroken`
#: paths (per the remediation-shape principle in
#: ``docs/extension-audit.md`` § Marker class boundaries — both
#: routes share the same remediation surface "the underlying
#: server process is not responding").
API_SERVER_NOT_READY_STEP: Literal["dev-server-not-ready"] = (
    "dev-server-not-ready"
)

#: Bounded-wait interval (seconds) between SIGTERM and SIGKILL in
#: :class:`HttpTeardown.teardown`. Mirrored from Story 4.4's
#: :data:`_TEARDOWN_GRACE_INTERVAL_SECONDS` for cross-driver
#: consistency (5 seconds is the typical balance between graceful-
#: shutdown opportunity and orphan-prevention).
_TEARDOWN_GRACE_INTERVAL_SECONDS: float = 5.0

#: Polling interval (seconds) used by :class:`HttpTeardown` to check
#: whether the SIGTERM'd process has exited within the bounded wait.
_TEARDOWN_POLL_INTERVAL_SECONDS: float = 0.1

#: Maximum number of characters retained in a
#: :class:`NetworkTraceRecord`'s body-excerpt fields. Bodies longer
#: than this are truncated with the ``[...]`` suffix sentinel — this
#: is the trace-record-level excerpt bound, distinct from Story
#: 4.12's evidence-file-level size budgets.
_TRACE_BODY_EXCERPT_MAX_CHARS: int = 4096

#: Default request timeout (seconds) for :meth:`HttpClient.request`
#: per AC-1's signature default.
_DEFAULT_REQUEST_TIMEOUT_SECONDS: float = 5.0


# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class HttpResponse(BaseModel):
    """One HTTP-response record returned by :meth:`HttpClient.request`
    and consumed by the assertion methods.

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Bodies are normalized to text — the production
    :class:`HttpClient` impl decodes byte-string bodies as UTF-8
    with ``errors="replace"``. Binary bodies are out-of-scope at
    THIS story; Story 4.12 thickens evidence-size + binary-body
    handling.

    Field semantics:
        * ``status`` — the integer HTTP response status code
          (``200``, ``404``, ``500``, ...).
        * ``headers`` — tuple of ``(name, value)`` pairs preserving
          server order. Values are kept as-received; redaction of
          sensitive header values is applied at the
          :class:`EvidenceCapturer` layer per the
          :class:`MaskedSelectorPolicy`, NOT on this model.
        * ``body`` — the response body as text (UTF-8 decoded with
          ``errors="replace"`` for byte-string bodies).
    """

    model_config = ConfigDict(frozen=True)

    status: int
    headers: tuple[tuple[str, str], ...]
    body: str


class ApiAssertion(BaseModel):
    """One assertion-record returned by :meth:`ApiDriver.assert_status`,
    :meth:`ApiDriver.assert_body`, or :meth:`ApiDriver.assert_header`.

    Frozen + ``extra="forbid"`` per AC-1's contract-shape discipline.
    Field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.

    Field semantics:
        * ``passed`` — bool; ``True`` iff the assertion held.
        * ``observed`` — the actual textual content the driver
          observed. Stringified by the substrate (e.g., integer
          status codes are projected to ``str(...)``) so the model
          shape is uniform across the three assertion kinds.
        * ``expected`` — the textual content the assertion required.
          Stringified analogously.
        * ``kind`` — one of ``status | body | header``; identifies
          which of the three :class:`ApiDriver` assertion methods
          produced the record.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    observed: str
    expected: str
    kind: Literal["status", "body", "header"]


class NetworkTraceRecord(BaseModel):
    """One network-trace record captured during AC verification —
    the api-side analogue of Story 4.4's :class:`NetworkRequest` model.

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Bodies are recorded as bounded-length excerpts (per
    :data:`_TRACE_BODY_EXCERPT_MAX_CHARS`) to avoid runaway evidence
    size; longer bodies are truncated with the ``[...]`` suffix
    sentinel. Story 4.12 owns the evidence-file-level size budgets;
    THIS field's bound is the per-trace-record-level excerpt.

    Field semantics:
        * ``method`` — the HTTP method (``GET``, ``POST``, ...).
        * ``url`` — the request URL.
        * ``request_headers`` — tuple of ``(name, value)`` request
          header pairs.
        * ``response_status`` — the integer response status code.
        * ``response_headers`` — tuple of ``(name, value)`` response
          header pairs.
        * ``request_body_excerpt`` — bounded-length excerpt of the
          request body (UTF-8 decoded; truncated with ``[...]`` if
          longer than :data:`_TRACE_BODY_EXCERPT_MAX_CHARS`).
        * ``response_body_excerpt`` — bounded-length excerpt of the
          response body (UTF-8 decoded; truncated with ``[...]`` if
          longer than :data:`_TRACE_BODY_EXCERPT_MAX_CHARS`).
    """

    model_config = ConfigDict(frozen=True)

    method: str
    url: str
    request_headers: tuple[tuple[str, str], ...]
    response_status: int
    response_headers: tuple[tuple[str, str], ...]
    request_body_excerpt: str
    response_body_excerpt: str


# --------------------------------------------------------------------------- #
# Protocols (project-type-specific availability probe / api-server runner /  #
# http client / api driver)                                                   #
# --------------------------------------------------------------------------- #


@runtime_checkable
class ApiAvailabilityProbe(Protocol):
    """Project-type-specific API service availability probe.

    Production binds to a single stdlib HTTP GET against
    ``http://localhost:{port}/`` with a 2-second timeout per the
    ``skills/bmad-automation/steps/qa-driver-http.md`` step file (on
    connection-refused / timeout / non-HTTP response return
    ``False``); tests use :class:`NoOpApiAvailabilityProbe`.
    """

    def is_available(self) -> bool:
        """Return ``True`` iff the API service answers a smoke probe;
        ``False`` otherwise (including any connection-refused,
        timeout, or non-HTTP-response condition).
        """


@runtime_checkable
class ApiServerRunner(Protocol):
    """Project-type-specific API-server runner.

    Production binds to a :func:`subprocess.Popen` of the api-server
    command read from ``_bmad/automation/qa-runbook.yaml``'s
    ``api_server_command`` field at the LLM-runtime layer per the
    ``skills/bmad-automation/steps/qa-driver-http.md`` step file;
    tests use :class:`NoOpApiServerRunner`.
    """

    def start(self, port: int) -> int:
        """Spawn the API server bound to ``port``; return the spawned
        process's PID.
        """


@runtime_checkable
class HttpClient(Protocol):
    """Low-level HTTP client primitive.

    Production binds to a Python-stdlib
    ``http.client.HTTPConnection``-based implementation per the step
    file at ``skills/bmad-automation/steps/qa-driver-http.md``;
    tests use :class:`NoOpHttpClient`.
    """

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | str | None = None,
        timeout: float = _DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> HttpResponse:
        """Issue an HTTP request and return the :class:`HttpResponse`."""


@runtime_checkable
class ApiDriver(Protocol):
    """The five driver-action abstraction the QA wrapper composes
    against the running API product per the verbatim epic AC at
    epics.md line 1938.

    Production implementations bind each method to the corresponding
    Python-stdlib ``http.client`` surface at the LLM-runtime layer
    per the step file at
    ``skills/bmad-automation/steps/qa-driver-http.md``; tests use
    :class:`NoOpApiDriver`.

    Method ↔ stdlib mapping (recorded byte-for-byte in the module
    docstring above and the step file's
    ``## Procedure — ApiDriver Protocol ↔ stdlib mappings`` section):

        * :meth:`request` ↔ ``http.client.HTTPConnection.request`` +
          ``getresponse`` + body read
        * :meth:`assert_status` ↔ in-Python comparison against
          :attr:`HttpResponse.status`
        * :meth:`assert_body` ↔ in-Python equality / substring /
          structural-Mapping match against :attr:`HttpResponse.body`
        * :meth:`assert_header` ↔ in-Python case-insensitive lookup
          against :attr:`HttpResponse.headers`
        * :meth:`inspect_network_trace` ↔ reads the per-driver-
          instance trace buffer the :meth:`request` method appends to

    The production implementation MUST raise :exc:`ApiServiceBroken`
    on connection-refused / timeout / 5xx-unrelated-to-AC-content
    conditions encountered during :meth:`request`; the QA wrapper
    catches the exception and routes through Story 4.3's
    :func:`surface_env_setup_failure` AS-IS.
    """

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | str | None = None,
        timeout: float = _DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> HttpResponse:
        """Issue an HTTP request and return the :class:`HttpResponse`.

        Raises :exc:`ApiServiceBroken` on service-broken conditions;
        the QA wrapper catches and routes through
        :func:`surface_env_setup_failure` AS-IS.
        """

    def assert_status(
        self, response: HttpResponse, expected: int
    ) -> ApiAssertion:
        """Compare ``response.status`` against ``expected`` (integer
        equality); return the :class:`ApiAssertion` record with
        ``kind="status"``.
        """

    def assert_body(
        self,
        response: HttpResponse,
        expected: str | Mapping[str, Any],
    ) -> ApiAssertion:
        """Compare ``response.body`` against ``expected``.

        The matching algorithm:
            * If ``expected`` is a string: equality-or-substring match
              (substring fallback when full equality fails).
            * If ``expected`` is a Mapping: parse the response body
              as JSON and check that every ``(key, value)`` pair in
              ``expected`` is present in the parsed body (structural
              subset match).

        Returns an :class:`ApiAssertion` with ``kind="body"``.
        """

    def assert_header(
        self,
        response: HttpResponse,
        name: str,
        expected: str,
    ) -> ApiAssertion:
        """Look up the header ``name`` (case-insensitive) in
        ``response.headers`` and compare against ``expected``;
        return the :class:`ApiAssertion` record with ``kind="header"``.
        """

    def inspect_network_trace(self) -> tuple[NetworkTraceRecord, ...]:
        """Return the tuple of :class:`NetworkTraceRecord` records
        captured since this driver instance was constructed.
        """


# --------------------------------------------------------------------------- #
# Exceptions                                                                  #
# --------------------------------------------------------------------------- #


class ApiServerNotReady(Exception):
    """Raised by :class:`HttpProvisioner.provision` when the injected
    :class:`ApiAvailabilityProbe` returns ``False`` AT init-time-of-
    provisioning (i.e., AFTER the api-server runner spawned the
    process but the smoke probe could not reach the service).

    Pattern 5 named-invariant diagnostic. The ``failure_step``
    attribute mirrors the
    ``env-setup-failed.sub_classifications`` enum member at
    ``schemas/marker-taxonomy.yaml`` line 112 byte-for-byte; Story
    4.3's :func:`provision_env` reads the attribute via
    ``getattr(exc, "failure_step", "dev-server-not-ready")`` and
    routes through
    :func:`loud_fail_harness.env_provisioning.surface_env_setup_failure`
    with ``sub_cause="dev-server-not-ready"``.

    Distinct from :exc:`ApiServiceBroken` which surfaces MID-RUN
    service-broken conditions AFTER provisioning succeeded;
    :exc:`ApiServerNotReady` is the AT-INIT-time variant. Both
    re-use the same ``"dev-server-not-ready"`` sub_classification
    per the remediation-shape principle (both routes share the
    remediation surface "the underlying server process is not
    responding"; the asymmetry vs Story 4.4 — which DID introduce a
    distinct ``playwright-mcp-unavailable`` mid-run marker class —
    is recorded in ``docs/extension-audit.md``).
    """

    failure_step: Literal["dev-server-not-ready"] = (
        API_SERVER_NOT_READY_STEP
    )


class ApiServiceBroken(Exception):
    """Raised by the production :class:`ApiDriver` (and surfaced by
    the QA wrapper's catch site) on a mid-run API-service-broken
    condition (connection-refused, timeout, 5xx-unrelated-to-AC-
    content).

    Pattern 5 named-invariant diagnostic. Carries the routing-shape
    signal so the LLM-runtime step file's mid-run handler reads
    ``getattr(exc, "failure_step", "dev-server-not-ready")`` AND
    ``getattr(exc, "failure_diagnostic", str(exc))`` and forwards
    both to Story 4.3's :func:`surface_env_setup_failure` AS-IS — no
    new emission helper because the marker class re-used is the
    existing ``env-setup-failed`` from Story 1.4 / Story 4.3, NOT a
    new class.

    Distinct from :exc:`ApiServerNotReady` which fires AT-INIT-time-
    of-provisioning; this exception fires MID-RUN AFTER provisioning
    succeeded but before AC verification completed.

    Attributes:
        failure_step: Class-level literal
            ``"dev-server-not-ready"`` mirroring the marker-taxonomy
            enum member byte-for-byte.
        failure_diagnostic: Instance-level free-form diagnostic
            string carrying the originating exception's
            ``str(...)`` rendering.
    """

    failure_step: Literal["dev-server-not-ready"] = (
        API_SERVER_NOT_READY_STEP
    )

    def __init__(self, failure_diagnostic: str) -> None:
        self.failure_diagnostic: str = failure_diagnostic
        super().__init__(f"api service broken: {failure_diagnostic}")


# --------------------------------------------------------------------------- #
# Reference NoOp impls (test-suite ONLY)                                      #
# --------------------------------------------------------------------------- #


class NoOpApiAvailabilityProbe:
    """Reference :class:`ApiAvailabilityProbe` implementation for the
    test suite ONLY.

    Returns the constructor-supplied ``available`` boolean from every
    :meth:`is_available` call; records the call count for tests
    asserting probe ordering vs runner.

    NOT for production use — the LLM-runtime protocol at
    ``skills/bmad-automation/steps/qa-driver-http.md`` ships the
    real stdlib HTTP-GET smoke-probe binding.
    """

    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        self.call_count: int = 0

    def is_available(self) -> bool:
        self.call_count += 1
        return self._available


class NoOpApiServerRunner:
    """Reference :class:`ApiServerRunner` implementation for the test
    suite ONLY.

    Returns a deterministic dummy PID from every :meth:`start` call.
    Records the latest ``port`` argument and the call count so tests
    can assert the runner was invoked with the expected ephemeral
    port AND that the runner-then-probe ordering is honored.

    NOT for production use — the LLM-runtime protocol at
    ``skills/bmad-automation/steps/qa-driver-http.md`` ships the
    real ``subprocess.Popen``-of-api-server binding.
    """

    def __init__(self, *, pid: int = 12345) -> None:
        self._pid = pid
        self.last_port: int | None = None
        self.call_count: int = 0

    def start(self, port: int) -> int:
        self.last_port = port
        self.call_count += 1
        return self._pid


class NoOpHttpClient:
    """Reference :class:`HttpClient` implementation for the test suite
    ONLY.

    Returns a deterministic dummy :class:`HttpResponse` from every
    :meth:`request` call. Records the latest ``(method, url)``
    argument tuple so tests can assert the client was invoked with
    expected arguments.

    NOT for production use — the LLM-runtime protocol at
    ``skills/bmad-automation/steps/qa-driver-http.md`` ships the
    real ``http.client.HTTPConnection`` binding.
    """

    def __init__(self, *, response: HttpResponse | None = None) -> None:
        self._response = response or HttpResponse(
            status=200,
            headers=(("Content-Type", "text/plain"),),
            body="ok",
        )
        self.calls: list[tuple[str, str]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | str | None = None,
        timeout: float = _DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> HttpResponse:
        del headers, body, timeout
        self.calls.append((method, url))
        return self._response


class NoOpApiDriver:
    """Reference :class:`ApiDriver` implementation for the test suite
    ONLY.

    Records every action's arguments for assertion. Returns the
    constructor-supplied :class:`ApiAssertion` record from each
    assertion method (or raises the constructor-supplied exception
    if one was supplied) so tests can drive both the pass and fail
    paths AND the mid-run :exc:`ApiServiceBroken` re-raise path.

    NOT for production use — the LLM-runtime protocol at
    ``skills/bmad-automation/steps/qa-driver-http.md`` ships the
    real stdlib bindings.
    """

    def __init__(
        self,
        *,
        response: HttpResponse | None = None,
        assertion: ApiAssertion | None = None,
        action_exception: BaseException | None = None,
        traces: tuple[NetworkTraceRecord, ...] | None = None,
    ) -> None:
        self._response = response or HttpResponse(
            status=200,
            headers=(("Content-Type", "text/plain"),),
            body="ok",
        )
        self._assertion = assertion or ApiAssertion(
            passed=True,
            observed="200",
            expected="200",
            kind="status",
        )
        self._action_exception = action_exception
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self._traces: list[NetworkTraceRecord] = list(traces or ())

    def _record(self, action_kind: str, *args: str) -> None:
        if self._action_exception is not None:
            raise self._action_exception
        self.calls.append((action_kind, args))

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | str | None = None,
        timeout: float = _DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> HttpResponse:
        del headers, body, timeout
        self._record("request", method, url)
        # Build a deterministic trace record for inspection; harmless
        # for tests that don't assert on the trace shape.
        request_body_excerpt = ""
        response_body_excerpt = self._response.body[
            :_TRACE_BODY_EXCERPT_MAX_CHARS
        ]
        self._traces.append(
            NetworkTraceRecord(
                method=method,
                url=url,
                request_headers=(),
                response_status=self._response.status,
                response_headers=self._response.headers,
                request_body_excerpt=request_body_excerpt,
                response_body_excerpt=response_body_excerpt,
            )
        )
        return self._response

    def assert_status(
        self, response: HttpResponse, expected: int
    ) -> ApiAssertion:
        del response
        self._record("assert_status", str(expected))
        return self._assertion

    def assert_body(
        self,
        response: HttpResponse,
        expected: str | Mapping[str, Any],
    ) -> ApiAssertion:
        del response
        self._record("assert_body", repr(expected))
        return self._assertion

    def assert_header(
        self,
        response: HttpResponse,
        name: str,
        expected: str,
    ) -> ApiAssertion:
        del response
        self._record("assert_header", name, expected)
        return self._assertion

    def inspect_network_trace(self) -> tuple[NetworkTraceRecord, ...]:
        return tuple(self._traces)


# --------------------------------------------------------------------------- #
# HttpProvisioner / HttpTeardown — Provisioner / Teardown impls              #
# --------------------------------------------------------------------------- #


class HttpProvisioner:
    """Project-type-specific (api) :class:`Provisioner` Protocol
    implementation.

    Composes the injected :class:`ApiAvailabilityProbe` and
    :class:`ApiServerRunner` to provision an api env at the
    orchestrator-owned ``review → qa`` seam (Story 4.3's
    :func:`provision_env`).

    Behavior (load-bearing per AC-2):

        1. Call ``self._api_server_runner.start(port)`` to spawn the
           API server; the runner returns the spawned PID. Any
           exception raised by the runner propagates unchanged
           (Story 4.3's :func:`provision_env` catches it and routes
           via the default ``failure_step="dev-server-not-ready"``).
        2. Call ``self._availability_probe.is_available()``. On
           ``False``, perform a best-effort
           ``os.kill(pid, signal.SIGTERM)`` cleanup of the orphan
           PID (swallowing ``ProcessLookupError`` /
           ``PermissionError`` so the orphan-process surface does
           not accumulate), THEN raise :exc:`ApiServerNotReady`
           carrying ``failure_step="dev-server-not-ready"`` so
           Story 4.3's :func:`provision_env` catches it via
           ``getattr(exc, "failure_step", "dev-server-not-ready")``
           and routes through :func:`surface_env_setup_failure`
           with ``sub_cause="dev-server-not-ready"``.
        3. On availability ``True``, construct and return a
           :class:`ProvisionedEnv` carrying ``env_kind=project_type``
           + the input ``port`` + the runner's PID + a non-null
           timezone-aware UTC ``started_at`` timestamp.

    The class structurally satisfies Story 4.3's :class:`Provisioner`
    Protocol — ``isinstance(provisioner, Provisioner)`` returns
    ``True`` because :class:`Provisioner` is ``@runtime_checkable``.

    Order asymmetry vs Story 4.4: :class:`PlaywrightProvisioner`
    probes BEFORE running because Playwright-MCP availability is the
    gating precondition; :class:`HttpProvisioner` probes AFTER
    spawning because the api server itself must be up before the
    smoke probe can succeed. The order asymmetry is recorded here +
    in the module docstring + in ``docs/extension-audit.md``.
    """

    def __init__(
        self,
        availability_probe: ApiAvailabilityProbe,
        api_server_runner: ApiServerRunner,
    ) -> None:
        self._availability_probe = availability_probe
        self._api_server_runner = api_server_runner

    def provision(
        self,
        story_id: str,
        project_type: EnvKind,
        port: int,
    ) -> ProvisionedEnv:
        """Compose the project-type-specific (api) provisioning per
        AC-2.

        Args:
            story_id: BMAD story identifier (signature-symmetric
                with Story 4.3's :class:`Provisioner` Protocol;
                threaded through for downstream visibility).
            project_type: ``web`` or ``api``; passed through directly
                as the ``env_kind`` field of the returned
                :class:`ProvisionedEnv` per the
                :class:`Provisioner` Protocol signature. Callers
                are responsible for dispatching to the correct
                provisioner — Story 4.4 ships the sibling
                :class:`PlaywrightProvisioner` for ``web`` project
                types.
            port: Integer ephemeral TCP port allocated by Story
                4.3's :func:`allocate_ephemeral_port`.

        Returns:
            :class:`ProvisionedEnv` carrying ``env_kind=project_type``,
            ``port`` matching the input, ``pid`` matching the
            runner's return, ``started_at`` non-null timezone-aware
            UTC datetime.

        Raises:
            :exc:`ApiServerNotReady`: the availability probe
                returned ``False`` after the runner spawned the
                process; the ``failure_step`` attribute is
                ``"dev-server-not-ready"`` byte-for-byte. Best-
                effort SIGTERM cleanup is applied to the orphan PID
                BEFORE the exception is raised.
            Whatever exception the runner raised: propagated
                unchanged so Story 4.3's :func:`provision_env`
                routes via the default
                ``failure_step="dev-server-not-ready"``.
        """
        _ = story_id  # Sensor-not-advisor: signature-symmetric with the protocol.
        pid = self._api_server_runner.start(port)
        if not self._availability_probe.is_available():
            # Best-effort orphan cleanup before raising; swallow
            # PLE/PE so the cleanup is idempotent across repeated
            # provisioning attempts.
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            raise ApiServerNotReady(
                "API service did not respond at provisioning time"
            )
        return ProvisionedEnv(
            env_kind=project_type,
            port=port,
            pid=pid,
            started_at=datetime.now(timezone.utc),
        )


class HttpTeardown:
    """Project-type-specific (api) :class:`Teardown` Protocol
    implementation.

    Implements the SIGTERM → bounded-wait → SIGKILL escalation per
    AC-3 + the cross-OS subprocess-termination convention. Behaviour
    is identical to Story 4.4's :class:`PlaywrightTeardown` at the
    algorithmic level — both widen ``except`` to
    ``(ProcessLookupError, PermissionError)`` per Story 4.4's
    review-fix discipline.

    Behavior:

        1. Call ``os.kill(provisioned_env.pid, signal.SIGTERM)``.
        2. Poll for up to :data:`_TEARDOWN_GRACE_INTERVAL_SECONDS`
           in :data:`_TEARDOWN_POLL_INTERVAL_SECONDS` increments,
           checking process liveness via ``os.kill(pid, 0)``.
        3. On bounded-wait expiry without clean exit, escalate to
           ``os.kill(provisioned_env.pid, signal.SIGKILL)``.
        4. On any :exc:`ProcessLookupError` / :exc:`PermissionError`
           along the way, swallow the exception (idempotent
           teardown — the process is already gone or not
           accessible, the structural goal is satisfied).

    The class structurally satisfies Story 4.3's :class:`Teardown`
    Protocol.
    """

    def teardown(self, provisioned_env: ProvisionedEnv) -> None:
        """Terminate the api-server process per the SIGTERM →
        bounded-wait → SIGKILL escalation per AC-3.
        """
        pid = provisioned_env.pid
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return  # Idempotent: process already gone or not accessible.

        deadline = time.monotonic() + _TEARDOWN_GRACE_INTERVAL_SECONDS
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
            return


# --------------------------------------------------------------------------- #
# verify_ac — per-AC verification primitive (api project type)                #
# --------------------------------------------------------------------------- #


def verify_ac(
    ac_id: str,
    ac_text: str,
    plan_entry: QABehavioralPlanEntry,
    driver: ApiDriver,
    evidence_capturer: EvidenceCapturer,
    masked_selectors: MaskedSelectorPolicy,
) -> AcResult:
    """Compose the per-AC verification primitive for ``api`` project
    types.

    Behavior (load-bearing per AC-4):

        * Dispatch the appropriate :class:`ApiDriver` action sequence
          per the plan entry's ``assertion_shape`` (declarative
          pattern; the MVP placeholder dispatch at THIS story's
          scope routes every plan entry through a
          :meth:`ApiDriver.request` call followed by a
          :meth:`ApiDriver.assert_status` check against status code
          200 — Story 4.6 thickens the dispatcher to a richer
          ``assertion_shape``-driven router; Story 4.7 enforces the
          AC-assertion-evidence triple at the schema level).
        * Capture mechanical Tier-1 evidence via
          ``evidence_capturer.capture("network-trace", payload)``
          where ``payload`` carries the request/response trace
          excerpt rendered from
          :meth:`ApiDriver.inspect_network_trace`. At THIS story's
          scope only Tier-1 mechanical evidence is captured;
          Tier-2 outcome and Tier-3 semantic are Story 4.8's
          surface.
        * Construct and return the :class:`AcResult` per the
          ``$defs/ac_result`` envelope shape:
            - ``status="pass"`` iff the dispatched assertion held
              AND ≥ 1 evidence_ref was captured.
            - ``status="fail"`` if the assertion did NOT hold.
            - ``status="blocked"`` if the dispatched action raised a
              non-:exc:`ApiServiceBroken`, non-Pydantic exception
              (mid-run service-broken is the QA wrapper's
              responsibility to catch and route through
              :func:`surface_env_setup_failure` AS-IS; THIS
              function does NOT catch :exc:`ApiServiceBroken`).

    The function MUST re-raise :exc:`ApiServiceBroken` UNCHANGED —
    the QA wrapper catches them and routes through
    :func:`surface_env_setup_failure` AS-IS; :func:`verify_ac` does
    NOT swallow service-broken exceptions because that path is
    structurally distinct from AC-fail (the verbatim epic AC at
    epics.md line 1947 commits to "separate code paths, separate
    envelopes").

    The function does NOT itself emit markers, write to
    ``run-state.yaml``, or read TEA artifacts (FR16 invariant;
    structurally encoded by the function's argument list excluding
    TEA-related shapes).

    Args:
        ac_id: The AC identifier (e.g., ``"AC-1"``); written
            verbatim to the returned :class:`AcResult.ac_id`.
        ac_text: The AC's verbatim text from the dispatch payload's
            ``ac_list``; carried into the assertion-string
            rendering.
        plan_entry: The
            :class:`loud_fail_harness.qa_behavioral_plan.QABehavioralPlanEntry`
            for THIS AC; carries the ``assertion_shape`` +
            ``expected_evidence_tier`` (consumed by Story 4.6 / 4.8
            for richer dispatch; THIS story's MVP dispatcher reads
            the ``assertion_shape`` for the human-readable assertion
            string only).
        driver: The :class:`ApiDriver` Protocol implementation;
            production binds to the stdlib ``http.client`` surface
            per the step file at
            ``skills/bmad-automation/steps/qa-driver-http.md``;
            tests use :class:`NoOpApiDriver`.
        evidence_capturer: The :class:`EvidenceCapturer` Protocol
            implementation (REUSED AS-IS from Story 4.4); production
            writes to disk under
            ``_bmad-output/qa-evidence/{story-id}/{run-id}/``;
            tests use :class:`NoOpEvidenceCapturer`.
        masked_selectors: The :class:`MaskedSelectorPolicy` consumed
            by the :class:`EvidenceCapturer` to redact sensitive
            content. Threaded through so the :func:`verify_ac`
            signature structurally encodes the FR-AC-1942 redaction
            commitment; the api-side wrapper at
            :func:`_apply_api_masked_selector_policy` is applied to
            trace excerpts BEFORE they reach the
            :class:`EvidenceCapturer`.

    Returns:
        :class:`AcResult` whose ``model_dump()`` JSON projection
        mirrors ``schemas/envelope.schema.yaml`` ``$defs/ac_result``
        lines 164-194 byte-for-byte.

    Raises:
        :exc:`ApiServiceBroken`: re-raised UNCHANGED on any mid-run
            service-broken condition surfaced by the
            :class:`ApiDriver`. The QA wrapper catches and routes
            through :func:`surface_env_setup_failure` AS-IS.
    """
    assertion_str = (
        plan_entry.assertion_shape
        if plan_entry.assertion_shape
        else f"verify: {ac_text}"
    )

    # MVP placeholder dispatcher: GET / + assert_status(200). Story
    # 4.6 thickens to a richer assertion_shape-driven router across
    # all four ApiDriver assertion methods.
    method, url, expected_status = "GET", "/", 200

    try:
        response = driver.request(method, url)
        assertion = driver.assert_status(response, expected_status)
    except ApiServiceBroken:
        # Mid-run service-broken is the QA wrapper's responsibility
        # to catch and route through surface_env_setup_failure
        # AS-IS. THIS function does NOT catch it — propagate
        # unchanged.
        raise
    except Exception as exc:
        # Non-service-broken exception during AC verification —
        # verification cannot complete; status="blocked" with the
        # exception's diagnostic captured for downstream visibility
        # (Story 4.13 thickens consumer semantics; Story 4.10's
        # escalation contracts + Story 4.11's compromise blockquote
        # are render-surface only). Guard against the capturer itself
        # raising so the original driver error is preserved in the
        # assertions tuple.
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

    # Build the network-trace evidence payload from the driver's
    # trace buffer. The api-side masked-selector policy is applied
    # BEFORE the evidence_capturer.capture call so sensitive header
    # values / JSON-body fields / query-string parameters are
    # redacted regardless of whether the capturer's own
    # _apply_masked_selector_policy implementation handles api-side
    # patterns.
    traces = driver.inspect_network_trace()
    trace_text = _render_trace_text(traces, assertion)
    redacted_text = _apply_api_masked_selector_policy(
        trace_text, masked_selectors
    )
    evidence_ref = evidence_capturer.capture("network-trace", redacted_text)

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
            f"{assertion.kind}: observed={assertion.observed!r} "
            f"expected={assertion.expected!r} passed={assertion.passed}",
        ),
        evidence_refs=(EvidenceRef(path=evidence_ref, tier="tier-1-mechanical"),),
        semantic_verification="not_applicable",
    )


# --------------------------------------------------------------------------- #
# Internal helpers                                                            #
# --------------------------------------------------------------------------- #


def _render_trace_text(
    traces: tuple[NetworkTraceRecord, ...],
    assertion: ApiAssertion,
) -> str:
    """Render a textual representation of a tuple of network-trace
    records for evidence persistence.

    Conservative dev's-call format: one record per line, plus a
    trailing line carrying the assertion's observed-vs-expected
    detail. Story 4.12 may thicken to a richer rendering.
    """
    if not traces:
        return (
            f"{assertion.kind}: observed={assertion.observed!r} "
            f"expected={assertion.expected!r}"
        )
    lines: list[str] = []
    for trace in traces:
        lines.append(
            f"{trace.method} {trace.url} -> {trace.response_status}"
        )
        if trace.request_headers:
            for name, value in trace.request_headers:
                lines.append(f">  {name}: {value}")
        if trace.request_body_excerpt:
            lines.append(f">  body: {trace.request_body_excerpt}")
        if trace.response_headers:
            for name, value in trace.response_headers:
                lines.append(f"<  {name}: {value}")
        if trace.response_body_excerpt:
            lines.append(f"<  body: {trace.response_body_excerpt}")
    lines.append(
        f"{assertion.kind}: observed={assertion.observed!r} "
        f"expected={assertion.expected!r}"
    )
    return "\n".join(lines)


def _apply_api_masked_selector_policy(
    text: str, policy: MaskedSelectorPolicy
) -> str:
    """Apply the api-side :class:`MaskedSelectorPolicy` redaction to
    ``text``.

    Extends Story 4.4's CSS-selector-style algorithm
    (:func:`_apply_masked_selector_policy` from
    :mod:`loud_fail_harness.playwright_driver`) WITHOUT modifying it
    by:

        1. First, delegate to Story 4.4's helper for the CSS-selector
           branches (``input[type=password]`` etc.).
        2. Then, for each non-CSS plain-text selector, apply api-
           specific redaction:

           * **HTTP header pattern** —
             ``<selector>:[whitespace]<value>`` (case-insensitive on
             the selector-name match): redact ``<value>`` (rest of
             line until newline or end-of-string) with
             :data:`MASKED_REDACTION_SENTINEL`.
           * **JSON body pattern** —
             ``"<selector>"\\s*:\\s*"<value>"``: redact the quoted
             ``<value>`` with :data:`MASKED_REDACTION_SENTINEL`.
           * **Query-string pattern** — ``<selector>=<value>``
             where ``<value>`` is bounded by ``&``, whitespace, or
             end-of-string: redact ``<value>``.

    Empty :attr:`MaskedSelectorPolicy.masked_selectors` returns the
    text verbatim (no redaction).

    The api-side patterns are evaluated regardless of whether the
    selector is a CSS form — the CSS branch's redaction is applied
    first AND the api-side patterns are applied second so a single
    selector covers both DOM-snapshot evidence (from web-driver
    captures via Story 4.4) AND HTTP-trace evidence (from api-driver
    captures via THIS module). This is consistent with Story 4.4's
    design that :class:`MaskedSelectorPolicy` is project-type-
    agnostic.
    """
    if not policy.masked_selectors:
        return text
    redacted = _apply_masked_selector_policy(text, policy)
    for selector in policy.masked_selectors:
        if not selector:
            continue
        # Skip CSS-shape selectors here; Story 4.4's algorithm
        # already handled them above.
        if "input[type=" in selector:
            continue
        redacted = _redact_http_header_value(redacted, selector)
        redacted = _redact_json_body_field(redacted, selector)
        redacted = _redact_query_string_value(redacted, selector)
    return redacted


def _redact_http_header_value(text: str, selector: str) -> str:
    """Redact HTTP-header value for ``<selector>: <value>`` occurrences.

    Case-insensitive on the header-name match. The value is
    everything from the colon-and-whitespace separator up to the
    next newline (or end-of-string). Word-boundary anchored on the
    selector to avoid spurious matches inside larger identifiers.
    Conservative — does not require the selector to appear at the
    start of a line so leading prefix glyphs (e.g., trace-render
    ``>``/``<`` markers) do not block redaction.
    """
    pattern = re.compile(
        r"(?i)(\b"
        + re.escape(selector)
        + r"\b[ \t]*:[ \t]*)([^\r\n]+)"
    )
    return pattern.sub(
        lambda m: f"{m.group(1)}{MASKED_REDACTION_SENTINEL}", text
    )


def _redact_json_body_field(text: str, selector: str) -> str:
    """Redact JSON-body field value for ``"<selector>": "<value>"``
    occurrences.

    The pattern matches double-quoted keys whose name equals
    ``selector`` (case-sensitive — JSON keys are case-sensitive)
    followed by a colon-with-optional-whitespace and a double-quoted
    string value. The value is replaced with
    :data:`MASKED_REDACTION_SENTINEL`. Numeric / null / nested-
    object JSON values are out-of-scope at THIS story's MVP cut
    (dev's-call extension point — Story 4.12 may thicken).
    """
    pattern = re.compile(
        r'("'
        + re.escape(selector)
        + r'"\s*:\s*)"((?:[^"\\]|\\.)*)"'
    )
    return pattern.sub(
        lambda m: f'{m.group(1)}"{MASKED_REDACTION_SENTINEL}"', text
    )


def _redact_query_string_value(text: str, selector: str) -> str:
    """Redact query-string parameter value for
    ``<selector>=<value>`` occurrences.

    The value is bounded by ``&``, whitespace, or end-of-string.
    Conservative — anchors on ``?`` or ``&`` boundary characters to
    avoid false positives on non-query-string text.
    """
    pattern = re.compile(
        r"([?&]"
        + re.escape(selector)
        + r"=)([^&\s]+)"
    )
    return pattern.sub(
        lambda m: f"{m.group(1)}{MASKED_REDACTION_SENTINEL}", text
    )


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


__all__ = [
    "API_SERVER_NOT_READY_STEP",
    "HttpResponse",
    "ApiAssertion",
    "NetworkTraceRecord",
    "ApiServerNotReady",
    "ApiServiceBroken",
    "ApiAvailabilityProbe",
    "ApiServerRunner",
    "HttpClient",
    "ApiDriver",
    "HttpProvisioner",
    "HttpTeardown",
    "NoOpApiAvailabilityProbe",
    "NoOpApiServerRunner",
    "NoOpApiDriver",
    "NoOpHttpClient",
    "verify_ac",
]
