"""Contract-coverage matrix for Story 2.8 (minimal Dev-wrapper subagent).

This docstring IS the contract-coverage checklist required by AC-6. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to stories 1.2-1.9 + 2.2-2.7).

Fixture-shape conformance (AC-5, AC-6):
    [x] dev-pass-with-findings.yaml validates against schema           → test_dev_pass_with_findings_fixture_validates_against_schema
    [x] dev-fail-blocked-by-tests.yaml validates against schema        → test_dev_fail_blocked_by_tests_fixture_validates_against_schema
    [x] dev-pass-empty-scope.yaml validates against schema             → test_dev_pass_empty_scope_fixture_validates_against_schema

Cross-fixture invariants (AC-5, AC-6, FR50, FR52, FR54):
    [x] every dev-*.yaml carries non-empty proposed_commit_message     → test_all_dev_fixtures_carry_proposed_commit_message_field
    [x] every dev-*.yaml has scope_expanded_to == [] (Epic-2 invariant)→ test_all_dev_fixtures_have_empty_scope_expanded_to
    [x] no dev-*.yaml carries forbidden flow-policy fields             → test_all_dev_fixtures_have_no_forbidden_flow_policy_fields

Wrapper-prose discipline (AC-2, AC-3, AC-4, AC-6):
    [x] dev-wrapper.md documents the FR11 scope_expanded_to contract   → test_dev_wrapper_documents_scope_expanded_to_contract
        (relaxed from Story 2.8's Epic-2 hardcode by Story 5.3 AC-6 —
        the empty-array invariant is now retry-conditional, not
        era-conditional, per the FR10 / FR11 contract-pair landing)
    [x] dev-wrapper.md has zero cross-specialist references            → test_dev_wrapper_no_cross_specialist_references
    [x] dev-wrapper.md documents bmad-dev-story composition            → test_dev_wrapper_documents_bmad_dev_story_composition
    [x] dev-wrapper.md documents required envelope fields              → test_dev_wrapper_documents_required_envelope_fields
    [x] dev-wrapper.md carries the Story 5.3 fix-only retry-mode       → test_dev_wrapper_documents_fix_only_retry_mode_section
        section (FR10 / FR11)

Directory shape (AC-1):
    [x] agents/ contains dev-wrapper.md at top-level (one of two       → test_agents_directory_contains_dev_wrapper
        specialist files at this point — relaxed in story 2.9 per
        the deferred review finding)
    [x] dev-wrapper.md uses LF line endings                            → test_dev_wrapper_has_lf_line_endings
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

import pytest
import yaml

from loud_fail_harness.specialist_dispatch import validate_return_envelope


# --------------------------------------------------------------------------- #
# Fixtures (resolution at fixture-time only, never at module import time —    #
# Epic 1 retro Action #1).                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def repo_root() -> pathlib.Path:
    from loud_fail_harness._shared import find_repo_root

    return find_repo_root()


@pytest.fixture(scope="module")
def envelopes_dir(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "examples" / "envelopes"


@pytest.fixture(scope="module")
def agents_dir(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "agents"


@pytest.fixture(scope="module")
def dev_wrapper_path(agents_dir: pathlib.Path) -> pathlib.Path:
    return agents_dir / "dev-wrapper.md"


@pytest.fixture(scope="module")
def dev_wrapper_text(dev_wrapper_path: pathlib.Path) -> str:
    return dev_wrapper_path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dev_wrapper_bytes(dev_wrapper_path: pathlib.Path) -> bytes:
    return dev_wrapper_path.read_bytes()


def _load_envelope(envelopes_dir: pathlib.Path, filename: str) -> dict[str, Any]:
    return yaml.safe_load((envelopes_dir / filename).read_text(encoding="utf-8"))


def _all_dev_envelope_filenames() -> tuple[str, ...]:
    return (
        "dev-pass.yaml",
        "dev-pass-with-findings.yaml",
        "dev-fail-blocked-by-tests.yaml",
        "dev-pass-empty-scope.yaml",
    )


# --------------------------------------------------------------------------- #
# Fixture-shape conformance                                                   #
# --------------------------------------------------------------------------- #


def test_dev_pass_with_findings_fixture_validates_against_schema(
    envelopes_dir: pathlib.Path,
) -> None:
    envelope = _load_envelope(envelopes_dir, "dev-pass-with-findings.yaml")
    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
    assert envelope["proposed_commit_message"]
    assert envelope["scope_expanded_to"] == []
    assert envelope["status"] == "pass"
    assert envelope["findings"], "fixture should carry at least one finding"


def test_dev_fail_blocked_by_tests_fixture_validates_against_schema(
    envelopes_dir: pathlib.Path,
) -> None:
    envelope = _load_envelope(envelopes_dir, "dev-fail-blocked-by-tests.yaml")
    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
    assert envelope["proposed_commit_message"]
    assert envelope["scope_expanded_to"] == []
    assert envelope["status"] == "fail"
    assert any(f["bucket"] == "patch" for f in envelope["findings"])


def test_dev_pass_empty_scope_fixture_validates_against_schema(
    envelopes_dir: pathlib.Path,
) -> None:
    envelope = _load_envelope(envelopes_dir, "dev-pass-empty-scope.yaml")
    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
    assert envelope["proposed_commit_message"]
    assert envelope["scope_expanded_to"] == []
    assert envelope["status"] == "pass"
    assert envelope["artifacts"] == []
    assert envelope["findings"] == []


# --------------------------------------------------------------------------- #
# Cross-fixture invariants                                                    #
# --------------------------------------------------------------------------- #


def test_all_dev_fixtures_carry_proposed_commit_message_field(
    envelopes_dir: pathlib.Path,
) -> None:
    for name in _all_dev_envelope_filenames():
        envelope = _load_envelope(envelopes_dir, name)
        msg = envelope.get("proposed_commit_message")
        assert isinstance(msg, str) and msg.strip(), (
            f"{name} missing or empty proposed_commit_message"
        )


def test_all_dev_fixtures_have_empty_scope_expanded_to(
    envelopes_dir: pathlib.Path,
) -> None:
    for name in _all_dev_envelope_filenames():
        envelope = _load_envelope(envelopes_dir, name)
        assert envelope.get("scope_expanded_to") == [], (
            f"{name} violates first-dispatch invariant: "
            f"scope_expanded_to must be [] on non-retry dispatch "
            f"(Story 5.3 relaxed the Epic-2 unconditional hardcode to "
            f"retry-conditional; first-dispatch fixtures must still use [])"
        )


def test_all_dev_fixtures_have_no_forbidden_flow_policy_fields(
    envelopes_dir: pathlib.Path,
) -> None:
    for name in _all_dev_envelope_filenames():
        envelope = _load_envelope(envelopes_dir, name)
        assert "next_action" not in envelope, f"{name} carries forbidden next_action"
        assert "recommendation" not in envelope, (
            f"{name} carries forbidden recommendation"
        )


# --------------------------------------------------------------------------- #
# Wrapper-prose discipline                                                    #
# --------------------------------------------------------------------------- #


def test_dev_wrapper_documents_scope_expanded_to_contract(
    dev_wrapper_text: str,
) -> None:
    """Post-Story-5.3 contract: the FR54 ``scope_expanded_to`` prose
    names the FR11 contract anchor + the orchestrator-side
    ``affected_files`` scope lock + the literal ``[]`` empty-array
    posture for the no-expansion case. The Epic-2 hardcode prose was
    relaxed by Story 5.3 AC-6 (the empty-array invariant is now
    retry-conditional, not era-conditional)."""
    text = dev_wrapper_text
    idx = text.find("scope_expanded_to")
    assert idx >= 0, "dev-wrapper.md must mention scope_expanded_to"
    # Post-5.3: the first scope_expanded_to mention names FR11 and the
    # affected_files scope lock; check both substrings within the
    # first 400 chars (the prose is longer post-5.3).
    window = text[idx : idx + 400]
    assert "FR11" in window, (
        "first scope_expanded_to mention must name FR11 within 400 chars"
    )
    assert "affected_files" in window, (
        "first scope_expanded_to mention must name affected_files within 400 chars"
    )
    assert "[]" in window, (
        "first scope_expanded_to mention must show the literal [] within 400 chars"
    )


def test_dev_wrapper_documents_fix_only_retry_mode_section(
    dev_wrapper_text: str,
) -> None:
    """Post-Story-5.3 AC-6 contract: dev-wrapper.md carries a
    ``## Fix-only retry mode (FR10 / FR11)`` section naming the
    capability-level constraint, the reporting contract, and the
    Story 5.4 forward-pointer for the verifier."""
    text = dev_wrapper_text
    assert "## Fix-only retry mode (FR10 / FR11)" in text
    assert re.search(
        r"# Retry directive \(fix-only mode .* Story 5\.3\)", text
    ), "section must reference the rendered prompt-body header verbatim"
    assert "Constrain your work" in text
    assert "Story 5.4" in text


def test_dev_wrapper_no_cross_specialist_references(dev_wrapper_text: str) -> None:
    forbidden = (
        "agents/review-bmad-wrapper.md",
        "agents/qa.md",
        "agents/lad.md",
        "agents/review-lad-wrapper.md",
    )
    # AC-4: zero substring matches anywhere in the file. The wrapper's
    # FR62 prohibition prose names sibling specialists by human-readable
    # form (Review-BMAD wrapper, QA, Review-LAD), not by `agents/<slug>.md`
    # path-form, so the pluggability_gate's Rule 1 regex cannot fire on
    # this wrapper once sibling specialists land in stories 2.9 / 2.10.
    for name in forbidden:
        assert name not in dev_wrapper_text, (
            f"dev-wrapper.md must not reference {name} (FR62 zero-substring-match)"
        )
    # And bmad-dev-story is allowed (positive assertion).
    assert "bmad-dev-story" in dev_wrapper_text


def test_dev_wrapper_documents_bmad_dev_story_composition(
    dev_wrapper_text: str,
) -> None:
    assert dev_wrapper_text.count("bmad-dev-story") >= 2, (
        "dev-wrapper.md must document bmad-dev-story composition (Role + Procedure)"
    )


def test_dev_wrapper_documents_required_envelope_fields(
    dev_wrapper_text: str,
) -> None:
    for field in (
        "status",
        "artifacts",
        "findings",
        "rationale",
        "proposed_commit_message",
        "scope_expanded_to",
    ):
        assert field in dev_wrapper_text, (
            f"dev-wrapper.md must document the {field} envelope field"
        )


# --------------------------------------------------------------------------- #
# Directory shape                                                             #
# --------------------------------------------------------------------------- #


def test_agents_directory_contains_dev_wrapper(agents_dir: pathlib.Path) -> None:
    assert agents_dir.is_dir(), "agents/ directory must exist"
    md_files = sorted(p.name for p in agents_dir.glob("*.md"))
    assert "dev-wrapper.md" in md_files, (
        f"agents/ top-level must contain dev-wrapper.md; found {md_files}"
    )
    subdirs = [p for p in agents_dir.iterdir() if p.is_dir()]
    assert subdirs == [], f"agents/ must have no subdirectories; found {subdirs}"


def test_dev_wrapper_has_lf_line_endings(dev_wrapper_bytes: bytes) -> None:
    assert b"\r\n" not in dev_wrapper_bytes, (
        "dev-wrapper.md must use LF line endings (no CRLF)"
    )
    assert b"\r" not in dev_wrapper_bytes, "dev-wrapper.md must use LF line endings"
