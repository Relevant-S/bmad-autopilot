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
