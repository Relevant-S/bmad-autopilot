---
expected_marker: a11y-delta-exceeded
scenario: A web story ran with the a11y audit opted in (`qa-runbook.a11y.enabled` set to true); for one AC the opt-in accessibility audit (axe-core via the existing Playwright MCP browser surface) found that the Automator's self-computed violation delta versus the stored baseline — a set-difference on axe-core `violations[]` keys — exceeded the configurable a11y delta threshold, surfacing `a11y-delta-exceeded` as evidence for the practitioner to triage.
---
# Synthetic story: a11y-delta-exceeded

A web project story was dispatched with the Phase-2 accessibility audit opted
in (`qa-runbook.a11y.enabled: true`, FR-P2-6 / ADR-011). For one acceptance
criterion the QA wrapper injected axe-core's `axe.min.js` into the
Playwright-MCP-driven page, ran `axe.run()`, and obtained the deterministic
`violations[]` result.

Because axe-core ships **no native baseline-delta**, the Automator computed the
delta itself: a set-difference on `(rule-id, target-selector, …)` violation
keys between the stored baseline and this run. The number of newly-introduced
violations **exceeded the configurable a11y delta threshold**, so the QA wrapper
emitted `a11y-delta-exceeded` with the `{ac_id}` context field, and the
diagnostic pointed at the delta evidence artifact.

The marker reports a regression the **Automator measured**, not an axe-core
verdict (the maturity is split: axe-core's output is mature/diffable; the delta
is ours to compute). It is surfaced as evidence — the substrate does NOT
auto-resolve or fail the AC (sensor-not-advisor + visibility-over-enforcement);
the human triages the new violations against the baseline and either fixes the
regression or re-anchors the baseline intentionally.

This is a **QA-runtime evidence marker** emitted by the Story 19.4 QA wrapper
(orphan, tolerated by enumeration-check). Story 19.3 enumerates the class only;
the delta evidence artifact, the threshold config surface, and the runtime
emission land in Story 19.4 (the flip-the-switch property).
