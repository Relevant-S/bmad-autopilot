"""QA longitudinal flakiness threshold + ``flakiness-threshold-exceeded`` marker — FR-P2-8 (Story 20.3).

The threshold-evaluation **substrate** layered on Story 20.2's flakiness-log
persistence (:mod:`loud_fail_harness.qa_flakiness_log`). Story 20.2 landed the
gitignored, per-story, append-only corpus of per-AC pass/fail history accumulated
ACROSS runs; it deliberately emitted NO marker. THIS module lands the threshold
evaluated per AC on every QA run plus the ``flakiness-threshold-exceeded`` marker
that fires when an AC crosses it — surfacing real, longitudinal flakiness visibly
per the loud-fail doctrine (first-honest-failure parity for the across-runs axis)
instead of leaving it buried in a practitioner-local YAML no one reads.

Architectural template (clone :mod:`loud_fail_harness.qa_visual_regression` /
:mod:`loud_fail_harness.qa_a11y_audit`): the closest siblings — per-AC
QA-evidence markers that surface via a typed ``*_emissions`` envelope array + the
bundle's per-AC marker-comment render. Replicated discipline:

    * **Pure library, NOT a sixth substrate component.** ADR-003 enumerates
      exactly five substrate components; THIS module is a pure-library sibling
      consumed by the QA wrapper (``agents/qa.md``) + the bundle assembler — the
      same status :mod:`qa_flakiness_log` / :mod:`qa_plan_rederivation` hold.
      FOUR specialists / THREE hooks / FIVE components held.
    * ``decide_*`` **(always-returns-a-verdict)** — :func:`evaluate_ac_flakiness`
      returns a :class:`FlakinessThresholdDecision` for every AC (mirrors
      :func:`qa_visual_regression.decide_visual_regression_mode`).
    * ``surface_*`` **(Pattern-5 atomic-on-failure emission helper)** —
      :func:`surface_flakiness_threshold_exceeded` runs
      :func:`validate_marker_emission` FIRST; registry rejection raises
      :exc:`UnknownMarkerClass` before any state is constructed (mirrors
      :func:`qa_visual_regression.surface_visual_regression_delta_exceeded`).

Threshold semantics (AC-3 — designed, not guessed):
    An AC crosses the threshold when its **most-recent**
    ``threshold_consecutive_runs`` run records all exist AND each carries
    ``retry_count_within_run >= threshold_transient_fail_count``.
    ``retry_count_within_run`` is the ACTION-LEVEL / Playwright-native retry tier
    (prd.md line 1044) — the field Story 20.2 built precisely as the transient-
    flakiness signal ("a ``pass`` with non-zero ``retry_count_within_run`` is
    itself a flakiness signal"). It is the ONLY transient-fail predicate; the
    ``status`` field is intentionally NOT consulted. A clean deterministic fail
    (``status: fail``, ``retry_count_within_run: 0``) is NOT flakiness — it is
    breakage the AC verdict already surfaces; flakiness is *intermittency*, not
    breakage, so it does NOT qualify a run. The default (``3`` consecutive runs,
    each with ``>= 1`` action-level retry) is the PRD-stated default and remains
    tunable per-project via the two ``flakiness:`` qa-runbook knobs.

Sensor-not-advisor (PRD-level invariant + Pattern 5):
    This library RETURNS the decision + (on exceed) the emission record. It does
    NOT write the flakiness log (the wrapper owns the Story 20.2
    ``append_run_record`` / ``persist_flakiness_log`` write), does NOT emit
    markers to event logs (the record is data the wrapper rides on the envelope),
    does NOT print, and does NOT flip ``ac_results`` or contribute to the
    wrapper-level ``status``. The threshold marker is story-level evidence; the
    orchestrator's flow policy decides what a fired marker means.

Cross-component reuse posture:
    * Pydantic v2 — REUSED (already pinned). No new runtime dependency.
    * :mod:`loud_fail_harness.qa_flakiness_log` — REUSED UNCHANGED for the
      :class:`FlakinessAcHistory` / :class:`FlakinessRunRecord` shapes
      :func:`evaluate_ac_flakiness` reads.
    * :mod:`loud_fail_harness.specialist_dispatch` — REUSED for
      :class:`MarkerClassRegistry` + :func:`validate_marker_emission`.
    * :mod:`loud_fail_harness.input_hardening` — REUSED for
      :func:`harden_identifier` on ``story_id`` / ``ac_id``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loud_fail_harness.input_hardening import harden_identifier
from loud_fail_harness.qa_flakiness_log import FlakinessAcHistory
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

#: The marker class identifier emitted when an AC crosses the threshold. Consumed
#: AS-IS from ``schemas/marker-taxonomy.yaml``; THIS module is its sole runtime
#: emitter. Mirrors Story 20.1's ``PLAN_REDERIVATION_DRIFT_DETECTED_MARKER``.
FLAKINESS_THRESHOLD_EXCEEDED_MARKER: Final[
    Literal["flakiness-threshold-exceeded"]
] = "flakiness-threshold-exceeded"

#: PRD-stated default: an AC must carry a transient fail on this many consecutive
#: runs before the threshold is crossed (prd.md FR-P2-8 / line 186).
DEFAULT_THRESHOLD_CONSECUTIVE_RUNS: Final[int] = 3

#: PRD-stated default: the per-run action-level retry count at or above which a
#: run record counts as a transient fail.
DEFAULT_THRESHOLD_TRANSIENT_FAIL_COUNT: Final[int] = 1


class FlakinessThresholdConfig(BaseModel):
    """The two threshold knobs, parsed from the optional qa-runbook ``flakiness:``
    block (AC-1).

    Numeric-only: both fields are ``int`` range-validated by ``Field(ge=1)`` —
    that constraint IS the loud-fail guard on malformed values (a ``< 1`` knob
    raises :exc:`pydantic.ValidationError` at construction). There is NO string
    hostile-input surface, so the input-hardening registry records it with empty
    buckets (the ``qa_visual_regression.VisualDiffResult`` precedent).

    Absence of the ``flakiness:`` block is NOT a marker — it means "defaults
    apply" (FR42 user-owned-file discipline); :func:`load_flakiness_threshold_config`
    returns the all-defaults instance.

    Frozen for determinism + hashability; field declaration order is load-bearing
    for byte-stable ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    threshold_consecutive_runs: int = Field(
        default=DEFAULT_THRESHOLD_CONSECUTIVE_RUNS, ge=1
    )
    threshold_transient_fail_count: int = Field(
        default=DEFAULT_THRESHOLD_TRANSIENT_FAIL_COUNT, ge=1
    )


class FlakinessThresholdDecision(BaseModel):
    """The always-returned per-AC verdict of :func:`evaluate_ac_flakiness`
    (mirrors :class:`qa_visual_regression.VisualRegressionDecision`).

    Field semantics:
        * ``ac_id`` — the acceptance-criterion the verdict scopes to.
        * ``exceeded`` — ``True`` IFF the AC's trailing transient-fail streak
          reaches ``threshold_consecutive_runs`` (AC-3).
        * ``consecutive_transient_fail_runs`` — the length of the current trailing
          transient-fail streak (the diagnostic; reported on every AC, exceed or
          not). ``ac_id`` here comes from the parsed-plan history boundary, not
          raw external ingress, so it is internal_only (NOT re-hardened).

    Frozen for determinism + hashability; field declaration order load-bearing.
    """

    model_config = ConfigDict(frozen=True)

    ac_id: str = Field(min_length=1)
    exceeded: bool
    consecutive_transient_fail_runs: int = Field(ge=0)


class FlakinessThresholdDiagnosticContext(BaseModel):
    """The diagnostic context carried on the ``flakiness-threshold-exceeded``
    marker emission (mirrors
    :class:`qa_visual_regression.VisualRegressionDiagnosticContext`, AC-scoped).

    Field semantics:
        * ``story_id`` — the BMAD story identifier the dispatch is scoped to (raw
          external-ingress; hardened).
        * ``ac_id`` — the acceptance-criterion that crossed the threshold (supplied
          by the wrapper from the dispatch AC list; hardened defensively).
        * ``consecutive_transient_fail_runs`` — the trailing transient-fail streak
          length at the crossing (an ``int`` — not a hostile-text surface, so NOT
          routed through ``harden_identifier``).

    Frozen for hashability + determinism; field declaration order load-bearing for
    byte-stable ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    ac_id: str = Field(min_length=1)
    consecutive_transient_fail_runs: int = Field(ge=0)

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> "FlakinessThresholdDiagnosticContext":
        """Input-hardening (Story 24.2 discipline). ``min_length=1`` accepts
        ``"   "``; route ``story_id`` / ``ac_id`` through the shared helper to
        reject whitespace-only / embedded-newline / null-byte values.
        ``consecutive_transient_fail_runs`` is an int — not a hostile-text surface.
        """
        harden_identifier(self.story_id, "FlakinessThresholdDiagnosticContext.story_id")
        harden_identifier(self.ac_id, "FlakinessThresholdDiagnosticContext.ac_id")
        return self


class FlakinessThresholdEmissionRecord(BaseModel):
    """One ``flakiness-threshold-exceeded`` emission record. Byte-mirrors the
    envelope ``$defs/flakiness_emission`` AC-scoped shape (``marker_class`` +
    ``ac_id``), flat-mirroring
    :class:`qa_visual_regression.VisualRegressionDeltaExceededEmissionRecord`.
    Frozen + field-order-load-bearing for byte-stable ``model_dump_json()``.
    """

    model_config = ConfigDict(frozen=True)

    marker_class: Literal["flakiness-threshold-exceeded"]
    ac_id: str = Field(min_length=1)


class FlakinessThresholdEmission(BaseModel):
    """The atomic-emission return shape of
    :func:`surface_flakiness_threshold_exceeded`. Mirrors
    :class:`qa_visual_regression.VisualRegressionDeltaExceededEmission` —
    co-exposes the diagnostic context alongside the marker record.
    """

    model_config = ConfigDict(frozen=True)

    marker_record: FlakinessThresholdEmissionRecord
    diagnostic_context: FlakinessThresholdDiagnosticContext


def load_flakiness_threshold_config(
    runbook: Mapping[str, Any] | None,
) -> FlakinessThresholdConfig:
    """Read the optional ``flakiness:`` block from a parsed qa-runbook mapping and
    return the threshold config.

    Absent runbook / absent ``flakiness:`` block → the all-defaults config (AC-1
    absence-is-not-a-marker; mirrors the ``masked_selectors`` / ``heuristics`` /
    ``a11y`` absence-of-marker posture). When present, the two ``int`` knobs are
    range-validated by ``Field(ge=1)`` — a ``< 1`` value raises
    :exc:`pydantic.ValidationError` (loud-fail).

    Raises:
        ValueError: the ``flakiness:`` key is present but is not a mapping (a
            malformed runbook — loud-fail rather than silently ignore it).
        pydantic.ValidationError: a knob is present but ``< 1``.
    """
    if runbook is None:
        return FlakinessThresholdConfig()
    block = runbook.get("flakiness")
    if block is None:
        return FlakinessThresholdConfig()
    if not isinstance(block, Mapping):
        raise ValueError(
            f"qa-runbook 'flakiness' block must be a mapping; got "
            f"{type(block).__name__}"
        )
    return FlakinessThresholdConfig(
        **{
            key: block[key]
            for key in (
                "threshold_consecutive_runs",
                "threshold_transient_fail_count",
            )
            if key in block
        }
    )


def evaluate_ac_flakiness(
    history: FlakinessAcHistory,
    config: FlakinessThresholdConfig,
) -> FlakinessThresholdDecision:
    """Evaluate the consecutive-transient-fail threshold for one AC (AC-3). Pure;
    no I/O.

    Walks ``history.runs`` (ordered oldest→newest per Story 20.2) from the newest
    record backwards, counting the trailing streak of records whose
    ``retry_count_within_run >= config.threshold_transient_fail_count``. The AC is
    ``exceeded`` IFF that streak reaches ``config.threshold_consecutive_runs`` —
    which holds exactly when the most-recent ``threshold_consecutive_runs`` records
    all exist AND all are transient fails (fewer-than-threshold histories can never
    reach the streak length, so they are never exceeded).

    ``status`` is intentionally not consulted (AC-3): the transient-fail predicate
    is purely the action-level ``retry_count_within_run`` — a ``pass`` with a
    non-zero retry IS a transient fail, a clean deterministic ``fail`` with zero
    retries is NOT.
    """
    streak = 0
    for record in reversed(history.runs):
        if record.retry_count_within_run >= config.threshold_transient_fail_count:
            streak += 1
        else:
            break
    return FlakinessThresholdDecision(
        ac_id=history.ac_id,
        exceeded=streak >= config.threshold_consecutive_runs,
        consecutive_transient_fail_runs=streak,
    )


def surface_flakiness_threshold_exceeded(
    story_id: str,
    ac_id: str,
    registry: MarkerClassRegistry,
    consecutive_transient_fail_runs: int,
) -> FlakinessThresholdEmission:
    """Atomic-on-failure ``flakiness-threshold-exceeded`` emission helper.

    Mirrors :func:`qa_visual_regression.surface_visual_regression_delta_exceeded`
    AS-IS: :func:`validate_marker_emission` runs FIRST; on registry rejection
    :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass` propagates per
    Pattern 5 BEFORE any partial state is constructed.

    Pure: no file I/O, no event-log write — the emission record is data the wrapper
    rides on the envelope's ``flakiness_emissions`` array; the bundle assembler
    renders the marker comment. Sensor-not-advisor: surfaces the longitudinal
    flakiness for the human; does NOT flip the AC verdict.

    Raises:
        UnknownMarkerClass: registry does not contain
            ``"flakiness-threshold-exceeded"``.
    """
    validate_marker_emission(registry, FLAKINESS_THRESHOLD_EXCEEDED_MARKER)
    diagnostic_context = FlakinessThresholdDiagnosticContext(
        story_id=story_id,
        ac_id=ac_id,
        consecutive_transient_fail_runs=consecutive_transient_fail_runs,
    )
    marker_record = FlakinessThresholdEmissionRecord(
        marker_class=FLAKINESS_THRESHOLD_EXCEEDED_MARKER,
        ac_id=ac_id,
    )
    return FlakinessThresholdEmission(
        marker_record=marker_record,
        diagnostic_context=diagnostic_context,
    )


__all__ = [
    "DEFAULT_THRESHOLD_CONSECUTIVE_RUNS",
    "DEFAULT_THRESHOLD_TRANSIENT_FAIL_COUNT",
    "FLAKINESS_THRESHOLD_EXCEEDED_MARKER",
    "FlakinessThresholdConfig",
    "FlakinessThresholdDecision",
    "FlakinessThresholdDiagnosticContext",
    "FlakinessThresholdEmission",
    "FlakinessThresholdEmissionRecord",
    "evaluate_ac_flakiness",
    "load_flakiness_threshold_config",
    "surface_flakiness_threshold_exceeded",
]
