"""Substrate component 3: Skip-event-to-marker reconciliation (Layer A primary mechanism).

See ADR-003 + FR30 + FR33.

This module is the load-bearing half of the loud-fail substrate. It exists
specifically to keep FR33's reconciliation check non-tautological: a check
that derives "what skipped" from "what markers were emitted" passes whenever
markers exist, regardless of whether the underlying skip-events actually
fired. The reconciler closes that loop by accepting two independent inputs
(skip-events + markers) and producing a triple-classification:

    matched        — (skip-event, marker) pairs (PASS)
    silent_skips   — skip-events without a matching marker (FAIL — the
                     loud-fail-doctrine violation FR33 names)
    orphan_markers — markers without a matching skip-event (WARN)

Matching algorithm (canonical at this story):

    1. Sort BOTH inputs by ``(marker_class, story_id, source)`` using
       ``_NONE_LAST`` (U+FFFF) as the sentinel for ``None`` values — placing
       ``None`` AFTER all non-empty strings under Unicode order (AC-5:
       "None-equivalent placeholders sorted last").
    2. Greedy 1:1 within each ``(marker_class, story_id)`` group, where the
       story_id rule is: BOTH ``None`` OR BOTH populated and equal. The
       asymmetric "one None / other populated" case does NOT match — strict
       equality is the conservative default at this story; Epic 6's runtime
       variant may relax with explicit AC backing.
    3. Remaining unmatched skip-events become ``silent_skips`` (FAIL);
       remaining unmatched markers become ``orphan_markers`` (WARN).
    4. The reconciler is taxonomy-agnostic by design: it does NOT validate
       ``marker_class`` membership against ``schemas/marker-taxonomy.yaml``.
       That cross-check is substrate component 4's job (story 1.5's
       ``enumeration_check``).

Determinism (AC-5):
    ``model_dump_json()`` of the same ``ClassificationResult`` is byte-
    identical across runs given the same inputs. Achieved by deterministic
    input sort, no reliance on Python ``set`` iteration order in output, and
    Pydantic v2's field-declaration-order JSON serialization (NOT alphabetical
    key order).

Loud-fail discipline (Pattern 5):
    Pydantic v2 raises ``ValidationError`` at model construction when inputs
    are missing required fields; this is propagated, not swallowed. The
    three-case classification is for valid-shape inputs only — malformed
    inputs are caller bugs, distinct from classification cases.

Sensor-not-advisor:
    The reconciler reports what classification each input falls into. It does
    NOT recommend remediation, prioritize escalation, or suggest "next
    actions" on silent-skip cases. That is downstream tooling's job (story
    1.8's CI gate, Epic 6's runtime emission, the PR-bundle assembler).
"""

from __future__ import annotations

import pathlib
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict

from loud_fail_harness._shared import find_repo_root

# Sentinel for None values in sort keys: U+FFFF sorts after all printable
# Unicode strings, satisfying AC-5's "None-equivalent placeholders sorted last."
_NONE_LAST = "￿"


class SkipEvent(BaseModel):
    """A detected skip-event awaiting marker reconciliation.

    The matching key is ``(marker_class, story_id)``. ``source`` is free-form
    provenance (e.g. ``"orchestrator-event-log"``, ``"runtime-state-
    inspection"``, ``"fixture-coverage"``) used only for deterministic
    ordering and human diagnostics; it does NOT participate in matching.
    """

    model_config = ConfigDict(frozen=True)

    marker_class: str
    story_id: Optional[str] = None
    source: Optional[str] = None


class Marker(BaseModel):
    """An emitted marker awaiting skip-event reconciliation. Same shape as
    ``SkipEvent``; the distinction is semantic (emitted vs. detected)."""

    model_config = ConfigDict(frozen=True)

    marker_class: str
    story_id: Optional[str] = None
    source: Optional[str] = None


class MatchedPair(BaseModel):
    """A reconciled (skip-event, marker) pair. PASS classification."""

    model_config = ConfigDict(frozen=True)

    skip_event: SkipEvent
    marker: Marker


class ClassificationResult(BaseModel):
    """Triple-classification reconciler output.

    Field declaration order is load-bearing: ``model_dump_json()`` follows
    declaration order (Pydantic v2 default), which AC-5's byte-equality
    guarantee depends on. Do NOT reorder these fields without bumping the
    reconciler API's contract version.
    """

    model_config = ConfigDict(frozen=True)

    matched: list[MatchedPair]
    silent_skips: list[SkipEvent]
    orphan_markers: list[Marker]


def _skip_sort_key(skip: SkipEvent) -> tuple[str, str, str]:
    return (
        skip.marker_class,
        skip.story_id if skip.story_id is not None else _NONE_LAST,
        skip.source if skip.source is not None else _NONE_LAST,
    )


def _marker_sort_key(marker: Marker) -> tuple[str, str, str]:
    return (
        marker.marker_class,
        marker.story_id if marker.story_id is not None else _NONE_LAST,
        marker.source if marker.source is not None else _NONE_LAST,
    )


def _matches(skip: SkipEvent, marker: Marker) -> bool:
    if skip.marker_class != marker.marker_class:
        return False
    if skip.story_id is None and marker.story_id is None:
        return True
    if skip.story_id is not None and marker.story_id is not None and skip.story_id == marker.story_id:
        return True
    return False


def reconcile(
    skip_events: list[SkipEvent], markers: list[Marker]
) -> ClassificationResult:
    """Reconcile skip-events against markers; return triple-classification.

    See module docstring for the canonical matching algorithm and determinism
    rules. The matching is greedy and 1:1 within an ``(marker_class,
    story_id)`` group; if K skip-events share a key with M markers, the
    output produces ``min(K, M)`` matches and the surplus on the larger side
    falls into ``silent_skips`` or ``orphan_markers`` respectively.
    """
    sorted_skips = sorted(skip_events, key=_skip_sort_key)
    sorted_markers = sorted(markers, key=_marker_sort_key)

    matched: list[MatchedPair] = []
    silent_skips: list[SkipEvent] = []
    consumed_marker_indices: set[int] = set()

    for skip in sorted_skips:
        match_idx: int | None = None
        for idx, marker in enumerate(sorted_markers):
            if idx in consumed_marker_indices:
                continue
            if _matches(skip, marker):
                match_idx = idx
                break
        if match_idx is None:
            silent_skips.append(skip)
        else:
            matched.append(
                MatchedPair(skip_event=skip, marker=sorted_markers[match_idx])
            )
            consumed_marker_indices.add(match_idx)

    orphan_markers = [
        marker
        for idx, marker in enumerate(sorted_markers)
        if idx not in consumed_marker_indices
    ]

    return ClassificationResult(
        matched=matched,
        silent_skips=silent_skips,
        orphan_markers=orphan_markers,
    )


def load_marker_taxonomy(path: pathlib.Path | None = None) -> set[str]:
    """Return the canonical set of ``marker_class`` identifiers from the
    marker-taxonomy YAML file.

    Convenience helper for downstream callers (substrate components 4 + 5
    in stories 1.5 + 1.7, and the FR33 fixture-driven CI gate in story 1.8)
    that need to validate ``marker_class`` membership against the canonical
    enumeration. NOT consumed by :func:`reconcile` — the reconciler is
    taxonomy-agnostic by design.

    The default path resolves to ``<repo-root>/schemas/marker-taxonomy.yaml``
    via :func:`loud_fail_harness.envelope_validator.find_repo_root`. Pass an
    explicit ``path`` to override (e.g. for fixture-driven tests).
    """
    if path is None:
        path = find_repo_root() / "schemas" / "marker-taxonomy.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("markers"), list):
        raise RuntimeError(
            f"marker-taxonomy file at {path} is malformed: "
            "expected top-level mapping with a 'markers' list"
        )
    result: set[str] = set()
    for i, entry in enumerate(raw["markers"]):
        if not isinstance(entry, dict) or "marker_class" not in entry:
            raise RuntimeError(
                f"marker-taxonomy file at {path} is malformed: "
                f"entry {i} must be a mapping with a 'marker_class' key; "
                f"got: {entry!r}"
            )
        mc = entry["marker_class"]
        if not isinstance(mc, str):
            raise RuntimeError(
                f"marker-taxonomy file at {path} is malformed: "
                f"entry {i} has non-string marker_class value: {mc!r}"
            )
        result.add(mc)
    return result


def load_marker_lifetimes(path: pathlib.Path | None = None) -> dict[str, str]:
    """Return a ``marker_class`` → ``lifetime`` map from the marker-taxonomy
    YAML file, defaulting every entry that omits ``lifetime`` to ``"durable"``.

    Sibling of :func:`load_marker_taxonomy` (same parse machinery; same
    default-path resolution via :func:`find_repo_root` at function-call time).
    Added by Story 15.1 (AC-6) so the epic-run-state write-back filter can
    source the transient/durable axis structurally from the taxonomy rather
    than from a hardcoded class list — a future transient marker is covered
    with zero filter edits.

    ``lifetime`` is an optional field (Story 15.1 MINOR bump 1.8 → 1.9): an
    entry without it inherits ``"durable"`` (preserving the Story 1.4
    marker-permanence rule for durable markers). A present-but-invalid
    ``lifetime`` value raises ``RuntimeError`` (Pattern 5 loud-fail — a typo
    in the taxonomy must not silently degrade to ``durable``).
    """
    if path is None:
        path = find_repo_root() / "schemas" / "marker-taxonomy.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("markers"), list):
        raise RuntimeError(
            f"marker-taxonomy file at {path} is malformed: "
            "expected top-level mapping with a 'markers' list"
        )
    result: dict[str, str] = {}
    for i, entry in enumerate(raw["markers"]):
        if not isinstance(entry, dict) or "marker_class" not in entry:
            raise RuntimeError(
                f"marker-taxonomy file at {path} is malformed: "
                f"entry {i} must be a mapping with a 'marker_class' key; "
                f"got: {entry!r}"
            )
        mc = entry["marker_class"]
        if not isinstance(mc, str):
            raise RuntimeError(
                f"marker-taxonomy file at {path} is malformed: "
                f"entry {i} has non-string marker_class value: {mc!r}"
            )
        lifetime = entry.get("lifetime", "durable")
        if lifetime not in ("transient", "durable"):
            raise RuntimeError(
                f"marker-taxonomy file at {path} is malformed: "
                f"entry {i} ({mc!r}) has invalid lifetime {lifetime!r} "
                "(expected 'transient' or 'durable')"
            )
        result[mc] = lifetime
    return result
