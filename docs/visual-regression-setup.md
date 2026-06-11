# Visual Regression Setup

Operator-facing setup guide for the visual-regression snapshotting audit the BMAD Agent Development Automator runs via the QA specialist on `project_type: web` and `project_type: mobile` BMAD projects (Phase 2 — FR-P2-10 / ADR-012, see `_bmad-output/planning-artifacts/architecture.md` ADR-012).

The visual-regression audit is **opt-in, web-AND-mobile, and default-deferred**: it runs only when BOTH gates hold — `project_type ∈ {web, mobile}` AND `_bmad/automation/qa-runbook.yaml` carries `visual_regression.enabled: true`. On `project_type: api` (no UI to capture), on `visual_regression.enabled: false`, and on the unconfigured default, the audit is a **silent skip** (no audit, no `visual-regression-*` marker — the opt-in-skip posture, mirroring `masked_selectors`).

This guide covers: installing pixelmatch, enabling the runbook block, where baselines are stored, how to re-anchor a baseline, the gitignored-vs-committed baseline choice, how to read the diff artifact + the two markers, and a Troubleshooting section.

## Prerequisites

The visual-regression audit composes with the EXISTING MCP surfaces the QA driver already drives (per ADR-007 / ADR-012 — "compose with the existing driver, don't branch"). It does NOT spin up a second browser, and does NOT introduce a new MCP server. The diff runs over two saved PNG files — a path uniform across web AND mobile (this is why the file-based diff is chosen over a11y's web-only in-page injection: mobile has no `browser_evaluate` surface). The operator-side prerequisites:

- **A working `web` or `mobile` QA loop.** For `web`, the Playwright MCP must already be driving the running product (the same surface `playwright_driver` uses for `verify_ac`, exposing `browser_take_screenshot`). For `mobile`, the mobile-MCP must already be driving the connected device (Story 9.3; exposing `mobile_take_screenshot` / `mobile_save_screenshot`). If the project-type QA loop runs, the screenshot-capture path is already present.
- **node.js** with `npm` on `$PATH` (to install the diff engine).

## Install pixelmatch

The diff engine is the **pixelmatch** package (Mapbox, ISC-licensed; GitHub `mapbox/pixelmatch`) — the de-facto open-source pixel-comparison engine that powers Playwright's own `toHaveScreenshot`, jest-image-snapshot, and cypress-image-snapshot. Its PNG-decode companion **pngjs** decodes the saved screenshots into the pixel buffers pixelmatch compares. Install both at the project root:

```
npm install pixelmatch pngjs
```

The `version_floor` is `7.2` (pinned in `schemas/dependencies.yaml` per Story 19.5; `7.2.0` verified at activation via `npm view pixelmatch version`). pixelmatch is an `opt-in-skip` dependency: its absence does NOT block `init` — the audit simply does not run until the engine is installed AND the runbook block is enabled.

## Enable the runbook block

Open `_bmad/automation/qa-runbook.yaml` at the project root and uncomment the `visual_regression:` worked-example block (it ships commented-out — the default-defer posture). The minimal enablement:

```yaml
visual_regression:
  enabled: true
  delta_threshold: 0
  scope: per-ac
  baseline_storage: gitignored
```

- `enabled: true|false` — the master gate. `false` (or the block absent) is a silent skip.
- `delta_threshold: <float>` — the mismatched-pixel **ratio** (0.0–1.0) tolerated before the `visual-regression-delta-exceeded` marker fires. Default `0` means "any pixel difference beyond pixelmatch's anti-aliasing + color tolerance is a regression" — the strictest, most defensible default. (pixelmatch's internal per-pixel color threshold + anti-aliasing detection absorb sub-perceptual rendering noise, so the ratio-level threshold can stay strict.)
- `scope: per-ac|per-story` — `per-ac` (default) captures one screenshot per AC against that AC's verified surface, with one baseline per `(story, ac)`. `per-story` collapses to a single whole-story snapshot + baseline.
- `baseline_storage: gitignored|committed` — see "Baseline storage" below. Default `gitignored`.

ABSENCE of the block is NOT a marker (FR42 user-owned file — absence means "visual-regression audit deferred"), explicitly stated in the block's comment header.

## How the audit runs

On the web/mobile opt-in path, for each AC (or once per story under `scope: per-story`), the QA wrapper:

1. captures the current screenshot via the EXISTING per-`project_type` MCP surface — `browser_take_screenshot` (web) through the Playwright MCP, or `mobile_take_screenshot` / `mobile_save_screenshot` (mobile) through the mobile-MCP;
2. persists it under the canonical run-scoped path `_bmad-output/qa-evidence/{story-id}/{run-id}/` (subject to the NFR-P6 size-budget + `evidence-truncated` machinery AS-IS, and the same `MaskedSelectorPolicy` redaction the driver applies at evidence-write time per NFR-S2 — visual evidence adds NO new masking surface);
3. loads-or-creates the per-AC baseline via `qa_visual_regression.py`;
4. runs pixelmatch over the two saved PNGs (baseline + current) and computes the self-computed mismatched-pixel ratio (`mismatched_pixels / total_pixels`).

pixelmatch ships **no baseline lifecycle** (it returns only a raw mismatched-pixel count for one comparison — the load-bearing ADR-012 finding); the Automator owns the baseline load/create, the ratio, the threshold, and the marker. The visual delta is **story-level evidence, not an AC gate** (sensor-not-advisor): a fired `visual-regression-delta-exceeded` marker surfaces the regression for the human; it does NOT flip the AC's pass/fail verdict (which stays the mechanical-assertion outcome), exactly as a11y and exploratory-heuristic findings do not flip AC status. The orchestrator's flow policy — not the QA wrapper — decides what a fired marker means.

## Baseline storage + re-anchoring

Per-AC baselines are stored as PNG images under:

```
_bmad-output/qa-visual-baseline/{story-id}/{ac-id}/baseline.png
```

- **`gitignored` (default)** — this tree is gitignored (mirroring the `qa-evidence` / `qa-a11y-baseline` precedent): practitioner-local longitudinal signal, not committed history.
- **`committed`** — set `baseline_storage: committed` to curate baselines in-repo. Visual baselines are images a team may legitimately want to commit and review (unlike a11y's JSON key set), so the committed option is first-class. When `committed`, you are responsible for adding the `baseline.png` files to version control (the default `.gitignore` entry covers the tree only for the gitignored posture).

Re-anchoring is **manual-delete only — there is no `force_reanchor` runbook config field**:

- **First run for an AC** (no prior baseline): the current screenshot is written as the new baseline AND the informational `visual-regression-baseline-missing` marker fires (NOT a failure — there is nothing to compare against yet).
- **Re-anchor a baseline intentionally**: delete the stored `baseline.png` for that `(story, ac)`. The next run treats the AC as having no prior baseline, writes a fresh anchor, and emits `visual-regression-baseline-missing`. Use this after you have triaged and accepted a changed render as the new known-good state.

## Reading the evidence

Two markers can surface on the QA envelope's `visual_regression_emissions` array; the PR bundle renders each as a `<!-- bmad-automation:marker visual-regression-* -->` comment with a diagnostic pointer:

- **`visual-regression-baseline-missing`** (informational, AC-scoped) — a new baseline was anchored for this AC. No action required for a genuinely new baseline; if the anchor is unexpectedly new, confirm the prior baseline was not lost or relocated before trusting subsequent deltas.
- **`visual-regression-delta-exceeded`** (AC-scoped) — the self-computed mismatched-pixel ratio exceeded `delta_threshold`, OR the baseline and current dimensions differed (a changed render size, which pixelmatch cannot diff over unequal dimensions — folded into this marker as a regression). The marker's `diagnostic_pointer` directs you to the **diff evidence artifact** (the diff PNG highlighting the changed pixels + the ratio / counts / dimensions) under the run-scoped qa-evidence path. Triage the changed region, then fix the regression or re-anchor the baseline intentionally.

There is no third `-mode-unstable` marker: pixel-diff over two equal-dimension PNGs is deterministic, so the non-deterministic-delta escape valve a11y needed does not arise here.

## Troubleshooting

- **The audit never runs / no marker ever fires.** Check BOTH gates: `project_type` must be `web` or `mobile` (NOT `api` — there is no UI to capture), AND `visual_regression.enabled` must be `true` with the block uncommented. Absence of the block, `enabled: false`, and `project_type: api` are all SILENT skips by design (no marker — the opt-in-skip posture).
- **`visual-regression-delta-exceeded` fires on every run with no real change.** The most common cause is dynamic content (timestamps, animations, randomized data, anti-aliasing on a different GPU). pixelmatch's per-pixel color threshold + anti-aliasing detection absorb sub-perceptual noise, but genuinely dynamic regions will diff. Triage the diff PNG to confirm; if the change is expected, re-anchor the baseline (delete `baseline.png`). If a systematic dynamic-content false-positive rate emerges across runs, that is the ADR-012 revisit-condition signal (it would justify adding perceptual/SSIM scoring or per-AC ignore-regions — out of scope for this opt-in substrate).
- **`visual-regression-delta-exceeded` fires and the artifact shows `dimension_mismatch: true`.** The current screenshot's dimensions differ from the baseline's (e.g. a viewport/orientation change, or a layout that changed the page height). pixelmatch cannot diff unequal dimensions, so the Automator folds a changed render size into `delta-exceeded` (the strictest defensible interpretation). If the new size is intended, re-anchor the baseline.
- **Every run emits `visual-regression-baseline-missing`.** The baseline is not being found between runs. If `baseline_storage: gitignored`, baselines are local-only — a fresh checkout / CI runner starts with no baseline (expected). If you need baselines to persist across machines, use `baseline_storage: committed` and commit the `baseline.png` files. Also confirm the baseline file is a valid PNG: a corrupt / truncated / non-PNG file is treated as absent (the safe fresh-anchor path), so a broken baseline will re-emit `baseline-missing` every run.
- **`pixelmatch: command not found` / engine missing.** Run `npm install pixelmatch pngjs` at the project root. pixelmatch is `opt-in-skip`, so its absence does not block `init` — but the audit cannot run until it is installed.

## Cross-references

- ADR-012 — `_bmad-output/planning-artifacts/architecture.md`. The source-of-truth for the pixelmatch tool choice (Mapbox, ISC, `version_floor "7.2"`), the pixel-delta (mismatched-pixel ratio) vs perceptual-delta (SSIM) decision, the capture-via-existing-Playwright/mobile-MCP decision (no new MCP server), the Automator-owned baseline-delta finding (pixelmatch has none), the dimension-mismatch fold (no third marker), and the rejected alternatives (odiff / ImageMagick / Honeydiff / Chromatic-Percy-Applitools-SaaS / SSIM).
- ADR-007 — "compose with the existing driver, don't branch" (the existing-MCP-surface capture logic).
- ADR-011 — the a11y tool-selection ADR; the immediate twin (same Automator-owned-delta finding, same compose-with-driver logic, same SaaS-cell-1 rejection).
- `schemas/dependencies.yaml` — the canonical `pixelmatch` dependency declaration (`opt-in-skip`, `version_floor "7.2"`; Story 19.5).
- `schemas/marker-taxonomy.yaml` — the two visual-regression evidence marker classes (`visual-regression-delta-exceeded` / `visual-regression-baseline-missing`; schema_version `1.15`) and their `diagnostic_pointer` / `pointer_context_fields`.
- `schemas/envelope.schema.yaml` — the `visual_regression_emissions` array + `$defs/visual_regression_emission` the QA wrapper rides the records on.
- `agents/qa.md` — the QA specialist wrapper carrying the web-AND-mobile + opt-in-gated visual-regression audit procedure step.
