"""Story 19.4 — A11y audit delta engine + Pattern-5 emission helpers.

The pure-library substrate owning the accessibility-audit primitives the QA
specialist composes on the web opt-in path (FR-P2-6 / ADR-011): axe-core
result parsing, ``(rule-id, target-selector)`` violation-key normalization,
per-AC baseline load/store, the self-computed set-difference delta (axe-core
ships NO native baseline-delta — the load-bearing ADR-011 finding), the
configurable-threshold compare, the non-deterministic-delta detection, and the
three ``a11y-*`` marker emission helpers.

This is the RUNTIME half of the 19.3<->19.4 "activate-then-integrate" seam
(mirroring 9.1->9.3 mobile and 10.1->10.4 LAD). Story 19.3 froze the tool
(axe-core, ``version_floor "4.12"``), the ``dependencies.yaml`` entry, and the
three marker classes (``a11y-baseline-stale`` / ``a11y-delta-exceeded`` /
``a11y-delta-mode-unstable``; marker-taxonomy ``1.14``). THIS module consumes
those classes AS-IS via :func:`validate_marker_emission` and wires emission.

Pattern 5 (atomic-on-failure) at the three ``surface_a11y_*`` helpers mirrors
:func:`qa_exploratory_heuristics.surface_heuristic_skipped` byte-for-byte: the
runtime registry is validated FIRST; on rejection :exc:`UnknownMarkerClass`
propagates with NO partial state constructed.

Sensor-not-advisor: a fired ``a11y-*`` marker SURFACES regression evidence for
the human; it does NOT flip an AC's pass/fail verdict (the a11y delta is
story-level evidence, exactly as exploratory-heuristic findings are). Flow
policy lives in the orchestrator, never here.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loud_fail_harness.input_hardening import harden_identifier, harden_path_segment
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

# --------------------------------------------------------------------------- #
# Symbolic constants                                                          #
# --------------------------------------------------------------------------- #

#: The three canonical a11y marker class identifiers, consumed AS-IS from
#: ``schemas/marker-taxonomy.yaml`` (Story 19.3 enumeration; ``1.14``). THIS
#: module is the FIRST runtime emitter. Mirrors the
#: :data:`qa_exploratory_heuristics.HEURISTIC_SKIPPED_MARKER` constant pattern.
A11Y_BASELINE_STALE_MARKER: Final[Literal["a11y-baseline-stale"]] = "a11y-baseline-stale"
A11Y_DELTA_EXCEEDED_MARKER: Final[Literal["a11y-delta-exceeded"]] = "a11y-delta-exceeded"
A11Y_DELTA_MODE_UNSTABLE_MARKER: Final[Literal["a11y-delta-mode-unstable"]] = (
    "a11y-delta-mode-unstable"
)

#: The per-AC baseline-storage root 19.3 forward-pointed (gitignored,
#: practitioner-local longitudinal signal; the qa-evidence precedent). Baselines
#: live under ``_bmad-output/qa-a11y-baseline/{story-id}/{ac-id}/baseline.json``.
A11Y_BASELINE_ROOT: Final[str] = "_bmad-output/qa-a11y-baseline"
BASELINE_FILENAME: Final[str] = "baseline.json"

#: The default a11y delta threshold (``qa-runbook.a11y.delta_threshold``). ``0``
#: means "any newly-introduced violation key beyond the baseline is a
#: regression" — the strictest, most defensible default for the opt-in posture.
DEFAULT_DELTA_THRESHOLD: Final[int] = 0

#: The closed set of audit modes :func:`decide_a11y_mode` resolves. Three map to
#: a marker emission; ``delta-within-threshold`` is the silent within-budget arm.
A11yAuditMode = Literal[
    "baseline-stale",
    "delta-exceeded",
    "delta-within-threshold",
    "delta-mode-unstable",
]

# --------------------------------------------------------------------------- #
# Externally-constructed parse model (axe.run() JSON ingress)                 #
# --------------------------------------------------------------------------- #


class AxeViolationKey(BaseModel):
    """One normalized axe-core violation key — the ``(rule-id, target-selector)``
    pair the self-computed delta diffs on.

    Constructed from the browser-supplied ``axe.run()`` JSON (therefore
    ``externally_constructed`` per the Story 24.2 input-hardening registry): the
    ``rule_id`` is ``violations[i].id`` and the ``target_selector`` is the
    canonicalized ``violations[i].nodes[j].target`` (the array-of-strings iframe
    path / array-of-arrays shadow-DOM shapes flattened to a stable string by
    :func:`_canonicalize_target`).

    Frozen for hashability + determinism — instances populate the
    ``frozenset`` the set-difference delta operates on. Field declaration order
    is load-bearing for byte-stable ``model_dump_json()`` / baseline-JSON output.
    """

    model_config = ConfigDict(frozen=True)

    rule_id: str = Field(min_length=1)
    target_selector: str = Field(min_length=1)

    @model_validator(mode="after")
    def _harden_external_inputs(self) -> "AxeViolationKey":
        harden_identifier(self.rule_id, "AxeViolationKey.rule_id")
        harden_identifier(self.target_selector, "AxeViolationKey.target_selector")
        return self


# --------------------------------------------------------------------------- #
# Pure computation result carriers (NamedTuple — not BaseModel, no I/O)       #
# --------------------------------------------------------------------------- #


class NormalizedViolations(NamedTuple):
    """The result of :func:`normalize_violation_keys`.

    ``keys`` is the stable set of violation keys; ``stable`` is ``False`` when
    any violation could not be canonicalized to a stable key (the AC-5
    non-deterministic-delta trigger — e.g. a malformed / empty ``target``).
    """

    keys: frozenset[AxeViolationKey]
    stable: bool


class A11yDelta(NamedTuple):
    """The result of :func:`compute_delta`: the newly-introduced violation keys
    (current minus baseline) and whether their count exceeds the threshold."""

    new_keys: frozenset[AxeViolationKey]
    exceeded: bool


class A11yAuditDecision(NamedTuple):
    """The result of :func:`decide_a11y_mode`: which audit arm fired plus the
    new violation keys (empty for the baseline-stale / unstable arms)."""

    mode: A11yAuditMode
    new_keys: frozenset[AxeViolationKey]


# --------------------------------------------------------------------------- #
# Diagnostic contexts (co-exposed on the emissions; externally_constructed)   #
# --------------------------------------------------------------------------- #


class A11yAcScopedDiagnosticContext(BaseModel):
    """The diagnostic context co-exposed on the two AC-scoped a11y emissions
    (``a11y-baseline-stale`` / ``a11y-delta-exceeded``).

    Mirrors :class:`qa_exploratory_heuristics.HeuristicSkippedDiagnosticContext`:
    frozen for hashability + determinism; field order load-bearing for byte-stable
    ``model_dump_json()``. ``story_id`` is the raw external-ingress identifier;
    ``ac_id`` is supplied by the wrapper from the dispatch ``ac_list`` — both are
    hardened defensively.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    ac_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> "A11yAcScopedDiagnosticContext":
        harden_identifier(self.story_id, "A11yAcScopedDiagnosticContext.story_id")
        harden_identifier(self.ac_id, "A11yAcScopedDiagnosticContext.ac_id")
        return self


class A11yRunScopedDiagnosticContext(BaseModel):
    """The diagnostic context co-exposed on the envelope-scoped
    ``a11y-delta-mode-unstable`` emission (``pointer_context_fields: []`` per
    19.3 — no ``ac_id``; the unstable-delta fallback is run-scoped, not AC-scoped).
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> "A11yRunScopedDiagnosticContext":
        harden_identifier(self.story_id, "A11yRunScopedDiagnosticContext.story_id")
        return self


# --------------------------------------------------------------------------- #
# Emission records (the envelope-bound `a11y_emissions[]` item shape)         #
# --------------------------------------------------------------------------- #


class A11yBaselineStaleEmissionRecord(BaseModel):
    """One ``a11y-baseline-stale`` emission record. Byte-mirrors the envelope
    ``$defs/a11y_emission`` AC-scoped shape (``marker_class`` + ``ac_id``).

    Frozen + field-order-load-bearing for byte-stable ``model_dump_json()``.
    """

    model_config = ConfigDict(frozen=True)

    marker_class: Literal["a11y-baseline-stale"]
    ac_id: str = Field(min_length=1)


class A11yDeltaExceededEmissionRecord(BaseModel):
    """One ``a11y-delta-exceeded`` emission record. Byte-mirrors the envelope
    ``$defs/a11y_emission`` AC-scoped shape (``marker_class`` + ``ac_id``)."""

    model_config = ConfigDict(frozen=True)

    marker_class: Literal["a11y-delta-exceeded"]
    ac_id: str = Field(min_length=1)


class A11yDeltaModeUnstableEmissionRecord(BaseModel):
    """One ``a11y-delta-mode-unstable`` emission record. Byte-mirrors the
    envelope ``$defs/a11y_emission`` envelope-scoped shape (``marker_class``
    only — no ``ac_id`` per ``pointer_context_fields: []``)."""

    model_config = ConfigDict(frozen=True)

    marker_class: Literal["a11y-delta-mode-unstable"]


# --------------------------------------------------------------------------- #
# Emission wrappers (atomic-emission return shape; co-expose the context)     #
# --------------------------------------------------------------------------- #


class A11yBaselineStaleEmission(BaseModel):
    """The atomic-emission return shape of :func:`surface_a11y_baseline_stale`.
    Mirrors :class:`qa_exploratory_heuristics.HeuristicSkippedEmission` —
    co-exposes the diagnostic context alongside the marker record."""

    model_config = ConfigDict(frozen=True)

    marker_record: A11yBaselineStaleEmissionRecord
    diagnostic_context: A11yAcScopedDiagnosticContext


class A11yDeltaExceededEmission(BaseModel):
    """The atomic-emission return shape of :func:`surface_a11y_delta_exceeded`."""

    model_config = ConfigDict(frozen=True)

    marker_record: A11yDeltaExceededEmissionRecord
    diagnostic_context: A11yAcScopedDiagnosticContext


class A11yDeltaModeUnstableEmission(BaseModel):
    """The atomic-emission return shape of
    :func:`surface_a11y_delta_mode_unstable`."""

    model_config = ConfigDict(frozen=True)

    marker_record: A11yDeltaModeUnstableEmissionRecord
    diagnostic_context: A11yRunScopedDiagnosticContext


# --------------------------------------------------------------------------- #
# Violation-key normalization                                                 #
# --------------------------------------------------------------------------- #


def _canonicalize_target(target: Any) -> str | None:
    """Canonicalize an axe-core ``nodes[].target`` to a stable selector string.

    Handles the three axe-core ``target`` shapes (Deque API): a single CSS
    selector string for a top-level element; an array-of-strings for an
    iframe/frame nesting path; an array-of-arrays for shadow-DOM piercing.
    Returns ``None`` when the target is empty / malformed / contains a
    non-string leaf — the signal that a stable key cannot be formed (the AC-5
    non-deterministic-delta trigger).
    """
    if isinstance(target, str):
        return target if target.strip() else None
    if not isinstance(target, Sequence) or isinstance(target, (str, bytes)):
        return None
    if len(target) == 0:
        return None
    parts: list[str] = []
    for element in target:
        if isinstance(element, str):
            if not element.strip():
                return None
            parts.append(element)
        elif isinstance(element, Sequence) and not isinstance(element, (str, bytes)):
            if len(element) == 0:
                return None
            sub: list[str] = []
            for piece in element:
                if not isinstance(piece, str) or not piece.strip():
                    return None
                sub.append(piece)
            parts.append("(" + " >> ".join(sub) + ")")
        else:
            return None
    return " | ".join(parts)


def normalize_violation_keys(raw_axe_result: Mapping[str, Any]) -> NormalizedViolations:
    """Normalize an ``axe.run()`` result to the stable ``(rule-id,
    target-selector)`` violation-key set.

    Walks ``violations[].nodes[].target``; constructs one :class:`AxeViolationKey`
    per (rule, node-target). ``stable`` is ``False`` when the top-level shape is
    malformed, when a violation lacks a usable ``id`` / ``nodes`` list, or when a
    node's ``target`` cannot be canonicalized — any of which makes the
    self-computed delta untrustworthy (the AC-5 unstable trigger).
    """
    violations = raw_axe_result.get("violations")
    if not isinstance(violations, Sequence) or isinstance(violations, (str, bytes)):
        return NormalizedViolations(keys=frozenset(), stable=False)
    keys: set[AxeViolationKey] = set()
    stable = True
    for violation in violations:
        if not isinstance(violation, Mapping):
            stable = False
            continue
        rule_id = violation.get("id")
        nodes = violation.get("nodes")
        if not isinstance(rule_id, str) or not rule_id.strip():
            stable = False
            continue
        if not isinstance(nodes, Sequence) or isinstance(nodes, (str, bytes)):
            stable = False
            continue
        for node in nodes:
            if not isinstance(node, Mapping):
                stable = False
                continue
            canonical = _canonicalize_target(node.get("target"))
            if canonical is None:
                stable = False
                continue
            try:
                keys.add(AxeViolationKey(rule_id=rule_id, target_selector=canonical))
            except ValueError:
                stable = False
    return NormalizedViolations(keys=frozenset(keys), stable=stable)


# --------------------------------------------------------------------------- #
# Baseline path + load/store + serialization                                  #
# --------------------------------------------------------------------------- #


def compute_baseline_dir(story_id: str, ac_id: str) -> pathlib.PurePosixPath:
    """Return the per-AC baseline dir ``_bmad-output/qa-a11y-baseline/{story-id}/{ac-id}``.

    Mirrors :func:`qa_evidence_persistence.compute_run_dir`'s pure-path posture;
    ``story_id`` / ``ac_id`` are hardened as path segments (rejecting separators /
    ``..`` traversal) so a malformed identifier cannot compose a path outside the
    baseline umbrella.
    """
    harden_path_segment(story_id, "compute_baseline_dir.story_id")
    harden_path_segment(ac_id, "compute_baseline_dir.ac_id")
    return pathlib.PurePosixPath(A11Y_BASELINE_ROOT) / story_id / ac_id


def serialize_violation_keys(keys: frozenset[AxeViolationKey]) -> str:
    """Serialize a violation-key set to deterministic (sorted) inspectable JSON."""
    payload = {
        "violation_keys": [
            {"rule_id": key.rule_id, "target_selector": key.target_selector}
            for key in _sorted_keys(keys)
        ]
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def deserialize_violation_keys(text: str) -> frozenset[AxeViolationKey]:
    """Inverse of :func:`serialize_violation_keys` — parse stored baseline JSON."""
    data = json.loads(text)
    items = data.get("violation_keys", []) if isinstance(data, Mapping) else []
    return frozenset(
        AxeViolationKey(rule_id=item["rule_id"], target_selector=item["target_selector"])
        for item in items
    )


def load_baseline(baseline_dir: pathlib.Path) -> frozenset[AxeViolationKey] | None:
    """Load the stored baseline key set for an AC, or ``None`` when no prior
    baseline exists or the baseline file is unreadable / corrupt.

    Returning ``None`` on a corrupt file triggers the safe baseline-stale path
    (anchor created + ``a11y-baseline-stale`` emitted) rather than propagating
    an unhandled exception through the QA run.
    """
    baseline_file = baseline_dir / BASELINE_FILENAME
    if not baseline_file.exists():
        return None
    try:
        return deserialize_violation_keys(baseline_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def store_baseline(
    baseline_dir: pathlib.Path, keys: frozenset[AxeViolationKey]
) -> pathlib.Path:
    """Write ``keys`` as the new baseline anchor (AC-3), creating the per-AC
    baseline dir. Returns the written ``baseline.json`` path."""
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline_file = baseline_dir / BASELINE_FILENAME
    baseline_file.write_text(serialize_violation_keys(keys), encoding="utf-8")
    return baseline_file


def _sorted_keys(keys: frozenset[AxeViolationKey]) -> list[AxeViolationKey]:
    return sorted(keys, key=lambda key: (key.rule_id, key.target_selector))


# --------------------------------------------------------------------------- #
# Self-computed set-difference delta + threshold compare + mode decision      #
# --------------------------------------------------------------------------- #


def compute_delta(
    baseline_keys: frozenset[AxeViolationKey],
    current_keys: frozenset[AxeViolationKey],
    threshold: int = DEFAULT_DELTA_THRESHOLD,
) -> A11yDelta:
    """Compute the self-computed baseline delta: the set-difference of current
    minus baseline violation keys (the newly-introduced violations), and whether
    that count exceeds ``threshold``.

    axe-core ships NO native baseline-delta (the load-bearing ADR-011 finding);
    THIS is where the Automator computes it over the deterministic JSON.
    """
    if threshold < 0:
        raise ValueError(f"delta threshold must be >= 0; got {threshold}")
    new_keys = frozenset(current_keys - baseline_keys)
    return A11yDelta(new_keys=new_keys, exceeded=len(new_keys) > threshold)


def decide_a11y_mode(
    baseline_keys: frozenset[AxeViolationKey] | None,
    current: NormalizedViolations,
    threshold: int = DEFAULT_DELTA_THRESHOLD,
) -> A11yAuditDecision:
    """Resolve which a11y audit arm fires for this run.

    Precedence:
      1. current normalization is unstable (regardless of whether a baseline
         exists) -> ``delta-mode-unstable`` (ship full-report-no-delta; AC-5).
         Anchoring a partial key set as the first-run baseline would cause
         false-positive ``delta-exceeded`` on subsequent stable runs, so the
         escape valve fires unconditionally when the key set is unreliable.
      2. no prior baseline (and stable) -> ``baseline-stale`` (anchor created; AC-3).
      3. baseline exists, stable -> ``delta-exceeded`` when new-key count
         exceeds ``threshold``, else ``delta-within-threshold`` (AC-4).
    """
    if not current.stable:
        return A11yAuditDecision(mode="delta-mode-unstable", new_keys=frozenset())
    if baseline_keys is None:
        return A11yAuditDecision(mode="baseline-stale", new_keys=frozenset())
    delta = compute_delta(baseline_keys, current.keys, threshold)
    mode: A11yAuditMode = "delta-exceeded" if delta.exceeded else "delta-within-threshold"
    return A11yAuditDecision(mode=mode, new_keys=delta.new_keys)


def serialize_delta_artifact(
    *,
    new_keys: frozenset[AxeViolationKey],
    baseline_keys: frozenset[AxeViolationKey],
    current_keys: frozenset[AxeViolationKey],
    threshold: int = DEFAULT_DELTA_THRESHOLD,
) -> str:
    """Serialize the delta evidence artifact (the new-violations set + the
    baseline-vs-current diff) the ``a11y-delta-exceeded`` marker's
    ``diagnostic_pointer`` directs the operator to (AC-4).

    Carries both sides of the diff: ``new_violation_keys`` (introduced since
    the baseline) and ``removed_violation_keys`` (fixed since the baseline).
    """
    removed_keys = frozenset(baseline_keys - current_keys)
    payload = {
        "baseline_count": len(baseline_keys),
        "current_count": len(current_keys),
        "new_violation_count": len(new_keys),
        "removed_violation_count": len(removed_keys),
        "threshold": threshold,
        "exceeded": len(new_keys) > threshold,
        "new_violation_keys": [
            {"rule_id": key.rule_id, "target_selector": key.target_selector}
            for key in _sorted_keys(new_keys)
        ],
        "removed_violation_keys": [
            {"rule_id": key.rule_id, "target_selector": key.target_selector}
            for key in _sorted_keys(removed_keys)
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


# --------------------------------------------------------------------------- #
# Pattern-5 atomic-on-failure emission helpers                                #
# --------------------------------------------------------------------------- #


def surface_a11y_baseline_stale(
    story_id: str,
    ac_id: str,
    registry: MarkerClassRegistry,
) -> A11yBaselineStaleEmission:
    """Atomic-on-failure ``a11y-baseline-stale`` (informational) emission helper.

    Mirrors :func:`qa_exploratory_heuristics.surface_heuristic_skipped` AS-IS:
    :func:`validate_marker_emission` runs FIRST; on registry rejection
    :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass` propagates
    per Pattern 5 BEFORE any partial state is constructed.

    Pure: no file I/O, no orchestrator-event log write — the emission record is
    data the wrapper rides on the envelope's ``a11y_emissions`` array; the bundle
    assembler renders the marker comment.

    Raises:
        UnknownMarkerClass: registry does not contain ``"a11y-baseline-stale"``.
    """
    validate_marker_emission(registry, A11Y_BASELINE_STALE_MARKER)
    diagnostic_context = A11yAcScopedDiagnosticContext(story_id=story_id, ac_id=ac_id)
    marker_record = A11yBaselineStaleEmissionRecord(
        marker_class=A11Y_BASELINE_STALE_MARKER,
        ac_id=ac_id,
    )
    return A11yBaselineStaleEmission(
        marker_record=marker_record,
        diagnostic_context=diagnostic_context,
    )


def surface_a11y_delta_exceeded(
    story_id: str,
    ac_id: str,
    registry: MarkerClassRegistry,
) -> A11yDeltaExceededEmission:
    """Atomic-on-failure ``a11y-delta-exceeded`` emission helper.

    Mirrors :func:`surface_a11y_baseline_stale`. Sensor-not-advisor: surfaces the
    regression for the human; does NOT auto-fail the AC.

    Raises:
        UnknownMarkerClass: registry does not contain ``"a11y-delta-exceeded"``.
    """
    validate_marker_emission(registry, A11Y_DELTA_EXCEEDED_MARKER)
    diagnostic_context = A11yAcScopedDiagnosticContext(story_id=story_id, ac_id=ac_id)
    marker_record = A11yDeltaExceededEmissionRecord(
        marker_class=A11Y_DELTA_EXCEEDED_MARKER,
        ac_id=ac_id,
    )
    return A11yDeltaExceededEmission(
        marker_record=marker_record,
        diagnostic_context=diagnostic_context,
    )


def surface_a11y_delta_mode_unstable(
    story_id: str,
    registry: MarkerClassRegistry,
) -> A11yDeltaModeUnstableEmission:
    """Atomic-on-failure ``a11y-delta-mode-unstable`` (fallback) emission helper.

    Envelope-scoped (``pointer_context_fields: []`` — no ``ac_id``). Mirrors
    :func:`surface_a11y_baseline_stale`. This is the ADR-011 loud-fail escape
    valve: the delta is withheld rather than emitting a possibly-wrong regression
    verdict (the full report is still captured by the wrapper).

    Raises:
        UnknownMarkerClass: registry does not contain ``"a11y-delta-mode-unstable"``.
    """
    validate_marker_emission(registry, A11Y_DELTA_MODE_UNSTABLE_MARKER)
    diagnostic_context = A11yRunScopedDiagnosticContext(story_id=story_id)
    marker_record = A11yDeltaModeUnstableEmissionRecord(
        marker_class=A11Y_DELTA_MODE_UNSTABLE_MARKER,
    )
    return A11yDeltaModeUnstableEmission(
        marker_record=marker_record,
        diagnostic_context=diagnostic_context,
    )


__all__ = [
    "A11Y_BASELINE_ROOT",
    "A11Y_BASELINE_STALE_MARKER",
    "A11Y_DELTA_EXCEEDED_MARKER",
    "A11Y_DELTA_MODE_UNSTABLE_MARKER",
    "BASELINE_FILENAME",
    "DEFAULT_DELTA_THRESHOLD",
    "A11yAuditMode",
    "AxeViolationKey",
    "NormalizedViolations",
    "A11yDelta",
    "A11yAuditDecision",
    "A11yAcScopedDiagnosticContext",
    "A11yRunScopedDiagnosticContext",
    "A11yBaselineStaleEmissionRecord",
    "A11yDeltaExceededEmissionRecord",
    "A11yDeltaModeUnstableEmissionRecord",
    "A11yBaselineStaleEmission",
    "A11yDeltaExceededEmission",
    "A11yDeltaModeUnstableEmission",
    "normalize_violation_keys",
    "compute_baseline_dir",
    "serialize_violation_keys",
    "deserialize_violation_keys",
    "load_baseline",
    "store_baseline",
    "compute_delta",
    "decide_a11y_mode",
    "serialize_delta_artifact",
    "surface_a11y_baseline_stale",
    "surface_a11y_delta_exceeded",
    "surface_a11y_delta_mode_unstable",
]
