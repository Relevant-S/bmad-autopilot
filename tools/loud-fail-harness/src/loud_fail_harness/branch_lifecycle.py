"""Per-story branch lifecycle module (story 2.3). NFR-R3 + NFR-S3 + NFR-O5.

Architectural placement (story 1.10b precedent + story 2.2 precedent — story
2.2 Dev Notes "Why ``run_state.py`` is a substrate library (not a sixth
substrate component)"): this module is a sibling of
:mod:`loud_fail_harness.story_doc_validator` and
:mod:`loud_fail_harness.run_state` and the five substrate-component modules
(``envelope_validator``, ``event_validator``, ``reconciler``,
``enumeration_check``, ``fixture_coverage``). It is **NOT a sixth substrate
component**. ADR-003 Consequence 1 enumerates exactly five substrate
components (architecture.md lines 311-315); this module is a substrate
**library** consumed by Epic 2/3/4/5/6/7/8 specialist subagents at runtime
to perform NFR-R3 + NFR-S3-compliant per-story branch lifecycle operations
against the user's working tree. The substrate-component count stays at
FIVE; the harness module count grows.

Closer in shape to ``run_state.py`` than to the directory-scanning CI gates
(``pluggability_gate.py``, ``hook_budget_gate.py``): there is no canonical
filesystem surface to scan at this story's landing time because branch
operations happen at orchestrator runtime in Epic 2+, not as committed
filesystem artifacts on disk.

What this library provides:
    * **Public function** :func:`create_story_branch` — the SOLE git-write
      surface in this module; consults the trunk-name allowlist before any
      branch-write; halts on uncommitted-user-work via the injected
      :class:`WorkingTreeProbe` callable; performs a single atomic
      ``git checkout -b`` for new branches OR a plain ``git checkout`` for
      existing branches (idempotent per NFR-R2).
    * **Working-tree probe factory** :func:`default_working_tree_probe` —
      returns a :class:`WorkingTreeProbe` callable wrapping
      ``git status --porcelain``; the factory pattern preserves
      sensor-not-advisor (the *caller* injects the probe; the helper
      consumes whatever the caller hands it; tests inject deterministic
      stubs without monkey-patching ``subprocess.run``).
    * **Pydantic v2 frozen models** :class:`WorkingTreeProbeResult` and
      :class:`BranchLifecycleResult` — Pattern 4 state-update discipline +
      Epic 1 retro Action #2 (sequence fields are ``tuple[…]``, NOT
      ``list[…]``, so ``frozen=True`` blocks BOTH attribute reassignment
      AND in-place mutation structurally; mirrors story 2.2's posture).
    * **Named-invariant exception hierarchy** :class:`BranchLifecycleBlocked`
      → :class:`GitUncommittedWorkDetected` /
      :class:`TrunkBranchWriteRejected` — Pattern 5 named-invariant
      diagnostic per architecture.md lines 983-991; each subclass pins
      its ``marker_class`` to the corresponding entry in
      ``schemas/marker-taxonomy.yaml`` for the caller's envelope-level
      emission (sensor-not-advisor — the helper does NOT auto-emit; the
      caller emits via its envelope + the orchestrator-event log).
    * **Default trunk allowlist** :data:`DEFAULT_TRUNK_ALLOWLIST` —
      exposed for caller convenience, NOT as an internally-applied
      default; the caller MUST pass ``trunk_allowlist`` explicitly per
      AC-1 (keyword-only AND non-defaulted).

What this library enforces:
    * **NFR-R3** (PRD line 947) — "Automator commits are always on the
      per-story branch, never on ``main`` / ``master`` / user's trunk;
      never force-push; never rebase user commits; never delete branches
      except as explicit opt-in cleanup after successful merge. Git
      operations that would destroy uncommitted user work halt with a
      diagnostic rather than proceeding." Encoded structurally as: (a)
      the trunk-allowlist consultation BEFORE any branch-write; (b) the
      :class:`WorkingTreeProbe` halt-on-unclean-tree contract; (c) the
      complete absence of force-push / rebase / branch-delete code paths
      in this module.
    * **NFR-S3** (PRD line 971) — "Automator git operations are limited
      to: branch creation, checkout, commit, and local branch management.
      No auto-push to remote (except opt-in auto-merge in Phase 2+). No
      force-push ever. No operations on branches other than the story
      branch. No operations on ``main`` / ``master`` / ``trunk``." This
      module's only ``subprocess.run`` invocations are: ``git rev-parse``
      (read-only HEAD + branch existence checks), ``git status
      --porcelain`` (read-only working-tree probe; only via the default
      probe factory), ``git checkout`` (idempotent existing-branch
      checkout), ``git checkout -b`` (atomic create-and-checkout). No
      ``git push`` / ``git push --force`` / ``git rebase`` / ``git reset
      --hard`` / ``git clean`` / ``git branch -D`` / ``git branch
      --delete`` / ``git fetch`` / ``git pull`` / ``git merge`` /
      ``git cherry-pick`` / ``git tag`` / ``git remote`` under any code
      path.
    * **NFR-O5** (PRD line 984) — "Named diagnostic per failure class —
      every failure surface ... produces a diagnostic with the failed
      invariant's name and a specific remediation pointer." Encoded as
      the named exception classes :class:`GitUncommittedWorkDetected`
      and :class:`TrunkBranchWriteRejected`, each carrying a marker-
      class identifier matching ``schemas/marker-taxonomy.yaml`` and a
      ``__str__`` form including an actionable-fix-pointer.
    * **Pattern 5** (architecture.md lines 983-991) — "Every error class
      corresponds to a marker class in ``marker-taxonomy.yaml``. Every
      marker emission includes an actionable-fix-pointer (per FR31).
      Silent error swallowing is forbidden — loud-fail doctrine. Errors
      flow into PR bundle via Stop hook assembly (per ADR-001,
      ADR-003)." This module's exception classes pin to the marker-
      taxonomy entries added by AC-4 of this story
      (``git-uncommitted-work-detected`` and
      ``trunk-branch-write-rejected``).
    * **NFR-R2** (PRD line 946) — "Crash recovery — on session restart
      after a crash mid-story, ``SessionStart`` hook detects the in-
      progress run-state and offers resumption (via FR46). Orchestrator
      never duplicates state-advancing actions (re-creates a branch
      that already exists, ...)." Encoded as the existing-branch-
      checkout idempotency: when ``git rev-parse --verify --quiet
      <branch>`` succeeds, the helper performs ``git checkout <branch>``
      (no re-creation) and returns ``BranchLifecycleResult(created=False,
      ...)``.

## Working tree probe contract

The :class:`WorkingTreeProbe` parameter (callable returning a
:class:`WorkingTreeProbeResult`) is **caller-injected**, not module-
chosen. The caller (Story 2.5's orchestrator skill) constructs the
probe by calling :func:`default_working_tree_probe` with its repo root
and passes the resulting callable to :func:`create_story_branch`. The
factory wraps ``git status --porcelain`` (read-only; see NFR-S3
allowed primitives); tests inject deterministic stubs without
monkey-patching ``subprocess.run``::

    from loud_fail_harness.branch_lifecycle import (
        create_story_branch, WorkingTreeProbeResult, default_working_tree_probe,
        DEFAULT_TRUNK_ALLOWLIST,
    )

    # Production caller (orchestrator skill, Story 2.5):
    probe = default_working_tree_probe(repo_root)
    result = create_story_branch(
        story_id="2-3",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        working_tree_probe=probe,
        repo_root=repo_root,
    )

    # Test injection:
    def stub_probe() -> WorkingTreeProbeResult:
        return WorkingTreeProbeResult(clean=True)
    result = create_story_branch(
        story_id="2-3",
        trunk_allowlist=DEFAULT_TRUNK_ALLOWLIST,
        working_tree_probe=stub_probe,
        repo_root=tmp_path,
    )

The factory pattern preserves sensor-not-advisor — the helper does
NOT itself decide how to detect uncommitted work; the caller injects
the policy.

## Trunk-allowlist semantics

The :data:`DEFAULT_TRUNK_ALLOWLIST` constant is ``("main", "master",
"trunk")`` per NFR-S3's verbatim enumeration. The constant is exposed
for caller convenience — it is NOT applied as an internal default;
the ``trunk_allowlist`` parameter of :func:`create_story_branch` is
**keyword-only AND non-defaulted** (omitting it is a ``TypeError`` at
call time per Python's missing-required-keyword-argument semantics).

The orchestrator skill (Story 2.5) reads the project's override from
``_bmad/automation/config.yaml`` per FR40 and passes the resolved
tuple. Projects whose trunk has a non-standard name (``develop``,
``mainline``, ``release``) override the default; the helper is
agnostic to the source of the tuple.

The comparison is **exact-string-match** against the entries in
``trunk_allowlist`` — not glob-match, not substring-match — per
``docs/git-hygiene.md`` § "No operations on ``main`` / ``master`` /
``trunk``". The branch name is derived from the ``story_id`` via
:func:`_branch_name_for_story`; if the derived name appears in
``trunk_allowlist``, the helper raises
:exc:`TrunkBranchWriteRejected` BEFORE invoking any git command (the
rejection is at module level, not a post-`git`-failure recovery).

## Sensor-not-advisor (PRD-level invariant + Pattern 5)

The library RAISES typed exceptions
(:exc:`GitUncommittedWorkDetected`,
:exc:`TrunkBranchWriteRejected`) carrying marker-class identifiers
on the diagnostic path; it does NOT emit markers itself, does NOT
auto-stash, does NOT auto-commit, does NOT log, does NOT print.
Same posture as 1.10b (``story_doc_validator``) and 2.2
(``run_state``). The calling specialist (Story 2.5's orchestrator
skill, then Story 2.6's dispatch wrapper) emits the marker via its
envelope + the orchestrator's event log per ADR-001 + Pattern 5.

## ``find_repo_root()`` discipline (Epic 1 retro Action #1)

Epic 1 retrospective Challenge #1 (line 55) flagged
``find_repo_root()`` called at module import time, raising
``RuntimeError`` when pytest is invoked outside the repo root.
Action #1 (line 106) targets this risk for every downstream module.

This module honors the discipline: ``find_repo_root()`` is NOT
called at module top-level. The :func:`create_story_branch` helper
takes ``repo_root: pathlib.Path | None = None`` from the caller; if
``None``, the helper computes it lazily via
:func:`_default_repo_root` (which calls ``find_repo_root()`` at
function-call time, not at import time). Tests use ``tmp_path``
fixtures that supply ``repo_root`` explicitly — no
``find_repo_root()`` involvement at module collection time.

## FR62 pluggability classification

This module is *substrate-shared library* per Story 1.10b's precedent
(``story_doc_validator.py``) and Story 2.2's precedent
(``run_state.py``) and ADR-003's substrate-vs-specialist boundary;
consumed by Stories 2.4, 2.5, 2.7, 2.11 and Phase 1.5+ successors.
The FR62 gate (Story 1.10a's
:mod:`loud_fail_harness.pluggability_gate`) does NOT flag substrate
cross-imports; specialist subagents (Dev, Review-BMAD, QA, LAD) live
in ``agents/*.md`` and the gate's no-cross-references rule applies
to *that* surface, not this one.

## Forward-compat consumers

Stories that will consume :func:`create_story_branch` exclusively
(no direct ``git checkout``-form invocation outside this module's
public surface — Pattern 5 + NFR-S3 enforcement):

    * Story 2.4 — BMAD lifecycle state machine: composes
      :func:`create_story_branch` with
      :func:`loud_fail_harness.run_state.advance_run_state` at the
      ``ready-for-dev → in-progress`` transition; the branch creation
      is one of the side effects the state-transition author wires.
    * Story 2.5 — orchestrator skill scaffold: binding consumer per
      epics.md line 1293 ("creates the per-story branch via Story
      2.3"); ``/bmad-automation run <story-id>`` calls into branch
      creation as step (c) of the entry sequence.
    * Story 2.7 — three hooks (SubagentStop / Stop / SessionStart):
      SubagentStop's commit handler relies on the story branch being
      checked out; SessionStart reads ``branch_name`` from run-state
      and verifies the local branch ref via ``git rev-parse`` per
      FR46.
    * Story 2.11 — PR bundle assembly: reads ``branch_name`` from
      run-state and renders it in the bundle's machine-readable
      header.
    * Phase 1.5+ — any future story that touches the working tree
      consumes this primitive rather than re-implementing the
      trunk-allowlist + clean-tree-probe protocol.
"""

from __future__ import annotations

import pathlib
import subprocess
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness._shared import find_repo_root


#: Marker-class string identifier for the working-tree-uncommitted halt
#: diagnostic. Source-of-truth: ``schemas/marker-taxonomy.yaml`` (entry
#: 28; added by Story 2.3 AC-4). Distinct from
#: ``"dangling-uncommitted-work"`` (entry 14; ADR-005 git-probe
#: diagnostic — visibility-only, recovery-time); this marker is
#: write-time, flow-blocking. Surfaced via
#: :attr:`GitUncommittedWorkDetected.marker_class` for the caller's
#: envelope-level emission (sensor-not-advisor; the helper does NOT
#: auto-emit).
_MARKER_GIT_UNCOMMITTED_WORK_DETECTED: str = "git-uncommitted-work-detected"

#: Marker-class string identifier for the trunk-allowlist rejection
#: diagnostic. Source-of-truth: ``schemas/marker-taxonomy.yaml`` (entry
#: 29; added by Story 2.3 AC-4). Surfaced via
#: :attr:`TrunkBranchWriteRejected.marker_class` for the caller's
#: envelope-level emission.
_MARKER_TRUNK_BRANCH_WRITE_REJECTED: str = "trunk-branch-write-rejected"


#: Default trunk-name allowlist matching NFR-S3's verbatim enumeration
#: (PRD line 971). Exposed for caller convenience; NOT applied as an
#: internal default — the ``trunk_allowlist`` parameter of
#: :func:`create_story_branch` is keyword-only AND non-defaulted, so
#: omitting it is a ``TypeError`` at call time. Callers (orchestrator
#: skill in Story 2.5+) read the project's override from
#: ``_bmad/automation/config.yaml`` per FR40 and pass the resolved
#: tuple.
DEFAULT_TRUNK_ALLOWLIST: tuple[str, ...] = ("main", "master", "trunk")


def _branch_name_for_story(story_id: str) -> str:
    """Derive the per-story branch name from a ``story_id`` per the
    canonical convention codified in ``bmad-autopilot/docs/git-
    hygiene.md`` § "Branch naming convention" (Story 1.12a's
    deliverable; cited verbatim).

    Convention: ``bmad-automation/story/<story-id>``. The
    ``bmad-automation/`` namespace prefix makes Automator-produced
    branches visually distinguishable from human-created branches at
    a glance (NFR-O6 commit-history legibility applied to branch
    names). The ``story/<story-id>`` infix scopes the branch to a
    single BMAD story-id so per-story branch lifecycle is
    unambiguous: every branch under ``bmad-automation/story/``
    corresponds to exactly one story file, and the Automator can
    locate the owning story-id from the branch name without external
    state.

    Phase 2+ extensions (per ``docs/git-hygiene.md`` § "Phase 2+
    extensions") — additional naming conventions for hotfix
    branches, retry-mode branches, draft branches — edit THIS helper
    in a single place; the broader module surface stays unchanged.
    """
    return f"bmad-automation/story/{story_id}"


def _default_repo_root() -> pathlib.Path:
    """Resolve the canonical repo root via :func:`loud_fail_harness.
    _shared.find_repo_root` at function-call time (Epic 1 retro
    Action #1 discipline — never at module import time).
    """
    return find_repo_root()


class WorkingTreeProbeResult(BaseModel):
    """Return shape of a working-tree probe supplied to
    :func:`create_story_branch`.

    Frozen + sequence-typed-as-``tuple[…]`` per Epic 1 retro Action
    #2 / story 2.2 frozen-tuple precedent.

    Field semantics:
        * ``clean`` — the canonical decision. ``True`` if the working
          tree has no uncommitted changes; ``False`` if the probe
          detected uncommitted modifications, untracked files, or
          staged changes that have not yet been committed.
        * ``uncommitted_paths`` — tuple of path strings for each
          uncommitted entry the probe detected (one entry per non-
          empty line of ``git status --porcelain`` for the default
          probe). Empty tuple when ``clean=True``.
        * ``reason`` — human-readable explanation of the outcome.
          Free-form; ``None`` when ``clean=True``; the default probe
          sets this to ``"<N> uncommitted path(s) detected"`` when
          unclean.
    """

    model_config = ConfigDict(frozen=True)

    clean: bool
    uncommitted_paths: tuple[str, ...] = ()
    reason: str | None = None


class BranchLifecycleResult(BaseModel):
    """Return shape of a successful :func:`create_story_branch` call.

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``branch_name`` — the per-story branch name derived from
          ``story_id`` per :func:`_branch_name_for_story`.
        * ``created`` — ``True`` if the branch was newly created via
          ``git checkout -b``; ``False`` if it already existed and the
          helper performed a plain ``git checkout`` (idempotent path
          per NFR-R2).
        * ``previous_branch`` — the branch name HEAD pointed to before
          the call (captured pre-checkout via ``git rev-parse
          --abbrev-ref HEAD``); ``None`` if HEAD could not be
          resolved (e.g., empty repo with no commits, or detached
          HEAD with no symbolic ref).
        * ``repo_root`` — the resolved repo root passed to / computed
          by :func:`create_story_branch`; surfaced for caller
          convenience (e.g., logging, follow-up git operations).
    """

    model_config = ConfigDict(frozen=True)

    branch_name: str = Field(min_length=1)
    created: bool
    previous_branch: str | None
    repo_root: pathlib.Path


#: Type alias for the working-tree-probe parameter of
#: :func:`create_story_branch`. A zero-arg callable returning a
#: :class:`WorkingTreeProbeResult`. The callable is constructed by
#: :func:`default_working_tree_probe` for production use; tests
#: inject deterministic stubs.
WorkingTreeProbe = Callable[[], WorkingTreeProbeResult]


class BranchLifecycleBlocked(Exception):
    """Base exception class for any structural rejection from
    :func:`create_story_branch`.

    Pattern 5 named-invariant diagnostic (architecture.md lines
    983-991): the exception surfaces both the upstream cause AND
    the attempted-story-id so the diagnostic envelope can render a
    complete picture (what the orchestrator was trying to do, and
    what blocked it). Subclasses pin ``marker_class`` to a specific
    entry in ``schemas/marker-taxonomy.yaml``.

    Attributes:
        cause: The upstream signal that triggered the block —
            :class:`WorkingTreeProbeResult` for probe-based halts
            (:class:`GitUncommittedWorkDetected`; AC-1 type contract),
            a :class:`BaseException` propagated from a probe failure,
            or ``None`` for purely structural rejections where no
            upstream signal exists (:class:`TrunkBranchWriteRejected`
            fires from a data check, not from a probe or OS error).
        attempted_story_id: The ``story_id`` argument the caller
            passed to :func:`create_story_branch`.
        marker_class: The marker-class string identifier matching
            ``schemas/marker-taxonomy.yaml``; the caller emits the
            marker via its envelope (sensor-not-advisor; the helper
            does NOT auto-emit).
    """

    def __init__(
        self,
        *,
        cause: BaseException | WorkingTreeProbeResult | None,
        attempted_story_id: str,
        marker_class: str,
        message: str,
    ) -> None:
        self.cause: BaseException | WorkingTreeProbeResult | None = cause
        self.attempted_story_id: str = attempted_story_id
        self.marker_class: str = marker_class
        super().__init__(message)


class GitUncommittedWorkDetected(BranchLifecycleBlocked):
    """Raised by :func:`create_story_branch` when the
    :class:`WorkingTreeProbe` reports the working tree is unclean,
    BEFORE any ``git checkout``-form command is invoked.

    NFR-R3 (PRD line 947) verbatim — "Git operations that would
    destroy uncommitted user work halt with a diagnostic rather than
    proceeding." NFR-O5 (PRD line 984) — named diagnostic per failure
    class with actionable-fix-pointer.

    The orchestrator does NOT auto-stash, auto-commit, or auto-clean
    on the practitioner's behalf (epics.md line 1242). The exception's
    ``__str__`` form includes the uncommitted-path count + a
    remediation pointer to ``docs/git-hygiene.md``; the practitioner
    decides remediation (stash, commit, or abort).

    Distinct from ``dangling-uncommitted-work`` (the ADR-005 git-
    probe diagnostic — visibility-only, recovery-time); this marker
    is a write-time halt, fired BEFORE any branch-creation operation
    runs. The marker-taxonomy entry's ``diagnostic_pointer`` block
    names the distinction verbatim.

    Attributes:
        uncommitted_paths: Tuple of path strings (one per non-empty
            line of ``git status --porcelain`` for the default probe)
            the probe detected as uncommitted. Surfaced through the
            exception's ``__str__`` form for the actionable-fix-
            pointer.
    """

    def __init__(
        self,
        *,
        attempted_story_id: str,
        uncommitted_paths: tuple[str, ...],
    ) -> None:
        self.uncommitted_paths: tuple[str, ...] = uncommitted_paths
        message = (
            f"Working tree has {len(uncommitted_paths)} uncommitted path(s); "
            f"stash, commit, or abort before re-running. "
            f"See bmad-autopilot/docs/git-hygiene.md."
        )
        # Reconstruct WorkingTreeProbeResult from the path data so `cause`
        # carries the structured probe evidence per AC-1's type contract
        # (BranchLifecycleBlocked.cause: BaseException | WorkingTreeProbeResult).
        probe_result = WorkingTreeProbeResult(
            clean=False,
            uncommitted_paths=uncommitted_paths,
            reason=f"{len(uncommitted_paths)} uncommitted path(s) detected",
        )
        super().__init__(
            cause=probe_result,
            attempted_story_id=attempted_story_id,
            marker_class=_MARKER_GIT_UNCOMMITTED_WORK_DETECTED,
            message=message,
        )


class TrunkBranchWriteRejected(BranchLifecycleBlocked):
    """Raised by :func:`create_story_branch` when the would-be branch
    name matches an entry in the configured ``trunk_allowlist``,
    BEFORE any ``git`` command is invoked.

    NFR-S3 (PRD line 971) verbatim — "No operations on ``main`` /
    ``master`` / ``trunk``." The rejection is at module level (not a
    post-`git`-failure recovery); no git command runs against the
    protected branch.

    The default allowlist is ``DEFAULT_TRUNK_ALLOWLIST = ("main",
    "master", "trunk")``; the orchestrator skill (Story 2.5) reads
    the override from ``_bmad/automation/config.yaml`` per FR40 and
    passes the resolved tuple. Projects with non-standard trunk
    names (``develop``, ``mainline``, ``release``) extend the
    allowlist; the helper is agnostic to the source of the tuple.

    Attributes:
        attempted_branch: The branch name derived from
            ``story_id`` that was rejected. Surfaced through the
            exception's ``__str__`` form.
    """

    def __init__(
        self,
        *,
        attempted_story_id: str,
        attempted_branch: str,
    ) -> None:
        self.attempted_branch: str = attempted_branch
        message = (
            f"Refusing to operate on trunk-allowlisted branch "
            f"{attempted_branch!r}; per NFR-S3 the Automator never targets "
            f"main / master / trunk. Review trunk_allowlist configuration "
            f"in _bmad/automation/config.yaml or the story_id derivation."
        )
        super().__init__(
            cause=None,
            attempted_story_id=attempted_story_id,
            marker_class=_MARKER_TRUNK_BRANCH_WRITE_REJECTED,
            message=message,
        )


def default_working_tree_probe(repo_root: pathlib.Path) -> WorkingTreeProbe:
    """Return a :class:`WorkingTreeProbe` callable wrapping
    ``git status --porcelain``.

    The factory pattern preserves sensor-not-advisor: the *caller*
    constructs the probe explicitly (typically once per story-loop
    entry in the orchestrator skill); the probe is then passed to
    :func:`create_story_branch`. Tests inject deterministic stubs
    via ``lambda: WorkingTreeProbeResult(clean=False,
    uncommitted_paths=("a.py",))`` rather than monkey-patching the
    factory.

    The wrapped command is read-only per NFR-S3's allowed-primitives
    enumeration — ``git status`` is in the explicit read-only set
    documented in ``docs/git-hygiene.md`` § "Allowed primitives".

    The probe parses ``git status --porcelain`` output: each non-empty
    line has format ``XY <path>`` (two-char status + space + path);
    the path-portion (``line[3:]``) is the uncommitted entry's path.
    Renames produce ``RXX old -> new`` — the path-portion is
    ``"old -> new"``, which is fine for diagnostic surfacing (the
    helper does not perform git operations against rename-form
    paths; it just renders them in the diagnostic).

    Args:
        repo_root: The repository root the ``git status`` command
            runs against (passed as ``cwd``).

    Returns:
        A zero-arg callable returning a :class:`WorkingTreeProbeResult`.

    Raises:
        subprocess.CalledProcessError: If ``git status`` itself fails
            (e.g., not a git repo at ``cwd`` — git exits non-zero).
            The failure propagates from the probe at invocation time,
            not from the factory; sensor-not-advisor — the helper does
            NOT translate the OS error into a marker exception.
        FileNotFoundError: If ``cwd`` does not exist or ``git`` is
            not installed — subprocess raises before git even runs.
    """

    def _probe() -> WorkingTreeProbeResult:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        # Porcelain format: ``XY <path>`` — strip the 2-char status + space
        # prefix. Defensive ``len(line) > 3`` guard handles malformed lines
        # (treats the whole line as the path; never raises IndexError).
        paths: tuple[str, ...] = tuple(
            line[3:] if len(line) > 3 else line for line in lines
        )
        clean = len(paths) == 0
        return WorkingTreeProbeResult(
            clean=clean,
            uncommitted_paths=paths,
            reason=(
                None
                if clean
                else f"{len(paths)} uncommitted path(s) detected"
            ),
        )

    return _probe


def create_story_branch(
    story_id: str,
    *,
    trunk_allowlist: tuple[str, ...],
    working_tree_probe: WorkingTreeProbe,
    repo_root: pathlib.Path | None = None,
) -> BranchLifecycleResult:
    """Create (or idempotently checkout) the per-story branch for
    ``story_id``, after the trunk-allowlist consultation passes and
    the working-tree probe reports clean.

    Execution order (load-bearing per NFR-R3 + NFR-S3 + Pattern 5):

        1. Derive ``branch_name`` from ``story_id`` via
           :func:`_branch_name_for_story` (the canonical convention
           codified in ``docs/git-hygiene.md``).
        2. Invoke ``working_tree_probe()`` synchronously and capture
           its :class:`WorkingTreeProbeResult`. If
           ``result.clean is False``, raise
           :exc:`GitUncommittedWorkDetected` BEFORE invoking any
           git command.
        3. Check ``branch_name`` against ``trunk_allowlist`` —
           exact-string-match per NFR-S3. If a match is found,
           raise :exc:`TrunkBranchWriteRejected` BEFORE invoking
           any git command.
        4. Capture ``previous_branch`` via ``git rev-parse
           --abbrev-ref HEAD`` (read-only; tolerates failure for
           empty repos).
        5. Check whether ``branch_name`` already exists locally via
           ``git rev-parse --verify --quiet <branch_name>`` (read-
           only; ``returncode == 0`` means exists).
        6. If the branch exists, ``git checkout <branch_name>``
           (idempotent per NFR-R2 — orchestrator never re-creates an
           existing branch). If it does not, ``git checkout -b
           <branch_name>`` (atomic create-and-checkout).

    The ``trunk_allowlist`` and ``working_tree_probe`` parameters are
    **keyword-only** (the ``*,`` separator) AND **non-defaulted** (no
    ``= None``, no fallback values) so that omitting either is a
    ``TypeError`` at call time per Python's missing-required-keyword-
    argument semantics; mypy strict mode (when enabled) catches the
    omission at type-check time. There is no API path to create a
    story branch without supplying both — the protocol is structural,
    not documented-only.

    The helper does NOT call ``git push``, ``git push --force``,
    ``git rebase``, ``git reset --hard``, ``git clean``, ``git branch
    -D``, ``git branch --delete``, ``git fetch``, ``git pull``, ``git
    merge``, ``git cherry-pick``, ``git tag``, or ``git remote`` under
    any code path. The full ``subprocess.run`` invocation surface is
    limited to: ``git rev-parse`` (read-only), ``git status
    --porcelain`` (read-only; only via the default probe factory),
    ``git checkout`` (idempotent existing-branch checkout), ``git
    checkout -b`` (atomic create-and-checkout). All invocations use
    the list-form ``args`` (NEVER ``shell=True``), shell-injection-
    safe by construction.

    Args:
        story_id: The BMAD story identifier (e.g., ``"2-3"``,
            ``"1-12a"``). Used to derive the branch name per
            :func:`_branch_name_for_story`.
        trunk_allowlist: The tuple of branch names to reject as
            protected trunk branches. Exact-string-match; case-
            sensitive. The orchestrator skill (Story 2.5) reads the
            override from ``_bmad/automation/config.yaml`` per FR40
            and passes the resolved tuple; pass
            :data:`DEFAULT_TRUNK_ALLOWLIST` for the NFR-S3-verbatim
            default.
        working_tree_probe: A zero-arg callable returning a
            :class:`WorkingTreeProbeResult`. Constructed via
            :func:`default_working_tree_probe` for production use;
            tests inject deterministic stubs.
        repo_root: The repository root for the git operations
            (passed as ``cwd`` to ``subprocess.run``). Defaults to
            ``None``, in which case :func:`_default_repo_root` is
            called lazily to resolve via
            :func:`loud_fail_harness._shared.find_repo_root` (Epic 1
            retro Action #1 discipline — NEVER at module import
            time).

    Returns:
        :class:`BranchLifecycleResult` carrying the branch name,
        whether it was newly created, the previous branch, and the
        resolved repo root.

    Raises:
        GitUncommittedWorkDetected: The working-tree probe reported
            uncommitted user work. No git command was invoked.
        TrunkBranchWriteRejected: The derived branch name matched
            an entry in ``trunk_allowlist``. No git command was
            invoked.
        subprocess.CalledProcessError: A ``git checkout`` or
            ``git checkout -b`` command failed at the OS layer.
            Sensor-not-advisor — the helper does NOT translate the
            OS error into a marker exception; the caller surfaces
            it as appropriate.
    """
    if repo_root is None:
        repo_root = _default_repo_root()

    # Step 1: Derive branch name.
    branch_name = _branch_name_for_story(story_id)

    # Step 2: Working-tree probe.
    probe_result = working_tree_probe()
    if not probe_result.clean:
        raise GitUncommittedWorkDetected(
            attempted_story_id=story_id,
            uncommitted_paths=probe_result.uncommitted_paths,
        )

    # Step 3: Trunk-allowlist consultation (BEFORE git invocation).
    if branch_name in trunk_allowlist:
        raise TrunkBranchWriteRejected(
            attempted_story_id=story_id,
            attempted_branch=branch_name,
        )

    # Step 4: Capture previous branch (read-only; tolerate failure for
    # detached-HEAD or empty-repo cases).
    previous_result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    previous_branch: str | None
    if previous_result.returncode == 0:
        stdout = previous_result.stdout.strip()
        # git rev-parse --abbrev-ref HEAD prints the literal string "HEAD"
        # (with exit 0) when in detached HEAD state; normalize to None per
        # BranchLifecycleResult.previous_branch's documented contract.
        previous_branch = stdout if (stdout and stdout != "HEAD") else None
    else:
        previous_branch = None

    # Step 5: Check existence of target branch (read-only).
    # Use ``refs/heads/<branch>`` to restrict to local branches only;
    # bare ``branch_name`` would also resolve remote-tracking refs
    # (refs/remotes/…), producing a false positive that triggers DWIM
    # checkout rather than a clean create-and-checkout.
    exists_result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch_name}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    branch_exists = exists_result.returncode == 0

    # Step 6: Checkout existing OR create-and-checkout. ``check=True``
    # so a real git failure propagates as ``subprocess.CalledProcessError``
    # (sensor-not-advisor — the helper does NOT translate OS errors).
    if branch_exists:
        subprocess.run(
            ["git", "checkout", branch_name],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        created = False
    else:
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        created = True

    return BranchLifecycleResult(
        branch_name=branch_name,
        created=created,
        previous_branch=previous_branch,
        repo_root=repo_root,
    )


__all__ = [
    "BranchLifecycleBlocked",
    "BranchLifecycleResult",
    "DEFAULT_TRUNK_ALLOWLIST",
    "GitUncommittedWorkDetected",
    "TrunkBranchWriteRejected",
    "WorkingTreeProbe",
    "WorkingTreeProbeResult",
    "create_story_branch",
    "default_working_tree_probe",
]
