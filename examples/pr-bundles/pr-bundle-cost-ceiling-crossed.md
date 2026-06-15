<!--
Canonical example PR bundle fixture — Story 6.5 (in-flight cost streaming +
cost-near-ceiling 75% threshold; specialist boundary cadence).
100%-crossing variant: BOTH `cost-near-ceiling` AND
`cost-near-ceiling: ceiling-crossed` active markers surfaced in the loud-fail
block per Story 6.1's `_render_loud_fail_block`; cost-breakdown section from
Story 6.4 renders the per-(specialist × retry) table with running totals
exceeding the $5 ceiling. Loop did not auto-halt per NFR-O8 verbatim —
the practitioner decides whether to abort. Bundle assembled successfully.

Source story: bmad-autopilot/_bmad-output/implementation-artifacts/6-5-in-flight-cost-streaming-cost-near-ceiling-75-threshold-specialist-boundary-cadence.md
Source envelopes (canonical corpus — unchanged at Story 6.5):
  - examples/envelopes/dev-pass.yaml                 (Story 1.2)
  - examples/envelopes/review-pass-three-layer.yaml  (Story 3.1)
  - examples/envelopes/qa-pass-ac1-tier1.yaml        (Story 4.6)
Active markers: ('cost-near-ceiling', 'cost-near-ceiling: ceiling-crossed')
Running total: $5.50 = 110% of $5 ceiling
Cost-to-date: dev=$3.50, review_bmad=$2.00
-->
# PR bundle — story sample-cost-near-ceiling-001 (run run-2026-05-06-cost-near-ceiling)

Branch: bmad-automation/story/sample-cost-near-ceiling-001
Final state: done
Generated: 2026-05-06T12:00:00+00:00

## ⚠️ Walking Skeleton Mode

All thickening features are present; this bundle is no longer a walking-skeleton. The Walking Skeleton Mode header section is retained for structural-historical continuity.

## ⚠️ Loud-Fail Markers

### cost-near-ceiling

- Sub-classification: none
- Diagnostic pointer: In-flight cost-telemetry shows a story-run is approaching its cost budget (default: 75% of ceiling per Epic 6 specialist boundary cadence). Signal to the practitioner before the budget exhausts; loop continues. Remediation: monitor or interrupt before exhaustion.
- How to enable: In-flight cost-telemetry shows a story-run is approaching its cost budget (default: 75% of ceiling per Epic 6 specialist boundary cadence). Signal to the practitioner before the budget exhausts; loop continues. Remediation: monitor or interrupt before exhaustion.

### cost-near-ceiling: ceiling-crossed

- Sub-classification: ceiling-crossed
- Diagnostic pointer: In-flight cost-telemetry shows a story-run is approaching its cost budget (default: 75% of ceiling per Epic 6 specialist boundary cadence). Signal to the practitioner before the budget exhausts; loop continues. Remediation: monitor or interrupt before exhaustion.
- How to enable: In-flight cost-telemetry shows a story-run is approaching its cost budget (default: 75% of ceiling per Epic 6 specialist boundary cadence). Signal to the practitioner before the budget exhausts; loop continues. Remediation: monitor or interrupt before exhaustion.

## 💸 Cost Breakdown

| Specialist | Retry attempt | Cost delta (USD) | Per-specialist running total (USD) |
| --- | --- | --- | --- |
| dev | 1 | 1.50 | 1.50 |
| dev | 2 | 2.00 | 3.50 |
| dev | total | — | 3.50 |
| review-bmad | 1 | 1.00 | 1.00 |
| review-bmad | 2 | 1.00 | 2.00 |
| review-bmad | total | — | 2.00 |

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
