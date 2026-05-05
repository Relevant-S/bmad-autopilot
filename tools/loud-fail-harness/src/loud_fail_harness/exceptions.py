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
