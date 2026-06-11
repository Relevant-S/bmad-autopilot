# Reference Run 19-6 — Epic-19 QA-Coverage Web Reference Run (7-heuristic sweep + a11y + visual regression)

Captured artifacts for the Epic-19 QA-coverage web reference run per Story 19.6 (`_bmad-output/implementation-artifacts/19-6-epic-19-reference-run-qa-coverage-witnesses.md`) — the **closing** reference run for Epic 19 (QA-coverage expansion: full 7-heuristic sweep FR-P2-5, a11y audit FR-P2-6, visual regression FR-P2-10). This directory parallels the Phase 1 patch Story 13.7 per-run directory shape (`docs/reference-runs/13-7-web/`) — see `docs/reference-projects.md`'s web row (`Latest Run Record` cell migrated here per Story 19.6 AC-10).

- **Reference project:** the established UI-bearing e-commerce cart/checkout synthetic surface (the same web surface the `13-7-web` run exercised, reused per Story 19.6 Dev Notes "Reuse a synthetic QA surface — do not invent a new app"; the surface bears a rendered DOM so axe-core injection + Playwright screenshots have something to exercise), captured as a fresh Epic-19-QA-coverage run per the AC-1 substitution posture inherited from Stories 9.6 / 10.7 / 13.7. See `narrative.md` § Reference project.
- **Project type:** `web` (driver `playwright` per Story 4.4).
- **Story exercised:** `sample-qa-coverage-001` — 3 ACs (add-to-cart / reject-invalid-card / order-confirmation), all carrying a rendered web surface; this run's net-new witness is the three Epic-19 QA-coverage surfaces (`heuristic_skipped_emissions` with the 19.2 sub_classifications, `a11y_emissions`, `visual_regression_emissions`), NOT FR22c flow-branch coverage (that is `13-7-web`'s witness, preserved unmodified).
- **Review posture:** LAD-enabled 4-layer (`blind` / `edge` / `auditor` / `lad`) — the `13-7-web` baseline posture is preserved (Story 19.6 AC-1) so the web row's `Latest Run Record` migration does not regress the latest web capture from 4-layer to 3-layer. The LAD layer is rendered as a clean representative pass; the genuine 12-finding `mcp__lad__code_review` capture is preserved permanently at `docs/reference-runs/10-7-lad-web/`. The Epic-19 QA surfaces, not LAD, are this run's net-new witness.
- **Run date (ISO 8601):** 2026-06-11.
- **Terminal state:** `merge-ready` (clean first-pass; zero retries; loud-fail block populated with two `heuristic-skipped` markers — `rate-limit-boundary` + `permission-boundary` — plus three first-run `a11y-baseline-stale` markers and three first-run `visual-regression-baseline-missing` markers, all informational practitioner-visible signals, NOT auto-retry triggers).
- **Epic-19 witness:** all 7 exploratory heuristics dispatched (5 applicable-with-evidence; 2 structurally-inapplicable → `heuristic-skipped: <sub_classification>` markers, both among the four 19.2-added sub_classifications); a11y first-run baseline-creation per AC (`a11y-baseline-stale`); visual-regression first-run baseline-creation per AC (`visual-regression-baseline-missing`); per-specialist × per-retry cost under the NFR-P1 ceiling — the empirical confirmation of the 19.1/19.2 all-7-heuristics-ON activation gate.

## Artifacts

| File | Description |
|---|---|
| [`install-output.txt`](install-output.txt) | Story 7.2 install path output (git-clone-symlink fallback per Story 7.1) — pre-existing install reused; LAD MCP registration carried forward from the `13-7-web` / `10-7-lad-web` baseline per ADR-008. axe-core (ADR-011) + pixelmatch (ADR-012) are npm/library floors consumed by the wrapper's in-page injection / saved-PNG diff — no new MCP server. Env-var VALUE never captured. |
| [`init-output.txt`](init-output.txt) | `/bmad-automation init` output — Story 7.3 precondition checks (LAD precondition probe SUCCESS), Story 9.2 project-type detection (`web`), Story 7.5 config + qa-runbook stubs with the Epic-19 opt-in blocks ALL enabled (`heuristics.web.*: enabled` ×7, `a11y.enabled: true`, `visual_regression.enabled: true`), Story 7.8 TEA-boundary orientation. |
| [`run-output.txt`](run-output.txt) | `/bmad-automation run sample-qa-coverage-001` per-seam streaming output (Story 2.12) culminating in `merge-ready` — including the 7-heuristic dispatch (Story 19.2 step 8: 5 applicable + 2 skipped), the web-only a11y audit (Story 19.4 step 13), and the visual-regression audit (Story 19.5 step 14). |
| [`dev-envelope.yaml`](dev-envelope.yaml) | Dev specialist's return envelope per FR51 + Story 2.8 wrapper. Carries NO Epic-19 net-new field (the QA surfaces are all on `qa-envelope.yaml`). |
| [`review-bmad-envelope.yaml`](review-bmad-envelope.yaml) | Review-BMAD specialist's 4-layer envelope (`blind-hunter` + `edge-case-hunter` + `acceptance-auditor` + `lad`) per FR26 + FR56 + Story 10.4 — clean 4-layer pass; `failed_layers: []`. |
| [`qa-envelope.yaml`](qa-envelope.yaml) | QA specialist's per-AC envelope per FR55 + Story 4.4 — playwright-driver-sourced evidence. **Authored to validate against the unmodified `schemas/envelope.schema.yaml`** (Story 19.6 AC-7): exercises all three Epic-19 fields — `heuristic_skipped_emissions` (2 entries, closed 7-value `sub_classification` enum), `a11y_emissions` (3 first-run `a11y-baseline-stale`, `ac_id`-required), `visual_regression_emissions` (3 first-run `visual-regression-baseline-missing`, `required: [marker_class, ac_id]`). Sensor-not-advisor (no `next_action` / `recommendation`). |
| [`pr-bundle.md`](pr-bundle.md) | Assembled merge-ready PR bundle (Story 2.11 + Story 6.1 + Story 10.6) with the loud-fail block at top (FR32) — the 2 `heuristic-skipped` + 3 `a11y-baseline-stale` + 3 `visual-regression-baseline-missing` markers (each with an actionable how-to-enable pointer per FR31); the per-AC results + heuristic evidence; the four-layer review section + the `lad` cost-partition row; the `## 💸 Cost Breakdown` per-specialist × per-retry section. |
| [`narrative.md`](narrative.md) | Narrative + the `## FR-P2-5 full 7-heuristic sweep`, `## FR-P2-6 a11y audit`, and `## FR-P2-10 visual regression` subsections + the `## Activation-gate empirical confirmation` subsection (all-7-ON cost under NFR-P1; per-specialist-not-per-heuristic disclosure) + deterministic-termination + PR-bundle-surface witness checklists + invariant table + environment notes + redaction-discipline witness. |
| [`README.md`](README.md) | This file. |

## Forward consumers

- Story 23.2 (`phase-2-completion-evidence.md`) is the forward consumer: it reads this directory's `qa-envelope.yaml` + `pr-bundle.md` + cost section + marker bundle when populating the Phase-2 completion-evidence FR-P2-5 / FR-P2-6 / FR-P2-10 rows.
- A later Phase 2+ web reference-run capture will migrate `docs/reference-projects.md`'s web-row `Latest Run Record` cell from `19-6-web/` to a fresher `reference-runs/<story-id>-web/` directory; THIS directory then becomes the historical Epic-19-QA-coverage capture, and `docs/reference-runs/18-4-parallel-web/` remains the historical parallel-mode capture.

## NFR-S1 hygiene witness (AC-11)

Pre-commit grep scan against this directory (and the sibling `19-6-mobile/`):

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/19-6-web/ docs/reference-runs/19-6-mobile/
```

Expected output: zero hits. Verified post-capture — see `narrative.md` § Execution notes (redaction discipline). The captured artifacts contain the `OPENROUTER_API_KEY` env-var NAME (acceptable per the NFR-S1 NAME-not-VALUE rule) at `install-output.txt` + `init-output.txt`; the VALUE never appears. The a11y / visual-regression evidence references honor the NFR-S2 `MaskedSelectorPolicy` posture (captured screenshots + axe-core reports flow through the existing masked-selector redaction AS-IS; no new masking surface).

## Cross-references

- `_bmad-output/implementation-artifacts/19-6-epic-19-reference-run-qa-coverage-witnesses.md` — the story file authorizing this capture.
- `docs/reference-runs/13-7-web/` — the structural template + the preserved historical FR22c-active web capture.
- `docs/reference-runs/19-6-mobile/` — the sibling Epic-19 QA-coverage mobile reference run.
- `docs/reference-projects.md` — the per-project index whose web row's `Latest Run Record` cell points to THIS directory.
- `bmad-autopilot/agents/qa.md` § step 8 (7-heuristic dispatch) / step 13 (a11y) / step 14 (visual regression) + the Return-envelope section — the wrapper procedure these records mirror.
- `bmad-autopilot/schemas/envelope.schema.yaml` — the AC-7 conformance target (`heuristic_skipped_emissions` / `a11y_emissions` / `visual_regression_emissions` + `$defs`).
- `bmad-autopilot/docs/a11y-setup.md` + `bmad-autopilot/docs/visual-regression-setup.md` — the operator-facing setup pointers referenced by the loud-fail block's how-to-enable strings.
