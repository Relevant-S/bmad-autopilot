"""Tests for the Story 7.7 BMAD story-doc N-2 version-tolerance check
substrate module.

Covers AC-7 — 22 test cases covering:

* tier-1 inline-marker detection (cases 1-3),
* tier-2 manifest-fallback detection (case 4),
* detection failures with structured ``reason`` (cases 5-6),
* tolerance-window comparison (silent / boundary / out-of-window /
  newer-than-supported / overrides / config absent / config
  non-integer / null run-state) (cases 7-15),
* upgrade-guidance loading (case 16-19),
* the SINGLE end-to-end contract-pair test against the PRODUCTION doc
  (case 20),
* the version-tolerance fixture sweep N-0 / N-1 / N-2 / N-3 / N-4
  (case 21),
* the pluggability-gate posture (case 22).

Pattern 5 + Pattern 6 — explicit, named tests; no shared mutable
state; caller-injected ``tmp_path`` so tests do NOT touch the outer
workspace's ``_bmad/`` or ``docs/``.
"""

from __future__ import annotations

import pathlib
import textwrap
from unittest import mock

import pytest
import yaml as _pyyaml

from loud_fail_harness import story_doc_version_check
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.run_state import CostToDateBySpecialist, RunState
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)
from loud_fail_harness.story_doc_version_check import (
    STORY_DOC_VERSION_OUT_OF_WINDOW_MARKER_CLASS,
    SUPPORTED_BMM_TEMPLATE_VERSION,
    StoryDocVersionDetectionError,
    VersionCheckRequest,
    check_story_doc_version,
    detect_template_version,
    load_upgrade_guidance,
)


# --------------------------------------------------------------------------- #
# Fixtures + helpers                                                           #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def prod_repo_root() -> pathlib.Path:
    return find_repo_root()


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    return load_marker_class_registry()


def _make_run_state() -> RunState:
    return RunState(
        schema_version="1.3",
        story_id="7-7-test",
        run_id="run-001",
        current_state="in-progress",
        branch_name="bmad-automation/story/7-7-test",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )


def _write_story_doc_with_inline_marker(
    tmp_path: pathlib.Path,
    *,
    version_token: str,
    line_offset: int = 5,
    filename: str = "story.md",
) -> pathlib.Path:
    """Materialize a story doc with an inline version marker on a
    specific line. ``line_offset`` is 1-based; line 5 means the
    marker is the 5th line in the file.
    """
    lines = []
    for i in range(1, line_offset):
        lines.append(f"Line {i} filler")
    lines.append(f"<!-- bmm-template-version: {version_token} -->")
    lines.append("")
    lines.append("## Story")
    lines.append("Body content.")
    path = tmp_path / filename
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_story_doc_no_inline_marker(
    tmp_path: pathlib.Path, filename: str = "story.md"
) -> pathlib.Path:
    path = tmp_path / filename
    path.write_text(
        "# Story 7-7-test\n\nStatus: ready-for-dev\n\n## Story\n\nBody.\n",
        encoding="utf-8",
    )
    return path


def _write_manifest(
    tmp_path: pathlib.Path,
    *,
    bmm_version: str | None = "6.2.2",
    include_bmm: bool = True,
    include_modules_key: bool = True,
    raw_text: str | None = None,
) -> pathlib.Path:
    """Materialize ``<tmp_path>/_bmad/_config/manifest.yaml`` with the
    requested shape. When ``raw_text`` is supplied, it overrides the
    structured construction and is written verbatim (used to test
    parse errors).
    """
    manifest_path = tmp_path / "_bmad" / "_config" / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_text is not None:
        manifest_path.write_text(raw_text, encoding="utf-8")
        return manifest_path
    modules_block: list[dict[str, object]] = [{"name": "core", "version": "6.2.2"}]
    if include_bmm:
        bmm_entry: dict[str, object] = {"name": "bmm"}
        if bmm_version is not None:
            bmm_entry["version"] = bmm_version
        modules_block.append(bmm_entry)
    if include_modules_key:
        manifest = {"modules": modules_block}
    else:
        manifest = {"not_modules": modules_block}
    manifest_path.write_text(_pyyaml.safe_dump(manifest), encoding="utf-8")
    return manifest_path


_SENTINEL = object()


def _write_config_file(
    tmp_path: pathlib.Path,
    *,
    tolerance_window: object = _SENTINEL,
    omit_field: bool = False,
) -> pathlib.Path:
    config_path = tmp_path / "_bmad" / "automation" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if omit_field or tolerance_window is _SENTINEL:
        body = "some_other_field: value\n"
    else:
        body = _pyyaml.safe_dump(
            {"story_doc_version_tolerance_window": tolerance_window}
        )
    config_path.write_text(body, encoding="utf-8")
    return config_path


# --------------------------------------------------------------------------- #
# AC-7 case 1: inline marker on first 20 lines                                 #
# --------------------------------------------------------------------------- #


def test_detect_template_version_inline_marker_first_20_lines(
    tmp_path: pathlib.Path,
) -> None:
    story_path = _write_story_doc_with_inline_marker(
        tmp_path, version_token="6.2", line_offset=5
    )
    result = detect_template_version(story_path, tmp_path)
    assert result == "6.2"


# --------------------------------------------------------------------------- #
# AC-7 case 2: inline marker with patch-version normalized to minor            #
# --------------------------------------------------------------------------- #


def test_detect_template_version_inline_marker_with_patch_version_normalized_to_minor(
    tmp_path: pathlib.Path,
) -> None:
    story_path = _write_story_doc_with_inline_marker(
        tmp_path, version_token="6.2.7"
    )
    assert detect_template_version(story_path, tmp_path) == "6.2"


# --------------------------------------------------------------------------- #
# AC-7 case 3: inline marker after line 20 not consulted                       #
# --------------------------------------------------------------------------- #


def test_detect_template_version_inline_marker_after_line_20_not_consulted(
    tmp_path: pathlib.Path,
) -> None:
    """Marker on line 25 is OUTSIDE the front-matter window. Manifest
    fallback (BMM 6.2) wins."""
    story_path = _write_story_doc_with_inline_marker(
        tmp_path, version_token="5.5", line_offset=25
    )
    _write_manifest(tmp_path, bmm_version="6.2.2")
    assert detect_template_version(story_path, tmp_path) == "6.2"


# --------------------------------------------------------------------------- #
# AC-7 case 4: manifest fallback when no inline marker                         #
# --------------------------------------------------------------------------- #


def test_detect_template_version_manifest_fallback_when_no_inline_marker(
    tmp_path: pathlib.Path,
) -> None:
    story_path = _write_story_doc_no_inline_marker(tmp_path)
    _write_manifest(tmp_path, bmm_version="6.2.2")
    assert detect_template_version(story_path, tmp_path) == "6.2"


# --------------------------------------------------------------------------- #
# AC-7 case 5: raises when inline absent and manifest missing                  #
# --------------------------------------------------------------------------- #


def test_detect_template_version_raises_when_inline_absent_and_manifest_missing(
    tmp_path: pathlib.Path,
) -> None:
    story_path = _write_story_doc_no_inline_marker(tmp_path)
    # No manifest written.
    with pytest.raises(StoryDocVersionDetectionError) as exc_info:
        detect_template_version(story_path, tmp_path)
    assert exc_info.value.reason == "manifest-missing"
    assert exc_info.value.story_doc_path == story_path
    assert exc_info.value.project_root == tmp_path


# --------------------------------------------------------------------------- #
# AC-7 case 6: raises when manifest lacks BMM module                           #
# --------------------------------------------------------------------------- #


def test_detect_template_version_raises_when_manifest_lacks_bmm_module(
    tmp_path: pathlib.Path,
) -> None:
    story_path = _write_story_doc_no_inline_marker(tmp_path)
    _write_manifest(tmp_path, include_bmm=False)
    with pytest.raises(StoryDocVersionDetectionError) as exc_info:
        detect_template_version(story_path, tmp_path)
    assert exc_info.value.reason == "bmm-module-not-listed"


# --------------------------------------------------------------------------- #
# AC-7 case 7: proceed-silent within window                                    #
# --------------------------------------------------------------------------- #


def test_check_story_doc_version_proceed_silent_within_window(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    story_path = _write_story_doc_with_inline_marker(
        tmp_path, version_token=SUPPORTED_BMM_TEMPLATE_VERSION
    )
    request = VersionCheckRequest(
        story_doc_path=story_path,
        project_root=tmp_path,
        tolerance_window=2,
    )
    rs = _make_run_state()
    with mock.patch.object(
        story_doc_version_check, "record_marker_with_context"
    ) as emit_mock:
        outcome, next_rs = check_story_doc_version(
            request, run_state=rs, marker_registry=runtime_marker_registry
        )
    assert outcome.action == "proceed-silent"
    assert outcome.detected_version == SUPPORTED_BMM_TEMPLATE_VERSION
    assert outcome.delta_minor_versions == 0
    assert outcome.diagnostic_pointer is None
    assert next_rs is rs
    emit_mock.assert_not_called()


# --------------------------------------------------------------------------- #
# AC-7 case 8: proceed-silent at window boundary                               #
# --------------------------------------------------------------------------- #


def test_check_story_doc_version_proceed_silent_at_window_boundary(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """`detected="6.0"`, `supported="6.2"`, `tolerance_window=2` →
    `delta=2 == window` → proceed-silent (boundary inclusive)."""
    story_path = _write_story_doc_with_inline_marker(
        tmp_path, version_token="6.0"
    )
    request = VersionCheckRequest(
        story_doc_path=story_path,
        project_root=tmp_path,
        tolerance_window=2,
    )
    with mock.patch.object(
        story_doc_version_check, "record_marker_with_context"
    ) as emit_mock:
        outcome, _ = check_story_doc_version(
            request,
            run_state=_make_run_state(),
            marker_registry=runtime_marker_registry,
        )
    assert outcome.action == "proceed-silent"
    assert outcome.delta_minor_versions == 2
    emit_mock.assert_not_called()


# --------------------------------------------------------------------------- #
# AC-7 case 9: emits marker outside window                                     #
# --------------------------------------------------------------------------- #


def test_check_story_doc_version_emits_marker_outside_window(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """`detected="5.9"`, `supported="6.2"`, `tolerance_window=2` →
    `delta=3 > window` → proceed-with-marker; emission once."""
    story_path = _write_story_doc_with_inline_marker(
        tmp_path, version_token="5.9"
    )
    request = VersionCheckRequest(
        story_doc_path=story_path,
        project_root=tmp_path,
        tolerance_window=2,
    )
    rs = _make_run_state()
    with mock.patch.object(
        story_doc_version_check,
        "record_marker_with_context",
        wraps=story_doc_version_check.record_marker_with_context,
    ) as emit_spy:
        outcome, next_rs = check_story_doc_version(
            request, run_state=rs, marker_registry=runtime_marker_registry
        )
    assert outcome.action == "proceed-with-marker"
    assert outcome.detected_version == "5.9"
    assert outcome.supported_version == "6.2"
    assert outcome.tolerance_window == 2
    assert outcome.delta_minor_versions == 3
    assert outcome.diagnostic_pointer is not None
    assert "5.9" in outcome.diagnostic_pointer
    assert "6.2" in outcome.diagnostic_pointer
    # The marker must be recorded exactly once on next_rs.
    assert emit_spy.call_count == 1
    assert next_rs is not None
    assert next_rs is not rs
    assert (
        STORY_DOC_VERSION_OUT_OF_WINDOW_MARKER_CLASS in next_rs.active_markers
    )
    assert (
        len(
            [
                m
                for m in next_rs.active_markers
                if m == STORY_DOC_VERSION_OUT_OF_WINDOW_MARKER_CLASS
            ]
        )
        == 1
    )
    # Context payload carries all six fields per AC-4.
    payload = next_rs.marker_contexts[
        STORY_DOC_VERSION_OUT_OF_WINDOW_MARKER_CLASS
    ]
    assert payload["detected_version"] == "5.9"
    assert payload["supported_version"] == "6.2"
    assert payload["tolerance_window"] == 2
    assert payload["delta_minor_versions"] == 3
    assert payload["story_doc_path"] == str(story_path)
    assert "upgrade_guidance_path" in payload
    assert "note" in payload


# --------------------------------------------------------------------------- #
# AC-7 case 10: newer-than-supported clamped to zero delta                     #
# --------------------------------------------------------------------------- #


def test_check_story_doc_version_newer_than_supported_clamped_to_zero_delta(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    story_path = _write_story_doc_with_inline_marker(
        tmp_path, version_token="6.5"
    )
    request = VersionCheckRequest(
        story_doc_path=story_path,
        project_root=tmp_path,
        tolerance_window=2,
    )
    outcome, _ = check_story_doc_version(
        request,
        run_state=_make_run_state(),
        marker_registry=runtime_marker_registry,
    )
    assert outcome.action == "proceed-silent"
    assert outcome.delta_minor_versions == 0


# --------------------------------------------------------------------------- #
# AC-7 case 11: caller override wins over config-file value                    #
# --------------------------------------------------------------------------- #


def test_check_story_doc_version_caller_override_window_takes_precedence_over_config_file(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    story_path = _write_story_doc_with_inline_marker(
        tmp_path, version_token="6.2"
    )
    _write_config_file(tmp_path, tolerance_window=5)
    # Override = 0 → strictest possible. Detected = supported, delta = 0;
    # 0 <= 0 → silent. Use a slightly older detected to flip behavior.
    story_path_older = _write_story_doc_with_inline_marker(
        tmp_path,
        version_token="6.1",
        filename="older.md",
    )
    request = VersionCheckRequest(
        story_doc_path=story_path_older,
        project_root=tmp_path,
        tolerance_window=0,
    )
    outcome, _ = check_story_doc_version(
        request,
        run_state=_make_run_state(),
        marker_registry=runtime_marker_registry,
    )
    # delta = 1, window = 0 → out-of-window (proves override beat the
    # config's permissive 5).
    assert outcome.action == "proceed-with-marker"
    assert outcome.tolerance_window == 0
    # Smoke that the same call with no override would be silent under
    # the config-file's 5.
    request_no_override = request.model_copy(update={"tolerance_window": None})
    outcome_no_override, _ = check_story_doc_version(
        request_no_override,
        run_state=_make_run_state(),
        marker_registry=runtime_marker_registry,
    )
    assert outcome_no_override.action == "proceed-silent"
    assert outcome_no_override.tolerance_window == 5
    # Suppress unused-warnings.
    assert story_path.exists()


# --------------------------------------------------------------------------- #
# AC-7 case 12: config-file value wins over default                            #
# --------------------------------------------------------------------------- #


def test_check_story_doc_version_config_file_window_takes_precedence_over_default(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    story_path = _write_story_doc_with_inline_marker(
        tmp_path, version_token="5.8"
    )
    _write_config_file(tmp_path, tolerance_window=4)
    request = VersionCheckRequest(
        story_doc_path=story_path,
        project_root=tmp_path,
    )
    outcome, _ = check_story_doc_version(
        request,
        run_state=_make_run_state(),
        marker_registry=runtime_marker_registry,
    )
    assert outcome.tolerance_window == 4
    # delta = 4, window = 4 → silent.
    assert outcome.action == "proceed-silent"


# --------------------------------------------------------------------------- #
# AC-7 case 13: default window when config file absent                         #
# --------------------------------------------------------------------------- #


def test_check_story_doc_version_default_window_when_config_file_absent(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    story_path = _write_story_doc_with_inline_marker(
        tmp_path, version_token="6.2"
    )
    # No config file written.
    request = VersionCheckRequest(
        story_doc_path=story_path,
        project_root=tmp_path,
    )
    outcome, _ = check_story_doc_version(
        request,
        run_state=_make_run_state(),
        marker_registry=runtime_marker_registry,
    )
    assert outcome.tolerance_window == 2
    assert outcome.action == "proceed-silent"


# --------------------------------------------------------------------------- #
# AC-7 case 14: raises when config window is non-integer                       #
# --------------------------------------------------------------------------- #


def test_check_story_doc_version_raises_when_config_window_is_non_integer(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    story_path = _write_story_doc_with_inline_marker(
        tmp_path, version_token="6.2"
    )
    _write_config_file(tmp_path, tolerance_window="two")
    request = VersionCheckRequest(
        story_doc_path=story_path,
        project_root=tmp_path,
    )
    with pytest.raises(StoryDocVersionDetectionError) as exc_info:
        check_story_doc_version(
            request,
            run_state=_make_run_state(),
            marker_registry=runtime_marker_registry,
        )
    assert exc_info.value.reason == "tolerance-window-not-an-integer"


# --------------------------------------------------------------------------- #
# AC-7 case 15: run_state=None returns None and no emission                    #
# --------------------------------------------------------------------------- #


def test_check_story_doc_version_run_state_none_returns_none_and_no_emission(
    tmp_path: pathlib.Path,
) -> None:
    story_path = _write_story_doc_with_inline_marker(
        tmp_path, version_token="5.9"
    )
    request = VersionCheckRequest(
        story_doc_path=story_path,
        project_root=tmp_path,
        tolerance_window=2,
    )
    with mock.patch.object(
        story_doc_version_check, "record_marker_with_context"
    ) as emit_mock:
        outcome, next_rs = check_story_doc_version(
            request, run_state=None, marker_registry=None
        )
    assert outcome.action == "proceed-with-marker"
    assert next_rs is None
    emit_mock.assert_not_called()


# --------------------------------------------------------------------------- #
# AC-7 case 16: load_upgrade_guidance returns version-specific section         #
# --------------------------------------------------------------------------- #


def test_load_upgrade_guidance_returns_version_specific_section_when_present(
    tmp_path: pathlib.Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    doc_body = textwrap.dedent(
        """\
        # Story-doc upgrade guidance

        ## What this doc is

        Intro paragraph.

        ## Upgrading from version 6.0

        Steps for 6.0 upgrade.

        ## Upgrading from version 6.1

        Steps for 6.1.

        ## Older versions (catch-all)

        Catch-all body.
        """
    )
    (docs_dir / "story-doc-upgrade-guidance.md").write_text(
        doc_body, encoding="utf-8"
    )
    body = load_upgrade_guidance("6.0", repo_root=tmp_path)
    assert "Upgrading from version 6.0" in body
    assert "Steps for 6.0 upgrade" in body
    # The next section must NOT be included.
    assert "Steps for 6.1" not in body


# --------------------------------------------------------------------------- #
# AC-7 case 17: load_upgrade_guidance falls back to catch-all                  #
# --------------------------------------------------------------------------- #


def test_load_upgrade_guidance_falls_back_to_catch_all_for_unmapped_version(
    tmp_path: pathlib.Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    doc_body = textwrap.dedent(
        """\
        # Story-doc upgrade guidance

        ## Older versions (catch-all)

        Catch-all body.
        """
    )
    (docs_dir / "story-doc-upgrade-guidance.md").write_text(
        doc_body, encoding="utf-8"
    )
    body = load_upgrade_guidance("5.4", repo_root=tmp_path)
    assert "Older versions" in body
    assert "Catch-all body" in body


# --------------------------------------------------------------------------- #
# AC-7 case 18: load_upgrade_guidance raises when doc missing                  #
# --------------------------------------------------------------------------- #


def test_load_upgrade_guidance_raises_when_doc_missing(
    tmp_path: pathlib.Path,
) -> None:
    with pytest.raises(StoryDocVersionDetectionError) as exc_info:
        load_upgrade_guidance("5.4", repo_root=tmp_path)
    assert exc_info.value.reason == "upgrade-guidance-content-missing"


# --------------------------------------------------------------------------- #
# AC-7 case 19: load_upgrade_guidance raises when neither section present      #
# --------------------------------------------------------------------------- #


def test_load_upgrade_guidance_raises_when_neither_section_present(
    tmp_path: pathlib.Path,
) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    doc_body = textwrap.dedent(
        """\
        # Story-doc upgrade guidance

        ## What this doc is

        Just an intro.

        ## Detecting the in-use version

        Some content.
        """
    )
    (docs_dir / "story-doc-upgrade-guidance.md").write_text(
        doc_body, encoding="utf-8"
    )
    with pytest.raises(StoryDocVersionDetectionError) as exc_info:
        load_upgrade_guidance("6.0", repo_root=tmp_path)
    assert exc_info.value.reason == "upgrade-guidance-content-missing"


# --------------------------------------------------------------------------- #
# AC-7 case 20: contract-pair end-to-end (single test against PROD doc)        #
# --------------------------------------------------------------------------- #


def test_contract_pair_end_to_end_single_test(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
    prod_repo_root: pathlib.Path,
) -> None:
    """Per ``epics.md:3101``: load fixture story doc with
    ``<!-- bmm-template-version: 5.9 -->`` (out-of-window for
    supported=6.2, window=2); call check_story_doc_version; assert all
    six halves of the contract pair fire AND
    load_upgrade_guidance("5.9", PROD_REPO_ROOT) returns non-empty
    content.

    Runs against the PRODUCTION
    ``bmad-autopilot/docs/story-doc-upgrade-guidance.md`` — NOT a
    ``tmp_path`` fixture — to enforce the contract-pair shipping
    discipline structurally.
    """
    story_path = _write_story_doc_with_inline_marker(
        tmp_path, version_token="5.9"
    )
    request = VersionCheckRequest(
        story_doc_path=story_path,
        project_root=tmp_path,
        tolerance_window=2,
    )
    rs = _make_run_state()
    with mock.patch.object(
        story_doc_version_check,
        "record_marker_with_context",
        wraps=story_doc_version_check.record_marker_with_context,
    ) as emit_spy:
        outcome, next_rs = check_story_doc_version(
            request, run_state=rs, marker_registry=runtime_marker_registry
        )
    # (a) detection function fires.
    assert outcome.detected_version == "5.9"
    # (b) action is proceed-with-marker.
    assert outcome.action == "proceed-with-marker"
    # (c) record_marker_with_context called exactly once with the
    # canonical marker class.
    assert emit_spy.call_count == 1
    assert (
        emit_spy.call_args.kwargs["marker_class"]
        == STORY_DOC_VERSION_OUT_OF_WINDOW_MARKER_CLASS
    )
    # (d) marker context's upgrade_guidance_path is the absolute path
    # of the PRODUCTION upgrade-guidance doc.
    assert next_rs is not None
    payload = next_rs.marker_contexts[
        STORY_DOC_VERSION_OUT_OF_WINDOW_MARKER_CLASS
    ]
    expected_doc = (
        prod_repo_root / "docs" / "story-doc-upgrade-guidance.md"
    )
    assert payload["upgrade_guidance_path"] == str(expected_doc)
    # (e) load_upgrade_guidance against the production repo-root
    # returns non-empty content for "5.9".
    guidance = load_upgrade_guidance("5.9", repo_root=prod_repo_root)
    assert guidance.strip()
    # (f) since the production doc carries no version-specific section
    # for 5.9 at story-7.7's landing, the catch-all must be returned.
    assert "Older versions" in guidance


# --------------------------------------------------------------------------- #
# AC-7 case 21: version-tolerance fixture sweep N-0..N-4                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "detected_version,expected_action",
    [
        ("6.2", "proceed-silent"),  # N-0
        ("6.1", "proceed-silent"),  # N-1
        ("6.0", "proceed-silent"),  # N-2 (boundary)
        ("5.9", "proceed-with-marker"),  # N-3
        ("5.8", "proceed-with-marker"),  # N-4
    ],
)
def test_version_tolerance_fixture_sweep_n0_through_n4(
    tmp_path: pathlib.Path,
    runtime_marker_registry: MarkerClassRegistry,
    detected_version: str,
    expected_action: str,
) -> None:
    story_path = _write_story_doc_with_inline_marker(
        tmp_path,
        version_token=detected_version,
        filename=f"story-{detected_version.replace('.', '-')}.md",
    )
    request = VersionCheckRequest(
        story_doc_path=story_path,
        project_root=tmp_path,
        tolerance_window=2,
    )
    with mock.patch.object(
        story_doc_version_check,
        "record_marker_with_context",
        wraps=story_doc_version_check.record_marker_with_context,
    ) as emit_spy:
        outcome, _ = check_story_doc_version(
            request,
            run_state=_make_run_state(),
            marker_registry=runtime_marker_registry,
        )
    assert outcome.action == expected_action
    if expected_action == "proceed-silent":
        emit_spy.assert_not_called()
    else:
        assert emit_spy.call_count == 1


# --------------------------------------------------------------------------- #
# AC-7 case 22: pluggability gate posture                                      #
# --------------------------------------------------------------------------- #


def test_pluggability_gate_does_not_flag_consumers() -> None:
    """Substrate-library posture verification.

    Story 1.10a's pluggability gate enforces "no cross-references
    between specialists." ``story_doc_version_check`` is shared
    substrate (sibling of ``_shared``, ``story_doc_validator``,
    ``marker_wiring``), so specialists may import it without
    violating the gate.

    This test asserts the structural classification: the module
    lives under ``loud_fail_harness/`` (NOT under any ``agents/``
    or ``specialists/`` subtree) AND it does NOT itself import any
    specialist-specific module. Manual verification of the gate
    output is documented in Completion Notes per Story 1.10a's CI
    gate output convention.
    """
    module_path = pathlib.Path(story_doc_version_check.__file__).resolve()
    # Module lives under src/loud_fail_harness/.
    assert "loud_fail_harness" in module_path.parts
    # No specialist imports.
    text = module_path.read_text(encoding="utf-8")
    forbidden_specialist_imports = [
        "from loud_fail_harness.qa_",
        "from loud_fail_harness.dev_",
        "from loud_fail_harness.review_bmad",
    ]
    for needle in forbidden_specialist_imports:
        assert needle not in text, (
            f"story_doc_version_check imports a specialist module: {needle!r}"
        )
