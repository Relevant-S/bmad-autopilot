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
