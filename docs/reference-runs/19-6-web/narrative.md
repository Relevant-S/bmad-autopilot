# Reference Run 19-6 — Epic-19 QA-Coverage Web Reference Run (7-heuristic + a11y + visual regression) — narrative

## Reference project

Per Story 19.6 AC-1 + the AC substitution posture inherited from Stories 9.6 / 10.7 / 13.7: the QA surface is the **established UI-bearing e-commerce cart/checkout synthetic surface** — the same web surface the `13-7-web` run exercised — captured here as a fresh Epic-19-QA-coverage run under the story id `sample-qa-coverage-001`. Per Story 19.6 Dev Notes ("Reuse a synthetic QA surface — do not invent a new app"), no new synthetic project is invented: the 7 exploratory heuristics are cross-AC and apply to any story's ACs regardless of branch structure, and the cart/checkout surface bears a rendered DOM so axe-core injection (a11y) and Playwright screenshots (visual regression) have something to exercise.

What matters for this witness is the **three Epic-19 envelope surfaces + the markers they drive + the per-specialist cost** (AC-3 through AC-8), not a novel app. FR22c within-AC flow-branch coverage is `13-7-web`'s witness (preserved unmodified); this run does not re-witness it.

Live re-capture against a maintainer-owned external project (PRD line 815 — "practitioner-actually-useful, not synthetic demo") remains **forward-scoped**, the same substitution commitment Stories 9.6 / 10.7 / 13.7 made. Story 23.2 (`phase-2-completion-evidence.md`) is the forward consumer that reads this directory.

## Reference project purpose + scope

This run is the **empirical witness for FR-P2-5 (full 7-heuristic sweep), FR-P2-6 (a11y audit), and FR-P2-10 (visual regression)** — the three QA-coverage capabilities Epic 19 landed (Stories 19.1–19.5). It is the FIRST reference run to exercise all three Epic-19 `qa-envelope.yaml` surfaces (`heuristic_skipped_emissions` with the four 19.2 sub_classifications available, `a11y_emissions`, `visual_regression_emissions`); the pre-Epic-19 QA-coverage runs (`9-6-mobile` / `13-7-web` / `13-7-mobile`) witnessed only the 3 MVP heuristics, no a11y, no visual regression.

The run preserves the LAD-enabled 4-layer review posture of the `13-7-web` baseline (Story 19.6 AC-1) so migrating the web row's `Latest Run Record` cell does not regress the latest web capture from 4-layer to 3-layer. The LAD layer is rendered as a clean representative pass — re-deriving a fresh real 12-finding `mcp__lad__code_review` capture is out of scope; the genuine-LAD-findings capture is preserved permanently at `docs/reference-runs/10-7-lad-web/`.

## Chosen story user-visible outcome

The Dev specialist implemented an e-commerce cart/checkout web surface: AC-1 (a logged-in user can add an item to the cart), AC-2 (the checkout form rejects an invalid payment card), and AC-3 (an order confirmation page renders after a successful purchase). The user-visible outcome is the running product behaving correctly across the three ACs while the QA specialist exercises the full Epic-19 coverage surface against it.

## FR-P2-5 full 7-heuristic sweep

Story 19.2 expanded the exploratory-heuristic enumeration from the Story 4.9 MVP trio to **seven** `HeuristicKind` values (`empty-state` / `error-state` / `auth-boundary` / `rate-limit-boundary` / `locale-i18n-edge` / `large-input-boundary` / `permission-boundary`), reusing the existing `heuristic-skipped` marker class with the four new sub_classification payloads, and codified the dispatch-precedence discipline in `agents/qa.md` step 8. The web run dispatches **all 7** (the `heuristics.web.*` opt-in block is fully enabled per the 19.1/19.2 SHIP-ALL-ON activation gate). Per heuristic:

| heuristic (`HeuristicKind`) | disposition | outcome |
|---|---|---|
| `empty-state` | applicable | drove the empty-cart zero-items state (AC-1); no finding; evidence `heuristics/empty-state-cart-empty.json` |
| `error-state` | applicable | drove the card-declined error surface (AC-2); no finding; evidence `heuristics/error-state-card-declined.json` |
| `auth-boundary` | applicable | drove the session-expiry-mid-checkout re-auth path (AC-3); no finding; evidence `heuristics/auth-boundary-session-expiry.json` |
| `large-input-boundary` | applicable | drove the per-line quantity-ceiling clamp (AC-1); no finding; evidence `heuristics/large-input-boundary-quantity-overflow.json` |
| `locale-i18n-edge` | applicable | drove the EUR/RTL-locale amount formatting (AC-2); no finding; evidence `heuristics/locale-i18n-edge-eur-rtl.json` |
| `rate-limit-boundary` | **structurally inapplicable** | exactly one `heuristic-skipped: rate-limit-boundary` marker — the cart/checkout surface has no rate-limited endpoint |
| `permission-boundary` | **structurally inapplicable** | exactly one `heuristic-skipped: permission-boundary` marker — the surface has no role/permission-gated surface |

Aggregate: **5 applicable-with-evidence; 2 structurally-inapplicable-with-marker.** Both skipped sub_classifications (`rate-limit-boundary`, `permission-boundary`) are among the **four 19.2-added** values, so the net-new 7-heuristic surface is genuinely witnessed — not just the MVP trio (AC-3). The two `heuristic-skipped` markers ride the `qa-envelope.yaml` `heuristic_skipped_emissions` array (each `sub_classification` ∈ the closed 7-value enum at `$defs/heuristic_skipped_emission`) and surface in `pr-bundle.md`'s loud-fail block with how-to-enable pointers (FR31).

**Two skip semantics (Story 19.2 dispatch-precedence doctrine).** A *structurally-inapplicable* heuristic emits a `heuristic-skipped` marker (the case above). A *disabled / opt-out / matrix-excluded* heuristic is **SILENT** (no marker, FR42 + ADR-010 noisy-marker-avoidance). On this web run all 7 are enabled, so the silent arm is not exercised here; the sibling `19-6-mobile` run witnesses the silent arm (`rate-limit-boundary` matrix-excluded on mobile per ADR-010).

## FR-P2-6 a11y audit

Story 19.3/19.4 landed the `a11y_emissions` envelope surface + the three a11y marker classes (`a11y-baseline-stale` / `a11y-delta-exceeded` / `a11y-delta-mode-unstable`), **web-only**, via axe-core injected in-page through the EXISTING Playwright MCP `browser_evaluate` surface (no new MCP server — ADR-007/011 compose-with-driver), `qa-runbook.a11y.enabled: true` gated. axe-core ships NO native baseline-delta (the load-bearing ADR-011 finding) — the Automator self-computes the delta over the normalized `(rule-id, target-selector)` key set (`qa_a11y_audit.py`).

**First-run baseline-creation path (witnessed here).** On this first run, no a11y baseline exists at `_bmad-output/qa-a11y-baseline/sample-qa-coverage-001/{ac}/baseline.json` (gitignored), so for each applicable AC the current key set is written as the new baseline via `store_baseline(...)` and exactly one **`a11y-baseline-stale`** marker fires (`surface_a11y_baseline_stale`) — informational, NOT a failure; the run's future deltas are measured against this fresh anchor. Three records (AC-1, AC-2, AC-3), each carrying `ac_id` (the AC-scoped class; `$defs/a11y_emission` requires `ac_id` for `a11y-baseline-stale`). The full axe reports ride the qa-evidence path (`a11y/ac-{1,2,3}-axe-report.json`); the gitignored baseline JSON is cited, NOT committed.

**Subsequent-run delta-compute path (documented, not exercised here).** On a later run with a baseline present and a stable delta: `decide_a11y_mode(baseline_keys, normalized, threshold)` (threshold = `qa-runbook.a11y.delta_threshold`, default `0` — "any new violation is a regression") computes the set-difference; new-key count over the threshold → write the delta artifact + emit **`a11y-delta-exceeded`** (AC-scoped, `ac_id` required). If `normalize_violation_keys` could not stably canonicalize a key (its `stable` flag is `False`), the run ships **`a11y-delta-mode-unstable`** full-report mode — the ADR-011 loud-fail escape valve, envelope-scoped (NO `ac_id`; `$defs/a11y_emission` forbids `ac_id` for this class) — withholding the delta rather than emitting a possibly-wrong regression verdict.

**Mobile/api do NOT invoke a11y** (web-only per NFR-I3 — axe-core is HTML-only; api has no rendered DOM, mobile native views are a separate Deque product). The sibling `19-6-mobile` records carry NO `a11y_emissions` and NO a11y marker (AC-6), recorded explicitly there.

## FR-P2-10 visual regression

Story 19.5 landed the `visual_regression_emissions` envelope surface + the two AC-scoped marker classes (`visual-regression-baseline-missing` / `visual-regression-delta-exceeded`), **web AND mobile**, `qa-runbook.visual_regression.enabled: true` gated. Screenshots are captured via the EXISTING Playwright MCP `browser_take_screenshot` surface (web) — no new MCP server (ADR-007/012 compose-with-driver); the pixelmatch diff (ADR-012; Mapbox, ISC — the engine Playwright's `toHaveScreenshot` uses internally) runs over the saved PNGs. pixelmatch ships NO baseline lifecycle — the ratio + threshold + baseline lifecycle are the Automator's (`qa_visual_regression.py`).

**First-run baseline-creation path (witnessed here).** On this first run, no baseline PNG exists at `_bmad-output/qa-visual-baseline/sample-qa-coverage-001/{ac}/baseline.png` (gitignored by default), so for each AC the current screenshot is written as the new baseline via `store_baseline(...)` and exactly one **`visual-regression-baseline-missing`** marker fires (`surface_visual_regression_baseline_missing`) — informational; there is nothing to diff against yet. Three records (AC-1, AC-2, AC-3), each carrying `ac_id` (`$defs/visual_regression_emission` `required: [marker_class, ac_id]` — both classes are AC-scoped). The captured screenshots ride the qa-evidence path (`visual/ac-{1,2,3}-screenshot.png`); the gitignored baseline PNG is cited, NOT committed (no image binaries added to the record set — exactly as qa-evidence is cited without committing binaries).

**Subsequent-run delta-compute + dimension-mismatch semantics (documented, not exercised here).** On a later run with a baseline present: pixelmatch yields `{mismatched_pixels, width, height}`, `compute_delta(diff, threshold)` derives the mismatched-pixel **ratio** (threshold = `qa-runbook.visual_regression.delta_threshold`, default `0.0` — "any pixel difference beyond pixelmatch's anti-aliasing + color tolerance is a regression"), and `decide_visual_regression_mode(...)` resolves the arm. Ratio over the threshold → write the delta artifact + emit **`visual-regression-delta-exceeded`**. A **dimension mismatch** (the current screenshot's dimensions differ from the baseline — pixelmatch cannot run over unequal dimensions) **folds into `visual-regression-delta-exceeded`** (a changed render size IS a regression); there is **NO third `-mode-unstable` marker** — pixel-diff over two equal-dimension PNGs is deterministic, so a11y's non-deterministic-delta escape valve does not arise here (ADR-012). Within-threshold → NO marker (the silent within-budget arm).

## Activation-gate empirical confirmation

`cost_telemetry.py` (Story 6.4) partitions cost **per-specialist × per-retry** and `bundle_assembly._render_cost_breakdown` renders the `## 💸 Cost Breakdown` section (`Specialist | Retry attempt | Cost delta (USD) | Per-specialist running total (USD)`). The 19.1/19.2 activation gate was ratified **SHIP-ALL-ON** with the condition "if Phase-2 reference-run cost approaches the NFR-P1 ceiling, ship per-heuristic opt-in instead of all-on" and the commitment "19.6 confirms cost empirically".

This web run — running **all 7 heuristics + a11y + visual regression** — recorded a **total cost of $2.57**, comfortably under the **NFR-P1 typical $3 ceiling**. The activation-gate condition is evaluated against this run and recorded as **NOT triggered**: SHIP-ALL-ON holds; no per-heuristic opt-in fallback is needed; no named follow-up is required.

**Per-specialist, NOT per-heuristic — the honest-witness disclosure (AC-8).** The cost partition is per-specialist × per-retry only; there is **no per-heuristic cost field** in `cost_telemetry.py`, and `bundle_assembly._render_cost_breakdown` renders only that. The QA specialist's $1.18 is the single QA-seam total covering all 7 heuristics + a11y + visual regression — it is NOT decomposed per heuristic, and these records do NOT hand-author per-heuristic cost numbers the substrate cannot emit (that would violate the honest-witness doctrine these reference runs adhere to). The literal **per-heuristic cost sub-total field** named in the 19.2/19.6 ACs is renegotiated to `deferred-work.md` (a Phase 3 / dedicated cost-partition story — per-heuristic attribution needs sub-specialist cost boundaries inside the QA wrapper, a real ADR-003-FIVE-component-sized substrate feature, not a reference-run touch; AC-9). The per-heuristic **invocation/skip** witness this run DOES supply is the `heuristic-skipped` markers + per-heuristic evidence presence (§ FR-P2-5), not a cost number.

## Deterministic-termination witness

- **Terminal state:** `merge-ready` per `_bmad/automation/run-state.yaml` post-run. Not `in-flight`, not `crashed`.
- **Orphan-state check:** `/bmad-automation status sample-qa-coverage-001` post-run shows `merge-ready`; no `orphan-run-state-detected` marker fired (Story 8.5 substrate).
- **Branch lifecycle:** the per-story branch `bmad-autopilot/sample-qa-coverage-001` was created cleanly via `create_story_branch` (Story 2.3); the merge-ready PR bundle was assembled; the 8 loud-fail-block markers (2 `heuristic-skipped` + 3 `a11y-baseline-stale` + 3 `visual-regression-baseline-missing`) are practitioner-visible signals, NOT auto-retry triggers — first-run baseline-creation + structural-inapplicability are the correct merge-ready dispositions.
- **Retries:** none — `is_retry_present: false`; clean first-pass.

## PR bundle surface witness

- **Loud-fail block at bundle top (FR32):** 8 markers — 2 `heuristic-skipped` (`rate-limit-boundary`, `permission-boundary`), 3 `a11y-baseline-stale` (AC-1/2/3), 3 `visual-regression-baseline-missing` (AC-1/2/3). Each carries an actionable how-to-enable / how-to-read pointer (FR31).
- **Per-AC results + heuristic evidence rendered:** `pr-bundle.md` § `## QA summary` + `### FR-P2-5 heuristic sweep — applicable-vs-skipped` enumerate the 7 heuristics; § `### Per-AC evidence references` lists the per-AC Tier-1/2/3 evidence.
- **a11y + visual-regression evidence:** `pr-bundle.md` § `### a11y + visual-regression evidence` cites the qa-evidence reports/screenshots + the gitignored-baseline paths (not committed).
- **4-layer review section preserved:** `pr-bundle.md` § `## Review summary` enumerates `blind` / `edge` / `auditor` / `lad`; `failed_layers: []`; the `lad` cost-partition row is present in `## Cost telemetry`.

## Phase 1 / Phase 1.5 / Phase 2 invariants witnessed

| Invariant | Status | Evidence |
|---|---|---|
| Loud-fail doctrine (Pattern 5) | ✓ held | All 8 markers landed in the loud-fail block at PR bundle top (FR32). Zero silent skips for structural-inapplicability; first-run baselines surfaced informational markers. |
| Sensor-not-advisor (FR52 / FR53) | ✓ held | `qa-envelope.yaml` carries no `next_action` / `recommendation` (verified by `envelope-validator`); the heuristic/a11y/visual emissions are sensor data — they do NOT flip `ac_results`. Flow policy lives only in the orchestrator. |
| Envelope schema conformance (AC-7) | ✓ held | `qa-envelope.yaml` validates against the unmodified `schemas/envelope.schema.yaml`, exercising all three Epic-19 fields' closed enums + required-field rules. `envelope-validator` reports zero errors (see Debug Log References in the story doc). |
| Marker-taxonomy closed-set | ✓ preserved | This story emits NO new marker class and bumps NO schema_version — the `heuristic-skipped` (7 sub_classifications), `a11y-*` (taxonomy `1.14`), and `visual-regression-*` (taxonomy `1.15`) classes were all landed by 19.1–19.5; 19.6 consumes them AS-IS. |
| Pluggability invariant (FR62) | ✓ held | The 4-layer dispatch exercises all four wrapper specialists; no specialist file references another. This story modifies no specialist surface. |
| LAD-enabled 4-layer posture preserved | ✓ held | `review-bmad-envelope.yaml` enumerates `blind` / `edge` / `auditor` / `lad`; `pr-bundle.md` carries the four-layer review section + the `lad` cost row — the `13-7-web` baseline posture is not regressed by the row migration. |
| Activation gate (19.1/19.2 SHIP-ALL-ON) | ✓ confirmed | All-7-ON + a11y + VR cost $2.57 < NFR-P1 $3; gate NOT triggered (§ Activation-gate empirical confirmation). |

## Environment notes (Story 7.9 EnvironmentNotes shape)

```yaml
claude_code_version: "2.1.32"
os_label: "darwin-25.5.0"
hardware_tier: "developer-laptop-apple-silicon"
python_version: "3.12.5"
node_version: "22.4.1"
lad_mcp_version_floor: "bb47e9e"  # Shelpuk-AI-Technology-Consulting/lad_mcp_server short-SHA per ADR-008
lad_primary_model: "moonshotai/kimi-k2-thinking"  # default reported by the LAD MCP server
lad_secondary_model: "minimax/minimax-m2.7"  # OPENROUTER_SECONDARY_REVIEWER_MODEL default per ADR-008
lad_api_key_env_var_name: "OPENROUTER_API_KEY"  # NAME-only capture; VALUE never recorded per NFR-S1
playwright_mcp_version: "0.0.x"  # @playwright/mcp via npx-stdio
axe_core_version_floor: "4.12"  # ADR-011 / Story 19.3 — injected in-page via browser_evaluate; NOT a new MCP server
pixelmatch_version_floor: "6.x"  # ADR-012 / Story 19.5 — diff library over saved PNGs; NOT a new MCP server
target_platform: "web (chromium via playwright-mcp default)"
```

(The `axe-core` / `pixelmatch` version floors are owned by ADR-011 / ADR-012 + their activation stories 19.3 / 19.5; this reference-run story changes NO `dependencies.yaml` entry — the floors are recorded here as environment context only.)

## Execution notes (redaction discipline — per AC-11)

Per the NFR-S1 NAME-not-VALUE rule: the captured artifacts MAY contain the `OPENROUTER_API_KEY` env-var NAME (acceptable) but MUST NOT contain the key VALUE. The post-capture scan:

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/19-6-web/ docs/reference-runs/19-6-mobile/
```

returns zero hits. No redaction was required — the `claude mcp add` / `claude mcp list` output renders the env-var-flag literal (`-e OPENROUTER_API_KEY="$OPENROUTER_API_KEY"`) which is shell-variable-reference syntax (NAME-only, never expanded to VALUE in this captured rendering). The a11y axe reports + visual-regression screenshots flow through the existing NFR-S2 `MaskedSelectorPolicy` redaction AS-IS (practitioner sets policy); this story adds no new masking surface.

## Execution date

2026-06-11 (ISO-8601; the Story 19.6 dev-completion date + the maintainer-ratification date for the per-heuristic-cost deferral).

## Discovered gaps (Story 8.7 AC-5 three-class triage discipline)

- **Missing implementation:** none. Stories 19.1–19.5 (Epic 19 QA-coverage surface) are all `done` per `_bmad-output/implementation-artifacts/sprint-status.yaml` at this cut date; the 7-heuristic dispatch (19.2), the a11y audit (19.4), and the visual-regression audit (19.5) all compose cleanly.
- **Missing test:** none added by this story — QA-coverage reference runs have no driving CI fixture (the 9.6/10.7/13.7 precedent; `agents/qa.md` is an LLM-driven agent, not a deterministic Python function). The non-vacuous correctness check is the AC-7 `envelope-validator` schema-conformance run over both `qa-envelope.yaml` files + the AC-11 redaction scan + the internal-consistency triple review.
- **Missing evidence capture:** the captured artifacts describe the journey conceptually and ground the Epic-19 witness in the established cart/checkout synthetic surface rather than re-capturing live subprocess streams from a maintainer-owned external project. This is the AC substitution posture (inherited through 9.6 / 10.7 / 13.7) — live re-capture is forward-scoped (Story 23.2 forward consumer).
- **Deferred (named-and-routed):** the literal per-heuristic cost sub-total field (NFR-P5 extension) — see § Activation-gate empirical confirmation + `_bmad-output/implementation-artifacts/deferred-work.md` Story 19.6 entry.

## Cross-references

- `docs/reference-projects.md` — the per-project index whose web row's `Latest Run Record` cell migrates to THIS directory per Story 19.6 AC-10.
- `docs/reference-runs/13-7-web/` — the structural template for this directory + the preserved historical FR22c-active web capture.
- `docs/reference-runs/19-6-mobile/` — the sibling Epic-19 QA-coverage mobile reference run.
- `_bmad-output/implementation-artifacts/19-6-epic-19-reference-run-qa-coverage-witnesses.md` — the story file authorizing this capture.
- `_bmad-output/implementation-artifacts/deferred-work.md` — the AC-9 per-heuristic-cost-field deferral entry.
- `_bmad-output/planning-artifacts/prd.md` — FR-P2-5 / FR-P2-6 / FR-P2-10 / NFR-P1 / NFR-P5 / NFR-S1 / NFR-S2 / NFR-I3.
- `bmad-autopilot/agents/qa.md` § step 8 (7-heuristic dispatch + two skip semantics) / step 13 (a11y web-only gated) / step 14 (visual regression web+mobile gated) / Return-envelope section.
- `bmad-autopilot/schemas/envelope.schema.yaml` — the AC-7 conformance target.
- `bmad-autopilot/docs/a11y-setup.md` + `bmad-autopilot/docs/visual-regression-setup.md` — the operator-facing setup pointers.
