"""Contract-coverage matrix for the story-file locking protocol
(Story 14.3).

The test names below are the canonical narrative — they appear in CI
output and read as a contract.

API + module structure (AC-1, AC-2, AC-3):
    [x] __all__ exports public API in alphabetical order            → test_module_all_exports
    [x] LockRecord is frozen Pydantic                                → test_lock_record_is_frozen
    [x] LockRecord.schema_version is closed Literal                  → test_lock_record_schema_version_is_closed_literal
    [x] find_repo_root not called at module import                   → test_find_repo_root_not_called_at_import
    [x] story_file_lock does NOT invoke subprocess.run               → test_story_file_lock_does_not_invoke_subprocess
    [x] acquire_lock missing worktree_path raises TypeError          → test_acquire_lock_missing_worktree_path_typeerror
    [x] acquire_lock worktree_path is keyword-only                   → test_acquire_lock_keyword_only_worktree_path

acquire_lock — clean acquisition (AC-4):
    [x] creates new lock on clean state                              → test_acquire_lock_creates_new_lock_on_clean_state
    [x] record carries pid, timestamp, worktree path, hostname       → test_acquire_lock_record_carries_pid_timestamp_worktree_path_hostname
    [x] returns acquired=True, was_stale_takeover=False              → test_acquire_lock_returns_acquired_true_was_stale_takeover_false
    [x] resolves repo_root lazily when None                          → test_acquire_lock_repo_root_none_resolves_lazily
    [x] uses atomic O_CREAT | O_EXCL                                 → test_acquire_lock_uses_atomic_o_excl
    [x] stale-takeover uses os.replace (not unlink-then-create)      → test_acquire_lock_stale_takeover_uses_os_replace_not_unlink_then_create

acquire_lock — collision handling (AC-4):
    [x] live competitor → StoryFileLockContended                     → test_acquire_lock_contention_with_live_pid_raises_contended
    [x] dead pid → stale takeover                                    → test_acquire_lock_stale_takeover_when_pid_not_alive
    [x] age beyond threshold → stale takeover                        → test_acquire_lock_stale_takeover_when_age_exceeded
    [x] corrupted file → StoryFileLockCorrupted                      → test_acquire_lock_corrupted_file_raises_corrupted

release_lock (AC-5):
    [x] removes existing lock                                        → test_release_lock_removes_existing_lock
    [x] idempotent when no lock exists                               → test_release_lock_idempotent_when_no_lock_exists
    [x] matching expected_pid removes                                → test_release_lock_with_matching_expected_pid_removes
    [x] mismatched expected_pid raises release-conflict              → test_release_lock_with_mismatched_expected_pid_raises_release_conflict
    [x] clears corrupted file                                        → test_release_lock_clears_corrupted_file

inspect_lock (AC-6):
    [x] returns None for absent file                                 → test_inspect_lock_returns_none_for_absent_file
    [x] returns LockInspectionResult for clean file                  → test_inspect_lock_returns_record_for_clean_file
    [x] returns parse_error for corrupted file                       → test_inspect_lock_returns_parse_error_for_corrupted_file

is_stale (AC-6):
    [x] returns pid-not-alive when probe returns False               → test_is_stale_returns_pid_not_alive_when_pid_probe_false
    [x] returns age-exceeded when age over threshold                 → test_is_stale_returns_age_exceeded_when_age_over_threshold
    [x] returns fresh when pid alive and age under threshold         → test_is_stale_returns_fresh_when_pid_alive_and_age_under_threshold

Context manager (AC-6):
    [x] releases on clean exit                                       → test_story_file_lock_context_manager_releases_on_clean_exit
    [x] releases on exception in body                                → test_story_file_lock_context_manager_releases_on_exception_in_body
    [x] suppresses release-conflict, logs to stderr                  → test_story_file_lock_context_manager_suppresses_release_conflict_logs_to_stderr

Production defaults:
    [x] default pid probe returns True for own pid                   → test_default_pid_probe_returns_true_for_own_pid
    [x] default pid probe returns False for dead pid                 → test_default_pid_probe_returns_false_for_dead_pid
    [x] default clock returns UTC datetime                           → test_default_clock_returns_utc_datetime
"""

from __future__ import annotations

import ast
import datetime
import os
import pathlib
import subprocess
import sys
from typing import Any
from unittest import mock

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness import story_file_lock
from loud_fail_harness.story_file_lock import (
    DEFAULT_STALE_THRESHOLD_SECONDS,
    LockAcquisitionResult,
    LockInspectionResult,
    LockRecord,
    LockReleaseResult,
    StalenessVerdict,
    StoryFileLockBlocked,
    StoryFileLockContended,
    StoryFileLockCorrupted,
    StoryFileLockReleaseConflict,
    _default_clock,
    _default_pid_probe,
    acquire_lock,
    inspect_lock,
    is_stale,
    release_lock,
    story_file_lock as story_file_lock_cm,
)


# --------------------------------------------------------------------------- #
# Fixtures + helpers                                                          #
# --------------------------------------------------------------------------- #


def _make_lock_dir(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Return ``(repo_root, locks_root)`` rooted under ``tmp_path``.

    ``repo_root`` is ``tmp_path``; ``locks_root`` is the canonical
    ``<repo_root>/_bmad/automation/locks/`` directory. The directory is
    NOT pre-created — :func:`acquire_lock` creates it lazily per AC-4
    step 3.
    """
    repo_root = tmp_path
    locks_root = tmp_path / "_bmad" / "automation" / "locks"
    return repo_root, locks_root


def _alive_pid_probe(_pid: int) -> bool:
    return True


def _dead_pid_probe(_pid: int) -> bool:
    return False


def _fixed_clock(when: datetime.datetime) -> "callable":
    def _clock() -> datetime.datetime:
        return when
    return _clock


def _t0() -> datetime.datetime:
    return datetime.datetime(2026, 5, 30, 12, 0, 0, tzinfo=datetime.timezone.utc)


# --------------------------------------------------------------------------- #
# API + module structure                                                      #
# --------------------------------------------------------------------------- #


def test_exception_hierarchy() -> None:
    assert issubclass(StoryFileLockContended, StoryFileLockBlocked)
    assert issubclass(StoryFileLockCorrupted, StoryFileLockBlocked)
    assert issubclass(StoryFileLockReleaseConflict, StoryFileLockBlocked)
    assert issubclass(StoryFileLockBlocked, Exception)


def test_staleness_verdict_is_frozen() -> None:
    verdict = StalenessVerdict(
        is_stale=False,
        reason="fresh",
        record=_sample_record(_t0()),
        evaluated_at=_t0(),
        age_seconds=1.0,
    )
    with pytest.raises(ValidationError):
        verdict.is_stale = True  # type: ignore[misc]


def test_module_all_exports() -> None:
    expected = [
        "DEFAULT_STALE_THRESHOLD_SECONDS",
        "LockAcquisitionResult",
        "LockInspectionResult",
        "LockRecord",
        "LockReleaseResult",
        "StalenessVerdict",
        "StoryFileLockBlocked",
        "StoryFileLockContended",
        "StoryFileLockCorrupted",
        "StoryFileLockReleaseConflict",
        "acquire_lock",
        "inspect_lock",
        "is_stale",
        "release_lock",
        "story_file_lock",
    ]
    assert story_file_lock.__all__ == expected
    assert expected == sorted(expected)


def test_lock_record_is_frozen() -> None:
    record = LockRecord(
        schema_version="1.0",
        story_id="14-3",
        pid=os.getpid(),
        started_at=_t0(),
        worktree_path=pathlib.Path("/tmp/wt"),
        hostname="testhost",
    )
    with pytest.raises(ValidationError):
        record.pid = 999  # type: ignore[misc]


def test_lock_record_schema_version_is_closed_literal() -> None:
    annotation = LockRecord.model_fields["schema_version"].annotation
    assert getattr(annotation, "__args__", ()) == ("1.0",)


def test_find_repo_root_not_called_at_import() -> None:
    src = pathlib.Path(story_file_lock.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                func = stmt.value.func
                if isinstance(func, ast.Name) and func.id == "find_repo_root":
                    pytest.fail(
                        "find_repo_root() must not be called at module top-level"
                    )


def test_story_file_lock_does_not_invoke_subprocess() -> None:
    src = pathlib.Path(story_file_lock.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"run", "Popen", "call", "check_output"}:
            value = node.value
            if isinstance(value, ast.Name) and value.id == "subprocess":
                pytest.fail("subprocess.* invocation forbidden in story_file_lock.py")


def test_acquire_lock_missing_worktree_path_typeerror(tmp_path: pathlib.Path) -> None:
    _, locks_root = _make_lock_dir(tmp_path)
    with pytest.raises(TypeError):
        acquire_lock("14-3", locks_root=locks_root, repo_root=tmp_path)  # type: ignore[call-arg]


def test_acquire_lock_keyword_only_worktree_path(tmp_path: pathlib.Path) -> None:
    _, locks_root = _make_lock_dir(tmp_path)
    with pytest.raises(TypeError):
        acquire_lock(
            "14-3",
            tmp_path / "wt",  # type: ignore[misc]
            locks_root=locks_root,
            repo_root=tmp_path,
        )


# --------------------------------------------------------------------------- #
# acquire_lock — clean acquisition (AC-4)                                     #
# --------------------------------------------------------------------------- #


def test_acquire_lock_creates_new_lock_on_clean_state(tmp_path: pathlib.Path) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    result = acquire_lock(
        "14-3",
        worktree_path=tmp_path / "wt",
        locks_root=locks_root,
        repo_root=repo_root,
        clock=_fixed_clock(_t0()),
        pid_probe=_alive_pid_probe,
    )
    assert result.acquired is True
    assert result.was_stale_takeover is False
    assert result.lock_path.exists()


def test_acquire_lock_record_carries_pid_timestamp_worktree_path_hostname(
    tmp_path: pathlib.Path,
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    wt = tmp_path / "wt"
    wt.mkdir()
    result = acquire_lock(
        "14-3",
        worktree_path=wt,
        locks_root=locks_root,
        repo_root=repo_root,
        clock=_fixed_clock(_t0()),
    )
    assert result.record.pid == os.getpid()
    assert result.record.started_at == _t0()
    assert result.record.worktree_path == wt.resolve()
    assert result.record.hostname  # non-empty


def test_acquire_lock_returns_acquired_true_was_stale_takeover_false(
    tmp_path: pathlib.Path,
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    result = acquire_lock(
        "14-3",
        worktree_path=tmp_path / "wt",
        locks_root=locks_root,
        repo_root=repo_root,
    )
    assert isinstance(result, LockAcquisitionResult)
    assert result.acquired is True
    assert result.was_stale_takeover is False


def test_acquire_lock_repo_root_none_resolves_lazily(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        story_file_lock, "_default_repo_root", lambda: tmp_path
    )
    _, locks_root = _make_lock_dir(tmp_path)
    result = acquire_lock(
        "14-3",
        worktree_path=tmp_path / "wt",
        locks_root=locks_root,
    )
    assert result.lock_path.parent == locks_root


def test_acquire_lock_uses_atomic_o_excl(tmp_path: pathlib.Path) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    real_open = os.open
    captured_flags: list[int] = []

    def _spy_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if isinstance(path, str) and path.endswith(".lock"):
            captured_flags.append(flags)
        return real_open(path, flags, *args, **kwargs)

    with mock.patch.object(story_file_lock.os, "open", _spy_open):
        acquire_lock(
            "14-3",
            worktree_path=tmp_path / "wt",
            locks_root=locks_root,
            repo_root=repo_root,
        )

    assert captured_flags, "no os.open call on .lock observed"
    flags = captured_flags[0]
    assert flags & os.O_CREAT, "O_CREAT not set"
    assert flags & os.O_EXCL, "O_EXCL not set"


def test_acquire_lock_stale_takeover_uses_os_replace_not_unlink_then_create(
    tmp_path: pathlib.Path,
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    acquire_lock(
        "14-3",
        worktree_path=tmp_path / "wt-1",
        locks_root=locks_root,
        repo_root=repo_root,
    )

    replace_calls: list[tuple[str, str]] = []
    unlink_calls: list[Any] = []
    real_replace = os.replace
    real_unlink = os.unlink

    def _spy_replace(src: Any, dst: Any, **kw: Any) -> None:
        replace_calls.append((str(src), str(dst)))
        real_replace(src, dst, **kw)

    def _spy_unlink(p: Any, **kw: Any) -> None:
        unlink_calls.append(p)
        real_unlink(p, **kw)

    with mock.patch.object(story_file_lock.os, "replace", _spy_replace), \
            mock.patch.object(story_file_lock.os, "unlink", _spy_unlink):
        result = acquire_lock(
            "14-3",
            worktree_path=tmp_path / "wt-2",
            locks_root=locks_root,
            repo_root=repo_root,
            pid_probe=_dead_pid_probe,
        )

    assert result.was_stale_takeover is True
    assert replace_calls, "os.replace not invoked on stale takeover"
    assert not unlink_calls, "stale takeover must NOT use unlink-then-create"


# --------------------------------------------------------------------------- #
# acquire_lock — collision handling                                           #
# --------------------------------------------------------------------------- #


def test_acquire_lock_contention_with_live_pid_raises_contended(
    tmp_path: pathlib.Path,
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    first = acquire_lock(
        "14-3",
        worktree_path=tmp_path / "wt-1",
        locks_root=locks_root,
        repo_root=repo_root,
        clock=_fixed_clock(_t0()),
    )
    assert first.acquired

    with pytest.raises(StoryFileLockContended) as exc_info:
        acquire_lock(
            "14-3",
            worktree_path=tmp_path / "wt-2",
            locks_root=locks_root,
            repo_root=repo_root,
            pid_probe=_alive_pid_probe,
            clock=_fixed_clock(_t0()),
        )

    assert exc_info.value.marker_class == "worktree-stale-lock"
    assert exc_info.value.attempted_story_id == "14-3"
    assert isinstance(exc_info.value.cause, LockRecord)


def test_acquire_lock_stale_takeover_when_pid_not_alive(
    tmp_path: pathlib.Path,
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    acquire_lock(
        "14-3",
        worktree_path=tmp_path / "wt-1",
        locks_root=locks_root,
        repo_root=repo_root,
    )
    result = acquire_lock(
        "14-3",
        worktree_path=tmp_path / "wt-2",
        locks_root=locks_root,
        repo_root=repo_root,
        pid_probe=_dead_pid_probe,
    )
    assert result.acquired is True
    assert result.was_stale_takeover is True


def test_acquire_lock_stale_takeover_when_age_exceeded(
    tmp_path: pathlib.Path,
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    acquire_lock(
        "14-3",
        worktree_path=tmp_path / "wt-1",
        locks_root=locks_root,
        repo_root=repo_root,
        clock=_fixed_clock(_t0()),
    )

    later = _t0() + datetime.timedelta(seconds=3601)
    result = acquire_lock(
        "14-3",
        worktree_path=tmp_path / "wt-2",
        locks_root=locks_root,
        repo_root=repo_root,
        pid_probe=_alive_pid_probe,
        clock=_fixed_clock(later),
    )
    assert result.was_stale_takeover is True


def test_acquire_lock_corrupted_file_raises_corrupted(
    tmp_path: pathlib.Path,
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    locks_root.mkdir(parents=True)
    (locks_root / "14-3.lock").write_text("not: valid: yaml: [content", encoding="utf-8")

    with pytest.raises(StoryFileLockCorrupted) as exc_info:
        acquire_lock(
            "14-3",
            worktree_path=tmp_path / "wt",
            locks_root=locks_root,
            repo_root=repo_root,
        )

    assert exc_info.value.marker_class == "worktree-stale-lock"
    assert exc_info.value.attempted_story_id == "14-3"


# --------------------------------------------------------------------------- #
# release_lock (AC-5)                                                         #
# --------------------------------------------------------------------------- #


def test_release_lock_removes_existing_lock(tmp_path: pathlib.Path) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    acquire_lock(
        "14-3",
        worktree_path=tmp_path / "wt",
        locks_root=locks_root,
        repo_root=repo_root,
    )
    result = release_lock("14-3", locks_root=locks_root, repo_root=repo_root)
    assert result.released is True
    assert isinstance(result, LockReleaseResult)
    assert not result.lock_path.exists()


def test_release_lock_idempotent_when_no_lock_exists(
    tmp_path: pathlib.Path,
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    result = release_lock("14-3", locks_root=locks_root, repo_root=repo_root)
    assert result.released is False
    assert result.record is None


def test_release_lock_with_matching_expected_pid_removes(
    tmp_path: pathlib.Path,
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    acquire_lock(
        "14-3",
        worktree_path=tmp_path / "wt",
        locks_root=locks_root,
        repo_root=repo_root,
    )
    result = release_lock(
        "14-3",
        locks_root=locks_root,
        repo_root=repo_root,
        expected_pid=os.getpid(),
    )
    assert result.released is True


def test_release_lock_with_mismatched_expected_pid_raises_release_conflict(
    tmp_path: pathlib.Path,
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    acquire_lock(
        "14-3",
        worktree_path=tmp_path / "wt",
        locks_root=locks_root,
        repo_root=repo_root,
    )
    other_pid = os.getpid() + 999_999
    with pytest.raises(StoryFileLockReleaseConflict) as exc_info:
        release_lock(
            "14-3",
            locks_root=locks_root,
            repo_root=repo_root,
            expected_pid=other_pid,
        )
    assert exc_info.value.marker_class == "worktree-stale-lock"


def test_release_lock_clears_corrupted_file(tmp_path: pathlib.Path) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    locks_root.mkdir(parents=True)
    lock_path = locks_root / "14-3.lock"
    lock_path.write_text("garbage: [unclosed", encoding="utf-8")

    result = release_lock("14-3", locks_root=locks_root, repo_root=repo_root)
    assert result.released is True
    assert result.record is None
    assert not lock_path.exists()


# --------------------------------------------------------------------------- #
# inspect_lock (AC-6)                                                         #
# --------------------------------------------------------------------------- #


def test_inspect_lock_returns_none_for_absent_file(tmp_path: pathlib.Path) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    assert (
        inspect_lock("14-3", locks_root=locks_root, repo_root=repo_root)
        is None
    )


def test_inspect_lock_returns_record_for_clean_file(tmp_path: pathlib.Path) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    acquire_lock(
        "14-3",
        worktree_path=tmp_path / "wt",
        locks_root=locks_root,
        repo_root=repo_root,
        clock=_fixed_clock(_t0()),
    )
    result = inspect_lock("14-3", locks_root=locks_root, repo_root=repo_root)
    assert isinstance(result, LockInspectionResult)
    assert result.exists is True
    assert result.parse_error is None
    assert result.record is not None
    assert result.record.story_id == "14-3"


def test_inspect_lock_returns_parse_error_for_corrupted_file(
    tmp_path: pathlib.Path,
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    locks_root.mkdir(parents=True)
    (locks_root / "14-3.lock").write_text("[: not yaml]", encoding="utf-8")

    result = inspect_lock("14-3", locks_root=locks_root, repo_root=repo_root)
    assert result is not None
    assert result.exists is True
    assert result.parse_error is not None
    assert result.record is None


# --------------------------------------------------------------------------- #
# is_stale (AC-6)                                                             #
# --------------------------------------------------------------------------- #


def _sample_record(when: datetime.datetime) -> LockRecord:
    return LockRecord(
        schema_version="1.0",
        story_id="14-3",
        pid=os.getpid(),
        started_at=when,
        worktree_path=pathlib.Path("/tmp/wt"),
        hostname="testhost",
    )


def test_is_stale_returns_pid_not_alive_when_pid_probe_false() -> None:
    record = _sample_record(_t0())
    verdict = is_stale(
        record,
        stale_threshold_seconds=3600,
        pid_probe=_dead_pid_probe,
        clock=_fixed_clock(_t0() + datetime.timedelta(seconds=10)),
    )
    assert verdict.is_stale is True
    assert verdict.reason == "pid-not-alive"


def test_is_stale_returns_age_exceeded_when_age_over_threshold() -> None:
    record = _sample_record(_t0())
    verdict = is_stale(
        record,
        stale_threshold_seconds=3600,
        pid_probe=_alive_pid_probe,
        clock=_fixed_clock(_t0() + datetime.timedelta(seconds=3601)),
    )
    assert verdict.is_stale is True
    assert verdict.reason == "age-exceeded"


def test_is_stale_returns_fresh_when_pid_alive_and_age_under_threshold() -> None:
    record = _sample_record(_t0())
    verdict = is_stale(
        record,
        stale_threshold_seconds=3600,
        pid_probe=_alive_pid_probe,
        clock=_fixed_clock(_t0() + datetime.timedelta(seconds=10)),
    )
    assert verdict.is_stale is False
    assert verdict.reason == "fresh"


# --------------------------------------------------------------------------- #
# Context manager (AC-6)                                                      #
# --------------------------------------------------------------------------- #


def test_story_file_lock_context_manager_releases_on_clean_exit(
    tmp_path: pathlib.Path,
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    with story_file_lock_cm(
        "14-3",
        worktree_path=tmp_path / "wt",
        locks_root=locks_root,
        repo_root=repo_root,
    ) as result:
        assert result.acquired
        assert result.lock_path.exists()
    assert not (locks_root / "14-3.lock").exists()


def test_story_file_lock_context_manager_releases_on_exception_in_body(
    tmp_path: pathlib.Path,
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    with pytest.raises(RuntimeError, match="boom"):
        with story_file_lock_cm(
            "14-3",
            worktree_path=tmp_path / "wt",
            locks_root=locks_root,
            repo_root=repo_root,
        ):
            raise RuntimeError("boom")
    assert not (locks_root / "14-3.lock").exists()


def test_story_file_lock_context_manager_suppresses_release_conflict_logs_to_stderr(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo_root, locks_root = _make_lock_dir(tmp_path)
    with story_file_lock_cm(
        "14-3",
        worktree_path=tmp_path / "wt",
        locks_root=locks_root,
        repo_root=repo_root,
    ) as result:
        # Simulate stale-takeover by another process: overwrite the on-disk
        # record with a foreign pid before the context manager's finally
        # release_lock(expected_pid=os.getpid()) runs.
        foreign = LockRecord(
            schema_version="1.0",
            story_id="14-3",
            pid=os.getpid() + 999_999,
            started_at=_t0(),
            worktree_path=tmp_path / "wt-other",
            hostname="otherhost",
        )
        result.lock_path.write_text(
            yaml.safe_dump(foreign.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )

    captured = capsys.readouterr()
    assert "release-conflict" in captured.err
    # No exception escaped — body completed normally; release-conflict was
    # suppressed inside __exit__'s finally per AC-6.


# --------------------------------------------------------------------------- #
# Production defaults                                                         #
# --------------------------------------------------------------------------- #


def test_default_pid_probe_returns_true_for_own_pid() -> None:
    assert _default_pid_probe(os.getpid()) is True


def test_default_pid_probe_returns_false_for_dead_pid() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"])
    proc.wait()
    assert _default_pid_probe(proc.pid) is False


def test_default_clock_returns_utc_datetime() -> None:
    now = _default_clock()
    assert isinstance(now, datetime.datetime)
    assert now.tzinfo == datetime.timezone.utc


def test_default_stale_threshold_value() -> None:
    assert DEFAULT_STALE_THRESHOLD_SECONDS == 3600
