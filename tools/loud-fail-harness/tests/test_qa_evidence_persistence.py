"""Contract-coverage matrix for the evidence-persistence + size-budget
+ truncation-marker + sanitization-mechanism substrate (Story 4.12).

Mirrors the test-file shape established by ``test_qa_evidence_tier.py``
(Story 4.8) for the emission-helper + decision-function surface;
extends with the path-construction + run-id-allocation + size-budget-
boundary primitives unique to FR49 / NFR-P6 / NFR-R4 / NFR-S2.

Test enumeration (Story 4.12 AC-8 — ≥ 16 logical tests across eight
categories):

Constant pins:
    1. test_evidence_root_constant_value
    2. test_evidence_truncated_marker_constant_value
    3. test_module_all_exports

Path construction (FR49):
    4. test_compute_evidence_root_returns_pure_posix_path
    5. test_compute_run_dir_concatenates_story_and_run

Run-id format (NFR-R4):
    6. test_allocate_run_id_format
    7. test_allocate_run_id_with_injected_now
    8. test_allocate_run_id_lexicographic_sort

evaluate_size_budget decision branches (NFR-P6):
    9.  test_evaluate_size_budget_accept_under_ceiling
    10. test_evaluate_size_budget_accept_at_ceiling_boundary
    11. test_evaluate_size_budget_truncate_over_ceiling
    12. test_evaluate_size_budget_negative_current_raises_value_error
    13. test_evaluate_size_budget_negative_incoming_raises_value_error
    14. test_evaluate_size_budget_unknown_marker_class_propagates

Pattern-5 atomic-on-failure:
    15. test_surface_evidence_truncated_atomic_on_failure
    16. test_surface_evidence_truncated_happy_path

Marker-taxonomy freshness:
    17. test_how_to_enable_pointer_matches_marker_taxonomy_byte_for_byte

Absence-of-marker structural enforcement (NFR-S2):
    18. test_no_masking_not_configured_marker_class_in_taxonomy

Audit-doc cross-reference:
    19. test_extension_audit_row_present
"""

from __future__ import annotations

import pathlib
import re
from datetime import datetime, timezone
from pathlib import PurePosixPath

import pytest
import yaml

from loud_fail_harness import qa_evidence_persistence
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.qa_evidence_persistence import (
    EVIDENCE_ROOT,
    EVIDENCE_TRUNCATED_MARKER,
    EvidenceTruncatedDiagnosticContext,
    EvidenceTruncatedEmission,
    EvidenceTruncatedEmissionRecord,
    SizeBudgetOutcome,
    _HOW_TO_ENABLE_POINTER,
    allocate_run_id,
    compute_evidence_root,
    compute_run_dir,
    evaluate_size_budget,
    surface_evidence_truncated,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
)


# --------------------------------------------------------------------------- #
# Fixtures (Epic 1 retro Action #1: never call find_repo_root at module top   #
# level — pytest fixtures only).                                              #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def repo_root() -> pathlib.Path:
    """Module-scoped repo-root fixture (Epic 1 retro Action #1)."""
    return find_repo_root()


@pytest.fixture(scope="module")
def marker_taxonomy_path(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "schemas" / "marker-taxonomy.yaml"


@pytest.fixture(scope="module")
def extension_audit_path(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "docs" / "extension-audit.md"


def _make_registry() -> MarkerClassRegistry:
    """Registry containing exactly the ``evidence-truncated`` marker class."""
    return MarkerClassRegistry(
        marker_classes=frozenset({"evidence-truncated"})
    )


def _empty_registry() -> MarkerClassRegistry:
    """Registry with no marker classes (consumed by the atomic-on-failure
    test)."""
    return MarkerClassRegistry(marker_classes=frozenset())


# --------------------------------------------------------------------------- #
# 1. Constant pins                                                            #
# --------------------------------------------------------------------------- #


def test_evidence_root_constant_value() -> None:
    """``EVIDENCE_ROOT`` is the canonical FR49 path-root literal — single
    source of truth for downstream consumers (Story 4.13 wrapper, Story
    7.5 init scaffolding) so they read this constant rather than re-
    typing the literal."""
    assert EVIDENCE_ROOT == "_bmad-output/qa-evidence"


def test_evidence_truncated_marker_constant_value() -> None:
    """``EVIDENCE_TRUNCATED_MARKER`` mirrors the canonical
    ``schemas/marker-taxonomy.yaml`` line 144 ``marker_class`` byte-
    for-byte; THIS module is the FIRST runtime emitter."""
    assert EVIDENCE_TRUNCATED_MARKER == "evidence-truncated"


def test_module_all_exports() -> None:
    """The module's ``__all__`` enumerates every public symbol the
    wrapper-side composition + downstream Story 4.13 / 7.5 consumers
    depend on."""
    expected = {
        "EVIDENCE_ROOT",
        "EVIDENCE_TRUNCATED_MARKER",
        "EvidenceTruncatedDiagnosticContext",
        "EvidenceTruncatedEmission",
        "EvidenceTruncatedEmissionRecord",
        "SizeBudgetOutcome",
        "allocate_run_id",
        "compute_evidence_root",
        "compute_run_dir",
        "evaluate_size_budget",
        "surface_evidence_truncated",
    }
    assert set(qa_evidence_persistence.__all__) == expected


# --------------------------------------------------------------------------- #
# 2. Path construction (FR49)                                                 #
# --------------------------------------------------------------------------- #


def test_compute_evidence_root_returns_pure_posix_path() -> None:
    """``compute_evidence_root("sample-001")`` returns a forward-slash-
    separated PurePosixPath regardless of host OS."""
    result = compute_evidence_root("sample-001")
    assert isinstance(result, PurePosixPath)
    assert str(result) == "_bmad-output/qa-evidence/sample-001"


def test_compute_run_dir_concatenates_story_and_run() -> None:
    """``compute_run_dir("s", "r")`` composes story + run-id under
    EVIDENCE_ROOT — forward-slash-separated regardless of host OS."""
    result = compute_run_dir("s", "r")
    assert isinstance(result, PurePosixPath)
    assert str(result) == "_bmad-output/qa-evidence/s/r"


# --------------------------------------------------------------------------- #
# 3. Run-id format (NFR-R4)                                                   #
# --------------------------------------------------------------------------- #


_RUN_ID_PATTERN = re.compile(r"^\d{8}T\d{6}Z$")


def test_allocate_run_id_format() -> None:
    """Default ``now=None`` resolves to wall-clock UTC; the returned
    string matches ``^\\d{8}T\\d{6}Z$`` (16 chars; uppercase T + Z)."""
    result = allocate_run_id()
    assert isinstance(result, str)
    assert len(result) == 16
    assert _RUN_ID_PATTERN.match(result), (
        f"run_id {result!r} does not match canonical pattern"
    )


def test_allocate_run_id_with_injected_now() -> None:
    """Byte-equality on injected `now` — establishes the format pin
    against an explicit instant (no wall-clock dependence)."""
    instant = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
    assert allocate_run_id(now=instant) == "20260503T120000Z"


def test_allocate_run_id_lexicographic_sort() -> None:
    """Two run-ids produced from successive UTC instants sort
    lexicographically in chronological order — the format is sortable
    as plain strings, satisfying NFR-R4's "practitioner can inspect
    prior runs" inspection ergonomics."""
    earlier = allocate_run_id(
        now=datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
    )
    later = allocate_run_id(
        now=datetime(2026, 5, 3, 13, 0, 0, tzinfo=timezone.utc)
    )
    assert earlier < later
    assert sorted([later, earlier]) == [earlier, later]


# --------------------------------------------------------------------------- #
# 4. evaluate_size_budget decision branches (NFR-P6)                          #
# --------------------------------------------------------------------------- #


def test_evaluate_size_budget_accept_under_ceiling() -> None:
    """Cumulative bytes strictly below the ceiling → ``verdict="accept"``,
    no marker emitted, no registry interaction required for success."""
    registry = _make_registry()
    outcome = evaluate_size_budget(
        story_id="sample-001",
        run_id="20260503T120000Z",
        current_total_bytes=0,
        incoming_write_bytes=100,
        max_size_bytes=200,
        registry=registry,
    )
    assert isinstance(outcome, SizeBudgetOutcome)
    assert outcome.verdict == "accept"
    assert outcome.marker_record is None


def test_evaluate_size_budget_accept_at_ceiling_boundary() -> None:
    """Boundary at exact equality is the LAST acceptable write — verdict
    is ``accept`` (epics.md line 2163-2166: the next byte tips into
    truncate)."""
    registry = _make_registry()
    outcome = evaluate_size_budget(
        story_id="sample-001",
        run_id="20260503T120000Z",
        current_total_bytes=100,
        incoming_write_bytes=100,
        max_size_bytes=200,
        registry=registry,
    )
    assert outcome.verdict == "accept"
    assert outcome.marker_record is None


def test_evaluate_size_budget_truncate_over_ceiling() -> None:
    """Cumulative bytes strictly above the ceiling → ``verdict="truncate"``,
    a populated ``EvidenceTruncatedEmissionRecord`` is co-carried with
    the canonical marker_class + diagnostic context."""
    registry = _make_registry()
    outcome = evaluate_size_budget(
        story_id="sample-001",
        run_id="20260503T120000Z",
        current_total_bytes=100,
        incoming_write_bytes=101,
        max_size_bytes=200,
        registry=registry,
    )
    assert outcome.verdict == "truncate"
    assert outcome.marker_record is not None
    assert outcome.marker_record.marker_class == "evidence-truncated"
    assert (
        outcome.marker_record.diagnostic_context.story_id == "sample-001"
    )
    assert (
        outcome.marker_record.diagnostic_context.run_id == "20260503T120000Z"
    )
    assert outcome.marker_record.diagnostic_context.how_to_enable_pointer
    assert (
        outcome.marker_record.diagnostic_context.how_to_enable_pointer
        == _HOW_TO_ENABLE_POINTER
    )


def test_evaluate_size_budget_negative_current_raises_value_error() -> None:
    """Negative ``current_total_bytes`` violates the named-invariant
    Pattern-5 guard → ``ValueError``."""
    registry = _make_registry()
    with pytest.raises(ValueError, match=">= 0"):
        evaluate_size_budget(
            story_id="sample-001",
            run_id="20260503T120000Z",
            current_total_bytes=-1,
            incoming_write_bytes=10,
            max_size_bytes=200,
            registry=registry,
        )


def test_evaluate_size_budget_negative_incoming_raises_value_error() -> None:
    """Negative ``incoming_write_bytes`` violates the named-invariant
    Pattern-5 guard → ``ValueError``."""
    registry = _make_registry()
    with pytest.raises(ValueError, match=">= 0"):
        evaluate_size_budget(
            story_id="sample-001",
            run_id="20260503T120000Z",
            current_total_bytes=10,
            incoming_write_bytes=-1,
            max_size_bytes=200,
            registry=registry,
        )


def test_evaluate_size_budget_unknown_marker_class_propagates() -> None:
    """On the truncate branch ``UnknownMarkerClass`` propagates UNCHANGED
    per Pattern 5; the accept branch does NOT touch the registry so an
    incomplete registry is harmless on accept."""
    incomplete = _empty_registry()

    accept_outcome = evaluate_size_budget(
        story_id="sample-001",
        run_id="20260503T120000Z",
        current_total_bytes=0,
        incoming_write_bytes=10,
        max_size_bytes=200,
        registry=incomplete,
    )
    assert accept_outcome.verdict == "accept"
    assert accept_outcome.marker_record is None

    with pytest.raises(UnknownMarkerClass):
        evaluate_size_budget(
            story_id="sample-001",
            run_id="20260503T120000Z",
            current_total_bytes=200,
            incoming_write_bytes=1,
            max_size_bytes=200,
            registry=incomplete,
        )


# --------------------------------------------------------------------------- #
# 5. Pattern-5 atomic-on-failure for surface_evidence_truncated               #
# --------------------------------------------------------------------------- #


def test_surface_evidence_truncated_atomic_on_failure() -> None:
    """Registry rejection raises ``UnknownMarkerClass`` BEFORE any
    partial state is constructed (Pattern 5; mirrors Story 4.8's
    ``test_surface_tier_3_not_configured_atomic_on_failure``)."""
    with pytest.raises(UnknownMarkerClass):
        surface_evidence_truncated(
            story_id="sample-001",
            run_id="20260503T120000Z",
            registry=_empty_registry(),
        )


def test_surface_evidence_truncated_happy_path() -> None:
    """Happy path: the emission carries the canonical marker_class +
    story_id + run_id + the canonical how_to_enable_pointer."""
    emission = surface_evidence_truncated(
        story_id="sample-001",
        run_id="20260503T120000Z",
        registry=_make_registry(),
    )
    assert isinstance(emission, EvidenceTruncatedEmission)
    assert isinstance(emission.marker_record, EvidenceTruncatedEmissionRecord)
    assert isinstance(
        emission.diagnostic_context, EvidenceTruncatedDiagnosticContext
    )
    assert emission.marker_record.marker_class == "evidence-truncated"
    assert emission.diagnostic_context.story_id == "sample-001"
    assert emission.diagnostic_context.run_id == "20260503T120000Z"
    assert (
        emission.diagnostic_context.how_to_enable_pointer
        == _HOW_TO_ENABLE_POINTER
    )
    # Co-exposed: the marker_record carries the same diagnostic_context
    # object reference.
    assert (
        emission.marker_record.diagnostic_context
        == emission.diagnostic_context
    )


# --------------------------------------------------------------------------- #
# 6. Marker-taxonomy freshness                                                #
# --------------------------------------------------------------------------- #


def test_how_to_enable_pointer_matches_marker_taxonomy_byte_for_byte(
    marker_taxonomy_path: pathlib.Path,
) -> None:
    """Freshness guard: ``_HOW_TO_ENABLE_POINTER`` byte-equals the YAML's
    ``diagnostic_pointer`` value for the ``evidence-truncated`` entry.
    Whitespace-normalized comparison (both sides stripped) — fails LOUDLY
    if the taxonomy is edited without updating the substrate constant.
    Mirrors Story 4.8's freshness-test pattern.
    """
    taxonomy = yaml.safe_load(
        marker_taxonomy_path.read_text(encoding="utf-8")
    )
    entries = taxonomy["markers"]
    matches = [e for e in entries if e["marker_class"] == "evidence-truncated"]
    assert len(matches) == 1, (
        "expected exactly one 'evidence-truncated' entry in marker-taxonomy.yaml; "
        f"found {len(matches)}"
    )
    target = matches[0]
    yaml_pointer = target["diagnostic_pointer"]
    assert yaml_pointer == _HOW_TO_ENABLE_POINTER, (
        "evidence-truncated diagnostic_pointer drifted: marker-taxonomy.yaml "
        "and qa_evidence_persistence._HOW_TO_ENABLE_POINTER are out of sync"
    )


# --------------------------------------------------------------------------- #
# 7. Absence-of-marker structural enforcement (NFR-S2)                        #
# --------------------------------------------------------------------------- #


def test_no_masking_not_configured_marker_class_in_taxonomy(
    marker_taxonomy_path: pathlib.Path,
) -> None:
    """The verbatim epic AC at ``epics.md`` line 2175 forbids a
    ``masking-not-configured`` marker class — the absence is the
    structural enforcement of NFR-S2's "Automator does not auto-scrub"
    doctrine. THIS test catches an accidental future addition to the
    taxonomy."""
    taxonomy = yaml.safe_load(
        marker_taxonomy_path.read_text(encoding="utf-8")
    )
    classes = {e["marker_class"] for e in taxonomy["markers"]}
    assert "masking-not-configured" not in classes, (
        "marker-taxonomy.yaml gained a `masking-not-configured` class — this "
        "violates NFR-S2's absence-of-marker doctrine (epics.md line 2175); "
        "emitting a marker on missing `masked_selectors` would constitute "
        "auto-scrubbing-by-shame"
    )


# --------------------------------------------------------------------------- #
# 8. Audit-doc cross-reference                                                #
# --------------------------------------------------------------------------- #


def test_extension_audit_row_present(extension_audit_path: pathlib.Path) -> None:
    """The Story 4.12 row appended to ``docs/extension-audit.md`` per
    AC-5 is reachable by substring; this is the human-readable surface
    + the structural-non-emission's audit witness."""
    text = extension_audit_path.read_text(encoding="utf-8")
    assert "qa_evidence_persistence" in text
    assert "non-emission of `masking-not-configured`" in text
    # The doctrine-quote anchor (verbatim from epics.md line 2175):
    assert "auto-scrubbing-by-shame" in text
    # The NFR-S2 verbatim anchor:
    assert "the Automator provides the masking mechanism, not the policy" in text


# --------------------------------------------------------------------------- #
# 9. New guard tests (review findings)                                        #
# --------------------------------------------------------------------------- #


def test_evaluate_size_budget_zero_max_size_bytes_raises_value_error() -> None:
    """max_size_bytes=0 is not a valid ceiling — raises ValueError with a
    config-pointing message (Pattern-5 named-invariant guard)."""
    registry = _make_registry()
    with pytest.raises(ValueError, match="max_evidence_size_mb"):
        evaluate_size_budget(
            story_id="sample-001",
            run_id="20260503T120000Z",
            current_total_bytes=0,
            incoming_write_bytes=0,
            max_size_bytes=0,
            registry=registry,
        )


def test_evaluate_size_budget_negative_max_size_bytes_raises_value_error() -> None:
    """Negative max_size_bytes raises ValueError with a config-pointing
    message — catches misconfigured max_evidence_size_mb values."""
    registry = _make_registry()
    with pytest.raises(ValueError, match="max_evidence_size_mb"):
        evaluate_size_budget(
            story_id="sample-001",
            run_id="20260503T120000Z",
            current_total_bytes=0,
            incoming_write_bytes=10,
            max_size_bytes=-1,
            registry=registry,
        )


def test_allocate_run_id_naive_datetime_raises_value_error() -> None:
    """Timezone-naive datetime raises ValueError — prevents false UTC stamp
    (the Z suffix is only accurate for UTC-aware instants)."""
    naive = datetime(2026, 5, 3, 12, 0, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        allocate_run_id(now=naive)


def test_allocate_run_id_non_utc_aware_normalizes_to_utc() -> None:
    """A timezone-aware non-UTC datetime is normalized to UTC before
    formatting — the Z suffix is always accurate."""
    from datetime import timedelta

    utc_plus_5 = timezone(timedelta(hours=5))
    # 17:00 UTC+5 == 12:00 UTC
    non_utc = datetime(2026, 5, 3, 17, 0, 0, tzinfo=utc_plus_5)
    result = allocate_run_id(now=non_utc)
    assert result == "20260503T120000Z"


def test_compute_evidence_root_traversal_raises_value_error() -> None:
    """story_id containing '..' path traversal segments raises ValueError —
    prevents escaping the _bmad-output/qa-evidence/ root."""
    with pytest.raises(ValueError, match="path traversal"):
        compute_evidence_root("../outside")


def test_compute_run_dir_traversal_raises_value_error() -> None:
    """run_id containing '..' path traversal segments raises ValueError —
    prevents escaping the story-scoped evidence directory."""
    with pytest.raises(ValueError, match="path traversal"):
        compute_run_dir("sample-001", "../escape")


def test_size_budget_outcome_rejects_accept_with_marker_record() -> None:
    """SizeBudgetOutcome model_validator rejects verdict='accept' paired
    with a non-None marker_record — enforces the discriminated-union
    invariant at construction time."""
    registry = _make_registry()
    emission = surface_evidence_truncated(
        story_id="sample-001",
        run_id="20260503T120000Z",
        registry=registry,
    )
    with pytest.raises(ValueError, match="verdict='accept' requires marker_record=None"):
        SizeBudgetOutcome(verdict="accept", marker_record=emission.marker_record)


def test_size_budget_outcome_rejects_truncate_without_marker_record() -> None:
    """SizeBudgetOutcome model_validator rejects verdict='truncate' paired
    with marker_record=None — enforces the discriminated-union invariant
    at construction time."""
    with pytest.raises(ValueError, match="verdict='truncate' requires"):
        SizeBudgetOutcome(verdict="truncate", marker_record=None)
