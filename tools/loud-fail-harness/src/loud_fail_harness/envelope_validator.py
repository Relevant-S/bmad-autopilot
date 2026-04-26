"""Substrate component 1: Specialist envelope schema validation. See ADR-003.

Loads the canonical envelope JSON Schema (YAML-encoded) and validates specialist
envelopes against it. Implements FR53 — the CI gate that rejects envelopes whose
shape violates FR51/FR52 (uniform envelope, sensor-not-advisor).

Loud-fail discipline (Pattern 5):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — all envelopes valid (or zero envelopes provided; the gate is a no-op
            on empty input per AC-3, unless ``--require-nonempty`` is passed)
        1 — at least one envelope failed validation
        2 — harness-level error (schema malformed, file unreadable, etc.)
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections.abc import Sequence

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from loud_fail_harness._shared import _path_pointer, find_repo_root, load_schema

#: Known forbidden flow-policy field names (FR52). The schema's
#: ``additionalProperties: false`` already rejects ANY undeclared field — this
#: set exists so the validator's CLI surface can rewrite generic
#: "additional property" errors into named "forbidden flow-policy field"
#: messages for the two most plausible cases. Future flow-policy-implying field
#: names not yet imagined are still rejected by ``additionalProperties: false``;
#: their error message will name the field but not call it "flow-policy".
FORBIDDEN_FLOW_POLICY_FIELDS: frozenset[str] = frozenset({"next_action", "recommendation"})

_ADDITIONAL_PROPERTY_KEY_PATTERN = re.compile(r"'([^']+)'")


def validate_envelope(envelope: dict, schema: dict) -> list[ValidationError]:
    """Return *every* validation error against ``schema`` (not just the first).

    An empty list means the envelope is valid.
    """
    validator = Draft202012Validator(schema)
    return list(validator.iter_errors(envelope))


def validate_file(
    envelope_path: pathlib.Path, schema: dict
) -> list[ValidationError]:
    """Load YAML from ``envelope_path`` and validate it against ``schema``.

    Returns a single synthetic error if the file does not parse to a mapping
    (rather than raising) so the CLI can keep formatting consistent across
    multiple envelope arguments.
    """
    raw = yaml.safe_load(envelope_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return [
            ValidationError(
                f"envelope at {envelope_path} did not parse to a YAML mapping at top level"
            )
        ]
    return validate_envelope(raw, schema)


def format_errors(
    errors: Sequence[ValidationError],
    envelope_path: pathlib.Path | None = None,
) -> str:
    """Render validation errors as a human-readable, CI-log-friendly string.

    Forbidden flow-policy fields (``next_action``, ``recommendation``, plus any
    future entry in :data:`FORBIDDEN_FLOW_POLICY_FIELDS`) are rewritten to a
    named, FR52-anchored message. Other errors keep their default phrasing,
    prefixed with their JSON-pointer path.
    """
    if not errors:
        return ""

    lines: list[str] = []
    if envelope_path is not None:
        lines.append(f"envelope: {envelope_path}")

    reported_forbidden: set[str] = set()
    # Pre-scan so the `not`-clause suppression below is order-independent.
    saw_top_level_additional_properties = any(
        e.validator == "additionalProperties" and not list(e.absolute_path)
        for e in errors
    )

    for err in errors:
        path_list = list(err.absolute_path)

        if err.validator == "additionalProperties" and not path_list:
            for key in _ADDITIONAL_PROPERTY_KEY_PATTERN.findall(err.message):
                if key in FORBIDDEN_FLOW_POLICY_FIELDS:
                    if key not in reported_forbidden:
                        reported_forbidden.add(key)
                        lines.append(
                            f"forbidden flow-policy field: {key} "
                            "(sensor-not-advisor invariant; see FR52)"
                        )
                else:
                    lines.append(
                        f"additional property '{key}' not allowed "
                        "(envelope contract is closed; see FR51)"
                    )
            continue

        if err.validator == "additionalProperties":
            parent = _path_pointer(path_list)
            for key in _ADDITIONAL_PROPERTY_KEY_PATTERN.findall(err.message):
                lines.append(
                    f"{parent}: additional property '{key}' not allowed"
                )
            continue

        if err.validator == "not" and not path_list:
            # The defense-in-depth `not` clause fired. If we already reported a
            # specific forbidden field via additionalProperties, the `not`
            # error is redundant — suppress it to keep the log tight.
            if saw_top_level_additional_properties:
                continue
            lines.append(
                "forbidden flow-policy field present "
                "(sensor-not-advisor invariant; see FR52)"
            )
            continue

        lines.append(f"{_path_pointer(path_list)}: {err.message}")

    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="envelope-validator",
        description=(
            "Validate specialist envelope YAML files against the canonical "
            "envelope schema (substrate component 1; ADR-003 / FR51-FR56)."
        ),
    )
    parser.add_argument(
        "--schema",
        type=pathlib.Path,
        default=None,
        help=(
            "Path to envelope schema YAML. Defaults to "
            "<repo-root>/schemas/envelope.schema.yaml resolved from this "
            "module's location."
        ),
    )
    parser.add_argument(
        "--require-nonempty",
        action="store_true",
        help=(
            "Fail with exit code 2 if no envelope paths are provided. "
            "Default behavior is to pass (no-op gate on empty set, per AC-3)."
        ),
    )
    parser.add_argument(
        "envelopes",
        nargs="*",
        type=pathlib.Path,
        help="Envelope YAML files to validate.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    schema_path: pathlib.Path
    if args.schema is not None:
        schema_path = args.schema
    else:
        try:
            schema_path = find_repo_root() / "schemas" / "envelope.schema.yaml"
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    try:
        schema = load_schema(schema_path)
    except OSError as exc:
        print(
            f"harness-level error: schema unreadable: {schema_path}: {exc}",
            file=sys.stderr,
        )
        return 2
    except (SchemaError, yaml.YAMLError) as exc:
        print(
            f"harness-level error: schema malformed: {schema_path}: {exc}",
            file=sys.stderr,
        )
        return 2

    if not args.envelopes:
        if args.require_nonempty:
            print(
                "harness-level error: --require-nonempty set but no envelopes provided",
                file=sys.stderr,
            )
            return 2
        return 0

    any_failed = False
    for envelope_path in args.envelopes:
        try:
            errors = validate_file(envelope_path, schema)
        except OSError as exc:
            print(
                f"harness-level error: envelope unreadable: {envelope_path}: {exc}",
                file=sys.stderr,
            )
            return 2
        except yaml.YAMLError as exc:
            print(
                f"harness-level error: envelope YAML parse failure: "
                f"{envelope_path}: {exc}",
                file=sys.stderr,
            )
            return 2

        if errors:
            any_failed = True
            print(format_errors(errors, envelope_path=envelope_path))

    return 1 if any_failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
