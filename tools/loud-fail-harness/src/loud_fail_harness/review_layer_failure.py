"""Review-BMAD per-layer failure three-channel atomic emission (Story 3.3).

Architectural placement (story 1.10a + story 1.10b precedent — story 2.6's
``specialist_dispatch.py`` Dev Notes "substrate-shared library NOT a sixth
substrate component"; story 2.11's ``bundle_assembly.py``): this module is
a **substrate library NOT a sixth substrate component**. ADR-003
Consequence 1 enumerates exactly five substrate components
(architecture.md lines 311-315); this module is a substrate **library**
consumed by the Review-BMAD wrapper's envelope post-processing path + the
test fixtures' envelope synthesis paths + future Epic 5 / Epic 6 consumers.

What this library provides:
    * **Single source-of-truth function** :func:`surface_failed_layers`
      — the ONLY emission path for the three-channel projection of a
      per-layer failure (FR28 + FR56). The function's atomicity is
      enforced as a code-structure invariant via the AC-9 CI lint
      :mod:`loud_fail_harness.review_layer_failure_emission_gate`;
      no developer can emit one channel without the other two.

The three-channel atomic emission contract (Story 3.3 AC-1):

    1. **Channel 1 — `failed_layers` envelope field (orchestrator surface)**.
       Always present by wrapper discipline (Story 3.1 wrapper.md line 53);
       sorted alphabetically. The `[]` empty-list invariant for the
       zero-failure path is the wrapper's pre-existing commitment; this
       function preserves it.

    2. **Channel 2 — `review-layer-failed` marker (tooling surface)**.
       One marker emission record per failed layer; each emission is
       validated via :func:`loud_fail_harness.specialist_dispatch.validate_marker_emission`
       against the runtime :class:`MarkerClassRegistry` per Story 2.6's
       pattern. Registry rejection raises :exc:`UnknownMarkerClass`
       per Pattern 5. The marker class identifier is consumed AS-IS
       from ``schemas/marker-taxonomy.yaml`` lines 218-224 (Story 1.4
       enumeration; the diagnostic_pointer text already anticipates
       THIS story).

    3. **Channel 3 — synthetic `decision_needed: HIGH` finding (human
       reviewer surface)**. One synthetic finding per failed layer
       appended to the envelope's ``findings`` array; each finding
       carries ``bucket: decision_needed``, ``severity: HIGH``,
       ``meta: review-completeness`` (the wrapper-layer-only
       discriminator added to ``$defs/finding`` at Story 3.3 AC-2;
       see ``docs/extension-audit.md`` per-convention table for the
       BMAD-extension event record). The ``meta`` discriminator is
       what Story 3.4's PR-bundle review-section rendering filters
       on to visually distinguish wrapper-generated meta-findings
       from layer-produced content findings (epics.md line 1729).

The atomicity invariant — the three projections MUST agree by
construction; mismatch is a contract violation Epic 6 / Story 6.1
surfaces as a cross-channel reconciliation gate. The atomicity is
enforced as a CODE-STRUCTURE invariant (a single source-of-truth
function is the only emission path; a CI lint scans for forbidden
direct mutations of any of the three channels outside this function),
NOT a per-bundle reconciliation gate. This is the SAME pattern
Story 2.2 applied to atomic-write: NFR-R8 ("write-ordering invariant")
is enforced by the API shape of :func:`RunStateAtomicWriter.write`,
not by developer discipline.

Contract anchors:
    FR27, FR28, FR52, FR56, FR62, NFR-R8, ADR-002, ADR-003,
    Pattern 1 (snake_case fields; kebab-case identifier values),
    Pattern 2 (marker class naming),
    Pattern 4 (state-update discipline — envelope mutated in-place),
    Pattern 5 (loud-fail doctrine — registry rejection raises rather
               than silently coercing).

Cross-references:
    * Story 1.4 ``schemas/marker-taxonomy.yaml`` lines 218-224 —
      ``review-layer-failed`` marker class identity (consumed AS-IS).
    * Story 2.6 :mod:`loud_fail_harness.specialist_dispatch` —
      :class:`MarkerClassRegistry`, :func:`validate_marker_emission`,
      :exc:`UnknownMarkerClass`.
    * Story 3.1 ``agents/review-bmad-wrapper.md`` — the
      ``failed_layers`` envelope field's wrapper-side declaration
      discipline ("always present by wrapper discipline, even when
      empty `[]`" — wrapper.md line 53).
    * Story 3.2 ``docs/extension-audit.md`` "Finding-taxonomy bumps —
      the no-introductions principle" subsection — the operational
      policy this story exercises as its first worked instance.
    * Story 3.4 — downstream consumer of the ``meta:
      review-completeness`` discriminator for PR-bundle review-section
      rendering.
    * Epic 6 / Story 6.1 — downstream cross-channel reconciliation
      gate that asserts the three projections agree.

FR62 pluggability classification:
    This module is *substrate-shared library* per Story 1.10b's
    precedent. The FR62 pluggability gate at
    :mod:`loud_fail_harness.pluggability_gate` scans ``agents/*.md``
    only; the substrate at ``tools/loud-fail-harness/`` is OUTSIDE
    the gate's scope by construction. Sibling specialists (Dev, QA,
    LAD) are referenced ONLY by HUMAN-READABLE prose names if at all;
    this module references no specialist by slug or path.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)


#: The marker class identifier emitted at channel 2 (Story 1.4 enumeration;
#: ``schemas/marker-taxonomy.yaml`` lines 218-224). Consumed AS-IS; THIS
#: module is the FIRST runtime emitter of the marker for the per-layer
#: failure surface.
REVIEW_LAYER_FAILED_MARKER: str = "review-layer-failed"

#: The wrapper-layer-only discriminator value carried on synthetic
#: meta-findings emitted at channel 3. Sourced from the AC-2 schema bump
#: at ``schemas/envelope.schema.yaml`` ``$defs/finding.properties.meta``
#: enum. Story 3.4's PR-bundle review-section rendering filters on this
#: value to distinguish wrapper-generated meta-findings from layer-produced
#: content findings (epics.md line 1729).
META_REVIEW_COMPLETENESS: str = "review-completeness"


@dataclasses.dataclass(frozen=True)
class MarkerEmissionRecord:
    """One marker-emission record per failed layer (channel 2 surface).

    Frozen for determinism + hashability per Epic 1 retro Action #2.

    Field semantics:
        * ``marker_class`` — the canonical marker class identifier from
          ``schemas/marker-taxonomy.yaml`` (always
          ``"review-layer-failed"`` at this story's scope).
        * ``failed_layer`` — the per-layer identifier (one of
          ``{"blind", "edge", "auditor", "lad"}`` per the schema's
          ``failed_layers`` enum at ``envelope.schema.yaml`` lines
          92-97). Carried as a structured payload field on the marker
          emission record without modifying ``marker-taxonomy.yaml``'s
          ``sub_classifications`` list — the AC-1 "carries the
          failed-layer identifier(s)" language at epics.md line 1692
          names the rendered-bundle convention, not the taxonomy-yaml
          ``sub_classifications`` enum.
    """

    marker_class: str
    failed_layer: str


def _build_synthetic_finding(failed_layer: str) -> dict[str, Any]:
    """Construct one synthetic ``decision_needed: HIGH`` finding for a
    failed review layer (channel 3 surface).

    The synthetic finding represents a wrapper-level synthesis of the
    failure (not a layer-attributed observation), so ``source: merged``
    is chosen from the schema's ``$defs/finding.source`` enum at
    ``envelope.schema.yaml`` line 117 — the ``merged`` value is also
    used by ``bmad-code-review``'s ``step-03-triage.md`` step 2 when
    cross-layer dedup merges findings from two or more layers; the
    semantic alignment is intentional. The ``meta: review-completeness``
    discriminator is what downstream tooling filters on (Story 3.4 +
    the future ``verification_mode`` precedent at epics.md line 2068).
    """
    return {
        "id": f"review-layer-failed-{failed_layer}",
        "source": "merged",
        "title": f"Review layer `{failed_layer}` failed; review findings are incomplete",
        "detail": (
            f"Review layer `{failed_layer}` did not reach a verdict "
            f"(structural failure: crash / timeout / non-zero exit per "
            f"FR28 graceful degradation). The reviewer must decide whether "
            f"to proceed with the partial review or trigger a re-run; "
            f"orchestrator-side flow policy (Epic 5 / Story 5.2) routes "
            f"this finding's `decision_needed` bucket per FR27."
        ),
        "location": f"agents/review-bmad-wrapper.md:failed_layer={failed_layer}",
        "bucket": "decision_needed",
        "severity": "HIGH",
        "meta": META_REVIEW_COMPLETENESS,
    }


def surface_failed_layers(
    envelope: dict[str, Any],
    layer_ids: list[str] | tuple[str, ...] | frozenset[str] | set[str],
    registry: MarkerClassRegistry,
) -> tuple[MarkerEmissionRecord, ...]:
    """Surface a per-layer failure across all THREE channels atomically.

    THIS function is the SINGLE source-of-truth emission path for the
    three-channel projection of a per-layer review failure (FR28 +
    FR56). The atomicity is enforced as a code-structure invariant
    via the AC-9 CI lint
    :mod:`loud_fail_harness.review_layer_failure_emission_gate`.
    No other code path in the harness source tree or in the
    ``agents/review-bmad-wrapper.md`` agent definition is permitted
    to: assign ``failed_layers`` directly; emit the
    ``review-layer-failed`` marker string literal; or append a
    finding carrying ``meta: review-completeness``.

    Behavior:
        * **Channel 1 (envelope field)** — mutates ``envelope`` in
          place to set ``envelope["failed_layers"] = sorted(layer_ids)``
          (alphabetical sort; deterministic ordering across calls).
          The list is normalized via ``sorted(set(layer_ids))`` so
          duplicate inputs collapse and order is canonical.
        * **Channel 2 (marker emission)** — for each failed layer,
          calls :func:`validate_marker_emission` against ``registry``
          (per-layer call; the AC-1 "exactly once per failed layer"
          invariant is the AC-9 CI lint's structural target). On
          success, appends one :class:`MarkerEmissionRecord` to the
          returned tuple carrying ``marker_class="review-layer-failed"``
          + ``failed_layer=<layer_id>``. On registry rejection
          :exc:`UnknownMarkerClass` propagates per Pattern 5; the
          envelope is left **completely unmodified** — all per-layer
          validations are performed first; the envelope is mutated
          only after every validation passes (true atomicity: channels
          1, 2, and 3 are all uncommitted until the full loop
          succeeds).
        * **Channel 3 (synthetic finding)** — for each failed layer,
          appends one synthetic finding to ``envelope["findings"]``
          (initialized to ``[]`` if absent) carrying
          ``bucket: decision_needed``, ``severity: HIGH``,
          ``meta: review-completeness``, ``source: merged``,
          ``id: review-layer-failed-<layer_id>``, plus ``title``,
          ``detail``, and ``location`` naming the failed layer + the
          next-action consequence.

    Zero-failure path (``layer_ids`` empty): channel 1 sets
    ``failed_layers = []``; channels 2 + 3 are silent (no marker
    emission record produced; no synthetic finding appended;
    ``envelope["findings"]`` is unmodified). The empty-list invariant
    on channel 1 is preserved per Story 3.1's wrapper discipline.

    Args:
        envelope: The Review-BMAD envelope dict, mutated IN PLACE.
            Must already conform structurally to
            ``schemas/envelope.schema.yaml`` BEFORE this call (the
            wrapper's prior fields ``status`` / ``artifacts`` /
            ``rationale`` must be set; ``findings`` may be missing or
            ``[]``). Post-call, the envelope still validates against
            the schema (the synthetic finding's ``meta:
            review-completeness`` value survives the AC-2 schema bump).
        layer_ids: The set of failed layer identifiers (each from
            ``{"blind", "edge", "auditor", "lad"}`` per the schema's
            ``failed_layers`` enum). Accepted as any iterable; sorted
            + de-duplicated internally. Empty input triggers the
            zero-failure silent path.
        registry: The runtime :class:`MarkerClassRegistry` from
            :func:`load_marker_class_registry`; must contain the
            ``review-layer-failed`` marker class (verified by Story 1.4's
            enumeration). Registry rejection raises
            :exc:`UnknownMarkerClass`.

    Returns:
        Tuple of :class:`MarkerEmissionRecord` instances, one per
        failed layer (in the same alphabetical order as
        ``envelope["failed_layers"]``). Empty tuple for the
        zero-failure path. The tuple is the bundle assembler's input
        for rendering ``<!-- review-layer-failed: <layer> -->``
        comments (per Story 3.3 AC-4 +
        :mod:`loud_fail_harness.bundle_assembly`).

    Raises:
        :exc:`UnknownMarkerClass`: registry does not contain
        ``"review-layer-failed"``. Pattern 5 named-invariant
        diagnostic; the substrate seam's existing exception type.
    """
    sorted_layers = sorted(set(layer_ids))

    if not sorted_layers:
        envelope["failed_layers"] = sorted_layers
        return ()

    # Validate all marker emissions BEFORE mutating the envelope.
    # True atomicity: if any validate_marker_emission raises
    # UnknownMarkerClass the envelope is left completely unmodified —
    # channels 1, 2, and 3 all uncommitted. Mirrors Story 2.2's
    # atomic-write pattern (NFR-R8 enforced by API shape).
    emissions: list[MarkerEmissionRecord] = []
    new_findings: list[dict[str, Any]] = []
    for failed_layer in sorted_layers:
        validate_marker_emission(registry, REVIEW_LAYER_FAILED_MARKER)
        emissions.append(
            MarkerEmissionRecord(
                marker_class=REVIEW_LAYER_FAILED_MARKER,
                failed_layer=failed_layer,
            )
        )
        new_findings.append(_build_synthetic_finding(failed_layer))

    # All validations passed — mutate the envelope atomically.
    envelope["failed_layers"] = sorted_layers  # channel 1
    envelope.setdefault("findings", []).extend(new_findings)  # channel 3

    return tuple(emissions)  # channel 2: marker records for bundle assembler


__all__ = [
    "REVIEW_LAYER_FAILED_MARKER",
    "META_REVIEW_COMPLETENESS",
    "MarkerEmissionRecord",
    "surface_failed_layers",
]
