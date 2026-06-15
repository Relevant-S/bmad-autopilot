"""QA per-run plan re-derivation cross-check — FR-P2-9 (Story 20.1).

An **independent, read-only cross-check** layered on top of Story 4.2's
AC-hash :mod:`loud_fail_harness.qa_plan_drift`. The two are orthogonal
drift surfaces:

    * **FR23 / ``plan-drift-detected`` (Story 4.2):** the **AC text**
      changed (``compute_ac_hash`` diverges). Triggers the
      ``drift-suspected`` branch → ``plan_status`` reset + plan
      regeneration. That channel is left FULLY intact; FR-P2-9 is
      additive only.
    * **FR-P2-9 / ``plan-rederivation-drift-detected`` (this module):**
      the **plan content** drifted even though the AC text — and thus
      ``ac_hash`` — is unchanged, i.e. on the ``reuse-existing`` path.
      The persisted plan was authored under one qa-runbook / derivation
      state; if re-deriving from current state yields different content
      at a named surface, that is re-derivation drift.

Critical structural fact (see :mod:`loud_fail_harness.qa_behavioral_plan`
module docstring "Flow-branch enumeration" + ``compute_ac_hash``):
``compute_ac_hash`` hashes ONLY AC text (``AcEntry.ac_text``). The per-AC
plan-content fields — ``heuristic_applicability``, ``flow_branches``,
``semantic_verification_requirement``, ``expected_evidence_tier`` — are
deliberately OUT of the hash. That is precisely why those fields are the
FR-P2-9 drift surfaces: a change to them is invisible to FR23 and is the
gap FR-P2-9 closes.

Drift-surface mapping (AC-2) — exactly the per-AC content fields
``compute_ac_hash`` EXCLUDES (``ac_hash`` and ``assertion_shape`` are
AC-text-derived; comparing them would double-count AC-hash drift):

    +----------------------------------+-------------------------------------------+
    | Drift surface (this module)      | ``QABehavioralPlanEntry`` field(s)        |
    +==================================+===========================================+
    | ``heuristic_applicability``      | ``heuristic_applicability``               |
    | ``flow_branches``                | ``flow_branches``                         |
    | ``semantic_verification_tier``   | ``semantic_verification_requirement`` +   |
    |                                  | ``expected_evidence_tier`` (the pair)     |
    +----------------------------------+-------------------------------------------+

Architectural placement (parallel to Story 4.2's
:mod:`loud_fail_harness.qa_plan_drift`): a **substrate library NOT a
sixth substrate component**. ADR-003 enumerates exactly five substrate
components; THIS module is a pure-library sibling consumed by the QA
wrapper's ``reuse-existing`` branch (``agents/qa.md``) + the bundle
assembler's QA-section render. The new module holds FOUR/THREE/FIVE
(specialists / hooks / components) unchanged.

Re-derivation ownership (design decision):
    The library owns the **comparison + marker emission**, NOT the
    re-derivation itself — exactly as
    :func:`loud_fail_harness.qa_plan_drift.surface_plan_drift` owns the
    hash comparison while the wrapper supplies the inputs. The wrapper
    (``agents/qa.md``) produces the re-derived :class:`QABehavioralPlan`
    from current AC + qa-runbook state (the same content-authoring it
    does on ``write-new``); the library cross-checks the persisted vs
    re-derived plans. This keeps the LLM-authored content derivation in
    the wrapper (sensor) and the deterministic structural comparison +
    loud-fail emission in the testable substrate.

Scoped to the ``reuse-existing`` path (``ac_hash`` equal) so a mismatch
is necessarily "beyond AC-hash drift" (AC-2). Frozen Pydantic v2 models
compare structurally with ``==`` (confirmed current Pydantic 2.13.3) —
the tuples / scalars are diffed directly.

Sensor-not-advisor (PRD-level invariant + Pattern 5):
    The library RETURNS the cross-check result (+ the marker record on
    drift); it does NOT write the story doc (AC-3 — re-derivation never
    silently overwrites the persisted plan; FR23's ``plan_status`` reset
    remains the ONLY trigger for plan refresh), does NOT emit markers to
    the event log (the marker record is data the wrapper consumes), does
    NOT log, does NOT print. Same posture as Stories 4.1 / 4.2.

Atomic-on-failure (Pattern 5):
    :func:`validate_marker_emission(registry, MARKER)` runs FIRST — on
    EVERY cross-check, green or drift — so a registry that cannot support
    the marker fails loud with :exc:`UnknownMarkerClass` before any drift
    state is constructed.

Downstream-consumer linkage:
    :mod:`loud_fail_harness.bundle_assembly`'s QA-section render surfaces
    the ``plan_rederivation`` envelope field as a ``FR-P2-9 cross-check:
    green`` / ``… drift detected`` line co-located with the retained
    FR25 ``render_compromise_blockquote`` note (AC-5: retain-and-accompany,
    NOT remove), plus a ``### Plan re-derivation drift detected`` H3
    sub-section + the structured marker comment
    ``<!-- bmad-automation:marker plan-rederivation-drift-detected -->``
    when ``cross_check_status == "drift-detected"``.

Cross-component reuse posture:
    * Pydantic v2 — REUSED (already pinned). No new runtime dependency.
    * :mod:`loud_fail_harness.qa_behavioral_plan` — REUSED for the
      :class:`QABehavioralPlan` / :class:`QABehavioralPlanEntry` shapes.
    * :mod:`loud_fail_harness.specialist_dispatch` — REUSED for
      :class:`MarkerClassRegistry` + :func:`validate_marker_emission`.
    * :mod:`loud_fail_harness.input_hardening` — REUSED for
      :func:`harden_identifier` on ``story_id``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loud_fail_harness.input_hardening import harden_identifier
from loud_fail_harness.qa_behavioral_plan import QABehavioralPlan
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

#: The marker class identifier emitted on the drift branch. Consumed AS-IS
#: from ``schemas/marker-taxonomy.yaml``; THIS module is its FIRST runtime
#: emitter. Mirrors Story 4.2's ``PLAN_DRIFT_DETECTED_MARKER`` constant.
PLAN_REDERIVATION_DRIFT_DETECTED_MARKER: str = "plan-rederivation-drift-detected"

#: The three drift surfaces cross-checked per AC (AC-2). The third value,
#: ``semantic_verification_tier``, represents the
#: (``semantic_verification_requirement``, ``expected_evidence_tier``) pair
#: — both are AC-text-independent semantic-tier content, flagged together
#: when either differs. Interpolated into the marker's ``diagnostic_pointer``
#: via the taxonomy's ``pointer_context_fields: [drift_surfaces]``.
PlanRederivationDriftSurface = Literal[
    "heuristic_applicability",
    "flow_branches",
    "semantic_verification_tier",
]

#: Canonical surface order for deterministic, byte-stable ``drift_surfaces``
#: output (frozen-model field order is load-bearing; so is this).
_SURFACE_ORDER: tuple[PlanRederivationDriftSurface, ...] = (
    "heuristic_applicability",
    "flow_branches",
    "semantic_verification_tier",
)


class PlanRederivationDiagnosticContext(BaseModel):
    """The diagnostic context carried on the
    ``plan-rederivation-drift-detected`` marker emission AND projected onto
    the QA envelope's optional top-level ``plan_rederivation`` field.

    Field semantics:
        * ``story_id`` — the BMAD story identifier the dispatch is scoped to
          (the raw external-ingress identifier; routed through
          :func:`harden_identifier`).
        * ``drift_surfaces`` — the distinct drift surfaces that differed,
          in canonical order (a non-empty subset of
          :data:`PlanRederivationDriftSurface`). Interpolated into the
          marker's ``diagnostic_pointer``.
        * ``drifted_ac_ids`` — the ``ac_id`` values whose per-AC content
          drifted, in persisted-plan order. These come from
          ``QABehavioralPlanEntry.ac_id`` (an internal parsed-plan boundary,
          not raw external ingress — so NOT hardened here, mirroring
          :class:`loud_fail_harness.qa_plan_drift.PlanDriftDiagnosticContext`
          which hardens only ``story_id``).

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    drift_surfaces: tuple[PlanRederivationDriftSurface, ...] = Field(min_length=1)
    drifted_ac_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> "PlanRederivationDiagnosticContext":
        """Input-hardening (Story 24.2 discipline). The ``min_length=1``
        constraint accepts ``"   "``; route ``story_id`` through the shared
        helper to reject whitespace-only / embedded-newline / null-byte
        values — exactly as ``PlanDriftDiagnosticContext`` does.
        """
        harden_identifier(self.story_id, "PlanRederivationDiagnosticContext.story_id")
        return self


class PlanRederivationEmissionRecord(BaseModel):
    """One marker-emission record for the
    ``plan-rederivation-drift-detected`` channel.

    Frozen for determinism + hashability; field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``marker_class`` — the canonical marker class identifier
          (always ``"plan-rederivation-drift-detected"`` at this scope;
          verified by the :data:`PLAN_REDERIVATION_DRIFT_DETECTED_MARKER`
          symbolic constant).
        * ``diagnostic_context`` — the
          :class:`PlanRederivationDiagnosticContext` carried on the marker.
    """

    model_config = ConfigDict(frozen=True)

    marker_class: str
    diagnostic_context: PlanRederivationDiagnosticContext


class PlanRederivationCrossCheck(BaseModel):
    """The always-returned cross-check verdict of
    :func:`surface_plan_rederivation_cross_check`.

    Returned on EVERY ``reuse-existing`` QA run so the bundle can render
    the green / drift line unconditionally (mirroring the a11y / visual
    ``decide_*`` always-returns-a-verdict precedent).

    Field semantics:
        * ``cross_check_status`` — ``"green"`` when the persisted and
          re-derived plans agree at all three drift surfaces;
          ``"drift-detected"`` on any mismatch beyond AC-hash.
        * ``emission_record`` — the :class:`PlanRederivationEmissionRecord`
          carrying the marker + diagnostic context. Present IFF
          ``cross_check_status == "drift-detected"``; ``None`` on green.

    Envelope projection (the wrapper writes the FLAT
    ``$defs/plan_rederivation`` shape to the envelope's ``plan_rederivation``
    field): ``{cross_check_status}`` on green; on drift additionally
    ``{story_id, drift_surfaces, drifted_ac_ids}`` lifted from
    ``emission_record.diagnostic_context``.

    Frozen for determinism + hashability; the ``status``↔``record``
    coherence (record present iff drift) is enforced by
    :meth:`_check_status_record_coherence`.
    """

    model_config = ConfigDict(frozen=True)

    cross_check_status: Literal["green", "drift-detected"]
    emission_record: PlanRederivationEmissionRecord | None = None

    @model_validator(mode="after")
    def _check_status_record_coherence(self) -> "PlanRederivationCrossCheck":
        if self.cross_check_status == "drift-detected" and self.emission_record is None:
            raise ValueError(
                "drift-detected cross-check requires an emission_record"
            )
        if self.cross_check_status == "green" and self.emission_record is not None:
            raise ValueError("green cross-check must not carry an emission_record")
        return self


def surface_plan_rederivation_cross_check(
    persisted_plan: QABehavioralPlan,
    rederived_plan: QABehavioralPlan,
    story_id: str,
    registry: MarkerClassRegistry,
) -> PlanRederivationCrossCheck:
    """Cross-check the persisted vs re-derived QA Behavioral Plan at the
    three non-AC-hash drift surfaces; surface drift on any mismatch.

    THIS function is the single source-of-truth comparison path for
    FR-P2-9. Pure: no file I/O, no story-doc reads or writes (AC-3), no
    marker emission to event logs (the marker record is data the wrapper
    consumes). Caller scopes the invocation to the ``reuse-existing`` path
    (``ac_hash`` equal) so any mismatch is necessarily "beyond AC-hash
    drift" (AC-2).

    Behavior:
        * **Step 1 — Validate marker emission FIRST** (atomic-on-failure
          per Pattern 5), on green AND drift. Registry rejection raises
          :exc:`UnknownMarkerClass` before any drift state is constructed.
        * **Step 2 — Compare per-AC content**, matching entries by
          ``ac_id``. For each persisted entry with a same-``ac_id``
          re-derived entry, compare the three drift surfaces:
          ``heuristic_applicability`` (tuple), ``flow_branches`` (tuple of
          frozen :class:`FlowBranch`), and the semantic-verification tier
          pair (``semantic_verification_requirement`` +
          ``expected_evidence_tier``). ``ac_hash`` and ``assertion_shape``
          are EXCLUDED (AC-text-derived — FR23's channel).
        * **Step 3 — Return the verdict**. No drift → ``green`` with no
          emission record. Drift → ``drift-detected`` carrying a
          :class:`PlanRederivationEmissionRecord` naming the distinct
          ``drift_surfaces`` + the ``drifted_ac_ids``.

    Args:
        persisted_plan: The plan parsed from the story doc (the
            ``reuse-existing`` upstream output).
        rederived_plan: The plan the wrapper re-authored this run from the
            current AC list + qa-runbook state.
        story_id: The BMAD story identifier (threaded into the diagnostic).
        registry: The runtime :class:`MarkerClassRegistry`; must contain
            ``plan-rederivation-drift-detected``. Rejection raises
            :exc:`UnknownMarkerClass`.

    Returns:
        :class:`PlanRederivationCrossCheck` — always; ``green`` or
        ``drift-detected``.

    Raises:
        :exc:`UnknownMarkerClass`: registry does not contain
        ``"plan-rederivation-drift-detected"``.
    """
    validate_marker_emission(registry, PLAN_REDERIVATION_DRIFT_DETECTED_MARKER)

    rederived_by_id = {entry.ac_id: entry for entry in rederived_plan.entries}

    surfaces_seen: set[PlanRederivationDriftSurface] = set()
    drifted_ac_ids: list[str] = []
    for persisted in persisted_plan.entries:
        rederived = rederived_by_id.get(persisted.ac_id)
        if rederived is None:
            continue
        ac_surfaces: set[PlanRederivationDriftSurface] = set()
        if persisted.heuristic_applicability != rederived.heuristic_applicability:
            ac_surfaces.add("heuristic_applicability")
        if persisted.flow_branches != rederived.flow_branches:
            ac_surfaces.add("flow_branches")
        if (
            persisted.semantic_verification_requirement,
            persisted.expected_evidence_tier,
        ) != (
            rederived.semantic_verification_requirement,
            rederived.expected_evidence_tier,
        ):
            ac_surfaces.add("semantic_verification_tier")
        if ac_surfaces:
            surfaces_seen |= ac_surfaces
            drifted_ac_ids.append(persisted.ac_id)

    if not surfaces_seen:
        return PlanRederivationCrossCheck(cross_check_status="green")

    drift_surfaces = tuple(s for s in _SURFACE_ORDER if s in surfaces_seen)
    diagnostic_context = PlanRederivationDiagnosticContext(
        story_id=story_id,
        drift_surfaces=drift_surfaces,
        drifted_ac_ids=tuple(drifted_ac_ids),
    )
    emission_record = PlanRederivationEmissionRecord(
        marker_class=PLAN_REDERIVATION_DRIFT_DETECTED_MARKER,
        diagnostic_context=diagnostic_context,
    )
    return PlanRederivationCrossCheck(
        cross_check_status="drift-detected",
        emission_record=emission_record,
    )


__all__ = [
    "PLAN_REDERIVATION_DRIFT_DETECTED_MARKER",
    "PlanRederivationCrossCheck",
    "PlanRederivationDiagnosticContext",
    "PlanRederivationDriftSurface",
    "PlanRederivationEmissionRecord",
    "surface_plan_rederivation_cross_check",
]
