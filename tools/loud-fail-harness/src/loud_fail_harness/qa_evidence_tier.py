"""Story 4.8 — Three-tier evidence hierarchy + Tier-3 not_configured marker.

The pure-library substrate component owning the three-tier evidence
primitives (FR20 + FR21) AND the ``Tier-3-not-configured`` marker
emission helper. Composed by Story 4.13's wrapper-thickening
procedure into the QA envelope projection; consumed by the bumped
``$defs/evidence_ref`` + ``$defs/ac_result.semantic_verification``
schema invariants from ``schemas/envelope.schema.yaml`` (cell-1
architectural core per ADR-002).

Sources:
    * Verbatim epic AC at ``_bmad-output/planning-artifacts/epics.md``
      lines 2019-2051.
    * PRD FR20 (line 834) — three-tier evidence hierarchy.
    * PRD FR21 (line 835) — ``semantic_verification: not_configured``
      loud-fail marker when Tier-3 is required but tooling isn't set
      up.
    * PRD FR31 (line 853) — every loud-fail marker carries an
      actionable "how to enable" pointer.
    * ADR-002 (architecture.md lines 99-204) — cell-1 architectural
      core; this module is the substrate-side declaration of the
      tier hierarchy primitives consumed by the cell-1 schema.

Pattern 5 (atomic-on-failure) at :func:`surface_tier_3_not_configured`
mirrors Story 4.6's :func:`surface_smoke_first_abort`
(``qa_ac_iteration.py``) byte-for-byte: the registry is validated
FIRST; on rejection :exc:`UnknownMarkerClass` propagates with NO
partial state constructed.

Cross-story coupling avoidance (mirrors Stories 4.2 / 4.4 / 4.5 /
4.6): the ``EvidenceTier`` Literal value set is duplicated here from
``qa_behavioral_plan.ExpectedEvidenceTier`` rather than re-imported
to avoid the Story-1.x → Story-4.x coupling chain. The duplication
is exercised by the :mod:`test_qa_evidence_tier` byte-equality
contract test (see ``tests/test_qa_evidence_tier.py``).

In-place-thickening linkage (Epic 3 retro Insight #1):
    THIS story does NOT modify ``agents/qa.md`` — Story 4.13 owns
    wrapper thickening completion (composes
    :func:`evaluate_semantic_verification` once per AC after
    ``iterate_acs`` returns; corrects the forward-pointer prose at
    ``agents/qa.md`` line 106 referring to the now-rejected
    ``{tier: 3, status: configured | not_configured}`` object form).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

if TYPE_CHECKING:
    from loud_fail_harness.run_state import RunState

# --------------------------------------------------------------------------- #
# Symbolic constants                                                          #
# --------------------------------------------------------------------------- #

#: The canonical marker class identifier for the Tier-3-not-configured
#: emission (Story 1.4 enumeration; ``schemas/marker-taxonomy.yaml``
#: line 78). Consumed AS-IS; THIS module is the FIRST runtime emitter.
#: Mirrors Story 4.6's :data:`SMOKE_FIRST_ABORT_MARKER` constant
#: pattern at ``qa_ac_iteration.py``.
TIER_3_NOT_CONFIGURED_MARKER: Final[Literal["Tier-3-not-configured"]] = (
    "Tier-3-not-configured"
)

# --------------------------------------------------------------------------- #
# Type aliases                                                                #
# --------------------------------------------------------------------------- #

#: Allowed values for :class:`EvidenceRef.tier` AND for the bumped
#: ``$defs/evidence_ref.tier`` schema enum byte-for-byte. Mirrors
#: ``qa_behavioral_plan.ExpectedEvidenceTier`` (lines 150-152) — the
#: PLAN-side ``expected_evidence_tier`` field. Duplicated here rather
#: than re-imported to avoid Story-1.x ↔ Story-4.x cross-coupling
#: (mirrors the Stories 4.2 / 4.4 / 4.5 / 4.6 cross-story-coupling-
#: avoidance posture).
EvidenceTier = Literal[
    "tier-1-mechanical", "tier-2-outcome", "tier-3-semantic"
]

#: Allowed values for the per-AC ``semantic_verification`` result-side
#: field (verbatim per PRD line 596 + epics.md lines 2036-2047). The
#: result-side field captures what HAPPENED at verification time:
#:   * ``verified`` — Tier-3 ran and passed.
#:   * ``not_configured`` — plan declared Tier-3 required but tooling
#:     isn't set up; emitted alongside the
#:     :data:`TIER_3_NOT_CONFIGURED_MARKER` marker.
#:   * ``not_applicable`` — plan declared Tier-3 N/A, OR plan declared
#:     Tier-3 optional and tooling isn't configured.
#:
#: Distinct from :data:`SemanticVerificationRequirement` which carries
#: the PLAN-side ``required | optional | not_applicable`` (a forward-
#: looking promise the plan makes). "required" is INTENTIONALLY absent
#: from this enum — it is a plan-side value, not a result-side outcome.
SemanticVerificationResult = Literal[
    "verified", "not_configured", "not_applicable"
]

#: Allowed values for the PLAN-side ``semantic_verification_requirement``
#: field. Duplicated from
#: ``qa_behavioral_plan.SemanticVerificationRequirement`` (lines
#: 158-160) for the same cross-story-coupling-avoidance reason as
#: :data:`EvidenceTier`. Consumed by
#: :func:`evaluate_semantic_verification` as the input branching key.
SemanticVerificationRequirement = Literal[
    "required", "optional", "not_applicable"
]

# --------------------------------------------------------------------------- #
# How-to-enable pointer (per FR31 actionable remediation surface)             #
# --------------------------------------------------------------------------- #

#: The verbatim multiline ``diagnostic_pointer`` text for the
#: ``Tier-3-not-configured`` marker class, copied AS-IS from
#: ``schemas/marker-taxonomy.yaml`` lines 80-83. The substrate library
#: does NOT itself read the YAML at runtime — this constant is the
#: canonical compile-time copy. The
#: :mod:`test_qa_evidence_tier` byte-equality freshness test asserts
#: this constant equals the YAML's ``diagnostic_pointer`` field for
#: the ``Tier-3-not-configured`` entry, preventing silent drift.
_HOW_TO_ENABLE_POINTER: Final[str] = (
    "QA Tier-3 (semantic verification) is not configured for {ac_id}.\n"
    "Verification proceeds with Tier-1/Tier-2 evidence only. Remediation:\n"
    "configure semantic verification for {ac_id} per `qa-runbook.yaml` at\n"
    "`<project-root>/_bmad-output/qa-runbook.yaml`, OR accept the lower-tier\n"
    "evidence as sufficient for this AC.\n"
)

# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class EvidenceRef(BaseModel):
    """One evidence-tier-tagged reference carried in
    :class:`AcResult.evidence_refs` (envelope-projection counterpart of
    ``$defs/evidence_ref``).

    The Pydantic-v2 projection's ``model_dump()`` JSON shape mirrors
    ``schemas/envelope.schema.yaml`` ``$defs/evidence_ref`` byte-for-
    byte: ``{path: <str>, tier: <EvidenceTier>}``.

    Frozen for hashability + determinism per Epic 1 retro Action #2.
    Field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.

    Field semantics:
        * ``path`` — repo-relative evidence-path string (≥ 1 char;
          mirrors the schema's ``minLength: 1``). The path SHOULD point
          under ``_bmad-output/qa-evidence/{story-id}/{run-id}/`` per
          FR49 — the convention is wrapper-side, not enforced here.
        * ``tier`` — one of ``tier-1-mechanical``, ``tier-2-outcome``,
          ``tier-3-semantic`` (FR20). Mirrors the schema's
          ``$defs/evidence_ref.tier`` enum byte-for-byte.
    """

    model_config = ConfigDict(frozen=True)

    path: str = Field(min_length=1)
    tier: EvidenceTier


class Tier3NotConfiguredDiagnosticContext(BaseModel):
    """The three-field diagnostic context carried on the
    ``Tier-3-not-configured`` marker emission (per FR31).

    Field semantics (verbatim from the epic AC at ``epics.md`` lines
    2034-2047 + FR31 line 853):
        * ``story_id`` — the BMAD story identifier the dispatch is
          scoped to.
        * ``ac_id`` — the AC identifier whose semantic-verification
          tier was required by the plan but isn't configured.
        * ``how_to_enable_pointer`` — the per-FR31 actionable
          remediation pointer; sourced from
          ``schemas/marker-taxonomy.yaml`` lines 80-83's
          ``diagnostic_pointer`` field (the canonical copy lives at
          :data:`_HOW_TO_ENABLE_POINTER`).

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    ac_id: str = Field(min_length=1)
    how_to_enable_pointer: str = Field(min_length=1)


class Tier3NotConfiguredEmissionRecord(BaseModel):
    """One marker-emission record for the ``Tier-3-not-configured``
    channel.

    Local to Story 4.8 — NOT a reuse of Story 4.6's
    :class:`SmokeFirstAbortEmissionRecord` per the cross-story-coupling-
    avoidance posture (different diagnostic shape, different
    remediation surface).

    Frozen for determinism + hashability. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``marker_class`` — the canonical marker class identifier
          (always ``"Tier-3-not-configured"`` at this story's scope;
          verified by the :data:`TIER_3_NOT_CONFIGURED_MARKER`
          symbolic constant).
        * ``diagnostic_context`` — the three-field
          :class:`Tier3NotConfiguredDiagnosticContext` carried on the
          marker emission. Bundle-assembler consumers (Story 4.13)
          read this field to render the human-readable diagnostic
          sub-section + the actionable how-to-enable pointer.
    """

    model_config = ConfigDict(frozen=True)

    marker_class: Literal["Tier-3-not-configured"]
    diagnostic_context: Tier3NotConfiguredDiagnosticContext


class Tier3NotConfiguredEmission(BaseModel):
    """The atomic-emission return shape of
    :func:`surface_tier_3_not_configured`.

    Mirrors Story 4.6's :class:`SmokeFirstAbortEmission` co-exposure
    pattern at ``qa_ac_iteration.py`` lines 256-285 byte-for-byte (the
    ``diagnostic_context`` is co-exposed alongside the ``marker_record``
    for ergonomic access without unwrapping the record — the equal
    payload object as ``marker_record.diagnostic_context``).

    Frozen for determinism + hashability. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``marker_record`` — the
          :class:`Tier3NotConfiguredEmissionRecord` carrying
          ``marker_class="Tier-3-not-configured"`` + the three-field
          diagnostic context.
        * ``diagnostic_context`` — the three-field
          :class:`Tier3NotConfiguredDiagnosticContext`. Co-exposed for
          ergonomic access (equal payload object as
          ``marker_record.diagnostic_context``).
    """

    model_config = ConfigDict(frozen=True)

    marker_record: Tier3NotConfiguredEmissionRecord
    diagnostic_context: Tier3NotConfiguredDiagnosticContext


class PlanAndConfigForEvaluation(BaseModel):
    """The two inputs to :func:`evaluate_semantic_verification`,
    bundled as a tiny frozen model for ergonomic threading.

    The wrapper-side composition at Story 4.13 reads
    ``tier_3_configured`` from ``qa-runbook.yaml``'s
    ``tier_3_semantic_verification`` field (default
    ``not_configured`` → ``False``). THIS module does NOT read the
    runbook — the substrate is pure-library; the wrapper threads the
    bool from runbook reads done in the LLM-runtime layer.

    Field semantics:
        * ``plan_requirement`` — the PLAN-side
          ``semantic_verification_requirement`` for the AC (one of
          ``required | optional | not_applicable``).
        * ``tier_3_configured`` — the runbook-side flag indicating
          whether semantic-verification tooling is set up for this
          repo.
    """

    model_config = ConfigDict(frozen=True)

    plan_requirement: SemanticVerificationRequirement
    tier_3_configured: bool


# --------------------------------------------------------------------------- #
# Emission helpers + decision function                                        #
# --------------------------------------------------------------------------- #


def surface_tier_3_not_configured(
    story_id: str,
    ac_id: str,
    registry: MarkerClassRegistry,
) -> Tier3NotConfiguredEmission:
    """Atomic-on-failure ``Tier-3-not-configured`` emission helper.

    Mirrors Story 4.6's :func:`surface_smoke_first_abort` Pattern-5
    atomic-on-failure structure byte-for-byte:
    :func:`validate_marker_emission` runs FIRST; on registry rejection
    :exc:`UnknownMarkerClass` propagates UNCHANGED per Pattern 5
    BEFORE any partial state is constructed.

    Behavior:
        * **Step 1 — Validate marker emission FIRST**. Calls
          :func:`validate_marker_emission(registry,
          TIER_3_NOT_CONFIGURED_MARKER)`. On registry rejection
          :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
          propagates per Pattern 5; NO partial state is constructed
          (atomic-on-failure).
        * **Step 2 — Construct the diagnostic context** carrying
          ``story_id`` + ``ac_id`` + ``how_to_enable_pointer`` (sourced
          from :data:`_HOW_TO_ENABLE_POINTER`).
        * **Step 3 — Construct the marker emission record** carrying
          the canonical marker class string ``"Tier-3-not-configured"``
          + the diagnostic context.
        * **Step 4 — Return the** :class:`Tier3NotConfiguredEmission`
          carrying both the marker record + the (co-exposed)
          diagnostic context.

    Pure: no file I/O, no story-doc reads or writes, no marker
    emission to the orchestrator-event log (the
    :class:`Tier3NotConfiguredEmissionRecord` is data the wrapper
    consumes; the structured bundle-comment marker is rendered by the
    bundle assembler when reading the envelope's per-AC tier-3-not-
    configured emission record — Story 4.13 finalizes that rendering
    surface).

    Args:
        story_id: The BMAD story identifier; threaded into the
            diagnostic context.
        ac_id: The AC identifier whose semantic-verification tier was
            required by the plan but isn't configured.
        registry: The runtime
            :class:`loud_fail_harness.specialist_dispatch.MarkerClassRegistry`
            from
            :func:`loud_fail_harness.specialist_dispatch.load_marker_class_registry`;
            must contain the ``Tier-3-not-configured`` marker class
            (verified by Story 1.4's enumeration). Registry rejection
            raises :exc:`UnknownMarkerClass`.

    Returns:
        :class:`Tier3NotConfiguredEmission` carrying ``marker_record``
        + ``diagnostic_context``.

    Raises:
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
            registry does not contain ``"Tier-3-not-configured"``.
            Pattern 5 named-invariant diagnostic; the substrate seam's
            existing exception type.
    """
    validate_marker_emission(registry, TIER_3_NOT_CONFIGURED_MARKER)

    diagnostic_context = Tier3NotConfiguredDiagnosticContext(
        story_id=story_id,
        ac_id=ac_id,
        how_to_enable_pointer=_HOW_TO_ENABLE_POINTER,
    )
    marker_record = Tier3NotConfiguredEmissionRecord(
        marker_class=TIER_3_NOT_CONFIGURED_MARKER,
        diagnostic_context=diagnostic_context,
    )
    return Tier3NotConfiguredEmission(
        marker_record=marker_record,
        diagnostic_context=diagnostic_context,
    )


def evaluate_semantic_verification(
    plan_requirement: SemanticVerificationRequirement,
    tier_3_configured: bool,
    story_id: str,
    ac_id: str,
    registry: MarkerClassRegistry,
) -> tuple[
    SemanticVerificationResult,
    Tier3NotConfiguredEmissionRecord | None,
]:
    """The five-branch semantic-verification decision function (FR20 +
    FR21).

    Branch logic per the verbatim epic AC at ``epics.md`` lines
    2034-2047:

        * ``plan_requirement == "not_applicable"`` →
          ``("not_applicable", None)`` per epics.md line 2047
          ("explicit non-applicability is not a gap"; NO marker).
        * ``plan_requirement == "optional"`` AND ``tier_3_configured``
          → ``("verified", None)`` (Tier-3 ran successfully).
        * ``plan_requirement == "optional"`` AND NOT
          ``tier_3_configured`` → ``("not_applicable", None)``
          (optional-without-config collapses to non-applicability;
          NO marker — optional-without-config is NOT a gap, mirroring
          epics.md line 2047's "explicit non-applicability" doctrine
          extended to the opt-in case).
        * ``plan_requirement == "required"`` AND ``tier_3_configured``
          → ``("verified", None)`` per epics.md line 2042 ("Tier-3
          verification succeeds").
        * ``plan_requirement == "required"`` AND NOT
          ``tier_3_configured`` → calls
          :func:`surface_tier_3_not_configured`; returns
          ``("not_configured", emission.marker_record)`` per
          epics.md lines 2036-2038.

    The function does NOT touch :class:`AcResult.status` — the AC's
    pass/fail is determined by Tier-1+Tier-2 mechanical/outcome
    verification per the verbatim epic AC at line 2038 ("the marker
    signals visibility of the gap, not a failure"). The function
    does NOT itself construct an :class:`AcResult` — that is Story
    4.13's wrapper-thickening surface; THIS module exposes the
    decision data for the wrapper to compose.

    Pure: no file I/O.

    Args:
        plan_requirement: The PLAN-side
            ``semantic_verification_requirement`` for the AC.
        tier_3_configured: The runbook-side flag indicating whether
            semantic-verification tooling is set up for this repo.
        story_id: Threaded into the diagnostic context on the
            ``required + not-configured`` branch.
        ac_id: Threaded into the diagnostic context on the
            ``required + not-configured`` branch.
        registry: The runtime marker-class registry; consumed only
            on the ``required + not-configured`` branch.

    Returns:
        Tuple ``(result, marker_record)``:
            * ``result`` is one of ``"verified" | "not_configured" |
              "not_applicable"`` — the per-AC ``semantic_verification``
              field value the wrapper projects onto the envelope.
            * ``marker_record`` is the
              :class:`Tier3NotConfiguredEmissionRecord` ON the
              ``required + not-configured`` branch only; ``None`` on
              every other branch.

    Raises:
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
            registry does not contain ``"Tier-3-not-configured"``;
            propagates from
            :func:`surface_tier_3_not_configured`. Only reachable on
            the ``required + not-configured`` branch.
    """
    if plan_requirement == "not_applicable":
        return ("not_applicable", None)
    if plan_requirement == "optional":
        if tier_3_configured:
            return ("verified", None)
        return ("not_applicable", None)
    elif plan_requirement == "required":
        if tier_3_configured:
            return ("verified", None)
        emission = surface_tier_3_not_configured(story_id, ac_id, registry)
        return ("not_configured", emission.marker_record)
    else:
        raise ValueError(
            f"Unknown plan_requirement: {plan_requirement!r}; "
            "expected 'not_applicable', 'optional', or 'required'"
        )


def record_tier_3_not_configured_in_run_state(
    *,
    run_state: RunState,
    ac_id: str,
    marker_registry: MarkerClassRegistry | None = None,
) -> RunState:
    """Compose a ``Tier-3-not-configured`` marker into RunState.

    Story 6.7 D-6.2-1 discharge: the orchestrator-side helper that
    populates ``run_state.active_markers`` AND ``run_state.marker_contexts``
    so Story 6.2's ``_interpolate_actionable_pointer`` renders the
    ``{ac_id}`` placeholder verbatim from the taxonomy's
    ``pointer_context_fields: [ac_id]`` declaration.

    Sensor-not-advisor: the orchestrator-skill caller decides WHEN to
    invoke (typically after consuming a
    :class:`Tier3NotConfiguredEmission` from
    :func:`surface_tier_3_not_configured`); this helper just records.

    Pattern 4 batch-write: this helper does NOT call
    :func:`loud_fail_harness.run_state.advance_run_state`. The caller
    composes the returned :class:`RunState` INTO the next-state
    argument it passes to ``advance_run_state``; one atomic write per
    seam transition.

    Composes :func:`loud_fail_harness.marker_wiring.record_marker_with_context`
    via lazy import (avoids the marker_wiring → specialist_dispatch →
    qa_evidence_tier potential indirect cycle at module load time).

    Args:
        run_state: The :class:`RunState` BEFORE the marker append.
        ac_id: The AC identifier whose semantic-verification tier was
            required by the plan but isn't configured. Populates
            ``marker_contexts["Tier-3-not-configured"] = {"ac_id": <value>}``.
        marker_registry: Optional :class:`MarkerClassRegistry` for
            pre-emission validation per Pattern 5.

    Returns:
        A new :class:`RunState` carrying the ``Tier-3-not-configured``
        marker entry + ``marker_contexts["Tier-3-not-configured"]``
        populated; or the input run-state unchanged on de-dup.
    """
    from loud_fail_harness.marker_wiring import record_marker_with_context

    return record_marker_with_context(
        run_state=run_state,
        marker_class=TIER_3_NOT_CONFIGURED_MARKER,
        context={"ac_id": ac_id},
        marker_registry=marker_registry,
    )


__all__ = (
    "EvidenceRef",
    "EvidenceTier",
    "PlanAndConfigForEvaluation",
    "SemanticVerificationRequirement",
    "SemanticVerificationResult",
    "TIER_3_NOT_CONFIGURED_MARKER",
    "Tier3NotConfiguredDiagnosticContext",
    "Tier3NotConfiguredEmission",
    "Tier3NotConfiguredEmissionRecord",
    "evaluate_semantic_verification",
    "record_tier_3_not_configured_in_run_state",
    "surface_tier_3_not_configured",
)
