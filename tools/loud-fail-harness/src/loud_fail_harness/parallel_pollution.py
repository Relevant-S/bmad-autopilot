"""Story 18.2 — Cross-story state-pollution detector + emitter (FR-P2-4).

Architectural placement (ADR-003 Consequence 1 + ADR-005 Phase-2 extension):
this module is the *runtime activation* of the contract Story 14.5
pre-provisioned (the ``parallel-story-state-pollution`` marker + the ADR-005
Phase-2 invariant + the positive/negative fixture pair). Like
``parallel_dispatch.py`` it is a substrate **LIBRARY**, NOT a sixth substrate
component — the substrate-component count stays FIVE (ADR-003 Consequence 1).

Why a SEPARATE module from ``parallel_dispatch.py`` (design decision (a)):
    The marker literal ``parallel-story-state-pollution`` and the emit
    projection live here, not in ``parallel_dispatch.py``. Story 18.1's
    ``test_module_is_taxonomy_neutral`` asserts ``parallel_dispatch.py`` carries
    no pollution-marker literal; ``dispatch_stories_parallel`` DELEGATES the
    detect + emit to this library (it references ``parallel_pollution`` by name
    only), so 18.1's taxonomy-neutrality witness stays green AND the marker
    literal has exactly one home (the dedicated detection module). The detector
    is a PURE function over a claim set so the AC-7 fixture witness and the
    dispatcher feed the SAME function.

Sensor-not-advisor (FR52 / ADR-005 Phase-2 "Emit behaviour"):
    This library DETECTS and SURFACES. It never reassigns a port, re-paths an
    evidence directory, or reconciles the aggregate — remediation is the
    practitioner's (ADR-005 Phase-2: "NO auto-resolution"). The dispatcher
    pauses the epic on the existing ``epic-paused-on-escalation`` state (no enum
    widening); the ``parallel-story-state-pollution`` marker in
    ``active_markers`` discriminates a pollution pause from a quality-escalation
    pause.
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loud_fail_harness.input_hardening import harden_identifier
from loud_fail_harness.epic_run_state import (
    EpicRunState,
    EpicRunStateNotFound,
    EpicRunStateParseError,
    load_epic_run_state,
)

#: The loud-fail marker class Story 14.5 pre-provisioned (taxonomy entry 31).
#: Durable (NOT a member of ``transient_marker_classes``) so it survives
#: ``filter_transient_markers`` / ``advance_epic_run_state`` to the PR bundle.
PARALLEL_STORY_STATE_POLLUTION_MARKER = "parallel-story-state-pollution"

#: ADR-005 Phase-2 shared surface → taxonomy ``sub_classification`` (1:1 with
#: the three enumerated ``sub_classifications`` on the marker entry). The keys
#: are the fixture's ``shared_surface`` / ``colliding_surface`` vocabulary; the
#: values are the marker's sub-classification vocabulary.
_SURFACE_SUBCLASS: Mapping[str, str] = {
    "shared-port": "shared-port-collision",
    "shared-evidence-root": "shared-evidence-root-collision",
    "aggregate-run-state": "aggregate-run-state-cross-write",
}


class StoryClaim(BaseModel):
    """One live worktree's shared-surface claims (ADR-005 Phase-2 inventory).

    The runtime analogue of a single ``worktrees:`` entry in Story 14.5's
    fixtures, so the AC-7 witness drives the SAME detector with fixture-sourced
    and registry-sourced claims through one code path. ``allocated_port`` /
    ``evidence_subpath`` are ``None`` until provisioning has claimed them — a
    story that has not yet provisioned a port cannot collide on the port pool
    (None contributes NO conflict on that surface). Frozen + tuple/Mapping
    discipline (Pattern 4) for hashability and byte-stable dumps.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    allocated_port: int | None = None
    evidence_subpath: str | None = None
    aggregate_claim_story_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> "StoryClaim":
        """Input-hardening (Story 24.2 — the Epic 18 parallel-claim surface).
        ``story_id`` / ``aggregate_claim_story_id`` key the cross-story conflict
        domain; the ``min_length=1`` constraints accept whitespace-only values.
        Route both through the shared helper.
        """
        harden_identifier(self.story_id, "StoryClaim.story_id")
        harden_identifier(
            self.aggregate_claim_story_id, "StoryClaim.aggregate_claim_story_id"
        )
        return self


class PollutionConflict(BaseModel):
    """A detected cross-story collision on one shared surface.

    The fields are the marker's ``pointer_context_fields``
    (``story_id`` / ``conflicting_story_id`` / ``shared_surface``) plus the
    ``sub_classification`` — so emission is a mechanical projection (no field
    translation, no drift between detector output and marker context).
    ``story_id`` / ``conflicting_story_id`` are canonically ordered
    (``story_id`` is the lexicographically-smaller of the colliding pair) so the
    same claim set yields the SAME conflict regardless of claim ordering.
    """

    model_config = ConfigDict(frozen=True)

    sub_classification: str
    story_id: str
    conflicting_story_id: str
    shared_surface: str


class StoryClaimProvider(Protocol):
    """The main-thread claim source the parallel dispatcher injects.

    Given a story-id about to be admitted, returns the :class:`StoryClaim` to
    register in the live-claim registry. Called ONLY on the dispatching (main)
    thread (the registry is mutated single-writer per 18.1's discipline); the
    provider itself sources the port from ``env_provisioning.allocate_ephemeral_port``
    and the evidence subpath / aggregate-claim id for that story. Keyword-only +
    non-defaulted (the project's structural-callback discipline). When the
    dispatcher is called with no provider, detection is inert and the parallel
    path behaves exactly as Story 18.1 shipped it.
    """

    def __call__(self, *, story_id: str) -> StoryClaim: ...


def _conflict(surface: str, a: StoryClaim, b: StoryClaim) -> PollutionConflict:
    first, second = sorted((a.story_id, b.story_id))
    return PollutionConflict(
        sub_classification=_SURFACE_SUBCLASS[surface],
        story_id=first,
        conflicting_story_id=second,
        shared_surface=surface,
    )


def detect_state_pollution(
    claims: Sequence[StoryClaim],
) -> tuple[PollutionConflict, ...]:
    """Evaluate the three ADR-005 Phase-2 surfaces over a set of live claims.

    Pure function (no I/O, no thread state). Pairwise over distinct stories:
      (a) same non-``None`` ``allocated_port`` → ``shared-port-collision``;
      (b) same non-``None`` ``evidence_subpath`` → ``shared-evidence-root-collision``;
      (c) same ``aggregate_claim_story_id`` (one story-id owned by two live
          worktrees) → ``aggregate-run-state-cross-write``.

    Deterministic + order-independent: conflict records are canonically ordered
    by ``(sub_classification, story_id, conflicting_story_id)``, and a ``None``
    surface contributes NO conflict. (The aggregate-run-state LOST-UPDATE arm —
    a write whose pre-image disagrees with the on-disk aggregate — is detected
    separately by :func:`detect_aggregate_preimage_conflict` at the write
    boundary, since it needs the on-disk pre-image and is not pure over claims.)
    """
    conflicts: list[PollutionConflict] = []
    n = len(claims)
    for i in range(n):
        a = claims[i]
        for j in range(i + 1, n):
            b = claims[j]
            if a.story_id == b.story_id:
                continue
            if a.allocated_port is not None and a.allocated_port == b.allocated_port:
                conflicts.append(_conflict("shared-port", a, b))
            if (
                a.evidence_subpath is not None
                and a.evidence_subpath == b.evidence_subpath
            ):
                conflicts.append(_conflict("shared-evidence-root", a, b))
            if a.aggregate_claim_story_id == b.aggregate_claim_story_id:
                conflicts.append(_conflict("aggregate-run-state", a, b))
    conflicts.sort(
        key=lambda c: (c.sub_classification, c.story_id, c.conflicting_story_id)
    )
    return tuple(conflicts)


def detect_aggregate_preimage_conflict(
    epic_run_state_path: pathlib.Path,
    expected_pre_image: EpicRunState,
    *,
    story_id: str,
) -> PollutionConflict | None:
    """Lost-update guard for the aggregate-run-state surface (ADR-005 Phase-2
    "Activation boundary" — reuse Story 14.4's atomic-write discipline extended
    with a pre-image compare).

    18.1 made the aggregate single-writer (the main-thread fold), so under that
    invariant the on-disk aggregate the fold is about to overwrite ALWAYS equals
    the in-memory pre-image; this guard fires only if that invariant is ever
    violated (an out-of-band writer landed between the fold's read and write —
    a lost update). It is the loud-fail sensor for that case.

    Returns ``None`` when the aggregate is absent (the first fold has not written
    it yet) or matches the pre-image. On divergence (or an unparseable on-disk
    aggregate) returns an ``aggregate-run-state-cross-write`` conflict. The
    out-of-band writer is by definition unidentified, so both ``story_id`` and
    ``conflicting_story_id`` name the folding story (the only story-id the guard
    can attribute the divergence to).
    """
    if not epic_run_state_path.is_file():
        return None
    try:
        on_disk = load_epic_run_state(epic_run_state_path)
    except EpicRunStateNotFound:
        return None
    except EpicRunStateParseError:
        return _aggregate_lost_update_conflict(story_id)
    if on_disk == expected_pre_image:
        return None
    return _aggregate_lost_update_conflict(story_id)


def _aggregate_lost_update_conflict(story_id: str) -> PollutionConflict:
    return PollutionConflict(
        sub_classification=_SURFACE_SUBCLASS["aggregate-run-state"],
        story_id=story_id,
        conflicting_story_id=story_id,
        shared_surface="aggregate-run-state",
    )


def record_pollution_markers(
    epic_state: EpicRunState,
    conflicts: Sequence[PollutionConflict],
) -> EpicRunState:
    """Project conflicts onto durable markers + first-emission context.

    Pure function — returns a NEW :class:`EpicRunState` (or the input unchanged
    when ``conflicts`` adds nothing). For each conflict the full marker string
    ``parallel-story-state-pollution: <sub_classification>`` is appended to
    ``active_markers`` (de-dup by full marker-string equality — Story 1.4
    marker-permanence). The marker's ``pointer_context_fields`` are written to
    ``marker_contexts`` keyed by the base marker class, FIRST-emission-context
    wins (the established ``record_marker_with_context`` pattern, replicated here
    because that helper is typed for the per-story ``RunState``).
    """
    active = epic_state.active_markers
    contexts: dict[str, Mapping[str, object]] = dict(epic_state.marker_contexts)
    changed = False
    for conflict in conflicts:
        full = (
            f"{PARALLEL_STORY_STATE_POLLUTION_MARKER}: {conflict.sub_classification}"
        )
        if full in active:
            continue
        active = (*active, full)
        changed = True
        if PARALLEL_STORY_STATE_POLLUTION_MARKER not in contexts:
            contexts[PARALLEL_STORY_STATE_POLLUTION_MARKER] = {
                "story_id": conflict.story_id,
                "conflicting_story_id": conflict.conflicting_story_id,
                "shared_surface": conflict.shared_surface,
            }
    if not changed:
        return epic_state
    return epic_state.model_copy(
        update={"active_markers": active, "marker_contexts": contexts}
    )


def emit_and_pause_on_conflicts(
    epic_state: EpicRunState,
    conflicts: Sequence[PollutionConflict],
) -> EpicRunState:
    """Record the durable sub-classified marker(s) + context and transition the
    epic to ``epic-paused-on-escalation`` (the ratified pollution pause — no enum
    widening; the marker is the discriminator).

    Sensor-not-advisor: the substrate does NOT resolve the collision; it pauses
    so the practitioner inspects the named surface. Returns ``epic_state``
    unchanged when ``conflicts`` is empty. The caller persists the returned state
    via ``advance_epic_run_state`` (the durable marker survives the transient
    filter; ``marker_contexts`` survives the atomic write).
    """
    if not conflicts:
        return epic_state
    recorded = record_pollution_markers(epic_state, conflicts)
    if recorded.current_state == "epic-paused-on-escalation":
        return recorded
    return recorded.model_copy(update={"current_state": "epic-paused-on-escalation"})


__all__ = [
    "PARALLEL_STORY_STATE_POLLUTION_MARKER",
    "PollutionConflict",
    "StoryClaim",
    "StoryClaimProvider",
    "detect_aggregate_preimage_conflict",
    "detect_state_pollution",
    "emit_and_pause_on_conflicts",
    "record_pollution_markers",
]
