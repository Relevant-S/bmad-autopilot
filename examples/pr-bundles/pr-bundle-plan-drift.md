<!--
Canonical example PR bundle fixture — Story 4.2 (AC-hash plan-drift
detection + plan_status reset).

Source story: bmad-autopilot/_bmad-output/implementation-artifacts/4-2-ac-hash-plan-drift-detection-plan-status-reset.md
Source envelopes (post-4.2 canonical corpus):
  - examples/envelopes/dev-pass.yaml                       (Story 1.2)
  - examples/envelopes/review-pass-three-layer.yaml        (Story 3.1)
  - examples/envelopes/qa-pass-with-plan-drift.yaml        (Story 4.2)
Assembler module: tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py

This fixture is a regression baseline. Subsequent epics (4 / 5 / 6)
regenerate this fixture in place when bundle rendering thickens —
review the diff before committing the regenerated fixture.

Story 4.2 surface exercised: the QA envelope's `plan_drift` field is
non-null, so the assembler renders an `### Plan drift detected` H3
sub-section under `## Per-AC results` carrying the four-field
diagnostic context plus the structured `plan-drift-detected` marker
comment co-located. The Story 3.4 `walking-skeleton-bundle` marker
continues to emit at the bundle's bottom because Epic 6 / Story 6.1's
loud-fail-block landing has not flipped `is_loud_fail_block_present`
yet.
-->
# PR bundle — story sample-auto-001 (run run-2026-04-30-001)

Branch: bmad-automation/story/sample-auto-001
Final state: done
Generated: 2026-04-30T12:00:00+00:00

## ⚠️ Walking Skeleton Mode

This PR bundle is a walking-skeleton — it enumerates the structural shape of the BMAD automation loop while the following thickenings remain unfinished:

- Tier-1 evidence only (Epic 4 thickens to Tier-2 + Tier-3-where-configured).
- No retry (Epic 5 thickens with whole-story retry budget + bucket-driven action item derivation).
- No loud-fail block (Epic 6 thickens with the dedicated top-of-bundle loud-fail block + per-specialist × per-retry cost breakdown + actionable how-to-enable pointers).

## Per-AC results

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


<!-- bmad-automation:marker walking-skeleton-bundle -->
