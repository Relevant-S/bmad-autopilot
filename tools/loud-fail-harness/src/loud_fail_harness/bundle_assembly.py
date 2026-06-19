"""Walking-skeleton PR bundle assembler — Story 2.11 substrate module.

## Substrate-component identity

THIS module is the SIXTH substrate component beyond ADR-003's enumerated
five (envelope_validator, event_validator, reconciler, enumeration_check,
fixture_coverage). It composes the existing five (and Story 2.6's
:class:`loud_fail_harness.specialist_dispatch.MarkerClassRegistry` +
Story 2.2's :class:`loud_fail_harness.run_state.RunState` + Story 2.11's
:mod:`loud_fail_harness.thickening_flags`) into a single artifact: the
merge-ready PR bundle markdown rendered from the three Epic-2
specialists' return envelopes plus the orchestrator's run-state record.

## Input contract

    * ``story_id`` — the BMAD story key (e.g. ``"sample-auto-001"``).
    * ``run_id`` — orchestrator-domain run identifier per ADR-005
      Consequence 1; used to scope dispatch logs and bundle output paths.
    * ``run_state_path`` — :class:`pathlib.Path` to the on-disk
      ``_bmad/automation/run-state.yaml`` artifact written by Story 2.2's
      :func:`loud_fail_harness.run_state.advance_run_state`.
    * ``logs_root`` — :class:`pathlib.Path` prefix under which Story 2.6's
      :func:`loud_fail_harness.specialist_dispatch.persist_dispatch_log`
      wrote the three specialists' diagnostic logs at the canonical
      :data:`loud_fail_harness.specialist_dispatch.LOG_PATH_TEMPLATE`
      (typically ``_bmad-output/qa-evidence/`` per View 3 line 1171).
    * ``bundle_root`` — :class:`pathlib.Path` prefix under which the
      assembler writes the bundle markdown (typically
      ``_bmad-output/pr-bundles/`` per epics.md Story 2.11 lines
      1490-1492).

## Output contract

    * A markdown file written atomically (Pattern 4: ``tempfile`` +
      ``os.replace``) at ``bundle_root/{story_id}/{run_id}.md``.
    * A returned :class:`AssembleBundleResult` carrying the resolved
      bundle path, the emitted markers tuple, the rendered Walking
      Skeleton Mode header text, and the set of specialists whose
      envelopes were folded into the bundle.

## Marker-emission contract

The ``walking-skeleton-bundle`` marker is emitted iff
:func:`loud_fail_harness.thickening_flags.is_loud_fail_block_present`
returns ``False``. The rule is structural — predicated on the flag's
return value — NOT era-based — predicated on a hardcoded "if Epic == 2"
check. Per the verbatim epic AC at ``epics.md`` Story 2.11 lines
1527-1528 + ``schemas/marker-taxonomy.yaml`` lines 210-216's
diagnostic_pointer, "absent loud-fail block triggers the marker" (rule
clarified by Epic 6). Epic 6's Story 6.1 lands the loud-fail block; its
arrival flips :func:`is_loud_fail_block_present` in place, which
inverts emission without any edit to THIS module.

Pre-emission validation runs through Story 2.6's runtime
:class:`loud_fail_harness.specialist_dispatch.MarkerClassRegistry`:
the candidate marker class is resolved against the registry's
membership before the bundle is written. Registry rejection raises
:exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass` per
Pattern 5 — the assembler does NOT silently substitute or omit.

## Cell-1 contract / cell-4 host-Bridge boundary

Per ``architecture.md`` line 130 + ADR-002 cell 4 row 4: PR bundle
**rendering** (markup + assembly via Stop hook) is the cell-1 portable
contract; the bash Stop hook at ``hooks/stop.sh`` is the cell-4
host-Bridge invocation seam. Two hosts implementing the same cell-1
contract MUST produce semantically identical bundles
(``architecture.md`` line 189). THIS module IS the cell-1 contract.
The bash hook composes the assembler exclusively via
``python3 -m loud_fail_harness.bundle_assembly``; it does NOT inline
rendering decisions.

## Cross-references

    * Story 2.5 :mod:`loud_fail_harness.orchestrator_run_entry` —
      parallel substrate-module precedent.
    * Story 2.6 :mod:`loud_fail_harness.specialist_dispatch` —
      :data:`LOG_PATH_TEMPLATE`, :func:`persist_dispatch_log`,
      :class:`MarkerClassRegistry`, :func:`load_marker_class_registry`,
      :func:`validate_marker_emission`, :exc:`UnknownMarkerClass`.
    * Story 2.7 ``hooks/stop.sh`` — the cell-4 host-Bridge invocation
      seam THIS story rewrites from a literal-placeholder body into a
      thin ``python3 -m`` invocation.
    * Story 1.4 ``schemas/marker-taxonomy.yaml`` lines 210-216 —
      ``walking-skeleton-bundle`` marker class identity (consumed
      AS-IS; THIS story does NOT modify the taxonomy).
    * Story 1.2 :func:`loud_fail_harness.envelope_validator.validate_envelope`
      — defense-in-depth re-validation of envelopes recovered from logs.
    * Story 2.11 :mod:`loud_fail_harness.thickening_flags` — the four-flag
      namespace whose :func:`is_loud_fail_block_present` predicates the
      marker emission rule.
    * Story 4.11 :mod:`loud_fail_harness.qa_plan_persistence_compromise`
      — :func:`render_compromise_blockquote` PREPENDED unconditionally to
      the ``## Per-AC results`` section body so the FR25 plan-persistence
      compromise (resumability vs purity tradeoff; FR-P2-9 Phase-2 upgrade
      path) is visible at PR-review time without scrolling into the story
      doc. The blockquote is rendered even when the QA envelope's
      ``ac_results`` array is empty — same render-surface single-source-
      of-truth invariant ``qa_behavioral_plan.render_plan_section`` uses
      on the story-doc side.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from types import ModuleType
from typing import Any, Final

import yaml

from loud_fail_harness import thickening_flags as _default_thickening_flags
from loud_fail_harness._shared import find_repo_root, load_schema
from loud_fail_harness.envelope_validator import format_errors, validate_envelope
from loud_fail_harness.cost_telemetry import (
    CostAggregation,
    OtelPipelineProtocol,
    aggregate_costs,
)
from loud_fail_harness.evidence_linkability import (
    DanglingEvidenceRef,
    format_dangling_inline_marker,
    validate_evidence_linkability_at_render,
)
from loud_fail_harness.exceptions import (
    MarkerContextMissing,
    OtelPipelineUnreachable,
    PromptIdCorrelationMissing,
)
from loud_fail_harness.marker_wiring import compute_alphabetical_marker_order
from loud_fail_harness.auto_merge_config import (
    AutoMergeConfig,
    AutoMergeConfigError,
    read_auto_merge_config_from_config_file,
)
from loud_fail_harness.auto_merge_gate import (
    AUTO_MERGE_GATE_NOT_MET_MARKER,
    DEFAULT_ADOPTION_METRICS_PATH,
    AutoMergeGateDecision,
    AutoMergeGateError,
    AutoMergeGateNotMetEmission,
    resolve_and_evaluate_auto_merge_gate,
    surface_auto_merge_gate_not_met,
)
from loud_fail_harness.auto_merge_execution import (
    AUTO_MERGE_SKIPPED_MARKER,
    AutoMergeSkippedEmission,
    attempt_auto_merge,
    skipped_gate_not_met,
    surface_auto_merge_skipped,
)
from loud_fail_harness.qa_a11y_audit import (
    A11Y_BASELINE_STALE_MARKER,
    A11Y_DELTA_EXCEEDED_MARKER,
    A11Y_DELTA_MODE_UNSTABLE_MARKER,
)
from loud_fail_harness.qa_exploratory_heuristics import HEURISTIC_SKIPPED_MARKER
from loud_fail_harness.qa_flakiness_threshold import (
    FLAKINESS_THRESHOLD_EXCEEDED_MARKER,
)
from loud_fail_harness.qa_visual_regression import (
    VISUAL_REGRESSION_BASELINE_MISSING_MARKER,
    VISUAL_REGRESSION_DELTA_EXCEEDED_MARKER,
)
from loud_fail_harness.qa_plan_drift import PLAN_DRIFT_DETECTED_MARKER
from loud_fail_harness.qa_plan_rederivation import (
    PLAN_REDERIVATION_DRIFT_DETECTED_MARKER,
)
from loud_fail_harness.qa_plan_persistence_compromise import (
    render_compromise_blockquote,
)
from loud_fail_harness.bundle_assembly_failure import (
    BUNDLE_ASSEMBLY_FAILED_EXIT_CODE,
    classify_assembly_failure,
    surface_assembly_failure,
)
from loud_fail_harness.review_layer_failure import (
    META_REVIEW_COMPLETENESS,
    REVIEW_LAYER_FAILED_MARKER,
)
from loud_fail_harness.run_state import RunState
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
    validate_marker_emission,
)


# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #


#: The Epic-2 specialist set whose dispatch logs the assembler reads.
#: Identifiers match Story 2.6's ``DispatchedSpecialist`` literal —
#: kebab-case-or-flat-lowercase strings used as the ``specialist``
#: component in :data:`loud_fail_harness.specialist_dispatch.LOG_PATH_TEMPLATE`.
EPIC_2_SPECIALISTS: tuple[str, str, str] = ("dev", "review-bmad", "qa")

#: At Epic 2 there is no retry; every specialist runs at attempt 1
#: per Stories 2.8 + 2.9 + 2.10 (Epic 5 lands retries).
EPIC_2_ATTEMPT_NUMBER: int = 1

#: The ``walking-skeleton-bundle`` marker class identifier from
#: ``schemas/marker-taxonomy.yaml`` lines 210-216 (Story 1.4). Consumed
#: AS-IS; THIS module is the FIRST runtime emitter of the marker (the
#: Story 2.7 placeholder used a fragile prose-comment heuristic, NOT
#: registry-resolved emission).
WALKING_SKELETON_MARKER: str = "walking-skeleton-bundle"

#: Structured (machine-readable, greppable) marker form per AC-4. The
#: legacy form ``<!-- walking-skeleton-bundle: marker_class -->`` (Story
#: 2.7's placeholder) is structurally forbidden — see :func:`_render_marker`
#: docstring for the reasoning.
_MARKER_COMMENT_PREFIX: str = "<!-- bmad-automation:marker "
_MARKER_COMMENT_SUFFIX: str = " -->"


# --------------------------------------------------------------------------- #
# Result dataclass + named exceptions                                         #
# --------------------------------------------------------------------------- #


@dataclasses.dataclass(frozen=True)
class AssembleBundleResult:
    """Return shape of :func:`assemble_bundle` on success.

    Frozen for determinism + hashability per Epic 1 retro Action #2.

    Field semantics:
        * ``bundle_path`` — resolved on-disk path of the written
          bundle markdown file.
        * ``emitted_markers`` — tuple of marker-class identifiers the
          assembler emitted into the bundle's body. At Epic 2 substrate
          state this is exactly ``("walking-skeleton-bundle",)`` per
          AC-4; future epics may add more.
        * ``header_text`` — the rendered Walking Skeleton Mode H2
          section body (the dynamically-assembled prose enumerating
          missing thickenings).
        * ``included_specialists`` — frozenset of specialist
          identifiers whose envelopes were folded into the bundle. At
          Epic 2 scope this is exactly
          ``frozenset({"dev", "review-bmad", "qa"})``.
    """

    bundle_path: pathlib.Path
    emitted_markers: tuple[str, ...]
    header_text: str
    included_specialists: frozenset[str]


class SpecialistDispatchLogNotFound(Exception):
    """Raised by :func:`assemble_bundle` when an expected dispatch log
    file is missing.

    Pattern 5 named-invariant diagnostic. The assembler does NOT
    silently render a partial bundle — every Epic-2 specialist's log is
    required input.
    """

    def __init__(self, *, specialist: str, expected_path: pathlib.Path) -> None:
        self.specialist = specialist
        self.expected_path = expected_path
        super().__init__(
            f"SpecialistDispatchLogNotFound: specialist={specialist!r} "
            f"expected dispatch log at {expected_path} (Story 2.6 "
            f"persist_dispatch_log writes here at NFR-O3 LOG_PATH_TEMPLATE); "
            "bundle assembly cannot render a partial bundle"
        )


class EnvelopeReValidationFailed(Exception):
    """Raised by :func:`assemble_bundle` when an envelope recovered
    from a dispatch log fails re-validation against
    ``schemas/envelope.schema.yaml``.

    Pattern 5 named-invariant diagnostic. Defense-in-depth: Story 2.6's
    :func:`validate_return_envelope` already validated the envelope at
    dispatch return time; this re-validation catches log-file tampering
    and version-skew between log write and bundle read.
    """

    def __init__(self, *, specialist: str, diagnostic: str) -> None:
        self.specialist = specialist
        self.diagnostic = diagnostic
        super().__init__(
            f"EnvelopeReValidationFailed: specialist={specialist!r} "
            f"envelope recovered from dispatch log failed re-validation: "
            f"{diagnostic}"
        )


class RunStateStoryIdMismatch(Exception):
    """Raised by :func:`assemble_bundle` when the on-disk run-state's
    ``story_id`` does not match the assembler's caller-supplied
    ``story_id`` argument.

    Pattern 5 named-invariant diagnostic. Surfaces the inconsistency
    rather than silently rendering a bundle correlated with the wrong
    story.
    """

    def __init__(self, *, expected: str, actual: str) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"RunStateStoryIdMismatch: caller-supplied story_id={expected!r} "
            f"does not match run-state.yaml story_id={actual!r}; "
            "this likely indicates a stale run-state file or a hook-layer "
            "mis-routing of the bundle invocation"
        )


# --------------------------------------------------------------------------- #
# Run-state + log loading                                                     #
# --------------------------------------------------------------------------- #


def _load_run_state(run_state_path: pathlib.Path) -> RunState:
    """Read and Pydantic-validate the run-state YAML.

    ``run-state.yaml`` is human-readable YAML per Pattern 1; the
    Pydantic-side schema is :class:`loud_fail_harness.run_state.RunState`.
    Loud-fail discipline: malformed YAML or schema-violating content
    propagates the underlying ``yaml.YAMLError`` /
    ``pydantic.ValidationError`` unchanged (no swallowing).
    """
    raw = yaml.safe_load(run_state_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(
            f"run-state file at {run_state_path} did not parse to a YAML "
            "mapping at top level"
        )
    return RunState.model_validate(dict(raw))


def _load_run_state_for_merge_decision(
    run_state_path: pathlib.Path,
) -> RunState | None:
    """Best-effort run-state read for the Story-17.3 merge-readiness decision in
    :func:`main`. Returns ``None`` on any read/parse failure rather than raising —
    the AUTHORITATIVE load happens inside :func:`assemble_bundle`, which loud-fails
    on a malformed/absent run-state; a ``None`` here just means "merge-readiness
    is undeterminable → do NOT merge", never silently swallowing the real error
    (the bundle assembler still surfaces it).
    """
    try:
        return _load_run_state(run_state_path)
    except Exception:  # noqa: BLE001 — see docstring; assemble_bundle is authoritative
        return None


def _read_envelope_from_dispatch_log(
    log_path: pathlib.Path,
    *,
    specialist: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Extract the ``return_envelope`` field from a Story-2.6 dispatch log
    and re-validate it.

    Pattern 5: missing file → :exc:`SpecialistDispatchLogNotFound`;
    re-validation failure → :exc:`EnvelopeReValidationFailed`.
    """
    if not log_path.exists():
        raise SpecialistDispatchLogNotFound(
            specialist=specialist, expected_path=log_path
        )
    log_payload = json.loads(log_path.read_text(encoding="utf-8"))
    envelope = log_payload.get("return_envelope")
    if not isinstance(envelope, dict):
        raise EnvelopeReValidationFailed(
            specialist=specialist,
            diagnostic=(
                "dispatch log's `return_envelope` field is missing or not a "
                "JSON object"
            ),
        )
    errors = validate_envelope(envelope, schema)
    if errors:
        raise EnvelopeReValidationFailed(
            specialist=specialist,
            diagnostic=format_errors(errors),
        )
    return envelope


def _resolve_log_path(
    logs_root: pathlib.Path, story_id: str, run_id: str, specialist: str
) -> pathlib.Path:
    """Resolve the canonical NFR-O3 dispatch log path per
    :data:`loud_fail_harness.specialist_dispatch.LOG_PATH_TEMPLATE`.
    """
    return (
        logs_root
        / story_id
        / run_id
        / "logs"
        / f"{specialist}-{EPIC_2_ATTEMPT_NUMBER}.log"
    )


# --------------------------------------------------------------------------- #
# Walking Skeleton Mode header rendering                                      #
# --------------------------------------------------------------------------- #


#: Per-flag header sentence. Each entry is a (flag-name, sentence)
#: pair; the sentence appears verbatim when the flag returns ``False``.
#: Naming the Epic that lands the thickening per the verbatim epic AC at
#: ``epics.md`` Story 2.11 lines 1521-1524.
_THICKENING_SENTENCES: tuple[tuple[str, str], ...] = (
    (
        "is_full_qa_present",
        "Tier-1 evidence only (Epic 4 thickens to Tier-2 + Tier-3-where-configured).",
    ),
    (
        "is_full_review_present",
        "Single-layer review (Epic 3 thickens to 3-layer adversarial pass).",
    ),
    (
        "is_retry_present",
        "No retry (Epic 5 thickens with whole-story retry budget + bucket-driven action item derivation).",
    ),
    (
        "is_loud_fail_block_present",
        "No loud-fail block (Epic 6 thickens with the dedicated top-of-bundle loud-fail block + per-specialist × per-retry cost breakdown + actionable how-to-enable pointers).",
    ),
)


def _render_walking_skeleton_header(flags: ModuleType) -> str:
    """Render the dynamic Walking Skeleton Mode H2 section body.

    Enumerates which thickening flags return ``False``; each False flag
    contributes one sentence naming the missing thickening + the Epic
    that lands it. Per the verbatim epic AC at lines 1521-1524 the
    prose is derived from the flags' return values — never hardcoded
    "Tier-1 only, single-layer review" prose.

    A flag returning ``True`` (post-Epic-3/4/5/6 substrate state)
    causes its corresponding sentence to be omitted from the
    enumeration. At Epic 2 substrate state all four flags return
    ``False`` so all four sentences appear.
    """
    missing: list[str] = []
    for flag_name, sentence in _THICKENING_SENTENCES:
        flag_fn = getattr(flags, flag_name)
        if not flag_fn():
            missing.append(sentence)
    if not missing:
        # All thickenings landed; the bundle is no longer a walking-
        # skeleton. The header section becomes a sentinel acknowledging
        # this. (Not exercised at Epic 2; structural posture for
        # Epic 6 forward-compat.)
        return (
            "All thickening features are present; this bundle is no longer a "
            "walking-skeleton. The Walking Skeleton Mode header section is "
            "retained for structural-historical continuity."
        )
    intro = (
        "This PR bundle is a walking-skeleton — it enumerates the structural "
        "shape of the BMAD automation loop while the following thickenings "
        "remain unfinished:"
    )
    bullet_lines = [f"- {sentence}" for sentence in missing]
    return intro + "\n\n" + "\n".join(bullet_lines)


# --------------------------------------------------------------------------- #
# Section renderers                                                           #
# --------------------------------------------------------------------------- #


def _render_per_ac_section(
    qa_envelope: dict[str, Any],
    *,
    marker_registry: MarkerClassRegistry,
    qa_evidence_dangling: tuple[DanglingEvidenceRef, ...] = (),
) -> str:
    """Render the ``## Per-AC results`` section from QA's envelope's
    ``ac_results`` array (FR55), followed by the optional Story-4.2
    ``### Plan drift detected`` sub-section when QA's envelope's
    ``plan_drift`` field is non-null, followed by the optional
    Story-4.9 ``### Exploratory heuristic findings`` sub-section when
    EITHER ``findings`` carries verification-mode-tagged entries OR
    ``heuristic_skipped_emissions`` is non-empty.

    At Epic 2 scope ``ac_results`` carries exactly one entry per Story
    2.10's AC-2; the renderer is structurally agnostic to the array
    length. Each entry surfaces ``ac_id``, ``status``, ``assertions``,
    ``evidence_refs``, ``semantic_verification``.

    Story 4.2 thickening (AC-5): when ``qa_envelope.get("plan_drift")``
    is a non-null object the renderer appends an
    ``### Plan drift detected`` H3 sub-section AFTER the ``ac_results``
    blocks, carrying the four diagnostic-context bullets in human-
    readable form + the structured marker comment
    ``<!-- bmad-automation:marker plan-drift-detected -->`` co-located.

    Story 4.9 thickening (AC-9): the renderer partitions the QA
    envelope's TOP-LEVEL ``findings`` array on the ``verification_mode``
    discriminator (heuristic findings vs AC-driven findings). When the
    heuristic-findings partition is non-empty OR the optional
    ``heuristic_skipped_emissions`` array is non-empty, the renderer
    appends an ``### Exploratory heuristic findings`` H3 sub-section
    AFTER ``### Plan drift detected``. AC-driven findings are NOT
    rendered by this section (Story 4.13 may add an AC-driven-findings
    render section as part of wrapper-thickening completion).

    Story 6.6 thickening (AC-1): when ``qa_evidence_dangling`` is a
    non-empty tuple of :class:`DanglingEvidenceRef` (the qa-evidence
    partition from
    :func:`loud_fail_harness.evidence_linkability.validate_evidence_linkability_at_render`),
    each evidence-bullet whose ``(ac_id, path)`` matches an entry in
    the tuple gets an inline ``— ⚠️ dangling-evidence-ref: qa-evidence
    — Remediation: regenerate the evidence OR fix the reference``
    suffix appended to the existing backtick-path bullet. Default
    empty preserves byte-stable behavior for callers that don't
    validate.

    Story 20.3 thickening (FR-P2-8 / AC-5): when the QA envelope's optional
    ``flakiness_emissions`` array is non-empty the renderer appends a
    ``### Flakiness threshold exceeded`` H3 sub-section AFTER the heuristic
    sub-section, emitting the per-AC ``<!-- bmad-automation:marker
    flakiness-threshold-exceeded -->`` comment co-located so the longitudinal
    marker is greppable in the bundle.

    Story 21.0 thickening (FR-P2-6 / FR-P2-10): when the QA envelope's optional
    ``a11y_emissions`` / ``visual_regression_emissions`` arrays carry AC-scoped
    entries, the renderer appends an ``### Accessibility audit findings`` and an
    ``### Visual regression findings`` H3 sub-section (in that order) AFTER the
    flakiness sub-section, each co-locating its per-AC ``<!-- bmad-automation:marker
    a11y-* -->`` / ``visual-regression-* -->`` comment. The envelope-scoped
    ``a11y-delta-mode-unstable`` is NOT rendered here — it lands at the bundle
    bottom via :func:`_render_qa_a11y_envelope_scoped_marker`.
    """
    dangling_index: dict[tuple[str, str], DanglingEvidenceRef] = {
        (ref.ac_id, ref.path): ref
        for ref in qa_evidence_dangling
        if ref.ac_id is not None
    }
    entries = qa_envelope.get("ac_results") or []
    if not entries:
        ac_results_body = "_(no ac_results in QA envelope)_"
    else:
        blocks: list[str] = []
        for entry in entries:
            ac_id = entry.get("ac_id", "(unknown)")
            status = entry.get("status", "(unknown)")
            assertions = entry.get("assertions") or []
            evidence_refs = entry.get("evidence_refs") or []
            semantic_verification = entry.get("semantic_verification", "not_applicable")
            block_lines = [
                f"### {ac_id} — status: `{status}`",
                "",
                "**Assertions:**",
            ]
            if assertions:
                block_lines.extend(f"- {assertion}" for assertion in assertions)
            else:
                block_lines.append("- _(none)_")
            block_lines.append("")
            block_lines.append("**Evidence:**")
            if evidence_refs:
                # Story 4.8 transitive shim: evidence_refs items are now
                # objects {path, tier} (post-bump $defs/evidence_ref) — render
                # the path string in backticks for backward-compat with the
                # pre-Story-4.8 bundle visual surface. Story 4.13 owns the
                # tier-aware render upgrade per the FR16-FR25 thickening
                # surface. Pre-Story-4.8 string items still
                # render correctly via the str(ref) fallback. Story 6.6
                # appends an inline dangling-evidence-ref indicator when the
                # (ac_id, path) tuple matches a qa_evidence_dangling entry.
                for ref in evidence_refs:
                    if isinstance(ref, dict) and "path" in ref:
                        path_str = ref["path"]
                    else:
                        path_str = str(ref)
                    bullet = f"- `{path_str}`"
                    dangling_ref = dangling_index.get(
                        (ac_id, path_str)
                    )
                    if dangling_ref is not None:
                        bullet = (
                            f"{bullet} — "
                            f"{format_dangling_inline_marker(ref=dangling_ref)}"
                        )
                    block_lines.append(bullet)
            else:
                block_lines.append("- _(none)_")
            block_lines.append("")
            block_lines.append(
                f"**Semantic verification:** `{semantic_verification}`"
            )
            blocks.append("\n".join(block_lines))
        ac_results_body = "\n\n".join(blocks)

    plan_drift_body = _render_qa_plan_drift_subsection(
        qa_envelope, marker_registry=marker_registry
    )
    rederivation_line = _render_qa_plan_rederivation_line(qa_envelope)
    rederivation_body = _render_qa_plan_rederivation_subsection(
        qa_envelope, marker_registry=marker_registry
    )
    heuristic_body = _render_qa_heuristic_findings_subsection(
        qa_envelope, marker_registry=marker_registry
    )
    flakiness_body = _render_qa_flakiness_subsection(
        qa_envelope, marker_registry=marker_registry
    )
    a11y_body = _render_qa_a11y_subsection(
        qa_envelope, marker_registry=marker_registry
    )
    visual_body = _render_qa_visual_subsection(
        qa_envelope, marker_registry=marker_registry
    )

    # Story 4.11 (FR25): the plan-persistence-compromise blockquote is
    # PREPENDED unconditionally — present even when ``ac_results`` is
    # empty/missing. The compromise applies to the QA Behavioral Plan
    # persistence concept itself (resumability vs purity tradeoff), not
    # to the per-AC results, so the placeholder body still shows the
    # blockquote above it. The canonical prose is sourced from
    # :func:`loud_fail_harness.qa_plan_persistence_compromise.render_compromise_blockquote`
    # — same single-source-of-truth invariant ``render_plan_section``
    # uses on the story-doc side.
    # Story 20.1 (FR-P2-9): the per-run plan re-derivation cross-check line
    # is co-located with the FR25 compromise blockquote (AC-5:
    # retain-and-accompany) — rendered on EVERY reuse-existing run that
    # populated the `plan_rederivation` field (green or drift). The
    # `### Plan re-derivation drift detected` H3 sub-section + structured
    # marker comment ride after `### Plan drift detected` on the drift branch.
    parts = [render_compromise_blockquote().rstrip("\n")]
    if rederivation_line:
        parts.append(rederivation_line)
    parts.append(ac_results_body)
    if plan_drift_body:
        parts.append(plan_drift_body)
    if rederivation_body:
        parts.append(rederivation_body)
    if heuristic_body:
        parts.append(heuristic_body)
    if flakiness_body:
        parts.append(flakiness_body)
    if a11y_body:
        parts.append(a11y_body)
    if visual_body:
        parts.append(visual_body)
    return "\n\n".join(parts)


def _render_qa_plan_drift_subsection(
    qa_envelope: dict[str, Any],
    *,
    marker_registry: MarkerClassRegistry,
) -> str:
    """Render the Story-4.2 ``### Plan drift detected`` H3 sub-section
    when QA's envelope ``plan_drift`` field is non-null; return the empty
    string otherwise (silent at the bundle-side path).

    The sub-section carries the four diagnostic-context items in human-
    readable form (``story_id``, ``prior_plan_status``, ``prior_ac_hash``,
    ``current_ac_hash``) per the verbatim epic AC at ``epics.md``
    line 1851 + the structured marker comment
    ``<!-- bmad-automation:marker plan-drift-detected -->`` co-located
    so the bundle carries the marker per the verbatim epic AC at
    ``epics.md`` line 1850. The full 64-char SHA-256 hex digests are
    rendered verbatim for tooling consumers (no truncation; the
    diagnostic surface is fidelity-preserving).

    Defense-in-depth re-validation per Pattern 5 (mirrors Story 3.3 at
    line 589): :func:`validate_marker_emission` fires once when
    ``plan_drift`` is non-null. The wrapper-side
    :func:`loud_fail_harness.qa_plan_drift.surface_plan_drift` already
    validated; the assembler validates again at render time. Registry
    rejection raises :exc:`UnknownMarkerClass` per Pattern 5.

    Story 3.4's ``walking-skeleton-bundle`` marker emission rule and
    Story 3.3's ``review-layer-failed`` per-layer marker emission are
    NOT modified — both continue to emit independently per their own
    structural predicates.
    """
    plan_drift = qa_envelope.get("plan_drift")
    if plan_drift is None:
        return ""

    validate_marker_emission(marker_registry, PLAN_DRIFT_DETECTED_MARKER)

    story_id = plan_drift.get("story_id", "(unknown)")
    prior_plan_status = plan_drift.get("prior_plan_status", "(unknown)")
    prior_ac_hash = plan_drift.get("prior_ac_hash", "(unknown)")
    current_ac_hash = plan_drift.get("current_ac_hash", "(unknown)")

    lines = [
        "### Plan drift detected",
        "",
        _render_marker(PLAN_DRIFT_DETECTED_MARKER),
        "",
        f"- Story ID: `{story_id}`",
        f"- Prior plan_status: `{prior_plan_status}`",
        f"- Prior ac_hash: `{prior_ac_hash}`",
        f"- Current ac_hash: `{current_ac_hash}`",
    ]
    return "\n".join(lines)


def _render_qa_plan_rederivation_line(qa_envelope: dict[str, Any]) -> str:
    """Render the Story-20.1 (FR-P2-9) ``FR-P2-9 cross-check: green`` /
    ``… drift detected`` line co-located with the FR25 compromise blockquote
    when QA's envelope ``plan_rederivation`` field is non-null; return the
    empty string otherwise (silent — the field is absent on non-reuse runs).

    The line is rendered on EVERY reuse-existing run (the field carries
    ``cross_check_status: green`` on agreement) so the substrate-level
    guarantee is inspectable in the bundle even when nothing drifted (AC-5).
    """
    plan_rederivation = qa_envelope.get("plan_rederivation")
    if plan_rederivation is None:
        return ""
    status = plan_rederivation.get("cross_check_status")
    if status == "drift-detected":
        return "> FR-P2-9 cross-check: drift detected"
    if status == "green":
        return "> FR-P2-9 cross-check: green"
    return ""


def _render_qa_plan_rederivation_subsection(
    qa_envelope: dict[str, Any],
    *,
    marker_registry: MarkerClassRegistry,
) -> str:
    """Render the Story-20.1 (FR-P2-9) ``### Plan re-derivation drift
    detected`` H3 sub-section when QA's envelope ``plan_rederivation`` field
    carries ``cross_check_status == "drift-detected"``; return the empty
    string otherwise (silent on green and on the absent field).

    The sub-section carries the diagnostic items in human-readable form
    (``story_id``, ``drift_surfaces``, ``drifted_ac_ids``) + the structured
    marker comment ``<!-- bmad-automation:marker
    plan-rederivation-drift-detected -->`` co-located so the bundle carries
    the marker. Defense-in-depth re-validation per Pattern 5 (mirrors
    :func:`_render_qa_plan_drift_subsection`): :func:`validate_marker_emission`
    fires once when the drift branch renders; registry rejection raises
    :exc:`UnknownMarkerClass`.

    FR23's ``### Plan drift detected`` render (AC-hash channel) is NOT
    modified — FR-P2-9 is additive; both sub-sections render independently
    per their own structural predicates.
    """
    plan_rederivation = qa_envelope.get("plan_rederivation")
    if plan_rederivation is None:
        return ""
    if plan_rederivation.get("cross_check_status") != "drift-detected":
        return ""

    validate_marker_emission(
        marker_registry, PLAN_REDERIVATION_DRIFT_DETECTED_MARKER
    )

    story_id = plan_rederivation.get("story_id", "(unknown)")
    drift_surfaces = plan_rederivation.get("drift_surfaces") or []
    drifted_ac_ids = plan_rederivation.get("drifted_ac_ids") or []
    surfaces_render = ", ".join(f"`{s}`" for s in drift_surfaces) or "_(none)_"
    ac_ids_render = ", ".join(f"`{a}`" for a in drifted_ac_ids) or "_(none)_"

    lines = [
        "### Plan re-derivation drift detected",
        "",
        _render_marker(PLAN_REDERIVATION_DRIFT_DETECTED_MARKER),
        "",
        f"- Story ID: `{story_id}`",
        f"- Drift surfaces: {surfaces_render}",
        f"- Drifted AC IDs: {ac_ids_render}",
    ]
    return "\n".join(lines)



def _render_qa_flakiness_subsection(
    qa_envelope: dict[str, Any],
    *,
    marker_registry: MarkerClassRegistry,
) -> str:
    """Render the Story-20.3 (FR-P2-8) ``### Flakiness threshold exceeded`` H3
    sub-section when QA's envelope ``flakiness_emissions`` array is non-empty;
    return the empty string otherwise (silent — the array is absent on runs where
    no AC crossed the longitudinal threshold).

    Each emission carries ``{marker_class, ac_id}``; the renderer emits the per-AC
    diagnostic prose + the structured ``<!-- bmad-automation:marker
    flakiness-threshold-exceeded -->`` marker comment co-located at the per-AC
    location, so the longitudinal marker is greppable in the bundle exactly as
    every sibling QA-evidence marker (``heuristic-skipped`` / ``plan-*`` /
    ``a11y-*`` / ``visual-regression-*``) is.

    Defense-in-depth re-validation per Pattern 5 (mirrors
    :func:`_render_qa_heuristic_findings_subsection`):
    :func:`validate_marker_emission` fires once per emission; registry rejection
    raises :exc:`UnknownMarkerClass`.
    """
    emissions = qa_envelope.get("flakiness_emissions") or []
    if not emissions:
        return ""

    lines = [
        "### Flakiness threshold exceeded",
        "",
        "Longitudinal flakiness surfaced by the FR-P2-8 across-runs threshold",
        "(Story 20.3): the AC's most-recent consecutive QA runs each needed an",
        "action-level transient retry. Story-level evidence — does NOT flip the",
        "AC verdict (sensor-not-advisor); inspect the gitignored flakiness log at",
        "`_bmad-output/qa-flakiness/<story-id>.yaml`.",
    ]
    for emission in emissions:
        validate_marker_emission(
            marker_registry, FLAKINESS_THRESHOLD_EXCEEDED_MARKER
        )
        ac_id = emission["ac_id"]
        lines.append("")
        lines.append(
            f"AC `{ac_id}` crossed the consecutive-transient-fail threshold."
        )
        lines.append(_render_marker(FLAKINESS_THRESHOLD_EXCEEDED_MARKER))

    return "\n".join(lines)


def _render_auto_merge_gate_not_met_subsection(
    emission: AutoMergeGateNotMetEmission | None,
    *,
    gate_config_error: str | None = None,
    marker_registry: MarkerClassRegistry,
) -> str:
    """Render the Story-17.2 (FR-P2-3) ``### Auto-merge gate not met`` H3
    sub-section when the auto-merge gate-condition evaluator surfaced an emission
    (a configured gate was unmet at Stop-hook time); return the empty string
    otherwise (silent — there is no emission on ``green`` / ``not-configured``
    decisions, the latter being the shipped default).

    When ``gate_config_error`` is set (adoption-metrics absent or malformed),
    renders a ``### Auto-merge gate — configuration error`` sub-section instead
    so the bundle still captures the problem rather than silently omitting the
    gate section.

    Mirrors :func:`_render_qa_flakiness_subsection`'s emit/render split: the
    evaluator (:mod:`loud_fail_harness.auto_merge_gate`) EMITS; the assembler
    RENDERS the diagnostic prose + the co-located ``<!-- bmad-automation:marker
    auto-merge-gate-not-met -->`` comment so the orchestrator-domain marker is
    greppable in the bundle exactly as every sibling observability marker is.

    Defense-in-depth re-validation per Pattern 5:
    :func:`validate_marker_emission` fires once; registry rejection raises
    :exc:`UnknownMarkerClass`.
    """
    if emission is None and gate_config_error is None:
        return ""
    if gate_config_error is not None:
        lines = [
            "### Auto-merge gate — configuration error",
            "",
            f"The FR-P2-3 auto-merge gate evaluator could not run: {gate_config_error}",
            "",
            "Fix `adoption-metrics.yaml` or the auto-merge config and re-run.",
        ]
        return "\n".join(lines)
    assert emission is not None
    validate_marker_emission(marker_registry, AUTO_MERGE_GATE_NOT_MET_MARKER)
    lines = [
        "### Auto-merge gate not met",
        "",
        "The FR-P2-3 auto-merge gate-condition evaluator (Story 17.2) found at",
        "least one configured gate unmet at Stop-hook time. INFORMATIONAL",
        "(sensor-not-advisor) — does NOT merge, advance state, or flip any wrapper",
        "status; auto-merge is gated by data, not intention, and Story 17.3 owns",
        "the merge decision.",
        "",
        emission.diagnostic_pointer,
        _render_marker(AUTO_MERGE_GATE_NOT_MET_MARKER),
    ]
    return "\n".join(lines)


def _render_auto_merge_skipped_subsection(
    emission: AutoMergeSkippedEmission | None,
    *,
    marker_registry: MarkerClassRegistry,
) -> str:
    """Render the Story-17.3 (FR-P2-3) ``### Auto-merge skipped`` H3 sub-section
    when the auto-merge execution actuator was armed but the merge did not
    complete; return the empty string otherwise (silent — there is no emission on
    a successful merge, on a non-merge-ready bundle, or on the ``enabled: false``
    shipped default).

    Mirrors :func:`_render_auto_merge_gate_not_met_subsection`'s emit/render
    split: the actuator (:mod:`loud_fail_harness.auto_merge_execution`) EMITS; the
    assembler RENDERS the diagnostic prose + the co-located ``<!--
    bmad-automation:marker auto-merge-skipped -->`` comment so the
    orchestrator-domain marker is greppable in the bundle exactly as every sibling
    observability marker is.

    Defense-in-depth re-validation per Pattern 5:
    :func:`validate_marker_emission` fires once; registry rejection raises
    :exc:`UnknownMarkerClass`.
    """
    if emission is None:
        return ""
    validate_marker_emission(marker_registry, AUTO_MERGE_SKIPPED_MARKER)
    lines = [
        "### Auto-merge skipped",
        "",
        "The FR-P2-3 auto-merge execution actuator (Story 17.3) was armed",
        "(`auto_merge.enabled: true`) on a merge-ready bundle but the merge did",
        f"NOT complete (reason: `{emission.skip_reason}`). The PR remains in draft",
        "for human handling — failure is loud, never silent (NFR-R6).",
        "INFORMATIONAL (sensor-not-advisor) — does NOT change run state, flip any",
        "wrapper status, or retry the merge.",
        "",
        emission.diagnostic_pointer,
        _render_marker(AUTO_MERGE_SKIPPED_MARKER),
    ]
    return "\n".join(lines)


_A11Y_AC_SCOPED_MARKERS: Final = frozenset(
    {A11Y_BASELINE_STALE_MARKER, A11Y_DELTA_EXCEEDED_MARKER}
)

_A11Y_AC_DIAGNOSTIC: Final = {
    A11Y_BASELINE_STALE_MARKER: (
        "the a11y baseline was missing or refreshed (no prior delta could be computed)"
    ),
    A11Y_DELTA_EXCEEDED_MARKER: (
        "the a11y violation-key delta exceeded the configured threshold"
    ),
}

_VISUAL_DIAGNOSTIC: Final = {
    VISUAL_REGRESSION_DELTA_EXCEEDED_MARKER: (
        "the visual mismatched-pixel-ratio delta exceeded the configured threshold"
    ),
    VISUAL_REGRESSION_BASELINE_MISSING_MARKER: (
        "the visual baseline was missing (a new baseline was captured this run)"
    ),
}


def _render_qa_a11y_subsection(
    qa_envelope: dict[str, Any],
    *,
    marker_registry: MarkerClassRegistry,
) -> str:
    """Render the Story-21.0 (FR-P2-6) ``### Accessibility audit findings`` H3
    sub-section for the TWO AC-scoped a11y classes (``a11y-baseline-stale`` /
    ``a11y-delta-exceeded``) when QA's envelope ``a11y_emissions`` array carries
    such entries; return the empty string otherwise (silent — the array is
    absent on api/mobile, on ``a11y.enabled: false``, and on the unconfigured
    default, per ``agents/qa.md:144``).

    The envelope-scoped ``a11y-delta-mode-unstable`` (``pointer_context_fields:
    []`` — NO ``ac_id``) is FILTERED OUT here and rendered at the bundle bottom
    by :func:`_render_qa_a11y_envelope_scoped_marker` (the canonical envelope-
    scoped location, mirroring ``marker_emissions``).

    Byte-mirrors :func:`_render_qa_flakiness_subsection`: per-emission diagnostic
    prose + the co-located ``<!-- bmad-automation:marker a11y-* -->`` comment.
    Defense-in-depth re-validation per Pattern 5: :func:`validate_marker_emission`
    fires once per emission; registry rejection raises :exc:`UnknownMarkerClass`.
    """
    emissions = [
        emission
        for emission in (qa_envelope.get("a11y_emissions") or [])
        if emission.get("marker_class") in _A11Y_AC_SCOPED_MARKERS
    ]
    if not emissions:
        return ""

    lines = [
        "### Accessibility audit findings",
        "",
        "Accessibility-audit signal surfaced by the Epic-19 a11y delta engine",
        "(FR-P2-6). Story-level evidence — does NOT flip the AC verdict",
        "(sensor-not-advisor); inspect the gitignored per-AC baselines under",
        "`_bmad-output/qa-a11y-baseline/<story-id>/<ac-id>/`.",
    ]
    for emission in emissions:
        marker_class = emission["marker_class"]
        validate_marker_emission(marker_registry, marker_class)
        ac_id = emission["ac_id"]
        lines.append("")
        lines.append(f"AC `{ac_id}`: {_A11Y_AC_DIAGNOSTIC[marker_class]}.")
        lines.append(_render_marker(marker_class))

    return "\n".join(lines)


def _render_qa_visual_subsection(
    qa_envelope: dict[str, Any],
    *,
    marker_registry: MarkerClassRegistry,
) -> str:
    """Render the Story-21.0 (FR-P2-10) ``### Visual regression findings`` H3
    sub-section when QA's envelope ``visual_regression_emissions`` array is
    non-empty; return the empty string otherwise (silent — the array is absent
    on api, on ``visual_regression.enabled: false``, and on the unconfigured
    default, per ``agents/qa.md:145``).

    BOTH visual classes (``visual-regression-delta-exceeded`` /
    ``visual-regression-baseline-missing``) are AC-scoped, so no filtering is
    needed beyond the array — a near-verbatim clone of
    :func:`_render_qa_flakiness_subsection`. Per-emission diagnostic prose + the
    co-located ``<!-- bmad-automation:marker visual-regression-* -->`` comment;
    Pattern-5 :func:`validate_marker_emission` fires once per emission.
    """
    emissions = qa_envelope.get("visual_regression_emissions") or []
    if not emissions:
        return ""

    lines = [
        "### Visual regression findings",
        "",
        "Visual-regression signal surfaced by the Epic-19 pixelmatch delta engine",
        "(FR-P2-10). Story-level evidence — does NOT flip the AC verdict",
        "(sensor-not-advisor); inspect the gitignored per-AC baselines under",
        "`_bmad-output/qa-visual-baseline/<story-id>/<ac-id>/`.",
    ]
    for emission in emissions:
        marker_class = emission["marker_class"]
        validate_marker_emission(marker_registry, marker_class)
        ac_id = emission["ac_id"]
        lines.append("")
        lines.append(f"AC `{ac_id}`: {_VISUAL_DIAGNOSTIC[marker_class]}.")
        lines.append(_render_marker(marker_class))

    return "\n".join(lines)


def _render_qa_a11y_envelope_scoped_marker(
    qa_envelope: dict[str, Any],
    *,
    marker_registry: MarkerClassRegistry,
) -> str:
    """Render the Story-21.0 (FR-P2-6) envelope-scoped ``a11y-delta-mode-unstable``
    marker comment for the bundle bottom; return the empty string when no such
    entry is present.

    Unlike the two AC-scoped a11y classes, ``a11y-delta-mode-unstable`` has
    ``pointer_context_fields: []`` (no ``ac_id``) — it is a run-level
    "delta mode was unstable, full-report fallback" signal, NOT an AC finding.
    Per ``agents/qa.md:144`` it renders at the bundle bottom, the same canonical
    location the walking-skeleton ``emitted_markers`` use in
    :func:`assemble_bundle`'s ``body_parts`` tail (which :func:`_render_per_ac_section`
    cannot reach). Pattern-5 :func:`validate_marker_emission` fires once.
    """
    for emission in qa_envelope.get("a11y_emissions") or []:
        if emission.get("marker_class") == A11Y_DELTA_MODE_UNSTABLE_MARKER:
            validate_marker_emission(marker_registry, A11Y_DELTA_MODE_UNSTABLE_MARKER)
            return _render_marker(A11Y_DELTA_MODE_UNSTABLE_MARKER)
    return ""


def _render_qa_heuristic_findings_subsection(
    qa_envelope: dict[str, Any],
    *,
    marker_registry: MarkerClassRegistry,
) -> str:
    """Render the Story-4.9 ``### Exploratory heuristic findings`` H3
    sub-section when EITHER the QA envelope's top-level ``findings``
    array carries entries with ``verification_mode ==
    "exploratory-heuristic"`` OR the optional
    ``heuristic_skipped_emissions`` array is non-empty; return the
    empty string otherwise (silent at the bundle-side path).

    The sub-section partitions the top-level ``findings`` array on the
    ``verification_mode`` discriminator field (Story 4.9 AC-9):
    heuristic findings (carrying
    ``verification_mode == "exploratory-heuristic"``) are rendered as
    bullets via :func:`_render_finding_bullet`; AC-driven findings
    (without ``verification_mode``) are NOT rendered by this section.
    Per-emission diagnostic prose + the ``heuristic-skipped:
    <sub_classification>`` marker comment pair are co-located inside
    the same sub-section.

    Defense-in-depth re-validation per Pattern 5 (mirrors Story 3.3 +
    Story 4.2): :func:`validate_marker_emission` fires once per
    emission entry. Registry rejection raises
    :exc:`UnknownMarkerClass` per Pattern 5.
    """
    findings = qa_envelope.get("findings") or []
    heuristic_findings = [
        f for f in findings
        if isinstance(f, dict)
        and f.get("verification_mode") == "exploratory-heuristic"
    ]
    emissions = qa_envelope.get("heuristic_skipped_emissions") or []

    if not heuristic_findings and not emissions:
        return ""

    lines = [
        "### Exploratory heuristic findings",
        "",
        "Synthetic findings surfaced by the three MVP exploratory heuristics",
        "(empty-state / error-state / auth-boundary) per FR22. Distinct from",
        "AC-driven findings: these are exploratory drift-catching observations,",
        "not per-AC verification verdicts.",
    ]

    if heuristic_findings:
        lines.append("")
        lines.extend(_render_finding_bullet(f) for f in heuristic_findings)

    for emission in emissions:
        validate_marker_emission(marker_registry, HEURISTIC_SKIPPED_MARKER)
        sub_classification = emission.get("sub_classification", "(unknown)")
        lines.append("")
        lines.append(
            f"Heuristic {sub_classification} skipped — structurally "
            "inapplicable to this story per the QA Behavioral Plan's "
            "`heuristic_applicability` field."
        )
        lines.append(
            f"<!-- bmad-automation:marker {HEURISTIC_SKIPPED_MARKER}: "
            f"{sub_classification} -->"
        )

    return "\n".join(lines)


#: Story 3.4 AC-1 fixed bucket order — the canonical FR27 enum from
#: ``schemas/envelope.schema.yaml`` ``$defs/finding.bucket`` (lines 127-129).
#: The renderer iterates this tuple to produce per-bucket sub-sections in
#: deterministic order; out-of-enum values would have been rejected at
#: ``validate_envelope`` upstream per the Story 3.2 passthrough invariant.
_BUCKET_ORDER: tuple[str, ...] = ("decision_needed", "patch", "defer", "dismiss")

#: Story 3.4 AC-1 fixed severity order — the canonical FR27 enum from
#: ``schemas/envelope.schema.yaml`` ``$defs/finding.severity`` (lines 130-132).
_SEVERITY_ORDER: tuple[str, ...] = ("HIGH", "MED", "LOW")


def _render_finding_bullet(finding: dict[str, Any]) -> str:
    """Render a single finding bullet with source-layer attribution.

    Story 3.4 AC-1: each bullet surfaces the finding's ``id`` (rendered
    as inline code), ``title``, ``source`` layer name (rendered as an
    ``[<layer>]`` square-bracket prefix tag), and ``location`` (rendered
    as inline code when non-empty). The ``source`` enum permits ``blind``
    / ``edge`` / ``auditor`` / ``merged`` for the Review-BMAD wrapper's
    own findings AND ``qa`` / ``lad`` for cross-specialist envelopes
    (``envelope.schema.yaml`` lines 115-117); whatever value the finding
    carries is rendered verbatim.
    """
    fid = finding.get("id", "(unknown)")
    title = finding.get("title", "(no title)")
    source = finding.get("source", "(unknown)")
    location = finding.get("location", "")
    if location:
        return f"- [{source}] `{fid}` — {title} (`{location}`)"
    return f"- [{source}] `{fid}` — {title}"


def _render_review_findings_section(
    review_envelope: dict[str, Any],
    *,
    marker_registry: MarkerClassRegistry,
) -> str:
    """Render the ``## Review findings`` section grouped by ``bucket`` ×
    ``severity`` with source-layer attribution (Story 3.4 AC-1).

    Layer-produced content findings (those whose ``meta`` field is NOT
    set to the synthetic-meta-finding discriminator ``META_REVIEW_COMPLETENESS``
    imported from :mod:`loud_fail_harness.review_layer_failure`) are
    partitioned by ``bucket`` ∈ ``(decision_needed, patch, defer,
    dismiss)`` in fixed order, then by ``severity`` ∈
    ``(HIGH, MED, LOW)`` within each non-empty bucket.
    Empty bucket/severity slots are elided (no orphan headers). Each
    bullet carries its ``source`` layer name as a ``[<layer>]`` prefix
    tag per Story 3.1's layer-attribution discipline preserved through
    triage.

    Synthetic findings carrying the ``META_REVIEW_COMPLETENESS``
    discriminator on their ``meta`` field (Story 3.3 AC-2 schema bump;
    emitted by ``surface_failed_layers``) are rendered in a SEPARATE
    sub-section appearing AFTER the bucket × severity sections under a
    dedicated heading naming the synthetic-meta-finding nature so the
    human reviewer can distinguish "the wrapper synthesized this because
    a layer crashed" (Story 3.3 channel-3 surface) from "a layer
    observed this in the diff" (the Blind Hunter / Edge Case Hunter /
    Acceptance Auditor content findings).

    On empty ``findings`` AND empty ``failed_layers`` the section body is
    ``_(no findings)_`` + ``Failed layers: (none)`` (legacy placeholders
    preserved per Story 3.4 AC-1 (d)).

    Story 3.3 thickening (AC-4) PRESERVED VERBATIM: when ``failed_layers``
    is non-empty, one ``<!-- bmad-automation:marker review-layer-failed:
    <layer> -->`` HTML-comment marker is rendered per failed layer
    co-located with the existing "Failed layers: ..." prose, with the
    per-layer ``validate_marker_emission`` defense-in-depth call firing
    exactly once per failed layer (the AC-9 CI lint
    ``review-layer-failure-emission-gate`` structurally allowlists this
    canonical site). When ``failed_layers`` is empty, ZERO marker
    comments are rendered (silent at channel 2 for the zero-failure
    path; per Story 3.3 AC-1 channel-2 silence invariant).
    """
    findings = review_envelope.get("findings") or []
    failed_layers = review_envelope.get("failed_layers") or []

    # Story 3.4 AC-1 partition: layer-produced content findings vs
    # synthetic meta-findings carrying the META_REVIEW_COMPLETENESS
    # discriminator (the Story 3.3 channel-3 surface). The discriminator
    # is the partitioning key per the verbatim Story 3.4 AC at epics.md
    # line 1729; a synthetic meta finding's bucket is decision_needed by
    # Story 3.3 AC-1 contract, but it does NOT render in the bucket
    # sub-section — it renders in the dedicated meta sub-section.
    content_findings: list[dict[str, Any]] = [
        f for f in findings if f.get("meta") != META_REVIEW_COMPLETENESS
    ]
    meta_findings: list[dict[str, Any]] = [
        f for f in findings if f.get("meta") == META_REVIEW_COMPLETENESS
    ]

    section_chunks: list[str] = []

    # Bucket × severity grouping for layer-produced content findings.
    bucket_chunks: list[str] = []
    for bucket in _BUCKET_ORDER:
        in_bucket = [f for f in content_findings if f.get("bucket") == bucket]
        if not in_bucket:
            continue
        severity_chunks: list[str] = []
        for severity in _SEVERITY_ORDER:
            in_severity = [f for f in in_bucket if f.get("severity") == severity]
            if not in_severity:
                continue
            severity_chunks.append(
                f"**{severity}:**\n"
                + "\n".join(_render_finding_bullet(f) for f in in_severity)
            )
        if severity_chunks:
            bucket_chunks.append(
                f"### bucket: {bucket}\n\n" + "\n\n".join(severity_chunks)
            )
    if bucket_chunks:
        section_chunks.append("\n\n".join(bucket_chunks))

    # Synthetic meta-finding sub-section (rendered AFTER bucket sections
    # so layer-produced content findings read first per the AC-1 (b)
    # recommended placement).
    if meta_findings:
        meta_lines = [
            "### Review-completeness meta-findings (synthetic; per Story 3.3)",
            "",
        ]
        meta_lines.extend(_render_finding_bullet(f) for f in meta_findings)
        section_chunks.append("\n".join(meta_lines))

    if not content_findings and not meta_findings:
        # AC-1 (d) empty-array case: preserve the legacy placeholder when
        # no findings exist at all. (When `failed_layers` is non-empty
        # but `findings` is empty, this branch still applies — the
        # findings body renders the placeholder, and the failed_layers
        # prose + per-layer markers render below.)
        findings_body = "_(no findings)_"
    else:
        findings_body = "\n\n".join(section_chunks)

    if failed_layers:
        failed_layers_body_lines = [
            "Failed layers: "
            + ", ".join(f"`{layer}`" for layer in failed_layers)
        ]
        for layer in failed_layers:
            # Defense-in-depth re-validation per Pattern 5 — wrapper-side
            # surface_failed_layers already validated; the assembler
            # validates again at render time. Per-layer call mirrors the
            # AC-1 "exactly once per failed layer" invariant the AC-9
            # CI lint structurally enforces upstream.
            validate_marker_emission(marker_registry, REVIEW_LAYER_FAILED_MARKER)
            failed_layers_body_lines.append(
                _render_per_layer_marker(REVIEW_LAYER_FAILED_MARKER, layer)
            )
        failed_layers_body = "\n".join(failed_layers_body_lines)
    else:
        failed_layers_body = "Failed layers: (none)"

    return findings_body + "\n\n" + failed_layers_body


def _fenced_code_block(content: str) -> str:
    """Wrap content in a CommonMark fenced code block with dynamic fence length.

    Counts the longest consecutive backtick run in ``content`` and uses one
    more backtick for the fence, per CommonMark spec §4.5. This prevents any
    line in the content that starts with three or more backticks (e.g. a commit
    message containing an inline code example) from prematurely closing the
    fence. The content itself is never modified — only the surrounding delimiter
    adapts.
    """
    max_run = max(
        (len(m.group()) for m in re.finditer(r"`+", content)),
        default=0,
    )
    fence = "`" * max(3, max_run + 1)
    return f"{fence}\n{content}\n{fence}"


def _render_dev_section(dev_envelope: dict[str, Any]) -> str:
    """Render the ``## Dev`` section: Dev's ``proposed_commit_message``
    verbatim (FR50) plus ``scope_expanded_to`` surface.

    No truncation, no markdown injection, no transformation other than
    newline normalization on the commit message. The commit message is wrapped
    in a dynamically-lengthed code fence (via :func:`_fenced_code_block`) so
    that commit messages containing triple-backtick sequences do not break the
    fence — fence length adapts to content, content is never modified.
    """
    commit_message = dev_envelope.get("proposed_commit_message", "")
    scope_expanded_to = dev_envelope.get("scope_expanded_to") or []
    lines = ["**Proposed commit message:**", "", _fenced_code_block(commit_message), ""]
    if scope_expanded_to:
        lines.append("**Scope expanded to:**")
        lines.extend(f"- `{path}`" for path in scope_expanded_to)
    else:
        lines.append("Scope expanded to: (none)")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Marker emission                                                             #
# --------------------------------------------------------------------------- #


def _render_marker(marker_class: str) -> str:
    """Render the structured (greppable, machine-readable) marker
    HTML comment per AC-4.

    The Story 2.7 placeholder used the form
    ``<!-- walking-skeleton-bundle: marker_class -->`` — a fragile prose
    heuristic per the verbatim epic AC at lines 1501-1502; THIS module
    emits the structured form
    ``<!-- bmad-automation:marker walking-skeleton-bundle -->``. The
    structured form is greppable via
    ``grep -c 'bmad-automation:marker walking-skeleton-bundle'``
    returning the emission count.
    """
    return f"{_MARKER_COMMENT_PREFIX}{marker_class}{_MARKER_COMMENT_SUFFIX}"


def _render_per_layer_marker(marker_class: str, sub_classification: str) -> str:
    """Render the per-layer marker comment for Story 3.3's
    ``review-layer-failed`` channel-2 surface.

    Reuses the existing :data:`_MARKER_COMMENT_PREFIX` /
    :data:`_MARKER_COMMENT_SUFFIX` constants verbatim per AC-4's
    "introduce a per-layer rendering helper that reuses the existing
    prefix/suffix constants" option, producing the form
    ``<!-- bmad-automation:marker review-layer-failed: <layer> -->``.
    The substring ``review-layer-failed: <layer>`` is the
    machine-readable identifier downstream tooling (Story 1.5's
    ``enumeration_check`` + Story 1.8's ``fr33-fixture-gate``) already
    enumerates against; the bundle-comment form is the canonical
    emission target per Story 1.4's marker-taxonomy commitment.
    """
    return (
        f"{_MARKER_COMMENT_PREFIX}{marker_class}: "
        f"{sub_classification}{_MARKER_COMMENT_SUFFIX}"
    )


# --------------------------------------------------------------------------- #
# Loud-fail block rendering (Story 6.1 — top-of-bundle dedicated block)       #
# --------------------------------------------------------------------------- #


#: Sentinel H2 + body emitted when ``run_state.active_markers`` is
#: empty. Per AC-3 the block's *presence* is structural — the H2 is
#: rendered even when no markers are active so downstream tooling can
#: rely on a deterministic structural anchor.
_LOUD_FAIL_NONE_SENTINEL: str = (
    "## ✓ Loud-Fail Markers — None\n\n"
    "No loud-fail markers are active on this run."
)

#: Sentinel H2 + body emitted when the cost-breakdown aggregation is
#: empty AND no ``cost-telemetry-unavailable`` marker is active (Story
#: 6.4 / AC-3). Mirrors :data:`_LOUD_FAIL_NONE_SENTINEL`'s
#: presence-is-structural posture: the H2 is rendered even when no
#: cost-events have accrued so downstream tooling can rely on a
#: deterministic structural anchor.
_COST_BREAKDOWN_NONE_SENTINEL: str = (
    "## 💸 Cost Breakdown — None\n\n"
    "No cost telemetry events have been recorded for this run."
)

#: Prefix that identifies a ``cost-telemetry-unavailable`` marker class
#: with or without sub-classification suffix (Story 6.4 / AC-2).
_COST_TELEMETRY_UNAVAILABLE_PREFIX: str = "cost-telemetry-unavailable"


def _load_marker_taxonomy_entries(
    taxonomy_path: pathlib.Path | None = None,
) -> Mapping[str, Mapping[str, Any]]:
    """Load the full marker-taxonomy YAML and return a mapping from
    ``marker_class`` to the entry's ``diagnostic_pointer`` +
    ``sub_classifications`` fields.

    Sibling to
    :func:`loud_fail_harness.specialist_dispatch.load_marker_class_registry`
    (which only carries the marker-class identifier set); THIS helper
    surfaces the per-entry text fields needed to render the loud-fail
    block per Story 6.1 AC-1's verbatim shape contract. The on-disk
    taxonomy file is the single source of truth (Story 1.4); the
    returned dict is a frozen view that does NOT mutate the file.

    Args:
        taxonomy_path: Optional explicit path to the taxonomy YAML. If
            ``None``, resolves via
            :func:`loud_fail_harness._shared.find_repo_root` at
            function-call time (Epic 1 retro Action #1; NEVER at
            module import time).

    Returns:
        :class:`Mapping` from marker-class identifier string to entry
        mapping. Each entry mapping contains at minimum the
        ``diagnostic_pointer`` (str) and ``sub_classifications`` (list)
        fields.
    """
    if taxonomy_path is None:
        taxonomy_path = find_repo_root() / "schemas" / "marker-taxonomy.yaml"
    raw = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("markers"), list):
        raise RuntimeError(
            f"Marker taxonomy at {taxonomy_path} is malformed: expected a "
            f"mapping with 'markers' list, got {type(raw).__name__}"
        )
    entries: dict[str, Mapping[str, Any]] = {}
    for entry in raw.get("markers", []):
        if isinstance(entry, dict) and "marker_class" in entry:
            entries[str(entry["marker_class"])] = entry
    return entries


def _interpolate_actionable_pointer(
    template: str,
    context: Mapping[str, object],
    *,
    required_fields: Sequence[str],
) -> str:
    """Interpolate a marker's ``diagnostic_pointer`` template against
    runtime context to produce the actionable ``- How to enable:`` text.

    Story 6.2 / FR31 / Pattern 5 / NFR-O5. Single interpolation surface
    consumed by :func:`_render_loud_fail_block`; consolidates the
    "validate required fields → loud-fail on missing → interpolate"
    discipline into one place so every marker class with declared
    ``pointer_context_fields`` (in ``marker-taxonomy.yaml``) follows the
    same contract.

    Behavior:

        * When ``required_fields`` is empty the function returns
          ``template`` verbatim — context-free markers (24 of the 27
          taxonomy entries at Story 6.2's landing) pass through
          unchanged. This is the AC-2 no-op path.
        * When ``required_fields`` is non-empty, every named field must
          be present in ``context``; the first missing field surfaces as
          a :exc:`MarkerContextMissing` with ``marker_class=""``
          (the caller — :func:`_render_loud_fail_block` — late-binds the
          marker_class on the raised exception so the diagnostic carries
          full context). Pattern 5 named-invariant convention; NFR-O5
          named-invariant diagnostic.
        * On success, the function returns ``template.format(**context)``
          — Python's :meth:`str.format` substitution with the context
          dict as kwargs. Excess context keys (not referenced by any
          ``{placeholder}`` in ``template``) are tolerated; ``format``
          ignores unused kwargs by design.
        * If ``template`` contains a ``{placeholder}`` whose name is
          NOT in ``required_fields`` AND not in ``context``, Python's
          ``format`` raises :exc:`KeyError`; this is mapped to
          :exc:`MarkerContextMissing` for diagnostic uniformity (the
          orphan-placeholder case is structurally rejected by the
          taxonomy-contract test in ``test_marker_taxonomy.py`` per
          AC-3, but the runtime mapping defends against drift).

    Args:
        template: The ``diagnostic_pointer`` template string from
            ``marker-taxonomy.yaml`` for the marker class being rendered.
        context: The marker's per-emission context — typically
            ``run_state.marker_contexts.get(marker_class, {})``.
        required_fields: The marker's declared ``pointer_context_fields``
            list from ``marker-taxonomy.yaml``; the names that MUST be
            present in ``context`` for interpolation to succeed.

    Returns:
        The rendered actionable pointer text, with all
        ``{placeholders}`` substituted from ``context``.

    Raises:
        MarkerContextMissing: A required field is absent from
            ``context`` (or a template placeholder lacks a context
            value). Caller late-binds ``marker_class`` for diagnostic
            clarity.
    """
    if not required_fields:
        return template

    for field_name in required_fields:
        if field_name not in context:
            raise MarkerContextMissing(
                marker_class="",
                missing_field=field_name,
            )

    try:
        return template.format(**context)
    except KeyError as exc:
        # Orphan placeholder: template references {field} not declared
        # in required_fields and absent from context. Map to the named
        # invariant diagnostic per NFR-O5 instead of leaking KeyError.
        missing = exc.args[0] if exc.args else ""
        raise MarkerContextMissing(
            marker_class="",
            missing_field=str(missing),
        ) from exc


def _merge_evidence_linkability_markers(
    existing: tuple[str, ...],
    appended: tuple[str, ...],
) -> tuple[str, ...]:
    """Merge bundle-render-time dangling-evidence markers into the
    persistent ``run_state.active_markers`` tuple per Story 6.6.

    Concatenates ``existing`` and ``appended`` in order — existing
    markers first, dangling-evidence markers appended at the end — and
    de-duplicates against existing entries by full marker-string
    equality so that if the orchestrator-side path already emitted a
    ``dangling-evidence-ref: <sub>`` marker (e.g. from a prior
    Story 5.5 CLI-hook run that persisted the marker into run-state),
    the assembler-side computation does NOT re-append the same
    identifier. The existing entry is preserved at its original
    position per Story 1.4's marker-permanence rule; the new entry
    is dropped.

    The merge is in-memory only; the assembler does NOT write the
    derived markers back to ``run_state.yaml``. Pattern 4's batch-
    write rule is preserved — bundle-render-time validation is a
    UI-only augmentation, not a persistent state mutation.

    Args:
        existing: The persistent ``run_state.active_markers`` tuple.
        appended: The
            :attr:`EvidenceLinkabilityResult.marker_classifications_to_append`
            tuple — at most two entries (qa-evidence and
            retry-history sub-classifications) in alphabetical order.

    Returns:
        Merged tuple in input order; appended entries already present
        in ``existing`` are dropped.
    """
    if not appended:
        return existing
    existing_set = set(existing)
    deduped = tuple(m for m in appended if m not in existing_set)
    return existing + deduped


def _render_marker_entry_body(
    marker_class: str,
    *,
    marker_registry: MarkerClassRegistry,
    marker_contexts: Mapping[str, Mapping[str, object]],
    taxonomy_entries: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Render the per-marker H3 header + 3 bullets for a single marker.

    Story 7.3 path (b) — single source of truth for the marker-entry
    shape consumed by BOTH:

    * Story 6.1's :func:`_render_loud_fail_block` (this file's PR-bundle
      loud-fail block renderer)
    * Story 7.3's :func:`loud_fail_harness.init_preconditions.format_init_diagnostic`
      (the ``init`` precondition aggregated diagnostic renderer)

    The shared helper guarantees that a future taxonomy bump or
    pointer-text edit propagates to BOTH consumers without drift per
    Story 5.8 AC-4 + Story 6.1 AC-2's structural-derivation invariant.
    Story 7.3 AC-6 path (b) names this extraction as the canonical
    landing of the cross-consumer shape.

    Args:
        marker_class: The full marker string (possibly carrying a
            ``: <sub_class>`` Pattern 2 suffix). The bullet rendering
            strips the suffix before taxonomy lookup but the H3 header
            uses the full string verbatim so the run-specific sub-class
            is visible.
        marker_registry: Validates the BASE marker class against the
            taxonomy enumeration per Pattern 5; rejection raises
            :exc:`UnknownMarkerClass`.
        marker_contexts: Per-base-marker-class context mapping for
            Story 6.2 actionable-pointer interpolation (the
            ``How to enable`` bullet).
        taxonomy_entries: Pre-loaded mapping from marker-class string
            to taxonomy entry per :func:`_load_marker_taxonomy_entries`.

    Returns:
        A list of five lines in the canonical shape:
        ``["### {marker_class}", "", "- Sub-classification: …",
        "- Diagnostic pointer: …", "- How to enable: …"]``. The caller
        composes these with surrounding header / blank-line separators.

    Raises:
        UnknownMarkerClass: The base marker class is not in the
            registry.
        MarkerContextMissing: The marker class has non-empty
            ``pointer_context_fields`` and one or more required fields
            are missing from ``marker_contexts``.
    """
    # Pattern 2 (architecture.md line 962): an active marker may carry an
    # optional ``: <sub_class>`` suffix (e.g.
    # ``cost-telemetry-unavailable: otel-pipeline-unreachable``). Strip the
    # suffix before the registry / taxonomy lookup so the base class
    # validates and the entry is found; the rendered H3 still uses the
    # full marker string (including the suffix) so the run-specific sub-
    # classification is visible.
    if ":" in marker_class:
        base_marker_class, run_specific_sub = marker_class.split(":", 1)
        base_marker_class = base_marker_class.strip()
        run_specific_sub = run_specific_sub.strip()
    else:
        base_marker_class = marker_class
        run_specific_sub = ""
    validate_marker_emission(marker_registry, base_marker_class)
    entry = taxonomy_entries.get(base_marker_class, {})
    diagnostic_pointer_raw = str(entry.get("diagnostic_pointer", ""))
    diagnostic_pointer = " ".join(diagnostic_pointer_raw.split())
    if run_specific_sub:
        # Run-specific sub-classification (Pattern 2 suffix) supersedes the
        # taxonomy's full enumeration for the rendered bullet — the bullet
        # reflects the SPECIFIC failure mode this run hit, not the set of
        # possibilities.
        sub_class_str = run_specific_sub
    else:
        # No sub-classification was emitted for this run (base class only).
        # Render "none" regardless of what the taxonomy enumerates for
        # sub_classifications — that field documents possible suffixes, not
        # which one this run hit (Story 6.5 review patch D1).
        sub_class_str = "none"
    required_fields = tuple(entry.get("pointer_context_fields") or ())
    marker_context = marker_contexts.get(base_marker_class, {})
    try:
        actionable_pointer_raw = _interpolate_actionable_pointer(
            template=diagnostic_pointer_raw,
            context=marker_context,
            required_fields=required_fields,
        )
    except MarkerContextMissing as exc:
        exc.marker_class = marker_class
        raise
    actionable_pointer = " ".join(actionable_pointer_raw.split())
    return [
        f"### {marker_class}",
        "",
        f"- Sub-classification: {sub_class_str}",
        f"- Diagnostic pointer: {diagnostic_pointer}",
        f"- How to enable: {actionable_pointer}",
    ]


def _render_loud_fail_block(
    active_markers: tuple[str, ...],
    *,
    marker_registry: MarkerClassRegistry,
    marker_contexts: Mapping[str, Mapping[str, object]] | None = None,
    taxonomy_entries: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """Render the Story 6.1 dedicated top-of-bundle loud-fail block.

    Per the verbatim epic AC at ``epics.md`` lines 2550-2554 + PRD FR32:
    the bundle's first content section after the title and any era
    headers is a ``## ⚠️ Loud-Fail Markers`` block listing every active
    marker for the run. When ``active_markers`` is empty the block
    renders as the ``## ✓ Loud-Fail Markers — None`` sentinel (AC-3 —
    the block's *presence* is structural, not its non-empty content).

    Per AC-1's four-element entry shape (H3 header + three bullets):
    each marker entry is rendered as ``### {marker_class}`` H3 followed
    by:

        * ``- Sub-classification: <str>`` — rendered as ``none`` if the
          taxonomy lists ``sub_classifications: []``.
        * ``- Diagnostic pointer: <text>`` — verbatim text from the
          marker-taxonomy entry's ``diagnostic_pointer`` field (the
          practitioner-facing reference; un-interpolated).
        * ``- How to enable: <actionable>`` — Story 6.2 fills this slot
          with the actionable pointer per FR31. The bullet's content is
          the marker's ``diagnostic_pointer`` template interpolated
          against ``marker_contexts.get(marker_class, {})`` per the
          marker's declared ``pointer_context_fields``. Missing
          required-context fields surface as
          :exc:`MarkerContextMissing` per Pattern 5 / NFR-O5.

    Marker-class identifiers are validated against ``marker_registry``
    per Story 2.6's pattern; rejection raises :exc:`UnknownMarkerClass`
    per Pattern 5.

    Story 6.7 AC-4 — Order-stable rendering: the rendered loud-fail
    block iterates ``active_markers`` in alphabetical order by
    ``(base_class, sub_classification)`` via
    :func:`loud_fail_harness.marker_wiring.compute_alphabetical_marker_order`.
    The persistent ``run_state.active_markers`` tuple is UNCHANGED —
    on-disk persistence stays in emission order per Story 1.4's
    marker-permanence rule; only the rendered iteration order is
    normalized so the loud-fail block is byte-stable across runs
    regardless of which marker fired first.

    Story 6.7 marker rendering surface: the three orchestrator-side
    marker classes ``specialist-timeout``, ``hook-failed``, and
    ``context-near-limit`` (recorded via
    :mod:`loud_fail_harness.marker_wiring`) flow through this rendering
    path with full Story 6.2 actionable-pointer enrichment — the
    ``{specialist}`` / ``{timeout_seconds}`` / ``{hook_name}``
    placeholders interpolate against the ``marker_contexts`` mapping
    populated by the recorders.

    Story 7.3 path (b) refactor: the per-marker H3 + 3-bullet shape
    is extracted into the shared :func:`_render_marker_entry_body`
    helper so :func:`loud_fail_harness.init_preconditions.format_init_diagnostic`
    consumes the single source of truth for the marker-entry shape
    (Story 5.8 AC-4 + Story 6.1 AC-2's structural-derivation
    invariant). The H2 header + iteration-order discipline + empty-case
    sentinel remain owned by THIS function; the per-entry body is
    delegated.

    Args:
        active_markers: Tuple of marker-class identifiers active on the
            run, sourced from
            :class:`loud_fail_harness.run_state.RunState.active_markers`.
            Persistent emission order is preserved on the input tuple;
            the rendered iteration is alphabetical (Story 6.7 AC-4).
        marker_registry: Runtime
            :class:`loud_fail_harness.specialist_dispatch.MarkerClassRegistry`
            used to validate every marker-class identifier; rejection
            raises :exc:`UnknownMarkerClass` per Pattern 5.
        marker_contexts: Per-marker-class context map sourced from
            :attr:`loud_fail_harness.run_state.RunState.marker_contexts`.
            Used to interpolate ``diagnostic_pointer`` templates per the
            marker's declared ``pointer_context_fields``. Defaults to an
            empty mapping; markers without ``pointer_context_fields``
            entries render their template verbatim.
        taxonomy_entries: Optional pre-loaded mapping from marker-class
            string to taxonomy entry (per
            :func:`_load_marker_taxonomy_entries`'s return shape).
            Defaults to a fresh load via
            :func:`_load_marker_taxonomy_entries` at call time.

    Returns:
        The rendered markdown body (no leading or trailing newline
        beyond the canonical structural shape).

    Raises:
        MarkerContextMissing: A marker class with non-empty
            ``pointer_context_fields`` lacks one or more required fields
            in ``marker_contexts``. The exception's ``marker_class``
            attribute is late-bound to the offending class for
            diagnostic clarity per NFR-O5.
    """
    if not active_markers:
        return _LOUD_FAIL_NONE_SENTINEL

    entries = (
        taxonomy_entries
        if taxonomy_entries is not None
        else _load_marker_taxonomy_entries()
    )
    contexts: Mapping[str, Mapping[str, object]] = (
        marker_contexts if marker_contexts is not None else {}
    )

    parts: list[str] = ["## ⚠️ Loud-Fail Markers", ""]
    # Story 6.7 AC-4: order-stable rendering — alphabetical by base
    # class then sub-classification. The persistent
    # ``run_state.active_markers`` tuple is UNCHANGED (on-disk
    # persistence stays in emission order per Story 1.4's
    # marker-permanence rule); only the rendered iteration order is
    # normalized for stable display.
    for marker_class in compute_alphabetical_marker_order(active_markers):
        entry_lines = _render_marker_entry_body(
            marker_class,
            marker_registry=marker_registry,
            marker_contexts=contexts,
            taxonomy_entries=entries,
        )
        parts.extend(entry_lines)
        parts.append("")
    # Drop the trailing blank line so the joined block does not
    # double-newline against the assembler's section separator.
    if parts and parts[-1] == "":
        parts.pop()
    return "\n".join(parts)



def _render_cost_breakdown(
    active_markers: tuple[str, ...],
    marker_contexts: Mapping[str, Mapping[str, object]],
    cost_aggregation: "CostAggregation",
    *,
    marker_registry: MarkerClassRegistry,
    taxonomy_entries: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """Render the Story 6.4 cost-breakdown section.

    Three render branches per AC-3 / AC-2:

        * Degraded — any active marker starts with the
          ``cost-telemetry-unavailable`` prefix → render
          ``## ⚠️ Cost Breakdown — Telemetry Unavailable`` + the
          taxonomy entry's ``diagnostic_pointer`` text rendered verbatim
          + the ``Sub-classification: <sub>`` line. NO fabricated zeros
          (AC-3 verbatim).
        * Empty — no cost-telemetry-unavailable marker active AND
          ``cost_aggregation.per_specialist_per_retry`` is empty →
          render the :data:`_COST_BREAKDOWN_NONE_SENTINEL`. Mirrors
          :func:`_render_loud_fail_block`'s ``— None`` sentinel posture.
        * Green — render ``## 💸 Cost Breakdown`` + a markdown table
          with columns ``Specialist | Retry attempt | Cost delta (USD) |
          Per-specialist running total (USD)``. Rows sorted alphabetically
          by specialist then numerically by retry_attempt; per-specialist
          totals row appended after each specialist's run of rows.

    Per AC-3 the section's *presence* is structural — the H2 is
    rendered in all three branches; the absence-of-content phrasing is
    the contract for the empty-aggregation case.

    Args:
        active_markers: Tuple of marker-class identifiers active on the
            run; ``cost-telemetry-unavailable``-prefixed entries trigger
            the degraded branch.
        marker_contexts: Per-marker-class context map; sourced from
            :attr:`loud_fail_harness.run_state.RunState.marker_contexts`.
            Reserved for forward-compat — the v1
            ``cost-telemetry-unavailable`` taxonomy entry takes
            ``pointer_context_fields: []`` so no interpolation happens
            at this story's landing.
        cost_aggregation: Frozen
            :class:`loud_fail_harness.cost_telemetry.CostAggregation`
            carrying the per-(specialist × retry_attempt) detail.
            Empty aggregation triggers the empty branch.
        marker_registry: Runtime
            :class:`loud_fail_harness.specialist_dispatch.MarkerClassRegistry`
            used (forward-compat) to validate marker-class identifiers
            consumed in the degraded branch.
        taxonomy_entries: Optional pre-loaded mapping; defaults to a
            fresh load via :func:`_load_marker_taxonomy_entries` at
            call time (used only in the degraded branch).

    Returns:
        The rendered markdown body (no leading or trailing newline
        beyond the canonical structural shape).
    """
    _ = marker_registry  # forward-compat: registry membership of
    # ``cost-telemetry-unavailable`` is validated at marker emission
    # time (per Story 6.2 / 6.4); the renderer trusts the active_markers
    # tuple at this story's landing.
    _ = marker_contexts  # forward-compat: empty pointer_context_fields
    # at this story's landing means no interpolation needed.

    degraded_marker = next(
        (
            marker
            for marker in active_markers
            if marker.split(":", 1)[0].strip() == _COST_TELEMETRY_UNAVAILABLE_PREFIX
        ),
        None,
    )
    if degraded_marker is not None:
        entries = (
            taxonomy_entries
            if taxonomy_entries is not None
            else _load_marker_taxonomy_entries()
        )
        entry = entries.get(_COST_TELEMETRY_UNAVAILABLE_PREFIX, {})
        diagnostic_pointer_raw = str(entry.get("diagnostic_pointer", ""))
        diagnostic_pointer = " ".join(diagnostic_pointer_raw.split())
        # Sub-classification suffix per Pattern 2 (architecture.md line 962).
        if ":" in degraded_marker:
            sub_class = degraded_marker.split(":", 1)[1].strip()
        else:
            sub_class = ""
        body_lines = [
            "## ⚠️ Cost Breakdown — Telemetry Unavailable",
            "",
            diagnostic_pointer,
            "",
            f"Sub-classification: {sub_class}" if sub_class else "Sub-classification: none",
        ]
        return "\n".join(body_lines)

    per_retry = cost_aggregation.per_specialist_per_retry
    if not per_retry:
        return _COST_BREAKDOWN_NONE_SENTINEL

    parts: list[str] = [
        "## 💸 Cost Breakdown",
        "",
        "| Specialist | Retry attempt | Cost delta (USD) | Per-specialist running total (USD) |",
        "| --- | --- | --- | --- |",
    ]
    # Group by specialist (alphabetical), then by retry_attempt (numerical).
    by_specialist: dict[str, list[tuple[int, float]]] = {}
    for (specialist, retry_attempt), cost_delta in per_retry.items():
        by_specialist.setdefault(specialist, []).append((retry_attempt, cost_delta))
    for specialist in sorted(by_specialist.keys()):
        running_total = 0.0
        for retry_attempt, cost_delta in sorted(by_specialist[specialist]):
            running_total += cost_delta
            parts.append(
                f"| {specialist} | {retry_attempt} | "
                f"{cost_delta:.2f} | {running_total:.2f} |"
            )
        parts.append(f"| {specialist} | total | — | {running_total:.2f} |")
    return "\n".join(parts)


def _load_cost_aggregation(
    story_id: str,
    otel_pipeline: "OtelPipelineProtocol | None",
) -> "CostAggregation":
    """Load the per-run cost aggregation for the bundle's cost-breakdown
    section (Story 6.4 / AC-3).

    Returns an empty :class:`loud_fail_harness.cost_telemetry.CostAggregation`
    when:

        * ``otel_pipeline`` is ``None`` (default — backward-compat for
          existing call sites that don't inject a pipeline; the bundle's
          cost-breakdown section renders the ``— None`` sentinel).
        * The pipeline raises
          :exc:`loud_fail_harness.exceptions.OtelPipelineUnreachable` or
          :exc:`loud_fail_harness.exceptions.PromptIdCorrelationMissing`
          (the marker is already in ``run_state.active_markers`` from
          the per-dispatch boundary; the assembler does NOT re-emit —
          it consumes the marker).

    Otherwise calls
    :meth:`loud_fail_harness.cost_telemetry.OtelPipelineProtocol.read_events`
    with ``prompt_id=story_id`` as the run-scoped filter convention
    (operator-managed OTel-bridge implementations are expected to
    interpret the ``prompt_id`` argument as a filter scope for the
    per-run read; per-dispatch reads use the dispatch's ``prompt_id``
    directly via :func:`cost_telemetry.collect`).

    Args:
        story_id: The run's story identifier; used as the run-scoped
            filter argument to ``otel_pipeline.read_events``. Both
            bundle-variant call sites (merge-ready :func:`assemble_bundle`
            and the escalation variant) pass their respective context's
            ``story_id`` field — the helper does not need a full
            ``RunState``.
        otel_pipeline: Optional OTel-pipeline protocol implementation;
            ``None`` (default) returns empty aggregation.

    .. note::
        **Known MVP gap** — if the OTel pipeline raises only at assembly
        time (e.g., a transient outage between the last specialist
        dispatch and the bundle render) but NOT at the per-dispatch
        boundary, no ``cost-telemetry-unavailable`` marker is in
        ``run_state.active_markers`` and the renderer shows the
        ``— None`` sentinel rather than the degraded variant. In the
        normal total-outage case both per-dispatch and assembly-time
        reads fail together, so the marker IS in ``active_markers`` and
        the degraded variant renders correctly. Upgrading this to emit
        the marker at assembly time is a post-MVP candidate tracked in
        ``deferred-work.md`` (D-6.4-CR-1).
    """
    if otel_pipeline is None:
        return CostAggregation()
    try:
        events = tuple(otel_pipeline.read_events(prompt_id=story_id))
    except (OtelPipelineUnreachable, PromptIdCorrelationMissing):
        return CostAggregation()
    return aggregate_costs(events)


def _format_sub_classification(sc: Any) -> str:
    """Render one ``sub_classifications`` entry as a string.

    Taxonomy entries with kebab-case literal sub-classifications appear
    as plain strings (e.g. ``"port-bind-failed"``); Story 1.4's
    structured-condition entries appear as mappings. This helper
    surfaces a stable string projection so the loud-fail block's
    sub-classification bullet is deterministic regardless of entry
    shape.
    """
    if isinstance(sc, Mapping):
        condition = sc.get("condition")
        if isinstance(condition, str) and condition:
            return condition
        return str(dict(sc))
    return str(sc)


def _emit_walking_skeleton_marker(
    *,
    flags: ModuleType,
    marker_registry: MarkerClassRegistry,
) -> tuple[str, ...]:
    """Decide whether to emit the ``walking-skeleton-bundle`` marker AND
    pre-validate it against the runtime registry.

    Per AC-4: emit iff
    :func:`loud_fail_harness.thickening_flags.is_loud_fail_block_present`
    returns ``False``. If emission proceeds, the marker class
    identifier is validated against the runtime
    :class:`MarkerClassRegistry` per Story 2.6's pattern; rejection
    raises :exc:`UnknownMarkerClass` per Pattern 5.
    """
    if flags.is_loud_fail_block_present():
        return ()
    validate_marker_emission(marker_registry, WALKING_SKELETON_MARKER)
    return (WALKING_SKELETON_MARKER,)


# --------------------------------------------------------------------------- #
# Atomic bundle write                                                         #
# --------------------------------------------------------------------------- #


def _atomic_write_bundle(bundle_path: pathlib.Path, body: str) -> None:
    """Write the bundle markdown atomically per Pattern 4.

    Mirrors Story 2.2's :func:`advance_run_state` and Story 2.6's
    :func:`persist_dispatch_log`: ``tempfile.NamedTemporaryFile`` +
    ``os.fsync`` + ``os.replace``. On any exception between temp-write
    and ``os.replace`` the temp file is unlinked before re-raising —
    the bundle path is never left in a partial state.
    """
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        dir=bundle_path.parent,
        delete=False,
        encoding="utf-8",
        suffix=".tmp",
    )
    tmp_path = pathlib.Path(tmp.name)
    try:
        try:
            tmp.write(body)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        os.replace(tmp_path, bundle_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def assemble_bundle(
    story_id: str,
    run_id: str,
    run_state_path: pathlib.Path,
    logs_root: pathlib.Path,
    bundle_root: pathlib.Path,
    *,
    marker_registry: MarkerClassRegistry | None = None,
    thickening_flags: ModuleType | None = None,
    generated_at: datetime | None = None,
    envelope_schema: dict[str, Any] | None = None,
    otel_pipeline: OtelPipelineProtocol | None = None,
    repo_root: pathlib.Path | None = None,
    auto_merge_gate_emission: AutoMergeGateNotMetEmission | None = None,
    auto_merge_gate_error: str | None = None,
    auto_merge_skipped_emission: AutoMergeSkippedEmission | None = None,
) -> AssembleBundleResult:
    """Assemble the walking-skeleton merge-ready PR bundle.

    See module docstring for the input/output contract and the marker
    emission rule. ``marker_registry`` and ``thickening_flags`` are
    keyword-only injection points that default to the canonical
    runtime values; both enable test-time substitution per Story 2.6's
    :func:`make_task_tool_dispatch_callback` precedent. ``generated_at``
    + ``envelope_schema`` + ``repo_root`` are additional injection
    points for deterministic-fixture tests.

    Args:
        story_id: BMAD story key.
        run_id: Orchestrator-domain run identifier.
        run_state_path: Path to the on-disk run-state YAML.
        logs_root: Prefix under which the three dispatch logs live.
        bundle_root: Prefix under which the bundle markdown is written.
        marker_registry: Optional pre-loaded
            :class:`MarkerClassRegistry`; defaults to the canonical
            taxonomy via :func:`load_marker_class_registry`.
        thickening_flags: Optional namespace exposing the four flag
            functions; defaults to
            :mod:`loud_fail_harness.thickening_flags`.
        generated_at: Optional UTC timezone-aware timestamp rendered in
            the bundle's metadata block; defaults to
            ``datetime.now(timezone.utc)``.
        envelope_schema: Optional pre-loaded envelope schema dict;
            defaults to
            ``<repo-root>/schemas/envelope.schema.yaml``.
        otel_pipeline: Optional
            :class:`loud_fail_harness.cost_telemetry.OtelPipelineProtocol`
            implementation injected by the orchestrator runtime per
            ADR-006 Combo 3 / B1 (operator-managed OTLP backend).
            ``None`` (the default) backs the empty-aggregation path so
            existing call sites pre-Story-6.4 keep their byte-stable
            output for the zero-cost-events case (the cost-breakdown
            section renders the ``— None`` sentinel). Per Story 6.4 /
            AC-2 the pipeline's :exc:`OtelPipelineUnreachable` /
            :exc:`PromptIdCorrelationMissing` exceptions are caught
            inside :func:`_load_cost_aggregation` and translated into
            an empty aggregation; the marker is already in
            ``run_state.active_markers`` from the per-dispatch boundary.
        repo_root: Optional repository root used by Story 6.6's
            bundle-render-time evidence-trace linkability validation
            (:func:`loud_fail_harness.evidence_linkability.validate_evidence_linkability_at_render`)
            to resolve ``evidence_refs[].path`` and
            ``retry_history[].path`` strings against on-disk
            artifacts. Defaults to :func:`find_repo_root`. Tests
            override this to seed/control on-disk evidence-resolution
            without polluting the surrounding workspace — same
            test-injection posture ``envelope_schema`` /
            ``otel_pipeline`` already document.

    Returns:
        :class:`AssembleBundleResult`.
    """
    flags = thickening_flags if thickening_flags is not None else _default_thickening_flags
    registry = (
        marker_registry if marker_registry is not None else load_marker_class_registry()
    )
    schema = (
        envelope_schema
        if envelope_schema is not None
        else load_schema(find_repo_root() / "schemas" / "envelope.schema.yaml")
    )
    # Story 6.6: the evidence-trace linkability validation resolves
    # ``ac_results[].evidence_refs[].path`` and
    # ``retry_history[].path`` strings against this root. Default to
    # the process's current working directory (``Path.cwd()``) — NOT
    # :func:`find_repo_root`. Rationale: production hooks invoke the
    # assembler from the user's project root (where evidence files
    # actually live), not from the harness install location;
    # cwd-rooting matches the hook's existing pattern of consuming
    # ``_bmad/automation/run-state.yaml`` and
    # ``_bmad-output/qa-evidence/`` as cwd-relative paths. Tests
    # override via the keyword arg.
    resolved_repo_root = (
        repo_root if repo_root is not None else pathlib.Path.cwd()
    )
    rendered_at = (
        generated_at if generated_at is not None else datetime.now(timezone.utc)
    )
    if rendered_at.tzinfo is None:
        raise ValueError(
            "assemble_bundle: generated_at must be timezone-aware UTC; "
            "got naive datetime — pass datetime.now(timezone.utc) or a "
            "timezone-aware datetime"
        )

    # Step 1: Load run-state (sanity-check story_id; pull metadata).
    run_state = _load_run_state(run_state_path)
    if run_state.story_id != story_id:
        raise RunStateStoryIdMismatch(
            expected=story_id, actual=run_state.story_id
        )

    # Step 2: Read the three dispatch logs; re-validate envelopes.
    envelopes: dict[str, dict[str, Any]] = {}
    for specialist in EPIC_2_SPECIALISTS:
        log_path = _resolve_log_path(logs_root, story_id, run_id, specialist)
        envelopes[specialist] = _read_envelope_from_dispatch_log(
            log_path, specialist=specialist, schema=schema
        )

    # Step 3: Decide marker emission BEFORE writing the bundle (defense-
    # in-depth — Pattern 5: a registry rejection must surface before
    # any filesystem mutation).
    emitted_markers = _emit_walking_skeleton_marker(
        flags=flags, marker_registry=registry
    )

    # Step 4: Render header + section bodies.
    header_text = _render_walking_skeleton_header(flags)

    # Story 6.6 (NFR-O7): bundle-render-time evidence-trace
    # linkability validation. Walks every ``ac_results[].evidence_refs[].path``
    # AND every thickened ``run_state.retry_history[].path`` against
    # the on-disk artifact; surfaces dangling refs as
    # ``dangling-evidence-ref: <sub>`` markers in the loud-fail block
    # AND as inline indicators at their reference locations. The
    # bundle assembles successfully on dangling — visibility-not-
    # enforcement per the loud-fail doctrine.
    evidence_linkability_result = validate_evidence_linkability_at_render(
        ac_results=envelopes["qa"].get("ac_results") or [],
        retry_history=tuple(run_state.retry_history),
        repo_root=resolved_repo_root,
    )
    merged_active_markers = _merge_evidence_linkability_markers(
        run_state.active_markers,
        evidence_linkability_result.marker_classifications_to_append,
    )

    loud_fail_block = _render_loud_fail_block(
        merged_active_markers,
        marker_registry=registry,
        marker_contexts=run_state.marker_contexts,
    )
    cost_aggregation = _load_cost_aggregation(run_state.story_id, otel_pipeline)
    cost_breakdown_block = _render_cost_breakdown(
        merged_active_markers,
        run_state.marker_contexts,
        cost_aggregation,
        marker_registry=registry,
    )
    per_ac_body = _render_per_ac_section(
        envelopes["qa"],
        marker_registry=registry,
        qa_evidence_dangling=evidence_linkability_result.qa_evidence_dangling,
    )
    review_body = _render_review_findings_section(
        envelopes["review-bmad"], marker_registry=registry
    )
    dev_body = _render_dev_section(envelopes["dev"])

    # Step 5: Assemble the markdown body. The loud-fail block is the
    # FIRST content section after the title metadata block + the
    # ``## ⚠️ Walking Skeleton Mode`` header, BEFORE
    # ``## Per-AC results`` / ``## Review findings`` / ``## Dev`` per
    # Story 6.1 AC-1's verbatim structural-position contract.
    body_parts: list[str] = [
        f"# PR bundle — story {story_id} (run {run_id})",
        "",
        f"Branch: {run_state.branch_name}",
        f"Final state: {run_state.current_state}",
        f"Generated: {rendered_at.isoformat()}",
        "",
        "## ⚠️ Walking Skeleton Mode",
        "",
        header_text,
        "",
        loud_fail_block,
        "",
        cost_breakdown_block,
        "",
        "## Per-AC results",
        "",
        per_ac_body,
        "",
        "## Review findings",
        "",
        review_body,
        "",
        "## Dev",
        "",
        dev_body,
        "",
    ]
    if emitted_markers:
        body_parts.append("")
        for marker in emitted_markers:
            body_parts.append(_render_marker(marker))
        body_parts.append("")
    # Story 21.0 (FR-P2-6): the envelope-scoped a11y-delta-mode-unstable marker
    # renders at the canonical bundle-bottom location (no ac_id → not a per-AC
    # finding), independent of ac_results content.
    a11y_envelope_scoped = _render_qa_a11y_envelope_scoped_marker(
        envelopes["qa"], marker_registry=registry
    )
    if a11y_envelope_scoped:
        body_parts.append("")
        body_parts.append(a11y_envelope_scoped)
        body_parts.append("")
    # Story 17.2 (FR-P2-3): the orchestrator-domain auto-merge-gate-not-met
    # marker renders at the canonical bundle-bottom location (it is not a per-AC
    # QA finding); empty string when no gate fired (green / not-configured).
    auto_merge_gate_body = _render_auto_merge_gate_not_met_subsection(
        auto_merge_gate_emission,
        gate_config_error=auto_merge_gate_error,
        marker_registry=registry,
    )
    if auto_merge_gate_body:
        body_parts.append("")
        body_parts.append(auto_merge_gate_body)
        body_parts.append("")
    # Story 17.3 (FR-P2-3): the orchestrator-domain auto-merge-skipped marker
    # renders at the canonical bundle-bottom location (it is not a per-AC QA
    # finding); empty string when the merge succeeded, the bundle was not
    # merge-ready, or auto-merge was not armed (the shipped default).
    auto_merge_skipped_body = _render_auto_merge_skipped_subsection(
        auto_merge_skipped_emission,
        marker_registry=registry,
    )
    if auto_merge_skipped_body:
        body_parts.append("")
        body_parts.append(auto_merge_skipped_body)
        body_parts.append("")
    bundle_body = "\n".join(body_parts)

    # Step 6: Atomic write.
    bundle_path = bundle_root / story_id / f"{run_id}.md"
    _atomic_write_bundle(bundle_path, bundle_body)

    return AssembleBundleResult(
        bundle_path=bundle_path,
        emitted_markers=emitted_markers,
        header_text=header_text,
        included_specialists=frozenset(EPIC_2_SPECIALISTS),
    )


# --------------------------------------------------------------------------- #
# CLI entry point                                                             #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loud_fail_harness.bundle_assembly",
        description=(
            "Assemble the walking-skeleton merge-ready PR bundle "
            "(Story 2.11). Substrate-component invocation seam from the "
            "Stop hook (Story 2.7 → 2.11) per ADR-002 cell 4 row 4."
        ),
    )
    parser.add_argument("--story-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-state-path", required=True, type=pathlib.Path)
    parser.add_argument("--logs-root", required=True, type=pathlib.Path)
    parser.add_argument("--bundle-root", required=True, type=pathlib.Path)
    # Story 6.6: optional override for the repository root used by
    # bundle-render-time evidence-trace linkability validation. Hooks
    # pass the project's cwd so evidence_refs[].path resolves against
    # the user's project, not the harness install location.
    parser.add_argument("--repo-root", required=False, type=pathlib.Path, default=None)
    # Story 17.2 (FR-P2-3): the per-story auto-merge gate-condition evaluator
    # runs at EVERY Stop-hook invocation. Both default to the cwd-relative paths
    # the hook's other artifacts use (the hook bash is unchanged — these optional
    # args carry their defaults when absent; tests override them).
    parser.add_argument(
        "--auto-merge-config-path",
        required=False,
        type=pathlib.Path,
        default=pathlib.Path("_bmad/automation/config.yaml"),
    )
    parser.add_argument(
        "--adoption-metrics-path",
        required=False,
        type=pathlib.Path,
        default=DEFAULT_ADOPTION_METRICS_PATH,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    # Story 17.2 (FR-P2-3): evaluate the gate at every Stop-hook invocation
    # (continuous observability). AutoMergeConfigError (malformed automation
    # config) exits 1 — that file is unconditional infrastructure. AutoMergeGateError
    # (missing/malformed adoption-metrics when gates are configured) degrades
    # gracefully: the error surfaces as a subsection in the bundle so the Phase-1
    # output is never suppressed by a Phase-2 config problem.
    registry = load_marker_class_registry()
    auto_merge_gate_emission: AutoMergeGateNotMetEmission | None = None
    auto_merge_gate_error: str | None = None
    auto_merge_config: AutoMergeConfig | None = None
    gate_decision: AutoMergeGateDecision | None = None
    try:
        auto_merge_config = read_auto_merge_config_from_config_file(
            args.auto_merge_config_path
        )
        gate_decision = resolve_and_evaluate_auto_merge_gate(
            auto_merge_config, metrics_path=args.adoption_metrics_path
        )
        if gate_decision.status == "gate-not-met":
            auto_merge_gate_emission = surface_auto_merge_gate_not_met(
                gate_decision, registry
            )
    except AutoMergeConfigError as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 1
    except AutoMergeGateError as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        auto_merge_gate_error = str(exc)

    # Story 17.3 (FR-P2-3): the auto-merge execution decision. The actuator is
    # the system's FIRST actuator and FIRST remote-mutating surface — the
    # *decision* (the AC-2 conjunction) is orchestrator-domain flow policy that
    # lives HERE, not in the sensor-free actuator module. Fire the merge ONLY on
    # `enabled AND gate green AND merge-ready (current_state == "done")`; surface
    # every non-merge outcome (when armed + merge-ready) as `auto-merge-skipped`.
    # When `enabled: false` (the shipped default) auto-merge is not engaged: no
    # merge attempt, NO marker. A gate-config error (gate_decision is None) means
    # the gate is undeterminable → do NOT merge (the config-error subsection
    # already surfaces the problem loudly).
    auto_merge_skipped_emission: AutoMergeSkippedEmission | None = None
    if (
        auto_merge_config is not None
        and auto_merge_config.enabled
        and gate_decision is not None
    ):
        merge_run_state = _load_run_state_for_merge_decision(args.run_state_path)
        if merge_run_state is None:
            sys.stderr.write(
                "AutoMergeArmingRunStateUnavailable: auto-merge is armed "
                f"(auto_merge.enabled) but the run-state at "
                f"{str(args.run_state_path)!r} could not be loaded; the armed-"
                "merge intent is surfaced loudly here (the bundle assembler fails "
                "the run on the same unreadable run-state).\n"
            )
        elif (
            merge_run_state.story_id != args.story_id
            and merge_run_state.current_state == "done"
        ):
            # Story 22.6 AC-7(iii): an armed (enabled) auto-merge whose run-state
            # story_id does not match the requested story_id must NOT silently
            # drop the armed-merge intent. Only loud-fail when current_state is
            # "done" — a mismatch on an in-flight run is not yet actionable and
            # would be a false alarm.
            sys.stderr.write(
                "AutoMergeArmingStoryIdMismatch: auto-merge is armed "
                f"(auto_merge.enabled) but run-state story_id="
                f"{merge_run_state.story_id!r} != requested story_id="
                f"{args.story_id!r}; the armed-merge intent is dropped and "
                "surfaced loudly (the bundle assembler fails the run on the same "
                "mismatch).\n"
            )
        elif merge_run_state.current_state == "done":
            if gate_decision.status == "green":
                outcome = attempt_auto_merge(
                    branch_name=merge_run_state.branch_name,
                    repo_root=args.repo_root or pathlib.Path.cwd(),
                )
            else:
                outcome = skipped_gate_not_met(merge_run_state.branch_name)
            if outcome.status == "skipped":
                auto_merge_skipped_emission = surface_auto_merge_skipped(
                    outcome, registry
                )

    try:
        result = assemble_bundle(
            story_id=args.story_id,
            run_id=args.run_id,
            run_state_path=args.run_state_path,
            logs_root=args.logs_root,
            bundle_root=args.bundle_root,
            repo_root=args.repo_root,
            marker_registry=registry,
            auto_merge_gate_emission=auto_merge_gate_emission,
            auto_merge_gate_error=auto_merge_gate_error,
            auto_merge_skipped_emission=auto_merge_skipped_emission,
        )
    except (
        SpecialistDispatchLogNotFound,
        RunStateStoryIdMismatch,
    ) as exc:
        # Pre-condition failures: dispatch log missing or run-state did
        # not match the requested story. The assembler had nothing to
        # assemble; this is NOT an assembler-logic failure per the
        # remediation-shape principle (epics.md Story 6.9 lines 2841-2842),
        # so DO NOT emit `bundle-assembly-failed`. Existing exit-1 path
        # preserved.
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 1
    except (SystemExit, KeyboardInterrupt):
        # Pattern 5: never catch SystemExit / KeyboardInterrupt; propagate
        # so `bundle-assembly-failed` does NOT mask intentional process exit.
        raise
    except BaseException as exc:  # noqa: BLE001 — Story 6.9 outer catchall
        # Story 6.9 AC-1: assembler-logic failure (envelope shape
        # mismatch, missing finding fields, taxonomy reference unresolved,
        # finding-rendering crash, assembler-internal exception). Route
        # through `surface_assembly_failure` to emit the
        # `bundle-assembly-failed` marker across all three reinforcing
        # channels atomically, then exit with the distinct exit code 2
        # (signalling "assembler logic failed; marker already emitted")
        # so `handle_hook_exit_code` can distinguish this from a Stop
        # hook mechanical failure (AC-3).
        failed_step = classify_assembly_failure(exc, partial_bundle_path=None)
        try:
            surface_assembly_failure(
                story_id=args.story_id,
                run_id=args.run_id,
                run_state_path=args.run_state_path,
                bundle_root=args.bundle_root,
                exc=exc,
                failed_step=failed_step,
                partial_bundle_path=None,
            )
        except Exception:  # noqa: BLE001 — partial emission; AC-3 discriminator still holds
            pass
        return BUNDLE_ASSEMBLY_FAILED_EXIT_CODE
    sys.stdout.write(f"{result.bundle_path}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
