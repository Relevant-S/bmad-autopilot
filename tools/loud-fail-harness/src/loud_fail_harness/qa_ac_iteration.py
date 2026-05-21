"""QA plan-driven AC iteration framework + smoke-first abort (Story 4.6).

FR22b + FR16 + FR17 + Pattern 5. Composes Story 4.1's
:mod:`loud_fail_harness.qa_behavioral_plan` (the
:class:`QABehavioralPlan` + :class:`QABehavioralPlanEntry` shape +
the :class:`AcEntry` dispatch-payload shape), Story 4.4's
:mod:`loud_fail_harness.playwright_driver`
(:func:`verify_ac` for ``project_type="web"`` + the cross-driver
:class:`AcResult` / :class:`EvidenceCapturer` /
:class:`MaskedSelectorPolicy` primitives), Story 4.5's
:mod:`loud_fail_harness.http_driver`
(:func:`verify_ac` for ``project_type="api"``), and Story 2.6's
:mod:`loud_fail_harness.specialist_dispatch` (the
:class:`MarkerClassRegistry` + :func:`validate_marker_emission`
emission discipline).

Architectural placement (parallel to Stories 4.2 / 4.3 / 4.4 / 4.5
substrate-library siblings of ADR-003's five enumerated substrate
components):  this module is a **substrate library NOT a sixth
substrate component**. ADR-003 enumerates exactly five substrate
components (architecture.md lines 311-315); THIS module is a
substrate **library** consumed by the QA wrapper at AC-iteration
time (Story 4.13 forthcoming wrapper thickening composes
:func:`iterate_acs` once at ``agents/qa.md`` Procedure step
"Drive the running product per ``project_type``"). It is
structurally a pure-library sibling of Stories 4.1 / 4.2 / 4.3 /
4.4 / 4.5.

Plan-driven iteration contract (Story 4.6 AC-2 + AC-3 + AC-4):

    1. **AC-iteration in story-doc order** — :func:`iterate_acs`
       walks ``plan.entries`` in plan-tuple order, which equals
       ``ac_list`` story-doc order per Story 4.1's ``generate_plan``
       byte-stable ordering. Per FR22b ("execute acceptance criteria
       in story-doc order, using AC numbering as criticality
       signal").

    2. **Smoke-first abort on AC-1 failure** (FR22b — verbatim epic
       AC at ``epics.md`` lines 1976-1985). When the FIRST iteration
       returns ``status="fail"``:

         * :func:`surface_smoke_first_abort` validates the
           ``smoke-first-abort`` marker class against the runtime
           registry FIRST (atomic-on-failure per Pattern 5; mirrors
           Story 4.2's :func:`surface_plan_drift` byte-for-byte +
           Story 3.3's
           :func:`loud_fail_harness.review_layer_failure.surface_review_layer_failure`).
         * Iteration aborts — AC-2 through AC-N's ``verify_ac`` is
           NOT called.
         * The returned :class:`AcIterationResult` carries the
           single AC-1 failure result + the marker emission record
           (NOT a wall of cascading failures per the verbatim epic
           AC at ``epics.md`` line 1976).

    3. **Non-AC-1 failure continues iteration** — when AC-1 passes
       (or is ``blocked``) but a later AC fails, iteration continues
       through every remaining entry; ``smoke_first_abort`` stays
       :data:`None`. Smoke-first abort fires ONLY on AC-1 ``"fail"``
       per the verbatim epic AC.

    4. **Plan-absent / plan-ac-list-mismatch loud-fail** — on
       structural inputs that should have been caught upstream by
       Story 4.2's :func:`surface_plan_drift` BEFORE iteration
       starts (``plan is None``, empty ``plan.entries``, or AC-id
       mismatch between ``plan.entries`` and ``ac_list``),
       :func:`iterate_acs` raises :exc:`PlanAbsentForIteration`
       with a structured ``failure_diagnostic`` naming the mismatch
       shape. The exception propagates UNCHANGED — the QA wrapper
       catches and routes via Story 4.10's ``verification-fail``
       escalation contract.

    5. **Within-AC flow-branch processing** (FR22c — Story 13.3;
       Architecture Pattern 8 "Within-AC Flow-Branch Enumeration").
       For every non-aborting AC, :func:`iterate_acs` processes the
       per-AC ``flow_branches[]`` enumeration Story 13.2 landed on
       :class:`QABehavioralPlanEntry`: each ``intentionally-skipped``
       branch becomes a ``heuristic-skipped: flow-branch-<branch-id>``
       marker record via :func:`surface_flow_branch_skipped`; each
       ``must-visit`` branch becomes a coverage obligation. Both
       halves are carried back, per AC, on
       :attr:`AcIterationResult.flow_branch_coverage` as a tuple of
       :class:`AcFlowBranchCoverage` records. Per Pattern 8,
       enumeration is plan-generation and *visitation is run-time* —
       this library emits the deterministic skip markers and surfaces
       the ``must-visit`` obligation as typed data; it does NOT drive
       a ``must-visit`` branch (Story 13.4's ``agents/qa.md``
       wrapper-prompt change does that, and Story 13.5's CI fixture
       reconciles a ``must-visit`` branch with no evidence and no
       marker). Smoke-first abort (item 2) takes precedence — a
       failed AC-1's ``flow_branches[]`` are not processed.

Marker-class linkage:
    The ``smoke-first-abort`` marker class exists from Story 1.4 at
    ``schemas/marker-taxonomy.yaml`` line 188. THIS module is the
    FIRST runtime emitter — consumed AS-IS via
    :func:`validate_marker_emission(registry, SMOKE_FIRST_ABORT_MARKER)`.
    Per the per-marker remediation-shape principle codified in
    ``docs/extension-audit.md`` § Marker class boundaries, the
    ``smoke-first-abort`` class is REMEDIATION-shaped — "fix the
    smoke-failing surface, then re-run QA" — and SHARED across all
    project types since the remediation surface is identical
    regardless of whether AC-1 was a Playwright DOM check or an
    HTTP status check.

Cross-driver primitive reuse posture (mirrors Story 4.5's design
rationale at ``4-5-http-driver-api-project-type.md`` § Why a NEW
module — "the cross-module reuse is via direct import — these are
project-type-agnostic primitives whose canonical declaration site
happens to be ``playwright_driver.py`` because Story 4.4 landed
first in build order; a future refactor MAY relocate them to a
shared module, but THIS story does NOT perform that refactor"):

    * :class:`AcResult` — REUSED AS-IS via direct import from
      :mod:`loud_fail_harness.playwright_driver`.
    * :class:`EvidenceCapturer` (Protocol) — REUSED AS-IS via
      direct import from :mod:`loud_fail_harness.playwright_driver`.
    * :class:`MaskedSelectorPolicy` — REUSED AS-IS via direct
      import from :mod:`loud_fail_harness.playwright_driver`.
    * :class:`WebDriver` (Protocol) — REUSED AS-IS via direct
      import from :mod:`loud_fail_harness.playwright_driver`.
    * :class:`ApiDriver` (Protocol) — REUSED AS-IS via direct
      import from :mod:`loud_fail_harness.http_driver`.
    * :exc:`PlaywrightMcpUnavailable` (re-raised UNCHANGED by
      ``playwright_driver.verify_ac`` — propagates through
      :func:`iterate_acs` to the QA wrapper which routes through
      :func:`surface_playwright_mcp_unavailable`).
    * :exc:`ApiServiceBroken` (re-raised UNCHANGED by
      ``http_driver.verify_ac`` — propagates through
      :func:`iterate_acs` to the QA wrapper which routes through
      :func:`surface_env_setup_failure`).

In-place-thickening linkage (Epic 3 retro Insight #1):
    ``agents/qa.md`` is the wrapper composing this library. The
    wrapper's existing forward-pointer at line 34 ("Stories 4.6 +
    4.7 thicken the wrapper IN PLACE to plan-driven AC iteration")
    IS the in-place-thickening commitment THIS story preserves.
    THIS story does NOT modify ``agents/qa.md`` — Story 4.13 owns
    the wrapper thickening completion (composes :func:`iterate_acs`
    once at "Drive the running product per ``project_type``" step;
    consumes the :class:`AcIterationResult` for envelope
    projection).

No-new-step-file structural choice (per Story 4.6 AC-10):
    THIS story does NOT add a new step file. The iteration
    framework has no LLM-runtime tool surface — pure-Python
    composition of Story 4.4's / 4.5's project-type-specific
    driver step files (``qa-driver-playwright.md`` and
    ``qa-driver-http.md``) at AC-iteration time. The two existing
    step files already declare Story 4.6 as a forward consumer
    (the verbatim line at ``qa-driver-playwright.md`` line 102:
    "Story 4.6 — plan-driven AC iteration framework consumes
    ``verify_ac`` at iteration time"; analogous in
    ``qa-driver-http.md``); THIS story closes the forward-pointer
    commitment without introducing new tool-surface bindings.

QA-independence-from-TEA-artifacts invariant (FR16, PRD line 830):
    The iteration framework reads ONLY the ``ac_list`` + ``plan``
    + driver/capturer/policy arguments from the dispatch payload.
    The framework does NOT read TEA test files, dev tests, review
    findings, or commit diffs. The invariant is structurally
    encoded by :func:`iterate_acs`'s signature.

Sensor-not-advisor (PRD-level invariant + Pattern 5):
    The library RETURNS the :class:`AcIterationResult`; it does
    NOT write to the story doc, does NOT emit markers (the marker
    record is data, not an emission), does NOT log, does NOT print.
    Same posture as Stories 4.1 / 4.2 / 4.3 / 4.4 / 4.5 / 3.3 /
    2.6 / 1.10b.
"""

from __future__ import annotations

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness.http_driver import verify_ac as _http_verify_ac
from loud_fail_harness.http_driver import ApiDriver
# Story 9.3 — mobile project type dispatch
from loud_fail_harness.mobile_driver import MobileDriver
from loud_fail_harness.mobile_driver import verify_ac as _mobile_verify_ac
from loud_fail_harness.playwright_driver import (
    AcResult,
    EvidenceCapturer,
    MaskedSelectorPolicy,
    WebDriver,
)
from loud_fail_harness.playwright_driver import verify_ac as _playwright_verify_ac
from loud_fail_harness.qa_behavioral_plan import (
    AcEntry,
    FlowBranch,
    QABehavioralPlan,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)


#: The marker class identifier emitted on AC-1 failure (Story 1.4
#: enumeration; ``schemas/marker-taxonomy.yaml`` line 188). Consumed
#: AS-IS; THIS module is the FIRST runtime emitter. Mirrors Story
#: 4.2's ``PLAN_DRIFT_DETECTED_MARKER`` constant pattern + Story
#: 4.4's ``PLAYWRIGHT_MCP_UNAVAILABLE_MARKER`` constant pattern.
SMOKE_FIRST_ABORT_MARKER: Literal["smoke-first-abort"] = "smoke-first-abort"


#: The marker class identifier emitted for an ``intentionally-skipped``
#: within-AC flow branch (FR22c / Story 13.3). It is the EXISTING v1
#: 27-class ``heuristic-skipped`` marker class from
#: ``schemas/marker-taxonomy.yaml`` — reused AS-IS with NO new top-level
#: class; the ``flow-branch`` sub-classification under it is declared by
#: Story 13.6's v1.5 → v1.6 PATCH bump. This is the SAME canonical
#: taxonomy string as
#: :data:`loud_fail_harness.qa_exploratory_heuristics.HEURISTIC_SKIPPED_MARKER`,
#: defined LOCALLY here (not cross-imported) to avoid a cross-module
#: coupling — consistent with the codebase's documented
#: ``HeuristicKind``-is-duplicated cross-story-coupling-avoidance posture.
HEURISTIC_SKIPPED_MARKER: Final[Literal["heuristic-skipped"]] = "heuristic-skipped"


#: The supported project-type literal alias mirroring the dispatch
#: payload's ``project_type`` enum at
#: ``schemas/tea-handoff-contract.yaml`` lines 133-141 byte-for-byte.
#: Story 9.3 widened the literal to include ``mobile``: mobile
#: dispatch is wired to :func:`loud_fail_harness.mobile_driver.verify_ac`
#: per Story 9.3 + ADR-007 (Phase 1.5 mobile-mcp activation).
ProjectType = Literal["web", "api", "mobile"]


class SmokeFirstAbortDiagnosticContext(BaseModel):
    """The four-field diagnostic context carried on the
    ``smoke-first-abort`` marker emission.

    Field semantics (verbatim epic AC at ``epics.md`` line 1985):
        * ``story_id`` — the BMAD story identifier the dispatch is
          scoped to.
        * ``failed_ac_id`` — the AC identifier of the failed
          smoke-first AC (always ``"AC-1"`` at MVP, but
          parameterized for forward-pointer flexibility — Story
          4.7 / Story 4.9 may extend the criticality-signal model).
        * ``failed_assertions`` — tuple of human-readable assertion
          strings copied verbatim from the AC-1
          :class:`AcResult.assertions` tuple (NOT recomputed).
        * ``failed_evidence_refs`` — tuple of repo-relative
          evidence-path strings copied verbatim from the AC-1
          :class:`AcResult.evidence_refs` tuple (NOT recomputed).

    Frozen for hashability + determinism per Epic 1 retro Action
    #2. Field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str
    failed_ac_id: str
    failed_assertions: tuple[str, ...]
    failed_evidence_refs: tuple[str, ...]


class SmokeFirstAbortEmissionRecord(BaseModel):
    """One marker-emission record for the ``smoke-first-abort``
    channel.

    Local to Story 4.6 — NOT a reuse of Story 4.2's
    :class:`loud_fail_harness.qa_plan_drift.PlanDriftEmissionRecord`
    or Story 3.3's
    :class:`loud_fail_harness.review_layer_failure.MarkerEmissionRecord`
    because the payload shape differs (Story 4.2 carries the
    four-field plan-drift diagnostic; THIS story carries the
    four-field smoke-first-abort diagnostic). Cross-story coupling
    avoidance — same posture Stories 4.2 / 4.4 / 4.5 took.

    Frozen for determinism + hashability. Field declaration order
    is load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``marker_class`` — the canonical marker class identifier
          from ``schemas/marker-taxonomy.yaml`` (always
          ``"smoke-first-abort"`` at this story's scope; verified
          by the :data:`SMOKE_FIRST_ABORT_MARKER` symbolic
          constant).
        * ``diagnostic_context`` — the four-field
          :class:`SmokeFirstAbortDiagnosticContext` carried on the
          marker emission. Bundle-assembler consumers (Story 4.13)
          read this field to render the human-readable diagnostic
          sub-section.
    """

    model_config = ConfigDict(frozen=True)

    marker_class: Literal["smoke-first-abort"]
    diagnostic_context: SmokeFirstAbortDiagnosticContext


class SmokeFirstAbortEmission(BaseModel):
    """The atomic-emission return shape of
    :func:`surface_smoke_first_abort`.

    Mirrors Story 4.2's :class:`PlanDriftEmission` co-exposure
    pattern at ``qa_plan_drift.py`` lines 280-294 byte-for-byte
    (the ``diagnostic_context`` is co-exposed alongside the
    ``marker_record`` for ergonomic access without unwrapping the
    record — the equal payload object as
    ``marker_record.diagnostic_context``).

    Frozen for determinism + hashability per Epic 1 retro Action
    #2. Field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.

    Field semantics:
        * ``marker_record`` — the
          :class:`SmokeFirstAbortEmissionRecord` carrying
          ``marker_class="smoke-first-abort"`` + the four-field
          diagnostic context.
        * ``diagnostic_context`` — the four-field
          :class:`SmokeFirstAbortDiagnosticContext`. Co-exposed for
          ergonomic access (equal payload object as
          ``marker_record.diagnostic_context``).
    """

    model_config = ConfigDict(frozen=True)

    marker_record: SmokeFirstAbortEmissionRecord
    diagnostic_context: SmokeFirstAbortDiagnosticContext


class FlowBranchSkippedDiagnosticContext(BaseModel):
    """The five-field diagnostic context carried on a
    ``heuristic-skipped: flow-branch-<branch-id>`` marker emission
    (FR22c / Story 13.3).

    Emitted for one ``intentionally-skipped`` within-AC flow branch (a
    :class:`loud_fail_harness.qa_behavioral_plan.FlowBranch` of a per-AC
    ``flow_branches[]`` entry — Story 13.2). Carries enough for the
    operator to see, in the PR bundle, *what* within-AC branch was
    skipped and *why*.

    Field semantics:
        * ``story_id`` — the BMAD story identifier the dispatch is
          scoped to.
        * ``ac_id`` — the AC identifier whose ``flow_branches[]`` the
          skipped branch belongs to.
        * ``branch_id`` — the skipped :class:`FlowBranch`'s
          ``branch_id`` (the ``<branch-id>`` component of the rendered
          ``heuristic-skipped: flow-branch-<branch-id>`` marker token).
        * ``branch_description`` — the skipped branch's ``description``
          (the human-readable "what").
        * ``skip_rationale`` — the operator-facing "why", copied
          VERBATIM from the :class:`FlowBranch`'s ``skip_rationale``
          (Story 13.2's ``FlowBranch`` model guarantees it non-empty
          for an ``intentionally-skipped`` branch via its
          ``@model_validator``).

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    ac_id: str = Field(min_length=1)
    branch_id: str = Field(min_length=1)
    branch_description: str = Field(min_length=1)
    skip_rationale: str = Field(min_length=1)


class FlowBranchSkippedEmissionRecord(BaseModel):
    """One marker-emission record for the within-AC flow-branch skip
    channel (FR22c / Story 13.3).

    Local to Story 13.3 — NOT a reuse of Story 4.9's
    :class:`loud_fail_harness.qa_exploratory_heuristics.HeuristicSkippedEmissionRecord`,
    whose own docstring states "Local to Story 4.9 — NOT a reuse …
    different diagnostic shape, different remediation surface". A
    within-AC ``flow-branch`` skip and a cross-AC exploratory-heuristic
    skip share the ``heuristic-skipped`` marker class but carry
    different diagnostic payloads — the cross-story-coupling-avoidance
    posture Stories 4.2 / 4.6 / 4.9 took.

    Frozen for determinism + hashability. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``marker_class`` — the canonical marker class identifier;
          always ``"heuristic-skipped"`` — the EXISTING v1 27-class
          marker class, reused AS-IS with NO new top-level class (the
          whole point of Story 13.6's PATCH-only taxonomy bump).
          Verified by the :data:`HEURISTIC_SKIPPED_MARKER` constant.
        * ``sub_classification`` — always ``"flow-branch"``: the
          taxonomy-reconcilable sub-classification token Story 13.6
          declares under ``heuristic-skipped``; distinguishes a
          within-AC flow-branch skip from the cross-AC exploratory
          heuristics (``empty-state`` / ``error-state`` /
          ``auth-boundary``).
        * ``diagnostic_context`` — the five-field
          :class:`FlowBranchSkippedDiagnosticContext`.
    """

    model_config = ConfigDict(frozen=True)

    marker_class: Literal["heuristic-skipped"]
    sub_classification: Literal["flow-branch"]
    diagnostic_context: FlowBranchSkippedDiagnosticContext


class FlowBranchSkippedEmission(BaseModel):
    """The atomic-emission return shape of
    :func:`surface_flow_branch_skipped` (FR22c / Story 13.3).

    Mirrors Story 4.6's :class:`SmokeFirstAbortEmission` + Story 4.9's
    :class:`loud_fail_harness.qa_exploratory_heuristics.HeuristicSkippedEmission`
    co-exposure pattern: the ``diagnostic_context`` is co-exposed
    alongside the ``marker_record`` for ergonomic access without
    unwrapping the record (the equal payload object as
    ``marker_record.diagnostic_context``).

    Frozen for determinism + hashability. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``marker_record`` — the
          :class:`FlowBranchSkippedEmissionRecord`.
        * ``diagnostic_context`` — the five-field
          :class:`FlowBranchSkippedDiagnosticContext`. Co-exposed for
          ergonomic access (equal payload object as
          ``marker_record.diagnostic_context``).
    """

    model_config = ConfigDict(frozen=True)

    marker_record: FlowBranchSkippedEmissionRecord
    diagnostic_context: FlowBranchSkippedDiagnosticContext


class AcFlowBranchCoverage(BaseModel):
    """The per-AC within-AC flow-branch coverage record (FR22c /
    Story 13.3) — both halves of the FR22c contract for one AC in a
    single typed, operator-reviewable, machine-readable shape.

    Produced by :func:`iterate_acs` for ONE iterated AC, and ONLY for an
    AC whose ``flow_branches`` tuple is non-empty — an AC with an empty
    ``flow_branches[]`` (every pre-FR22c AC, and every strictly-linear
    FR22c AC) contributes NO :class:`AcFlowBranchCoverage` record.

    Frozen for determinism + hashability. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics — the two halves of the FR22c within-AC contract:
        * ``ac_id`` — the AC identifier this coverage record is for.
        * ``must_visit_branch_ids`` — the ``branch_id`` of every
          ``FlowBranch`` of the AC whose ``disposition ==
          "must-visit"``, in plan-declaration order. This is the
          COVERAGE OBLIGATION: Story 13.4's wrapper drives each of
          these branches at run time, and Story 13.5's CI fixture
          reconciles a ``must-visit`` branch with no evidence and no
          marker as a contract violation. :func:`iterate_acs` does NOT
          itself visit a ``must-visit`` branch — it only surfaces the
          obligation as typed data.
        * ``skipped`` — one :class:`FlowBranchSkippedEmissionRecord`
          per ``intentionally-skipped`` branch of the AC, in
          plan-declaration order. This is the DISCHARGED-BY-MARKER
          set: each skip is loud-failed via a
          ``heuristic-skipped: flow-branch-<branch-id>`` marker.
    """

    model_config = ConfigDict(frozen=True)

    ac_id: str = Field(min_length=1)
    must_visit_branch_ids: tuple[str, ...]
    skipped: tuple[FlowBranchSkippedEmissionRecord, ...]


class AcIterationResult(BaseModel):
    """The result of :func:`iterate_acs` — composed by the QA
    wrapper to project into the envelope's ``ac_results`` array
    (FR55), surface the ``smoke-first-abort`` marker via the
    orchestrator-event log (when ``smoke_first_abort`` is non-None),
    AND surface the FR22c within-AC flow-branch coverage (Story 13.3).

    Frozen + field declaration order load-bearing for byte-stable
    ``model_dump_json()`` output. ``flow_branch_coverage`` is appended
    LAST so every pre-existing field keeps its byte position.

    Field semantics:
        * ``ac_results`` — tuple of :class:`AcResult` records
          collected during iteration. On smoke-first abort the
          tuple contains EXACTLY ONE entry (the AC-1 failure) per
          the verbatim epic AC at ``epics.md`` line 1976. On
          happy-path completion the tuple matches ``plan.entries``
          1-1 in story-doc order. On non-AC-1 mid-iteration
          failure the tuple contains ALL entries (every plan entry
          is processed via ``verify_ac`` even past the failed one).
        * ``smoke_first_abort`` — the
          :class:`SmokeFirstAbortEmissionRecord` when AC-1 failed
          (FR22b smoke-first abort fired). :data:`None` when AC-1
          passed or was ``blocked``, or when iteration completed
          without an AC-1 fail. Status ``"blocked"`` does NOT
          trigger smoke-first abort — only ``"fail"`` triggers per
          the verbatim epic AC.
        * ``project_type`` — echoed verbatim from the dispatch for
          downstream debugging visibility.
        * ``flow_branch_coverage`` — the FR22c within-AC
          flow-branch-coverage surface (Story 13.3): one
          :class:`AcFlowBranchCoverage` per iterated AC whose
          ``flow_branches[]`` was non-empty, in plan-iteration
          (story-doc) order. EMPTY for a pre-FR22c plan, for a plan
          whose ACs are all strictly linear (no enumerated
          branches), AND on a smoke-first-aborted run — on abort it
          carries only the coverage of ACs processed before the
          abort, which is none, because a failed AC-1 returns before
          its own flow-branch processing (AC-6). Additive-optional
          with an empty-tuple default: an :class:`AcIterationResult`
          constructed WITHOUT ``flow_branch_coverage`` succeeds and
          yields ``flow_branch_coverage == ()`` — the property that
          keeps Story 13.3 non-breaking for every pre-existing
          constructor and consumer.
    """

    model_config = ConfigDict(frozen=True)

    ac_results: tuple[AcResult, ...]
    smoke_first_abort: SmokeFirstAbortEmissionRecord | None = None
    project_type: ProjectType
    flow_branch_coverage: tuple[AcFlowBranchCoverage, ...] = Field(
        default_factory=tuple
    )


class PlanAbsentForIteration(Exception):
    """Raised by :func:`iterate_acs` when the plan / ac_list shape
    is structurally invalid for iteration.

    Plan-absent / plan-ac-list-mismatch should have been caught by
    Story 4.2's :func:`surface_plan_drift` BEFORE iteration starts;
    the iteration framework loud-fails on this rather than silently
    proceeding (Pattern 5 named-invariant diagnostic). The QA
    wrapper catches and routes via Story 4.10's ``verification-fail``
    escalation contract.

    Attributes:
        failure_diagnostic: The structured diagnostic naming the
            mismatch shape — one of:

                * ``"plan absent: parsed_plan is None"``
                * ``"plan absent: parsed_plan.entries is empty"``
                * ``"plan-ac-list-mismatch: plan ac_ids={X}
                  ac_list ac_ids={Y}"`` (with sorted AC-id sets)

            Mirrors :exc:`ApiServiceBroken.failure_diagnostic` and
            :exc:`PlaywrightMcpUnavailable` shape conventions.
    """

    def __init__(self, failure_diagnostic: str) -> None:
        self.failure_diagnostic: str = failure_diagnostic
        super().__init__(failure_diagnostic)


def surface_smoke_first_abort(
    story_id: str,
    registry: MarkerClassRegistry,
    ac1_result: AcResult,
) -> SmokeFirstAbortEmission:
    """Atomic-on-failure smoke-first-abort emission helper.

    Mirrors Story 4.2's
    :func:`loud_fail_harness.qa_plan_drift.surface_plan_drift`
    Pattern-5 atomic-on-failure structure byte-for-byte:
    :func:`validate_marker_emission` runs FIRST; on registry
    rejection :exc:`UnknownMarkerClass` propagates UNCHANGED per
    Pattern 5 BEFORE any partial state is constructed.

    Behavior:
        * **Step 1 — Validate marker emission FIRST**. Calls
          :func:`validate_marker_emission(registry,
          SMOKE_FIRST_ABORT_MARKER)`. On registry rejection
          :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
          propagates per Pattern 5; NO partial state is
          constructed (atomic-on-failure; mirrors Story 4.2 line
          372 + Story 3.3 lines 274-289).
        * **Step 2 — Construct the diagnostic context** carrying
          ``story_id`` + ``failed_ac_id`` (from ``ac1_result.ac_id``)
          + ``failed_assertions`` (copied verbatim from
          ``ac1_result.assertions``) + ``failed_evidence_refs``
          (copied verbatim from ``ac1_result.evidence_refs``).
        * **Step 3 — Construct the marker emission record**
          carrying the canonical marker class string
          ``"smoke-first-abort"`` + the diagnostic context.
        * **Step 4 — Return the** :class:`SmokeFirstAbortEmission`
          carrying both the marker record + the (co-exposed)
          diagnostic context.

    Pure: no file I/O, no story-doc reads or writes, no marker
    emission to the orchestrator-event log.

    Args:
        story_id: The BMAD story identifier; threaded into the
            diagnostic context.
        registry: The runtime
            :class:`loud_fail_harness.specialist_dispatch.MarkerClassRegistry`
            from
            :func:`loud_fail_harness.specialist_dispatch.load_marker_class_registry`;
            must contain the ``smoke-first-abort`` marker class
            (verified by Story 1.4's enumeration). Registry
            rejection raises :exc:`UnknownMarkerClass`.
        ac1_result: The AC-1 :class:`AcResult` whose ``status`` is
            ``"fail"``. The diagnostic context copies its
            ``assertions`` + ``evidence_refs`` tuples verbatim.

    Returns:
        :class:`SmokeFirstAbortEmission` carrying ``marker_record``
        + ``diagnostic_context``.

    Raises:
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
        registry does not contain ``"smoke-first-abort"``. Pattern
        5 named-invariant diagnostic; the substrate seam's
        existing exception type.
    """
    validate_marker_emission(registry, SMOKE_FIRST_ABORT_MARKER)

    # Story 4.8 transitive shim: AcResult.evidence_refs is bumped to
    # tuple[EvidenceRef, ...] but SmokeFirstAbortDiagnosticContext's
    # failed_evidence_refs (Story 4.6) is tuple[str, ...]. Project the
    # path strings out of the tier-aware refs so the diagnostic shape
    # is preserved unchanged. The tier metadata is recoverable from
    # the source AcResult when needed by Story 4.10's escalation
    # routing; the smoke-first diagnostic is intentionally narrow per
    # the verbatim epic AC at epics.md line 1985.
    diagnostic_context = SmokeFirstAbortDiagnosticContext(
        story_id=story_id,
        failed_ac_id=ac1_result.ac_id,
        failed_assertions=ac1_result.assertions,
        failed_evidence_refs=tuple(
            ref.path for ref in ac1_result.evidence_refs
        ),
    )
    marker_record = SmokeFirstAbortEmissionRecord(
        marker_class=SMOKE_FIRST_ABORT_MARKER,
        diagnostic_context=diagnostic_context,
    )
    return SmokeFirstAbortEmission(
        marker_record=marker_record,
        diagnostic_context=diagnostic_context,
    )


def surface_flow_branch_skipped(
    story_id: str,
    ac_id: str,
    branch: FlowBranch,
    registry: MarkerClassRegistry,
) -> FlowBranchSkippedEmission:
    """Atomic-on-failure within-AC flow-branch-skipped emission helper
    (FR22c / Story 13.3).

    Mirrors Story 4.6's :func:`surface_smoke_first_abort` + Story 4.9's
    :func:`loud_fail_harness.qa_exploratory_heuristics.surface_heuristic_skipped`
    Pattern-5 atomic-on-failure structure byte-for-byte:
    :func:`validate_marker_emission` runs FIRST; on registry rejection
    :exc:`UnknownMarkerClass` propagates UNCHANGED per Pattern 5 BEFORE
    any partial state is constructed.

    Behavior:
        * **Step 1 — Validate marker emission FIRST**. Calls
          :func:`validate_marker_emission(registry,
          HEURISTIC_SKIPPED_MARKER)`. On registry rejection
          :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
          propagates per Pattern 5; NO partial state is constructed
          (atomic-on-failure). The ``heuristic-skipped`` marker class
          exists in the registry from Story 1.4 — the Story 13.6
          dependency is the taxonomy's ``flow-branch``
          *sub-classification* + the CI reconciliation, NOT the runtime
          registry (which checks only the marker *class*).
        * **Step 2 — Precondition guard**. ``branch.disposition`` MUST
          be ``"intentionally-skipped"`` — emitting a skip marker for a
          ``must-visit`` branch is a caller bug; :exc:`ValueError` is
          raised otherwise.
        * **Step 3 — Construct the diagnostic context** carrying
          ``story_id`` + ``ac_id`` + the ``branch``'s ``branch_id`` /
          ``description`` / ``skip_rationale`` (copied VERBATIM —
          ``branch.skip_rationale`` is guaranteed non-``None`` and
          non-empty for an ``intentionally-skipped`` branch by
          :class:`FlowBranch`'s ``@model_validator``).
        * **Step 4 — Construct the marker emission record** carrying
          ``marker_class="heuristic-skipped"`` +
          ``sub_classification="flow-branch"`` + the diagnostic
          context.
        * **Step 5 — Return the** :class:`FlowBranchSkippedEmission`
          carrying both the marker record + the (co-exposed) diagnostic
          context.

    Pure: no file I/O, no story-doc reads or writes, no marker emission
    to the orchestrator-event log (the
    :class:`FlowBranchSkippedEmissionRecord` is *data* the QA wrapper
    consumes and emits — Story 13.4 / the bundle assembler renders the
    literal ``heuristic-skipped: flow-branch-<branch-id>`` token).

    Args:
        story_id: The BMAD story identifier; threaded into the
            diagnostic context.
        ac_id: The AC identifier whose ``flow_branches[]`` the skipped
            branch belongs to; threaded into the diagnostic context.
        branch: The ``intentionally-skipped``
            :class:`loud_fail_harness.qa_behavioral_plan.FlowBranch`.
            Its ``branch_id`` / ``description`` / ``skip_rationale``
            are copied verbatim into the diagnostic context.
        registry: The runtime
            :class:`loud_fail_harness.specialist_dispatch.MarkerClassRegistry`;
            must contain the ``heuristic-skipped`` marker class.
            Registry rejection raises :exc:`UnknownMarkerClass`.

    Returns:
        :class:`FlowBranchSkippedEmission` carrying ``marker_record`` +
        ``diagnostic_context``.

    Raises:
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
            registry does not contain ``"heuristic-skipped"``.
        :exc:`ValueError`: ``branch.disposition`` is not
            ``"intentionally-skipped"`` (a skip marker for a
            ``must-visit`` branch is a caller bug).
    """
    validate_marker_emission(registry, HEURISTIC_SKIPPED_MARKER)

    if branch.disposition != "intentionally-skipped":
        raise ValueError(
            "surface_flow_branch_skipped requires an intentionally-skipped"
            f" flow branch; got disposition={branch.disposition!r} for"
            f" branch_id={branch.branch_id!r}"
        )
    # branch.skip_rationale is guaranteed non-None + non-empty for an
    # intentionally-skipped branch by FlowBranch's @model_validator; the
    # assert narrows str | None -> str for the type checker (the same
    # narrowing-assert posture as iterate_acs's driver guards).
    assert branch.skip_rationale is not None

    diagnostic_context = FlowBranchSkippedDiagnosticContext(
        story_id=story_id,
        ac_id=ac_id,
        branch_id=branch.branch_id,
        branch_description=branch.description,
        skip_rationale=branch.skip_rationale,
    )
    marker_record = FlowBranchSkippedEmissionRecord(
        marker_class=HEURISTIC_SKIPPED_MARKER,
        sub_classification="flow-branch",
        diagnostic_context=diagnostic_context,
    )
    return FlowBranchSkippedEmission(
        marker_record=marker_record,
        diagnostic_context=diagnostic_context,
    )


def iterate_acs(
    plan: QABehavioralPlan | None,
    ac_list: tuple[AcEntry, ...] | list[AcEntry],
    project_type: ProjectType,
    story_id: str,
    registry: MarkerClassRegistry,
    *,
    web_driver: WebDriver | None = None,
    api_driver: ApiDriver | None = None,
    mobile_driver: MobileDriver | None = None,
    evidence_capturer: EvidenceCapturer,
    masked_selectors: MaskedSelectorPolicy,
) -> AcIterationResult:
    """Iterate the QA Behavioral Plan's per-AC entries in story-doc
    order with smoke-first abort on AC-1 failure (FR22b).

    The pure-library composition of Story 4.4's
    :func:`loud_fail_harness.playwright_driver.verify_ac` (when
    ``project_type="web"``) OR Story 4.5's
    :func:`loud_fail_harness.http_driver.verify_ac` (when
    ``project_type="api"``) at iteration time across the full
    ``plan.entries`` tuple per FR22b.

    Behavior:
        * **Step 1 — argument validation** (AC-6). Raises
          :exc:`ValueError` on:

            - ``project_type="web"`` with ``web_driver=None``;
            - ``project_type="api"`` with ``api_driver=None``;
            - ``project_type="mobile"`` with ``mobile_driver=None``
              (Story 9.3 Phase 1.5 mobile-mcp activation);
            - ``project_type`` not in ``{"web", "api", "mobile"}``
              (any other string).

        * **Step 2 — plan-absent / plan-ac-list-mismatch
          detection** (AC-5). Raises
          :exc:`PlanAbsentForIteration` on:

            - ``plan is None``;
            - ``plan.entries == ()`` (empty tuple);
            - AC-id mismatch between ``plan.entries`` and
              ``ac_list`` (a structural drift Story 4.2's
              :func:`surface_plan_drift` should have caught
              upstream).

        * **Step 3 — happy-path / smoke-first abort iteration**
          (AC-2 + AC-3 + AC-4). Walks ``plan.entries`` in plan-
          tuple order (which equals ``ac_list`` story-doc order
          per Story 4.1's ``generate_plan`` byte-stable ordering);
          for each entry dispatches :func:`verify_ac` per
          ``project_type`` with the looked-up ``ac_text`` from
          ``ac_list``. Smoke-first abort fires when index-0
          returns ``status="fail"`` — :func:`surface_smoke_first_abort`
          validates the marker class FIRST (Pattern 5
          atomic-on-failure), then the result is returned with
          a single AC-1 entry + the marker record. Status
          ``"blocked"`` on AC-1 does NOT trigger smoke-first
          abort (per the verbatim epic AC — only ``"fail"``
          triggers).

        * **Step 4 — within-AC flow-branch processing** (FR22c —
          AC-4 + AC-6 + AC-8 / Story 13.3). After each non-aborting
          entry's ``verify_ac`` call, the framework processes
          ``entry.flow_branches`` (Story 13.2's per-AC within-AC
          branch enumeration on :class:`QABehavioralPlanEntry`):
          every ``intentionally-skipped`` branch becomes a
          ``heuristic-skipped: flow-branch-<branch-id>`` marker
          record via :func:`surface_flow_branch_skipped`, and every
          ``must-visit`` branch's ``branch_id`` becomes a coverage
          obligation. One :class:`AcFlowBranchCoverage` record is
          produced per iterated AC whose ``flow_branches`` tuple is
          non-empty; the records accumulate, in plan-iteration order,
          into the returned
          :attr:`AcIterationResult.flow_branch_coverage`. The
          processing is plan-driven with no driver dependency, so it
          lives once in the shared loop body — byte-identical on the
          web / api / mobile branches (AC-8). The framework does NOT
          itself drive a ``must-visit`` branch: visitation +
          per-branch evidence is the QA agent's run-time job (Story
          13.4's ``agents/qa.md`` wrapper-prompt change), and the
          must-visit-vs-evidence reconciliation is Story 13.5's CI
          gate.

          **FR22b × FR22c precedence** (AC-6 — resolves the
          deferred-work item "FR22b × FR22c interaction at AC-1
          failure unspecified", ``deferred-work.md`` line 793):
          smoke-first abort wins. When AC-1's ``verify_ac`` returns
          ``status="fail"``, :func:`iterate_acs` fires
          :func:`surface_smoke_first_abort` and returns immediately —
          AC-1's own ``flow_branches[]`` are NOT processed (no skip
          markers, no coverage record), so the returned
          :class:`AcIterationResult` carries
          ``flow_branch_coverage == ()``. A broken happy path makes
          within-AC branch coverage moot, exactly as FR22b makes
          downstream-AC coverage moot. For every NON-aborting AC — a
          ``pass`` / ``blocked`` AC-1 and every reached AC-2..AC-N —
          flow-branch processing runs regardless of that AC's own
          ``status`` (the ``intentionally-skipped`` emissions are
          plan-derived and status-independent).

    The function does NOT itself catch :exc:`PlaywrightMcpUnavailable`
    or :exc:`ApiServiceBroken` — those propagate UNCHANGED for the
    QA wrapper to catch and route through Stories 4.4 / 4.5's
    existing helpers (Story 4.10 finalizes routing).

    Args:
        plan: The :class:`QABehavioralPlan` from Story 4.1's
            :func:`loud_fail_harness.qa_behavioral_plan.persist_or_reuse_plan`
            (the wrapper-side branch that produced the plan after
            Story 4.2's drift detection). May be :data:`None` —
            triggers :exc:`PlanAbsentForIteration`.
        ac_list: The current AC list from the dispatch payload
            (FR16 single QA-side input channel). Tuple or list of
            :class:`AcEntry`. Must align 1-1 with ``plan.entries``
            by ``ac_id`` (else :exc:`PlanAbsentForIteration`).
        project_type: ``"web"`` (dispatch via
            :mod:`playwright_driver`), ``"api"`` (dispatch via
            :mod:`http_driver`), or ``"mobile"`` (dispatch via
            :mod:`mobile_driver` — Story 9.3 Phase 1.5 mobile-mcp
            activation). Any other value raises :exc:`ValueError`.
        story_id: The BMAD story identifier; threaded into the
            smoke-first-abort diagnostic context on AC-1 failure.
        registry: The runtime :class:`MarkerClassRegistry`. Must
            contain ``"smoke-first-abort"`` for the abort path and
            ``"heuristic-skipped"`` for plans with
            ``intentionally-skipped`` branches (via
            :func:`surface_flow_branch_skipped` — FR22c / Story 13.3).
        web_driver: The :class:`WebDriver` Protocol implementation
            for ``project_type="web"``; required (else
            :exc:`ValueError`).
        api_driver: The :class:`ApiDriver` Protocol implementation
            for ``project_type="api"``; required (else
            :exc:`ValueError`).
        mobile_driver: The :class:`MobileDriver` Protocol
            implementation for ``project_type="mobile"``; required
            for that branch (else :exc:`ValueError`). Story 9.3.
        evidence_capturer: The :class:`EvidenceCapturer` Protocol
            implementation; threaded into every
            :func:`verify_ac` call.
        masked_selectors: The :class:`MaskedSelectorPolicy`;
            threaded into every :func:`verify_ac` call.

    Returns:
        :class:`AcIterationResult` carrying ``ac_results`` (tuple
        of per-AC records in story-doc order) +
        ``smoke_first_abort`` (the marker record on AC-1 failure;
        :data:`None` otherwise) + ``project_type`` (echoed) +
        ``flow_branch_coverage`` (one :class:`AcFlowBranchCoverage`
        per iterated AC with a non-empty ``flow_branches[]``, in
        plan-iteration order; empty tuple for a pre-FR22c plan or a
        smoke-first-aborted run — FR22c / Story 13.3).

    Raises:
        :exc:`ValueError`: ``project_type`` is unsupported OR the
            project-type-appropriate driver is :data:`None`.
        :exc:`PlanAbsentForIteration`: structural plan / ac_list
            shape invalid for iteration.
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
            (a) on AC-1 failure, the registry does not contain
            ``"smoke-first-abort"`` (from
            :func:`surface_smoke_first_abort`); OR (b) the registry
            does not contain ``"heuristic-skipped"`` AND the plan has
            an ``intentionally-skipped`` branch on a non-aborting AC
            (from :func:`surface_flow_branch_skipped` — FR22c /
            Story 13.3). Both propagate unchanged per Pattern 5.
        :exc:`loud_fail_harness.playwright_driver.PlaywrightMcpUnavailable`:
            re-raised UNCHANGED on mid-run MCP unavailability for
            ``project_type="web"``.
        :exc:`loud_fail_harness.http_driver.ApiServiceBroken`:
            re-raised UNCHANGED on mid-run service-broken for
            ``project_type="api"``.
        :exc:`loud_fail_harness.mobile_driver.MobileMcpUnavailable`:
            re-raised UNCHANGED on mid-run mobile-MCP unavailability
            for ``project_type="mobile"`` — parallel to
            ``PlaywrightMcpUnavailable`` for web. The QA wrapper
            catches and routes through
            :func:`loud_fail_harness.mobile_driver.surface_mobile_mcp_unavailable`.
    """
    # Step 1 — argument validation (AC-6). Order matters: validate
    # project_type's driver-presence pair BEFORE rejecting unknown
    # project_types so the practitioner sees the most-specific
    # diagnostic. Story 9.3 added the ``mobile`` branch.
    if project_type == "web":
        if web_driver is None:
            raise ValueError("project_type='web' requires web_driver")
    elif project_type == "api":
        if api_driver is None:
            raise ValueError("project_type='api' requires api_driver")
    elif project_type == "mobile":
        if mobile_driver is None:
            raise ValueError("project_type='mobile' requires mobile_driver")
    else:
        raise ValueError(f"unsupported project_type: {project_type!r}")

    # Step 2 — plan-absent / plan-ac-list-mismatch detection (AC-5).
    if plan is None:
        raise PlanAbsentForIteration("plan absent: parsed_plan is None")
    if not plan.entries:
        raise PlanAbsentForIteration(
            "plan absent: parsed_plan.entries is empty"
        )

    plan_ac_ids = {entry.ac_id for entry in plan.entries}
    list_ac_ids = {ac.ac_id for ac in ac_list}
    if plan_ac_ids != list_ac_ids:
        raise PlanAbsentForIteration(
            f"plan-ac-list-mismatch: plan ac_ids={sorted(plan_ac_ids)}"
            f" ac_list ac_ids={sorted(list_ac_ids)}"
        )

    # Step 3 — happy-path / smoke-first abort iteration. Build the
    # ac_text lookup by ac_id; iterate plan.entries in plan-tuple
    # order (which equals ac_list story-doc order per Story 4.1).
    ac_text_by_id: dict[str, str] = {ac.ac_id: ac.ac_text for ac in ac_list}
    collected: list[AcResult] = []
    flow_branch_coverage: list[AcFlowBranchCoverage] = []

    for index, entry in enumerate(plan.entries):
        if project_type == "web":
            assert web_driver is not None  # narrowed by AC-6 guard above
            ac_result = _playwright_verify_ac(
                ac_id=entry.ac_id,
                ac_text=ac_text_by_id[entry.ac_id],
                plan_entry=entry,
                driver=web_driver,
                evidence_capturer=evidence_capturer,
                masked_selectors=masked_selectors,
            )
        elif project_type == "api":
            assert api_driver is not None  # narrowed by AC-6 guard above
            ac_result = _http_verify_ac(
                ac_id=entry.ac_id,
                ac_text=ac_text_by_id[entry.ac_id],
                plan_entry=entry,
                driver=api_driver,
                evidence_capturer=evidence_capturer,
                masked_selectors=masked_selectors,
            )
        else:  # project_type == "mobile" — Story 9.3; narrowed by AC-6 guard above
            assert mobile_driver is not None
            ac_result = _mobile_verify_ac(
                entry.ac_id,
                ac_text_by_id[entry.ac_id],
                entry,
                mobile_driver,
                evidence_capturer,
                masked_selectors,
            )
        collected.append(ac_result)

        # Smoke-first abort check (FR22b — AC-1 failure only). Only
        # status="fail" triggers; "blocked" does NOT trigger per the
        # verbatim epic AC at epics.md line 1976.
        #
        # FR22b × FR22c precedence (AC-6 / Story 13.3 — resolves the
        # deferred-work item "FR22b × FR22c interaction at AC-1 failure
        # unspecified", deferred-work.md line 793): smoke-first abort
        # takes precedence over flow-branch processing. This check runs
        # and early-returns BEFORE the per-AC flow-branch block below,
        # so a failed AC-1's own flow_branches[] are NOT processed (no
        # skip markers, no coverage record) and the returned result
        # carries flow_branch_coverage == (). A broken happy path makes
        # within-AC branch coverage moot, exactly as FR22b makes
        # downstream-AC coverage moot.
        if entry.ac_id == "AC-1" and ac_result.status == "fail":
            emission = surface_smoke_first_abort(
                story_id=story_id,
                registry=registry,
                ac1_result=ac_result,
            )
            return AcIterationResult(
                ac_results=tuple(collected),
                smoke_first_abort=emission.marker_record,
                project_type=project_type,
                flow_branch_coverage=(),
            )

        # FR22c within-AC flow-branch processing (AC-4 / AC-8 /
        # Story 13.3). Plan-driven and project-type-agnostic: this block
        # reads only entry.flow_branches and has no driver dependency,
        # so it lives ONCE in the shared loop body — never duplicated
        # per project_type branch (AC-8). It runs for every NON-aborting
        # AC regardless of that AC's own status (a pass / blocked AC-1
        # and every reached AC-2..AC-N): the intentionally-skipped
        # emissions are plan-derived and status-independent. The
        # framework does NOT itself visit a must-visit branch — driving
        # each must-visit branch and supplying per-branch evidence is
        # the QA agent's run-time job (Story 13.4's agents/qa.md
        # wrapper-prompt change); iterate_acs only emits the
        # deterministic skip markers and surfaces the must-visit
        # obligation as typed data (Story 13.5's CI gate reconciles it).
        if entry.flow_branches:
            must_visit_branch_ids: list[str] = []
            skipped_records: list[FlowBranchSkippedEmissionRecord] = []
            for branch in entry.flow_branches:
                if branch.disposition == "intentionally-skipped":
                    branch_emission = surface_flow_branch_skipped(
                        story_id=story_id,
                        ac_id=entry.ac_id,
                        branch=branch,
                        registry=registry,
                    )
                    skipped_records.append(branch_emission.marker_record)
                elif branch.disposition == "must-visit":
                    must_visit_branch_ids.append(branch.branch_id)
                else:
                    raise ValueError(
                        "Unexpected FlowBranch disposition"
                        f" {branch.disposition!r} for"
                        f" branch_id={branch.branch_id!r}"
                    )
            flow_branch_coverage.append(
                AcFlowBranchCoverage(
                    ac_id=entry.ac_id,
                    must_visit_branch_ids=tuple(must_visit_branch_ids),
                    skipped=tuple(skipped_records),
                )
            )

    return AcIterationResult(
        ac_results=tuple(collected),
        smoke_first_abort=None,
        project_type=project_type,
        flow_branch_coverage=tuple(flow_branch_coverage),
    )


__all__ = [
    "HEURISTIC_SKIPPED_MARKER",
    "SMOKE_FIRST_ABORT_MARKER",
    "AcFlowBranchCoverage",
    "AcIterationResult",
    "FlowBranchSkippedDiagnosticContext",
    "FlowBranchSkippedEmission",
    "FlowBranchSkippedEmissionRecord",
    "MobileDriver",
    "PlanAbsentForIteration",
    "ProjectType",
    "SmokeFirstAbortDiagnosticContext",
    "SmokeFirstAbortEmission",
    "SmokeFirstAbortEmissionRecord",
    "iterate_acs",
    "surface_flow_branch_skipped",
    "surface_smoke_first_abort",
]
