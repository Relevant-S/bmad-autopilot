"""Story 5.1 — Whole-story retry budget configuration + enforcement.

Pure-library substrate component owning the orchestrator-side
budget-mechanics surface for FR8: read the ``retry_budget`` value from
``_bmad/automation/config.yaml`` (default ``2``); decide whether the
in-flight loop may dispatch another retry round (``DISPATCH_RETRY``) or
must halt for budget exhaustion (``HALT_BUDGET_EXHAUSTED``); raise
loudly on malformed config input.

This module is the FIRST Epic-5 substrate landing per ``epics.md``
lines 2218-2233. Siblings in Epic 5: 5.2 (bucket-driven action-item
routing — :mod:`retry_router`), 5.3 / 5.4 (fix-only contract pair +
scope-assertion verification), 5.5 (externalized retry-history file),
5.6 (budget-exhaustion handler — emits ``retry-budget-exhausted``
marker and preserves state per FR14), 5.7 (deferred-work spike), 5.8
(escalation-bundle assembler — consumes 5.6's exhaustion + 5.5's
history references + 5.7's deferred-work format), 5.9 (epic-close
``is_retry_present()`` flag flip).

Sources:
    * **PRD FR8** (``_bmad-output/planning-artifacts/prd.md`` line 819,
      verbatim): "Orchestrator enforces a configurable whole-story
      retry budget (default: 2; configurable via
      ``_bmad/automation/config.yaml``)."
    * **Story 5.1 verbatim epic AC** at ``epics.md`` lines 2236-2262
      (the Epic 5 sequence's first substrate primitive).
    * **Story 2.2** lander — :class:`loud_fail_harness.run_state.RunState`
      Pydantic model + :class:`loud_fail_harness.run_state.RetryAttempt`
      shape; this module composes against the existing schema-version
      1.1 run-state cache AS-IS.
    * **Story 1.4** lander — ``schemas/marker-taxonomy.yaml`` lines
      247-252 enumerate the ``retry-budget-exhausted`` marker class;
      THIS module DOES NOT EMIT it (Story 5.6 owns emission).

Composition discipline (sensor-not-advisor; ADR-001):
    The orchestrator skill (LLM-runtime; ``skills/bmad-automation/
    steps/run.md``) calls :func:`evaluate_retry_decision` at the
    retry-routing seam (Story 5.2 thickens that seam) AFTER it has
    classified a specialist return as retry-eligible. On
    ``DISPATCH_RETRY`` the orchestrator dispatches a new specialist
    round and on its return appends a :class:`RetryAttempt` to the
    run-state's ``retry_history`` tuple via Story 2.2's
    :func:`loud_fail_harness.run_state.advance_run_state` atomic-
    write helper (the canonical write-path; THIS module does NOT call
    it directly). On ``HALT_BUDGET_EXHAUSTED`` the orchestrator routes
    to Story 5.6's exhaustion handler (which owns marker emission +
    state preservation per FR14).

Derived-counter structural commitment (drift-prevention):
    ``budget_remaining = resolved_budget - len(run_state.retry_history)``
    is DERIVED at decision-time, NOT stored as a separate
    ``run-state.yaml`` field. A stored counter and the
    ``retry_history`` array could disagree (e.g., a future bug appends
    a :class:`RetryAttempt` without decrementing the counter, or vice
    versa); the derived form makes disagreement structurally
    impossible. The choice also avoids a ``schemas/run-state.yaml``
    MINOR version bump (additive optional field) at this story's
    landing time — the existing schema 1.1 shape suffices. Story 5.5
    will externalize ``retry_history`` to a separate file
    (``_bmad/automation/retry-history-{run-id}.yaml`` or similar);
    THIS module's derived posture stays correct because the count is
    re-derived from whichever container holds the history at that
    point.

What this module does NOT own:
    * **Marker emission** — the ``retry-budget-exhausted`` marker class
      is consumed structurally only here; Story 5.6 owns runtime
      emission of the marker + the parallel ``retry-budget-exhausted``
      orchestrator-event class.
    * **Bucket filtering** — :func:`evaluate_retry_decision` is
      invoked AFTER the orchestrator has already classified the
      specialist return as retry-eligible (Story 5.2's
      ``should_retry(envelope)`` returns ``True``). This module is
      bucket-agnostic on purpose; mixing routing + budget concerns
      would conflate two flow-policy responsibilities.
    * **State writes** — read-only on :class:`RunState`. The orchestrator
      is responsible for the write-path through
      :func:`loud_fail_harness.run_state.advance_run_state` per
      Pattern 4 + NFR-R8 ordering.
    * **Wrapper-side retry-mode plumbing** — ``retry_mode: fix-only``
      + ``affected_files`` + ``scope_expanded_to`` is Story 5.3's
      contract pair surface.

Pluggability invariant (FR62):
    This module lives at ``tools/loud-fail-harness/src/loud_fail_harness/
    retry_budget.py`` (the harness substrate). The FR62 pluggability
    gate (:mod:`loud_fail_harness.pluggability_gate`) scans only
    ``agents/*.md`` specialist subagent files; it does NOT scan
    harness substrate. The new module does not affect gate behavior.

Pattern conformance:
    * **Pattern 1 (YAML casing + file naming)** — module file name
      ``retry_budget.py`` is snake_case (file-name boundary per
      architecture.md lines 932-935); function names ``resolve_*`` /
      ``read_*`` / ``evaluate_*`` are snake_case (Python convention);
      :class:`RetryDecision` enum-member values are kebab-case
      identifier strings (precedent: :data:`loud_fail_harness.run_state.
      CurrentState` Literal members like ``"ready-for-dev"``,
      ``"in-progress"``).
    * **Pattern 4 (state-update discipline)** — this module adds NO
      new write-path to ``run-state.yaml``; it only READS the
      :class:`RunState`'s ``retry_history`` tuple at decision-time.
      Story 5.6 owns the next state-write surface (exhaustion-emission
      non-advance state).
    * **Pattern 5 (loud-fail / error-handling doctrine)** —
      :class:`RetryBudgetConfigError` raises loudly on malformed input
      (non-int, negative, ``bool``, string-int, float-int). The only
      silent-default path is "config absent" (legitimate pre-Story-7.5
      state) and "field absent" (config exists but ``retry_budget``
      key omitted). Malformed YAML at the file level raises with the
      parser-error context attached for operator remediation per the
      FR48a / NFR-O5 actionable-pointer posture.
"""

from __future__ import annotations

import enum
import pathlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from loud_fail_harness.run_state import RunState

#: Default retry-budget value per FR8 ("default: 2").
DEFAULT_RETRY_BUDGET: int = 2

#: Canonical config-file field name. Snake_case per Pattern 1's
#: structural-key boundary (architecture.md lines 932-935).
_RETRY_BUDGET_FIELD: str = "retry_budget"


class RetryBudgetConfigError(ValueError):
    """Raised on malformed ``retry_budget`` config input.

    The ``ValueError`` lineage is intentional — the per-input-shape
    contract (AC-1 / AC-2) treats "wrong type" / "negative" / "bool"
    as value-domain violations, not type-system errors. Subclassing
    :class:`ValueError` keeps stdlib introspection (e.g., generic
    ``except ValueError`` in higher-level error handlers) compatible
    while allowing precise ``except RetryBudgetConfigError`` catches
    at the orchestrator boundary.

    Message format (per AC-1's diagnostic-shape contract; FR48a /
    NFR-O5 actionable-pointer posture): include the offending value,
    the field name (``retry_budget``), and a remediation hint so an
    operator pasting the error into a chat can identify what to change
    in their ``_bmad/automation/config.yaml`` without reading source.
    """


class RetryDecision(enum.Enum):
    """Orchestrator-side routing decision returned by
    :func:`evaluate_retry_decision`.

    Two members:

    * :attr:`DISPATCH_RETRY` — the budget has remaining capacity
      (``len(retry_history) < resolved_budget``); the orchestrator
      MAY dispatch another specialist round.
    * :attr:`HALT_BUDGET_EXHAUSTED` — the budget is exhausted
      (``len(retry_history) >= resolved_budget``); the next non-pass
      return must route to Story 5.6's exhaustion handler instead of
      another retry dispatch.

    Member values are kebab-case identifier strings per Pattern 1
    (precedent: :data:`loud_fail_harness.run_state.CurrentState`
    Literal members). They appear in orchestrator-event log entries
    Story 5.6 will emit; the ``"halt-budget-exhausted"`` value is
    structurally adjacent to the ``retry-budget-exhausted`` marker
    class registered at ``schemas/marker-taxonomy.yaml`` lines
    247-252 (Story 1.4 lander) but is NOT the marker class itself —
    this module does not emit markers.
    """

    DISPATCH_RETRY = "dispatch-retry"
    HALT_BUDGET_EXHAUSTED = "halt-budget-exhausted"


def resolve_retry_budget(
    config: Mapping[str, Any] | None = None,
    *,
    default: int = DEFAULT_RETRY_BUDGET,
) -> int:
    """Resolve the integer retry-budget from a config mapping.

    Pure function (no I/O). Used at the orchestrator-skill boundary
    after the caller has already loaded the YAML mapping (or knows
    no config exists). The thin file-reader helper
    :func:`read_retry_budget_from_config_file` is the I/O-side
    composition target for the canonical
    ``_bmad/automation/config.yaml`` path.

    Per-input contract (AC-2):

    * ``config is None`` → return ``default`` (covers the
      pre-Story-7.5 "config.yaml not yet scaffolded" case).
    * ``config={}`` → return ``default`` (config exists but the
      ``retry_budget`` key is omitted).
    * ``config={"retry_budget": <int N>}`` where ``N >= 0`` AND
      ``type(N) is int`` (not :class:`bool`) → return ``N``.
    * ``config={"retry_budget": None}`` → return ``default`` (the
      YAML loader parses ``retry_budget:`` with no value as
      :data:`None`; treat as field-absent).
    * Any other value (string-int, float-int, negative int, ``bool``,
      arbitrary type) → raise :exc:`RetryBudgetConfigError`.

    The ``default`` keyword permits test-side override. Production
    callers always pass the FR8-specified default of ``2``.
    """
    if config is None:
        return default

    if _RETRY_BUDGET_FIELD not in config:
        return default

    value = config[_RETRY_BUDGET_FIELD]

    if value is None:
        return default

    # bool is a subclass of int in Python; explicit reject before the
    # int-type check so True/False don't slip through as 1/0. Loud-fail
    # posture per Pattern 5: an operator typo (`retry_budget: yes`
    # parses to True) must surface, not silently coerce.
    if isinstance(value, bool):
        raise RetryBudgetConfigError(
            f"{_RETRY_BUDGET_FIELD} must be a non-negative integer; "
            f"got {value!r} ({type(value).__name__}) — booleans are "
            f"rejected to avoid YAML truthy-coercion ambiguity — "
            f"write the value as an unquoted integer in config.yaml "
            f"(e.g., 'retry_budget: 2')"
        )

    # Reject everything that is not strictly an int. Strings (`"2"`),
    # floats (`2.0`), and arbitrary types are config-shape violations
    # per the YAML int-form contract.
    if type(value) is not int:
        raise RetryBudgetConfigError(
            f"{_RETRY_BUDGET_FIELD} must be a YAML int; "
            f"got {value!r} ({type(value).__name__}) — write the value "
            f"as an unquoted integer in config.yaml (e.g., "
            f"'retry_budget: 2', not 'retry_budget: \"2\"' or "
            f"'retry_budget: 2.0')"
        )

    if value < 0:
        raise RetryBudgetConfigError(
            f"{_RETRY_BUDGET_FIELD} must be a non-negative integer; "
            f"got {value!r} (int) — set retry_budget to 0 (no retries) "
            f"or a positive integer"
        )

    return value


def read_retry_budget_from_config_file(
    config_path: pathlib.Path,
    *,
    default: int = DEFAULT_RETRY_BUDGET,
) -> int:
    """Read the ``retry_budget`` value from a YAML config file.

    Thin file-reader helper that delegates value-shape validation to
    :func:`resolve_retry_budget`. Uses :func:`yaml.safe_load` (NOT
    :func:`yaml.load`) per the loud-fail security doctrine — arbitrary
    Python object construction via the unsafe loader is a known
    vulnerability and never appropriate for operator-facing config.

    Per-input contract (AC-4):

    * ``config_path`` does NOT exist → return ``default`` (do NOT
      raise). Covers the "user has not scaffolded
      ``_bmad/automation/config.yaml`` yet" case (Story 7.5 owns
      scaffold generation; pre-7.5 silent-defaulting is the
      contract).
    * ``config_path`` exists but the file is empty → return
      ``default``.
    * ``config_path`` exists and parses to a YAML mapping → delegate
      to :func:`resolve_retry_budget` (which handles field-absent /
      field-present / value-shape).
    * ``config_path`` exists but is malformed YAML → raise
      :exc:`RetryBudgetConfigError` with the parse-error context
      chained via ``__cause__``. Loud-fail per Pattern 5: corrupt
      config is NOT silently fallback-able.
    * ``config_path`` exists and parses to a non-mapping (list,
      scalar) → raise :exc:`RetryBudgetConfigError` (the contract is
      "config.yaml is a YAML mapping at top level").
    """
    if not config_path.exists():
        return default

    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RetryBudgetConfigError(
            f"failed to read {config_path}: {exc}"
        ) from exc

    if not raw_text.strip():
        return default

    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise RetryBudgetConfigError(
            f"{config_path} is not valid YAML; "
            f"parser error: {exc} — fix the YAML syntax in "
            f"{config_path} and re-run"
        ) from exc

    if parsed is None:
        # Whitespace-only or comment-only YAML parses to None even
        # after the strip() check above (e.g., a file containing only
        # `# comment\n` strips to `# comment` which is non-empty but
        # parses to None).
        return default

    if not isinstance(parsed, Mapping):
        raise RetryBudgetConfigError(
            f"{config_path} top-level must be a YAML mapping; "
            f"got {type(parsed).__name__}: {parsed!r} — write the file as "
            f"'retry_budget: 2' (key/value pairs at the top level), "
            f"not as a list or scalar"
        )

    return resolve_retry_budget(parsed, default=default)


def evaluate_retry_decision(
    run_state: RunState,
    resolved_budget: int,
) -> RetryDecision:
    """Decide whether to dispatch another retry round or halt.

    Pure function (no I/O; no global-state mutation; idempotent on
    repeated calls with the same inputs). The
    :class:`loud_fail_harness.run_state.RunState` parameter is
    Pydantic-v2-frozen; this function does not (and structurally
    cannot) mutate it.

    Decision rule (AC-3):

    * ``len(run_state.retry_history) < resolved_budget`` →
      :attr:`RetryDecision.DISPATCH_RETRY` (budget remaining is
      ``resolved_budget - len(retry_history)``).
    * ``len(run_state.retry_history) >= resolved_budget`` →
      :attr:`RetryDecision.HALT_BUDGET_EXHAUSTED` (the next non-pass
      return triggers Story 5.6's exhaustion handler).

    The function is BUCKET-AGNOSTIC by design — it does NOT inspect
    ``run_state.last_envelope``. Bucket-driven action-item filtering
    (e.g., excluding ``bucket: passthrough`` from retry-eligibility)
    is Story 5.2's surface. By contract, the orchestrator skill calls
    :func:`evaluate_retry_decision` ONLY when its retry-routing seam
    has already classified the return as retry-eligible.

    The ``resolved_budget == 0`` case is correctly handled by the
    same rule: ``len(retry_history) >= 0`` is always true, so a zero-
    budget config halts on the first retry-eligible return (legitimate
    operator choice = "no retries permitted"; downstream is Story 5.6's
    exhaustion handler).

    The function is also defensive against ``len(retry_history) >
    resolved_budget`` (over-reach) — should not occur if the function
    is consulted before each dispatch, but if it does, the same halt
    decision is returned. Idempotent on already-exhausted state.

    Raises:
        ValueError: if ``resolved_budget`` is negative. Pass the output
            of :func:`resolve_retry_budget` (which validates the value)
            or a guaranteed non-negative budget.
    """
    if resolved_budget < 0:
        raise ValueError(
            f"resolved_budget must be a non-negative integer; "
            f"got {resolved_budget!r} — pass the output of "
            f"resolve_retry_budget() or a validated non-negative budget"
        )
    if len(run_state.retry_history) < resolved_budget:
        return RetryDecision.DISPATCH_RETRY
    return RetryDecision.HALT_BUDGET_EXHAUSTED


__all__ = [
    "DEFAULT_RETRY_BUDGET",
    "RetryBudgetConfigError",
    "RetryDecision",
    "evaluate_retry_decision",
    "read_retry_budget_from_config_file",
    "resolve_retry_budget",
]
