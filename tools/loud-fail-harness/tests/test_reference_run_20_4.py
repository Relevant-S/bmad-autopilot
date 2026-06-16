"""Epic-20 reference-run replay witness (Story 20.4 / FR-P2-8 + FR-P2-9).

This is the ONE harness touch Story 20.4 makes (AC-7 / AC-11), and the
maintainer-ratified strengthening over the 9.6/10.7/13.7/19.6 Debug-Log-only
proof: where those QA-coverage reference runs rest on LLM-driven heuristic
dispatch (un-replayable), the Epic-20 verdicts come from PURE, DETERMINISTIC
substrate (``qa_plan_rederivation.surface_plan_rederivation_cross_check`` +
``qa_flakiness_threshold.evaluate_ac_flakiness``), so the captured records can be
CI-pinned against the real code rather than merely schema-shaped.

This module is a pure CONSUMER of the landed runtime: it adds NO
``src/loud_fail_harness/*.py`` module and modifies none (the substrate-component
count stays FIVE per ADR-003), and it reads ``docs/reference-runs/20-4-web/`` as
DATA — introducing no runtime↔harness cross-reference (``pluggability-gate``
stays green). It pins that the committed reference artifacts remain
substrate-faithful if either the artifacts or the Epic-20 substrate ever drift.

It replays three witnesses:
  * the committed flakiness-corpus snapshot ``qa-flakiness-log.yaml`` through the
    real ``load_flakiness_log`` / ``validate_flakiness_log`` + ``evaluate_ac_flakiness``
    — proving the flaky AC (AC-2) crosses the default threshold and the clean
    control AC (AC-1) does not, and that the primary envelope's
    ``flakiness_emissions`` names exactly the exceeded AC(s);
  * the FR-P2-9 cross-check on its GREEN branch — an identical persisted/re-derived
    plan pair yields ``cross_check_status == "green"``, matching ``qa-envelope.yaml``;
  * the FR-P2-9 cross-check on its DRIFT branch — a plan pair differing only at
    AC-2's ``heuristic_applicability`` yields ``drift-detected`` with
    ``drift_surfaces == ("heuristic_applicability",)`` and ``drifted_ac_ids == ("AC-2",)``,
    matching ``qa-envelope-rederivation-drift.yaml``.
"""

from __future__ import annotations

import pathlib
import shutil
from collections import Counter

import pytest
import yaml

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.qa_behavioral_plan import (
    QABehavioralPlan,
    QABehavioralPlanEntry,
)
from loud_fail_harness.qa_flakiness_log import (
    FlakinessAcHistory,
    FlakinessLog,
    compute_flakiness_log_path,
    load_flakiness_log,
    validate_flakiness_log,
)
from loud_fail_harness.qa_flakiness_threshold import (
    FLAKINESS_THRESHOLD_EXCEEDED_MARKER,
    FlakinessThresholdConfig,
    evaluate_ac_flakiness,
)
from loud_fail_harness.qa_plan_rederivation import (
    PLAN_REDERIVATION_DRIFT_DETECTED_MARKER,
    surface_plan_rederivation_cross_check,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)

_STORY_ID = "sample-qa-coverage-001"
_FLAKY_AC = "AC-2"
_CONTROL_AC = "AC-1"
_CONTROL_AC_HEURISTICS = ("empty-state",)


@pytest.fixture(scope="module")
def reference_dir() -> pathlib.Path:
    return find_repo_root() / "docs" / "reference-runs" / "20-4-web"


@pytest.fixture(scope="module")
def marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


def _load_yaml(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _entry(
    ac_id: str, *, heuristics: tuple[str, ...] = ()
) -> QABehavioralPlanEntry:
    return QABehavioralPlanEntry(
        ac_id=ac_id,
        assertion_shape=f"{ac_id} holds",
        expected_evidence_tier="tier-1-mechanical",  # type: ignore[arg-type]
        semantic_verification_requirement="not_applicable",  # type: ignore[arg-type]
        heuristic_applicability=heuristics,  # type: ignore[arg-type]
    )


def _plan(entries: tuple[QABehavioralPlanEntry, ...]) -> QABehavioralPlan:
    return QABehavioralPlan(
        plan_status="generated",
        ac_hash="a" * 64,
        entries=entries,
    )


# --------------------------------------------------------------------------- #
# FR-P2-8 — the committed flakiness corpus replays through the real substrate  #
# --------------------------------------------------------------------------- #


def test_corpus_snapshot_validates_against_unmodified_schema(
    reference_dir: pathlib.Path,
) -> None:
    """AC-6/AC-7: the committed snapshot is schema-faithful via the real
    path-based validator (exit 0 == valid)."""
    assert validate_flakiness_log(reference_dir / "qa-flakiness-log.yaml") == 0


def test_corpus_snapshot_loads_via_real_loader(
    reference_dir: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """AC-7: the committed snapshot is substrate-faithful via the real
    ``load_flakiness_log`` (the gitignored-store loader), exercised by staging
    the snapshot at the path the loader computes for the story."""
    staged = compute_flakiness_log_path(_STORY_ID, repo_root=tmp_path)
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(reference_dir / "qa-flakiness-log.yaml", staged)

    loaded = load_flakiness_log(_STORY_ID, repo_root=tmp_path)

    assert loaded is not None
    assert loaded.story_id == _STORY_ID
    assert {ac.ac_id for ac in loaded.acs} == {_CONTROL_AC, _FLAKY_AC, "AC-3"}


def _history(log: FlakinessLog, ac_id: str) -> FlakinessAcHistory:
    return next(ac for ac in log.acs if ac.ac_id == ac_id)


def test_flaky_ac_crosses_default_threshold(
    reference_dir: pathlib.Path,
) -> None:
    """AC-7: the flaky AC's trailing transient-fail streak reaches the default
    threshold — the literal reproduction of the epic AC's 'flakiness threshold
    fires on a multi-run fixture'."""
    log = FlakinessLog.model_validate(
        _load_yaml(reference_dir / "qa-flakiness-log.yaml")
    )
    decision = evaluate_ac_flakiness(
        _history(log, _FLAKY_AC), FlakinessThresholdConfig()
    )

    assert decision.exceeded is True
    assert decision.consecutive_transient_fail_runs >= 3


def test_control_ac_does_not_cross_threshold(
    reference_dir: pathlib.Path,
) -> None:
    """AC-7: the clean control AC never crosses (no-marker-on-absence parity)."""
    log = FlakinessLog.model_validate(
        _load_yaml(reference_dir / "qa-flakiness-log.yaml")
    )
    decision = evaluate_ac_flakiness(
        _history(log, _CONTROL_AC), FlakinessThresholdConfig()
    )

    assert decision.exceeded is False
    assert decision.consecutive_transient_fail_runs == 0


def test_primary_envelope_emits_exactly_the_exceeded_acs(
    reference_dir: pathlib.Path,
) -> None:
    """AC-5/AC-7: the primary envelope's ``flakiness_emissions`` names exactly
    the AC(s) the substrate finds exceeded over the committed corpus — binding
    the witnessed emission to the replayed verdict."""
    log = FlakinessLog.model_validate(
        _load_yaml(reference_dir / "qa-flakiness-log.yaml")
    )
    exceeded = {
        ac.ac_id
        for ac in log.acs
        if evaluate_ac_flakiness(ac, FlakinessThresholdConfig()).exceeded
    }

    envelope = _load_yaml(reference_dir / "qa-envelope.yaml")
    emissions = envelope.get("flakiness_emissions") or []
    assert Counter(e["ac_id"] for e in emissions) == Counter(exceeded)
    assert all(
        e["marker_class"] == FLAKINESS_THRESHOLD_EXCEEDED_MARKER
        for e in emissions
    )


# --------------------------------------------------------------------------- #
# FR-P2-9 — the cross-check replays green + drift through the real substrate    #
# --------------------------------------------------------------------------- #


def test_green_pair_reproduces_primary_envelope_verdict(
    reference_dir: pathlib.Path, marker_registry: MarkerClassRegistry
) -> None:
    """AC-2/AC-7: an identical persisted/re-derived plan pair yields ``green`` —
    matching the primary envelope's ``plan_rederivation.cross_check_status``."""
    persisted = _plan(
        (_entry(_CONTROL_AC, heuristics=_CONTROL_AC_HEURISTICS), _entry(_FLAKY_AC))
    )
    rederived = _plan(
        (_entry(_CONTROL_AC, heuristics=_CONTROL_AC_HEURISTICS), _entry(_FLAKY_AC))
    )

    result = surface_plan_rederivation_cross_check(
        persisted, rederived, _STORY_ID, marker_registry
    )

    assert result.cross_check_status == "green"
    assert result.emission_record is None

    envelope = _load_yaml(reference_dir / "qa-envelope.yaml")
    assert envelope["plan_rederivation"]["cross_check_status"] == "green"


def test_drift_pair_reproduces_drift_envelope_verdict(
    reference_dir: pathlib.Path, marker_registry: MarkerClassRegistry
) -> None:
    """AC-3/AC-7: a plan pair differing only at AC-2's ``heuristic_applicability``
    (the mutated-qa-runbook scenario the drift envelope documents) yields
    ``drift-detected`` with ``drift_surfaces``/``drifted_ac_ids`` matching the
    witnessed drift envelope."""
    persisted = _plan(
        (_entry(_CONTROL_AC, heuristics=_CONTROL_AC_HEURISTICS), _entry(_FLAKY_AC))
    )
    rederived = _plan(
        (
            _entry(_CONTROL_AC, heuristics=_CONTROL_AC_HEURISTICS),
            _entry(_FLAKY_AC, heuristics=("rate-limit-boundary",)),
        )
    )

    result = surface_plan_rederivation_cross_check(
        persisted, rederived, _STORY_ID, marker_registry
    )

    assert result.cross_check_status == "drift-detected"
    assert result.emission_record is not None
    assert result.emission_record.marker_class == PLAN_REDERIVATION_DRIFT_DETECTED_MARKER
    context = result.emission_record.diagnostic_context
    assert context.drift_surfaces == ("heuristic_applicability",)
    assert context.drifted_ac_ids == (_FLAKY_AC,)

    envelope = _load_yaml(reference_dir / "qa-envelope-rederivation-drift.yaml")
    rederivation = envelope["plan_rederivation"]
    assert rederivation["cross_check_status"] == "drift-detected"
    assert rederivation["drift_surfaces"] == list(context.drift_surfaces)
    assert rederivation["drifted_ac_ids"] == list(context.drifted_ac_ids)
    assert rederivation["story_id"] == _STORY_ID
