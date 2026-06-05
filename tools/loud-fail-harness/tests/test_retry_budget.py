"""Tests for ``loud_fail_harness.retry_budget`` per Story 5.1.

AC mapping (verbatim from
``_bmad-output/implementation-artifacts/5-1-whole-story-retry-budget-configuration-enforcement.md``):

    * AC-1 — module + public-API surface (existence + import smoke
      test exercised via the imports at the top of this file plus
      :func:`test_module_exports_public_api`).
    * AC-2 — ``resolve_retry_budget`` 11-case branching matrix +
      ``default=`` keyword override + error-message format.
    * AC-3 — ``evaluate_retry_decision`` 8-case decision matrix +
      purity baseline + bucket-agnosticism baseline.
    * AC-4 — ``read_retry_budget_from_config_file`` 8-case file-system
      branching matrix using pytest's ``tmp_path`` fixture.
    * AC-5 — simulated-retry-round end-to-end (3 sequential
      :func:`evaluate_retry_decision` calls; Pydantic v2 frozen-model
      ``model_copy(update=...)`` discipline).
    * AC-6 — configurability override end-to-end (file-read → resolve
      → 5-round decision sequence with ``retry_budget: 5``).
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
import yaml

from loud_fail_harness.retry_budget import (
    DEFAULT_MAX_PARALLEL_STORIES,
    DEFAULT_PER_EPIC_RETRY_MULTIPLIER,
    DEFAULT_PER_SPRINT_RETRY_MULTIPLIER,
    DEFAULT_RETRY_BUDGET,
    DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD,
    RetryBudgetConfigError,
    RetryDecision,
    evaluate_retry_decision,
    read_max_parallel_stories_from_config_file,
    read_parallel_stories_from_config_file,
    read_per_epic_retry_budget_multiplier_from_config_file,
    read_per_sprint_retry_budget_from_config_file,
    read_retry_budget_from_config_file,
    read_sprint_escalation_rate_threshold_from_config_file,
    resolve_max_parallel_stories,
    resolve_parallel_stories,
    resolve_per_epic_retry_budget_multiplier,
    resolve_per_sprint_retry_budget_override,
    resolve_retry_budget,
    resolve_sprint_escalation_rate_threshold,
)
from loud_fail_harness.run_state import (
    CostToDateBySpecialist,
    RetryAttempt,
    RunState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run_state(
    *,
    retry_history_length: int = 0,
    last_envelope: dict[str, Any] | None = None,
    **overrides: Any,
) -> RunState:
    """Construct a minimal valid :class:`RunState` for budget-mechanics
    testing.

    Mirrors the ``_minimal_run_state`` helper in
    ``tests/test_run_state.py`` (per-file convention; helpers are not
    cross-imported across test modules in this harness). The
    ``retry_history`` tuple is built with N
    :class:`RetryAttempt` entries; ``last_envelope`` is parametrizable
    so the bucket-agnosticism test can vary it independently of all
    other fields.
    """
    history: tuple[RetryAttempt, ...] = tuple(
        RetryAttempt(retry_attempt=i + 1, retry_reason="test")
        for i in range(retry_history_length)
    )
    base: dict[str, Any] = {
        "schema_version": "1.1",
        "story_id": "5-1-test",
        "run_id": "run-5-1-0001",
        "current_state": "in-progress",
        "branch_name": "story/5-1-test",
        "dispatched_specialist": None,
        "last_envelope": last_envelope,
        "pending_qa_dispatch_payload": None,
        "retry_history": history,
        "active_markers": (),
        "cost_to_date_by_specialist": CostToDateBySpecialist(),
    }
    base.update(overrides)
    return RunState(**base)


# ---------------------------------------------------------------------------
# AC-1 — Module surface smoke
# ---------------------------------------------------------------------------


def test_module_exports_public_api() -> None:
    """The six public-API symbols are importable + the FR8 default is 2."""
    # Imports at the top of this file already prove the public surface
    # imports cleanly; this test additionally pins the default value.
    assert DEFAULT_RETRY_BUDGET == 2
    assert RetryDecision.DISPATCH_RETRY.value == "dispatch-retry"
    assert RetryDecision.HALT_BUDGET_EXHAUSTED.value == "halt-budget-exhausted"
    assert issubclass(RetryBudgetConfigError, ValueError)


# ---------------------------------------------------------------------------
# AC-2 — resolve_retry_budget — 11-case branching matrix
# ---------------------------------------------------------------------------


def test_resolve_retry_budget_returns_default_for_none_config() -> None:
    """Case 1: ``config is None`` → default (covers pre-Story-7.5 state)."""
    assert resolve_retry_budget(None) == 2


def test_resolve_retry_budget_returns_default_for_empty_dict_config() -> None:
    """Case 2: empty dict → default (config exists; field absent)."""
    assert resolve_retry_budget({}) == 2


def test_resolve_retry_budget_returns_zero_for_zero_value() -> None:
    """Case 3: explicit zero → zero (no retries; legitimate operator choice)."""
    assert resolve_retry_budget({"retry_budget": 0}) == 0


@pytest.mark.parametrize("value", [1, 2, 5, 10, 100])
def test_resolve_retry_budget_returns_resolved_value_for_int(value: int) -> None:
    """Cases 4-5 (+ extras): positive int → that int."""
    assert resolve_retry_budget({"retry_budget": value}) == value


def test_resolve_retry_budget_rejects_string_int() -> None:
    """Case 6: string-form int → raise (YAML int form required)."""
    with pytest.raises(RetryBudgetConfigError, match="YAML int"):
        resolve_retry_budget({"retry_budget": "2"})


def test_resolve_retry_budget_rejects_float_int() -> None:
    """Case 7: float-int → raise (YAML int form required)."""
    with pytest.raises(RetryBudgetConfigError, match="YAML int"):
        resolve_retry_budget({"retry_budget": 2.0})


def test_resolve_retry_budget_rejects_negative_int() -> None:
    """Case 8: negative → raise (non-negative integer invariant)."""
    with pytest.raises(RetryBudgetConfigError, match="non-negative integer"):
        resolve_retry_budget({"retry_budget": -1})


def test_resolve_retry_budget_rejects_bool_true() -> None:
    """Case 9: bool True → raise (Python ``bool ⊆ int`` ambiguity)."""
    with pytest.raises(RetryBudgetConfigError, match="non-negative integer"):
        resolve_retry_budget({"retry_budget": True})


def test_resolve_retry_budget_rejects_bool_false() -> None:
    """Case 10: bool False → raise (same ``bool ⊆ int`` rationale)."""
    with pytest.raises(RetryBudgetConfigError, match="non-negative integer"):
        resolve_retry_budget({"retry_budget": False})


def test_resolve_retry_budget_treats_none_value_as_field_absent() -> None:
    """Case 11: None-valued field → default (YAML ``retry_budget:`` empty)."""
    assert resolve_retry_budget({"retry_budget": None}) == 2


@pytest.mark.parametrize(
    "junk_value",
    [
        [1, 2],  # list
        {"nested": "mapping"},  # dict
        object(),  # arbitrary object
        complex(1, 2),  # complex number
    ],
)
def test_resolve_retry_budget_rejects_arbitrary_non_int(junk_value: Any) -> None:
    """Cases beyond the 11-case spec: arbitrary non-int → raise.

    The AC-1 contract is "non-int values raise". The spec enumerates
    the operator-likely inputs (string, float, bool, negative, None);
    this test guards against silent-coercion regressions for less-
    likely inputs.
    """
    with pytest.raises(RetryBudgetConfigError):
        resolve_retry_budget({"retry_budget": junk_value})


def test_resolve_retry_budget_honors_default_keyword_override() -> None:
    """``default=N`` keyword overrides the function's built-in default."""
    assert resolve_retry_budget(None, default=5) == 5
    assert resolve_retry_budget({}, default=5) == 5
    assert resolve_retry_budget({"retry_budget": None}, default=7) == 7


def test_resolve_retry_budget_error_message_contains_field_and_value() -> None:
    """Per AC-1's diagnostic-shape contract: the message includes the
    offending value, the field name ``retry_budget``, and a remediation
    hint."""
    with pytest.raises(RetryBudgetConfigError) as exc_info:
        resolve_retry_budget({"retry_budget": -3})
    msg = str(exc_info.value)
    assert "retry_budget" in msg
    assert "-3" in msg
    assert "non-negative" in msg.lower()

    with pytest.raises(RetryBudgetConfigError) as exc_info_str:
        resolve_retry_budget({"retry_budget": "abc"})
    msg_str = str(exc_info_str.value)
    assert "retry_budget" in msg_str
    assert "abc" in msg_str
    assert "yaml int" in msg_str.lower()


# ---------------------------------------------------------------------------
# AC-3 — evaluate_retry_decision — 8-case decision matrix + invariants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("history_len", "budget"),
    [
        (0, 1),
        (0, 2),
        (1, 2),
        (1, 5),
    ],
)
def test_evaluate_retry_decision_dispatches_when_under_budget(
    history_len: int, budget: int
) -> None:
    """Cases 2, 3, 4, 7: ``len(history) < budget`` → DISPATCH_RETRY."""
    rs = _make_run_state(retry_history_length=history_len)
    assert evaluate_retry_decision(rs, budget) == RetryDecision.DISPATCH_RETRY


@pytest.mark.parametrize(
    ("history_len", "budget"),
    [
        (2, 2),
        (5, 5),
    ],
)
def test_evaluate_retry_decision_halts_when_at_budget(
    history_len: int, budget: int
) -> None:
    """Cases 5, 8: ``len(history) == budget`` → HALT_BUDGET_EXHAUSTED."""
    rs = _make_run_state(retry_history_length=history_len)
    assert evaluate_retry_decision(rs, budget) == RetryDecision.HALT_BUDGET_EXHAUSTED


def test_evaluate_retry_decision_halts_when_over_budget_defensive() -> None:
    """Case 6: ``len(history) > budget`` → HALT (defensive idempotence)."""
    rs = _make_run_state(retry_history_length=3)
    assert evaluate_retry_decision(rs, 2) == RetryDecision.HALT_BUDGET_EXHAUSTED


def test_evaluate_retry_decision_halts_immediately_for_zero_budget() -> None:
    """Case 1: zero budget halts on first retry-eligible return."""
    rs = _make_run_state(retry_history_length=0)
    assert evaluate_retry_decision(rs, 0) == RetryDecision.HALT_BUDGET_EXHAUSTED


def test_evaluate_retry_decision_is_pure() -> None:
    """Purity baseline: same input → same output; no mutation of RunState.

    Pydantic v2 frozen-models structurally enforce no-mutation; this
    test is a regression baseline against a future accidental
    introduction of side effects (e.g., a logging hook that mutates
    RunState through a private attribute).
    """
    rs = _make_run_state(retry_history_length=1)
    rs_dump_before = rs.model_dump_json()
    decision_a = evaluate_retry_decision(rs, 2)
    decision_b = evaluate_retry_decision(rs, 2)
    rs_dump_after = rs.model_dump_json()
    assert decision_a == decision_b
    assert rs_dump_before == rs_dump_after


def test_evaluate_retry_decision_is_bucket_agnostic() -> None:
    """``last_envelope`` shape MUST NOT influence the decision.

    Story 5.2 owns bucket filtering; this module is bucket-agnostic by
    contract. Build two RunState instances differing ONLY in
    ``last_envelope`` and assert identical decisions.
    """
    rs_no_envelope = _make_run_state(
        retry_history_length=1,
        last_envelope=None,
    )
    rs_patch_bucket = _make_run_state(
        retry_history_length=1,
        last_envelope={
            "envelope_class": "dev",
            "findings": [{"bucket": "patch", "id": "f-001"}],
        },
    )
    rs_passthrough_bucket = _make_run_state(
        retry_history_length=1,
        last_envelope={
            "envelope_class": "review-bmad",
            "findings": [{"bucket": "passthrough", "id": "f-002"}],
        },
    )
    decision_none = evaluate_retry_decision(rs_no_envelope, 2)
    decision_patch = evaluate_retry_decision(rs_patch_bucket, 2)
    decision_through = evaluate_retry_decision(rs_passthrough_bucket, 2)
    assert decision_none == RetryDecision.DISPATCH_RETRY
    assert decision_none == decision_patch == decision_through


def test_evaluate_retry_decision_raises_for_negative_budget() -> None:
    """Negative resolved_budget must raise ValueError (Pattern 5 loud-fail).

    The guard protects Story 5.2 callers that construct resolved_budget
    via any path other than resolve_retry_budget().
    """
    rs = _make_run_state()
    with pytest.raises(ValueError, match="non-negative"):
        evaluate_retry_decision(rs, -1)
    with pytest.raises(ValueError, match="non-negative"):
        evaluate_retry_decision(rs, -100)


# ---------------------------------------------------------------------------
# AC-4 — read_retry_budget_from_config_file — 8-case file-system matrix
# ---------------------------------------------------------------------------


def test_read_retry_budget_from_config_file_returns_default_for_missing_file(
    tmp_path: pathlib.Path,
) -> None:
    """Case 1: file does not exist → default (do NOT raise)."""
    config_path = tmp_path / "config.yaml"
    assert not config_path.exists()
    assert read_retry_budget_from_config_file(config_path) == 2


def test_read_retry_budget_from_config_file_returns_default_for_empty_file(
    tmp_path: pathlib.Path,
) -> None:
    """Case 2: empty file → default."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("", encoding="utf-8")
    assert read_retry_budget_from_config_file(config_path) == 2


def test_read_retry_budget_from_config_file_returns_default_for_whitespace_only(
    tmp_path: pathlib.Path,
) -> None:
    """Case 2 variant: comment-only / whitespace-only file → default.

    YAML parses comment-only files to ``None`` (not an empty mapping);
    the helper must still return the default rather than raising.
    """
    config_path = tmp_path / "config.yaml"
    config_path.write_text("# top-level comment only\n", encoding="utf-8")
    assert read_retry_budget_from_config_file(config_path) == 2


def test_read_retry_budget_from_config_file_reads_resolved_value(
    tmp_path: pathlib.Path,
) -> None:
    """Case 3: parses to ``{retry_budget: 3}`` → 3."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("retry_budget: 3\n", encoding="utf-8")
    assert read_retry_budget_from_config_file(config_path) == 3


def test_read_retry_budget_from_config_file_returns_default_for_field_absent(
    tmp_path: pathlib.Path,
) -> None:
    """Case 4: parses to a mapping without the field → default."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("some_other_field: value\n", encoding="utf-8")
    assert read_retry_budget_from_config_file(config_path) == 2


def test_read_retry_budget_from_config_file_raises_for_malformed_yaml(
    tmp_path: pathlib.Path,
) -> None:
    """Case 5: malformed YAML → raise; message includes parser context."""
    config_path = tmp_path / "config.yaml"
    # Unclosed flow-mapping bracket — guaranteed YAMLError from PyYAML.
    config_path.write_text("retry_budget: {unclosed\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="not valid YAML"):
        read_retry_budget_from_config_file(config_path)


def test_read_retry_budget_from_config_file_chains_yaml_error_cause(
    tmp_path: pathlib.Path,
) -> None:
    """Case 5 detail: ``__cause__`` is set to the underlying YAMLError."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("retry_budget: {unclosed\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError) as exc_info:
        read_retry_budget_from_config_file(config_path)
    assert isinstance(exc_info.value.__cause__, yaml.YAMLError)


def test_read_retry_budget_from_config_file_raises_for_top_level_list(
    tmp_path: pathlib.Path,
) -> None:
    """Case 6: parses to a list → raise."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML mapping"):
        read_retry_budget_from_config_file(config_path)


def test_read_retry_budget_from_config_file_raises_for_top_level_scalar(
    tmp_path: pathlib.Path,
) -> None:
    """Case 7: parses to a bare scalar → raise."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("hello\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML mapping"):
        read_retry_budget_from_config_file(config_path)


def test_read_retry_budget_from_config_file_propagates_resolver_error(
    tmp_path: pathlib.Path,
) -> None:
    """Case 8: parses to a mapping with bad value → resolver error propagates."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text('retry_budget: "not-an-int"\n', encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="YAML int"):
        read_retry_budget_from_config_file(config_path)


def test_read_retry_budget_from_config_file_honors_default_keyword(
    tmp_path: pathlib.Path,
) -> None:
    """``default=`` keyword propagates to the resolver path."""
    missing_path = tmp_path / "missing.yaml"
    assert read_retry_budget_from_config_file(missing_path, default=7) == 7
    empty_path = tmp_path / "empty.yaml"
    empty_path.write_text("", encoding="utf-8")
    assert read_retry_budget_from_config_file(empty_path, default=7) == 7


def test_read_retry_budget_from_config_file_raises_for_non_utf8_file(
    tmp_path: pathlib.Path,
) -> None:
    """Non-UTF-8 file content must be wrapped as RetryBudgetConfigError.

    UnicodeDecodeError is not an OSError subclass; without explicit
    handling it would escape the function's contract boundary.
    """
    config_path = tmp_path / "config.yaml"
    config_path.write_bytes(b"retry_budget: \xff\xfe")  # invalid UTF-8 bytes
    with pytest.raises(RetryBudgetConfigError, match="failed to read"):
        read_retry_budget_from_config_file(config_path)


# ---------------------------------------------------------------------------
# AC-5 — Simulated retry round end-to-end
# ---------------------------------------------------------------------------


def test_simulated_retry_round_three_call_sequence() -> None:
    """3 sequential decisions across a 2-budget loop:

    1. Pre-first-retry (history empty)         → DISPATCH_RETRY
    2. After first retry round (history len 1) → DISPATCH_RETRY
    3. After second retry round (history len 2)→ HALT_BUDGET_EXHAUSTED

    Pydantic v2 frozen-model invariant: each post-round state is built
    via ``model_copy(update={"retry_history": (...,)})``; the three
    bindings are distinct objects.
    """
    budget = 2
    rs_round_0 = _make_run_state(retry_history_length=0)
    decision_0 = evaluate_retry_decision(rs_round_0, budget)
    assert decision_0 == RetryDecision.DISPATCH_RETRY

    rs_round_1 = rs_round_0.model_copy(
        update={
            "retry_history": (
                RetryAttempt(retry_attempt=1, retry_reason="patch-bucket-finding"),
            ),
        }
    )
    decision_1 = evaluate_retry_decision(rs_round_1, budget)
    assert decision_1 == RetryDecision.DISPATCH_RETRY

    rs_round_2 = rs_round_1.model_copy(
        update={
            "retry_history": (
                RetryAttempt(retry_attempt=1, retry_reason="patch-bucket-finding"),
                RetryAttempt(retry_attempt=2, retry_reason="patch-bucket-finding-2"),
            ),
        }
    )
    decision_2 = evaluate_retry_decision(rs_round_2, budget)
    assert decision_2 == RetryDecision.HALT_BUDGET_EXHAUSTED

    # Three distinct objects per the frozen-model invariant.
    assert rs_round_0 is not rs_round_1
    assert rs_round_1 is not rs_round_2
    assert rs_round_0 is not rs_round_2


# ---------------------------------------------------------------------------
# AC-6 — Configurability override end-to-end
# ---------------------------------------------------------------------------


def test_configurability_override_via_config_file(
    tmp_path: pathlib.Path,
) -> None:
    """End-to-end: write ``retry_budget: 5`` → file-read returns 5;
    decision sequence dispatches through 4 rounds and halts on the
    fifth, demonstrating operator-controlled budget vs. the FR8
    default of 2.
    """
    config_dir = tmp_path / "_bmad" / "automation"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text("retry_budget: 5\n", encoding="utf-8")

    resolved = read_retry_budget_from_config_file(config_path)
    assert resolved == 5

    # Pre-fifth-retry state (4 retries done; 1 round still permitted).
    rs_pre_fifth = _make_run_state(retry_history_length=4)
    assert (
        evaluate_retry_decision(rs_pre_fifth, resolved)
        == RetryDecision.DISPATCH_RETRY
    )

    # Post-fifth-retry state (budget reached).
    rs_post_fifth = rs_pre_fifth.model_copy(
        update={
            "retry_history": tuple(
                RetryAttempt(retry_attempt=i + 1, retry_reason="op-override-loop")
                for i in range(5)
            ),
        }
    )
    assert (
        evaluate_retry_decision(rs_post_fifth, resolved)
        == RetryDecision.HALT_BUDGET_EXHAUSTED
    )


def test_configurability_override_default_vs_override_diverges(
    tmp_path: pathlib.Path,
) -> None:
    """Cross-check: same RunState, different budgets → different decisions.

    With ``retry_history`` length 3, default budget 2 says HALT;
    operator-overridden budget 5 says DISPATCH. This pins the
    operator-control contract end-to-end.
    """
    rs = _make_run_state(retry_history_length=3)

    # Default-budget path (config absent / pre-Story-7.5 state).
    missing_path = tmp_path / "config.yaml"
    default_budget = read_retry_budget_from_config_file(missing_path)
    assert default_budget == 2
    assert (
        evaluate_retry_decision(rs, default_budget)
        == RetryDecision.HALT_BUDGET_EXHAUSTED
    )

    # Operator-override path.
    config_path = tmp_path / "override.yaml"
    config_path.write_text("retry_budget: 5\n", encoding="utf-8")
    override_budget = read_retry_budget_from_config_file(config_path)
    assert override_budget == 5
    assert (
        evaluate_retry_decision(rs, override_budget)
        == RetryDecision.DISPATCH_RETRY
    )


# --------------------------------------------------------------------------- #
# Story 15.2 — per-epic retry-budget multiplier resolver (AC-1)               #
#   Mirrors the resolve_retry_budget / read_..._from_config_file contract     #
#   verbatim; the ONLY semantic differences are the field name and the floor  #
#   of 1 (reject < 1) rather than 0.                                          #
# --------------------------------------------------------------------------- #


def test_default_per_epic_retry_multiplier_is_two() -> None:
    assert DEFAULT_PER_EPIC_RETRY_MULTIPLIER == 2


def test_resolve_per_epic_returns_default_for_none_config() -> None:
    assert resolve_per_epic_retry_budget_multiplier(None) == 2


def test_resolve_per_epic_returns_default_for_empty_dict_config() -> None:
    assert resolve_per_epic_retry_budget_multiplier({}) == 2


def test_resolve_per_epic_returns_default_for_field_absent() -> None:
    assert resolve_per_epic_retry_budget_multiplier({"retry_budget": 9}) == 2


@pytest.mark.parametrize("value", [1, 2, 3, 10])
def test_resolve_per_epic_returns_resolved_value_for_int(value: int) -> None:
    assert (
        resolve_per_epic_retry_budget_multiplier(
            {"per_epic_retry_budget_multiplier": value}
        )
        == value
    )


def test_resolve_per_epic_treats_none_value_as_field_absent() -> None:
    assert (
        resolve_per_epic_retry_budget_multiplier(
            {"per_epic_retry_budget_multiplier": None}
        )
        == 2
    )


def test_resolve_per_epic_rejects_zero() -> None:
    # Floor is 1 (NOT 0) — this is the only semantic difference from the
    # per-story resolver.
    with pytest.raises(RetryBudgetConfigError, match=">= 1"):
        resolve_per_epic_retry_budget_multiplier(
            {"per_epic_retry_budget_multiplier": 0}
        )


def test_resolve_per_epic_rejects_negative_int() -> None:
    with pytest.raises(RetryBudgetConfigError, match=">= 1"):
        resolve_per_epic_retry_budget_multiplier(
            {"per_epic_retry_budget_multiplier": -1}
        )


def test_resolve_per_epic_rejects_string_int() -> None:
    with pytest.raises(RetryBudgetConfigError, match="YAML int"):
        resolve_per_epic_retry_budget_multiplier(
            {"per_epic_retry_budget_multiplier": "2"}
        )


def test_resolve_per_epic_rejects_float() -> None:
    with pytest.raises(RetryBudgetConfigError, match="YAML int"):
        resolve_per_epic_retry_budget_multiplier(
            {"per_epic_retry_budget_multiplier": 2.0}
        )


@pytest.mark.parametrize("value", [True, False])
def test_resolve_per_epic_rejects_bool(value: bool) -> None:
    with pytest.raises(RetryBudgetConfigError, match="booleans are rejected"):
        resolve_per_epic_retry_budget_multiplier(
            {"per_epic_retry_budget_multiplier": value}
        )


def test_resolve_per_epic_honors_default_keyword_override() -> None:
    assert resolve_per_epic_retry_budget_multiplier(None, default=4) == 4


def test_resolve_per_epic_error_message_contains_field_and_value() -> None:
    with pytest.raises(RetryBudgetConfigError) as excinfo:
        resolve_per_epic_retry_budget_multiplier(
            {"per_epic_retry_budget_multiplier": 0}
        )
    message = str(excinfo.value)
    assert "per_epic_retry_budget_multiplier" in message
    assert "0" in message


def test_read_per_epic_returns_default_for_missing_file(
    tmp_path: pathlib.Path,
) -> None:
    assert (
        read_per_epic_retry_budget_multiplier_from_config_file(
            tmp_path / "absent.yaml"
        )
        == 2
    )


def test_read_per_epic_returns_default_for_empty_file(
    tmp_path: pathlib.Path,
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")
    assert read_per_epic_retry_budget_multiplier_from_config_file(config) == 2


def test_read_per_epic_reads_resolved_value(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "per_epic_retry_budget_multiplier: 3\n", encoding="utf-8"
    )
    assert read_per_epic_retry_budget_multiplier_from_config_file(config) == 3


def test_read_per_epic_raises_for_malformed_yaml(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("per_epic_retry_budget_multiplier: [\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="not valid YAML"):
        read_per_epic_retry_budget_multiplier_from_config_file(config)


def test_read_per_epic_raises_for_non_mapping(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML mapping"):
        read_per_epic_retry_budget_multiplier_from_config_file(config)


def test_read_per_epic_propagates_resolver_error(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "per_epic_retry_budget_multiplier: 0\n", encoding="utf-8"
    )
    with pytest.raises(RetryBudgetConfigError, match=">= 1"):
        read_per_epic_retry_budget_multiplier_from_config_file(config)


def test_read_per_epic_returns_default_for_whitespace_only(
    tmp_path: pathlib.Path,
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("   \n\t\n", encoding="utf-8")
    assert read_per_epic_retry_budget_multiplier_from_config_file(config) == 2


def test_read_per_epic_raises_for_non_utf8_file(
    tmp_path: pathlib.Path,
) -> None:
    config = tmp_path / "config.yaml"
    config.write_bytes(b"\xff\xfe")  # invalid UTF-8
    with pytest.raises(RetryBudgetConfigError, match="failed to read"):
        read_per_epic_retry_budget_multiplier_from_config_file(config)


# ===========================================================================
# Story 16.2 — per-sprint retry-budget override resolver
# ===========================================================================


def test_resolve_per_sprint_override_none_config_returns_none() -> None:
    assert resolve_per_sprint_retry_budget_override(None) is None


def test_resolve_per_sprint_override_field_absent_returns_none() -> None:
    assert resolve_per_sprint_retry_budget_override({}) is None


def test_resolve_per_sprint_override_value_none_returns_none() -> None:
    assert resolve_per_sprint_retry_budget_override(
        {"per_sprint_retry_budget": None}
    ) is None


def test_resolve_per_sprint_override_valid_int() -> None:
    assert (
        resolve_per_sprint_retry_budget_override({"per_sprint_retry_budget": 12})
        == 12
    )


def test_resolve_per_sprint_override_explicit_zero_distinct_from_absent() -> None:
    # 0 is a meaningful override (no per-sprint retries), distinct from absent.
    assert (
        resolve_per_sprint_retry_budget_override({"per_sprint_retry_budget": 0})
        == 0
    )


def test_resolve_per_sprint_override_rejects_bool() -> None:
    with pytest.raises(RetryBudgetConfigError, match="booleans are rejected"):
        resolve_per_sprint_retry_budget_override({"per_sprint_retry_budget": True})


def test_resolve_per_sprint_override_rejects_string_int() -> None:
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML int"):
        resolve_per_sprint_retry_budget_override({"per_sprint_retry_budget": "12"})


def test_resolve_per_sprint_override_rejects_float() -> None:
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML int"):
        resolve_per_sprint_retry_budget_override({"per_sprint_retry_budget": 12.0})


def test_resolve_per_sprint_override_rejects_negative() -> None:
    with pytest.raises(RetryBudgetConfigError, match="non-negative integer"):
        resolve_per_sprint_retry_budget_override({"per_sprint_retry_budget": -1})


def test_read_per_sprint_missing_file_returns_none(tmp_path: pathlib.Path) -> None:
    assert (
        read_per_sprint_retry_budget_from_config_file(tmp_path / "absent.yaml")
        is None
    )


def test_read_per_sprint_empty_file_returns_none(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")
    assert read_per_sprint_retry_budget_from_config_file(config) is None


def test_read_per_sprint_comment_only_returns_none(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("# only a comment\n", encoding="utf-8")
    assert read_per_sprint_retry_budget_from_config_file(config) is None


def test_read_per_sprint_valid(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("per_sprint_retry_budget: 9\n", encoding="utf-8")
    assert read_per_sprint_retry_budget_from_config_file(config) == 9


def test_read_per_sprint_malformed_yaml_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("per_sprint_retry_budget: [\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="not valid YAML"):
        read_per_sprint_retry_budget_from_config_file(config)


def test_read_per_sprint_non_mapping_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML mapping"):
        read_per_sprint_retry_budget_from_config_file(config)


def test_read_per_sprint_non_utf8_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_bytes(b"\xff\xfe")
    with pytest.raises(RetryBudgetConfigError, match="failed to read"):
        read_per_sprint_retry_budget_from_config_file(config)


# ===========================================================================
# Story 16.2 — sprint escalation-rate threshold resolver
# ===========================================================================


def test_resolve_threshold_none_config_returns_default() -> None:
    assert (
        resolve_sprint_escalation_rate_threshold(None)
        == DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD
    )


def test_resolve_threshold_field_absent_returns_default() -> None:
    assert (
        resolve_sprint_escalation_rate_threshold({})
        == DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD
    )


def test_resolve_threshold_value_none_returns_default() -> None:
    assert (
        resolve_sprint_escalation_rate_threshold(
            {"sprint_escalation_rate_threshold": None}
        )
        == DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD
    )


def test_resolve_threshold_valid_float() -> None:
    assert (
        resolve_sprint_escalation_rate_threshold(
            {"sprint_escalation_rate_threshold": 0.4}
        )
        == 0.4
    )


def test_resolve_threshold_int_coerced_to_float() -> None:
    result = resolve_sprint_escalation_rate_threshold(
        {"sprint_escalation_rate_threshold": 1}
    )
    assert result == 1.0
    assert isinstance(result, float)


def test_resolve_threshold_upper_bound_one_accepted() -> None:
    assert (
        resolve_sprint_escalation_rate_threshold(
            {"sprint_escalation_rate_threshold": 1.0}
        )
        == 1.0
    )


def test_resolve_threshold_rejects_bool() -> None:
    with pytest.raises(RetryBudgetConfigError, match="booleans are rejected"):
        resolve_sprint_escalation_rate_threshold(
            {"sprint_escalation_rate_threshold": True}
        )


def test_resolve_threshold_rejects_string() -> None:
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML number"):
        resolve_sprint_escalation_rate_threshold(
            {"sprint_escalation_rate_threshold": "0.25"}
        )


def test_resolve_threshold_rejects_zero() -> None:
    with pytest.raises(RetryBudgetConfigError, match="range"):
        resolve_sprint_escalation_rate_threshold(
            {"sprint_escalation_rate_threshold": 0.0}
        )


def test_resolve_threshold_rejects_above_one() -> None:
    with pytest.raises(RetryBudgetConfigError, match="range"):
        resolve_sprint_escalation_rate_threshold(
            {"sprint_escalation_rate_threshold": 1.5}
        )


def test_resolve_threshold_rejects_negative() -> None:
    with pytest.raises(RetryBudgetConfigError, match="range"):
        resolve_sprint_escalation_rate_threshold(
            {"sprint_escalation_rate_threshold": -0.1}
        )


def test_read_threshold_missing_file_returns_default(
    tmp_path: pathlib.Path,
) -> None:
    assert (
        read_sprint_escalation_rate_threshold_from_config_file(
            tmp_path / "absent.yaml"
        )
        == DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD
    )


def test_read_threshold_empty_file_returns_default(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")
    assert (
        read_sprint_escalation_rate_threshold_from_config_file(config)
        == DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD
    )


def test_read_threshold_valid(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("sprint_escalation_rate_threshold: 0.5\n", encoding="utf-8")
    assert read_sprint_escalation_rate_threshold_from_config_file(config) == 0.5


def test_read_threshold_malformed_yaml_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("sprint_escalation_rate_threshold: [\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="not valid YAML"):
        read_sprint_escalation_rate_threshold_from_config_file(config)


def test_read_threshold_non_mapping_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML mapping"):
        read_sprint_escalation_rate_threshold_from_config_file(config)


def test_read_threshold_non_utf8_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_bytes(b"\xff\xfe")
    with pytest.raises(RetryBudgetConfigError, match="failed to read"):
        read_sprint_escalation_rate_threshold_from_config_file(config)


def test_default_per_sprint_multiplier_is_two() -> None:
    assert DEFAULT_PER_SPRINT_RETRY_MULTIPLIER == 2


def test_read_per_sprint_resolver_error_propagates(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("per_sprint_retry_budget: true\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="booleans are rejected"):
        read_per_sprint_retry_budget_from_config_file(config)


def test_read_threshold_resolver_error_propagates(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("sprint_escalation_rate_threshold: true\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="booleans are rejected"):
        read_sprint_escalation_rate_threshold_from_config_file(config)


# ---------------------------------------------------------------------------
# Story 18.1 AC-1 — resolve_parallel_stories (bool resolver; INVERSE of the int
# resolvers — accept type(value) is bool, reject everything else)
# ---------------------------------------------------------------------------


def test_resolve_parallel_stories_none_config_returns_default() -> None:
    assert resolve_parallel_stories(None) is False


def test_resolve_parallel_stories_field_absent_returns_default() -> None:
    assert resolve_parallel_stories({"retry_budget": 2}) is False


def test_resolve_parallel_stories_value_none_returns_default() -> None:
    assert resolve_parallel_stories({"parallel_stories": None}) is False


@pytest.mark.parametrize("value", [True, False])
def test_resolve_parallel_stories_accepts_bool(value: bool) -> None:
    assert resolve_parallel_stories({"parallel_stories": value}) is value


def test_resolve_parallel_stories_honors_default_keyword() -> None:
    assert resolve_parallel_stories(None, default=True) is True


@pytest.mark.parametrize("value", [0, 1, 2])
def test_resolve_parallel_stories_rejects_int(value: int) -> None:
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML boolean"):
        resolve_parallel_stories({"parallel_stories": value})


@pytest.mark.parametrize("value", ["true", "false", "yes", ""])
def test_resolve_parallel_stories_rejects_string(value: str) -> None:
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML boolean"):
        resolve_parallel_stories({"parallel_stories": value})


def test_resolve_parallel_stories_rejects_float() -> None:
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML boolean"):
        resolve_parallel_stories({"parallel_stories": 1.0})


@pytest.mark.parametrize("value", [[], {}, [True]])
def test_resolve_parallel_stories_rejects_container(value: object) -> None:
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML boolean"):
        resolve_parallel_stories({"parallel_stories": value})


def test_resolve_parallel_stories_error_names_field() -> None:
    with pytest.raises(RetryBudgetConfigError) as exc_info:
        resolve_parallel_stories({"parallel_stories": 1})
    assert "parallel_stories" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Story 18.1 AC-1 — read_parallel_stories_from_config_file (file contract)
# ---------------------------------------------------------------------------


def test_read_parallel_stories_missing_file_returns_default(
    tmp_path: pathlib.Path,
) -> None:
    assert read_parallel_stories_from_config_file(tmp_path / "nope.yaml") is False


def test_read_parallel_stories_empty_file_returns_default(
    tmp_path: pathlib.Path,
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")
    assert read_parallel_stories_from_config_file(config) is False


def test_read_parallel_stories_reads_value(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("parallel_stories: true\n", encoding="utf-8")
    assert read_parallel_stories_from_config_file(config) is True


def test_read_parallel_stories_malformed_yaml_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("parallel_stories: [\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="not valid YAML"):
        read_parallel_stories_from_config_file(config)


def test_read_parallel_stories_non_mapping_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML mapping"):
        read_parallel_stories_from_config_file(config)


def test_read_parallel_stories_propagates_resolver_error(
    tmp_path: pathlib.Path,
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("parallel_stories: 1\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML boolean"):
        read_parallel_stories_from_config_file(config)


# ---------------------------------------------------------------------------
# Story 18.1 AC-1 — resolve_max_parallel_stories (int resolver, floor 1, dflt 2)
# ---------------------------------------------------------------------------


def test_default_max_parallel_stories_is_two() -> None:
    assert DEFAULT_MAX_PARALLEL_STORIES == 2


def test_resolve_max_parallel_none_config_returns_default() -> None:
    assert resolve_max_parallel_stories(None) == 2


def test_resolve_max_parallel_field_absent_returns_default() -> None:
    assert resolve_max_parallel_stories({"parallel_stories": True}) == 2


def test_resolve_max_parallel_value_none_returns_default() -> None:
    assert resolve_max_parallel_stories({"max_parallel_stories": None}) == 2


@pytest.mark.parametrize("value", [1, 2, 8])
def test_resolve_max_parallel_accepts_int_at_or_above_floor(value: int) -> None:
    assert resolve_max_parallel_stories({"max_parallel_stories": value}) == value


def test_resolve_max_parallel_honors_default_keyword() -> None:
    assert resolve_max_parallel_stories(None, default=4) == 4


def test_resolve_max_parallel_rejects_zero() -> None:
    with pytest.raises(RetryBudgetConfigError, match="must be an integer >= 1"):
        resolve_max_parallel_stories({"max_parallel_stories": 0})


def test_resolve_max_parallel_rejects_negative() -> None:
    with pytest.raises(RetryBudgetConfigError, match="must be an integer >= 1"):
        resolve_max_parallel_stories({"max_parallel_stories": -1})


@pytest.mark.parametrize("value", [True, False])
def test_resolve_max_parallel_rejects_bool(value: bool) -> None:
    with pytest.raises(RetryBudgetConfigError, match="booleans are rejected"):
        resolve_max_parallel_stories({"max_parallel_stories": value})


def test_resolve_max_parallel_rejects_string_int() -> None:
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML int"):
        resolve_max_parallel_stories({"max_parallel_stories": "2"})


def test_resolve_max_parallel_rejects_float() -> None:
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML int"):
        resolve_max_parallel_stories({"max_parallel_stories": 2.0})


def test_resolve_max_parallel_error_names_field() -> None:
    with pytest.raises(RetryBudgetConfigError) as exc_info:
        resolve_max_parallel_stories({"max_parallel_stories": 0})
    assert "max_parallel_stories" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Story 18.1 AC-1 — read_max_parallel_stories_from_config_file (file contract)
# ---------------------------------------------------------------------------


def test_read_max_parallel_missing_file_returns_default(
    tmp_path: pathlib.Path,
) -> None:
    assert read_max_parallel_stories_from_config_file(tmp_path / "nope.yaml") == 2


def test_read_max_parallel_empty_file_returns_default(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("", encoding="utf-8")
    assert read_max_parallel_stories_from_config_file(config) == 2


def test_read_max_parallel_reads_value(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("max_parallel_stories: 3\n", encoding="utf-8")
    assert read_max_parallel_stories_from_config_file(config) == 3


def test_read_max_parallel_malformed_yaml_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("max_parallel_stories: [\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="not valid YAML"):
        read_max_parallel_stories_from_config_file(config)


def test_read_max_parallel_non_mapping_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("42\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="must be a YAML mapping"):
        read_max_parallel_stories_from_config_file(config)


def test_read_max_parallel_propagates_resolver_error(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("max_parallel_stories: 0\n", encoding="utf-8")
    with pytest.raises(RetryBudgetConfigError, match="must be an integer >= 1"):
        read_max_parallel_stories_from_config_file(config)


def test_read_max_parallel_non_utf8_raises(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_bytes(b"\xff\xfe max_parallel_stories: 2")
    with pytest.raises(RetryBudgetConfigError, match="failed to read"):
        read_max_parallel_stories_from_config_file(config)
