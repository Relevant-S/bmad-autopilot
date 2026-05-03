"""Story 5.2 — Bucket-driven action-item derivation + retry routing.

Pure-library substrate component owning the orchestrator-side
bucket-driven routing surface for FR9 + FR8 composition: classify a
specialist return envelope into one of four flow-policy outcomes
(``RETRY_DEV`` / ``ESCALATE`` / ``DEFER_AND_ADVANCE`` /
``DISMISS_AND_ADVANCE``); derive structured action items from
``patch[HIGH|MED]`` findings (the FR9 context-firewall payload — never
the full review prose); render the ``defer``-bucket sink as an
append-only section in ``deferred-work.md`` (format-MVP per Story 5.7's
forward-pointer).

This module is the SECOND Epic-5 substrate landing per ``epics.md``
lines 2218-2233 — sibling of Story 5.1's :mod:`retry_budget`. The two
modules COMPOSE at the orchestrator-skill's retry-routing seam (route
first, then budget-check on :attr:`RoutingOutcome.RETRY_DEV`); see
``skills/bmad-automation/steps/run.md`` for the LLM-runtime composition
prose. THIS module is BUDGET-AGNOSTIC; :mod:`retry_budget` is
BUCKET-AGNOSTIC; the two functions live in separate modules so the
orchestrator-skill can swap one without affecting the other (Pattern of
"one module per flow-policy concern").

Sources:
    * **PRD FR9** (``_bmad-output/planning-artifacts/prd.md`` line 820,
      verbatim): "Orchestrator routes retry findings back to the
      responsible specialist using structured action items derived from
      ``patch``-bucket findings — never the full review prose."
    * **PRD FR8** (``prd.md`` line 819) — composed Epic-5 sibling per
      Story 5.1 lander; THIS module's :attr:`RoutingOutcome.RETRY_DEV`
      outcome routes through :func:`retry_budget.evaluate_retry_decision`
      at the orchestrator-skill seam.
    * **PRD FR27** (``prd.md`` line 846) — "Review-BMAD uses BMAD's
      existing finding taxonomy (``decision_needed | patch | defer |
      dismiss``) with ``HIGH | MED | LOW`` severity — no new buckets
      introduced by the Automator." THIS module's enum-value posture
      honors this verbatim.
    * **Story 5.2 verbatim epic AC** at ``epics.md`` lines 2264-2289.
    * **Story 3.2** lander — finding-taxonomy passthrough; the upstream
      that exposes ``bucket`` verbatim for THIS module to consume as
      the routing key directly (no re-derivation, no re-classification).

Routing rule table (canonical reference; verbatim from epics.md lines
2274-2278 + per-finding-precedence elaboration):

    ============================================================  ===========================
    Envelope ``findings`` content                                  Returned ``RoutingOutcome``
    ============================================================  ===========================
    ≥ 1 finding with ``bucket: decision_needed`` (any severity)   :attr:`ESCALATE`
    ≥ 1 ``patch[HIGH|MED]`` AND no ``decision_needed``            :attr:`RETRY_DEV`
    ≥ 1 ``defer`` AND only ``defer``/``dismiss``/``patch[LOW]``    :attr:`DEFER_AND_ADVANCE`
    ≥ 1 ``dismiss`` AND only ``dismiss``/``patch[LOW]``           :attr:`DISMISS_AND_ADVANCE`
    Only ``patch[LOW]`` findings                                  :attr:`DISMISS_AND_ADVANCE`
    ============================================================  ===========================

Precedence ordering (load-bearing for AC-2 conformance):

    1. ``decision_needed`` PREEMPTS all other buckets — needs human
       input; running a Dev retry on ``patch`` findings while a
       ``decision_needed`` finding is unresolved would force the
       practitioner to choose between two interleaved cycles.
    2. ``patch[HIGH|MED]`` triggers :attr:`RoutingOutcome.RETRY_DEV`.
       LOW-severity ``patch`` findings DO NOT trigger retries (per
       epics.md line 2275 — "patch (HIGH/MED) → trigger Dev retry").
    3. ``defer`` → :attr:`DEFER_AND_ADVANCE` (record + advance).
    4. ``dismiss`` only → :attr:`DISMISS_AND_ADVANCE` (advance silently).
    5. ``patch[LOW]``-only carve-out → :attr:`DISMISS_AND_ADVANCE` —
       valid sensor observations the reviewer chose to surface; the
       reviewer did not classify them as defer/dismiss/decision-needed,
       but they are not retry-eligible per rule 2; advancing without
       retry is correct flow-policy.

Structural action-item shape (the FR9 context-firewall payload):
    :class:`ActionItem` is a ``dataclass(frozen=True)`` with the four
    required fields ``{finding_id, location, required_change, severity}``.
    The architecture pattern is "Pydantic at boundaries, dataclasses at
    flow-policy internals" — Pydantic models live in
    :mod:`run_state` / :mod:`specialist_dispatch` for envelope-shape
    contracts (validated boundaries); :class:`ActionItem` is an
    orchestrator-internal payload consumed by Story 5.3's
    ``affected_files`` derivation. Re-validation at the dataclass layer
    would duplicate ``envelope.schema.yaml`` enforcement (already
    performed at :func:`specialist_dispatch.validate_return_envelope`
    time) and conflicts with the "validate at boundaries; trust internal
    data" principle. ``frozen=True`` provides hashability + immutability
    + zero-runtime-validation overhead; mirrors :mod:`bundle_assembly`'s
    precedent for orchestrator-internal accumulation structures.

Story 3.2 passthrough composition:
    The ``bucket`` field arrives verbatim from :mod:`bmad-code-review`
    via the finding-taxonomy passthrough Story 3.2 established. THIS
    module does NOT re-derive or re-classify; it consumes ``bucket`` as
    the routing key directly (per epics.md line 2279 — "the routing
    logic uses ``bucket`` as the routing key directly (no extra parsing
    per Story 3.2's passthrough)").

Story 5.1 composition discipline:
    THIS module returns :attr:`RoutingOutcome.RETRY_DEV` for
    ``patch``-bucket findings; the orchestrator-skill THEN consults
    :func:`retry_budget.evaluate_retry_decision` to determine whether
    budget remains. Composition order: route first, then budget-check.
    THIS module is BUDGET-AGNOSTIC, mirroring 5.1's BUCKET-AGNOSTIC
    posture. See ``skills/bmad-automation/steps/run.md`` for the
    LLM-runtime composition prose.

What this module does NOT own:
    * **Wrapper-side ``retry_mode: fix-only`` + ``affected_files`` +
      ``scope_expanded_to`` plumbing** — Story 5.3's contract pair
      surface; CONSUMES :class:`ActionItem` as the input to its
      ``affected_files`` derivation per epics.md line 2302.
    * **Scope-assertion verification** — Story 5.4's verifier; consumes
      Story 5.3's ``scope_expanded_to`` declaration.
    * **Externalized retry history** — Story 5.5 thickens
      :class:`RunState.retry_history` with per-round artifact references.
    * **Retry-budget-exhausted marker emission** — Story 5.6 owns
      runtime emission + the parallel ``retry-budget-exhausted``
      orchestrator-event class.
    * **``deferred-work.md`` format spec audit** — Story 5.7 may tighten
      the format; THIS story commits to the bullet-line MVP via
      :func:`record_defer_findings`.
    * **Escalation-bundle assembly** — Story 5.8 consumes THIS module's
      :attr:`RoutingOutcome.ESCALATE` outcome.
    * **``is_retry_present()`` flag flip** — Story 5.9 epic-close in-place
      flip per the Story 2.11 / 3.4 / 4.13 pattern.

Pluggability invariant (FR62):
    This module lives at ``tools/loud-fail-harness/src/loud_fail_harness/
    retry_router.py`` (the harness substrate). The FR62 pluggability
    gate (:mod:`pluggability_gate`) scans only ``agents/*.md`` specialist
    subagent files; it does NOT scan harness substrate. The new module
    does not affect gate behavior.

Sensor-not-advisor invariant (FR52 / ADR-002 invariant 1):
    THIS module is FLOW-POLICY territory (the orchestrator's job per
    ADR-001); specialists do not call it. Specialists return envelopes
    that THIS module CONSUMES.

Pattern conformance:
    * **Pattern 1** — module file name ``retry_router.py`` is snake_case;
      function names are snake_case; :class:`RoutingOutcome` enum-member
      values are kebab-case identifier strings (precedent:
      :class:`retry_budget.RetryDecision`); :class:`Severity` enum-member
      values are uppercase per the envelope schema's literal enum (the
      FR27 / Story 3.2 verbatim-preservation invariant overrides
      Pattern 1's "kebab-case identifier values" default for this
      specific case).
    * **Pattern 4** — this module READS :attr:`RunState.last_envelope`
      via :func:`route_envelope`; it adds NO new write-path to
      ``run-state.yaml``. The :func:`record_defer_findings` write is to
      a DIFFERENT file (``_bmad-output/implementation-artifacts/
      deferred-work.md``) and does NOT participate in the canonical
      ``run-state.yaml`` ↔ story-doc atomic-write discipline.
    * **Pattern 5** — :class:`RoutingError` raises loudly on contract
      violations (None envelope, unknown bucket, ``status: pass``,
      missing findings). :func:`record_defer_findings` propagates
      :exc:`OSError` unchanged (disk failures are halt conditions).
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: Canonical bucket enum from ``schemas/envelope.schema.yaml`` line 164,
#: preserved verbatim per FR27 / Story 3.2's "no new buckets" invariant.
_VALID_BUCKETS: frozenset[str] = frozenset(
    {"decision_needed", "patch", "defer", "dismiss"}
)

#: Canonical severity enum from ``schemas/envelope.schema.yaml`` line 167,
#: preserved verbatim (uppercase) per the FR27 invariant.
_VALID_SEVERITIES: frozenset[str] = frozenset({"HIGH", "MED", "LOW"})

#: Severities that make a ``patch``-bucket finding retry-eligible per
#: epics.md line 2275 — "patch (HIGH/MED) → trigger Dev retry".
_RETRY_ELIGIBLE_PATCH_SEVERITIES: frozenset[str] = frozenset({"HIGH", "MED"})

#: Required finding-shape keys this module reads. Mirrors
#: ``envelope.schema.yaml`` ``$defs/finding.required`` minus ``source`` /
#: ``title`` (consumed by other surfaces; not load-bearing for routing).
_REQUIRED_FINDING_KEYS: frozenset[str] = frozenset(
    {"id", "detail", "location", "bucket", "severity"}
)


class RoutingError(ValueError):
    """Raised on contract violations in :func:`route_envelope` /
    :func:`derive_action_items` / :func:`derive_deferred_findings`.

    The :class:`ValueError` lineage matches :class:`retry_budget.
    RetryBudgetConfigError`'s posture: per-input-shape contract
    violations are value-domain errors, not type-system errors.
    Subclassing :class:`ValueError` keeps stdlib introspection (e.g.,
    generic ``except ValueError`` in higher-level error handlers)
    compatible while allowing precise ``except RoutingError`` catches at
    the orchestrator boundary.

    Message format (per AC-1's diagnostic-shape contract; FR48a /
    NFR-O5 actionable-pointer posture): include the offending value, the
    field name, and a remediation hint so an operator pasting the error
    into a chat can identify what to change without reading source.
    """


class RoutingOutcome(enum.Enum):
    """Orchestrator-side routing decision returned by :func:`route_envelope`.

    Four members map 1:1 to the four-bucket → four-outcome routing rule
    (per epics.md lines 2274-2278):

    * :attr:`RETRY_DEV` — at least one finding has ``bucket: patch`` AND
      ``severity in {HIGH, MED}`` (and no ``decision_needed`` finding
      preempts); orchestrator should derive action items via
      :func:`derive_action_items` and dispatch a Dev retry (gated by
      :func:`retry_budget.evaluate_retry_decision`).
    * :attr:`ESCALATE` — at least one finding has ``bucket:
      decision_needed`` (PREEMPTS all other buckets per AC-2 precedence
      rule 1); orchestrator routes to Story 5.8's escalation handler
      (no retry — needs human input).
    * :attr:`DEFER_AND_ADVANCE` — no ``decision_needed``, no
      ``patch[HIGH|MED]``, AND ≥ 1 ``defer`` finding; orchestrator
      records each ``defer`` finding to ``deferred-work.md`` via
      :func:`record_defer_findings` and advances state.
    * :attr:`DISMISS_AND_ADVANCE` — no ``decision_needed``, no
      ``patch[HIGH|MED]``, no ``defer``; orchestrator advances state
      without recording (the findings are sensor-observations the
      reviewer chose to surface but explicitly classify as no-action,
      OR the only findings are ``patch[LOW]`` per AC-2 rule 5 carve-out).

    Member-value strings are kebab-case identifier strings per Pattern 1
    (precedent: :class:`retry_budget.RetryDecision` member values).
    """

    RETRY_DEV = "retry-dev"
    ESCALATE = "escalate"
    DEFER_AND_ADVANCE = "defer-and-advance"
    DISMISS_AND_ADVANCE = "dismiss-and-advance"


class Severity(enum.Enum):
    """Finding severity discriminator.

    Member values mirror the envelope schema's ``$defs/finding.severity``
    enum verbatim (uppercase, per ``schemas/envelope.schema.yaml`` line
    167). This is the rare case where the upstream BMAD-core envelope
    shape dictates the literal form, so Pattern 1's "identifier values
    are kebab-case" rule is overridden by the FR27 / Story 3.2 "no new
    taxonomy values; preserve BMAD's literals verbatim" invariant.

    The enum exists for caller convenience (typed access to severity vs.
    magic strings); the :class:`ActionItem` dataclass-side ``severity``
    field commits to the literal string form (``"HIGH"`` / ``"MED"`` /
    ``"LOW"``) for byte-stability + JSON-round-trippability. Callers may
    convert string ↔ enum via ``Severity(value)`` / ``severity.value``
    as needed.
    """

    HIGH = "HIGH"
    MED = "MED"
    LOW = "LOW"


def _normalize_severity(severity: Any) -> str:
    """Normalize a severity value to its canonical string form.

    Accepts either a :class:`Severity` enum member or a raw string,
    returning the string value in both cases. This permits callers to
    pass either form to the routing functions without raising
    :class:`RoutingError`.
    """
    if isinstance(severity, Severity):
        return severity.value
    return severity  # type: ignore[return-value]


@dataclasses.dataclass(frozen=True)
class ActionItem:
    """Structured retry-input shape per FR9 (the context-firewall payload).

    Four required fields, populated from a single envelope finding (which
    must have ``bucket: patch`` AND ``severity in {HIGH, MED}`` to be
    retry-eligible per :func:`derive_action_items`):

    * ``finding_id`` — sourced from the envelope finding's ``id`` field
      (``envelope.schema.yaml`` ``$defs/finding.id`` is ``string,
      minLength: 1``).
    * ``location`` — sourced from ``location`` (``"file:line"`` form OR
      ``""`` for non-file-anchored findings per envelope schema).
    * ``required_change`` — sourced from the envelope finding's
      ``detail`` field (``string, minLength: 1`` per schema). The naming
      "required_change" (vs. raw "detail") reflects FR9's framing: what
      the action item REQUIRES the recipient (Dev) to do.
    * ``severity`` — sourced from ``severity``; preserved AS-IS as the
      literal string (``"HIGH"`` / ``"MED"``); NOT normalized to
      :class:`Severity` (callers may convert if needed; the dataclass
      commits to the string form for byte-stability +
      JSON-round-trippability, mirroring the envelope-side dict surface).

    ``frozen=True`` (hashable, immutable; matches :class:`run_state.
    RetryAttempt`'s frozen-Pydantic posture). Field-declaration order is
    load-bearing for byte-stable :func:`dataclasses.asdict` output —
    Story 5.3 composes against ``dataclasses.asdict(item)`` to splice
    into the dispatch payload.

    NO ``__post_init__`` validation at MVP — the upstream envelope was
    already validated against ``envelope.schema.yaml`` at
    :func:`specialist_dispatch.validate_return_envelope` time, so the
    values are pre-shaped per the schema; defensive re-validation here
    would duplicate schema enforcement and conflict with "validate at
    boundaries; trust internal data".
    """

    finding_id: str
    location: str
    required_change: str
    severity: str


@dataclasses.dataclass(frozen=True)
class DeferredFinding:
    """Structured ``deferred-work.md``-append payload.

    Four required fields, populated from a single envelope finding with
    ``bucket: defer`` (severity-agnostic):

    * ``finding_id`` — sourced from the envelope finding's ``id`` field.
    * ``location`` — sourced from ``location``.
    * ``description`` — sourced from the envelope finding's ``detail``
      field (same field used for :attr:`ActionItem.required_change` but
      renamed at the deferred-work layer because the semantics are
      "what was deferred" not "what must change").
    * ``source_story_id`` — the BMAD story identifier the deferral
      originated from (required for the ``deferred-work.md``'s
      "Deferred from: code review of <story-id>" header per the existing
      format observed at ``_bmad-output/implementation-artifacts/
      deferred-work.md``).

    ``frozen=True``; field-declaration order is load-bearing for
    byte-stability.
    """

    finding_id: str
    location: str
    description: str
    source_story_id: str


def _validate_envelope_shape(envelope: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Guard the envelope-shape contract for routing-eligible callers.

    Centralizes the contract checks shared by :func:`route_envelope`,
    :func:`derive_action_items`, and :func:`derive_deferred_findings`:
    envelope must be a non-None mapping with a non-pass ``status`` and
    a non-empty ``findings`` array.
    """
    if envelope is None:
        raise RoutingError(
            "envelope must be a non-None mapping; got None — orchestrator-skill "
            "must call validate_return_envelope before route_envelope / "
            "derive_action_items / derive_deferred_findings"
        )

    if not isinstance(envelope, Mapping):
        raise RoutingError(
            f"envelope must be a Mapping; got {type(envelope).__name__}: "
            f"{envelope!r} — orchestrator-skill must pass the deserialized "
            f"envelope dict from validate_return_envelope"
        )

    status = envelope.get("status")
    if status == "pass":
        raise RoutingError(
            "route_envelope is only called for non-pass returns; got "
            "status='pass' — the orchestrator-skill's flow-policy code "
            "must branch on status BEFORE calling route_envelope"
        )

    findings = envelope.get("findings")
    if findings is None:
        raise RoutingError(
            "envelope must have a 'findings' array; got missing/None — "
            "envelope.schema.yaml requires findings; orchestrator-skill "
            "must call validate_return_envelope before route_envelope"
        )

    if not isinstance(findings, Sequence) or isinstance(findings, (str, bytes)):
        raise RoutingError(
            f"envelope['findings'] must be a sequence; got "
            f"{type(findings).__name__}: {findings!r} — "
            f"envelope.schema.yaml $defs declares findings as an array"
        )

    if len(findings) == 0:
        raise RoutingError(
            "envelope['findings'] must be non-empty for non-pass status; "
            "got [] — orchestrator-skill must branch on status BEFORE calling "
            "route_envelope; route_envelope is only for non-pass envelopes with findings"
        )

    return envelope


def _validate_finding_shape(finding: Any, *, index: int) -> Mapping[str, Any]:
    """Guard a single finding's shape for routing-eligible callers.

    Validates that the finding is a Mapping with all required keys AND
    a known ``bucket`` / ``severity`` value (forward-compat loud-fail
    per Story 3.2 — unknown enum values surface as :class:`RoutingError`).
    """
    if not isinstance(finding, Mapping):
        raise RoutingError(
            f"envelope['findings'][{index}] must be a Mapping; got "
            f"{type(finding).__name__}: {finding!r} — "
            f"envelope.schema.yaml $defs/finding declares each finding as "
            f"a dict-shaped object"
        )

    missing = _REQUIRED_FINDING_KEYS - set(finding.keys())
    if missing:
        raise RoutingError(
            f"envelope['findings'][{index}] missing required keys "
            f"{sorted(missing)}; got keys {sorted(finding.keys())} — "
            f"routing validation requires id, detail, location, bucket, severity "
            f"(envelope.schema.yaml $defs/finding also requires source and title "
            f"— validated upstream by validate_return_envelope)"
        )

    bucket = finding["bucket"]
    if bucket not in _VALID_BUCKETS:
        raise RoutingError(
            f"unknown bucket value {bucket!r} at envelope['findings'][{index}]; "
            f"envelope.schema.yaml $defs/finding.bucket enumerates "
            f"{sorted(_VALID_BUCKETS)} — a new bucket value is a "
            f"BMAD-extension event requiring docs/extension-audit.md "
            f"classification per Story 1.11"
        )

    severity = _normalize_severity(finding["severity"])
    if severity not in _VALID_SEVERITIES:
        raise RoutingError(
            f"unknown severity value {severity!r} at "
            f"envelope['findings'][{index}]; envelope.schema.yaml "
            f"$defs/finding.severity enumerates {sorted(_VALID_SEVERITIES)} — "
            f"a new severity value is a BMAD-extension event requiring "
            f"docs/extension-audit.md classification per Story 1.11"
        )

    return finding


def route_envelope(envelope: Mapping[str, Any] | None) -> RoutingOutcome:
    """Classify a specialist return envelope into a flow-policy outcome.

    Pure function: no I/O; no mutation of inputs; no global-state
    mutation; idempotent (repeated calls with the same envelope return
    the same :class:`RoutingOutcome`).

    Consumes a deserialized envelope ``dict`` (the
    :attr:`run_state.RunState.last_envelope` shape per ``run_state.py``
    line 383 / ``schemas/run-state.yaml``); returns a
    :class:`RoutingOutcome` member per the routing rule table +
    precedence ordering documented in this module's docstring.

    Precedence ordering (load-bearing):

    1. ``decision_needed`` PREEMPTS — any finding with this bucket
       returns :attr:`RoutingOutcome.ESCALATE`.
    2. ``patch[HIGH|MED]`` → :attr:`RoutingOutcome.RETRY_DEV` (LOW
       severity ``patch`` findings are intentionally NOT retry-eligible).
    3. ``defer`` (any severity) → :attr:`RoutingOutcome.DEFER_AND_ADVANCE`.
    4. ``dismiss`` only → :attr:`RoutingOutcome.DISMISS_AND_ADVANCE`.
    5. ``patch[LOW]``-only carve-out → :attr:`RoutingOutcome.
       DISMISS_AND_ADVANCE` (valid sensor observations the reviewer
       chose to surface; not retry-eligible per rule 2; advancing
       without retry is correct flow-policy).

    Raises :class:`RoutingError` on contract violations: ``envelope is
    None``; envelope is not a Mapping; ``status: pass`` (programmer
    error — caller should branch on status BEFORE calling); ``findings``
    is missing or empty (programmer error); finding has unknown
    ``bucket`` / ``severity`` value (forward-compat loud-fail per
    Story 3.2 + Story 1.11 BMAD-extension classification path); finding
    is missing required shape keys.
    """
    validated = _validate_envelope_shape(envelope)

    has_decision_needed = False
    has_retry_eligible_patch = False
    has_defer = False
    has_dismiss = False

    for index, finding in enumerate(validated["findings"]):
        shape = _validate_finding_shape(finding, index=index)
        bucket = shape["bucket"]
        severity = _normalize_severity(shape["severity"])

        if bucket == "decision_needed":
            has_decision_needed = True
        elif bucket == "patch":
            if severity in _RETRY_ELIGIBLE_PATCH_SEVERITIES:
                has_retry_eligible_patch = True
            # patch[LOW] does NOT trigger retry per epics.md line 2275;
            # falls through to the rule-5 carve-out below.
        elif bucket == "defer":
            has_defer = True
        elif bucket == "dismiss":
            has_dismiss = True
        # No other branch reachable: _validate_finding_shape rejects
        # unknown bucket values; this is exhaustive over _VALID_BUCKETS.

    if has_decision_needed:
        return RoutingOutcome.ESCALATE
    if has_retry_eligible_patch:
        return RoutingOutcome.RETRY_DEV
    if has_defer:
        return RoutingOutcome.DEFER_AND_ADVANCE
    # Remaining cases: dismiss-only, patch[LOW]-only, or any mix of the
    # two. All advance silently per AC-2 rules 4 + 5.
    _ = has_dismiss  # documented; no further branching needed.
    return RoutingOutcome.DISMISS_AND_ADVANCE


def derive_action_items(
    envelope: Mapping[str, Any] | None,
) -> tuple[ActionItem, ...]:
    """Derive structured action items from ``patch[HIGH|MED]`` findings.

    Pure function. Iterates ``envelope['findings']`` in original order;
    for each finding where ``bucket == "patch"`` AND ``severity in
    {"HIGH", "MED"}``, constructs an :class:`ActionItem` from the
    finding's ``id`` / ``location`` / ``detail`` / ``severity`` fields.

    Returns a frozen ``tuple[ActionItem, ...]``; empty input (no
    retry-eligible patch findings) returns ``()``. Order is preserved
    from the envelope's ``findings`` array (the specialist's order is
    the action-item order — Dev sees them in the same sequence the
    reviewer surfaced them).

    Critical invariant (the FR9 context-firewall premise; AC-5
    regression baseline): ``required_change`` is sourced from the
    finding's ``detail`` field, and NOTHING ELSE from the envelope is
    included. The envelope's ``rationale`` field (review prose
    narrative) is NOT included in any :class:`ActionItem`. The
    envelope's other findings (non-patch, or ``patch[LOW]``) are NOT
    included.

    Raises :class:`RoutingError` on the same shape violations as
    :func:`route_envelope`. In practice the orchestrator-skill calls
    :func:`derive_action_items` only when :func:`route_envelope` already
    returned :attr:`RoutingOutcome.RETRY_DEV` (which guarantees ≥ 1
    retry-eligible patch finding), but the validation is duplicated for
    callers who skip the route step.
    """
    validated = _validate_envelope_shape(envelope)

    items: list[ActionItem] = []
    for index, finding in enumerate(validated["findings"]):
        shape = _validate_finding_shape(finding, index=index)
        if shape["bucket"] != "patch":
            continue
        if shape["severity"] not in _RETRY_ELIGIBLE_PATCH_SEVERITIES:
            continue
        items.append(
            ActionItem(
                finding_id=shape["id"],
                location=shape["location"],
                required_change=shape["detail"],
                severity=_normalize_severity(shape["severity"]),
            )
        )
    return tuple(items)


def derive_deferred_findings(
    envelope: Mapping[str, Any] | None,
    *,
    source_story_id: str,
) -> tuple[DeferredFinding, ...]:
    """Derive ``DeferredFinding`` tuples from ``defer``-bucket findings.

    Pure function. Iterates ``envelope['findings']`` in original order;
    for each finding where ``bucket == "defer"`` (severity-agnostic),
    constructs a :class:`DeferredFinding` from the finding's ``id`` /
    ``location`` / ``detail`` fields plus the ``source_story_id``
    keyword arg (the orchestrator-skill knows which story the envelope
    is for).

    Returns a frozen ``tuple[DeferredFinding, ...]``; empty input (no
    ``defer`` findings) returns ``()``.

    Raises :class:`RoutingError` on the same shape violations as
    :func:`route_envelope`.
    """
    validated = _validate_envelope_shape(envelope)

    if not source_story_id:
        raise RoutingError(
            "source_story_id must be a non-empty string; got "
            f"{source_story_id!r} — the deferred-work.md section header "
            "requires a story identifier (e.g., '5-2-bucket-driven-...'); "
            "the orchestrator-skill knows which story the envelope is for"
        )

    items: list[DeferredFinding] = []
    for index, finding in enumerate(validated["findings"]):
        shape = _validate_finding_shape(finding, index=index)
        if shape["bucket"] != "defer":
            continue
        items.append(
            DeferredFinding(
                finding_id=shape["id"],
                location=shape["location"],
                description=shape["detail"],
                source_story_id=source_story_id,
            )
        )
    return tuple(items)


def _default_clock() -> datetime:
    """Default clock for :func:`record_defer_findings` — UTC now."""
    return datetime.now(timezone.utc)


def record_defer_findings(
    deferred: Sequence[DeferredFinding],
    deferred_work_path: Path,
    *,
    story_id: str,
    clock: Callable[[], datetime] = _default_clock,
) -> int:
    """Append a ``deferred-work.md`` section for a sequence of findings.

    Side-effecting helper (file append) but isolated — uses
    :meth:`pathlib.Path.read_text` / :meth:`pathlib.Path.write_text` for
    a read-modify-write cycle (NOT ``open(path, "a")``) to match the
    harness's atomic-write discipline at other modules and to keep the
    helper testable without race conditions in pytest's ``tmp_path``.

    Append rule (per AC-6):

    1. If ``deferred_work_path`` does NOT exist (or exists with 0
       bytes), create the file with content ``# Deferred Work\\n\\n``.
    2. Append a new ``## Deferred from: code review of <story_id>
       (<YYYY-MM-DD>)`` section header (date derived from ``clock()``).
    3. Under the section, one bullet per :class:`DeferredFinding`
       formatted as ``- **<finding_id>** [\\`<location>\\`] —
       <description>`` (mirrors the existing convention observed at
       ``_bmad-output/implementation-artifacts/deferred-work.md`` lines
       4-14).
    4. Append a blank line after the last bullet to separate from any
       subsequent section.
    5. Return the count of records appended (``= len(deferred)``).

    Empty-input handling: per AC-6 + the dev's-call recommendation in
    the story's "Open design choices" — the function CREATES the file
    with the ``# Deferred Work`` header on empty input (consistent file
    existence post-call) but DOES NOT append a section header or
    bullets; returns ``0``. The orchestrator-skill can call the helper
    unconditionally and trust the file exists post-call.

    Args:
        deferred: Sequence of :class:`DeferredFinding` to record.
        deferred_work_path: Path to the ``deferred-work.md`` file
            (typically ``_bmad-output/implementation-artifacts/
            deferred-work.md``). The orchestrator-skill ensures the
            parent directory exists; this helper does NOT mkdir.
        story_id: The BMAD story identifier (e.g.,
            ``"5-2-bucket-driven-action-item-derivation-retry-routing"``).
            Required for the section header.
        clock: Optional callable returning a :class:`datetime` for
            deterministic test-side date stamps; default
            :func:`_default_clock` returns UTC ``datetime.now``.

    Returns:
        The number of records appended (``= len(deferred)``).

    Raises:
        OSError: Propagated unchanged from
            :meth:`pathlib.Path.read_text` /
            :meth:`pathlib.Path.write_text` (disk-full / permission-denied
            etc.) — disk failures are halt conditions per Pattern 5.
        RoutingError: If ``story_id`` is empty.
    """
    if not story_id:
        raise RoutingError(
            "story_id must be a non-empty string; got "
            f"{story_id!r} — the deferred-work.md section header "
            "requires a story identifier (e.g., '5-2-bucket-driven-...')"
        )

    if deferred_work_path.exists():
        existing = deferred_work_path.read_text(encoding="utf-8")
    else:
        existing = ""

    needs_header = not existing.strip()
    if needs_header:
        existing = "# Deferred Work\n\n"

    if len(deferred) == 0:
        # Empty-input: ensure the file exists with the header but do not
        # append a section. Recommendation per the story's Open design
        # choices: create-on-empty for caller-side consistency.
        if needs_header:
            deferred_work_path.write_text(existing, encoding="utf-8")
        return 0

    # Ensure trailing whitespace boundary before appending the new section.
    if not existing.endswith("\n\n"):
        if existing.endswith("\n"):
            existing = existing + "\n"
        else:
            existing = existing + "\n\n"

    date_stamp = clock().strftime("%Y-%m-%d")
    section_lines = [
        f"## Deferred from: code review of {story_id} ({date_stamp})\n",
        "\n",
    ]
    for item in deferred:
        section_lines.append(
            f"- **{item.finding_id}** [`{item.location}`] — {item.description}\n"
        )
    section_lines.append("\n")

    new_content = existing + "".join(section_lines)
    deferred_work_path.write_text(new_content, encoding="utf-8")
    return len(deferred)


__all__ = [
    "ActionItem",
    "DeferredFinding",
    "RoutingError",
    "RoutingOutcome",
    "Severity",
    "derive_action_items",
    "derive_deferred_findings",
    "record_defer_findings",
    "route_envelope",
]
