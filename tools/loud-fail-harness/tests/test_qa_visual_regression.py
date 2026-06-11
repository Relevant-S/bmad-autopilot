"""Story 19.5 — qa_visual_regression substrate-library coverage.

Exercises the visual-regression delta engine (pixelmatch result parse + per-AC
baseline load/store + mismatched-pixel-ratio delta + threshold compare +
dimension-mismatch fold + mode decision + artifact serialization) and the two
Pattern-5 atomic-on-failure ``surface_visual_regression_*`` emission helpers.

Non-vacuous (Story 24.3 retro): assertions name the EXACT marker classes
(``visual-regression-delta-exceeded`` / ``visual-regression-baseline-missing``)
and exact ratio/mode/count outcomes, never ``len(...) > 0``.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from pydantic import ValidationError

from loud_fail_harness.envelope_validator import (
    find_repo_root,
    load_schema,
    validate_envelope,
)
from loud_fail_harness.qa_visual_regression import (
    BASELINE_FILENAME,
    DEFAULT_DELTA_THRESHOLD,
    VISUAL_REGRESSION_BASELINE_MISSING_MARKER,
    VISUAL_REGRESSION_DELTA_EXCEEDED_MARKER,
    VisualDiffResult,
    VisualRegressionBaselineMissingEmission,
    VisualRegressionDeltaExceededEmission,
    compute_baseline_dir,
    compute_delta,
    decide_visual_regression_mode,
    load_baseline,
    serialize_delta_artifact,
    store_baseline,
    surface_visual_regression_baseline_missing,
    surface_visual_regression_delta_exceeded,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
)

REPO_ROOT = find_repo_root()
SCHEMA_PATH = REPO_ROOT / "schemas" / "envelope.schema.yaml"

#: A minimal byte string whose leading 8 bytes are the PNG signature
#: ``load_baseline`` checks (the trailing bytes are an inert stand-in for the
#: decoded image — the substrate never decodes PNGs; pixelmatch does, in JS).
_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"


def _registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(
        marker_classes=frozenset(
            {
                VISUAL_REGRESSION_DELTA_EXCEEDED_MARKER,
                VISUAL_REGRESSION_BASELINE_MISSING_MARKER,
            }
        )
    )


def _empty_registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(marker_classes=frozenset())


# --------------------------------------------------------------------------- #
# VisualDiffResult — externally-constructed parse model hardening             #
# --------------------------------------------------------------------------- #


def test_visual_diff_result_computes_ratio_and_total() -> None:
    diff = VisualDiffResult(mismatched_pixels=25, width=10, height=10)
    assert diff.total_pixels == 100
    assert diff.ratio == 0.25


def test_visual_diff_result_rejects_mismatched_exceeding_total() -> None:
    with pytest.raises(ValidationError):
        VisualDiffResult(mismatched_pixels=101, width=10, height=10)


@pytest.mark.parametrize("bad", [{"width": 0}, {"height": 0}, {"width": -1}])
def test_visual_diff_result_rejects_nonpositive_dimensions(bad: dict) -> None:
    kwargs = {"mismatched_pixels": 0, "width": 10, "height": 10, **bad}
    with pytest.raises(ValidationError):
        VisualDiffResult(**kwargs)


def test_visual_diff_result_rejects_negative_mismatch() -> None:
    with pytest.raises(ValidationError):
        VisualDiffResult(mismatched_pixels=-1, width=10, height=10)


# --------------------------------------------------------------------------- #
# Baseline path hardening + load/store                                        #
# --------------------------------------------------------------------------- #


def test_compute_baseline_dir_shape() -> None:
    assert str(compute_baseline_dir("19-5", "AC-1")) == (
        "_bmad-output/qa-visual-baseline/19-5/AC-1"
    )


def test_compute_baseline_dir_returns_concrete_path_composable_with_load_baseline(
    tmp_path: pathlib.Path,
) -> None:
    # D1 regression: compute_baseline_dir must return pathlib.Path (not
    # PurePosixPath) so callers can pass its result directly to load_baseline /
    # store_baseline without an AttributeError on .exists() / .mkdir().
    rel = compute_baseline_dir("19-5", "AC-1")
    assert isinstance(rel, pathlib.Path), (
        "compute_baseline_dir must return pathlib.Path, not PurePosixPath"
    )
    # End-to-end composition: root the relative path under tmp_path and verify
    # the full load_baseline(compute_baseline_dir(...)) call chain works.
    baseline_dir = tmp_path / rel
    assert load_baseline(baseline_dir) is None
    store_baseline(baseline_dir, _PNG)
    assert load_baseline(baseline_dir) == baseline_dir / BASELINE_FILENAME


@pytest.mark.parametrize("seg", ["..", "a/b", "a\x00b", "  "])
def test_compute_baseline_dir_rejects_hostile_segments(seg: str) -> None:
    with pytest.raises(ValueError):
        compute_baseline_dir(seg, "AC-1")
    with pytest.raises(ValueError):
        compute_baseline_dir("19-5", seg)


def test_load_baseline_absent_returns_none(tmp_path: pathlib.Path) -> None:
    assert load_baseline(tmp_path / "19-5" / "AC-1") is None


def test_store_then_load_baseline_roundtrip(tmp_path: pathlib.Path) -> None:
    baseline_dir = tmp_path / "19-5" / "AC-1"
    written = store_baseline(baseline_dir, _PNG)
    assert written == baseline_dir / BASELINE_FILENAME
    assert written.read_bytes() == _PNG
    assert load_baseline(baseline_dir) == written


def test_load_baseline_corrupt_non_png_returns_none(tmp_path: pathlib.Path) -> None:
    # A stored file whose leading bytes are NOT the PNG signature is treated as
    # absent → the safe baseline-missing + fresh-anchor path (19.4 F2 lesson).
    baseline_dir = tmp_path / "19-5" / "AC-1"
    store_baseline(baseline_dir, b"not-a-png-at-all")
    assert load_baseline(baseline_dir) is None


# --------------------------------------------------------------------------- #
# compute_delta — mismatched-pixel ratio + threshold                          #
# --------------------------------------------------------------------------- #


def test_compute_delta_ratio_and_exceeded_over_threshold() -> None:
    diff = VisualDiffResult(mismatched_pixels=30, width=10, height=10)
    delta = compute_delta(diff, threshold=0.1)
    assert delta.ratio == 0.3
    assert delta.mismatched_pixels == 30
    assert delta.total_pixels == 100
    assert delta.exceeded is True


def test_compute_delta_within_threshold_not_exceeded() -> None:
    diff = VisualDiffResult(mismatched_pixels=5, width=10, height=10)
    assert compute_delta(diff, threshold=0.1).exceeded is False


def test_compute_delta_threshold_boundary_at_vs_over() -> None:
    diff = VisualDiffResult(mismatched_pixels=10, width=10, height=10)  # ratio 0.1
    # AT the threshold is NOT exceeded (strict >).
    assert compute_delta(diff, threshold=0.1).exceeded is False
    # Just OVER the threshold is exceeded.
    assert compute_delta(diff, threshold=0.09).exceeded is True


def test_compute_delta_default_threshold_zero_any_diff_is_regression() -> None:
    assert DEFAULT_DELTA_THRESHOLD == 0.0
    diff = VisualDiffResult(mismatched_pixels=1, width=10, height=10)
    assert compute_delta(diff).exceeded is True
    clean = VisualDiffResult(mismatched_pixels=0, width=10, height=10)
    assert compute_delta(clean).exceeded is False


def test_compute_delta_rejects_negative_threshold() -> None:
    diff = VisualDiffResult(mismatched_pixels=0, width=10, height=10)
    with pytest.raises(ValueError):
        compute_delta(diff, threshold=-0.1)


def test_compute_delta_rejects_threshold_above_one() -> None:
    # D4 regression: threshold > 1.0 must raise ValueError; a ratio is always
    # in [0.0, 1.0] so a threshold of e.g. 2.0 would silently make exceeded
    # permanently False, disabling all visual-regression-delta-exceeded markers.
    diff = VisualDiffResult(mismatched_pixels=0, width=10, height=10)
    with pytest.raises(ValueError):
        compute_delta(diff, threshold=1.1)
    with pytest.raises(ValueError):
        compute_delta(diff, threshold=2.0)
    # Boundary: exactly 1.0 is valid (ratio == 1.0 means all pixels differ).
    delta = compute_delta(diff, threshold=1.0)
    assert delta.exceeded is False


# --------------------------------------------------------------------------- #
# decide_visual_regression_mode — the three arms                              #
# --------------------------------------------------------------------------- #


def test_decide_mode_no_baseline_is_baseline_missing() -> None:
    diff = VisualDiffResult(mismatched_pixels=0, width=10, height=10)
    decision = decide_visual_regression_mode(
        baseline_present=False, diff=diff, threshold=0.0
    )
    assert decision.mode == "baseline-missing"
    assert decision.delta is None


def test_decide_mode_ratio_over_threshold_is_delta_exceeded() -> None:
    diff = VisualDiffResult(mismatched_pixels=30, width=10, height=10)
    decision = decide_visual_regression_mode(
        baseline_present=True, diff=diff, threshold=0.1
    )
    assert decision.mode == "delta-exceeded"
    assert decision.delta is not None
    assert decision.delta.ratio == 0.3


def test_decide_mode_dimension_mismatch_folds_into_delta_exceeded() -> None:
    # diff=None signals a dimension mismatch (pixelmatch could not run over
    # unequal dimensions) when a baseline IS present.
    decision = decide_visual_regression_mode(
        baseline_present=True, diff=None, threshold=0.0
    )
    assert decision.mode == "delta-exceeded"
    assert decision.delta is None


def test_decide_mode_within_threshold_no_marker() -> None:
    diff = VisualDiffResult(mismatched_pixels=2, width=10, height=10)
    decision = decide_visual_regression_mode(
        baseline_present=True, diff=diff, threshold=0.1
    )
    assert decision.mode == "delta-within-threshold"
    assert decision.delta is not None
    assert decision.delta.exceeded is False


# --------------------------------------------------------------------------- #
# serialize_delta_artifact — ratio branch + dimension-mismatch branch         #
# --------------------------------------------------------------------------- #


def test_serialize_delta_artifact_ratio_branch() -> None:
    diff = VisualDiffResult(mismatched_pixels=30, width=10, height=10)
    text = serialize_delta_artifact(
        diff=diff,
        baseline_width=10,
        baseline_height=10,
        current_width=10,
        current_height=10,
        threshold=0.1,
        diff_image_path="_bmad-output/qa-evidence/19-5/run/diff.png",
    )
    payload = json.loads(text)
    assert payload["dimension_mismatch"] is False
    assert payload["mismatched_pixels"] == 30
    assert payload["total_pixels"] == 100
    assert payload["ratio"] == 0.3
    assert payload["exceeded"] is True
    assert payload["diff_image_path"].endswith("diff.png")


def test_serialize_delta_artifact_dimension_mismatch_branch() -> None:
    text = serialize_delta_artifact(
        diff=None,
        baseline_width=10,
        baseline_height=10,
        current_width=20,
        current_height=10,
    )
    payload = json.loads(text)
    assert payload["dimension_mismatch"] is True
    assert payload["mismatched_pixels"] is None
    assert payload["ratio"] is None
    assert payload["exceeded"] is True
    assert payload["baseline_width"] == 10
    assert payload["current_width"] == 20


def test_serialize_delta_artifact_rejects_diff_with_dimension_mismatch() -> None:
    # D3 regression: passing diff=non-None alongside mismatched dimensions is
    # contradictory — pixelmatch cannot run over unequal dimensions, so the
    # function must reject this combination with ValueError.
    diff = VisualDiffResult(mismatched_pixels=5, width=10, height=10)
    with pytest.raises(ValueError, match="dimensions mismatch"):
        serialize_delta_artifact(
            diff=diff,
            baseline_width=10,
            baseline_height=10,
            current_width=20,
            current_height=10,
        )


# --------------------------------------------------------------------------- #
# Pattern-5 atomic-on-failure emission helpers                                #
# --------------------------------------------------------------------------- #


def test_surface_delta_exceeded_happy_path() -> None:
    emission = surface_visual_regression_delta_exceeded("19-5", "AC-1", _registry())
    assert isinstance(emission, VisualRegressionDeltaExceededEmission)
    assert emission.marker_record.marker_class == "visual-regression-delta-exceeded"
    assert emission.marker_record.ac_id == "AC-1"
    assert emission.diagnostic_context.story_id == "19-5"
    assert emission.diagnostic_context.ac_id == "AC-1"


def test_surface_baseline_missing_happy_path() -> None:
    emission = surface_visual_regression_baseline_missing("19-5", "AC-2", _registry())
    assert isinstance(emission, VisualRegressionBaselineMissingEmission)
    assert emission.marker_record.marker_class == "visual-regression-baseline-missing"
    assert emission.marker_record.ac_id == "AC-2"


def test_surface_delta_exceeded_atomic_on_failure() -> None:
    with pytest.raises(UnknownMarkerClass):
        surface_visual_regression_delta_exceeded("19-5", "AC-1", _empty_registry())


def test_surface_baseline_missing_atomic_on_failure() -> None:
    with pytest.raises(UnknownMarkerClass):
        surface_visual_regression_baseline_missing("19-5", "AC-1", _empty_registry())


# --------------------------------------------------------------------------- #
# End-to-end composition over a real baseline tree                            #
# --------------------------------------------------------------------------- #


def test_end_to_end_first_run_creates_baseline_and_surfaces_missing(
    tmp_path: pathlib.Path,
) -> None:
    registry = _registry()
    baseline_dir = tmp_path / "19-5" / "AC-1"
    assert load_baseline(baseline_dir) is None
    decision = decide_visual_regression_mode(
        baseline_present=False, diff=None, threshold=0.0
    )
    assert decision.mode == "baseline-missing"
    store_baseline(baseline_dir, _PNG)
    emission = surface_visual_regression_baseline_missing("19-5", "AC-1", registry)
    assert emission.marker_record.marker_class == "visual-regression-baseline-missing"
    assert load_baseline(baseline_dir) == baseline_dir / BASELINE_FILENAME


def test_end_to_end_second_run_over_threshold_surfaces_delta_exceeded(
    tmp_path: pathlib.Path,
) -> None:
    registry = _registry()
    baseline_dir = tmp_path / "19-5" / "AC-1"
    store_baseline(baseline_dir, _PNG)
    diff = VisualDiffResult(mismatched_pixels=40, width=10, height=10)
    decision = decide_visual_regression_mode(
        baseline_present=load_baseline(baseline_dir) is not None,
        diff=diff,
        threshold=DEFAULT_DELTA_THRESHOLD,
    )
    assert decision.mode == "delta-exceeded"
    emission = surface_visual_regression_delta_exceeded("19-5", "AC-1", registry)
    assert emission.marker_record.marker_class == "visual-regression-delta-exceeded"


def test_end_to_end_corrupt_baseline_routes_to_baseline_missing(
    tmp_path: pathlib.Path,
) -> None:
    baseline_dir = tmp_path / "19-5" / "AC-1"
    store_baseline(baseline_dir, b"corrupt-not-png")
    # load_baseline returns None on a corrupt file → the safe baseline-missing path.
    assert load_baseline(baseline_dir) is None
    decision = decide_visual_regression_mode(
        baseline_present=False, diff=None, threshold=0.0
    )
    assert decision.mode == "baseline-missing"


# --------------------------------------------------------------------------- #
# Envelope byte-mirror: emission records validate as visual_regression_emissions #
# --------------------------------------------------------------------------- #


def test_emission_records_validate_against_envelope_schema() -> None:
    schema = load_schema(SCHEMA_PATH)
    base = {"status": "pass", "artifacts": ["x"], "findings": [], "rationale": "ok"}
    records = [
        surface_visual_regression_delta_exceeded(
            "19-5", "AC-1", _registry()
        ).marker_record.model_dump(),
        surface_visual_regression_baseline_missing(
            "19-5", "AC-2", _registry()
        ).marker_record.model_dump(),
    ]
    envelope = base | {"visual_regression_emissions": records}
    assert validate_envelope(envelope, schema) == []


def test_envelope_rejects_visual_regression_missing_ac_id() -> None:
    schema = load_schema(SCHEMA_PATH)
    base = {"status": "pass", "artifacts": ["x"], "findings": [], "rationale": "ok"}
    # ac_id is unconditionally required for BOTH classes (AC-scoped).
    envelope = base | {
        "visual_regression_emissions": [
            {"marker_class": "visual-regression-delta-exceeded"}
        ]
    }
    assert validate_envelope(envelope, schema) != []


def test_envelope_rejects_visual_regression_wrong_enum() -> None:
    schema = load_schema(SCHEMA_PATH)
    base = {"status": "pass", "artifacts": ["x"], "findings": [], "rationale": "ok"}
    envelope = base | {
        "visual_regression_emissions": [
            {"marker_class": "visual-regression-mode-unstable", "ac_id": "AC-1"}
        ]
    }
    assert validate_envelope(envelope, schema) != []


def test_envelope_rejects_visual_regression_additional_property() -> None:
    schema = load_schema(SCHEMA_PATH)
    base = {"status": "pass", "artifacts": ["x"], "findings": [], "rationale": "ok"}
    envelope = base | {
        "visual_regression_emissions": [
            {
                "marker_class": "visual-regression-delta-exceeded",
                "ac_id": "AC-1",
                "next_action": "retry",
            }
        ]
    }
    assert validate_envelope(envelope, schema) != []


# --------------------------------------------------------------------------- #
# Absence-of-marker doctrine: NO silent-skip marker class exists              #
# --------------------------------------------------------------------------- #


def test_no_visual_regression_skip_or_disabled_marker_class_in_taxonomy() -> None:
    """web/mobile + opt-in gating is a SILENT skip on api/unconfigured — NO marker
    fires (mirrors the a11y / masked_selectors absence-of-marker doctrine).
    Structural witness: the taxonomy carries ONLY the two evidence classes; no
    `visual-regression-skipped` / `-disabled` / `-not-configured` class exists."""
    import yaml

    taxonomy = yaml.safe_load(
        (REPO_ROOT / "schemas" / "marker-taxonomy.yaml").read_text(encoding="utf-8")
    )
    vr_classes = {
        entry["marker_class"]
        for entry in taxonomy["markers"]
        if entry["marker_class"].startswith("visual-regression-")
    }
    assert vr_classes == {
        "visual-regression-delta-exceeded",
        "visual-regression-baseline-missing",
    }
