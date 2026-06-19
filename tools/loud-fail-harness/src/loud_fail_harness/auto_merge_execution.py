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

It lands the **mechanism only** (the merge call + the ``auto-merge-skipped``
marker). The *decision* — the ``enabled AND green AND merge-ready`` conjunction
(AC-2) — is orchestrator-domain flow policy and lives in
:func:`loud_fail_harness.bundle_assembly.main`, NOT here. This module never reads
config / gate / run-state to *decide*: it is handed a branch and told to merge,
preserving sensor-not-advisor.

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
    * **gh CLI** (``cli.github.com/manual/gh_pr_merge``, checked 2026-06-17):
      ``gh pr merge [<branch>] -s/--squash``; exit codes 0 success / 1 error /
      2 canceled / 4 auth-required.

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
#: green; ``merge-conflict`` — ``gh`` reported the PR could not be cleanly merged;
#: ``gh-unavailable`` — the ``gh`` CLI is absent / not on PATH; ``merge-failed`` —
#: any other non-zero ``gh`` exit (no open PR, draft PR, auth/network, timeout).
SkipReason = Literal["gate-not-met", "merge-conflict", "gh-unavailable", "merge-failed"]

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


def attempt_auto_merge(
    *,
    branch_name: str,
    repo_root: pathlib.Path,
    gh_runner: _GhRunner = _default_gh_runner,
    strategy: MergeStrategy = "squash",
) -> AutoMergeOutcome:
    """Execute ``gh pr merge --<strategy> <branch_name>`` on the per-story branch.

    The branch is passed **explicitly** (not relying on the current checkout) so
    the actuator is independent of the Stop hook's working-tree state.
    ``returncode == 0`` → ``merged``; a non-zero exit, an absent ``gh`` CLI, or a
    timeout → ``skipped`` with the matching :data:`SkipReason`. **NEVER raises on
    a merge failure** — a failed merge is data the caller surfaces as
    ``auto-merge-skipped``; the PR is left in draft for human handling (NFR-R6).

    No ``git push``, no ``--force``, no ``--rebase``, no ``--delete-branch``, no
    branch operations outside the named per-story branch, and ``main`` / trunk is
    never the merge target — the merge is GitHub-side on the branch's own PR
    (NFR-S3 / NFR-R3).
    """
    flag = _STRATEGY_FLAGS.get(strategy)
    if flag is None:
        raise ValueError(
            f"unsupported merge strategy {strategy!r}; 17.3 supports only 'squash'"
        )

    if not branch_name.strip():
        # Story 22.6 AC-7(ii): refuse to invoke `gh pr merge --squash ""` with an
        # empty/whitespace branch_name (a malformed merge target). A failed merge
        # is data, not an exception (module docstring), so this surfaces as a
        # loud `auto-merge-skipped` rather than raising — mapped to the existing
        # `merge-failed` SkipReason (no marker-taxonomy bump; the gh_detail names
        # the precondition). `branch_name` from run-state is runtime data, so a
        # skipped outcome (not the ValueError raised for an unsupported strategy,
        # which is a caller-API misuse) is the consistent loud-fail surface.
        return AutoMergeOutcome(
            status="skipped",
            branch_name=branch_name,
            skip_reason="merge-failed",
            gh_stderr=(
                "refusing to invoke `gh pr merge` with an empty/whitespace "
                "branch_name (precondition guard, Story 22.6 AC-7(ii))"
            ),
        )

    gh_args = ["pr", "merge", flag, branch_name]
    try:
        completed = gh_runner(gh_args, repo_root)
    except FileNotFoundError as exc:
        # Story 22.6 AC-7(iv): a missing `cwd` (repo_root) raises the SAME
        # FileNotFoundError as a missing `gh` CLI. Distinguish via the exception
        # filename — subprocess sets it to the cwd path on a missing working
        # directory and to the executable name on a missing binary — so the
        # diagnostic is honest. The injected-runner stubs raise
        # FileNotFoundError("gh") (filename=None) → the gh-unavailable default.
        if exc.filename is not None and pathlib.Path(str(exc.filename)).resolve() == pathlib.Path(str(repo_root)).resolve():
            return AutoMergeOutcome(
                status="skipped",
                branch_name=branch_name,
                skip_reason="merge-failed",
                gh_stderr=(
                    f"repo_root {str(repo_root)!r} does not exist; cannot set the "
                    "gh working directory (NOT a missing gh CLI; precondition "
                    "guard, Story 22.6 AC-7(iv))"
                ),
            )
        return AutoMergeOutcome(
            status="skipped",
            branch_name=branch_name,
            skip_reason="gh-unavailable",
            gh_stderr="gh executable not found on PATH",
        )
    except subprocess.TimeoutExpired as exc:
        return AutoMergeOutcome(
            status="skipped",
            branch_name=branch_name,
            skip_reason="merge-failed",
            gh_stderr=f"gh pr merge timed out after {_GH_TIMEOUT_SECONDS}s: {exc}",
        )

    if completed.returncode == 0:
        return AutoMergeOutcome(status="merged", branch_name=branch_name)

    return AutoMergeOutcome(
        status="skipped",
        branch_name=branch_name,
        skip_reason=_classify_failure(completed),
        gh_returncode=completed.returncode,
        gh_stderr=(completed.stderr or "").strip() or None,
    )


_SKIP_REASON_PROSE: Final[dict[str, str]] = {
    "gate-not-met": (
        "the 17.2 auto-merge gate was not green (a configured adoption gate was "
        "unmet), so the merge was never attempted"
    ),
    "merge-conflict": "gh reported the PR could not be cleanly merged (conflict)",
    "gh-unavailable": "the gh CLI is not available on PATH",
    "merge-failed": (
        "gh pr merge exited non-zero (e.g. no open PR, the PR is still in draft, "
        "branch protection / required checks pending, or an auth/network failure)"
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
