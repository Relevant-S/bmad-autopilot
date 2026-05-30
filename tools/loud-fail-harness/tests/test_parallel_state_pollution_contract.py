"""Contract/shape witness for Story 14.5 ``parallel-story-state-pollution``.

This is a PRE-PROVISION witness — it pins the shared-state-surface inventory,
the positive/negative fixture pair, and the taxonomy↔fixture sub-classification
coherence so Epic 18 Story 18.2 can wire detection without re-touching the
contract. It imports NO production detector (there is none yet) and exercises
NO runtime emission; it is a pure data-shape assertion.
"""

from __future__ import annotations

import pathlib

import yaml

_TESTS_DIR = pathlib.Path(__file__).resolve().parent
_FIXTURE_DIR = _TESTS_DIR / "fixtures" / "parallel-state-pollution"
_TAXONOMY_PATH = _TESTS_DIR.parents[2] / "schemas" / "marker-taxonomy.yaml"

_MARKER_CLASS = "parallel-story-state-pollution"

# colliding_surface value -> the worktree field that collision lands on
_SURFACE_FIELD = {
    "shared-port": "allocated_port",
    "shared-evidence-root": "evidence_subpath",
    "aggregate-run-state": "aggregate_claim_story_id",
}
# colliding_surface value -> the taxonomy sub_classification it sub-classifies to
_SURFACE_SUBCLASS = {
    "shared-port": "shared-port-collision",
    "shared-evidence-root": "shared-evidence-root-collision",
    "aggregate-run-state": "aggregate-run-state-cross-write",
}


def _load_yaml(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _surface_values(worktree: dict) -> tuple:
    return (
        worktree["allocated_port"],
        worktree["evidence_subpath"],
        worktree["aggregate_claim_story_id"],
    )


def test_both_fixtures_parse_as_yaml() -> None:
    clean = _load_yaml(_FIXTURE_DIR / "clean-parallel-state.yaml")
    polluted = _load_yaml(_FIXTURE_DIR / "polluted-parallel-state.yaml")
    assert isinstance(clean, dict)
    assert isinstance(polluted, dict)
    assert clean["parallel_stories"] is True
    assert polluted["parallel_stories"] is True
    assert len(clean["worktrees"]) == 2
    assert len(polluted["worktrees"]) == 2


def test_clean_fixture_surface_claims_are_pairwise_disjoint() -> None:
    """Positive invariant: no shared-surface field coincides across the two
    worktrees, so no per-surface collision predicate fires."""
    clean = _load_yaml(_FIXTURE_DIR / "clean-parallel-state.yaml")
    assert clean["expected_marker"] is None
    wt_a, wt_b = clean["worktrees"]
    for value_a, value_b in zip(_surface_values(wt_a), _surface_values(wt_b)):
        assert value_a != value_b


def test_polluted_fixture_collides_on_declared_surface() -> None:
    """Negative invariant: the two worktrees collide on the declared surface's
    field, and the fixture declares the colliding surface explicitly."""
    polluted = _load_yaml(_FIXTURE_DIR / "polluted-parallel-state.yaml")
    assert polluted["expected_marker"] == _MARKER_CLASS

    surface = polluted["colliding_surface"]
    assert surface in _SURFACE_FIELD, f"unknown colliding_surface: {surface}"

    field = _SURFACE_FIELD[surface]
    wt_a, wt_b = polluted["worktrees"]
    assert wt_a[field] == wt_b[field], (
        f"polluted fixture must collide on {field} for surface {surface}"
    )

    context = polluted["collision_context"]
    assert context["story_id"] != context["conflicting_story_id"]
    assert context["shared_surface"] == surface


def _taxonomy_entry(marker_class: str) -> dict:
    taxonomy = _load_yaml(_TAXONOMY_PATH)
    for entry in taxonomy["markers"]:
        if entry["marker_class"] == marker_class:
            return entry
    raise AssertionError(f"{marker_class} not enumerated in marker-taxonomy.yaml")


def test_taxonomy_fixture_subclassification_coherence() -> None:
    """Taxonomy↔fixture coherence: the marker is enumerated, and the polluted
    fixture's declared sub-classification is one of the three enumerated
    sub_classifications."""
    entry = _taxonomy_entry(_MARKER_CLASS)
    enumerated = set(entry["sub_classifications"])
    assert enumerated == {
        "shared-port-collision",
        "shared-evidence-root-collision",
        "aggregate-run-state-cross-write",
    }

    polluted = _load_yaml(_FIXTURE_DIR / "polluted-parallel-state.yaml")
    declared = polluted["expected_sub_classification"]
    assert declared in enumerated
    surface = polluted["colliding_surface"]
    assert surface in _SURFACE_SUBCLASS, f"unknown colliding_surface: {surface!r}"
    assert _SURFACE_SUBCLASS[surface] == declared


def test_taxonomy_entry_declares_all_placeholder_context_fields() -> None:
    """Every {placeholder} in diagnostic_pointer is declared in
    pointer_context_fields (forward-reference for Epic 18 Story 18.2)."""
    entry = _taxonomy_entry(_MARKER_CLASS)
    assert entry["pointer_context_fields"] == [
        "story_id",
        "conflicting_story_id",
        "shared_surface",
    ]
