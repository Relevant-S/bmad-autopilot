"""Story 17.2 — auto-merge gate-condition evaluator + ``auto-merge-gate-not-met`` marker."""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any

import pytest
import yaml

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.auto_merge_config import (
    AutoMergeConfig,
    AutoMergeGateConditions,
)
from loud_fail_harness.auto_merge_gate import (
    AUTO_MERGE_GATE_NOT_MET_MARKER,
    DEFAULT_ADOPTION_METRICS_PATH,
    AdoptionMetrics,
    AutoMergeGateDecision,
    AutoMergeGateError,
    AutoMergeGateNotMetEmission,
    evaluate_auto_merge_gate,
    read_adoption_metrics,
    resolve_adoption_metrics,
    resolve_and_evaluate_auto_merge_gate,
    surface_auto_merge_gate_not_met,
)
from loud_fail_harness.bundle_assembly import (
    _render_auto_merge_gate_not_met_subsection,
    assemble_bundle,
    main as bundle_main,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
    load_marker_class_registry,
)

# --------------------------------------------------------------------------- #
# Fixtures / helpers                                                          #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


def _canonical_registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(
        marker_classes=frozenset({AUTO_MERGE_GATE_NOT_MET_MARKER})
    )


def _config(
    *,
    enabled: bool = False,
    months: int | None = 6,
    fidelity: float | None = 0.9,
    retry: float | None = 0.1,
) -> AutoMergeConfig:
    return AutoMergeConfig(
        enabled=enabled,
        gate_conditions=AutoMergeGateConditions(
            min_adoption_months=months,
            min_completion_fidelity=fidelity,
            max_retry_exhaustion=retry,
        ),
    )


def _metrics_doc(
    *, months: int = 6, fidelity: float = 0.9, retry: float = 0.1
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "adoption_months": months,
        "completion_fidelity": fidelity,
        "retry_exhaustion": retry,
    }


def _write_metrics(path: pathlib.Path, doc: dict[str, Any] | str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = doc if isinstance(doc, str) else yaml.safe_dump(doc, sort_keys=False)
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# AC-1 — adoption-metrics reader (loud-fail contract)                         #
# --------------------------------------------------------------------------- #


def test_resolve_adoption_metrics_valid() -> None:
    m = resolve_adoption_metrics(_metrics_doc(months=12, fidelity=0.95, retry=0.05))
    assert m == AdoptionMetrics(
        adoption_months=12, completion_fidelity=0.95, retry_exhaustion=0.05
    )


def test_resolve_accepts_int_for_fraction_fields() -> None:
    m = resolve_adoption_metrics(_metrics_doc(fidelity=1, retry=0))
    assert m.completion_fidelity == 1.0
    assert m.retry_exhaustion == 0.0


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: d.pop("schema_version"), id="missing-schema-version"),
        pytest.param(
            lambda d: d.__setitem__("schema_version", "2.0"), id="wrong-schema-version"
        ),
        pytest.param(lambda d: d.pop("adoption_months"), id="missing-months"),
        pytest.param(lambda d: d.pop("completion_fidelity"), id="missing-fidelity"),
        pytest.param(lambda d: d.pop("retry_exhaustion"), id="missing-retry"),
        pytest.param(
            lambda d: d.__setitem__("adoption_months", -1), id="negative-months"
        ),
        pytest.param(
            lambda d: d.__setitem__("adoption_months", 6.0), id="float-months"
        ),
        pytest.param(
            lambda d: d.__setitem__("adoption_months", True), id="bool-months"
        ),
        pytest.param(
            lambda d: d.__setitem__("completion_fidelity", 1.5), id="fidelity-too-high"
        ),
        pytest.param(
            lambda d: d.__setitem__("retry_exhaustion", -0.1), id="retry-negative"
        ),
        pytest.param(
            lambda d: d.__setitem__("completion_fidelity", True), id="bool-fidelity"
        ),
        pytest.param(
            lambda d: d.__setitem__("completion_fidelity", "0.9"), id="str-fidelity"
        ),
        pytest.param(
            lambda d: d.__setitem__("completion_fidelity", float("nan")), id="nan"
        ),
        pytest.param(
            lambda d: d.__setitem__("retry_exhaustion", float("inf")), id="inf"
        ),
    ],
)
def test_resolve_adoption_metrics_loud_fails(mutate: Any) -> None:
    doc = _metrics_doc()
    mutate(doc)
    with pytest.raises(AutoMergeGateError):
        resolve_adoption_metrics(doc)


def test_nan_diagnostic_names_field() -> None:
    doc = _metrics_doc()
    doc["completion_fidelity"] = float("nan")
    with pytest.raises(AutoMergeGateError, match="completion_fidelity"):
        resolve_adoption_metrics(doc)


def test_read_missing_file_loud_fails(tmp_path: pathlib.Path) -> None:
    with pytest.raises(AutoMergeGateError, match="does not exist"):
        read_adoption_metrics(tmp_path / "absent.yaml")


def test_read_empty_file_loud_fails(tmp_path: pathlib.Path) -> None:
    path = _write_metrics(tmp_path / "m.yaml", "   \n")
    with pytest.raises(AutoMergeGateError, match="empty"):
        read_adoption_metrics(path)


def test_read_malformed_yaml_loud_fails(tmp_path: pathlib.Path) -> None:
    path = _write_metrics(tmp_path / "m.yaml", "adoption_months: [unterminated\n")
    with pytest.raises(AutoMergeGateError, match="not valid YAML"):
        read_adoption_metrics(path)


def test_read_non_mapping_loud_fails(tmp_path: pathlib.Path) -> None:
    path = _write_metrics(tmp_path / "m.yaml", "- 1\n- 2\n")
    with pytest.raises(AutoMergeGateError, match="must be a YAML mapping"):
        read_adoption_metrics(path)


def test_read_valid_file_resolves(tmp_path: pathlib.Path) -> None:
    path = _write_metrics(tmp_path / "m.yaml", _metrics_doc(months=8))
    assert read_adoption_metrics(path).adoption_months == 8


# --------------------------------------------------------------------------- #
# AC-2 — per-gate pass/fail + boundary conditions                             #
# --------------------------------------------------------------------------- #


def test_all_gates_met_is_green() -> None:
    d = evaluate_auto_merge_gate(_config(), AdoptionMetrics(6, 0.9, 0.1))
    assert d.status == "green"
    assert all(v.passed for v in d.verdicts)
    assert {v.gate_name for v in d.verdicts} == {
        "min_adoption_months",
        "min_completion_fidelity",
        "max_retry_exhaustion",
    }


@pytest.mark.parametrize(
    "metrics,failing",
    [
        (AdoptionMetrics(5, 0.9, 0.1), {"min_adoption_months"}),
        (AdoptionMetrics(6, 0.89, 0.1), {"min_completion_fidelity"}),
        (AdoptionMetrics(6, 0.9, 0.11), {"max_retry_exhaustion"}),
        (
            AdoptionMetrics(1, 0.1, 0.9),
            {
                "min_adoption_months",
                "min_completion_fidelity",
                "max_retry_exhaustion",
            },
        ),
    ],
)
def test_single_and_combined_gate_failures(
    metrics: AdoptionMetrics, failing: set[str]
) -> None:
    d = evaluate_auto_merge_gate(_config(), metrics)
    assert d.status == "gate-not-met"
    assert {v.gate_name for v in d.failing_verdicts} == failing


def test_boundary_at_threshold_passes() -> None:
    # >= and <= are inclusive: exactly-at-threshold passes every gate.
    d = evaluate_auto_merge_gate(_config(months=6, fidelity=0.9, retry=0.1),
                                 AdoptionMetrics(6, 0.9, 0.1))
    assert d.status == "green"


def test_boundary_just_below_and_above() -> None:
    # adoption just below fails; retry just above its ceiling fails.
    assert evaluate_auto_merge_gate(
        _config(), AdoptionMetrics(5, 0.9, 0.1)
    ).status == "gate-not-met"
    assert evaluate_auto_merge_gate(
        _config(), AdoptionMetrics(6, 0.9, 0.1000001)
    ).status == "gate-not-met"


def test_verdict_carries_current_value_and_threshold() -> None:
    d = evaluate_auto_merge_gate(_config(months=6), AdoptionMetrics(3, 0.9, 0.1))
    months_v = next(v for v in d.verdicts if v.gate_name == "min_adoption_months")
    assert months_v.current_value == 3
    assert months_v.threshold == 6
    assert months_v.comparison == ">="
    assert months_v.passed is False


# --------------------------------------------------------------------------- #
# AC-4 — blank gates evaluate to nothing; partial-config handling             #
# --------------------------------------------------------------------------- #


def test_blank_gates_are_not_configured() -> None:
    d = evaluate_auto_merge_gate(
        _config(months=None, fidelity=None, retry=None),
        AdoptionMetrics(0, 0.0, 1.0),
    )
    assert d.status == "not-configured"
    assert d.verdicts == ()


def test_partial_config_evaluates_only_set_gates() -> None:
    # enabled:false permits partial gates (17.1); evaluate only the set one.
    d = evaluate_auto_merge_gate(
        _config(months=6, fidelity=None, retry=None),
        AdoptionMetrics(3, 0.0, 1.0),
    )
    assert d.status == "gate-not-met"
    assert [v.gate_name for v in d.verdicts] == ["min_adoption_months"]


def test_resolve_and_evaluate_not_configured_never_reads_metrics(
    tmp_path: pathlib.Path,
) -> None:
    # Default install: blank gates → not-configured, metrics file absent is fine.
    d = resolve_and_evaluate_auto_merge_gate(
        _config(months=None, fidelity=None, retry=None),
        metrics_path=tmp_path / "absent.yaml",
    )
    assert d.status == "not-configured"


def test_resolve_and_evaluate_configured_reads_metrics(tmp_path: pathlib.Path) -> None:
    path = _write_metrics(tmp_path / "m.yaml", _metrics_doc(months=3))
    d = resolve_and_evaluate_auto_merge_gate(_config(), metrics_path=path)
    assert d.status == "gate-not-met"


def test_resolve_and_evaluate_configured_missing_metrics_loud_fails(
    tmp_path: pathlib.Path,
) -> None:
    with pytest.raises(AutoMergeGateError):
        resolve_and_evaluate_auto_merge_gate(
            _config(), metrics_path=tmp_path / "absent.yaml"
        )


def test_default_metrics_path() -> None:
    assert DEFAULT_ADOPTION_METRICS_PATH == pathlib.Path(
        "_bmad-output/metrics/adoption-metrics.yaml"
    )


# --------------------------------------------------------------------------- #
# AC-3 — surface_ emission: diagnostic names each failing gate                #
# --------------------------------------------------------------------------- #


def test_surface_names_each_failing_gate_with_value_and_threshold() -> None:
    d = evaluate_auto_merge_gate(_config(), AdoptionMetrics(3, 0.8, 0.2))
    emission = surface_auto_merge_gate_not_met(d, _canonical_registry())
    assert isinstance(emission, AutoMergeGateNotMetEmission)
    assert emission.marker_class == AUTO_MERGE_GATE_NOT_MET_MARKER
    ptr = emission.diagnostic_pointer
    for token in (
        "min_adoption_months",
        "min_completion_fidelity",
        "max_retry_exhaustion",
        "adoption_months=3",
        ">= 6",
        "<= 0.1",
    ):
        assert token in ptr, f"missing {token!r} in diagnostic: {ptr}"
    assert {v.gate_name for v in emission.failing_gates} == {
        "min_adoption_months",
        "min_completion_fidelity",
        "max_retry_exhaustion",
    }


def test_surface_only_includes_failing_gates() -> None:
    d = evaluate_auto_merge_gate(_config(), AdoptionMetrics(3, 0.9, 0.1))
    emission = surface_auto_merge_gate_not_met(d, _canonical_registry())
    assert [v.gate_name for v in emission.failing_gates] == ["min_adoption_months"]


def test_surface_rejects_non_gate_not_met_decision() -> None:
    green = AutoMergeGateDecision(status="green", verdicts=())
    with pytest.raises(ValueError, match="gate-not-met"):
        surface_auto_merge_gate_not_met(green, _canonical_registry())


def test_surface_unknown_marker_class_raises() -> None:
    d = evaluate_auto_merge_gate(_config(), AdoptionMetrics(3, 0.9, 0.1))
    with pytest.raises(UnknownMarkerClass):
        surface_auto_merge_gate_not_met(d, MarkerClassRegistry(marker_classes=frozenset()))


def test_marker_in_canonical_taxonomy(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    assert AUTO_MERGE_GATE_NOT_MET_MARKER in runtime_marker_registry.marker_classes


# --------------------------------------------------------------------------- #
# AC-6 — render path (sub-section + marker comment)                           #
# --------------------------------------------------------------------------- #


def _gate_not_met_emission() -> AutoMergeGateNotMetEmission:
    d = evaluate_auto_merge_gate(_config(), AdoptionMetrics(3, 0.8, 0.2))
    return surface_auto_merge_gate_not_met(d, _canonical_registry())


def test_render_subsection_emits_heading_and_marker_comment() -> None:
    body = _render_auto_merge_gate_not_met_subsection(
        _gate_not_met_emission(), marker_registry=_canonical_registry()
    )
    assert "### Auto-merge gate not met" in body
    assert f"<!-- bmad-automation:marker {AUTO_MERGE_GATE_NOT_MET_MARKER} -->" in body
    assert "min_adoption_months" in body


def test_render_subsection_empty_on_none() -> None:
    assert (
        _render_auto_merge_gate_not_met_subsection(
            None, marker_registry=_canonical_registry()
        )
        == ""
    )


def test_render_subsection_unknown_marker_raises() -> None:
    with pytest.raises(UnknownMarkerClass):
        _render_auto_merge_gate_not_met_subsection(
            _gate_not_met_emission(),
            marker_registry=MarkerClassRegistry(marker_classes=frozenset()),
        )


# --------------------------------------------------------------------------- #
# AC-6 — assemble_bundle wiring (render appears iff emission passed)           #
# --------------------------------------------------------------------------- #

_STORY_ID = "sample-auto-001"
_RUN_ID = "run-2026-04-29-001"


def _seed_bundle_inputs(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    envelopes_dir = find_repo_root() / "examples" / "envelopes"
    dev = yaml.safe_load((envelopes_dir / "dev-pass.yaml").read_text(encoding="utf-8"))
    review = yaml.safe_load(
        (envelopes_dir / "review-pass-three-layer.yaml").read_text(encoding="utf-8")
    )
    qa = yaml.safe_load(
        (envelopes_dir / "qa-pass-ac1-tier1.yaml").read_text(encoding="utf-8")
    )
    rs_path = tmp_path / "_bmad" / "automation" / "run-state.yaml"
    rs_path.parent.mkdir(parents=True, exist_ok=True)
    rs_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.1",
                "story_id": _STORY_ID,
                "run_id": _RUN_ID,
                "current_state": "done",
                "branch_name": f"bmad-automation/story/{_STORY_ID}",
                "dispatched_specialist": None,
                "last_envelope": None,
                "pending_qa_dispatch_payload": None,
                "retry_history": [],
                "active_markers": [],
                "cost_to_date_by_specialist": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    logs_root = tmp_path / "qa-evidence"
    for specialist, env in (("dev", dev), ("review-bmad", review), ("qa", qa)):
        log_path = logs_root / _STORY_ID / _RUN_ID / "logs" / f"{specialist}-1.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            json.dumps(
                {
                    "dispatched_specialist": specialist,
                    "story_id": _STORY_ID,
                    "attempt_number": 1,
                    "agent_definition_path": f"agents/{specialist}.md",
                    "acceptance_criteria": [{"ac_id": "AC-1", "text": "stub"}],
                    "dispatch_timestamp": "2026-04-29T12:00:00+00:00",
                    "return_timestamp": "2026-04-29T12:01:00+00:00",
                    "return_envelope": env,
                }
            ),
            encoding="utf-8",
        )
    evidence = (
        tmp_path
        / "_bmad-output"
        / "qa-evidence"
        / "sample-001"
        / _RUN_ID
        / "ac1-http-200.log"
    )
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("HTTP/1.1 200 OK\n", encoding="utf-8")
    return rs_path, logs_root, tmp_path / "pr-bundles"


def test_assemble_bundle_renders_marker_when_emission_present(
    tmp_path: pathlib.Path, runtime_marker_registry: MarkerClassRegistry
) -> None:
    rs_path, logs_root, bundle_root = _seed_bundle_inputs(tmp_path)
    result = assemble_bundle(
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        marker_registry=runtime_marker_registry,
        generated_at=datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc),
        repo_root=tmp_path,
        auto_merge_gate_emission=_gate_not_met_emission(),
    )
    body = result.bundle_path.read_text(encoding="utf-8")
    assert "### Auto-merge gate not met" in body
    assert f"<!-- bmad-automation:marker {AUTO_MERGE_GATE_NOT_MET_MARKER} -->" in body


def test_assemble_bundle_omits_section_when_no_emission(
    tmp_path: pathlib.Path, runtime_marker_registry: MarkerClassRegistry
) -> None:
    rs_path, logs_root, bundle_root = _seed_bundle_inputs(tmp_path)
    result = assemble_bundle(
        story_id=_STORY_ID,
        run_id=_RUN_ID,
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        marker_registry=runtime_marker_registry,
        generated_at=datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc),
        repo_root=tmp_path,
    )
    body = result.bundle_path.read_text(encoding="utf-8")
    assert "Auto-merge gate not met" not in body
    assert AUTO_MERGE_GATE_NOT_MET_MARKER not in body


# --------------------------------------------------------------------------- #
# AC-4/AC-7 — main() end-to-end Stop-hook path                                #
# --------------------------------------------------------------------------- #


def _main_argv(
    tmp_path: pathlib.Path,
    rs_path: pathlib.Path,
    logs_root: pathlib.Path,
    bundle_root: pathlib.Path,
    *,
    config_path: pathlib.Path,
    metrics_path: pathlib.Path,
) -> list[str]:
    return [
        "--story-id", _STORY_ID,
        "--run-id", _RUN_ID,
        "--run-state-path", str(rs_path),
        "--logs-root", str(logs_root),
        "--bundle-root", str(bundle_root),
        "--repo-root", str(tmp_path),
        "--auto-merge-config-path", str(config_path),
        "--adoption-metrics-path", str(metrics_path),
    ]


def test_main_emits_marker_when_gate_unmet(tmp_path: pathlib.Path) -> None:
    rs_path, logs_root, bundle_root = _seed_bundle_inputs(tmp_path)
    config_path = _write_metrics(
        tmp_path / "config.yaml",
        yaml.safe_dump(
            {
                "auto_merge": {
                    "enabled": False,
                    "gate_conditions": {
                        "min_adoption_months": 6,
                        "min_completion_fidelity": 0.9,
                        "max_retry_exhaustion": 0.1,
                    },
                }
            }
        ),
    )
    metrics_path = _write_metrics(tmp_path / "adoption-metrics.yaml", _metrics_doc(months=2))
    rc = bundle_main(
        _main_argv(tmp_path, rs_path, logs_root, bundle_root,
                   config_path=config_path, metrics_path=metrics_path)
    )
    assert rc == 0
    body = (bundle_root / _STORY_ID / f"{_RUN_ID}.md").read_text(encoding="utf-8")
    assert f"<!-- bmad-automation:marker {AUTO_MERGE_GATE_NOT_MET_MARKER} -->" in body


def test_main_no_marker_on_default_blank_gates(tmp_path: pathlib.Path) -> None:
    rs_path, logs_root, bundle_root = _seed_bundle_inputs(tmp_path)
    # No config file at all → disabled + blank gates → not-configured → no read.
    rc = bundle_main(
        _main_argv(tmp_path, rs_path, logs_root, bundle_root,
                   config_path=tmp_path / "absent-config.yaml",
                   metrics_path=tmp_path / "absent-metrics.yaml")
    )
    assert rc == 0
    body = (bundle_root / _STORY_ID / f"{_RUN_ID}.md").read_text(encoding="utf-8")
    assert AUTO_MERGE_GATE_NOT_MET_MARKER not in body


def test_main_gate_error_degrades_gracefully(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rs_path, logs_root, bundle_root = _seed_bundle_inputs(tmp_path)
    config_path = _write_metrics(
        tmp_path / "config.yaml",
        yaml.safe_dump(
            {
                "auto_merge": {
                    "enabled": False,
                    "gate_conditions": {
                        "min_adoption_months": 6,
                        "min_completion_fidelity": 0.9,
                        "max_retry_exhaustion": 0.1,
                    },
                }
            }
        ),
    )
    rc = bundle_main(
        _main_argv(tmp_path, rs_path, logs_root, bundle_root,
                   config_path=config_path,
                   metrics_path=tmp_path / "absent-metrics.yaml")
    )
    # AutoMergeGateError (Phase-2 opt-in) degrades gracefully: stderr + exit 0,
    # bundle is written with a configuration-error subsection (Phase-1 output
    # is never suppressed by a Phase-2 config problem).
    assert rc == 0
    assert "AutoMergeGateError" in capsys.readouterr().err
    bundle = (bundle_root / _STORY_ID / f"{_RUN_ID}.md").read_text(encoding="utf-8")
    assert "### Auto-merge gate — configuration error" in bundle
