"""Contract-coverage matrix for the onboarding benchmark substrate (Story 7.9).

This docstring IS the contract-coverage checklist required by AC-8. Each test
cites the AC it witnesses verbatim per Pattern 5's named-invariant convention.

Schema validation tests (AC-1, AC-2):
    [x] EnvironmentNotes requires all fields                  → test_environment_notes_requires_all_fields
    [x] ComponentTimings rejects negative values              → test_component_timings_rejects_negative_values
    [x] BenchmarkRecord root validator: component-sum tolerance
                                                              → test_benchmark_record_root_validator_component_sum_within_tolerance
    [x] BenchmarkRecord root validator: missed_component required when target missed
                                                              → test_benchmark_record_root_validator_missed_component_required_when_target_missed
    [x] BenchmarkRecord root validator: remediation note required when target missed
                                                              → test_benchmark_record_root_validator_remediation_note_required_when_target_missed
    [x] BenchmarkRecord root validator: missed_component must be None when target met
                                                              → test_benchmark_record_root_validator_missed_component_must_be_none_when_target_met

Pure-function tests (AC-3, AC-4):
    [x] evaluate_target returns True when total within budget → test_evaluate_target_returns_true_when_total_within_budget
    [x] evaluate_target returns False with argmax when total exceeds budget
                                                              → test_evaluate_target_returns_false_with_argmax_when_total_exceeds_budget
    [x] evaluate_target appends aggregate-overage suffix when argmax within historical mean
                                                              → test_evaluate_target_appends_aggregate_overage_suffix_when_argmax_within_historical_mean
    [x] render_record_row produces deterministic output       → test_render_record_row_produces_deterministic_output
    [x] render_record_row check/x emojis                      → test_render_record_row_renders_check_emoji_for_target_met_true_and_x_emoji_for_false

Artifact append tests (AC-3):
    [x] append creates file when absent                       → test_append_record_to_artifact_creates_file_when_absent
    [x] append inserts before end anchor                      → test_append_record_to_artifact_inserts_before_end_anchor
    [x] append raises when anchors missing                    → test_append_record_to_artifact_raises_when_anchors_missing
    [x] append raises when anchors out of order               → test_append_record_to_artifact_raises_when_anchors_out_of_order
    [x] append raises on duplicate row                        → test_append_record_to_artifact_raises_on_duplicate_row
    [x] append uses atomic write                              → test_append_record_to_artifact_uses_atomic_write

Reproducibility tests (AC-5):
    [x] run_benchmark loads canonical fixture byte-equal      → test_run_benchmark_loads_canonical_fixture_byte_equal
    [x] run_benchmark uses fresh reference project            → test_run_benchmark_uses_fresh_reference_project
    [x] run_benchmark raises on non-empty reference project   → test_run_benchmark_raises_on_non_empty_reference_project
    [x] run_benchmark probes claude code version at runtime   → test_run_benchmark_probes_claude_code_version_at_runtime

CLI smoke tests (AC-7, AC-4):
    [x] main returns 0 on target met dry run                  → test_main_returns_0_on_target_met_dry_run
    [x] main returns 1 on target missed non-dry run           → test_main_returns_1_on_target_missed_non_dry_run
    [x] main returns 2 on benchmark artifact error            → test_main_returns_2_on_benchmark_artifact_error
    [x] main with dry run does not write artifact             → test_main_with_dry_run_does_not_write_artifact
"""

from __future__ import annotations

import pathlib
import subprocess
from collections.abc import Sequence
from typing import Any
from unittest import mock

import pytest
from pydantic import ValidationError

from loud_fail_harness import onboarding_benchmark
from loud_fail_harness.onboarding_benchmark import (
    ARTIFACT_RELATIVE_PATH,
    BENCHMARK_FIXTURE_PATH,
    ROWS_BEGIN_ANCHOR,
    ROWS_END_ANCHOR,
    TARGET_FIRST_LOOP_SECONDS,
    BenchmarkArtifactError,
    BenchmarkRecord,
    BenchmarkRequest,
    ComponentTimings,
    EnvironmentNotes,
    append_record_to_artifact,
    build_artifact_seed,
    evaluate_target,
    main,
    render_record_row,
    run_benchmark,
)
from loud_fail_harness.sample_story_scaffold import (
    CANONICAL_CONTENT_RESOURCE,
    load_sample_story_content,
)


# --------------------------------------------------------------------------- #
# Fixtures + helpers                                                           #
# --------------------------------------------------------------------------- #


def _env_fixture() -> EnvironmentNotes:
    return EnvironmentNotes(
        claude_code_version="2.1.32",
        os_label="darwin-25.3.0",
        hardware_tier="developer-laptop",
        python_version="3.12.5",
    )


def _green_timings_fixture() -> ComponentTimings:
    """Component timings whose sum is well within the 300s budget."""
    return ComponentTimings(
        install_seconds=10.0,
        init_precondition_check_seconds=5.0,
        init_scaffold_seconds=2.0,
        init_stub_generation_seconds=3.0,
        first_specialist_dispatch_seconds=4.0,
        dev_runtime_seconds=80.0,
        review_bmad_runtime_seconds=40.0,
        qa_runtime_seconds=50.0,
        bundle_assembly_seconds=6.0,
    )


def _missed_target_timings_fixture() -> ComponentTimings:
    """Component timings whose sum exceeds the 300s budget (≈ 410s)."""
    return ComponentTimings(
        install_seconds=10.0,
        init_precondition_check_seconds=5.0,
        init_scaffold_seconds=2.0,
        init_stub_generation_seconds=3.0,
        first_specialist_dispatch_seconds=4.0,
        dev_runtime_seconds=200.0,  # The expected argmax.
        review_bmad_runtime_seconds=80.0,
        qa_runtime_seconds=100.0,
        bundle_assembly_seconds=6.0,
    )


def _green_record_fixture() -> BenchmarkRecord:
    timings = _green_timings_fixture()
    return BenchmarkRecord(
        date="2026-05-08",
        version="0.0.1",
        environment=_env_fixture(),
        component_timings=timings,
        end_to_end_total_seconds=timings.total_seconds(),
        target_met=True,
        missed_component=None,
        remediation_or_deferral_note=None,
    )


def _missed_record_fixture() -> BenchmarkRecord:
    timings = _missed_target_timings_fixture()
    target_met, missed = evaluate_target(timings)
    return BenchmarkRecord(
        date="2026-05-08",
        version="0.0.1",
        environment=_env_fixture(),
        component_timings=timings,
        end_to_end_total_seconds=timings.total_seconds(),
        target_met=target_met,
        missed_component=missed,
        remediation_or_deferral_note=(
            "Dev runtime regression in seed run; Story 7.9 infrastructure "
            "landing — first real release benchmark fires via "
            "release-benchmark.yml."
        ),
    )


class _FakeRunner:
    """Subprocess-runner stub for tests.

    Records every invocation in ``calls``; returns a configurable
    ``CompletedProcess[str]`` per call. Default behavior: returncode 0 + a
    minimal claude-version stdout for the version-probe call.
    """

    def __init__(
        self,
        *,
        claude_version_stdout: str = "2.1.32",
        per_phase_returncode: int = 0,
        per_phase_stderr: str = "",
    ) -> None:
        self.calls: list[tuple[Sequence[str], pathlib.Path | None, float | None]] = []
        self._claude_version_stdout = claude_version_stdout
        self._per_phase_returncode = per_phase_returncode
        self._per_phase_stderr = per_phase_stderr

    def __call__(
        self,
        cmd: Sequence[str],
        *,
        cwd: pathlib.Path | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((tuple(cmd), cwd, timeout))
        if list(cmd) == ["claude", "--version"]:
            return subprocess.CompletedProcess(
                args=list(cmd), returncode=0, stdout=self._claude_version_stdout, stderr=""
            )
        return subprocess.CompletedProcess(
            args=list(cmd),
            returncode=self._per_phase_returncode,
            stdout="",
            stderr=self._per_phase_stderr,
        )


# --------------------------------------------------------------------------- #
# Schema validation tests (AC-1, AC-2)                                         #
# --------------------------------------------------------------------------- #


def test_environment_notes_requires_all_fields() -> None:
    """AC-1: EnvironmentNotes Pydantic strict-mode rejects missing fields."""
    with pytest.raises(ValidationError):
        EnvironmentNotes(  # type: ignore[call-arg]
            claude_code_version="2.1.32",
            os_label="darwin-25.3.0",
            hardware_tier="developer-laptop",
            # python_version omitted — strict-mode fails.
        )


def test_component_timings_rejects_negative_values() -> None:
    """AC-2: ComponentTimings field validator rejects negative durations."""
    with pytest.raises(ValidationError):
        ComponentTimings(
            install_seconds=-1.0,
            init_precondition_check_seconds=0.0,
            init_scaffold_seconds=0.0,
            init_stub_generation_seconds=0.0,
            first_specialist_dispatch_seconds=0.0,
            dev_runtime_seconds=0.0,
            review_bmad_runtime_seconds=0.0,
            qa_runtime_seconds=0.0,
            bundle_assembly_seconds=0.0,
        )


def test_benchmark_record_root_validator_component_sum_within_tolerance() -> None:
    """AC-2: end_to_end_total_seconds within ±0.5s of sum(components) passes;
    drift outside the window raises with named invariant.
    """
    timings = _green_timings_fixture()
    component_sum = timings.total_seconds()

    # Within tolerance: passes.
    record = BenchmarkRecord(
        date="2026-05-08",
        version="0.0.1",
        environment=_env_fixture(),
        component_timings=timings,
        end_to_end_total_seconds=component_sum + 0.4,
        target_met=True,
        missed_component=None,
        remediation_or_deferral_note=None,
    )
    assert record.end_to_end_total_seconds == pytest.approx(component_sum + 0.4)

    # Sum exceeds total → physically impossible.
    with pytest.raises(ValidationError, match="component-sum-exceeds-end-to-end-total"):
        BenchmarkRecord(
            date="2026-05-08",
            version="0.0.1",
            environment=_env_fixture(),
            component_timings=timings,
            end_to_end_total_seconds=component_sum - 1.0,
            target_met=True,
            missed_component=None,
            remediation_or_deferral_note=None,
        )

    # Total exceeds sum by > 0.5s → unaccounted overhead.
    with pytest.raises(ValidationError, match="unaccounted-overhead-exceeds-tolerance"):
        BenchmarkRecord(
            date="2026-05-08",
            version="0.0.1",
            environment=_env_fixture(),
            component_timings=timings,
            end_to_end_total_seconds=component_sum + 5.0,
            target_met=True,
            missed_component=None,
            remediation_or_deferral_note=None,
        )


def test_benchmark_record_root_validator_missed_component_required_when_target_missed() -> None:
    """AC-4: target_met=False → missed_component MUST be non-None."""
    timings = _missed_target_timings_fixture()
    with pytest.raises(ValidationError, match="missed-component-required-when-target-missed"):
        BenchmarkRecord(
            date="2026-05-08",
            version="0.0.1",
            environment=_env_fixture(),
            component_timings=timings,
            end_to_end_total_seconds=timings.total_seconds(),
            target_met=False,
            missed_component=None,
            remediation_or_deferral_note="placeholder",
        )


def test_benchmark_record_root_validator_remediation_note_required_when_target_missed() -> None:
    """AC-4: target_met=False → remediation_or_deferral_note MUST be non-None."""
    timings = _missed_target_timings_fixture()
    with pytest.raises(ValidationError, match="remediation-note-required-when-target-missed"):
        BenchmarkRecord(
            date="2026-05-08",
            version="0.0.1",
            environment=_env_fixture(),
            component_timings=timings,
            end_to_end_total_seconds=timings.total_seconds(),
            target_met=False,
            missed_component="dev_runtime_seconds",
            remediation_or_deferral_note=None,
        )


def test_benchmark_record_root_validator_missed_component_must_be_none_when_target_met() -> None:
    """AC-4: target_met=True → missed_component MUST be None (and note must be None)."""
    timings = _green_timings_fixture()
    with pytest.raises(ValidationError, match="missed-component-must-be-none-when-target-met"):
        BenchmarkRecord(
            date="2026-05-08",
            version="0.0.1",
            environment=_env_fixture(),
            component_timings=timings,
            end_to_end_total_seconds=timings.total_seconds(),
            target_met=True,
            missed_component="dev_runtime_seconds",
            remediation_or_deferral_note=None,
        )

    with pytest.raises(ValidationError, match="remediation-note-must-be-none-when-target-met"):
        BenchmarkRecord(
            date="2026-05-08",
            version="0.0.1",
            environment=_env_fixture(),
            component_timings=timings,
            end_to_end_total_seconds=timings.total_seconds(),
            target_met=True,
            missed_component=None,
            remediation_or_deferral_note="leftover note",
        )


# --------------------------------------------------------------------------- #
# Pure-function tests (AC-3, AC-4)                                             #
# --------------------------------------------------------------------------- #


def test_evaluate_target_returns_true_when_total_within_budget() -> None:
    target_met, missed = evaluate_target(_green_timings_fixture())
    assert target_met is True
    assert missed is None


def test_evaluate_target_returns_false_with_argmax_when_total_exceeds_budget() -> None:
    target_met, missed = evaluate_target(_missed_target_timings_fixture())
    assert target_met is False
    assert missed == "dev_runtime_seconds"


def test_evaluate_target_appends_aggregate_overage_suffix_when_argmax_within_historical_mean() -> None:
    """AC-4 verbatim: when the argmax-component is itself within its historical-
    mean budget, the field name is suffixed with `+aggregate-overage`.
    """
    timings = _missed_target_timings_fixture()
    # Bootstrap a historical-mean dict where the argmax (dev_runtime_seconds=200)
    # is BELOW its historical mean (250).
    historical_means = {"dev_runtime_seconds": 250.0}
    target_met, missed = evaluate_target(timings, historical_means=historical_means)
    assert target_met is False
    assert missed == "dev_runtime_seconds+aggregate-overage"


def test_render_record_row_produces_deterministic_output() -> None:
    record = _green_record_fixture()
    row1 = render_record_row(record)
    row2 = render_record_row(record)
    assert row1 == row2


def test_render_record_row_renders_check_emoji_for_target_met_true_and_x_emoji_for_false() -> None:
    green = _green_record_fixture()
    missed = _missed_record_fixture()
    assert "✅" in render_record_row(green)
    assert "—" in render_record_row(green)  # missed_component column → em-dash on green
    assert "❌" in render_record_row(missed)
    assert "dev_runtime_seconds" in render_record_row(missed)


# --------------------------------------------------------------------------- #
# Artifact append tests (AC-3)                                                 #
# --------------------------------------------------------------------------- #


def test_append_record_to_artifact_creates_file_when_absent(tmp_path: pathlib.Path) -> None:
    artifact_path = tmp_path / "onboarding-benchmark.md"
    record = _green_record_fixture()

    append_record_to_artifact(record, artifact_path)

    assert artifact_path.exists()
    body = artifact_path.read_text(encoding="utf-8")
    assert "# Onboarding Benchmark" in body
    assert ROWS_BEGIN_ANCHOR in body
    assert ROWS_END_ANCHOR in body
    assert render_record_row(record) in body


def test_append_record_to_artifact_inserts_before_end_anchor(tmp_path: pathlib.Path) -> None:
    artifact_path = tmp_path / "onboarding-benchmark.md"
    artifact_path.write_text(build_artifact_seed(seed_record=None), encoding="utf-8")

    record = _green_record_fixture()
    append_record_to_artifact(record, artifact_path)

    body = artifact_path.read_text(encoding="utf-8")
    rendered_row = render_record_row(record)
    # Use standalone-line search (with leading \n) to avoid matching anchor
    # strings embedded in the preamble text's backtick code spans.
    _begin_nl = body.find("\n" + ROWS_BEGIN_ANCHOR)
    _end_nl = body.find("\n" + ROWS_END_ANCHOR)
    row_idx = body.find(rendered_row)
    assert _begin_nl >= 0 and row_idx >= 0 and _end_nl >= 0
    begin_idx = _begin_nl + 1
    end_idx = _end_nl + 1
    assert begin_idx < row_idx < end_idx


def test_append_record_to_artifact_raises_when_anchors_missing(tmp_path: pathlib.Path) -> None:
    artifact_path = tmp_path / "onboarding-benchmark.md"
    artifact_path.write_text("# Onboarding Benchmark\n\nNo anchors here.\n", encoding="utf-8")
    with pytest.raises(BenchmarkArtifactError) as excinfo:
        append_record_to_artifact(_green_record_fixture(), artifact_path)
    assert excinfo.value.reason == "artifact-anchors-missing"


def test_append_record_to_artifact_raises_when_anchors_out_of_order(tmp_path: pathlib.Path) -> None:
    artifact_path = tmp_path / "onboarding-benchmark.md"
    artifact_path.write_text(
        f"# Onboarding Benchmark\n\n{ROWS_END_ANCHOR}\n\n{ROWS_BEGIN_ANCHOR}\n",
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkArtifactError) as excinfo:
        append_record_to_artifact(_green_record_fixture(), artifact_path)
    assert excinfo.value.reason == "artifact-anchors-missing"


def test_append_record_to_artifact_raises_on_duplicate_row(tmp_path: pathlib.Path) -> None:
    artifact_path = tmp_path / "onboarding-benchmark.md"
    record = _green_record_fixture()

    append_record_to_artifact(record, artifact_path)
    with pytest.raises(BenchmarkArtifactError) as excinfo:
        append_record_to_artifact(record, artifact_path)
    assert excinfo.value.reason == "duplicate-row-detected"

    # A record differing in ALL three key fields must NOT trigger duplicate detection.
    different_record = BenchmarkRecord(
        date="2026-06-01",
        version="0.0.2",
        environment=EnvironmentNotes(
            claude_code_version="2.2.0",
            os_label="linux-5.15.0",
            hardware_tier="ci-runner-standard",
            python_version="3.12.5",
        ),
        component_timings=_green_timings_fixture(),
        end_to_end_total_seconds=_green_timings_fixture().total_seconds(),
        target_met=True,
        missed_component=None,
        remediation_or_deferral_note=None,
    )
    # Must succeed (different triple — not a duplicate).
    append_record_to_artifact(different_record, artifact_path)


def test_append_record_to_artifact_uses_atomic_write(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify the helper at `_atomic_write_text` is invoked (mocked via
    monkey-patch on the module-level symbol).
    """
    artifact_path = tmp_path / "onboarding-benchmark.md"
    captured: list[tuple[pathlib.Path, str]] = []

    def _spy(path: pathlib.Path, body: str) -> None:
        captured.append((path, body))
        path.write_text(body, encoding="utf-8")

    monkeypatch.setattr(onboarding_benchmark, "_atomic_write_text", _spy)
    append_record_to_artifact(_green_record_fixture(), artifact_path)
    assert len(captured) == 1
    assert captured[0][0] == artifact_path
    assert "# Onboarding Benchmark" in captured[0][1]


# --------------------------------------------------------------------------- #
# Reproducibility tests (AC-5)                                                 #
# --------------------------------------------------------------------------- #


def test_run_benchmark_loads_canonical_fixture_byte_equal() -> None:
    """AC-5 byte-equality contract: the benchmark fixture loaded at run-time
    matches the fixture committed at `_data/sample-auto-001.md`.
    """
    import importlib.resources

    assert BENCHMARK_FIXTURE_PATH == CANONICAL_CONTENT_RESOURCE

    # Verify byte-equality: load_sample_story_content() must return the same
    # text as reading the committed package data file directly.
    content_via_api = load_sample_story_content()
    pkg_data = importlib.resources.files("loud_fail_harness").joinpath(BENCHMARK_FIXTURE_PATH)
    content_from_resource = pkg_data.read_text(encoding="utf-8")
    assert content_via_api == content_from_resource


def test_run_benchmark_uses_fresh_reference_project(tmp_path: pathlib.Path) -> None:
    """The reference project root is a caller-provided absolute path; the
    BenchmarkRequest validator enforces absoluteness.
    """
    runner = _FakeRunner()
    request = BenchmarkRequest(
        reference_project_root=tmp_path / "fresh",
        version="0.0.1",
        hardware_tier="developer-laptop",
    )
    request.reference_project_root.mkdir(parents=True, exist_ok=True)
    record = run_benchmark(request, subprocess_runner=runner, today="2026-05-08")
    assert record.date == "2026-05-08"

    with pytest.raises(ValidationError):
        BenchmarkRequest(
            reference_project_root=pathlib.Path("relative/not/absolute"),
            version="0.0.1",
            hardware_tier="developer-laptop",
        )


def test_run_benchmark_raises_on_non_empty_reference_project(tmp_path: pathlib.Path) -> None:
    """AC-8: run_benchmark raises BenchmarkArtifactError when reference project
    root is not empty — a leftover from a prior run violates AC-5 reproducibility.
    """
    non_empty_root = tmp_path / "non_empty"
    non_empty_root.mkdir()
    (non_empty_root / "leftover.txt").write_text("stale", encoding="utf-8")

    runner = _FakeRunner()
    request = BenchmarkRequest(
        reference_project_root=non_empty_root,
        version="0.0.1",
        hardware_tier="developer-laptop",
    )
    with pytest.raises(BenchmarkArtifactError) as excinfo:
        run_benchmark(request, subprocess_runner=runner)
    assert excinfo.value.reason == "phase-subprocess-failed"
    assert excinfo.value.phase == "reference-project-freshness-check"


def test_run_benchmark_probes_claude_code_version_at_runtime(tmp_path: pathlib.Path) -> None:
    """When `claude_code_version` is None, the runner probes via the injected
    subprocess; tests assert the captured version matches the mock's return.
    """
    runner = _FakeRunner(claude_version_stdout="claude 2.1.99\n")
    request = BenchmarkRequest(
        reference_project_root=tmp_path,
        version="0.0.1",
        hardware_tier="developer-laptop",
    )
    record = run_benchmark(request, subprocess_runner=runner, today="2026-05-08")
    assert record.environment.claude_code_version == "2.1.99"

    # When override is supplied, no probe runs.
    runner2 = _FakeRunner()
    request2 = BenchmarkRequest(
        reference_project_root=tmp_path,
        version="0.0.1",
        hardware_tier="developer-laptop",
        claude_code_version="9.9.9",
    )
    record2 = run_benchmark(request2, subprocess_runner=runner2, today="2026-05-08")
    assert record2.environment.claude_code_version == "9.9.9"
    assert not any(list(call[0]) == ["claude", "--version"] for call in runner2.calls)


# --------------------------------------------------------------------------- #
# CLI smoke tests (AC-7, AC-4)                                                 #
# --------------------------------------------------------------------------- #


def _patch_run_benchmark_to_return(
    monkeypatch: pytest.MonkeyPatch, record: BenchmarkRecord
) -> None:
    def _stub(request: BenchmarkRequest, **kwargs: Any) -> BenchmarkRecord:
        return record

    monkeypatch.setattr(onboarding_benchmark, "run_benchmark", _stub)


def test_main_returns_0_on_target_met_dry_run(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_path = tmp_path / "onboarding-benchmark.md"
    _patch_run_benchmark_to_return(monkeypatch, _green_record_fixture())
    rc = main(
        [
            "--hardware-tier",
            "developer-laptop",
            "--version",
            "0.0.1",
            "--reference-project-root",
            str(tmp_path),
            "--artifact-path",
            str(artifact_path),
            "--dry-run",
        ]
    )
    assert rc == 0
    assert not artifact_path.exists()  # dry-run does NOT write.


def test_main_returns_1_on_target_missed_non_dry_run(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_path = tmp_path / "onboarding-benchmark.md"
    _patch_run_benchmark_to_return(monkeypatch, _missed_record_fixture())
    rc = main(
        [
            "--hardware-tier",
            "developer-laptop",
            "--version",
            "0.0.1",
            "--reference-project-root",
            str(tmp_path),
            "--artifact-path",
            str(artifact_path),
        ]
    )
    assert rc == 1
    assert artifact_path.exists()  # missed-target row STILL appended.


def test_main_returns_2_on_benchmark_artifact_error(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inject a malformed artifact (no anchor markers) so append raises
    BenchmarkArtifactError → exit-code 2.
    """
    artifact_path = tmp_path / "onboarding-benchmark.md"
    artifact_path.write_text("malformed; no anchors", encoding="utf-8")
    _patch_run_benchmark_to_return(monkeypatch, _green_record_fixture())
    rc = main(
        [
            "--hardware-tier",
            "developer-laptop",
            "--version",
            "0.0.1",
            "--reference-project-root",
            str(tmp_path),
            "--artifact-path",
            str(artifact_path),
        ]
    )
    assert rc == 2


def test_main_with_dry_run_does_not_write_artifact(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry-run path leaves the artifact untouched."""
    artifact_path = tmp_path / "onboarding-benchmark.md"
    pre_existing = build_artifact_seed(seed_record=None)
    artifact_path.write_text(pre_existing, encoding="utf-8")
    _patch_run_benchmark_to_return(monkeypatch, _missed_record_fixture())
    rc = main(
        [
            "--hardware-tier",
            "developer-laptop",
            "--version",
            "0.0.1",
            "--reference-project-root",
            str(tmp_path),
            "--artifact-path",
            str(artifact_path),
            "--dry-run",
        ]
    )
    assert rc == 0
    assert artifact_path.read_text(encoding="utf-8") == pre_existing


# --------------------------------------------------------------------------- #
# Pluggability gate posture (AC-1)                                             #
# --------------------------------------------------------------------------- #


def test_onboarding_benchmark_is_substrate_library_no_specialist_imports() -> None:
    """The module is shared substrate (sibling of marker_coverage_audit, etc.) —
    NOT a specialist. The pluggability gate is over `agents/`, NOT over
    `tools/loud-fail-harness/src/loud_fail_harness/`, so onboarding_benchmark
    is structurally exempt. This test pins that posture by asserting the
    module's import list contains NO specialist-wrapper references.
    """
    src = pathlib.Path(onboarding_benchmark.__file__).read_text(encoding="utf-8")
    forbidden_specialist_paths = (
        "agents/dev-wrapper.md",
        "agents/review-bmad-wrapper.md",
        "agents/qa.md",
        "agents/lad-wrapper.md",
    )
    for forbidden in forbidden_specialist_paths:
        assert forbidden not in src, (
            f"onboarding_benchmark must not reference {forbidden}; the module is "
            "shared substrate, not a specialist surface."
        )


# --------------------------------------------------------------------------- #
# Released-artifact integration (AC-3)                                         #
# --------------------------------------------------------------------------- #


def test_released_onboarding_benchmark_md_has_required_structure() -> None:
    """The committed `bmad-autopilot/docs/onboarding-benchmark.md` has the
    canonical structure (header + methodology + anchored rows table +
    trailing section). Mirrors test_marker_coverage_audit.py's
    test_canonical_marker_coverage_audit_md_matches_render shape.
    """
    from loud_fail_harness._shared import find_repo_root

    repo_root = find_repo_root()
    artifact_path = repo_root / ARTIFACT_RELATIVE_PATH
    assert artifact_path.exists(), f"missing committed artifact at {artifact_path}"
    body = artifact_path.read_text(encoding="utf-8")
    assert body.startswith("# Onboarding Benchmark (NFR-P3 / FR44)")
    assert "## Methodology" in body
    assert "## Per-release rows" in body
    assert "## Regeneration" in body
    # Section order: Methodology before Per-release rows before Regeneration.
    assert body.index("## Methodology") < body.index("## Per-release rows") < body.index("## Regeneration")
    assert ROWS_BEGIN_ANCHOR in body
    assert ROWS_END_ANCHOR in body
    assert body.find("\n" + ROWS_BEGIN_ANCHOR) < body.find("\n" + ROWS_END_ANCHOR)


# --------------------------------------------------------------------------- #
# Module-level constants pinning (AC-1)                                        #
# --------------------------------------------------------------------------- #


def test_target_first_loop_seconds_is_300() -> None:
    """The 5-minute NFR-P3 budget; mutating this constant requires a
    release-notes flag per FR44's published-commitment posture (AC-1).
    """
    assert TARGET_FIRST_LOOP_SECONDS == 300


def test_artifact_relative_path_canonical() -> None:
    """The artifact lives at `docs/onboarding-benchmark.md` — sibling of
    `docs/marker-coverage-audit.md` and `docs/extension-audit.md`.
    """
    assert ARTIFACT_RELATIVE_PATH == "docs/onboarding-benchmark.md"


def test_benchmark_request_subprocess_runner_injection_seam() -> None:
    """AC-8 verbatim: tests do NOT invoke the actual Claude Code CLI; the unit
    tests stub the subprocess phase via dependency-injection.
    """
    runner = mock.Mock(
        return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="2.1.32", stderr=""
        )
    )
    request = BenchmarkRequest(
        reference_project_root=pathlib.Path("/tmp/fixture-only-not-touched"),
        version="0.0.1",
        hardware_tier="other",
    )
    record = run_benchmark(request, subprocess_runner=runner, today="2026-05-08")
    # The runner was invoked at least once for the version probe + each phase.
    assert runner.called
    assert record.environment.claude_code_version == "2.1.32"
