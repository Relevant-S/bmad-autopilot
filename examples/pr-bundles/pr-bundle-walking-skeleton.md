<!--
Canonical example PR bundle fixture — regenerated at Story 4.13
(QA wrapper thickening completion + `is_full_qa_present` flag flip;
post-3.4 + post-4.13 cumulative flag-flip state — TWO flags True
(`is_full_review_present` since Story 3.4; `is_full_qa_present` since
Story 4.13); TWO flags False (`is_retry_present` — Epic 5 owns;
`is_loud_fail_block_present` — Epic 6 owns)).

Source story: bmad-autopilot/_bmad-output/implementation-artifacts/4-13-qa-wrapper-thickening-completion.md
Source envelopes (canonical corpus — unchanged at Story 4.13 because
the QA envelope's bundle-side rendering is unchanged at the envelope
shape level; the thickening is at the wrapper-side prose + the
flag-flip rendering, not at the envelope-rendering code):
  - examples/envelopes/dev-pass.yaml                 (Story 1.2)
  - examples/envelopes/review-pass-three-layer.yaml  (Story 3.1)
  - examples/envelopes/qa-pass-ac1-tier1.yaml        (Story 2.10)
Assembler module: tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py

This fixture is a regression baseline. Subsequent epics (5 / 6)
regenerate this fixture in place when bundle rendering thickens —
review the diff before committing the regenerated fixture. The Story
4.13 regeneration delta is the dropped "Tier-1 evidence only" bullet
from the Walking Skeleton Mode header (the structural witness of
`is_full_qa_present()` flipping True); no edit to the assembler's
`_render_walking_skeleton_header` or `_THICKENING_SENTENCES` was
required.
-->
# PR bundle — story sample-auto-001 (run run-2026-04-29-001)

Branch: bmad-automation/story/sample-auto-001
Final state: done
Generated: 2026-04-29T12:00:00+00:00

## ⚠️ Walking Skeleton Mode

This PR bundle is a walking-skeleton — it enumerates the structural shape of the BMAD automation loop while the following thickenings remain unfinished:

- No retry (Epic 5 thickens with whole-story retry budget + bucket-driven action item derivation).
- No loud-fail block (Epic 6 thickens with the dedicated top-of-bundle loud-fail block + per-specialist × per-retry cost breakdown + actionable how-to-enable pointers).

## Per-AC results

> **Plan-persistence compromise note (FR25):**
>
> This plan is persisted across runs for resumability.
> Persistence is a known compromise: full QA independence would re-derive the plan every run.
> See `docs/extension-audit.md` and FR-P2-9 (Phase 2 upgrade replacing this with per-run plan re-derivation cross-check).

### AC-1 — status: `pass`

**Assertions:**
- HTTP POST /healthz returned status code 200

**Evidence:**
- `_bmad-output/qa-evidence/sample-001/run-2026-04-29-001/ac1-http-200.log`

**Semantic verification:** `not_applicable`

## Review findings

### bucket: defer

**MED:**
- [blind] `review-001` — Diff-only adversarial pass surfaced no contract violations (`bmad-autopilot/agents/review-bmad-wrapper.md:1`)

**LOW:**
- [edge] `review-002` — Boundary condition on partial layer failure shape covered by fixtures (`bmad-autopilot/agents/review-bmad-wrapper.md:55`)
- [auditor] `review-003` — Story doc references epics.md line numbers verbatim (`bmad-autopilot/_bmad-output/implementation-artifacts/3-1-three-layer-parallel-pass-wiring.md:1`)
- [merged] `review-004` — Wrapper prose explicitly names all three layer identifiers (`bmad-autopilot/agents/review-bmad-wrapper.md:25`)

Failed layers: (none)

## Dev

**Proposed commit message:**

```
feat(harness): land envelope schema + validator (substrate component 1)
```

Scope expanded to: (none)


<!-- bmad-automation:marker walking-skeleton-bundle -->
