"""Contract-coverage matrix for the retry-history externalization
substrate (Story 5.5).

AC mapping:

* AC-1 — module imports cleanly + ``__all__`` shape.
* AC-3 — :func:`persist_retry_round` writes per-round artifacts to
  canonical disk locations atomically; ordering invariant verified
  via the :func:`advance_run_state` pairing test.
* AC-4 — :func:`resolve_retry_round` lazy-loads artifacts;
  :exc:`DanglingRetryRoundRef` on missing path; :exc:`RetryHistoryError`
  on YAML-parse failure / schema-mismatch.
* AC-5 — :func:`detect_dangling_refs` purity invariant +
  order-preservation cases.
* AC-6 — :func:`_main` CLI integration covers clean / dangling /
  pre-thickening-MVP / mixed / missing-run-state cases with byte-stable
  output.

Per epics.md verbatim discipline, this test module exercises ONLY the
substrate under :mod:`loud_fail_harness.retry_history`; it does NOT
import :mod:`loud_fail_harness.retry_router` or
:mod:`loud_fail_harness.retry_dispatch` (the substrate is consumed
AS-IS at the orchestrator-skill layer; THIS module accepts already-
extracted ``findings`` / ``scope`` tuples).
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness.retry_history import (
    DANGLING_EVIDENCE_REF_MARKER,
    DanglingRetryRoundRef,
    RetryAttemptRef,
    RetryHistoryError,
    RetryRoundArtifacts,
    _main,
    compute_artifacts_path,
    compute_round_dir,
    default_artifact_writer,
    detect_dangling_refs,
    persist_retry_round,
    resolve_retry_round,
)
from loud_fail_harness.run_state import (
    CostToDateBySpecialist,
    RetryAttempt,
    RunState,
    RunStateAdvanceBlocked,
    StoryDocCallbackBlocked,
    StoryDocCallbackResult,
    advance_run_state,
)


# --------------------------------------------------------------------------- #
# Helpers / fixtures                                                          #
# --------------------------------------------------------------------------- #


def _make_round(
    *,
    round_id: str = "round-01",
    retry_attempt: int = 1,
    findings: tuple[dict[str, Any], ...] = (
        {"id": "patch-1", "severity": "med"},
    ),
    scope_affected_files: tuple[str, ...] = ("src/foo.py",),
    scope_expanded_to: tuple[str, ...] = (),
    actual_diff_files: tuple[str, ...] = ("src/foo.py",),
    created_at: str = "2026-05-04T00:00:00+00:00",
) -> RetryRoundArtifacts:
    return RetryRoundArtifacts(
        round_id=round_id,
        retry_attempt=retry_attempt,
        findings=findings,
        scope_affected_files=scope_affected_files,
        scope_expanded_to=scope_expanded_to,
        actual_diff_files=actual_diff_files,
        created_at=created_at,
    )


def _make_ref(
    *,
    retry_attempt: int = 1,
    retry_reason: str = "patch-bucket-retry",
    round_id: str = "round-01",
    path: str = "_bmad-output/retry-history/5-5-foo/round-01/artifacts.yaml",
) -> RetryAttemptRef:
    return RetryAttemptRef(
        retry_attempt=retry_attempt,
        retry_reason=retry_reason,
        round_id=round_id,
        path=path,
    )


class _RecordingWriter:
    """Test double for :data:`ArtifactWriter`. Records every call;
    does NOT touch disk."""

    def __init__(self) -> None:
        self.calls: list[tuple[pathlib.Path, str]] = []

    def __call__(self, target_path: pathlib.Path, body: str) -> None:
        self.calls.append((target_path, body))


# --------------------------------------------------------------------------- #
# AC-1 — module shape + import smoke                                          #
# --------------------------------------------------------------------------- #


def test_module_all_exports_alphabetically_sorted() -> None:
    from loud_fail_harness import retry_history as mod

    assert list(mod.__all__) == sorted(mod.__all__)
    expected = {
        "ArtifactWriter",
        "DanglingRetryRoundRef",
        "RetryAttemptRef",
        "RetryHistoryError",
        "RetryRoundArtifacts",
        "compute_artifacts_path",
        "compute_round_dir",
        "default_artifact_writer",
        "detect_dangling_refs",
        "persist_retry_round",
        "resolve_retry_round",
    }
    assert set(mod.__all__) == expected


def test_dangling_marker_constant_value() -> None:
    """Marker class string is sourced VERBATIM from
    schemas/marker-taxonomy.yaml line 199 (REUSE per epics.md line
    2379)."""
    assert DANGLING_EVIDENCE_REF_MARKER == "dangling-evidence-ref"


def test_dangling_retry_round_ref_marker_class_classvar() -> None:
    assert DanglingRetryRoundRef.marker_class == "dangling-evidence-ref"


# --------------------------------------------------------------------------- #
# Path helpers                                                                #
# --------------------------------------------------------------------------- #


def test_compute_round_dir_concatenates_repo_story_round(
    tmp_path: pathlib.Path,
) -> None:
    out = compute_round_dir(
        repo_root=tmp_path, story_id="5-5-foo", round_id="round-01"
    )
    assert out == tmp_path / "_bmad-output" / "retry-history" / "5-5-foo" / "round-01"


def test_compute_round_dir_rejects_empty_story(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="story_id"):
        compute_round_dir(
            repo_root=tmp_path, story_id="", round_id="round-01"
        )


def test_compute_round_dir_rejects_empty_round(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="round_id"):
        compute_round_dir(
            repo_root=tmp_path, story_id="5-5-foo", round_id=""
        )


def test_compute_round_dir_rejects_path_traversal_story(
    tmp_path: pathlib.Path,
) -> None:
    with pytest.raises(ValueError, match=r"\.\."):
        compute_round_dir(
            repo_root=tmp_path, story_id="../etc", round_id="round-01"
        )


def test_compute_round_dir_rejects_path_traversal_round(
    tmp_path: pathlib.Path,
) -> None:
    with pytest.raises(ValueError, match=r"\.\."):
        compute_round_dir(
            repo_root=tmp_path, story_id="5-5-foo", round_id="../etc"
        )


def test_compute_round_dir_rejects_absolute_story(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        compute_round_dir(
            repo_root=tmp_path, story_id="/etc/passwd", round_id="round-01"
        )


def test_compute_round_dir_rejects_absolute_round(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        compute_round_dir(
            repo_root=tmp_path, story_id="5-5-foo", round_id="/etc"
        )


def test_resolve_retry_round_traversal_in_ref_path_raises_history_error(
    tmp_path: pathlib.Path,
) -> None:
    ref = _make_ref(path="../../../etc/passwd")
    with pytest.raises(RetryHistoryError) as excinfo:
        resolve_retry_round(ref=ref, repo_root=tmp_path)
    assert not isinstance(excinfo.value, DanglingRetryRoundRef)
    assert "traversal" in str(excinfo.value)


def test_resolve_retry_round_absolute_ref_path_raises_history_error(
    tmp_path: pathlib.Path,
) -> None:
    ref = _make_ref(path="/etc/passwd")
    with pytest.raises(RetryHistoryError) as excinfo:
        resolve_retry_round(ref=ref, repo_root=tmp_path)
    assert not isinstance(excinfo.value, DanglingRetryRoundRef)


# ---------------------------------------------------------------------------
# _detect_corrupted_refs
# ---------------------------------------------------------------------------


def test_detect_corrupted_refs_empty(tmp_path: pathlib.Path) -> None:
    from loud_fail_harness.retry_history import _detect_corrupted_refs

    assert _detect_corrupted_refs(refs=(), repo_root=tmp_path) == ()


def test_detect_corrupted_refs_clean_refs_excluded(tmp_path: pathlib.Path) -> None:
    from loud_fail_harness.retry_history import _detect_corrupted_refs

    ref = _persist(tmp_path, round_id="round-01", retry_attempt=1)
    assert _detect_corrupted_refs(refs=(ref,), repo_root=tmp_path) == ()


def test_detect_corrupted_refs_dangling_excluded(tmp_path: pathlib.Path) -> None:
    from loud_fail_harness.retry_history import _detect_corrupted_refs

    ref = _make_ref(path="nonexistent/artifacts.yaml")
    assert _detect_corrupted_refs(refs=(ref,), repo_root=tmp_path) == ()


def test_detect_corrupted_refs_corrupted_included(tmp_path: pathlib.Path) -> None:
    from loud_fail_harness.retry_history import _detect_corrupted_refs

    target = (
        tmp_path
        / "_bmad-output"
        / "retry-history"
        / "5-5-foo"
        / "round-01"
        / "artifacts.yaml"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[: corrupted yaml", encoding="utf-8")
    ref = _make_ref()
    result = _detect_corrupted_refs(refs=(ref,), repo_root=tmp_path)
    assert result == (ref,)


# ---------------------------------------------------------------------------
# Updated _main: exit 1 on malformed/corrupted thickened entries
# ---------------------------------------------------------------------------


def test_main_corrupted_artifact_exits_one(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Corrupted-but-present artifact: _main exits 1 and emits stderr
    diagnostic (previously exited 0, silently hiding the corruption)."""
    target = (
        tmp_path
        / "_bmad-output"
        / "retry-history"
        / "5-5-foo"
        / "round-01"
        / "artifacts.yaml"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[: corrupted yaml", encoding="utf-8")
    rs_path = tmp_path / "run-state.yaml"
    _write_run_state_yaml(
        rs_path,
        retry_history=[
            {
                "retry_attempt": 1,
                "retry_reason": "patch-bucket-retry",
                "round_id": "round-01",
                "path": "_bmad-output/retry-history/5-5-foo/round-01/artifacts.yaml",
            }
        ],
    )
    rc = _main(["--run-state", str(rs_path), "--repo-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "retry-history-corrupted" in captured.err


def test_main_malformed_thickened_entry_missing_retry_reason_exits_one(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Thickened entry (has path+round_id) with missing retry_reason:
    _main emits a suspicious-entry warning and exits 1."""
    rs_path = tmp_path / "run-state.yaml"
    _write_run_state_yaml(
        rs_path,
        retry_history=[
            {
                "retry_attempt": 1,
                "round_id": "round-01",
                "path": "_bmad-output/retry-history/5-5-foo/round-01/artifacts.yaml",
                # retry_reason intentionally absent
            }
        ],
    )
    rc = _main(["--run-state", str(rs_path), "--repo-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "malformed" in captured.err


def test_compute_artifacts_path_returns_artifacts_yaml(
    tmp_path: pathlib.Path,
) -> None:
    round_dir = tmp_path / "5-5-foo" / "round-01"
    out = compute_artifacts_path(round_dir)
    assert out == round_dir / "artifacts.yaml"


# --------------------------------------------------------------------------- #
# Pydantic model invariants                                                   #
# --------------------------------------------------------------------------- #


def test_retry_round_artifacts_invalid_round_id_rejected() -> None:
    with pytest.raises(ValidationError):
        RetryRoundArtifacts(
            round_id="invalid",
            retry_attempt=1,
            findings=(),
            scope_affected_files=("src/foo.py",),
            scope_expanded_to=(),
            actual_diff_files=(),
            created_at="2026-05-04T00:00:00+00:00",
        )


def test_retry_round_artifacts_empty_scope_rejected() -> None:
    with pytest.raises(ValidationError):
        RetryRoundArtifacts(
            round_id="round-01",
            retry_attempt=1,
            findings=(),
            scope_affected_files=(),
            scope_expanded_to=(),
            actual_diff_files=(),
            created_at="2026-05-04T00:00:00+00:00",
        )


def test_retry_round_artifacts_frozen() -> None:
    r = _make_round()
    with pytest.raises(ValidationError):
        r.round_id = "round-99"  # type: ignore[misc]


def test_retry_attempt_ref_to_retry_attempt_round_trip() -> None:
    ref = _make_ref()
    attempt = ref.to_retry_attempt()
    assert attempt.retry_attempt == ref.retry_attempt
    assert attempt.retry_reason == ref.retry_reason
    assert attempt.round_id == ref.round_id
    assert attempt.path == ref.path


def test_retry_attempt_ref_invalid_round_id_rejected() -> None:
    with pytest.raises(ValidationError):
        RetryAttemptRef(
            retry_attempt=1,
            retry_reason="x",
            round_id="round_01",  # underscore is wrong
            path="some/path",
        )


# --------------------------------------------------------------------------- #
# AC-3 — persist_retry_round                                                  #
# --------------------------------------------------------------------------- #


def test_persist_retry_round_in_memory_writer(
    tmp_path: pathlib.Path,
) -> None:
    writer = _RecordingWriter()
    round = _make_round()
    ref = persist_retry_round(
        round=round,
        repo_root=tmp_path,
        story_id="5-5-foo",
        retry_reason="patch-bucket-retry",
        writer=writer,
    )
    assert len(writer.calls) == 1
    target_path, body = writer.calls[0]
    assert target_path == (
        tmp_path
        / "_bmad-output"
        / "retry-history"
        / "5-5-foo"
        / "round-01"
        / "artifacts.yaml"
    )
    parsed = yaml.safe_load(body)
    assert parsed["round_id"] == "round-01"
    assert parsed["retry_attempt"] == 1
    assert parsed["scope_affected_files"] == ["src/foo.py"]
    assert ref == RetryAttemptRef(
        retry_attempt=1,
        retry_reason="patch-bucket-retry",
        round_id="round-01",
        path="_bmad-output/retry-history/5-5-foo/round-01/artifacts.yaml",
    )


def test_persist_retry_round_default_writer_round_trip(
    tmp_path: pathlib.Path,
) -> None:
    round = _make_round(round_id="round-02", retry_attempt=2)
    ref = persist_retry_round(
        round=round,
        repo_root=tmp_path,
        story_id="5-5-bar",
        retry_reason="patch-bucket-retry",
    )
    on_disk = tmp_path / pathlib.PurePosixPath(ref.path)
    assert on_disk.exists()
    loaded = resolve_retry_round(ref=ref, repo_root=tmp_path)
    assert loaded == round


def test_persist_retry_round_writer_exception_propagates(
    tmp_path: pathlib.Path,
) -> None:
    def _raising_writer(target_path: pathlib.Path, body: str) -> None:
        raise OSError("disk full simulation")

    with pytest.raises(OSError, match="disk full simulation"):
        persist_retry_round(
            round=_make_round(),
            repo_root=tmp_path,
            story_id="5-5-foo",
            retry_reason="patch-bucket-retry",
            writer=_raising_writer,
        )


def test_persist_retry_round_invalid_story_id_raises_value_error(
    tmp_path: pathlib.Path,
) -> None:
    writer = _RecordingWriter()
    with pytest.raises(ValueError):
        persist_retry_round(
            round=_make_round(),
            repo_root=tmp_path,
            story_id="",
            retry_reason="x",
            writer=writer,
        )
    assert writer.calls == []


# --------------------------------------------------------------------------- #
# AC-3 ordering smoke — pairing with advance_run_state                        #
# --------------------------------------------------------------------------- #


def _minimal_run_state(**overrides: Any) -> RunState:
    base: dict[str, Any] = {
        "schema_version": "1.2",
        "story_id": "5-5-foo",
        "run_id": "run-001",
        "current_state": "in-progress",
        "branch_name": "feature/5-5",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": (),
        "active_markers": (),
        "cost_to_date_by_specialist": CostToDateBySpecialist(),
    }
    base.update(overrides)
    return RunState(**base)


def test_pairing_with_advance_run_state_persists_then_advances(
    tmp_path: pathlib.Path,
) -> None:
    """The canonical pattern: persist per-round artifact first via the
    callback, advance run-state on success.

    On callback success the run-state file ends up updated; the
    per-round artifact is on disk before the run-state writes."""
    run_state_path = tmp_path / "run-state.yaml"
    run_state_path.write_text(
        yaml.safe_dump(
            json.loads(_minimal_run_state().model_dump_json()),
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    captured_ref: dict[str, RetryAttemptRef | None] = {"ref": None}

    def _cb() -> StoryDocCallbackResult:
        try:
            captured_ref["ref"] = persist_retry_round(
                round=_make_round(),
                repo_root=tmp_path,
                story_id="5-5-foo",
                retry_reason="patch-bucket-retry",
            )
        except Exception as exc:
            raise StoryDocCallbackBlocked(str(exc)) from exc
        return StoryDocCallbackResult(accepted=True)

    next_state = _minimal_run_state(
        retry_history=(
            RetryAttempt(
                retry_attempt=1,
                retry_reason="patch-bucket-retry",
                round_id="round-01",
                path=(
                    "_bmad-output/retry-history/5-5-foo/round-01/"
                    "artifacts.yaml"
                ),
            ),
        ),
    )

    advance_run_state(
        run_state_path=run_state_path,
        next_state=next_state,
        story_doc_callback=_cb,
    )

    # Per-round artifact on disk.
    assert captured_ref["ref"] is not None
    artifact_path = tmp_path / pathlib.PurePosixPath(captured_ref["ref"].path)
    assert artifact_path.exists()

    # Run-state advanced with thickened RetryAttempt.
    on_disk = yaml.safe_load(run_state_path.read_text(encoding="utf-8"))
    assert on_disk["retry_history"][0]["round_id"] == "round-01"
    assert on_disk["retry_history"][0]["path"].endswith(
        "round-01/artifacts.yaml"
    )


def test_pairing_persist_failure_blocks_advance(
    tmp_path: pathlib.Path,
) -> None:
    """If the per-round artifact write fails inside the callback, the
    run-state advance is BLOCKED — the prior run-state file content is
    unchanged on disk per NFR-R8."""
    run_state_path = tmp_path / "run-state.yaml"
    initial = _minimal_run_state()
    initial_body = yaml.safe_dump(
        json.loads(initial.model_dump_json()), sort_keys=False
    )
    run_state_path.write_text(initial_body, encoding="utf-8")

    def _raising_writer(target_path: pathlib.Path, body: str) -> None:
        raise OSError("simulated persist failure")

    def _cb() -> StoryDocCallbackResult:
        try:
            persist_retry_round(
                round=_make_round(),
                repo_root=tmp_path,
                story_id="5-5-foo",
                retry_reason="patch-bucket-retry",
                writer=_raising_writer,
            )
        except Exception as exc:
            raise StoryDocCallbackBlocked(str(exc)) from exc
        return StoryDocCallbackResult(accepted=True)

    next_state = _minimal_run_state(current_state="review")

    with pytest.raises(RunStateAdvanceBlocked):
        advance_run_state(
            run_state_path=run_state_path,
            next_state=next_state,
            story_doc_callback=_cb,
        )

    # Run-state on disk is byte-identical to the initial content.
    assert run_state_path.read_text(encoding="utf-8") == initial_body


# --------------------------------------------------------------------------- #
# AC-4 — resolve_retry_round                                                  #
# --------------------------------------------------------------------------- #


def test_resolve_retry_round_happy_round_trip(tmp_path: pathlib.Path) -> None:
    round = _make_round()
    ref = persist_retry_round(
        round=round,
        repo_root=tmp_path,
        story_id="5-5-foo",
        retry_reason="patch-bucket-retry",
    )
    loaded = resolve_retry_round(ref=ref, repo_root=tmp_path)
    assert loaded == round


def test_resolve_retry_round_missing_path_raises_dangling(
    tmp_path: pathlib.Path,
) -> None:
    ref = _make_ref(path="nowhere/artifacts.yaml")
    with pytest.raises(DanglingRetryRoundRef) as excinfo:
        resolve_retry_round(ref=ref, repo_root=tmp_path)
    err = excinfo.value
    assert err.marker_class == "dangling-evidence-ref"
    assert err.ref == ref
    msg = str(err)
    assert "nowhere/artifacts.yaml" in msg
    assert "regenerate the evidence OR fix the reference" in msg


def test_resolve_retry_round_corrupted_yaml_raises_history_error(
    tmp_path: pathlib.Path,
) -> None:
    target = (
        tmp_path
        / "_bmad-output"
        / "retry-history"
        / "5-5-foo"
        / "round-01"
        / "artifacts.yaml"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not: valid: yaml: at: all: :\n", encoding="utf-8")
    ref = _make_ref()
    with pytest.raises(RetryHistoryError) as excinfo:
        resolve_retry_round(ref=ref, repo_root=tmp_path)
    # Distinct from DanglingRetryRoundRef — the lineage is load-bearing.
    assert not isinstance(excinfo.value, DanglingRetryRoundRef)
    assert isinstance(excinfo.value.__cause__, yaml.YAMLError)


def test_resolve_retry_round_schema_mismatch_raises_history_error(
    tmp_path: pathlib.Path,
) -> None:
    target = (
        tmp_path
        / "_bmad-output"
        / "retry-history"
        / "5-5-foo"
        / "round-01"
        / "artifacts.yaml"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump({"retry_attempt": 1, "scope_affected_files": ["x"]}),
        encoding="utf-8",
    )
    ref = _make_ref()
    with pytest.raises(RetryHistoryError) as excinfo:
        resolve_retry_round(ref=ref, repo_root=tmp_path)
    assert not isinstance(excinfo.value, DanglingRetryRoundRef)
    assert isinstance(excinfo.value.__cause__, ValidationError)


# --------------------------------------------------------------------------- #
# AC-5 — detect_dangling_refs                                                 #
# --------------------------------------------------------------------------- #


def _persist(
    tmp_path: pathlib.Path,
    *,
    round_id: str,
    retry_attempt: int,
) -> RetryAttemptRef:
    return persist_retry_round(
        round=_make_round(round_id=round_id, retry_attempt=retry_attempt),
        repo_root=tmp_path,
        story_id="5-5-foo",
        retry_reason="patch-bucket-retry",
    )


def test_detect_dangling_refs_all_clean(tmp_path: pathlib.Path) -> None:
    refs = (
        _persist(tmp_path, round_id="round-01", retry_attempt=1),
        _persist(tmp_path, round_id="round-02", retry_attempt=2),
    )
    assert detect_dangling_refs(refs=refs, repo_root=tmp_path) == ()


def test_detect_dangling_refs_all_dangling(tmp_path: pathlib.Path) -> None:
    refs = (
        _make_ref(round_id="round-01", path="missing/01.yaml"),
        _make_ref(round_id="round-02", path="missing/02.yaml"),
    )
    assert detect_dangling_refs(refs=refs, repo_root=tmp_path) == refs


def test_detect_dangling_refs_mixed_preserves_order(
    tmp_path: pathlib.Path,
) -> None:
    a_dangling = _make_ref(round_id="round-01", path="missing/a.yaml")
    b_clean = _persist(tmp_path, round_id="round-02", retry_attempt=2)
    c_dangling = _make_ref(round_id="round-03", path="missing/c.yaml")
    d_clean = _persist(tmp_path, round_id="round-04", retry_attempt=4)
    refs = (a_dangling, b_clean, c_dangling, d_clean)
    assert detect_dangling_refs(refs=refs, repo_root=tmp_path) == (
        a_dangling,
        c_dangling,
    )


def test_detect_dangling_refs_empty_input(tmp_path: pathlib.Path) -> None:
    assert detect_dangling_refs(refs=(), repo_root=tmp_path) == ()


def test_detect_dangling_refs_corrupted_excluded_from_dangling_set(
    tmp_path: pathlib.Path,
) -> None:
    """Corrupted-but-present is NOT classified as dangling per the
    AC-5 contract; the function silently excludes from the dangling-
    set (the CLI consumer surfaces both kinds separately)."""
    target = (
        tmp_path
        / "_bmad-output"
        / "retry-history"
        / "5-5-foo"
        / "round-01"
        / "artifacts.yaml"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[: corrupted yaml", encoding="utf-8")
    ref = _make_ref()
    assert detect_dangling_refs(refs=(ref,), repo_root=tmp_path) == ()


# --------------------------------------------------------------------------- #
# AC-6 — _main CLI                                                            #
# --------------------------------------------------------------------------- #


def _write_run_state_yaml(
    path: pathlib.Path,
    *,
    retry_history: list[dict[str, Any]],
) -> None:
    rs_doc = {
        "schema_version": "1.2",
        "story_id": "5-5-foo",
        "run_id": "run-001",
        "current_state": "in-progress",
        "branch_name": "feature/5-5",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": retry_history,
        "active_markers": [],
        "cost_to_date_by_specialist": {},
    }
    path.write_text(yaml.safe_dump(rs_doc, sort_keys=False), encoding="utf-8")


def test_main_clean_run_exits_zero(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ref1 = _persist(tmp_path, round_id="round-01", retry_attempt=1)
    ref2 = _persist(tmp_path, round_id="round-02", retry_attempt=2)
    rs_path = tmp_path / "run-state.yaml"
    _write_run_state_yaml(
        rs_path,
        retry_history=[
            ref1.model_dump(),
            ref2.model_dump(),
        ],
    )
    rc = _main(["--run-state", str(rs_path), "--repo-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "retry-history: clean (rounds=2)" in captured.out
    assert captured.err == ""


def test_main_dangling_run_exits_one(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rs_path = tmp_path / "run-state.yaml"
    _write_run_state_yaml(
        rs_path,
        retry_history=[
            {
                "retry_attempt": 1,
                "retry_reason": "patch-bucket-retry",
                "round_id": "round-01",
                "path": "_bmad-output/retry-history/5-5-foo/round-01/artifacts.yaml",
            },
        ],
    )
    rc = _main(["--run-state", str(rs_path), "--repo-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "dangling-evidence-ref" in captured.err
    assert "round-01" in captured.err
    assert "regenerate the evidence OR fix the reference" in captured.err


def test_main_pre_thickening_entries_skipped(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pre-Story-5.5 entries (no round_id / no path) are skipped — they
    predate externalization and are not dangling."""
    rs_path = tmp_path / "run-state.yaml"
    _write_run_state_yaml(
        rs_path,
        retry_history=[
            {"retry_attempt": 1, "retry_reason": "old-style-retry"},
            {"retry_attempt": 2, "retry_reason": "old-style-retry"},
        ],
    )
    rc = _main(["--run-state", str(rs_path), "--repo-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "retry-history: clean (rounds=0)" in captured.out


def test_main_mixed_only_thickened_dangling_surfaced(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ref_clean = _persist(tmp_path, round_id="round-02", retry_attempt=2)
    rs_path = tmp_path / "run-state.yaml"
    _write_run_state_yaml(
        rs_path,
        retry_history=[
            ref_clean.model_dump(),
            {
                "retry_attempt": 3,
                "retry_reason": "patch-bucket-retry",
                "round_id": "round-03",
                "path": "_bmad-output/retry-history/5-5-foo/round-03/artifacts.yaml",
            },
            {"retry_attempt": 1, "retry_reason": "old-style-retry"},
        ],
    )
    rc = _main(["--run-state", str(rs_path), "--repo-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 1
    assert "round-03" in captured.err
    assert "round-02" not in captured.err
    assert "dangling_count=1" in captured.err


def test_main_missing_run_state_file_exits_nonzero(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _main(
        [
            "--run-state",
            str(tmp_path / "no-such-file.yaml"),
            "--repo-root",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert "run-state not found" in captured.err


def test_main_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        _main(["--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "retry-history-resolve" in captured.out


# --------------------------------------------------------------------------- #
# Determinism                                                                 #
# --------------------------------------------------------------------------- #


def test_serialization_deterministic_byte_stable(
    tmp_path: pathlib.Path,
) -> None:
    """Two persistences of equal RetryRoundArtifacts produce byte-
    identical bodies (load-bearing field declaration order)."""
    writer1 = _RecordingWriter()
    writer2 = _RecordingWriter()
    round = _make_round()
    persist_retry_round(
        round=round,
        repo_root=tmp_path,
        story_id="5-5-foo",
        retry_reason="patch-bucket-retry",
        writer=writer1,
    )
    persist_retry_round(
        round=round,
        repo_root=tmp_path,
        story_id="5-5-foo",
        retry_reason="patch-bucket-retry",
        writer=writer2,
    )
    assert writer1.calls[0][1] == writer2.calls[0][1]


# --------------------------------------------------------------------------- #
# default_artifact_writer atomic-write smoke                                  #
# --------------------------------------------------------------------------- #


def test_default_artifact_writer_writes_atomically(
    tmp_path: pathlib.Path,
) -> None:
    target = tmp_path / "nested" / "dir" / "file.yaml"
    default_artifact_writer(target, "key: value\n")
    assert target.read_text(encoding="utf-8") == "key: value\n"
    # No leftover temp files in the directory.
    siblings = list(target.parent.iterdir())
    assert siblings == [target]


def test_default_artifact_writer_overwrites_existing(
    tmp_path: pathlib.Path,
) -> None:
    target = tmp_path / "file.yaml"
    target.write_text("old: 1\n", encoding="utf-8")
    default_artifact_writer(target, "new: 2\n")
    assert target.read_text(encoding="utf-8") == "new: 2\n"


# --------------------------------------------------------------------------- #
# Free-running smoke — created_at format helper                               #
# --------------------------------------------------------------------------- #


def test_round_created_at_iso_8601_round_trip(
    tmp_path: pathlib.Path,
) -> None:
    """Smoke that an ISO-8601 UTC string supplied at construction time
    round-trips through persist + resolve."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    round = _make_round(created_at=now)
    ref = persist_retry_round(
        round=round,
        repo_root=tmp_path,
        story_id="5-5-foo",
        retry_reason="patch-bucket-retry",
    )
    loaded = resolve_retry_round(ref=ref, repo_root=tmp_path)
    assert loaded.created_at == now
