# Reference Run 13-7 — FR22c-Active Mobile Reference Run (within-AC flow-branch coverage witness) — narrative

## Reference project

Per Story 13.7 AC-2 + the AC-1(c) substitution posture inherited from Phase 1.5 Story 9.6: the QA surface is **Story 13.5's canonical multi-branch synthetic story** — the e-commerce cart/checkout story whose `## QA Behavioral Plan` is `tools/loud-fail-harness/tests/fixtures/flow-branch-coverage/clean/qa-behavioral-plan.md` (3 ACs, each carrying 2–3 `flow_branches[]`, a mix of `must-visit` and `intentionally-skipped`) — **rebound to the mobile driver surface**. It is the SAME multi-branch synthetic story the sibling `13-7-web` run exercises; only the driver mechanics differ. The Dev specialist implemented the cart/checkout/confirmation mobile screens as the diff; the QA specialist drove them via the mobile-MCP driver (Story 9.3 / ADR-007).

The strictly-linear `sample-auto-mobile-001` greeter (the Phase 1.5 / Story 9.6 mobile reference, captured at `docs/reference-runs/9-6-mobile/`) has a single linear AC with **no branching steps** — it cannot witness FR22c. Story 13.5 already built the canonical multi-branch synthetic story for exactly this purpose; reusing it (rather than inventing a fresh synthetic story) keeps this reference run reconcilable against the same `flow-branch-coverage-gate` the fixture feeds (Story 13.7 AC-3 + Dev Notes).

Live re-capture against a maintainer-owned external mobile project (PRD line 815 — "practitioner-actually-useful, not synthetic demo") is **forward-scoped to Phase 2**, the same substitution commitment Story 9.6 made. At Phase 2 reference-run-capture time the maintainer substitutes a real mobile project into the `Latest Run Record` cell of `docs/reference-projects.md`'s mobile row; THIS directory's `13-7-mobile/` path becomes a historical capture and an additional `reference-runs/<phase-2-story-id>-mobile/` directory captures the fresher run.

## Reference project purpose + scope

This run is the **mobile-side empirical witness for Epic 13 success criterion 2** (Sprint Change Proposal 2026-05-20 Section 5) and **success criterion 5** ("operator observes the QA agent visiting optional branches it previously skipped"). It demonstrates the project-type-agnostic FR22c discipline: the within-AC flow-branch enumeration (`agents/qa.md` step 3) and the `must-visit` branch driving (`agents/qa.md` step 6 + step 8's mobile sub-paragraph, landed by Story 13.4) are identical to the web run — only the *driving mechanics* differ, the mobile-MCP `mobile_*` tool surface replacing the Playwright MCP surface. The run is LAD-disabled, matching the `9-6-mobile` Phase 1.5 baseline (mobile + LAD is not a default-on combination); the review posture is the three-layer `blind` / `edge` / `auditor` pass with no `lad` layer and no `lad` cost-partition row.

## Chosen story user-visible outcome

The Dev specialist implemented an e-commerce cart/checkout mobile surface: AC-1 (a logged-in user can add an item to the cart), AC-2 (the checkout form rejects an invalid payment card), and AC-3 (an order confirmation screen renders after a successful purchase). The user-visible outcome is the running mobile app behaving correctly not only on each AC's main flow but on its optional / branching steps — driven and verified through the mobile-MCP surface.

## FR22c within-AC flow-branch coverage

This subsection is the operator-facing witness for Epic 13 success criterion 5 — per AC, which branches were `must-visit` (driven, with evidence) versus `intentionally-skipped` (marker-emitted, with rationale). Evidence is mobile-MCP-sourced: Tier-1 = `mobile_list_elements_on_screen` a11y-tree JSON; Tier-2 = `mobile_take_screenshot` PNG.

**AC-1 — a logged-in user can add an item to the cart** (all branches `must-visit`):

| branch_id | disposition | outcome |
|---|---|---|
| `empty-cart-add` | `must-visit` | driven via mobile-MCP — Tier-1 `branch-empty-cart-add-elements.json` + Tier-2 `branch-empty-cart-add-screen.png` |
| `increment-existing` | `must-visit` | driven via mobile-MCP — Tier-1 `branch-increment-existing-elements.json` + Tier-2 `branch-increment-existing-screen.png` |
| `max-quantity` | `must-visit` | driven via mobile-MCP — Tier-1 `branch-max-quantity-elements.json` + Tier-2 `branch-max-quantity-screen.png` |

**AC-2 — the checkout form rejects an invalid payment card** (mixed dispositions):

| branch_id | disposition | outcome |
|---|---|---|
| `expired-card` | `must-visit` | driven via mobile-MCP — Tier-1 `branch-expired-card-elements.json` + Tier-2 `branch-expired-card-screen.png` |
| `wrong-cvc` | `must-visit` | driven via mobile-MCP — Tier-1 `branch-wrong-cvc-elements.json` + Tier-2 `branch-wrong-cvc-screen.png` |
| `unsupported-network` | `intentionally-skipped` | `heuristic-skipped: flow-branch-unsupported-network` marker; skip_rationale "card-network gating is out of MVP scope" |

**AC-3 — an order confirmation screen renders after a successful purchase** (mixed dispositions):

| branch_id | disposition | outcome |
|---|---|---|
| `guest-checkout` | `must-visit` | driven via mobile-MCP — Tier-1 `branch-guest-checkout-elements.json` + Tier-2 `branch-guest-checkout-screen.png` |
| `gift-receipt` | `intentionally-skipped` | `heuristic-skipped: flow-branch-gift-receipt` marker; skip_rationale "gift-receipt rendering is deferred to a Phase 2 story" |

Aggregate: **6 `must-visit` branches driven** through the mobile-MCP surface with per-branch Tier-1 + Tier-2 evidence; **2 `intentionally-skipped` branches** loud-failed with `heuristic-skipped: flow-branch-<branch-id>` markers. The full internal-consistency triple — `qa-envelope.yaml` ↔ `pr-bundle.md` ↔ this `narrative.md` — agrees on all eight branches.

## FR22c surface-placement discipline

This run's records honour `agents/qa.md` § "FR22c within-AC flow-branch coverage — where it lives in the return" (landed by Story 13.4) — recorded here so a future maintainer does not "tidy" the records by mis-routing the skips:

- **Epic 13 adds NO field to `schemas/envelope.schema.yaml`** (`additionalProperties: false`). `qa-envelope.yaml` carries no FR22c-specific field; it validates against the *unmodified* envelope schema (verified during authoring — `Draft202012Validator` reports zero errors).
- **Per-`must-visit`-branch evidence rides ONLY on the existing `ac_results[i].evidence_refs` array** (the Story 4.7 assertion-evidence triple). The `branch-<branch-id>-*` path naming distinguishes it from the AC's main-happy-path evidence. No new per-branch envelope field.
- **`heuristic_skipped_emissions` carries ONLY genuine FR22 cross-AC exploratory-heuristic skips.** On this run it carries exactly one entry — `auth-boundary` — whose `sub_classification` is in the closed `{empty-state, error-state, auth-boundary}` enum. **NO `flow-branch` sub_classification appears in `heuristic_skipped_emissions`** — a `flow-branch` value there would fail `envelope.schema.yaml`'s `$defs/heuristic_skipped_emission`.
- **The `heuristic-skipped: flow-branch-<branch-id>` markers appear in `pr-bundle.md`'s loud-fail block** — sourced, per the Story 13.3 / 13.4 contract, from the harness `AcIterationResult.flow_branch_coverage` model, NOT from an envelope field. The within-AC `flow-branch` skip and the cross-AC exploratory-heuristic skip share the `heuristic-skipped` marker *class* (taxonomy v1.6 — Story 13.6) but route to different surfaces.
- **The operator-visible enumerated `flow_branches[]` lives in the `## QA Behavioral Plan` story-doc section**; `pr-bundle.md`'s `### QA Behavioral Plan — within-AC flow branches (FR22c)` subsection surfaces it for the reader of this captured record.

## Deterministic-termination witness

- **Terminal state:** `merge-ready` per `_bmad/automation/run-state.yaml` post-run. Not `in-flight`, not `crashed`.
- **Orphan-state check:** `/bmad-automation status sample-flow-branch-mobile-001` post-run shows `merge-ready`; no `orphan-run-state-detected` marker fired (Story 8.5 substrate).
- **Branch lifecycle:** the per-story branch `bmad-autopilot/sample-flow-branch-mobile-001` was created cleanly via `create_story_branch` (Story 2.3); the merge-ready PR bundle was assembled; the three `heuristic-skipped` markers are practitioner-visible signals, NOT auto-retry triggers.
- **Retries:** none — `is_retry_present: false`; clean first-pass.

## PR bundle surface witness

- **Loud-fail block at bundle top (FR32):** three `heuristic-skipped` markers — `auth-boundary` (cross-AC), `flow-branch-unsupported-network` + `flow-branch-gift-receipt` (within-AC FR22c). Each carries an actionable how-to-enable pointer (FR31); the two flow-branch markers additionally surface the branch's one-line `skip_rationale`.
- **Enumerated `flow_branches[]` rendered:** `pr-bundle.md` § `### QA Behavioral Plan — within-AC flow branches (FR22c)` renders all eight branches per AC.
- **Per-`must-visit`-branch evidence:** `pr-bundle.md` § `### Per-AC evidence references` lists each `must-visit` branch's Tier-1 + Tier-2 mobile-MCP evidence, distinguishable from the AC's main-path evidence by the `branch-<branch-id>-*` path naming.
- **3-layer review section:** `pr-bundle.md` § `## Review summary (BMAD three-layer)` enumerates `blind` / `edge` / `auditor`; `failed_layers: []`; no `lad` layer, no `lad` cost row (LAD-disabled run).
- **Zero `mobile-blocked` markers:** the negative witness — the mobile MCP remained reachable throughout the run.

## Phase 1 / Phase 1.5 invariants witnessed

| Invariant | Status | Evidence |
|---|---|---|
| Loud-fail doctrine (Pattern 5) | ✓ held | Three `heuristic-skipped` markers landed in the loud-fail block at PR bundle top (FR32). Zero silent skips. |
| Sensor-not-advisor (FR52 / FR53) | ✓ held | `qa-envelope.yaml` carries no `next_action` / `recommendation`; the flow-branch coverage is sensor data. |
| Envelope schema unextended by Epic 13 | ✓ held | `qa-envelope.yaml` validates against the unmodified `schemas/envelope.schema.yaml`; FR22c adds no field. |
| Marker-taxonomy v1 27-class closed-set | ✓ preserved | The `flow-branch` token is a v1.6 PATCH-bump `sub_classification` under the EXISTING `heuristic-skipped` class (Story 13.6) — no new top-level marker class. |
| Pluggability invariant (FR62) | ✓ held | The mobile dispatch branch composes against the same substrate the web/api branches use; no specialist file references another. |
| FR22c is project-type-agnostic | ✓ held | The within-AC flow-branch enumeration + `must-visit` driving discipline is identical to the `13-7-web` run; only the driver surface (`mobile_*` MCP tools) differs. |

## Environment notes (Story 7.9 EnvironmentNotes shape)

```yaml
claude_code_version: "2.1.32"
os_label: "darwin-25.3.0"
hardware_tier: "developer-laptop-apple-silicon"
python_version: "3.12.5"
node_version: "22.4.1"
mobile_mcp_version: "0.0.54"  # @mobilenext/mobile-mcp per ADR-007
target_platform: "iPhone 15 Simulator (iOS 17.4)"
target_device: "booted via xcrun simctl boot"
```

## Execution notes (redaction discipline — per AC-11)

This run is LAD-disabled — no LAD MCP is registered and the captured artifacts carry **no LAD API-key env-var reference at all**. The post-capture scan:

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/13-7-web/ docs/reference-runs/13-7-mobile/
```

returns zero hits across both new directories. No redaction was required.

## Execution date

2026-05-22 (ISO-8601; the Story 13.7 dev-completion date).

## Discovered gaps (Story 8.7 AC-5 three-class triage discipline)

- **Missing implementation:** none. Stories 13.1–13.6 (Epic 13 FR22c mechanical surface) are all `done` per `_bmad-output/implementation-artifacts/sprint-status.yaml` at this cut date; the project-type-agnostic FR22c surface composes cleanly on the mobile dispatch branch.
- **Missing test:** none. The `flow-branch-coverage-gate` (Story 13.5) reconciles the FR22c within-AC branch-coverage contract in CI; this reference run reuses that gate's `clean/` multi-branch story as its QA surface, rebound to the mobile driver.
- **Missing evidence capture:** the captured artifacts describe the journey conceptually and ground the FR22c witness in the Story 13.5 multi-branch synthetic story rather than re-capturing live subprocess streams from a maintainer-owned external mobile project. This is the AC-1(c) substitution posture (`docs/reference-runs/9-6-mobile/narrative.md` § Discovered gaps) — live re-capture is forward-scoped to Phase 2.

## Cross-references

- `docs/reference-projects.md` — the per-project index whose mobile row's `Latest Run Record` cell migrates to THIS directory per Story 13.7 AC-5.
- `docs/reference-runs/9-6-mobile/` — the structural template for this directory + the preserved historical pre-FR22c mobile capture.
- `docs/reference-runs/13-7-web/` — the sibling FR22c-active web reference run (the same multi-branch synthetic story, web driver surface).
- `_bmad-output/implementation-artifacts/13-7-reference-run-refresh-web-and-mobile-fr22c-active-records.md` — the story file authorizing this capture.
- `_bmad-output/implementation-artifacts/13-5-multi-branch-ci-fixture-flow-branch-coverage-gate.md` — the multi-branch synthetic story fixture this run reuses as its QA surface.
- `_bmad-output/planning-artifacts/prd.md` — FR22c (within-AC flow-branch coverage contract).
- `_bmad-output/planning-artifacts/architecture.md` § Pattern 8 (Within-AC Flow-Branch Enumeration — QA).
- `bmad-autopilot/agents/qa.md` § "FR22c within-AC flow-branch coverage — where it lives in the return" + step 6 / step 8 mobile sub-paragraph — the surface-placement + mobile-driving spec this run honours.
