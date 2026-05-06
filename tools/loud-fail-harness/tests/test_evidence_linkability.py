"""Story 6.6 — bundle-render-time evidence-trace linkability validator tests.

Witnesses NFR-O7 verbatim per ``prd.md:986`` ("Every ``evidence_refs``
entry resolves to a real artifact or emits a dangling-ref loud-fail
marker") + the verbatim Story 6.6 ACs at ``epics.md`` lines 2711-2737.

Each test docstring cites the specific AC (or sub-claim) it witnesses
verbatim per Pattern 5's named-invariant convention (precedent: every
test in :mod:`tests.test_cost_streaming` /
:mod:`tests.test_cost_telemetry` / :mod:`tests.test_retry_history`).
"""

from __future__ import annotations

import pathlib

import pytest

from loud_fail_harness.evidence_linkability import (
    DANGLING_EVIDENCE_REF_MARKER,
    DanglingEvidenceRef,
    EvidenceLinkabilityResult,
    QA_EVIDENCE_SUB_CLASSIFICATION,
    RETRY_HISTORY_SUB_CLASSIFICATION,
    compute_dangling_evidence_marker_classifications,
    detect_dangling_qa_evidence_refs,
    detect_dangling_retry_history_refs,
    format_dangling_inline_marker,
    validate_evidence_linkability_at_render,
)
from loud_fail_harness.exceptions import EvidenceLinkabilityInvariantError
from loud_fail_harness.run_state import RetryAttempt


# --------------------------------------------------------------------------- #
# (a) DanglingEvidenceRef source-vs-fields invariant                          #
# --------------------------------------------------------------------------- #


def test_qa_evidence_source_with_none_ac_id_raises() -> None:
    """AC-1: source=='qa-evidence' requires ac_id non-None — Pattern 5
    named-invariant ``source-vs-fields-mismatch``."""
    with pytest.raises(EvidenceLinkabilityInvariantError) as excinfo:
        DanglingEvidenceRef(
            source="qa-evidence",
            path="_bmad-output/qa-evidence/foo/bar.log",
            ac_id=None,
            round_id=None,
            retry_attempt=None,
        )
    assert "source-vs-fields-mismatch" in str(excinfo.value)
    assert "qa-evidence" in str(excinfo.value)


def test_qa_evidence_source_with_round_id_set_raises() -> None:
    """AC-1: source=='qa-evidence' requires round_id is None."""
    with pytest.raises(EvidenceLinkabilityInvariantError) as excinfo:
        DanglingEvidenceRef(
            source="qa-evidence",
            path="path",
            ac_id="AC-1",
            round_id="round-01",
            retry_attempt=None,
        )
    assert "source-vs-fields-mismatch" in str(excinfo.value)
    assert "round_id" in str(excinfo.value)


def test_qa_evidence_source_with_retry_attempt_set_raises() -> None:
    """AC-1: source=='qa-evidence' requires retry_attempt is None."""
    with pytest.raises(EvidenceLinkabilityInvariantError):
        DanglingEvidenceRef(
            source="qa-evidence",
            path="path",
            ac_id="AC-1",
            round_id=None,
            retry_attempt=2,
        )


def test_retry_history_source_with_ac_id_set_raises() -> None:
    """AC-1: source=='retry-history' requires ac_id is None."""
    with pytest.raises(EvidenceLinkabilityInvariantError):
        DanglingEvidenceRef(
            source="retry-history",
            path="path",
            ac_id="AC-1",
            round_id="round-01",
            retry_attempt=1,
        )


def test_retry_history_source_with_none_round_id_raises() -> None:
    """AC-1: source=='retry-history' requires round_id non-None."""
    with pytest.raises(EvidenceLinkabilityInvariantError):
        DanglingEvidenceRef(
            source="retry-history",
            path="path",
            ac_id=None,
            round_id=None,
            retry_attempt=1,
        )


def test_retry_history_source_with_none_retry_attempt_raises() -> None:
    """AC-1: source=='retry-history' requires retry_attempt non-None."""
    with pytest.raises(EvidenceLinkabilityInvariantError):
        DanglingEvidenceRef(
            source="retry-history",
            path="path",
            ac_id=None,
            round_id="round-01",
            retry_attempt=None,
        )


def test_qa_evidence_well_formed_constructs_cleanly() -> None:
    """AC-1: well-formed qa-evidence DanglingEvidenceRef constructs."""
    ref = DanglingEvidenceRef(
        source="qa-evidence",
        path="_bmad-output/qa-evidence/foo/bar.log",
        ac_id="AC-1",
        round_id=None,
        retry_attempt=None,
    )
    assert ref.source == "qa-evidence"
    assert ref.ac_id == "AC-1"
    assert ref.path == "_bmad-output/qa-evidence/foo/bar.log"


def test_retry_history_well_formed_constructs_cleanly() -> None:
    """AC-1: well-formed retry-history DanglingEvidenceRef constructs."""
    ref = DanglingEvidenceRef(
        source="retry-history",
        path="_bmad-output/retry-history/foo/round-01.yaml",
        ac_id=None,
        round_id="round-01",
        retry_attempt=1,
    )
    assert ref.source == "retry-history"
    assert ref.round_id == "round-01"
    assert ref.retry_attempt == 1


# --------------------------------------------------------------------------- #
# (b) detect_dangling_qa_evidence_refs                                        #
# --------------------------------------------------------------------------- #


def test_detect_qa_empty_input_returns_empty(tmp_path: pathlib.Path) -> None:
    """AC-1: empty ac_results → empty tuple."""
    result = detect_dangling_qa_evidence_refs(
        ac_results=[], repo_root=tmp_path
    )
    assert result == ()


def test_detect_qa_clean_refs_returns_empty(tmp_path: pathlib.Path) -> None:
    """AC-1: clean evidence_refs (file exists) → empty tuple."""
    (tmp_path / "evidence.log").write_text("ok\n", encoding="utf-8")
    ac_results = [
        {
            "ac_id": "AC-1",
            "evidence_refs": [
                {"path": "evidence.log", "tier": "tier-1-mechanical"}
            ],
        }
    ]
    result = detect_dangling_qa_evidence_refs(
        ac_results=ac_results, repo_root=tmp_path
    )
    assert result == ()


def test_detect_qa_one_missing_ref_returns_one_dangling(
    tmp_path: pathlib.Path,
) -> None:
    """AC-1: one missing ref → one DanglingEvidenceRef carrying source +
    ac_id + path."""
    ac_results = [
        {
            "ac_id": "AC-1",
            "evidence_refs": [
                {"path": "missing.log", "tier": "tier-1-mechanical"}
            ],
        }
    ]
    result = detect_dangling_qa_evidence_refs(
        ac_results=ac_results, repo_root=tmp_path
    )
    assert len(result) == 1
    assert result[0].source == "qa-evidence"
    assert result[0].ac_id == "AC-1"
    assert result[0].path == "missing.log"
    assert result[0].round_id is None
    assert result[0].retry_attempt is None


def test_detect_qa_preserves_input_order(tmp_path: pathlib.Path) -> None:
    """AC-1: result preserves AC-order × ref-order across multi-AC input."""
    (tmp_path / "ac1-clean.log").write_text("ok\n", encoding="utf-8")
    (tmp_path / "ac2-clean.log").write_text("ok\n", encoding="utf-8")
    ac_results = [
        {
            "ac_id": "AC-1",
            "evidence_refs": [
                {"path": "ac1-clean.log"},
                {"path": "ac1-missing-a.log"},
                {"path": "ac1-missing-b.log"},
            ],
        },
        {
            "ac_id": "AC-2",
            "evidence_refs": [
                {"path": "ac2-missing.log"},
                {"path": "ac2-clean.log"},
            ],
        },
    ]
    result = detect_dangling_qa_evidence_refs(
        ac_results=ac_results, repo_root=tmp_path
    )
    paths = [ref.path for ref in result]
    assert paths == [
        "ac1-missing-a.log",
        "ac1-missing-b.log",
        "ac2-missing.log",
    ]
    assert [ref.ac_id for ref in result] == ["AC-1", "AC-1", "AC-2"]


def test_detect_qa_handles_string_evidence_refs_per_story_4_8_shim(
    tmp_path: pathlib.Path,
) -> None:
    """AC-1: Story 4.7 / 4.8 transitive shim — evidence_refs items can
    be plain strings (pre-Story-4.8 shape) per
    ``_render_per_ac_section`` shim convention."""
    ac_results = [
        {
            "ac_id": "AC-1",
            "evidence_refs": ["missing-string-form.log"],
        }
    ]
    result = detect_dangling_qa_evidence_refs(
        ac_results=ac_results, repo_root=tmp_path
    )
    assert len(result) == 1
    assert result[0].path == "missing-string-form.log"


# --------------------------------------------------------------------------- #
# (c) detect_dangling_retry_history_refs                                      #
# --------------------------------------------------------------------------- #


def test_detect_retry_empty_input_returns_empty(
    tmp_path: pathlib.Path,
) -> None:
    """AC-1: empty retry_history → empty tuple."""
    result = detect_dangling_retry_history_refs(
        retry_history=[], repo_root=tmp_path
    )
    assert result == ()


def test_detect_retry_pre_thickened_entries_skipped(
    tmp_path: pathlib.Path,
) -> None:
    """AC-1: pre-Story-5.5 entries (no path / round_id) silently
    skipped per the
    ``bundle_assembly_escalation._retry_attempt_ref_payload`` skip-
    criterion."""
    # Pydantic RetryAttempt MVP shape (round_id + path None).
    pre_thick = RetryAttempt(retry_attempt=1, retry_reason="MVP")
    result = detect_dangling_retry_history_refs(
        retry_history=[pre_thick], repo_root=tmp_path
    )
    assert result == ()


def test_detect_retry_thickened_clean_returns_empty(
    tmp_path: pathlib.Path,
) -> None:
    """AC-1: thickened entries with clean paths → empty tuple."""
    artifact_path = (
        tmp_path / "_bmad-output" / "retry-history" / "foo" / "round-01.yaml"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("dummy: ok\n", encoding="utf-8")
    rel_path = "_bmad-output/retry-history/foo/round-01.yaml"
    thick = RetryAttempt(
        retry_attempt=1,
        retry_reason="thickened",
        round_id="round-01",
        path=rel_path,
    )
    result = detect_dangling_retry_history_refs(
        retry_history=[thick], repo_root=tmp_path
    )
    assert result == ()


def test_detect_retry_thickened_missing_returns_one_dangling(
    tmp_path: pathlib.Path,
) -> None:
    """AC-1: thickened entries with missing paths → one
    DanglingEvidenceRef carrying source='retry-history' + round_id +
    retry_attempt."""
    rel_path = "_bmad-output/retry-history/foo/round-01.yaml"
    thick = RetryAttempt(
        retry_attempt=2,
        retry_reason="dangling round",
        round_id="round-01",
        path=rel_path,
    )
    result = detect_dangling_retry_history_refs(
        retry_history=[thick], repo_root=tmp_path
    )
    assert len(result) == 1
    assert result[0].source == "retry-history"
    assert result[0].round_id == "round-01"
    assert result[0].retry_attempt == 2
    assert result[0].path == rel_path
    assert result[0].ac_id is None


def test_detect_retry_accepts_dict_entries(tmp_path: pathlib.Path) -> None:
    """AC-1: helper accepts BOTH RetryAttempt models AND raw dict
    mappings (escalation-bundle context shape)."""
    rel_path = "_bmad-output/retry-history/foo/round-02.yaml"
    raw = {
        "retry_attempt": 3,
        "retry_reason": "from dict",
        "round_id": "round-02",
        "path": rel_path,
    }
    result = detect_dangling_retry_history_refs(
        retry_history=[raw], repo_root=tmp_path
    )
    assert len(result) == 1
    assert result[0].source == "retry-history"
    assert result[0].round_id == "round-02"


# --------------------------------------------------------------------------- #
# (d) compute_dangling_evidence_marker_classifications                        #
# --------------------------------------------------------------------------- #


def test_classification_empty_input_empty_tuple() -> None:
    """AC-2: empty input → empty tuple."""
    assert compute_dangling_evidence_marker_classifications([]) == ()


def test_classification_qa_evidence_only() -> None:
    """AC-2: one qa-evidence dangling → one
    `dangling-evidence-ref: qa-evidence` marker classification."""
    refs = (
        DanglingEvidenceRef(
            source="qa-evidence",
            path="p",
            ac_id="AC-1",
            round_id=None,
            retry_attempt=None,
        ),
    )
    result = compute_dangling_evidence_marker_classifications(refs)
    assert result == ("dangling-evidence-ref: qa-evidence",)


def test_classification_retry_history_only() -> None:
    """AC-2: one retry-history dangling → one
    `dangling-evidence-ref: retry-history` marker classification."""
    refs = (
        DanglingEvidenceRef(
            source="retry-history",
            path="p",
            ac_id=None,
            round_id="round-01",
            retry_attempt=1,
        ),
    )
    result = compute_dangling_evidence_marker_classifications(refs)
    assert result == ("dangling-evidence-ref: retry-history",)


def test_classification_both_in_alphabetical_order() -> None:
    """AC-3: both qa-evidence AND retry-history dangling → both
    markers in alphabetical order (qa-evidence first)."""
    refs = (
        DanglingEvidenceRef(
            source="retry-history",
            path="p1",
            ac_id=None,
            round_id="round-01",
            retry_attempt=1,
        ),
        DanglingEvidenceRef(
            source="qa-evidence",
            path="p2",
            ac_id="AC-1",
            round_id=None,
            retry_attempt=None,
        ),
    )
    result = compute_dangling_evidence_marker_classifications(refs)
    assert result == (
        "dangling-evidence-ref: qa-evidence",
        "dangling-evidence-ref: retry-history",
    )


def test_classification_one_marker_per_source_class_no_duplicates() -> None:
    """AC-2: ONE marker per source-class regardless of how many
    individual refs dangle within that class."""
    refs = tuple(
        DanglingEvidenceRef(
            source="qa-evidence",
            path=f"p{i}",
            ac_id=f"AC-{i}",
            round_id=None,
            retry_attempt=None,
        )
        for i in range(1, 4)
    )
    result = compute_dangling_evidence_marker_classifications(refs)
    assert result == ("dangling-evidence-ref: qa-evidence",)


# --------------------------------------------------------------------------- #
# (e) format_dangling_inline_marker                                           #
# --------------------------------------------------------------------------- #


def test_inline_marker_format_qa_evidence_byte_stable() -> None:
    """AC-1: inline-rendering helper is byte-stable; format carries
    the literal substring '⚠️ dangling-evidence-ref' + sub-classification +
    path verbatim."""
    ref = DanglingEvidenceRef(
        source="qa-evidence",
        path="_bmad-output/qa-evidence/sample/run/file.log",
        ac_id="AC-1",
        round_id=None,
        retry_attempt=None,
    )
    rendered = format_dangling_inline_marker(ref=ref)
    assert "⚠️ dangling-evidence-ref" in rendered
    assert "qa-evidence" in rendered
    assert "regenerate the evidence OR fix the reference" in rendered
    assert "_bmad-output/qa-evidence/sample/run/file.log" in rendered
    # idempotent
    assert format_dangling_inline_marker(ref=ref) == rendered


def test_inline_marker_format_retry_history() -> None:
    """AC-1: inline-rendering for retry-history carries the
    sub-classification 'retry-history'."""
    ref = DanglingEvidenceRef(
        source="retry-history",
        path="_bmad-output/retry-history/x/round-01.yaml",
        ac_id=None,
        round_id="round-01",
        retry_attempt=1,
    )
    rendered = format_dangling_inline_marker(ref=ref)
    assert "⚠️ dangling-evidence-ref" in rendered
    assert "retry-history" in rendered


# --------------------------------------------------------------------------- #
# (f) validate_evidence_linkability_at_render                                 #
# --------------------------------------------------------------------------- #


def test_validate_happy_path_empty_result(tmp_path: pathlib.Path) -> None:
    """AC-1: no dangling → empty dangling_refs + empty
    marker_classifications_to_append + empty partitions."""
    result = validate_evidence_linkability_at_render(
        ac_results=[], retry_history=[], repo_root=tmp_path
    )
    assert isinstance(result, EvidenceLinkabilityResult)
    assert result.dangling_refs == ()
    assert result.marker_classifications_to_append == ()
    assert result.qa_evidence_dangling == ()
    assert result.retry_history_dangling == ()


def test_validate_qa_only_dangling_partition(tmp_path: pathlib.Path) -> None:
    """AC-2: QA-only dangling → result carries qa-evidence partition;
    retry-history partition is empty."""
    ac_results = [
        {
            "ac_id": "AC-1",
            "evidence_refs": [{"path": "missing.log"}],
        }
    ]
    result = validate_evidence_linkability_at_render(
        ac_results=ac_results, retry_history=[], repo_root=tmp_path
    )
    assert len(result.qa_evidence_dangling) == 1
    assert result.retry_history_dangling == ()
    assert result.marker_classifications_to_append == (
        "dangling-evidence-ref: qa-evidence",
    )


def test_validate_retry_only_dangling_partition(
    tmp_path: pathlib.Path,
) -> None:
    """AC-2: retry-history-only dangling → result carries
    retry-history partition; qa-evidence partition is empty."""
    thick = RetryAttempt(
        retry_attempt=1,
        retry_reason="r",
        round_id="round-01",
        path="_bmad-output/retry-history/x/round-01.yaml",
    )
    result = validate_evidence_linkability_at_render(
        ac_results=[], retry_history=[thick], repo_root=tmp_path
    )
    assert result.qa_evidence_dangling == ()
    assert len(result.retry_history_dangling) == 1
    assert result.marker_classifications_to_append == (
        "dangling-evidence-ref: retry-history",
    )


def test_validate_both_partitions_alphabetical_order(
    tmp_path: pathlib.Path,
) -> None:
    """AC-3: both partitions populated AND
    marker_classifications_to_append in alphabetical order
    (qa-evidence first)."""
    ac_results = [
        {
            "ac_id": "AC-1",
            "evidence_refs": [{"path": "missing-qa.log"}],
        }
    ]
    thick = RetryAttempt(
        retry_attempt=1,
        retry_reason="r",
        round_id="round-01",
        path="_bmad-output/retry-history/x/round-01.yaml",
    )
    result = validate_evidence_linkability_at_render(
        ac_results=ac_results, retry_history=[thick], repo_root=tmp_path
    )
    assert len(result.qa_evidence_dangling) == 1
    assert len(result.retry_history_dangling) == 1
    assert result.marker_classifications_to_append == (
        "dangling-evidence-ref: qa-evidence",
        "dangling-evidence-ref: retry-history",
    )
    # dangling_refs is qa-evidence-first then retry-history.
    assert result.dangling_refs[0].source == "qa-evidence"
    assert result.dangling_refs[1].source == "retry-history"


def test_validate_idempotent_byte_stable(tmp_path: pathlib.Path) -> None:
    """AC-1: idempotent + byte-stable — second call with same inputs
    returns equal EvidenceLinkabilityResult."""
    ac_results = [
        {
            "ac_id": "AC-1",
            "evidence_refs": [{"path": "missing.log"}],
        }
    ]
    first = validate_evidence_linkability_at_render(
        ac_results=ac_results, retry_history=[], repo_root=tmp_path
    )
    second = validate_evidence_linkability_at_render(
        ac_results=ac_results, retry_history=[], repo_root=tmp_path
    )
    assert first == second


# --------------------------------------------------------------------------- #
# Module-surface invariants                                                    #
# --------------------------------------------------------------------------- #


def test_module_constants_exposed_in_all() -> None:
    """AC-7 surface boundedness — DANGLING_EVIDENCE_REF_MARKER and the
    sub-classification constants are exposed via __all__."""
    from loud_fail_harness import evidence_linkability

    assert "DANGLING_EVIDENCE_REF_MARKER" in evidence_linkability.__all__
    assert "QA_EVIDENCE_SUB_CLASSIFICATION" in evidence_linkability.__all__
    assert "RETRY_HISTORY_SUB_CLASSIFICATION" in evidence_linkability.__all__


def test_marker_constant_matches_retry_history_source_of_truth() -> None:
    """AC-3: DANGLING_EVIDENCE_REF_MARKER is sourced from retry_history
    per the marker-class-reuse principle (Story 1.11 / Story 5.5).
    """
    from loud_fail_harness import retry_history

    assert (
        DANGLING_EVIDENCE_REF_MARKER
        == retry_history.DANGLING_EVIDENCE_REF_MARKER
    )
    assert DANGLING_EVIDENCE_REF_MARKER == "dangling-evidence-ref"
    assert QA_EVIDENCE_SUB_CLASSIFICATION == "qa-evidence"
    assert RETRY_HISTORY_SUB_CLASSIFICATION == "retry-history"
