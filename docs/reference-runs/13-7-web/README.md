# Reference Run 13-7 — FR22c-Active Web Reference Run (within-AC flow-branch coverage witness)

Captured artifacts for the FR22c-active web reference run per Story 13.7 (`_bmad-output/implementation-artifacts/13-7-reference-run-refresh-web-and-mobile-fr22c-active-records.md`). This directory parallels the Phase 1.5 Story 10.7 per-run directory shape (`docs/reference-runs/10-7-lad-web/`) — see `docs/reference-projects.md`'s web row (`Latest Run Record` cell migrated here per Story 13.7 AC-5).

- **Reference project:** Story 13.5's canonical multi-branch synthetic story (the e-commerce cart/checkout story; QA Behavioral Plan = `tools/loud-fail-harness/tests/fixtures/flow-branch-coverage/clean/qa-behavioral-plan.md`), exercised as a stand-in per the AC-1(c) substitution posture inherited from Stories 9.6 / 10.7. See `narrative.md` § Reference project.
- **Project type:** `web` (driver `playwright` per Story 4.4).
- **Story exercised:** `sample-flow-branch-001` — 3 ACs, each carrying 2–3 within-AC `flow_branches[]`; the strictly-linear `sample-auto-001` greeter has no branching ACs and cannot witness FR22c, so the multi-branch synthetic story is used (Story 13.7 AC-1 / AC-3).
- **Review posture:** LAD-enabled 4-layer (`blind` / `edge` / `auditor` / `lad`) — the `10-7-lad-web` baseline posture is preserved (Story 13.7 AC-1) so the web row's `Latest Run Record` migration does not regress the latest web capture from 4-layer to 3-layer. The LAD layer is rendered as a clean representative pass; the genuine 12-finding `mcp__lad__code_review` capture is preserved permanently at `docs/reference-runs/10-7-lad-web/`.
- **Run date (ISO 8601):** 2026-05-22.
- **Terminal state:** `merge-ready` (clean first-pass; zero retries; loud-fail block populated with three `heuristic-skipped` markers — one cross-AC exploratory heuristic + two within-AC FR22c flow-branch skips).
- **FR22c witness:** 6 `must-visit` within-AC flow branches driven with per-branch Tier-1 + Tier-2 evidence; 2 `intentionally-skipped` branches loud-failed via `heuristic-skipped: flow-branch-<branch-id>` markers. This is the empirical witness for Epic 13 success criteria 2 + 5.

## Artifacts

| File | Description |
|---|---|
| [`install-output.txt`](install-output.txt) | Story 7.2 install path output (git-clone-symlink fallback per Story 7.1) — pre-existing install reused; LAD MCP registration carried forward from the `10-7-lad-web` baseline per ADR-008. Env-var VALUE never captured. |
| [`init-output.txt`](init-output.txt) | `/bmad-automation init` output — Story 7.3 precondition checks (LAD precondition probe SUCCESS), Story 9.2 project-type detection (`web`), Story 7.5 config + qa-runbook stubs (`review_lad.enabled: true`), Story 7.8 TEA-boundary orientation. |
| [`run-output.txt`](run-output.txt) | `/bmad-automation run sample-flow-branch-001` per-seam streaming output (Story 2.12) culminating in `merge-ready` — including the FR22c must-visit branch driving (Story 13.4 wrapper step 6) and the two `intentionally-skipped` flow-branch marker emissions (Story 13.3 `surface_flow_branch_skipped`). |
| [`dev-envelope.yaml`](dev-envelope.yaml) | Dev specialist's return envelope per FR51 + Story 2.8 wrapper. |
| [`review-bmad-envelope.yaml`](review-bmad-envelope.yaml) | Review-BMAD specialist's 4-layer envelope (`blind-hunter` + `edge-case-hunter` + `acceptance-auditor` + `lad`) per FR26 + FR56 + Story 10.4 — clean 4-layer pass; `failed_layers: []`. |
| [`qa-envelope.yaml`](qa-envelope.yaml) | QA specialist's per-AC envelope per FR55 + Story 4.4 — playwright-driver-sourced evidence. **Authored to validate against the unmodified `schemas/envelope.schema.yaml`** (Story 13.7 AC-4): FR22c adds no envelope field; per-`must-visit`-branch evidence rides on `ac_results[i].evidence_refs`; `heuristic_skipped_emissions` carries only the cross-AC `auth-boundary` skip — NO `flow-branch` sub_classification. |
| [`pr-bundle.md`](pr-bundle.md) | Assembled merge-ready PR bundle (Story 2.11 + Story 6.1 + Story 10.6) with the loud-fail block at top (FR32) — three `heuristic-skipped` markers; the enumerated `flow_branches[]` per AC; per-`must-visit`-branch evidence references; the four-layer review section + the `lad` cost-partition row. |
| [`narrative.md`](narrative.md) | Narrative + the dedicated `## FR22c within-AC flow-branch coverage` subsection (per-AC must-visit-vs-skipped enumeration — Epic 13 success criterion 5) + the `## FR22c surface-placement discipline` note (AC-4) + deterministic-termination + PR-bundle-surface witness checklists + invariant table + environment notes + redaction-discipline witness. |
| [`README.md`](README.md) | This file. |

## Forward consumers

- A Phase 2 web reference-run capture will migrate `docs/reference-projects.md`'s web-row `Latest Run Record` cell from `13-7-web/` to a fresher `reference-runs/<phase-2-story-id>-web/` directory; THIS directory then becomes a historical FR22c-active capture, and `docs/reference-runs/10-7-lad-web/` remains the historical pre-FR22c web capture.

## NFR-S1 hygiene witness (AC-11)

Pre-commit grep scan against this directory (and the sibling `13-7-mobile/`):

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/13-7-web/ docs/reference-runs/13-7-mobile/
```

Expected output: zero hits. Verified post-capture — see `narrative.md` § Execution notes (redaction discipline). The captured artifacts contain the `OPENROUTER_API_KEY` env-var NAME (acceptable per the NFR-S1 NAME-not-VALUE rule) at `install-output.txt` + `init-output.txt`; the VALUE never appears.

## Cross-references

- `_bmad-output/implementation-artifacts/13-7-reference-run-refresh-web-and-mobile-fr22c-active-records.md` — the story file authorizing this capture.
- `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-20.md` — Epic 13 success criteria 2 + 5 this run is the empirical witness for.
- `docs/reference-runs/10-7-lad-web/` — the structural template + the preserved historical pre-FR22c web capture.
- `docs/reference-runs/13-7-mobile/` — the sibling FR22c-active mobile reference run.
- `docs/reference-projects.md` — the per-project index whose web row's `Latest Run Record` cell points to THIS directory.
- `bmad-autopilot/agents/qa.md` § "FR22c within-AC flow-branch coverage — where it lives in the return" — the AC-4 surface-placement spec.
- `bmad-autopilot/tools/loud-fail-harness/tests/fixtures/flow-branch-coverage/clean/` — the multi-branch synthetic story this run reuses as its QA surface.
