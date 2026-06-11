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
    [x] Review-LAD: ``source: "lad"`` finding accepted           → test_specialist_source_lad

Negative-path — Pattern 1 / closed-enumeration discipline:
    [x] ``status`` value ``Pass`` (capitalized) rejected         → test_enum_violation_status_capitalized
    [x] ``status`` value ``passed`` (extra suffix) rejected      → test_enum_violation_status_passed
    [x] unknown ``bucket`` value rejected                        → test_enum_violation_bucket_unknown
    [x] unknown ``severity`` value (e.g. ``Critical``) rejected  → test_enum_violation_severity_unknown

Schema self-check:
    [x] schemas/envelope.schema.yaml meta-validates              → test_schema_meta_validates

Canonical positive envelope (AC-3 dependency):
    [x] examples/envelopes/dev-pass.yaml validates clean             → test_canonical_dev_pass_envelope_validates
    [x] examples/envelopes/review-lad-pass.yaml validates clean      → test_canonical_lad_pass_envelope_validates

Canonical negative envelope (Phase 1.5 / Story 10.3):
    [x] examples/envelopes/review-lad-fail-shape.yaml rejected (bucket enum) → test_canonical_lad_fail_shape_envelope_rejected
    [x] CLI exit 1 on review-lad-fail-shape.yaml                             → test_cli_lad_fail_shape_envelope_exits_one

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

Negative-path — three-tier evidence hierarchy + semantic_verification enum (FR20 + FR21; Story 4.8):
    [x] string-form evidence_refs item rejected (type)           → test_evidence_refs_pre_bump_string_form_rejected
    [x] object-form item with valid tier accepted (parametrized) → test_evidence_refs_object_form_with_valid_tier_accepted
    [x] unknown tier value rejected (enum)                       → test_evidence_refs_object_form_unknown_tier_rejected
    [x] extra property in evidence_ref rejected                  → test_evidence_refs_object_form_extra_property_rejected
    [x] missing path in evidence_ref rejected                    → test_evidence_refs_object_form_missing_path_rejected
    [x] semantic_verification "required" string rejected (enum)  → test_semantic_verification_pre_bump_required_string_rejected
    [x] semantic_verification object form rejected (type)        → test_semantic_verification_pre_bump_object_form_rejected
    [x] three valid semantic_verification values accepted        → test_semantic_verification_three_valid_enum_values_accepted
    [x] format_errors renames tier-enum violation                → test_format_errors_renames_tier_enum_violation
    [x] format_errors renames semantic_verification enum         → test_format_errors_renames_semantic_verification_enum_violation
    [x] format_errors does not mangle unrelated enum errors      → test_format_errors_does_not_mangle_non_evidence_ref_enum_errors
    [x] migrated qa-*.yaml fixtures validate clean post-Story-4.8 → test_existing_corpus_qa_fixtures_validate_clean (in-place updated)

Negative-path — exploratory-heuristic discriminator + heuristic_skipped_emissions field (FR22; Story 4.9):
    [x] finding `verification_mode: "speculative-mutation"` rejected → test_finding_verification_mode_unknown_value_rejected
    [x] finding `verification_mode: "exploratory-heuristic"` accepted → test_finding_verification_mode_exploratory_heuristic_accepted
    [x] finding without `verification_mode` accepted (optional)      → test_finding_verification_mode_absent_accepted
    [x] format_errors renames verification_mode enum violation       → test_format_errors_renames_verification_mode_enum_violation
    [x] heuristic_skipped_emissions valid entry accepted (parametrized) → test_heuristic_skipped_emissions_array_with_valid_entry_accepted
    [x] heuristic_skipped_emissions unknown sub_classification rejected → test_heuristic_skipped_emissions_unknown_sub_classification_rejected
    [x] heuristic_skipped_emissions missing required field rejected  → test_heuristic_skipped_emissions_missing_required_field_rejected
    [x] heuristic_skipped_emissions extra property rejected          → test_heuristic_skipped_emissions_extra_property_rejected
    [x] heuristic_skipped_emissions field absent accepted (optional) → test_heuristic_skipped_emissions_field_absent_accepted
    [x] format_errors does not mangle unrelated verification_mode-adjacent enum errors → test_format_errors_does_not_mangle_non_verification_mode_enum_errors
    [x] post-Story-4.9 corpus regression-guard                       → test_existing_corpus_qa_fixtures_validate_clean_post_bump
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
LAD_PASS_ENVELOPE_PATH = REPO_ROOT / "examples" / "envelopes" / "review-lad-pass.yaml"
LAD_FAIL_SHAPE_ENVELOPE_PATH = (
    REPO_ROOT / "examples" / "envelopes" / "review-lad-fail-shape.yaml"
)


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
    evidence_refs: tuple = ("evidence/screen-001.png",),
    ac_id: str = "AC-1",
    semantic_verification: object = "not_applicable",
) -> dict:
    """Return a minimal valid QA envelope with one parametrizable `ac_results` entry.

    The default-argument tuples are immutable (no mutable-default-argument
    pitfall). Tests pass `()` explicitly to construct empty-array shapes that
    exercise the AC-assertion-evidence triple invariant (Story 4.7).

    Story 4.8: ``evidence_refs`` items are auto-wrapped to the bumped
    object form ``{path, tier: tier-1-mechanical}`` when callers pass
    string-form items (the pre-Story-4.8 convention); pre-bumped object-
    form items pass through verbatim. ``semantic_verification`` defaults
    to ``"not_applicable"`` (the bumped FR21 closed-enum value) instead
    of the previously-permitted-by-the-loose-``oneOf`` object form.
    """
    refs: list[object] = []
    for r in evidence_refs:
        if isinstance(r, str):
            refs.append({"path": r, "tier": "tier-1-mechanical"})
        else:
            refs.append(r)
    return _minimal_valid_envelope() | {
        "ac_results": [
            {
                "ac_id": ac_id,
                "status": ac_status,
                "assertions": list(assertions),
                "evidence_refs": refs,
                "semantic_verification": semantic_verification,
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


def test_canonical_lad_pass_envelope_validates(schema: dict) -> None:
    errors = validate_file(LAD_PASS_ENVELOPE_PATH, schema)
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
                "evidence_refs": [
                    {"path": "evidence/screen-001.png", "tier": "tier-1-mechanical"}
                ],
                "semantic_verification": "not_applicable",
            }
        ],
    }
    assert validate_envelope(envelope, schema) == []


def test_specialist_extension_review_bmad(schema: dict) -> None:
    envelope = _minimal_valid_envelope() | {
        "failed_layers": ["blind", "edge"],
    }
    assert validate_envelope(envelope, schema) == []


def test_specialist_source_lad(schema: dict) -> None:
    """Defense-in-depth: confirm the `$defs/finding.source` enum genuinely
    admits `lad` at runtime (Phase 1 reserved the value; Story 10.3 confirms
    reservation is honoured)."""
    finding = _minimal_finding(source="lad")
    envelope = _minimal_valid_envelope() | {"findings": [finding]}
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
    """Regression guard: every existing qa-*.yaml fixture validates under the bumped schema.

    Story 4.7 baseline: passing-AC entries have non-empty assertions +
    evidence_refs (FR19 triple invariant).

    Story 4.8 extension (in-place update): the corpus has been migrated
    from string-form ``evidence_refs`` items to the bumped object form
    ``{path, tier: tier-1-mechanical}`` for every ``qa-*.yaml`` fixture
    (12 fixtures total post-migration; 11 migrated + 1 new
    ``qa-pass-tier-3-not-configured.yaml``). Any fixture whose
    evidence_refs were not migrated would regress here LOUDLY.
    """
    qa_fixtures = sorted((REPO_ROOT / "examples" / "envelopes").glob("qa-*.yaml"))
    assert qa_fixtures, "no qa-*.yaml fixtures discovered — corpus inspection broke"
    for fixture in qa_fixtures:
        errors = validate_file(fixture, schema)
        assert errors == [], (
            f"fixture {fixture.name} regressed under FR19 + FR20 + FR21 invariants: "
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
                  - path: evidence/screen-001.png
                    tier: tier-1-mechanical
                semantic_verification: not_applicable
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
                    semantic_verification: not_applicable
            """),
            encoding="utf-8",
        )
        rc = main(["--schema", str(SCHEMA_PATH), str(envelope_file)])
        assert rc == 0, (
            f"expected exit 0 for {ac_status!r} AC with empty arrays; got {rc}"
        )


# --------------------------------------------------------------------------- #
# Negative-path: three-tier evidence hierarchy + semantic_verification enum   #
# (FR20 + FR21; Story 4.8)                                                    #
# --------------------------------------------------------------------------- #


def test_evidence_refs_pre_bump_string_form_rejected(schema: dict) -> None:
    """Pre-Story-4.8 string-form evidence_refs items are rejected by
    the bumped schema's ``$defs/evidence_ref`` `$ref` (item type must
    be object, not string).
    """
    envelope = _minimal_valid_envelope() | {
        "ac_results": [
            {
                "ac_id": "AC-1",
                "status": "pass",
                "assertions": ["a"],
                "evidence_refs": ["x.txt"],  # pre-bump string form
                "semantic_verification": "not_applicable",
            }
        ],
    }
    errors = validate_envelope(envelope, schema)
    type_errors = [
        e
        for e in errors
        if e.validator == "type"
        and list(e.absolute_path) == ["ac_results", 0, "evidence_refs", 0]
    ]
    assert type_errors, (
        f"expected a type ValidationError at ac_results[0].evidence_refs[0]; "
        f"got: {[(e.validator, list(e.absolute_path)) for e in errors]}"
    )


@pytest.mark.parametrize(
    "tier",
    ["tier-1-mechanical", "tier-2-outcome", "tier-3-semantic"],
)
def test_evidence_refs_object_form_with_valid_tier_accepted(
    schema: dict, tier: str
) -> None:
    """Object-form evidence_refs items with valid tier values pass
    schema validation."""
    envelope = _minimal_qa_envelope(
        ac_status="pass",
        evidence_refs=({"path": "evidence/x.txt", "tier": tier},),
    )
    assert validate_envelope(envelope, schema) == []


def test_evidence_refs_object_form_unknown_tier_rejected(schema: dict) -> None:
    """Out-of-enum tier values produce an enum violation at
    ac_results[0].evidence_refs[0].tier."""
    envelope = _minimal_qa_envelope(
        ac_status="pass",
        evidence_refs=(
            {"path": "x.txt", "tier": "tier-4-formal-proof"},
        ),
    )
    errors = validate_envelope(envelope, schema)
    enum_errors = [
        e
        for e in errors
        if e.validator == "enum"
        and list(e.absolute_path)
        == ["ac_results", 0, "evidence_refs", 0, "tier"]
    ]
    assert len(enum_errors) == 1, (
        f"expected exactly one enum violation at evidence_refs[0].tier; "
        f"got: {[(e.validator, list(e.absolute_path)) for e in errors]}"
    )


def test_evidence_refs_object_form_extra_property_rejected(
    schema: dict,
) -> None:
    """``additionalProperties: false`` on $defs/evidence_ref rejects
    extra keys."""
    envelope = _minimal_qa_envelope(
        ac_status="pass",
        evidence_refs=(
            {"path": "x.txt", "tier": "tier-1-mechanical", "notes": "extra"},
        ),
    )
    errors = validate_envelope(envelope, schema)
    extra_errors = [e for e in errors if e.validator == "additionalProperties"]
    assert extra_errors, (
        f"expected additionalProperties violation; "
        f"got: {[(e.validator, list(e.absolute_path)) for e in errors]}"
    )


def test_evidence_refs_object_form_missing_path_rejected(schema: dict) -> None:
    """``required: [path, tier]`` on $defs/evidence_ref rejects items
    missing ``path``."""
    envelope = _minimal_qa_envelope(
        ac_status="pass",
        evidence_refs=({"tier": "tier-1-mechanical"},),
    )
    errors = validate_envelope(envelope, schema)
    required_errors = [
        e
        for e in errors
        if e.validator == "required" and "path" in e.message
    ]
    assert required_errors, (
        f"expected a required-field validation error naming 'path'; "
        f"got: {[(e.validator, e.message) for e in errors]}"
    )


def test_semantic_verification_pre_bump_required_string_rejected(
    schema: dict,
) -> None:
    """The literal ``"required"`` (the PLAN-side value the loose pre-
    bump ``oneOf: [object, string]`` permitted) is REJECTED by the
    bumped closed string enum — ``required`` is intentionally absent
    from the result-side enum.
    """
    envelope = _minimal_qa_envelope(
        ac_status="pass",
        semantic_verification="required",
    )
    errors = validate_envelope(envelope, schema)
    enum_errors = [
        e
        for e in errors
        if e.validator == "enum"
        and list(e.absolute_path) == ["ac_results", 0, "semantic_verification"]
    ]
    assert len(enum_errors) == 1, (
        f"expected exactly one enum violation at semantic_verification; "
        f"got: {[(e.validator, list(e.absolute_path)) for e in errors]}"
    )


def test_semantic_verification_pre_bump_object_form_rejected(
    schema: dict,
) -> None:
    """Object-form ``semantic_verification`` (the previously-permitted-
    by-the-loose-``oneOf`` shape that the bumped enum REJECTS)
    produces a ``type`` violation. The forward-pointer prose drift in
    ``agents/qa.md`` is documented in this story's Completion Notes.
    """
    envelope = _minimal_qa_envelope(
        ac_status="pass",
        semantic_verification={"tier": 3, "status": "configured"},
    )
    errors = validate_envelope(envelope, schema)
    type_errors = [
        e
        for e in errors
        if e.validator == "type"
        and list(e.absolute_path) == ["ac_results", 0, "semantic_verification"]
    ]
    assert type_errors, (
        f"expected a type ValidationError at semantic_verification; "
        f"got: {[(e.validator, list(e.absolute_path)) for e in errors]}"
    )


@pytest.mark.parametrize(
    "value", ["verified", "not_configured", "not_applicable"]
)
def test_semantic_verification_three_valid_enum_values_accepted(
    schema: dict, value: str
) -> None:
    """Each of the three FR21-canonical result-side values validates
    cleanly."""
    envelope = _minimal_qa_envelope(
        ac_status="pass",
        semantic_verification=value,
    )
    assert validate_envelope(envelope, schema) == []


def test_format_errors_renames_tier_enum_violation(schema: dict) -> None:
    """The Story 4.8 ``format_errors`` rewrite branch (a) renames
    tier-enum violations and resolves the AC-id when ``envelope`` is
    passed (mirrors Story 4.7 AC-id resolution)."""
    envelope = _minimal_qa_envelope(
        ac_status="pass",
        evidence_refs=(
            {"path": "x.txt", "tier": "tier-4-formal-proof"},
        ),
    )
    errors = validate_envelope(envelope, schema)
    output = format_errors(errors, envelope=envelope)
    assert "three-tier evidence hierarchy invariant" in output, (
        f"expected FR20 invariant text in format_errors output; got: {output!r}"
    )
    assert "tier must be one of" in output
    assert "AC-1" in output
    # Bare-index form must NOT leak through when AC-id resolution succeeds.
    assert "ac_results[0]" not in output


def test_format_errors_renames_semantic_verification_enum_violation(
    schema: dict,
) -> None:
    """The Story 4.8 ``format_errors`` rewrite branch (b) renames
    semantic_verification-enum violations and resolves the AC-id."""
    envelope = _minimal_qa_envelope(
        ac_status="pass",
        semantic_verification="required",
    )
    errors = validate_envelope(envelope, schema)
    output = format_errors(errors, envelope=envelope)
    assert "three-tier evidence hierarchy invariant" in output
    assert "semantic_verification must be one of" in output
    assert "AC-1" in output


def test_format_errors_does_not_mangle_non_evidence_ref_enum_errors(
    schema: dict,
) -> None:
    """The path-conditional rewrites added by Story 4.8 (AC-8) MUST
    NOT clobber unrelated enum errors. Feeds an envelope with a
    top-level ``status`` enum violation and asserts the standard
    diagnostic phrasing survives.
    """
    envelope = _minimal_valid_envelope() | {"status": "halfpass"}
    errors = validate_envelope(envelope, schema)
    output = format_errors(errors, envelope=envelope)
    # The Story 4.8 rewrite branches are scoped to ac_results paths;
    # this top-level status-enum error must keep its standard surface.
    assert "three-tier evidence hierarchy invariant" not in output, (
        f"FR20/FR21 rewrite leaked onto unrelated enum error; got: {output!r}"
    )
    assert "/status" in output, f"Expected /status pointer; got: {output!r}"
    assert "halfpass" in output, f"Expected 'halfpass' value in output; got: {output!r}"
    assert "is not one of" in output, f"Expected enum-violation phrasing; got: {output!r}"


# --------------------------------------------------------------------------- #
# Negative-path — exploratory-heuristic discriminator + heuristic_skipped     #
# emissions (FR22; Story 4.9)                                                 #
# --------------------------------------------------------------------------- #


def _heuristic_finding(**overrides: object) -> dict:
    base = {
        "id": "qa-heuristic-empty-001",
        "source": "qa",
        "title": "empty list view renders generic placeholder",
        "detail": "exploratory observation",
        "location": "src/components/list-view.tsx:42",
        "bucket": "decision_needed",
        "severity": "MED",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "bad_value", ["speculative-mutation", "manual", "automated", ""]
)
def test_finding_verification_mode_unknown_value_rejected(
    schema: dict, bad_value: str
) -> None:
    envelope = _minimal_valid_envelope()
    envelope["findings"] = [_heuristic_finding(verification_mode=bad_value)]
    errors = validate_envelope(envelope, schema)
    enum_errors = [
        e for e in errors
        if e.validator == "enum"
        and list(e.absolute_path) == ["findings", 0, "verification_mode"]
    ]
    assert len(enum_errors) == 1, (
        f"expected one enum violation at findings[0].verification_mode; got {errors}"
    )


def test_finding_verification_mode_exploratory_heuristic_accepted(schema: dict) -> None:
    envelope = _minimal_valid_envelope()
    envelope["findings"] = [
        _heuristic_finding(verification_mode="exploratory-heuristic")
    ]
    assert validate_envelope(envelope, schema) == []


def test_finding_verification_mode_absent_accepted(schema: dict) -> None:
    envelope = _minimal_valid_envelope()
    envelope["findings"] = [_heuristic_finding()]
    assert validate_envelope(envelope, schema) == []


def test_format_errors_renames_verification_mode_enum_violation(schema: dict) -> None:
    envelope = _minimal_valid_envelope()
    envelope["findings"] = [
        _heuristic_finding(verification_mode="speculative-mutation")
    ]
    errors = validate_envelope(envelope, schema)
    output = format_errors(errors, envelope=envelope)
    assert "exploratory-heuristic discriminator invariant" in output, output
    assert 'verification_mode must be "exploratory-heuristic"' in output, output
    assert "qa-heuristic-empty-001" in output, output


@pytest.mark.parametrize(
    "sub_classification",
    [
        "empty-state",
        "error-state",
        "auth-boundary",
        "rate-limit-boundary",
        "locale-i18n-edge",
        "large-input-boundary",
        "permission-boundary",
    ],
)
def test_heuristic_skipped_emissions_array_with_valid_entry_accepted(
    schema: dict, sub_classification: str
) -> None:
    envelope = _minimal_valid_envelope()
    envelope["heuristic_skipped_emissions"] = [
        {
            "marker_class": "heuristic-skipped",
            "sub_classification": sub_classification,
            "story_id": "auto-001",
        }
    ]
    assert validate_envelope(envelope, schema) == []


@pytest.mark.parametrize("sub_classification", ["flow-branch", "form-validation"])
def test_heuristic_skipped_emissions_unknown_sub_classification_rejected(
    schema: dict, sub_classification: str
) -> None:
    """The envelope ``heuristic_skipped_emissions`` enum is the EXPLORATORY
    subset (the seven ``HeuristicKind`` values). ``flow-branch`` (FR22c) is NOT
    among them — it routes to the ``AcFlowBranchCoverage`` surface, not here — so
    it is rejected at the envelope seam exactly like a fabricated name."""
    envelope = _minimal_valid_envelope()
    envelope["heuristic_skipped_emissions"] = [
        {
            "marker_class": "heuristic-skipped",
            "sub_classification": sub_classification,
            "story_id": "auto-001",
        }
    ]
    errors = validate_envelope(envelope, schema)
    enum_errors = [
        e for e in errors
        if e.validator == "enum"
        and list(e.absolute_path)
        == ["heuristic_skipped_emissions", 0, "sub_classification"]
    ]
    assert len(enum_errors) == 1, errors


def test_heuristic_skipped_emissions_missing_required_field_rejected(
    schema: dict,
) -> None:
    envelope = _minimal_valid_envelope()
    envelope["heuristic_skipped_emissions"] = [
        {
            "marker_class": "heuristic-skipped",
            "sub_classification": "empty-state",
        }
    ]
    errors = validate_envelope(envelope, schema)
    required_errors = [
        e for e in errors
        if e.validator == "required" and "story_id" in e.message
    ]
    assert required_errors, errors


def test_heuristic_skipped_emissions_extra_property_rejected(schema: dict) -> None:
    envelope = _minimal_valid_envelope()
    envelope["heuristic_skipped_emissions"] = [
        {
            "marker_class": "heuristic-skipped",
            "sub_classification": "empty-state",
            "story_id": "auto-001",
            "extra": "x",
        }
    ]
    errors = validate_envelope(envelope, schema)
    extra_errors = [e for e in errors if e.validator == "additionalProperties"]
    assert extra_errors, errors


def test_heuristic_skipped_emissions_field_absent_accepted(schema: dict) -> None:
    envelope = _minimal_valid_envelope()
    assert "heuristic_skipped_emissions" not in envelope
    assert validate_envelope(envelope, schema) == []


def test_format_errors_does_not_mangle_non_verification_mode_enum_errors(
    schema: dict,
) -> None:
    """The path-conditional rewrite added by Story 4.9 (AC-4) MUST NOT clobber
    existing rewrite-path outputs. Feeds an envelope with a Story 4.8 tier-enum
    violation and asserts the existing tier-enum diagnostic is produced unchanged
    (no regression on the existing rewrite paths — byte-for-byte verification)."""
    envelope = _minimal_qa_envelope(
        ac_status="pass",
        evidence_refs=({"path": "x.txt", "tier": "tier-4-formal-proof"},),
    )
    errors = validate_envelope(envelope, schema)
    output = format_errors(errors, envelope=envelope)
    # Story 4.8 tier-enum rewrite branch MUST still fire with its exact diagnostic.
    assert "three-tier evidence hierarchy invariant" in output, (
        f"expected Story 4.8 tier-enum diagnostic; got: {output!r}"
    )
    assert "tier must be one of" in output
    # Story 4.9 verification_mode branch MUST NOT fire on this path.
    assert "exploratory-heuristic discriminator invariant" not in output, output


def test_existing_corpus_qa_fixtures_validate_clean_post_bump(schema: dict) -> None:
    """Story 4.9 regression guard: every existing qa-*.yaml fixture
    (the pre-Story-4.9 shape — none carry verification_mode on
    findings, none carry heuristic_skipped_emissions) AND the two new
    Story-4.9 fixtures MUST validate cleanly under the bumped schema."""
    qa_fixtures = sorted((REPO_ROOT / "examples" / "envelopes").glob("qa-*.yaml"))
    assert qa_fixtures, "no qa-*.yaml fixtures discovered"
    for fixture in qa_fixtures:
        errors = validate_file(fixture, schema)
        assert errors == [], (
            f"fixture {fixture.name} regressed under Story 4.9 schema bump: "
            f"{format_errors(errors)}"
        )


# --------------------------------------------------------------------------- #
# Canonical negative envelope — Phase 1.5 / Story 10.3                        #
# (per-source-agnostic shape-rule enforcement against a Review-LAD envelope)  #
# --------------------------------------------------------------------------- #


def test_canonical_lad_fail_shape_envelope_rejected(schema: dict) -> None:
    """The failing-shape Review-LAD fixture is rejected with a single
    enum-violation at ``findings[0]/bucket`` (Story 10.3 AC-4). The
    `bucket` enum violation is the per-source-agnostic shape rule the
    fixture exercises; the test asserts the validator's per-source-
    agnostic discipline extends to LAD envelopes the same way it
    extends to Dev / QA / Review-BMAD envelopes."""
    errors = validate_file(LAD_FAIL_SHAPE_ENVELOPE_PATH, schema)
    assert errors, (
        "expected the failing-shape Review-LAD fixture to be rejected; "
        "got an empty error list"
    )
    bucket_enum_errors = [
        e
        for e in errors
        if e.validator == "enum"
        and tuple(e.absolute_path) == ("findings", 0, "bucket")
    ]
    assert bucket_enum_errors, (
        f"expected an enum violation at findings[0]/bucket; got: "
        f"{[(e.validator, list(e.absolute_path)) for e in errors]}"
    )


def test_cli_lad_fail_shape_envelope_exits_one() -> None:
    """CLI returns exit 1 when invoked on the failing-shape Review-LAD
    fixture — proves the CI-runtime gate fails the build at the same
    boundary the Python-API surfaces."""
    rc = main(["--schema", str(SCHEMA_PATH), str(LAD_FAIL_SHAPE_ENVELOPE_PATH)])
    assert rc == 1, (
        f"expected exit 1 on review-lad-fail-shape.yaml; got {rc}"
    )
