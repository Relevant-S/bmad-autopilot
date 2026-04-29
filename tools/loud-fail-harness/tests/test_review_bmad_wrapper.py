"""Contract-coverage matrix for Story 2.9 (minimal Review-BMAD-wrapper subagent).

This docstring IS the contract-coverage checklist required by AC-7. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to stories 1.2-1.9 + 2.2-2.8).

Fixture-shape conformance (AC-6, AC-7):
    [x] review-pass-acceptance-auditor.yaml validates against schema   → test_review_pass_acceptance_auditor_fixture_validates_against_schema
    [x] review-fail-layer-failure.yaml validates against schema        → test_review_fail_layer_failure_fixture_validates_against_schema

Cross-fixture invariants (AC-4, AC-7, FR52, FR56):
    [x] every review-*.yaml has failed_layers field present (list)     → test_all_review_fixtures_have_failed_layers_field_present
    [x] no review-*.yaml carries forbidden flow-policy fields          → test_all_review_fixtures_have_no_forbidden_flow_policy_fields

Wrapper-prose discipline (AC-2, AC-3, AC-4, AC-5, AC-7, AC-8):
    [x] review-bmad-wrapper.md names Acceptance Auditor at Epic 2 scope→ test_review_bmad_wrapper_documents_acceptance_auditor_single_layer_scope
    [x] review-bmad-wrapper.md names failed_layers always-present      → test_review_bmad_wrapper_documents_failed_layers_invariant
    [x] review-bmad-wrapper.md has zero cross-specialist references    → test_review_bmad_wrapper_no_cross_specialist_references
    [x] review-bmad-wrapper.md documents bmad-code-review composition  → test_review_bmad_wrapper_documents_bmad_code_review_composition
    [x] review-bmad-wrapper.md documents required envelope fields      → test_review_bmad_wrapper_documents_required_envelope_fields
    [x] review-bmad-wrapper.md documents Acceptance Auditor rationale  → test_review_bmad_wrapper_documents_acceptance_auditor_rationale

Directory shape (AC-1):
    [x] agents/ contains dev-wrapper.md AND review-bmad-wrapper.md at  → test_agents_directory_contains_dev_wrapper_and_review_bmad_wrapper_at_minimum
        minimum (one of three+ specialist files at this point)
    [x] review-bmad-wrapper.md uses LF line endings                    → test_review_bmad_wrapper_has_lf_line_endings
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
def review_wrapper_path(agents_dir: pathlib.Path) -> pathlib.Path:
    return agents_dir / "review-bmad-wrapper.md"


@pytest.fixture(scope="module")
def review_wrapper_text(review_wrapper_path: pathlib.Path) -> str:
    return review_wrapper_path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def review_wrapper_bytes(review_wrapper_path: pathlib.Path) -> bytes:
    return review_wrapper_path.read_bytes()


def _load_envelope(envelopes_dir: pathlib.Path, filename: str) -> dict[str, Any]:
    return yaml.safe_load((envelopes_dir / filename).read_text(encoding="utf-8"))


def _all_review_envelope_filenames() -> tuple[str, ...]:
    return (
        "review-pass-acceptance-auditor.yaml",
        "review-fail-layer-failure.yaml",
    )


_FAILED_LAYERS_ENUM: frozenset[str] = frozenset({"blind", "edge", "auditor", "lad"})


# --------------------------------------------------------------------------- #
# Fixture-shape conformance                                                   #
# --------------------------------------------------------------------------- #


def test_review_pass_acceptance_auditor_fixture_validates_against_schema(
    envelopes_dir: pathlib.Path,
) -> None:
    envelope = _load_envelope(envelopes_dir, "review-pass-acceptance-auditor.yaml")
    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
    assert envelope["status"] == "pass"
    assert isinstance(envelope["failed_layers"], list)
    assert envelope["failed_layers"] == []
    assert envelope["findings"], "fixture should carry at least one finding"
    for finding in envelope["findings"]:
        assert finding["source"] == "auditor", (
            "Acceptance Auditor findings must use source: auditor per "
            "envelope.schema.yaml line 117"
        )
        assert finding["bucket"] in {"defer", "dismiss"}, (
            "review-pass fixture findings must be defer or dismiss bucket; "
            "patch-bucket findings would route the orchestrator into a Dev "
            "fix-only retry per FR9"
        )


def test_review_fail_layer_failure_fixture_validates_against_schema(
    envelopes_dir: pathlib.Path,
) -> None:
    envelope = _load_envelope(envelopes_dir, "review-fail-layer-failure.yaml")
    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
    assert envelope["status"] == "blocked", (
        "structural layer failure uses status=blocked, not status=fail "
        "(status=fail means the layer ran and reported AC violations)"
    )
    assert envelope["artifacts"] == [], (
        "no review output produced when layer never completed"
    )
    assert envelope["findings"] == [], "no findings when no review happened"
    assert envelope["failed_layers"] == ["auditor"], (
        "graceful-degradation signal per FR28: Acceptance Auditor failed structurally"
    )


# --------------------------------------------------------------------------- #
# Cross-fixture invariants                                                    #
# --------------------------------------------------------------------------- #


def test_all_review_fixtures_have_failed_layers_field_present(
    envelopes_dir: pathlib.Path,
) -> None:
    for name in _all_review_envelope_filenames():
        envelope = _load_envelope(envelopes_dir, name)
        assert "failed_layers" in envelope, (
            f"{name} must declare failed_layers (always present, even when empty)"
        )
        layers = envelope["failed_layers"]
        assert isinstance(layers, list), f"{name} failed_layers must be a list"
        for layer in layers:
            assert layer in _FAILED_LAYERS_ENUM, (
                f"{name} failed_layers item {layer!r} not in schema enum "
                f"{sorted(_FAILED_LAYERS_ENUM)}"
            )


def test_all_review_fixtures_have_no_forbidden_flow_policy_fields(
    envelopes_dir: pathlib.Path,
) -> None:
    for name in _all_review_envelope_filenames():
        envelope = _load_envelope(envelopes_dir, name)
        assert "next_action" not in envelope, f"{name} carries forbidden next_action"
        assert "recommendation" not in envelope, (
            f"{name} carries forbidden recommendation"
        )


# --------------------------------------------------------------------------- #
# Wrapper-prose discipline                                                    #
# --------------------------------------------------------------------------- #


def test_review_bmad_wrapper_documents_acceptance_auditor_single_layer_scope(
    review_wrapper_text: str,
) -> None:
    text = review_wrapper_text
    idx = text.find("Acceptance Auditor")
    assert idx >= 0, "review-bmad-wrapper.md must mention Acceptance Auditor"
    # AC-3 (b): Epic 2 within 200 chars of first Acceptance Auditor mention.
    window_200 = text[idx : idx + 200]
    assert re.search(r"[Ee]pic 2", window_200), (
        "first Acceptance Auditor mention must name Epic 2 within 200 chars"
    )
    # AC-3 (c): Epic 3 or Story 3.1 within 600 chars of first Acceptance Auditor.
    window_600 = text[idx : idx + 600]
    assert re.search(r"Epic 3|Story 3\.1", window_600), (
        "first Acceptance Auditor mention must name Epic 3 or Story 3.1 within 600 chars"
    )


def test_review_bmad_wrapper_documents_failed_layers_invariant(
    review_wrapper_text: str,
) -> None:
    text = review_wrapper_text
    idx = text.find("failed_layers")
    assert idx >= 0, "review-bmad-wrapper.md must mention failed_layers"
    window = text[idx : idx + 400]
    # AC-4 (b): auditor within window.
    assert "auditor" in window, (
        "first failed_layers mention must name auditor within 400 chars"
    )
    # AC-4 (c): the always-present-even-when-empty invariant. Match the
    # bracketed-empty-list literal as a standalone token (not the trailing `]`
    # of an enum like `[blind, edge, auditor, lad]`) OR the literal word
    # "empty". Regex requires a non-`,` non-alphanum char before `[]` so that
    # enum closures cannot satisfy the proximity check coincidentally.
    assert re.search(r"(^|[^A-Za-z0-9,])\[\]", window) or "empty" in window, (
        "first failed_layers mention must show standalone [] or word 'empty' "
        "within 400 chars (bare enum-closing bracket does not count)"
    )


def test_review_bmad_wrapper_no_cross_specialist_references(
    review_wrapper_text: str,
) -> None:
    # AC-5: zero substring matches for any sibling specialist agent file by path.
    # The wrapper's FR62 prohibition prose names sibling specialists by
    # human-readable form (the Dev specialist, the QA specialist, the
    # Phase-1.5 LAD layer), not by literal `agents/<slug>.md` path-form, so
    # the pluggability_gate's Rule 1 regex cannot fire on this wrapper.
    forbidden_paths = (
        "agents/dev-wrapper.md",
        "agents/qa.md",
        "agents/lad.md",
        "agents/review-lad.md",
    )
    for name in forbidden_paths:
        assert name not in review_wrapper_text, (
            f"review-bmad-wrapper.md must not reference {name} "
            "(FR62 zero-substring-match)"
        )
    # AC-5 (slug-form): zero word-bounded matches for the multi-hyphen sibling
    # slugs that would trigger the pluggability gate's Rule 2 regex.
    forbidden_slugs = ("dev-wrapper", "review-lad")
    for slug in forbidden_slugs:
        assert not re.search(r"\b" + re.escape(slug) + r"\b", review_wrapper_text), (
            f"review-bmad-wrapper.md must not reference slug {slug!r} "
            "(FR62 Rule 2 slug-form prohibition)"
        )
    # bmad-code-review is allowed (positive assertion — upstream BMAD-core
    # primitive, NOT a specialist per FR62 enumeration).
    assert "bmad-code-review" in review_wrapper_text


def test_review_bmad_wrapper_documents_bmad_code_review_composition(
    review_wrapper_text: str,
) -> None:
    assert review_wrapper_text.count("bmad-code-review") >= 2, (
        "review-bmad-wrapper.md must document bmad-code-review composition "
        "(Role + Procedure)"
    )


def test_review_bmad_wrapper_documents_required_envelope_fields(
    review_wrapper_text: str,
) -> None:
    for field in (
        "status",
        "artifacts",
        "findings",
        "rationale",
        "failed_layers",
    ):
        assert field in review_wrapper_text, (
            f"review-bmad-wrapper.md must document the {field} envelope field"
        )


def test_review_bmad_wrapper_documents_acceptance_auditor_rationale(
    review_wrapper_text: str,
) -> None:
    text = review_wrapper_text
    # AC-8 clause-(a) marker: traceability to acceptance criteria.
    assert re.search(r"traceab", text), (
        "review-bmad-wrapper.md must document Acceptance Auditor traceability "
        "rationale (clause a) per AC-8"
    )
    # AC-8 clause-(b) marker: seam-contract churn minimization OR aggregated output.
    assert "seam-contract" in text or "aggregated output" in text, (
        "review-bmad-wrapper.md must document Acceptance Auditor "
        "seam-contract / aggregated-output rationale (clause b) per AC-8"
    )


# --------------------------------------------------------------------------- #
# Directory shape                                                             #
# --------------------------------------------------------------------------- #


def test_agents_directory_contains_dev_wrapper_and_review_bmad_wrapper_at_minimum(
    agents_dir: pathlib.Path,
) -> None:
    assert agents_dir.is_dir(), "agents/ directory must exist"
    md_files = sorted(p.name for p in agents_dir.glob("*.md"))
    assert {"dev-wrapper.md", "review-bmad-wrapper.md"}.issubset(set(md_files)), (
        "agents/ top-level must contain dev-wrapper.md and review-bmad-wrapper.md "
        f"at minimum (additional sibling specialists permitted); found {md_files}"
    )
    subdirs = [p for p in agents_dir.iterdir() if p.is_dir()]
    assert subdirs == [], f"agents/ must have no subdirectories; found {subdirs}"


def test_review_bmad_wrapper_has_lf_line_endings(
    review_wrapper_bytes: bytes,
) -> None:
    assert b"\r\n" not in review_wrapper_bytes, (
        "review-bmad-wrapper.md must use LF line endings (no CRLF)"
    )
    assert b"\r" not in review_wrapper_bytes, (
        "review-bmad-wrapper.md must use LF line endings"
    )
