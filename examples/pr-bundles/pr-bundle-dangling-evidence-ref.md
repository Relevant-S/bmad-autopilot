<!--
Canonical example PR bundle fixture — generated at Story 6.6
(bundle-render-time evidence-trace linkability validation; NFR-O7 enforcement;
sub-classifications `qa-evidence` and `retry-history`).

Source story: bmad-autopilot/_bmad-output/implementation-artifacts/6-6-evidence-trace-linkability-runtime-dangling-evidence-ref-detection.md
Source envelopes (canonical corpus — unchanged at Story 6.6 because
6.6 adds the bundle-render-time evidence-linkability validator + an
additive sub_classifications enum extension on the existing
`dangling-evidence-ref` marker class without edits to the canonical
envelope corpus):
  - examples/envelopes/dev-pass.yaml                 (Story 1.2)
  - examples/envelopes/review-pass-three-layer.yaml  (Story 3.1)
  - examples/envelopes/qa-pass-ac1-tier1.yaml        (Story 2.10)
Assembler module: tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py
New substrate library: tools/loud-fail-harness/src/loud_fail_harness/evidence_linkability.py

This fixture is a regression baseline for Story 6.6's bundle-render-time
evidence-trace linkability validation. The seeded run-state thickens
`retry_history` with one entry pointing at a non-existent retry-round
artifact AND the QA envelope's `evidence_refs[0].path` points at a
non-existent file — BOTH sources dangle on the same run, exercising
AC-1 + AC-2 + AC-3's verbatim multi-source posture.

Story 6.6 generation deltas vs the post-6.5 fixture corpus:
  (i)   `## ⚠️ Loud-Fail Markers` block now carries TWO entries —
        `### dangling-evidence-ref: qa-evidence` AND
        `### dangling-evidence-ref: retry-history` — in alphabetical
        order per AC-3's "qa-evidence FIRST then retry-history"
        convention.
  (ii)  Each entry's `Sub-classification:` bullet shows the AC-3 sub-
        classification value verbatim (`qa-evidence` / `retry-history`)
        per Pattern 2's `: <cause>` suffix format ratified by Story 6.5
        for `cost-near-ceiling: ceiling-crossed`.
  (iii) The `## Per-AC results` body's evidence_refs bullet for AC-1's
        dangling path carries the inline `— ⚠️ dangling-evidence-ref:
        qa-evidence — Remediation: regenerate the evidence OR fix the
        reference (path=...)` suffix per AC-1's "rendered with an
        inline `⚠️ dangling-evidence-ref` marker indication at the
        reference location" verbatim.
  (iv)  No edit to `_render_loud_fail_block` was required — the existing
        `if ":" in marker_class:` split (review patch D1 from Story 6.5)
        handles sub-classified markers; Story 6.6's new sub-
        classifications go through the same path.
  (v)   No edit to `_render_cost_breakdown` was required — the
        degraded-render branch checks for `cost-telemetry-unavailable`
        prefix only; dangling-evidence markers are pass-through.
  (vi)  AssembleBundleResult.emitted_markers is unchanged — dangling-
        evidence markers flow via active_markers (the merged tuple),
        NOT via the assembler's own first-emission return field.

Visibility-not-enforcement posture: the bundle assembles successfully
despite both dangling refs. NFR-O7 says "or emits a dangling-ref loud-
fail marker" — it does NOT say "or the bundle fails to assemble." The
practitioner sees the markers in the loud-fail block AND the inline
indicators at the per-AC bullets and decides remediation per the loud-
fail-doctrine posture ratified across Epic 6 (6.4 graceful-degrade;
6.5 no-auto-halt; 6.6 visibility-not-enforcement).

Regenerate via:
  cd bmad-autopilot/tools/loud-fail-harness
  uv run pytest tests/test_evidence_linkability_smoke.py
  # then run the canonical-fixture regression test that compares
  # this file's body (modulo this header) byte-for-byte with the
  # assembler output.
-->
# PR bundle — story sample-auto-001 (run run-2026-04-29-001)

Branch: bmad-automation/story/sample-auto-001
Final state: done
Generated: 2026-04-29T12:00:00+00:00

## ⚠️ Walking Skeleton Mode

All thickening features are present; this bundle is no longer a walking-skeleton. The Walking Skeleton Mode header section is retained for structural-historical continuity.

## ⚠️ Loud-Fail Markers

### dangling-evidence-ref: qa-evidence

- Sub-classification: qa-evidence
- Diagnostic pointer: A PR bundle contains an evidence reference path that does not resolve to an on-disk artifact. Remediation: regenerate the evidence OR fix the reference. Distinct from `orphan-run-state-detected`: dangling-evidence is about evidence-file disappearance for a known story; orphan-run- state is about run-state for a deleted story-doc.
- How to enable: A PR bundle contains an evidence reference path that does not resolve to an on-disk artifact. Remediation: regenerate the evidence OR fix the reference. Distinct from `orphan-run-state-detected`: dangling-evidence is about evidence-file disappearance for a known story; orphan-run- state is about run-state for a deleted story-doc.

### dangling-evidence-ref: retry-history

- Sub-classification: retry-history
- Diagnostic pointer: A PR bundle contains an evidence reference path that does not resolve to an on-disk artifact. Remediation: regenerate the evidence OR fix the reference. Distinct from `orphan-run-state-detected`: dangling-evidence is about evidence-file disappearance for a known story; orphan-run- state is about run-state for a deleted story-doc.
- How to enable: A PR bundle contains an evidence reference path that does not resolve to an on-disk artifact. Remediation: regenerate the evidence OR fix the reference. Distinct from `orphan-run-state-detected`: dangling-evidence is about evidence-file disappearance for a known story; orphan-run- state is about run-state for a deleted story-doc.

## 💸 Cost Breakdown — None

No cost telemetry events have been recorded for this run.

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
- `_bmad-output/qa-evidence/sample-001/run-2026-04-29-001/ac1-http-200.log` — ⚠️ dangling-evidence-ref: qa-evidence — regenerate the evidence OR fix the reference (path='_bmad-output/qa-evidence/sample-001/run-2026-04-29-001/ac1-http-200.log')

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
