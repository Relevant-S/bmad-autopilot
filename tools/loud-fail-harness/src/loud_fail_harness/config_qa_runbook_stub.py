"""Story 7.5 — `/bmad-automation init` config + qa-runbook stub generator.

Substrate library sibling of :mod:`loud_fail_harness.install_path` (Story
7.2's first Epic-7 runtime-code module),
:mod:`loud_fail_harness.init_preconditions` (Story 7.3), and
:mod:`loud_fail_harness.sample_story_scaffold` (Story 7.4). NOT a sixth
substrate component beyond ADR-003 Consequence 1's enumerated five
(envelope_validator, event_validator, reconciler, enumeration_check,
fixture_coverage); the count remains FIVE.

Architectural anchors:

* **FR40** (PRD line 865 verbatim) — "``init`` writes documented default
  ``_bmad/automation/config.yaml`` and ``_bmad/automation/qa-runbook.yaml``
  stubs with comments pointing to opt-in feature enablement".
* **architecture.md lines 1167-1168 + 1218** — the user-facing config +
  qa-runbook artifact paths (``_bmad/automation/config.yaml`` and
  ``_bmad/automation/qa-runbook.yaml``) live under the practitioner's
  BMAD project (View 3); ``init`` scaffolds them from packaged templates
  shipped under :mod:`loud_fail_harness` (View 2).
* **epics.md lines 3015-3023** — the canonical-defaults manifest:
  ``retry_budget`` (FR8), ``specialist_timeout_minutes`` (NFR-P2),
  ``cost_ceiling_per_story`` (NFR-P1), ``evidence_max_size_mb`` (NFR-P6),
  ``story_doc_version_tolerance_window`` (Story 7.7);
  ``masked_selectors`` (Story 4.12), Tier-3 semantic verification
  (Story 4.8), per-story Behavioral Plan overrides (Story 4.1).
* **Story 1.11 atomic-vs-aggregated principle** (epics.md lines
  1042-1045) — Story 7.5 introduces ZERO new marker classes. File-system
  errors propagate UNCHANGED per Pattern 5; the orchestrator skill's
  runtime layer (Story 7.6) is the policy boundary that decides whether
  to wrap an error in a marker (e.g., ``init-would-destroy-existing-
  artifact`` is Story 7.6's surface).
* **Story 7.6** (non-destructive guard, lands later in this epic) —
  OWNS the preserve-on-re-run rule per ``epics.md`` line 3050 ("existing
  ``_bmad/automation/config.yaml`` and ``_bmad/automation/qa-runbook.yaml``
  are preserved as-is") AND the additive-merge rule per ``epics.md``
  line 3051. Story 7.5's :func:`scaffold_config_qa_runbook_stubs`
  OVERWRITES existing files at the resolved target paths; the
  orchestrator skill at thickening time is responsible for invoking
  this function ONLY when the non-destructive guard has cleared the
  target paths OR ``--overwrite-confirmed`` was passed.
* **Pattern 6** (architecture.md) — strict typing + dependency injection
  via the typed :class:`StubScaffoldRequest` Pydantic model; no
  subprocess calls, no network calls, no environment probes; the
  caller-injected ``project_root`` lets tests use ``tmp_path`` and
  lets production wire through the orchestrator skill at thickening time.

Why packaged data + ``importlib.resources`` (not string constants):

* **Editability** — YAML files render in IDEs and on GitHub; a Python
  triple-quoted string does not. Practitioners (or future maintainers
  refining the defaults) MUST be able to read / diff / preview the
  canonical defaults as YAML.
* **Shape validation in tests** — Tests use ``yaml.safe_load(canonical_
  content)`` and assert structural properties.
* **Established codebase pattern** — ``sample_story_scaffold.py:276-279``
  (Story 7.4) and ``marker_coverage_audit.py:706`` already establish
  ``importlib.resources.files("loud_fail_harness").joinpath(...)`` as
  the canonical packaged-data access pattern. Story 7.5 follows the
  same shape byte-for-byte.

Why two stub-write functions in ONE call (not two separate scaffolds):

* The two stubs share a parent directory (``_bmad/automation/``); two
  separate ``mkdir`` calls would be wasteful and double the test surface.
* The orchestrator skill at thickening time invokes them as a single
  unit per FR40 verbatim ("init writes documented default
  ``_bmad/automation/config.yaml`` AND ``_bmad/automation/qa-runbook.yaml``
  stubs").
* Story 7.6's non-destructive guard treats them as a unit per
  ``epics.md`` line 3050 — the guard fires when EITHER would be
  overwritten.

:func:`load_config_template` and :func:`load_qa_runbook_template` ARE
separate so the test suite can exercise each shape independently AND
so future readers can read either canonical default without
instantiating a request.

Sensor-not-advisor posture:

    The scaffolder WRITES the canonical content to caller-supplied
    target paths and RETURNS a typed outcome describing what happened.
    It does NOT decide WHETHER to scaffold (the orchestrator skill's
    argument-parsing + Story 7.6's non-destructive guard make that
    decision); it does NOT decide what next; it does NOT register
    markers, touch ``run_state``, or write to ``events.jsonl``.

Loud-fail invariants:

* ``content-resource-missing`` — :func:`load_config_template` and
  :func:`load_qa_runbook_template` resolve the canonical content via
  :func:`importlib.resources.files`. If the packaged resource is
  missing (build-time misconfiguration), the underlying
  ``FileNotFoundError`` propagates to the caller UNCHANGED per
  Pattern 5; no sentinel string fallback.
* ``filesystem-error-propagates`` — :func:`scaffold_config_qa_runbook_stubs`
  does NOT catch ``OSError`` / ``PermissionError`` / ``FileNotFoundError``
  from the filesystem write. Partial-write recovery (config written,
  qa-runbook write fails) is loud-fail-by-design; the orchestrator
  skill at thickening time (Story 7.6) is the cleanup-policy boundary.
* ``no-umbrella-marker`` — Story 7.5 does NOT introduce any marker
  class. The scaffolder NEVER calls
  :func:`loud_fail_harness.marker_wiring.record_marker_with_context`.
  The deliberate import below (with ``# noqa`` to silence "unused")
  surfaces the symbol in this module's namespace solely so the test
  suite can patch ``loud_fail_harness.config_qa_runbook_stub.record_marker_with_context``
  and assert non-invocation — the consuming-module patch-target
  discipline established by Story 7.4's deferred-review fix.
"""

from __future__ import annotations

import importlib.resources
import pathlib
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from loud_fail_harness.marker_wiring import (  # noqa: F401
    record_marker_with_context,
)

__all__ = [
    "CONFIG_TARGET_FILENAME",
    "CONFIG_TEMPLATE_RESOURCE",
    "QA_RUNBOOK_TARGET_FILENAME",
    "QA_RUNBOOK_TEMPLATE_RESOURCE",
    "STUB_TARGET_SUBDIR",
    "StubScaffoldOutcome",
    "StubScaffoldOutcomeKind",
    "StubScaffoldRequest",
    "load_config_template",
    "load_qa_runbook_template",
    "resolve_config_path",
    "resolve_qa_runbook_path",
    "scaffold_config_qa_runbook_stubs",
]


# --------------------------------------------------------------------------- #
# Canonical-path constants (Pattern 6 — values surfaced as named typed        #
# constants so tests assert against the same constants the production code    #
# uses).                                                                       #
# --------------------------------------------------------------------------- #

CONFIG_TEMPLATE_RESOURCE: Final[str] = "_data/config.yaml.template"
"""Package-relative resource path for the canonical config stub content."""

QA_RUNBOOK_TEMPLATE_RESOURCE: Final[str] = "_data/qa-runbook.yaml.template"
"""Package-relative resource path for the canonical qa-runbook stub content."""

CONFIG_TARGET_FILENAME: Final[str] = "config.yaml"
"""The canonical filename of the user-facing config artifact (FR40)."""

QA_RUNBOOK_TARGET_FILENAME: Final[str] = "qa-runbook.yaml"
"""The canonical filename of the user-facing qa-runbook artifact (FR40)."""

STUB_TARGET_SUBDIR: Final[tuple[str, str]] = ("_bmad", "automation")
"""The canonical sub-path under the practitioner's project root where both
stub files are scaffolded. Mirrors the architecture.md lines 1167-1168
verbatim ``_bmad/automation/`` convention. Fixed-arity ``tuple[str, str]``
per Story 7.4's deferred-review fix to the ``tuple[str, ...]`` shape."""


# --------------------------------------------------------------------------- #
# Typed Pydantic surface (Pattern 6 — strict typing).                          #
# --------------------------------------------------------------------------- #


StubScaffoldOutcomeKind = Literal["scaffolded"]
"""The single terminal outcome of :func:`scaffold_config_qa_runbook_stubs`
at MVP. Future opt-outs (if any) are additive enum members per the
established widening pattern; Story 7.5 has no opt-out flag per the epic
(the orchestrator skill at thickening time is the policy boundary that
decides WHETHER to scaffold)."""


class StubScaffoldRequest(BaseModel):
    """Typed input to :func:`scaffold_config_qa_runbook_stubs`.

    Pattern 6 — explicit, named, frozen so the orchestrator skill (or
    its progressive thickening across Stories 7.6 / 7.8) constructs an
    immutable request and the substrate function does not mutate caller
    state.

    Attributes:
        project_root: The practitioner's BMAD project root. The two
            scaffold targets resolve under this path
            (``project_root / _bmad / automation / config.yaml`` and
            ``project_root / _bmad / automation / qa-runbook.yaml``).
            REQUIRED — no default; the orchestrator skill is responsible
            for resolving the project root before calling this function
            (likely via ``pathlib.Path.cwd()`` or a CLI-injected path).
            Test code injects ``tmp_path``.
    """

    model_config = ConfigDict(frozen=True)

    project_root: pathlib.Path = Field(
        ...,
        description=(
            "The practitioner's BMAD project root; the two scaffold "
            "targets resolve under <project_root>/_bmad/automation/."
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


class StubScaffoldOutcome(BaseModel):
    """Typed terminal outcome of :func:`scaffold_config_qa_runbook_stubs`.

    Frozen so callers can pass the outcome through Pydantic-aware
    boundaries without re-validation each hop. The ``notes`` field is
    suitable verbatim for ``init``'s output line at orchestrator-skill
    thickening time.

    Attributes:
        outcome: ``"scaffolded"`` per :data:`StubScaffoldOutcomeKind`.
        config_target_path: Absolute resolved path of the config stub
            written under ``project_root``.
        qa_runbook_target_path: Absolute resolved path of the qa-runbook
            stub written under ``project_root``.
        config_bytes_written: UTF-8 byte length of the config canonical
            content written to ``config_target_path``.
        qa_runbook_bytes_written: UTF-8 byte length of the qa-runbook
            canonical content written to ``qa_runbook_target_path``.
        notes: One-line human-readable summary suitable for ``init``'s
            output line; names BOTH paths per the FR40 verbatim posture.
    """

    model_config = ConfigDict(frozen=True)

    outcome: StubScaffoldOutcomeKind
    config_target_path: pathlib.Path
    qa_runbook_target_path: pathlib.Path
    config_bytes_written: int
    qa_runbook_bytes_written: int
    notes: str


# --------------------------------------------------------------------------- #
# Public API — canonical content loaders + path resolvers + scaffold orch.    #
# --------------------------------------------------------------------------- #


def load_config_template() -> str:
    """Return the canonical config-stub content as UTF-8 text.

    The content lives at the package-relative resource path
    :data:`CONFIG_TEMPLATE_RESOURCE` and is resolved via
    :func:`importlib.resources.files` so the lookup is cwd-independent
    (parallel to :func:`loud_fail_harness.sample_story_scaffold.load_sample_story_content`
    at ``sample_story_scaffold.py:276-279``).

    The function is SIDE-EFFECT-FREE — no filesystem writes, no caching,
    no logging. Repeated calls return BYTE-IDENTICAL strings.

    Returns:
        The canonical content as a single ``str`` decoded explicitly
        with UTF-8 (no platform-default fallback).

    Raises:
        FileNotFoundError: The packaged resource is missing
            (build-time misconfiguration). Pattern 5 — Story 7.5 does
            NOT swallow this into a sentinel string.
        UnicodeDecodeError: The packaged resource is not UTF-8
            (build-time misconfiguration). Pattern 5 — propagates
            UNCHANGED.
    """
    resource = importlib.resources.files("loud_fail_harness").joinpath(
        CONFIG_TEMPLATE_RESOURCE
    )
    return resource.read_text(encoding="utf-8")


def load_qa_runbook_template() -> str:
    """Return the canonical qa-runbook-stub content as UTF-8 text.

    Same posture as :func:`load_config_template`; resolves the
    qa-runbook canonical content via :data:`QA_RUNBOOK_TEMPLATE_RESOURCE`.

    Returns:
        The canonical content as a single ``str`` decoded explicitly
        with UTF-8.

    Raises:
        FileNotFoundError: The packaged resource is missing.
        UnicodeDecodeError: The packaged resource is not UTF-8.
    """
    resource = importlib.resources.files("loud_fail_harness").joinpath(
        QA_RUNBOOK_TEMPLATE_RESOURCE
    )
    return resource.read_text(encoding="utf-8")


def resolve_config_path(project_root: pathlib.Path) -> pathlib.Path:
    """Resolve the canonical config-stub target path under ``project_root``.

    The path is::

        <project_root>/_bmad/automation/config.yaml

    Exposed as a public helper so the orchestrator skill (and Story 7.6's
    non-destructive guard at thickening time) can resolve the path
    WITHOUT calling :func:`scaffold_config_qa_runbook_stubs` (e.g., to
    check existence before deciding whether to scaffold).

    Args:
        project_root: The practitioner's BMAD project root.

    Returns:
        The resolved target path as ``pathlib.Path``. Pure path-arithmetic
        helper — does NOT call ``.resolve()``, does NOT touch the
        filesystem, does NOT raise on a non-existent ``project_root``.
    """
    target = project_root
    for segment in STUB_TARGET_SUBDIR:
        target = target / segment
    return target / CONFIG_TARGET_FILENAME


def resolve_qa_runbook_path(project_root: pathlib.Path) -> pathlib.Path:
    """Resolve the canonical qa-runbook-stub target path under ``project_root``.

    The path is::

        <project_root>/_bmad/automation/qa-runbook.yaml

    Same posture as :func:`resolve_config_path` — pure path-arithmetic.

    Args:
        project_root: The practitioner's BMAD project root.

    Returns:
        The resolved target path as ``pathlib.Path``.
    """
    target = project_root
    for segment in STUB_TARGET_SUBDIR:
        target = target / segment
    return target / QA_RUNBOOK_TARGET_FILENAME


def scaffold_config_qa_runbook_stubs(
    request: StubScaffoldRequest,
) -> StubScaffoldOutcome:
    """Write BOTH canonical stubs to their resolved target paths.

    Single public orchestration entry point per AC-4. Composes
    :func:`resolve_config_path` + :func:`resolve_qa_runbook_path` +
    :func:`load_config_template` + :func:`load_qa_runbook_template` +
    :meth:`pathlib.Path.write_text`. Pure orchestration — no marker
    registration, no ``run_state`` mutation, no event-log writes; only
    the filesystem writes under ``request.project_root``.

    Write order is deterministic: config FIRST, qa-runbook SECOND. This
    makes partial-write inspection in tests well-defined: if the config
    write succeeds and the qa-runbook write raises, the on-disk state
    has the config file present and the qa-runbook absent.

    Idempotency posture (per AC-4): the function OVERWRITES existing
    files at the target paths. The "preserve on re-run" rule from
    ``epics.md`` line 3050 AND the additive-merge rule from line 3051
    are OWNED by Story 7.6's non-destructive guard; the orchestrator
    skill at thickening time invokes this function ONLY when the guard
    has cleared the target paths OR ``--overwrite-confirmed`` was
    passed.

    Args:
        request: The typed input. ``project_root`` is REQUIRED.

    Returns:
        :class:`StubScaffoldOutcome` with ``outcome="scaffolded"``,
        both resolved target paths, both UTF-8 byte lengths, and a
        ``notes`` line suitable for ``init``'s output.

    Raises:
        OSError: A filesystem write error (target directory is
            read-only, parent path is a regular file not a directory,
            disk full, etc.). Pattern 5 — Story 7.5 does NOT swallow
            filesystem errors into a sentinel outcome.
        PermissionError: A subclass of ``OSError`` raised when the
            target directory cannot be written. Propagates UNCHANGED.
        FileNotFoundError: Raised by :func:`load_config_template` or
            :func:`load_qa_runbook_template` if the corresponding
            packaged resource is missing. Propagates UNCHANGED.
    """
    config_target_path = resolve_config_path(request.project_root)
    qa_runbook_target_path = resolve_qa_runbook_path(request.project_root)

    # Both stubs share the parent directory; one mkdir covers both.
    config_target_path.parent.mkdir(parents=True, exist_ok=True)

    config_content = load_config_template()
    qa_runbook_content = load_qa_runbook_template()

    config_target_path.write_text(config_content, encoding="utf-8")
    qa_runbook_target_path.write_text(qa_runbook_content, encoding="utf-8")

    notes = (
        f"Config + qa-runbook stubs scaffolded at {config_target_path} "
        f"and {qa_runbook_target_path}. Edit defaults per `# Source:` "
        "cross-references; opt-in features documented under "
        "`# Worked example`."
    )
    return StubScaffoldOutcome(
        outcome="scaffolded",
        config_target_path=config_target_path,
        qa_runbook_target_path=qa_runbook_target_path,
        config_bytes_written=len(config_content.encode("utf-8")),
        qa_runbook_bytes_written=len(qa_runbook_content.encode("utf-8")),
        notes=notes,
    )
