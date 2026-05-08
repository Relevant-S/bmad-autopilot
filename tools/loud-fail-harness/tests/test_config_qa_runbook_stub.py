"""Tests for the Story 7.5 config + qa-runbook stub-generation module.

Covers AC-7 — seventeen independent test functions covering:

* canonical content loaders (UTF-8 determinism + ``FileNotFoundError``
  propagation for both templates),
* config canonical content's structural properties per AC-1
  (top-level keys + per-key default values + per-field
  ``# Source:`` cross-references),
* qa-runbook canonical content's structural properties per AC-2
  (three opt-in surface markers + ``Story <N>`` cross-references),
* both stubs parse as YAML (config: non-empty mapping; qa-runbook: dict
  or None for the all-commented case),
* placeholder-free assertions (no leftover ``<TODO>``/``<TBD>``/
  ``<FILL_ME_IN>`` markers),
* ``scaffold_config_qa_runbook_stubs`` happy path (writes BOTH files at
  predictable paths, creates parent dir, returns informative outcome),
* ``scaffold_config_qa_runbook_stubs`` overwrites existing files (Story
  7.6 owns preserve-on-re-run),
* ``PermissionError`` propagates UNCHANGED on read-only parent
  (Pattern 5),
* partial-write posture is loud-fail-by-design — config write succeeds,
  qa-runbook write raises, on-disk state is the partial state (Story
  7.6 owns the cleanup-policy boundary),
* zero marker registrations (Story 1.11 atomic-vs-aggregated principle),
* defensive ``project_root`` scope (resolved targets stay under
  caller-supplied root),
* ``StubScaffoldRequest`` rejects relative ``project_root`` (D1 fix from
  Story 7.4 precedent),
* ``StubScaffoldOutcome`` is frozen Pydantic v2,
* ``resolve_config_path`` + ``resolve_qa_runbook_path`` are pure path-
  arithmetic helpers (no filesystem I/O).

Pattern 5 + Pattern 6 — explicit, named tests; no shared mutable state;
caller-injected ``tmp_path`` so tests do NOT touch the outer workspace's
``_bmad/automation/``.
"""

from __future__ import annotations

import importlib.resources
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

from loud_fail_harness.config_qa_runbook_stub import (
    CONFIG_TARGET_FILENAME,
    CONFIG_TEMPLATE_RESOURCE,
    QA_RUNBOOK_TARGET_FILENAME,
    QA_RUNBOOK_TEMPLATE_RESOURCE,
    STUB_TARGET_SUBDIR,
    StubScaffoldOutcome,
    StubScaffoldRequest,
    load_config_template,
    load_qa_runbook_template,
    resolve_config_path,
    resolve_qa_runbook_path,
    scaffold_config_qa_runbook_stubs,
)

# --------------------------------------------------------------------------- #
# Module-level constants used by multiple tests                                #
# --------------------------------------------------------------------------- #

#: The canonical filenames that land in the user's BMAD project per FR40.
_CONFIG_FILENAME: Final[str] = "config.yaml"
_QA_RUNBOOK_FILENAME: Final[str] = "qa-runbook.yaml"

#: Required top-level keys in the config canonical content per AC-1
#: (``epics.md`` line 3017 verbatim).
_REQUIRED_CONFIG_KEYS_AND_VALUES: Final[dict[str, int]] = {
    "retry_budget": 2,
    "specialist_timeout_minutes": 15,
    "cost_ceiling_per_story": 5,
    "evidence_max_size_mb": 50,
    "story_doc_version_tolerance_window": 2,
}

#: Required FR/NFR identifiers in the config ``# Source:`` cross-references
#: per AC-1 / AC-7 case 4. The five core defaults' source identifiers.
_REQUIRED_CONFIG_SOURCE_IDENTIFIERS: Final[tuple[str, ...]] = (
    "FR8",
    "NFR-P2",
    "NFR-P1",
    "NFR-P6",
    "FR43",
)

#: Required ``Story <N>`` cross-references in the qa-runbook canonical
#: content per AC-2 / AC-7 case 5.
_REQUIRED_QA_RUNBOOK_STORY_REFS: Final[tuple[str, ...]] = (
    "Story 4.1",
    "Story 4.8",
    "Story 4.12",
)

#: Required canonical-name strings in the qa-runbook content per AC-7
#: case 5 — exercise the documented opt-in field names directly.
_REQUIRED_QA_RUNBOOK_NAME_STRINGS: Final[tuple[str, ...]] = (
    "masked_selectors",
    "tier_3_semantic_verification",
    "behavioral_plan_overrides",
    "not_configured",
)

#: Forbidden placeholder markers per AC-7 case 7.
_FORBIDDEN_PLACEHOLDERS: Final[tuple[str, ...]] = (
    "<TODO>",
    "<TBD>",
    "<FILL_ME_IN>",
)


# --------------------------------------------------------------------------- #
# AC-7 case 1 — `load_config_template` returns canonical UTF-8 content.        #
# --------------------------------------------------------------------------- #


def test_load_config_template_returns_canonical_utf8() -> None:
    """The function returns a non-empty UTF-8 string whose first non-blank
    line starts with ``#`` (the YAML comment-header convention); two
    consecutive calls return BYTE-IDENTICAL content (defensive against
    accidental in-memory mutation)."""
    first = load_config_template()
    second = load_config_template()

    assert isinstance(first, str)
    assert first  # non-empty
    assert first == second  # byte-identical across calls

    first_non_blank_line = next(line for line in first.splitlines() if line.strip())
    assert first_non_blank_line.startswith("#"), (
        f"config canonical content's first non-blank line MUST be a YAML "
        f"comment; got: {first_non_blank_line!r}"
    )

    # Confirm UTF-8 round-trip — encoding/decoding is lossless.
    assert first.encode("utf-8").decode("utf-8") == first


# --------------------------------------------------------------------------- #
# AC-7 case 2 — `load_qa_runbook_template` returns canonical UTF-8 content.    #
# --------------------------------------------------------------------------- #


def test_load_qa_runbook_template_returns_canonical_utf8() -> None:
    """Same shape as the config-template case against the qa-runbook
    template."""
    first = load_qa_runbook_template()
    second = load_qa_runbook_template()

    assert isinstance(first, str)
    assert first
    assert first == second

    first_non_blank_line = next(line for line in first.splitlines() if line.strip())
    assert first_non_blank_line.startswith("#"), (
        f"qa-runbook canonical content's first non-blank line MUST be a "
        f"YAML comment; got: {first_non_blank_line!r}"
    )

    assert first.encode("utf-8").decode("utf-8") == first


# --------------------------------------------------------------------------- #
# AC-7 case 3 — Both loaders propagate `FileNotFoundError` UNCHANGED.          #
# --------------------------------------------------------------------------- #


def test_load_config_template_propagates_file_not_found_unchanged() -> None:
    """If the packaged resource is missing (build-time misconfiguration),
    `FileNotFoundError` propagates UNCHANGED. The function does NOT
    swallow into a sentinel string per Pattern 5."""
    with mock.patch(
        "loud_fail_harness.config_qa_runbook_stub.importlib.resources.files"
    ) as mock_files:
        mock_resource = mock.Mock()
        mock_resource.joinpath.return_value.read_text.side_effect = (
            FileNotFoundError(f"packaged resource {CONFIG_TEMPLATE_RESOURCE} missing")
        )
        mock_files.return_value = mock_resource

        with pytest.raises(FileNotFoundError) as exc_info:
            load_config_template()
        assert CONFIG_TEMPLATE_RESOURCE in str(exc_info.value)


def test_load_qa_runbook_template_propagates_file_not_found_unchanged() -> None:
    """Same posture as the config case for the qa-runbook loader."""
    with mock.patch(
        "loud_fail_harness.config_qa_runbook_stub.importlib.resources.files"
    ) as mock_files:
        mock_resource = mock.Mock()
        mock_resource.joinpath.return_value.read_text.side_effect = (
            FileNotFoundError(
                f"packaged resource {QA_RUNBOOK_TEMPLATE_RESOURCE} missing"
            )
        )
        mock_files.return_value = mock_resource

        with pytest.raises(FileNotFoundError) as exc_info:
            load_qa_runbook_template()
        assert QA_RUNBOOK_TEMPLATE_RESOURCE in str(exc_info.value)


# --------------------------------------------------------------------------- #
# AC-7 case 4 — Config stub has FR40-named fields with `Source:` refs.         #
# --------------------------------------------------------------------------- #


def test_config_stub_has_required_fields_with_source_cross_references() -> None:
    """The config canonical content parses as a YAML mapping containing
    EXACTLY the five required keys per AC-1 with the expected default
    values; the textual content contains EACH of the five required
    ``# Source:`` cross-reference identifiers per AC-7 case 4."""
    content = load_config_template()
    parsed = yaml.safe_load(content)

    assert isinstance(parsed, dict), (
        f"config canonical content MUST parse as a YAML mapping; "
        f"got {type(parsed).__name__}"
    )
    assert parsed, "config canonical content MUST be non-empty"

    for key, expected_value in _REQUIRED_CONFIG_KEYS_AND_VALUES.items():
        assert key in parsed, (
            f"config canonical content missing required FR40 field {key!r}"
        )
        assert parsed[key] == expected_value, (
            f"config field {key!r} default value drift: expected "
            f"{expected_value!r}, got {parsed[key]!r}"
        )

    for identifier in _REQUIRED_CONFIG_SOURCE_IDENTIFIERS:
        pattern = re.compile(rf"^# Source:.*\b{re.escape(identifier)}\b", re.MULTILINE)
        assert pattern.search(content), (
            f"config canonical content missing required `# Source:` "
            f"cross-reference for {identifier!r}; AC-1 requires every "
            f"documented field to carry a grep-matchable FR/NFR pointer"
        )


# --------------------------------------------------------------------------- #
# AC-7 case 5 — Qa-runbook stub has three opt-in surfaces + Story refs.        #
# --------------------------------------------------------------------------- #


def test_qa_runbook_stub_has_three_opt_in_surfaces_with_story_cross_references() -> None:
    """The qa-runbook canonical content's textual content contains
    ``Story 4.1`` / ``Story 4.8`` / ``Story 4.12`` adjacent to the
    documented commented-out blocks per AC-2; the canonical names
    ``masked_selectors`` / ``tier_3_semantic_verification`` /
    ``behavioral_plan_overrides`` / ``not_configured`` are present
    per AC-7 case 5."""
    content = load_qa_runbook_template()

    for story_ref in _REQUIRED_QA_RUNBOOK_STORY_REFS:
        pattern = re.compile(rf"# .*\b{re.escape(story_ref)}\b", re.MULTILINE)
        assert pattern.search(content), (
            f"qa-runbook canonical content missing required {story_ref!r} "
            f"cross-reference (must appear in a `# Story <N>` comment line)"
        )

    for name in _REQUIRED_QA_RUNBOOK_NAME_STRINGS:
        assert name in content, (
            f"qa-runbook canonical content missing required canonical "
            f"name string {name!r}"
        )


# --------------------------------------------------------------------------- #
# AC-7 case 6 — Both stubs parse as YAML (config: dict; qa-runbook: dict|None).#
# --------------------------------------------------------------------------- #


def test_both_stubs_parse_as_yaml() -> None:
    """The config stub parses to a non-empty `dict`; the qa-runbook
    stub parses to a `dict` (possibly empty if all opt-in surfaces are
    commented out — explicit handling of the all-commented case per
    AC-2). The test asserts the parse succeeds and is a `dict`-or-None
    for the qa-runbook (commented-out case yields None per
    PyYAML's safe_load)."""
    config_parsed = yaml.safe_load(load_config_template())
    assert isinstance(config_parsed, dict), (
        f"config stub MUST parse as a non-None YAML mapping; "
        f"got {type(config_parsed).__name__}"
    )
    assert config_parsed, "config stub MUST be a non-empty mapping"

    qa_runbook_parsed = yaml.safe_load(load_qa_runbook_template())
    assert qa_runbook_parsed is None or isinstance(qa_runbook_parsed, dict), (
        f"qa-runbook stub MUST parse to a YAML mapping (or None for the "
        f"all-commented case); got {type(qa_runbook_parsed).__name__}"
    )
    # Defensive: NEVER a string or list (per AC-7 case 6 verbatim).
    assert not isinstance(qa_runbook_parsed, (str, list)), (
        "qa-runbook stub must not parse as a string or list"
    )


# --------------------------------------------------------------------------- #
# AC-7 case 7 — Both stubs do NOT contain placeholder markers.                 #
# --------------------------------------------------------------------------- #


def test_both_stubs_have_no_placeholder_markers() -> None:
    """Per AC-7 case 7: the canonical content has no leftover
    ``<TODO>`` / ``<TBD>`` / ``<FILL_ME_IN>`` placeholder strings
    (case-insensitive)."""
    for label, content in (
        ("config", load_config_template()),
        ("qa-runbook", load_qa_runbook_template()),
    ):
        lower = content.lower()
        for placeholder in _FORBIDDEN_PLACEHOLDERS:
            assert placeholder.lower() not in lower, (
                f"{label} canonical content contains forbidden placeholder "
                f"{placeholder!r}; canonical templates must ship without "
                f"leftover placeholders"
            )


# --------------------------------------------------------------------------- #
# AC-7 case 8 — Happy-path scaffold writes BOTH files at predictable paths.    #
# --------------------------------------------------------------------------- #


def test_scaffold_happy_path_writes_both_files_at_predictable_paths(
    tmp_path: pathlib.Path,
) -> None:
    """`scaffold_config_qa_runbook_stubs` writes BOTH canonical contents
    to ``<project_root>/_bmad/automation/{config,qa-runbook}.yaml`` and
    returns an informative outcome with both byte lengths."""
    request = StubScaffoldRequest(project_root=tmp_path)
    outcome = scaffold_config_qa_runbook_stubs(request)

    expected_config = tmp_path / "_bmad" / "automation" / _CONFIG_FILENAME
    expected_qa_runbook = tmp_path / "_bmad" / "automation" / _QA_RUNBOOK_FILENAME

    assert outcome.outcome == "scaffolded"
    assert outcome.config_target_path == expected_config
    assert outcome.qa_runbook_target_path == expected_qa_runbook
    assert outcome.config_target_path.is_file()
    assert outcome.qa_runbook_target_path.is_file()

    written_config = outcome.config_target_path.read_text(encoding="utf-8")
    written_qa_runbook = outcome.qa_runbook_target_path.read_text(encoding="utf-8")
    canonical_config = load_config_template()
    canonical_qa_runbook = load_qa_runbook_template()

    assert written_config == canonical_config
    assert written_qa_runbook == canonical_qa_runbook

    assert outcome.config_bytes_written == len(canonical_config.encode("utf-8"))
    assert outcome.qa_runbook_bytes_written == len(canonical_qa_runbook.encode("utf-8"))

    assert outcome.notes
    assert str(expected_config) in outcome.notes
    assert str(expected_qa_runbook) in outcome.notes


# --------------------------------------------------------------------------- #
# AC-7 case 9 — Scaffold creates parent directories if absent.                 #
# --------------------------------------------------------------------------- #


def test_scaffold_creates_parent_directories(tmp_path: pathlib.Path) -> None:
    """Given `tmp_path` where `_bmad/automation/` does NOT yet exist,
    the function succeeds; after the call, the parent directories
    exist and are directories (not files)."""
    parent_dir = tmp_path / "_bmad" / "automation"
    assert not parent_dir.exists()

    request = StubScaffoldRequest(project_root=tmp_path)
    outcome = scaffold_config_qa_runbook_stubs(request)

    assert outcome.outcome == "scaffolded"
    assert parent_dir.is_dir()
    assert parent_dir.parent.is_dir()


# --------------------------------------------------------------------------- #
# AC-7 case 10 — Scaffold overwrites existing files (Story 7.6 owns preserve). #
# --------------------------------------------------------------------------- #


def test_scaffold_overwrites_existing_files(tmp_path: pathlib.Path) -> None:
    """Story 7.6 owns the preserve-on-re-run rule per ``epics.md`` line
    3050 AND the additive-merge rule per line 3051. Story 7.5's
    substrate function's contract is "write the canonical content to
    the target paths"; called against existing files at both target
    paths, the function OVERWRITES both. The orchestrator skill at
    thickening time is responsible for invoking this function ONLY
    when the non-destructive guard has cleared the target paths OR
    `--overwrite-confirmed` was passed."""
    expected_config = tmp_path / "_bmad" / "automation" / _CONFIG_FILENAME
    expected_qa_runbook = tmp_path / "_bmad" / "automation" / _QA_RUNBOOK_FILENAME
    expected_config.parent.mkdir(parents=True, exist_ok=True)
    expected_config.write_text("stale config from a previous run\n", encoding="utf-8")
    expected_qa_runbook.write_text(
        "stale qa-runbook from a previous run\n", encoding="utf-8"
    )

    request = StubScaffoldRequest(project_root=tmp_path)
    outcome = scaffold_config_qa_runbook_stubs(request)

    assert outcome.outcome == "scaffolded"
    assert expected_config.read_text(encoding="utf-8") == load_config_template()
    assert (
        expected_qa_runbook.read_text(encoding="utf-8") == load_qa_runbook_template()
    )


# --------------------------------------------------------------------------- #
# AC-7 case 11 — `PermissionError` propagates UNCHANGED.                       #
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="Windows chmod is a no-op; root bypasses POSIX directory-write permission bits",
)
def test_scaffold_propagates_permission_error_unchanged(
    tmp_path: pathlib.Path,
) -> None:
    """Given `tmp_path` with a read-only `_bmad/automation/` directory,
    the function raises `PermissionError` UNCHANGED per Pattern 5
    (loud-fail). Cleanup restores write permission so `tmp_path`
    removal succeeds."""
    parent_dir = tmp_path / "_bmad" / "automation"
    parent_dir.mkdir(parents=True)

    original_mode = parent_dir.stat().st_mode
    parent_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x; no write
    try:
        request = StubScaffoldRequest(project_root=tmp_path)
        with pytest.raises(PermissionError):
            scaffold_config_qa_runbook_stubs(request)
    finally:
        parent_dir.chmod(original_mode)


# --------------------------------------------------------------------------- #
# AC-7 case 12 — Partial-write posture is loud-fail-by-design.                 #
# --------------------------------------------------------------------------- #


def test_scaffold_partial_write_is_loud_fail_by_design(
    tmp_path: pathlib.Path,
) -> None:
    """Story 7.5's substrate function is loud-fail-by-design per
    AC-5: if the config write succeeds and the qa-runbook write
    raises, the function does NOT clean up the partial config file —
    the orchestrator skill at thickening time (Story 7.6) is the
    cleanup-policy boundary. The test patches `pathlib.Path.write_text`
    to succeed for the config path AND raise `PermissionError` for
    the qa-runbook path, then inspects the on-disk state."""
    expected_config = tmp_path / "_bmad" / "automation" / _CONFIG_FILENAME
    expected_qa_runbook = tmp_path / "_bmad" / "automation" / _QA_RUNBOOK_FILENAME

    real_write_text = pathlib.Path.write_text

    def selective_write_text(
        self: pathlib.Path, *args: object, **kwargs: object
    ) -> int:
        if self == expected_qa_runbook:
            raise PermissionError(f"simulated write failure on {self}")
        return real_write_text(self, *args, **kwargs)  # type: ignore[arg-type]

    request = StubScaffoldRequest(project_root=tmp_path)
    with mock.patch.object(pathlib.Path, "write_text", selective_write_text):
        with pytest.raises(PermissionError):
            scaffold_config_qa_runbook_stubs(request)

    # On-disk state: config written, qa-runbook absent. Story 7.6 owns
    # the cleanup-policy boundary; Story 7.5 leaves the partial state
    # for the policy-layer caller to inspect.
    assert expected_config.is_file()
    assert expected_config.read_text(encoding="utf-8") == load_config_template()
    assert not expected_qa_runbook.exists()


# --------------------------------------------------------------------------- #
# AC-7 case 13 — Scaffold registers ZERO markers.                              #
# --------------------------------------------------------------------------- #


def test_scaffold_does_not_register_any_markers(tmp_path: pathlib.Path) -> None:
    """Story 7.5 introduces ZERO new marker classes. The patch target
    is the CONSUMING module's namespace
    (`loud_fail_harness.config_qa_runbook_stub.record_marker_with_context`)
    per Story 7.4's deferred-review fix; the import is present in the
    consuming module solely to expose the patchable symbol.

    Covers all three invocation paths per AC-7 case 13 verbatim: happy-path,
    overwrite, AND partial-write (config succeeds, qa-runbook raises)."""
    with mock.patch(
        "loud_fail_harness.config_qa_runbook_stub.record_marker_with_context"
    ) as mock_record:
        # Happy path
        scaffold_config_qa_runbook_stubs(
            StubScaffoldRequest(project_root=tmp_path)
        )
        # Re-call against existing files (overwrites) — same path, no marker.
        scaffold_config_qa_runbook_stubs(
            StubScaffoldRequest(project_root=tmp_path)
        )
        # Partial-write path — config succeeds, qa-runbook write raises;
        # no marker must be registered per AC-5 + Story 1.11.
        expected_qa_runbook = (
            tmp_path / "_bmad" / "automation" / _QA_RUNBOOK_FILENAME
        )
        real_write_text = pathlib.Path.write_text

        def _fail_on_qa_runbook(
            self: pathlib.Path, *args: object, **kwargs: object
        ) -> int:
            if self == expected_qa_runbook:
                raise PermissionError("simulated qa-runbook write failure")
            return real_write_text(self, *args, **kwargs)  # type: ignore[arg-type]

        with mock.patch.object(pathlib.Path, "write_text", _fail_on_qa_runbook):
            with pytest.raises(PermissionError):
                scaffold_config_qa_runbook_stubs(
                    StubScaffoldRequest(project_root=tmp_path)
                )
        assert not mock_record.called, (
            "Story 7.5 introduces zero marker classes; "
            "scaffold must not call record_marker_with_context"
        )


# --------------------------------------------------------------------------- #
# AC-7 case 14 — Resolved targets stay under caller-supplied `project_root`.   #
# --------------------------------------------------------------------------- #


def test_resolved_targets_stay_under_project_root(tmp_path: pathlib.Path) -> None:
    """Per AC-4 / Story 7.4's deferred-review fix to the prefix-collision
    issue: both resolved target paths must be descendants of the caller-
    supplied `project_root`; the scaffolder must NEVER write to the
    canonical resource path inside the harness package (`_data/`)."""
    config_target = resolve_config_path(tmp_path)
    qa_runbook_target = resolve_qa_runbook_path(tmp_path)

    assert config_target.is_relative_to(tmp_path), (
        f"config target {config_target!r} escaped caller-supplied "
        f"project_root {tmp_path!r}"
    )
    assert qa_runbook_target.is_relative_to(tmp_path), (
        f"qa-runbook target {qa_runbook_target!r} escaped caller-supplied "
        f"project_root {tmp_path!r}"
    )

    # And neither must resolve to the harness's `_data/` packaged resources.
    canonical_config_resource = str(
        importlib.resources.files("loud_fail_harness").joinpath(
            CONFIG_TEMPLATE_RESOURCE
        )
    )
    canonical_qa_runbook_resource = str(
        importlib.resources.files("loud_fail_harness").joinpath(
            QA_RUNBOOK_TEMPLATE_RESOURCE
        )
    )
    assert str(config_target) != canonical_config_resource
    assert str(qa_runbook_target) != canonical_qa_runbook_resource


# --------------------------------------------------------------------------- #
# AC-7 case 15 — `StubScaffoldRequest` rejects relative `project_root`.        #
# --------------------------------------------------------------------------- #


def test_scaffold_request_rejects_relative_project_root() -> None:
    """`StubScaffoldRequest` MUST reject relative paths for `project_root`
    (mirrors Story 7.4's `is_absolute` field validator). The validator
    enforces that resolved target paths are always absolute, preventing
    accidentally-cwd-relative target writes."""
    with pytest.raises(ValidationError):
        StubScaffoldRequest(project_root=pathlib.Path("relative/path"))


# --------------------------------------------------------------------------- #
# AC-7 case 16 — `StubScaffoldOutcome` is frozen Pydantic v2.                  #
# --------------------------------------------------------------------------- #


def test_outcome_model_is_frozen_pydantic_v2() -> None:
    """`StubScaffoldOutcome` is frozen (Pattern 6 — immutable typed
    boundaries); attempting to mutate raises `pydantic.ValidationError`."""
    outcome = StubScaffoldOutcome(
        outcome="scaffolded",
        config_target_path=pathlib.Path("/tmp/c"),
        qa_runbook_target_path=pathlib.Path("/tmp/q"),
        config_bytes_written=42,
        qa_runbook_bytes_written=99,
        notes="ok",
    )
    with pytest.raises(ValidationError):
        outcome.outcome = "scaffolded"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# AC-7 case 17 — Path resolvers are pure (no filesystem I/O).                  #
# --------------------------------------------------------------------------- #


def test_path_resolvers_are_pure(tmp_path: pathlib.Path) -> None:
    """`resolve_config_path` and `resolve_qa_runbook_path` are pure path-
    arithmetic helpers; calling them does NOT mkdir, does NOT touch
    the filesystem, does NOT raise on a non-existent project_root."""
    nonexistent = tmp_path / "definitely-does-not-exist"
    assert not nonexistent.exists()

    config_target = resolve_config_path(nonexistent)
    qa_runbook_target = resolve_qa_runbook_path(nonexistent)

    assert config_target == (
        nonexistent / "_bmad" / "automation" / _CONFIG_FILENAME
    )
    assert qa_runbook_target == (
        nonexistent / "_bmad" / "automation" / _QA_RUNBOOK_FILENAME
    )
    # Filesystem untouched after the calls.
    assert not nonexistent.exists()
    assert not config_target.parent.exists()


# --------------------------------------------------------------------------- #
# Supplementary structural-coverage test — constants match documentation.     #
# --------------------------------------------------------------------------- #


def test_canonical_constants_match_documentation() -> None:
    """The canonical-path constants compose to the FR40-documented user-
    facing paths (``_bmad/automation/config.yaml`` and
    ``_bmad/automation/qa-runbook.yaml``)."""
    assert STUB_TARGET_SUBDIR == ("_bmad", "automation")
    assert CONFIG_TARGET_FILENAME == "config.yaml"
    assert QA_RUNBOOK_TARGET_FILENAME == "qa-runbook.yaml"
    assert CONFIG_TEMPLATE_RESOURCE == "_data/config.yaml.template"
    assert QA_RUNBOOK_TEMPLATE_RESOURCE == "_data/qa-runbook.yaml.template"
