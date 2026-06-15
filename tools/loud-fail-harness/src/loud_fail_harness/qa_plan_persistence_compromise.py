"""QA plan-persistence-compromise visibility library — Story 4.11. FR25.

Architectural placement (parallel to ``qa_behavioral_plan`` from Story 4.1
and ``qa_plan_drift`` from Story 4.2): this module is structurally a pure-
library sibling of the substrate-component modules and the prior cell-2
QA-thickening modules. It is **NOT a sixth substrate component** (ADR-003
enumerates exactly five substrate components at architecture.md lines
311-315; ``bundle_assembly`` is already the cell-2 sixth-by-sequence
non-substrate library). It is a pure library consumed by Story 4.1's
:func:`loud_fail_harness.qa_behavioral_plan.render_plan_section` AND
Story 2.11's :func:`loud_fail_harness.bundle_assembly._render_per_ac_section`
to satisfy FR25's "QA documents its plan-persistence-compromise visibly
in the QA Behavioral Plan section AND in the PR bundle" commitment
(PRD line 841).

What this library owns:
    * :data:`COMPROMISE_NOTE_BODY` — a frozen module-level multi-line
      string constant carrying the canonical compromise prose. Three
      lines (newline-separated; no trailing newline). Closest precedent
      is :data:`loud_fail_harness.qa_evidence_tier._HOW_TO_ENABLE_POINTER`
      (Story 4.8's frozen multi-line text constant pattern).
    * :func:`render_compromise_blockquote` — a pure helper rendering
      :data:`COMPROMISE_NOTE_BODY` as a level-1 markdown blockquote
      (``> `` prefix on every line; bold FR25-anchored heading line +
      blank blockquote line + each compromise prose line as ``> ``-
      prefixed continuation; trailing newline so downstream
      concatenation produces well-formed markdown). Takes no arguments;
      fully deterministic.

Verbatim epic AC (``_bmad-output/planning-artifacts/epics.md`` lines
2124-2148, reproduced as a procedural checklist):

    1. Extend Story 4.1's ``render_plan_section`` so every rendered plan
       body carries a canonical ``> **Plan-persistence compromise note
       (FR25):**`` markdown blockquote naming the persistence-vs-purity
       tradeoff + the FR-P2-9 Phase-2 upgrade path + the
       ``docs/extension-audit.md`` cross-reference.
    2. Extend Story 2.11's bundle assembler ``_render_per_ac_section``
       to prepend the SAME blockquote at the top of ``## Per-AC results``
       so the compromise is visible at PR-review time without scrolling
       into the story doc.
    3. Author a single source-of-truth module (THIS module) exposing
       :data:`COMPROMISE_NOTE_BODY` + :func:`render_compromise_blockquote`
       consumed by both render sites — the structured-config-consumed-
       by-assembler half of the verbatim epic AC at ``epics.md`` line
       2139 ("the bundle reads the compromise content from
       ``docs/extension-audit.md`` (or from a structured config consumed
       by the assembler) rather than duplicating prose — same drift-
       prevention pattern as Story 1.12a's TEA-boundary doc").
    4. Append ONE new row to ``bmad-autopilot/docs/extension-audit.md``
       per-convention table for the ``QA Behavioral Plan persistence``
       convention with classification ``automator-internal`` + Phase-2
       upgrade marker ``FR-P2-9``. The audit-doc row carries the same
       canonical prose verbatim so a single drift-prevention test
       (audit-doc-contains-:data:`COMPROMISE_NOTE_BODY`-lines) structurally
       enforces single-source-of-truth equivalence between the constant
       + the audit doc + both render sites.

FR-P2-9 Phase-2 upgrade pointer (``_bmad-output/planning-artifacts/prd.md``
line 128 — "Per-run plan re-derivation cross-check"): MVP accepts plan
persistence to support ``bmad-automation:resume {story-id}`` from Story
8.3 without re-deriving the plan; full QA independence per FR-P2-9 re-derives
the plan every run with a cross-check against the persisted plan
(Story 20.1, LANDED — :mod:`loud_fail_harness.qa_plan_rederivation`).
The FR-P2-9 resolution is **retain-and-accompany, NOT remove**: THIS
module's :data:`COMPROMISE_NOTE_BODY` constant + both render sites are
RETAINED; Story 20.1 adds an independent, read-only per-run cross-check
that ACCOMPANIES the compromise note (the persistence-for-resumability
tradeoff still stands — ``bmad-automation:resume`` relies on the
persisted plan), making the re-derivation guarantee inspectable in the
PR bundle co-located with this note. The audit-doc row is retained and
annotated accordingly; the constant's line-3 forward-pointer to FR-P2-9
remains accurate prose.

Cross-reference to ``docs/extension-audit.md``:
    The audit doc's per-convention table carries one row appended by
    THIS story (Story 4.11) for the ``QA Behavioral Plan persistence``
    convention. The row's rationale cell embeds :data:`COMPROMISE_NOTE_BODY`
    verbatim — the drift-prevention anchor. The
    :mod:`test_qa_plan_persistence_compromise` per-line substring freshness
    test asserts every non-empty line of the constant is a substring of
    the audit doc's text, preventing silent drift between the constant
    + the audit-doc row.

Consumer linkage:
    * :func:`loud_fail_harness.qa_behavioral_plan.render_plan_section`
      (Story 4.1) PREPENDS :func:`render_compromise_blockquote` output
      to its rendered body. The compromise blockquote is the FIRST
      content of the rendered ``## QA Behavioral Plan`` section body;
      followed by a blank line; followed by the existing two HTML-
      comment metadata lines (``plan_status`` + ``ac_hash``); followed
      by the per-AC entries.
    * :func:`loud_fail_harness.bundle_assembly._render_per_ac_section`
      (Story 2.11) PREPENDS :func:`render_compromise_blockquote` output
      to its rendered ``## Per-AC results`` section body. The compromise
      blockquote is the FIRST content under the H2 header; followed by a
      blank line; followed by the existing ``ac_results`` blocks (and
      the optional ``### Plan drift detected`` + ``### Exploratory
      heuristic findings`` H3 sub-sections from Stories 4.2 + 4.9).
    * The wrapper-side composition (``bmad-autopilot/agents/qa.md``)
      is DEFERRED to Story 4.13 (wrapper-completion thickening); the
      wrapper continues to forward-point at Story 4.13's surface for
      compromise-note authoring. THIS story pre-positions the rendering
      primitives as substrate so 4.13's wrapper-thickening composes them
      via library-by-path-citation discipline (ADR-005).

Cross-component reuse posture:
    * Python stdlib only — NO new runtime dependencies. The module
      imports nothing beyond ``typing.Final`` (used to mark the
      module-level constant as semantically frozen for mypy).
    * NO ``pydantic.BaseModel`` — there is no per-plan structured data;
      the compromise note is fixed-text decoration sourced from the
      canonical constant on every render, NOT round-tripped through
      :func:`loud_fail_harness.qa_behavioral_plan.parse_plan_section`
      as structured data.
    * NO ``yaml`` — the canonical text lives in this Python module, NOT
      in a YAML config file. Adding a third drift surface (YAML config
      + Python module + audit doc) was rejected at story-design time
      because the audit doc IS the human-readable surface; a YAML config
      would expand the drift surface without adding a benefit.
    * NO ``jsonschema`` — the compromise note is render-surface, not
      contract-shape.

Sensor-not-advisor (PRD-level invariant + Pattern 5):
    The library RENDERS canonical prose; it does NOT call validators,
    does NOT emit markers, does NOT read or write files (the audit-doc
    cross-reference is a *static* doc-level pointer, NOT a runtime read),
    does NOT log, does NOT print. Same posture as Stories 1.4 / 1.5 /
    1.6 / 1.7 / 1.8 / 1.9 / 1.10a / 1.10b / 4.1 / 4.2 / 4.6 / 4.7 / 4.8 /
    4.9 / 4.10.

In-place-thickening linkage (Epic 3 retro Insight #1, third confirmation):
    NO ``agents/qa.md`` modification at THIS story (Story 4.13 owns
    wrapper-completion thickening per ``epics.md`` line 2192). Same
    agent identity, same envelope contract — only the rendering
    primitives are added under ``src/loud_fail_harness/`` for 4.13's
    wrapper-thickening to compose. Six stale forward-pointers in
    pre-existing modules (``bundle_assembly.py``, ``http_driver.py``,
    ``playwright_driver.py``, ``qa_ac_iteration.py``, ``qa_evidence_tier.py``)
    that referenced "Story 4.11" as the bundle-render-thickening
    finalization site for tier-aware / structured-emission rendering
    are corrected to reference Story 4.13 per Pattern 5's loud-fail
    discipline applied to documentation drift.
"""

from __future__ import annotations

from typing import Final

#: The canonical compromise prose. Three lines (``\n``-separated; no
#: trailing newline). Each line is a self-contained sentence:
#:
#: * Line 1 — the persistence statement (verbatim per ``epics.md`` line
#:   2134).
#: * Line 2 — the persistence-vs-purity tradeoff (verbatim per the same
#:   line).
#: * Line 3 — the cross-references to ``docs/extension-audit.md`` and
#:   FR-P2-9.
#:
#: Stored as a single string with embedded ``\n`` rather than as a list
#: of lines because consumers join differently:
#: :func:`render_compromise_blockquote` formats each line with the ``> ``
#: blockquote prefix; the audit-doc row's drift-prevention test splits
#: on ``\n`` and asserts each non-empty line is a substring of the audit
#: doc's text.
COMPROMISE_NOTE_BODY: Final[str] = (
    "This plan is persisted across runs for resumability.\n"
    "Persistence is a known compromise: full QA independence would "
    "re-derive the plan every run.\n"
    "See `docs/extension-audit.md` and FR-P2-9 "
    "(Story 20.1, LANDED — accompanies this note with per-run plan re-derivation cross-check)."
)


def render_compromise_blockquote() -> str:
    """Render :data:`COMPROMISE_NOTE_BODY` as a level-1 markdown
    blockquote with the canonical FR25-anchored heading line.

    Output shape (deterministic; same on every call)::

        > **Plan-persistence compromise note (FR25):**
        >
        > {COMPROMISE_NOTE_BODY line 1}
        > {COMPROMISE_NOTE_BODY line 2}
        > {COMPROMISE_NOTE_BODY line 3}

    Every line begins with ``> `` (the blockquote prefix); the second
    line carries only the prefix (an "empty" blockquote line separating
    the bold heading from the prose); each compromise prose line is a
    ``> ``-prefixed continuation. The output ends with a trailing
    newline so downstream concatenation with subsequent markdown
    produces well-formed structure (no run-on with the next paragraph).

    Returns:
        The rendered blockquote string. Pure: takes no arguments;
        depends only on :data:`COMPROMISE_NOTE_BODY`; has no side
        effects.
    """
    lines = ["> **Plan-persistence compromise note (FR25):**", ">"]
    for body_line in COMPROMISE_NOTE_BODY.split("\n"):
        lines.append(f"> {body_line}")
    return "\n".join(lines) + "\n"


__all__ = ["COMPROMISE_NOTE_BODY", "render_compromise_blockquote"]
