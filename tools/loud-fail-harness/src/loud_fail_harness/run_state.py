"""Run-state schema models + atomic-write helper layer (story 2.2).

Architectural placement (story 1.10b precedent — story 2.2 Dev Notes
"Why ``run_state.py`` is a substrate library (not a sixth substrate
component)"): this module is a sibling of
:mod:`loud_fail_harness.story_doc_validator` and the five substrate-
component modules (``envelope_validator``, ``event_validator``,
``reconciler``, ``enumeration_check``, ``fixture_coverage``). It is
**NOT a sixth substrate component**. ADR-003 Consequence 1 enumerates
exactly five substrate components (architecture.md lines 311-315); this
module is a substrate **library** consumed by Epic 2/3/4/5/6/7/8
specialist subagents at runtime to perform schema-validated, atomic,
ordered run-state writes against ``_bmad/automation/run-state.yaml``
(View 3 line 1171). The substrate-component count stays at FIVE; the
harness module count grows.

Closer in shape to ``story_doc_validator.py`` than to the directory-
scanning CI gates (``pluggability_gate.py``, ``hook_budget_gate.py``):
there is no canonical filesystem surface to scan at this story's
landing time because run-state writes happen at orchestrator runtime in
Epic 2+, not as committed filesystem artifacts on disk.

What this library provides:
    * **Pydantic v2 models** (:class:`RunState`, :class:`RetryAttempt`,
      :class:`CostToDateBySpecialist`) mirroring ``schemas/run-state.yaml``
      1:1. Frozen for hashability + immutability discipline (Pattern 4
      state-update discipline + Epic 1 retrospective Action #2).
    * **Atomic-write helper** (:func:`advance_run_state`) whose public
      function signature *structurally* requires the caller to supply a
      story-doc-update callback (no default value; no None acceptable;
      no API path that writes run-state without supplying the callback).
      The protocol is encoded in the type signature, not in a docstring
      a future contributor can ignore.
    * **Execution-order discipline**: callback first → atomic-rename
      run-state second on callback success → no run-state mutation on
      callback failure with a named diagnostic
      (:exc:`RunStateAdvanceBlocked`).

What this library enforces:
    * **NFR-R1** (PRD line 945) — atomic run-state writes via
      temp-file-plus-atomic-rename. Implemented as: write
      ``next_state.model_dump_json()`` (yaml-dumped) to a collision-
      resistant temp path
      (``<run_state_path>.tmp.<pid>.<token_hex>``); ``os.fsync`` the
      temp file's contents; ``os.replace`` the temp path over the
      target. ``os.replace`` is atomic on POSIX per the documented
      stdlib semantics; on crash mid-rename, either the prior version
      or the new version is on disk — never a partial-state file.
    * **NFR-R8** (PRD line 952) — cross-state consistency: story-doc
      writes complete before run-state advances. Encoded structurally
      as the helper's "callback first → run-state second" execution
      order. There is no API path to advance run-state that bypasses
      the callback.
    * **Pattern 4** (architecture.md lines 973-981) — "All run-state
      writes go through atomic-write helpers (temp-file-plus-atomic-
      rename per NFR-R1). No direct writes to ``run-state.yaml``
      outside the helper layer." This module IS the helper layer.
    * **ADR-005 Consequence 1** (line 509) — post-recovery run-state
      conforms to the same schema as pre-crash run-state. The
      :class:`RunState` model (and the YAML artifact at
      ``schemas/run-state.yaml`` it mirrors) IS that schema.
    * **ADR-005 Consequence 6** (line 529) — temp-file-plus-atomic-
      rename via stdlib ``pathlib`` + ``os.replace``; this module is
      the implementation.

## Story-doc-validator integration

The :func:`advance_run_state`'s ``story_doc_callback`` parameter
typically wraps a specialist's write to a documented story-doc section
(per ADR-005's multi-writer story-doc model). Callers whose callback
writes to a documented section MUST consult
:func:`loud_fail_harness.story_doc_validator.validate_section_write`
BEFORE invoking the write; a ``ValidationResult.accepted=False``
outcome is the canonical failure signal the callback returns to
:func:`advance_run_state` to *block* the run-state advance and emit
``undocumented-section-write`` per the marker-taxonomy registration
(``schemas/marker-taxonomy.yaml`` line 151).

The helper does NOT perform this consultation itself — sensor-not-
advisor (Pattern 5; ADR-005 multi-writer story-doc model): the
*caller* is the specialist that owns the section, the helper is
substrate. The helper's :exc:`RunStateAdvanceBlocked.cause` carries
the upstream :class:`StoryDocCallbackResult` so the caller has the
marker-class identifier in hand for its own envelope-level emission
per the orchestrator-event log discipline. The helper does NOT auto-
emit the ``undocumented-section-write`` marker.

Canonical caller-side integration pattern::

    from loud_fail_harness.story_doc_validator import validate_section_write
    from loud_fail_harness.run_state import (
        advance_run_state, StoryDocCallbackResult, StoryDocCallbackBlocked,
    )

    def _callback() -> StoryDocCallbackResult:
        result = validate_section_write("## Dev Agent Record")
        if not result.accepted:
            raise StoryDocCallbackBlocked(
                f"section write rejected: {result.reason}; "
                f"marker={result.marker}"
            )
        # ... actually write the story-doc section here ...
        return StoryDocCallbackResult(accepted=True)

    advance_run_state(
        run_state_path=path_to_run_state,
        next_state=next_state,
        story_doc_callback=_callback,
    )

## FR62 pluggability classification

This module is *substrate-shared library* per Story 1.10b's precedent
and ADR-003's substrate-vs-specialist boundary; consumed by Stories
2.3, 2.4, 2.6, 2.7, 2.8, 2.9, 2.10, 2.12 and Epic 4–8 successors. The
FR62 gate (Story 1.10a's :mod:`loud_fail_harness.pluggability_gate`)
does NOT flag substrate cross-imports; specialist subagents (Dev,
Review-BMAD, QA, LAD) live in ``agents/*.md`` and the gate's no-cross-
references rule applies to *that* surface, not this one.

## Forward-compat consumers

Stories that will consume :func:`advance_run_state` exclusively (no
direct file write to ``run-state.yaml`` is structurally possible per
this module's API surface — Pattern 4 enforcement):

    * Story 2.3 — per-story branch lifecycle module: branch-creation
      and branch-checkout transitions advance run-state.
    * Story 2.4 — BMAD lifecycle state-transition logic (binding
      consumer per epics.md lines 1266-1271; "any direct file write
      to run-state.yaml is structurally impossible (per Story 2.2's
      API)"); the highest-volume caller of this helper.
    * Story 2.5 — orchestrator skill scaffold; binding consumer per
      epics.md line 1293 ("initializes run-state via Story 2.2's
      helper").
    * Story 2.6 — Task-tool dispatch wrapper: dispatch-event run-state
      writes (cost-counter updates, marker emissions,
      dispatched_specialist field).
    * Story 2.7 — SubagentStop / Stop / SessionStart hooks; Stop hook
      reads run-state for PR bundle assembly per epics.md line 1369.
    * Story 2.8 / 2.9 / 2.10 — minimal Dev / Review-BMAD / QA
      wrappers; each consumes run-state at specialist-return time.
    * Story 2.12 — per-seam state streaming + per-specialist log
      persistence; consumes run-state's seam-transition events via
      the ``current_state`` + ``dispatched_specialist`` fields.
    * Stories 4.x — QA elaboration; consumes
      ``pending_qa_dispatch_payload`` field at QA dispatch.
    * Stories 5.x — retry-escalation; populates ``retry_history``
      field per FR13 / FR14.
    * Stories 6.x — cost telemetry; populates
      ``cost_to_date_by_specialist`` field per NFR-O8 / ADR-006
      Consequence 2.
    * Stories 7.x — installation / onboarding; first-run scaffolding
      writes the initial run-state via this helper.
    * Stories 8.x — resumability; SessionStart reattachment reads
      run-state via the same model (no advance, just load).

## Pydantic frozen-tuple rationale (Epic 1 retro Action #2 resolution)

Epic 1 retrospective Challenge #2 (epic-1-retro-2026-04-27.md line 57)
flagged the Pydantic-v2 frozen-model gap: ``model_config =
ConfigDict(frozen=True)`` blocks attribute reassignment but does NOT
block in-place mutation of mutable values within fields. A model
declared with ``retry_history: list[RetryAttempt]`` would still
accept ``RunState(...).retry_history.append(...)`` — silently
violating the immutability contract that motivates ``frozen=True``.

Story 2.2 is the first story to introduce new Pydantic models with
sequence fields, so it is the natural site for resolution per
retro Action #2 (line 107). The chosen resolution is **tuple-typed
sequence fields**: ``retry_history: tuple[RetryAttempt, ...]``;
``active_markers: tuple[str, ...]``. ``tuple`` is immutable by
Python's type semantics — no ``.append``, no ``.extend``, no
``__setitem__`` — so ``frozen=True`` blocks BOTH field reassignment
AND in-place mutation structurally.

The cost is verbosity at consumer call-sites: instead of
``state.retry_history.append(new)``, callers write
``state.model_copy(update={"retry_history": (*state.retry_history,
new)})``. This is a tolerable tax for the structural guarantee — and
``model_copy`` is the canonical Pydantic-v2 API for "produce a new
frozen instance with one field changed", which is exactly the
mutation semantics the orchestrator wants (every advance produces a
new ``RunState`` instance; the prior instance never mutates).

The ``cost_to_date_by_specialist`` field is shaped as a nested
:class:`CostToDateBySpecialist` Pydantic model (NOT a
``dict[str, float]``) so its frozen-ness is enforced structurally
rather than via a dict-immutability convention.

For ``last_envelope`` and ``pending_qa_dispatch_payload``, the field
type is ``dict[str, Any] | None`` — these fields ``$ref`` into
``envelope.schema.yaml`` and ``tea-handoff-contract.yaml``
respectively at the JSON Schema layer, so the envelope/handoff shape
is enforced on round-trip via the YAML artifact, not via duplicated
Pydantic models. The dict's contents are conventionally immutable in
the run-state surface (orchestrator code never mutates
``state.last_envelope["status"] = ...``); this is documented
discipline rather than structural enforcement.

## Sensor-not-advisor (PRD-level invariant + ADR-005 multi-writer)

The library RETURNS the rejection on callback failure
(:exc:`RunStateAdvanceBlocked` carries ``cause`` + ``attempted_next_
state``); it does NOT emit markers itself, does NOT auto-correct
state, does NOT log, does NOT print. Same posture as 1.4 / 1.5 / 1.6 /
1.7 / 1.8 / 1.9 / 1.10a / 1.10b / 1.12b / 2.1.

## ``find_repo_root()`` discipline (Epic 1 retro Action #1 resolution)

Epic 1 retrospective Challenge #1 (line 55) flagged ``find_repo_root()``
called at module import time, raising ``RuntimeError`` when pytest is
invoked outside the repo root. Action #1 (line 106) targets this
risk for every downstream module.

This module honors the discipline: ``find_repo_root()`` is NOT called
at module top-level. The :func:`advance_run_state` helper takes
``run_state_path: pathlib.Path`` from the caller (caller-controlled
location is the right default — the orchestrator skill knows where
its run-state lives; tests use ``tmp_path`` fixtures).

The :data:`DEFAULT_RUN_STATE_PATH` constant exposed for caller
convenience is a *relative* ``pathlib.Path`` (not anchored to any
filesystem root); callers anchor it against their own root (e.g., the
user's BMAD project root or a test ``tmp_path``). No
``find_repo_root()`` involvement.

## Determinism

    * :class:`RunState` and the nested models use Pydantic v2 frozen
      configuration; field declaration order is load-bearing for
      byte-stable ``model_dump_json()`` output (parallel to 1.4 / 1.5
      / 1.6 / 1.7 / 1.8 / 1.9 / 1.10a / 1.10b discipline).
    * :func:`advance_run_state` writes a deterministic YAML body
      (``yaml.safe_dump(..., sort_keys=False)`` preserves Pydantic's
      field declaration order); two advances against equal
      ``next_state`` arguments produce byte-identical files modulo
      the temp-file path collision-resistance suffix.
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets
from collections.abc import Callable
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

#: Marker-class string identifier (consumed from
#: ``schemas/marker-taxonomy.yaml``; same source-of-truth posture as
#: :data:`loud_fail_harness.story_doc_validator._MARKER_UNDOCUMENTED_SECTION_WRITE`).
#: Surfaced as the canonical default for callers that wrap
#: :func:`loud_fail_harness.story_doc_validator.validate_section_write` and
#: forward the rejection up through the callback contract; not used
#: internally by :func:`advance_run_state` itself (sensor-not-advisor).
_MARKER_UNDOCUMENTED_SECTION_WRITE: str = "undocumented-section-write"

#: User-installation runtime path for run-state per architecture.md View 3
#: line 1171. Relative ``pathlib.Path`` (not anchored to any filesystem
#: root); callers anchor it against their own root (e.g. the user's BMAD
#: project root, or a test ``tmp_path``). The constant being public is
#: acceptable because reading a path is not writing its file contents
#: (the structural enforcement is at the writer surface
#: :func:`advance_run_state`, not the path-naming surface). Computed
#: lazily-via-literal — no ``find_repo_root()`` involvement at module
#: import time per Epic 1 retrospective Action #1.
DEFAULT_RUN_STATE_PATH: pathlib.Path = pathlib.Path(
    "_bmad/automation/run-state.yaml"
)


class RetryAttempt(BaseModel):
    """One retry attempt entry inside :attr:`RunState.retry_history`.

    Mirrors the AC-1 schema's ``retry_history.items`` shape 1:1. MVP
    shape opened in Story 2.2; thickened additively in Story 5.5 with
    the optional ``round_id`` + ``path`` reference fields per the
    contract-header PATCH-version-additive discipline (sub-property
    addition under an existing field; no rename, no constraint
    tightening). Story 2.2-era + Story 5.1-era instances continue to
    instantiate cleanly with both new fields defaulting to ``None``.

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output. The
    field declaration order ``retry_attempt → retry_reason → round_id
    → path`` matches the schema's property declaration order
    verbatim.

    Serialization drops the ``round_id`` + ``path`` fields when
    ``None`` so that the YAML output matches the AC-2 JSON-Schema
    shape — the new sub-properties are optional (no ``required``
    constraint) and typed ``string`` (not nullable). Pre-Story-5.5
    entries serialize as ``{retry_attempt: N, retry_reason: "..."}``;
    a thickened entry serializes as ``{retry_attempt: N, retry_reason:
    "...", round_id: "round-NN", path: "..."}``. Mirrors
    :class:`CostToDateBySpecialist`'s ``_drop_none_costs`` pattern.

    Co-presence invariant (Story 5.5 review finding D-1): ``round_id``
    and ``path`` must be both set or both ``None``. A half-thickened
    entry (one set, the other absent) indicates a producer bug;
    :class:`RetryAttempt` rejects it at construction time so the
    invariant is enforced at the model boundary, not scattered across
    consumers.
    """

    model_config = ConfigDict(frozen=True)

    retry_attempt: int = Field(ge=1)
    retry_reason: str = Field(min_length=1)
    round_id: str | None = Field(
        default=None, min_length=1, pattern=r"^round-\d{2}$"
    )
    path: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _require_co_presence(self) -> "RetryAttempt":
        if (self.round_id is None) != (self.path is None):
            raise ValueError(
                "RetryAttempt.round_id and .path must be both set or both "
                "None (co-presence invariant); got "
                f"round_id={self.round_id!r}, path={self.path!r}"
            )
        return self

    @model_serializer(mode="wrap")
    def _drop_none_optional_fields(
        self,
        handler: Callable[["RetryAttempt"], dict[str, Any]],
    ) -> dict[str, Any]:
        dumped = handler(self)
        return {
            k: v
            for k, v in dumped.items()
            if not (k in ("round_id", "path") and v is None)
        }


class CostToDateBySpecialist(BaseModel):
    """Per-specialist cumulative cost-to-date map for in-flight cost
    observability per NFR-O8.

    Mirrors the AC-1 schema's ``cost_to_date_by_specialist`` shape 1:1.
    All fields optional (every specialist may be absent at pre-first-
    dispatch state). Property names follow Pattern 1's snake_case
    field-name boundary (architecture.md lines 932-935); they parallel
    the :class:`RunState`'s ``dispatched_specialist`` enum values
    transliterated to snake_case (the enum side stays kebab-case per
    Pattern 1's identifier boundary).

    Frozen + nested model (NOT ``dict[str, float]``) so its frozen-
    ness is enforced structurally rather than via a dict-immutability
    convention.

    Serialization drops fields whose value is ``None`` so that the
    YAML output matches the AC-1 JSON-Schema shape — properties are
    optional (no ``required`` constraint) and typed ``number`` (not
    nullable). Pre-first-dispatch state serializes as ``{}``; a state
    with cost only attributed to Dev serializes as ``{dev: 1.5}``.
    The model-level ``exclude_none`` discipline overrides parent
    serializers' ``exclude_none=False`` settings.
    """

    model_config = ConfigDict(frozen=True)

    dev: float | None = Field(default=None, ge=0)
    review_bmad: float | None = Field(default=None, ge=0)
    qa: float | None = Field(default=None, ge=0)
    lad: float | None = Field(default=None, ge=0)

    @model_serializer(mode="wrap")
    def _drop_none_costs(
        self,
        handler: Callable[["CostToDateBySpecialist"], dict[str, Any]],
    ) -> dict[str, Any]:
        return {k: v for k, v in handler(self).items() if v is not None}


#: Closed enum for :attr:`RunState.current_state`. BMAD lifecycle states
#: per architecture.md line 1256 + the proposed ``qa`` state per upstream
#: proposal 1 (line 1259) + ``escalated`` for the retry-budget-
#: exhaustion non-advance state per FR14. Kebab-case identifiers per
#: Pattern 1.
CurrentState = Literal[
    "ready-for-dev",
    "in-progress",
    "review",
    "qa",
    "done",
    "escalated",
]


#: Closed enum for :attr:`RunState.dispatched_specialist`. The four MVP
#: specialists plus the Phase-1.5 LAD; ``None`` represents no specialist
#: currently dispatched (story-loop entry, between specialist returns).
DispatchedSpecialist = Literal["dev", "review-bmad", "qa", "lad"]


class LastRetryDirective(BaseModel):
    """Pydantic-v2 mirror of ``$defs.last_retry_directive`` in
    ``schemas/run-state.yaml`` (added by Story 5.4 per the schema's
    1.1 → 1.2 MINOR additive bump).

    Snapshot of the most-recent fix-only retry directive declared by
    the orchestrator at retry-dispatch time per FR10 / Story 5.3
    (:class:`loud_fail_harness.retry_dispatch.RetryDispatchDirective`).
    Persisted on disk so Story 5.4's SubagentStop hook
    (``scope-assertion-verify`` CLI) can read the declared scope at
    hook time and compare it against Dev's actual git diff per FR12.

    Field semantics:
        * ``retry_mode`` — closed-enum literal ``"fix-only"`` at MVP
          mirroring ``schemas/orchestrator-event.yaml`` line 275 +
          ``run-state.yaml``'s ``$defs.last_retry_directive.retry_mode``
          enum verbatim.
        * ``affected_files`` — frozen tuple of repo-relative file path
          strings (the scope lock declaration). Sourced from
          :func:`loud_fail_harness.retry_dispatch.derive_affected_files`'s
          output. ``min_length=1`` mirrors the schema's ``minItems: 1``.

    Frozen + ``extra="forbid"``; field declaration order is load-bearing
    for byte-stable ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    retry_mode: Literal["fix-only"]
    affected_files: tuple[str, ...] = Field(min_length=1)


class RunState(BaseModel):
    """Orchestrator-domain canonical cache of flow-control state for
    the in-flight story loop.

    Mirrors ``schemas/run-state.yaml`` 1:1. Reconstructable from
    story-doc + event-log on recovery per ADR-005 Sub-decision (c);
    post-recovery instances conform to this same schema per ADR-005
    Consequence 1.

    Frozen for hashability + immutability discipline (Pattern 4
    state-update discipline + Epic 1 retro Action #2). Sequence-typed
    fields are tuple-typed (NOT list-typed) so ``frozen=True`` blocks
    BOTH field reassignment AND in-place mutation structurally; see
    the module docstring's "Pydantic frozen-tuple rationale" section
    for the full justification.

    Field declaration order matches ``schemas/run-state.yaml``'s
    ``required`` enumeration order (load-bearing for byte-stable
    ``model_dump_json()`` output).
    """

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["1.1", "1.2"]
    story_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    current_state: CurrentState
    branch_name: str = Field(min_length=1)
    dispatched_specialist: DispatchedSpecialist | None
    last_envelope: dict[str, Any] | None
    pending_qa_dispatch_payload: dict[str, Any] | None
    retry_history: tuple[RetryAttempt, ...]
    active_markers: tuple[str, ...]
    cost_to_date_by_specialist: CostToDateBySpecialist
    last_retry_directive: LastRetryDirective | None = None


class StoryDocCallbackResult(BaseModel):
    """Return shape of a story-doc callback supplied to
    :func:`advance_run_state`.

    Frozen + field-declaration-order JSON serialization (parallel to
    1.10b's :class:`ValidationResult`).

    Field semantics:
        * ``accepted`` — the canonical decision. ``True`` if the
          callback's story-doc work succeeded and run-state advance
          should proceed; ``False`` if the callback rejects the
          advance (e.g., a section-allowlist rejection forwarded from
          :func:`loud_fail_harness.story_doc_validator.validate_section_write`).
        * ``reason`` — human-readable explanation of the outcome. Free-
          form; surfaced through :exc:`RunStateAdvanceBlocked.cause`
          to the orchestrator's diagnostic envelope.
        * ``marker`` — marker-class string identifier on rejection
          (e.g. ``"undocumented-section-write"``); ``None`` on
          acceptance. The string is owned by
          ``schemas/marker-taxonomy.yaml``; the calling specialist
          emits the marker itself (sensor-not-advisor; the helper
          does NOT auto-emit).
    """

    model_config = ConfigDict(frozen=True)

    accepted: bool
    reason: str | None = None
    marker: str | None = None


#: Type alias for the story-doc callback parameter of
#: :func:`advance_run_state`. A zero-arg callable returning a
#: :class:`StoryDocCallbackResult` (or raising
#: :exc:`StoryDocCallbackBlocked`). The callback wraps the specialist's
#: documented-section write; see the module docstring's "Story-doc-
#: validator integration" section for the canonical pattern.
StoryDocCallback = Callable[[], StoryDocCallbackResult]


class StoryDocCallbackBlocked(Exception):
    """Raised by a story-doc callback to signal that the run-state
    advance MUST be blocked.

    Equivalent to returning :class:`StoryDocCallbackResult` with
    ``accepted=False`` — the helper treats both equally (the exception
    path is the more idiomatic Python form for "abort with a
    diagnostic"; the result-object path is the more idiomatic data-
    flow form for "carry an upstream rejection through").

    The exception's ``args[0]`` (or any custom attributes) are
    propagated through :exc:`RunStateAdvanceBlocked.cause` to the
    diagnostic envelope.
    """


class RunStateAdvanceBlocked(Exception):
    """Raised by :func:`advance_run_state` when the story-doc callback
    fails (raise OR non-success result), preventing the run-state
    advance per NFR-R8 cross-state consistency.

    Pattern 5 named-invariant diagnostic (architecture.md lines
    983-991): the exception surfaces both the upstream cause AND the
    attempted-next-state so the diagnostic envelope can render a
    complete picture (what the orchestrator was trying to do, and
    what blocked it).

    Attributes:
        cause: The upstream failure — either the
            ``BaseException`` the callback raised, or the
            non-success ``StoryDocCallbackResult`` it returned.
            Surfaces the marker-class identifier (when applicable)
            for the caller's envelope-level emission.
        attempted_next_state: The ``RunState`` instance the caller
            tried to advance to. Surfaces both the lifecycle
            transition (current_state value) and the full pre-
            advance state for diagnostic correlation.
    """

    def __init__(
        self,
        cause: BaseException | StoryDocCallbackResult,
        attempted_next_state: RunState,
    ) -> None:
        self.cause: BaseException | StoryDocCallbackResult = cause
        self.attempted_next_state: RunState = attempted_next_state
        super().__init__(
            f"run-state advance blocked: cause={cause!r}; "
            f"attempted_next_state.current_state={attempted_next_state.current_state!r}"
        )


class AdvanceResult(BaseModel):
    """Return shape of a successful :func:`advance_run_state` call.

    Frozen for hashability + determinism. Carries the next-state value
    (for caller convenience — avoids re-reading the file) and the
    on-disk path written (for caller logging / event-log emission).

    Field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    next_state: RunState
    wrote_path: pathlib.Path


def _serialize_run_state(state: RunState) -> str:
    """Render a :class:`RunState` instance as the canonical on-disk YAML
    body.

    Pipeline (per AC-2): ``model_dump_json`` → ``json.loads`` →
    ``yaml.safe_dump``. The JSON roundtrip canonicalizes Python types
    (``pathlib.Path``, ``tuple``, etc.) into JSON-Schema-compatible
    primitives before YAML dumping, so the on-disk file's structure
    matches the JSON Schema's structure exactly.

    ``sort_keys=False`` preserves Pydantic's field-declaration order
    (load-bearing for byte-stable output and human-readable
    inspection per NFR-O2).
    """
    json_str = state.model_dump_json(by_alias=False, exclude_none=False)
    payload: dict[str, Any] = json.loads(json_str)
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)


def advance_run_state(
    run_state_path: pathlib.Path,
    next_state: RunState,
    *,
    story_doc_callback: StoryDocCallback,
) -> AdvanceResult:
    """Advance run-state to ``next_state`` after the story-doc
    callback succeeds, atomically.

    Execution order (load-bearing per NFR-R8 + Pattern 4):

        1. Invoke ``story_doc_callback()`` synchronously and capture
           its :class:`StoryDocCallbackResult`.
        2. If the callback raised any exception OR returned a non-
           success result — DO NOT touch ``run_state_path``; raise
           :exc:`RunStateAdvanceBlocked` with ``cause=<upstream>`` and
           ``attempted_next_state=next_state``.
        3. If the callback succeeded — write ``next_state`` to a
           collision-resistant temp file
           (``<run_state_path>.tmp.<pid>.<token_hex>``); ``os.fsync``
           the temp file's contents before close; ``os.replace`` the
           temp path over ``run_state_path`` (atomic on POSIX per
           ``os.replace`` semantics — the implementation of NFR-R1's
           "temp-file-plus-atomic-rename" invariant).

    On any exception between temp-write and ``os.replace`` (e.g., an
    ``OSError`` from the rename), the temp file is unlinked
    (``missing_ok=True``) before re-raising — so on failure the
    filesystem state is "either the prior version is on disk and no
    temp file remains, OR the prior version is on disk and the temp
    file is gone after cleanup". Never a partial-state file at
    ``run_state_path`` per NFR-R1.

    The callback parameter is **keyword-only** (the ``*,`` separator)
    AND **non-defaulted** (no ``= None``, no no-op default) so that
    omitting the callback is a ``TypeError`` at call time; mypy
    strict mode (when enabled) catches the omission at type-check
    time. There is no API path to advance run-state without supplying
    the callback — the protocol is structural, not documented-only.

    Args:
        run_state_path: Caller-controlled on-disk path of the run-
            state file. The helper does NOT compute this from
            ``find_repo_root()`` or any environment variable; the
            caller (orchestrator skill or test fixture) supplies it
            explicitly.
        next_state: The :class:`RunState` instance to advance to.
            The helper does NOT validate ``next_state`` against the
            current on-disk state (lifecycle invariants are Story
            2.4's BMAD lifecycle state machine's responsibility); it
            writes whatever ``next_state`` is supplied after the
            callback succeeds.
        story_doc_callback: Zero-arg callable returning a
            :class:`StoryDocCallbackResult`. See the module
            docstring's "Story-doc-validator integration" section
            for the canonical pattern wrapping
            :func:`loud_fail_harness.story_doc_validator.validate_section_write`.

    Returns:
        :class:`AdvanceResult` carrying the written ``next_state``
        and the on-disk ``wrote_path``.

    Raises:
        RunStateAdvanceBlocked: The story-doc callback failed (raised
            an exception OR returned ``accepted=False``). Run-state
            on disk is unchanged.
        OSError: The temp-write or atomic-rename failed at the OS
            layer (e.g., disk full, permission denied). The temp
            file is unlinked before re-raise; run-state on disk is
            unchanged.
    """
    # Step 1+2: invoke callback; handle raise OR non-success result.
    try:
        callback_result = story_doc_callback()
    except BaseException as exc:
        raise RunStateAdvanceBlocked(
            cause=exc, attempted_next_state=next_state
        ) from exc
    if not callback_result.accepted:
        raise RunStateAdvanceBlocked(
            cause=callback_result, attempted_next_state=next_state
        )

    # Step 3: serialize + write to temp file + fsync + atomic-rename.
    body = _serialize_run_state(next_state)
    temp_path = run_state_path.with_name(
        f"{run_state_path.name}.tmp.{os.getpid()}.{secrets.token_hex(4)}"
    )
    try:
        # Write + fsync + close in a single managed scope.
        fd = os.open(
            temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        # Atomic rename; on POSIX this is the NFR-R1 atomicity
        # primitive. If the prior file at run_state_path existed, it
        # is replaced atomically; if it did not, the temp file is
        # renamed into place atomically.
        os.replace(temp_path, run_state_path)
    except BaseException:
        # Clean up the temp file if anything between os.open and the
        # successful os.replace failed. ``missing_ok=True`` because
        # the failure may have happened before the temp file was
        # created (very narrow window) or after a partial write.
        temp_path.unlink(missing_ok=True)
        raise

    return AdvanceResult(next_state=next_state, wrote_path=run_state_path)


__all__ = [
    "RunState",
    "RetryAttempt",
    "CostToDateBySpecialist",
    "LastRetryDirective",
    "StoryDocCallback",
    "StoryDocCallbackResult",
    "StoryDocCallbackBlocked",
    "AdvanceResult",
    "RunStateAdvanceBlocked",
    "advance_run_state",
    "DEFAULT_RUN_STATE_PATH",
]
