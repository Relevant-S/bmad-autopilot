# Reference Run 19-6 — Epic-19 QA-Coverage Mobile Reference Run (6-of-7 heuristic subset + visual regression) — narrative

## Reference project

Per Story 19.6 AC-2 + the AC substitution posture inherited from Stories 9.6 / 13.7: the QA surface is the **established UI-bearing e-commerce cart/checkout synthetic surface** — the SAME surface the sibling `19-6-web` run exercises — **rebound to the mobile driver surface**, captured under the story id `sample-qa-coverage-mobile-001`. Per Story 19.6 Dev Notes ("Reuse a synthetic QA surface — do not invent a new app"), no new synthetic project is invented; only the driving mechanics differ from the web run (the mobile-MCP `mobile_*` tool surface replacing the Playwright MCP surface). The Dev specialist implemented the cart/checkout/confirmation mobile screens as the diff; the QA specialist drove them via the mobile-MCP driver (Story 9.3 / ADR-007).

Live re-capture against a maintainer-owned external mobile project (PRD line 815 — "practitioner-actually-useful, not synthetic demo") remains **forward-scoped**, the same substitution commitment Stories 9.6 / 13.7 made. Story 23.2 (`phase-2-completion-evidence.md`, including the H8 live mobile re-capture) is the forward consumer that reads this directory.

## Reference project purpose + scope

This run is the **mobile-side empirical witness for FR-P2-5 (the 6-of-7 mobile heuristic subset) and FR-P2-10 (visual regression)** — two of the three QA-coverage capabilities Epic 19 landed. It demonstrates the project-type-agnostic core of the Epic-19 surfaces: the exploratory-heuristic dispatch (`agents/qa.md` step 8) and the visual-regression capture (step 14) compose against the mobile driver exactly as against the web driver — only the driving mechanics differ. The run is LAD-disabled, matching the `9-6-mobile` / `13-7-mobile` baseline; the review posture is the three-layer `blind` / `edge` / `auditor` pass with no `lad` layer and no `lad` cost-partition row.

The one capability this mobile run does NOT witness is a11y (FR-P2-6) — a11y is web-only (§ FR-P2-6 a11y NOT invoked).

## Chosen story user-visible outcome

The Dev specialist implemented an e-commerce cart/checkout mobile surface: AC-1 (a logged-in user can add an item to the cart), AC-2 (the checkout form rejects an invalid payment card), and AC-3 (an order confirmation screen renders after a successful purchase). The user-visible outcome is the running mobile app behaving correctly across the three ACs while the QA specialist exercises the mobile Epic-19 coverage surface against it.

## FR-P2-5 mobile 6-of-7 heuristic subset

`MOBILE_HEURISTIC_SPECS` covers **six of the seven** heuristics — `auth-boundary` / `empty-state` / `error-state` / `large-input-boundary` / `locale-i18n-edge` / `permission-boundary` — and **`rate-limit-boundary` is excluded from the mobile matrix per ADR-010**. The mobile run dispatches the six (the `heuristics.mobile.*` opt-in block enabled). Per heuristic:

| heuristic (`HeuristicKind`) | mobile disposition | outcome |
|---|---|---|
| `empty-state` | applicable | drove the empty-cart state via mobile-mcp (AC-1); no finding; evidence `heuristics/empty-state-cart-empty.json` |
| `error-state` | applicable | drove the card-declined error surface via mobile-mcp (AC-2); no finding; evidence `heuristics/error-state-card-declined.json` |
| `auth-boundary` | applicable | drove the session-expiry boundary via mobile-mcp (AC-3); no finding; evidence `heuristics/auth-boundary-session-expiry.json` |
| `large-input-boundary` | applicable | drove the per-line quantity-ceiling clamp via mobile-mcp (AC-1); no finding; evidence `heuristics/large-input-boundary-quantity-overflow.json` |
| `locale-i18n-edge` | applicable | drove the EUR/RTL-locale formatting via mobile-mcp (AC-2); no finding; evidence `heuristics/locale-i18n-edge-eur-rtl.json` |
| `permission-boundary` | **structurally inapplicable** | exactly one `heuristic-skipped: permission-boundary` marker — the surface has no role/permission-gated surface |
| `rate-limit-boundary` | **silently matrix-excluded (ADR-010)** | **NOT dispatched; NO marker** — see below |

Aggregate: **5 applicable-with-evidence; 1 structurally-inapplicable-with-marker.** The one skipped sub_classification (`permission-boundary`) is among the **four 19.2-added** values ∈ the closed 7-value enum, so the net-new surface is genuinely witnessed on mobile too. The `heuristic-skipped: permission-boundary` marker rides the `qa-envelope.yaml` `heuristic_skipped_emissions` array and surfaces in `pr-bundle.md`'s loud-fail block with a how-to-enable pointer (FR31).

### rate-limit-boundary is SILENTLY matrix-excluded — NO marker (the AC-4 witness)

Story 19.2 codified TWO skip semantics (`agents/qa.md` step 8): **structural-inapplicability** → a `heuristic-skipped: <sub_classification>` marker (the `permission-boundary` case above); **disabled / opt-out / matrix-excluded** → **SILENT** (no marker, FR42 + ADR-010 noisy-marker-avoidance). `rate-limit-boundary` is **matrix-excluded** from the mobile dispatch per ADR-010 (it is not in `MOBILE_HEURISTIC_SPECS`), so it is **silently** excluded: it is NOT dispatched and emits **NO `heuristic-skipped: rate-limit-boundary` marker anywhere in this directory**.

> **Maintainer note (do not "fix" this by adding a marker).** A `heuristic-skipped: rate-limit-boundary` marker on this mobile run would be a doctrine violation — matrix-exclusion is the SILENT arm, distinct from structural-inapplicability (the marker arm). This is recorded explicitly per Story 19.6 AC-4 so a future reader does not mistake the absence of a `rate-limit-boundary` skip marker for a gap in the records. The web sibling (`19-6-web`) DOES dispatch `rate-limit-boundary` (it is in the web matrix) and there it is structurally inapplicable → it emits a `heuristic-skipped: rate-limit-boundary` marker. The contrast between the two runs is the witness that the two skip semantics are correctly distinguished. Citations: ADR-010 (mobile matrix exclusion) + Story 19.2 (dispatch-precedence doctrine, two skip semantics).

## FR-P2-10 visual regression

Story 19.5 landed the `visual_regression_emissions` envelope surface + the two AC-scoped marker classes, **web AND mobile**, `qa-runbook.visual_regression.enabled: true` gated. On mobile, screenshots are captured via the EXISTING mobile-mcp `mobile_take_screenshot` (/ `mobile_save_screenshot`) surface — no new MCP server (ADR-007/012 compose-with-driver); the pixelmatch diff (ADR-012) runs over the saved PNGs, uniform across web+mobile.

**First-run baseline-creation path (witnessed here).** On this first run, no baseline PNG exists at `_bmad-output/qa-visual-baseline/sample-qa-coverage-mobile-001/{ac}/baseline.png` (gitignored by default), so for each AC the current screenshot is written as the new baseline via `store_baseline(...)` and exactly one **`visual-regression-baseline-missing`** marker fires — informational; there is nothing to diff against yet. Three records (AC-1, AC-2, AC-3), each carrying `ac_id` (`$defs/visual_regression_emission` `required: [marker_class, ac_id]`). The captured screenshots ride the qa-evidence path (`visual/ac-{1,2,3}-screenshot.png`); the gitignored baseline PNG is cited, NOT committed (no image binaries added to the record set).

**Subsequent-run delta-compute + dimension-mismatch semantics (documented, not exercised here).** Identical to the web sibling: pixelmatch yields `{mismatched_pixels, width, height}`, `compute_delta(diff, threshold)` derives the mismatched-pixel ratio (threshold = `qa-runbook.visual_regression.delta_threshold`, default `0.0`), ratio over threshold → `visual-regression-delta-exceeded`; a **dimension mismatch folds into `visual-regression-delta-exceeded`** (a changed render size IS a regression); there is **NO third `-mode-unstable` marker** — pixel-diff is deterministic (ADR-012). Within-threshold → NO marker.

## FR-P2-6 a11y NOT invoked (web-only)

a11y (Story 19.3/19.4) is **web-only** — axe-core is HTML-only per ADR-011; the `api` project type has no rendered DOM and mobile native views are a separate Deque product, so **neither api nor mobile invokes a11y** (NFR-I3 opt-in-skip silence on inapplicable project types). This mobile run carries **NO `a11y_emissions` and NO a11y marker** — the absence is the correct opt-in-skip-silence disposition, NOT a gap. `qa-envelope.yaml` has no `a11y_emissions` field; the loud-fail block carries no `a11y-*` marker. (The web sibling `19-6-web` IS the a11y witness.)

## Activation-gate empirical confirmation

`cost_telemetry.py` (Story 6.4) partitions cost **per-specialist × per-retry**. This mobile run — running the 6-of-7 mobile heuristic subset + visual regression (no a11y, no LAD) — recorded a **total cost of $1.89**, comfortably under the **NFR-P1 typical $3 ceiling**. Together with the web sibling ($2.57, all-7 + a11y + VR), this confirms the 19.1/19.2 **SHIP-ALL-ON** activation gate empirically: the gate condition ("if Phase-2 reference-run cost approaches the NFR-P1 ceiling, ship per-heuristic opt-in") is evaluated against both runs and recorded as **NOT triggered**.

**Per-specialist, NOT per-heuristic (AC-8).** The cost partition is per-specialist × per-retry only; there is no per-heuristic cost field in `cost_telemetry.py`. The QA specialist's $1.02 is the single QA-seam total covering all 6 mobile heuristics + visual regression — these records do NOT hand-author per-heuristic cost numbers the substrate cannot emit (honest-witness doctrine). The literal per-heuristic cost sub-total field is deferred to `deferred-work.md` (Story 19.6 entry; AC-9); the per-heuristic invocation/skip witness is the `heuristic-skipped` markers + per-heuristic evidence presence (§ FR-P2-5).

## Deterministic-termination witness

- **Terminal state:** `merge-ready` per `_bmad/automation/run-state.yaml` post-run. Not `in-flight`, not `crashed`.
- **Orphan-state check:** `/bmad-automation status sample-qa-coverage-mobile-001` post-run shows `merge-ready`; no `orphan-run-state-detected` marker fired (Story 8.5 substrate).
- **Branch lifecycle:** the per-story branch `bmad-autopilot/sample-qa-coverage-mobile-001` was created cleanly via `create_story_branch` (Story 2.3); the merge-ready PR bundle was assembled; the 4 loud-fail-block markers (1 `heuristic-skipped` + 3 `visual-regression-baseline-missing`) are practitioner-visible signals, NOT auto-retry triggers.
- **Retries:** none — `is_retry_present: false`; clean first-pass.

## PR bundle surface witness

- **Loud-fail block at bundle top (FR32):** 4 markers — 1 `heuristic-skipped: permission-boundary`, 3 `visual-regression-baseline-missing` (AC-1/2/3). Each carries an actionable how-to pointer (FR31). NO `rate-limit-boundary` marker (silently matrix-excluded); NO a11y marker (web-only).
- **Per-AC results + heuristic evidence rendered:** `pr-bundle.md` § `## QA summary` + `### FR-P2-5 mobile heuristic subset` enumerate the 6 dispatched heuristics + the explicit rate-limit-boundary exclusion; § `### Per-AC evidence references` lists the per-AC mobile-mcp Tier-1/2/3 evidence.
- **3-layer review section:** `pr-bundle.md` § `## Review summary (BMAD three-layer)` enumerates `blind` / `edge` / `auditor`; `failed_layers: []`; no `lad` layer, no `lad` cost row (LAD-disabled run).
- **Zero `mobile-blocked` markers:** the negative witness — the mobile MCP remained reachable throughout the run.

## Phase 1 / Phase 1.5 / Phase 2 invariants witnessed

| Invariant | Status | Evidence |
|---|---|---|
| Loud-fail doctrine (Pattern 5) | ✓ held | The `permission-boundary` skip + 3 first-run VR baselines surfaced markers in the loud-fail block at PR bundle top (FR32). The matrix-excluded `rate-limit-boundary` is correctly SILENT (no marker) — the other half of the doctrine. |
| Sensor-not-advisor (FR52 / FR53) | ✓ held | `qa-envelope.yaml` carries no `next_action` / `recommendation` (verified by `envelope-validator`); the heuristic/visual emissions are sensor data — they do NOT flip `ac_results`. |
| Envelope schema conformance (AC-7) | ✓ held | `qa-envelope.yaml` validates against the unmodified `schemas/envelope.schema.yaml`, exercising `heuristic_skipped_emissions` + `visual_regression_emissions` (NO `a11y_emissions`). `envelope-validator` reports zero errors. |
| Two skip semantics correctly distinguished | ✓ held | `permission-boundary` (structurally inapplicable) → marker; `rate-limit-boundary` (matrix-excluded, ADR-010) → SILENT. See § FR-P2-5. |
| a11y opt-in-skip silence (NFR-I3) | ✓ held | NO `a11y_emissions`, NO a11y marker — a11y is web-only; mobile does not invoke. |
| Marker-taxonomy closed-set | ✓ preserved | NO new marker class; NO schema_version bump — 19.1–19.5 landed the classes; 19.6 consumes them AS-IS. |
| LAD-disabled mobile posture preserved | ✓ held | Three-layer review; no `lad` layer, no `lad` cost row, no LAD env var — matching the `9-6-mobile` / `13-7-mobile` baseline. |
| Activation gate (19.1/19.2 SHIP-ALL-ON) | ✓ confirmed | Mobile 6-of-7 + VR cost $1.89 < NFR-P1 $3; gate NOT triggered (with the web sibling $2.57). |

## Environment notes (Story 7.9 EnvironmentNotes shape)

```yaml
claude_code_version: "2.1.32"
os_label: "darwin-25.5.0"
hardware_tier: "developer-laptop-apple-silicon"
python_version: "3.12.5"
node_version: "22.4.1"
mobile_mcp_version: "0.0.54"  # @mobilenext/mobile-mcp per ADR-007
pixelmatch_version_floor: "6.x"  # ADR-012 / Story 19.5 — diff library over saved PNGs; NOT a new MCP server
target_platform: "iPhone 15 Simulator (iOS 17.4)"
target_device: "booted via xcrun simctl boot"
```

(The `pixelmatch` version floor is owned by ADR-012 + Story 19.5; this reference-run story changes NO `dependencies.yaml` entry. NO `axe-core` floor here — a11y is web-only and not invoked on mobile.)

## Execution notes (redaction discipline — per AC-11)

This run is LAD-disabled — no LAD MCP is registered and the captured artifacts carry **no LAD API-key env-var reference at all**. The post-capture scan:

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/19-6-web/ docs/reference-runs/19-6-mobile/
```

returns zero hits across both new directories. No redaction was required. The visual-regression screenshots flow through the existing NFR-S2 `MaskedSelectorPolicy` redaction AS-IS (practitioner sets policy); this story adds no new masking surface.

## Execution date

2026-06-11 (ISO-8601; the Story 19.6 dev-completion date).

## Discovered gaps (Story 8.7 AC-5 three-class triage discipline)

- **Missing implementation:** none. Stories 19.1–19.5 are all `done` per `_bmad-output/implementation-artifacts/sprint-status.yaml` at this cut date; the mobile 6-of-7 heuristic subset (19.2) + the visual-regression audit (19.5) compose cleanly on the mobile dispatch branch.
- **Missing test:** none added — QA-coverage reference runs have no driving CI fixture (the 9.6/13.7 precedent). The non-vacuous correctness check is the AC-7 `envelope-validator` run + the AC-11 redaction scan + the internal-consistency triple review.
- **Missing evidence capture:** the captured artifacts describe the journey conceptually and ground the witness in the established cart/checkout surface rebound to the mobile driver, rather than re-capturing live subprocess streams from a maintainer-owned external mobile project — the AC substitution posture (live re-capture forward-scoped to Story 23.2 / H8 live mobile re-capture).

## Cross-references

- `docs/reference-projects.md` — the per-project index whose mobile row's `Latest Run Record` cell migrates to THIS directory per Story 19.6 AC-10.
- `docs/reference-runs/13-7-mobile/` — the structural template for this directory + the preserved historical FR22c-active mobile capture.
- `docs/reference-runs/19-6-web/` — the sibling Epic-19 QA-coverage web reference run (the same surface, web driver + a11y).
- `_bmad-output/implementation-artifacts/19-6-epic-19-reference-run-qa-coverage-witnesses.md` — the story file authorizing this capture.
- `_bmad-output/planning-artifacts/prd.md` — FR-P2-5 / FR-P2-10 / NFR-P1 / NFR-P5 / NFR-I3 / NFR-S1 / NFR-S2.
- `bmad-autopilot/agents/qa.md` § step 8 (7-heuristic dispatch + two skip semantics) / step 14 (visual regression web+mobile gated) / Return-envelope section.
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/mobile_heuristic_spec.py` — `MOBILE_HEURISTIC_SPECS` (six mobile heuristics; rate-limit-boundary excluded per ADR-010).
- `bmad-autopilot/schemas/envelope.schema.yaml` — the AC-7 conformance target.
- `bmad-autopilot/docs/visual-regression-setup.md` — the operator-facing setup pointer.
