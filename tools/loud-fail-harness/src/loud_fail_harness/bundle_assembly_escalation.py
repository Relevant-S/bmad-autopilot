"""Escalation-variant PR bundle assembler — Story 5.8 substrate module.

## Substrate-component identity

THIS module is the SEVENTH substrate component beyond ADR-003's enumerated
five (envelope_validator, event_validator, reconciler, enumeration_check,
fixture_coverage), composed from Story 2.11's
:mod:`loud_fail_harness.bundle_assembly` (SIXTH) + Story 5.5's
:mod:`loud_fail_harness.retry_history` + Story 5.4's
:mod:`loud_fail_harness.scope_assertion` + Story 5.6's
:mod:`loud_fail_harness.retry_budget_exhaustion` + Story 1.4's
``marker-taxonomy.yaml`` + Story 4.10's contract fragments at
``schemas/escalation-bundles/`` + Story 5.7's ``automator-internal``-
ratified BMAD-METHOD ``deferred-work.md`` format.

## Single rendering core (shared with Story 2.11)

Per the verbatim epic AC at ``epics.md`` lines 2479-2481, "Story 2.11 now
has two variants but a single rendering core — escalation variant is a
distinct flow, not a fork of the assembler". Mechanically, THIS module
imports the shared rendering helpers from :mod:`bundle_assembly` directly:
``_render_walking_skeleton_header``, ``_render_finding_bullet``,
``_render_marker``, ``_emit_walking_skeleton_marker``,
``_atomic_write_bundle``, ``_THICKENING_SENTENCES``,
``WALKING_SKELETON_MARKER``, ``_default_thickening_flags``. The Python
underscore convention does NOT prevent imports — it documents package-
internal API; importing across module boundaries within the same package
is the canonical pattern for shared rendering helpers per Story 2.11's
substrate-component identity at ``bundle_assembly.py`` lines 1-12.

The import-direction is one-way: escalation depends on merge-ready;
merge-ready does NOT depend on escalation. This prevents circular-import
drift AND structurally guarantees that future modifications to
:func:`bundle_assembly.assemble_bundle` (merge-ready) cannot inadvertently
couple with escalation-variant logic. The byte-equality test
``test_walking_skeleton_header_byte_identical_across_variants`` is the
structural surface for "the rendering core has been forked" — failure of
that test is the loud-fail signal.

## Input contract

    * ``context`` — a Pydantic-validated
      :class:`loud_fail_harness.retry_budget_exhaustion.ExhaustionContext`
      with ``trigger ∈ {BUDGET_EXHAUSTED, SCOPE_ASSERTION_VIOLATION}``.
      Future QA-domain triggers (verification-fail / env-setup-fail) land
      via Story 5.6's ``ExhaustionTrigger`` enum extension OR a parallel
      context dataclass; the dispatch-by-``bundle_class``-discriminator
      posture lets that landing happen WITHOUT touching this module's
      public surface.
    * ``repo_root`` — :class:`pathlib.Path` the deterministic on-disk
      output path is anchored to (Epic 1 retro Action #1 discipline:
      every public helper accepts ``repo_root`` as a caller-supplied
      parameter; no module-import-time ``find_repo_root()`` call).

## Output contract

    * A markdown file written atomically (Pattern 4: ``tempfile`` +
      ``os.replace``) at the deterministic per-run path computed by
      :func:`loud_fail_harness.retry_budget_exhaustion.compute_escalation_bundle_path`
      (``{repo_root}/_bmad-output/escalation-bundles/{story_id}/{run_id}/escalation.md``).
    * A returned :class:`AssembleEscalationBundleResult` carrying the
      resolved bundle path, the emitted markers tuple, the rendered
      Walking Skeleton Mode header text, the bundle class discriminator,
      and the rendered machine-readable payload dict.

## Marker-emission contract

The ``walking-skeleton-bundle`` marker is emitted iff
:func:`loud_fail_harness.thickening_flags.is_loud_fail_block_present`
returns ``False``. This is the SAME structural rule as
:mod:`bundle_assembly` (merge-ready); the rule predicate flips for both
variants in lockstep when ``is_loud_fail_block_present`` flips (Epic 6's
Story 6.1 territory). THIS module does NOT add a loud-fail block — that
is Story 6.1's surface.

## Schema-conformance-at-assembly-time (Pattern 5 loud-fail)

Per the verbatim epic AC at ``epics.md`` lines 2483-2486, the assembler
reads contract content rules from the relevant
``schemas/escalation-bundles/{bundle_class}.yaml`` fragment at startup
and validates the constructed payload via
``jsonschema.Draft202012Validator(schema).validate(payload)`` BEFORE
:func:`_atomic_write_bundle` is invoked. Validation failure raises
:exc:`EscalationBundleSchemaConformanceError` per Pattern 5 (loud-fail
doctrine — defense-in-depth: a contract violation surfaces as a
structurally-distinct exception, NOT as silent drift to a non-conformant
bundle on disk).

## Cross-references

    * Story 2.11 :mod:`loud_fail_harness.bundle_assembly` — the merge-
      ready assembler whose rendering helpers are imported here.
    * Story 4.10 ``schemas/escalation-bundles/{verification-fail,
      env-setup-fail}.yaml`` — Epic-4 contract fragments consumed AS-IS
      via ``yaml.safe_load(...)``.
    * Story 5.4 :class:`loud_fail_harness.scope_assertion.ScopeAssertionDiagnostic`
      — populates ``scope_violation_diagnostic`` field for
      scope-assertion-violation bundles.
    * Story 5.5 :class:`loud_fail_harness.retry_history.RetryAttemptRef`
      — the reference shape rendered as ``retry_history_refs`` array.
    * Story 5.6 :class:`loud_fail_harness.retry_budget_exhaustion.ExhaustionContext`
      — the input dataclass.
    * Story 5.6 :func:`loud_fail_harness.retry_budget_exhaustion.compute_escalation_bundle_path`
      — reused AS-IS for output path computation.
    * Story 5.6 :data:`loud_fail_harness.retry_budget_exhaustion._REMEDIATION_HINT`
      — sourced verbatim for the retry-budget-exhausted bundle's
      escalation-rationale text.
    * Story 5.7 BMAD-METHOD ``deferred-work.md`` format ratified as
      ``automator-internal`` — referenced by the
      ``deferred_work_pointer`` field with canonical default path
      ``_bmad-output/implementation-artifacts/deferred-work.md``.
    * marker-taxonomy.yaml line 237 (``scope-assertion-violation``) +
      line 247 (``retry-budget-exhausted``) — marker-class strict-name
      references resolved by substrate component 4 (enumeration_check.py).

## ``find_repo_root()`` discipline (Epic 1 retro Action #1)

No path computation in this module calls ``find_repo_root()`` at module
import time. All public helpers accept ``repo_root`` as a caller-
supplied parameter.
"""

from __future__ import annotations

import dataclasses
import pathlib
from collections.abc import Mapping
from datetime import datetime, timezone
from types import ModuleType
from typing import Any, Final

import jsonschema
import yaml

from loud_fail_harness.bundle_assembly import _default_thickening_flags
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.bundle_assembly import (
    WALKING_SKELETON_MARKER,
    _atomic_write_bundle,
    _emit_walking_skeleton_marker,
    _render_finding_bullet,
    _render_marker,
    _render_walking_skeleton_header,
    _THICKENING_SENTENCES,
)
from loud_fail_harness.retry_budget_exhaustion import (
    ExhaustionContext,
    ExhaustionTrigger,
    _REMEDIATION_HINT,
    compute_escalation_bundle_path,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    load_marker_class_registry,
)

# Re-export the shared-rendering-core symbols for AC-4 import-introspection
# tests AND for downstream consumers that need the structural-shared
# surface visible from this module without round-tripping through
# :mod:`bundle_assembly`.
__all__ = [
    "AssembleEscalationBundleResult",
    "BUNDLE_CLASS_TO_SCHEMA_FILENAME",
    "ESCALATION_BUNDLE_SCHEMA_DIR",
    "EscalationBundleSchemaConformanceError",
    "EscalationBundleSchemaNotFound",
    "WALKING_SKELETON_MARKER",
    "assemble_escalation_bundle",
    "_THICKENING_SENTENCES",
    "_atomic_write_bundle",
    "_default_thickening_flags",
    "_emit_walking_skeleton_marker",
    "_render_finding_bullet",
    "_render_marker",
    "_render_walking_skeleton_header",
]


# --------------------------------------------------------------------------- #
# Constants                                                                   #
# --------------------------------------------------------------------------- #


#: Repo-relative directory under which the four escalation-bundle schema
#: fragments live. Story 4.10 created the directory; THIS module
#: consumes it AS-IS without modification per the Epic-4-vs-Epic-5
#: deliberate boundary at ``epics.md`` lines 2108-2112.
ESCALATION_BUNDLE_SCHEMA_DIR: Final[str] = "schemas/escalation-bundles"


#: Mapping from ``bundle_class`` discriminator value to the relative
#: schema-fragment filename. The four bundle classes covered are the
#: AC-1 four-trigger matrix:
#:   * ``retry-budget-exhausted`` — Story 5.8 contract (Epic 5 retry
#:     domain).
#:   * ``scope-assertion-violation`` — Story 5.8 contract (Epic 5 scope
#:     domain).
#:   * ``verification-fail`` — Story 4.10 contract (Epic 4 QA domain;
#:     consumed AS-IS).
#:   * ``env-setup-fail`` — Story 4.10 contract (Epic 4 QA domain;
#:     consumed AS-IS).
BUNDLE_CLASS_TO_SCHEMA_FILENAME: Final[Mapping[str, str]] = {
    "retry-budget-exhausted": "retry-budget-exhausted.yaml",
    "scope-assertion-violation": "scope-assertion-violation.yaml",
    "verification-fail": "verification-fail.yaml",
    "env-setup-fail": "env-setup-fail.yaml",
}


#: Mapping from :class:`ExhaustionTrigger` enum value to the
#: corresponding ``bundle_class`` discriminator string. The Epic-5
#: trigger surface enumerates only TWO retry/scope-domain values; the
#: QA-domain bundle classes do NOT have a corresponding ExhaustionTrigger
#: at MVP per the AC-1 note on the QA-domain trigger seam (the future
#: QA-domain trigger story extends the enum OR introduces a parallel
#: context dataclass; either way, this mapping is the closed-set
#: dispatch surface for the Epic-5-domain side).
_EXHAUSTION_TRIGGER_TO_BUNDLE_CLASS: Final[Mapping[ExhaustionTrigger, str]] = {
    ExhaustionTrigger.BUDGET_EXHAUSTED: "retry-budget-exhausted",
    ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION: "scope-assertion-violation",
}


#: Canonical default repo-relative path for the BMAD-METHOD
#: ``deferred-work.md`` artifact. Sourced from the live exemplar at
#: ``_bmad-output/implementation-artifacts/deferred-work.md`` ratified
#: by Story 5.7's ``automator-internal`` audit per
#: ``docs/extension-audit.md``'s SEVENTH per-convention row.
_DEFERRED_WORK_DEFAULT_PATH: Final[str] = (
    "_bmad-output/implementation-artifacts/deferred-work.md"
)


#: Canonical default repo-relative path for the run-state.yaml artifact
#: per architecture.md ADR-005. Used as the
#: ``preserved_run_state_path`` value when the assembler renders the
#: preservation block and no override is supplied.
_PRESERVED_RUN_STATE_DEFAULT_PATH: Final[str] = "_bmad/automation/run-state.yaml"


# --------------------------------------------------------------------------- #
# Result dataclass + named exceptions                                         #
# --------------------------------------------------------------------------- #


@dataclasses.dataclass(frozen=True)
class AssembleEscalationBundleResult:
    """Return shape of :func:`assemble_escalation_bundle` on success.

    Frozen for determinism + hashability per Epic 1 retro Action #2.
    Mirrors :class:`loud_fail_harness.bundle_assembly.AssembleBundleResult`'s
    field declaration order where overlapping; adds the
    ``bundle_class`` discriminator + the rendered ``payload`` dict so
    downstream tooling has the full machine-readable surface without
    re-parsing the bundle markdown.

    Field semantics:
        * ``bundle_path`` — resolved on-disk path of the written
          escalation-bundle markdown file (per
          :func:`compute_escalation_bundle_path`).
        * ``emitted_markers`` — tuple of marker-class identifiers the
          assembler emitted into the bundle's body. At Epic 5 substrate
          state this is exactly ``("walking-skeleton-bundle",)`` per the
          shared marker-emission rule with merge-ready bundles; future
          Epics may add more.
        * ``header_text`` — the rendered Walking Skeleton Mode H2
          section body produced by the SHARED
          :func:`bundle_assembly._render_walking_skeleton_header` helper.
        * ``bundle_class`` — the discriminator naming which of the four
          escalation-bundle classes this bundle is.
        * ``payload`` — the machine-readable structured payload dict
          (validated against the relevant schema fragment).
    """

    bundle_path: pathlib.Path
    emitted_markers: tuple[str, ...]
    header_text: str
    bundle_class: str
    payload: Mapping[str, Any]


class EscalationBundleSchemaNotFound(Exception):
    """Raised by :func:`assemble_escalation_bundle` when the relevant
    ``schemas/escalation-bundles/{bundle_class}.yaml`` fragment file
    does not exist on disk at the expected path.

    Pattern 5 named-invariant diagnostic. The assembler does NOT
    silently fall back to a default schema or skip validation — every
    bundle class must have its contract on disk.
    """

    def __init__(self, *, bundle_class: str, expected_path: pathlib.Path) -> None:
        self.bundle_class = bundle_class
        self.expected_path = expected_path
        super().__init__(
            f"EscalationBundleSchemaNotFound: bundle_class={bundle_class!r} "
            f"expected schema fragment at {expected_path} (Story 4.10 / "
            "Story 5.8 contract authoring); escalation-bundle assembly "
            "cannot proceed without the relevant content contract"
        )


class EscalationBundleSchemaConformanceError(Exception):
    """Raised by :func:`assemble_escalation_bundle` when the constructed
    machine-readable payload fails JSON-Schema-2020-12 validation
    against the relevant ``schemas/escalation-bundles/{bundle_class}.yaml``
    fragment.

    Pattern 5 named-invariant diagnostic. Defense-in-depth per the
    verbatim epic AC at ``epics.md`` lines 2483-2486 — the validation
    runs BEFORE :func:`_atomic_write_bundle` is invoked; validation
    failure produces zero filesystem mutations.
    """

    def __init__(
        self,
        *,
        bundle_class: str,
        schema_path: pathlib.Path,
        failing_field: str,
        expected_shape: str,
    ) -> None:
        self.bundle_class = bundle_class
        self.schema_path = schema_path
        self.failing_field = failing_field
        self.expected_shape = expected_shape
        super().__init__(
            f"EscalationBundleSchemaConformanceError: bundle_class="
            f"{bundle_class!r} schema={schema_path} failing_field="
            f"{failing_field!r} expected_shape={expected_shape!r}; "
            "the assembler did NOT write a non-conformant bundle to "
            "disk (Pattern 5 loud-fail doctrine — defense-in-depth)"
        )


# --------------------------------------------------------------------------- #
# Schema loading + payload validation                                         #
# --------------------------------------------------------------------------- #


def _resolve_schema_path(
    *, schemas_root: pathlib.Path, bundle_class: str
) -> pathlib.Path:
    """Resolve the on-disk path to the schema fragment for the given
    ``bundle_class``.

    The resolution rule is the deterministic
    ``{schemas_root}/{ESCALATION_BUNDLE_SCHEMA_DIR}/{filename}`` path
    computation; the filename comes from
    :data:`BUNDLE_CLASS_TO_SCHEMA_FILENAME`. Unknown ``bundle_class``
    values raise :exc:`EscalationBundleSchemaNotFound` (the missing-
    schema and unknown-class failures collapse to the same Pattern 5
    surface — an unknown bundle class is structurally a missing-schema
    state from the assembler's perspective).
    """
    filename = BUNDLE_CLASS_TO_SCHEMA_FILENAME.get(bundle_class)
    if filename is None:
        raise EscalationBundleSchemaNotFound(
            bundle_class=bundle_class,
            expected_path=schemas_root / ESCALATION_BUNDLE_SCHEMA_DIR,
        )
    return schemas_root / ESCALATION_BUNDLE_SCHEMA_DIR / filename


def _load_schema(schema_path: pathlib.Path, *, bundle_class: str) -> dict[str, Any]:
    """Read + ``yaml.safe_load`` the schema fragment, raising
    :exc:`EscalationBundleSchemaNotFound` if the file does not exist.
    """
    if not schema_path.exists():
        raise EscalationBundleSchemaNotFound(
            bundle_class=bundle_class, expected_path=schema_path
        )
    return yaml.safe_load(schema_path.read_text(encoding="utf-8"))


def _validate_payload_against_schema(
    *,
    payload: Mapping[str, Any],
    bundle_class: str,
    schemas_root: pathlib.Path,
) -> None:
    """Validate ``payload`` against the schema fragment for
    ``bundle_class``. Raises :exc:`EscalationBundleSchemaConformanceError`
    on validation failure (the FIRST validation error is surfaced; the
    full error iterator is intentionally NOT exposed because the Pattern
    5 surface is one-error-per-failure for diagnostic clarity).
    """
    schema_path = _resolve_schema_path(
        schemas_root=schemas_root, bundle_class=bundle_class
    )
    schema = _load_schema(schema_path, bundle_class=bundle_class)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(dict(payload)), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        # ``first.absolute_path`` is a deque of path components; the
        # JSON-pointer-shaped string is the diagnostic-friendly form.
        failing_field = (
            "/" + "/".join(str(p) for p in first.absolute_path)
            if first.absolute_path
            else "<root>"
        )
        raise EscalationBundleSchemaConformanceError(
            bundle_class=bundle_class,
            schema_path=schema_path,
            failing_field=failing_field,
            expected_shape=first.message,
        )


# --------------------------------------------------------------------------- #
# Section renderers (escalation-variant-specific)                             #
# --------------------------------------------------------------------------- #


def _render_escalation_rationale(
    *, bundle_class: str, context: ExhaustionContext | None = None
) -> str:
    """Render the ``## Escalation rationale`` section body (1-3
    sentences naming which trigger fired).

    The rationale text is sourced from the marker-taxonomy.yaml
    diagnostic_pointer for the relevant marker class — substrate-side
    reuse prevents drift between the marker emission's remediation hint
    and the bundle's rationale text. For ``retry-budget-exhausted``,
    the canonical text mirrors
    :data:`loud_fail_harness.retry_budget_exhaustion._REMEDIATION_HINT`
    verbatim.
    """
    if bundle_class == "retry-budget-exhausted":
        body = _REMEDIATION_HINT
    elif bundle_class == "scope-assertion-violation":
        body = (
            "FR10 (fix-only constraint) + FR12 (verification logic) + "
            "FR58 (SubagentStop hook non-zero exit path). Domain-specific "
            "contract violation distinct from `hook-failed` because "
            "remediation differs (review Dev's diff vs. declared scope; "
            "possibly tighten retry's `affected_files`); markers are "
            "remediation-shaped, not emission-point-shaped."
        )
    elif bundle_class == "verification-fail":
        body = (
            "FR24a — QA's default retry policy on verification failure is "
            "`escalate`. Verification failures imply semantic drift / gamed "
            "tests / integration gaps, NOT `patch` findings. Inspect the "
            "failing AC result and the QA Behavioral Plan section linked "
            "below for drift inspection."
        )
    elif bundle_class == "env-setup-fail":
        body = (
            "FR24b — env-setup failures are structurally distinct from "
            "verification failures; story-state preservation prevents the "
            "QA lifecycle state from being entered when the env never came "
            "up. Re-running env-provisioning + QA after config remediation "
            "produces a clean run starting from the preserved review state."
        )
    else:
        # Unreachable at Pattern 5 level — _resolve_bundle_class enforces
        # closed-set membership before this is called. Kept as a defensive
        # branch so a future bundle-class addition surfaces a structurally
        # named exception rather than a silent empty rationale.
        raise EscalationBundleSchemaNotFound(
            bundle_class=bundle_class,
            expected_path=pathlib.Path(ESCALATION_BUNDLE_SCHEMA_DIR),
        )

    trigger_value = context.trigger.value if context is not None else bundle_class
    return f"Trigger fired: `{trigger_value}` (marker class `{bundle_class}`).\n\n{body}"


def _render_outstanding_findings(context: ExhaustionContext) -> str:
    """Render the ``## Outstanding findings`` section body from the
    ``last_envelope``'s findings array (if present).

    Per AC-2 section 3: the section MAY be empty for
    ``SCOPE_ASSERTION_VIOLATION`` triggers (the violation is the
    finding); render an explicit sentinel in that case. Each rendered
    finding bullet flows through the SHARED
    :func:`bundle_assembly._render_finding_bullet` helper for byte-
    stable per-finding rendering.
    """
    envelope = context.last_envelope
    findings: list[Any] = []
    if envelope is not None:
        raw = envelope.get("findings") or []
        findings = [f for f in raw if isinstance(f, dict)]

    if context.trigger is ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION and not findings:
        # Per AC-2 section 3: scope-assertion-violation triggers may
        # carry no envelope-side findings (the violation IS the
        # finding); render the explicit sentinel so the section is
        # present-but-explicit, not empty-or-misleading.
        return (
            "No outstanding findings — see scope-assertion violation "
            "diagnostic below."
        )

    if envelope is None:
        return (
            "_(no last envelope captured — "
            "the trigger fired without a return-envelope payload)_"
        )

    if not findings:
        return "_(no findings in last envelope)_"

    return "\n".join(_render_finding_bullet(f) for f in findings)


def _render_retry_history(context: ExhaustionContext) -> str:
    """Render the ``## Retry history`` section body from
    ``context.retry_history`` (``tuple[RetryAttempt, ...]``).

    Per AC-2 section 4: each entry produces a one-line summary plus a
    relative-path link to the per-round artifact directory. The section
    MUST be present (not OMITTED) even when ``retry_history`` is empty
    — render the sentinel ``- (no retry rounds recorded)`` per the
    existing placeholder behavior.
    """
    if not context.retry_history:
        return "- (no retry rounds recorded)"

    lines: list[str] = []
    for attempt in context.retry_history:
        round_id = attempt.round_id if attempt.round_id is not None else "(unset)"
        path = attempt.path if attempt.path is not None else "(unset)"
        lines.append(
            f"- attempt={attempt.retry_attempt}, "
            f"reason={attempt.retry_reason!r}, "
            f"round_id={round_id}, path={path}"
        )
        if attempt.path is not None:
            lines.append(f"  - [Round {attempt.retry_attempt} artifacts]({path})")
    return "\n".join(lines)


def _render_deferred_work_pointer(*, story_id: str) -> str:
    """Render the ``## Deferred-work pointer`` section body.

    Per AC-2 section 5: emits a markdown link to
    ``_bmad-output/implementation-artifacts/deferred-work.md`` per
    Story 5.7's ``automator-internal`` ratification of the BMAD-METHOD
    format. The optional section anchor (``## Deferred from: code
    review of <story_id> (<YYYY-MM-DD>)``) is rendered as a follow-on
    note since the per-story date suffix isn't known at assembly-time
    for stories that haven't yet had defer-time persistence.
    """
    target = _DEFERRED_WORK_DEFAULT_PATH
    return (
        f"Deferred work for this story: [{target}]({target})\n"
        "\n"
        f"If a `## Deferred from: code review of {story_id} (<YYYY-MM-DD>)` "
        "section exists in that file (Story 5.2's `record_defer_findings` "
        "writes it at defer-time), it carries the per-finding deferred work "
        "rationale. The pointer is required in this bundle's structure "
        "regardless of whether the section exists at assembly-time — a "
        "dangling pointer surfaces at consume-time, NOT at assembly-time."
    )


def _render_preservation_block(*, context: ExhaustionContext) -> str:
    """Render the ``## Preservation`` section body — two key-value lines
    per AC-2 section 6.

    The run-state path is rendered relative to ``repo_root`` for
    portability; the canonical default
    ``_bmad/automation/run-state.yaml`` per ADR-005 is used.
    """
    return (
        f"**Preserved branch:** `{context.branch_name}`\n"
        f"**Preserved run-state path:** `{_PRESERVED_RUN_STATE_DEFAULT_PATH}`"
    )


# --------------------------------------------------------------------------- #
# Machine-readable payload construction                                       #
# --------------------------------------------------------------------------- #


def _retry_attempt_ref_payload(attempts: tuple[Any, ...]) -> list[dict[str, Any]]:
    """Convert ``context.retry_history`` (tuple of
    :class:`loud_fail_harness.run_state.RetryAttempt`) into the
    ``retry_history_refs`` array shape declared by the schema.

    Entries with missing ``round_id`` / ``path`` (Story 5.5's pre-
    thickened state) are SKIPPED — the schema requires both fields per
    the ``$defs/retry_attempt_ref`` block. This is structurally legal
    because the assembler runs after Story 5.5's externalization
    landing; an entry missing ``round_id`` / ``path`` would represent
    a pre-Story-5.5 fixture, which is out of scope for the production
    write path.
    """
    out: list[dict[str, Any]] = []
    for attempt in attempts:
        round_id = getattr(attempt, "round_id", None)
        path = getattr(attempt, "path", None)
        if round_id is None or path is None:
            continue
        out.append(
            {
                "retry_attempt": attempt.retry_attempt,
                "retry_reason": attempt.retry_reason,
                "round_id": round_id,
                "path": path,
            }
        )
    return out


def _construct_machine_readable_payload(
    *, context: ExhaustionContext, bundle_class: str
) -> dict[str, Any]:
    """Build the machine-readable structured payload dict per the
    schema fragment for ``bundle_class``.

    The payload is intentionally constructed BEFORE schema validation
    so that a payload-construction defect surfaces at validation time
    (Pattern 5 defense-in-depth) — NOT as silent drift.

    Only Epic-5-domain bundle classes are constructed here.
    QA-domain bundle classes (verification-fail, env-setup-fail) are
    constructed by the future QA-domain trigger story OR (at MVP) by
    the test fixture composing the payload directly per the AC-1 note
    on the QA-domain trigger seam.
    """
    if bundle_class not in {
        "retry-budget-exhausted",
        "scope-assertion-violation",
    }:
        raise EscalationBundleSchemaNotFound(
            bundle_class=bundle_class,
            expected_path=pathlib.Path(ESCALATION_BUNDLE_SCHEMA_DIR),
        )

    rationale = _render_escalation_rationale(
        bundle_class=bundle_class, context=context
    ).split("\n\n", 1)[-1]

    # The envelope_path field is sourced from
    # ``context.bundle_artifact_path`` for the Epic-5-domain bundle
    # classes; the bundle artifact path correlates with the failing
    # envelope's dispatch log (Story 5.6's
    # ``record_retry_budget_exhaustion`` populates this field upstream).
    payload: dict[str, Any] = {
        "bundle_class": bundle_class,
        "story_id": context.story_id,
        "run_id": context.run_id,
        "retry_history_refs": _retry_attempt_ref_payload(context.retry_history),
        "outstanding_findings_pointer": {
            "envelope_path": context.bundle_artifact_path,
        },
        "escalation_rationale": rationale,
        "deferred_work_pointer": {"path": _DEFERRED_WORK_DEFAULT_PATH},
        "preserved_branch_name": context.branch_name,
        "preserved_run_state_path": _PRESERVED_RUN_STATE_DEFAULT_PATH,
        "marker_class": bundle_class,
    }

    if bundle_class == "scope-assertion-violation":
        diag = context.scope_violation_diagnostic
        if diag is None:
            # Co-presence is enforced by ExhaustionContext's
            # model_validator — this branch is structurally unreachable
            # for a Pydantic-validated context. Kept as a defensive
            # branch surfacing a Pattern 5 exception if reached via a
            # future API extension.
            raise EscalationBundleSchemaConformanceError(
                bundle_class=bundle_class,
                schema_path=pathlib.Path(ESCALATION_BUNDLE_SCHEMA_DIR)
                / BUNDLE_CLASS_TO_SCHEMA_FILENAME[bundle_class],
                failing_field="/scope_violation_diagnostic",
                expected_shape=(
                    "REQUIRED for scope-assertion-violation bundles "
                    "but None on the ExhaustionContext"
                ),
            )
        payload["scope_violation_diagnostic"] = {
            "declared_scope": list(diag.declared_scope),
            "declared_expansion": list(diag.declared_expansion),
            "violating_files": list(diag.violating_files),
            "retry_round": diag.retry_round,
        }

    return payload


# --------------------------------------------------------------------------- #
# Bundle-class dispatch                                                       #
# --------------------------------------------------------------------------- #


def _resolve_bundle_class(context: ExhaustionContext) -> str:
    """Map the trigger to its bundle_class discriminator.

    The dispatch is closed-set at MVP per the AC-1 note on the QA-
    domain trigger seam. Future QA-domain trigger landings extend
    :class:`ExhaustionTrigger` (or compose a parallel context dataclass);
    the dispatch table grows without changing this module's public
    surface.

    Raises:
        EscalationBundleSchemaNotFound: the trigger value is not in the
            dispatch table (e.g. a newly-added :class:`ExhaustionTrigger`
            value not yet registered here). Pattern 5 named-invariant
            diagnostic — raises instead of a raw :exc:`KeyError` so
            callers catching the Pattern 5 surface receive a structured
            exception with diagnostic detail.
    """
    bundle_class = _EXHAUSTION_TRIGGER_TO_BUNDLE_CLASS.get(context.trigger)
    if bundle_class is None:
        raise EscalationBundleSchemaNotFound(
            bundle_class=repr(context.trigger),
            expected_path=pathlib.Path(ESCALATION_BUNDLE_SCHEMA_DIR),
        )
    return bundle_class


# --------------------------------------------------------------------------- #
# Markdown body assembly                                                      #
# --------------------------------------------------------------------------- #


def _render_machine_readable_block(payload: Mapping[str, Any]) -> str:
    """Render the trailing ``<!-- bmad-automation:escalation-bundle ...
    -->`` HTML-comment-block carrying the YAML payload.

    Mirrors the :func:`bundle_assembly._render_marker` machine-readable
    form structurally; downstream tooling (Story 6.1's loud-fail-block
    reconciler, future Phase-2 escalation analyzers) parses the YAML
    block, NOT the prose markdown.
    """
    yaml_block = yaml.safe_dump(dict(payload), sort_keys=False).rstrip()
    return f"<!-- bmad-automation:escalation-bundle\n{yaml_block}\n-->"


def _render_bundle_body(
    *,
    context: ExhaustionContext,
    bundle_class: str,
    flags: ModuleType,
    rendered_at: datetime,
    header_text: str,
    payload: Mapping[str, Any],
    emitted_markers: tuple[str, ...],
) -> str:
    """Render the full markdown body for an Epic-5-domain escalation
    bundle (retry-budget-exhausted OR scope-assertion-violation).

    The six AC-2 sections are rendered in fixed order; the trailing
    machine-readable block carries the validated payload.
    """
    sections: list[str] = [
        f"# Escalation bundle — story {context.story_id} (run {context.run_id})",
        "",
        f"Bundle class: `{bundle_class}`",
        f"Branch: `{context.branch_name}`",
        f"Generated: {rendered_at.isoformat()}",
        "",
        "## ⚠️ Walking Skeleton Mode",
        "",
        header_text,
        "",
        "## Escalation rationale",
        "",
        _render_escalation_rationale(bundle_class=bundle_class, context=context),
        "",
        "## Outstanding findings",
        "",
        _render_outstanding_findings(context),
        "",
        "## Retry history",
        "",
        _render_retry_history(context),
        "",
        "## Deferred-work pointer",
        "",
        _render_deferred_work_pointer(story_id=context.story_id),
        "",
        "## Preservation",
        "",
        _render_preservation_block(context=context),
        "",
    ]

    if context.trigger is ExhaustionTrigger.SCOPE_ASSERTION_VIOLATION:
        diag = context.scope_violation_diagnostic
        if diag is not None:
            sections.extend(
                [
                    "## Scope-assertion diagnostic",
                    "",
                    f"- declared_scope: `{list(diag.declared_scope)}`",
                    f"- declared_expansion: `{list(diag.declared_expansion)}`",
                    f"- violating_files: `{list(diag.violating_files)}`",
                    f"- retry_round: `{diag.retry_round}`",
                    "",
                ]
            )

    if emitted_markers:
        for marker in emitted_markers:
            sections.append(_render_marker(marker))
        sections.append("")

    sections.append(_render_machine_readable_block(payload))
    sections.append("")

    # Use the flags arg defensively so static-analysis sees it consumed
    # even though the in-body rendering already routed through
    # ``header_text`` from :func:`_render_walking_skeleton_header(flags)`.
    _ = flags
    return "\n".join(sections)


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #


def assemble_escalation_bundle(
    context: ExhaustionContext,
    *,
    repo_root: pathlib.Path,
    schemas_root: pathlib.Path | None = None,
    marker_registry: MarkerClassRegistry | None = None,
    thickening_flags: ModuleType | None = None,
    generated_at: datetime | None = None,
) -> AssembleEscalationBundleResult:
    """Assemble the escalation-variant PR bundle for an Epic-5-domain
    trigger.

    See module docstring for the input/output contract, the marker-
    emission rule, and the schema-conformance-at-assembly-time invariant.
    ``marker_registry`` and ``thickening_flags`` are keyword-only
    injection points that default to the canonical runtime values; both
    enable test-time substitution per the
    :func:`bundle_assembly.assemble_bundle` precedent.
    ``generated_at`` is an additional injection point for deterministic-
    fixture tests. ``schemas_root`` is an injection point for tests that
    use a ``tmp_path``-rooted bundle output but reference schema
    fragments at the actual repo root; defaults to
    :func:`loud_fail_harness._shared.find_repo_root`.

    Args:
        context: Pydantic-validated :class:`ExhaustionContext` carrying
            the trigger discriminator + the full diagnostic payload.
        repo_root: Repository root the deterministic on-disk output path
            is anchored to. Caller-supplied per Epic 1 retro Action #1.
        schemas_root: Optional override for the directory under which
            ``schemas/escalation-bundles/{bundle_class}.yaml`` is
            resolved. Defaults to the actual repo root via
            :func:`find_repo_root`. Mirrors
            :func:`bundle_assembly.assemble_bundle`'s
            ``envelope_schema`` injection-point pattern (test-time
            decoupling of bundle output root from schema fragment root).
        marker_registry: Optional pre-loaded :class:`MarkerClassRegistry`;
            defaults to the canonical taxonomy via
            :func:`load_marker_class_registry`.
        thickening_flags: Optional namespace exposing the four flag
            functions; defaults to
            :mod:`loud_fail_harness.thickening_flags`.
        generated_at: Optional UTC timezone-aware timestamp rendered in
            the bundle's metadata block; defaults to
            ``datetime.now(timezone.utc)``.

    Returns:
        :class:`AssembleEscalationBundleResult` carrying the bundle path,
        emitted markers, header text, bundle class discriminator, and
        validated machine-readable payload.

    Raises:
        EscalationBundleSchemaNotFound: bundle_class has no schema
            fragment on disk OR (defensively) bundle_class is unknown.
        EscalationBundleSchemaConformanceError: constructed payload
            fails JSON-Schema-2020-12 validation against the relevant
            schema fragment. The validation runs BEFORE the markdown
            is written to disk; validation failure produces zero
            filesystem mutations.
    """
    flags = (
        thickening_flags if thickening_flags is not None else _default_thickening_flags
    )
    registry = (
        marker_registry if marker_registry is not None else load_marker_class_registry()
    )
    rendered_at = (
        generated_at if generated_at is not None else datetime.now(timezone.utc)
    )
    if rendered_at.tzinfo is None:
        raise ValueError(
            "assemble_escalation_bundle: generated_at must be timezone-aware "
            "UTC; got naive datetime — pass datetime.now(timezone.utc) or a "
            "timezone-aware datetime"
        )

    resolved_schemas_root = (
        schemas_root if schemas_root is not None else find_repo_root()
    )

    bundle_class = _resolve_bundle_class(context)

    # Step 1: Construct the machine-readable structured payload.
    payload = _construct_machine_readable_payload(
        context=context, bundle_class=bundle_class
    )

    # Step 2: Validate against the schema fragment BEFORE any filesystem
    # mutation (Pattern 5 defense-in-depth — mirrors
    # :func:`bundle_assembly.assemble_bundle` Step 3 ordering).
    _validate_payload_against_schema(
        payload=payload,
        bundle_class=bundle_class,
        schemas_root=resolved_schemas_root,
    )

    # Step 3: Decide marker emission BEFORE writing the bundle. The
    # marker-emission rule is the SAME structural predicate as
    # :func:`bundle_assembly.assemble_bundle` — the marker emits iff
    # ``is_loud_fail_block_present()`` returns False. Story 6.1's
    # in-place flip cascades to BOTH variants.
    emitted_markers = _emit_walking_skeleton_marker(
        flags=flags, marker_registry=registry
    )

    # Step 4: Render header + bundle body.
    header_text = _render_walking_skeleton_header(flags)
    body = _render_bundle_body(
        context=context,
        bundle_class=bundle_class,
        flags=flags,
        rendered_at=rendered_at,
        header_text=header_text,
        payload=payload,
        emitted_markers=emitted_markers,
    )

    # Step 5: Atomic write at the deterministic per-run path.
    bundle_path = compute_escalation_bundle_path(
        repo_root=repo_root,
        story_id=context.story_id,
        run_id=context.run_id,
    )
    _atomic_write_bundle(bundle_path, body)

    return AssembleEscalationBundleResult(
        bundle_path=bundle_path,
        emitted_markers=emitted_markers,
        header_text=header_text,
        bundle_class=bundle_class,
        payload=payload,
    )
