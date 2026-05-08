"""Story 7.3 — ``/bmad-automation init`` precondition orchestration.

Substrate library sibling of :mod:`loud_fail_harness.install_path` (Story
7.2's first Epic-7 runtime-code module). NOT a sixth substrate component
beyond ADR-003 Consequence 1's enumerated five (envelope_validator,
event_validator, reconciler, enumeration_check, fixture_coverage); the
count remains FIVE.

Architectural anchors:

* **FR37** (PRD line 862 verbatim) — "``/bmad-automation init`` performs
  precondition checks (TEA module presence, Playwright MCP reachability,
  git state, Claude Code version, BMAD core version) and emits
  named-invariant diagnostics with specific fixes on any failure."
* **FR38** (PRD line 863 verbatim) — "``init`` blocks installation until
  hard-dependency preconditions (e.g., TEA module) are met, with
  actionable guidance for resolution."
* **NFR-O5** (PRD line 984 verbatim) — "every failure surface … produces
  a diagnostic with the failed invariant's name and a specific
  remediation pointer. Generic error messages are forbidden."
* **Story 1.11 atomic-vs-aggregated principle** (epics.md lines 1042-1045
  verbatim) — Markers represent atomic failure surfaces, not aggregated
  conditions. Epic 7 ``init`` precondition checks ARE NOT aggregated
  under a hypothetical ``init-precondition-failed`` umbrella; each
  underlying failure (TEA missing, Playwright MCP unavailable, BMAD core
  wrong version) maps to existing markers (``env-setup-failed``,
  ``playwright-mcp-unavailable``). The diagnostic layer aggregates per
  NFR-O5; the marker taxonomy stays atomic.
* **Epic 7 preamble** (epics.md line 2847 verbatim) — "**Not added**
  (per atomic-vs-aggregated principle): ``init-precondition-failed`` —
  composed of existing markers; init's diagnostic layer aggregates per
  NFR-O5."
* **Story 6.1 single-source-of-truth** (epics.md line 2962 verbatim) —
  "the diagnostic format is consistent with Story 6.1's loud-fail block
  shape so practitioners reading either get the same mental model." The
  init aggregator delegates per-marker-entry rendering to
  :func:`loud_fail_harness.bundle_assembly._render_marker_entry_body`
  (path (b) per Story 7.3 AC-6) so a future taxonomy bump or
  pointer-text edit propagates to BOTH the bundle's loud-fail block AND
  ``init``'s diagnostic without drift.
* **SDN-001** (architecture.md lines 608-763) — Dependency failure-profile
  schema. Source-of-truth manifest at ``schemas/dependencies.yaml``;
  parsed via :func:`loud_fail_harness.dependencies_validator.load_dependencies`
  (Story 1.6's seam contract).
* **Architecture line 734 verbatim** — "``total-block`` halts init with
  the named diagnostic; ``graceful-degrade`` emits the named marker but
  proceeds; ``opt-in-skip`` stays silent unless a
  ``configured-but-missing`` sub-classification fires."
* **Pattern 6** (architecture.md) — strict typing + dependency injection.
  Probe callables are INJECTED via :class:`PreconditionProbeRegistry` so
  production probes (subprocess ``claude --version``, file-system reads
  for ``_bmad/_config/manifest.yaml``, network reachability) are mocked
  in tests without monkey-patching.

Sensor-not-advisor posture:

    The dispatcher RECORDS markers and BUILDS a :class:`PreconditionRun`
    aggregating the per-dependency outcomes. It does NOT decide WHAT to
    do next; the orchestrator skill (or its progressive thickening in
    Stories 7.4 / 7.5 / 7.6 / 7.8) is the policy layer that interprets
    ``halted=True`` and surfaces the diagnostic to the practitioner.

Loud-fail invariants:

* ``unknown-marker-class`` — :func:`run_init_preconditions` validates
  every recorded marker class against the
  :class:`MarkerClassRegistry`; an unknown class raises
  :exc:`UnknownMarkerClass` per Pattern 5 (no silent fallback to a
  generic class).
* ``no-umbrella-marker`` — the aggregator NEVER emits
  ``init-precondition-failed`` per Story 1.11. The marker taxonomy is
  NOT extended with an umbrella class; the aggregator is a string
  diagnostic, not a marker registration.
* ``schema-violation-propagates`` — :func:`load_dependencies` raises
  :exc:`RuntimeError` on SDN-001 shape violations; this module does NOT
  swallow that exception into a precondition diagnostic. The contract
  failure surfaces to the caller unchanged per Pattern 5 + the
  harness's exit-code matrix.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable, Mapping
from typing import Any, Literal

from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness.bundle_assembly import (
    _load_marker_taxonomy_entries,
    _render_marker_entry_body,
)
from loud_fail_harness.exceptions import MarkerContextMissing
from loud_fail_harness.dependencies_validator import load_dependencies
from loud_fail_harness.marker_wiring import record_marker_with_context
from loud_fail_harness.run_state import RunState
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)

__all__ = [
    "PreconditionProbeResult",
    "PreconditionResult",
    "PreconditionRun",
    "PreconditionProbeRegistry",
    "ProjectType",
    "run_init_preconditions",
    "format_init_diagnostic",
]


ProjectType = Literal["web", "api", "mobile"]
"""The three canonical project-type identifiers per Story 4.4 / 4.5 +
SDN-001's ``by_project_type`` schema."""

PreconditionOutcome = Literal["pass", "halt", "warn", "silent"]
"""The four per-dependency outcome states. ``pass`` = probe succeeded;
``halt`` = total-block probe failed (run halts); ``warn`` =
graceful-degrade probe failed OR opt-in-skip with a registered marker;
``silent`` = opt-in-skip dependency unconfigured / not applicable."""


_INIT_DIAGNOSTIC_HEADER: str = (
    "## Init Precondition Check — Named-Invariant Diagnostic"
)
"""H2 header for the aggregated ``init`` diagnostic per AC-5. The
``## `` H2 prefix matches Story 6.1's loud-fail block H2 shape so
practitioners reading either get the same mental model (AC-6)."""

_INIT_ALL_PRECONDITIONS_MET_SENTINEL: str = (
    "## Init Precondition Check — All Preconditions Met\n"
)
"""Empty-case sentinel per AC-5 — mirrors Story 6.1's
``## ✓ Loud-Fail Markers — None`` posture: the H2 is rendered even when
no preconditions failed so downstream tooling can rely on a deterministic
structural anchor."""


# --------------------------------------------------------------------------- #
# Typed Pydantic models (Pattern 6)                                           #
# --------------------------------------------------------------------------- #


class PreconditionProbeResult(BaseModel):
    """Result of probing a single declared dependency's environment.

    Returned by an injected probe callable in
    :class:`PreconditionProbeRegistry`. Populated by the orchestrator
    skill's runtime-thickening probes (Stories 7.4 / 7.5 / 7.6 / 7.8);
    fixture-instantiated by the test suite to exercise every dispatch
    branch without subprocess / file-system / network access.

    Pattern 6: strict typing. Frozen for hashability + state-update
    discipline.

    Fields:
        available: Whether the probed dependency is installed /
            reachable. ``False`` is the sole signal that disambiguates
            "missing" from "wrong version" (the latter is signalled by
            ``available=True`` + ``version_observed`` below the floor).
        version_observed: The version string the probe observed (e.g.,
            ``"2.1.32"`` from ``claude --version`` parsing). ``None``
            when version-agnostic OR when the probe did NOT capture a
            version. Compared to the dependency entry's ``version_floor``
            via :class:`packaging.version.Version` IFF the floor is a
            parseable semver string; free-text floors (e.g.,
            ``"version-agnostic; detected at init"``) skip the
            comparison and treat ``available=True`` as success.
        sub_classification: For opt-in-skip dependencies (LAD), the
            condition string that matched (e.g.,
            ``"configured-but-api-key-missing"`` per
            ``dependencies.yaml`` lines 156-159). The dispatcher walks
            the entry's ``sub_classifications:`` list to find the
            matching condition and routes to its ``emits_marker`` /
            ``silent`` branch.
        evidence: Optional human-readable evidence string (e.g., the raw
            ``claude --version`` stdout) for diagnostic enrichment. NOT
            currently surfaced in the aggregated diagnostic; reserved
            for Stories 7.4-7.8 if the orchestrator-skill thickening
            wants to expose probe evidence in the user-facing message.
    """

    model_config = ConfigDict(frozen=True)

    available: bool
    version_observed: str | None = None
    sub_classification: str | None = None
    evidence: str | None = None


class PreconditionResult(BaseModel):
    """Per-dependency outcome of one ``init`` precondition probe pass.

    Aggregated into :class:`PreconditionRun.results` in declaration
    order (the order entries appear in ``dependencies.yaml``). Distinct
    from :class:`PreconditionProbeResult` (the raw probe return value);
    this is the dispatcher's processed verdict carrying marker-routing
    metadata.

    Pattern 6: strict typing. Frozen.

    Fields:
        dependency: The dependency identifier (e.g., ``"claude-code"``,
            ``"playwright-mcp"``). Sourced from the parsed
            ``dependencies.yaml`` mapping key.
        outcome: One of ``"pass"`` / ``"halt"`` / ``"warn"`` /
            ``"silent"`` per the dispatch logic in
            :func:`run_init_preconditions`.
        marker_class: The base marker class registered for this
            dependency's failure (e.g., ``"env-setup-failed"``). ``None``
            when ``outcome`` is ``"pass"`` or ``"silent"``.
        sub_classification: The marker sub-classification suffix
            (Pattern 2) for this dependency's failure (e.g.,
            ``"tea-module-missing"``). ``None`` when no sub-classification
            applies (e.g., the ``playwright-mcp-unavailable`` entry has
            ``sub_classifications: []`` in the taxonomy).
        diagnostic_text: The fully-resolved diagnostic-pointer text per
            the marker taxonomy (Story 6.2 actionable interpolation).
            Currently unused by :func:`format_init_diagnostic` (the
            renderer re-derives it from the taxonomy via
            :func:`_render_marker_entry_body` so the single-source-of-
            truth invariant holds); reserved for downstream stories
            that may want a flattened result structure.
        dependency_diagnostic: The dependency entry's ``diagnostic``
            field verbatim from ``dependencies.yaml`` (e.g., ``"TEA
            module not installed. Run `/bmad:install tea` and re-run
            `/bmad-automation init`."``). Surfaces in the aggregated
            diagnostic's ``Per-dependency remediation`` bullet per
            AC-5. ``None`` when the dependency entry does not declare a
            ``diagnostic`` field for the init phase (e.g., LAD
            opt-in-skip entries).
    """

    model_config = ConfigDict(frozen=True)

    dependency: str = Field(min_length=1)
    outcome: PreconditionOutcome
    marker_class: str | None = None
    sub_classification: str | None = None
    diagnostic_text: str | None = None
    dependency_diagnostic: str | None = None


class PreconditionRun(BaseModel):
    """Aggregated outcome of one ``init`` precondition orchestration pass.

    Returned by :func:`run_init_preconditions`. Consumed by
    :func:`format_init_diagnostic` AND by the orchestrator skill (or
    its Stories 7.4-7.8 thickening) to decide whether to halt the
    ``init`` flow.

    The run does NOT short-circuit on the FIRST total-block failure —
    every dependency probe runs so the aggregated diagnostic shows ALL
    failed deps in one pass per AC-3 ("Do not bail after first finding"
    discipline established by ``dependencies_validator.py:46-51``).

    Pattern 6: strict typing. Frozen.

    Fields:
        halted: ``True`` IFF at least one ``PreconditionResult`` has
            ``outcome == "halt"``. The orchestrator skill MUST treat
            this flag as the authoritative halt signal; ``init`` does
            NOT proceed to scaffold (Story 7.4) or config-stub
            generation (Story 7.5) when ``halted=True``.
        results: Tuple of per-dependency results in DECLARATION ORDER
            (the order entries appear in ``dependencies.yaml``, NOT
            alphabetically) per AC-2 + the file's header comment lines
            62-65 verbatim — "Canonical entry order (preserve verbatim
            — re-ordering loses architectural narrative semantics)".
        run_state: The post-dispatch :class:`RunState` carrying every
            registered marker in ``active_markers`` and every populated
            ``marker_contexts`` entry. ``None`` when the caller did not
            supply a starting :class:`RunState` (test isolation /
            diagnostic-only mode).
    """

    model_config = ConfigDict(frozen=True)

    halted: bool
    results: tuple[PreconditionResult, ...]
    run_state: RunState | None = None


PreconditionProbe = Callable[[], PreconditionProbeResult]
"""Type alias for an injected per-dependency probe callable.

Each probe takes zero arguments and returns a
:class:`PreconditionProbeResult` describing the dependency's
environment state. The orchestrator-skill thickening in Stories 7.4-7.8
constructs production probes (subprocess wrappers, file-system reads,
network calls) and passes them to :func:`run_init_preconditions` via
:class:`PreconditionProbeRegistry`. The test suite injects fixture
probes returning canned results.
"""


class PreconditionProbeRegistry(BaseModel):
    """Injected per-dependency probe registry (Pattern 6).

    Pattern 6 — strict typing + dependency injection. Each probe is a
    callable returning a typed :class:`PreconditionProbeResult`; mypy
    catches probe-signature drift at CI time. Production probes are
    instantiated by the orchestrator skill's Stories 7.4-7.8 thickening;
    test probes are instantiated per :class:`PreconditionProbeResult`
    fixture in :mod:`tests.test_init_preconditions`.

    The registry's field set covers every top-level dependency
    identifier currently declared in ``dependencies.yaml``
    (``claude-code``, ``bmad-core``, ``tea-module``, ``playwright-mcp``,
    ``mobile-mcp``, ``lad``). When ``dependencies.yaml`` adds a new
    dependency in a future MINOR-bump, this registry's field set is
    extended additively (with a corresponding migration in the
    orchestrator skill's probe instantiation).

    All fields are required so the test suite cannot accidentally
    forget a dependency probe; the dispatcher fails loudly on a
    missing-probe access via the standard
    :exc:`pydantic.ValidationError` path.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    claude_code: PreconditionProbe
    bmad_core: PreconditionProbe
    tea_module: PreconditionProbe
    playwright_mcp: PreconditionProbe
    mobile_mcp: PreconditionProbe
    lad: PreconditionProbe

    def probe_for(self, dependency: str) -> PreconditionProbe | None:
        """Return the probe callable for ``dependency`` or ``None``.

        Maps the kebab-case ``dependencies.yaml`` identifier (e.g.,
        ``"claude-code"``) to the snake_case Pydantic field (e.g.,
        ``claude_code``). Returns ``None`` for unrecognised
        dependencies — the dispatcher treats this as a SKIP (no probe
        runs; outcome is ``"silent"``) so a future ``dependencies.yaml``
        addition does not crash the orchestrator until the registry
        catches up.
        """
        attr_name = dependency.replace("-", "_")
        probe = getattr(self, attr_name, None)
        if probe is None or not callable(probe):
            return None
        return probe  # type: ignore[no-any-return]


# --------------------------------------------------------------------------- #
# Profile resolution                                                          #
# --------------------------------------------------------------------------- #


def _resolve_init_profile(
    entry: Mapping[str, Any],
    project_type: ProjectType,
) -> Mapping[str, Any] | None:
    """Resolve the ``init`` lifecycle profile for one dependency entry.

    Walks the SDN-001 shape (architecture.md lines 624-730):

    1. Top-level ``profiles.init`` (e.g., ``claude-code``,
       ``bmad-core``, ``tea-module``, ``lad``).
    2. ``by_project_type[<project_type>].profiles.init`` (e.g.,
       ``playwright-mcp``, ``mobile-mcp``).
    3. Returns ``None`` if neither applies (defensive against future
       SDN-001 extensions adding additional discriminators).

    Args:
        entry: One dependency entry's parsed mapping.
        project_type: The project-type discriminator passed to
            :func:`run_init_preconditions`.

    Returns:
        The init profile mapping (with ``profile``, ``diagnostic``,
        ``marker_class``, ``sub_classification``, etc. as applicable),
        or ``None`` if no init lifecycle phase is declared for this
        entry under the resolved discriminator.
    """
    top_level_profiles = entry.get("profiles")
    if isinstance(top_level_profiles, Mapping):
        init_profile = top_level_profiles.get("init")
        if isinstance(init_profile, Mapping):
            return init_profile

    by_project_type = entry.get("by_project_type")
    if isinstance(by_project_type, Mapping):
        project_entry = by_project_type.get(project_type)
        if isinstance(project_entry, Mapping):
            project_profiles = project_entry.get("profiles")
            if isinstance(project_profiles, Mapping):
                init_profile = project_profiles.get("init")
                if isinstance(init_profile, Mapping):
                    return init_profile

    return None


# --------------------------------------------------------------------------- #
# Version comparison                                                          #
# --------------------------------------------------------------------------- #


def _version_below_floor(observed: str | None, floor: str | None) -> bool:
    """Return ``True`` IFF a numeric ``observed`` is below a numeric ``floor``.

    Uses :class:`packaging.version.Version` for comparison. Free-text
    floors (e.g., ``"officially-supported-as-of-mvp-release"``,
    ``"version-agnostic; detected at init"``,
    ``"latest-at-phase-1.5-design-time"``) are NOT semver-parseable;
    the function returns ``False`` for them so the dispatcher treats
    ``available=True`` as success without a version comparison.

    Likewise, when ``observed`` is ``None`` (the probe did NOT capture a
    version) OR ``observed`` is non-parseable, returns ``False``: the
    probe-level decision (``available=True``) is the source of truth and
    a missing version is not a failure.
    """
    if observed is None or floor is None:
        return False
    try:
        observed_v = Version(observed)
    except InvalidVersion:
        return False
    try:
        floor_v = Version(floor)
    except InvalidVersion:
        return False
    return observed_v < floor_v


# --------------------------------------------------------------------------- #
# Marker registration helper                                                  #
# --------------------------------------------------------------------------- #


def _build_marker_context(
    entry: Mapping[str, Any],
    project_type: ProjectType,
    marker_class: str,
    taxonomy_entries: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, str]:
    """Build the ``marker_contexts[marker_class]`` mapping for emission.

    Reads the taxonomy entry's ``pointer_context_fields`` declaration
    and populates each declared field from the dependency entry +
    project-type parameter. Missing values default to empty strings —
    Story 6.2's interpolation surfaces those at render time as
    :exc:`MarkerContextMissing` if any required field lacks a value;
    Story 7.3 callers populate the canonical fields proactively so the
    interpolation always succeeds.

    For the four init marker classes Story 7.3 exercises:

    * ``env-setup-failed`` — ``pointer_context_fields: []``; returns
      empty mapping.
    * ``playwright-mcp-unavailable`` — ``pointer_context_fields:
      [project_type, version_range]``; returns the pair populated from
      the passed ``project_type`` and the dependency entry's
      ``version_floor`` (treated as the version range string per Story
      6.2's actionable-pointer pattern).

    Args:
        entry: The dependency entry mapping.
        project_type: The project-type discriminator.
        marker_class: The base marker class (no Pattern 2 suffix).
        taxonomy_entries: Pre-loaded taxonomy entries map.

    Returns:
        The context mapping for this marker emission. Empty when the
        taxonomy class declares ``pointer_context_fields: []``.
    """
    taxonomy_entry = taxonomy_entries.get(marker_class, {})
    required_fields = tuple(taxonomy_entry.get("pointer_context_fields") or ())
    if not required_fields:
        return {}
    version_floor = entry.get("version_floor") or entry.get("version_policy") or ""
    sources: dict[str, str] = {
        "project_type": project_type,
        "version_range": str(version_floor),
    }
    return {field: sources.get(field, "") for field in required_fields}


# --------------------------------------------------------------------------- #
# Dispatcher branches                                                         #
# --------------------------------------------------------------------------- #


def _dispatch_total_block(
    *,
    dependency: str,
    entry: Mapping[str, Any],
    profile_spec: Mapping[str, Any],
    project_type: ProjectType,
    probe_result: PreconditionProbeResult,
    run_state: RunState | None,
    marker_registry: MarkerClassRegistry,
    taxonomy_entries: Mapping[str, Mapping[str, Any]],
) -> tuple[PreconditionResult, RunState | None]:
    """Dispatch a total-block init profile per AC-3.

    On probe-fail (``available=False`` OR version below floor):

    * Registers the marker per the profile's ``marker_class`` /
      ``sub_classification`` declaration via
      :func:`record_marker_with_context`.
    * Records ``outcome="halt"`` in the result.
    * Surfaces the dependency's ``diagnostic`` field verbatim.

    On probe-pass (``available=True`` AND version satisfies floor):

    * Records ``outcome="pass"``.
    * Does NOT register a marker.
    """
    version_floor = entry.get("version_floor")
    is_version_floor_str = isinstance(version_floor, str)
    version_below = (
        is_version_floor_str
        and _version_below_floor(
            probe_result.version_observed,
            version_floor if is_version_floor_str else None,
        )
    )
    failed = (not probe_result.available) or version_below
    diagnostic = profile_spec.get("diagnostic")
    dep_diagnostic = diagnostic if isinstance(diagnostic, str) else None

    if not failed:
        return (
            PreconditionResult(
                dependency=dependency,
                outcome="pass",
                marker_class=None,
                sub_classification=None,
                diagnostic_text=None,
                dependency_diagnostic=dep_diagnostic,
            ),
            run_state,
        )

    marker_class = profile_spec.get("marker_class")
    if not isinstance(marker_class, str) or not marker_class:
        # Defensive: the profile MUST declare marker_class for a
        # total-block init failure post-Story 7.3 (per AC-8). If the
        # field is absent, the dispatcher cannot route the marker —
        # surface as a contract violation rather than a silent skip.
        raise RuntimeError(
            f"init_preconditions: dependency {dependency!r} total-block "
            "init profile is missing required field 'marker_class' "
            "(per Story 7.3 AC-8 / SDN-001 schema-version 1.1+)"
        )
    sub_class_raw = profile_spec.get("sub_classification")
    sub_class = sub_class_raw if isinstance(sub_class_raw, str) and sub_class_raw else None

    next_run_state = run_state
    if next_run_state is not None:
        context = _build_marker_context(entry, project_type, marker_class, taxonomy_entries)
        next_run_state = record_marker_with_context(
            run_state=next_run_state,
            marker_class=marker_class,
            sub_classification=sub_class,
            context=context if context else None,
            marker_registry=marker_registry,
        )

    return (
        PreconditionResult(
            dependency=dependency,
            outcome="halt",
            marker_class=marker_class,
            sub_classification=sub_class,
            diagnostic_text=dep_diagnostic,
            dependency_diagnostic=dep_diagnostic,
        ),
        next_run_state,
    )


def _dispatch_graceful_degrade(
    *,
    dependency: str,
    entry: Mapping[str, Any],
    profile_spec: Mapping[str, Any],
    project_type: ProjectType,
    probe_result: PreconditionProbeResult,
    run_state: RunState | None,
    marker_registry: MarkerClassRegistry,
    taxonomy_entries: Mapping[str, Mapping[str, Any]],
) -> tuple[PreconditionResult, RunState | None]:
    """Dispatch a graceful-degrade init profile per AC-4.

    On probe-fail (``available=False`` OR version below floor): registers
    the profile's ``marker_class`` (with ``sub_classification`` if
    declared), records ``outcome="warn"``; does NOT halt.

    On probe-pass: records ``outcome="pass"``; no marker.

    Version-floor check mirrors :func:`_dispatch_total_block` for
    symmetry (code-review patch D2-A): a dep that is present but below
    the declared floor is functionally degraded — exactly the
    graceful-degrade semantics (emit marker, proceed). Free-text
    ``version_floor`` values are treated as availability-only per the
    same :func:`_version_below_floor` semantics used in total-block.

    Currently no canonical dependency declares ``graceful-degrade`` at
    the init phase per ``dependencies.yaml`` (graceful-degrade entries
    are all runtime-only). The branch is exercised directly by
    :func:`tests.test_init_preconditions.test_dispatch_graceful_degrade_fail_branch_warn_and_marker`.
    """
    diagnostic = profile_spec.get("diagnostic")
    dep_diagnostic = diagnostic if isinstance(diagnostic, str) else None

    version_floor = entry.get("version_floor")
    is_version_floor_str = isinstance(version_floor, str)
    version_below = is_version_floor_str and _version_below_floor(
        probe_result.version_observed,
        version_floor if is_version_floor_str else None,
    )
    failed = (not probe_result.available) or version_below

    if not failed:
        return (
            PreconditionResult(
                dependency=dependency,
                outcome="pass",
                dependency_diagnostic=dep_diagnostic,
            ),
            run_state,
        )

    marker_class = profile_spec.get("marker_class")
    if not isinstance(marker_class, str) or not marker_class:
        raise RuntimeError(
            f"init_preconditions: dependency {dependency!r} graceful-degrade "
            "init profile is missing required field 'marker_class' "
            "(per SDN-001 graceful-degrade contract)"
        )
    sub_class_raw = profile_spec.get("sub_classification")
    sub_class = sub_class_raw if isinstance(sub_class_raw, str) and sub_class_raw else None

    next_run_state = run_state
    if next_run_state is not None:
        context = _build_marker_context(entry, project_type, marker_class, taxonomy_entries)
        next_run_state = record_marker_with_context(
            run_state=next_run_state,
            marker_class=marker_class,
            sub_classification=sub_class,
            context=context if context else None,
            marker_registry=marker_registry,
        )

    return (
        PreconditionResult(
            dependency=dependency,
            outcome="warn",
            marker_class=marker_class,
            sub_classification=sub_class,
            diagnostic_text=dep_diagnostic,
            dependency_diagnostic=dep_diagnostic,
        ),
        next_run_state,
    )


def _dispatch_opt_in_skip(
    *,
    dependency: str,
    entry: Mapping[str, Any],
    profile_spec: Mapping[str, Any],
    project_type: ProjectType,
    probe_result: PreconditionProbeResult,
    run_state: RunState | None,
    marker_registry: MarkerClassRegistry,
    taxonomy_entries: Mapping[str, Mapping[str, Any]],
) -> tuple[PreconditionResult, RunState | None]:
    """Dispatch an opt-in-skip init profile per AC-4.

    Walks the profile's ``sub_classifications`` list looking for an
    entry whose ``condition`` matches the probe's
    ``sub_classification`` field:

    * ``emits_marker`` branch — registers the named marker, records
      ``outcome="warn"``.
    * ``silent: true`` branch — records ``outcome="silent"`` without
      registering a marker.

    When the probe returns ``available=True`` (the dependency IS
    available; opt-in-skip means the dependency is optional, not that
    a missing probe always silently skips), records ``outcome="pass"``.
    When ``available=False`` and no sub_classification matches, records
    ``outcome="silent"``.
    """
    if probe_result.available:
        return (
            PreconditionResult(dependency=dependency, outcome="pass"),
            run_state,
        )

    sub_classifications = profile_spec.get("sub_classifications") or []
    if not isinstance(sub_classifications, list):
        sub_classifications = []

    matched: Mapping[str, Any] | None = None
    if probe_result.sub_classification is not None:
        for entry_sc in sub_classifications:
            if not isinstance(entry_sc, Mapping):
                continue
            if entry_sc.get("condition") == probe_result.sub_classification:
                matched = entry_sc
                break

    if matched is None:
        return (
            PreconditionResult(dependency=dependency, outcome="silent"),
            run_state,
        )

    if matched.get("silent") is True:
        return (
            PreconditionResult(dependency=dependency, outcome="silent"),
            run_state,
        )

    emits_marker_raw = matched.get("emits_marker")
    if not isinstance(emits_marker_raw, str) or not emits_marker_raw:
        return (
            PreconditionResult(dependency=dependency, outcome="silent"),
            run_state,
        )
    emits_marker: str = emits_marker_raw

    diagnostic_pointer = matched.get("diagnostic_pointer")
    dep_diagnostic = diagnostic_pointer if isinstance(diagnostic_pointer, str) else None

    next_run_state = run_state
    if next_run_state is not None:
        context = _build_marker_context(entry, project_type, emits_marker, taxonomy_entries)
        next_run_state = record_marker_with_context(
            run_state=next_run_state,
            marker_class=emits_marker,
            sub_classification=None,
            context=context if context else None,
            marker_registry=marker_registry,
        )

    return (
        PreconditionResult(
            dependency=dependency,
            outcome="warn",
            marker_class=emits_marker,
            sub_classification=probe_result.sub_classification,
            diagnostic_text=dep_diagnostic,
            dependency_diagnostic=dep_diagnostic,
        ),
        next_run_state,
    )


# --------------------------------------------------------------------------- #
# Public orchestration entry point                                            #
# --------------------------------------------------------------------------- #


def run_init_preconditions(
    probes: PreconditionProbeRegistry,
    project_type: ProjectType,
    *,
    dependencies_path: pathlib.Path | None = None,
    marker_registry: MarkerClassRegistry | None = None,
    run_state: RunState | None = None,
) -> PreconditionRun:
    """Walk every declared dependency's init profile and dispatch.

    Single public orchestration entry point per AC-1 / AC-2. Composes
    :func:`load_dependencies` + the three dispatcher branches +
    :func:`record_marker_with_context`. Pure orchestration — no I/O
    beyond the dependencies.yaml read; no subprocess calls; the
    injected probe callables are responsible for their own probe I/O.

    The dispatcher walks the ``dependencies`` mapping in DECLARATION
    ORDER (the order entries appear in ``dependencies.yaml``, NOT
    alphabetically) per AC-2. Every dependency is probed (no
    short-circuit on first failure) so the aggregated diagnostic shows
    ALL failures in one pass per AC-3.

    Args:
        probes: Injected per-dependency probe registry. Pattern 6 —
            production probes are subprocess / file-system / network
            wrappers instantiated by the orchestrator skill;
            test probes are fixture callables.
        project_type: One of ``"web"`` / ``"api"`` / ``"mobile"``;
            consumed when resolving ``by_project_type`` profiles for
            ``playwright-mcp`` / ``mobile-mcp``.
        dependencies_path: Optional explicit path to a
            ``dependencies.yaml`` fixture (test isolation). Defaults to
            the canonical workspace path resolved by
            :func:`load_dependencies`.
        marker_registry: Optional pre-loaded
            :class:`MarkerClassRegistry`. Defaults to a fresh load via
            :func:`load_marker_class_registry`.
        run_state: Optional starting :class:`RunState`. When provided,
            marker registrations compose into that state; the returned
            ``run_state`` carries the post-dispatch state. When ``None``,
            no marker persistence occurs (the dispatcher records the
            per-dep results without populating ``active_markers``);
            useful for diagnostic-only / test paths.

    Returns:
        :class:`PreconditionRun` with ``halted`` set IFF at least one
        result has ``outcome=="halt"``, ``results`` in declaration
        order, and ``run_state`` carrying the post-dispatch state (or
        ``None`` when none was supplied).

    Raises:
        RuntimeError: ``load_dependencies`` raised on SDN-001 shape
            violation (file unreadable, YAML parse failure, schema
            violation). The exception propagates UNCHANGED per
            Pattern 5 — Story 7.3 does NOT swallow the contract failure
            into a precondition diagnostic.
        UnknownMarkerClass: A registered marker class is not in
            ``marker_registry``. Surfaces a contract violation per
            Pattern 5.
    """
    raw = load_dependencies(dependencies_path)
    dependencies = raw.get("dependencies")
    if not isinstance(dependencies, Mapping):
        # SDN-001 shape contract: ``dependencies`` MUST be a mapping;
        # load_dependencies's validator enforces this, so this branch
        # should not fire. Defensive guard for type narrowing.
        raise RuntimeError(
            f"init_preconditions: dependencies.yaml at {dependencies_path or '<default>'} "
            "did not yield a 'dependencies' mapping"
        )

    if marker_registry is None:
        marker_registry = load_marker_class_registry()
    taxonomy_entries = _load_marker_taxonomy_entries()

    results: list[PreconditionResult] = []
    current_run_state = run_state

    for dependency, entry in dependencies.items():
        if not isinstance(entry, Mapping):
            continue
        profile_spec = _resolve_init_profile(entry, project_type)
        if profile_spec is None:
            # No init profile declared under the resolved discriminator;
            # structurally analogous to opt-in-skip-not-applicable.
            results.append(
                PreconditionResult(dependency=dependency, outcome="silent")
            )
            continue

        probe = probes.probe_for(dependency)
        if probe is None:
            # Dependency declared in the schema but no probe registered;
            # silent-skip the dispatch so a future schema addition does
            # not crash before the orchestrator's probe registry catches
            # up.
            results.append(
                PreconditionResult(dependency=dependency, outcome="silent")
            )
            continue

        probe_result = probe()

        profile_kind = profile_spec.get("profile")
        if profile_kind == "total-block":
            result, current_run_state = _dispatch_total_block(
                dependency=dependency,
                entry=entry,
                profile_spec=profile_spec,
                project_type=project_type,
                probe_result=probe_result,
                run_state=current_run_state,
                marker_registry=marker_registry,
                taxonomy_entries=taxonomy_entries,
            )
        elif profile_kind == "graceful-degrade":
            result, current_run_state = _dispatch_graceful_degrade(
                dependency=dependency,
                entry=entry,
                profile_spec=profile_spec,
                project_type=project_type,
                probe_result=probe_result,
                run_state=current_run_state,
                marker_registry=marker_registry,
                taxonomy_entries=taxonomy_entries,
            )
        elif profile_kind == "opt-in-skip":
            result, current_run_state = _dispatch_opt_in_skip(
                dependency=dependency,
                entry=entry,
                profile_spec=profile_spec,
                project_type=project_type,
                probe_result=probe_result,
                run_state=current_run_state,
                marker_registry=marker_registry,
                taxonomy_entries=taxonomy_entries,
            )
        else:
            # Unknown profile value would have been rejected by
            # load_dependencies's SDN-001 validator already; defensive
            # guard.
            raise RuntimeError(
                f"init_preconditions: dependency {dependency!r} init profile "
                f"declares unknown 'profile' value {profile_kind!r}"
            )
        results.append(result)

    halted = any(r.outcome == "halt" for r in results)
    return PreconditionRun(
        halted=halted,
        results=tuple(results),
        run_state=current_run_state,
    )


# --------------------------------------------------------------------------- #
# Aggregated diagnostic renderer (AC-5 / AC-6)                                #
# --------------------------------------------------------------------------- #


def format_init_diagnostic(
    run: PreconditionRun,
    *,
    marker_registry: MarkerClassRegistry | None = None,
) -> str:
    """Render the aggregated named-invariant diagnostic per AC-5.

    Per AC-5: lists every failed precondition (``outcome in ("halt",
    "warn")``) WITHOUT introducing an umbrella marker. ``outcome ==
    "pass"`` and ``outcome == "silent"`` results are OMITTED — the
    diagnostic is failure-focused per loud-fail discipline.

    Per AC-6 path (b): each per-marker entry's H3 + Sub-classification
    bullet + Diagnostic pointer bullet are rendered via
    :func:`bundle_assembly._render_marker_entry_body` so the shape is
    byte-identical to the bundle's loud-fail block (Story 6.1 single
    source of truth). The init diagnostic ADDS three init-specific
    bullets (``Dependency``, ``Per-dependency remediation``,
    ``Lifecycle outcome``) interleaved per AC-5's order:

    .. code-block:: markdown

        ### {marker_class}

        - Dependency: {dep_name}
        - Sub-classification: {sub_class_str}
        - Diagnostic pointer: {diagnostic_pointer}
        - How to enable: {actionable_pointer}
        - Per-dependency remediation: {dep_diagnostic}
        - Lifecycle outcome: halt | warn

    The ``How to enable`` bullet is inherited from the shared helper
    so the byte-identical structural match per AC-9 case 12 holds for
    the H3 header + Sub-classification bullet + Diagnostic pointer
    bullet (the three inherited bullets named verbatim in AC-6).

    Per AC-5 empty-case sentinel: when no entries have ``outcome in
    ("halt", "warn")``, returns ``"## Init Precondition Check — All
    Preconditions Met\\n"`` — mirrors Story 6.1's
    ``## ✓ Loud-Fail Markers — None`` posture.

    Args:
        run: The :class:`PreconditionRun` returned by
            :func:`run_init_preconditions`.
        marker_registry: Optional pre-loaded
            :class:`MarkerClassRegistry`. Defaults to a fresh load.

    Returns:
        The rendered markdown body. The empty-case sentinel ends with a
        trailing newline (per AC-5's verbatim form); the non-empty
        body does NOT carry a trailing newline beyond the canonical
        structural shape (mirroring
        :func:`bundle_assembly._render_loud_fail_block`'s posture).
    """
    failed = tuple(r for r in run.results if r.outcome in ("halt", "warn"))
    if not failed:
        return _INIT_ALL_PRECONDITIONS_MET_SENTINEL

    if marker_registry is None:
        marker_registry = load_marker_class_registry()
    taxonomy_entries = _load_marker_taxonomy_entries()

    contexts: dict[str, Mapping[str, object]] = {}
    if run.run_state is not None:
        contexts = dict(run.run_state.marker_contexts)

    parts: list[str] = [_INIT_DIAGNOSTIC_HEADER, ""]
    for result in failed:
        if not result.marker_class:
            # Defensive: a "halt" or "warn" result must carry a marker
            # class (post-Story 7.3); skip otherwise rather than emit
            # a malformed entry.
            continue
        full_marker = (
            f"{result.marker_class}: {result.sub_classification}"
            if result.sub_classification
            else result.marker_class
        )
        try:
            entry_lines = _render_marker_entry_body(
                full_marker,
                marker_registry=marker_registry,
                marker_contexts=contexts,
                taxonomy_entries=taxonomy_entries,
            )
        except MarkerContextMissing:
            # Diagnostic-only mode (run_state=None): pointer-context fields
            # unavailable for interpolation. Render without the actionable
            # pointer interpolation rather than crashing.
            taxonomy_entry = taxonomy_entries.get(result.marker_class, {})
            raw_pointer = " ".join(
                str(taxonomy_entry.get("diagnostic_pointer", "")).split()
            )
            sub_str = result.sub_classification or "none"
            entry_lines = [
                f"### {full_marker}",
                "",
                f"- Sub-classification: {sub_str}",
                f"- Diagnostic pointer: {raw_pointer}",
                "- How to enable: (context unavailable — supply run_state for full pointer interpolation)",
            ]
        # entry_lines layout:
        #   [0] "### {marker_class}"
        #   [1] ""
        #   [2] "- Sub-classification: …"
        #   [3] "- Diagnostic pointer: …"
        #   [4] "- How to enable: …"
        # AC-5's per-entry order interleaves:
        #   ### marker_class
        #   <blank>
        #   - Dependency: <dep>
        #   - Sub-classification: …       (inherited verbatim)
        #   - Diagnostic pointer: …       (inherited verbatim)
        #   - How to enable: …            (inherited verbatim — the byte-
        #                                  identical contract per AC-6 names
        #                                  the first two; the third is
        #                                  preserved for shared-helper
        #                                  fidelity.)
        #   - Per-dependency remediation: <dep_diagnostic>
        #   - Lifecycle outcome: halt | warn
        h3_header = entry_lines[0]
        sub_class_bullet = entry_lines[2]
        diag_pointer_bullet = entry_lines[3]
        how_to_enable_bullet = entry_lines[4]
        dep_remediation = result.dependency_diagnostic or ""
        parts.extend(
            [
                h3_header,
                "",
                f"- Dependency: {result.dependency}",
                sub_class_bullet,
                diag_pointer_bullet,
                how_to_enable_bullet,
                f"- Per-dependency remediation: {dep_remediation}",
                f"- Lifecycle outcome: {result.outcome}",
                "",
            ]
        )
    if parts and parts[-1] == "":
        parts.pop()
    return "\n".join(parts)
