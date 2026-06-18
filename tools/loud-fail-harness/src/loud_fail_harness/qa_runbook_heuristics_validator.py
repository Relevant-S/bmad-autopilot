"""Shape-contract validator for the `qa-runbook.yaml` `heuristics:` block — Story 19.1.

This module is the **single canonical source of truth** for the closed
seven-heuristic exploratory set (ADR-010 / FR-P2-5). It freezes the set as
:data:`FROZEN_HEURISTIC_NAMES` and validates the two `qa-runbook.yaml` surfaces
that reference heuristic names:

    * ``heuristics.{web,api,mobile}.<heuristic-name>: enabled | disabled`` — the
      per-project-type activation block (AC-3).
    * ``behavioral_plan_overrides.<story-id>.ac_<n>.heuristic_opt_out:
      [<heuristic-name>, ...]`` — the per-AC opt-out escape valve (AC-4).

Seam contract (19.1 ↔ 19.2): 19.1 is **schema + ADR only**. The driving
``qa_exploratory_heuristics.HeuristicKind`` Literal stays at the MVP THREE
(``empty-state`` / ``error-state`` / ``auth-boundary``); 19.2 expands it to the
seven and bumps the marker taxonomy. A contract test asserts the MVP-3 Literal
is a SUBSET of :data:`FROZEN_HEURISTIC_NAMES`, so the schema-level 7-set and the
runtime 3-set cannot silently contradict before 19.2 reconciles them. The 7
names live in EXACTLY ONE place (this constant) — the ADR *describes* the frozen
set, the template *documents* it as commented opt-in defaults, neither is a
competing authority (FR30 / Pattern 1 single-source-of-truth).

Loud-fail discipline (Pattern 5): every rejection surfaces an explicit named
finding + nonzero exit; the validator never silently passes malformed config.
ABSENCE of the `heuristics:` block is NOT a failure (opt-in / FR42 user-owned
file — absence means "all ADR-010 defaults active", mirroring the
`masked_selectors` "no marker on absence" posture). Exit codes mirror
``dependencies_validator``:

    0 — file parses, no heuristics-shape findings.
    1 — at least one validation finding (an AC-5 rejection class).
    2 — harness-level error (file unreadable / YAML parse failure /
        top-level non-mapping).

Input-hardening (Story 24.2 discipline): the closed-set checks on project-type
keys / heuristic names / enablement values are themselves a STRICTER form of
hardening than ``harden_identifier`` (a whitespace/newline/null-byte-injected
value is rejected as an unknown-name / unknown-project-type finding). The
genuinely free-text surface — the ``<story-id>`` and ``ac_<n>`` keys enclosing a
``heuristic_opt_out`` — is routed through ``harden_identifier`` via the
externally-constructed :class:`HeuristicOptOutEntry` model (registered in
``_data/input_hardening_registry.yaml``).

Sensor-not-advisor: the validator REPORTS which rule each finding violates and
where (JSON-pointer-style), with a remediation pointer to ADR-010 / FR-P2-5. It
does not rewrite the runbook or recommend specific heuristic selections.
"""

from __future__ import annotations

import argparse
import importlib.resources
import pathlib
import sys
from collections.abc import Sequence
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from loud_fail_harness._shared import _path_pointer, find_repo_root
from loud_fail_harness.input_hardening import harden_identifier

__all__ = [
    "FROZEN_HEURISTIC_NAMES",
    "HeuristicOptOutEntry",
    "ValidationFinding",
    "format_findings",
    "load_qa_runbook_heuristics",
    "main",
    "validate_qa_runbook_heuristics",
]


#: The CLOSED seven-heuristic exploratory set (ADR-010 / FR-P2-5), in
#: PRD-canonical kebab-case. The MVP trio (Story 4.9) + the four ratified
#: additions (2026-06-10). This constant is the ONLY authority on the set; the
#: ADR describes it, the template documents it, the contract test ties the
#: MVP-3 driving Literal to it. 19.2 expands ``HeuristicKind`` to match.
FROZEN_HEURISTIC_NAMES: frozenset[str] = frozenset(
    {
        # MVP-3 (Story 4.9 — empty-state / error-state / auth-boundary).
        "empty-state",
        "error-state",
        "auth-boundary",
        # +4 (ADR-010, ratified 2026-06-10).
        "rate-limit-boundary",
        "locale-i18n-edge",
        "large-input-boundary",
        "permission-boundary",
    }
)


#: Closed set of project-type keys permitted under ``heuristics:``.
_PROJECT_TYPES: tuple[str, ...] = ("web", "api", "mobile")

#: Closed set of per-heuristic enablement values.
_ENABLEMENT_VALUES: tuple[str, ...] = ("enabled", "disabled")

_ADR_REMEDIATION: str = "(per ADR-010 / FR-P2-5; FROZEN_HEURISTIC_NAMES is the closed set)"

#: Closed set of int knobs permitted under the `flakiness:` block (Story 20.3 /
#: FR-P2-8); each must be an int >= 1 (the Pydantic Field(ge=1) range-validation
#: boundary, asserted here at the qa-runbook surface).
_FLAKINESS_KNOBS: tuple[str, ...] = (
    "threshold_consecutive_runs",
    "threshold_transient_fail_count",
)

_FLAKINESS_REMEDIATION: str = (
    "(per Story 20.3 / FR-P2-8; both flakiness threshold knobs are int >= 1)"
)

_RUN_AGAINST_SELF_REMEDIATION: str = (
    "(per ADR-013 / H11; run_against_self is a bool, default false)"
)


def _frozen_names_rendered() -> str:
    return ", ".join(sorted(FROZEN_HEURISTIC_NAMES))


class ValidationFinding(BaseModel):
    """A single `heuristics:`-shape rule violation.

    NFR-O5 named-invariant diagnostic shape (parallel to
    ``dependencies_validator.ValidationFinding``): ``pointer`` names the
    offending field path, ``message`` states the violated invariant verbatim,
    ``remediation`` names the contract. Frozen for hashability + determinism;
    field declaration order is load-bearing for byte-stable JSON dumps.
    """

    model_config = ConfigDict(frozen=True)

    pointer: str
    message: str
    remediation: str


class HeuristicOptOutEntry(BaseModel):
    """Externally-constructed from a ``behavioral_plan_overrides.<story-id>.ac_<n>``
    block that declares a ``heuristic_opt_out`` list.

    Its job is the orthogonal hostile-input surface (Story 24.2): the
    ``<story-id>`` and ``ac_<n>`` keys are free-text operator-authored mapping
    keys, so they are routed through ``harden_identifier`` (whitespace-only /
    embedded-newline / null-byte rejection). The opt-out *values* are
    closed-set-checked against :data:`FROZEN_HEURISTIC_NAMES` separately in the
    findings walk, not here.

    Frozen for determinism. Construction failure raises ``ValidationError`` —
    the walk converts that into an explicit finding (loud-fail, not silent
    swallow), so the broad ``except ValueError`` Rule-C hazard does not apply.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    ac_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> "HeuristicOptOutEntry":
        harden_identifier(self.story_id, "HeuristicOptOutEntry.story_id")
        harden_identifier(self.ac_key, "HeuristicOptOutEntry.ac_key")
        return self


def _type_name(value: Any) -> str:
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


def _validate_heuristics_block(
    heuristics: object, out: list[ValidationFinding]
) -> None:
    if not isinstance(heuristics, dict):
        out.append(
            _make_finding(
                "/heuristics",
                f"'heuristics' must be a mapping; got {_type_name(heuristics)}",
                _ADR_REMEDIATION,
            )
        )
        return
    for project_type, names_map in heuristics.items():
        pt_path: list[object] = ["heuristics", project_type]
        if project_type not in _PROJECT_TYPES:
            out.append(
                _make_finding(
                    _path_pointer(pt_path),
                    f"unknown project-type key {project_type!r} under 'heuristics' "
                    f"(must be one of {', '.join(_PROJECT_TYPES)})",
                    _ADR_REMEDIATION,
                )
            )
            continue
        if not isinstance(names_map, dict):
            out.append(
                _make_finding(
                    _path_pointer(pt_path),
                    f"'heuristics.{project_type}' must be a mapping; "
                    f"got {_type_name(names_map)}",
                    _ADR_REMEDIATION,
                )
            )
            continue
        for name, value in names_map.items():
            name_path = [*pt_path, name]
            if name not in FROZEN_HEURISTIC_NAMES:
                out.append(
                    _make_finding(
                        _path_pointer(name_path),
                        f"unknown heuristic name {name!r} "
                        f"(must be one of {_frozen_names_rendered()})",
                        _ADR_REMEDIATION,
                    )
                )
                continue
            if not isinstance(value, str) or value not in _ENABLEMENT_VALUES:
                out.append(
                    _make_finding(
                        _path_pointer(name_path),
                        f"enablement value {value!r} not in "
                        f"{{{', '.join(_ENABLEMENT_VALUES)}}}",
                        _ADR_REMEDIATION,
                    )
                )


def _validate_flakiness_block(
    flakiness: object, out: list[ValidationFinding]
) -> None:
    """Type-check the optional `flakiness:` block (Story 20.3 / FR-P2-8). Each of
    the two threshold knobs, WHEN present, must be an int >= 1 (a bool is rejected
    — ``True``/``False`` are int subclasses but not valid threshold counts).
    Absent block / absent knob → no finding (FR42: absence means "defaults apply").
    Emits a :class:`ValidationFinding` (never raises) on a malformed value,
    mirroring :func:`_validate_heuristics_block`'s finding-emitting shape."""
    if not isinstance(flakiness, dict):
        out.append(
            _make_finding(
                "/flakiness",
                f"'flakiness' must be a mapping; got {_type_name(flakiness)}",
                _FLAKINESS_REMEDIATION,
            )
        )
        return
    for knob in _FLAKINESS_KNOBS:
        if knob not in flakiness:
            continue
        value = flakiness[knob]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            out.append(
                _make_finding(
                    _path_pointer(["flakiness", knob]),
                    f"'flakiness.{knob}' must be an int >= 1; got {value!r}",
                    _FLAKINESS_REMEDIATION,
                )
            )


def _validate_run_against_self(
    value: object, out: list[ValidationFinding]
) -> None:
    """Type-check the optional top-level `run_against_self` knob (ADR-013 / H11
    path (a) opt-in). WHEN present it must be a bool; absence means the default
    `false` (FR42 user-owned file — absence is never a finding, mirroring the
    `flakiness:` block). Emits a :class:`ValidationFinding` (never raises) on a
    non-bool value."""
    if not isinstance(value, bool):
        out.append(
            _make_finding(
                "/run_against_self",
                f"'run_against_self' must be a bool; got {_type_name(value)}",
                _RUN_AGAINST_SELF_REMEDIATION,
            )
        )


def _validate_opt_out_list(
    opt_out: object, base_path: list[object], out: list[ValidationFinding]
) -> None:
    if not isinstance(opt_out, list):
        out.append(
            _make_finding(
                _path_pointer(base_path),
                f"'heuristic_opt_out' must be a sequence; got {_type_name(opt_out)}",
                _ADR_REMEDIATION,
            )
        )
        return
    for i, entry in enumerate(opt_out):
        if not isinstance(entry, str) or entry not in FROZEN_HEURISTIC_NAMES:
            out.append(
                _make_finding(
                    _path_pointer([*base_path, i]),
                    f"heuristic_opt_out entry {entry!r} not in "
                    f"FROZEN_HEURISTIC_NAMES (must be one of {_frozen_names_rendered()})",
                    _ADR_REMEDIATION,
                )
            )


def _validate_overrides(overrides: object, out: list[ValidationFinding]) -> None:
    if not isinstance(overrides, dict):
        # Other shape rules of behavioral_plan_overrides are Story 4.1's surface,
        # not this validator's — only flag the type so a non-mapping cannot hide
        # an unvalidated heuristic_opt_out below it.
        out.append(
            _make_finding(
                "/behavioral_plan_overrides",
                f"'behavioral_plan_overrides' must be a mapping; "
                f"got {_type_name(overrides)}",
                "(per Story 4.1 / 19.1 — heuristic_opt_out lives under ac_<n>)",
            )
        )
        return
    for story_id, ac_map in overrides.items():
        if not isinstance(ac_map, dict):
            out.append(
                _make_finding(
                    _path_pointer(["behavioral_plan_overrides", story_id]),
                    f"story entry {story_id!r} must be a mapping; got {_type_name(ac_map)}",
                    "(per Story 4.1 / 19.1 — heuristic_opt_out lives under ac_<n>)",
                )
            )
            continue
        for ac_key, ac_entry in ac_map.items():
            if not isinstance(ac_entry, dict) or "heuristic_opt_out" not in ac_entry:
                continue
            base: list[object] = [
                "behavioral_plan_overrides",
                story_id,
                ac_key,
            ]
            try:
                HeuristicOptOutEntry(story_id=str(story_id), ac_key=str(ac_key))
            except ValidationError as exc:
                out.append(
                    _make_finding(
                        _path_pointer(base),
                        f"hostile input in opt-out key path: {exc.errors()[0]['msg']}",
                        "(per Story 24.2 input-hardening; harden_identifier)",
                    )
                )
            else:
                _validate_opt_out_list(
                    ac_entry["heuristic_opt_out"],
                    [*base, "heuristic_opt_out"],
                    out,
                )


def validate_qa_runbook_heuristics(
    raw: dict, file_path: str
) -> list[ValidationFinding]:
    """Walk the two heuristic-referencing surfaces of a parsed `qa-runbook.yaml`
    and return every shape-rule violation.

    Pure-ish function: empty list = valid (or no heuristics config present);
    non-empty list = at least one AC-5 rejection. Does NOT raise on shape
    violations (those are findings). The returned list is sorted lexicographically
    by ``(pointer, message)`` for determinism. Surfaces NOT owned here (other
    `qa-runbook.yaml` keys, the non-opt-out fields of
    ``behavioral_plan_overrides``) are left untouched — this validator asserts the
    ``heuristics:`` block + per-AC ``heuristic_opt_out`` + the Story 20.3
    ``flakiness:`` threshold knobs (each int >= 1 when present) + the ADR-013
    top-level ``run_against_self`` knob (bool when present).

    ``file_path`` is accepted for API symmetry with :func:`format_findings`.
    """
    del file_path
    out: list[ValidationFinding] = []

    if not isinstance(raw, dict):
        out.append(
            _make_finding(
                "<root>",
                f"top-level must be a YAML mapping; got {_type_name(raw)}",
                _ADR_REMEDIATION,
            )
        )
        return out

    if "heuristics" in raw:
        _validate_heuristics_block(raw["heuristics"], out)
    if "behavioral_plan_overrides" in raw:
        _validate_overrides(raw["behavioral_plan_overrides"], out)
    if "flakiness" in raw:
        _validate_flakiness_block(raw["flakiness"], out)
    if "run_against_self" in raw:
        _validate_run_against_self(raw["run_against_self"], out)

    out.sort(key=lambda f: (f.pointer, f.message))
    return out


def format_findings(findings: list[ValidationFinding], file_path: str) -> str:
    """Render the validator result for stdout. Header naming the file; one line
    per finding (``pointer: message remediation``). Mirrors
    ``dependencies_validator.format_findings``."""
    lines: list[str] = []
    lines.append(f"qa-runbook heuristics validation (ADR-010 / FR-P2-5): {file_path}")
    lines.append("")
    if not findings:
        lines.append("OK: 0 findings.")
        return "\n".join(lines)

    lines.append(f"ERROR: {len(findings)} shape-rule violation(s).")
    for f in findings:
        lines.append(f"  - {f.pointer}: {f.message} {f.remediation}")
    return "\n".join(lines)


def _resolve_template_path() -> pathlib.Path:
    """Resolve the package-bundled `qa-runbook.yaml.template` via
    importlib.resources (cwd-independent; mirrors
    ``input_hardening_gate._resolve_registry_path``). This is the default
    no-arg validation target — the shipped template carries the documented
    (commented-out) defaults, so the no-arg invocation asserts the template
    parses with no malformed heuristics config."""
    return pathlib.Path(
        str(
            importlib.resources.files("loud_fail_harness").joinpath(
                "_data/qa-runbook.yaml.template"
            )
        )
    )


def load_qa_runbook_heuristics(path: pathlib.Path | None = None) -> dict:
    """Load + shape-validate a `qa-runbook.yaml` (or the bundled template);
    return the parsed dict. Convenience helper mirroring
    ``dependencies_validator.load_dependencies``. Raises ``RuntimeError``
    (loud-fail) on a non-mapping top level or any heuristics-shape finding.

    An all-comments / empty file (the shipped template's steady state) parses to
    ``None`` and is treated as ``{}`` — no heuristics config is the opt-in
    default, never a failure (FR42)."""
    if path is None:
        path = _resolve_template_path()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise RuntimeError(
            f"qa-runbook.yaml at {path} did not parse to a YAML mapping at top "
            f"level (got {_type_name(raw)})"
        )
    findings = validate_qa_runbook_heuristics(raw, str(path))
    if findings:
        raise RuntimeError(
            f"qa-runbook.yaml at {path} failed heuristics shape validation:\n"
            + format_findings(findings, str(path))
        )
    return raw


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qa-runbook-heuristics-validator",
        description=(
            "Validate the `heuristics:` block + per-AC `heuristic_opt_out` of a "
            "qa-runbook.yaml against the closed seven-heuristic set "
            "(FROZEN_HEURISTIC_NAMES; ADR-010 / FR-P2-5). Rejects unknown "
            "heuristic names, enablement values outside {enabled, disabled}, "
            "unknown project-type keys, and out-of-set opt-out entries."
        ),
    )
    parser.add_argument(
        "--qa-runbook-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to qa-runbook.yaml (default: the package-bundled "
            "_data/qa-runbook.yaml.template). Test-injection flag; the no-arg "
            "invocation validates the shipped template."
        ),
    )
    return parser


def _display_path(path: pathlib.Path) -> str:
    try:
        repo_root = find_repo_root()
        return str(path.resolve().relative_to(repo_root.resolve()))
    except (RuntimeError, ValueError):
        return str(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    runbook_path: pathlib.Path = (
        args.qa_runbook_path
        if args.qa_runbook_path is not None
        else _resolve_template_path()
    )

    try:
        text = runbook_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"harness-level error: qa-runbook.yaml unreadable: {runbook_path}: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        print(
            f"harness-level error: qa-runbook.yaml YAML parse failure: "
            f"{runbook_path}: {exc}",
            file=sys.stderr,
        )
        return 2

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        print(
            f"harness-level error: qa-runbook.yaml did not parse to a YAML mapping: "
            f"{runbook_path} (got {_type_name(raw)})",
            file=sys.stderr,
        )
        return 2

    findings = validate_qa_runbook_heuristics(raw, str(runbook_path))
    print(format_findings(findings, _display_path(runbook_path)))
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
