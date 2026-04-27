"""Pattern 1 + Pattern 2 naming-convention lint over the cell-1 schema files.

Codifies architecture.md § Implementation Patterns 1 and 2 mechanically — for
the conventions whose mechanical-enforcement-where-feasible position is named
in architecture.md lines 1031-1032 and refined by story 1.12b AC-2 / AC-3.

Contract anchors (story 1.12b):
    * AC-2 (Pattern 1 casing CI lint over the cell-1 schema files):
      structural keys (field names) follow ``snake_case``; identifier values
      and entity-identifier dictionary keys follow ``kebab-case``. The
      position-classification of each surface is encoded in
      :data:`_CASING_RULES`.
    * AC-3 (Pattern 2 marker class naming regex over
      ``schemas/marker-taxonomy.yaml``): each ``marker_class`` field value
      matches :data:`_MARKER_CLASS_REGEX` (≥ 2 kebab-with-acronym segments);
      each ``sub_classifications`` label matches
      :data:`_SUB_CLASSIFICATION_REGEX` (lowercase kebab).
    * AC-6 (single ``naming-lint`` CLI entry; ordering position between
      ``dependencies-validator`` and ``enumeration-check``).
    * AC-7 (test coverage shape — positive + Pattern-1-negative + Pattern-2-
      negative + sub-classification-negative + harness-error + CLI exit-0 +
      not-bailing).

Architecture anchors:
    * architecture.md lines 925-955 — Pattern 1 casing convention prose.
    * architecture.md lines 957-965 — Pattern 2 marker-class naming format.
    * architecture.md line 955 — "Older artifacts already matching the
      convention ... are left as-is." — the basis for not registering enum
      values that hold PRD-canonical lifecycle/finding literals
      (e.g. ``status: pass / fail / blocked``;
      ``bucket: decision_needed / patch / defer / dismiss``;
      ``from_state / to_state`` lifecycle states; ``severity: HIGH/MED/LOW``).
    * architecture.md lines 967-971 — Pattern 3 OTel pass-through attribute
      keys (``prompt.id``, ``claude_code.cost.usage``, etc.) are NOT recast
      under our convention; the walker exempts dotted property names.
    * architecture.md lines 1031-1032 — Enforcement matrix; Pattern 1 cell-1
      schema scope is CI-enforced here; Pattern 2 is CI-enforced here.

Architectural placement: this module is a sibling of ``dependencies_validator``
(per-file shape validator that is **NOT** a sixth substrate component — ADR-003
substrate-component count stays at five). The harness gate count grows to
NINE at this story's landing (envelope-validator, event-validator,
dependencies-validator, naming-lint [this gate], enumeration-check,
fixture-coverage, fr33-fixture-gate, hook-budget-gate, pluggability-gate).

Loud-fail discipline (Pattern 5):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — all rules satisfied (no findings)
        1 — at least one validation finding (Pattern 1 OR Pattern 2 violation)
        2 — harness-level error (file unreadable, YAML parse failure, top-level
            not a YAML mapping)

"Do not bail after first finding" (parallel to ``dependencies_validator`` /
``enumeration_check`` / ``envelope_validator``'s ``iter_errors`` discipline):
    The lint walks both patterns across all four schema files in one pass; the
    returned list is sorted lexicographically by ``(file_path, pointer,
    message)`` for determinism, and the CLI prints every finding before exit.

Sensor-not-advisor (PRD-level invariant):
    Findings name the offending location, the violated regex, and a
    remediation pointer to ``docs/implementation-patterns.md``. The lint does
    not propose rewrites or auto-fix.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections.abc import Sequence
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from loud_fail_harness._shared import _path_pointer, find_repo_root


#: Pattern 1 — snake_case for field names (architecture.md line 932 + line 952).
_SNAKE_CASE_REGEX: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]*$")

#: Pattern 1 — kebab-case for identifier values and entity-identifier keys
#: (architecture.md line 933 + lines 953-955; story 1.12b AC-2). Single-segment
#: names (e.g. ``qa``, ``dev``, ``lad``, ``init``, ``runtime``, ``web``,
#: ``api``, ``mobile``) are permitted via the trailing group's ``*``
#: quantifier. Mixed-case kebab-with-acronym (``LAD-skipped``) and numeric
#: segments (``Tier-3-not-configured``) are accommodated per architecture.md
#: line 961's existing-taxonomy entries.
_KEBAB_CASE_REGEX: re.Pattern[str] = re.compile(
    r"^[A-Za-z][A-Za-z0-9]*(-[A-Za-z0-9]+)*$"
)

#: Pattern 2 — marker class naming (architecture.md line 961; story 1.12b AC-3).
#: Stricter than ``_KEBAB_CASE_REGEX``: requires ≥ 2 segments per the
#: ``<domain>-<state>`` shape, so single-word names (``singleword``) are
#: rejected. Encoded as a named module-level constant per AC-3 to prevent
#: future contributors "fixing" the regex to something stricter that would
#: break existing kebab-with-acronym names without a deliberate Pattern 2
#: amendment.
_MARKER_CLASS_REGEX: re.Pattern[str] = re.compile(
    r"^[A-Za-z][A-Za-z0-9]*(-[A-Za-z0-9]+)+$"
)

#: Pattern 2 — sub-classification labels (story 1.12b AC-3). Strictly lowercase
#: kebab; ≥ 1 segment. Existing examples in ``marker-taxonomy.yaml``:
#: ``port-bind-failed``, ``timeout-exceeded``, ``otel-pipeline-unreachable``.
_SUB_CLASSIFICATION_REGEX: re.Pattern[str] = re.compile(
    r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"
)


#: Position-classification table per AC-2.
#:
#: A static dictionary mapping each cell-1 schema file to a
#: per-position-class list of JSON-pointer-like glob selectors. Glob notation:
#: ``*`` matches a single path segment; ``""`` (empty string) matches the
#: top-level mapping. Path segments are rendered as the YAML keys (string)
#: or list indices (stringified integer).
#:
#: Position semantics:
#:
#:     ``field-name``
#:         At this nodepoint, the keys are FIELD NAMES — each key must match
#:         :data:`_SNAKE_CASE_REGEX`. (Pattern 1's "structural keys describing
#:         a payload's structure" half — architecture.md line 932.)
#:
#:     ``entity-identifier-key``
#:         At this nodepoint, the keys are ENTITY IDENTIFIERS — each key must
#:         match :data:`_KEBAB_CASE_REGEX`. (Pattern 1's
#:         "dictionary-key-as-entity-identifier boundary" half —
#:         architecture.md line 935.)
#:
#:     ``entity-identifier-value``
#:         This LEAF nodepoint holds an ENTITY IDENTIFIER value — the string
#:         at this position must match :data:`_KEBAB_CASE_REGEX`.
#:
#: Positions deliberately NOT registered (per architecture.md line 955
#: "older artifacts already matching the convention ... are left as-is"):
#: enum values inside ``envelope.schema.yaml`` (status / bucket / severity /
#: source / failed_layers items — PRD-canonical lifecycle/finding literals;
#: ``decision_needed`` is the conspicuous example) and inside
#: ``orchestrator-event.yaml``'s lifecycle / role / outcome enums
#: (status / specialist / from_state / to_state / retry_mode / escalation_class
#: / env_kind / outcome / hook_name) — also PRD literals. The Pattern 3
#: kebab-case event-class enum on the discriminator is explicitly registered
#: so format drift on event class names IS caught.
#:
#: OTel pass-through attribute keys (containing a ``.`` character) are
#: exempted programmatically in :func:`_walk` per Pattern 3 / ADR-006
#: Consequence 5.
#:
#: Adding a new structural key to one of the cell-1 schemas: register the
#: key's parent-path under ``field-name`` (or under the appropriate identifier
#: position class) in this table, and add a do/don't worked example to
#: ``docs/implementation-patterns.md``.
_CASING_RULES: dict[str, dict[str, list[str]]] = {
    # ---- envelope.schema.yaml — JSON Schema 2020-12 document --------------
    # User-defined field names live under ``properties:`` (top-level allowed-
    # field allowlist) and ``$defs.<def>.properties:`` (per-def field
    # allowlists for ``finding`` and ``ac_result``). JSON-Schema reserved
    # keywords (``type``, ``required``, ``enum``, ``additionalProperties``,
    # ``$defs``, ``$ref``, ``oneOf``, ``not``, ``anyOf``, ``items``,
    # ``description``, etc.) are NOT user-defined fields and are exempt by
    # this table not registering them.
    "schemas/envelope.schema.yaml": {
        "field-name": [
            "/properties",
            "/$defs/*/properties",
        ],
        "entity-identifier-value": [],
        "entity-identifier-key": [],
    },
    # ---- orchestrator-event.yaml — JSON Schema 2020-12 document -----------
    # User-defined field names under top-level ``properties:`` and inside
    # each ``oneOf`` branch's ``properties:``. Pattern 3 kebab-case event
    # class names are checked at:
    #   /properties/event_class/enum/*           — top-level discriminator enum
    #   /oneOf/*/properties/event_class/const    — per-branch const literal
    "schemas/orchestrator-event.yaml": {
        "field-name": [
            "/properties",
            "/oneOf/*/properties",
        ],
        "entity-identifier-value": [
            "/properties/event_class/enum/*",
            "/oneOf/*/properties/event_class/const",
        ],
        "entity-identifier-key": [],
    },
    # ---- marker-taxonomy.yaml — YAML data file ----------------------------
    # Top-level keys (``schema_version``, ``markers``) and per-marker entry
    # keys (``marker_class``, ``diagnostic_pointer``, ``sub_classifications``)
    # are field names. ``marker_class:`` values are entity-identifier values
    # under Pattern 1's looser kebab regex; Pattern 2's stricter ≥-2-segment
    # regex applies in the dedicated walker (:func:`lint_marker_class_naming`).
    "schemas/marker-taxonomy.yaml": {
        "field-name": [
            "",
            "/markers/*",
        ],
        "entity-identifier-value": [
            "/markers/*/marker_class",
        ],
        "entity-identifier-key": [],
    },
    # ---- dependencies.yaml — YAML data file -------------------------------
    # Three position classes apply:
    #   field-name              — structural keys at top-level, per-dependency
    #                             entry, profile spec, and sub_classifications
    #                             entry.
    #   entity-identifier-key   — dependency identifiers under
    #                             ``/dependencies``; phase keys
    #                             (init/runtime); project-type keys
    #                             (web/api/mobile).
    #   entity-identifier-value — ``profile:`` enum values (total-block, ...);
    #                             ``marker_class:`` / ``emits_marker:`` values
    #                             (kebab marker names).
    # NOT linted: ``version_floor`` strings (versions, not entity ids);
    # ``phase`` numeric strings (e.g. ``"1.5"``); ``condition`` strings (free-
    # form labels, not entity ids); ``diagnostic`` / ``diagnostic_pointer``
    # prose (free text).
    "schemas/dependencies.yaml": {
        "field-name": [
            "",
            "/dependencies/*",
            "/dependencies/*/profiles/*",
            "/dependencies/*/by_project_type/*",
            "/dependencies/*/by_project_type/*/profiles/*",
            "/dependencies/*/profiles/*/sub_classifications/*",
            "/dependencies/*/by_project_type/*/profiles/*/sub_classifications/*",
        ],
        "entity-identifier-value": [
            "/dependencies/*/profiles/*/profile",
            "/dependencies/*/profiles/*/marker_class",
            "/dependencies/*/by_project_type/*/profiles/*/profile",
            "/dependencies/*/by_project_type/*/profiles/*/marker_class",
            "/dependencies/*/profiles/*/sub_classifications/*/emits_marker",
            "/dependencies/*/by_project_type/*/profiles/*/sub_classifications/*/emits_marker",
        ],
        "entity-identifier-key": [
            "/dependencies",
            "/dependencies/*/profiles",
            "/dependencies/*/by_project_type",
            "/dependencies/*/by_project_type/*/profiles",
        ],
    },
    # ---- tea-handoff-contract.yaml — JSON Schema 2020-12 document ---------
    # User-defined field names live under top-level ``properties:`` and inside
    # ``/properties/ac_list/items/properties:`` (the per-AC item shape).
    # JSON-Schema reserved keywords (``type``, ``required``, ``enum``,
    # ``additionalProperties``, ``items``, ``description``, ``minLength``,
    # ``minItems``, ``maxItems``, etc.) are NOT user-defined fields and are
    # exempt by this table not registering them. The ``project_type`` enum
    # values (``web``, ``api``, ``mobile``) are entity-identifier values and
    # match _KEBAB_CASE_REGEX as single-segment names. Story 2.1 AC-3.
    "schemas/tea-handoff-contract.yaml": {
        "field-name": [
            "/properties",
            "/properties/ac_list/items/properties",
        ],
        "entity-identifier-value": [
            "/properties/project_type/enum/*",
        ],
        "entity-identifier-key": [],
    },
}


#: Canonical relative paths for the cell-1 schema files. The CLI's default
#: target set; also the position-classification-table key set. Story 2.1
#: AC-3 added ``schemas/tea-handoff-contract.yaml`` as the fifth cell-1
#: artifact (TEA-handoff dispatch payload contract).
_CANONICAL_TARGETS: tuple[str, ...] = (
    "schemas/envelope.schema.yaml",
    "schemas/orchestrator-event.yaml",
    "schemas/marker-taxonomy.yaml",
    "schemas/dependencies.yaml",
    "schemas/tea-handoff-contract.yaml",
)


_PATTERN_1_REMEDIATION = (
    "(see docs/implementation-patterns.md"
    "#pattern-1-casing-and-file-naming-convention-for-yaml-artifacts)"
)
_PATTERN_2_REMEDIATION = (
    "(see docs/implementation-patterns.md"
    "#pattern-2-marker-class-naming-convention)"
)


class ValidationFinding(BaseModel):
    """A single Pattern 1 or Pattern 2 lint finding.

    NFR-O5 named-invariant diagnostic shape (parallel to
    :class:`dependencies_validator.ValidationFinding`):

        ``file_path``   — repo-relative path of the offending file
                          (e.g. ``schemas/dependencies.yaml``).
        ``pointer``     — JSON-pointer-like location of the offending key
                          or value (e.g. ``/dependencies/Claude_Code``).
        ``message``     — the violated invariant verbatim, naming the
                          offending string and the regex that did not match.
        ``remediation`` — one-line pointer to ``docs/implementation-patterns.md``
                          (Pattern 1 or Pattern 2 anchor as appropriate).

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable output (parallel to story 1.4 / 1.5 / 1.6
    discipline).
    """

    model_config = ConfigDict(frozen=True)

    file_path: str
    pointer: str
    message: str
    remediation: str


def _glob_match(pattern: str, parts: Sequence[str]) -> bool:
    """Match a JSON-pointer-like glob against a list of path segments.

    Pattern syntax:
        ``""``        → matches the empty path (root mapping).
        ``"/foo"``    → matches segments ``["foo"]``.
        ``"/foo/*"``  → matches any segments ``["foo", x]`` for any ``x``.
        ``"/foo/*/bar"`` → matches ``["foo", x, "bar"]`` for any ``x``.

    Each ``*`` matches exactly one segment; this lint does not need recursive
    wildcards (``**``) because every registered position is at a known depth.
    """
    if pattern == "":
        return len(parts) == 0
    pattern_parts = pattern.lstrip("/").split("/")
    if len(pattern_parts) != len(parts):
        return False
    for p, q in zip(pattern_parts, parts, strict=True):
        if p == "*":
            continue
        if p != q:
            return False
    return True


def _path_class_for(file_key: str, parts: list[str]) -> str | None:
    """Return the position-class registered for ``parts`` in ``file_key``'s rules,
    or ``None`` if no rule matches."""
    rules = _CASING_RULES.get(file_key)
    if rules is None:
        return None
    for cls, patterns in rules.items():
        for pattern in patterns:
            if _glob_match(pattern, parts):
                return cls
    return None


def _walk(
    node: Any,
    parts: list[str],
    file_key: str,
    out: list[ValidationFinding],
) -> None:
    """Depth-first walker. Applies the position-classification rules at each path.

    The walker visits every key/value in the parsed YAML tree. At each visited
    nodepoint, it consults :func:`_path_class_for` to determine which Pattern 1
    rule applies (if any). Mappings, sequences, and leaves are handled
    distinctly:

    * **mapping with ``field-name`` rule** — each key is regex-checked for
      snake_case; OTel pass-through keys (containing a ``.``) are exempt per
      Pattern 3.
    * **mapping with ``entity-identifier-key`` rule** — each key is
      regex-checked for kebab-case.
    * **leaf string with ``entity-identifier-value`` rule** — the string is
      regex-checked for kebab-case.

    The walker recurses into every child regardless of position-class, so
    nested rules are reached.
    """
    cls = _path_class_for(file_key, parts)

    if isinstance(node, dict):
        if cls == "field-name":
            for key in node:
                if not isinstance(key, str):
                    continue
                # Pattern 3 / ADR-006 Consequence 5: OTel pass-through attribute
                # keys (e.g. ``prompt.id``, ``claude_code.cost.usage``) are
                # external and not recast under Pattern 1.
                if "." in key:
                    continue
                if not _SNAKE_CASE_REGEX.fullmatch(key):
                    out.append(
                        ValidationFinding(
                            file_path=file_key,
                            pointer=_path_pointer([*parts, key]),
                            message=(
                                f"field name {key!r} does not match snake_case "
                                f"(regex {_SNAKE_CASE_REGEX.pattern})"
                            ),
                            remediation=_PATTERN_1_REMEDIATION,
                        )
                    )
        elif cls == "entity-identifier-key":
            for key in node:
                if not isinstance(key, str):
                    continue
                if not _KEBAB_CASE_REGEX.fullmatch(key):
                    out.append(
                        ValidationFinding(
                            file_path=file_key,
                            pointer=_path_pointer([*parts, key]),
                            message=(
                                f"entity-identifier key {key!r} does not match "
                                f"kebab-case (regex {_KEBAB_CASE_REGEX.pattern})"
                            ),
                            remediation=_PATTERN_1_REMEDIATION,
                        )
                    )
        for raw_key, value in node.items():
            key_str = raw_key if isinstance(raw_key, str) else str(raw_key)
            _walk(value, [*parts, key_str], file_key, out)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk(item, [*parts, str(i)], file_key, out)
    else:
        if cls == "entity-identifier-value" and isinstance(node, str):
            if not _KEBAB_CASE_REGEX.fullmatch(node):
                out.append(
                    ValidationFinding(
                        file_path=file_key,
                        pointer=_path_pointer(parts),
                        message=(
                            f"entity-identifier value {node!r} does not match "
                            f"kebab-case (regex {_KEBAB_CASE_REGEX.pattern})"
                        ),
                        remediation=_PATTERN_1_REMEDIATION,
                    )
                )


def lint_casing(file_key: str, raw: Any) -> list[ValidationFinding]:
    """Pattern 1 walker for one of the cell-1 schema files.

    ``file_key`` MUST be one of :data:`_CANONICAL_TARGETS` for the position-
    classification table to apply; for unknown keys the walker emits no
    findings (no rules match → no checks fire).

    If ``raw`` is not a YAML mapping (programmer-bug surface; ``main`` rejects
    this at the harness boundary with exit 2), a single root-level finding is
    surfaced rather than crashing — same loud-fail posture as
    :func:`dependencies_validator.validate_dependencies`.
    """
    out: list[ValidationFinding] = []
    if not isinstance(raw, dict):
        out.append(
            ValidationFinding(
                file_path=file_key,
                pointer="<root>",
                message=(
                    f"top-level must be a YAML mapping; got {type(raw).__name__}"
                ),
                remediation=_PATTERN_1_REMEDIATION,
            )
        )
        return out
    _walk(raw, [], file_key, out)
    return out


def lint_marker_class_naming(raw: Any) -> list[ValidationFinding]:
    """Pattern 2 walker over ``schemas/marker-taxonomy.yaml`` (story 1.12b AC-3).

    Validates each marker entry's ``marker_class`` value against
    :data:`_MARKER_CLASS_REGEX` (≥ 2 kebab-with-acronym segments) and each
    ``sub_classifications`` list element against
    :data:`_SUB_CLASSIFICATION_REGEX` (lowercase kebab; ≥ 1 segment).

    Pattern 1's ``lint_casing`` already surfaces ``marker_class`` values that
    fail the looser ``_KEBAB_CASE_REGEX`` (e.g. ``state_recovery_drift`` with
    underscores). Pattern 2 catches the stricter ≥-2-segment shape (e.g.
    ``singleword`` passes Pattern 1 but fails Pattern 2). Both findings can
    fire for the same value when both rules are violated; tests assert they
    co-exist deterministically.
    """
    file_key = "schemas/marker-taxonomy.yaml"
    out: list[ValidationFinding] = []
    if not isinstance(raw, dict):
        return out
    markers = raw.get("markers")
    if not isinstance(markers, list):
        return out
    for i, entry in enumerate(markers):
        if not isinstance(entry, dict):
            continue
        marker_class_value = entry.get("marker_class")
        if isinstance(marker_class_value, str):
            if not _MARKER_CLASS_REGEX.fullmatch(marker_class_value):
                out.append(
                    ValidationFinding(
                        file_path=file_key,
                        pointer=_path_pointer(["markers", i, "marker_class"]),
                        message=(
                            f"marker class {marker_class_value!r} does not "
                            "match the marker-class-name format "
                            f"(regex {_MARKER_CLASS_REGEX.pattern}; ≥ 2 "
                            "kebab-case segments per architecture.md line 961)"
                        ),
                        remediation=_PATTERN_2_REMEDIATION,
                    )
                )
        sub_classifications = entry.get("sub_classifications")
        if isinstance(sub_classifications, list):
            for j, label in enumerate(sub_classifications):
                if not isinstance(label, str):
                    continue
                if not _SUB_CLASSIFICATION_REGEX.fullmatch(label):
                    out.append(
                        ValidationFinding(
                            file_path=file_key,
                            pointer=_path_pointer(
                                ["markers", i, "sub_classifications", j]
                            ),
                            message=(
                                f"sub-classification label {label!r} does not "
                                "match the sub-classification format "
                                f"(regex {_SUB_CLASSIFICATION_REGEX.pattern})"
                            ),
                            remediation=_PATTERN_2_REMEDIATION,
                        )
                    )
    return out


def _resolve_file_key(path: pathlib.Path) -> str:
    """Resolve an on-disk path to its canonical position-classification key.

    Recognized basenames map to ``schemas/<basename>``; anything else returns
    the path's string form (and the position-classification table emits no
    findings for unknown keys, which is the deliberate posture for tests
    that pass ad-hoc fixtures with non-canonical names).
    """
    name = path.name
    canonical_basenames = {
        "envelope.schema.yaml",
        "orchestrator-event.yaml",
        "marker-taxonomy.yaml",
        "dependencies.yaml",
        "tea-handoff-contract.yaml",
    }
    if name in canonical_basenames:
        return f"schemas/{name}"
    return str(path)


def _format_findings(findings: list[ValidationFinding]) -> str:
    """Render the validator result for stdout.

    Mirrors the "header + per-finding line" shape of
    :func:`dependencies_validator.format_findings`.
    """
    if not findings:
        return "Naming lint (Pattern 1 + Pattern 2): OK; 0 findings."
    lines = [
        f"Naming lint (Pattern 1 + Pattern 2): {len(findings)} finding(s)."
    ]
    for f in findings:
        lines.append(
            f"  - {f.file_path}{f.pointer}: {f.message} {f.remediation}"
        )
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="naming-lint",
        description=(
            "Pattern 1 (YAML casing convention) + Pattern 2 (marker class "
            "naming) static linter over the cell-1 schema files. Story "
            "1.12b (four schemas) + Story 2.1 AC-3 (tea-handoff-contract.yaml); "
            "architecture.md § Implementation Patterns lines 919-1006."
        ),
    )
    parser.add_argument(
        "schemas",
        nargs="*",
        type=pathlib.Path,
        help=(
            "Optional explicit schema paths. Default: discover the five cell-1 "
            "schemas (envelope.schema.yaml, orchestrator-event.yaml, "
            "marker-taxonomy.yaml, dependencies.yaml, tea-handoff-contract.yaml) "
            "under the repo root via find_repo_root. Test-injection flag; CI "
            "invocations omit it."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point — exit codes 0 / 1 / 2 per the loud-fail discipline."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    targets: list[tuple[str, pathlib.Path]]
    if args.schemas:
        targets = [(_resolve_file_key(p), p) for p in args.schemas]
    else:
        try:
            repo_root = find_repo_root()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        targets = [
            (rel, repo_root / rel) for rel in _CANONICAL_TARGETS
        ]

    findings: list[ValidationFinding] = []
    for file_key, path in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(
                f"harness-level error: schema file unreadable: {path}: {exc}",
                file=sys.stderr,
            )
            return 2
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            print(
                f"harness-level error: YAML parse failure: {path}: {exc}",
                file=sys.stderr,
            )
            return 2
        if not isinstance(raw, dict):
            print(
                f"harness-level error: top-level not a YAML mapping: {path} "
                f"(got {type(raw).__name__})",
                file=sys.stderr,
            )
            return 2
        findings.extend(lint_casing(file_key, raw))
        if file_key == "schemas/marker-taxonomy.yaml":
            findings.extend(lint_marker_class_naming(raw))

    findings.sort(key=lambda f: (f.file_path, f.pointer, f.message))
    print(_format_findings(findings))
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
