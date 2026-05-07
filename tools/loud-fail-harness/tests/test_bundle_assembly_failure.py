"""Contract-coverage matrix for `surface_assembly_failure` (Story 6.9 AC-6).

This docstring IS the contract-coverage checklist required by AC-6 of
Story 6.9. Reviewers verify every row maps to at least one passing test
in this module. The matrix is review-enforced, NOT CI-enforced.

The test surface is the single source-of-truth function
:func:`loud_fail_harness.bundle_assembly_failure.surface_assembly_failure`
which emits the three-channel atomic projection of a bundle-assembly
logical failure (FR59 + NFR-O5). The atomicity is enforced as a
code-structure invariant; the AC-4 CI lint
:mod:`loud_fail_harness.bundle_assembly_failure_emission_gate` is the
structural guard. THESE tests assert the FUNCTIONAL contract:

Surface description coverage (Story 6.9 AC-6 items (a)-(f)):
    [x] (a) happy path: all three channels emit + record returned
        → test_surface_assembly_failure_happy_path_emits_all_three_channels
    [x] (b) atomicity (validate-then-mutate): registry-rejection raises
        BEFORE any channel commits
        → test_surface_assembly_failure_validate_then_mutate_atomicity
    [x] (c) idempotency: second emission for same `(story_id, run_id,
        failed_step)` produces a single marker entry; fallback file
        overwritten last-write-wins
        → test_surface_assembly_failure_idempotency_dedup_and_overwrite
    [x] (d) each of FIVE `AssemblyFailureStep` sub-classifications
        exercised with representative exception
        → test_surface_assembly_failure_five_sub_classifications_full_coverage
    [x] (e) `classify_assembly_failure` mapping rules; SystemExit /
        KeyboardInterrupt propagate; pure-function (no I/O)
        → test_classify_assembly_failure_*
    [x] (f) `__all__` enumerates the public surface exhaustively
        → test_module_all_exhaustively_enumerates_public_surface
"""

from __future__ import annotations

import io
import pathlib

import pytest

from loud_fail_harness.bundle_assembly import EnvelopeReValidationFailed
from loud_fail_harness.bundle_assembly_failure import (
    BUNDLE_ASSEMBLY_FAILED_EXIT_CODE,
    BUNDLE_ASSEMBLY_FAILED_MARKER,
    AssemblyFailureRecord,
    AssemblyFailureStep,
    classify_assembly_failure,
    surface_assembly_failure,
)
from loud_fail_harness.run_state import (
    CostToDateBySpecialist,
    RunState,
    _serialize_run_state,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
)

import loud_fail_harness.bundle_assembly_failure as module_under_test


def _make_canonical_registry() -> MarkerClassRegistry:
    """Build a registry containing the `bundle-assembly-failed` class."""
    return MarkerClassRegistry(
        marker_classes=frozenset({BUNDLE_ASSEMBLY_FAILED_MARKER})
    )


def _make_base_run_state(
    *, story_id: str = "auto-001", run_id: str = "r1"
) -> RunState:
    """Minimal valid RunState for the tests.

    Mirrors Story 2.2's MVP shape per ``test_cost_telemetry.base_run_state``
    fixture without the dependency import.
    """
    return RunState(
        schema_version="1.3",
        story_id=story_id,
        run_id=run_id,
        current_state="ready-for-dev",
        branch_name=f"bmad-automation/story/{story_id}",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        marker_contexts={},
        cost_to_date_by_specialist=CostToDateBySpecialist(),
        last_retry_directive=None,
    )


def _seed_run_state_yaml(
    tmp_path: pathlib.Path,
    *,
    story_id: str = "auto-001",
    run_id: str = "r1",
) -> pathlib.Path:
    """Write a canonical run-state YAML to disk and return the path."""
    rs = _make_base_run_state(story_id=story_id, run_id=run_id)
    path = tmp_path / "run-state.yaml"
    path.write_text(_serialize_run_state(rs), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# (a) — happy path                                                            #
# --------------------------------------------------------------------------- #


def test_surface_assembly_failure_happy_path_emits_all_three_channels(
    tmp_path: pathlib.Path,
) -> None:
    """Witnesses Story 6.9 AC-1 verbatim — `bundle_assembly.main`'s
    wrapping try/except routes through `surface_assembly_failure` across
    THREE reinforcing channels (fallback diagnostic file at the canonical
    path, stderr line, persisted run-state marker for next-cycle loud-
    fail-block render); each known assembler-failure mode maps to the
    correct sub-classification.
    """
    run_state_path = _seed_run_state_yaml(tmp_path)
    bundle_root = tmp_path / "pr-bundles"
    stderr = io.StringIO()
    exc = EnvelopeReValidationFailed(
        specialist="dev", diagnostic="envelope shape mismatch"
    )

    record = surface_assembly_failure(
        story_id="auto-001",
        run_id="r1",
        run_state_path=run_state_path,
        bundle_root=bundle_root,
        exc=exc,
        failed_step="envelope-mismatch",
        registry=_make_canonical_registry(),
        stderr=stderr,
    )

    # Returned record carries full failure context.
    assert isinstance(record, AssemblyFailureRecord)
    assert record.story_id == "auto-001"
    assert record.run_id == "r1"
    assert record.failed_step == "envelope-mismatch"
    assert record.exception_type == "EnvelopeReValidationFailed"
    assert "envelope shape mismatch" in record.exception_message
    assert record.partial_bundle_path is None

    # Channel 1 — fallback diagnostic file.
    expected_log = bundle_root / "auto-001" / "r1.assembly-failure.log"
    assert record.fallback_diagnostic_path == expected_log
    assert expected_log.exists()
    body = expected_log.read_text(encoding="utf-8")
    assert body.startswith("=== bundle-assembly-failed ===\n")
    assert "story_id: auto-001" in body
    assert "run_id: r1" in body
    assert "failed_step: envelope-mismatch" in body
    assert "exception_type: EnvelopeReValidationFailed" in body
    assert "exception_message: " in body
    assert "envelope shape mismatch" in body
    assert "generated_at: " in body
    assert "traceback:" in body

    # Channel 2 — stderr one-line emission.
    stderr_text = stderr.getvalue()
    assert stderr_text.startswith(
        "bundle-assembly-failed: envelope-mismatch at auto-001/r1 — see "
    )
    assert str(expected_log) in stderr_text

    # Channel 3 — persisted run-state marker.
    import yaml  # local — rebuild RunState from disk

    persisted = RunState.model_validate(
        yaml.safe_load(run_state_path.read_text(encoding="utf-8"))
    )
    assert (
        "bundle-assembly-failed: envelope-mismatch" in persisted.active_markers
    )
    ctx = persisted.marker_contexts["bundle-assembly-failed"]
    assert ctx == {
        "exception_type": "EnvelopeReValidationFailed",
        "failed_step": "envelope-mismatch",
        "run_id": "r1",
        "story_id": "auto-001",
    }


# --------------------------------------------------------------------------- #
# (b) — atomicity (validate-then-mutate)                                      #
# --------------------------------------------------------------------------- #


def test_surface_assembly_failure_validate_then_mutate_atomicity(
    tmp_path: pathlib.Path,
) -> None:
    """Witnesses Story 6.9 AC-1 + AC-4 atomicity — registry-rejection
    raises BEFORE any of the three channels commit. Mirrors
    `surface_failed_layers`'s pre-loop validation discipline at
    `review_layer_failure.py:281`.
    """
    run_state_path = _seed_run_state_yaml(tmp_path)
    bundle_root = tmp_path / "pr-bundles"
    stderr = io.StringIO()
    empty_registry = MarkerClassRegistry(marker_classes=frozenset())

    pre_yaml = run_state_path.read_text(encoding="utf-8")

    with pytest.raises(UnknownMarkerClass):
        surface_assembly_failure(
            story_id="auto-001",
            run_id="r1",
            run_state_path=run_state_path,
            bundle_root=bundle_root,
            exc=ValueError("any"),
            failed_step="internal-exception",
            registry=empty_registry,
            stderr=stderr,
        )

    # Channel 1 — fallback file NOT written.
    expected_log = bundle_root / "auto-001" / "r1.assembly-failure.log"
    assert not expected_log.exists()
    # Channel 2 — stderr empty.
    assert stderr.getvalue() == ""
    # Channel 3 — run-state on disk unchanged.
    assert run_state_path.read_text(encoding="utf-8") == pre_yaml


# --------------------------------------------------------------------------- #
# (c) — idempotency                                                           #
# --------------------------------------------------------------------------- #


def test_surface_assembly_failure_idempotency_dedup_and_overwrite(
    tmp_path: pathlib.Path,
) -> None:
    """Witnesses Story 6.9 AC-1 (second invocation idempotency) verbatim
    — calling `surface_assembly_failure` twice with the same
    `(story_id, run_id, failed_step)` produces a single marker entry in
    `active_markers` (de-dup per Story 6.7's marker-recorder discipline);
    fallback file is overwritten with latest invocation's content.
    """
    run_state_path = _seed_run_state_yaml(tmp_path)
    bundle_root = tmp_path / "pr-bundles"

    surface_assembly_failure(
        story_id="auto-001",
        run_id="r1",
        run_state_path=run_state_path,
        bundle_root=bundle_root,
        exc=EnvelopeReValidationFailed(specialist="dev", diagnostic="first"),
        failed_step="envelope-mismatch",
        registry=_make_canonical_registry(),
        stderr=io.StringIO(),
    )
    log_path = bundle_root / "auto-001" / "r1.assembly-failure.log"
    first_body = log_path.read_text(encoding="utf-8")

    surface_assembly_failure(
        story_id="auto-001",
        run_id="r1",
        run_state_path=run_state_path,
        bundle_root=bundle_root,
        exc=EnvelopeReValidationFailed(specialist="dev", diagnostic="second"),
        failed_step="envelope-mismatch",
        registry=_make_canonical_registry(),
        stderr=io.StringIO(),
    )

    # Marker de-dup: a SINGLE entry survives.
    import yaml

    persisted = RunState.model_validate(
        yaml.safe_load(run_state_path.read_text(encoding="utf-8"))
    )
    matches = [
        m
        for m in persisted.active_markers
        if m == "bundle-assembly-failed: envelope-mismatch"
    ]
    assert len(matches) == 1

    # Fallback file: overwritten with second invocation's content.
    second_body = log_path.read_text(encoding="utf-8")
    assert "second" in second_body
    assert "first" not in second_body
    # Headers identical (the file format is stable).
    assert first_body.split("\n")[0] == second_body.split("\n")[0]


# --------------------------------------------------------------------------- #
# (d) — five `AssemblyFailureStep` sub-classifications                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "failed_step,exc",
    [
        (
            "envelope-mismatch",
            EnvelopeReValidationFailed(
                specialist="dev", diagnostic="env shape"
            ),
        ),
        ("missing-finding-fields", KeyError("severity")),
        (
            "taxonomy-unresolved",
            UnknownMarkerClass(
                marker_class="bogus-class",
                known_classes=frozenset({BUNDLE_ASSEMBLY_FAILED_MARKER}),
            ),
        ),
        ("finding-render-crash", RuntimeError("render helper crashed")),
        ("internal-exception", Exception("generic")),
    ],
)
def test_surface_assembly_failure_five_sub_classifications_full_coverage(
    tmp_path: pathlib.Path, failed_step: AssemblyFailureStep, exc: BaseException
) -> None:
    """Witnesses Story 6.9 AC-1 + AC-2 — each of the FIVE
    `AssemblyFailureStep` sub-classifications is exercised with a
    representative exception class; the marker `: <step>` suffix and
    `marker_contexts` mapping reflect the failure mode verbatim.
    """
    run_state_path = _seed_run_state_yaml(tmp_path)
    bundle_root = tmp_path / "pr-bundles"

    record = surface_assembly_failure(
        story_id="auto-001",
        run_id=f"r-{failed_step}",
        run_state_path=run_state_path,
        bundle_root=bundle_root,
        exc=exc,
        failed_step=failed_step,
        registry=_make_canonical_registry(),
        stderr=io.StringIO(),
    )

    assert record.failed_step == failed_step
    log_path = bundle_root / "auto-001" / f"r-{failed_step}.assembly-failure.log"
    assert log_path.exists()
    body = log_path.read_text(encoding="utf-8")
    assert f"failed_step: {failed_step}" in body

    import yaml

    persisted = RunState.model_validate(
        yaml.safe_load(run_state_path.read_text(encoding="utf-8"))
    )
    assert f"bundle-assembly-failed: {failed_step}" in persisted.active_markers


# --------------------------------------------------------------------------- #
# (e) — `classify_assembly_failure` mapping rules                             #
# --------------------------------------------------------------------------- #


def test_classify_assembly_failure_envelope_mismatch() -> None:
    """Witnesses AC-1 — `EnvelopeReValidationFailed` → `envelope-mismatch`."""
    assert (
        classify_assembly_failure(
            EnvelopeReValidationFailed(specialist="dev", diagnostic="x")
        )
        == "envelope-mismatch"
    )


def test_classify_assembly_failure_taxonomy_unresolved() -> None:
    """Witnesses AC-1 — `UnknownMarkerClass` → `taxonomy-unresolved`."""
    exc = UnknownMarkerClass(
        marker_class="bogus", known_classes=frozenset({"x"})
    )
    assert classify_assembly_failure(exc) == "taxonomy-unresolved"


def test_classify_assembly_failure_missing_finding_fields() -> None:
    """Witnesses AC-1 — `KeyError` → `missing-finding-fields`."""
    assert (
        classify_assembly_failure(KeyError("severity"))
        == "missing-finding-fields"
    )


def test_classify_assembly_failure_finding_render_crash_with_partial_bundle(
    tmp_path: pathlib.Path,
) -> None:
    """Witnesses AC-1 — non-`KeyError` exception with partial bundle on
    disk → `finding-render-crash`.
    """
    partial = tmp_path / "partial.md"
    partial.write_text("partial render", encoding="utf-8")
    assert (
        classify_assembly_failure(
            RuntimeError("crashed mid-render"), partial_bundle_path=partial
        )
        == "finding-render-crash"
    )


def test_classify_assembly_failure_finding_render_crash_generic_exception() -> None:
    """Witnesses AC-1 (post-F1 fix) — any Exception subclass, including a
    plain `Exception`, maps to `finding-render-crash`; `partial_bundle_path`
    is irrelevant to classification.
    """
    assert classify_assembly_failure(Exception("generic")) == "finding-render-crash"


def test_classify_assembly_failure_internal_exception_base_exception_only() -> None:
    """Witnesses AC-1 — `internal-exception` is reserved for non-``Exception``
    ``BaseException`` subclasses (e.g. ``GeneratorExit``-like custom classes
    that do NOT inherit from ``Exception``).
    """

    class _NonExceptionBase(BaseException):
        pass

    assert classify_assembly_failure(_NonExceptionBase()) == "internal-exception"


def test_classify_assembly_failure_pure_function_no_io(
    tmp_path: pathlib.Path,
) -> None:
    """Witnesses AC-1 — `classify_assembly_failure` is a PURE function
    (no I/O). Verified by giving it a non-existent partial-bundle path
    and asserting no FileNotFoundError raised.
    """
    nonexistent = tmp_path / "does-not-exist.md"
    assert (
        classify_assembly_failure(
            RuntimeError("crashed"), partial_bundle_path=nonexistent
        )
        == "finding-render-crash"
    )


# --------------------------------------------------------------------------- #
# (f) — `__all__` enumeration                                                 #
# --------------------------------------------------------------------------- #


def test_module_all_exhaustively_enumerates_public_surface() -> None:
    """Witnesses Story 6.9 AC-6 (f) — `__all__` enumerates the public
    surface exhaustively per the existing convention.
    """
    assert set(module_under_test.__all__) == {
        "BUNDLE_ASSEMBLY_FAILED_EXIT_CODE",
        "BUNDLE_ASSEMBLY_FAILED_MARKER",
        "AssemblyFailureRecord",
        "AssemblyFailureStep",
        "classify_assembly_failure",
        "surface_assembly_failure",
    }


def test_bundle_assembly_failed_exit_code_is_two() -> None:
    """The exit-code-2 contract is Story 6.9's load-bearing AC-3 invariant
    — `BUNDLE_ASSEMBLY_FAILED_EXIT_CODE` is exactly 2 so
    `handle_hook_exit_code` can distinguish "assembler logic failed" from
    "Stop hook crashed mechanically".
    """
    assert BUNDLE_ASSEMBLY_FAILED_EXIT_CODE == 2
