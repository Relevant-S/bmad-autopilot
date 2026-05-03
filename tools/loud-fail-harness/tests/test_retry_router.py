"""Tests for ``loud_fail_harness.retry_router`` per Story 5.2.

AC mapping (verbatim from
``_bmad-output/implementation-artifacts/5-2-bucket-driven-action-item-derivation-retry-routing.md``):

    * AC-1 — module + public-API surface (existence + import smoke
      test exercised via the imports at the top of this file plus
      :func:`test_module_exports_public_api`).
    * AC-2 — ``route_envelope`` four-bucket → four-outcome routing rule
      with explicit precedence ordering + error-path tests + purity
      baseline + RoutingError-message-format test.
    * AC-3 — ``derive_action_items`` derivation rule + field mapping +
      patch-severity inclusion/exclusion + ordering + empty-input.
    * AC-4 — ``derive_deferred_findings`` derivation rule (severity-
      agnostic) + non-defer exclusion + ``source_story_id`` propagation
      + empty-input.
    * AC-5 — prose-not-included negative-path test (the FR9
      context-firewall regression baseline).
    * AC-6 — ``record_defer_findings`` file-creation + append + bullet
      format + clock injection + no-op-for-empty + return-count.
    * AC-7 — ``route_envelope`` + ``derive_action_items`` end-to-end
      composition test.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from loud_fail_harness.retry_router import (
    ActionItem,
    DeferredFinding,
    RoutingError,
    RoutingOutcome,
    Severity,
    _VALID_SEVERITIES,
    derive_action_items,
    derive_deferred_findings,
    record_defer_findings,
    route_envelope,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    *,
    id: str = "F-1",
    source: str = "blind",
    title: str = "title",
    detail: str = "detail",
    location: str = "src/x.py:1",
    bucket: str = "patch",
    severity: str = "HIGH",
    **overrides: Any,
) -> dict[str, Any]:
    """Construct a minimal valid finding dict matching ``$defs/finding``."""
    finding: dict[str, Any] = {
        "id": id,
        "source": source,
        "title": title,
        "detail": detail,
        "location": location,
        "bucket": bucket,
        "severity": severity,
    }
    finding.update(overrides)
    return finding


def _make_envelope(
    *,
    status: str = "fail",
    findings: tuple[dict[str, Any], ...] = (),
    rationale: str = "rationale text",
    artifacts: tuple[dict[str, Any], ...] = (),
    **overrides: Any,
) -> dict[str, Any]:
    """Construct a minimal valid envelope dict matching the schema's
    required fields ``[status, artifacts, findings, rationale]``."""
    envelope: dict[str, Any] = {
        "status": status,
        "artifacts": list(artifacts),
        "findings": list(findings),
        "rationale": rationale,
    }
    envelope.update(overrides)
    return envelope


def _fixed_clock() -> datetime:
    return datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# AC-1 — module exports
# ---------------------------------------------------------------------------


def test_module_exports_public_api() -> None:
    """The module exposes the nine documented public symbols."""
    from loud_fail_harness import retry_router

    expected = {
        "ActionItem",
        "DeferredFinding",
        "RoutingError",
        "RoutingOutcome",
        "Severity",
        "derive_action_items",
        "derive_deferred_findings",
        "record_defer_findings",
        "route_envelope",
    }
    assert set(retry_router.__all__) == expected
    for name in expected:
        assert hasattr(retry_router, name)


def test_routing_outcome_member_values_are_kebab_case() -> None:
    assert RoutingOutcome.RETRY_DEV.value == "retry-dev"
    assert RoutingOutcome.ESCALATE.value == "escalate"
    assert RoutingOutcome.DEFER_AND_ADVANCE.value == "defer-and-advance"
    assert RoutingOutcome.DISMISS_AND_ADVANCE.value == "dismiss-and-advance"


def test_severity_member_values_match_envelope_schema() -> None:
    assert Severity.HIGH.value == "HIGH"
    assert Severity.MED.value == "MED"
    assert Severity.LOW.value == "LOW"
    # Cross-check: enum members and the internal filter set must stay in sync.
    assert {m.value for m in Severity} == _VALID_SEVERITIES


def test_route_envelope_accepts_severity_enum_members() -> None:
    """Severity enum member as finding severity does not raise RoutingError."""
    from loud_fail_harness.retry_router import _normalize_severity

    assert _normalize_severity(Severity.HIGH) == "HIGH"
    assert _normalize_severity(Severity.MED) == "MED"
    assert _normalize_severity(Severity.LOW) == "LOW"
    assert _normalize_severity("HIGH") == "HIGH"

    # A finding dict using Severity.HIGH must route correctly.
    env = _make_envelope(
        findings=[_make_finding(bucket="patch", severity=Severity.HIGH)]  # type: ignore[arg-type]
    )
    assert route_envelope(env) == RoutingOutcome.RETRY_DEV


def test_action_item_is_frozen_and_hashable() -> None:
    item = ActionItem(
        finding_id="F-1",
        location="src/x.py:1",
        required_change="do thing",
        severity="HIGH",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.severity = "LOW"  # type: ignore[misc]
    # Hashable — round-trip through a set.
    assert {item} == {item}


def test_deferred_finding_is_frozen_and_hashable() -> None:
    item = DeferredFinding(
        finding_id="F-1",
        location="src/x.py:1",
        description="defer reason",
        source_story_id="5-2-test",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.description = "other"  # type: ignore[misc]
    assert {item} == {item}


# ---------------------------------------------------------------------------
# AC-2 — route_envelope routing rule + precedence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("severity", ["HIGH", "MED", "LOW"])
def test_route_envelope_returns_escalate_for_decision_needed_finding(
    severity: str,
) -> None:
    env = _make_envelope(
        findings=(_make_finding(bucket="decision_needed", severity=severity),),
    )
    assert route_envelope(env) is RoutingOutcome.ESCALATE


@pytest.mark.parametrize("severity", ["HIGH", "MED"])
def test_route_envelope_returns_retry_dev_for_patch_high_or_med(
    severity: str,
) -> None:
    env = _make_envelope(
        findings=(_make_finding(bucket="patch", severity=severity),),
    )
    assert route_envelope(env) is RoutingOutcome.RETRY_DEV


@pytest.mark.parametrize("severity", ["HIGH", "MED", "LOW"])
def test_route_envelope_returns_defer_and_advance_for_defer_only(
    severity: str,
) -> None:
    env = _make_envelope(
        findings=(_make_finding(bucket="defer", severity=severity),),
    )
    assert route_envelope(env) is RoutingOutcome.DEFER_AND_ADVANCE


@pytest.mark.parametrize("severity", ["HIGH", "MED", "LOW"])
def test_route_envelope_returns_dismiss_and_advance_for_dismiss_only(
    severity: str,
) -> None:
    env = _make_envelope(
        findings=(_make_finding(bucket="dismiss", severity=severity),),
    )
    assert route_envelope(env) is RoutingOutcome.DISMISS_AND_ADVANCE


def test_route_envelope_returns_dismiss_and_advance_for_patch_low_only() -> None:
    """Rule 5 carve-out: ``patch[LOW]``-only → DISMISS_AND_ADVANCE."""
    env = _make_envelope(
        findings=(_make_finding(bucket="patch", severity="LOW"),),
    )
    assert route_envelope(env) is RoutingOutcome.DISMISS_AND_ADVANCE


def test_route_envelope_decision_needed_preempts_patch() -> None:
    """Precedence rule 1: decision_needed PREEMPTS patch[HIGH]."""
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="decision_needed", severity="HIGH"),
            _make_finding(id="F-2", bucket="patch", severity="HIGH"),
        ),
    )
    assert route_envelope(env) is RoutingOutcome.ESCALATE


def test_route_envelope_decision_needed_preempts_defer_and_dismiss() -> None:
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="defer", severity="MED"),
            _make_finding(id="F-2", bucket="decision_needed", severity="LOW"),
            _make_finding(id="F-3", bucket="dismiss", severity="LOW"),
        ),
    )
    assert route_envelope(env) is RoutingOutcome.ESCALATE


def test_route_envelope_patch_high_preempts_defer_and_dismiss() -> None:
    """Precedence rule 2: patch[HIGH|MED] preempts defer/dismiss."""
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="patch", severity="HIGH"),
            _make_finding(id="F-2", bucket="defer", severity="MED"),
            _make_finding(id="F-3", bucket="dismiss", severity="LOW"),
        ),
    )
    assert route_envelope(env) is RoutingOutcome.RETRY_DEV


def test_route_envelope_defer_preempts_dismiss() -> None:
    """Precedence rule 3: defer (any severity) preempts dismiss-only."""
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="defer", severity="LOW"),
            _make_finding(id="F-2", bucket="dismiss", severity="HIGH"),
        ),
    )
    assert route_envelope(env) is RoutingOutcome.DEFER_AND_ADVANCE


def test_route_envelope_patch_low_with_dismiss_returns_dismiss() -> None:
    """Mixed patch[LOW] + dismiss → DISMISS_AND_ADVANCE (rule 4 + 5)."""
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="patch", severity="LOW"),
            _make_finding(id="F-2", bucket="dismiss", severity="MED"),
        ),
    )
    assert route_envelope(env) is RoutingOutcome.DISMISS_AND_ADVANCE


def test_route_envelope_patch_low_with_defer_returns_defer() -> None:
    """Mixed patch[LOW] + defer → DEFER_AND_ADVANCE (defer preempts)."""
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="patch", severity="LOW"),
            _make_finding(id="F-2", bucket="defer", severity="HIGH"),
        ),
    )
    assert route_envelope(env) is RoutingOutcome.DEFER_AND_ADVANCE


def test_route_envelope_raises_for_pass_status() -> None:
    env = _make_envelope(status="pass", findings=())
    with pytest.raises(RoutingError, match="route_envelope is only called"):
        route_envelope(env)


def test_route_envelope_raises_for_none_envelope() -> None:
    with pytest.raises(
        RoutingError, match="validate_return_envelope before route_envelope"
    ):
        route_envelope(None)


def test_route_envelope_raises_for_non_mapping_envelope() -> None:
    with pytest.raises(RoutingError, match="must be a Mapping"):
        route_envelope(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_route_envelope_raises_for_empty_findings() -> None:
    env = _make_envelope(status="fail", findings=())
    with pytest.raises(RoutingError, match="must be non-empty"):
        route_envelope(env)


def test_route_envelope_raises_for_missing_findings_key() -> None:
    env = _make_envelope(status="fail", findings=())
    del env["findings"]
    with pytest.raises(RoutingError, match="must have a 'findings' array"):
        route_envelope(env)


def test_route_envelope_raises_for_non_sequence_findings() -> None:
    env = _make_envelope(status="fail")
    env["findings"] = "not-a-sequence"
    with pytest.raises(RoutingError, match="must be a sequence"):
        route_envelope(env)


def test_route_envelope_raises_for_unknown_bucket() -> None:
    env = _make_envelope(
        findings=(_make_finding(bucket="unknown-bucket", severity="HIGH"),),
    )
    with pytest.raises(RoutingError, match="unknown bucket value"):
        route_envelope(env)


def test_route_envelope_raises_for_unknown_severity() -> None:
    env = _make_envelope(
        findings=(_make_finding(bucket="patch", severity="CRITICAL"),),
    )
    with pytest.raises(RoutingError, match="unknown severity value"):
        route_envelope(env)


def test_route_envelope_raises_for_finding_missing_keys() -> None:
    env = _make_envelope(findings=())
    env["findings"] = [{"id": "F-1"}]  # missing detail/location/bucket/severity
    with pytest.raises(RoutingError, match="missing required keys"):
        route_envelope(env)


def test_route_envelope_raises_for_non_mapping_finding() -> None:
    env = _make_envelope(findings=())
    env["findings"] = ["not-a-mapping"]
    with pytest.raises(RoutingError, match="must be a Mapping"):
        route_envelope(env)


def test_route_envelope_is_pure_no_mutation() -> None:
    """Purity baseline: same input → same output; no mutation."""
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="patch", severity="HIGH"),
            _make_finding(id="F-2", bucket="defer", severity="MED"),
        ),
    )
    snapshot = {
        "status": env["status"],
        "rationale": env["rationale"],
        "findings_len": len(env["findings"]),
        "first_id": env["findings"][0]["id"],
    }

    out_a = route_envelope(env)
    out_b = route_envelope(env)
    assert out_a is out_b is RoutingOutcome.RETRY_DEV
    assert snapshot["status"] == env["status"]
    assert snapshot["rationale"] == env["rationale"]
    assert snapshot["findings_len"] == len(env["findings"])
    assert snapshot["first_id"] == env["findings"][0]["id"]


@pytest.mark.parametrize(
    "envelope_factory, match_substring",
    [
        (lambda: None, "validate_return_envelope before route_envelope"),
        (
            lambda: _make_envelope(status="pass", findings=()),
            "route_envelope is only called",
        ),
        (
            lambda: _make_envelope(findings=()),
            "must be non-empty",
        ),
        (
            lambda: _make_envelope(
                findings=(_make_finding(bucket="garbage", severity="HIGH"),)
            ),
            "unknown bucket value",
        ),
        (
            lambda: _make_envelope(
                findings=(_make_finding(severity="WAT"),)
            ),
            "unknown severity value",
        ),
    ],
)
def test_routing_error_message_contains_remediation_hint(
    envelope_factory: Any, match_substring: str
) -> None:
    """Each error path's message contains an actionable remediation hint."""
    with pytest.raises(RoutingError, match=match_substring):
        route_envelope(envelope_factory())


# ---------------------------------------------------------------------------
# AC-3 — derive_action_items
# ---------------------------------------------------------------------------


def test_derive_action_items_includes_patch_high_only() -> None:
    env = _make_envelope(
        findings=(_make_finding(bucket="patch", severity="HIGH"),)
    )
    items = derive_action_items(env)
    assert len(items) == 1
    assert items[0].severity == "HIGH"


def test_derive_action_items_includes_patch_med_only() -> None:
    env = _make_envelope(
        findings=(_make_finding(bucket="patch", severity="MED"),)
    )
    items = derive_action_items(env)
    assert len(items) == 1
    assert items[0].severity == "MED"


def test_derive_action_items_excludes_patch_low() -> None:
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="patch", severity="HIGH"),
            _make_finding(id="F-2", bucket="patch", severity="LOW"),
        )
    )
    items = derive_action_items(env)
    assert len(items) == 1
    assert items[0].finding_id == "F-1"


@pytest.mark.parametrize(
    "bucket", ["decision_needed", "defer", "dismiss"]
)
def test_derive_action_items_excludes_non_patch_buckets(bucket: str) -> None:
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="patch", severity="HIGH"),
            _make_finding(id="F-2", bucket=bucket, severity="HIGH"),
        )
    )
    items = derive_action_items(env)
    assert len(items) == 1
    assert items[0].finding_id == "F-1"


def test_derive_action_items_preserves_order() -> None:
    env = _make_envelope(
        findings=(
            _make_finding(id="F-3", bucket="patch", severity="HIGH"),
            _make_finding(id="F-1", bucket="patch", severity="MED"),
            _make_finding(id="F-2", bucket="patch", severity="HIGH"),
        )
    )
    items = derive_action_items(env)
    assert [i.finding_id for i in items] == ["F-3", "F-1", "F-2"]


def test_derive_action_items_empty_for_no_eligible_findings() -> None:
    env = _make_envelope(
        findings=(_make_finding(bucket="dismiss", severity="LOW"),)
    )
    assert derive_action_items(env) == ()


def test_derive_action_items_returns_tuple_not_list() -> None:
    env = _make_envelope(
        findings=(_make_finding(bucket="patch", severity="HIGH"),)
    )
    items = derive_action_items(env)
    assert isinstance(items, tuple)


def test_derive_action_items_field_mapping() -> None:
    env = _make_envelope(
        findings=(
            _make_finding(
                id="FID-42",
                bucket="patch",
                severity="MED",
                detail="patch detail content",
                location="src/foo.py:10",
            ),
        )
    )
    item = derive_action_items(env)[0]
    assert item.finding_id == "FID-42"
    assert item.location == "src/foo.py:10"
    assert item.required_change == "patch detail content"
    assert item.severity == "MED"


def test_derive_action_items_raises_for_invalid_envelope() -> None:
    with pytest.raises(RoutingError):
        derive_action_items(None)


def test_derive_action_items_mixed_buckets_and_severities() -> None:
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="patch", severity="HIGH"),
            _make_finding(id="F-2", bucket="patch", severity="MED"),
            _make_finding(id="F-3", bucket="defer", severity="HIGH"),
            _make_finding(id="F-4", bucket="dismiss", severity="MED"),
            _make_finding(id="F-5", bucket="patch", severity="LOW"),
        )
    )
    items = derive_action_items(env)
    assert [i.finding_id for i in items] == ["F-1", "F-2"]


# ---------------------------------------------------------------------------
# AC-5 — prose-not-included regression baseline (FR9 context-firewall)
# ---------------------------------------------------------------------------


def test_derive_action_items_does_not_include_review_prose_or_non_patch_details() -> None:
    """The FR9 context-firewall regression baseline test."""
    env = _make_envelope(
        status="fail",
        rationale=(
            "DISTINCTIVE_PROSE_MARKER_RATIONALE — this prose must NEVER "
            "appear in any ActionItem"
        ),
        findings=(
            _make_finding(
                id="F-1",
                source="blind",
                title="t",
                detail="patch detail content",
                location="src/foo.py:10",
                bucket="patch",
                severity="HIGH",
            ),
            _make_finding(
                id="F-2",
                source="edge",
                title="t",
                detail="DISTINCTIVE_PROSE_MARKER_DEFER_DETAIL",
                location="src/bar.py:20",
                bucket="defer",
                severity="MED",
            ),
        ),
    )

    action_items = derive_action_items(env)

    corpus = "".join(
        str(value)
        for item in action_items
        for value in dataclasses.asdict(item).values()
    )

    assert "DISTINCTIVE_PROSE_MARKER_RATIONALE" not in corpus
    assert "DISTINCTIVE_PROSE_MARKER_DEFER_DETAIL" not in corpus
    assert len(action_items) == 1
    assert action_items[0].required_change == "patch detail content"


# ---------------------------------------------------------------------------
# AC-4 — derive_deferred_findings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("severity", ["HIGH", "MED", "LOW"])
def test_derive_deferred_findings_includes_all_severities(severity: str) -> None:
    env = _make_envelope(
        findings=(_make_finding(bucket="defer", severity=severity),)
    )
    items = derive_deferred_findings(env, source_story_id="5-2-test")
    assert len(items) == 1
    assert items[0].source_story_id == "5-2-test"


@pytest.mark.parametrize(
    "bucket", ["decision_needed", "patch", "dismiss"]
)
def test_derive_deferred_findings_excludes_non_defer_buckets(bucket: str) -> None:
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="defer", severity="HIGH"),
            _make_finding(id="F-2", bucket=bucket, severity="HIGH"),
        )
    )
    items = derive_deferred_findings(env, source_story_id="5-2-test")
    assert len(items) == 1
    assert items[0].finding_id == "F-1"


def test_derive_deferred_findings_propagates_source_story_id() -> None:
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="defer", severity="HIGH"),
            _make_finding(id="F-2", bucket="defer", severity="LOW"),
        )
    )
    items = derive_deferred_findings(env, source_story_id="some-other-story")
    assert all(i.source_story_id == "some-other-story" for i in items)


def test_derive_deferred_findings_empty_for_no_defer_findings() -> None:
    env = _make_envelope(
        findings=(_make_finding(bucket="patch", severity="HIGH"),)
    )
    assert derive_deferred_findings(env, source_story_id="5-2-test") == ()


def test_derive_deferred_findings_field_mapping() -> None:
    env = _make_envelope(
        findings=(
            _make_finding(
                id="DEF-7",
                bucket="defer",
                severity="LOW",
                detail="defer description",
                location="src/x.py:99",
            ),
        )
    )
    item = derive_deferred_findings(env, source_story_id="5-2-test")[0]
    assert item.finding_id == "DEF-7"
    assert item.location == "src/x.py:99"
    assert item.description == "defer description"
    assert item.source_story_id == "5-2-test"


def test_derive_deferred_findings_preserves_order() -> None:
    env = _make_envelope(
        findings=(
            _make_finding(id="F-3", bucket="defer", severity="HIGH"),
            _make_finding(id="F-1", bucket="patch", severity="HIGH"),
            _make_finding(id="F-2", bucket="defer", severity="LOW"),
        )
    )
    items = derive_deferred_findings(env, source_story_id="5-2-test")
    assert [i.finding_id for i in items] == ["F-3", "F-2"]


def test_derive_deferred_findings_raises_for_empty_source_story_id() -> None:
    env = _make_envelope(
        findings=(_make_finding(bucket="defer", severity="HIGH"),)
    )
    with pytest.raises(RoutingError, match="source_story_id"):
        derive_deferred_findings(env, source_story_id="")


# ---------------------------------------------------------------------------
# AC-6 — record_defer_findings
# ---------------------------------------------------------------------------


def test_record_defer_findings_creates_file_when_missing(tmp_path: Path) -> None:
    target = tmp_path / "deferred-work.md"
    deferred = (
        DeferredFinding(
            finding_id="F-1",
            location="src/x.py:1",
            description="first reason",
            source_story_id="5-2-test",
        ),
    )
    count = record_defer_findings(
        deferred, target, story_id="5-2-test", clock=_fixed_clock
    )
    assert count == 1
    text = target.read_text(encoding="utf-8")
    assert text.startswith("# Deferred Work\n\n")
    assert (
        "## Deferred from: code review of 5-2-test (2026-05-04)" in text
    )
    assert "- **F-1** [`src/x.py:1`] — first reason" in text


def test_record_defer_findings_appends_to_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "deferred-work.md"
    target.write_text(
        "# Deferred Work\n\n"
        "## Deferred from: code review of older-story (2026-04-01)\n\n"
        "- **OLD-1** [`src/o.py:1`] — older reason\n\n",
        encoding="utf-8",
    )
    deferred = (
        DeferredFinding(
            finding_id="F-1",
            location="src/x.py:1",
            description="new reason",
            source_story_id="5-2-test",
        ),
    )
    record_defer_findings(
        deferred, target, story_id="5-2-test", clock=_fixed_clock
    )
    text = target.read_text(encoding="utf-8")
    assert "older-story" in text
    assert "OLD-1" in text
    assert "## Deferred from: code review of 5-2-test (2026-05-04)" in text
    older_idx = text.index("older-story")
    newer_idx = text.index("5-2-test (2026-05-04)")
    assert older_idx < newer_idx


def test_record_defer_findings_renders_correct_bullet_format(
    tmp_path: Path,
) -> None:
    target = tmp_path / "deferred-work.md"
    deferred = (
        DeferredFinding(
            finding_id="`some.symbol_with_backticks`",
            location="tools/loud-fail-harness/tests/test_x.py:84",
            description="reason with — em dash and other content",
            source_story_id="5-2-test",
        ),
    )
    record_defer_findings(
        deferred, target, story_id="5-2-test", clock=_fixed_clock
    )
    text = target.read_text(encoding="utf-8")
    assert (
        "- **`some.symbol_with_backticks`** "
        "[`tools/loud-fail-harness/tests/test_x.py:84`] — "
        "reason with — em dash and other content"
    ) in text


def test_record_defer_findings_uses_clock_for_date_stamp(tmp_path: Path) -> None:
    target = tmp_path / "deferred-work.md"
    deferred = (
        DeferredFinding(
            finding_id="F-1",
            location="src/x.py:1",
            description="reason",
            source_story_id="5-2-test",
        ),
    )

    def custom_clock() -> datetime:
        return datetime(2030, 1, 15, tzinfo=timezone.utc)

    record_defer_findings(
        deferred, target, story_id="5-2-test", clock=custom_clock
    )
    text = target.read_text(encoding="utf-8")
    assert "(2030-01-15)" in text


def test_record_defer_findings_no_op_for_empty_sequence(tmp_path: Path) -> None:
    target = tmp_path / "deferred-work.md"
    count = record_defer_findings(
        (), target, story_id="5-2-test", clock=_fixed_clock
    )
    assert count == 0
    # File created with header only; no section appended.
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert text == "# Deferred Work\n\n"
    assert "## Deferred from" not in text


def test_record_defer_findings_no_op_preserves_existing_content(
    tmp_path: Path,
) -> None:
    target = tmp_path / "deferred-work.md"
    target.write_text(
        "# Deferred Work\n\n"
        "## Deferred from: code review of older-story (2026-04-01)\n\n"
        "- **OLD-1** [`src/o.py:1`] — older reason\n\n",
        encoding="utf-8",
    )
    before = target.read_text(encoding="utf-8")
    count = record_defer_findings(
        (), target, story_id="5-2-test", clock=_fixed_clock
    )
    assert count == 0
    assert target.read_text(encoding="utf-8") == before


def test_record_defer_findings_returns_count(tmp_path: Path) -> None:
    target = tmp_path / "deferred-work.md"
    deferred = tuple(
        DeferredFinding(
            finding_id=f"F-{i}",
            location=f"src/x.py:{i}",
            description=f"reason {i}",
            source_story_id="5-2-test",
        )
        for i in range(3)
    )
    count = record_defer_findings(
        deferred, target, story_id="5-2-test", clock=_fixed_clock
    )
    assert count == 3
    text = target.read_text(encoding="utf-8")
    for i in range(3):
        assert f"- **F-{i}** [`src/x.py:{i}`] — reason {i}" in text


def test_record_defer_findings_empty_existing_file(tmp_path: Path) -> None:
    """Existing-but-empty file is treated as missing."""
    target = tmp_path / "deferred-work.md"
    target.write_text("", encoding="utf-8")
    deferred = (
        DeferredFinding(
            finding_id="F-1",
            location="src/x.py:1",
            description="reason",
            source_story_id="5-2-test",
        ),
    )
    record_defer_findings(
        deferred, target, story_id="5-2-test", clock=_fixed_clock
    )
    text = target.read_text(encoding="utf-8")
    assert text.startswith("# Deferred Work\n\n")
    assert "## Deferred from: code review of 5-2-test" in text


def test_record_defer_findings_raises_for_empty_story_id(tmp_path: Path) -> None:
    target = tmp_path / "deferred-work.md"
    deferred = (
        DeferredFinding(
            finding_id="F-1",
            location="src/x.py:1",
            description="reason",
            source_story_id="5-2-test",
        ),
    )
    with pytest.raises(RoutingError, match="story_id"):
        record_defer_findings(deferred, target, story_id="")


def test_record_defer_findings_double_append_section_boundary(
    tmp_path: Path,
) -> None:
    """Two sequential calls produce both sections with correct boundary."""
    target = tmp_path / "deferred-work.md"
    d1 = DeferredFinding(
        finding_id="F-1", location="src/a.py:1", description="first", source_story_id="5-2"
    )
    d2 = DeferredFinding(
        finding_id="F-2", location="src/b.py:2", description="second", source_story_id="5-3"
    )
    fixed = datetime(2026, 5, 4, 0, 0, 0, tzinfo=timezone.utc)
    record_defer_findings((d1,), target, story_id="5-2", clock=lambda: fixed)
    record_defer_findings((d2,), target, story_id="5-3", clock=lambda: fixed)
    content = target.read_text(encoding="utf-8")
    assert "## Deferred from: code review of 5-2 (2026-05-04)" in content
    assert "## Deferred from: code review of 5-3 (2026-05-04)" in content
    # Sections must be separated by a blank line, not run together.
    idx_first = content.index("## Deferred from: code review of 5-2")
    idx_second = content.index("## Deferred from: code review of 5-3")
    between = content[idx_first:idx_second]
    assert "\n\n" in between, "sections must be separated by a blank line"


# ---------------------------------------------------------------------------
# AC-7 — composition test
# ---------------------------------------------------------------------------


def test_route_envelope_then_derive_action_items_composition() -> None:
    """RETRY_DEV outcome → derive_action_items returns the patch findings."""
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="patch", severity="HIGH"),
            _make_finding(id="F-2", bucket="patch", severity="MED"),
            _make_finding(id="F-3", bucket="defer", severity="LOW"),
        )
    )
    assert route_envelope(env) is RoutingOutcome.RETRY_DEV
    items = derive_action_items(env)
    assert len(items) == 2
    assert [i.finding_id for i in items] == ["F-1", "F-2"]


def test_route_envelope_then_escalate_does_not_derive_action_items() -> None:
    """ESCALATE outcome → caller does NOT call derive_action_items."""
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="decision_needed", severity="HIGH"),
            _make_finding(id="F-2", bucket="patch", severity="HIGH"),
        )
    )
    outcome = route_envelope(env)
    assert outcome is RoutingOutcome.ESCALATE
    # Composition discipline: the orchestrator-skill branches on outcome
    # BEFORE calling derive_action_items. derive_action_items would still
    # work on this envelope (returns the patch finding) but the
    # orchestrator-skill must NOT call it because the outcome is ESCALATE.
    if outcome is RoutingOutcome.RETRY_DEV:  # pragma: no cover
        derive_action_items(env)


def test_defer_outcome_composes_with_derive_deferred_findings() -> None:
    env = _make_envelope(
        findings=(
            _make_finding(id="F-1", bucket="defer", severity="MED"),
            _make_finding(id="F-2", bucket="dismiss", severity="LOW"),
        )
    )
    outcome = route_envelope(env)
    assert outcome is RoutingOutcome.DEFER_AND_ADVANCE
    items = derive_deferred_findings(env, source_story_id="5-2-test")
    assert len(items) == 1
    assert items[0].finding_id == "F-1"
