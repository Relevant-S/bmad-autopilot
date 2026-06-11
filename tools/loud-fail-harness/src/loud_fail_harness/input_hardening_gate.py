"""Input-hardening structural CI gate — Story 24.2 (Epic 24 Action #2).

## What this gate enforces

The input-hardening discipline was applied-by-memory and re-discovered
reactively across five consecutive epics (13 → 14 → 15 → 16 → 18). This gate
converts "apply the checklist from memory" into "the build fails if you don't",
making a sixth recurrence structurally impossible. It is the marker-taxonomy /
fixture-coverage closed-enumeration discipline applied to *models*.

Mirrors :mod:`no_destructive_resume_lint` byte-for-byte in *shape* (LintFinding
+ LintResult frozen Pydantic models + deterministic ``format_findings`` +
``main`` CLI exiting 0/1/2). It is a sibling library + CI gate, NOT a sixth
substrate component (ADR-003's FIVE-component lock holds — naming-lint /
pluggability-gate / no-destructive-resume-lint are all gates, none a component),
and it emits NO runtime marker (build-time gate → stderr findings + nonzero
exit, like every other gate).

## The three structural rules

* **Rule A — model classification (completeness).** Every ``BaseModel`` subclass
  discovered by AST in the governed source tree appears in EXACTLY ONE bucket of
  the closed registry (``_data/input_hardening_registry.yaml``):
  ``externally_constructed`` (carries a hostile-input surface) or
  ``internal_only`` (constructed solely from already-validated in-process data).
  A model in NEITHER bucket → ``A-unclassified-model`` (forces every new model to
  be triaged at authoring time). A model in BOTH → ``A-double-classified``.
* **Rule B — per-model hardening coverage.** For each ``externally_constructed``
  entry, the model's ``@model_validator``/``@field_validator`` body must route
  every declared ``identifier_field`` through ``harden_identifier``, every
  ``path_field`` through ``harden_path_segment``, and every ``dup_key_field``
  collection through ``reject_duplicate_identifiers``. Coverage is detected via
  each helper call's LABEL string argument (``"<ClassName>.<field>"``, a trailing
  ``[]`` for per-element collection hardening stripped), decoupling the check
  from how the value is referenced (``self.x`` vs a loop variable). A registered
  field with no matching hardening call → ``B-field-unhardened``.
* **Rule C — ValidationError catch-boundary (loud-fail).** In Pydantic v2.13+
  ``ValidationError`` IS a ``ValueError`` subclass (verified: ``ValidationError``
  MRO contains ``ValueError``), so ``except (ValueError, KeyError)`` around a
  model construction does NOT *miss* the ``ValidationError`` — it *catches* it.
  The real loud-fail hazard is the inverse: such a handler SILENTLY SWALLOWS the
  construction failure. Rule C (AST, bounded — NOT call-graph) flags any
  ``try/except`` whose handler catches ``ValueError``/``KeyError``, whose ``try``
  body directly constructs an ``externally_constructed`` model (or calls a
  registered parse-function), and whose handler does NOT re-raise →
  ``C-validationerror-swallowed``. A ``module:lineno → rationale`` allowlist
  permits deliberate exemptions. [The story's AC-4 premise — that the
  construction ValidationError is not a ValueError subclass — does not hold for
  the pinned ``pydantic>=2.13.3,<3``; Rule C is re-aimed to the true invariant.
  See the Dev Agent Record of Story 24.2 for the empirical proof.]

## Loud-fail discipline (Pattern 5)

    0 — full pass: ``LintResult.findings == ()``.
    1 — invariant violation: any finding present.
    2 — harness-level error: a scanned file is unreadable / non-UTF-8 /
        non-parseable, the registry data file is missing / malformed, OR the
        registry names a model absent from the governed tree (registry rot).

## Sensor-not-advisor (PRD-level invariant)

The gate REPORTS findings with remediation pointers; it does NOT auto-edit
models, add validators, or rewrite the registry.
"""

from __future__ import annotations

import argparse
import ast
import importlib.resources
import logging
import pathlib
import sys
from collections.abc import Sequence
from typing import Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from ._shared import find_repo_root

__all__ = [
    "LintFinding",
    "LintResult",
    "ModelRegistry",
    "discover_models",
    "format_findings",
    "load_registry",
    "main",
    "run_input_hardening_gate",
]

_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Module-level constants                                                      #
# --------------------------------------------------------------------------- #


#: The governed source tree (relative to the harness package root). Models under
#: ``tests/`` and ``agents/`` are deliberately out of scope (Story 24.2 scope
#: guard "governed source = src/loud_fail_harness/**").
_SRC_RELATIVE: Final[tuple[str, ...]] = ("src", "loud_fail_harness")


#: The base class name that marks a class as a Pydantic model under discovery.
#: Discovery contract: a class is a model iff one of its bases is a ``Name`` or
#: ``Attribute`` resolving to ``BaseModel`` (covers ``BaseModel`` and
#: ``pydantic.BaseModel``). Transitive-via-local-BaseModel-subclass chains are
#: out of scope — the governed tree has none (every model subclasses BaseModel
#: directly; the non-BaseModel local bases are all Protocol/Exception/Enum).
_BASEMODEL_NAME: Final[str] = "BaseModel"


#: The three shared hardening helpers (``loud_fail_harness.input_hardening``)
#: whose calls Rule B credits, keyed by registry field-bucket.
_IDENTIFIER_HELPER: Final[str] = "harden_identifier"
_PATH_HELPER: Final[str] = "harden_path_segment"
_DUP_HELPER: Final[str] = "reject_duplicate_identifiers"


#: Pydantic-validator decorator names whose method bodies Rule B inspects for
#: hardening calls. A hardening call outside a validator-decorated method does
#: NOT run at construction, so it is not credited.
_VALIDATOR_DECORATORS: Final[frozenset[str]] = frozenset(
    {"model_validator", "field_validator"}
)


#: Exception names whose ``except`` clause Rule C treats as catching a
#: construction-time ``ValidationError`` (which subclasses ValueError in v2.13+).
_RULE_C_CAUGHT_NAMES: Final[frozenset[str]] = frozenset({"ValueError", "KeyError"})


#: Rule C per-site allowlist: ``"<module_stem>:<except-handler-lineno>" ->
#: rationale``. A site listed here is a deliberate exemption (the broad catch is
#: intended; e.g. the handler re-raises a domain error elsewhere or the swallow
#: is the documented contract). Every entry MUST carry a one-line rationale.
_RULE_C_ALLOWLIST: Final[dict[str, str]] = {
    "qa_a11y_audit:339": (
        "Intentional: hostile axe-core selector that fails AxeViolationKey "
        "construction marks the normalization run as unstable (stable=False) "
        "rather than crashing — unstable runs emit a11y-delta-mode-unstable "
        "instead of a partial delta that would cause false-positive regressions."
    ),
}


_RULE_A_UNCLASSIFIED_REMEDIATION: str = (
    "(per Story 24.2 AC-2 Rule A: every BaseModel subclass under "
    "src/loud_fail_harness/ MUST be classified in exactly one bucket of "
    "_data/input_hardening_registry.yaml. Remediation: add this model to "
    "`externally_constructed` (with its identifier/path/dup fields) if it is "
    "built from parsed text / config / story-doc frontmatter / CLI args / "
    "operator edits, else to `internal_only`.)"
)


_RULE_A_DOUBLE_REMEDIATION: str = (
    "(per Story 24.2 AC-2 Rule A: a model must be in EXACTLY ONE bucket. "
    "Remediation: remove this model from one of `externally_constructed` / "
    "`internal_only` in _data/input_hardening_registry.yaml.)"
)


_RULE_B_REMEDIATION: str = (
    "(per Story 24.2 AC-3 Rule B: every registered field must be routed through "
    "the shared input_hardening helper inside a @model_validator/@field_validator. "
    "Remediation: add `harden_identifier(self.<field>, \"<Model>.<field>\")` "
    "(or harden_path_segment / reject_duplicate_identifiers) — the label string "
    "is what the gate matches.)"
)


_RULE_C_REMEDIATION: str = (
    "(per Story 24.2 AC-4 Rule C: a broad `except (ValueError|KeyError)` around a "
    "registered-model construction SILENTLY SWALLOWS the construction "
    "ValidationError — ValidationError subclasses ValueError in pydantic v2.13+. "
    "Remediation: re-raise (so the loud-fail propagates), narrow the except so it "
    "does not subsume ValidationError, or add the site to the gate's "
    "_RULE_C_ALLOWLIST with a one-line rationale.)"
)


# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class LintFinding(BaseModel):
    """A single structural-rule violation. Frozen for hashability + determinism;
    field declaration order is load-bearing for byte-stable output. Mirrors
    :class:`no_destructive_resume_lint.LintFinding`'s shape."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    file_path: pathlib.Path
    line_number: int
    rule: Literal[
        "A-unclassified-model",
        "A-double-classified",
        "B-field-unhardened",
        "C-validationerror-swallowed",
    ]
    diagnostic: str


class LintResult(BaseModel):
    """Aggregate gate result. Frozen for determinism; findings ordered by
    ``(file_path, line_number, rule)`` for byte-stable output."""

    model_config = ConfigDict(frozen=True)

    findings: tuple[LintFinding, ...]
    models_discovered: int


class _FieldBuckets(BaseModel):
    """Per-model hardening declaration in the ``externally_constructed`` bucket."""

    model_config = ConfigDict(frozen=True)

    identifier_fields: tuple[str, ...] = ()
    path_fields: tuple[str, ...] = ()
    dup_key_fields: tuple[str, ...] = ()


class ModelRegistry(BaseModel):
    """The closed dual-registry loaded from
    ``_data/input_hardening_registry.yaml``."""

    model_config = ConfigDict(frozen=True)

    externally_constructed: dict[str, _FieldBuckets]
    internal_only: frozenset[str]
    parse_functions: frozenset[str] = frozenset()


# --------------------------------------------------------------------------- #
# AST discovery                                                               #
# --------------------------------------------------------------------------- #


class _DiscoveredModel(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    qualname: str
    class_name: str
    file_path: pathlib.Path
    line_number: int
    node: ast.ClassDef


def _parse_module(file_path: pathlib.Path) -> ast.Module:
    """Read + parse Python source. Raises :class:`RuntimeError` on UTF-8 /
    OSError / SyntaxError so callers surface them as harness-level errors."""
    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"file not UTF-8: {file_path}") from exc
    except OSError as exc:
        raise RuntimeError(f"file unreadable: {file_path}") from exc
    try:
        return ast.parse(text, filename=str(file_path))
    except SyntaxError as exc:
        raise RuntimeError(f"file not parseable as Python: {file_path}: {exc}") from exc


def _base_is_basemodel(base: ast.expr) -> bool:
    if isinstance(base, ast.Name):
        return base.id == _BASEMODEL_NAME
    if isinstance(base, ast.Attribute):
        return base.attr == _BASEMODEL_NAME
    return False


def discover_models(src_dir: pathlib.Path) -> list[_DiscoveredModel]:
    """Discover every ``BaseModel`` subclass under ``src_dir`` (recursive).

    Qualname is ``<module-stem>.<ClassName>``. Top-level + nested class defs are
    both walked. Raises :class:`RuntimeError` on any unreadable/unparseable file.
    """
    discovered: list[_DiscoveredModel] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        tree = _parse_module(py_file)
        stem = py_file.stem
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(_base_is_basemodel(base) for base in node.bases):
                continue
            discovered.append(
                _DiscoveredModel(
                    qualname=f"{stem}.{node.name}",
                    class_name=node.name,
                    file_path=py_file,
                    line_number=node.lineno,
                    node=node,
                )
            )
    return discovered


# --------------------------------------------------------------------------- #
# Registry loading                                                            #
# --------------------------------------------------------------------------- #


def _resolve_registry_path() -> pathlib.Path:
    """Resolve the bundled registry via importlib.resources (cwd-independent;
    mirrors :func:`marker_coverage_audit._resolve_surfaces_path`)."""
    return pathlib.Path(
        str(
            importlib.resources.files("loud_fail_harness").joinpath(
                "_data/input_hardening_registry.yaml"
            )
        )
    )


def load_registry(registry_path: pathlib.Path | None = None) -> ModelRegistry:
    """Load + validate the closed model-classification registry. Raises
    :class:`RuntimeError` on a missing / malformed data file."""
    path = registry_path if registry_path is not None else _resolve_registry_path()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"registry file unreadable: {path}") from exc
    except yaml.YAMLError as exc:
        raise RuntimeError(f"registry file not valid YAML: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RuntimeError(f"registry file did not parse to a mapping: {path}")
    try:
        return ModelRegistry.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 — surfaced as harness-level error
        raise RuntimeError(f"registry file malformed: {path}: {exc}") from exc


# --------------------------------------------------------------------------- #
# Rule A — model classification                                               #
# --------------------------------------------------------------------------- #


def _scan_rule_a(
    models: list[_DiscoveredModel], registry: ModelRegistry
) -> list[LintFinding]:
    external = set(registry.externally_constructed)
    internal = set(registry.internal_only)
    findings: list[LintFinding] = []
    for model in models:
        in_external = model.qualname in external
        in_internal = model.qualname in internal
        if in_external and in_internal:
            findings.append(
                LintFinding(
                    file_path=model.file_path,
                    line_number=model.line_number,
                    rule="A-double-classified",
                    diagnostic=(
                        f"{model.qualname}: classified in BOTH "
                        f"externally_constructed AND internal_only. "
                        f"{_RULE_A_DOUBLE_REMEDIATION}"
                    ),
                )
            )
        elif not in_external and not in_internal:
            findings.append(
                LintFinding(
                    file_path=model.file_path,
                    line_number=model.line_number,
                    rule="A-unclassified-model",
                    diagnostic=(
                        f"{model.qualname}: not classified in "
                        f"_data/input_hardening_registry.yaml. "
                        f"{_RULE_A_UNCLASSIFIED_REMEDIATION}"
                    ),
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Rule B — per-model hardening coverage                                       #
# --------------------------------------------------------------------------- #


def _has_validator_decorator(func: ast.FunctionDef) -> bool:
    for dec in func.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name) and target.id in _VALIDATOR_DECORATORS:
            return True
        if isinstance(target, ast.Attribute) and target.attr in _VALIDATOR_DECORATORS:
            return True
    return False


def _hardening_labels(class_node: ast.ClassDef) -> dict[str, set[str]]:
    """Collect, per helper name, the set of normalized LABEL strings passed to
    that helper inside any validator-decorated method of ``class_node``.

    A label ``"Model.field[]"`` (per-element collection hardening) is normalized
    by stripping the trailing ``[]`` so it credits the field ``Model.field``.
    """
    labels: dict[str, set[str]] = {
        _IDENTIFIER_HELPER: set(),
        _PATH_HELPER: set(),
        _DUP_HELPER: set(),
    }
    for member in class_node.body:
        if not isinstance(member, ast.FunctionDef):
            continue
        if not _has_validator_decorator(member):
            continue
        for call in ast.walk(member):
            if not isinstance(call, ast.Call):
                continue
            callee = call.func
            name = (
                callee.id
                if isinstance(callee, ast.Name)
                else callee.attr
                if isinstance(callee, ast.Attribute)
                else None
            )
            if name not in labels:
                continue
            label = _string_label_arg(call)
            if label is None:
                continue
            if label.endswith("[]"):
                label = label[:-2]
            labels[name].add(label)
    return labels


def _string_label_arg(call: ast.Call) -> str | None:
    """Return the LABEL string of a helper call. ``harden_identifier(value,
    label)`` / ``harden_path_segment(value, label)`` use the 2nd positional;
    ``reject_duplicate_identifiers(values, label)`` likewise. Only a literal
    ``str`` constant is credited (a dynamic label is not statically matchable)."""
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        value = call.args[1].value
        if isinstance(value, str):
            return value
    for kw in call.keywords:
        if kw.arg == "label" and isinstance(kw.value, ast.Constant):
            value = kw.value.value
            if isinstance(value, str):
                return value
    return None


def _scan_rule_b(
    models: list[_DiscoveredModel], registry: ModelRegistry
) -> list[LintFinding]:
    by_qualname = {m.qualname: m for m in models}
    findings: list[LintFinding] = []
    for qualname, buckets in sorted(registry.externally_constructed.items()):
        model = by_qualname.get(qualname)
        if model is None:
            continue  # registry-rot is surfaced separately (harness error)
        labels = _hardening_labels(model.node)
        checks = (
            (buckets.identifier_fields, _IDENTIFIER_HELPER),
            (buckets.path_fields, _PATH_HELPER),
            (buckets.dup_key_fields, _DUP_HELPER),
        )
        for fields, helper in checks:
            for field in fields:
                expected = f"{model.class_name}.{field}"
                if expected in labels[helper]:
                    continue
                findings.append(
                    LintFinding(
                        file_path=model.file_path,
                        line_number=model.line_number,
                        rule="B-field-unhardened",
                        diagnostic=(
                            f"{qualname}: registered field {field!r} has no "
                            f"{helper}(…, {expected!r}) call in a validator body. "
                            f"{_RULE_B_REMEDIATION}"
                        ),
                    )
                )
    return findings


# --------------------------------------------------------------------------- #
# Rule C — ValidationError catch-boundary                                     #
# --------------------------------------------------------------------------- #


def _handler_catches_value_or_key(handler: ast.ExceptHandler) -> bool:
    caught = handler.type
    if caught is None:
        return False  # bare except is out of the ValueError/KeyError scope
    names: list[str] = []
    if isinstance(caught, ast.Tuple):
        names = [e.id for e in caught.elts if isinstance(e, ast.Name)]
    elif isinstance(caught, ast.Name):
        names = [caught.id]
    return any(n in _RULE_C_CAUGHT_NAMES for n in names)


def _handler_reraises(handler: ast.ExceptHandler) -> bool:
    return any(isinstance(stmt, ast.Raise) for stmt in handler.body)


def _try_body_constructs_registered(
    handler_try: ast.Try, construct_names: frozenset[str]
) -> bool:
    for stmt in handler_try.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                callee = node.func
                if isinstance(callee, ast.Name) and callee.id in construct_names:
                    return True
                if isinstance(callee, ast.Attribute) and callee.attr in construct_names:
                    return True
    return False


def _scan_rule_c(
    file_path: pathlib.Path,
    tree: ast.Module,
    module_stem: str,
    registry: ModelRegistry,
) -> list[LintFinding]:
    construct_names = (
        frozenset(b.split(".")[-1] for b in registry.externally_constructed)
        | registry.parse_functions
    )
    findings: list[LintFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not _try_body_constructs_registered(node, construct_names):
            continue
        for handler in node.handlers:
            if not _handler_catches_value_or_key(handler):
                continue
            if _handler_reraises(handler):
                continue
            key = f"{module_stem}:{handler.lineno}"
            if key in _RULE_C_ALLOWLIST:
                continue
            findings.append(
                LintFinding(
                    file_path=file_path,
                    line_number=handler.lineno,
                    rule="C-validationerror-swallowed",
                    diagnostic=(
                        f"{module_stem}: except handler at line {handler.lineno} "
                        f"catches ValueError/KeyError around a registered-model "
                        f"construction and does not re-raise — the construction "
                        f"ValidationError is silently swallowed. {_RULE_C_REMEDIATION}"
                    ),
                )
            )
    return findings


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #


def run_input_hardening_gate(
    harness_root: pathlib.Path, *, registry_path: pathlib.Path | None = None
) -> LintResult:
    """Execute the gate over the harness substrate rooted at ``harness_root``.

    Raises :class:`RuntimeError` on any unreadable/unparseable file, a missing /
    malformed registry, or registry rot (a registered model absent from the
    governed tree).
    """
    src_dir = harness_root.joinpath(*_SRC_RELATIVE)
    models = discover_models(src_dir)
    registry = load_registry(registry_path)

    discovered_qualnames = {m.qualname for m in models}
    registry_qualnames = set(registry.externally_constructed) | set(
        registry.internal_only
    )
    stale = sorted(registry_qualnames - discovered_qualnames)
    if stale:
        raise RuntimeError(
            "registry names model(s) not found in the governed tree "
            f"(registry rot — rename/remove the stale entries): {stale}"
        )

    findings: list[LintFinding] = []
    findings.extend(_scan_rule_a(models, registry))
    findings.extend(_scan_rule_b(models, registry))
    for py_file in sorted(src_dir.rglob("*.py")):
        tree = _parse_module(py_file)
        findings.extend(_scan_rule_c(py_file, tree, py_file.stem, registry))

    findings.sort(key=lambda f: (str(f.file_path), f.line_number, f.rule))
    return LintResult(findings=tuple(findings), models_discovered=len(models))


# --------------------------------------------------------------------------- #
# Formatter                                                                   #
# --------------------------------------------------------------------------- #


def _display_path(
    path: pathlib.Path, harness_root: pathlib.Path | None = None
) -> str:
    if harness_root is None:
        return str(path.resolve())
    try:
        return str(path.resolve().relative_to(harness_root.resolve()))
    except ValueError:
        return str(path.resolve())


def format_findings(result: LintResult, *, harness_root: str) -> str:
    """Render a :class:`LintResult` for stdout. Mirrors
    :func:`no_destructive_resume_lint.format_findings`'s shape."""
    lines: list[str] = []
    lines.append("Input-hardening gate (story 24.2; Epic 24 Action #2)")
    lines.append(f"  harness root: {harness_root}")
    lines.append(f"  models discovered: {result.models_discovered}")
    lines.append("")

    harness_root_path = pathlib.Path(harness_root) if harness_root else None
    for finding in result.findings:
        rendered_path = _display_path(finding.file_path, harness_root=harness_root_path)
        lines.append(
            f"input-hardening-gate: {rendered_path}:"
            f"{finding.line_number} {finding.rule} {finding.diagnostic}"
        )
        lines.append("")

    if not result.findings:
        lines.append(
            f"input-hardening-gate: 0 findings "
            f"({result.models_discovered} models scanned)"
        )
    else:
        lines.append(f"input-hardening-gate: {len(result.findings)} findings")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="input-hardening-gate",
        description=(
            "Input-hardening structural CI gate (story 24.2; Epic 24 Action #2). "
            "Asserts every externally-constructed Pydantic model under "
            "src/loud_fail_harness/ is classified in a closed registry (Rule A), "
            "routes its hostile-input fields through the shared input_hardening "
            "helpers (Rule B), and that no broad except silently swallows a "
            "construction ValidationError (Rule C)."
        ),
    )
    parser.add_argument(
        "--harness-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to the loud-fail-harness package root (default: "
            "<repo-root>/tools/loud-fail-harness/). Test-injection flag; CI "
            "invocations omit it."
        ),
    )
    parser.add_argument(
        "--registry-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to the input-hardening registry YAML (default: the "
            "package-bundled _data/input_hardening_registry.yaml). Test-injection."
        ),
    )
    parser.add_argument(
        "--list-unclassified",
        action="store_true",
        help=(
            "Bootstrap aid (Task 2): print every discovered model qualname NOT "
            "yet in the registry, one per line, then exit 0. Use to enumerate "
            "and bucket models when authoring/extending the registry."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Exit codes: 0 full pass, 1 finding present, 2 harness
    error (file/registry unreadable/malformed, or registry rot)."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    harness_root: pathlib.Path
    if args.harness_root is None:
        try:
            repo_root = find_repo_root()
        except RuntimeError as exc:
            print(f"input-hardening-gate: harness-level error: {exc}", file=sys.stderr)
            return 2
        harness_root = repo_root / "tools" / "loud-fail-harness"
    else:
        harness_root = args.harness_root

    src_dir = harness_root.joinpath(*_SRC_RELATIVE)
    if not src_dir.is_dir():
        print(
            "input-hardening-gate: harness-level error: "
            f"src/loud_fail_harness/ not found under {harness_root!s}",
            file=sys.stderr,
        )
        return 2

    if args.list_unclassified:
        try:
            models = discover_models(src_dir)
            registry = _safe_registry(args.registry_path)
        except RuntimeError as exc:
            print(f"input-hardening-gate: harness-level error: {exc}", file=sys.stderr)
            return 2
        classified = set(registry.externally_constructed) | set(registry.internal_only)
        for qualname in sorted({m.qualname for m in models} - classified):
            print(qualname)
        return 0

    try:
        result = run_input_hardening_gate(
            harness_root, registry_path=args.registry_path
        )
    except RuntimeError as exc:
        print(f"input-hardening-gate: harness-level error: {exc}", file=sys.stderr)
        return 2

    print(
        format_findings(
            result, harness_root=_display_path(harness_root, harness_root=None)
        )
    )
    return 1 if result.findings else 0


def _safe_registry(registry_path: pathlib.Path | None) -> ModelRegistry:
    """Load the registry, tolerating a missing file as an empty registry so
    ``--list-unclassified`` works during initial bootstrap (before the data
    file exists)."""
    path = registry_path if registry_path is not None else _resolve_registry_path()
    if not path.is_file():
        return ModelRegistry(externally_constructed={}, internal_only=frozenset())
    return load_registry(path)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
