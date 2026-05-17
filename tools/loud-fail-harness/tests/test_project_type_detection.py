"""Tests for the Story 9.2 project-type-detection substrate module.

Covers AC-7 — fourteen independent test functions covering the
detection-rule matrix (mobile / web / api / ambiguous /
no-indicators), the diagnostic-prose contract, and the atomic-write
helper's three branches (written / preserved / appended) plus the
atomic-on-failure semantics.

Pattern 5 + Pattern 6 — explicit, named tests; no shared mutable
state; caller-injected ``tmp_path`` fixture so tests do NOT touch
the outer workspace's filesystem.

Each test exercises the public API of
:mod:`loud_fail_harness.project_type_detection` (the Story 9.2
substrate sensor + atomic state-update). Tests intentionally do
NOT cross-reference substrate components 4 (enumeration_check) or
5 (fixture_coverage) — Story 9.1's review-finding pattern flagged
overclaimed substrate-component coverage in test docstrings.
"""

from __future__ import annotations

import json
import pathlib
import textwrap
from unittest import mock

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness.config_qa_runbook_stub import (
    StubScaffoldRequest,
    scaffold_config_qa_runbook_stubs,
)
from loud_fail_harness.project_type_detection import (
    DetectionOutcome,
    DetectionRequest,
    WriteResult,
    detect_project_type,
    write_detected_project_type,
)

# --------------------------------------------------------------------------- #
# Mobile rule — three positive paths (RN, Flutter, Expo).                     #
# --------------------------------------------------------------------------- #


def test_mobile_react_native_ios_and_android_directories(
    tmp_path: pathlib.Path,
) -> None:
    """AC-7 case 1 — RN layout: top-level ``ios/`` + ``android/``."""
    (tmp_path / "ios").mkdir()
    (tmp_path / "android").mkdir()

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "mobile"
    assert outcome.reason == "unambiguous"
    assert "ios/" in outcome.evidence
    assert "android/" in outcome.evidence
    assert outcome.diagnostic is None


def test_mobile_flutter_pubspec_yaml(tmp_path: pathlib.Path) -> None:
    """AC-7 case 2 — Flutter top-level ``pubspec.yaml`` manifest."""
    (tmp_path / "pubspec.yaml").write_text(
        textwrap.dedent(
            """\
            name: my_flutter_app
            description: A new Flutter project.
            environment:
              sdk: '>=3.0.0 <4.0.0'
            flutter:
              uses-material-design: true
            """
        ),
        encoding="utf-8",
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "mobile"
    assert outcome.reason == "unambiguous"
    assert "pubspec.yaml" in outcome.evidence


def test_mobile_expo_app_json(tmp_path: pathlib.Path) -> None:
    """AC-7 case 3 — Expo manifest: ``app.json`` with top-level ``expo``
    key."""
    (tmp_path / "app.json").write_text(
        json.dumps({"expo": {"name": "MyExpoApp", "slug": "my-expo-app"}}),
        encoding="utf-8",
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "mobile"
    assert outcome.reason == "unambiguous"
    assert "app.json:expo" in outcome.evidence


# --------------------------------------------------------------------------- #
# Web rule — package.json with front-end framework deps.                      #
# --------------------------------------------------------------------------- #


def test_web_next_in_package_json(tmp_path: pathlib.Path) -> None:
    """AC-7 case 4 — Next.js in ``dependencies`` triggers ``web``."""
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"next": "^14.0.0"}}),
        encoding="utf-8",
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "web"
    assert outcome.reason == "unambiguous"
    assert "package.json:next" in outcome.evidence


def test_web_react_in_dev_dependencies(tmp_path: pathlib.Path) -> None:
    """AC-7 case 5 — React in ``devDependencies`` triggers ``web``."""
    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"react": "^18.0.0"}}),
        encoding="utf-8",
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "web"
    assert outcome.reason == "unambiguous"
    assert "package.json:react" in outcome.evidence


# --------------------------------------------------------------------------- #
# API rule — Node, Python, Go positive paths.                                 #
# --------------------------------------------------------------------------- #


def test_api_fastify_package_json(tmp_path: pathlib.Path) -> None:
    """AC-7 case 6 — Fastify in ``dependencies`` triggers ``api``."""
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"fastify": "^4.0.0"}}),
        encoding="utf-8",
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "api"
    assert outcome.reason == "unambiguous"
    assert "package.json:fastify" in outcome.evidence


def test_api_fastapi_pyproject(tmp_path: pathlib.Path) -> None:
    """AC-7 case 7 — FastAPI under PEP-621 ``[project].dependencies``."""
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [project]
            name = "demo"
            version = "0.1.0"
            dependencies = [
                "fastapi>=0.100",
                "uvicorn[standard]",
            ]
            """
        ),
        encoding="utf-8",
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "api"
    assert outcome.reason == "unambiguous"
    assert "pyproject.toml:fastapi" in outcome.evidence


def test_api_go_mod_marker(tmp_path: pathlib.Path) -> None:
    """AC-7 case 8 — bare ``go.mod`` file triggers ``api`` (file-
    existence-only marker)."""
    (tmp_path / "go.mod").write_text(
        "module example.com/demo\n\ngo 1.22\n", encoding="utf-8"
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "api"
    assert outcome.reason == "unambiguous"
    assert "go.mod" in outcome.evidence


# --------------------------------------------------------------------------- #
# Ambiguous + no-indicators paths.                                            #
# --------------------------------------------------------------------------- #


def test_ambiguous_mobile_plus_web_monorepo(
    tmp_path: pathlib.Path,
) -> None:
    """AC-7 case 9 — ios/+android/ + package.json web framework →
    ambiguous halt; diagnostic enumerates both indicator names."""
    (tmp_path / "ios").mkdir()
    (tmp_path / "android").mkdir()
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"next": "^14.0.0"}}),
        encoding="utf-8",
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type is None
    assert outcome.reason == "ambiguous"
    assert outcome.diagnostic is not None
    assert "ios/" in outcome.diagnostic
    assert "android/" in outcome.diagnostic
    assert "package.json:next" in outcome.diagnostic


def test_no_indicators_empty_dir(tmp_path: pathlib.Path) -> None:
    """AC-7 case 10 — empty project root → no-indicators halt;
    diagnostic names the manual-override path."""
    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type is None
    assert outcome.reason == "no-indicators"
    assert outcome.evidence == []
    assert outcome.diagnostic is not None
    # Names the manual-override path (project_type field in config.yaml).
    assert "project_type" in outcome.diagnostic
    assert "_bmad/automation/config.yaml" in outcome.diagnostic


def test_diagnostic_prose_lists_three_resolution_options_in_order(
    tmp_path: pathlib.Path,
) -> None:
    """AC-7 case 11 — assert the diagnostic string contains the three
    numbered resolution options in the canonical order per AC-3 for
    both the ambiguous and the no-indicators halt paths."""
    # Ambiguous halt.
    (tmp_path / "ios").mkdir()
    (tmp_path / "android").mkdir()
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"vue": "^3.0.0"}}),
        encoding="utf-8",
    )
    ambiguous = detect_project_type(
        DetectionRequest(project_root=tmp_path)
    )
    assert ambiguous.diagnostic is not None
    _assert_three_options_in_canonical_order(ambiguous.diagnostic)

    # No-indicators halt (fresh empty dir).
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    no_indicators = detect_project_type(
        DetectionRequest(project_root=empty_root)
    )
    assert no_indicators.diagnostic is not None
    _assert_three_options_in_canonical_order(no_indicators.diagnostic)


def _assert_three_options_in_canonical_order(diagnostic: str) -> None:
    pos_1 = diagnostic.find("1.")
    pos_2 = diagnostic.find("2.")
    pos_3 = diagnostic.find("3.")
    assert pos_1 != -1, "diagnostic missing option 1"
    assert pos_2 != -1, "diagnostic missing option 2"
    assert pos_3 != -1, "diagnostic missing option 3"
    assert pos_1 < pos_2 < pos_3, (
        "three options must appear in canonical order"
    )
    # Each option's anchor phrase appears in the right span.
    assert "config.yaml" in diagnostic[pos_1:pos_2]
    assert (
        "Restructure" in diagnostic[pos_2:pos_3]
        or "restructure" in diagnostic[pos_2:pos_3]
    )
    assert (
        "issue" in diagnostic[pos_3:]
        or "Automator" in diagnostic[pos_3:]
    )


# --------------------------------------------------------------------------- #
# write_detected_project_type — three branches + atomic-on-failure.           #
# --------------------------------------------------------------------------- #


def test_write_detected_project_type_proceed_fresh(
    tmp_path: pathlib.Path,
) -> None:
    """AC-7 case 12 — proceed-fresh: scaffold canonical config.yaml via
    Story 7.5, write detected value, assert parsed YAML carries
    project_type and the surrounding comment block is preserved."""
    scaffold_config_qa_runbook_stubs(
        StubScaffoldRequest(project_root=tmp_path)
    )

    result = write_detected_project_type(tmp_path, "mobile")

    assert result.action == "written"
    assert result.detected_value == "mobile"
    assert result.existing_value is None

    config_path = tmp_path / "_bmad" / "automation" / "config.yaml"
    raw = config_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw)
    assert parsed["project_type"] == "mobile"
    # AC-4 source-cross-reference line is preserved.
    assert "FR40 | FR-P1.5-2" in raw


def test_write_detected_project_type_preserved_when_already_set(
    tmp_path: pathlib.Path,
) -> None:
    """AC-7 case 13 — existing config has project_type: api → no-op,
    file value remains api (Story 7.6 existing-value-wins contract)."""
    config_path = tmp_path / "_bmad" / "automation" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "retry_budget: 2\nproject_type: api\n", encoding="utf-8"
    )

    result = write_detected_project_type(tmp_path, "mobile")

    assert result.action == "preserved"
    assert result.detected_value == "mobile"
    assert result.existing_value == "api"

    parsed = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert parsed["project_type"] == "api"


def test_write_detected_project_type_atomic_no_partial_write(
    tmp_path: pathlib.Path,
) -> None:
    """AC-7 case 14 — Pattern 4 atomic-on-failure: when ``os.replace``
    raises mid-write, the original config.yaml file's bytes are
    unchanged."""
    scaffold_config_qa_runbook_stubs(
        StubScaffoldRequest(project_root=tmp_path)
    )
    config_path = tmp_path / "_bmad" / "automation" / "config.yaml"
    pre_write_bytes = config_path.read_bytes()

    with mock.patch(
        "loud_fail_harness.project_type_detection.os.replace",
        side_effect=OSError("simulated replace failure"),
    ):
        with pytest.raises(OSError, match="simulated replace failure"):
            write_detected_project_type(tmp_path, "web")

    post_write_bytes = config_path.read_bytes()
    assert post_write_bytes == pre_write_bytes, (
        "atomic-on-failure violated: original config.yaml bytes "
        "changed despite write raising"
    )
    # No leftover temp file from the failed atomic-write attempt.
    leftover_temps = list(config_path.parent.glob(f"{config_path.name}.tmp.*"))
    assert leftover_temps == [], (
        f"unexpected temp file(s) left behind: {leftover_temps}"
    )


# --------------------------------------------------------------------------- #
# Pydantic model + request-validation surface (defensive boundary).           #
# --------------------------------------------------------------------------- #


def test_detection_request_rejects_relative_project_root() -> None:
    """``DetectionRequest`` mirrors :class:`GuardRequest` /
    :class:`StubScaffoldRequest`'s absolute-path field validator;
    relative paths raise ``ValidationError`` (D1 precedent)."""
    with pytest.raises(ValidationError):
        DetectionRequest(project_root=pathlib.Path("./relative-root"))


def test_outcome_and_write_result_are_frozen(
    tmp_path: pathlib.Path,
) -> None:
    """:class:`DetectionOutcome` and :class:`WriteResult` are
    Pattern-6 frozen Pydantic v2 models — mutation raises."""
    outcome = DetectionOutcome(reason="no-indicators", diagnostic="x")
    with pytest.raises(ValidationError):
        outcome.reason = "unambiguous"  # type: ignore[misc]

    write = WriteResult(
        action="written",
        detected_value="web",
        config_path=tmp_path / "config.yaml",
    )
    with pytest.raises(ValidationError):
        write.action = "appended"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Review-fix tests (Story 9.2 code-review patches P-01 through P-09).        #
# --------------------------------------------------------------------------- #


def test_mobile_react_native_with_react_peer_dep_not_ambiguous(
    tmp_path: pathlib.Path,
) -> None:
    """P-01 review fix — canonical RN layout: ios/+android/ + react in
    package.json must classify as mobile, not ambiguous. react is a
    mandatory RN peer dependency and must not trigger the web-ambiguity
    guard when mobile indicators are also present."""
    (tmp_path / "ios").mkdir()
    (tmp_path / "android").mkdir()
    (tmp_path / "package.json").write_text(
        json.dumps(
            {"dependencies": {"react": "18.2.0", "react-native": "0.73.0"}}
        ),
        encoding="utf-8",
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "mobile"
    assert outcome.reason == "unambiguous"
    assert "ios/" in outcome.evidence
    assert "android/" in outcome.evidence


def test_write_detected_project_type_appended(
    tmp_path: pathlib.Path,
) -> None:
    """P-04 review fix — appended branch: config.yaml without the
    canonical placeholder line → write_detected_project_type appends
    the key at end-of-file."""
    config_path = tmp_path / "_bmad" / "automation" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("retry_budget: 2\n", encoding="utf-8")

    result = write_detected_project_type(tmp_path, "api")

    assert result.action == "appended"
    assert result.detected_value == "api"
    assert result.existing_value is None

    parsed = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert parsed["project_type"] == "api"


def test_ambiguous_mobile_plus_api_monorepo(
    tmp_path: pathlib.Path,
) -> None:
    """P-05 review fix — mobile + api conflict → ambiguous halt.
    ios/+android/ + go.mod (RN + Go backend monorepo)."""
    (tmp_path / "ios").mkdir()
    (tmp_path / "android").mkdir()
    (tmp_path / "go.mod").write_text(
        "module example.com/demo\n\ngo 1.22\n", encoding="utf-8"
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type is None
    assert outcome.reason == "ambiguous"
    assert outcome.diagnostic is not None
    assert "ios/" in outcome.diagnostic
    assert "android/" in outcome.diagnostic
    assert "go.mod" in outcome.diagnostic


def test_api_poetry_pyproject(tmp_path: pathlib.Path) -> None:
    """P-06 review fix — Poetry-style pyproject.toml (no [project] table,
    only [tool.poetry.dependencies]) triggers api classification."""
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """\
            [tool.poetry]
            name = "demo"
            version = "0.1.0"

            [tool.poetry.dependencies]
            python = "^3.11"
            fastapi = "^0.100.0"
            """
        ),
        encoding="utf-8",
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "api"
    assert outcome.reason == "unambiguous"
    assert "pyproject.toml:fastapi" in outcome.evidence


def test_mobile_app_json_react_native_key(tmp_path: pathlib.Path) -> None:
    """P-07 review fix (AC-7 gap) — app.json with react-native top-level
    key (React Native bare workflow manifest) → mobile classification."""
    (tmp_path / "app.json").write_text(
        json.dumps({"react-native": {"name": "MyRNApp"}}),
        encoding="utf-8",
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "mobile"
    assert outcome.reason == "unambiguous"
    assert "app.json:react-native" in outcome.evidence


def test_pubspec_yaml_as_directory_not_mobile(tmp_path: pathlib.Path) -> None:
    """P-08 review fix — a directory named pubspec.yaml at project root
    must not trigger mobile classification (is_file() guard)."""
    (tmp_path / "pubspec.yaml").mkdir()

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type is None
    assert outcome.reason == "no-indicators"


def test_api_cargo_toml_marker(tmp_path: pathlib.Path) -> None:
    """P-09 review fix — Cargo.toml file-existence triggers api."""
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "api"
    assert outcome.reason == "unambiguous"
    assert "Cargo.toml" in outcome.evidence


def test_api_pom_xml_marker(tmp_path: pathlib.Path) -> None:
    """P-09 review fix — pom.xml file-existence triggers api."""
    (tmp_path / "pom.xml").write_text("<project/>\n", encoding="utf-8")

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "api"
    assert outcome.reason == "unambiguous"
    assert "pom.xml" in outcome.evidence


def test_api_build_gradle_marker(tmp_path: pathlib.Path) -> None:
    """P-09 review fix — build.gradle file-existence triggers api."""
    (tmp_path / "build.gradle").write_text("// gradle\n", encoding="utf-8")

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "api"
    assert outcome.reason == "unambiguous"
    assert "build.gradle" in outcome.evidence


def test_write_detected_project_type_preserved_when_non_canonical_value(
    tmp_path: pathlib.Path,
) -> None:
    """P-03 review fix — config.yaml with a non-canonical project_type
    value must not have a duplicate key appended on write; the helper
    returns action='preserved' to respect the existing-value-wins
    contract even for unrecognized values."""
    config_path = tmp_path / "_bmad" / "automation" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "retry_budget: 2\nproject_type: custom-monorepo\n", encoding="utf-8"
    )

    result = write_detected_project_type(tmp_path, "mobile")

    assert result.action == "preserved"
    content = config_path.read_text(encoding="utf-8")
    assert content.count("project_type:") == 1



# =========================================================================
# Story 12.1 — read-side short-circuit on existing
# `_bmad/automation/config.yaml:project_type`. Each test below names its
# AC predicate. The 27 pre-existing tests are byte-identical.
# =========================================================================


def _write_config(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    """AC-6 setup helper — write a config.yaml with the given body
    text under `<tmp_path>/_bmad/automation/`. Returns the file path."""
    config_dir = tmp_path / "_bmad" / "automation"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(body, encoding="utf-8")
    return config_path


def test_existing_config_short_circuits_to_mobile(
    tmp_path: pathlib.Path,
) -> None:
    """AC-1 — canonical mobile value in config short-circuits before
    indicator scan; evidence string is the exact single-token form."""
    _write_config(tmp_path, "project_type: mobile\n")

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "mobile"
    assert outcome.reason == "unambiguous"
    assert outcome.diagnostic is None
    assert outcome.evidence == [
        "_bmad/automation/config.yaml:project_type=mobile"
    ]


def test_existing_config_short_circuits_to_web(
    tmp_path: pathlib.Path,
) -> None:
    """AC-1 — canonical web value in config short-circuits before
    indicator scan."""
    _write_config(tmp_path, "project_type: web\n")

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "web"
    assert outcome.reason == "unambiguous"
    assert outcome.diagnostic is None
    assert outcome.evidence == [
        "_bmad/automation/config.yaml:project_type=web"
    ]


def test_existing_config_short_circuits_to_api(
    tmp_path: pathlib.Path,
) -> None:
    """AC-1 — canonical api value in config short-circuits before
    indicator scan."""
    _write_config(tmp_path, "project_type: api\n")

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "api"
    assert outcome.reason == "unambiguous"
    assert outcome.diagnostic is None
    assert outcome.evidence == [
        "_bmad/automation/config.yaml:project_type=api"
    ]


def test_existing_config_short_circuits_with_surrounding_comments(
    tmp_path: pathlib.Path,
) -> None:
    """AC-1 + AC-2 — column-0 anchor honors the key regardless of
    surrounding comment lines; mimics the canonical
    `config.yaml.template` shape from Story 9.2 AC-4."""
    _write_config(
        tmp_path,
        "# Source: FR40 | FR-P1.5-2\n"
        "project_type: mobile\n"
        "# trailing comment\n",
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "mobile"
    assert outcome.reason == "unambiguous"
    assert outcome.diagnostic is None
    assert outcome.evidence == [
        "_bmad/automation/config.yaml:project_type=mobile"
    ]


def test_existing_config_takes_precedence_over_top_level_indicators(
    tmp_path: pathlib.Path,
) -> None:
    """AC-1 — load-bearing behavioral contract: explicit-config wins
    over filesystem indicators; the indicator scan is skipped so
    `package.json:react` does NOT appear in evidence."""
    _write_config(tmp_path, "project_type: api\n")
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react": "^18.0.0"}}),
        encoding="utf-8",
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "api"
    assert outcome.reason == "unambiguous"
    assert outcome.evidence == [
        "_bmad/automation/config.yaml:project_type=api"
    ]


def test_existing_config_short_circuits_in_nested_layout_case(
    tmp_path: pathlib.Path,
) -> None:
    """AC-1 — paw-care-app trigger case: `_bmad/` at the root, the
    mobile workspace under a subdirectory. The top-level-only
    indicator scan would find nothing; the read-side short-circuit
    honors the practitioner-supplied value."""
    _write_config(tmp_path, "project_type: mobile\n")
    nested = tmp_path / "paw-care"
    (nested / "ios").mkdir(parents=True)
    (nested / "android").mkdir(parents=True)

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "mobile"
    assert outcome.reason == "unambiguous"
    assert outcome.evidence == [
        "_bmad/automation/config.yaml:project_type=mobile"
    ]


def test_malformed_config_falls_through_to_indicator_scan(
    tmp_path: pathlib.Path,
) -> None:
    """AC-3 — `UnicodeDecodeError` on read is caught; indicator scan
    runs unchanged."""
    config_dir = tmp_path / "_bmad" / "automation"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").write_bytes(b"\xff\xfe\x00\x01nope")
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"next": "^14"}}),
        encoding="utf-8",
    )

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "web"
    assert outcome.evidence == ["package.json:next"]


def test_unreadable_config_falls_through_to_indicator_scan(
    tmp_path: pathlib.Path,
) -> None:
    """AC-3 — `IsADirectoryError` (subclass of `OSError`) on read is
    caught; indicator scan runs unchanged."""
    config_dir = tmp_path / "_bmad" / "automation"
    config_dir.mkdir(parents=True)
    (config_dir / "config.yaml").mkdir()
    (tmp_path / "go.mod").write_text("module foo\n", encoding="utf-8")

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "api"
    assert outcome.evidence == ["go.mod"]


def test_non_canonical_value_in_config_falls_through_to_indicator_scan(
    tmp_path: pathlib.Path,
) -> None:
    """AC-4 — non-canonical value (`desktop`) does NOT short-circuit;
    `_scan_existing_project_type` returns None for it; the indicator
    scan runs unchanged."""
    _write_config(tmp_path, "project_type: desktop\n")
    (tmp_path / "pubspec.yaml").write_text("name: foo\n", encoding="utf-8")

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "mobile"
    assert outcome.evidence == ["pubspec.yaml"]


def test_commented_only_project_type_line_falls_through_unchanged(
    tmp_path: pathlib.Path,
) -> None:
    """AC-3 — the canonical commented-placeholder line from
    `config.yaml.template` MUST NOT trigger the short-circuit;
    first-init flow on a freshly-scaffolded template flows to the
    indicator scan."""
    _write_config(tmp_path, "# project_type: mobile\n")

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type is None
    assert outcome.reason == "no-indicators"
    assert outcome.diagnostic is not None


def test_absent_config_falls_through_unchanged_regression(
    tmp_path: pathlib.Path,
) -> None:
    """AC-3 — most important regression guard: no `_bmad/` directory
    at all; the canonical Story 9.2 happy path remains unaffected
    (RN ios/+android/ resolves to mobile)."""
    (tmp_path / "ios").mkdir()
    (tmp_path / "android").mkdir()

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "mobile"
    assert outcome.evidence == ["ios/", "android/"]


def test_indented_project_type_key_under_nested_mapping_does_not_short_circuit(
    tmp_path: pathlib.Path,
) -> None:
    """AC-2 — column-0 anchor at `_scan_existing_project_type` is
    load-bearing; indented `project_type:` (e.g., under `metadata:`)
    is ignored on the read path just as it is on the write path."""
    _write_config(tmp_path, "metadata:\n  project_type: mobile\n")
    (tmp_path / "go.mod").write_text("module foo\n", encoding="utf-8")

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type == "api"
    assert outcome.evidence == ["go.mod"]


def test_no_indicators_diagnostic_appends_non_canonical_value_hint(
    tmp_path: pathlib.Path,
) -> None:
    """AC-5 (IN) — when the indicator scan resolves to no-indicators
    AND a non-canonical `project_type:` line is present in config,
    the diagnostic gains a self-diagnosis hint pointing at the
    canonical-literal requirement. No marker emission; no reason
    field change."""
    _write_config(tmp_path, "project_type: desktop\n")

    outcome = detect_project_type(DetectionRequest(project_root=tmp_path))

    assert outcome.project_type is None
    assert outcome.reason == "no-indicators"
    assert outcome.diagnostic is not None
    assert "not one of {web, api, mobile}" in outcome.diagnostic
