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


def test_taxonomy_schema_version_is_1_4(taxonomy_data: dict) -> None:
    """Story 9.3 bumps schema_version from ``"1.3"`` to ``"1.4"`` per
    the file's own PATCH-bump rule (additive: one new sub_classification
    ``mobile-mcp-init-unreachable`` appended under ``env-setup-failed``
    for Phase 1.5 mobile-mcp activation per ADR-007). The top-level
    27-class closed-set is preserved; no MAJOR bump per
    ``epics-phase-1.5.md`` line 120.
    """
    assert taxonomy_data.get("schema_version") == "1.4"


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
