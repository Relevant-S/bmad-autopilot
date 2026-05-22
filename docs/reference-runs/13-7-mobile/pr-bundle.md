# PR Bundle: sample-flow-branch-mobile-001 (merge-ready; FR22c within-AC flow-branch coverage)

<!-- bundle-mode: thickened; is_retry_present: false -->

> **Note on the rendered section names.** This `pr-bundle.md` is an
> illustrative stand-in capture (the AC-1(c) substitution posture inherited
> from Stories 9.6 / 10.7). Its section headers mirror the
> `docs/reference-runs/9-6-mobile/` precedent. The runtime bundle assembler
> (`tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py`)
> renders the QA section under the H2 `## Per-AC results` with per-AC
> `### <ac-id> — status: <status>` blocks; the loud-fail block under
> `## ⚠️ Loud-Fail Markers`; the cost partition under `## 💸 Cost
> Breakdown`. The enumerated `flow_branches[]` are the operator-facing
> FR22c surface and live in the story doc's `## QA Behavioral Plan`
> section — surfaced here for the reader.

## Loud-fail block

<!-- bmad-automation:marker heuristic-skipped: auth-boundary -->
- `heuristic-skipped: auth-boundary` (FR22 plan-driven applicability; no AC declared auth-boundary applicable — the cart/checkout synthetic story has no session-expiry boundary as a cross-AC exploratory surface — `surface_heuristic_skipped` per Story 4.9 substrate). How to enable: declare auth-boundary applicable in an AC's `heuristic_applicability` in the QA Behavioral Plan AND implement a session-expiry boundary. See `docs/extension-audit.md` § FR22 + `skills/bmad-automation/steps/qa-mobile-heuristics.md` § auth-boundary.

<!-- bmad-automation:marker heuristic-skipped: flow-branch-unsupported-network -->
- `heuristic-skipped: flow-branch-unsupported-network` (FR22c within-AC flow-branch coverage; AC-2's `unsupported-network` flow branch was enumerated `intentionally-skipped` in the QA Behavioral Plan — `surface_flow_branch_skipped` per Story 13.3 substrate, marker taxonomy v1.6 `flow-branch` sub-classification per Story 13.6). skip_rationale: "card-network gating is out of MVP scope". How to enable: set the branch's `disposition: must-visit` in AC-2's `flow_branches[]` of the `## QA Behavioral Plan` AND implement the unsupported-card-network surface. See `docs/architecture.md` § Pattern 8 (Within-AC Flow-Branch Enumeration) + `agents/qa.md` step 6.

<!-- bmad-automation:marker heuristic-skipped: flow-branch-gift-receipt -->
- `heuristic-skipped: flow-branch-gift-receipt` (FR22c within-AC flow-branch coverage; AC-3's `gift-receipt` flow branch was enumerated `intentionally-skipped` in the QA Behavioral Plan — `surface_flow_branch_skipped` per Story 13.3 substrate, marker taxonomy v1.6 `flow-branch` sub-classification per Story 13.6). skip_rationale: "gift-receipt rendering is deferred to a Phase 2 story". How to enable: set the branch's `disposition: must-visit` in AC-3's `flow_branches[]` of the `## QA Behavioral Plan` AND implement the gift-receipt confirmation surface. See `docs/architecture.md` § Pattern 8 + `agents/qa.md` step 6.

(Zero `mobile-blocked` markers — the mobile MCP remained reachable throughout the run. Zero `LAD-skipped` markers — LAD-disabled run, matching the `9-6-mobile` Phase 1.5 baseline; no `lad` layer, no `lad` cost row. The two `heuristic-skipped: flow-branch-*` markers are sourced, per the Story 13.3 / 13.4 contract, from the harness `AcIterationResult.flow_branch_coverage` model — NOT from the QA envelope's `heuristic_skipped_emissions` array. See `narrative.md` § FR22c surface-placement discipline.)

## Story

`sample-flow-branch-mobile-001` — the multi-branch synthetic e-commerce cart/checkout story (Story 13.5's `tests/fixtures/flow-branch-coverage/clean/qa-behavioral-plan.md`) rebound to the mobile driver surface per Story 13.7 AC-2 / AC-3. project_type=mobile per Story 9.2 detection. Driver=mobile per Story 9.3 dispatch.

## Acceptance criteria

- AC-1: a logged-in user can add an item to the cart.
- AC-2: the checkout form rejects an invalid payment card.
- AC-3: an order confirmation screen renders after a successful purchase.

## Dev summary

Implemented the cart/checkout/confirmation mobile screens — each AC's main flow plus the within-AC optional/branching steps the QA Behavioral Plan enumerates. No retries; clean first-pass.

Commit: `Story sample-flow-branch-mobile-001: cart + checkout + confirmation screens`

## Review summary (BMAD three-layer)

- Blind Hunter: clean
- Edge Case Hunter: clean
- Acceptance Auditor: rationale validated

failed_layers: []

(LAD-disabled run — mobile + LAD is not a default-on combination; this run matches the `9-6-mobile` Phase 1.5 baseline. No `lad` layer, no `lad` cost-partition row.)

## QA summary

- AC-1: pass (main flow + 3 must-visit flow branches driven)
- AC-2: pass (main flow + 2 must-visit flow branches driven; 1 intentionally-skipped branch marker-emitted)
- AC-3: pass (main flow + 1 must-visit flow branch driven; 1 intentionally-skipped branch marker-emitted)
- Heuristics: empty-state pass, error-state pass, auth-boundary skipped (marker emitted in the loud-fail block above)
- Behavioral plan: human-reviewed
- Driver: mobile (Story 9.3 dispatch — `mobile_driver.MobileDriver` Protocol; mobile-mcp tool surface per ADR-007)

### QA Behavioral Plan — within-AC flow branches (FR22c)

The enumerated `flow_branches[]` per AC (the operator-facing FR22c surface — rendered from the story doc's `## QA Behavioral Plan` section; the per-AC entry shape matches `examples/qa-behavioral-plans/qa-behavioral-plan-flow-branches.md`):

**AC-1 — a logged-in user can add an item to the cart**

| branch_id | description | disposition |
|---|---|---|
| `empty-cart-add` | adding the first item to a previously empty cart | `must-visit` |
| `increment-existing` | adding an item already in the cart increments its quantity | `must-visit` |
| `max-quantity` | adding an item already at the per-line quantity ceiling | `must-visit` |

**AC-2 — the checkout form rejects an invalid payment card**

| branch_id | description | disposition | skip_rationale |
|---|---|---|---|
| `expired-card` | submitting a card past its expiry date | `must-visit` | — |
| `wrong-cvc` | submitting a card with an incorrect CVC | `must-visit` | — |
| `unsupported-network` | submitting a card from an unsupported card network | `intentionally-skipped` | card-network gating is out of MVP scope |

**AC-3 — an order confirmation screen renders after a successful purchase**

| branch_id | description | disposition | skip_rationale |
|---|---|---|---|
| `guest-checkout` | confirmation render for a guest (non-logged-in) purchase | `must-visit` | — |
| `gift-receipt` | confirmation render with the gift-receipt option enabled | `intentionally-skipped` | gift-receipt rendering is deferred to a Phase 2 story |

Flow-branch coverage: **6 `must-visit` branches driven** through the mobile-MCP surface with per-branch Tier-1 + Tier-2 evidence; **2 `intentionally-skipped` branches** loud-failed via the `heuristic-skipped: flow-branch-<branch-id>` markers in the loud-fail block above. Only the driver mechanics differ from the `13-7-web` run.

### Per-AC evidence references (FR19 evidence-triple invariant)

Per-`must-visit`-branch evidence is distinguishable from the AC's main-happy-path evidence by the `branch-<branch-id>-*` path naming; all paths under `_bmad-output/qa-evidence/sample-flow-branch-mobile-001/run-001/`. Tier-1 = `mobile_list_elements_on_screen` a11y-tree JSON; Tier-2 = `mobile_take_screenshot` PNG.

- AC-1:
  - main: `ac-1/main-add-to-cart-elements.json` (Tier-1), `ac-1/main-cart-screen.png` (Tier-2)
  - branch `empty-cart-add`: `ac-1/branch-empty-cart-add-elements.json` (Tier-1), `ac-1/branch-empty-cart-add-screen.png` (Tier-2)
  - branch `increment-existing`: `ac-1/branch-increment-existing-elements.json` (Tier-1), `ac-1/branch-increment-existing-screen.png` (Tier-2)
  - branch `max-quantity`: `ac-1/branch-max-quantity-elements.json` (Tier-1), `ac-1/branch-max-quantity-screen.png` (Tier-2)
- AC-2:
  - main: `ac-2/main-reject-invalid-card-elements.json` (Tier-1), `ac-2/main-rejection-screen.png` (Tier-2), `ac-2/main-semantic-verification.json` (Tier-3)
  - branch `expired-card`: `ac-2/branch-expired-card-elements.json` (Tier-1), `ac-2/branch-expired-card-screen.png` (Tier-2)
  - branch `wrong-cvc`: `ac-2/branch-wrong-cvc-elements.json` (Tier-1), `ac-2/branch-wrong-cvc-screen.png` (Tier-2)
- AC-3:
  - main: `ac-3/main-order-confirmation-elements.json` (Tier-1), `ac-3/main-confirmation-screen.png` (Tier-2), `ac-3/main-semantic-verification.json` (Tier-3)
  - branch `guest-checkout`: `ac-3/branch-guest-checkout-elements.json` (Tier-1), `ac-3/branch-guest-checkout-screen.png` (Tier-2)

## Cost telemetry (NFR-P5)

| Specialist | First-pass | Retries | Total |
|---|---|---|---|
| dev | $0.50 | — | $0.50 |
| qa | $0.73 | — | $0.73 |
| review-bmad | $0.35 | — | $0.35 |
| **Total** | **$1.58** | **—** | **$1.58** |

Cost target: NFR-P1 typical $3 (this run is $1.58, within budget). No `lad` row — LAD-disabled run per the `9-6-mobile` baseline.

## Retry history

(no retries — first-pass clean; `is_retry_present: false`)

## Run metadata

- run-id: run-001
- branch: bmad-autopilot/sample-flow-branch-mobile-001
- run-state: _bmad/automation/run-state.yaml (auto-cleaned post-merge)
- project_type: mobile
- driver: mobile (Story 9.3)
- review posture: 3-layer (blind / edge / auditor) — LAD-disabled per the 9-6-mobile baseline
- target platform: iPhone 15 Simulator (iOS 17.4; booted via `xcrun simctl boot`)
- terminal state: merge-ready
- FR22c witness: 6 must-visit branches driven; 2 intentionally-skipped branches marker-emitted
