"""SDN-001 schema-content validator for ``schemas/dependencies.yaml``.

This module enforces the SDN-001 shape contract for the cell-1 dependency
manifest landed by story 1.6 — the canonical structure documented in
architecture.md lines 624-730. Per-rule diagnostics follow NFR-O5's
"named-invariant + remediation pointer" discipline; the loud-fail exit-code
matrix mirrors stories 1.2 / 1.3 / 1.5.

Architectural placement (story 1.6 Dev Notes "Substrate component count
stays at five"): this validator is structurally a sibling of the five
substrate-component modules (envelope_validator, event_validator,
reconciler, enumeration_check, fixture_coverage) but it is **NOT a sixth
substrate component**. ADR-003's substrate count stays at five
(Consequence 1 + SDN-001 cross-coupling at architecture.md line 1253).
``dependencies_validator`` is a *schema-content validator* analogous to
``envelope_validator`` and ``event_validator`` (which validate JSON-Schema
instance documents); this module validates the SDN-001 cell-1 YAML data
shape. It has no Layer A / B / C framing, no reconciliation duty, and no
enumeration-equivalence to maintain — those are the substrate components'
jobs.

Downstream consumers (per SDN-001 § Consumers):
    * ``/bmad-automation init`` precondition checks (Epic 7 Story 7.3) —
      consume the parsed shape via :func:`load_dependencies` per FR37/FR38.
    * Orchestrator-skill runtime degradation handler (Epic 6) — consumes
      ``runtime.profile`` per dependency per NFR-I3.
    * PR-bundle assembly (Epic 6 / FR30) — marker emissions surfaced from
      runtime degradation flow through ADR-003 substrate components 3 + 4.

Cross-story seam contract (1.5 ↔ 1.6): this validator enforces the SDN-001
*shape*; story 1.5's :mod:`loud_fail_harness.enumeration_check` enforces
``marker_class`` / ``emits_marker`` *cross-references* against
``schemas/marker-taxonomy.yaml``. Separate concerns; both run in CI per the
gate-ordering rationale (dependencies-validator runs BEFORE enumeration-
check so a malformed dependencies.yaml surfaces with the tighter NFR-O5
named-invariant diagnostic FIRST, before enumeration_check's broader
"did not parse to YAML mapping" exit-2 path fires).

Loud-fail discipline (Pattern 5):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — file parses, all SDN-001-shape rules satisfied (no findings)
        1 — at least one validation finding (shape rule violation per AC-2)
        2 — harness-level error (file unreadable, YAML parse failure, file
            did not parse to a YAML mapping)

"Do not bail after first finding" (parallel to story 1.5's AC-3 / AC-4 +
envelope_validator's ``iter_errors`` discipline):
    :func:`validate_dependencies` walks the parsed YAML dict and emits one
    :class:`ValidationFinding` per shape rule violation; the returned list
    is sorted lexicographically by ``(pointer, message)`` for determinism.
    The CLI prints every finding to stdout before exiting non-zero.

Sensor-not-advisor (PRD-level invariant; same posture as reconciler +
enumeration_check):
    The validator REPORTS what shape rule each finding violates and where,
    with a remediation pointer to SDN-001 / NFR-I3. It does NOT recommend
    specific schema rewrites, suggest dependency additions, or auto-rewrite
    the schema.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Sequence
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from loud_fail_harness._shared import _path_pointer, find_repo_root

#: Closed set of failure profile values (per SDN-001 / NFR-I3).
_FAILURE_PROFILES: tuple[str, ...] = ("total-block", "graceful-degrade", "opt-in-skip")

#: Closed set of lifecycle phase keys (per SDN-001).
_LIFECYCLE_PHASES: tuple[str, ...] = ("init", "runtime")

#: Closed set of project-type keys for ``by_project_type`` (per SDN-001 +
#: PRD Runtime Compatibility Matrix project-type triad).
_PROJECT_TYPES: tuple[str, ...] = ("web", "api", "mobile")

#: Top-level keys permitted on a ``dependencies.yaml`` document.
_TOP_LEVEL_ALLOWED: tuple[str, ...] = ("schema_version", "dependencies")

#: Keys permitted on a single ``dependencies.<dep>`` entry.
_DEPENDENCY_ALLOWED: tuple[str, ...] = (
    "version_floor",
    "version_ceiling_policy",
    "version_policy",
    "phase",
    "profiles",
    "by_project_type",
)

#: Keys permitted inside a profile-spec mapping (the value at
#: ``profiles.<phase>`` or ``by_project_type.<type>.profiles.<phase>``).
_PROFILE_SPEC_ALLOWED: tuple[str, ...] = (
    "profile",
    "diagnostic",
    "diagnostic_pointer",
    "marker_class",
    "sub_classifications",
)

#: Keys permitted inside a project-type-entry mapping (the value at
#: ``by_project_type.<type>``).
_PROJECT_TYPE_VALUE_ALLOWED: tuple[str, ...] = ("profiles",)

#: Keys permitted inside a single ``sub_classifications[i]`` entry.
_SUB_CLASSIFICATION_ALLOWED: tuple[str, ...] = (
    "condition",
    "emits_marker",
    "silent",
    "diagnostic_pointer",
)


class ValidationFinding(BaseModel):
    """A single SDN-001 shape-rule violation.

    NFR-O5 named-invariant diagnostic shape: every finding names

    * ``pointer``  — the offending field path as a JSON-pointer-style string
      (e.g. ``/dependencies/playwright-mcp/by_project_type/web/profiles/runtime/marker_class``).
    * ``message``  — the violated invariant verbatim (e.g.
      ``"unknown failure_profile value 'bogus' (must be one of total-block, graceful-degrade, opt-in-skip)"``).
    * ``remediation`` — a one-line NFR-O5 pointer naming the SDN-001 contract
      (e.g. ``"(per SDN-001 / NFR-I3)"``).

    Frozen for hashability + determinism; field declaration order is
    load-bearing for byte-stable JSON dumps (parallel to story 1.4's frozen
    Pydantic models + story 1.5's :class:`Reference`).
    """

    model_config = ConfigDict(frozen=True)

    pointer: str
    message: str
    remediation: str


def _type_name(value: Any) -> str:
    """Render a YAML-load-time Python value's type for diagnostic prose."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, dict):
        return "mapping"
    if isinstance(value, list):
        return "sequence"
    return type(value).__name__


def _make_finding(pointer: str, message: str, remediation: str) -> ValidationFinding:
    return ValidationFinding(pointer=pointer, message=message, remediation=remediation)


def _validate_sub_classifications(
    entries: object,
    base_path: list[object],
    out: list[ValidationFinding],
) -> None:
    if not isinstance(entries, list):
        out.append(
            _make_finding(
                _path_pointer(base_path),
                f"'sub_classifications' must be a sequence; got {_type_name(entries)}",
                "(per SDN-001)",
            )
        )
        return
    for i, entry in enumerate(entries):
        entry_path = [*base_path, i]
        if not isinstance(entry, dict):
            out.append(
                _make_finding(
                    _path_pointer(entry_path),
                    f"sub_classifications[{i}] must be a mapping; got {_type_name(entry)}",
                    "(per SDN-001)",
                )
            )
            continue

        if "condition" not in entry:
            out.append(
                _make_finding(
                    _path_pointer([*entry_path, "condition"]),
                    f"sub_classifications[{i}]: missing required field 'condition'",
                    "(per SDN-001)",
                )
            )
        elif not isinstance(entry["condition"], str):
            out.append(
                _make_finding(
                    _path_pointer([*entry_path, "condition"]),
                    f"sub_classifications[{i}]: 'condition' must be a string; "
                    f"got {_type_name(entry['condition'])}",
                    "(per SDN-001)",
                )
            )

        has_emits = "emits_marker" in entry
        has_silent = "silent" in entry
        if has_emits and has_silent:
            out.append(
                _make_finding(
                    _path_pointer(entry_path),
                    f"sub_classifications[{i}]: must declare exactly one of "
                    "'emits_marker' or 'silent: true'; both present",
                    "(per SDN-001)",
                )
            )
        elif not has_emits and not has_silent:
            out.append(
                _make_finding(
                    _path_pointer(entry_path),
                    f"sub_classifications[{i}]: must declare exactly one of "
                    "'emits_marker' or 'silent: true'; neither present",
                    "(per SDN-001)",
                )
            )
        else:
            if has_emits and not isinstance(entry["emits_marker"], str):
                out.append(
                    _make_finding(
                        _path_pointer([*entry_path, "emits_marker"]),
                        f"sub_classifications[{i}]: 'emits_marker' must be a string; "
                        f"got {_type_name(entry['emits_marker'])}",
                        "(per SDN-001)",
                    )
                )
            if has_silent and entry["silent"] is not True:
                out.append(
                    _make_finding(
                        _path_pointer([*entry_path, "silent"]),
                        f"sub_classifications[{i}]: 'silent' must be the literal "
                        f"boolean true; got {entry['silent']!r}",
                        "(per SDN-001)",
                    )
                )

        for key in entry:
            if key not in _SUB_CLASSIFICATION_ALLOWED:
                out.append(
                    _make_finding(
                        _path_pointer([*entry_path, key]),
                        f"sub_classifications[{i}]: unknown field '{key}' "
                        f"(allowed: {', '.join(_SUB_CLASSIFICATION_ALLOWED)})",
                        "(per SDN-001)",
                    )
                )


def _validate_profile_spec(
    profile_spec: object,
    base_path: list[object],
    out: list[ValidationFinding],
) -> None:
    if not isinstance(profile_spec, dict):
        out.append(
            _make_finding(
                _path_pointer(base_path),
                f"profile spec must be a mapping; got {_type_name(profile_spec)}",
                "(per SDN-001)",
            )
        )
        return

    if "profile" not in profile_spec:
        out.append(
            _make_finding(
                _path_pointer([*base_path, "profile"]),
                "missing required field 'profile'",
                "(per SDN-001 / NFR-I3)",
            )
        )
    else:
        profile_value = profile_spec["profile"]
        if not isinstance(profile_value, str) or profile_value not in _FAILURE_PROFILES:
            out.append(
                _make_finding(
                    _path_pointer([*base_path, "profile"]),
                    f"unknown failure_profile value {profile_value!r} "
                    f"(must be one of {', '.join(_FAILURE_PROFILES)})",
                    "(per SDN-001 / NFR-I3)",
                )
            )
        else:
            # Profile-specific required-field rules.
            if profile_value == "total-block":
                # Diagnostic is required at the init phase (the operator-facing
                # precondition-check moment per FR37 / NFR-O5 — the operator
                # needs an actionable hint to fix the missing precondition).
                # SDN-001's canonical structure (architecture.md lines 624-730)
                # has runtime total-block entries without diagnostic on
                # claude-code, bmad-core, tea-module: at runtime, total-block
                # halts the loop with marker-driven run-state preservation, not
                # a per-dep diagnostic. The phase-conditional rule preserves
                # both surfaces.
                phase_key = base_path[-1] if base_path else None
                if phase_key == "init" and "diagnostic" not in profile_spec:
                    out.append(
                        _make_finding(
                            _path_pointer([*base_path, "diagnostic"]),
                            "missing required field 'diagnostic' for total-block profile at init phase",
                            "(per SDN-001; total-block at init requires actionable "
                            "diagnostic per FR37 / NFR-O5)",
                        )
                    )
            elif profile_value == "graceful-degrade":
                for required_field in ("marker_class", "diagnostic_pointer"):
                    if required_field not in profile_spec:
                        out.append(
                            _make_finding(
                                _path_pointer([*base_path, required_field]),
                                f"missing required field '{required_field}' "
                                "for graceful-degrade profile",
                                "(per SDN-001; graceful-degrade requires "
                                "marker emission + diagnostic pointer per "
                                "NFR-I3 / FR30)",
                            )
                        )
            # opt-in-skip has no required fields beyond 'profile' itself; the
            # optional sub_classifications are validated below regardless of
            # profile value.

    if "sub_classifications" in profile_spec:
        _validate_sub_classifications(
            profile_spec["sub_classifications"],
            [*base_path, "sub_classifications"],
            out,
        )

    for key in profile_spec:
        if key not in _PROFILE_SPEC_ALLOWED:
            out.append(
                _make_finding(
                    _path_pointer([*base_path, key]),
                    f"unknown field '{key}' "
                    f"(allowed: {', '.join(_PROFILE_SPEC_ALLOWED)})",
                    "(per SDN-001)",
                )
            )


def _validate_profiles_map(
    profiles: object,
    base_path: list[object],
    out: list[ValidationFinding],
) -> None:
    if not isinstance(profiles, dict):
        out.append(
            _make_finding(
                _path_pointer(base_path),
                f"'profiles' must be a mapping; got {_type_name(profiles)}",
                "(per SDN-001)",
            )
        )
        return
    for phase, profile_spec in profiles.items():
        phase_path = [*base_path, phase]
        if phase not in _LIFECYCLE_PHASES:
            out.append(
                _make_finding(
                    _path_pointer(phase_path),
                    f"unknown lifecycle phase {phase!r} "
                    f"(must be one of {', '.join(_LIFECYCLE_PHASES)})",
                    "(per SDN-001)",
                )
            )
            # Skip recursion so we don't multiply diagnostics for the same
            # root cause (a misnamed phase is one error, not many).
            continue
        _validate_profile_spec(profile_spec, phase_path, out)


def _validate_by_project_type(
    by_pt: object,
    base_path: list[object],
    out: list[ValidationFinding],
) -> None:
    if not isinstance(by_pt, dict):
        out.append(
            _make_finding(
                _path_pointer(base_path),
                f"'by_project_type' must be a mapping; got {_type_name(by_pt)}",
                "(per SDN-001)",
            )
        )
        return
    for project_type, value in by_pt.items():
        pt_path = [*base_path, project_type]
        if project_type not in _PROJECT_TYPES:
            out.append(
                _make_finding(
                    _path_pointer(pt_path),
                    f"unknown project type {project_type!r} "
                    f"(must be one of {', '.join(_PROJECT_TYPES)})",
                    "(per SDN-001)",
                )
            )
            continue
        if not isinstance(value, dict):
            out.append(
                _make_finding(
                    _path_pointer(pt_path),
                    f"project-type entry must be a mapping; got {_type_name(value)}",
                    "(per SDN-001)",
                )
            )
            continue
        if "profiles" not in value:
            out.append(
                _make_finding(
                    _path_pointer([*pt_path, "profiles"]),
                    "missing required field 'profiles'",
                    "(per SDN-001)",
                )
            )
        else:
            _validate_profiles_map(value["profiles"], [*pt_path, "profiles"], out)
        for key in value:
            if key not in _PROJECT_TYPE_VALUE_ALLOWED:
                out.append(
                    _make_finding(
                        _path_pointer([*pt_path, key]),
                        f"unknown field '{key}' under project-type entry "
                        f"(allowed: {', '.join(_PROJECT_TYPE_VALUE_ALLOWED)})",
                        "(per SDN-001)",
                    )
                )


def _validate_dependency_entry(
    dep_id: str,
    entry: object,
    out: list[ValidationFinding],
) -> None:
    base_path: list[object] = ["dependencies", dep_id]
    if not isinstance(entry, dict):
        out.append(
            _make_finding(
                _path_pointer(base_path),
                f"dependency '{dep_id}' must be a mapping; got {_type_name(entry)}",
                "(per SDN-001)",
            )
        )
        return

    has_profiles = "profiles" in entry
    has_by_pt = "by_project_type" in entry
    if has_profiles and has_by_pt:
        out.append(
            _make_finding(
                _path_pointer(base_path),
                f"'{dep_id}': must declare exactly one of 'profiles' (top-level) "
                "or 'by_project_type' (project-type-conditional); both present",
                "(per SDN-001 mutual exclusion)",
            )
        )
    elif not has_profiles and not has_by_pt:
        out.append(
            _make_finding(
                _path_pointer(base_path),
                f"'{dep_id}': must declare exactly one of 'profiles' (top-level) "
                "or 'by_project_type' (project-type-conditional); neither present",
                "(per SDN-001 mutual exclusion)",
            )
        )

    if has_profiles:
        _validate_profiles_map(entry["profiles"], [*base_path, "profiles"], out)
    if has_by_pt:
        _validate_by_project_type(
            entry["by_project_type"], [*base_path, "by_project_type"], out
        )

    for key in entry:
        if key not in _DEPENDENCY_ALLOWED:
            out.append(
                _make_finding(
                    _path_pointer([*base_path, key]),
                    f"'{dep_id}': unknown field '{key}' "
                    f"(allowed: {', '.join(_DEPENDENCY_ALLOWED)})",
                    "(per SDN-001)",
                )
            )


def validate_dependencies(raw: dict, file_path: str) -> list[ValidationFinding]:
    """Walk the parsed YAML dict and return every SDN-001 shape-rule violation.

    Pure function: empty list = valid; non-empty list = at least one shape
    rule violation. Does NOT raise on shape violations (those are findings,
    not exceptions); only :class:`pydantic.ValidationError` from
    :class:`ValidationFinding` model construction itself can propagate, and
    that is a caller bug per Pattern 5 + story 1.4 / 1.5 discipline.

    The returned list is sorted lexicographically by ``(pointer, message)``
    for determinism (parallel to 1.4 / 1.5 + AC-6 "Determinism" case). Walk
    order alone is insufficient; an explicit sort keeps diagnostic output
    stable across runs and across YAML-loader versions.

    The ``file_path`` parameter is part of the public API shape (per AC-2)
    so future callers can attach file context to rendered output without
    re-plumbing; finding bodies use JSON-pointer paths rooted at the YAML
    document, not file paths, so the parameter is currently consumed only
    by :func:`format_findings` (the rendering layer that has both inputs).
    """
    del file_path  # accepted for API symmetry with format_findings
    out: list[ValidationFinding] = []

    if not isinstance(raw, dict):
        # Programmer-bug guard: main() rejects non-dict YAML at the harness
        # boundary (exit 2 + stderr). If a non-dict still reaches this
        # function (direct-API misuse), surface a single root-level finding
        # rather than crashing — same loud-fail posture, different surface.
        out.append(
            _make_finding(
                "<root>",
                f"top-level must be a YAML mapping; got {_type_name(raw)}",
                "(per SDN-001 § Schema)",
            )
        )
        return out

    if "schema_version" not in raw:
        out.append(
            _make_finding(
                "/schema_version",
                "missing required field 'schema_version'",
                "(per SDN-001 Versioning Discipline)",
            )
        )
    elif not isinstance(raw["schema_version"], str):
        out.append(
            _make_finding(
                "/schema_version",
                f"'schema_version' must be a string; "
                f"got {_type_name(raw['schema_version'])}",
                "(per SDN-001 Versioning Discipline)",
            )
        )

    if "dependencies" not in raw:
        out.append(
            _make_finding(
                "/dependencies",
                "missing required field 'dependencies'",
                "(per SDN-001 § Schema)",
            )
        )
    else:
        deps = raw["dependencies"]
        if not isinstance(deps, dict):
            out.append(
                _make_finding(
                    "/dependencies",
                    f"'dependencies' must be a mapping; got {_type_name(deps)}",
                    "(per SDN-001 § Schema)",
                )
            )
        else:
            for dep_id, entry in deps.items():
                _validate_dependency_entry(str(dep_id), entry, out)

    for key in raw:
        if key not in _TOP_LEVEL_ALLOWED:
            out.append(
                _make_finding(
                    f"/{key}",
                    f"unknown top-level key '{key}' "
                    "(per SDN-001, only 'schema_version' and 'dependencies' "
                    "are permitted)",
                    "(per SDN-001 § Schema)",
                )
            )

    out.sort(key=lambda f: (f.pointer, f.message))
    return out


def format_findings(findings: list[ValidationFinding], file_path: str) -> str:
    """Render the validator result for stdout.

    Header naming the file under inspection; one line per finding with
    ``pointer + ": " + message + " " + remediation``. Mirrors the
    "name the offending entity + remediation pointer" discipline from
    1.2 / 1.3 / 1.5.
    """
    lines: list[str] = []
    lines.append(f"Dependencies schema validation (SDN-001): {file_path}")
    lines.append("")
    if not findings:
        lines.append("OK: 0 findings.")
        return "\n".join(lines)

    lines.append(f"ERROR: {len(findings)} shape-rule violation(s).")
    for f in findings:
        lines.append(f"  - {f.pointer}: {f.message} {f.remediation}")
    return "\n".join(lines)


def load_dependencies(path: pathlib.Path | None = None) -> dict:
    """Load + shape-validate ``schemas/dependencies.yaml``; return parsed dict.

    Convenience helper for downstream callers (Epic 7 init per FR37/FR38;
    Epic 6 runtime degradation per NFR-I3) — distinct from
    :func:`validate_dependencies` which returns the findings list for
    CLI / test consumption. If the on-disk file's shape is invalid, raises
    ``RuntimeError`` (loud-fail) with the formatted findings string.
    Parallel to story 1.4's ``load_marker_taxonomy`` API pattern.

    Default path resolves to ``<repo-root>/schemas/dependencies.yaml`` via
    :func:`loud_fail_harness._shared.find_repo_root`. Pass an explicit
    ``path`` to override (e.g. for tests or alternate-location consumers).
    """
    if path is None:
        path = find_repo_root() / "schemas" / "dependencies.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(
            f"dependencies.yaml at {path} did not parse to a YAML mapping at "
            f"top level (got {_type_name(raw)})"
        )
    findings = validate_dependencies(raw, str(path))
    if findings:
        raise RuntimeError(
            f"dependencies.yaml at {path} failed SDN-001 shape validation:\n"
            + format_findings(findings, str(path))
        )
    return raw


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dependencies-validator",
        description=(
            "Validate schemas/dependencies.yaml against the SDN-001 shape "
            "contract (failure_profile enum closure, required fields per "
            "profile, profiles-vs-by_project_type mutual exclusion, "
            "sub_classifications shape rules). Cell-1 schema-content "
            "validator; ADR-002 + ADR-003 (extended) + SDN-001 + "
            "NFR-I1 / NFR-I3."
        ),
    )
    parser.add_argument(
        "--dependencies-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to dependencies.yaml (default: "
            "<repo-root>/schemas/dependencies.yaml). Test-injection flag; "
            "CI invocations omit it."
        ),
    )
    return parser


def _display_path(path: pathlib.Path) -> str:
    """Render ``path`` relative to repo root if possible; absolute otherwise.

    Test invocations pass ``tmp_path`` files outside the repo — for those
    the relative resolution fails and the absolute path is returned, which
    is still informative in stdout. Canonical CI invocations use the
    in-repo schema file and produce stable relative paths like
    ``schemas/dependencies.yaml`` for diff-friendly output.
    """
    try:
        repo_root = find_repo_root()
        return str(path.resolve().relative_to(repo_root.resolve()))
    except (RuntimeError, ValueError):
        return str(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    deps_path: pathlib.Path
    if args.dependencies_path is not None:
        deps_path = args.dependencies_path
    else:
        try:
            deps_path = find_repo_root() / "schemas" / "dependencies.yaml"
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    try:
        text = deps_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"harness-level error: dependencies.yaml unreadable: {deps_path}: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        print(
            f"harness-level error: dependencies.yaml YAML parse failure: "
            f"{deps_path}: {exc}",
            file=sys.stderr,
        )
        return 2

    if not isinstance(raw, dict):
        print(
            f"harness-level error: dependencies.yaml did not parse to a YAML mapping: "
            f"{deps_path} (got {_type_name(raw)})",
            file=sys.stderr,
        )
        return 2

    findings = validate_dependencies(raw, str(deps_path))
    print(format_findings(findings, _display_path(deps_path)))
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
