<!--
Canonical example PR bundle fixture — Story 4.2 (AC-hash plan-drift
detection + plan_status reset); regenerated at Story 6.1 (loud-fail
block + structural-derivation flag flip; Epic 6 OPEN; the in-place-
flip cohort closes — FOUR flags True (`is_full_review_present` since
Story 3.4; `is_full_qa_present` since Story 4.13; `is_retry_present`
since Story 5.9; `is_loud_fail_block_present` since Story 6.1 —
flipped via *structural derivation* per AC-2's drift-prevention
contract-pair contract).

Source story: bmad-autopilot/_bmad-output/implementation-artifacts/4-2-ac-hash-plan-drift-detection-plan-status-reset.md
Story 6.1 regeneration source: bmad-autopilot/_bmad-output/implementation-artifacts/6-1-loud-fail-block-pr-bundle-structure-computed-flag-marker-emission-inversion.md
Source envelopes (canonical corpus — unchanged at Story 6.1):
  - examples/envelopes/dev-pass.yaml                       (Story 1.2)
  - examples/envelopes/review-pass-three-layer.yaml        (Story 3.1)
  - examples/envelopes/qa-pass-with-plan-drift.yaml        (Story 4.2)
Assembler module: tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py

This fixture is a regression baseline. The pre-Epic-6 snapshot is
preserved at `pre-epic-6-snapshot.md` (Story 6.1 AC-4 + Story 1.4
permanence rule). Subsequent epics regenerate THIS fixture in place
when bundle rendering thickens; the snapshot is NEVER touched.

Story 4.2 surface exercised: the QA envelope's `plan_drift` field is
non-null, so the assembler renders an `### Plan drift detected` H3
sub-section under `## Per-AC results` carrying the four-field
diagnostic context plus the structured `plan-drift-detected` marker
comment co-located.

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
  (iv)  The `plan-drift-detected` marker comment continues to emit
        co-located with the `### Plan drift detected` H3 sub-section
        (Story 4.2's surface is unaffected by 6.1's flag flip).

Story 6.2 update (FR31 actionable-pointer enrichment):
  - The per-marker `- How to enable:` bullet's content is now the
    interpolated `diagnostic_pointer` text from `marker-taxonomy.yaml`
    (un-interpolated for context-free markers like
    `plan-drift-detected`, which has `pointer_context_fields: []`)
    instead of the literal `_HOW_TO_ENABLE_PLACEHOLDER` string Story
    6.1 emitted at the same structural position.
  - Fixture body is unchanged at this story's landing because
    `active_markers` is empty here (the `## ✓ Loud-Fail Markers —
    None` sentinel renders; the `plan-drift-detected` indicator
    surfaces via the inline `bmad-automation:marker plan-drift-detected`
    HTML comment in `## Per-AC results`, not the loud-fail block).

Story 6.4 update (per-specialist × per-retry cost telemetry):
  - New `## 💸 Cost Breakdown — None` H2 block rendered as the SECOND
    content section, immediately after the loud-fail block and BEFORE
    `## Per-AC results` per AC-3's structural-position contract. The
    plan-drift fixture seeds zero cost-events (no `otel_pipeline`
    injected at the assembler call site) so the empty-aggregation
    sentinel renders.
-->
# PR bundle — story sample-auto-001 (run run-2026-04-30-001)

Branch: bmad-automation/story/sample-auto-001
Final state: done
Generated: 2026-04-30T12:00:00+00:00

## ⚠️ Walking Skeleton Mode

All thickening features are present; this bundle is no longer a walking-skeleton. The Walking Skeleton Mode header section is retained for structural-historical continuity.

## ✓ Loud-Fail Markers — None

No loud-fail markers are active on this run.

## 💸 Cost Breakdown — None

No cost telemetry events have been recorded for this run.

## Per-AC results

> **Plan-persistence compromise note (FR25):**
>
> This plan is persisted across runs for resumability.
> Persistence is a known compromise: full QA independence would re-derive the plan every run.
> See `docs/extension-audit.md` and FR-P2-9 (Story 20.1, LANDED — accompanies this note with per-run plan re-derivation cross-check).

### AC-1 — status: `pass`

**Assertions:**
- HTTP POST /healthz returned status code 200

**Evidence:**
- `_bmad-output/qa-evidence/sample-001/run-2026-04-30-001/ac1-http-200.log`

**Semantic verification:** `not_applicable`

### Plan drift detected

<!-- bmad-automation:marker plan-drift-detected -->

- Story ID: `sample-auto-001`
- Prior plan_status: `human-reviewed`
- Prior ac_hash: `0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef`
- Current ac_hash: `fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210`

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
