# Reference Run 19-6 — Epic-19 QA-Coverage Mobile Reference Run (6-of-7 heuristic subset + visual regression)

Captured artifacts for the Epic-19 QA-coverage mobile reference run per Story 19.6 (`_bmad-output/implementation-artifacts/19-6-epic-19-reference-run-qa-coverage-witnesses.md`) — the mobile sibling of the `19-6-web` closing reference run for Epic 19. This directory parallels the Phase 1 patch Story 13.7 per-run directory shape (`docs/reference-runs/13-7-mobile/`) — see `docs/reference-projects.md`'s mobile row (`Latest Run Record` cell migrated here per Story 19.6 AC-10).

- **Reference project:** the established UI-bearing e-commerce cart/checkout synthetic surface (the SAME surface the `19-6-web` run exercises), **rebound to the mobile driver surface**, exercised as a stand-in per the AC substitution posture inherited from Stories 9.6 / 13.7. See `narrative.md` § Reference project.
- **Project type:** `mobile` (driver `mobile` per Story 9.3 / ADR-007).
- **Story exercised:** `sample-qa-coverage-mobile-001` — the SAME 3-AC cart/checkout surface the sibling `19-6-web` run exercises; only the driver mechanics differ. This run's net-new witness is the mobile Epic-19 QA-coverage surfaces (`heuristic_skipped_emissions` for the 6-of-7 mobile subset, `visual_regression_emissions`); a11y is web-only and NOT witnessed here (NFR-I3).
- **Review posture:** three-layer (`blind` / `edge` / `auditor`) — LAD-disabled, matching the `9-6-mobile` / `13-7-mobile` baseline (mobile + LAD is not a default-on combination). No `lad` layer, no `lad` cost-partition row, and no LAD API-key env var referenced anywhere in this directory.
- **Run date (ISO 8601):** 2026-06-11.
- **Terminal state:** `merge-ready` (clean first-pass; zero retries; loud-fail block populated with one `heuristic-skipped: permission-boundary` marker plus three first-run `visual-regression-baseline-missing` markers; zero `mobile-blocked` markers; NO a11y marker; NO `heuristic-skipped: rate-limit-boundary` marker — silently matrix-excluded per ADR-010).
- **Epic-19 witness:** the 6-of-7 mobile heuristic subset dispatched (5 applicable-with-evidence; `permission-boundary` structurally-inapplicable → marker; `rate-limit-boundary` SILENTLY matrix-excluded — NO marker); visual-regression first-run baseline-creation per AC via the mobile-mcp capture surface; NO a11y (web-only).

## Artifacts

| File | Description |
|---|---|
| [`install-output.txt`](install-output.txt) | Story 7.2 install path output (git-clone-symlink fallback per Story 7.1) — pre-existing install reused; mobile MCP registered via `claude mcp add mobile-mcp -- npx -y @mobilenext/mobile-mcp@latest` per ADR-007. LAD-disabled — no LAD MCP, no LAD API-key env var. pixelmatch (ADR-012) is a diff library over saved PNGs — no new MCP server. |
| [`init-output.txt`](init-output.txt) | `/bmad-automation init` output — Story 7.3 precondition checks (mobile-mcp probe SUCCESS), Story 9.2 project-type detection (`mobile`), Story 7.5 config + qa-runbook stubs with the 6-of-7 mobile heuristic subset enabled + `visual_regression.enabled: true` + NO `a11y:` block (web-only), Story 7.8 TEA-boundary orientation. |
| [`run-output.txt`](run-output.txt) | `/bmad-automation run sample-qa-coverage-mobile-001` per-seam streaming output (Story 2.12) culminating in `merge-ready` — including the 6-of-7 mobile heuristic dispatch (rate-limit-boundary silently matrix-excluded), the visual-regression audit via mobile_take_screenshot, and the explicit NO-a11y record. |
| [`dev-envelope.yaml`](dev-envelope.yaml) | Dev specialist's return envelope per FR51 + Story 2.8 wrapper. Carries NO Epic-19 net-new field. |
| [`review-bmad-envelope.yaml`](review-bmad-envelope.yaml) | Review-BMAD specialist's three-layer envelope (`blind-hunter` + `edge-case-hunter` + `acceptance-auditor`) per FR26 + FR56 + Story 2.9 — clean three-layer pass; `failed_layers: []`; no `lad` layer (LAD-disabled). |
| [`qa-envelope.yaml`](qa-envelope.yaml) | QA specialist's per-AC envelope per FR55 + Story 9.3 — mobile-driver-sourced evidence (`mobile_list_elements_on_screen` a11y-tree JSON = Tier-1; `mobile_take_screenshot` PNG = Tier-2). **Authored to validate against the unmodified `schemas/envelope.schema.yaml`** (Story 19.6 AC-7): exercises `heuristic_skipped_emissions` (1 entry — `permission-boundary`; NO `rate-limit-boundary`) + `visual_regression_emissions` (3 first-run `visual-regression-baseline-missing`); NO `a11y_emissions`. Sensor-not-advisor. |
| [`pr-bundle.md`](pr-bundle.md) | Assembled merge-ready PR bundle (Story 2.11 + Story 6.1) with the loud-fail block at top (FR32) — 1 `heuristic-skipped` + 3 `visual-regression-baseline-missing` markers (each with an actionable how-to pointer per FR31); the per-AC results + heuristic evidence; the three-layer review section; the per-specialist × per-retry cost section (no `lad` row). |
| [`narrative.md`](narrative.md) | Narrative + the `## FR-P2-5 mobile 6-of-7 heuristic subset` (incl. the explicit rate-limit-boundary silent-matrix-exclusion record), `## FR-P2-10 visual regression`, and `## FR-P2-6 a11y NOT invoked (web-only)` subsections + the `## Activation-gate empirical confirmation` subsection + deterministic-termination + PR-bundle-surface witness checklists + invariant table + environment notes + redaction-discipline witness. |
| [`README.md`](README.md) | This file. |

## Forward consumers

- Story 23.2 (`phase-2-completion-evidence.md`) is the forward consumer: it reads this directory's `qa-envelope.yaml` + `pr-bundle.md` + cost section + marker bundle when populating the Phase-2 completion-evidence FR-P2-5 / FR-P2-10 mobile rows.
- A later Phase 2+ mobile reference-run capture (including the H8 live mobile re-capture Story 23.2 carries) will migrate `docs/reference-projects.md`'s mobile-row `Latest Run Record` cell from `19-6-mobile/` to a fresher directory; THIS directory then becomes the historical Epic-19-QA-coverage mobile capture, and `docs/reference-runs/13-7-mobile/` remains the historical FR22c-active mobile capture.

## NFR-S1 hygiene witness (AC-11)

This run is LAD-disabled — the captured artifacts carry no LAD API-key env-var reference at all. The pre-commit grep scan against this directory (and the sibling `19-6-web/`):

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/19-6-web/ docs/reference-runs/19-6-mobile/
```

returns zero hits. Verified post-capture — see `narrative.md` § Execution notes (redaction discipline). The visual-regression screenshots flow through the existing NFR-S2 `MaskedSelectorPolicy` redaction AS-IS (no new masking surface).

## Cross-references

- `_bmad-output/implementation-artifacts/19-6-epic-19-reference-run-qa-coverage-witnesses.md` — the story file authorizing this capture.
- `docs/reference-runs/13-7-mobile/` — the structural template + the preserved historical FR22c-active mobile capture.
- `docs/reference-runs/19-6-web/` — the sibling Epic-19 QA-coverage web reference run (the same surface, web driver + a11y).
- `docs/reference-projects.md` — the per-project index whose mobile row's `Latest Run Record` cell points to THIS directory.
- `bmad-autopilot/agents/qa.md` § step 8 (7-heuristic dispatch + two skip semantics) / step 14 (visual regression web+mobile gated) + the Return-envelope section.
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/mobile_heuristic_spec.py` — `MOBILE_HEURISTIC_SPECS` (the six mobile heuristics; rate-limit-boundary excluded per ADR-010).
- `bmad-autopilot/schemas/envelope.schema.yaml` — the AC-7 conformance target.
- `bmad-autopilot/docs/visual-regression-setup.md` — the operator-facing setup pointer.
