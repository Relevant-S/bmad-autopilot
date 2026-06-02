"""Epic-level running/final PR-bundle assembler — Story 15.3 substrate library.

## Substrate-component identity

THIS module is a substrate **LIBRARY** in the bundle-assembly family (sibling of
:mod:`loud_fail_harness.bundle_assembly` and
:mod:`loud_fail_harness.bundle_assembly_escalation`), NOT a sixth substrate
component. ADR-003 Consequence 1 keeps the substrate closed at FIVE; this module
is composition over the existing rendering core, mirroring how
``bundle_assembly_escalation.py`` reuses ``bundle_assembly``'s helpers without
forking the renderer (Story 5.8). FR60 (≤3 hooks) and FR62 (pluggability) both
hold: the running/final epic bundle reuses the EXISTING Stop hook via the
established Story 2.11 ``python3 -m`` substrate-invocation boundary.

## Single rendering core (shared with Story 2.11 / 6.1)

The per-epic loud-fail block is rendered by the SAME
:func:`loud_fail_harness.bundle_assembly._render_loud_fail_block` the per-story
bundle uses (Story 6.1), and the atomic write reuses
:func:`loud_fail_harness.bundle_assembly._atomic_write_bundle` (Pattern 4 /
NFR-R1). No parallel renderer is forked. The import-direction is one-way: this
module depends on ``bundle_assembly``; ``bundle_assembly`` does NOT depend on
this module (no circular drift; modifications to ``assemble_bundle`` cannot
couple to epic-scope logic — AC-5 bit-identity for the per-story bundle).

The ``EpicRunState`` cache does NOT persist ``marker_contexts`` (unlike the
per-story ``RunState``). The sole per-epic durable marker — ``epic-budget-
exhausted`` — declares ``pointer_context_fields: [epic_id, run_id, consumed,
effective_budget]`` in ``marker-taxonomy.yaml``, so this module SYNTHESIZES the
render-time context for it from the loaded ``EpicRunState`` fields (see
:func:`_build_marker_contexts`). The per-story markers are NOT re-aggregated
inline; each per-story status row carries a POINTER to that story's own
canonical artifact (per-story merge-ready bundle / escalation bundle / live
event-stream), where that story's markers are canonically rendered (Story 15.3
Dev Notes "Marker-surfacing decision" — model A; avoids a fourth canonical
store, NFR-R8).

## Running-vs-final + idempotent regeneration (AC-4)

There is ONE epic-bundle artifact per ``(epic_id, run_id)`` at the deterministic
path ``_bmad-output/epic-pr-bundles/<epic-id>/<run-id>.md``. The Stop hook
re-invokes this assembler at each per-story completion boundary (running) and
again at epic close (final); the running and final bundle are the SAME file at
successive ``epic-run-state.yaml`` cache states, NOT two distinct files.
Regeneration is idempotent: the write is atomic (NFR-R1) and ``generated_at`` is
an injection point so re-rendering from an unchanged cache produces byte-stable
output (the ``assemble_bundle`` precedent).

## Failure routing (AC-6 — reuse Story 6.9; no new marker class)

``main`` mirrors :func:`loud_fail_harness.bundle_assembly.main`:

    * Pre-condition failure (missing epic-run-state, or a ``run_id``-correlated
      ``epic_id`` mismatch) → stderr + exit 1, NO marker. Same remediation-shape
      discipline as ``assemble_bundle.main``'s ``SpecialistDispatchLogNotFound`` /
      ``RunStateStoryIdMismatch`` handling.
    * Assembler-logic failure (epic-run-state SHAPE mismatch / per-story-status
      enum unresolved / render crash) → routes through the EXISTING
      :func:`loud_fail_harness.bundle_assembly_failure.surface_assembly_failure`
      and exits :data:`BUNDLE_ASSEMBLY_FAILED_EXIT_CODE`. NO new marker class —
      the closed-set count is unchanged.

``surface_assembly_failure``'s persisted-marker channel (Channel 3) is bound to
the per-story ``RunState`` schema; an ``EpicRunState`` document does not validate
as a ``RunState``, so that channel naturally degrades (the call is wrapped in the
same best-effort ``try/except`` ``bundle_assembly.main`` uses). The durable
signal lives in the always-on fallback diagnostic file (Channel 1) + the stderr
line (Channel 2) + the distinct exit code — sufficient for the loud-fail
contract, and correct precisely because the failing input may BE the malformed
epic-run-state we would otherwise write back to.
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import sys
from collections.abc import Mapping
from datetime import datetime, timezone

import yaml

from loud_fail_harness.bundle_assembly import (
    _atomic_write_bundle,
    _render_loud_fail_block,
)
from loud_fail_harness.bundle_assembly_failure import (
    BUNDLE_ASSEMBLY_FAILED_EXIT_CODE,
    classify_assembly_failure,
    surface_assembly_failure,
)
from loud_fail_harness.epic_lifecycle import EPIC_BUDGET_EXHAUSTED_MARKER
from loud_fail_harness.epic_run_state import EpicRunState
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)

__all__ = [
    "AssembleEpicBundleResult",
    "EpicBundlePathInvariantViolation",
    "EpicRunStateEpicIdMismatch",
    "EpicRunStateNotFound",
    "assemble_epic_bundle",
    "compute_epic_bundle_path",
    "main",
]

#: Directory (under ``_bmad-output/``) the epic bundle is written to. Mirrors the
#: per-story ``pr-bundles`` + escalation ``escalation-bundles`` path conventions.
EPIC_PR_BUNDLES_DIRNAME = "epic-pr-bundles"

#: Per-story-artifact pointer roots (Dev Notes "Marker-surfacing decision":
#: directory-level, story_id-keyed — the cache stores no per-story run_id, so a
#: per-run-file pointer is impossible without a cache-schema change that no AC
#: demands).
_PR_BUNDLE_POINTER_ROOT = "_bmad-output/pr-bundles"
_ESCALATION_BUNDLE_POINTER_ROOT = "_bmad-output/escalation-bundles"
_EVENT_STREAM_POINTER_ROOT = "_bmad-output/qa-evidence"

#: Terminal "completed" statuses whose pointer is the per-story merge-ready
#: bundle directory.
_COMPLETED_STATUSES: frozenset[str] = frozenset({"merge-ready", "done"})


class EpicBundlePathInvariantViolation(ValueError):
    """``epic_id`` / ``run_id`` failed the path-component hardening guard.

    Empty, absolute, or ``..``-traversal-bearing. Mirrors
    :class:`loud_fail_harness.retry_budget_exhaustion.RetryBudgetExhaustionInvariantViolation`'s
    posture for :func:`compute_escalation_bundle_path` (Epic 14 retro Action #2).
    """


class EpicRunStateNotFound(Exception):
    """Pre-condition failure: the epic-run-state cache file does not exist.

    Mirrors :class:`loud_fail_harness.bundle_assembly.SpecialistDispatchLogNotFound`'s
    pre-condition posture — exit 1, NO ``bundle-assembly-failed`` marker (the
    assembler had nothing to assemble).
    """

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        super().__init__(f"epic-run-state cache not found at {path}")


class EpicRunStateEpicIdMismatch(Exception):
    """Pre-condition failure: the loaded epic-run-state is for a different epic.

    The epic-scope sibling of
    :class:`loud_fail_harness.bundle_assembly.RunStateStoryIdMismatch` — exit 1,
    NO marker.
    """

    def __init__(self, *, expected: str, actual: str) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"epic-run-state epic_id {actual!r} does not match requested {expected!r}"
        )


@dataclasses.dataclass(frozen=True)
class AssembleEpicBundleResult:
    """Return shape of :func:`assemble_epic_bundle` on success.

    Frozen for determinism + hashability (Epic 1 retro Action #2).
    """

    bundle_path: pathlib.Path
    epic_id: str
    run_id: str
    current_state: str
    story_ids: tuple[str, ...]


def _reject_path_component(value: str, *, name: str) -> None:
    if not value:
        raise EpicBundlePathInvariantViolation(f"{name} must not be empty")
    pure = pathlib.PurePosixPath(value)
    if pure.is_absolute():
        raise EpicBundlePathInvariantViolation(
            f"{name} must not be an absolute path; got {value!r}"
        )
    if ".." in pure.parts:
        raise EpicBundlePathInvariantViolation(
            f"{name} must not contain '..' path traversal segments; got {value!r}"
        )


def compute_epic_bundle_path(
    *,
    repo_root: pathlib.Path,
    epic_id: str,
    run_id: str,
) -> pathlib.Path:
    """Return the deterministic per-run epic-bundle file path
    ``{repo_root}/_bmad-output/epic-pr-bundles/{epic_id}/{run_id}.md``.

    Pure path computation; does NOT create the directory. Mirrors
    :func:`loud_fail_harness.retry_budget_exhaustion.compute_escalation_bundle_path`:
    rejects empty / absolute / ``..``-traversal ``epic_id`` & ``run_id``.

    Raises:
        EpicBundlePathInvariantViolation: ``epic_id`` or ``run_id`` empty /
            absolute / contains ``..``.
    """
    _reject_path_component(epic_id, name="epic_id")
    _reject_path_component(run_id, name="run_id")
    return (
        repo_root
        / "_bmad-output"
        / EPIC_PR_BUNDLES_DIRNAME
        / epic_id
        / f"{run_id}.md"
    )


def _load_epic_run_state(epic_run_state_path: pathlib.Path) -> EpicRunState:
    """Read + Pydantic-validate the epic-run-state cache YAML.

    A missing file is a PRE-CONDITION failure (:exc:`EpicRunStateNotFound`); a
    present-but-malformed file (YAML error, non-mapping top level, or shape that
    does not validate as :class:`EpicRunState`) is an ASSEMBLER-LOGIC failure —
    the underlying ``yaml.YAMLError`` / ``ValueError`` / ``pydantic.ValidationError``
    propagates unchanged (no swallowing) so ``main`` routes it through
    ``surface_assembly_failure`` (AC-6).
    """
    if not epic_run_state_path.exists():
        raise EpicRunStateNotFound(epic_run_state_path)
    raw = yaml.safe_load(epic_run_state_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError(
            f"epic-run-state file at {epic_run_state_path} did not parse to a "
            "YAML mapping at top level"
        )
    return EpicRunState.model_validate(dict(raw))


def _story_artifact_pointer(story_id: str, status: str) -> str:
    """Map a per-story status to its canonical-artifact pointer (AC-2).

    completed (``merge-ready`` / ``done``) → per-story merge-ready bundle dir;
    ``escalated`` → escalation-bundle dir (where the inline retry history is
    canonically rendered, Story 5.8); everything else (in-progress / review / qa
    / ready-for-dev) → the live per-story event-stream location — the "live state
    link". Directory-level, story_id-keyed.
    """
    if status in _COMPLETED_STATUSES:
        return f"{_PR_BUNDLE_POINTER_ROOT}/{story_id}/"
    if status == "escalated":
        return f"{_ESCALATION_BUNDLE_POINTER_ROOT}/{story_id}/"
    return f"{_EVENT_STREAM_POINTER_ROOT}/{story_id}/"


def _render_story_table(state: EpicRunState) -> str:
    parts = [
        "## Stories",
        "",
        "| Story | Status | Artifact |",
        "| --- | --- | --- |",
    ]
    for story_id in state.story_ids:
        status = state.per_story_status.get(story_id, "unknown")
        pointer = _story_artifact_pointer(story_id, status)
        parts.append(f"| {story_id} | {status} | {pointer} |")
    return "\n".join(parts)


def _render_cost_partition(state: EpicRunState) -> str:
    partition = state.per_epic_cost_partition
    parts = [
        "## 💸 Epic Cost Partition",
        "",
        "| Story | Cost (USD) |",
        "| --- | --- |",
    ]
    any_zero = False
    for story_id in state.story_ids:
        cost = partition.per_story_cost.get(story_id, 0.0)
        if cost == 0.0:
            any_zero = True
        parts.append(f"| {story_id} | {cost:.2f} |")
    parts.append(f"| Epic total | {partition.epic_cost_total:.2f} |")
    if any_zero:
        parts.append("")
        parts.append(
            "_A per-story cost of 0.00 may reflect `cost-telemetry-unavailable` "
            "at that story's boundary (Story 6.4); the epic total is a LOWER "
            "BOUND._"
        )
    return "\n".join(parts)


def _render_retry_budget(state: EpicRunState) -> str:
    budget = state.per_epic_retry_budget
    return "\n".join(
        [
            "## Retry budget",
            "",
            f"Consumed {budget.consumed} of {budget.effective_budget} "
            f"(multiplier {budget.multiplier} × {budget.story_count} stories).",
        ]
    )


def _build_marker_contexts(state: EpicRunState) -> dict[str, dict[str, object]]:
    """Synthesize the render-time marker context the loud-fail-block renderer
    needs (the epic-run-state cache does not persist ``marker_contexts``).

    ``epic-budget-exhausted`` declares ``pointer_context_fields: [epic_id,
    run_id, consumed, effective_budget]``; all four are derivable from the loaded
    ``EpicRunState``. The renderer only interpolates contexts for ACTIVE markers,
    so the entry is harmless when the marker is not present.
    """
    return {
        EPIC_BUDGET_EXHAUSTED_MARKER: {
            "epic_id": state.epic_id,
            "run_id": state.run_id,
            "consumed": state.per_epic_retry_budget.consumed,
            "effective_budget": state.per_epic_retry_budget.effective_budget,
        }
    }


def assemble_epic_bundle(
    epic_id: str,
    run_id: str,
    epic_run_state_path: pathlib.Path,
    bundle_root: pathlib.Path,
    *,
    marker_registry: MarkerClassRegistry | None = None,
    generated_at: datetime | None = None,
) -> AssembleEpicBundleResult:
    """Assemble the running/final epic-level PR bundle (AC-1, AC-2, AC-4).

    Reads the ``EpicRunState`` cache at ``epic_run_state_path``, renders the
    header + per-story status table (with per-story-artifact pointers) +
    per-story/per-epic cost partition + retry-budget-consumption line + per-epic
    loud-fail block, and atomic-writes to ``bundle_root/<epic_id>/<run_id>.md``
    (the deterministic path; mirror of :func:`compute_epic_bundle_path` when
    ``bundle_root`` is ``<repo_root>/_bmad-output/epic-pr-bundles``).

    Args:
        epic_id: The ``epic-<N>`` identifier.
        run_id: Orchestrator-domain run identifier correlating with the cache.
        epic_run_state_path: On-disk path to ``epic-run-state.yaml``.
        bundle_root: Prefix under which ``<epic_id>/<run_id>.md`` is written
            (the hook passes ``_bmad-output/epic-pr-bundles``; mirrors the
            per-story ``--bundle-root`` posture).
        marker_registry: Optional pre-loaded registry; defaults to the canonical
            taxonomy via :func:`load_marker_class_registry`.
        generated_at: Optional timezone-aware UTC timestamp rendered in the
            metadata block; defaults to ``datetime.now(timezone.utc)``. The
            injection point backs AC-4's byte-stable-fixture idempotency.

    Returns:
        :class:`AssembleEpicBundleResult`.

    Raises:
        EpicBundlePathInvariantViolation: ``epic_id`` / ``run_id`` failed the
            path-component hardening guard.
        EpicRunStateNotFound: pre-condition — the cache file is absent.
        EpicRunStateEpicIdMismatch: pre-condition — the cache is for a
            different epic.
    """
    registry = (
        marker_registry if marker_registry is not None else load_marker_class_registry()
    )
    rendered_at = (
        generated_at if generated_at is not None else datetime.now(timezone.utc)
    )
    if rendered_at.tzinfo is None:
        raise ValueError(
            "assemble_epic_bundle: generated_at must be timezone-aware UTC; got "
            "naive datetime — pass datetime.now(timezone.utc) or a timezone-aware "
            "datetime"
        )

    _reject_path_component(epic_id, name="epic_id")
    _reject_path_component(run_id, name="run_id")

    state = _load_epic_run_state(epic_run_state_path)
    if state.epic_id != epic_id:
        raise EpicRunStateEpicIdMismatch(expected=epic_id, actual=state.epic_id)

    loud_fail_block = _render_loud_fail_block(
        state.active_markers,
        marker_registry=registry,
        marker_contexts=_build_marker_contexts(state),
    )

    body_parts = [
        f"# Epic PR bundle — epic {epic_id} (run {run_id})",
        "",
        f"Epic state: {state.current_state}",
        f"Generated: {rendered_at.isoformat()}",
        "",
        _render_story_table(state),
        "",
        _render_cost_partition(state),
        "",
        _render_retry_budget(state),
        "",
        loud_fail_block,
        "",
    ]
    bundle_body = "\n".join(body_parts)

    bundle_path = bundle_root / epic_id / f"{run_id}.md"
    _atomic_write_bundle(bundle_path, bundle_body)

    return AssembleEpicBundleResult(
        bundle_path=bundle_path,
        epic_id=epic_id,
        run_id=run_id,
        current_state=state.current_state,
        story_ids=state.story_ids,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loud_fail_harness.bundle_assembly_epic",
        description=(
            "Assemble the running/final epic-level PR bundle (Story 15.3). "
            "Substrate-library invocation seam from the EXISTING Stop hook "
            "(Story 2.11 boundary; no 4th hook)."
        ),
    )
    parser.add_argument("--epic-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--epic-run-state-path", required=True, type=pathlib.Path
    )
    parser.add_argument("--bundle-root", required=True, type=pathlib.Path)
    # Accepted for CLI parity with bundle_assembly.main (the Stop hook dispatches
    # uniformly). RESERVED: the epic bundle renders directory-level per-story-
    # artifact pointers (not render-time-resolved evidence paths à la Story 6.6),
    # so it is unused at this story's scope.
    parser.add_argument("--repo-root", required=False, type=pathlib.Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    try:
        result = assemble_epic_bundle(
            epic_id=args.epic_id,
            run_id=args.run_id,
            epic_run_state_path=args.epic_run_state_path,
            bundle_root=args.bundle_root,
        )
    except (EpicBundlePathInvariantViolation, EpicRunStateNotFound, EpicRunStateEpicIdMismatch) as exc:
        # Pre-condition failures: bad path component (invalid epic_id / run_id),
        # missing cache, or cache for a different epic. The assembler had nothing
        # to assemble; NOT an assembler-logic failure (remediation-shape
        # discipline), so DO NOT emit `bundle-assembly-failed`.
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 1
    except (SystemExit, KeyboardInterrupt):
        # Pattern 5: never mask intentional process exit.
        raise
    except BaseException as exc:  # noqa: BLE001 — Story 6.9 outer catchall
        # Assembler-logic failure (epic-run-state shape mismatch, per-story-status
        # enum unresolved, render crash, internal exception). Route through the
        # EXISTING surface_assembly_failure (AC-6 — no new marker class) and exit
        # with the Story 6.9 distinct exit code. Channel 3 (persisted run-state
        # marker) is per-story-RunState-bound; the EpicRunState cache does not
        # validate as a RunState, so that channel degrades — the always-on
        # fallback diagnostic file + stderr line + exit code carry the signal.
        failed_step = classify_assembly_failure(exc, partial_bundle_path=None)
        try:
            surface_assembly_failure(
                story_id=args.epic_id,
                run_id=args.run_id,
                run_state_path=args.epic_run_state_path,
                bundle_root=args.bundle_root,
                exc=exc,
                failed_step=failed_step,
                partial_bundle_path=None,
            )
        except Exception:  # noqa: BLE001 — best-effort; AC-6 exit-code discriminator still holds
            pass
        return BUNDLE_ASSEMBLY_FAILED_EXIT_CODE
    sys.stdout.write(f"{result.bundle_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
