"""Story 17.1 — tests for the auto-merge config surface + gate-condition schema.

Mirrors ``test_retry_budget.py``'s ``tmp_path``-config-file style. Covers the
fixture pair (AC-5), the disabled/blank-gate default paths (AC-3), the headline
no-gate-but-enabled loud-fail (AC-2), and the per-field type/range rejections
(AC-4).
"""

from __future__ import annotations

import importlib.resources
import pathlib
from typing import Any

import pytest

from loud_fail_harness.auto_merge_config import (
    DEFAULT_AUTO_MERGE_ENABLED,
    AutoMergeConfig,
    AutoMergeConfigError,
    AutoMergeGateConditions,
    read_auto_merge_config_from_config_file,
    resolve_auto_merge_config,
)

_FULL_GATES = {
    "min_adoption_months": 6,
    "min_completion_fidelity": 0.9,
    "max_retry_exhaustion": 0.1,
}


# ---------------------------------------------------------------------------
# Module shape + defaults
# ---------------------------------------------------------------------------


def test_default_auto_merge_enabled_is_false() -> None:
    assert DEFAULT_AUTO_MERGE_ENABLED is False


def test_resolved_dataclasses_are_frozen() -> None:
    cfg = resolve_auto_merge_config(None)
    with pytest.raises((AttributeError, TypeError)):
        cfg.enabled = True  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        cfg.gate_conditions.min_adoption_months = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AC-3 — default / disabled paths accept blank gates (no rejection)
# ---------------------------------------------------------------------------


def test_resolve_none_config_returns_disabled() -> None:
    cfg = resolve_auto_merge_config(None)
    assert cfg == AutoMergeConfig(
        enabled=False,
        gate_conditions=AutoMergeGateConditions(None, None, None),
    )


def test_resolve_auto_merge_key_absent_returns_disabled() -> None:
    cfg = resolve_auto_merge_config({"retry_budget": 2})
    assert cfg.enabled is False
    assert cfg.gate_conditions == AutoMergeGateConditions(None, None, None)


def test_resolve_auto_merge_block_none_returns_disabled() -> None:
    cfg = resolve_auto_merge_config({"auto_merge": None})
    assert cfg.enabled is False


def test_resolve_disabled_with_blank_gates_is_clean() -> None:
    cfg = resolve_auto_merge_config({"auto_merge": {"enabled": False}})
    assert cfg.enabled is False
    assert cfg.gate_conditions == AutoMergeGateConditions(None, None, None)


def test_resolve_disabled_with_partial_gates_is_clean() -> None:
    cfg = resolve_auto_merge_config(
        {"auto_merge": {"enabled": False, "gate_conditions": {"min_adoption_months": 0}}}
    )
    assert cfg.enabled is False
    assert cfg.gate_conditions.min_adoption_months == 0


def test_resolve_enabled_absent_defaults_disabled_even_with_blank_gates() -> None:
    cfg = resolve_auto_merge_config({"auto_merge": {"gate_conditions": None}})
    assert cfg.enabled is False


# ---------------------------------------------------------------------------
# AC-5 — fixture pair: valid enabled+full gates resolves; invalid is rejected
# ---------------------------------------------------------------------------


def test_fixture_valid_enabled_with_full_gates_resolves() -> None:
    cfg = resolve_auto_merge_config(
        {"auto_merge": {"enabled": True, "gate_conditions": dict(_FULL_GATES)}}
    )
    assert cfg == AutoMergeConfig(
        enabled=True,
        gate_conditions=AutoMergeGateConditions(
            min_adoption_months=6,
            min_completion_fidelity=0.9,
            max_retry_exhaustion=0.1,
        ),
    )


def test_fixture_invalid_enabled_with_absent_gates_is_rejected() -> None:
    with pytest.raises(AutoMergeConfigError, match="absent or zero-valued"):
        resolve_auto_merge_config({"auto_merge": {"enabled": True}})


# ---------------------------------------------------------------------------
# AC-2 — no-gate-but-enabled cross-field loud-fail (the headline)
# ---------------------------------------------------------------------------


def test_enabled_with_gate_conditions_none_rejected_names_all_three() -> None:
    with pytest.raises(AutoMergeConfigError) as exc_info:
        resolve_auto_merge_config(
            {"auto_merge": {"enabled": True, "gate_conditions": None}}
        )
    message = str(exc_info.value)
    assert "min_adoption_months" in message
    assert "min_completion_fidelity" in message
    assert "max_retry_exhaustion" in message


@pytest.mark.parametrize(
    "absent_field",
    ["min_adoption_months", "min_completion_fidelity", "max_retry_exhaustion"],
)
def test_enabled_with_one_gate_absent_names_that_gate(absent_field: str) -> None:
    gates = dict(_FULL_GATES)
    del gates[absent_field]
    with pytest.raises(AutoMergeConfigError) as exc_info:
        resolve_auto_merge_config(
            {"auto_merge": {"enabled": True, "gate_conditions": gates}}
        )
    assert absent_field in str(exc_info.value)


@pytest.mark.parametrize(
    ("zero_field", "zero_value"),
    [
        ("min_adoption_months", 0),
        ("min_completion_fidelity", 0.0),
        ("max_retry_exhaustion", 0.0),
    ],
)
def test_enabled_with_zero_valued_gate_rejected(
    zero_field: str, zero_value: float
) -> None:
    gates = dict(_FULL_GATES)
    gates[zero_field] = zero_value
    with pytest.raises(AutoMergeConfigError, match="absent or zero-valued") as exc_info:
        resolve_auto_merge_config(
            {"auto_merge": {"enabled": True, "gate_conditions": gates}}
        )
    assert zero_field in str(exc_info.value)


def test_enabled_with_explicit_null_gate_value_rejected() -> None:
    gates = dict(_FULL_GATES)
    gates["min_completion_fidelity"] = None  # type: ignore[assignment]
    with pytest.raises(AutoMergeConfigError) as exc_info:
        resolve_auto_merge_config(
            {"auto_merge": {"enabled": True, "gate_conditions": gates}}
        )
    assert "min_completion_fidelity" in str(exc_info.value)


def test_enabled_with_full_non_zero_gates_including_boundaries_resolves() -> None:
    cfg = resolve_auto_merge_config(
        {
            "auto_merge": {
                "enabled": True,
                "gate_conditions": {
                    "min_adoption_months": 1,
                    "min_completion_fidelity": 1.0,
                    "max_retry_exhaustion": 1.0,
                },
            }
        }
    )
    assert cfg.enabled is True


# ---------------------------------------------------------------------------
# AC-4 — malformed shapes rejected with field-named diagnostics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [1, 0, "true", "false", 1.0, [], {}])
def test_enabled_non_bool_rejected(value: object) -> None:
    with pytest.raises(AutoMergeConfigError, match="must be a YAML boolean") as exc_info:
        resolve_auto_merge_config({"auto_merge": {"enabled": value}})
    assert "auto_merge.enabled" in str(exc_info.value)


@pytest.mark.parametrize("value", [["a"], "scalar", 3])
def test_auto_merge_block_non_mapping_rejected(value: object) -> None:
    with pytest.raises(AutoMergeConfigError, match="auto_merge must be a YAML mapping"):
        resolve_auto_merge_config({"auto_merge": value})


@pytest.mark.parametrize("value", [["a"], "scalar", 3])
def test_gate_conditions_non_mapping_rejected(value: object) -> None:
    with pytest.raises(
        AutoMergeConfigError, match="gate_conditions must be a YAML mapping"
    ):
        resolve_auto_merge_config(
            {"auto_merge": {"enabled": False, "gate_conditions": value}}
        )


@pytest.mark.parametrize("value", [True, False])
def test_min_adoption_months_bool_rejected(value: bool) -> None:
    with pytest.raises(AutoMergeConfigError, match="must be an integer >= 0") as exc:
        resolve_auto_merge_config(
            {"auto_merge": {"gate_conditions": {"min_adoption_months": value}}}
        )
    assert "min_adoption_months" in str(exc.value)


@pytest.mark.parametrize("value", ["6", 6.0, [6]])
def test_min_adoption_months_non_int_rejected(value: object) -> None:
    with pytest.raises(AutoMergeConfigError, match="must be a YAML int"):
        resolve_auto_merge_config(
            {"auto_merge": {"gate_conditions": {"min_adoption_months": value}}}
        )


def test_min_adoption_months_negative_rejected() -> None:
    with pytest.raises(AutoMergeConfigError, match="must be an integer >= 0"):
        resolve_auto_merge_config(
            {"auto_merge": {"gate_conditions": {"min_adoption_months": -1}}}
        )


@pytest.mark.parametrize(
    "gate_field", ["min_completion_fidelity", "max_retry_exhaustion"]
)
def test_fraction_gate_bool_rejected(gate_field: str) -> None:
    with pytest.raises(AutoMergeConfigError, match="must be a number") as exc:
        resolve_auto_merge_config(
            {"auto_merge": {"gate_conditions": {gate_field: True}}}
        )
    assert gate_field in str(exc.value)


@pytest.mark.parametrize(
    "gate_field", ["min_completion_fidelity", "max_retry_exhaustion"]
)
@pytest.mark.parametrize("value", ["0.9", [0.9], {}])
def test_fraction_gate_non_numeric_rejected(gate_field: str, value: object) -> None:
    with pytest.raises(AutoMergeConfigError, match="must be a YAML number"):
        resolve_auto_merge_config(
            {"auto_merge": {"gate_conditions": {gate_field: value}}}
        )


@pytest.mark.parametrize(
    "gate_field", ["min_completion_fidelity", "max_retry_exhaustion"]
)
@pytest.mark.parametrize("value", [-0.1, 1.5, 2])
def test_fraction_gate_out_of_range_rejected(gate_field: str, value: float) -> None:
    with pytest.raises(AutoMergeConfigError, match="must be in the range"):
        resolve_auto_merge_config(
            {"auto_merge": {"gate_conditions": {gate_field: value}}}
        )


def test_fraction_gate_accepts_int_coerced_to_float() -> None:
    cfg = resolve_auto_merge_config(
        {"auto_merge": {"gate_conditions": {"min_completion_fidelity": 1}}}
    )
    assert cfg.gate_conditions.min_completion_fidelity == 1.0
    assert isinstance(cfg.gate_conditions.min_completion_fidelity, float)


# ---------------------------------------------------------------------------
# read_auto_merge_config_from_config_file — file contract
# ---------------------------------------------------------------------------


def test_read_missing_file_returns_disabled(tmp_path: pathlib.Path) -> None:
    cfg = read_auto_merge_config_from_config_file(tmp_path / "nope.yaml")
    assert cfg.enabled is False


def test_read_empty_file_returns_disabled(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")
    assert read_auto_merge_config_from_config_file(config).enabled is False


def test_read_whitespace_only_returns_disabled(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("   \n\t\n", encoding="utf-8")
    assert read_auto_merge_config_from_config_file(config).enabled is False


def test_read_valid_enabled_fixture_resolves(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "auto_merge:\n"
        "  enabled: true\n"
        "  gate_conditions:\n"
        "    min_adoption_months: 6\n"
        "    min_completion_fidelity: 0.9\n"
        "    max_retry_exhaustion: 0.1\n",
        encoding="utf-8",
    )
    cfg = read_auto_merge_config_from_config_file(config)
    assert cfg.enabled is True
    assert cfg.gate_conditions.min_adoption_months == 6


def test_read_invalid_enabled_fixture_rejected(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "auto_merge:\n  enabled: true\n  gate_conditions:\n    max_retry_exhaustion: 0\n",
        encoding="utf-8",
    )
    with pytest.raises(AutoMergeConfigError, match="absent or zero-valued"):
        read_auto_merge_config_from_config_file(config)


def test_read_malformed_yaml_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("auto_merge: [\n", encoding="utf-8")
    with pytest.raises(AutoMergeConfigError, match="not valid YAML"):
        read_auto_merge_config_from_config_file(config)


def test_read_non_mapping_top_level_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(AutoMergeConfigError, match="must be a YAML mapping"):
        read_auto_merge_config_from_config_file(config)


def test_read_propagates_resolver_error(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("auto_merge:\n  enabled: notabool\n", encoding="utf-8")
    with pytest.raises(AutoMergeConfigError, match="must be a YAML boolean"):
        read_auto_merge_config_from_config_file(config)


# ---------------------------------------------------------------------------
# AC-1 — config template carries the auto_merge surface and resolves disabled
# ---------------------------------------------------------------------------


def _read_template() -> str:
    return (
        importlib.resources.files("loud_fail_harness") / "_data" / "config.yaml.template"
    ).read_text(encoding="utf-8")


def test_config_template_carries_auto_merge_block() -> None:
    template = _read_template()
    assert "auto_merge:" in template
    assert "enabled: false" in template
    assert "gate_conditions:" in template
    for gate in ("min_adoption_months", "min_completion_fidelity", "max_retry_exhaustion"):
        assert gate in template


def test_config_template_gates_ship_blank_with_tbd_rationale() -> None:
    template = _read_template()
    assert "TBD — set by maintainer when gate threshold is determined post-release data" in template


def test_config_template_auto_merge_resolves_to_disabled() -> None:
    import yaml

    parsed: Any = yaml.safe_load(_read_template())
    cfg = resolve_auto_merge_config(parsed)
    assert cfg == AutoMergeConfig(
        enabled=False,
        gate_conditions=AutoMergeGateConditions(None, None, None),
    )


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------


def test_module_all_exports() -> None:
    import loud_fail_harness.auto_merge_config as _mod

    assert set(_mod.__all__) == {
        "AutoMergeConfig",
        "AutoMergeConfigError",
        "AutoMergeGateConditions",
        "DEFAULT_AUTO_MERGE_ENABLED",
        "read_auto_merge_config_from_config_file",
        "resolve_auto_merge_config",
    }


# ---------------------------------------------------------------------------
# default_enabled=True parameter — loud-fail on absent/empty config
# ---------------------------------------------------------------------------


def test_resolve_default_enabled_true_with_absent_config_raises() -> None:
    with pytest.raises(AutoMergeConfigError, match="absent or zero-valued"):
        resolve_auto_merge_config(None, default_enabled=True)


def test_resolve_default_enabled_true_with_absent_key_raises() -> None:
    with pytest.raises(AutoMergeConfigError, match="absent or zero-valued"):
        resolve_auto_merge_config({"retry_budget": 2}, default_enabled=True)


def test_read_default_enabled_true_missing_file_raises(tmp_path: pathlib.Path) -> None:
    with pytest.raises(AutoMergeConfigError, match="absent or zero-valued"):
        read_auto_merge_config_from_config_file(
            tmp_path / "nope.yaml", default_enabled=True
        )


def test_read_default_enabled_true_empty_file_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")
    with pytest.raises(AutoMergeConfigError, match="absent or zero-valued"):
        read_auto_merge_config_from_config_file(config, default_enabled=True)


# ---------------------------------------------------------------------------
# read_auto_merge_config_from_config_file — UnicodeDecodeError path
# ---------------------------------------------------------------------------


def test_read_non_utf8_file_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_bytes(b"\xff\xfe bad bytes")
    with pytest.raises(AutoMergeConfigError, match="failed to read"):
        read_auto_merge_config_from_config_file(config)


# ---------------------------------------------------------------------------
# AC-2 — integer 0 for fraction gates coerced and rejected (YAML `field: 0`)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "gate_field", ["min_completion_fidelity", "max_retry_exhaustion"]
)
def test_enabled_with_integer_zero_fraction_gate_rejected(gate_field: str) -> None:
    gates = dict(_FULL_GATES)
    gates[gate_field] = 0  # YAML `gate_field: 0` → int → coerced to 0.0 → rejected
    with pytest.raises(AutoMergeConfigError, match="absent or zero-valued") as exc_info:
        resolve_auto_merge_config(
            {"auto_merge": {"enabled": True, "gate_conditions": gates}}
        )
    assert gate_field in str(exc_info.value)
