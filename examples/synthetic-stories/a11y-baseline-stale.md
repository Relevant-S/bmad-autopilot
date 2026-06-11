---
expected_marker: a11y-baseline-stale
scenario: A web story ran with the a11y audit opted in (`qa-runbook.a11y.enabled` set to true), and for one AC the opt-in accessibility audit (axe-core injected in-page via the existing Playwright MCP browser surface) found no prior stored baseline — so it created a new baseline and anchored this run's self-computed violation delta against it, surfacing the informational `a11y-baseline-stale` marker rather than silently treating a fresh anchor as a historical comparison.
---
# Synthetic story: a11y-baseline-stale

A web project story was dispatched with the Phase-2 accessibility audit opted
in (`qa-runbook.a11y.enabled: true`, FR-P2-6 / ADR-011). For one acceptance
criterion the QA wrapper injected axe-core's `axe.min.js` into the
Playwright-MCP-driven page and called `axe.run()`, reading back the
deterministic `violations[]` result (no new MCP server — the engine composes
with the browser surface the web QA path already drives, per ADR-007).

The audit ships **delta-enabled**: the Automator self-computes the
baseline-delta over axe-core's stable `violations[]` JSON (axe-core has no
native baseline-delta). On this AC there was **no prior stored baseline** for
the audited surface, so the audit:

* created a new baseline from this run's `violations[]`, and
* anchored the run's delta against that freshly-created baseline,

then emitted the informational `a11y-baseline-stale` marker carrying the
`{ac_id}` context field. The marker is **not a failure** (sensor-not-advisor):
it records that the delta this run reports is measured against a new anchor, so
a downstream `a11y-delta-exceeded` on the same run would be measured against
this baseline rather than a historical one.

This marker is a **QA-runtime evidence marker**, emitted by the Story 19.4 QA
wrapper — exactly as `LAD-skipped` is wrapper-emitted, NOT declared on the
`axe-core` dependency profile. It is therefore an enumeration-check orphan
(tolerated). At Story 19.3 the class is enumerated in
`schemas/marker-taxonomy.yaml` only; the runtime emission path and the
baseline-storage location land in Story 19.4 (the flip-the-switch property).
