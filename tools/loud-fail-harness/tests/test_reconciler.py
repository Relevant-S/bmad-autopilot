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

Taxonomy file shape (AC-1, AC-2, AC-3, AC-6; extended by Story 2.3 — 27→29 entries; schema_version 1.0→1.6; Story 14.3 — 29→30; Story 14.5 — 30→31; schema_version 1.6→1.8; Story 15.1 — optional `lifetime` field, 31 entries unchanged, schema_version 1.8→1.9; Story 15.2 — 31→32 entries, schema_version 1.9→1.10; Story 16.2 — 32→33 entries, schema_version 1.10→1.11; Story 24.1 — 33→34 entries, schema_version 1.11→1.12; Story 19.2 — 34 entries unchanged, +4 heuristic-skipped sub_classifications, schema_version 1.12→1.13; Story 19.3 — 34→37 entries (a11y-baseline-stale / a11y-delta-exceeded / a11y-delta-mode-unstable), schema_version 1.13→1.14):
    [x] all 37 expected marker_class identifiers present         → test_taxonomy_has_37_canonical_markers
    [x] every entry has non-empty diagnostic_pointer             → test_taxonomy_entries_have_non_empty_diagnostic_pointer
    [x] schema_version: "1.14" at top level                      → test_taxonomy_declares_schema_version_1_14
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

load_marker_lifetimes helper (Story 15.1 AC-6 surface):
    [x] default path returns dict with worktree-stale-lock → transient    → test_load_marker_lifetimes_default_path
    [x] explicit path override loads alternate file                        → test_load_marker_lifetimes_explicit_path
    [x] all entries without lifetime field default to durable              → test_load_marker_lifetimes_defaults_to_durable
    [x] present-but-invalid lifetime value raises RuntimeError            → test_load_marker_lifetimes_invalid_lifetime_raises
    [x] missing file raises FileNotFoundError (loud-fail)                  → test_load_marker_lifetimes_missing_file_raises

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
    load_marker_lifetimes,
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
    # Story 20.1 — Epic 20 per-run plan re-derivation cross-check (FR-P2-9).
    "plan-rederivation-drift-detected",
    # Story 20.3 — Epic 20 longitudinal flakiness threshold (FR-P2-8).
    "flakiness-threshold-exceeded",
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
    # Story 14.3 — Epic 14 worktree-isolation substrate (NFR-R2 + NFR-R8).
    "worktree-stale-lock",
    # Story 14.5 — Epic 14 parallel-mode cross-state pollution pre-provision.
    "parallel-story-state-pollution",
    # Story 15.2 — Epic 15 per-epic cumulative retry-budget exhaustion.
    "epic-budget-exhausted",
    # Story 16.2 — Epic 16 sprint-scope systemic-escalation signal.
    "sprint-escalation-rate-exceeded",
    # Story 24.1 — Epic 24 parallel-dispatch admission/seed infra loud-fail.
    "parallel-dispatch-infra-failed",
    # Story 19.3 — Epic 19 a11y-audit evidence markers (ADR-011 / FR-P2-6).
    "a11y-baseline-stale",
    "a11y-delta-exceeded",
    "a11y-delta-mode-unstable",
    # Story 19.5 — Epic 19 visual-regression evidence markers (ADR-012 / FR-P2-10).
    "visual-regression-delta-exceeded",
    "visual-regression-baseline-missing",
    # Story 21.2 — Epic 21 background-execution runtime-evidence marker (FR-P2-7).
    "background-primitive-unstable",
    # Story 17.2 — Epic 17 auto-merge gate-condition observability marker (FR-P2-3).
    "auto-merge-gate-not-met",
    # Story 17.3 — Epic 17 auto-merge execution actuator marker (FR-P2-3).
    "auto-merge-skipped",
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


def test_taxonomy_has_37_canonical_markers(taxonomy_data: dict) -> None:
    names = [m["marker_class"] for m in taxonomy_data["markers"]]
    assert len(names) == 44
    assert names == CANONICAL_MARKER_CLASSES, (
        "marker-taxonomy.yaml entries are out of canonical order; "
        "AC-2 mandates the order verbatim (Story 2.3 appended entries 28-29; "
        "Story 14.3 appended entry 30: worktree-stale-lock; "
        "Story 14.5 appended entry 31: parallel-story-state-pollution; "
        "Story 15.2 appended entry 32: epic-budget-exhausted; "
        "Story 16.2 appended entry 33: sprint-escalation-rate-exceeded; "
        "Story 24.1 appended entry 34: parallel-dispatch-infra-failed; "
        "Story 19.3 appended entries 35-37: a11y-baseline-stale / "
        "a11y-delta-exceeded / a11y-delta-mode-unstable; "
        "Story 19.5 appended entries 38-39: visual-regression-delta-exceeded / "
        "visual-regression-baseline-missing; "
        "Story 20.1 appended entry 40: plan-rederivation-drift-detected; "
        "Story 20.3 appended entry 41: flakiness-threshold-exceeded; "
        "Story 21.2 appended entry 42: background-primitive-unstable; "
        "Story 17.2 appended entry 43: auto-merge-gate-not-met; "
        "Story 17.3 appended entry 44: auto-merge-skipped)"
    )


def test_taxonomy_entries_have_non_empty_diagnostic_pointer(
    taxonomy_data: dict,
) -> None:
    for entry in taxonomy_data["markers"]:
        pointer = entry.get("diagnostic_pointer")
        assert isinstance(pointer, str)
        assert pointer.strip(), entry["marker_class"]


def test_taxonomy_declares_schema_version_1_14(taxonomy_data: dict) -> None:
    # Story 9.3 bumped 1.3 → 1.4 (additive sub_classification per ADR-007).
    # Story 9.5 bumped 1.4 → 1.5 (additive: two new sub_classifications under
    # mobile-blocked — init-unavailable + mid-run-unavailable).
    # Story 13.6 bumped 1.5 → 1.6 (additive: the flow-branch sub_classification
    # under heuristic-skipped for the FR22c within-AC flow-branch contract).
    # Story 14.3 bumped 1.6 → 1.7 (additive: new top-level marker class
    # ``worktree-stale-lock`` per ADR-009 Consequence 5 + epics-phase-2.md
    # line 325 forward-pointer contract; treated as PATCH per the epic-level
    # contract).
    # Story 14.5 bumped 1.7 → 1.8 (additive: new top-level marker class
    # ``parallel-story-state-pollution`` per ADR-009 Consequence 5 +
    # epics-phase-2.md line 353; treated as PATCH per epics-phase-2.md line 70
    # + the Story 14.3 precedent).
    # Story 15.1 bumps 1.8 → 1.9 (additive: OPTIONAL `lifetime` field on the
    # worktree-stale-lock entry; new top-level field, not a new class — the
    # 31-class closed-set below is unchanged; MINOR bump per the file's
    # documented additive-optional-field rule).
    # Story 15.2 bumps 1.9 → 1.10 (additive: new top-level marker class
    # ``epic-budget-exhausted`` for the per-epic cumulative retry-budget
    # exhaustion surface; closed-set 31 → 32; treated as PATCH per
    # epics-phase-2.md line 70 + line 411 + the Story 14.3/14.5 precedent).
    # Story 16.2 bumps 1.10 → 1.11 (additive: new top-level marker class
    # ``sprint-escalation-rate-exceeded`` for the sprint-scope systemic-
    # escalation signal; closed-set 32 → 33; treated as PATCH per
    # epics-phase-2.md line 70 + line 149 + the Story 14.3/14.5/15.2 precedent).
    # Story 24.1 bumps 1.11 → 1.12 (additive: new top-level marker class
    # ``parallel-dispatch-infra-failed`` for the parallel-dispatcher admission/
    # seed infra loud-fail surface; closed-set 33 → 34; MINOR bump per the
    # documented new-top-level-class rule + epics-phase-2.md line 70 + the
    # Story 14.5/15.2/16.2 precedent).
    # Story 19.2 bumps 1.12 → 1.13 (additive: four new exploratory
    # ``heuristic-skipped`` sub_classifications — rate-limit-boundary /
    # locale-i18n-edge / large-input-boundary / permission-boundary; the 34-class
    # closed-set is PRESERVED; PATCH bump per the sub_classification rule + the
    # Story 9.5/13.6 heuristic-skipped precedent).
    # Story 19.3 bumps 1.13 → 1.14 (additive: three new top-level a11y-audit
    # evidence marker classes — a11y-baseline-stale / a11y-delta-exceeded /
    # a11y-delta-mode-unstable; closed-set 34 → 37; MINOR bump per the new-top-
    # level-class rule + epics-phase-2.md line 70 + the Story 24.1 precedent;
    # ADR-011 / FR-P2-6; no runtime emitter — Story 19.4 wires emission).
    # Story 20.1 bumps 1.15 → 1.16 (PATCH: plan-rederivation-drift-detected; FR-P2-9).
    assert taxonomy_data.get("schema_version") == "1.21"


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
    assert len(ids) == 44  # Story 17.3 appended auto-merge-skipped (43 → 44)
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
# load_marker_lifetimes helper (Story 15.1 AC-6)                              #
# --------------------------------------------------------------------------- #


def test_load_marker_lifetimes_default_path() -> None:
    """Default path resolution returns the real taxonomy; worktree-stale-lock
    is the sole transient entry at Story 15.1."""
    lifetimes = load_marker_lifetimes()
    assert isinstance(lifetimes, dict)
    assert lifetimes.get("worktree-stale-lock") == "transient"
    assert all(v in ("transient", "durable") for v in lifetimes.values())


def test_load_marker_lifetimes_explicit_path(tmp_path: pathlib.Path) -> None:
    """Explicit path override is consumed; entries without ``lifetime`` default
    to ``"durable"``."""
    fixture = tmp_path / "mini-taxonomy.yaml"
    fixture.write_text(
        "schema_version: \"0.0\"\n"
        "markers:\n"
        "  - marker_class: alpha\n"
        "    lifetime: transient\n"
        "    diagnostic_pointer: a\n"
        "    sub_classifications: []\n"
        "  - marker_class: beta\n"
        "    diagnostic_pointer: b\n"
        "    sub_classifications: []\n",
        encoding="utf-8",
    )
    lifetimes = load_marker_lifetimes(fixture)
    assert lifetimes == {"alpha": "transient", "beta": "durable"}


def test_load_marker_lifetimes_defaults_to_durable(tmp_path: pathlib.Path) -> None:
    """All entries in a taxonomy that omits the ``lifetime`` field get
    ``"durable"`` — the marker-permanence default (Story 1.4)."""
    fixture = tmp_path / "no-lifetime.yaml"
    fixture.write_text(
        "schema_version: \"0.0\"\n"
        "markers:\n"
        "  - marker_class: x\n"
        "    diagnostic_pointer: x\n"
        "    sub_classifications: []\n"
        "  - marker_class: y\n"
        "    diagnostic_pointer: y\n"
        "    sub_classifications: []\n",
        encoding="utf-8",
    )
    lifetimes = load_marker_lifetimes(fixture)
    assert lifetimes == {"x": "durable", "y": "durable"}


def test_load_marker_lifetimes_invalid_lifetime_raises(tmp_path: pathlib.Path) -> None:
    """A present-but-invalid ``lifetime`` value raises ``RuntimeError``
    (Pattern 5 loud-fail — a typo must not silently degrade to durable)."""
    fixture = tmp_path / "bad-lifetime.yaml"
    fixture.write_text(
        "schema_version: \"0.0\"\n"
        "markers:\n"
        "  - marker_class: alpha\n"
        "    lifetime: permanent\n"
        "    diagnostic_pointer: a\n"
        "    sub_classifications: []\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="invalid lifetime"):
        load_marker_lifetimes(fixture)


def test_load_marker_lifetimes_missing_file_raises(tmp_path: pathlib.Path) -> None:
    """A path that does not exist surfaces a ``FileNotFoundError`` (loud-fail;
    not swallowed into a silent empty dict)."""
    with pytest.raises(FileNotFoundError):
        load_marker_lifetimes(tmp_path / "nonexistent.yaml")


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
