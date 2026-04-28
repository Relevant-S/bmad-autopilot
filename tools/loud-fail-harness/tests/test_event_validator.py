"""Contract-coverage matrix for substrate component 2 (event validator).

This docstring IS the contract-coverage checklist required by AC-4. Reviewers
verify every row maps to at least one passing test in this module. The matrix
is review-enforced, NOT CI-enforced (parallel to story 1.2 AC-4).

Per-event-class positive payloads (AC-4 — one per class, 10 total):
    [x] specialist-dispatched valid                              → test_positive_specialist_dispatched
    [x] specialist-returned valid                                → test_positive_specialist_returned
    [x] state-transition valid                                   → test_positive_state_transition
    [x] state-transition self-transition rejected (P5)           → test_state_transition_self_transition_rejected
    [x] state-transition-halted valid                            → test_positive_state_transition_halted
    [x] retry-attempted valid                                    → test_positive_retry_attempted
    [x] retry-attempted empty affected_files rejected (P6)       → test_retry_attempted_empty_affected_files_rejected
    [x] escalation-fired valid                                   → test_positive_escalation_fired
    [x] env-provisioned valid                                    → test_positive_env_provisioned
    [x] env-torn-down valid                                      → test_positive_env_torn_down
    [x] hook-fired valid                                         → test_positive_hook_fired
    [x] cost-event valid                                         → test_positive_cost_event

Per-event-class negative-required-field tests (AC-4 — one per class, 10 total):
    [x] specialist-dispatched missing `specialist`               → test_missing_required_per_class[specialist-dispatched]
    [x] specialist-returned missing `status`                     → test_missing_required_per_class[specialist-returned]
    [x] state-transition missing `from_state`                    → test_missing_required_per_class[state-transition]
    [x] state-transition-halted missing `halted_at_state`        → test_missing_required_per_class[state-transition-halted]
    [x] retry-attempted missing `affected_files`                 → test_missing_required_per_class[retry-attempted]
    [x] escalation-fired missing `escalation_class`              → test_missing_required_per_class[escalation-fired]
    [x] env-provisioned missing `env_kind`                       → test_missing_required_per_class[env-provisioned]
    [x] env-torn-down missing `outcome`                          → test_missing_required_per_class[env-torn-down]
    [x] hook-fired missing `hook_name`                           → test_missing_required_per_class[hook-fired]
    [x] cost-event missing `cost_delta_usd`                      → test_missing_required_per_class[cost-event]

Boundary cases (AC-4):
    [x] missing `event_class` → "missing required field: event_class" → test_boundary_missing_event_class
    [x] snake_case event_class value rejected with UX rewrite    → test_boundary_snake_case_event_class
    [x] unknown kebab-case event_class rejected with UX rewrite  → test_boundary_unknown_event_class
    [x] kebab-case field within event payload rejected           → test_boundary_kebab_case_field_in_event
    [x] missing top-level `story_id`                             → test_boundary_missing_story_id
    [x] missing top-level `event_id`                             → test_boundary_missing_event_id
    [x] missing top-level `timestamp`                            → test_boundary_missing_timestamp

OTel pass-through (AC-2, AC-4):
    [x] cost-event with all four OTel attrs validates clean      → test_otel_passthrough_cost_event_validates
    [x] OTel slot is distinct from snake_case slot               → test_otel_passthrough_slots_distinct
    [x] re-cased OTel attribute (e.g. claude_code_cost_usage) rejected → test_otel_recased_attribute_rejected

Schema self-check (AC-1):
    [x] schemas/orchestrator-event.yaml meta-validates           → test_schema_meta_validates

Canonical positive event fixture (AC-3 dependency):
    [x] examples/orchestrator-events/specialist-dispatched.yaml  → test_canonical_specialist_dispatched_validates

CLI / harness behavior:
    [x] empty argv → exit 0 (gate is no-op on empty set)         → test_cli_no_events_returns_zero
    [x] --require-nonempty + empty argv → exit 2                  → test_cli_require_nonempty_with_no_args
    [x] valid event → exit 0                                     → test_cli_valid_event_returns_zero
    [x] unknown event class → exit 1, UX rewrite                 → test_cli_unknown_event_class_returns_one
    [x] missing event_class → exit 1, UX rewrite                 → test_cli_missing_event_class_returns_one
    [x] schema meta-invalid → exit 2                            → test_cli_meta_invalid_schema_returns_two
    [x] schema YAML parse error → exit 2                        → test_cli_schema_yaml_parse_error_returns_two
    [x] event unreadable → exit 2                                → test_cli_event_unreadable_returns_two
    [x] event YAML parse failure → exit 2                        → test_cli_event_yaml_parse_failure_returns_two
    [x] event is not a mapping → produces synthetic error        → test_validate_file_non_mapping
    [x] default schema path resolves                             → test_cli_default_schema_path_resolves
    [x] mixed valid + invalid → still exits 1                    → test_cli_invalid_then_valid_still_returns_one

Format edge cases:
    [x] format_errors([]) returns empty string                   → test_format_errors_empty
    [x] format_errors prefixes event path when given             → test_format_errors_includes_event_path
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from loud_fail_harness.envelope_validator import find_repo_root
from loud_fail_harness.event_validator import (
    format_errors,
    load_schema,
    main,
    validate_event,
    validate_file,
)

REPO_ROOT = find_repo_root()
SCHEMA_PATH = REPO_ROOT / "schemas" / "orchestrator-event.yaml"
SEED_FIXTURE_PATH = (
    REPO_ROOT / "examples" / "orchestrator-events" / "specialist-dispatched.yaml"
)


@pytest.fixture(scope="module")
def schema() -> dict:
    return load_schema(SCHEMA_PATH)


def _common_top_level(**overrides: object) -> dict:
    base: dict = {
        "event_id": "ev-test-0001",
        "timestamp": "2026-04-26T00:00:00Z",
        "story_id": "1.3",
    }
    base.update(overrides)
    return base


def _specialist_dispatched(**overrides: object) -> dict:
    base = _common_top_level(
        event_class="specialist-dispatched",
        specialist="dev",
        prompt_id="prompt-1",
        retry_attempt=0,
    )
    base.update(overrides)
    return base


def _specialist_returned(**overrides: object) -> dict:
    base = _common_top_level(
        event_class="specialist-returned",
        specialist="dev",
        prompt_id="prompt-1",
        retry_attempt=0,
        status="pass",
    )
    base.update(overrides)
    return base


def _state_transition(**overrides: object) -> dict:
    base = _common_top_level(
        event_class="state-transition",
        from_state="ready-for-dev",
        to_state="in-progress",
    )
    base.update(overrides)
    return base


def _state_transition_halted(**overrides: object) -> dict:
    base = _common_top_level(
        event_class="state-transition-halted",
        halted_at_state="review",
        halt_reason="non-pass-envelope",
        triggering_specialist="review-bmad",
        last_envelope_status="fail",
    )
    base.update(overrides)
    return base


def _retry_attempted(**overrides: object) -> dict:
    base = _common_top_level(
        event_class="retry-attempted",
        specialist="dev",
        retry_attempt=1,
        affected_files=["src/foo.py"],
    )
    base.update(overrides)
    return base


def _escalation_fired(**overrides: object) -> dict:
    base = _common_top_level(
        event_class="escalation-fired",
        escalation_class="retry-budget-exhausted",
        bundle_artifact_path="_bmad-output/escalations/x.md",
    )
    base.update(overrides)
    return base


def _env_provisioned(**overrides: object) -> dict:
    base = _common_top_level(
        event_class="env-provisioned",
        env_kind="web",
    )
    base.update(overrides)
    return base


def _env_torn_down(**overrides: object) -> dict:
    base = _common_top_level(
        event_class="env-torn-down",
        env_kind="web",
        outcome="clean",
    )
    base.update(overrides)
    return base


def _hook_fired(**overrides: object) -> dict:
    base = _common_top_level(
        event_class="hook-fired",
        hook_name="subagent-stop",
        exit_code=0,
    )
    base.update(overrides)
    return base


def _cost_event(**overrides: object) -> dict:
    base = _common_top_level(
        event_class="cost-event",
        prompt_id="prompt-1",
        retry_attempt=0,
        specialist="dev",
        cost_delta_usd=0.012,
    )
    base.update(overrides)
    return base


_BUILDERS = {
    "specialist-dispatched": _specialist_dispatched,
    "specialist-returned": _specialist_returned,
    "state-transition": _state_transition,
    "state-transition-halted": _state_transition_halted,
    "retry-attempted": _retry_attempted,
    "escalation-fired": _escalation_fired,
    "env-provisioned": _env_provisioned,
    "env-torn-down": _env_torn_down,
    "hook-fired": _hook_fired,
    "cost-event": _cost_event,
}


# --------------------------------------------------------------------------- #
# Schema self-check + canonical fixture                                       #
# --------------------------------------------------------------------------- #


def test_schema_meta_validates() -> None:
    schema = load_schema(SCHEMA_PATH)
    assert schema.get("$schema", "").endswith("/draft/2020-12/schema")


def test_canonical_specialist_dispatched_validates(schema: dict) -> None:
    errors = validate_file(SEED_FIXTURE_PATH, schema)
    assert errors == [], format_errors(errors)


# --------------------------------------------------------------------------- #
# Per-event-class positive payloads                                            #
# --------------------------------------------------------------------------- #


def test_positive_specialist_dispatched(schema: dict) -> None:
    assert validate_event(_specialist_dispatched(), schema) == []


def test_positive_specialist_returned(schema: dict) -> None:
    assert validate_event(_specialist_returned(), schema) == []


def test_positive_state_transition(schema: dict) -> None:
    assert validate_event(_state_transition(), schema) == []


def test_positive_state_transition_halted(schema: dict) -> None:
    assert validate_event(_state_transition_halted(), schema) == []


def test_state_transition_self_transition_rejected(schema: dict) -> None:
    """from_state == to_state must be rejected (review finding P5)."""
    event = _state_transition(from_state="review", to_state="review")
    errors = validate_event(event, schema)
    assert errors, "self-transition (review → review) should fail validation"


def test_positive_retry_attempted(schema: dict) -> None:
    assert validate_event(_retry_attempted(), schema) == []


def test_retry_attempted_empty_affected_files_rejected(schema: dict) -> None:
    """affected_files: [] must be rejected; minItems: 1 (review finding P6)."""
    event = _retry_attempted(affected_files=[])
    errors = validate_event(event, schema)
    assert errors, "empty affected_files should fail validation"


def test_positive_escalation_fired(schema: dict) -> None:
    assert validate_event(_escalation_fired(), schema) == []


def test_positive_env_provisioned(schema: dict) -> None:
    assert validate_event(_env_provisioned(), schema) == []


def test_positive_env_torn_down(schema: dict) -> None:
    assert validate_event(_env_torn_down(), schema) == []


def test_positive_hook_fired(schema: dict) -> None:
    assert validate_event(_hook_fired(), schema) == []


def test_positive_cost_event(schema: dict) -> None:
    assert validate_event(_cost_event(), schema) == []


# --------------------------------------------------------------------------- #
# Per-event-class negative-required-field tests                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "event_class,missing_field",
    [
        ("specialist-dispatched", "specialist"),
        ("specialist-returned", "status"),
        ("state-transition", "from_state"),
        ("state-transition-halted", "halted_at_state"),
        ("retry-attempted", "affected_files"),
        ("escalation-fired", "escalation_class"),
        ("env-provisioned", "env_kind"),
        ("env-torn-down", "outcome"),
        ("hook-fired", "hook_name"),
        ("cost-event", "cost_delta_usd"),
    ],
)
def test_missing_required_per_class(
    schema: dict, event_class: str, missing_field: str
) -> None:
    builder = _BUILDERS[event_class]
    event = builder()
    del event[missing_field]
    errors = validate_event(event, schema)
    assert errors, f"missing {missing_field} on {event_class} should fail"
    output = format_errors(errors)
    assert missing_field in output


# --------------------------------------------------------------------------- #
# Boundary-case tests                                                          #
# --------------------------------------------------------------------------- #


def test_boundary_missing_event_class(schema: dict) -> None:
    event = _specialist_dispatched()
    del event["event_class"]
    errors = validate_event(event, schema)
    assert errors
    out = format_errors(errors)
    assert "missing required field: event_class" in out


def test_boundary_snake_case_event_class(schema: dict) -> None:
    event = _specialist_dispatched(event_class="specialist_dispatched")
    errors = validate_event(event, schema)
    assert errors
    out = format_errors(errors)
    assert "unknown event class: specialist_dispatched" in out


def test_boundary_unknown_event_class(schema: dict) -> None:
    event = _common_top_level(event_class="foo-bar-baz")
    errors = validate_event(event, schema)
    assert errors
    out = format_errors(errors)
    assert "unknown event class: foo-bar-baz" in out


def test_boundary_kebab_case_field_in_event(schema: dict) -> None:
    """A kebab-case field name (e.g. ``retry-attempt``) within a
    specialist-dispatched event must be rejected by the per-branch
    additionalProperties: false discipline."""
    event = _specialist_dispatched()
    event["retry-attempt"] = event.pop("retry_attempt")
    errors = validate_event(event, schema)
    assert errors
    out = format_errors(errors)
    assert "retry-attempt" in out


def test_boundary_missing_story_id(schema: dict) -> None:
    event = _specialist_dispatched()
    del event["story_id"]
    errors = validate_event(event, schema)
    assert errors
    out = format_errors(errors)
    assert "story_id" in out


def test_boundary_missing_event_id(schema: dict) -> None:
    event = _specialist_dispatched()
    del event["event_id"]
    errors = validate_event(event, schema)
    assert errors
    out = format_errors(errors)
    assert "event_id" in out


def test_boundary_missing_timestamp(schema: dict) -> None:
    event = _specialist_dispatched()
    del event["timestamp"]
    errors = validate_event(event, schema)
    assert errors
    out = format_errors(errors)
    assert "timestamp" in out


# --------------------------------------------------------------------------- #
# OTel pass-through tests                                                      #
# --------------------------------------------------------------------------- #


def test_otel_passthrough_cost_event_validates(schema: dict) -> None:
    """cost-event with all four OTel-canonical attribute names (dotted,
    mixed-case) validates clean without re-casing — Pattern 3 + AC-2."""
    event = _cost_event()
    event["prompt.id"] = "otel-prompt-id-abc"
    event["claude_code.cost.usage"] = 0.012
    event["claude_code.token.usage"] = 4321
    event["query_source"] = "main"
    assert validate_event(event, schema) == []


def test_otel_passthrough_slots_distinct(schema: dict) -> None:
    """The OTel ``prompt.id`` slot and the snake_case ``prompt_id`` slot are
    distinct named fields. Removing the required snake_case ``prompt_id``
    while leaving only the OTel ``prompt.id`` must fail — proving they are
    NOT silently routed to the same slot.
    """
    event = _cost_event()
    del event["prompt_id"]
    event["prompt.id"] = "otel-prompt-id-only"
    errors = validate_event(event, schema)
    assert errors, "removing snake_case prompt_id should fail even when prompt.id is set"
    out = format_errors(errors)
    assert "prompt_id" in out


def test_otel_recased_attribute_rejected(schema: dict) -> None:
    """A re-cased OTel attribute name (e.g. ``claude_code_cost_usage``
    instead of ``claude_code.cost.usage``) must be rejected — the schema
    enumerates a closed set of OTel pass-through names per Pattern 3.
    """
    event = _cost_event()
    event["claude_code_cost_usage"] = 0.012
    errors = validate_event(event, schema)
    assert errors
    out = format_errors(errors)
    assert "claude_code_cost_usage" in out


# --------------------------------------------------------------------------- #
# format_errors edge cases                                                     #
# --------------------------------------------------------------------------- #


def test_format_errors_empty() -> None:
    assert format_errors([]) == ""


def test_format_errors_includes_event_path(schema: dict) -> None:
    event = _common_top_level(event_class="foo-bar-baz")
    errors = validate_event(event, schema)
    out = format_errors(errors, event_path=pathlib.Path("/tmp/bad.yaml"))
    assert "event: /tmp/bad.yaml" in out


# --------------------------------------------------------------------------- #
# validate_file / load_schema edge cases                                       #
# --------------------------------------------------------------------------- #


def test_validate_file_non_mapping(tmp_path: pathlib.Path, schema: dict) -> None:
    bad = tmp_path / "not-a-mapping.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    errors = validate_file(bad, schema)
    assert errors
    assert "not parse to a YAML mapping" in errors[0].message


# --------------------------------------------------------------------------- #
# CLI behavior                                                                 #
# --------------------------------------------------------------------------- #


def test_cli_no_events_returns_zero() -> None:
    assert main(["--schema", str(SCHEMA_PATH)]) == 0


def test_cli_require_nonempty_with_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--schema", str(SCHEMA_PATH), "--require-nonempty"])
    assert rc == 2
    assert "no events provided" in capsys.readouterr().err


def test_cli_default_schema_path_resolves() -> None:
    assert main([]) == 0


def test_cli_valid_event_returns_zero() -> None:
    assert main(["--schema", str(SCHEMA_PATH), str(SEED_FIXTURE_PATH)]) == 0


def test_cli_unknown_event_class_returns_one(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent(
            """\
            event_class: foo-bar-baz
            event_id: ev-1
            timestamp: "2026-04-26T00:00:00Z"
            story_id: "1.3"
            """
        ),
        encoding="utf-8",
    )
    rc = main(["--schema", str(SCHEMA_PATH), str(bad)])
    assert rc == 1
    assert "unknown event class: foo-bar-baz" in capsys.readouterr().out


def test_cli_missing_event_class_returns_one(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent(
            """\
            event_id: ev-1
            timestamp: "2026-04-26T00:00:00Z"
            story_id: "1.3"
            """
        ),
        encoding="utf-8",
    )
    rc = main(["--schema", str(SCHEMA_PATH), str(bad)])
    assert rc == 1
    assert "missing required field: event_class" in capsys.readouterr().out


def test_cli_meta_invalid_schema_returns_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Schema file is valid YAML but fails Draft202012Validator.check_schema."""
    bad_schema = tmp_path / "bad-schema.yaml"
    bad_schema.write_text("type: not-a-valid-type\n", encoding="utf-8")
    rc = main(["--schema", str(bad_schema), str(SEED_FIXTURE_PATH)])
    assert rc == 2
    assert "schema" in capsys.readouterr().err.lower()


def test_cli_schema_yaml_parse_error_returns_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Schema file contains invalid YAML (yaml.YAMLError path in main)."""
    bad_schema = tmp_path / "bad-schema.yaml"
    bad_schema.write_text("key: [unclosed bracket\n", encoding="utf-8")
    rc = main(["--schema", str(bad_schema), str(SEED_FIXTURE_PATH)])
    assert rc == 2
    assert "schema" in capsys.readouterr().err.lower()


def test_cli_unreadable_schema_returns_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        ["--schema", str(tmp_path / "missing-schema.yaml"), str(SEED_FIXTURE_PATH)]
    )
    assert rc == 2
    assert "schema" in capsys.readouterr().err.lower()


def test_cli_event_unreadable_returns_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        ["--schema", str(SCHEMA_PATH), str(tmp_path / "missing-event.yaml")]
    )
    assert rc == 2
    assert "event" in capsys.readouterr().err.lower()


def test_cli_event_yaml_parse_failure_returns_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "broken.yaml"
    bad.write_text(
        "event_class: specialist-dispatched\n  bad: indentation\nfoo:\n   - : :\n",
        encoding="utf-8",
    )
    rc = main(["--schema", str(SCHEMA_PATH), str(bad)])
    assert rc == 2
    assert "event" in capsys.readouterr().err.lower()


def test_cli_invalid_then_valid_still_returns_one(
    tmp_path: pathlib.Path,
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent(
            """\
            event_class: foo-bar-baz
            event_id: ev-1
            timestamp: "2026-04-26T00:00:00Z"
            story_id: "1.3"
            """
        ),
        encoding="utf-8",
    )
    rc = main(
        [
            "--schema",
            str(SCHEMA_PATH),
            str(SEED_FIXTURE_PATH),
            str(bad),
        ]
    )
    assert rc == 1
