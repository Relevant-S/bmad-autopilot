"""Contract-coverage matrix for substrate component 4 (cross-schema enumeration_check).

This docstring IS the contract-coverage checklist required by AC-6. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to story 1.2 / 1.3 / 1.4 AC-5).

Pure-API classification cases (AC-1, AC-3, AC-4, AC-5):
    [x] valid full match                                         → test_valid_full_match
    [x] missing marker_class reference                           → test_missing_marker_class_reference
    [x] orphan marker class                                      → test_orphan_marker_class
    [x] removed-from-taxonomy lists EVERY dangling reference     → test_removed_from_taxonomy_lists_every_dangling_reference

Strict-name discovery rule (AC-1 false-positive prevention):
    [x] escalation_class.enum collision is NOT a reference       → test_strict_name_discovery_does_not_match_escalation_class
    [x] outcome.enum collision is NOT a reference                → test_strict_name_discovery_does_not_match_outcome
    [x] event_class.const collision is NOT a reference           → test_strict_name_discovery_does_not_match_event_class

Strict-name discovery (positive — three documented value shapes):
    [x] direct-string marker_class value                         → test_discovery_direct_string_value
    [x] const-wrapped marker_class value                         → test_discovery_const_wrapped_value
    [x] enum-wrapped marker_class values (list)                  → test_discovery_enum_wrapped_values
    [x] emits_marker direct string (SDN-001 sub_classification)  → test_discovery_emits_marker_direct_string

Dependencies.yaml absent / present (AC-2):
    [x] dependencies.yaml absent → graceful skip + summary note  → test_dependencies_yaml_absent_does_not_fail
    [x] dependencies.yaml present (SDN-001 shape) → both fields  → test_dependencies_yaml_present_picks_up_marker_class_and_emits_marker

Loud-fail / harness-level errors (AC-6 case 9, Pattern 5):
    [x] malformed taxonomy (missing markers key) → exit 2        → test_loud_fail_on_malformed_taxonomy
    [x] taxonomy entry missing marker_class → exit 2             → test_loud_fail_on_taxonomy_entry_missing_marker_class
    [x] malformed event-schema YAML → exit 2                     → test_loud_fail_on_malformed_event_schema_yaml
    [x] dependencies.yaml YAML parse error → exit 2              → test_loud_fail_on_malformed_dependencies_yaml

Determinism (AC-3 + AC-5):
    [x] orphan ordering is lexicographically sorted              → test_orphan_ordering_lexicographic
    [x] missing-reference ordering by (file, pointer)            → test_missing_ordering_by_file_and_pointer
    [x] CheckResult is byte-stable across two invocations        → test_orphan_ordering_deterministic_across_invocations
    [x] CheckResult.model_dump_json byte-identical for shuffled  → test_determinism_under_shuffle

Pydantic v2 frozen-model discipline:
    [x] Reference is frozen (assignment raises)                  → test_reference_is_frozen
    [x] CheckResult is frozen (assignment raises)                → test_check_result_is_frozen
    [x] Reference rejects unknown discovery_kind                 → test_reference_rejects_unknown_discovery_kind

CLI / main exit-code matrix (AC-3 + AC-4 + AC-8):
    [x] exit 0 on all-passing input                              → test_main_exits_zero_on_passing_input
    [x] exit 1 on missing reference                              → test_main_exits_one_on_missing_reference
    [x] exit 1 lists EVERY missing reference (do not bail first) → test_main_exit_one_lists_every_missing_reference
    [x] exit 2 on harness error                                  → test_main_exits_two_on_harness_error

Stdout shape (AC-2 / AC-3 / AC-5):
    [x] absent-deferral note present when dependencies missing   → test_stdout_absent_deferral_note
    [x] absent-deferral note suppressed when dependencies present → test_stdout_no_deferral_note_when_dependencies_present
    [x] orphan section header present when orphans non-empty     → test_stdout_orphan_section_header
    [x] missing-reference ERROR section names file + pointer     → test_stdout_missing_reference_names_file_and_pointer
    [x] format_findings header present unconditionally           → test_format_findings_header_present

Default-path resolution + uncommon harness-error paths:
    [x] main() with no flags resolves canonical schemas          → test_main_with_no_flags_resolves_canonical_schemas
    [x] taxonomy YAML parse failure (not just missing key)       → test_main_yaml_error_on_taxonomy_returns_two
    [x] event-schema OSError (directory path)                    → test_main_oserror_on_event_schema_returns_two
    [x] dependencies.yaml OSError (directory path, NOT absent)   → test_main_oserror_on_dependencies_returns_two

Performance (AC-1 + AC-6 case 8):
    [x] enumeration_check < 1.0s on canonical schemas            → test_check_completes_under_one_second_on_canonical_schemas (@pytest.mark.performance)

Review-patch additions (code review 2026-04-26):
    [x] null marker_class in taxonomy → exit 2                   → test_loud_fail_on_null_marker_class_in_taxonomy
    [x] non-dict dependencies.yaml (valid YAML) → exit 2         → test_loud_fail_on_non_dict_dependencies_yaml

Escalation-bundles directory reconciliation (Story 4.10):
    [x] absent dir → graceful skip + deferral note               → test_escalation_bundles_directory_absent_clean_skip
    [x] empty dir → clean skip, NO deferral note                 → test_escalation_bundles_directory_empty_clean_skip
    [x] real contracts → 4 references resolve cleanly            → test_escalation_bundles_directory_with_clean_contracts_passes
    [x] missing-marker reference in contract → exit 1            → test_escalation_bundles_contract_with_missing_marker_reference_fails
    [x] malformed YAML in contract → exit 2                      → test_escalation_bundles_contract_yaml_parse_failure_yields_harness_error
    [x] non-mapping YAML in contract → exit 2                    → test_escalation_bundles_contract_non_mapping_yields_harness_error
    [x] CLI flag overrides default escalation-bundles-dir        → test_escalation_bundles_dir_cli_flag_overrides_default
    [x] both optional pairs absent → both deferral notes printed → test_dependencies_absent_AND_escalation_bundles_absent_clean_skip

Coverage (AC-6):
    [x] enumeration_check.py module-level statement coverage ≥ 90% → review-enforced; not a CI gate
"""

from __future__ import annotations

import io
import pathlib
import random
import time
from contextlib import redirect_stderr, redirect_stdout

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.enumeration_check import (
    CheckResult,
    Reference,
    check_enumeration,
    discover_marker_class_references,
    format_findings,
    main,
)


REPO_ROOT = find_repo_root()
CANONICAL_TAXONOMY_PATH = REPO_ROOT / "schemas" / "marker-taxonomy.yaml"
CANONICAL_EVENT_SCHEMA_PATH = REPO_ROOT / "schemas" / "orchestrator-event.yaml"


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _write_yaml(path: pathlib.Path, data: object) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _minimal_event_schema(extra_classes: list[dict] | None = None) -> dict:
    """Build a minimal-but-valid JSON Schema 2020-12 event-schema dict.

    Tests inject per-class branches via ``extra_classes`` to exercise the
    discovery walker without needing the full canonical schema. The shape
    here matches the canonical orchestrator-event.yaml's discriminated-union
    pattern (top-level oneOf + per-class properties.event_class.const).
    """
    base_class = {
        "type": "object",
        "additionalProperties": False,
        "required": ["event_class"],
        "properties": {
            "event_class": {"const": "specialist-dispatched"},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["event_class"],
        "properties": {
            "event_class": {"type": "string"},
        },
        "oneOf": [base_class, *(extra_classes or [])],
    }


def _write_taxonomy(path: pathlib.Path, marker_classes: list[str]) -> None:
    _write_yaml(
        path,
        {
            "schema_version": "1.0",
            "markers": [
                {
                    "marker_class": mc,
                    "diagnostic_pointer": f"synthetic pointer for {mc}",
                    "sub_classifications": [],
                }
                for mc in marker_classes
            ],
        },
    )


def _bare_run(
    tmp_path: pathlib.Path,
    *,
    taxonomy_path: pathlib.Path,
    event_schema_path: pathlib.Path,
    dependencies_path: pathlib.Path | None = None,
    escalation_bundles_dir: pathlib.Path | None = None,
) -> tuple[int, str, str]:
    """Invoke main() with the four CLI test-injection flags and capture streams.

    ``dependencies_path`` may point at a non-existent file (the absent path)
    or an existing one (the present path); main() handles both per AC-2.

    ``escalation_bundles_dir`` (Story 4.10) defaults to a non-existent
    tmp_path so the canonical repo's `schemas/escalation-bundles/` directory
    does NOT leak into Story-1.5-era tests; tests that need to exercise the
    escalation-bundles pair pass an explicit value.
    """
    deps_path = dependencies_path or (tmp_path / "definitely-absent-dependencies.yaml")
    escalation_bundles = escalation_bundles_dir or (
        tmp_path / "definitely-absent-escalation-bundles"
    )
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main(
            [
                "--taxonomy-path",
                str(taxonomy_path),
                "--event-schema-path",
                str(event_schema_path),
                "--dependencies-path",
                str(deps_path),
                "--escalation-bundles-dir",
                str(escalation_bundles),
            ]
        )
    return rc, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------------- #
# Pure-API classification cases                                               #
# --------------------------------------------------------------------------- #


def test_valid_full_match(tmp_path: pathlib.Path) -> None:
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    _write_taxonomy(taxonomy_path, ["a", "b", "c"])
    _write_yaml(
        event_schema_path,
        _minimal_event_schema(
            [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["event_class", "marker_class"],
                    "properties": {
                        "event_class": {"const": "marker-emitted"},
                        "marker_class": {"const": "a"},
                    },
                }
            ]
        ),
    )
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 0
    assert "Summary: 1 passing reference(s), 0 missing reference(s)" in out
    # Orphan list contains the two unreferenced taxonomy entries.
    assert "  - b: " in out
    assert "  - c: " in out
    assert "  - a:" not in out


def test_missing_marker_class_reference(tmp_path: pathlib.Path) -> None:
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    _write_taxonomy(taxonomy_path, ["a", "b"])
    _write_yaml(
        event_schema_path,
        _minimal_event_schema(
            [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["event_class", "marker_class"],
                    "properties": {
                        "event_class": {"const": "marker-emitted"},
                        "marker_class": {"const": "nonexistent"},
                    },
                }
            ]
        ),
    )
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 1
    assert "nonexistent" in out
    assert "/oneOf/1/properties/marker_class/const" in out
    assert "ERROR:" in out
    assert "Remediation:" in out


def test_orphan_marker_class(tmp_path: pathlib.Path) -> None:
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    _write_taxonomy(taxonomy_path, ["a", "b", "c"])
    _write_yaml(
        event_schema_path,
        _minimal_event_schema(
            [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["event_class", "marker_class"],
                    "properties": {
                        "event_class": {"const": "marker-emitted"},
                        "marker_class": {"const": "a"},
                    },
                }
            ]
        ),
    )
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 0
    assert "Orphan marker classes (warn-level — allowed but flagged):" in out
    # "b" appears before "c" lexicographically AND only those two are orphans.
    b_idx = out.index("  - b: ")
    c_idx = out.index("  - c: ")
    assert b_idx < c_idx
    assert "  - a: " not in out  # "a" is referenced and therefore not orphan


def test_removed_from_taxonomy_lists_every_dangling_reference(
    tmp_path: pathlib.Path,
) -> None:
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    _write_taxonomy(taxonomy_path, ["a"])
    _write_yaml(
        event_schema_path,
        _minimal_event_schema(
            [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["event_class", "marker_class"],
                    "properties": {
                        "event_class": {"const": "marker-one"},
                        "marker_class": {"const": "removed-1"},
                    },
                },
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["event_class", "marker_class"],
                    "properties": {
                        "event_class": {"const": "marker-two"},
                        "marker_class": {"const": "removed-2"},
                    },
                },
            ]
        ),
    )
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 1
    assert "removed-1" in out
    assert "removed-2" in out
    assert "/oneOf/1/properties/marker_class/const" in out
    assert "/oneOf/2/properties/marker_class/const" in out
    assert "Summary: 0 passing reference(s), 2 missing reference(s)" in out


# --------------------------------------------------------------------------- #
# Strict-name discovery (AC-1)                                                #
# --------------------------------------------------------------------------- #


def test_strict_name_discovery_does_not_match_escalation_class(
    tmp_path: pathlib.Path,
) -> None:
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    _write_taxonomy(taxonomy_path, ["retry-budget-exhausted"])
    _write_yaml(
        event_schema_path,
        _minimal_event_schema(
            [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["event_class", "escalation_class"],
                    "properties": {
                        "event_class": {"const": "escalation-fired"},
                        "escalation_class": {
                            "type": "string",
                            "enum": ["retry-budget-exhausted", "qa-verification-fail"],
                        },
                    },
                }
            ]
        ),
    )
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 0
    assert "Summary: 0 passing reference(s), 0 missing reference(s)" in out
    # retry-budget-exhausted is in the taxonomy but never discovered as a
    # reference, so it falls through into the orphan list.
    assert "  - retry-budget-exhausted:" in out


def test_strict_name_discovery_does_not_match_outcome(tmp_path: pathlib.Path) -> None:
    schema = {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "string",
                "enum": ["clean", "orphan-process-cleanup"],
            },
        },
    }
    refs = discover_marker_class_references(schema, "synthetic.yaml")
    assert refs == []


def test_strict_name_discovery_does_not_match_event_class(
    tmp_path: pathlib.Path,
) -> None:
    schema = {
        "type": "object",
        "properties": {
            "event_class": {"const": "cost-event"},
        },
    }
    refs = discover_marker_class_references(schema, "synthetic.yaml")
    assert refs == []


def test_discovery_direct_string_value() -> None:
    refs = discover_marker_class_references(
        {"marker_class": "env-setup-failed"}, "synthetic.yaml"
    )
    assert len(refs) == 1
    r = refs[0]
    assert r.marker_class == "env-setup-failed"
    assert r.pointer == "/marker_class"
    assert r.discovery_kind == "marker_class"
    assert r.source_file == "synthetic.yaml"


def test_discovery_const_wrapped_value() -> None:
    refs = discover_marker_class_references(
        {"properties": {"marker_class": {"const": "env-setup-failed"}}},
        "synthetic.yaml",
    )
    assert len(refs) == 1
    assert refs[0].pointer == "/properties/marker_class/const"
    assert refs[0].marker_class == "env-setup-failed"


def test_discovery_enum_wrapped_values() -> None:
    refs = discover_marker_class_references(
        {
            "properties": {
                "marker_class": {"enum": ["env-setup-failed", "mobile-blocked"]},
            }
        },
        "synthetic.yaml",
    )
    assert len(refs) == 2
    pointers = {r.pointer for r in refs}
    assert pointers == {
        "/properties/marker_class/enum/0",
        "/properties/marker_class/enum/1",
    }
    assert {r.marker_class for r in refs} == {"env-setup-failed", "mobile-blocked"}


def test_discovery_emits_marker_direct_string() -> None:
    deps = {
        "dependencies": {
            "y": {
                "profiles": {
                    "init": {
                        "sub_classifications": [{"emits_marker": "LAD-skipped"}],
                    },
                },
            },
        },
    }
    refs = discover_marker_class_references(deps, "schemas/dependencies.yaml")
    assert len(refs) == 1
    r = refs[0]
    assert r.marker_class == "LAD-skipped"
    assert r.discovery_kind == "emits_marker"
    assert (
        r.pointer
        == "/dependencies/y/profiles/init/sub_classifications/0/emits_marker"
    )


# --------------------------------------------------------------------------- #
# Dependencies.yaml absent / present (AC-2)                                   #
# --------------------------------------------------------------------------- #


def test_dependencies_yaml_absent_does_not_fail(tmp_path: pathlib.Path) -> None:
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    _write_taxonomy(taxonomy_path, ["a"])
    _write_yaml(event_schema_path, _minimal_event_schema())
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
        dependencies_path=tmp_path / "missing-deps.yaml",
    )
    assert rc == 0
    assert "schemas/dependencies.yaml not present; deferred to story 1.6" in out


def test_dependencies_yaml_present_picks_up_marker_class_and_emits_marker(
    tmp_path: pathlib.Path,
) -> None:
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    deps_path = tmp_path / "dependencies.yaml"
    _write_taxonomy(taxonomy_path, ["env-setup-failed", "LAD-skipped"])
    _write_yaml(event_schema_path, _minimal_event_schema())
    _write_yaml(
        deps_path,
        {
            "schema_version": "1.0",
            "dependencies": {
                "playwright-mcp": {
                    "by_project_type": {
                        "web": {
                            "profiles": {
                                "runtime": {"marker_class": "env-setup-failed"},
                            },
                        },
                    },
                },
                "lad-mcp": {
                    "profiles": {
                        "init": {
                            "sub_classifications": [
                                {"emits_marker": "LAD-skipped"},
                            ],
                        },
                    },
                },
            },
        },
    )
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
        dependencies_path=deps_path,
    )
    assert rc == 0
    assert "Summary: 2 passing reference(s), 0 missing reference(s)" in out
    # The deferral note must NOT appear when dependencies.yaml is present.
    assert "deferred to story 1.6" not in out


# --------------------------------------------------------------------------- #
# Loud-fail / harness-level errors (AC-6 case 9, Pattern 5)                   #
# --------------------------------------------------------------------------- #


def test_loud_fail_on_malformed_taxonomy(tmp_path: pathlib.Path) -> None:
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    # Missing the top-level `markers:` key — load_marker_taxonomy raises
    # RuntimeError naming the file path.
    _write_yaml(taxonomy_path, {"schema_version": "1.0"})
    _write_yaml(event_schema_path, _minimal_event_schema())
    rc, out, err = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 2
    combined = out + err
    assert str(taxonomy_path) in combined
    assert "malformed" in combined
    assert "markers" in combined


def test_loud_fail_on_taxonomy_entry_missing_marker_class(
    tmp_path: pathlib.Path,
) -> None:
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    _write_yaml(
        taxonomy_path,
        {
            "schema_version": "1.0",
            "markers": [{"diagnostic_pointer": "no marker_class here"}],
        },
    )
    _write_yaml(event_schema_path, _minimal_event_schema())
    rc, _, err = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 2
    assert "marker_class" in err
    assert str(taxonomy_path) in err


def test_loud_fail_on_malformed_event_schema_yaml(tmp_path: pathlib.Path) -> None:
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    _write_taxonomy(taxonomy_path, ["a"])
    event_schema_path.write_text(": :\nnot valid yaml\n", encoding="utf-8")
    rc, _, err = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 2
    assert str(event_schema_path) in err


def test_loud_fail_on_malformed_dependencies_yaml(tmp_path: pathlib.Path) -> None:
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    deps_path = tmp_path / "dependencies.yaml"
    _write_taxonomy(taxonomy_path, ["a"])
    _write_yaml(event_schema_path, _minimal_event_schema())
    deps_path.write_text("dependencies:\n  x:\n    profiles:\n  bad-indent\n", encoding="utf-8")
    rc, _, err = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
        dependencies_path=deps_path,
    )
    assert rc == 2
    assert str(deps_path) in err


# --------------------------------------------------------------------------- #
# Determinism (AC-3 + AC-5)                                                   #
# --------------------------------------------------------------------------- #


def test_orphan_ordering_lexicographic() -> None:
    taxonomy = {"zeta", "alpha", "beta"}
    result = check_enumeration(taxonomy, [])
    assert result.orphans == ["alpha", "beta", "zeta"]


def test_missing_ordering_by_file_and_pointer() -> None:
    refs = [
        Reference(
            marker_class="x",
            source_file="z.yaml",
            pointer="/p/2",
            discovery_kind="marker_class",
        ),
        Reference(
            marker_class="x",
            source_file="a.yaml",
            pointer="/p/1",
            discovery_kind="marker_class",
        ),
        Reference(
            marker_class="x",
            source_file="a.yaml",
            pointer="/p/0",
            discovery_kind="marker_class",
        ),
    ]
    result = check_enumeration(set(), refs)
    assert [r.source_file for r in result.missing] == ["a.yaml", "a.yaml", "z.yaml"]
    assert [r.pointer for r in result.missing] == ["/p/0", "/p/1", "/p/2"]


def test_orphan_ordering_deterministic_across_invocations() -> None:
    taxonomy = {"c", "a", "b"}
    refs: list[Reference] = []
    r1 = check_enumeration(taxonomy, refs)
    r2 = check_enumeration(taxonomy, refs)
    assert r1.model_dump_json() == r2.model_dump_json()


def test_determinism_under_shuffle() -> None:
    taxonomy = {f"m-{i}" for i in range(50)}
    refs = [
        Reference(
            marker_class=f"m-{i}",
            source_file=f"file-{i % 3}.yaml",
            pointer=f"/p/{i}",
            discovery_kind="marker_class",
        )
        for i in range(20)
    ]
    rng = random.Random(2026)
    shuffled = refs.copy()
    rng.shuffle(shuffled)
    r1 = check_enumeration(taxonomy, refs)
    r2 = check_enumeration(taxonomy, shuffled)
    assert r1.model_dump_json() == r2.model_dump_json()


# --------------------------------------------------------------------------- #
# Pydantic v2 frozen-model discipline                                         #
# --------------------------------------------------------------------------- #


def test_reference_is_frozen() -> None:
    r = Reference(
        marker_class="a",
        source_file="f.yaml",
        pointer="/p",
        discovery_kind="marker_class",
    )
    with pytest.raises(ValidationError):
        r.marker_class = "b"  # type: ignore[misc]


def test_check_result_is_frozen() -> None:
    r = CheckResult(passing=[], missing=[], orphans=[])
    with pytest.raises(ValidationError):
        r.passing = []  # type: ignore[misc]


def test_reference_rejects_unknown_discovery_kind() -> None:
    with pytest.raises(ValidationError):
        Reference(
            marker_class="a",
            source_file="f.yaml",
            pointer="/p",
            discovery_kind="other-thing",  # type: ignore[arg-type]
        )


# --------------------------------------------------------------------------- #
# CLI / main exit-code matrix                                                 #
# --------------------------------------------------------------------------- #


def test_main_exits_zero_on_passing_input(tmp_path: pathlib.Path) -> None:
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    _write_taxonomy(taxonomy_path, ["a"])
    _write_yaml(event_schema_path, _minimal_event_schema())
    rc, _, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 0


def test_main_exits_one_on_missing_reference(tmp_path: pathlib.Path) -> None:
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    _write_taxonomy(taxonomy_path, ["a"])
    _write_yaml(
        event_schema_path,
        _minimal_event_schema(
            [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["event_class", "marker_class"],
                    "properties": {
                        "event_class": {"const": "x"},
                        "marker_class": {"const": "missing-marker"},
                    },
                }
            ]
        ),
    )
    rc, _, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 1


def test_main_exit_one_lists_every_missing_reference(tmp_path: pathlib.Path) -> None:
    """AC-3 explicit: do NOT bail after the first missing reference."""
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    _write_taxonomy(taxonomy_path, ["only-defined"])
    _write_yaml(
        event_schema_path,
        _minimal_event_schema(
            [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["event_class", "marker_class"],
                    "properties": {
                        "event_class": {"const": "x"},
                        "marker_class": {"const": "missing-1"},
                    },
                },
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["event_class", "marker_class"],
                    "properties": {
                        "event_class": {"const": "y"},
                        "marker_class": {"const": "missing-2"},
                    },
                },
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["event_class", "marker_class"],
                    "properties": {
                        "event_class": {"const": "z"},
                        "marker_class": {"const": "missing-3"},
                    },
                },
            ]
        ),
    )
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 1
    assert "missing-1" in out
    assert "missing-2" in out
    assert "missing-3" in out
    assert "Summary: 0 passing reference(s), 3 missing reference(s)" in out


def test_main_exits_two_on_harness_error(tmp_path: pathlib.Path) -> None:
    """An unreadable taxonomy file (not a missing-reference issue) is a
    harness-level error and surfaces with exit 2 — distinct from the
    validation-failure exit 1."""
    taxonomy_path = tmp_path / "missing.yaml"  # never created
    event_schema_path = tmp_path / "events.yaml"
    _write_yaml(event_schema_path, _minimal_event_schema())
    rc, _, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 2


# --------------------------------------------------------------------------- #
# Stdout shape                                                                #
# --------------------------------------------------------------------------- #


def test_stdout_absent_deferral_note(tmp_path: pathlib.Path) -> None:
    out = format_findings(
        CheckResult(passing=[], missing=[], orphans=[]),
        dependencies_present=False,
    )
    assert "deferred to story 1.6" in out


def test_stdout_no_deferral_note_when_dependencies_present(
    tmp_path: pathlib.Path,
) -> None:
    out = format_findings(
        CheckResult(passing=[], missing=[], orphans=[]),
        dependencies_present=True,
    )
    assert "deferred to story 1.6" not in out


def test_stdout_orphan_section_header() -> None:
    out = format_findings(
        CheckResult(passing=[], missing=[], orphans=["a"]),
        dependencies_present=True,
    )
    assert "Orphan marker classes (warn-level — allowed but flagged):" in out
    assert "  - a:" in out


def test_stdout_missing_reference_names_file_and_pointer() -> None:
    ref = Reference(
        marker_class="x",
        source_file="schemas/orchestrator-event.yaml",
        pointer="/oneOf/3/properties/marker_class/const",
        discovery_kind="marker_class",
    )
    out = format_findings(
        CheckResult(passing=[], missing=[ref], orphans=[]),
        dependencies_present=True,
    )
    assert "ERROR:" in out
    assert "x at schemas/orchestrator-event.yaml#/oneOf/3/properties/marker_class/const" in out
    assert "[marker_class]" in out
    assert "Remediation:" in out
    assert "schemas/marker-taxonomy.yaml" in out
    assert "FR30" in out


def test_format_findings_header_present() -> None:
    out = format_findings(
        CheckResult(passing=[], missing=[], orphans=[]),
        dependencies_present=True,
    )
    assert "Cross-schema enumeration check (substrate component 4)" in out


# --------------------------------------------------------------------------- #
# Default-path resolution + uncommon harness-error paths                       #
# --------------------------------------------------------------------------- #


def test_main_with_no_flags_resolves_canonical_schemas() -> None:
    """Smoke test for ``_resolve_default_paths``: no CLI flags provided →
    main() resolves taxonomy + event-schema + dependencies via
    ``find_repo_root``. Mirrors the canonical CI invocation."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main([])
    assert rc == 0
    assert "Cross-schema enumeration check (substrate component 4)" in out.getvalue()


def test_main_yaml_error_on_taxonomy_returns_two(tmp_path: pathlib.Path) -> None:
    """A taxonomy file with malformed YAML triggers
    ``yaml.YAMLError`` inside ``load_marker_taxonomy`` — main() returns 2
    distinct from the RuntimeError "missing markers key" path."""
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    # An unterminated flow-mapping triggers yaml.YAMLError reliably (it never
    # parses to a value, unlike most malformed-content cases which yaml
    # tolerantly resolves to None / a string / a list).
    taxonomy_path.write_text("{unterminated:\n", encoding="utf-8")
    _write_yaml(event_schema_path, _minimal_event_schema())
    rc, _, err = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 2
    assert str(taxonomy_path) in err
    assert "YAML parse failure" in err


def test_main_oserror_on_event_schema_returns_two(tmp_path: pathlib.Path) -> None:
    """An event-schema path that is a directory (not a file) triggers
    IsADirectoryError, an OSError subclass — main() returns 2."""
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_dir = tmp_path / "events.yaml"  # name like a file but is a dir
    event_schema_dir.mkdir()
    _write_taxonomy(taxonomy_path, ["a"])
    rc, _, err = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_dir,
    )
    assert rc == 2
    assert str(event_schema_dir) in err
    assert "orchestrator-event schema" in err


def test_main_oserror_on_dependencies_returns_two(tmp_path: pathlib.Path) -> None:
    """A dependencies.yaml path that is a directory (not a file, not absent)
    triggers a non-FileNotFoundError OSError — that IS a harness error and
    must NOT be silently treated like the absent path. AC-2 explicit."""
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    deps_dir = tmp_path / "dependencies.yaml"
    deps_dir.mkdir()
    _write_taxonomy(taxonomy_path, ["a"])
    _write_yaml(event_schema_path, _minimal_event_schema())
    rc, _, err = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
        dependencies_path=deps_dir,
    )
    assert rc == 2
    assert str(deps_dir) in err
    assert "dependencies.yaml" in err


# --------------------------------------------------------------------------- #
# Performance (AC-1 + AC-6 case 8)                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.performance
def test_check_completes_under_one_second_on_canonical_schemas(
    tmp_path: pathlib.Path,
) -> None:
    """AC-1: the check must finish in < 1.0s on the MVP-sized canonical
    schemas. Uses the dependencies-absent path because dependencies.yaml
    does not exist at this story's landing time (story 1.6's deliverable)."""
    out, err = io.StringIO(), io.StringIO()
    deps_path_absent = tmp_path / "dependencies-absent.yaml"
    start = time.perf_counter()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main(
            [
                "--taxonomy-path",
                str(CANONICAL_TAXONOMY_PATH),
                "--event-schema-path",
                str(CANONICAL_EVENT_SCHEMA_PATH),
                "--dependencies-path",
                str(deps_path_absent),
            ]
        )
    elapsed = time.perf_counter() - start
    assert rc == 0
    assert elapsed < 1.0, (
        f"AC-1 performance budget exceeded: {elapsed:.3f}s > 1.0s on "
        f"the canonical schemas; profile with python -X importtime + "
        f"time.perf_counter and tighten before merging."
    )


# --------------------------------------------------------------------------- #
# Review-patch additions (code-review of 1-5, 2026-04-26)                    #
# --------------------------------------------------------------------------- #


def test_loud_fail_on_null_marker_class_in_taxonomy(tmp_path: pathlib.Path) -> None:
    """Taxonomy entry with a null marker_class value (YAML ``marker_class:``)
    must surface as exit 2 + diagnostic, NOT crash with TypeError in sorted().

    P1 patch: load_marker_taxonomy now validates that marker_class is a str.
    """
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    taxonomy_path.write_text(
        "schema_version: '1.0'\nmarkers:\n  - marker_class:\n    diagnostic_pointer: x\n    sub_classifications: []\n",
        encoding="utf-8",
    )
    _write_yaml(event_schema_path, _minimal_event_schema())
    rc, _, err = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
    )
    assert rc == 2
    assert "malformed" in err
    assert str(taxonomy_path) in err


def test_loud_fail_on_non_dict_dependencies_yaml(tmp_path: pathlib.Path) -> None:
    """A dependencies.yaml that exists but parses to a non-dict (list, null,
    scalar) must surface as exit 2 + diagnostic, NOT silently yield zero
    references while suppressing the deferral note.

    D1 patch: non-dict deps_raw is now a harness error (exit 2).
    """
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    deps_path = tmp_path / "dependencies.yaml"
    _write_taxonomy(taxonomy_path, ["a"])
    _write_yaml(event_schema_path, _minimal_event_schema())
    # Valid YAML but not a dict — a list is the most likely accidental shape.
    deps_path.write_text("- item_one\n- item_two\n", encoding="utf-8")
    rc, _, err = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
        dependencies_path=deps_path,
    )
    assert rc == 2
    assert str(deps_path) in err
    assert "YAML mapping" in err


# --------------------------------------------------------------------------- #
# Escalation-bundles directory reconciliation (Story 4.10)                    #
# --------------------------------------------------------------------------- #


CANONICAL_ESCALATION_BUNDLES_DIR = REPO_ROOT / "schemas" / "escalation-bundles"


def test_escalation_bundles_directory_absent_clean_skip(
    tmp_path: pathlib.Path,
) -> None:
    """When the escalation-bundles directory does not exist, ``main`` returns
    exit 0 and stdout includes the canonical deferral note. Mirrors the
    existing ``test_dependencies_yaml_absent_does_not_fail`` posture."""
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    _write_taxonomy(taxonomy_path, ["a"])
    _write_yaml(event_schema_path, _minimal_event_schema())
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
        escalation_bundles_dir=tmp_path / "definitely-absent-dir",
    )
    assert rc == 0
    assert (
        "schemas/escalation-bundles/ not present; deferred to story 4.10" in out
    )


def test_escalation_bundles_directory_empty_clean_skip(
    tmp_path: pathlib.Path,
) -> None:
    """When the escalation-bundles directory exists but is empty (no
    ``*.yaml`` files), ``main`` returns exit 0 and the deferral note is NOT
    printed (the directory IS present, just empty); no references are
    discovered from the directory."""
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    escalation_bundles_dir = tmp_path / "escalation-bundles"
    escalation_bundles_dir.mkdir()
    _write_taxonomy(taxonomy_path, ["a"])
    _write_yaml(event_schema_path, _minimal_event_schema())
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
        escalation_bundles_dir=escalation_bundles_dir,
    )
    assert rc == 0
    assert "Summary:" in out
    assert (
        "schemas/escalation-bundles/ not present; deferred to story 4.10"
        not in out
    )


def test_escalation_bundles_directory_with_clean_contracts_passes(
    tmp_path: pathlib.Path,
) -> None:
    """Pointing ``--escalation-bundles-dir`` at the canonical in-repo
    directory containing both real contracts (``verification-fail.yaml`` +
    ``env-setup-fail.yaml``) yields exit 0 + the four marker references
    (``env-setup-failed``, ``Tier-3-not-configured``, ``plan-drift-detected``,
    ``smoke-first-abort``) all resolve cleanly against the canonical
    marker-taxonomy.yaml."""
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=CANONICAL_TAXONOMY_PATH,
        event_schema_path=CANONICAL_EVENT_SCHEMA_PATH,
        escalation_bundles_dir=CANONICAL_ESCALATION_BUNDLES_DIR,
    )
    assert rc == 0
    # The four canonical Story-4.10 marker references must all resolve to
    # taxonomy entries (i.e., none of them appear in the orphan list, since
    # an orphan is a taxonomy entry that NO reference resolves to). The
    # orphan-list-rendering shape is `  - <marker_class>: ` per format_findings.
    for resolved_marker in (
        "env-setup-failed",
        "Tier-3-not-configured",
        "plan-drift-detected",
        "smoke-first-abort",
    ):
        assert f"  - {resolved_marker}:" not in out, (
            f"{resolved_marker} resolved by escalation-bundle contract should "
            f"not appear in the orphan list"
        )
    # No deferral note when the directory is present.
    assert (
        "schemas/escalation-bundles/ not present; deferred to story 4.10"
        not in out
    )


def test_escalation_bundles_contract_with_missing_marker_reference_fails(
    tmp_path: pathlib.Path,
) -> None:
    """A synthesized contract whose ``marker_class`` field references a non-
    existent marker class triggers exit 1 + the canonical
    ``_MISSING_REFERENCE_REMEDIATION`` prose names the malformed reference."""
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    escalation_bundles_dir = tmp_path / "escalation-bundles"
    escalation_bundles_dir.mkdir()
    _write_taxonomy(taxonomy_path, ["a"])
    _write_yaml(event_schema_path, _minimal_event_schema())
    _write_yaml(
        escalation_bundles_dir / "synthetic.yaml",
        {
            "type": "object",
            "properties": {
                "marker_class": {"const": "nonexistent-marker-class"},
            },
        },
    )
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
        escalation_bundles_dir=escalation_bundles_dir,
    )
    assert rc == 1
    assert "nonexistent-marker-class" in out
    assert "ERROR:" in out
    assert "Remediation:" in out
    assert "schemas/marker-taxonomy.yaml" in out


def test_escalation_bundles_contract_yaml_parse_failure_yields_harness_error(
    tmp_path: pathlib.Path,
) -> None:
    """A contract file containing malformed YAML (an unterminated flow-
    mapping, the same shape that triggers ``yaml.YAMLError`` reliably for
    other tests in this module) yields exit 2 with the canonical harness-
    level diagnostic naming the YAML parse failure.

    Note: this test exercises the YAML-parse-failure error path, NOT the
    OSError path. The function was renamed from
    ``test_escalation_bundles_contract_yaml_parse_failure_yields_harness_error``
    to reflect the actual trigger condition (Review patch 2026-05-03).
    """
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    escalation_bundles_dir = tmp_path / "escalation-bundles"
    escalation_bundles_dir.mkdir()
    _write_taxonomy(taxonomy_path, ["a"])
    _write_yaml(event_schema_path, _minimal_event_schema())
    bad_fragment = escalation_bundles_dir / "bad.yaml"
    bad_fragment.write_text("{unterminated:\n", encoding="utf-8")
    rc, _, err = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
        escalation_bundles_dir=escalation_bundles_dir,
    )
    assert rc == 2
    assert "harness-level error: escalation-bundle contract YAML parse failure:" in err
    assert str(bad_fragment) in err


def test_escalation_bundles_contract_non_mapping_yields_harness_error(
    tmp_path: pathlib.Path,
) -> None:
    """A contract file whose top-level YAML is a list (NOT a mapping) yields
    exit 2 + the canonical "did not parse to a YAML mapping" diagnostic.
    Mirrors the dependencies.yaml non-dict pattern (D1 patch)."""
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    escalation_bundles_dir = tmp_path / "escalation-bundles"
    escalation_bundles_dir.mkdir()
    _write_taxonomy(taxonomy_path, ["a"])
    _write_yaml(event_schema_path, _minimal_event_schema())
    non_mapping = escalation_bundles_dir / "list.yaml"
    non_mapping.write_text("- item_one\n- item_two\n", encoding="utf-8")
    rc, _, err = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
        escalation_bundles_dir=escalation_bundles_dir,
    )
    assert rc == 2
    assert "harness-level error: escalation-bundle contract did not parse to a YAML mapping:" in err
    assert str(non_mapping) in err


def test_escalation_bundles_dir_cli_flag_overrides_default(
    tmp_path: pathlib.Path,
) -> None:
    """Invoking ``main`` with ``--escalation-bundles-dir <tmp_path>`` (a
    synthetic directory containing one contract referencing a custom marker
    class) consumes the override exclusively — references are discovered from
    the override path, NOT from the canonical
    ``<repo-root>/schemas/escalation-bundles/`` (whose contracts reference
    only the four canonical Story-4.10 markers)."""
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    escalation_bundles_dir = tmp_path / "escalation-bundles"
    escalation_bundles_dir.mkdir()
    # Marker class unique to the synthetic override; the canonical four
    # Story-4.10 markers are intentionally NOT in this taxonomy so that any
    # leakage from the canonical in-repo escalation-bundles directory would
    # surface as missing references (rc == 1) and fail the test.
    _write_taxonomy(taxonomy_path, ["override-only-marker"])
    _write_yaml(event_schema_path, _minimal_event_schema())
    _write_yaml(
        escalation_bundles_dir / "override.yaml",
        {
            "type": "object",
            "properties": {
                "marker_class": {"const": "override-only-marker"},
            },
        },
    )
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
        escalation_bundles_dir=escalation_bundles_dir,
    )
    assert rc == 0
    # The override marker is referenced (passing); canonical Story-4.10
    # markers are NOT present in this taxonomy, so if the canonical in-repo
    # directory had been scanned we'd see them as missing references and
    # rc would be 1.
    assert "Summary: 1 passing reference(s), 0 missing reference(s)" in out


def test_dependencies_absent_AND_escalation_bundles_absent_clean_skip(
    tmp_path: pathlib.Path,
) -> None:
    """When BOTH optional pairs are absent simultaneously (no dependencies
    .yaml AND no escalation-bundles directory), ``main`` returns exit 0 +
    BOTH deferral notes are printed."""
    taxonomy_path = tmp_path / "taxonomy.yaml"
    event_schema_path = tmp_path / "events.yaml"
    _write_taxonomy(taxonomy_path, ["a"])
    _write_yaml(event_schema_path, _minimal_event_schema())
    rc, out, _ = _bare_run(
        tmp_path,
        taxonomy_path=taxonomy_path,
        event_schema_path=event_schema_path,
        dependencies_path=tmp_path / "missing-deps.yaml",
        escalation_bundles_dir=tmp_path / "missing-escalation-bundles",
    )
    assert rc == 0
    assert "schemas/dependencies.yaml not present; deferred to story 1.6" in out
    assert (
        "schemas/escalation-bundles/ not present; deferred to story 4.10" in out
    )
