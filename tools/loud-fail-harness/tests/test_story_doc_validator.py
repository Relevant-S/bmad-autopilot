"""Contract-coverage matrix for the story-doc section-allowlist library (story 1.10b).

This docstring IS the contract-coverage checklist required by AC-8. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to story 1.2 / 1.3 / 1.4 / 1.5 /
1.6 / 1.7 / 1.8 / 1.9 / 1.10a AC discipline).

Accepted-section cases (AC-3, AC-8) — one test per ALLOWED_SECTIONS entry:
    [x] ## Dev Agent Record (canonical first entry)               → test_accepted_dev_agent_record
    [x] ## Senior Developer Review (AI)                            → test_accepted_senior_developer_review_ai
    [x] ## Review Findings                                          → test_accepted_review_findings
    [x] ## QA Behavioral Plan (upstream-proposal addition)         → test_accepted_qa_behavioral_plan
    [x] ## Review Follow-ups (AI) (post-retry-escalation write)     → test_accepted_review_follow_ups_ai

Rejected-section cases (AC-3, AC-4, AC-8) — strict-equality + suggestion:
    [x] arbitrary unallowed name                                    → test_rejected_arbitrary_section
    [x] near-miss (## QA Plan vs ## QA Behavioral Plan)             → test_rejected_near_miss_qa_plan
    [x] case difference (lowercase variant)                          → test_rejected_case_difference
    [x] trailing whitespace                                          → test_rejected_trailing_whitespace
    [x] leading whitespace                                           → test_rejected_leading_whitespace
    [x] missing `## ` prefix                                         → test_rejected_missing_prefix
    [x] empty string                                                 → test_rejected_empty_string
    [x] whitespace-only string                                       → test_rejected_whitespace_only
    [x] unrelated input — no candidate clears cutoff                 → test_rejected_no_close_match

Type-validation cases (AC-3, AC-8):
    [x] non-string inputs (None, int, list, bytes) raise TypeError   → test_validate_section_write_rejects_non_string_input
    [x] is_allowed rejects non-string                                → test_is_allowed_rejects_non_string_input
    [x] closest_allowlisted rejects non-string                       → test_closest_allowlisted_rejects_non_string_input

Convenience-helper cases (AC-3, AC-4, AC-8):
    [x] is_allowed returns bool                                       → test_is_allowed_returns_bool
    [x] closest_allowlisted with n=2 returns first match              → test_closest_allowlisted_with_n_2
    [x] closest_allowlisted returns [] for unrelated                  → test_closest_allowlisted_returns_empty_for_unrelated

Marker-class taxonomy seam (AC-5):
    [x] undocumented-section-write class present in marker-taxonomy.yaml → test_undocumented_section_write_class_in_taxonomy

Allowlist constant shape (AC-2):
    [x] ALLOWED_SECTIONS is a tuple of strings, length 5              → test_allowed_sections_is_tuple_of_strings
    [x] ALLOWED_SECTIONS canonical PRD-line-901 order                  → test_allowed_sections_canonical_order
    [x] __all__ exports public API                                     → test_module_all_exports

Determinism + serialization (AC-6, AC-8):
    [x] two invocations on same input produce identical JSON           → test_determinism_repeated_invocation
    [x] ValidationResult.model_dump_json byte-identical                → test_validation_result_json_serialization_stable

Pydantic v2 frozen-model discipline (AC-6, AC-8):
    [x] ValidationResult is frozen + hashable                          → test_validation_result_is_frozen_and_hashable

CLI / main exit-code matrix (AC-7, AC-8):
    [x] main(['--help']) raises SystemExit(0)                          → test_main_help_resolves
    [x] main(['## Dev Agent Record']) returns 0; stdout JSON           → test_main_accepts_allowlisted_section
    [x] main(['## Bogus Section']) returns 1; stdout marker            → test_main_rejects_unallowed_section

Coverage (AC-8):
    [x] story_doc_validator.py module-level statement coverage ≥ 90%   → review-enforced; not a CI gate
"""

from __future__ import annotations

import io
import json
import pathlib
import sys
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.story_doc_validator import (
    ALLOWED_SECTIONS,
    ValidationResult,
    closest_allowlisted,
    is_allowed,
    main,
    validate_section_write,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _capture_main(argv: list[str]) -> tuple[int, str, str]:
    """Run ``main(argv)`` capturing stdout + stderr; return ``(rc, out, err)``.

    Mirrors the pattern used by the other harness CLI test suites
    (``test_pluggability_gate``, ``test_hook_budget_gate``, etc.).
    """
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        rc = main(argv)
    return rc, out_buf.getvalue(), err_buf.getvalue()


# ---------------------------------------------------------------------------
# Accepted-section tests (AC-3, AC-8)
# ---------------------------------------------------------------------------


def test_accepted_dev_agent_record() -> None:
    """``## Dev Agent Record`` is the canonical first allowlist entry.

    PRD line 901 enumeration order: Dev Agent Record first because it is
    the chronologically-first specialist write per ADR-005's section-
    presence-implies-state oracle.
    """
    result = validate_section_write("## Dev Agent Record")
    assert result.accepted is True
    assert result.marker is None
    assert result.suggestion is None
    assert result.section_name == "## Dev Agent Record"
    assert result.reason == "section in v1 allowlist"


def test_accepted_senior_developer_review_ai() -> None:
    result = validate_section_write("## Senior Developer Review (AI)")
    assert result.accepted is True
    assert result.marker is None
    assert result.suggestion is None
    assert result.section_name == "## Senior Developer Review (AI)"


def test_accepted_review_findings() -> None:
    result = validate_section_write("## Review Findings")
    assert result.accepted is True
    assert result.marker is None
    assert result.suggestion is None
    assert result.section_name == "## Review Findings"


def test_accepted_qa_behavioral_plan() -> None:
    """``## QA Behavioral Plan`` is the upstream-proposal addition (FR23 + epics.md line 1832)."""
    result = validate_section_write("## QA Behavioral Plan")
    assert result.accepted is True
    assert result.marker is None
    assert result.suggestion is None
    assert result.section_name == "## QA Behavioral Plan"


def test_accepted_review_follow_ups_ai() -> None:
    """``## Review Follow-ups (AI)`` is the post-retry-escalation write (epics.md line 501)."""
    result = validate_section_write("## Review Follow-ups (AI)")
    assert result.accepted is True
    assert result.marker is None
    assert result.suggestion is None
    assert result.section_name == "## Review Follow-ups (AI)"


# ---------------------------------------------------------------------------
# Rejected-section tests (AC-3, AC-4, AC-8)
# ---------------------------------------------------------------------------


def test_rejected_arbitrary_section() -> None:
    """An arbitrary unallowed name is rejected with the marker.

    Suggestion may or may not clear the cutoff for an unrelated name.
    """
    result = validate_section_write("## Some Random Section")
    assert result.accepted is False
    assert result.marker == "undocumented-section-write"
    assert result.reason == "section not in v1 allowlist"
    assert result.suggestion is None or result.suggestion in ALLOWED_SECTIONS


def test_rejected_near_miss_qa_plan() -> None:
    """The deliberate-strict-equality + informational-suggestion split (AC-4).

    A specialist that mis-spells ``## QA Behavioral Plan`` as ``## QA
    Plan`` gets a rejection with suggestion ``"## QA Behavioral Plan"`` —
    actionable. The contract is hard (strict equality fails); the
    suggestion is a UX affordance, never a fallback match.
    """
    result = validate_section_write("## QA Plan")
    assert result.accepted is False
    assert result.marker == "undocumented-section-write"
    assert result.suggestion == "## QA Behavioral Plan"


def test_rejected_case_difference() -> None:
    """Lowercased variant is rejected (case-sensitive comparison).

    Documents the contract: the v1 allowlist uses Title Case for section
    words verbatim; lowercased variants are NOT accepted.
    """
    result = validate_section_write("## dev agent record")
    assert result.accepted is False
    assert result.marker == "undocumented-section-write"
    assert result.suggestion == "## Dev Agent Record"


def test_rejected_trailing_whitespace() -> None:
    """Trailing whitespace is rejected (whitespace-significant). No normalization."""
    result = validate_section_write("## Dev Agent Record ")
    assert result.accepted is False
    assert result.marker == "undocumented-section-write"
    assert result.suggestion == "## Dev Agent Record"


def test_rejected_leading_whitespace() -> None:
    """Leading whitespace is rejected. No normalization."""
    result = validate_section_write("  ## Dev Agent Record")
    assert result.accepted is False
    assert result.marker == "undocumented-section-write"
    assert result.suggestion == "## Dev Agent Record"


def test_rejected_missing_prefix() -> None:
    """Missing ``## `` prefix is rejected (the prefix is part of section identity).

    The suggestion is deterministically ``"## Dev Agent Record"``:
    ``difflib.SequenceMatcher`` ratio for ``"Dev Agent Record"`` vs
    ``"## Dev Agent Record"`` is ~0.91, well above the 0.6 cutoff, so the
    ``None`` arm is unreachable.
    """
    result = validate_section_write("Dev Agent Record")
    assert result.accepted is False
    assert result.marker == "undocumented-section-write"
    assert result.suggestion == "## Dev Agent Record"


def test_rejected_empty_string() -> None:
    """Empty string is rejected; no candidate clears the cutoff."""
    result = validate_section_write("")
    assert result.accepted is False
    assert result.marker == "undocumented-section-write"
    assert result.suggestion is None


def test_rejected_whitespace_only() -> None:
    """Whitespace-only string is rejected; no candidate clears the cutoff."""
    result = validate_section_write("   ")
    assert result.accepted is False
    assert result.marker == "undocumented-section-write"
    assert result.suggestion is None


def test_rejected_no_close_match() -> None:
    """Unrelated input — the cutoff suppresses suggestions."""
    result = validate_section_write("## Completely Unrelated Topic")
    assert result.accepted is False
    assert result.marker == "undocumented-section-write"
    assert result.suggestion is None


# ---------------------------------------------------------------------------
# Type-validation tests (AC-3, AC-8)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_input",
    [
        None,
        42,
        ["## Dev Agent Record"],
        b"## Dev Agent Record",
    ],
)
def test_validate_section_write_rejects_non_string_input(bad_input: Any) -> None:
    """Non-string inputs raise ``TypeError`` with offending-type-named message."""
    with pytest.raises(TypeError) as exc_info:
        validate_section_write(bad_input)  # type: ignore[arg-type]
    assert "section_name must be str" in str(exc_info.value)
    assert type(bad_input).__name__ in str(exc_info.value)


@pytest.mark.parametrize(
    "bad_input",
    [None, 42, ["## Dev Agent Record"], b"## Dev Agent Record"],
)
def test_is_allowed_rejects_non_string_input(bad_input: Any) -> None:
    """``is_allowed`` defensive runtime check parallel to ``validate_section_write``."""
    with pytest.raises(TypeError) as exc_info:
        is_allowed(bad_input)  # type: ignore[arg-type]
    assert "section_name must be str" in str(exc_info.value)


@pytest.mark.parametrize(
    "bad_input",
    [None, 42, ["## Dev Agent Record"], b"## Dev Agent Record"],
)
def test_closest_allowlisted_rejects_non_string_input(bad_input: Any) -> None:
    """``closest_allowlisted`` defensive runtime check parallel to ``validate_section_write``."""
    with pytest.raises(TypeError) as exc_info:
        closest_allowlisted(bad_input)  # type: ignore[arg-type]
    assert "section_name must be str" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Convenience-helper tests (AC-3, AC-4, AC-8)
# ---------------------------------------------------------------------------


def test_is_allowed_returns_bool() -> None:
    """``is_allowed`` is a thin wrapper returning the boolean answer."""
    assert is_allowed("## Dev Agent Record") is True
    assert is_allowed("## Bogus") is False
    # Sanity: it should NOT instantiate ValidationResult.
    assert isinstance(is_allowed("## Dev Agent Record"), bool)


def test_closest_allowlisted_with_n_2() -> None:
    """``closest_allowlisted`` is callable with custom ``n`` and ``cutoff``.

    First element is the top match; the helper is exposed so Epic 2+
    consumers that want multiple candidates can call it with their own
    parameters.
    """
    candidates = closest_allowlisted("## QA Plan", n=2, cutoff=0.5)
    assert candidates  # Non-empty
    assert candidates[0] == "## QA Behavioral Plan"
    # All returned candidates must come from ALLOWED_SECTIONS.
    for c in candidates:
        assert c in ALLOWED_SECTIONS


def test_closest_allowlisted_returns_empty_for_unrelated() -> None:
    """For genuinely-unrelated input the helper returns ``[]`` (NOT ``None``)."""
    assert closest_allowlisted("XYZ123", n=1, cutoff=0.6) == []


# ---------------------------------------------------------------------------
# Marker-class taxonomy seam (AC-5)
# ---------------------------------------------------------------------------


def test_undocumented_section_write_class_in_taxonomy() -> None:
    """The ``undocumented-section-write`` marker class lives in marker-taxonomy.yaml.

    Story 1.10b consumes the marker-class IDENTIFIER as a string;
    ``schemas/marker-taxonomy.yaml`` (line 151 at this story's landing
    time, added in story 1.4 per the FR-named-class proactive-add
    discipline) IS the authoritative declaration. This test is the
    inverse-direction validation of story 1.5's ``enumeration_check``
    and prevents drift if a future PR accidentally removes or renames
    the class. Loud-fails with a clear "story 1.10b's contract is
    broken at the cross-schema seam" message if the entry is missing.
    """
    repo_root = find_repo_root()
    taxonomy_path = repo_root / "schemas" / "marker-taxonomy.yaml"
    raw = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict), (
        f"marker-taxonomy.yaml did not parse to a YAML mapping at top level "
        f"(loud-fail seam: story 1.10b's contract is broken at the cross-"
        f"schema seam at {taxonomy_path})"
    )
    markers = raw.get("markers")
    assert isinstance(markers, list), (
        "marker-taxonomy.yaml has no top-level `markers:` list "
        "(loud-fail seam: story 1.10b's contract is broken at the cross-"
        "schema seam — `markers` key missing or non-list)"
    )
    classes = {entry.get("marker_class") for entry in markers if isinstance(entry, dict)}
    assert "undocumented-section-write" in classes, (
        "the `undocumented-section-write` class is no longer in "
        "marker-taxonomy.yaml; story 1.10b's contract is broken at the "
        "cross-schema seam — story 1.10b consumes the identifier as a "
        "string and depends on the YAML declaration being authoritative"
    )


# ---------------------------------------------------------------------------
# Allowlist constant shape (AC-2)
# ---------------------------------------------------------------------------


def test_allowed_sections_is_tuple_of_strings() -> None:
    """``ALLOWED_SECTIONS`` is a frozen ``tuple`` of strings with length 5."""
    assert isinstance(ALLOWED_SECTIONS, tuple)
    assert all(isinstance(s, str) for s in ALLOWED_SECTIONS)
    assert len(ALLOWED_SECTIONS) == 5


def test_allowed_sections_canonical_order() -> None:
    """Canonical PRD-line-901 order — load-bearing per AC-2.

    Dev Agent Record first (chronologically-first specialist write per
    ADR-005's section-presence-implies-state oracle); QA Behavioral Plan
    fourth (upstream-proposal addition); Review Follow-ups last (post-
    retry-escalation write per epics.md line 501).
    """
    assert ALLOWED_SECTIONS == (
        "## Dev Agent Record",
        "## Senior Developer Review (AI)",
        "## Review Findings",
        "## QA Behavioral Plan",
        "## Review Follow-ups (AI)",
    )


def test_module_all_exports() -> None:
    """``__all__`` exports the public API surface per AC-2."""
    from loud_fail_harness import story_doc_validator

    assert hasattr(story_doc_validator, "__all__")
    expected = {
        "ALLOWED_SECTIONS",
        "ValidationResult",
        "validate_section_write",
        "is_allowed",
        "closest_allowlisted",
    }
    assert expected.issubset(set(story_doc_validator.__all__))


# ---------------------------------------------------------------------------
# Determinism + serialization (AC-6, AC-8)
# ---------------------------------------------------------------------------


def test_determinism_repeated_invocation() -> None:
    """Two invocations on the same rejected input produce byte-identical JSON.

    Parallel to 1.4 / 1.5 / 1.6 / 1.7 / 1.8 / 1.9 / 1.10a determinism
    discipline.
    """
    result1 = validate_section_write("## QA Plan")
    result2 = validate_section_write("## QA Plan")
    assert result1.model_dump_json() == result2.model_dump_json()


def test_validation_result_json_serialization_stable() -> None:
    """``model_dump_json()`` is byte-identical across two invocations.

    Field-declaration order is load-bearing for byte-stable serialization.
    """
    result = validate_section_write("## Dev Agent Record")
    first = result.model_dump_json()
    second = result.model_dump_json()
    assert first == second
    # Sanity-check field order in the serialized form (load-bearing for
    # determinism + the AC-6 field-declaration-order discipline).
    accepted_idx = first.index('"accepted"')
    section_idx = first.index('"section_name"')
    marker_idx = first.index('"marker"')
    reason_idx = first.index('"reason"')
    suggestion_idx = first.index('"suggestion"')
    assert accepted_idx < section_idx < marker_idx < reason_idx < suggestion_idx


# ---------------------------------------------------------------------------
# Pydantic v2 frozen-model discipline (AC-6, AC-8)
# ---------------------------------------------------------------------------


def test_validation_result_is_frozen_and_hashable() -> None:
    """``ValidationResult`` is frozen (assignment raises) AND hashable (no list fields).

    Tests both the ``accepted=True`` path (marker=None, suggestion=None) and
    the ``accepted=False`` path (marker="undocumented-section-write",
    suggestion non-None) to cover the full field-combination space.
    """
    accepted_result = ValidationResult(
        accepted=True,
        section_name="## Dev Agent Record",
        marker=None,
        reason="section in v1 allowlist",
        suggestion=None,
    )
    with pytest.raises(ValidationError):
        accepted_result.accepted = False  # type: ignore[misc]
    # Accepted path: hashable + equal to identical instance.
    assert hash(accepted_result) == hash(
        ValidationResult(
            accepted=True,
            section_name="## Dev Agent Record",
            marker=None,
            reason="section in v1 allowlist",
            suggestion=None,
        )
    )
    assert len({accepted_result, accepted_result}) == 1

    # Rejected path: non-None marker + non-None suggestion are also hashable.
    rejected_result = ValidationResult(
        accepted=False,
        section_name="## QA Plan",
        marker="undocumented-section-write",
        reason="section not in v1 allowlist",
        suggestion="## QA Behavioral Plan",
    )
    assert hash(rejected_result) == hash(
        ValidationResult(
            accepted=False,
            section_name="## QA Plan",
            marker="undocumented-section-write",
            reason="section not in v1 allowlist",
            suggestion="## QA Behavioral Plan",
        )
    )
    assert len({rejected_result, rejected_result}) == 1
    # Accepted and rejected results are distinct in a set.
    assert len({accepted_result, rejected_result}) == 2


# ---------------------------------------------------------------------------
# CLI / main exit-code matrix (AC-7, AC-8)
# ---------------------------------------------------------------------------


def test_main_help_resolves(capsys: pytest.CaptureFixture[str]) -> None:
    """``main(['--help'])`` raises ``SystemExit(0)`` and prints expected help text."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    # AC-8 row "main --help" requires the help text mentions ``section_name``.
    assert "section_name" in captured.out


def test_main_accepts_allowlisted_section() -> None:
    """``main(['## Dev Agent Record'])`` returns 0; stdout contains accepted=true JSON."""
    rc, out, err = _capture_main(["## Dev Agent Record"])
    assert rc == 0
    assert err == ""
    parsed = json.loads(out)
    assert parsed["accepted"] is True
    assert parsed["section_name"] == "## Dev Agent Record"
    assert parsed["marker"] is None
    assert parsed["suggestion"] is None


def test_main_rejects_unallowed_section() -> None:
    """``main(['## Bogus Section'])`` returns 1; stdout contains the marker."""
    rc, out, err = _capture_main(["## Bogus Section"])
    assert rc == 1
    assert err == ""
    parsed = json.loads(out)
    assert parsed["accepted"] is False
    assert parsed["marker"] == "undocumented-section-write"
    assert parsed["section_name"] == "## Bogus Section"


# ---------------------------------------------------------------------------
# Cross-platform sanity — find_repo_root resolves on this dev machine
# ---------------------------------------------------------------------------


def test_find_repo_root_locates_taxonomy_file() -> None:
    """Sanity: the taxonomy seam-test depends on ``find_repo_root`` resolving.

    Documents that the seam-test infrastructure is not silently broken
    (i.e., a future repo-layout change breaking ``find_repo_root`` would
    surface here distinct from the seam test's `loud-fail` message).
    """
    repo_root = find_repo_root()
    assert isinstance(repo_root, pathlib.Path)
    taxonomy_path = repo_root / "schemas" / "marker-taxonomy.yaml"
    assert taxonomy_path.is_file()


# Suppress unused-import warning in environments where sys is only referenced
# for clarity in the module header.
_ = sys
