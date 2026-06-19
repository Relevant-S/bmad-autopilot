"""`*_emissions` → bundle-render-path gate — Story 22.6 G2 (Epic 20 retro Action #1).

Build-time gate (NOT a runtime marker — like sibling gates 22.4 / 24.2 / 24.3 it
emits :class:`Finding`s + a nonzero exit, never a persisted run-state marker).
Asserts that **every** typed ``*_emissions[]`` field declared under
``properties:`` in ``schemas/envelope.schema.yaml`` has a corresponding render
path in ``bundle_assembly.py``, via the closed field→render-surface registry
``_data/emissions_render_surfaces.yaml``. Enforces BOTH directions so the real
risk the gate exists to catch — a future ``*_emissions`` field shipped without a
bundle render path, silently dropped from the PR bundle — fails the build:

  * ``schema-field-unregistered`` — a schema ``*_emissions`` field is absent from
    the registry (the new-emissions-field-without-render-path hazard).
  * ``registry-field-not-in-schema`` — a registry key is not a live schema field
    (registry rot — the field was renamed/removed but the registry kept it).
  * ``render-function-not-defined`` — a registered render function is not
    ``def``-defined in ``bundle_assembly.py``.
  * ``render-function-not-invoked`` — a registered render function is defined but
    never called in ``bundle_assembly.py`` (dead render path).
  * ``field-not-accessed`` — the field literal (``qa_envelope.get("<field>")``)
    is not accessed anywhere in ``bundle_assembly.py``.

This GENERALIZES Story 21.0's per-class greppable pins (which pinned individual
marker classes) into a field-driven structural check.

## CI posture

Unlike the outer-workspace gates (forward-pointer-drift / done-story-review-
ledger), every input here — the envelope schema, the registry, and
``bundle_assembly.py`` — lives in the inner repo, so the gate runs as a real
``ci.yml`` step (``uv run emissions-render-path-gate``) alongside the
emission-gate grouping, mirroring ``input-hardening-gate``'s real-CI-step
posture.
"""

from __future__ import annotations

import argparse
import importlib.resources
import io
import pathlib
import re
import sys
import tokenize as _tok
from collections.abc import Sequence
from typing import Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from ._shared import find_repo_root

__all__ = [
    "Finding",
    "GateResult",
    "discover_emissions_fields",
    "evaluate_emissions_render_paths",
    "format_findings",
    "load_render_surface_registry",
    "main",
    "run_emissions_render_path_gate",
]

_EMISSIONS_SUFFIX: Final[str] = "_emissions"
_ENVELOPE_SCHEMA_REL: Final[str] = "schemas/envelope.schema.yaml"
_BUNDLE_SOURCE_REL: Final[str] = (
    "tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py"
)
_REGISTRY_RESOURCE: Final[str] = "_data/emissions_render_surfaces.yaml"

FindingRule = Literal[
    "schema-field-unregistered",
    "registry-field-not-in-schema",
    "render-function-not-defined",
    "render-function-not-invoked",
    "field-not-accessed",
]


class Finding(BaseModel):
    """A single render-path violation.

    Frozen for determinism; field declaration order is load-bearing for
    byte-stable dumps (mirrors :class:`pluggability_gate.CrossReferenceFinding`).

    Attributes:
        rule: The violation discriminator.
        field_name: The ``*_emissions`` field (or registry key) the finding is
            about; ``render_target`` carries the render-function name for the
            two render-function rules.
        render_target: The render function name for render-function rules; empty
            string for the field-level rules.
        diagnostic: Human-readable message naming the gap + remediation (NFR-O5).
    """

    model_config = ConfigDict(frozen=True)

    rule: FindingRule
    field_name: str
    render_target: str
    diagnostic: str


class GateResult(BaseModel):
    """Aggregate gate result.

    Frozen for determinism; field declaration order is load-bearing for
    byte-stable dumps.

    Attributes:
        findings: All findings, ordered by ``(rule, field_name, render_target)``.
        schema_fields_scanned: The ``*_emissions`` fields discovered in the
            envelope schema, in sorted order.
        registry_fields_scanned: The registry keys, in sorted order (the gate's
            non-vacuity witness in the summary line).
    """

    model_config = ConfigDict(frozen=True)

    findings: tuple[Finding, ...]
    schema_fields_scanned: tuple[str, ...]
    registry_fields_scanned: tuple[str, ...]


def discover_emissions_fields(schema: dict) -> set[str]:
    """Return the typed ``*_emissions`` field names from a loaded envelope schema.

    Scans the top-level ``properties`` mapping (the authoritative home of the
    typed emission arrays). A field qualifies when its key ends in
    ``_emissions``; the gate does not require ``type: array`` so a future
    object-shaped emissions field is still covered.
    """
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return set()
    return {
        key
        for key in properties
        if isinstance(key, str) and key.endswith(_EMISSIONS_SUFFIX)
    }


def load_render_surface_registry(
    registry_path: pathlib.Path,
) -> dict[str, list[str]]:
    """Load the field→render-functions registry from ``registry_path``.

    Raises :class:`ValueError` on a malformed shape (mapped to exit 2 by
    :func:`main`); :class:`OSError` / :class:`yaml.YAMLError` propagate the same
    way.
    """
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"emissions render-surface registry {registry_path} did not parse to "
            "a YAML mapping"
        )
    surfaces = raw.get("emissions_render_surfaces")
    if not isinstance(surfaces, dict):
        raise ValueError(
            f"emissions render-surface registry {registry_path} is missing a "
            "mapping under `emissions_render_surfaces`"
        )
    out: dict[str, list[str]] = {}
    for field_name, entry in surfaces.items():
        if not isinstance(field_name, str):
            raise ValueError(f"registry key {field_name!r} is not a string")
        if not isinstance(entry, dict):
            raise ValueError(f"registry entry for {field_name!r} is not a mapping")
        render_functions = entry.get("render_functions")
        if not isinstance(render_functions, list) or not all(
            isinstance(fn, str) for fn in render_functions
        ):
            raise ValueError(
                f"registry entry for {field_name!r} has a malformed "
                "`render_functions` list"
            )
        out[field_name] = list(render_functions)
    return out


def _code_only_source(source: str) -> str:
    """Return source with comment and string tokens blanked to empty lines."""
    prose: set[int] = set()
    try:
        reader = io.StringIO(source).readline
        for tok in _tok.generate_tokens(reader):
            if tok.type in (_tok.COMMENT, _tok.STRING):
                for lineno in range(tok.start[0], tok.end[0] + 1):
                    prose.add(lineno)
    except _tok.TokenError:
        return source
    lines = source.splitlines(keepends=True)
    return "".join(
        ("\n" if line.endswith("\n") else "") if (i + 1) in prose else line
        for i, line in enumerate(lines)
    )


def _is_defined(function_name: str, source: str) -> bool:
    return bool(
        re.search(rf"^\s*def\s+{re.escape(function_name)}\s*\(", source, re.MULTILINE)
    )


def _is_invoked(function_name: str, source: str) -> bool:
    """A call site exists when ``<fn>(`` appears more than ``def <fn>(`` in code."""
    code = _code_only_source(source)
    all_calls = len(re.findall(rf"\b{re.escape(function_name)}\s*\(", code))
    definitions = len(
        re.findall(rf"\bdef\s+{re.escape(function_name)}\s*\(", code)
    )
    return all_calls - definitions >= 1


def _is_field_accessed(field_name: str, source: str) -> bool:
    return bool(re.search(rf"""['"]{re.escape(field_name)}['"]""", source))


def evaluate_emissions_render_paths(
    *,
    schema_fields: set[str],
    registry: dict[str, list[str]],
    bundle_source: str,
) -> GateResult:
    """Apply the both-directions render-path rules. Pure (no I/O).

    Findings are sorted by ``(rule, field_name, render_target)`` for byte-stable
    CI diffs.
    """
    findings: list[Finding] = []

    for field_name in schema_fields:
        if field_name not in registry:
            findings.append(
                Finding(
                    rule="schema-field-unregistered",
                    field_name=field_name,
                    render_target="",
                    diagnostic=(
                        f"envelope schema declares `{field_name}` but it has no "
                        "entry in _data/emissions_render_surfaces.yaml — a typed "
                        "emissions array with no bundle render path is silently "
                        "dropped from the PR bundle. Add the field → render "
                        "function(s) mapping to the registry and a render path in "
                        "bundle_assembly.py."
                    ),
                )
            )

    for field_name, render_functions in registry.items():
        if field_name not in schema_fields:
            findings.append(
                Finding(
                    rule="registry-field-not-in-schema",
                    field_name=field_name,
                    render_target="",
                    diagnostic=(
                        f"registry maps `{field_name}` but no such `*_emissions` "
                        "field exists under `properties:` in "
                        "schemas/envelope.schema.yaml (registry rot). Remove the "
                        "stale registry entry or restore the schema field."
                    ),
                )
            )
            continue
        if not _is_field_accessed(field_name, bundle_source):
            findings.append(
                Finding(
                    rule="field-not-accessed",
                    field_name=field_name,
                    render_target="",
                    diagnostic=(
                        f"`{field_name}` is never accessed in bundle_assembly.py "
                        '(expected `qa_envelope.get("'
                        f'{field_name}")`) — the emissions array is not read into '
                        "any render path."
                    ),
                )
            )
        for function_name in render_functions:
            if not _is_defined(function_name, bundle_source):
                findings.append(
                    Finding(
                        rule="render-function-not-defined",
                        field_name=field_name,
                        render_target=function_name,
                        diagnostic=(
                            f"render function `{function_name}` mapped for "
                            f"`{field_name}` is not def-defined in "
                            "bundle_assembly.py."
                        ),
                    )
                )
            elif not _is_invoked(function_name, bundle_source):
                findings.append(
                    Finding(
                        rule="render-function-not-invoked",
                        field_name=field_name,
                        render_target=function_name,
                        diagnostic=(
                            f"render function `{function_name}` mapped for "
                            f"`{field_name}` is defined but never invoked in "
                            "bundle_assembly.py (dead render path)."
                        ),
                    )
                )

    findings.sort(key=lambda f: (f.rule, f.field_name, f.render_target))
    return GateResult(
        findings=tuple(findings),
        schema_fields_scanned=tuple(sorted(schema_fields)),
        registry_fields_scanned=tuple(sorted(registry)),
    )


def run_emissions_render_path_gate(
    *,
    schema_path: pathlib.Path,
    registry_path: pathlib.Path,
    bundle_source_path: pathlib.Path,
) -> GateResult:
    """Read all three inputs and evaluate the rules.

    Raises :class:`OSError` / :class:`UnicodeDecodeError` on unreadable inputs,
    :class:`yaml.YAMLError` / :class:`ValueError` on a malformed schema/registry
    — all mapped to exit 2 by :func:`main`.
    """
    raw_schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    if not isinstance(raw_schema, dict):
        raise ValueError(
            f"envelope schema {schema_path} did not parse to a YAML mapping"
        )
    schema_fields = discover_emissions_fields(raw_schema)
    registry = load_render_surface_registry(registry_path)
    bundle_source = bundle_source_path.read_text(encoding="utf-8")
    return evaluate_emissions_render_paths(
        schema_fields=schema_fields,
        registry=registry,
        bundle_source=bundle_source,
    )


def format_findings(result: GateResult) -> str:
    """Render a :class:`GateResult` for stdout, byte-stable."""
    lines: list[str] = []
    lines.append("emissions-render-path gate (story 22.6; G2)")
    lines.append(
        f"  schema *_emissions fields: {len(result.schema_fields_scanned)} "
        f"({', '.join(result.schema_fields_scanned)})"
    )
    lines.append(
        f"  registry fields: {len(result.registry_fields_scanned)}"
    )
    lines.append("")
    for finding in result.findings:
        target = f" [{finding.render_target}]" if finding.render_target else ""
        lines.append(
            f"emissions-render-path-gate: {finding.field_name}{target} "
            f"{finding.rule} {finding.diagnostic}"
        )
        lines.append("")
    if not result.findings:
        lines.append(
            f"emissions-render-path-gate: 0 findings "
            f"({len(result.schema_fields_scanned)} schema fields, "
            f"{len(result.registry_fields_scanned)} registry fields)"
        )
    else:
        lines.append(
            f"emissions-render-path-gate: {len(result.findings)} findings"
        )
    return "\n".join(lines)


def _resolve_registry_path() -> pathlib.Path:
    """Resolve the bundled registry via importlib.resources (cwd-independent;
    mirrors :func:`input_hardening_gate._resolve_registry_path`)."""
    return pathlib.Path(
        str(
            importlib.resources.files("loud_fail_harness").joinpath(_REGISTRY_RESOURCE)
        )
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emissions-render-path-gate",
        description=(
            "`*_emissions` → bundle-render-path gate (story 22.6; G2). Fails when "
            "a typed `*_emissions[]` envelope field has no render path in "
            "bundle_assembly.py, or when the registry has rotted. Build-time gate "
            "— no runtime marker."
        ),
    )
    parser.add_argument(
        "--schema",
        type=pathlib.Path,
        default=None,
        help=(
            "Path to envelope.schema.yaml (default: schemas/envelope.schema.yaml "
            "under the discovered repo root)."
        ),
    )
    parser.add_argument(
        "--registry",
        type=pathlib.Path,
        default=None,
        help=(
            "Path to the field→render-surface registry (default: the package-"
            "bundled _data/emissions_render_surfaces.yaml)."
        ),
    )
    parser.add_argument(
        "--bundle-source",
        type=pathlib.Path,
        default=None,
        help=(
            "Path to bundle_assembly.py (default: the inner-repo harness module)."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Exit codes:
        * ``0`` — ``GateResult.findings == ()`` (full pass).
        * ``1`` — any finding present (an emissions field lacks a render path,
          registry rot, or a missing/dead render function).
        * ``2`` — harness-level error (inputs unresolvable / unreadable /
          malformed schema or registry). Never a silent exit-0.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = find_repo_root()
    except RuntimeError as exc:
        print(f"emissions-render-path-gate: harness-level error: {exc}", file=sys.stderr)
        return 2

    schema_path: pathlib.Path = args.schema or (repo_root / _ENVELOPE_SCHEMA_REL)
    registry_path: pathlib.Path = args.registry or _resolve_registry_path()
    bundle_source_path: pathlib.Path = args.bundle_source or (
        repo_root / _BUNDLE_SOURCE_REL
    )

    for label, probe in (
        ("envelope schema", schema_path),
        ("registry", registry_path),
        ("bundle_assembly.py", bundle_source_path),
    ):
        if not probe.is_file():
            print(
                f"emissions-render-path-gate: harness-level error: {label} not "
                f"found ({probe!s})",
                file=sys.stderr,
            )
            return 2

    try:
        result = run_emissions_render_path_gate(
            schema_path=schema_path,
            registry_path=registry_path,
            bundle_source_path=bundle_source_path,
        )
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        print(
            f"emissions-render-path-gate: harness-level error: {exc}",
            file=sys.stderr,
        )
        return 2

    print(format_findings(result))
    return 1 if result.findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
