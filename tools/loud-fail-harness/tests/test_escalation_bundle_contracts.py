"""Contract-coverage matrix for the two escalation-bundle schema fragments
landed by Story 4.10 — `schemas/escalation-bundles/verification-fail.yaml`
and `schemas/escalation-bundles/env-setup-fail.yaml`.

This docstring IS the contract-coverage checklist. Reviewers verify every
row maps to at least one passing test in this module. The matrix is review-
enforced, NOT CI-enforced (parallel to story 1.5 / 4.7 / 4.8 / 4.9 AC-5).

Schema-validity (verification-fail.yaml):
    [x] schema is a well-formed JSON-Schema-2020-12 document
        → test_verification_fail_contract_is_well_formed_jsonschema_2020_12
    [x] required top-level fields enumerated per AC-2(b)
        → test_verification_fail_contract_carries_required_top_level_fields
    [x] bundle_class.enum == ["verification-fail"] (single-value)
        → test_verification_fail_bundle_class_enum_is_single_value_verification_fail
    [x] retry_policy.enum == ["escalate"] (single-value, FR24a)
        → test_verification_fail_retry_policy_enum_is_single_value_escalate
    [x] failing_ac_result status enum is [fail, blocked] (NOT pass)
        → test_verification_fail_failing_ac_result_status_excludes_pass
    [x] qa_behavioral_plan_pointer.section_heading const is canonical
        → test_verification_fail_qa_behavioral_plan_pointer_section_heading_is_const
    [x] three optional marker_class refs (Tier-3, plan-drift, smoke-first)
        → test_verification_fail_carries_marker_class_references_for_three_markers

Schema-validity (env-setup-fail.yaml):
    [x] schema is a well-formed JSON-Schema-2020-12 document
        → test_env_setup_fail_contract_is_well_formed_jsonschema_2020_12
    [x] required top-level fields enumerated per AC-3(b)
        → test_env_setup_fail_contract_carries_required_top_level_fields
    [x] bundle_class.enum == ["env-setup-fail"] (single-value)
        → test_env_setup_fail_bundle_class_enum_is_single_value_env_setup_fail
    [x] retry_policy.enum == ["escalate-with-env-diagnostic"] (FR24b)
        → test_env_setup_fail_retry_policy_enum_is_single_value_escalate_with_env_diagnostic
    [x] story_state_preservation_note.current_state.const == "review"
        → test_env_setup_fail_story_state_preservation_current_state_is_const_review
    [x] story_state_preservation_note.intended_next_state_skipped == "qa"
        → test_env_setup_fail_story_state_intended_next_state_skipped_is_const_qa
    [x] env_setup_diagnostic.marker_class.const == "env-setup-failed"
        → test_env_setup_fail_carries_marker_class_reference_for_env_setup_failed

Structural-distinctness invariants (cross-contract):
    [x] verification-fail lacks env_setup_diagnostic
        → test_verification_fail_lacks_env_setup_diagnostic_field
    [x] env-setup-fail lacks failing_ac_result (per AC-3(j))
        → test_env_setup_fail_lacks_failing_ac_result_field
    [x] env-setup-fail lacks qa_behavioral_plan_pointer (per AC-3(k))
        → test_env_setup_fail_lacks_qa_behavioral_plan_pointer_field
    [x] both contracts close with additionalProperties: false at top level
        → test_both_contracts_close_with_additional_properties_false_at_top_level
    [x] both contracts have distinct $id URLs
        → test_both_contracts_have_distinct_id_urls

Header-comment integrity:
    [x] verification-fail header names FR24a + Story 4.10
        → test_verification_fail_header_names_FR24a_and_story_4_10
    [x] env-setup-fail header names FR24b + Story 4.10
        → test_env_setup_fail_header_names_FR24b_and_story_4_10
    [x] both contracts header references ADR-002 + cell-1 classification
        → test_both_contracts_header_name_ADR_002_cell_1_classification

Pattern-1 + Pattern-2 conformance:
    [x] verification-fail all structural keys are snake_case
        → test_verification_fail_all_structural_keys_are_snake_case
    [x] env-setup-fail all structural keys are snake_case
        → test_env_setup_fail_all_structural_keys_are_snake_case
    [x] verification-fail marker_class values match canonical taxonomy casing
        (parametrized across Tier-3-not-configured / plan-drift-detected /
        smoke-first-abort)
        → test_verification_fail_marker_class_values_are_kebab_case
    [x] env-setup-fail marker_class value matches canonical taxonomy casing
        (env-setup-failed)
        → test_env_setup_fail_marker_class_value_is_kebab_case

LF line endings (optional):
    [x] verification-fail.yaml uses LF line endings (no CR)
        → test_verification_fail_yaml_uses_LF_line_endings
    [x] env-setup-fail.yaml uses LF line endings (no CR)
        → test_env_setup_fail_yaml_uses_LF_line_endings
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml
from jsonschema import Draft202012Validator

from loud_fail_harness._shared import find_repo_root


REPO_ROOT = find_repo_root()
ESCALATION_BUNDLES_DIR = REPO_ROOT / "schemas" / "escalation-bundles"
VERIFICATION_FAIL_PATH = ESCALATION_BUNDLES_DIR / "verification-fail.yaml"
ENV_SETUP_FAIL_PATH = ESCALATION_BUNDLES_DIR / "env-setup-fail.yaml"

# JSON-Schema-2020-12 reserved keywords + per-property structural keys that
# are NOT user-defined field names. Pattern-1 conformance only validates
# user-defined keys; reserved keywords are exempt by construction.
_JSON_SCHEMA_RESERVED_KEYS: frozenset[str] = frozenset(
    {
        "$schema",
        "$id",
        "$ref",
        "$defs",
        "$comment",
        "$anchor",
        "$dynamicRef",
        "$dynamicAnchor",
        "additionalProperties",
        "additionalItems",
        "unevaluatedItems",
        "unevaluatedProperties",
        "properties",
        "patternProperties",
        "required",
        "items",
        "prefixItems",
        "contains",
        "type",
        "enum",
        "const",
        "description",
        "title",
        "default",
        "examples",
        "format",
        "pattern",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "minProperties",
        "maxProperties",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "uniqueItems",
        "oneOf",
        "anyOf",
        "allOf",
        "if",
        "then",
        "else",
        "not",
        "schema_version",
        # Story-4.10 contract-author convenience: the YAML files use a few
        # JSON-Schema standard keys that aren't user-defined field names but
        # do appear as map keys at validation positions.
        "definitions",
        "deprecated",
        "readOnly",
        "writeOnly",
        "contentEncoding",
        "contentMediaType",
        "contentSchema",
    }
)

_SNAKE_CASE_REGEX = re.compile(r"^[a-z_][a-z0-9_]*$")


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _load_schema(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _walk_user_keys(node: object, path: list[str]) -> list[tuple[str, list[str]]]:
    """Recursively collect every dict key NOT in the JSON-Schema reserved set.

    Returns a list of (key, JSON-pointer-style-path) tuples. Used by Pattern-1
    conformance tests to assert snake_case across user-defined field names.

    The walker treats `properties` as a SPECIAL position: keys directly
    under `/properties/` (or `/$defs/<defname>/properties/`) ARE user-defined
    field names — they MUST conform. Keys directly under `enum: [...]`
    arrays are entity-identifier values (not field names) — they are
    excluded from this collection (validated separately by Pattern-2 tests).
    """
    out: list[tuple[str, list[str]]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            child_path = [*path, str(k)]
            # Detect "is k a user-defined field name?": k is a user-defined
            # field name iff its parent path ends with `properties` AND k
            # is not a JSON-Schema reserved key.
            if path and path[-1] == "properties" and k not in _JSON_SCHEMA_RESERVED_KEYS:
                out.append((str(k), child_path))
            out.extend(_walk_user_keys(v, child_path))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(_walk_user_keys(item, [*path, str(i)]))
    return out


def _collect_marker_class_const_values(node: object, path: list[str]) -> list[tuple[str, list[str]]]:
    """Collect every value at `marker_class.const` positions in the schema.

    Used by Pattern-2 tests to assert canonical-taxonomy casing of marker
    class identifiers referenced via the strict-name `marker_class` rule.
    """
    out: list[tuple[str, list[str]]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            child_path = [*path, str(k)]
            if k == "marker_class" and isinstance(v, dict):
                const_val = v.get("const")
                if isinstance(const_val, str):
                    out.append((const_val, [*child_path, "const"]))
                # Also handle enum-wrapped form (defense-in-depth — the
                # canonical contracts don't use this shape, but a future
                # refactor might).
                enum_val = v.get("enum")
                if isinstance(enum_val, list):
                    for i, item in enumerate(enum_val):
                        if isinstance(item, str):
                            out.append((item, [*child_path, "enum", str(i)]))
            out.extend(_collect_marker_class_const_values(v, child_path))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(_collect_marker_class_const_values(item, [*path, str(i)]))
    return out


# --------------------------------------------------------------------------- #
# Schema-validity (verification-fail.yaml)                                    #
# --------------------------------------------------------------------------- #


def test_verification_fail_contract_is_well_formed_jsonschema_2020_12() -> None:
    """The verification-fail contract MUST be a well-formed
    JSON-Schema-2020-12 schema document. ``Draft202012Validator.check_schema``
    raises ``SchemaError`` if the schema fails meta-validation."""
    schema = _load_schema(VERIFICATION_FAIL_PATH)
    Draft202012Validator.check_schema(schema)


def test_verification_fail_contract_carries_required_top_level_fields() -> None:
    """Per AC-2(b), the contract's `required:` field enumerates exactly the
    seven structurally-required top-level fields."""
    schema = _load_schema(VERIFICATION_FAIL_PATH)
    expected = {
        "bundle_class",
        "story_id",
        "run_id",
        "retry_policy",
        "failing_ac_result",
        "qa_behavioral_plan_pointer",
        "evidence_refs",
    }
    assert set(schema["required"]) == expected


def test_verification_fail_bundle_class_enum_is_single_value_verification_fail() -> None:
    """Per AC-2(c), `bundle_class.enum` is the single-value
    `["verification-fail"]` discriminator."""
    schema = _load_schema(VERIFICATION_FAIL_PATH)
    assert schema["properties"]["bundle_class"]["enum"] == ["verification-fail"]


def test_verification_fail_retry_policy_enum_is_single_value_escalate() -> None:
    """Per AC-2(f) + FR24a (PRD line 839), `retry_policy.enum` is the
    single-value `["escalate"]` policy discriminator."""
    schema = _load_schema(VERIFICATION_FAIL_PATH)
    assert schema["properties"]["retry_policy"]["enum"] == ["escalate"]


def test_verification_fail_failing_ac_result_status_excludes_pass() -> None:
    """Per AC-2(g), the `failing_ac_result` AC-result `status` enum is
    narrowed to `[fail, blocked]` (NOT `[pass, fail, blocked]`) — by
    definition this contract carries a non-passing AC result; passing AC
    results do NOT trigger verification-fail escalation."""
    schema = _load_schema(VERIFICATION_FAIL_PATH)
    status_enum = schema["$defs"]["failing_ac_result"]["properties"]["status"]["enum"]
    assert set(status_enum) == {"fail", "blocked"}
    assert "pass" not in status_enum


def test_verification_fail_qa_behavioral_plan_pointer_section_heading_is_const() -> None:
    """Per AC-2(h), the `qa_behavioral_plan_pointer.section_heading` field
    is a const-form pointer to the canonical `## QA Behavioral Plan`
    section heading from Story 1.10b's section-allowlist."""
    schema = _load_schema(VERIFICATION_FAIL_PATH)
    section_heading = schema["properties"]["qa_behavioral_plan_pointer"][
        "properties"
    ]["section_heading"]
    assert section_heading["const"] == "## QA Behavioral Plan"


def test_verification_fail_carries_marker_class_references_for_three_markers() -> None:
    """Per AC-5, the verification-fail contract references exactly three
    optional marker classes via `marker_class` strict-name fields:
    `Tier-3-not-configured`, `plan-drift-detected`, `smoke-first-abort`.
    Set-equality assertion catches both missing refs and unintended extras.
    """
    schema = _load_schema(VERIFICATION_FAIL_PATH)
    marker_consts = {value for value, _ in _collect_marker_class_const_values(schema, [])}
    assert marker_consts == {"Tier-3-not-configured", "plan-drift-detected", "smoke-first-abort"}


# --------------------------------------------------------------------------- #
# Schema-validity (env-setup-fail.yaml)                                       #
# --------------------------------------------------------------------------- #


def test_env_setup_fail_contract_is_well_formed_jsonschema_2020_12() -> None:
    """The env-setup-fail contract MUST be a well-formed
    JSON-Schema-2020-12 schema document."""
    schema = _load_schema(ENV_SETUP_FAIL_PATH)
    Draft202012Validator.check_schema(schema)


def test_env_setup_fail_contract_carries_required_top_level_fields() -> None:
    """Per AC-3(b), the env-setup-fail contract's `required:` field
    enumerates exactly the seven structurally-required top-level fields."""
    schema = _load_schema(ENV_SETUP_FAIL_PATH)
    expected = {
        "bundle_class",
        "story_id",
        "run_id",
        "retry_policy",
        "env_setup_diagnostic",
        "qa_runbook_pointer",
        "story_state_preservation_note",
    }
    assert set(schema["required"]) == expected


def test_env_setup_fail_bundle_class_enum_is_single_value_env_setup_fail() -> None:
    """Per AC-3(c), `bundle_class.enum` is the single-value
    `["env-setup-fail"]` discriminator."""
    schema = _load_schema(ENV_SETUP_FAIL_PATH)
    assert schema["properties"]["bundle_class"]["enum"] == ["env-setup-fail"]


def test_env_setup_fail_retry_policy_enum_is_single_value_escalate_with_env_diagnostic() -> None:
    """Per AC-3(f) + FR24b (PRD line 840), `retry_policy.enum` is the
    single-value `["escalate-with-env-diagnostic"]` policy discriminator."""
    schema = _load_schema(ENV_SETUP_FAIL_PATH)
    assert schema["properties"]["retry_policy"]["enum"] == [
        "escalate-with-env-diagnostic"
    ]


def test_env_setup_fail_story_state_preservation_current_state_is_const_review() -> None:
    """Per AC-3(i), `story_state_preservation_note.current_state` is the
    const-form `"review"` lifecycle-state preservation marker."""
    schema = _load_schema(ENV_SETUP_FAIL_PATH)
    current_state = schema["properties"]["story_state_preservation_note"][
        "properties"
    ]["current_state"]
    assert current_state["const"] == "review"


def test_env_setup_fail_story_state_intended_next_state_skipped_is_const_qa() -> None:
    """Per AC-3(i), `story_state_preservation_note.intended_next_state_skipped`
    is the const-form `"qa"` skipped-state marker."""
    schema = _load_schema(ENV_SETUP_FAIL_PATH)
    intended = schema["properties"]["story_state_preservation_note"][
        "properties"
    ]["intended_next_state_skipped"]
    assert intended["const"] == "qa"


def test_env_setup_fail_carries_marker_class_reference_for_env_setup_failed() -> None:
    """Per AC-3(g) + AC-5, the env-setup-fail contract references the
    `env-setup-failed` marker class via the
    `env_setup_diagnostic.marker_class` strict-name field."""
    schema = _load_schema(ENV_SETUP_FAIL_PATH)
    marker_consts = {value for value, _ in _collect_marker_class_const_values(schema, [])}
    assert "env-setup-failed" in marker_consts


# --------------------------------------------------------------------------- #
# Structural-distinctness invariants (cross-contract)                          #
# --------------------------------------------------------------------------- #


def test_verification_fail_lacks_env_setup_diagnostic_field() -> None:
    """Per AC-2 + the structural-distinctness invariant at AC-3 / epics.md
    line 2106, verification-fail does NOT include `env_setup_diagnostic`.
    The contract's narrowed shape (no env-setup-diagnostic; no qa-runbook-
    pointer; no story-state-preservation-note) is the structural
    distinctness from env-setup-fail."""
    schema = _load_schema(VERIFICATION_FAIL_PATH)
    assert "env_setup_diagnostic" not in schema["properties"]


def test_env_setup_fail_lacks_failing_ac_result_field() -> None:
    """Per AC-3(j), env-setup-fail occurs BEFORE QA dispatch; there is no
    AC-failure record to carry. The contract's narrowed shape (no
    failing_ac_result) IS the structural distinctness from verification-
    fail."""
    schema = _load_schema(ENV_SETUP_FAIL_PATH)
    assert "failing_ac_result" not in schema["properties"]


def test_env_setup_fail_lacks_qa_behavioral_plan_pointer_field() -> None:
    """Per AC-3(k), the QA Behavioral Plan is a downstream-of-env-
    provisioning artifact; env-setup failures occur before the plan is
    consumed."""
    schema = _load_schema(ENV_SETUP_FAIL_PATH)
    assert "qa_behavioral_plan_pointer" not in schema["properties"]


def test_both_contracts_close_with_additional_properties_false_at_top_level() -> None:
    """Both contracts MUST close with `additionalProperties: false` at the
    top level. Closed-by-default rejects every undeclared field, mirroring
    `envelope.schema.yaml`'s closed-by-default invariant."""
    verification = _load_schema(VERIFICATION_FAIL_PATH)
    env_setup = _load_schema(ENV_SETUP_FAIL_PATH)
    assert verification["additionalProperties"] is False
    assert env_setup["additionalProperties"] is False


def test_both_contracts_have_distinct_id_urls() -> None:
    """Both contracts MUST have well-formed AND distinct `$id` URLs so
    JSON-Schema reference resolution disambiguates them."""
    verification = _load_schema(VERIFICATION_FAIL_PATH)
    env_setup = _load_schema(ENV_SETUP_FAIL_PATH)
    assert verification["$id"].startswith("https://bmad-autopilot.local/")
    assert env_setup["$id"].startswith("https://bmad-autopilot.local/")
    assert verification["$id"] != env_setup["$id"]
    assert "verification-fail" in verification["$id"]
    assert "env-setup-fail" in env_setup["$id"]


# --------------------------------------------------------------------------- #
# Header-comment integrity                                                    #
# --------------------------------------------------------------------------- #


def test_verification_fail_header_names_FR24a_and_story_4_10() -> None:
    """The verification-fail contract's header comment block MUST cite
    FR24a and Story 4.10 verbatim. Loaded as text (NOT parsed YAML —
    comments are stripped at parse time)."""
    text = VERIFICATION_FAIL_PATH.read_text(encoding="utf-8")
    assert "FR24a" in text
    assert "Story 4.10" in text


def test_env_setup_fail_header_names_FR24b_and_story_4_10() -> None:
    """The env-setup-fail contract's header comment block MUST cite FR24b
    and Story 4.10 verbatim."""
    text = ENV_SETUP_FAIL_PATH.read_text(encoding="utf-8")
    assert "FR24b" in text
    assert "Story 4.10" in text


def test_both_contracts_header_name_ADR_002_cell_1_classification() -> None:
    """Both contract files' headers MUST reference ADR-002 + the cell-1
    architectural-core classification per the contract-anchors discipline."""
    verification_text = VERIFICATION_FAIL_PATH.read_text(encoding="utf-8")
    env_setup_text = ENV_SETUP_FAIL_PATH.read_text(encoding="utf-8")
    for text in (verification_text, env_setup_text):
        assert "ADR-002" in text
        assert "cell-1" in text
        assert "architectural-core" in text


# --------------------------------------------------------------------------- #
# Pattern-1 + Pattern-2 conformance                                           #
# --------------------------------------------------------------------------- #


def test_verification_fail_all_structural_keys_are_snake_case() -> None:
    """Per AC-4, every user-defined field name (key under a `properties:`
    map) MUST be snake_case per Pattern 1 (architecture.md lines 925-955)."""
    schema = _load_schema(VERIFICATION_FAIL_PATH)
    user_keys = _walk_user_keys(schema, [])
    assert user_keys, "expected at least one user-defined key"
    for key, path in user_keys:
        assert _SNAKE_CASE_REGEX.match(key), (
            f"non-snake_case user key {key!r} at /{('/').join(path)}"
        )


def test_env_setup_fail_all_structural_keys_are_snake_case() -> None:
    """Per AC-4, every user-defined field name MUST be snake_case."""
    schema = _load_schema(ENV_SETUP_FAIL_PATH)
    user_keys = _walk_user_keys(schema, [])
    assert user_keys, "expected at least one user-defined key"
    for key, path in user_keys:
        assert _SNAKE_CASE_REGEX.match(key), (
            f"non-snake_case user key {key!r} at /{('/').join(path)}"
        )


@pytest.mark.parametrize(
    "expected_marker_class",
    ["Tier-3-not-configured", "plan-drift-detected", "smoke-first-abort"],
)
def test_verification_fail_marker_class_values_are_kebab_case(
    expected_marker_class: str,
) -> None:
    """Per AC-4 + Pattern 2, every `marker_class.const` value in the
    verification-fail contract MUST match the verbatim casing from the
    canonical taxonomy. Tests are parametrized across the three optional
    marker references; `Tier-3-not-configured` is intentional CamelCase-
    prefix kebab (mirrors `LAD-skipped` precedent at marker-taxonomy.yaml
    line 70)."""
    schema = _load_schema(VERIFICATION_FAIL_PATH)
    marker_consts = {value for value, _ in _collect_marker_class_const_values(schema, [])}
    assert expected_marker_class in marker_consts


def test_env_setup_fail_marker_class_value_is_kebab_case() -> None:
    """Per AC-4 + Pattern 2, the env-setup-fail contract's
    `env_setup_diagnostic.marker_class.const` value MUST match the
    canonical taxonomy casing of `env-setup-failed`."""
    schema = _load_schema(ENV_SETUP_FAIL_PATH)
    marker_consts = {value for value, _ in _collect_marker_class_const_values(schema, [])}
    assert marker_consts == {"env-setup-failed"}


# --------------------------------------------------------------------------- #
# LF line endings (optional)                                                  #
# --------------------------------------------------------------------------- #


def test_verification_fail_yaml_uses_LF_line_endings() -> None:
    """Mirrors prior stories' LF-discipline test: the contract file MUST NOT
    contain CR characters (no CRLF or bare CR endings)."""
    raw_bytes = VERIFICATION_FAIL_PATH.read_bytes()
    assert b"\r" not in raw_bytes


def test_env_setup_fail_yaml_uses_LF_line_endings() -> None:
    """Mirrors prior stories' LF-discipline test."""
    raw_bytes = ENV_SETUP_FAIL_PATH.read_bytes()
    assert b"\r" not in raw_bytes
