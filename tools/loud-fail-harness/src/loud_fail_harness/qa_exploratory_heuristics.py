"""Story 4.9 — Three exploratory heuristics + verification_mode discriminator.

The pure-library substrate component owning the three MVP exploratory
heuristic primitives (FR22) AND the ``heuristic-skipped`` marker
emission helper. Composed by Story 4.13's wrapper-thickening procedure
into the QA envelope projection; consumed by the bumped
``$defs/finding.properties.verification_mode`` discriminator field +
the new ``$defs/heuristic_skipped_emission`` envelope shape from
``schemas/envelope.schema.yaml`` (cell-1 architectural core per
ADR-002).

Sources:
    * Verbatim epic AC at ``_bmad-output/planning-artifacts/epics.md``
      lines 2053-2083.
    * PRD FR22 (line 836) — three MVP exploratory heuristics
      (empty-state / error-state / auth-boundary).
    * ADR-002 (architecture.md lines 99-204) — cell-1 architectural
      core; this module is the substrate-side declaration of the
      verification-mode discriminator + heuristic-skipped emission
      primitives consumed by the cell-1 schema.

Pattern 5 (atomic-on-failure) at :func:`surface_heuristic_skipped`
mirrors Story 4.6's :func:`surface_smoke_first_abort` AND Story 4.8's
:func:`surface_tier_3_not_configured` byte-for-byte: the registry is
validated FIRST; on rejection :exc:`UnknownMarkerClass` propagates
with NO partial state constructed.

Cross-story coupling avoidance (mirrors Stories 4.2 / 4.4 / 4.5 / 4.6
/ 4.8): the :data:`HeuristicKind` Literal value set is duplicated
here from ``qa_behavioral_plan.HeuristicApplicability`` rather than
re-imported to avoid the Story-1.x → Story-4.x coupling chain. The
duplication is exercised by the
:mod:`test_qa_exploratory_heuristics` byte-equality contract test.

In-place-thickening linkage (Epic 3 retro Insight #1):
    THIS story does NOT modify ``agents/qa.md`` — Story 4.13 owns
    wrapper thickening completion (composes
    :func:`evaluate_heuristic_applicability`,
    :func:`surface_heuristic_skipped`, and
    :func:`tag_heuristic_finding` into the wrapper's procedural-step
    responsibilities; corrects the forward-pointer prose at
    ``agents/qa.md`` line 41 currently saying "Do NOT execute the
    three exploratory heuristics — Epic 4's Story 4.9 owns the
    heuristics per FR22").
"""

from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness.qa_behavioral_plan import QABehavioralPlan
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

# --------------------------------------------------------------------------- #
# Symbolic constants                                                          #
# --------------------------------------------------------------------------- #

#: The canonical marker class identifier for the heuristic-skipped
#: emission (Story 1.4 enumeration; ``schemas/marker-taxonomy.yaml``
#: line 86). Consumed AS-IS; THIS module is the FIRST runtime emitter.
#: Mirrors Story 4.6's :data:`SMOKE_FIRST_ABORT_MARKER` + Story 4.8's
#: :data:`TIER_3_NOT_CONFIGURED_MARKER` constant pattern.
HEURISTIC_SKIPPED_MARKER: Final[Literal["heuristic-skipped"]] = "heuristic-skipped"

#: The canonical ``verification_mode`` field value from
#: ``envelope.schema.yaml``'s newly-bumped
#: ``$defs/finding.properties.verification_mode.enum``. Mirrors Story
#: 3.3's :data:`META_REVIEW_COMPLETENESS` constant pattern at
#: ``review_layer_failure.py`` line 121.
EXPLORATORY_HEURISTIC_VERIFICATION_MODE: Final[Literal["exploratory-heuristic"]] = (
    "exploratory-heuristic"
)

# --------------------------------------------------------------------------- #
# Type aliases                                                                #
# --------------------------------------------------------------------------- #

#: The closed three-heuristic enumeration. Mirrors
#: ``qa_behavioral_plan.HeuristicApplicability`` at line 164
#: byte-for-byte (intentional duplication to avoid cross-module
#: coupling per the Stories 4.6 / 4.8 cross-story-coupling-avoidance
#: posture; a contract test asserts byte-equality of the literal value
#: sets).
HeuristicKind = Literal["empty-state", "error-state", "auth-boundary"]

#: The closed enum mirroring the schema's
#: ``$defs/finding.properties.verification_mode.enum`` byte-for-byte.
VerificationMode = Literal["exploratory-heuristic"]

# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class HeuristicSkippedDiagnosticContext(BaseModel):
    """The two-field diagnostic context carried on the
    ``heuristic-skipped`` marker emission (per FR22).

    Field semantics (verbatim from the epic AC at ``epics.md`` lines
    2071-2074):
        * ``story_id`` — the BMAD story identifier the dispatch is
          scoped to.
        * ``heuristic_kind`` — names the structurally-skipped
          heuristic (one of ``empty-state | error-state |
          auth-boundary``).

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    heuristic_kind: HeuristicKind


class HeuristicSkippedEmissionRecord(BaseModel):
    """One marker-emission record for the ``heuristic-skipped`` channel.

    Local to Story 4.9 — NOT a reuse of Story 4.6's
    :class:`SmokeFirstAbortEmissionRecord` or Story 4.8's
    :class:`Tier3NotConfiguredEmissionRecord` per the cross-story-
    coupling-avoidance posture (different diagnostic shape, different
    remediation surface).

    Frozen for determinism + hashability. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``marker_class`` — the canonical marker class identifier
          (always ``"heuristic-skipped"`` at this story's scope;
          verified by the :data:`HEURISTIC_SKIPPED_MARKER` symbolic
          constant).
        * ``sub_classification`` — the structured marker
          sub-classification naming the inapplicable heuristic;
          consumed by the bundle assembler to render the marker
          comment (separate from the diagnostic context's
          ``heuristic_kind`` for orthogonal-purpose-clarity).
        * ``diagnostic_context`` — the two-field
          :class:`HeuristicSkippedDiagnosticContext` carried on the
          marker emission.
    """

    model_config = ConfigDict(frozen=True)

    marker_class: Literal["heuristic-skipped"]
    sub_classification: HeuristicKind
    diagnostic_context: HeuristicSkippedDiagnosticContext


class HeuristicSkippedEmission(BaseModel):
    """The atomic-emission return shape of
    :func:`surface_heuristic_skipped`.

    Mirrors Story 4.6's :class:`SmokeFirstAbortEmission` + Story 4.8's
    :class:`Tier3NotConfiguredEmission` co-exposure pattern: the
    ``diagnostic_context`` is co-exposed alongside the
    ``marker_record`` for ergonomic access without unwrapping the
    record.

    Frozen for determinism + hashability. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    marker_record: HeuristicSkippedEmissionRecord
    diagnostic_context: HeuristicSkippedDiagnosticContext


# --------------------------------------------------------------------------- #
# Emission helpers + decision functions                                       #
# --------------------------------------------------------------------------- #


def surface_heuristic_skipped(
    story_id: str,
    heuristic_kind: HeuristicKind,
    registry: MarkerClassRegistry,
) -> HeuristicSkippedEmission:
    """Atomic-on-failure ``heuristic-skipped`` emission helper.

    Mirrors Story 4.6's :func:`surface_smoke_first_abort` + Story 4.8's
    :func:`surface_tier_3_not_configured` Pattern-5 atomic-on-failure
    structure byte-for-byte: :func:`validate_marker_emission` runs
    FIRST; on registry rejection :exc:`UnknownMarkerClass` propagates
    UNCHANGED per Pattern 5 BEFORE any partial state is constructed.

    Behavior:
        * **Step 1 — Validate marker emission FIRST**. Calls
          :func:`validate_marker_emission(registry,
          HEURISTIC_SKIPPED_MARKER)`. On registry rejection
          :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
          propagates per Pattern 5; NO partial state is constructed
          (atomic-on-failure).
        * **Step 2 — Construct the diagnostic context** carrying
          ``story_id`` + ``heuristic_kind``.
        * **Step 3 — Construct the marker emission record** carrying
          the canonical marker class string ``"heuristic-skipped"`` +
          the matching ``sub_classification`` + the diagnostic
          context.
        * **Step 4 — Return the** :class:`HeuristicSkippedEmission`
          carrying both the marker record + the (co-exposed)
          diagnostic context.

    Pure: no file I/O, no story-doc reads or writes, no marker
    emission to the orchestrator-event log (the
    :class:`HeuristicSkippedEmissionRecord` is data the wrapper
    consumes; the structured bundle-comment marker is rendered by the
    bundle assembler when reading the envelope's heuristic-skipped
    emissions list).

    Args:
        story_id: The BMAD story identifier; threaded into the
            diagnostic context.
        heuristic_kind: The structurally-skipped heuristic kind.
        registry: The runtime
            :class:`loud_fail_harness.specialist_dispatch.MarkerClassRegistry`;
            must contain the ``heuristic-skipped`` marker class.
            Registry rejection raises :exc:`UnknownMarkerClass`.

    Returns:
        :class:`HeuristicSkippedEmission` carrying ``marker_record``
        + ``diagnostic_context``.

    Raises:
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
            registry does not contain ``"heuristic-skipped"``.
    """
    validate_marker_emission(registry, HEURISTIC_SKIPPED_MARKER)

    diagnostic_context = HeuristicSkippedDiagnosticContext(
        story_id=story_id,
        heuristic_kind=heuristic_kind,
    )
    marker_record = HeuristicSkippedEmissionRecord(
        marker_class=HEURISTIC_SKIPPED_MARKER,
        sub_classification=heuristic_kind,
        diagnostic_context=diagnostic_context,
    )
    return HeuristicSkippedEmission(
        marker_record=marker_record,
        diagnostic_context=diagnostic_context,
    )


def tag_heuristic_finding(finding: dict[str, Any]) -> dict[str, Any]:
    """Stamp the ``verification_mode: "exploratory-heuristic"``
    discriminator on a finding dict.

    Pure helper: returns a NEW shallow-copy dict; the input is NOT
    mutated. The caller is responsible for ensuring the input
    finding's other fields conform to ``$defs/finding`` shape (the
    function does NOT validate the input — that is the envelope-
    validator's job at the seam). Mirrors
    ``review_layer_failure._build_synthetic_finding`` discipline.

    The function asserts (via Python ``assert``) that the input dict
    does NOT already carry ``verification_mode`` (defense against
    double-tagging). The precondition is a code-correctness
    invariant, not a runtime-data invariant — callers compose this
    function exactly once per finding by construction.

    Args:
        finding: The input finding dict; not mutated.

    Returns:
        A new dict carrying every original key plus
        ``verification_mode: "exploratory-heuristic"``.
    """
    assert "verification_mode" not in finding, (
        "tag_heuristic_finding precondition: finding must not already carry "
        "`verification_mode` (double-tagging guard)"
    )
    return {**finding, "verification_mode": EXPLORATORY_HEURISTIC_VERIFICATION_MODE}


def evaluate_heuristic_applicability(
    plan: QABehavioralPlan,
    heuristic_kind: HeuristicKind,
) -> bool:
    """Return ``True`` iff ANY plan entry's ``heuristic_applicability``
    tuple contains ``heuristic_kind``.

    Behavior per the verbatim epic AC at ``epics.md`` lines 2071-2074:
    a heuristic is applicable to the story when at least one AC's
    plan entry declares the heuristic as in-scope; the heuristic is
    structurally inapplicable (and thus emits
    ``heuristic-skipped: <kind>``) when NO AC declares it.

    Reads ONLY ``plan.entries[*].heuristic_applicability`` — never
    AC text, never driver state, never any other input (FR16
    invariant; the heuristic-applicability decision is plan-driven,
    not raw-AC-driven). Pure: no file I/O.

    Args:
        plan: The QA Behavioral Plan.
        heuristic_kind: The heuristic kind to check applicability for.

    Returns:
        ``True`` iff at least one plan entry declares
        ``heuristic_kind`` in its ``heuristic_applicability`` tuple.
    """
    return any(
        heuristic_kind in entry.heuristic_applicability
        for entry in plan.entries
    )


__all__ = (
    "EXPLORATORY_HEURISTIC_VERIFICATION_MODE",
    "HEURISTIC_SKIPPED_MARKER",
    "HeuristicKind",
    "HeuristicSkippedDiagnosticContext",
    "HeuristicSkippedEmission",
    "HeuristicSkippedEmissionRecord",
    "VerificationMode",
    "evaluate_heuristic_applicability",
    "surface_heuristic_skipped",
    "tag_heuristic_finding",
)
