"""Story-file locking protocol — Story 14.3 substrate-library.

Architectural placement (Story 14.2 ADR-009 Consequence 4 precedent +
ADR-003 Consequence 1 substrate-component closure at FIVE per
architecture.md lines 311-315): this module is a substrate-**library** —
sibling of :mod:`loud_fail_harness.branch_lifecycle` (Story 2.3),
:mod:`loud_fail_harness.run_state` (Story 2.2),
:mod:`loud_fail_harness.worktree_lifecycle` (Story 14.2),
:mod:`loud_fail_harness.story_doc_validator` (Story 1.10b), and the
five substrate-component modules (``envelope_validator``,
``event_validator``, ``reconciler``, ``enumeration_check``,
``fixture_coverage``). It is **NOT a sixth substrate component**. The
substrate-component count stays at FIVE; the harness library count
grows by one (this module).

Role in the Epic 14 substrate chain: Story 14.3 composes on top of
Story 14.2's ``worktree_lifecycle`` to provide the per-story
filesystem-coordination primitive that prevents concurrent BMAD-state
writes to the same story-doc when multiple worktrees run in parallel
(Epic 18 / FR-P2-4) OR when a crashed worktree leaves an orphaned lock
file on disk (NFR-R2 crash-recovery + NFR-R7 no-destructive-resume).
Story 14.3 enumerates the ``worktree-stale-lock`` marker class in
``schemas/marker-taxonomy.yaml`` (the PATCH bump 1.6 → 1.7), and
extends ``session_start_reattach`` with a fifth ``worktree-stale-lock-
detected`` branch firing on resume after a crashed worktree.

What this library provides:
    * **Public function** :func:`acquire_lock` — atomic create-or-fail via
      ``os.open(O_CREAT | O_EXCL | O_WRONLY)``; on collision, inspects
      the existing record and either raises
      :exc:`StoryFileLockContended` (live competitor) OR performs an
      atomic ``os.replace`` stale-takeover (dead PID OR age beyond
      threshold).
    * **Public function** :func:`release_lock` — idempotent on already-
      absent state; optionally pid-asserting via ``expected_pid``;
      raises :exc:`StoryFileLockReleaseConflict` only when the caller
      explicitly asserts ownership and the on-disk PID disagrees.
    * **Public function** :func:`inspect_lock` — defensive read-only
      probe; returns ``None`` on absence; returns a
      :class:`LockInspectionResult` carrying either ``record`` (clean
      parse) OR ``parse_error`` (one-line summary; never both).
    * **Public function** :func:`is_stale` — pure-function staleness
      predicate over a :class:`LockRecord`; two-arm evaluation
      (pid-not-alive OR age-exceeded); returns a
      :class:`StalenessVerdict` carrying the discriminator.
    * **Context manager** :func:`story_file_lock` — try/finally wrapper
      that calls :func:`acquire_lock` on entry and
      :func:`release_lock` (with ``expected_pid=os.getpid()``) on exit;
      release-conflict diagnostics are logged-to-stderr and the
      exception is suppressed inside the ``finally`` so the body's
      exception (if any) propagates per Python's standard semantics.
    * **Pydantic v2 frozen models** :class:`LockRecord` /
      :class:`LockAcquisitionResult` / :class:`LockReleaseResult` /
      :class:`LockInspectionResult` / :class:`StalenessVerdict` —
      Pattern 4 state-update discipline.
    * **Named-invariant exception hierarchy**
      :class:`StoryFileLockBlocked` →
      :class:`StoryFileLockContended` / :class:`StoryFileLockCorrupted`
      / :class:`StoryFileLockReleaseConflict` — Pattern 5 named-
      invariant diagnostic; all three pin
      ``marker_class="worktree-stale-lock"``.

What this library enforces:
    * **NFR-R2** (PRD line 946; crash recovery) — :func:`is_stale`'s
      pid-probe + age-threshold predicates surface mid-create / mid-
      cleanup residue from a crashed worktree; :func:`acquire_lock`'s
      stale-takeover path lets the recovery loop proceed atomically
      via ``os.replace`` (a single-write replacement; NEVER
      ``unlink``-then-``open`` which would open a race window).
    * **NFR-R7** (PRD line 951; no destructive resume) — the library
      is operator-decided at the SessionStart altitude: the marker
      emission is observability-only; the operator (NOT the substrate)
      decides whether to clear a stale lock at recovery time.
      :func:`acquire_lock`'s in-process stale-takeover IS the
      single-actor replacement allowed by the protocol — the
      SessionStart hook does NOT auto-clear, mirrors Story 14.2's
      no-auto-``--force`` posture per NFR-R3 + Pattern 5.
    * **NFR-R8** (PRD line 952; cross-state consistency) — the lock
      file is a coordination-primitive layered above story-doc
      (canonical) and run-state (cache); a stale lock does NOT corrupt
      either, it merely signals that a previous worktree's lifecycle
      did not complete cleanly. The categorical separation (story-doc /
      run-state / lock) is the load-bearing distinction.
    * **NFR-S3** (PRD line 971; banned-verb posture) — pure-Python
      filesystem operations only; ZERO :func:`subprocess.run` calls in
      this module. ``os.kill(pid, 0)`` is the canonical POSIX liveness
      probe (no signal sent; raises :exc:`ProcessLookupError` on dead
      pid).
    * **NFR-O5** (PRD line 984; named diagnostic per failure class) +
      **Pattern 5** (architecture.md lines 983-991) — three
      sub-classifications map 1:1 to :class:`StalenessVerdict.reason`
      (``pid-not-alive`` / ``age-exceeded``) + the corrupted-file
      branch (``corrupted-lock-file``). The taxonomy enumeration in
      ``schemas/marker-taxonomy.yaml`` (Story 14.3 PATCH bump) keeps
      the YAML and the in-code :class:`typing.Literal` in lock-step.
    * **Pattern 4** (state-update discipline) + **Epic 1 retro
      Action #2** (frozen + tuple) — every Pydantic v2 result model is
      ``model_config = ConfigDict(frozen=True)``.
    * **Pattern 6** (strict typing + dependency injection) —
      ``pid_probe`` + ``clock`` are keyword-only injection points with
      production defaults; tests inject deterministic stubs.

Sensor-not-advisor (PRD-level invariant + Pattern 5):

    The library RAISES typed exceptions
    (:exc:`StoryFileLockContended`, :exc:`StoryFileLockCorrupted`,
    :exc:`StoryFileLockReleaseConflict`) carrying
    ``marker_class="worktree-stale-lock"`` identifiers on the
    diagnostic path. It does NOT emit markers itself, does NOT log,
    does NOT print, does NOT auto-clear stale locks. Same posture as
    1.10b (``story_doc_validator``), 2.2 (``run_state``), 2.3
    (``branch_lifecycle``), and 14.2 (``worktree_lifecycle``). The
    calling specialist (``session_start_reattach`` per Story 14.3
    integration; Stories 14.4 / 15.x / 18.x for downstream consumers)
    EMITS the marker via :func:`marker_wiring.record_marker_with_context`.

``find_repo_root()`` discipline (Epic 1 retro Action #1):

    Epic 1 retrospective Challenge #1 flagged ``find_repo_root()``
    called at module import time. This module honors the discipline:
    ``find_repo_root()`` is NOT called at module top-level.
    :func:`acquire_lock` / :func:`release_lock` / :func:`inspect_lock`
    / :func:`story_file_lock` each take ``repo_root: pathlib.Path |
    None = None`` from the caller; if ``None``, the helper computes it
    lazily via :func:`_default_repo_root` (which calls
    ``find_repo_root()`` at function-call time, not at import time).
    Tests use ``tmp_path`` fixtures that supply ``repo_root``
    explicitly.

FR62 pluggability classification:

    This module is *substrate-shared library* per the precedent of
    Stories 1.10b / 2.2 / 2.3 / 14.2. The FR62 gate (Story 1.10a's
    :mod:`loud_fail_harness.pluggability_gate`) flags cross-references
    between specialist subagents (Dev, Review-BMAD, QA, LAD under
    ``agents/*.md``); it does NOT flag substrate cross-imports. The
    ``session_start_reattach → story_file_lock`` direction (Story 14.3
    integration) is structurally permitted. The REVERSE direction
    (``story_file_lock → session_start_reattach``) is FORBIDDEN —
    would create a cycle and would couple the locking primitive to
    SessionStart's emission seam.

Forward-compat consumers:

    Stories that will consume this library exclusively (no direct
    filesystem-lock-form invocation outside this module's public
    surface — Pattern 5 + NFR-S3 enforcement):

        * Story 14.4 — epic-run-state schema with per-worktree
          run-state addressing: composes :func:`acquire_lock` /
          :func:`release_lock` on the per-worktree run-state write
          path.
        * Story 14.5 — parallel-story state-pollution marker: uses
          :func:`inspect_lock` to distinguish live-competitor writes
          from cross-worktree pollution.
        * Story 14.6 — Epic-14 reference fixture: end-to-end witness
          of acquire + crash + recovery + release cycle.
        * Epic 15 — sequential epic orchestration: composes
          :func:`story_file_lock` context manager around per-story
          dispatch under ``parallel_stories: false``.
        * Epic 18 — parallel-story execution: pure-flip-the-switch
          activation against this already-witnessed locking primitive.
"""

from __future__ import annotations

import contextlib
import datetime
import errno
import os
import pathlib
import socket
import sys
from typing import Callable, Final, Iterator, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from loud_fail_harness.input_hardening import harden_identifier

from loud_fail_harness._shared import find_repo_root


#: Marker-class string identifier for stale-lock / contended / corrupted
#: diagnostics. Single constant because all three new exception subclasses
#: pin to the same class string per AC-3 — sub-classifications land in
#: ``schemas/marker-taxonomy.yaml`` via the PATCH bump 1.6 → 1.7
#: (Story 14.3 deliverable). Mirrors ``worktree_lifecycle._MARKER_WORKTREE_STALE_LOCK``
#: verbatim; the two modules pin the SAME string identifier (constants
#: are cheap to duplicate, cross-module coupling is not).
_MARKER_WORKTREE_STALE_LOCK: str = "worktree-stale-lock"


#: Default staleness threshold for a lock-record's ``started_at`` field.
#: 3600 seconds (1 hour) — long enough to outlast any reasonable specialist
#: invocation (including LAD's external-LLM latency budget), short enough
#: that operator inspection isn't blocked on a multi-day-old crash.
DEFAULT_STALE_THRESHOLD_SECONDS: Final[int] = 3600


#: Lock-file suffix factored as a constant for `lock_path` computation
#: + test discoverability.
LOCK_FILE_SUFFIX: Final[str] = ".lock"

#: Maximum number of EEXIST-then-absent race retries in :func:`acquire_lock`.
#: The race (file appeared at O_EXCL, gone by inspect) is a normal filesystem
#: event under concurrent release; one retry covers it. Beyond that, repeated
#: occurrence indicates a filesystem anomaly.
_MAX_RACE_RETRIES: Final[int] = 1


# --------------------------------------------------------------------------- #
# Pydantic v2 frozen models (Pattern 4 + Epic 1 retro Action #2).             #
# --------------------------------------------------------------------------- #


class LockRecord(BaseModel):
    """The on-disk lock-file body shape.

    Pattern 4 — frozen for hashability + determinism; field declaration
    order is the YAML-write order. ``schema_version`` is a closed
    :class:`typing.Literal` so a future schema bump must extend the
    enum (mirrors :class:`run_state.RunState.schema_version` posture).

    Attributes:
        schema_version: ``"1.0"`` at landing. Closed Literal —
            schema-version-mismatch lock files surface via
            :exc:`pydantic.ValidationError` rather than silently
            mis-parsing.
        story_id: The BMAD story identifier the lock is held for.
        pid: The PID that acquired the lock. Used by :func:`is_stale`
            via the dependency-injected ``pid_probe`` callable.
        started_at: UTC wall-clock time of acquisition. Used by
            :func:`is_stale` for age-threshold detection. Pydantic v2
            datetime parsing accepts ISO 8601 with ``Z`` suffix or
            ``+00:00`` offset.
        worktree_path: The on-disk path of the worktree that holds the
            lock. Recorded for operator-visibility on diagnostic
            surfaces; not consulted by :func:`is_stale`.
        hostname: The hostname of the machine that holds the lock.
            Recorded for cross-host parallel-mode operator diagnostics.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"]
    story_id: str = Field(min_length=1)
    pid: int = Field(gt=0)
    started_at: datetime.datetime
    worktree_path: pathlib.Path
    hostname: str = Field(min_length=1)

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> "LockRecord":
        """Input-hardening (Story 24.2 — the Epic 14 ``LockRecord`` recurrence).
        The lock-file body is parsed from operator-editable on-disk YAML; the
        ``min_length=1`` constraint accepts whitespace-only ``story_id``. Route
        it through the shared helper to reject whitespace-only / embedded-newline
        / null-byte values.
        """
        harden_identifier(self.story_id, "LockRecord.story_id")
        return self


class LockAcquisitionResult(BaseModel):
    """Return shape of :func:`acquire_lock` on the success paths.

    Attributes:
        story_id: The story identifier passed to :func:`acquire_lock`.
        lock_path: The computed on-disk path of the lock file.
        acquired: Always ``True``; narrowed to ``Literal[True]`` because
            contention raises :exc:`StoryFileLockContended` rather than
            returning ``False``. Field retained for structural symmetry with
            :class:`LockReleaseResult.released`.
        record: The candidate :class:`LockRecord` written to disk by
            the call.
        was_stale_takeover: ``True`` when the acquisition cleared a
            stale lock via ``os.replace``; ``False`` for clean
            create-only-if-absent acquisitions.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str
    lock_path: pathlib.Path
    acquired: Literal[True]
    record: LockRecord
    was_stale_takeover: bool


class LockReleaseResult(BaseModel):
    """Return shape of :func:`release_lock`.

    Attributes:
        story_id: The story identifier passed to :func:`release_lock`.
        lock_path: The computed on-disk path of the lock file.
        released: ``True`` when the file was deleted by the call;
            ``False`` when the file did not exist (idempotent release).
        record: The :class:`LockRecord` that was on disk at release
            time; ``None`` on the absent-file path AND on the
            corrupted-file path (the corrupted file is cleared but the
            record cannot be returned).
    """

    model_config = ConfigDict(frozen=True)

    story_id: str
    lock_path: pathlib.Path
    released: bool
    record: LockRecord | None


class LockInspectionResult(BaseModel):
    """Return shape of :func:`inspect_lock` when the file exists.

    Attributes:
        story_id: The story identifier passed to :func:`inspect_lock`.
        lock_path: The computed on-disk path of the lock file.
        exists: ``True`` always (inspection returns ``None`` for the
            non-existent file path; this field is present for symmetry
            with potential future ``exists=False`` extensions).
        record: The parsed :class:`LockRecord` on a clean parse;
            ``None`` when parsing failed (see ``parse_error``).
        parse_error: One-line summary of the parse failure (truncated
            to 200 chars); ``None`` on clean parse. Mutually exclusive
            with ``record`` — exactly one is populated.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str
    lock_path: pathlib.Path
    exists: bool
    record: LockRecord | None
    parse_error: str | None


class StalenessVerdict(BaseModel):
    """Return shape of :func:`is_stale`.

    Attributes:
        is_stale: ``True`` when at least one of the two staleness
            predicates fires (pid not alive OR age beyond threshold).
        reason: The discriminator. ``"pid-not-alive"`` and
            ``"age-exceeded"`` map 1:1 to the
            ``schemas/marker-taxonomy.yaml`` sub_classifications;
            ``"fresh"`` indicates a live lock (no marker emission).
        record: The input record, threaded through for diagnostic
            convenience.
        evaluated_at: The clock-read taken at evaluation time.
        age_seconds: The computed ``(evaluated_at - record.started_at)``
            in seconds. Surfaces in operator diagnostics.
    """

    model_config = ConfigDict(frozen=True)

    is_stale: bool
    reason: Literal["pid-not-alive", "age-exceeded", "fresh"]
    record: LockRecord
    evaluated_at: datetime.datetime
    age_seconds: float


# --------------------------------------------------------------------------- #
# Named-invariant exception hierarchy (Pattern 5 + AC-3).                     #
# --------------------------------------------------------------------------- #


class StoryFileLockBlocked(Exception):
    """Base class for every structural rejection from :func:`acquire_lock` /
    :func:`release_lock`.

    Pattern 5 named-invariant diagnostic: the exception carries the
    attempted-story-id + attempted-lock-path + ``marker_class``
    identifier so a downstream emission seam (e.g.,
    ``session_start_reattach``) can render a complete picture. Distinct
    base class from :exc:`worktree_lifecycle.WorktreeLifecycleBlocked`
    (per AC-3 Pattern 5 module-altitude discipline — constants are
    cheap to duplicate, cross-module exception-hierarchy coupling is
    not).

    Attributes:
        attempted_story_id: The ``story_id`` argument the caller
            passed to the entry-point.
        attempted_lock_path: The on-disk lock-file path the call was
            about to act on; ``None`` when the rejection fired before
            any path computation.
        marker_class: ``"worktree-stale-lock"`` for every subclass.
        cause: The upstream signal — a :exc:`BaseException` propagated
            from a YAML / pydantic parse failure, OR a
            :class:`LockRecord` carrying the live competitor's state,
            OR a :class:`LockInspectionResult` carrying the corrupted-
            file diagnostic, OR ``None``.
    """

    def __init__(
        self,
        *,
        attempted_story_id: str,
        attempted_lock_path: pathlib.Path | None,
        marker_class: str,
        message: str,
        cause: BaseException | LockRecord | LockInspectionResult | None = None,
    ) -> None:
        self.attempted_story_id: str = attempted_story_id
        self.attempted_lock_path: pathlib.Path | None = attempted_lock_path
        self.marker_class: str = marker_class
        self.cause: (
            BaseException | LockRecord | LockInspectionResult | None
        ) = cause
        super().__init__(message)


class StoryFileLockContended(StoryFileLockBlocked):
    """Raised by :func:`acquire_lock` when the lock file exists AND the
    existing record's holding PID is alive AND its age is below the
    staleness threshold.

    The substrate REFUSES to silently re-acquire a healthy lock — the
    caller must wait, retry, or escalate. Operator-decided remediation;
    the substrate does NOT auto-evict live competitors.
    """

    def __init__(
        self,
        *,
        attempted_story_id: str,
        attempted_lock_path: pathlib.Path,
        existing_record: LockRecord,
    ) -> None:
        message = (
            f"Story file lock for {attempted_story_id!r} is held by a live "
            f"competitor at {attempted_lock_path} "
            f"(pid={existing_record.pid}, started_at={existing_record.started_at!s}, "
            f"worktree_path={existing_record.worktree_path!s}, "
            f"hostname={existing_record.hostname!r}). "
            "Inspect the holding worktree; retry after the competitor "
            "releases OR escalate to operator if the holder is unresponsive."
        )
        super().__init__(
            attempted_story_id=attempted_story_id,
            attempted_lock_path=attempted_lock_path,
            marker_class=_MARKER_WORKTREE_STALE_LOCK,
            message=message,
            cause=existing_record,
        )


class StoryFileLockCorrupted(StoryFileLockBlocked):
    """Raised by :func:`acquire_lock` when the lock file exists but YAML
    parsing OR :class:`LockRecord` validation fails.

    The file is on-disk but is not a valid lock record — a previous
    write was interrupted mid-stream OR a hand-edit corrupted the
    YAML. Operator-decided remediation: delete the lock file manually
    (after confirming no holder is active) OR escalate.
    """

    def __init__(
        self,
        *,
        attempted_story_id: str,
        attempted_lock_path: pathlib.Path,
        parse_error: str,
    ) -> None:
        message = (
            f"Story file lock at {attempted_lock_path} is corrupted "
            f"(parse failure: {parse_error}). Operator remediation: "
            f"inspect the file, confirm no holding process is active, then "
            f"`rm {attempted_lock_path}` and retry."
        )
        super().__init__(
            attempted_story_id=attempted_story_id,
            attempted_lock_path=attempted_lock_path,
            marker_class=_MARKER_WORKTREE_STALE_LOCK,
            message=message,
            cause=RuntimeError(parse_error),
        )


class StoryFileLockReleaseConflict(StoryFileLockBlocked):
    """Raised by :func:`release_lock` only when the caller explicitly
    supplied ``expected_pid`` AND the on-disk PID disagrees.

    Defensive surface — SessionStart's recovery path does NOT supply
    ``expected_pid`` (it uses :func:`inspect_lock` + :func:`is_stale`
    and writes a fresh acquisition on takeover), so this exception
    never fires on the recovery path. Fires when an in-process
    ``with story_file_lock(...)`` body sleeps past the stale threshold
    and another process takes over the lock; the context-manager's
    ``__exit__`` suppresses-and-logs this case.
    """

    def __init__(
        self,
        *,
        attempted_story_id: str,
        attempted_lock_path: pathlib.Path,
        existing_record: LockRecord,
        expected_pid: int,
    ) -> None:
        message = (
            f"Release of story file lock for {attempted_story_id!r} at "
            f"{attempted_lock_path} refused: expected_pid={expected_pid} but "
            f"on-disk pid={existing_record.pid}. The lock has been taken "
            "over by another process; do NOT delete the on-disk file."
        )
        super().__init__(
            attempted_story_id=attempted_story_id,
            attempted_lock_path=attempted_lock_path,
            marker_class=_MARKER_WORKTREE_STALE_LOCK,
            message=message,
            cause=existing_record,
        )


# --------------------------------------------------------------------------- #
# Module-local default helpers (Epic 1 retro Action #1 + Pattern 6).          #
# --------------------------------------------------------------------------- #


def _default_repo_root() -> pathlib.Path:
    """Resolve the canonical repo root lazily via
    :func:`loud_fail_harness._shared.find_repo_root` at function-call
    time (Epic 1 retro Action #1 discipline — never at module import
    time).
    """
    return find_repo_root()


def _default_locks_root(repo_root: pathlib.Path) -> pathlib.Path:
    """Compute the default per-story locks directory under ``repo_root``.

    Path convention: ``<repo_root>/_bmad/automation/locks/`` per
    epics-phase-2.md line 321. Co-located with
    ``_bmad/automation/run-state.yaml`` (Story 2.2) and
    ``_bmad/automation/worktrees/`` (Story 14.2); namespace-disjoint
    from ``.claude/``.
    """
    return repo_root / "_bmad" / "automation" / "locks"


def _default_pid_probe(pid: int) -> bool:
    """Production default PID-liveness probe.

    Uses :func:`os.kill` with ``signal=0`` — the canonical POSIX
    liveness check. Per the Python ``os.kill`` docs: "If ``sig`` is 0,
    then no actual signal is sent, but error checking is still
    performed; this can be used to check if a target process exists."

    Returns ``True`` when the process exists (and the current user has
    permission to signal it, OR exists-but-not-ours).
    Returns ``False`` when the process does not exist
    (:exc:`ProcessLookupError`) or another OS error fires.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is not signal-able by us (different uid).
        # Treated as alive — the process is still consuming a PID slot.
        return True
    except OSError:
        # Conservative: any other OS error means we cannot confirm liveness.
        return False
    return True


def _default_clock() -> datetime.datetime:
    """Production default clock — UTC ``datetime.datetime``."""
    return datetime.datetime.now(tz=datetime.timezone.utc)


def _lock_path_for(
    story_id: str, locks_root: pathlib.Path
) -> pathlib.Path:
    """Compute ``<locks_root>/<story_id>.lock`` per AC-4 step 2."""
    return locks_root / f"{story_id}{LOCK_FILE_SUFFIX}"


# --------------------------------------------------------------------------- #
# Public API.                                                                  #
# --------------------------------------------------------------------------- #


def inspect_lock(
    story_id: str,
    *,
    locks_root: pathlib.Path | None = None,
    repo_root: pathlib.Path | None = None,
) -> LockInspectionResult | None:
    """Read-only probe over ``<locks_root>/<story_id>.lock``.

    Returns ``None`` when the file does not exist (callers distinguish
    "no file" from "corrupted file" via the ``is None`` vs
    :class:`LockInspectionResult` distinction).

    When the file exists, returns a :class:`LockInspectionResult` with
    EITHER ``record`` populated (clean parse) OR ``parse_error``
    populated (one-line summary of the YAML / Pydantic failure,
    truncated to 200 chars). Mutually exclusive — exactly one is
    populated.

    NEVER raises on parse failure — defensive posture mirrors
    :func:`worktree_lifecycle._parse_worktree_list_porcelain`.

    Args:
        story_id: BMAD story identifier.
        locks_root: Optional directory containing lock files.
            Defaults to ``<repo_root>/_bmad/automation/locks`` when
            ``None``.
        repo_root: Optional repo root; resolved lazily via
            :func:`find_repo_root` when ``None``.

    Returns:
        ``None`` when the lock file does not exist; otherwise a
        :class:`LockInspectionResult`.
    """
    resolved_repo = repo_root if repo_root is not None else _default_repo_root()
    resolved_locks = (
        locks_root if locks_root is not None else _default_locks_root(resolved_repo)
    )
    lock_path = _lock_path_for(story_id, resolved_locks)

    if not lock_path.exists():
        return None

    try:
        text = lock_path.read_text(encoding="utf-8")
    except OSError as exc:
        return LockInspectionResult(
            story_id=story_id,
            lock_path=lock_path,
            exists=True,
            record=None,
            parse_error=f"read-error: {exc!s}"[:200],
        )

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return LockInspectionResult(
            story_id=story_id,
            lock_path=lock_path,
            exists=True,
            record=None,
            parse_error=str(exc)[:200],
        )

    if not isinstance(raw, dict):
        return LockInspectionResult(
            story_id=story_id,
            lock_path=lock_path,
            exists=True,
            record=None,
            parse_error=f"expected mapping at lock-file root, got {type(raw).__name__}"[
                :200
            ],
        )

    try:
        record = LockRecord(**raw)
    except ValidationError as exc:
        return LockInspectionResult(
            story_id=story_id,
            lock_path=lock_path,
            exists=True,
            record=None,
            parse_error=str(exc)[:200],
        )

    return LockInspectionResult(
        story_id=story_id,
        lock_path=lock_path,
        exists=True,
        record=record,
        parse_error=None,
    )


def is_stale(
    record: LockRecord,
    *,
    stale_threshold_seconds: int,
    pid_probe: Callable[[int], bool],
    clock: Callable[[], datetime.datetime],
) -> StalenessVerdict:
    """Pure-function staleness predicate over a :class:`LockRecord`.

    Two-arm evaluation, first match wins:

    1. ``pid_probe(record.pid)`` returns ``False`` →
       ``StalenessVerdict(is_stale=True, reason="pid-not-alive")``.
    2. ``(clock() - record.started_at).total_seconds() >
       stale_threshold_seconds`` →
       ``StalenessVerdict(is_stale=True, reason="age-exceeded")``.
    3. Else → ``StalenessVerdict(is_stale=False, reason="fresh")``.

    All inputs (``pid_probe``, ``clock``, ``stale_threshold_seconds``)
    are keyword-only AND non-defaulted at THIS surface — :func:`is_stale`
    is the dependency-injection seam, so the public-facing
    :func:`acquire_lock` resolves the production defaults BEFORE
    delegating to :func:`is_stale`.
    """
    evaluated_at = clock()
    # Hand-edited or externally-generated lock files may omit timezone info.
    # Assume UTC so subtraction doesn't raise TypeError (production clocks
    # always return UTC-aware; this normalizes the mismatch edge case only).
    started_at = record.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=datetime.timezone.utc)
    age_seconds = (evaluated_at - started_at).total_seconds()

    if not pid_probe(record.pid):
        return StalenessVerdict(
            is_stale=True,
            reason="pid-not-alive",
            record=record,
            evaluated_at=evaluated_at,
            age_seconds=age_seconds,
        )

    if age_seconds > stale_threshold_seconds:
        return StalenessVerdict(
            is_stale=True,
            reason="age-exceeded",
            record=record,
            evaluated_at=evaluated_at,
            age_seconds=age_seconds,
        )

    return StalenessVerdict(
        is_stale=False,
        reason="fresh",
        record=record,
        evaluated_at=evaluated_at,
        age_seconds=age_seconds,
    )


def acquire_lock(
    story_id: str,
    *,
    worktree_path: pathlib.Path,
    locks_root: pathlib.Path | None = None,
    repo_root: pathlib.Path | None = None,
    stale_threshold_seconds: int | None = None,
    pid_probe: Callable[[int], bool] | None = None,
    clock: Callable[[], datetime.datetime] | None = None,
    _retry_count: int = 0,
) -> LockAcquisitionResult:
    """Atomically acquire ``<locks_root>/<story_id>.lock``.

    Execution order per AC-4:

    1. Resolve ``repo_root`` / ``locks_root`` /
       ``stale_threshold_seconds`` / ``pid_probe`` / ``clock`` lazily
       from their ``None`` defaults.
    2. Compute ``lock_path``.
    3. ``locks_root.mkdir(parents=True, exist_ok=True)``.
    4. Build the candidate :class:`LockRecord`.
    5. Atomic write attempt via
       ``os.open(O_CREAT | O_EXCL | O_WRONLY)``:
       a. On success → write YAML, close fd, return
          ``acquired=True, was_stale_takeover=False``.
       b. On ``OSError(errno=EEXIST)`` → proceed to collision handling.
       c. On other ``OSError`` → propagate (sensor-not-advisor —
          disk-full / permission-denied is the caller's concern).
    6. Collision handling — invoke :func:`inspect_lock` to read the
       on-disk record; on parse failure raise
       :exc:`StoryFileLockCorrupted`.
    7. Staleness check via :func:`is_stale`. On ``is_stale=False`` →
       raise :exc:`StoryFileLockContended`. No write occurs.
    8. Stale-takeover — write the candidate record to a sibling
       ``.tmp`` path, then ``os.replace`` atomically over the existing
       file. Return ``acquired=True, was_stale_takeover=True``.

    ``worktree_path`` is keyword-only AND non-defaulted; omitting it
    raises :exc:`TypeError`.
    """
    resolved_repo = repo_root if repo_root is not None else _default_repo_root()
    resolved_locks = (
        locks_root if locks_root is not None else _default_locks_root(resolved_repo)
    )
    resolved_threshold = (
        stale_threshold_seconds
        if stale_threshold_seconds is not None
        else DEFAULT_STALE_THRESHOLD_SECONDS
    )
    resolved_pid_probe = pid_probe if pid_probe is not None else _default_pid_probe
    resolved_clock = clock if clock is not None else _default_clock

    lock_path = _lock_path_for(story_id, resolved_locks)
    resolved_locks.mkdir(parents=True, exist_ok=True)

    candidate = LockRecord(
        schema_version="1.0",
        story_id=story_id,
        pid=os.getpid(),
        started_at=resolved_clock(),
        worktree_path=worktree_path.resolve(),
        hostname=socket.gethostname(),
    )
    serialized = yaml.safe_dump(
        candidate.model_dump(mode="json"), sort_keys=False
    )

    try:
        fd = os.open(
            str(lock_path),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o644,
        )
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise
    else:
        try:
            os.write(fd, serialized.encode("utf-8"))
        finally:
            os.close(fd)
        return LockAcquisitionResult(
            story_id=story_id,
            lock_path=lock_path,
            acquired=True,
            record=candidate,
            was_stale_takeover=False,
        )

    inspection = inspect_lock(
        story_id, locks_root=resolved_locks, repo_root=resolved_repo
    )
    if inspection is None:
        # Race: file appeared at O_EXCL, gone by inspect (concurrent release).
        if _retry_count >= _MAX_RACE_RETRIES:
            raise RuntimeError(
                f"acquire_lock: EEXIST-then-absent race on {lock_path!s} "
                f"repeated {_retry_count + 1} time(s); filesystem anomaly or "
                "high-frequency concurrent release — operator investigation required"
            )
        return acquire_lock(
            story_id,
            worktree_path=worktree_path,
            locks_root=resolved_locks,
            repo_root=resolved_repo,
            stale_threshold_seconds=resolved_threshold,
            pid_probe=resolved_pid_probe,
            clock=resolved_clock,
            _retry_count=_retry_count + 1,
        )
    if inspection.parse_error is not None or inspection.record is None:
        raise StoryFileLockCorrupted(
            attempted_story_id=story_id,
            attempted_lock_path=lock_path,
            parse_error=inspection.parse_error or "record-missing",
        )

    verdict = is_stale(
        inspection.record,
        stale_threshold_seconds=resolved_threshold,
        pid_probe=resolved_pid_probe,
        clock=resolved_clock,
    )
    if not verdict.is_stale:
        raise StoryFileLockContended(
            attempted_story_id=story_id,
            attempted_lock_path=lock_path,
            existing_record=inspection.record,
        )

    tmp_path = lock_path.with_suffix(lock_path.suffix + ".tmp")
    tmp_path.write_text(serialized, encoding="utf-8")
    try:
        os.replace(str(tmp_path), str(lock_path))
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise
    return LockAcquisitionResult(
        story_id=story_id,
        lock_path=lock_path,
        acquired=True,
        record=candidate,
        was_stale_takeover=True,
    )


def release_lock(
    story_id: str,
    *,
    locks_root: pathlib.Path | None = None,
    repo_root: pathlib.Path | None = None,
    expected_pid: int | None = None,
) -> LockReleaseResult:
    """Release ``<locks_root>/<story_id>.lock``.

    Execution order per AC-5:

    1. Resolve ``repo_root`` / ``locks_root`` lazily.
    2. Compute ``lock_path``.
    3. If the file does not exist → return ``released=False,
       record=None`` (idempotent).
    4. Inspect the on-disk record. If parsing failed, the file IS
       cleared (corrupted-file-blocks-future-acquisition would be
       worse than letting release succeed).
    5. If ``expected_pid is not None`` AND ``record.pid !=
       expected_pid`` → raise :exc:`StoryFileLockReleaseConflict`; do
       NOT delete.
    6. Else → ``lock_path.unlink()`` and return ``released=True``.
    """
    resolved_repo = repo_root if repo_root is not None else _default_repo_root()
    resolved_locks = (
        locks_root if locks_root is not None else _default_locks_root(resolved_repo)
    )
    lock_path = _lock_path_for(story_id, resolved_locks)

    if not lock_path.exists():
        return LockReleaseResult(
            story_id=story_id,
            lock_path=lock_path,
            released=False,
            record=None,
        )

    inspection = inspect_lock(
        story_id, locks_root=resolved_locks, repo_root=resolved_repo
    )
    if inspection is None:
        # Race: existed at the .exists() check, gone by inspect.
        return LockReleaseResult(
            story_id=story_id,
            lock_path=lock_path,
            released=False,
            record=None,
        )

    if inspection.record is None:
        # Corrupted file. Clear it — the alternative (leak the
        # corrupted file) would block all future acquisitions.
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        return LockReleaseResult(
            story_id=story_id,
            lock_path=lock_path,
            released=True,
            record=None,
        )

    if expected_pid is not None and inspection.record.pid != expected_pid:
        raise StoryFileLockReleaseConflict(
            attempted_story_id=story_id,
            attempted_lock_path=lock_path,
            existing_record=inspection.record,
            expected_pid=expected_pid,
        )

    lock_path.unlink(missing_ok=True)
    return LockReleaseResult(
        story_id=story_id,
        lock_path=lock_path,
        released=True,
        record=inspection.record,
    )


@contextlib.contextmanager
def story_file_lock(
    story_id: str,
    *,
    worktree_path: pathlib.Path,
    locks_root: pathlib.Path | None = None,
    repo_root: pathlib.Path | None = None,
    stale_threshold_seconds: int | None = None,
) -> Iterator[LockAcquisitionResult]:
    """Acquire-release context manager around :func:`acquire_lock` /
    :func:`release_lock`.

    Acquires the lock on entry, yields the
    :class:`LockAcquisitionResult`, releases on exit (via ``finally``)
    with ``expected_pid=os.getpid()`` so a stale-takeover by another
    process during the ``with`` body surfaces as
    :exc:`StoryFileLockReleaseConflict`. That exception is suppressed-
    and-logged inside the ``finally`` so the body's exception (if any)
    propagates per Python's standard context-manager semantics.
    """
    owning_pid = os.getpid()
    result = acquire_lock(
        story_id,
        worktree_path=worktree_path,
        locks_root=locks_root,
        repo_root=repo_root,
        stale_threshold_seconds=stale_threshold_seconds,
    )
    try:
        yield result
    finally:
        try:
            release_lock(
                story_id,
                locks_root=locks_root,
                repo_root=repo_root,
                expected_pid=owning_pid,
            )
        except StoryFileLockReleaseConflict as exc:
            # Lock was taken over mid-body via stale-takeover. Surface
            # a single-line diagnostic to stderr; do NOT re-raise (the
            # body's exception, if any, takes precedence per Python's
            # exception-propagation semantics inside __exit__).
            print(
                f"story-file-lock: release-conflict: {exc!s}",
                file=sys.stderr,
            )


__all__ = [
    "DEFAULT_STALE_THRESHOLD_SECONDS",
    "LockAcquisitionResult",
    "LockInspectionResult",
    "LockRecord",
    "LockReleaseResult",
    "StalenessVerdict",
    "StoryFileLockBlocked",
    "StoryFileLockContended",
    "StoryFileLockCorrupted",
    "StoryFileLockReleaseConflict",
    "acquire_lock",
    "inspect_lock",
    "is_stale",
    "release_lock",
    "story_file_lock",
]
