"""Tests for the input-hardening structural gate — Story 24.2 (AC-7, AC-8).

Two layers: (1) the gate runs CLEAN against the real governed tree (the
integration witness that Rules A/B/C all pass post-implementation); (2) synthetic
tmp-tree fixtures exercise each rule's positive + negative path in isolation,
plus byte-stable ordering, registry rot, the allowlist, and the boundary-
discipline witnesses (FOUR specialists / THREE hooks / marker closed-set 37 /
schema_version "1.14" / no runtime marker emission).
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from loud_fail_harness import input_hardening_gate as gate
from loud_fail_harness._shared import find_repo_root


# --------------------------------------------------------------------------- #
# Synthetic harness-tree builder                                              #
# --------------------------------------------------------------------------- #


def _write_harness(
    tmp: pathlib.Path,
    modules: dict[str, str],
    registry: dict[str, object],
) -> tuple[pathlib.Path, pathlib.Path]:
    src = tmp / "src" / "loud_fail_harness"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    for name, body in modules.items():
        (src / f"{name}.py").write_text(body, encoding="utf-8")
    reg = tmp / "registry.yaml"
    reg.write_text(yaml.safe_dump(registry), encoding="utf-8")
    return tmp, reg


_HARDENED_MODEL = """\
from pydantic import BaseModel, model_validator

from loud_fail_harness.input_hardening import harden_identifier


class Bar(BaseModel):
    name: str

    @model_validator(mode="after")
    def _harden(self) -> "Bar":
        harden_identifier(self.name, "Bar.name")
        return self
"""

_UNHARDENED_MODEL = """\
from pydantic import BaseModel


class Bar(BaseModel):
    name: str
"""


# --------------------------------------------------------------------------- #
# Integration witness: the real tree is clean                                 #
# --------------------------------------------------------------------------- #


def test_real_governed_tree_is_clean() -> None:
    harness_root = find_repo_root() / "tools" / "loud-fail-harness"
    result = gate.run_input_hardening_gate(harness_root)
    assert result.findings == ()
    assert result.models_discovered >= 187


# --------------------------------------------------------------------------- #
# Rule A — classification                                                     #
# --------------------------------------------------------------------------- #


def test_rule_a_unclassified_model(tmp_path: pathlib.Path) -> None:
    root, reg = _write_harness(
        tmp_path,
        {"mod_a": _UNHARDENED_MODEL},
        {"externally_constructed": {}, "internal_only": []},
    )
    result = gate.run_input_hardening_gate(root, registry_path=reg)
    assert [f.rule for f in result.findings] == ["A-unclassified-model"]
    assert "mod_a.Bar" in result.findings[0].diagnostic


def test_rule_a_double_classified(tmp_path: pathlib.Path) -> None:
    root, reg = _write_harness(
        tmp_path,
        {"mod_a": _UNHARDENED_MODEL},
        {
            "externally_constructed": {"mod_a.Bar": {}},
            "internal_only": ["mod_a.Bar"],
        },
    )
    result = gate.run_input_hardening_gate(root, registry_path=reg)
    assert [f.rule for f in result.findings] == ["A-double-classified"]


def test_rule_a_internal_only_is_clean(tmp_path: pathlib.Path) -> None:
    root, reg = _write_harness(
        tmp_path,
        {"mod_a": _UNHARDENED_MODEL},
        {"externally_constructed": {}, "internal_only": ["mod_a.Bar"]},
    )
    result = gate.run_input_hardening_gate(root, registry_path=reg)
    assert result.findings == ()


# --------------------------------------------------------------------------- #
# Rule B — per-field hardening coverage                                       #
# --------------------------------------------------------------------------- #


def test_rule_b_field_unhardened(tmp_path: pathlib.Path) -> None:
    root, reg = _write_harness(
        tmp_path,
        {"mod_b": _UNHARDENED_MODEL},
        {
            "externally_constructed": {"mod_b.Bar": {"identifier_fields": ["name"]}},
            "internal_only": [],
        },
    )
    result = gate.run_input_hardening_gate(root, registry_path=reg)
    assert [f.rule for f in result.findings] == ["B-field-unhardened"]
    assert "'name'" in result.findings[0].diagnostic


def test_rule_b_hardened_field_is_clean(tmp_path: pathlib.Path) -> None:
    root, reg = _write_harness(
        tmp_path,
        {"mod_b": _HARDENED_MODEL},
        {
            "externally_constructed": {"mod_b.Bar": {"identifier_fields": ["name"]}},
            "internal_only": [],
        },
    )
    result = gate.run_input_hardening_gate(root, registry_path=reg)
    assert result.findings == ()


def test_rule_b_call_outside_validator_does_not_count(tmp_path: pathlib.Path) -> None:
    body = """\
from loud_fail_harness.input_hardening import harden_identifier
from pydantic import BaseModel


class Bar(BaseModel):
    name: str

    def not_a_validator(self) -> None:
        harden_identifier(self.name, "Bar.name")
"""
    root, reg = _write_harness(
        tmp_path,
        {"mod_b": body},
        {
            "externally_constructed": {"mod_b.Bar": {"identifier_fields": ["name"]}},
            "internal_only": [],
        },
    )
    result = gate.run_input_hardening_gate(root, registry_path=reg)
    assert [f.rule for f in result.findings] == ["B-field-unhardened"]


# --------------------------------------------------------------------------- #
# Rule C — ValidationError catch-boundary (swallow)                           #
# --------------------------------------------------------------------------- #


_SWALLOW_MODULE = """\
from pydantic import BaseModel


class Baz(BaseModel):
    x: int


def parse(value: object) -> object:
    try:
        return Baz(x=value)
    except ValueError:
        return None
"""

_RERAISE_MODULE = """\
from pydantic import BaseModel


class Baz(BaseModel):
    x: int


def parse(value: object) -> object:
    try:
        return Baz(x=value)
    except ValueError:
        raise
"""

_OUT_OF_SCOPE_MODULE = """\
from pydantic import BaseModel


class Baz(BaseModel):
    x: int


def parse(value: object) -> object:
    try:
        return Baz(x=value)
    except TypeError:
        return None
"""


def _registry_for_baz() -> dict[str, object]:
    return {
        "externally_constructed": {"mod_c.Baz": {}},
        "internal_only": [],
    }


def test_rule_c_swallow_flagged(tmp_path: pathlib.Path) -> None:
    root, reg = _write_harness(tmp_path, {"mod_c": _SWALLOW_MODULE}, _registry_for_baz())
    result = gate.run_input_hardening_gate(root, registry_path=reg)
    assert [f.rule for f in result.findings] == ["C-validationerror-swallowed"]


def test_rule_c_reraise_is_clean(tmp_path: pathlib.Path) -> None:
    root, reg = _write_harness(tmp_path, {"mod_c": _RERAISE_MODULE}, _registry_for_baz())
    result = gate.run_input_hardening_gate(root, registry_path=reg)
    assert result.findings == ()


def test_rule_c_out_of_scope_handler_is_clean(tmp_path: pathlib.Path) -> None:
    root, reg = _write_harness(
        tmp_path, {"mod_c": _OUT_OF_SCOPE_MODULE}, _registry_for_baz()
    )
    result = gate.run_input_hardening_gate(root, registry_path=reg)
    assert result.findings == ()


def test_rule_c_allowlisted_site_is_clean(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, reg = _write_harness(tmp_path, {"mod_c": _SWALLOW_MODULE}, _registry_for_baz())
    flagged = gate.run_input_hardening_gate(root, registry_path=reg)
    (finding,) = flagged.findings
    monkeypatch.setitem(
        gate._RULE_C_ALLOWLIST,
        f"mod_c:{finding.line_number}",
        "test: deliberate swallow",
    )
    result = gate.run_input_hardening_gate(root, registry_path=reg)
    assert result.findings == ()


# --------------------------------------------------------------------------- #
# Determinism + registry rot + CLI                                            #
# --------------------------------------------------------------------------- #


def test_findings_are_byte_stable_sorted(tmp_path: pathlib.Path) -> None:
    modules = {
        "mod_z": _UNHARDENED_MODEL,
        "mod_a": _UNHARDENED_MODEL.replace("Bar", "Foo"),
    }
    root, reg = _write_harness(
        tmp_path, modules, {"externally_constructed": {}, "internal_only": []}
    )
    result = gate.run_input_hardening_gate(root, registry_path=reg)
    keys = [(str(f.file_path), f.line_number, f.rule) for f in result.findings]
    assert keys == sorted(keys)
    assert len(result.findings) == 2


def test_registry_rot_raises(tmp_path: pathlib.Path) -> None:
    root, reg = _write_harness(
        tmp_path,
        {"mod_a": _UNHARDENED_MODEL},
        {"externally_constructed": {}, "internal_only": ["mod_a.Ghost"]},
    )
    with pytest.raises(RuntimeError, match="registry rot"):
        gate.run_input_hardening_gate(root, registry_path=reg)


def test_main_exit_codes(tmp_path: pathlib.Path) -> None:
    clean_root, clean_reg = _write_harness(
        tmp_path / "clean",
        {"mod_a": _UNHARDENED_MODEL},
        {"externally_constructed": {}, "internal_only": ["mod_a.Bar"]},
    )
    assert gate.main(["--harness-root", str(clean_root), "--registry-path", str(clean_reg)]) == 0

    dirty_root, dirty_reg = _write_harness(
        tmp_path / "dirty",
        {"mod_a": _UNHARDENED_MODEL},
        {"externally_constructed": {}, "internal_only": []},
    )
    assert gate.main(["--harness-root", str(dirty_root), "--registry-path", str(dirty_reg)]) == 1

    rot_root, rot_reg = _write_harness(
        tmp_path / "rot",
        {"mod_a": _UNHARDENED_MODEL},
        {"externally_constructed": {}, "internal_only": ["mod_a.Ghost"]},
    )
    assert gate.main(["--harness-root", str(rot_root), "--registry-path", str(rot_reg)]) == 2


def test_list_unclassified(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, reg = _write_harness(
        tmp_path,
        {"mod_a": _UNHARDENED_MODEL},
        {"externally_constructed": {}, "internal_only": []},
    )
    rc = gate.main(
        [
            "--harness-root",
            str(root),
            "--registry-path",
            str(reg),
            "--list-unclassified",
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "mod_a.Bar"


# --------------------------------------------------------------------------- #
# Boundary discipline (AC-7) — PRD-locked invariants held by construction     #
# --------------------------------------------------------------------------- #


def test_boundary_four_specialists_three_hooks() -> None:
    repo_root = find_repo_root()
    specialists = sorted(p.name for p in (repo_root / "agents").glob("*.md"))
    assert specialists == [
        "dev-wrapper.md",
        "qa.md",
        "review-bmad-wrapper.md",
        "review-lad-wrapper.md",
    ]
    hooks = sorted(p.name for p in (repo_root / "hooks").glob("*.sh"))
    assert len(hooks) == 3


def test_boundary_marker_taxonomy_unchanged() -> None:
    repo_root = find_repo_root()
    raw = yaml.safe_load(
        (repo_root / "schemas" / "marker-taxonomy.yaml").read_text(encoding="utf-8")
    )
    assert raw["schema_version"] == "1.14"
    assert len(raw["markers"]) == 37


def test_gate_emits_no_runtime_marker() -> None:
    # Build-time gate: no marker-taxonomy class reference, no active_markers
    # emission (mirrors naming-lint / pluggability-gate / no-destructive-resume-
    # lint, which carry no marker class).
    src = pathlib.Path(gate.__file__).read_text(encoding="utf-8")
    assert "active_markers" not in src
    assert "marker_class=" not in src
    assert "marker-taxonomy.yaml" not in src  # does not load/consult the taxonomy
