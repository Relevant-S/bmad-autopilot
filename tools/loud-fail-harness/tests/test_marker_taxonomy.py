"""Story 6.2 — marker-taxonomy contract tests.

Verifies the structural invariants the per-entry ``pointer_context_fields``
field codifies (Story 6.2 AC-3) — every marker class has a non-empty
``diagnostic_pointer`` (Story 1.4 contract); every marker class declares
a ``pointer_context_fields`` list (possibly ``[]`` for context-free
classes); placeholder names in ``diagnostic_pointer`` text round-trip
with declared ``pointer_context_fields`` entries (no orphan placeholders;
no unused declared fields).
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml


@pytest.fixture(scope="module")
def taxonomy_path() -> pathlib.Path:
    """Resolve the canonical taxonomy file relative to the harness tree.
    Mirrors the resolution used in ``test_reconciler.py`` /
    ``test_qa_evidence_tier.py``.
    """
    return (
        pathlib.Path(__file__).resolve().parents[3]
        / "schemas"
        / "marker-taxonomy.yaml"
    )


@pytest.fixture(scope="module")
def taxonomy_data(taxonomy_path: pathlib.Path) -> dict:
    return yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))


def _placeholders_in(text: str) -> set[str]:
    """Extract ``{name}`` placeholders from a ``diagnostic_pointer``
    template. Uses ``\\w+`` so identifiers with hyphens (e.g.
    ``{story-id}``) — which are illegal Python ``str.format`` field
    names — are NOT matched and don't count as placeholders.
    """
    return set(re.findall(r"\{(\w+)\}", text))


def test_taxonomy_schema_version_is_1_14(taxonomy_data: dict) -> None:
    """Story 19.3 bumps schema_version from ``"1.13"`` to ``"1.14"`` for the
    three new top-level a11y-audit evidence marker classes
    (``a11y-baseline-stale`` / ``a11y-delta-exceeded`` /
    ``a11y-delta-mode-unstable``; ADR-011 / FR-P2-6). MINOR bump per the
    documented new-top-level-class rule + epics-phase-2.md line 70 + the Story
    24.1 (1.11 → 1.12) new-Phase-2-class-as-MINOR precedent; the top-level
    closed-set grows 34 → 37. Prior Story 19.2 bumped 1.12 → 1.13 (PATCH) for
    the four new exploratory ``heuristic-skipped`` sub_classifications.
    """
    # Story 20.1 (FR-P2-9) bumps 1.15 → 1.16 (PATCH) for the new top-level
    # plan-rederivation-drift-detected class (closed-set 39 → 40).
    assert taxonomy_data.get("schema_version") == "1.16"


def test_a11y_marker_classes_enumerated(taxonomy_data: dict) -> None:
    """Story 19.3 AC-4 / AC-8b: the three a11y-audit evidence marker classes are
    enumerated as top-level classes with non-empty ``diagnostic_pointer``, the
    exact ``pointer_context_fields`` shapes (``[ac_id]`` / ``[ac_id]`` / ``[]``),
    empty ``sub_classifications``, and (by omission) the durable default lifetime
    so they survive the Story 15.1 transient write-back filter. The closed-set is
    exactly 37. Runtime emission is Story 19.4's (NO emitter lands here).
    """
    by_class = {entry["marker_class"]: entry for entry in taxonomy_data["markers"]}
    expected_pointer_fields = {
        "a11y-baseline-stale": ["ac_id"],
        "a11y-delta-exceeded": ["ac_id"],
        "a11y-delta-mode-unstable": [],
    }
    for marker_class, fields in expected_pointer_fields.items():
        assert marker_class in by_class, f"taxonomy missing {marker_class}"
        entry = by_class[marker_class]
        assert entry["diagnostic_pointer"].strip(), (
            f"{marker_class}: diagnostic_pointer must be non-empty"
        )
        assert entry["pointer_context_fields"] == fields, (
            f"{marker_class}: pointer_context_fields drifted"
        )
        assert entry["sub_classifications"] == [], (
            f"{marker_class}: sub_classifications must be empty"
        )
        assert "lifetime" not in entry, (
            f"{marker_class}: must inherit the durable default (no lifetime field)"
        )
    # Story 20.1 appended plan-rederivation-drift-detected (39 → 40).
    assert len(taxonomy_data["markers"]) == 40


def test_visual_regression_marker_classes_enumerated(taxonomy_data: dict) -> None:
    """Story 19.5 AC-3: the two visual-regression evidence marker classes are
    enumerated as top-level classes with non-empty ``diagnostic_pointer``, both
    AC-scoped (``pointer_context_fields: [ac_id]``), empty ``sub_classifications``,
    and (by omission) the durable default lifetime. The closed-set is exactly 39,
    schema_version is ``1.15``. Unlike a11y (19.3 enumerate → 19.4 emit), runtime
    emission lands in THIS story — no flip-the-switch split — and there is NO
    third ``-mode-unstable`` class (pixel-diff is deterministic).
    """
    assert taxonomy_data["schema_version"] == "1.16"
    by_class = {entry["marker_class"]: entry for entry in taxonomy_data["markers"]}
    for marker_class in (
        "visual-regression-delta-exceeded",
        "visual-regression-baseline-missing",
    ):
        assert marker_class in by_class, f"taxonomy missing {marker_class}"
        entry = by_class[marker_class]
        assert entry["diagnostic_pointer"].strip(), (
            f"{marker_class}: diagnostic_pointer must be non-empty"
        )
        assert entry["pointer_context_fields"] == ["ac_id"], (
            f"{marker_class}: must be AC-scoped ([ac_id])"
        )
        assert entry["sub_classifications"] == [], (
            f"{marker_class}: sub_classifications must be empty"
        )
        assert "lifetime" not in entry, (
            f"{marker_class}: must inherit the durable default (no lifetime field)"
        )
    # No third -mode-unstable class (pixel-diff is deterministic; dimension
    # mismatch folds into delta-exceeded).
    assert "visual-regression-mode-unstable" not in by_class
    assert len(taxonomy_data["markers"]) == 40


def test_worktree_stale_lock_declares_transient_lifetime(
    taxonomy_data: dict,
) -> None:
    """Story 15.1 AC-6: the ``worktree-stale-lock`` entry — and ONLY it —
    carries ``lifetime: transient``; the field is the structural source of
    the transient/durable axis the epic-run-state write-back filter
    consults at runtime (no hardcoded class list).
    """
    by_class = {entry["marker_class"]: entry for entry in taxonomy_data["markers"]}
    assert by_class["worktree-stale-lock"].get("lifetime") == "transient"


def test_lifetime_field_is_optional_and_defaults_durable(
    taxonomy_data: dict,
) -> None:
    """Story 15.1 AC-6: ``lifetime`` is an OPTIONAL field — every entry
    other than ``worktree-stale-lock`` omits it (inheriting the ``durable``
    default), preserving the Story 1.4 marker-permanence rule for durable
    markers. Any entry that DOES declare ``lifetime`` declares one of the
    two closed-enum values.
    """
    for entry in taxonomy_data["markers"]:
        marker_class = entry["marker_class"]
        if "lifetime" not in entry:
            continue
        assert entry["lifetime"] in {"transient", "durable"}, (
            f"{marker_class}: lifetime must be 'transient' or 'durable'"
        )
        if marker_class != "worktree-stale-lock":
            assert entry["lifetime"] == "durable", (
                f"{marker_class}: only worktree-stale-lock is transient at "
                f"Story 15.1; an explicit lifetime here must be 'durable'"
            )


def test_epic_budget_exhausted_entry_shape(taxonomy_data: dict) -> None:
    """Story 15.2 AC-5: ``epic-budget-exhausted`` is enumerated as a new
    top-level marker class with the budget-context pointer fields, an empty
    sub_classifications list, and (by omission) the durable default lifetime so
    it survives the Story 15.1 transient write-back filter."""
    by_class = {entry["marker_class"]: entry for entry in taxonomy_data["markers"]}
    assert "epic-budget-exhausted" in by_class, (
        "taxonomy missing the epic-budget-exhausted marker class"
    )
    entry = by_class["epic-budget-exhausted"]
    assert entry["pointer_context_fields"] == [
        "epic_id",
        "run_id",
        "consumed",
        "effective_budget",
    ]
    assert entry["sub_classifications"] == []
    assert "lifetime" not in entry  # durable by default → never stripped
    assert entry["diagnostic_pointer"].strip()


def test_heuristic_skipped_declares_flow_branch_sub_classification(
    taxonomy_data: dict,
) -> None:
    """FR22c / Story 13.6 + ADR-010 / Story 19.2: the ``heuristic-skipped``
    marker class declares the 8-value sub_classification set — the seven
    exploratory ``HeuristicKind`` values (``empty-state`` / ``error-state`` /
    ``auth-boundary`` MVP trio + the four Story 19.2 additions
    ``rate-limit-boundary`` / ``locale-i18n-edge`` / ``large-input-boundary`` /
    ``permission-boundary``, inserted after ``auth-boundary``) followed by the
    unchanged ``flow-branch`` (FR22c, kept LAST). This pins both the Story 13.6
    ``flow-branch`` addition and the Story 19.2 expansion, plus the
    insert-before-flow-branch, no-reorder discipline (the seven exploratory
    values stay contiguous and ``flow-branch`` stays terminal).
    """
    by_class = {
        entry["marker_class"]: entry for entry in taxonomy_data["markers"]
    }
    assert "heuristic-skipped" in by_class, (
        "taxonomy missing the heuristic-skipped marker class"
    )
    assert by_class["heuristic-skipped"]["sub_classifications"] == [
        "empty-state",
        "error-state",
        "auth-boundary",
        "rate-limit-boundary",
        "locale-i18n-edge",
        "large-input-boundary",
        "permission-boundary",
        "flow-branch",
    ]


def test_every_marker_has_non_empty_diagnostic_pointer(
    taxonomy_data: dict,
) -> None:
    """AC-3 / Story 1.4 contract verified at runtime: every marker
    class has a non-empty ``diagnostic_pointer`` field (string,
    length ≥ 1).
    """
    for entry in taxonomy_data["markers"]:
        marker_class = entry.get("marker_class")
        diagnostic = entry.get("diagnostic_pointer")
        assert isinstance(diagnostic, str), (
            f"{marker_class}: diagnostic_pointer must be a string, "
            f"got {type(diagnostic).__name__}"
        )
        assert diagnostic.strip(), (
            f"{marker_class}: diagnostic_pointer must be non-empty"
        )


def test_every_marker_declares_pointer_context_fields(
    taxonomy_data: dict,
) -> None:
    """AC-3: every marker class has a ``pointer_context_fields`` field
    (the schema's new contract), possibly ``[]``.
    """
    for entry in taxonomy_data["markers"]:
        marker_class = entry.get("marker_class")
        assert "pointer_context_fields" in entry, (
            f"{marker_class}: missing pointer_context_fields field"
        )
        fields = entry["pointer_context_fields"]
        assert isinstance(fields, list), (
            f"{marker_class}: pointer_context_fields must be a list, "
            f"got {type(fields).__name__}"
        )
        for field_name in fields:
            assert isinstance(field_name, str) and field_name, (
                f"{marker_class}: each pointer_context_fields entry "
                f"must be a non-empty string"
            )


def test_declared_fields_appear_as_placeholders_in_diagnostic_pointer(
    taxonomy_data: dict,
) -> None:
    """AC-3: for each marker with non-empty ``pointer_context_fields``,
    every declared field name appears at least once as ``{field}`` in
    the ``diagnostic_pointer`` text. Structural consistency check.
    """
    for entry in taxonomy_data["markers"]:
        marker_class = entry.get("marker_class")
        fields = set(entry.get("pointer_context_fields") or [])
        if not fields:
            continue
        placeholders = _placeholders_in(entry["diagnostic_pointer"])
        missing = fields - placeholders
        assert not missing, (
            f"{marker_class}: pointer_context_fields {sorted(missing)} "
            f"not present as placeholders in diagnostic_pointer"
        )


def test_no_orphan_placeholders_in_diagnostic_pointer(
    taxonomy_data: dict,
) -> None:
    """AC-3 inverse consistency check: for each ``{placeholder}`` in
    ``diagnostic_pointer``, the placeholder name appears in
    ``pointer_context_fields``. Prevents drift where prose gains a
    ``{field}`` without the structured declaration.
    """
    for entry in taxonomy_data["markers"]:
        marker_class = entry.get("marker_class")
        fields = set(entry.get("pointer_context_fields") or [])
        placeholders = _placeholders_in(entry["diagnostic_pointer"])
        orphans = placeholders - fields
        assert not orphans, (
            f"{marker_class}: orphan {{placeholders}} {sorted(orphans)} "
            f"in diagnostic_pointer not declared in pointer_context_fields"
        )


def test_three_enriched_classes_have_expected_pointer_context_fields(
    taxonomy_data: dict,
) -> None:
    """AC-3 / AC-5: the three verbatim-named-by-AC enriched marker
    classes have the exact ``pointer_context_fields`` shapes specified
    in the BOUNDED specification.
    """
    expected: dict[str, list[str]] = {
        "Tier-3-not-configured": ["ac_id"],
        "playwright-mcp-unavailable": ["project_type", "version_range"],
        "specialist-timeout": ["specialist", "timeout_seconds"],
    }
    by_class = {entry["marker_class"]: entry for entry in taxonomy_data["markers"]}
    for marker_class, fields in expected.items():
        assert marker_class in by_class, (
            f"taxonomy missing the enriched class {marker_class}"
        )
        assert by_class[marker_class]["pointer_context_fields"] == fields, (
            f"{marker_class}: pointer_context_fields shape drifted from "
            f"the BOUNDED specification"
        )


def test_three_enriched_classes_template_interpolates_against_seeded_context(
    taxonomy_data: dict,
) -> None:
    """AC-1 / AC-3: each enriched class's ``diagnostic_pointer``, when
    interpolated against a seeded context, produces text containing the
    seeded values and NO surviving ``{placeholder}`` literals — the
    end-to-end interpolation contract for the witness set.
    """
    by_class = {entry["marker_class"]: entry for entry in taxonomy_data["markers"]}
    seeds: dict[str, dict[str, str]] = {
        "Tier-3-not-configured": {"ac_id": "AC-7"},
        "playwright-mcp-unavailable": {
            "project_type": "web",
            "version_range": ">=0.0.27,<0.1",
        },
        "specialist-timeout": {
            "specialist": "qa",
            "timeout_seconds": "120",
        },
    }
    for marker_class, context in seeds.items():
        template = by_class[marker_class]["diagnostic_pointer"]
        interpolated = template.format(**context)
        for value in context.values():
            assert value in interpolated, (
                f"{marker_class}: interpolated text missing seeded value {value!r}"
            )
        # Structural invariant: no surviving {field} placeholders for
        # enriched classes after interpolation.
        for field_name in context:
            assert "{" + field_name + "}" not in interpolated
