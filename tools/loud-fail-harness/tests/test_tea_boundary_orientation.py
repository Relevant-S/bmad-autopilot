"""Tests for the Story 7.8 TEA-boundary first-run orientation substrate
module.

Covers AC-8 — 28 test cases covering:

* doc-extraction (cases 1-7),
* emit-tracking-config-read (cases 8-13),
* config-write — present-field replace + absent-field append (cases 14-18),
* the pure-decision evaluator (cases 19-20),
* the production emitter that composes evaluator + writer (cases 21-22),
* the SINGLE end-to-end contract-pair test against the PRODUCTION doc
  (case 23),
* the AC-5 template addition + name-matches-constant invariants
  (cases 24-25),
* the section-heading constant byte-equivalence (case 26),
* the AC-5 cross-story integration with Story 7.6's additive merge
  (case 27),
* the pluggability-gate posture (case 28).

Pattern 5 + Pattern 6 — explicit, named tests; no shared mutable
state; caller-injected ``tmp_path`` so unit tests do NOT touch the
outer workspace's ``_bmad/`` or ``docs/``.
"""

from __future__ import annotations

import os
import pathlib
import textwrap
from unittest import mock

import pytest
import yaml as _pyyaml

from loud_fail_harness import _shared, tea_boundary_orientation
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.config_qa_runbook_stub import (
    StubScaffoldRequest,
    load_config_template,
    resolve_config_path,
    scaffold_config_qa_runbook_stubs,
)
from loud_fail_harness.init_non_destructive_guard import additively_merge_config
from loud_fail_harness.tea_boundary_orientation import (
    EMIT_TRACKING_FIELD,
    ORIENTATION_SECTION_HEADING,
    OrientationConfigError,
    OrientationOutcome,
    OrientationRequest,
    emit_orientation_if_first_run,
    evaluate_orientation_emission,
    extract_orientation_message,
    read_emit_tracking_field,
    write_emit_tracking_field,
)


# --------------------------------------------------------------------------- #
# Fixtures + helpers                                                           #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def prod_repo_root() -> pathlib.Path:
    return find_repo_root()


_CANONICAL_BODY = textwrap.dedent(
    """\
    > ✅ TEA detected. Quick note: **TEA validates your test suite** (runs your tests, assesses coverage). **The Automator exercises your running product** (drives the UI/API against AC, produces behavioral evidence). Both run per story; they don't overlap. Full boundary in `docs/tea-vs-automator.md`.
    """
).strip()


def _write_doc_outer_layout(
    tmp_path: pathlib.Path, *, body: str = _CANONICAL_BODY
) -> pathlib.Path:
    """Materialize a fixture doc at
    ``tmp_path/bmad-autopilot/docs/tea-vs-automator.md`` with the given
    body under ``## First-Run Orientation Message``.
    """
    doc_dir = tmp_path / "bmad-autopilot" / "docs"
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / "tea-vs-automator.md"
    doc_path.write_text(
        "# TEA vs. Automator boundary\n"
        "\n"
        "Some preface content.\n"
        "\n"
        "## First-Run Orientation Message\n"
        "\n"
        f"{body}\n"
        "\n"
        "## Notes for contributors editing this section\n"
        "\n"
        "More content.\n",
        encoding="utf-8",
    )
    return doc_path


def _write_doc_inner_layout(
    tmp_path: pathlib.Path, *, body: str = _CANONICAL_BODY
) -> pathlib.Path:
    """Materialize a fixture doc at ``tmp_path/docs/tea-vs-automator.md``."""
    doc_dir = tmp_path / "docs"
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / "tea-vs-automator.md"
    doc_path.write_text(
        "# TEA vs. Automator boundary\n"
        "\n"
        "## First-Run Orientation Message\n"
        "\n"
        f"{body}\n"
        "\n"
        "## Other section\n"
        "\n"
        "Trailing.\n",
        encoding="utf-8",
    )
    return doc_path


def _write_config(
    tmp_path: pathlib.Path,
    *,
    body: str | None = None,
    field_value: str | None = "false",
) -> pathlib.Path:
    """Write a config.yaml at ``tmp_path/_bmad/automation/config.yaml``.

    When ``body`` is given, it is written verbatim. Otherwise a minimal
    canonical-shaped config is composed using ``field_value`` for the
    emit-tracking field (``None`` omits the field entirely).
    """
    config_dir = tmp_path / "_bmad" / "automation"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    if body is not None:
        config_path.write_text(body, encoding="utf-8")
        return config_path
    parts = [
        "# Existing comment header.\n",
        "retry_budget: 2\n",
        "specialist_timeout_minutes: 15\n",
    ]
    if field_value is not None:
        parts.append("\n# user-edited comment about the field\n")
        parts.append(f"{EMIT_TRACKING_FIELD}: {field_value}\n")
    config_path.write_text("".join(parts), encoding="utf-8")
    return config_path


# --------------------------------------------------------------------------- #
# AC-8 cases 1-7 — doc-extraction                                              #
# --------------------------------------------------------------------------- #


def test_extract_orientation_message_returns_section_body(
    tmp_path: pathlib.Path,
) -> None:
    """Case 1 — fixture in outer layout returns body verbatim."""
    _write_doc_outer_layout(tmp_path)
    body = extract_orientation_message(tmp_path)
    assert body == _CANONICAL_BODY
    assert body.startswith("> ")  # blockquote prefix preserved


def test_extract_orientation_message_inner_repo_path_fallback(
    tmp_path: pathlib.Path,
) -> None:
    """Case 2 — fixture in inner layout returns body via fallback path."""
    _write_doc_inner_layout(tmp_path)
    body = extract_orientation_message(tmp_path)
    assert body == _CANONICAL_BODY


def test_extract_orientation_message_raises_when_doc_missing(
    tmp_path: pathlib.Path,
) -> None:
    """Case 3 — neither candidate path exists → doc-missing."""
    with pytest.raises(OrientationConfigError) as exc_info:
        extract_orientation_message(tmp_path)
    assert exc_info.value.reason == "doc-missing"
    assert exc_info.value.repo_root == tmp_path


def test_extract_orientation_message_raises_when_section_heading_missing(
    tmp_path: pathlib.Path,
) -> None:
    """Case 4 — doc exists but lacks the canonical heading."""
    doc_dir = tmp_path / "docs"
    doc_dir.mkdir(parents=True)
    doc_path = doc_dir / "tea-vs-automator.md"
    doc_path.write_text(
        "# TEA vs. Automator\n\n## Some other section\n\nBody.\n",
        encoding="utf-8",
    )
    with pytest.raises(OrientationConfigError) as exc_info:
        extract_orientation_message(tmp_path)
    assert exc_info.value.reason == "section-heading-missing"
    assert exc_info.value.doc_path == doc_path


def test_extract_orientation_message_raises_when_section_body_empty(
    tmp_path: pathlib.Path,
) -> None:
    """Case 5 — heading present but body is pure whitespace."""
    doc_dir = tmp_path / "docs"
    doc_dir.mkdir(parents=True)
    doc_path = doc_dir / "tea-vs-automator.md"
    doc_path.write_text(
        "# TEA\n\n## First-Run Orientation Message\n\n## Next section\n\nBody.\n",
        encoding="utf-8",
    )
    with pytest.raises(OrientationConfigError) as exc_info:
        extract_orientation_message(tmp_path)
    assert exc_info.value.reason == "section-body-empty"


def test_extract_orientation_message_stops_at_next_h2(
    tmp_path: pathlib.Path,
) -> None:
    """Case 6 — body capture stops at next H2 heading."""
    body = "Body line one.\n> Blockquote line."
    _write_doc_outer_layout(tmp_path, body=body)
    extracted = extract_orientation_message(tmp_path)
    assert extracted == body
    assert "Notes for contributors" not in extracted


def test_extract_orientation_message_raises_on_oserror(
    tmp_path: pathlib.Path,
) -> None:
    """Case 7 — OSError on read → doc-missing (TOCTOU-safe)."""
    _write_doc_outer_layout(tmp_path)
    with mock.patch.object(
        pathlib.Path, "read_text", side_effect=OSError("permission denied")
    ):
        with pytest.raises(OrientationConfigError) as exc_info:
            extract_orientation_message(tmp_path)
    assert exc_info.value.reason == "doc-missing"


# --------------------------------------------------------------------------- #
# AC-8 cases 8-13 — emit-tracking-field reader                                 #
# --------------------------------------------------------------------------- #


def test_read_emit_tracking_field_returns_false_when_config_absent(
    tmp_path: pathlib.Path,
) -> None:
    """Case 8 — file absent → False (day-zero posture)."""
    assert read_emit_tracking_field(tmp_path) is False


def test_read_emit_tracking_field_returns_false_when_field_absent_in_existing_config(
    tmp_path: pathlib.Path,
) -> None:
    """Case 9 — file present but field absent → False (pre-7.8 config)."""
    _write_config(tmp_path, field_value=None)
    assert read_emit_tracking_field(tmp_path) is False


def test_read_emit_tracking_field_returns_true_when_field_set(
    tmp_path: pathlib.Path,
) -> None:
    """Case 10 — field set to true → True."""
    _write_config(tmp_path, field_value="true")
    assert read_emit_tracking_field(tmp_path) is True


def test_read_emit_tracking_field_returns_false_when_field_set_to_false(
    tmp_path: pathlib.Path,
) -> None:
    """Case 11 — field set to false → False."""
    _write_config(tmp_path, field_value="false")
    assert read_emit_tracking_field(tmp_path) is False


def test_read_emit_tracking_field_raises_when_field_is_non_boolean(
    tmp_path: pathlib.Path,
) -> None:
    """Case 12 — non-boolean value (e.g., string "yes") → loud-fail."""
    _write_config(tmp_path, field_value='"yes"')
    with pytest.raises(OrientationConfigError) as exc_info:
        read_emit_tracking_field(tmp_path)
    assert exc_info.value.reason == "emit-field-not-boolean"
    assert exc_info.value.project_root == tmp_path


def test_read_emit_tracking_field_raises_when_config_yaml_malformed(
    tmp_path: pathlib.Path,
) -> None:
    """Case 13 — malformed YAML → config-yaml-parse-error."""
    _write_config(
        tmp_path,
        body="this is: : not : valid : yaml :::\n  - broken\n: indent\n",
    )
    with pytest.raises(OrientationConfigError) as exc_info:
        read_emit_tracking_field(tmp_path)
    assert exc_info.value.reason == "config-yaml-parse-error"


# --------------------------------------------------------------------------- #
# AC-8 cases 14-18 — emit-tracking-field writer                                #
# --------------------------------------------------------------------------- #


def test_write_emit_tracking_field_replaces_existing_false_with_true(
    tmp_path: pathlib.Path,
) -> None:
    """Case 14 — replace path: field flips false→true; other fields preserved."""
    body = (
        "# Header comment.\n"
        "retry_budget: 2\n"
        "specialist_timeout_minutes: 15\n"
        "\n"
        "# user-edited comment\n"
        f"{EMIT_TRACKING_FIELD}: false\n"
    )
    config_path = _write_config(tmp_path, body=body)
    write_emit_tracking_field(tmp_path)
    new_text = config_path.read_text(encoding="utf-8")
    parsed = _pyyaml.safe_load(new_text)
    assert parsed[EMIT_TRACKING_FIELD] is True
    # Other fields byte-identical.
    assert "retry_budget: 2\n" in new_text
    assert "specialist_timeout_minutes: 15\n" in new_text
    # Comments byte-identical.
    assert "# Header comment.\n" in new_text
    assert "# user-edited comment\n" in new_text


def test_write_emit_tracking_field_appends_when_field_absent(
    tmp_path: pathlib.Path,
) -> None:
    """Case 15 — append path: field added with canonical comment block."""
    body = "# Header.\nretry_budget: 2\n"
    config_path = _write_config(tmp_path, body=body)
    write_emit_tracking_field(tmp_path)
    new_text = config_path.read_text(encoding="utf-8")
    parsed = _pyyaml.safe_load(new_text)
    assert parsed[EMIT_TRACKING_FIELD] is True
    # Existing field preserved.
    assert "retry_budget: 2\n" in new_text
    # Canonical comment block present.
    assert "# First-run TEA-boundary orientation tracking" in new_text
    assert "# Source: FR34" in new_text
    # Field at end of file.
    assert new_text.rstrip().endswith(f"{EMIT_TRACKING_FIELD}: true")


def test_write_emit_tracking_field_raises_when_config_absent(
    tmp_path: pathlib.Path,
) -> None:
    """Case 16 — config absent → config-atomic-write-failed."""
    with pytest.raises(OrientationConfigError) as exc_info:
        write_emit_tracking_field(tmp_path)
    assert exc_info.value.reason == "config-atomic-write-failed"


def test_write_emit_tracking_field_raises_when_config_malformed(
    tmp_path: pathlib.Path,
) -> None:
    """Case 17 — malformed YAML → config-yaml-parse-error."""
    _write_config(
        tmp_path,
        body="this is: : not : valid : yaml :::\n  - broken\n: indent\n",
    )
    with pytest.raises(OrientationConfigError) as exc_info:
        write_emit_tracking_field(tmp_path)
    assert exc_info.value.reason == "config-yaml-parse-error"


def test_write_emit_tracking_field_atomic_write_uses_tmp_then_replace(
    tmp_path: pathlib.Path,
) -> None:
    """Case 18 — verify atomic-write pattern (temp-file + os.replace)."""
    body = f"retry_budget: 2\n{EMIT_TRACKING_FIELD}: false\n"
    _write_config(tmp_path, body=body)
    with mock.patch.object(
        _shared,
        "os",
        wraps=os,
    ) as os_spy:
        # Re-use real os.* but spy on os.replace.
        os_spy.replace = mock.Mock(wraps=os.replace)
        os_spy.O_WRONLY = os.O_WRONLY
        os_spy.O_CREAT = os.O_CREAT
        os_spy.O_EXCL = os.O_EXCL
        os_spy.open = os.open
        os_spy.fdopen = os.fdopen
        os_spy.fsync = os.fsync
        os_spy.getpid = os.getpid
        write_emit_tracking_field(tmp_path)
        assert os_spy.replace.call_count == 1
        src, dst = os_spy.replace.call_args[0]
        assert ".tmp." in str(src)
        assert str(dst).endswith("config.yaml")


# --------------------------------------------------------------------------- #
# AC-8 cases 19-20 — pure-decision evaluator                                   #
# --------------------------------------------------------------------------- #


def test_evaluate_orientation_emission_returns_emit_when_first_run(
    tmp_path: pathlib.Path,
) -> None:
    """Case 19 — doc + config-without-field → action=emit."""
    _write_doc_outer_layout(tmp_path)
    _write_config(tmp_path, field_value=None)
    request = OrientationRequest(project_root=tmp_path, repo_root=tmp_path)
    outcome = evaluate_orientation_emission(request)
    assert outcome.action == "emit"
    assert outcome.message_text == _CANONICAL_BODY
    assert outcome.config_field_was_updated is False
    assert outcome.config_path == resolve_config_path(tmp_path)


def test_evaluate_orientation_emission_returns_skip_when_already_emitted(
    tmp_path: pathlib.Path,
) -> None:
    """Case 20 — config field=true → action=skip-already-emitted."""
    _write_doc_outer_layout(tmp_path)
    _write_config(tmp_path, field_value="true")
    request = OrientationRequest(project_root=tmp_path, repo_root=tmp_path)
    outcome = evaluate_orientation_emission(request)
    assert outcome.action == "skip-already-emitted"
    assert outcome.message_text is None
    assert outcome.config_field_was_updated is False


# --------------------------------------------------------------------------- #
# AC-8 cases 21-22 — production emitter                                        #
# --------------------------------------------------------------------------- #


def test_emit_orientation_if_first_run_writes_field_on_emit_branch(
    tmp_path: pathlib.Path,
) -> None:
    """Case 21 — emit branch flips field to true."""
    _write_doc_outer_layout(tmp_path)
    _write_config(tmp_path, field_value="false")
    request = OrientationRequest(project_root=tmp_path, repo_root=tmp_path)
    outcome = emit_orientation_if_first_run(request)
    assert outcome.action == "emit"
    assert outcome.config_field_was_updated is True
    assert outcome.message_text == _CANONICAL_BODY
    # On-disk verification.
    on_disk = _pyyaml.safe_load(
        outcome.config_path.read_text(encoding="utf-8")
    )
    assert on_disk[EMIT_TRACKING_FIELD] is True


def test_emit_orientation_if_first_run_no_write_on_skip_branch(
    tmp_path: pathlib.Path,
) -> None:
    """Case 22 — skip branch leaves on-disk file byte-identical."""
    _write_doc_outer_layout(tmp_path)
    body = (
        "retry_budget: 2\n"
        f"{EMIT_TRACKING_FIELD}: true\n"
    )
    config_path = _write_config(tmp_path, body=body)
    pre_text = config_path.read_text(encoding="utf-8")
    request = OrientationRequest(project_root=tmp_path, repo_root=tmp_path)
    outcome = emit_orientation_if_first_run(request)
    assert outcome.action == "skip-already-emitted"
    assert outcome.config_field_was_updated is False
    post_text = config_path.read_text(encoding="utf-8")
    assert post_text == pre_text  # byte-identical


# --------------------------------------------------------------------------- #
# AC-8 case 23 — SINGLE end-to-end against PRODUCTION doc                      #
# --------------------------------------------------------------------------- #


def test_contract_pair_end_to_end_against_production_doc(
    prod_repo_root: pathlib.Path,
) -> None:
    """Case 23 — runs against PRODUCTION doc; structural enforcement of
    contract-pair shipping discipline.

    If Story 1.12a's section is removed/renamed/depopulated, this test
    fails and the PR cannot land.
    """
    body = extract_orientation_message(prod_repo_root)
    assert body, "production orientation body must be non-empty"
    # FR34-anchored substring assertions per AC-8 case 23.
    assert "TEA validates" in body
    assert "Automator exercises" in body


# --------------------------------------------------------------------------- #
# AC-8 cases 24-25 — template addition + name-matches-constant                 #
# --------------------------------------------------------------------------- #


def test_template_contains_emit_tracking_field_with_default_false() -> None:
    """Case 24 — template parses with field default=False."""
    template_text = load_config_template()
    parsed = _pyyaml.safe_load(template_text)
    assert EMIT_TRACKING_FIELD in parsed
    assert parsed[EMIT_TRACKING_FIELD] is False


def test_template_emit_tracking_field_name_matches_module_constant() -> None:
    """Case 25 — module constant is the YAML key."""
    assert EMIT_TRACKING_FIELD == "tea_boundary_orientation_emitted"
    template_text = load_config_template()
    parsed = _pyyaml.safe_load(template_text)
    assert EMIT_TRACKING_FIELD in parsed


# --------------------------------------------------------------------------- #
# AC-8 case 26 — section-heading constant matches doc heading                  #
# --------------------------------------------------------------------------- #


def test_section_heading_constant_matches_doc_heading_byte_for_byte(
    prod_repo_root: pathlib.Path,
) -> None:
    """Case 26 — module constant equals the H2 line in the production doc.

    Self-test of the contributor-discipline-note at
    ``tea-vs-automator.md:36``.
    """
    assert ORIENTATION_SECTION_HEADING == "## First-Run Orientation Message"
    # The production doc lives at one of two canonical locations
    # (outer-workspace vs. inner-repo layout); use the production
    # resolution logic.
    candidates = [
        prod_repo_root / "bmad-autopilot" / "docs" / "tea-vs-automator.md",
        prod_repo_root / "docs" / "tea-vs-automator.md",
    ]
    doc_path = next((p for p in candidates if p.is_file()), None)
    assert doc_path is not None, (
        f"production tea-vs-automator.md not found at any of: {candidates}"
    )
    text = doc_path.read_text(encoding="utf-8")
    matches = [
        line
        for line in text.splitlines()
        if line == ORIENTATION_SECTION_HEADING
    ]
    assert len(matches) == 1


# --------------------------------------------------------------------------- #
# AC-8 case 27 — cross-story integration with Story 7.6 additive merge         #
# --------------------------------------------------------------------------- #


def test_additively_merge_config_adds_tea_boundary_field_for_pre_78_config(
    tmp_path: pathlib.Path,
) -> None:
    """Case 27 — Story 7.6's additive merge re-introduces the field with
    the canonical comment block when run on a pre-7.8 config.
    """
    # Step 1: scaffold a fresh config via Story 7.5.
    scaffold_config_qa_runbook_stubs(StubScaffoldRequest(project_root=tmp_path))
    config_path = resolve_config_path(tmp_path)
    pre_7_8_text = config_path.read_text(encoding="utf-8")
    # Step 2: simulate a pre-7.8 config by stripping the field + its
    # comment block. The canonical comment block starts with the line
    # "# First-run TEA-boundary orientation tracking" and ends with the
    # field line.
    lines = pre_7_8_text.splitlines(keepends=True)
    keep: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith("# First-run TEA-boundary orientation tracking"):
            skipping = True
            # Walk back over the trailing blank line we just appended.
            if keep and keep[-1] == "\n":
                keep.pop()
            continue
        if skipping:
            if line.startswith(f"{EMIT_TRACKING_FIELD}:"):
                skipping = False
            continue
        keep.append(line)
    stripped_text = "".join(keep)
    config_path.write_text(stripped_text, encoding="utf-8")
    # Confirm pre-7.8 simulation succeeded.
    parsed_before = _pyyaml.safe_load(stripped_text)
    assert EMIT_TRACKING_FIELD not in parsed_before
    # Step 3: invoke Story 7.6's additive merge.
    additively_merge_config(tmp_path)
    # Step 4: assert merged file has the field with default false +
    # the canonical comment block.
    merged_text = config_path.read_text(encoding="utf-8")
    parsed_after = _pyyaml.safe_load(merged_text)
    assert parsed_after[EMIT_TRACKING_FIELD] is False
    assert "# First-run TEA-boundary orientation tracking" in merged_text
    assert "# Source: FR34" in merged_text


# --------------------------------------------------------------------------- #
# AC-8 case 28 — pluggability gate posture                                     #
# --------------------------------------------------------------------------- #


def test_pluggability_gate_does_not_flag_consumers() -> None:
    """Case 28 — substrate-library posture verification.

    Mirrors Story 7.7 case 22. ``tea_boundary_orientation`` is shared
    substrate (sibling of ``story_doc_version_check``,
    ``init_non_destructive_guard``, ``_shared``, ``marker_wiring``).
    The module lives under ``loud_fail_harness/`` and does NOT import
    any specialist-specific module. Manual verification of Story 1.10a's
    CI gate output is documented in Completion Notes.
    """
    module_path = pathlib.Path(tea_boundary_orientation.__file__).resolve()
    assert "loud_fail_harness" in module_path.parts
    text = module_path.read_text(encoding="utf-8")
    forbidden_specialist_imports = [
        "from loud_fail_harness.qa_",
        "from loud_fail_harness.dev_",
        "from loud_fail_harness.review_bmad",
    ]
    for needle in forbidden_specialist_imports:
        assert needle not in text, (
            f"tea_boundary_orientation imports a specialist module: {needle!r}"
        )


# --------------------------------------------------------------------------- #
# Bonus: OrientationOutcome / OrientationRequest validators                    #
# --------------------------------------------------------------------------- #


def test_orientation_request_rejects_relative_project_root() -> None:
    """Validator regression — relative path is rejected."""
    with pytest.raises(ValueError):
        OrientationRequest(project_root=pathlib.Path("./relative"))


def test_orientation_request_rejects_relative_repo_root(
    tmp_path: pathlib.Path,
) -> None:
    """Validator regression — relative repo_root is rejected when provided."""
    with pytest.raises(ValueError):
        OrientationRequest(
            project_root=tmp_path,
            repo_root=pathlib.Path("./relative"),
        )


def test_orientation_outcome_is_frozen(tmp_path: pathlib.Path) -> None:
    """Validator regression — OrientationOutcome is immutable."""
    outcome = OrientationOutcome(
        action="emit",
        message_text="text",
        config_path=tmp_path / "_bmad" / "automation" / "config.yaml",
        config_field_was_updated=True,
    )
    with pytest.raises(Exception):
        outcome.action = "skip-already-emitted"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Review patches (code review 2026-05-08)                                     #
# --------------------------------------------------------------------------- #


def test_appended_field_block_template_matches_config_template() -> None:
    """F1 review patch — _APPENDED_FIELD_BLOCK_TEMPLATE must be byte-identical
    to the comment block preceding the field in config.yaml.template.
    Structural enforcement of AC-4's drift-prevention requirement.
    """
    from loud_fail_harness.tea_boundary_orientation import _APPENDED_FIELD_BLOCK_TEMPLATE

    template_text = load_config_template()
    marker = "# First-run TEA-boundary"
    idx = template_text.find(marker)
    assert idx >= 0, "comment block not found in config.yaml.template"
    field_line = f"{EMIT_TRACKING_FIELD}: false"
    field_idx = template_text.find(field_line, idx)
    assert field_idx >= 0, "field line not found in config.yaml.template"
    template_comment_block = template_text[idx:field_idx]
    assert _APPENDED_FIELD_BLOCK_TEMPLATE == template_comment_block, (
        "_APPENDED_FIELD_BLOCK_TEMPLATE has drifted from config.yaml.template's "
        "comment block — update one to match the other"
    )


def test_extract_orientation_message_raises_on_unicode_decode_error(
    tmp_path: pathlib.Path,
) -> None:
    """F2 review patch — UnicodeDecodeError on read_text → doc-missing (AC-2)."""
    _write_doc_outer_layout(tmp_path)
    with mock.patch.object(
        pathlib.Path,
        "read_text",
        side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "reason"),
    ):
        with pytest.raises(OrientationConfigError) as exc_info:
            extract_orientation_message(tmp_path)
    assert exc_info.value.reason == "doc-missing"


def test_read_emit_tracking_field_raises_on_oserror(
    tmp_path: pathlib.Path,
) -> None:
    """F3 review patch — OSError on config read_text → config-yaml-parse-error (AC-3)."""
    _write_config(tmp_path, field_value="false")
    with mock.patch.object(
        pathlib.Path, "read_text", side_effect=OSError("permission denied")
    ):
        with pytest.raises(OrientationConfigError) as exc_info:
            read_emit_tracking_field(tmp_path)
    assert exc_info.value.reason == "config-yaml-parse-error"
    assert exc_info.value.project_root == tmp_path


def test_write_emit_tracking_field_raises_on_multiple_field_occurrences(
    tmp_path: pathlib.Path,
) -> None:
    """F4 review patch — two field occurrences → config-yaml-parse-error (AC-4)."""
    body = (
        f"{EMIT_TRACKING_FIELD}: false\n"
        "retry_budget: 2\n"
        f"{EMIT_TRACKING_FIELD}: false\n"
    )
    _write_config(tmp_path, body=body)
    with pytest.raises(OrientationConfigError) as exc_info:
        write_emit_tracking_field(tmp_path)
    assert exc_info.value.reason == "config-yaml-parse-error"
