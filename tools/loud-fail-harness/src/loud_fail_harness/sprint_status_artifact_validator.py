"""Sprint-status-artifact subjective-field rejector (Story 16.3 substrate library).

## The central new contract (AC-4)

This library is the "validator that rejects subjective fields" half of Story
16.3's central deliverable. It exposes two pure verdict functions + a thin CLI,
mirroring :mod:`loud_fail_harness.story_doc_validator`'s pure-verdict + 0/1/2
exit-code posture (and its NO-marker-emission stance — Pattern 5
sensor-not-advisor: this is a structural gate that reports a verdict, NOT a
runtime marker-emitter).

Two complementary guarantees (defense in depth — the loud-fail / structural-
enforcement reflex, not a prose addendum):

    * :func:`validate_artifact_data` — jsonschema-validates the structured
      artifact data against ``schemas/sprint-status-artifact.yaml``. Because the
      schema declares ``additionalProperties: false`` at EVERY object level, ANY
      subjective / unknown field (``what_went_well``, ``recommendation``,
      ``lessons_learned``, ``sentiment``, …) is REJECTED — the schema-layer
      guarantee. This is also called by ``assemble_sprint_status_artifact`` on
      the assembled model's serialization BEFORE the atomic write (AC-5).
    * :func:`scan_rendered_markdown` — case-insensitively scans the rendered
      markdown's section HEADINGS against the closed
      :data:`_SUBJECTIVE_HEADING_DENYLIST` and rejects on the first match.
      Markdown is free-form, so the schema alone cannot bind the rendered file;
      the denylist is the rendered-surface guard (and the guard against a hand-
      edited artifact).

## Substrate-component identity

Substrate **LIBRARY** (sibling of ``story_doc_validator`` / ``bundle_assembly_
epic``), NOT a sixth substrate component (ADR-003 Consequence 1 keeps the
substrate closed at FIVE). Registered in ``pyproject.toml`` as a library-as-CLI-
aid (NOT a CI gate at this landing — same posture as ``story-doc-validator`` /
``marker-coverage-audit``; the artifact is runtime-emitted, not a committed
filesystem surface to scan, so CI enforcement is the test suite).
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Mapping, Sequence

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from pydantic import BaseModel, ConfigDict

from loud_fail_harness._shared import find_repo_root, load_schema

__all__ = [
    "ArtifactValidationResult",
    "scan_rendered_markdown",
    "validate_artifact_data",
]

#: Closed denylist of subjective section-heading phrases (case-insensitive,
#: substring match — so ``recommendation`` covers ``recommendations``). Markdown
#: is free-form, so the closed schema cannot bind the rendered file; this is the
#: rendered-surface guard. The objective headings the assembler emits (per-epic
#: summary, per-story summary, aggregate cost, retry-budget consumption,
#: escalation rate, active loud-fail markers) contain NONE of these.
_SUBJECTIVE_HEADING_DENYLIST: tuple[str, ...] = (
    "what went well",
    "what went badly",
    "what went poorly",
    "lessons learned",
    "recommendation",
    "retrospective",
    "action items",
    "reflection",
    "sentiment",
    "improvement",
)

#: Default on-disk schema path resolver is lazy (Epic 1 retro Action #1 — no
#: ``find_repo_root()`` at import time). Resolved inside the function unless a
#: caller injects ``schema_path`` (tests pass the repo's path explicitly).
_SCHEMA_FILENAME = "sprint-status-artifact.yaml"


class ArtifactValidationResult(BaseModel):
    """Result of a sprint-status-artifact validation (schema-data OR markdown).

    Frozen for hashability + determinism; field declaration order is load-bearing
    for byte-stable ``model_dump_json()`` (mirrors ``story_doc_validator``'s
    :class:`ValidationResult`).

    Field semantics:
        * ``accepted`` — ``True`` iff the artifact carries NO subjective/unknown
          field (data path) or NO subjective heading (markdown path).
        * ``reason`` — human-readable verdict explanation.
        * ``offending`` — the rejecting field-path / heading on rejection;
          ``None`` on acceptance.
    """

    model_config = ConfigDict(frozen=True)

    accepted: bool
    reason: str
    offending: str | None


def _schema_path() -> pathlib.Path:
    return find_repo_root() / "schemas" / _SCHEMA_FILENAME


def validate_artifact_data(
    data: Mapping[str, object],
    *,
    schema_path: pathlib.Path | None = None,
) -> ArtifactValidationResult:
    """Schema-validate the structured artifact data (AC-4 (a)).

    jsonschema-validates ``data`` against ``schemas/sprint-status-artifact.yaml``.
    Because the schema is closed (``additionalProperties: false`` at every object
    level), ANY subjective / unknown field is REJECTED — the schema-layer
    guarantee that "no subjective fields" holds.

    Args:
        data: The structured artifact data (typically
            ``SprintStatusArtifact.model_dump(mode="json")``).
        schema_path: Optional explicit schema path (a ``pathlib.Path``); defaults
            to ``<repo-root>/schemas/sprint-status-artifact.yaml`` resolved
            lazily.

    Returns:
        :class:`ArtifactValidationResult`. ``offending`` names the JSON-pointer
        path of the first (best-match) failing instance on rejection.

    Raises:
        TypeError: ``data`` is not a :class:`Mapping` (mirrors the
            ``validate_section_write`` defensive type-check → exit 2).
    """
    if not isinstance(data, Mapping):
        raise TypeError(
            f"data must be a Mapping, got {type(data).__name__}"
        )
    resolved = schema_path if schema_path is not None else _schema_path()
    schema = load_schema(resolved)
    validator = Draft202012Validator(schema)
    error = best_match(validator.iter_errors(dict(data)))
    if error is None:
        return ArtifactValidationResult(
            accepted=True,
            reason="artifact data conforms to sprint-status-artifact.yaml",
            offending=None,
        )
    pointer = "/".join(str(part) for part in error.absolute_path) or "<root>"
    return ArtifactValidationResult(
        accepted=False,
        reason=f"schema violation at {pointer}: {error.message}",
        offending=pointer,
    )


def scan_rendered_markdown(text: str) -> ArtifactValidationResult:
    """Scan rendered markdown headings for subjective content (AC-4 (b)).

    Case-insensitively scans every markdown HEADING line (``#``-prefixed) against
    the closed :data:`_SUBJECTIVE_HEADING_DENYLIST` and rejects on the first
    match. Pure; no marker emission.

    Args:
        text: The rendered artifact markdown.

    Returns:
        :class:`ArtifactValidationResult`. ``offending`` names the matched
        heading (verbatim) + the denylisted phrase on rejection.

    Raises:
        TypeError: ``text`` is not a ``str`` (→ exit 2).
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        heading = stripped.lstrip("#").strip().lower()
        for phrase in _SUBJECTIVE_HEADING_DENYLIST:
            if phrase in heading:
                return ArtifactValidationResult(
                    accepted=False,
                    reason=(
                        "rendered artifact carries a subjective heading "
                        f"(matched {phrase!r}) — the artifact is NOT a "
                        "retrospective"
                    ),
                    offending=f"{stripped} (matched {phrase!r})",
                )
    return ArtifactValidationResult(
        accepted=True,
        reason="rendered artifact carries no subjective headings",
        offending=None,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sprint-status-artifact-validator",
        description=(
            "Validate a sprint-status artifact's subjective-field abstinence "
            "(Story 16.3). --data <path.yaml> schema-validates the structured "
            "artifact data (additionalProperties:false rejects subjective "
            "fields); --artifact <path.md> scans rendered markdown headings "
            "against the subjective-heading denylist. Returns exit 0 on accept, "
            "1 on reject, 2 on harness-level error. Library-as-CLI-aid; NOT a CI "
            "gate (the artifact is runtime-emitted, test-suite-enforced)."
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--data",
        help="Path to a YAML artifact-data document to schema-validate.",
    )
    group.add_argument(
        "--artifact",
        help="Path to a rendered .md artifact to scan for subjective headings.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point (AC-4 — verbatim 0/1/2 contract from
    :func:`story_doc_validator.main`).

    Returns:
        0 — accepted; 1 — rejected; 2 — harness-level error.

    Stdout: ``result.model_dump_json(indent=2)``. Stderr (only on exit 2):
    ``"harness-level error: <message>"``.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    try:
        if args.data is not None:
            raw = yaml.safe_load(pathlib.Path(args.data).read_text(encoding="utf-8"))
            if not isinstance(raw, Mapping):
                raise TypeError(
                    f"--data file {args.data} did not parse to a YAML mapping "
                    "at top level"
                )
            result = validate_artifact_data(raw)
        else:
            text = pathlib.Path(args.artifact).read_text(encoding="utf-8")
            result = scan_rendered_markdown(text)
    except (TypeError, OSError) as exc:
        print(f"harness-level error: {exc}", file=sys.stderr)
        return 2
    print(result.model_dump_json(indent=2))
    return 0 if result.accepted else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
