"""Per-story worktree lifecycle module (story 14.2). NFR-R1 + NFR-R2 +
NFR-R3 + NFR-S3 + NFR-O5.

Architectural placement (story 14.1 ADR-009 Consequence 4 verbatim —
"the worktree-lifecycle library Story 14.2 lands is a substrate-**library**
— a sibling of ``branch_lifecycle.py`` and ``run_state.py`` — NOT a sixth
substrate **component**"; ADR-003 Consequence 1 substrate-component
closure at FIVE per architecture.md lines 311-315; epics-phase-2.md
line 109+ substrate-component closure invariant): this module is a
sibling of :mod:`loud_fail_harness.branch_lifecycle` (story 2.3),
:mod:`loud_fail_harness.run_state` (story 2.2),
:mod:`loud_fail_harness.story_doc_validator` (story 1.10b), and the
five substrate-component modules (``envelope_validator``,
``event_validator``, ``reconciler``, ``enumeration_check``,
``fixture_coverage``). It is **NOT a sixth substrate component**. The
substrate-component count stays at FIVE; the harness library count
grows by one (this module).

What this library provides:
    * **Public function** :func:`create_worktree` — single atomic git-write
      via ``git worktree add -b <branch> <path> <base-ref>`` per
      ADR-009 atomicity contract (NFR-R1); consults the trunk-name
      allowlist BEFORE any branch-write; raises typed exceptions on
      pre-existing-worktree / mid-create-crash residue.
    * **Public function** :func:`cleanup_worktree` — idempotent removal
      via ``git worktree remove <path>``; short-circuits with
      ``preserve_on_escalation=True`` when run-state ``current_state``
      is the escalation-terminal value (``escalated``) per ADR-009
      Cleanup-on-merge-ready policy + FR14 + NFR-R5; raises
      ``WorktreeRemoveRefused`` on the canonical
      "contains modified or untracked files" git refusal — NEVER
      escalates to ``--force`` on the default path.
    * **Public function** :func:`inspect_worktree` — read-only single-
      story inspection via ``git worktree list --porcelain``; surfaces
      ``prunable`` + ``locked`` annotations per the documented
      porcelain format (https://git-scm.com/docs/git-worktree).
    * **Public function** :func:`list_active_worktrees` — read-only
      full enumeration via the same git command; tuple-of-results per
      Pattern 4 + Epic 1 retro Action #2.
    * **Pydantic v2 frozen models** :class:`WorktreeLifecycleResult` /
      :class:`WorktreeCleanupResult` / :class:`WorktreeInspectionResult`
      — Pattern 4 state-update discipline; every sequence field is
      ``tuple[…]`` so ``frozen=True`` blocks BOTH attribute
      reassignment AND in-place mutation structurally.
    * **Named-invariant exception hierarchy**
      :class:`WorktreeLifecycleBlocked` →
      :class:`WorktreeAlreadyExistsForStory` /
      :class:`WorktreeStalePartialState` /
      :class:`WorktreeRemoveRefused` — Pattern 5 named-invariant
      diagnostic per architecture.md lines 983-991; all three pin
      ``marker_class="worktree-stale-lock"`` (the single forward-pointer
      string; Story 14.3 enumerates in ``schemas/marker-taxonomy.yaml``
      per ADR-009 Consequence 5 PATCH-bump discipline).

What this library enforces:
    * **NFR-R1** (atomic writes) — ``git worktree add -b <branch>
      <path> <base-ref>`` IS the single atomic create operation per
      ADR-009 atomicity contract: one invocation writes the worktree
      admin dir at ``$GIT_COMMON_DIR/worktrees/<id>/``, the working
      tree at ``<path>``, AND the new branch ref at
      ``refs/heads/<branch>``. No further atomic-write helper is
      needed at this story's landing.
    * **NFR-R2** (crash recovery) — partial state from a mid-create /
      mid-cleanup crash is detectable via the ``prunable`` annotation
      in ``git worktree list --porcelain`` (per ADR-009 "Behaviour on
      crash mid-create / mid-cleanup"). :class:`WorktreeStalePartialState`
      surfaces the residue on subsequent :func:`create_worktree` calls;
      :attr:`WorktreeInspectionResult.is_prunable` surfaces it on
      inspection. :func:`cleanup_worktree` is idempotent — invoking
      against an already-cleaned-up story returns
      ``removed=False, preserved_for_escalation=False`` without raising.
    * **NFR-R3** (PRD line 947) + **NFR-S3** (PRD line 971) extended per
      ADR-009 Interaction-with-NFR-R3 clause (e) verbatim — "NFR-S3's
      banned-verb list is **extended** to also forbid ``git worktree
      remove --force`` from non-escalation paths and ``git worktree
      add --force`` from any path". Encoded structurally as the
      complete absence of ``--force`` token in any ``subprocess.run``
      invocation in this module; verified by
      ``test_worktree_lifecycle_does_not_invoke_force_anywhere``. The
      pre-existing NFR-S3 banned list (``git push`` / ``git push
      --force`` / ``git rebase`` / ``git reset --hard`` / ``git
      clean`` / ``git branch -D`` / ``git branch --delete`` / ``git
      fetch`` / ``git pull`` / ``git merge`` / ``git cherry-pick`` /
      ``git tag`` / ``git remote``) is preserved verbatim — none of
      these subcommands are invoked from this module under any code
      path.
    * **NFR-O5** (PRD line 984) + **Pattern 5** (architecture.md lines
      983-991) — named diagnostic per failure class. Each exception
      class carries a ``marker_class`` string identifier; the
      ``__str__`` form includes an actionable-fix-pointer.
      Sensor-not-advisor: the library RAISES typed exceptions; the
      caller (orchestrator skill via its envelope + the orchestrator-
      event log per ADR-001) EMITS the marker. The library does NOT
      log, print, auto-prune, auto-remove, or auto-cleanup.

Sensor-not-advisor (PRD-level invariant + Pattern 5):

    The library RAISES typed exceptions
    (:exc:`WorktreeAlreadyExistsForStory`,
    :exc:`WorktreeStalePartialState`, :exc:`WorktreeRemoveRefused`)
    carrying ``marker_class="worktree-stale-lock"`` identifiers on the
    diagnostic path; it does NOT emit markers itself, does NOT
    auto-prune, does NOT auto-remove, does NOT log, does NOT print.
    Same posture as 1.10b (``story_doc_validator``), 2.2
    (``run_state``), and 2.3 (``branch_lifecycle``). The calling
    specialist (orchestrator skill in Story 2.5+; per-story-worktree
    dispatch in Epic 18) emits the marker via its envelope + the
    orchestrator's event log per ADR-001 + Pattern 5. The
    ``worktree-stale-lock`` enumeration in
    ``schemas/marker-taxonomy.yaml`` is Story 14.3's deliverable per
    ADR-009 Consequence 5; at this story's landing the marker-class
    string is a forward-pointer in code only (the contract-pair
    pattern's in-code reference is what gets validated when Story 14.3
    lands its enumeration).

``find_repo_root()`` discipline (Epic 1 retro Action #1):

    Epic 1 retrospective Challenge #1 (line 55) flagged
    ``find_repo_root()`` called at module import time, raising
    ``RuntimeError`` when pytest is invoked outside the repo root.
    Action #1 (line 106) targets this risk for every downstream module.

    This module honors the discipline: ``find_repo_root()`` is NOT
    called at module top-level. The :func:`create_worktree` /
    :func:`cleanup_worktree` / :func:`inspect_worktree` /
    :func:`list_active_worktrees` helpers each take ``repo_root:
    pathlib.Path | None = None`` from the caller; if ``None``, the
    helper computes it lazily via :func:`_default_repo_root` (which
    calls ``find_repo_root()`` at function-call time, not at import
    time). Tests use ``tmp_path`` fixtures that supply ``repo_root``
    explicitly — no ``find_repo_root()`` involvement at module
    collection time.

FR62 pluggability classification:

    This module is *substrate-shared library* per Story 1.10b's
    precedent (``story_doc_validator.py``), Story 2.2's precedent
    (``run_state.py``), and Story 2.3's precedent
    (``branch_lifecycle.py``). The FR62 gate (Story 1.10a's
    :mod:`loud_fail_harness.pluggability_gate`) flags cross-references
    between specialist subagents (Dev, Review-BMAD, QA, LAD under
    ``agents/*.md``); it does NOT flag substrate cross-imports. The
    ``worktree_lifecycle`` → ``branch_lifecycle`` direction (this
    module imports :func:`branch_lifecycle._branch_name_for_story` +
    :exc:`branch_lifecycle.TrunkBranchWriteRejected`) is structurally
    permitted. The REVERSE direction
    (``branch_lifecycle → worktree_lifecycle``) is FORBIDDEN — it
    would create a cycle and violate ADR-009 Consequence 3
    "``branch_lifecycle.py`` is preserved unchanged by this story".

Forward-compat consumers:

    Stories that will consume this library exclusively (no direct
    ``git worktree``-form invocation outside this module's public
    surface — Pattern 5 + NFR-S3 enforcement):

        * Story 14.3 — story-file locking protocol: composes
          :func:`inspect_worktree` for SessionStart's stale-lock
          detection; enumerates the ``worktree-stale-lock`` marker
          class in ``schemas/marker-taxonomy.yaml`` (the PATCH-bump
          completing the forward-pointer pinned by this story).
        * Story 14.4 — epic-run-state schema with per-worktree
          run-state addressing: consumes :func:`list_active_worktrees`
          to enumerate the worktrees an epic run owns.
        * Story 14.5 — parallel-story state-pollution marker:
          consumes :func:`inspect_worktree` to discriminate
          cross-worktree state writes.
        * Story 14.6 — Epic-14 reference fixture: invokes the full
          create + inspect + cleanup cycle as the end-to-end
          substrate-smoke witness.
        * Epic 15 — sequential epic orchestration: composes
          :func:`create_worktree` + :func:`cleanup_worktree` for
          per-story isolation under ``parallel_stories: false``.
        * Epic 18 — parallel-story execution: pure-flip-the-switch
          activation against this already-witnessed substrate.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import threading

import yaml
from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.branch_lifecycle import (
    TrunkBranchWriteRejected,
    _branch_name_for_story,
)
from loud_fail_harness import run_state as _run_state_mod
from loud_fail_harness.run_state import DEFAULT_RUN_STATE_PATH


#: Marker-class string identifier for the stale-lock / mid-create /
#: mid-cleanup-crash-residue / remove-refused diagnostics. Single
#: constant because all three new exception subclasses pin to the
#: same class string per ADR-009 Consequence 5 + Story 14.2 AC-3 —
#: sub-classifications, if any, land in Story 14.3 per the PATCH-bump
#: discipline. Forward-pointer at this story's landing: the
#: enumeration in ``schemas/marker-taxonomy.yaml`` is Story 14.3's
#: deliverable (per ADR-009 Consequence 5); the in-code string
#: reference is the contract-pair anchor.
_MARKER_WORKTREE_STALE_LOCK: str = "worktree-stale-lock"


# git's .git/worktrees/ admin tree is shared across all per-story worktrees;
# concurrent `git worktree add`/`remove` race on a sibling's half-written
# commondir (errno-0 read failure under parallel dispatch). Serialize the
# mutating check-then-act sections — the dispatcher is single-process
# (ThreadPoolExecutor), so an in-process lock is sufficient. The git ops are
# fast and the story loops run after the lock releases, so story-level
# parallelism is unaffected.
_WORKTREE_ADMIN_LOCK = threading.Lock()


#: Canonical escalation-terminal ``current_state`` value (per the
#: closed :data:`loud_fail_harness.run_state.CurrentState` Literal
#: enum). The ``escalated`` state is the post-retry-budget-exhausted
#: rest-state (FR14 / NFR-R5) at which :func:`cleanup_worktree` with
#: ``preserve_on_escalation=True`` short-circuits to preserve the
#: worktree alongside the branch + run-state file for human
#: inspection per ADR-009 Cleanup-on-merge-ready policy verbatim.
#: Conservative discipline (Story 14.2 AC-5 step 4): the substrate
#: does NOT expand into ``lifecycle_state_machine`` internals; only
#: the single ``escalated`` literal triggers the short-circuit. Story
#: 14.4 may rationalize per-worktree addressing as run-state
#: surfaces grow.
_ESCALATION_TERMINAL_STATES: frozenset[str] = frozenset({"escalated"})


#: Regex for parsing the ``git --version`` style numeric component of
#: a worktree-list entry's ``HEAD <40-char-hex>`` SHA. The SHA shape
#: is documented at https://git-scm.com/docs/git-worktree under
#: "LIST OUTPUT FORMAT".
_SHA_FULL_PATTERN: re.Pattern[str] = re.compile(r"^[0-9a-f]{40}$")


def _default_repo_root() -> pathlib.Path:
    """Resolve the canonical repo root via :func:`loud_fail_harness.
    _shared.find_repo_root` at function-call time (Epic 1 retro
    Action #1 discipline — never at module import time).
    """
    return find_repo_root()


def _default_worktrees_root(repo_root: pathlib.Path) -> pathlib.Path:
    """Compute the default per-story-worktrees directory path under
    ``repo_root``.

    Path convention: ``<repo_root>/_bmad/automation/worktrees/`` per
    ADR-009 Decision section. Co-located with
    ``_bmad/automation/run-state.yaml`` (Story 2.2 surface).
    Namespace-disjoint from ``.claude/worktrees/`` (Claude Code's
    session-scoped worktree namespace) per ADR-009 Rationale bullet 4.
    """
    return repo_root / "_bmad" / "automation" / "worktrees"


class WorktreeLifecycleResult(BaseModel):
    """Return shape of a successful :func:`create_worktree` call.

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``story_id`` — the BMAD story identifier the worktree was
          created for.
        * ``branch_name`` — the per-story branch name derived via
          :func:`branch_lifecycle._branch_name_for_story` so the
          worktree's branch matches the Phase-1 canonical
          convention ``bmad-automation/story/<story-id>``.
        * ``worktree_path`` — the on-disk path of the worktree's
          working tree.
        * ``created`` — ``True`` when the worktree was newly created
          via the single atomic ``git worktree add -b`` invocation;
          ``False`` when an idempotent existing-worktree path
          returned without a git-write (this story does NOT take an
          idempotent re-checkout path — existing worktrees raise
          :exc:`WorktreeAlreadyExistsForStory` per AC-4 step 5 — so
          ``created`` is always ``True`` on a successful return; the
          field exists for symmetry with
          :class:`branch_lifecycle.BranchLifecycleResult` and for
          forward-compatibility with a future
          ``allow_existing=True``-style escalation surface that is
          deliberately out-of-scope here).
        * ``base_ref`` — the ref the worktree was created from
          (passed through as recorded by the caller).
        * ``repo_root`` — the resolved repo root the git operations
          ran against.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str
    branch_name: str = Field(min_length=1)
    worktree_path: pathlib.Path
    created: bool
    base_ref: str
    repo_root: pathlib.Path


class WorktreeCleanupResult(BaseModel):
    """Return shape of a :func:`cleanup_worktree` call.

    Frozen + sequence-typed-as-``tuple[…]`` per Epic 1 retro Action
    #2. The model has no sequence fields at this story's landing;
    the frozen-tuple discipline is preserved for forward-compat.

    Field semantics:
        * ``story_id`` — the BMAD story identifier cleanup targeted.
        * ``worktree_path`` — the on-disk path cleanup targeted.
        * ``removed`` — ``True`` when ``git worktree remove`` ran and
          exited 0; ``False`` when (a) ``preserve_on_escalation=True``
          short-circuited because run-state ``current_state`` is in
          :data:`_ESCALATION_TERMINAL_STATES`, OR (b) the worktree
          did not exist when cleanup was invoked (idempotent
          short-circuit per NFR-R2), OR (c) the existing record has
          a ``prunable`` annotation (mid-cleanup-crash residue;
          operator runs ``git worktree prune`` per the
          documented-remediation surface per Story 14.2 design
          notes).
        * ``preserved_for_escalation`` — ``True`` when the
          ``preserve_on_escalation=True`` short-circuit fired; mutually
          exclusive with ``removed=True``.
        * ``repo_root`` — the resolved repo root the git operations
          ran against.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str
    worktree_path: pathlib.Path
    removed: bool
    preserved_for_escalation: bool
    repo_root: pathlib.Path


class WorktreeInspectionResult(BaseModel):
    """Return shape of a :func:`inspect_worktree` call OR a single
    element of the :func:`list_active_worktrees` tuple.

    Frozen + sequence-typed-as-``tuple[…]`` per Epic 1 retro Action
    #2; no sequence fields at this story's landing.

    Field semantics:
        * ``story_id`` — the derived BMAD story identifier when the
          worktree's path matches the
          ``<repo>/_bmad/automation/worktrees/<story-id>/`` convention;
          ``None`` when the worktree's path does not match (covers
          the main repo's worktree and any non-bmad-automation
          worktrees co-existing under the same repo). Discrimination
          by ``story_id`` is the caller's responsibility.
        * ``worktree_path`` — the absolute on-disk path of the
          worktree's working tree (as reported by ``git worktree list
          --porcelain``).
        * ``branch`` — the resolved branch ref short-name (e.g.,
          ``"bmad-automation/story/2-3"``); ``None`` when the
          worktree is in detached-HEAD state (the porcelain output
          carries the literal ``detached`` annotation line).
        * ``head_sha`` — 40-char lowercase hex SHA of the worktree's
          HEAD; ``None`` for missing-tree / not-reported cases.
        * ``is_prunable`` — ``True`` when the porcelain record
          carries a ``prunable`` annotation (the working tree is
          missing on disk; the admin dir is orphaned; mid-create or
          mid-cleanup crash residue per ADR-009 "Behaviour on crash
          mid-create / mid-cleanup").
        * ``is_locked`` — ``True`` when the porcelain record carries
          a ``locked`` annotation (the operator manually invoked
          ``git worktree lock``; not auto-set by this module under
          any code path).
        * ``prunable_reason`` — the post-colon prose from the
          porcelain ``prunable: <reason>`` line (e.g.,
          ``"gitdir file points to non-existent location"``);
          ``None`` when ``is_prunable`` is False OR when the
          ``prunable`` annotation appeared without a reason.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str | None
    worktree_path: pathlib.Path
    branch: str | None
    head_sha: str | None
    is_prunable: bool
    is_locked: bool
    prunable_reason: str | None


class WorktreeLifecycleBlocked(Exception):
    """Base exception class for any structural rejection from
    :func:`create_worktree` / :func:`cleanup_worktree`.

    Pattern 5 named-invariant diagnostic (architecture.md lines
    983-991): the exception surfaces both the upstream cause AND the
    attempted-story-id + attempted-worktree-path so the diagnostic
    envelope can render a complete picture (what the orchestrator was
    trying to do, what the on-disk state was, and what blocked it).
    Subclasses pin ``marker_class`` to ``"worktree-stale-lock"`` (the
    single forward-pointer string per ADR-009 Consequence 5; Story
    14.3 enumerates).

    Distinct base class from :exc:`branch_lifecycle.BranchLifecycleBlocked`
    (the two surfaces' ``cause`` carriers diverge structurally — branch
    lifecycle carries :class:`WorkingTreeProbeResult` evidence, worktree
    lifecycle carries :class:`WorktreeInspectionResult` evidence — so a
    common parent would constrain ``cause``'s type to ``object``,
    losing the per-surface Pattern-5 typing the diagnostic surface
    relies on).

    Attributes:
        attempted_story_id: The ``story_id`` argument the caller
            passed to the entry-point.
        attempted_worktree_path: The on-disk path the entry-point
            was about to act on; ``None`` when the rejection fired
            before any path computation.
        marker_class: ``"worktree-stale-lock"`` for every subclass.
        cause: The upstream signal (a
            :class:`WorktreeInspectionResult` when the rejection
            fired because the porcelain probe surfaced an unexpected
            on-disk state; a :class:`BaseException` propagated from
            a subprocess failure; ``None`` for purely structural
            rejections).
    """

    def __init__(
        self,
        *,
        attempted_story_id: str,
        attempted_worktree_path: pathlib.Path | None,
        marker_class: str,
        message: str,
        cause: BaseException | WorktreeInspectionResult | None = None,
    ) -> None:
        self.attempted_story_id: str = attempted_story_id
        self.attempted_worktree_path: pathlib.Path | None = attempted_worktree_path
        self.marker_class: str = marker_class
        self.cause: BaseException | WorktreeInspectionResult | None = cause
        super().__init__(message)


class WorktreeAlreadyExistsForStory(WorktreeLifecycleBlocked):
    """Raised by :func:`create_worktree` when the target worktree path
    OR the derived branch name is already registered by ``git worktree
    list --porcelain`` (with a non-prunable record).

    The substrate REFUSES to silently re-checkout into an existing
    worktree — the operator (not the substrate) decides whether to
    invoke cleanup-then-retry. Git itself would refuse the
    ``git worktree add`` without ``--force``; the substrate surfaces
    the refusal as a typed exception BEFORE the git invocation when
    the conflict is detectable via the porcelain probe, and via
    ``subprocess.CalledProcessError`` when the conflict is race-
    detected by git itself during ``add`` (sensor-not-advisor — the
    helper does NOT translate that OS error into this marker
    exception path).
    """

    def __init__(
        self,
        *,
        attempted_story_id: str,
        attempted_worktree_path: pathlib.Path,
        attempted_branch_name: str,
        existing_record: WorktreeInspectionResult | None = None,
    ) -> None:
        self.attempted_branch_name = attempted_branch_name
        message = (
            f"Worktree for story {attempted_story_id!r} already exists at "
            f"{attempted_worktree_path}. Run cleanup before re-creating; "
            f"the substrate refuses to re-checkout into an existing worktree "
            f"on the default path (NFR-S3 banned-verb extension forbids "
            f"`git worktree add --force`). Inspect via "
            f"`git worktree list` and remediate before retry."
        )
        super().__init__(
            attempted_story_id=attempted_story_id,
            attempted_worktree_path=attempted_worktree_path,
            marker_class=_MARKER_WORKTREE_STALE_LOCK,
            message=message,
            cause=existing_record,
        )


class WorktreeStalePartialState(WorktreeLifecycleBlocked):
    """Raised by :func:`create_worktree` when ``git worktree list
    --porcelain`` reports an existing record for the target path
    WHOSE working tree is missing on disk (the canonical
    mid-create / mid-cleanup crash inconsistency per ADR-009
    "Behaviour on crash mid-create / mid-cleanup").

    Remediation is ``git worktree prune`` (NOT
    ``git worktree remove --force``; the substrate never invokes
    ``--force`` on the default path per NFR-S3 banned-verb extension
    per ADR-009 Interaction-with-NFR-R3 clause e). The operator runs
    the prune as the explicit recovery surface; the substrate does
    NOT auto-prune on the practitioner's behalf (same posture as
    :mod:`branch_lifecycle` not auto-stashing).
    """

    def __init__(
        self,
        *,
        attempted_story_id: str,
        attempted_worktree_path: pathlib.Path,
        stale_record: WorktreeInspectionResult | None = None,
    ) -> None:
        message = (
            f"Worktree for story {attempted_story_id!r} has stale partial "
            f"state at {attempted_worktree_path} (admin dir present, working "
            f"tree missing — mid-create / mid-cleanup crash residue). Run "
            f"`git worktree prune` to remediate; the substrate refuses to "
            f"silently overwrite stale state. See ADR-009 "
            f"\"Behaviour on crash mid-create / mid-cleanup\"."
        )
        super().__init__(
            attempted_story_id=attempted_story_id,
            attempted_worktree_path=attempted_worktree_path,
            marker_class=_MARKER_WORKTREE_STALE_LOCK,
            message=message,
            cause=stale_record,
        )


class WorktreeRemoveRefused(WorktreeLifecycleBlocked):
    """Raised by :func:`cleanup_worktree` when ``git worktree remove
    <path>`` exits non-zero with the canonical
    "contains modified or untracked files" refusal.

    The operator decides whether to escalate to ``--force`` per
    NFR-R3 (the substrate's default path NEVER escalates per NFR-S3
    banned-verb extension per ADR-009 Interaction-with-NFR-R3
    clause e). The substrate surfaces the refusal as the loud-fail
    diagnostic; the operator inspects the worktree, commits or
    stashes the unwanted modifications, then re-runs cleanup OR
    manually invokes ``git worktree remove --force <path>`` outside
    the substrate.
    """

    def __init__(
        self,
        *,
        attempted_story_id: str,
        attempted_worktree_path: pathlib.Path,
        stderr: str | None = None,
    ) -> None:
        self.stderr = stderr
        message = (
            f"Worktree for story {attempted_story_id!r} at "
            f"{attempted_worktree_path} refused removal (contains modified "
            f"or untracked files). Inspect, commit, or stash the changes "
            f"before re-running cleanup; the substrate's default path NEVER "
            f"escalates to `git worktree remove --force` (NFR-S3 banned-verb "
            f"extension per ADR-009)."
        )
        super().__init__(
            attempted_story_id=attempted_story_id,
            attempted_worktree_path=attempted_worktree_path,
            marker_class=_MARKER_WORKTREE_STALE_LOCK,
            message=message,
            cause=None,
        )


def _parse_worktree_list_porcelain(
    stdout: str,
    worktrees_root: pathlib.Path,
) -> tuple[WorktreeInspectionResult, ...]:
    """Parse the ``git worktree list --porcelain`` output into a tuple
    of :class:`WorktreeInspectionResult`.

    Output format (https://git-scm.com/docs/git-worktree under "LIST
    OUTPUT FORMAT"): label-per-line, label-value pairs separated by
    a single space, boolean annotations label-only, empty line ends
    each record, first attribute of every record is ``worktree
    <path>``. Annotations recognized: ``HEAD <sha>``, ``branch
    refs/heads/<name>``, ``detached``, ``locked [<reason>]``,
    ``prunable [<reason>]``, ``bare`` (skipped — no working tree).

    Defensive-parse posture mirroring
    :func:`branch_lifecycle.default_working_tree_probe._probe` lines
    571-587: malformed records are skipped without raising; only
    records with a parseable ``worktree`` first-line attribute are
    surfaced. Returns an empty tuple on empty input.
    """
    records: list[WorktreeInspectionResult] = []
    worktrees_root_resolved = worktrees_root.resolve()
    current_path: pathlib.Path | None = None
    current_head: str | None = None
    current_branch: str | None = None
    current_prunable: bool = False
    current_prunable_reason: str | None = None
    current_locked: bool = False
    current_bare: bool = False

    def _flush() -> None:
        nonlocal current_path, current_head, current_branch
        nonlocal current_prunable, current_prunable_reason
        nonlocal current_locked, current_bare
        if current_path is not None and not current_bare:
            story_id = _derive_story_id(current_path, worktrees_root_resolved)
            records.append(
                WorktreeInspectionResult(
                    story_id=story_id,
                    worktree_path=current_path,
                    branch=current_branch,
                    head_sha=current_head,
                    is_prunable=current_prunable,
                    is_locked=current_locked,
                    prunable_reason=current_prunable_reason,
                )
            )
        current_path = None
        current_head = None
        current_branch = None
        current_prunable = False
        current_prunable_reason = None
        current_locked = False
        current_bare = False

    for line in stdout.splitlines():
        if not line.strip():
            _flush()
            continue
        label, _, value = line.partition(" ")
        if label == "worktree":
            # Start of a new record. Flush any prior unterminated
            # record defensively (the porcelain format guarantees
            # empty-line separators, but absent ones are tolerated).
            _flush()
            try:
                current_path = pathlib.Path(value).resolve()
            except (OSError, ValueError):
                current_path = pathlib.Path(value)
        elif label == "HEAD":
            if _SHA_FULL_PATTERN.match(value):
                current_head = value
        elif label == "branch":
            # value is ``refs/heads/<name>`` per documented format;
            # strip the prefix defensively (tolerates absence).
            if value.startswith("refs/heads/"):
                current_branch = value[len("refs/heads/"):]
            else:
                current_branch = value
        elif label == "detached":
            current_branch = None
        elif label == "locked":
            current_locked = True
        elif label == "prunable":
            current_prunable = True
            current_prunable_reason = value or None
        elif label == "bare":
            current_bare = True
        # Unrecognized labels are silently skipped (forward-compat
        # with future porcelain extensions per the documented stability
        # contract).

    # Trailing record without an empty-line terminator.
    _flush()

    return tuple(records)


def _derive_story_id(
    worktree_path: pathlib.Path,
    worktrees_root_resolved: pathlib.Path,
) -> str | None:
    """Derive a story-id from a worktree path IFF the path is a
    direct child of ``<repo>/_bmad/automation/worktrees/``.

    Concrete path-component check per AC-6 (NOT a regex): the parent
    of the worktree path must equal ``worktrees_root_resolved``. Any
    path not under the canonical namespace returns ``None``, which is
    the caller's signal that this entry is the main worktree or a
    non-bmad-automation worktree co-existing under the same repo.
    """
    try:
        if worktree_path.parent.resolve() == worktrees_root_resolved:
            return worktree_path.name
    except (OSError, ValueError):
        return None
    return None


def _read_current_state(repo_root: pathlib.Path) -> str | None:
    """Read ``current_state`` from ``<repo_root>/<DEFAULT_RUN_STATE_PATH>``
    defensively, via ``run_state.RunState`` Pydantic parsing per AC-5 step 4.

    Returns the string value when the YAML file exists, parses, and
    the resulting :class:`~loud_fail_harness.run_state.RunState` model
    is valid. Returns ``None`` on missing file / YAML parse failure /
    Pydantic validation failure — the caller (:func:`cleanup_worktree`)
    treats ``None`` as "no escalation-terminal state detected, proceed
    with cleanup" rather than as a fatal error. Conservative discipline
    per Story 14.2 AC-5 step 4.
    """
    run_state_path = repo_root / DEFAULT_RUN_STATE_PATH
    try:
        text = run_state_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        parsed = _run_state_mod.RunState(**data)
    except Exception:
        return None
    return parsed.current_state


def create_worktree(
    story_id: str,
    *,
    base_ref: str,
    trunk_allowlist: tuple[str, ...],
    worktrees_root: pathlib.Path | None = None,
    repo_root: pathlib.Path | None = None,
) -> WorktreeLifecycleResult:
    """Create a per-story worktree for ``story_id`` against ``base_ref``,
    after the trunk-allowlist consultation passes and no existing
    worktree (healthy OR stale) blocks the create.

    Execution order (load-bearing per NFR-R1 + NFR-R3 + NFR-S3 +
    Pattern 5; per Story 14.2 AC-4):

        1. Resolve ``repo_root`` (lazy :func:`_default_repo_root` when
           ``None``) + ``worktrees_root`` (default
           ``<repo_root>/_bmad/automation/worktrees`` when ``None``).
        2. Derive ``branch_name`` via
           :func:`branch_lifecycle._branch_name_for_story` — the
           canonical convention. The branch is created by
           ``git worktree add -b`` (one atomic invocation per
           ADR-009); we do NOT compose a second
           :func:`branch_lifecycle.create_story_branch` call because
           that would produce two write paths against the same branch
           ref and break NFR-R2 idempotency.
        3. Check ``branch_name`` against ``trunk_allowlist`` —
           exact-string-match per NFR-S3. Match raises
           :exc:`branch_lifecycle.TrunkBranchWriteRejected`
           (re-using the Phase-1 exception class because the
           rejection semantics + marker class are identical at the
           branch-name altitude).
        4. Compute ``worktree_path = worktrees_root / story_id``.
        5. Invoke ``git worktree list --porcelain`` (read-only).
           If an existing record matches ``worktree_path``:
             * Prunable annotation present → raise
               :exc:`WorktreeStalePartialState`.
             * Otherwise → raise :exc:`WorktreeAlreadyExistsForStory`.
        6. If an existing record matches ``branch_name`` at a
           different path → raise :exc:`WorktreeAlreadyExistsForStory`.
        7. Ensure ``worktrees_root`` exists on disk (idempotent
           ``mkdir(parents=True, exist_ok=True)`` — no race window;
           atomic at the OS layer).
        8. Invoke ``git worktree add -b <branch_name> <worktree_path>
           <base_ref>`` via ``subprocess.run`` list-form (NEVER
           ``shell=True``). This is the SINGLE atomic create
           operation per ADR-009 NFR-R1 contract.
        9. Return :class:`WorktreeLifecycleResult`.

    Args:
        story_id: The BMAD story identifier (e.g., ``"14-2"``).
        base_ref: The git ref the worktree is created from (e.g.,
            ``"main"``, ``"origin/main"``, a commit SHA). Keyword-only
            AND non-defaulted; omitting it raises ``TypeError`` at
            call time per Python's missing-required-keyword-argument
            semantics.
        trunk_allowlist: The tuple of branch names to reject as
            protected trunk branches. Exact-string-match. Keyword-only
            AND non-defaulted.
        worktrees_root: The parent directory under which the new
            worktree is placed; defaults to
            ``<repo_root>/_bmad/automation/worktrees``. The parameter
            exists primarily so tests inject ``tmp_path`` without
            monkey-patching.
        repo_root: The repository root for the git operations
            (passed as ``cwd`` to ``subprocess.run``). Defaults to
            ``None``; resolved lazily via :func:`_default_repo_root`
            at function-call time per Epic 1 retro Action #1
            discipline.

    Returns:
        :class:`WorktreeLifecycleResult` carrying the story id,
        branch name, worktree path, ``created=True``, base ref, and
        resolved repo root.

    Raises:
        branch_lifecycle.TrunkBranchWriteRejected: The derived
            branch name matched an entry in ``trunk_allowlist``. No
            git command was invoked (re-used Phase-1 exception class).
        WorktreeAlreadyExistsForStory: A worktree already exists at
            the target path OR the derived branch name is already
            checked out elsewhere. No git-write was invoked.
        WorktreeStalePartialState: A stale worktree-admin record
            exists at the target path WHOSE working tree is missing
            on disk. No git-write was invoked.
        subprocess.CalledProcessError: ``git worktree add`` exited
            non-zero (e.g., invalid base_ref, race-detected duplicate,
            git binary I/O failure). Sensor-not-advisor — the helper
            does NOT translate the OS error into a marker exception;
            the caller surfaces per its envelope discipline.
    """
    if repo_root is None:
        repo_root = _default_repo_root()
    if worktrees_root is None:
        worktrees_root = _default_worktrees_root(repo_root)

    branch_name = _branch_name_for_story(story_id)

    if branch_name in trunk_allowlist:
        raise TrunkBranchWriteRejected(
            attempted_story_id=story_id,
            attempted_branch=branch_name,
        )

    worktree_path = worktrees_root / story_id

    with _WORKTREE_ADMIN_LOCK:
        existing_records = _list_porcelain(repo_root, worktrees_root)
        target_resolved = _safe_resolve(worktree_path)
        for record in existing_records:
            record_resolved = _safe_resolve(record.worktree_path)
            if record_resolved == target_resolved:
                if record.is_prunable:
                    raise WorktreeStalePartialState(
                        attempted_story_id=story_id,
                        attempted_worktree_path=worktree_path,
                        stale_record=record,
                    )
                raise WorktreeAlreadyExistsForStory(
                    attempted_story_id=story_id,
                    attempted_worktree_path=worktree_path,
                    attempted_branch_name=branch_name,
                    existing_record=record,
                )
            if record.branch == branch_name:
                raise WorktreeAlreadyExistsForStory(
                    attempted_story_id=story_id,
                    attempted_worktree_path=worktree_path,
                    attempted_branch_name=branch_name,
                    existing_record=record,
                )

        worktrees_root.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "-b",
                branch_name,
                str(worktree_path),
                base_ref,
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )

    return WorktreeLifecycleResult(
        story_id=story_id,
        branch_name=branch_name,
        worktree_path=worktree_path,
        created=True,
        base_ref=base_ref,
        repo_root=repo_root,
    )


def cleanup_worktree(
    story_id: str,
    *,
    preserve_on_escalation: bool = True,
    worktrees_root: pathlib.Path | None = None,
    repo_root: pathlib.Path | None = None,
) -> WorktreeCleanupResult:
    """Remove the per-story worktree for ``story_id`` via ``git worktree
    remove <path>``, with a ``preserve_on_escalation`` short-circuit on
    escalation-terminal run-state.

    Execution order (per Story 14.2 AC-5):

        1. Resolve ``repo_root`` + ``worktrees_root`` lazily.
        2. Compute ``worktree_path = worktrees_root / story_id``.
        3. Read ``git worktree list --porcelain`` and find the
           record matching ``worktree_path``. If no record exists →
           return ``WorktreeCleanupResult(removed=False,
           preserved_for_escalation=False, ...)`` (idempotent
           cleanup per NFR-R2).
        4. If the matched record is annotated ``prunable`` (mid-
           cleanup-crash residue), return ``removed=False,
           preserved_for_escalation=False`` without invoking ``git
           worktree remove`` — the operator runs ``git worktree
           prune`` as the documented remediation surface. A prunable
           worktree has no working tree on disk; there is nothing to
           preserve, so this check fires BEFORE the escalation
           short-circuit. Conservative path per Story 14.2 design
           notes; avoids confusing failure modes from ``remove``
           against a path with no working tree.
        5. ``preserve_on_escalation=True`` short-circuit: read
           ``<repo_root>/_bmad/automation/run-state.yaml``. If
           ``current_state`` is in :data:`_ESCALATION_TERMINAL_STATES`,
           return ``preserved_for_escalation=True`` without invoking
           ``git worktree remove`` (the worktree is preserved
           alongside the branch + run-state file for human inspection
           per ADR-009 Cleanup-on-merge-ready policy + FR14 +
           NFR-R5).
        6. Invoke ``git worktree remove <worktree_path>`` via
           ``subprocess.run`` list-form (NEVER ``shell=True``,
           NEVER ``--force``).
             * Exit 0 → ``removed=True``.
             * Exit non-zero + stderr matches "contains modified" OR
               "contains untracked" → raise
               :exc:`WorktreeRemoveRefused`.
             * Other non-zero → ``subprocess.CalledProcessError``
               propagates.
        7. Return :class:`WorktreeCleanupResult`.

    The function has NO ``--force`` code path. NFR-R3 + NFR-S3
    banned-verb extension per ADR-009 Interaction-with-NFR-R3 clause
    (e) verbatim.

    Args:
        story_id: The BMAD story identifier the worktree belongs to.
        preserve_on_escalation: When ``True`` (default per
            epics-phase-2.md line 305), the function short-circuits
            without removing the worktree if run-state
            ``current_state`` is escalation-terminal. Keyword-only.
        worktrees_root: The parent directory the worktree lives under;
            defaults to
            ``<repo_root>/_bmad/automation/worktrees``.
        repo_root: The repository root; defaults to ``None`` (lazy
            via :func:`_default_repo_root`).

    Returns:
        :class:`WorktreeCleanupResult`.

    Raises:
        WorktreeRemoveRefused: ``git worktree remove`` refused
            because the worktree contains modified or untracked
            files; the substrate's default path NEVER escalates to
            ``--force``.
        subprocess.CalledProcessError: ``git worktree remove`` exited
            non-zero for any other reason (e.g., git binary I/O
            failure).
    """
    if repo_root is None:
        repo_root = _default_repo_root()
    if worktrees_root is None:
        worktrees_root = _default_worktrees_root(repo_root)

    worktree_path = worktrees_root / story_id

    with _WORKTREE_ADMIN_LOCK:
        records = _list_porcelain(repo_root, worktrees_root)
        target_resolved = _safe_resolve(worktree_path)
        matched: WorktreeInspectionResult | None = None
        for record in records:
            if _safe_resolve(record.worktree_path) == target_resolved:
                matched = record
                break

        if matched is None:
            return WorktreeCleanupResult(
                story_id=story_id,
                worktree_path=worktree_path,
                removed=False,
                preserved_for_escalation=False,
                repo_root=repo_root,
            )

        if matched.is_prunable:
            return WorktreeCleanupResult(
                story_id=story_id,
                worktree_path=worktree_path,
                removed=False,
                preserved_for_escalation=False,
                repo_root=repo_root,
            )

        if preserve_on_escalation:
            current_state = _read_current_state(repo_root)
            if current_state in _ESCALATION_TERMINAL_STATES:
                return WorktreeCleanupResult(
                    story_id=story_id,
                    worktree_path=worktree_path,
                    removed=False,
                    preserved_for_escalation=True,
                    repo_root=repo_root,
                )

        result = subprocess.run(
            ["git", "worktree", "remove", str(worktree_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr_lower = (result.stderr or "").lower()
            if (
                "contains modified" in stderr_lower
                or "contains untracked" in stderr_lower
            ):
                raise WorktreeRemoveRefused(
                    attempted_story_id=story_id,
                    attempted_worktree_path=worktree_path,
                    stderr=result.stderr,
                )
            # Other non-zero exits propagate per sensor-not-advisor — the
            # caller decides escalation.
            raise subprocess.CalledProcessError(
                returncode=result.returncode,
                cmd=result.args,
                output=result.stdout,
                stderr=result.stderr,
            )

    return WorktreeCleanupResult(
        story_id=story_id,
        worktree_path=worktree_path,
        removed=True,
        preserved_for_escalation=False,
        repo_root=repo_root,
    )


def inspect_worktree(
    story_id: str,
    *,
    worktrees_root: pathlib.Path | None = None,
    repo_root: pathlib.Path | None = None,
) -> WorktreeInspectionResult | None:
    """Return the :class:`WorktreeInspectionResult` for ``story_id``'s
    worktree, or ``None`` if no record matches.

    Path-equality after :meth:`pathlib.Path.resolve` to handle
    symlink-form repos. Read-only — invokes only ``git worktree list
    --porcelain``.
    """
    if repo_root is None:
        repo_root = _default_repo_root()
    if worktrees_root is None:
        worktrees_root = _default_worktrees_root(repo_root)

    worktree_path = worktrees_root / story_id
    target_resolved = _safe_resolve(worktree_path)

    for record in _list_porcelain(repo_root, worktrees_root):
        if _safe_resolve(record.worktree_path) == target_resolved:
            return record
    return None


def list_active_worktrees(
    *,
    repo_root: pathlib.Path | None = None,
) -> tuple[WorktreeInspectionResult, ...]:
    """Return the full tuple of :class:`WorktreeInspectionResult` for
    every worktree the repo registers (including the main worktree
    and any non-bmad-automation worktrees).

    Discrimination by ``story_id`` is the caller's responsibility
    via :attr:`WorktreeInspectionResult.story_id` (``None`` for paths
    not matching the ``_bmad/automation/worktrees/<story-id>/``
    convention).

    Read-only — invokes only ``git worktree list --porcelain``.
    """
    if repo_root is None:
        repo_root = _default_repo_root()
    worktrees_root = _default_worktrees_root(repo_root)
    return _list_porcelain(repo_root, worktrees_root)


def _list_porcelain(
    repo_root: pathlib.Path,
    worktrees_root: pathlib.Path,
) -> tuple[WorktreeInspectionResult, ...]:
    """Run ``git worktree list --porcelain`` against ``repo_root`` and
    parse the output. ``check=True`` so a real git failure propagates
    (sensor-not-advisor).
    """
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return _parse_worktree_list_porcelain(result.stdout, worktrees_root)


def _safe_resolve(path: pathlib.Path) -> pathlib.Path:
    """Best-effort :meth:`pathlib.Path.resolve` that falls back to the
    un-resolved path when the underlying OS call would raise (e.g.,
    missing intermediate directories on some platforms). Tolerated
    because ``cleanup_worktree`` / :func:`inspect_worktree` deliberately
    compare paths whose targets may be missing on disk (mid-cleanup-
    crash residue).
    """
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path


__all__ = [
    "WorktreeAlreadyExistsForStory",
    "WorktreeCleanupResult",
    "WorktreeInspectionResult",
    "WorktreeLifecycleBlocked",
    "WorktreeLifecycleResult",
    "WorktreeRemoveRefused",
    "WorktreeStalePartialState",
    "cleanup_worktree",
    "create_worktree",
    "inspect_worktree",
    "list_active_worktrees",
]
