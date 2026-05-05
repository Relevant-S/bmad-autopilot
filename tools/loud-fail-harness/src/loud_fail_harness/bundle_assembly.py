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
from collections.abc import Mapping
from datetime import datetime, timezone
from types import ModuleType
from typing import Any

import yaml

from loud_fail_harness import thickening_flags as _default_thickening_flags
from loud_fail_harness._shared import find_repo_root, load_schema
from loud_fail_harness.envelope_validator import format_errors, validate_envelope
from loud_fail_harness.qa_exploratory_heuristics import HEURISTIC_SKIPPED_MARKER
from loud_fail_harness.qa_plan_drift import PLAN_DRIFT_DETECTED_MARKER
from loud_fail_harness.qa_plan_persistence_compromise import (
    render_compromise_blockquote,
)
from loud_fail_harness.review_layer_failure import (
    META_REVIEW_COMPLETENESS,
    REVIEW_LAYER_FAILED_MARKER,
)
from loud_fail_harness.run_state import RunState
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
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
    """
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
                # render correctly via the str(ref) fallback.
                block_lines.extend(
                    f"- `{ref['path']}`" if isinstance(ref, dict) and "path" in ref
                    else f"- `{ref}`"
                    for ref in evidence_refs
                )
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
    heuristic_body = _render_qa_heuristic_findings_subsection(
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
    parts = [render_compromise_blockquote().rstrip("\n"), ac_results_body]
    if plan_drift_body:
        parts.append(plan_drift_body)
    if heuristic_body:
        parts.append(heuristic_body)
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


#: The literal "How to enable" placeholder string emitted by
#: :func:`_render_loud_fail_block` for every active marker entry. Story
#: 6.2 thickens this slot by interpolating the ``diagnostic_pointer``
#: text against per-marker context (``{ac_id}`` / ``{specialist}`` /
#: ``{port}`` / ``{version_range}``) per FR31; Story 6.1 emits the raw
#: placeholder so the structural slot exists.
_HOW_TO_ENABLE_PLACEHOLDER: str = (
    "(actionable pointer interpolation lands at Story 6.2 — see "
    "marker-taxonomy.yaml entry for the diagnostic_pointer template)"
)


#: Sentinel H2 + body emitted when ``run_state.active_markers`` is
#: empty. Per AC-3 the block's *presence* is structural — the H2 is
#: rendered even when no markers are active so downstream tooling can
#: rely on a deterministic structural anchor.
_LOUD_FAIL_NONE_SENTINEL: str = (
    "## ✓ Loud-Fail Markers — None\n\n"
    "No loud-fail markers are active on this run."
)


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


def _render_loud_fail_block(
    active_markers: tuple[str, ...],
    *,
    marker_registry: MarkerClassRegistry,
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
          taxonomy lists ``sub_classifications: []``; placeholder slot
          for Story 6.2's per-marker interpolation.
        * ``- Diagnostic pointer: <text>`` — verbatim text from the
          marker-taxonomy entry's ``diagnostic_pointer`` field; Story
          6.2 thickens the interpolation, 6.1 emits the raw text.
        * ``- How to enable: <placeholder>`` — the literal
          :data:`_HOW_TO_ENABLE_PLACEHOLDER` string; Story 6.2 fills
          this slot with the actionable pointer per FR31.

    Marker-class identifiers are validated against ``marker_registry``
    per Story 2.6's pattern; rejection raises :exc:`UnknownMarkerClass`
    per Pattern 5.

    Args:
        active_markers: Tuple of marker-class identifiers active on the
            run, sourced from
            :class:`loud_fail_harness.run_state.RunState.active_markers`.
            Order is preserved as emitted; entries are not re-sorted.
        marker_registry: Runtime
            :class:`loud_fail_harness.specialist_dispatch.MarkerClassRegistry`
            used to validate every marker-class identifier; rejection
            raises :exc:`UnknownMarkerClass` per Pattern 5.
        taxonomy_entries: Optional pre-loaded mapping from marker-class
            string to taxonomy entry (per
            :func:`_load_marker_taxonomy_entries`'s return shape).
            Defaults to a fresh load via
            :func:`_load_marker_taxonomy_entries` at call time.

    Returns:
        The rendered markdown body (no leading or trailing newline
        beyond the canonical structural shape).
    """
    if not active_markers:
        return _LOUD_FAIL_NONE_SENTINEL

    entries = (
        taxonomy_entries
        if taxonomy_entries is not None
        else _load_marker_taxonomy_entries()
    )

    parts: list[str] = ["## ⚠️ Loud-Fail Markers", ""]
    for marker_class in active_markers:
        validate_marker_emission(marker_registry, marker_class)
        entry = entries.get(marker_class, {})
        diagnostic_pointer = " ".join(str(entry.get("diagnostic_pointer", "")).split())
        sub_classifications = entry.get("sub_classifications") or []
        sub_class_str = (
            ", ".join(_format_sub_classification(sc) for sc in sub_classifications)
            if sub_classifications
            else "none"
        )
        parts.append(f"### {marker_class}")
        parts.append("")
        parts.append(f"- Sub-classification: {sub_class_str}")
        parts.append(f"- Diagnostic pointer: {diagnostic_pointer}")
        parts.append(f"- How to enable: {_HOW_TO_ENABLE_PLACEHOLDER}")
        parts.append("")
    # Drop the trailing blank line so the joined block does not
    # double-newline against the assembler's section separator.
    if parts and parts[-1] == "":
        parts.pop()
    return "\n".join(parts)


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
) -> AssembleBundleResult:
    """Assemble the walking-skeleton merge-ready PR bundle.

    See module docstring for the input/output contract and the marker
    emission rule. ``marker_registry`` and ``thickening_flags`` are
    keyword-only injection points that default to the canonical
    runtime values; both enable test-time substitution per Story 2.6's
    :func:`make_task_tool_dispatch_callback` precedent. ``generated_at``
    + ``envelope_schema`` are additional injection points for
    deterministic-fixture tests.

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
    loud_fail_block = _render_loud_fail_block(
        run_state.active_markers, marker_registry=registry
    )
    per_ac_body = _render_per_ac_section(
        envelopes["qa"], marker_registry=registry
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    try:
        result = assemble_bundle(
            story_id=args.story_id,
            run_id=args.run_id,
            run_state_path=args.run_state_path,
            logs_root=args.logs_root,
            bundle_root=args.bundle_root,
        )
    except (
        SpecialistDispatchLogNotFound,
        EnvelopeReValidationFailed,
        RunStateStoryIdMismatch,
        UnknownMarkerClass,
    ) as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 1
    sys.stdout.write(f"{result.bundle_path}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
