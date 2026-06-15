<!--
Canonical example PR bundle fixture — Story 6.5 (in-flight cost streaming +
cost-near-ceiling 75% threshold; specialist boundary cadence).
75%-crossing variant: `cost-near-ceiling` active marker surfaced in the
loud-fail block per Story 6.1's `_render_loud_fail_block`; cost-breakdown
section from Story 6.4 renders the per-(specialist × retry) table with
running totals approaching the $5 ceiling. Loop did not auto-halt
per NFR-O8 — bundle assembled successfully.

Source story: bmad-autopilot/_bmad-output/implementation-artifacts/6-5-in-flight-cost-streaming-cost-near-ceiling-75-threshold-specialist-boundary-cadence.md
Source envelopes (canonical corpus — unchanged at Story 6.5):
  - examples/envelopes/dev-pass.yaml                 (Story 1.2)
  - examples/envelopes/review-pass-three-layer.yaml  (Story 3.1)
  - examples/envelopes/qa-pass-ac1-tier1.yaml        (Story 4.6)
Active markers: ('cost-near-ceiling',) — running total $4.00 = 80% of $5 ceiling
Cost-to-date: dev=$2.60, review_bmad=$1.40
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

## 💸 Cost Breakdown

| Specialist | Retry attempt | Cost delta (USD) | Per-specialist running total (USD) |
| --- | --- | --- | --- |
| dev | 1 | 1.20 | 1.20 |
| dev | 2 | 1.40 | 2.60 |
| dev | total | — | 2.60 |
| review-bmad | 1 | 0.80 | 0.80 |
| review-bmad | 2 | 0.60 | 1.40 |
| review-bmad | total | — | 1.40 |

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
