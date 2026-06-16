# PR Bundle: sample-qa-coverage-001 (merge-ready; Epic-20 QA independence — plan re-derivation cross-check + flakiness threshold)

<!-- bundle-mode: thickened; is_retry_present: false -->

> **Note on the rendered section names.** This `pr-bundle.md` is an
> illustrative stand-in capture (the AC-1 substitution posture inherited
> from Stories 9.6 / 10.7 / 13.7 / 19.6). Its section headers mirror the
> `docs/reference-runs/19-6-web/` precedent. The runtime bundle assembler
> (`tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py`)
> renders the QA section under the H2 `## Per-AC results`; the FR-P2-9
> cross-check line (`_render_qa_plan_rederivation_line`) co-located with the
> FR25 compromise blockquote (`render_compromise_blockquote`, RETAINED per
> Story 20.1's retain-and-accompany resolution); the
> `### Flakiness threshold exceeded` H3 + per-AC marker comment
> (`_render_qa_flakiness_subsection`); the `### Plan re-derivation drift
> detected` H3 + marker comment (`_render_qa_plan_rederivation_subsection`)
> on the drift branch; the loud-fail block under `## ⚠️ Loud-Fail Markers`;
> the cost partition under `## 💸 Cost Breakdown`. The drift-branch excerpt
> below is reproduced from the run-004 follow-on bundle
> (`qa-envelope-rederivation-drift.yaml`) so the
> `plan-rederivation-drift-detected` marker is greppable in THIS file.

## Loud-fail block

<!-- bmad-automation:marker heuristic-skipped: rate-limit-boundary -->
- `heuristic-skipped: rate-limit-boundary` (FR-P2-5 carried-forward 7-heuristic sweep; the cart/checkout synthetic surface has no rate-limited endpoint as a cross-AC exploratory surface on this run, so the heuristic is structurally inapplicable — `surface_heuristic_skipped` per Story 4.9 substrate, sub_classification expanded to seven per Story 19.2 / ADR-010). How to enable: declare `rate-limit-boundary` applicable in an AC's `heuristic_applicability` in the QA Behavioral Plan AND implement a rate-limited surface. See `docs/extension-audit.md` § FR22 + `agents/qa.md` step 8. (NB: the run-004 follow-on does exactly this for AC-2 — and that re-derivation is what drives the drift witness below.)

<!-- bmad-automation:marker heuristic-skipped: permission-boundary -->
- `heuristic-skipped: permission-boundary` (FR-P2-5 carried-forward 7-heuristic sweep; the cart/checkout synthetic surface has no role/permission-gated surface as a cross-AC exploratory surface, so the heuristic is structurally inapplicable — `surface_heuristic_skipped` per Story 4.9 substrate). How to enable: declare `permission-boundary` applicable in an AC's `heuristic_applicability` AND implement a role/permission-gated surface. See `docs/extension-audit.md` § FR22 + `agents/qa.md` step 8.

(Zero `LAD-skipped` markers — `mcp__lad__code_review` reached the dual-reviewer pass and produced a clean verdict. Zero `mobile-blocked` markers — web project type. The two Epic-20 markers — `flakiness-threshold-exceeded` and `plan-rederivation-drift-detected` — are QA-EVIDENCE markers and surface at their per-AC location in `## Per-AC results` below, NOT in this loud-fail block and NOT via `run_state.active_markers` — the deliberate "QA-evidence orphan" pattern shared with `a11y-*` / `visual-regression-*` / `heuristic-skipped` / `plan-drift-detected`. See `narrative.md` § Flakiness threshold exceeded.)

## Story

`sample-qa-coverage-001` — the established UI-bearing e-commerce cart/checkout synthetic surface (reused per Story 20.4 Dev Notes — not a new app), captured as the Epic-20 QA-independence + flakiness witness. project_type=web per Story 9.2 detection. Driver=playwright per Story 4.4 dispatch. This is the third accumulating run (run-003).

## Acceptance criteria

- AC-1: a logged-in user can add an item to the cart.
- AC-2: the checkout form rejects an invalid payment card.
- AC-3: an order confirmation page renders after a successful purchase.

## Dev summary

No source change on run-003 (the cart/checkout/confirmation surface is unchanged since run-001). The Epic-20 witnesses are QA-side: the per-run plan re-derivation cross-check and the longitudinal flakiness accumulation.

## Review summary (BMAD four-layer — LAD ENABLED per Story 10.4 AC-2)

- Blind Hunter: clean (AC-coverage gap analysis pass)
- Edge Case Hunter: clean (boundary-condition analysis pass)
- Acceptance Auditor: rationale validated against the story ACs
- **LAD (Review-LAD, 4th parallel reviewer)**: clean — `mcp__lad__code_review` dual-reviewer parallel pass COMPLETED with zero findings.

failed_layers: []

The LAD layer is rendered as a clean representative pass: this run's net-new witness is the Epic-20 QA-independence + flakiness surfaces, not LAD. The genuine 12-finding real-`mcp__lad__code_review` capture is preserved permanently at `docs/reference-runs/10-7-lad-web/` (Story 20.4 AC-1 — re-deriving a fresh real LAD finding-set is out of scope).

## Per-AC results

> **Plan-persistence compromise note (FR25):**
>
> This plan is persisted across runs for resumability.
> Persistence is a known compromise: full QA independence would re-derive the plan every run.
> See `docs/extension-audit.md` and FR-P2-9 (Story 20.1, LANDED — accompanies this note with per-run plan re-derivation cross-check).

> FR-P2-9 cross-check: green

- AC-1: pass (main add-to-cart flow; empty-state + large-input-boundary heuristics applicable; 0 action-level retries — clean control AC for the flakiness corpus)
- AC-2: pass (main invalid-card-rejection flow; error-state + locale-i18n-edge heuristics applicable; **2 action-level transient retries** — a `pass` WITH action-level retries IS a transient fail per Story 20.2/20.3)
- AC-3: pass (main order-confirmation flow; auth-boundary heuristic applicable; 0 action-level retries)

The FR-P2-9 cross-check ran on the reuse-existing path (AC text unchanged → `ac_hash` matches): the persisted `## QA Behavioral Plan` and the re-derived plan agree at all three drift surfaces (`heuristic_applicability` / `flow_branches` / `semantic_verification_tier`), so `cross_check_status: green` and NO `plan-rederivation-drift-detected` marker fired. The FR25 compromise blockquote above is RETAINED (Story 20.1's retain-and-accompany resolution — the cross-check accompanies the note, it does not remove it).

### Flakiness threshold exceeded

Longitudinal flakiness surfaced by the FR-P2-8 across-runs threshold (Story 20.3): the AC's most-recent consecutive QA runs each needed an action-level transient retry. Story-level evidence — does NOT flip the AC verdict (sensor-not-advisor); inspect the gitignored flakiness log at `_bmad-output/qa-flakiness/<story-id>.yaml` (the committed snapshot of this corpus is `qa-flakiness-log.yaml` in this directory).

AC `AC-2` crossed the consecutive-transient-fail threshold.
<!-- bmad-automation:marker flakiness-threshold-exceeded -->

(`grep -c 'bmad-automation:marker flakiness-threshold-exceeded' pr-bundle.md` → 1. AC-1 / AC-3 are silent — their trailing records carry `retry_count_within_run: 0`, so no marker fires, the no-marker-on-absence parity.)

### Per-AC evidence references (FR19 evidence-triple invariant)

All AC paths under `_bmad-output/qa-evidence/sample-qa-coverage-001/run-003/`.

- AC-1: `ac-1/main-add-to-cart-action.json` (Tier-1), `ac-1/main-cart-line-count.png` (Tier-2)
- AC-2: `ac-2/main-reject-invalid-card-action.json` (Tier-1), `ac-2/main-rejection-message.png` (Tier-2), `ac-2/main-semantic-verification.json` (Tier-3)
- AC-3: `ac-3/main-order-confirmation-action.json` (Tier-1), `ac-3/main-confirmation-page.png` (Tier-2), `ac-3/main-semantic-verification.json` (Tier-3)

## Drift-run excerpt (run-004 follow-on — the FR-P2-9 drift branch)

The cross-check is per-run state, so witnessing both branches requires two run captures. The run-004 follow-on (`qa-envelope-rederivation-drift.yaml`) was a second run of the SAME story after the qa-runbook was edited to declare `rate-limit-boundary` applicable to AC-2. The AC text is unchanged, so `ac_hash` still matches and the reuse-existing path was taken; the re-derived plan now carries `rate-limit-boundary` in AC-2's `heuristic_applicability` while the persisted plan (written on run-001) does not — so the read-only cross-check found a mismatch at the `heuristic_applicability` surface. Its bundle rendered:

### Plan re-derivation drift detected

<!-- bmad-automation:marker plan-rederivation-drift-detected -->

- Story ID: `sample-qa-coverage-001`
- Drift surfaces: `heuristic_applicability`
- Drifted AC IDs: `AC-2`

(`grep -c 'bmad-automation:marker plan-rederivation-drift-detected' pr-bundle.md` → 1. The persisted `## QA Behavioral Plan` is NOT overwritten — FR-P2-9 is a read-only cross-check, Story 20.1 AC-3; FR23's `plan_status` reset on AC-hash drift remains the only refresh trigger, and the AC text did not change.)

## Cost telemetry (NFR-P5 — per-specialist × per-retry partition per Story 10.6 AC-6)

| Specialist | First-pass | Retries | Total |
|---|---|---|---|
| dev | $0.42 | — | $0.42 |
| lad | $0.48 | — | $0.48 |
| qa | $1.13 | — | $1.13 |
| review-bmad | $0.36 | — | $0.36 |
| **Total** | **$2.39** | **—** | **$2.39** |

Cost target: NFR-P1 typical $3 (this run is $2.39, within budget). **Neither Epic-20 surface adds a cost row** (AC-8): the plan re-derivation cross-check is a pure in-wrapper comparison (`surface_plan_rederivation_cross_check` — no new specialist boundary), and the flakiness log accumulates on EVERY QA run as part of the existing QA seam (it is not an opt-in cost-bearing capability like a11y / visual regression). The partition shape is unchanged from `19-6-web`. The QA specialist's $1.13 is the single QA-seam total.

(Alphabetical sort per `bundle_assembly.py` post-Story-10.6: `dev → lad → qa → review-bmad`. The `lad` row is the per-specialist Review-LAD partition witness per NFR-P5 + Story 10.6 AC-6 — the LAD-enabled 4-layer posture of the `19-6-web` baseline is preserved.)

## Retry history

(no whole-story retries — first-pass clean; `is_retry_present: false`. NB: AC-2's "2 action-level transient retries" are the Playwright-NATIVE / action-level retry tier — DISTINCT from the orchestrator whole-story retry budget, which was not consumed. This two-tier distinction is exactly what the flakiness signal captures: a story that reaches merge-ready cleanly can still be accumulating action-level flakiness.)

## Run metadata

- run-id: run-003 (primary / latest); run-004 = the drift follow-on (excerpt above)
- branch: bmad-autopilot/sample-qa-coverage-001
- run-state: _bmad/automation/run-state.yaml (auto-cleaned post-merge)
- project_type: web
- driver: playwright (Story 4.4)
- review posture: 4-layer (blind / edge / auditor / lad) — LAD-enabled per Story 10.4
- lad-mcp version_floor: bb47e9e (per ADR-008; `Shelpuk-AI-Technology-Consulting/lad_mcp_server` short-SHA)
- terminal state: merge-ready
- Epic-20 witness: FR-P2-9 cross-check green (run-003) + drift-detected (run-004); FR-P2-8 flakiness-threshold-exceeded (AC-2) over the 3-run corpus
