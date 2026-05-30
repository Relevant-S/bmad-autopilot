"""Epic-/sprint-run-state schema models + per-worktree run-state addressing
(story 14.4).

Architectural placement (ADR-003 Consequence 1 + ADR-009 + the Epic 14
substrate chain): this module is a sibling of
:mod:`loud_fail_harness.run_state` (story 2.2),
:mod:`loud_fail_harness.worktree_lifecycle` (story 14.2), and
:mod:`loud_fail_harness.story_file_lock` (story 14.3). It is **NOT a sixth
substrate component — substrate LIBRARY**. ADR-003 Consequence 1 enumerates
exactly five substrate components (architecture.md lines 310-315); the two
new cell-1 schemas this module mirrors (``schemas/epic-run-state.yaml`` +
``schemas/sprint-run-state.yaml``) are run-state-FAMILY artifacts validated by
the existing envelope-validator family's JSON-Schema machinery — no new gate
is added. The substrate-component count stays at FIVE; the harness library
count grows.

This module composes UP the Epic 14 substrate chain (run-state at story scope
→ worktree lifecycle → story-file locking → epic/sprint run-state at the
aggregate scopes). It is consumed by Epic 15 (``run --epic``), Epic 16
(``run --sprint``), and Epic 18 (``parallel_stories: true``) — none of which
exist at this story's landing time (forward-compat consumers; see below).

What this library provides:
    * **Pydantic v2 models** (:class:`EpicRunState`, :class:`SprintRunState`,
      and the nested :class:`PerEpicRetryBudget`,
      :class:`PerEpicCostPartition`, :class:`PerSprintRetryBudget`) mirroring
      ``schemas/epic-run-state.yaml`` and ``schemas/sprint-run-state.yaml``
      1:1. Frozen + tuple-typed sequence fields (Pattern 4 + Epic 1
      retrospective Action #2).
    * **Closed lifecycle enums** as module-level :data:`EpicCurrentState`,
      :data:`SprintCurrentState`, :data:`PerStoryStatus` ``Literal`` aliases
      (the ``run_state.CurrentState`` posture one + two scopes up).
    * **Per-worktree run-state addressing** (:func:`worktree_run_state_path`):
      a pure path-derivation helper. Per-worktree run-state is the EXISTING
      per-story ``loud_fail_harness.run_state.RunState`` document (no new
      model) written at the worktree-scoped path
      ``<repo_root>/_bmad/automation/worktrees/<story-id>/run-state.yaml`` per
      ADR-009 Consequence 6. The shape is byte-identical to
      ``schemas/run-state.yaml``; only the on-disk PATH differs.

What this library enforces:
    * **NFR-R1** (PRD line 980) — atomic run-state writes. All run-state-
      family writes inherit the temp-file-plus-atomic-rename contract. This
      module lands SHAPES + a PATH helper, not WRITE paths: per-worktree
      writes reuse the existing path-parameterized
      :func:`loud_fail_harness.run_state.advance_run_state` (it already
      accepts an arbitrary ``run_state_path``); epic/sprint write paths land
      in Epic 15/16.
    * **NFR-R8** (PRD line 987) — cross-state consistency: story-doc
      canonical, run-state cache, at EVERY scope. The epic-run-state and
      sprint-run-state documents are higher-altitude AGGREGATE caches
      reconstructable from the per-story story-docs + sprint-status.yaml on
      recovery (ADR-005's three-store model); they do NOT introduce a fourth
      canonical store.
    * **NFR-R2** (PRD line 981) — crash recovery. The per-worktree addressing
      convention is what lets a crashed parallel-mode worktree's run-state be
      located + reattached on SessionStart (composes with story 14.3's lock-
      staleness probe + story 8.1's reattachment at the worktree path).
    * **Pattern 1** (architecture.md File-naming + casing) — ``<kebab-
      name>.yaml`` cell-1 file-naming; snake_case structural keys; kebab-case
      identifier enum values.
    * **Pattern 4** (architecture.md state-update discipline) — every model is
      ``model_config = ConfigDict(frozen=True)``; every sequence field is
      ``tuple[…]`` not ``list[…]``; cost/budget partitions are nested Pydantic
      models, never bare ``dict[str, float]``, so frozen-ness is structural.

## Sensor-not-advisor (PRD-level invariant)

The models are pure data shapes. This module does NOT emit markers, does NOT
log, does NOT print, does NOT write to disk. :func:`worktree_run_state_path`
is a pure function (path arithmetic only). Same posture as 2.2 / 14.2 / 14.3.

## ``find_repo_root()`` discipline (Epic 1 retro Action #1 resolution)

``find_repo_root()`` is NOT called at module import time. The
:func:`_default_repo_root` helper calls it at function-call time, and only
when :func:`worktree_run_state_path` is invoked with both ``worktrees_root``
and ``repo_root`` left ``None``. Callers that supply either argument (tests
use ``tmp_path``; the orchestrator knows its own root) never reach
``find_repo_root()``. The structural witness is
``test_find_repo_root_not_called_at_import``.

## FR62 pluggability classification

This module is a *substrate-shared library* per ADR-003's substrate-vs-
specialist boundary. It references the per-story
:class:`loud_fail_harness.run_state.RunState` shape (the per-worktree run-
state document type) in prose only — the per-worktree document is THAT model,
unchanged. Substrate cross-composition is permitted; the FR62 gate
(:mod:`loud_fail_harness.pluggability_gate`) audits ``agents/*.md`` specialist-
wrapper cross-references, not substrate libraries. The reverse direction
(``run_state`` → ``epic_run_state``) is FORBIDDEN — it would couple the
ratified per-story helper to the new epic/sprint shapes — and is not present.

## Forward-compat consumers

The module has NO consumers at landing time. The binding consumers are:

    * **Stories 15.x** — epic-level orchestration: ``run --epic`` reads/writes
      :class:`EpicRunState`; Story 15.2's per-epic retry budget consumes
      :class:`PerEpicRetryBudget`; Story 15.3/15.5's cost partition consumes
      :class:`PerEpicCostPartition`. The prospective 4th atomic-write consumer
      (story 14.4 AC-6 H1 deferral) is Epic 15's ``advance_epic_run_state``.
    * **Stories 16.x** — sprint-level orchestration: ``run --sprint``
      reads/writes :class:`SprintRunState` (the schema landed here per the
      Epic 16 Story 16.1 forward-pointer at epics-phase-2.md line 476);
      Story 16.2's per-sprint budget consumes :class:`PerSprintRetryBudget`.
    * **Stories 18.x** — parallel-story execution: ``parallel_stories: true``
      uses :func:`worktree_run_state_path` to address each worktree's run-
      state document; Story 14.5 layers cross-state-consistency on the epic-
      run-state aggregate.

## Determinism

The models use Pydantic v2 frozen configuration; field declaration order
matches the schema property order (load-bearing for byte-stable
``model_dump_json()`` output — the structural witness that the Pydantic
encoding and the JSON-Schema encoding cannot drift).
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness._shared import find_repo_root

#: Closed enum for :attr:`EpicRunState.current_state` (and the value type of
#: :attr:`SprintRunState.per_epic_status`). The four epic lifecycle states are
#: sourced verbatim from Epic 15 Stories 15.1 / 15.2 / 15.4 ACs. Kebab-case
#: identifiers per Pattern 1.
EpicCurrentState = Literal[
    "epic-in-progress",
    "epic-paused-on-escalation",
    "epic-paused-on-budget",
    "epic-complete",
]

#: Closed enum for :attr:`SprintRunState.current_state`. The four sprint
#: lifecycle states mirror the epic states one scope up; sourced verbatim from
#: Epic 16 Stories 16.1 / 16.2 ACs. Kebab-case identifiers per Pattern 1.
SprintCurrentState = Literal[
    "sprint-in-progress",
    "sprint-paused-on-escalation",
    "sprint-paused-on-budget",
    "sprint-complete",
]

#: Closed enum for :attr:`EpicRunState.per_story_status` values. The six
#: ``run_state.CurrentState`` members + ``merge-ready`` per Epic 15 Story 15.3
#: line 423 ("per-story status (merge-ready / escalated / in-progress)").
#: Kebab-case identifiers per Pattern 1.
PerStoryStatus = Literal[
    "ready-for-dev",
    "in-progress",
    "review",
    "qa",
    "done",
    "escalated",
    "merge-ready",
]


class PerEpicRetryBudget(BaseModel):
    """Per-epic retry-budget aggregate (Epic 15 Story 15.2).

    Mirrors ``schemas/epic-run-state.yaml`` ``$defs.per_epic_retry_budget``
    1:1. Separate from the per-story budgets (Phase 1 Story 5.1). The
    effective budget = ``multiplier × story_count`` (default multiplier 2);
    ``consumed`` reaches ``effective_budget`` at the ``epic-paused-on-budget``
    transition.

    Frozen; field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    multiplier: int = Field(ge=1)
    story_count: int = Field(ge=0)
    effective_budget: int = Field(ge=0)
    consumed: int = Field(ge=0)


class PerEpicCostPartition(BaseModel):
    """Per-epic cost-partition aggregate (Epic 15 Stories 15.3 / 15.5;
    NFR-P5 extension).

    Mirrors ``schemas/epic-run-state.yaml`` ``$defs.per_epic_cost_partition``
    1:1. Carries the per-story cost map (story_id → cumulative cost) + the
    epic cost total the partition rolls up to.

    ``per_story_cost`` is a ``Mapping[str, float]`` with a read-only contract
    (the ``Mapping`` annotation signals it; ``frozen=True`` blocks attribute
    reassignment) — the same nuance ``run_state.RunState.marker_contexts``
    documents (Pydantic v2's Rust JSON serializer rejects ``MappingProxyType``,
    so a plain ``dict`` is used with the ``Mapping`` annotation signalling
    intent). Frozen; field declaration order is load-bearing.
    """

    model_config = ConfigDict(frozen=True)

    per_story_cost: Mapping[str, float]
    epic_cost_total: float = Field(ge=0)


class PerSprintRetryBudget(BaseModel):
    """Per-sprint retry-budget aggregate (Epic 16 Story 16.2).

    Mirrors ``schemas/sprint-run-state.yaml``
    ``$defs.per_sprint_retry_budget`` 1:1. Separate from the per-epic and
    per-story budgets; the per-epic structure one scope up (``epic_count``
    substitutes for ``story_count``).

    Frozen; field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    multiplier: int = Field(ge=1)
    epic_count: int = Field(ge=0)
    effective_budget: int = Field(ge=0)
    consumed: int = Field(ge=0)


class EpicRunState(BaseModel):
    """Orchestrator-domain canonical cache of flow-control state at EPIC scope
    for the sequential-epic loop (Epic 15 / FR-P2-1).

    Mirrors ``schemas/epic-run-state.yaml`` 1:1. A higher-altitude aggregate
    cache over the per-story run-state documents; reconstructable from the
    per-story story-docs + sprint-status.yaml on recovery per ADR-005. Does
    NOT introduce a fourth canonical store (NFR-R8).

    Frozen for hashability/immutability discipline (Pattern 4 + Epic 1 retro
    Action #2). Sequence-typed fields are tuple-typed (NOT list-typed) so
    ``frozen=True`` blocks BOTH field reassignment AND in-place mutation
    structurally. Field declaration order matches the schema's ``required``
    enumeration order (load-bearing for byte-stable ``model_dump_json()``).
    """

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"]
    epic_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    current_state: EpicCurrentState
    story_ids: tuple[str, ...]
    per_story_status: Mapping[str, PerStoryStatus]
    per_epic_retry_budget: PerEpicRetryBudget
    per_epic_cost_partition: PerEpicCostPartition
    active_markers: tuple[str, ...]


class SprintRunState(BaseModel):
    """Orchestrator-domain canonical cache of flow-control state at SPRINT
    scope for the sprint loop (Epic 16 / FR-P2-2).

    Mirrors ``schemas/sprint-run-state.yaml`` 1:1. A higher-altitude aggregate
    cache over the per-epic epic-run-state documents (plus the per-story run-
    state documents for unassigned stories); reconstructable on recovery per
    ADR-005. Does NOT introduce a fourth canonical store (NFR-R8).

    ``per_epic_status`` values are :data:`EpicCurrentState` (byte-identical to
    :attr:`EpicRunState.current_state` — co-versioned per the schema contract-
    header). ``unassigned_story_ids`` is the per-story fallback dispatch
    surface per Story 16.1 line 475.

    Frozen + tuple-typed sequence fields; field declaration order matches the
    schema's ``required`` enumeration order.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.0"]
    sprint_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    current_state: SprintCurrentState
    epic_ids: tuple[str, ...]
    per_epic_status: Mapping[str, EpicCurrentState]
    unassigned_story_ids: tuple[str, ...]
    per_sprint_retry_budget: PerSprintRetryBudget
    active_markers: tuple[str, ...]


def _default_repo_root() -> pathlib.Path:
    """Resolve the canonical repo root via :func:`loud_fail_harness._shared.
    find_repo_root` at function-call time (Epic 1 retro Action #1 discipline —
    never at module import time). Module-local copy mirroring
    ``worktree_lifecycle._default_repo_root`` (NOT a cross-import — the two
    modules keep their constant/helper surfaces decoupled per Pattern 5
    module-altitude discipline).
    """
    return find_repo_root()


def worktree_run_state_path(
    story_id: str,
    *,
    worktrees_root: pathlib.Path | None = None,
    repo_root: pathlib.Path | None = None,
) -> pathlib.Path:
    """Derive the per-worktree run-state path for ``story_id``.

    Per-worktree run-state is the EXISTING per-story
    :class:`loud_fail_harness.run_state.RunState` document (no new model; AC-2)
    written at a worktree-scoped path per ADR-009 Consequence 6:
    ``<worktrees_root>/<story_id>/run-state.yaml`` where ``worktrees_root``
    defaults to ``<repo_root>/_bmad/automation/worktrees`` (co-located with the
    per-story ``_bmad/automation/run-state.yaml`` and the
    ``_bmad/automation/locks/`` lock files; namespace-disjoint from
    ``.claude/worktrees/``).

    Resolution order (lazy — no ``find_repo_root()`` unless both roots are
    ``None``):
        * ``worktrees_root`` supplied → use it verbatim.
        * else ``repo_root`` supplied → ``<repo_root>/_bmad/automation/
          worktrees``.
        * else → ``<_default_repo_root()>/_bmad/automation/worktrees``.

    Pure function; no filesystem access, no marker emission (sensor-not-
    advisor).
    """
    if not story_id:
        raise ValueError("story_id must be non-empty")
    if worktrees_root is None:
        root = repo_root if repo_root is not None else _default_repo_root()
        worktrees_root = root / "_bmad" / "automation" / "worktrees"
    return worktrees_root / story_id / "run-state.yaml"


__all__ = [
    "EpicCurrentState",
    "EpicRunState",
    "PerEpicCostPartition",
    "PerEpicRetryBudget",
    "PerSprintRetryBudget",
    "PerStoryStatus",
    "SprintCurrentState",
    "SprintRunState",
    "worktree_run_state_path",
]
