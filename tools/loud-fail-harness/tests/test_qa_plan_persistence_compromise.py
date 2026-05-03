"""Contract-coverage matrix for the QA plan-persistence-compromise
visibility library (Story 4.11 — FR25).

Mirrors the test-file shape established by ``test_qa_behavioral_plan.py``
(Story 4.1) and the canonical-fixture regeneration-baseline pattern from
``test_bundle_assembly.py`` (Story 3.4).

Test enumeration (AC-7 — 11 tests across 5 categories + 1 module-exports check = 12 total):

    Category 1 — constant content (AC-1):
        1. test_compromise_note_body_is_three_lines
        2. test_compromise_note_body_contains_persistence_phrase
        3. test_compromise_note_body_contains_purity_tradeoff_phrase
        4. test_compromise_note_body_contains_phase2_upgrade_pointer

    Category 2 — blockquote shape (AC-1):
        5. test_render_compromise_blockquote_is_well_formed_markdown_blockquote
        6. test_render_compromise_blockquote_is_deterministic

    Category 3 — drift-prevention against audit doc (AC-6):
        7. test_audit_doc_contains_compromise_note_body_lines

    Category 4 — render-site integration (AC-2 + AC-3):
        8. test_render_plan_section_prepends_blockquote
        9. test_render_plan_section_round_trips_with_blockquote
        10. test_render_per_ac_section_prepends_blockquote

    Category 5 — fixture pin (AC-2 + AC-8):
        11. test_canonical_fixture_includes_blockquote
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest

from loud_fail_harness import qa_plan_persistence_compromise
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.bundle_assembly import _render_per_ac_section
from loud_fail_harness.qa_behavioral_plan import (
    QABehavioralPlan,
    QABehavioralPlanEntry,
    parse_plan_section,
    render_plan_section,
)
from loud_fail_harness.qa_plan_persistence_compromise import (
    COMPROMISE_NOTE_BODY,
    render_compromise_blockquote,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)


@pytest.fixture(scope="module")
def repo_root() -> pathlib.Path:
    """Module-scoped repo-root fixture (Epic 1 retro Action #1: never call
    ``find_repo_root`` at module top-level)."""
    return find_repo_root()


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


def _minimal_plan() -> QABehavioralPlan:
    return QABehavioralPlan(
        plan_status="generated",
        ac_hash="0" * 64,
        entries=(
            QABehavioralPlanEntry(
                ac_id="1",
                assertion_shape="verify: minimal",
                expected_evidence_tier="tier-1-mechanical",
                semantic_verification_requirement="not_applicable",
                heuristic_applicability=(),
            ),
        ),
    )


# 1
def test_compromise_note_body_is_three_lines() -> None:
    """The constant carries exactly three newline-separated lines (AC-1)."""
    lines = COMPROMISE_NOTE_BODY.split("\n")
    assert len(lines) == 3
    # No trailing newline (consumers add their own line endings as needed).
    assert not COMPROMISE_NOTE_BODY.endswith("\n")


# 2
def test_compromise_note_body_contains_persistence_phrase() -> None:
    """The verbatim persistence phrase from epics.md line 2134 (AC-1 (i))."""
    assert (
        "This plan is persisted across runs for resumability."
        in COMPROMISE_NOTE_BODY
    )


# 3
def test_compromise_note_body_contains_purity_tradeoff_phrase() -> None:
    """The verbatim purity-tradeoff phrase from epics.md line 2134 (AC-1 (ii))."""
    assert (
        "Persistence is a known compromise: full QA independence would "
        "re-derive the plan every run."
        in COMPROMISE_NOTE_BODY
    )


# 4
def test_compromise_note_body_contains_phase2_upgrade_pointer() -> None:
    """The FR-P2-9 + audit-doc cross-references (AC-1 (iii))."""
    assert "FR-P2-9" in COMPROMISE_NOTE_BODY
    assert "docs/extension-audit.md" in COMPROMISE_NOTE_BODY


# 5
def test_render_compromise_blockquote_is_well_formed_markdown_blockquote() -> None:
    """Every line is ``> ``-prefixed; first line carries the bold FR25
    heading; trailing newline present (AC-1)."""
    rendered = render_compromise_blockquote()
    assert rendered.endswith("\n")

    lines = rendered.rstrip("\n").split("\n")
    # Heading + blank-blockquote-line + 3 prose lines = 5 lines.
    assert len(lines) == 5

    # Every line begins with the level-1 blockquote prefix.
    for line in lines:
        assert line.startswith(">")
        # Level-1 blockquote: either ``> `` or the empty-blockquote ``>``.
        assert line == ">" or line.startswith("> ")

    # First line is the bold FR25-anchored heading.
    assert "**Plan-persistence compromise note (FR25):**" in lines[0]

    # Lines 3-5 each carry a non-empty compromise prose continuation.
    for body_line, prose_line in zip(lines[2:], COMPROMISE_NOTE_BODY.split("\n")):
        assert body_line == f"> {prose_line}"


# 6
def test_render_compromise_blockquote_is_deterministic() -> None:
    """Two calls return byte-identical strings (AC-1 — fully deterministic)."""
    assert render_compromise_blockquote() == render_compromise_blockquote()


# 7
def test_audit_doc_contains_compromise_note_body_lines(
    repo_root: pathlib.Path,
) -> None:
    """Drift-prevention anchor (AC-6): every non-empty line of
    :data:`COMPROMISE_NOTE_BODY` MUST appear as a substring in the audit
    doc. The audit-doc row encodes line-breaks as ``<br>`` so the multiline
    constant cannot match as a single substring; the per-line search is
    the structurally-correct drift check."""
    audit_path = repo_root / "docs" / "extension-audit.md"
    audit_text = audit_path.read_text(encoding="utf-8")
    for line in COMPROMISE_NOTE_BODY.split("\n"):
        if not line:
            continue
        assert line in audit_text, (
            f"COMPROMISE_NOTE_BODY line is missing from the audit doc — "
            f"single-source-of-truth drift-prevention invariant violated "
            f"(missing line: {line!r}). Update "
            f"`docs/extension-audit.md`'s Story 4.11 row to carry the "
            f"updated constant prose verbatim, OR revert the constant "
            f"change."
        )


# 8
def test_render_plan_section_prepends_blockquote() -> None:
    """``render_plan_section`` PREPENDS the compromise blockquote (AC-2):
    the rendered body's first line is the blockquote's first line."""
    body = render_plan_section(_minimal_plan())
    blockquote = render_compromise_blockquote()
    assert body.startswith(blockquote)
    # Blockquote is followed by a blank line then the HTML-comment metadata.
    assert "\n\n<!-- plan_status: generated -->" in body


# 9
def test_render_plan_section_round_trips_with_blockquote() -> None:
    """The Story 4.1 AC-4 round-trip discipline holds with the new prepend
    (AC-2): ``parse_plan_section(render_plan_section(plan)) == plan``."""
    plan = _minimal_plan()
    rendered = render_plan_section(plan)
    parsed = parse_plan_section(rendered)
    assert parsed == plan


# 10
def test_render_per_ac_section_prepends_blockquote(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """``_render_per_ac_section`` PREPENDS the compromise blockquote even
    when ``ac_results`` is empty/missing (AC-3 — unconditional prepend)."""
    qa_envelope_empty: dict[str, Any] = {}
    body = _render_per_ac_section(
        qa_envelope_empty, marker_registry=runtime_marker_registry
    )
    blockquote = render_compromise_blockquote()
    # The blockquote rstripped of its trailing newline is prepended; the
    # joining ``\n\n`` produces blank-line separation from the placeholder.
    assert body.startswith(blockquote.rstrip("\n"))
    # Even when ac_results is empty, the placeholder appears AFTER the
    # blockquote — verifying unconditional prepend.
    assert "_(no ac_results in QA envelope)_" in body
    # The placeholder appears strictly after the blockquote's last line.
    blockquote_end = body.find(blockquote.rstrip("\n")) + len(
        blockquote.rstrip("\n")
    )
    placeholder_start = body.find("_(no ac_results in QA envelope)_")
    assert placeholder_start > blockquote_end


# 11
def test_canonical_fixture_includes_blockquote(
    repo_root: pathlib.Path,
) -> None:
    """The regen-baseline fixture's first line is the blockquote heading
    (AC-2 + AC-8)."""
    fixture_path = (
        repo_root
        / "examples"
        / "qa-behavioral-plans"
        / "qa-behavioral-plan-multi-ac-mixed-tiers.md"
    )
    fixture_text = fixture_path.read_text(encoding="utf-8")
    blockquote = render_compromise_blockquote()
    assert fixture_text.startswith(blockquote)


# Module-level public-API exposure check (mirrors Story 4.1's
# `test_module_all_exports`).
def test_module_all_exports() -> None:
    """The module's ``__all__`` enumerates exactly the two public symbols
    named by AC-1."""
    assert set(qa_plan_persistence_compromise.__all__) == {
        "COMPROMISE_NOTE_BODY",
        "render_compromise_blockquote",
    }
