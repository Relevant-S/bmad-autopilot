"""Story 4.12 — Evidence persistence + size budget + truncation marker
+ sanitization mechanism.

The pure-library substrate component owning the canonical
``_bmad-output/qa-evidence/{story-id}/{run-id}/`` persistence path
(FR49), per-run ``run_id`` allocation (NFR-R4), the Pattern-5 atomic-
on-failure ``evidence-truncated`` marker emission helper + size-budget
decision function (NFR-P6), AND the cross-component reuse documentation
for the existing :class:`MaskedSelectorPolicy` sanitization mechanism
(NFR-S2). Composed by Story 4.13's wrapper-thickening procedure into
the QA wrapper's per-AC evidence-write loop; consumed AS-IS by Story
7.5's ``qa-runbook.yaml.template`` init-time scaffolding (the
``max_evidence_size_mb`` field is read at the wrapper boundary, not
inside this module).

Sources:
    * Verbatim epic AC at ``_bmad-output/planning-artifacts/epics.md``
      lines 2150-2180.
    * PRD FR49 (line 878) — "QA behavioral evidence is persisted at
      ``_bmad-output/qa-evidence/{story-id}/{run-id}/`` (gitignored)
      with a configurable ``max_evidence_size_mb`` budget."
    * PRD NFR-P6 (line 939) — "Evidence bundle size budget — per-run
      evidence bundle … respects a configurable ``max_evidence_size_mb``
      limit … Overruns are truncated with a loud-fail marker
      (``evidence-truncated: {story-id}``)."
    * PRD NFR-R4 (line 948) — "Evidence durability — QA evidence is
      preserved across orchestrator crashes and session restarts.
      Evidence from past runs on the same story is not overwritten by
      new runs (distinct ``run-id`` per run)."
    * PRD NFR-S2 (line 970) — "Evidence bundle sanitization — … the
      Automator does not automatically scrub sensitive content. …
      Sensitive-data masking is the practitioner's responsibility; the
      Automator provides the masking mechanism, not the policy."
    * PRD FR31 (line 853) — every loud-fail marker carries an
      actionable how-to-enable pointer.

Verbatim epic AC checklist (epics.md lines 2156-2180):
    1. Persistence-path discipline — ``_bmad-output/qa-evidence/
       {story-id}/{run-id}/`` (gitignored). Owned by
       :func:`compute_evidence_root` + :func:`compute_run_dir`.
    2. Per-run ``run_id`` allocation — UTC ``YYYYMMDDTHHMMSSZ`` stamp;
       distinct per orchestrator-driven QA dispatch; NEVER overwrites
       prior runs. Owned by :func:`allocate_run_id`.
    3. Size-budget enforcement — ``max_evidence_size_mb`` byte ceiling;
       overruns emit the ``evidence-truncated`` marker. Owned by
       :func:`evaluate_size_budget` + :func:`surface_evidence_truncated`.
    4. Sanitization mechanism — the existing
       :class:`MaskedSelectorPolicy` (Story 4.4) is the canonical
       mechanism; THIS module documents the reuse posture. The absence
       of a ``masking-not-configured`` marker IS the structural
       enforcement of NFR-S2's "Automator does not auto-scrub" doctrine.
    5. Audit-doc visibility — ``docs/extension-audit.md`` carries the
       new ``automator-internal`` row recording the absence-of-marker
       decision.

Pattern 5 (atomic-on-failure) at :func:`surface_evidence_truncated`
mirrors Story 4.6's :func:`surface_smoke_first_abort` and Story 4.8's
:func:`surface_tier_3_not_configured` byte-for-byte: the registry is
validated FIRST; on rejection :exc:`UnknownMarkerClass` propagates
with NO partial state constructed.

Cross-component reuse posture:
    * :class:`MarkerClassRegistry` + :func:`validate_marker_emission`
      from :mod:`loud_fail_harness.specialist_dispatch` — AS-IS reuse
      (mirroring Stories 4.6 / 4.8 / 4.9).
    * :class:`MaskedSelectorPolicy` (``playwright_driver.py`` line 374;
      api-side mirror used by ``http_driver.py`` per Story 4.5) is the
      canonical sanitization mechanism per NFR-S2 — the masking
      algorithm lives at the driver level (``playwright_driver.py``
      line 1275 + ``http_driver.py`` line 1215); THIS module does NOT
      call it, does NOT extend it, does NOT modify its default. The
      ``masked_selectors`` field defaults to an empty tuple
      (``playwright_driver.py`` line 396); when the field is empty,
      drivers persist evidence raw — NO redaction, NO marker emission,
      NO log warning per the verbatim epic AC at ``epics.md`` lines
      2173-2176. The non-emission of a ``masking-not-configured``
      marker is a structural choice — emitting a marker on absence
      would constitute "auto-scrubbing-by-shame" per the verbatim
      epic AC at line 2175 and would violate NFR-S2's "Automator
      does not auto-scrub" doctrine. THIS story enforces the non-
      emission BY NOT IMPLEMENTING such a marker AND by recording
      the decision in ``docs/extension-audit.md`` per AC-5.
    * :mod:`qa_evidence_tier`'s shape patterns (Pydantic frozen
      models; co-exposed ``marker_record`` + ``diagnostic_context``;
      :data:`_HOW_TO_ENABLE_POINTER` freshness-test pattern) are
      MIRRORED IN STRUCTURE byte-for-byte.
    * Per-run wrapper-side composition (Story 4.13) constructs
      :class:`MaskedSelectorPolicy` from
      ``_bmad/automation/qa-runbook.yaml``'s ``masked_selectors``
      field (Story 7.5 owns the runbook stub generation per
      ``epics.md`` line 3022); the policy is then threaded into
      :func:`iterate_acs` (``qa_ac_iteration.py`` line 452 — already
      accepts :class:`MaskedSelectorPolicy`) AS-IS.
    * Wrapper-side collision-handling delegation: THIS module is
      pure-library — :func:`allocate_run_id` does NOT introduce a
      uniqueness lock, does NOT read the filesystem to check
      existence, does NOT loop on collision. The orchestrator-driven
      cadence (separate Task tool invocations) provides the natural
      sub-second-or-greater spacing that makes collisions vanishingly
      rare in practice; the wrapper-side responsibility (Story 4.13)
      is "if ``compute_run_dir(story_id, run_id).exists()``, allocate
      a new one" — THIS story's pure-library scope ends at the format
      declaration.

Sensor-not-advisor split:
    THIS module RENDERS path strings + DECIDES budget verdict + EMITS
    marker records. THIS module does NOT call validators, does NOT
    read files, does NOT log, does NOT write to the filesystem.
    Wrapper-side I/O lives at Story 4.13.

In-place-thickening linkage (Epic 3 retro Insight #1):
    THIS story does NOT modify ``agents/qa.md`` — Story 4.13 owns
    wrapper-thickening completion (composes
    :func:`evaluate_size_budget` verdicts into actual disk writes /
    skips and threads :class:`EvidenceTruncatedEmissionRecord` into
    the QA envelope's marker emissions).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loud_fail_harness.input_hardening import harden_identifier
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

# --------------------------------------------------------------------------- #
# Symbolic constants                                                          #
# --------------------------------------------------------------------------- #

#: The canonical marker class identifier for the ``evidence-truncated``
#: emission (Story 1.4 enumeration; ``schemas/marker-taxonomy.yaml``
#: line 144). Consumed AS-IS; THIS module is the FIRST runtime emitter.
#: Mirrors Story 4.8's :data:`TIER_3_NOT_CONFIGURED_MARKER` constant
#: pattern at ``qa_evidence_tier.py`` byte-for-byte.
EVIDENCE_TRUNCATED_MARKER: Final[Literal["evidence-truncated"]] = (
    "evidence-truncated"
)

#: The canonical literal for the FR49 evidence-path root,
#: ``_bmad-output/qa-evidence``. Single source of truth: downstream
#: consumers (Story 4.13 wrapper composition, Story 7.5 init
#: scaffolding) read this constant rather than re-typing the literal.
EVIDENCE_ROOT: Final[str] = "_bmad-output/qa-evidence"


# --------------------------------------------------------------------------- #
# How-to-enable pointer (per FR31 actionable remediation surface)             #
# --------------------------------------------------------------------------- #

#: The verbatim multiline ``diagnostic_pointer`` text for the
#: ``evidence-truncated`` marker class, copied AS-IS from
#: ``schemas/marker-taxonomy.yaml`` lines 145-149. The substrate
#: library does NOT itself read the YAML at runtime — this constant
#: is the canonical compile-time copy. The
#: :mod:`test_qa_evidence_persistence` byte-equality freshness test
#: asserts this constant equals the YAML's ``diagnostic_pointer``
#: field for the ``evidence-truncated`` entry, preventing silent drift.
_HOW_TO_ENABLE_POINTER: Final[str] = (
    "QA evidence (screenshot / DOM / HTTP log) exceeded `max_evidence_size_mb`\n"
    "and was truncated for the bundle. Remediation: inspect the truncated\n"
    "artifact at its on-disk path under\n"
    "`_bmad-output/qa-evidence/{story-id}/{run-id}/`.\n"
)

# --------------------------------------------------------------------------- #
# Path helpers                                                                #
# --------------------------------------------------------------------------- #


def compute_evidence_root(story_id: str) -> PurePosixPath:
    """Return the per-story evidence root ``_bmad-output/qa-evidence/{story-id}``.

    Repo-relative, OS-independent. Uses :class:`PurePosixPath` so the
    rendered string is forward-slash-separated regardless of host OS
    — mirrors the canonical-path discipline at
    ``qa_evidence_tier.py`` lines 152-154 (FR49 paths are repo-
    relative, not OS-native).

    Args:
        story_id: The BMAD story identifier; appended under
            :data:`EVIDENCE_ROOT`.

    Returns:
        :class:`PurePosixPath` representing
        ``_bmad-output/qa-evidence/{story-id}``.
    """
    if not story_id:
        raise ValueError("story_id must not be empty")
    if ".." in PurePosixPath(story_id).parts:
        raise ValueError(
            f"story_id must not contain '..' path traversal segments; "
            f"got {story_id!r}"
        )
    return PurePosixPath(EVIDENCE_ROOT) / story_id


def compute_run_dir(story_id: str, run_id: str) -> PurePosixPath:
    """Return the per-run evidence dir ``_bmad-output/qa-evidence/{story-id}/{run-id}``.

    Composes :func:`compute_evidence_root` with the per-run ``run_id``
    sub-segment per FR49's canonical path structure.

    Args:
        story_id: The BMAD story identifier.
        run_id: The per-run identifier produced by
            :func:`allocate_run_id`.

    Returns:
        :class:`PurePosixPath` representing
        ``_bmad-output/qa-evidence/{story-id}/{run-id}``.
    """
    if not run_id:
        raise ValueError("run_id must not be empty")
    if ".." in PurePosixPath(run_id).parts:
        raise ValueError(
            f"run_id must not contain '..' path traversal segments; "
            f"got {run_id!r}"
        )
    return compute_evidence_root(story_id) / run_id


def allocate_run_id(now: datetime | None = None) -> str:
    """Return a 16-character UTC stamp ``YYYYMMDDTHHMMSSZ`` for a QA run.

    Format pin: exactly 16 characters; uppercase ``T`` + uppercase
    ``Z``; no hyphens, colons, or fractional seconds. The format is
    stable, sortable lexicographically (NFR-R4 inspection ergonomics
    — "practitioner can inspect prior runs" line 948).

    THIS function does NOT introduce a uniqueness lock, does NOT
    read the filesystem to check existence, does NOT loop on
    collision. The wrapper-side composition (Story 4.13) handles
    on-disk uniqueness — see the module docstring's
    "Cross-component reuse posture" → "Wrapper-side collision-
    handling delegation".

    Args:
        now: Optional injected current-instant for tests. Defaults
            to :func:`datetime.now` against
            :data:`datetime.timezone.utc`.

    Returns:
        UTC stamp as a 16-character string matching ``^\\d{8}T\\d{6}Z$``.
    """
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError(
            "now must be timezone-aware; got a naive datetime. "
            "Use datetime.now(timezone.utc) or pass an aware datetime."
        )
    return instant.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class EvidenceTruncatedDiagnosticContext(BaseModel):
    """The three-field diagnostic context carried on the
    ``evidence-truncated`` marker emission (per FR31).

    Field semantics:
        * ``story_id`` — the BMAD story identifier the dispatch is
          scoped to.
        * ``run_id`` — the per-run identifier produced by
          :func:`allocate_run_id` for the in-flight QA dispatch.
        * ``how_to_enable_pointer`` — the per-FR31 actionable
          remediation pointer; sourced from
          ``schemas/marker-taxonomy.yaml`` lines 145-149's
          ``diagnostic_pointer`` field (the canonical copy lives at
          :data:`_HOW_TO_ENABLE_POINTER`).

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.
    Mirrors :class:`Tier3NotConfiguredDiagnosticContext` byte-for-
    byte in shape.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    how_to_enable_pointer: str = Field(min_length=1)

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> "EvidenceTruncatedDiagnosticContext":
        """Input-hardening (Story 24.2). Route ``story_id``/``run_id`` through the
        shared helper (rejects whitespace-only / embedded-newline / null-byte)."""
        harden_identifier(self.story_id, "EvidenceTruncatedDiagnosticContext.story_id")
        harden_identifier(self.run_id, "EvidenceTruncatedDiagnosticContext.run_id")
        return self


class EvidenceTruncatedEmissionRecord(BaseModel):
    """One marker-emission record for the ``evidence-truncated`` channel.

    Local to Story 4.12 — NOT a reuse of Story 4.6's
    :class:`SmokeFirstAbortEmissionRecord` or Story 4.8's
    :class:`Tier3NotConfiguredEmissionRecord` per the cross-story-
    coupling-avoidance posture (different diagnostic shape, different
    remediation surface).

    Frozen for determinism + hashability. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``marker_class`` — the canonical marker class identifier
          (always ``"evidence-truncated"`` at this story's scope;
          verified by the :data:`EVIDENCE_TRUNCATED_MARKER` symbolic
          constant).
        * ``diagnostic_context`` — the three-field
          :class:`EvidenceTruncatedDiagnosticContext` carried on the
          marker emission. Bundle-assembler consumers (Story 4.13)
          read this field to render the human-readable diagnostic
          sub-section + the actionable how-to-enable pointer.
    """

    model_config = ConfigDict(frozen=True)

    marker_class: Literal["evidence-truncated"]
    diagnostic_context: EvidenceTruncatedDiagnosticContext


class EvidenceTruncatedEmission(BaseModel):
    """The atomic-emission return shape of
    :func:`surface_evidence_truncated`.

    Mirrors Story 4.8's :class:`Tier3NotConfiguredEmission` co-
    exposure pattern at ``qa_evidence_tier.py`` lines 223-250 byte-
    for-byte (the ``diagnostic_context`` is co-exposed alongside the
    ``marker_record`` for ergonomic access without unwrapping the
    record — the equal payload object as
    ``marker_record.diagnostic_context``).

    Frozen for determinism + hashability. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``marker_record`` — the
          :class:`EvidenceTruncatedEmissionRecord` carrying
          ``marker_class="evidence-truncated"`` + the three-field
          diagnostic context.
        * ``diagnostic_context`` — the three-field
          :class:`EvidenceTruncatedDiagnosticContext`. Co-exposed for
          ergonomic access (equal payload object as
          ``marker_record.diagnostic_context``).
    """

    model_config = ConfigDict(frozen=True)

    marker_record: EvidenceTruncatedEmissionRecord
    diagnostic_context: EvidenceTruncatedDiagnosticContext


class SizeBudgetOutcome(BaseModel):
    """The result-shape returned by :func:`evaluate_size_budget`.

    Two-variant discriminator field ``verdict`` selects between the
    accept-branch (no marker emitted) and the truncate-branch (the
    :class:`EvidenceTruncatedEmissionRecord` is co-carried).

    Frozen for determinism + hashability. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``verdict`` — ``"accept"`` when the cumulative bundle size
          (current + incoming) fits under the byte ceiling (boundary
          at exact equality is ``accept``); ``"truncate"`` when it
          exceeds.
        * ``marker_record`` — populated only on the ``"truncate"``
          branch with the
          :class:`EvidenceTruncatedEmissionRecord` produced by
          :func:`surface_evidence_truncated`. ``None`` on the
          ``"accept"`` branch.
    """

    model_config = ConfigDict(frozen=True)

    verdict: Literal["accept", "truncate"]
    marker_record: EvidenceTruncatedEmissionRecord | None = None

    @model_validator(mode="after")
    def _check_verdict_marker_consistency(self) -> "SizeBudgetOutcome":
        if self.verdict == "accept" and self.marker_record is not None:
            raise ValueError(
                "SizeBudgetOutcome: verdict='accept' requires marker_record=None"
            )
        if self.verdict == "truncate" and self.marker_record is None:
            raise ValueError(
                "SizeBudgetOutcome: verdict='truncate' requires a non-None marker_record"
            )
        return self


# --------------------------------------------------------------------------- #
# Emission helpers + decision function                                        #
# --------------------------------------------------------------------------- #


def surface_evidence_truncated(
    story_id: str,
    run_id: str,
    registry: MarkerClassRegistry,
) -> EvidenceTruncatedEmission:
    """Atomic-on-failure ``evidence-truncated`` emission helper.

    Mirrors Story 4.8's :func:`surface_tier_3_not_configured` Pattern-5
    atomic-on-failure structure byte-for-byte:
    :func:`validate_marker_emission` runs FIRST; on registry rejection
    :exc:`UnknownMarkerClass` propagates UNCHANGED per Pattern 5
    BEFORE any partial state is constructed.

    Behavior:
        * **Step 1 — Validate marker emission FIRST**. Calls
          :func:`validate_marker_emission(registry,
          EVIDENCE_TRUNCATED_MARKER)`. On registry rejection
          :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
          propagates per Pattern 5; NO partial state is constructed
          (atomic-on-failure).
        * **Step 2 — Construct the diagnostic context** carrying
          ``story_id`` + ``run_id`` + ``how_to_enable_pointer``
          (sourced from :data:`_HOW_TO_ENABLE_POINTER`).
        * **Step 3 — Construct the marker emission record** carrying
          the canonical marker class string ``"evidence-truncated"``
          + the diagnostic context.
        * **Step 4 — Return the** :class:`EvidenceTruncatedEmission`
          carrying both the marker record + the (co-exposed)
          diagnostic context.

    Pure: no file I/O, no story-doc reads or writes, no marker
    emission to the orchestrator-event log (the
    :class:`EvidenceTruncatedEmissionRecord` is data the wrapper
    consumes; the structured bundle-comment marker is rendered by
    the bundle assembler when reading the envelope's marker
    emissions — Story 4.13 finalizes that rendering surface).

    Args:
        story_id: The BMAD story identifier; threaded into the
            diagnostic context.
        run_id: The per-run identifier produced by
            :func:`allocate_run_id`; threaded into the diagnostic
            context.
        registry: The runtime
            :class:`loud_fail_harness.specialist_dispatch.MarkerClassRegistry`
            from
            :func:`loud_fail_harness.specialist_dispatch.load_marker_class_registry`;
            must contain the ``evidence-truncated`` marker class
            (verified by Story 1.4's enumeration). Registry rejection
            raises :exc:`UnknownMarkerClass`.

    Returns:
        :class:`EvidenceTruncatedEmission` carrying ``marker_record``
        + ``diagnostic_context``.

    Raises:
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
            registry does not contain ``"evidence-truncated"``.
            Pattern 5 named-invariant diagnostic; the substrate seam's
            existing exception type.
    """
    validate_marker_emission(registry, EVIDENCE_TRUNCATED_MARKER)

    diagnostic_context = EvidenceTruncatedDiagnosticContext(
        story_id=story_id,
        run_id=run_id,
        how_to_enable_pointer=_HOW_TO_ENABLE_POINTER,
    )
    marker_record = EvidenceTruncatedEmissionRecord(
        marker_class=EVIDENCE_TRUNCATED_MARKER,
        diagnostic_context=diagnostic_context,
    )
    return EvidenceTruncatedEmission(
        marker_record=marker_record,
        diagnostic_context=diagnostic_context,
    )


def evaluate_size_budget(
    story_id: str,
    run_id: str,
    current_total_bytes: int,
    incoming_write_bytes: int,
    max_size_bytes: int,
    registry: MarkerClassRegistry,
) -> SizeBudgetOutcome:
    """Pattern-5 atomic-on-failure size-budget decision per NFR-P6.

    The pure decision function correctly branches on the verbatim
    epic AC at ``epics.md`` lines 2163-2166:

        * **accept branch** —
          ``current_total_bytes + incoming_write_bytes <=
          max_size_bytes`` →
          :class:`SizeBudgetOutcome` ``(verdict="accept",
          marker_record=None)``. NO marker emission. NO registry
          interaction (the registry parameter is accepted but unused
          on the accept branch — defensive contract for the truncate
          branch's symmetric signature).
        * **boundary at exact equality** —
          ``current_total_bytes + incoming_write_bytes ==
          max_size_bytes`` is the LAST acceptable write — verdict is
          ``accept``. The next byte tips into ``truncate``.
        * **truncate branch** —
          ``current_total_bytes + incoming_write_bytes >
          max_size_bytes`` → calls
          :func:`surface_evidence_truncated(story_id, run_id,
          registry)`; on success returns
          :class:`SizeBudgetOutcome` ``(verdict="truncate",
          marker_record=emission.marker_record)``; on
          :exc:`UnknownMarkerClass` propagates UNCHANGED per
          Pattern 5 (the registry-rejection failure is not catchable
          here — atomic-on-failure means no partial state is ever
          returned).

    The function does NOT touch the filesystem (no read, no write,
    no ``os.path``) — it is the pure decision; the wrapper composes
    the actual write/skip at Story 4.13. The ``max_size_bytes``
    parameter accepts the byte-count integer derived from
    ``max_evidence_size_mb * 1024 * 1024`` at the wrapper-side
    reading of ``_bmad/automation/config.yaml`` per Story 7.5's
    ``evidence_max_size_mb`` field (PRD line 939; ``epics.md`` line
    3017).

    Args:
        story_id: The BMAD story identifier; threaded into the
            diagnostic context on the truncate branch.
        run_id: The per-run identifier; threaded into the diagnostic
            context on the truncate branch.
        current_total_bytes: Cumulative bytes already written to the
            evidence bundle for the in-flight run. Must be ``>= 0``.
        incoming_write_bytes: Byte count of the next intended write.
            Must be ``>= 0``.
        max_size_bytes: The byte ceiling derived from
            ``max_evidence_size_mb * 1024 * 1024`` at the wrapper
            boundary.
        registry: The runtime marker-class registry; consumed only
            on the truncate branch.

    Returns:
        :class:`SizeBudgetOutcome` carrying the verdict and (on
        truncate) the marker record.

    Raises:
        ValueError: ``current_total_bytes`` or
            ``incoming_write_bytes`` is negative. Pattern-5 named-
            invariant diagnostic; defensive bound on integer-
            arithmetic input — the caller cannot pass negatives
            accidentally because byte counts are non-negative by
            physical meaning; the explicit guard catches programming-
            error reuse.
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
            registry does not contain ``"evidence-truncated"``;
            propagates from :func:`surface_evidence_truncated`. Only
            reachable on the truncate branch.
    """
    if current_total_bytes < 0 or incoming_write_bytes < 0:
        raise ValueError(
            "current_total_bytes and incoming_write_bytes must be >= 0; "
            f"got current_total_bytes={current_total_bytes!r}, "
            f"incoming_write_bytes={incoming_write_bytes!r}"
        )
    if max_size_bytes <= 0:
        raise ValueError(
            "max_size_bytes must be > 0; "
            f"got max_size_bytes={max_size_bytes!r}. "
            "Check the max_evidence_size_mb configuration value."
        )

    if current_total_bytes + incoming_write_bytes <= max_size_bytes:
        return SizeBudgetOutcome(verdict="accept", marker_record=None)

    emission = surface_evidence_truncated(story_id, run_id, registry)
    return SizeBudgetOutcome(
        verdict="truncate", marker_record=emission.marker_record
    )


__all__ = (
    "EVIDENCE_ROOT",
    "EVIDENCE_TRUNCATED_MARKER",
    "EvidenceTruncatedDiagnosticContext",
    "EvidenceTruncatedEmission",
    "EvidenceTruncatedEmissionRecord",
    "SizeBudgetOutcome",
    "allocate_run_id",
    "compute_evidence_root",
    "compute_run_dir",
    "evaluate_size_budget",
    "surface_evidence_truncated",
)
