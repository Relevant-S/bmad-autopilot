"""Substrate component 2: Orchestrator-event schema validation. See ADR-003.

Loads the canonical orchestrator-event JSON Schema (YAML-encoded) and validates
orchestrator-emitted event payloads against it. Implements the event-side
half of the substrate-validation guarantee that pairs with substrate component
1 (envelope validation): every event the orchestrator emits at a seam
transition (per ADR-001 Consequence 2) has a canonical, harness-validatable
shape with closed per-class field sets.

Discriminated union: events are matched to one of nine event classes via the
``event_class`` field (kebab-case enum, Pattern 3). Each per-class branch is
closed (``additionalProperties: false``) and declares its own required +
optional fields. OTel-derived attribute names (``prompt.id``,
``claude_code.cost.usage``, ``claude_code.token.usage``, ``query_source``) are
external/host-Bridge per ADR-002 + ADR-006 Consequence 5; they pass through
under their dotted/mixed-case names without re-casing (Pattern 3).

Loud-fail discipline (Pattern 5):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — all events valid (or zero events provided; the gate is a no-op
            on empty input per AC-3, unless ``--require-nonempty`` is passed)
        1 — at least one event failed validation
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

_ADDITIONAL_PROPERTY_KEY_PATTERN = re.compile(r"'([^']+)'")


def validate_event(event: dict, schema: dict) -> list[ValidationError]:
    """Return *every* validation error against ``schema`` (not just the first).

    An empty list means the event is valid.
    """
    validator = Draft202012Validator(schema)
    return list(validator.iter_errors(event))


def validate_file(
    event_path: pathlib.Path, schema: dict
) -> list[ValidationError]:
    """Load YAML from ``event_path`` and validate it against ``schema``.

    Returns a single synthetic error if the file does not parse to a mapping
    (rather than raising) so the CLI can keep formatting consistent across
    multiple event arguments.
    """
    raw = yaml.safe_load(event_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return [
            ValidationError(
                f"event at {event_path} did not parse to a YAML mapping at top level"
            )
        ]
    return validate_event(raw, schema)


def _is_event_class_enum_error(err: ValidationError) -> bool:
    return list(err.absolute_path) == ["event_class"] and err.validator == "enum"


def _is_top_level_missing_event_class(err: ValidationError) -> bool:
    return (
        not list(err.absolute_path)
        and err.validator == "required"
        and "'event_class'" in err.message
    )


def _format_branch_errors(
    event_class_value: str,
    branch_errors: Sequence[ValidationError],
) -> list[str]:
    """Render the sub-errors from the per-class branch that *should have*
    matched (i.e. its ``properties.event_class.const`` matched the payload).

    Errors are rewritten with the event-class name in front so reviewers can
    tell which per-class contract was violated.
    """
    out: list[str] = []
    for ctx in branch_errors:
        sub_path = list(ctx.absolute_path)
        anchor = "" if not sub_path else f" {_path_pointer(sub_path)}"
        if ctx.validator == "additionalProperties":
            keys = _ADDITIONAL_PROPERTY_KEY_PATTERN.findall(ctx.message)
            if keys:
                for key in keys:
                    out.append(
                        f"{event_class_value} event{anchor}: unexpected field '{key}' "
                        "(per-class contract is closed; see schemas/orchestrator-event.yaml)"
                    )
            else:
                out.append(f"{event_class_value} event{anchor}: {ctx.message}")
        else:
            out.append(f"{event_class_value} event{anchor}: {ctx.message}")
    return out


def format_errors(
    errors: Sequence[ValidationError],
    event_path: pathlib.Path | None = None,
) -> str:
    """Render validation errors as a human-readable, CI-log-friendly string.

    Special UX rewrites (per AC-2 + Task 2):

    * Unknown ``event_class`` value → ``unknown event class: <name>`` (the
      generic ``'<name>' is not one of [...]`` enum error is suppressed).
    * Missing top-level ``event_class`` → ``missing required field: event_class``.
    * Per-class field violations (the matching ``oneOf`` branch's sub-errors)
      are surfaced with the event-class name as a prefix so reviewers see
      *which* per-class contract was broken; the generic
      ``is not valid under any of the given schemas`` banner is suppressed.

    Other errors (e.g., missing top-level ``event_id``/``timestamp``/
    ``story_id``, additionalProperties at root) keep their default phrasing,
    prefixed with their JSON-pointer path.
    """
    if not errors:
        return ""

    lines: list[str] = []
    if event_path is not None:
        lines.append(f"event: {event_path}")

    # Pre-scan: identify the event_class-specific diagnoses so we can suppress
    # noisier oneOf / unevaluatedProperties banners when a sharper diagnosis
    # is already in hand.
    unknown_event_class_value: object | None = None
    missing_event_class = False
    for err in errors:
        if _is_event_class_enum_error(err):
            unknown_event_class_value = err.instance
        if _is_top_level_missing_event_class(err):
            missing_event_class = True

    # Suppress unevaluatedProperties at root when oneOf is present — the oneOf
    # diagnosis (or the unknown/missing event_class diagnosis) is sharper, and
    # unevaluatedProperties just lists fields that no branch managed to claim
    # because the branch failed for a different reason. Only suppress when
    # something more specific *is* present; otherwise let the message stand.
    has_one_of_root = any(
        not list(err.absolute_path) and err.validator == "oneOf" for err in errors
    )
    sharper_root_diagnosis = (
        unknown_event_class_value is not None
        or missing_event_class
        or has_one_of_root
    )

    if missing_event_class:
        lines.append("missing required field: event_class")

    if unknown_event_class_value is not None:
        lines.append(
            f"unknown event class: {unknown_event_class_value} "
            "(event_class must be one of the canonical kebab-case identifiers; "
            "see schemas/orchestrator-event.yaml)"
        )

    for err in errors:
        path = list(err.absolute_path)

        # Already-handled special cases.
        if _is_event_class_enum_error(err) or _is_top_level_missing_event_class(err):
            continue

        # Suppress redundant root-level unevaluatedProperties when something
        # sharper is already reported.
        if (
            not path
            and err.validator == "unevaluatedProperties"
            and sharper_root_diagnosis
        ):
            continue

        # oneOf failure at root: surface the matching-branch sub-errors when
        # the payload's event_class identifies a real branch; otherwise the
        # top-level enum / missing-required diagnosis already gave the answer.
        if not path and err.validator == "oneOf":
            event_class_value = (
                err.instance.get("event_class")
                if isinstance(err.instance, dict)
                else None
            )
            if event_class_value is None or missing_event_class:
                continue
            if unknown_event_class_value is not None:
                continue

            # Find the branch in oneOf whose properties.event_class.const matches.
            matched_branch_idx: int | None = None
            branches = err.validator_value or []
            for idx, branch_schema in enumerate(branches):
                if not isinstance(branch_schema, dict):
                    continue
                ec_const = (
                    branch_schema.get("properties", {})
                    .get("event_class", {})
                    .get("const")
                )
                if ec_const == event_class_value:
                    matched_branch_idx = idx
                    break

            if matched_branch_idx is None:
                # event_class is a string that didn't match any branch's const
                # (e.g., snake_case form). Top-level enum already covered it.
                continue

            # Group context errors by branch index. jsonschema reports each
            # context error's schema_path as ``[<branch_idx>, <keyword>, ...]``
            # relative to the oneOf array.
            branch_errors_by_index: dict[int, list[ValidationError]] = {}
            for ctx in err.context or []:
                sp = list(ctx.schema_path)
                if not sp or not isinstance(sp[0], int):
                    continue
                branch_errors_by_index.setdefault(sp[0], []).append(ctx)

            matched_errors = branch_errors_by_index.get(matched_branch_idx, [])
            if matched_errors:
                lines.extend(
                    _format_branch_errors(str(event_class_value), matched_errors)
                )
            else:
                # Branch matched but produced no sub-errors recoverable from
                # context; fall back to the generic banner.
                lines.append(f"{_path_pointer(path)}: {err.message}")
            continue

        # additionalProperties at any path: name the offending key(s).
        if err.validator == "additionalProperties":
            anchor = _path_pointer(path) if path else "<root>"
            keys = _ADDITIONAL_PROPERTY_KEY_PATTERN.findall(err.message)
            if keys:
                for key in keys:
                    lines.append(f"{anchor}: additional property '{key}' not allowed")
            else:
                lines.append(f"{anchor}: {err.message}")
            continue

        lines.append(f"{_path_pointer(path)}: {err.message}")

    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="event-validator",
        description=(
            "Validate orchestrator-event YAML files against the canonical "
            "orchestrator-event schema (substrate component 2; ADR-001 / ADR-003)."
        ),
    )
    parser.add_argument(
        "--schema",
        type=pathlib.Path,
        default=None,
        help=(
            "Path to orchestrator-event schema YAML. Defaults to "
            "<repo-root>/schemas/orchestrator-event.yaml resolved from this "
            "module's location."
        ),
    )
    parser.add_argument(
        "--require-nonempty",
        action="store_true",
        help=(
            "Fail with exit code 2 if no event paths are provided. "
            "Default behavior is to pass (no-op gate on empty set, per AC-3)."
        ),
    )
    parser.add_argument(
        "events",
        nargs="*",
        type=pathlib.Path,
        help="Event YAML files to validate.",
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
            schema_path = find_repo_root() / "schemas" / "orchestrator-event.yaml"
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

    if not args.events:
        if args.require_nonempty:
            print(
                "harness-level error: --require-nonempty set but no events provided",
                file=sys.stderr,
            )
            return 2
        return 0

    any_failed = False
    for event_path in args.events:
        try:
            errors = validate_file(event_path, schema)
        except OSError as exc:
            print(
                f"harness-level error: event unreadable: {event_path}: {exc}",
                file=sys.stderr,
            )
            return 2
        except yaml.YAMLError as exc:
            print(
                f"harness-level error: event YAML parse failure: "
                f"{event_path}: {exc}",
                file=sys.stderr,
            )
            return 2

        if errors:
            any_failed = True
            print(format_errors(errors, event_path=event_path))

    return 1 if any_failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
