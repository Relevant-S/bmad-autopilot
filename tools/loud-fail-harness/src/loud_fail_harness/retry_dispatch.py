"""Story 5.3 — Dev fix-only retry mechanism (contract pair).

Pure-library substrate component owning the orchestrator-side
retry-dispatch surface for FR10 + FR11 + FR54: the orchestrator declares
a fix-only ``retry_mode`` flag plus an ``affected_files`` scope lock at
retry-dispatch time; the Dev specialist receives the declaration as a
prepended ``# Retry directive`` section in its prompt body; on return,
Dev's envelope reports ``scope_expanded_to`` listing any files touched
outside the declared scope. THIS module owns the directive-construction +
prompt-body composition + envelope-reading surface; the post-return
diff-vs-declaration verification is Story 5.4's territory.

This module is the THIRD Epic-5 substrate landing per ``epics.md``
lines 2218-2233 — sibling of Story 5.1's :mod:`retry_budget` and
Story 5.2's :mod:`retry_router`. It CONSUMES Story 5.2's
:class:`retry_router.ActionItem` AS-IS (the structured retry-input
shape) and Story 2.6's :data:`specialist_dispatch.PromptBodyRenderer`
type alias + :func:`specialist_dispatch.default_prompt_body_renderer`
(the base renderer composed by the renderer factory). It is the FR9
substrate-level claim CLOSER paired with Story 5.2's opener — Story 5.2
established the "structured action items derived from ``patch``-bucket
findings — never the full review prose" payload shape; THIS module
extends the structural FR9 enforcement to the renderer surface (the
rendered prompt body STRUCTURALLY EXCLUDES the envelope's ``rationale``
because the renderer's API surface only takes ``directive`` +
``action_items``, never the envelope itself).

Sources:
    * **PRD FR10** (``_bmad-output/planning-artifacts/prd.md`` line 821,
      verbatim): "On Dev retry, Orchestrator applies a capability-level
      fix-only constraint to Dev's invocation — Dev receives an explicit
      scope declaration (``affected_files``), a fix-only mode flag
      (``retry_mode: fix-only``), and an instruction to not refactor
      code outside the declared scope. The specific prompt content
      implementing this constraint is an implementation detail; the
      capability is that Dev's retry behavior is constrained to the
      declared scope."
    * **PRD FR11** (``prd.md`` line 822, verbatim): "Dev's return
      envelope declares ``scope_expanded_to``, listing any files touched
      outside the original scope lock (empty list on clean retries)."
    * **PRD FR54** (``prd.md`` line 886, verbatim): "Dev's return
      envelope includes ``proposed_commit_message`` (semantic commit
      content) and ``scope_expanded_to`` (scope declaration for retry
      diff verification)."
    * **PRD FR9** (``prd.md`` line 820) — context-firewall premise; the
      renderer's API surface STRUCTURALLY EXCLUDES the envelope's
      ``rationale`` field by accepting only ``directive`` +
      ``action_items``.
    * **Story 5.3 verbatim epic AC** at ``epics.md`` lines 2291-2325.
    * **epics.md line 2295** (verbatim, the architectural commitment
      for the contract-pair shipping discipline): "the context-firewall
      mechanism is implemented atomically as a unit (contract pairs
      that ship separately become contract pairs that drift)". This
      rationale is the structural reason the AC-5 pair test is a
      SINGLE test function (not split into orchestrator-side + Dev-side
      variants); splitting would let drift between sides slip through
      Story 5.4's verification.

Composition with Story 5.1 / 5.2 / 5.4 / 5.6:

    The orchestrator-skill's run-loop composition path post-5.3 (see
    ``skills/bmad-automation/steps/dispatch.md`` for the LLM-runtime
    prose):

        outcome = retry_router.route_envelope(run_state.last_envelope)
        if outcome is RoutingOutcome.RETRY_DEV:
            decision = retry_budget.evaluate_retry_decision(...)
            if decision is RetryDecision.DISPATCH_RETRY:
                action_items = retry_router.derive_action_items(
                    run_state.last_envelope
                )
                affected_files = retry_dispatch.derive_affected_files(
                    action_items
                )
                if not affected_files:
                    ...  # degenerate; route to Story 5.8
                directive = retry_dispatch.RetryDispatchDirective(
                    retry_mode="fix-only",
                    affected_files=affected_files,
                )
                renderer = retry_dispatch.make_retry_prompt_body_renderer(
                    directive, action_items
                )
                payload = specialist_dispatch.build_dispatch_payload(
                    ...,
                    prompt_body_renderer=renderer,
                )
                # ... dispatch via Task tool ... await Dev return ...
                scope_expanded_to = retry_dispatch.extract_scope_expanded_to(
                    dev_envelope
                )
                # Story 5.4 thickens: compare against actual git diff.

What this module does NOT own:

    * **Whole-story retry budget mechanics** — Story 5.1's
      :mod:`retry_budget`; consumed AS-IS at the orchestrator-skill
      layer (the orchestrator-skill calls
      :func:`retry_budget.evaluate_retry_decision` BEFORE this module's
      :func:`derive_affected_files`).
    * **Bucket-driven routing + action-item derivation** — Story 5.2's
      :mod:`retry_router`; consumed AS-IS via
      :class:`retry_router.ActionItem`.
    * **Scope-assertion verification (post-return diff vs. declaration)**
      — Story 5.4's verifier surface; CONSUMES THIS module's
      :func:`extract_scope_expanded_to` and the orchestrator-side
      declared ``affected_files`` to compute the diff-vs-declaration
      mismatch and emit the ``scope-assertion-violation`` marker.
    * **Retry-budget-exhausted marker emission** — Story 5.6 owns
      runtime emission. The ``retry-attempted`` orchestrator-event
      class IS schema-declared at ``schemas/orchestrator-event.yaml``
      lines 245-275 with ``retry_mode: enum [fix-only]`` +
      ``affected_files: array[string], minItems: 1`` — but THIS module
      does NOT emit the event. The event-construction helper
      (``make_retry_attempted_event``) MAY land in Story 5.4 OR Story
      5.6 alongside the runtime caller; defer per the verbatim
      open-design-choice note in the Story 5.3 dev-notes.
    * **Externalized retry history** — Story 5.5 thickens
      :class:`run_state.RetryAttempt` with per-round artifact
      references; orthogonal to THIS module's directive shape.
    * **Escalation-bundle assembly** — Story 5.8 consumes
      :func:`extract_scope_expanded_to`'s output (alongside Story 5.4's
      violation marker AND Story 5.6's exhaustion artifacts).
    * **``is_retry_present()`` flag flip** — Story 5.9 epic-close
      in-place flip per the Story 2.11 / 3.4 / 4.13 pattern.

Pluggability invariant (FR62):
    This module lives at ``tools/loud-fail-harness/src/loud_fail_harness/
    retry_dispatch.py`` (the harness substrate). The FR62 pluggability
    gate (:mod:`pluggability_gate`) scans only ``agents/*.md`` specialist
    subagent files; it does NOT scan harness substrate. The orchestrator-
    side dispatch wiring composes against this module AS DATA via Python
    imports of pure functions per ADR-001's portable-surface boundary;
    the Dev wrapper is read AS DATA (via :meth:`pathlib.Path.read_text`
    in :func:`specialist_dispatch.build_dispatch_payload`) and rendered
    by the closure this module's factory produces. Neither side imports
    the other.

Sensor-not-advisor invariant (FR52 / ADR-002 invariant 1):
    THIS module is FLOW-POLICY territory (the orchestrator's job per
    ADR-001); Dev does NOT call it; Dev RECEIVES the rendered prompt
    body the orchestrator constructs via this module's renderer factory
    and REPORTS its ``scope_expanded_to`` field on the return envelope.

Pattern conformance:
    * **Pattern 1** — module file name ``retry_dispatch.py`` is
      snake_case; function names are snake_case; class names are
      PascalCase; the ``retry_mode`` field VALUE ``"fix-only"`` is a
      kebab-case identifier sourced VERBATIM from the orchestrator-event
      schema enum at ``schemas/orchestrator-event.yaml`` line 275 (the
      schema-side enum is the authoritative constraint; see also
      :class:`RoutingOutcome` member-value precedent in
      :mod:`retry_router`).
    * **Pattern 4** — this module READS the envelope dict via
      :func:`extract_scope_expanded_to`; it adds NO new write-path to
      ``run-state.yaml``. Story 5.5 owns the ``retry_history``
      thickening; THIS module is read-only at the run-state surface.
    * **Pattern 5** — :class:`RetryDispatchError` raises loudly on
      contract violations (None envelope, non-list ``scope_expanded_to``,
      non-string items, programmer-error type mismatches). The
      :func:`make_retry_prompt_body_renderer` factory itself does not
      raise — but the returned closure inherits the base renderer's
      error-propagation behavior unchanged.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any

from loud_fail_harness.retry_router import ActionItem
from loud_fail_harness.specialist_dispatch import (
    PromptBodyRenderer,
    StoryDocResolution,
    default_prompt_body_renderer,
)


class RetryDispatchError(ValueError):
    """Raised on contract violations in :func:`derive_affected_files` /
    :func:`extract_scope_expanded_to`.

    The :class:`ValueError` lineage matches :class:`retry_router.
    RoutingError` and :class:`retry_budget.RetryBudgetConfigError`'s
    posture: per-input-shape contract violations are value-domain
    errors, not type-system errors. Subclassing :class:`ValueError`
    keeps stdlib introspection (e.g., generic ``except ValueError`` in
    higher-level error handlers) compatible while allowing precise
    ``except RetryDispatchError`` catches at the orchestrator boundary.

    Message format (per AC-1's diagnostic-shape contract; FR48a /
    NFR-O5 actionable-pointer posture): include the offending value,
    the field name, and a remediation hint so an operator pasting the
    error into a chat can identify what to change without reading
    source.
    """


@dataclasses.dataclass(frozen=True)
class RetryDispatchDirective:
    """Orchestrator-internal directive shape for fix-only retry dispatch.

    Bundles the ``retry_mode`` flag plus the ``affected_files`` scope
    lock as a single immutable value. Consumed by
    :func:`make_retry_prompt_body_renderer` to render the prepended
    ``# Retry directive`` section AND by future Story 5.4 / 5.6
    callers to construct the ``retry-attempted`` orchestrator-event
    payload (via :func:`dataclasses.asdict`).

    Field semantics:

    * ``retry_mode`` — literal ``"fix-only"`` at MVP per the
      orchestrator-event schema's enum at ``schemas/
      orchestrator-event.yaml`` line 275 (``enum: [fix-only]``).
      The field is ``str``-typed (NOT a ``Literal["fix-only"]`` typed)
      for forward-compatibility with future ``retry_mode`` values
      (e.g., ``"refactor-allowed"`` if the controlled-expansion
      pathway at ``architecture.md`` line 463 is ever introduced —
      explicitly out-of-scope at MVP). The schema-side enum constraint
      is the authoritative validator; field-level enforcement here
      would duplicate that and conflict with "validate at boundaries".
    * ``affected_files`` — frozen tuple of repo-relative file path
      strings (the scope lock declaration). Sourced from
      :func:`derive_affected_files`'s output; preserved verbatim from
      :class:`retry_router.ActionItem`'s ``location`` field. At least 1
      entry per the orchestrator-event schema's ``minItems: 1``
      constraint at line 269; the dataclass itself does NOT enforce
      ``minItems`` at construction (rationale: the constraint lives at
      the event-emission boundary; dataclass-side enforcement would
      duplicate schema enforcement). Tests assert that the
      orchestrator-side composition path naturally produces
      ``len(affected_files) >= 1`` because
      ``RoutingOutcome.RETRY_DEV`` requires ≥ 1 ``patch[HIGH|MED]``
      finding (per Story 5.2 AC-2), which guarantees ≥ 1
      :class:`ActionItem` with a non-empty ``location``.

    ``frozen=True`` (hashable, immutable; matches :class:`retry_router.
    ActionItem` and :class:`retry_router.DeferredFinding`'s precedent).
    Field-declaration order is load-bearing for byte-stable
    :func:`dataclasses.asdict` output — downstream consumers (Story
    5.4 / 5.6 ``retry-attempted`` event-payload construction) splice
    the ``asdict`` result into the event payload and depend on the
    declared field order matching the property listing order for
    ``retry_mode`` and ``affected_files`` in the ``retry-attempted``
    event class at ``schemas/orchestrator-event.yaml`` (the
    ``properties`` section, not the event-level ``required`` array).

    NO ``__post_init__`` validation at MVP — same rationale as
    :class:`retry_router.ActionItem`: defensive re-validation here
    would duplicate the schema enforcement performed at the
    event-emission boundary AND conflict with "validate at boundaries;
    trust internal data".
    """

    retry_mode: str
    affected_files: tuple[str, ...]


def derive_affected_files(
    action_items: Sequence[ActionItem],
) -> tuple[str, ...]:
    """Extract a deduplicated tuple of repo-relative file paths from
    :class:`ActionItem` ``location`` fields.

    Pure function. No I/O; no mutation of the input sequence; no side
    effects. Iterates ``action_items`` in input order and extracts the
    file-path prefix per the rule:

    * Empty ``location`` (``""``) → SKIPPED (not a file-anchored
      finding per ``envelope.schema.yaml`` line 159).
    * ``location`` containing ``":"`` → split on the LAST ``":"``
      (equivalent to ``location.rsplit(":", 1)[0]``); the prefix is
      the file path (handles both ``"file:line"`` and the
      ``"file:line:col"`` shape gracefully).
    * ``location`` without ``":"`` → use AS-IS as the file path
      (some findings are file-level without a line anchor).

    Deduplicates while preserving first-occurrence order: multiple
    :class:`ActionItem` instances anchored at the same file (e.g., at
    different lines) collapse to one entry. The order matches the
    order findings appeared in the source envelope per
    :func:`retry_router.derive_action_items`'s order-preservation
    contract.

    Empty input ``()`` → returns ``()`` (well-defined; not an error).
    All-empty-locations input → returns ``()`` (every item had
    ``location: ""``); the caller is expected to surface this as a
    degenerate case (a no-scope retry contradicts FR10's capability
    framing — the orchestrator-skill at runtime SHOULD escalate per
    the LLM-runtime composition prose at
    ``skills/bmad-automation/steps/dispatch.md``).

    Raises :exc:`RetryDispatchError` if any ``action_item.location`` is
    not a string (programmer-error invariant; the upstream
    :func:`specialist_dispatch.validate_return_envelope` already
    enforces the type at the envelope layer, so a non-string would
    indicate a substrate bug).
    """
    seen: set[str] = set()
    paths: list[str] = []
    for index, item in enumerate(action_items):
        location = item.location
        if not isinstance(location, str):
            raise RetryDispatchError(
                f"action_items[{index}].location must be a str; "
                f"got {type(location).__name__} ({location!r}). "
                "Remediation: this indicates an upstream substrate "
                "bug — validate_return_envelope should have rejected "
                "the envelope before retry_router.derive_action_items "
                "produced this ActionItem; file an issue."
            )
        if not location:
            continue
        if ":" in location:
            file_path = location.rsplit(":", 1)[0]
        else:
            file_path = location
        if file_path in seen:
            continue
        seen.add(file_path)
        paths.append(file_path)
    return tuple(paths)


def make_retry_prompt_body_renderer(
    directive: RetryDispatchDirective,
    action_items: Sequence[ActionItem],
    *,
    base_renderer: PromptBodyRenderer = default_prompt_body_renderer,
) -> PromptBodyRenderer:
    """Construct a :data:`PromptBodyRenderer` that prepends the
    ``# Retry directive (fix-only mode — Story 5.3)`` section.

    Pure factory. The captured ``directive`` + ``action_items`` are
    closed over BY-VALUE at factory-call time; subsequent mutation
    attempts (which the ``frozen=True`` dataclass forbids anyway) do
    NOT reach into the returned closure's view of the directive.

    The returned closure conforms to :data:`PromptBodyRenderer`'s
    signature ``(agent_definition_text, story_doc_resolution,
    attempt_number) -> str``. It produces output of the shape:

        # Retry directive (fix-only mode — Story 5.3)

        retry_mode: fix-only

        affected_files:
          src/foo.py
          src/bar.py

        action_items:
        - F-1 [src/foo.py:10] (severity=HIGH) — make foo do X
        - F-2 [src/bar.py:25] (severity=MED) — make bar do Y

        Constrain your work to the files listed under `affected_files`. ...

        On clean retries (no scope expansion), set `scope_expanded_to: []`. ...

        <base_renderer's output appended below, separated by a blank line>

    The capability-level constraint instruction + ``scope_expanded_to``
    reporting reminder are sourced VERBATIM per AC-3 to keep contract
    substrings detectable by tests AND to reduce drift risk against
    the FR10 capability surface.

    The base renderer's output is APPENDED AS-IS — it composes the
    agent-definition text, story context, AC list, and return contract
    per its existing contract at
    :func:`specialist_dispatch.default_prompt_body_renderer`. The
    envelope's ``rationale`` field is NEVER passed to this factory
    (the API surface accepts only ``directive`` + ``action_items``);
    this is the FR9 context-firewall structural enforcement at the
    renderer surface — the rationale CANNOT leak through this path.
    """
    captured_directive = directive
    captured_action_items = tuple(action_items)

    def renderer(
        agent_definition_text: str,
        story_doc_resolution: StoryDocResolution,
        attempt_number: int,
    ) -> str:
        affected_files_block = "\n".join(
            f"  {path}" for path in captured_directive.affected_files
        )
        action_items_block = "\n".join(
            f"- {item.finding_id} [{item.location}] "
            f"(severity={item.severity}) — {item.required_change}"
            for item in captured_action_items
        )
        directive_section = (
            "# Retry directive (fix-only mode — Story 5.3)\n"
            "\n"
            f"retry_mode: {captured_directive.retry_mode}\n"
            "\n"
            "affected_files:\n"
            f"{affected_files_block}\n"
            "\n"
            "action_items:\n"
            f"{action_items_block}\n"
            "\n"
            "Constrain your work to the files listed under "
            "`affected_files`. If your fix structurally requires "
            "touching files outside this scope, populate "
            "`scope_expanded_to` with the additional file paths in "
            "your return envelope. Do NOT silently expand scope; the "
            "orchestrator verifies your reported `scope_expanded_to` "
            "against your actual diff (Story 5.4).\n"
            "\n"
            "On clean retries (no scope expansion), set "
            "`scope_expanded_to: []`. On scope expansion, list every "
            "file path you touched outside `affected_files`."
        )
        base_output = base_renderer(
            agent_definition_text, story_doc_resolution, attempt_number
        )
        return f"{directive_section}\n\n{base_output}"

    return renderer


def extract_scope_expanded_to(
    envelope: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    """Extract the ``scope_expanded_to`` declaration from a Dev return
    envelope as a frozen tuple of repo-relative file paths.

    Pure function. No I/O; no mutation of the input mapping.

    Behavior table:

    ============================================  =============================
    Envelope shape                                Returned value
    ============================================  =============================
    ``None``                                      raises :exc:`RetryDispatchError`
    Missing ``scope_expanded_to`` key             ``()``
    ``scope_expanded_to: []``                     ``()``
    ``scope_expanded_to: ["a", "b"]``             ``("a", "b")`` (order preserved)
    ``scope_expanded_to: "not a list"``           raises :exc:`RetryDispatchError`
    ``scope_expanded_to: [123, "a"]`` (non-str)   raises :exc:`RetryDispatchError`
    ============================================  =============================

    Rationale for "missing key → ``()``": the field is OPTIONAL per
    the envelope schema (``envelope.schema.yaml`` lines 96-101 declare
    ``scope_expanded_to`` outside the top-level ``required`` list);
    non-Dev specialists never emit it; first-dispatch Dev envelopes
    (Epic 2) hardcode ``[]``. Returning ``()`` for absent + ``[]`` is
    the same observable result and matches the schema's "field absence
    == empty list" semantics.

    Rationale for None-envelope hard-fail: the orchestrator-skill MUST
    invoke :func:`specialist_dispatch.validate_return_envelope` before
    reaching this function; a ``None`` envelope here indicates a
    substrate composition error.

    Rationale for type-mismatch hard-fail: the upstream
    :func:`specialist_dispatch.validate_return_envelope` already
    rejects malformed shapes against ``envelope.schema.yaml``, so a
    type-mismatch here would indicate either a substrate bug OR a
    caller skipping validation. Loud-fail per Pattern 5.
    """
    if envelope is None:
        raise RetryDispatchError(
            "envelope must be a non-None Mapping; got None. "
            "Remediation: orchestrator-skill must call "
            "specialist_dispatch.validate_return_envelope before "
            "extract_scope_expanded_to per the dispatch.md "
            "load-bearing post-dispatch ordering."
        )
    if "scope_expanded_to" not in envelope:
        return ()
    raw = envelope["scope_expanded_to"]
    if not isinstance(raw, list):
        raise RetryDispatchError(
            f"envelope['scope_expanded_to'] must be a list per "
            f"envelope.schema.yaml lines 96-101 (array of string); "
            f"got {type(raw).__name__} ({raw!r}). "
            "Remediation: re-validate the envelope via "
            "specialist_dispatch.validate_return_envelope; the "
            "schema's array constraint should have rejected this "
            "shape upstream."
        )
    for index, item in enumerate(raw):
        if not isinstance(item, str):
            raise RetryDispatchError(
                f"envelope['scope_expanded_to'][{index}] must be a "
                f"str per envelope.schema.yaml line 100 "
                f"(items.type: string); got {type(item).__name__} "
                f"({item!r}). Remediation: re-validate the envelope "
                "via specialist_dispatch.validate_return_envelope."
            )
    return tuple(raw)


__all__ = [
    "RetryDispatchDirective",
    "RetryDispatchError",
    "derive_affected_files",
    "extract_scope_expanded_to",
    "make_retry_prompt_body_renderer",
]
