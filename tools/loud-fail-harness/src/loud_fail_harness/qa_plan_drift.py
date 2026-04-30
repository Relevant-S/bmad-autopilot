"""QA AC-hash plan-drift detection — two-channel atomic emission (Story 4.2).

FR23 + FR16 + Pattern 5. Consumes Story 4.1's ``drift-suspected``
``PlanPersistAction`` token AS-IS without redefining the action enum and
without modifying ``qa_behavioral_plan.py``'s public API.

Architectural placement (parallel to Story 3.3's
:mod:`loud_fail_harness.review_layer_failure`): this module is a
**substrate library NOT a sixth substrate component**. ADR-003 enumerates
exactly five substrate components (architecture.md lines 311-315);
THIS module is a substrate **library** consumed by the QA wrapper's
``drift-suspected`` branch (per ``agents/qa.md`` Procedure step 6) +
the bundle assembler's QA-section render (per Story 4.2 AC-5) + future
Epic 5 / Epic 6 consumers. It is structurally a pure-library sibling of
Story 4.1's :mod:`loud_fail_harness.qa_behavioral_plan`.

Two-channel atomic emission contract (Story 4.2 AC-1):

    1. **Channel 1 — fresh ``QABehavioralPlan`` (story-doc surface)**.
       The plan is regenerated via Story 4.1's
       :func:`loud_fail_harness.qa_behavioral_plan.generate_plan`; the
       returned plan carries ``plan_status="generated"`` per Story 4.1's
       ``generate_plan`` semantics + a fresh ``ac_hash`` matching
       :func:`loud_fail_harness.qa_behavioral_plan.compute_ac_hash` of
       the new ``ac_list`` byte-for-byte. The reset to ``"generated"``
       is **unconditional** — even if the prior plan was
       ``"human-reviewed"`` it returns to ``"generated"`` per the
       verbatim epic AC at ``epics.md`` line 1845.

    2. **Channel 2 — ``plan-drift-detected`` marker (tooling surface)**.
       One :class:`PlanDriftEmissionRecord` carrying
       ``marker_class="plan-drift-detected"`` + the four-field
       diagnostic context per the verbatim epic AC at ``epics.md``
       line 1851 (``story_id``, ``prior_plan_status``,
       ``prior_ac_hash``, ``current_ac_hash``). The marker class
       identifier is consumed AS-IS from
       ``schemas/marker-taxonomy.yaml`` line 114 (Story 1.4
       enumeration; the ``diagnostic_pointer`` text already
       anticipates THIS story).

The atomicity invariant — both projections MUST agree by construction;
mismatch is a contract violation downstream tooling surfaces. The
atomicity is enforced as a CODE-STRUCTURE invariant (a single
source-of-truth function is the only emission path; registry validation
runs FIRST so a rejection raises :exc:`UnknownMarkerClass` per Pattern 5
BEFORE either channel is constructed). Same posture Story 3.3
established for ``surface_failed_layers`` and Story 2.2 applied to
atomic-write (NFR-R8 enforced by API shape, not by developer
discipline).

Marker-class linkage:
    The ``plan-drift-detected`` marker class exists in
    ``schemas/marker-taxonomy.yaml`` from Story 1.4's proactive add (the
    epic-close marker sweep per ``docs/extension-audit.md`` § Epic-close
    marker sweep). THIS module is the FIRST runtime emitter — Story 4.1's
    ``qa_behavioral_plan.py`` returns the ``"drift-suspected"`` action
    token but does NOT emit any marker (the verbatim Story 4.1 commitment
    at ``qa_behavioral_plan.py`` lines 18-21 + lines 137-145).

Upstream-consumer linkage:
    Story 4.1's :mod:`loud_fail_harness.qa_behavioral_plan` is the
    upstream library producing the ``"drift-suspected"`` action token
    from :func:`persist_or_reuse_plan`. The wrapper's
    ``drift-suspected`` branch composes :func:`surface_plan_drift` ON
    TOP of Story 4.1's surface — Story 4.1's ``PlanPersistAction``
    enum is unchanged; Story 4.1's
    :func:`persist_or_reuse_plan` API is unchanged; Story 4.1's
    :func:`compute_ac_hash` + :func:`generate_plan` are composed
    verbatim, not reimplemented.

Downstream-consumer linkage:
    :mod:`loud_fail_harness.bundle_assembly`'s QA-section render
    surfaces the ``plan_drift`` envelope field as an
    ``### Plan drift detected`` H3 sub-section + the structured marker
    comment ``<!-- bmad-automation:marker plan-drift-detected -->``
    co-located. The QA-section render is conditional on
    ``qa_envelope.get("plan_drift")`` being a non-null object; when
    absent or null, ZERO marker comments are rendered (the structural-
    not-era-based emission rule from Story 3.4's architecture.md
    addendum at line 1581 is structurally mirrored here — emit iff the
    field is non-null).

In-place-thickening linkage (Epic 3 retro Insight #1 — second
confirmation site after Story 4.1's first landing):
    ``agents/qa.md`` is the wrapper composing this library. The wrapper's
    Procedure step 6's ``drift-suspected`` branch graduates IN PLACE
    from Story 4.1's regenerate-fresh-with-TODO posture to the
    affirmative "DO" procedural step naming :func:`surface_plan_drift`
    + :func:`validate_marker_emission` + the ``plan_drift`` envelope-
    field write. Same agent identity, same envelope contract — only
    the wrapper's internal coverage thickens.

Structural-not-era-based emission rule:
    The ``plan-drift-detected`` marker emits iff QA's envelope
    ``plan_drift`` field is non-null. Epic 6 / Story 6.1's loud-fail-
    block landing thickens visibility further per the verbatim epic
    AC at ``epics.md`` line 1850 ("Epic 6 thickens visibility further")
    without modifying THIS module's emission code — the same
    structural-not-era-based posture Story 3.4 codified for
    ``walking-skeleton-bundle`` at ``architecture.md`` line 1581.

QA-independence-from-TEA-artifacts invariant (FR16, PRD line 830):
    Drift detection reads ONLY the ``ac_list`` from the dispatch
    payload + the parsed plan from the story doc. Drift detection
    does NOT read TEA test files, dev tests, review findings, or
    commit diffs. The invariant is structurally encoded by the
    function signature: :func:`surface_plan_drift` accepts only
    ``parsed_plan``, ``ac_list``, ``story_id``, and ``registry`` —
    no TEA-artifact channel exists.

Cross-component reuse posture (Story 1.10b precedent):
    * Pydantic v2 :class:`pydantic.BaseModel` + :class:`pydantic.ConfigDict`
      — REUSED (already pinned by stories 1.1 / 1.2 / 1.10b / 4.1).
    * Story 4.1's :mod:`loud_fail_harness.qa_behavioral_plan` —
      REUSED for ``compute_ac_hash`` + ``generate_plan`` + ``PlanStatus``
      + ``QABehavioralPlan`` + ``AcEntry``.
    * Story 2.6's :mod:`loud_fail_harness.specialist_dispatch` —
      REUSED for :class:`MarkerClassRegistry` +
      :func:`validate_marker_emission` + :exc:`UnknownMarkerClass`.
    * No new runtime dependencies. No file I/O. No story-doc reads or
      writes (the wrapper's procedural step is responsible for both).

Procedural checklist (verbatim epic AC at epics.md lines 1842-1856):

    1. ``persist_or_reuse_plan`` returns ``"drift-suspected"`` (Story 4.1
       contract; the upstream-consumer surface).
    2. The wrapper's ``drift-suspected`` branch calls
       :func:`surface_plan_drift` with ``(parsed_plan, ac_list,
       story_id, registry)``.
    3. :func:`surface_plan_drift` validates the marker class against
       the registry FIRST (atomic-on-failure per Pattern 5).
    4. On success, regenerates a fresh plan via
       :func:`loud_fail_harness.qa_behavioral_plan.generate_plan`
       (the regenerated plan carries ``plan_status="generated"`` +
       a fresh ``ac_hash`` matching the current AC list).
    5. Constructs the diagnostic context preserving the prior state
       (``prior_plan_status``, ``prior_ac_hash``).
    6. Constructs the marker emission record carrying the diagnostic.
    7. Returns the :class:`PlanDriftEmission` three-tuple to the
       wrapper.
    8. The wrapper writes the diagnostic context to the QA envelope's
       ``plan_drift`` field; calls
       :func:`loud_fail_harness.story_doc_validator.validate_section_write`
       for ``"## QA Behavioral Plan"``; renders the fresh plan via
       :func:`loud_fail_harness.qa_behavioral_plan.render_plan_section`
       and writes it to the story doc under the H2 header.
    9. The bundle assembler's QA-section render surfaces the
       ``plan_drift`` envelope field as an ``### Plan drift detected``
       H3 sub-section + the structured marker comment.

Sensor-not-advisor (PRD-level invariant + Pattern 5):
    The library RETURNS the fresh plan + the marker record + the
    diagnostic context; it does NOT write to the story doc, does NOT
    emit markers (the marker record is data, not an emission), does
    NOT call :func:`validate_section_write`, does NOT log, does NOT
    print. Same posture as Stories 4.1 / 3.3 / 2.6 / 1.10b.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness.qa_behavioral_plan import (
    AcEntry,
    PlanStatus,
    QABehavioralPlan,
    compute_ac_hash,
    generate_plan,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

#: The marker class identifier emitted at channel 2 (Story 1.4 enumeration;
#: ``schemas/marker-taxonomy.yaml`` line 114). Consumed AS-IS; THIS module
#: is the FIRST runtime emitter of the marker for the AC-hash plan-drift
#: surface. Mirrors Story 3.3's ``REVIEW_LAYER_FAILED_MARKER`` constant
#: pattern at :mod:`loud_fail_harness.review_layer_failure`.
PLAN_DRIFT_DETECTED_MARKER: str = "plan-drift-detected"


class PlanDriftDiagnosticContext(BaseModel):
    """The four-field diagnostic context carried on the
    ``plan-drift-detected`` marker emission AND on the QA envelope's
    optional ``plan_drift`` top-level field (per AC-3's schema bump).

    Field semantics (verbatim epic AC at ``epics.md`` line 1851):
        * ``story_id`` — the BMAD story identifier the dispatch is scoped
          to (mirrors Story 4.1's ``persist_or_reuse_plan`` ``story_id``
          parameter).
        * ``prior_plan_status`` — the parsed plan's ``plan_status`` BEFORE
          drift was detected. One of ``{generated, human-reviewed}`` per
          Story 4.1's ``PlanStatus`` Literal at ``qa_behavioral_plan.py``
          line 170. Preserved in the diagnostic for downstream visibility
          (the reset to ``"generated"`` happens on the fresh plan; the
          diagnostic preserves the prior state).
        * ``prior_ac_hash`` — the parsed plan's ``ac_hash`` BEFORE drift.
          64-char SHA-256 hex digest per Story 4.1's ``compute_ac_hash``
          contract from ``docs/architecture.md`` line 1591.
        * ``current_ac_hash`` — :func:`compute_ac_hash` of the current
          ``ac_list``. 64-char SHA-256 hex digest matching the fresh
          plan's ``ac_hash`` byte-for-byte.

    Frozen for hashability + determinism per Epic 1 retro Action #2 +
    Story 4.1's ``QABehavioralPlan`` discipline. Field declaration order
    is load-bearing for byte-stable ``model_dump_json()`` output (mirrors
    Story 4.1's ``QABehavioralPlanEntry`` + ``QABehavioralPlan``).
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    prior_plan_status: PlanStatus
    prior_ac_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_ac_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PlanDriftEmissionRecord(BaseModel):
    """One marker-emission record for the ``plan-drift-detected`` channel
    (channel 2 surface).

    Local to Story 4.2 — NOT a reuse of Story 3.3's
    :class:`loud_fail_harness.review_layer_failure.MarkerEmissionRecord`
    because the payload shape differs (Story 3.3 carries a single
    ``failed_layer`` string; Story 4.2 carries the four-field diagnostic
    context). Cross-story coupling avoidance — same posture Story 1.10b's
    ``ValidationResult`` took vs reusing Story 1.2's envelope-validation
    shapes.

    Frozen for determinism + hashability. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``marker_class`` — the canonical marker class identifier from
          ``schemas/marker-taxonomy.yaml`` (always
          ``"plan-drift-detected"`` at this story's scope; verified by
          the :data:`PLAN_DRIFT_DETECTED_MARKER` symbolic constant).
        * ``diagnostic_context`` — the four-field
          :class:`PlanDriftDiagnosticContext` carried on the marker
          emission. Bundle-assembler consumers read this field to render
          the human-readable diagnostic sub-section.
    """

    model_config = ConfigDict(frozen=True)

    marker_class: str
    diagnostic_context: PlanDriftDiagnosticContext


class PlanDriftEmission(BaseModel):
    """The two-channel atomic-emission return shape of
    :func:`surface_plan_drift`.

    Channels are paired by construction — both ``fresh_plan`` and
    ``marker_record`` are present on a successful drift detection;
    registry rejection raises :exc:`UnknownMarkerClass` BEFORE either
    is constructed (atomic-on-failure per Pattern 5; mirrors Story 3.3
    AC-7 at :mod:`loud_fail_harness.review_layer_failure` lines 274-289).

    Frozen for determinism + hashability per Epic 1 retro Action #2.
    Field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.

    Field semantics:
        * ``fresh_plan`` — the regenerated :class:`QABehavioralPlan`
          carrying ``plan_status="generated"`` + a fresh ``ac_hash``
          matching :func:`compute_ac_hash` of the current ``ac_list``
          byte-for-byte. The reset to ``"generated"`` is unconditional
          (even on a prior ``"human-reviewed"`` plan, per the verbatim
          epic AC at ``epics.md`` line 1845). The wrapper's
          ``drift-suspected`` branch writes this plan to the story doc
          under the ``## QA Behavioral Plan`` H2 header via
          :func:`loud_fail_harness.story_doc_validator.validate_section_write`
          + :func:`loud_fail_harness.qa_behavioral_plan.render_plan_section`.
        * ``marker_record`` — the :class:`PlanDriftEmissionRecord`
          carrying ``marker_class="plan-drift-detected"`` + the
          four-field diagnostic context. Bundle-assembler consumers
          read the diagnostic to render the
          ``### Plan drift detected`` H3 sub-section.
        * ``diagnostic_context`` — the four-field
          :class:`PlanDriftDiagnosticContext`. Co-exposed for ergonomic
          access without unwrapping ``marker_record`` (same payload
          object as ``marker_record.diagnostic_context``; the wrapper
          writes this to the QA envelope's ``plan_drift`` field per
          AC-3's schema bump).
    """

    model_config = ConfigDict(frozen=True)

    fresh_plan: QABehavioralPlan
    marker_record: PlanDriftEmissionRecord
    diagnostic_context: PlanDriftDiagnosticContext


def surface_plan_drift(
    parsed_plan: QABehavioralPlan,
    ac_list: list[AcEntry] | tuple[AcEntry, ...],
    story_id: str,
    registry: MarkerClassRegistry,
) -> PlanDriftEmission:
    """Surface AC-hash plan drift across both channels atomically.

    THIS function is the SINGLE source-of-truth emission path for the
    two-channel projection of an AC-hash plan drift (FR23). Composes
    Story 4.1's :func:`compute_ac_hash` + :func:`generate_plan` and
    Story 2.6's :func:`validate_marker_emission`. Pure: no file I/O,
    no story-doc reads or writes, no marker emission to event logs
    (the marker record is data the wrapper consumes; it is NOT
    emitted to the orchestrator-event log by this function).

    Behavior:
        * **Step 1 — Validate marker emission FIRST**. Calls
          :func:`validate_marker_emission(registry, PLAN_DRIFT_DETECTED_MARKER)`.
          On registry rejection :exc:`UnknownMarkerClass` propagates
          per Pattern 5; NO partial state is constructed (atomic-on-
          failure; mirrors Story 3.3 AC-7 at
          :mod:`loud_fail_harness.review_layer_failure` lines 274-289).
        * **Step 2 — Compute the current AC hash + regenerate the
          fresh plan** via Story 4.1's
          :func:`loud_fail_harness.qa_behavioral_plan.compute_ac_hash`
          and :func:`loud_fail_harness.qa_behavioral_plan.generate_plan`.
          The regenerated plan carries ``plan_status="generated"`` per
          Story 4.1's ``generate_plan`` semantics + a fresh ``ac_hash``
          matching :func:`compute_ac_hash` of ``ac_list`` byte-for-byte.
          The reset to ``"generated"`` is unconditional — even if
          ``parsed_plan.plan_status == "human-reviewed"`` the fresh
          plan returns to ``"generated"`` per the verbatim epic AC at
          ``epics.md`` line 1845.
        * **Step 3 — Construct the diagnostic context** preserving the
          prior state — ``prior_plan_status`` is ``parsed_plan.plan_status``
          (NOT the reset value); ``prior_ac_hash`` is
          ``parsed_plan.ac_hash`` (NOT the freshly-computed hash).
          ``current_ac_hash`` is the freshly-computed hash; ``story_id``
          is the dispatch payload's story identifier.
        * **Step 4 — Construct the marker emission record** carrying
          ``marker_class="plan-drift-detected"`` + the diagnostic
          context.
        * **Step 5 — Return the** :class:`PlanDriftEmission` carrying
          the fresh plan + the marker record + the diagnostic context.

    Args:
        parsed_plan: The plan parsed from the story doc (the upstream
            output of Story 4.1's
            :func:`loud_fail_harness.qa_behavioral_plan.persist_or_reuse_plan`
            on the ``"drift-suspected"`` branch). Carries the prior
            ``plan_status`` + prior ``ac_hash`` the diagnostic
            context preserves.
        ac_list: The current AC list from the dispatch payload (the
            single QA-side input channel; FR16 invariant). Accepted as
            list or tuple of :class:`AcEntry`; the regenerated plan's
            entries reflect this list verbatim per Story 4.1's
            ``generate_plan`` semantics.
        story_id: The BMAD story identifier (mirrors Story 4.1's
            ``persist_or_reuse_plan`` parameter; threaded into the
            diagnostic context).
        registry: The runtime :class:`MarkerClassRegistry` from
            :func:`loud_fail_harness.specialist_dispatch.load_marker_class_registry`;
            must contain the ``plan-drift-detected`` marker class
            (verified by Story 1.4's enumeration). Registry rejection
            raises :exc:`UnknownMarkerClass`.

    Returns:
        :class:`PlanDriftEmission` carrying ``fresh_plan`` (channel 1)
        + ``marker_record`` (channel 2) + ``diagnostic_context``
        (co-exposed for ergonomic access).

    Raises:
        :exc:`UnknownMarkerClass`: registry does not contain
        ``"plan-drift-detected"``. Pattern 5 named-invariant
        diagnostic; the substrate seam's existing exception type.
    """
    validate_marker_emission(registry, PLAN_DRIFT_DETECTED_MARKER)

    current_ac_hash = compute_ac_hash(ac_list)
    fresh_plan = generate_plan(story_id, ac_list)

    diagnostic_context = PlanDriftDiagnosticContext(
        story_id=story_id,
        prior_plan_status=parsed_plan.plan_status,
        prior_ac_hash=parsed_plan.ac_hash,
        current_ac_hash=current_ac_hash,
    )
    marker_record = PlanDriftEmissionRecord(
        marker_class=PLAN_DRIFT_DETECTED_MARKER,
        diagnostic_context=diagnostic_context,
    )
    return PlanDriftEmission(
        fresh_plan=fresh_plan,
        marker_record=marker_record,
        diagnostic_context=diagnostic_context,
    )


__all__ = [
    "PLAN_DRIFT_DETECTED_MARKER",
    "PlanDriftDiagnosticContext",
    "PlanDriftEmission",
    "PlanDriftEmissionRecord",
    "surface_plan_drift",
]
