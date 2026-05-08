"""BMAD story-doc N-2 version-tolerance check + ``story-doc-version-out-of-window``
marker emission — Story 7.7 substrate library.

## Substrate-component identity

THIS module is a substrate **library** sibling of
:mod:`loud_fail_harness.story_doc_validator` (Story 1.10b),
:mod:`loud_fail_harness.init_preconditions` (Story 7.3),
:mod:`loud_fail_harness.sample_story_scaffold` (Story 7.4),
:mod:`loud_fail_harness.config_qa_runbook_stub` (Story 7.5), and
:mod:`loud_fail_harness.init_non_destructive_guard` (Story 7.6). It is
**NOT a sixth substrate component** beyond ADR-003 Consequence 1's
enumerated five (``envelope_validator``, ``event_validator``,
``reconciler``, ``enumeration_check``, ``fixture_coverage``); the count
remains FIVE.

The module is the SEVENTH Epic-7 runtime-code introduction (after
Stories 7.2 / 7.3 / 7.4 / 7.5 / 7.6) and the FIRST Epic-7 story to
wire INTO the orchestrator-state-machine specialist-dispatch flow
rather than the ``init``-time install flow.

## Architectural anchors

- **FR43** (PRD line 868) — "Automator reads story docs written in BMAD
  story-doc template formats up to N-2 minor versions old without
  failing; out-of-window versions produce a loud-fail marker with
  upgrade guidance."
- **NFR-I5** (PRD line 962) — "Story-doc version tolerance — Automator
  tolerates BMAD story-doc template formats within the configured
  window... out-of-window produces a loud-fail marker with upgrade
  guidance, not a hard failure."
- **Story 1.4 v1 marker taxonomy** — ``story-doc-version-out-of-window``
  is the canonical marker class (``schemas/marker-taxonomy.yaml``
  lines 352-358); this module CONSUMES the existing entry AS-IS (NO
  new marker classes).
- **Story 7.5 config field** — ``story_doc_version_tolerance_window``
  is shipped at ``_data/config.yaml.template:67`` (default ``2``);
  this module READS the field; does NOT modify the template.
- **Story 6.3 marker-coverage-audit pre-routing** —
  ``_data/marker_coverage_surfaces.yaml:2708-2715`` declares
  ``surface_name: orchestrator-state-machine`` with ``verdict:
  scheduled-by-story``, ``discharging_story: "7.7"``; this story
  flips the row to ``verdict: emitted``.
- **Pattern 5** loud-fail / named invariants —
  :class:`StoryDocVersionDetectionError` surfaces a structural
  detection failure (neither inline marker nor manifest fallback
  yields a parseable version) rather than coercing to a sentinel
  "unknown" version.
- **Pattern 6** Python code style — strict typing, frozen Pydantic
  models, caller-injected ``project_root`` so tests use ``tmp_path``.
- **Pattern 7** story-doc adherence — the contract-pair shipping
  discipline (``epics.md`` lines 3099-3102): the marker exists ONLY
  to point at remediation; the remediation MUST ship in the same PR;
  a single end-to-end test exercises both halves.

## The contract pair

The marker (signal) and the upgrade-guidance content (remediation) are
two halves of one contract. The marker's ``diagnostic_pointer``
references ``docs/story-doc-upgrade-guidance.md``. Updating the doc
updates the actionable guidance without code changes.

## Detection mechanism (two-tier)

1. **Inline HTML-comment marker** — ``<!-- bmm-template-version: X.Y -->``
   on the first 20 lines of the story doc. The BMM 6.2 template (at
   Story 7.7's landing) carries no inline marker; this tier is
   forward-compatible (future BMM versions or the Automator's own
   ``create-story`` workflow MAY emit one on doc generation).
2. **Manifest fallback** — ``_bmad/_config/manifest.yaml``'s ``modules``
   list, looking for ``name: bmm`` and reading ``version``. This is
   the steady-state production path at Story 7.7's landing.

Both versions are normalized to **minor-version granularity**
(``"6.2.7"`` → ``"6.2"``) — FR43's tolerance unit is "N-2 minor
versions".

If neither tier yields a parseable version,
:class:`StoryDocVersionDetectionError` propagates (Pattern 5
loud-fail). The orchestrator catches this and routes it to the
``env-setup-failed`` escalation surface; the marker class
``story-doc-version-out-of-window`` is RESERVED for "version detected,
out of window" (atomic-vs-aggregated principle from Story 1.11).

## Tolerance-window comparison

Base-10 encoding for cross-major minor-step count::

    delta = (supported_major * 10 + supported_minor) - (
        detected_major * 10 + detected_minor
    )

This gives ``5.9 → 6.2`` a delta of ``3`` (62 - 59) and ``5.8 → 6.2``
a delta of ``4`` (62 - 58), matching the contiguous minor-step count
across major boundaries. BMAD is assumed to ship fewer than 10 minors
per major; this is enforced by ``_normalize_to_minor``'s assertion guard.

Negative ``delta`` (newer-than-supported) is clamped to ``0`` —
forward-compatibility-by-default. Boundary inclusivity per
``epics.md:3106``: ``delta == window`` is silent; ``delta > window``
emits the marker.
"""

from __future__ import annotations

import logging
import pathlib
import re
from typing import TYPE_CHECKING, Final, Literal

import yaml as _pyyaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .marker_wiring import record_marker_with_context
from .run_state import RunState

if TYPE_CHECKING:
    from .specialist_dispatch import MarkerClassRegistry

__all__ = [
    "STORY_DOC_VERSION_OUT_OF_WINDOW_MARKER_CLASS",
    "SUPPORTED_BMM_TEMPLATE_VERSION",
    "StoryDocVersionDetectionError",
    "VersionCheckOutcome",
    "VersionCheckRequest",
    "check_story_doc_version",
    "detect_template_version",
    "load_upgrade_guidance",
]

_logger = logging.getLogger(__name__)

#: The BMM template minor-version Story 7.7 supports as "N" (current
#: Automator-supported version). Bumped per release per
#: ``prd.md:660-674`` ("Versioning & Deprecation"). At Story 7.7's
#: landing, the outer workspace's ``_bmad/_config/manifest.yaml``
#: declares BMM ``version: 6.2.2`` → minor-version is ``"6.2"``.
SUPPORTED_BMM_TEMPLATE_VERSION: Final[str] = "6.2"

#: The Story 1.4 v1 marker class consumed AS-IS by this module on the
#: out-of-window branch. NO new marker classes introduced (per Story
#: 1.11 atomic-vs-aggregated principle). Sourced from
#: ``schemas/marker-taxonomy.yaml`` lines 352-358.
STORY_DOC_VERSION_OUT_OF_WINDOW_MARKER_CLASS: Final[
    Literal["story-doc-version-out-of-window"]
] = "story-doc-version-out-of-window"

#: Default tolerance-window when neither caller override nor
#: ``_bmad/automation/config.yaml`` provides a value. Per
#: ``prd.md:672`` and ``_data/config.yaml.template:67``.
_DEFAULT_TOLERANCE_WINDOW: Final[int] = 2

#: Front-matter scan window. Defensive against scanning large story
#: docs end-to-end on every read. Matches the convention "front-matter
#: / header zone".
_FRONT_MATTER_LINE_BUDGET: Final[int] = 20

#: Inline-marker regex. Lowercase kebab-case is canonical per Pattern
#: 1; explicit anchoring is unnecessary because the comment-delimiter
#: tolerates surrounding whitespace via ``\s*``. Patch-version is
#: optional (``X.Y`` or ``X.Y.Z``); the function normalizes to minor.
_INLINE_VERSION_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"<!--\s*bmm-template-version:\s*(?P<version>\d+\.\d+(?:\.\d+)?)\s*-->"
)

#: Path segments under ``project_root`` to the BMAD module manifest.
#: The manifest is BMAD core's installer-output; this module reads the
#: ``modules: [{name: bmm, version: ...}]`` entry as the tier-2
#: fallback when no inline marker is present.
_MANIFEST_PATH_SEGMENTS: Final[tuple[str, ...]] = (
    "_bmad",
    "_config",
    "manifest.yaml",
)

#: Path segments under ``project_root`` to the practitioner's
#: Automator config. Story 7.5 ships the
#: ``story_doc_version_tolerance_window`` field at this canonical path.
_CONFIG_PATH_SEGMENTS: Final[tuple[str, ...]] = (
    "_bmad",
    "automation",
    "config.yaml",
)

#: Filename + repo-relative segments for the upgrade-guidance doc.
#: Lives at ``<repo_root>/docs/story-doc-upgrade-guidance.md`` per
#: Story 1.12a's doc-promotion-boundary precedent.
_UPGRADE_GUIDANCE_DOC_SEGMENTS: Final[tuple[str, ...]] = (
    "docs",
    "story-doc-upgrade-guidance.md",
)

#: Section heading for version-specific upgrade guidance. Stripping the
#: trailing ``X.Y`` portion is delegated to the regex below.
_VERSION_SPECIFIC_HEADING_RE: Final[re.Pattern[str]] = re.compile(
    r"^## Upgrading from version (?P<version>\d+\.\d+)\b.*$",
    re.MULTILINE,
)

#: Section heading for the catch-all guidance. Used when the
#: detected-version-specific section is absent.
_CATCH_ALL_HEADING_RE: Final[re.Pattern[str]] = re.compile(
    r"^## Older versions\b.*$", re.MULTILINE
)

#: Heading prefix for any H2 section. Used to delimit the body of a
#: located section (heading-to-next-heading or EOF).
_NEXT_H2_HEADING_RE: Final[re.Pattern[str]] = re.compile(
    r"^## ", re.MULTILINE
)


# --------------------------------------------------------------------------- #
# Error class — Pattern 5 named-invariant loud-fail.                           #
# --------------------------------------------------------------------------- #


class StoryDocVersionDetectionError(Exception):
    """Raised when version detection cannot produce a parseable result.

    Pattern 5 — loud-fail / named invariants. The exception carries a
    structured ``reason`` discriminator naming the concrete failure
    mode so callers (the orchestrator-state-machine wiring) can route
    to the correct escalation surface.

    Per AC-5: this class is RESERVED for "version-undetectable" — a
    distinct concern from "version-detected, out-of-window" (which
    surfaces the ``story-doc-version-out-of-window`` marker class).
    The atomic-vs-aggregated principle from Story 1.11 holds —
    separate signals for separate concerns.

    Attributes:
        reason: A short kebab-case discriminator naming the concrete
            failure. Documented values: ``"manifest-missing"``,
            ``"manifest-yaml-parse-error"``,
            ``"bmm-module-not-listed"``,
            ``"bmm-version-field-missing"``,
            ``"bmm-version-field-unparseable"``,
            ``"tolerance-window-not-an-integer"``,
            ``"upgrade-guidance-content-missing"``,
            ``"config-yaml-parse-error"``,
            ``"story-doc-unreadable"``.
        story_doc_path: The story-doc path the detector was working
            with at the time of failure. ``None`` for failures
            unrelated to the story doc (e.g., tolerance-window or
            upgrade-guidance failures).
        project_root: The project root the detector was working with.
            Same nullability semantics as ``story_doc_path``.
    """

    def __init__(
        self,
        *,
        reason: str,
        story_doc_path: pathlib.Path | None = None,
        project_root: pathlib.Path | None = None,
    ) -> None:
        self.reason = reason
        self.story_doc_path = story_doc_path
        self.project_root = project_root
        message = f"StoryDocVersionDetectionError[{reason}]"
        if story_doc_path is not None:
            message += f" story_doc={story_doc_path!s}"
        if project_root is not None:
            message += f" project_root={project_root!s}"
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Typed Pydantic models (Pattern 6 — explicit, frozen, named).                 #
# --------------------------------------------------------------------------- #


class VersionCheckRequest(BaseModel):
    """Typed input to :func:`check_story_doc_version`.

    Pattern 6 — frozen so callers cannot mutate the request mid-check.
    Mirrors :class:`loud_fail_harness.init_non_destructive_guard.GuardRequest`
    + :class:`loud_fail_harness.sample_story_scaffold.SampleScaffoldRequest`
    in shape; the ``is_absolute`` field validators replicate the
    precedent at ``sample_story_scaffold.py:202-211``.

    Attributes:
        story_doc_path: The absolute path to the story doc the
            orchestrator just located via
            :func:`loud_fail_harness.orchestrator_run_entry.default_story_doc_resolver`.
            Required; ``is_absolute`` enforced at validation time.
        project_root: The practitioner's project root. The detector
            reads ``<project_root>/_bmad/_config/manifest.yaml`` for
            the manifest-fallback tier and
            ``<project_root>/_bmad/automation/config.yaml`` for the
            tolerance-window override (Story 7.5 field). Required;
            ``is_absolute`` enforced.
        tolerance_window: Caller-provided override. When ``None``
            (default), the function reads the config-file value;
            falls back to :data:`_DEFAULT_TOLERANCE_WINDOW` when the
            config file is absent OR the field is absent. The
            override is the highest-precedence source so tests can
            exercise boundary conditions deterministically.
    """

    model_config = ConfigDict(frozen=True)

    story_doc_path: pathlib.Path = Field(
        ...,
        description=(
            "Absolute path to the located story doc. Read for the "
            "tier-1 inline-marker scan."
        ),
    )
    project_root: pathlib.Path = Field(
        ...,
        description=(
            "Absolute path to the practitioner's project root. Read "
            "for the tier-2 manifest fallback and the tolerance-"
            "window config override."
        ),
    )
    tolerance_window: int | None = Field(
        default=None,
        description=(
            "Caller-provided override for the tolerance window. None "
            "→ read from <project_root>/_bmad/automation/config.yaml; "
            "absent in config → fall back to default 2."
        ),
    )

    @field_validator("story_doc_path")
    @classmethod
    def _story_doc_path_must_be_absolute(cls, v: pathlib.Path) -> pathlib.Path:
        if not v.is_absolute():
            raise ValueError(
                f"story_doc_path must be an absolute path; got {v!r}. "
                "Pass a pathlib.Path resolved by the orchestrator's "
                "story-doc resolver."
            )
        return v

    @field_validator("project_root")
    @classmethod
    def _project_root_must_be_absolute(cls, v: pathlib.Path) -> pathlib.Path:
        if not v.is_absolute():
            raise ValueError(
                f"project_root must be an absolute path; got {v!r}. "
                "Pass pathlib.Path.cwd() or a CLI-resolved absolute path."
            )
        return v

    @field_validator("tolerance_window")
    @classmethod
    def _tolerance_window_must_be_non_negative(
        cls, v: int | None
    ) -> int | None:
        if v is not None and v < 0:
            raise ValueError(
                f"tolerance_window must be non-negative; got {v!r}."
            )
        return v


class VersionCheckOutcome(BaseModel):
    """Typed return of :func:`check_story_doc_version`.

    Pattern 6 — frozen so the orchestrator cannot mutate the outcome
    between read and route.

    Attributes:
        action: One of two canonical actions. The orchestrator
            ALWAYS proceeds with the story-doc read per FR43 + NFR-I5
            verbatim ("not a hard failure"); the marker is a SIGNAL,
            not a HALT.
        detected_version: The BMM template minor-version detected
            (e.g., ``"6.0"``, ``"6.1"``, ``"6.2"``). Always populated
            on a successful (non-raising) call.
        supported_version: Snapshot of
            :data:`SUPPORTED_BMM_TEMPLATE_VERSION` at the time of the
            call.
        tolerance_window: The resolved window value (caller override
            → config-file value → default ``2``).
        delta_minor_versions: Base-10 encoded minor-step count:
            ``(supported_major * 10 + supported_minor) -
            (detected_major * 10 + detected_minor)``. For within-major
            comparisons this reduces to ``supported_minor -
            detected_minor``; for cross-major comparisons (e.g.,
            ``detected="5.9"``, ``supported="6.2"``) it gives the
            contiguous minor-step count (``62 - 59 = 3``). Always
            ``>= 0`` because newer-than-supported is clamped to ``0``
            (forward-compatibility-by-default).
        diagnostic_pointer: Set when ``action="proceed-with-marker"``;
            carries the interpolated text per AC-4. ``None`` on the
            silent branch.
    """

    model_config = ConfigDict(frozen=True)

    action: Literal["proceed-silent", "proceed-with-marker"]
    detected_version: str
    supported_version: str
    tolerance_window: int
    delta_minor_versions: int
    diagnostic_pointer: str | None = None


# --------------------------------------------------------------------------- #
# Internal helpers.                                                            #
# --------------------------------------------------------------------------- #


def _normalize_to_minor(version: str) -> str:
    """Normalize an ``X.Y`` or ``X.Y.Z`` version string to ``X.Y``.

    The function does NOT validate the input shape (the caller's
    regex / yaml-load already constrained it to digits + dots);
    splitting on ``.`` and re-joining the first two parts is
    sufficient.
    """
    parts = version.split(".")
    if len(parts) < 2:
        # Defensive: should never happen because callers have
        # already validated the shape via regex or YAML parsing.
        # Treat as a Pattern-5 invariant violation.
        raise StoryDocVersionDetectionError(
            reason="bmm-version-field-unparseable",
        )
    # Guard for the base-10 cross-major encoding used in
    # check_story_doc_version.  BMAD reaching minor >= 10 would cause
    # the base-10 positional encoding to overlap between majors (e.g.,
    # major=5 minor=10 → 60, same as major=6 minor=0). Fail loudly
    # rather than silently producing a wrong delta.
    try:
        minor_int = int(parts[1])
    except ValueError:
        raise StoryDocVersionDetectionError(
            reason="bmm-version-field-unparseable",
        )
    if minor_int >= 10:
        raise StoryDocVersionDetectionError(
            reason="bmm-version-field-unparseable",
        )
    return f"{parts[0]}.{parts[1]}"


def _read_inline_marker(story_doc_path: pathlib.Path) -> str | None:
    """Tier-1 detection: scan the first 20 lines for the inline marker.

    Returns the normalized minor-version string when a match is found,
    else ``None``. The ``story_doc_path`` is expected to be a readable
    file resolved by the orchestrator's story-doc resolver; an
    ``OSError`` or encoding error at this point signals a resolver bug
    or a TOCTOU race and raises :class:`StoryDocVersionDetectionError`
    (reason ``"story-doc-unreadable"``) rather than silently falling
    through to the manifest fallback.

    When MULTIPLE inline markers appear in the first 20 lines, the
    FIRST match wins (deterministic; per AC-2 verbatim).
    """
    try:
        text = story_doc_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise StoryDocVersionDetectionError(
            reason="story-doc-unreadable",
            story_doc_path=story_doc_path,
        ) from exc
    front_matter = "\n".join(text.splitlines()[:_FRONT_MATTER_LINE_BUDGET])
    match = _INLINE_VERSION_MARKER_RE.search(front_matter)
    if match is None:
        return None
    return _normalize_to_minor(match.group("version"))


def _read_manifest_bmm_version(
    project_root: pathlib.Path,
    story_doc_path: pathlib.Path,
) -> str:
    """Tier-2 detection: parse ``_bmad/_config/manifest.yaml`` for the
    BMM module's ``version`` field.

    Raises :class:`StoryDocVersionDetectionError` with a structured
    ``reason`` per Pattern 5 when the manifest cannot be read or the
    BMM entry is missing / malformed.
    """
    manifest_path = project_root
    for segment in _MANIFEST_PATH_SEGMENTS:
        manifest_path = manifest_path / segment
    if not manifest_path.is_file():
        raise StoryDocVersionDetectionError(
            reason="manifest-missing",
            story_doc_path=story_doc_path,
            project_root=project_root,
        )
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # "File present but unreadable" is distinct from "YAML malformed"
        # so the orchestrator can give the practitioner targeted guidance.
        raise StoryDocVersionDetectionError(
            reason="manifest-unreadable",
            story_doc_path=story_doc_path,
            project_root=project_root,
        ) from exc
    try:
        manifest = _pyyaml.safe_load(text)
    except _pyyaml.YAMLError as exc:
        raise StoryDocVersionDetectionError(
            reason="manifest-yaml-parse-error",
            story_doc_path=story_doc_path,
            project_root=project_root,
        ) from exc
    if not isinstance(manifest, dict):
        raise StoryDocVersionDetectionError(
            reason="manifest-yaml-parse-error",
            story_doc_path=story_doc_path,
            project_root=project_root,
        )
    modules = manifest.get("modules")
    if not isinstance(modules, list):
        raise StoryDocVersionDetectionError(
            reason="bmm-module-not-listed",
            story_doc_path=story_doc_path,
            project_root=project_root,
        )
    bmm_entry: dict[str, object] | None = None
    for entry in modules:
        if isinstance(entry, dict) and entry.get("name") == "bmm":
            bmm_entry = entry
            break
    if bmm_entry is None:
        raise StoryDocVersionDetectionError(
            reason="bmm-module-not-listed",
            story_doc_path=story_doc_path,
            project_root=project_root,
        )
    raw_version = bmm_entry.get("version")
    if raw_version is None:
        # Field is absent from the BMM entry.
        raise StoryDocVersionDetectionError(
            reason="bmm-version-field-missing",
            story_doc_path=story_doc_path,
            project_root=project_root,
        )
    if not isinstance(raw_version, str) or not raw_version:
        # Field is present but holds the wrong type (YAML int, bool, etc.)
        # or is an empty string — structurally unparseable.
        raise StoryDocVersionDetectionError(
            reason="bmm-version-field-unparseable",
            story_doc_path=story_doc_path,
            project_root=project_root,
        )
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", raw_version):
        raise StoryDocVersionDetectionError(
            reason="bmm-version-field-unparseable",
            story_doc_path=story_doc_path,
            project_root=project_root,
        )
    return _normalize_to_minor(raw_version)


def _resolve_tolerance_window(
    project_root: pathlib.Path,
    caller_override: int | None,
) -> int:
    """Resolve the effective tolerance-window per AC-3 precedence:

    1. Caller-provided override (``request.tolerance_window``) when
       not ``None``.
    2. ``story_doc_version_tolerance_window`` field in
       ``<project_root>/_bmad/automation/config.yaml`` when the
       config file exists AND the field is present AND it parses
       as an ``int``.
    3. Default :data:`_DEFAULT_TOLERANCE_WINDOW` (``2``) — used when
       the config file is absent OR the field is absent.

    Raises :class:`StoryDocVersionDetectionError` (reason
    ``tolerance-window-not-an-integer``) if the config file declares
    the field with a non-integer or negative value (Pattern 5 — the
    contract is structurally violated).
    """
    if caller_override is not None:
        return caller_override
    config_path = project_root
    for segment in _CONFIG_PATH_SEGMENTS:
        config_path = config_path / segment
    if not config_path.is_file():
        return _DEFAULT_TOLERANCE_WINDOW
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        # File disappeared between is_file() and read_text() — treat
        # as absent and fall back to default.
        return _DEFAULT_TOLERANCE_WINDOW
    except UnicodeDecodeError as exc:
        # Non-UTF-8 bytes in the config file are a structural violation
        # (Pattern 5 — corrupt boundary input, not a benign absence).
        raise StoryDocVersionDetectionError(
            reason="config-yaml-parse-error",
            project_root=project_root,
        ) from exc
    try:
        config = _pyyaml.safe_load(text)
    except (_pyyaml.YAMLError, UnicodeDecodeError) as exc:
        # Pattern 5 — a corrupt or non-UTF-8 config file is a
        # structural violation at the project_root boundary, not a
        # benign "file absent" case. Raise loudly so the orchestrator
        # can route to the env-setup-failed escalation surface.
        raise StoryDocVersionDetectionError(
            reason="config-yaml-parse-error",
            project_root=project_root,
        ) from exc
    if not isinstance(config, dict):
        return _DEFAULT_TOLERANCE_WINDOW
    if "story_doc_version_tolerance_window" not in config:
        return _DEFAULT_TOLERANCE_WINDOW
    raw = config["story_doc_version_tolerance_window"]
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        # PyYAML maps ``true`` / ``false`` to bool (subclass of int);
        # explicitly reject. Strings, floats, lists, negative ints, etc.
        # all hit this branch.
        raise StoryDocVersionDetectionError(
            reason="tolerance-window-not-an-integer",
            project_root=project_root,
        )
    return raw


def _build_diagnostic_pointer(
    *,
    detected_version: str,
    supported_version: str,
    tolerance_window: int,
    delta_minor_versions: int,
) -> str:
    """Build the AC-4 verbatim diagnostic_pointer interpolation.

    The first sentence-block reproduces the prose verbatim from
    ``schemas/marker-taxonomy.yaml:354-356`` (Pattern 7's verbatim-
    text discipline); the subsequent specifics interpolate the four
    runtime values. Mirrors the format-init-diagnostic structure
    from Story 7.3.
    """
    return (
        "FR43 (N-2 minor-version tolerance window) + NFR-I5 "
        "(story-doc version tolerance behavior). An out-of-window "
        "story-doc template version surfaces this marker plus "
        "upgrade guidance, rather than failing hard. "
        f"Detected BMM template version: {detected_version}. "
        f"Current Automator-supported version: {supported_version}. "
        f"Tolerance window: {tolerance_window} minor versions. "
        f"Detected version is {delta_minor_versions} minor versions behind. "
        "Upgrade guidance: see docs/story-doc-upgrade-guidance.md "
        f"(the 'Upgrading from version {detected_version}' section, "
        "OR the catch-all 'Older versions' section if no "
        "version-specific section exists)."
    )


def _resolve_repo_root_for_guidance() -> pathlib.Path:
    """Resolve the repo-root for production upgrade-guidance reads.

    Returns the directory containing ``.github/`` by walking up from
    this file's location, mirroring
    :func:`loud_fail_harness._shared.find_repo_root`. The function
    is duplicated locally (rather than imported) to keep this module
    Story-1.10a-pluggability-gate-clean: ``_shared`` is already
    classified as substrate, but tests in ``tests/test_pluggability_gate.py``
    are sensitive to the specific import shape.

    Tests inject a ``repo_root`` directly via the
    :func:`load_upgrade_guidance` keyword argument to bypass this
    resolution path entirely.
    """
    here = pathlib.Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".github").is_dir():
            return candidate
    raise RuntimeError(
        "story_doc_version_check: could not locate repo root "
        f"(no .github ancestor) starting from {here}"
    )


# --------------------------------------------------------------------------- #
# Public API.                                                                  #
# --------------------------------------------------------------------------- #


def detect_template_version(
    story_doc_path: pathlib.Path,
    project_root: pathlib.Path,
) -> str:
    """Pure detection function: return the detected BMM template
    minor-version as a string.

    No marker emission, no run-state mutation. Used internally by
    :func:`check_story_doc_version` AND callable by tests for fixture
    introspection.

    Detection mechanism per AC-2:

    1. Scan the first 20 lines of ``story_doc_path`` for an inline
       ``<!-- bmm-template-version: X.Y -->`` marker. When present,
       the first match wins (deterministic).
    2. Fall back to ``<project_root>/_bmad/_config/manifest.yaml``,
       reading the ``modules: [{name: bmm, version: X.Y.Z}]`` entry.

    The result is normalized to minor-version granularity (``"6.2.7"``
    → ``"6.2"``).

    Args:
        story_doc_path: Absolute path to the story doc.
        project_root: Absolute path to the practitioner's project
            root.

    Returns:
        The detected BMM template minor-version as a string.

    Raises:
        StoryDocVersionDetectionError: Neither tier yielded a
            parseable version. The exception's ``reason`` field
            names the concrete failure.
    """
    inline_version = _read_inline_marker(story_doc_path)
    if inline_version is not None:
        return inline_version
    return _read_manifest_bmm_version(project_root, story_doc_path)


def check_story_doc_version(
    request: VersionCheckRequest,
    *,
    run_state: RunState | None = None,
    marker_registry: MarkerClassRegistry | None = None,
) -> tuple[VersionCheckOutcome, RunState | None]:
    """Compose detection + tolerance-window comparison + (conditionally)
    marker emission.

    The canonical entry point for orchestrator-state-machine wiring.
    Mirrors the ``(result, run_state)`` accumulation shape from
    :func:`loud_fail_harness.init_preconditions.run_init_preconditions`
    and
    :func:`loud_fail_harness.init_non_destructive_guard.evaluate_non_destructive_guard`.

    On the silent branch (``delta <= tolerance_window``):

    * Returns ``(outcome, run_state)`` where
      ``outcome.action="proceed-silent"`` and ``outcome.diagnostic_pointer
      is None``.
    * Does NOT call :func:`loud_fail_harness.marker_wiring.record_marker_with_context`.

    On the marker branch (``delta > tolerance_window``):

    * Builds the AC-4 ``diagnostic_pointer`` interpolation.
    * When ``run_state is not None`` AND ``marker_registry is not None``,
      records the ``story-doc-version-out-of-window`` marker EXACTLY
      ONCE on the run-state via
      :func:`loud_fail_harness.marker_wiring.record_marker_with_context`.
    * When ``run_state is None`` (e.g., test exercises the function
      without a runtime), the marker is NOT emitted; the second
      tuple-element is ``None``. The orchestrator-state-machine
      ALWAYS provides a non-None ``run_state`` at runtime, so the
      production path always emits the marker.

    Args:
        request: The typed input.
        run_state: Optional runtime ``RunState``. Threaded through
            the marker emission path on the out-of-window branch;
            ``None`` (test-without-runtime) suppresses emission.
        marker_registry: Optional marker registry. Same nullability
            semantics as ``run_state``.

    Returns:
        A tuple ``(VersionCheckOutcome, RunState | None)``.

    Raises:
        StoryDocVersionDetectionError: Detection failed in
            :func:`detect_template_version`, OR the tolerance-window
            config-file value is non-integer. The exception
            propagates UNCHANGED to the caller (Pattern 5 — the
            orchestrator routes it to the ``env-setup-failed``
            escalation surface; this function does NOT swallow into
            a sentinel ``VersionCheckOutcome``).
    """
    detected = detect_template_version(
        request.story_doc_path, request.project_root
    )
    supported = SUPPORTED_BMM_TEMPLATE_VERSION
    tolerance_window = _resolve_tolerance_window(
        request.project_root, request.tolerance_window
    )

    # Compute the minor-step delta. For the within-major case, this
    # reduces to ``supported_minor - detected_minor`` per AC-3 verbatim.
    # For the cross-major case (e.g., supported=6.2, detected=5.9), the
    # AC-7 fixture-sweep verbatim test (case 21) demands ``delta=3``
    # for ``5.9 → 6.2`` and ``delta=4`` for ``5.8 → 6.2`` — i.e., the
    # contiguous minor-step count across BMAD's release history. We
    # encode this with a base-10 normalization: ``major * 10 + minor``
    # gives ``6.2 → 62``, ``5.9 → 59``, ``5.8 → 58``, ``6.0 → 60``,
    # producing the expected deltas. The assumption (BMAD ships at
    # most 9 minors per major before bumping) is enforced by
    # _normalize_to_minor's assertion; if violated, detection raises
    # StoryDocVersionDetectionError before reaching this computation.
    detected_major, detected_minor = (
        int(detected.split(".")[0]),
        int(detected.split(".")[1]),
    )
    supported_parts = supported.split(".")
    supported_major = int(supported_parts[0])
    supported_minor = int(supported_parts[1])
    # Guard the same base-10 assumption enforced for detected versions by
    # _normalize_to_minor: BMAD ships at most 9 minors per major before
    # bumping. If the constant violates this, raise loudly (programmer error).
    if supported_minor >= 10:
        raise StoryDocVersionDetectionError(
            reason="bmm-version-field-unparseable",
            project_root=request.project_root,
        )
    raw_delta = (supported_major * 10 + supported_minor) - (
        detected_major * 10 + detected_minor
    )
    # Negative delta (newer-than-supported) is clamped to 0 per
    # AC-3 ("forward-compatibility-by-default").
    delta = max(0, raw_delta)

    if delta <= tolerance_window:
        return (
            VersionCheckOutcome(
                action="proceed-silent",
                detected_version=detected,
                supported_version=supported,
                tolerance_window=tolerance_window,
                delta_minor_versions=delta,
                diagnostic_pointer=None,
            ),
            run_state,
        )

    # Out-of-window branch.
    diagnostic_pointer = _build_diagnostic_pointer(
        detected_version=detected,
        supported_version=supported,
        tolerance_window=tolerance_window,
        delta_minor_versions=delta,
    )
    outcome = VersionCheckOutcome(
        action="proceed-with-marker",
        detected_version=detected,
        supported_version=supported,
        tolerance_window=tolerance_window,
        delta_minor_versions=delta,
        diagnostic_pointer=diagnostic_pointer,
    )
    if run_state is None or marker_registry is None:
        return (outcome, run_state)

    try:
        repo_root = _resolve_repo_root_for_guidance()
    except RuntimeError:
        # Defensive: if the repo-root can't be resolved at runtime
        # (e.g., the harness is being exercised outside its source
        # checkout), fall back to ``project_root`` so the marker
        # context still carries a best-effort path. The marker
        # itself remains useful.
        _logger.info(
            "story_doc_version_check: repo root unresolvable; "
            "using project_root as upgrade_guidance_path basis"
        )
        repo_root = request.project_root
    upgrade_guidance_path = repo_root
    for segment in _UPGRADE_GUIDANCE_DOC_SEGMENTS:
        upgrade_guidance_path = upgrade_guidance_path / segment

    note = (
        f"detected {detected} < supported {supported} by "
        f"{delta} minor versions; tolerance window is "
        f"{tolerance_window}; see upgrade guidance"
    )
    context: dict[str, object] = {
        "detected_version": detected,
        "supported_version": supported,
        "tolerance_window": tolerance_window,
        "delta_minor_versions": delta,
        "story_doc_path": str(request.story_doc_path),
        "upgrade_guidance_path": str(upgrade_guidance_path),
        "note": note,
        # AC-4: store the pre-rendered interpolated text in RunState so
        # the bundle renderer can surface the version-specific pointer
        # without reconstructing it from the individual fields.
        "diagnostic_pointer": diagnostic_pointer,
    }
    next_run_state = record_marker_with_context(
        run_state=run_state,
        marker_class=STORY_DOC_VERSION_OUT_OF_WINDOW_MARKER_CLASS,
        sub_classification=None,
        context=context,
        marker_registry=marker_registry,
    )
    return (outcome, next_run_state)


def load_upgrade_guidance(
    detected_version: str,
    *,
    repo_root: pathlib.Path | None = None,
) -> str:
    """Load the upgrade-guidance section corresponding to ``detected_version``.

    Reads ``<repo_root>/docs/story-doc-upgrade-guidance.md`` and returns
    the body of the H2-section matching ``## Upgrading from version
    {detected_version}`` if present, else the body of the catch-all
    section ``## Older versions ...`` if present. Raises
    :class:`StoryDocVersionDetectionError` (reason
    ``upgrade-guidance-content-missing``) when the doc is absent or
    when neither section can be located — Pattern 5: the doc is part
    of the contract pair; missing content is a structural failure.

    Section-extraction is regex-only (no full markdown AST parsing
    per Pattern 6 — keep substrate code unfussy).

    Args:
        detected_version: The minor-version string returned by
            :func:`detect_template_version` (e.g., ``"6.0"``,
            ``"5.9"``).
        repo_root: Optional repo-root override. When ``None``, the
            function resolves the repo-root by walking up from this
            file's location to the directory containing ``.github/``
            (mirroring :func:`loud_fail_harness._shared.find_repo_root`).
            Tests inject ``tmp_path`` per Pattern 6.

    Returns:
        The section body as a single ``str`` (heading line
        included). Empty-but-present sections return their (empty
        body) heading line.

    Raises:
        StoryDocVersionDetectionError: The doc is missing OR neither
            the version-specific section nor the catch-all section
            is present.
    """
    if repo_root is not None:
        resolved_root = repo_root
    else:
        try:
            resolved_root = _resolve_repo_root_for_guidance()
        except RuntimeError as exc:
            raise StoryDocVersionDetectionError(
                reason="upgrade-guidance-content-missing",
            ) from exc
    doc_path = resolved_root
    for segment in _UPGRADE_GUIDANCE_DOC_SEGMENTS:
        doc_path = doc_path / segment
    if not doc_path.is_file():
        raise StoryDocVersionDetectionError(
            reason="upgrade-guidance-content-missing",
        )
    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError:
        # TOCTOU: is_file() passed but read_text failed (permissions
        # revoked, race condition).  Route to the same structured error
        # as "doc missing" so callers have a single catch point.
        raise StoryDocVersionDetectionError(
            reason="upgrade-guidance-content-missing",
        )

    # Find a version-specific section first.
    for match in _VERSION_SPECIFIC_HEADING_RE.finditer(text):
        if match.group("version") == detected_version:
            return _extract_section_body(text, match.start())

    # Fall back to the catch-all.
    catch_all_match = _CATCH_ALL_HEADING_RE.search(text)
    if catch_all_match is not None:
        return _extract_section_body(text, catch_all_match.start())

    raise StoryDocVersionDetectionError(
        reason="upgrade-guidance-content-missing",
    )


def _extract_section_body(text: str, section_start: int) -> str:
    """Return the body of an H2-section beginning at ``section_start``.

    Body extends from the heading line through (but not including)
    the next ``^## `` heading or EOF. The leading heading line is
    INCLUDED in the returned string so callers see the full section
    context.
    """
    rest = text[section_start:]
    # Skip the heading line itself before searching for the next H2.
    # pos=1 would skip only one character; find the first newline to
    # correctly skip the full heading line (avoids off-by-one boundary
    # on back-to-back H2 headings with empty section bodies).
    heading_end = rest.find("\n")
    next_heading_pos = heading_end + 1 if heading_end != -1 else len(rest)
    next_heading_match = _NEXT_H2_HEADING_RE.search(rest, pos=next_heading_pos)
    if next_heading_match is None:
        return rest
    return rest[: next_heading_match.start()]
