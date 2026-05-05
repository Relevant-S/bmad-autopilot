<!--
Canonical example PR bundle fixture — regenerated at Story 6.1
(loud-fail block + structural-derivation flag flip; Epic 6 OPEN; the
in-place-flip cohort closes — FOUR flags True (`is_full_review_present`
since Story 3.4; `is_full_qa_present` since Story 4.13;
`is_retry_present` since Story 5.9; `is_loud_fail_block_present` since
Story 6.1 — flipped via *structural derivation* against
`inspect.getsource(bundle_assembly.assemble_bundle)` per AC-2's
drift-prevention contract-pair contract).

Source story: bmad-autopilot/_bmad-output/implementation-artifacts/6-1-loud-fail-block-pr-bundle-structure-computed-flag-marker-emission-inversion.md
Source envelopes (canonical corpus — unchanged at Story 6.1 because
6.1 adds the loud-fail block sub-renderer + the computed flag without
edits to the canonical envelope corpus):
  - examples/envelopes/dev-pass.yaml                 (Story 1.2)
  - examples/envelopes/review-pass-three-layer.yaml  (Story 3.1)
  - examples/envelopes/qa-pass-ac1-tier1.yaml        (Story 2.10)
Assembler module: tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py

This fixture is a regression baseline. The pre-Epic-6 snapshot is
preserved at `pre-epic-6-snapshot.md` per Story 6.1 AC-4 + Story 1.4's
permanence rule — the snapshot retains the original
structured `bmad-automation:marker walking-skeleton-bundle` comment as a
provenance signal of the pre-6.1 era. Subsequent epics regenerate THIS
fixture in place when bundle rendering thickens; the snapshot is
NEVER touched.

Story 6.1 regeneration delta:
  (i)   Walking Skeleton Mode header now renders the all-thickenings-
        landed sentinel (the four sentence-prefixes — "Single-layer
        review" / "Tier-1 evidence only" / "No retry" / "No loud-fail
        block" — are all dropped because all four flags return True).
  (ii)  New `## ✓ Loud-Fail Markers — None` H2 block rendered as the
        FIRST content section after the title metadata block + Walking
        Skeleton header per AC-1 + AC-3.
  (iii) The structured `bmad-automation:marker walking-skeleton-bundle`
        comment is dropped from the bundle — the structural rule
        `if flags.is_loud_fail_block_present(): return ()` at
        `_emit_walking_skeleton_marker` fires (the rule itself is
        unchanged; only the flag's return value changed).
  (iv)  No edit to `_render_walking_skeleton_header`,
        `_THICKENING_SENTENCES`, OR `_emit_walking_skeleton_marker` was
        required — the inversion flows entirely through the new flag
        semantics per AC-4.

Story 6.2 update (FR31 actionable-pointer enrichment):
  - The per-marker `- How to enable:` bullet's content is now the
    interpolated `diagnostic_pointer` text (un-interpolated for
    context-free markers like `walking-skeleton-bundle`) instead of
    the literal `_HOW_TO_ENABLE_PLACEHOLDER` string Story 6.1 emitted
    at the same structural position.
  - Fixture body is unchanged at this story's landing because
    `active_markers` is empty here (the `## ✓ Loud-Fail Markers —
    None` sentinel renders; no per-marker H3 entries are produced and
    therefore no actionable-pointer bullet is rendered for this
    fixture). When a future fixture seeds an enriched marker
    (`Tier-3-not-configured` / `playwright-mcp-unavailable` /
    `specialist-timeout`), the seeded `marker_contexts` field flows
    through to the bullet's interpolated text.
-->
# PR bundle — story sample-auto-001 (run run-2026-04-29-001)

Branch: bmad-automation/story/sample-auto-001
Final state: done
Generated: 2026-04-29T12:00:00+00:00

## ⚠️ Walking Skeleton Mode

All thickening features are present; this bundle is no longer a walking-skeleton. The Walking Skeleton Mode header section is retained for structural-historical continuity.

## ✓ Loud-Fail Markers — None

No loud-fail markers are active on this run.

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
