<!--
Canonical example PR bundle fixture — generated at Story 6.7
(orchestrator-side marker wiring for specialist-timeout / hook-failed /
context-near-limit; alphabetical render-time iteration per AC-4).

Source story: bmad-autopilot/_bmad-output/implementation-artifacts/6-7-specialist-timeout-hook-failed-context-near-limit-markers-fully-wired-into-pr-bundle.md
Source envelopes (canonical corpus — unchanged at Story 6.7 because
6.7 adds orchestrator-side recorder helpers + dispatch-boundary
composition seams + render-time alphabetical normalization without
edits to the canonical envelope corpus):
  - examples/envelopes/dev-pass.yaml                 (Story 1.2)
  - examples/envelopes/review-pass-three-layer.yaml  (Story 3.1)
  - examples/envelopes/qa-pass-ac1-tier1.yaml        (Story 2.10)
Assembler module: tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py
New substrate library: tools/loud-fail-harness/src/loud_fail_harness/marker_wiring.py

This fixture is a regression baseline for Story 6.7's orchestrator-side
marker wiring. The seeded run-state carries three Story 6.7 markers
recorded via the canonical recorders:

  * specialist-timeout: timeout-exceeded (recorded via
    record_specialist_timeout_marker for specialist=dev,
    timeout_seconds=900)
  * hook-failed: subagent-stop (recorded via
    record_hook_failure_marker for hook_name=subagent-stop)
  * context-near-limit: dev (recorded via
    record_context_near_limit_marker for specialist=dev)

The loud-fail block iterates the three markers in alphabetical order
per Story 6.7 AC-4 — context-near-limit FIRST → hook-failed SECOND →
specialist-timeout THIRD — independent of the emission order in the
persistent run_state.active_markers tuple (which preserves emission
order per Story 1.4's marker-permanence rule).

The bundle assembles successfully — visibility-not-enforcement per
the loud-fail doctrine ratified across Epic 6 (Stories 6.4 / 6.5 /
6.6 / 6.7).

Regression contract: this fixture must byte-match the post-Story-6.7
output of assemble_bundle for the seeded run-state. If the rendered
bundle diverges, regenerate via the Story 6.7 canonical-fixture test
in tests/test_marker_wiring_smoke.py.
-->
# PR bundle — story sample-marker-wiring-001 (run run-2026-05-06-marker-wiring)

Branch: bmad-automation/story/sample-marker-wiring-001
Final state: done
Generated: 2026-05-06T12:00:00+00:00

## ⚠️ Walking Skeleton Mode

All thickening features are present; this bundle is no longer a walking-skeleton. The Walking Skeleton Mode header section is retained for structural-historical continuity.

## ⚠️ Loud-Fail Markers

### context-near-limit: dev

- Sub-classification: dev
- Diagnostic pointer: Specialist {specialist}'s working context is approaching the model's context budget. Signals to the orchestrator that retry should be `fix-only` rather than `from-scratch`. Remediation options: split the AC, reduce input scope; see `docs/architecture.md` § Context-budget management. NOT a terminal failure — a degradation signal.
- How to enable: Specialist dev's working context is approaching the model's context budget. Signals to the orchestrator that retry should be `fix-only` rather than `from-scratch`. Remediation options: split the AC, reduce input scope; see `docs/architecture.md` § Context-budget management. NOT a terminal failure — a degradation signal.

### hook-failed: subagent-stop

- Sub-classification: subagent-stop
- Diagnostic pointer: A hook's exit code is non-zero. Distinct from `bundle-assembly-failed` (assembler-logic remediation) and `scope-assertion-violation` (Dev-diff- vs-scope remediation): `hook-failed` remediates against the bash script's environment. See `sub_classifications` for the canonical hook-name suffix (`session-start`, `stop`, `subagent-stop`) emitted at runtime per Story 6.7's wiring; the failure-mode suffixes (`non-zero-exit`, `timeout`, `missing-binary`) document underlying causes a future Phase 2 thickening MAY emit as compound suffixes.
- How to enable: A hook's exit code is non-zero. Distinct from `bundle-assembly-failed` (assembler-logic remediation) and `scope-assertion-violation` (Dev-diff- vs-scope remediation): `hook-failed` remediates against the bash script's environment. See `sub_classifications` for the canonical hook-name suffix (`session-start`, `stop`, `subagent-stop`) emitted at runtime per Story 6.7's wiring; the failure-mode suffixes (`non-zero-exit`, `timeout`, `missing-binary`) document underlying causes a future Phase 2 thickening MAY emit as compound suffixes.

### specialist-timeout: timeout-exceeded

- Sub-classification: timeout-exceeded
- Diagnostic pointer: Specialist {specialist} exceeded the orchestrator's per-specialist timeout budget ({timeout_seconds}s). Envelope is treated as failed; remediation targets the specialist's prompt or evidence size. See `sub_classifications` for the specific timeout cause (`timeout-exceeded` vs. `context-budget-exceeded`).
- How to enable: Specialist dev exceeded the orchestrator's per-specialist timeout budget (900s). Envelope is treated as failed; remediation targets the specialist's prompt or evidence size. See `sub_classifications` for the specific timeout cause (`timeout-exceeded` vs. `context-budget-exceeded`).

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
