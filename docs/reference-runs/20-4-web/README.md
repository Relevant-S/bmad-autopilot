# Reference Run 20-4 — Epic-20 QA-Independence + Flakiness Web Reference Run (plan re-derivation cross-check + flakiness threshold)

Captured artifacts for the Epic-20 web reference run per Story 20.4 (`_bmad-output/implementation-artifacts/20-4-epic-20-reference-runs-flakiness-corpus-witness.md`) — the **closing** reference run for Epic 20 (QA Independence Restoration + Flakiness Signal: per-run plan re-derivation cross-check FR-P2-9, longitudinal flakiness log + threshold FR-P2-8). This directory parallels the Epic-19 per-run directory shape (`docs/reference-runs/19-6-web/`) — see `docs/reference-projects.md`'s web row (`Latest Run Record` cell migrated here per Story 20.4 AC-9).

- **Reference project:** the established UI-bearing e-commerce cart/checkout synthetic surface (the same web surface the `19-6-web` / `13-7-web` runs exercised, reused per Story 20.4 Dev Notes "Reuse a synthetic QA surface — do not invent a new app"), captured as a fresh Epic-20 run per the AC-1 substitution posture inherited from Stories 9.6 / 10.7 / 13.7 / 19.6. See `narrative.md` § Reference project.
- **Project type:** `web` (driver `playwright` per Story 4.4).
- **Story exercised:** `sample-qa-coverage-001` — 3 ACs (add-to-cart / reject-invalid-card / order-confirmation). This run's net-new witness is the two Epic-20 QA-independence surfaces (`plan_rederivation` on its green AND drift branches, `flakiness_emissions` backed by a committed corpus snapshot), NOT the Epic-19 QA-coverage surfaces (that is `19-6-web`'s witness, preserved unmodified and carried forward here structurally).
- **Review posture:** LAD-enabled 4-layer (`blind` / `edge` / `auditor` / `lad`) — the `19-6-web` baseline posture is preserved (Story 20.4 AC-1) so the web row's `Latest Run Record` migration does not regress the latest web capture from 4-layer to 3-layer. The LAD layer is rendered as a clean representative pass; the genuine 12-finding `mcp__lad__code_review` capture is preserved permanently at `docs/reference-runs/10-7-lad-web/`.
- **Run sequence (ISO 8601):** run-001 (2026-06-13) → run-002 (2026-06-14) → run-003 (2026-06-15, the PRIMARY / latest capture) accumulating the flakiness corpus; run-004 (the drift follow-on after a qa-runbook mutation).
- **Terminal state:** `merge-ready` (clean first-pass; zero whole-story retries). Both Epic-20 markers (`flakiness-threshold-exceeded` on AC-2; `plan-rederivation-drift-detected` on the run-004 follow-on) are story-level QA-evidence and do NOT escalate the terminal.
- **Epic-20 witness:** FR-P2-9 cross-check `green` on the clean run-003 reuse-existing path AND `drift-detected` on the run-004 mutated-qa-runbook follow-on (`drift_surfaces: [heuristic_applicability]`, persisted plan NOT overwritten); FR-P2-8 flakiness corpus accumulating ≥3 consecutive transient-fail runs on AC-2 → `flakiness-threshold-exceeded`, with AC-1 a clean silent control; per-specialist × per-retry cost under the NFR-P1 ceiling (neither Epic-20 surface adds a cost row).

## Artifacts

| File | Description |
|---|---|
| [`install-output.txt`](install-output.txt) | Story 7.2 install path output (git-clone-symlink fallback per Story 7.1) — pre-existing install reused; LAD MCP registration carried forward from the `19-6-web` / `10-7-lad-web` baseline per ADR-008. No new MCP server for Epic 20 (both surfaces are pure in-wrapper substrate). Env-var VALUE never captured. |
| [`init-output.txt`](init-output.txt) | `/bmad-automation init` output — Story 7.3 precondition checks (LAD probe SUCCESS), Story 9.2 project-type detection (`web`), Story 7.5 config + qa-runbook stubs with the Epic-19 opt-in blocks carried forward AND NO `flakiness:` block (its absence = the Story 20.3 defaults 3/1 apply — absence is NOT a marker), Story 7.8 TEA-boundary orientation. |
| [`run-output.txt`](run-output.txt) | `/bmad-automation run sample-qa-coverage-001` per-seam streaming output (Story 2.12) for run-003 culminating in `merge-ready` — including the reuse-existing path, the FR-P2-9 cross-check (green), AC-2's action-level transient retries, the flakiness-log append + threshold evaluation (AC-2 exceeded), and a tail note on the run-004 drift follow-on. |
| [`dev-envelope.yaml`](dev-envelope.yaml) | Dev specialist's return envelope per FR51 + Story 2.8 wrapper. Carries NO Epic-20 net-new field (the two surfaces are all on the QA envelopes + the corpus snapshot). |
| [`review-bmad-envelope.yaml`](review-bmad-envelope.yaml) | Review-BMAD specialist's 4-layer envelope (`blind-hunter` + `edge-case-hunter` + `acceptance-auditor` + `lad`) per FR26 + FR56 + Story 10.4 — clean 4-layer pass; `failed_layers: []`. |
| [`qa-envelope.yaml`](qa-envelope.yaml) | QA specialist's per-AC envelope for the PRIMARY run-003 per FR55 + Story 4.4 — playwright-driver-sourced evidence. **Authored to validate against the unmodified `schemas/envelope.schema.yaml`** (Story 20.4 AC-6): exercises `plan_rederivation: { cross_check_status: green }` (AC-2) + `flakiness_emissions: [ { flakiness-threshold-exceeded, AC-2 } ]` (AC-5) + the carried-forward `heuristic_skipped_emissions`. Sensor-not-advisor (no `next_action` / `recommendation`). |
| [`qa-envelope-rederivation-drift.yaml`](qa-envelope-rederivation-drift.yaml) | **Supplementary Epic-20 witness #1** — the run-004 drift-run QA envelope (AC-3). Validates against the `$defs/plan_rederivation` conditional drift branch: `plan_rederivation: { cross_check_status: drift-detected, drift_surfaces: [heuristic_applicability], drifted_ac_ids: [AC-2], story_id: sample-qa-coverage-001 }`. |
| [`qa-flakiness-log.yaml`](qa-flakiness-log.yaml) | **Supplementary Epic-20 witness #2** — the committed 3-run flakiness-corpus SNAPSHOT (AC-4). The live `_bmad-output/qa-flakiness/<story-id>.yaml` store is gitignored (Story 20.2); this is the captured record, validating against the unmodified `schemas/qa-flakiness-log.yaml`. AC-2 carries 3 consecutive transient-fail records; AC-1 is the clean control. |
| [`pr-bundle.md`](pr-bundle.md) | Assembled merge-ready PR bundle (Story 2.11 + Story 6.1 + Story 10.6): the `## Per-AC results` with the `FR-P2-9 cross-check: green` line co-located with the RETAINED FR25 compromise blockquote (AC-2); the `### Flakiness threshold exceeded` H3 + per-AC marker comment (AC-5, greppable); the run-004 drift-run excerpt with the `### Plan re-derivation drift detected` H3 + marker comment (AC-3, greppable); the four-layer review section + the `lad` cost-partition row; the `## 💸 Cost Breakdown` per-specialist × per-retry section (total under NFR-P1). |
| [`narrative.md`](narrative.md) | Narrative + the `## FR-P2-9 plan re-derivation cross-check` (green + drift + AC-hash-channel distinction + the no-overwrite guarantee), `## FR-P2-8 flakiness corpus` (the run-001→003 accumulation timeline + transient-signal semantics + gitignored-vs-snapshot distinction), `## Flakiness threshold exceeded` (story-level-evidence-not-AC-gate; clean-control silence), and `## Substrate-replay as the non-vacuous proof` subsections + deterministic-termination + PR-bundle-surface witness checklists + invariant table + environment notes + redaction-discipline witness + the no-mobile-capture scoping decision. |
| [`README.md`](README.md) | This file. |

## Forward consumers

- Story 23.2 (`phase-2-completion-evidence.md`) is the forward consumer: it reads this directory's `qa-envelope.yaml` + `qa-envelope-rederivation-drift.yaml` + `qa-flakiness-log.yaml` + `pr-bundle.md` + cost section + marker bundle when populating the Phase-2 completion-evidence FR-P2-8 / FR-P2-9 rows.
- A later Phase 2+ web reference-run capture will migrate `docs/reference-projects.md`'s web-row `Latest Run Record` cell from `20-4-web/` to a fresher `reference-runs/<story-id>-web/` directory; THIS directory then becomes the historical Epic-20-QA-independence capture, and `docs/reference-runs/19-6-web/` remains the historical Epic-19-QA-coverage capture.

## Substrate-replay witness (AC-7)

Unlike the LLM-driven 19.6 capture, the Epic-20 verdicts come from pure, deterministic substrate, so this directory is CI-pinned by the NEW committed test `tools/loud-fail-harness/tests/test_reference_run_20_4.py`. It loads the committed artifacts here and replays them through the real `evaluate_ac_flakiness` (AC-2 exceeded / AC-1 not), `surface_plan_rederivation_cross_check` (green for the identical plan pair / drift-detected for the mutated pair), and `load_flakiness_log` / `validate_flakiness_log` — reproducing the witnessed verdicts. It reads this directory as DATA (no runtime↔harness cross-reference; `pluggability-gate` stays green). `uv run pytest tests/test_reference_run_20_4.py` → exit 0.

## NFR-S1 hygiene witness (AC-10)

Pre-commit grep scan against this directory:

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/20-4-web/
```

Expected output: zero hits. Verified post-capture — see `narrative.md` § Execution notes (redaction discipline). The captured artifacts contain the `OPENROUTER_API_KEY` env-var NAME (acceptable per the NFR-S1 NAME-not-VALUE rule) at `install-output.txt` + `init-output.txt`; the VALUE never appears. The `qa-flakiness-log.yaml` `evidence_ref` pointers cite the gitignored qa-evidence tree (NFR-O3) without committing any binary; captured evidence flows through the existing NFR-S2 `MaskedSelectorPolicy` redaction AS-IS (no new masking surface).

## Cross-references

- `_bmad-output/implementation-artifacts/20-4-epic-20-reference-runs-flakiness-corpus-witness.md` — the story file authorizing this capture.
- `docs/reference-runs/19-6-web/` — the structural template + the preserved historical Epic-19 QA-coverage web capture.
- `docs/reference-projects.md` — the per-project index whose web row's `Latest Run Record` cell points to THIS directory.
- `bmad-autopilot/schemas/envelope.schema.yaml` + `schemas/qa-flakiness-log.yaml` — the AC-6 conformance targets.
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/qa_plan_rederivation.py` + `qa_flakiness_log.py` + `qa_flakiness_threshold.py` — the landed Epic-20 substrate + the AC-7 replay entry points.
