"""Contract-coverage matrix for the QA-wrapper prose thickening
landed by Story 9.4 (mobile exploratory heuristics).

Mirrors the wrapper-prose-validation pattern established by
``test_qa_wrapper.py`` (Story 4.13 baseline) for surgical-thickening
witnesses. Substring matches are case-sensitive and tolerate
surrounding context; assertion failures surface drift between the
story's AC-4(a) / AC-4(b) / AC-9 directives and the actual file
contents.

Test enumeration (Story 9.4 AC-8 — ≥ 3 logical tests):

    1. test_qa_wrapper_step_8_has_mobile_branch_paragraph
    2. test_qa_wrapper_forward_pointer_for_story_9_4_now_landed
    3. test_qa_driver_mobile_step_file_forward_pointer_now_landed
"""

from __future__ import annotations

from loud_fail_harness._shared import find_repo_root

REPO_ROOT = find_repo_root()
QA_AGENT_PATH = REPO_ROOT / "agents" / "qa.md"
QA_DRIVER_MOBILE_PATH = (
    REPO_ROOT / "skills" / "bmad-automation" / "steps" / "qa-driver-mobile.md"
)


def test_qa_wrapper_step_8_has_mobile_branch_paragraph() -> None:
    """AC-4(a) witness: the mobile-branch sub-paragraph appears in
    ``agents/qa.md`` step-8 body verbatim."""
    text = QA_AGENT_PATH.read_text(encoding="utf-8")
    expected = (
        'On the mobile project-type branch (when project_type == "mobile"), '
        "the per-kind driving procedure follows the mobile-specific scenario "
        "rebinding documented in skills/bmad-automation/steps/qa-mobile-heuristics.md "
        "(Story 9.4):"
    )
    assert expected in text


def test_qa_wrapper_forward_pointer_for_story_9_4_now_landed() -> None:
    """AC-4(b) witness: the forward-pointer bullet now reads
    ``Epic 9 / Story 9.4 (LANDED)`` and the pre-edit text has been
    removed."""
    text = QA_AGENT_PATH.read_text(encoding="utf-8")
    assert (
        "**Epic 9 / Story 9.4 (LANDED) — mobile exploratory heuristics.**"
        in text
    )
    pre_edit = (
        "Mobile-specific exploratory heuristics compose against THIS story's "
        "`mobile_driver` substrate landing at AC-iteration time; the "
        "`heuristic-skipped` marker class extends with mobile-driver "
        "sub-classifications. THIS story does NOT pre-empt Story 9.4 — the "
        "mobile branch at step 8 above currently iterates the same three "
        "Phase-1 heuristics (empty-state, error-state, auth-boundary) AS-IS; "
        "mobile-parity heuristics are 9.4's surface."
    )
    assert pre_edit not in text


def test_qa_driver_mobile_step_file_forward_pointer_now_landed() -> None:
    """AC-9 witness: the Story 9.4 forward-pointer bullet at the bottom
    of ``qa-driver-mobile.md`` has been updated to a now-landed
    pointer; the pre-edit text has been removed."""
    text = QA_DRIVER_MOBILE_PATH.read_text(encoding="utf-8")
    assert (
        "**Story 9.4 (LANDED) — mobile exploratory heuristics "
        "(three MVP-parity heuristics with `heuristic-skipped` "
        "emission)**"
        in text
    )
    pre_edit_tail = (
        "the heuristic dispatcher composes the same three Phase-1 "
        "heuristics (empty-state, error-state, auth-boundary) AS-IS, "
        "with the addition of mobile-specific applicability gating."
    )
    assert pre_edit_tail not in text
