"""Unit tests for the shared input-hardening helpers — Story 24.2 AC-1.

Two layers: (1) the direct accept/reject matrix for each primitive
(whitespace-only, leading/trailing/embedded newline, null byte, path
separators, ``..``, duplicate list); and (2) the registry-derived, non-vacuous
per-model behavioral corpus (AC-5) that constructs every EXTERNALLY_CONSTRUCTED
model with each hostile input per registered field and asserts a
``ValidationError``.
"""

from __future__ import annotations

import datetime
import os
import pathlib
from collections.abc import Callable

import pytest
from pydantic import BaseModel, ValidationError

from loud_fail_harness.epic_run_state import (
    EpicRunState,
    PerEpicCostPartition,
    PerEpicRetryBudget,
    PerSprintRetryBudget,
    SprintRunState,
)
from loud_fail_harness.input_hardening import (
    harden_identifier,
    harden_path_segment,
    reject_duplicate_identifiers,
)
from loud_fail_harness.input_hardening_gate import load_registry
from loud_fail_harness.parallel_pollution import StoryClaim
from loud_fail_harness.qa_ac_iteration import (
    FlowBranchSkippedDiagnosticContext,
    SmokeFirstAbortDiagnosticContext,
)
from loud_fail_harness.qa_behavioral_plan import FlowBranch
from loud_fail_harness.qa_a11y_audit import (
    A11yAcScopedDiagnosticContext,
    A11yRunScopedDiagnosticContext,
    AxeViolationKey,
)
from loud_fail_harness.qa_evidence_persistence import EvidenceTruncatedDiagnosticContext
from loud_fail_harness.qa_evidence_tier import Tier3NotConfiguredDiagnosticContext
from loud_fail_harness.qa_exploratory_heuristics import HeuristicSkippedDiagnosticContext
from loud_fail_harness.qa_plan_drift import PlanDriftDiagnosticContext
from loud_fail_harness.qa_runbook_heuristics_validator import HeuristicOptOutEntry
from loud_fail_harness.run_state import CostToDateBySpecialist, RunState
from loud_fail_harness.story_file_lock import LockRecord


# --------------------------------------------------------------------------- #
# harden_identifier                                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("value", ["epic-15", "15-1-foo", "a", "run-2026-06-10"])
def test_harden_identifier_accepts_clean_kebab(value: str) -> None:
    assert harden_identifier(value, "L") == value


@pytest.mark.parametrize("value", ["", "   ", "\t", "\n", " \t "])
def test_harden_identifier_rejects_whitespace_only(value: str) -> None:
    with pytest.raises(ValueError, match="whitespace-only"):
        harden_identifier(value, "L")


@pytest.mark.parametrize("value", ["epic-15\n", "\nepic-15", "a\nb", "a\rb", "a\r\nb"])
def test_harden_identifier_rejects_embedded_newline(value: str) -> None:
    with pytest.raises(ValueError, match="embedded newlines"):
        harden_identifier(value, "L")


@pytest.mark.parametrize("value", ["a\x00b", "\x00", "epic-15\x00"])
def test_harden_identifier_rejects_null_byte(value: str) -> None:
    with pytest.raises(ValueError, match="null byte"):
        harden_identifier(value, "L")


def test_harden_identifier_label_appears_in_message() -> None:
    with pytest.raises(ValueError, match="MyField"):
        harden_identifier("   ", "MyField")


# --------------------------------------------------------------------------- #
# harden_path_segment                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("value", ["14-4-foo", "epic-16", "story-id"])
def test_harden_path_segment_accepts_clean_segment(value: str) -> None:
    assert harden_path_segment(value, "L") == value


def test_harden_path_segment_inherits_identifier_rejections() -> None:
    with pytest.raises(ValueError, match="whitespace-only"):
        harden_path_segment("   ", "L")
    with pytest.raises(ValueError, match="embedded newlines"):
        harden_path_segment("a\nb", "L")
    with pytest.raises(ValueError, match="null byte"):
        harden_path_segment("a\x00b", "L")


@pytest.mark.parametrize("value", ["a/b", "a\\b", "/etc", "nested/path"])
def test_harden_path_segment_rejects_path_separator(value: str) -> None:
    with pytest.raises(ValueError, match="path separator"):
        harden_path_segment(value, "L")


@pytest.mark.parametrize("value", ["..", "a..b", "..etc"])
def test_harden_path_segment_rejects_traversal(value: str) -> None:
    with pytest.raises(ValueError, match="traversal"):
        harden_path_segment(value, "L")


def test_harden_path_segment_separator_checked_before_traversal() -> None:
    # "../etc" contains both "/" and ".."; the separator check fires first
    # (matches the migrated epic_run_state_path_for ordering contract).
    with pytest.raises(ValueError, match="path separator"):
        harden_path_segment("../etc", "L")


# --------------------------------------------------------------------------- #
# reject_duplicate_identifiers                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "values",
    [(), ("a",), ("a", "b", "c"), ["15-1", "15-2", "15-3"]],
)
def test_reject_duplicate_identifiers_accepts_unique(values: object) -> None:
    assert reject_duplicate_identifiers(values, "L") is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "values",
    [("a", "a"), ("a", "b", "a"), ["15-1", "15-2", "15-1"]],
)
def test_reject_duplicate_identifiers_rejects_dupes(values: object) -> None:
    with pytest.raises(ValueError, match="duplicate identifiers"):
        reject_duplicate_identifiers(values, "L")  # type: ignore[arg-type]


def test_reject_duplicate_identifiers_reports_repeated_value() -> None:
    with pytest.raises(ValueError, match="15-1"):
        reject_duplicate_identifiers(("15-1", "15-1"), "L")


# --------------------------------------------------------------------------- #
# Registry-derived non-vacuous behavioral corpus (AC-5)                       #
# --------------------------------------------------------------------------- #
#
# For each EXTERNALLY_CONSTRUCTED model × each registered field, construct the
# model with each applicable hostile input and assert a ValidationError. The
# corpus is DERIVED from the registry (see _corpus_params), so adding an
# externally_constructed entry automatically extends coverage — and forces a
# baseline here (test_every_external_model_has_corpus_baseline). Non-vacuity:
# every identifier field is probed with a null byte (and every path/min_length-
# only field with whitespace-only), inputs that ONLY the model_validator
# hardening rejects — so a present-but-inert validator fails this corpus even
# though the AST Rule B passed.


def _epic_kwargs() -> dict[str, object]:
    return dict(
        schema_version="1.0",
        epic_id="epic-15",
        run_id="run-epic-15-001",
        current_state="epic-in-progress",
        story_ids=("15-1-foo",),
        per_story_status={"15-1-foo": "ready-for-dev"},
        per_epic_retry_budget=PerEpicRetryBudget(
            multiplier=2, story_count=1, effective_budget=2, consumed=0
        ),
        per_epic_cost_partition=PerEpicCostPartition(
            per_story_cost={"15-1-foo": 0.0}, epic_cost_total=0.0
        ),
        active_markers=(),
    )


def _sprint_kwargs() -> dict[str, object]:
    return dict(
        schema_version="1.0",
        sprint_id="sprint-phase-2",
        run_id="run-sprint-phase-2-001",
        current_state="sprint-in-progress",
        epic_ids=("epic-15", "epic-16"),
        per_epic_status={"epic-15": "epic-in-progress", "epic-16": "epic-complete"},
        unassigned_story_ids=("14-6-ref",),
        per_sprint_retry_budget=PerSprintRetryBudget(
            multiplier=2, epic_count=2, effective_budget=4, consumed=0
        ),
        active_markers=(),
    )


def _run_state_kwargs() -> dict[str, object]:
    return dict(
        schema_version="1.2",
        story_id="2-2-test",
        run_id="run-001",
        current_state="ready-for-dev",
        branch_name="feature/2-2",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )


def _flow_branch_kwargs() -> dict[str, object]:
    return dict(branch_id="happy-path", description="the main flow")


def _plan_drift_kwargs() -> dict[str, object]:
    return dict(
        story_id="4-2-test",
        prior_plan_status="generated",
        prior_ac_hash="0" * 64,
        current_ac_hash="1" * 64,
    )


def _lock_record_kwargs() -> dict[str, object]:
    return dict(
        schema_version="1.0",
        story_id="14-3",
        pid=os.getpid(),
        started_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        worktree_path=pathlib.Path("/tmp/wt"),
        hostname="testhost",
    )


def _story_claim_kwargs() -> dict[str, object]:
    return dict(
        story_id="a-story", allocated_port=4317, aggregate_claim_story_id="a-story"
    )


def _smoke_abort_kwargs() -> dict[str, object]:
    return dict(
        story_id="4-6-test",
        failed_ac_id="AC-1",
        failed_assertions=("status 200",),
        failed_evidence_refs=("evidence.txt",),
    )


def _flow_skipped_kwargs() -> dict[str, object]:
    return dict(
        story_id="4-6-test",
        ac_id="AC-1",
        branch_id="branch-1",
        branch_description="the branch",
        skip_rationale="not reachable",
    )


def _evidence_truncated_kwargs() -> dict[str, object]:
    return dict(
        story_id="4-12-test",
        run_id="run-001",
        how_to_enable_pointer="see docs/qa-runbook.md",
    )


def _tier3_kwargs() -> dict[str, object]:
    return dict(
        story_id="4-8-test",
        ac_id="AC-1",
        how_to_enable_pointer="see docs/qa-runbook.md",
    )


def _heuristic_skipped_kwargs() -> dict[str, object]:
    return dict(story_id="auto-001", heuristic_kind="empty-state")


def _axe_violation_key_kwargs() -> dict[str, object]:
    return dict(rule_id="color-contrast", target_selector="#nav button")


def _a11y_ac_scoped_kwargs() -> dict[str, object]:
    return dict(story_id="19-4", ac_id="AC-1")


def _a11y_run_scoped_kwargs() -> dict[str, object]:
    return dict(story_id="19-4")


def _opt_out_entry_kwargs() -> dict[str, object]:
    return dict(story_id="auto-019-001", ac_key="ac_1")


#: qualname -> (model class, valid-baseline-kwargs factory).
_BASELINES: dict[str, tuple[type[BaseModel], Callable[[], dict[str, object]]]] = {
    "epic_run_state.EpicRunState": (EpicRunState, _epic_kwargs),
    "epic_run_state.SprintRunState": (SprintRunState, _sprint_kwargs),
    "run_state.RunState": (RunState, _run_state_kwargs),
    "qa_behavioral_plan.FlowBranch": (FlowBranch, _flow_branch_kwargs),
    "qa_plan_drift.PlanDriftDiagnosticContext": (
        PlanDriftDiagnosticContext,
        _plan_drift_kwargs,
    ),
    "story_file_lock.LockRecord": (LockRecord, _lock_record_kwargs),
    "parallel_pollution.StoryClaim": (StoryClaim, _story_claim_kwargs),
    "qa_ac_iteration.SmokeFirstAbortDiagnosticContext": (
        SmokeFirstAbortDiagnosticContext,
        _smoke_abort_kwargs,
    ),
    "qa_ac_iteration.FlowBranchSkippedDiagnosticContext": (
        FlowBranchSkippedDiagnosticContext,
        _flow_skipped_kwargs,
    ),
    "qa_evidence_persistence.EvidenceTruncatedDiagnosticContext": (
        EvidenceTruncatedDiagnosticContext,
        _evidence_truncated_kwargs,
    ),
    "qa_evidence_tier.Tier3NotConfiguredDiagnosticContext": (
        Tier3NotConfiguredDiagnosticContext,
        _tier3_kwargs,
    ),
    "qa_exploratory_heuristics.HeuristicSkippedDiagnosticContext": (
        HeuristicSkippedDiagnosticContext,
        _heuristic_skipped_kwargs,
    ),
    "qa_a11y_audit.AxeViolationKey": (AxeViolationKey, _axe_violation_key_kwargs),
    "qa_a11y_audit.A11yAcScopedDiagnosticContext": (
        A11yAcScopedDiagnosticContext,
        _a11y_ac_scoped_kwargs,
    ),
    "qa_a11y_audit.A11yRunScopedDiagnosticContext": (
        A11yRunScopedDiagnosticContext,
        _a11y_run_scoped_kwargs,
    ),
    "qa_runbook_heuristics_validator.HeuristicOptOutEntry": (
        HeuristicOptOutEntry,
        _opt_out_entry_kwargs,
    ),
}


_IDENTIFIER_HOSTILE = {"whitespace": "   ", "newline": "x\ny", "null": "x\x00y"}
_PATH_EXTRA_HOSTILE = {"separator": "a/b", "traversal": ".."}


def _corpus_params() -> list[tuple[str, str, str, str]]:
    """Derive (qualname, field, bucket, hostile-label) cases from the registry."""
    registry = load_registry()
    params: list[tuple[str, str, str, str]] = []
    for qualname, buckets in registry.externally_constructed.items():
        for field in buckets.identifier_fields:
            for label in _IDENTIFIER_HOSTILE:
                params.append((qualname, field, "identifier", label))
        for field in buckets.path_fields:
            for label in {**_IDENTIFIER_HOSTILE, **_PATH_EXTRA_HOSTILE}:
                params.append((qualname, field, "path", label))
        for field in buckets.dup_key_fields:
            params.append((qualname, field, "dup", "duplicate"))
    return params


def test_every_external_model_has_corpus_baseline() -> None:
    registry = load_registry()
    missing = set(registry.externally_constructed) - set(_BASELINES)
    assert not missing, f"externally_constructed models without a corpus baseline: {missing}"


@pytest.mark.parametrize("qualname", sorted(_BASELINES))
def test_corpus_baseline_is_valid(qualname: str) -> None:
    model, factory = _BASELINES[qualname]
    model(**factory())  # must not raise


@pytest.mark.parametrize(
    "qualname,field,bucket,label",
    _corpus_params(),
    ids=lambda v: v if isinstance(v, str) else repr(v),
)
def test_external_model_rejects_hostile_input(
    qualname: str, field: str, bucket: str, label: str
) -> None:
    model, factory = _BASELINES[qualname]
    kwargs = factory()
    if bucket == "dup":
        kwargs[field] = ("dup-x", "dup-x")
    else:
        hostile = {**_IDENTIFIER_HOSTILE, **_PATH_EXTRA_HOSTILE}[label]
        current = kwargs[field]
        kwargs[field] = (hostile,) if isinstance(current, tuple) else hostile
    with pytest.raises(ValidationError):
        model(**kwargs)
