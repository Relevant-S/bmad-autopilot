# Reference Run 13-7 — FR22c-Active Mobile Reference Run (within-AC flow-branch coverage witness)

Captured artifacts for the FR22c-active mobile reference run per Story 13.7 (`_bmad-output/implementation-artifacts/13-7-reference-run-refresh-web-and-mobile-fr22c-active-records.md`). This directory parallels the Phase 1.5 Story 9.6 per-run directory shape (`docs/reference-runs/9-6-mobile/`) — see `docs/reference-projects.md`'s mobile row (`Latest Run Record` cell migrated here per Story 13.7 AC-5).

- **Reference project:** Story 13.5's canonical multi-branch synthetic story (the e-commerce cart/checkout story; QA Behavioral Plan = `tools/loud-fail-harness/tests/fixtures/flow-branch-coverage/clean/qa-behavioral-plan.md`), **rebound to the mobile driver surface**, exercised as a stand-in per the AC-1(c) substitution posture inherited from Story 9.6. See `narrative.md` § Reference project.
- **Project type:** `mobile` (driver `mobile` per Story 9.3 / ADR-007).
- **Story exercised:** `sample-flow-branch-mobile-001` — the SAME 3-AC multi-branch synthetic story the sibling `13-7-web` run exercises; only the driver mechanics differ. The strictly-linear `sample-auto-mobile-001` greeter has no branching ACs and cannot witness FR22c (Story 13.7 AC-2 / AC-3).
- **Review posture:** three-layer (`blind` / `edge` / `auditor`) — LAD-disabled, matching the `9-6-mobile` Phase 1.5 baseline (mobile + LAD is not a default-on combination). No `lad` layer, no `lad` cost-partition row, and no LAD API-key env var referenced anywhere in this directory.
- **Run date (ISO 8601):** 2026-05-22.
- **Terminal state:** `merge-ready` (clean first-pass; zero retries; loud-fail block populated with three `heuristic-skipped` markers — one cross-AC exploratory heuristic + two within-AC FR22c flow-branch skips; zero `mobile-blocked` markers).
- **FR22c witness:** 6 `must-visit` within-AC flow branches driven through the mobile-MCP surface with per-branch Tier-1 + Tier-2 evidence; 2 `intentionally-skipped` branches loud-failed via `heuristic-skipped: flow-branch-<branch-id>` markers. This is the mobile-side empirical witness for Epic 13 success criteria 2 + 5.

## Artifacts

| File | Description |
|---|---|
| [`install-output.txt`](install-output.txt) | Story 7.2 install path output (git-clone-symlink fallback per Story 7.1) — pre-existing install reused; mobile MCP registered via `claude mcp add mobile-mcp -- npx -y @mobilenext/mobile-mcp@latest` per ADR-007. LAD-disabled — no LAD MCP, no LAD API-key env var. |
| [`init-output.txt`](init-output.txt) | `/bmad-automation init` output — Story 7.3 precondition checks (mobile-mcp probe SUCCESS), Story 9.2 project-type detection (`mobile`), Story 7.5 config + qa-runbook stubs (`mobile_app_package_name` field per Story 9.3 AC-8), Story 7.8 TEA-boundary orientation. |
| [`run-output.txt`](run-output.txt) | `/bmad-automation run sample-flow-branch-mobile-001` per-seam streaming output (Story 2.12) culminating in `merge-ready` — including the FR22c must-visit branch driving through the mobile-MCP surface (Story 13.4 wrapper step 6 mobile sub-paragraph) and the two `intentionally-skipped` flow-branch marker emissions (Story 13.3 `surface_flow_branch_skipped`). |
| [`dev-envelope.yaml`](dev-envelope.yaml) | Dev specialist's return envelope per FR51 + Story 2.8 wrapper. |
| [`review-bmad-envelope.yaml`](review-bmad-envelope.yaml) | Review-BMAD specialist's three-layer envelope (`blind-hunter` + `edge-case-hunter` + `acceptance-auditor`) per FR26 + FR56 + Story 2.9 — clean three-layer pass; `failed_layers: []`; no `lad` layer (LAD-disabled). |
| [`qa-envelope.yaml`](qa-envelope.yaml) | QA specialist's per-AC envelope per FR55 + Story 9.3 — mobile-driver-sourced evidence (`mobile_list_elements_on_screen` a11y-tree JSON = Tier-1; `mobile_take_screenshot` PNG = Tier-2). **Authored to validate against the unmodified `schemas/envelope.schema.yaml`** (Story 13.7 AC-4): FR22c adds no envelope field; per-`must-visit`-branch evidence rides on `ac_results[i].evidence_refs`; `heuristic_skipped_emissions` carries only the cross-AC `auth-boundary` skip — NO `flow-branch` sub_classification. |
| [`pr-bundle.md`](pr-bundle.md) | Assembled merge-ready PR bundle (Story 2.11 + Story 6.1) with the loud-fail block at top (FR32) — three `heuristic-skipped` markers; the enumerated `flow_branches[]` per AC; per-`must-visit`-branch evidence references; the three-layer review section. |
| [`narrative.md`](narrative.md) | Narrative + the dedicated `## FR22c within-AC flow-branch coverage` subsection (per-AC must-visit-vs-skipped enumeration — Epic 13 success criterion 5) + the `## FR22c surface-placement discipline` note (AC-4) + deterministic-termination + PR-bundle-surface witness checklists + invariant table + environment notes + redaction-discipline witness. |
| [`README.md`](README.md) | This file. |

## Forward consumers

- A Phase 2 mobile reference-run capture will migrate `docs/reference-projects.md`'s mobile-row `Latest Run Record` cell from `13-7-mobile/` to a fresher `reference-runs/<phase-2-story-id>-mobile/` directory; THIS directory then becomes a historical FR22c-active capture, and `docs/reference-runs/9-6-mobile/` remains the historical pre-FR22c mobile capture.

## NFR-S1 hygiene witness (AC-11)

This run is LAD-disabled — the captured artifacts carry no LAD API-key env-var reference at all. The pre-commit grep scan against this directory (and the sibling `13-7-web/`):

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/13-7-web/ docs/reference-runs/13-7-mobile/
```

returns zero hits. Verified post-capture — see `narrative.md` § Execution notes (redaction discipline).

## Cross-references

- `_bmad-output/implementation-artifacts/13-7-reference-run-refresh-web-and-mobile-fr22c-active-records.md` — the story file authorizing this capture.
- `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-20.md` — Epic 13 success criteria 2 + 5 this run is the empirical witness for.
- `docs/reference-runs/9-6-mobile/` — the structural template + the preserved historical pre-FR22c mobile capture.
- `docs/reference-runs/13-7-web/` — the sibling FR22c-active web reference run.
- `docs/reference-projects.md` — the per-project index whose mobile row's `Latest Run Record` cell points to THIS directory.
- `bmad-autopilot/agents/qa.md` § "FR22c within-AC flow-branch coverage — where it lives in the return" + step 6 / step 8 mobile sub-paragraph — the AC-4 surface-placement + mobile-driving spec.
- `bmad-autopilot/tools/loud-fail-harness/tests/fixtures/flow-branch-coverage/clean/` — the multi-branch synthetic story this run reuses as its QA surface.
