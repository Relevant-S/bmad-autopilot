"""Contract-coverage matrix for substrate component 1 (envelope validator).

This docstring IS the contract-coverage checklist required by AC-4. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (no automated check that every row is
present), per the story's deliberate avoidance of cargo-culted coverage gates.

Negative-path — forbidden flow-policy fields (FR52):
    [x] envelope contains ``next_action``                        → test_forbidden_field_next_action
    [x] envelope contains ``recommendation``                     → test_forbidden_field_recommendation
    [x] format_errors rewrites both with named messages          → test_format_errors_names_forbidden_field

Negative-path — missing required top-level fields:
    [x] missing ``status``                                       → test_missing_required_top_level[status]
    [x] missing ``artifacts``                                    → test_missing_required_top_level[artifacts]
    [x] missing ``findings``                                     → test_missing_required_top_level[findings]
    [x] missing ``rationale``                                    → test_missing_required_top_level[rationale]

Negative-path — missing required finding-object subfields:
    [x] finding missing ``id``                                   → test_missing_required_finding_subfield[id]
    [x] finding missing ``source``                               → test_missing_required_finding_subfield[source]
    [x] finding missing ``title``                                → test_missing_required_finding_subfield[title]
    [x] finding missing ``detail``                               → test_missing_required_finding_subfield[detail]
    [x] finding missing ``location``                             → test_missing_required_finding_subfield[location]
    [x] finding missing ``bucket``                               → test_missing_required_finding_subfield[bucket]
    [x] finding missing ``severity``                             → test_missing_required_finding_subfield[severity]

Positive-path — specialist extension shapes:
    [x] Dev: ``proposed_commit_message`` + ``scope_expanded_to`` → test_specialist_extension_dev
    [x] QA: ``ac_results`` with one full-shape AC entry          → test_specialist_extension_qa
    [x] Review-BMAD: ``failed_layers`` with enum members         → test_specialist_extension_review_bmad

Negative-path — Pattern 1 / closed-enumeration discipline:
    [x] ``status`` value ``Pass`` (capitalized) rejected         → test_enum_violation_status_capitalized
    [x] ``status`` value ``passed`` (extra suffix) rejected      → test_enum_violation_status_passed
    [x] unknown ``bucket`` value rejected                        → test_enum_violation_bucket_unknown
    [x] unknown ``severity`` value (e.g. ``Critical``) rejected  → test_enum_violation_severity_unknown

Schema self-check:
    [x] schemas/envelope.schema.yaml meta-validates              → test_schema_meta_validates

Canonical positive envelope (AC-3 dependency):
    [x] examples/envelopes/dev-pass.yaml validates clean         → test_canonical_dev_pass_envelope_validates

CLI / harness behavior:
    [x] empty argv → exit 0 (gate is no-op on empty set)         → test_cli_no_envelopes_returns_zero
    [x] --require-nonempty + empty argv → exit 2                  → test_cli_require_nonempty_with_no_args
    [x] valid envelope → exit 0                                  → test_cli_valid_envelope_returns_zero
    [x] forbidden-field envelope → exit 1, names field           → test_cli_forbidden_field_returns_one
    [x] schema malformed → exit 2                                → test_cli_malformed_schema_returns_two
    [x] envelope unreadable → exit 2                             → test_cli_envelope_unreadable_returns_two
    [x] envelope is not a mapping → produces synthetic error     → test_validate_file_non_mapping
    [x] find_repo_root raises when no ancestor has .github       → test_find_repo_root_no_ancestor

Format edge cases:
    [x] format_errors([]) returns empty string                   → test_format_errors_empty
    [x] nested additionalProperties (inside finding) formatted   → test_format_errors_nested_additional_property
    [x] `not`-only schema produces generic forbidden message     → test_format_errors_not_clause_only
    [x] non-additional-properties error includes path pointer    → test_format_errors_path_pointer
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from loud_fail_harness.envelope_validator import (
    FORBIDDEN_FLOW_POLICY_FIELDS,
    find_repo_root,
    format_errors,
    load_schema,
    main,
    validate_envelope,
    validate_file,
)

REPO_ROOT = find_repo_root()
SCHEMA_PATH = REPO_ROOT / "schemas" / "envelope.schema.yaml"
DEV_PASS_ENVELOPE_PATH = REPO_ROOT / "examples" / "envelopes" / "dev-pass.yaml"


@pytest.fixture(scope="module")
def schema() -> dict:
    return load_schema(SCHEMA_PATH)


def _minimal_valid_envelope() -> dict:
    return {
        "status": "pass",
        "artifacts": ["src/foo.py"],
        "findings": [],
        "rationale": "all green",
    }


def _minimal_finding(**overrides: object) -> dict:
    base = {
        "id": "F-001",
        "source": "blind",
        "title": "example finding",
        "detail": "details here",
        "location": "src/foo.py:42",
        "bucket": "patch",
        "severity": "MED",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Schema self-check + canonical envelope                                      #
# --------------------------------------------------------------------------- #


def test_schema_meta_validates() -> None:
    schema = load_schema(SCHEMA_PATH)
    assert schema.get("$schema", "").endswith("/draft/2020-12/schema")


def test_canonical_dev_pass_envelope_validates(schema: dict) -> None:
    errors = validate_file(DEV_PASS_ENVELOPE_PATH, schema)
    assert errors == [], format_errors(errors)


def test_minimal_envelope_validates(schema: dict) -> None:
    assert validate_envelope(_minimal_valid_envelope(), schema) == []


# --------------------------------------------------------------------------- #
# Negative-path: forbidden flow-policy fields                                 #
# --------------------------------------------------------------------------- #


def test_forbidden_field_next_action(schema: dict) -> None:
    envelope = _minimal_valid_envelope() | {"next_action": "retry"}
    errors = validate_envelope(envelope, schema)
    assert errors, "forbidden field next_action should produce errors"
    output = format_errors(errors)
    assert "forbidden flow-policy field: next_action" in output


def test_forbidden_field_recommendation(schema: dict) -> None:
    envelope = _minimal_valid_envelope() | {"recommendation": "merge"}
    errors = validate_envelope(envelope, schema)
    assert errors, "forbidden field recommendation should produce errors"
    output = format_errors(errors)
    assert "forbidden flow-policy field: recommendation" in output


def test_format_errors_names_forbidden_field(schema: dict) -> None:
    """Sanity check that EVERY name in FORBIDDEN_FLOW_POLICY_FIELDS produces
    a named message (so adding a new entry to the set is automatically tested
    without remembering to add a parametrize row)."""
    for field in FORBIDDEN_FLOW_POLICY_FIELDS:
        envelope = _minimal_valid_envelope() | {field: "x"}
        output = format_errors(validate_envelope(envelope, schema))
        assert f"forbidden flow-policy field: {field}" in output, (
            f"missing named rewrite for forbidden field {field}"
        )


def test_unknown_top_level_field_emits_named_error(schema: dict) -> None:
    """A future flow-policy-implying field name not yet in the forbidden set
    is still rejected — this is the defensive `additionalProperties: false`
    catch."""
    envelope = _minimal_valid_envelope() | {"should_retry": True}
    errors = validate_envelope(envelope, schema)
    assert errors
    output = format_errors(errors)
    assert "should_retry" in output
    assert "forbidden flow-policy field" not in output  # not in the named set


# --------------------------------------------------------------------------- #
# Negative-path: missing required fields                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("field", ["status", "artifacts", "findings", "rationale"])
def test_missing_required_top_level(schema: dict, field: str) -> None:
    envelope = _minimal_valid_envelope()
    del envelope[field]
    errors = validate_envelope(envelope, schema)
    assert errors, f"missing required field {field} should fail"
    messages = " ".join(err.message for err in errors)
    assert field in messages


@pytest.mark.parametrize(
    "subfield",
    ["id", "source", "title", "detail", "location", "bucket", "severity"],
)
def test_missing_required_finding_subfield(schema: dict, subfield: str) -> None:
    finding = _minimal_finding()
    del finding[subfield]
    envelope = _minimal_valid_envelope() | {"findings": [finding]}
    errors = validate_envelope(envelope, schema)
    assert errors, f"missing finding subfield {subfield} should fail"
    messages = " ".join(err.message for err in errors)
    assert subfield in messages


# --------------------------------------------------------------------------- #
# Positive-path: specialist extensions                                        #
# --------------------------------------------------------------------------- #


def test_specialist_extension_dev(schema: dict) -> None:
    envelope = _minimal_valid_envelope() | {
        "proposed_commit_message": "feat: add foo",
        "scope_expanded_to": ["src/bar.py"],
    }
    assert validate_envelope(envelope, schema) == []


def test_specialist_extension_qa(schema: dict) -> None:
    envelope = _minimal_valid_envelope() | {
        "ac_results": [
            {
                "ac_id": "AC-1",
                "status": "pass",
                "assertions": ["login button visible"],
                "evidence_refs": ["evidence/screen-001.png"],
                "semantic_verification": {"checked_by": "playwright"},
            }
        ],
    }
    assert validate_envelope(envelope, schema) == []


def test_specialist_extension_review_bmad(schema: dict) -> None:
    envelope = _minimal_valid_envelope() | {
        "failed_layers": ["blind", "edge"],
    }
    assert validate_envelope(envelope, schema) == []


def test_finding_optional_retry_likely_to_resolve(schema: dict) -> None:
    finding = _minimal_finding(retry_likely_to_resolve=True)
    envelope = _minimal_valid_envelope() | {"findings": [finding]}
    assert validate_envelope(envelope, schema) == []


# --------------------------------------------------------------------------- #
# Negative-path: closed-enumeration / Pattern 1 violations                    #
# --------------------------------------------------------------------------- #


def test_enum_violation_status_capitalized(schema: dict) -> None:
    envelope = _minimal_valid_envelope() | {"status": "Pass"}
    errors = validate_envelope(envelope, schema)
    assert errors


def test_enum_violation_status_passed(schema: dict) -> None:
    envelope = _minimal_valid_envelope() | {"status": "passed"}
    errors = validate_envelope(envelope, schema)
    assert errors


def test_enum_violation_bucket_unknown(schema: dict) -> None:
    finding = _minimal_finding(bucket="suggest")
    envelope = _minimal_valid_envelope() | {"findings": [finding]}
    errors = validate_envelope(envelope, schema)
    assert errors


def test_enum_violation_severity_unknown(schema: dict) -> None:
    finding = _minimal_finding(severity="Critical")
    envelope = _minimal_valid_envelope() | {"findings": [finding]}
    errors = validate_envelope(envelope, schema)
    assert errors


def test_failed_layers_unknown_member_rejected(schema: dict) -> None:
    envelope = _minimal_valid_envelope() | {"failed_layers": ["compliance"]}
    errors = validate_envelope(envelope, schema)
    assert errors


# --------------------------------------------------------------------------- #
# format_errors edge cases                                                    #
# --------------------------------------------------------------------------- #


def test_format_errors_empty() -> None:
    assert format_errors([]) == ""


def test_format_errors_nested_additional_property(schema: dict) -> None:
    finding = _minimal_finding(some_unknown_subfield="x")
    envelope = _minimal_valid_envelope() | {"findings": [finding]}
    errors = validate_envelope(envelope, schema)
    output = format_errors(errors)
    assert "some_unknown_subfield" in output
    assert "/findings/0" in output


def test_format_errors_path_pointer(schema: dict) -> None:
    envelope = _minimal_valid_envelope() | {"status": "Pass"}
    output = format_errors(validate_envelope(envelope, schema))
    assert "/status" in output


def test_format_errors_includes_envelope_path(schema: dict) -> None:
    envelope = _minimal_valid_envelope() | {"next_action": "retry"}
    errors = validate_envelope(envelope, schema)
    out = format_errors(errors, envelope_path=pathlib.Path("/tmp/bad.yaml"))
    assert "envelope: /tmp/bad.yaml" in out


def test_format_errors_not_clause_only() -> None:
    """Synthetic schema with `not` but no additionalProperties — verifies the
    fallback "forbidden flow-policy field present" message path."""
    schema = {
        "type": "object",
        "required": ["status"],
        "properties": {"status": {"type": "string"}},
        "not": {"required": ["next_action"]},
    }
    errors = validate_envelope(
        {"status": "pass", "next_action": "retry"}, schema
    )
    output = format_errors(errors)
    assert "forbidden flow-policy field present" in output


# --------------------------------------------------------------------------- #
# validate_file / load_schema edge cases                                      #
# --------------------------------------------------------------------------- #


def test_validate_file_non_mapping(tmp_path: pathlib.Path, schema: dict) -> None:
    bad = tmp_path / "not-a-mapping.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    errors = validate_file(bad, schema)
    assert errors
    assert "not parse to a YAML mapping" in errors[0].message


def test_load_schema_non_mapping(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "not-a-schema.yaml"
    bad.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    from jsonschema.exceptions import SchemaError

    with pytest.raises(SchemaError):
        load_schema(bad)


def test_load_schema_malformed(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "broken.yaml"
    # additionalProperties must be a boolean or schema, not an int.
    bad.write_text(
        "$schema: 'https://json-schema.org/draft/2020-12/schema'\n"
        "type: object\n"
        "additionalProperties: 17\n",
        encoding="utf-8",
    )
    from jsonschema.exceptions import SchemaError

    with pytest.raises(SchemaError):
        load_schema(bad)


def test_find_repo_root_no_ancestor(tmp_path: pathlib.Path) -> None:
    leaf = tmp_path / "deep" / "leaf"
    leaf.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="could not locate repo root"):
        find_repo_root(leaf)


def test_find_repo_root_locates_dot_github(tmp_path: pathlib.Path) -> None:
    fake_root = tmp_path / "fake-repo"
    (fake_root / ".github").mkdir(parents=True)
    (fake_root / "tools" / "deep").mkdir(parents=True)
    assert find_repo_root(fake_root / "tools" / "deep") == fake_root


# --------------------------------------------------------------------------- #
# CLI behavior                                                                #
# --------------------------------------------------------------------------- #


def test_cli_no_envelopes_returns_zero() -> None:
    assert main(["--schema", str(SCHEMA_PATH)]) == 0


def test_cli_require_nonempty_with_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--schema", str(SCHEMA_PATH), "--require-nonempty"])
    assert rc == 2
    assert "no envelopes provided" in capsys.readouterr().err


def test_cli_default_schema_path_resolves() -> None:
    """Without --schema, the validator resolves <repo-root>/schemas/envelope.schema.yaml."""
    assert main([]) == 0


def test_cli_valid_envelope_returns_zero() -> None:
    assert main(["--schema", str(SCHEMA_PATH), str(DEV_PASS_ENVELOPE_PATH)]) == 0


def test_cli_forbidden_field_returns_one(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent(
            """\
            status: pass
            artifacts: []
            findings: []
            rationale: ok
            next_action: retry
            """
        ),
        encoding="utf-8",
    )
    rc = main(["--schema", str(SCHEMA_PATH), str(bad)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "forbidden flow-policy field: next_action" in out


def test_cli_malformed_schema_returns_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad_schema = tmp_path / "bad-schema.yaml"
    bad_schema.write_text(": not yaml\n", encoding="utf-8")
    rc = main(["--schema", str(bad_schema), str(DEV_PASS_ENVELOPE_PATH)])
    assert rc == 2
    assert "schema" in capsys.readouterr().err.lower()


def test_cli_unreadable_schema_returns_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        ["--schema", str(tmp_path / "does-not-exist.yaml"), str(DEV_PASS_ENVELOPE_PATH)]
    )
    assert rc == 2
    assert "schema" in capsys.readouterr().err.lower()


def test_cli_envelope_unreadable_returns_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        ["--schema", str(SCHEMA_PATH), str(tmp_path / "missing-envelope.yaml")]
    )
    assert rc == 2
    assert "envelope" in capsys.readouterr().err.lower()


def test_cli_envelope_yaml_parse_failure_returns_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "broken.yaml"
    bad.write_text("status: pass\n  bad: indentation\nfoo:\n   - : :\n", encoding="utf-8")
    rc = main(["--schema", str(SCHEMA_PATH), str(bad)])
    assert rc == 2
    assert "envelope" in capsys.readouterr().err.lower()


def test_cli_invalid_then_valid_still_returns_one(
    tmp_path: pathlib.Path,
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "status: passed\nartifacts: []\nfindings: []\nrationale: x\n",
        encoding="utf-8",
    )
    rc = main(
        [
            "--schema",
            str(SCHEMA_PATH),
            str(DEV_PASS_ENVELOPE_PATH),
            str(bad),
        ]
    )
    assert rc == 1
