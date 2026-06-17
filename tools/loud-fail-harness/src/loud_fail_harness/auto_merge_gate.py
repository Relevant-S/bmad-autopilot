"""Story 17.2 — Auto-merge gate-condition evaluator + ``auto-merge-gate-not-met`` marker (FR-P2-3).

The SECOND of Epic 17's three stories. It reads the 17.1-resolved
:class:`~loud_fail_harness.auto_merge_config.AutoMergeConfig` plus a new
maintainer-curated ``_bmad-output/metrics/adoption-metrics.yaml`` record,
computes pass/fail per gate, and surfaces the observability marker
``auto-merge-gate-not-met`` whenever a configured gate is unmet — so auto-merge
is gated **by data, not by intention**, with continuous loud-fail visibility.

It lands the **evaluator + its observability marker only**. NO merge behaviour:
no ``gh pr merge`` / ``git merge`` / push (17.3), no Stop-hook bash change / 4th
hook (17.3), no ``auto-merge-skipped`` marker (17.3), no mutation of the 17.1
resolver (consumed read-only). The evaluator returns a structured **decision**
(a sensor envelope, not a recommendation) that 17.3 consumes to drive the merge
and the skip signal.

Design (ratify-or-override in review): **plain frozen dataclasses + imperative
validation**, mirroring the directly-consumed 17.1
:mod:`loud_fail_harness.auto_merge_config` resolver rather than the Pydantic
flakiness sibling. Rationale: this keeps Epic 17's config-and-gate surface
internally consistent (one validation idiom across 17.1/17.2), and the metrics
model is numeric-only (no string / path hostile-input surface), so a Pydantic
``BaseModel`` would couple the module to the ``input-hardening-gate`` model
registry for no value — exactly the trade-off 17.1's module docstring records.
Whichever route, NaN / Inf are rejected explicitly (``math.isnan`` /
``math.isinf``): ``nan >= threshold`` and ``nan <= threshold`` both silently
evaluate ``False``, which would mask a malformed gate as a quiet failure instead
of a loud one.

Comparison semantics (1:1 with the 17.1 gate triple — ``prd.md`` line 748):
    * ``min_adoption_months`` ⇒ pass iff ``adoption_months >= threshold``.
    * ``min_completion_fidelity`` ⇒ pass iff ``completion_fidelity >= threshold``.
    * ``max_retry_exhaustion`` ⇒ pass iff ``retry_exhaustion <= threshold``
      (the INVERTED direction — it is a ceiling).

Sources:
    * **Story 17.2 epic AC** at ``epics-phase-2.md`` lines 552-566.
    * **PRD FR-P2-3** (``prd.md`` line 946) + **Scope Decisions** (line 748).
    * **NFR-S3** (``prd.md`` line 1006) — remote push opt-in, three audited slices.

Pattern compliance (architecture.md → Implementation Patterns):
    * **Pattern 1** — snake_case structural keys (``adoption_months`` /
      ``completion_fidelity`` / ``retry_exhaustion``); snake_case functions.
    * **Pattern 2** — ``auto-merge-gate-not-met`` is the new ``marker_class``
      landed in ``schemas/marker-taxonomy.yaml``.
    * **Pattern 5 (loud-fail)** — :class:`AutoMergeGateError` raises on
      missing / malformed / out-of-range / NaN / Inf metrics when gates are
      configured; :func:`surface_auto_merge_gate_not_met` runs
      :func:`validate_marker_emission` FIRST (atomic-on-failure).
    * **Sensor-not-advisor** — the marker is INFORMATIONAL; emitting it does
      NOT flip a wrapper status or change ``current_state`` (mirrors
      ``sprint-escalation-rate-exceeded`` / ``flakiness-threshold-exceeded``).
"""

from __future__ import annotations

import math
import pathlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal

import yaml

from loud_fail_harness.auto_merge_config import AutoMergeConfig
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

#: The marker class emitted when a configured gate is unmet. Consumed AS-IS from
#: ``schemas/marker-taxonomy.yaml``; THIS module is its sole runtime emitter.
#: Mirrors Story 20.3's ``FLAKINESS_THRESHOLD_EXCEEDED_MARKER`` constant.
AUTO_MERGE_GATE_NOT_MET_MARKER: Final[
    Literal["auto-merge-gate-not-met"]
] = "auto-merge-gate-not-met"

#: Overall decision status. ``green`` — all configured gates pass;
#: ``gate-not-met`` — at least one configured gate fails; ``not-configured`` —
#: all three gate conditions blank/TBD (the shipped default; nothing to evaluate).
GateStatus = Literal["green", "gate-not-met", "not-configured"]

#: adoption-metrics document field names (Pattern 1 snake_case).
_SCHEMA_VERSION_FIELD: str = "schema_version"
_SCHEMA_VERSION_VALUE: str = "1.0"
_ADOPTION_MONTHS_FIELD: str = "adoption_months"
_COMPLETION_FIDELITY_FIELD: str = "completion_fidelity"
_RETRY_EXHAUSTION_FIELD: str = "retry_exhaustion"

#: Default maintainer-curated metrics path (cwd-relative; the Stop hook runs from
#: the user's project root). Single-sourced so the reader default and any future
#: consumer default cannot drift.
DEFAULT_ADOPTION_METRICS_PATH: Final[pathlib.Path] = pathlib.Path(
    "_bmad-output/metrics/adoption-metrics.yaml"
)


class AutoMergeGateError(ValueError):
    """Raised on a missing / malformed / out-of-range / NaN / Inf adoption-metrics
    record when gate conditions ARE configured (the only state where the file is
    consulted) — you cannot pass a data gate with no data.

    The ``ValueError`` lineage mirrors
    :class:`loud_fail_harness.auto_merge_config.AutoMergeConfigError`. A red gate
    is NOT an error (it is data the decision carries); only malformed/absent
    metrics raise. Message format (FR48a / NFR-O5 actionable-pointer posture):
    include the offending field / value and a remediation hint pointing at
    ``_bmad-output/metrics/adoption-metrics.yaml``.
    """


@dataclass(frozen=True)
class AdoptionMetrics:
    """Resolved maintainer-curated reference-project metrics (the
    ``adoption-metrics.yaml`` record), 1:1 with the 17.1 gate triple.
    """

    adoption_months: int
    completion_fidelity: float
    retry_exhaustion: float


@dataclass(frozen=True)
class GateVerdict:
    """One gate's pass/fail verdict with the current-value / threshold pair that
    produced it — enough that an operator pasting the diagnostic knows exactly
    which metric fell short and by how much.
    """

    gate_name: str
    metric_field: str
    current_value: float
    threshold: float
    comparison: Literal[">=", "<="]
    passed: bool


@dataclass(frozen=True)
class AutoMergeGateDecision:
    """The always-returned structured decision (a sensor envelope, not a
    recommendation). ``status`` is the overall verdict; ``verdicts`` carries one
    :class:`GateVerdict` per CONFIGURED gate (empty when ``not-configured``).
    """

    status: GateStatus
    verdicts: tuple[GateVerdict, ...]

    @property
    def failing_verdicts(self) -> tuple[GateVerdict, ...]:
        return tuple(verdict for verdict in self.verdicts if not verdict.passed)


@dataclass(frozen=True)
class AutoMergeGateNotMetEmission:
    """The atomic-emission return shape of
    :func:`surface_auto_merge_gate_not_met` — the marker class, the
    runtime-filled per-gate ``diagnostic_pointer`` (names each failing gate,
    its current value, and the required threshold), and the failing verdicts.
    """

    marker_class: Literal["auto-merge-gate-not-met"]
    diagnostic_pointer: str
    failing_gates: tuple[GateVerdict, ...]


def _reject_non_finite(value: float, field: str) -> None:
    if math.isnan(value):
        raise AutoMergeGateError(
            f"adoption-metrics {field} is NaN (.nan) — a NaN metric silently "
            f"fails every threshold comparison rather than loud-failing; set "
            f"{field} to a real number in adoption-metrics.yaml"
        )
    if math.isinf(value):
        raise AutoMergeGateError(
            f"adoption-metrics {field} is infinite — set {field} to a finite "
            f"number in adoption-metrics.yaml"
        )


def _resolve_adoption_months(metrics: Mapping[str, Any]) -> int:
    if _ADOPTION_MONTHS_FIELD not in metrics:
        raise AutoMergeGateError(
            f"adoption-metrics is missing required field "
            f"'{_ADOPTION_MONTHS_FIELD}' — add it (e.g. "
            f"'{_ADOPTION_MONTHS_FIELD}: 6') to adoption-metrics.yaml"
        )

    value = metrics[_ADOPTION_MONTHS_FIELD]
    if isinstance(value, bool):
        raise AutoMergeGateError(
            f"adoption-metrics {_ADOPTION_MONTHS_FIELD} must be an integer >= 0; "
            f"got {value!r} (bool) — booleans are rejected to avoid YAML "
            f"truthy-coercion ambiguity; write it as an unquoted integer"
        )
    if type(value) is not int:
        raise AutoMergeGateError(
            f"adoption-metrics {_ADOPTION_MONTHS_FIELD} must be a YAML int; got "
            f"{value!r} ({type(value).__name__}) — write it as an unquoted "
            f"integer (e.g. '{_ADOPTION_MONTHS_FIELD}: 6')"
        )
    if value < 0:
        raise AutoMergeGateError(
            f"adoption-metrics {_ADOPTION_MONTHS_FIELD} must be >= 0; got "
            f"{value!r} — adoption duration cannot be negative"
        )
    return value


def _resolve_fraction_metric(metrics: Mapping[str, Any], field: str) -> float:
    if field not in metrics:
        raise AutoMergeGateError(
            f"adoption-metrics is missing required field '{field}' — add it "
            f"(e.g. '{field}: 0.9') to adoption-metrics.yaml"
        )

    value = metrics[field]
    if isinstance(value, bool):
        raise AutoMergeGateError(
            f"adoption-metrics {field} must be a number in [0.0, 1.0]; got "
            f"{value!r} (bool) — booleans are rejected to avoid YAML "
            f"truthy-coercion ambiguity; write it as an unquoted fraction"
        )
    if type(value) not in (int, float):
        raise AutoMergeGateError(
            f"adoption-metrics {field} must be a YAML number; got {value!r} "
            f"({type(value).__name__}) — write it as an unquoted fraction "
            f"(e.g. '{field}: 0.9')"
        )

    coerced = float(value)
    _reject_non_finite(coerced, field)
    if not (0.0 <= coerced <= 1.0):
        raise AutoMergeGateError(
            f"adoption-metrics {field} must be in the range [0.0, 1.0]; got "
            f"{value!r} — fidelity / exhaustion rates are fractions of 1"
        )
    return coerced


def resolve_adoption_metrics(metrics: Mapping[str, Any]) -> AdoptionMetrics:
    """Validate a parsed adoption-metrics mapping into an :class:`AdoptionMetrics`.

    Per-field contract (mirrors
    :func:`loud_fail_harness.auto_merge_config.resolve_auto_merge_config`):
    ``schema_version`` must equal ``"1.0"``; ``adoption_months`` rejects ``bool``
    and requires a non-negative ``int``; ``completion_fidelity`` /
    ``retry_exhaustion`` reject ``bool``, accept ``int`` | ``float`` coerced to
    ``float``, reject NaN / Inf, and require the range [0.0, 1.0]. Any violation
    raises :exc:`AutoMergeGateError`.
    """
    schema_version = metrics.get(_SCHEMA_VERSION_FIELD)
    if schema_version != _SCHEMA_VERSION_VALUE:
        raise AutoMergeGateError(
            f"adoption-metrics {_SCHEMA_VERSION_FIELD} must be "
            f"'{_SCHEMA_VERSION_VALUE}'; got {schema_version!r} — set "
            f"'{_SCHEMA_VERSION_FIELD}: \"{_SCHEMA_VERSION_VALUE}\"' in "
            f"adoption-metrics.yaml"
        )
    return AdoptionMetrics(
        adoption_months=_resolve_adoption_months(metrics),
        completion_fidelity=_resolve_fraction_metric(
            metrics, _COMPLETION_FIDELITY_FIELD
        ),
        retry_exhaustion=_resolve_fraction_metric(metrics, _RETRY_EXHAUSTION_FIELD),
    )


def read_adoption_metrics(metrics_path: pathlib.Path) -> AdoptionMetrics:
    """Read + validate the maintainer-curated adoption-metrics file.

    Unlike the 17.1 config reader (which treats absence as a legitimate default),
    this reader is invoked ONLY when gate conditions are configured, so an absent
    / empty / malformed file is a LOUD FAIL (:exc:`AutoMergeGateError`) — you
    cannot pass a data gate with no data. Uses :func:`yaml.safe_load` per the
    loud-fail security doctrine.
    """
    if not metrics_path.exists():
        raise AutoMergeGateError(
            f"auto_merge.gate_conditions are configured but the adoption-metrics "
            f"file {metrics_path} does not exist — a data gate cannot pass "
            f"without data; create {metrics_path} (see schemas/adoption-metrics.yaml) "
            f"or clear auto_merge.gate_conditions"
        )

    try:
        raw_text = metrics_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AutoMergeGateError(
            f"failed to read adoption-metrics file {metrics_path}: {exc}"
        ) from exc

    if not raw_text.strip():
        raise AutoMergeGateError(
            f"auto_merge.gate_conditions are configured but the adoption-metrics "
            f"file {metrics_path} is empty — populate it (see "
            f"schemas/adoption-metrics.yaml) or clear auto_merge.gate_conditions"
        )

    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise AutoMergeGateError(
            f"{metrics_path} is not valid YAML; parser error: {exc} — fix the "
            f"YAML syntax and re-run"
        ) from exc

    if not isinstance(parsed, Mapping):
        raise AutoMergeGateError(
            f"{metrics_path} top-level must be a YAML mapping; got "
            f"{type(parsed).__name__}: {parsed!r} — write the file as "
            f"'{_ADOPTION_MONTHS_FIELD}:' / '{_COMPLETION_FIDELITY_FIELD}:' / "
            f"'{_RETRY_EXHAUSTION_FIELD}:' key/value pairs"
        )

    return resolve_adoption_metrics(parsed)


def _gates_unconfigured(config: AutoMergeConfig) -> bool:
    gates = config.gate_conditions
    return (
        gates.min_adoption_months is None
        and gates.min_completion_fidelity is None
        and gates.max_retry_exhaustion is None
    )


def evaluate_auto_merge_gate(
    config: AutoMergeConfig, metrics: AdoptionMetrics
) -> AutoMergeGateDecision:
    """Compute the per-gate pass/fail decision (AC-2/3/4). Pure; no I/O.

    When all three gate conditions are ``None`` (blank/TBD — the shipped
    default), returns ``not-configured`` with no verdicts (``metrics`` ignored —
    the caller should not even read the file in this case; see
    :func:`resolve_and_evaluate_auto_merge_gate`). Otherwise builds one
    :class:`GateVerdict` per CONFIGURED gate (a ``None`` gate is skipped, the
    legitimate ``enabled: false`` partial-configuration state the 17.1 resolver
    permits) and aggregates: ``gate-not-met`` iff any configured gate fails, else
    ``green``.

    ALWAYS returns a decision; NEVER raises on a red gate — a red gate is data,
    not an error. (Malformed/absent metrics raise at the reader, not here.)
    """
    if _gates_unconfigured(config):
        return AutoMergeGateDecision(status="not-configured", verdicts=())

    gates = config.gate_conditions
    verdicts: list[GateVerdict] = []

    if gates.min_adoption_months is not None:
        threshold = float(gates.min_adoption_months)
        current = float(metrics.adoption_months)
        verdicts.append(
            GateVerdict(
                gate_name="min_adoption_months",
                metric_field=_ADOPTION_MONTHS_FIELD,
                current_value=current,
                threshold=threshold,
                comparison=">=",
                passed=current >= threshold,
            )
        )

    if gates.min_completion_fidelity is not None:
        threshold = gates.min_completion_fidelity
        current = metrics.completion_fidelity
        verdicts.append(
            GateVerdict(
                gate_name="min_completion_fidelity",
                metric_field=_COMPLETION_FIDELITY_FIELD,
                current_value=current,
                threshold=threshold,
                comparison=">=",
                passed=current >= threshold,
            )
        )

    if gates.max_retry_exhaustion is not None:
        threshold = gates.max_retry_exhaustion
        current = metrics.retry_exhaustion
        verdicts.append(
            GateVerdict(
                gate_name="max_retry_exhaustion",
                metric_field=_RETRY_EXHAUSTION_FIELD,
                current_value=current,
                threshold=threshold,
                comparison="<=",
                passed=current <= threshold,
            )
        )

    status: GateStatus = (
        "gate-not-met" if any(not v.passed for v in verdicts) else "green"
    )
    return AutoMergeGateDecision(status=status, verdicts=tuple(verdicts))


def resolve_and_evaluate_auto_merge_gate(
    config: AutoMergeConfig,
    *,
    metrics_path: pathlib.Path = DEFAULT_ADOPTION_METRICS_PATH,
) -> AutoMergeGateDecision:
    """Orchestration helper: short-circuit on ``not-configured`` (the metrics
    file is NEVER read on the default install), else read + validate the metrics
    (loud-fail on missing/malformed) and evaluate.

    This is the Stop-hook substrate entry the bundle assembler's ``main`` calls
    at EVERY per-story invocation (AC-4 continuous observability) regardless of
    ``config.enabled``.
    """
    if _gates_unconfigured(config):
        return AutoMergeGateDecision(status="not-configured", verdicts=())
    metrics = read_adoption_metrics(metrics_path)
    return evaluate_auto_merge_gate(config, metrics)


def _render_diagnostic_pointer(failing: tuple[GateVerdict, ...]) -> str:
    clauses = [
        f"{v.gate_name} (reference {v.metric_field}={_fmt(v.current_value)} "
        f"fails required {v.comparison} {_fmt(v.threshold)})"
        for v in failing
    ]
    return (
        "auto-merge gate(s) not met: "
        + "; ".join(clauses)
        + ". Remediation: curate _bmad-output/metrics/adoption-metrics.yaml so "
        "the reference metrics meet the gate, or tune auto_merge.gate_conditions "
        "in _bmad/automation/config.yaml. INFORMATIONAL (sensor-not-advisor) — "
        "does not change run state; 17.3 decides what a fired marker means."
    )


def _fmt(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return repr(value)


def surface_auto_merge_gate_not_met(
    decision: AutoMergeGateDecision,
    registry: MarkerClassRegistry,
) -> AutoMergeGateNotMetEmission:
    """Atomic-on-failure ``auto-merge-gate-not-met`` emission helper (Pattern 5).

    Mirrors :func:`loud_fail_harness.qa_flakiness_threshold.surface_flakiness_threshold_exceeded`:
    :func:`validate_marker_emission` runs FIRST; on registry rejection
    :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass` propagates
    BEFORE any partial state is constructed. Pure: no file I/O, no event-log
    write — the emission is data the assembler renders.

    Raises:
        ValueError: ``decision.status`` is not ``gate-not-met`` (nothing to
            emit — the caller must check before calling).
        UnknownMarkerClass: registry does not contain ``auto-merge-gate-not-met``.
    """
    if decision.status != "gate-not-met":
        raise ValueError(
            f"surface_auto_merge_gate_not_met called with status "
            f"{decision.status!r}; the marker is only emitted on 'gate-not-met'"
        )
    validate_marker_emission(registry, AUTO_MERGE_GATE_NOT_MET_MARKER)
    failing = decision.failing_verdicts
    return AutoMergeGateNotMetEmission(
        marker_class=AUTO_MERGE_GATE_NOT_MET_MARKER,
        diagnostic_pointer=_render_diagnostic_pointer(failing),
        failing_gates=failing,
    )


__all__ = [
    "AUTO_MERGE_GATE_NOT_MET_MARKER",
    "DEFAULT_ADOPTION_METRICS_PATH",
    "AdoptionMetrics",
    "AutoMergeGateDecision",
    "AutoMergeGateError",
    "AutoMergeGateNotMetEmission",
    "GateStatus",
    "GateVerdict",
    "evaluate_auto_merge_gate",
    "read_adoption_metrics",
    "resolve_adoption_metrics",
    "resolve_and_evaluate_auto_merge_gate",
    "surface_auto_merge_gate_not_met",
]
