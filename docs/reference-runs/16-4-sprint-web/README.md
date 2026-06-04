# Reference Run 16-4 — Sprint-Scope Web Reference Run (`status --sprint` query + sprint-state-tree witness)

Captured artifacts for the Epic-16 sprint-scope reference run per Story 16.4 (`_bmad-output/implementation-artifacts/16-4-bmad-automation-status-sprint-query-sprint-level-reference-run-fixture.md`). This directory is the sprint-scope analog of Story 15.5's `docs/reference-runs/15-5-epic-web/` — one scope up. See `docs/reference-projects.md`'s web row (`Latest Run Record` cell migrated here per Story 16.4 AC-7; the prior `15-5-epic-web/` is preserved as the historical epic-scope capture).

- **Reference project:** the `bmad-autopilot/` development workspace itself, exercised as a stand-in per the Story 8.7 AC-3 option (b) posture inherited through Stories 9.6 / 10.7 / 13.7 / 15.5 and blessed for sprint scope by `epics-phase-2.md` line 526 ("a sprint-scope reference run record is captured … run-against-development-workspace stand-in acceptable … record captured for Epic 23"). See `narrative.md` § Reference project.
- **Project type:** `web` (the sprint-orchestration layer is project-type-agnostic; the web row is the one this capture migrates).
- **Scope:** **sprint** — a synthetic multi-epic sprint (`sprint-916-ref` over `epic-916` + `epic-917`, with stories `916-1-alpha` / `916-2-bravo` / `917-1-charlie`, all `ready-for-dev`) driven end-to-end through `sprint_lifecycle.run_sprint_loop`. The ids are deliberately NOT the real `sprint-1` / `epic-16` (no collision with the live planning slice). Two epics so a genuine mid-sprint boundary exists distinct from sprint-close; three stories total.
- **Determinism posture:** the per-epic/per-story dispatch is the injected deterministic `EpicLoopRunner` (the ratified Story 16.1 seam) — NOT a live LLM run. In the clean run BOTH epic units drive a **real** nested `epic_lifecycle.run_epic_loop` (with their own injected `StoryLoopRunner` stub), writing genuine per-epic `epic-run-state-<id>.yaml` caches that survive for the `status --sprint` read, so the sprint↔epic seam is genuinely exercised. See `narrative.md` § Stand-in disclosure.
- **Run date (ISO 8601):** 2026-06-04.
- **Terminal state:** `sprint-complete` (clean run — both epics `epic-complete`; all three stories `merge-ready`; per-sprint retry budget consumed 1 of 4; no active loud-fail markers). The fixture additionally witnesses the `sprint-paused-on-escalation`, `sprint-paused-on-budget`, and `sprint-escalation-rate-exceeded` (informational, does-not-pause) variants (see `narrative.md` § Deterministic-termination witness).
- **Sprint-state-tree witness:** the read-only `status --sprint` render (`status-sprint-output.md`) presents the full sprint → epics → stories tree with rolled-up aggregate cost (Σ per-epic = 4.50 USD), per-sprint retry-budget consumption (1 of 4), re-derived escalation rate (0 of 3 = 0.0%), and the scoped active-markers union — the breakdown-plus-rollup the industry charges a Marketplace gadget for, made first-class (`narrative.md` § Sprint-state-tree witness).

## Artifacts

| File | Description |
|---|---|
| [`status-sprint-output.md`](status-sprint-output.md) | The genuine read-only `status --sprint sprint-916-ref` human render over the persisted terminal caches (the verbatim `render_sprint_inspection_human` output; the `## Pointers` absolute paths normalized to `<project-root>` — see `narrative.md` § Redaction discipline). The sprint→epics→stories tree, aggregate cost, per-sprint retry budget, escalation rate, scoped active-markers, and the AC-3 drill-down pointers. |
| [`sprint-status-artifact-sprint-916-ref.md`](sprint-status-artifact-sprint-916-ref.md) | The 16.3 `assemble_sprint_status_artifact` output at sprint close, rendered from the SAME terminal caches the `status --sprint` query read (the read path composes). Genuine assembler output, copied verbatim. |
| [`sprint-run-state.yaml`](sprint-run-state.yaml) | The persisted terminal sprint-run-state cache (the NFR-R8 aggregate VIEW the query + artifact render from) — `current_state: sprint-complete`, `per_epic_status`, the per-sprint retry budget, and the active-markers list. |
| [`narrative.md`](narrative.md) | Sprint-scope execution notes: the stand-in disclosure intro (REAL vs STANDS-IN), the AC-3 pointer-not-projection scope decision, the NFR-P3 per-sprint-latency observation + stand-in caveat (AC-8), the redaction-discipline witness, and the forward-consumer pointer to Story 23.2. |
| [`README.md`](README.md) | This file. |

## How these artifacts were produced (honest capture)

The `status-sprint-output.md` + `sprint-status-artifact-*.md` + `sprint-run-state.yaml` are NOT hand-authored. They are the verbatim output of the SAME substrate the CI fixture drives — `tools/loud-fail-harness/tests/test_epic_16_reference_run_fixture.py` (`_drive_clean_run`) with a fixed `generated_at` (2026-06-04T12:00:00Z) so the render + artifact are byte-stable (only the `## Pointers` ephemeral `tmp_path` prefixes are normalized to `<project-root>` — the substantive content is untouched). The fixture re-verifies this exact composition on every CI run (the deterministic, CI-green engine; the Story 14.6 / 15.5 "Reference **Fixture**" lineage); this directory commits the human-facing capture (the Story 10.7 / 13.7 / 15.5 "**Reference-Run**" lineage).

## Forward consumers

- **Story 23.2** (`docs/phase-2-completion-evidence.md`) — reads THIS directory's `status-sprint-output.md` + `sprint-status-artifact-*.md` + `sprint-run-state.yaml` when populating the Epic-16 sprint-scope reference-run row. Story 16.4 does NOT build that artifact or its `phase-2-completion-evidence` CI gate — that is Story 23.1.
- A later Phase 2 sprint-scope web capture (e.g. against a real maintainer-owned project per the Epic 22 H11 decision) will migrate `docs/reference-projects.md`'s web-row `Latest Run Record` cell from `16-4-sprint-web/` to a fresher directory; THIS directory then becomes a historical sprint-scope capture.

## NFR-S1 hygiene witness

Pre-commit grep scan against this directory:

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/16-4-sprint-web/
```

Expected output: zero hits. Verified post-capture. The synthetic sprint carries no secrets at all (no env-provisioning, no MCP keys — the injected runner stands in for live dispatch); env-var NAMEs (never VALUEs) remain acceptable per the NFR-S1 NAME-not-VALUE rule.

## Cross-references

- `_bmad-output/implementation-artifacts/16-4-bmad-automation-status-sprint-query-sprint-level-reference-run-fixture.md` — the story file authorizing this capture.
- `tools/loud-fail-harness/tests/test_epic_16_reference_run_fixture.py` — the CI fixture that PRODUCES these artifacts and re-verifies them every run.
- `docs/reference-runs/15-5-epic-web/` — the structural template (one scope down) + the preserved historical epic-scope web capture.
- `docs/reference-projects.md` — the per-project index whose web row's `Latest Run Record` cell points to THIS directory.
- `_bmad-output/planning-artifacts/epics-phase-2.md` Story 16.4 (lines 513–526), Epic 16 framing (462–464), per-mode NFR-P3 + per-sprint cost+latency budget (204), Story 23.1/23.2 (the forward consumer).
