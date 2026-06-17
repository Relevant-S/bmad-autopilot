"""Story 17.1 — Auto-merge config surface + gate-condition schema (FR-P2-3).

Pure-library substrate owning the orchestrator-side *config surface* for
auto-merge: read the ``auto_merge`` block from
``_bmad/automation/config.yaml`` and resolve it into an
:class:`AutoMergeConfig` (``enabled`` flag + nested
:class:`AutoMergeGateConditions`), raising loudly on malformed input and on
the headline cross-field violation — ``enabled: true`` with absent / partial /
zero-valued gate conditions.

This is the FIRST of Epic 17's three stories. It lands **config + validation
only**: no gate-condition evaluator (17.2), no ``gh pr merge`` / Stop-hook
execution (17.3), no marker emission, no ``adoption-metrics.yaml`` read, no
orchestrator-skill wiring. The flag stays default-false and nothing reads it
yet — landing the surface ahead of the logic is the deliberate Epic-17
sequencing (auto-merge is the first Phase-2 surface that can push to a remote,
so it ships in three audited slices per NFR-S3).

Composition discipline (mirrors the existing flat opt-in flags
``parallel_stories`` / ``background_execution`` in
:mod:`loud_fail_harness.retry_budget`): a ``resolve_X(mapping)`` +
``read_X_from_config_file(path)`` pair raising an
:class:`AutoMergeConfigError` (``ValueError`` lineage), using
:func:`yaml.safe_load`. The one structural addition over those flat scalar
flags is the nested ``gate_conditions`` sub-block carrying a cross-field
validation rule (enabled ⇒ non-zero gates).

Plain frozen dataclasses (NOT a Pydantic model) are used deliberately: the
entire existing config surface resolves via plain functions, and a Pydantic
``BaseModel`` here would require registration in
``_data/input_hardening_registry.yaml`` to satisfy the ``input-hardening-gate``
(Rule A) — coupling this surface to that gate for no benefit, since the
``auto_merge`` block carries no string identifier/path fields.

Sources:
    * **PRD FR-P2-3** (``_bmad-output/planning-artifacts/prd.md`` line 946):
      "Auto-merge — configurable flag (default false); gated on
      reference-project adoption conditions per Scope Decisions table."
    * **PRD Scope Decisions** (``prd.md`` line 748, auto-merge row): "≥ 6
      months adoption with completion-fidelity ≥ X% and retry-exhaustion ≤ Y%
      on reference projects (specific thresholds TBD post-release data)" —
      the three gate conditions (:data:`_MIN_ADOPTION_MONTHS_FIELD`,
      :data:`_MIN_COMPLETION_FIDELITY_FIELD`,
      :data:`_MAX_RETRY_EXHAUSTION_FIELD`) plus their TBD-blank default.
    * **Story 17.1 epic AC** at ``epics-phase-2.md`` lines 533-582.

Pattern compliance (architecture.md → Implementation Patterns):
    * **Pattern 1 (snake_case structural keys)** — every config-file field is
      snake_case (``auto_merge``, ``gate_conditions``, ``min_adoption_months``,
      ...); Python ``resolve_*`` / ``read_*`` are snake_case per convention.
    * **Pattern 5 (loud-fail)** — :class:`AutoMergeConfigError` raises loudly
      on malformed input and on the no-gate-but-enabled cross-field violation;
      the only silent-default paths are "config absent" / "block absent" /
      "disabled with blank gates" (all legitimate per AC-3).
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import yaml

#: Default ``auto_merge.enabled`` value per FR-P2-3 ("configurable flag,
#: default false"). Single-sourced here so the resolver default and any future
#: consumer default can never drift.
DEFAULT_AUTO_MERGE_ENABLED: bool = False

#: Canonical ``auto_merge`` config-file block name. Snake_case per Pattern 1.
_AUTO_MERGE_FIELD: str = "auto_merge"

#: Canonical ``auto_merge.enabled`` field name (the opt-in gate).
_ENABLED_FIELD: str = "enabled"

#: Canonical ``auto_merge.gate_conditions`` sub-block name.
_GATE_CONDITIONS_FIELD: str = "gate_conditions"

#: Gate condition — minimum reference-project adoption duration in months
#: (``prd.md`` line 748: "≥ 6 months adoption"). Integer >= 0; ``0`` triggers
#: the no-gate cross-field rejection when ``enabled``.
_MIN_ADOPTION_MONTHS_FIELD: str = "min_adoption_months"

#: Gate condition — minimum completion fidelity as a fraction in [0.0, 1.0]
#: (``prd.md`` line 748: "completion-fidelity ≥ X%").
_MIN_COMPLETION_FIDELITY_FIELD: str = "min_completion_fidelity"

#: Gate condition — maximum retry-exhaustion rate as a fraction in [0.0, 1.0]
#: (``prd.md`` line 748: "retry-exhaustion ≤ Y%").
_MAX_RETRY_EXHAUSTION_FIELD: str = "max_retry_exhaustion"


class AutoMergeConfigError(ValueError):
    """Raised on malformed ``auto_merge`` config input or the no-gate-but-enabled
    cross-field violation.

    The ``ValueError`` lineage mirrors
    :class:`loud_fail_harness.retry_budget.RetryBudgetConfigError`: the
    per-input-shape contract treats "wrong type" / "out of range" / "enabled
    without gates" as value-domain violations. Subclassing :class:`ValueError`
    keeps generic ``except ValueError`` handlers compatible while allowing a
    precise ``except AutoMergeConfigError`` catch at the orchestrator boundary.

    Message format (FR48a / NFR-O5 actionable-pointer posture): include the
    offending value / field name (dotted, e.g. ``auto_merge.enabled``) and a
    remediation hint so an operator pasting the error into a chat can identify
    what to change in their ``_bmad/automation/config.yaml`` without reading
    source.
    """


@dataclass(frozen=True)
class AutoMergeGateConditions:
    """Resolved gate-condition triple for auto-merge admission.

    Each field is ``None`` when its config key is absent / valueless (the
    legitimate TBD-blank default state while thresholds are unset per
    ``prd.md`` line 748). When ``auto_merge.enabled`` is true, all three MUST
    be present and non-zero (enforced in :func:`resolve_auto_merge_config`).
    17.2's gate-condition evaluator consumes this shape.
    """

    min_adoption_months: int | None
    min_completion_fidelity: float | None
    max_retry_exhaustion: float | None


@dataclass(frozen=True)
class AutoMergeConfig:
    """Resolved ``auto_merge`` config: the opt-in flag + its gate conditions."""

    enabled: bool
    gate_conditions: AutoMergeGateConditions


def _resolve_enabled(block: Mapping[str, Any], default_enabled: bool) -> bool:
    if _ENABLED_FIELD not in block:
        return default_enabled

    value = block[_ENABLED_FIELD]
    if value is None:
        return default_enabled

    if type(value) is not bool:
        raise AutoMergeConfigError(
            f"{_AUTO_MERGE_FIELD}.{_ENABLED_FIELD} must be a YAML boolean; "
            f"got {value!r} ({type(value).__name__}) — write the value as an "
            f"unquoted YAML bool in config.yaml (e.g., "
            f"'{_AUTO_MERGE_FIELD}:\\n  {_ENABLED_FIELD}: true' or "
            f"'{_ENABLED_FIELD}: false'), not as an integer, quoted string, or "
            f"other type"
        )

    return value


def _resolve_min_adoption_months(gate_block: Mapping[str, Any]) -> int | None:
    if _MIN_ADOPTION_MONTHS_FIELD not in gate_block:
        return None

    value = gate_block[_MIN_ADOPTION_MONTHS_FIELD]
    if value is None:
        return None

    field = f"{_AUTO_MERGE_FIELD}.{_GATE_CONDITIONS_FIELD}.{_MIN_ADOPTION_MONTHS_FIELD}"

    if isinstance(value, bool):
        raise AutoMergeConfigError(
            f"{field} must be an integer >= 0; got {value!r} "
            f"({type(value).__name__}) — booleans are rejected to avoid YAML "
            f"truthy-coercion ambiguity — write the value as an unquoted "
            f"integer (e.g., '{_MIN_ADOPTION_MONTHS_FIELD}: 6')"
        )

    if type(value) is not int:
        raise AutoMergeConfigError(
            f"{field} must be a YAML int; got {value!r} "
            f"({type(value).__name__}) — write the value as an unquoted integer "
            f"(e.g., '{_MIN_ADOPTION_MONTHS_FIELD}: 6', not "
            f"'{_MIN_ADOPTION_MONTHS_FIELD}: \"6\"' or "
            f"'{_MIN_ADOPTION_MONTHS_FIELD}: 6.0')"
        )

    if value < 0:
        raise AutoMergeConfigError(
            f"{field} must be an integer >= 0; got {value!r} (int) — a negative "
            f"adoption-month gate is meaningless; set it to a positive integer "
            f"(e.g., 6) or leave it blank while the threshold is TBD"
        )

    return value


def _resolve_fraction_gate(
    gate_block: Mapping[str, Any], gate_field: str
) -> float | None:
    if gate_field not in gate_block:
        return None

    value = gate_block[gate_field]
    if value is None:
        return None

    field = f"{_AUTO_MERGE_FIELD}.{_GATE_CONDITIONS_FIELD}.{gate_field}"

    if isinstance(value, bool):
        raise AutoMergeConfigError(
            f"{field} must be a number in [0.0, 1.0]; got {value!r} "
            f"({type(value).__name__}) — booleans are rejected to avoid YAML "
            f"truthy-coercion ambiguity — write the value as an unquoted "
            f"fraction (e.g., '{gate_field}: 0.9')"
        )

    if type(value) not in (int, float):
        raise AutoMergeConfigError(
            f"{field} must be a YAML number; got {value!r} "
            f"({type(value).__name__}) — write the value as an unquoted fraction "
            f"(e.g., '{gate_field}: 0.9', not '{gate_field}: \"0.9\"')"
        )

    coerced = float(value)
    if not (0.0 <= coerced <= 1.0):
        raise AutoMergeConfigError(
            f"{field} must be in the range [0.0, 1.0]; got {value!r} — gate "
            f"fidelity / exhaustion rates are fractions of 1; set it to e.g. 0.9"
        )

    return coerced


def _resolve_gate_conditions(block: Mapping[str, Any]) -> AutoMergeGateConditions:
    if _GATE_CONDITIONS_FIELD not in block:
        return AutoMergeGateConditions(None, None, None)

    raw = block[_GATE_CONDITIONS_FIELD]
    if raw is None:
        return AutoMergeGateConditions(None, None, None)

    if not isinstance(raw, Mapping):
        raise AutoMergeConfigError(
            f"{_AUTO_MERGE_FIELD}.{_GATE_CONDITIONS_FIELD} must be a YAML "
            f"mapping; got {type(raw).__name__}: {raw!r} — write it as a nested "
            f"block of '{_MIN_ADOPTION_MONTHS_FIELD}' / "
            f"'{_MIN_COMPLETION_FIDELITY_FIELD}' / '{_MAX_RETRY_EXHAUSTION_FIELD}' "
            f"key/value pairs, not as a list or scalar"
        )

    return AutoMergeGateConditions(
        min_adoption_months=_resolve_min_adoption_months(raw),
        min_completion_fidelity=_resolve_fraction_gate(
            raw, _MIN_COMPLETION_FIDELITY_FIELD
        ),
        max_retry_exhaustion=_resolve_fraction_gate(raw, _MAX_RETRY_EXHAUSTION_FIELD),
    )


def _enforce_enabled_requires_gates(
    enabled: bool, gate_conditions: AutoMergeGateConditions
) -> None:
    """The headline loud-fail (AC-2): ``enabled: true`` requires all three gate
    conditions present and non-zero. Skipped entirely when disabled — blank
    gates are the legitimate TBD default while disabled.
    """
    if not enabled:
        return

    offending: list[str] = []
    if (
        gate_conditions.min_adoption_months is None
        or gate_conditions.min_adoption_months == 0
    ):
        offending.append(_MIN_ADOPTION_MONTHS_FIELD)
    if (
        gate_conditions.min_completion_fidelity is None
        or gate_conditions.min_completion_fidelity == 0.0
    ):
        offending.append(_MIN_COMPLETION_FIDELITY_FIELD)
    if (
        gate_conditions.max_retry_exhaustion is None
        or gate_conditions.max_retry_exhaustion == 0.0
    ):
        offending.append(_MAX_RETRY_EXHAUSTION_FIELD)

    if offending:
        raise AutoMergeConfigError(
            f"{_AUTO_MERGE_FIELD}.{_ENABLED_FIELD} is true but these gate "
            f"conditions are absent or zero-valued: {', '.join(offending)} — "
            f"auto-merge MUST NOT run without a non-zero adoption gate (PRD "
            f"line 748: thresholds TBD post-release data); set non-zero values "
            f"for all of {_MIN_ADOPTION_MONTHS_FIELD}, "
            f"{_MIN_COMPLETION_FIDELITY_FIELD}, {_MAX_RETRY_EXHAUSTION_FIELD} "
            f"under {_AUTO_MERGE_FIELD}.{_GATE_CONDITIONS_FIELD}, or set "
            f"{_AUTO_MERGE_FIELD}.{_ENABLED_FIELD}: false"
        )


def resolve_auto_merge_config(
    config: Mapping[str, Any] | None = None,
    *,
    default_enabled: bool = DEFAULT_AUTO_MERGE_ENABLED,
) -> AutoMergeConfig:
    """Resolve the ``auto_merge`` block from a config mapping (Story 17.1).

    Per-input contract:

    * ``config is None`` / ``auto_merge`` key absent / block value ``None`` →
      disabled config with blank gates (AC-3, the shipped default state).
    * ``auto_merge.enabled`` follows the **bool-only** discipline of
      :func:`loud_fail_harness.retry_budget.resolve_parallel_stories`
      (``type(value) is bool``; absent / ``None`` → ``default_enabled``).
    * ``min_adoption_months``: reject ``bool``; require ``int``; reject ``< 0``.
    * ``min_completion_fidelity`` / ``max_retry_exhaustion``: reject ``bool``;
      accept ``int`` | ``float`` coerced to ``float``; require range [0.0, 1.0].
    * Per-field shape validation runs FIRST, then the cross-field rule (AC-2):
      when ``enabled`` is true, all three gates must be present and non-zero,
      else :exc:`AutoMergeConfigError` naming the offending condition(s).
    """
    if config is None or _AUTO_MERGE_FIELD not in config:
        block: Any = None
    else:
        block = config[_AUTO_MERGE_FIELD]

    if block is None:
        resolved = AutoMergeConfig(
            enabled=default_enabled,
            gate_conditions=AutoMergeGateConditions(None, None, None),
        )
        _enforce_enabled_requires_gates(resolved.enabled, resolved.gate_conditions)
        return resolved

    if not isinstance(block, Mapping):
        raise AutoMergeConfigError(
            f"{_AUTO_MERGE_FIELD} must be a YAML mapping; got "
            f"{type(block).__name__}: {block!r} — write it as a nested block "
            f"with '{_ENABLED_FIELD}:' and '{_GATE_CONDITIONS_FIELD}:' keys, not "
            f"as a list or scalar"
        )

    enabled = _resolve_enabled(block, default_enabled)
    gate_conditions = _resolve_gate_conditions(block)
    _enforce_enabled_requires_gates(enabled, gate_conditions)
    return AutoMergeConfig(enabled=enabled, gate_conditions=gate_conditions)


def read_auto_merge_config_from_config_file(
    config_path: pathlib.Path,
    *,
    default_enabled: bool = DEFAULT_AUTO_MERGE_ENABLED,
) -> AutoMergeConfig:
    """Read the ``auto_merge`` block from a YAML config file (Story 17.1).

    The missing-file / empty-file / malformed-YAML / non-mapping contract is
    identical to
    :func:`loud_fail_harness.retry_budget.read_parallel_stories_from_config_file`
    (delegates value-shape + cross-field validation to
    :func:`resolve_auto_merge_config`). Uses :func:`yaml.safe_load` per the
    loud-fail security doctrine.
    """
    if not config_path.exists():
        return resolve_auto_merge_config(None, default_enabled=default_enabled)

    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AutoMergeConfigError(f"failed to read {config_path}: {exc}") from exc

    if not raw_text.strip():
        return resolve_auto_merge_config(None, default_enabled=default_enabled)

    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise AutoMergeConfigError(
            f"{config_path} is not valid YAML; parser error: {exc} — fix the "
            f"YAML syntax in {config_path} and re-run"
        ) from exc

    if parsed is None:
        return resolve_auto_merge_config(None, default_enabled=default_enabled)

    if not isinstance(parsed, Mapping):
        raise AutoMergeConfigError(
            f"{config_path} top-level must be a YAML mapping; got "
            f"{type(parsed).__name__}: {parsed!r} — write the file as key/value "
            f"pairs at the top level (an '{_AUTO_MERGE_FIELD}:' block), not as a "
            f"list or scalar"
        )

    return resolve_auto_merge_config(parsed, default_enabled=default_enabled)


__all__ = [
    "AutoMergeConfig",
    "AutoMergeConfigError",
    "AutoMergeGateConditions",
    "DEFAULT_AUTO_MERGE_ENABLED",
    "read_auto_merge_config_from_config_file",
    "resolve_auto_merge_config",
]
