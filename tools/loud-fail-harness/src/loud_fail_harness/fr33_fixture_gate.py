"""FR33 fixture-driven reconciliation CI gate (story 1.8). See ADR-003 + FR33.

Architectural placement (story 1.8 Dev Notes "Do not create a 6th substrate
component slot"): this module is structurally a sibling of the five substrate-
component modules (envelope_validator, event_validator, reconciler,
enumeration_check, fixture_coverage) but it is **NOT a sixth substrate
component**. ADR-003 Consequence 1 enumerates exactly five (architecture.md
line 311-315); this gate is a CI **gate** that *consumes* substrate components
2 + 3 + 5 to enforce FR33's reconciliation invariant against the fixture
corpus. The component count stays at FIVE.

What this gate exercises:
    Substrate component 3 / :mod:`loud_fail_harness.reconciler` is ADR-003
    Layer A's primary mechanism (architecture.md line 313). This gate replays
    each fixture's ``expected_marker`` through ``reconciler.reconcile`` and
    asserts a clean :class:`~loud_fail_harness.reconciler.MatchedPair` round-
    trip — failing CI when reconciler logic regresses or when a fixture-side
    declaration drifts from the reconciler's behavior.

What this gate enforces:
    FR33's loud-fail-marker-completeness invariant over the *known* skip-class
    set (architecture.md line 219; PRD § FR33 line 855). The architectural
    commitment is "blocking" — not best-effort — over the fixture corpus.
    Story 6.8 (Epic 6 forward reference) lights up the *runtime* variant;
    that gate consumes the same ``reconciler.py`` component **without
    modification** (epics.md line 905 + line 2783) and emits distinct-shape
    diagnostics so debuggers can disambiguate which gate fired (epics.md
    line 2790).

Cross-story seam contract (1.7 ↔ 1.8):
    Story 1.7's :mod:`loud_fail_harness.fixture_coverage` validates COVERAGE
    (every taxonomy class has ≥1 fixture). This story validates RECONCILIATION-
    OF-COVERED (every fixture's ``expected_marker`` round-trips cleanly
    through ``reconciler.py``). The two gates run in series: 1.7's gate first
    (this story's AC-7 ordering rationale: "defense-in-depth, not redundancy"
    — when this gate fails, all upstream structural causes have already been
    ruled out).

Loud-fail discipline (Pattern 5):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — full pass: every fixture's reconciliation matched its declared
            ``expected_marker``; no findings of any class.
        1 — fixture-side or reconciliation-side regression: at least one of
            {``reconciliation_mismatch``, ``dangling_event_class``} is non-
            empty AND ``harness_bug`` is empty. Recoverable by fixing the
            fixture declaration OR the reconciler logic.
        2 — harness-level error: at least one of {``harness_bug`` non-empty,
            fixtures-dir unreadable, taxonomy unreadable / malformed, event-
            schema unreadable / malformed}. The harness itself is misconfigured;
            a developer fix to the gate's synthesis logic is required.

    Mixed-finding precedence (AC-4 final clause): if both ``harness_bug`` AND
    ``reconciliation_mismatch`` / ``dangling_event_class`` findings are
    present, exit 2 fires (harness-bug is the higher-severity class — the
    gate's own correctness is suspect). All findings of all classes ARE
    printed before exit (the precedence affects the exit CODE only —
    diagnostics from every category appear in the CI log).

Sensor-not-advisor (PRD-level invariant):
    The gate REPORTS per-fixture reconciliation outcomes with remediation
    pointers; it does NOT auto-rewrite fixtures, suggest specific reconciler
    logic changes, or recommend marker-class renames. Same posture as 1.4 /
    1.5 / 1.6 / 1.7.

Cross-component reuse posture (story 1.8 do-not-do matrix "Modify <X> to ..."):
    * :func:`loud_fail_harness.event_validator.validate_event` — REUSED for
      synthesized-payload schema validation. NOT re-implemented.
    * :func:`loud_fail_harness.event_validator.format_errors` — REUSED for
      verbatim error prose inside ``harness_bug`` finding messages.
    * :func:`loud_fail_harness.reconciler.reconcile` — REUSED for the
      reconciliation step; the reconciler API is FROZEN per story 1.4.
    * :class:`loud_fail_harness.reconciler.SkipEvent` /
      :class:`~loud_fail_harness.reconciler.Marker` /
      :class:`~loud_fail_harness.reconciler.ClassificationResult` — REUSED.
    * :func:`loud_fail_harness.reconciler.load_marker_taxonomy` — REUSED.
    * :func:`loud_fail_harness.fixture_coverage.discover_fixtures` — REUSED
      for directory walk + frontmatter parsing.
    * :func:`loud_fail_harness.fixture_coverage._parse_frontmatter` — REUSED
      (module-private; the underscore convention is non-binding and this is
      the canonical parser per the third-caller-rule's twin).
    * :func:`loud_fail_harness._shared.find_repo_root` /
      :func:`~loud_fail_harness._shared.load_schema` — REUSED for default-
      path resolution and schema loading.

Co-versioning seam (synthesized event payload vs. orchestrator-event schema):
    The per-class required-field map (:data:`_PER_CLASS_REQUIRED_FIELDS`)
    MIRRORS ``schemas/orchestrator-event.yaml``'s ``oneOf`` per-class branches
    (line 112 onward). If either drifts (e.g. a future MINOR bump adds a
    required field to ``specialist-returned``), this gate fails its own
    canonical-corpus run with ``harness_bug`` exit 2 — surfacing the schema/
    gate drift LOUDLY before downstream reconciler consumers silently
    miscompute. This is a different co-versioning relationship than the
    marker-taxonomy ↔ orchestrator-event one (per ADR-003 Consequence 2):
    that one is enforced by substrate component 4 (``enumeration_check``);
    this one is enforced by THIS gate's own canonical-corpus pass.

Determinism (AC-2 last clause + AC-6 tests):
    All synthesized payloads use literal stable identifiers (``ev-1-8-replay-
    <stem>``, ``2026-04-26T00:00:00Z``, ``1.8-replay-<stem>``, ``prompt-1-8-
    replay-<stem>``) — no ``uuid4()``, no ``datetime.now()``, no ``random``.
    All output lists sorted by ``(file_path, marker_class)`` (parallel to
    1.4 / 1.5 / 1.6 / 1.7). ``GateResult`` is a Pydantic v2 frozen model with
    field-declaration-order JSON serialization (load-bearing for byte-stable
    ``model_dump_json()``).
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections.abc import Sequence
from typing import Any, Literal, Optional

import yaml
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict

from loud_fail_harness._shared import find_repo_root, load_schema
from loud_fail_harness.event_validator import format_errors, validate_event
from loud_fail_harness.fixture_coverage import (
    Fixture,
    _parse_frontmatter,
    discover_fixtures,
)
from loud_fail_harness.reconciler import (
    ClassificationResult,
    Marker,
    SkipEvent,
    load_marker_taxonomy,
    reconcile,
)

#: Canonical orchestrator-event class enum (mirrors
#: ``schemas/orchestrator-event.yaml`` line 86-94). Co-versioned with the
#: schema; if either drifts, AC-6 ``test_per_class_required_field_synthesis``
#: fires LOUDLY.
_CANONICAL_EVENT_CLASS_ENUM: tuple[str, ...] = (
    "specialist-dispatched",
    "specialist-returned",
    "state-transition",
    "retry-attempted",
    "escalation-fired",
    "env-provisioned",
    "env-torn-down",
    "hook-fired",
    "cost-event",
)

#: Canonical default event class for synthesized payloads (AC-2 step (a)).
#: Chosen because every fixture's "skipped phase" semantics map cleanly to a
#: returning specialist reporting failure, AND ``specialist-returned``'s
#: required-field set is small + stable.
_DEFAULT_EVENT_CLASS: str = "specialist-returned"

#: Per-class required-field map MIRRORS ``schemas/orchestrator-event.yaml``'s
#: ``oneOf`` discriminated-union branches. Co-versioned with the schema; if
#: either drifts, this gate's own canonical-corpus run fails with
#: ``harness_bug`` exit 2 (the synthesized payload no longer validates).
#:
#: The map carries ONLY the per-class fields BEYOND the four common required
#: fields (``event_class``, ``event_id``, ``timestamp``, ``story_id``); the
#: common fields are populated by :func:`_synthesize_event` for every class.
#:
#: Format: ``event_class -> dict[field_name, literal_value_or_template]``.
#: Templates that need the fixture stem are filled in at synthesis time via
#: ``str.format(stem=...)``.
_PER_CLASS_REQUIRED_FIELDS: dict[str, dict[str, Any]] = {
    "specialist-dispatched": {
        "specialist": "dev",
        "prompt_id": "prompt-1-8-replay-{stem}",
        "retry_attempt": 0,
    },
    "specialist-returned": {
        "specialist": "dev",
        "prompt_id": "prompt-1-8-replay-{stem}",
        "retry_attempt": 0,
        "status": "fail",
    },
    "state-transition": {
        "from_state": "in-progress",
        "to_state": "review",
    },
    "retry-attempted": {
        "specialist": "dev",
        "retry_attempt": 1,
        "affected_files": ["src/fr33_fixture_gate.py"],
    },
    "escalation-fired": {
        "escalation_class": "qa-verification-fail",
        "bundle_artifact_path": "_bmad-output/escalation-bundles/1-8-replay.md",
    },
    "env-provisioned": {
        "env_kind": "web",
    },
    "env-torn-down": {
        "env_kind": "web",
        "outcome": "clean",
    },
    "hook-fired": {
        "hook_name": "subagent-stop",
        "exit_code": 0,
    },
    "cost-event": {
        "prompt_id": "prompt-1-8-replay-{stem}",
        "retry_attempt": 0,
        "specialist": "dev",
        "cost_delta_usd": 0,
    },
}

#: AC-5 row-1 / row-2 / row-3 remediation pointers. Verbatim per epics.md
#: line 2789 + the validator-contract table.
_RECONCILIATION_MISMATCH_REMEDIATION = (
    "(per AC-2; either (a) the fixture's expected_marker is wrong vs. "
    "taxonomy/scenario, OR (b) reconciler.py's matching logic regressed — "
    "bisect against story 1.4's commit)"
)
_DANGLING_EVENT_CLASS_REMEDIATION = (
    "(per AC-3; fix the fixture's expected_event_class to a canonical enum "
    "value, OR remove the field — it is optional per story 1.7's AC-2; OR "
    "add the new event class to schemas/orchestrator-event.yaml via the "
    "FR65 / ADR-003 skip-class-recognition workflow)"
)
_HARNESS_BUG_REMEDIATION = (
    "(per AC-4 mixed-precedence rule: this is exit 2 — fix the gate's "
    "synthesis logic before debugging fixture-side or reconciler-side "
    "findings)"
)
_SHAPE_BROKEN_REMEDIATION = (
    "(per AC-3 seam contract: story 1.7's fixture-coverage gate certifies "
    "corpus shape before this gate runs in CI; if running this gate "
    "standalone, fix the fixture's frontmatter to include a valid string "
    "expected_marker field before re-running)"
)

#: Stable literal timestamp used in every synthesized payload (AC-2
#: determinism rule + Dev Notes "do-not-do `datetime.now()`").
_SYNTHESIS_TIMESTAMP: str = "2026-04-26T00:00:00Z"

#: Source string carried in synthesized SkipEvent + Marker objects (Dev
#: Notes: "story_id literal" + "source='fixture-replay'").
_FIXTURE_REPLAY_SOURCE: str = "fixture-replay"

_STEM_SLUG_PATTERN = re.compile(r"[^a-zA-Z0-9-]+")


class Reference(BaseModel):
    """A passing fixture reference (file_path + marker_class).

    Frozen for hashability + determinism; field declaration order is load-
    bearing for byte-stable JSON dumps. Mirrors the type from
    :class:`loud_fail_harness.fixture_coverage.Reference` by SHAPE; declared
    locally per the within-module-only-coupling discipline (do not import
    cross-module Pydantic models).
    """

    model_config = ConfigDict(frozen=True)

    file_path: str
    marker_class: str


class ReplayFinding(BaseModel):
    """A single per-fixture replay finding.

    NFR-O5 named-invariant diagnostic shape: every finding names

    * ``file_path``    — display path of the offending fixture (relative to
      repo root via :func:`loud_fail_harness._shared.find_repo_root`).
    * ``marker_class`` — declared ``expected_marker`` (or empty string when
      the fixture lacks one — preserved for sort-key stability).
    * ``category``     — classification bucket the finding belongs to.
    * ``message``      — the AC-5 distinct-shape diagnostic prose verbatim.
    * ``remediation``  — one-line NFR-O5 pointer naming AC-2 / AC-3 / AC-4.

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable JSON dumps.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str
    marker_class: str
    category: Literal[
        "reconciliation-mismatch", "harness-bug", "dangling-event-class"
    ]
    message: str
    remediation: str


class GateResult(BaseModel):
    """Quad-classification fixture-driven reconciliation gate output.

    * ``passing`` — fixtures whose replay reconciled cleanly. One
      :class:`Reference` per fixture; sorted by ``(file_path,
      marker_class)``.
    * ``reconciliation_mismatch`` — fixtures whose replay diverged from the
      declared ``expected_marker`` (silent_skips / orphan_markers populated
      OR matched-pair carries a different marker_class). FAIL exit 1.
    * ``harness_bug`` — fixtures whose synthesized orchestrator-event
      payload failed schema validation (the gate's own synthesis logic is
      broken). FAIL exit 2 (mixed-precedence: highest severity).
    * ``dangling_event_class`` — fixtures whose declared
      ``expected_event_class`` is NOT in
      ``schemas/orchestrator-event.yaml``'s ``event_class`` enum. FAIL
      exit 1.

    Field declaration order matches Pydantic v2's JSON-serialization order
    (load-bearing for byte-stable dumps; parallel to 1.4 / 1.5 / 1.6 / 1.7).
    """

    model_config = ConfigDict(frozen=True)

    passing: list[Reference]
    reconciliation_mismatch: list[ReplayFinding]
    harness_bug: list[ReplayFinding]
    dangling_event_class: list[ReplayFinding]


def _stem_slug(file_path: str) -> str:
    """Render a deterministic slug from a fixture's filename stem.

    Strips the ``.md`` suffix and any directory components, then sanitizes
    non-alphanumeric/non-hyphen characters (defensive — canonical fixture
    filenames are already kebab-case per Pattern 2). Used for stable
    ``event_id`` / ``story_id`` / ``prompt_id`` literals.
    """
    name = pathlib.Path(file_path).stem
    return _STEM_SLUG_PATTERN.sub("-", name).strip("-")


def _summarize_reconcile_outcome(
    expected_marker: str, result: ClassificationResult
) -> str:
    """Render ``<actual>`` per AC-5 row 1: short prose summary of the
    reconciler's divergence from the expected clean ``MatchedPair``.

    Diagnostic shapes (AC-5 row 1 enumeration):
        * ``silent_skips=[<X>], matched=[]`` — skip survived; no marker matched.
        * ``orphan_markers=[<X>], matched=[]`` — marker survived; no skip matched.
        * ``matched=[(<Y>, <Y>)] (different marker class)`` — pair matched but
          its marker_class differs from the fixture's expectation.
        * ``matched=[] (zero matches)`` — both inputs went unmatched (atypical).
    """
    if result.silent_skips and not result.matched:
        classes = ", ".join(s.marker_class for s in result.silent_skips)
        return f"silent_skips=[{classes}], matched=[]"
    if result.orphan_markers and not result.matched:
        classes = ", ".join(m.marker_class for m in result.orphan_markers)
        return f"orphan_markers=[{classes}], matched=[]"
    if result.matched:
        first = result.matched[0]
        skip_class = first.skip_event.marker_class
        marker_class = first.marker.marker_class
        if skip_class != expected_marker or marker_class != expected_marker:
            return (
                f"matched=[({skip_class}, {marker_class})] "
                "(different marker class)"
            )
        # Correct-class pair matched but clean_match is False due to residuals
        # (non-empty silent_skips or orphan_markers alongside the match).
        residuals: list[str] = []
        if result.silent_skips:
            classes = ", ".join(s.marker_class for s in result.silent_skips)
            residuals.append(f"silent_skips=[{classes}]")
        if result.orphan_markers:
            classes = ", ".join(m.marker_class for m in result.orphan_markers)
            residuals.append(f"orphan_markers=[{classes}]")
        return (
            f"matched=[({skip_class}, {marker_class})] but unexpected "
            f"residuals: {', '.join(residuals)}"
        )
    return "matched=[] (zero matches)"


def _synthesize_event(
    fixture: Fixture,
    parsed_frontmatter: Optional[dict],
    *,
    event_class_enum: Sequence[str] = _CANONICAL_EVENT_CLASS_ENUM,
) -> tuple[Optional[dict], Optional[ReplayFinding]]:
    """Synthesize a deterministic orchestrator-event payload for ``fixture``.

    AC-2 step (a) — event-class selection rule:

        * If the fixture's frontmatter declares ``expected_event_class`` AND
          its value is in ``event_class_enum``, use it.
        * If declared AND NOT in the enum, return a ``dangling-event-class``
          finding (AC-3 row 4). The fixture is wrong, not the harness.
        * If absent / empty / non-string, default to
          :data:`_DEFAULT_EVENT_CLASS` (``specialist-returned``).

    Determinism (AC-2 last clause): all literal values are stable
    (``ev-1-8-replay-<stem>`` etc.) — no ``uuid4()``, no
    ``datetime.now()``, no ``random``. The function is pure: it does NOT
    read from disk, does NOT print, does NOT raise.
    """
    expected_marker = fixture.expected_marker or ""
    stem = _stem_slug(fixture.file_path)

    declared_event_class: Optional[str] = None
    if isinstance(parsed_frontmatter, dict):
        raw = parsed_frontmatter.get("expected_event_class")
        if isinstance(raw, str) and raw:
            declared_event_class = raw

    event_class: str
    if declared_event_class is not None:
        if declared_event_class not in event_class_enum:
            canonical = ", ".join(event_class_enum)
            message = (
                f"Fixture event-class declaration invalid: synthetic-story "
                f"'{stem}' declared expected_event_class "
                f"'{declared_event_class}' which is not in "
                f"schemas/orchestrator-event.yaml's event_class enum "
                f"(canonical enum: {canonical})."
            )
            finding = ReplayFinding(
                file_path=fixture.file_path,
                marker_class=expected_marker,
                category="dangling-event-class",
                message=message,
                remediation=_DANGLING_EVENT_CLASS_REMEDIATION,
            )
            return (None, finding)
        event_class = declared_event_class
    else:
        event_class = _DEFAULT_EVENT_CLASS

    payload: dict[str, Any] = {
        "event_class": event_class,
        "event_id": f"ev-1-8-replay-{stem}",
        "timestamp": _SYNTHESIS_TIMESTAMP,
        "story_id": f"1.8-replay-{stem}",
    }

    per_class = _PER_CLASS_REQUIRED_FIELDS.get(event_class, {})
    for key, value in per_class.items():
        if isinstance(value, str):
            payload[key] = value.format(stem=stem)
        else:
            payload[key] = value

    return (payload, None)


def replay_fixture(
    fixture: Fixture,
    parsed_frontmatter: Optional[dict],
    taxonomy: set[str],
    event_schema: dict,
) -> tuple[Optional[Reference], Optional[ReplayFinding]]:
    """Replay a single fixture through the reconciliation invariant.

    AC-2 algorithm:
        (a) synthesize an orchestrator-event payload
        (b) validate the payload against ``event_schema``
        (c) construct ``SkipEvent`` + ``Marker`` carrying
            ``fixture.expected_marker``
        (d) call :func:`reconcile`
        (e) assert the outcome is a clean :class:`MatchedPair`

    Pure: does NOT read from disk, does NOT print, does NOT raise on per-
    fixture mismatch. Returns ``(Reference, None)`` on pass and
    ``(None, ReplayFinding(category=...))`` on any failure path. Skips
    fixtures whose frontmatter shape was already broken upstream
    (``expected_marker is None`` — story 1.7's gate has already failed CI
    in canonical CI ordering).

    The ``taxonomy`` argument is unused inside this function; it is accepted
    for symmetry with :func:`run_fr33_fixture_gate`'s contract and for future
    extensions (e.g. story 6.8's runtime-mode flag) without changing the
    public surface.
    """
    del taxonomy  # see docstring; reserved for future extensions

    if fixture.expected_marker is None:
        # Per AC-3 final clause: "NEVER as silent passes." In canonical CI
        # ordering story 1.7's gate runs first and fails before this gate runs,
        # so this path is unreachable in production. When this gate runs
        # standalone against a shape-broken corpus, surface as harness_bug so
        # the developer knows upstream gate certification was skipped.
        stem = _stem_slug(fixture.file_path)
        message = (
            f"Harness bug: synthetic-story '{stem}' has no expected_marker — "
            f"story 1.7's fixture-coverage gate should have caught this upstream "
            f"(frontmatter shape violation: expected_marker missing or non-string). "
            f"Inspect the fixture's frontmatter or ensure story 1.7's gate ran "
            f"first."
        )
        return (
            None,
            ReplayFinding(
                file_path=fixture.file_path,
                marker_class="",
                category="harness-bug",
                message=message,
                remediation=_SHAPE_BROKEN_REMEDIATION,
            ),
        )

    expected_marker = fixture.expected_marker

    payload, dangling_finding = _synthesize_event(fixture, parsed_frontmatter)
    if dangling_finding is not None:
        return (None, dangling_finding)

    if payload is None:
        raise RuntimeError(
            "_synthesize_event returned (None, None) — programming error in this gate"
        )

    schema_errors = validate_event(payload, event_schema)
    if schema_errors:
        stem = _stem_slug(fixture.file_path)
        verbatim_errors = format_errors(schema_errors).replace("\n", " | ")
        message = (
            f"Harness bug: synthetic-story '{stem}' replay produced an "
            f"orchestrator-event that failed schema validation. Synthesized "
            f"event_class: {payload.get('event_class', '<unknown>')}. "
            f"Validation error: {verbatim_errors}. Inspect "
            f"fr33_fixture_gate.py's payload-synthesis logic — the canonical "
            f"defaults have drifted from schemas/orchestrator-event.yaml."
        )
        finding = ReplayFinding(
            file_path=fixture.file_path,
            marker_class=expected_marker,
            category="harness-bug",
            message=message,
            remediation=_HARNESS_BUG_REMEDIATION,
        )
        return (None, finding)

    story_id = payload["story_id"]
    skip = SkipEvent(
        marker_class=expected_marker,
        story_id=story_id,
        source=_FIXTURE_REPLAY_SOURCE,
    )
    marker = Marker(
        marker_class=expected_marker,
        story_id=story_id,
        source=_FIXTURE_REPLAY_SOURCE,
    )

    result = reconcile([skip], [marker])

    clean_match = (
        len(result.matched) == 1
        and result.matched[0].skip_event.marker_class == expected_marker
        and result.matched[0].marker.marker_class == expected_marker
        and not result.silent_skips
        and not result.orphan_markers
    )

    if clean_match:
        return (
            Reference(file_path=fixture.file_path, marker_class=expected_marker),
            None,
        )

    stem = _stem_slug(fixture.file_path)
    summary = _summarize_reconcile_outcome(expected_marker, result)
    message = (
        f"Fixture reconciliation failed: synthetic-story '{stem}' declared "
        f"expected_marker '{expected_marker}' but reconciler produced "
        f"{summary}. Inspect harness logic or fixture declaration."
    )
    finding = ReplayFinding(
        file_path=fixture.file_path,
        marker_class=expected_marker,
        category="reconciliation-mismatch",
        message=message,
        remediation=_RECONCILIATION_MISMATCH_REMEDIATION,
    )
    return (None, finding)


def _resolve_fixture_path(
    file_path: str, fixtures_dir: pathlib.Path
) -> pathlib.Path:
    """Resolve a :class:`Fixture`'s ``file_path`` to an absolute path on disk.

    ``file_path`` is either an absolute path (tmp_path / out-of-repo case
    from :func:`fixture_coverage._display_path`) or a repo-relative display
    path like ``examples/synthetic-stories/<X>.md``. The fixture corpus is
    flat (story 1.7 contract — subdirectory fixtures already carry shape
    violations and are filtered out before this function is reached), so
    resolving against ``fixtures_dir`` by filename basename is sufficient.
    """
    p = pathlib.Path(file_path)
    if p.is_absolute():
        return p
    return fixtures_dir / p.name


def _load_parsed_frontmatter(
    fixture: Fixture, fixtures_dir: pathlib.Path
) -> Optional[dict]:
    """Re-read a fixture's content and re-parse its frontmatter.

    Story 1.7's :class:`Fixture` model deliberately does NOT expose the
    parsed frontmatter dict (that would break its byte-stability invariant).
    The third-caller-rule's twin justifies the cross-module use of
    :func:`fixture_coverage._parse_frontmatter`: it is the canonical parser,
    re-implementing it would duplicate logic already validated by 1.7's
    AC-6 contract-coverage matrix, and the underscore convention is non-
    binding.

    Returns the parsed dict (or None for shape-broken / unreadable
    fixtures). Errors here do NOT raise — :func:`replay_fixture` handles
    ``expected_marker is None`` by returning ``(None, None)`` (skip), and
    ``parsed_frontmatter is None`` by defaulting to
    :data:`_DEFAULT_EVENT_CLASS`.
    """
    if fixture.expected_marker is None:
        return None
    abs_path = _resolve_fixture_path(fixture.file_path, fixtures_dir)
    try:
        text = abs_path.read_text(encoding="utf-8")
    except OSError:
        return None
    parsed, _ = _parse_frontmatter(text, fixture.file_path)
    return parsed


def run_fr33_fixture_gate(
    fixtures: list[Fixture],
    taxonomy: set[str],
    event_schema: dict,
    *,
    fixtures_dir: pathlib.Path,
) -> GateResult:
    """Replay every fixture; partition results into the four buckets.

    Iterates ``fixtures`` in input order, re-reads each fixture's frontmatter
    via :func:`_load_parsed_frontmatter`, and calls :func:`replay_fixture`.
    Partitions results into the four :class:`GateResult` buckets per AC-3.
    NEVER bails after the first finding within a category — every category is
    collected end-to-end before output (parallel to 1.5 / 1.7).

    Sorted-output discipline (AC-3 + AC-6 determinism rule): ``passing`` and
    the three finding lists are sorted by ``(file_path, marker_class)`` —
    parallel to 1.4 / 1.5 / 1.6 / 1.7's lex-sort discipline.
    """
    passing: list[Reference] = []
    reconciliation_mismatch: list[ReplayFinding] = []
    harness_bug: list[ReplayFinding] = []
    dangling_event_class: list[ReplayFinding] = []

    for fixture in fixtures:
        parsed = _load_parsed_frontmatter(fixture, fixtures_dir)
        ref, finding = replay_fixture(fixture, parsed, taxonomy, event_schema)
        if ref is not None:
            passing.append(ref)
            continue
        if finding is None:
            # Defensive: replay_fixture no longer returns (None, None) after
            # the F1 fix; this guard is kept as a safety net for future changes.
            continue
        if finding.category == "reconciliation-mismatch":
            reconciliation_mismatch.append(finding)
        elif finding.category == "harness-bug":
            harness_bug.append(finding)
        elif finding.category == "dangling-event-class":
            dangling_event_class.append(finding)

    def _ref_key(r: Reference) -> tuple[str, str]:
        return (r.file_path, r.marker_class)

    def _finding_key(f: ReplayFinding) -> tuple[str, str]:
        return (f.file_path, f.marker_class)

    passing.sort(key=_ref_key)
    reconciliation_mismatch.sort(key=_finding_key)
    harness_bug.sort(key=_finding_key)
    dangling_event_class.sort(key=_finding_key)

    return GateResult(
        passing=passing,
        reconciliation_mismatch=reconciliation_mismatch,
        harness_bug=harness_bug,
        dangling_event_class=dangling_event_class,
    )


def format_findings(
    result: GateResult,
    *,
    fixtures_dir: str,
    taxonomy_path: str,
    event_schema_path: str,
) -> str:
    """Render a :class:`GateResult` for stdout.

    Header naming inputs; passing-summary line; per-bucket finding lists with
    AC-5 distinct-shape diagnostics; footer Summary line. Mirrors the
    "name the offending entity + remediation pointer" discipline from 1.5 /
    1.6 / 1.7. The Summary footer's bucket order matches
    :class:`GateResult`'s field declaration order.
    """
    lines: list[str] = []
    lines.append("FR33 fixture-driven reconciliation gate (story 1.8)")
    lines.append(f"  fixtures dir:    {fixtures_dir}")
    lines.append(f"  taxonomy:        {taxonomy_path}")
    lines.append(f"  event schema:    {event_schema_path}")
    lines.append("")

    has_findings = bool(
        result.reconciliation_mismatch
        or result.harness_bug
        or result.dangling_event_class
    )
    passing_line = (
        f"OK: {len(result.passing)} passing fixture(s) reconciled cleanly"
    )
    if has_findings:
        passing_line += " (but findings below)"
    lines.append(passing_line + ".")

    if result.reconciliation_mismatch:
        lines.append("")
        lines.append(
            f"FAIL: {len(result.reconciliation_mismatch)} "
            "reconciliation-mismatch finding(s)."
        )
        for f in result.reconciliation_mismatch:
            lines.append(f"  - {f.message} {f.remediation}")

    if result.harness_bug:
        lines.append("")
        lines.append(
            f"FAIL: {len(result.harness_bug)} harness-bug finding(s)."
        )
        for f in result.harness_bug:
            lines.append(f"  - {f.message} {f.remediation}")

    if result.dangling_event_class:
        lines.append("")
        lines.append(
            f"FAIL: {len(result.dangling_event_class)} "
            "dangling-event-class finding(s)."
        )
        for f in result.dangling_event_class:
            lines.append(f"  - {f.message} {f.remediation}")

    lines.append("")
    lines.append(
        f"Summary: {len(result.passing)} passing fixture(s), "
        f"{len(result.reconciliation_mismatch)} reconciliation-mismatch finding(s), "
        f"{len(result.harness_bug)} harness-bug finding(s), "
        f"{len(result.dangling_event_class)} dangling-event-class finding(s)."
    )
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fr33-fixture-gate",
        description=(
            "FR33 fixture-driven reconciliation CI gate. Replays each "
            "synthetic-story fixture through reconciler.py and asserts the "
            "fixture's expected_marker round-trips cleanly as a "
            "MatchedPair. Story 1.8; ADR-003 + FR33."
        ),
    )
    parser.add_argument(
        "--fixtures-dir",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to examples/synthetic-stories/ (default: "
            "<repo-root>/examples/synthetic-stories/). Test-injection flag; "
            "CI invocations omit it."
        ),
    )
    parser.add_argument(
        "--taxonomy-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to marker-taxonomy.yaml (default: "
            "<repo-root>/schemas/marker-taxonomy.yaml). Test-injection flag; "
            "CI invocations omit it."
        ),
    )
    parser.add_argument(
        "--event-schema",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to orchestrator-event.yaml (default: "
            "<repo-root>/schemas/orchestrator-event.yaml). Test-injection "
            "flag; CI invocations omit it."
        ),
    )
    return parser


def _display_path(
    path: pathlib.Path, repo_root: Optional[pathlib.Path] = None
) -> str:
    """Render ``path`` relative to repo root if possible; absolute otherwise.

    Mirrors :func:`fixture_coverage._display_path`'s posture so canonical CI
    invocations produce stable diff-friendly relative paths and tmp_path
    invocations fall back to absolute (which is still informative in stdout).
    """
    try:
        rr = repo_root if repo_root is not None else find_repo_root()
        return str(path.resolve().relative_to(rr.resolve()))
    except (RuntimeError, ValueError):
        return str(path.resolve())


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    fixtures_dir: pathlib.Path
    taxonomy_path: pathlib.Path
    event_schema_path: pathlib.Path
    repo_root: Optional[pathlib.Path] = None
    if (
        args.fixtures_dir is None
        or args.taxonomy_path is None
        or args.event_schema is None
    ):
        try:
            repo_root = find_repo_root()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        fixtures_dir = (
            args.fixtures_dir or repo_root / "examples" / "synthetic-stories"
        )
        taxonomy_path = (
            args.taxonomy_path or repo_root / "schemas" / "marker-taxonomy.yaml"
        )
        event_schema_path = (
            args.event_schema or repo_root / "schemas" / "orchestrator-event.yaml"
        )
    else:
        fixtures_dir = args.fixtures_dir
        taxonomy_path = args.taxonomy_path
        event_schema_path = args.event_schema

    try:
        taxonomy = load_marker_taxonomy(taxonomy_path)
    except RuntimeError as exc:
        print(
            f"harness-level error: marker-taxonomy malformed: {taxonomy_path}: {exc}",
            file=sys.stderr,
        )
        return 2
    except OSError as exc:
        print(
            "harness-level error: marker-taxonomy unreadable: "
            f"{taxonomy_path}: {exc}",
            file=sys.stderr,
        )
        return 2
    except yaml.YAMLError as exc:
        print(
            "harness-level error: marker-taxonomy YAML parse failure: "
            f"{taxonomy_path}: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        event_schema = load_schema(event_schema_path)
    except OSError as exc:
        print(
            "harness-level error: orchestrator-event schema unreadable: "
            f"{event_schema_path}: {exc}",
            file=sys.stderr,
        )
        return 2
    except (SchemaError, yaml.YAMLError) as exc:
        print(
            "harness-level error: orchestrator-event schema malformed: "
            f"{event_schema_path}: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        fixtures = discover_fixtures(fixtures_dir, repo_root=repo_root)
    except FileNotFoundError as exc:
        print(f"harness-level error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(
            "harness-level error: examples/synthetic-stories/ unreadable: "
            f"{fixtures_dir}: {exc}",
            file=sys.stderr,
        )
        return 2

    result = run_fr33_fixture_gate(
        fixtures, taxonomy, event_schema, fixtures_dir=fixtures_dir
    )
    print(
        format_findings(
            result,
            fixtures_dir=_display_path(fixtures_dir, repo_root=repo_root),
            taxonomy_path=_display_path(taxonomy_path, repo_root=repo_root),
            event_schema_path=_display_path(event_schema_path, repo_root=repo_root),
        )
    )

    # Mixed-precedence rule (AC-4 final clause): harness-bug wins; exit 2.
    if result.harness_bug:
        return 2
    if result.reconciliation_mismatch or result.dangling_event_class:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
