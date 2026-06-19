"""Story 17.3 — Auto-merge execution actuator + ``auto-merge-skipped`` marker (FR-P2-3).

The THIRD and final story of Epic 17, and the system's **first actuator**:
every prior specialist/evaluator is sensor-not-advisor, returning a structured
observation; this module is the first that *acts on the world*. It consumes the
17.1-resolved :class:`~loud_fail_harness.auto_merge_config.AutoMergeConfig` and
the 17.2 :class:`~loud_fail_harness.auto_merge_gate.AutoMergeGateDecision` (both
read-only, in the orchestrator-domain caller) and, when armed, executes
``gh pr merge --squash`` on the per-story branch — making auto-merge the first
Phase-2 surface that mutates a remote, **indirectly via PR-merge, never via a
direct push to ``main``** (NFR-S3 / NFR-R3).

It lands the **mechanism only** (the ready→merge calls + the ``auto-merge-skipped``
marker). Story 22.7 inserts a ``gh pr ready <branch>`` draft→ready transition
BEFORE ``gh pr merge`` so an armed conjunction can land on a real project where
Phase-1 leaves the PR in ``draft`` (``gh pr merge`` on a draft PR exits non-zero).
The readiness step is loud-fail: a failure surfaces ``auto-merge-skipped:
ready-failed`` and the merge is NOT attempted afterward. The *decision* — the
``enabled AND green AND merge-ready`` conjunction (AC-2) — is orchestrator-domain
flow policy and lives in :func:`loud_fail_harness.bundle_assembly.main`, NOT here.
This module never reads config / gate / run-state to *decide*: it is handed a
branch and told to ready/merge, preserving sensor-not-advisor.

Merge strategy: ``--squash`` (the epic AC asks the story to pick + record the
rationale). A per-story branch accumulates Dev + QA + review-retry + Automator
commits; squashing collapses them into ONE commit on ``main`` per story —
matching BMAD's "one story = one mergeable unit" granularity, keeping ``main``
history clean of intra-story retry churn, and (critically) **never rebasing user
commits** (NFR-R3). ``--merge`` would pollute ``main`` with the full intra-story
DAG; ``--rebase`` rewrites commit history (closer to the NFR-R3 line). Squash is
the conservative, history-clean choice. ``--delete-branch`` and ``--auto`` are
deliberately NOT passed (the per-story branch is preserved as evidence; the
merge outcome stays deterministic at Stop-hook time).

A failed merge is **data, not an exception**: a merge conflict, an absent ``gh``
CLI, a missing/draft PR, or an auth/network non-zero exit all return an
``AutoMergeOutcome`` whose ``status`` is ``skipped`` with a sub-classification —
the PR remains in draft for human handling, surfaced loudly via
``auto-merge-skipped`` (NFR-R6), never silently swallowed.

Design (mirrors 17.1 / 17.2): **plain frozen dataclasses + imperative
validation**, NOT Pydantic. The outcome types are enum / int / optional-str
(the latter being captured ``gh`` stderr surfaced verbatim in a diagnostic, not
parsed into a model), so there is no externally-*constructed* hostile-input
model — the module stays off the ``input-hardening-gate`` registry, the same
trade-off 17.1 / 17.2 recorded.

Sources:
    * **Story 17.3 epic AC** at ``epics-phase-2.md`` lines 568-582.
    * **PRD FR-P2-3** (``prd.md`` line 946) + **NFR-S3** (line 1006) / **NFR-R3**
      (line 982) / **NFR-R6** (line 985).
    * **gh CLI** (``cli.github.com/manual/gh_pr_merge`` +
      ``cli.github.com/manual/gh_pr_ready``, checked 2026-06-19):
      ``gh pr ready [<branch>]`` (GitHub-side ``markPullRequestReadyForReview``
      mutation; idempotent no-op on an already-ready PR) then
      ``gh pr merge [<branch>] -s/--squash``; both share exit codes 0 success /
      1 error / 2 canceled / 4 auth-required.

Pattern compliance (architecture.md → Implementation Patterns):
    * **Pattern 2** — ``auto-merge-skipped`` is the new ``marker_class`` landed
      in ``schemas/marker-taxonomy.yaml``.
    * **Pattern 5 (loud-fail)** — :func:`surface_auto_merge_skipped` runs
      :func:`validate_marker_emission` FIRST (atomic-on-failure); a failed merge
      surfaces as a marker rather than raising.
    * **Pattern 6 (frozen DI seam)** — :data:`_GhRunner` /
      :func:`_default_gh_runner` mirror
      ``session_start_reattach._default_git_runner``: ``capture_output=True``,
      ``text=True``, ``check=False``, ``timeout``, never raising on non-zero.
    * **Sensor-not-advisor** — the marker is INFORMATIONAL; emitting it does NOT
      flip a wrapper status or change ``current_state`` (the story is already
      ``done``; the human handles the draft PR).
"""

from __future__ import annotations

import pathlib
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Callable, Final, Literal

from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

#: The marker class emitted when an ARMED auto-merge did not complete. Consumed
#: AS-IS from ``schemas/marker-taxonomy.yaml``; THIS module is its sole runtime
#: emitter. Mirrors 17.2's ``AUTO_MERGE_GATE_NOT_MET_MARKER`` constant.
AUTO_MERGE_SKIPPED_MARKER: Final[Literal["auto-merge-skipped"]] = "auto-merge-skipped"

#: Why an armed auto-merge did not complete (the marker's sub_classifications):
#: ``gate-not-met`` — the merge was never attempted because the 17.2 gate was not
#: green; ``ready-failed`` — the ``gh pr ready`` draft→ready transition that
#: PRECEDES the merge did not succeed (Story 22.7), so the merge was never
#: attempted; ``merge-conflict`` — ``gh`` reported the PR could not be cleanly
#: merged; ``gh-unavailable`` — the ``gh`` CLI is absent / not on PATH (at the
#: MERGE step); ``merge-failed`` — any other non-zero ``gh`` exit at the merge
#: step (no open PR, auth/network, timeout). ``ready-failed`` names the readiness
#: STEP as the failure site (distinct remediation from a merge-step failure); the
#: captured ``gh`` exit code + stderr ride along in ``gh_detail`` verbatim.
SkipReason = Literal[
    "gate-not-met", "ready-failed", "merge-conflict", "gh-unavailable", "merge-failed"
]

#: Terminal outcome of an attempted merge.
MergeStatus = Literal["merged", "skipped"]

#: Supported merge strategy. 17.3 ships ``squash`` only (see module docstring);
#: the parameter exists so a future story can extend without an API break.
MergeStrategy = Literal["squash"]

_STRATEGY_FLAGS: Final[dict[str, str]] = {"squash": "--squash"}

#: ``gh`` subprocess timeout (seconds). Bounds a pathologically-hung CLI; mirrors
#: ``session_start_reattach._default_git_runner``'s 30s bound.
_GH_TIMEOUT_SECONDS: Final[int] = 60


_GhRunner = Callable[
    [Sequence[str], pathlib.Path], "subprocess.CompletedProcess[str]"
]


def _default_gh_runner(
    args: Sequence[str], cwd: pathlib.Path
) -> "subprocess.CompletedProcess[str]":
    """Production gh_runner — wraps stdlib :func:`subprocess.run`.

    Returns the :class:`subprocess.CompletedProcess` directly; never raises on
    non-zero exit (callers inspect ``returncode``). A :class:`FileNotFoundError`
    (no ``gh`` on PATH) and a :class:`subprocess.TimeoutExpired` DO propagate —
    :func:`attempt_auto_merge` catches both and maps them to a skip outcome.
    """
    return subprocess.run(
        ["gh", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=_GH_TIMEOUT_SECONDS,
        stdin=subprocess.DEVNULL,
    )


@dataclass(frozen=True)
class AutoMergeOutcome:
    """The always-returned result of an attempted (or deliberately not-attempted)
    auto-merge.

    ``status == "merged"`` iff ``gh pr merge`` exited 0. ``status == "skipped"``
    carries the :data:`SkipReason` sub-classification plus, for execution
    failures, the captured ``gh`` ``returncode`` / ``stderr`` so the rendered
    marker names exactly why the merge did not land.
    """

    status: MergeStatus
    branch_name: str
    skip_reason: SkipReason | None = None
    gh_returncode: int | None = None
    gh_stderr: str | None = None

    def __post_init__(self) -> None:
        if self.status == "skipped" and self.skip_reason is None:
            raise ValueError(
                "AutoMergeOutcome with status='skipped' must carry a skip_reason"
            )
        if self.status == "merged" and self.skip_reason is not None:
            raise ValueError(
                "AutoMergeOutcome with status='merged' must not carry a skip_reason"
            )
        if self.skip_reason == "gate-not-met" and (
            self.gh_returncode is not None or self.gh_stderr is not None
        ):
            raise ValueError(
                "AutoMergeOutcome with skip_reason='gate-not-met' must not carry "
                "gh_returncode or gh_stderr (gate-not-met is a pre-gh decision)"
            )


@dataclass(frozen=True)
class AutoMergeSkippedEmission:
    """The atomic-emission return shape of :func:`surface_auto_merge_skipped` —
    the marker class, the runtime-filled ``diagnostic_pointer`` (names the skip
    reason + remediation), the ``skip_reason`` sub-classification, and the
    captured ``gh`` detail (``None`` for the ``gate-not-met`` reason, which is
    decided before any ``gh`` invocation).
    """

    marker_class: Literal["auto-merge-skipped"]
    diagnostic_pointer: str
    skip_reason: SkipReason
    gh_detail: str | None


def skipped_gate_not_met(branch_name: str) -> AutoMergeOutcome:
    """Construct the no-``gh``-invocation skip outcome for the case where the
    merge was ARMED (``enabled`` + merge-ready) but the 17.2 gate was not green.

    The merge is never attempted; the orchestrator-domain caller
    (:func:`loud_fail_harness.bundle_assembly.main`) uses this to build the
    ``auto-merge-skipped: gate-not-met`` emission without touching the remote.
    """
    return AutoMergeOutcome(
        status="skipped", branch_name=branch_name, skip_reason="gate-not-met"
    )


def _classify_failure(
    completed: "subprocess.CompletedProcess[str]",
) -> SkipReason:
    stderr = (completed.stderr or "").lower()
    if "conflict" in stderr or "not mergeable" in stderr or "cannot be cleanly" in stderr:
        return "merge-conflict"
    return "merge-failed"


@dataclass(frozen=True)
class _GhInvocationFailure:
    """A ``gh`` call that produced NO exit code (the CLI was absent, the call
    timed out, or the ``cwd`` / ``repo_root`` was missing). ``stderr`` is the
    honest loud-fail detail surfaced verbatim in ``gh_detail``; ``gh_unavailable``
    is True ONLY for a genuinely missing ``gh`` binary (it drives the merge step's
    ``gh-unavailable`` sub-classification — the readiness step folds every
    invocation failure into ``ready-failed`` and relies on ``stderr`` for detail).
    """

    stderr: str
    gh_unavailable: bool


def _invoke_gh(
    gh_args: Sequence[str],
    *,
    repo_root: pathlib.Path,
    gh_runner: _GhRunner,
) -> "subprocess.CompletedProcess[str] | _GhInvocationFailure":
    """Run one ``gh`` subcommand, mapping the two no-exit-code failure modes to a
    :class:`_GhInvocationFailure` so ``gh pr ready`` and ``gh pr merge`` reuse
    identical loud-fail plumbing (Story 22.7 — do NOT duplicate the guards). A
    :class:`subprocess.CompletedProcess` (any ``returncode``) is returned as-is.
    """
    try:
        return gh_runner(gh_args, repo_root)
    except FileNotFoundError as exc:
        # Story 22.6 AC-7(iv): a missing `cwd` (repo_root) raises the SAME
        # FileNotFoundError as a missing `gh` CLI. Distinguish via the exception
        # filename — subprocess sets it to the cwd path on a missing working
        # directory and to the executable name on a missing binary — so the
        # diagnostic is honest. The injected-runner stubs raise
        # FileNotFoundError("gh") (filename=None) → the gh-unavailable default.
        if exc.filename is not None and pathlib.Path(str(exc.filename)).resolve() == pathlib.Path(str(repo_root)).resolve():
            return _GhInvocationFailure(
                stderr=(
                    f"repo_root {str(repo_root)!r} does not exist; cannot set the "
                    "gh working directory (NOT a missing gh CLI; precondition "
                    "guard, Story 22.6 AC-7(iv))"
                ),
                gh_unavailable=False,
            )
        return _GhInvocationFailure(
            stderr="gh executable not found on PATH", gh_unavailable=True
        )
    except subprocess.TimeoutExpired as exc:
        return _GhInvocationFailure(
            stderr=(
                f"gh {' '.join(gh_args[:2])} timed out after "
                f"{_GH_TIMEOUT_SECONDS}s: {exc}"
            ),
            gh_unavailable=False,
        )


def _attempt_pr_ready(
    *,
    branch_name: str,
    repo_root: pathlib.Path,
    gh_runner: _GhRunner,
) -> AutoMergeOutcome | None:
    """Story 22.7 — the draft→ready transition that PRECEDES the merge.

    Runs ``gh pr ready <branch_name>`` (a GitHub-side ``markPullRequestReadyForReview``
    GraphQL mutation — NO ``git push``, idempotent no-op on an already-ready PR).
    Returns ``None`` on success (the caller proceeds to the merge); returns a
    ``skipped`` :class:`AutoMergeOutcome` with the ``ready-failed`` sub-classification
    on ANY failure (non-zero exit, absent ``gh``, timeout, missing ``repo_root``),
    so the caller does **NOT** attempt the merge afterward (AC-2). A failed
    readiness is data, not an exception.
    """
    result = _invoke_gh(
        ["pr", "ready", branch_name], repo_root=repo_root, gh_runner=gh_runner
    )
    if isinstance(result, _GhInvocationFailure):
        return AutoMergeOutcome(
            status="skipped",
            branch_name=branch_name,
            skip_reason="ready-failed",
            gh_stderr=result.stderr,
        )
    if result.returncode != 0:
        return AutoMergeOutcome(
            status="skipped",
            branch_name=branch_name,
            skip_reason="ready-failed",
            gh_returncode=result.returncode,
            gh_stderr=(result.stderr or "").strip() or None,
        )
    return None


def attempt_auto_merge(
    *,
    branch_name: str,
    repo_root: pathlib.Path,
    gh_runner: _GhRunner = _default_gh_runner,
    strategy: MergeStrategy = "squash",
) -> AutoMergeOutcome:
    """Ready-then-merge the per-story branch: ``gh pr ready <branch_name>`` followed
    by ``gh pr merge --<strategy> <branch_name>``.

    Story 22.7 inserts the readiness transition BEFORE the merge so an armed
    ``enabled AND gate-green AND done`` conjunction can land on a real project
    where Phase-1 leaves the PR in ``draft``. The readiness step is loud-fail: a
    ``gh pr ready`` failure returns ``skipped`` with the ``ready-failed``
    sub-classification and the merge is **NOT** attempted (AC-2).

    The branch is passed **explicitly** (not relying on the current checkout) so
    the actuator is independent of the Stop hook's working-tree state. On a clean
    readiness, ``gh pr merge`` ``returncode == 0`` → ``merged``; a non-zero exit,
    an absent ``gh`` CLI, or a timeout → ``skipped`` with the matching
    :data:`SkipReason`. **NEVER raises on a ready/merge failure** — it is data the
    caller surfaces as ``auto-merge-skipped``; the PR is left in draft for human
    handling (NFR-R6).

    Both ``gh pr ready`` and ``gh pr merge`` are GitHub-side PR operations only:
    no ``git push``, no ``--force``, no ``--rebase``, no ``--delete-branch``, no
    branch operations outside the named per-story branch, and ``main`` / trunk is
    never a direct write target — the readiness + merge are GitHub-side on the
    branch's own PR (NFR-S3 / NFR-R3).
    """
    flag = _STRATEGY_FLAGS.get(strategy)
    if flag is None:
        raise ValueError(
            f"unsupported merge strategy {strategy!r}; 17.3 supports only 'squash'"
        )

    if not branch_name.strip():
        # Story 22.6 AC-7(ii): refuse to invoke `gh` with an empty/whitespace
        # branch_name (a malformed PR target for BOTH the readiness and merge
        # steps). A failed merge is data, not an exception (module docstring), so
        # this surfaces as a loud `auto-merge-skipped` rather than raising —
        # mapped to the existing `merge-failed` SkipReason (no marker-taxonomy
        # bump; the gh_detail names the precondition). It is a precondition on the
        # whole mechanism that short-circuits before any gh call, so it keeps its
        # `merge-failed` classification rather than `ready-failed`. `branch_name`
        # from run-state is runtime data, so a skipped outcome (not the ValueError
        # raised for an unsupported strategy, which is a caller-API misuse) is the
        # consistent loud-fail surface.
        return AutoMergeOutcome(
            status="skipped",
            branch_name=branch_name,
            skip_reason="merge-failed",
            gh_stderr=(
                "refusing to invoke `gh` with an empty/whitespace branch_name "
                "(precondition guard, Story 22.6 AC-7(ii))"
            ),
        )

    ready_outcome = _attempt_pr_ready(
        branch_name=branch_name, repo_root=repo_root, gh_runner=gh_runner
    )
    if ready_outcome is not None:
        return ready_outcome  # readiness failed → do NOT attempt the merge (AC-2)

    result = _invoke_gh(
        ["pr", "merge", flag, branch_name], repo_root=repo_root, gh_runner=gh_runner
    )
    if isinstance(result, _GhInvocationFailure):
        return AutoMergeOutcome(
            status="skipped",
            branch_name=branch_name,
            skip_reason="gh-unavailable" if result.gh_unavailable else "merge-failed",
            gh_stderr=result.stderr,
        )

    if result.returncode == 0:
        return AutoMergeOutcome(status="merged", branch_name=branch_name)

    return AutoMergeOutcome(
        status="skipped",
        branch_name=branch_name,
        skip_reason=_classify_failure(result),
        gh_returncode=result.returncode,
        gh_stderr=(result.stderr or "").strip() or None,
    )


_SKIP_REASON_PROSE: Final[dict[str, str]] = {
    "gate-not-met": (
        "the 17.2 auto-merge gate was not green (a configured adoption gate was "
        "unmet), so the merge was never attempted"
    ),
    "ready-failed": (
        "gh pr ready (the draft->ready transition that precedes the merge, Story "
        "22.7) did not succeed (e.g. the gh CLI is absent, a timeout, a missing "
        "repo_root, insufficient permission to mark the draft PR ready, or any "
        "other non-zero gh exit), so the merge was NOT attempted afterward — "
        "remediation is at the readiness step (check draft-PR permissions / plan "
        "tier / branch state), distinct from a merge-step failure"
    ),
    "merge-conflict": "gh reported the PR could not be cleanly merged (conflict)",
    "gh-unavailable": "the gh CLI is not available on PATH",
    "merge-failed": (
        "gh pr merge exited non-zero (e.g. no open PR, branch protection / "
        "required checks pending, or an auth/network failure)"
    ),
}


def _gh_detail(outcome: AutoMergeOutcome) -> str | None:
    if outcome.gh_returncode is None and outcome.gh_stderr is None:
        return None
    parts: list[str] = []
    if outcome.gh_returncode is not None:
        parts.append(f"exit={outcome.gh_returncode}")
    if outcome.gh_stderr:
        parts.append(f"stderr={outcome.gh_stderr}")
    return "; ".join(parts) if parts else None


def _render_diagnostic_pointer(outcome: AutoMergeOutcome, gh_detail: str | None) -> str:
    assert outcome.skip_reason is not None
    prose = _SKIP_REASON_PROSE[outcome.skip_reason]
    detail = f" ({gh_detail})" if gh_detail else ""
    return (
        f"auto-merge skipped [{outcome.skip_reason}] on branch "
        f"{outcome.branch_name}: {prose}{detail}. The PR remains in draft for "
        "human handling — failure is loud, never silent (NFR-R6). INFORMATIONAL "
        "(sensor-not-advisor): does not change run state, flip any wrapper "
        "status, or retry the merge; the human decides next steps."
    )


def surface_auto_merge_skipped(
    outcome: AutoMergeOutcome,
    registry: MarkerClassRegistry,
) -> AutoMergeSkippedEmission:
    """Atomic-on-failure ``auto-merge-skipped`` emission helper (Pattern 5).

    Mirrors :func:`loud_fail_harness.auto_merge_gate.surface_auto_merge_gate_not_met`:
    :func:`validate_marker_emission` runs FIRST; on registry rejection
    :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass` propagates
    BEFORE any partial state is constructed. Pure: no file I/O, no event-log
    write — the emission is data the assembler renders.

    Raises:
        ValueError: ``outcome.status`` is not ``skipped`` (nothing to emit — the
            caller must check before calling).
        UnknownMarkerClass: registry does not contain ``auto-merge-skipped``.
    """
    if outcome.status != "skipped" or outcome.skip_reason is None:
        raise ValueError(
            f"surface_auto_merge_skipped called with status {outcome.status!r}; "
            "the marker is only emitted on a 'skipped' outcome"
        )
    validate_marker_emission(registry, AUTO_MERGE_SKIPPED_MARKER)
    gh_detail = _gh_detail(outcome)
    return AutoMergeSkippedEmission(
        marker_class=AUTO_MERGE_SKIPPED_MARKER,
        diagnostic_pointer=_render_diagnostic_pointer(outcome, gh_detail),
        skip_reason=outcome.skip_reason,
        gh_detail=gh_detail,
    )


__all__ = [
    "AUTO_MERGE_SKIPPED_MARKER",
    "AutoMergeOutcome",
    "AutoMergeSkippedEmission",
    "MergeStatus",
    "MergeStrategy",
    "SkipReason",
    "attempt_auto_merge",
    "skipped_gate_not_met",
    "surface_auto_merge_skipped",
]
