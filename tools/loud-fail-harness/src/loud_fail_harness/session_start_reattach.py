"""SessionStart reattachment + schema-version handling — Story 8.1 substrate library.

## Substrate-component identity

THIS module is a substrate **library** sibling of
:mod:`loud_fail_harness.init_non_destructive_guard` (Story 7.6),
:mod:`loud_fail_harness.tea_boundary_orientation` (Story 7.8), and
:mod:`loud_fail_harness.story_doc_version_check` (Story 7.7). It is **NOT a
sixth substrate component** beyond ADR-003 Consequence 1's enumerated five
(``envelope_validator``, ``event_validator``, ``reconciler``,
``enumeration_check``, ``fixture_coverage``); the count remains FIVE through
Epic 8 per the Epic 7 retro framing (``epic-7-retro-2026-05-08.md`` line 122).

The module is the FIRST Epic-8 runtime-code introduction (Stories 8.2 / 8.3 /
8.4 / 8.5 / 8.6 / 8.7 follow per the dependency map at
``epics.md`` lines 3187-3201). It replaces Story 2.7's literal SessionStart
stub at ``hooks/session-start.sh`` per ``epics.md`` line 1386 verbatim
("Story 8.1 is the single place SessionStart's real implementation lands;
reviewers reject any creep of Epic 8 logic into Epic 2's stub").

## Architectural anchors

- **FR46** (PRD line 874) — "``SessionStart`` hook detects existing
  orchestrator branches and run-state files, signaling reattachment to the
  orchestrator rather than duplicate initialization."
- **FR45** (PRD line 873) — run-state path is
  ``_bmad/automation/run-state.yaml`` (gitignored, ephemeral); architecture.md
  View 3 line 1171 places it at user-runtime.
- **NFR-R2** (PRD line 946) — "Crash recovery without duplicate state advance."
- **NFR-R7** (PRD line 951) — "No destructive resume" — the substrate is
  read-only against run-state, story-doc, sprint-status, and the git working
  tree. Story 8.6's ``can_dispatch()`` substrate guard supersedes this
  documentation commitment with structural enforcement.
- **NFR-R8** (PRD line 952) — "Cross-state consistency: story-doc canonical,
  run-state cache."
- **Story 1.4 v1 marker taxonomy** — ``recovery-state-conflict`` is the
  canonical schema-mismatch marker (``schemas/marker-taxonomy.yaml`` lines
  372-380); this module CONSUMES the existing taxonomy entry AS-IS (NO new
  marker classes). ``pointer_context_fields: []`` means no template
  interpolation is required at emission time.
- **Pattern 5** loud-fail / named invariants —
  :class:`SessionStartReattachError` surfaces substrate-level failures
  (e.g., taxonomy load failure) as a contract violation; recovery-state
  schema-mismatch surfaces as the marker class instead (the marker IS the
  loud-fail signal for the schema-mismatch sub-case per AC-6).
- **Pattern 6** Python code style — strict typing, frozen Pydantic models,
  caller-injected ``project_root`` and ``git_runner`` so tests use ``tmp_path``.

## The four ``ReattachOutcome.action`` branches

* ``no-run-state-found`` — ``<project_root>/_bmad/automation/run-state.yaml``
  does not exist; SessionStart is a no-op (silent normal startup).
* ``reattach-clean`` — file exists AND parses AND validates AND the named
  branch exists in the local git repo (when applicable); the orchestrator
  skill consumes the ``branch_name`` + ``dispatched_specialist`` +
  ``current_state`` signal at next ``/bmad-automation`` invocation.
* ``reattach-with-marker`` — file exists but validation FAILS (YAML parse
  error OR ``schema_version`` not in closed enum OR required field missing);
  ``recovery-state-conflict`` marker emitted with structured diagnostic.
* ``anomaly-branch-missing`` — file exists, validates, but the named branch
  is absent from the git repo; observability-only stderr diagnostic, NO
  marker (parallel to ``dangling-uncommitted-work``'s diagnostic-only
  posture per ADR-005 Consequence rationale at ``architecture.md`` line 497).
  Story 8.2's recovery algorithm consumes this signal.

## No state-advancing actions

No state-advancing actions: this substrate is read-only against run-state,
story-doc, sprint-status, and the git working tree. Story 8.6's
can_dispatch() substrate guard supersedes this commitment with structural
enforcement.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import re
import subprocess
import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING, Callable, Final, Literal

import yaml as _pyyaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from referencing import Registry
from referencing.jsonschema import DRAFT202012

from ._shared import find_repo_root, load_schema
from .marker_wiring import record_marker_with_context
from .run_state import RunState

if TYPE_CHECKING:
    from .specialist_dispatch import MarkerClassRegistry

__all__ = [
    "RECOVERY_STATE_CONFLICT_MARKER_CLASS",
    "RUN_STATE_RELATIVE_PATH",
    "RUN_STATE_SCHEMA_CURRENT_VERSION",
    "ReattachOutcome",
    "ReattachRequest",
    "SessionStartReattachError",
    "detect_run_state",
    "evaluate_reattach",
    "main",
    "render_recovery_state_conflict_diagnostic",
    "validate_run_state_schema",
]

_logger = logging.getLogger(__name__)

#: The architecture.md View 3 line 1171 + FR45 documented run-state path,
#: relative to ``project_root``. Sourced verbatim from
#: ``schemas/run-state.yaml`` contract-header comment block.
RUN_STATE_RELATIVE_PATH: Final[str] = "_bmad/automation/run-state.yaml"

#: The Story 1.4 v1 marker class consumed AS-IS by this module on the
#: schema-mismatch branch. NO new marker classes introduced (per Story 1.11
#: atomic-vs-aggregated principle). Sourced from
#: ``schemas/marker-taxonomy.yaml`` lines 372-380.
RECOVERY_STATE_CONFLICT_MARKER_CLASS: Final[
    Literal["recovery-state-conflict"]
] = "recovery-state-conflict"


def _current_schema_version() -> str:
    """Return the highest member of ``RunState.schema_version``'s ``Literal``.

    Evaluated at module import time (called by the module-level constant
    ``RUN_STATE_SCHEMA_CURRENT_VERSION`` below) so Story 2.2 schema bumps
    surface here without an additional edit.

    Uses version-tuple comparison (``(1, 3)`` > ``(1, 10)`` is False, so
    ``"1.10"`` correctly ranks above ``"1.3"``). Lexicographic ``max()``
    would silently report ``"1.3"`` as the max once the enum includes ``"1.10"``.
    """
    annotation = RunState.model_fields["schema_version"].annotation
    args = getattr(annotation, "__args__", ())
    if not args:
        raise SessionStartReattachError(
            reason="schema-version-annotation-empty",
            diagnostic=(
                "RunState.schema_version is not a Literal[...] with members; "
                "harness-level error — Story 2.2 schema model is malformed."
            ),
        )
    # Version-tuple sort: "1.10" > "1.3" (correct); lexicographic would give
    # "1.3" > "1.10" (wrong once the enum reaches double-digit minor versions).
    return max(args, key=lambda a: tuple(int(x) for x in str(a).split(".")))


#: Snapshot mirror of the highest ``schema_version`` enum member. Evaluated
#: at module import time via :func:`_current_schema_version`; provided for
#: diagnostic-rendering convenience so callers need not introspect the model.
RUN_STATE_SCHEMA_CURRENT_VERSION: Final[str] = _current_schema_version()


# --------------------------------------------------------------------------- #
# Error class — Pattern 5 named-invariant loud-fail.                           #
# --------------------------------------------------------------------------- #


class SessionStartReattachError(Exception):
    """Raised on substrate-level failures inside the SessionStart reattachment.

    Pattern 5 — loud-fail / named invariants. Analogous in shape to
    :class:`loud_fail_harness.install_path.InstallPathConfigError` and
    :class:`loud_fail_harness.tea_boundary_orientation.OrientationConfigError`.

    RESERVED for substrate-level errors (taxonomy registry load failure,
    schema-annotation introspection failure, file-system permission errors
    on a present run-state file). Schema-mismatch failures of the run-state
    file's CONTENT do NOT raise this — they surface as the
    ``recovery-state-conflict`` marker class via
    :func:`evaluate_reattach` (the marker IS the loud-fail signal per AC-6).

    Attributes:
        reason: A short kebab-case discriminator naming the concrete failure.
            Documented values: ``"run-state-unreadable"``,
            ``"schema-version-annotation-empty"``,
            ``"taxonomy-load-failure"``.
        diagnostic: Human-readable diagnostic naming the failure mode and
            a remediation hint per NFR-O5.
        path: The on-disk path the substrate was working with at the time
            of failure, when applicable.
    """

    def __init__(
        self,
        *,
        reason: str,
        diagnostic: str,
        path: pathlib.Path | None = None,
    ) -> None:
        self.reason = reason
        self.diagnostic = diagnostic
        self.path = path
        message = f"SessionStartReattachError[{reason}]: {diagnostic}"
        if path is not None:
            message += f" (path={path!s})"
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Typed Pydantic models (Pattern 6 — explicit, frozen, named).                 #
# --------------------------------------------------------------------------- #


_GitRunner = Callable[
    [Sequence[str], pathlib.Path], "subprocess.CompletedProcess[str]"
]


def _default_git_runner(
    args: Sequence[str], cwd: pathlib.Path
) -> "subprocess.CompletedProcess[str]":
    """Production git_runner — wraps stdlib :func:`subprocess.run`.

    Returns the :class:`subprocess.CompletedProcess` directly; never raises
    on non-zero exit (callers inspect ``returncode``). The 30-second timeout
    bounds pathological git misbehavior.
    """
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


class ReattachRequest(BaseModel):
    """Typed input to :func:`evaluate_reattach`.

    Pattern 6 — frozen so callers cannot mutate the request mid-evaluation.
    Mirrors :class:`loud_fail_harness.init_non_destructive_guard.GuardRequest`
    + :class:`loud_fail_harness.tea_boundary_orientation.OrientationRequest`
    in shape; the ``is_absolute`` field validator replicates the precedent at
    ``init_non_destructive_guard.py`` lines 224-231.

    Attributes:
        project_root: The practitioner's BMAD project root. The substrate
            inspects ``<project_root>/_bmad/automation/run-state.yaml``.
            Required; ``is_absolute`` enforced at validation time.
        git_runner: Pattern-6 dependency-injection seam for tests.
            Production runs default to a stdlib :func:`subprocess.run`
            wrapper; tests inject a stub returning a synthesized
            :class:`subprocess.CompletedProcess` so the branch-detection
            path can be exercised without a real git repo.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    project_root: pathlib.Path = Field(
        ...,
        description=(
            "Absolute path to the practitioner's project root. Read for "
            "the run-state file and the git rev-parse probe."
        ),
    )
    git_runner: _GitRunner | None = Field(
        default=None,
        description=(
            "Optional git_runner injection for tests. None → stdlib "
            "subprocess.run wrapper at evaluate-reattach time."
        ),
    )

    @field_validator("project_root")
    @classmethod
    def _project_root_must_be_absolute(cls, v: pathlib.Path) -> pathlib.Path:
        if not v.is_absolute():
            raise ValueError(
                f"project_root must be an absolute path; got {v!r}. "
                "Pass pathlib.Path.cwd() or a CLI-resolved absolute path."
            )
        return v


_ReattachAction = Literal[
    "no-run-state-found",
    "reattach-clean",
    "reattach-with-marker",
    "anomaly-branch-missing",
]


class ReattachOutcome(BaseModel):
    """Typed return of :func:`evaluate_reattach`.

    Pattern 6 — frozen so the orchestrator skill cannot mutate the outcome
    between read and route.

    Attributes:
        action: One of the four canonical actions. The CLI emits the
            stderr line shape per the action discriminator; the
            orchestrator skill at session-restart time consumes the
            structured ``session-start: reattach: ...`` prefix per
            Pattern 5's machine-parseable-diagnostic discipline.
        run_state_path: Set when the file existed; ``None`` on
            ``no-run-state-found``.
        detected_schema_version: Populated when the file parsed enough to
            surface a ``schema_version`` value (even if the value is not
            in the closed enum); ``None`` on YAML-parse-error or
            ``no-run-state-found``.
        current_schema_version: Copy of the highest ``schema_version``
            enum member at call time. Always populated.
        branch_name: The ``branch_name`` field from the parsed run-state
            when readable; ``None`` otherwise.
        current_branch: Result of ``git rev-parse --abbrev-ref HEAD``
            against ``project_root`` when the project is a git repo;
            ``None`` when not a git repo OR the git probe fails.
        dispatched_specialist: The ``dispatched_specialist`` field from
            the parsed run-state when readable; ``None`` otherwise.
        current_state: The ``current_state`` field from the parsed
            run-state when readable; ``None`` otherwise.
        marker_class: Set to ``"recovery-state-conflict"`` when
            ``action == "reattach-with-marker"``; ``None`` otherwise.
        diagnostic: The rendered marker diagnostic per AC-6; ``None`` on
            the silent branches.
        validation_failures: JSON-pointer-style paths of fields that
            failed schema validation when applicable; empty tuple
            otherwise.
    """

    model_config = ConfigDict(frozen=True)

    action: _ReattachAction
    run_state_path: pathlib.Path | None = None
    detected_schema_version: str | None = None
    current_schema_version: str
    branch_name: str | None = None
    current_branch: str | None = None
    dispatched_specialist: str | None = None
    current_state: str | None = None
    marker_class: Literal["recovery-state-conflict"] | None = None
    diagnostic: str | None = None
    validation_failures: tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# Pure detection + validation primitives.                                      #
# --------------------------------------------------------------------------- #


def detect_run_state(project_root: pathlib.Path) -> pathlib.Path | None:
    """Pure detection function for the run-state file.

    Returns the absolute path when ``<project_root>/_bmad/automation/
    run-state.yaml`` exists, else ``None``. No marker emission; no run-state
    mutation; no I/O beyond ``Path.is_file``.

    Raises:
        SessionStartReattachError: The path exists but is not readable
            (file present, ``os.access(path, os.R_OK)`` False). This is the
            substrate-level loud-fail per Pattern 5 — distinct from the
            ``no-run-state-found`` (file absent) branch which is silent.
    """
    candidate = project_root / RUN_STATE_RELATIVE_PATH
    if not candidate.is_file():
        return None
    # Defensive: file exists but cannot be read. Surface as substrate-level
    # error rather than coercing to no-run-state-found OR a synthesized
    # validation failure.
    import os

    if not os.access(candidate, os.R_OK):
        raise SessionStartReattachError(
            reason="run-state-unreadable",
            diagnostic=(
                f"run-state file at {candidate!s} exists but is not readable; "
                "remediation: check filesystem permissions OR delete and "
                "re-run /bmad-automation run <story-id> per NFR-R8."
            ),
            path=candidate,
        )
    return candidate.resolve()


def validate_run_state_schema(
    run_state_path: pathlib.Path,
) -> tuple[RunState | None, tuple[str, ...], str | None]:
    """Validate a run-state file against the current schema.

    Two-tier validation:
        1. ``jsonschema.Draft202012Validator`` against
           ``schemas/run-state.yaml`` (the contract per ADR-001).
        2. :meth:`RunState.model_validate` (Story 2.2's Pydantic model).

    On clean validation: returns ``(RunState, (), detected_schema_version)``.
    On YAML parse error: returns ``(None, ("<root>",), None)``.
    On JSON-Schema or Pydantic validation error: returns ``(None, paths,
    detected_schema_version)`` where ``paths`` is the JSON-pointer-style
    tuple naming the failing fields (e.g., ``("/schema_version",)`` when
    out-of-enum; ``("/story_id",)`` when missing-required) and
    ``detected_schema_version`` is the raw ``schema_version`` value from
    the file when parseable (``None`` on YAML-parse-error or absent key).

    The third return element avoids a second file read on the validation-
    failure path (callers no longer need to call ``_read_detected_schema_version``
    separately).

    The function does NOT raise on validation failures; the failure paths
    ARE the structured signal. It DOES raise :class:`SessionStartReattachError`
    on substrate-level errors (OS read errors, schema-file missing, or
    ``find_repo_root`` failure indicating a broken harness environment).
    """
    try:
        text = run_state_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SessionStartReattachError(
            reason="run-state-unreadable",
            diagnostic=(
                f"failed to read run-state file at {run_state_path!s}: {exc!s}"
            ),
            path=run_state_path,
        ) from exc

    try:
        parsed = _pyyaml.safe_load(text)
    except _pyyaml.YAMLError as exc:
        problem_mark = getattr(exc, "problem_mark", None)
        _logger.debug(
            "session_start_reattach: YAML parse error at %s: %s",
            problem_mark,
            exc,
        )
        return (None, ("<root>",), None)

    if not isinstance(parsed, dict):
        return (None, ("<root>",), None)

    # Extract schema_version early — used in diagnostics even on failure.
    raw_sv = parsed.get("schema_version")
    detected_schema_version: str | None = (
        raw_sv if isinstance(raw_sv, str) else None
    )

    # Tier 1: JSON-Schema validation. The run-state schema $refs into sibling
    # schemas (envelope.schema.yaml, tea-handoff-contract.yaml); register them
    # explicitly so jsonschema can resolve the references without a network
    # fetch. Wrap harness-level I/O in SessionStartReattachError so main()
    # sees a structured failure instead of a raw RuntimeError or OSError.
    try:
        schemas_dir = find_repo_root() / "schemas"
        run_state_schema = load_schema(schemas_dir / "run-state.yaml")
    except (RuntimeError, OSError) as exc:
        raise SessionStartReattachError(
            reason="schema-load-failure",
            diagnostic=(
                f"failed to load run-state schema: {exc!s}; "
                "harness-level error — verify the harness installation."
            ),
        ) from exc

    registry: Registry = Registry()
    for sibling_name in ("envelope.schema.yaml", "tea-handoff-contract.yaml"):
        sibling_path = schemas_dir / sibling_name
        if sibling_path.is_file():
            sibling_schema = load_schema(sibling_path)
            registry = registry.with_resource(
                uri=sibling_name,
                resource=DRAFT202012.create_resource(sibling_schema),
            )
    validator = Draft202012Validator(run_state_schema, registry=registry)
    schema_errors = list(validator.iter_errors(parsed))

    # Tier 2: Pydantic model validation. The Pydantic model mirrors the
    # JSON-Schema 1:1 per Story 2.2 commitment, so disagreement is a
    # programmer-error sanity-check signal (logged at WARN). The contract
    # is: prefer JSON-Schema (the schema is the contract per ADR-001).
    try:
        run_state = RunState.model_validate(parsed)
    except ValidationError as pyd_exc:
        if not schema_errors:
            _logger.warning(
                "session_start_reattach: schema/Pydantic disagreement on %s: "
                "JSON-Schema clean but Pydantic raised %s",
                run_state_path,
                pyd_exc,
            )
        run_state = None

    if schema_errors:
        # Render JSON-pointer-style paths from the absolute_path deque on
        # each error. Order is the iteration order from
        # Draft202012Validator.iter_errors (deterministic by schema-keyword
        # ordering).
        paths: list[str] = []
        for err in schema_errors:
            if err.absolute_path:
                pointer = "/" + "/".join(str(p) for p in err.absolute_path)
            else:
                # Top-level error (e.g., missing required field at root,
                # additionalProperties violation at root). For required-
                # validator errors, extract the field name via regex rather
                # than split("'") — more explicit about the expected format
                # and degrades gracefully to "<root>" when it doesn't match.
                if err.validator == "required" and err.message:
                    m = re.search(r"'([^']+)' is a required property", err.message)
                    pointer = f"/{m.group(1)}" if m else "<root>"
                else:
                    pointer = "<root>"
            if pointer not in paths:
                paths.append(pointer)
        return (None, tuple(paths), detected_schema_version)

    if run_state is None:
        return (None, ("<root>",), detected_schema_version)

    return (run_state, (), detected_schema_version)


def render_recovery_state_conflict_diagnostic(outcome: "ReattachOutcome") -> str:
    """Pure deterministic formatter producing the AC-6 diagnostic text.

    Composition (six clauses per AC-6):

    1. ``recovery-state-conflict: `` literal prefix.
    2. ``detected schema_version=<value-or-"<absent>">`` clause.
    3. ``current schema_version=<value>`` clause.
    4. ``validation failures: <comma-separated-paths>`` clause.
    5. ``remediation:`` clause enumerating the two paths verbatim per epic AC.
    6. Pointer-to-marker-taxonomy clause:
       ``see schemas/marker-taxonomy.yaml:372-380 for marker class definition``.
    """
    detected = (
        outcome.detected_schema_version
        if outcome.detected_schema_version is not None
        else "<absent>"
    )
    failures = (
        ", ".join(outcome.validation_failures)
        if outcome.validation_failures
        else "<none>"
    )
    return (
        "recovery-state-conflict: "
        f"detected schema_version={detected}; "
        f"current schema_version={outcome.current_schema_version}; "
        f"validation failures: {failures}; "
        "remediation: "
        "(a) manual run-state migration to current schema_version, "
        "(b) accept loss of prior run-state and resume from the story-doc "
        "as canonical per NFR-R8 (delete the run-state file and re-run "
        "/bmad-automation run <story-id>); "
        "see schemas/marker-taxonomy.yaml:372-380 for marker class definition"
    )


# --------------------------------------------------------------------------- #
# Helpers for the partial-parse + git probe paths.                             #
# --------------------------------------------------------------------------- #


def _read_detected_schema_version(
    run_state_path: pathlib.Path,
) -> str | None:
    """Best-effort read of ``schema_version`` from a (possibly invalid)
    run-state file.

    The diagnostic surface is more useful when we can name the
    ``detected_schema_version`` even on the validation-failure branch. This
    helper returns the value when YAML parses + the field is present + it's
    a string; ``None`` on any failure (parse error, missing key, non-string
    value).
    """
    try:
        text = run_state_path.read_text(encoding="utf-8")
        parsed = _pyyaml.safe_load(text)
    except (OSError, _pyyaml.YAMLError):
        return None
    if not isinstance(parsed, dict):
        return None
    value = parsed.get("schema_version")
    if not isinstance(value, str):
        return None
    return value


def _probe_current_branch(
    project_root: pathlib.Path, git_runner: _GitRunner | None
) -> str | None:
    """Return the current git branch name, or ``None`` if unavailable.

    Uses ``git rev-parse --abbrev-ref HEAD``. Treats any non-zero exit OR
    OSError OR ``CalledProcessError`` OR ``TimeoutExpired`` as
    "git-unavailable" (returns ``None``) per AC-3 — the absence of git is
    NOT an anomaly.
    """
    runner = git_runner if git_runner is not None else _default_git_runner
    try:
        result = runner(
            ("rev-parse", "--abbrev-ref", "HEAD"), project_root
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    if not branch:
        return None
    return branch


def _probe_branch_exists(
    project_root: pathlib.Path,
    branch_name: str,
    git_runner: _GitRunner | None,
) -> bool | None:
    """Return ``True`` when the named branch exists locally, ``False`` when
    confirmed missing, ``None`` when git itself is unavailable.

    Uses ``git show-ref --verify --quiet refs/heads/<branch_name>`` for a
    literal (non-glob) ref lookup. ``git branch --list <name>`` treats the
    argument as a shell glob pattern, which could match unintended branches
    when ``branch_name`` contains ``*``, ``?``, or ``[`` characters.

    Exit-code semantics of ``git show-ref --verify``:
      * ``0`` — ref found → ``True``
      * ``1`` — ref NOT found (explicit "ref missing" signal) → ``False``
      * ``>1`` (e.g., ``128`` for "not a git repository") — git error → ``None``
    """
    runner = git_runner if git_runner is not None else _default_git_runner
    try:
        result = runner(
            ("show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"),
            project_root,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        # show-ref --verify returns 1 specifically when the named ref does
        # not exist; this is distinct from git-level failures (exit 128+).
        return False
    # returncode > 1: git error (not a git repo, corrupted index, etc.).
    return None


# --------------------------------------------------------------------------- #
# Composite entry point.                                                       #
# --------------------------------------------------------------------------- #


def evaluate_reattach(
    request: ReattachRequest,
    *,
    run_state: RunState | None = None,
    marker_registry: "MarkerClassRegistry | None" = None,
) -> tuple[ReattachOutcome, RunState | None]:
    """Composite SessionStart-reattachment decision.

    No state-advancing actions: this substrate is read-only against
    run-state, story-doc, sprint-status, and the git working tree. Story
    8.6's can_dispatch() substrate guard supersedes this commitment with
    structural enforcement.

    The four branches:

    1. No run-state file → ``no-run-state-found`` (silent normal startup).
    2. File present, validation succeeds, branch present (or git unavailable)
       → ``reattach-clean``.
    3. File present, validation succeeds, but the named branch is missing
       from a git repo where probing succeeded → ``anomaly-branch-missing``
       (observability-only; NO marker emitted).
    4. File present, validation fails → ``reattach-with-marker``;
       ``recovery-state-conflict`` marker emitted via
       :func:`record_marker_with_context` when ``run_state`` AND
       ``marker_registry`` are both supplied.

    Args:
        request: The typed input.
        run_state: Optional runtime ``RunState``. Threaded through the
            marker emission path on the schema-mismatch branch; ``None``
            (test-without-runtime) suppresses emission and the second
            tuple-element is ``None``.
        marker_registry: Optional marker registry. Same nullability
            semantics as ``run_state``.

    Returns:
        A tuple ``(ReattachOutcome, RunState | None)``.
    """
    current_schema_version = RUN_STATE_SCHEMA_CURRENT_VERSION
    current_branch = _probe_current_branch(
        request.project_root, request.git_runner
    )

    # Branch 1 — no run-state file.
    detected = detect_run_state(request.project_root)
    if detected is None:
        return (
            ReattachOutcome(
                action="no-run-state-found",
                run_state_path=None,
                detected_schema_version=None,
                current_schema_version=current_schema_version,
                branch_name=None,
                current_branch=current_branch,
                dispatched_specialist=None,
                current_state=None,
                marker_class=None,
                diagnostic=None,
                validation_failures=(),
            ),
            run_state,
        )

    # Branches 2/3/4 — file exists; validate.
    # The third return element carries the detected schema_version directly,
    # eliminating a second file read on the validation-failure path.
    parsed_run_state, validation_failures, detected_schema_version = (
        validate_run_state_schema(detected)
    )

    # Branch 4 — validation failure.
    if validation_failures:
        outcome = ReattachOutcome(
            action="reattach-with-marker",
            run_state_path=detected,
            detected_schema_version=detected_schema_version,
            current_schema_version=current_schema_version,
            branch_name=None,
            current_branch=current_branch,
            dispatched_specialist=None,
            current_state=None,
            marker_class=RECOVERY_STATE_CONFLICT_MARKER_CLASS,
            diagnostic=None,
            validation_failures=validation_failures,
        )
        diagnostic = render_recovery_state_conflict_diagnostic(outcome)
        # Re-build with the rendered diagnostic populated. Pydantic frozen
        # discipline: model_copy with update.
        outcome = outcome.model_copy(update={"diagnostic": diagnostic})

        if run_state is None or marker_registry is None:
            return (outcome, run_state)

        # AC-6: pointer_context_fields is empty per the taxonomy (lines
        # 372-380), so the context dict is empty. The diagnostic IS the
        # rendered output; no template interpolation.
        next_run_state = record_marker_with_context(
            run_state=run_state,
            marker_class=RECOVERY_STATE_CONFLICT_MARKER_CLASS,
            sub_classification=None,
            context=None,
            marker_registry=marker_registry,
        )
        return (outcome, next_run_state)

    # Branches 2/3 — validation succeeded.
    assert parsed_run_state is not None  # narrows for mypy; validated above.
    branch_name = parsed_run_state.branch_name
    dispatched_specialist = parsed_run_state.dispatched_specialist
    current_state = parsed_run_state.current_state
    detected_schema_version = parsed_run_state.schema_version

    # Probe whether the named branch exists. None means git unavailable
    # (treated as no-anomaly per AC-3); False means branch missing
    # (anomaly); True means branch present.
    branch_exists = _probe_branch_exists(
        request.project_root, branch_name, request.git_runner
    )

    if branch_exists is False:
        # Branch 3 — anomaly: branch missing but git is otherwise functional.
        anomaly_diagnostic = (
            f"session-start: anomaly: run-state references branch "
            f"'{branch_name}' which does not exist in the local repo; "
            "remediation: run /bmad-automation status <story-id> to inspect "
            "the recovery surface OR run /bmad-automation resume <story-id> "
            "after Story 8.3 lands; Epic 8.2's full recovery algorithm "
            "consumes this signal"
        )
        return (
            ReattachOutcome(
                action="anomaly-branch-missing",
                run_state_path=detected,
                detected_schema_version=detected_schema_version,
                current_schema_version=current_schema_version,
                branch_name=branch_name,
                current_branch=current_branch,
                dispatched_specialist=dispatched_specialist,
                current_state=current_state,
                marker_class=None,
                diagnostic=anomaly_diagnostic,
                validation_failures=(),
            ),
            run_state,
        )

    # Branch 2 — reattach-clean (branch present OR git unavailable).
    return (
        ReattachOutcome(
            action="reattach-clean",
            run_state_path=detected,
            detected_schema_version=detected_schema_version,
            current_schema_version=current_schema_version,
            branch_name=branch_name,
            current_branch=current_branch,
            dispatched_specialist=dispatched_specialist,
            current_state=current_state,
            marker_class=None,
            diagnostic=None,
            validation_failures=(),
        ),
        run_state,
    )


# --------------------------------------------------------------------------- #
# CLI entry point — invoked by hooks/session-start.sh.                         #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session-start-reattach",
        description=(
            "SessionStart reattachment + schema-version handling (Story 8.1, "
            "FR46). Detects an in-flight run-state file at "
            "_bmad/automation/run-state.yaml under the supplied project "
            "root, validates it against the current schema, and emits a "
            "structured stderr line on each branch (no-run-state-found, "
            "reattach-clean, anomaly-branch-missing, or "
            "reattach-with-marker)."
        ),
    )
    parser.add_argument(
        "--project-root",
        type=pathlib.Path,
        required=True,
        help=(
            "Absolute path to the practitioner's project root. The hook "
            "passes git rev-parse --show-toplevel (with pwd fallback)."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point invoked by ``hooks/session-start.sh``.

    Exit codes per AC-9:
        * ``0`` — silent (no run-state) OR clean reattach OR anomaly
          (diagnostic only) OR schema-mismatch (marker emitted).
        * ``1`` — substrate-level error inside the harness itself
          (e.g., ``RunState`` model fails to import; this is the
          ``harness-level error`` exit per Pattern 5; never used for
          marker-emitting branches because the marker IS the loud-fail
          signal).
        * ``2`` — argparse / argument-validation failure (argparse default).

    The marker-class branch returns 0 because the marker IS the loud-fail
    signal; non-zero exit would trigger Story 6.7's ``hook-failed`` marker
    which is a less-specific class than ``recovery-state-conflict`` (per
    Pattern 5's "named diagnostic per failure class" → "more-specific
    marker wins" discipline).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    project_root = args.project_root
    if not project_root.is_absolute():
        # Hook supplies an absolute path (git rev-parse --show-toplevel ||
        # pwd both yield absolute); resolve defensively.
        project_root = project_root.resolve()

    # The CLI does NOT load run_state from disk — Story 8.1's substrate is
    # READ-ONLY against run-state per AC-5; the marker emission via
    # marker_wiring.record_marker_with_context() requires a RunState in
    # memory, which the CLI does not have. This is consistent with the
    # AC-6 flow: when the CLI runs at hook time, the marker class is
    # surfaced via the rendered stderr diagnostic (the orchestrator skill
    # consumes the structured prefix and re-emits the marker in-process
    # against the live RunState at the next /bmad-automation invocation
    # per Story 8.2's recovery algorithm).
    try:
        request = ReattachRequest(project_root=project_root)
    except ValueError as exc:
        print(f"harness-level error: {exc}", file=sys.stderr)
        return 1

    try:
        outcome, _ = evaluate_reattach(
            request, run_state=None, marker_registry=None
        )
    except SessionStartReattachError as exc:
        # Substrate-level loud-fail — print the diagnostic; exit 1.
        print(f"session-start: harness-level error: {exc}", file=sys.stderr)
        return 1

    # Render the per-branch stderr line per AC-2/3/5/6.
    if outcome.action == "no-run-state-found":
        print(
            "session-start: no in-flight Automator run detected; normal startup",
            file=sys.stderr,
        )
        return 0

    if outcome.action == "reattach-clean":
        print(
            (
                f"session-start: reattach: run-state validates against "
                f"schema_version={outcome.detected_schema_version}; "
                f"branch={outcome.branch_name}; "
                f"specialist={outcome.dispatched_specialist}; "
                f"state={outcome.current_state}; "
                "orchestrator skill consumes this signal at next "
                "/bmad-automation invocation"
            ),
            file=sys.stderr,
        )
        return 0

    if outcome.action == "anomaly-branch-missing":
        # diagnostic populated by evaluate_reattach already starts with
        # "session-start: anomaly:" per AC-3.
        print(outcome.diagnostic, file=sys.stderr)
        return 0

    # outcome.action == "reattach-with-marker" — schema-mismatch branch.
    # Prefix the rendered diagnostic with the hook-name discipline per
    # AC-6 + Story 2.7's diagnostic-format precedent.
    print(f"session-start: {outcome.diagnostic}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
