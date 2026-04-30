"""Contract-coverage matrix for the Story 3.5 rationale-validation artifact.

This docstring IS the contract-coverage checklist required by Story 3.5 AC-6.
Reviewers verify every row maps to at least one passing test in this module.
The matrix is review-enforced, NOT CI-enforced (parallel to stories 1.2-1.9 +
2.2-2.8 + 2.9 + 3.1-3.4 discipline tests).

Structural-guard invariants (Story 3.5 AC-6 items 1-9):
    [x] artifact exists at canonical path                                → test_rationale_validation_artifact_exists_at_canonical_path
    [x] verbatim clause (a) substring present                            → test_rationale_validation_artifact_contains_verbatim_clause_a_substring
    [x] verbatim clause (b) substring present                            → test_rationale_validation_artifact_contains_verbatim_clause_b_substring
    [x] canonical machine-readable verdict line present + unique         → test_rationale_validation_artifact_contains_canonical_verdict_line
    [x] artifact references source rationale at docs/architecture.md    → test_rationale_validation_artifact_references_source_rationale
    [x] artifact names rationale → validation → written artifact pattern → test_rationale_validation_artifact_names_pattern_for_future_epics
    [x] extension-audit.md contains "Rationale Validations" heading +    → test_extension_audit_md_contains_rationale_validations_section
        pointer to artifact path
    [x] extension-audit.md pointer entry names a canonical verdict token → test_extension_audit_md_pointer_entry_names_verdict
    [x] artifact uses LF-only line endings                               → test_rationale_validation_artifact_has_lf_line_endings

The test does NOT prejudge the dev's verdict — items #4 + #8 accept ANY of the
three canonical tokens `{rationale-holds, rationale-invalidated, partial}` as
valid. The structural guard is against drift (artifact deletion, verdict-token
typo, broken pointer), NOT against any particular substantive judgment.
"""

from __future__ import annotations

import pathlib
import re

import pytest


# --------------------------------------------------------------------------- #
# Fixtures (resolution at fixture-time only, never at module import time —    #
# Epic 1 retro Action #1).                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def repo_root() -> pathlib.Path:
    from loud_fail_harness._shared import find_repo_root

    return find_repo_root()


@pytest.fixture(scope="module")
def artifact_path(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "docs" / "rationale-validations" / "2.9-acceptance-auditor.md"


@pytest.fixture(scope="module")
def artifact_text(artifact_path: pathlib.Path) -> str:
    return artifact_path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def artifact_bytes(artifact_path: pathlib.Path) -> bytes:
    return artifact_path.read_bytes()


@pytest.fixture(scope="module")
def extension_audit_path(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "docs" / "extension-audit.md"


@pytest.fixture(scope="module")
def extension_audit_text(extension_audit_path: pathlib.Path) -> str:
    return extension_audit_path.read_text(encoding="utf-8")


# Canonical clause verbatim slices from `docs/architecture.md` lines 1453 + 1455.
# Each slice is >60 chars and <100 chars and is sufficiently distinctive that a
# paraphrase or rewrite would not match the literal substring.
_CLAUSE_A_VERBATIM_SLICE = (
    "The Acceptance Auditor's findings are most directly "
    "traceable to story acceptance criteria."
)
_CLAUSE_B_VERBATIM_SLICE = (
    "The Acceptance Auditor's output shape is closest to "
    "the eventual three-layer aggregated output."
)

# Canonical machine-readable verdict-line shape per Story 3.5 AC-5 + AC-6 item 4.
_CANONICAL_VERDICT_LINE_REGEX = re.compile(
    r"^\*\*Verdict: (rationale-holds|rationale-invalidated|partial)\*\*$",
    re.MULTILINE,
)

# Canonical pattern-citation proxies per Story 3.5 AC-6 item 6 (any of the three
# substrings is acceptable; the test accepts ANY proxy).
_PATTERN_CITATION_PROXIES = (
    "rationale → validation → written artifact",
    "rationale-validation pattern",
    "epics.md lines 1774-1776",
)

# Canonical verdict-token enum per Story 3.5 AC-5 + AC-6 item 8 (extension-audit
# pointer-entry verdict-token-presence invariant).
_CANONICAL_VERDICT_TOKENS = ("rationale-holds", "rationale-invalidated", "partial")


# --------------------------------------------------------------------------- #
# Test 1 — artifact exists at canonical path (AC-6 item 1).                   #
# --------------------------------------------------------------------------- #


def test_rationale_validation_artifact_exists_at_canonical_path(
    artifact_path: pathlib.Path,
) -> None:
    assert artifact_path.is_file(), (
        f"rationale-validation artifact must exist at canonical path "
        f"docs/rationale-validations/2.9-acceptance-auditor.md (epics.md "
        f"line 1762); not found at {artifact_path}"
    )


# --------------------------------------------------------------------------- #
# Tests 2 + 3 — verbatim clause substrings (AC-6 items 2 + 3).                #
# --------------------------------------------------------------------------- #


def test_rationale_validation_artifact_contains_verbatim_clause_a_substring(
    artifact_text: str,
) -> None:
    assert _CLAUSE_A_VERBATIM_SLICE in artifact_text, (
        "rationale-validation artifact must reproduce clause (a) WORD-FOR-WORD "
        "from docs/architecture.md line 1453; verbatim slice "
        f"{_CLAUSE_A_VERBATIM_SLICE!r} not found in artifact text"
    )


def test_rationale_validation_artifact_contains_verbatim_clause_b_substring(
    artifact_text: str,
) -> None:
    assert _CLAUSE_B_VERBATIM_SLICE in artifact_text, (
        "rationale-validation artifact must reproduce clause (b) WORD-FOR-WORD "
        "from docs/architecture.md line 1455; verbatim slice "
        f"{_CLAUSE_B_VERBATIM_SLICE!r} not found in artifact text"
    )


# --------------------------------------------------------------------------- #
# Test 4 — canonical verdict line present + unique (AC-6 item 4).             #
# --------------------------------------------------------------------------- #


def test_rationale_validation_artifact_contains_canonical_verdict_line(
    artifact_text: str,
) -> None:
    matches = _CANONICAL_VERDICT_LINE_REGEX.findall(artifact_text)
    assert len(matches) == 1, (
        "rationale-validation artifact must contain EXACTLY ONE canonical "
        "machine-readable verdict line of shape `**Verdict: <token>**` where "
        "<token> in {rationale-holds, rationale-invalidated, partial}; found "
        f"{len(matches)} matches: {matches}"
    )


# --------------------------------------------------------------------------- #
# Test 5 — source-rationale pointer (AC-6 item 5).                            #
# --------------------------------------------------------------------------- #


def test_rationale_validation_artifact_references_source_rationale(
    artifact_text: str,
) -> None:
    assert "docs/architecture.md" in artifact_text, (
        "rationale-validation artifact must contain a pointer/reference to "
        "docs/architecture.md (the source rationale at lines 1445-1463); the "
        "literal substring 'docs/architecture.md' was not found"
    )


# --------------------------------------------------------------------------- #
# Test 6 — pattern citation for future epics (AC-6 item 6).                   #
# --------------------------------------------------------------------------- #


def test_rationale_validation_artifact_names_pattern_for_future_epics(
    artifact_text: str,
) -> None:
    matched_proxies = [
        proxy for proxy in _PATTERN_CITATION_PROXIES if proxy in artifact_text
    ]
    assert matched_proxies, (
        "rationale-validation artifact must name Story 3.5's pattern explicitly "
        "as a referenceable shape for future epics per epics.md lines 1774-1776; "
        f"none of the canonical proxies {_PATTERN_CITATION_PROXIES} were found "
        "in the artifact text"
    )


# --------------------------------------------------------------------------- #
# Test 7 — extension-audit Rationale Validations heading + pointer (AC-6     #
# item 7).                                                                    #
# --------------------------------------------------------------------------- #


def test_extension_audit_md_contains_rationale_validations_section(
    extension_audit_text: str,
) -> None:
    assert "Rationale Validations" in extension_audit_text, (
        "docs/extension-audit.md must contain a 'Rationale Validations' "
        "heading (H2 or H3 — dev's-call) per Story 3.5 AC-2; the literal "
        "substring 'Rationale Validations' was not found"
    )
    assert (
        "docs/rationale-validations/2.9-acceptance-auditor.md"
        in extension_audit_text
    ), (
        "docs/extension-audit.md must contain a pointer entry to the rationale-"
        "validation artifact at docs/rationale-validations/2.9-acceptance-"
        "auditor.md per Story 3.5 AC-2; the literal substring "
        "'docs/rationale-validations/2.9-acceptance-auditor.md' was not found"
    )


# --------------------------------------------------------------------------- #
# Test 8 — extension-audit pointer-entry verdict-token presence (AC-6 item 8).#
# --------------------------------------------------------------------------- #


def test_extension_audit_md_pointer_entry_names_verdict(
    extension_audit_text: str,
) -> None:
    matched_tokens = [
        token for token in _CANONICAL_VERDICT_TOKENS if token in extension_audit_text
    ]
    assert matched_tokens, (
        "docs/extension-audit.md must contain at least one canonical verdict "
        f"token from {_CANONICAL_VERDICT_TOKENS} in the per-artifact pointer "
        "entry per Story 3.5 AC-2 + AC-6 item 8; none found"
    )


# --------------------------------------------------------------------------- #
# Test 9 — LF-only line endings (AC-6 item 9; parallel to                     #
# test_dev_wrapper_has_lf_line_endings from Story 2.8 / 2.9).                 #
# --------------------------------------------------------------------------- #


def test_rationale_validation_artifact_has_lf_line_endings(
    artifact_bytes: bytes,
) -> None:
    assert b"\r\n" not in artifact_bytes, (
        "rationale-validation artifact must use LF line endings (no CRLF)"
    )
    assert b"\r" not in artifact_bytes, (
        "rationale-validation artifact must use LF line endings (no CR)"
    )
