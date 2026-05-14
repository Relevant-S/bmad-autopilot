# Reference Run 9-6 — Mobile QA via Mobile MCP

Captured artifacts for the Phase 1.5 mobile reference run per Story 9.6 (`_bmad-output/implementation-artifacts/9-6-reference-mobile-project-fixture-end-to-end-run.md`). This directory parallels Phase 1 Story 8.7's per-journey evidence directories (`docs/mvp-completion-evidence/journey-{1..4}/`) — see `docs/reference-projects.md`'s mobile row for the cross-reference.

- **Reference project:** `bmad-autopilot/` development workspace itself (Story 8.7 AC-3 option (b) stand-in posture extended to Phase 1.5 mobile — see `narrative.md` § Reference project for the rationale).
- **Story exercised:** `sample-auto-mobile-001` (synthetic mobile-equivalent of Story 7.4's `sample-auto-001` — a minimal greeter mobile app launching to a "hello mobile" screen; substrate-level coverage in `tools/loud-fail-harness/tests/test_mobile_driver.py` (23 tests), `test_qa_ac_iteration.py::TestMobileDispatch` (4 tests), and `test_mobile_heuristic_spec.py` (21 tests); no dedicated story fixture exists for this stand-in run per the AC-1(c) substitution posture).
- **Run date (ISO 8601):** 2026-05-12.
- **Terminal state:** `merge-ready` (clean first-pass; zero retries; loud-fail block populated with two `heuristic-skipped` markers (`empty-state` + `auth-boundary`) per FR22 plan-driven applicability).

## Artifacts

| File | Description |
|---|---|
| [`install-output.txt`](install-output.txt) | Story 7.2 install path output (git-clone-symlink fallback chosen per Story 7.1 spike outcome) — pre-existing install reused on the dev machine; mobile MCP registered via `claude mcp add mobile-mcp -- npx -y @mobilenext/mobile-mcp@latest` per ADR-007 / `docs/mobile-mcp-setup.md`. |
| [`init-output.txt`](init-output.txt) | `/bmad-automation init` output covering Story 7.3 precondition checks (mobile-mcp probe success — `mobile_get_screen_size` returns clean), Story 7.4 sample-story scaffold, Story 7.5 config + qa-runbook stub generation (`project_type: mobile` written per Story 9.2 detection + `mobile_app_package_name` field per Story 9.3 AC-8), Story 7.8 TEA-boundary first-run orientation. |
| [`run-output.txt`](run-output.txt) | `/bmad-automation run sample-auto-mobile-001` per-seam streaming output (Story 2.12) culminating in `merge-ready` completion via the mobile-driver dispatch branch (Story 9.3 `qa_ac_iteration.py` `ProjectType="mobile"` dispatch). |
| [`dev-envelope.yaml`](dev-envelope.yaml) | Dev specialist's return envelope per FR51 + Story 2.8 wrapper. |
| [`review-bmad-envelope.yaml`](review-bmad-envelope.yaml) | Review-BMAD specialist's three-layer envelope (`blind-hunter` + `edge-case-hunter` + `acceptance-auditor`) per FR26 + FR56 + Story 2.9 — clean three-layer pass. |
| [`qa-envelope.yaml`](qa-envelope.yaml) | QA specialist's per-AC envelope per FR22b + Story 2.10 + Story 9.3 — mobile-driver-sourced evidence references (`mobile_take_screenshot` PNG paths + `mobile_list_elements_on_screen` a11y-tree JSON snapshot paths under `_bmad-output/qa-evidence/sample-auto-mobile-001/run-001/`). |
| [`pr-bundle.md`](pr-bundle.md) | Assembled merge-ready PR bundle (Story 2.11 + Story 6.1) with loud-fail block at top per FR32 — populated marker bundle (two `heuristic-skipped` markers (`empty-state` + `auth-boundary`); zero `mobile-blocked` markers because the run completed cleanly), per-specialist cost partition (NFR-P5), per-AC evidence references (FR19 evidence-triple), zero retries. |
| [`narrative.md`](narrative.md) | Narrative + environment notes + execution date + Phase 1.5 invariant witnesses + deterministic-termination witness checklist (AC-4) + PR-bundle-surface witness checklist (AC-5) + NFR-P3 budget comparison (AC-7). |

## Forward consumers

- **Story 11.2** (`_bmad-output/planning-artifacts/epics-phase-1.5.md` line 357 — "Mobile + LAD Reference-Project Run Records Populated"; lines 363–370 detail) reads THIS directory's `pr-bundle.md` + cost section + marker bundle when populating the mobile-row in `phase-1.5-completion-evidence.md`. Forward-pointer status: **(LANDED — see commit `<sha7>`)** at Story 11.2 landing (2026-05-14) per the convention established in Stories 9.3 / 9.4 / 9.5.
