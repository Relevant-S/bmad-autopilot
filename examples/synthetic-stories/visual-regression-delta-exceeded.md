---
expected_marker: visual-regression-delta-exceeded
scenario: A web or mobile story ran with the visual-regression audit opted in (`qa-runbook.visual_regression.enabled` set to true); for one AC the opt-in snapshot audit captured the current screenshot via the existing Playwright MCP (`browser_take_screenshot`) / mobile-mcp (`mobile_take_screenshot`) surface, ran pixelmatch over the saved baseline + current PNGs, and found that the Automator's self-computed mismatched-pixel ratio exceeded the configurable visual delta threshold — surfacing `visual-regression-delta-exceeded` as evidence for the practitioner to triage.
---
# Synthetic story: visual-regression-delta-exceeded

A web (or mobile) project story was dispatched with the Phase-2 visual-regression
audit opted in (`qa-runbook.visual_regression.enabled: true`, FR-P2-10 /
ADR-012). For one acceptance criterion the QA wrapper captured the current
screenshot through the EXISTING MCP surface the project-type driver already
drives — `browser_take_screenshot` (web) via the Playwright MCP, or
`mobile_take_screenshot` (mobile) via mobile-mcp — and ran pixelmatch over the
two saved PNG files (the stored baseline + this run's capture). NO new MCP
server: the diff composes with the existing driver, per ADR-007 / ADR-012.

Because pixelmatch ships **no baseline lifecycle** (it returns only a raw
mismatched-pixel count for one comparison), the Automator computed the delta
itself: the mismatched-pixel ratio `mismatched_pixels / total_pixels`. The ratio
**exceeded the configurable visual delta threshold**
(`qa-runbook.visual_regression.delta_threshold`), so the QA wrapper emitted
`visual-regression-delta-exceeded` with the `{ac_id}` context field, and the
diagnostic pointed at the diff evidence artifact (the diff PNG + the
ratio/counts/dimensions). The dimension-mismatch edge folds here too: a changed
render size — where the baseline and current dimensions differ, so pixelmatch
cannot run over unequal dimensions — IS a visual regression, recorded with the
dimension change in the same artifact (the strictest defensible interpretation;
no third `-mode-unstable` marker, because pixel-diff over equal-dimension PNGs is
deterministic).

The marker reports a regression the **Automator measured**, not a pixelmatch
verdict. It is surfaced as evidence — the substrate does NOT auto-resolve or fail
the AC (sensor-not-advisor + visibility-over-enforcement); the human triages the
changed region and either fixes the regression or re-anchors the baseline
intentionally (manual-delete only — there is no `force_reanchor` field).

This is a **QA-runtime evidence marker** emitted by the Story 19.5 QA wrapper
(orphan, tolerated by enumeration-check). Unlike a11y (19.3 enumerate → 19.4
emit), Story 19.5 is a COMBINED activation+integration story: the class is
enumerated AND emission lands in the same commit (no flip-the-switch split).
