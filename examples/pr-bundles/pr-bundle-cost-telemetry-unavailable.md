<!--
Canonical example PR bundle fixture — Story 6.4 (per-specialist × per-retry
cost telemetry collection, boundary-driven OTel pipeline; ADR-006 Combo 3).
Graceful-degrade variant: `cost-telemetry-unavailable: otel-pipeline-unreachable`
active marker triggers the marker-rendered cost-breakdown variant per AC-2.
NO fabricated zeros, NO silently-omitted section.

Source story: bmad-autopilot/_bmad-output/implementation-artifacts/6-4-per-specialist-per-retry-cost-telemetry-collection-boundary-driven-otel-pipeline.md
Source envelopes (canonical corpus — unchanged at Story 6.4):
  - examples/envelopes/dev-pass.yaml                 (Story 1.2)
  - examples/envelopes/review-pass-three-layer.yaml  (Story 3.1)
  - examples/envelopes/qa-pass-ac1-tier1.yaml        (Story 2.10)
Source run-state: active_markers=("cost-telemetry-unavailable: otel-pipeline-unreachable",)
Assembler module: tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py
Cost-telemetry substrate: tools/loud-fail-harness/src/loud_fail_harness/cost_telemetry.py
Marker-taxonomy entry: schemas/marker-taxonomy.yaml lines 303-312

The fixture is regenerated when the assembler's cost-breakdown rendering
intentionally changes; the canonical-fixture regression test
`test_canonical_cost_telemetry_unavailable_bundle_fixture_matches_assembler_output`
guards against accidental drift.
-->
# PR bundle — story sample-cost-telemetry-001 (run run-2026-05-06-cost)

Branch: bmad-automation/story/sample-cost-telemetry-001
Final state: done
Generated: 2026-05-06T12:00:00+00:00

## ⚠️ Walking Skeleton Mode

All thickening features are present; this bundle is no longer a walking-skeleton. The Walking Skeleton Mode header section is retained for structural-historical continuity.

## ⚠️ Loud-Fail Markers

### cost-telemetry-unavailable: otel-pipeline-unreachable

- Sub-classification: otel-pipeline-unreachable
- Diagnostic pointer: ADR-006 (OTel cost-event pipeline) + NFR-P5 (per-retry cost observability). Graceful-degrade behavior when OTel pipeline fails: cost data unavailable for the run; loop continues; bundle's cost-breakdown section shows the marker rather than fabricated zeros.
- How to enable: ADR-006 (OTel cost-event pipeline) + NFR-P5 (per-retry cost observability). Graceful-degrade behavior when OTel pipeline fails: cost data unavailable for the run; loop continues; bundle's cost-breakdown section shows the marker rather than fabricated zeros.

## ⚠️ Cost Breakdown — Telemetry Unavailable

ADR-006 (OTel cost-event pipeline) + NFR-P5 (per-retry cost observability). Graceful-degrade behavior when OTel pipeline fails: cost data unavailable for the run; loop continues; bundle's cost-breakdown section shows the marker rather than fabricated zeros.

Sub-classification: otel-pipeline-unreachable

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
