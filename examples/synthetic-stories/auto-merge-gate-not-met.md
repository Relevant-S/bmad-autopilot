---
expected_marker: auto-merge-gate-not-met
scenario: At Stop-hook time (per-story scope) the auto-merge gate-condition evaluator read the resolved `auto_merge.gate_conditions` (Story 17.1) and the maintainer-curated `_bmad-output/metrics/adoption-metrics.yaml`, computed pass/fail per configured gate, and found at least one gate unmet (e.g. `min_adoption_months` requires `>= 6` but the reference `adoption_months` is `3`). The evaluator surfaced the INFORMATIONAL `auto-merge-gate-not-met` marker (FR-P2-3) with a `diagnostic_pointer` naming each failing gate, its current value, and the required threshold — WITHOUT merging, advancing state, or flipping any wrapper status (sensor-not-advisor; the merge decision is Story 17.3).
---
# Synthetic story: auto-merge-gate-not-met

On this Stop-hook invocation the per-story bundle-assembly substrate ran the
Epic 17 auto-merge gate-condition evaluator (Story 17.2 / FR-P2-3). The
evaluator resolved the `auto_merge` block from `_bmad/automation/config.yaml`
into an `AutoMergeConfig` (Story 17.1, consumed read-only) and — because the
gate conditions were configured (at least one of `min_adoption_months` /
`min_completion_fidelity` / `max_retry_exhaustion` non-blank) — read the
maintainer-curated reference-project metrics from
`_bmad-output/metrics/adoption-metrics.yaml`.

It computed pass/fail per configured gate: `min_adoption_months` passes iff
`adoption_months >= threshold`; `min_completion_fidelity` passes iff
`completion_fidelity >= threshold`; `max_retry_exhaustion` passes iff
`retry_exhaustion <= threshold` (the inverted direction — it is a ceiling). At
least one configured gate was **unmet**, so the evaluator returned a
`gate-not-met` decision and the substrate surfaced `auto-merge-gate-not-met`,
carrying a `diagnostic_pointer` that names each failing gate, its current
reference value, and the required threshold (`failing_gates` is the
`pointer_context_fields` entry).

The evaluator runs at **every** Stop-hook invocation regardless of
`auto_merge.enabled` (continuous observability, the NFR-O8 precedent), so a
maintainer can see whether the gate would block **before** flipping
`enabled: true`. When the gate conditions are blank/TBD — the shipped default —
the evaluator returns `not-configured` and emits **nothing** (no per-run noise
on default installs); the metrics file is not even read.

The marker is **INFORMATIONAL** (sensor-not-advisor, mirroring
`flakiness-threshold-exceeded` / `sprint-escalation-rate-exceeded`): emitting it
does NOT flip a wrapper status, does NOT change `current_state`, and does NOT
itself merge or block. Auto-merge is **gated by data, not by intention** — and
the merge logic plus the `auto-merge-skipped` signal are deferred to Story 17.3.
This is an **orchestrator-domain runtime observability marker** (orphan,
tolerated by enumeration-check), emitted by
`auto_merge_gate.surface_auto_merge_gate_not_met` and rendered into the
per-story PR bundle by `bundle_assembly`.
