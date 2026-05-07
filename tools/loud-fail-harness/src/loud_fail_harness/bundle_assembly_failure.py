"""Bundle-assembly failure three-channel atomic emission (Story 6.9).

Architectural placement (Story 3.3's ``review_layer_failure.py`` precedent +
Story 6.7's ``marker_wiring.record_marker_with_context`` consumer):
this module is a **substrate library NOT a sixth substrate component**.
ADR-003 Consequence 1 enumerates exactly five substrate components
(``architecture.md`` lines 311-315); this module is a substrate **library**
(sibling of ``review_layer_failure.py`` / ``marker_wiring.py`` /
``cost_telemetry.py`` / ``cost_streaming.py`` / ``evidence_linkability.py``)
consumed exclusively by :mod:`loud_fail_harness.bundle_assembly`'s ``main``
entry-point — the orchestrator-side seam that wraps the assembler in
failure-detection logic.

What this library provides:
    * **Single source-of-truth function** :func:`surface_assembly_failure`
      — the ONLY emission path for the three-channel projection of a
      bundle-assembly logical failure (FR59 + NFR-O5). The function's
      atomicity is enforced as a code-structure invariant via the
      Story 6.9 CI lint
      :mod:`loud_fail_harness.bundle_assembly_failure_emission_gate`;
      no developer can emit one channel without the other two.

The three-channel atomic emission contract (Story 6.9 AC-1 + AC-4):

    1. **Channel 1 — Fallback diagnostic file (always)**.
       Written to ``<bundle_root>/<story_id>/<run_id>.assembly-failure.log``
       with structured-text content (header ``=== bundle-assembly-failed ===``,
       ``story_id``, ``run_id``, ``failed_step``, ``exception_type``,
       ``exception_message``, full Python ``traceback``, optional
       ``partial_bundle_path``, ISO-8601 UTC ``generated_at`` timestamp).
       Uses :meth:`pathlib.Path.write_text` for atomic single-write per
       Pattern 4 (``write_text`` is a single ``write()`` syscall on POSIX;
       cross-platform robustness via write-then-rename is a Phase 2 upgrade).

    2. **Channel 2 — Streaming terminal (always)**.
       One-line stderr emission of the form
       ``bundle-assembly-failed: <failed-step> at <story-id>/<run-id> — see <fallback-diagnostic-path>``
       so practitioners watching ``bundle_assembly``'s subprocess output
       see the marker class + sub-classification + canonical fallback-file
       path in real time.

    3. **Channel 3 — Persisted run-state marker (best-effort
       partial-bundle render PLUS persisted form)**. Two reinforcing
       sub-projections of the same channel:
        (a) **Best-effort partial render** — IF the assembler crashed
            AFTER reaching ``_render_loud_fail_block`` then the partial
            bundle on disk MAY include the marker inline; this branch is
            naturally satisfied by the partial bundle's loud-fail block
            and requires no special-casing here.
        (b) **Persisted form** — invokes the
            ``marker_recorder`` callable (default
            :func:`loud_fail_harness.marker_wiring.record_marker_with_context`)
            with ``marker_class=BUNDLE_ASSEMBLY_FAILED_MARKER``,
            ``sub_classification=failed_step``, and the four-field
            ``context`` dict per the taxonomy's extended
            ``pointer_context_fields``; persists the new run-state via
            :func:`loud_fail_harness.run_state.advance_run_state` with a
            no-op story-doc callback (no story-doc edit at failure-detection
            time). The persisted entry survives across the failed run so
            the next-cycle bundle (after remediation) renders the marker
            in its loud-fail block via the existing Story 6.1 + Story 6.2
            path.

The atomicity invariant — ALL three channels MUST agree by construction;
mismatch is a contract violation. The atomicity is enforced as a
CODE-STRUCTURE invariant (a single source-of-truth function is the only
emission path; a CI lint scans for forbidden direct mutations of any of
the three channels outside this function), NOT a per-bundle reconciliation
gate. This is the SAME pattern Story 3.3 applied to ``surface_failed_layers``
and Story 2.2 applied to atomic-write: the API shape IS the invariant.

Validate-then-mutate atomicity: if the supplied
:class:`MarkerClassRegistry` rejects the marker class, the
:exc:`UnknownMarkerClass` exception propagates BEFORE any of the three
channels commit — no fallback-diagnostic file written; no stderr line
emitted; run-state on disk unchanged. This mirrors
:func:`loud_fail_harness.review_layer_failure.surface_failed_layers`'s
pre-loop validation discipline.

Remediation-shape principle (Story 6.9 AC-2 + AC-3):
    The ``bundle-assembly-failed`` marker class is *distinct* from
    ``hook-failed: stop``. ``hook-failed`` remediates the Stop hook
    script's bash / environment / invocation contract (FR1, NFR-R6);
    ``bundle-assembly-failed`` remediates the assembler's logical surface
    (envelope shape, finding rendering, taxonomy reference, internal
    exception). The two emission events are independent because they
    sense different surfaces — Stop hook clean + assembler crash → only
    ``bundle-assembly-failed`` fires; both surfaces fail → both markers
    fire (per AC-3's cross-failure matrix). The runtime signal that
    distinguishes the two is the assembler's exit code:
    :data:`BUNDLE_ASSEMBLY_FAILED_EXIT_CODE` (=2) means "assembler
    logic failed; marker already emitted via :func:`surface_assembly_failure`";
    any other non-zero exit means "Stop hook crashed mechanically; route
    through :func:`loud_fail_harness.marker_wiring.record_hook_failure_marker`".
    The :func:`loud_fail_harness.orchestrator_run_entry.handle_hook_exit_code`
    helper consumes the constant exported here to gate the
    ``hook-failed: stop`` emission.

Contract anchors:
    FR59 (Stop hook bundle assembly), NFR-O5 (named-invariant
    diagnostics), ADR-003 (substrate-vs-specialist boundary at
    ``architecture.md`` lines 311-315),
    Pattern 1 (snake_case fields; kebab-case identifier values),
    Pattern 2 (marker class naming; ``: <cause>`` suffix),
    Pattern 4 (state-update discipline — single atomic write per seam
               via :func:`advance_run_state`),
    Pattern 5 (loud-fail / named invariants — registry rejection
               raises rather than silently coercing).

Cross-references:
    * Story 1.4 ``schemas/marker-taxonomy.yaml`` lines 292-301 —
      ``bundle-assembly-failed`` marker class identity (consumed
      AS-IS for the marker-class string; EXTENDED additively for
      ``pointer_context_fields`` / ``sub_classifications`` /
      ``diagnostic_pointer`` interpolation).
    * Story 2.7 ``hooks/stop.sh`` — the Stop hook's
      ``exec python3 -m loud_fail_harness.bundle_assembly`` invocation
      seam. NOT modified by Story 6.9; the assembler's exit code is the
      runtime signal consumed by ``handle_hook_exit_code``.
    * Story 2.11 ``bundle_assembly.assemble_bundle`` — the assembler's
      success path. NOT modified by Story 6.9; only ``main``'s wrapping
      logic changes.
    * Story 3.3 :mod:`loud_fail_harness.review_layer_failure` +
      :mod:`loud_fail_harness.review_layer_failure_emission_gate` —
      the canonical source-of-truth-with-CI-lint precedent this module
      mirrors byte-for-byte in shape.
    * Story 6.1 :func:`loud_fail_harness.bundle_assembly._render_loud_fail_block`
      — the loud-fail block consumed by Channel 3's "best-effort partial
      render" branch.
    * Story 6.2 :func:`loud_fail_harness.bundle_assembly._interpolate_actionable_pointer`
      — the actionable-pointer rendering machinery consumed by Channel
      3's persisted-marker form on the next-cycle bundle.
    * Story 6.7 :func:`loud_fail_harness.marker_wiring.record_marker_with_context`
      — the canonical orchestrator-side marker-recorder helper this
      module composes for Channel 3's persisted form.

FR62 pluggability classification:
    This module is *substrate-shared library* per Story 1.10b's precedent.
    The FR62 pluggability gate at
    :mod:`loud_fail_harness.pluggability_gate` scans ``agents/*.md`` only;
    the substrate at ``tools/loud-fail-harness/`` is OUTSIDE the gate's
    scope by construction. This module references no specialist by slug
    or path.
"""

from __future__ import annotations

import dataclasses
import datetime
import pathlib
import sys
import traceback
from collections.abc import Callable
from typing import Final, Literal, TextIO

import yaml

from loud_fail_harness.marker_wiring import record_marker_with_context
from loud_fail_harness.run_state import (
    RunState,
    StoryDocCallbackResult,
    advance_run_state,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)

#: The marker class identifier emitted at all three channels (Story 1.4
#: enumeration; ``schemas/marker-taxonomy.yaml`` lines 292-301). Consumed
#: AS-IS; the taxonomy entry is EXTENDED additively for
#: ``pointer_context_fields`` / ``sub_classifications`` / placeholder-
#: interpolated ``diagnostic_pointer`` per Story 6.9 AC-1 + AC-2.
BUNDLE_ASSEMBLY_FAILED_MARKER: Final[Literal["bundle-assembly-failed"]] = (
    "bundle-assembly-failed"
)

#: The assembler-logic-failure exit code. Distinct from the pre-condition
#: exit 1 used by ``SpecialistDispatchLogNotFound`` / ``RunStateStoryIdMismatch``
#: cases. The Story 6.9 AC-3 conditional in
#: :func:`loud_fail_harness.orchestrator_run_entry.handle_hook_exit_code`
#: imports THIS constant to gate the ``hook-failed: stop`` emission so the
#: two markers stay remediation-shape-distinct at runtime. No magic
#: literals at consumer call-sites.
BUNDLE_ASSEMBLY_FAILED_EXIT_CODE: Final[int] = 2

#: The five enumerated assembler-failure modes (epics.md line 2818
#: verbatim: "envelope shape mismatch, missing finding fields, taxonomy
#: reference unresolved, finding-rendering crash, assembler-internal
#: exception"). Mirrored verbatim into the
#: ``schemas/marker-taxonomy.yaml`` ``bundle-assembly-failed`` entry's
#: ``sub_classifications`` list (alphabetical) per Story 6.9 AC-2.
AssemblyFailureStep = Literal[
    "envelope-mismatch",
    "finding-render-crash",
    "internal-exception",
    "missing-finding-fields",
    "taxonomy-unresolved",
]


@dataclasses.dataclass(frozen=True)
class AssemblyFailureRecord:
    """The captured failure context returned by :func:`surface_assembly_failure`.

    Frozen for determinism + hashability per Epic 1 retro Action #2.

    Field semantics:
        * ``story_id`` — the BMAD story identifier.
        * ``run_id`` — the per-run identifier under which the assembler
          was invoked.
        * ``failed_step`` — one of the five :data:`AssemblyFailureStep`
          values; the sub-classification suffix on the emitted marker.
        * ``exception_type`` — the unqualified class name of the caught
          exception (e.g., ``"EnvelopeReValidationFailed"``,
          ``"KeyError"``). Carried as the ``exception_type`` interpolation
          key for the taxonomy's diagnostic_pointer.
        * ``exception_message`` — ``str(exc)`` of the caught exception;
          surfaces in the fallback diagnostic file for human reading.
        * ``traceback_text`` — full Python traceback as rendered by
          :func:`traceback.format_exception`; surfaces in the fallback
          diagnostic file for stack-trace-driven debugging.
        * ``partial_bundle_path`` — optional on-disk path to the partial
          bundle if the assembler crashed AFTER any partial-render step.
          ``None`` if the assembler crashed before any bundle file was
          written.
        * ``fallback_diagnostic_path`` — the canonical on-disk location
          of the Channel 1 fallback diagnostic file
          (``<bundle_root>/<story_id>/<run_id>.assembly-failure.log``).
    """

    story_id: str
    run_id: str
    failed_step: AssemblyFailureStep
    exception_type: str
    exception_message: str
    traceback_text: str
    partial_bundle_path: pathlib.Path | None
    fallback_diagnostic_path: pathlib.Path


def classify_assembly_failure(
    exc: BaseException, partial_bundle_path: pathlib.Path | None = None
) -> AssemblyFailureStep:
    """Map a caught assembler exception to its :data:`AssemblyFailureStep`.

    Pure function (no I/O). Used by :func:`bundle_assembly.main`'s outer
    try/except to classify the caught exception before invoking
    :func:`surface_assembly_failure`. Importable independently for unit-
    test parity per Story 6.9 AC-6 (e).

    Mapping rules (in order; first match wins):
        * :exc:`loud_fail_harness.bundle_assembly.EnvelopeReValidationFailed`
          → ``"envelope-mismatch"``.
        * :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
          → ``"taxonomy-unresolved"``.
        * :exc:`KeyError` raised from a finding-rendering helper
          → ``"missing-finding-fields"``.
        * Any other :exc:`Exception` subclass (including
          :exc:`RuntimeError` raised from a rendering helper)
          → ``"finding-render-crash"``.
        * Non-``Exception`` :exc:`BaseException` (e.g.
          :exc:`GeneratorExit`) → ``"internal-exception"``.

    Note: :exc:`SystemExit` and :exc:`KeyboardInterrupt` are NOT caught
    by ``bundle_assembly.main``'s outer try/except per Pattern 5's
    named-invariant convention; this helper does not classify them
    either (callers should not invoke this helper for those exception
    types).

    Args:
        exc: The caught exception instance.
        partial_bundle_path: Optional on-disk path to a partial bundle
            file if the assembler crashed mid-render. Accepted for API
            compatibility; not used for classification — all
            :exc:`Exception` subclasses map to ``"finding-render-crash"``
            regardless of whether a partial bundle exists on disk.

    Returns:
        The :data:`AssemblyFailureStep` Literal value to use as the
        marker sub-classification.
    """
    from loud_fail_harness.bundle_assembly import EnvelopeReValidationFailed
    from loud_fail_harness.specialist_dispatch import UnknownMarkerClass

    if isinstance(exc, EnvelopeReValidationFailed):
        return "envelope-mismatch"
    if isinstance(exc, UnknownMarkerClass):
        return "taxonomy-unresolved"
    if isinstance(exc, KeyError):
        return "missing-finding-fields"
    if isinstance(exc, Exception):
        return "finding-render-crash"
    return "internal-exception"


def _format_diagnostic_text(
    *,
    story_id: str,
    run_id: str,
    failed_step: AssemblyFailureStep,
    exception_type: str,
    exception_message: str,
    traceback_text: str,
    partial_bundle_path: pathlib.Path | None,
    generated_at: str,
) -> str:
    """Render the fallback diagnostic file's structured-text body.

    Header is the canonical grep target ``=== bundle-assembly-failed ===``;
    fields are emitted in the documented order so practitioners scanning
    logs across runs see consistent layout. The function is private (the
    canonical fixture's golden output is the public contract).
    """
    lines: list[str] = []
    lines.append("=== bundle-assembly-failed ===")
    lines.append(f"story_id: {story_id}")
    lines.append(f"run_id: {run_id}")
    lines.append(f"failed_step: {failed_step}")
    lines.append(f"exception_type: {exception_type}")
    lines.append(f"exception_message: {exception_message}")
    lines.append(f"generated_at: {generated_at}")
    if partial_bundle_path is not None:
        lines.append(f"partial_bundle_path: {partial_bundle_path}")
    else:
        lines.append("partial_bundle_path: <none>")
    lines.append("")
    lines.append("traceback:")
    lines.append(traceback_text.rstrip("\n"))
    lines.append("")
    return "\n".join(lines)


def _no_op_story_doc_callback() -> StoryDocCallbackResult:
    """Module-private no-op story-doc callback for the Channel 3 write.

    The bundle-assembly-failure path does NOT edit the story doc — the
    failure happens at run-cycle close after specialist work is done.
    Using :func:`advance_run_state` with a no-op callback preserves the
    structural invariant that ALL run-state writes route through
    :func:`advance_run_state` (Pattern 4 verbatim); mirrors the
    ``_no_op_story_doc_callback`` in
    :mod:`loud_fail_harness.orchestrator_run_entry`.
    """
    return StoryDocCallbackResult(
        accepted=True,
        reason=(
            "bundle-assembly-failed run-state persistence — no story-doc "
            "edit needed at failure-detection time"
        ),
    )


def surface_assembly_failure(
    *,
    story_id: str,
    run_id: str,
    run_state_path: pathlib.Path,
    bundle_root: pathlib.Path,
    exc: BaseException,
    failed_step: AssemblyFailureStep,
    partial_bundle_path: pathlib.Path | None = None,
    registry: MarkerClassRegistry | None = None,
    marker_recorder: Callable[..., RunState] = record_marker_with_context,
    stderr: TextIO | None = None,
) -> AssemblyFailureRecord:
    """Surface an assembler-logic failure across all THREE channels atomically.

    THIS function is the SINGLE source-of-truth emission path for the
    three-channel projection of a bundle-assembly logical failure
    (FR59 + NFR-O5). The atomicity is enforced as a code-structure
    invariant via the AC-4 CI lint
    :mod:`loud_fail_harness.bundle_assembly_failure_emission_gate`.
    No other code path in the harness source tree is permitted to:
    write a ``*.assembly-failure.log`` file directly; emit the
    ``bundle-assembly-failed`` marker string literal; or append a
    ``bundle-assembly-failed`` entry to ``run_state.active_markers``.

    Behavior (validate-then-mutate atomicity per Pattern 5):
        * **Step 0 (validation)** — if ``registry`` is supplied,
          calls :func:`validate_marker_emission` against the registry;
          on registry rejection :exc:`UnknownMarkerClass` propagates
          BEFORE any of the three channels commit. If ``registry`` is
          ``None`` (default), no pre-validation is performed (callers
          either supply the registry explicitly OR rely on the
          ``marker_recorder``'s own per-call validation).
        * **Channel 1 (fallback diagnostic file)** — writes
          ``<bundle_root>/<story_id>/<run_id>.assembly-failure.log``
          with the structured-text body via
          :meth:`pathlib.Path.write_text`. Parent directory is created
          via :meth:`pathlib.Path.mkdir(parents=True, exist_ok=True)`
          so the canonical hierarchy is materialized lazily.
        * **Channel 2 (stderr line)** — writes one line to ``stderr``
          of the form ``bundle-assembly-failed: <failed-step> at
          <story-id>/<run-id> — see <fallback-diagnostic-path>``.
        * **Channel 3 (persisted run-state marker)** — loads the
          run-state via :func:`RunState.model_validate`, invokes
          ``marker_recorder`` with ``marker_class``,
          ``sub_classification``, and the four-field ``context`` per
          the taxonomy's extended ``pointer_context_fields``, then
          persists via :func:`advance_run_state` with a no-op story-doc
          callback (no story-doc edit at failure-detection time).

    Channels are NOT individually rolled back on partial failure: if
    Channel 1 succeeds and Channel 3 raises, the on-disk diagnostic file
    survives by design (the practitioner needs the diagnostic even if
    run-state persistence fails — that is the point of three reinforcing
    channels). Pre-emission registry validation is the atomicity guard;
    once validation passes the channels are emitted in order.

    Args:
        story_id: BMAD story identifier (e.g., ``"auto-001"``).
        run_id: Per-run identifier.
        run_state_path: On-disk path of the run-state YAML file. The
            file must exist + parse to a valid :class:`RunState` per
            ``schemas/run-state.yaml``; otherwise the underlying
            :exc:`pydantic.ValidationError` propagates per Pattern 5.
        bundle_root: Root directory under which the canonical fallback-
            file path ``<bundle_root>/<story_id>/<run_id>.assembly-failure.log``
            is materialized.
        exc: The caught assembler-logic exception. Used to populate
            ``exception_type``, ``exception_message``, and
            ``traceback_text`` on the returned record.
        failed_step: One of the five :data:`AssemblyFailureStep` values;
            forms the marker's ``: <cause>`` suffix per Pattern 2.
        partial_bundle_path: Optional on-disk path to the partial
            bundle if the assembler crashed AFTER a partial-render
            step. Surfaces in the fallback diagnostic file for the
            audit trail.
        registry: Optional :class:`MarkerClassRegistry` for
            pre-emission validation per Pattern 5. ``None`` skips
            pre-validation; the ``marker_recorder`` may still validate
            internally.
        marker_recorder: Keyword-only injection seam mirroring the
            convention from Story 6.7's ``record_*`` helpers. Default
            :func:`loud_fail_harness.marker_wiring.record_marker_with_context`.
        stderr: TextIO sink for Channel 2. Default :data:`sys.stderr`;
            tests inject :class:`io.StringIO` for capture.

    Returns:
        :class:`AssemblyFailureRecord` carrying the captured failure
        context for the caller's logging / re-raise decision.

    Raises:
        UnknownMarkerClass: ``registry`` was supplied AND
            ``BUNDLE_ASSEMBLY_FAILED_MARKER`` is not in the registry's
            enumeration. Validation happens BEFORE any channel commits.
    """
    # Validate-then-mutate: registry rejection raises BEFORE any channel
    # commits. Mirrors surface_failed_layers's pre-loop validation.
    if registry is not None:
        validate_marker_emission(registry, BUNDLE_ASSEMBLY_FAILED_MARKER)

    # Resolve `stderr` at call-time so pytest capsys / capfd can intercept
    # the `sys.stderr` redirection. A function-default of `sys.stderr`
    # would bind once at module-load time, defeating capsys.
    if stderr is None:
        stderr = sys.stderr

    # Capture failure context for both the on-disk diagnostic AND the
    # returned record; computed once so all surfaces agree.
    exception_type = type(exc).__name__
    exception_message = str(exc)
    traceback_text = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    generated_at = datetime.datetime.now(datetime.UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    fallback_diagnostic_path = (
        bundle_root / story_id / f"{run_id}.assembly-failure.log"
    )

    # Channel 1 — fallback diagnostic file (always).
    fallback_diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
    fallback_diagnostic_path.write_text(
        _format_diagnostic_text(
            story_id=story_id,
            run_id=run_id,
            failed_step=failed_step,
            exception_type=exception_type,
            exception_message=exception_message,
            traceback_text=traceback_text,
            partial_bundle_path=partial_bundle_path,
            generated_at=generated_at,
        ),
        encoding="utf-8",
    )

    # Channel 2 — stderr line (always).
    stderr.write(
        f"{BUNDLE_ASSEMBLY_FAILED_MARKER}: {failed_step} at "
        f"{story_id}/{run_id} — see {fallback_diagnostic_path}\n"
    )

    # Channel 3 — persisted run-state marker.
    raw = yaml.safe_load(run_state_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"run-state file at {run_state_path} did not parse to a YAML "
            "mapping at top level"
        )
    current = RunState.model_validate(raw)
    next_state = marker_recorder(
        run_state=current,
        marker_class=BUNDLE_ASSEMBLY_FAILED_MARKER,
        sub_classification=failed_step,
        context={
            "exception_type": exception_type,
            "failed_step": failed_step,
            "run_id": run_id,
            "story_id": story_id,
        },
    )
    if next_state is not current:
        advance_run_state(
            run_state_path,
            next_state,
            story_doc_callback=_no_op_story_doc_callback,
        )

    return AssemblyFailureRecord(
        story_id=story_id,
        run_id=run_id,
        failed_step=failed_step,
        exception_type=exception_type,
        exception_message=exception_message,
        traceback_text=traceback_text,
        partial_bundle_path=partial_bundle_path,
        fallback_diagnostic_path=fallback_diagnostic_path,
    )


__all__ = [
    "BUNDLE_ASSEMBLY_FAILED_EXIT_CODE",
    "BUNDLE_ASSEMBLY_FAILED_MARKER",
    "AssemblyFailureRecord",
    "AssemblyFailureStep",
    "classify_assembly_failure",
    "surface_assembly_failure",
]
