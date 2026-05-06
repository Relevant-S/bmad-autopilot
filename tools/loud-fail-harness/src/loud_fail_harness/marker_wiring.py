"""Story 6.7 — Orchestrator-side marker wiring for ``specialist-timeout``,
``hook-failed``, and ``context-near-limit`` skip-events.

Substrate library sibling of :mod:`loud_fail_harness.cost_telemetry` /
:mod:`loud_fail_harness.cost_streaming` /
:mod:`loud_fail_harness.evidence_linkability` /
:mod:`loud_fail_harness.event_streaming` / :mod:`loud_fail_harness.run_state`
per architecture.md lines 311-315. NOT a sixth substrate component beyond
ADR-003 Consequence 1's enumerated five (envelope_validator, event_validator,
reconciler, enumeration_check, fixture_coverage); the count remains FIVE.

Architectural anchors:

* **NFR-P2** (PRD) — "Per-specialist invocation timeout default 15
  minutes"; this module persists ``specialist-timeout`` markers when
  Story 2.6's :exc:`SpecialistTimeoutExceeded` raises at the dispatch
  wrapper seam.
* **NFR-P4** (PRD) — "Specialist context-window approach surfaces a
  loud-fail marker"; this module persists ``context-near-limit``
  markers when the dispatch wrapper's caller-supplied
  ``is_context_near_limit`` callable returns ``True``.
* **NFR-R6** (PRD) — "Every hook's exit code is observable with a
  loud-fail marker on non-zero"; this module persists ``hook-failed:
  <hook-name>`` markers when the orchestrator's hook-result handler
  detects a non-zero exit.
* **Pattern 2** (architecture.md line 962) — Sub-classification via
  ``: <cause>`` suffix; this module emits
  ``specialist-timeout: timeout-exceeded`` /
  ``hook-failed: <hook-name>`` / ``context-near-limit: <specialist>``
  per the post-Story-6.7 ``marker-taxonomy.yaml`` extensions.
* **Pattern 4** (architecture.md) — State-update discipline. Recorder
  helpers produce a NEW :class:`RunState` instance (frozen Pydantic
  ``model_copy(update=...)``); the caller composes with
  :func:`loud_fail_harness.run_state.advance_run_state` for atomic
  persistence per the canonical batch-write rule.
* **Pattern 5** (architecture.md) — Loud-fail / named invariants. The
  generic :func:`record_marker_with_context` helper validates the base
  marker class against an optional :class:`MarkerClassRegistry`; an
  unknown class raises :exc:`UnknownMarkerClass` per Pattern 5.

Sensor-not-advisor posture:

    The recorder helpers RECORD and PERSIST a marker into the run-state
    cache. They do NOT decide WHEN to emit. The dispatch wrapper /
    hook-result handler / specialist envelope / orchestrator skill is
    the policy layer that decides WHEN; this substrate just provides
    the canonical recording helpers.

Marker-permanence rule (Story 1.4):

    A second recording attempt for the SAME full marker string (base
    class + sub-classification suffix) is a no-op; the FIRST emission
    wins. The persistent ``run_state.active_markers`` tuple stays in
    emission order; the rendered loud-fail block re-orders for stable
    display via :func:`compute_alphabetical_marker_order` per AC-4.

Public API:

    * :data:`SPECIALIST_TIMEOUT_MARKER` /
      :data:`HOOK_FAILED_MARKER` /
      :data:`CONTEXT_NEAR_LIMIT_MARKER` — base marker-class identifiers.
    * :data:`HOOK_NAMES` / :data:`SPECIALIST_NAMES` — canonical
      enumerations of the suffix values the recorders accept.
    * :data:`HookName` / :data:`SpecialistName` —
      :class:`Literal` typing aliases documenting the canonical
      kebab-case identifiers; the recorder parameter signatures use
      ``str`` to mirror sibling substrate (``cost_telemetry.py`` /
      ``cost_streaming.py``) and accept runtime-sourced strings from
      caught exceptions / envelope fields without ``cast(...)``
      ceremony. Callers needing strict static checks construct the
      Literal at the call site.
    * :data:`SpecialistTimeoutSubCause` — closed enum :class:`Literal`
      remains strictly typed because the substrate fully owns the
      enumerated values.
    * :func:`record_specialist_timeout_marker` — NFR-P2 specialist
      timeout recorder; populates ``marker_contexts["specialist-timeout"]``.
    * :func:`record_hook_failure_marker` — NFR-R6 hook-exit recorder;
      ``marker_contexts`` unchanged (taxonomy
      ``pointer_context_fields: []``).
    * :func:`record_context_near_limit_marker` — NFR-P4 context-budget
      recorder; populates ``marker_contexts["context-near-limit"]``.
    * :func:`record_marker_with_context` — generic helper that
      composes the three named recorders; ALSO consumed by the QA
      wrapper / Playwright driver to discharge D-6.2-1 deferred-work.
    * :func:`compute_alphabetical_marker_order` — pure render-time
      normalization helper consumed by
      :func:`loud_fail_harness.bundle_assembly._render_loud_fail_block`
      per AC-4.

Cross-references:

    * Story 1.4 ``schemas/marker-taxonomy.yaml`` — three v1 entries
      (``specialist-timeout``, ``hook-failed``, ``context-near-limit``)
      consumed; Story 6.7 makes TWO additive entry extensions
      (``hook-failed.sub_classifications`` += hook-names;
      ``context-near-limit`` gains ``pointer_context_fields:
      [specialist]`` + ``sub_classifications: [dev, qa, review-bmad]``
      + interpolated ``diagnostic_pointer``).
    * Story 1.11 marker-class-reuse principle — preserved: ZERO new
      marker classes; per-source sub-classifications differentiate
      runs without proliferating classes.
    * Story 2.2 :func:`loud_fail_harness.run_state.advance_run_state`
      — the canonical atomic-write helper recorders compose with via
      Pattern 4's batch-write rule.
    * Story 2.6 :class:`loud_fail_harness.specialist_dispatch.SpecialistTimeoutExceeded`
      — ``marker_class: ClassVar[Literal["specialist-timeout"]]`` +
      ``sub_cause: ClassVar[Literal["timeout-exceeded"]]`` consumed
      AS-IS; this module IMPORTS the ClassVar names; does NOT modify
      the exception class.
    * Story 2.7 ``hooks/{subagent-stop,stop,session-start}.sh`` — the
      three canonical hook scripts; the orchestrator-side hook-result
      handler sensors their exit codes and invokes
      :func:`record_hook_failure_marker`.
    * Story 6.1 :func:`loud_fail_harness.bundle_assembly._render_loud_fail_block`
      — consumed AS-IS; the alphabetical re-ordering is a one-line
      iteration-seam wrapper added in this story.
    * Story 6.2 :func:`loud_fail_harness.bundle_assembly._interpolate_actionable_pointer`
      — consumed AS-IS; the interpolation path renders the
      ``{specialist}`` / ``{timeout_seconds}`` placeholders against
      the ``marker_contexts`` populated by this module's recorders.
    * Story 6.5 :class:`loud_fail_harness.cost_streaming.CostStreamingResult.marker_classifications_to_append`
      — the ``tuple[tuple[str, Mapping[str, str]], ...]`` payload shape
      this module's design follows in spirit (the recorders produce a
      new ``RunState`` rather than a payload tuple because they
      persist immediately via ``advance_run_state`` rather than
      deferring to a downstream caller).
    * Story 6.6 :func:`loud_fail_harness.evidence_linkability.validate_evidence_linkability_at_render`
      — orthogonal sibling substrate; both stories preserve the
      in-place-flip / additive-substrate discipline.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Literal

from loud_fail_harness.run_state import RunState
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)


__all__ = [
    "CONTEXT_NEAR_LIMIT_MARKER",
    "HOOK_FAILED_MARKER",
    "HOOK_NAMES",
    "HookName",
    "SPECIALIST_NAMES",
    "SPECIALIST_TIMEOUT_MARKER",
    "SpecialistName",
    "SpecialistTimeoutSubCause",
    "compute_alphabetical_marker_order",
    "record_context_near_limit_marker",
    "record_hook_failure_marker",
    "record_marker_with_context",
    "record_specialist_timeout_marker",
]


# --------------------------------------------------------------------------- #
# Constants + typing aliases                                                  #
# --------------------------------------------------------------------------- #


#: The ``specialist-timeout`` marker class identifier sourced verbatim
#: from ``schemas/marker-taxonomy.yaml`` and Story 2.6's
#: :class:`SpecialistTimeoutExceeded.marker_class` ClassVar. Pattern 2
#: kebab-case identifier.
SPECIALIST_TIMEOUT_MARKER: Final[Literal["specialist-timeout"]] = (
    "specialist-timeout"
)

#: The ``hook-failed`` marker class identifier sourced verbatim from
#: ``schemas/marker-taxonomy.yaml``. Pattern 2 kebab-case identifier.
HOOK_FAILED_MARKER: Final[Literal["hook-failed"]] = "hook-failed"

#: The ``context-near-limit`` marker class identifier sourced verbatim
#: from ``schemas/marker-taxonomy.yaml``. Pattern 2 kebab-case
#: identifier.
CONTEXT_NEAR_LIMIT_MARKER: Final[Literal["context-near-limit"]] = (
    "context-near-limit"
)

#: Canonical hook-name suffixes per the post-Story-6.7
#: ``marker-taxonomy.yaml`` ``hook-failed.sub_classifications``
#: extension. Alphabetical ordering matches the rendered loud-fail
#: block's iteration order via
#: :func:`compute_alphabetical_marker_order`.
HookName = Literal["session-start", "stop", "subagent-stop"]

#: Tuple form of :data:`HookName` for runtime enumeration (mypy
#: ``Literal`` types do not expose runtime members; this constant
#: provides parity for tests + introspection).
HOOK_NAMES: Final[tuple[str, ...]] = ("session-start", "stop", "subagent-stop")

#: Canonical specialist-name suffixes per the post-Story-6.7
#: ``marker-taxonomy.yaml`` ``context-near-limit.sub_classifications``
#: extension. Mirrors Story 6.4's per-specialist kebab-case identifier
#: discipline; alphabetical.
SpecialistName = Literal["dev", "qa", "review-bmad"]

#: Tuple form of :data:`SpecialistName` for runtime enumeration.
SPECIALIST_NAMES: Final[tuple[str, ...]] = ("dev", "qa", "review-bmad")

#: Sub-cause suffixes for :data:`SPECIALIST_TIMEOUT_MARKER`. Mirrors
#: Story 2.6's :class:`SpecialistTimeoutExceeded.sub_cause` ClassVar at
#: ``specialist_dispatch.py`` plus the future
#: ``context-budget-exceeded`` reservation noted in that exception's
#: docstring.
SpecialistTimeoutSubCause = Literal["timeout-exceeded", "context-budget-exceeded"]


# --------------------------------------------------------------------------- #
# Internal helpers                                                            #
# --------------------------------------------------------------------------- #


def _format_marker_with_suffix(base: str, sub: str | None) -> str:
    """Compose Pattern 2's ``base: sub`` marker string.

    Returns the bare ``base`` when ``sub`` is ``None`` or empty so
    base-only emissions (e.g., ``cost-near-ceiling`` per Story 6.5)
    remain byte-stable for callers that go through this helper.
    """
    if sub:
        return f"{base}: {sub}"
    return base


def _extend_marker_contexts(
    existing: Mapping[str, Mapping[str, str]],
    base_class: str,
    context: Mapping[str, str] | None,
) -> Mapping[str, Mapping[str, str]]:
    """Set ``marker_contexts[base_class] = context`` if not already present.

    Marker-permanence rule (Story 1.4) parallel to ``active_markers``:
    the FIRST emission's context wins. A second recording attempt for
    the same base class returns the input mapping unchanged so the
    rendered ``How to enable:`` bullet reflects the run's first
    surfacing of the marker class.

    Returns the input mapping unchanged when ``context`` is ``None`` or
    empty (no contribution).
    """
    if not context:
        return existing
    if base_class in existing:
        return existing
    new_contexts: dict[str, Mapping[str, str]] = dict(existing)
    new_contexts[base_class] = dict(context)
    return new_contexts


# --------------------------------------------------------------------------- #
# Recorder helpers                                                            #
# --------------------------------------------------------------------------- #


def record_specialist_timeout_marker(
    *,
    run_state: RunState,
    specialist: SpecialistName,
    timeout_seconds: int,
    sub_cause: SpecialistTimeoutSubCause = "timeout-exceeded",
) -> RunState:
    """Record a ``specialist-timeout: <sub_cause>`` marker into run-state.

    Witnesses AC-1 verbatim — "any ``specialist-timeout`` marker emitted
    during a run flows through to the bundle's loud-fail block (Story
    6.1) And the marker's actionable pointer includes: which specialist
    timed out, the timeout configuration (NFR-P2 default 15 min), how
    to extend the timeout in ``config.yaml``".

    Pure function (no I/O). Returns a NEW :class:`RunState` (frozen
    Pydantic ``model_copy(update=...)``); the caller composes with
    :func:`loud_fail_harness.run_state.advance_run_state` for atomic
    persistence per Pattern 4's batch-write rule.

    Marker-permanence rule (Story 1.4): a second call with the SAME
    ``sub_cause`` for a run-state already carrying the marker returns
    the input run-state unchanged. The de-dup is by full marker-string
    equality; ``timeout-exceeded`` vs ``context-budget-exceeded`` are
    distinct entries.

    Populates ``marker_contexts["specialist-timeout"]`` with
    ``{"specialist": <name>, "timeout_seconds": <int-as-str>}`` per the
    taxonomy's ``pointer_context_fields: [specialist, timeout_seconds]``
    declaration so Story 6.2's ``_interpolate_actionable_pointer``
    renders the run-specific actionable pointer at bundle-render time.
    The FIRST emission's context wins per the marker-permanence rule.

    Args:
        run_state: The pre-emission run-state cache.
        specialist: Kebab-case specialist identifier (one of
            :data:`SPECIALIST_NAMES`).
        timeout_seconds: The wall-clock budget that was exceeded
            (NFR-P2 default 900 seconds = 15 minutes).
        sub_cause: One of :data:`SpecialistTimeoutSubCause`. Defaults
            to ``"timeout-exceeded"`` (Story 2.6's
            :class:`SpecialistTimeoutExceeded.sub_cause` ClassVar);
            ``"context-budget-exceeded"`` is reserved for the Phase 2
            thickening Story 2.6's docstring at
            ``specialist_dispatch.py`` line 944 names.

    Returns:
        A new :class:`RunState` instance with ``active_markers``
        extended (or the input unchanged on de-dup).
    """
    full = _format_marker_with_suffix(SPECIALIST_TIMEOUT_MARKER, sub_cause)
    if full in run_state.active_markers:
        return run_state
    new_active = run_state.active_markers + (full,)
    new_contexts = _extend_marker_contexts(
        run_state.marker_contexts,
        SPECIALIST_TIMEOUT_MARKER,
        {"specialist": str(specialist), "timeout_seconds": str(timeout_seconds)},
    )
    return run_state.model_copy(
        update={"active_markers": new_active, "marker_contexts": new_contexts}
    )


def record_hook_failure_marker(
    *, run_state: RunState, hook_name: HookName
) -> RunState:
    """Record a ``hook-failed: <hook_name>`` marker into run-state.

    Witnesses AC-2 verbatim — "any of the three hooks (SubagentStop,
    Stop, SessionStart) exits non-zero per NFR-R6 When the orchestrator
    detects the hook failure Then a ``hook-failed: {hook-name}`` marker
    is emitted with sub-classification naming which hook And the marker
    flows through to the bundle's loud-fail block".

    Pure function (no I/O). Returns a NEW :class:`RunState`.

    ``marker_contexts`` is UNCHANGED — the taxonomy's
    ``hook-failed.pointer_context_fields: []`` declaration means the
    diagnostic_pointer text renders verbatim with no interpolation.
    The hook-name appears in the rendered ``Sub-classification:``
    bullet (driven by the marker-string suffix) AND distinguishes
    remediation in the diagnostic_pointer text per Story 1.4's existing
    ``hook-failed`` taxonomy entry.

    Marker-permanence rule (Story 1.4): per-hook-name de-dup. THREE
    distinct calls for ``subagent-stop`` + ``stop`` + ``session-start``
    produce three entries (none de-duplicated against each other); a
    second call for the SAME hook returns the input run-state
    unchanged.

    Args:
        run_state: The pre-emission run-state cache.
        hook_name: One of :data:`HOOK_NAMES`.

    Returns:
        A new :class:`RunState` instance with ``active_markers``
        extended (or the input unchanged on de-dup).
    """
    full = _format_marker_with_suffix(HOOK_FAILED_MARKER, hook_name)
    if full in run_state.active_markers:
        return run_state
    new_active = run_state.active_markers + (full,)
    return run_state.model_copy(update={"active_markers": new_active})


def record_context_near_limit_marker(
    *, run_state: RunState, specialist: SpecialistName
) -> RunState:
    """Record a ``context-near-limit: <specialist>`` marker into run-state.

    Witnesses AC-3 verbatim — "any specialist invocation approaches
    Claude Code's context-window limit per NFR-P4 When the orchestrator
    detects the near-limit condition Then a ``context-near-limit:
    {specialist}`` marker is emitted with the specialist identifier as
    sub-classification".

    Pure function (no I/O). Returns a NEW :class:`RunState`.

    Populates ``marker_contexts["context-near-limit"]`` with
    ``{"specialist": <name>}`` per the post-Story-6.7 taxonomy
    extension ``pointer_context_fields: [specialist]``. The FIRST
    specialist's context wins per the marker-permanence rule; the
    sub-classification suffix on each marker entry differentiates the
    rendered H3 headers — see the architecture.md "Orchestrator-side
    marker wiring" section for the documented visibility-vs-precision
    tradeoff (Phase 2 thickening to per-sub-classification context
    keys is tracked in ``_bmad-output/implementation-artifacts/deferred-work.md``).

    Marker-permanence rule (Story 1.4): per-specialist de-dup. THREE
    distinct calls for ``dev`` + ``qa`` + ``review-bmad`` produce
    three entries; a second call for the same specialist returns the
    input run-state unchanged.

    Args:
        run_state: The pre-emission run-state cache.
        specialist: One of :data:`SPECIALIST_NAMES`.

    Returns:
        A new :class:`RunState` instance with ``active_markers``
        extended (or the input unchanged on de-dup).
    """
    full = _format_marker_with_suffix(CONTEXT_NEAR_LIMIT_MARKER, specialist)
    if full in run_state.active_markers:
        return run_state
    new_active = run_state.active_markers + (full,)
    new_contexts = _extend_marker_contexts(
        run_state.marker_contexts,
        CONTEXT_NEAR_LIMIT_MARKER,
        {"specialist": str(specialist)},
    )
    return run_state.model_copy(
        update={"active_markers": new_active, "marker_contexts": new_contexts}
    )


def record_marker_with_context(
    *,
    run_state: RunState,
    marker_class: str,
    sub_classification: str | None = None,
    context: Mapping[str, str] | None = None,
    marker_registry: MarkerClassRegistry | None = None,
) -> RunState:
    """Generic orchestrator-side marker recorder with optional context.

    Witnesses AC-5 verbatim — the canonical generic helper that
    discharges D-6.2-1 deferred-work. Composed by :mod:`qa_evidence_tier`
    (``Tier-3-not-configured`` with ``{ac_id}``) and
    :mod:`playwright_driver` (``playwright-mcp-unavailable`` with
    ``{project_type, version_range}``); also serves as the canonical
    pattern for future orchestrator-side marker emitters.

    Pure function (no I/O). Returns a NEW :class:`RunState`.

    When ``marker_registry`` is supplied, validates ``marker_class``
    against the registry per Pattern 5; an unknown class raises
    :exc:`UnknownMarkerClass` per Story 2.6's
    :func:`validate_marker_emission` contract. ``None`` (default)
    skips validation — appropriate for the three named recorders that
    work with known taxonomy classes.

    Marker-permanence rule (Story 1.4): de-dup by full marker-string
    equality (``marker_class`` + ``: <sub_classification>``).

    Args:
        run_state: The pre-emission run-state cache.
        marker_class: Base marker class identifier (kebab-case per
            Pattern 2).
        sub_classification: Optional Pattern 2 ``: <cause>`` suffix.
        context: Optional ``pointer_context_fields`` mapping per the
            taxonomy entry. The FIRST emission's context wins.
        marker_registry: Optional :class:`MarkerClassRegistry` for
            pre-emission validation per Pattern 5.

    Returns:
        A new :class:`RunState` instance with ``active_markers``
        extended (or the input unchanged on de-dup).

    Raises:
        UnknownMarkerClass: ``marker_registry`` was supplied AND
            ``marker_class`` is not in the registry's enumeration.
    """
    if marker_registry is not None:
        validate_marker_emission(marker_registry, marker_class)
    full = _format_marker_with_suffix(marker_class, sub_classification)
    if full in run_state.active_markers:
        return run_state
    new_active = run_state.active_markers + (full,)
    if context:
        new_contexts = _extend_marker_contexts(
            run_state.marker_contexts, marker_class, context
        )
        return run_state.model_copy(
            update={
                "active_markers": new_active,
                "marker_contexts": new_contexts,
            }
        )
    return run_state.model_copy(update={"active_markers": new_active})


# --------------------------------------------------------------------------- #
# Render-time alphabetical normalization                                      #
# --------------------------------------------------------------------------- #


def compute_alphabetical_marker_order(
    active_markers: tuple[str, ...],
) -> tuple[str, ...]:
    """Sort ``active_markers`` by ``(base_class, sub_classification)``.

    Witnesses AC-4 verbatim — "rendering is order-stable (deterministic
    ordering across runs — alphabetical by marker class then
    sub-classification)".

    Pure function (no I/O). Idempotent + byte-stable: same input always
    yields the same output. Stable sort: ties (same base + same sub —
    not expected per per-recorder de-dup but defensive) preserve
    emission order.

    Render-time normalization helper consumed by
    :func:`loud_fail_harness.bundle_assembly._render_loud_fail_block`.
    The persistent ``run_state.active_markers`` tuple is UNCHANGED —
    on-disk persistence stays in emission order per Story 1.4's
    marker-permanence rule; only the rendered iteration order is
    normalized for stable display.

    Args:
        active_markers: The persistent emission-order tuple sourced
            from :class:`loud_fail_harness.run_state.RunState.active_markers`
            (or a Story 6.6 :func:`_merge_evidence_linkability_markers`
            result for the bundle-render-time merge).

    Returns:
        A new tuple with the same entries sorted alphabetically by
        ``(base_class, sub_classification)``.
    """

    def _sort_key(marker: str) -> tuple[str, str]:
        if ":" in marker:
            base, sub = marker.split(":", 1)
            return (base.strip(), sub.strip())
        return (marker, "")

    return tuple(sorted(active_markers, key=_sort_key))
