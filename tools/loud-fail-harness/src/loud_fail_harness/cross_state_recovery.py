"""Cross-state consistency recovery algorithm — Story 8.2 substrate library.

## Substrate-component identity

THIS module is a substrate **library** sibling of
:mod:`loud_fail_harness.session_start_reattach` (Story 8.1),
:mod:`loud_fail_harness.init_non_destructive_guard` (Story 7.6),
:mod:`loud_fail_harness.tea_boundary_orientation` (Story 7.8), and
:mod:`loud_fail_harness.story_doc_version_check` (Story 7.7). It is **NOT a
sixth substrate component** beyond ADR-003 Consequence 1's enumerated five
(``envelope_validator``, ``event_validator``, ``reconciler``,
``enumeration_check``, ``fixture_coverage``); the count remains FIVE through
Epic 8 per the Epic 7 retro framing
(``epic-7-retro-2026-05-08.md`` line 122).

The module is the SECOND Epic-8 runtime-code introduction (after Story 8.1's
SessionStart reattachment substrate). Consumers:

* The orchestrator skill at ``/bmad-automation resume <story-id>`` time
  (Story 8.3 — the explicit-reattach path; consumes the algorithm against
  a practitioner-named story-id).
* Story 8.1's :func:`session_start_reattach.evaluate_reattach`
  reattach-clean branch may thread the recovery call into its branch in a
  future amendment; at THIS story's landing the 8.1 substrate is unchanged
  per AC-11.

## Architectural anchors

- **NFR-R8** (PRD line 952 verbatim) — "Cross-state consistency — story-doc
  writes complete before run-state advances. On crash recovery
  disagreement: story-doc canonical, run-state reconstructed from it."
- **NFR-R7** (PRD line 951) — "No destructive resume" — the substrate is
  read-only against story-doc, sprint-status, and the git working tree.
  Story 8.6's ``can_dispatch()`` substrate guard supersedes this
  documentation commitment with structural enforcement.
- **NFR-R2** (PRD line 946) — "Crash recovery without duplicate state
  advance."
- **ADR-005 Sub-decision (b) Reading 3** (architecture.md line 462) —
  "domain-canonical in normal flow; story-doc-wins-tiebreak in recovery
  disagreement." This module IS the implementation of Reading 3.
- **ADR-005 Consequence 1** (architecture.md lines 499, 504-509) — story-doc
  section presence is the canonical state oracle for cross-state
  reconciliation; post-recovery run-state instances conform to the same
  schema as pre-crash instances (the substrate runs a defensive
  ``Draft202012Validator.iter_errors`` on rebuilt instances per AC-6).
- **Story 1.4 v1 marker taxonomy** — ``recovery-state-conflict`` is the
  canonical halt marker (``schemas/marker-taxonomy.yaml`` lines 372-380);
  this module CONSUMES the existing taxonomy entry AS-IS (NO new marker
  classes). ``pointer_context_fields: []`` means no template
  interpolation is required at emission time.
- **Story 1.11 atomic-vs-aggregated principle** — the algorithm enumerates
  named atomic disagreement classes per AC-3 (``lifecycle-state-mismatch``,
  ``active-markers-divergence``, ``specialist-dispatched-no-return``,
  ``sprint-status-disagrees-with-story-doc``, ``retry-history-irreconcilable``,
  ``story-doc-corrupt-or-missing``, ``no-run-state-on-disk``) without
  inventing an umbrella sub-classification.
- **Pattern 5** loud-fail / named invariants — :class:`CrossStateRecoveryError`
  surfaces substrate-level failures (e.g., rebuilt-run-state schema-validation
  failure) as a contract violation; cross-state disagreement surfaces as
  the marker class on the unsalvageable-conflict path (the marker IS the
  loud-fail signal for that path per AC-7).
- **Pattern 6** Python code style — strict typing, frozen Pydantic models,
  caller-injected resolvers + writer so tests use ``tmp_path``-rooted
  fixtures without subprocess / file-system coupling.

## The three ``RecoveryOutcome.action`` branches

* ``recovery-clean`` — the two stores agree; no rebuild needed; silent
  success.
* ``recovery-rebuilt`` — the two stores disagreed on a recoverable
  dimension (lifecycle-state mismatch, active-markers divergence, specialist-
  dispatched-no-return, OR sprint-status mismatch as a NAMED-DIAGNOSTIC
  cross-check); the algorithm rebuilds run-state from the story-doc per
  ADR-005 Reading 3. Silent-with-rebuild (no marker emitted) per
  ``architecture.md:498`` ("auto-rebuild + marker is the doctrine-aligned
  default... drift is *expected* in recovery").
* ``recovery-conflict-halt`` — the disagreement is structurally
  unsalvageable (story-doc corrupt / missing, retry-history irreconcilable
  with story-doc-implied-state, OR no run-state on disk at all);
  ``recovery-state-conflict`` marker emitted exactly once with a
  named-invariant diagnostic enumerating each detected disagreement.

## Two-store reconciliation, third-store cross-check-only

Per epic AC verbatim (``epics.md:3249-3250``), the reconciliation is
``run-state`` + ``story-doc``. Sprint-status disagreement is NAMED-DIAGNOSTIC
only — surfaced inside the ``recovery-state-conflict`` marker text on the
halt path AND inside ``RecoveryOutcome.disagreements`` on the rebuild path
— but is NEVER REWRITTEN by THIS substrate. The actual rewrite is Story
8.3's territory if it lands at all in MVP, or Phase 1.5 territory.

## Best-effort vs lossless recovery

Per epic AC verbatim (``epics.md:3253-3257``), the recoverable-vs-ephemeral
boundary is observable:

* **Recoverable markers**: those persisted to the story-doc body via the
  Story 3.2 ``[Review][Patch]`` / ``[Review][Defer]`` Review-Findings
  taxonomy, the Story 4.x ``tier-3-not-configured`` QA-evidence row, and
  the forward-compat ``<!-- marker: <class> -->`` HTML comment surface.
  Restored to ``rebuilt_run_state.active_markers``.
* **Ephemeral markers**: those that fired transiently and are not
  persisted to story-doc (``specialist-timeout``, ``hook-failed``,
  ``context-near-limit``, ``cost-near-ceiling``, ``evidence-truncated``,
  ``playwright-mcp-unavailable``). NOT fabricated. Surfaced via
  ``RecoveryOutcome.unrestored_ephemeral_markers`` so the lossy boundary
  is observable.

## No state-advancing actions outside run-state

The substrate writes ONLY to run-state (via :func:`run_state.advance_run_state`
on the rebuild path with the no-op story-doc callback). It does NOT modify
the story-doc, does NOT modify sprint-status, does NOT touch git working
tree state, does NOT emit orchestrator-events to the JSONL log. Story 8.6's
``can_dispatch`` substrate guard supersedes this commitment with structural
enforcement.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final, Literal

import yaml as _pyyaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from referencing import Registry
from referencing.jsonschema import DRAFT202012

from ._shared import find_repo_root, load_schema
from .marker_wiring import (
    compute_alphabetical_marker_order,
    record_marker_with_context,
)
from .orchestrator_run_entry import (
    SprintStatusMismatch,
    StoryDocMalformed,
    StoryDocNotFound,
    StoryDocResolution,
    SprintStatusResolver,
    StoryDocResolver,
    default_sprint_status_resolver,
    default_story_doc_resolver,
)
from .review_layer_failure import REVIEW_LAYER_FAILED_MARKER
from .run_state import (
    CostToDateBySpecialist,
    CurrentState,
    RunState,
    StoryDocCallbackResult,
    advance_run_state,
)
from .story_doc_validator import ALLOWED_SECTIONS

if TYPE_CHECKING:
    from .specialist_dispatch import MarkerClassRegistry

__all__ = [
    "RECOVERY_STATE_CONFLICT_MARKER_CLASS",
    "RUN_STATE_RELATIVE_PATH",
    "CrossStateRecoveryError",
    "RecoveryOutcome",
    "RecoveryRequest",
    "RunStateWriter",
    "derive_state_from_story_doc",
    "evaluate_recovery",
    "extract_persisted_markers",
    "main",
    "render_recovery_state_conflict_diagnostic",
]

_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Module-level constants                                                       #
# --------------------------------------------------------------------------- #


#: Story 1.4 v1 marker class consumed AS-IS on the unsalvageable-conflict
#: branch. NO new marker classes introduced. Sourced from
#: ``schemas/marker-taxonomy.yaml`` lines 372-380. Carried as a per-substrate
#: literal (parallel to :data:`session_start_reattach.RECOVERY_STATE_CONFLICT_MARKER_CLASS`)
#: per the per-substrate-string-literal convention from Story 8.1 — each
#: substrate that emits the marker carries its own constant rather than
#: reaching into a sibling's namespace.
RECOVERY_STATE_CONFLICT_MARKER_CLASS: Final[
    Literal["recovery-state-conflict"]
] = "recovery-state-conflict"

#: User-installation runtime path for run-state per architecture.md View 3
#: line 1171. Mirror of :data:`session_start_reattach.RUN_STATE_RELATIVE_PATH`.
RUN_STATE_RELATIVE_PATH: Final[str] = "_bmad/automation/run-state.yaml"

#: Closed enumeration of the seven named disagreement classes per AC-3.
#: ``no-run-state-on-disk`` is structurally distinct (no ``prior_run_state``
#: to compare against) and surfaces only on the no-run-state path.
_DISAGREEMENT_CLASSES: Final[frozenset[str]] = frozenset({
    "lifecycle-state-mismatch",
    "active-markers-divergence",
    "specialist-dispatched-no-return",
    "sprint-status-disagrees-with-story-doc",
    "retry-history-irreconcilable",
    "story-doc-corrupt-or-missing",
    "no-run-state-on-disk",
})

#: Disagreement classes that the algorithm can auto-rebuild from. The
#: complement (``story-doc-corrupt-or-missing``, ``retry-history-irreconcilable``,
#: ``no-run-state-on-disk``) are unsalvageable per AC-6.
_RECONCILABLE_DISAGREEMENTS: Final[frozenset[str]] = frozenset({
    "lifecycle-state-mismatch",
    "active-markers-divergence",
    "specialist-dispatched-no-return",
    "sprint-status-disagrees-with-story-doc",
})

#: Marker classes restorable from story-doc artifacts per AC-5. Subset of
#: the v1 27-class taxonomy in ``schemas/marker-taxonomy.yaml``. Each class
#: produces a story-doc body artifact (Review-Findings taxonomy, QA-evidence
#: row, OR HTML-comment surface) so post-recovery presence is observable.
#:
#: 1:1 mapping to taxonomy entries (kebab-case marker class strings):
#:   * ``review-layer-failed`` — Review-BMAD ``[Review][Defer]`` taxonomy
#:     entry in the ``## Senior Developer Review (AI)`` section (Story 3.2).
#:   * ``decision-needed-finding`` — Review-BMAD finding taxonomy entry
#:     surfaced in the ``## Review Findings`` section.
#:   * ``tier-3-not-configured`` — QA Behavioral Plan evidence-row marker
#:     (Story 4.8) in the ``## QA Behavioral Plan`` section.
#:   * ``dangling-evidence-ref`` — Story 6.6 evidence-trace-linkability
#:     marker; persisted via the HTML-comment surface OR review section.
#:   * ``masked-selectors`` — Story 4.12 absence-of-marker doctrine
#:     reference; persisted via HTML-comment when surfaced.
#:   * ``undocumented-section-write`` — Story 1.10b section-allowlist
#:     rejection; recorded in story-doc body via HTML-comment surface.
_RECOVERABLE_MARKER_CLASSES: Final[frozenset[str]] = frozenset({
    REVIEW_LAYER_FAILED_MARKER,
    "decision-needed-finding",
    "tier-3-not-configured",
    "dangling-evidence-ref",
    "masked-selectors",
    "undocumented-section-write",
})

#: Marker classes that fire transiently and are not persisted to story-doc
#: per AC-5. Recovery does NOT fabricate these; the
#: :attr:`RecoveryOutcome.unrestored_ephemeral_markers` field surfaces the
#: lossy boundary.
_EPHEMERAL_MARKER_CLASSES: Final[frozenset[str]] = frozenset({
    "specialist-timeout",
    "hook-failed",
    "context-near-limit",
    "cost-near-ceiling",
    "evidence-truncated",
    "playwright-mcp-unavailable",
})

#: AC-5 invariant: the recoverable + ephemeral sets are disjoint.
assert (_RECOVERABLE_MARKER_CLASSES & _EPHEMERAL_MARKER_CLASSES) == frozenset(), (
    "Recoverable and ephemeral marker class sets must be disjoint per AC-5"
)


# --------------------------------------------------------------------------- #
# Section-presence-to-state oracle data                                        #
# --------------------------------------------------------------------------- #


#: The four story-doc sections that participate in the lifecycle-state
#: oracle per AC-4. Subset of ``story_doc_validator.ALLOWED_SECTIONS``;
#: ``## Review Findings`` and ``## Review Follow-ups (AI)`` are excluded
#: from the oracle (Review Findings is co-emitted with Senior Developer
#: Review; Review Follow-ups is post-``done``).
_SECTION_DEV_AGENT_RECORD: Final[str] = "## Dev Agent Record"
_SECTION_SENIOR_DEVELOPER_REVIEW: Final[str] = "## Senior Developer Review (AI)"
_SECTION_REVIEW_FINDINGS: Final[str] = "## Review Findings"
_SECTION_QA_BEHAVIORAL_PLAN: Final[str] = "## QA Behavioral Plan"
_SECTION_REVIEW_FOLLOW_UPS: Final[str] = "## Review Follow-ups (AI)"

#: Status-line parser per Story 2.5's ``_STATUS_LINE_RE`` pattern.
_STATUS_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^Status:\s*(?P<state>\S.*?)\s*$", re.MULTILINE
)

#: Fenced-code-block stripper so ``Status:`` inside an example block does
#: not leak into the oracle. Mirrors
#: ``orchestrator_run_entry._FENCED_CODE_BLOCK_RE``.
_FENCED_CODE_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"```.*?```|~~~.*?~~~", re.DOTALL
)

#: HTML-comment marker surface per AC-5. Captures the marker class name
#: between ``<!-- marker: `` and ``-->`` (with the optional
#: ``<!-- /marker -->`` closer ignored — the open tag carries the class).
_HTML_MARKER_COMMENT_RE: Final[re.Pattern[str]] = re.compile(
    r"<!--\s*marker:\s*(?P<class>[a-z][a-z0-9-]*)\s*-->"
)

#: Review-Findings taxonomy regex per Story 3.2 — ``[Review][Patch]
#: <marker-class>: ...`` or ``[Review][Defer] <marker-class>: ...``.
_REVIEW_TAXONOMY_RE: Final[re.Pattern[str]] = re.compile(
    r"\[Review\]\[(?:Patch|Defer)\]\s+(?P<class>[a-z][a-z0-9-]*)\s*:"
)

#: QA Behavioral Plan tier-3 evidence row regex. Matches the canonical
#: phrasing surfaced by Story 4.8's tier-3-not-configured marker.
_TIER_3_NOT_CONFIGURED_RE: Final[re.Pattern[str]] = re.compile(
    r"tier-3\s+evidence\s+not\s+configured", re.IGNORECASE
)


# --------------------------------------------------------------------------- #
# Error class — Pattern 5 named-invariant loud-fail.                           #
# --------------------------------------------------------------------------- #


class CrossStateRecoveryError(Exception):
    """Raised on substrate-level failures inside the cross-state recovery.

    Pattern 5 — loud-fail / named invariants. Analogous in shape to
    :class:`session_start_reattach.SessionStartReattachError` and
    :class:`init_non_destructive_guard.GuardConfigCorrupted`.

    RESERVED for substrate-level errors (rebuilt RunState fails defensive
    schema validation, story-doc resolver raises an unexpected exception
    NOT in the documented set, MarkerClassRegistry construction failure).
    Cross-state disagreement does NOT raise this — disagreement surfaces
    as the ``recovery-state-conflict`` marker class via
    :func:`evaluate_recovery` on the unsalvageable-conflict path (the
    marker IS the loud-fail signal per AC-7).

    Attributes:
        reason: Short kebab-case discriminator naming the concrete failure.
            Documented values: ``"rebuilt-run-state-fails-schema-validation"``,
            ``"story-doc-resolver-unexpected-exception"``,
            ``"taxonomy-load-failure"``, ``"schema-load-failure"``.
        diagnostic: Human-readable diagnostic naming the failure mode and
            a remediation hint per NFR-O5.
        path: The on-disk path the substrate was working with at the time
            of failure, when applicable.
    """

    def __init__(
        self,
        *,
        reason: str,
        diagnostic: str,
        path: pathlib.Path | None = None,
    ) -> None:
        self.reason = reason
        self.diagnostic = diagnostic
        self.path = path
        message = f"CrossStateRecoveryError[{reason}]: {diagnostic}"
        if path is not None:
            message += f" (path={path!s})"
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Pattern-6 DI seam: run-state writer.                                         #
# --------------------------------------------------------------------------- #


#: Type alias for the run-state writer injected via :class:`RecoveryRequest`.
#: Production default closes over :func:`run_state.advance_run_state` with
#: the no-op story-doc callback at
#: :func:`orchestrator_run_entry._no_op_story_doc_callback`.
RunStateWriter = Callable[[pathlib.Path, RunState], None]


def _default_run_state_writer(
    run_state_path: pathlib.Path, next_state: RunState
) -> None:
    """Default :data:`RunStateWriter` — composes :func:`advance_run_state`.

    The story-doc callback is a no-op because rebuild does NOT mutate the
    story-doc — the story-doc is the source-of-truth, not a derivable
    cache. This mirrors :func:`orchestrator_run_entry._no_op_story_doc_callback`
    inline so the cross-state recovery substrate does not import the
    private helper.
    """

    def _no_op_story_doc_callback() -> StoryDocCallbackResult:
        return StoryDocCallbackResult(
            accepted=True,
            reason=(
                "cross-state-recovery rebuild — story-doc is the source-of-truth, "
                "no story-doc edit is performed during recovery"
            ),
        )

    advance_run_state(
        run_state_path=run_state_path,
        next_state=next_state,
        story_doc_callback=_no_op_story_doc_callback,
    )


# --------------------------------------------------------------------------- #
# Typed Pydantic models (Pattern 6 — explicit, frozen, named).                 #
# --------------------------------------------------------------------------- #


class RecoveryRequest(BaseModel):
    """Typed input to :func:`evaluate_recovery`.

    Pattern 6 — frozen so callers cannot mutate the request mid-evaluation.
    Mirrors :class:`session_start_reattach.ReattachRequest` and
    :class:`init_non_destructive_guard.GuardRequest` in shape.

    Attributes:
        project_root: The practitioner's BMAD project root. The substrate
            inspects ``<project_root>/_bmad/automation/run-state.yaml`` AND
            ``<project_root>/_bmad-output/implementation-artifacts/<story-id>*.md``.
            Required; ``is_absolute`` enforced at validation time.
        story_id: The BMAD story identifier the practitioner supplied at
            ``/bmad-automation resume <story-id>`` OR the run-state's
            ``story_id`` field when called from a Story 8.1 reattachment
            context. Required; ``min_length=1``.
        story_doc_resolver: Pattern-6 dependency-injection seam for tests.
            Production runs default to
            :func:`orchestrator_run_entry.default_story_doc_resolver` per
            the Story 2.5 precedent.
        sprint_status_resolver: Pattern-6 DI seam. Production default =
            :func:`orchestrator_run_entry.default_sprint_status_resolver`.
            Consumed for the cross-store named-diagnostic surfacing per
            AC-7 — sprint-status-disagreement is named in the diagnostic
            but is NEVER rewritten.
        run_state_writer: Pattern-6 DI seam for the rebuild path's
            on-disk write. Production default = a closure over
            :func:`run_state.advance_run_state` with a no-op story-doc
            callback. Tests inject stubs to assert substrate behavior
            without exercising the canonical writer.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    project_root: pathlib.Path = Field(
        ...,
        description=(
            "Absolute path to the practitioner's project root. Read for "
            "the run-state file and the story-doc resolver."
        ),
    )
    story_id: str = Field(
        ...,
        min_length=1,
        description=(
            "BMAD story identifier; sourced from /bmad-automation resume "
            "<story-id> OR the run-state's story_id field."
        ),
    )
    story_doc_resolver: StoryDocResolver | None = Field(
        default=None,
        description=(
            "Optional StoryDocResolver injection for tests. None → "
            "default_story_doc_resolver at evaluate-recovery time."
        ),
    )
    sprint_status_resolver: SprintStatusResolver | None = Field(
        default=None,
        description=(
            "Optional SprintStatusResolver injection for tests. None → "
            "default_sprint_status_resolver at evaluate-recovery time."
        ),
    )
    run_state_writer: RunStateWriter | None = Field(
        default=None,
        description=(
            "Optional RunStateWriter injection for tests. None → "
            "_default_run_state_writer at evaluate-recovery time."
        ),
    )
    run_state_path: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional explicit path to the run-state file. None → "
            "project_root / RUN_STATE_RELATIVE_PATH. CLI sets this when "
            "--run-state-path is provided so the write target matches the "
            "read source."
        ),
    )

    @field_validator("project_root")
    @classmethod
    def _project_root_must_be_absolute(cls, v: pathlib.Path) -> pathlib.Path:
        if not v.is_absolute():
            raise ValueError(
                f"project_root must be an absolute path; got {v!r}. "
                "Pass pathlib.Path.cwd() or a CLI-resolved absolute path."
            )
        return v


_RecoveryAction = Literal[
    "recovery-clean",
    "recovery-rebuilt",
    "recovery-conflict-halt",
]


class RecoveryOutcome(BaseModel):
    """Typed return of :func:`evaluate_recovery`.

    Pattern 6 — frozen so the orchestrator skill cannot mutate the
    outcome between read and route.

    Attributes:
        action: One of the three canonical actions per AC-1.
        disagreements: Tuple of named-invariant strings naming each
            detected disagreement per AC-3. Empty on ``recovery-clean``;
            populated in deterministic detection order otherwise.
        prior_run_state: The input ``RunState`` (frozen-tuple-typed);
            preserved verbatim for diagnostic comparison. ``None`` only
            when the recovery was invoked against a story-id with no
            run-state on disk.
        rebuilt_run_state: The rebuilt-from-story-doc ``RunState`` on
            ``recovery-rebuilt``; same as ``prior_run_state`` on
            ``recovery-clean``; ``None`` on ``recovery-conflict-halt``.
        restored_markers: Subset of markers extracted from story-doc
            that were restored to ``rebuilt_run_state.active_markers``;
            empty on ``recovery-clean`` and ``recovery-conflict-halt``.
        unrestored_ephemeral_markers: Subset of
            ``prior_run_state.active_markers`` not restored because they
            are ephemeral; always empty on ``recovery-clean``; populated
            on ``recovery-rebuilt`` to make the best-effort lossy boundary
            observable per the loud-fail doctrine.
        marker_class: Set to ``"recovery-state-conflict"`` when
            ``action == "recovery-conflict-halt"``; ``None`` otherwise.
        diagnostic: Rendered marker diagnostic per AC-7; ``None`` on the
            silent (recovery-clean) and rebuild-only (recovery-rebuilt)
            branches.
        story_doc_implied_state: Lifecycle state derived from story-doc
            section presence per AC-4's section-to-state oracle;
            populated on all branches except
            ``recovery-conflict-halt: story-doc-corrupt-or-missing``.
        sprint_status_observed: Sprint-status entry's ``current_state``
            when the resolver returned successfully; ``None`` when the
            resolver raised OR was not invoked. Surfaced for diagnostic
            rendering only — sprint-status is NEVER rewritten by THIS
            substrate per AC-1.
    """

    model_config = ConfigDict(frozen=True)

    action: _RecoveryAction
    disagreements: tuple[str, ...] = ()
    prior_run_state: RunState | None = None
    rebuilt_run_state: RunState | None = None
    restored_markers: tuple[str, ...] = ()
    unrestored_ephemeral_markers: tuple[str, ...] = ()
    marker_class: Literal["recovery-state-conflict"] | None = None
    diagnostic: str | None = None
    story_doc_implied_state: CurrentState | None = None
    sprint_status_observed: str | None = None


# --------------------------------------------------------------------------- #
# Pure section-presence-to-state oracle (AC-4).                                #
# --------------------------------------------------------------------------- #


def _strip_fenced_code(text: str) -> str:
    """Strip fenced code blocks from ``text`` so heading-shaped strings
    inside code examples are not misread as actual sections."""
    return _FENCED_CODE_BLOCK_RE.sub("", text)


def _extract_status_line(story_doc_text: str) -> str | None:
    """Best-effort extract of the ``Status:`` line value from a story-doc.

    Returns the raw state string when located, ``None`` otherwise.
    """
    cleaned = _strip_fenced_code(story_doc_text)
    match = _STATUS_LINE_RE.search(cleaned)
    if match is None:
        return None
    return match.group("state").strip()


def _find_sections(story_doc_text: str) -> frozenset[str]:
    """Return the frozenset of allowed-section heading literals present in
    the doc text.

    Conservative match: each section's heading must appear at the start
    of a line (per markdown's heading discipline). Sections inside fenced
    code blocks are excluded.
    """
    cleaned = _strip_fenced_code(story_doc_text)
    found: set[str] = set()
    for section in ALLOWED_SECTIONS:
        # Heading appears at start-of-line. Use a re.escape-anchored search
        # to avoid substring matches like ``# ## Dev Agent Record``.
        pattern = re.compile(
            r"^" + re.escape(section) + r"\s*$", re.MULTILINE
        )
        if pattern.search(cleaned):
            found.add(section)
    return frozenset(found)


def derive_state_from_story_doc(
    story_doc_resolution: StoryDocResolution,
    story_doc_text: str,
) -> tuple[CurrentState, frozenset[str]]:
    """Pure section-presence-to-state oracle per AC-4.

    Returns ``(implied_state, sections_present)`` where ``implied_state``
    is the highest-implied-state per the AC-4 mapping and
    ``sections_present`` is the set of allow-listed section heading
    literals actually found in the doc text.

    AC-4 mapping table:

    +-------------------------------------------------+------------------+
    | Sections present                                | Implied state    |
    +=================================================+==================+
    | ∅                                               | ``ready-for-dev``|
    +-------------------------------------------------+------------------+
    | ``## Dev Agent Record`` only                    | ``in-progress``  |
    +-------------------------------------------------+------------------+
    | + ``## Senior Developer Review (AI)``           | ``review``       |
    +-------------------------------------------------+------------------+
    | + ``## QA Behavioral Plan``                     | ``qa``           |
    +-------------------------------------------------+------------------+

    Status-line tiebreak: when the doc's ``Status:`` value is one of the
    terminal states (``done``, ``escalated``) AND the section presence
    supports that terminal (``qa`` or higher), the terminal wins. When
    the Status line and section-presence disagree on a non-terminal
    (e.g., ``Status: in-progress`` but ``## Senior Developer Review (AI)``
    present), the section presence wins per the ADR-005 durability
    rationale.

    Invalid section dependencies (Senior Developer Review present without
    Dev Agent Record; QA Behavioral Plan without Senior Developer Review)
    surface as story-doc-corrupt: the oracle raises a ``ValueError`` so
    the caller can map the failure to the
    ``story-doc-corrupt-or-missing`` named invariant.

    Pure function: no side effects, no marker emission, deterministic on
    identical inputs.
    """
    sections_present = _find_sections(story_doc_text)

    has_dev = _SECTION_DEV_AGENT_RECORD in sections_present
    has_review = _SECTION_SENIOR_DEVELOPER_REVIEW in sections_present
    has_qa = _SECTION_QA_BEHAVIORAL_PLAN in sections_present

    # Section dependency violations per AC-4 (rows 5+6 of the mapping):
    # Senior Developer Review present without Dev Agent Record → corrupt.
    # QA Behavioral Plan present without Senior Developer Review → corrupt.
    if has_review and not has_dev:
        raise ValueError(
            "story-doc section dependency violation: "
            f"{_SECTION_SENIOR_DEVELOPER_REVIEW!r} is present without "
            f"{_SECTION_DEV_AGENT_RECORD!r}; the lifecycle DAG forbids "
            "Review-BMAD running before Dev"
        )
    if has_qa and not has_review:
        raise ValueError(
            "story-doc section dependency violation: "
            f"{_SECTION_QA_BEHAVIORAL_PLAN!r} is present without "
            f"{_SECTION_SENIOR_DEVELOPER_REVIEW!r}; the lifecycle DAG forbids "
            "QA running before Review-BMAD"
        )

    if has_qa:
        section_implied: CurrentState = "qa"
    elif has_review:
        section_implied = "review"
    elif has_dev:
        section_implied = "in-progress"
    else:
        section_implied = "ready-for-dev"

    # Status-line tiebreak: terminal states (``done``, ``escalated``) win
    # only when the section presence supports them (qa or higher).
    status_line = _extract_status_line(story_doc_text)
    if status_line in ("done", "escalated"):
        # A terminal Status line on a doc whose section presence is below
        # ``qa`` (e.g., ``Status: done`` but no QA section) is a
        # structural-impossibility we surface upstream as
        # ``retry-history-irreconcilable``; here the oracle returns the
        # Status value verbatim so the caller can detect the mismatch.
        if has_qa:
            return (status_line, sections_present)  # type: ignore[return-value]
        # Inconsistent terminal Status without supporting sections —
        # treat as story-doc-corrupt rather than silently downgrading.
        raise ValueError(
            f"story-doc Status line {status_line!r} contradicts section "
            f"presence (sections={sorted(sections_present)!r}); a terminal "
            "Status requires QA Behavioral Plan section presence"
        )

    return (section_implied, sections_present)


# --------------------------------------------------------------------------- #
# Pure marker extraction (AC-5).                                               #
# --------------------------------------------------------------------------- #


def extract_persisted_markers(
    story_doc_text: str,
    sections_present: frozenset[str],
) -> frozenset[str]:
    """Pure extraction returning marker classes recoverable from story-doc.

    Conservative per AC-5: extracts from
        * ``## Senior Developer Review (AI)``'s ``[Review][Patch]`` /
          ``[Review][Defer]`` taxonomy entries (Story 3.2).
        * ``## QA Behavioral Plan``'s ``tier-3 evidence not configured``
          phrasing (Story 4.8).
        * any ``<!-- marker: <class> -->`` HTML comment in the doc body
          (forward-compat extraction surface).

    Markers appearing only in ``## Dev Agent Record`` debug-log
    references are NOT extracted (debug output, not persisted-state).

    Pure function — no I/O.
    """
    extracted: set[str] = set()

    # HTML-comment surface: strip fenced code first so markers inside code
    # examples are not falsely extracted (matches the section-scoped paths
    # which go through _slice_section_body → _strip_fenced_code).
    html_safe_text = _strip_fenced_code(story_doc_text)
    for match in _HTML_MARKER_COMMENT_RE.finditer(html_safe_text):
        klass = match.group("class")
        if klass in _RECOVERABLE_MARKER_CLASSES:
            extracted.add(klass)

    # Section-scoped extractions.
    if _SECTION_SENIOR_DEVELOPER_REVIEW in sections_present:
        review_body = _slice_section_body(
            story_doc_text, _SECTION_SENIOR_DEVELOPER_REVIEW
        )
        for match in _REVIEW_TAXONOMY_RE.finditer(review_body):
            klass = match.group("class")
            if klass in _RECOVERABLE_MARKER_CLASSES:
                extracted.add(klass)

    if _SECTION_QA_BEHAVIORAL_PLAN in sections_present:
        qa_body = _slice_section_body(
            story_doc_text, _SECTION_QA_BEHAVIORAL_PLAN
        )
        if _TIER_3_NOT_CONFIGURED_RE.search(qa_body):
            extracted.add("tier-3-not-configured")

    return frozenset(extracted)


def _slice_section_body(story_doc_text: str, section_heading: str) -> str:
    """Slice the body of ``section_heading`` from the doc text.

    Returns the body between the heading line and the next ``## ``-prefixed
    heading (or EOF). Empty string if the heading is not present.
    """
    cleaned = _strip_fenced_code(story_doc_text)
    pattern = re.compile(r"^" + re.escape(section_heading) + r"\s*$", re.MULTILINE)
    match = pattern.search(cleaned)
    if match is None:
        return ""
    start = match.end()
    rest = cleaned[start:]
    next_section_match = re.search(r"^## ", rest, re.MULTILINE)
    if next_section_match is None:
        return rest
    return rest[: next_section_match.start()]


# --------------------------------------------------------------------------- #
# Diagnostic renderer (AC-7).                                                  #
# --------------------------------------------------------------------------- #


def render_recovery_state_conflict_diagnostic(
    outcome: RecoveryOutcome,
    project_root: pathlib.Path | None = None,
) -> str:
    """Pure deterministic formatter producing the AC-7 diagnostic text.

    Composition (six clauses per AC-7):

    1. ``recovery-state-conflict: `` literal prefix.
    2. ``disagreements: <comma-separated-named-invariants>`` clause.
    3. ``prior run-state: ...`` clause when ``prior_run_state`` is non-None.
    4. ``story-doc-implied state: <v>`` clause when the oracle ran.
    5. ``sprint-status entry: <v>`` clause when the resolver ran.
    6. ``remediation:`` clause naming the two paths from
       ``epics.md:3261-3262`` verbatim.
    7. Pointer-to-marker-taxonomy clause:
       ``see schemas/marker-taxonomy.yaml:372-380 for marker class definition``.

    Mirrors :func:`session_start_reattach.render_recovery_state_conflict_diagnostic`
    in shape; the literal prefix is identical for orchestrator-skill
    parseability per Pattern 5's machine-parseable-diagnostic discipline,
    but the body differs (8.1: schema-mismatch fields; 8.2: cross-state
    disagreement enumeration).
    """
    disagreements = (
        ", ".join(outcome.disagreements)
        if outcome.disagreements
        else "<none>"
    )
    parts: list[str] = [
        f"recovery-state-conflict: disagreements: {disagreements}",
    ]

    if project_root is not None:
        parts.append(f"project-root: {project_root!s}")

    if outcome.prior_run_state is not None:
        latest_retry = (
            outcome.prior_run_state.retry_history[-1]
            if outcome.prior_run_state.retry_history
            else None
        )
        latest_retry_str = (
            f"{latest_retry.retry_attempt}: {latest_retry.retry_reason}"
            if latest_retry is not None
            else "<none>"
        )
        parts.append(
            f"prior run-state: current_state="
            f"{outcome.prior_run_state.current_state}, "
            f"dispatched_specialist={outcome.prior_run_state.dispatched_specialist}, "
            f"latest retry_history entry={latest_retry_str}"
        )

    if outcome.story_doc_implied_state is not None:
        parts.append(
            f"story-doc-implied state: {outcome.story_doc_implied_state}"
        )

    if outcome.sprint_status_observed is not None:
        parts.append(
            f"sprint-status entry: {outcome.sprint_status_observed}"
        )

    parts.append(
        "remediation: "
        "(a) human triage of which state representation reflects reality, "
        "then explicit reconciliation by editing the story-doc OR deleting "
        "the run-state file and re-running /bmad-automation run <story-id>, "
        "(b) preserve all stores for forensic inspection — do NOT auto-purge"
    )
    parts.append(
        "see schemas/marker-taxonomy.yaml:372-380 for marker class definition"
    )

    return "; ".join(parts)


# --------------------------------------------------------------------------- #
# Internal helpers for the rebuild path.                                       #
# --------------------------------------------------------------------------- #


def _classify_active_markers(
    active_markers: tuple[str, ...],
) -> tuple[frozenset[str], frozenset[str]]:
    """Partition ``active_markers`` into (recoverable-base-classes, ephemeral-base-classes).

    Strips Pattern-2 ``: <sub_classification>`` suffixes for the
    membership check (the recoverable / ephemeral sets enumerate base
    marker classes only).
    """
    recoverable: set[str] = set()
    ephemeral: set[str] = set()
    for marker in active_markers:
        base = marker.split(":", 1)[0].strip() if ":" in marker else marker
        if base in _RECOVERABLE_MARKER_CLASSES:
            recoverable.add(marker)
        elif base in _EPHEMERAL_MARKER_CLASSES:
            ephemeral.add(marker)
    return frozenset(recoverable), frozenset(ephemeral)


def _retry_history_irreconcilable(
    prior: RunState, story_doc_implied_state: CurrentState
) -> bool:
    """Return True when the run-state's ``retry_history`` records a
    transition the story-doc-implied-state cannot follow.

    The check is conservative: we look at the latest retry's
    ``retry_reason`` for terminal-state markers (``escalated``, ``done``)
    and compare against ``story_doc_implied_state``. The only structurally
    impossible combination at MVP is ``Status: done`` (oracle returns
    ``done``) when the latest retry recorded escalation (a non-recoverable
    terminal that the lifecycle DAG cannot exit).
    """
    if not prior.retry_history:
        return False
    # Indicators of escalation in retry_history: the substrate's
    # consumers (Story 5.6) record ``retry_reason`` text that names the
    # escalation cause. We detect the structurally-impossible
    # done-after-escalated combination via the run-state's
    # ``current_state`` being ``escalated`` (the lifecycle DAG's terminal
    # for retry-budget-exhaustion) AND the story-doc-implied-state being
    # ``done`` — the lifecycle DAG forbids ``escalated → done``.
    if (
        prior.current_state == "escalated"
        and story_doc_implied_state == "done"
    ):
        return True
    # The inverse — Status: done in run-state, story-doc shows escalated —
    # is also irreconcilable (escalation cannot follow done; done is a
    # natural leaf per LIFECYCLE_TRANSITIONS).
    if (
        prior.current_state == "done"
        and story_doc_implied_state == "escalated"
    ):
        return True
    return False


def _validate_rebuilt_against_schema(
    rebuilt: RunState, project_root: pathlib.Path
) -> None:
    """Defensive AC-6 schema validation of a rebuilt RunState.

    ADR-005 Consequence 1 verbatim: post-recovery state shape is a schema
    commitment. Failure is a programmer-error sanity check (Pydantic's
    ``model_validate`` already accepted the instance); raises
    :class:`CrossStateRecoveryError` per Pattern 5 loud-fail discipline.
    """
    try:
        schemas_dir = find_repo_root() / "schemas"
        run_state_schema = load_schema(schemas_dir / "run-state.yaml")
    except (RuntimeError, OSError) as exc:
        raise CrossStateRecoveryError(
            reason="schema-load-failure",
            diagnostic=(
                f"failed to load run-state schema: {exc!s}; "
                "harness-level error — verify the harness installation."
            ),
        ) from exc

    registry: Registry = Registry()
    for sibling_name in ("envelope.schema.yaml", "tea-handoff-contract.yaml"):
        sibling_path = schemas_dir / sibling_name
        if sibling_path.is_file():
            sibling_schema = load_schema(sibling_path)
            registry = registry.with_resource(
                uri=sibling_name,
                resource=DRAFT202012.create_resource(sibling_schema),
            )
    validator = Draft202012Validator(run_state_schema, registry=registry)
    payload = _coerce_to_jsonschema_payload(rebuilt)
    errors = list(validator.iter_errors(payload))
    if errors:
        paths = []
        for err in errors:
            if err.absolute_path:
                paths.append("/" + "/".join(str(p) for p in err.absolute_path))
            else:
                paths.append("<root>")
        raise CrossStateRecoveryError(
            reason="rebuilt-run-state-fails-schema-validation",
            diagnostic=(
                f"rebuilt RunState failed JSON-Schema validation against "
                f"schemas/run-state.yaml: {sorted(set(paths))!r}; "
                "this indicates a defect in the recovery substrate"
            ),
            path=project_root,
        )


def _coerce_to_jsonschema_payload(state: RunState) -> dict[str, Any]:
    """Render a :class:`RunState` to a JSON-compatible dict for schema validation."""
    import json

    return json.loads(state.model_dump_json(by_alias=False, exclude_none=False))


# --------------------------------------------------------------------------- #
# Composite entry point.                                                       #
# --------------------------------------------------------------------------- #


def evaluate_recovery(
    request: RecoveryRequest,
    *,
    run_state: RunState | None,
    marker_registry: "MarkerClassRegistry | None" = None,
) -> tuple[RecoveryOutcome, RunState | None]:
    """Composite cross-state-consistency-recovery decision.

    No state-advancing actions outside run-state: this substrate is
    read-only against story-doc, sprint-status, and the git working tree.
    The substrate's only writes go to run-state via
    :func:`run_state.advance_run_state` on the rebuild path.

    The three branches per AC-1:

    1. Stores agree → ``recovery-clean``. Silent.
    2. Stores disagree on a recoverable dimension → ``recovery-rebuilt``.
       Run-state rebuilt from story-doc per ADR-005 Reading 3; silent
       (no marker) per ``architecture.md:498``.
    3. Disagreement is unsalvageable → ``recovery-conflict-halt``.
       ``recovery-state-conflict`` marker emitted with named-invariant
       diagnostic.

    Args:
        request: The typed input.
        run_state: The on-disk run-state cache as a :class:`RunState`
            instance. ``None`` indicates no run-state file at the named
            project_root for the named story-id — surfaces as
            ``recovery-conflict-halt: no-run-state-on-disk`` per AC-2.
        marker_registry: Optional marker-class registry for AC-7's marker
            emission. ``None`` suppresses emission and the second
            tuple-element on the halt path equals ``run_state`` unchanged
            per the test-injection seam from Story 8.1's identical
            pattern.

    Returns:
        ``(RecoveryOutcome, RunState | None)``. The second element is
        ``run_state`` unchanged on ``recovery-clean``;
        ``outcome.rebuilt_run_state`` on ``recovery-rebuilt``;
        on ``recovery-conflict-halt`` with a non-None prior ``run_state``:
        ``record_marker_with_context(...)`` result (or ``run_state``
        unchanged when ``marker_registry`` is None);
        on ``recovery-conflict-halt`` with ``run_state is None``: a
        sentinel stub ``RunState`` carrying the conflict marker (when
        ``marker_registry`` is provided) or ``None`` (when not).
    """
    project_root = request.project_root
    story_id = request.story_id

    # AC-2 — no run-state path: surface as recovery-conflict-halt.
    if run_state is None:
        outcome = RecoveryOutcome(
            action="recovery-conflict-halt",
            disagreements=("no-run-state-on-disk",),
            prior_run_state=None,
            rebuilt_run_state=None,
            restored_markers=(),
            unrestored_ephemeral_markers=(),
            marker_class=RECOVERY_STATE_CONFLICT_MARKER_CLASS,
            diagnostic=None,
            story_doc_implied_state=None,
            sprint_status_observed=None,
        )
        diagnostic = render_recovery_state_conflict_diagnostic(outcome, project_root)
        outcome = outcome.model_copy(update={"diagnostic": diagnostic})
        if marker_registry is None:
            return (outcome, None)
        # AC-2 "marker emitted" requirement: no prior RunState exists, so a
        # sentinel stub is constructed solely to carry the conflict marker.
        # Caller uses outcome.action == "recovery-conflict-halt" to detect halt;
        # the stub's other fields are not trustworthy state.
        stub = RunState.model_construct(
            schema_version="1.3",
            story_id=request.story_id,
            run_id="sentinel-no-run-state",
            current_state="in-progress",
            branch_name="unknown",
            dispatched_specialist=None,
            last_envelope=None,
            pending_qa_dispatch_payload=None,
            retry_history=(),
            active_markers=(),
            cost_to_date_by_specialist=CostToDateBySpecialist(),
            marker_contexts={},
        )
        return (outcome, record_marker_with_context(
            run_state=stub,
            marker_class=RECOVERY_STATE_CONFLICT_MARKER_CLASS,
            sub_classification=None,
            context=None,
            marker_registry=marker_registry,
        ))

    # Resolve story-doc.
    story_doc_resolver = (
        request.story_doc_resolver
        if request.story_doc_resolver is not None
        else default_story_doc_resolver
    )
    story_doc_resolution: StoryDocResolution | None = None
    story_doc_text: str | None = None
    try:
        story_doc_resolution = story_doc_resolver(story_id, project_root)
        story_doc_text = story_doc_resolution.path.read_text(encoding="utf-8")
    except (StoryDocNotFound, StoryDocMalformed):
        # Unsalvageable: story-doc-corrupt-or-missing.
        return _build_unsalvageable_halt(
            run_state=run_state,
            disagreements=("story-doc-corrupt-or-missing",),
            story_doc_implied_state=None,
            sprint_status_observed=None,
            marker_registry=marker_registry,
            project_root=project_root,
        )
    except OSError as exc:
        return _build_unsalvageable_halt(
            run_state=run_state,
            disagreements=("story-doc-corrupt-or-missing",),
            story_doc_implied_state=None,
            sprint_status_observed=None,
            marker_registry=marker_registry,
            extra_diagnostic_hint=(
                f"story-doc read failed at {project_root!s}: {exc!s}"
            ),
            project_root=project_root,
        )
    except Exception as exc:
        # Resolver raised something outside the documented set; surface as
        # substrate-level loud-fail per Pattern 5.
        raise CrossStateRecoveryError(
            reason="story-doc-resolver-unexpected-exception",
            diagnostic=(
                f"story_doc_resolver raised {type(exc).__name__}({exc!s}); "
                "expected one of StoryDocNotFound | StoryDocMalformed | OSError"
            ),
        ) from exc

    # Resolve sprint-status (cross-check only).
    sprint_status_resolver = (
        request.sprint_status_resolver
        if request.sprint_status_resolver is not None
        else default_sprint_status_resolver
    )
    sprint_status_observed: str | None = None
    try:
        sprint_status_resolution = sprint_status_resolver(
            story_id, project_root
        )
        sprint_status_observed = sprint_status_resolution.current_state
    except (SprintStatusMismatch, OSError):
        # Sprint-status missing or malformed — cross-check is skipped, NOT
        # halted (sprint-status is the third store; only the two stores
        # reconcile per epic AC).
        sprint_status_observed = None

    # Section-presence-to-state oracle.
    try:
        story_doc_implied_state, sections_present = derive_state_from_story_doc(
            story_doc_resolution, story_doc_text
        )
    except ValueError:
        return _build_unsalvageable_halt(
            run_state=run_state,
            disagreements=("story-doc-corrupt-or-missing",),
            story_doc_implied_state=None,
            sprint_status_observed=sprint_status_observed,
            marker_registry=marker_registry,
            project_root=project_root,
        )

    # Detect disagreements (deterministic order matches AC-3 enumeration).
    disagreements: list[str] = []

    if run_state.current_state != story_doc_implied_state:
        disagreements.append("lifecycle-state-mismatch")

    extractable_markers = extract_persisted_markers(
        story_doc_text, sections_present
    )
    recoverable_in_run_state, ephemeral_in_run_state = _classify_active_markers(
        run_state.active_markers
    )
    # Active-markers divergence: the run-state's recoverable subset is NOT a
    # superset of the story-doc-extractable set (i.e., story-doc has markers
    # the run-state lacks). This is the structural definition of "story-doc
    # has more truth than run-state cache" per AC-3.
    run_state_recoverable_bases: set[str] = {
        marker.split(":", 1)[0].strip() if ":" in marker else marker
        for marker in recoverable_in_run_state
    }
    if not extractable_markers.issubset(run_state_recoverable_bases):
        disagreements.append("active-markers-divergence")

    if (
        run_state.dispatched_specialist is not None
        and run_state.last_envelope is None
    ):
        # The run-state shows a specialist was dispatched but no envelope
        # came back. Cross-check whether the story-doc has the
        # corresponding specialist's section.
        specialist_section_map = {
            "dev": _SECTION_DEV_AGENT_RECORD,
            "review-bmad": _SECTION_SENIOR_DEVELOPER_REVIEW,
            "qa": _SECTION_QA_BEHAVIORAL_PLAN,
        }
        expected_section = specialist_section_map.get(
            run_state.dispatched_specialist
        )
        if expected_section is not None and expected_section not in sections_present:
            disagreements.append("specialist-dispatched-no-return")

    if (
        sprint_status_observed is not None
        and sprint_status_observed != story_doc_implied_state
        # ``optional`` is the retrospective row; not a lifecycle state.
        and sprint_status_observed != "optional"
        # ``backlog`` and ``ready-for-dev`` are equivalent for a story
        # whose story-doc shows ready-for-dev.
        and not (
            sprint_status_observed in ("backlog", "ready-for-dev")
            and story_doc_implied_state == "ready-for-dev"
        )
    ):
        disagreements.append("sprint-status-disagrees-with-story-doc")

    if _retry_history_irreconcilable(run_state, story_doc_implied_state):
        disagreements.append("retry-history-irreconcilable")

    # AC-1: clean branch.
    if not disagreements:
        return (
            RecoveryOutcome(
                action="recovery-clean",
                disagreements=(),
                prior_run_state=run_state,
                rebuilt_run_state=run_state,
                restored_markers=(),
                unrestored_ephemeral_markers=(),
                marker_class=None,
                diagnostic=None,
                story_doc_implied_state=story_doc_implied_state,
                sprint_status_observed=sprint_status_observed,
            ),
            run_state,
        )

    # AC-6: unsalvageable disagreements halt.
    unsalvageable = {
        "story-doc-corrupt-or-missing",
        "retry-history-irreconcilable",
    }
    if any(d in unsalvageable for d in disagreements):
        return _build_unsalvageable_halt(
            run_state=run_state,
            disagreements=tuple(disagreements),
            story_doc_implied_state=story_doc_implied_state,
            sprint_status_observed=sprint_status_observed,
            marker_registry=marker_registry,
            project_root=project_root,
        )

    # AC-6: recoverable disagreements → rebuild from story-doc.
    rebuilt = _build_rebuilt_run_state(
        prior=run_state,
        story_doc_implied_state=story_doc_implied_state,
        extractable_markers=extractable_markers,
    )
    _validate_rebuilt_against_schema(rebuilt, project_root)

    restored_markers_set = (
        set(rebuilt.active_markers) - set(run_state.active_markers)
    )
    restored_markers = tuple(sorted(restored_markers_set))
    unrestored_ephemeral = tuple(sorted(ephemeral_in_run_state))

    # Optionally persist the rebuild to disk via the writer DI seam.
    writer = (
        request.run_state_writer
        if request.run_state_writer is not None
        else _default_run_state_writer
    )
    run_state_path = (
        request.run_state_path
        if request.run_state_path is not None
        else project_root / RUN_STATE_RELATIVE_PATH
    )
    if run_state_path.is_file():
        # Disk-write failure (OSError, RunStateAdvanceBlocked) propagates
        # to the caller per AC-6 — the substrate does NOT swallow disk-IO
        # failures into a marker.
        writer(run_state_path, rebuilt)

    outcome = RecoveryOutcome(
        action="recovery-rebuilt",
        disagreements=tuple(disagreements),
        prior_run_state=run_state,
        rebuilt_run_state=rebuilt,
        restored_markers=restored_markers,
        unrestored_ephemeral_markers=unrestored_ephemeral,
        marker_class=None,
        diagnostic=None,
        story_doc_implied_state=story_doc_implied_state,
        sprint_status_observed=sprint_status_observed,
    )
    return (outcome, rebuilt)


def _build_unsalvageable_halt(
    *,
    run_state: RunState | None,
    disagreements: tuple[str, ...],
    story_doc_implied_state: CurrentState | None,
    sprint_status_observed: str | None,
    marker_registry: "MarkerClassRegistry | None",
    extra_diagnostic_hint: str | None = None,
    project_root: pathlib.Path | None = None,
) -> tuple[RecoveryOutcome, RunState | None]:
    """Build the ``recovery-conflict-halt`` outcome and emit the marker."""
    outcome = RecoveryOutcome(
        action="recovery-conflict-halt",
        disagreements=disagreements,
        prior_run_state=run_state,
        rebuilt_run_state=None,
        restored_markers=(),
        unrestored_ephemeral_markers=(),
        marker_class=RECOVERY_STATE_CONFLICT_MARKER_CLASS,
        diagnostic=None,
        story_doc_implied_state=story_doc_implied_state,
        sprint_status_observed=sprint_status_observed,
    )
    diagnostic = render_recovery_state_conflict_diagnostic(outcome, project_root)
    if extra_diagnostic_hint:
        diagnostic = f"{diagnostic}; hint: {extra_diagnostic_hint}"
    outcome = outcome.model_copy(update={"diagnostic": diagnostic})

    if run_state is None or marker_registry is None:
        return (outcome, run_state)

    next_run_state = record_marker_with_context(
        run_state=run_state,
        marker_class=RECOVERY_STATE_CONFLICT_MARKER_CLASS,
        sub_classification=None,
        context=None,
        marker_registry=marker_registry,
    )
    return (outcome, next_run_state)


def _build_rebuilt_run_state(
    *,
    prior: RunState,
    story_doc_implied_state: CurrentState,
    extractable_markers: frozenset[str],
) -> RunState:
    """Build the rebuilt :class:`RunState` per AC-6.

    Story-doc wins on lifecycle state; orchestrator-domain fields
    (``run_id``, ``branch_name``, ``pending_qa_dispatch_payload``,
    ``cost_to_date_by_specialist``, ``last_retry_directive``) are
    preserved from the prior cache because the story-doc has no canonical
    record of them.

    Active markers are union(prior recoverable subset, extractable), then
    sorted alphabetically per :func:`marker_wiring.compute_alphabetical_marker_order`.
    Ephemeral markers from ``prior.active_markers`` are NOT carried
    forward (per AC-5's lossy boundary).
    """
    recoverable_in_prior, _ephemeral = _classify_active_markers(
        prior.active_markers
    )
    # Deduplicate: recoverable_in_prior carries full strings (e.g.,
    # "review-layer-failed: reason"); extractable_markers carries base
    # classes only. Add an extractable entry only when its base class is not
    # already covered by a full-string entry from prior, to avoid duplicates
    # in active_markers (compute_alphabetical_marker_order does not dedup).
    prior_base_classes: set[str] = {
        m.split(":", 1)[0].strip() if ":" in m else m
        for m in recoverable_in_prior
    }
    new_active_set: set[str] = set(recoverable_in_prior)
    for m in extractable_markers:
        if m not in prior_base_classes:
            new_active_set.add(m)
    new_active = compute_alphabetical_marker_order(tuple(new_active_set))

    # Drop marker_contexts entries whose key (base class) is no longer in
    # active_markers — orphan-context cleanup mirrors
    # marker_wiring._extend_marker_contexts's housekeeping.
    new_active_bases: set[str] = {
        marker.split(":", 1)[0].strip() if ":" in marker else marker
        for marker in new_active
    }
    new_marker_contexts: Mapping[str, Mapping[str, object]] = {
        klass: ctx
        for klass, ctx in prior.marker_contexts.items()
        if klass in new_active_bases
    }

    # Pydantic v2 model_copy(update=...) on a frozen model returns a new
    # immutable instance — satisfies AC-6's no-mutation intent. Resetting
    # dispatched_specialist and last_envelope prevents the rebuilt state from
    # re-triggering the specialist-dispatched-no-return disagreement on the
    # next evaluate_recovery call.
    return prior.model_copy(
        update={
            "current_state": story_doc_implied_state,
            "active_markers": new_active,
            "marker_contexts": new_marker_contexts,
            "dispatched_specialist": None,
            "last_envelope": None,
        }
    )


# --------------------------------------------------------------------------- #
# CLI entry point.                                                             #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cross-state-recovery",
        description=(
            "Cross-state consistency recovery algorithm (Story 8.2, "
            "NFR-R8 + ADR-005 Reading-3). Reads the run-state file at "
            "<project_root>/_bmad/automation/run-state.yaml and the "
            "story-doc at <project_root>/_bmad-output/implementation-"
            "artifacts/<story-id>*.md, reconciles disagreement per the "
            "section-presence-to-state oracle, and either silently "
            "advances (recovery-clean), silently rebuilds run-state from "
            "story-doc (recovery-rebuilt), or halts with the "
            "recovery-state-conflict marker (recovery-conflict-halt)."
        ),
    )
    parser.add_argument(
        "--project-root",
        type=pathlib.Path,
        required=True,
        help="Absolute path to the practitioner's project root.",
    )
    parser.add_argument(
        "--story-id",
        type=str,
        required=True,
        help=(
            "BMAD story identifier (e.g., '8-2'); matches the story-doc "
            "filename prefix under _bmad-output/implementation-artifacts/."
        ),
    )
    parser.add_argument(
        "--run-state-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Optional explicit path to the run-state file. Defaults to "
            "<project_root>/_bmad/automation/run-state.yaml."
        ),
    )
    return parser


def _load_run_state_from_disk(
    run_state_path: pathlib.Path,
) -> RunState | None:
    """Load a :class:`RunState` from disk; return ``None`` when absent.

    Raises :class:`CrossStateRecoveryError` on substrate-level issues
    (file unreadable, YAML parse failure, schema-validation failure).
    """
    if not run_state_path.is_file():
        return None
    try:
        text = run_state_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CrossStateRecoveryError(
            reason="run-state-unreadable",
            diagnostic=(
                f"failed to read run-state file at {run_state_path!s}: {exc!s}"
            ),
            path=run_state_path,
        ) from exc
    try:
        parsed = _pyyaml.safe_load(text)
    except _pyyaml.YAMLError as exc:
        raise CrossStateRecoveryError(
            reason="run-state-parse-failure",
            diagnostic=(
                f"YAML parse error in run-state at {run_state_path!s}: {exc!s}"
            ),
            path=run_state_path,
        ) from exc
    if not isinstance(parsed, dict):
        raise CrossStateRecoveryError(
            reason="run-state-parse-failure",
            diagnostic=(
                f"run-state at {run_state_path!s} did not parse as a YAML mapping"
            ),
            path=run_state_path,
        )
    try:
        return RunState.model_validate(parsed)
    except ValidationError as exc:
        raise CrossStateRecoveryError(
            reason="run-state-schema-validation-failure",
            diagnostic=(
                f"run-state at {run_state_path!s} fails Pydantic validation: "
                f"{exc!s}"
            ),
            path=run_state_path,
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point invoked by the Story 8.3 ``/bmad-automation resume``
    slash command's orchestrator-skill step.

    Exit codes per AC-1 / AC-10:
        * ``0`` — ``recovery-clean`` OR ``recovery-rebuilt`` (silent
          successes from a flow-control perspective).
        * ``1`` — ``recovery-conflict-halt`` (the marker IS the loud-fail
          signal AND the exit code makes the halt observable to the
          orchestrator skill's bash-level wait).
        * ``2`` — harness-level error inside the substrate per Pattern 5
          (Pydantic model construction failure, story-doc resolver raised
          an unexpected exception, etc.).

    The 0-vs-1 split for ``recovery-clean``/``rebuilt``-vs-``conflict-halt``
    diverges from Story 8.1's all-zero-on-marker convention because: in
    8.1's case the SessionStart hook MUST exit 0 (non-zero hook exit
    would trigger Story 6.7's ``hook-failed`` marker which is wrong); in
    8.2's case the substrate is invoked from the orchestrator skill (NOT
    a hook), so the exit code is the right signal channel for halt-vs-
    resume.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    project_root = args.project_root
    if not project_root.is_absolute():
        project_root = project_root.resolve()

    run_state_path = (
        args.run_state_path
        if args.run_state_path is not None
        else project_root / RUN_STATE_RELATIVE_PATH
    )

    try:
        request = RecoveryRequest(
            project_root=project_root,
            story_id=args.story_id,
            run_state_path=run_state_path,
        )
    except (ValueError, ValidationError) as exc:
        print(f"harness-level error: {exc}", file=sys.stderr)
        return 2

    try:
        run_state = _load_run_state_from_disk(run_state_path)
        outcome, _ = evaluate_recovery(
            request, run_state=run_state, marker_registry=None
        )
    except CrossStateRecoveryError as exc:
        print(f"cross-state-recovery: harness-level error: {exc}", file=sys.stderr)
        return 2

    if outcome.action == "recovery-clean":
        print(
            (
                f"cross-state-recovery: recovery-clean: stores agree; "
                f"current_state={outcome.story_doc_implied_state}"
            ),
            file=sys.stderr,
        )
        return 0

    if outcome.action == "recovery-rebuilt":
        print(
            (
                f"cross-state-recovery: recovery-rebuilt: stores disagreed; "
                f"run-state rebuilt from story-doc per ADR-005 Reading-3; "
                f"disagreements={list(outcome.disagreements)}; "
                f"story-doc-implied state={outcome.story_doc_implied_state}; "
                f"restored_markers={list(outcome.restored_markers)}; "
                f"unrestored_ephemeral_markers="
                f"{list(outcome.unrestored_ephemeral_markers)}"
            ),
            file=sys.stderr,
        )
        return 0

    # recovery-conflict-halt
    print(f"cross-state-recovery: {outcome.diagnostic}", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
