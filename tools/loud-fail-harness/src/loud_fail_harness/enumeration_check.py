"""Substrate component 4: Marker-taxonomy ↔ event-schema enumeration-equivalence reconciliation. See ADR-003.

This module implements Layer A's *completeness mitigation* (distinct from
substrate component 3, the reconciler — which is Layer A's primary mechanism).
It cross-validates that every ``marker_class`` reference in the orchestrator-
event schema (and, when present, ``schemas/dependencies.yaml`` per SDN-001
AND ``schemas/escalation-bundles/*.yaml`` per Story 4.10) resolves to an
enumerated entry in the closed ``marker-taxonomy.yaml`` set.

Four reconciliation pairs are covered architecturally:

* ``marker-taxonomy.yaml`` ↔ ``orchestrator-event.yaml`` — primary pair.
* ``marker-taxonomy.yaml`` ↔ ``dependencies.yaml`` (SDN-001 sub-decision) —
  optional at this story (file lands in story 1.6); absent path is gracefully
  skipped per AC-2.
* ``marker-taxonomy.yaml`` ↔ ``schemas/escalation-bundles/*.yaml`` — Epic 4
  escalation-bundle contracts (Story 4.10); optional at this story (directory
  lands in story 4.10); absent path is gracefully skipped per Story 4.10
  AC-6(e). Per ADR-003 Consequence 7, this fourth pair is internal evolution
  of substrate component 4 — substrate-component count remains FIVE.
* ``marker-taxonomy.yaml`` ↔ fixture-coverage — handled by substrate
  component 5 (story 1.7), NOT this module.

Strict-name discovery (AC-1):
    Only properties whose key is literally ``marker_class`` or ``emits_marker``
    are scanned. Their values pass through ``const`` / ``enum`` JSON-Schema
    wrappers, but other property names (``escalation_class``, ``outcome``,
    ``event_class``, ...) are NOT scanned even when their enum values happen
    to string-match a marker class identifier — false-positive prevention per
    Dev-Notes "discovery rule" worked-examples table.

Loud-fail discipline (Pattern 5):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — all references resolve (warn-level orphans permitted)
        1 — at least one reference points to a marker class not present in
            the taxonomy (AC-3 "added a reference to a marker that was never
            defined" + AC-4 "removed a marker that something still references"
            — both surface as a closure-equivalence violation; see
            ``format_findings`` for the unified rendered diagnostic)
        2 — harness-level error (schema unreadable, malformed YAML, malformed
            taxonomy, etc.)

Sensor-not-advisor:
    The check reports what classification each reference falls into (passing /
    missing / orphan) and prints actionable diagnostics; it does NOT recommend
    specific architectural changes, suggest renames, or auto-rewrite the
    schemas. Same posture as the reconciler (story 1.4).
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Sequence
from typing import Literal

import yaml
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict

from loud_fail_harness._shared import _path_pointer, find_repo_root, load_schema
from loud_fail_harness.reconciler import load_marker_taxonomy

#: Property keys treated as marker-class references under the strict-name rule
#: (AC-1). The rule is: only when the immediate dict key is literally one of
#: these strings does the value count as a reference. Sibling keys whose enum
#: values happen to string-match a marker class identifier (e.g.
#: ``escalation_class: { enum: [retry-budget-exhausted, ...] }``) are NOT
#: counted — that prevents false positives without bespoke configuration.
_STRICT_NAME_KEYS: tuple[Literal["marker_class", "emits_marker"], ...] = (
    "marker_class",
    "emits_marker",
)


class Reference(BaseModel):
    """A single discovered ``marker_class`` (or ``emits_marker``) reference.

    Frozen for hashability + determinism; field declaration order is load-
    bearing for ``model_dump_json()`` byte-stability.
    """

    model_config = ConfigDict(frozen=True)

    marker_class: str
    source_file: str
    pointer: str
    discovery_kind: Literal["marker_class", "emits_marker"]


class CheckResult(BaseModel):
    """Triple-classification enumeration-check output.

    * ``passing`` — references that resolve cleanly to taxonomy entries.
    * ``missing`` — references whose marker class is not in the taxonomy
      (the AC-3 / AC-4 closure-equivalence violations).
    * ``orphans`` — taxonomy entries that no reference resolves to.

    Determinism (AC-3 "do not bail after first" + AC-5 lex-sorted orphans):
        ``passing`` and ``missing`` are sorted by ``(source_file, pointer)``
        before construction; ``orphans`` is lexicographically sorted. Field
        declaration order matches Pydantic v2's JSON-serialization order
        (load-bearing for byte-stable dumps).
    """

    model_config = ConfigDict(frozen=True)

    passing: list[Reference]
    missing: list[Reference]
    orphans: list[str]


def _extract_value_into_references(
    key: Literal["marker_class", "emits_marker"],
    value: object,
    path: list[object],
    file_path: str,
    out: list[Reference],
) -> None:
    """Given the value V at a strict-name key K's path P, append reference(s).

    Three documented value shapes (per Dev-Notes worked-examples table):

    * V is a string                      → one reference at P.
    * V is a dict with a string ``const`` → one reference at P + ``["const"]``.
    * V is a dict with an ``enum`` list   → one reference per string item, at
      P + ``["enum", i]``.

    Other shapes (V is a list, V is a non-string scalar, V is a dict without
    ``const``/``enum``, ...) yield nothing — strict-name discovery covers only
    the documented JSON-Schema / SDN-001 forms. The walker does not recurse
    into a strict-name key's subtree beyond const/enum extraction; that would
    invent semantics the AC text does not specify.

    Worked example showing why ``escalation_class`` is intentionally NOT a
    match: the canonical orchestrator-event.yaml declares ::

        escalation_class:
          type: string
          enum: [retry-budget-exhausted, qa-verification-fail, qa-env-setup-fail]

    Even though ``retry-budget-exhausted`` is a real marker class identifier
    (it IS in the taxonomy), the dict key here is ``escalation_class``, not a
    strict-name match, so :func:`discover_marker_class_references` does NOT
    add a Reference for it. The escalation enum carries those values for its
    own contract reasons (escalation-kind dispatch); a heuristic discovery
    rule that flagged any taxonomy-string-equal enum value would conflate
    incidental coincidences with intentional cross-schema references.
    """
    if isinstance(value, str):
        out.append(
            Reference(
                marker_class=value,
                source_file=file_path,
                pointer=_path_pointer(path),
                discovery_kind=key,
            )
        )
        return
    if isinstance(value, dict):
        const_value = value.get("const")
        if isinstance(const_value, str):
            out.append(
                Reference(
                    marker_class=const_value,
                    source_file=file_path,
                    pointer=_path_pointer([*path, "const"]),
                    discovery_kind=key,
                )
            )
        enum_value = value.get("enum")
        if isinstance(enum_value, list):
            for i, item in enumerate(enum_value):
                if isinstance(item, str):
                    out.append(
                        Reference(
                            marker_class=item,
                            source_file=file_path,
                            pointer=_path_pointer([*path, "enum", i]),
                            discovery_kind=key,
                        )
                    )


def _walk(
    node: object,
    path: list[object],
    file_path: str,
    out: list[Reference],
) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            child_path = [*path, k]
            if k in _STRICT_NAME_KEYS:
                _extract_value_into_references(k, v, child_path, file_path, out)
            else:
                _walk(v, child_path, file_path, out)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk(item, [*path, i], file_path, out)


def discover_marker_class_references(
    schema: dict, file_path: str
) -> list[Reference]:
    """Walk a parsed YAML/JSON-Schema dict and return every ``marker_class``
    (and SDN-001 ``emits_marker``) reference with its JSON-pointer path.

    See :func:`_extract_value_into_references` for the strict-name rule the
    walker enforces. The returned list preserves discovery order;
    :func:`check_enumeration` re-sorts deterministically before producing
    its result.
    """
    out: list[Reference] = []
    _walk(schema, [], file_path, out)
    return out


def check_enumeration(
    taxonomy: set[str], references: list[Reference]
) -> CheckResult:
    """Partition ``references`` against ``taxonomy`` into the three classes.

    * ``passing`` — reference's ``marker_class`` IS in the taxonomy.
    * ``missing`` — reference's ``marker_class`` is NOT in the taxonomy.
    * ``orphans`` — taxonomy entries that no reference resolves to.

    Output is deterministic across runs on the same inputs: ``passing`` and
    ``missing`` are sorted by ``(source_file, pointer)``; ``orphans`` is
    lexicographically sorted. No reliance on Python ``set`` iteration order
    leaks into the result (parallel to story 1.4's reconciler discipline).
    """
    referenced: set[str] = {r.marker_class for r in references}

    passing: list[Reference] = []
    missing: list[Reference] = []
    for r in references:
        if r.marker_class in taxonomy:
            passing.append(r)
        else:
            missing.append(r)

    def _key(r: Reference) -> tuple[str, str]:
        return (r.source_file, r.pointer)

    passing.sort(key=_key)
    missing.sort(key=_key)
    orphans = sorted(taxonomy - referenced)

    return CheckResult(passing=passing, missing=missing, orphans=orphans)


_DEPENDENCIES_DEFERRAL_NOTE = (
    "note: schemas/dependencies.yaml not present; deferred to story 1.6"
)
_ESCALATION_BUNDLES_DEFERRAL_NOTE = (
    "note: schemas/escalation-bundles/ not present; deferred to story 4.10"
)
_MISSING_REFERENCE_REMEDIATION = (
    "Remediation: add the marker_class entry to schemas/marker-taxonomy.yaml "
    "OR remove the reference (taxonomy is single-source-of-truth per "
    "FR30 / SDN-001). "
    "(Cause: either the reference was added before the marker class was defined, "
    "or the marker class was removed while this reference still existed.)"
)


def format_findings(
    result: CheckResult,
    *,
    dependencies_present: bool,
    escalation_bundles_present: bool = True,
) -> str:
    """Render a :class:`CheckResult` for stdout.

    Always prints a header and a summary line. Conditionally prints:

    * the dependencies-absent deferral note (AC-2) when
      ``dependencies_present`` is False;
    * the escalation-bundles-absent deferral note (Story 4.10 AC-6(f)) when
      ``escalation_bundles_present`` is False;
    * an ``ERROR:`` section listing every missing reference with file +
      JSON-pointer + remediation prose (AC-3 / AC-4); the rendered shape is
      the same regardless of whether the violation is "added a reference to
      an undefined marker" or "removed a marker still referenced" — the
      remediation prose names both possibilities (taxonomy is single-source-
      of-truth);
    * an ``Orphan marker classes (warn-level — allowed but flagged):``
      section (AC-5) listing every orphan with the canonical
      "expected to bind in Epic 2+ ..." remediation suffix.

    The summary line is unconditional so a green CI run still surfaces the
    counts (Pattern 5: explicit, never silent on the warn-level half).

    The ``escalation_bundles_present`` keyword defaults to ``True`` so test
    callers using only the dependencies-pair shape continue to compile and
    pass without churn (parallel to story 4.7's additive-default pattern).
    """
    lines: list[str] = []
    lines.append("Cross-schema enumeration check (substrate component 4)")
    lines.append("")

    if not dependencies_present:
        lines.append(_DEPENDENCIES_DEFERRAL_NOTE)
        lines.append("")

    if not escalation_bundles_present:
        lines.append(_ESCALATION_BUNDLES_DEFERRAL_NOTE)
        lines.append("")

    if result.missing:
        lines.append(
            f"ERROR: {len(result.missing)} marker_class reference(s) "
            "not present in schemas/marker-taxonomy.yaml."
        )
        lines.append(_MISSING_REFERENCE_REMEDIATION)
        for ref in result.missing:
            lines.append(
                f"  - {ref.marker_class} at "
                f"{ref.source_file}#{ref.pointer} "
                f"[{ref.discovery_kind}]"
            )
        lines.append("")

    if result.orphans:
        lines.append(
            "Orphan marker classes (warn-level — allowed but flagged):"
        )
        for orphan in result.orphans:
            lines.append(
                f"  - {orphan}: no event or dependency currently emits "
                "this; expected to bind in Epic 2+ orchestrator stories "
                "or in story 1.6 dependencies.yaml"
            )
        lines.append("")

    lines.append(
        f"Summary: {len(result.passing)} passing reference(s), "
        f"{len(result.missing)} missing reference(s), "
        f"{len(result.orphans)} orphan marker class(es) (warn-level)."
    )
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="enumeration-check",
        description=(
            "Cross-schema enumeration_check. Validates that every "
            "marker_class reference in the orchestrator-event schema "
            "(and, if present, schemas/dependencies.yaml AND "
            "schemas/escalation-bundles/*.yaml) resolves to an entry in "
            "schemas/marker-taxonomy.yaml. Substrate component 4; "
            "ADR-003 + FR33; Story 4.10 added the escalation-bundles "
            "reconciliation pair."
        ),
    )
    parser.add_argument(
        "--taxonomy-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to marker-taxonomy.yaml (default: "
            "<repo-root>/schemas/marker-taxonomy.yaml). Test-injection "
            "flag; CI invocations omit it."
        ),
    )
    parser.add_argument(
        "--event-schema-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to orchestrator-event.yaml (default: "
            "<repo-root>/schemas/orchestrator-event.yaml). Test-injection "
            "flag; CI invocations omit it."
        ),
    )
    parser.add_argument(
        "--dependencies-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to dependencies.yaml (default: "
            "<repo-root>/schemas/dependencies.yaml). Test-injection "
            "flag; CI invocations omit it. The default path is optional — "
            "its absence is gracefully skipped per AC-2."
        ),
    )
    parser.add_argument(
        "--escalation-bundles-dir",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to the escalation-bundles directory (default: "
            "<repo-root>/schemas/escalation-bundles). Test-injection "
            "flag; CI invocations omit it. The default path is optional — "
            "its absence is gracefully skipped per Story 4.10 AC-6(e)."
        ),
    )
    return parser


def _resolve_default_paths() -> tuple[
    pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path
]:
    repo_root = find_repo_root()
    return (
        repo_root / "schemas" / "marker-taxonomy.yaml",
        repo_root / "schemas" / "orchestrator-event.yaml",
        repo_root / "schemas" / "dependencies.yaml",
        repo_root / "schemas" / "escalation-bundles",
    )


def _display_path(path: pathlib.Path) -> str:
    """Render a path relative to repo root if possible; absolute otherwise.

    Test invocations pass tmp_path schema files outside the repo — for those
    the relative resolution fails and the absolute path is returned, which
    is still informative in stdout. Canonical CI invocations use the
    in-repo schemas and produce stable relative paths like
    ``schemas/orchestrator-event.yaml`` for diff-friendly output.
    """
    try:
        repo_root = find_repo_root()
        return str(path.resolve().relative_to(repo_root.resolve()))
    except (RuntimeError, ValueError):
        return str(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    taxonomy_path: pathlib.Path
    event_schema_path: pathlib.Path
    dependencies_path: pathlib.Path
    escalation_bundles_dir: pathlib.Path
    if (
        args.taxonomy_path is None
        or args.event_schema_path is None
        or args.dependencies_path is None
        or args.escalation_bundles_dir is None
    ):
        try:
            (
                d_taxonomy,
                d_event_schema,
                d_dependencies,
                d_escalation_bundles,
            ) = _resolve_default_paths()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        taxonomy_path = args.taxonomy_path or d_taxonomy
        event_schema_path = args.event_schema_path or d_event_schema
        dependencies_path = args.dependencies_path or d_dependencies
        escalation_bundles_dir = (
            args.escalation_bundles_dir or d_escalation_bundles
        )
    else:
        taxonomy_path = args.taxonomy_path
        event_schema_path = args.event_schema_path
        dependencies_path = args.dependencies_path
        escalation_bundles_dir = args.escalation_bundles_dir

    try:
        taxonomy = load_marker_taxonomy(taxonomy_path)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print(
            "harness-level error: marker-taxonomy unreadable: "
            f"{taxonomy_path}: {exc}",
            file=sys.stderr,
        )
        return 2
    except yaml.YAMLError as exc:
        print(
            "harness-level error: marker-taxonomy YAML parse failure: "
            f"{taxonomy_path}: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        event_schema = load_schema(event_schema_path)
    except OSError as exc:
        print(
            "harness-level error: orchestrator-event schema unreadable: "
            f"{event_schema_path}: {exc}",
            file=sys.stderr,
        )
        return 2
    except (SchemaError, yaml.YAMLError) as exc:
        print(
            "harness-level error: orchestrator-event schema malformed: "
            f"{event_schema_path}: {exc}",
            file=sys.stderr,
        )
        return 2

    references: list[Reference] = []
    references.extend(
        discover_marker_class_references(
            event_schema, _display_path(event_schema_path)
        )
    )

    dependencies_present = False
    try:
        deps_text = dependencies_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # AC-2: absent dependencies.yaml is a clean skip, NOT a harness error.
        # Other OSError subclasses (PermissionError, IsADirectoryError, ...)
        # ARE harness errors and surface below.
        pass
    except OSError as exc:
        print(
            "harness-level error: dependencies.yaml unreadable: "
            f"{dependencies_path}: {exc}",
            file=sys.stderr,
        )
        return 2
    else:
        try:
            deps_raw = yaml.safe_load(deps_text)
        except yaml.YAMLError as exc:
            print(
                "harness-level error: dependencies.yaml YAML parse failure: "
                f"{dependencies_path}: {exc}",
                file=sys.stderr,
            )
            return 2
        if not isinstance(deps_raw, dict):
            print(
                "harness-level error: dependencies.yaml did not parse to a YAML mapping: "
                f"{dependencies_path} (got {type(deps_raw).__name__})",
                file=sys.stderr,
            )
            return 2
        dependencies_present = True
        references.extend(
            discover_marker_class_references(
                deps_raw, _display_path(dependencies_path)
            )
        )

    # Story 4.10 — fourth reconciliation pair:
    # marker-taxonomy.yaml ↔ schemas/escalation-bundles/*.yaml.
    # Mirrors the dependencies-discovery block byte-for-byte for error-
    # handling shape (the four error paths — absent (handled by `is_dir()`
    # check), OSError, YAMLError, non-mapping — surface as harness-level
    # errors with exit code 2 per the existing Pattern 5 discipline). The
    # absent-directory path is a clean skip per AC-6(e); other OSError
    # subclasses encountered while reading individual fragments ARE harness
    # errors and surface below.
    escalation_bundles_present = False
    if escalation_bundles_dir.is_dir():
        escalation_bundles_present = True
        for fragment_path in sorted(escalation_bundles_dir.glob("*.yaml")):
            try:
                fragment_text = fragment_path.read_text(encoding="utf-8")
            except OSError as exc:
                print(
                    "harness-level error: escalation-bundle contract unreadable: "
                    f"{fragment_path}: {exc}",
                    file=sys.stderr,
                )
                return 2
            try:
                fragment = yaml.safe_load(fragment_text)
            except yaml.YAMLError as exc:
                print(
                    "harness-level error: escalation-bundle contract YAML parse failure: "
                    f"{fragment_path}: {exc}",
                    file=sys.stderr,
                )
                return 2
            if not isinstance(fragment, dict):
                print(
                    "harness-level error: escalation-bundle contract did not parse to a YAML mapping: "
                    f"{fragment_path} (got {type(fragment).__name__})",
                    file=sys.stderr,
                )
                return 2
            references.extend(
                discover_marker_class_references(
                    fragment, _display_path(fragment_path)
                )
            )

    result = check_enumeration(taxonomy, references)
    print(
        format_findings(
            result,
            dependencies_present=dependencies_present,
            escalation_bundles_present=escalation_bundles_present,
        )
    )
    return 1 if result.missing else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
