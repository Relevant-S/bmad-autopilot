"""Contract-coverage matrix for the QA Behavioral Plan library (story 4.1).

Mirrors the test-file shape established by ``test_story_doc_validator.py``
(story 1.10b) and the canonical-fixture regeneration-baseline pattern from
``test_bundle_assembly.py`` (story 3.4 — fixture round-trip discipline).

Test enumeration (AC-6 — 19 tests):
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
"""

from __future__ import annotations

import builtins
import pathlib

import pytest

from loud_fail_harness import qa_behavioral_plan
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.qa_behavioral_plan import (
    AcEntry,
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
