"""Story 5.4 — Scope-assertion verification + violation loud-fail.

Pure-library substrate component owning the orchestrator-side post-Dev-
return scope-assertion verification surface for FR12 + FR58: compares
Dev's actual git diff against the union of the orchestrator's declared
``affected_files`` (Story 5.3's :class:`RetryDispatchDirective`) and
Dev's reported ``scope_expanded_to`` (Story 5.3's
:func:`extract_scope_expanded_to`); on mismatch, emits a
``scope-assertion-violation`` marker via the SubagentStop hook's exit-
code path. THIS module owns the comparison + diagnostic-construction +
default git-diff probe + CLI entry-point surface; the runtime emission
boundary is the SubagentStop hook (``hooks/subagent-stop.sh``).

This module is the FOURTH Epic-5 substrate landing per ``epics.md``
lines 2218-2233 — sibling of Story 5.1's :mod:`retry_budget`,
Story 5.2's :mod:`retry_router`, and Story 5.3's :mod:`retry_dispatch`.
It is the FR12 + FR58 substrate-level claim CLOSER paired with
Story 5.3's FR10 + FR11 contract-pair opener — Story 5.3 established
the orchestrator-side declaration + Dev-side reporting; THIS module
closes the verification chain by computing the actual-vs-declared
mismatch.

Sources:
    * **PRD FR12** (``_bmad-output/planning-artifacts/prd.md`` line 823,
      verbatim): "Orchestrator verifies Dev's actual diff matches the
      ``scope_expanded_to`` declaration; mismatch fails loudly as a
      scope-assertion violation."
    * **PRD FR58** (``prd.md`` line 893, verbatim): "``SubagentStop``
      hook (Dev) creates a git commit using ``proposed_commit_message``
      from Dev's return envelope; non-zero exit on scope-assertion
      violation."
    * **PRD NFR-O5** (``prd.md`` line 984) — named diagnostic per
      failure class with actionable remediation pointer.
    * **Story 5.4 verbatim epic AC** at ``epics.md`` lines 2327-2360.
    * **epics.md line 2343** (verbatim, the architectural commitment
      for two-surface closure): "the SubagentStop hook (Story 2.7)
      exits non-zero on this violation per FR58 — the exit-code path
      lit up in Epic 2 is fully exercised here in Epic 5".
    * **epics.md line 2349** (verbatim, the budget-non-decrement
      invariant): "the violation does NOT consume a retry round (it's
      a contract violation, not a normal failure)".

Marker class:
    The ``scope-assertion-violation`` marker class is enumerated in
    ``schemas/marker-taxonomy.yaml`` lines 237-245 (the v1 closed
    taxonomy adds it proactively per Story 1.4's epic-close marker
    sweep). The taxonomy entry's ``diagnostic_pointer`` (verbatim):
    "FR10 (fix-only constraint) + FR12 (verification logic) + FR58
    (SubagentStop hook non-zero exit path). Domain-specific contract
    violation distinct from ``hook-failed`` because remediation
    differs (review Dev's diff vs. declared scope; possibly tighten
    retry's ``affected_files``); markers are remediation-shaped, not
    emission-point-shaped." THIS module's
    :class:`ScopeAssertionViolation` exception + diagnostic prose
    surface the remediation hint VERBATIM so an operator pasting the
    error into chat can identify what to change without reading
    source.

Composition with Story 5.1 / 5.2 / 5.3 / 5.6 / 5.8:

    The orchestrator-skill's run-loop composition path post-5.4 (see
    ``skills/bmad-automation/steps/run.md`` for the LLM-runtime
    prose):

        # Story 5.3 produces the directive at retry-dispatch time.
        directive = retry_dispatch.RetryDispatchDirective(
            retry_mode="fix-only",
            affected_files=affected_files,
        )
        # ... persist `last_retry_directive` on run-state (Story 5.4 schema bump).
        # ... dispatch via Task tool ... await Dev return ...
        scope_expanded_to = retry_dispatch.extract_scope_expanded_to(
            dev_envelope
        )
        # SubagentStop hook fires here (Story 2.7's exit-code path);
        # the hook invokes Story 5.4's `scope-assertion-verify` CLI,
        # which calls `verify_scope_assertion` against the declared
        # scope and Dev's actual git diff. On violation:
        # * the hook exits 1 (the runtime-emission boundary);
        # * the orchestrator-skill detects the violation marker on
        #   stderr;
        # * routes to Story 5.6's exhaustion handler (the `escalated`
        #   lifecycle state);
        # * the budget counter is NOT decremented (epics.md line 2349);
        # * Story 5.8 renders the violation diagnostic in the
        #   escalation bundle.

What this module does NOT own:

    * **Whole-story retry budget mechanics** — Story 5.1's
      :mod:`retry_budget`; consumed AS-IS at the orchestrator-skill
      layer. The budget counter is NOT decremented on
      scope-assertion-violation per AC-3 (epics.md line 2349 verbatim).
    * **Bucket-driven routing + action-item derivation** — Story 5.2's
      :mod:`retry_router`; consumed AS-IS via Story 5.3's
      :func:`derive_affected_files` upstream.
    * **Contract-pair dispatch surface** — Story 5.3's
      :mod:`retry_dispatch`; consumed AS-IS via
      :func:`extract_scope_expanded_to` at the orchestrator-skill
      layer. THIS module does NOT directly import
      :mod:`retry_dispatch` — the verifier accepts already-extracted
      tuples per the sensor-not-advisor + flow-policy-territory
      boundary.
    * **Externalized retry history** — Story 5.5; orthogonal to THIS
      story's ``last_retry_directive`` field (a single-most-recent-
      directive snapshot, NOT a full history).
    * **Retry-budget-exhausted runtime emission** — Story 5.6 owns
      the marker-emission handler. THIS story routes
      scope-assertion-violations to that handler but does not own it.
    * **Escalation-bundle assembly** — Story 5.8 consumes THIS
      module's :class:`ScopeAssertionDiagnostic` (alongside Story
      5.6's exhaustion artifacts).
    * **``is_retry_present()`` flag flip** — Story 5.9 epic-close
      in-place flip.

Pluggability invariant (FR62):
    This module lives at ``tools/loud-fail-harness/src/loud_fail_harness/
    scope_assertion.py`` (the harness substrate). The FR62 pluggability
    gate (:mod:`pluggability_gate`) scans only ``agents/*.md`` specialist
    subagent files; it does NOT scan harness substrate. The SubagentStop
    hook composes against this module AS DATA (via the
    ``scope-assertion-verify`` CLI entry-point) per ADR-001's portable-
    surface boundary. The Dev wrapper does NOT import or reference this
    module — Dev is REPORTED-ON by it, not a caller.

Sensor-not-advisor invariant (FR52 / ADR-002 invariant 1):
    THIS module is FLOW-POLICY territory (the orchestrator's job per
    ADR-001); Dev does NOT call it. The mechanism is mechanical
    enforcement per FR12 verbatim — it is policed by the substrate, NOT
    by Dev's discipline OR by review prose.

Pattern conformance:
    * **Pattern 1** — module file name ``scope_assertion.py`` is
      snake_case; function names are snake_case; class names are
      PascalCase; the marker-class identifier value
      ``"scope-assertion-violation"`` is kebab-case sourced VERBATIM
      from the marker-taxonomy.
    * **Pattern 4** — this module READS run-state (via the CLI's YAML
      load); it adds NO new write-path to ``run-state.yaml`` (the
      ``last_retry_directive`` field is WRITTEN by the orchestrator-
      skill at retry-dispatch time per Story 5.3's composition).
    * **Pattern 5** — :class:`ScopeAssertionViolation` and
      :class:`ScopeAssertionProbeError` raise loudly with named-
      invariant diagnostics + actionable-fix-pointers per NFR-O5.

Determinism:
    * :class:`ScopeAssertionResult` and :class:`ScopeAssertionDiagnostic`
      are ``dataclass(frozen=True)``; field-declaration order is load-
      bearing for byte-stable :func:`dataclasses.asdict` output
      (downstream Story 5.8 escalation-bundle assembly may serialize
      the diagnostic).
    * The CLI's stdout / stderr formats are byte-stable for the
      AC-7 hook-integration test.

Git-shell-out posture:
    The default git-diff probe shells out via :func:`subprocess.run` —
    the only I/O escape hatch in the module. The injectable
    :data:`ActualDiffProbe` callable abstraction lets tests run pure-
    in-memory (a stub probe returns a known tuple). Mirrors
    :func:`branch_lifecycle.default_working_tree_probe` precedent
    verbatim. Subprocess invocations use the list-form ``args`` (NEVER
    ``shell=True``); shell-injection-safe by construction.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import pathlib
import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import ClassVar, Literal

import yaml

from loud_fail_harness._shared import find_repo_root


@dataclasses.dataclass(frozen=True)
class ScopeAssertionResult:
    """Verifier-output dataclass — the comparison result of
    :func:`verify_scope_assertion`.

    Field semantics:

    * ``is_violation`` — ``True`` if Dev's actual diff contains files
      outside (``affected_files`` ∪ ``scope_expanded_to``); ``False``
      otherwise.
    * ``violating_files`` — frozen tuple of repo-relative file paths
      Dev actually touched but did NOT declare. Empty tuple iff
      ``is_violation == False``. First-occurrence order matches the
      order of paths in the actual-diff probe's output.
    * ``declared_scope`` — verbatim copy of the input ``affected_files``
      parameter (preserved for diagnostic surfacing).
    * ``declared_expansion`` — verbatim copy of the input
      ``scope_expanded_to`` parameter.
    * ``actual_files`` — verbatim copy of the input ``actual_files``
      parameter (the probe's output).
    * ``verified_at`` — ISO-8601 UTC timestamp of when verification
      ran (set by :func:`verify_scope_assertion` at call time).

    ``frozen=True``; field-declaration order load-bearing for byte-
    stable :func:`dataclasses.asdict` output (downstream Story 5.8
    escalation-bundle assembler may serialize for the bundle's
    violation-context section).
    """

    is_violation: bool
    violating_files: tuple[str, ...]
    declared_scope: tuple[str, ...]
    declared_expansion: tuple[str, ...]
    actual_files: tuple[str, ...]
    verified_at: str


@dataclasses.dataclass(frozen=True)
class ScopeAssertionDiagnostic:
    """Emission-ready diagnostic dataclass — the marker payload.

    Built by :func:`make_scope_assertion_diagnostic` ONLY when the
    upstream :class:`ScopeAssertionResult` has ``is_violation == True``
    (constructing a diagnostic for a non-violation is meaningless;
    the builder raises ``ValueError`` if attempted).

    Field semantics:

    * ``marker_class`` — class-var, sourced VERBATIM from
      ``schemas/marker-taxonomy.yaml`` line 237. The ``ClassVar``
      posture mirrors :class:`branch_lifecycle.GitUncommittedWorkDetected.marker_class`
      precedent.
    * ``story_id`` — the BMAD story identifier (caller-supplied at
      diagnostic-construction time).
    * ``retry_round`` — 1-indexed retry attempt number (caller-supplied;
      matches ``run_state.retry_history[].retry_attempt``).
    * ``violating_files`` / ``declared_scope`` / ``declared_expansion``
      — copied from the :class:`ScopeAssertionResult`.

    ``frozen=True``; serializable via :func:`dataclasses.asdict` for
    stderr-emission + escalation-bundle context (Story 5.8 consumer).
    """

    marker_class: ClassVar[Literal["scope-assertion-violation"]] = (
        "scope-assertion-violation"
    )
    story_id: str
    retry_round: int
    violating_files: tuple[str, ...]
    declared_scope: tuple[str, ...]
    declared_expansion: tuple[str, ...]


class ScopeAssertionViolation(Exception):
    """Raised when an operator wants the violation surfaced as an
    exception (not used by the verifier itself — the verifier returns
    a :class:`ScopeAssertionResult`; the exception class exists for
    future callers that prefer the exception path).

    The ``ValueError`` lineage is INTENTIONALLY NOT used here — the
    violation is a flow-blocking domain event, NOT a value-domain
    error. Mirrors :class:`branch_lifecycle.BranchLifecycleBlocked`
    precedent. ``ValueError`` is reserved for input-shape contract
    violations (see :class:`ScopeAssertionProbeError`).

    Pattern 5 named-invariant diagnostic (architecture.md lines
    983-991). The exception's ``__str__`` form includes the
    violating-files list, the declared-scope context, AND the
    remediation-hint substring "review Dev's diff vs. declared
    scope; possibly tighten retry's ``affected_files``" verbatim from
    the marker-taxonomy diagnostic_pointer.
    """

    marker_class: ClassVar[Literal["scope-assertion-violation"]] = (
        "scope-assertion-violation"
    )

    def __init__(self, diagnostic: ScopeAssertionDiagnostic) -> None:
        self.diagnostic: ScopeAssertionDiagnostic = diagnostic
        message = (
            f"scope-assertion-violation: Dev's diff for story "
            f"{diagnostic.story_id!r} (retry round "
            f"{diagnostic.retry_round}) touched "
            f"{len(diagnostic.violating_files)} undeclared file(s): "
            f"{list(diagnostic.violating_files)!r}; "
            f"declared_scope={list(diagnostic.declared_scope)!r}; "
            f"declared_expansion={list(diagnostic.declared_expansion)!r}. "
            "Remediation: review Dev's diff vs. declared scope; "
            "possibly tighten retry's `affected_files`."
        )
        super().__init__(message)


class ScopeAssertionProbeError(ValueError):
    """Raised by :func:`default_actual_diff_probe`'s returned closure
    on git-shell-out failures (non-zero exit, timeout, missing
    ``HEAD~1``, etc.).

    The :class:`ValueError` lineage matches
    :class:`retry_dispatch.RetryDispatchError`'s posture: per-input-
    shape contract violations are value-domain errors. The probe's
    failure indicates either a timing-constraint violation (the
    SubagentStop hook fires AFTER the commit per Story 2.7, so HEAD~1
    must exist at hook time) OR an environmental misconfiguration
    (not a git repo, git not on PATH).

    Message format (per AC-1's diagnostic-shape contract; FR48a /
    NFR-O5 actionable-pointer posture): include the failed git
    command, its stderr, and a remediation hint.
    """


#: Type alias for the sensor-not-advisor probe interface (mirrors
#: :data:`branch_lifecycle.WorkingTreeProbe`). Returns a tuple of
#: repo-relative file path strings representing the files Dev modified
#: in the most recent commit. The default probe targets
#: ``git diff --name-only HEAD~1..HEAD``; tests inject deterministic
#: stubs.
ActualDiffProbe = Callable[[], tuple[str, ...]]


def verify_scope_assertion(
    *,
    affected_files: tuple[str, ...],
    scope_expanded_to: tuple[str, ...],
    actual_files: tuple[str, ...],
) -> ScopeAssertionResult:
    """Compare Dev's actual diff against (``affected_files`` ∪
    ``scope_expanded_to``) and return a :class:`ScopeAssertionResult`.

    Pure function. No I/O; no mutation; no side effects. Keyword-only
    arguments (the leading ``*,`` separator) so that field-order
    confusion at call sites is impossible.

    Algorithm:

    * ``declared_set = set(affected_files) | set(scope_expanded_to)``
      — the union of declared scope.
    * ``actual_set = set(actual_files)``.
    * ``violating_set = actual_set - declared_set`` — files actually
      touched but NOT declared.
    * ``violating_files = tuple(p for p in actual_files if p in
      violating_set)`` — preserves first-occurrence order from the
      probe's output.
    * ``is_violation = bool(violating_files)``.
    * ``verified_at`` — ``datetime.now(timezone.utc).isoformat(
      timespec="seconds")``.

    Args:
        affected_files: Repo-relative file paths the orchestrator
            declared at retry-dispatch time (Story 5.3's
            :func:`derive_affected_files` output, persisted as
            ``run_state.last_retry_directive.affected_files``).
        scope_expanded_to: Repo-relative file paths Dev reported as
            necessary expansion in its return envelope's
            ``scope_expanded_to`` field (Story 5.3's
            :func:`extract_scope_expanded_to` output).
        actual_files: Repo-relative file paths Dev actually touched,
            as observed by the :data:`ActualDiffProbe` (or supplied
            directly by tests).

    Returns:
        :class:`ScopeAssertionResult` carrying the comparison verdict
        + the input fields preserved for diagnostic surfacing.

    Raises:
        ValueError: Any input contains non-string items (programmer-
            error invariant; the upstream :func:`extract_scope_expanded_to`
            and :func:`derive_affected_files` already enforce string-
            typing). Raised as :exc:`ValueError` directly (NOT as
            :exc:`ScopeAssertionViolation` — the violation class is
            reserved for actual scope violations; input-type errors
            are programmer errors).
    """
    affected_tuple = tuple(affected_files)
    expansion_tuple = tuple(scope_expanded_to)
    actual_tuple = tuple(actual_files)

    for label, items in (
        ("affected_files", affected_tuple),
        ("scope_expanded_to", expansion_tuple),
        ("actual_files", actual_tuple),
    ):
        for index, item in enumerate(items):
            if not isinstance(item, str):
                raise ValueError(
                    f"{label}[{index}] must be a str; got "
                    f"{type(item).__name__} ({item!r}). "
                    "Remediation: this indicates a substrate "
                    "composition bug — extract_scope_expanded_to + "
                    "derive_affected_files already enforce string-"
                    "typing at the upstream layer."
                )

    declared_set = set(affected_tuple) | set(expansion_tuple)
    actual_set = set(actual_tuple)
    violating_set = actual_set - declared_set
    violating_files = tuple(p for p in actual_tuple if p in violating_set)
    verified_at = _dt.datetime.now(_dt.timezone.utc).isoformat(
        timespec="seconds"
    )
    return ScopeAssertionResult(
        is_violation=bool(violating_files),
        violating_files=violating_files,
        declared_scope=affected_tuple,
        declared_expansion=expansion_tuple,
        actual_files=actual_tuple,
        verified_at=verified_at,
    )


def make_scope_assertion_diagnostic(
    result: ScopeAssertionResult,
    *,
    story_id: str,
    retry_round: int,
) -> ScopeAssertionDiagnostic:
    """Build an emission-ready :class:`ScopeAssertionDiagnostic` from a
    violation :class:`ScopeAssertionResult`.

    Pure builder. Pre-condition: ``result.is_violation == True``;
    constructing a diagnostic for a non-violation is meaningless.

    Args:
        result: Verifier output. MUST have ``is_violation == True``.
        story_id: BMAD story identifier; non-empty.
        retry_round: 1-indexed retry attempt number; ``>= 1``.

    Returns:
        :class:`ScopeAssertionDiagnostic` with the input fields copied
        verbatim from the result + the caller-supplied ``story_id`` +
        ``retry_round``.

    Raises:
        ValueError: ``result.is_violation == False``, or
            ``story_id`` is empty, or ``retry_round < 1``.
    """
    if not result.is_violation:
        raise ValueError(
            "make_scope_assertion_diagnostic precondition failed: "
            "result.is_violation == False; constructing a diagnostic "
            "for a non-violation is meaningless. Remediation: only "
            "build the diagnostic on the violation branch of the "
            "orchestrator-skill's post-Dev-return routing."
        )
    if not story_id:
        raise ValueError(
            "story_id must be a non-empty str; got empty string. "
            "Remediation: pass the BMAD story identifier "
            "(e.g. '5-4-...') from run_state.story_id."
        )
    if retry_round < 1:
        raise ValueError(
            f"retry_round must be >= 1 (1-indexed per run-state's "
            f"retry_attempt minimum: 1); got {retry_round}. "
            "Remediation: read run_state.retry_history[-1].retry_attempt "
            "or pass len(run_state.retry_history)."
        )
    return ScopeAssertionDiagnostic(
        story_id=story_id,
        retry_round=retry_round,
        violating_files=result.violating_files,
        declared_scope=result.declared_scope,
        declared_expansion=result.declared_expansion,
    )


def default_actual_diff_probe(
    *,
    repo_root: pathlib.Path,
    base_ref: str = "HEAD~1",
    head_ref: str = "HEAD",
) -> ActualDiffProbe:
    """Return an :data:`ActualDiffProbe` callable wrapping
    ``git diff --name-only {base_ref}..{head_ref}``.

    Mirrors :func:`branch_lifecycle.default_working_tree_probe`
    precedent verbatim. The factory closure captures ``repo_root +
    base_ref + head_ref`` AT FACTORY-CALL TIME (closure semantics; not
    lazily re-resolved); subsequent re-binding of the variables in the
    caller's scope does NOT reach into the returned closure.

    The wrapped command is read-only per NFR-S3's allowed-primitives
    enumeration — ``git diff --name-only`` is a read-only diff probe
    that does not mutate the working tree.

    The probe parses ``git diff --name-only`` output: one path per
    line; empty lines stripped; order preserved (matches git's
    output order, which is deterministic for a fixed commit pair).

    Args:
        repo_root: The repository root the ``git diff`` command runs
            against (passed as ``cwd``).
        base_ref: Lower bound of the diff range. Default ``"HEAD~1"``
            because the SubagentStop hook fires AFTER ``git commit``
            per Story 2.7's commit-then-verify ordering, so HEAD~1
            always exists at hook time.
        head_ref: Upper bound of the diff range. Default ``"HEAD"``.

    Returns:
        A zero-arg :data:`ActualDiffProbe` callable.

    Raises:
        ScopeAssertionProbeError: The probe's git invocation failed
            (non-zero exit, timeout, missing ref, not-a-git-repo).
    """
    captured_root = repo_root
    captured_base = base_ref
    captured_head = head_ref

    def _probe() -> tuple[str, ...]:
        cmd = [
            "git",
            "diff",
            "--name-only",
            f"{captured_base}..{captured_head}",
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd=captured_root,
                capture_output=True,
                text=True,
                check=True,
                timeout=10.0,
            )
        except subprocess.TimeoutExpired as exc:
            raise ScopeAssertionProbeError(
                f"git diff probe timed out after 10.0s "
                f"(cmd={cmd!r}, cwd={captured_root!r}). "
                "Remediation: investigate slow git operations on the "
                "repo; the SubagentStop hook fires post-commit, so "
                "this should be fast — check repo size + git config."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise ScopeAssertionProbeError(
                f"git diff probe failed with exit {exc.returncode} "
                f"(cmd={cmd!r}, cwd={captured_root!r}); stderr="
                f"{exc.stderr!r}. Remediation: ensure the repo has at "
                "least two commits at hook time (HEAD~1 must exist; "
                "the SubagentStop hook fires after `git commit` per "
                "Story 2.7 — if this is your first commit, that is "
                "the timing-constraint violation)."
            ) from exc
        except OSError as exc:
            raise ScopeAssertionProbeError(
                f"git diff probe could not invoke git (cmd={cmd!r}, "
                f"cwd={captured_root!r}); OS error: {exc}. Remediation: "
                "ensure git is installed, the cwd exists, and is a "
                "directory (not a file)."
            ) from exc

        return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())

    return _probe


def _format_clean_message(
    *,
    declared_scope: tuple[str, ...],
    declared_expansion: tuple[str, ...],
    actual_files: tuple[str, ...],
) -> str:
    return (
        f"scope-assertion: clean (declared_scope={len(declared_scope)}, "
        f"declared_expansion={len(declared_expansion)}, "
        f"actual={len(actual_files)})"
    )


def _format_violation_message(
    diagnostic: ScopeAssertionDiagnostic,
) -> str:
    """Render the multi-line stderr block emitted by the CLI on
    violation. The format is byte-stable for the AC-7 hook-integration
    test."""
    lines = [
        f"scope-assertion-violation: marker_class={diagnostic.marker_class}",
        f"story_id={diagnostic.story_id}",
        f"retry_round={diagnostic.retry_round}",
        f"declared_scope={list(diagnostic.declared_scope)!r}",
        f"declared_expansion={list(diagnostic.declared_expansion)!r}",
        "violating_files:",
    ]
    for path in diagnostic.violating_files:
        lines.append(f"  - {path}")
    lines.append(
        "Remediation: review Dev's diff vs. declared scope; "
        "possibly tighten retry's `affected_files`."
    )
    return "\n".join(lines)


def _main(argv: Sequence[str] | None = None) -> int:
    """CLI entry-point registered as ``scope-assertion-verify`` in
    ``pyproject.toml`` ``[project.scripts]``.

    Reads run-state YAML from ``--run-state PATH``; extracts
    ``last_retry_directive.affected_files`` (None or empty → exits 0
    silently — no retry in flight, no scope to verify) AND
    ``last_envelope.scope_expanded_to`` (None or empty → empty tuple);
    invokes :func:`default_actual_diff_probe` to compute actual files;
    calls :func:`verify_scope_assertion`.

    On clean: prints a single-line status to stdout; exits 0.
    On violation: prints a structured multi-line diagnostic on stderr
    (one line per violating file + the marker_class identifier + the
    remediation hint); exits 1.

    The output format is byte-stable for the AC-7 hook-integration
    test.
    """
    parser = argparse.ArgumentParser(
        prog="scope-assertion-verify",
        description=(
            "Verify Dev's actual git diff against the orchestrator's "
            "declared scope (Story 5.4 / FR12 + FR58)."
        ),
    )
    parser.add_argument(
        "--run-state",
        required=True,
        type=pathlib.Path,
        help="Path to run-state.yaml (e.g. _bmad/automation/run-state.yaml).",
    )
    parser.add_argument(
        "--repo-root",
        required=False,
        type=pathlib.Path,
        default=None,
        help=(
            "Repo root for the git-diff probe (defaults to "
            "find_repo_root() at call time)."
        ),
    )
    args = parser.parse_args(argv)

    run_state_path: pathlib.Path = args.run_state
    repo_root: pathlib.Path = args.repo_root or find_repo_root()

    try:
        raw = yaml.safe_load(run_state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(
            f"scope-assertion-verify: run-state not found at "
            f"{run_state_path}; nothing to verify (exit 0).",
            file=sys.stderr,
        )
        return 0
    if not isinstance(raw, dict):
        print(
            f"scope-assertion-verify: run-state at {run_state_path} did "
            f"not parse to a YAML mapping; nothing to verify (exit 0).",
            file=sys.stderr,
        )
        return 0

    directive = raw.get("last_retry_directive")
    if not isinstance(directive, dict):
        # No retry in flight; no scope to verify. Exit 0 silently per
        # the AC-1 short-circuit contract.
        print(_format_clean_message(
            declared_scope=(),
            declared_expansion=(),
            actual_files=(),
        ))
        return 0
    affected_raw = directive.get("affected_files") or []
    if not isinstance(affected_raw, list) or not affected_raw:
        # Degenerate / absent directive; nothing to verify.
        print(_format_clean_message(
            declared_scope=(),
            declared_expansion=(),
            actual_files=(),
        ))
        return 0
    affected_files = tuple(str(p) for p in affected_raw)

    envelope = raw.get("last_envelope") or {}
    if not isinstance(envelope, dict):
        envelope = {}
    expansion_raw = envelope.get("scope_expanded_to") or []
    if not isinstance(expansion_raw, list):
        expansion_raw = []
    scope_expanded_to = tuple(str(p) for p in expansion_raw)

    probe = default_actual_diff_probe(repo_root=repo_root)
    try:
        actual_files = probe()
    except ScopeAssertionProbeError as exc:
        print(
            f"scope-assertion-verify: probe-error: {exc}",
            file=sys.stderr,
        )
        return 1

    result = verify_scope_assertion(
        affected_files=affected_files,
        scope_expanded_to=scope_expanded_to,
        actual_files=actual_files,
    )

    if not result.is_violation:
        print(_format_clean_message(
            declared_scope=affected_files,
            declared_expansion=scope_expanded_to,
            actual_files=actual_files,
        ))
        return 0

    story_id = str(raw.get("story_id") or "")
    retry_history = raw.get("retry_history") or []
    if isinstance(retry_history, list) and retry_history:
        last_attempt = retry_history[-1]
        if isinstance(last_attempt, dict):
            try:
                retry_round = int(last_attempt.get("retry_attempt") or 1)
            except (TypeError, ValueError):
                retry_round = 1
        else:
            retry_round = len(retry_history)
    else:
        retry_round = 1

    diagnostic = make_scope_assertion_diagnostic(
        result,
        story_id=story_id or "<unknown>",
        retry_round=retry_round,
    )
    print(_format_violation_message(diagnostic), file=sys.stderr)
    return 1


__all__ = [
    "ActualDiffProbe",
    "ScopeAssertionDiagnostic",
    "ScopeAssertionProbeError",
    "ScopeAssertionResult",
    "ScopeAssertionViolation",
    "default_actual_diff_probe",
    "make_scope_assertion_diagnostic",
    "verify_scope_assertion",
]
