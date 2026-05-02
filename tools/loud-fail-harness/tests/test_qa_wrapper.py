"""Contract-coverage matrix for Story 2.10 (minimal QA subagent, AC-1 only).

This docstring IS the contract-coverage checklist required by AC-7. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to stories 1.2-1.9 + 2.2-2.9).

Fixture-shape conformance (AC-7):
    [x] qa-pass-ac1-tier1.yaml validates against schema           → test_qa_pass_ac1_tier1_fixture_validates_against_schema
    [x] qa-fail-ac1-assertion.yaml validates against schema       → test_qa_fail_ac1_assertion_fixture_validates_against_schema

Cross-fixture invariants (AC-4, AC-7, FR52, FR55):
    [x] every qa-*.yaml has ac_results of length exactly 1 (Epic-2)→ test_all_qa_fixtures_have_exactly_one_ac_result_at_epic_2_scope
    [x] no qa-*.yaml carries forbidden flow-policy fields         → test_all_qa_fixtures_have_no_forbidden_flow_policy_fields

Wrapper-prose discipline (AC-2, AC-3, AC-4, AC-5, AC-6, AC-8):
    [x] qa.md names AC-1-only Epic-2 scope + Epic-4 forward-pointer→ test_qa_wrapper_documents_ac1_only_single_scope
    [x] qa.md documents ac_results always-one-entry invariant     → test_qa_wrapper_documents_ac_results_invariant
    [x] qa.md honors FR16 TEA-independence invariant              → test_qa_wrapper_honors_fr16_tea_independence
    [x] qa.md has zero cross-specialist references                → test_qa_wrapper_no_cross_specialist_references
    [x] qa.md documents required envelope fields                  → test_qa_wrapper_documents_required_envelope_fields
    [x] qa.md documents qa-evidence path discipline               → test_qa_wrapper_documents_qa_evidence_path_discipline
    [x] qa.md documents AC-1-only Tier-1-evidence-only rationale  → test_qa_wrapper_documents_ac1_only_rationale

Directory shape (AC-1):
    [x] agents/ contains exactly three specialists                → test_agents_directory_contains_three_specialists
    [x] qa.md uses LF line endings                                → test_qa_wrapper_has_lf_line_endings
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
def qa_wrapper_path(agents_dir: pathlib.Path) -> pathlib.Path:
    return agents_dir / "qa.md"


@pytest.fixture(scope="module")
def qa_wrapper_text(qa_wrapper_path: pathlib.Path) -> str:
    return qa_wrapper_path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def qa_wrapper_bytes(qa_wrapper_path: pathlib.Path) -> bytes:
    return qa_wrapper_path.read_bytes()


def _load_envelope(envelopes_dir: pathlib.Path, filename: str) -> dict[str, Any]:
    return yaml.safe_load((envelopes_dir / filename).read_text(encoding="utf-8"))


def _all_qa_envelope_filenames() -> tuple[str, ...]:
    return (
        "qa-pass-ac1-tier1.yaml",
        "qa-fail-ac1-assertion.yaml",
    )


_QA_EVIDENCE_PATH_FRAGMENT: str = "_bmad-output/qa-evidence/"


# --------------------------------------------------------------------------- #
# Fixture-shape conformance                                                   #
# --------------------------------------------------------------------------- #


def test_qa_pass_ac1_tier1_fixture_validates_against_schema(
    envelopes_dir: pathlib.Path,
) -> None:
    envelope = _load_envelope(envelopes_dir, "qa-pass-ac1-tier1.yaml")
    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
    assert envelope["status"] == "pass"
    assert envelope["findings"] == [], (
        "qa-pass fixture must have empty findings (AC-1 success — no AC violations)"
    )
    ac_results = envelope["ac_results"]
    assert len(ac_results) == 1, (
        "Epic 2 scope: ac_results must contain exactly one entry"
    )
    entry = ac_results[0]
    assert entry["ac_id"] == "AC-1"
    assert entry["status"] == "pass"
    assert entry["assertions"], "≥ 1 mechanical Tier-1 assertion required per FR19"
    assert entry["evidence_refs"], "≥ 1 evidence reference required per FR19"
    assert entry["semantic_verification"] == "not_applicable", (
        "Epic 2 scope: semantic_verification is the literal string 'not_applicable'"
    )
    # Story 4.8: evidence_refs items are now {path, tier} objects per the
    # bumped $defs/evidence_ref shape; the path-under-qa-evidence invariant
    # checks the `path` key.
    assert _QA_EVIDENCE_PATH_FRAGMENT in entry["evidence_refs"][0]["path"], (
        "evidence_refs must point under the canonical _bmad-output/qa-evidence/ path per FR49"
    )


def test_qa_fail_ac1_assertion_fixture_validates_against_schema(
    envelopes_dir: pathlib.Path,
) -> None:
    envelope = _load_envelope(envelopes_dir, "qa-fail-ac1-assertion.yaml")
    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
    assert envelope["status"] == "fail", (
        "AC failure uses status=fail (the assertion ran but did not hold); "
        "structural failure (env setup) would use status=blocked"
    )
    assert envelope["findings"], "qa-fail fixture must surface the failed assertion"
    for finding in envelope["findings"]:
        assert finding["source"] == "qa", (
            "QA findings must use source: qa per envelope.schema.yaml line 117"
        )
        assert finding["bucket"] == "decision_needed", (
            "Per FR24a verification-fail uses bucket=decision_needed (NOT patch)"
        )
        assert finding["severity"] == "HIGH", (
            "AC-1 failure is HIGH severity per FR22b smoke-AC criticality"
        )
    ac_results = envelope["ac_results"]
    assert len(ac_results) == 1, "Epic 2 scope: ac_results length is exactly 1"
    entry = ac_results[0]
    assert entry["ac_id"] == "AC-1"
    assert entry["status"] == "fail"
    assert entry["assertions"]
    assert entry["evidence_refs"]
    assert entry["semantic_verification"] == "not_applicable"
    # Story 4.8: evidence_refs items are now {path, tier} objects.
    assert _QA_EVIDENCE_PATH_FRAGMENT in entry["evidence_refs"][0]["path"]


# --------------------------------------------------------------------------- #
# Cross-fixture invariants                                                    #
# --------------------------------------------------------------------------- #


def test_all_qa_fixtures_have_exactly_one_ac_result_at_epic_2_scope(
    envelopes_dir: pathlib.Path,
) -> None:
    for name in _all_qa_envelope_filenames():
        envelope = _load_envelope(envelopes_dir, name)
        ac_results = envelope.get("ac_results")
        assert isinstance(ac_results, list), (
            f"{name} must declare ac_results as an array"
        )
        assert len(ac_results) == 1, (
            f"{name} violates Epic-2 invariant: ac_results length must be exactly 1; "
            f"got {len(ac_results)}"
        )
        entry = ac_results[0]
        assert entry["ac_id"] == "AC-1", (
            f"{name} ac_results[0].ac_id must be 'AC-1' at Epic-2 scope"
        )
        assert entry["semantic_verification"] == "not_applicable", (
            f"{name} ac_results[0].semantic_verification must be the literal "
            "string 'not_applicable' at Epic-2 scope"
        )


def test_all_qa_fixtures_have_no_forbidden_flow_policy_fields(
    envelopes_dir: pathlib.Path,
) -> None:
    for name in _all_qa_envelope_filenames():
        envelope = _load_envelope(envelopes_dir, name)
        assert "next_action" not in envelope, f"{name} carries forbidden next_action"
        assert "recommendation" not in envelope, (
            f"{name} carries forbidden recommendation"
        )


# --------------------------------------------------------------------------- #
# Wrapper-prose discipline                                                    #
# --------------------------------------------------------------------------- #


def test_qa_wrapper_documents_ac1_only_single_scope(qa_wrapper_text: str) -> None:
    text = qa_wrapper_text
    idx = text.find("AC-1")
    assert idx >= 0, "qa.md must mention AC-1"
    # AC-3 (b): Epic 2 within 200 chars of first AC-1 mention.
    window_200 = text[idx : idx + 200]
    assert re.search(r"[Ee]pic 2", window_200), (
        "first AC-1 mention must name Epic 2 within 200 chars"
    )
    # AC-3 (c): Epic 4 within 600 chars of first AC-1 mention (forward pointer).
    window_600 = text[idx : idx + 600]
    assert "Epic 4" in window_600, (
        "first AC-1 mention must name Epic 4 within 600 chars (forward pointer)"
    )


def test_qa_wrapper_documents_ac_results_invariant(qa_wrapper_text: str) -> None:
    text = qa_wrapper_text
    idx = text.find("ac_results")
    assert idx >= 0, "qa.md must mention ac_results"
    # AC-4 (b): AC-1 within 200 chars of first ac_results mention.
    window_200 = text[idx : idx + 200]
    assert "AC-1" in window_200, (
        "first ac_results mention must name AC-1 within 200 chars"
    )
    # AC-4 (c): not_applicable within 400 chars of first ac_results mention.
    window_400 = text[idx : idx + 400]
    assert "not_applicable" in window_400, (
        "first ac_results mention must name not_applicable within 400 chars"
    )


def test_qa_wrapper_honors_fr16_tea_independence(qa_wrapper_text: str) -> None:
    # AC-5: FR16 invariant explicitly named.
    assert "FR16" in qa_wrapper_text, (
        "qa.md must explicitly name FR16 (QA-independence-from-TEA-artifacts invariant)"
    )
    # AC-5: structural encoding via tea_artifacts_consumed.
    assert "tea_artifacts_consumed" in qa_wrapper_text, (
        "qa.md must name tea_artifacts_consumed (the structural encoding of FR16)"
    )
    # AC-5: FR16 prose mentions TEA (e.g., "TEA test files", "TEA artifacts").
    # Case-sensitive — TEA module name is consistently uppercase.
    assert "TEA" in qa_wrapper_text, (
        "qa.md must mention TEA at least once (FR16 prose context)"
    )


def test_qa_wrapper_no_cross_specialist_references(qa_wrapper_text: str) -> None:
    # AC-6 (path-form): zero substring matches for any sibling specialist agent
    # file by path. The wrapper's FR62 prohibition prose names sibling
    # specialists by human-readable form ("the Dev specialist", "the
    # Review-BMAD specialist", "the Phase-1.5 LAD layer"), not by literal
    # `agents/<slug>.md` path-form, so the pluggability_gate's Rule 1 regex
    # cannot fire on this wrapper.
    forbidden_paths = (
        "agents/dev-wrapper.md",
        "agents/review-bmad-wrapper.md",
        "agents/lad.md",
        "agents/review-lad.md",
    )
    for name in forbidden_paths:
        assert name not in qa_wrapper_text, (
            f"qa.md must not reference {name} (FR62 zero-substring-match)"
        )
    # AC-6 (slug-form): zero word-bounded matches for any sibling specialist
    # slug. Single-word slugs (`lad`) are checked too (AC-6 enumerates them
    # explicitly even though pluggability_gate's Rule 2 deliberately
    # excludes single-word slugs from runtime scanning).
    forbidden_slugs = (
        "dev-wrapper",
        "review-bmad-wrapper",
        "lad",
        "review-lad",
    )
    for slug in forbidden_slugs:
        assert not re.search(r"\b" + re.escape(slug) + r"\b", qa_wrapper_text), (
            f"qa.md must not reference slug {slug!r} (FR62 word-boundary check)"
        )


def test_qa_wrapper_documents_required_envelope_fields(qa_wrapper_text: str) -> None:
    # AC-2: documented contract sections include all envelope fields plus
    # the QA-specific extension.
    for field in (
        "status",
        "artifacts",
        "findings",
        "rationale",
        "ac_results",
    ):
        assert field in qa_wrapper_text, (
            f"qa.md must document the {field} envelope field"
        )


def test_qa_wrapper_documents_qa_evidence_path_discipline(
    qa_wrapper_text: str,
) -> None:
    # FR49: evidence persisted at _bmad-output/qa-evidence/{story-id}/{run-id}/
    assert _QA_EVIDENCE_PATH_FRAGMENT in qa_wrapper_text, (
        f"qa.md must document the canonical evidence path "
        f"({_QA_EVIDENCE_PATH_FRAGMENT}) per FR49"
    )


def test_qa_wrapper_documents_ac1_only_rationale(qa_wrapper_text: str) -> None:
    text = qa_wrapper_text
    # AC-8 clause-(c) marker: seam contract / seam-contract phrase.
    assert "seam contract" in text or "seam-contract" in text, (
        "qa.md must document the AC-1-only Tier-1-evidence-only rationale "
        "(clause c: same agent identity, same envelope contract — seam "
        "contracts unchanged) per AC-8"
    )
    # AC-8 clause-(b) marker: Tier-1 evidence (case-insensitive on digit
    # boundary so `Tier-1` and `Tier 1` both qualify).
    assert re.search(r"[Tt]ier[- ]1", text), (
        "qa.md must document the AC-1-only Tier-1-evidence-only rationale "
        "(clause b: Tier-1 evidence keeps the wrapper endogenous) per AC-8"
    )


# --------------------------------------------------------------------------- #
# Directory shape                                                             #
# --------------------------------------------------------------------------- #


def test_agents_directory_contains_three_specialists(
    agents_dir: pathlib.Path,
) -> None:
    assert agents_dir.is_dir(), "agents/ directory must exist"
    md_files = sorted(p.name for p in agents_dir.glob("*.md"))
    assert set(md_files) == {
        "dev-wrapper.md",
        "review-bmad-wrapper.md",
        "qa.md",
    }, (
        "agents/ top-level must contain exactly dev-wrapper.md, "
        f"review-bmad-wrapper.md, and qa.md; found {md_files}"
    )
    subdirs = [p for p in agents_dir.iterdir() if p.is_dir()]
    assert subdirs == [], f"agents/ must have no subdirectories; found {subdirs}"


def test_qa_wrapper_has_lf_line_endings(qa_wrapper_bytes: bytes) -> None:
    assert b"\r\n" not in qa_wrapper_bytes, (
        "qa.md must use LF line endings (no CRLF)"
    )
    assert b"\r" not in qa_wrapper_bytes, "qa.md must use LF line endings"
