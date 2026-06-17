"""``/bmad-automation status <story-id>`` substrate library — Story 8.4.

## Substrate-component identity

THIS module is a substrate **library** sibling of
:mod:`loud_fail_harness.session_start_reattach` (Story 8.1),
:mod:`loud_fail_harness.cross_state_recovery` (Story 8.2),
:mod:`loud_fail_harness.resume_command` (Story 8.3),
:mod:`loud_fail_harness.init_non_destructive_guard` (Story 7.6),
:mod:`loud_fail_harness.tea_boundary_orientation` (Story 7.8), and
:mod:`loud_fail_harness.story_doc_version_check` (Story 7.7). It is **NOT a
sixth substrate component** beyond ADR-003 Consequence 1's enumerated five
(``envelope_validator``, ``event_validator``, ``reconciler``,
``enumeration_check``, ``fixture_coverage``); the count remains FIVE through
Epic 8 per the Epic 7 retro framing
(``epic-7-retro-2026-05-08.md`` line 122) and Story 8.3's Completion Notes
("Substrate-component count holds at FIVE per ADR-003 Consequence 1").

The module is the FOURTH Epic-8 runtime-code introduction (after Story 8.1's
SessionStart reattachment substrate, Story 8.2's cross-state recovery
algorithm, Story 8.3's resume command). Consumers:

* The orchestrator skill at ``/bmad-automation status <story-id>`` time
  (the explicit single-story-inspection path; consumes the canonical
  inspection function for a practitioner-named story-id). The skill prose
  lives at ``skills/bmad-automation/steps/status.md``; THIS module is
  invoked as the ``bmad-automation-status`` CLI.
* (Forward-scoped) Story 8.5's no-args multi-story listing, which calls
  :func:`inspect_story` per enumerated story-id and projects the
  :class:`StoryInspection` payload to a row-summary shape (story-id,
  current state, marker count, last activity timestamp, branch name)
  per epics.md:3342 verbatim. The projection-not-duplication invariant
  is the structural commitment of THIS story's AC-9
  ``test_story_inspection_payload_supports_8_5_projection_shape``.

This module is the SECOND production-call site of
:func:`cross_state_recovery._load_run_state_from_disk` (after Story 8.3's
``resume_command.evaluate_resume`` per its 8-3-...:518 Dev's-call
documentation). THIS story does NOT promote the helper to public — it
consumes the same private name via the same ``from .cross_state_recovery
import _load_run_state_from_disk`` import per the precedent. (Story 8.6
may revisit promotion when retrofitting the canonical ``can_dispatch()``
substrate guard; Story 8.4 holds the line on Story 8.3's Dev's-call.)

## Architectural anchors

- **FR48** (PRD line 876) — "``/bmad-automation status [story-id]`` exposes
  current state, retry history, loud-fail markers, and latest specialist
  return without advancing state or mutating run-state." THIS substrate IS
  the single-story-inspection implementation.
- **NFR-O4** (PRD line 983) — verbatim: "exposes current state, retry
  history, loud-fail markers, and latest specialist return without
  advancing state or mutating run-state" — the read-only invariant.
- **NFR-R5** (PRD line 949) — retry-history preservation visibility; the
  inspection's ``retry_history`` + ``resolved_retry_rounds`` fields surface
  this.
- **NFR-O2** (PRD line 981) — run-state inspectability; status complements
  but does not replace direct YAML inspection.
- **ADR-003 Consequence 1** (architecture.md lines 311-315) — substrate-
  component count closure at FIVE (this module is a substrate-library
  sibling, NOT a sixth component).
- **Pattern 5** (architecture.md) — loud-fail / named-invariant diagnostic
  (the no-run-state path).
- **Pattern 6** (architecture.md) — typed-substrate / dependency-injection
  posture (Pydantic frozen models + explicit-path injection seams).

## The two ``StatusOutcome.action`` branches

* ``status-found`` — run-state file present at the resolved path; the
  inspection succeeded; ``inspection: StoryInspection`` is populated;
  ``diagnostic`` is ``None``.
* ``status-no-run-state`` — pre-check found NO run-state file at the
  resolved path; halts with a named-invariant diagnostic
  ``no-in-flight-run-found-for-story-id`` per epics.md:3322-3325
  verbatim ("the command halts with a named-invariant diagnostic"); NO
  marker emitted (the named-invariant diagnostic IS the loud-fail signal —
  distinct from Story 8.5's ``orphan-run-state-detected`` marker which
  fires on the INVERSE pattern: run-state exists but story-doc is missing).

## Read-only invariant (NFR-O4 verbatim)

The substrate is read-only against run-state, story-doc, sprint-status,
per-specialist logs, events.jsonl, deferred-work.md, retry-history
artifacts, and the git working tree. NO call to
``record_marker_with_context``, ``commit_transition``, ``advance_run_state``,
``_default_run_state_writer``, ``default_artifact_writer``, the event-log
appender factory, ``subprocess.run(["git", ...])``, or any other
write-shaped surface. The structural witness is AC-9's
``test_status_command_has_no_write_surfaces`` test.

This substrate does NOT invoke ``cross_state_recovery.evaluate_recovery``
because that function's rebuild path mutates run-state via the
``run_state_writer`` DI seam — even if run-state and story-doc disagree,
status surfaces the run-state's recorded values WITHOUT correcting them.
The recovery-on-disagreement path is ``/bmad-automation resume``'s job,
not ``/bmad-automation status``'s.

## Sensor-not-advisor

Per ADR-001 + Pattern 5, this substrate produces a directive
(:class:`StatusOutcome` carrying :class:`StoryInspection`); the
orchestrator skill's ``steps/status.md`` runtime protocol parses the
directive and surfaces the rendered output verbatim. THIS substrate does
NOT invoke the Task tool, does NOT emit orchestrator events, does NOT
advance lifecycle state, does NOT mutate any persisted state.
"""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
from collections.abc import Sequence
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .background_dispatch import (
    _default_background_runs_recorder,
    make_git_ground_truth_probe,
    reconcile_background_runs,
    render_background_runs_section,
)
from .cross_state_recovery import (
    RUN_STATE_RELATIVE_PATH,
    CrossStateRecoveryError,
    _load_run_state_from_disk,
)
from .marker_wiring import compute_alphabetical_marker_order
from .orchestrator_run_entry import (
    StoryDocResolver,
    default_story_doc_resolver,
)
from .retry_history import (
    DanglingRetryRoundRef,
    RetryAttemptRef,
    RetryHistoryError,
    RetryRoundArtifacts,
    detect_dangling_refs,
    resolve_retry_round,
)
from .run_state import (
    CostToDateBySpecialist,
    CurrentState,
    DispatchedSpecialist,
    RetryAttempt,
)
from .specialist_dispatch import load_marker_class_registry

__all__ = [
    "StatusCommandError",
    "StatusOutcome",
    "StatusRequest",
    "StoryInspection",
    "inspect_story",
    "main",
    "render_no_run_state_diagnostic",
    "render_story_inspection_human",
    "render_story_inspection_json",
]

_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Module-level constants                                                       #
# --------------------------------------------------------------------------- #


#: Default qa-evidence root relative to ``project_root`` per architecture.md
#: View 3 line 1171. Mirrors the practitioner installation path.
_QA_EVIDENCE_RELATIVE_PATH: str = "_bmad-output/qa-evidence"


# --------------------------------------------------------------------------- #
# Exception classes                                                           #
# --------------------------------------------------------------------------- #


class StatusCommandError(Exception):
    """Raised on substrate-level failures inside the status command.

    Pattern 5 — loud-fail / named invariants. Analogous in shape to
    :class:`resume_command.ResumeCommandError`,
    :class:`cross_state_recovery.CrossStateRecoveryError`, and
    :class:`session_start_reattach.SessionStartReattachError`.

    RESERVED for substrate-level errors:
      * :func:`cross_state_recovery._load_run_state_from_disk` raised
        :class:`CrossStateRecoveryError` (chained via ``from exc``).
      * ``run_state_path.is_file()`` raised :class:`OSError` (permission
        denied, broken filesystem).
      * Any other unexpected exception from the load substrate that is
        NOT in the documented :class:`CrossStateRecoveryError` set.

    Programmer-error invariant per Pattern 5 — no marker emission at
    THIS surface (mirrors Story 8.3's ``ResumeCommandError`` posture).

    Attributes:
        reason: Short kebab-case discriminator naming the concrete failure.
            Documented values: ``"cross-state-recovery-substrate-error"``,
            ``"run-state-path-access-error"``.
        diagnostic: Human-readable diagnostic naming the failure mode and
            a remediation hint per NFR-O5.
    """

    #: Programmer-error invariant signal — no marker emission at THIS
    #: surface. Mirrors Story 8.3's ``ResumeCommandError`` posture.
    marker_class: ClassVar[None] = None

    def __init__(self, *, reason: str, diagnostic: str) -> None:
        self.reason = reason
        self.diagnostic = diagnostic
        super().__init__(f"StatusCommandError[{reason}]: {diagnostic}")


# --------------------------------------------------------------------------- #
# Pydantic models — AC-1 public API                                           #
# --------------------------------------------------------------------------- #


class StatusRequest(BaseModel):
    """Typed input to :func:`inspect_story`.

    Pattern 6 — frozen so callers cannot mutate the request mid-evaluation.
    Mirrors :class:`resume_command.ResumeRequest`,
    :class:`cross_state_recovery.RecoveryRequest`,
    :class:`session_start_reattach.ReattachRequest`, and
    :class:`init_non_destructive_guard.GuardRequest` in shape.

    Attributes:
        project_root: Practitioner's BMAD project root. The substrate
            inspects ``<project_root>/_bmad/automation/run-state.yaml``
            (unless ``run_state_path`` overrides) and resolves the
            story-doc + per-specialist log dir from sub-paths.
            Required; ``is_absolute`` enforced at validation time.
        story_id: BMAD story identifier the practitioner supplied at
            ``/bmad-automation status <story-id>``. Required;
            ``min_length=1``.
        run_state_path: Pattern-6 explicit-path injection. ``None``
            resolves to ``project_root / RUN_STATE_RELATIVE_PATH``. CLI
            sets this when ``--run-state-path`` is provided so the
            substrate's pre-check matches the practitioner's run-state
            location.
        qa_evidence_root: Pattern-6 explicit-path injection for the
            per-specialist log directory. ``None`` resolves to
            ``project_root / _QA_EVIDENCE_RELATIVE_PATH`` per
            architecture.md View 3 line 1171.
        resolve_retry_rounds: Governs whether
            :func:`retry_history.resolve_retry_round` is invoked per
            :class:`RetryAttemptRef`. ``False`` (default) returns the
            refs unchanged for fast projection by Story 8.5's
            enumeration; ``True`` resolves to
            :class:`RetryRoundArtifacts` for the human/JSON renderers.
            The default-OFF posture keeps Story 8.5's enumeration cheap.
        repo_root: Pattern-6 explicit-path injection for the
            :func:`retry_history.resolve_retry_round` invocation's
            ``repo_root`` argument. ``None`` defaults to ``project_root``
            (the typical project layout has retry-history rooted at
            ``<project_root>/_bmad-output/retry-history/...``).
        story_doc_resolver: Pattern-6 dependency-injection seam for
            tests. Production runs default to
            :func:`orchestrator_run_entry.default_story_doc_resolver` per
            the Story 2.5 + Story 8.2 + Story 8.3 precedent. Resolver
            failure is graceful-degraded per AC-3 — the inspection still
            proceeds with ``story_doc_path=None``.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    project_root: pathlib.Path = Field(
        ...,
        description=(
            "Absolute path to the practitioner's project root. Read for "
            "the run-state file, story-doc resolution, and the "
            "per-specialist log directory projection."
        ),
    )
    story_id: str = Field(
        ...,
        min_length=1,
        description=(
            "BMAD story identifier; sourced from /bmad-automation status "
            "<story-id> OR Story 8.5's enumeration loop."
        ),
    )
    run_state_path: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional explicit path to the run-state file. None → "
            "project_root / RUN_STATE_RELATIVE_PATH."
        ),
    )
    qa_evidence_root: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional explicit path to the qa-evidence root. None → "
            "project_root / _bmad-output/qa-evidence."
        ),
    )
    resolve_retry_rounds: bool = Field(
        default=False,
        description=(
            "When True, resolve every populated RetryAttemptRef into "
            "RetryRoundArtifacts via retry_history.resolve_retry_round. "
            "Default False keeps Story 8.5's enumeration cheap."
        ),
    )
    repo_root: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional explicit repo_root for retry-round resolution. "
            "None defaults to project_root."
        ),
    )
    story_doc_resolver: StoryDocResolver | None = Field(
        default=None,
        description=(
            "Optional StoryDocResolver injection for tests. None → "
            "default_story_doc_resolver at inspect-story time."
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


class StoryInspection(BaseModel):
    """The canonical inspection payload Story 8.5 projects from.

    Per epics.md:3318-3320 verbatim, Story 8.5's no-args listing calls
    :func:`inspect_story` per enumerated story-id and projects this
    payload to a row-summary shape (story-id, current state, marker
    count, last activity timestamp, branch name) per epics.md:3342.
    The projection-not-duplication invariant mirrors Story 6.4's
    per-specialist × per-retry cost being a projection of OTel events
    per epics.md:3320 verbatim.

    Frozen for hashability + immutability discipline (Pattern 4 / Epic 1
    retro Action #2). Field declaration order is load-bearing for
    byte-stable :meth:`model_dump_json` output (mirrors Story 5.5's
    :class:`RetryRoundArtifacts` and Story 2.2's :class:`RunState`
    discipline).

    Each :class:`RunState`-derived field is a direct passthrough (NOT a
    re-encoded subset). This passthrough discipline ensures schema-
    version evolution of :class:`RunState` (e.g., a hypothetical 1.4
    minor bump) extends :class:`StoryInspection` additively without
    restructuring.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    story_id: str
    current_state: CurrentState
    branch_name: str
    run_id: str
    dispatched_specialist: DispatchedSpecialist | None
    last_envelope: dict[str, Any] | None
    active_markers: tuple[str, ...]
    retry_history: tuple[RetryAttempt, ...]
    resolved_retry_rounds: tuple[RetryRoundArtifacts, ...] | None
    dangling_retry_round_refs: tuple[RetryAttemptRef, ...]
    run_state_path: pathlib.Path
    per_specialist_log_dir: pathlib.Path
    story_doc_path: pathlib.Path | None
    cost_to_date_by_specialist: CostToDateBySpecialist


_StatusAction = Literal["status-found", "status-no-run-state"]


class StatusOutcome(BaseModel):
    """Typed return of :func:`inspect_story`.

    Pattern 6 — frozen so the orchestrator skill cannot mutate the
    outcome between read and route.

    Attributes:
        action: One of two canonical actions per AC-1.
        inspection: Populated on ``status-found``; ``None`` on
            ``status-no-run-state``.
        diagnostic: ``None`` on ``status-found`` (silent success — the
            renderer formats the inspection); populated on
            ``status-no-run-state`` (the named-invariant diagnostic per
            AC-2).
    """

    model_config = ConfigDict(frozen=True)

    action: _StatusAction
    inspection: StoryInspection | None = None
    diagnostic: str | None = None


# --------------------------------------------------------------------------- #
# Pure functions                                                              #
# --------------------------------------------------------------------------- #


def render_no_run_state_diagnostic(
    request: StatusRequest, run_state_path: pathlib.Path
) -> str:
    """Pure deterministic formatter producing the AC-2 named-invariant
    diagnostic text.

    Mirrors :func:`resume_command.render_no_run_state_diagnostic` in
    shape but is structurally distinct — the no-run-state-status path
    is NOT a ``recovery-state-conflict`` marker AND the remediation
    pointers differ: status points at ``/bmad-automation run <story-id>``
    for fresh-start AND at ``/bmad-automation status`` (no-args, when
    Story 8.5 lands) for orphan-discovery. Diagnostic prefix is
    ``status: `` (NOT ``resume: ``).

    Composition (per AC-2 verbatim):

    1. ``status: `` literal prefix.
    2. ``no-in-flight-run-found-for-story-id`` named-invariant token.
    3. ``story_id: <story-id>`` clause.
    4. ``probed run-state path: <absolute-path>`` clause.
    5. ``remediation:`` clause naming TWO paths per epics.md:3325
       verbatim:
         (a) start a fresh run via ``/bmad-automation run <story-id>``;
         (b) verify the story-id matches an in-flight story by listing
         all stories via ``/bmad-automation status`` (Story 8.5 — when
         landed).
    """
    parts: list[str] = [
        f"status: no-in-flight-run-found-for-story-id: {request.story_id}",
        f"probed run-state path: {run_state_path!s}",
        (
            "remediation: "
            f"(a) start a fresh run via /bmad-automation run {request.story_id}, "
            "(b) verify the story-id matches an in-flight story by listing "
            "all stories via /bmad-automation status (Story 8.5 — when landed)"
        ),
    ]
    return "; ".join(parts)


def _project_per_specialist_log_dir(
    qa_evidence_root: pathlib.Path, story_id: str, run_id: str
) -> pathlib.Path:
    """Project the per-specialist log directory path per Story 2.6's
    ``LOG_PATH_TEMPLATE``.

    The template is ``{story_id}/{run_id}/logs/{specialist}-{attempt}.log``;
    the directory portion (the parent of all per-specialist log files)
    is ``<qa_evidence_root>/<story_id>/<run_id>/logs/``. THIS function
    computes the directory; it does NOT enumerate the directory's
    contents (NFR-O4 read-only invariant — keeping the surface narrow).

    The practitioner / Story 8.5 / a future test may inspect the
    directory directly via ``os.listdir`` or
    :meth:`pathlib.Path.iterdir` per the human render's pointer-clause.
    """
    return qa_evidence_root / story_id / run_id / "logs"


def _resolve_story_doc_path(
    request: StatusRequest,
) -> pathlib.Path | None:
    """Resolve the story-doc path via the request's resolver, returning
    ``None`` on any resolver failure per AC-3's graceful-degrade contract.

    Story-doc absence does NOT halt the inspection; the orphan-detection-
    by-marker path is Story 8.5's surface NOT THIS story's. Mirrors the
    "log-then-continue on resolver failure" precedent at Story 8.3's
    ``evaluate_recovery`` graceful-degrade path.
    """
    resolver = (
        request.story_doc_resolver
        if request.story_doc_resolver is not None
        else default_story_doc_resolver
    )
    try:
        resolution = resolver(request.story_id, request.project_root)
    except Exception as exc:  # noqa: BLE001 — graceful-degrade boundary
        # AC-3 graceful-degrade: any resolver failure (StoryDocNotFound,
        # StoryDocMalformed, OSError, etc.) yields story_doc_path=None.
        # The inspection still proceeds with run-state-derived fields.
        _logger.debug(
            "story-doc resolver failed for story_id=%r: %r — proceeding "
            "with story_doc_path=None per AC-3 graceful-degrade",
            request.story_id,
            exc,
        )
        return None
    return resolution.path


def _build_retry_attempt_refs(
    retry_history: tuple[RetryAttempt, ...],
) -> tuple[RetryAttemptRef, ...]:
    """Build a tuple of :class:`RetryAttemptRef` from the populated
    entries in ``retry_history``.

    Pre-Story-5.5 entries (entries where ``round_id is None`` OR
    ``path is None``) are SKIPPED — they cannot be resolved per the
    Story 5.5 contract. Mixed-history (some pre-5.5 + some post-5.5)
    is supported: only the populated entries are resolvable.
    """
    refs: list[RetryAttemptRef] = []
    for attempt in retry_history:
        if attempt.round_id is None or attempt.path is None:
            # Pre-Story-5.5 entry; cannot be resolved.
            continue
        refs.append(
            RetryAttemptRef(
                retry_attempt=attempt.retry_attempt,
                retry_reason=attempt.retry_reason,
                round_id=attempt.round_id,
                path=attempt.path,
            )
        )
    return tuple(refs)


# --------------------------------------------------------------------------- #
# inspect_story — canonical entry point                                       #
# --------------------------------------------------------------------------- #


def inspect_story(request: StatusRequest) -> StatusOutcome:
    """Canonical single-story inspection function per FR48 + NFR-O4.

    THIS is the function Story 8.5 imports + invokes per enumerated
    story-id per epics.md:3318-3320 verbatim. Pure-function-shaped (the
    only side effects are filesystem reads via
    :func:`_load_run_state_from_disk`,
    :func:`default_story_doc_resolver`, and conditionally
    :func:`resolve_retry_round`). NEVER mutates run-state, story-doc,
    sprint-status, per-specialist logs, events.jsonl, deferred-work.md,
    or the git working tree (the read-only invariant per NFR-O4
    verbatim).

    The two branches per AC-1:

    1. ``run-state file does NOT exist at the resolved path`` →
       ``status-no-run-state``. NO marker emitted; named-invariant
       diagnostic produced via :func:`render_no_run_state_diagnostic`.
       :func:`_load_run_state_from_disk` is NOT invoked.
    2. ``run-state file present`` → load run-state; resolve story-doc
       (graceful-degrade on failure); build :class:`StoryInspection`;
       conditionally resolve retry rounds; return ``status-found``.

    Args:
        request: The typed input.

    Returns:
        :class:`StatusOutcome`. ``inspection`` is populated on
        ``status-found``; ``diagnostic`` is populated on
        ``status-no-run-state``.

    Raises:
        StatusCommandError: When the run-state-path probe raised
            :class:`OSError` OR when
            :func:`_load_run_state_from_disk` raised
            :class:`CrossStateRecoveryError` (chained via ``from exc``).
    """
    run_state_path = (
        request.run_state_path
        if request.run_state_path is not None
        else request.project_root / RUN_STATE_RELATIVE_PATH
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

    # AC-2 — no-run-state pre-check + OSError guard.
    try:
        run_state_file_exists = run_state_path.is_file()
    except OSError as exc:
        raise StatusCommandError(
            reason="run-state-path-access-error",
            diagnostic=(
                f"status: harness-level error: cannot probe run-state path "
                f"{run_state_path!s}: {exc}"
            ),
        ) from exc
    if not run_state_file_exists:
        diagnostic = render_no_run_state_diagnostic(request, run_state_path)
        return StatusOutcome(
            action="status-no-run-state",
            inspection=None,
            diagnostic=diagnostic,
        )

    # AC-3 — load run-state via the private same-package helper per
    # Story 8.3's Dev's-call precedent (TWO consumers of the private
    # name; THIS story holds the line on promotion).
    try:
        run_state = _load_run_state_from_disk(run_state_path)
    except CrossStateRecoveryError as exc:
        raise StatusCommandError(
            reason="cross-state-recovery-substrate-error",
            diagnostic=str(exc),
        ) from exc

    # TOCTOU guard per AC-2: file deleted between is_file() and the
    # load returning None → treat as no-run-state (mirrors Story 8.3's
    # TOCTOU guard at resume_command.py:~656).
    if run_state is None:
        diagnostic = render_no_run_state_diagnostic(request, run_state_path)
        return StatusOutcome(
            action="status-no-run-state",
            inspection=None,
            diagnostic=diagnostic,
        )

    # Story-id mismatch guard: the loaded file may belong to a different
    # story (e.g., when run_state_path defaults to the canonical path and
    # another story's run-state is resident there). Return status-no-run-state
    # rather than returning status-found with contaminated data.
    if run_state.story_id != request.story_id:
        diagnostic = render_no_run_state_diagnostic(request, run_state_path)
        return StatusOutcome(
            action="status-no-run-state",
            inspection=None,
            diagnostic=diagnostic,
        )

    # AC-3 — story-doc resolution with graceful-degrade.
    story_doc_path = _resolve_story_doc_path(request)

    # AC-3 — retry-round resolution (conditional).
    resolved_retry_rounds: tuple[RetryRoundArtifacts, ...] | None
    dangling_retry_round_refs: tuple[RetryAttemptRef, ...]
    if request.resolve_retry_rounds:
        refs = _build_retry_attempt_refs(run_state.retry_history)
        if refs:
            try:
                pre_detected_dangling: tuple[RetryAttemptRef, ...] = detect_dangling_refs(
                    refs=refs, repo_root=repo_root
                )
            except OSError as exc:
                raise StatusCommandError(
                    reason="retry-history-access-error",
                    diagnostic=(
                        f"status: harness-level error: cannot probe retry-round "
                        f"artifact paths: {exc}"
                    ),
                ) from exc
            dangling_set = set(pre_detected_dangling)
            toctou_dangling: list[RetryAttemptRef] = []
            resolved_list: list[RetryRoundArtifacts] = []
            for ref in refs:
                if ref in dangling_set:
                    continue
                try:
                    resolved_list.append(
                        resolve_retry_round(ref=ref, repo_root=repo_root)
                    )
                except DanglingRetryRoundRef:
                    # TOCTOU: artifact present during detect_dangling_refs
                    # but deleted before resolve_retry_round. Classify as
                    # dangling so it surfaces structurally rather than
                    # disappearing into the gap between resolved + dangling.
                    toctou_dangling.append(ref)
                except RetryHistoryError as exc:
                    # Corrupted-but-present artifact (parse / schema
                    # failure). Per AC-10 + NFR-O4: do NOT raise, do
                    # NOT emit a marker; surface structurally by
                    # logging at DEBUG and skipping the round.
                    # Practitioners see the corruption via the dangling
                    # block (corruption is NOT classified as dangling
                    # per Story 5.5 detect_dangling_refs's contract,
                    # so corrupted-but-present artifacts surface in
                    # neither resolved nor dangling fields — they
                    # inhabit the gap by design).
                    _logger.debug(
                        "retry-round artifact %r failed to resolve: %r — "
                        "skipping per NFR-O4 read-only invariant",
                        ref.path,
                        exc,
                    )
                    continue
            dangling_retry_round_refs = pre_detected_dangling + tuple(toctou_dangling)
            resolved_retry_rounds = tuple(resolved_list)
        else:
            # Empty retry_history OR all-pre-5.5 entries — empty tuples
            # for both fields; no resolution attempted.
            resolved_retry_rounds = ()
            dangling_retry_round_refs = ()
    else:
        resolved_retry_rounds = None
        dangling_retry_round_refs = ()

    inspection = StoryInspection(
        story_id=request.story_id,
        current_state=run_state.current_state,
        branch_name=run_state.branch_name,
        run_id=run_state.run_id,
        dispatched_specialist=run_state.dispatched_specialist,
        last_envelope=run_state.last_envelope,
        active_markers=run_state.active_markers,
        retry_history=run_state.retry_history,
        resolved_retry_rounds=resolved_retry_rounds,
        dangling_retry_round_refs=dangling_retry_round_refs,
        run_state_path=run_state_path,
        per_specialist_log_dir=_project_per_specialist_log_dir(
            qa_evidence_root, request.story_id, run_state.run_id
        ),
        story_doc_path=story_doc_path,
        cost_to_date_by_specialist=run_state.cost_to_date_by_specialist,
    )
    return StatusOutcome(
        action="status-found",
        inspection=inspection,
        diagnostic=None,
    )


# --------------------------------------------------------------------------- #
# Renderers (pure deterministic formatters)                                   #
# --------------------------------------------------------------------------- #


def render_story_inspection_human(inspection: StoryInspection) -> str:
    """Pure deterministic formatter producing the AC-4 human-readable
    terminal output.

    Section structure mirrors Story 6.1's loud-fail block style for the
    marker section AND Story 5.8's escalation-bundle structure for the
    retry-history section per epics.md:3315 verbatim. Byte-stable on
    identical input (the AC-9 purity contract).

    Sections (in order):

    1. Heading: ``# /bmad-automation status — story <story-id>``
    2. ``## Lifecycle state``
    3. ``## Active loud-fail markers`` (alphabetical via
       :func:`compute_alphabetical_marker_order`)
    4. ``## Retry history`` (mirrors
       :func:`bundle_assembly_escalation._render_retry_history`)
    5. ``## Latest specialist envelope``
    6. ``## Cost-to-date by specialist``
    """
    lines: list[str] = []
    lines.append(f"# /bmad-automation status — story {inspection.story_id}")
    lines.append("")

    # --- Lifecycle state ---
    lines.append("## Lifecycle state")
    lines.append("")
    lines.append(f"state: {inspection.current_state}")
    lines.append(f"branch: {inspection.branch_name}")
    lines.append(f"run_id: {inspection.run_id}")
    lines.append(f"run_state_path: {inspection.run_state_path!s}")
    story_doc_value = (
        str(inspection.story_doc_path)
        if inspection.story_doc_path is not None
        else "(unresolved)"
    )
    lines.append(f"story_doc: {story_doc_value}")
    lines.append("")

    # --- Active loud-fail markers ---
    lines.append("## Active loud-fail markers")
    lines.append("")
    if not inspection.active_markers:
        lines.append("(no active markers)")
    else:
        for marker in compute_alphabetical_marker_order(inspection.active_markers):
            lines.append(f"- {marker}")
    lines.append("")

    # --- Retry history ---
    lines.append("## Retry history")
    lines.append("")
    if not inspection.retry_history:
        lines.append("(no retries — story has not entered the retry seam)")
    else:
        # Index resolved rounds by round_id for in-line annotation.
        resolved_index: dict[str, RetryRoundArtifacts] = {}
        if inspection.resolved_retry_rounds is not None:
            resolved_index = {
                r.round_id: r for r in inspection.resolved_retry_rounds
            }
        # Index dangling refs by round_id.
        dangling_round_ids: set[str] = {
            ref.round_id for ref in inspection.dangling_retry_round_refs
        }
        for attempt in inspection.retry_history:
            lines.append(
                f"- attempt {attempt.retry_attempt} — {attempt.retry_reason}"
            )
            if attempt.round_id is not None and attempt.path is not None:
                if attempt.round_id in dangling_round_ids:
                    lines.append(
                        f"  - ({attempt.round_id} — DANGLING: {attempt.path})"
                    )
                elif attempt.round_id in resolved_index:
                    rr = resolved_index[attempt.round_id]
                    lines.append(
                        f"  - {attempt.round_id} → {attempt.path} "
                        f"(findings_count={len(rr.findings)})"
                    )
                else:
                    lines.append(
                        f"  - {attempt.round_id} → {attempt.path}"
                    )
    lines.append("")

    # --- Latest specialist envelope ---
    lines.append("## Latest specialist envelope")
    lines.append("")
    dispatched_value = (
        inspection.dispatched_specialist
        if inspection.dispatched_specialist is not None
        else "(none)"
    )
    lines.append(f"dispatched_specialist: {dispatched_value}")
    if inspection.last_envelope is not None:
        envelope_status = inspection.last_envelope.get("status", "(unknown)")
        lines.append(f"envelope_status: {envelope_status}")
        # Truncated JSON dump (200 chars) per AC-4. Use sort_keys for
        # byte-stable output.
        try:
            envelope_json = json.dumps(inspection.last_envelope, sort_keys=True)
        except (TypeError, ValueError):
            envelope_json = "(envelope not JSON-serializable)"
        if len(envelope_json) > 200:
            envelope_json = envelope_json[:200] + "…"
        lines.append(f"envelope_preview: {envelope_json}")
    else:
        lines.append("envelope_status: (no envelope recorded)")
    lines.append(
        f"per_specialist_log_dir: {inspection.per_specialist_log_dir!s} "
        "(inspect via filesystem for full per-specialist envelope history)"
    )
    lines.append("")

    # --- Cost-to-date by specialist ---
    lines.append("## Cost-to-date by specialist")
    lines.append("")
    cost = inspection.cost_to_date_by_specialist
    for label, value in (
        ("dev", cost.dev),
        ("review-bmad", cost.review_bmad),
        ("qa", cost.qa),
        ("lad", cost.lad),
    ):
        rendered = "(none)" if value is None else f"{value}"
        lines.append(f"- {label}: {rendered}")

    return "\n".join(lines)


def render_story_inspection_json(inspection: StoryInspection) -> str:
    """Pure deterministic JSON formatter producing the AC-5
    machine-consumable output.

    Uses :meth:`StoryInspection.model_dump_json` with ``indent=2`` per
    Pydantic v2's canonical serialization. Field declaration order is
    load-bearing for byte-stable output (mirrors
    :class:`resume_command.ResumeOutcome`'s frozen-Pydantic discipline).
    :class:`pathlib.Path` fields serialize as posix-style strings on
    POSIX hosts (Pydantic v2 default for ``Path``).

    Round-trip: ``StoryInspection.model_validate_json(rendered)`` →
    ``render_story_inspection_json(inspection)`` is byte-stable on the
    same instance (deterministic field ordering via frozen model).
    """
    return inspection.model_dump_json(indent=2)


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bmad-automation-status",
        description=(
            "/bmad-automation status <story-id> substrate (Story 8.4, "
            "FR48 + NFR-O4). Read-only single-story inspection: loads "
            "run-state via Story 8.2's _load_run_state_from_disk helper, "
            "resolves retry rounds via Story 5.5's "
            "retry_history.resolve_retry_round (when --resolve-retry-rounds "
            "is set OR --json is set), projects per-specialist log dir "
            "via Story 2.6's LOG_PATH_TEMPLATE. Halts on no-run-state with "
            "a named-invariant diagnostic."
        ),
    )
    parser.add_argument(
        "story_id",
        type=str,
        help=(
            "BMAD story identifier (e.g., '8-3'); matches the story-doc "
            "filename prefix under _bmad-output/implementation-artifacts/."
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
        "--run-state-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Optional explicit path to the run-state file. Defaults to "
            "<project_root>/_bmad/automation/run-state.yaml."
        ),
    )
    parser.add_argument(
        "--qa-evidence-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Optional explicit path to the qa-evidence root. Defaults to "
            "<project_root>/_bmad-output/qa-evidence."
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
            "render. Implies --resolve-retry-rounds."
        ),
    )
    parser.add_argument(
        "--resolve-retry-rounds",
        action="store_true",
        dest="resolve_retry_rounds",
        help=(
            "Resolve every populated RetryAttemptRef into "
            "RetryRoundArtifacts (default OFF to keep Story 8.5's "
            "enumeration cheap; auto-ON when --json is set)."
        ),
    )
    parser.add_argument(
        "--background-agents-json",
        type=pathlib.Path,
        default=None,
        dest="background_agents_json",
        help=(
            "Optional path to a file containing the captured `claude agents "
            "--json --all` output (Story 21.2 / FR-P2-7). When provided, the "
            "status command appends a '## Background runs' section reconciling "
            "each background run against git ground-truth and emitting the "
            "background-primitive-unstable marker on the unconfirmable-on-"
            "resume path. Omitted → no background-runs section (bit-identical "
            "to the pre-Story-21.2 output)."
        ),
    )
    return parser


def _render_background_runs_for_cli(
    agents_json_path: pathlib.Path,
    *,
    repo_root: pathlib.Path,
) -> str:
    """Read the captured ``claude agents --json`` file, reconcile against git
    ground-truth, and render the ``## Background runs`` section (Story 21.2 AC-6).

    The marker emission flows through the discovery-surface recorder
    (:func:`background_dispatch._default_background_runs_recorder`), NOT a
    run-state write — status stays read-only against run-state contents.
    """
    raw = json.loads(agents_json_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise StatusCommandError(
            reason="background-agents-json-not-a-list",
            diagnostic=(
                f"status: harness-level error: {agents_json_path} must contain a "
                f"JSON array (the `claude agents --json` output); got "
                f"{type(raw).__name__}"
            ),
        )
    registry = load_marker_class_registry()
    roster = reconcile_background_runs(
        raw,
        git_ground_truth_probe=make_git_ground_truth_probe(repo_root=repo_root),
        marker_recorder=_default_background_runs_recorder,
        marker_registry=registry,
    )
    return render_background_runs_section(roster)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point invoked by the orchestrator skill's
    ``steps/status.md`` runtime protocol per AC-7.

    Exit codes per AC-1:
        * ``0`` — ``status-found`` (silent success; the rendered
          inspection is printed to stdout).
        * ``1`` — ``status-no-run-state`` (halt with diagnostic to
          stderr).
        * ``2`` — harness-level error inside the substrate per
          Pattern 5 (Pydantic model construction failure, run-state
          access failure, recovery substrate unexpected exception).

    The 0-vs-1 split mirrors Story 8.3's ``bmad-automation-resume`` CLI
    semantics (resume's ``resume-dispatch`` ↔ status's ``status-found``;
    resume's ``resume-no-run-state`` ↔ status's ``status-no-run-state``).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    project_root = (
        args.project_root if args.project_root is not None else pathlib.Path.cwd()
    )
    if not project_root.is_absolute():
        project_root = project_root.resolve()

    # AC-5: --json IMPLIES --resolve-retry-rounds=True.
    resolve_retry_rounds = bool(args.resolve_retry_rounds) or bool(args.json_flag)

    try:
        request = StatusRequest(
            project_root=project_root,
            story_id=args.story_id,
            run_state_path=args.run_state_path,
            qa_evidence_root=args.qa_evidence_root,
            repo_root=args.repo_root,
            resolve_retry_rounds=resolve_retry_rounds,
        )
    except (ValueError, ValidationError) as exc:
        print(f"status: harness-level error: {exc}", file=sys.stderr)
        return 2

    try:
        outcome = inspect_story(request)
    except StatusCommandError as exc:
        print(f"status: harness-level error: {exc}", file=sys.stderr)
        return 2

    # Story 21.2 / FR-P2-7: optionally append the background-runs section,
    # reconciled against git ground-truth (read-only). Incompatible with --json
    # (the JSON schema is stable and does not include the background-runs section;
    # combining both flags would silently suppress the reconciliation and the
    # background-primitive-unstable emission — a loud-fail violation).
    background_section: str | None = None
    if args.background_agents_json is not None:
        if args.json_flag:
            print(
                "status: --background-agents-json is incompatible with --json: "
                "the JSON output schema does not include the background-runs "
                "section; omit --json to get the reconciled human-readable output "
                "with background-primitive-unstable marker emission",
                file=sys.stderr,
            )
            return 2
        try:
            background_section = _render_background_runs_for_cli(
                args.background_agents_json, repo_root=project_root
            )
        except (StatusCommandError, OSError, ValueError) as exc:
            print(f"status: harness-level error: {exc}", file=sys.stderr)
            return 2

    if outcome.action == "status-found":
        if outcome.inspection is None:
            print(
                "status: harness-level error: status-found outcome has "
                "inspection=None — substrate contract violated",
                file=sys.stderr,
            )
            return 2
        if args.json_flag:
            print(render_story_inspection_json(outcome.inspection))
        else:
            print(render_story_inspection_human(outcome.inspection))
            if background_section is not None:
                print("")
                print(background_section)
        return 0

    # outcome.action == "status-no-run-state"
    if outcome.diagnostic is not None:
        print(outcome.diagnostic, file=sys.stderr)
    if background_section is not None:
        print(background_section)
    return 1
