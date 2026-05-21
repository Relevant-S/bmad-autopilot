"""Contract-coverage matrix for the QA-wrapper prose thickening landed
by Story 13.4 (FR22c within-AC flow-branch coverage — web + mobile
parity).

Mirrors the wrapper-prose-validation pattern established by
``test_qa_wrapper.py`` (Story 4.13 baseline) and
``test_qa_wrapper_mobile_heuristics.py`` (Story 9.4 surgical-thickening
witness). Substring matches are case-sensitive and tolerate surrounding
context; an assertion failure surfaces drift between Story 13.4's
AC-1..AC-6 directives and the actual ``agents/qa.md`` contents.

Test enumeration (Story 13.4 AC-8 — 7 logical tests):

    1. test_plan_generation_phase_instructs_flow_branch_enumeration
    2. test_plan_generation_phase_names_model_copy_frozen_idiom
    3. test_run_phase_instructs_must_visit_branch_driving
    4. test_run_phase_carries_mobile_sub_paragraph_and_names_three_project_types
    5. test_smoke_first_abort_flow_branch_precedence_clause_present
    6. test_return_envelope_documents_flow_branch_coverage_boundary
    7. test_fr_surface_clause_names_fr22c_story_13_4_pattern_8
"""

from __future__ import annotations

from loud_fail_harness._shared import find_repo_root

REPO_ROOT = find_repo_root()
QA_AGENT_PATH = REPO_ROOT / "agents" / "qa.md"


def test_plan_generation_phase_instructs_flow_branch_enumeration() -> None:
    """AC-1 witness: the plan-generation phase (step 3 / step 4 region)
    instructs the agent to enumerate each AC's optional / branching
    steps into the per-AC ``flow_branches[]`` field."""
    text = QA_AGENT_PATH.read_text(encoding="utf-8")
    assert (
        "**FR22c within-AC flow-branch enumeration (plan-authoring "
        "branches only).**"
        in text
    )
    assert "identify the optional / branching steps of that AC's flow" in text
    assert "construct one `FlowBranch`" in text
    assert "flow_branches" in text
    # The drift-suspected regeneration path (step 4) is re-enumerated.
    assert (
        "apply the FR22c within-AC flow-branch enumeration of step 3 to "
        "`emission.fresh_plan`"
        in text
    )
    # reuse-existing does NOT re-enumerate; a strictly-linear AC yields
    # an empty flow_branches tuple.
    assert "The `reuse-existing` branch does NOT re-enumerate" in text
    assert "correctly yields an empty `flow_branches` tuple" in text


def test_plan_generation_phase_names_model_copy_frozen_idiom() -> None:
    """AC-1 witness: the plan-generation prose names the frozen-model
    enrichment idiom ``model_copy`` so the agent does not reach for an
    invalid in-place assignment."""
    text = QA_AGENT_PATH.read_text(encoding="utf-8")
    assert "frozen Pydantic v2 model" in text
    assert (
        'entry.model_copy(update={"flow_branches": (FlowBranch(...), ...)})'
        in text
    )


def test_run_phase_instructs_must_visit_branch_driving() -> None:
    """AC-2 witness: the run phase (step 6 region) instructs the agent
    to drive each ``must-visit`` branch and capture per-branch evidence,
    and names the ``iterate_acs`` flow-branch surface."""
    text = QA_AGENT_PATH.read_text(encoding="utf-8")
    assert "**FR22c within-AC flow-branch driving.**" in text
    assert (
        "you MUST exercise each `must-visit` branch's flow path through "
        "the `project_type` driver"
        in text
    )
    assert "capture per-branch evidence" in text
    assert "ac_results[i].evidence_refs" in text
    assert "flow_branch_coverage" in text
    assert "AcFlowBranchCoverage" in text
    assert "must_visit_branch_ids" in text
    # iterate_acs does NOT drive must-visit branches; the reconciliation
    # gate is named as a Story 13.5 forward pointer.
    assert "`iterate_acs` itself does NOT drive `must-visit` branches" in text
    assert "Story 13.5's CI fixture-driven gate" in text
    # intentionally-skipped branches need no driving.
    assert "You do NOT drive `intentionally-skipped` branches" in text


def test_run_phase_carries_mobile_sub_paragraph_and_names_three_project_types() -> None:
    """AC-3 witness: the run-phase branch-driving discipline is a
    project-type-agnostic core plus a mobile-specific sub-paragraph, and
    names all three project types (web / api / mobile)."""
    text = QA_AGENT_PATH.read_text(encoding="utf-8")
    # The mobile-specific branch-driving sub-paragraph — structurally
    # parallel to step 8's mobile paragraph but a distinct step-6 region
    # paragraph (the continuation "rebind ..." distinguishes it from the
    # step-8 verbatim block).
    assert (
        'On the mobile project-type branch (when project_type == "mobile"), '
        'rebind "drive each `must-visit` branch" to the mobile-MCP driving '
        "surface"
        in text
    )
    # The project-type-agnostic core names all three project types.
    assert (
        "exactly as AC-level driving already differs per `web` / `api` / "
        "`mobile`"
        in text
    )
    # The mobile sub-paragraph references the mobile step files without
    # modifying them.
    assert "skills/bmad-automation/steps/qa-driver-mobile.md" in text
    assert "skills/bmad-automation/steps/qa-mobile-heuristics.md" in text


def test_smoke_first_abort_flow_branch_precedence_clause_present() -> None:
    """AC-4 witness: the smoke-first-abort x flow-branch precedence rule
    is reflected in the step-6 prose."""
    text = QA_AGENT_PATH.read_text(encoding="utf-8")
    assert "flow-branch precedence (FR22b" in text
    assert "you do NOT drive AC-1's flow branches" in text
    assert "flow_branch_coverage == ()" in text
    # Non-aborting ACs: flow-branch processing runs regardless of status.
    assert (
        "flow-branch processing runs regardless of that AC's own `status`"
        in text
    )


def test_return_envelope_documents_flow_branch_coverage_boundary() -> None:
    """AC-5 witness: the Return envelope section documents that
    flow-branch records MUST NOT go in ``heuristic_skipped_emissions``
    and that flow-branch coverage rides on
    ``AcIterationResult.flow_branch_coverage``."""
    text = QA_AGENT_PATH.read_text(encoding="utf-8")
    assert (
        "### FR22c within-AC flow-branch coverage" in text
    )
    assert "AcIterationResult.flow_branch_coverage" in text
    assert (
        "The `flow-branch` skip records MUST NOT be placed in the "
        "envelope's `heuristic_skipped_emissions` array."
        in text
    )
    # Per-must-visit-branch evidence rides on the existing ac_results
    # evidence_refs array — no schema change.
    assert (
        "per-`must-visit`-branch evidence rides on the existing "
        "schema-validated `ac_results[i].evidence_refs` array"
        in text
    )
    # The QA Behavioral Plan section is the canonical operator-facing
    # FR22c surface.
    assert "canonical operator-facing FR22c surface" in text


def test_fr_surface_clause_names_fr22c_story_13_4_pattern_8() -> None:
    """AC-6 witness: a full-FR-surface clause names FR22c, Architecture
    Pattern 8, and Story 13.4 as the wrapper-prompt landing."""
    text = QA_AGENT_PATH.read_text(encoding="utf-8")
    assert "**Epic 13 / FR22c (Phase 1 patch" in text
    assert "Architecture Pattern 8" in text
    assert "THIS story (13.4)" in text
    # The v1 27-class marker-taxonomy closed-set is preserved.
    assert (
        "v1 27-class marker-taxonomy closed-set is preserved" in text
    )
    assert "Sprint Change Proposal 2026-05-20" in text
