# A11y Audit Setup

Operator-facing setup guide for the accessibility (a11y) audit the BMAD Agent Development Automator runs via the QA specialist on `project_type: web` BMAD projects (Phase 2 — FR-P2-6 / ADR-011, see `_bmad-output/planning-artifacts/architecture.md` ADR-011).

The a11y audit is **opt-in, web-only, and default-deferred**: it runs only when BOTH gates hold — `project_type == web` AND `_bmad/automation/qa-runbook.yaml` carries `a11y.enabled: true`. On `project_type: api|mobile`, on `a11y.enabled: false`, and on the unconfigured default, the audit is a **silent skip** (no audit, no `a11y-*` marker — the opt-in-skip posture, mirroring `masked_selectors`). axe-core is HTML-only (Deque FAQ); `api` has no rendered DOM and native mobile views are a separate Deque product, so neither invokes.

This guide covers: installing axe-core, enabling the runbook block, where baselines are stored, how to re-anchor a baseline, and how to read the delta / full-report evidence.

## Prerequisites

The a11y audit composes with the EXISTING Playwright MCP browser surface the `web` QA driver already drives (per ADR-007 / ADR-011 — "compose with the existing driver, don't branch"). It does NOT spin up a second browser (the Pa11y / Lighthouse rejection in ADR-011) and does NOT introduce a new MCP server (the standalone-a11y-MCP rejection). The operator-side prerequisites:

- **A working `web` QA loop.** The Playwright MCP must already be installed and driving the running product (the same surface `playwright_driver` uses for `verify_ac`). If web QA runs, the a11y audit's injection path is already present.
- **node.js** with `npm` on `$PATH` (to install the axe-core engine bundle).

## Install axe-core

The accessibility engine is the **axe-core** package (Deque, MPL-2.0 licensed; GitHub `dequelabs/axe-core`). Install it at the project root:

```
npm install axe-core
```

This ships `node_modules/axe-core/axe.min.js` — the engine bundle the audit injects into the page under test. Do **NOT** install `@axe-core/playwright`: that is the `@playwright/test`-runner adapter (`AxeBuilder({ page }).analyze()`), which is NOT required here — the wrapper injects the engine (`axe.min.js`) through the Playwright MCP `browser_evaluate` surface it already drives, then calls `axe.run()` in-page.

The `version_floor` is `4.12` (pinned in `schemas/dependencies.yaml` per Story 19.3; `4.12.1` verified at activation). axe-core is an `opt-in-skip` dependency: its absence does NOT block `init` — the audit simply does not run until the engine is installed AND the runbook block is enabled.

## Enable the runbook block

Open `_bmad/automation/qa-runbook.yaml` at the project root and uncomment the `a11y:` worked-example block (it ships commented-out — the default-defer posture). The minimal enablement:

```yaml
a11y:
  enabled: true
  delta_threshold: 0
  scope: per-ac
```

- `enabled: true|false` — the master gate. `false` (or the block absent) is a silent skip.
- `delta_threshold: <int>` — the count of newly-introduced violation keys (beyond the baseline) tolerated before the `a11y-delta-exceeded` marker fires. Default `0` means "any new violation is a regression" — the strictest, most defensible default.
- `scope: per-ac|per-story` — `per-ac` (default) runs one `axe.run()` per AC against that AC's verified surface, with one baseline per `(story, ac)`. `per-story` collapses to a single whole-story audit + baseline.

ABSENCE of the block is NOT a marker (FR42 user-owned file — absence means "a11y audit deferred"), explicitly stated in the block's comment header.

## How the audit runs

On the web opt-in path, for each AC (or once per story under `scope: per-story`), the QA wrapper:

1. injects `axe.min.js` into the running page via the Playwright MCP `browser_evaluate` surface and calls `axe.run()` (resolving to `{ violations[], passes[], incomplete[], inapplicable[], testEngine, ... }`);
2. persists the **full axe-core report** as a Tier-1/Tier-2 evidence artifact under the canonical run-scoped path `_bmad-output/qa-evidence/{story-id}/{run-id}/` (subject to the NFR-P6 size-budget + `evidence-truncated` machinery AS-IS, and the same `MaskedSelectorPolicy` redaction the `web` driver applies at evidence-write time per NFR-S2);
3. normalizes each violation to a stable `(rule-id, target-selector)` key (handling the `target` string / iframe-path / shadow-DOM-array shapes per the Deque API);
4. loads-or-creates the per-AC baseline and computes the self-computed set-difference delta.

The a11y delta is **story-level evidence, not an AC gate** (sensor-not-advisor): a fired `a11y-delta-exceeded` marker surfaces the regression for the human; it does NOT flip the AC's pass/fail verdict (which stays the mechanical-assertion outcome), exactly as exploratory-heuristic findings do not flip AC status. The orchestrator's flow policy — not the QA wrapper — decides what a fired marker means.

## Baseline storage + re-anchoring

Per-AC baselines are stored as plain JSON (the normalized violation-key set) under:

```
_bmad-output/qa-a11y-baseline/{story-id}/{ac-id}/baseline.json
```

This tree is **gitignored** (mirroring the `qa-evidence` precedent) — it is practitioner-local longitudinal signal, not committed history. Inspect a baseline directly (it is plain sorted JSON per NFR-O2).

- **First run for an AC** (no prior baseline): the current `axe.run()` violation set is written as the new baseline AND the informational `a11y-baseline-stale` marker fires (NOT a failure — the run's delta is measured against this fresh anchor).
- **Re-anchor a baseline intentionally** (manual-delete only — there is no `force_reanchor` runbook config field): delete the stored `baseline.json` for that `(story, ac)`. The next run treats the AC as having no prior baseline, writes a fresh anchor, and emits `a11y-baseline-stale`. Use this after you have triaged and accepted a set of violations as the new known-good state.

## Reading the evidence

Three markers can surface on the QA envelope's `a11y_emissions` array; the PR bundle renders each as a `<!-- bmad-automation:marker a11y-* -->` comment with a diagnostic pointer:

- **`a11y-baseline-stale`** (informational, AC-scoped) — a new baseline was anchored for this AC. No action required for a genuinely new baseline; if the anchor is unexpectedly new, confirm the prior baseline artifact was not lost or relocated before trusting the run's delta.
- **`a11y-delta-exceeded`** (AC-scoped) — the self-computed delta exceeded `delta_threshold`. The marker's `diagnostic_pointer` directs you to the **delta evidence artifact** (the new-violations set + the baseline-vs-current diff) under the run-scoped qa-evidence path. Triage the newly-introduced violations against the baseline, then fix the regression or re-anchor the baseline intentionally.
- **`a11y-delta-mode-unstable`** (envelope-scoped, no `ac_id`) — the FALLBACK: the self-computed delta could not be produced reliably (a violation key could not be stably canonicalized), so the audit shipped **full-report mode (no delta)** rather than a possibly-wrong regression verdict. The full axe-core report is still captured as evidence — read it directly. This is the ADR-011 loud-fail escape valve; if it recurs across Phase-2 reference runs (the Story 19.6 signal), ADR-011's revisit condition fires (make full-report the default).

The **full axe-core report** is always captured as evidence regardless of which delta marker (if any) fired — read it under `_bmad-output/qa-evidence/{story-id}/{run-id}/` for the complete `violations[]` detail (rule id, impact, help URL, the offending nodes' HTML + selectors).

## Cross-references

- ADR-011 — `_bmad-output/planning-artifacts/architecture.md`. The source-of-truth for the axe-core tool choice (Deque, MPL-2.0, `version_floor "4.12"`), the in-page-via-existing-Playwright-MCP injection decision (no new MCP server), the split baseline-delta verdict (axe-core output mature/diffable but NO native baseline-delta → the Automator self-computes the delta), the `a11y-delta-mode-unstable` full-report fallback, and the rejected alternatives (standalone-a11y-MCP / Pa11y / Lighthouse / Chromatic-SaaS).
- ADR-007 — "compose with the existing driver, don't branch" (the in-page injection logic).
- `schemas/dependencies.yaml` — the canonical `axe-core` dependency declaration (`opt-in-skip`, `version_floor "4.12"`; Story 19.3).
- `schemas/marker-taxonomy.yaml` — the three a11y evidence marker classes (`a11y-baseline-stale` / `a11y-delta-exceeded` / `a11y-delta-mode-unstable`; schema_version `1.14`) and their `diagnostic_pointer` / `pointer_context_fields`.
- `schemas/envelope.schema.yaml` — the `a11y_emissions` array + `$defs/a11y_emission` the QA wrapper rides the records on.
- `agents/qa.md` — the QA specialist wrapper carrying the web-only + opt-in-gated a11y-audit procedure step.
