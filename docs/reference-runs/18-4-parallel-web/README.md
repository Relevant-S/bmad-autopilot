# Reference Run 18-4 — Parallel-Mode Web Reference Run (`run --epic` with `parallel_stories: true`)

Captured artifacts for the Epic-18 parallel-mode reference run per Story 18.4 (`_bmad-output/implementation-artifacts/18-4-parallel-mode-reference-fixture-end-to-end-run.md`). This directory is the parallel-mode analog of Story 15.5's `docs/reference-runs/15-5-epic-web/` (sequential epic scope), adapted to concurrent dispatch. See `docs/reference-projects.md`'s web row (`Latest Run Record` cell migrated here per Story 18.4 AC-6; the prior `16-4-sprint-web/` is preserved as the historical sprint-scope capture).

- **Reference project:** the `bmad-autopilot/` development workspace itself, exercised as a stand-in per the Story 8.7 AC-3 option (b) posture inherited through Stories 9.6 / 10.7 / 13.7 / 15.5 / 16.4 and blessed for Phase-2 epic scope by `epics-phase-2.md` line 454. See `narrative.md` § Reference project.
- **Project type:** `web` (the parallel-dispatch layer is project-type-agnostic; the web row is the one this capture migrates).
- **Mode:** **parallel** — `parallel_stories: true`, `max_parallel_stories: 2`, driven end-to-end through `epic_lifecycle.run_epic_loop`'s parallel branch (which delegates phase-3 to `parallel_dispatch.dispatch_stories_parallel` and constructs the production `env_provisioning.ParallelEnvClaimProvider` + `DisjointPortAllocator`).
- **Scope:** **epic** — a synthetic 2-story epic (`epic-918` with stories `918-1-alpha` / `918-2-bravo`, both `ready-for-dev`). The ids are deliberately NOT the real `epic-18` (no collision with the live planning slice; `enumerate_epic_stories` requires an `epic-<digits>` id). Exactly `max_parallel_stories` stories so both are admitted in a single wave and genuinely run concurrently.
- **Determinism posture:** the per-story dispatch is a deterministic injected `ParallelStoryLoopRunner` (the ratified Story 18.1 seam) carrying a `threading.Barrier(2)` concurrency rendezvous — NOT a live LLM run. In the clean run BOTH stories drive a **real** per-story worktree lifecycle (`create_worktree` → schema-valid per-worktree `RunState` write → `cleanup_worktree`) under genuine `ThreadPoolExecutor` concurrency, so the epic↔worktree↔dispatch seam is genuinely exercised. See `narrative.md` § Stand-in disclosure.
- **Run date (ISO 8601):** 2026-06-09.
- **Terminal state:** `epic-complete` (clean run — both stories `merge-ready`; per-epic retry budget consumed 0 of 4; no active loud-fail markers; zero orphan worktrees; no `worktree-stale-lock` persisted).
- **Concurrency-overlap witness:** the `Barrier(2)` rendezvous released (both runner bodies were in-flight simultaneously) and the thread-safe peak observed-concurrency counter reached 2 — an explicit assertion, loud-fail bounded by a finite timeout so a regression to sequential dispatch fails fast rather than hanging. See `narrative.md` § Concurrency-overlap witness.
- **Clean-run no-pollution + negative witness:** the clean run fires NO `parallel-story-state-pollution` marker (the production disjoint-claim provider keeps Story 18.2's live detector silent — a NON-vacuous witness, since the run drives the real `run_epic_loop` parallel branch that constructs the real provider); a separate negative-witness function drives `dispatch_stories_parallel` directly with a deliberately-colliding provider (two stories → same `allocated_port`) and proves the durable `parallel-story-state-pollution: shared-port-collision` marker fires + the epic pauses on `epic-paused-on-escalation` + in-flight units drain. The two together prove the prevention (18.3) ⟷ detection (18.2) composition end-to-end. See `narrative.md` § Prevention ⟷ detection.

## Artifacts

| File | Description |
|---|---|
| [`pr-bundle-epic-close.md`](pr-bundle-epic-close.md) | The genuine `bundle_assembly_epic.assemble_epic_bundle` output at epic close, copied verbatim — the per-story (= per-worktree, under parallel mode) cost partition (one row per story + `Epic total`; `epic_cost_total == sum(per_story_cost)`), the per-story status table with per-story-artifact pointers, the retry-budget-consumption line, and the loud-fail block (None active). Substrate-produced, an HONEST capture. |
| [`epic-run-state.yaml`](epic-run-state.yaml) | The persisted terminal epic-run-state cache the bundle renders from (the NFR-R8 aggregate VIEW) — `current_state: epic-complete`, `per_story_status`, the per-epic retry budget, the `per_epic_cost_partition`, and the (empty) active-markers list. |
| [`narrative.md`](narrative.md) | Parallel-mode execution notes: the stand-in disclosure intro (REAL vs STANDS-IN), the concurrency-overlap witness, the per-story=per-worktree cost framing, the per-sprint-out-of-scope note, the NFR-P3 per-epic-latency observation + parallel-mode caveat, the NFR-S1 redaction witness, the substrate-defect-and-fix disclosure (the seed-ordering bug 18.4 surfaced), and the forward-consumer pointer to Story 23.2. |
| [`README.md`](README.md) | This file. |

## How these artifacts were produced (honest capture)

The `pr-bundle-epic-close.md` + `epic-run-state.yaml` are NOT hand-authored. They are the verbatim output of the SAME substrate the CI fixture drives — `tools/loud-fail-harness/tests/test_epic_18_reference_run_fixture.py` (the clean-run carrier) — driven once with a fixed `generated_at` (2026-06-09T12:00:00Z) + fixed `run_id` (`run-epic-918-ref-001`) so the bundle is byte-stable (the fixture asserts assemble-twice → byte-identical). The fixture re-verifies this exact composition (deterministic `epic-complete`, the concurrency rendezvous, the no-pollution + negative witnesses, the cost partition) on every CI run (the Story 14.6 / 15.5 / 16.4 "Reference **Fixture**" lineage); this directory commits the human-facing capture (the Story 10.7 / 13.7 / 15.5 / 16.4 "**Reference-Run**" lineage).

## Substrate defect surfaced + fixed (read with the capture)

This is the FIRST integration that drives the **real** `run_epic_loop(parallel_stories=True)` against a **real** git repo with the **real** `ParallelEnvClaimProvider` (every Story 18.1–18.3 unit test stubbed `create_worktree` / `worktree_run_state_path`). Doing so surfaced a latent seam defect: `ParallelEnvClaimProvider.__call__` eagerly pre-seeded the per-worktree run-state on the main thread during admission, which pre-created the worktree directory **before** `create_worktree`'s `git worktree add` — so the real parallel path crashed with `fatal: '<path>' already exists`. Per the loud-fail / surface-don't-paper-over doctrine the defect was fixed (not worked around) as a contract-pair within Story 18.4: the carrier write was deferred to a new `ClaimCarrierSeed` seam (`ParallelEnvClaimProvider.seed_carrier`) the dispatcher invokes AFTER `create_worktree`. See `narrative.md` § Substrate defect + fix and the story's Completion Notes. This is exactly the value of an end-to-end reference fixture — it caught a composition defect the unit tests structurally could not.

## Forward consumers

- **Story 23.2** (`docs/phase-2-completion-evidence.md`) — reads THIS directory's `pr-bundle-epic-close.md` + `epic-run-state.yaml` when populating the Epic-18 parallel-mode reference-run row. Story 18.4 does NOT build that artifact or its `phase-2-completion-evidence` CI gate — that is Story 23.1.
- A later Phase 2 parallel-mode web capture (e.g. against a real maintainer-owned project per the Epic 22 H11 decision) will migrate `docs/reference-projects.md`'s web-row `Latest Run Record` cell from `18-4-parallel-web/` to a fresher directory; THIS directory then becomes a historical parallel-mode capture.

## NFR-S1 hygiene witness

Pre-commit grep scan against this directory:

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/18-4-parallel-web/
```

Expected output: zero hits. Verified post-capture. The synthetic epic carries no secrets at all (no env-provisioning side effects materialize a key — the injected runner stands in for live dispatch; the disjoint port is an OS-ephemeral integer, not a secret VALUE); env-var NAMEs (never VALUEs) remain acceptable per the NFR-S1 NAME-not-VALUE rule.

## Cross-references

- `_bmad-output/implementation-artifacts/18-4-parallel-mode-reference-fixture-end-to-end-run.md` — the story file authorizing this capture.
- `tools/loud-fail-harness/tests/test_epic_18_reference_run_fixture.py` — the CI fixture that PRODUCES these artifacts and re-verifies them every run.
- `docs/reference-runs/15-5-epic-web/` — the structural template (sequential epic scope) this parallel-mode capture adapts.
- `docs/reference-runs/16-4-sprint-web/` — the preceding (sprint-scope) `Latest Run Record`, preserved as historical.
- `docs/reference-projects.md` — the per-project index whose web row's `Latest Run Record` cell points to THIS directory.
- `_bmad-output/planning-artifacts/epics-phase-2.md` Story 18.4 (the AC block under "## Epic 18"), Epic 18 framing (lines 161–167), FR-P2-4 / FR7 / NFR-P5 mapping (lines 229, 237), Story 23.1/23.2 (the forward consumer).
