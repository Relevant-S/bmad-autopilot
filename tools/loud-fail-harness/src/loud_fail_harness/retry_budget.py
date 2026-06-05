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

#: Default per-epic retry-budget multiplier (Story 15.2 / FR-P2-1). The
#: effective per-epic budget is ``multiplier × story_count``. Canonical home is
#: here (alongside :data:`DEFAULT_RETRY_BUDGET`, the per-story sibling);
#: :mod:`loud_fail_harness.epic_lifecycle` re-exports it. Single-sourced (the
#: literal ``2`` lives only here) so the resolver default and the epic-init
#: default can never drift.
DEFAULT_PER_EPIC_RETRY_MULTIPLIER: int = 2

#: Canonical config-file field name. Snake_case per Pattern 1's
#: structural-key boundary (architecture.md lines 932-935).
_RETRY_BUDGET_FIELD: str = "retry_budget"

#: Canonical per-epic-multiplier config-file field name (Story 15.2). Snake_case
#: per Pattern 1's structural-key boundary.
_PER_EPIC_RETRY_BUDGET_MULTIPLIER_FIELD: str = "per_epic_retry_budget_multiplier"

#: Default per-sprint retry-budget multiplier (Story 16.1 / 16.2 / FR-P2-2). The
#: leading term of the per-sprint effective-budget formula
#: ``multiplier × epic_count + per_story_budget × unassigned_story_count``.
#: Canonical home is here (alongside :data:`DEFAULT_RETRY_BUDGET` and
#: :data:`DEFAULT_PER_EPIC_RETRY_MULTIPLIER`); :mod:`loud_fail_harness.
#: sprint_lifecycle` re-exports it. Equals the per-epic default of 2 by design
#: (the same "2×" cost-bounding philosophy carried one scope up).
DEFAULT_PER_SPRINT_RETRY_MULTIPLIER: int = 2

#: Default sprint escalation-rate threshold (Story 16.2 / FR-P2-2). When the
#: cumulative ``escalated_stories / stories_completed`` exceeds this fraction the
#: orchestrator emits the informational ``sprint-escalation-rate-exceeded``
#: marker (it does NOT pause — sensor-not-advisor). Calibrated from the PRD's
#: 15–25% retry-budget-exhaustion target band (Technical Success criteria).
DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD: float = 0.25

#: Canonical per-sprint-budget-override config-file field name (Story 16.2). An
#: ABSOLUTE override of the computed effective budget (NOT a multiplier — contrast
#: ``per_epic_retry_budget_multiplier``). Snake_case per Pattern 1.
_PER_SPRINT_RETRY_BUDGET_FIELD: str = "per_sprint_retry_budget"

#: Canonical sprint-escalation-rate-threshold config-file field name (Story
#: 16.2). Snake_case per Pattern 1's structural-key boundary.
_SPRINT_ESCALATION_RATE_THRESHOLD_FIELD: str = "sprint_escalation_rate_threshold"

#: Default parallel-story concurrency ceiling (Story 18.1 / FR-P2-4). When
#: ``parallel_stories`` is enabled, the epic loop fans out at most this many
#: per-story loops concurrently. Single-sourced here so the resolver default and
#: the dispatcher default can never drift; ``epic_lifecycle`` re-exports it.
DEFAULT_MAX_PARALLEL_STORIES: int = 2

#: Canonical ``parallel_stories`` config-file field name (Story 18.1). The opt-in
#: gate for concurrent per-story dispatch. Snake_case per Pattern 1.
_PARALLEL_STORIES_FIELD: str = "parallel_stories"

#: Canonical ``max_parallel_stories`` config-file field name (Story 18.1). The
#: concurrency ceiling honored when ``parallel_stories`` is true. Snake_case.
_MAX_PARALLEL_STORIES_FIELD: str = "max_parallel_stories"


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


def resolve_per_epic_retry_budget_multiplier(
    config: Mapping[str, Any] | None = None,
    *,
    default: int = DEFAULT_PER_EPIC_RETRY_MULTIPLIER,
) -> int:
    """Resolve the integer per-epic retry-budget multiplier from a config
    mapping (Story 15.2 / FR-P2-1).

    The per-epic sibling of :func:`resolve_retry_budget`. The effective per-epic
    budget the epic loop enforces is ``multiplier × story_count`` (separate from
    — and additive on top of — the per-story budgets). The ONLY semantic
    differences from :func:`resolve_retry_budget` are the field name
    (``per_epic_retry_budget_multiplier``) and the floor of **1** rather than 0:
    a multiplier of 0 would make every non-empty epic instantly exhausted,
    which is never a meaningful operator choice (set the per-story
    ``retry_budget`` to 0 to forbid retries).

    Per-input contract (mirrors :func:`resolve_retry_budget` verbatim except the
    floor):

    * ``config is None`` → ``default``.
    * field absent / value ``None`` → ``default``.
    * ``type(value) is int`` (not :class:`bool`) AND ``value >= 1`` → ``value``.
    * any other value (string-int, float, ``bool``, ``< 1``) →
      :exc:`RetryBudgetConfigError`.
    """
    if config is None:
        return default

    if _PER_EPIC_RETRY_BUDGET_MULTIPLIER_FIELD not in config:
        return default

    value = config[_PER_EPIC_RETRY_BUDGET_MULTIPLIER_FIELD]

    if value is None:
        return default

    if isinstance(value, bool):
        raise RetryBudgetConfigError(
            f"{_PER_EPIC_RETRY_BUDGET_MULTIPLIER_FIELD} must be an integer "
            f">= 1; got {value!r} ({type(value).__name__}) — booleans are "
            f"rejected to avoid YAML truthy-coercion ambiguity — write the "
            f"value as an unquoted integer in config.yaml (e.g., "
            f"'per_epic_retry_budget_multiplier: 2')"
        )

    if type(value) is not int:
        raise RetryBudgetConfigError(
            f"{_PER_EPIC_RETRY_BUDGET_MULTIPLIER_FIELD} must be a YAML int; "
            f"got {value!r} ({type(value).__name__}) — write the value as an "
            f"unquoted integer in config.yaml (e.g., "
            f"'per_epic_retry_budget_multiplier: 2', not "
            f"'per_epic_retry_budget_multiplier: \"2\"' or "
            f"'per_epic_retry_budget_multiplier: 2.0')"
        )

    if value < 1:
        raise RetryBudgetConfigError(
            f"{_PER_EPIC_RETRY_BUDGET_MULTIPLIER_FIELD} must be an integer "
            f">= 1; got {value!r} (int) — the per-epic budget is "
            f"multiplier × story_count, so a multiplier below 1 would exhaust "
            f"every epic immediately; set it to 1 or a larger integer"
        )

    return value


def read_per_epic_retry_budget_multiplier_from_config_file(
    config_path: pathlib.Path,
    *,
    default: int = DEFAULT_PER_EPIC_RETRY_MULTIPLIER,
) -> int:
    """Read ``per_epic_retry_budget_multiplier`` from a YAML config file
    (Story 15.2).

    The per-epic sibling of :func:`read_retry_budget_from_config_file`; the
    missing-file / empty-file / malformed-YAML / non-mapping contract is
    identical (delegates value-shape validation to
    :func:`resolve_per_epic_retry_budget_multiplier`). Uses
    :func:`yaml.safe_load` per the loud-fail security doctrine.
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
        return default

    if not isinstance(parsed, Mapping):
        raise RetryBudgetConfigError(
            f"{config_path} top-level must be a YAML mapping; "
            f"got {type(parsed).__name__}: {parsed!r} — write the file as "
            f"'per_epic_retry_budget_multiplier: 2' (key/value pairs at the "
            f"top level), not as a list or scalar"
        )

    return resolve_per_epic_retry_budget_multiplier(parsed, default=default)


def resolve_per_sprint_retry_budget_override(
    config: Mapping[str, Any] | None = None,
    *,
    default: int | None = None,
) -> int | None:
    """Resolve the optional per-sprint retry-budget ABSOLUTE override from a
    config mapping (Story 16.2 / FR-P2-2).

    Unlike :func:`resolve_per_epic_retry_budget_multiplier` (a multiplier), the
    ``per_sprint_retry_budget`` field is an ABSOLUTE override of the auto-computed
    effective budget. A return of ``None`` means "no override present — the caller
    auto-computes from the formula ``multiplier × epic_count + per_story_budget ×
    unassigned_story_count``";     a return of ``0`` is the degenerate unlimited case —
    :func:`apply_sprint_budget`'s ``effective_budget > 0`` guard treats
    ``effective_budget=0`` as no ceiling (never exhausted). The minimum effective
    enforcement value is ``1`` (the sprint pauses once cumulative consumed ≥ 1
    retry). The floor is therefore **0** (the same non-negative contract as
    :func:`resolve_retry_budget`), and the absent-``None`` vs. explicit-``0``
    distinction is load-bearing.

    Per-input contract (mirrors :func:`resolve_retry_budget` except the absent
    sentinel is ``None``, not a numeric default):

    * ``config is None`` → ``default`` (``None``).
    * field absent / value ``None`` → ``default`` (``None``).
    * ``type(value) is int`` (not :class:`bool`) AND ``value >= 0`` → ``value``.
    * any other value (string-int, float, ``bool``, negative) →
      :exc:`RetryBudgetConfigError`.
    """
    if config is None:
        return default

    if _PER_SPRINT_RETRY_BUDGET_FIELD not in config:
        return default

    value = config[_PER_SPRINT_RETRY_BUDGET_FIELD]

    if value is None:
        return default

    if isinstance(value, bool):
        raise RetryBudgetConfigError(
            f"{_PER_SPRINT_RETRY_BUDGET_FIELD} must be a non-negative integer; "
            f"got {value!r} ({type(value).__name__}) — booleans are rejected to "
            f"avoid YAML truthy-coercion ambiguity — write the value as an "
            f"unquoted integer in config.yaml (e.g., 'per_sprint_retry_budget: "
            f"12'), or omit the field to auto-compute the budget"
        )

    if type(value) is not int:
        raise RetryBudgetConfigError(
            f"{_PER_SPRINT_RETRY_BUDGET_FIELD} must be a YAML int; "
            f"got {value!r} ({type(value).__name__}) — write the value as an "
            f"unquoted integer in config.yaml (e.g., 'per_sprint_retry_budget: "
            f"12', not '\"12\"' or '12.0'), or omit the field to auto-compute"
        )

    if value < 0:
        raise RetryBudgetConfigError(
            f"{_PER_SPRINT_RETRY_BUDGET_FIELD} must be a non-negative integer; "
            f"got {value!r} (int) — set it to a positive integer (minimum "
            f"useful value: 1) or omit the field to auto-compute the budget"
        )

    return value


def read_per_sprint_retry_budget_from_config_file(
    config_path: pathlib.Path,
    *,
    default: int | None = None,
) -> int | None:
    """Read the optional ``per_sprint_retry_budget`` override from a YAML config
    file (Story 16.2).

    The per-sprint sibling of
    :func:`read_per_epic_retry_budget_multiplier_from_config_file`; the
    missing-file / empty-file / malformed-YAML / non-mapping contract is identical
    (delegates value-shape validation to
    :func:`resolve_per_sprint_retry_budget_override`). Returns ``None`` (the
    ``default``) when no override is configured. Uses :func:`yaml.safe_load` per
    the loud-fail security doctrine.
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
        return default

    if not isinstance(parsed, Mapping):
        raise RetryBudgetConfigError(
            f"{config_path} top-level must be a YAML mapping; "
            f"got {type(parsed).__name__}: {parsed!r} — write the file as "
            f"'per_sprint_retry_budget: 12' (key/value pairs at the top level), "
            f"not as a list or scalar"
        )

    return resolve_per_sprint_retry_budget_override(parsed, default=default)


def resolve_sprint_escalation_rate_threshold(
    config: Mapping[str, Any] | None = None,
    *,
    default: float = DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD,
) -> float:
    """Resolve the sprint escalation-rate threshold from a config mapping
    (Story 16.2 / FR-P2-2).

    The threshold is a fraction in the half-open range ``(0.0, 1.0]``: when the
    cumulative ``escalated_stories / stories_completed`` exceeds it, the sprint
    loop emits the informational ``sprint-escalation-rate-exceeded`` marker. A
    YAML int (e.g. ``1``) is accepted and coerced to ``float`` (``1.0``); a
    ``bool`` is rejected (``int`` subclass). Zero / negative / ``> 1.0`` are
    rejected: a threshold of 0 would fire on the first escalation (use a small
    positive fraction instead) and a threshold above 1 can never be exceeded.

    Per-input contract (mirrors :func:`resolve_retry_budget`'s shape):

    * ``config is None`` → ``default``.
    * field absent / value ``None`` → ``default``.
    * ``int`` or ``float`` (not :class:`bool`) in ``(0.0, 1.0]`` → ``float(value)``.
    * any other value (``bool``, string, ``<= 0.0``, ``> 1.0``) →
      :exc:`RetryBudgetConfigError`.
    """
    if config is None:
        return default

    if _SPRINT_ESCALATION_RATE_THRESHOLD_FIELD not in config:
        return default

    value = config[_SPRINT_ESCALATION_RATE_THRESHOLD_FIELD]

    if value is None:
        return default

    if isinstance(value, bool):
        raise RetryBudgetConfigError(
            f"{_SPRINT_ESCALATION_RATE_THRESHOLD_FIELD} must be a number in "
            f"(0.0, 1.0]; got {value!r} ({type(value).__name__}) — booleans are "
            f"rejected to avoid YAML truthy-coercion ambiguity — write the value "
            f"as an unquoted fraction in config.yaml (e.g., "
            f"'sprint_escalation_rate_threshold: 0.25')"
        )

    if type(value) not in (int, float):
        raise RetryBudgetConfigError(
            f"{_SPRINT_ESCALATION_RATE_THRESHOLD_FIELD} must be a YAML number; "
            f"got {value!r} ({type(value).__name__}) — write the value as an "
            f"unquoted fraction in config.yaml (e.g., "
            f"'sprint_escalation_rate_threshold: 0.25', not '\"0.25\"')"
        )

    coerced = float(value)
    if not (0.0 < coerced <= 1.0):
        raise RetryBudgetConfigError(
            f"{_SPRINT_ESCALATION_RATE_THRESHOLD_FIELD} must be in the range "
            f"(0.0, 1.0]; got {value!r} — a threshold of 0 would fire on the "
            f"first escalation (use a small positive fraction) and a threshold "
            f"above 1 can never be exceeded; set it to e.g. 0.25"
        )

    return coerced


def read_sprint_escalation_rate_threshold_from_config_file(
    config_path: pathlib.Path,
    *,
    default: float = DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD,
) -> float:
    """Read ``sprint_escalation_rate_threshold`` from a YAML config file
    (Story 16.2).

    The sibling of :func:`read_retry_budget_from_config_file`; the missing-file /
    empty-file / malformed-YAML / non-mapping contract is identical (delegates
    value-shape validation to :func:`resolve_sprint_escalation_rate_threshold`).
    Uses :func:`yaml.safe_load` per the loud-fail security doctrine.
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
        return default

    if not isinstance(parsed, Mapping):
        raise RetryBudgetConfigError(
            f"{config_path} top-level must be a YAML mapping; "
            f"got {type(parsed).__name__}: {parsed!r} — write the file as "
            f"'sprint_escalation_rate_threshold: 0.25' (key/value pairs at the "
            f"top level), not as a list or scalar"
        )

    return resolve_sprint_escalation_rate_threshold(parsed, default=default)


def resolve_parallel_stories(
    config: Mapping[str, Any] | None = None,
    *,
    default: bool = False,
) -> bool:
    """Resolve the ``parallel_stories`` opt-in flag from a config mapping
    (Story 18.1 / FR-P2-4).

    The structural INVERSE of the integer resolvers in this module. Those reject
    :class:`bool` (``isinstance(value, bool)`` → error) to avoid YAML
    truthy-coercion ambiguity for integer fields; ``parallel_stories`` is a
    genuine boolean, so this resolver does the opposite — it REQUIRES
    ``type(value) is bool`` and rejects everything else (``int`` including
    ``0``/``1``, ``str`` including ``"true"``/``"false"``, ``float``, and
    containers). A non-bool here is the same class of operator typo
    (``parallel_stories: 1`` / ``parallel_stories: "true"``) the int resolvers
    guard against from the other direction.

    Per-input contract:

    * ``config is None`` → ``default`` (pre-Story-7.5 "config.yaml not yet
      scaffolded" case).
    * field absent / value ``None`` → ``default`` (the YAML loader parses
      ``parallel_stories:`` with no value as :data:`None`).
    * ``type(value) is bool`` → the value.
    * any other value → :exc:`RetryBudgetConfigError` naming the field + the
      YAML-bool remediation.
    """
    if config is None:
        return default

    if _PARALLEL_STORIES_FIELD not in config:
        return default

    value = config[_PARALLEL_STORIES_FIELD]

    if value is None:
        return default

    if type(value) is not bool:
        raise RetryBudgetConfigError(
            f"{_PARALLEL_STORIES_FIELD} must be a YAML boolean; "
            f"got {value!r} ({type(value).__name__}) — write the value as an "
            f"unquoted YAML bool in config.yaml (e.g., "
            f"'parallel_stories: true' or 'parallel_stories: false'), not as an "
            f"integer, quoted string, or other type"
        )

    return value


def read_parallel_stories_from_config_file(
    config_path: pathlib.Path,
    *,
    default: bool = False,
) -> bool:
    """Read ``parallel_stories`` from a YAML config file (Story 18.1).

    The boolean sibling of :func:`read_retry_budget_from_config_file`; the
    missing-file / empty-file / malformed-YAML / non-mapping contract is
    identical (delegates value-shape validation to
    :func:`resolve_parallel_stories`). Uses :func:`yaml.safe_load` per the
    loud-fail security doctrine.
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
        return default

    if not isinstance(parsed, Mapping):
        raise RetryBudgetConfigError(
            f"{config_path} top-level must be a YAML mapping; "
            f"got {type(parsed).__name__}: {parsed!r} — write the file as "
            f"'parallel_stories: false' (key/value pairs at the top level), "
            f"not as a list or scalar"
        )

    return resolve_parallel_stories(parsed, default=default)


def resolve_max_parallel_stories(
    config: Mapping[str, Any] | None = None,
    *,
    default: int = DEFAULT_MAX_PARALLEL_STORIES,
) -> int:
    """Resolve the ``max_parallel_stories`` concurrency ceiling from a config
    mapping (Story 18.1 / FR-P2-4).

    An integer resolver with a floor of **1** and default **2**, mirroring
    :func:`resolve_per_epic_retry_budget_multiplier` verbatim except the field
    name. A ``max_parallel_stories`` below 1 is never a meaningful operator
    choice — set ``parallel_stories: false`` to disable concurrency rather than
    asking for "at most zero" in-flight stories.

    Per-input contract:

    * ``config is None`` → ``default``.
    * field absent / value ``None`` → ``default``.
    * ``type(value) is int`` (not :class:`bool`) AND ``value >= 1`` → ``value``.
    * any other value (``bool``, string-int, ``float``, ``< 1``) →
      :exc:`RetryBudgetConfigError`.
    """
    if config is None:
        return default

    if _MAX_PARALLEL_STORIES_FIELD not in config:
        return default

    value = config[_MAX_PARALLEL_STORIES_FIELD]

    if value is None:
        return default

    if isinstance(value, bool):
        raise RetryBudgetConfigError(
            f"{_MAX_PARALLEL_STORIES_FIELD} must be an integer >= 1; "
            f"got {value!r} ({type(value).__name__}) — booleans are rejected "
            f"to avoid YAML truthy-coercion ambiguity — write the value as an "
            f"unquoted integer in config.yaml (e.g., 'max_parallel_stories: 2')"
        )

    if type(value) is not int:
        raise RetryBudgetConfigError(
            f"{_MAX_PARALLEL_STORIES_FIELD} must be a YAML int; "
            f"got {value!r} ({type(value).__name__}) — write the value as an "
            f"unquoted integer in config.yaml (e.g., 'max_parallel_stories: 2', "
            f"not 'max_parallel_stories: \"2\"' or "
            f"'max_parallel_stories: 2.0')"
        )

    if value < 1:
        raise RetryBudgetConfigError(
            f"{_MAX_PARALLEL_STORIES_FIELD} must be an integer >= 1; "
            f"got {value!r} (int) — a concurrency ceiling below 1 would admit "
            f"no in-flight stories; set it to 1 or a larger integer, or set "
            f"'parallel_stories: false' to disable concurrent dispatch"
        )

    return value


def read_max_parallel_stories_from_config_file(
    config_path: pathlib.Path,
    *,
    default: int = DEFAULT_MAX_PARALLEL_STORIES,
) -> int:
    """Read ``max_parallel_stories`` from a YAML config file (Story 18.1).

    The sibling of :func:`read_retry_budget_from_config_file`; the missing-file
    / empty-file / malformed-YAML / non-mapping contract is identical (delegates
    value-shape validation to :func:`resolve_max_parallel_stories`). Uses
    :func:`yaml.safe_load` per the loud-fail security doctrine.
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
        return default

    if not isinstance(parsed, Mapping):
        raise RetryBudgetConfigError(
            f"{config_path} top-level must be a YAML mapping; "
            f"got {type(parsed).__name__}: {parsed!r} — write the file as "
            f"'max_parallel_stories: 2' (key/value pairs at the top level), "
            f"not as a list or scalar"
        )

    return resolve_max_parallel_stories(parsed, default=default)


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
    "DEFAULT_MAX_PARALLEL_STORIES",
    "DEFAULT_PER_EPIC_RETRY_MULTIPLIER",
    "DEFAULT_PER_SPRINT_RETRY_MULTIPLIER",
    "DEFAULT_RETRY_BUDGET",
    "DEFAULT_SPRINT_ESCALATION_RATE_THRESHOLD",
    "RetryBudgetConfigError",
    "RetryDecision",
    "evaluate_retry_decision",
    "read_max_parallel_stories_from_config_file",
    "read_parallel_stories_from_config_file",
    "read_per_epic_retry_budget_multiplier_from_config_file",
    "read_per_sprint_retry_budget_from_config_file",
    "read_retry_budget_from_config_file",
    "read_sprint_escalation_rate_threshold_from_config_file",
    "resolve_max_parallel_stories",
    "resolve_parallel_stories",
    "resolve_per_epic_retry_budget_multiplier",
    "resolve_per_sprint_retry_budget_override",
    "resolve_retry_budget",
    "resolve_sprint_escalation_rate_threshold",
]
