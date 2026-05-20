"""Contract-coverage matrix for the QA Behavioral Plan library (story 4.1).

Mirrors the test-file shape established by ``test_story_doc_validator.py``
(story 1.10b) and the canonical-fixture regeneration-baseline pattern from
``test_bundle_assembly.py`` (story 3.4 — fixture round-trip discipline).

Test enumeration (32 tests — 19 from Story 4.1 AC-6, 11 added by Story
13.2 AC-8 / AC-5 for the FR22c ``flow_branches`` surface, 2 added by
Story 13.2 code-review patches for defensive-parser coverage):
    1.  test_generate_plan_first_run_structure
    2.  test_generate_plan_ac_hash_matches_compute_ac_hash
    3.  test_compute_ac_hash_deterministic
    4.  test_compute_ac_hash_whitespace_stable
    5.  test_compute_ac_hash_content_discriminates
    6.  test_compute_ac_hash_order_treatment
    7.  test_render_parse_round_trip_single_ac
    8.  test_render_parse_round_trip_multi_ac_mixed_tiers
    9.  test_parse_plan_section_returns_none_for_non_plan_text
    10. test_persist_or_reuse_plan_write_new_when_no_existing_plan
    11. test_persist_or_reuse_plan_reuse_existing_preserves_generated_status
    12. test_persist_or_reuse_plan_reuse_existing_preserves_human_reviewed_status
    13. test_persist_or_reuse_plan_drift_suspected_when_hash_mismatches
    14. test_persist_or_reuse_plan_does_not_perform_file_io
    15. test_section_name_is_in_allowlist
    16. test_canonical_fixture_round_trips_through_parse_render
    17. test_module_all_exports
    18. test_plan_persist_action_enum_values
    19. test_qa_behavioral_plan_has_lf_line_endings
    20. test_flow_branch_disposition_defaults_to_must_visit
    21. test_flow_branch_intentionally_skipped_with_rationale_constructs
    22. test_flow_branch_intentionally_skipped_without_rationale_raises
    23. test_flow_branch_must_visit_with_rationale_raises
    24. test_plan_entry_without_flow_branches_defaults_empty
    25. test_render_parse_round_trip_with_flow_branches
    26. test_parse_pre_fr22c_plan_yields_empty_flow_branches
    27. test_flow_branches_fixture_round_trips
    28. test_module_all_exports_flow_branch_symbols
    29. test_flow_branch_lines_do_not_pollute_scalar_field_extraction
    30. test_parse_plan_section_returns_none_for_malformed_flow_branches
    31. test_parse_plan_section_returns_none_for_missing_description
    32. test_parse_plan_section_returns_none_for_flow_branches_header_no_records
"""

from __future__ import annotations

import builtins
import pathlib

import pytest
from pydantic import ValidationError

from loud_fail_harness import qa_behavioral_plan
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.qa_behavioral_plan import (
    AcEntry,
    FlowBranch,
    PlanPersistAction,
    QABehavioralPlan,
    QABehavioralPlanEntry,
    compute_ac_hash,
    generate_plan,
    parse_plan_section,
    persist_or_reuse_plan,
    render_plan_section,
)
from loud_fail_harness.story_doc_validator import validate_section_write


@pytest.fixture(scope="module")
def repo_root() -> pathlib.Path:
    """Module-scoped repo-root fixture (Epic 1 retro Action #1: never call
    ``find_repo_root`` at module top-level)."""
    return find_repo_root()


def _three_ac_fixture() -> list[AcEntry]:
    return [
        AcEntry(ac_id="1", ac_text="User can register with email."),
        AcEntry(ac_id="2", ac_text="Form rejects invalid email syntax."),
        AcEntry(ac_id="3", ac_text="Unauthenticated /dashboard redirects."),
    ]


# 1
def test_generate_plan_first_run_structure() -> None:
    ac_list = _three_ac_fixture()
    plan = generate_plan(story_id="4.1-test", ac_list=ac_list)
    assert len(plan.entries) == 3
    for entry in plan.entries:
        assert entry.assertion_shape
        assert entry.expected_evidence_tier in {
            "tier-1-mechanical",
            "tier-2-outcome",
            "tier-3-semantic",
        }
        assert entry.semantic_verification_requirement in {
            "required",
            "optional",
            "not_applicable",
        }
        assert isinstance(entry.heuristic_applicability, tuple)
    assert plan.plan_status == "generated"
    assert isinstance(plan.ac_hash, str) and len(plan.ac_hash) == 64
    int(plan.ac_hash, 16)  # validates hex


# 2
def test_generate_plan_ac_hash_matches_compute_ac_hash() -> None:
    ac_list = _three_ac_fixture()
    plan = generate_plan(story_id="4.1-test", ac_list=ac_list)
    assert plan.ac_hash == compute_ac_hash(ac_list)


# 3
def test_compute_ac_hash_deterministic() -> None:
    ac_list = _three_ac_fixture()
    assert compute_ac_hash(ac_list) == compute_ac_hash(ac_list)


# 4
def test_compute_ac_hash_whitespace_stable() -> None:
    ac_list_a = [
        AcEntry(ac_id="1", ac_text="foo bar baz"),
        AcEntry(ac_id="2", ac_text="alpha beta"),
    ]
    ac_list_b = [
        AcEntry(ac_id="1", ac_text="  foo  bar\tbaz  "),
        AcEntry(ac_id="2", ac_text="\nalpha   beta\n"),
    ]
    assert compute_ac_hash(ac_list_a) == compute_ac_hash(ac_list_b)


# 5
def test_compute_ac_hash_content_discriminates() -> None:
    ac_list_a = [AcEntry(ac_id="1", ac_text="foo bar baz")]
    ac_list_b = [AcEntry(ac_id="1", ac_text="foo bar qux")]
    assert compute_ac_hash(ac_list_a) != compute_ac_hash(ac_list_b)


# 6
def test_compute_ac_hash_order_treatment() -> None:
    """Order-stable: AC reordering with same content yields the same hash
    (epics.md line 1855; recorded in module docstring + architecture.md
    addendum AC-7)."""
    ac_list_in_order = [
        AcEntry(ac_id="1", ac_text="alpha"),
        AcEntry(ac_id="2", ac_text="beta"),
        AcEntry(ac_id="3", ac_text="gamma"),
    ]
    ac_list_reversed = [
        AcEntry(ac_id="1", ac_text="gamma"),
        AcEntry(ac_id="2", ac_text="beta"),
        AcEntry(ac_id="3", ac_text="alpha"),
    ]
    assert compute_ac_hash(ac_list_in_order) == compute_ac_hash(
        ac_list_reversed
    )


# 7
def test_render_parse_round_trip_single_ac() -> None:
    plan = generate_plan(
        story_id="4.1-test",
        ac_list=[AcEntry(ac_id="1", ac_text="single AC")],
    )
    rendered = render_plan_section(plan)
    parsed = parse_plan_section(rendered)
    assert parsed == plan


# 8
def test_render_parse_round_trip_multi_ac_mixed_tiers() -> None:
    plan = QABehavioralPlan(
        plan_status="generated",
        ac_hash="0" * 64,
        entries=(
            QABehavioralPlanEntry(
                ac_id="1",
                assertion_shape="verify: x",
                expected_evidence_tier="tier-1-mechanical",
                semantic_verification_requirement="not_applicable",
                heuristic_applicability=(),
            ),
            QABehavioralPlanEntry(
                ac_id="2",
                assertion_shape="verify: y",
                expected_evidence_tier="tier-2-outcome",
                semantic_verification_requirement="required",
                heuristic_applicability=("empty-state", "auth-boundary"),
            ),
            QABehavioralPlanEntry(
                ac_id="3",
                assertion_shape="verify: z",
                expected_evidence_tier="tier-3-semantic",
                semantic_verification_requirement="optional",
                heuristic_applicability=("error-state",),
            ),
        ),
    )
    rendered = render_plan_section(plan)
    parsed = parse_plan_section(rendered)
    assert parsed == plan


# 9
def test_parse_plan_section_returns_none_for_non_plan_text() -> None:
    assert parse_plan_section("not a plan section body") is None
    assert parse_plan_section("") is None
    assert parse_plan_section("### AC-1\n- assertion_shape: x\n") is None


# 10
def test_persist_or_reuse_plan_write_new_when_no_existing_plan() -> None:
    story_doc_text = (
        "# Story 4.1\n\n## Acceptance Criteria\n\n1. AC-1 text\n"
    )
    ac_list = [AcEntry(ac_id="1", ac_text="AC-1 text")]
    plan, action = persist_or_reuse_plan(
        story_doc_text=story_doc_text, story_id="4.1", ac_list=ac_list
    )
    assert action == "write-new"
    assert plan.plan_status == "generated"


def _story_doc_with_plan(plan_status: str, ac_hash: str) -> str:
    return (
        "# Story 4.1\n\n"
        "## Acceptance Criteria\n\n1. AC-1 text\n\n"
        "## QA Behavioral Plan\n"
        f"<!-- plan_status: {plan_status} -->\n"
        f"<!-- ac_hash: {ac_hash} -->\n\n"
        "### AC-1\n\n"
        "- assertion_shape: verify: AC-1 text\n"
        "- expected_evidence_tier: tier-1-mechanical\n"
        "- semantic_verification_requirement: not_applicable\n"
        "- heuristic_applicability: []\n\n"
        "## Some Other Section\n\nbody\n"
    )


# 11
def test_persist_or_reuse_plan_reuse_existing_preserves_generated_status() -> None:
    ac_list = [AcEntry(ac_id="1", ac_text="AC-1 text")]
    ac_hash = compute_ac_hash(ac_list)
    story_doc_text = _story_doc_with_plan(
        plan_status="generated", ac_hash=ac_hash
    )
    plan, action = persist_or_reuse_plan(
        story_doc_text=story_doc_text, story_id="4.1", ac_list=ac_list
    )
    assert action == "reuse-existing"
    assert plan.plan_status == "generated"


# 12
def test_persist_or_reuse_plan_reuse_existing_preserves_human_reviewed_status() -> None:
    ac_list = [AcEntry(ac_id="1", ac_text="AC-1 text")]
    ac_hash = compute_ac_hash(ac_list)
    story_doc_text = _story_doc_with_plan(
        plan_status="human-reviewed", ac_hash=ac_hash
    )
    plan, action = persist_or_reuse_plan(
        story_doc_text=story_doc_text, story_id="4.1", ac_list=ac_list
    )
    assert action == "reuse-existing"
    assert plan.plan_status == "human-reviewed"


# 13
def test_persist_or_reuse_plan_drift_suspected_when_hash_mismatches() -> None:
    ac_list = [AcEntry(ac_id="1", ac_text="AC-1 text — UPDATED")]
    stale_hash = "f" * 64
    story_doc_text = _story_doc_with_plan(
        plan_status="human-reviewed", ac_hash=stale_hash
    )
    plan, action = persist_or_reuse_plan(
        story_doc_text=story_doc_text, story_id="4.1", ac_list=ac_list
    )
    assert action == "drift-suspected"
    # plan_status UNCHANGED — story 4.1 does NOT reset; story 4.2 does.
    assert plan.plan_status == "human-reviewed"
    assert plan.ac_hash == stale_hash


# 14
def test_persist_or_reuse_plan_does_not_perform_file_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_open(*args: object, **kwargs: object) -> object:
        raise AssertionError(
            "persist_or_reuse_plan must not perform file I/O"
        )

    monkeypatch.setattr(builtins, "open", _no_open)

    def _no_read_text(self: pathlib.Path, *a: object, **kw: object) -> str:
        raise AssertionError(
            "persist_or_reuse_plan must not call Path.read_text"
        )

    def _no_write_text(
        self: pathlib.Path, *a: object, **kw: object
    ) -> int:
        raise AssertionError(
            "persist_or_reuse_plan must not call Path.write_text"
        )

    monkeypatch.setattr(pathlib.Path, "read_text", _no_read_text)
    monkeypatch.setattr(pathlib.Path, "write_text", _no_write_text)

    ac_list = [AcEntry(ac_id="1", ac_text="AC-1 text")]
    persist_or_reuse_plan(
        story_doc_text="# story\n\n## Acceptance Criteria\n\n1. AC\n",
        story_id="4.1",
        ac_list=ac_list,
    )


# 15
def test_section_name_is_in_allowlist() -> None:
    result = validate_section_write("## QA Behavioral Plan")
    assert result.accepted is True


# 16
def test_canonical_fixture_round_trips_through_parse_render(
    repo_root: pathlib.Path,
) -> None:
    fixture_path = (
        repo_root
        / "examples"
        / "qa-behavioral-plans"
        / "qa-behavioral-plan-multi-ac-mixed-tiers.md"
    )
    fixture_text = fixture_path.read_text(encoding="utf-8")
    parsed = parse_plan_section(fixture_text)
    assert parsed is not None
    assert render_plan_section(parsed) == fixture_text


# 17
def test_module_all_exports() -> None:
    expected = {
        "QABehavioralPlan",
        "PlanPersistAction",
        "generate_plan",
        "compute_ac_hash",
        "render_plan_section",
        "parse_plan_section",
        "persist_or_reuse_plan",
    }
    assert expected.issubset(set(qa_behavioral_plan.__all__))


# 18
def test_plan_persist_action_enum_values() -> None:
    """``PlanPersistAction`` is a ``Literal`` carrying exactly three values."""
    args = PlanPersistAction.__args__  # type: ignore[attr-defined]
    assert set(args) == {"write-new", "reuse-existing", "drift-suspected"}
    assert len(args) == 3


# 19
def test_qa_behavioral_plan_has_lf_line_endings(
    repo_root: pathlib.Path,
) -> None:
    module_path = (
        repo_root
        / "tools"
        / "loud-fail-harness"
        / "src"
        / "loud_fail_harness"
        / "qa_behavioral_plan.py"
    )
    raw = module_path.read_bytes()
    assert b"\r" not in raw


# 20
def test_flow_branch_disposition_defaults_to_must_visit() -> None:
    """AC-8.1 — ``FlowBranch.disposition`` defaults to ``"must-visit"`` when
    ``disposition`` is omitted (FR22c default-disposition rule)."""
    branch = FlowBranch(branch_id="happy-path", description="the main flow")
    assert branch.disposition == "must-visit"
    assert branch.skip_rationale is None


# 21
def test_flow_branch_intentionally_skipped_with_rationale_constructs() -> None:
    """AC-8.2 — an ``intentionally-skipped`` branch with a non-empty
    ``skip_rationale`` constructs successfully."""
    branch = FlowBranch(
        branch_id="duplicate-email",
        description="resubmitting an already-registered email",
        disposition="intentionally-skipped",
        skip_rationale="covered by AC-3's uniqueness assertion",
    )
    assert branch.disposition == "intentionally-skipped"
    assert branch.skip_rationale == "covered by AC-3's uniqueness assertion"


# 22
def test_flow_branch_intentionally_skipped_without_rationale_raises() -> None:
    """AC-8.3 — an ``intentionally-skipped`` branch with a missing, empty, or
    whitespace-only ``skip_rationale`` raises ``ValidationError``."""
    for bad_rationale in (None, "", "   "):
        with pytest.raises(ValidationError):
            FlowBranch(
                branch_id="x",
                description="d",
                disposition="intentionally-skipped",
                skip_rationale=bad_rationale,
            )


# 23
def test_flow_branch_must_visit_with_rationale_raises() -> None:
    """AC-8.4 — a ``must-visit`` branch carrying a non-``None``
    ``skip_rationale`` raises ``ValidationError`` (a rationale on a
    must-visit branch is a contradiction). Holds for explicit and defaulted
    ``disposition``."""
    with pytest.raises(ValidationError):
        FlowBranch(
            branch_id="x",
            description="d",
            disposition="must-visit",
            skip_rationale="should not be here",
        )
    with pytest.raises(ValidationError):
        FlowBranch(
            branch_id="x",
            description="d",
            skip_rationale="must-visit is the default disposition",
        )


# 24
def test_plan_entry_without_flow_branches_defaults_empty() -> None:
    """AC-8.5 — constructing a ``QABehavioralPlanEntry`` WITHOUT
    ``flow_branches`` succeeds and yields ``flow_branches == ()`` (the
    additive-optional contract)."""
    entry = QABehavioralPlanEntry(
        ac_id="1",
        assertion_shape="verify: x",
        expected_evidence_tier="tier-1-mechanical",
        semantic_verification_requirement="not_applicable",
    )
    assert entry.flow_branches == ()


def _flow_branch_plan() -> QABehavioralPlan:
    """A two-AC plan: AC-1 with empty ``flow_branches`` (omit-when-empty
    path), AC-2 with mixed dispositions. Used by the round-trip + field-
    pollution tests."""
    return QABehavioralPlan(
        plan_status="generated",
        ac_hash="a" * 64,
        entries=(
            QABehavioralPlanEntry(
                ac_id="1",
                assertion_shape="verify: linear AC",
                expected_evidence_tier="tier-1-mechanical",
                semantic_verification_requirement="not_applicable",
            ),
            QABehavioralPlanEntry(
                ac_id="2",
                assertion_shape="verify: branching AC",
                expected_evidence_tier="tier-2-outcome",
                semantic_verification_requirement="required",
                heuristic_applicability=("error-state",),
                flow_branches=(
                    FlowBranch(
                        branch_id="happy-path",
                        description="valid submission persists the record",
                    ),
                    FlowBranch(
                        branch_id="duplicate",
                        description="resubmitting an existing record",
                        disposition="intentionally-skipped",
                        skip_rationale="covered by AC-1's uniqueness check",
                    ),
                ),
            ),
        ),
    )


# 25
def test_render_parse_round_trip_with_flow_branches() -> None:
    """AC-8.6 — a render→parse round-trip of a plan whose entries carry
    populated ``flow_branches`` with mixed dispositions yields
    ``parsed == original``."""
    plan = _flow_branch_plan()
    parsed = parse_plan_section(render_plan_section(plan))
    assert parsed == plan


# 26
def test_parse_pre_fr22c_plan_yields_empty_flow_branches() -> None:
    """AC-8.7 — parsing a plan section with NO ``flow_branches`` blocks
    yields entries with ``flow_branches == ()`` and does not raise
    (back-compat contract)."""
    plan = QABehavioralPlan(
        plan_status="generated",
        ac_hash="b" * 64,
        entries=(
            QABehavioralPlanEntry(
                ac_id="1",
                assertion_shape="verify: x",
                expected_evidence_tier="tier-1-mechanical",
                semantic_verification_requirement="not_applicable",
            ),
            QABehavioralPlanEntry(
                ac_id="2",
                assertion_shape="verify: y",
                expected_evidence_tier="tier-2-outcome",
                semantic_verification_requirement="required",
                heuristic_applicability=("empty-state",),
            ),
        ),
    )
    rendered = render_plan_section(plan)
    assert "- flow_branches:" not in rendered
    parsed = parse_plan_section(rendered)
    assert parsed is not None
    assert all(entry.flow_branches == () for entry in parsed.entries)
    assert parsed == plan


# 27
def test_flow_branches_fixture_round_trips(repo_root: pathlib.Path) -> None:
    """AC-8.8 — the new ``qa-behavioral-plan-flow-branches.md`` fixture
    round-trips byte-for-byte through ``parse_plan_section`` →
    ``render_plan_section``, and exercises both dispositions plus the
    omit-when-empty path."""
    fixture_path = (
        repo_root
        / "examples"
        / "qa-behavioral-plans"
        / "qa-behavioral-plan-flow-branches.md"
    )
    fixture_text = fixture_path.read_text(encoding="utf-8")
    parsed = parse_plan_section(fixture_text)
    assert parsed is not None
    assert render_plan_section(parsed) == fixture_text
    dispositions = {
        branch.disposition
        for entry in parsed.entries
        for branch in entry.flow_branches
    }
    assert dispositions == {"must-visit", "intentionally-skipped"}
    assert any(entry.flow_branches == () for entry in parsed.entries)


# 28
def test_module_all_exports_flow_branch_symbols() -> None:
    """AC-8.9 — ``qa_behavioral_plan.__all__`` contains ``FlowBranch`` and
    ``FlowBranchDisposition``."""
    assert {"FlowBranch", "FlowBranchDisposition"}.issubset(
        set(qa_behavioral_plan.__all__)
    )


# 29
def test_flow_branch_lines_do_not_pollute_scalar_field_extraction() -> None:
    """AC-5 — the indented branch-record lines and the bare
    ``- flow_branches:`` header MUST NOT be captured by the
    column-0-anchored ``_FIELD_LINE_RE`` four-scalar-field extraction."""
    rendered = render_plan_section(_flow_branch_plan())
    keys = {
        match.group("key")
        for match in qa_behavioral_plan._FIELD_LINE_RE.finditer(rendered)
    }
    assert keys == {
        "assertion_shape",
        "expected_evidence_tier",
        "semantic_verification_requirement",
        "heuristic_applicability",
    }


# 30
def test_parse_plan_section_returns_none_for_malformed_flow_branches() -> None:
    """A ``- flow_branches:`` header followed by an unparseable record line
    makes ``_parse_flow_branches`` raise ``ValueError`` → ``parse_plan_section``
    returns ``None`` (defensive-parser discipline)."""
    body = (
        "<!-- plan_status: generated -->\n"
        f"<!-- ac_hash: {'0' * 64} -->\n\n"
        "### AC-1\n\n"
        "- assertion_shape: verify: x\n"
        "- expected_evidence_tier: tier-1-mechanical\n"
        "- semantic_verification_requirement: not_applicable\n"
        "- heuristic_applicability: []\n"
        "- flow_branches:\n"
        "  this is not a valid branch record\n"
    )
    assert parse_plan_section(body) is None


# 31
def test_parse_plan_section_returns_none_for_missing_description() -> None:
    """Code-review patch — a branch record that omits the ``description``
    sub-field causes ``_parse_flow_branches`` to raise ``KeyError``
    (``record["description"]``) → ``parse_plan_section`` returns ``None``
    (defensive-parser discipline; no ``ValidationError`` escapes)."""
    body = (
        "<!-- plan_status: generated -->\n"
        f"<!-- ac_hash: {'0' * 64} -->\n\n"
        "### AC-1\n\n"
        "- assertion_shape: verify: x\n"
        "- expected_evidence_tier: tier-1-mechanical\n"
        "- semantic_verification_requirement: not_applicable\n"
        "- heuristic_applicability: []\n"
        "- flow_branches:\n"
        "  - branch_id: no-desc\n"
        "    disposition: must-visit\n"
    )
    assert parse_plan_section(body) is None


# 32
def test_parse_plan_section_returns_none_for_flow_branches_header_no_records() -> None:
    """Code-review patch — a ``- flow_branches:`` header immediately followed
    by a blank line (no branch records) causes ``_parse_flow_branches`` to
    raise ``ValueError`` → ``parse_plan_section`` returns ``None``."""
    body = (
        "<!-- plan_status: generated -->\n"
        f"<!-- ac_hash: {'0' * 64} -->\n\n"
        "### AC-1\n\n"
        "- assertion_shape: verify: x\n"
        "- expected_evidence_tier: tier-1-mechanical\n"
        "- semantic_verification_requirement: not_applicable\n"
        "- heuristic_applicability: []\n"
        "- flow_branches:\n"
        "\n"
    )
    assert parse_plan_section(body) is None
