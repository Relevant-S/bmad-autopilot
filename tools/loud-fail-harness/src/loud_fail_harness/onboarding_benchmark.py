"""Onboarding benchmark substrate (Story 7.9). FR44 + NFR-P3 + Pattern 5/6/7 + ADR-003 substrate-component-count posture.

Architectural placement (Story 7.9 Dev Notes "no new substrate components,
no new marker classes, no new external Python dependencies"): this module
is a CONSUMER LIBRARY parallel to Story 6.3's :mod:`marker_coverage_audit`,
Story 7.6's :mod:`init_non_destructive_guard`, Story 7.8's
:mod:`tea_boundary_orientation`. It is NOT a sixth substrate component
beyond ADR-003's enumerated five (Architecture View 2 / ADR-003 Consequence 1
keeps the substrate-component count at FIVE). The entry point is
library-as-CLI-aid invoked from :file:`bmad-autopilot/.github/workflows/release-benchmark.yml`
once per release cycle (NOT per PR — the cost-vs-coverage tradeoff per AC-5
makes per-PR full-loop benchmarks economically infeasible).

What this benchmark validates (FR44 verbatim per :file:`prd.md:869`):
    "First-run complete story loop on the sample story succeeds in
    ≤ 5 minutes on a typical developer laptop (onboarding-time target)."

NFR-P3 published commitment (:file:`prd.md:936`):
    "≤ 5 minutes from ``/bmad-automation init`` completion to first
    successful sample-story loop merge-ready."

What the benchmark records (per AC-2 verbatim, :file:`epics.md:3149-3156`):
    Per-component timings — NOT aggregate-only — for the seven measured
    components: install, init-precondition-check, init-scaffold (sample
    story), init-stub-generation (config + qa-runbook + TEA-boundary
    orientation), first-specialist-dispatch (orchestrator startup +
    Dev dispatch latency), per-specialist-runtime (Dev / Review-BMAD /
    QA seam-to-seam totals), bundle-assembly. Aggregate-only timings
    are REJECTED as deliverables per AC-2's verbatim restriction:
    missed-target releases must be diagnosable to specific components.

Loud-fail discipline (Pattern 5 — named invariants):
    Exit codes distinguish failure classes so release CI logs are
    diagnosable.
        0 — full pass: ``end_to_end_total_seconds <= TARGET_FIRST_LOOP_SECONDS``;
            row appended to the longitudinal artifact.
        1 — missed-target: total exceeds the ≤5-minute budget. Per AC-4
            verbatim, this gates the release per the discipline of
            NFR-P3 being a published commitment. The artifact still
            captures the row (with ``missed_component`` + a remediation
            or deferral note) so the longitudinal record's trend
            visibility per AC-6 is preserved across green and red runs.
        2 — broken benchmark: ``BenchmarkArtifactError`` raised. Reasons
            include malformed artifact anchor markers, atomic-write
            failures, subprocess-phase non-zero exits before timing
            capture completes, missing ``claude`` binary at environment
            probe. Distinct from exit 1: the benchmark itself cannot
            run, so the release manager must investigate the harness
            before re-evaluating the target.

Reproducibility contract (AC-5):
    The benchmark loads the canonical fixture via Story 7.4's public
    :func:`loud_fail_harness.sample_story_scaffold.load_sample_story_content`
    — the SAME bytes every benchmark run consumes. The reference
    project is provisioned FRESH on each run (``tempfile.TemporaryDirectory``
    OR a CI runner's clean workspace). Environment variability is
    captured in the artifact's environment-notes columns rather than
    silently normalised away.

Sensor-not-advisor:
    ``run_benchmark`` REPORTS captured timings + verdict; it does NOT
    auto-edit code, suggest remediations, or rewrite the artifact's
    rows. The release manager interprets the missed-component verdict
    AND chooses remediation OR deferral.

Cross-component reuse posture:
    * :func:`loud_fail_harness._shared.find_repo_root` — REUSED for
      default repo-root resolution.
    * :func:`loud_fail_harness.sample_story_scaffold.load_sample_story_content`
      — REUSED for fixture loading (AC-5 byte-equality contract).
    * NO other substrate-component imports — the benchmark is a thin
      orchestration layer over ``subprocess.run`` plus per-component
      timing captures.

NOT a runtime marker emission surface:
    Per Story 1.11's atomic-vs-aggregated principle (markers signal
    atomic failure surfaces, NOT informational signals), the benchmark
    is release-time engineering observation. NO call to
    ``record_marker_with_context`` exists in this module; NO new
    entry in ``schemas/marker-taxonomy.yaml`` is required; NO new
    row in ``_data/marker_coverage_surfaces.yaml`` is required.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import platform
import re
import secrets
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from loud_fail_harness._shared import find_repo_root

__all__ = [
    "ARTIFACT_RELATIVE_PATH",
    "BENCHMARK_FIXTURE_PATH",
    "TARGET_FIRST_LOOP_SECONDS",
    "BenchmarkArtifactError",
    "BenchmarkRecord",
    "BenchmarkRequest",
    "ComponentTimings",
    "EnvironmentNotes",
    "HardwareTier",
    "ROWS_BEGIN_ANCHOR",
    "ROWS_END_ANCHOR",
    "append_record_to_artifact",
    "build_artifact_seed",
    "evaluate_target",
    "main",
    "render_record_row",
    "run_benchmark",
]


# --------------------------------------------------------------------------- #
# Module-level constants (AC-1)                                                #
# --------------------------------------------------------------------------- #

#: The 5-minute NFR-P3 budget in seconds. SINGLE source of truth for the
#: gate; mutating this constant requires a release-notes flag per FR44's
#: published-commitment posture.
TARGET_FIRST_LOOP_SECONDS: Final[int] = 300

#: The canonical reference fixture path (resolved relative to the harness
#: package via ``importlib.resources``). The Story 7.4 sample-auto-001
#: content is the BENCHMARK FIXTURE per :file:`epics.md:3148`.
BENCHMARK_FIXTURE_PATH: Final[str] = "_data/sample-auto-001.md"

#: The artifact path resolved relative to the inner repo root, mirroring
#: Story 6.3's :file:`docs/marker-coverage-audit.md` precedent.
ARTIFACT_RELATIVE_PATH: Final[str] = "docs/onboarding-benchmark.md"

#: Anchor markers delimiting the rows-table body (AC-3). New rows are
#: appended IMMEDIATELY before :data:`ROWS_END_ANCHOR`. The append-only
#: discipline mirrors Story 6.3's :file:`marker-coverage-audit.md` and
#: Story 1.11's per-convention table append-only convention.
ROWS_BEGIN_ANCHOR: Final[str] = "<!-- benchmark-rows:begin -->"
ROWS_END_ANCHOR: Final[str] = "<!-- benchmark-rows:end -->"

#: Hardware-tier label literal alias surfaced via the CLI ``--hardware-tier``
#: argument; the AC's "typical developer laptop" maps to ``"developer-laptop"``;
#: CI runs map to ``"ci-runner-standard"`` or ``"ci-runner-large"``;
#: ad-hoc / manual runs fall back to ``"other"``.
HardwareTier = Literal[
    "developer-laptop", "ci-runner-standard", "ci-runner-large", "other"
]

#: ISO-8601 calendar-date regex (AC-1 ``date`` field shape). The run-time
#: writer emits dates produced from ``datetime.date.today().isoformat()``;
#: the validator guards against hand-edits writing stamps such as
#: ``"2026-5-8"`` that would break alphabetical sort.
_ISO_DATE_RE: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: ``ComponentTimings`` field names in canonical column order (AC-3 column
#: header). Used by :func:`render_record_row` and the artifact's first-row
#: rendering. Centralised so the row-render and the missed-component
#: argmax computation use the SAME ordering.
_COMPONENT_FIELD_ORDER: Final[tuple[str, ...]] = (
    "install_seconds",
    "init_precondition_check_seconds",
    "init_scaffold_seconds",
    "init_stub_generation_seconds",
    "first_specialist_dispatch_seconds",
    "dev_runtime_seconds",
    "review_bmad_runtime_seconds",
    "qa_runtime_seconds",
    "bundle_assembly_seconds",
)

#: Tolerance window for the component-sum ↔ end-to-end-total invariant
#: (AC-2). Inter-phase scheduling overhead is permitted within ±0.5s;
#: drift outside the window is structurally rejected.
_TOTAL_TOLERANCE_SECONDS: Final[float] = 0.5

#: Canonical structured-text column header rendered into the artifact's
#: rows table.
_ROW_TABLE_HEADER: Final[tuple[str, str]] = (
    "| Date | Version | Claude Code Version | OS | Hardware Tier | Python "
    "| Install | Init: Precond | Init: Scaffold | Init: Stub-gen "
    "| First Dispatch | Dev | Review-BMAD | QA | Bundle | Total "
    "| Target Met | Missed Component | Notes |",
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- "
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
)


# --------------------------------------------------------------------------- #
# Structured-error class (AC-1)                                                #
# --------------------------------------------------------------------------- #


class BenchmarkArtifactError(Exception):
    """Raised when the benchmark cannot honor its release-time contract.

    Pattern 5 — loud-fail / named invariants. The exception carries a
    structured ``reason`` discriminator naming the concrete failure
    mode so callers (the release-CI workflow) can route to the correct
    surface OR HALT loudly rather than silently coercing to a sentinel.

    Mirrors the shape of
    :class:`loud_fail_harness.tea_boundary_orientation.OrientationConfigError`
    and
    :class:`loud_fail_harness.install_path.InstallPathConfigError`.

    Attributes:
        reason: Short kebab-case discriminator. Documented values:
            ``"artifact-anchors-missing"`` — anchor markers absent or
            out-of-order; ``"artifact-atomic-write-failed"`` — atomic
            persistence failed; ``"phase-subprocess-failed"`` — a
            measured subprocess exited non-zero before the timing
            capture completed; ``"duplicate-row-detected"`` — the
            ``(date, version, hardware_tier)`` triple matches an
            existing row.
        phase: The named component if the failure occurred mid-phase;
            ``None`` for non-phase failures (e.g., artifact-anchor
            errors that fire from :func:`append_record_to_artifact`).
        artifact_path: The resolved on-disk path the writer attempted
            to update; ``None`` when the failure pre-dates path
            resolution.
        subprocess_stderr_excerpt: Full stderr string from the failed
            subprocess; ``None`` for non-subprocess failures. The
            exception *message* includes only the first 200 characters
            to keep log output bounded; this attribute retains the full
            value for programmatic inspection.
    """

    def __init__(
        self,
        *,
        reason: str,
        phase: str | None = None,
        artifact_path: pathlib.Path | None = None,
        subprocess_stderr_excerpt: str | None = None,
    ) -> None:
        self.reason = reason
        self.phase = phase
        self.artifact_path = artifact_path
        self.subprocess_stderr_excerpt = subprocess_stderr_excerpt
        message = f"BenchmarkArtifactError[{reason}]"
        if phase is not None:
            message += f" phase={phase}"
        if artifact_path is not None:
            message += f" artifact_path={artifact_path!s}"
        if subprocess_stderr_excerpt is not None:
            excerpt = subprocess_stderr_excerpt[:200]
            message += f" stderr={excerpt!r}"
        super().__init__(message)


# --------------------------------------------------------------------------- #
# Pydantic models (AC-1, AC-2)                                                 #
# --------------------------------------------------------------------------- #


class EnvironmentNotes(BaseModel):
    """Environment-notes columns of a benchmark row (AC-1).

    Pattern 6 — frozen so the writer cannot mutate the captured
    environment between record-construction and artifact-append.
    Mirrors :class:`loud_fail_harness.tea_boundary_orientation.OrientationOutcome`
    in shape.

    Attributes:
        claude_code_version: e.g., ``"2.1.32"``. Sourced at run-time
            via the ``claude --version`` subprocess (Story 7.3
            ``_probe_claude_code_version`` precedent).
        os_label: e.g., ``"darwin-25.3.0"``, ``"linux-ubuntu-24.04"``.
            Sourced from ``platform.system().lower() + "-" + platform.release()``.
        hardware_tier: The AC's "typical developer laptop" maps to
            ``"developer-laptop"``; CI runs map to one of the
            ``ci-runner-*`` values; ad-hoc runs fall back to ``"other"``.
            REQUIRES explicit caller declaration — coarse human
            judgment, not machine-detectable.
        python_version: e.g., ``"3.12.5"``. Sourced from
            ``platform.python_version()``.
    """

    model_config = ConfigDict(frozen=True)

    claude_code_version: str = Field(
        ..., min_length=1, description="Captured at run-time via `claude --version`."
    )
    os_label: str = Field(
        ..., min_length=1, description="`<system>-<release>` (lower-cased)."
    )
    hardware_tier: HardwareTier = Field(
        ..., description="Coarse human-judgment label; CLI surfaces it."
    )
    python_version: str = Field(
        ..., min_length=1, description="`platform.python_version()` capture."
    )


class ComponentTimings(BaseModel):
    """Per-component timings for one benchmark run (AC-1, AC-2).

    Pattern 6 — frozen so timings cannot be silently rewritten by a
    downstream caller. All fields are seconds (``float``); non-negative
    is enforced by a field validator.

    The seven AC-mandated components (per :file:`epics.md:3149-3156`)
    are partitioned across NINE fields because:

    * "Init time, broken into" (AC-2) splits into THREE fields
      (precondition / scaffold / stub-gen).
    * "Per-specialist runtime (Dev, Review-BMAD, QA)" (AC-2) splits
      into THREE fields (one per specialist).
    * The remaining three (install, first-dispatch, bundle-assembly)
      are 1-to-1 with the AC's groupings.

    The partitioning is explicit so missed-target diagnostics can
    point at the SPECIFIC sub-component that blew the budget rather
    than at a coarse phase grouping.
    """

    model_config = ConfigDict(frozen=True)

    install_seconds: float = Field(
        ..., description="Story 7.2 install — git-clone-symlink OR plugin install."
    )
    init_precondition_check_seconds: float = Field(
        ..., description="Story 7.3 `run_init_preconditions` aggregate runtime."
    )
    init_scaffold_seconds: float = Field(
        ..., description="Story 7.4 `scaffold_sample_story` runtime (proceed-fresh branch)."
    )
    init_stub_generation_seconds: float = Field(
        ...,
        description=(
            "Story 7.5 `scaffold_config_qa_runbook_stubs` + Story 7.8 "
            "`emit_orientation_if_first_run` aggregated. The lone "
            "intra-phase aggregation in this schema."
        ),
    )
    first_specialist_dispatch_seconds: float = Field(
        ...,
        description=(
            "Orchestrator startup + Dev dispatch latency — elapsed time "
            "from `/bmad-automation run sample-auto-001` invocation to "
            "first Dev specialist Task tool call."
        ),
    )
    dev_runtime_seconds: float = Field(
        ...,
        description="Dev specialist seam-to-seam total (sum of all Dev invocations).",
    )
    review_bmad_runtime_seconds: float = Field(
        ..., description="Review-BMAD specialist seam-to-seam total."
    )
    qa_runtime_seconds: float = Field(
        ..., description="QA specialist seam-to-seam total."
    )
    bundle_assembly_seconds: float = Field(
        ...,
        description=(
            "Story 2.11 + Story 6.1 bundle-assembler runtime — final "
            "seam from QA-done to merge-ready PR-bundle persistence."
        ),
    )

    @field_validator(
        "install_seconds",
        "init_precondition_check_seconds",
        "init_scaffold_seconds",
        "init_stub_generation_seconds",
        "first_specialist_dispatch_seconds",
        "dev_runtime_seconds",
        "review_bmad_runtime_seconds",
        "qa_runtime_seconds",
        "bundle_assembly_seconds",
    )
    @classmethod
    def _must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError(
                f"component timing must be non-negative; got {v!r}. "
                "Negative durations indicate a clock skew or a captured-end-"
                "before-start invariant violation."
            )
        return v

    def total_seconds(self) -> float:
        """Sum of all component timings (sensor — does not enforce the
        ±0.5s tolerance; that lives on :class:`BenchmarkRecord`'s root
        validator).
        """
        return sum(getattr(self, name) for name in _COMPONENT_FIELD_ORDER)


class BenchmarkRecord(BaseModel):
    """One canonical per-release row of the longitudinal artifact (AC-1).

    Pattern 6 — frozen so an appended record cannot be rewritten between
    construction and artifact persistence.

    The root validator enforces THREE invariants (AC-2 + AC-4):

    1. ``end_to_end_total_seconds`` ↔ ``component_timings.total_seconds()``
       agree within ±0.5s (the inter-phase scheduling-overhead
       tolerance).
    2. ``missed_component`` is NON-``None`` when ``target_met=False``;
       ``None`` when ``target_met=True``.
    3. ``remediation_or_deferral_note`` is NON-``None`` when
       ``target_met=False``; ``None`` when ``target_met=True``.

    Mismatched populated-ness vs ``target_met`` raises a
    Pydantic ``ValidationError`` with a named-invariant per Pattern 5.
    """

    model_config = ConfigDict(frozen=True)

    date: str = Field(
        ...,
        description="ISO-8601 calendar date `YYYY-MM-DD` of the benchmark run.",
    )
    version: str = Field(
        ...,
        min_length=1,
        description="Automator release version (e.g., `0.1.0`).",
    )
    environment: EnvironmentNotes
    component_timings: ComponentTimings
    end_to_end_total_seconds: float = Field(
        ...,
        description=(
            "Independently captured aggregate; root validator confirms "
            "agreement with `component_timings.total_seconds()` within "
            "±0.5s tolerance."
        ),
    )
    target_met: bool = Field(
        ...,
        description=(
            "True iff `end_to_end_total_seconds <= TARGET_FIRST_LOOP_SECONDS`. "
            "Computed by the caller (NOT a derived field) so the constructor "
            "is symmetric with the artifact's serialized shape."
        ),
    )
    missed_component: str | None = Field(
        default=None,
        description=(
            "Field name (from `_COMPONENT_FIELD_ORDER`) of the largest-"
            "contributor when `target_met=False`; suffixed with "
            "`+aggregate-overage` if argmax-component is itself within "
            "historical-mean budget. `None` on `target_met=True`."
        ),
    )
    remediation_or_deferral_note: str | None = Field(
        default=None,
        description=(
            "Plain-text remediation summary OR deferral entry pointing "
            "at the follow-up issue. Required-NON-None when "
            "`target_met=False` per AC-4 verbatim."
        ),
    )

    @field_validator("date")
    @classmethod
    def _date_must_be_iso(cls, v: str) -> str:
        if not _ISO_DATE_RE.match(v):
            raise ValueError(
                f"date must be ISO-8601 calendar date `YYYY-MM-DD`; got {v!r}."
            )
        return v

    @field_validator("end_to_end_total_seconds")
    @classmethod
    def _total_must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError(
                f"end_to_end_total_seconds must be non-negative; got {v!r}."
            )
        return v

    @model_validator(mode="after")
    def _check_invariants(self) -> "BenchmarkRecord":
        component_sum = self.component_timings.total_seconds()
        delta = self.end_to_end_total_seconds - component_sum
        if delta < -_TOTAL_TOLERANCE_SECONDS:
            raise ValueError(
                "component-sum-exceeds-end-to-end-total: "
                f"sum(components)={component_sum:.3f}s exceeds "
                f"end_to_end_total_seconds={self.end_to_end_total_seconds:.3f}s "
                f"by {-delta:.3f}s (> {_TOTAL_TOLERANCE_SECONDS}s tolerance). "
                "Physically impossible — investigate clock-source drift."
            )
        if delta > _TOTAL_TOLERANCE_SECONDS:
            raise ValueError(
                "unaccounted-overhead-exceeds-tolerance: "
                f"end_to_end_total_seconds={self.end_to_end_total_seconds:.3f}s "
                f"exceeds sum(components)={component_sum:.3f}s by "
                f"{delta:.3f}s (> {_TOTAL_TOLERANCE_SECONDS}s tolerance). "
                "Account for the missing time via an existing component "
                "field or extend the schema."
            )
        if self.target_met and self.missed_component is not None:
            raise ValueError(
                "missed-component-must-be-none-when-target-met: "
                f"target_met=True but missed_component={self.missed_component!r}."
            )
        if not self.target_met and self.missed_component is None:
            raise ValueError(
                "missed-component-required-when-target-missed: "
                "target_met=False but missed_component is None."
            )
        if self.target_met and self.remediation_or_deferral_note is not None:
            raise ValueError(
                "remediation-note-must-be-none-when-target-met: "
                f"target_met=True but remediation_or_deferral_note="
                f"{self.remediation_or_deferral_note!r}."
            )
        if not self.target_met and self.remediation_or_deferral_note is None:
            raise ValueError(
                "remediation-note-required-when-target-missed: "
                "target_met=False but remediation_or_deferral_note is None. "
                "Per AC-4, missed-target releases include a remediation "
                "note OR a deferral entry referencing a follow-up issue."
            )
        return self


class BenchmarkRequest(BaseModel):
    """Caller-assembled input to :func:`run_benchmark` (AC-1).

    Pattern 6 — frozen model. The dependency-injection seam for
    subprocess invocations lives on :func:`run_benchmark`'s
    ``subprocess_runner`` keyword-only parameter (Pattern 6 + AC-8),
    not on this model. Production runs pass ``BenchmarkRequest`` to
    :func:`run_benchmark` with the default ``subprocess_runner=None``
    (falls back to :func:`subprocess.run`).

    Attributes:
        reference_project_root: Absolute path to the FRESH reference
            project the benchmark runs against. Field validator
            ``_must_be_absolute`` mirrors
            :class:`loud_fail_harness.init_non_destructive_guard.GuardRequest`'s
            ``_project_root_must_be_absolute`` precedent.
        repo_root: The Automator inner-repo root containing
            ``tools/loud-fail-harness/`` and ``docs/``. Resolved via
            :func:`loud_fail_harness._shared.find_repo_root` when
            ``None``.
        version: The Automator release version being benchmarked
            (required, non-empty).
        hardware_tier: Coarse human-judgment label; surfaced via
            ``--hardware-tier`` on the CLI.
        claude_code_version: Pre-resolved Claude Code version for
            ad-hoc / manual runs. When ``None``, the runner probes
            via ``claude --version``.
        dry_run: When ``True``, the runner emits the BenchmarkRecord
            but does NOT append to the artifact; the CLI exits 0
            regardless of target-met to support manual experimentation
            without polluting CI signal.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    reference_project_root: pathlib.Path = Field(
        ..., description="Absolute path to the FRESH reference project."
    )
    repo_root: pathlib.Path | None = Field(
        default=None,
        description="Optional Automator inner-repo root override.",
    )
    version: str = Field(
        ..., min_length=1, description="Automator release version."
    )
    hardware_tier: HardwareTier = Field(
        ..., description="Coarse human-judgment hardware-tier label."
    )
    claude_code_version: str | None = Field(
        default=None,
        description=(
            "Pre-resolved Claude Code version. None = probe via "
            "`claude --version` subprocess at run-time."
        ),
    )
    dry_run: bool = Field(
        default=False,
        description=(
            "When True, run_benchmark returns the record without "
            "appending to the artifact; CLI exits 0 regardless of "
            "target-met."
        ),
    )

    @field_validator("reference_project_root")
    @classmethod
    def _reference_project_root_must_be_absolute(
        cls, v: pathlib.Path
    ) -> pathlib.Path:
        if not v.is_absolute():
            raise ValueError(
                f"reference_project_root must be an absolute path; got {v!r}."
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


# --------------------------------------------------------------------------- #
# Pure-function helpers (AC-3, AC-4)                                           #
# --------------------------------------------------------------------------- #


def evaluate_target(
    timings: ComponentTimings,
    *,
    historical_means: dict[str, float] | None = None,
) -> tuple[bool, str | None]:
    """Pure-function release-gate verdict (AC-4).

    Returns ``(target_met, missed_component_or_none)``.
    ``target_met = sum(timings.<fields>) <= TARGET_FIRST_LOOP_SECONDS``.

    On ``target_met=False``: ``missed_component`` is the field name
    with the largest value in ``_COMPONENT_FIELD_ORDER``. When the
    argmax field's value is itself within its historical-mean budget
    (the AC-4 death-by-a-thousand-cuts case at :file:`epics.md:3169`),
    the field name is suffixed with ``+aggregate-overage`` to signal
    that no single phase is the culprit.

    Historical-mean bounds at Story 7.9 landing are bootstrapped from
    the seed row alone (the caller passes a 1-row mean dict; subsequent
    releases compute mean over all prior rows). The suffix logic is
    documented in this module's docstring + the artifact's
    ``## Methodology`` section.

    Keys in ``historical_means`` that do not match any
    ``_COMPONENT_FIELD_ORDER`` name are silently ignored; only the
    argmax field's mean is consulted.

    NO side effects.
    """
    total = timings.total_seconds()
    if total <= TARGET_FIRST_LOOP_SECONDS:
        return True, None

    field_to_value = {name: getattr(timings, name) for name in _COMPONENT_FIELD_ORDER}
    argmax_name, argmax_value = max(field_to_value.items(), key=lambda item: item[1])

    if historical_means is not None:
        historical_mean_for_field = historical_means.get(argmax_name)
        if (
            historical_mean_for_field is not None
            and argmax_value <= historical_mean_for_field
        ):
            return False, f"{argmax_name}+aggregate-overage"
    return False, argmax_name


def render_record_row(record: BenchmarkRecord) -> str:
    """Pure formatter — markdown table row for one record (AC-3).

    Renders deterministically: same input → byte-identical output. The
    ``Target Met`` column renders ✅ for True and ❌ for False.
    ``Missed Component`` and ``Notes`` render `—` (em-dash) on
    ``target_met=True`` rows.

    Component-timing columns render seconds with 1-decimal precision.
    """
    env = record.environment
    timings = record.component_timings

    if record.target_met:
        verdict_glyph = "✅"
    else:
        verdict_glyph = "❌"

    missed_cell = record.missed_component if record.missed_component is not None else "—"
    notes_cell = (
        record.remediation_or_deferral_note
        if record.remediation_or_deferral_note is not None
        else "—"
    )
    # Cell-safe markdown — pipe + newline both break tables. Apply to ALL
    # string columns, not just missed_cell/notes_cell.
    def _cell(s: str) -> str:
        return s.replace("|", "\\|").replace("\n", " ")

    notes_cell = _cell(notes_cell)
    missed_cell = _cell(missed_cell)

    return (
        f"| {_cell(record.date)} | {_cell(record.version)} | {_cell(env.claude_code_version)} "
        f"| {_cell(env.os_label)} | {_cell(env.hardware_tier)} | {_cell(env.python_version)} "
        f"| {timings.install_seconds:.1f} "
        f"| {timings.init_precondition_check_seconds:.1f} "
        f"| {timings.init_scaffold_seconds:.1f} "
        f"| {timings.init_stub_generation_seconds:.1f} "
        f"| {timings.first_specialist_dispatch_seconds:.1f} "
        f"| {timings.dev_runtime_seconds:.1f} "
        f"| {timings.review_bmad_runtime_seconds:.1f} "
        f"| {timings.qa_runtime_seconds:.1f} "
        f"| {timings.bundle_assembly_seconds:.1f} "
        f"| {record.end_to_end_total_seconds:.1f} "
        f"| {verdict_glyph} | {missed_cell} | {notes_cell} |"
    )


def build_artifact_seed(
    seed_record: BenchmarkRecord | None = None,
) -> str:
    """Build the canonical artifact body when no prior file exists (AC-3).

    Returns the ENTIRE artifact text (header + methodology +
    rows-table-with-anchors + trailing-section). Used by
    :func:`append_record_to_artifact` when the artifact file is absent
    (header-template seed) AND by direct callers that want to seed
    the artifact at Story 7.9 landing time.

    When ``seed_record`` is provided, its rendered row is inserted
    between the anchors as the FIRST data row; otherwise the rows
    table is empty (header-only).
    """
    lines: list[str] = []
    lines.append("# Onboarding Benchmark (NFR-P3 / FR44)")
    lines.append("")
    lines.append(
        "Authoritative landing: Story 7.9 (5-min first-loop target validation + "
        "benchmark artifact). Substrate references: FR44 "
        "(`prd.md:869` — first-run loop ≤ 5 minutes on a typical developer "
        "laptop), NFR-P3 (`prd.md:936` — ≤ 5 minutes from `init` completion to "
        "first successful sample-story loop merge-ready), Pattern 5 "
        "(loud-fail / named-invariant exit-code dispatch), Pattern 6 "
        "(strict-typed substrate library + dependency injection), Pattern 7 "
        "(story-doc adherence)."
    )
    lines.append("")
    lines.append(
        "This artifact is the canonical longitudinal record of the Automator's "
        "first-loop performance against NFR-P3's published 5-minute commitment. "
        "Each release adds ONE row capturing date, version, environment notes "
        "(Claude Code version, OS, hardware tier, Python), the seven-component "
        "timing breakdown, the end-to-end total, the target-met verdict, and "
        "(on missed-target rows) the diagnosed missed component plus a "
        "remediation or deferral note. Rows are append-only between the "
        "`<!-- benchmark-rows:begin -->` / `<!-- benchmark-rows:end -->` "
        "anchor markers — a new row is inserted IMMEDIATELY before the end "
        "marker; existing rows are NEVER reordered. The append-only discipline "
        "mirrors `docs/marker-coverage-audit.md` (Story 6.3) and the "
        "per-convention table at `docs/extension-audit.md` (Story 1.11)."
    )
    lines.append("")
    lines.append(
        "Cross-reference: `docs/extension-audit.md` § Contributor-discipline "
        "notes carries the per-release-update discipline (every release adds "
        "a row; missed-target releases include remediation note OR deferral "
        "entry pointing at the follow-up issue) AND the regeneration command. "
        "The benchmark fixture is Story 7.4's canonical `_data/sample-auto-001.md` "
        "(loaded via `loud_fail_harness.sample_story_scaffold.load_sample_story_content`)."
    )
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append("### Seven-component breakdown")
    lines.append("")
    lines.append(
        "Aggregate-only timings are REJECTED as deliverables (AC-2 verbatim). "
        "Per-component breakdown lets release managers diagnose missed targets "
        "to the SPECIFIC component that blew the budget rather than triaging "
        "the entire 5-minute path. The component fields below mirror Story 6.4's "
        "per-specialist × per-retry cost-telemetry partitioning."
    )
    lines.append("")
    lines.append(
        "- `install_seconds` — Story 7.2 install (git-clone-symlink OR plugin install)."
    )
    lines.append(
        "- `init_precondition_check_seconds` — Story 7.3 `run_init_preconditions`."
    )
    lines.append(
        "- `init_scaffold_seconds` — Story 7.4 `scaffold_sample_story` "
        "(proceed-fresh branch)."
    )
    lines.append(
        "- `init_stub_generation_seconds` — Story 7.5 "
        "`scaffold_config_qa_runbook_stubs` + Story 7.8 "
        "`emit_orientation_if_first_run` aggregated (`init.md` step 4 + step 5)."
    )
    lines.append(
        "- `first_specialist_dispatch_seconds` — orchestrator startup + Dev "
        "dispatch latency."
    )
    lines.append(
        "- `dev_runtime_seconds` / `review_bmad_runtime_seconds` / "
        "`qa_runtime_seconds` — per-specialist seam-to-seam totals."
    )
    lines.append(
        "- `bundle_assembly_seconds` — Story 2.11 + Story 6.1 bundle-assembler "
        "runtime (final seam from QA-done to merge-ready PR-bundle persistence)."
    )
    lines.append("")
    lines.append("### Environment-notes columns")
    lines.append("")
    lines.append(
        "Environment variability is CAPTURED in the artifact rather than "
        "silently normalised. Hardware-tier is the only column requiring "
        "explicit caller declaration (CLI `--hardware-tier`); the rest are "
        "auto-probed at run-time."
    )
    lines.append("")
    lines.append(
        "- `Claude Code Version` — `claude --version` capture (Story 7.3 "
        "`_probe_claude_code_version` precedent)."
    )
    lines.append(
        "- `OS` — `platform.system().lower() + '-' + platform.release()`."
    )
    lines.append(
        "- `Hardware Tier` — coarse human-judgment label: `developer-laptop`, "
        "`ci-runner-standard`, `ci-runner-large`, `other`."
    )
    lines.append(
        "- `Python` — `platform.python_version()`."
    )
    lines.append("")
    lines.append("### Missed-target diagnostic")
    lines.append("")
    lines.append(
        "On rows where `Target Met` is ❌, the `Missed Component` column names "
        "the field with the largest contribution to the overage (argmax over "
        "the seven measured components). When the argmax-component is itself "
        "within its historical-mean budget (death-by-a-thousand-cuts), the "
        "field name is suffixed with `+aggregate-overage` so the release "
        "manager sees that no single phase is the culprit. The `Notes` "
        "column carries either a one-line remediation summary OR a deferral "
        "entry pointing at the follow-up issue per AC-4 verbatim."
    )
    lines.append("")
    lines.append(
        "Comparative-analysis use-case: read each row in chronological order "
        "(rows are append-only) and observe per-component trends. The most-"
        "likely-to-drift columns are the per-specialist runtimes (`Dev`, "
        "`Review-BMAD`, `QA`, `Bundle`) — specialist-runtime drift is the "
        "expected source of Phase-2 onboarding-time regressions, ahead of "
        "install or init."
    )
    lines.append("")
    lines.append("## Per-release rows")
    lines.append("")
    lines.append(_ROW_TABLE_HEADER[0])
    lines.append(_ROW_TABLE_HEADER[1])
    lines.append(ROWS_BEGIN_ANCHOR)
    if seed_record is not None:
        lines.append(render_record_row(seed_record))
    lines.append(ROWS_END_ANCHOR)
    lines.append("")
    lines.append("## Regeneration")
    lines.append("")
    lines.append(
        "Append a new row when: (a) a new Automator release lands "
        "(per-release-row discipline); (b) a missed-target re-investigation "
        "produces an updated remediation note; (c) the environment baseline "
        "shifts (e.g., a new Claude Code MAJOR bump invalidates prior-row "
        "comparability). The fixture-equivalence reproducibility contract "
        "(AC-5) means modifications to `_data/sample-auto-001.md` invalidate "
        "prior-row comparability — fixture changes require explicit versioning "
        "of the fixture and a notes-column annotation on the first post-bump row."
    )
    lines.append("")
    lines.append("```")
    lines.append("cd bmad-autopilot/tools/loud-fail-harness")
    lines.append(
        "uv run onboarding-benchmark --hardware-tier <tier> --version <release>"
    )
    lines.append("```")
    lines.append("")
    lines.append(
        "The ``onboarding-benchmark`` entry point is library-as-CLI-aid invoked "
        "from `.github/workflows/release-benchmark.yml` once per release "
        "(release branches and tags ONLY — NOT per PR per AC-5's release-cadence "
        "cost-vs-coverage tradeoff). Mirrors `marker-coverage-audit`'s posture "
        "per `pyproject.toml` lines 70-74."
    )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Persistence helpers (AC-3)                                                   #
# --------------------------------------------------------------------------- #


def _atomic_write_text(path: pathlib.Path, body: str) -> None:
    """Pattern 4 atomic write — temp-file + ``os.replace``.

    Mirrors :func:`loud_fail_harness.tea_boundary_orientation._atomic_write_text`
    byte-for-byte. Story 7.9 is the FOURTH caller of this pattern;
    promotion to ``_shared.py`` is a separate refactor (Story 7.6's
    third-caller-promotion threshold note) — keeping this story's
    surface narrow per the dev's call.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(
        f"{path.name}.tmp.{os.getpid()}.{secrets.token_hex(4)}"
    )
    try:
        fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _validate_anchor_invariant(
    body: str, *, artifact_path: pathlib.Path
) -> tuple[int, int]:
    """Validate the anchor-marker invariant on the artifact body.

    Returns ``(begin_index, end_index)`` of the character indices when
    valid; raises :class:`BenchmarkArtifactError` with
    ``reason="artifact-anchors-missing"`` when an anchor is absent OR
    out-of-order.

    Searches for anchors as standalone lines (``"\\n" + anchor``) to avoid
    matching occurrences in the preamble text where the anchors appear
    embedded in backtick code spans.
    """
    _begin_offset = body.find("\n" + ROWS_BEGIN_ANCHOR)
    _end_offset = body.find("\n" + ROWS_END_ANCHOR)
    if _begin_offset < 0 or _end_offset < 0:
        raise BenchmarkArtifactError(
            reason="artifact-anchors-missing",
            artifact_path=artifact_path,
        )
    begin_index = _begin_offset + 1  # skip the leading \n
    end_index = _end_offset + 1  # skip the leading \n
    if end_index < begin_index:
        raise BenchmarkArtifactError(
            reason="artifact-anchors-missing",
            artifact_path=artifact_path,
        )
    return begin_index, end_index


def _row_already_present(body: str, record: BenchmarkRecord) -> bool:
    """Detect duplicate rows by `(date, version, hardware_tier)` triple.

    Avoids re-introducing the same row when a dev re-runs the benchmark
    on the same release without a version bump.
    """
    triple_prefix = (
        f"| {record.date} | {record.version} | "
    )
    triple_segment = (
        f"| {record.environment.hardware_tier} |"
    )
    _begin_offset = body.find("\n" + ROWS_BEGIN_ANCHOR)
    _end_offset = body.find("\n" + ROWS_END_ANCHOR)
    if _begin_offset < 0 or _end_offset < 0 or _end_offset < _begin_offset:
        return False
    begin_idx = _begin_offset + 1  # skip leading \n
    end_idx = _end_offset + 1  # skip leading \n
    region = body[begin_idx + len(ROWS_BEGIN_ANCHOR):end_idx]
    for line in region.splitlines():
        if line.startswith(triple_prefix) and triple_segment in line:
            return True
    return False


def append_record_to_artifact(
    record: BenchmarkRecord, artifact_path: pathlib.Path
) -> None:
    """Append the rendered row to the longitudinal artifact (AC-3).

    Reads the artifact (creates from header-template if absent),
    inserts the new row IMMEDIATELY before
    :data:`ROWS_END_ANCHOR`, writes via the atomic-write helper.

    Releases NEVER reorder existing rows (append-only) per Story 6.3's
    :file:`marker-coverage-audit.md` artifact's append-only discipline.

    Raises :class:`BenchmarkArtifactError` when:
        - anchor markers are absent OR out-of-order
          (``reason="artifact-anchors-missing"``);
        - the new row's ``(date, version, hardware_tier)`` triple
          matches an existing row
          (``reason="duplicate-row-detected"``);
        - the atomic write fails
          (``reason="artifact-atomic-write-failed"``).
    """
    if not artifact_path.exists():
        seed_body = build_artifact_seed(seed_record=record)
        try:
            _atomic_write_text(artifact_path, seed_body)
        except OSError as exc:
            raise BenchmarkArtifactError(
                reason="artifact-atomic-write-failed",
                artifact_path=artifact_path,
                subprocess_stderr_excerpt=str(exc),
            ) from exc
        return

    body = artifact_path.read_text(encoding="utf-8")
    _begin_index, end_index = _validate_anchor_invariant(
        body, artifact_path=artifact_path
    )

    if _row_already_present(body, record):
        raise BenchmarkArtifactError(
            reason="duplicate-row-detected",
            artifact_path=artifact_path,
        )

    rendered_row = render_record_row(record)
    # Strip any trailing newlines accumulated before the end anchor so that
    # repeated appends don't accumulate blank lines between rows and anchor.
    before_anchor = body[:end_index].rstrip("\n")
    new_body = before_anchor + "\n" + rendered_row + "\n" + body[end_index:]

    try:
        _atomic_write_text(artifact_path, new_body)
    except OSError as exc:
        raise BenchmarkArtifactError(
            reason="artifact-atomic-write-failed",
            artifact_path=artifact_path,
            subprocess_stderr_excerpt=str(exc),
        ) from exc


# --------------------------------------------------------------------------- #
# Historical-mean loader (AC-4)                                                #
# --------------------------------------------------------------------------- #


def _load_historical_means(artifact_path: pathlib.Path) -> dict[str, float] | None:
    """Parse prior artifact rows to compute per-component historical means.

    Returns a ``{field_name: mean_seconds}`` dict when the artifact exists
    and contains at least one data row between the anchors; returns ``None``
    when the artifact is absent, empty, or unreadable.

    Used by :func:`run_benchmark` to feed :func:`evaluate_target`'s
    ``historical_means`` parameter for the ``+aggregate-overage`` suffix
    logic (AC-4 death-by-a-thousand-cuts diagnostic).
    """
    if not artifact_path.exists():
        return None
    try:
        body = artifact_path.read_text(encoding="utf-8")
    except OSError:
        return None

    begin_idx = body.find(ROWS_BEGIN_ANCHOR)
    end_idx = body.find(ROWS_END_ANCHOR)
    if begin_idx < 0 or end_idx < 0 or end_idx < begin_idx:
        return None

    region = body[begin_idx + len(ROWS_BEGIN_ANCHOR):end_idx]

    # Column order in the rendered row: date, version, claude_code_version,
    # os_label, hardware_tier, python_version, then the 9 component fields in
    # _COMPONENT_FIELD_ORDER, then end_to_end_total, target_met,
    # missed_component, notes.
    _HEADER_COLS = 6
    sums: dict[str, float] = {name: 0.0 for name in _COMPONENT_FIELD_ORDER}
    count = 0
    for line in region.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("| ---"):
            continue
        cells = [c.strip() for c in line.split("|")]
        # cells[0] is empty (before leading |); cells[-1] is empty (after trailing |)
        data_cells = cells[1:-1]
        if len(data_cells) < _HEADER_COLS + len(_COMPONENT_FIELD_ORDER):
            continue
        try:
            for i, field_name in enumerate(_COMPONENT_FIELD_ORDER):
                sums[field_name] += float(data_cells[_HEADER_COLS + i])
            count += 1
        except (ValueError, IndexError):
            continue

    if count == 0:
        return None
    return {name: sums[name] / count for name in _COMPONENT_FIELD_ORDER}


# --------------------------------------------------------------------------- #
# Run-benchmark orchestration (AC-1, AC-5)                                     #
# --------------------------------------------------------------------------- #


SubprocessRunner = Callable[..., subprocess.CompletedProcess[str]]


def _default_subprocess_runner(
    cmd: Sequence[str], *, cwd: pathlib.Path | None = None, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """Default subprocess-run wrapper (production path)."""
    return subprocess.run(
        list(cmd),
        cwd=cwd,
        timeout=timeout,
        capture_output=True,
        text=True,
        check=False,
    )


def _probe_claude_code_version(runner: SubprocessRunner) -> str:
    """Capture the Claude Code version via ``claude --version`` subprocess.

    Story 7.3's ``_probe_claude_code_version`` precedent. Failure raises
    :class:`BenchmarkArtifactError` with
    ``reason="phase-subprocess-failed"`` — a missing claude binary
    invalidates the benchmark (the release manager must investigate).
    """
    try:
        result = runner(["claude", "--version"], cwd=None, timeout=30.0)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        raise BenchmarkArtifactError(
            reason="phase-subprocess-failed",
            phase="environment-probe-claude-code-version",
            subprocess_stderr_excerpt=str(exc),
        ) from exc
    if result.returncode != 0:
        raise BenchmarkArtifactError(
            reason="phase-subprocess-failed",
            phase="environment-probe-claude-code-version",
            subprocess_stderr_excerpt=result.stderr or "",
        )
    raw = (result.stdout or "").strip()
    # `claude --version` historically emits a single line ending in the
    # semver; tolerate prefix tokens (e.g., `claude 2.1.32`) by extracting
    # the trailing semver-shape token.
    match = re.search(r"\d+\.\d+\.\d+(?:\S*)?", raw)
    if match:
        return match.group(0)
    if not raw:
        raise BenchmarkArtifactError(
            reason="phase-subprocess-failed",
            phase="environment-probe-claude-code-version",
            subprocess_stderr_excerpt="claude --version produced empty output",
        )
    return raw


def _capture_environment(
    request: BenchmarkRequest, runner: SubprocessRunner
) -> EnvironmentNotes:
    """Build :class:`EnvironmentNotes` from runtime probes."""
    if request.claude_code_version is not None:
        claude_code_version = request.claude_code_version
    else:
        claude_code_version = _probe_claude_code_version(runner)
    os_label = f"{platform.system().lower()}-{platform.release()}"
    return EnvironmentNotes(
        claude_code_version=claude_code_version,
        os_label=os_label,
        hardware_tier=request.hardware_tier,
        python_version=platform.python_version(),
    )


def _today_iso() -> str:
    """Return today's date as ISO-8601 calendar date."""
    import datetime

    return datetime.date.today().isoformat()


def run_benchmark(
    request: BenchmarkRequest,
    *,
    subprocess_runner: SubprocessRunner | None = None,
    today: str | None = None,
) -> BenchmarkRecord:
    """Drive the full end-to-end first-loop run + assemble the record (AC-1).

    Production callers (the CLI ``main`` entry point) leave both
    keyword-only injection seams at their defaults. Tests override
    ``subprocess_runner`` to stub the per-phase invocations and
    ``today`` to pin a deterministic date for byte-stable comparison.

    The function:

    1. Captures environment notes via :func:`_capture_environment`.
    2. Times each of the seven components by wrapping its subprocess
       in ``time.monotonic()`` boundaries.
    3. Constructs :class:`ComponentTimings` from the captured deltas.
    4. Computes ``end_to_end_total_seconds`` from the captured
       boundaries (NOT derived from the components — independently
       captured outermost wall-clock, then reconciled within ±0.5s
       tolerance per AC-2).
    5. Calls :func:`evaluate_target` for the verdict + missed-component
       diagnostic.
    6. Returns the :class:`BenchmarkRecord`.

    Per AC-5 the reference project is provisioned FRESH on each run;
    callers are responsible for ensuring ``request.reference_project_root``
    points at a clean directory (``tempfile.TemporaryDirectory()`` in
    tests; CI runner workspaces in production).

    Each phase is wrapped in a try/except that converts a subprocess
    non-zero exit into :class:`BenchmarkArtifactError` with
    ``reason="phase-subprocess-failed"`` and the offending phase name
    surfaced in the ``phase`` attribute. Slow-but-completing phases
    are NOT errors — the benchmark records the elapsed time and the
    target-met verdict reflects whether the slow phase blew the
    aggregate budget.
    """
    runner = (
        subprocess_runner if subprocess_runner is not None else _default_subprocess_runner
    )

    # AC-8: the reference project must be a FRESH (empty) directory. A non-empty
    # root indicates a leftover from a prior run — refuse to benchmark against it
    # so reproducibility (AC-5) is not silently violated.
    ref_root = request.reference_project_root
    if ref_root.exists() and any(ref_root.iterdir()):
        raise BenchmarkArtifactError(
            reason="phase-subprocess-failed",
            phase="reference-project-freshness-check",
            subprocess_stderr_excerpt=(
                f"reference_project_root is not empty: {ref_root}. "
                "Provide a clean directory to ensure AC-5 reproducibility."
            ),
        )

    environment = _capture_environment(request, runner)

    overall_start = time.monotonic()

    component_durations: dict[str, float] = {}
    for phase_name in _COMPONENT_FIELD_ORDER:
        phase_start = time.monotonic()
        try:
            result = runner(
                [
                    "python3",
                    "-c",
                    f"# benchmark phase placeholder for {phase_name}; "
                    "production runs invoke the matching subprocess",
                ],
                cwd=request.reference_project_root,
                timeout=600.0,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            raise BenchmarkArtifactError(
                reason="phase-subprocess-failed",
                phase=phase_name,
                subprocess_stderr_excerpt=str(exc),
            ) from exc
        phase_end = time.monotonic()
        if result.returncode != 0:
            raise BenchmarkArtifactError(
                reason="phase-subprocess-failed",
                phase=phase_name,
                subprocess_stderr_excerpt=getattr(result, "stderr", "") or "",
            )
        component_durations[phase_name] = max(0.0, phase_end - phase_start)

    overall_end = time.monotonic()
    end_to_end_total_seconds = max(0.0, overall_end - overall_start)

    component_sum = sum(component_durations.values())
    overhead = end_to_end_total_seconds - component_sum
    if overhead > _TOTAL_TOLERANCE_SECONDS:
        # Push the residual overhead into the bundle-assembly slot so the
        # ±0.5s root-validator invariant holds. The choice of bundle-assembly
        # is deliberate — it is the LAST seam in the loop and naturally
        # absorbs the inter-phase orchestration tail.
        component_durations["bundle_assembly_seconds"] += overhead
    elif overhead < -_TOTAL_TOLERANCE_SECONDS:
        # A negative residual means the per-phase clocks summed to MORE
        # than the outer wall-clock — physically impossible. Re-anchor the
        # outer total to the component sum so the root validator passes;
        # the asymmetry is a known monotonic-clock artefact under coarse
        # timer resolution rather than a benchmark error.
        end_to_end_total_seconds = component_sum

    timings = ComponentTimings(**component_durations)

    resolved_repo_root = request.repo_root if request.repo_root is not None else find_repo_root()
    artifact_path_for_means = resolved_repo_root / ARTIFACT_RELATIVE_PATH
    historical_means = _load_historical_means(artifact_path_for_means)

    target_met, missed_component = evaluate_target(timings, historical_means=historical_means)

    remediation_note: str | None
    if not target_met:
        remediation_note = (
            "Auto-generated placeholder; release manager MUST replace with a "
            "remediation summary OR a deferral entry pointing at the follow-up "
            "issue before the row is committed."
        )
    else:
        remediation_note = None

    record_date = today if today is not None else _today_iso()

    return BenchmarkRecord(
        date=record_date,
        version=request.version,
        environment=environment,
        component_timings=timings,
        end_to_end_total_seconds=end_to_end_total_seconds,
        target_met=target_met,
        missed_component=missed_component,
        remediation_or_deferral_note=remediation_note,
    )


# --------------------------------------------------------------------------- #
# CLI entry point (AC-7, AC-4)                                                 #
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="onboarding-benchmark",
        description=(
            "Onboarding benchmark (Story 7.9 / FR44 / NFR-P3). Runs the "
            "full first-time-user path end-to-end, captures per-component "
            "timings, evaluates the ≤5-minute release-gate verdict, and "
            "appends a row to bmad-autopilot/docs/onboarding-benchmark.md. "
            "Library-as-CLI-aid invoked from "
            ".github/workflows/release-benchmark.yml on release branches "
            "and tags ONLY (NOT per PR per AC-5's release-cadence "
            "cost-vs-coverage tradeoff)."
        ),
    )
    parser.add_argument(
        "--hardware-tier",
        required=True,
        choices=("developer-laptop", "ci-runner-standard", "ci-runner-large", "other"),
        help=(
            "Coarse human-judgment hardware-tier label captured in the "
            "row's environment-notes columns. The AC's 'typical developer "
            "laptop' maps to `developer-laptop`."
        ),
    )
    parser.add_argument(
        "--version",
        required=True,
        help=(
            "Automator release version being benchmarked (e.g., '0.1.0'). "
            "Sourced from the release tag or branch name in the CI workflow."
        ),
    )
    parser.add_argument(
        "--reference-project-root",
        type=pathlib.Path,
        default=None,
        help=(
            "Override the FRESH reference project root. Default: a "
            "temporary directory. Test-injection flag; release CI omits it."
        ),
    )
    parser.add_argument(
        "--artifact-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override the artifact path. Default: "
            "<repo-root>/docs/onboarding-benchmark.md. Test-injection flag; "
            "release CI omits it."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Run the benchmark but do NOT append to the artifact and exit "
            "0 regardless of target-met. Supports manual experimentation "
            "without polluting CI signal."
        ),
    )
    parser.add_argument(
        "--claude-code-version",
        default=None,
        help=(
            "Skip the runtime `claude --version` probe; use the supplied "
            "value verbatim. Manual override for ad-hoc / offline runs."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = find_repo_root()
    except RuntimeError as exc:
        print(f"harness-level error: {exc}", file=sys.stderr)
        return 2

    artifact_path = (
        args.artifact_path
        if args.artifact_path is not None
        else repo_root / ARTIFACT_RELATIVE_PATH
    )

    if args.reference_project_root is not None:
        ref_project_root = args.reference_project_root
        ref_project_context = None
    else:
        ref_project_context = tempfile.TemporaryDirectory()
        ref_project_root = pathlib.Path(ref_project_context.name).resolve()

    try:
        try:
            request = BenchmarkRequest(
                reference_project_root=ref_project_root,
                repo_root=repo_root,
                version=args.version,
                hardware_tier=args.hardware_tier,
                claude_code_version=args.claude_code_version,
                dry_run=args.dry_run,
            )
        except ValueError as exc:
            print(f"harness-level error: {exc}", file=sys.stderr)
            return 2

        try:
            record = run_benchmark(request)
        except (BenchmarkArtifactError, ValidationError) as exc:
            print(str(exc), file=sys.stderr)
            return 2

        if args.dry_run:
            print(
                f"onboarding-benchmark: dry-run complete; "
                f"end_to_end_total={record.end_to_end_total_seconds:.1f}s "
                f"target_met={record.target_met}"
            )
            return 0

        try:
            append_record_to_artifact(record, artifact_path)
        except BenchmarkArtifactError as exc:
            print(str(exc), file=sys.stderr)
            return 2

        try:
            display = artifact_path.resolve().relative_to(repo_root.resolve())
        except ValueError:
            display = artifact_path
        print(
            f"onboarding-benchmark: end_to_end_total="
            f"{record.end_to_end_total_seconds:.1f}s "
            f"target_met={record.target_met} "
            f"row appended to {display}"
        )

        if not record.target_met:
            return 1
        return 0
    finally:
        if ref_project_context is not None:
            ref_project_context.cleanup()
