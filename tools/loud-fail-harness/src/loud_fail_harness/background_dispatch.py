"""Story 21.2 — Background / fire-and-forget execution (the ``partial`` surface) — FR-P2-7.

The substrate library backing the reduced ``partial`` surface the Story 21.1
spike selected (verdict ``partially-stable`` → path ``partial``;
``docs/research-spikes/2026-06-17-background-primitive-stability.md``). It owns
three seams:

1. **Daemon-backed dispatch (AC-5).** :func:`build_background_dispatch_command`
   constructs the ``claude --bg …`` argv for dispatching the whole story loop as
   a detached, daemon-backed Claude Code background session. It builds; it does
   NOT execute — an injected launcher executes, so the seam is unit-testable
   without spawning a daemon. :func:`dispatch_run` is the flag-gated composition:
   ``background_execution: true`` → build + launch the detached session and
   return a non-blocking confirmation; ``false`` → the existing foreground loop,
   bit-identical. **CRITICAL** — the in-session ``Agent`` ``run_in_background``
   subagent path is explicitly NOT used; that is the ``#63023`` silent-data-loss
   path the spike rejected. This module never imports or references the Agent
   tool.

2. **Status reconciliation + loud-fail marker (AC-6).**
   :func:`reconcile_background_runs` consumes the parsed ``claude agents --json``
   output AS INJECTED DATA and cross-checks each background run against git
   ground-truth (an injected probe). Each run is classified ``in-flight`` /
   ``completed-confirmed`` / ``unconfirmable``; for every ``unconfirmable`` run
   it emits :data:`BACKGROUND_PRIMITIVE_UNSTABLE_MARKER` via the injected
   ``marker_recorder`` — the discovery-surface emission pattern of Story 8.5's
   ``orphan-run-state-detected`` (:mod:`loud_fail_harness.multi_story_status`),
   NOT a run-state mutation. Status stays read-only against run-state contents.

3. **Re-entrancy guard (AC-5).** The dispatched child re-enters
   ``/bmad-automation run <story-id>`` carrying :data:`BACKGROUND_REENTRY_FLAG`;
   the run protocol recognizes the flag (:func:`is_background_reentry`) and runs
   the real foreground loop with background dispatch disabled, so the detached
   session does not recurse.

Sensor-not-advisor (Pattern 5 + the spike's ``partial`` posture): the marker
SURFACES the unconfirmable run; it does NOT auto-recover, re-dispatch, or flip
``ac_results`` / wrapper ``status`` / run lifecycle state. Pattern 5
defence-in-depth: :func:`validate_marker_emission` runs BEFORE every marker
record; a registry rejection raises
:exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`.

Boundaries (Story 21.2 AC-9): a new harness module — NOT a sixth substrate
component, NOT a specialist, NOT a hook. It imports nothing across the
runtime↔harness pluggability boundary.
"""

from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loud_fail_harness.branch_lifecycle import _branch_name_for_story
from loud_fail_harness.input_hardening import harden_identifier
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

_logger = logging.getLogger(__name__)

#: The marker class emitted when a background run cannot be confirmed landed on
#: resume. Consumed AS-IS from ``schemas/marker-taxonomy.yaml`` (PATCH bump 1.17
#: → 1.18, closed-set 41 → 42; Story 21.2); THIS module is its sole runtime
#: emitter. Mirrors the constant-declaration pattern of
#: :data:`loud_fail_harness.qa_flakiness_threshold.FLAKINESS_THRESHOLD_EXCEEDED_MARKER`.
BACKGROUND_PRIMITIVE_UNSTABLE_MARKER: Final[
    Literal["background-primitive-unstable"]
] = "background-primitive-unstable"

#: Re-entrancy sentinel appended to the dispatched child's slash-command prompt.
#: The run protocol (``skills/bmad-automation/steps/run.md``) recognizes it and
#: forces the foreground loop so the detached background session does not recurse.
BACKGROUND_REENTRY_FLAG: Final[str] = "--foreground"

#: Default Claude Code executable name for the dispatch argv.
_DEFAULT_CLAUDE_EXECUTABLE: Final[str] = "claude"

#: Background-agent states (compared lowercased) that mean the run is still in
#: flight — no confirmation is owed yet, so no marker fires.
_IN_FLIGHT_STATES: Final[frozenset[str]] = frozenset(
    {
        "running",
        "in_progress",
        "in-progress",
        "queued",
        "pending",
        "waiting",
        "active",
        "starting",
        "dispatched",
    }
)

#: Background-agent states (compared lowercased) that mean the run claims to be
#: finished — ground-truth confirmation is required before it counts as landed.
_COMPLETED_STATES: Final[frozenset[str]] = frozenset(
    {
        "completed",
        "complete",
        "done",
        "succeeded",
        "success",
        "finished",
    }
)

#: Session JSON string fields scanned (in order) to recover the BMAD story-id
#: from the dispatched ``/bmad-automation run <story-id>`` prompt when the
#: session carries no explicit ``story_id``.
_STORY_ID_SOURCE_FIELDS: Final[tuple[str, ...]] = (
    "story_id",
    "storyId",
    "prompt",
    "title",
    "name",
    "description",
    "task",
)

_RUN_COMMAND_RE: Final[re.Pattern[str]] = re.compile(
    r"/bmad-automation\s+run\s+(?P<story_id>[A-Za-z0-9][A-Za-z0-9._-]*)"
)

#: Accepted story-id format: must start with an alphanumeric char and contain
#: only alphanumerics, dots, underscores, and hyphens. Mirrors the capture group
#: in ``_RUN_COMMAND_RE`` and the dispatch-prompt shape produced by
#: ``build_background_dispatch_command``. Enforced on the dispatch path (prevents
#: spaces / flag prefixes from corrupting the re-entrant child's prompt) and on
#: the JSON-ingress explicit-field path (prevents ``../../`` traversal tokens
#: from reaching ``_branch_name_for_story``).
_STORY_ID_FORMAT_RE: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
)

#: ``claude agents --json`` registry probe: returns the parsed JSON array. Thin
#: caller-supplied seam so reconciliation is unit-testable without a daemon.
AgentsJsonProbe = Callable[[], Sequence[Mapping[str, Any]]]

#: Discovery-surface marker recorder. Mirrors
#: :data:`loud_fail_harness.multi_story_status.MarkerRecorder` byte-for-byte.
MarkerRecorder = Callable[[str, Mapping[str, Any]], None]

#: Detached-session launcher: receives the built argv, executes it (production),
#: or records it (tests). Returns whatever the caller wants to surface.
BackgroundLauncher = Callable[[Sequence[str]], Any]

#: Foreground-loop thunk: runs the real six-step ``run_story_loop_entry`` when
#: background dispatch is off (or on the re-entrant child). Returns its result.
ForegroundRunner = Callable[[], Any]

BackgroundRunClassification = Literal[
    "in-flight", "completed-confirmed", "unconfirmable"
]


# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class BackgroundAgentSession(BaseModel):
    """One parsed ``claude agents --json`` array element.

    Frozen; field declaration order load-bearing for byte-stable
    ``model_dump_json()`` output. ``story_id`` is the BMAD story the session was
    dispatched for (parsed from the session's recorded dispatch prompt when not
    carried explicitly); ``None`` when it cannot be recovered — which is itself
    an ``unconfirmable`` signature (the run's work cannot be located).
    """

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(min_length=1)
    state: str = Field(min_length=1)
    story_id: str | None = None
    waiting_for: str | None = None

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> "BackgroundAgentSession":
        """Input-hardening (Story 24.2 discipline). ``story_id`` is the genuine
        external-ingress identifier — it traces back to the operator's
        ``/bmad-automation run <story-id>`` invocation recovered from the
        session's dispatch prompt — so reject whitespace-only / embedded-newline
        / null-byte values. ``session_id`` / ``state`` / ``waiting_for`` are
        daemon-generated status tokens (not operator identifiers), so they are
        NOT routed through the identifier hardener.
        """
        if self.story_id is not None:
            harden_identifier(self.story_id, "BackgroundAgentSession.story_id")
        return self


class GitGroundTruth(BaseModel):
    """The git ground-truth a probe reports for one background run's story.

    ``branch_exists`` — the per-story branch is present in the repo.
    ``has_landed_commits`` — that branch points at real work (≥1 commit). A
    completed session whose branch is absent OR carries no commits is the
    ``#63023`` silent-loss signature.
    """

    model_config = ConfigDict(frozen=True)

    branch_exists: bool
    has_landed_commits: bool


#: Git ground-truth probe: maps a background session to its git landed-state.
GitGroundTruthProbe = Callable[[BackgroundAgentSession], GitGroundTruth]


class ReconciledBackgroundRun(BaseModel):
    """One reconciled background run (a row of the roster).

    Frozen; field declaration order load-bearing. ``marker_emitted`` records
    whether THIS run triggered a ``background-primitive-unstable`` emission
    (True iff ``classification == "unconfirmable"``).
    """

    model_config = ConfigDict(frozen=True)

    session_id: str
    story_id: str | None
    state: str
    classification: BackgroundRunClassification
    marker_emitted: bool


class BackgroundRunRoster(BaseModel):
    """The reconciled roster of all background runs (AC-6 return shape)."""

    model_config = ConfigDict(frozen=True)

    runs: tuple[ReconciledBackgroundRun, ...]


class BackgroundDispatchResult(BaseModel):
    """The flag-gated return of :func:`dispatch_run` (AC-5).

    ``arbitrary_types_allowed`` so ``launch_result`` / ``foreground_result`` can
    carry whatever the injected launcher / foreground runner returned (a real
    ``RunStoryLoopEntryResult`` in production, a stub in tests) without coupling
    this module to those types.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    mode: Literal["background", "foreground"]
    command: tuple[str, ...] | None = None
    confirmation: str | None = None
    launch_result: object | None = None
    foreground_result: object | None = None


# --------------------------------------------------------------------------- #
# Dispatch seam (AC-5)                                                        #
# --------------------------------------------------------------------------- #


def build_background_dispatch_command(
    story_id: str,
    *,
    project_root: Any,
    claude_executable: str = _DEFAULT_CLAUDE_EXECUTABLE,
    extra_args: Sequence[str] = (),
) -> tuple[str, ...]:
    """Build the ``claude --bg …`` argv that dispatches the story loop as a
    detached, daemon-backed background session (AC-5).

    Pure (no exec): the returned argv is handed to an injected launcher. The
    dispatched prompt re-enters ``/bmad-automation run <story-id>`` carrying
    :data:`BACKGROUND_REENTRY_FLAG` so the detached child runs the real
    foreground loop and does not recurse.

    **NOT the in-session ``Agent run_in_background`` path** — that is the
    ``anthropics/claude-code#63023`` silent-data-loss path the Story 21.1 spike
    rejected. This builder constructs ONLY the daemon-backed ``claude --bg``
    surface the spike verified functional at Claude Code 2.1.179.

    Args:
        story_id: BMAD story identifier (external ingress → hardened).
        project_root: Project root the detached session is granted access to via
            ``--add-dir`` and runs under.
        claude_executable: Executable name/path (overridable for tests).
        extra_args: Additional flags inserted before the prompt (e.g.
            ``--permission-mode`` / ``--model``); forwarded verbatim.
    """
    safe_story_id = harden_identifier(story_id, "background_dispatch.story_id")
    if not _STORY_ID_FORMAT_RE.match(safe_story_id):
        raise ValueError(
            f"background_dispatch.story_id: invalid format {safe_story_id!r} — "
            f"must match [A-Za-z0-9][A-Za-z0-9._-]* (no spaces, leading dashes, "
            f"or path-traversal tokens); set background_execution: false for a "
            f"foreground run, or correct the story-id before dispatching"
        )
    prompt = f"/bmad-automation run {safe_story_id} {BACKGROUND_REENTRY_FLAG}"
    return (
        claude_executable,
        "--bg",
        "--add-dir",
        str(project_root),
        *tuple(extra_args),
        prompt,
    )


def build_background_dispatch_confirmation(story_id: str) -> str:
    """Build the non-blocking confirmation returned after a background dispatch.

    Directs the operator to ``/bmad-automation status`` (the surface that
    reconciles the run against git ground-truth and emits the loud-fail marker
    on the unconfirmable-on-resume path).
    """
    safe_story_id = harden_identifier(story_id, "background_dispatch.story_id")
    return (
        f"background-dispatched: story {safe_story_id} dispatched as a detached "
        f"Claude Code background session (claude --bg). The terminal is NOT "
        f"blocked. Inspect progress + landed state via "
        f"`/bmad-automation status {safe_story_id}` (background runs are "
        f"reconciled against git ground-truth; a background-primitive-unstable "
        f"marker surfaces if the run cannot be confirmed landed on resume)."
    )


def is_background_reentry(args: Sequence[str]) -> bool:
    """Return ``True`` iff ``args`` carries the re-entrancy sentinel.

    The run protocol calls this on the child invocation's argument list; a
    ``True`` result forces the foreground loop (background dispatch disabled) so
    the detached session does not recurse.
    """
    return BACKGROUND_REENTRY_FLAG in tuple(args)


def decide_dispatch_mode(
    *,
    background_execution: bool,
    background_reentry: bool,
) -> Literal["background", "foreground"]:
    """Pure gate: ``background`` iff background execution is on AND this is not
    the re-entrant child; ``foreground`` otherwise."""
    if background_execution and not background_reentry:
        return "background"
    return "foreground"


def dispatch_run(
    story_id: str,
    *,
    project_root: Any,
    background_execution: bool,
    launcher: BackgroundLauncher,
    foreground_runner: ForegroundRunner,
    background_reentry: bool = False,
    claude_executable: str = _DEFAULT_CLAUDE_EXECUTABLE,
    extra_args: Sequence[str] = (),
) -> BackgroundDispatchResult:
    """Flag-gated story-loop dispatch (AC-5).

    ``background_execution: true`` (and not a re-entrant child) → build the
    ``claude --bg`` argv, hand it to ``launcher`` (the foreground loop is NOT
    run), and return a non-blocking confirmation. Otherwise → invoke
    ``foreground_runner`` (the existing six-step loop) and return its result.
    When ``background_execution`` is ``False`` the path is bit-identical to the
    foreground loop: no argv built, ``launcher`` never called.
    """
    mode = decide_dispatch_mode(
        background_execution=background_execution,
        background_reentry=background_reentry,
    )
    if mode == "background":
        command = build_background_dispatch_command(
            story_id,
            project_root=project_root,
            claude_executable=claude_executable,
            extra_args=extra_args,
        )
        launch_result = launcher(command)
        return BackgroundDispatchResult(
            mode="background",
            command=command,
            confirmation=build_background_dispatch_confirmation(story_id),
            launch_result=launch_result,
        )
    foreground_result = foreground_runner()
    return BackgroundDispatchResult(
        mode="foreground",
        foreground_result=foreground_result,
    )


# --------------------------------------------------------------------------- #
# Status reconciliation + marker emission (AC-6)                              #
# --------------------------------------------------------------------------- #


def _extract_story_id(entry: Mapping[str, Any]) -> str | None:
    """Recover the BMAD story-id from a ``claude agents --json`` element.

    Prefers an explicit ``story_id`` / ``storyId`` field; otherwise scans the
    session's recorded prompt/title/etc. for the dispatched
    ``/bmad-automation run <story-id>`` command. Returns ``None`` when no
    story-id can be recovered (an ``unconfirmable`` signature).
    """
    for field in _STORY_ID_SOURCE_FIELDS:
        value = entry.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        if field in ("story_id", "storyId"):
            candidate = value.strip()
            if not _STORY_ID_FORMAT_RE.match(candidate):
                _logger.warning(
                    "background_dispatch: explicit story_id field %r fails format "
                    "check — treating run as unconfirmable",
                    candidate,
                )
                return None
            return candidate
        match = _RUN_COMMAND_RE.search(value)
        if match is not None:
            return match.group("story_id")
    return None


def parse_background_agent_sessions(
    agents_json: Sequence[Mapping[str, Any]],
) -> tuple[BackgroundAgentSession, ...]:
    """Parse the ``claude agents --json`` array into typed sessions.

    Honors the spike's named field surface (``id`` / ``state`` / ``waitingFor``);
    entries missing ``id`` or ``state`` are skipped (a malformed registry row is
    not a story run). ``story_id`` is recovered via :func:`_extract_story_id`.
    """
    sessions: list[BackgroundAgentSession] = []
    for entry in agents_json:
        session_id = entry.get("id")
        state = entry.get("state")
        if not isinstance(session_id, str) or not session_id.strip():
            continue
        if not isinstance(state, str) or not state.strip():
            continue
        waiting_for = entry.get("waitingFor")
        sessions.append(
            BackgroundAgentSession(
                session_id=session_id.strip(),
                state=state.strip(),
                story_id=_extract_story_id(entry),
                waiting_for=(
                    waiting_for.strip()
                    if isinstance(waiting_for, str) and waiting_for.strip()
                    else None
                ),
            )
        )
    return tuple(sessions)


def _classify_run(
    session: BackgroundAgentSession,
    ground_truth: GitGroundTruth | None,
) -> BackgroundRunClassification:
    """Classify one background run.

    In-flight states → ``in-flight`` (no confirmation owed). A session whose
    daemon state claims completion (in ``_COMPLETED_STATES``) AND whose git
    ground-truth confirms the per-story branch landed with story-specific commits
    → ``completed-confirmed``. Everything else — including ``failed`` /
    ``cancelled`` / ``error`` / any unrecognized state — → ``unconfirmable``:
    uncertainty surfaces loudly per the loud-fail doctrine.
    """
    if session.state.lower() in _IN_FLIGHT_STATES:
        return "in-flight"
    if (
        session.state.lower() in _COMPLETED_STATES
        and ground_truth is not None
        and ground_truth.branch_exists
        and ground_truth.has_landed_commits
    ):
        return "completed-confirmed"
    return "unconfirmable"


def _build_unconfirmable_context(
    session: BackgroundAgentSession,
    ground_truth: GitGroundTruth | None,
) -> dict[str, Any]:
    """Build the marker context for a ``background-primitive-unstable`` emission.

    Carries the ``pointer_context_fields`` named in the taxonomy entry
    (``story_id`` / ``session_id``) plus the git signals + a remediation clause.
    """
    return {
        "story_id": session.story_id if session.story_id is not None else "<unknown>",
        "session_id": session.session_id,
        "agent_state": session.state,
        "git_branch_exists": (
            ground_truth.branch_exists if ground_truth is not None else False
        ),
        "git_has_landed_commits": (
            ground_truth.has_landed_commits if ground_truth is not None else False
        ),
        "remediation": (
            "inspect `claude agents --json --all` for the session's actual "
            "state; check the per-story branch / PR landed state directly with "
            "git; if the run was lost, re-dispatch the story (set "
            "background_execution: false for a foreground run, or re-issue the "
            "background dispatch)."
        ),
    }


def reconcile_background_runs(
    agents_json: Sequence[Mapping[str, Any]],
    *,
    git_ground_truth_probe: GitGroundTruthProbe,
    marker_recorder: MarkerRecorder,
    marker_registry: MarkerClassRegistry,
) -> BackgroundRunRoster:
    """Reconcile ``claude agents --json`` against git ground-truth (AC-6).

    Consumes the parsed agents-json AS INJECTED DATA (the live invocation is a
    thin caller-supplied probe). Each run is classified ``in-flight`` /
    ``completed-confirmed`` / ``unconfirmable``; for every ``unconfirmable`` run
    the helper validates the marker class against the registry (Pattern 5
    validate-first) and records :data:`BACKGROUND_PRIMITIVE_UNSTABLE_MARKER` via
    the injected ``marker_recorder`` — the Story 8.5 discovery-surface emission
    pattern, read-only against run-state. Silent on all confirmed / in-flight
    runs.

    Raises:
        UnknownMarkerClass: the registry does not contain the marker class —
            raised by :func:`validate_marker_emission` BEFORE any record, per
            Pattern 5 defence-in-depth.
    """
    sessions = parse_background_agent_sessions(agents_json)
    rows: list[ReconciledBackgroundRun] = []
    for session in sessions:
        ground_truth: GitGroundTruth | None = None
        if session.state.lower() not in _IN_FLIGHT_STATES:
            ground_truth = git_ground_truth_probe(session)
        classification = _classify_run(session, ground_truth)
        marker_emitted = False
        if classification == "unconfirmable":
            validate_marker_emission(
                marker_registry, BACKGROUND_PRIMITIVE_UNSTABLE_MARKER
            )
            marker_recorder(
                BACKGROUND_PRIMITIVE_UNSTABLE_MARKER,
                _build_unconfirmable_context(session, ground_truth),
            )
            marker_emitted = True
        rows.append(
            ReconciledBackgroundRun(
                session_id=session.session_id,
                story_id=session.story_id,
                state=session.state,
                classification=classification,
                marker_emitted=marker_emitted,
            )
        )
    return BackgroundRunRoster(runs=tuple(rows))


def _sanitize_display_token(token: str, max_len: int = 80) -> str:
    """Strip non-printable chars and truncate daemon-supplied status tokens.

    Prevents daemon-controlled ``state`` / ``session_id`` values from injecting
    control characters or the marker string literal into the rendered section.
    """
    return "".join(ch for ch in token if ch.isprintable() and ch not in "\r\n")[:max_len]


def render_background_runs_section(roster: BackgroundRunRoster) -> str:
    """Pure deterministic formatter for the ``## Background runs`` status section.

    Byte-stable on identical input. Lists each reconciled run with its
    classification; names the unconfirmable runs as carrying the loud-fail
    marker so it is greppable in the status / bundle output. Daemon-supplied
    ``session_id`` and ``state`` tokens are sanitized before interpolation.
    """
    lines: list[str] = ["## Background runs", ""]
    if not roster.runs:
        lines.append("(no background runs registered)")
        return "\n".join(lines)
    for run in roster.runs:
        story = run.story_id if run.story_id is not None else "<unknown>"
        safe_session_id = _sanitize_display_token(run.session_id)
        safe_state = _sanitize_display_token(run.state)
        suffix = (
            f" — {BACKGROUND_PRIMITIVE_UNSTABLE_MARKER}"
            if run.marker_emitted
            else ""
        )
        lines.append(
            f"- {safe_session_id} [story {story}] state={safe_state} "
            f"→ {run.classification}{suffix}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Default production probes / recorders                                       #
# --------------------------------------------------------------------------- #


def _default_background_runs_recorder(
    marker_class: str, context: Mapping[str, Any]
) -> None:
    """Default :data:`MarkerRecorder` — logs the emission at INFO.

    Mirrors :func:`loud_fail_harness.multi_story_status._default_marker_recorder`:
    production marker visibility for the discovery surface without a run-state
    write. Tests inject a list-appender stub to capture emissions structurally.
    """
    _logger.info("marker-emitted: %s context=%r", marker_class, dict(context))


def make_git_ground_truth_probe(
    *,
    repo_root: Any,
    base_ref: str = "main",
) -> GitGroundTruthProbe:
    """Build the production git-ground-truth probe (read-only).

    The returned probe derives the per-story branch name via
    :func:`loud_fail_harness.branch_lifecycle._branch_name_for_story` and runs
    two read-only ``git`` queries: ``git rev-parse --verify refs/heads/<branch>``
    (branch present) and ``git rev-list --count refs/heads/<base_ref>..refs/heads/<branch>``
    (story-specific commits — NOT total ancestry; a branch freshly cut off
    ``base_ref`` with no new commits counts 0 and is NOT confirmed). It mutates
    nothing (NFR-S3 / NFR-O4). Any git failure / unknown story-id →
    ``GitGroundTruth(False, False)`` so the run surfaces as ``unconfirmable`` —
    uncertainty fails loud, per the spike's "cannot be confirmed landed" framing.
    """

    def _probe(session: BackgroundAgentSession) -> GitGroundTruth:
        if session.story_id is None:
            return GitGroundTruth(branch_exists=False, has_landed_commits=False)
        branch = _branch_name_for_story(session.story_id)
        try:
            verify = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, ValueError) as exc:
            _logger.debug("git rev-parse failed for %s: %r", branch, exc)
            return GitGroundTruth(branch_exists=False, has_landed_commits=False)
        if verify.returncode != 0:
            return GitGroundTruth(branch_exists=False, has_landed_commits=False)
        try:
            count = subprocess.run(
                [
                    "git",
                    "rev-list",
                    "--count",
                    f"refs/heads/{base_ref}..refs/heads/{branch}",
                ],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, ValueError) as exc:
            _logger.debug("git rev-list failed for %s: %r", branch, exc)
            return GitGroundTruth(branch_exists=True, has_landed_commits=False)
        has_commits = count.returncode == 0 and count.stdout.strip().isdigit() and (
            int(count.stdout.strip()) > 0
        )
        return GitGroundTruth(branch_exists=True, has_landed_commits=has_commits)

    return _probe


__all__ = [
    "BACKGROUND_PRIMITIVE_UNSTABLE_MARKER",
    "BACKGROUND_REENTRY_FLAG",
    "AgentsJsonProbe",
    "BackgroundAgentSession",
    "BackgroundDispatchResult",
    "BackgroundLauncher",
    "BackgroundRunClassification",
    "BackgroundRunRoster",
    "ForegroundRunner",
    "GitGroundTruth",
    "GitGroundTruthProbe",
    "MarkerRecorder",
    "ReconciledBackgroundRun",
    "build_background_dispatch_command",
    "build_background_dispatch_confirmation",
    "decide_dispatch_mode",
    "dispatch_run",
    "is_background_reentry",
    "make_git_ground_truth_probe",
    "parse_background_agent_sessions",
    "reconcile_background_runs",
    "render_background_runs_section",
]
