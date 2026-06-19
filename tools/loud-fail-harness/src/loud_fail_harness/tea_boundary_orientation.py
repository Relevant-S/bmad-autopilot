"""TEA-boundary first-run orientation message — Story 7.8 substrate library.

## Substrate-component identity

THIS module is a substrate **library** sibling of
:mod:`loud_fail_harness.story_doc_validator` (Story 1.10b),
:mod:`loud_fail_harness.init_preconditions` (Story 7.3),
:mod:`loud_fail_harness.sample_story_scaffold` (Story 7.4),
:mod:`loud_fail_harness.config_qa_runbook_stub` (Story 7.5),
:mod:`loud_fail_harness.init_non_destructive_guard` (Story 7.6), and
:mod:`loud_fail_harness.story_doc_version_check` (Story 7.7). It is
**NOT a sixth substrate component** beyond ADR-003 Consequence 1's
enumerated five (``envelope_validator``, ``event_validator``,
``reconciler``, ``enumeration_check``, ``fixture_coverage``); the count
remains FIVE.

The module is the EIGHTH Epic-7 runtime-code introduction (after
Stories 7.2 / 7.3 / 7.4 / 7.5 / 7.6 / 7.7) and the LAST init-time-flow
Epic-7 story before Story 7.9's end-to-end benchmark.

## Architectural anchors

- **FR34** (PRD line 856) — "``/bmad-automation init`` emits a one-time
  TEA-boundary orientation message on first successful install — in
  terminal output, not just docs — stating what TEA validates vs. what
  the Automator exercises."
- **PRD line 320** — Success-Criteria framing for the < 10% TEA-
  boundary-confusion target ("directly addresses the ... target from
  Success Criteria; catches the risk where a user would otherwise
  encounter it").
- **Story 1.12a doc-promotion-boundary precedent** — the canonical
  ``## First-Run Orientation Message`` section ships at
  ``bmad-autopilot/docs/tea-vs-automator.md:25-29``; this module
  CONSUMES the section AS-IS and does NOT modify the doc.
- **Epic-7 Story 7.8 AC** (``epics.md`` lines 3108-3136) — the
  message is NOT duplicated in ``init``'s code; first-run is tracked
  via a structured field in ``_bmad/automation/config.yaml``; doc
  edits propagate to next-install runtime emissions naturally.
- **Story 7.5 config field** — ``tea_boundary_orientation_emitted`` is
  added to ``_data/config.yaml.template`` by Story 7.8 with default
  ``false``; this module READS the field on every ``init`` invocation
  and WRITES ``true`` on first successful emission.
- **Story 1.4 marker taxonomy** — Story 7.8 emits NO marker. The
  orientation message is informational, not a failure surface (Story
  1.11 atomic-vs-aggregated principle: markers represent atomic
  failure surfaces, NOT informational broadcasts).
- **Pattern 4** atomic-write — temp-file + ``os.replace``; mirrored
  byte-for-byte from
  :func:`loud_fail_harness.init_non_destructive_guard._atomic_write_text`.
- **Pattern 5** loud-fail / named invariants —
  :class:`OrientationConfigError` surfaces a structural failure mode
  (missing doc, missing section, malformed config, non-boolean field
  value) with a concrete ``reason`` discriminator.
- **Pattern 6** Python code style — strict typing, frozen Pydantic
  models, caller-injected ``project_root`` so tests use ``tmp_path``;
  presentation lives at the LLM-runtime layer (the substrate library
  does NOT print).
- **Pattern 7** story-doc adherence — the contract-pair shipping
  discipline: the marker source (the message text) lives in the doc;
  the runtime reads the doc; a single end-to-end test exercises both
  halves; drift between doc and runtime is structurally prevented.

## The contract pair

The doc (``bmad-autopilot/docs/tea-vs-automator.md``) is the source of
truth for the orientation message text. The runtime extracts the
``## First-Run Orientation Message`` section body from the doc; no
Python string literal in this module duplicates the prose. The only
structural constants are :data:`EMIT_TRACKING_FIELD` (the YAML key
name) and :data:`ORIENTATION_SECTION_HEADING` (the H2 heading the
extractor matches).

If a contributor edits the orientation text, they edit the doc and
ship the PR; the very next ``init`` first-run on a project surfaces
the updated content automatically.

## Doc-extraction mechanism

Regex-anchored heading match + body capture until the next ``## ``
heading or end-of-file. Multiline + dotall flags; case-sensitive — the
contributor-discipline note at ``tea-vs-automator.md:31-38`` forbids
heading variants. The extracted body is whitespace-stripped (leading +
trailing) before return; internal newlines and the blockquote prefix
are preserved verbatim for terminal-rendering fidelity.

## Emit-tracking arithmetic

The :data:`EMIT_TRACKING_FIELD` field in
``<project_root>/_bmad/automation/config.yaml`` is a tri-state in
practice:

* **Field absent / config absent** → treated as ``False`` (first-run
  posture; emit). Defensive against pre-7.8 configs upgrading via
  Story 7.6's additive merge.
* **Field present + value ``false``** → emit. The fresh-install path:
  Story 7.5's stub generation writes the field as ``false``; Story
  7.8's emission then flips it to ``true``.
* **Field present + value ``true``** → skip. The subsequent-run path.
* **Field present + non-boolean value** → loud-fail
  (:class:`OrientationConfigError`). The contract is boolean; silent
  coercion would mask config corruption.

## Reset semantics — interaction with Story 7.6

Per ``epics.md:3130``: "projects with prior emissions do NOT re-emit
unless explicit reset is invoked (Story 7.6)." Story 7.6's
``--overwrite-confirmed --yes`` path resets the entire config to
canonical defaults — which means
:data:`EMIT_TRACKING_FIELD` resets to ``false``, and Story 7.8's next
emission fires again. No Story-7.8 code is required for this path —
the reset-via-overwrite path is automatic by virtue of the field
living in the config that Story 7.6 already overwrites.
"""

from __future__ import annotations

import logging
import pathlib
import re
from typing import Any, Final, Literal

import yaml as _pyyaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from loud_fail_harness._shared import atomic_write_text as _atomic_write_text

__all__ = [
    "EMIT_TRACKING_FIELD",
    "ORIENTATION_SECTION_HEADING",
    "OrientationConfigError",
    "OrientationOutcome",
    "OrientationRequest",
    "emit_orientation_if_first_run",
    "evaluate_orientation_emission",
    "extract_orientation_message",
    "read_emit_tracking_field",
    "write_emit_tracking_field",
]

_logger = logging.getLogger(__name__)

#: The canonical YAML key name in
#: ``<project_root>/_bmad/automation/config.yaml`` that tracks whether
#: the FR34 orientation message has been emitted on this project.
#: Single source of truth for callers, tests, and the
#: :data:`config.yaml.template` field per Story 7.8 AC-1 + AC-5.
EMIT_TRACKING_FIELD: Final[str] = "tea_boundary_orientation_emitted"

#: The H2 heading the doc-extraction regex matches in
#: ``bmad-autopilot/docs/tea-vs-automator.md``. Byte-identical to the
#: doc heading at ``tea-vs-automator.md:25`` per the contributor-
#: discipline note at ``tea-vs-automator.md:36`` ("exactly
#: ``## First-Run Orientation Message`` — two ``#`` characters, four
#: hyphenated/spaced words, no trailing punctuation, no emoji prefix").
ORIENTATION_SECTION_HEADING: Final[str] = "## First-Run Orientation Message"

#: Path segments under ``project_root`` to the practitioner's
#: Automator config. Mirrors ``story_doc_version_check._CONFIG_PATH_SEGMENTS``.
_CONFIG_PATH_SEGMENTS: Final[tuple[str, ...]] = (
    "_bmad",
    "automation",
    "config.yaml",
)

#: Path segments to the canonical TEA-vs-Automator boundary doc when
#: ``repo_root`` resolves to the OUTER workspace root (the practitioner-
#: facing case where the LLM-runtime invokes ``init`` from the
#: practitioner's CWD that contains the ``bmad-autopilot/`` checkout).
_DOC_OUTER_WORKSPACE_SEGMENTS: Final[tuple[str, ...]] = (
    "bmad-autopilot",
    "docs",
    "tea-vs-automator.md",
)

#: Path segments to the canonical TEA-vs-Automator boundary doc when
#: ``repo_root`` resolves to the INNER repo root (the dev-time case
#: where tests run from ``bmad-autopilot/`` directly).
_DOC_INNER_REPO_SEGMENTS: Final[tuple[str, ...]] = (
    "docs",
    "tea-vs-automator.md",
)

#: Heading + body capture regex. Multiline + dotall flags; case-sensitive
#: per the contributor-discipline note. The body group is whitespace-
#: stripped by the caller before return.
_ORIENTATION_SECTION_RE: Final[re.Pattern[str]] = re.compile(
    r"(?ms)^##\s+First-Run\s+Orientation\s+Message\s*$(?P<body>.*?)(?=^##\s|\Z)"
)

#: Field-replacement regex for the present-field path of
#: :func:`write_emit_tracking_field`. Anchored at line-start and line-
#: end (``re.MULTILINE``); preserves indentation + trailing whitespace
#: via the captured groups.
_FIELD_REPLACE_RE: Final[re.Pattern[str]] = re.compile(
    rf"(?m)^(\s*{re.escape(EMIT_TRACKING_FIELD)}:\s*)(true|false)(\s*)$"
)

#: The canonical comment block + field appended when
#: :func:`write_emit_tracking_field` runs against a config that LACKS
#: the field. Byte-identical to the appended block in
#: :data:`_data/config.yaml.template` per AC-5 (single source of
#: truth — the template ships with ``false``; the appended-on-emit
#: block ships with ``true``; the surrounding comment text is
#: identical).
_APPENDED_FIELD_BLOCK_TEMPLATE: Final[str] = """\
# First-run TEA-boundary orientation tracking. `init` reads this field
# before emitting the FR34 one-time TEA-vs-Automator orientation message
# in terminal output (Story 7.8). On first emission, `init` flips this
# field to `true`; subsequent re-runs read `true` and skip the message
# per FR34's "one-time" qualifier. To force re-emission, run
# `/bmad-automation init --overwrite-confirmed --yes` (Story 7.6's
# explicit-override path; resets the entire config to canonical defaults).
# Source: FR34 (see _bmad-output/planning-artifacts/prd.md line 856)
# Default rationale: `false` on fresh install — the orientation message
# has not yet been shown; `init`'s first successful run on the project
# is the "first run" the FR34 one-time qualifier names.
"""


# --------------------------------------------------------------------------- #
# Error class — Pattern 5 named-invariant loud-fail.                          #
# --------------------------------------------------------------------------- #


class OrientationConfigError(Exception):
    """Raised when the orientation contract-pair cannot be honored.

    Pattern 5 — loud-fail / named invariants. The exception carries a
    structured ``reason`` discriminator naming the concrete failure
    mode so callers (the orchestrator-skill ``init.md`` runtime) can
    route to the correct surface OR HALT loudly rather than silently
    coercing to a sentinel.

    Mirrors the shape of
    :class:`loud_fail_harness.story_doc_version_check.StoryDocVersionDetectionError`
    and
    :class:`loud_fail_harness.install_path.InstallPathConfigError`.

    Attributes:
        reason: A short kebab-case discriminator naming the concrete
            failure. Documented values: ``"doc-missing"``,
            ``"section-heading-missing"``, ``"section-body-empty"``,
            ``"config-yaml-parse-error"``, ``"emit-field-not-boolean"``,
            ``"config-atomic-write-failed"``.
        repo_root: The repo root the doc-extractor was working with.
            ``None`` for failures unrelated to doc extraction
            (e.g., config-side failures).
        project_root: The project root the config-side reader/writer
            was working with. ``None`` for failures unrelated to the
            config (e.g., doc-side failures).
        doc_path: The doc path the extractor attempted to read.
            ``None`` for failures unrelated to doc extraction.
    """

    def __init__(
        self,
        *,
        reason: str,
        repo_root: pathlib.Path | None = None,
        project_root: pathlib.Path | None = None,
        doc_path: pathlib.Path | None = None,
    ) -> None:
        self.reason = reason
        self.repo_root = repo_root
        self.project_root = project_root
        self.doc_path = doc_path
        message = f"OrientationConfigError[{reason}]"
        if repo_root is not None:
            message += f" repo_root={repo_root!s}"
        if project_root is not None:
            message += f" project_root={project_root!s}"
        if doc_path is not None:
            message += f" doc_path={doc_path!s}"
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Typed Pydantic surface (Pattern 6 — strict typing).                         #
# --------------------------------------------------------------------------- #


class OrientationRequest(BaseModel):
    """Typed input to :func:`evaluate_orientation_emission` and
    :func:`emit_orientation_if_first_run`.

    Pattern 6 — frozen so callers cannot mutate the request mid-evaluation.
    Mirrors :class:`loud_fail_harness.init_non_destructive_guard.GuardRequest`
    and :class:`loud_fail_harness.story_doc_version_check.VersionCheckRequest`
    in shape.

    Attributes:
        project_root: The practitioner's BMAD project root. The functions
            resolve ``<project_root>/_bmad/automation/config.yaml`` for
            the emit-tracking-field read/write. REQUIRED;
            ``is_absolute`` enforced at validation time.
        repo_root: The Automator repo root — i.e., the directory
            containing ``bmad-autopilot/docs/tea-vs-automator.md``
            (outer-workspace case) OR the directory containing
            ``docs/tea-vs-automator.md`` (inner-repo case). When
            ``None``, the production functions resolve the repo root
            via :func:`_resolve_repo_root_for_orientation`. Tests
            inject ``tmp_path`` directly to bypass production resolution.
    """

    model_config = ConfigDict(frozen=True)

    project_root: pathlib.Path = Field(
        ...,
        description=(
            "The practitioner's BMAD project root; the emit-tracking "
            "field lives at <project_root>/_bmad/automation/config.yaml."
        ),
    )
    repo_root: pathlib.Path | None = Field(
        default=None,
        description=(
            "Optional Automator repo-root override. When None, "
            "resolved by walking up from this file's location to the "
            "directory containing .github/. Tests inject tmp_path."
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

    @field_validator("repo_root")
    @classmethod
    def _repo_root_must_be_absolute(
        cls, v: pathlib.Path | None
    ) -> pathlib.Path | None:
        if v is not None and not v.is_absolute():
            raise ValueError(
                f"repo_root must be an absolute path when provided; got {v!r}."
            )
        return v


class OrientationOutcome(BaseModel):
    """Typed return of :func:`evaluate_orientation_emission` and
    :func:`emit_orientation_if_first_run`.

    Pattern 6 — frozen so the orchestrator-skill cannot mutate the
    outcome between read and route.

    Attributes:
        action: One of two canonical actions. ``"emit"`` when the
            field is absent OR ``False`` (first-run posture);
            ``"skip-already-emitted"`` when the field is ``True``.
        message_text: The verbatim orientation-message body extracted
            from the doc on the ``"emit"`` branch (whitespace-stripped
            but with the ``> `` blockquote prefixes intact for terminal-
            rendering fidelity); ``None`` on the ``"skip-already-emitted"``
            branch.
        config_path: The resolved path to
            ``<project_root>/_bmad/automation/config.yaml``; always
            populated for caller transparency (regardless of whether
            the file currently exists).
        config_field_was_updated: ``True`` when the production
            :func:`emit_orientation_if_first_run` flipped the field to
            ``True`` (or appended it). Always ``False`` on the
            ``"skip-already-emitted"`` branch and on the pure-decision
            :func:`evaluate_orientation_emission` path.
    """

    model_config = ConfigDict(frozen=True)

    action: Literal["emit", "skip-already-emitted"]
    message_text: str | None
    config_path: pathlib.Path
    config_field_was_updated: bool = False


# --------------------------------------------------------------------------- #
# Internal helpers — repo-root resolution, atomic write, top-level YAML load. #
# --------------------------------------------------------------------------- #


def _resolve_repo_root_for_orientation() -> pathlib.Path:
    """Resolve the repo-root for production doc-extraction reads.

    Returns the directory containing ``.github/`` by walking up from
    this file's location, mirroring
    :func:`loud_fail_harness._shared.find_repo_root`. The function is
    duplicated locally (rather than imported) to keep this module
    pluggability-gate-clean: ``_shared`` is already classified as
    substrate, but tests in ``tests/test_pluggability_gate.py`` are
    sensitive to specific import shapes (mirrors Story 7.7's
    ``_resolve_repo_root_for_guidance`` precedent at
    ``story_doc_version_check.py:655-677``).

    Tests inject a ``repo_root`` directly via the
    :class:`OrientationRequest.repo_root` field to bypass this
    resolution path entirely.
    """
    here = pathlib.Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".github").is_dir():
            return candidate
    raise RuntimeError(
        "tea_boundary_orientation: could not locate repo root "
        f"(no .github ancestor) starting from {here}"
    )


def _ensure_trailing_newline(text: str) -> str:
    """Return ``text`` with at least one trailing newline."""
    return text if text.endswith("\n") else text + "\n"


def _resolve_config_path(project_root: pathlib.Path) -> pathlib.Path:
    """Resolve the canonical config path under ``project_root``.

    Path-arithmetic only — does NOT touch the filesystem.
    """
    target = project_root
    for segment in _CONFIG_PATH_SEGMENTS:
        target = target / segment
    return target


def _resolve_doc_path(repo_root: pathlib.Path) -> pathlib.Path:
    """Resolve the doc path under ``repo_root``, trying outer-workspace
    layout first then inner-repo fallback.

    Returns the FIRST path that exists as a file. If neither candidate
    exists, returns the second candidate (inner-repo fallback) so
    callers can include the path in the resulting structured error
    per AC-2.
    """
    outer = repo_root
    for segment in _DOC_OUTER_WORKSPACE_SEGMENTS:
        outer = outer / segment
    if outer.is_file():
        return outer
    inner = repo_root
    for segment in _DOC_INNER_REPO_SEGMENTS:
        inner = inner / segment
    return inner


# --------------------------------------------------------------------------- #
# Public API — pure doc extractor.                                            #
# --------------------------------------------------------------------------- #


def extract_orientation_message(repo_root: pathlib.Path) -> str:
    """Read the canonical TEA-vs-Automator boundary doc and return the
    body of the ``## First-Run Orientation Message`` section.

    Tries ``<repo_root>/bmad-autopilot/docs/tea-vs-automator.md`` FIRST
    (the outer-workspace case where the LLM-runtime invokes from the
    practitioner's CWD that contains the ``bmad-autopilot/`` checkout);
    if absent, tries ``<repo_root>/docs/tea-vs-automator.md`` (the
    inner-repo case where tests run from ``bmad-autopilot/`` directly).

    The extractor uses a multiline + dotall regex anchored on the H2
    heading; the captured body group is whitespace-stripped (leading +
    trailing) before return. Internal newlines and the ``> `` blockquote
    prefix are preserved verbatim — the LLM-runtime layer at
    ``init.md`` is responsible for terminal-rendering decisions per
    Pattern 6 (presentation-vs-content separation).

    Args:
        repo_root: The repo root the doc lives under. Tests inject
            ``tmp_path``; production callers resolve via
            :func:`_resolve_repo_root_for_orientation` (or pass
            ``OrientationRequest.repo_root=None`` to defer resolution).

    Returns:
        The section body as UTF-8 text, whitespace-stripped, with
        internal newlines + blockquote prefixes preserved.

    Raises:
        OrientationConfigError: ``reason="doc-missing"`` when neither
            candidate path exists OR the read raises ``OSError`` /
            ``UnicodeDecodeError``;
            ``reason="section-heading-missing"`` when the doc is
            present but the canonical H2 heading is not;
            ``reason="section-body-empty"`` when the heading matches
            but the captured body is pure whitespace.
    """
    doc_path = _resolve_doc_path(repo_root)
    if not doc_path.is_file():
        raise OrientationConfigError(
            reason="doc-missing",
            repo_root=repo_root,
            doc_path=doc_path,
        )
    try:
        text = doc_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise OrientationConfigError(
            reason="doc-missing",
            repo_root=repo_root,
            doc_path=doc_path,
        ) from exc
    match = _ORIENTATION_SECTION_RE.search(text)
    if match is None:
        raise OrientationConfigError(
            reason="section-heading-missing",
            repo_root=repo_root,
            doc_path=doc_path,
        )
    body = match.group("body").strip()
    if not body:
        raise OrientationConfigError(
            reason="section-body-empty",
            repo_root=repo_root,
            doc_path=doc_path,
        )
    return body


# --------------------------------------------------------------------------- #
# Public API — emit-tracking-field reader.                                    #
# --------------------------------------------------------------------------- #


def read_emit_tracking_field(project_root: pathlib.Path) -> bool:
    """Read the :data:`EMIT_TRACKING_FIELD` value from
    ``<project_root>/_bmad/automation/config.yaml``.

    Returns ``False`` when the config file is absent (day-zero before
    Story 7.5's stub-generation lands the file) OR the field is absent
    from an existing mapping (pre-7.8 config upgrading via Story 7.6's
    additive merge). Returns ``True`` only when the field is present
    with a true boolean value.

    Per Pattern 5 (loud-fail), raises :class:`OrientationConfigError`
    when the file exists but is malformed YAML OR the field is present
    with a non-boolean value — silent coercion would mask config
    corruption.

    Args:
        project_root: The practitioner's BMAD project root.

    Returns:
        ``True`` if the field is present with value ``True``;
        ``False`` otherwise (file absent, field absent, or value
        explicitly ``False``).

    Raises:
        OrientationConfigError: ``reason="config-yaml-parse-error"``
            when the file exists but cannot be parsed as YAML OR the
            top-level type is non-mapping OR the read raises
            ``OSError`` / ``UnicodeDecodeError``;
            ``reason="emit-field-not-boolean"`` when the field is
            present with a non-boolean value (e.g., the YAML literal
            ``"yes"``, ``1``, ``null``, a list, a mapping).
    """
    config_path = _resolve_config_path(project_root)
    if not config_path.is_file():
        return False
    try:
        raw = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise OrientationConfigError(
            reason="config-yaml-parse-error",
            project_root=project_root,
        ) from exc
    try:
        loaded: Any = _pyyaml.safe_load(raw)
    except _pyyaml.YAMLError as exc:
        raise OrientationConfigError(
            reason="config-yaml-parse-error",
            project_root=project_root,
        ) from exc
    if loaded is None:
        return False
    if not isinstance(loaded, dict):
        raise OrientationConfigError(
            reason="config-yaml-parse-error",
            project_root=project_root,
        )
    if EMIT_TRACKING_FIELD not in loaded:
        return False
    value = loaded[EMIT_TRACKING_FIELD]
    if not isinstance(value, bool):
        raise OrientationConfigError(
            reason="emit-field-not-boolean",
            project_root=project_root,
        )
    return value


# --------------------------------------------------------------------------- #
# Public API — emit-tracking-field writer.                                    #
# --------------------------------------------------------------------------- #


def write_emit_tracking_field(project_root: pathlib.Path) -> None:
    """In-place text-level config edit: set
    :data:`EMIT_TRACKING_FIELD` to ``true``.

    If the field is present, performs a regex substitution that
    preserves indentation + trailing whitespace (deterministic single
    replacement per file). If the field is absent, APPENDS the
    canonical comment block + field at the end of the file in the
    same shape as :data:`config.yaml.template`'s field section,
    preserving existing trailing-newline discipline.

    The text-level append preserves user content BYTE-FOR-BYTE — no
    ruamel round-trip risk to existing comments / quoting / order
    (mirrors :func:`loud_fail_harness.init_non_destructive_guard._additively_merge`).

    Args:
        project_root: The practitioner's BMAD project root.

    Raises:
        OrientationConfigError: ``reason="config-atomic-write-failed"``
            when the config file does not exist (Story 7.8 does NOT
            create the file; Story 7.5's stub-generator owns
            file-creation) OR the atomic-write fails;
            ``reason="config-yaml-parse-error"`` when the existing
            file cannot be parsed (malformed YAML) OR has multiple
            occurrences of the field (structural anomaly).
    """
    config_path = _resolve_config_path(project_root)
    if not config_path.is_file():
        raise OrientationConfigError(
            reason="config-atomic-write-failed",
            project_root=project_root,
        )
    try:
        existing_raw = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise OrientationConfigError(
            reason="config-yaml-parse-error",
            project_root=project_root,
        ) from exc
    # Validate that the existing file is parseable YAML before any
    # text-level edit; preserves the loud-fail posture against malformed
    # configs (per Pattern 5).
    try:
        loaded: Any = _pyyaml.safe_load(existing_raw)
    except _pyyaml.YAMLError as exc:
        raise OrientationConfigError(
            reason="config-yaml-parse-error",
            project_root=project_root,
        ) from exc
    if loaded is not None and not isinstance(loaded, dict):
        raise OrientationConfigError(
            reason="config-yaml-parse-error",
            project_root=project_root,
        )

    matches = list(_FIELD_REPLACE_RE.finditer(existing_raw))
    if len(matches) > 1:
        raise OrientationConfigError(
            reason="config-yaml-parse-error",
            project_root=project_root,
        )
    if matches:
        new_text = _FIELD_REPLACE_RE.sub(r"\1true\3", existing_raw, count=1)
    else:
        # Append-path: blank-line separator + canonical comment block +
        # the field with value true.
        prefix = _ensure_trailing_newline(existing_raw)
        appended = (
            "\n"
            + _APPENDED_FIELD_BLOCK_TEMPLATE
            + f"{EMIT_TRACKING_FIELD}: true\n"
        )
        new_text = prefix + appended
    try:
        _atomic_write_text(config_path, new_text)
    except OSError as exc:
        raise OrientationConfigError(
            reason="config-atomic-write-failed",
            project_root=project_root,
        ) from exc


# --------------------------------------------------------------------------- #
# Public API — pure-decision evaluator + production emitter.                  #
# --------------------------------------------------------------------------- #


def evaluate_orientation_emission(
    request: OrientationRequest,
) -> OrientationOutcome:
    """Pure-decision entry point — returns the canonical outcome
    WITHOUT performing the side-effecting config write.

    Used by tests + the dry-run path; production calls
    :func:`emit_orientation_if_first_run` instead which composes this
    function with the atomic config-update.

    The function:

    1. Reads the emit-tracking field via :func:`read_emit_tracking_field`.
    2. If the field is ``True``, returns
       ``OrientationOutcome(action="skip-already-emitted", message_text=None, ...)``.
    3. Otherwise, resolves the repo root (caller override or
       :func:`_resolve_repo_root_for_orientation`), invokes
       :func:`extract_orientation_message`, and returns
       ``OrientationOutcome(action="emit", message_text=<body>, ...)``
       with ``config_field_was_updated=False``.

    Args:
        request: The typed :class:`OrientationRequest`.

    Returns:
        :class:`OrientationOutcome` describing the decision (always
        ``config_field_was_updated=False`` on this path).

    Raises:
        OrientationConfigError: Propagated from
            :func:`read_emit_tracking_field` OR
            :func:`extract_orientation_message`.
    """
    config_path = _resolve_config_path(request.project_root)
    already_emitted = read_emit_tracking_field(request.project_root)
    if already_emitted:
        return OrientationOutcome(
            action="skip-already-emitted",
            message_text=None,
            config_path=config_path,
            config_field_was_updated=False,
        )
    if request.repo_root is not None:
        repo_root = request.repo_root
    else:
        try:
            repo_root = _resolve_repo_root_for_orientation()
        except RuntimeError as exc:
            raise OrientationConfigError(
                reason="doc-missing",
                project_root=request.project_root,
            ) from exc
    body = extract_orientation_message(repo_root)
    return OrientationOutcome(
        action="emit",
        message_text=body,
        config_path=config_path,
        config_field_was_updated=False,
    )


def emit_orientation_if_first_run(
    request: OrientationRequest,
) -> OrientationOutcome:
    """Production entry point — composes
    :func:`evaluate_orientation_emission` with the side-effecting
    config-update on the ``"emit"`` branch.

    The function does NOT print to stdout — the LLM-runtime wrapping
    ``init.md`` is the surface that prints ``outcome.message_text``
    (per Pattern 6 — substrate code is pure-library; presentation
    lives at the LLM-runtime layer; same posture as Story 7.6's
    outcome-print discipline).

    On the ``"emit"`` branch, calls :func:`write_emit_tracking_field`
    AFTER the message-text extraction succeeds — so an extraction
    failure does NOT flip the field (the next ``init`` re-run gets
    another chance once the doc is restored).

    Args:
        request: The typed :class:`OrientationRequest`.

    Returns:
        :class:`OrientationOutcome` with ``action`` reflecting the
        branch taken AND ``config_field_was_updated=True`` when the
        field was flipped.

    Raises:
        OrientationConfigError: Propagated from
            :func:`evaluate_orientation_emission` OR
            :func:`write_emit_tracking_field`.
    """
    outcome = evaluate_orientation_emission(request)
    if outcome.action == "skip-already-emitted":
        return outcome
    write_emit_tracking_field(request.project_root)
    return OrientationOutcome(
        action="emit",
        message_text=outcome.message_text,
        config_path=outcome.config_path,
        config_field_was_updated=True,
    )
