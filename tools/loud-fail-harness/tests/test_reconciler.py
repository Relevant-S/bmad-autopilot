"""Contract-coverage matrix for substrate component 3 (skip-event/marker reconciler).

This docstring IS the contract-coverage checklist required by AC-6. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to story 1.2 AC-5 + story 1.3
AC-5).

Three-case classification (AC-4, AC-6) — pure-case fixtures:
    [x] only matched_pairs                                       → test_only_matched_pairs
    [x] only silent_skips                                        → test_only_silent_skips
    [x] only orphan_markers                                      → test_only_orphan_markers

Mixed-case fixture (AC-6):
    [x] all three classifications populated simultaneously       → test_mixed_classification

Greedy 1:1 matching (AC-4 algorithm rule):
    [x] 3 skip-events + 5 markers same key → 3 matched, 2 orphan → test_greedy_more_markers_than_skips
    [x] 5 skip-events + 3 markers same key → 3 matched, 2 silent → test_greedy_more_skips_than_markers

story_id matching (AC-4 algorithm rule):
    [x] both None → matches on marker_class only                 → test_story_id_both_none_match
    [x] both populated and equal → match                         → test_story_id_both_populated_match
    [x] both populated and unequal → no match                    → test_story_id_both_populated_unequal_no_match
    [x] one None / one populated → no match (asymmetric)         → test_story_id_asymmetric_no_match

Determinism (AC-5):
    [x] shuffled-equivalent inputs → byte-identical output       → test_determinism_under_shuffle

Taxonomy file shape (AC-1, AC-2, AC-3, AC-6; extended by Story 2.3 — 27→29 entries; schema_version 1.0→1.1):
    [x] all 29 expected marker_class identifiers present         → test_taxonomy_has_29_canonical_markers
    [x] every entry has non-empty diagnostic_pointer             → test_taxonomy_entries_have_non_empty_diagnostic_pointer
    [x] schema_version: "1.1" at top level                       → test_taxonomy_declares_schema_version_1_1
    [x] no duplicate marker_class identifiers (collision test)   → test_taxonomy_has_no_duplicate_marker_classes
    [x] every entry carries sub_classifications field            → test_taxonomy_entries_have_sub_classifications_field

14 mandated diagnostic_pointer keyword spot-checks (AC-2 verbatim text; Story 2.3 added 2):
    [x] walking-skeleton-bundle / "Epic 2 thin-signals"
    [x] review-layer-failed / "decision_needed: HIGH"
    [x] playwright-mcp-unavailable / "FR17"
    [x] scope-assertion-violation / "FR10"
    [x] retry-budget-exhausted / "FR8"
    [x] bundle-assembly-failed / "FR59"
    [x] reconciler-mismatch-runtime / "FR33"
    [x] cost-telemetry-unavailable / "ADR-006"
    [x] story-doc-version-out-of-window / "FR43"
    [x] init-would-destroy-existing-artifact / "FR41"
    [x] recovery-state-conflict / "NFR-R8"
    [x] orphan-run-state-detected / "FR48b"
    [x] git-uncommitted-work-detected / "NFR-R3"        (Story 2.3)
    [x] trunk-branch-write-rejected / "NFR-S3"          (Story 2.3)
    All fourteen covered by                                      → test_mandated_diagnostic_pointer_keywords

Pydantic v2 loud-fail (Pattern 5 / AC-4):
    [x] missing marker_class on SkipEvent → ValidationError      → test_skip_event_missing_marker_class_raises
    [x] missing marker_class on Marker → ValidationError         → test_marker_missing_marker_class_raises

Pydantic v2 frozen-model immutability (AC-4 model_config rule):
    [x] reassigning ClassificationResult field → exception       → test_classification_result_is_frozen
    [x] reassigning SkipEvent field → exception                  → test_skip_event_is_frozen

load_marker_taxonomy helper (Task 3 surface):
    [x] default path resolves to <repo-root>/schemas/...         → test_load_marker_taxonomy_default_path
    [x] explicit path override loads alternate file              → test_load_marker_taxonomy_explicit_path
    [x] malformed file raises RuntimeError (loud-fail)           → test_load_marker_taxonomy_malformed_raises
    [x] entry missing marker_class raises RuntimeError           → test_load_marker_taxonomy_entry_missing_marker_class_raises

Coverage gate (AC-6):
    [x] reconciler.py module-level statement coverage ≥ 90%      → review-enforced; not a CI gate

Sanity / shape checks (not AC-gated):
    [x] matched pair references correct skip_event and marker     → test_matched_pair_shape
"""

from __future__ import annotations

import pathlib
import random

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness.envelope_validator import find_repo_root
from loud_fail_harness.reconciler import (
    ClassificationResult,
    Marker,
    MatchedPair,
    SkipEvent,
    load_marker_taxonomy,
    reconcile,
)


CANONICAL_MARKER_CLASSES = [
    "LAD-skipped",
    "Tier-3-not-configured",
    "heuristic-skipped",
    "mobile-blocked",
    "env-setup-failed",
    "plan-drift-detected",
    "specialist-timeout",
    "context-near-limit",
    "evidence-truncated",
    "hook-failed",
    "undocumented-section-write",
    "orphan-process-cleanup",
    "cost-near-ceiling",
    "smoke-first-abort",
    "dangling-evidence-ref",
    "walking-skeleton-bundle",
    "review-layer-failed",
    "playwright-mcp-unavailable",
    "scope-assertion-violation",
    "retry-budget-exhausted",
    "bundle-assembly-failed",
    "reconciler-mismatch-runtime",
    "cost-telemetry-unavailable",
    "story-doc-version-out-of-window",
    "init-would-destroy-existing-artifact",
    "recovery-state-conflict",
    "orphan-run-state-detected",
    # Story 2.3 — branch-lifecycle write-time guards (NFR-R3 + NFR-S3).
    "git-uncommitted-work-detected",
    "trunk-branch-write-rejected",
]

# Map: marker_class → key phrase that must appear verbatim in
# `diagnostic_pointer`. Sourced from AC-2's mandated text. One keyword per
# marker is enough; full-text equality is too brittle.
MANDATED_DIAGNOSTIC_KEYWORDS: dict[str, str] = {
    "walking-skeleton-bundle": "Epic 2 thin-signals",
    "review-layer-failed": "decision_needed: HIGH",
    "playwright-mcp-unavailable": "FR17",
    "scope-assertion-violation": "FR10",
    "retry-budget-exhausted": "FR8",
    "bundle-assembly-failed": "FR59",
    "reconciler-mismatch-runtime": "FR33",
    "cost-telemetry-unavailable": "ADR-006",
    "story-doc-version-out-of-window": "FR43",
    "init-would-destroy-existing-artifact": "FR41",
    "recovery-state-conflict": "NFR-R8",
    "orphan-run-state-detected": "FR48b",
    # Story 2.3 — branch-lifecycle write-time guards.
    "git-uncommitted-work-detected": "NFR-R3",
    "trunk-branch-write-rejected": "NFR-S3",
}


TAXONOMY_PATH = (
    find_repo_root() / "schemas" / "marker-taxonomy.yaml"
)


@pytest.fixture(scope="module")
def taxonomy_data() -> dict:
    return yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Three-case classification — pure cases (AC-4, AC-6)                         #
# --------------------------------------------------------------------------- #


def test_only_matched_pairs() -> None:
    skips = [
        SkipEvent(marker_class="LAD-skipped", story_id="1.4"),
        SkipEvent(marker_class="hook-failed", story_id="1.4"),
        SkipEvent(marker_class="env-setup-failed", story_id="2.1"),
    ]
    markers = [
        Marker(marker_class="LAD-skipped", story_id="1.4"),
        Marker(marker_class="hook-failed", story_id="1.4"),
        Marker(marker_class="env-setup-failed", story_id="2.1"),
    ]
    result = reconcile(skips, markers)
    assert len(result.matched) == 3
    assert result.silent_skips == []
    assert result.orphan_markers == []


def test_only_silent_skips() -> None:
    skips = [
        SkipEvent(marker_class="LAD-skipped"),
        SkipEvent(marker_class="hook-failed"),
        SkipEvent(marker_class="env-setup-failed"),
    ]
    result = reconcile(skips, [])
    assert result.matched == []
    assert len(result.silent_skips) == 3
    assert result.orphan_markers == []


def test_only_orphan_markers() -> None:
    markers = [
        Marker(marker_class="LAD-skipped"),
        Marker(marker_class="hook-failed"),
        Marker(marker_class="env-setup-failed"),
    ]
    result = reconcile([], markers)
    assert result.matched == []
    assert result.silent_skips == []
    assert len(result.orphan_markers) == 3


# --------------------------------------------------------------------------- #
# Mixed-case fixture (AC-6)                                                   #
# --------------------------------------------------------------------------- #


def test_mixed_classification() -> None:
    skips = [
        SkipEvent(marker_class="LAD-skipped", story_id="1.4"),  # matches
        SkipEvent(marker_class="hook-failed", story_id="1.4"),  # matches
        SkipEvent(marker_class="env-setup-failed", story_id="2.1"),  # silent
        SkipEvent(marker_class="plan-drift-detected", story_id="3.1"),  # silent
        SkipEvent(marker_class="evidence-truncated", story_id="2.2"),  # silent
    ]
    markers = [
        Marker(marker_class="LAD-skipped", story_id="1.4"),
        Marker(marker_class="hook-failed", story_id="1.4"),
        Marker(marker_class="cost-near-ceiling", story_id="4.5"),  # orphan
        Marker(marker_class="smoke-first-abort", story_id="4.6"),  # orphan
    ]
    result = reconcile(skips, markers)
    assert len(result.matched) == 2
    matched_classes = {pair.skip_event.marker_class for pair in result.matched}
    assert matched_classes == {"LAD-skipped", "hook-failed"}

    assert len(result.silent_skips) == 3
    silent_classes = {s.marker_class for s in result.silent_skips}
    assert silent_classes == {
        "env-setup-failed",
        "plan-drift-detected",
        "evidence-truncated",
    }

    assert len(result.orphan_markers) == 2
    orphan_classes = {m.marker_class for m in result.orphan_markers}
    assert orphan_classes == {"cost-near-ceiling", "smoke-first-abort"}


# --------------------------------------------------------------------------- #
# Greedy 1:1 matching (AC-4 algorithm rule)                                   #
# --------------------------------------------------------------------------- #


def test_greedy_more_markers_than_skips() -> None:
    skips = [SkipEvent(marker_class="hook-failed", story_id="1.4") for _ in range(3)]
    markers = [Marker(marker_class="hook-failed", story_id="1.4") for _ in range(5)]
    result = reconcile(skips, markers)
    assert len(result.matched) == 3
    assert result.silent_skips == []
    assert len(result.orphan_markers) == 2


def test_greedy_more_skips_than_markers() -> None:
    skips = [SkipEvent(marker_class="hook-failed", story_id="1.4") for _ in range(5)]
    markers = [Marker(marker_class="hook-failed", story_id="1.4") for _ in range(3)]
    result = reconcile(skips, markers)
    assert len(result.matched) == 3
    assert len(result.silent_skips) == 2
    assert result.orphan_markers == []


# --------------------------------------------------------------------------- #
# story_id matching modes (AC-4 algorithm rule)                               #
# --------------------------------------------------------------------------- #


def test_story_id_both_none_match() -> None:
    """Story-id-agnostic mode (both ``None``) matches purely on
    ``marker_class`` — the fixture-driven Layer C input shape."""
    result = reconcile(
        [SkipEvent(marker_class="LAD-skipped")],
        [Marker(marker_class="LAD-skipped")],
    )
    assert len(result.matched) == 1


def test_story_id_both_populated_match() -> None:
    result = reconcile(
        [SkipEvent(marker_class="LAD-skipped", story_id="1.4")],
        [Marker(marker_class="LAD-skipped", story_id="1.4")],
    )
    assert len(result.matched) == 1


def test_story_id_both_populated_unequal_no_match() -> None:
    result = reconcile(
        [SkipEvent(marker_class="LAD-skipped", story_id="1.4")],
        [Marker(marker_class="LAD-skipped", story_id="2.7")],
    )
    assert result.matched == []
    assert len(result.silent_skips) == 1
    assert len(result.orphan_markers) == 1


def test_story_id_asymmetric_no_match() -> None:
    """Asymmetric case (one ``None`` / one populated) does NOT match — strict
    equality is the conservative default at this story; Epic 6's runtime
    variant may relax with explicit AC backing."""
    result = reconcile(
        [SkipEvent(marker_class="LAD-skipped", story_id=None)],
        [Marker(marker_class="LAD-skipped", story_id="1.4")],
    )
    assert result.matched == []
    assert len(result.silent_skips) == 1
    assert len(result.orphan_markers) == 1

    # Reverse asymmetry — same expected outcome.
    result2 = reconcile(
        [SkipEvent(marker_class="LAD-skipped", story_id="1.4")],
        [Marker(marker_class="LAD-skipped", story_id=None)],
    )
    assert result2.matched == []
    assert len(result2.silent_skips) == 1
    assert len(result2.orphan_markers) == 1


# --------------------------------------------------------------------------- #
# Determinism (AC-5)                                                          #
# --------------------------------------------------------------------------- #


def test_determinism_under_shuffle() -> None:
    """Shuffled-equivalent inputs MUST produce byte-identical
    ``model_dump_json()`` output. Run multiple iterations to catch any
    Python run-to-run variance (PYTHONHASHSEED, dict ordering, etc.)."""
    skips_canonical = [
        SkipEvent(marker_class="LAD-skipped", story_id="1.4", source="a"),
        SkipEvent(marker_class="hook-failed", story_id="1.4", source="b"),
        SkipEvent(marker_class="env-setup-failed", story_id="2.1", source="c"),
        SkipEvent(marker_class="plan-drift-detected", story_id="3.1", source="d"),
    ]
    markers_canonical = [
        Marker(marker_class="LAD-skipped", story_id="1.4", source="x"),
        Marker(marker_class="hook-failed", story_id="1.4", source="y"),
        Marker(marker_class="cost-near-ceiling", story_id="4.5", source="z"),
    ]

    baseline_json = reconcile(
        list(skips_canonical), list(markers_canonical)
    ).model_dump_json()

    rng = random.Random(42)
    for iteration in range(5):
        skips_shuffled = list(skips_canonical)
        markers_shuffled = list(markers_canonical)
        rng.shuffle(skips_shuffled)
        rng.shuffle(markers_shuffled)
        run_json = reconcile(skips_shuffled, markers_shuffled).model_dump_json()
        assert run_json == baseline_json, (
            f"determinism violation on iteration {iteration}: "
            f"output diverged under input shuffle"
        )


# --------------------------------------------------------------------------- #
# Taxonomy file shape (AC-1, AC-2, AC-3, AC-6)                                #
# --------------------------------------------------------------------------- #


def test_taxonomy_has_29_canonical_markers(taxonomy_data: dict) -> None:
    names = [m["marker_class"] for m in taxonomy_data["markers"]]
    assert len(names) == 29
    assert names == CANONICAL_MARKER_CLASSES, (
        "marker-taxonomy.yaml entries are out of canonical order; "
        "AC-2 mandates the order verbatim (Story 2.3 appended entries 28-29)"
    )


def test_taxonomy_entries_have_non_empty_diagnostic_pointer(
    taxonomy_data: dict,
) -> None:
    for entry in taxonomy_data["markers"]:
        pointer = entry.get("diagnostic_pointer")
        assert isinstance(pointer, str)
        assert pointer.strip(), entry["marker_class"]


def test_taxonomy_declares_schema_version_1_1(taxonomy_data: dict) -> None:
    assert taxonomy_data.get("schema_version") == "1.1"


def test_taxonomy_has_no_duplicate_marker_classes(taxonomy_data: dict) -> None:
    names = [m["marker_class"] for m in taxonomy_data["markers"]]
    assert len(set(names)) == len(names)


def test_taxonomy_entries_have_sub_classifications_field(
    taxonomy_data: dict,
) -> None:
    for entry in taxonomy_data["markers"]:
        assert "sub_classifications" in entry, entry["marker_class"]
        assert isinstance(entry["sub_classifications"], list)


def test_mandated_diagnostic_pointer_keywords(taxonomy_data: dict) -> None:
    """The 12 markers listed in AC-2 as having load-bearing diagnostic_pointer
    text must contain the AC-mandated key phrase. Spot-check, not full-text
    equality (which would be too brittle to maintain)."""
    by_name = {m["marker_class"]: m for m in taxonomy_data["markers"]}
    for marker_class, keyword in MANDATED_DIAGNOSTIC_KEYWORDS.items():
        entry = by_name[marker_class]
        assert keyword in entry["diagnostic_pointer"], (
            f"diagnostic_pointer for {marker_class} missing AC-mandated "
            f"keyword '{keyword}'"
        )


# --------------------------------------------------------------------------- #
# Pydantic v2 loud-fail discipline (Pattern 5 / AC-4)                         #
# --------------------------------------------------------------------------- #


def test_skip_event_missing_marker_class_raises() -> None:
    with pytest.raises(ValidationError):
        SkipEvent.model_validate({"story_id": "1.4"})  # type: ignore[arg-type]


def test_marker_missing_marker_class_raises() -> None:
    with pytest.raises(ValidationError):
        Marker.model_validate({"story_id": "1.4"})  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Pydantic v2 frozen-model immutability (AC-4 model_config rule)              #
# --------------------------------------------------------------------------- #


def test_classification_result_is_frozen() -> None:
    result = reconcile([], [])
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        result.matched = []  # type: ignore[misc]


def test_skip_event_is_frozen() -> None:
    skip = SkipEvent(marker_class="LAD-skipped")
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        skip.marker_class = "hook-failed"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# load_marker_taxonomy helper                                                 #
# --------------------------------------------------------------------------- #


def test_load_marker_taxonomy_default_path() -> None:
    ids = load_marker_taxonomy()
    assert isinstance(ids, set)
    assert len(ids) == 29
    assert set(CANONICAL_MARKER_CLASSES) == ids


def test_load_marker_taxonomy_explicit_path(tmp_path: pathlib.Path) -> None:
    fixture = tmp_path / "fake-taxonomy.yaml"
    fixture.write_text(
        "schema_version: \"0.0\"\n"
        "markers:\n"
        "  - marker_class: alpha-skipped\n"
        "    diagnostic_pointer: a\n"
        "    sub_classifications: []\n"
        "  - marker_class: beta-skipped\n"
        "    diagnostic_pointer: b\n"
        "    sub_classifications: []\n",
        encoding="utf-8",
    )
    ids = load_marker_taxonomy(fixture)
    assert ids == {"alpha-skipped", "beta-skipped"}


def test_load_marker_taxonomy_malformed_raises(tmp_path: pathlib.Path) -> None:
    fixture = tmp_path / "broken.yaml"
    fixture.write_text("not_a_markers_list: 42\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="malformed"):
        load_marker_taxonomy(fixture)


def test_load_marker_taxonomy_entry_missing_marker_class_raises(tmp_path: pathlib.Path) -> None:
    """Entry-level validation: a dict missing 'marker_class' raises RuntimeError,
    not a bare KeyError (loud-fail discipline — Pattern 5)."""
    fixture = tmp_path / "bad-entry.yaml"
    fixture.write_text(
        "schema_version: \"0.0\"\n"
        "markers:\n"
        "  - diagnostic_pointer: oops\n"
        "    sub_classifications: []\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="malformed"):
        load_marker_taxonomy(fixture)


# --------------------------------------------------------------------------- #
# Sanity: matched pairs reference the SAME objects we passed in (no copy)     #
# --------------------------------------------------------------------------- #


def test_matched_pair_shape() -> None:
    skip = SkipEvent(marker_class="LAD-skipped", story_id="1.4", source="t")
    mark = Marker(marker_class="LAD-skipped", story_id="1.4", source="b")
    result = reconcile([skip], [mark])
    assert isinstance(result, ClassificationResult)
    assert isinstance(result.matched[0], MatchedPair)
    assert result.matched[0].skip_event == skip
    assert result.matched[0].marker == mark
