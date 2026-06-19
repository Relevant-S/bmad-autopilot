"""Story 17.3 — auto-merge execution actuator + ``auto-merge-skipped`` marker."""

from __future__ import annotations

import json
import pathlib
import subprocess
from typing import Any

import pytest
import yaml

from loud_fail_harness import bundle_assembly
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.auto_merge_execution import (
    AUTO_MERGE_SKIPPED_MARKER,
    AutoMergeOutcome,
    AutoMergeSkippedEmission,
    _classify_failure,
    attempt_auto_merge,
    skipped_gate_not_met,
    surface_auto_merge_skipped,
)
from loud_fail_harness.bundle_assembly import (
    _render_auto_merge_skipped_subsection,
    main as bundle_main,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
    load_marker_class_registry,
)

_BRANCH = "bmad-automation/story/sample-auto-001"


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


def _canonical_registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(marker_classes=frozenset({AUTO_MERGE_SKIPPED_MARKER}))


class _RecordingRunner:
    """Pattern-6 stub gh_runner: records each call and returns a synthesized
    :class:`subprocess.CompletedProcess` (or raises a pre-seeded exception)."""

    def __init__(self, result: Any) -> None:
        self._result = result
        self.calls: list[tuple[list[str], Any]] = []

    def __call__(self, args: Any, cwd: Any) -> "subprocess.CompletedProcess[str]":
        self.calls.append((list(args), cwd))
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result


def _completed(returncode: int, stderr: str = "") -> "subprocess.CompletedProcess[str]":
    return subprocess.CompletedProcess(
        args=["gh", "pr", "merge"], returncode=returncode, stdout="", stderr=stderr
    )


# --------------------------------------------------------------------------- #
# AC-3/AC-7 — attempt_auto_merge (injected runner; no real gh/network)        #
# --------------------------------------------------------------------------- #


def test_success_returns_merged_and_runs_squash_on_branch() -> None:
    runner = _RecordingRunner(_completed(0))
    out = attempt_auto_merge(branch_name=_BRANCH, repo_root="/repo", gh_runner=runner)
    assert out == AutoMergeOutcome(status="merged", branch_name=_BRANCH)
    assert runner.calls == [(["pr", "merge", "--squash", _BRANCH], "/repo")]


def test_no_push_force_or_main_in_invocation() -> None:
    runner = _RecordingRunner(_completed(0))
    attempt_auto_merge(branch_name=_BRANCH, repo_root="/repo", gh_runner=runner)
    cmd = runner.calls[0][0]
    joined = " ".join(cmd)
    assert "push" not in joined
    assert "--force" not in joined
    assert "--rebase" not in joined
    assert "--delete-branch" not in joined
    assert "main" not in cmd
    assert "master" not in cmd


def test_conflict_stderr_classifies_merge_conflict() -> None:
    runner = _RecordingRunner(
        _completed(1, stderr="X Pull request is not mergeable: merge conflict")
    )
    out = attempt_auto_merge(branch_name=_BRANCH, repo_root="/repo", gh_runner=runner)
    assert out.status == "skipped"
    assert out.skip_reason == "merge-conflict"
    assert out.gh_returncode == 1
    assert out.gh_stderr is not None and "conflict" in out.gh_stderr.lower()


def test_gh_absent_classifies_gh_unavailable() -> None:
    runner = _RecordingRunner(FileNotFoundError("gh"))
    out = attempt_auto_merge(branch_name=_BRANCH, repo_root="/repo", gh_runner=runner)
    assert out.status == "skipped"
    assert out.skip_reason == "gh-unavailable"
    assert out.gh_returncode is None


def test_generic_nonzero_classifies_merge_failed() -> None:
    runner = _RecordingRunner(_completed(4, stderr="authentication required"))
    out = attempt_auto_merge(branch_name=_BRANCH, repo_root="/repo", gh_runner=runner)
    assert out.status == "skipped"
    assert out.skip_reason == "merge-failed"
    assert out.gh_returncode == 4


def test_timeout_classifies_merge_failed() -> None:
    runner = _RecordingRunner(subprocess.TimeoutExpired(cmd="gh", timeout=60))
    out = attempt_auto_merge(branch_name=_BRANCH, repo_root="/repo", gh_runner=runner)
    assert out.status == "skipped"
    assert out.skip_reason == "merge-failed"
    assert out.gh_stderr is not None and "timed out" in out.gh_stderr


def test_unsupported_strategy_raises() -> None:
    with pytest.raises(ValueError, match="squash"):
        attempt_auto_merge(
            branch_name=_BRANCH,
            repo_root="/repo",
            gh_runner=_RecordingRunner(_completed(0)),
            strategy="merge",  # type: ignore[arg-type]
        )


# --------------------------------------------------------------------------- #
# Story 22.6 AC-7 — the four Story-17.3 actuator failure-classification edges  #
# (each guarded or accept-as-is; see Dev Agent Record + deferred-work.md)      #
# --------------------------------------------------------------------------- #


def test_classify_failure_substrings_pinned() -> None:
    # AC-7(i) — accept-as-is: _classify_failure's stderr substring match is
    # locale/gh-version fragile, but a misclassification only flips
    # merge-conflict <-> merge-failed and BOTH fire auto-merge-skipped loudly.
    # This test PINS the current substrings so a silent change is caught.
    for stderr in (
        "X Pull request is not mergeable: merge conflict",
        "GraphQL: the merge is not mergeable",
        "the branch cannot be cleanly merged onto the base",
    ):
        assert _classify_failure(_completed(1, stderr=stderr)) == "merge-conflict"
    assert _classify_failure(_completed(1, stderr="authentication required")) == "merge-failed"
    assert _classify_failure(_completed(1, stderr="")) == "merge-failed"


def test_empty_branch_name_skips_without_invoking_gh() -> None:
    # AC-7(ii) — guard: empty/whitespace branch_name short-circuits BEFORE gh,
    # mapped to the existing merge-failed SkipReason (no taxonomy bump).
    runner = _RecordingRunner(_completed(0))
    out = attempt_auto_merge(branch_name="   ", repo_root="/repo", gh_runner=runner)
    assert out.status == "skipped"
    assert out.skip_reason == "merge-failed"
    assert runner.calls == []
    assert out.gh_stderr is not None and "empty/whitespace branch_name" in out.gh_stderr


def test_missing_cwd_distinguished_from_missing_gh(tmp_path: pathlib.Path) -> None:
    # AC-7(iv) — guard: a missing cwd (repo_root) is distinguished from a missing
    # gh CLI via the exception filename → honest merge-failed diagnostic.
    missing = tmp_path / "nope"
    runner = _RecordingRunner(
        FileNotFoundError(2, "No such file or directory", str(missing))
    )
    out = attempt_auto_merge(branch_name=_BRANCH, repo_root=missing, gh_runner=runner)
    assert out.status == "skipped"
    assert out.skip_reason == "merge-failed"
    assert out.gh_stderr is not None and "does not exist" in out.gh_stderr


def test_missing_gh_still_classifies_gh_unavailable() -> None:
    # AC-7(iv) — the discriminator must NOT misfire for a genuine missing gh:
    # the exception filename is the executable, not repo_root.
    runner = _RecordingRunner(
        FileNotFoundError(2, "No such file or directory", "gh")
    )
    out = attempt_auto_merge(branch_name=_BRANCH, repo_root="/repo", gh_runner=runner)
    assert out.status == "skipped"
    assert out.skip_reason == "gh-unavailable"


# --------------------------------------------------------------------------- #
# AutoMergeOutcome invariants                                                  #
# --------------------------------------------------------------------------- #


def test_skipped_outcome_requires_reason() -> None:
    with pytest.raises(ValueError, match="skip_reason"):
        AutoMergeOutcome(status="skipped", branch_name=_BRANCH)


def test_merged_outcome_rejects_reason() -> None:
    with pytest.raises(ValueError, match="must not carry"):
        AutoMergeOutcome(
            status="merged", branch_name=_BRANCH, skip_reason="merge-failed"
        )


def test_skipped_gate_not_met_constructor() -> None:
    out = skipped_gate_not_met(_BRANCH)
    assert out.status == "skipped"
    assert out.skip_reason == "gate-not-met"
    assert out.gh_returncode is None and out.gh_stderr is None


# --------------------------------------------------------------------------- #
# AC-4 — surface_auto_merge_skipped emission (validate-first ordering)        #
# --------------------------------------------------------------------------- #


def test_surface_emission_shape_for_gate_not_met() -> None:
    emission = surface_auto_merge_skipped(skipped_gate_not_met(_BRANCH), _canonical_registry())
    assert isinstance(emission, AutoMergeSkippedEmission)
    assert emission.marker_class == AUTO_MERGE_SKIPPED_MARKER
    assert emission.skip_reason == "gate-not-met"
    assert emission.gh_detail is None
    assert "gate-not-met" in emission.diagnostic_pointer
    assert "draft" in emission.diagnostic_pointer


def test_surface_emission_carries_gh_detail_on_execution_failure() -> None:
    out = AutoMergeOutcome(
        status="skipped",
        branch_name=_BRANCH,
        skip_reason="merge-failed",
        gh_returncode=4,
        gh_stderr="authentication required",
    )
    emission = surface_auto_merge_skipped(out, _canonical_registry())
    assert emission.skip_reason == "merge-failed"
    assert emission.gh_detail is not None
    assert "exit=4" in emission.gh_detail
    assert "authentication required" in emission.gh_detail


def test_surface_rejects_merged_outcome() -> None:
    with pytest.raises(ValueError, match="skipped"):
        surface_auto_merge_skipped(
            AutoMergeOutcome(status="merged", branch_name=_BRANCH),
            _canonical_registry(),
        )


def test_surface_validate_marker_emission_runs_first() -> None:
    with pytest.raises(UnknownMarkerClass):
        surface_auto_merge_skipped(
            skipped_gate_not_met(_BRANCH),
            MarkerClassRegistry(marker_classes=frozenset()),
        )


def test_marker_in_canonical_taxonomy(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    assert AUTO_MERGE_SKIPPED_MARKER in runtime_marker_registry.marker_classes


# --------------------------------------------------------------------------- #
# AC-6 — render path (sub-section + marker comment)                           #
# --------------------------------------------------------------------------- #


def test_render_subsection_emits_heading_and_marker_comment() -> None:
    emission = surface_auto_merge_skipped(skipped_gate_not_met(_BRANCH), _canonical_registry())
    body = _render_auto_merge_skipped_subsection(
        emission, marker_registry=_canonical_registry()
    )
    assert "### Auto-merge skipped" in body
    assert f"<!-- bmad-automation:marker {AUTO_MERGE_SKIPPED_MARKER} -->" in body
    assert "gate-not-met" in body


def test_render_subsection_empty_on_none() -> None:
    assert (
        _render_auto_merge_skipped_subsection(None, marker_registry=_canonical_registry())
        == ""
    )


def test_render_subsection_unknown_marker_raises() -> None:
    emission = surface_auto_merge_skipped(skipped_gate_not_met(_BRANCH), _canonical_registry())
    with pytest.raises(UnknownMarkerClass):
        _render_auto_merge_skipped_subsection(
            emission, marker_registry=MarkerClassRegistry(marker_classes=frozenset())
        )


# --------------------------------------------------------------------------- #
# AC-1/2/5/9 — main() end-to-end Stop-hook merge decision                     #
# --------------------------------------------------------------------------- #

_STORY_ID = "sample-auto-001"
_RUN_ID = "run-2026-04-29-001"


def _seed_bundle_inputs(
    tmp_path: pathlib.Path, *, current_state: str = "done"
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
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
                "current_state": current_state,
                "branch_name": _BRANCH,
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
        tmp_path / "_bmad-output" / "qa-evidence" / "sample-001" / _RUN_ID / "ac1-http-200.log"
    )
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("HTTP/1.1 200 OK\n", encoding="utf-8")
    return rs_path, logs_root, tmp_path / "pr-bundles"


def _write_config(tmp_path: pathlib.Path, *, enabled: bool) -> pathlib.Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "auto_merge": {
                    "enabled": enabled,
                    "gate_conditions": {
                        "min_adoption_months": 6,
                        "min_completion_fidelity": 0.9,
                        "max_retry_exhaustion": 0.1,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_metrics(tmp_path: pathlib.Path, *, months: int) -> pathlib.Path:
    path = tmp_path / "adoption-metrics.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "adoption_months": months,
                "completion_fidelity": 0.95,
                "retry_exhaustion": 0.05,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _argv(
    tmp_path: pathlib.Path,
    rs_path: pathlib.Path,
    logs_root: pathlib.Path,
    bundle_root: pathlib.Path,
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


def _patch_attempt(
    monkeypatch: pytest.MonkeyPatch, runner: _RecordingRunner
) -> None:
    """Route main()'s actuator call through the REAL attempt_auto_merge with an
    injected recording runner — so the gh command construction + classification
    are exercised, only the subprocess is stubbed."""

    def fake(*, branch_name: str, repo_root: Any) -> AutoMergeOutcome:
        return attempt_auto_merge(
            branch_name=branch_name, repo_root=repo_root, gh_runner=runner
        )

    monkeypatch.setattr(bundle_assembly, "attempt_auto_merge", fake)


def test_main_enabled_green_done_merges_no_skip_marker(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-2/AC-9: enabled + gate green + merge-ready → gh pr merge --squash fires
    # and succeeds; NO auto-merge-skipped marker; exit 0. This is the Epic-23
    # reference-run witness for a successful auto-merge.
    rs_path, logs_root, bundle_root = _seed_bundle_inputs(tmp_path)
    runner = _RecordingRunner(_completed(0))
    _patch_attempt(monkeypatch, runner)
    rc = bundle_main(
        _argv(
            tmp_path, rs_path, logs_root, bundle_root,
            _write_config(tmp_path, enabled=True),
            _write_metrics(tmp_path, months=12),
        )
    )
    assert rc == 0
    assert runner.calls == [(["pr", "merge", "--squash", _BRANCH], tmp_path)]
    body = (bundle_root / _STORY_ID / f"{_RUN_ID}.md").read_text(encoding="utf-8")
    assert "### Auto-merge skipped" not in body
    assert AUTO_MERGE_SKIPPED_MARKER not in body


def test_main_enabled_green_done_merge_fails_emits_skip(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-5: armed + green + merge-ready but gh fails → auto-merge-skipped rendered,
    # PR left in draft, exit 0 (the skip is loud-fail DATA, not a bundle failure).
    rs_path, logs_root, bundle_root = _seed_bundle_inputs(tmp_path)
    runner = _RecordingRunner(_completed(1, stderr="not mergeable: merge conflict"))
    _patch_attempt(monkeypatch, runner)
    rc = bundle_main(
        _argv(
            tmp_path, rs_path, logs_root, bundle_root,
            _write_config(tmp_path, enabled=True),
            _write_metrics(tmp_path, months=12),
        )
    )
    assert rc == 0
    body = (bundle_root / _STORY_ID / f"{_RUN_ID}.md").read_text(encoding="utf-8")
    assert "### Auto-merge skipped" in body
    assert f"<!-- bmad-automation:marker {AUTO_MERGE_SKIPPED_MARKER} -->" in body
    assert "merge-conflict" in body


def test_main_enabled_gate_not_met_done_emits_skip_gate_not_met(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-5: enabled + merge-ready but gate not green → auto-merge-skipped:gate-not-met,
    # NO gh invocation.
    rs_path, logs_root, bundle_root = _seed_bundle_inputs(tmp_path)
    sentinel = _RecordingRunner(_completed(0))
    _patch_attempt(monkeypatch, sentinel)
    rc = bundle_main(
        _argv(
            tmp_path, rs_path, logs_root, bundle_root,
            _write_config(tmp_path, enabled=True),
            _write_metrics(tmp_path, months=2),  # fails min_adoption_months >= 6
        )
    )
    assert rc == 0
    assert sentinel.calls == []  # no merge attempted on gate-not-met
    body = (bundle_root / _STORY_ID / f"{_RUN_ID}.md").read_text(encoding="utf-8")
    assert "### Auto-merge skipped" in body
    assert "gate-not-met" in body


def test_main_disabled_default_no_merge_no_marker(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-5: enabled:false (shipped default) → no merge attempt, NO auto-merge-skipped.
    rs_path, logs_root, bundle_root = _seed_bundle_inputs(tmp_path)
    sentinel = _RecordingRunner(_completed(0))
    _patch_attempt(monkeypatch, sentinel)
    rc = bundle_main(
        _argv(
            tmp_path, rs_path, logs_root, bundle_root,
            _write_config(tmp_path, enabled=False),
            _write_metrics(tmp_path, months=12),
        )
    )
    assert rc == 0
    assert sentinel.calls == []
    body = (bundle_root / _STORY_ID / f"{_RUN_ID}.md").read_text(encoding="utf-8")
    assert AUTO_MERGE_SKIPPED_MARKER not in body


def test_main_not_merge_ready_no_merge(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-2: current_state != "done" (escalated) → no merge call, no skip marker.
    rs_path, logs_root, bundle_root = _seed_bundle_inputs(
        tmp_path, current_state="escalated"
    )
    sentinel = _RecordingRunner(_completed(0))
    _patch_attempt(monkeypatch, sentinel)
    rc = bundle_main(
        _argv(
            tmp_path, rs_path, logs_root, bundle_root,
            _write_config(tmp_path, enabled=True),
            _write_metrics(tmp_path, months=12),
        )
    )
    assert rc == 0
    assert sentinel.calls == []
    body = (bundle_root / _STORY_ID / f"{_RUN_ID}.md").read_text(encoding="utf-8")
    assert AUTO_MERGE_SKIPPED_MARKER not in body


def test_main_gate_config_error_no_merge_no_marker(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # gate_decision is None (AutoMergeGateError: malformed adoption-metrics with
    # enabled:true) → do NOT merge, NO auto-merge-skipped marker. The 17.2
    # gate-error subsection is the loud signal; the merge block is skipped.
    rs_path, logs_root, bundle_root = _seed_bundle_inputs(tmp_path)
    sentinel = _RecordingRunner(_completed(0))
    _patch_attempt(monkeypatch, sentinel)
    metrics_path = tmp_path / "adoption-metrics.yaml"
    metrics_path.write_text("not: valid: yaml: [", encoding="utf-8")
    rc = bundle_main(
        _argv(
            tmp_path, rs_path, logs_root, bundle_root,
            _write_config(tmp_path, enabled=True),
            metrics_path,
        )
    )
    assert rc == 0
    assert sentinel.calls == []
    body = (bundle_root / _STORY_ID / f"{_RUN_ID}.md").read_text(encoding="utf-8")
    assert AUTO_MERGE_SKIPPED_MARKER not in body


def test_main_armed_story_id_mismatch_is_loud_not_silent(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # AC-7(iii) — guard: an armed (enabled) auto-merge whose run-state story_id
    # does not match the requested --story-id must NOT silently drop the
    # armed-merge intent. The run loud-fails (exit 1 via the assembler's
    # authoritative RunStateStoryIdMismatch) and the arming site emits a loud
    # AutoMergeArmingStoryIdMismatch diagnostic; the merge actuator is NOT called.
    rs_path, logs_root, bundle_root = _seed_bundle_inputs(tmp_path)
    runner = _RecordingRunner(_completed(0))
    _patch_attempt(monkeypatch, runner)
    argv = [
        "--story-id", "other-story-99",
        "--run-id", _RUN_ID,
        "--run-state-path", str(rs_path),
        "--logs-root", str(logs_root),
        "--bundle-root", str(bundle_root),
        "--repo-root", str(tmp_path),
        "--auto-merge-config-path", str(_write_config(tmp_path, enabled=True)),
        "--adoption-metrics-path", str(_write_metrics(tmp_path, months=12)),
    ]
    rc = bundle_main(argv)
    assert rc == 1
    assert runner.calls == []
    assert "AutoMergeArmingStoryIdMismatch" in capsys.readouterr().err
