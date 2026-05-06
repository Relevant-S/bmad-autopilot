"""FR33 runtime reconciliation CI gate (story 6.8). See ADR-003 + FR33.

Architectural placement (story 6.8 Dev Notes "Substrate-vs-specialist boundary"):
this module is structurally a sibling of the five substrate-component modules
(envelope_validator, event_validator, reconciler, enumeration_check,
fixture_coverage) AND of story 1.8's :mod:`fr33_fixture_gate`, but it is **NOT
a sixth substrate component**. ADR-003 Consequence 1 enumerates exactly five
(architecture.md line 311-315); this gate is a CI **gate** that *consumes*
substrate-component-3 (:mod:`loud_fail_harness.reconciler`) to enforce FR33's
reconciliation invariant against captured reference-project orchestrator-event
logs. The component count stays at FIVE.

What this gate exercises (vs. story 1.8's fixture gate):
    Both gates compose with substrate-component-3 / :mod:`reconciler`'s
    :func:`reconcile` WITHOUT modification (story 1.8 AC-4 + story 6.8 AC-1 —
    epics.md line 905 + line 2783). The fixture gate (story 1.8) operates on
    SYNTHETIC fixtures from ``examples/synthetic-stories/``; this gate operates
    on CAPTURED reference-project run logs from
    ``tools/loud-fail-harness/tests/fixtures/runtime-captures/``. The two
    gates run independently in CI; their CI-failure diagnostics are
    structurally distinct (story 6.8 AC-2) so debuggers know which gate fired
    without re-deriving from the marker-class string (Story 1.11's flat-
    routing principle).

Input contract (epics.md lines 2786-2802 verbatim — story 6.8 AC-2 + AC-3):
    Each capture directory carries TWO files:

    * ``events.jsonl`` — one orchestrator-event entry per line; canonical
      shape per story 2.12 (:mod:`loud_fail_harness.event_streaming`'s
      :func:`default_event_log_path` resolves the canonical user-runtime
      location ``_bmad-output/qa-evidence/<story_id>/<run_id>/events.jsonl``
      per ADR-001's append-only single-writer contract). Skip-event entries
      additionally carry an optional ``marker_class`` field (kebab-case
      Pattern 2 identifier) AND an optional ``emission_site`` field (free-
      form code-surface string used by the AC-2 verbatim diagnostic
      template's ``{code_surface}`` placeholder). Entries without
      ``marker_class`` are non-skip events and are filtered out of the
      reconciler input. See ``tests/fixtures/runtime-captures/README.md``
      for the synthesis convention.
    * ``run-state.yaml`` — story 2.2's atomic run-state schema; the
      captured run's final ``active_markers`` tuple (string-of-marker-class
      identifiers per Pattern 2's ``<base-class>: <sub-classification>``
      shape) is the runtime marker source. ZERO new fields added by story
      6.8.

Capture-format extension fields (relaxed shape vs canonical schema):
    The canonical ``schemas/orchestrator-event.yaml`` per-class branches
    declare ``additionalProperties: false``; promoting ``marker_class`` and
    ``emission_site`` to canonical fields is a forward-looking Phase 2
    thickening tracked in ``deferred-work.md`` (per story 6.8 Dev Notes
    "Non-trivial design decisions" #2). At MVP, the runtime gate validates
    SHAPE (the four common required fields per
    :data:`_COMMON_REQUIRED_FIELDS`) rather than calling
    :func:`event_validator.validate_event` against the strict canonical
    schema — strict validation would loud-fail on every skip-event entry.
    The ``event_schema`` argument is accepted for symmetry with story 1.8's
    contract and for future Phase-2 promotion of ``marker_class`` /
    ``emission_site`` to canonical fields without changing the public
    surface.

Skip-event identification (story 6.8 surface enumeration item (iv)):
    An events.jsonl entry is a skip-event if it carries a non-empty
    ``marker_class`` field (kebab-case Pattern 2 identifier). Other entries
    are filtered out of the reconciler input — non-skip events
    (``state-transition``, ``specialist-dispatched``, etc.) do not
    contribute to FR33's marker-emission reconciliation invariant.

Marker extraction (story 6.8 surface enumeration item (v)):
    Each entry in ``run_state.active_markers`` is parsed via Pattern 2's
    ``<base-class>: <sub-classification>`` split; the matching key in
    :func:`reconcile` is base-class only (sub-classifications are
    diagnostic per :mod:`reconciler`'s ``_matches`` algorithm — see story
    6.8 Dev Notes "Non-trivial design decisions" #3). Markers whose base-
    class is NOT in the loaded taxonomy surface as
    ``marker-taxonomy-mismatch`` findings (loud-fail per NFR-O5).

Diagnostic shape (story 6.8 AC-2 verbatim — epics.md line 2790):
    Reconciliation-mismatch findings render the AC-2 verbatim template:
    ``Runtime reconciliation failed: reference-project run produced skip-
    event class `<X>` at code surface `<surface>` but no emitted marker
    reconciled. Inspect specialist or hook at `<surface>` for missing
    emission.`` The ``<X>`` placeholder is the missing skip-event marker-
    class; the ``<surface>`` placeholder is the captured event-log entry's
    optional ``emission_site`` field (or :data:`_UNKNOWN_SURFACE_SENTINEL`
    if absent). The renderer's section header is
    ``## Runtime reconciliation findings`` — distinct from the fixture
    gate's ``Fixture reconciliation failed`` template per AC-2's "distinct-
    shape diagnostics" commitment.

Loud-fail discipline (Pattern 5):
    Exit codes distinguish failure classes so CI logs are diagnosable.

        0 — full pass: every detected skip-event reconciled to an emitted
            marker; no findings of any class.
        1 — runtime reconciliation regression: at least one
            ``runtime_reconciliation_mismatch`` finding present AND
            ``schema_shape_broken`` / ``marker_taxonomy_mismatch`` empty.
            Recoverable by adding the missed marker emission OR by fixing
            the captured fixture if the skip-event was bogus.
        2 — capture-shape or taxonomy-mismatch error: at least one of
            ``schema_shape_broken`` / ``marker_taxonomy_mismatch`` non-
            empty (the captured fixture itself is malformed; OR a marker
            class was emitted that is not in
            ``schemas/marker-taxonomy.yaml``). Mixed-precedence: if BOTH
            shape/taxonomy AND reconciliation-mismatch findings are
            present, exit 2 (the higher-severity class — the capture
            corpus's own correctness is suspect).

Sensor-not-advisor (PRD-level invariant):
    The gate REPORTS per-capture reconciliation outcomes with remediation
    pointers; it does NOT auto-rewrite captures, suggest specific
    specialist code changes, or recommend marker-class renames. Same
    posture as 1.4 / 1.5 / 1.6 / 1.7 / 1.8.

Cross-component reuse posture (story 6.8 do-not-do enumeration):
    * :func:`loud_fail_harness.reconciler.reconcile` — REUSED for the
      reconciliation step; the reconciler API is FROZEN per story 1.4 +
      story 1.8 AC-4.
    * :class:`loud_fail_harness.reconciler.SkipEvent` /
      :class:`~loud_fail_harness.reconciler.Marker` /
      :class:`~loud_fail_harness.reconciler.ClassificationResult` —
      REUSED.
    * :func:`loud_fail_harness.reconciler.load_marker_taxonomy` — REUSED.
    * :func:`loud_fail_harness._shared.find_repo_root` /
      :func:`~loud_fail_harness._shared.load_schema` — REUSED for default-
      path resolution and schema loading.
    * :mod:`loud_fail_harness.fr33_fixture_gate` — UNCHANGED. The runtime
      gate is a sibling module; story 6.8 AC-1 + Story 1.8 AC-4 forbid
      modifying the fixture gate.

Determinism (parallel to story 1.8's AC-2/AC-6 + story 6.8 AC-1):
    All output lists sorted by ``(file_path, marker_class)``.
    :class:`RuntimeGateResult` is a Pydantic v2 frozen model with field-
    declaration-order JSON serialization (load-bearing for byte-stable
    ``model_dump_json()``).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections.abc import Sequence
from typing import Final, Literal, Optional

import yaml
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict

from loud_fail_harness._shared import find_repo_root, load_schema
from loud_fail_harness.reconciler import (
    Marker,
    SkipEvent,
    load_marker_taxonomy,
    reconcile,
)

#: Source string carried in synthesized SkipEvent + Marker objects per the
#: Pattern 5 named-invariant convention. Distinguishes runtime-gate provenance
#: from :data:`fr33_fixture_gate._FIXTURE_REPLAY_SOURCE` (story 1.8) so a
#: future composite-classification consumer can disambiguate by ``source``
#: without parsing the per-finding diagnostic.
RuntimeReplaySource: Final[str] = "orchestrator-event-log-runtime"

#: Canonical four common required fields on every orchestrator-event entry per
#: ``schemas/orchestrator-event.yaml`` lines 80-111. The runtime gate validates
#: SHAPE via this minimal contract rather than strict per-class schema
#: validation (which would loud-fail on every ``marker_class``-bearing skip-
#: event entry per the canonical schema's ``additionalProperties: false``
#: constraint). Promotion of ``marker_class`` and ``emission_site`` to
#: canonical schema fields is a Phase 2 thickening per story 6.8 Dev Notes
#: "Non-trivial design decisions" #2.
_COMMON_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "event_class",
    "event_id",
    "timestamp",
    "story_id",
)

#: Sentinel returned by :func:`_extract_emission_site` when the captured
#: event-log entry lacks an ``emission_site`` field. Surfaced in the AC-2
#: verbatim diagnostic's ``<surface>`` placeholder with a documented
#: annotation pointing at the architecture H3 § Runtime gate input contract.
_UNKNOWN_SURFACE_SENTINEL: Final[str] = "<unknown-surface>"

#: Annotation appended to the AC-2 diagnostic when ``emission_site`` is
#: absent. Documents the Phase 2 promotion path for contributors per story
#: 6.8 Dev Notes "Non-trivial design decisions" #2.
_UNKNOWN_SURFACE_ANNOTATION: Final[str] = (
    " (no emission_site captured — see "
    "`docs/architecture.md` § Runtime gate input contract)"
)

#: AC-2 verbatim diagnostic template — epics.md line 2790. Two interpolation
#: placeholders: ``{skip_event_class}`` (kebab-case Pattern 2 marker-class
#: identifier from the missed skip-event) and ``{code_surface}`` (free-form
#: code-surface string from the captured event-log entry's ``emission_site``).
_AC_2_RECONCILIATION_MISMATCH_TEMPLATE: Final[str] = (
    "Runtime reconciliation failed: reference-project run produced "
    "skip-event class `{skip_event_class}` at code surface "
    "`{code_surface}` but no emitted marker reconciled. Inspect "
    "specialist or hook at `{code_surface}` for missing emission."
)

#: Schema-shape-broken remediation pointer per Pattern 5 / NFR-O5 named-
#: invariant convention. Mirrors story 1.8's ``_HARNESS_BUG_REMEDIATION``
#: shape but routes to capture-fixture authoring rather than gate-synthesis
#: logic.
_SCHEMA_SHAPE_BROKEN_REMEDIATION: Final[str] = (
    "(per AC-7 mixed-precedence rule: this is exit 2 — fix the captured "
    "events.jsonl entry's shape before debugging reconciliation findings; "
    "see `tests/fixtures/runtime-captures/README.md` for the canonical "
    "events.jsonl shape)"
)

#: Marker-taxonomy-mismatch remediation pointer per Pattern 5 / NFR-O5.
#: Mirrors story 1.8's ``_DANGLING_EVENT_CLASS_REMEDIATION`` shape.
_MARKER_TAXONOMY_MISMATCH_REMEDIATION: Final[str] = (
    "(per AC-7 mixed-precedence rule: this is exit 2 — either (a) the "
    "captured run-state's `active_markers` declares a marker class that is "
    "not in `schemas/marker-taxonomy.yaml` (taxonomy-side fix), OR (b) the "
    "captured fixture's `active_markers` is bogus and should be edited to "
    "use a canonical taxonomy entry; see "
    "`tests/fixtures/runtime-captures/README.md`)"
)

#: Reconciliation-mismatch remediation pointer per Pattern 5 / NFR-O5.
#: Mirrors story 1.8's ``_RECONCILIATION_MISMATCH_REMEDIATION`` shape.
_RUNTIME_RECONCILIATION_MISMATCH_REMEDIATION: Final[str] = (
    "(per AC-2; the captured reference-project run produced a skip-event "
    "class that no emitted marker reconciled — add the missing marker "
    "emission at the named code surface OR fix the capture if the skip-"
    "event was bogus)"
)

#: Three-category enum carried by :class:`RuntimeFinding`'s ``category``
#: field. Parallels story 1.8's ``ReplayFinding.category`` three-value
#: ``Literal`` per the NFR-O5 named-invariant diagnostic shape; the bucket
#: names are the runtime variant of the fixture gate's
#: (reconciliation-mismatch, harness-bug, dangling-event-class) trio.
RuntimeFindingCategory = Literal[
    "runtime-reconciliation-mismatch",
    "schema-shape-broken",
    "marker-taxonomy-mismatch",
]


class RuntimeReference(BaseModel):
    """A passing reconciliation reference (file_path + marker_class).

    Frozen for hashability + determinism; field declaration order is load-
    bearing for byte-stable JSON dumps. Mirrors the type from
    :class:`fr33_fixture_gate.Reference` by SHAPE; declared locally per the
    within-module-only-coupling discipline (do not import cross-module
    Pydantic models).
    """

    model_config = ConfigDict(frozen=True)

    file_path: str
    marker_class: str


class RuntimeFinding(BaseModel):
    """A single per-capture runtime-reconciliation-gate finding.

    NFR-O5 named-invariant diagnostic shape: every finding names

    * ``file_path``    — display path of the offending capture file
      (events.jsonl OR run-state.yaml — disambiguated by the rendered
      diagnostic). Relative to repo root via
      :func:`loud_fail_harness._shared.find_repo_root` when resolvable.
    * ``marker_class`` — the marker-class identifier the finding is bound
      to (or empty string when the finding is a per-entry shape failure
      with no marker context).
    * ``category``     — classification bucket the finding belongs to.
    * ``message``      — the AC-2 distinct-shape diagnostic prose
      verbatim (or the equivalent shape/taxonomy diagnostic).
    * ``remediation``  — one-line NFR-O5 pointer naming AC-1 / AC-2 / AC-3.

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable JSON dumps.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str
    marker_class: str
    category: RuntimeFindingCategory
    message: str
    remediation: str


class RuntimeGateResult(BaseModel):
    """Quad-classification runtime-reconciliation-gate output.

    * ``passing`` — capture entries whose skip-event reconciled cleanly to
      an emitted marker. One :class:`RuntimeReference` per matched
      ``(skip_event, marker)`` pair; sorted by ``(file_path, marker_class)``.
    * ``runtime_reconciliation_mismatch`` — captures whose detected skip-
      events did not reconcile to emitted markers. FAIL exit 1.
    * ``schema_shape_broken`` — captures with malformed events.jsonl
      entries (missing the four common required fields, malformed JSON,
      etc.). FAIL exit 2 (mixed-precedence: highest severity).
    * ``marker_taxonomy_mismatch`` — captures whose run-state
      ``active_markers`` declares a marker class not in
      ``schemas/marker-taxonomy.yaml``. FAIL exit 2 (mixed-precedence:
      tied with schema-shape-broken).

    Field declaration order matches Pydantic v2's JSON-serialization order
    (load-bearing for byte-stable dumps; parallel to 1.4 / 1.5 / 1.6 / 1.7
    / 1.8).
    """

    model_config = ConfigDict(frozen=True)

    passing: list[RuntimeReference]
    runtime_reconciliation_mismatch: list[RuntimeFinding]
    schema_shape_broken: list[RuntimeFinding]
    marker_taxonomy_mismatch: list[RuntimeFinding]


def _split_marker_base_class(active_marker: str) -> str:
    """Strip the optional ``: <sub-classification>`` Pattern 2 suffix.

    Per story 6.8 Dev Notes "Non-trivial design decisions" #3, the matching
    key in :func:`reconcile` is base-class only — sub-classifications are
    diagnostic granularity, not reconciliation-key-bearing.
    """
    if ": " in active_marker:
        return active_marker.split(": ", 1)[0]
    return active_marker


def _extract_emission_site(event: dict) -> tuple[str, bool]:
    """Pull the optional ``emission_site`` field from a captured event entry.

    Returns ``(emission_site, captured)`` where ``captured`` is ``True``
    when the field was present and a non-empty string. The fallback
    sentinel :data:`_UNKNOWN_SURFACE_SENTINEL` surfaces in the AC-2
    diagnostic with the documented annotation.
    """
    raw = event.get("emission_site")
    if isinstance(raw, str) and raw:
        return raw, True
    return _UNKNOWN_SURFACE_SENTINEL, False


def _has_common_shape(event: dict) -> Optional[str]:
    """Return ``None`` if ``event`` has the four common required fields;
    otherwise return a single-line diagnostic naming the missing field(s).
    """
    if not isinstance(event, dict):
        return f"entry is not a JSON object (got {type(event).__name__})"
    missing: list[str] = []
    for field in _COMMON_REQUIRED_FIELDS:
        value = event.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(field)
    if missing:
        return "missing or empty required field(s): " + ", ".join(missing)
    return None


def _parse_events_jsonl(
    events_path: pathlib.Path,
) -> tuple[list[dict], list[tuple[int, str]]]:
    """Parse ``events.jsonl`` line-by-line.

    Returns ``(parsed_entries, parse_failures)`` where ``parse_failures`` is
    a list of ``(line_number, error_message)`` for malformed JSON lines.
    Blank lines are silently skipped per JSON Lines convention.
    """
    parsed: list[dict] = []
    failures: list[tuple[int, str]] = []
    text = events_path.read_text(encoding="utf-8")
    for idx, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            failures.append((idx, f"JSON decode error: {exc}"))
            continue
        if not isinstance(entry, dict):
            failures.append((idx, f"line is not a JSON object: {entry!r}"))
            continue
        parsed.append(entry)
    return parsed, failures


def extract_runtime_skip_events(
    events: list[dict],
    *,
    event_schema: dict,
    file_path: str,
) -> tuple[list[SkipEvent], list[RuntimeFinding], dict[tuple[str, str], str]]:
    """Iterate captured event-log entries; surface skip-events + findings.

    Algorithm per story 6.8 surface enumeration item (iv):

    1. For each entry: validate the four common required fields per
       :func:`_has_common_shape`. Entries failing this MINIMAL shape check
       are routed to ``schema_shape_broken`` findings (NOT to silent_skips
       — schema breakage is a distinct surface per story 6.8 (iv)).
    2. Entries with no ``marker_class`` field are non-skip events
       (state-transition / specialist-dispatched / etc.) and are filtered
       OUT of the reconciler input.
    3. Entries WITH a non-empty string ``marker_class`` field construct a
       :class:`SkipEvent` carrying ``marker_class`` (Pattern 2 base-class
       string), ``story_id`` (from the entry), and ``source``
       :data:`RuntimeReplaySource`. The optional ``emission_site`` field
       is captured into the returned ``emission_sites`` map keyed by
       ``(marker_class, story_id)`` for later AC-2 diagnostic
       interpolation.

    The ``event_schema`` argument is unused inside this function at MVP;
    it is accepted for symmetry with story 1.8's contract and for future
    Phase-2 promotion of ``marker_class`` / ``emission_site`` to canonical
    fields without changing the public surface (see module docstring).
    """
    del event_schema  # see docstring; reserved for Phase 2 thickening

    skip_events: list[SkipEvent] = []
    findings: list[RuntimeFinding] = []
    emission_sites: dict[tuple[str, str], str] = {}

    for idx, entry in enumerate(events, start=1):
        shape_error = _has_common_shape(entry)
        if shape_error is not None:
            message = (
                f"Capture events.jsonl entry {idx} is shape-broken: "
                f"{shape_error}. Inspect the captured events.jsonl per "
                f"`tests/fixtures/runtime-captures/README.md`."
            )
            findings.append(
                RuntimeFinding(
                    file_path=file_path,
                    marker_class="",
                    category="schema-shape-broken",
                    message=message,
                    remediation=_SCHEMA_SHAPE_BROKEN_REMEDIATION,
                )
            )
            continue

        marker_class_raw = entry.get("marker_class")
        if not isinstance(marker_class_raw, str) or not marker_class_raw:
            # Non-skip event — filter out per story 6.8 surface (iv).
            continue

        story_id = entry["story_id"]
        marker_base_class = _split_marker_base_class(marker_class_raw)
        if not marker_base_class:
            findings.append(
                RuntimeFinding(
                    file_path=file_path,
                    marker_class="",
                    category="schema-shape-broken",
                    message=(
                        f"Capture events.jsonl entry {idx} has a `marker_class` "
                        f"value {marker_class_raw!r} whose Pattern 2 base-class "
                        "parsed to an empty string (leading ': ' prefix). "
                        "Inspect the captured events.jsonl per "
                        "`tests/fixtures/runtime-captures/README.md`."
                    ),
                    remediation=_SCHEMA_SHAPE_BROKEN_REMEDIATION,
                )
            )
            continue
        skip_events.append(
            SkipEvent(
                marker_class=marker_base_class,
                story_id=story_id,
                source=RuntimeReplaySource,
            )
        )
        site, _ = _extract_emission_site(entry)
        if (marker_base_class, story_id) not in emission_sites:
            emission_sites[(marker_base_class, story_id)] = site

    return skip_events, findings, emission_sites


def extract_runtime_markers(
    active_markers: tuple[str, ...] | Sequence[str],
    *,
    story_id: str,
    taxonomy: set[str],
    file_path: str,
) -> tuple[list[Marker], list[RuntimeFinding]]:
    """Construct :class:`Marker` instances from a captured run's
    ``active_markers`` tuple.

    Algorithm per story 6.8 surface enumeration item (v):

    1. For each entry: parse Pattern 2's ``<base-class>: <sub-
       classification>`` shape via :func:`_split_marker_base_class`. The
       matching key in :func:`reconcile` is base-class only per
       :func:`reconciler._matches`.
    2. Markers whose base-class is NOT in the loaded taxonomy surface as
       ``marker-taxonomy-mismatch`` findings (loud-fail per NFR-O5).
    3. Markers whose base-class IS in the taxonomy construct a
       :class:`Marker` carrying the BASE class only, the supplied
       ``story_id``, and ``source`` :data:`RuntimeReplaySource`.
    """
    markers: list[Marker] = []
    findings: list[RuntimeFinding] = []

    for entry in active_markers:
        if not isinstance(entry, str) or not entry:
            findings.append(
                RuntimeFinding(
                    file_path=file_path,
                    marker_class="",
                    category="schema-shape-broken",
                    message=(
                        "Capture run-state.yaml `active_markers` carries a "
                        "non-string or empty entry; expected kebab-case "
                        "Pattern 2 marker-class identifier."
                    ),
                    remediation=_SCHEMA_SHAPE_BROKEN_REMEDIATION,
                )
            )
            continue

        base_class = _split_marker_base_class(entry)
        if base_class not in taxonomy:
            findings.append(
                RuntimeFinding(
                    file_path=file_path,
                    marker_class=base_class,
                    category="marker-taxonomy-mismatch",
                    message=(
                        f"Capture run-state.yaml `active_markers` declares "
                        f"marker class `{base_class}` (parsed from `{entry}`) "
                        f"which is not in `schemas/marker-taxonomy.yaml`."
                    ),
                    remediation=_MARKER_TAXONOMY_MISMATCH_REMEDIATION,
                )
            )
            continue

        markers.append(
            Marker(
                marker_class=base_class,
                story_id=story_id,
                source=RuntimeReplaySource,
            )
        )

    return markers, findings


def replay_runtime_capture(
    events_path: pathlib.Path,
    run_state_path: pathlib.Path,
    taxonomy: set[str],
    event_schema: dict,
) -> RuntimeGateResult:
    """Replay ONE capture directory (events.jsonl + run-state.yaml) through
    the SHARED reconciliation invariant.

    Algorithm per story 6.8 surface enumeration item (vi):

    1. Read + parse ``events.jsonl`` line-by-line; JSON-decode failures
       route to ``schema_shape_broken`` findings.
    2. Read + parse ``run-state.yaml``; structural failures (not a YAML
       mapping; missing ``active_markers`` field) raise
       :class:`RuntimeError` (loud-fail per Pattern 5 / NFR-O5; the gate's
       caller catches this at the top level).
    3. Extract skip-events via :func:`extract_runtime_skip_events`.
    4. Extract markers via :func:`extract_runtime_markers`.
    5. Call the SHARED :func:`reconciler.reconcile` WITHOUT modification
       per story 6.8 AC-1 + story 1.8 AC-4.
    6. Partition ``ClassificationResult.silent_skips`` into
       ``runtime_reconciliation_mismatch`` findings using the AC-2 verbatim
       template; ``ClassificationResult.matched`` populates ``passing``.
       ``ClassificationResult.orphan_markers`` are NOT routed to a finding
       category at MVP per story 6.8 Dev Notes "Non-trivial design
       decisions" #1 (Phase 2 thickening tracked in ``deferred-work.md``).

    Pure (modulo argument-supplied disk reads via the path arguments).
    """
    events, parse_failures = _parse_events_jsonl(events_path)
    file_path = str(events_path)
    run_state_file_path = str(run_state_path)

    schema_shape_broken: list[RuntimeFinding] = []
    for line_no, error_msg in parse_failures:
        message = (
            f"Capture events.jsonl line {line_no} is shape-broken: "
            f"{error_msg}. Inspect the captured events.jsonl per "
            f"`tests/fixtures/runtime-captures/README.md`."
        )
        schema_shape_broken.append(
            RuntimeFinding(
                file_path=file_path,
                marker_class="",
                category="schema-shape-broken",
                message=message,
                remediation=_SCHEMA_SHAPE_BROKEN_REMEDIATION,
            )
        )

    run_state_raw = yaml.safe_load(run_state_path.read_text(encoding="utf-8"))
    if not isinstance(run_state_raw, dict):
        raise RuntimeError(
            f"capture run-state malformed: {run_state_path}: "
            "expected top-level YAML mapping"
        )
    story_id_raw = run_state_raw.get("story_id")
    if not isinstance(story_id_raw, str) or not story_id_raw:
        raise RuntimeError(
            f"capture run-state malformed: {run_state_path}: "
            "missing or empty `story_id` field"
        )
    active_markers_raw = run_state_raw.get("active_markers", [])
    if not isinstance(active_markers_raw, list):
        raise RuntimeError(
            f"capture run-state malformed: {run_state_path}: "
            "`active_markers` must be a list"
        )

    skip_events, skip_findings, emission_sites = extract_runtime_skip_events(
        events, event_schema=event_schema, file_path=file_path
    )
    schema_shape_broken.extend(skip_findings)

    # Cross-source story_id consistency check (D2 review finding): if
    # events.jsonl entries carry a different story_id than run-state.yaml,
    # the reconciler's (marker_class, story_id) matching key won't align and
    # every skip-event becomes a spurious silent_skip.  Surface a named
    # diagnostic so contributors don't have to re-derive the mismatch.
    mismatched_story_ids = {
        se.story_id for se in skip_events if se.story_id != story_id_raw
    }
    if mismatched_story_ids:
        _sorted_ids = sorted(sid for sid in mismatched_story_ids if sid is not None)
        schema_shape_broken.append(
            RuntimeFinding(
                file_path=file_path,
                marker_class="",
                category="schema-shape-broken",
                message=(
                    "Capture story_id mismatch: events.jsonl entries carry "
                    f"story_id(s) {_sorted_ids!r} but "
                    f"run-state.yaml reports story_id {story_id_raw!r}. "
                    "The reconciler matches on (marker_class, story_id); "
                    "mismatched story_ids produce spurious "
                    "runtime-reconciliation-mismatch findings. Ensure both "
                    "files originate from the same captured run."
                ),
                remediation=_SCHEMA_SHAPE_BROKEN_REMEDIATION,
            )
        )

    markers, marker_findings = extract_runtime_markers(
        tuple(active_markers_raw),
        story_id=story_id_raw,
        taxonomy=taxonomy,
        file_path=run_state_file_path,
    )
    marker_taxonomy_mismatch: list[RuntimeFinding] = []
    for finding in marker_findings:
        if finding.category == "schema-shape-broken":
            schema_shape_broken.append(finding)
        else:
            marker_taxonomy_mismatch.append(finding)

    result = reconcile(skip_events, markers)

    passing: list[RuntimeReference] = []
    for matched_pair in result.matched:
        passing.append(
            RuntimeReference(
                file_path=file_path,
                marker_class=matched_pair.marker.marker_class,
            )
        )

    runtime_reconciliation_mismatch: list[RuntimeFinding] = []
    for skip in result.silent_skips:
        site = emission_sites.get(
            (skip.marker_class, skip.story_id or ""),
            _UNKNOWN_SURFACE_SENTINEL,
        )
        annotation = ""
        if site == _UNKNOWN_SURFACE_SENTINEL:
            annotation = _UNKNOWN_SURFACE_ANNOTATION
        message = (
            _AC_2_RECONCILIATION_MISMATCH_TEMPLATE.format(
                skip_event_class=skip.marker_class,
                code_surface=site,
            )
            + annotation
        )
        runtime_reconciliation_mismatch.append(
            RuntimeFinding(
                file_path=file_path,
                marker_class=skip.marker_class,
                category="runtime-reconciliation-mismatch",
                message=message,
                remediation=_RUNTIME_RECONCILIATION_MISMATCH_REMEDIATION,
            )
        )

    return RuntimeGateResult(
        passing=passing,
        runtime_reconciliation_mismatch=runtime_reconciliation_mismatch,
        schema_shape_broken=schema_shape_broken,
        marker_taxonomy_mismatch=marker_taxonomy_mismatch,
    )


def run_fr33_runtime_gate(
    captures: list[pathlib.Path],
    taxonomy: set[str],
    event_schema: dict,
    *,
    captures_root: pathlib.Path,
) -> RuntimeGateResult:
    """Replay every capture; partition results into the four buckets.

    Each capture path must be a directory containing ``events.jsonl`` AND
    ``run-state.yaml``. Captures missing either file route to a single
    ``schema_shape_broken`` finding (NFR-O5 named-invariant diagnostic per
    Pattern 5).

    Sorted-output discipline (parallel to story 1.8's
    ``(file_path, marker_class)`` lex-sort precedent): ``passing`` and the
    three finding lists are sorted by ``(file_path, marker_class)``.
    """
    del captures_root  # accepted for symmetry with fr33_fixture_gate's API

    passing: list[RuntimeReference] = []
    runtime_reconciliation_mismatch: list[RuntimeFinding] = []
    schema_shape_broken: list[RuntimeFinding] = []
    marker_taxonomy_mismatch: list[RuntimeFinding] = []

    for capture in captures:
        events_path = capture / "events.jsonl"
        run_state_path = capture / "run-state.yaml"
        missing: list[str] = []
        if not events_path.is_file():
            missing.append("events.jsonl")
        if not run_state_path.is_file():
            missing.append("run-state.yaml")
        if missing:
            schema_shape_broken.append(
                RuntimeFinding(
                    file_path=str(capture),
                    marker_class="",
                    category="schema-shape-broken",
                    message=(
                        f"Capture directory `{capture}` is missing "
                        f"required file(s): {', '.join(missing)}. Each "
                        f"capture must contain BOTH events.jsonl AND "
                        f"run-state.yaml per `tests/fixtures/runtime-"
                        f"captures/README.md`."
                    ),
                    remediation=_SCHEMA_SHAPE_BROKEN_REMEDIATION,
                )
            )
            continue

        try:
            result = replay_runtime_capture(
                events_path, run_state_path, taxonomy, event_schema
            )
        except (RuntimeError, OSError, ValueError, yaml.YAMLError) as exc:
            schema_shape_broken.append(
                RuntimeFinding(
                    file_path=str(capture),
                    marker_class="",
                    category="schema-shape-broken",
                    message=(
                        f"Capture directory `{capture}` failed to replay: "
                        f"{exc}."
                    ),
                    remediation=_SCHEMA_SHAPE_BROKEN_REMEDIATION,
                )
            )
            continue

        passing.extend(result.passing)
        runtime_reconciliation_mismatch.extend(
            result.runtime_reconciliation_mismatch
        )
        schema_shape_broken.extend(result.schema_shape_broken)
        marker_taxonomy_mismatch.extend(result.marker_taxonomy_mismatch)

    def _ref_key(r: RuntimeReference) -> tuple[str, str]:
        return (r.file_path, r.marker_class)

    def _finding_key(f: RuntimeFinding) -> tuple[str, str]:
        return (f.file_path, f.marker_class)

    passing.sort(key=_ref_key)
    runtime_reconciliation_mismatch.sort(key=_finding_key)
    schema_shape_broken.sort(key=_finding_key)
    marker_taxonomy_mismatch.sort(key=_finding_key)

    return RuntimeGateResult(
        passing=passing,
        runtime_reconciliation_mismatch=runtime_reconciliation_mismatch,
        schema_shape_broken=schema_shape_broken,
        marker_taxonomy_mismatch=marker_taxonomy_mismatch,
    )


def format_findings(
    result: RuntimeGateResult,
    *,
    captures_root: str,
    taxonomy_path: str,
) -> str:
    """Render a :class:`RuntimeGateResult` for stdout.

    Header naming inputs; passing-summary line; per-bucket finding lists
    with the AC-2 distinct-shape diagnostics; footer Summary line. Mirrors
    story 1.8's :func:`fr33_fixture_gate.format_findings` posture but uses
    the NEW ``## Runtime reconciliation findings`` section header per AC-2's
    "distinct-shape diagnostics" commitment — debuggers grep for this header
    to identify which gate fired without re-deriving from the marker-class
    string (Story 1.11's flat-routing principle).
    """
    lines: list[str] = []
    lines.append("FR33 runtime reconciliation gate (story 6.8)")
    lines.append(f"  captures root:   {captures_root}")
    lines.append(f"  taxonomy:        {taxonomy_path}")
    lines.append("")

    has_findings = bool(
        result.runtime_reconciliation_mismatch
        or result.schema_shape_broken
        or result.marker_taxonomy_mismatch
    )
    passing_line = (
        f"OK: {len(result.passing)} passing capture entry(s) reconciled "
        f"cleanly"
    )
    if has_findings:
        passing_line += " (but findings below)"
    lines.append(passing_line + ".")

    if has_findings:
        lines.append("")
        lines.append("## Runtime reconciliation findings")

    if result.runtime_reconciliation_mismatch:
        lines.append("")
        lines.append(
            f"FAIL: {len(result.runtime_reconciliation_mismatch)} "
            "runtime-reconciliation-mismatch finding(s)."
        )
        for f in result.runtime_reconciliation_mismatch:
            lines.append(f"  - {f.message} {f.remediation}")

    if result.schema_shape_broken:
        lines.append("")
        lines.append(
            f"FAIL: {len(result.schema_shape_broken)} "
            "schema-shape-broken finding(s)."
        )
        for f in result.schema_shape_broken:
            lines.append(f"  - {f.message} {f.remediation}")

    if result.marker_taxonomy_mismatch:
        lines.append("")
        lines.append(
            f"FAIL: {len(result.marker_taxonomy_mismatch)} "
            "marker-taxonomy-mismatch finding(s)."
        )
        for f in result.marker_taxonomy_mismatch:
            lines.append(f"  - {f.message} {f.remediation}")

    lines.append("")
    lines.append(
        f"Summary: {len(result.passing)} passing capture entry(s), "
        f"{len(result.runtime_reconciliation_mismatch)} "
        "runtime-reconciliation-mismatch finding(s), "
        f"{len(result.schema_shape_broken)} schema-shape-broken finding(s), "
        f"{len(result.marker_taxonomy_mismatch)} "
        "marker-taxonomy-mismatch finding(s)."
    )
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fr33-runtime-gate",
        description=(
            "FR33 runtime reconciliation CI gate. Replays each captured "
            "reference-project run (events.jsonl + run-state.yaml) through "
            "reconciler.py and asserts every detected skip-event reconciles "
            "to an emitted marker. Story 6.8; ADR-003 + FR33."
        ),
    )
    parser.add_argument(
        "captures",
        nargs="*",
        type=pathlib.Path,
        default=None,
        help=(
            "Capture directory paths (each containing events.jsonl + "
            "run-state.yaml). Defaults to globbing "
            "tests/fixtures/runtime-captures/*/ relative to repo root."
        ),
    )
    parser.add_argument(
        "--taxonomy-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to marker-taxonomy.yaml (default: "
            "<repo-root>/schemas/marker-taxonomy.yaml). Test-injection "
            "flag; CI invocations omit it."
        ),
    )
    parser.add_argument(
        "--event-schema",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to orchestrator-event.yaml (default: "
            "<repo-root>/schemas/orchestrator-event.yaml). Accepted for "
            "symmetry with fr33-fixture-gate; consulted only for forward-"
            "compat shape checks at MVP. Test-injection flag."
        ),
    )
    parser.add_argument(
        "--captures-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Override default-glob root (default: "
            "<harness-root>/tests/fixtures/runtime-captures/ resolved from "
            "the harness install). Test-injection flag; CI invocations "
            "omit it."
        ),
    )
    return parser


def _display_path(
    path: pathlib.Path, repo_root: Optional[pathlib.Path] = None
) -> str:
    """Render ``path`` relative to repo root if possible; absolute otherwise.

    Mirrors :func:`fr33_fixture_gate._display_path`'s posture.
    """
    try:
        rr = repo_root if repo_root is not None else find_repo_root()
        return str(path.resolve().relative_to(rr.resolve()))
    except (RuntimeError, ValueError):
        return str(path.resolve())


def _resolve_default_captures_root(repo_root: pathlib.Path) -> pathlib.Path:
    """Resolve the default capture-fixtures root.

    The fixtures live at
    ``<repo-root>/tools/loud-fail-harness/tests/fixtures/runtime-captures/``;
    the gate is canonically invoked from
    ``<repo-root>/tools/loud-fail-harness/`` per ``.github/workflows/ci.yml``.
    """
    return (
        repo_root
        / "tools"
        / "loud-fail-harness"
        / "tests"
        / "fixtures"
        / "runtime-captures"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    taxonomy_path: pathlib.Path
    event_schema_path: pathlib.Path
    captures_root: pathlib.Path
    repo_root: Optional[pathlib.Path] = None

    if (
        args.taxonomy_path is None
        or args.event_schema is None
        or args.captures_root is None
    ):
        try:
            repo_root = find_repo_root()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        taxonomy_path = (
            args.taxonomy_path or repo_root / "schemas" / "marker-taxonomy.yaml"
        )
        event_schema_path = (
            args.event_schema or repo_root / "schemas" / "orchestrator-event.yaml"
        )
        captures_root = (
            args.captures_root or _resolve_default_captures_root(repo_root)
        )
    else:
        taxonomy_path = args.taxonomy_path
        event_schema_path = args.event_schema
        captures_root = args.captures_root

    captures: list[pathlib.Path]
    if args.captures:
        captures = list(args.captures)
    else:
        if not captures_root.is_dir():
            print(
                f"harness-level error: runtime-captures root unreadable: "
                f"{captures_root}",
                file=sys.stderr,
            )
            return 2
        captures = sorted(
            p for p in captures_root.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )

    if not captures:
        print(
            "harness-level error: runtime-captures corpus is empty — no "
            "capture directories found. Add at least one capture directory "
            f"containing events.jsonl + run-state.yaml under {captures_root}.",
            file=sys.stderr,
        )
        return 2

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

    result = run_fr33_runtime_gate(
        captures, taxonomy, event_schema, captures_root=captures_root
    )
    print(
        format_findings(
            result,
            captures_root=_display_path(captures_root, repo_root=repo_root),
            taxonomy_path=_display_path(taxonomy_path, repo_root=repo_root),
        )
    )

    # Mixed-precedence rule: schema-shape-broken / taxonomy-mismatch wins;
    # exit 2. Otherwise reconciliation-mismatch → exit 1; clean → exit 0.
    if result.schema_shape_broken or result.marker_taxonomy_mismatch:
        return 2
    if result.runtime_reconciliation_mismatch:
        return 1
    return 0


__all__ = [
    "RuntimeFinding",
    "RuntimeFindingCategory",
    "RuntimeGateResult",
    "RuntimeReference",
    "RuntimeReplaySource",
    "extract_runtime_markers",
    "extract_runtime_skip_events",
    "format_findings",
    "main",
    "replay_runtime_capture",
    "run_fr33_runtime_gate",
]
