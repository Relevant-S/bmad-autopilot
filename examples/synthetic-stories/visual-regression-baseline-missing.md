---
expected_marker: visual-regression-baseline-missing
scenario: A web or mobile story ran with the visual-regression audit opted in (`qa-runbook.visual_regression.enabled` set to true), and for one AC the opt-in snapshot audit (screenshot captured via the existing Playwright MCP / mobile-mcp surface) found no prior stored baseline — so it created a new baseline from this run's screenshot and has nothing to compare against yet, surfacing the informational `visual-regression-baseline-missing` marker rather than silently treating a fresh anchor as a historical comparison.
---
# Synthetic story: visual-regression-baseline-missing

A web (or mobile) project story was dispatched with the Phase-2
visual-regression audit opted in (`qa-runbook.visual_regression.enabled: true`,
FR-P2-10 / ADR-012). For one acceptance criterion the QA wrapper captured the
current screenshot through the EXISTING MCP surface the project-type driver
already drives — `browser_take_screenshot` (web) via the Playwright MCP, or
`mobile_take_screenshot` (mobile) via mobile-mcp (no new MCP server — the diff
path composes with the driver the QA path already uses, per ADR-007).

On this AC there was **no prior stored baseline** for the audited surface
(`_bmad-output/qa-visual-baseline/{story-id}/{ac-id}/baseline.png` did not
exist), so the audit:

* created a new baseline from this run's screenshot, and
* has nothing to compare against yet,

then emitted the informational `visual-regression-baseline-missing` marker
carrying the `{ac_id}` context field. The marker is **not a failure**
(sensor-not-advisor): it records that this run anchored a fresh baseline.

It is **distinct from `visual-regression-delta-exceeded`** by remediation, not by
behavior: baseline-missing means regenerate/confirm, delta-exceeded means
investigate-change. The marker covers BOTH a genuine first run AND a subsequent
run whose baseline was deleted or relocated — the substrate cannot distinguish
them, so the operator reads the marker and decides whether the fresh anchor is
expected (if unexpectedly new, confirm the prior baseline was not lost before
trusting subsequent deltas).

This marker is a **QA-runtime evidence marker**, emitted by the Story 19.5 QA
wrapper — exactly as `a11y-baseline-stale` is wrapper-emitted, NOT declared on
the `pixelmatch` dependency profile. It is therefore an enumeration-check orphan
(tolerated). Story 19.5 is COMBINED: the class is enumerated in
`schemas/marker-taxonomy.yaml` AND emission lands in the same commit (no
flip-the-switch split).
