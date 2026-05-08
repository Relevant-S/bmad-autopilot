"""Tests for the Story 7.6 non-destructive ``init`` guard substrate module.

Covers AC-7 — twenty-two independent test functions covering:

* existence detection across the three canonical scaffold-target paths
  (sample-story, config, qa-runbook),
* the four ``GuardOutcome.action`` branches (``proceed-fresh`` /
  ``preserve-merge`` / ``overwrite-confirmed`` / ``halt-would-destroy``),
* halt-route enumeration (``secondary-confirmation-missing`` /
  ``merge-failed``),
* additive-merge contract on existing config (canonical comment-blocks
  + values appended; user customizations preserved verbatim; no-op
  when all canonical keys present; ``GuardConfigCorrupted`` on
  malformed YAML),
* qa-runbook all-commented-canonical posture handling,
* structured audit-log entry shape + filename pattern,
* parent-directory creation for first override-confirmed invocation,
* ``PermissionError`` propagation,
* ``GuardRequest`` / ``GuardOutcome`` typed model invariants
  (``is_absolute`` validator; frozen),
* defensive ``project_root`` scope (resolved targets stay under
  caller-supplied root),
* null-runtime null-guard (``run_state=None`` halt path is silent),
* marker emission discipline — no marker on ``proceed-fresh`` /
  ``preserve-merge`` / ``overwrite-confirmed``; exactly-one on each
  halt route.

Pattern 5 + Pattern 6 — explicit, named tests; no shared mutable
state; caller-injected ``tmp_path`` so tests do NOT touch the outer
workspace's ``_bmad/automation/`` or ``_bmad-output/init-history/``.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
import stat
import sys
from typing import Final
from unittest import mock

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness import init_non_destructive_guard
from loud_fail_harness.config_qa_runbook_stub import (
    load_config_template,
    load_qa_runbook_template,
    resolve_config_path,
    resolve_qa_runbook_path,
)
from loud_fail_harness.init_non_destructive_guard import (
    AUDIT_LOG_FILENAME_PATTERN,
    AUDIT_LOG_SUBDIR,
    INIT_WOULD_DESTROY_MARKER_CLASS,
    GuardConfigCorrupted,
    GuardOutcome,
    GuardRequest,
    MergeResult,
    additively_merge_config,
    additively_merge_qa_runbook,
    detect_existing_user_owned_artifacts,
    evaluate_non_destructive_guard,
    write_init_history_entry,
)
from loud_fail_harness.run_state import CostToDateBySpecialist, RunState
from loud_fail_harness.sample_story_scaffold import (
    resolve_target_path as resolve_sample_story_path,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)


# --------------------------------------------------------------------------- #
# Module-level constants used by multiple tests                                #
# --------------------------------------------------------------------------- #

_CANONICAL_CONFIG_KEYS: Final[tuple[str, ...]] = tuple(
    yaml.safe_load(load_config_template()).keys()
)
_CANONICAL_CONFIG_KEY_COUNT: Final[int] = len(_CANONICAL_CONFIG_KEYS)


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


def _make_run_state() -> RunState:
    return RunState(
        schema_version="1.3",
        story_id="7-6-test",
        run_id="run-001",
        current_state="in-progress",
        branch_name="bmad-automation/story/7-6-test",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


def _make_existing_project_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """Materialize all three canonical scaffold-targets with valid content."""
    config_target = resolve_config_path(tmp_path)
    qa_runbook_target = resolve_qa_runbook_path(tmp_path)
    sample_target = resolve_sample_story_path(tmp_path)

    config_target.parent.mkdir(parents=True, exist_ok=True)
    sample_target.parent.mkdir(parents=True, exist_ok=True)

    config_target.write_text(load_config_template(), encoding="utf-8")
    qa_runbook_target.write_text(load_qa_runbook_template(), encoding="utf-8")
    sample_target.write_text("# sample story (preserved verbatim)\n", encoding="utf-8")
    return tmp_path


def _make_corrupted_config(tmp_path: pathlib.Path) -> pathlib.Path:
    """Materialize a project root where config.yaml is malformed YAML."""
    config_target = resolve_config_path(tmp_path)
    config_target.parent.mkdir(parents=True, exist_ok=True)
    # PyYAML rejects this body (unterminated flow sequence).
    config_target.write_text("this is not yaml: [\n", encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------- #
# AC-7 case 1 — `detect_existing_user_owned_artifacts` empty on fresh project. #
# --------------------------------------------------------------------------- #


def test_detect_returns_empty_tuple_on_fresh_project(tmp_path: pathlib.Path) -> None:
    """No existing user-owned files; the function returns ``()`` and is
    side-effect-free (no ``mkdir``, no logging)."""
    initial_listing = sorted(p.name for p in tmp_path.iterdir())

    result = detect_existing_user_owned_artifacts(tmp_path)

    assert result == ()
    assert sorted(p.name for p in tmp_path.iterdir()) == initial_listing


# --------------------------------------------------------------------------- #
# AC-7 case 2 — `detect_existing_user_owned_artifacts` finds all three.        #
# --------------------------------------------------------------------------- #


def test_detect_finds_all_three_canonical_paths_in_deterministic_order(
    tmp_path: pathlib.Path,
) -> None:
    """Given all three scaffold-target files materialized, the function
    returns the three paths in deterministic order: sample-story FIRST,
    config SECOND, qa-runbook THIRD."""
    _make_existing_project_root(tmp_path)

    result = detect_existing_user_owned_artifacts(tmp_path)

    assert len(result) == 3
    assert result[0] == resolve_sample_story_path(tmp_path)
    assert result[1] == resolve_config_path(tmp_path)
    assert result[2] == resolve_qa_runbook_path(tmp_path)
    for p in result:
        assert p.is_absolute()
        assert p.is_relative_to(tmp_path)


# --------------------------------------------------------------------------- #
# AC-7 case 3 — `detect_existing_user_owned_artifacts` ignores directories.    #
# --------------------------------------------------------------------------- #


def test_detect_ignores_directory_at_canonical_target_path(
    tmp_path: pathlib.Path,
) -> None:
    """A directory at a canonical target path is structurally distinct
    from a regular-file overwrite-target; the ``is_file()`` filter
    excludes directories."""
    config_target = resolve_config_path(tmp_path)
    # Materialize the config TARGET path as a DIRECTORY (not a file).
    config_target.parent.mkdir(parents=True, exist_ok=True)
    config_target.mkdir()

    result = detect_existing_user_owned_artifacts(tmp_path)
    assert config_target not in result


# --------------------------------------------------------------------------- #
# AC-7 case 4 — `evaluate_non_destructive_guard` `proceed-fresh` on empty.     #
# --------------------------------------------------------------------------- #


def test_evaluate_returns_proceed_fresh_on_fresh_project(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """On a fresh project, the function returns
    ``GuardOutcome(action="proceed-fresh", existing_files=(), audit_log_path=None)``;
    no marker is registered."""
    request = GuardRequest(project_root=tmp_path)
    rs = _make_run_state()

    outcome, next_rs = evaluate_non_destructive_guard(
        request, run_state=rs, marker_registry=runtime_marker_registry
    )

    assert outcome.action == "proceed-fresh"
    assert outcome.existing_files == ()
    assert outcome.audit_log_path is None
    assert outcome.diagnostic is None
    # No marker emitted; run-state is preserved unchanged.
    assert next_rs is rs
    assert next_rs.active_markers == ()


# --------------------------------------------------------------------------- #
# AC-7 case 5 — `evaluate_non_destructive_guard` `preserve-merge` on re-run.   #
# --------------------------------------------------------------------------- #


def test_evaluate_returns_preserve_merge_on_default_re_run(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """On a re-run with default flags AND valid existing YAML, the
    function returns ``preserve-merge`` carrying all three existing
    files; no marker is registered."""
    _make_existing_project_root(tmp_path)
    request = GuardRequest(project_root=tmp_path)
    rs = _make_run_state()

    outcome, next_rs = evaluate_non_destructive_guard(
        request, run_state=rs, marker_registry=runtime_marker_registry
    )

    assert outcome.action == "preserve-merge"
    assert len(outcome.existing_files) == 3
    assert outcome.audit_log_path is None
    assert next_rs is rs
    assert next_rs.active_markers == ()


# --------------------------------------------------------------------------- #
# AC-7 case 6 — No marker on `proceed-fresh` / `preserve-merge` / `overwrite-  #
# confirmed`. (The structural witness against accidental marker emission.)    #
# --------------------------------------------------------------------------- #


def test_evaluate_does_not_emit_marker_on_non_halt_branches(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Per the verbatim AC at ``epics.md`` line 3058 — "**no marker fires
    on intentional override**". The patched-symbol-name discipline
    follows Story 7.4's deferred-review fix: patch the CONSUMING
    module's namespace
    (``loud_fail_harness.init_non_destructive_guard.record_marker_with_context``).

    Covers all THREE non-halt branches per AC-7 case 6 verbatim:
    ``proceed-fresh``, ``preserve-merge``, ``overwrite-confirmed``."""
    with mock.patch(
        "loud_fail_harness.init_non_destructive_guard.record_marker_with_context"
    ) as mock_record:
        # Branch 1 — fresh project.
        request_fresh = GuardRequest(project_root=tmp_path)
        evaluate_non_destructive_guard(
            request_fresh,
            run_state=_make_run_state(),
            marker_registry=runtime_marker_registry,
        )
        # Branch 2 — preserve-merge on re-run.
        _make_existing_project_root(tmp_path)
        request_re_run = GuardRequest(project_root=tmp_path)
        evaluate_non_destructive_guard(
            request_re_run,
            run_state=_make_run_state(),
            marker_registry=runtime_marker_registry,
        )
        # Branch 3 — overwrite-confirmed.
        request_override = GuardRequest(
            project_root=tmp_path,
            override_confirmed=True,
            secondary_confirmed=True,
        )
        evaluate_non_destructive_guard(
            request_override,
            run_state=_make_run_state(),
            marker_registry=runtime_marker_registry,
        )

        assert mock_record.call_count == 0, (
            "init-would-destroy-existing-artifact must NOT fire on "
            "proceed-fresh / preserve-merge / overwrite-confirmed; "
            f"called {mock_record.call_count} time(s)"
        )


# --------------------------------------------------------------------------- #
# AC-7 case 7 — Halt + emit marker once on override-without-secondary.        #
# --------------------------------------------------------------------------- #


def test_evaluate_halts_and_emits_marker_on_override_without_secondary(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Override flag without secondary confirmation halts AND registers
    the marker EXACTLY ONCE."""
    _make_existing_project_root(tmp_path)
    request = GuardRequest(
        project_root=tmp_path,
        override_confirmed=True,
        secondary_confirmed=False,
    )
    rs = _make_run_state()

    with mock.patch(
        "loud_fail_harness.init_non_destructive_guard.record_marker_with_context",
        wraps=init_non_destructive_guard.record_marker_with_context,
    ) as mock_record:
        outcome, next_rs = evaluate_non_destructive_guard(
            request, run_state=rs, marker_registry=runtime_marker_registry
        )

    assert outcome.action == "halt-would-destroy"
    assert outcome.existing_files == tuple(
        detect_existing_user_owned_artifacts(tmp_path)
    )
    assert outcome.audit_log_path is None
    assert outcome.diagnostic is not None
    # AC-4: diagnostic enumerates the three practitioner options.
    assert "Back up" in outcome.diagnostic
    assert "Merge" in outcome.diagnostic
    assert "Explicit override" in outcome.diagnostic
    assert mock_record.call_count == 1
    call_kwargs = mock_record.call_args.kwargs
    assert call_kwargs["marker_class"] == INIT_WOULD_DESTROY_MARKER_CLASS
    assert next_rs is not None
    assert INIT_WOULD_DESTROY_MARKER_CLASS in next_rs.active_markers


# --------------------------------------------------------------------------- #
# AC-7 case 8 — Halt + emit marker on additive-merge-corrupted-config.        #
# --------------------------------------------------------------------------- #


def test_evaluate_halts_and_emits_marker_on_corrupted_existing_config(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Existing config.yaml with malformed YAML triggers the
    ``merge-failed`` halt route; the marker is registered exactly
    once; the diagnostic includes a "Restore or delete" hint."""
    _make_corrupted_config(tmp_path)
    request = GuardRequest(project_root=tmp_path)
    rs = _make_run_state()

    with mock.patch(
        "loud_fail_harness.init_non_destructive_guard.record_marker_with_context",
        wraps=init_non_destructive_guard.record_marker_with_context,
    ) as mock_record:
        outcome, next_rs = evaluate_non_destructive_guard(
            request, run_state=rs, marker_registry=runtime_marker_registry
        )

    assert outcome.action == "halt-would-destroy"
    assert outcome.diagnostic is not None
    assert "Restore or delete" in outcome.diagnostic
    assert resolve_config_path(tmp_path).name in outcome.diagnostic
    assert mock_record.call_count == 1
    assert next_rs is not None
    assert INIT_WOULD_DESTROY_MARKER_CLASS in next_rs.active_markers


# --------------------------------------------------------------------------- #
# AC-7 case 9 — `overwrite-confirmed` writes audit-log with expected shape.   #
# --------------------------------------------------------------------------- #


def test_evaluate_overwrite_confirmed_writes_audit_log(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Full override produces ``overwrite-confirmed``; the audit log
    file exists at ``_bmad-output/init-history/{timestamp}.log`` with
    the documented key set; ``loud_fail_marker_emitted`` is the
    LITERAL boolean ``False`` (per AC-7 case 9)."""
    _make_existing_project_root(tmp_path)
    request = GuardRequest(
        project_root=tmp_path,
        override_confirmed=True,
        secondary_confirmed=True,
    )

    outcome, _next_rs = evaluate_non_destructive_guard(
        request, run_state=_make_run_state(), marker_registry=runtime_marker_registry
    )

    assert outcome.action == "overwrite-confirmed"
    assert outcome.audit_log_path is not None
    assert outcome.audit_log_path.is_file()
    assert AUDIT_LOG_FILENAME_PATTERN.match(outcome.audit_log_path.name)
    assert outcome.audit_log_path.parent == tmp_path / "_bmad-output" / "init-history"

    body = yaml.safe_load(outcome.audit_log_path.read_text(encoding="utf-8"))
    assert isinstance(body, dict)
    expected_keys = {
        "timestamp",
        "action",
        "files_overwritten",
        "practitioner_intent",
        "loud_fail_marker_emitted",
        "rationale_pointer",
    }
    assert expected_keys <= body.keys()
    assert body["loud_fail_marker_emitted"] is False
    assert body["action"] == "overwrite-confirmed"
    assert body["practitioner_intent"] == (
        "explicit override (--overwrite-confirmed --yes)"
    )
    assert "docs/extension-audit.md" in body["rationale_pointer"]
    assert body["files_overwritten"]
    for raw_path in body["files_overwritten"]:
        assert isinstance(raw_path, str)


# --------------------------------------------------------------------------- #
# AC-7 case 10 — `additively_merge_config` adds new + preserves existing.     #
# --------------------------------------------------------------------------- #


def test_additively_merge_config_adds_new_keys_and_preserves_existing(
    tmp_path: pathlib.Path,
) -> None:
    """Existing config carrying TWO of the canonical-defaults keys with
    hand-edited values + ONE custom non-canonical key; the merge adds
    the missing canonical keys at the end with their preceding comment
    blocks; existing values + comments + key positions + the custom
    key are unchanged."""
    config_target = resolve_config_path(tmp_path)
    config_target.parent.mkdir(parents=True, exist_ok=True)
    existing_text = (
        "# user customizations preserved\n"
        "retry_budget: 5  # bumped per team policy\n"
        "my_custom_field: hello\n"
        "\n"
        "specialist_timeout_minutes: 30  # team is slow\n"
    )
    config_target.write_text(existing_text, encoding="utf-8")

    result = additively_merge_config(tmp_path)

    assert result.action == "merged"
    # Existing top-level keys: retry_budget, my_custom_field, specialist_timeout_minutes
    assert result.existing_keys_preserved == 3
    # Canonical has _CANONICAL_CONFIG_KEY_COUNT keys total; two are present
    # in existing → (total - 2) are added.
    assert result.new_keys_added == _CANONICAL_CONFIG_KEY_COUNT - 2
    assert result.bytes_written is not None and result.bytes_written > 0

    final_text = config_target.read_text(encoding="utf-8")
    # Existing customizations preserved verbatim.
    assert "# user customizations preserved" in final_text
    assert "retry_budget: 5  # bumped per team policy" in final_text
    assert "my_custom_field: hello" in final_text
    assert "specialist_timeout_minutes: 30  # team is slow" in final_text
    # New canonical keys present.
    new_keys = [k for k in _CANONICAL_CONFIG_KEYS if k not in {"retry_budget", "specialist_timeout_minutes"}]
    for key in new_keys:
        assert re.search(rf"^{re.escape(key)}\s*:", final_text, re.MULTILINE), (
            f"merged config missing canonical key {key!r}"
        )
    # Canonical comment-blocks transferred: at least one comment line present
    # in the merged output that was not in the original existing text.
    added_lines = set(final_text.splitlines()) - set(existing_text.splitlines())
    assert any(line.strip().startswith("#") for line in added_lines), (
        "additively_merge_config must transfer canonical comment blocks "
        "to the merged output alongside each appended key"
    )
    # Final YAML still parses cleanly.
    parsed = yaml.safe_load(final_text)
    assert isinstance(parsed, dict)
    assert parsed["retry_budget"] == 5  # user value preserved
    assert parsed["specialist_timeout_minutes"] == 30
    assert parsed["my_custom_field"] == "hello"


# --------------------------------------------------------------------------- #
# AC-7 case 11 — `additively_merge_config` is a no-op when all keys present.  #
# --------------------------------------------------------------------------- #


def test_additively_merge_config_is_no_op_when_all_keys_present(
    tmp_path: pathlib.Path,
) -> None:
    """If the existing config carries every canonical key (verbatim
    canonical content), the merge returns ``no-op`` AND the on-disk
    file is byte-identical post-call (skip-write)."""
    config_target = resolve_config_path(tmp_path)
    config_target.parent.mkdir(parents=True, exist_ok=True)
    canonical = load_config_template()
    config_target.write_text(canonical, encoding="utf-8")

    pre_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    result = additively_merge_config(tmp_path)

    assert result.action == "no-op"
    assert result.new_keys_added == 0
    assert result.existing_keys_preserved == _CANONICAL_CONFIG_KEY_COUNT
    assert result.bytes_written is None

    post_text = config_target.read_text(encoding="utf-8")
    post_hash = hashlib.sha256(post_text.encode("utf-8")).hexdigest()
    assert pre_hash == post_hash, "no-op merge must not mutate the on-disk file"


# --------------------------------------------------------------------------- #
# AC-7 case 12 — `additively_merge_config` raises on malformed YAML.          #
# --------------------------------------------------------------------------- #


def test_additively_merge_config_raises_guard_config_corrupted_on_malformed_yaml(
    tmp_path: pathlib.Path,
) -> None:
    """Malformed existing YAML raises ``GuardConfigCorrupted`` whose
    diagnostic mirrors ``InstallPathConfigError`` ("Restore or delete
    the file before re-running")."""
    _make_corrupted_config(tmp_path)
    config_target = resolve_config_path(tmp_path)

    with pytest.raises(GuardConfigCorrupted) as exc_info:
        additively_merge_config(tmp_path)

    assert exc_info.value.path == config_target
    assert "Restore or delete the file before re-running" in exc_info.value.diagnostic


# --------------------------------------------------------------------------- #
# AC-7 case 13 — `additively_merge_qa_runbook` handles all-commented canonical.#
# --------------------------------------------------------------------------- #


def test_additively_merge_qa_runbook_no_op_when_canonical_all_commented(
    tmp_path: pathlib.Path,
) -> None:
    """Story 7.5's qa-runbook canonical template is all-commented-out
    (parses to ``None``); when paired with non-empty existing user
    content (e.g., opt-in ``masked_selectors``), the merge returns
    ``no-op`` AND the on-disk file is byte-identical post-call."""
    qa_runbook_target = resolve_qa_runbook_path(tmp_path)
    qa_runbook_target.parent.mkdir(parents=True, exist_ok=True)
    user_content = (
        "# user opt-in masking\n"
        'masked_selectors:\n'
        '  - ".secret"\n'
    )
    qa_runbook_target.write_text(user_content, encoding="utf-8")

    pre_hash = hashlib.sha256(user_content.encode("utf-8")).hexdigest()

    result = additively_merge_qa_runbook(tmp_path)

    assert result.action == "no-op"
    assert result.new_keys_added == 0

    post_text = qa_runbook_target.read_text(encoding="utf-8")
    assert hashlib.sha256(post_text.encode("utf-8")).hexdigest() == pre_hash


# --------------------------------------------------------------------------- #
# AC-7 case 14 — `write_init_history_entry` writes structured YAML log.       #
# --------------------------------------------------------------------------- #


def test_write_init_history_entry_writes_structured_yaml(
    tmp_path: pathlib.Path,
) -> None:
    """Given an injected ``timestamp`` (Pattern 6 — test determinism),
    the function returns the resolved path with the expected name and
    parses to a non-empty dict with the expected keys."""
    fixed_stamp = "20260508T120000Z"
    files_touched: tuple[pathlib.Path, ...] = (
        resolve_config_path(tmp_path),
        resolve_qa_runbook_path(tmp_path),
    )

    audit_path = write_init_history_entry(
        tmp_path,
        action="overwrite-confirmed",
        files_touched=files_touched,
        timestamp=fixed_stamp,
    )

    expected_path = tmp_path / "_bmad-output" / "init-history" / f"{fixed_stamp}.log"
    assert audit_path == expected_path
    assert audit_path.is_file()
    body = yaml.safe_load(audit_path.read_text(encoding="utf-8"))
    assert isinstance(body, dict)
    assert body
    assert {
        "timestamp",
        "action",
        "files_overwritten",
        "practitioner_intent",
        "loud_fail_marker_emitted",
        "rationale_pointer",
    } <= body.keys()
    # The body's ISO-8601 timestamp matches the filename stamp's instant.
    assert body["timestamp"] == "2026-05-08T12:00:00+00:00"


# --------------------------------------------------------------------------- #
# AC-7 case 15 — `write_init_history_entry` creates parent dir if absent.     #
# --------------------------------------------------------------------------- #


def test_write_init_history_entry_creates_parent_directory(
    tmp_path: pathlib.Path,
) -> None:
    """Given ``tmp_path`` where ``_bmad-output/init-history/`` does
    not exist, the function creates it via ``mkdir(parents=True,
    exist_ok=True)``; post-call the directory exists and is a
    directory."""
    expected_dir = tmp_path / "_bmad-output" / "init-history"
    assert not expected_dir.exists()

    write_init_history_entry(
        tmp_path,
        action="overwrite-confirmed",
        files_touched=(),
        timestamp="20260508T120000Z",
    )

    assert expected_dir.is_dir()


# --------------------------------------------------------------------------- #
# AC-7 case 16 — `PermissionError` propagates UNCHANGED on read-only audit-dir.#
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="Windows chmod is a no-op; root bypasses POSIX directory-write permission bits",
)
def test_evaluate_propagates_permission_error_on_readonly_audit_dir(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """Given an existing ``_bmad-output/init-history/`` chmodded
    read-only AND a request for the override path, the function
    raises ``PermissionError`` UNCHANGED per Pattern 5 (loud-fail).
    Cleanup restores write permission so ``tmp_path`` removal
    succeeds."""
    _make_existing_project_root(tmp_path)
    audit_dir = tmp_path / "_bmad-output" / "init-history"
    audit_dir.mkdir(parents=True, exist_ok=True)
    original_mode = audit_dir.stat().st_mode
    audit_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x; no write
    try:
        request = GuardRequest(
            project_root=tmp_path,
            override_confirmed=True,
            secondary_confirmed=True,
        )
        with pytest.raises(PermissionError):
            evaluate_non_destructive_guard(
                request,
                run_state=_make_run_state(),
                marker_registry=runtime_marker_registry,
            )
    finally:
        audit_dir.chmod(original_mode)


# --------------------------------------------------------------------------- #
# AC-7 case 17 — `GuardRequest` rejects relative `project_root`.              #
# --------------------------------------------------------------------------- #


def test_guard_request_rejects_relative_project_root() -> None:
    """``GuardRequest`` MUST reject relative paths (mirrors Story 7.4's
    ``is_absolute`` field validator)."""
    with pytest.raises(ValidationError):
        GuardRequest(project_root=pathlib.Path("relative/path"))


# --------------------------------------------------------------------------- #
# AC-7 case 18 — `GuardOutcome` is frozen Pydantic v2.                        #
# --------------------------------------------------------------------------- #


def test_guard_outcome_is_frozen() -> None:
    """``GuardOutcome`` is frozen; attempting to mutate raises
    ``pydantic.ValidationError``."""
    outcome = GuardOutcome(
        action="proceed-fresh",
        existing_files=(),
        audit_log_path=None,
        diagnostic=None,
        notes="ok",
    )
    with pytest.raises(ValidationError):
        outcome.action = "preserve-merge"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# AC-7 case 19 — Resolved targets stay under caller-supplied `project_root`.  #
# --------------------------------------------------------------------------- #


def test_resolved_targets_stay_under_project_root(tmp_path: pathlib.Path) -> None:
    """For every non-halt action, the resolved ``audit_log_path`` (when
    present) AND every path in ``existing_files`` is a descendant of
    the caller-supplied ``project_root``."""
    _make_existing_project_root(tmp_path)
    request_override = GuardRequest(
        project_root=tmp_path,
        override_confirmed=True,
        secondary_confirmed=True,
    )

    outcome, _next_rs = evaluate_non_destructive_guard(
        request_override,
        run_state=_make_run_state(),
        marker_registry=load_marker_class_registry(),
    )

    assert outcome.action == "overwrite-confirmed"
    assert outcome.audit_log_path is not None
    assert outcome.audit_log_path.is_relative_to(tmp_path)
    for p in outcome.existing_files:
        assert p.is_relative_to(tmp_path)


# --------------------------------------------------------------------------- #
# AC-7 case 20 — `run_state=None` halt path is silent (null-guard).           #
# --------------------------------------------------------------------------- #


def test_evaluate_null_runtime_halt_does_not_emit_marker(
    tmp_path: pathlib.Path,
) -> None:
    """When the halt path triggers AND ``run_state=None``, the function
    returns ``(outcome, None)`` AND does NOT call
    ``record_marker_with_context``. Mirrors the null-guard pattern at
    ``init_preconditions.py:557-559``."""
    _make_existing_project_root(tmp_path)
    request = GuardRequest(
        project_root=tmp_path,
        override_confirmed=True,
        secondary_confirmed=False,
    )

    with mock.patch(
        "loud_fail_harness.init_non_destructive_guard.record_marker_with_context"
    ) as mock_record:
        outcome, next_rs = evaluate_non_destructive_guard(
            request, run_state=None, marker_registry=None
        )

    assert outcome.action == "halt-would-destroy"
    assert next_rs is None
    assert mock_record.call_count == 0


# --------------------------------------------------------------------------- #
# AC-7 case 21 — Marker context payload includes `existing_files`+`halt_route`.#
# --------------------------------------------------------------------------- #


def test_marker_context_payload_carries_halt_route_and_existing_files(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """On the halt path, the patched ``record_marker_with_context``
    call's ``context`` keyword carries ``existing_files`` (list of
    path strings), ``halt_route`` (literal value), and a freeform
    ``note`` line."""
    _make_existing_project_root(tmp_path)
    request = GuardRequest(
        project_root=tmp_path,
        override_confirmed=True,
        secondary_confirmed=False,
    )

    with mock.patch(
        "loud_fail_harness.init_non_destructive_guard.record_marker_with_context",
        wraps=init_non_destructive_guard.record_marker_with_context,
    ) as mock_record:
        evaluate_non_destructive_guard(
            request,
            run_state=_make_run_state(),
            marker_registry=runtime_marker_registry,
        )

    assert mock_record.call_count == 1
    call_kwargs = mock_record.call_args.kwargs
    assert call_kwargs["marker_class"] == INIT_WOULD_DESTROY_MARKER_CLASS
    context = call_kwargs["context"]
    assert isinstance(context, dict)
    assert context["halt_route"] == "secondary-confirmation-missing"
    assert isinstance(context["existing_files"], list)
    assert all(isinstance(p, str) for p in context["existing_files"])
    assert context["note"]


# --------------------------------------------------------------------------- #
# AC-7 case 22 — Override on a fresh project (defensive symmetry).            #
# --------------------------------------------------------------------------- #


def test_override_on_fresh_project_proceeds_fresh_no_audit_log(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """``override_confirmed=True, secondary_confirmed=True`` on a FRESH
    project (no existing files) returns ``proceed-fresh`` (NOT
    ``overwrite-confirmed``) — the documented dev's-call per
    Completion Note 3 and the AC-3 exception clause: an audit-log
    entry with ``files_overwritten: []`` has no informational value;
    destruction-record audit logs are only written when actual
    user-owned content is overwritten. The structural witness against
    accidental audit-log proliferation on clean installs."""
    request = GuardRequest(
        project_root=tmp_path,
        override_confirmed=True,
        secondary_confirmed=True,
    )

    outcome, _next_rs = evaluate_non_destructive_guard(
        request,
        run_state=_make_run_state(),
        marker_registry=runtime_marker_registry,
    )

    assert outcome.action == "proceed-fresh"
    assert outcome.audit_log_path is None
    assert outcome.existing_files == ()
    audit_dir = tmp_path / "_bmad-output" / "init-history"
    assert not audit_dir.exists()


# --------------------------------------------------------------------------- #
# Supplementary structural-coverage test — constants match documentation.     #
# --------------------------------------------------------------------------- #


def test_canonical_constants_match_documentation() -> None:
    """``AUDIT_LOG_SUBDIR`` composes to ``_bmad-output/init-history``;
    the marker class string matches the v1 taxonomy entry."""
    assert AUDIT_LOG_SUBDIR == ("_bmad-output", "init-history")
    assert INIT_WOULD_DESTROY_MARKER_CLASS == "init-would-destroy-existing-artifact"
    # Filename pattern matches Story 4.12's allocate_run_id stamp shape.
    assert AUDIT_LOG_FILENAME_PATTERN.match("20260508T120000Z.log")
    assert not AUDIT_LOG_FILENAME_PATTERN.match("20260508T120000Z")
    assert not AUDIT_LOG_FILENAME_PATTERN.match("not-a-stamp.log")


# --------------------------------------------------------------------------- #
# Supplementary structural-coverage test — `MergeResult` is frozen.           #
# --------------------------------------------------------------------------- #


def test_merge_result_is_frozen() -> None:
    """``MergeResult`` is frozen Pydantic v2 (Pattern 6)."""
    mr = MergeResult(
        target_path=pathlib.Path("/tmp/x"),
        action="no-op",
        existing_keys_preserved=0,
        new_keys_added=0,
        bytes_written=None,
    )
    with pytest.raises(ValidationError):
        mr.action = "merged"  # type: ignore[misc]
