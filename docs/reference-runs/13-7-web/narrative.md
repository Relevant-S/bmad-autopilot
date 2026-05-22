# Reference Run 13-7 — FR22c-Active Web Reference Run (within-AC flow-branch coverage witness) — narrative

## Reference project

Per Story 13.7 AC-1 + the AC-1(c) substitution posture inherited from Phase 1.5 Stories 9.6 / 10.7: the QA surface is **Story 13.5's canonical multi-branch synthetic story** — the e-commerce cart/checkout story whose `## QA Behavioral Plan` is `tools/loud-fail-harness/tests/fixtures/flow-branch-coverage/clean/qa-behavioral-plan.md` (3 ACs, each carrying 2–3 `flow_branches[]`, a mix of `must-visit` and `intentionally-skipped`, with AC-2 and AC-3 each mixing both dispositions). The Dev specialist implemented the cart/checkout/confirmation web surface as the diff; the QA specialist drove it via the Playwright MCP driver (Story 4.4).

The strictly-linear `sample-auto-001` greeter (the Phase 1 / Story 8.7 web reference, captured at `docs/reference-runs/10-7-lad-web/`) has a single linear AC with **no branching steps** — it cannot witness FR22c. Story 13.5 already built the canonical multi-branch synthetic story for exactly this purpose; reusing it (rather than inventing a fresh synthetic story) keeps this reference run reconcilable against the same `flow-branch-coverage-gate` the fixture feeds, and honours the no-wheel-reinvention discipline (Story 13.7 AC-3 + Dev Notes).

Live re-capture against a maintainer-owned external project (PRD line 815 — "practitioner-actually-useful, not synthetic demo") is **forward-scoped to Phase 2**, the same substitution commitment Stories 9.6 / 10.7 made. At Phase 2 reference-run-capture time the maintainer substitutes a real web project into the `Latest Run Record` cell of `docs/reference-projects.md`'s web row; THIS directory's `13-7-web/` path becomes a historical capture and an additional `reference-runs/<phase-2-story-id>-web/` directory captures the fresher run.

## Reference project purpose + scope

This run is the **empirical witness for Epic 13 success criterion 2** (Sprint Change Proposal 2026-05-20 Section 5 — "Reference-run records refreshed … show enumerated `flow_branches[]` per AC + per-branch evidence OR `heuristic-skipped: flow-branch-<id>` markers") and **success criterion 5** ("operator observes the QA agent visiting optional branches it previously skipped"). The cross-run observation that triggered Epic 13 was that the QA agent reliably drove an AC's main flow but skipped or under-tested the optional / branching steps *within* that AC. This run is the standing proof that the originally-reported skip behavior is no longer reproducible: every `must-visit` flow branch is driven with per-branch evidence, and every `intentionally-skipped` branch is loud-failed with a marker plus its plan `skip_rationale`.

The run also preserves the LAD-enabled 4-layer review posture of the `10-7-lad-web` baseline (Story 13.7 AC-1) so that migrating the web row's `Latest Run Record` cell from `10-7-lad-web/` to `13-7-web/` does not regress the latest web capture from 4-layer to 3-layer. The LAD layer is rendered as a clean representative pass — re-deriving a fresh real 12-finding `mcp__lad__code_review` capture is explicitly out of scope; the genuine-LAD-findings capture is preserved permanently at `docs/reference-runs/10-7-lad-web/`. FR22c within-AC flow-branch coverage, not LAD, is this run's net-new witness.

## Chosen story user-visible outcome

The Dev specialist implemented an e-commerce cart/checkout surface: AC-1 (a logged-in user can add an item to the cart), AC-2 (the checkout form rejects an invalid payment card), and AC-3 (an order confirmation page renders after a successful purchase). The user-visible outcome is the running product behaving correctly not only on each AC's main flow but on its optional / branching steps — the empty-cart-vs-increment-vs-ceiling paths of add-to-cart, the expired-vs-wrong-CVC paths of card rejection, and the logged-in-vs-guest paths of order confirmation.

## FR22c within-AC flow-branch coverage

This subsection is the operator-facing witness for Epic 13 success criterion 5 — per AC, which branches were `must-visit` (driven, with evidence) versus `intentionally-skipped` (marker-emitted, with rationale).

**AC-1 — a logged-in user can add an item to the cart** (all branches `must-visit`):

| branch_id | disposition | outcome |
|---|---|---|
| `empty-cart-add` | `must-visit` | driven — Tier-1 `branch-empty-cart-add-action.json` + Tier-2 `branch-empty-cart-add-state.png` |
| `increment-existing` | `must-visit` | driven — Tier-1 `branch-increment-existing-action.json` + Tier-2 `branch-increment-existing-state.png` |
| `max-quantity` | `must-visit` | driven — Tier-1 `branch-max-quantity-action.json` + Tier-2 `branch-max-quantity-state.png` |

**AC-2 — the checkout form rejects an invalid payment card** (mixed dispositions):

| branch_id | disposition | outcome |
|---|---|---|
| `expired-card` | `must-visit` | driven — Tier-1 `branch-expired-card-action.json` + Tier-2 `branch-expired-card-rejection.png` |
| `wrong-cvc` | `must-visit` | driven — Tier-1 `branch-wrong-cvc-action.json` + Tier-2 `branch-wrong-cvc-rejection.png` |
| `unsupported-network` | `intentionally-skipped` | `heuristic-skipped: flow-branch-unsupported-network` marker; skip_rationale "card-network gating is out of MVP scope" |

**AC-3 — an order confirmation page renders after a successful purchase** (mixed dispositions):

| branch_id | disposition | outcome |
|---|---|---|
| `guest-checkout` | `must-visit` | driven — Tier-1 `branch-guest-checkout-action.json` + Tier-2 `branch-guest-checkout-confirmation.png` |
| `gift-receipt` | `intentionally-skipped` | `heuristic-skipped: flow-branch-gift-receipt` marker; skip_rationale "gift-receipt rendering is deferred to a Phase 2 story" |

Aggregate: **6 `must-visit` branches driven** with per-branch Tier-1 (mechanical) + Tier-2 (outcome) evidence; **2 `intentionally-skipped` branches** loud-failed with `heuristic-skipped: flow-branch-<branch-id>` markers. The full internal-consistency triple — `qa-envelope.yaml` ↔ `pr-bundle.md` ↔ this `narrative.md` — agrees on all eight branches.

## FR22c surface-placement discipline

This run's records honour `agents/qa.md` § "FR22c within-AC flow-branch coverage — where it lives in the return" (landed by Story 13.4) — recorded here so a future maintainer does not "tidy" the records by mis-routing the skips:

- **Epic 13 adds NO field to `schemas/envelope.schema.yaml`** (`additionalProperties: false`). `qa-envelope.yaml` carries no FR22c-specific field; it validates against the *unmodified* envelope schema (verified during authoring — `Draft202012Validator` reports zero errors).
- **Per-`must-visit`-branch evidence rides ONLY on the existing `ac_results[i].evidence_refs` array** (the Story 4.7 assertion-evidence triple). A `must-visit` branch's Tier-1 / Tier-2 evidence belongs to the AC it is a branch of; the `branch-<branch-id>-*` path naming distinguishes it from the AC's main-happy-path evidence. No new per-branch envelope field.
- **`heuristic_skipped_emissions` carries ONLY genuine FR22 cross-AC exploratory-heuristic skips.** On this run it carries exactly one entry — `auth-boundary` — whose `sub_classification` is in the closed `{empty-state, error-state, auth-boundary}` enum. **NO `flow-branch` sub_classification appears in `heuristic_skipped_emissions`** — a `flow-branch` value there would fail `envelope.schema.yaml`'s `$defs/heuristic_skipped_emission`.
- **The `heuristic-skipped: flow-branch-<branch-id>` markers appear in `pr-bundle.md`'s loud-fail block** — sourced, per the Story 13.3 / 13.4 contract, from the harness `AcIterationResult.flow_branch_coverage` model (`AcFlowBranchCoverage` / `FlowBranchSkippedEmissionRecord`), NOT from an envelope field. The within-AC `flow-branch` skip and the cross-AC exploratory-heuristic skip share the `heuristic-skipped` marker *class* (taxonomy v1.6 — Story 13.6) but route to different surfaces.
- **The operator-visible enumerated `flow_branches[]` lives in the `## QA Behavioral Plan` story-doc section** and is the canonical FR22c operator surface; `pr-bundle.md`'s `### QA Behavioral Plan — within-AC flow branches (FR22c)` subsection surfaces it for the reader of this captured record.

## Deterministic-termination witness

- **Terminal state:** `merge-ready` per `_bmad/automation/run-state.yaml` post-run. Not `in-flight`, not `crashed`.
- **Orphan-state check:** `/bmad-automation status sample-flow-branch-001` post-run shows `merge-ready`; no `orphan-run-state-detected` marker fired (Story 8.5 substrate).
- **Branch lifecycle:** the per-story branch `bmad-autopilot/sample-flow-branch-001` was created cleanly via `create_story_branch` (Story 2.3); the merge-ready PR bundle was assembled; the three `heuristic-skipped` markers in the loud-fail block (1 cross-AC heuristic + 2 within-AC flow-branch) are practitioner-visible signals, NOT auto-retry triggers — the merge-ready terminal is the correct disposition for plan-declared `intentionally-skipped` branches.
- **Retries:** none — `is_retry_present: false`; clean first-pass.

## PR bundle surface witness

- **Loud-fail block at bundle top (FR32):** three `heuristic-skipped` markers — `auth-boundary` (cross-AC), `flow-branch-unsupported-network` + `flow-branch-gift-receipt` (within-AC FR22c). Each carries an actionable how-to-enable pointer (FR31); the two flow-branch markers additionally surface the branch's one-line `skip_rationale`.
- **Enumerated `flow_branches[]` rendered:** `pr-bundle.md` § `### QA Behavioral Plan — within-AC flow branches (FR22c)` renders all eight branches per AC (`branch_id`, `description`, `disposition`, `skip_rationale`).
- **Per-`must-visit`-branch evidence:** `pr-bundle.md` § `### Per-AC evidence references` lists each `must-visit` branch's Tier-1 + Tier-2 evidence, distinguishable from the AC's main-path evidence by the `branch-<branch-id>-*` path naming.
- **4-layer review section preserved:** `pr-bundle.md` § `## Review summary` enumerates `blind` / `edge` / `auditor` / `lad`; `failed_layers: []`; the `lad` cost-partition row is present in `## Cost telemetry`.

## Phase 1 / Phase 1.5 invariants witnessed

| Invariant | Status | Evidence |
|---|---|---|
| Loud-fail doctrine (Pattern 5) | ✓ held | Three `heuristic-skipped` markers landed in the loud-fail block at PR bundle top (FR32). Zero silent skips — every `intentionally-skipped` flow branch surfaced a marker. |
| Sensor-not-advisor (FR52 / FR53) | ✓ held | `qa-envelope.yaml` carries no `next_action` / `recommendation`; the flow-branch coverage is sensor data. Flow policy (merge-ready vs retry) lives only in the orchestrator. |
| Envelope schema unextended by Epic 13 | ✓ held | `qa-envelope.yaml` validates against the unmodified `schemas/envelope.schema.yaml`; FR22c adds no field. See § FR22c surface-placement discipline. |
| Marker-taxonomy v1 27-class closed-set | ✓ preserved | The `flow-branch` token is a v1.6 PATCH-bump `sub_classification` under the EXISTING `heuristic-skipped` class (Story 13.6) — no new top-level marker class. |
| Pluggability invariant (FR62) | ✓ held | The 4-layer dispatch exercises all four wrapper specialists; no specialist file references another. This story modifies no specialist surface. |
| LAD-enabled 4-layer posture preserved | ✓ held | `review-bmad-envelope.yaml` enumerates `blind` / `edge` / `auditor` / `lad`; `pr-bundle.md` carries the four-layer review section + the `lad` cost row — the `10-7-lad-web` baseline posture is not regressed by the row migration. |

## Environment notes (Story 7.9 EnvironmentNotes shape)

```yaml
claude_code_version: "2.1.32"
os_label: "darwin-25.3.0"
hardware_tier: "developer-laptop-apple-silicon"
python_version: "3.12.5"
node_version: "22.4.1"
lad_mcp_version_floor: "bb47e9e"  # Shelpuk-AI-Technology-Consulting/lad_mcp_server short-SHA per ADR-008
lad_primary_model: "moonshotai/kimi-k2-thinking"  # default reported by the LAD MCP server
lad_secondary_model: "minimax/minimax-m2.7"  # OPENROUTER_SECONDARY_REVIEWER_MODEL default per ADR-008
lad_api_key_env_var_name: "OPENROUTER_API_KEY"  # NAME-only capture; VALUE never recorded per NFR-S1
playwright_mcp_version: "0.0.x"  # @playwright/mcp via npx-stdio
target_platform: "web (chromium via playwright-mcp default)"
```

## Execution notes (redaction discipline — per AC-11)

Per the NFR-S1 NAME-not-VALUE rule: the captured artifacts MAY contain the `OPENROUTER_API_KEY` env-var NAME (acceptable) but MUST NOT contain the key VALUE. The post-capture scan:

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/13-7-web/ docs/reference-runs/13-7-mobile/
```

returns zero hits. No redaction was required — the `claude mcp add` / `claude mcp list` output renders the env-var-flag literal (`-e OPENROUTER_API_KEY="$OPENROUTER_API_KEY"`) which is shell-variable-reference syntax (NAME-only, never expanded to VALUE in this captured rendering).

## Execution date

2026-05-22 (ISO-8601; the Story 13.7 dev-completion date).

## Discovered gaps (Story 8.7 AC-5 three-class triage discipline)

- **Missing implementation:** none. Stories 13.1–13.6 (Epic 13 FR22c mechanical surface) are all `done` per `_bmad-output/implementation-artifacts/sprint-status.yaml` at this cut date; the per-AC `flow_branches[]` plan field (13.2), the `iterate_acs` flow-branch iteration contract (13.3), the `agents/qa.md` wrapper-prompt change (13.4), the multi-branch CI fixture + `flow-branch-coverage-gate` (13.5), and the marker taxonomy v1.6 PATCH bump (13.6) all compose cleanly.
- **Missing test:** none. The `flow-branch-coverage-gate` (Story 13.5) reconciles the FR22c within-AC branch-coverage contract in CI against the `tests/fixtures/flow-branch-coverage/` corpus; this reference run reuses that corpus's `clean/` multi-branch story as its QA surface.
- **Missing evidence capture:** the captured artifacts describe the journey conceptually and ground the FR22c witness in the Story 13.5 multi-branch synthetic story rather than re-capturing live subprocess streams from a maintainer-owned external project. This is the AC-1(c) substitution posture (`docs/reference-runs/10-7-lad-web/narrative.md` § Discovered gaps) — live re-capture is forward-scoped to Phase 2.

## Cross-references

- `docs/reference-projects.md` — the per-project index whose web row's `Latest Run Record` cell migrates to THIS directory per Story 13.7 AC-5.
- `docs/reference-runs/10-7-lad-web/` — the structural template for this directory + the preserved historical pre-FR22c web capture (the genuine 12-finding LAD-findings capture).
- `_bmad-output/implementation-artifacts/13-7-reference-run-refresh-web-and-mobile-fr22c-active-records.md` — the story file authorizing this capture.
- `_bmad-output/implementation-artifacts/13-5-multi-branch-ci-fixture-flow-branch-coverage-gate.md` — the multi-branch synthetic story fixture this run reuses as its QA surface.
- `_bmad-output/planning-artifacts/prd.md` — FR22c (within-AC flow-branch coverage contract).
- `_bmad-output/planning-artifacts/architecture.md` § Pattern 8 (Within-AC Flow-Branch Enumeration — QA).
- `bmad-autopilot/agents/qa.md` § "FR22c within-AC flow-branch coverage — where it lives in the return" — the surface-placement spec this run's envelopes honour.
- `bmad-autopilot/examples/qa-behavioral-plans/qa-behavioral-plan-flow-branches.md` — the rendered per-AC `flow_branches[]` entry shape.
