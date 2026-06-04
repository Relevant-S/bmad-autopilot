# Reference Run 16-4 — Sprint-Scope Web Reference Run — narrative

## Stand-in disclosure (read first — what is REAL vs what STANDS IN)

Per the Story 10.7 narrative-honesty discipline (state the stand-in posture in the intro, not buried in § Discovered gaps): this run is a **sprint-orchestration-substrate witness**, not a live LLM run.

**What is REAL** (genuinely exercised substrate):

- The sprint Orchestrator — `sprint_lifecycle.run_sprint_loop` — drives the synthetic sprint's two epic units sequentially end-to-end: `_parse_sprint_units` enumeration → `init_sprint_run_state` (per-sprint retry-budget formula `multiplier × epic_count`) → per-unit dispatch → `fold_epic_terminal` + cumulative `per_sprint_retry_budget` fold + `apply_sprint_budget` + the running escalation-rate tally at each boundary → `advance_sprint_run_state` atomic writes (with the transient-marker filter applied) → terminal state.
- The ≥-1-real-lifecycle seam: in the clean run BOTH epic units' injected `EpicLoopRunner` drives a **real** nested `epic_lifecycle.run_epic_loop` (each with its own injected `StoryLoopRunner` stub), writing a genuine per-epic `epic-run-state-epic-916.yaml` / `epic-run-state-epic-917.yaml` cache at the sprint-loop-supplied per-epic-addressed path (`epic_run_state_path_for`). Those caches SURVIVE on disk for the `status --sprint` read — so the sprint↔epic seam is a genuine integration witness, not a model-level tautology.
- The read-only `status --sprint` query — `sprint_status_command.inspect_sprint` REUSING Story 16.3's `build_sprint_status_artifact` aggregate read (the sprint-state-tree rollup over the sprint-run-state cache + each per-epic cache) — rendered to `status-sprint-output.md` verbatim. Zero write surface (FR48 / NFR-O4): the query never advances state, never assembles the `.md` artifact, never emits a marker.
- The 16.3 `assemble_sprint_status_artifact` at sprint close (`sprint-status-artifact-sprint-916-ref.md`), rendered from the SAME terminal caches — proving the read path composes (the query and the artifact agree on the aggregate cost 4.50 USD).
- Deterministic termination across all four sprint outcomes (`sprint-complete`, `sprint-paused-on-escalation`, `sprint-paused-on-budget`, and `sprint-complete` + the informational `sprint-escalation-rate-exceeded` marker) with no crash.

**What STANDS IN** (not exercised here):

- **The live per-epic/per-story specialist dispatch** — represented by the injected deterministic `EpicLoopRunner` / `StoryLoopRunner` (the architecturally-ratified Story 16.1 / 15.1 seam). The runners return canned outcomes with non-zero costs/retries. This is NOT a mock-instead-of-real shortcut: the per-epic + per-story loops' bit-identity is preserved precisely BY injecting at these boundaries. It does mean there is no live Dev/Review-BMAD/QA/Review-LAD execution in this run.
- **The "real external reference project"** — the `bmad-autopilot/` development workspace is the stand-in per Story 8.7 AC-3 option (b), extended to sprint scope per `epics-phase-2.md` line 526. Live re-capture against a deployed runtime + a maintainer-owned project is forward-scoped to the Epic 22 H11 decision + Story 23.2.

This split is the same honesty posture Stories 9.6 / 10.7 / 13.7 / 15.5 used; the net-new witness here is **sprint-scope orchestration composition + the read-only `status --sprint` sprint-state-tree**, not live dispatch.

## Reference project purpose + scope

This run is the **empirical, CI-witnessed proof that Epic 16's sprint-orchestration substrate (Stories 16.1–16.3) composes end-to-end** before Epic 17 (auto-merge) builds on the sprint surface. It is the Epic-16 analog of Story 15.5's epic-scope fixture — one scope up, at the sprint-orchestrator-integration surface (`run_sprint_loop`), since 16.1–16.3 already landed all the runtime and 16.4 adds the read-only query on top.

The synthetic sprint `sprint-916-ref` carries two epics (`epic-916`, `epic-917`) with three `ready-for-dev` stories total so a genuine **mid-sprint boundary** (epic-916 done, epic-917 not yet dispatched) exists distinct from **sprint-close** (all epics terminal). The ids are deliberately numeric-and-non-real: `run_epic_loop` requires `epic-<digits>` ids, so the synthetic `epic-916` / `epic-917` carry no collision against the live `epic-16` planning slice.

## Deterministic-termination witness

The fixture drives `run_sprint_loop` to all four sprint outcomes; each terminates deterministically with no raise:

| Run | Injected outcomes | Terminal state | Dispatched | Pause |
|---|---|---|---|---|
| clean | both epics `epic-complete` (REAL nested loop) | `sprint-complete` | `epic-916`, `epic-917` | none |
| escalation | `epic-916` → `epic-paused-on-escalation` | `sprint-paused-on-escalation` | `epic-916` (strict prefix) | `epic-916` |
| budget | `epic-916` retries (4) exhaust `multiplier 2 × 2 epics = 4` | `sprint-paused-on-budget` | `epic-916` | `epic-916` |
| escalation-rate | `epic-916` returns `epic-complete` with 2 of 4 stories escalated internally | `sprint-complete` + `sprint-escalation-rate-exceeded` | `epic-916`, `epic-917` | none |

In the escalation and budget runs the downstream epic (`epic-917`) does **not** auto-advance (sensor-not-advisor; the sprint halts, the human decides continuation — Story 16.1 AC-4). The escalation-rate run demonstrates the key Story 16.2 invariant: the `sprint-escalation-rate-exceeded` marker is **informational** — it surfaces a rate crossing (2/4 = 0.5 > the 0.25 threshold) WITHOUT pausing, so the sprint still reaches `sprint-complete` carrying the durable marker.

## Sprint-state-tree witness (the `status --sprint` read; AC-2)

The committed `status-sprint-output.md` is the genuine read-only render over the persisted terminal caches. It presents the full **sprint → epics → stories** tree the AC names:

- **Sprint lifecycle state** — `sprint-complete`, `sprint_id`, `run_id`, the pinned `generated_at`.
- **Sprint state tree** — each per-epic row (`epic-916 → epic-complete`, cost 3.75 USD, retries 1/4; `epic-917 → epic-complete`, cost 0.75 USD, retries 0/2) with its per-story rows nested beneath (`916-1-alpha`, `916-2-bravo`, `917-1-charlie`, all `merge-ready` with their costs).
- **Aggregate cost** — `4.50 USD` (Σ per-epic `epic_cost_total`).
- **Per-sprint retry budget** — `Used 1 of 4` (story `916-1-alpha`'s single retry; budget = `multiplier 2 × 2 epics`).
- **Escalation rate** — `Escalated 0 of 3 completed = 0.0%` (re-derived from the per-epic caches; the clean run has no escalations).
- **Active loud-fail markers** — `(no active markers)` on the clean run.
- **Pointers** — the resolved sprint-run-state path + the sprint-status-artifact path (via `compute_sprint_status_artifact_path`) + the AC-3 drill-down pointers.

This is the breakdown-plus-rollup the industry tooling charges a Marketplace gadget for (Jira's native sprint reports show only top-level rollups and force a drill-down for the per-epic-and-per-story breakdown within the sprint) — made first-class in the terminal.

## Marker-surfacing scope decision (AC-3 — pointer-not-projection)

The `status --sprint` render surfaces the AGGREGATE scoped active-markers union (sprint ∪ per-epic, de-duped on `(marker_class, scope)`) that `build_sprint_status_artifact` already carries — it does NOT project Story 8.4's `inspect_story` per contained story at sprint scale (O(all-stories-across-all-epics) reads on a read-only query does not compose up; NFR-R8). Instead it POINTS the practitioner to `status --epic <epic-id>` (per-epic marker detail) and `status <story-id>` (per-story marker + retry-history detail) for drill-down. The multi-scope observability chain (`status --sprint` → `status --epic` → `status <story-id>`) composes, each layer surfacing its own scope's markers without re-aggregating the layer below — the Story 15.3 pointer-not-projection decision applied one scope up. (On the clean run the union is empty; the escalation/rate runs exercise the non-empty union in CI.)

## NFR-P3 per-sprint-latency observation (AC-8 — H3 input, not a failure)

Per `epics-phase-2.md` Story 16.4 AC-8 + the Story 15.5 AC-6 framing: "NFR-P3 budget on per-sprint latency is observed; the overage is recorded as input to H3 per-mode articulation (Epic 22) — overage is empirical witness, not failure."

**Observation with the explicit stand-in caveat:** because the per-epic/per-story dispatch is the injected deterministic runner (no live LLM), this captured run has **no genuine per-sprint wall-clock latency**. The only real timing component is the sprint-LAYER overhead — unit enumeration + per-unit folds + `advance_sprint_run_state` atomic writes + the aggregate read (`build_sprint_status_artifact`) + the 16.3 artifact assembly — which is negligible (sub-second for a two-epic sprint; the whole fixture, including both real nested `run_epic_loop` drives, runs in well under a second). A genuine per-sprint-latency witness against a deployed runtime is therefore **forward-scoped to Story 23.2 / Epic 22 H3**, which already carries per-mode NFR-P3 articulation AND the new per-epic / per-sprint cost+latency budgets (`epics-phase-2.md` lines 78, 204).

This is recorded as an H3 input in `deferred-work.md` (cross-referencing the existing 15.5 per-epic + the Phase-1.5 mobile 07:32 / LAD-enabled 05:24 overage entries) — the same "H3 surfacing IS the value" framing Stories 9.6 / 10.7 / 15.5 used. It is a witness-of-a-gap (the stand-in cannot validate per-sprint latency empirically), not a story-level failure.

## Execution notes (redaction discipline)

The synthetic sprint involves no env-provisioning, no MCP servers, and no API keys — the injected runner stands in for all live dispatch — so the captured directory carries no secrets at all. The only normalization applied to `status-sprint-output.md` is the `## Pointers` absolute-path prefix: the fixture runs under an ephemeral `tmp_path`, so the load-bearing-irrelevant `tmp_path` prefix is rewritten to `<project-root>` (the substantive render content is verbatim). The post-capture `grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/16-4-sprint-web/` returns zero hits (NFR-S1; env-var NAMEs are acceptable, VALUEs never appear — there are none to redact here).

## Execution date

2026-06-04 (ISO 8601). The `status --sprint` render + 16.3 artifact `generated_at` pinned to 2026-06-04T12:00:00Z for byte-stable capture.

## Discovered gaps (Story 8.7 AC-5 three-class triage discipline)

- **Forward-scoped (not a gap in this story):** a genuine per-sprint-latency witness against a deployed runtime + a live per-epic/per-story dispatch — Story 23.2 / Epic 22 H3 (recorded in `deferred-work.md`). The stand-in posture is the inherited Story 10.7 commitment, not a defect.
- No substrate gaps surfaced: Stories 16.1–16.3 + this story's `sprint_status_command` compose at every seam the fixture drives.

## Cross-references

- `_bmad-output/implementation-artifacts/16-4-bmad-automation-status-sprint-query-sprint-level-reference-run-fixture.md` — the story file.
- `tools/loud-fail-harness/tests/test_epic_16_reference_run_fixture.py` — the CI fixture that produces + re-verifies these artifacts.
- `docs/reference-runs/15-5-epic-web/` — the structural template (one scope down) + preserved historical epic-scope web capture.
- `_bmad-output/implementation-artifacts/deferred-work.md` — the AC-8 NFR-P3 per-sprint-latency H3-input entry (cross-references the 15.5 per-epic + the mobile/LAD overage precedents).
- `_bmad-output/planning-artifacts/epics-phase-2.md` — Story 16.4 AC (lines 513–526), Epic 16 framing (462–464), per-mode NFR-P3 + per-sprint budget (204), Story 23.1/23.2 (the forward consumer).
