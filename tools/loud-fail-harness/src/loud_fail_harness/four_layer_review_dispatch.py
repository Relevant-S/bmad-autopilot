"""Story 10.4 — `failed_layers` enum extension + `bmad-code-review` 4-layer integration.

Architectural placement (Story 1.10b + 2.6 + 3.3 substrate-library precedent):
this module is a **substrate-library NOT a sixth substrate component**.
ADR-003 Consequence 1 enumerates exactly FIVE substrate components
(envelope_validator, event_validator, reconciler, enumeration_check,
fixture_coverage); this module is a substrate **library** consumed by the
orchestrator skill prose (`skills/bmad-automation/steps/run.md` step (f))
and exercised at `tests/test_four_layer_review_dispatch.py`. The substrate-
component count remains FIVE post-Story-10.4 per `epics-phase-1.5.md`
line 119 + `docs/extension-audit.md` Story 10.4 row classification.

What this library provides
==========================

* :class:`FourLayerReviewResult` — frozen dataclass carrying the merged
  envelope plus the per-wrapper envelopes (read-only inspection surface
  for downstream Epic-5 retry routing + Story 2.11 bundle assembly +
  Story 6.4 cost telemetry).

* :func:`dispatch_four_layer_review` — composes Story 2.6's
  ``dispatch_callback`` to dispatch ``review-bmad`` AND (when
  ``lad_enabled=True``) ``lad`` as TWO Task-tool invocations from a
  single orchestrator-side seam. The dispatches are conceptually
  parallel (both consume the same ``story_id`` + AC list + change set;
  neither depends on the other's envelope); at runtime the LLM may
  dispatch them sequentially via two Task-tool calls — the substrate
  function returns AFTER both envelopes are validated and present. The
  function's signature mirrors Story 2.6's dispatch surface — same
  ``DispatchCallback`` type alias, same ``EventLogAppender`` closure,
  same ``StoryDocResolution`` — to preserve substrate uniformity per
  ADR-004.

* :func:`merge_review_envelopes` — pure function (no I/O, no env
  access) that merges the two specialist envelopes into a single
  review-envelope-shape dict: concatenates ``findings`` arrays
  (preserving each finding's ``source`` value verbatim — ``blind`` /
  ``edge`` / ``auditor`` / ``merged`` from Review-BMAD; ``lad`` from
  Review-LAD); composes ``failed_layers`` via
  :func:`loud_fail_harness.review_layer_failure.surface_failed_layers`
  (single canonical site for the three-channel atomic emission per
  Story 3.3 AC-9); composes ``status`` per the merged verdict semantics
  (any HIGH/patch finding → ``fail``; total 4-of-4 layer failure →
  ``blocked``; otherwise ``pass``); composes ``artifacts`` as the
  sorted union; composes ``rationale`` as a 1-3 sentence prose summary
  (Phase-1 prose preserved when LAD is disabled — AC-7 bit-identity
  invariant).

Architectural anchors
=====================

* **FR-P1.5-1** (Phase-1.5 / Review-LAD activation) — LAD lands as the
  opt-in 4th parallel reviewer; default-off; gated by
  ``_bmad/automation/config.yaml#review_lad.enabled``.
* **FR29** (4-layer adversarial review composition) — LAD integrates
  alongside the existing 3 Review-BMAD layers (blind / edge / auditor).
* **FR56** (failed_layers envelope-field declaration) — the merged
  envelope's ``failed_layers`` field admits ``lad`` per the schema's
  enum (Phase-1 reservation honoured at runtime by THIS story).
* **FR62** (pluggability invariant) — this module dispatches
  ``review-bmad`` and ``lad`` wrappers via the substrate's
  ``dispatch_callback`` abstraction; it does NOT ``import`` either
  wrapper's prose, and it does NOT reference Dev / QA wrappers. The
  substrate at ``tools/loud-fail-harness/`` is OUTSIDE the FR62
  pluggability gate's scope by construction (the gate scans
  ``agents/*.md`` only). Sibling specialists (Dev, QA) are referenced
  ONLY by HUMAN-READABLE prose names if at all; this module references
  no specialist by slug or path.
* **NFR-S1** (sensor-not-advisor) — the merged envelope carries zero
  flow-policy fields; ``merge_review_envelopes`` does not introduce
  ``next_action`` / ``recommendation`` / any orchestrator-flow signal.
* **Pattern 1** (snake_case fields; kebab-case identifier values) —
  every new identifier follows the convention.
* **Pattern 4** (state-update discipline — envelope mutated in-place at
  the final ``surface_failed_layers`` call site per Story 3.3's
  in-place mutation contract).
* **Pattern 5** (loud-fail doctrine) — LAD-layer structural failure
  (``SpecialistTimeoutExceeded`` / ``EnvelopeValidationFailed`` /
  ``UnknownMarkerClass``) is caught at the dispatch boundary and
  routed through ``surface_failed_layers`` (single source-of-truth
  emission path for the three-channel projection); the substrate does
  NOT silently swallow LAD failures.
* **ADR-003** — substrate-component closure at FIVE preserved.
* **ADR-004** — specialist-dispatch mechanism (Task tool); this
  substrate composes Story 2.6's ``dispatch_callback`` factory output
  at the same protocol level per ADR-004's substrate-vs-LLM-runtime
  split.
* **ADR-008** — LAD MCP server selection (consumed indirectly via the
  ``agents/review-lad-wrapper.md`` envelope shape; this module does
  NOT directly invoke the ``mcp__lad__code_review`` tool).

FR62 pluggability classification (verbatim per Story 10.4 AC-2)
===============================================================

This module is *substrate-shared library* per Story 1.10b's precedent.
The FR62 pluggability gate at
:mod:`loud_fail_harness.pluggability_gate` scans ``agents/*.md`` only;
the substrate at ``tools/loud-fail-harness/`` is OUTSIDE the gate's
scope by construction. Sibling specialists (Dev, QA) are referenced
ONLY by HUMAN-READABLE prose names if at all; this module dispatches
Review-BMAD and Review-LAD via the ``dispatch_callback`` substrate
abstraction — it does NOT import either wrapper's prose, and it does
NOT reference Dev or QA wrappers.

LAD-layer-failure detection
===========================

``merge_review_envelopes`` treats LAD as failed when either:

(i) ``lad_envelope is None`` — the dispatch raised a named exception
    (``SpecialistTimeoutExceeded`` / ``EnvelopeValidationFailed`` /
    ``UnknownMarkerClass``) and was caught at the dispatch boundary
    by :func:`dispatch_four_layer_review`; OR

(ii) ``lad_envelope["status"] == "blocked"`` — the wrapper itself
     signalled a precondition failure per Story 10.2 AC-2 status
     semantics (e.g., MCP process crashed, dispatch payload malformed,
     upstream MCP-server-reported error such as missing/invalid API
     key per Story 12.2's validation-responsibility-boundary
     correction).

The two detection paths converge to the same three-channel emission
(``failed_layers: ["lad"]`` + synthetic ``decision_needed: HIGH``
finding carrying the meta discriminator + the marker class
emission record) via the existing
:func:`loud_fail_harness.review_layer_failure.surface_failed_layers`
substrate. Symbolic constants:
:data:`loud_fail_harness.review_layer_failure.REVIEW_LAYER_FAILED_MARKER`
(marker-class identifier) and
:data:`loud_fail_harness.review_layer_failure.META_REVIEW_COMPLETENESS`
(synthetic meta-finding discriminator).

No-introduction principle (Story 3.2 + Story 10.3 codification)
===============================================================

THIS story introduces:

* ZERO new marker classes (the
  :data:`loud_fail_harness.review_layer_failure.REVIEW_LAYER_FAILED_MARKER`
  marker class is reused per the marker-taxonomy v1 27-class closed-set
  invariant);
* ZERO envelope-schema shape changes (Story 10.3's prose-only update is
  the only Phase-1.5 envelope-schema edit);
* ZERO new dependencies (``lad`` was activated at Story 10.1);
* ZERO new substrate components (the substrate-library classification
  is recorded in ``docs/extension-audit.md`` per AC-11).

The marker class carries the failed-layer
identifier as a structured payload field per Story 3.3's
:class:`MarkerEmissionRecord` shape — NOT as a new sub-classification
enum value. The 27-class top-level closed-set is preserved.

Cross-references
================

* Story 2.6 :mod:`loud_fail_harness.specialist_dispatch` —
  ``DispatchCallback`` Protocol, ``make_task_tool_dispatch_callback``
  factory, ``SpecialistTimeoutExceeded`` / ``EnvelopeValidationFailed``
  / ``UnknownMarkerClass`` named-invariant exceptions.
* Story 3.3 :mod:`loud_fail_harness.review_layer_failure` —
  :func:`surface_failed_layers` single source-of-truth three-channel
  emission path; THIS module's :func:`merge_review_envelopes` composes
  it for the LAD-layer-failure projection (AC-3 invariant).
* Story 3.3 :mod:`loud_fail_harness.review_layer_failure_emission_gate`
  — the AC-9 CI lint that structurally enforces the no-bypass
  invariant; THIS module passes the lint by construction (composes
  ``surface_failed_layers`` rather than mutating ``failed_layers``
  directly / appending the marker-string literal / appending
  meta-discriminator findings outside the canonical site).
* Story 10.1 ``schemas/dependencies.yaml`` — ``lad`` activated.
* Story 10.2 ``agents/review-lad-wrapper.md`` — the standalone LAD
  wrapper this module's runtime composes as the second of two parallel
  dispatches when ``lad_enabled=True``.
* Story 10.3 ``examples/envelopes/review-lad-{pass,fail-shape}.yaml``
  — the canonical LAD envelope fixtures; THIS module's tests consume
  the passing fixture verbatim.
* Story 10.5 — env-var-handling discipline at runtime (``LAD-skipped``
  marker emission via :func:`surface_lad_unavailable` for the
  LAD-unavailable / wrapper-blocked path; distinct from THIS story's
  runtime-failure marker per the symbolic
  :data:`loud_fail_harness.review_layer_failure.REVIEW_LAYER_FAILED_MARKER`
  constant).
* Story 10.6 — pluggability-CI-gate coverage extension to
  Review-LAD code + cost-observability partition extension.
* Story 10.7 — reference LAD-enabled end-to-end run fixture.
* Story 12.2 + Sprint Change Proposal 2026-05-18 —
  validation-responsibility-boundary correction. Retired the
  wrapper-side ``OPENROUTER_API_KEY`` presence check, the paired
  ``_LAD_API_KEY_MISSING_RATIONALE_SUBSTRING`` substrate rationale-
  substring discriminator, and the
  ``_load_lad_runtime_diagnostic_pointer`` SDN-001 reader. After
  this story the LAD-blocked branch collapses to a single
  unconditional ``mid-run-mcp-unavailable`` ``sub_cause`` emission
  carrying a credential-agnostic substrate-fallback diagnostic
  pointer (constant ``_LAD_MID_RUN_MCP_UNAVAILABLE_DIAGNOSTIC``);
  third-party credential validation lives at the upstream
  ``lad_mcp_server`` MCP boundary, not in this substrate.

See also: ``docs/extension-audit.md`` "no-introductions principle"
subsection (Story 3.2 codification) — THIS story is a worked instance.
"""

from __future__ import annotations

import dataclasses
import pathlib
from collections.abc import Callable
from typing import Any

from loud_fail_harness.env_provisioning import MarkerEmissionRecord
from loud_fail_harness.lad_mcp_unavailable import surface_lad_unavailable
from loud_fail_harness.orchestrator_run_entry import (
    DispatchCallback,
    StoryDocResolution,
)
from loud_fail_harness.review_layer_failure import (
    surface_failed_layers,
)
from loud_fail_harness.specialist_dispatch import (
    EnvelopeValidationFailed,
    EventLogAppender,
    MarkerClassRegistry,
    SpecialistTimeoutExceeded,
    UnknownMarkerClass,
)

__all__ = [
    "FourLayerReviewResult",
    "dispatch_four_layer_review",
    "merge_review_envelopes",
]


#: The LAD layer identifier — kebab-case-yaml-style scalar per Pattern 1.
#: Sourced from the schema's ``failed_layers`` items enum + the
#: ``$defs/finding.source`` enum at ``schemas/envelope.schema.yaml``;
#: also enumerated in :data:`loud_fail_harness.specialist_dispatch.SpecialistId`
#: (the dispatch-callback's specialist identifier) per Story 10.2's baseline.
_LAD_LAYER: str = "lad"

#: The Review-BMAD layer identifiers — used for the merged-verdict
#: blocked-on-total-4-layer-failure check at :func:`_compose_merged_status`.
_REVIEW_BMAD_LAYERS: frozenset[str] = frozenset({"blind", "edge", "auditor"})

#: All four parallel review layers — the 4-of-4 failure case for the
#: ``blocked`` verdict.
_ALL_FOUR_LAYERS: frozenset[str] = _REVIEW_BMAD_LAYERS | {_LAD_LAYER}


#: Substrate fallback diagnostic_pointer for the LAD mid-run unavailable
#: emission path (Story 12.2 + Sprint Change Proposal 2026-05-18 —
#: validation-responsibility-boundary correction). After Story 12.2 the
#: schema-sourced ``configured-but-api-key-missing`` runtime
#: ``diagnostic_pointer`` is retired (the schema's
#: ``lad.profiles.runtime.sub_classifications`` list shrinks to the
#: ``unconfigured`` entry, which is ``silent`` and carries no pointer).
#: This module-level constant is the credential-agnostic substrate
#: fallback the LAD-blocked branch passes to
#: :func:`surface_lad_unavailable`; the upstream MCP server's error
#: text (when present in the wrapper's ``rationale``) remains the
#: load-bearing operator signal.
_LAD_MID_RUN_MCP_UNAVAILABLE_DIAGNOSTIC: str = (
    "LAD MCP unavailable mid-run; 4th-layer review skipped."
)


#: Type alias for the envelope-resolver callable injected into
#: :func:`dispatch_four_layer_review`. Given a specialist identifier
#: (``"review-bmad"`` or ``"lad"``), returns the validated envelope
#: dict produced by that specialist's Task-tool dispatch.
#:
#: The production-time resolver (LLM-runtime) is constructed in
#: ``skills/bmad-automation/steps/run.md``'s step (f) — it parses the
#: Task tool's returned text via the substrate's
#: :func:`loud_fail_harness.specialist_dispatch.validate_return_envelope`
#: helper per Story 2.6's post-dispatch protocol at
#: ``skills/bmad-automation/steps/dispatch.md``. Tests inject
#: deterministic resolvers that return synthetic envelopes for
#: byte-stable assertions.
EnvelopeResolver = Callable[[str], dict[str, Any]]


@dataclasses.dataclass(frozen=True)
class FourLayerReviewResult:
    """Frozen dataclass carrying the 4-layer review-dispatch outcome.

    Frozen for determinism + hashability per Epic 1 retro Action #2.

    Field semantics:

        * ``merged_envelope`` — the merged review envelope produced by
          :func:`merge_review_envelopes`. When ``lad_dispatched`` is
          False, this is byte-equivalent to ``review_bmad_envelope``
          per the AC-5 bit-identity invariant (the LAD-disabled merge
          is a structural passthrough).
        * ``review_bmad_envelope`` — the Review-BMAD wrapper's envelope
          verbatim as returned by its Task-tool dispatch (preserved
          for diagnostic / downstream-consumer inspection per Story
          3.5's auditing precedent).
        * ``lad_envelope`` — the Review-LAD wrapper's envelope verbatim
          when LAD was dispatched AND its return envelope validated
          successfully; ``None`` when LAD was not dispatched
          (``lad_enabled=False``) OR when LAD's dispatch raised a
          named-invariant exception caught at the dispatch boundary
          (graceful-degradation per FR28 strict-superset semantics).
        * ``lad_dispatched`` — ``True`` iff ``lad_enabled=True`` was
          passed AND the dispatch callback was invoked for
          ``specialist="lad"`` (regardless of whether the dispatch
          succeeded — a dispatch attempt that caught a structural
          failure still counts as ``lad_dispatched=True`` because the
          dispatch-side observable was produced).
        * ``lad_skipped_emissions`` — tuple of
          :class:`loud_fail_harness.env_provisioning.MarkerEmissionRecord`
          carrying the ``LAD-skipped`` marker emissions produced at
          the LAD-dispatch-failure surface (Story 10.5 AC-4 + Story
          12.2 validation-responsibility-boundary correction). Each
          record's ``context.sub_cause`` is always
          ``"mid-run-mcp-unavailable"`` post-Story-12.2 (the prior
          ``"mid-run-api-key-missing"`` discriminator was retired
          when the wrapper-side ``OPENROUTER_API_KEY`` presence check
          + paired substrate rationale-substring branch were removed;
          upstream credential errors now flow through the unified
          ``mid-run-mcp-unavailable`` path). Empty tuple ``()`` when
          LAD is disabled (AC-5 silence-unless-configured invariant)
          OR when LAD reached a verdict (``status: pass`` / ``fail``).
          Default ``()`` preserves backward-compatibility for Story
          10.4's existing tests.
    """

    merged_envelope: dict[str, Any]
    review_bmad_envelope: dict[str, Any]
    lad_envelope: dict[str, Any] | None
    lad_dispatched: bool
    lad_skipped_emissions: tuple[MarkerEmissionRecord, ...] = ()


def merge_review_envelopes(
    *,
    review_bmad_envelope: dict[str, Any],
    lad_envelope: dict[str, Any] | None,
    marker_registry: MarkerClassRegistry,
) -> dict[str, Any]:
    """Merge the Review-BMAD and Review-LAD envelopes into a single
    review-envelope-shape dict.

    Pure function — no I/O, no environment access, no clock reads.
    Deterministic across runs given identical inputs (Epic 1 retro
    Action #2).

    LAD-absent branch (``lad_envelope is None`` AND
    ``review_bmad_envelope.get("failed_layers")`` contains no ``"lad"``
    entry): returns a deep-equality clone of ``review_bmad_envelope``
    AS-IS — the AC-7 bit-identity invariant. The function does NOT
    invoke :func:`surface_failed_layers` in this branch because the
    Review-BMAD envelope is already complete (the wrapper-side
    discipline at ``agents/review-bmad-wrapper.md`` already emitted
    the three-channel atomic projection for any Review-BMAD layer
    failures).

    LAD-present branch (``lad_envelope is not None`` OR an LAD-failure
    signal needs surfacing): composes a merged envelope skeleton; sorts
    the union of findings deterministically by ``(source, id)``; sorts
    the union of artifacts by string-comparison; computes the union of
    failed layers; composes the merged status; composes the merged
    rationale; THEN invokes :func:`surface_failed_layers` at a SINGLE
    call site to apply the three-channel atomic emission for the LAD
    layer when LAD is detected as failed.

    LAD-layer-failure detection (the two convergent paths):

        (i) ``lad_envelope is None`` — the caller's dispatch-side
            graceful-degradation path caught a named-invariant
            exception and signals "LAD failed structurally; surface
            the failure via the existing three-channel emission".

        (ii) ``lad_envelope["status"] == "blocked"`` — the wrapper
             itself signalled a precondition failure per Story 10.2
             AC-2 status semantics.

    Args:
        review_bmad_envelope: The Review-BMAD wrapper's envelope dict.
            Required; the function dereferences ``findings``,
            ``artifacts``, ``failed_layers``, ``status``, ``rationale``.
        lad_envelope: The Review-LAD wrapper's envelope dict, or
            ``None`` to signal LAD-disabled OR LAD-failed-at-dispatch.
        marker_registry: The runtime :class:`MarkerClassRegistry`;
            passed through to :func:`surface_failed_layers` when LAD
            is detected as failed. The registry MUST contain the
            ``review-layer-failed`` marker class (Story 1.4
            enumeration); registry rejection raises
            :exc:`UnknownMarkerClass` per Pattern 5.

    Returns:
        Merged envelope dict carrying ``status``, ``artifacts``,
        ``findings``, ``rationale``, ``failed_layers``. The dict is
        schema-conformant against ``schemas/envelope.schema.yaml``
        (assuming both input envelopes are schema-conformant).

    Raises:
        :exc:`UnknownMarkerClass`: registry does not contain the
        marker-class identifier referenced via
        :data:`loud_fail_harness.review_layer_failure.REVIEW_LAYER_FAILED_MARKER`.
        Propagates unchanged from :func:`surface_failed_layers`;
        Pattern 5 named-invariant diagnostic.
    """
    review_bmad_failed_layers: list[str] = list(
        review_bmad_envelope.get("failed_layers", [])
    )
    lad_failed = lad_envelope is None or lad_envelope.get("status") == "blocked"

    # LAD-absent + Review-BMAD has no "lad" entry → bit-identity
    # structural passthrough per AC-7. Return a deep-equality clone via
    # construction (preserves all dict keys, list orderings, scalar
    # values verbatim; no surface_failed_layers call needed because the
    # Review-BMAD envelope is already complete).
    if lad_envelope is None and _LAD_LAYER not in review_bmad_failed_layers:
        return _shallow_clone_envelope(review_bmad_envelope)

    merged: dict[str, Any] = _shallow_clone_envelope(review_bmad_envelope)

    # Compose findings as the deterministic union of both envelopes'
    # findings, sorted by (source, id) per Epic 1 retro Action #2.
    review_bmad_findings: list[dict[str, Any]] = list(
        review_bmad_envelope.get("findings", [])
    )
    lad_findings: list[dict[str, Any]] = (
        list(lad_envelope.get("findings", [])) if lad_envelope is not None else []
    )
    merged["findings"] = sorted(
        review_bmad_findings + lad_findings,
        key=lambda f: (f.get("source", ""), f.get("id", "")),
    )

    # Compose artifacts as the sorted union per AC-6.
    review_bmad_artifacts: set[str] = set(review_bmad_envelope.get("artifacts", []))
    lad_artifacts: set[str] = (
        set(lad_envelope.get("artifacts", [])) if lad_envelope is not None else set()
    )
    merged["artifacts"] = sorted(review_bmad_artifacts | lad_artifacts)

    # Compute the union of failed layers — Review-BMAD's existing
    # failed_layers entries + {"lad"} when LAD failed (either path).
    failed_layers_union: set[str] = set(review_bmad_failed_layers)
    if lad_failed:
        failed_layers_union.add(_LAD_LAYER)

    # Compose the merged status per AC-6 verdict semantics.
    merged["status"] = _compose_merged_status(
        merged_findings=merged["findings"],
        review_bmad_status=str(review_bmad_envelope.get("status", "")),
        failed_layers_union=failed_layers_union,
    )

    # Compose the merged rationale per AC-2 — 1-3 sentence prose;
    # names the 4-layer composition; preserves Review-BMAD's prose
    # context for diagnostic continuity.
    merged["rationale"] = _compose_merged_rationale(
        review_bmad_rationale=str(review_bmad_envelope.get("rationale", "")),
        lad_envelope=lad_envelope,
        lad_failed=lad_failed,
    )

    # Surface the failed-layer projection via the SINGLE source-of-truth
    # emission path per AC-3 — invoked ONLY when LAD failed (the FIRST
    # runtime consumer-via-`lad` site per AC-3 verbatim). AC-6 case (iv):
    # when LAD passes (lad_failed=False) and Review-BMAD has its own
    # failed_layers (e.g., ["edge"]), we do NOT re-call
    # surface_failed_layers — Review-BMAD's wrapper already emitted the
    # three-channel projection for its own layers per the wrapper-side
    # discipline at agents/review-bmad-wrapper.md (Story 3.3 three-
    # channel section); the merged envelope inherits failed_layers
    # verbatim from review_bmad_envelope via the _shallow_clone_envelope
    # call above.
    #
    # When invoked, surface_failed_layers is passed the UNION of Review-
    # BMAD's failed_layers plus {"lad"} per AC-3 verbatim ("passes the
    # union of Review-BMAD's `failed_layers` plus `["lad"]`-when-LAD-
    # failed"). The function emits synthetic meta-findings for ALL union
    # members; the post-call dedup collapses any duplicates against
    # Review-BMAD's prior wrapper-side emission (channel 3 appends per-
    # layer regardless of pre-existing per-layer findings).
    if lad_failed:
        _emissions = surface_failed_layers(
            merged, sorted(failed_layers_union), marker_registry
        )
        _ = _emissions  # tuple consumed by bundle assembler; not surfaced here
        # Re-sort + dedup synthetic findings by (source, id) for byte-
        # stable output; surface_failed_layers may have appended
        # duplicates against Review-BMAD's prior wrapper-side emission.
        merged["findings"] = _dedup_findings_by_id_source(merged["findings"])

    return merged


def dispatch_four_layer_review(
    *,
    story_id: str,
    story_doc_resolution: StoryDocResolution,
    run_state_path: pathlib.Path,
    dispatch_callback: DispatchCallback,
    event_log_appender: EventLogAppender,
    marker_registry: MarkerClassRegistry,
    envelope_resolver: EnvelopeResolver,
    lad_enabled: bool,
    agent_definition_dir: pathlib.Path,
    lad_api_key_env_var: str = "OPENROUTER_API_KEY",
) -> FourLayerReviewResult:
    """Composes Story 2.6's ``dispatch_callback`` to dispatch
    ``review-bmad`` and (when ``lad_enabled=True``) ``lad`` as TWO
    Task-tool invocations from a single orchestrator-side seam.

    The dispatches are conceptually parallel (both consume the same
    ``story_id`` + AC list + change set; neither depends on the other's
    envelope); at runtime the LLM may dispatch them sequentially via
    two Task-tool calls — the substrate function returns AFTER both
    envelopes are validated and present.

    LAD-enabled graceful-degradation (FR28 strict-superset semantics):
    if the LAD dispatch raises :exc:`SpecialistTimeoutExceeded` /
    :exc:`EnvelopeValidationFailed` / :exc:`UnknownMarkerClass` (Story
    2.6's named exceptions), the substrate catches the structural
    failure (does NOT propagate); the merge composes via
    :func:`merge_review_envelopes` with ``lad_envelope=None``; the
    three-channel atomic emission at the merge site projects
    ``failed_layers: [..., "lad"]`` via the existing
    :func:`surface_failed_layers` substrate (AC-3 invariant).

    LAD-disabled bit-identity invariant (AC-5): if ``lad_enabled is
    False``, the substrate dispatches Review-BMAD ONCE and short-
    circuits — zero LAD Task-tool invocation; zero ``lad`` dispatch
    log written; zero ``specialist-dispatched`` orchestrator event
    with ``specialist: lad``; zero ``lad`` cost-telemetry row
    aggregated. The merged envelope is byte-equivalent to the
    Review-BMAD envelope.

    Args:
        story_id: BMAD story identifier.
        story_doc_resolution: Resolved story-doc shape per Story 2.5's
            :class:`StoryDocResolution`.
        run_state_path: Path to the run-state YAML (passed through to
            the dispatch callback per Story 2.6's Protocol shape).
        dispatch_callback: Story 2.6's ``DispatchCallback`` —
            structurally compatible with
            :class:`TaskToolDispatchCallback` returned by
            :func:`make_task_tool_dispatch_callback`. Invoked exactly
            once for ``specialist="review-bmad"`` AND (when
            ``lad_enabled=True``) exactly once for ``specialist="lad"``.
        event_log_appender: Story 2.6's ``EventLogAppender`` closure
            (passed through to the dispatch callback for the
            ``specialist-dispatched`` / ``specialist-returned`` event
            emission per ``steps/dispatch.md`` protocol).
        marker_registry: Pre-loaded :class:`MarkerClassRegistry` (the
            orchestrator skill loads this once per
            ``/bmad-automation run`` invocation). Passed through to
            :func:`merge_review_envelopes`.
        envelope_resolver: Callable that returns the validated
            envelope dict for a given specialist id. The production-
            time resolver (LLM-runtime) parses the Task-tool returned
            text via Story 2.6's
            :func:`validate_return_envelope` per
            ``skills/bmad-automation/steps/dispatch.md`` post-dispatch
            protocol. Tests inject deterministic resolvers.
        lad_enabled: Config-driven gate per AC-1
            (``_bmad/automation/config.yaml#review_lad.enabled``).
            When ``False``, this function short-circuits after the
            Review-BMAD dispatch.
        agent_definition_dir: Directory under which the agent-definition
            files live (typically ``agents/`` per Stories 2.8 / 2.9 /
            2.10 / 10.2 landings). Mirrors Story 2.6's substrate
            surface; reserved for future thickening (e.g., Story 10.6's
            cost-observability partition might inspect the LAD wrapper
            file at this path). Unused inside the function body at MVP.

    Returns:
        :class:`FourLayerReviewResult` carrying the merged envelope,
        per-wrapper envelopes, and the ``lad_dispatched`` flag.

    Raises:
        Any exception NOT in
        ``{SpecialistTimeoutExceeded, EnvelopeValidationFailed,
        UnknownMarkerClass}`` raised by ``dispatch_callback`` is
        propagated unchanged (these are the only structural-failure
        exceptions caught + routed through the LAD graceful-degradation
        path per AC-6). The Review-BMAD dispatch's exceptions are
        propagated unchanged in all cases (Review-BMAD failure is NOT
        gracefully degraded at THIS story's scope — that would require
        a different policy decision the orchestrator skill owns).
    """
    # Reserved for forward-compatibility per AC-2 (mirrors substrate
    # surface; Story 10.6 + 10.7 may consume); document via _ to
    # silence the unused-parameter check without dropping the
    # signature symmetry.
    _ = agent_definition_dir

    # 1. Dispatch Review-BMAD via the existing Story 2.6 surface.
    review_bmad_dispatch_result = dispatch_callback(
        specialist="review-bmad",
        story_id=story_id,
        run_state_path=run_state_path,
        story_doc_resolution=story_doc_resolution,
        event_log_appender=event_log_appender,
    )
    _ = review_bmad_dispatch_result  # DispatchCallbackResult; envelope read via resolver

    review_bmad_envelope = envelope_resolver("review-bmad")

    # 2. LAD-disabled bit-identity short-circuit per AC-5.
    if not lad_enabled:
        return FourLayerReviewResult(
            merged_envelope=_shallow_clone_envelope(review_bmad_envelope),
            review_bmad_envelope=review_bmad_envelope,
            lad_envelope=None,
            lad_dispatched=False,
        )

    # 3. Dispatch LAD with graceful-degradation per AC-6. Catch the
    # three Story 2.6 named-invariant exceptions ONLY; any other
    # exception is a substrate bug or an out-of-band signal and
    # propagates unchanged per Pattern 5.
    #
    # Implementation choice (Task 2 step 3 of the story doc): on
    # caught structural failure, synthesize a `status: blocked` LAD
    # envelope so the merge_review_envelopes flow converges on the
    # wrapper-side blocked path. The synthesized envelope is NOT
    # exposed as `lad_envelope` on the returned FourLayerReviewResult
    # (that field is None to signal "LAD did not produce a real
    # envelope"); the merge consumes the synthetic envelope shape
    # internally to drive the failed_layers + synthetic-finding +
    # marker emission via surface_failed_layers.
    lad_envelope: dict[str, Any] | None
    lad_dispatch_failure_reason: str | None = None
    try:
        lad_dispatch_result = dispatch_callback(
            specialist=_LAD_LAYER,
            story_id=story_id,
            run_state_path=run_state_path,
            story_doc_resolution=story_doc_resolution,
            event_log_appender=event_log_appender,
            api_key_env_var=lad_api_key_env_var,
        )
        _ = lad_dispatch_result
        lad_envelope = envelope_resolver(_LAD_LAYER)
    except (
        SpecialistTimeoutExceeded,
        EnvelopeValidationFailed,
        UnknownMarkerClass,
    ) as exc:
        lad_envelope = None
        lad_dispatch_failure_reason = type(exc).__name__

    # Route to merge — when dispatch raised, synthesize a blocked-shape
    # LAD envelope so the merge's wrapper-blocked branch fires and
    # surface_failed_layers projects ["lad"] into failed_layers + the
    # synthetic meta-finding + the marker emission record.
    merge_lad_envelope: dict[str, Any] | None
    if lad_envelope is None and lad_dispatch_failure_reason is not None:
        merge_lad_envelope = {
            "status": "blocked",
            "artifacts": [],
            "findings": [],
            "rationale": (
                f"Review-LAD dispatch raised {lad_dispatch_failure_reason} "
                "at the substrate seam; graceful-degradation per FR28."
            ),
        }
    else:
        merge_lad_envelope = lad_envelope

    merged_envelope = merge_review_envelopes(
        review_bmad_envelope=review_bmad_envelope,
        lad_envelope=merge_lad_envelope,
        marker_registry=marker_registry,
    )

    # Story 10.5 AC-4 + Story 12.2 — mid-run ``LAD-skipped`` emission
    # site. Composes :func:`surface_lad_unavailable` (the single
    # source-of-truth substrate-library callable per Story 10.5 AC-2)
    # on the LAD-dispatch-failure path. Per Story 12.2 + Sprint Change
    # Proposal 2026-05-18 (validation-responsibility-boundary
    # correction), the prior rationale-substring discriminator
    # (``mid-run-api-key-missing`` vs ``mid-run-mcp-unavailable``) is
    # retired; the LAD-blocked branch collapses to a single
    # unconditional ``mid-run-mcp-unavailable`` ``sub_cause`` emission.
    # Third-party credential-error discrimination belongs at the
    # upstream MCP-server boundary, not here.
    #
    # The emission is ADDITIVE — it fires IN ADDITION TO the existing
    # ``review-layer-failed`` marker emission via
    # :func:`surface_failed_layers` inside :func:`merge_review_envelopes`
    # (the substrate-vs-operator concerns are orthogonal per the Story
    # 10.5 Dev Notes — ``LAD-skipped`` is operator-actionable while the
    # other marker is reviewer-side; both land when LAD fails mid-run).
    lad_skipped_emissions: tuple[MarkerEmissionRecord, ...] = ()
    if lad_dispatch_failure_reason is not None or (
        lad_envelope is not None and lad_envelope.get("status") == "blocked"
    ):
        _lad_emission = surface_lad_unavailable(
            story_id=story_id,
            registry=marker_registry,
            sub_cause="mid-run-mcp-unavailable",
            diagnostic_pointer=_LAD_MID_RUN_MCP_UNAVAILABLE_DIAGNOSTIC,
        )
        lad_skipped_emissions = (_lad_emission.marker_record,)
    # else — LAD reached a verdict (status == "pass" or "fail") or the
    # envelope is None (LAD disabled — structurally unreachable here
    # because the AC-5 short-circuit returns earlier). Empty-tuple
    # default carries through.

    return FourLayerReviewResult(
        merged_envelope=merged_envelope,
        review_bmad_envelope=review_bmad_envelope,
        lad_envelope=lad_envelope,
        lad_dispatched=True,
        lad_skipped_emissions=lad_skipped_emissions,
    )


def _shallow_clone_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Return a clone of ``envelope`` with list-typed top-level fields
    copied so the returned dict is safely mutable without affecting
    the input.

    ``artifacts`` and ``failed_layers`` receive shallow list copies
    (their items are strings). ``findings`` receives a one-level-deep
    copy (each finding dict is a new ``dict`` instance) so that
    downstream mutation of a finding's scalar fields — e.g. adding a
    ``meta`` key — does not leak back into the input envelope's finding
    dicts. Finding fields that are themselves containers (nested dicts
    or lists) are still shared, but no current substrate code mutates
    those sub-structures.
    """
    clone: dict[str, Any] = dict(envelope)
    for list_field in ("artifacts", "failed_layers"):
        if list_field in clone and isinstance(clone[list_field], list):
            clone[list_field] = list(clone[list_field])
    if "findings" in clone and isinstance(clone["findings"], list):
        clone["findings"] = [dict(f) for f in clone["findings"]]
    return clone


def _compose_merged_status(
    *,
    merged_findings: list[dict[str, Any]],
    review_bmad_status: str,
    failed_layers_union: set[str],
) -> str:
    """Compose the merged envelope's ``status`` per AC-6 verdict semantics.

    The rule (in priority order):

    (1) Any finding with ``bucket == "patch"`` AND ``severity == "HIGH"``
        → ``"fail"`` (the substantive-AC-violation precedence; mirrors
        the Review-BMAD wrapper's existing status discipline at
        ``agents/review-bmad-wrapper.md`` line 40).
    (2) All four layers failed (``failed_layers_union == {"blind",
        "edge", "auditor", "lad"}``) AND Review-BMAD's own ``status``
        is ``"blocked"`` → ``"blocked"`` (the 4-of-4-layer total-failure
        case; no surviving layer reached a verdict).
    (3) Otherwise → ``"pass"`` (FR28 strict-superset graceful-
        degradation; the LAD layer can carry the verdict when
        Review-BMAD totally failed, and vice versa).
    """
    for finding in merged_findings:
        if (
            finding.get("bucket") == "patch"
            and finding.get("severity") == "HIGH"
        ):
            return "fail"

    if (
        failed_layers_union == _ALL_FOUR_LAYERS
        and review_bmad_status == "blocked"
    ):
        return "blocked"

    return "pass"


def _compose_merged_rationale(
    *,
    review_bmad_rationale: str,
    lad_envelope: dict[str, Any] | None,
    lad_failed: bool,
) -> str:
    """Compose the merged envelope's ``rationale`` — 1-3 sentence prose
    naming the 4-layer composition per AC-2.

    When ``lad_envelope`` is present (not None) and LAD did NOT fail:
    appends a brief LAD-layer-contribution sentence to the Review-BMAD
    rationale. When ``lad_failed`` is True: appends a brief LAD-layer-
    failure sentence (the orchestrator-side flow policy decides whether
    to retry per FR28). When LAD is disabled (``lad_envelope is None``
    AND ``not lad_failed``): the caller has already returned via the
    bit-identity short-circuit, so this function is not invoked.
    """
    base = review_bmad_rationale.strip() or (
        "Review-BMAD composition reached a verdict at the 4-layer "
        "review-seam."
    )
    if lad_failed:
        return (
            f"{base} The Phase-1.5 LAD layer failed structurally and was "
            "gracefully degraded per FR28; orchestrator-side flow policy "
            "decides whether to retry the LAD layer."
        )
    lad_rationale = (
        str(lad_envelope.get("rationale", "")).strip()
        if lad_envelope is not None
        else ""
    )
    if lad_rationale:
        return (
            f"{base} The Phase-1.5 LAD layer also reached a verdict: "
            f"{lad_rationale}"
        )
    return f"{base} The Phase-1.5 LAD layer ran as the 4th parallel reviewer."


def _dedup_findings_by_id_source(
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """De-duplicate ``findings`` by ``(source, id)`` preserving first
    occurrence; re-sort by ``(source, id)`` for byte-stable output.

    Required because :func:`surface_failed_layers` appends one
    synthetic meta-finding per failed layer (channel 3) — when
    Review-BMAD's wrapper-side emission already covered (e.g.,) the
    ``edge`` layer, the merged envelope's ``findings`` array
    initially has two ``review-layer-failed-edge`` entries (one from
    Review-BMAD's prior emission; one from surface_failed_layers' new
    emission against the union). This helper collapses them to one.
    Determinism per Epic 1 retro Action #2.
    """
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for finding in findings:
        key = (str(finding.get("source", "")), str(finding.get("id", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return sorted(
        deduped,
        key=lambda f: (str(f.get("source", "")), str(f.get("id", ""))),
    )
