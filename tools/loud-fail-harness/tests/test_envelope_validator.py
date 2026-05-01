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

Negative-path — AC-assertion-evidence triple invariant (FR19; Story 4.7):
    [x] passing AC with empty `assertions` rejected              → test_ac_triple_pass_empty_assertions_rejected
    [x] passing AC with empty `evidence_refs` rejected           → test_ac_triple_pass_empty_evidence_refs_rejected
    [x] passing AC with both arrays empty: 2 errors              → test_ac_triple_pass_both_empty_rejected
    [x] failing/blocked AC with empty arrays accepted            → test_ac_triple_failing_empty_arrays_accepted
    [x] failing AC with assertions + evidence accepted           → test_ac_triple_failing_with_evidence_accepted
    [x] existing qa-*.yaml fixtures validate clean post-bump     → test_existing_corpus_qa_fixtures_validate_clean
    [x] CLI exit 1 for passing AC with empty assertions (AC-2)  → test_cli_triple_invariant_pass_empty_assertions_exits_one
    [x] CLI exit 0 for fail/blocked AC with empty arrays (AC-5) → test_cli_triple_invariant_failing_empty_arrays_exits_zero

format_errors AC-id resolution (Story 4.7):
    [x] minItems on ac_results triggers FR19 diagnostic line     → test_format_errors_renames_ac_triple_minitems
    [x] envelope kwarg resolves ac_id literal in diagnostic      → test_format_errors_resolves_ac_id_when_envelope_passed
    [x] non-minItems errors not mangled by FR19 rewrite          → test_format_errors_does_not_mangle_non_minitems_errors
    [x] AC-id resolution is defensive on missing/odd shapes      → test_format_errors_resilient_to_missing_ac_results_lookup
    [x] envelope_validator.py contains no CR characters          → test_lf_line_endings_envelope_validator
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



def _minimal_qa_envelope(
    ac_status: str = "pass",
    assertions: tuple[str, ...] = ("login button visible",),
    evidence_refs: tuple[str, ...] = ("evidence/screen-001.png",),
    ac_id: str = "AC-1",
) -> dict:
    """Return a minimal valid QA envelope with one parametrizable `ac_results` entry.

    The default-argument tuples are immutable (no mutable-default-argument
    pitfall). Tests pass `()` explicitly to construct empty-array shapes that
    exercise the AC-assertion-evidence triple invariant (Story 4.7).
    """
    return _minimal_valid_envelope() | {
        "ac_results": [
            {
                "ac_id": ac_id,
                "status": ac_status,
                "assertions": list(assertions),
                "evidence_refs": list(evidence_refs),
                "semantic_verification": {"checked_by": "playwright"},
            }
        ],
    }


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



# --------------------------------------------------------------------------- #
# Negative-path: AC-assertion-evidence triple invariant (FR19; Story 4.7)     #
# --------------------------------------------------------------------------- #


def test_ac_triple_pass_empty_assertions_rejected(schema: dict) -> None:
    """A passing AC with an empty `assertions` array fires the FR19 conditional."""
    envelope = _minimal_qa_envelope(
        ac_status="pass", assertions=(), evidence_refs=("e/1.png",)
    )
    errors = validate_envelope(envelope, schema)
    minitems_errors = [
        e
        for e in errors
        if e.validator == "minItems"
        and list(e.absolute_path) == ["ac_results", 0, "assertions"]
    ]
    assert len(minitems_errors) == 1, (
        f"expected exactly one minItems error at ac_results[0]/assertions; got: "
        f"{[(e.validator, list(e.absolute_path), e.message) for e in errors]}"
    )
    assert any(phrase in minitems_errors[0].message for phrase in ("too short", "non-empty")), (
        f"expected minItems diagnostic in message; got: {minitems_errors[0].message!r}"
    )


def test_ac_triple_pass_empty_evidence_refs_rejected(schema: dict) -> None:
    """A passing AC with an empty `evidence_refs` array fires the FR19 conditional."""
    envelope = _minimal_qa_envelope(
        ac_status="pass", assertions=("a",), evidence_refs=()
    )
    errors = validate_envelope(envelope, schema)
    minitems_errors = [
        e
        for e in errors
        if e.validator == "minItems"
        and list(e.absolute_path) == ["ac_results", 0, "evidence_refs"]
    ]
    assert len(minitems_errors) == 1, (
        f"expected exactly one minItems error at ac_results[0]/evidence_refs; got: "
        f"{[(e.validator, list(e.absolute_path), e.message) for e in errors]}"
    )
    assert any(phrase in minitems_errors[0].message for phrase in ("too short", "non-empty")), (
        f"expected minItems diagnostic in message; got: {minitems_errors[0].message!r}"
    )


def test_ac_triple_pass_both_empty_rejected(schema: dict) -> None:
    """A passing AC with BOTH arrays empty surfaces both gaps in one validation pass."""
    envelope = _minimal_qa_envelope(
        ac_status="pass", assertions=(), evidence_refs=()
    )
    errors = validate_envelope(envelope, schema)
    triple_signature = {
        (list(e.absolute_path)[-1], e.validator)
        for e in errors
        if e.validator == "minItems"
        and len(list(e.absolute_path)) == 3
        and list(e.absolute_path)[0] == "ac_results"
    }
    assert ("assertions", "minItems") in triple_signature, (
        f"expected `assertions` minItems error; saw: {triple_signature}"
    )
    assert ("evidence_refs", "minItems") in triple_signature, (
        f"expected `evidence_refs` minItems error; saw: {triple_signature}"
    )

    # Diagnostic surface: format_errors mentions BOTH array names AND the
    # invariant text so the FR19 rewrite branch is confirmed to have fired (AC-4).
    output = format_errors(errors)
    assert "AC-assertion-evidence triple invariant" in output, (
        f"expected FR19 invariant text in format_errors output; got: {output!r}"
    )
    assert "`assertions`" in output and "`evidence_refs`" in output


@pytest.mark.parametrize("status", ["fail", "blocked"])
def test_ac_triple_failing_empty_arrays_accepted(schema: dict, status: str) -> None:
    """The triple invariant applies ONLY to status==pass; failing/blocked permit empty arrays."""
    envelope = _minimal_qa_envelope(
        ac_status=status, assertions=(), evidence_refs=()
    )
    assert validate_envelope(envelope, schema) == [], (
        f"status={status!r} with empty assertions/evidence_refs must validate clean"
    )


def test_ac_triple_failing_with_evidence_accepted(schema: dict) -> None:
    """A failing AC PERMITS assertions + evidence — the invariant is one-way."""
    envelope = _minimal_qa_envelope(
        ac_status="fail", assertions=("a",), evidence_refs=("e",)
    )
    assert validate_envelope(envelope, schema) == []


def test_existing_corpus_qa_fixtures_validate_clean(schema: dict) -> None:
    """Regression guard: every existing qa-*.yaml fixture validates under the bumped schema."""
    qa_fixtures = sorted((REPO_ROOT / "examples" / "envelopes").glob("qa-*.yaml"))
    assert qa_fixtures, "no qa-*.yaml fixtures discovered — corpus inspection broke"
    for fixture in qa_fixtures:
        errors = validate_file(fixture, schema)
        assert errors == [], (
            f"fixture {fixture.name} regressed under FR19 triple invariant: "
            f"{format_errors(errors)}"
        )


# --------------------------------------------------------------------------- #
# format_errors — AC-id resolution + diagnostic refinement (Story 4.7)        #
# --------------------------------------------------------------------------- #


def test_format_errors_renames_ac_triple_minitems(schema: dict) -> None:
    """The FR19 rewrite renames the diagnostic and includes the array name."""
    envelope = _minimal_qa_envelope(
        ac_status="pass", assertions=(), evidence_refs=("e",)
    )
    errors = validate_envelope(envelope, schema)
    output = format_errors(errors, envelope_path=pathlib.Path("/tmp/x.yaml"))
    assert "AC-assertion-evidence triple invariant" in output
    assert "`assertions`" in output
    # Either bare-index form OR resolved AC-id is acceptable here (AC-7);
    # the AC-id-resolution path is exercised independently below.
    assert "ac_results[0]" in output or "AC-1" in output


def test_format_errors_resolves_ac_id_when_envelope_passed(schema: dict) -> None:
    """Passing the envelope through enables AC-id resolution in the diagnostic."""
    envelope = _minimal_qa_envelope(
        ac_status="pass", assertions=(), evidence_refs=("e",), ac_id="AC-7"
    )
    errors = validate_envelope(envelope, schema)
    output = format_errors(
        errors,
        envelope_path=pathlib.Path("/tmp/x.yaml"),
        envelope=envelope,
    )
    assert "AC-7" in output, (
        f"expected resolved AC-id 'AC-7' in diagnostic; got: {output!r}"
    )
    # The bare index form must NOT leak through when resolution succeeds.
    assert "ac_results[0]" not in output


def test_format_errors_does_not_mangle_non_minitems_errors(schema: dict) -> None:
    """The FR19 rewrite is path-conditional; existing additionalProperties output is byte-identical."""
    envelope = _minimal_valid_envelope() | {"unknown_field": "x"}
    output = format_errors(validate_envelope(envelope, schema))
    assert "additional property 'unknown_field' not allowed" in output


def test_format_errors_resilient_to_missing_ac_results_lookup(schema: dict) -> None:
    """Defensive fallback: any structural mismatch falls back to index form without raising."""
    envelope = _minimal_qa_envelope(
        ac_status="pass", assertions=(), evidence_refs=("e",)
    )
    errors = validate_envelope(envelope, schema)

    # Case A: envelope=None → index form.
    out_none = format_errors(errors, envelope=None)
    assert "ac_results[0]" in out_none

    # Case B: envelope is empty dict (missing `ac_results`) → falls back without raising.
    out_empty = format_errors(errors, envelope={})
    assert "ac_results[0]" in out_empty

    # Case C: index out of range → falls back without raising.
    out_oob = format_errors(errors, envelope={"ac_results": []})
    assert "ac_results[0]" in out_oob


def test_lf_line_endings_envelope_validator() -> None:
    """The modified envelope_validator.py contains no CR characters (LF discipline)."""
    module_path = (
        REPO_ROOT
        / "tools"
        / "loud-fail-harness"
        / "src"
        / "loud_fail_harness"
        / "envelope_validator.py"
    )
    raw = module_path.read_bytes()
    assert b"\r" not in raw, (
        "envelope_validator.py contains CR characters; expected pure LF endings"
    )


# --------------------------------------------------------------------------- #
# CLI exit-code verification — AC-triple invariant (AC-2 / AC-3 / AC-5)       #
# --------------------------------------------------------------------------- #


def test_cli_triple_invariant_pass_empty_assertions_exits_one(
    tmp_path: pathlib.Path,
) -> None:
    """CLI returns exit 1 when a passing AC has an empty `assertions` array (AC-2)."""
    envelope_file = tmp_path / "qa-triple-fail.yaml"
    envelope_file.write_text(
        textwrap.dedent("""\
            status: pass
            artifacts:
              - src/foo.py
            findings: []
            rationale: all green
            ac_results:
              - ac_id: AC-1
                status: pass
                assertions: []
                evidence_refs:
                  - evidence/screen-001.png
                semantic_verification:
                  checked_by: playwright
        """),
        encoding="utf-8",
    )
    rc = main(["--schema", str(SCHEMA_PATH), str(envelope_file)])
    assert rc == 1, f"expected exit 1 for passing AC with empty assertions; got {rc}"


def test_cli_triple_invariant_failing_empty_arrays_exits_zero(
    tmp_path: pathlib.Path,
) -> None:
    """CLI returns exit 0 for fail/blocked ACs with empty arrays — invariant is one-way (AC-5)."""
    for ac_status in ("fail", "blocked"):
        envelope_file = tmp_path / f"qa-{ac_status}-empty.yaml"
        envelope_file.write_text(
            textwrap.dedent(f"""\
                status: pass
                artifacts:
                  - src/foo.py
                findings: []
                rationale: all green
                ac_results:
                  - ac_id: AC-1
                    status: {ac_status}
                    assertions: []
                    evidence_refs: []
                    semantic_verification:
                      checked_by: playwright
            """),
            encoding="utf-8",
        )
        rc = main(["--schema", str(SCHEMA_PATH), str(envelope_file)])
        assert rc == 0, (
            f"expected exit 0 for {ac_status!r} AC with empty arrays; got {rc}"
        )
