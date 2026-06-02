"""``/bmad-automation status`` (no-args) multi-story listing substrate — Story 8.5.

## Substrate-component identity

THIS module is a substrate **library** sibling of
:mod:`loud_fail_harness.status_command` (Story 8.4),
:mod:`loud_fail_harness.resume_command` (Story 8.3),
:mod:`loud_fail_harness.cross_state_recovery` (Story 8.2),
:mod:`loud_fail_harness.session_start_reattach` (Story 8.1),
:mod:`loud_fail_harness.init_non_destructive_guard` (Story 7.6),
:mod:`loud_fail_harness.tea_boundary_orientation` (Story 7.8), and
:mod:`loud_fail_harness.story_doc_version_check` (Story 7.7). It is **NOT a
sixth substrate component** beyond ADR-003 Consequence 1's enumerated five
(``envelope_validator``, ``event_validator``, ``reconciler``,
``enumeration_check``, ``fixture_coverage``); the count remains FIVE through
Epic 8 per Story 8.4's Completion Notes verbatim ("Substrate-component count
holds at FIVE per ADR-003 Consequence 1").

The module is the FIFTH Epic-8 runtime-code introduction (after Story 8.1's
SessionStart reattachment substrate, Story 8.2's cross-state recovery
algorithm, Story 8.3's resume command, Story 8.4's status command). Its
upstream caller is the orchestrator skill's ``/bmad-automation status``
sub-step at no-args invocation time (the no-args branch of the
``[<id>]``-optional CLI surface; the with-id branch dispatches to
:mod:`loud_fail_harness.status_command` per Story 8.4). The skill prose
lives at ``skills/bmad-automation/steps/status.md``; THIS module is invoked
as the ``bmad-automation-status-list`` CLI.

## The projection-not-duplication invariant (epics.md:3318-3320)

THIS substrate is the projection-consumer of Story 8.4's canonical
:func:`status_command.inspect_story`. Per epics.md:3318-3320 verbatim,
"there is no parallel inspection logic in 8.5 — the only logic unique to
8.5 is enumeration + orphan detection + projection". The substrate's
:func:`enumerate_stories` orchestrator iterates per-discovered-story-id
and invokes ``request.inspect_story_fn(StatusRequest(...,
resolve_retry_rounds=False))``, then projects each returned
:class:`StoryInspection` to a :class:`StoryRowSummary` carrying the five
enumerated fields per epics.md:3342 verbatim ``(story_id, current_state,
marker_count, last_activity_timestamp, branch_name)``.

The cheap-default invariant ``resolve_retry_rounds=False`` honors Story
8.4's commitment that multi-story enumeration cannot afford per-story
retry-round filesystem resolution (epics.md:3320). Story 8.4 AC-9's
``test_story_inspection_payload_supports_8_5_projection_shape`` is the
structural witness this substrate consumes — the projection compiles
using ONLY :class:`StoryInspection`'s public fields with NO parallel
inspection logic.

## The orphan-run-state-detected emission surface (epics.md:3345-3349)

THIS substrate is the **first and only** production emission surface for
the ``orphan-run-state-detected`` marker class (registered at
``schemas/marker-taxonomy.yaml:382``; entry 21 of 27 in the v1 closed
taxonomy). Orphan = run-state-PRESENT-but-story-doc-MISSING per
epics.md:3345 verbatim; the inverse pattern (story-doc-present-but-
run-state-missing) is NOT an orphan and is omitted from the listing.

Orphan emission writes ONLY to the marker registry via
``request.marker_recorder("orphan-run-state-detected", context)`` — NOT
to run-state files. The substrate is read-only against run-state contents
per the AC-6 write-surface invariant (mtime + sha256 unchanged for every
run-state file in the test fixture per
``test_enumerate_stories_does_not_mutate_run_state_files``).

The no-auto-purge invariant per epics.md:3351-3355: orphan run-state
files are NEVER deleted automatically; the diagnostic surfaces the
remediation pointers (purge via ``rm <path>`` OR recover the missing
story-doc from version control) and the practitioner decides. This
mirrors Story 7.6's ``init_non_destructive_guard`` non-destructive-default
posture.

## Architectural anchors

- **FR48b** (PRD line 877) — verbatim: "``/bmad-automation status`` (no
  args) lists runs by walking run-state files". THIS substrate IS the
  multi-story-listing implementation.
- **NFR-O4** (PRD line 983) — single-story status read-only invariant.
  Bound for Story 8.4 NOT THIS story; multi-story listing IS a write
  surface for orphan emissions to the marker registry (NOT to run-state).
- **ADR-003 Consequence 1** (architecture.md lines 311-315) — substrate-
  component count closure at FIVE.
- **Pattern 1** (architecture.md) — kebab-case identifiers (e.g.,
  ``orphan-run-state-detected``, ``listing-found``, ``listing-empty``).
- **Pattern 4** — frozen Pydantic state-update discipline.
- **Pattern 5** — loud-fail / named-invariant diagnostic.
- **Pattern 6** — typed-substrate / dependency-injection posture
  (Pydantic frozen models + explicit-path injection seams + DI seams for
  ``marker_recorder``, ``inspect_story_fn``, ``story_doc_existence_probe``).

## Sensor-not-advisor

Per ADR-001 + Pattern 5, this substrate produces a directive
(:class:`ListingOutcome` carrying :class:`StoryListing`); the orchestrator
skill's ``steps/status.md`` no-args runtime protocol parses the directive
and surfaces the rendered output verbatim. THIS substrate does NOT invoke
the Task tool, does NOT emit orchestrator events, does NOT advance
lifecycle state, does NOT mutate run-state, story-doc, sprint-status,
per-specialist logs, events.jsonl, deferred-work.md, or the git working
tree (the read-only invariant against persistent state; the marker
registry write is the ONLY emission surface).
"""

from __future__ import annotations

import argparse
import datetime
import logging
import pathlib
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .epic_run_state import (
    EpicCurrentState,
    EpicRunStateNotFound,
    EpicRunStateParseError,
    load_epic_run_state,
)
from .run_state import CurrentState
from .status_command import StatusOutcome, StatusRequest, StoryInspection, inspect_story

__all__ = [
    "EpicGroupSummary",
    "ListingOutcome",
    "ListingRequest",
    "MultiStoryStatusError",
    "StoryListing",
    "StoryRowSummary",
    "enumerate_stories",
    "main",
    "render_listing_empty_message",
    "render_story_listing_human",
    "render_story_listing_json",
]

_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Module-level constants                                                       #
# --------------------------------------------------------------------------- #


_AUTOMATION_RELATIVE_PATH: str = "_bmad/automation"
_IMPLEMENTATION_ARTIFACTS_RELATIVE_PATH: str = "_bmad-output/implementation-artifacts"
_QA_EVIDENCE_RELATIVE_PATH: str = "_bmad-output/qa-evidence"
_SPRINT_STATUS_FILENAME: str = "sprint-status.yaml"

#: The non-terminal lifecycle states used to filter sprint-status-derived
#: candidates per AC-2. Controls which sprint-status entries contribute
#: to discovery (the sprint-status SOURCE only); run-state-derived
#: candidates are included regardless of their sprint-status value.
#: ``ready-for-dev``, ``done``, ``backlog``, and ``optional`` are
#: intentionally absent (pre-terminal or post-terminal states produce no
#: active Automator session). Epic-X-* keys are filtered separately by
#: name pattern.
_NON_TERMINAL_SPRINT_STATES: frozenset[str] = frozenset(
    {"in-progress", "review", "qa", "escalated"}
)

#: The marker class registered at ``schemas/marker-taxonomy.yaml:382``.
#: THIS substrate is the FIRST production emission surface (AC-3).
_ORPHAN_MARKER_CLASS: str = "orphan-run-state-detected"

#: Empty-listing canonical message per AC-2/AC-4. Distinct from Story
#: 8.4's no-run-state diagnostic (which is a halt; THIS is silent
#: success / steady state).
_EMPTY_LISTING_MESSAGE: str = (
    "(no stories with non-terminal automator state found)"
)

#: Type aliases for the DI seams.
MarkerRecorder = Callable[[str, Mapping[str, Any]], None]
InspectStoryFn = Callable[[StatusRequest], StatusOutcome]


# --------------------------------------------------------------------------- #
# Exception classes                                                           #
# --------------------------------------------------------------------------- #


class MultiStoryStatusError(Exception):
    """Raised on substrate-level failures inside the multi-story listing.

    Pattern 5 — loud-fail / named invariants. Analogous in shape to
    :class:`status_command.StatusCommandError`,
    :class:`resume_command.ResumeCommandError`, and
    :class:`cross_state_recovery.CrossStateRecoveryError`.

    Programmer-error invariant per Pattern 5 — no marker emission at
    THIS surface (mirrors Story 8.3's ``ResumeCommandError`` posture).

    Attributes:
        reason: Short kebab-case discriminator naming the concrete failure.
        diagnostic: Human-readable diagnostic naming the failure mode.
    """

    #: Programmer-error invariant signal — no marker emission at THIS
    #: surface. The orphan emission is the substrate's ONLY write
    #: surface AND it is a content-driven emission (orphan detected),
    #: NOT a programmer-error emission.
    marker_class: ClassVar[None] = None

    def __init__(self, *, reason: str, diagnostic: str) -> None:
        self.reason = reason
        self.diagnostic = diagnostic
        super().__init__(f"MultiStoryStatusError[{reason}]: {diagnostic}")


# --------------------------------------------------------------------------- #
# Pydantic models — AC-1 public API                                           #
# --------------------------------------------------------------------------- #


class ListingRequest(BaseModel):
    """Typed input to :func:`enumerate_stories`.

    Pattern 6 — frozen so callers cannot mutate the request mid-evaluation.
    Mirrors :class:`status_command.StatusRequest` in shape.

    Attributes:
        project_root: Practitioner's BMAD project root. Required;
            ``is_absolute`` enforced at validation time.
        automation_dir: Pattern-6 explicit-path injection for the run-state
            walk. ``None`` resolves to ``project_root / _bmad/automation``.
        implementation_artifacts_dir: Pattern-6 explicit-path injection
            for the story-doc + sprint-status walk. ``None`` resolves to
            ``project_root / _bmad-output/implementation-artifacts``.
        qa_evidence_root: Forwarded to per-story
            :class:`StatusRequest.qa_evidence_root`. ``None`` resolves to
            ``project_root / _bmad-output/qa-evidence``.
        repo_root: Forwarded to per-story :class:`StatusRequest.repo_root`.
            ``None`` defaults to ``project_root``.
        marker_recorder: Pattern-6 DI seam for
            :func:`marker_wiring.record_marker_with_context`. ``None``
            resolves to a default that logs the emission at INFO; tests
            inject a list-appender stub to capture emissions structurally.
        inspect_story_fn: Pattern-6 DI seam for
            :func:`status_command.inspect_story`. ``None`` resolves to the
            live function; tests inject canned outcomes.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    project_root: pathlib.Path = Field(
        ...,
        description=(
            "Absolute path to the practitioner's project root. The "
            "discovery walk reads run-state files under "
            "<project_root>/_bmad/automation/ and the sprint-status "
            "under <project_root>/_bmad-output/implementation-artifacts/."
        ),
    )
    automation_dir: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional explicit path to the automation directory (the "
            "run-state walk root). None → project_root / _bmad/automation."
        ),
    )
    implementation_artifacts_dir: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional explicit path to the implementation-artifacts "
            "directory. None → project_root / "
            "_bmad-output/implementation-artifacts."
        ),
    )
    qa_evidence_root: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional explicit path to the qa-evidence root forwarded to "
            "the per-story StatusRequest. None → project_root / "
            "_bmad-output/qa-evidence."
        ),
    )
    repo_root: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional explicit repo_root forwarded to the per-story "
            "StatusRequest. None → project_root."
        ),
    )
    marker_recorder: MarkerRecorder | None = Field(
        default=None,
        description=(
            "Pattern-6 DI seam for the orphan-run-state-detected marker "
            "emission. None → default INFO-logger; tests inject a list-"
            "appender stub."
        ),
    )
    inspect_story_fn: InspectStoryFn | None = Field(
        default=None,
        description=(
            "Pattern-6 DI seam for status_command.inspect_story. None → "
            "the live function; tests inject canned StatusOutcome stubs."
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


class StoryRowSummary(BaseModel):
    """The canonical projection of :class:`StoryInspection` per epics.md:3342.

    Pattern 4 — frozen for hashability + immutability discipline. Field
    declaration order is load-bearing for byte-stable
    :meth:`model_dump_json` output.

    The five core fields exactly match epics.md:3342 verbatim
    ``(story_id, current_state, marker_count, last_activity_timestamp,
    branch_name)``; ``is_orphan`` is the local addition for orphan-row
    discrimination required by AC-3.

    Orphan rows MAY have non-empty ``current_state`` and ``branch_name``
    even though the story-doc is missing — the orphan run-state file is
    intact and parseable; only the story-doc is missing. The substrate
    surfaces the run-state's recorded values (best-effort triage info).
    """

    model_config = ConfigDict(frozen=True)

    story_id: str
    current_state: CurrentState
    marker_count: int
    last_activity_timestamp: datetime.datetime | None
    branch_name: str
    is_orphan: bool = False


class EpicGroupSummary(BaseModel):
    """A discovered non-terminal epic's grouping header (Story 15.4 AC-5).

    Frozen per Pattern 4; field declaration order is load-bearing for
    byte-stable :meth:`model_dump_json` output. Surfaces the epic's
    ``epic_id`` + non-terminal ``current_state`` + member ``story_ids`` (in
    the epic-defined cache order Story 15.1 seeded). Terminal
    ``epic-complete`` epics are NEVER constructed (omitted at discovery time,
    mirroring the per-story non-terminal filter).
    """

    model_config = ConfigDict(frozen=True)

    epic_id: str
    current_state: EpicCurrentState
    story_ids: tuple[str, ...]


class StoryListing(BaseModel):
    """The canonical multi-story listing payload per AC-1.

    Frozen per Pattern 4. ``rows`` is sorted by ``story_id``
    lexicographically for deterministic byte-stable output (mirrors
    :func:`marker_wiring.compute_alphabetical_marker_order`).

    Orphan rows interleave with normal rows by lexicographic ordering;
    the ``is_orphan`` field discriminates them visually in the renderer
    per AC-4.

    ``epic_groups`` (Story 15.4 AC-5) is a PURELY ADDITIVE field carrying
    discovered non-terminal epic groupings. It defaults to ``()`` so a
    project that never ran ``run --epic`` has byte-identical no-args output
    (the renderers omit the field/section entirely when it is empty — the
    bit-identity guard).
    """

    model_config = ConfigDict(frozen=True)

    rows: tuple[StoryRowSummary, ...]
    orphan_count: int
    total_count: int
    epic_groups: tuple[EpicGroupSummary, ...] = ()


_ListingAction = Literal["listing-found", "listing-empty"]


class ListingOutcome(BaseModel):
    """Typed return of :func:`enumerate_stories`.

    Pattern 6 — frozen so the orchestrator skill cannot mutate the
    outcome between read and route.

    Attributes:
        action: ``"listing-found"`` when ``rows`` has at least one entry
            (normal OR orphan); ``"listing-empty"`` when no rows at all
            (the steady-state case per AC-2's empty-listing semantics —
            silent success, NOT a halt).
        listing: Populated unconditionally; empty ``listing.rows == ()``
            represents the empty case.
    """

    model_config = ConfigDict(frozen=True)

    action: _ListingAction
    listing: StoryListing


# --------------------------------------------------------------------------- #
# DI-seam defaults                                                            #
# --------------------------------------------------------------------------- #


def _default_marker_recorder(
    marker_class: str, context: Mapping[str, Any]
) -> None:
    """Default :data:`MarkerRecorder` invoked when ``ListingRequest.
    marker_recorder`` is ``None``.

    Production marker visibility for ``orphan-run-state-detected`` is
    the rendered listing's ``## Loud-fail markers`` section (the human-
    readable render assembles per-orphan loud-fail blocks per AC-4); the
    JSON render carries the orphan-detection structurally via
    ``StoryRowSummary.is_orphan``. THIS default ALSO emits an INFO log
    so emissions surface in the orchestrator-skill's runtime log
    pipeline.

    The substrate is read-only against run-state files per AC-6 — the
    canonical :func:`marker_wiring.record_marker_with_context` helper
    requires a :class:`RunState` to mutate, which conflicts with that
    invariant. Marker registry persistence at MVP is via the listing
    output's structural orphan rows; future hardening MAY thicken this
    default to a registry-backed appender per the AC-11 forward-scope
    discipline.
    """
    _logger.info("marker emitted: %s context=%r", marker_class, dict(context))


# --------------------------------------------------------------------------- #
# Discovery walk (AC-2)                                                       #
# --------------------------------------------------------------------------- #


def _extract_story_id_from_run_state_file(path: pathlib.Path) -> str | None:
    """Lightweight YAML parse of a run-state file to extract ``story_id``.

    Per AC-2: the discovery walk does NOT validate the full
    :class:`RunState` schema (Story 8.4's ``inspect_story`` validates per-
    candidate AFTER discovery). Malformed YAML or missing ``story_id``
    yields ``None``; the caller skips the candidate at DEBUG.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        _logger.debug("run-state file unreadable %r: %r — skipping", path, exc)
        return None
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        _logger.debug("run-state file malformed %r: %r — skipping", path, exc)
        return None
    if not isinstance(parsed, dict):
        _logger.debug(
            "run-state file %r did not parse as a mapping — skipping", path
        )
        return None
    story_id = parsed.get("story_id")
    if not isinstance(story_id, str) or not story_id.strip():
        _logger.debug(
            "run-state file %r lacks a 'story_id' field — skipping", path
        )
        return None
    return story_id


def _discover_run_state_candidates(
    automation_dir: pathlib.Path,
) -> dict[str, pathlib.Path]:
    """Walk ``automation_dir`` for ``*.yaml`` run-state files and extract
    each file's ``story_id``.

    Per AC-2: non-recursive ``*.yaml`` glob (the schema's documented
    location is a single file at ``_bmad/automation/run-state.yaml``;
    the walk is forward-compatible for a hypothetical future per-story
    layout). Returns a mapping of ``story_id → run_state_file_path``.
    """
    candidates: dict[str, pathlib.Path] = {}
    if not automation_dir.is_dir():
        return candidates
    for path in sorted(automation_dir.glob("*.yaml")):
        story_id = _extract_story_id_from_run_state_file(path)
        if story_id is None:
            continue
        # First-write-wins on duplicate story_id across multiple files —
        # MVP layout has only one file so this is structurally a no-op.
        candidates.setdefault(story_id, path)
    return candidates


def _discover_sprint_status_candidates(
    implementation_artifacts_dir: pathlib.Path,
) -> set[str]:
    """Walk ``implementation_artifacts_dir/sprint-status.yaml`` for
    non-terminal ``development_status`` entries.

    Per AC-2: filters entries whose status is in
    :data:`_NON_TERMINAL_SPRINT_STATES`; excludes ``epic-X``,
    ``epic-X-retrospective``, and any keys not matching the
    ``number-number-name`` pattern.
    """
    candidates: set[str] = set()
    sprint_path = implementation_artifacts_dir / _SPRINT_STATUS_FILENAME
    if not sprint_path.is_file():
        return candidates
    try:
        text = sprint_path.read_text(encoding="utf-8")
    except OSError as exc:
        _logger.debug(
            "sprint-status file unreadable %r: %r — skipping", sprint_path, exc
        )
        return candidates
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        _logger.debug(
            "sprint-status file malformed %r: %r — skipping", sprint_path, exc
        )
        return candidates
    if not isinstance(parsed, dict):
        return candidates
    development_status = parsed.get("development_status")
    if not isinstance(development_status, dict):
        return candidates
    for key, value in development_status.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if value not in _NON_TERMINAL_SPRINT_STATES:
            continue
        if key.startswith("epic-"):
            # Excludes both ``epic-X`` and ``epic-X-retrospective``.
            continue
        # Pattern: number-number-name (e.g., "8-5-bmad-...").
        head = key.split("-", 2)
        if len(head) < 2 or not head[0].isdigit() or not head[1].isdigit():
            continue
        candidates.add(key)
    return candidates


def _discover_epic_groups(
    automation_dir: pathlib.Path,
) -> tuple["EpicGroupSummary", ...]:
    """Walk ``automation_dir`` for epic-run-state cache(s) and project each
    non-terminal cache to an :class:`EpicGroupSummary` (Story 15.4 AC-5).

    The walk is a non-recursive ``*.yaml`` glob consistent with
    :func:`_discover_run_state_candidates` (so Epic 18's per-worktree
    expansion is additive). At Epic 15 scope this is the single
    ``epic-run-state.yaml``. A ``*.yaml`` that is NOT an epic-run-state cache
    (e.g. the per-story ``run-state.yaml``) fails
    :func:`epic_run_state.load_epic_run_state` validation and is skipped at
    DEBUG — it is not an epic-run-state file. Terminal ``epic-complete`` epics
    are omitted from the grouping headers (mirroring the per-story
    non-terminal filter).
    """
    if not automation_dir.is_dir():
        return ()
    groups: list[EpicGroupSummary] = []
    for path in sorted(automation_dir.glob("*.yaml")):
        try:
            cache = load_epic_run_state(path)
        except EpicRunStateNotFound as exc:
            _logger.debug(
                "candidate %r not found or disappeared (race) — skipping: %r",
                path,
                exc,
            )
            continue
        except EpicRunStateParseError as exc:
            _logger.debug(
                "candidate %r is not a valid epic-run-state cache: %r — "
                "skipping",
                path,
                exc,
            )
            continue
        if cache.current_state == "epic-complete":
            continue
        groups.append(
            EpicGroupSummary(
                epic_id=cache.epic_id,
                current_state=cache.current_state,
                story_ids=cache.story_ids,
            )
        )
    return tuple(groups)


# --------------------------------------------------------------------------- #
# Projection + orphan detection (AC-2 / AC-3)                                 #
# --------------------------------------------------------------------------- #


def _coerce_envelope_timestamp(
    envelope: Mapping[str, Any] | None,
) -> datetime.datetime | None:
    """Project ``last_envelope.timestamp`` to a ``datetime.datetime``.

    The envelope's ``timestamp`` field per ``schemas/envelope.schema.yaml``
    is an ISO-8601 string; a missing-or-unparseable timestamp yields
    ``None`` (story is in a pre-dispatch state OR the timestamp is
    structurally absent per the envelope schema's optional clause).
    """
    if envelope is None:
        return None
    raw = envelope.get("timestamp")
    if raw is None:
        return None
    if isinstance(raw, datetime.datetime):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return datetime.datetime.fromisoformat(raw)
    except ValueError:
        _logger.debug(
            "envelope timestamp %r is not ISO-8601 — projecting to None", raw
        )
        return None


def _project_inspection_to_row(
    inspection: StoryInspection, *, is_orphan: bool
) -> StoryRowSummary:
    """Project a :class:`StoryInspection` to a :class:`StoryRowSummary`
    per epics.md:3342.

    The projection compiles using ONLY :class:`StoryInspection`'s public
    fields — Story 8.4 AC-9's structural-witness contract.
    """
    return StoryRowSummary(
        story_id=inspection.story_id,
        current_state=inspection.current_state,
        marker_count=len(inspection.active_markers),
        last_activity_timestamp=_coerce_envelope_timestamp(
            inspection.last_envelope
        ),
        branch_name=inspection.branch_name,
        is_orphan=is_orphan,
    )


def _build_orphan_context(
    *,
    story_id: str,
    run_state_file_path: pathlib.Path,
    expected_story_doc_dir: pathlib.Path,
) -> dict[str, Any]:
    """Build the AC-3 marker context payload for an
    ``orphan-run-state-detected`` emission.
    """
    return {
        "story_id": story_id,
        "run_state_file_path": str(run_state_file_path),
        "expected_story_doc_dir": str(expected_story_doc_dir),
        "remediation": (
            "purge orphan run-state via direct filesystem rm "
            f"{run_state_file_path}; OR recover missing story-doc from "
            "version control (e.g., git log --diff-filter=D)"
        ),
    }


# --------------------------------------------------------------------------- #
# enumerate_stories — canonical entry point                                   #
# --------------------------------------------------------------------------- #


def enumerate_stories(request: ListingRequest) -> ListingOutcome:
    """Canonical multi-story enumeration entry per FR48b.

    THIS is the function the no-args slash-command branch invokes per
    AC-7's runtime protocol. Pure modulo: filesystem reads (the
    discovery walk + per-candidate ``inspect_story`` reads) AND marker-
    registry writes for orphan emissions (the ONLY write surface in
    this substrate, gated by the ``marker_recorder`` DI seam for
    testability).

    Algorithm per AC-2 / AC-3:

    1. Resolve injected paths (``automation_dir``,
       ``implementation_artifacts_dir``, ``qa_evidence_root``,
       ``repo_root``) against ``project_root`` defaults.
    2. Discover run-state-derived candidates by walking
       ``automation_dir`` for ``*.yaml`` files and extracting
       ``story_id`` from each (lightweight YAML parse; full schema
       validation happens per-candidate in ``inspect_story``).
    3. Discover sprint-status-derived candidates by reading
       ``implementation_artifacts_dir/sprint-status.yaml``'s
       ``development_status`` mapping and filtering against
       :data:`_NON_TERMINAL_SPRINT_STATES`.
    4. Union + dedup the candidate sets; sort lexicographically.
    5. Per candidate, invoke
       ``request.inspect_story_fn(StatusRequest(...,
       resolve_retry_rounds=False))``.
    6. If the inspection returns ``status-no-run-state`` for a
       sprint-status-only candidate, OMIT the candidate from the
       listing (it is NOT an orphan; orphan is the inverse pattern).
    7. If ``inspection.story_doc_path is None`` AND the candidate
       came from a run-state file (i.e., the run-state IS present),
       emit ``orphan-run-state-detected`` via
       ``request.marker_recorder`` AND mark the row ``is_orphan=True``.
    8. Project each inspection to a :class:`StoryRowSummary`.
    9. Sort rows lexicographically by ``story_id``; assemble
       :class:`StoryListing`; return :class:`ListingOutcome`.

    Args:
        request: The typed input.

    Returns:
        :class:`ListingOutcome`. ``action`` discriminates ``listing-found``
        (≥1 row) from ``listing-empty`` (0 rows; steady state).

    Raises:
        MultiStoryStatusError: When the substrate hits an unexpected
            programmer-error condition (currently no documented raise
            sites; reserved for future hardening).
    """
    automation_dir = (
        request.automation_dir
        if request.automation_dir is not None
        else request.project_root / _AUTOMATION_RELATIVE_PATH
    )
    implementation_artifacts_dir = (
        request.implementation_artifacts_dir
        if request.implementation_artifacts_dir is not None
        else request.project_root / _IMPLEMENTATION_ARTIFACTS_RELATIVE_PATH
    )
    qa_evidence_root = (
        request.qa_evidence_root
        if request.qa_evidence_root is not None
        else request.project_root / _QA_EVIDENCE_RELATIVE_PATH
    )
    repo_root = (
        request.repo_root
        if request.repo_root is not None
        else request.project_root
    )
    marker_recorder = (
        request.marker_recorder
        if request.marker_recorder is not None
        else _default_marker_recorder
    )
    inspect_fn = (
        request.inspect_story_fn
        if request.inspect_story_fn is not None
        else inspect_story
    )

    # AC-2: discovery walk.
    run_state_candidates = _discover_run_state_candidates(automation_dir)
    sprint_status_candidates = _discover_sprint_status_candidates(
        implementation_artifacts_dir
    )

    all_story_ids = sorted(
        set(run_state_candidates.keys()) | sprint_status_candidates
    )

    rows: list[StoryRowSummary] = []
    for story_id in all_story_ids:
        run_state_file_path = run_state_candidates.get(story_id)
        from_run_state = run_state_file_path is not None
        status_request = StatusRequest(
            project_root=request.project_root,
            story_id=story_id,
            run_state_path=run_state_file_path,
            qa_evidence_root=qa_evidence_root,
            repo_root=repo_root,
            resolve_retry_rounds=False,
        )
        try:
            outcome = inspect_fn(status_request)
        except Exception as exc:  # noqa: BLE001 — loud-fail boundary per P1
            raise MultiStoryStatusError(
                reason="inspect-story-error",
                diagnostic=(
                    f"inspect_story raised an unexpected error for "
                    f"story_id={story_id!r}: {exc!r}"
                ),
            ) from exc

        if outcome.action == "status-no-run-state":
            # Sprint-status-only candidate (story-doc present but no
            # run-state). NOT an orphan — orphan is the inverse pattern.
            # Omit from the listing per AC-2/AC-3.
            continue

        inspection = outcome.inspection
        if inspection is None:
            # Defensive: status-found with inspection=None violates the
            # substrate contract; skip silently rather than crash.
            _logger.debug(
                "inspect_story returned %r with inspection=None for "
                "story_id=%r — skipping",
                outcome.action,
                story_id,
            )
            continue

        # AC-3 orphan detection: structural signal from inspect_story's
        # graceful-degrade output. Production code path consumes
        # ``inspection.story_doc_path is None`` rather than re-probing.
        is_orphan = from_run_state and inspection.story_doc_path is None
        if is_orphan and run_state_file_path is not None:
            context = _build_orphan_context(
                story_id=story_id,
                run_state_file_path=run_state_file_path,
                expected_story_doc_dir=implementation_artifacts_dir,
            )
            marker_recorder(_ORPHAN_MARKER_CLASS, context)

        rows.append(_project_inspection_to_row(inspection, is_orphan=is_orphan))

    rows_tuple = tuple(rows)
    orphan_count = sum(1 for r in rows_tuple if r.is_orphan)
    # AC-5: purely-additive per-epic grouping. Empty when no epic-run-state
    # cache exists → byte-identical no-args output (the bit-identity guard).
    epic_groups = _discover_epic_groups(automation_dir)
    listing = StoryListing(
        rows=rows_tuple,
        orphan_count=orphan_count,
        total_count=len(rows_tuple),
        epic_groups=epic_groups,
    )
    action: _ListingAction = "listing-found" if rows_tuple else "listing-empty"
    return ListingOutcome(action=action, listing=listing)


# --------------------------------------------------------------------------- #
# Renderers (pure deterministic formatters)                                   #
# --------------------------------------------------------------------------- #


def render_listing_empty_message() -> str:
    """Pure deterministic formatter producing the AC-2 empty-listing
    message.

    Distinct from :func:`status_command.render_no_run_state_diagnostic`
    — the multi-story empty case is silent success (CLI exit 0), NOT a
    halt-with-diagnostic. Byte-stable on identical input (the AC-9
    purity contract).
    """
    return _EMPTY_LISTING_MESSAGE


def _format_timestamp(ts: datetime.datetime | None) -> str:
    if ts is None:
        return "(none)"
    return ts.isoformat()


def _render_story_row_line(row: StoryRowSummary) -> str:
    """Render a single per-story row line (byte-identical to the Story 8.5
    inline form). Shared by the ungrouped ``## Stories`` section and the
    per-epic grouped rows (Story 15.4 AC-5)."""
    ts_rendered = _format_timestamp(row.last_activity_timestamp)
    if row.is_orphan:
        return (
            f"[ORPHAN] {row.story_id} [{row.current_state}] "
            f"branch={row.branch_name} markers={row.marker_count} "
            f"last_activity={ts_rendered} -- story-doc missing; "
            "orphan-run-state-detected marker emitted"
        )
    return (
        f"{row.story_id} [{row.current_state}] "
        f"branch={row.branch_name} markers={row.marker_count} "
        f"last_activity={ts_rendered}"
    )


def render_story_listing_human(listing: StoryListing) -> str:
    """Pure deterministic formatter producing the AC-4 human-readable
    terminal output.

    Mirrors Story 6.1's loud-fail block style for the orphan section AND
    Story 5.8's escalation-bundle structure for the per-row summaries.
    Byte-stable on identical input (the AC-9 purity contract).

    Sections (in order):

    1. Heading: ``# /bmad-automation status — multi-story listing``
    2. ``## Summary`` — total + orphans counts.
    3. ``## Epics`` — per-epic grouped member rows (Story 15.4 AC-5; rendered
       ONLY when ``epic_groups`` is non-empty — purely additive).
    4. ``## Stories`` — ungrouped (non-epic-member) per-row entries.
    5. ``## Loud-fail markers`` — per-orphan blocks (rendered when
       ``orphan_count > 0``).
    6. ``## Empty case`` — empty-listing message (rendered when
       ``total_count == 0``).

    Bit-identity guard (Story 15.4 AC-5): when ``epic_groups`` is empty, the
    ``## Epics`` section is absent and EVERY row is a non-member, so the
    ``## Stories`` section is byte-identical to Story 8.5's output.
    """
    member_ids: set[str] = set()
    for group in listing.epic_groups:
        member_ids.update(group.story_ids)
    rows_by_id = {row.story_id: row for row in listing.rows}

    lines: list[str] = []
    lines.append("# /bmad-automation status — multi-story listing")
    lines.append("")

    # --- Summary ---
    lines.append("## Summary")
    lines.append("")
    lines.append(f"total: {listing.total_count}")
    lines.append(f"orphans: {listing.orphan_count}")
    lines.append("")

    # --- Epics (grouped member rows; purely additive) ---
    if listing.epic_groups:
        lines.append("## Epics")
        lines.append("")
        for group in listing.epic_groups:
            group_rows = [
                rows_by_id[sid] for sid in group.story_ids if sid in rows_by_id
            ]
            if not group_rows:
                continue
            lines.append(f"### {group.epic_id} [{group.current_state}]")
            lines.append("")
            for row in group_rows:
                lines.append(_render_story_row_line(row))
                lines.append("")

    # --- Stories (ungrouped non-members) ---
    non_member_rows = [
        row for row in listing.rows if row.story_id not in member_ids
    ]
    if non_member_rows:
        lines.append("## Stories")
        lines.append("")
        for row in non_member_rows:
            lines.append(_render_story_row_line(row))
            lines.append("")

    # --- Loud-fail markers ---
    if listing.orphan_count > 0:
        lines.append("## Loud-fail markers")
        lines.append("")
        for row in listing.rows:
            if not row.is_orphan:
                continue
            lines.append(
                f"### orphan-run-state-detected — story {row.story_id}"
            )
            lines.append("")
            lines.append(
                "diagnostic_pointer: FR48b (multi-story status enumeration). "
                "Fires when the status enumerator finds run-state entries "
                "for stories whose story-doc has been deleted, renamed, or "
                "moved."
            )
            lines.append(
                "remediation: purge orphan run-state via direct "
                "filesystem rm <run_state_file_path>; OR recover missing "
                "story-doc from version control (e.g., "
                "git log --diff-filter=D)."
            )
            lines.append("")

    # --- Empty case ---
    if listing.total_count == 0:
        lines.append("## Empty case")
        lines.append("")
        lines.append(render_listing_empty_message())
        lines.append("")

    return "\n".join(lines)


def render_story_listing_json(listing: StoryListing) -> str:
    """Pure deterministic JSON formatter producing the AC-5
    machine-consumable output.

    Uses :meth:`StoryListing.model_dump_json` with ``indent=2`` per
    Pydantic v2's canonical serialization. Field declaration order is
    load-bearing for byte-stable output. ``datetime.datetime`` fields
    serialize as ISO-8601; round-trip via
    :meth:`StoryListing.model_validate_json` is byte-stable.

    Bit-identity guard (Story 15.4 AC-5): ``epic_groups`` (the trailing
    additive field) is excluded from the dump when empty, so a project that
    never ran ``run --epic`` has byte-identical no-args JSON to Story 8.5's.
    """
    if listing.epic_groups:
        return listing.model_dump_json(indent=2)
    return listing.model_dump_json(indent=2, exclude={"epic_groups"})


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bmad-automation-status-list",
        description=(
            "/bmad-automation status (no-args) substrate (Story 8.5, "
            "FR48b). Multi-story enumeration with orphan-run-state-"
            "detected marker emission. Walks _bmad/automation/ for "
            "run-state files AND _bmad-output/implementation-artifacts/"
            "sprint-status.yaml for non-terminal entries; projects "
            "Story 8.4's status_command.inspect_story per enumerated "
            "story-id; emits orphan markers for run-state entries whose "
            "story-doc is missing."
        ),
    )
    parser.add_argument(
        "--project-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Absolute path to the practitioner's project root. Defaults "
            "to the current working directory."
        ),
    )
    parser.add_argument(
        "--automation-dir",
        type=pathlib.Path,
        default=None,
        help=(
            "Optional explicit path to the automation directory. "
            "Defaults to <project_root>/_bmad/automation."
        ),
    )
    parser.add_argument(
        "--implementation-artifacts-dir",
        type=pathlib.Path,
        default=None,
        help=(
            "Optional explicit path to the implementation-artifacts "
            "directory. Defaults to <project_root>/_bmad-output/"
            "implementation-artifacts."
        ),
    )
    parser.add_argument(
        "--qa-evidence-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Optional explicit path to the qa-evidence root. Defaults "
            "to <project_root>/_bmad-output/qa-evidence."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Optional explicit repo_root for retry-round artifact "
            "resolution. Defaults to --project-root."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_flag",
        help=(
            "Emit machine-consumable JSON instead of the human-readable "
            "render."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point invoked by the orchestrator skill's
    ``steps/status.md`` no-args runtime protocol per AC-7.

    Exit codes per AC-1:
        * ``0`` — ``listing-found`` OR ``listing-empty`` (silent
          success; both are non-error outcomes; orphan emissions are
          conveyed through the rendered listing, NOT through the exit
          code).
        * ``2`` — harness-level error inside the substrate per
          Pattern 5 (Pydantic validation failure, etc.).

    There is NO exit-code-1 path here — distinct from Story 8.4's CLI
    semantics. The multi-story enumeration has no analogous "named-
    story-not-found" halt; an empty listing is a steady-state outcome.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    project_root = (
        args.project_root if args.project_root is not None else pathlib.Path.cwd()
    )
    if not project_root.is_absolute():
        project_root = project_root.resolve()

    try:
        request = ListingRequest(
            project_root=project_root,
            automation_dir=args.automation_dir,
            implementation_artifacts_dir=args.implementation_artifacts_dir,
            qa_evidence_root=args.qa_evidence_root,
            repo_root=args.repo_root,
        )
    except (ValueError, ValidationError) as exc:
        print(f"status-list: harness-level error: {exc}", file=sys.stderr)
        return 2

    try:
        outcome = enumerate_stories(request)
    except MultiStoryStatusError as exc:
        print(f"status-list: harness-level error: {exc}", file=sys.stderr)
        return 2

    if args.json_flag:
        print(render_story_listing_json(outcome.listing))
    else:
        if outcome.action == "listing-empty":
            print(render_listing_empty_message())
        else:
            print(render_story_listing_human(outcome.listing))
    return 0
