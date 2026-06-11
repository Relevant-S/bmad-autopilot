"""Story 19.5 — Visual-regression delta engine + Pattern-5 emission helpers.

The pure-library substrate owning the visual-regression snapshotting primitives
the QA specialist composes on the web-AND-mobile opt-in path (FR-P2-10 /
ADR-012): the pixelmatch result-parse model, per-AC baseline load/create, the
self-computed mismatched-pixel-ratio delta (pixelmatch ships NO baseline
lifecycle — the load-bearing ADR-012 finding, the same as ADR-011 for
axe-core), the configurable-threshold compare, the dimension-mismatch fold, and
the two ``visual-regression-*`` marker emission helpers.

This is a COMBINED activation+integration story (no 19.3<->19.4-style split):
ADR-012 freezes the tool (pixelmatch, ISC, ``version_floor "7.2"``), the
``dependencies.yaml`` entry, and the two marker classes
(``visual-regression-delta-exceeded`` / ``visual-regression-baseline-missing``;
marker-taxonomy ``1.15``) AND THIS module consumes those classes AS-IS via
:func:`validate_marker_emission` and wires emission, all in one commit.

Mirrors :mod:`qa_a11y_audit` byte-for-byte in shape (it is the immediate twin),
with two domain differences: (1) pixel-diff over two equal-dimension PNGs is
DETERMINISTIC, so there is NO ``-mode-unstable`` third marker — the
non-deterministic-delta escape valve a11y needed does not arise; (2) the one
structural edge — a dimension mismatch between baseline and current (pixelmatch
requires equal dimensions) — FOLDS into ``visual-regression-delta-exceeded`` (a
changed render size IS a visual regression; the strictest defensible reading).

Pattern 5 (atomic-on-failure) at the two ``surface_visual_regression_*`` helpers
mirrors :func:`qa_a11y_audit.surface_a11y_baseline_stale` byte-for-byte: the
runtime registry is validated FIRST; on rejection :exc:`UnknownMarkerClass`
propagates with NO partial state constructed.

Sensor-not-advisor: a fired ``visual-regression-*`` marker SURFACES regression
evidence for the human; it does NOT flip an AC's pass/fail verdict (the visual
delta is story-level evidence, exactly as a11y deltas are). Flow policy lives in
the orchestrator, never here.
"""

from __future__ import annotations

import json
import pathlib
from typing import Final, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loud_fail_harness.input_hardening import harden_identifier, harden_path_segment
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

# --------------------------------------------------------------------------- #
# Symbolic constants                                                          #
# --------------------------------------------------------------------------- #

#: The two canonical visual-regression marker class identifiers, consumed AS-IS
#: from ``schemas/marker-taxonomy.yaml`` (Story 19.5 enumeration; ``1.15``).
#: THIS module is the runtime emitter (no activation/integration split). Mirrors
#: the :data:`qa_a11y_audit.A11Y_BASELINE_STALE_MARKER` constant pattern.
VISUAL_REGRESSION_DELTA_EXCEEDED_MARKER: Final[
    Literal["visual-regression-delta-exceeded"]
] = "visual-regression-delta-exceeded"
VISUAL_REGRESSION_BASELINE_MISSING_MARKER: Final[
    Literal["visual-regression-baseline-missing"]
] = "visual-regression-baseline-missing"

#: The per-AC baseline-storage root (gitignored by default; a maintainer-curated
#: ``committed`` option is exposed via ``qa-runbook.visual_regression.baseline_storage``).
#: Baselines live under ``_bmad-output/qa-visual-baseline/{story-id}/{ac-id}/baseline.png``.
VISUAL_BASELINE_ROOT: Final[str] = "_bmad-output/qa-visual-baseline"
BASELINE_FILENAME: Final[str] = "baseline.png"

#: The 8-byte PNG file signature. A stored baseline whose leading bytes do not
#: match is treated as corrupt -> :func:`load_baseline` returns ``None`` (the
#: safe baseline-missing + fresh-anchor path; the 19.4 F2 corrupt-read lesson).
_PNG_SIGNATURE: Final[bytes] = b"\x89PNG\r\n\x1a\n"

#: The default visual delta threshold (``qa-runbook.visual_regression.delta_threshold``).
#: ``0.0`` means "any mismatched-pixel ratio beyond pixelmatch's anti-aliasing +
#: color tolerance is a regression" — the strictest, most defensible default for
#: the opt-in posture (consistent with the a11y ``delta_threshold: 0`` framing).
DEFAULT_DELTA_THRESHOLD: Final[float] = 0.0

#: The closed set of audit modes :func:`decide_visual_regression_mode` resolves.
#: Two map to a marker emission; ``delta-within-threshold`` is the silent
#: within-budget arm. There is NO ``-mode-unstable`` arm (pixel-diff is
#: deterministic), unlike :data:`qa_a11y_audit.A11yAuditMode`.
VisualRegressionMode = Literal[
    "baseline-missing",
    "delta-exceeded",
    "delta-within-threshold",
]


# --------------------------------------------------------------------------- #
# Externally-constructed parse model (pixelmatch result ingress)              #
# --------------------------------------------------------------------------- #


class VisualDiffResult(BaseModel):
    """One pixelmatch comparison result — the ``{ mismatched_pixels, width,
    height }`` the diff engine returns for a single (baseline, current) pair.

    Constructed from the tool-supplied pixelmatch output (therefore
    ``externally_constructed`` per the Story 24.2 input-hardening registry). The
    fields are numeric, so they carry NO string hostile-input surface — they are
    range-hardened via ``Field(ge=0)`` / ``Field(gt=0)`` constraints plus the
    ``mismatched_pixels <= total_pixels`` invariant below (a corrupt count that
    exceeds the pixel area is rejected at construction).

    Frozen for determinism. Field declaration order is load-bearing for
    byte-stable ``model_dump_json()``.
    """

    model_config = ConfigDict(frozen=True)

    mismatched_pixels: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @model_validator(mode="after")
    def _harden_numeric_invariant(self) -> "VisualDiffResult":
        if self.mismatched_pixels > self.total_pixels:
            raise ValueError(
                "VisualDiffResult.mismatched_pixels must not exceed total_pixels "
                f"({self.width}x{self.height}={self.total_pixels}); "
                f"got {self.mismatched_pixels}"
            )
        return self

    @property
    def total_pixels(self) -> int:
        return self.width * self.height

    @property
    def ratio(self) -> float:
        return self.mismatched_pixels / self.total_pixels


# --------------------------------------------------------------------------- #
# Pure computation result carriers (NamedTuple — not BaseModel, no I/O)       #
# --------------------------------------------------------------------------- #


class VisualRegressionDelta(NamedTuple):
    """The result of :func:`compute_delta`: the mismatched-pixel ratio and
    whether it exceeds the configurable threshold."""

    mismatched_pixels: int
    total_pixels: int
    ratio: float
    exceeded: bool


class VisualRegressionDecision(NamedTuple):
    """The result of :func:`decide_visual_regression_mode`: which audit arm fired
    plus the computed delta (``None`` for the baseline-missing and the
    dimension-mismatch arms, where no ratio is computed)."""

    mode: VisualRegressionMode
    delta: VisualRegressionDelta | None


# --------------------------------------------------------------------------- #
# Diagnostic context (co-exposed on the emissions; externally_constructed)    #
# --------------------------------------------------------------------------- #


class VisualRegressionDiagnosticContext(BaseModel):
    """The diagnostic context co-exposed on both visual-regression emissions
    (``visual-regression-delta-exceeded`` / ``visual-regression-baseline-missing``;
    BOTH AC-scoped — there is no envelope-scoped class, so a single context
    suffices, unlike a11y's Ac/Run split).

    Mirrors :class:`qa_a11y_audit.A11yAcScopedDiagnosticContext`: frozen for
    determinism; field order load-bearing for byte-stable ``model_dump_json()``.
    ``story_id`` is the raw external-ingress identifier; ``ac_id`` is supplied by
    the wrapper from the dispatch ``ac_list`` — both are hardened defensively.
    """

    model_config = ConfigDict(frozen=True)

    story_id: str = Field(min_length=1)
    ac_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _harden_identifier_inputs(self) -> "VisualRegressionDiagnosticContext":
        harden_identifier(self.story_id, "VisualRegressionDiagnosticContext.story_id")
        harden_identifier(self.ac_id, "VisualRegressionDiagnosticContext.ac_id")
        return self


# --------------------------------------------------------------------------- #
# Emission records (the envelope-bound `visual_regression_emissions[]` shape)  #
# --------------------------------------------------------------------------- #


class VisualRegressionDeltaExceededEmissionRecord(BaseModel):
    """One ``visual-regression-delta-exceeded`` emission record. Byte-mirrors the
    envelope ``$defs/visual_regression_emission`` AC-scoped shape (``marker_class``
    + ``ac_id``). Frozen + field-order-load-bearing for byte-stable
    ``model_dump_json()``."""

    model_config = ConfigDict(frozen=True)

    marker_class: Literal["visual-regression-delta-exceeded"]
    ac_id: str = Field(min_length=1)


class VisualRegressionBaselineMissingEmissionRecord(BaseModel):
    """One ``visual-regression-baseline-missing`` emission record. Byte-mirrors
    the envelope ``$defs/visual_regression_emission`` AC-scoped shape
    (``marker_class`` + ``ac_id``)."""

    model_config = ConfigDict(frozen=True)

    marker_class: Literal["visual-regression-baseline-missing"]
    ac_id: str = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Emission wrappers (atomic-emission return shape; co-expose the context)     #
# --------------------------------------------------------------------------- #


class VisualRegressionDeltaExceededEmission(BaseModel):
    """The atomic-emission return shape of
    :func:`surface_visual_regression_delta_exceeded`. Mirrors
    :class:`qa_a11y_audit.A11yDeltaExceededEmission` — co-exposes the diagnostic
    context alongside the marker record."""

    model_config = ConfigDict(frozen=True)

    marker_record: VisualRegressionDeltaExceededEmissionRecord
    diagnostic_context: VisualRegressionDiagnosticContext


class VisualRegressionBaselineMissingEmission(BaseModel):
    """The atomic-emission return shape of
    :func:`surface_visual_regression_baseline_missing`."""

    model_config = ConfigDict(frozen=True)

    marker_record: VisualRegressionBaselineMissingEmissionRecord
    diagnostic_context: VisualRegressionDiagnosticContext


# --------------------------------------------------------------------------- #
# Baseline path + load/store                                                  #
# --------------------------------------------------------------------------- #


def compute_baseline_dir(story_id: str, ac_id: str) -> pathlib.Path:
    """Return the per-AC baseline dir
    ``_bmad-output/qa-visual-baseline/{story-id}/{ac-id}``.

    Mirrors :func:`qa_a11y_audit.compute_baseline_dir`; ``story_id`` / ``ac_id``
    are hardened as path segments (rejecting separators / ``..`` traversal) so a
    malformed identifier cannot compose a path outside the baseline umbrella.
    Returns a concrete :class:`pathlib.Path` (not ``PurePosixPath``) so callers
    can pass it directly to :func:`load_baseline` and :func:`store_baseline`.
    """
    harden_path_segment(story_id, "compute_baseline_dir.story_id")
    harden_path_segment(ac_id, "compute_baseline_dir.ac_id")
    return pathlib.Path(VISUAL_BASELINE_ROOT) / story_id / ac_id


def load_baseline(baseline_dir: pathlib.Path) -> pathlib.Path | None:
    """Return the stored baseline PNG path for an AC, or ``None`` when no prior
    baseline exists or the baseline file is unreadable / corrupt.

    A baseline whose leading bytes are not the PNG signature (a truncated /
    corrupted / non-PNG file) is treated as absent: returning ``None`` triggers
    the safe baseline-missing path (fresh anchor created +
    ``visual-regression-baseline-missing`` emitted) rather than feeding a corrupt
    image into the diff (the 19.4 F2 corrupt-read lesson).
    """
    baseline_file = baseline_dir / BASELINE_FILENAME
    if not baseline_file.exists():
        return None
    try:
        header = baseline_file.read_bytes()[: len(_PNG_SIGNATURE)]
    except OSError:
        return None
    if header != _PNG_SIGNATURE:
        return None
    return baseline_file


def store_baseline(baseline_dir: pathlib.Path, png_bytes: bytes) -> pathlib.Path:
    """Write ``png_bytes`` as the new baseline anchor (AC-4), creating the per-AC
    baseline dir. Returns the written ``baseline.png`` path."""
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline_file = baseline_dir / BASELINE_FILENAME
    baseline_file.write_bytes(png_bytes)
    return baseline_file


# --------------------------------------------------------------------------- #
# Self-computed mismatched-pixel-ratio delta + threshold + mode decision      #
# --------------------------------------------------------------------------- #


def compute_delta(
    diff: VisualDiffResult,
    threshold: float = DEFAULT_DELTA_THRESHOLD,
) -> VisualRegressionDelta:
    """Compute the self-computed visual delta: the mismatched-pixel ratio
    (``mismatched_pixels / total_pixels``) and whether it exceeds ``threshold``.

    pixelmatch returns a raw mismatched-pixel count for ONE comparison; it has no
    baseline lifecycle, no ratio, no threshold policy (the load-bearing ADR-012
    finding) — THIS is where the Automator computes the ratio over the
    deterministic count.
    """
    if threshold < 0 or threshold > 1.0:
        raise ValueError(
            f"delta threshold must be in [0.0, 1.0]; got {threshold}"
        )
    ratio = diff.ratio
    return VisualRegressionDelta(
        mismatched_pixels=diff.mismatched_pixels,
        total_pixels=diff.total_pixels,
        ratio=ratio,
        exceeded=ratio > threshold,
    )


def decide_visual_regression_mode(
    *,
    baseline_present: bool,
    diff: VisualDiffResult | None,
    threshold: float = DEFAULT_DELTA_THRESHOLD,
) -> VisualRegressionDecision:
    """Resolve which visual-regression audit arm fires for this run.

    The ``diff`` argument carries the dimension-mismatch signal: when a baseline
    IS present but the current screenshot's dimensions differ from it, pixelmatch
    cannot run (it requires equal dimensions), so the wrapper passes ``diff=None``
    to signal the mismatch.

    Precedence:
      1. no prior baseline -> ``baseline-missing`` (anchor created; AC-4).
      2. baseline present, ``diff is None`` (dimension mismatch) ->
         ``delta-exceeded`` (a changed render size IS a regression; the dimension
         change is recorded in the diff artifact — the strictest defensible
         interpretation; folds the structural edge rather than adding a marker).
      3. baseline present, ``diff`` present -> ``delta-exceeded`` when the ratio
         exceeds ``threshold``, else ``delta-within-threshold``.
    """
    if not baseline_present:
        return VisualRegressionDecision(mode="baseline-missing", delta=None)
    if diff is None:
        return VisualRegressionDecision(mode="delta-exceeded", delta=None)
    delta = compute_delta(diff, threshold)
    mode: VisualRegressionMode = (
        "delta-exceeded" if delta.exceeded else "delta-within-threshold"
    )
    return VisualRegressionDecision(mode=mode, delta=delta)


def serialize_delta_artifact(
    *,
    diff: VisualDiffResult | None,
    baseline_width: int,
    baseline_height: int,
    current_width: int,
    current_height: int,
    threshold: float = DEFAULT_DELTA_THRESHOLD,
    diff_image_path: str | None = None,
) -> str:
    """Serialize the delta evidence artifact (ratio + counts + dimensions + the
    diff-image path) the ``visual-regression-delta-exceeded`` marker's
    ``diagnostic_pointer`` directs the operator to (AC-3).

    Handles BOTH branches: a ratio-overage (``diff`` present) and a
    dimension-mismatch (``diff is None`` — a changed render size; ``exceeded`` is
    unconditionally ``True`` and the per-pixel counts are ``null`` because
    pixelmatch could not run over unequal dimensions).
    """
    dimension_mismatch = (baseline_width, baseline_height) != (
        current_width,
        current_height,
    )
    if diff is not None and dimension_mismatch:
        raise ValueError(
            "serialize_delta_artifact: pass diff=None when dimensions mismatch "
            f"(baseline {baseline_width}x{baseline_height} vs current "
            f"{current_width}x{current_height}); pixelmatch cannot run over "
            "unequal dimensions — the dimension mismatch IS the exceeded signal"
        )
    if diff is not None:
        delta = compute_delta(diff, threshold)
        mismatched_pixels: int | None = delta.mismatched_pixels
        total_pixels: int | None = delta.total_pixels
        ratio: float | None = delta.ratio
        exceeded = delta.exceeded
    else:
        mismatched_pixels = None
        total_pixels = None
        ratio = None
        exceeded = True
    payload = {
        "baseline_width": baseline_width,
        "baseline_height": baseline_height,
        "current_width": current_width,
        "current_height": current_height,
        "dimension_mismatch": dimension_mismatch,
        "mismatched_pixels": mismatched_pixels,
        "total_pixels": total_pixels,
        "ratio": ratio,
        "threshold": threshold,
        "exceeded": exceeded,
        "diff_image_path": diff_image_path,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


# --------------------------------------------------------------------------- #
# Pattern-5 atomic-on-failure emission helpers                                #
# --------------------------------------------------------------------------- #


def surface_visual_regression_delta_exceeded(
    story_id: str,
    ac_id: str,
    registry: MarkerClassRegistry,
) -> VisualRegressionDeltaExceededEmission:
    """Atomic-on-failure ``visual-regression-delta-exceeded`` emission helper.

    Mirrors :func:`qa_a11y_audit.surface_a11y_delta_exceeded` AS-IS:
    :func:`validate_marker_emission` runs FIRST; on registry rejection
    :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass` propagates
    per Pattern 5 BEFORE any partial state is constructed.

    Pure: no file I/O, no orchestrator-event log write — the emission record is
    data the wrapper rides on the envelope's ``visual_regression_emissions``
    array; the bundle assembler renders the marker comment. Sensor-not-advisor:
    surfaces the regression for the human; does NOT auto-fail the AC.

    Raises:
        UnknownMarkerClass: registry does not contain
            ``"visual-regression-delta-exceeded"``.
    """
    validate_marker_emission(registry, VISUAL_REGRESSION_DELTA_EXCEEDED_MARKER)
    diagnostic_context = VisualRegressionDiagnosticContext(
        story_id=story_id, ac_id=ac_id
    )
    marker_record = VisualRegressionDeltaExceededEmissionRecord(
        marker_class=VISUAL_REGRESSION_DELTA_EXCEEDED_MARKER,
        ac_id=ac_id,
    )
    return VisualRegressionDeltaExceededEmission(
        marker_record=marker_record,
        diagnostic_context=diagnostic_context,
    )


def surface_visual_regression_baseline_missing(
    story_id: str,
    ac_id: str,
    registry: MarkerClassRegistry,
) -> VisualRegressionBaselineMissingEmission:
    """Atomic-on-failure ``visual-regression-baseline-missing`` (informational)
    emission helper.

    Mirrors :func:`surface_visual_regression_delta_exceeded`. Distinct from
    delta-exceeded by remediation, not by behavior: no stored baseline existed
    for this AC's captured surface, so the audit created a NEW baseline from this
    run's screenshot and has nothing to compare against yet (covers both a
    genuine first run AND a subsequent run whose baseline was deleted/relocated —
    the substrate cannot distinguish them; the operator reads the marker and
    decides whether the fresh anchor is expected).

    Raises:
        UnknownMarkerClass: registry does not contain
            ``"visual-regression-baseline-missing"``.
    """
    validate_marker_emission(registry, VISUAL_REGRESSION_BASELINE_MISSING_MARKER)
    diagnostic_context = VisualRegressionDiagnosticContext(
        story_id=story_id, ac_id=ac_id
    )
    marker_record = VisualRegressionBaselineMissingEmissionRecord(
        marker_class=VISUAL_REGRESSION_BASELINE_MISSING_MARKER,
        ac_id=ac_id,
    )
    return VisualRegressionBaselineMissingEmission(
        marker_record=marker_record,
        diagnostic_context=diagnostic_context,
    )


__all__ = [
    "VISUAL_BASELINE_ROOT",
    "VISUAL_REGRESSION_BASELINE_MISSING_MARKER",
    "VISUAL_REGRESSION_DELTA_EXCEEDED_MARKER",
    "BASELINE_FILENAME",
    "DEFAULT_DELTA_THRESHOLD",
    "VisualRegressionMode",
    "VisualDiffResult",
    "VisualRegressionDelta",
    "VisualRegressionDecision",
    "VisualRegressionDiagnosticContext",
    "VisualRegressionDeltaExceededEmissionRecord",
    "VisualRegressionBaselineMissingEmissionRecord",
    "VisualRegressionDeltaExceededEmission",
    "VisualRegressionBaselineMissingEmission",
    "compute_baseline_dir",
    "load_baseline",
    "store_baseline",
    "compute_delta",
    "decide_visual_regression_mode",
    "serialize_delta_artifact",
    "surface_visual_regression_delta_exceeded",
    "surface_visual_regression_baseline_missing",
]
