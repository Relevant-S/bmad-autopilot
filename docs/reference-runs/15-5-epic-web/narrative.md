# Reference Run 15-5 — Epic-Scope Web Reference Run — narrative

## Stand-in disclosure (read first — what is REAL vs what STANDS IN)

Per the Story 10.7 narrative-honesty discipline (`deferred-work.md` line 810 — state the stand-in posture in the intro, not buried in § Discovered gaps): this run is an **epic-orchestration-substrate witness**, not a live LLM run.

**What is REAL** (genuinely exercised substrate):

- The epic Orchestrator — `epic_lifecycle.run_epic_loop` — drives the synthetic epic's three stories sequentially end-to-end: `enumerate_epic_stories` → `init_epic_run_state` → per-story dispatch → `fold_story_terminal` + `fold_story_cost` + `apply_epic_budget` at each boundary → `advance_epic_run_state` atomic writes (with the transient-marker filter applied) → terminal state.
- The per-epic cost fold (`fold_story_cost` → `PerEpicCostPartition`) and the per-epic retry-budget fold (`apply_epic_budget` → `PerEpicRetryBudget`).
- The running + close epic PR-bundle assembly (`bundle_assembly_epic.assemble_epic_bundle` + `_render_cost_partition` + `_render_retry_budget`) — `pr-bundle-mid-epic.md` and `pr-bundle-epic-close.md` are the verbatim assembler output, copied without edits.
- A **real** per-story worktree lifecycle for story 1 (`worktree_lifecycle.create_worktree` against a real throwaway git repo → a schema-valid per-worktree `RunState` written at the Story-14.4 worktree-scoped address → `cleanup_worktree` returning `removed=True`), so the epic↔worktree "no orphan worktree / no stale lock" seam is a genuine integration witness rather than a model-level tautology.
- Deterministic termination across all three epic-terminal variants (`epic-complete`, `epic-paused-on-escalation`, `epic-paused-on-budget`) with no crash, no orphan worktree, and no `worktree-stale-lock` persisted.

**What STANDS IN** (not exercised here):

- **The per-story specialist dispatch** — represented by the injected deterministic `StoryLoopRunner` (the architecturally-ratified Story 15.1 seam). Each story's runner returns a canned `StoryLoopOutcome(terminal_status, retries_consumed, cost)`. This is NOT a mock-instead-of-real shortcut: the per-story loop's bit-identity is preserved precisely BY injecting at this boundary (Story 15.1 AC-2). It does mean there is no live Dev/Review-BMAD/QA/Review-LAD execution in this run.
- **The "real external reference project"** — the `bmad-autopilot/` development workspace is the stand-in per Story 8.7 AC-3 option (b), extended to epic scope per `epics-phase-2.md` line 454. Live re-capture against a deployed runtime + a maintainer-owned project is forward-scoped to the Epic 22 H11 decision + Story 23.2.

This split is the same honesty posture Stories 9.6 / 10.7 / 13.7 used; the net-new witness here is **epic-scope orchestration composition + the per-epic cost partition**, not live dispatch.

## Reference project purpose + scope

This run is the **empirical, CI-witnessed proof that Epic 15's epic-orchestration substrate (Stories 15.1–15.4) composes end-to-end** before Epic 16 (sprint orchestration) builds sprint flow on top. It is the Epic-15 analog of Story 14.6's `test_epic_14_substrate_smoke.py` — but deepened one layer, to the orchestrator-integration surface (`run_epic_loop`), since 15.1–15.4 already landed all the runtime.

The synthetic epic `epic-915` carries three `ready-for-dev` stories so a genuine **mid-epic boundary** (story 1 done, epic still `epic-in-progress`) exists distinct from **epic-close** (all stories terminal). `epic-915` is deliberately numeric-and-non-real: `enumerate_epic_stories` requires an `epic-<digits>` id (`_parse_epic_number`), so the AC-1 illustrative `epic-ref15` shape is rendered as the clearly-synthetic `epic-915` with no collision against the live `epic-15` planning slice.

## Deterministic-termination witness

The fixture drives `run_epic_loop` to all three terminal variants; each terminates deterministically with no raise:

| Run | Injected outcomes | Terminal state | Dispatched | Pause |
|---|---|---|---|---|
| clean | all `merge-ready` | `epic-complete` | `915-1-alpha`, `915-2-bravo`, `915-3-charlie` | none |
| escalation | story 2 `escalated` | `epic-paused-on-escalation` | `915-1-alpha`, `915-2-bravo` (strict prefix) | `915-2-bravo` |
| budget | retries exhaust `multiplier 1 × 3` at story 2 | `epic-paused-on-budget` | `915-1-alpha`, `915-2-bravo` | `915-2-bravo` |

In the escalation and budget runs the downstream story (`915-3-charlie`) does **not** auto-advance (sensor-not-advisor; the epic halts, the human decides continuation — Story 15.1 AC-4). The budget run additionally carries the durable `epic-budget-exhausted` marker, which survives the transient filter. The clean run's persisted final state carries no `worktree-stale-lock` (the transient marker is re-derived from live state each cycle and filtered before persistence — the Story 15.1 option-(a) model; this run reuses the `test_epic_15_transient_marker_smoke.py` witness posture).

## Running + close PR-bundle witness

The epic PR bundle is captured at TWO points (the AC-3 "running bundle snapshot at mid-epic + epic-close"):

- **mid-epic** (`pr-bundle-mid-epic.md`) — epic state `epic-in-progress`; only `915-1-alpha` carries non-zero cost (1.50); the lower-bound caveat renders honestly because stories 2 + 3 are still 0.00; retry budget consumed 1 of 6.
- **epic-close** (`pr-bundle-epic-close.md`) — epic state `epic-complete`; full per-story cost partition (1.50 / 2.25 / 0.75) + `Epic total` 4.50; retry budget consumed 2 of 6.

The two snapshots DIFFER on exactly the expected fields (epic state + cost-partition completeness + budget consumption), proving the "running bundle" regenerates from the live cache rather than being a static artifact. The fixture also asserts byte-stability: assembling the close bundle twice from the unchanged cache with a fixed `generated_at` yields byte-identical output (the Story 15.3 / NFR-R1 idempotent-bundle contract).

## Per-story vs per-epic cost-partition scoping (NFR-P5, AC-4)

"Per-epic + per-story cost partition (per NFR-P5)" (AC source line 456) is satisfied by **two surfaces composing**, neither duplicating the other — the same NFR-R8 boundary Story 15.3 drew:

- **Per-epic scope** (witnessed HERE) — the epic-run-state cache's `PerEpicCostPartition` carries per-story TOTALS (`per_story_cost`) + `epic_cost_total`, rendered as the `## 💸 Epic Cost Partition` table. This is the per-epic NFR-P5 extension (`epics-phase-2.md` line 78) — the new surface this run witnesses.
- **Per-story scope** (pointed-to, NOT re-rendered here) — NFR-P5's per-specialist (Dev / Review-BMAD / QA / Review-LAD) + per-retry breakdown lives in the per-story `RunState.cost_to_date_by_specialist`, rendered in each story's own merge-ready / escalation bundle. The epic bundle POINTS to that artifact (`_bmad-output/pr-bundles/<story-id>/`) — it does NOT re-aggregate per-specialist cost into the epic cache (that would edge toward a fourth canonical store, the exact NFR-R8 violation Story 15.3 rejected).

This pointer-not-projection scoping matches the recurring industry pattern (Jira epic-progress reports show rolled-up totals + a drill-down "breakdown view" for each item's contribution; the per-item contribution lives one scope down): the epic layer renders the roll-up + per-story rows, and the per-specialist drill-down stays reachable at story scope.

## NFR-P3 per-epic-latency observation (AC-6 — H3 input, not a failure)

Per `epics-phase-2.md` Story 15.5 AC: "NFR-P3 budget on per-epic latency is observed; if exceeded, the overage is recorded as input to H3 per-mode articulation (Epic 22) — overage is empirical witness, not failure."

**Observation with the explicit stand-in caveat:** because the per-story specialist dispatch is the injected deterministic runner (no live LLM), this captured run has **no genuine per-story wall-clock latency**. The only real timing component is the epic-LAYER overhead — enumeration + per-story folds + `advance_epic_run_state` atomic writes + bundle assembly — which is negligible (sub-second for a three-story epic; the whole fixture, including a real `git worktree add`/`remove`, runs in ~1.7s). A genuine per-epic-latency witness against a deployed runtime is therefore **forward-scoped to Story 23.2 / Epic 22 H3**, which already carries per-mode NFR-P3 articulation AND the new per-epic / per-sprint cost+latency budgets (`epics-phase-2.md` lines 78, 204).

This is recorded as an H3 input in `deferred-work.md` (cross-referencing the existing H3 mobile 07:32 / LAD-enabled 05:24 overage entries) — the same "H3 surfacing IS the value" framing Stories 9.6 / 10.7 used. It is a witness-of-a-gap (the stand-in cannot validate per-epic latency empirically), not a story-level failure.

## Execution notes (redaction discipline)

The synthetic epic involves no env-provisioning, no MCP servers, and no API keys — the injected runner stands in for all live dispatch — so the captured directory carries no secrets at all. The post-capture `grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/15-5-epic-web/` returns zero hits (NFR-S1; env-var NAMEs are acceptable, VALUEs never appear — there are none to redact here).

## Execution date

2026-06-02 (ISO 8601). Bundle `generated_at` pinned to 2026-06-02T12:00:00Z for byte-stable capture.

## Discovered gaps (Story 8.7 AC-5 three-class triage discipline)

- **Forward-scoped (not a gap in this story):** a genuine per-epic-latency witness against a deployed runtime + a live per-story dispatch — Story 23.2 / Epic 22 H3 (recorded in `deferred-work.md`). The stand-in posture is the inherited Story 10.7 commitment, not a defect.
- No substrate gaps surfaced: Stories 15.1–15.4 compose at every seam the fixture drives.

## Cross-references

- `_bmad-output/implementation-artifacts/15-5-epic-15-reference-run-fixture-per-epic-cost-partition-witness.md` — the story file.
- `tools/loud-fail-harness/tests/test_epic_15_reference_run_fixture.py` — the CI fixture that produces + re-verifies these artifacts.
- `docs/reference-runs/13-7-web/` — the structural template + preserved historical per-story FR22c web capture.
- `_bmad-output/implementation-artifacts/deferred-work.md` — the AC-6 NFR-P3 per-epic-latency H3-input entry (cross-references the mobile/LAD overage precedents).
- `_bmad-output/planning-artifacts/epics-phase-2.md` — Story 15.5 AC (lines 445–458), Epic 15 framing (376–379), NFR-P5 per-epic extension (78), per-mode NFR-P3 (204), stand-in posture (454), Story 23.1/23.2 (the forward consumer).
