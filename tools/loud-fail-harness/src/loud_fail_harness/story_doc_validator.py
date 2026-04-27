"""Story-doc section-allowlist contract library (story 1.10b). FR66 + NFR-S5.

Architectural placement (story 1.10a precedent — story 1.10b Dev Notes
"Do not add a 6th substrate component slot"): this module is structurally
a sibling of the five substrate-component modules
(``envelope_validator``, ``event_validator``, ``reconciler``,
``enumeration_check``, ``fixture_coverage``), the prior CI gates
(``fr33_fixture_gate`` from story 1.8, ``hook_budget_gate`` from story 1.9,
``pluggability_gate`` from story 1.10a) and the substrate-shared helper
``_shared`` (extracted in story 1.5). It is **NOT a sixth substrate
component**. ADR-003 Consequence 1 enumerates exactly five substrate
components (architecture.md line 311-315); this module is a substrate
**library** consumed by Epic 2/3/4/5 specialist subagents at runtime to
enforce FR66 / NFR-S5 against story-doc writes. The substrate-component
count stays at FIVE; the harness module count grows.

Closer in shape to ``_shared.py`` than to ``pluggability_gate.py`` /
``hook_budget_gate.py`` (both directory-scanning CI gates): there is no
canonical filesystem surface to scan at this story's landing time because
story-doc writes happen at specialist runtime in Epic 2+, not as committed
filesystem artifacts on disk.

What this library enforces:
    * **FR66** (PRD line 901; epics.md line 114; architecture.md
      lines 999-1005) — "Automator writes only to documented story-doc
      sections (``## Dev Agent Record``, ``## Senior Developer Review (AI)``,
      ``## Review Findings``, new ``## QA Behavioral Plan``,
      ``## Review Follow-ups (AI)``) — never to arbitrary or BMAD-core-
      owned sections whose semantics it does not own." This library IS the
      FR66 enforcement primitive at the call site: specialists wrap their
      story-doc writes in ``validate_section_write(section_name)`` BEFORE
      the write happens; rejection returns the
      ``"undocumented-section-write"`` marker-class identifier for the
      caller to emit.
    * **NFR-S5** (PRD line 973) — "Story-doc write scope — Automator writes
      only to documented story-doc sections (per FR66). Writes to
      undocumented sections fail contract validation and surface a loud-
      fail marker (``undocumented-section-write: {section-name}``); the
      constraint is **contract-enforced, NOT filesystem-permission-
      enforced**. The choice prioritizes fail-loud visibility over
      filesystem ACL hardening." This library IS the contract; the marker-
      class registration lives in ``schemas/marker-taxonomy.yaml`` line 151
      (added in story 1.4 per the FR-named-class proactive-add discipline).

Marker-class linkage (sensor-not-advisor stance per Pattern 5 + ADR-005):
    The ``"undocumented-section-write"`` string is a STRING IDENTIFIER
    consumed from ``schemas/marker-taxonomy.yaml``. This library NEVER
    re-declares the class, NEVER mutates the taxonomy, NEVER emits the
    marker itself. The seam contract is one-directional: the taxonomy is
    the authoritative declaration; this library returns the identifier in
    ``ValidationResult.marker``; the calling SPECIALIST (Dev wrapper at
    story 2.8, Review-BMAD wrapper at story 3.2, QA wrapper at story 4.x,
    Review-BMAD wrapper writing ``## Review Follow-ups (AI)`` per
    epics.md line 501) is responsible for emission via its envelope + the
    orchestrator's event log (per ADR-005's multi-writer story-doc model).

Cross-story seam contracts (1.10b is invariant-pinned BEFORE downstream
specialist files land):
    * Story 2.8 lands ``agents/dev-wrapper.md``; consumes
      ``validate_section_write("## Dev Agent Record")`` BEFORE writing the
      section.
    * Story 2.9 lands ``agents/review-bmad-wrapper.md``; consumes
      ``validate_section_write("## Senior Developer Review (AI)")`` and
      ``validate_section_write("## Review Findings")``.
    * Story 2.10 lands ``agents/qa.md``; consumes
      ``validate_section_write("## QA Behavioral Plan")`` per epics.md
      line 1832 ("plan persistence via section-allowlist (write to
      allowlisted section succeeds; write to a non-allowlisted variant
      fails per Story 1.10b)").
    * Story 3.2 (Review-BMAD wrapper PR) consumes
      ``validate_section_write("## Senior Developer Review (AI)")`` +
      ``validate_section_write("## Review Findings")``.
    * Stories 4.x (QA elaboration) consume
      ``validate_section_write("## QA Behavioral Plan")`` for plan-
      persistence write paths.
    * Stories 5.x (retry-escalation) consume
      ``validate_section_write("## Review Follow-ups (AI)")`` per
      epics.md line 501.

The 5-section allowlist is the SINGLE source of truth in code; specialist
subagents (Epic 2+) import this constant or call ``validate_section_write``
rather than maintaining a per-specialist list (DRY discipline parallel to
``_shared.find_repo_root`` from story 1.5).

Strict-equality + informational-suggestion split (the deliberate framing
that prevents silent contract bypass):
    The contract is **strict equality** — Python ``in`` over the canonical
    tuple; bytewise comparison; case-sensitive; whitespace-significant.
    ``"## qa behavioral plan"`` (lowercase) is NOT accepted;
    ``"## QA Behavioral Plan "`` (trailing space) is NOT accepted;
    ``"  ## Dev Agent Record"`` (leading whitespace) is NOT accepted. Any
    normalization (``str.lower``, ``str.strip``, NFKC, ``re.IGNORECASE``,
    leading-``## `` re-prefixing) would silently accept inputs the FR66
    contract rejects.

    The ``suggestion`` field is **informational only** — derived via
    ``difflib.get_close_matches(section_name, ALLOWED_SECTIONS, n=1,
    cutoff=0.6)`` (stdlib; Ratcliff-Obershelp ratio — equivalent string-
    distance heuristic to Levenshtein per AC-4's wording). The cutoff
    ``0.6`` is ``difflib``'s documented default and matches typical "did
    you mean" UX conventions (too low produces noisy false-suggestions for
    genuinely-unrelated input; too high suppresses legitimate near-miss
    suggestions). The suggestion is NEVER a fallback match — the equality
    decision is decided by strict equality, never by suggestion presence.

Sensor-not-advisor (PRD-level invariant + ADR-005 multi-writer):
    The library RETURNS the rejection + the marker-class-to-emit; it
    does NOT emit markers itself, does NOT auto-correct the section name,
    does NOT normalize whitespace, does NOT lowercase or fuzzy-match for
    the equality decision, does NOT log, does NOT print (except in
    ``main`` — the CLI is a thin I/O wrapper). Same posture as 1.4 / 1.5 /
    1.6 / 1.7 / 1.8 / 1.9 / 1.10a.

Cross-component reuse posture (story 1.10b do-not-do matrix
"do not import from other validator/gate modules"):
    * ``difflib.get_close_matches`` from stdlib — REUSED for the suggestion
      algorithm. No new runtime dependency.
    * ``pydantic.BaseModel`` + ``pydantic.ConfigDict`` — REUSED for
      ``ValidationResult`` (already pinned by stories 1.1 / 1.2).
    * ``loud_fail_harness._shared.find_repo_root`` — NOT used by the
      library's pure path. Reused only by the seam-test in
      ``tests/test_story_doc_validator.py`` for reading the taxonomy file.

Pattern 7 linkage (architecture.md lines 999-1005, line 1031):
    This library IS Pattern 7's CI-enforcement mechanism for the parts of
    Pattern 7 that admit programmatic enforcement; the broader BMAD-core-
    owned-section abstinence rule is review-enforced. CI enforcement at
    landing time is (a) the test suite asserting library behavior (the
    existing ``uv run pytest`` step exercises ``test_story_doc_validator.py``),
    (b) the existing ``enumeration_check`` (story 1.5) verifying the
    marker class is in ``schemas/marker-taxonomy.yaml``. At Epic 2+,
    specialists wrap their write paths in ``validate_section_write`` calls
    — turning the library into a runtime enforcement primitive at every
    specialist write.

Why no separate CI workflow step (AC-7 rationale):
    Unlike ``pluggability-gate`` (which scans ``agents/``) or
    ``hook-budget-gate`` (which scans ``hooks/``),
    ``story-doc-validator`` has NO canonical filesystem surface to scan at
    MVP — story-doc writes happen at specialist runtime, not as committed
    filesystem artifacts. The optional CLI is registered for manual
    smoke-testing only (``uv run story-doc-validator '## QA Behavioral Plan'``);
    it is NOT wired into ``.github/workflows/ci.yml``. If a future epic
    discovers a need for a static-scan variant (e.g., scan all story doc
    files under ``_bmad-output/implementation-artifacts/`` for non-
    allowlisted sections), THAT epic can build it on top of
    ``validate_section_write``.

Determinism (parallel to 1.4 / 1.5 / 1.6 / 1.7 / 1.8 / 1.9 / 1.10a):
    * ``ALLOWED_SECTIONS`` is a frozen ``tuple`` — iteration order is
      stable (NOT a ``set``: hash-randomization breaks suggestion-tiebreak
      determinism).
    * ``validate_section_write(x).model_dump_json()`` is byte-identical
      across two invocations on the same input.
    * ``difflib.get_close_matches`` is stable per Python's documentation;
      the highest-ratio match is unambiguous, ties broken by allowlist
      iteration order (the canonical PRD-line-901 order).
    * ``ValidationResult`` is a Pydantic v2 frozen model with field-
      declaration-order JSON serialization (load-bearing for byte-stable
      ``model_dump_json()``).
"""

from __future__ import annotations

import argparse
import difflib
import sys
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

#: Canonical 5-section allowlist for the story-doc write scope (FR66 +
#: NFR-S5). The order is load-bearing per AC-2: matches PRD line 901's
#: enumeration order — Dev Agent Record first because it is the
#: chronologically-first specialist write per ADR-005's section-presence-
#: implies-state oracle; QA Behavioral Plan fourth because it is the
#: upstream-proposal addition; Review Follow-ups last because it is the
#: post-retry-escalation write per epics.md line 501. The ``## `` prefix
#: is part of the section identity, not a parsing artifact — a string
#: ``"Dev Agent Record"`` without the prefix is NOT a valid section name
#: per FR66's exact-spelling commitment.
#:
#: ``tuple`` is non-negotiable here: ``set`` iteration order varies across
#: runs (PYTHONHASHSEED), which would break the suggestion-tiebreak
#: determinism; ``list`` is mutable, allowing a contributor to ``.append``
#: at runtime and silently expand the allowlist outside the contract
#: surface. ``tuple`` is immutable + ordered + hashable + iteration-order-
#: stable per Python guarantees.
ALLOWED_SECTIONS: tuple[str, ...] = (
    "## Dev Agent Record",
    "## Senior Developer Review (AI)",
    "## Review Findings",
    "## QA Behavioral Plan",
    "## Review Follow-ups (AI)",
)

#: ``difflib.get_close_matches`` cutoff used by the suggestion algorithm.
#: ``0.6`` is ``difflib``'s documented default — produces useful "did you
#: mean" UX for typo-shaped near-misses (``## QA Plan`` → ``## QA
#: Behavioral Plan``) AND suppresses suggestions for unrelated input
#: (``## Random Topic`` → ``None``). Documented as a deliberate trade-off
#: per AC-4: too low produces noisy false-suggestions for genuinely-
#: unrelated input; too high suppresses legitimate near-miss suggestions.
_SUGGESTION_CUTOFF: float = 0.6

#: Marker-class string identifier (consumed from
#: ``schemas/marker-taxonomy.yaml`` line 151; added in story 1.4 per the
#: FR-named-class proactive-add discipline). Stored as a string literal —
#: NOT an ``enum.Enum`` value — because the YAML file IS the authoritative
#: declaration of marker classes (per Pattern 2). Re-declaring it as an
#: enum would create two sources of truth that could drift.
_MARKER_UNDOCUMENTED_SECTION_WRITE: str = "undocumented-section-write"


class ValidationResult(BaseModel):
    """Result of a story-doc section-name validation.

    Frozen for hashability + determinism; field declaration order is load-
    bearing for byte-stable ``model_dump_json()`` output (parallel to
    1.4 / 1.5 / 1.6 / 1.7 / 1.8 / 1.9 / 1.10a discipline).

    Field semantics:
        * ``accepted`` — strict-equality decision. ``True`` if and only if
          ``section_name in ALLOWED_SECTIONS``.
        * ``section_name`` — the input as received (NOT normalized;
          preserves the exact bytes the caller passed). Surfaced so the
          caller can correlate the rejection with its own log line.
        * ``marker`` — ``"undocumented-section-write"`` on rejection;
          ``None`` on acceptance. The string is the marker-class IDENTIFIER
          owned by ``schemas/marker-taxonomy.yaml``; the calling specialist
          emits the marker itself.
        * ``reason`` — human-readable explanation
          (``"section in v1 allowlist"`` on accept;
          ``"section not in v1 allowlist"`` on reject).
        * ``suggestion`` — closest allowlisted name on rejection (when
          ``difflib.get_close_matches`` returns a candidate clearing the
          cutoff); ``None`` otherwise. **Informational only** — never a
          fallback match.
    """

    model_config = ConfigDict(frozen=True)

    accepted: bool
    section_name: str
    marker: str | None
    reason: str
    suggestion: str | None


def is_allowed(section_name: str) -> bool:
    """Return ``True`` if ``section_name`` is an exact element of
    :data:`ALLOWED_SECTIONS`; ``False`` otherwise.

    Strict equality: ``section_name in ALLOWED_SECTIONS``. Case-sensitive,
    whitespace-significant, no normalization.

    Raises ``TypeError`` if ``section_name`` is not a ``str`` (defensive
    runtime check parallel to :func:`validate_section_write`).
    """
    if not isinstance(section_name, str):
        raise TypeError(
            f"section_name must be str, got {type(section_name).__name__}"
        )
    return section_name in ALLOWED_SECTIONS


def closest_allowlisted(
    section_name: str,
    n: int = 1,
    cutoff: float = _SUGGESTION_CUTOFF,
) -> list[str]:
    """Return up to ``n`` near-miss matches from :data:`ALLOWED_SECTIONS`
    for ``section_name``, ordered by descending similarity ratio.

    Thin wrapper around :func:`difflib.get_close_matches`. Returns ``[]``
    if no candidate clears the cutoff. Exposed as a separate helper so
    Epic 2+ consumers that want multiple candidates (e.g., a richer
    "did you mean" UX) can call it directly with custom ``n`` /
    ``cutoff``.

    Raises ``TypeError`` if ``section_name`` is not a ``str``.
    """
    if not isinstance(section_name, str):
        raise TypeError(
            f"section_name must be str, got {type(section_name).__name__}"
        )
    return difflib.get_close_matches(
        section_name, ALLOWED_SECTIONS, n=n, cutoff=cutoff
    )


def validate_section_write(section_name: str) -> ValidationResult:
    """Validate ``section_name`` against the v1 allowlist.

    Returns :class:`ValidationResult` with:
        * ``accepted=True``, ``marker=None``, ``suggestion=None``,
          ``reason="section in v1 allowlist"`` if
          ``section_name in ALLOWED_SECTIONS`` (strict equality).
        * ``accepted=False``,
          ``marker="undocumented-section-write"``,
          ``reason="section not in v1 allowlist"``,
          ``suggestion=<closest allowlisted name>`` (or ``None`` if no
          candidate clears the cutoff) otherwise.

    The function is pure — no global state mutation, no logging, no
    printing, no filesystem I/O. Repeated calls with the same input
    produce byte-identical ``ValidationResult.model_dump_json()`` output.

    The function does NOT emit the marker (per Pattern 5 sensor-not-
    advisor; per ADR-005 multi-writer story-doc model). The caller —
    specialist subagent + orchestrator in Epic 2/3/4/5 — is responsible
    for emission via its envelope + the orchestrator event log.

    Raises ``TypeError`` if ``section_name`` is not a ``str`` (the
    message names the offending type for diagnosability; parallel to the
    validator-module pattern from 1.2 / 1.3).
    """
    if not isinstance(section_name, str):
        raise TypeError(
            f"section_name must be str, got {type(section_name).__name__}"
        )
    if section_name in ALLOWED_SECTIONS:
        return ValidationResult(
            accepted=True,
            section_name=section_name,
            marker=None,
            reason="section in v1 allowlist",
            suggestion=None,
        )
    suggestions = closest_allowlisted(
        section_name, n=1, cutoff=_SUGGESTION_CUTOFF
    )
    return ValidationResult(
        accepted=False,
        section_name=section_name,
        marker=_MARKER_UNDOCUMENTED_SECTION_WRITE,
        reason="section not in v1 allowlist",
        suggestion=suggestions[0] if suggestions else None,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="story-doc-validator",
        description=(
            "Validate a story-doc section name against the v1 allowlist "
            "(FR66 / NFR-S5). Returns exit 0 on accept, 1 on reject, "
            "2 on harness-level error. Manual smoke-test aid; NOT a CI "
            "gate step (the library has no canonical filesystem surface "
            "to scan at MVP — story-doc writes happen at specialist "
            "runtime, not as committed filesystem artifacts)."
        ),
    )
    parser.add_argument(
        "section_name",
        help=(
            "The section name to validate (e.g., '## Dev Agent Record'). "
            "The '## ' prefix is part of the section identity per FR66's "
            "exact-spelling commitment."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. AC-7 manual smoke-test aid.

    Returns:
        0 — accepted (``result.accepted is True``).
        1 — rejected (``result.accepted is False``).
        2 — harness-level error (e.g., ``TypeError`` from a non-string
            argument; only reachable via direct ``main(...)`` invocation
            with a non-list argv, since argparse's standard input
            validation catches these before the function runs).

    Stdout: ``result.model_dump_json(indent=2)``. Stderr (only on exit
    2): ``"harness-level error: <message>"`` per the established
    1.5 / 1.6 / 1.7 / 1.8 / 1.9 / 1.10a pattern.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    try:
        result = validate_section_write(args.section_name)
    except TypeError as exc:
        print(f"harness-level error: {exc}", file=sys.stderr)
        return 2
    print(result.model_dump_json(indent=2))
    return 0 if result.accepted else 1


__all__ = [
    "ALLOWED_SECTIONS",
    "ValidationResult",
    "validate_section_write",
    "is_allowed",
    "closest_allowlisted",
]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
