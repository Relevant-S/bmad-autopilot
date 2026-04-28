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
    [x] dev-wrapper.md documents the Epic-2 empty-scope invariant      → test_dev_wrapper_documents_epic2_empty_scope_invariant
    [x] dev-wrapper.md has zero cross-specialist references            → test_dev_wrapper_no_cross_specialist_references
    [x] dev-wrapper.md documents bmad-dev-story composition            → test_dev_wrapper_documents_bmad_dev_story_composition
    [x] dev-wrapper.md documents required envelope fields              → test_dev_wrapper_documents_required_envelope_fields

Directory shape (AC-1):
    [x] agents/ contains exactly dev-wrapper.md at top-level           → test_agents_directory_contains_only_dev_wrapper
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
            f"{name} violates Epic-2 invariant: scope_expanded_to must be []"
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


def test_dev_wrapper_documents_epic2_empty_scope_invariant(
    dev_wrapper_text: str,
) -> None:
    text = dev_wrapper_text
    idx = text.find("scope_expanded_to")
    assert idx >= 0, "dev-wrapper.md must mention scope_expanded_to"
    window = text[idx : idx + 200]
    assert re.search(r"[Ee]pic 2", window), (
        "first scope_expanded_to mention must name Epic 2 within 200 chars"
    )
    assert "[]" in window, (
        "first scope_expanded_to mention must show the literal [] within 200 chars"
    )


def test_dev_wrapper_no_cross_specialist_references(dev_wrapper_text: str) -> None:
    forbidden = (
        "agents/review-bmad-wrapper.md",
        "agents/qa.md",
        "agents/lad.md",
        "agents/review-lad.md",
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


def test_agents_directory_contains_only_dev_wrapper(agents_dir: pathlib.Path) -> None:
    assert agents_dir.is_dir(), "agents/ directory must exist"
    md_files = sorted(p.name for p in agents_dir.glob("*.md"))
    assert md_files == ["dev-wrapper.md"], (
        f"agents/ top-level must contain exactly dev-wrapper.md; found {md_files}"
    )
    subdirs = [p for p in agents_dir.iterdir() if p.is_dir()]
    assert subdirs == [], f"agents/ must have no subdirectories; found {subdirs}"


def test_dev_wrapper_has_lf_line_endings(dev_wrapper_bytes: bytes) -> None:
    assert b"\r\n" not in dev_wrapper_bytes, (
        "dev-wrapper.md must use LF line endings (no CRLF)"
    )
    assert b"\r" not in dev_wrapper_bytes, "dev-wrapper.md must use LF line endings"
