---
expected_marker: a11y-delta-mode-unstable
scenario: A web story ran with the a11y audit opted in (`qa-runbook.a11y.enabled` set to true); for one AC the opt-in accessibility audit (axe-core via the existing Playwright MCP browser surface) could not produce its self-computed baseline-delta reliably, so it fell back to full-report mode (no delta) and surfaced `a11y-delta-mode-unstable` — the loud-fail escape valve named in ADR-011 — rather than silently shipping a possibly-wrong regression diff.
---
# Synthetic story: a11y-delta-mode-unstable

A web project story was dispatched with the Phase-2 accessibility audit opted
in (`qa-runbook.a11y.enabled: true`, FR-P2-6 / ADR-011). For one acceptance
criterion the QA wrapper injected axe-core's `axe.min.js` into the
Playwright-MCP-driven page and captured the `violations[]` report.

The audit ships delta-enabled, with the Automator computing the baseline-delta
over axe-core's `violations[]` JSON. On this run the self-computed delta could
**not be produced reliably** (the Automator-side set-difference proved
non-deterministic — the delta is the Automator's to get right, not axe-core's).
Rather than ship a possibly-wrong regression verdict, the audit fell back to
**full-report mode (no delta)** and emitted `a11y-delta-mode-unstable`.

This is the **loud-fail escape valve** ADR-011 names: the full axe-core
violation report is still captured as evidence; only the delta layer is
withheld, and the unstable-delta condition is surfaced rather than silently
swallowing a bad diff. The marker is **not a failure of the audit itself**
(sensor-not-advisor); it carries no context fields. If the unstable delta
recurs across Phase-2 reference runs, ADR-011's revisit condition fires (make
full-report the default).

This is a **QA-runtime evidence marker** emitted by the Story 19.4 QA wrapper
(orphan, tolerated by enumeration-check). Story 19.3 enumerates the class only;
the runtime emission and the full-report-no-delta path land in Story 19.4 (the
flip-the-switch property).
