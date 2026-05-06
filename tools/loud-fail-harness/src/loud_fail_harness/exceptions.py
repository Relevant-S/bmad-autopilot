"""Shared exception base classes for the loud-fail harness.

Pattern 5 named-invariant diagnostics (architecture.md) that represent
*contract violations* share a common :class:`ContractViolation` base.
Callers can ``except ContractViolation`` to catch the entire class of
structural-invariant failures without enumerating every specific subclass.

Note: some Pattern-5 exceptions (``RoutingError``, ``RetryDispatchError``,
``RetryBudgetConfigError``, ``ScopeAssertionProbeError``) use ``ValueError``
lineage for stdlib-introspection reasons (documented in their respective
modules) and intentionally do NOT inherit from :class:`ContractViolation`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class ContractViolation(Exception):
    """Base class for Pattern-5 named-invariant contract-violation diagnostics.

    Pattern 5 distinguishes two categories of loud-fail exceptions:

    * **Contract violations** (this class) — the code's structural invariants
      are broken: a required wire-up is absent, a taxonomy entry is missing,
      a scope contract is violated. Inherit from this class.
    * **Input-validation errors** — the caller passed a malformed value.
      These use ``ValueError`` lineage (``RoutingError``,
      ``RetryDispatchError``, ``RetryBudgetConfigError``,
      ``ScopeAssertionProbeError``) for stdlib compatibility.

    Callers that need to handle any contract violation generically use::

        except ContractViolation:
            ...
    """


class MarkerContextMissing(ContractViolation):
    """Raised when a marker emission lacks a required ``pointer_context_fields`` value.

    Story 6.2 (FR31) — every loud-fail marker carries an actionable
    ``- How to enable:`` pointer rendered from its ``diagnostic_pointer``
    template in ``marker-taxonomy.yaml``. When the template carries
    ``{field}`` placeholders, runtime context populates them at emission
    time via ``run_state.marker_contexts``. Pattern 5 (loud-fail / named
    invariants) and NFR-O5 (named-invariant diagnostics) require that a
    missing required context field surface as a contract violation rather
    than silently emitting raw template text.

    Attributes:
        marker_class: The marker class (taxonomy entry name) being emitted.
        missing_field: The first ``pointer_context_fields`` entry that was
            not present in ``run_state.marker_contexts[marker_class]``.
    """

    def __init__(self, *, marker_class: str, missing_field: str) -> None:
        self.marker_class = marker_class
        self.missing_field = missing_field
        super().__init__()

    def __str__(self) -> str:
        return (
            f"Marker {self.marker_class} requires context field "
            f"'{self.missing_field}' but it was not provided in "
            "run_state.marker_contexts"
        )


class MarkerCoverageAuditFailure(ContractViolation):
    """Raised by the marker emission coverage audit (Story 6.3) on any inconsistency.

    Story 6.3 (FR30 + FR33 + Pattern 5) — the audit module
    :mod:`loud_fail_harness.marker_coverage_audit` walks the canonical
    (marker_class × code_surface) coverage matrix declared in
    ``_data/marker_coverage_surfaces.yaml`` and validates that every
    intersection has exactly one verdict, every ``emitted`` row's
    ``code_path`` resolves to a real file:line carrying a marker reference,
    every ``not-applicable`` row carries non-empty rationale, and every
    ``scheduled-by-story`` row carries a ``discharging_story`` matching the
    ``<epic>.<story>`` pattern. Pattern 5 (loud-fail / named invariants) and
    NFR-O5 (named-invariant diagnostics) require that any inconsistency
    surface as a contract violation rather than silently rendering a
    misleading audit artifact.

    The exception aggregates three orthogonal failure modes (any combination
    may be non-empty) so a single audit invocation reports every defect
    rather than failing at the first one — mirrors the
    :class:`loud_fail_harness.fr33_fixture_gate.FR33FixtureGateFailure`
    aggregation discipline.

    Attributes:
        missing_intersections: ``(marker_class, surface_name)`` tuples that
            are absent from the verdicts list (no row covers the
            intersection). Empty tuple means the Cartesian product is
            covered.
        invalid_verdicts: Per-row diagnostic strings (``"<marker> ×
            <surface>: <reason>"``) for verdicts whose shape is malformed
            (``not-applicable`` missing rationale, ``scheduled-by-story``
            missing or malformed ``discharging_story``, ``gap`` verdict in
            production data, etc.).
        unresolved_code_paths: Per-row diagnostic strings for ``emitted``
            verdicts whose ``code_path`` does not point to a file containing
            a marker-class reference.
    """

    def __init__(
        self,
        *,
        missing_intersections: Sequence[tuple[str, str]] = (),
        invalid_verdicts: Sequence[str] = (),
        unresolved_code_paths: Sequence[str] = (),
    ) -> None:
        self.missing_intersections: tuple[tuple[str, str], ...] = tuple(
            missing_intersections
        )
        self.invalid_verdicts: tuple[str, ...] = tuple(invalid_verdicts)
        self.unresolved_code_paths: tuple[str, ...] = tuple(unresolved_code_paths)
        super().__init__()

    def __str__(self) -> str:
        return (
            "MarkerCoverageAuditFailure: "
            f"missing_intersections={self.missing_intersections!r}; "
            f"invalid_verdicts={self.invalid_verdicts!r}; "
            f"unresolved_code_paths={self.unresolved_code_paths!r}"
        )


class OtelPipelineUnreachable(ContractViolation):
    """Raised when the OTel pipeline read fails because the backend is unreachable.

    Story 6.4 (NFR-P5 + NFR-O8 + ADR-006 Combo 3 — A3' + B1 + C3) — the
    cost-telemetry boundary at :func:`loud_fail_harness.cost_telemetry.collect`
    queries the operator-managed OTLP backend via
    :class:`loud_fail_harness.cost_telemetry.OtelPipelineProtocol` to retrieve
    the per-dispatch ``cost-event`` records. When the backend is unreachable
    (collector down, OTLP endpoint refusing connections, read times out), the
    protocol implementation raises this exception. Pattern 5 (loud-fail /
    named invariants) and NFR-O5 (named-invariant diagnostics) require that
    the failure surface as a contract violation rather than silently zeroing
    cost telemetry.

    The exception is caught at the per-dispatch boundary by
    :func:`loud_fail_harness.cost_telemetry.derive_cost_telemetry_unavailable_marker`
    and translated into a ``cost-telemetry-unavailable: otel-pipeline-unreachable``
    marker emission per the marker-taxonomy.yaml v1 sub-classification —
    the marker, not the exception, is the user-visible loud-fail signal.
    The loop continues; cost-telemetry failure is graceful-degrade per AC-2.

    Attributes:
        prompt_id: The orchestrator-internal correlation key for the dispatch
            whose cost-event read failed (per ADR-006 Combo 3 / A3').
        story_id: The story whose run the dispatch belongs to.
        diagnostic: The underlying failure-mode diagnostic (e.g., ``"OTLP
            collector at localhost:4317 refused connection"``); preserved
            verbatim so NFR-O5 named-invariant context survives.
    """

    def __init__(self, *, prompt_id: str, story_id: str, diagnostic: str) -> None:
        self.prompt_id = prompt_id
        self.story_id = story_id
        self.diagnostic = diagnostic
        super().__init__()

    def __str__(self) -> str:
        return (
            "OtelPipelineUnreachable: "
            f"story_id={self.story_id!r}; prompt_id={self.prompt_id!r}; "
            f"diagnostic={self.diagnostic!r}"
        )


class PromptIdCorrelationMissing(ContractViolation):
    """Raised when the OTel pipeline returns events without a matching ``prompt_id``.

    Story 6.4 (NFR-P5 + ADR-006 Combo 3 — A3') — the orchestrator records
    ``(prompt_id, retry_attempt, specialist)`` per dispatch and queries the
    OTel backend filtered by ``prompt_id`` between specialist completions.
    When the backend returns events whose ``prompt.id`` attribute is missing
    or does not match the orchestrator's correlation key for the
    just-completed dispatch, the protocol implementation raises this
    exception. Pattern 5 (loud-fail / named invariants) and NFR-O5
    (named-invariant diagnostics) require that the correlation gap surface
    as a contract violation rather than silently aggregating mismatched
    cost data.

    The exception is caught at the per-dispatch boundary by
    :func:`loud_fail_harness.cost_telemetry.derive_cost_telemetry_unavailable_marker`
    and translated into a ``cost-telemetry-unavailable:
    prompt-id-correlation-missing`` marker emission per the
    marker-taxonomy.yaml v1 sub-classification. The loop continues; the
    bundle's cost-breakdown section renders the marker rather than
    fabricating zeros (AC-2).

    Attributes:
        prompt_id: The orchestrator-internal correlation key the dispatch
            recorded; what the backend was queried by.
        story_id: The story whose run the dispatch belongs to.
        diagnostic: The underlying failure-mode diagnostic (e.g., ``"OTel
            backend returned 3 events; 0 carried prompt.id matching
            'dispatch-uuid-123'"``); preserved verbatim for NFR-O5.
    """

    def __init__(self, *, prompt_id: str, story_id: str, diagnostic: str) -> None:
        self.prompt_id = prompt_id
        self.story_id = story_id
        self.diagnostic = diagnostic
        super().__init__()

    def __str__(self) -> str:
        return (
            "PromptIdCorrelationMissing: "
            f"story_id={self.story_id!r}; prompt_id={self.prompt_id!r}; "
            f"diagnostic={self.diagnostic!r}"
        )


class PerStoryCostCeilingConfigError(ContractViolation, ValueError):
    """Raised on malformed ``per_story_cost_ceiling_usd`` config input.

    Story 6.5 (NFR-P1 + NFR-O8 + Pattern 5) — the in-flight cost-streaming
    substrate at :mod:`loud_fail_harness.cost_streaming` resolves the
    per-story cost ceiling from ``_bmad/automation/config.yaml`` via
    :func:`loud_fail_harness.cost_streaming.resolve_per_story_cost_ceiling_usd`.
    The resolver follows :func:`loud_fail_harness.retry_budget.resolve_retry_budget`'s
    byte-stable input contract: ``None`` / empty mapping / missing key /
    ``None`` value all return the NFR-P1 default (``$5.00``); positive
    int OR positive float returns that value; bool / negative / zero /
    non-numeric raises this exception. Pattern 5 (loud-fail / named
    invariants) and NFR-O5 (named-invariant diagnostics) require that
    the malformed value surface as a contract violation rather than
    silently coercing or zeroing the ceiling.

    The class inherits BOTH :class:`ContractViolation` (so
    ``except ContractViolation`` at the orchestrator boundary catches it
    alongside the other Pattern-5 invariants) AND :class:`ValueError`
    (so generic ``except ValueError`` in higher-level error handlers and
    stdlib introspection stay compatible — same posture
    :class:`loud_fail_harness.retry_budget.RetryBudgetConfigError`
    documents at ``retry_budget.py:120-151``).

    Attributes:
        value: The offending value the resolver received under the
            ``per_story_cost_ceiling_usd`` key (preserved verbatim for
            the diagnostic so an operator pasting the error into a chat
            can identify the bad input without reading source).
        diagnostic: The NFR-O5 named-invariant diagnostic enumerating
            the offending value, the field name, and a remediation hint
            pointing at ``_bmad/automation/config.yaml``.
    """

    def __init__(self, *, value: Any, diagnostic: str) -> None:
        self.value = value
        self.diagnostic = diagnostic
        super().__init__(diagnostic)

    def __str__(self) -> str:
        return (
            "PerStoryCostCeilingConfigError: "
            f"value={self.value!r}; diagnostic={self.diagnostic!r}"
        )



class EvidenceLinkabilityInvariantError(ContractViolation, ValueError):
    """Raised when a ``DanglingEvidenceRef`` is constructed with a source-vs-fields combination that violates the canonical invariant.

    Story 6.6 (NFR-O7 + NFR-O5 + Pattern 5) — the bundle-render-time
    evidence-trace linkability validator at
    :mod:`loud_fail_harness.evidence_linkability` constructs frozen
    :class:`DanglingEvidenceRef` instances per dangling reference. The
    dataclass enforces a source-vs-fields invariant in ``__post_init__``:

    * ``source == "qa-evidence"`` REQUIRES ``ac_id`` non-``None`` AND
      ``round_id`` is ``None`` AND ``retry_attempt`` is ``None`` (the
      QA envelope's per-AC ``ac_results.evidence_refs`` shape — Story
      4.7 / 4.8 contract).
    * ``source == "retry-history"`` REQUIRES ``round_id`` non-``None``
      AND ``retry_attempt`` non-``None`` AND ``ac_id`` is ``None`` (the
      Story 5.5 ``RetryAttemptRef`` shape — round-scoped, AC-agnostic).

    Violations of either branch raise this exception with an NFR-O5
    named-invariant diagnostic (the violated invariant is named
    ``source-vs-fields-mismatch``) per Pattern 5's
    contract-violation-as-loud-fail doctrine. The same dual-inheritance
    posture as :class:`PerStoryCostCeilingConfigError` (Story 6.5) and
    :class:`loud_fail_harness.retry_budget.RetryBudgetConfigError` is
    preserved so generic ``except ContractViolation`` AND ``except
    ValueError`` handlers both catch it.

    Attributes:
        diagnostic: The NFR-O5 named-invariant diagnostic enumerating
            the offending field combination and naming the violated
            invariant (``source-vs-fields-mismatch``) so an operator
            reading the diagnostic can identify which branch failed
            without reading source.
    """

    def __init__(self, *, diagnostic: str) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic)

    def __str__(self) -> str:
        return (
            "EvidenceLinkabilityInvariantError: "
            f"diagnostic={self.diagnostic!r}"
        )
