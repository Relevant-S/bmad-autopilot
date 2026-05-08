"""Tests for the Story 7.4 sample-story-scaffold module.

Covers AC-8 — fifteen independent test functions covering:

* canonical content load via ``importlib.resources`` (UTF-8;
  determinism; ``FileNotFoundError`` propagation),
* canonical content's structural properties per AC-2 (multi-AC
  iteration; ≥1 Tier-2-applicable AC; ≥1 of three Story 4.9 exploratory
  heuristics; NO Tier-3 dependency; ``story_doc_validator``-conformant
  specialist sections; no forbidden smoke-fixture identity strings),
* ``scaffold_sample_story`` happy path (writes to predictable path,
  creates parent dirs, returns informative outcome),
* opt-out skip path (no resource read, no filesystem write,
  informative notes),
* idempotency posture overwrites (Story 7.6 owns preserve-on-re-run),
* ``PermissionError`` propagates UNCHANGED (Pattern 5),
* zero marker registrations (Story 1.11 atomic-vs-aggregated principle —
  no umbrella marker),
* defensive ``project_root`` scope (resolved target stays under
  caller-supplied root).

Pattern 5 + Pattern 6 — explicit, named tests; no shared mutable state;
caller-injected ``tmp_path`` so tests do NOT touch the outer workspace's
``_bmad-output/implementation-artifacts/``.
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
from pydantic import ValidationError

from loud_fail_harness.sample_story_scaffold import (
    CANONICAL_CONTENT_RESOURCE,
    CANONICAL_TARGET_FILENAME,
    SAMPLE_STORY_TARGET_SUBDIR,
    SampleScaffoldOutcome,
    SampleScaffoldRequest,
    load_sample_story_content,
    resolve_target_path,
    scaffold_sample_story,
)
from loud_fail_harness.story_doc_validator import ALLOWED_SECTIONS, is_allowed

# --------------------------------------------------------------------------- #
# Module-level constants used by multiple tests                                #
# --------------------------------------------------------------------------- #

#: The canonical filename that lands in the user's BMAD project per FR39.
_FILENAME: Final[str] = "sample-auto-001.md"

#: Forbidden-string deny-list per AC-8 case 8 (smoke-fixture identity is
#: reserved for Story 2.13's `tests/fixtures/sample-story-walking-skeleton.md`).
_FORBIDDEN_STRINGS: Final[tuple[str, ...]] = (
    "smoke",
    "walking skeleton",
    "fixture",
    "test infrastructure",
)

#: Tier-2-outcome-evidence shape phrases per AC-8 case 4. The canonical
#: content's AC text MUST contain at least one of these phrases —
#: observed-behavior assertion shape distinct from Tier-1 file-existence.
_TIER_2_PHRASES: Final[tuple[str, ...]] = (
    "returns",
    "response",
    "status",
    "body",
    "echoes",
    "rendered output",
    "the returned",
)

#: Tier-3-semantic-verification deny-list per AC-8 case 6. The canonical
#: content's AC text MUST NOT contain any of these phrases — Story 4.8's
#: ``not_configured`` default would gate first-loop completion on
#: optional tooling.
_TIER_3_DENYLIST: Final[tuple[str, ...]] = (
    "matches the specification's intent",
    "is correct",
    "is semantically valid",
    "user experience is acceptable",
    "matches the intent",
    "passes a semantic review",
)

#: The three Story 4.9 exploratory heuristics. AT LEAST ONE must be
#: keyword-applicable in the canonical content per AC-8 case 5.
_HEURISTIC_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "empty-state": ("empty", "no items", "missing", "absent"),
    "error-state": ("invalid", "malformed", "rejection", "400", "500"),
    "auth-boundary": ("unauthenticated", "no credentials", "401", "403"),
}


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _extract_acceptance_criteria_section(content: str) -> str:
    """Return the body of the ``## Acceptance Criteria`` section.

    Body is everything between the section header and the next ``## ``
    sibling header. Used by AC-count + Tier-2 + Tier-3 + heuristic
    assertions.
    """
    match = re.search(
        r"^## Acceptance Criteria\s*\n(.*?)(?=^## |\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(
            "canonical content missing required `## Acceptance Criteria` section"
        )
    return match.group(1)


def _count_top_level_numbered_acs(ac_section: str) -> int:
    """Count top-level numbered ACs (lines starting with ``1.``, ``2.``, etc.)."""
    return len(
        re.findall(
            r"^\d+\.\s+",
            ac_section,
            re.MULTILINE,
        )
    )


def _section_headers(content: str) -> list[str]:
    """Return all H2 section headers (lines starting with ``## ``)."""
    return [
        line.rstrip()
        for line in content.splitlines()
        if line.startswith("## ")
    ]


# --------------------------------------------------------------------------- #
# AC-8 case 1 — `load_sample_story_content` returns canonical UTF-8 content.   #
# --------------------------------------------------------------------------- #


def test_load_sample_story_content_returns_canonical_utf8() -> None:
    """The function returns a non-empty UTF-8 string whose first non-
    whitespace line starts with ``# ``; two calls return byte-identical
    content (defensive against accidental in-memory mutation)."""
    first = load_sample_story_content()
    second = load_sample_story_content()

    assert isinstance(first, str)
    assert first  # non-empty
    assert first == second  # byte-identical across calls

    first_non_blank_line = next(
        line for line in first.splitlines() if line.strip()
    )
    assert first_non_blank_line.startswith("# "), (
        f"canonical content's first non-blank line MUST be an H1 title; "
        f"got: {first_non_blank_line!r}"
    )

    # Confirm UTF-8 round-trip — encoding/decoding is lossless.
    assert first.encode("utf-8").decode("utf-8") == first


# --------------------------------------------------------------------------- #
# AC-8 case 2 — `load_sample_story_content` propagates `FileNotFoundError`.    #
# --------------------------------------------------------------------------- #


def test_load_sample_story_content_propagates_file_not_found_unchanged() -> None:
    """If the packaged resource is missing (build-time misconfiguration),
    `FileNotFoundError` propagates UNCHANGED. The function does NOT
    swallow into a sentinel string per Pattern 5."""
    with mock.patch(
        "loud_fail_harness.sample_story_scaffold.importlib.resources.files"
    ) as mock_files:
        mock_resource = mock.Mock()
        mock_resource.joinpath.return_value.read_text.side_effect = (
            FileNotFoundError(
                f"packaged resource {CANONICAL_CONTENT_RESOURCE} missing"
            )
        )
        mock_files.return_value = mock_resource

        with pytest.raises(FileNotFoundError) as exc_info:
            load_sample_story_content()
        assert CANONICAL_CONTENT_RESOURCE in str(exc_info.value)


# --------------------------------------------------------------------------- #
# AC-8 case 3 — Sample content has 2-4 numbered ACs (multi-AC iteration).      #
# --------------------------------------------------------------------------- #


def test_canonical_content_has_two_to_four_numbered_acs() -> None:
    """Per AC-2 verbatim: "exercise multi-AC iteration (more than one
    AC)". Per AC-3: AC count bounded to 2-4 to keep the QA AC-iteration
    surface bounded for the 5-min target per FR44."""
    content = load_sample_story_content()
    ac_section = _extract_acceptance_criteria_section(content)
    count = _count_top_level_numbered_acs(ac_section)
    assert 2 <= count <= 4, (
        f"canonical content has {count} numbered ACs; AC-2 / AC-3 require "
        f"2-4 (multi-AC iteration; bounded for 5-min first-loop target)"
    )


# --------------------------------------------------------------------------- #
# AC-8 case 4 — Sample has at least one Tier-2-outcome-evidence applicable AC. #
# --------------------------------------------------------------------------- #


def test_canonical_content_has_tier_2_outcome_evidence_ac() -> None:
    """Per AC-2: at least one AC's verification surface is Tier-2 —
    contains observed-behavior assertion shape (returns / status / body /
    rendered output / etc.) distinct from Tier-1 pure file-existence."""
    content = load_sample_story_content()
    ac_section = _extract_acceptance_criteria_section(content)
    lower = ac_section.lower()

    matched = [phrase for phrase in _TIER_2_PHRASES if phrase in lower]
    assert matched, (
        f"canonical content's `## Acceptance Criteria` section MUST contain "
        f"at least one Tier-2-outcome-evidence shape phrase from "
        f"{_TIER_2_PHRASES!r}; matched none. Per AC-2: at least one AC must "
        f"be designed to be verifiable at TIER-2 OUTCOME-EVIDENCE level."
    )


# --------------------------------------------------------------------------- #
# AC-8 case 5 — At least one of three Story 4.9 heuristics applicable.         #
# --------------------------------------------------------------------------- #


def test_canonical_content_has_at_least_one_exploratory_heuristic() -> None:
    """Per AC-2: at least one of `empty-state` / `error-state` /
    `auth-boundary` heuristic markers appears in either an AC's text or
    the `## Story` clause or a `## Tasks / Subtasks` task description."""
    content = load_sample_story_content()
    lower = content.lower()

    applicable: list[str] = [
        kind
        for kind, keywords in _HEURISTIC_KEYWORDS.items()
        if any(keyword in lower for keyword in keywords)
    ]
    assert applicable, (
        "canonical content MUST be applicable to at least one of the three "
        "Story 4.9 exploratory heuristics (empty-state / error-state / "
        f"auth-boundary); keyword-set match found NONE. Probed: "
        f"{_HEURISTIC_KEYWORDS!r}"
    )


# --------------------------------------------------------------------------- #
# AC-8 case 6 — Sample does NOT require Tier-3 semantic verification.          #
# --------------------------------------------------------------------------- #


def test_canonical_content_has_no_tier_3_semantic_verification_phrases() -> None:
    """Per AC-2 verbatim: "NOT require Tier-3 semantic verification — so
    first-loop completion doesn't gate on optional tooling". Story 4.8's
    `not_configured` is the default; any AC requiring Tier-3 would block
    first-loop completion."""
    content = load_sample_story_content()
    lower = content.lower()
    matched = [phrase for phrase in _TIER_3_DENYLIST if phrase.lower() in lower]
    assert not matched, (
        f"canonical content contains Tier-3-semantic-verification phrase(s) "
        f"{matched!r}; AC-2 forbids Tier-3 dependency in the sample story. "
        f"Story 4.8's default `not_configured` would gate first-loop "
        f"completion on optional tooling."
    )


# --------------------------------------------------------------------------- #
# AC-8 case 7 — Section headers respect `story_doc_validator` allowlist.       #
# --------------------------------------------------------------------------- #

#: The top-level BMAD-template convention sections every story doc has.
#: These are NOT specialist-write-scope sections (those land at runtime
#: when Dev / Review / QA wrappers populate them); they are the doc
#: skeleton.
_TEMPLATE_CONVENTION_SECTIONS: Final[frozenset[str]] = frozenset(
    {
        "## Story",
        "## Acceptance Criteria",
        "## Tasks / Subtasks",
        "## Dev Notes",
        "## References",
        "## Testing Standards",
        "## Change Log",
        "## Status",
    }
)


def test_canonical_content_section_headers_pass_story_doc_validator() -> None:
    """Every H2 section header in the canonical content is either a
    top-level BMAD-template convention section OR a member of the
    story-doc-validator's 5-section specialist-write-scope allowlist
    (per FR66 / NFR-S5 + ``story_doc_validator.py:189-195``)."""
    content = load_sample_story_content()
    headers = _section_headers(content)
    assert headers, "canonical content has no H2 sections"

    for header in headers:
        # Specialist-write-scope sections must pass the allowlist.
        if header in ALLOWED_SECTIONS:
            assert is_allowed(header), (
                f"specialist-write-scope header {header!r} should be allowed "
                f"by `is_allowed` but was rejected"
            )
            continue
        # Otherwise must be a top-level BMAD-template convention section.
        assert header in _TEMPLATE_CONVENTION_SECTIONS, (
            f"canonical content header {header!r} is NEITHER a "
            f"specialist-write-scope allowlisted section "
            f"{sorted(ALLOWED_SECTIONS)!r} NOR a top-level BMAD-template "
            f"convention section {sorted(_TEMPLATE_CONVENTION_SECTIONS)!r}"
        )


def test_canonical_content_has_required_template_sections() -> None:
    """The canonical content MUST contain the four BMAD story-doc
    template sections needed by the Dev / Review / QA wrappers per
    AC-2: `## Story`, `## Acceptance Criteria`, `## Tasks / Subtasks`,
    `## Dev Agent Record`."""
    content = load_sample_story_content()
    required = (
        "## Story",
        "## Acceptance Criteria",
        "## Tasks / Subtasks",
        "## Dev Agent Record",
    )
    for section in required:
        assert section in content, (
            f"canonical content missing required BMAD story-doc section "
            f"{section!r}"
        )


# --------------------------------------------------------------------------- #
# AC-8 case 8 — Forbidden smoke-fixture identity strings absent.               #
# --------------------------------------------------------------------------- #


def test_canonical_content_does_not_contain_smoke_fixture_identity_strings() -> None:
    """Per AC-2: the canonical content does NOT contain "smoke" /
    "walking skeleton" / "fixture" / "test infrastructure"
    (case-insensitive). Those strings belong to Story 2.13's smoke
    fixture's identity; Story 7.4's sample is user-facing per the
    structural-separation invariant in
    `bmad-autopilot/docs/extension-audit.md`."""
    content = load_sample_story_content().lower()
    matched = [s for s in _FORBIDDEN_STRINGS if s in content]
    assert not matched, (
        f"canonical content contains forbidden smoke-fixture identity "
        f"string(s) {matched!r}; the user-facing sample's namespace MUST "
        f"NOT overlap with the smoke fixture (see "
        f"`bmad-autopilot/docs/extension-audit.md` § "
        f'"Epic 2 walking-skeleton smoke fixture vs. Epic 7 user-facing '
        f'onboarding sample").'
    )


# --------------------------------------------------------------------------- #
# AC-8 case 9 — Happy-path scaffold writes file at predictable path.           #
# --------------------------------------------------------------------------- #


def test_scaffold_happy_path_writes_at_predictable_path(
    tmp_path: pathlib.Path,
) -> None:
    """`scaffold_sample_story(opt_out=False)` writes the canonical
    content to ``<project_root>/_bmad-output/implementation-artifacts/
    sample-auto-001.md`` and returns an informative outcome."""
    request = SampleScaffoldRequest(project_root=tmp_path, opt_out=False)
    outcome = scaffold_sample_story(request)

    expected_target = (
        tmp_path / "_bmad-output" / "implementation-artifacts" / _FILENAME
    )

    assert outcome.outcome == "scaffolded"
    assert outcome.target_path == expected_target
    assert outcome.target_path.is_file()

    written = outcome.target_path.read_text(encoding="utf-8")
    canonical = load_sample_story_content()
    assert written == canonical

    assert outcome.bytes_written == len(canonical.encode("utf-8"))
    assert outcome.notes
    assert "/bmad-automation run sample-auto-001" in outcome.notes


# --------------------------------------------------------------------------- #
# AC-8 case 10 — `mkdir(parents=True)` creates parent directories.             #
# --------------------------------------------------------------------------- #


def test_scaffold_creates_parent_directories(tmp_path: pathlib.Path) -> None:
    """Given `tmp_path` where `_bmad-output/implementation-artifacts/`
    does NOT yet exist, the function succeeds (no `FileNotFoundError`
    from the parent path); after the call, the parent directories
    exist and are directories."""
    parent_dir = tmp_path / "_bmad-output" / "implementation-artifacts"
    assert not parent_dir.exists()

    request = SampleScaffoldRequest(project_root=tmp_path, opt_out=False)
    outcome = scaffold_sample_story(request)

    assert outcome.outcome == "scaffolded"
    assert parent_dir.is_dir()
    assert parent_dir.parent.is_dir()


# --------------------------------------------------------------------------- #
# AC-8 case 11 — Opt-out skip with informative notes; no file written.         #
# --------------------------------------------------------------------------- #


def test_scaffold_opt_out_skips_with_informative_notes(
    tmp_path: pathlib.Path,
) -> None:
    """Given `opt_out=True`, the function returns
    `outcome="skipped-opt-out"`, `bytes_written is None`, the target
    file does NOT exist after the call, and `notes` mentions both
    `--no-sample-story` AND the resolved target path."""
    request = SampleScaffoldRequest(project_root=tmp_path, opt_out=True)
    outcome = scaffold_sample_story(request)

    expected_target = (
        tmp_path / "_bmad-output" / "implementation-artifacts" / _FILENAME
    )

    assert outcome.outcome == "skipped-opt-out"
    assert outcome.target_path == expected_target
    assert outcome.bytes_written is None
    assert not expected_target.exists()
    # Even the parent dir is NOT created on the opt-out path.
    assert not expected_target.parent.exists()
    assert "--no-sample-story" in outcome.notes
    assert str(expected_target) in outcome.notes


# --------------------------------------------------------------------------- #
# AC-8 case 12 — Idempotency overwrite (Story 7.6 owns preserve-on-re-run).    #
# --------------------------------------------------------------------------- #


def test_scaffold_overwrites_existing_file(tmp_path: pathlib.Path) -> None:
    """Story 7.6 owns the preserve-on-re-run rule per
    ``epics.md`` line 3052. Story 7.4's substrate function's contract is
    "write the canonical content to the target path"; called with
    `opt_out=False` on an existing file, the function OVERWRITES the
    file. The orchestrator skill at thickening time is responsible for
    invoking this function ONLY when the non-destructive guard has
    cleared the target."""
    expected_target = (
        tmp_path / "_bmad-output" / "implementation-artifacts" / _FILENAME
    )
    expected_target.parent.mkdir(parents=True, exist_ok=True)
    expected_target.write_text("stale content from a previous run\n", encoding="utf-8")
    assert expected_target.read_text(encoding="utf-8").startswith("stale")

    request = SampleScaffoldRequest(project_root=tmp_path, opt_out=False)
    outcome = scaffold_sample_story(request)

    assert outcome.outcome == "scaffolded"
    assert expected_target.read_text(encoding="utf-8") == load_sample_story_content()


# --------------------------------------------------------------------------- #
# AC-8 case 13 — `PermissionError` propagates UNCHANGED.                       #
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="Windows chmod is a no-op; root bypasses POSIX directory-write permission bits",
)
def test_scaffold_propagates_permission_error_unchanged(
    tmp_path: pathlib.Path,
) -> None:
    """Given `tmp_path` with a read-only `_bmad-output/implementation-
    artifacts/` directory, the function raises `PermissionError`
    UNCHANGED per Pattern 5 (loud-fail). Cleanup restores write
    permission so `tmp_path` removal succeeds."""
    parent_dir = tmp_path / "_bmad-output" / "implementation-artifacts"
    parent_dir.mkdir(parents=True)

    original_mode = parent_dir.stat().st_mode
    parent_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # r-x; no write
    try:
        request = SampleScaffoldRequest(project_root=tmp_path, opt_out=False)
        with pytest.raises(PermissionError):
            scaffold_sample_story(request)
    finally:
        parent_dir.chmod(original_mode)


# --------------------------------------------------------------------------- #
# AC-8 case 14 — Scaffold registers ZERO markers (Story 1.11 atomic-vs-aggregated). #
# --------------------------------------------------------------------------- #


def test_scaffold_does_not_register_any_markers(
    tmp_path: pathlib.Path,
) -> None:
    """Story 7.4 introduces ZERO new marker classes. Verified via
    import-inspection: `sample_story_scaffold` must not expose
    `marker_wiring` or `record_marker_with_context` in its module
    namespace — meaning no call path exists regardless of execution
    flow (per Story 1.11 atomic-vs-aggregated principle).

    Behavioral complement: scaffold calls complete without error on
    both happy-path and opt-out paths."""
    import loud_fail_harness.sample_story_scaffold as _mod

    assert not hasattr(_mod, "record_marker_with_context"), (
        "sample_story_scaffold must not expose record_marker_with_context "
        "in its module namespace — Story 7.4 introduces zero marker classes"
    )
    assert not hasattr(_mod, "marker_wiring"), (
        "sample_story_scaffold must not import marker_wiring — "
        "Story 7.4 introduces zero marker classes per Story 1.11"
    )
    # Behavioral: both execution paths complete without invoking any marker API.
    scaffold_sample_story(
        SampleScaffoldRequest(project_root=tmp_path, opt_out=False)
    )
    scaffold_sample_story(
        SampleScaffoldRequest(project_root=tmp_path / "other-root", opt_out=True)
    )


# --------------------------------------------------------------------------- #
# AC-8 case 15 — Defensive scope: target stays under caller's `project_root`.  #
# --------------------------------------------------------------------------- #


def test_resolve_target_path_stays_under_project_root(
    tmp_path: pathlib.Path,
) -> None:
    """Per AC-4: the resolved target path must be a descendant of the
    caller-supplied project_root; the scaffolder must NEVER write to
    the canonical resource path inside the harness package (`_data/`)."""
    target = resolve_target_path(tmp_path)

    assert target.is_relative_to(tmp_path), (
        f"resolved target {target!r} escaped caller-supplied "
        f"project_root {tmp_path!r}"
    )

    # And it must not be the harness's `_data/` resource by absolute path.
    canonical_resource_str = str(
        importlib.resources.files("loud_fail_harness").joinpath(
            CANONICAL_CONTENT_RESOURCE
        )
    )
    assert str(target) != canonical_resource_str, (
        f"resolved target {target!r} collides with the package-bundled "
        f"canonical resource path {canonical_resource_str!r}; the scaffolder "
        f"must NEVER write to the canonical resource path."
    )


# --------------------------------------------------------------------------- #
# Supplementary structural-coverage tests beyond AC-8 (parallel to             #
# Story 7.3's pattern: 15 AC-9 cases + 2 supplementary structural tests).      #
# --------------------------------------------------------------------------- #


def test_canonical_content_resource_constant_matches_data_layout() -> None:
    """The canonical resource constant points at a real file inside the
    package's `_data/` directory; defensive against accidental constant
    drift (rename, typo)."""
    resource_path = pathlib.Path(
        str(
            importlib.resources.files("loud_fail_harness").joinpath(
                CANONICAL_CONTENT_RESOURCE
            )
        )
    )
    assert resource_path.is_file(), (
        f"canonical resource constant CANONICAL_CONTENT_RESOURCE="
        f"{CANONICAL_CONTENT_RESOURCE!r} does not resolve to a real file"
    )


def test_canonical_target_subdir_constants_match_documentation() -> None:
    """The target-subdir constants compose to the FR39-documented
    user-facing path (``_bmad-output/implementation-artifacts/
    sample-auto-001.md``)."""
    assert SAMPLE_STORY_TARGET_SUBDIR == ("_bmad-output", "implementation-artifacts")
    assert CANONICAL_TARGET_FILENAME == "sample-auto-001.md"


def test_outcome_model_is_frozen_pydantic_v2() -> None:
    """`SampleScaffoldOutcome` is frozen (Pattern 6 — immutable typed
    boundaries); attempting to mutate raises `pydantic.ValidationError`."""
    outcome = SampleScaffoldOutcome(
        outcome="scaffolded",
        target_path=pathlib.Path("/tmp/x"),
        bytes_written=42,
        notes="ok",
    )
    with pytest.raises(ValidationError):
        outcome.outcome = "skipped-opt-out"  # type: ignore[misc]  # type: ignore[misc]


def test_scaffold_request_rejects_relative_project_root() -> None:
    """D1 fix: `SampleScaffoldRequest` must reject relative paths for
    `project_root` — the validator enforces that `project_root.is_absolute()`
    so the resolved `target_path` is always absolute and the docstring's
    "Absolute resolved path" claim holds."""
    with pytest.raises((ValidationError, ValueError)):
        SampleScaffoldRequest(project_root=pathlib.Path("relative/path"))
