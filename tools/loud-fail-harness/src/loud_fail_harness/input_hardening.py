"""Shared input-hardening primitives for externally-constructed models — Story 24.2.

Consolidates the four-property hostile-input rejection that was applied
by-memory across Epics 13 → 14 → 15 → 16 → 18 into one shared helper, enforced
across every externally-constructed model by ``input_hardening_gate`` (Rules
A/B). Each primitive raises ``ValueError`` so it composes inside a Pydantic
``@model_validator``/``@field_validator`` and is wrapped into ``ValidationError``
at construction.

The diagnostic-message shape mirrors the original ``epic_run_state._reject_unclean_text``
(``f"{label} must not be …; got {value!r}"``) so migrated call-sites keep their
error wording. ``harden_identifier`` is a strict superset of the original
(adds null-byte rejection); ``harden_path_segment`` additionally rejects path
separators and ``..`` traversal segments, consolidating the inline checks that
lived at ``epic_run_state_path_for``.
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = [
    "harden_identifier",
    "harden_path_segment",
    "reject_duplicate_identifiers",
]


def harden_identifier(value: str, label: str) -> str:
    """Reject whitespace-only, embedded-newline (``\\n``/``\\r``), and null-byte
    identifier inputs; return ``value`` unchanged on success.

    ``Field(min_length=1)`` rejects the empty string but NOT ``"   "`` (passes
    ``min_length``) nor ``"epic-15\\n"`` (an embedded newline that corrupts
    on-disk YAML line-structure / marker-key round-trips) nor ``"\\x00"`` (a
    null byte that truncates paths / poisons filesystem ops). This helper closes
    all three.
    """
    if not value.strip():
        raise ValueError(f"{label} must not be whitespace-only; got {value!r}")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{label} must not contain embedded newlines; got {value!r}")
    if "\x00" in value:
        raise ValueError(f"{label} must not contain a null byte; got {value!r}")
    return value


def harden_path_segment(value: str, label: str) -> str:
    """:func:`harden_identifier` plus path-separator (``/``, ``\\``) and ``..``
    traversal-segment rejection, so a malformed identifier can never compose a
    path outside its intended umbrella. Return ``value`` unchanged on success.
    """
    harden_identifier(value, label)
    if "/" in value or "\\" in value:
        raise ValueError(
            f"{label} must not contain a path separator; got {value!r}"
        )
    if ".." in value:
        raise ValueError(
            f"{label} must not contain a '..' traversal segment; got {value!r}"
        )
    return value


def reject_duplicate_identifiers(values: Iterable[str], label: str) -> None:
    """Raise on the first duplicate in ``values`` (the ``FlowBranch`` collision
    class — two identifiers colliding silently in the marker-key domain)."""
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(
                f"{label} must not contain duplicate identifiers; "
                f"got repeated {value!r}"
            )
        seen.add(value)
