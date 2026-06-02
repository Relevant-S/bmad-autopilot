# Reference Run 15-5 — Epic-Scope Web Reference Run (per-epic cost-partition + running/close PR-bundle witness)

Captured artifacts for the Epic-15 epic-scope reference run per Story 15.5 (`_bmad-output/implementation-artifacts/15-5-epic-15-reference-run-fixture-per-epic-cost-partition-witness.md`). This directory adapts the Phase 1.5 Story 10.7 / Phase 1-patch Story 13.7 per-run directory shape (`docs/reference-runs/13-7-web/`) to **epic scope** — see `docs/reference-projects.md`'s web row (`Latest Run Record` cell migrated here per Story 15.5 AC-5; the prior `13-7-web/` is preserved as the historical per-story FR22c capture).

- **Reference project:** the `bmad-autopilot/` development workspace itself, exercised as a stand-in per the Story 8.7 AC-3 option (b) posture inherited through Stories 9.6 / 10.7 / 13.7 and blessed for epic scope by `epics-phase-2.md` line 454 ("run-against-development-workspace stand-in acceptable per Story 10.7 precedent and pending Epic 22 H11 decision"). See `narrative.md` § Reference project.
- **Project type:** `web` (the epic-orchestration layer is project-type-agnostic; the web row is the one this capture migrates).
- **Scope:** **epic** — a synthetic multi-story epic (`epic-915` with `915-1-alpha` / `915-2-bravo` / `915-3-charlie`, all `ready-for-dev`) driven end-to-end through `epic_lifecycle.run_epic_loop`. `epic-915` is deliberately NOT the real `epic-15` (no collision with the live planning slice). Three stories so a genuine mid-epic boundary exists distinct from epic-close.
- **Determinism posture:** the per-story specialist dispatch is the injected deterministic `StoryLoopRunner` (the ratified Story 15.1 seam) — NOT a live LLM run. Story 1's runner additionally performs a **real** `worktree_lifecycle` create → per-worktree run-state write → cleanup, so the epic↔worktree "no orphan worktree / no stale lock" seam is genuinely exercised. See `narrative.md` § Stand-in disclosure.
- **Run date (ISO 8601):** 2026-06-02.
- **Terminal state:** `epic-complete` (clean run — all three stories `merge-ready`; per-epic retry budget consumed 2 of 6; zero orphan worktrees; no `worktree-stale-lock` persisted). The fixture additionally witnesses the `epic-paused-on-escalation` and `epic-paused-on-budget` variants (see `narrative.md` § Deterministic-termination witness).
- **Per-epic cost-partition witness:** the epic PR bundle renders one per-story cost row + an `Epic total` row (`epic_cost_total == sum(per_story_cost)` = 4.50; `fold_story_cost` threaded end-to-end). This is the load-bearing witness for the NFR-P5 per-epic extension (`epics-phase-2.md` line 78).

## Artifacts

| File | Description |
|---|---|
| [`pr-bundle-mid-epic.md`](pr-bundle-mid-epic.md) | The **running** epic PR bundle at the first per-story completion boundary (story 1 of 3 `merge-ready`; epic still `epic-in-progress`). The genuine `assemble_epic_bundle` output (Story 15.3), copied verbatim — only story 1 carries non-zero cost, so the lower-bound caveat renders (an HONEST capture of the partial partition). |
| [`pr-bundle-epic-close.md`](pr-bundle-epic-close.md) | The **final** epic PR bundle at epic close (`epic-complete`; full per-story cost partition; final retry-budget consumption). Genuine `assemble_epic_bundle` output, copied verbatim. |
| [`epic-run-state.yaml`](epic-run-state.yaml) | The persisted terminal epic-run-state cache (the NFR-R8 aggregate VIEW the bundle renders from) — `current_state: epic-complete`, per-story statuses, the per-epic retry budget, and the per-epic cost partition. |
| [`narrative.md`](narrative.md) | Epic-scope execution notes: the stand-in disclosure intro (REAL vs STANDS-IN), the per-story-vs-per-epic cost scoping (AC-4), the NFR-P3 per-epic-latency observation + stand-in caveat (AC-6), the redaction-discipline witness, and the forward-consumer pointer to Story 23.2. |
| [`README.md`](README.md) | This file. |

## How these artifacts were produced (honest capture)

The `pr-bundle-*.md` + `epic-run-state.yaml` are NOT hand-authored. They are the verbatim output of the SAME substrate the CI fixture drives — `tools/loud-fail-harness/tests/test_epic_15_reference_run_fixture.py` (`_drive_clean_run`) with a fixed `generated_at` (2026-06-02T12:00:00Z) so the bundle is byte-stable. The fixture re-verifies this exact composition on every CI run (the deterministic, CI-green engine; the Story 14.6 "Reference **Fixture**" lineage); this directory commits the human-facing capture (the Story 10.7 / 13.7 "**Reference-Run**" lineage).

## Forward consumers

- **Story 23.2** (`docs/phase-2-completion-evidence.md`) — reads THIS directory's `pr-bundle-epic-close.md` + cost partition + `epic-run-state.yaml` when populating the Epic-15 epic-scope reference-run row. Story 15.5 does NOT build that artifact or its `phase-2-completion-evidence` CI gate — that is Story 23.1.
- A later Phase 2 epic-scope web capture (e.g. against a real maintainer-owned project per the Epic 22 H11 decision) will migrate `docs/reference-projects.md`'s web-row `Latest Run Record` cell from `15-5-epic-web/` to a fresher directory; THIS directory then becomes a historical epic-scope capture.

## NFR-S1 hygiene witness

Pre-commit grep scan against this directory:

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/15-5-epic-web/
```

Expected output: zero hits. Verified post-capture. The synthetic epic carries no secrets at all (no env-provisioning, no MCP keys — the injected runner stands in for live dispatch); env-var NAMEs (never VALUEs) remain acceptable per the NFR-S1 NAME-not-VALUE rule.

## Cross-references

- `_bmad-output/implementation-artifacts/15-5-epic-15-reference-run-fixture-per-epic-cost-partition-witness.md` — the story file authorizing this capture.
- `tools/loud-fail-harness/tests/test_epic_15_reference_run_fixture.py` — the CI fixture that PRODUCES these artifacts and re-verifies them every run.
- `docs/reference-runs/13-7-web/` — the structural template + the preserved historical per-story FR22c web capture.
- `docs/reference-projects.md` — the per-project index whose web row's `Latest Run Record` cell points to THIS directory.
- `_bmad-output/planning-artifacts/epics-phase-2.md` lines 445–458 (Story 15.5 AC source), 376–379 (Epic 15 framing), 78 (NFR-P5 per-epic extension), 454 (stand-in posture).
