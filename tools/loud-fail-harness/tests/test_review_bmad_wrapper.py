"""Contract-coverage matrix for the Review-BMAD wrapper (Story 2.9 → Story 3.1 → Story 3.2 → Story 3.3).

This docstring IS the contract-coverage checklist required by AC-7 (Story 2.9),
AC-5 (Story 3.1), AC-5 (Story 3.2), and AC-7 (Story 3.3). Reviewers verify
every row maps to at least one passing test in this module. The matrix is
review-enforced, NOT CI-enforced (parallel to stories 1.2-1.9 + 2.2-2.8).
Story 3.3 thickens this file IN PLACE: existing Story 3.1 + 3.2 tests are
PRESERVED verbatim where the Story 3.3 additions are APPENDED (not
interleaved); new tests cover the 2 new envelope fixtures (the post-3.3
contract shape) + the AC-2 schema bump shape + the meta-field invariant
across review fixtures + the AC-3 wrapper-prose H2 section.

Fixture-shape conformance (Story 2.9 AC-6/AC-7; Story 3.1 AC-5; Story 3.2 AC-5; Story 3.3 AC-7):
    [x] review-pass-acceptance-auditor.yaml validates against schema     → test_review_pass_acceptance_auditor_fixture_validates_against_schema
    [x] review-fail-layer-failure.yaml validates against schema          → test_review_fail_layer_failure_fixture_validates_against_schema
    [x] review-pass-three-layer.yaml validates against schema            → test_review_pass_three_layer_fixture_validates_against_schema
    [x] review-fail-three-layer-patch.yaml validates against schema      → test_review_fail_three_layer_patch_fixture_validates_against_schema
    [x] review-blocked-partial-layer-failure.yaml validates against schema → test_review_blocked_partial_layer_failure_fixture_validates_against_schema
    [x] review-pass-bucket-coverage.yaml validates against schema +      → test_review_pass_bucket_coverage_fixture_validates_against_schema
        spans bucket × severity matrix
    [x] review-blocked-three-layer-failure-with-meta.yaml validates +    → test_review_blocked_three_layer_failure_with_meta_validates_against_schema
        carries 3 synthetic meta findings (Story 3.3 post-contract)
    [x] review-pass-partial-layer-failure-with-meta.yaml validates +     → test_review_pass_partial_layer_failure_with_meta_validates_against_schema
        carries 1 synthetic meta finding (Story 3.3 post-contract)

Story 3.3 schema-shape + meta-field invariants (Story 3.3 AC-7):
    [x] $defs/finding.properties.meta optional enum=[review-completeness] → test_envelope_schema_finding_meta_property_optional_with_review_completeness_enum
    [x] unknown meta value rejected at validate_return_envelope          → test_finding_with_unknown_meta_value_fails_envelope_schema_validation
    [x] post-3.3 review fixtures with failed_layers carry synthetic meta → test_synthetic_findings_carry_meta_review_completeness_in_post_3_3_fixtures
    [x] review-bmad-wrapper.md documents three-channel surface H2        → test_review_bmad_wrapper_documents_failed_layers_three_channel_surface

Cross-fixture invariants (Story 2.9 AC-4/AC-7, FR52, FR56; Story 3.1 AC-5;
Story 3.2 AC-5):
    [x] every review-*.yaml has failed_layers field present (6 fixtures) → test_all_review_fixtures_have_failed_layers_field_present
    [x] every review-*.yaml failed_layers ⊆ {blind, edge, auditor, lad}  → test_all_review_fixtures_have_failed_layers_subset_of_schema_enum
    [x] every review-*.yaml finding source ∈ schema source enum          → test_all_review_fixtures_have_layer_attribution_preserved_on_findings
    [x] no review-*.yaml carries forbidden flow-policy fields            → test_all_review_fixtures_have_no_forbidden_flow_policy_fields
    [x] every Epic-3-scope review-*.yaml carries surviving findings      → test_epic3_review_fixtures_carry_surviving_findings
    [x] every finding's bucket ∈ canonical FR27 taxonomy                 → test_all_review_fixtures_buckets_in_canonical_taxonomy
    [x] every finding's severity ∈ canonical FR27 taxonomy               → test_all_review_fixtures_severities_in_canonical_taxonomy

Forward-compat loud-fail path (Story 3.2 AC-5):
    [x] unknown bucket value rejected at validate_return_envelope        → test_unknown_bucket_value_fails_envelope_schema_validation
    [x] unknown severity value rejected at validate_return_envelope      → test_unknown_severity_value_fails_envelope_schema_validation
    [x] extra classification field on finding rejected at validator      → test_finding_with_extra_classification_field_fails_envelope_schema_validation

Wrapper-prose discipline (Story 2.9 AC-2/AC-3/AC-4/AC-5/AC-7/AC-8;
Story 3.1 AC-1/AC-2/AC-3/AC-5; Story 3.2 AC-1/AC-2/AC-5):
    [x] review-bmad-wrapper.md documents three-layer parallel-pass scope → test_review_bmad_wrapper_documents_three_layer_parallel_pass_scope
    [x] review-bmad-wrapper.md names failed_layers always-present        → test_review_bmad_wrapper_documents_failed_layers_invariant
    [x] review-bmad-wrapper.md has zero cross-specialist references      → test_review_bmad_wrapper_no_cross_specialist_references
    [x] review-bmad-wrapper.md documents bmad-code-review composition    → test_review_bmad_wrapper_documents_bmad_code_review_composition
    [x] review-bmad-wrapper.md documents required envelope fields        → test_review_bmad_wrapper_documents_required_envelope_fields
    [x] review-bmad-wrapper.md documents Acceptance Auditor rationale    → test_review_bmad_wrapper_documents_acceptance_auditor_rationale
    [x] review-bmad-wrapper.md documents finding-taxonomy passthrough    → test_review_bmad_wrapper_documents_finding_taxonomy_passthrough

Directory shape (Story 2.9 AC-1):
    [x] agents/ contains dev-wrapper.md AND review-bmad-wrapper.md at    → test_agents_directory_contains_dev_wrapper_and_review_bmad_wrapper_at_minimum
        minimum (one of three+ specialist files at this point)
    [x] review-bmad-wrapper.md uses LF line endings                      → test_review_bmad_wrapper_has_lf_line_endings
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
    """Story 3.3 extension: the set grows to 8 review-*.yaml fixtures with
    the addition of two new fixtures carrying the post-Story-3.3 synthetic
    meta-finding emission shape. Existing 6 fixtures (Story 2.9 + 3.1 + 3.2)
    preserved verbatim — the 2 new fixtures are additive.
    """
    return (
        "review-pass-acceptance-auditor.yaml",
        "review-fail-layer-failure.yaml",
        "review-pass-three-layer.yaml",
        "review-fail-three-layer-patch.yaml",
        "review-blocked-partial-layer-failure.yaml",
        "review-pass-bucket-coverage.yaml",
        "review-blocked-three-layer-failure-with-meta.yaml",
        "review-pass-partial-layer-failure-with-meta.yaml",
    )


def _post_3_3_review_envelope_filenames() -> tuple[str, ...]:
    """The post-Story-3.3 fixtures whose synthetic meta-finding emission
    is the AC-7 invariant target. Pre-3.3 fixtures
    (review-blocked-partial-layer-failure.yaml + review-fail-layer-failure
    .yaml) pre-date the synthetic-finding emission and are intentionally
    excluded from the meta-field invariant test — they remain valid
    against the post-3.3 schema because `meta` is optional, but they do
    NOT carry the synthetic finding (back-compat carve-out per AC-7
    item 3).
    """
    return (
        "review-blocked-three-layer-failure-with-meta.yaml",
        "review-pass-partial-layer-failure-with-meta.yaml",
    )


_FAILED_LAYERS_ENUM: frozenset[str] = frozenset({"blind", "edge", "auditor", "lad"})
_FINDING_SOURCE_ENUM: frozenset[str] = frozenset(
    {"blind", "edge", "auditor", "qa", "lad", "merged"}
)
_CANONICAL_BUCKETS: frozenset[str] = frozenset(
    {"decision_needed", "patch", "defer", "dismiss"}
)
_CANONICAL_SEVERITIES: frozenset[str] = frozenset({"HIGH", "MED", "LOW"})
_CANONICAL_META_VALUES: frozenset[str] = frozenset({"review-completeness"})


def _minimal_valid_finding() -> dict[str, Any]:
    """Construct a minimal schema-valid finding dict for forward-compat
    loud-fail tests. Caller mutates exactly one field to introduce the
    out-of-enum / extra-field condition the test asserts is rejected.
    """
    return {
        "id": "synth-001",
        "source": "auditor",
        "title": "synthesized finding for forward-compat loud-fail test",
        "detail": "Test-only synthesized finding; not produced by any specialist.",
        "location": "bmad-autopilot/tools/loud-fail-harness/tests/test_review_bmad_wrapper.py:1",
        "bucket": "defer",
        "severity": "LOW",
    }


def _minimal_valid_envelope() -> dict[str, Any]:
    """Construct a minimal schema-valid Review-BMAD envelope wrapping the
    synthesized finding. Caller mutates the finding's bucket/severity/extras
    to introduce the loud-fail condition under test.
    """
    return {
        "status": "pass",
        "artifacts": ["bmad-autopilot/agents/review-bmad-wrapper.md"],
        "findings": [_minimal_valid_finding()],
        "rationale": "Synthesized envelope for forward-compat loud-fail test.",
        "failed_layers": [],
    }


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


def test_review_pass_three_layer_fixture_validates_against_schema(
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.1 AC-5 item 4: post-aggregation envelope shape with all three
    layers running successfully and at least three distinct source values
    among the post-triage findings.
    """
    envelope = _load_envelope(envelopes_dir, "review-pass-three-layer.yaml")
    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
    assert envelope["status"] == "pass"
    assert envelope["failed_layers"] == []
    assert len(envelope["findings"]) >= 3, (
        "review-pass-three-layer fixture must carry at least three findings "
        "to demonstrate post-aggregation envelope shape across layers"
    )
    sources = {finding["source"] for finding in envelope["findings"]}
    expected_sources = {"blind", "edge", "auditor", "merged"}
    overlap = sources & expected_sources
    assert len(overlap) >= 3, (
        f"review-pass-three-layer fixture must surface at least three of "
        f"{sorted(expected_sources)}; got {sorted(sources)}"
    )


def test_review_fail_three_layer_patch_fixture_validates_against_schema(
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.1 AC-5 item 5: at least one HIGH-severity patch-bucket finding
    drives status=fail end-to-end.
    """
    envelope = _load_envelope(envelopes_dir, "review-fail-three-layer-patch.yaml")
    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
    assert envelope["status"] == "fail"
    high_patch_findings = [
        f
        for f in envelope["findings"]
        if f.get("bucket") == "patch" and f.get("severity") == "HIGH"
    ]
    assert high_patch_findings, (
        "review-fail-three-layer-patch fixture must carry at least one "
        "HIGH-severity patch-bucket finding driving the fail verdict per "
        "FR9 routing"
    )


def test_review_blocked_partial_layer_failure_fixture_validates_against_schema(
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.1 AC-5 item 6: partial-layer-failure shape — exactly one
    failed layer drawn from {blind, edge, auditor}; surviving layers'
    findings flow through normally per FR28 graceful degradation.
    """
    envelope = _load_envelope(
        envelopes_dir, "review-blocked-partial-layer-failure.yaml"
    )
    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
    assert envelope["status"] in {"pass", "fail"}, (
        "partial-layer-failure fixture must have status: pass or fail "
        "(blocked is reserved for total layer failure — all three layers failing)"
    )
    assert len(envelope["failed_layers"]) == 1, (
        "partial-layer-failure fixture must declare exactly one failed layer "
        "to demonstrate the partial-failure shape from AC-3 contract 2"
    )
    assert envelope["failed_layers"][0] in {"blind", "edge", "auditor"}, (
        "partial-layer-failure fixture's failed layer must be drawn from "
        "the three live Epic-3 layers"
    )
    assert len(envelope["findings"]) >= 1, (
        "FR28 graceful degradation: surviving layers' findings must flow "
        "through the envelope when one layer fails"
    )
    failed_layer = envelope["failed_layers"][0]
    for finding in envelope["findings"]:
        assert finding["source"] != failed_layer, (
            f"findings from the failed layer ({failed_layer}) must not appear "
            f"in the envelope per bmad-code-review's step-02-review.md "
            f"line 27 (failed-layer drop)"
        )


# --------------------------------------------------------------------------- #
# Cross-fixture invariants                                                    #
# --------------------------------------------------------------------------- #


def test_all_review_fixtures_have_failed_layers_field_present(
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.1 AC-5 item 9 (relaxed in place): the loaded set grows from
    the 2 Epic-2 fixtures to all 5 review-*.yaml fixtures.
    """
    for name in _all_review_envelope_filenames():
        envelope = _load_envelope(envelopes_dir, name)
        assert "failed_layers" in envelope, (
            f"{name} must declare failed_layers (always present, even when empty)"
        )
        layers = envelope["failed_layers"]
        assert isinstance(layers, list), f"{name} failed_layers must be a list"


def test_all_review_fixtures_have_failed_layers_subset_of_schema_enum(
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.1 AC-5 item 7: every fixture's failed_layers ⊆
    {blind, edge, auditor, lad} per envelope.schema.yaml lines 92-97.
    """
    for name in _all_review_envelope_filenames():
        envelope = _load_envelope(envelopes_dir, name)
        layers = envelope["failed_layers"]
        for layer in layers:
            assert layer in _FAILED_LAYERS_ENUM, (
                f"{name} failed_layers item {layer!r} not in schema enum "
                f"{sorted(_FAILED_LAYERS_ENUM)}"
            )


def test_all_review_fixtures_have_layer_attribution_preserved_on_findings(
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.1 AC-5 item 8: every finding's source field is drawn from
    the schema's source enum per envelope.schema.yaml line 117 — the
    layer-attribution discipline that lets Story 3.5 audit per-layer
    composition and lets Story 3.2 route bucket signals downstream.
    """
    for name in _all_review_envelope_filenames():
        envelope = _load_envelope(envelopes_dir, name)
        for finding in envelope["findings"]:
            source = finding.get("source")
            assert source in _FINDING_SOURCE_ENUM, (
                f"{name} finding source {source!r} not in schema enum "
                f"{sorted(_FINDING_SOURCE_ENUM)}"
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


def test_epic3_review_fixtures_carry_surviving_findings(
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.1 cross-fixture invariant: the three Epic-3-scope review
    fixtures (review-pass-three-layer.yaml, review-fail-three-layer-patch.yaml,
    review-blocked-partial-layer-failure.yaml) all carry at least one
    finding. The pass + fail + partial-failure shapes all reach a verdict
    via at least one surviving layer. Story 2.9's review-fail-layer-failure.yaml
    (Epic-2-scope single-layer total-failure case, preserved as canonical history)
    emits findings: []; the true Epic-3 total-layer-failure shape
    (failed_layers: ["blind", "edge", "auditor"]) has no fixture in this story —
    tracked for Story 3.3. Note: an all-dismiss triage run also produces
    findings: [] with status: pass; this test only checks the three named
    Epic-3 fixtures which are designed to carry surviving findings.
    """
    epic3_fixtures = (
        "review-pass-three-layer.yaml",
        "review-fail-three-layer-patch.yaml",
        "review-blocked-partial-layer-failure.yaml",
    )
    for name in epic3_fixtures:
        envelope = _load_envelope(envelopes_dir, name)
        assert envelope["findings"], (
            f"{name} must carry at least one finding (Epic-3-scope fixtures "
            f"exercise the post-aggregation envelope shape via surviving "
            f"layers' findings flowing through; only the total-layer-failure "
            f"case emits findings: [])"
        )


# --------------------------------------------------------------------------- #
# Wrapper-prose discipline                                                    #
# --------------------------------------------------------------------------- #


def test_review_bmad_wrapper_documents_three_layer_parallel_pass_scope(
    review_wrapper_text: str,
) -> None:
    """Story 3.1 AC-5 item 2: relaxed + renamed from Story 2.9's
    test_review_bmad_wrapper_documents_acceptance_auditor_single_layer_scope.
    The rewrite frames the wrapper as Epic-3-scope; all three layer names
    must appear in the prose, and Epic 3 framing must be near the first
    Acceptance Auditor mention.
    """
    text = review_wrapper_text
    for layer_name in ("Blind Hunter", "Edge Case Hunter", "Acceptance Auditor"):
        assert layer_name in text, (
            f"review-bmad-wrapper.md must name the {layer_name} layer "
            "(layer-attribution discipline is now structurally documented)"
        )
    idx = text.find("Acceptance Auditor")
    assert idx >= 0
    # Story 3.1 relaxation: Epic 3 framing within 600 chars of first
    # Acceptance Auditor mention; Epic 2 single-layer history may also
    # appear (referenced in the "Epic 3 thickening landing" section per
    # AC-1) but is no longer the dominant frame.
    window_600 = text[idx : idx + 600]
    assert re.search(r"Epic 3|Story 3\.1", window_600), (
        "first Acceptance Auditor mention must name Epic 3 or Story 3.1 within "
        "600 chars (the Epic-3-scope framing per Story 3.1 AC-1)"
    )


def test_review_bmad_wrapper_documents_failed_layers_invariant(
    review_wrapper_text: str,
) -> None:
    """Story 3.1 AC-5 item 3: substring-proximity assertion accepts any of
    blind / edge / auditor within the proximity window (relaxed from
    Story 2.9's auditor-only assertion).
    """
    text = review_wrapper_text
    idx = text.find("failed_layers")
    assert idx >= 0, "review-bmad-wrapper.md must mention failed_layers"
    window = text[idx : idx + 400]
    # Story 3.1 relaxation: any of blind / edge / auditor is acceptable in
    # the proximity window (Epic-3 thickened layer set).
    assert any(layer in window for layer in ("blind", "edge", "auditor")), (
        "first failed_layers mention must name at least one of "
        "blind / edge / auditor within 400 chars"
    )
    # Always-present invariant unchanged from Story 2.9 AC-4: standalone
    # `[]` token or the literal word "empty" near the first failed_layers
    # mention.
    assert re.search(r"(^|[^A-Za-z0-9,])\[\]", window) or "empty" in window, (
        "first failed_layers mention must show standalone [] or word 'empty' "
        "within 400 chars (bare enum-closing bracket does not count)"
    )


def test_review_bmad_wrapper_no_cross_specialist_references(
    review_wrapper_text: str,
) -> None:
    # Story 2.9 AC-5 + Story 3.1 AC-2: zero substring matches for any sibling
    # specialist agent file by path. The wrapper's FR62 prohibition prose names
    # sibling specialists by human-readable form (the Dev specialist, the QA
    # specialist, the Phase-1.5 LAD layer), not by literal `agents/<slug>.md`
    # path-form, so the pluggability_gate's Rule 1 regex cannot fire on this
    # wrapper.
    forbidden_paths = (
        "agents/dev-wrapper.md",
        "agents/qa.md",
        "agents/lad.md",
        "agents/review-lad-wrapper.md",
    )
    for name in forbidden_paths:
        assert name not in review_wrapper_text, (
            f"review-bmad-wrapper.md must not reference {name} "
            "(FR62 zero-substring-match)"
        )
    # Slug-form: zero word-bounded matches for the multi-hyphen sibling slugs
    # that would trigger the pluggability gate's Rule 2 regex.
    # Note: standalone single-word slugs (lad, qa) are deliberately excluded
    # from Rule 2 checking — the gate targets multi-hyphen slugs only; the
    # wrapper's `lad` occurrences are in schema-enum documentation context
    # ([blind, edge, auditor, lad]), not specialist references.
    forbidden_slugs = ("dev-wrapper", "review-lad-wrapper")
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
    # Story 2.9 AC-8 clause-(a) marker: traceability to acceptance criteria.
    # Story 3.1 AC-1 retains this language via the cross-reference to
    # Story 3.5's audit artifact which validates the Story 2.9 rationale
    # clauses against the actual three-layer composition.
    assert re.search(r"traceab", text), (
        "review-bmad-wrapper.md must document Acceptance Auditor traceability "
        "rationale (clause a) per Story 2.9 AC-8 / Story 3.1 AC-1"
    )
    # Story 2.9 AC-8 clause-(b) marker: seam-contract churn minimization OR
    # aggregated output.
    assert "seam-contract" in text or "aggregated output" in text, (
        "review-bmad-wrapper.md must document Acceptance Auditor "
        "seam-contract / aggregated-output rationale (clause b) per "
        "Story 2.9 AC-8 / Story 3.1 AC-1"
    )


def test_review_bmad_wrapper_documents_finding_taxonomy_passthrough(
    review_wrapper_text: str,
) -> None:
    """Story 3.2 AC-5 item 8: the wrapper's new H2 section names the
    bucket × severity passthrough invariant, the four canonical bucket
    values, the three canonical severity values, the Story 5.2 / Epic 5
    retry-router downstream consumer, the no-coercion language, and the
    forward-compat loud-fail path — all within a single contract section.
    """
    text = review_wrapper_text
    section_idx = text.find("## Finding-taxonomy passthrough")
    assert section_idx >= 0, (
        "review-bmad-wrapper.md must declare a Story-3.2 finding-taxonomy "
        "passthrough section by H2 heading"
    )
    # Story 3.2 marker is within 100 chars of the passthrough/taxonomy heading
    # (the AC accepts either substring as the proximity anchor).
    heading_window = text[section_idx : section_idx + 100]
    assert "Story 3.2" in heading_window, (
        "the passthrough section's heading must name Story 3.2 within 100 "
        "chars of 'passthrough' or 'taxonomy'"
    )
    section_window = text[section_idx : section_idx + 3000]
    for bucket_value in ("decision_needed", "patch", "defer", "dismiss"):
        assert bucket_value in section_window, (
            f"Story 3.2 passthrough section must name bucket value "
            f"{bucket_value!r} within the new section's 3000-char window"
        )
    for severity_value in ("HIGH", "MED", "LOW"):
        assert severity_value in section_window, (
            f"Story 3.2 passthrough section must name severity value "
            f"{severity_value!r} within the new section's 3000-char window"
        )
    assert "Story 5.2" in section_window or "Epic 5" in section_window, (
        "Story 3.2 passthrough section must name Story 5.2 or Epic 5 as the "
        "downstream retry-router consumer of the bucket signal"
    )
    assert "verbatim" in section_window or "passthrough" in section_window, (
        "Story 3.2 passthrough section must use the no-coercion language "
        "('verbatim' or 'passthrough') within the new section"
    )
    assert (
        "additionalProperties" in section_window
        or "forward-compat" in section_window
        or "forward-compatibility" in section_window
    ), (
        "Story 3.2 passthrough section must name the loud-fail path "
        "('additionalProperties' or 'forward-compat' / 'forward-compatibility')"
    )


# --------------------------------------------------------------------------- #
# Story 3.2 — bucket-coverage fixture shape                                   #
# --------------------------------------------------------------------------- #


def test_review_pass_bucket_coverage_fixture_validates_against_schema(
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.2 AC-5 item 2: the new bucket × severity matrix coverage
    fixture validates against the schema and spans the gap-filling
    (bucket, severity) combinations the existing 5 review fixtures
    collectively under-cover.
    """
    envelope = _load_envelope(envelopes_dir, "review-pass-bucket-coverage.yaml")
    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
    assert envelope["status"] == "pass"
    assert envelope["failed_layers"] == []
    assert len(envelope["findings"]) >= 7, (
        "review-pass-bucket-coverage fixture must carry at least seven "
        "findings to span the bucket × severity matrix per Story 3.2 AC-3"
    )
    bucket_severity_pairs = {
        (finding["bucket"], finding["severity"]) for finding in envelope["findings"]
    }
    required_pairs = {
        ("decision_needed", "HIGH"),
        ("decision_needed", "MED"),
        ("decision_needed", "LOW"),
        ("patch", "MED"),
        ("patch", "LOW"),
        ("defer", "HIGH"),
        ("dismiss", "MED"),
    }
    missing = required_pairs - bucket_severity_pairs
    assert not missing, (
        f"review-pass-bucket-coverage fixture missing required (bucket, "
        f"severity) combinations: {sorted(missing)}; got {sorted(bucket_severity_pairs)}"
    )
    sources = {finding["source"] for finding in envelope["findings"]}
    assert len(sources) >= 2, (
        "review-pass-bucket-coverage fixture must surface at least two "
        "distinct source values per Story 3.2 AC-3 (layer-attribution discipline)"
    )


# --------------------------------------------------------------------------- #
# Story 3.2 — canonical-taxonomy invariants (FR27)                            #
# --------------------------------------------------------------------------- #


def test_all_review_fixtures_buckets_in_canonical_taxonomy(
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.2 AC-5 item 3: every review fixture's findings carry only
    canonical FR27 bucket values. Schema-level enforcement is the structural
    backstop ($defs/finding bucket enum at envelope.schema.yaml line 130);
    this test is the explicit FR27 invariant making the canonical-taxonomy
    commitment a named contract assertion.
    """
    for name in _all_review_envelope_filenames():
        envelope = _load_envelope(envelopes_dir, name)
        for finding in envelope["findings"]:
            bucket = finding.get("bucket")
            assert bucket in _CANONICAL_BUCKETS, (
                f"{name} finding bucket {bucket!r} not in canonical FR27 "
                f"taxonomy {sorted(_CANONICAL_BUCKETS)}"
            )


def test_all_review_fixtures_severities_in_canonical_taxonomy(
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.2 AC-5 item 4: every review fixture's findings carry only
    canonical FR27 severity values. Schema-level enforcement is the
    structural backstop ($defs/finding severity enum at envelope.schema.yaml
    line 132); this test is the explicit FR27 invariant.
    """
    for name in _all_review_envelope_filenames():
        envelope = _load_envelope(envelopes_dir, name)
        for finding in envelope["findings"]:
            severity = finding.get("severity")
            assert severity in _CANONICAL_SEVERITIES, (
                f"{name} finding severity {severity!r} not in canonical FR27 "
                f"taxonomy {sorted(_CANONICAL_SEVERITIES)}"
            )


# --------------------------------------------------------------------------- #
# Story 3.2 — forward-compat loud-fail path                                   #
# --------------------------------------------------------------------------- #


def test_unknown_bucket_value_fails_envelope_schema_validation() -> None:
    """Story 3.2 AC-5 item 5: an envelope carrying a finding with an
    out-of-enum bucket value is REJECTED at validate_return_envelope —
    the substrate-seam loud-fail per Pattern 5. This is the architectural
    mechanism that makes the wrapper's verbatim-passthrough commitment
    safe: a future bmad-code-review release introducing a new bucket
    value cannot survive the gate without an explicit schema bump
    recorded in docs/extension-audit.md per Story 3.2 AC-4.
    """
    envelope = _minimal_valid_envelope()
    envelope["findings"][0]["bucket"] = "unknown_future_bucket"
    result = validate_return_envelope(envelope)
    assert not result.valid, (
        "envelope with out-of-enum bucket value must be rejected at the "
        "substrate seam (forward-compat loud-fail per Pattern 5)"
    )
    error_text = " ".join(result.errors).lower()
    assert "bucket" in error_text or "is not one of" in error_text, (
        f"validation error must name the offending field/constraint; "
        f"got {result.errors!r}"
    )


def test_unknown_severity_value_fails_envelope_schema_validation() -> None:
    """Story 3.2 AC-5 item 6: an envelope carrying a finding with an
    out-of-enum severity value is REJECTED at validate_return_envelope.
    """
    envelope = _minimal_valid_envelope()
    envelope["findings"][0]["severity"] = "CRITICAL"
    result = validate_return_envelope(envelope)
    assert not result.valid, (
        "envelope with out-of-enum severity value must be rejected at "
        "the substrate seam (forward-compat loud-fail per Pattern 5)"
    )
    error_text = " ".join(result.errors).lower()
    assert "severity" in error_text or "is not one of" in error_text, (
        f"validation error must name the offending field/constraint; "
        f"got {result.errors!r}"
    )


def test_finding_with_extra_classification_field_fails_envelope_schema_validation() -> None:
    """Story 3.2 AC-5 item 7: an envelope carrying a finding with an extra
    classification field (e.g., `category`) is REJECTED at
    validate_return_envelope. The schema's $defs/finding additionalProperties:
    false (envelope.schema.yaml line 110) is the structural enforcement of
    the FR27 + FR62 no-introductions invariant.
    """
    envelope = _minimal_valid_envelope()
    envelope["findings"][0]["category"] = "regression"
    result = validate_return_envelope(envelope)
    assert not result.valid, (
        "envelope with extra classification field on a finding must be "
        "rejected at the substrate seam (additionalProperties: false on "
        "$defs/finding per envelope.schema.yaml line 110)"
    )
    error_text = " ".join(result.errors).lower()
    assert "additional property" in error_text or "category" in error_text, (
        f"validation error must name the additionalProperties constraint or "
        f"the offending field; got {result.errors!r}"
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


# --------------------------------------------------------------------------- #
# Story 3.3 — post-3.3 fixture-shape conformance + schema bump invariants     #
# --------------------------------------------------------------------------- #


def test_review_blocked_three_layer_failure_with_meta_validates_against_schema(
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.3 AC-7 item 2: the new all-three-layers-fail fixture
    validates against the post-AC-2 schema and carries exactly 3
    synthetic meta-findings (one per failed layer).
    """
    envelope = _load_envelope(
        envelopes_dir, "review-blocked-three-layer-failure-with-meta.yaml"
    )
    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
    assert envelope["status"] == "blocked"
    assert envelope["artifacts"] == [], (
        "all-three-layers-fail fixture has empty artifacts (no review output)"
    )
    assert envelope["failed_layers"] == ["auditor", "blind", "edge"], (
        "failed_layers must be sorted alphabetically per Story 3.3 AC-1"
    )
    meta_findings = [
        f
        for f in envelope["findings"]
        if f.get("meta") == "review-completeness"
    ]
    assert len(meta_findings) == 3, (
        "all-three-layers-fail fixture must carry exactly 3 synthetic "
        "meta findings (one per failed layer)"
    )
    for finding in meta_findings:
        assert finding["bucket"] == "decision_needed"
        assert finding["severity"] == "HIGH"
        assert finding["meta"] == "review-completeness"
    finding_ids = {f["id"] for f in meta_findings}
    assert finding_ids == {
        "review-layer-failed-auditor",
        "review-layer-failed-blind",
        "review-layer-failed-edge",
    }


def test_review_pass_partial_layer_failure_with_meta_validates_against_schema(
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.3 AC-7 item 2: the new partial-layer-failure-with-meta
    fixture validates against the post-AC-2 schema and carries exactly
    1 synthetic meta-finding for the failed layer alongside the
    surviving layers' content findings.
    """
    envelope = _load_envelope(
        envelopes_dir, "review-pass-partial-layer-failure-with-meta.yaml"
    )
    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
    assert envelope["status"] == "pass"
    assert envelope["failed_layers"] == ["edge"]
    meta_findings = [
        f
        for f in envelope["findings"]
        if f.get("meta") == "review-completeness"
    ]
    assert len(meta_findings) == 1, (
        "partial-layer-failure-with-meta fixture must carry exactly 1 "
        "synthetic meta finding (for the single failed layer)"
    )
    assert meta_findings[0]["id"] == "review-layer-failed-edge"
    assert meta_findings[0]["bucket"] == "decision_needed"
    assert meta_findings[0]["severity"] == "HIGH"
    # Surviving layers' content findings flow through normally per FR28.
    content_findings = [
        f for f in envelope["findings"] if f.get("meta") is None
    ]
    assert len(content_findings) >= 1, (
        "FR28 graceful degradation: surviving layers' content findings "
        "must flow through alongside the synthetic meta finding"
    )


def test_synthetic_findings_carry_meta_review_completeness_in_post_3_3_fixtures(
    envelopes_dir: pathlib.Path,
) -> None:
    """Story 3.3 AC-7 item 3: post-Story-3.3 review fixtures with non-empty
    failed_layers carry AT LEAST ONE finding with meta: review-completeness
    (the post-Story-3.3 invariant). Pre-3.3 fixtures
    (review-blocked-partial-layer-failure.yaml +
    review-fail-layer-failure.yaml) are excluded by name — they pre-date
    the synthetic-finding emission and remain valid against the post-3.3
    schema because `meta` is optional (back-compat carve-out per AC-7
    item 3).
    """
    for name in _post_3_3_review_envelope_filenames():
        envelope = _load_envelope(envelopes_dir, name)
        assert envelope["failed_layers"], (
            f"{name} should carry non-empty failed_layers; the post-3.3 "
            "invariant is meaningful only when failed_layers is non-empty"
        )
        meta_findings = [
            f
            for f in envelope["findings"]
            if f.get("meta") == "review-completeness"
        ]
        assert len(meta_findings) == len(envelope["failed_layers"]), (
            f"{name} must carry exactly len(failed_layers)="
            f"{len(envelope['failed_layers'])} synthetic meta findings; "
            f"got {len(meta_findings)}"
        )
        for finding in meta_findings:
            assert finding["meta"] in _CANONICAL_META_VALUES, (
                f"{name} synthetic finding meta value "
                f"{finding['meta']!r} not in canonical "
                f"{sorted(_CANONICAL_META_VALUES)}"
            )


def test_envelope_schema_finding_meta_property_optional_with_review_completeness_enum(
    repo_root: pathlib.Path,
) -> None:
    """Story 3.3 AC-7 item 4: the schema bump at AC-2 lands the optional
    `meta` property with enum=[review-completeness], preserves
    additionalProperties=false on $defs/finding, and does NOT add `meta`
    to the required list.
    """
    schema = yaml.safe_load(
        (repo_root / "schemas" / "envelope.schema.yaml").read_text(
            encoding="utf-8"
        )
    )
    finding_def = schema["$defs"]["finding"]
    assert finding_def["additionalProperties"] is False, (
        "$defs/finding.additionalProperties must remain False after the "
        "Story 3.3 AC-2 schema bump"
    )
    assert "meta" not in finding_def["required"], (
        "meta is OPTIONAL on $defs/finding; it MUST NOT be in the "
        "required list (layer-produced findings continue to validate "
        "without it)"
    )
    meta_prop = finding_def["properties"]["meta"]
    assert meta_prop["type"] == "string", (
        "$defs/finding.properties.meta must have type=string"
    )
    assert meta_prop["enum"] == ["review-completeness"], (
        "$defs/finding.properties.meta enum must be exactly "
        "[review-completeness] at this story; future meta-finding kinds "
        "extend the enum via a follow-on schema bump per the audit-doc "
        "no-introductions principle"
    )


def test_finding_with_unknown_meta_value_fails_envelope_schema_validation() -> None:
    """Story 3.3 AC-7 item 5: a finding carrying meta value not in the
    enum is REJECTED at validate_return_envelope. Forward-compat
    loud-fail mirroring Story 3.2's bucket / severity tests; the
    substrate-seam loud-fail is the architectural backstop per Pattern 5.
    """
    envelope = _minimal_valid_envelope()
    envelope["findings"][0]["meta"] = "future-meta-kind"
    result = validate_return_envelope(envelope)
    assert not result.valid, (
        "envelope with out-of-enum meta value must be rejected at the "
        "substrate seam (forward-compat loud-fail per Pattern 5)"
    )
    error_text = " ".join(result.errors).lower()
    assert "meta" in error_text or "is not one of" in error_text or "enum" in error_text, (
        f"validation error must name the offending field/constraint; "
        f"got {result.errors!r}"
    )


def test_review_bmad_wrapper_documents_failed_layers_three_channel_surface(
    review_wrapper_text: str,
) -> None:
    """Story 3.3 AC-7 item 6: the wrapper's new H2 section documents the
    three-channel atomic emission contract, the `surface_failed_layers`
    function name, the `meta: review-completeness` discriminator, and
    cross-references Story 3.4 / Epic 6 / Story 6.1 as downstream
    consumers.
    """
    text = review_wrapper_text
    section_idx = text.find("## Failed-layers three-channel surface")
    assert section_idx >= 0, (
        "review-bmad-wrapper.md must declare a Story-3.3 H2 section "
        "named 'Failed-layers three-channel surface'"
    )
    heading_window = text[section_idx : section_idx + 100]
    assert "Story 3.3" in heading_window, (
        "the H2 section's heading must name Story 3.3 within 100 chars "
        "of 'three-channel' or 'failed-layers'"
    )
    section_window = text[section_idx : section_idx + 5000]
    for substring in (
        "failed_layers",
        "review-layer-failed",
        "meta: review-completeness",
        "decision_needed",
        "HIGH",
        "surface_failed_layers",
    ):
        assert substring in section_window, (
            f"Story 3.3 three-channel-surface section must name "
            f"{substring!r} within the section's 5000-char window"
        )
    assert "Story 3.4" in section_window or "Epic 6" in section_window, (
        "Story 3.3 section must name Story 3.4 or Epic 6 as the "
        "downstream consumer"
    )
    assert "Story 6.1" in section_window, (
        "Story 3.3 section must name Story 6.1 as the cross-channel "
        "reconciliation gate consumer"
    )
