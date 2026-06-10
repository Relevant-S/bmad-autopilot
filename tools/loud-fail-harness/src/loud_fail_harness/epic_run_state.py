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
      family writes inherit the temp-file-plus-atomic-rename contract. Story
      14.4 landed the SHAPES + a PATH helper; Story 15.1 lands the epic-scope
      WRITE path :func:`advance_epic_run_state` (the 4th atomic-write consumer
      story 14.4 AC-6 forward-pointed) by composing the single-sourced
      :func:`loud_fail_harness.run_state.atomic_write_text` primitive — NOT a
      re-implementation of the OS rename dance. Per-worktree write-backs reuse
      the existing path-parameterized
      :func:`loud_fail_harness.run_state.advance_run_state` (wrapped here by
      :func:`advance_worktree_run_state`, which layers the transient-marker
      filter); the sprint write path lands in Epic 16.
    * **NFR-R2 transient-marker discipline** (Story 15.1 AC-6) — a persisted
      (epic OR per-worktree) run-state carries ONLY durable markers. Both
      write paths filter out every marker whose taxonomy ``lifetime`` is
      ``transient`` before the atomic rename (:func:`filter_transient_markers`,
      sourced structurally from ``marker-taxonomy.yaml`` via
      :func:`loud_fail_harness.reconciler.load_marker_lifetimes` — never a
      hardcoded class list). Transient condition-markers (e.g.
      ``worktree-stale-lock``) are recomputed each cycle from live state by
      ``evaluate_reattach`` (left UNCHANGED), so a persisted-then-re-fed state
      never makes a transient marker go sticky.
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

The models are pure data shapes; the helpers do NOT emit markers, do NOT log,
do NOT print, do NOT decide flow. :func:`worktree_run_state_path` is a pure
function (path arithmetic only). The Story 15.1 write helpers
(:func:`advance_epic_run_state` / :func:`advance_worktree_run_state`) write the
run-state CACHE to disk via the atomic-write primitive — the same posture as
``run_state.advance_run_state`` (a mechanical persistence helper, not a flow
advisor). The transient-marker filter is a mechanical STRIP, not a marker
emission: it never adds a marker, only omits transient ones from the persisted
view. Same posture as 2.2 / 14.2 / 14.3.

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
specialist boundary. Story 15.1 adds real composition imports of
:func:`loud_fail_harness.run_state.atomic_write_text` /
:func:`~loud_fail_harness.run_state.advance_run_state` /
:class:`~loud_fail_harness.run_state.RunState` and of
:func:`loud_fail_harness.reconciler.load_marker_lifetimes` — substrate→
substrate cross-composition, which is permitted; the FR62 gate
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

import json
import pathlib
from collections.abc import Mapping
from typing import Any, ClassVar, Final, Literal, TypeVar

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.input_hardening import (
    harden_identifier,
    harden_path_segment,
    reject_duplicate_identifiers,
)
from loud_fail_harness.reconciler import load_marker_lifetimes
from loud_fail_harness.run_state import (
    AdvanceResult,
    RunState,
    StoryDocCallback,
    advance_run_state,
    atomic_write_text,
)

#: User-installation runtime path for epic-run-state per ADR-009 Consequence 6's
#: ``_bmad/automation/`` umbrella — co-located with the per-story
#: ``_bmad/automation/run-state.yaml`` (``run_state.DEFAULT_RUN_STATE_PATH``).
#: Relative ``pathlib.Path`` (not anchored to any filesystem root); callers
#: anchor it against their own root (the user's BMAD project root, or a test
#: ``tmp_path``). Computed lazily-via-literal — no ``find_repo_root()`` at
#: module import time per Epic 1 retrospective Action #1. The epic-run-state
#: document is an AGGREGATE CACHE (ADR-005 / NFR-R8), NOT a fourth canonical
#: store; this path names where that cache lives on disk.
DEFAULT_EPIC_RUN_STATE_PATH: pathlib.Path = pathlib.Path(
    "_bmad/automation/epic-run-state.yaml"
)

#: User-installation runtime path for sprint-run-state per ADR-009 Consequence
#: 6's ``_bmad/automation/`` umbrella — co-located with the epic-run-state and
#: per-story run-state caches (Story 16.1 AC-3). Relative ``pathlib.Path``;
#: callers anchor it against their own root. The sprint-run-state document is an
#: AGGREGATE CACHE (ADR-005 / NFR-R8) over the per-epic epic-run-state documents
#: (+ the per-story run-state documents for unassigned stories), NOT a fifth
#: canonical store; this path names where that cache lives on disk.
DEFAULT_SPRINT_RUN_STATE_PATH: pathlib.Path = pathlib.Path(
    "_bmad/automation/sprint-run-state.yaml"
)


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
    marker_contexts: Mapping[str, Mapping[str, object]] = Field(default_factory=dict)
    # Mirrors RunState.marker_contexts 1:1 (Story 18.2 AC-5) — the epic-scope
    # home for a durable marker's pointer_context_fields so the loud-fail block
    # resolves {placeholders} (e.g. parallel-story-state-pollution's
    # story_id/conflicting_story_id/shared_surface). Optional + default {} so
    # 1.0 documents without it still load; declared last to keep model_dump_json
    # byte-stable. Mapping (not MappingProxyType) — Pydantic v2's Rust JSON
    # serializer rejects MappingProxyType; frozen=True blocks reassignment.

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> EpicRunState:
        """Input-hardening (Epic 14 retro Action #2; Story 24.2 helper
        consolidation). The ``min_length=1`` field constraints reject the empty
        string but not whitespace-only / embedded-newline / null-byte values;
        ``story_ids`` carries no duplicate-rejection. This validator routes every
        externally-supplied identifier through the shared ``input_hardening``
        helpers so ``input_hardening_gate``'s Rule B sees the coverage.
        """
        harden_identifier(self.epic_id, "EpicRunState.epic_id")
        harden_identifier(self.run_id, "EpicRunState.run_id")
        for story_id in self.story_ids:
            harden_identifier(story_id, "EpicRunState.story_ids[]")
        reject_duplicate_identifiers(self.story_ids, "EpicRunState.story_ids")
        return self


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

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> SprintRunState:
        """Input-hardening (Epic 14 retro Action #2; mirrors
        :meth:`EpicRunState._harden_identifier_inputs` one scope up; Story 24.2
        helper consolidation). Routes every externally-supplied identifier
        through the shared ``input_hardening`` helpers so ``input_hardening_gate``'s
        Rule B sees the coverage.
        """
        harden_identifier(self.sprint_id, "SprintRunState.sprint_id")
        harden_identifier(self.run_id, "SprintRunState.run_id")
        for epic_id in self.epic_ids:
            harden_identifier(epic_id, "SprintRunState.epic_ids[]")
        for story_id in self.unassigned_story_ids:
            harden_identifier(story_id, "SprintRunState.unassigned_story_ids[]")
        reject_duplicate_identifiers(self.epic_ids, "SprintRunState.epic_ids")
        reject_duplicate_identifiers(
            self.unassigned_story_ids, "SprintRunState.unassigned_story_ids"
        )
        return self


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

    Input-hardening (Story 24.2 — closes deferred-work ``worktree_run_state_path``
    ``story_id`` path-traversal): ``story_id`` is routed through
    :func:`~loud_fail_harness.input_hardening.harden_path_segment`, rejecting
    whitespace-only / embedded-newline / null-byte / path-separator /
    ``..``-traversal values so a hostile ``story_id`` can never escape the
    worktrees umbrella. Pure function; no filesystem access, no marker emission
    (sensor-not-advisor).
    """
    harden_path_segment(story_id, "worktree_run_state_path.story_id")
    if worktrees_root is None:
        root = repo_root if repo_root is not None else _default_repo_root()
        worktrees_root = root / "_bmad" / "automation" / "worktrees"
    return worktrees_root / story_id / "run-state.yaml"


def epic_run_state_path_for(
    epic_id: str,
    *,
    repo_root: pathlib.Path | None = None,
) -> pathlib.Path:
    """Derive the per-epic-addressed epic-run-state path for ``epic_id``
    (Story 16.1 AC-3).

    Returns ``<repo_root>/_bmad/automation/epic-run-state-<epic-id>.yaml`` —
    a per-epic-addressed sibling of :data:`DEFAULT_EPIC_RUN_STATE_PATH` under
    ADR-009's ``_bmad/automation/`` umbrella. The sprint loop dispatches N epics
    sequentially against one repo; the single ``DEFAULT_EPIC_RUN_STATE_PATH``
    would be overwritten on each, losing every completed epic's cache that
    ``status --epic`` / ``status --sprint`` (Story 16.4) reads — so each epic
    unit gets its own addressed path. The addressing precedent is
    :func:`worktree_run_state_path` (Story 14.4 / ADR-009 Consequence 6 —
    FR45 "per-worktree run-state addressing"). The standalone ``run --epic``
    invocation keeps using :data:`DEFAULT_EPIC_RUN_STATE_PATH`; only the sprint
    loop reaches for the addressed path. The epic-run-state stays a
    reconstructable cache (NFR-R8) — this is a convenience/observability choice,
    not a new canonical store.

    Resolution: ``repo_root`` supplied → use it verbatim; else
    :func:`_default_repo_root` at call time (no ``find_repo_root()`` at import
    time per Epic 1 retro Action #1).

    Input-hardening (Epic 14 retro Action #2; Story 24.2 helper consolidation):
    ``epic_id`` is routed through :func:`~loud_fail_harness.input_hardening.harden_path_segment`,
    rejecting whitespace-only / embedded-newline / null-byte / path-separator /
    ``..``-traversal values so a malformed identifier can never compose a path
    outside the ``_bmad/automation/`` umbrella. Pure function; no filesystem
    access, no marker emission (sensor-not-advisor).
    """
    harden_path_segment(epic_id, "epic_run_state_path_for.epic_id")
    root = repo_root if repo_root is not None else _default_repo_root()
    return (
        root / "_bmad" / "automation" / f"epic-run-state-{epic_id}.yaml"
    )


def _serialize_epic_run_state(state: EpicRunState) -> str:
    """Render an :class:`EpicRunState` as the canonical on-disk YAML body.

    Mirrors ``run_state._serialize_run_state`` 1:1: ``model_dump_json`` →
    ``json.loads`` → ``yaml.safe_dump(sort_keys=False)`` so the JSON roundtrip
    canonicalizes Python types into JSON-Schema-compatible primitives and
    Pydantic's field-declaration order is preserved (load-bearing for
    byte-stable output + ``schemas/epic-run-state.yaml`` structural agreement).
    """
    json_str = state.model_dump_json(by_alias=False, exclude_none=False)
    payload: dict[str, Any] = json.loads(json_str)
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)


def _serialize_sprint_run_state(state: SprintRunState) -> str:
    """Render a :class:`SprintRunState` as the canonical on-disk YAML body.

    Mirrors :func:`_serialize_epic_run_state` 1:1 (``model_dump_json`` →
    ``json.loads`` → ``yaml.safe_dump(sort_keys=False)``) so the JSON roundtrip
    canonicalizes Python types into JSON-Schema-compatible primitives and
    Pydantic's field-declaration order is preserved (byte-stable output +
    ``schemas/sprint-run-state.yaml`` structural agreement).
    """
    json_str = state.model_dump_json(by_alias=False, exclude_none=False)
    payload: dict[str, Any] = json.loads(json_str)
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)


def _base_marker_class(marker: str) -> str:
    """Extract the base ``marker_class`` from a possibly sub-classified marker
    string (Pattern 2 ``base`` or ``base: sub``). The ``lifetime`` axis is a
    property of the base class, so a sub-classified emission
    (``worktree-stale-lock: pid-not-alive``) resolves to the same lifetime as
    the bare class.
    """
    return marker.split(": ", 1)[0]


def filter_transient_markers(
    active_markers: tuple[str, ...],
    transient_marker_classes: frozenset[str],
) -> tuple[str, ...]:
    """Return ``active_markers`` with every marker whose base class is in
    ``transient_marker_classes`` removed, order-preserving (Story 15.1 AC-6).

    Pure function — the single mechanism BOTH run-state-family write paths
    (:func:`advance_epic_run_state`, :func:`advance_worktree_run_state`)
    compose so a future transient marker is covered by adding ONE taxonomy
    field, with zero filter edits.
    """
    return tuple(
        marker
        for marker in active_markers
        if _base_marker_class(marker) not in transient_marker_classes
    )


def _resolve_transient_marker_classes(
    transient_marker_classes: frozenset[str] | None,
    taxonomy_path: pathlib.Path | None,
) -> frozenset[str]:
    """Resolve the transient-class set, preferring an explicit injection.

    Callers (the epic loop) typically load the set ONCE per run and inject it
    into every write; tests inject a deterministic set. When ``None``, the set
    is sourced from the taxonomy at function-call time (no ``find_repo_root()``
    at import time per Epic 1 retro Action #1).
    """
    if transient_marker_classes is not None:
        return transient_marker_classes
    lifetimes = load_marker_lifetimes(taxonomy_path)
    return frozenset(
        marker_class
        for marker_class, lifetime in lifetimes.items()
        if lifetime == "transient"
    )


class EpicRunStateAdvanceResult(BaseModel):
    """Return shape of a successful :func:`advance_epic_run_state` call.

    Frozen + field-declaration-order JSON serialization (parallel to
    ``run_state.AdvanceResult``). Carries the PERSISTED state (post-filter, so
    callers thread the on-disk truth forward without re-reading), the on-disk
    path written, and the transient markers that were stripped before the write
    (loud-visibility — the caller can surface "these transient markers were
    not persisted" rather than the strip being silent).

    Field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    next_state: EpicRunState
    wrote_path: pathlib.Path
    filtered_markers: tuple[str, ...]


def advance_epic_run_state(
    epic_run_state_path: pathlib.Path,
    next_state: EpicRunState,
    *,
    transient_marker_classes: frozenset[str] | None = None,
    taxonomy_path: pathlib.Path | None = None,
) -> EpicRunStateAdvanceResult:
    """Advance epic-run-state to ``next_state``, atomically, after stripping
    every transient-lifetime marker from ``active_markers`` (AC-3 + AC-6).

    The epic-scope sibling of ``run_state.advance_run_state``. Unlike the
    per-story helper, this takes NO story-doc callback: the epic-run-state
    document is an AGGREGATE CACHE (NFR-R8 / ADR-005), not a canonical store,
    so there is no story-doc to write-first at epic scope — the per-story
    story-docs are the canonical writes the per-story loop already performs
    (NFR-R8 canonical-write-first is honored one scope down; the epic cache is
    reconstructable from those).

    Execution order:

        1. Resolve the transient-class set (injected, or sourced from the
           taxonomy at call time — taxonomy-sourced, never hardcoded).
        2. Strip transient markers from ``next_state.active_markers`` via
           :func:`filter_transient_markers`. If nothing was stripped, the
           input state is persisted unchanged; otherwise a ``model_copy`` with
           the filtered tuple is persisted (the input instance is never
           mutated — frozen-model discipline).
        3. Serialize + write via ``run_state.atomic_write_text`` (the
           single-sourced temp-file-plus-atomic-rename primitive — NFR-R1). On
           any OS-layer failure the temp file is unlinked and the prior file is
           left intact (never a partial-state file at ``epic_run_state_path``).

    Args:
        epic_run_state_path: Caller-controlled on-disk path for the epic-run-
            state cache (the orchestrator anchors
            :data:`DEFAULT_EPIC_RUN_STATE_PATH` against its project root; tests
            use ``tmp_path``). The helper does NOT compute this from
            ``find_repo_root()``.
        next_state: The :class:`EpicRunState` to advance to (its input
            identifiers are hardened at construction per the model validator).
        transient_marker_classes: Optional pre-resolved transient-class set.
            When ``None``, resolved from the taxonomy.
        taxonomy_path: Optional explicit ``marker-taxonomy.yaml`` path used
            only when ``transient_marker_classes is None``.

    Returns:
        :class:`EpicRunStateAdvanceResult` with the PERSISTED (post-filter)
        state, the on-disk path, and the stripped markers.

    Raises:
        OSError: The temp-write or atomic-rename failed at the OS layer; the
            temp file is unlinked before re-raise and the prior cache is
            unchanged.
    """
    resolved = _resolve_transient_marker_classes(
        transient_marker_classes, taxonomy_path
    )
    kept = filter_transient_markers(next_state.active_markers, resolved)
    filtered = tuple(
        marker for marker in next_state.active_markers if marker not in kept
    )
    persisted_state = (
        next_state
        if kept == next_state.active_markers
        else next_state.model_copy(update={"active_markers": kept})
    )
    atomic_write_text(
        epic_run_state_path, _serialize_epic_run_state(persisted_state)
    )
    return EpicRunStateAdvanceResult(
        next_state=persisted_state,
        wrote_path=epic_run_state_path,
        filtered_markers=filtered,
    )


def advance_worktree_run_state(
    run_state_path: pathlib.Path,
    next_state: RunState,
    *,
    story_doc_callback: StoryDocCallback,
    transient_marker_classes: frozenset[str] | None = None,
    taxonomy_path: pathlib.Path | None = None,
) -> AdvanceResult:
    """Write back a per-worktree :class:`~loud_fail_harness.run_state.RunState`
    with the same transient-marker filter the epic-run-state path applies
    (AC-6 "any per-worktree write-back the epic loop performs filters out every
    transient marker").

    Thin composition over ``run_state.advance_run_state``: strip transient
    markers from ``next_state.active_markers`` first (so a recovery-recomputed
    ``worktree-stale-lock`` never gets persisted into a per-worktree run-state
    and made sticky), then delegate the canonical-write-first + atomic-rename
    to the unchanged per-story helper. The story-doc callback contract is
    preserved verbatim (NFR-R8 canonical-write-first still applies at the
    per-worktree story scope).

    Sequential Story 15.1 does not itself drive per-worktree write-backs
    (worktrees are the parallel-mode Epic 18 surface); this helper is the
    structural surface the epic loop / Epic 18 composes when it does, and the
    second witness site for the AC-7 strip-witness smoke.
    """
    resolved = _resolve_transient_marker_classes(
        transient_marker_classes, taxonomy_path
    )
    kept = filter_transient_markers(next_state.active_markers, resolved)
    persisted_state = (
        next_state
        if kept == next_state.active_markers
        else next_state.model_copy(update={"active_markers": kept})
    )
    return advance_run_state(
        run_state_path=run_state_path,
        next_state=persisted_state,
        story_doc_callback=story_doc_callback,
    )


class SprintRunStateAdvanceResult(BaseModel):
    """Return shape of a successful :func:`advance_sprint_run_state` call.

    The sprint-scope sibling of :class:`EpicRunStateAdvanceResult`. Carries the
    PERSISTED state (post-filter, so callers thread the on-disk truth forward
    without re-reading), the on-disk path written, and the transient markers
    that were stripped before the write (loud-visibility — the caller can
    surface "these transient markers were not persisted" rather than the strip
    being silent).

    Field declaration order is load-bearing for byte-stable ``model_dump_json()``
    output.
    """

    model_config = ConfigDict(frozen=True)

    next_state: SprintRunState
    wrote_path: pathlib.Path
    filtered_markers: tuple[str, ...]


def advance_sprint_run_state(
    sprint_run_state_path: pathlib.Path,
    next_state: SprintRunState,
    *,
    transient_marker_classes: frozenset[str] | None = None,
    taxonomy_path: pathlib.Path | None = None,
) -> SprintRunStateAdvanceResult:
    """Advance sprint-run-state to ``next_state``, atomically, after stripping
    every transient-lifetime marker from ``active_markers`` (Story 16.1 AC-3 +
    AC-7).

    The sprint-scope sibling of :func:`advance_epic_run_state`. Like the
    epic-scope helper — and UNLIKE the per-story ``run_state.advance_run_state``
    — this takes NO story-doc callback: the sprint-run-state document is an
    AGGREGATE CACHE (NFR-R8 / ADR-005) over the per-epic epic-run-state
    documents (+ the per-story run-state documents for unassigned stories), not
    a canonical store. The canonical writes happen TWO scopes down, inside each
    per-story loop; there is no sprint-scope canonical artifact to write-first.

    Execution order mirrors :func:`advance_epic_run_state` exactly:

        1. Resolve the transient-class set (injected, or sourced from the
           taxonomy at call time — taxonomy-sourced, never hardcoded).
        2. Strip transient markers from ``next_state.active_markers`` via
           :func:`filter_transient_markers`; persist the input unchanged when
           nothing was stripped, else a ``model_copy`` with the filtered tuple
           (the input instance is never mutated — frozen-model discipline).
        3. Serialize + write via ``run_state.atomic_write_text`` (the
           single-sourced temp-file-plus-atomic-rename primitive — NFR-R1). On
           any OS-layer failure the temp file is unlinked and the prior file is
           left intact (never a partial-state file).

    Raises:
        OSError: The temp-write or atomic-rename failed at the OS layer; the
            temp file is unlinked before re-raise and the prior cache is
            unchanged.
    """
    resolved = _resolve_transient_marker_classes(
        transient_marker_classes, taxonomy_path
    )
    kept = filter_transient_markers(next_state.active_markers, resolved)
    filtered = tuple(
        marker for marker in next_state.active_markers if marker not in kept
    )
    persisted_state = (
        next_state
        if kept == next_state.active_markers
        else next_state.model_copy(update={"active_markers": kept})
    )
    atomic_write_text(
        sprint_run_state_path, _serialize_sprint_run_state(persisted_state)
    )
    return SprintRunStateAdvanceResult(
        next_state=persisted_state,
        wrote_path=sprint_run_state_path,
        filtered_markers=filtered,
    )


class EpicRunStateNotFound(Exception):
    """Pre-condition: no epic-run-state cache file at the resolved path.

    The read-only status path (Story 15.4 ``epic_status_command.inspect_epic``)
    maps this to a named-invariant exit-1 halt (``epic-status-no-run-state``),
    NOT a marker — mirroring Story 8.4's ``no-in-flight-run-found-for-story-id``
    posture. Distinct from
    :class:`loud_fail_harness.bundle_assembly_epic.EpicRunStateNotFound` (the
    assembler's own pre-condition type, left unchurned per Story 15.4 Task 1);
    THIS public loader is the status path's clean home.
    """

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        super().__init__(f"epic-run-state cache not found at {path}")


class EpicRunStateParseError(Exception):
    """A present-but-malformed epic-run-state cache.

    Raised on a YAML error, a non-mapping top level, or a shape that fails
    :class:`EpicRunState` validation. The status caller maps this to exit 2
    (Pattern 5 harness-level error); the chained cause is preserved via
    ``from exc``.
    """

    def __init__(self, path: pathlib.Path, *, cause: str) -> None:
        self.path = path
        self.cause = cause
        super().__init__(
            f"epic-run-state cache at {path} failed to parse/validate: {cause}"
        )


def load_epic_run_state(epic_run_state_path: pathlib.Path) -> EpicRunState:
    """Read + Pydantic-validate the epic-run-state cache YAML (read-only).

    The single-sourced public loader for the read-only status path (Story
    15.4 AC-1). Returns the validated :class:`EpicRunState`; NEVER writes
    (no :func:`advance_epic_run_state`, no mutation). Distinct from
    :func:`loud_fail_harness.bundle_assembly_epic._load_epic_run_state` (the
    assembler-tuned loader, Story 15.3 — left unchurned per Story 15.4 Task 1
    so 15.3 behaviour is unchanged).

    Raises:
        EpicRunStateNotFound: no file at ``epic_run_state_path`` (pre-condition;
            the caller maps to exit 1).
        EpicRunStateParseError: present-but-malformed (unreadable, YAML error,
            non-mapping top level, or :class:`EpicRunState` validation failure;
            the caller maps to exit 2).
    """
    if not epic_run_state_path.is_file():
        raise EpicRunStateNotFound(epic_run_state_path)
    try:
        text = epic_run_state_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise EpicRunStateNotFound(epic_run_state_path) from exc
    except OSError as exc:
        raise EpicRunStateParseError(
            epic_run_state_path, cause=f"unreadable: {exc}"
        ) from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise EpicRunStateParseError(
            epic_run_state_path, cause=f"YAML error: {exc}"
        ) from exc
    if not isinstance(raw, Mapping):
        raise EpicRunStateParseError(
            epic_run_state_path,
            cause="did not parse to a YAML mapping at top level",
        )
    try:
        return EpicRunState.model_validate(dict(raw))
    except ValidationError as exc:
        raise EpicRunStateParseError(epic_run_state_path, cause=str(exc)) from exc


class SprintRunStateNotFound(Exception):
    """Pre-condition: no sprint-run-state cache file at the resolved path.

    The read-only status path (Story 16.4 ``sprint_status_command`` no-args
    sprint grouping) and ``inspect_sprint``'s no-cache branch map this to a
    named-invariant exit-1 halt, NOT a marker. Clearly namespaced under
    ``epic_run_state`` to coexist with the assembler-tuned
    :class:`loud_fail_harness.sprint_status_artifact.SprintRunStateNotFound`
    (Story 16.3, left unchurned per Story 16.4 Task 1's naming-reconciliation
    note); THIS public loader is the status / no-args path's clean home.
    """

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        super().__init__(f"sprint-run-state cache not found at {path}")


class SprintRunStateParseError(Exception):
    """A present-but-malformed sprint-run-state cache.

    Raised on a YAML error, a non-mapping top level, or a shape that fails
    :class:`SprintRunState` validation. The status caller maps this to exit 2
    (Pattern 5 harness-level error); the chained cause is preserved via
    ``from exc``.
    """

    def __init__(self, path: pathlib.Path, *, cause: str) -> None:
        self.path = path
        self.cause = cause
        super().__init__(
            f"sprint-run-state cache at {path} failed to parse/validate: {cause}"
        )


def load_sprint_run_state(sprint_run_state_path: pathlib.Path) -> SprintRunState:
    """Read + Pydantic-validate the sprint-run-state cache YAML (read-only).

    The single-sourced public loader for the read-only status / no-args path
    (Story 16.4 AC-1 / AC-5), the sprint-scope sibling of
    :func:`load_epic_run_state`. Returns the validated :class:`SprintRunState`;
    NEVER writes (no :func:`advance_sprint_run_state`, no mutation). Distinct
    from :func:`loud_fail_harness.sprint_status_artifact._load_sprint_run_state`
    (the assembler-tuned loader, Story 16.3 — left unchurned so 16.3 behaviour
    is unchanged).

    Raises:
        SprintRunStateNotFound: no file at ``sprint_run_state_path``
            (pre-condition; the caller maps to exit 1).
        SprintRunStateParseError: present-but-malformed (unreadable, YAML
            error, non-mapping top level, or :class:`SprintRunState` validation
            failure; the caller maps to exit 2).
    """
    if not sprint_run_state_path.is_file():
        raise SprintRunStateNotFound(sprint_run_state_path)
    try:
        text = sprint_run_state_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SprintRunStateNotFound(sprint_run_state_path) from exc
    except OSError as exc:
        raise SprintRunStateParseError(
            sprint_run_state_path, cause=f"unreadable: {exc}"
        ) from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SprintRunStateParseError(
            sprint_run_state_path, cause=f"YAML error: {exc}"
        ) from exc
    if not isinstance(raw, Mapping):
        raise SprintRunStateParseError(
            sprint_run_state_path,
            cause="did not parse to a YAML mapping at top level",
        )
    try:
        return SprintRunState.model_validate(dict(raw))
    except ValidationError as exc:
        raise SprintRunStateParseError(
            sprint_run_state_path, cause=str(exc)
        ) from exc


#: ``recovery-state-conflict`` marker class identifier, sourced VERBATIM from
#: ``schemas/marker-taxonomy.yaml``. Defined locally (single-literal-from-taxonomy
#: posture, parallel to
#: :data:`session_start_reattach.RECOVERY_STATE_CONFLICT_MARKER_CLASS` /
#: :data:`cross_state_recovery.RECOVERY_STATE_CONFLICT_MARKER_CLASS`) so this
#: low-level run-state module carries no import dependency on the recovery
#: modules that sit above it. Story 16.5 reuses this EXISTING class for the
#: resume-budget run_id-mismatch surface — no new top-level marker class (AC-11).
RECOVERY_STATE_CONFLICT_MARKER_CLASS: Final[
    Literal["recovery-state-conflict"]
] = "recovery-state-conflict"


class ResumeBudgetReconstructionConflict(Exception):
    """Raised when resume budget reconstruction reads a persisted run-state
    cache whose ``run_id`` does NOT match the ``run_id`` supplied to the loop
    (a stale cache from a DIFFERENT run occupying the same per-unit address).

    A genuine NFR-R8 cross-state disagreement — the budget cache is the
    canonical store for the cumulative ``consumed`` count (ADR-005) — so it
    carries the EXISTING ``recovery-state-conflict`` marker class (Story 16.5
    AC-8 / AC-11; NO new top-level marker class). The orchestrator runtime maps
    this typed substrate error to that marker; a true resume (matching
    ``run_id``) reconstructs silently. The message names BOTH conflicting
    ``run_id``s and the cache path so human triage has the disagreement fully
    localized.
    """

    marker_class: ClassVar[Literal["recovery-state-conflict"]] = (
        RECOVERY_STATE_CONFLICT_MARKER_CLASS
    )

    def __init__(
        self, *, cache_path: pathlib.Path, cache_run_id: str, loop_run_id: str
    ) -> None:
        self.cache_path = cache_path
        self.cache_run_id = cache_run_id
        self.loop_run_id = loop_run_id
        super().__init__(
            f"resume budget reconstruction conflict at {cache_path}: persisted "
            f"cache run_id {cache_run_id!r} != loop run_id {loop_run_id!r} "
            "(a stale cache from a different run at the same per-unit address)"
        )


_RunStateT = TypeVar("_RunStateT", EpicRunState, SprintRunState)


def reconstruct_budget_on_resume(
    fresh_state: _RunStateT,
    *,
    persisted: _RunStateT,
    run_id: str,
    cache_path: pathlib.Path,
    budget_field: Literal["per_epic_retry_budget", "per_sprint_retry_budget"],
    transient_marker_classes: frozenset[str],
) -> _RunStateT:
    """Carry the cumulative retry budget + durable markers forward from a
    persisted run-state cache onto a freshly-``init_*``-seeded state (Story
    16.5 AC-5..AC-8).

    The shared reconstruction primitive both scope loops compose: on resume the
    ``init_*`` seed reset ``consumed`` to 0 and recomputed ``effective_budget``
    over the (narrowed) remaining stories/epics — defeating the cumulative
    budget guard. This overwrites ONLY the budget sub-model (``budget_field``)
    and the durable ``active_markers`` with the persisted values, so the
    original unit-sized budget AND the already-consumed count survive the
    resume, and a degradation marker emitted before the pause (e.g.
    ``epic-budget-exhausted``) is not silently lost (loud-fail doctrine). Every
    other field of ``fresh_state`` (per-story/per-epic status, cost partition,
    ids) is left as freshly enumerated — per-story-status re-derivation and
    cost-partition reconstruction are explicitly OUT of scope (re-derived via
    enumerate-narrowing + the canonical stores; Story 16.5 reconstruction-scope
    boundary).

    Durable markers are filtered through ``transient_marker_classes`` (the same
    filter ``advance_*_run_state`` applies) so a recovery-recomputed transient
    marker never re-enters the aggregate.

    Raises:
        ResumeBudgetReconstructionConflict: ``persisted.run_id`` does not match
            ``run_id`` (a stale cache from a different run at the same per-unit
            address — AC-8). NOT raised on a true resume (matching ``run_id``).
    """
    if persisted.run_id != run_id:
        raise ResumeBudgetReconstructionConflict(
            cache_path=cache_path,
            cache_run_id=persisted.run_id,
            loop_run_id=run_id,
        )
    carried_markers = filter_transient_markers(
        persisted.active_markers, transient_marker_classes
    )
    return fresh_state.model_copy(
        update={
            budget_field: getattr(persisted, budget_field),
            "active_markers": carried_markers,
        }
    )


__all__ = [
    "DEFAULT_EPIC_RUN_STATE_PATH",
    "DEFAULT_SPRINT_RUN_STATE_PATH",
    "EpicCurrentState",
    "EpicRunState",
    "EpicRunStateAdvanceResult",
    "EpicRunStateNotFound",
    "EpicRunStateParseError",
    "PerEpicCostPartition",
    "PerEpicRetryBudget",
    "PerSprintRetryBudget",
    "PerStoryStatus",
    "RECOVERY_STATE_CONFLICT_MARKER_CLASS",
    "ResumeBudgetReconstructionConflict",
    "SprintCurrentState",
    "SprintRunState",
    "SprintRunStateAdvanceResult",
    "SprintRunStateNotFound",
    "SprintRunStateParseError",
    "advance_epic_run_state",
    "advance_sprint_run_state",
    "advance_worktree_run_state",
    "epic_run_state_path_for",
    "filter_transient_markers",
    "load_epic_run_state",
    "load_sprint_run_state",
    "reconstruct_budget_on_resume",
    "worktree_run_state_path",
]
