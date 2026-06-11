# PR Bundle: sample-qa-coverage-mobile-001 (merge-ready; Epic-19 QA coverage — 6-of-7 heuristic subset + visual regression)

<!-- bundle-mode: thickened; is_retry_present: false -->

> **Note on the rendered section names.** This `pr-bundle.md` is an
> illustrative stand-in capture (the AC substitution posture inherited
> from Stories 9.6 / 13.7). Its section headers mirror the
> `docs/reference-runs/13-7-mobile/` precedent. The runtime bundle
> assembler (`tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py`)
> renders the QA section under the H2 `## Per-AC results` with per-AC
> `### <ac-id> — status: <status>` blocks; the `heuristic_skipped_emissions`
> under the `### Exploratory heuristic findings` H3 sub-section; the
> loud-fail block under `## ⚠️ Loud-Fail Markers`; the cost partition under
> `## 💸 Cost Breakdown`. The `visual_regression_emissions` records ride
> the `qa-envelope.yaml` surface (the AC-7 schema-conformance witness) and
> are surfaced here in the loud-fail block per the `agents/qa.md`
> Return-envelope contract.

## Loud-fail block

<!-- bmad-automation:marker heuristic-skipped: permission-boundary -->
- `heuristic-skipped: permission-boundary` (FR-P2-5 mobile heuristic subset; the cart/checkout mobile surface has no role/permission-gated surface as a cross-AC exploratory surface, so the heuristic is structurally inapplicable — `surface_heuristic_skipped` per Story 4.9 substrate, sub_classification expanded to seven per Story 19.2 / ADR-010). How to enable: declare `permission-boundary` applicable in an AC's `heuristic_applicability` in the QA Behavioral Plan AND implement a role/permission-gated surface. See `docs/extension-audit.md` § FR22 + `agents/qa.md` step 8.

<!-- bmad-automation:marker visual-regression-baseline-missing: AC-1 -->
- `visual-regression-baseline-missing` (AC-1) (FR-P2-10 visual regression; web+mobile, `visual_regression.enabled: true`; first run — no prior baseline PNG existed at `_bmad-output/qa-visual-baseline/sample-qa-coverage-mobile-001/ac-1/baseline.png` (gitignored), so the current screenshot — captured via the mobile-mcp `mobile_take_screenshot` surface — was written as the new baseline and this informational marker fired; nothing to diff against yet — `surface_visual_regression_baseline_missing` per Story 19.5 substrate). See `docs/visual-regression-setup.md`.

<!-- bmad-automation:marker visual-regression-baseline-missing: AC-2 -->
- `visual-regression-baseline-missing` (AC-2) (FR-P2-10 visual regression; first-run baseline creation for AC-2's rejection screen via mobile_take_screenshot — informational; `surface_visual_regression_baseline_missing` per Story 19.5). See `docs/visual-regression-setup.md`.

<!-- bmad-automation:marker visual-regression-baseline-missing: AC-3 -->
- `visual-regression-baseline-missing` (AC-3) (FR-P2-10 visual regression; first-run baseline creation for AC-3's confirmation screen via mobile_take_screenshot — informational; `surface_visual_regression_baseline_missing` per Story 19.5). See `docs/visual-regression-setup.md`.

(Zero `mobile-blocked` markers — the mobile MCP remained reachable throughout the run. Zero `LAD-skipped` markers — LAD-disabled run, matching the `9-6-mobile` / `13-7-mobile` baseline; no `lad` layer, no `lad` cost row. **Zero `a11y-*` markers — a11y is web-only (NFR-I3); mobile does not invoke** (no `a11y_emissions` field on the envelope). **Zero `heuristic-skipped: rate-limit-boundary` marker — `rate-limit-boundary` is SILENTLY matrix-excluded on mobile per ADR-010; matrix-exclusion is the silent skip arm, distinct from the structural-inapplicability marker arm** — adding a marker here would be a doctrine violation. See `narrative.md` § FR-P2-5 mobile 6-of-7 heuristic subset.)

## Story

`sample-qa-coverage-mobile-001` — the established UI-bearing e-commerce cart/checkout synthetic surface (the SAME surface as `19-6-web`), rebound to the mobile driver surface per Story 19.6 AC-2. project_type=mobile per Story 9.2 detection. Driver=mobile per Story 9.3 dispatch. The `## QA Behavioral Plan` declares the 6-of-7 mobile heuristic applicability per AC + the `visual_regression` opt-in block (enabled); NO `a11y:` block (web-only).

## Acceptance criteria

- AC-1: a logged-in user can add an item to the cart.
- AC-2: the checkout form rejects an invalid payment card.
- AC-3: an order confirmation screen renders after a successful purchase.

## Dev summary

Implemented the cart/checkout/confirmation mobile screens so the QA specialist's 6-of-7 mobile heuristic subset + visual-regression capture have a rendered mobile surface to exercise. No retries; clean first-pass.

Commit: `Story sample-qa-coverage-mobile-001: cart + checkout + confirmation screens (Epic-19 QA-coverage surface)`

## Review summary (BMAD three-layer)

- Blind Hunter: clean
- Edge Case Hunter: clean
- Acceptance Auditor: rationale validated

failed_layers: []

(LAD-disabled run — mobile + LAD is not a default-on combination; this run matches the `9-6-mobile` / `13-7-mobile` baseline. No `lad` layer, no `lad` cost-partition row.)

## QA summary

- AC-1: pass (main add-to-cart flow; empty-state + large-input-boundary heuristics applicable, evidence captured)
- AC-2: pass (main invalid-card-rejection flow; error-state + locale-i18n-edge heuristics applicable, evidence captured)
- AC-3: pass (main order-confirmation flow; auth-boundary heuristic applicable, evidence captured)
- Heuristics (FR-P2-5 mobile subset — 6 dispatched): empty-state ✓, error-state ✓, auth-boundary ✓, large-input-boundary ✓, locale-i18n-edge ✓ (5 applicable, no findings); permission-boundary skipped (marker in the loud-fail block above); rate-limit-boundary silently matrix-excluded (ADR-010 — no marker)
- a11y (FR-P2-6): NOT invoked — web-only (NFR-I3)
- Visual regression (FR-P2-10 — enabled): first-run baseline created per AC via mobile_take_screenshot; 3 `visual-regression-baseline-missing` informational markers
- Behavioral plan: human-reviewed
- Driver: mobile (Story 9.3 dispatch — `mobile_driver.MobileDriver` Protocol; mobile-mcp tool surface per ADR-007)

### FR-P2-5 mobile heuristic subset — applicable-vs-skipped-vs-excluded

| heuristic (`HeuristicKind`) | mobile disposition | outcome |
|---|---|---|
| `empty-state` | applicable | drove the empty-cart state via mobile-mcp (AC-1) — no finding; evidence `heuristics/empty-state-cart-empty.json` |
| `error-state` | applicable | drove the card-declined error surface via mobile-mcp (AC-2) — no finding; evidence `heuristics/error-state-card-declined.json` |
| `auth-boundary` | applicable | drove the session-expiry boundary via mobile-mcp (AC-3) — no finding; evidence `heuristics/auth-boundary-session-expiry.json` |
| `large-input-boundary` | applicable | drove the quantity-overflow clamp via mobile-mcp (AC-1) — no finding; evidence `heuristics/large-input-boundary-quantity-overflow.json` |
| `locale-i18n-edge` | applicable | drove the EUR/RTL-locale formatting via mobile-mcp (AC-2) — no finding; evidence `heuristics/locale-i18n-edge-eur-rtl.json` |
| `permission-boundary` | **structurally inapplicable** | `heuristic-skipped: permission-boundary` marker (no role/permission-gated surface) |
| `rate-limit-boundary` | **silently matrix-excluded (ADR-010)** | NOT dispatched; NO marker (matrix-exclusion = silent skip arm) |

### Per-AC evidence references (FR19 evidence-triple invariant)

All AC paths under `_bmad-output/qa-evidence/sample-qa-coverage-mobile-001/run-001/`. Tier-1 = `mobile_list_elements_on_screen` a11y-tree JSON; Tier-2 = `mobile_take_screenshot` PNG.

- AC-1: `ac-1/main-add-to-cart-elements.json` (Tier-1), `ac-1/main-cart-screen.png` (Tier-2)
- AC-2: `ac-2/main-reject-invalid-card-elements.json` (Tier-1), `ac-2/main-rejection-screen.png` (Tier-2), `ac-2/main-semantic-verification.json` (Tier-3)
- AC-3: `ac-3/main-order-confirmation-elements.json` (Tier-1), `ac-3/main-confirmation-screen.png` (Tier-2), `ac-3/main-semantic-verification.json` (Tier-3)

### Visual-regression evidence (gitignored baselines cited, not committed)

- Visual screenshots (qa-evidence): `visual/ac-1-screenshot.png`, `visual/ac-2-screenshot.png`, `visual/ac-3-screenshot.png` (captured via mobile_take_screenshot). First-run baselines created at `_bmad-output/qa-visual-baseline/sample-qa-coverage-mobile-001/{ac-1,ac-2,ac-3}/baseline.png` — **gitignored, NOT committed** (cited conceptually, exactly as qa-evidence is cited without committing binaries).

## Cost telemetry (NFR-P5 — per-specialist × per-retry partition)

| Specialist | First-pass | Retries | Total |
|---|---|---|---|
| dev | $0.52 | — | $0.52 |
| qa | $1.02 | — | $1.02 |
| review-bmad | $0.35 | — | $0.35 |
| **Total** | **$1.89** | **—** | **$1.89** |

Cost target: NFR-P1 typical $3 (this run is $1.89, within budget) — the mobile 6-of-7 + visual-regression run stays under the ceiling (with the web sibling $2.57, the empirical confirmation of the 19.1/19.2 SHIP-ALL-ON activation gate). No `lad` row — LAD-disabled run per the `9-6-mobile` baseline. The cost partition is **per-specialist × per-retry**, NOT per-heuristic — the QA specialist's $1.02 is the single QA-seam total covering all 6 mobile heuristics + visual regression; the literal per-heuristic cost sub-total is deferred (see `narrative.md` § Activation-gate empirical confirmation + `deferred-work.md` Story 19.6 entry).

## Retry history

(no retries — first-pass clean; `is_retry_present: false`)

## Run metadata

- run-id: run-001
- branch: bmad-autopilot/sample-qa-coverage-mobile-001
- run-state: _bmad/automation/run-state.yaml (auto-cleaned post-merge)
- project_type: mobile
- driver: mobile (Story 9.3)
- review posture: 3-layer (blind / edge / auditor) — LAD-disabled per the 9-6-mobile / 13-7-mobile baseline
- target platform: iPhone 15 Simulator (iOS 17.4; booted via `xcrun simctl boot`)
- terminal state: merge-ready
- Epic-19 witness: 6-of-7 mobile heuristics dispatched (5 applicable + 1 skipped; rate-limit-boundary silently matrix-excluded); visual-regression first-run baseline ×3; NO a11y (web-only)
