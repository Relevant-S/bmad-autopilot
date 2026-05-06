"""Story 6.6 — Bundle-render-time evidence-trace linkability validator.

The SIXTH Epic-6 substrate landing per ``epics.md`` lines 2711-2737 —
sibling of Story 6.4's :mod:`cost_telemetry`, Story 6.5's
:mod:`cost_streaming`, Story 2.12's :mod:`event_streaming`, Story
2.2's :mod:`run_state`. The NFR-O7 substrate-level claim CLOSER paired
with Story 5.5's ``retry_history`` CLI-side surface and Story 4.12's
``qa_evidence_persistence`` opener.

Sources:
    * **PRD NFR-O7** (``_bmad-output/planning-artifacts/prd.md`` line
      986, verbatim): "Every ``evidence_refs`` entry resolves to a
      real artifact or emits a dangling-ref loud-fail marker."
    * **PRD FR55** (``prd.md`` line 887): the QA envelope's per-AC
      ``ac_results`` shape carrying the ``evidence_refs`` array
      Story 6.6 walks.
    * **Story 6.6 verbatim epic AC** at ``epics.md`` lines 2711-2737.
    * **epics.md line 2379** (verbatim, the marker-class-reuse
      rationale ratified by Story 5.5): "dangling references (path
      missing) emit a ``dangling-evidence-ref`` marker (Story 1.4
      taxonomy, reused — same diagnostic surface as evidence dangling
      refs)". Story 6.6 EXTENDS the reuse posture with a
      sub-classification per Pattern 2's ``: <cause>`` suffix format
      (architecture.md line 962) so the practitioner reads
      ``dangling-evidence-ref: qa-evidence`` vs ``dangling-evidence-ref:
      retry-history`` to distinguish source class without proliferating
      marker classes.

Marker class:
    The ``dangling-evidence-ref`` marker class is enumerated in
    ``schemas/marker-taxonomy.yaml`` lines 219-227 (Story 1.4 v1
    closed taxonomy). Story 6.6 ADDITIVELY extends the entry's
    ``sub_classifications`` list at line 227 from ``[]`` to
    ``[qa-evidence, retry-history]`` (alphabetical) per Pattern 2 —
    the same shape Story 6.5 demonstrated for ``cost-near-ceiling``'s
    ``[ceiling-crossed]``. The ``marker_class`` identifier itself is
    unchanged; the ``diagnostic_pointer`` text at lines 220-225 is
    unchanged. The constant
    :data:`loud_fail_harness.retry_history.DANGLING_EVIDENCE_REF_MARKER`
    is the single-source-of-truth literal — THIS module imports and
    re-exports it as :data:`DANGLING_EVIDENCE_REF_MARKER` for reader
    clarity rather than redefining the literal.

Composition with the bundle assembler:
    THIS module is consumed by
    :func:`loud_fail_harness.bundle_assembly.assemble_bundle` and
    :func:`loud_fail_harness.bundle_assembly_escalation.assemble_escalation_bundle`
    at the canonical render-time seam BEFORE the loud-fail block is
    rendered. The composition pattern is::

        result = validate_evidence_linkability_at_render(
            ac_results=envelopes["qa"].get("ac_results") or [],
            retry_history=run_state.retry_history,
            repo_root=pathlib.Path.cwd(),
        )
        merged_active_markers = _merge_evidence_linkability_markers(
            run_state.active_markers,
            result.marker_classifications_to_append,
        )
        loud_fail_block = _render_loud_fail_block(
            merged_active_markers, ...
        )
        per_ac_body = _render_per_ac_section(
            envelopes["qa"], ...,
            qa_evidence_dangling=result.qa_evidence_dangling,
        )

    The merge is in-memory only; the assembler does NOT write the
    derived markers back to ``run_state.yaml``. This preserves
    Pattern 4's batch-write rule (cost-counter-and-marker writes
    batch with other run-state writes between specialist completions
    — bundle-render-time validation is a UI-only augmentation, not a
    persistent state mutation) AND preserves Story 1.4's marker-
    permanence rule (markers already on-disk are sticky; the
    bundle-render-time merge is additive-and-deduplicating).

Composition with Story 5.5 :func:`retry_history.detect_dangling_refs`:
    THIS module IMPORTS the helper for the retry-history-side
    detection path; does NOT modify it. The compose-not-fork
    discipline mirrors the additive-substrate posture ratified by
    Stories 3.4 / 4.13 / 5.9 / 6.1 / 6.2 / 6.3 / 6.4 / 6.5.

Composition with Story 4.12 evidence persistence:
    THIS module reads from
    :data:`loud_fail_harness.qa_evidence_persistence.EVIDENCE_ROOT`-
    rooted paths the QA envelope already carries (``ac_results[].
    evidence_refs[].path``); does NOT modify the persistence module.
    The Story 4.7 / 4.8 ``$defs/evidence_ref`` shape (``{path, tier}``
    post-bump) is consumed AS-IS via the same isinstance(ref, dict)
    shim :func:`loud_fail_harness.bundle_assembly._render_per_ac_section`
    uses at lines 486-490.

Sensor-not-advisor invariant (FR52 / ADR-002 invariant 1):
    THIS module is FLOW-POLICY territory (orchestrator's job).
    Specialists do not call it; specialists are REPORTED-ON via the
    persisted artifacts. The pure detection helpers (the two
    ``detect_dangling_*`` functions, ``compute_dangling_evidence_marker_classifications``,
    ``format_dangling_inline_marker``, and the
    :func:`validate_evidence_linkability_at_render` composition entry
    point) are sensor-not-advisor — they return diagnostic tuples;
    the consumer (the bundle assembler) decides emission and
    rendering.

Loud-fail doctrine — visibility-not-enforcement posture:
    NFR-O7 says "Every ``evidence_refs`` entry resolves to a real
    artifact or emits a dangling-ref loud-fail marker" — it does NOT
    say "or the bundle fails to assemble." Story 6.6 surfaces
    dangling refs as markers + inline indicators; the bundle
    assembles successfully. This mirrors Story 6.5's no-auto-halt
    on cost ceiling crossing and Story 6.4's graceful-degrade on
    OTel-pipeline failure. The practitioner sees the markers in the
    loud-fail block and decides remediation — the system does NOT
    make the decision for them.

Story 5.5 CLI-hook complementarity:
    Story 5.5's ``retry-history-resolve`` CLI hook continues to
    surface dangling-ref diagnostics on hook execution per the
    existing mechanism — the bundle-assembler-side validation is a
    COMPLEMENTARY render-time check (catches refs that danglize
    between hook execution and bundle render; catches qa-evidence
    refs which Story 5.5's CLI does NOT cover).

Architectural placement (load-bearing):
    THIS module is a substrate **library**, NOT a sixth-counted
    substrate component beyond ADR-003's enumerated five
    (envelope_validator / event_validator / reconciler /
    enumeration_check / fixture_coverage). It is a sibling of
    :mod:`run_state`, :mod:`qa_evidence_persistence`,
    :mod:`retry_history`, :mod:`cost_telemetry`, :mod:`cost_streaming`
    — all substrate libraries that grew the harness module count
    without growing the substrate-component count (architecture.md
    lines 311-315).

``find_repo_root()`` discipline (Epic 1 retro Action #1):
    No path computation in this module calls ``find_repo_root()`` at
    module import time. All public helpers accept ``repo_root`` as a
    caller-supplied parameter; the bundle-assembler-side caller
    resolves :func:`loud_fail_harness._shared.find_repo_root` lazily
    at render time.
"""

from __future__ import annotations

import dataclasses
import pathlib
from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal

from loud_fail_harness.exceptions import EvidenceLinkabilityInvariantError
from loud_fail_harness.retry_history import (
    DANGLING_EVIDENCE_REF_MARKER as _RETRY_HISTORY_DANGLING_EVIDENCE_REF_MARKER,
    RetryAttemptRef,
    detect_dangling_refs,
)
from loud_fail_harness.run_state import RetryAttempt

__all__ = [
    "DANGLING_EVIDENCE_REF_MARKER",
    "DanglingEvidenceRef",
    "EvidenceLinkabilityResult",
    "QA_EVIDENCE_SUB_CLASSIFICATION",
    "RETRY_HISTORY_SUB_CLASSIFICATION",
    "compute_dangling_evidence_marker_classifications",
    "detect_dangling_qa_evidence_refs",
    "detect_dangling_retry_history_refs",
    "format_dangling_inline_marker",
    "validate_evidence_linkability_at_render",
]


# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #


#: The ``dangling-evidence-ref`` marker class identifier sourced as a
#: re-export from :mod:`loud_fail_harness.retry_history`'s
#: :data:`DANGLING_EVIDENCE_REF_MARKER` per the marker-class-reuse
#: principle (Story 1.11 ratified by Story 5.5 at ``epics.md`` line
#: 2379). The constant lives in :mod:`retry_history` for now —
#: Story 6.6 imports and re-exposes it for reader clarity. If a future
#: refactor centralizes the constant in this module, that is a
#: post-MVP cleanup tracked in ``deferred-work.md``.
DANGLING_EVIDENCE_REF_MARKER: Final[Literal["dangling-evidence-ref"]] = (
    _RETRY_HISTORY_DANGLING_EVIDENCE_REF_MARKER
)

#: The ``qa-evidence`` sub-classification per Pattern 2's ``: <cause>``
#: suffix format. Used as ``"dangling-evidence-ref: qa-evidence"`` when
#: a ``ac_results[].evidence_refs[].path`` entry resolves to a missing
#: on-disk artifact.
QA_EVIDENCE_SUB_CLASSIFICATION: Final[Literal["qa-evidence"]] = "qa-evidence"

#: The ``retry-history`` sub-classification per Pattern 2's ``: <cause>``
#: suffix format. Used as ``"dangling-evidence-ref: retry-history"``
#: when a ``run_state.retry_history[].path`` entry resolves to a
#: missing on-disk artifact.
RETRY_HISTORY_SUB_CLASSIFICATION: Final[Literal["retry-history"]] = (
    "retry-history"
)

#: Inline-rendering marker prefix for the per-bullet at-reference-
#: location indicator (rendered next to the dangling reference's
#: bullet line in ``## Per-AC results`` / ``## Retry history``). The
#: visible-emoji prefix mirrors Story 6.1's ``## ⚠️ Loud-Fail Markers``
#: block convention; the format follows
#: :mod:`loud_fail_harness.retry_history`'s ``_DANGLING_REMEDIATION_HINT``
#: convention.
_DANGLING_INLINE_MARKER_PREFIX: Final[str] = "⚠️ dangling-evidence-ref"

#: Verbatim remediation hint substring sourced from
#: ``schemas/marker-taxonomy.yaml`` line 222 ("Remediation: regenerate
#: the evidence OR fix the reference"). Surfaces in both the inline
#: per-bullet indicator and (via :exc:`EvidenceLinkabilityInvariantError`'s
#: diagnostic) any contract-violation surfaces.
_DANGLING_REMEDIATION_HINT: Final[str] = (
    "regenerate the evidence OR fix the reference"
)


# --------------------------------------------------------------------------- #
# Frozen dataclasses                                                          #
# --------------------------------------------------------------------------- #


@dataclasses.dataclass(frozen=True)
class DanglingEvidenceRef:
    """One dangling evidence reference detected at bundle-render time.

    Frozen for hashability + determinism. The five fields capture the
    union shape across both source classes; the source-vs-fields
    invariant is enforced in :meth:`__post_init__`.

    Field semantics:
        * ``source`` — the source class that produced the dangling
          reference (``"qa-evidence"`` or ``"retry-history"``). The
          source value drives the ``: <cause>`` sub-classification
          rendered in the loud-fail block via
          :func:`compute_dangling_evidence_marker_classifications`.
        * ``path`` — the missing artifact path verbatim from the
          reference (repo-relative; the same string the QA envelope
          / run-state carried).
        * ``ac_id`` — set when ``source == "qa-evidence"`` to identify
          the AC whose ``evidence_refs`` carried the dangling path;
          ``None`` when ``source == "retry-history"``.
        * ``round_id`` — set when ``source == "retry-history"`` to
          identify the retry-round; ``None`` when
          ``source == "qa-evidence"``.
        * ``retry_attempt`` — set when ``source == "retry-history"`` to
          mirror :attr:`RetryAttemptRef.retry_attempt`; ``None`` when
          ``source == "qa-evidence"``.

    Source-vs-fields invariant (NFR-O5 named-invariant
    ``source-vs-fields-mismatch``):
        * ``source == "qa-evidence"`` REQUIRES ``ac_id`` non-``None``
          AND ``round_id is None`` AND ``retry_attempt is None``.
        * ``source == "retry-history"`` REQUIRES ``round_id`` non-
          ``None`` AND ``retry_attempt`` non-``None`` AND
          ``ac_id is None``.

    Violations raise :exc:`EvidenceLinkabilityInvariantError` per
    Pattern 5's named-invariant ``Raises`` convention.
    """

    source: Literal["qa-evidence", "retry-history"]
    path: str
    ac_id: str | None
    round_id: str | None
    retry_attempt: int | None

    def __post_init__(self) -> None:
        if self.source == "qa-evidence":
            if self.ac_id is None:
                raise EvidenceLinkabilityInvariantError(
                    diagnostic=(
                        "source-vs-fields-mismatch: source='qa-evidence' "
                        "requires ac_id non-None; got "
                        f"ac_id={self.ac_id!r}, path={self.path!r}"
                    )
                )
            if self.round_id is not None:
                raise EvidenceLinkabilityInvariantError(
                    diagnostic=(
                        "source-vs-fields-mismatch: source='qa-evidence' "
                        "requires round_id is None; got "
                        f"round_id={self.round_id!r}, path={self.path!r}"
                    )
                )
            if self.retry_attempt is not None:
                raise EvidenceLinkabilityInvariantError(
                    diagnostic=(
                        "source-vs-fields-mismatch: source='qa-evidence' "
                        "requires retry_attempt is None; got "
                        f"retry_attempt={self.retry_attempt!r}, "
                        f"path={self.path!r}"
                    )
                )
        elif self.source == "retry-history":
            if self.round_id is None:
                raise EvidenceLinkabilityInvariantError(
                    diagnostic=(
                        "source-vs-fields-mismatch: source='retry-history' "
                        "requires round_id non-None; got "
                        f"round_id={self.round_id!r}, path={self.path!r}"
                    )
                )
            if self.retry_attempt is None:
                raise EvidenceLinkabilityInvariantError(
                    diagnostic=(
                        "source-vs-fields-mismatch: source='retry-history' "
                        "requires retry_attempt non-None; got "
                        f"retry_attempt={self.retry_attempt!r}, "
                        f"path={self.path!r}"
                    )
                )
            if self.ac_id is not None:
                raise EvidenceLinkabilityInvariantError(
                    diagnostic=(
                        "source-vs-fields-mismatch: source='retry-history' "
                        "requires ac_id is None; got "
                        f"ac_id={self.ac_id!r}, path={self.path!r}"
                    )
                )
        else:
            # Defensive — Literal["qa-evidence", "retry-history"]
            # nominally bars other values at the type-checker level,
            # but the runtime guard preserves loud-fail discipline if
            # a caller bypasses the typing.
            raise EvidenceLinkabilityInvariantError(
                diagnostic=(
                    "source-vs-fields-mismatch: source must be "
                    "'qa-evidence' or 'retry-history'; got "
                    f"source={self.source!r}"
                )
            )


@dataclasses.dataclass(frozen=True)
class EvidenceLinkabilityResult:
    """Return shape of :func:`validate_evidence_linkability_at_render`.

    Frozen for determinism + hashability.

    Field semantics:
        * ``dangling_refs`` — ALL dangling references across both
          sources, ordered qa-evidence-first then retry-history (each
          partition preserves input-order).
        * ``marker_classifications_to_append`` — the ordered tuple the
          caller appends to ``run_state.active_markers`` BEFORE
          rendering the loud-fail block. AT MOST TWO entries:
          ``"dangling-evidence-ref: qa-evidence"`` if any qa-evidence
          dangling exists; ``"dangling-evidence-ref: retry-history"``
          if any retry-history dangling exists; both if both
          partitions are non-empty (alphabetical order — qa-evidence
          first).
        * ``qa_evidence_dangling`` — qa-evidence partition (empty
          tuple if none) for downstream per-AC rendering use.
        * ``retry_history_dangling`` — retry-history partition (empty
          tuple if none) for downstream per-round rendering use.
    """

    dangling_refs: tuple[DanglingEvidenceRef, ...]
    marker_classifications_to_append: tuple[str, ...]
    qa_evidence_dangling: tuple[DanglingEvidenceRef, ...]
    retry_history_dangling: tuple[DanglingEvidenceRef, ...]


# --------------------------------------------------------------------------- #
# Pure detection helpers                                                      #
# --------------------------------------------------------------------------- #


def detect_dangling_qa_evidence_refs(
    *,
    ac_results: Sequence[Mapping[str, Any]],
    repo_root: pathlib.Path,
) -> tuple[DanglingEvidenceRef, ...]:
    """Walk QA's ``ac_results`` array and return one
    :class:`DanglingEvidenceRef` per missing on-disk artifact.

    Pure: the only I/O is :meth:`pathlib.Path.exists`; no logging,
    no marker emission, no print. Sensor-not-advisor: the returned
    tuple IS the diagnostic; the consumer decides emission.

    Story 4.7 / 4.8 transitive shim — ``evidence_refs`` items can be
    ``{path, tier}`` dicts (post-Story-4.8 ``$defs/evidence_ref``
    shape) OR plain strings (pre-Story-4.8 fallback). The helper
    handles both via the same ``isinstance(ref, dict)`` shim
    :func:`loud_fail_harness.bundle_assembly._render_per_ac_section`
    uses at lines 486-490 — corrupted entries (missing ``path``
    field; non-string ``path``) are silently skipped (the QA-
    envelope-side schema validation owns shape-integrity per
    Story 4.7's enforcement).

    Order is preserved (AC-order × evidence-ref-order). Empty
    ``ac_results`` → empty tuple.

    Args:
        ac_results: The QA envelope's ``ac_results`` array (each
            entry carries an ``ac_id`` string and an ``evidence_refs``
            sequence per FR55).
        repo_root: The repository root the ``evidence_refs[].path``
            strings are anchored to (typically Story 4.12's
            :data:`loud_fail_harness.qa_evidence_persistence.EVIDENCE_ROOT`-
            rooted path's repo-relative form).

    Returns:
        Tuple of dangling :class:`DanglingEvidenceRef` instances in
        input-order; ``source="qa-evidence"`` for every entry.
    """
    dangling: list[DanglingEvidenceRef] = []
    for entry in ac_results:
        if not isinstance(entry, Mapping):
            continue
        ac_id = entry.get("ac_id")
        if not isinstance(ac_id, str):
            continue
        evidence_refs = entry.get("evidence_refs") or []
        if not isinstance(evidence_refs, Sequence) or isinstance(evidence_refs, str):
            continue
        for ref in evidence_refs:
            if isinstance(ref, Mapping):
                path = ref.get("path")
            elif isinstance(ref, str):
                path = ref
            else:
                continue
            if not isinstance(path, str) or not path:
                continue
            if pathlib.PurePosixPath(path).is_absolute():
                continue
            if not (repo_root / path).exists():
                dangling.append(
                    DanglingEvidenceRef(
                        source="qa-evidence",
                        path=path,
                        ac_id=ac_id,
                        round_id=None,
                        retry_attempt=None,
                    )
                )
    return tuple(dangling)


def detect_dangling_retry_history_refs(
    *,
    retry_history: Sequence[Mapping[str, Any] | RetryAttempt],
    repo_root: pathlib.Path,
) -> tuple[DanglingEvidenceRef, ...]:
    """Walk ``retry_history`` and return one
    :class:`DanglingEvidenceRef` per missing on-disk artifact.

    Pure: the only I/O is :meth:`pathlib.Path.exists` (delegated via
    :func:`loud_fail_harness.retry_history.detect_dangling_refs`); no
    logging, no marker emission, no print. Sensor-not-advisor.

    Accepts BOTH :class:`loud_fail_harness.run_state.RetryAttempt`
    Pydantic models (the run-state-side tuple element shape) AND raw
    dict mappings (escalation-bundle context's ``retry_history_refs``
    shape). Pre-Story-5.5 entries lacking ``path`` / ``round_id``
    are silently skipped — the same skip-criterion
    :func:`loud_fail_harness.bundle_assembly_escalation._retry_attempt_ref_payload`
    uses.

    Compose-not-fork: for thickened entries the helper constructs a
    :class:`RetryAttemptRef` and delegates to
    :func:`loud_fail_harness.retry_history.detect_dangling_refs` for
    the actual filesystem check.

    Order is preserved (input-order). Empty ``retry_history`` → empty
    tuple.

    Args:
        retry_history: Sequence of retry-attempt entries — either
            :class:`RetryAttempt` Pydantic models (canonical run-
            state shape) or raw dict mappings (escalation-bundle
            context). Pre-Story-5.5 entries (no ``path`` / ``round_id``
            fields) are silently skipped.
        repo_root: The repository root the
            :attr:`RetryAttemptRef.path` strings are anchored to
            (typically
            :data:`loud_fail_harness.retry_history.RETRY_HISTORY_ROOT`-
            rooted form).

    Returns:
        Tuple of dangling :class:`DanglingEvidenceRef` instances in
        input-order; ``source="retry-history"`` for every entry.
    """
    dangling: list[DanglingEvidenceRef] = []
    for entry in retry_history:
        round_id: Any
        path: Any
        retry_attempt: Any
        retry_reason: Any
        if isinstance(entry, RetryAttempt):
            round_id = entry.round_id
            path = entry.path
            retry_attempt = entry.retry_attempt
            retry_reason = entry.retry_reason
        elif isinstance(entry, Mapping):
            round_id = entry.get("round_id")
            path = entry.get("path")
            retry_attempt = entry.get("retry_attempt")
            retry_reason = entry.get("retry_reason")
        else:
            continue
        # Pre-Story-5.5 skip-criterion: same as
        # bundle_assembly_escalation._retry_attempt_ref_payload uses.
        if not isinstance(round_id, str) or not round_id:
            continue
        if not isinstance(path, str) or not path:
            continue
        if not isinstance(retry_attempt, int) or retry_attempt < 1:
            continue
        if not isinstance(retry_reason, str) or not retry_reason:
            continue
        ref = RetryAttemptRef(
            retry_attempt=retry_attempt,
            retry_reason=retry_reason,
            round_id=round_id,
            path=path,
        )
        if detect_dangling_refs(refs=(ref,), repo_root=repo_root):
            dangling.append(
                DanglingEvidenceRef(
                    source="retry-history",
                    path=ref.path,
                    ac_id=None,
                    round_id=ref.round_id,
                    retry_attempt=ref.retry_attempt,
                )
            )
    return tuple(dangling)


def compute_dangling_evidence_marker_classifications(
    dangling: Sequence[DanglingEvidenceRef],
) -> tuple[str, ...]:
    """Partition ``dangling`` by source and emit the source-class
    summary marker classifications.

    Returns AT MOST TWO marker strings —
    ``"dangling-evidence-ref: qa-evidence"`` if any qa-evidence
    dangling exists; ``"dangling-evidence-ref: retry-history"`` if
    any retry-history dangling exists; both if both partitions are
    non-empty. The order is deterministic — qa-evidence FIRST then
    retry-history (alphabetical by sub-classification — same ordering
    convention :func:`loud_fail_harness.bundle_assembly._render_loud_fail_block`
    uses at lines 1129-1140).

    The function emits ONE marker per source-class regardless of how
    many individual dangling refs exist within that class — the
    per-ref detail is NOT lost: each dangling ref is individually
    rendered inline at its location in the per-AC body via
    :func:`format_dangling_inline_marker`. Mirrors Story 6.4's
    per-(specialist × retry) cost-breakdown vs single
    ``cost-telemetry-unavailable`` marker decomposition.

    Empty input → empty tuple.
    """
    has_qa_evidence = any(ref.source == "qa-evidence" for ref in dangling)
    has_retry_history = any(ref.source == "retry-history" for ref in dangling)
    classifications: list[str] = []
    if has_qa_evidence:
        classifications.append(
            f"{DANGLING_EVIDENCE_REF_MARKER}: {QA_EVIDENCE_SUB_CLASSIFICATION}"
        )
    if has_retry_history:
        classifications.append(
            f"{DANGLING_EVIDENCE_REF_MARKER}: "
            f"{RETRY_HISTORY_SUB_CLASSIFICATION}"
        )
    return tuple(classifications)


def format_dangling_inline_marker(*, ref: DanglingEvidenceRef) -> str:
    """Render the inline-at-reference-location marker text appended
    next to the dangling reference's bullet line.

    Format: ``⚠️ dangling-evidence-ref: <sub-classification> — <remediation> (path={path!r})``.

    The visible-emoji prefix mirrors Story 6.1's ``## ⚠️ Loud-Fail
    Markers`` block convention; the rendered text is plain-text (no
    HTML) per the bundle markdown convention; visible-color framing
    is downstream renderer concern (sensor-not-advisor).

    Pure; idempotent + byte-stable for a given input.
    """
    sub_classification = (
        QA_EVIDENCE_SUB_CLASSIFICATION
        if ref.source == "qa-evidence"
        else RETRY_HISTORY_SUB_CLASSIFICATION
    )
    return (
        f"{_DANGLING_INLINE_MARKER_PREFIX}: {sub_classification} — "
        f"{_DANGLING_REMEDIATION_HINT} (path={ref.path!r})"
    )


# --------------------------------------------------------------------------- #
# Composition entry point                                                     #
# --------------------------------------------------------------------------- #


def validate_evidence_linkability_at_render(
    *,
    ac_results: Sequence[Mapping[str, Any]],
    retry_history: Sequence[Mapping[str, Any] | RetryAttempt],
    repo_root: pathlib.Path,
) -> EvidenceLinkabilityResult:
    """Composition entry point: walk both source classes and return
    the full :class:`EvidenceLinkabilityResult`.

    Composes :func:`detect_dangling_qa_evidence_refs` +
    :func:`detect_dangling_retry_history_refs` +
    :func:`compute_dangling_evidence_marker_classifications` into a
    single render-time validation surface.

    Pure: the only I/O is :meth:`pathlib.Path.exists` via the two
    detection helpers; no logging, no marker emission, no print.
    Idempotent + byte-stable: a second call with the same inputs
    returns the same :class:`EvidenceLinkabilityResult`.

    Args:
        ac_results: The QA envelope's ``ac_results`` array.
        retry_history: The run-state's ``retry_history`` sequence.
        repo_root: The repository root.

    Returns:
        :class:`EvidenceLinkabilityResult`.
    """
    qa_evidence_dangling = detect_dangling_qa_evidence_refs(
        ac_results=ac_results, repo_root=repo_root
    )
    retry_history_dangling = detect_dangling_retry_history_refs(
        retry_history=retry_history, repo_root=repo_root
    )
    all_dangling = qa_evidence_dangling + retry_history_dangling
    classifications = compute_dangling_evidence_marker_classifications(
        all_dangling
    )
    return EvidenceLinkabilityResult(
        dangling_refs=all_dangling,
        marker_classifications_to_append=classifications,
        qa_evidence_dangling=qa_evidence_dangling,
        retry_history_dangling=retry_history_dangling,
    )
