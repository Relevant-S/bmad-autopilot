"""Story 10.5 — Substrate-library SINGLE source-of-truth for ``LAD-skipped``
marker emission on the mid-run LAD-MCP-unavailable surface.

Architectural placement (Story 1.10b + 9.5 + 10.4 substrate-library
precedent)
=========================================================================

This module is a **substrate-library NOT a sixth substrate component**.
ADR-003 Consequence 1 enumerates exactly FIVE substrate components
(envelope_validator, event_validator, reconciler, enumeration_check,
fixture_coverage); this module composes existing substrate
(:class:`loud_fail_harness.specialist_dispatch.MarkerClassRegistry`,
:func:`loud_fail_harness.specialist_dispatch.validate_marker_emission`,
:class:`loud_fail_harness.env_provisioning.MarkerEmissionRecord`) into
a new emission seam — it does NOT introduce a sixth CI gate. The
substrate-component count remains FIVE post-Story-10.5; the
``docs/extension-audit.md`` Story 10.5 row records this classification
explicitly per the AC-11 contract-pair pattern.

What this library provides
==========================

* :data:`LAD_SKIPPED_MARKER` — module-level :class:`typing.Literal`
  constant carrying the ``"LAD-skipped"`` marker-class string. Sourced
  AS-IS from ``schemas/marker-taxonomy.yaml`` line 97 (Phase 1
  taxonomy v1 closed-set member; preserved structurally per
  AC-9 invariant + Story 10.4 AC-10 invariant + Epic 8 retro's
  closed-set discipline).

* :class:`LadMcpUnavailableEmission` — frozen Pydantic ``BaseModel``
  (parallel to :class:`loud_fail_harness.mobile_driver.MobileMcpUnavailableEmission`
  byte-for-byte in shape) carrying the
  :class:`loud_fail_harness.env_provisioning.MarkerEmissionRecord`
  return field that downstream callers persist into the orchestrator's
  ``run_state`` via Story 6.3's marker-coverage substrate.

* :func:`surface_lad_unavailable` — pure substrate function (no file
  I/O, no env access; Pattern 6 dependency-injection) that is the
  SOLE callable site for ``LAD-skipped`` marker emission at runtime.
  Composes :func:`validate_marker_emission` (Story 2.6's substrate)
  for atomic-on-failure registry validation per Pattern 5;
  constructs the marker-emission record with the structured
  ``context`` payload carrying the four required fields
  ``{story_id, sub_cause, diagnostic_pointer, lifecycle_phase}``.

Architectural anchors
=====================

* **FR-P1.5-1** (Phase-1.5 / Review-LAD activation) — LAD lands as
  the opt-in 4th parallel reviewer; default-off; gated by
  ``_bmad/automation/config.yaml#review_lad.enabled``. This module is
  the substrate-library backing the runtime-failure surface of the
  Phase-1.5 LAD review path.
* **FR29** (4-layer adversarial review composition) — LAD failures
  (init-time + mid-run) surface as ``LAD-skipped`` markers per the
  SDN-001 ``opt-in-skip`` profile.
* **FR30** (loud-fail markers) — the substrate enforces structural
  marker emission via :func:`validate_marker_emission`; registry
  rejection raises
  :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`.
* **NFR-S1** (API-key handling contract; PRD verbatim: "API key is
  read from a documented environment variable, never from
  configuration files committed to git, never written to logs, PR
  bundles, evidence bundles, or run-state") — the substrate at this
  module reads only the env-var NAME via Pattern 6 dependency
  injection (the wrapper at LLM-runtime is the ONLY layer with
  access to the env-var VALUE). The structural witness is the
  ``tests/test_api_key_hygiene.py`` byte-level substring scan
  substrate-library test landed by Story 10.5 AC-7.
* **NFR-I3** (silence-unless-configured discipline) — the three
  LAD-disabled paths (init-time ``unconfigured``, mid-run
  ``lad_enabled=False``, omitted ``review_lad`` config block) ALL
  produce zero ``LAD-skipped`` emissions per AC-5. The
  ``_dispatch_opt_in_skip`` substrate's existing ``silent: true``
  branch routes the init-time path; the
  ``four_layer_review_dispatch.dispatch_four_layer_review``
  bit-identity short-circuit at AC-5 routes the mid-run path; the
  consumer-side ``config.get(...).get("enabled", False)`` default
  routes the omitted-block path.
* **Pattern 1** (snake_case fields; identifier values follow
  PRD-canonical literals) — every identifier in this module follows
  Pattern 1's snake_case-Python convention; the marker class string
  literal ``"LAD-skipped"`` is kebab-case-yaml-with-acronym per the
  existing taxonomy v1 entry at line 97.
* **Pattern 5** (loud-fail doctrine) — registry rejection raises
  :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
  BEFORE any partial state is constructed (atomic-on-failure;
  mirrors :func:`loud_fail_harness.mobile_driver.surface_mobile_mcp_unavailable`).
* **Pattern 6** (strict typing + dependency injection) — the
  function signature takes the :class:`MarkerClassRegistry` injected
  by the caller; the substrate does NOT load the registry from disk.
* **ADR-002** (substrate-vs-LLM-runtime split) — this module sits on
  the substrate side; the wrapper-side env-var presence check at
  ``agents/review-lad-wrapper.md`` is the LLM-runtime side.
* **ADR-003** — substrate-component closure at FIVE preserved (this
  module is substrate-library NOT a sixth component).
* **ADR-008** (LAD MCP server selection) — the env-var name
  ``OPENROUTER_API_KEY`` is the canonical name (line 681); the
  init-time + runtime ``diagnostic_pointer`` literals (lines 685 +
  687) are sourced from ``schemas/dependencies.yaml`` via
  :func:`loud_fail_harness.dependencies_validator.load_dependencies`
  per Story 1.6 source-of-truth rule.
* **SDN-001** (architecture.md lines 730-882) — Dependency
  failure-profile schema. The ``lad`` entry at
  ``schemas/dependencies.yaml`` lines 176-195 carries the init +
  runtime ``sub_classifications`` whose ``diagnostic_pointer``
  literals THIS substrate emits via the marker's ``context.diagnostic_pointer``
  field.

FR62 pluggability classification
================================

This module is *substrate-shared library* per Story 1.10b + Story 9.5
+ Story 10.4 precedent. The FR62 pluggability gate at
:mod:`loud_fail_harness.pluggability_gate` scans ``agents/*.md`` only;
the substrate at ``tools/loud-fail-harness/`` is OUTSIDE the gate's
scope by construction. Sibling specialists (Dev, Review-BMAD, QA) are
referenced ONLY by HUMAN-READABLE prose names if at all; this module
emits ``LAD-skipped`` via the canonical registry-validated path and
does NOT import any specialist wrapper. The pluggability invariant is
preserved structurally.

Cross-references
================

* Story 2.6 :mod:`loud_fail_harness.specialist_dispatch` —
  :func:`validate_marker_emission`,
  :class:`MarkerClassRegistry`, named-invariant exceptions.
* Story 3.3 :mod:`loud_fail_harness.review_layer_failure` —
  ``review-layer-failed`` marker is ORTHOGONAL to ``LAD-skipped``;
  both fire when LAD fails mid-run (the substrate-vs-operator
  concerns are orthogonal per Story 10.5 Story prose).
* Story 9.5 :mod:`loud_fail_harness.mobile_driver` —
  :func:`surface_mobile_mcp_unavailable` is the structural
  precedent THIS module's shape mirrors verbatim.
* Story 10.1 ``schemas/dependencies.yaml`` — ``lad`` activated;
  ADR-008 env-var name landed.
* Story 10.2 ``agents/review-lad-wrapper.md`` — the LAD wrapper
  whose ``status: blocked`` envelope shape this module's
  consumer-side substrate
  (:mod:`loud_fail_harness.four_layer_review_dispatch`) translates
  into a ``LAD-skipped`` marker emission.
* Story 10.4 :mod:`loud_fail_harness.four_layer_review_dispatch` —
  the runtime-dispatch substrate whose ``dispatch_four_layer_review``
  function composes THIS module's :func:`surface_lad_unavailable`
  at the mid-run LAD-dispatch-failure catch site per Story 10.5
  AC-4.
* Story 10.6 — pluggability-CI-gate coverage extension to
  Review-LAD code + cost-observability partition extension; will
  consume the ``FourLayerReviewResult.lad_skipped_emissions``
  tuple-field this story adds.
* Story 10.7 — reference LAD-enabled end-to-end run fixture; will
  consume this module's emission surface as the load-bearing
  Phase-1.5 LAD activation evidence.

See also: ``docs/extension-audit.md`` "no-introductions principle"
subsection (Story 3.2 codification) — THIS story is a worked
instance (ZERO new marker classes, ZERO new sub_classifications,
ZERO new substrate components).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from loud_fail_harness.env_provisioning import MarkerEmissionRecord
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

__all__ = [
    "LAD_SKIPPED_MARKER",
    "LadMcpUnavailableEmission",
    "surface_lad_unavailable",
]


# --------------------------------------------------------------------------- #
# Module-level constants                                                      #
# --------------------------------------------------------------------------- #

#: The marker-class string identifier emitted on the mid-run LAD-MCP-
#: unavailable surface AND (via the init-time path) the init-time
#: ``configured-but-api-key-missing`` precondition surface. Consumed
#: AS-IS from ``schemas/marker-taxonomy.yaml`` line 97 — Phase 1
#: taxonomy v1 closed-set member; ``sub_classifications: []`` empty
#: list (taxonomy line 104) is preserved structurally per Story 10.5
#: AC-9 invariant + Story 10.4 AC-10 invariant + Epic 8 retro's
#: ratified-closed-set discipline. Mirrors Story 9.5's
#: :data:`loud_fail_harness.mobile_driver.MOBILE_BLOCKED_MARKER`
#: constant pattern.
LAD_SKIPPED_MARKER: Literal["LAD-skipped"] = "LAD-skipped"


#: Sentinel string constants for the three ``sub_cause`` values that
#: :func:`surface_lad_unavailable` accepts. Kept as module-level
#: ``Literal`` constants for type-narrowing at downstream consumers
#: (Story 6.3 marker-coverage audit + Story 6.4 cost telemetry) and
#: single-point-of-edit hygiene per Pattern 6. NOT enumerated as a
#: marker ``sub_classification`` — the marker-taxonomy v1
#: ``LAD-skipped.sub_classifications: []`` empty list is preserved
#: per AC-9 invariant (the init-vs-runtime distinction is carried in
#: the marker's ``context.sub_cause`` payload, NOT in the marker's
#: ``sub_cause`` field).
_SubCause = Literal[
    "init-api-key-missing",
    "mid-run-api-key-missing",
    "mid-run-mcp-unavailable",
]


# --------------------------------------------------------------------------- #
# Typed Pydantic models (Pattern 6)                                           #
# --------------------------------------------------------------------------- #


class LadMcpUnavailableEmission(BaseModel):
    """The atomic-emission return shape of :func:`surface_lad_unavailable`.

    Parallel to
    :class:`loud_fail_harness.mobile_driver.MobileMcpUnavailableEmission`
    byte-for-byte in shape (single ``marker_record`` field; frozen for
    determinism + hashability per Epic 1 retro Action #2).

    Registry rejection raises
    :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
    BEFORE the ``marker_record`` is constructed (atomic-on-failure
    per Pattern 5; mirrors Story 9.5's
    :class:`MobileMcpUnavailableEmission` precedent verbatim).

    Field semantics:
        * ``marker_record`` — the
          :class:`loud_fail_harness.env_provisioning.MarkerEmissionRecord`
          carrying ``marker_class="LAD-skipped"`` (Pattern 1
          kebab-case-yaml-with-acronym literal per the existing
          taxonomy v1 entry) + ``sub_cause=None`` (THE LITERAL ``None``;
          marker-taxonomy v1 ``LAD-skipped.sub_classifications: []``
          empty list per ``schemas/marker-taxonomy.yaml`` line 104; this
          module does NOT add sub_classifications per AC-9 invariant) +
          ``context`` carrying the four-field structured payload
          ``{story_id, sub_cause, diagnostic_pointer, lifecycle_phase}``
          (the init-vs-runtime distinction lives in ``context.sub_cause``
          + ``context.lifecycle_phase``, NOT in the marker's
          ``sub_cause`` field).
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    marker_record: MarkerEmissionRecord


# --------------------------------------------------------------------------- #
# Pure substrate function (Pattern 5 atomic-emission)                         #
# --------------------------------------------------------------------------- #


def surface_lad_unavailable(
    *,
    story_id: str,
    registry: MarkerClassRegistry,
    sub_cause: _SubCause,
    diagnostic_pointer: str,
) -> LadMcpUnavailableEmission:
    """Surface mid-run LAD MCP unavailability via the SINGLE
    source-of-truth ``LAD-skipped`` marker emission path.

    Composes Story 2.6's :func:`validate_marker_emission` for
    registry validation per Pattern 5 (atomic-on-failure). Pure: no
    file I/O, no env access, no run-state writes (the marker record
    is data the caller consumes; it is NOT persisted by THIS
    function — the caller routes it into Story 6.3's marker-coverage
    substrate).

    Behavior (parallel to Story 9.5's
    :func:`loud_fail_harness.mobile_driver.surface_mobile_mcp_unavailable`
    verbatim):

        * **Step 1 — Validate marker emission FIRST.** Calls
          :func:`validate_marker_emission(registry, LAD_SKIPPED_MARKER)`.
          On registry rejection
          :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
          propagates per Pattern 5; NO partial state is constructed
          (atomic-on-failure; mirrors Stories 3.3 / 4.2 / 4.3 / 4.4 /
          9.5).
        * **Step 2 — Construct the context dict** carrying the four
          required fields ``(story_id, sub_cause, diagnostic_pointer,
          lifecycle_phase)`` where ``lifecycle_phase`` is derived
          from ``sub_cause``: ``"init"`` for
          ``sub_cause="init-api-key-missing"``; ``"runtime"`` for
          either ``"mid-run-api-key-missing"`` or
          ``"mid-run-mcp-unavailable"``. The context is consumed by
          Story 6.3's marker-coverage audit + Story 6.2's
          actionable-pointer interpolation.
        * **Step 3 — Construct the marker emission record** with
          ``marker_class="LAD-skipped"``, ``sub_cause=None`` (THE
          LITERAL ``None``; marker-taxonomy v1
          ``LAD-skipped.sub_classifications: []`` empty list per
          ``schemas/marker-taxonomy.yaml`` line 104; AC-9 invariant
          preserved structurally), and ``context=<step 2 dict>``.
        * **Step 4 — Return the** :class:`LadMcpUnavailableEmission`
          **carrying the marker_record.**

    Args:
        story_id: BMAD story identifier (mirrors Story 9.5's
            :func:`surface_mobile_mcp_unavailable` parameter;
            threaded into the marker's ``context.story_id``).
        registry: The runtime :class:`MarkerClassRegistry` from
            :func:`loud_fail_harness.specialist_dispatch.load_marker_class_registry`;
            must contain the ``"LAD-skipped"`` marker class. The
            registry is injected per Pattern 6 dependency-injection
            (production callers load it once per
            ``/bmad-automation run`` invocation; tests inject
            fixture registries).
        sub_cause: Discriminator carried in the marker's
            ``context.sub_cause`` payload. One of:

            * ``"init-api-key-missing"`` — init-time path; the
              orchestrator's ``init`` precondition check observed
              ``review_lad.enabled=true`` AND the
              ``OPENROUTER_API_KEY`` env var unset. Carries
              ``lifecycle_phase="init"`` in the context.
            * ``"mid-run-api-key-missing"`` — the LAD wrapper
              returned ``status: blocked`` with the
              API-key-missing rationale (AC-1 verbatim literal).
              Carries ``lifecycle_phase="runtime"``.
            * ``"mid-run-mcp-unavailable"`` — the LAD dispatch path
              hit ``SpecialistTimeoutExceeded`` /
              ``EnvelopeValidationFailed`` / ``UnknownMarkerClass``,
              OR the wrapper returned ``status: blocked`` for any
              non-API-key-missing reason (MCP-process-crash,
              MCP-tool-timeout, malformed payload). Carries
              ``lifecycle_phase="runtime"``.

        diagnostic_pointer: The SDN-001-sourced diagnostic-pointer
            string. For init-time emission, the
            ``schemas/dependencies.yaml#lad.profiles.init.sub_classifications[condition=configured-but-api-key-missing].diagnostic_pointer``
            literal verbatim. For runtime emission, the
            ``schemas/dependencies.yaml#lad.profiles.runtime.sub_classifications[condition=configured-but-api-key-missing].diagnostic_pointer``
            literal verbatim. The caller sources both via
            :func:`loud_fail_harness.dependencies_validator.load_dependencies`
            per Story 1.6's source-of-truth rule — NEVER hardcoded
            as a Python string literal at the call site.

    Returns:
        :class:`LadMcpUnavailableEmission` carrying ``marker_record``.

    Raises:
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
            registry does not contain ``"LAD-skipped"``.
    """
    # Step 1 — atomic-on-failure registry validation per Pattern 5.
    validate_marker_emission(registry, LAD_SKIPPED_MARKER)

    # Step 2 — construct the structured context payload.
    lifecycle_phase: Literal["init", "runtime"] = (
        "init" if sub_cause == "init-api-key-missing" else "runtime"
    )
    context: Mapping[str, Any] = {
        "story_id": story_id,
        "sub_cause": sub_cause,
        "diagnostic_pointer": diagnostic_pointer,
        "lifecycle_phase": lifecycle_phase,
    }

    # Step 3 — construct the marker emission record. ``sub_cause=None``
    # preserves the marker-taxonomy v1 closed-set + empty
    # ``LAD-skipped.sub_classifications: []`` invariant per AC-9.
    marker_record = MarkerEmissionRecord(
        marker_class=LAD_SKIPPED_MARKER,
        sub_cause=None,
        context=context,
    )

    # Step 4 — return the emission shape.
    return LadMcpUnavailableEmission(marker_record=marker_record)
