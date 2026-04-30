"""Contract-coverage matrix for `surface_failed_layers` (Story 3.3 AC-8).

This docstring IS the contract-coverage checklist required by AC-8 of
Story 3.3. Reviewers verify every row maps to at least one passing test
in this module. The matrix is review-enforced, NOT CI-enforced.

The test surface is the single source-of-truth function
:func:`loud_fail_harness.review_layer_failure.surface_failed_layers`
which emits the three-channel atomic projection of a per-layer review
failure (FR28 + FR56). The atomicity is enforced as a code-structure
invariant; the AC-9 CI lint
:mod:`loud_fail_harness.review_layer_failure_emission_gate` is the
structural guard. THESE tests assert the FUNCTIONAL contract:

Cardinality cases (Story 3.3 AC-8 items 1-4):
    [x] zero failures → channels 2 + 3 silent             → test_surface_failed_layers_zero_failures_silent_at_channels_two_and_three
    [x] one failure → all three channels emit atomically  → test_surface_failed_layers_one_failure_emits_all_three_channels_atomically
    [x] two failures → two synthetic findings + markers   → test_surface_failed_layers_two_failures_emits_two_synthetic_findings_and_two_markers
    [x] three failures → three synthetic findings + markers → test_surface_failed_layers_three_failures_emits_three_synthetic_findings_and_three_markers

Registry validation invariant (Story 3.3 AC-8 item 5):
    [x] unknown marker class raises UnknownMarkerClass    → test_surface_failed_layers_validates_marker_via_registry

Post-emission schema-conformance invariant (Story 3.3 AC-8 item 6):
    [x] post-emission envelope round-trips schema validation → test_surface_failed_layers_post_emission_envelope_validates_against_schema
"""

from __future__ import annotations

from typing import Any

import pytest

from loud_fail_harness.review_layer_failure import (
    META_REVIEW_COMPLETENESS,
    REVIEW_LAYER_FAILED_MARKER,
    MarkerEmissionRecord,
    surface_failed_layers,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
    validate_return_envelope,
)


def _make_canonical_registry() -> MarkerClassRegistry:
    """Build a registry containing the `review-layer-failed` marker class.

    Test-time registry construction uses a literal frozenset rather than
    loading the real taxonomy file — the AC-8 tests assert the function's
    contract independently of the on-disk taxonomy's content (Story 1.4's
    enumeration is verified by tests/test_enumeration_check.py).
    """
    return MarkerClassRegistry(marker_classes=frozenset({REVIEW_LAYER_FAILED_MARKER}))


def _minimal_envelope() -> dict[str, Any]:
    """Construct a minimal Review-BMAD envelope dict for the test calls.

    The envelope satisfies the schema's required fields (status,
    artifacts, findings, rationale) before the function call; the
    function may add `failed_layers` and append synthetic findings.
    """
    return {
        "status": "blocked",
        "artifacts": [],
        "findings": [],
        "rationale": (
            "Synthesized envelope for the surface_failed_layers AC-8 "
            "contract-coverage tests."
        ),
    }


# --------------------------------------------------------------------------- #
# Cardinality cases                                                           #
# --------------------------------------------------------------------------- #


def test_surface_failed_layers_zero_failures_silent_at_channels_two_and_three() -> None:
    """Story 3.3 AC-8 item 1: zero-failure path is silent at channels
    2 + 3 — no marker emission record produced; no synthetic finding
    appended; envelope["findings"] unchanged. Channel 1 sets
    failed_layers = [] per Story 3.1's empty-list invariant.
    """
    envelope = _minimal_envelope()
    envelope["findings"].append(
        {
            "id": "pre-existing-finding",
            "source": "auditor",
            "title": "An unrelated pre-existing finding",
            "detail": "Carried verbatim through the zero-failure path.",
            "location": "agents/review-bmad-wrapper.md:1",
            "bucket": "defer",
            "severity": "LOW",
        }
    )
    pre_call_findings_snapshot = list(envelope["findings"])
    registry = _make_canonical_registry()

    emissions = surface_failed_layers(envelope, [], registry)

    assert emissions == ()
    assert envelope["failed_layers"] == []
    # Channel 3 must be silent — pre-existing finding unmodified, no append.
    assert envelope["findings"] == pre_call_findings_snapshot


def test_surface_failed_layers_one_failure_emits_all_three_channels_atomically() -> None:
    """Story 3.3 AC-8 item 2: a single-failure invocation emits all three
    channels atomically — channel 1 sets failed_layers; channel 2
    produces one marker emission record; channel 3 appends one
    synthetic finding with the canonical bucket / severity / meta /
    source / id shape.
    """
    envelope = _minimal_envelope()
    registry = _make_canonical_registry()

    emissions = surface_failed_layers(envelope, ["edge"], registry)

    # Channel 1.
    assert envelope["failed_layers"] == ["edge"]
    # Channel 2.
    assert len(emissions) == 1
    assert emissions[0] == MarkerEmissionRecord(
        marker_class=REVIEW_LAYER_FAILED_MARKER,
        failed_layer="edge",
    )
    # Channel 3.
    assert len(envelope["findings"]) == 1
    finding = envelope["findings"][0]
    assert finding["id"] == "review-layer-failed-edge"
    assert finding["source"] == "merged"
    assert finding["bucket"] == "decision_needed"
    assert finding["severity"] == "HIGH"
    assert finding["meta"] == META_REVIEW_COMPLETENESS
    assert "edge" in finding["title"]
    assert "edge" in finding["detail"]
    assert "edge" in finding["location"]


def test_surface_failed_layers_two_failures_emits_two_synthetic_findings_and_two_markers() -> None:
    """Story 3.3 AC-8 item 3: two failures produce two marker emission
    records and two synthetic findings; failed_layers is sorted
    alphabetically per AC-1.
    """
    envelope = _minimal_envelope()
    registry = _make_canonical_registry()

    # Pass in non-sorted order to verify the function sorts.
    emissions = surface_failed_layers(envelope, ["edge", "blind"], registry)

    assert envelope["failed_layers"] == ["blind", "edge"]
    assert len(emissions) == 2
    assert tuple(em.failed_layer for em in emissions) == ("blind", "edge")
    assert all(em.marker_class == REVIEW_LAYER_FAILED_MARKER for em in emissions)
    meta_findings = [
        f
        for f in envelope["findings"]
        if f.get("meta") == META_REVIEW_COMPLETENESS
    ]
    assert len(meta_findings) == 2
    assert {f["id"] for f in meta_findings} == {
        "review-layer-failed-blind",
        "review-layer-failed-edge",
    }


def test_surface_failed_layers_three_failures_emits_three_synthetic_findings_and_three_markers() -> None:
    """Story 3.3 AC-8 item 4: all-three-layer-failure case (the canonical
    Story 3.4 PR-bundle review-section input shape).
    """
    envelope = _minimal_envelope()
    registry = _make_canonical_registry()

    emissions = surface_failed_layers(
        envelope, ["auditor", "blind", "edge"], registry
    )

    assert envelope["failed_layers"] == ["auditor", "blind", "edge"]
    assert len(emissions) == 3
    assert tuple(em.failed_layer for em in emissions) == (
        "auditor",
        "blind",
        "edge",
    )
    meta_findings = [
        f
        for f in envelope["findings"]
        if f.get("meta") == META_REVIEW_COMPLETENESS
    ]
    assert len(meta_findings) == 3
    assert {f["id"] for f in meta_findings} == {
        "review-layer-failed-auditor",
        "review-layer-failed-blind",
        "review-layer-failed-edge",
    }
    # AC-1: surface_failed_layers does NOT mutate envelope["status"]; the
    # all-three-fail → status: blocked pairing is the call-site's
    # responsibility (the test envelope was constructed with status:
    # blocked already; the function preserves it).
    assert envelope["status"] == "blocked"


# --------------------------------------------------------------------------- #
# Registry validation invariant                                               #
# --------------------------------------------------------------------------- #


def test_surface_failed_layers_validates_marker_via_registry() -> None:
    """Story 3.3 AC-8 item 5: registry rejection raises
    UnknownMarkerClass per the substrate seam's existing exception
    type (Pattern 5). When the registry contains the marker, no
    exception is raised.
    """
    envelope_no_marker = _minimal_envelope()
    empty_registry = MarkerClassRegistry(marker_classes=frozenset())

    with pytest.raises(UnknownMarkerClass):
        surface_failed_layers(envelope_no_marker, ["edge"], empty_registry)

    # Atomicity invariant (P1 fix): when UnknownMarkerClass is raised the
    # envelope must be completely unmodified — channel 1 is committed only
    # after all per-layer validations pass.
    assert "failed_layers" not in envelope_no_marker, (
        "channel 1 must not be committed before channels 2+3 are validated"
    )
    assert envelope_no_marker["findings"] == [], (
        "findings must be unmodified after a failed registry validation"
    )

    envelope_canonical = _minimal_envelope()
    canonical_registry = _make_canonical_registry()
    # Should not raise.
    surface_failed_layers(envelope_canonical, ["edge"], canonical_registry)
    assert envelope_canonical["failed_layers"] == ["edge"]


# --------------------------------------------------------------------------- #
# Post-emission schema conformance                                            #
# --------------------------------------------------------------------------- #


def test_surface_failed_layers_post_emission_envelope_validates_against_schema() -> None:
    """Story 3.3 AC-8 item 6: the post-emission envelope round-trips
    through `validate_return_envelope` cleanly — the synthetic
    findings' `meta: review-completeness` value survives validation
    per the AC-2 schema bump ($defs/finding.properties.meta enum
    [review-completeness]).
    """
    envelope = _minimal_envelope()
    registry = _make_canonical_registry()
    surface_failed_layers(envelope, ["auditor", "blind", "edge"], registry)

    result = validate_return_envelope(envelope)
    assert result.valid, result.errors
