"""Story 7.4 — `/bmad-automation init` sample-story scaffold.

Substrate library sibling of :mod:`loud_fail_harness.install_path` (Story
7.2's first Epic-7 runtime-code module) and
:mod:`loud_fail_harness.init_preconditions` (Story 7.3's second). NOT a
sixth substrate component beyond ADR-003 Consequence 1's enumerated five
(envelope_validator, event_validator, reconciler, enumeration_check,
fixture_coverage); the count remains FIVE.

Architectural anchors:

* **FR39** (PRD line 864 verbatim) — "``init`` scaffolds a try-it-now
  sample story at a predictable path
  (``_bmad-output/implementation-artifacts/sample-auto-001.md``), with an
  opt-out flag."
* **FR44 / NFR-P3** (PRD lines 869, 936) — "first-run complete story loop
  on the sample story succeeds in ≤ 5 minutes on a typical developer
  laptop". Story 7.9 exercises THIS sample as the benchmark target; the
  canonical content is deliberately bounded so the loop terminates in
  well under five minutes.
* **PRD line 307 verbatim** — first-impression posture: "Sample story
  scaffolded at ``_bmad-output/implementation-artifacts/sample-auto-001.md``.
  Try it: ``/bmad-automation run sample-auto-001``." The
  :class:`SampleScaffoldOutcome` ``notes`` field carries the same
  affordance.
* **Story 1.10b** (story-doc section-allowlist contract, FR66 / NFR-S5)
  — the canonical content respects the contract: only top-level BMAD
  convention sections (``## Story``, ``## Acceptance Criteria``,
  ``## Tasks / Subtasks``, ``## Dev Agent Record``) plus the
  ``Status:`` line; no specialist-write-scope sections present yet
  (those land at runtime when Dev / Review / QA wrappers populate them).
* **Story 1.11 atomic-vs-aggregated principle** (epics.md lines
  1042-1045) — Story 7.4 introduces ZERO new marker classes. File-system
  errors propagate UNCHANGED per Pattern 5; the orchestrator skill's
  runtime layer (Story 7.6) is the policy boundary that decides whether
  to wrap an error in a marker.
* **Story 2.13 contributor-discipline note**
  (``bmad-autopilot/docs/extension-audit.md`` § "Epic 2 walking-skeleton
  smoke fixture vs. Epic 7 user-facing onboarding sample") — the
  CANONICAL CONTENT here is STRUCTURALLY DISTINCT from
  ``bmad-autopilot/tools/loud-fail-harness/tests/fixtures/sample-story-walking-skeleton.md``:
  different audience, location, lifecycle, AC count, evidence tier,
  exploratory-heuristic applicability. This module's name
  (``sample_story_scaffold``) and the canonical resource path
  (``_data/sample-auto-001.md``) preserve the namespace separation.
* **Story 4.8** (Tier-3 evidence hierarchy) — the canonical content does
  NOT require Tier-3 semantic verification, so first-loop completion
  does not gate on optional tooling (``not_configured`` is the Story 4.8
  default).
* **Story 4.9** (three exploratory heuristics ``empty-state`` /
  ``error-state`` / ``auth-boundary``) — the canonical content's AC-2
  exercises ``empty-state``; AC-3 exercises ``error-state``.
* **Story 7.6** (non-destructive guard, lands later in this epic) —
  OWNS the preserve-on-re-run rule per ``epics.md`` line 3052
  ("sample story (``sample-auto-001.md``) is NOT regenerated if the
  practitioner has it on disk"). Story 7.4's
  :func:`scaffold_sample_story` OVERWRITES an existing file when called
  with ``opt_out=False``; the orchestrator skill at thickening time is
  responsible for invoking the function ONLY when the non-destructive
  guard has cleared the target path.
* **Pattern 6** (architecture.md) — strict typing + dependency injection
  via the typed :class:`SampleScaffoldRequest` Pydantic model; no
  subprocess calls, no network calls, no environment probes; the
  caller-injected ``project_root`` lets tests use ``tmp_path`` and lets
  production wire through the orchestrator skill.

Sensor-not-advisor posture:

    The scaffolder WRITES the canonical content to a caller-supplied
    target path and RETURNS a typed outcome describing what happened.
    It does NOT decide WHETHER to scaffold (the orchestrator skill's
    argument-parsing + Story 7.6's non-destructive guard make that
    decision); it does NOT decide what next; it does NOT register
    markers, touch ``run_state``, or write to ``events.jsonl``.

Loud-fail invariants:

* ``content-resource-missing`` — :func:`load_sample_story_content`
  resolves the canonical content via
  :func:`importlib.resources.files`. If the packaged resource is missing
  (build-time misconfiguration), the underlying ``FileNotFoundError``
  propagates to the caller UNCHANGED per Pattern 5; no sentinel string
  fallback.
* ``filesystem-error-propagates`` — :func:`scaffold_sample_story` does
  NOT catch ``OSError`` / ``PermissionError`` / ``FileNotFoundError``
  from the filesystem write. The caller (orchestrator skill) is the
  policy boundary that may wrap these in a marker; the substrate
  function stays loud per Pattern 5.
* ``no-umbrella-marker`` — Story 7.4 does NOT introduce any marker
  class. The scaffolder NEVER calls
  :func:`loud_fail_harness.marker_wiring.record_marker_with_context`.
"""

from __future__ import annotations

import importlib.resources
import pathlib
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "CANONICAL_CONTENT_RESOURCE",
    "CANONICAL_TARGET_FILENAME",
    "SAMPLE_STORY_TARGET_SUBDIR",
    "SampleScaffoldOutcome",
    "SampleScaffoldRequest",
    "load_sample_story_content",
    "resolve_target_path",
    "scaffold_sample_story",
]


# --------------------------------------------------------------------------- #
# Canonical-path constants (Pattern 6 — values surfaced as named typed        #
# constants so tests assert against the same constants the production code    #
# uses).                                                                       #
# --------------------------------------------------------------------------- #

CANONICAL_CONTENT_RESOURCE: Final[str] = "_data/sample-auto-001.md"
"""Package-relative resource path for the canonical sample-story content.

Resolved via :func:`importlib.resources.files` against the
``loud_fail_harness`` package; the file ships inside the wheel under
``loud_fail_harness/_data/sample-auto-001.md`` per
``[tool.hatch.build.targets.wheel] packages = ["src/loud_fail_harness"]``
in ``pyproject.toml`` (hatch packs every file under the configured
package dir; the existing ``_data/marker_coverage_surfaces.yaml``
precedent confirms inclusion).
"""

SAMPLE_STORY_TARGET_SUBDIR: Final[tuple[str, ...]] = (
    "_bmad-output",
    "implementation-artifacts",
)
"""The canonical sub-path under the practitioner's project root where the
sample story is scaffolded. Mirrors the user-facing sample's documented
location per FR39 verbatim AND per the existing
``_bmad-output/implementation-artifacts/`` convention used by every story
file in the workspace."""

CANONICAL_TARGET_FILENAME: Final[str] = "sample-auto-001.md"
"""The canonical filename of the user-facing sample story (FR39)."""


# --------------------------------------------------------------------------- #
# Typed Pydantic surface (Pattern 6 — strict typing).                          #
# --------------------------------------------------------------------------- #


SampleScaffoldOutcomeKind = Literal["scaffolded", "skipped-opt-out"]
"""The two terminal outcomes of :func:`scaffold_sample_story`.

* ``scaffolded`` — ``opt_out=False``; the canonical content was written
  to the resolved target path; ``bytes_written`` is non-None.
* ``skipped-opt-out`` — ``opt_out=True``; no resource read, no
  filesystem write; ``bytes_written`` is ``None``.
"""


class SampleScaffoldRequest(BaseModel):
    """Typed input to :func:`scaffold_sample_story`.

    Pattern 6 — explicit, named, frozen so the orchestrator skill (or its
    progressive thickening across Stories 7.5 / 7.6 / 7.8) constructs an
    immutable request and the substrate function does not mutate caller
    state.

    Attributes:
        project_root: The practitioner's BMAD project root. The scaffold
            target resolves under this path (``project_root /
            _bmad-output / implementation-artifacts /
            sample-auto-001.md``). REQUIRED — no default; the
            orchestrator skill is responsible for resolving the project
            root before calling this function (likely via
            ``pathlib.Path.cwd()`` or a CLI-injected path). Test code
            injects ``tmp_path``.
        opt_out: Mirrors the parsed boolean of the
            ``--no-sample-story`` flag (FR39). When ``True``, the
            scaffolder short-circuits without reading the canonical
            content or touching the filesystem.
    """

    model_config = ConfigDict(frozen=True)

    project_root: pathlib.Path = Field(
        ...,
        description=(
            "The practitioner's BMAD project root; the scaffold target "
            "resolves under <project_root>/_bmad-output/implementation-"
            "artifacts/sample-auto-001.md."
        ),
    )
    opt_out: bool = Field(
        default=False,
        description=(
            "When True, mirrors `--no-sample-story` and short-circuits "
            "the scaffold without reading the canonical content or "
            "touching the filesystem."
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


class SampleScaffoldOutcome(BaseModel):
    """Typed terminal outcome of :func:`scaffold_sample_story`.

    Frozen so callers can pass the outcome through Pydantic-aware
    boundaries (envelopes, run-state surfaces) without re-validation
    each hop. The ``notes`` field is suitable verbatim for ``init``'s
    output line at orchestrator-skill thickening time.

    Attributes:
        outcome: One of ``"scaffolded"`` | ``"skipped-opt-out"`` per
            :data:`SampleScaffoldOutcomeKind`.
        target_path: Absolute resolved path the function would have
            written to (populated even on the opt-out path so the
            orchestrator skill can name the path for diagnostic clarity).
        bytes_written: UTF-8 byte length of the canonical content
            written to ``target_path`` on the ``scaffolded`` path; ``None``
            on the ``skipped-opt-out`` path.
        notes: One-line human-readable summary suitable for ``init``'s
            output line. Always populated; mirrors PRD line 307's
            first-impression "Try it" affordance on the ``scaffolded``
            path.
    """

    model_config = ConfigDict(frozen=True)

    outcome: SampleScaffoldOutcomeKind
    target_path: pathlib.Path
    bytes_written: int | None
    notes: str


# --------------------------------------------------------------------------- #
# Public API — :func:`load_sample_story_content` + :func:`scaffold_sample_story`. #
# --------------------------------------------------------------------------- #


def load_sample_story_content() -> str:
    """Return the canonical sample-story content as UTF-8 text.

    The content lives at the package-relative resource path
    :data:`CANONICAL_CONTENT_RESOURCE` and is resolved via
    :func:`importlib.resources.files` so the lookup is cwd-independent
    (parallel to :func:`loud_fail_harness.marker_coverage_audit._resolve_surfaces_path`
    at ``marker_coverage_audit.py:706``).

    The function is SIDE-EFFECT-FREE — no filesystem writes, no caching,
    no logging. Repeated calls return BYTE-IDENTICAL strings (the
    underlying ``read_text`` reads the resource each call; if a future
    perf concern justifies caching, lru-cache the function then).

    Returns:
        The canonical content as a single ``str`` decoded explicitly
        with UTF-8 (no platform-default fallback).

    Raises:
        FileNotFoundError: The packaged resource is missing
            (build-time misconfiguration). Pattern 5 — Story 7.4 does
            NOT swallow this into a sentinel string.
        UnicodeDecodeError: The packaged resource is not UTF-8
            (build-time misconfiguration). Pattern 5 — propagates
            UNCHANGED.
    """
    resource = importlib.resources.files("loud_fail_harness").joinpath(
        CANONICAL_CONTENT_RESOURCE
    )
    return resource.read_text(encoding="utf-8")


def resolve_target_path(project_root: pathlib.Path) -> pathlib.Path:
    """Resolve the canonical scaffold target path under ``project_root``.

    The path is::

        <project_root>/_bmad-output/implementation-artifacts/sample-auto-001.md

    Exposed as a public helper so the orchestrator skill (and the
    non-destructive guard at Story 7.6 thickening time) can resolve the
    path WITHOUT calling :func:`scaffold_sample_story` (e.g., to check
    existence before deciding whether to scaffold).

    Args:
        project_root: The practitioner's BMAD project root.

    Returns:
        The resolved target path as ``pathlib.Path``. NOT resolved against
        the filesystem (no ``.resolve()`` call) — the path is preserved
        as the caller passed ``project_root``. The caller is responsible
        for normalization if needed.
    """
    target = project_root
    for segment in SAMPLE_STORY_TARGET_SUBDIR:
        target = target / segment
    return target / CANONICAL_TARGET_FILENAME


def scaffold_sample_story(request: SampleScaffoldRequest) -> SampleScaffoldOutcome:
    """Write the canonical sample story to the resolved target path.

    Single public orchestration entry point per AC-4. Composes
    :func:`resolve_target_path` + :func:`load_sample_story_content` +
    :meth:`pathlib.Path.write_text`. Pure orchestration — no marker
    registration, no ``run_state`` mutation, no event-log writes; only
    the filesystem write under ``request.project_root``.

    The two terminal paths:

    * ``request.opt_out is False`` — the function ensures the parent
      directories exist (``mkdir(parents=True, exist_ok=True)``), loads
      the canonical content, writes it with explicit UTF-8 encoding,
      and returns ``outcome="scaffolded"`` carrying the byte-length and
      a "Try it" notes line.
    * ``request.opt_out is True`` — the function does NOT read the
      canonical content, does NOT call ``mkdir``, does NOT write the
      file. Returns ``outcome="skipped-opt-out"`` with ``bytes_written=None``
      and an informative notes line naming both the
      ``--no-sample-story`` flag and the resolved target path so the
      orchestrator skill can surface a useful output line.

    Idempotency posture (per AC-6): when called with ``opt_out=False``,
    the function OVERWRITES an existing file at the target path. The
    "preserve on re-run" rule from ``epics.md`` line 3052 is OWNED by
    Story 7.6's non-destructive guard; the orchestrator skill at
    thickening time invokes this function ONLY when the guard has
    cleared the target.

    Args:
        request: The typed input. ``project_root`` is REQUIRED;
            ``opt_out`` defaults to ``False``.

    Returns:
        :class:`SampleScaffoldOutcome` with ``outcome``,
        ``target_path``, ``bytes_written``, and a ``notes`` line
        suitable for ``init``'s output.

    Raises:
        OSError: A filesystem write error (target directory is
            read-only, parent path is a regular file not a directory,
            disk full, etc.). Pattern 5 — Story 7.4 does NOT swallow
            filesystem errors into a sentinel outcome.
        PermissionError: A subclass of ``OSError`` raised when the
            target directory cannot be written. Propagates UNCHANGED.
        FileNotFoundError: Raised by :func:`load_sample_story_content`
            if the packaged resource is missing. Propagates UNCHANGED.
    """
    target_path = resolve_target_path(request.project_root)

    if request.opt_out:
        notes = (
            f"Sample story scaffold skipped (--no-sample-story). The user-"
            f"facing sample would have been written at {target_path}; re-run "
            "/bmad-automation init without the flag to opt back in."
        )
        return SampleScaffoldOutcome(
            outcome="skipped-opt-out",
            target_path=target_path,
            bytes_written=None,
            notes=notes,
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    content = load_sample_story_content()
    target_path.write_text(content, encoding="utf-8")
    notes = (
        f"Sample story scaffolded at {target_path}. Try it: "
        "`/bmad-automation run sample-auto-001`"
    )
    return SampleScaffoldOutcome(
        outcome="scaffolded",
        target_path=target_path,
        bytes_written=len(content.encode("utf-8")),
        notes=notes,
    )
