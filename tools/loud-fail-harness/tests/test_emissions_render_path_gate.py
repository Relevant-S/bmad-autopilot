"""Contract-coverage corpus for the `*_emissions` → render-path gate (Story 22.6 G2).

Drives the gate over the real envelope schema + registry + bundle_assembly.py
(baseline pass) and over synthetic inputs proving it catches the precise failure
it exists to catch — a typed emissions field with NO bundle render path — and is
not green-on-empty.

AC-2 — both-directions field→render-path enforcement:
    [x] test_baseline_real_inputs_pass             (the live tree is clean)
    [x] test_discover_emissions_fields_real_schema
    [x] test_registry_rot_field_not_in_schema
    [x] test_render_function_not_defined
    [x] test_render_function_not_invoked
    [x] test_field_not_accessed
    [x] test_findings_are_byte_stable_ordered

AC-4 — negative witness ("verify the verifier"):
    [x] test_foo_emissions_without_render_path_fails  (the negative witness)
    [x] test_main_exits_one_on_foo_emissions_fixture

AC-2 CLI + harness-level error:
    [x] test_main_exits_zero_on_clean
    [x] test_main_exit_two_when_schema_unresolvable
    [x] test_main_exit_two_on_malformed_registry

AC-5 — boundary witness (build-time gate, NO runtime marker).
"""

from __future__ import annotations

import pathlib

import yaml

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.emissions_render_path_gate import (
    _resolve_registry_path,
    discover_emissions_fields,
    evaluate_emissions_render_paths,
    main,
    run_emissions_render_path_gate,
)

_REPO_ROOT = find_repo_root()
_SCHEMA_PATH = _REPO_ROOT / "schemas" / "envelope.schema.yaml"
_BUNDLE_SOURCE = (
    _REPO_ROOT
    / "tools"
    / "loud-fail-harness"
    / "src"
    / "loud_fail_harness"
    / "bundle_assembly.py"
)
_REGISTRY_PATH = _resolve_registry_path()

_REAL_FIELDS = {
    "heuristic_skipped_emissions",
    "a11y_emissions",
    "visual_regression_emissions",
    "flakiness_emissions",
}
_REAL_REGISTRY = {
    "heuristic_skipped_emissions": ["_render_qa_heuristic_findings_subsection"],
    "a11y_emissions": [
        "_render_qa_a11y_subsection",
        "_render_qa_a11y_envelope_scoped_marker",
    ],
    "visual_regression_emissions": ["_render_qa_visual_subsection"],
    "flakiness_emissions": ["_render_qa_flakiness_subsection"],
}


def _bundle_source() -> str:
    return _BUNDLE_SOURCE.read_text(encoding="utf-8")


def test_baseline_real_inputs_pass() -> None:
    result = run_emissions_render_path_gate(
        schema_path=_SCHEMA_PATH,
        registry_path=_REGISTRY_PATH,
        bundle_source_path=_BUNDLE_SOURCE,
    )
    assert result.findings == ()
    assert set(result.schema_fields_scanned) == _REAL_FIELDS
    assert set(result.registry_fields_scanned) == _REAL_FIELDS


def test_discover_emissions_fields_real_schema() -> None:
    schema = yaml.safe_load(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert discover_emissions_fields(schema) == _REAL_FIELDS


def test_foo_emissions_without_render_path_fails() -> None:
    """The negative witness: a new `*_emissions` field with no registry entry
    (hence no render path) MUST fail the gate."""
    result = evaluate_emissions_render_paths(
        schema_fields=_REAL_FIELDS | {"foo_emissions"},
        registry=_REAL_REGISTRY,
        bundle_source=_bundle_source(),
    )
    rules = {(f.rule, f.field_name) for f in result.findings}
    assert ("schema-field-unregistered", "foo_emissions") in rules
    assert len(result.findings) == 1


def test_registry_rot_field_not_in_schema() -> None:
    registry = dict(_REAL_REGISTRY)
    registry["ghost_emissions"] = ["_render_qa_flakiness_subsection"]
    result = evaluate_emissions_render_paths(
        schema_fields=_REAL_FIELDS,
        registry=registry,
        bundle_source=_bundle_source(),
    )
    rules = {(f.rule, f.field_name) for f in result.findings}
    assert ("registry-field-not-in-schema", "ghost_emissions") in rules


def test_render_function_not_defined() -> None:
    registry = dict(_REAL_REGISTRY)
    registry["flakiness_emissions"] = ["_render_qa_does_not_exist"]
    result = evaluate_emissions_render_paths(
        schema_fields=_REAL_FIELDS,
        registry=registry,
        bundle_source=_bundle_source(),
    )
    rules = {(f.rule, f.render_target) for f in result.findings}
    assert ("render-function-not-defined", "_render_qa_does_not_exist") in rules


def test_render_function_not_invoked() -> None:
    source = (
        "def _render_qa_flakiness_subsection(x):\n    return x\n"
        'value = qa_envelope.get("flakiness_emissions")\n'
    )
    result = evaluate_emissions_render_paths(
        schema_fields={"flakiness_emissions"},
        registry={"flakiness_emissions": ["_render_qa_flakiness_subsection"]},
        bundle_source=source,
    )
    rules = {(f.rule, f.render_target) for f in result.findings}
    assert ("render-function-not-invoked", "_render_qa_flakiness_subsection") in rules


def test_field_not_accessed() -> None:
    source = "def _render_qa_flakiness_subsection(x):\n    return _render_qa_flakiness_subsection\n"
    result = evaluate_emissions_render_paths(
        schema_fields={"flakiness_emissions"},
        registry={"flakiness_emissions": ["_render_qa_flakiness_subsection"]},
        bundle_source=source,
    )
    rules = {f.rule for f in result.findings}
    assert "field-not-accessed" in rules


def test_findings_are_byte_stable_ordered() -> None:
    registry = dict(_REAL_REGISTRY)
    registry["zzz_emissions"] = ["_render_qa_flakiness_subsection"]
    registry["aaa_emissions"] = ["_render_qa_flakiness_subsection"]
    result = evaluate_emissions_render_paths(
        schema_fields=_REAL_FIELDS | {"mmm_emissions"},
        registry=registry,
        bundle_source=_bundle_source(),
    )
    keys = [(f.rule, f.field_name, f.render_target) for f in result.findings]
    assert keys == sorted(keys)


def test_main_exits_zero_on_clean() -> None:
    assert main([]) == 0


def test_main_exits_one_on_foo_emissions_fixture(tmp_path: pathlib.Path) -> None:
    fixture_schema = tmp_path / "envelope.schema.yaml"
    fixture_schema.write_text(
        yaml.safe_dump(
            {
                "type": "object",
                "properties": {
                    **{field: {"type": "array"} for field in _REAL_FIELDS},
                    "foo_emissions": {"type": "array"},
                },
            }
        ),
        encoding="utf-8",
    )
    exit_code = main(["--schema", str(fixture_schema)])
    assert exit_code == 1


def test_main_exit_two_when_schema_unresolvable(tmp_path: pathlib.Path) -> None:
    missing = tmp_path / "nope.yaml"
    assert main(["--schema", str(missing)]) == 2


def test_main_exit_two_on_malformed_registry(tmp_path: pathlib.Path) -> None:
    bad_registry = tmp_path / "registry.yaml"
    bad_registry.write_text("emissions_render_surfaces: [not, a, mapping]\n", encoding="utf-8")
    assert main(["--registry", str(bad_registry)]) == 2
