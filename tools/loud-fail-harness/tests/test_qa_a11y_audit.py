"""Story 19.4 — qa_a11y_audit substrate-library coverage.

Exercises the a11y delta engine (axe-result parse + ``(rule-id, target-selector)``
violation-key normalization + per-AC baseline load/store + self-computed
set-difference delta + threshold compare + non-deterministic-delta detection)
and the three Pattern-5 atomic-on-failure ``surface_a11y_*`` emission helpers.

Non-vacuous (Story 24.3 retro): assertions name the EXACT marker classes
(``a11y-baseline-stale`` / ``a11y-delta-exceeded`` / ``a11y-delta-mode-unstable``)
and exact key/count outcomes, never ``len(...) > 0``.
"""

from __future__ import annotations

import pathlib

import pytest

from loud_fail_harness.envelope_validator import (
    find_repo_root,
    load_schema,
    validate_envelope,
)
from loud_fail_harness.bundle_assembly import (
    _render_per_ac_section,
    _render_qa_a11y_envelope_scoped_marker,
)
from loud_fail_harness.qa_a11y_audit import (
    A11Y_BASELINE_STALE_MARKER,
    A11Y_DELTA_EXCEEDED_MARKER,
    A11Y_DELTA_MODE_UNSTABLE_MARKER,
    DEFAULT_DELTA_THRESHOLD,
    A11yBaselineStaleEmission,
    A11yDeltaExceededEmission,
    A11yDeltaModeUnstableEmission,
    AxeViolationKey,
    compute_baseline_dir,
    compute_delta,
    decide_a11y_mode,
    deserialize_violation_keys,
    load_baseline,
    normalize_violation_keys,
    serialize_delta_artifact,
    serialize_violation_keys,
    store_baseline,
    surface_a11y_baseline_stale,
    surface_a11y_delta_exceeded,
    surface_a11y_delta_mode_unstable,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
)

REPO_ROOT = find_repo_root()
SCHEMA_PATH = REPO_ROOT / "schemas" / "envelope.schema.yaml"


def _registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(
        marker_classes=frozenset(
            {
                A11Y_BASELINE_STALE_MARKER,
                A11Y_DELTA_EXCEEDED_MARKER,
                A11Y_DELTA_MODE_UNSTABLE_MARKER,
            }
        )
    )


def _empty_registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(marker_classes=frozenset())


def _axe_result(*violations: dict) -> dict:
    return {
        "violations": list(violations),
        "passes": [],
        "incomplete": [],
        "inapplicable": [],
        "testEngine": {"name": "axe-core", "version": "4.12.1"},
    }


def _violation(rule_id: str, *targets: object) -> dict:
    return {"id": rule_id, "nodes": [{"target": t} for t in targets]}


# --------------------------------------------------------------------------- #
# Violation-key normalization (target string / iframe / shadow-DOM shapes)    #
# --------------------------------------------------------------------------- #


def test_normalize_top_level_selector() -> None:
    result = normalize_violation_keys(_axe_result(_violation("color-contrast", ["#nav > button"])))
    assert result.stable is True
    assert result.keys == frozenset(
        {AxeViolationKey(rule_id="color-contrast", target_selector="#nav > button")}
    )


def test_normalize_iframe_path_target() -> None:
    """Array-of-strings target == iframe/frame nesting path."""
    result = normalize_violation_keys(
        _axe_result(_violation("button-name", ["#frame", "#btn-inside-frame"]))
    )
    assert result.stable is True
    assert result.keys == frozenset(
        {AxeViolationKey(rule_id="button-name", target_selector="#frame | #btn-inside-frame")}
    )


def test_normalize_shadow_dom_target() -> None:
    """Array-of-arrays target == shadow-DOM piercing path."""
    result = normalize_violation_keys(
        _axe_result(_violation("label", [["#host", "#shadow-input"]]))
    )
    assert result.stable is True
    assert result.keys == frozenset(
        {AxeViolationKey(rule_id="label", target_selector="(#host >> #shadow-input)")}
    )


def test_normalize_dedups_identical_keys() -> None:
    result = normalize_violation_keys(
        _axe_result(_violation("color-contrast", ["#a"], ["#a"]))
    )
    assert result.stable is True
    assert result.keys == frozenset(
        {AxeViolationKey(rule_id="color-contrast", target_selector="#a")}
    )


def test_normalize_empty_target_marks_unstable() -> None:
    result = normalize_violation_keys(_axe_result(_violation("color-contrast", [])))
    assert result.stable is False
    assert result.keys == frozenset()


def test_normalize_missing_id_marks_unstable() -> None:
    result = normalize_violation_keys(_axe_result({"id": "", "nodes": [{"target": ["#a"]}]}))
    assert result.stable is False


def test_normalize_malformed_top_level_marks_unstable() -> None:
    result = normalize_violation_keys({"violations": "not-a-list"})
    assert result.stable is False
    assert result.keys == frozenset()


def test_normalize_partial_unstable_keeps_good_keys() -> None:
    """A malformed node marks the run unstable but the well-formed keys survive."""
    result = normalize_violation_keys(
        _axe_result(
            _violation("color-contrast", ["#good"]),
            _violation("button-name", []),  # empty target -> unstable
        )
    )
    assert result.stable is False
    assert AxeViolationKey(rule_id="color-contrast", target_selector="#good") in result.keys


def test_normalize_bare_string_target() -> None:
    """axe-core occasionally returns a bare string instead of a list."""
    result = normalize_violation_keys(_axe_result(_violation("color-contrast", "button#submit")))
    assert result.stable is True
    assert result.keys == frozenset(
        {AxeViolationKey(rule_id="color-contrast", target_selector="button#submit")}
    )


def test_normalize_hostile_key_marks_unstable() -> None:
    """ValidationError from harden_identifier on a hostile selector -> stable=False."""
    result = normalize_violation_keys(_axe_result(_violation("color-contrast\nnewline", ["#a"])))
    assert result.stable is False


# --------------------------------------------------------------------------- #
# Set-difference delta + threshold compare                                    #
# --------------------------------------------------------------------------- #


def _key(rule: str, sel: str) -> AxeViolationKey:
    return AxeViolationKey(rule_id=rule, target_selector=sel)


def test_compute_delta_new_keys_only() -> None:
    baseline = frozenset({_key("a", "#1")})
    current = frozenset({_key("a", "#1"), _key("b", "#2")})
    delta = compute_delta(baseline, current, threshold=0)
    assert delta.new_keys == frozenset({_key("b", "#2")})
    assert delta.exceeded is True


def test_compute_delta_threshold_boundary_at_vs_over() -> None:
    baseline: frozenset[AxeViolationKey] = frozenset()
    current = frozenset({_key("a", "#1"), _key("b", "#2")})
    # exactly AT threshold (2 new, threshold 2) -> NOT exceeded
    assert compute_delta(baseline, current, threshold=2).exceeded is False
    # OVER threshold (2 new, threshold 1) -> exceeded
    assert compute_delta(baseline, current, threshold=1).exceeded is True


def test_compute_delta_default_threshold_zero_any_new_is_regression() -> None:
    assert DEFAULT_DELTA_THRESHOLD == 0
    delta = compute_delta(frozenset(), frozenset({_key("a", "#1")}))
    assert delta.exceeded is True


def test_compute_delta_fixed_or_unchanged_violations_not_exceeded() -> None:
    """Current is a subset of baseline (violations fixed) -> no new keys."""
    baseline = frozenset({_key("a", "#1"), _key("b", "#2")})
    current = frozenset({_key("a", "#1")})
    delta = compute_delta(baseline, current, threshold=0)
    assert delta.new_keys == frozenset()
    assert delta.exceeded is False


def test_compute_delta_negative_threshold_raises() -> None:
    with pytest.raises(ValueError, match="threshold must be >= 0"):
        compute_delta(frozenset(), frozenset(), threshold=-1)


# --------------------------------------------------------------------------- #
# Mode decision                                                               #
# --------------------------------------------------------------------------- #


def test_decide_mode_no_baseline_is_baseline_stale() -> None:
    current = normalize_violation_keys(_axe_result(_violation("a", ["#1"])))
    decision = decide_a11y_mode(None, current, threshold=0)
    assert decision.mode == "baseline-stale"
    assert decision.new_keys == frozenset()


def test_decide_mode_unstable_fires_regardless_of_baseline() -> None:
    unstable = normalize_violation_keys(_axe_result(_violation("a", [])))
    assert unstable.stable is False
    # baseline exists + unstable -> delta-mode-unstable
    assert decide_a11y_mode(frozenset({_key("a", "#1")}), unstable).mode == "delta-mode-unstable"
    # no baseline + unstable -> STILL delta-mode-unstable (D1=A: anchoring a partial
    # key set as first-run baseline would cause false-positive delta-exceeded on
    # subsequent stable runs; the escape valve fires unconditionally)
    assert decide_a11y_mode(None, unstable).mode == "delta-mode-unstable"


def test_decide_mode_delta_exceeded() -> None:
    current = normalize_violation_keys(_axe_result(_violation("a", ["#1"]), _violation("b", ["#2"])))
    decision = decide_a11y_mode(frozenset({_key("a", "#1")}), current, threshold=0)
    assert decision.mode == "delta-exceeded"
    assert decision.new_keys == frozenset({_key("b", "#2")})


def test_decide_mode_delta_within_threshold() -> None:
    current = normalize_violation_keys(_axe_result(_violation("a", ["#1"])))
    decision = decide_a11y_mode(frozenset({_key("a", "#1")}), current, threshold=0)
    assert decision.mode == "delta-within-threshold"
    assert decision.new_keys == frozenset()


# --------------------------------------------------------------------------- #
# Baseline path + load/store + serialization roundtrip                        #
# --------------------------------------------------------------------------- #


def test_compute_baseline_dir_path() -> None:
    assert str(compute_baseline_dir("19-4", "AC-1")) == "_bmad-output/qa-a11y-baseline/19-4/AC-1"


@pytest.mark.parametrize("bad", ["../escape", "a/b", "with\nnewline"])
def test_compute_baseline_dir_rejects_traversal(bad: str) -> None:
    with pytest.raises(ValueError):
        compute_baseline_dir(bad, "AC-1")


def test_baseline_store_then_load_roundtrip(tmp_path: pathlib.Path) -> None:
    keys = frozenset({_key("color-contrast", "#a"), _key("label", "(#host >> #x)")})
    baseline_dir = tmp_path / "19-4" / "AC-1"
    written = store_baseline(baseline_dir, keys)
    assert written.name == "baseline.json"
    assert load_baseline(baseline_dir) == keys


def test_load_baseline_absent_returns_none(tmp_path: pathlib.Path) -> None:
    assert load_baseline(tmp_path / "nonexistent") is None


def test_load_baseline_returns_none_on_corrupt_json(tmp_path: pathlib.Path) -> None:
    baseline_dir = tmp_path / "19-4" / "AC-1"
    baseline_dir.mkdir(parents=True)
    (baseline_dir / "baseline.json").write_text("not-valid-json", encoding="utf-8")
    assert load_baseline(baseline_dir) is None


def test_serialize_deserialize_roundtrip_is_sorted_stable() -> None:
    keys = frozenset({_key("b", "#2"), _key("a", "#1")})
    text = serialize_violation_keys(keys)
    # deterministic ordering: rule "a" before rule "b"
    assert text.index('"rule_id": "a"') < text.index('"rule_id": "b"')
    assert deserialize_violation_keys(text) == keys


def test_serialize_delta_artifact_carries_new_keys_and_diff() -> None:
    baseline = frozenset({_key("a", "#1"), _key("c", "#3")})
    current = frozenset({_key("a", "#1"), _key("b", "#2")})
    new_keys = frozenset({_key("b", "#2")})
    text = serialize_delta_artifact(
        new_keys=new_keys, baseline_keys=baseline, current_keys=current, threshold=0
    )
    assert '"new_violation_count": 1' in text
    assert '"baseline_count": 2' in text
    assert '"current_count": 2' in text
    assert '"exceeded": true' in text
    assert '"rule_id": "b"' in text
    # D3=A: removed violations (fixed since baseline) are included in the artifact
    assert '"removed_violation_count": 1' in text
    assert '"rule_id": "c"' in text


# --------------------------------------------------------------------------- #
# Input hardening on the externally-constructed parse model                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("bad", ["with\nnewline", "with\x00null", "   "])
def test_axe_violation_key_rejects_hostile_rule_id(bad: str) -> None:
    with pytest.raises(ValueError):
        AxeViolationKey(rule_id=bad, target_selector="#ok")


def test_axe_violation_key_rejects_hostile_selector() -> None:
    with pytest.raises(ValueError):
        AxeViolationKey(rule_id="color-contrast", target_selector="x\x00y")


# --------------------------------------------------------------------------- #
# Pattern-5 atomic-on-failure emission helpers                                #
# --------------------------------------------------------------------------- #


def test_surface_a11y_baseline_stale_happy_path() -> None:
    emission = surface_a11y_baseline_stale("19-4", "AC-1", _registry())
    assert isinstance(emission, A11yBaselineStaleEmission)
    assert emission.marker_record.marker_class == "a11y-baseline-stale"
    assert emission.marker_record.ac_id == "AC-1"
    assert emission.diagnostic_context.story_id == "19-4"
    assert emission.diagnostic_context.ac_id == "AC-1"


def test_surface_a11y_delta_exceeded_happy_path() -> None:
    emission = surface_a11y_delta_exceeded("19-4", "AC-2", _registry())
    assert isinstance(emission, A11yDeltaExceededEmission)
    assert emission.marker_record.marker_class == "a11y-delta-exceeded"
    assert emission.marker_record.ac_id == "AC-2"


def test_surface_a11y_delta_mode_unstable_happy_path_has_no_ac_id() -> None:
    emission = surface_a11y_delta_mode_unstable("19-4", _registry())
    assert isinstance(emission, A11yDeltaModeUnstableEmission)
    assert emission.marker_record.marker_class == "a11y-delta-mode-unstable"
    # envelope-scoped: the record carries NO ac_id field at all
    assert "ac_id" not in emission.marker_record.model_dump()
    assert emission.diagnostic_context.story_id == "19-4"


def test_surface_a11y_baseline_stale_atomic_on_failure() -> None:
    with pytest.raises(UnknownMarkerClass):
        surface_a11y_baseline_stale("19-4", "AC-1", _empty_registry())


def test_surface_a11y_delta_exceeded_atomic_on_failure() -> None:
    with pytest.raises(UnknownMarkerClass):
        surface_a11y_delta_exceeded("19-4", "AC-1", _empty_registry())


def test_surface_a11y_delta_mode_unstable_atomic_on_failure() -> None:
    with pytest.raises(UnknownMarkerClass):
        surface_a11y_delta_mode_unstable("19-4", _empty_registry())


# --------------------------------------------------------------------------- #
# Envelope byte-mirror: emission records validate as `a11y_emissions` items   #
# --------------------------------------------------------------------------- #


def test_emission_records_validate_against_envelope_schema() -> None:
    schema = load_schema(SCHEMA_PATH)
    base = {"status": "pass", "artifacts": ["x"], "findings": [], "rationale": "ok"}
    records = [
        surface_a11y_baseline_stale("19-4", "AC-1", _registry()).marker_record.model_dump(),
        surface_a11y_delta_exceeded("19-4", "AC-2", _registry()).marker_record.model_dump(),
        surface_a11y_delta_mode_unstable("19-4", _registry()).marker_record.model_dump(),
    ]
    envelope = base | {"a11y_emissions": records}
    assert validate_envelope(envelope, schema) == []


# --------------------------------------------------------------------------- #
# End-to-end composition (load-or-create -> emit) over a real baseline tree   #
# --------------------------------------------------------------------------- #


def test_end_to_end_first_run_creates_baseline_and_surfaces_stale(
    tmp_path: pathlib.Path,
) -> None:
    registry = _registry()
    axe_result = _axe_result(_violation("color-contrast", ["#a"]))
    current = normalize_violation_keys(axe_result)
    baseline_dir = tmp_path / "19-4" / "AC-1"

    baseline = load_baseline(baseline_dir)
    decision = decide_a11y_mode(baseline, current)
    assert decision.mode == "baseline-stale"

    store_baseline(baseline_dir, current.keys)
    emission = surface_a11y_baseline_stale("19-4", "AC-1", registry)
    assert emission.marker_record.marker_class == "a11y-baseline-stale"
    # baseline now persisted for the next run
    assert load_baseline(baseline_dir) == current.keys


def test_end_to_end_second_run_new_violation_surfaces_delta_exceeded(
    tmp_path: pathlib.Path,
) -> None:
    registry = _registry()
    baseline_dir = tmp_path / "19-4" / "AC-1"
    store_baseline(baseline_dir, frozenset({_key("color-contrast", "#a")}))

    current = normalize_violation_keys(
        _axe_result(_violation("color-contrast", ["#a"]), _violation("button-name", ["#b"]))
    )
    baseline = load_baseline(baseline_dir)
    decision = decide_a11y_mode(baseline, current, threshold=DEFAULT_DELTA_THRESHOLD)
    assert decision.mode == "delta-exceeded"
    assert decision.new_keys == frozenset({_key("button-name", "#b")})
    emission = surface_a11y_delta_exceeded("19-4", "AC-1", registry)
    assert emission.marker_record.marker_class == "a11y-delta-exceeded"


# --------------------------------------------------------------------------- #
# Absence-of-marker doctrine: NO silent-skip marker class exists              #
# --------------------------------------------------------------------------- #


def test_no_a11y_skip_or_disabled_marker_class_in_taxonomy() -> None:
    """Web-only / opt-in gating is a SILENT skip on api/mobile/unconfigured — NO
    marker fires (mirrors `test_no_masking_not_configured_marker_class_in_taxonomy`).
    Structural witness: the taxonomy carries ONLY the three evidence classes; no
    `a11y-skipped` / `a11y-disabled` / `a11y-not-configured` class exists."""
    import yaml

    taxonomy = yaml.safe_load(
        (REPO_ROOT / "schemas" / "marker-taxonomy.yaml").read_text(encoding="utf-8")
    )
    a11y_classes = {
        entry["marker_class"]
        for entry in taxonomy["markers"]
        if entry["marker_class"].startswith("a11y-")
    }
    assert a11y_classes == {
        "a11y-baseline-stale",
        "a11y-delta-exceeded",
        "a11y-delta-mode-unstable",
    }


# --------------------------------------------------------------------------- #
# Story 21.0 — bundle render-gap fix (a11y_emissions → bundle)                 #
# --------------------------------------------------------------------------- #


def _minimal_qa_envelope() -> dict[str, object]:
    return {
        "specialist": "qa",
        "status": "pass",
        "ac_results": [
            {
                "ac_id": "AC-1",
                "status": "pass",
                "assertions": ["holds"],
                "evidence_refs": [],
                "semantic_verification": "not_applicable",
            }
        ],
        "findings": [],
    }


def test_bundle_renders_ac_scoped_a11y_markers() -> None:
    envelope = _minimal_qa_envelope() | {
        "a11y_emissions": [
            {"marker_class": A11Y_BASELINE_STALE_MARKER, "ac_id": "AC-1"},
            {"marker_class": A11Y_DELTA_EXCEEDED_MARKER, "ac_id": "AC-2"},
        ]
    }
    rendered = _render_per_ac_section(envelope, marker_registry=_registry())
    assert rendered.count("bmad-automation:marker a11y-baseline-stale") == 1
    assert rendered.count("bmad-automation:marker a11y-delta-exceeded") == 1
    assert "### Accessibility audit findings" in rendered
    assert "AC `AC-1`" in rendered
    assert "AC `AC-2`" in rendered


def test_bundle_per_ac_section_excludes_envelope_scoped_a11y_marker() -> None:
    envelope = _minimal_qa_envelope() | {
        "a11y_emissions": [
            {"marker_class": A11Y_DELTA_MODE_UNSTABLE_MARKER},
        ]
    }
    rendered = _render_per_ac_section(envelope, marker_registry=_registry())
    assert "a11y-delta-mode-unstable" not in rendered
    assert "### Accessibility audit findings" not in rendered


def test_envelope_scoped_a11y_marker_renders_at_bottom() -> None:
    envelope = _minimal_qa_envelope() | {
        "a11y_emissions": [
            {"marker_class": A11Y_DELTA_MODE_UNSTABLE_MARKER},
        ]
    }
    rendered = _render_qa_a11y_envelope_scoped_marker(
        envelope, marker_registry=_registry()
    )
    assert rendered == "<!-- bmad-automation:marker a11y-delta-mode-unstable -->"


def test_envelope_scoped_a11y_marker_silent_without_unstable_entry() -> None:
    envelope = _minimal_qa_envelope() | {
        "a11y_emissions": [
            {"marker_class": A11Y_BASELINE_STALE_MARKER, "ac_id": "AC-1"},
        ]
    }
    assert (
        _render_qa_a11y_envelope_scoped_marker(envelope, marker_registry=_registry())
        == ""
    )


def test_bundle_silent_without_a11y_emissions() -> None:
    rendered = _render_per_ac_section(
        _minimal_qa_envelope(), marker_registry=_registry()
    )
    assert "a11y-baseline-stale" not in rendered
    assert "a11y-delta-exceeded" not in rendered
    assert "Accessibility audit findings" not in rendered


def test_a11y_render_revalidates_against_registry() -> None:
    envelope = _minimal_qa_envelope() | {
        "a11y_emissions": [
            {"marker_class": A11Y_DELTA_EXCEEDED_MARKER, "ac_id": "AC-1"},
        ]
    }
    empty_registry = MarkerClassRegistry(marker_classes=frozenset())
    with pytest.raises(UnknownMarkerClass):
        _render_per_ac_section(envelope, marker_registry=empty_registry)
