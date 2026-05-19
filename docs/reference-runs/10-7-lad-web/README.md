# Reference Run 10-7 — LAD-Enabled Web Reference Run (Phase 1.5 sycophancy-escape witness)

Captured artifacts for the Phase 1.5 LAD-enabled reference run per Story 10.7 (`_bmad-output/implementation-artifacts/10-7-reference-lad-enabled-run-fixture-end-to-end.md`). This directory parallels Phase 1.5 Story 9.6's `docs/reference-runs/9-6-mobile/` per-run directory shape AND Phase 1 Story 8.7's `docs/mvp-completion-evidence/journey-{1..4}/` per-journey precedent — see `docs/reference-projects.md`'s web row (`Latest Run Record` cell now points here per AC-2 Option B in-place update).

- **Reference project:** `bmad-autopilot/` development workspace itself (Story 8.7 AC-3 option (b) stand-in posture extended to Phase 1.5 LAD per AC-1(b) — see `narrative.md` § Reference project for the rationale).
- **Project type:** `web` (`sample-auto-001` fixture canonically exercised as web at Phase 1 Story 8.7 / journey-1; LAD-enabled overlay added at Phase 1.5 per ADR-008 + Stories 10.1–10.6 mechanical surface).
- **Story exercised:** `sample-auto-001` Phase-1.5-substrate-overlay variant — the Dev pass implemented the combined Phase 1.5 Stories 10.4 + 10.5 substrate (`four_layer_review_dispatch.py` + `lad_mcp_unavailable.py`; 1279 lines total — well above AC-1(f)'s ~50-line floor; multiple control-flow + error-handling + concurrency decision points) as the LAD-reviewable diff. This is the meta-validation surface (Phase 1.5 substrate reviewed by the Phase 1.5 LAD activation). No dedicated story fixture exists for this Phase 1.5 overlay run; the AC-1(c) substitution posture (Story 9.6 precedent) applies.
- **LAD configuration:** `_bmad/automation/config.yaml#review_lad.enabled: true` + `_bmad/automation/config.yaml#review_lad.api_key_env_var: OPENROUTER_API_KEY` (the post-Story-10.1 corrected env-var name per ADR-008 + Story 10.4 AC-1). LAD MCP registered per ADR-008 install handle: `claude mcp add --transport stdio lad -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" -- uvx --from git+https://github.com/Shelpuk-AI-Technology-Consulting/lad_mcp_server lad-mcp-server`. The `OPENROUTER_API_KEY` env var was set in the operator's shell with credits available; NAME captured in this directory, VALUE never captured per NFR-S1 + AC-3 redaction discipline.
- **Run date (ISO 8601):** 2026-05-14.
- **Terminal state:** `merge-ready` (clean first-pass; zero retries; loud-fail block populated with three `heuristic-skipped` markers; PR bundle review section non-empty — 12 LAD-source findings rendered into the existing `decision_needed | patch | defer | dismiss` triage taxonomy per Story 10.4 AC-3; 4 patch-bucket findings + 1 decision_needed are visible to the practitioner for follow-up).
- **Post-Story-12.2 walkthrough note (2026-05-18 validation-responsibility-boundary correction).** The captured-on-2026-05-14 fixture predates Sprint Change Proposal 2026-05-18 + Story 12.2. When this run is re-captured: the missing-`OPENROUTER_API_KEY` path no longer short-circuits in the wrapper — the upstream `lad_mcp_server` MCP server reports the credential error at `mcp__lad__code_review` invocation time; the wrapper catches the failure and emits `status: blocked` with rationale `"LAD MCP tool invocation failed: <upstream error>"`; the orchestrator emits the unified `LAD-skipped: mid-run-mcp-unavailable` marker (the prior `mid-run-api-key-missing` sub_cause is retired). The clean LAD-COMPLETED scenario captured here is unaffected by the correction (zero `LAD-skipped` emissions on this run; the changed behavior only manifests on the missing-key path).

## Artifacts

| File | Description |
|---|---|
| [`install-output.txt`](install-output.txt) | Story 7.2 install path output (git-clone-symlink fallback chosen per Story 7.1 spike outcome) — pre-existing install reused on the dev machine; LAD MCP registered via `claude mcp add --transport stdio lad -e OPENROUTER_API_KEY=… -- uvx --from git+… lad-mcp-server` per ADR-008 / `docs/lad-setup.md` (Story 10.7-shipped operator walkthrough). Env-var VALUE never captured. |
| [`init-output.txt`](init-output.txt) | `/bmad-automation init` output covering Story 7.3 precondition checks (LAD precondition probe SUCCESS — `mcp__lad__code_review` reachable + `OPENROUTER_API_KEY` env-var present; NOT skipped at init time per Story 10.5 AC-3), Story 7.5 config + qa-runbook stub generation (config shows `review_lad.enabled: true` + corrected env-var NAME), Story 7.8 TEA-boundary first-run orientation. |
| [`run-output.txt`](run-output.txt) | `/bmad-automation run sample-auto-001` per-seam streaming output (Story 2.12) culminating in `merge-ready` completion via the 4-layer review surface — dev-dispatched → dev-returned → review-bmad-dispatched (4-layer parallel) → review-bmad-returned → qa-dispatched → qa-returned → terminal `merge-ready`. The 4-layer dispatch is visible per Story 10.4 substrate's orchestrator-event emission; the LAD layer's single-reviewer-mode handling (OpenRouter secondary timeout) is also visible. |
| [`dev-envelope.yaml`](dev-envelope.yaml) | Dev specialist's return envelope per FR51 + Story 2.8 wrapper. |
| [`review-bmad-envelope.yaml`](review-bmad-envelope.yaml) | Review-BMAD specialist's 4-layer envelope (`blind-hunter` + `edge-case-hunter` + `acceptance-auditor` + `lad`) per FR26 + FR56 + Story 2.9 + Story 10.4 — **12 LAD-source findings (`source: "lad"`)** rendered per AC-4(a) + AC-4(b); status=fail driven by 4 patch-bucket findings; `failed_layers` empty (LAD layer COMPLETED in single-reviewer mode per ADR-008 dual-reviewer-fallback escape — not a failure). |
| [`qa-envelope.yaml`](qa-envelope.yaml) | QA specialist's per-AC envelope per FR22b + Story 2.10 + Story 4.4 — web-driver-sourced (playwright-mcp) evidence references under `_bmad-output/qa-evidence/sample-auto-001/run-001/`. |
| [`pr-bundle.md`](pr-bundle.md) | Assembled merge-ready PR bundle (Story 2.11 + Story 6.1 + Story 10.6) with loud-fail block at top per FR32 — populated marker bundle (three `heuristic-skipped` markers; zero `LAD-skipped` markers since LAD ran successfully); **per-specialist cost partition INCLUDING the `lad` row populated per NFR-P5 + Story 10.6 AC-6** (the row is the structural witness that Review-LAD is a first-class peer at the cost-observability boundary); per-AC evidence references (FR19 evidence-triple); zero retries; 4-layer review section enumerating `blind` / `edge` / `auditor` / `lad` per Story 10.4's PR-bundle rendering extension. |
| [`narrative.md`](narrative.md) | Narrative + environment notes + execution date + dedicated **LAD-only finding analysis** subsection (per AC-4(c) — per-finding 3-layer-would-have-missed analysis + aggregate count) + Phase 1.5 invariant witnesses + deterministic-termination witness checklist (AC-5(e)) + PR-bundle-surface witness checklist (AC-6(g)) + NFR-P3 budget comparison (AC-7) + execution-notes redaction-discipline witness. |

## Forward consumers

- **Story 11.2** (`_bmad-output/planning-artifacts/epics-phase-1.5.md` line 357 — "Mobile + LAD Reference-Project Run Records Populated"; lines 363–370 detail) reads THIS directory's `pr-bundle.md` + cost section + marker bundle + `review-bmad-envelope.yaml`'s LAD-source findings when populating the LAD-enabled row in `phase-1.5-completion-evidence.md`. Forward-pointer status: **(LANDED — see commit `<sha7>`)** at Story 11.2 landing (2026-05-14) per the convention established in Stories 9.6 / 10.1 / 10.2 / 10.3 / 10.4 / 10.5 / 10.6.

## NFR-S1 hygiene witness (AC-6(d))

Pre-commit grep scan against this directory:

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/10-7-lad-web/
```

Expected output: zero hits. Verified post-capture per `narrative.md` § Execution notes (redaction discipline).

## Cross-references

- `_bmad-output/implementation-artifacts/10-7-reference-lad-enabled-run-fixture-end-to-end.md` — the story file authorizing this capture.
- `_bmad-output/planning-artifacts/architecture.md#ADR-008 lines 661-734` — LAD MCP server selection / `OPENROUTER_API_KEY` contract / install handle / dual-reviewer parallelism.
- `_bmad-output/planning-artifacts/epics-phase-1.5.md` lines 320-334 — verbatim Story 10.7 epic AC.
- `_bmad-output/planning-artifacts/epics-phase-1.5.md` lines 357 + 363-370 — Story 11.2 forward consumer.
- `bmad-autopilot/agents/review-lad-wrapper.md` — Story 10.2 + Story 10.5 wrapper this run's LAD layer exercised.
- `bmad-autopilot/docs/lad-setup.md` — Story 10.7-shipped operator-facing LAD MCP setup guide.
- `bmad-autopilot/docs/reference-projects.md` — the per-project index whose web row's `Latest Run Record` cell now points to THIS directory.
- `_bmad-output/implementation-artifacts/deferred-work.md` § Deferred from: Story 10.7 LAD-enabled reference run (2026-05-14) — the H3 housekeeping entry surfaced by AC-7(c)'s NFR-P3 0:24-overage.
