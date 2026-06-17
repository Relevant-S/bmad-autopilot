# Claude Code background-agent primitive stability spike (Story 21.1)

> Spike-with-bounded-timebox **instance #3** of the pattern named at `docs/extension-audit.md` § "Research-blocker handling — the spike-with-bounded-timebox pattern" (Story 1.11). Backs FR-P2-7 (`_bmad-output/planning-artifacts/prd.md` line 950 — "Background / fire-and-forget orchestrator execution — pending Claude Code stable background-agent primitive"; revisit condition at `prd.md` line 168). Verbatim AC at `_bmad-output/planning-artifacts/epics-phase-2.md` lines 836–849 (Story 21.1); the consumer is Story 21.2 at lines 851–864; epic framing at lines 194/198. **Path reconciliation:** the epic's tentative path `bmad-autopilot/docs/spikes/background-primitive-spike-<date>.md` (`epics-phase-2.md` line 846) is reconciled to the **established** convention `bmad-autopilot/docs/research-spikes/{spike-start-date}-{topic-slug}.md` landed by Stories 5.7 (`2026-05-04-deferred-work-format.md`) and 7.1 (`2026-05-07-plugin-primitive-stability.md`) — no new directory, no precedent break. **Pattern-shape:** the spike question is hands-on observational (it required dispatching a live background agent and reading the open issue-tracker state), so per the pattern-selection decision aid at `docs/research-spikes/2026-05-07-plugin-primitive-stability.md` § "Forward consumers" → "Pattern-selection decision aid (per AC-9)" this spike uses the **task-bounded** shape (Story 7.1's shape, instance #2), not Story 5.7's calendar-week-only shape.

## Spike metadata

| Field | Value |
|---|---|
| Spike-start date | 2026-06-17 |
| Spike-end date | 2026-06-17 |
| Timebox (calendar-maximum) | ≤2 calendar days (per AC-4; `epics-phase-2.md` line 849 — "the spike timebox is enforced (≤2 days; if exceeded without verdict, default to `unstable` + named fallback per loud-fail doctrine — bounded spike cannot silently expand)") |
| Timebox-honored | **true** — converged same-day, within the ≤2-day maximum, in a single AI-Dev session (see `## Timebox & convergence note`) |
| Loud-fail default-at-maximum | **documented, did NOT fire** — had the ≤2-day maximum been reached without a verdict, the artifact would default to `unstable` + `named-fallback` per loud-fail doctrine (a named, visible outcome; not a silent extension). See `## Timebox & convergence note`. |
| Primitive version assessed | **Claude Code 2.1.179** (local `claude --version` at spike-time). Agent-SDK not separately versioned: the spike exercises the Claude Code CLI/TUI background primitive (`claude --bg` / `/bg` / `claude agents`) + the in-session `Agent` tool (`run_in_background: true`), not the standalone Agent SDK. Documentary evidence: the official changelog traversed through the 2.1.179 range; open-issue evidence spans `#63023` (opened 2026-05-28) and `#68117` (reported against 2.1.170) plus the continuous 2.1.x background-session churn. |
| Capabilities tested | background session start / mid-session pause / mid-session resume / mid-session inspection (the four FR-P2-7-load-bearing capabilities, epic-verbatim per `epics-phase-2.md` line 846) — see `## Capabilities tested` |
| **Stability verdict** | **`partially-stable`** |
| **Recommended path** | **`partial`** |
| Fallback-fired | **false** — the `unstable` → `named-fallback` branch did NOT fire (the verdict is `partially-stable`: the primitive is exposed and functional, not unavailable/breaking). The named-fallback structure is documented in `## Outcome-decision flow` for the pattern's reusability per AC-5. |
| Rejected alternatives | verdict `stable` (REJECTED); verdict `unstable` (REJECTED); path `implement` (REJECTED); path `named-fallback` (named-but-not-fired) — each with its excluding evidence point in `## Outcome-decision flow` |
| Evidence-source enumeration count | **6** (1 — first-hand hands-on probe in this CC 2.1.179 env; 2 — open issue `#63023` + duplicates `#67524`/`#193366`; 3 — open issue `#68117` lifecycle divergence; 4 — official Claude Code changelog; 5 — Anthropic autonomy positioning + community report; 6 — PRD/epic anchors + loud-fail doctrine) |
| Per-convention-table-row backreference | `docs/extension-audit.md` § "Per-convention table" — the most recently appended row (the FIRST row added by an Epic-21 story); classification `automator-internal` |
| FR-P2-7 anchor | `_bmad-output/planning-artifacts/prd.md` line 950 (post-MVP FR-P2-7) + line 168 (revisit condition: "revisit when Claude Code ships a stable background-agent primitive") |
| Epics anchor | `_bmad-output/planning-artifacts/epics-phase-2.md` lines 836–849 (Story 21.1 verbatim AC); lines 851–864 (Story 21.2 — the consumer); lines 194/198 (Epic 21 user-outcome + standalone framing) |
| Forward consumers | Story 21.2 (background-execution implementation OR named fallback — primary consumer); FR-P2-7 Phase-3 revisit (the deferred sub-capability + its named revisit trigger); future spike-blockered stories (task-bounded-shape worked example #3) |

## Capabilities tested

The four FR-P2-7-load-bearing capabilities (epic-verbatim) were each evaluated against named evidence — hands-on in this Claude Code 2.1.179 environment where safely feasible, and the documentary record otherwise. A capability is marked **supported** / **supported-with-caveats** / **unsupported** with the specific evidence point.

| Capability (epic-verbatim) | What FR-P2-7 needs it for | Support level | Evidence |
|---|---|---|---|
| Background session start | dispatch `/bmad-automation run <story-id>` without blocking the terminal | **supported** | First-hand: an `Agent`-tool `run_in_background: true` dispatch was accepted, ran detached, and returned its result (`background-agent-probe-alive: 10:05:11Z`) on CC 2.1.179. `claude --help` exposes the `claude agents` ("Manage background agents") subcommand; the changelog documents `claude --bg` / `/bg` / daemon-backed background sessions. The primitive is exposed and starts cleanly. |
| Mid-session pause | the user closes the session; the loop must not halt | **unsupported (in-session subagents) / supported-with-caveats (daemon-backed sessions)** | `#63023` (OPEN): in-session background agents (`run_in_background: true`) are **terminated when the session is paused** (laptop close, OS sleep, long idle) — work in isolated worktrees is lost and **no completion notification fires**. Daemon-backed `claude --bg` sessions are *designed* to persist across pause, but the changelog shows a continuing stream of fixes for "background sessions re-attached after overnight retire losing their conversation and re-running the original prompt" and "losing their running background tasks when reattached after a Claude Code update" — the pause/resume boundary is not yet reliable at 2.1.179. |
| Mid-session resume | the loop continues to completion after the session is gone | **supported-with-caveats** | The changelog shipped "`/resume` support for background sessions — sessions started via `claude --bg` or agent view now appear alongside interactive ones, marked with `bg`" and `claude --help` exposes `--resume` / `--from-pr`. BUT a long tail of resume bugs: `#63023` (no notification on resume; cannot distinguish dead from completed), "`--resume` not reporting background subagents that were running when the previous Claude Code process exited", "background-session respawn rejecting malformed resume IDs from corrupted state files", "background-session attach failing with EAUTH … after the daemon auto-updated". |
| Mid-session inspection | results surface via `/bmad-automation status` in the next session (FR48 extension) | **supported-with-caveats** | The changelog ships `claude agents --json` with `--all`, `id`, `state`, and `waitingFor` fields — a real enumeration surface. BUT first-hand: `TaskList` returned **"No tasks found"** for the running Agent-tool background subagent (reproducing `#67524`'s "`TaskList` returns 'No tasks found' for Agent-tool subagents" / "no way to enumerate background agents with an actual alive/dead status"); and `#68117` reports the agents panel and the task registry **disagreeing** — dead tasks render as "Running" with live-ticking timers while `TaskStop` reports "No task found". Inspection works but cannot be trusted as a liveness oracle; it must be reconciled against ground truth. |

**The split is load-bearing for the verdict.** Capabilities 1 (start) and the in-session completion path are supported — first-hand, the probe's completion notification fired correctly *while the session stayed live*. The break is specifically at the session-**pause/resume** boundary (capabilities 2 and 3) and the **liveness** half of inspection (capability 4) — which is exactly the cross-closed-session survive-and-surface-later path FR-P2-7 promises ("a session that can be closed without halting the loop … results surface in the next session via `/bmad-automation status`"). The `partially-stable` verdict exists precisely for this split.

## Evidence sources reviewed

Six sources audited (≥4 per the 7.1 floor). Each source's contribution to the `partially-stable` verdict / `partial` path is named.

### 1. First-hand hands-on probe — this Claude Code 2.1.179 environment

A trivial background agent was dispatched via the `Agent` tool with `run_in_background: true` (a liveness probe that echoes a timestamp and returns it). Observations:

- The dispatch was **accepted and ran detached** — the agent was assigned an ID, ran in the background, and returned `background-agent-probe-alive: 10:05:11Z` with a `<status>completed</status>` task-notification (~5.5s, one tool use). → background **session start** works first-hand.
- While the agent was running, `TaskList` returned **"No tasks found"** — the Agent-tool background subagent did not surface on the task-enumeration primitive. → first-hand reproduction of the inspection/liveness gap.
- `claude --version` → **2.1.179**; `claude --help` exposes `claude agents` ("Manage background agents"), `--resume`, `--from-pr`, `--agents`.

**Kind:** first-hand observation in the assessed primitive at the assessed version.

**Contribution:** refutes `unstable` (the primitive is exposed, dispatch succeeds, completion fires in-session) AND establishes the inspection caveat directly (the in-session subagent has no liveness query). Anchors the verdict in observed behavior, not assertion (AC-7).

### 2. Open issue `anthropics/claude-code#63023` — "Background agents silently die on session pause/resume" (+ duplicates `#67524`, `#193366`)

OPEN, opened 2026-05-28, labels `area:agent-view` / `area:agents` / `bug`. Background agents (`run_in_background: true`) are terminated when the session is paused; on resume **no completion notification fires**, uncommitted worktree work is permanently lost, and the model **cannot distinguish a dead agent from a completed one** ("silence should always mean 'running', never 'dead'"). Two reproduced multi-day pause windows lost 3-of-3 and 6-of-6 background agents respectively, with zero notifications. The issue additionally reports persistent `Monitor` tasks reaped ~4× per 3-hour session (every session >40 min experiences ≥1 harness-kill on idle). The "Expected behavior" requests a `session_pause` checkpoint hook **that does not yet exist**. Duplicate `#67524` (closed-as-duplicate of `#63023`) adds: "`TaskList` returns 'No tasks found' for Agent-tool subagents"; no API to re-activate an interrupted subagent.

**Kind:** the canonical open-bug record for the **exact** FR-P2-7 capability.

**Contribution:** the load-bearing instability — refutes `stable` decisively. The capability FR-P2-7 needs (survive a closed session, surface results later) has an open, unresolved silent-data-loss bug. A primitive that *silently* loses work on pause is the exact anti-pattern this product exists to prevent (loud-fail doctrine), which is itself substantive input to the `partial` path (any 21.2 surface must invert this silence into a loud marker).

### 3. Open issue `anthropics/claude-code#68117` — background-task lifecycle divergence (reported against 2.1.170)

OPEN, three related defects in one session: (1) **dead background tasks keep rendering as "Running"** with live-ticking timers for 5–7 hours while the backend registry says they are gone (`TaskStop` → "No task found"); the panel and the task registry are not reconciled. (2) Background-shell completion wake-ups can be **lost**, freezing the parent agent forever mid-wait. (3) Mass "interrupted by user" with **no user interaction**, millisecond-identical across agents (an app lifecycle event — auto-update/sleep — recorded as a user interrupt), with no notification to the parent session.

**Kind:** corroborating open-bug record for the inspection + resume halves.

**Contribution:** refutes `stable` and refines the inspection caveat — the enumeration surface (`claude agents` panel) can actively *mislead* (dead → "Running"). This is why the `partial` path requires 21.2 to reconcile background-run status against git ground-truth (per-story-branch / PR landed state) rather than trusting agent-view liveness.

### 4. Official Claude Code changelog — `https://code.claude.com/docs/en/changelog`

Traversed at spike-time. Dual signal:

- **Shipped & multi-surfaced** (refutes `unstable`): `/resume` support for background sessions ("sessions started via `claude --bg` or agent view now appear alongside interactive ones, marked with `bg`"); `claude agents --json` with `--all` / `id` / `state` / `waitingFor`; a background daemon (`claude daemon status`); pre-warmed background workers; `claude --bg --exec '<command>'`; and **dynamic workflows** ("ask Claude to create a workflow and it orchestrates work across tens to hundreds of agents in the background").
- **Pervasive active churn** (refutes `stable`): background-session fixes ship release after release through the 2.1.179 range, many on the **cross-session-survival** path specifically — "re-attached after overnight retire losing their conversation and re-running the original prompt"; "losing their running background tasks when reattached after a Claude Code update"; "`--resume` not reporting background subagents that were running when the previous Claude Code process exited"; "respawn rejecting malformed resume IDs from corrupted state files"; "attach failing with EAUTH … after the daemon auto-updated"; "background agents that resumed work being shown under Completed".

**Kind:** the canonical historical record of background-primitive evolution.

**Contribution:** the two-halves source. Confirms the primitive is real, intended for autonomy, and improving — AND that the precise survive-a-pause path is under heavy repair. This is the `partially-stable` signature: shipped without a stability tier, actively stabilizing, not stabilized.

### 5. Anthropic autonomy positioning + community report

Anthropic's "Enabling Claude Code to work more autonomously" post lists "background tasks keep long-running processes active without blocking" as a shipped capability. A community report (Reddit, "Thoughts on Claude Code 2.1.139 Agent View & Background…") notes the surface is real but UX-rough: "You have to use `claude --bg` or `/bg` first to configure permissions, then 'push' it into Agent View afterward."

**Kind:** vendor positioning + independent community corroboration.

**Contribution:** confirms the primitive is intended-for-autonomy (refutes `unstable`) while corroborating the not-yet-smooth posture (supports `partially-stable`). No blanket `GA`/`stable` classification of the background-agent / FleetView primitive surfaces — mirroring the 7.1 plugin finding's "shipped without a formal stability tier" zone.

### 6. PRD / epic anchors + loud-fail doctrine

`prd.md` line 950 frames FR-P2-7 as "pending Claude Code stable background-agent primitive"; line 168 sets the revisit condition ("revisit when Claude Code ships a stable background-agent primitive"). `epics-phase-2.md` lines 194/198 name the user-outcome ("a session that can be closed without halting the loop … results surface in the next session via `/bmad-automation status`") and the standalone, spike-bounded framing. `CLAUDE.md` loud-fail doctrine: "every retry, every skip, every degradation must surface a marker."

**Kind:** the requirement framing + the doctrinal input.

**Contribution:** supplies the load-bearing capability definition and the doctrinal discriminator — a primitive whose failure mode is *silent* work loss is the exact thing the product inverts. This rules out path `implement` (which would propagate the silence) and shapes path `partial` (any landed surface must emit a loud marker when a background run cannot be confirmed).

## Outcome-decision flow

Three verdicts (`stable` / `partially-stable` / `unstable`) × the recommended-path space (`implement` / `named-fallback` / `partial`). The selected verdict + path is named first; each rejected alternative names the specific excluding evidence point. The deterministic Story-21.2 routing rule is recorded as data at the end.

### Verdict `partially-stable` + path `partial` — **SELECTED**

**Fires because** the primitive is split exactly along the FR-P2-7 capability boundary:

- **Functional half (refutes `unstable`):** first-hand dispatch succeeded and completed on CC 2.1.179 (evidence source #1); the `claude agents` background-agent subcommand is exposed (`claude --help`); the daemon-backed `claude --bg` surface, `/resume` for background sessions, and `claude agents --json` (`--all`/`state`/`waitingFor`) are shipped and actively hardened (evidence source #4).
- **Instability half (refutes `stable`):** the EXACT FR-P2-7 capability — a session closed without halting the loop, results surfacing later — carries an open silent-data-loss bug (`#63023` + duplicates, evidence source #2), the inspection surface can mislead (dead → "Running", `#68117`, evidence source #3), and the cross-session-survival path is under pervasive active churn (evidence source #4). No blanket stability classification (evidence source #5).
- **Per-capability split:** start = supported; in-session completion = supported; pause = unsupported (in-session subagents) / supported-with-caveats (daemon sessions); resume = supported-with-caveats; inspection = supported-with-caveats. The load-bearing cross-closed-session survive-and-surface capability is unreliable → `partially-stable` is the precise fit (see `## Capabilities tested`).

**Path `partial` — what Story 21.2 ships vs defers (specified here; NOT wired by this story):**

- **SHIPS.** Story 21.2 dispatches background runs via the **daemon-backed background-session primitive** (`claude --bg` / `claude agents`), **not** the in-session `Agent` `run_in_background` subagent path (which `#63023` proves loses work silently on pause), gated on `_bmad/automation/config.yaml` `background_execution: true` (default `false`). `/bmad-automation status` (FR48 extension) surfaces in-flight + completed background runs by reading `claude agents --json` (`--all`/`state`/`waitingFor`) **and reconciling against git ground-truth** (per-story-branch / PR landed state) rather than trusting agent-view liveness alone (per `#68117`). A loud-fail marker (`background-primitive-unstable`, or a sub-classified variant) is emitted to the PR bundle whenever a background run **cannot be confirmed landed** on resume — inverting the silent-loss failure mode into a loud, greppable one (loud-fail doctrine).
- **DEFERS.** The unqualified "close the session and forget it; results always surface" guarantee. That depends on `#63023`'s proposed `session_pause` checkpoint hook (does not yet exist) and the resolution of the cross-session-survival churn. **Revisit trigger (carried in `## Forward consumers`):** when `#63023` closes with a session-pause checkpoint / persistence guarantee, OR Claude Code publishes a stability statement for the `claude agents` / `--bg` / FleetView primitive, OR ≥2 consecutive CC minor releases ship with no background-session cross-session-survival regression fix.

Because the verdict is `partially-stable` (not `unstable`), **no `deferred-work.md` ledger entry is required** (AC-9): the deferred sub-capability + revisit trigger are recorded in THIS artifact, and Story 21.2 proceeds to implementation of the reduced `partial` surface. FR-P2-7 does **not** carry wholesale to Phase 3; only the unqualified-silent-survival sub-capability defers, with the named revisit trigger above.

### Verdict `stable` — REJECTED

**Excluding evidence point:** open issue `#63023` (evidence source #2) — silent data loss on the *exact* FR-P2-7 capability, still open at spike-time — together with the changelog's continuous stream of cross-session-survival fixes at the assessed 2.1.179 range (evidence source #4; e.g. "re-attached after overnight retire losing their conversation"). A primitive under active repair for the precise survive-a-pause path, with no published stability tier, is not `stable`. Had `stable` fired, Story 21.2 would have shipped the full unqualified fire-and-forget surface — over-promising a guarantee the primitive cannot keep.

### Verdict `unstable` — REJECTED

**Excluding evidence point:** the first-hand dispatch on CC 2.1.179 succeeded and completed (evidence source #1); the `claude agents` background subcommand is exposed; daemon-backed background sessions exist and are actively hardened (evidence source #4). The `/plugin`-analogue here — `claude agents` / `claude --bg` — does **not** return a not-implemented error and the primitive is not breaking on a majority of paths. "Unstable" (unavailable-or-breaking) over-states what was observed.

### Path `implement` — REJECTED

**Excluding evidence point:** path `implement` (the `stable`-verdict consequence) would have Story 21.2 ship the full unqualified surface; given `#63023`'s silent-loss behavior, that would propagate silent data loss to users — the exact loud-fail anti-pattern the product exists to invert (evidence source #6). Excluded with verdict `stable`.

### Path `named-fallback` — NAMED, did NOT fire (documented per AC-5 for pattern reusability)

Mirroring Story 7.1's outcome-3 worked example: had the verdict been `unstable` — **or** had the ≤2-day timebox expired without convergence (the loud-fail default-at-maximum; see `## Timebox & convergence note`) — Story 21.2 would ship the **named fallback**. Its concrete, ready-to-execute Story-21.2 consequences (specified here; **NOT wired by this story** — `dependencies.yaml` and the marker taxonomy are untouched, AC-8):

1. **`dependencies.yaml`** gains a `background-primitive` dependency entry with profile **`opt-in-skip`** and **`phase: "2"`**, init + runtime sub-classifications (mirroring the landed `lad` / `axe-core` / `pixelmatch` opt-in-skip shape: `condition: unconfigured`, `silent: true`), and `marker_class: background-primitive-unstable`. Silent on `background_execution: false` (the default).
2. **Marker taxonomy** pre-provisions the **`background-primitive-unstable`** marker class via a **PATCH bump** (closed-set 41 → 42) — Story 21.2's deliverable per its AC "marker class enumerated per PATCH bump regardless of path." (This class does not exist today; confirmed absent at spike-time.)
3. **Runtime:** setting `background_execution: true` against the unstable primitive emits the `background-primitive-unstable` marker and **falls back to foreground execution** — silent for the user-flow, loud (greppable) in the PR bundle.
4. **FR-P2-7 carries to Phase 3** with THIS spike assessment as the input artifact, recorded as a `deferred-work.md` ledger entry (named-and-routed per loud-fail doctrine).

This branch **did not fire** because the verdict is `partially-stable` (the primitive is functional), not `unstable`. The structure is preserved here so that (a) whichever path Story 21.2 ultimately validates, the fallback is a documented, ready-to-execute branch and not a fresh design exercise; and (b) the pattern has its instance-#3 worked example of a named fallback that did not fire.

### Story-21.2 routing rule (recorded as data — AC-3)

Story 21.2 reads its path from THIS file rather than re-deriving it:

- **`stable` OR `partially-stable` → Story 21.2 proceeds to implementation.** **[SELECTED — `partially-stable`]** Here: the reduced **`partial`** surface above (daemon-backed background-session dispatch + ground-truth-reconciled `/bmad-automation status` + loud-fail marker on the unconfirmable-on-resume path; defer the unqualified silent-survival guarantee). Marker class enumerated per PATCH bump (closed-set 41 → 42) regardless (Phase-2 epic-contract convention per `epics-phase-2.md` line 70 — same as Stories 14.x/15.x/16.x/20.x top-level additions; overrides the taxonomy-header MINOR default). No `deferred-work.md` entry required.
- **`unstable` → Story 21.2 ships the named fallback** (`dependencies.yaml` opt-in-skip + `background-primitive-unstable` marker pre-provisioned) **and FR-P2-7 carries to Phase 3** with this assessment as input. **[not taken]**

## Timebox & convergence note

This spike was conducted in a single Claude Code AI-Dev session on 2026-06-17. Unlike Story 7.1 (whose timebox carried a calendar-**minimum** the compressed session could not honor), Story 21.1's timebox is a calendar-**maximum** (≤2 days) with a loud-fail default — so the discipline to document is *convergence within the maximum*, not honoring a minimum.

- **Timebox-honored = true.** Spike-start = spike-end = 2026-06-17, within the ≤2-day maximum. The verdict converged same-day because the evidence was directly observable: a first-hand background-agent dispatch in CC 2.1.179, the open issue-tracker state (`#63023` + duplicates; `#68117`), and the changelog churn record. The maximum was therefore non-binding for the *selected* outcome.
- **Loud-fail default-at-maximum (documented for reusability; did NOT fire).** Had the ≤2-day calendar maximum been reached without converging on a verdict, the artifact would **default to `unstable` + `named-fallback`** per loud-fail doctrine — a bounded spike cannot silently expand. The default is a named, visible outcome (it would have triggered the `## Outcome-decision flow` § "Path `named-fallback`" branch, including the `deferred-work.md` FR-P2-7 → Phase 3 carry), not a silent extension and not a silent no-op. This default did not fire because the spike converged on `partially-stable` within hours.
- **Reusability note (per 7.1's worked-example discipline).** A future spike with a calendar-maximum that finds itself unable to converge should: (a) record `timebox-honored = false` with a one-line rationale; (b) fire the named-fallback default explicitly (record the verdict as `unstable` + `named-fallback`, open the `deferred-work.md` carry); (c) never silently extend the timebox. THIS section is the worked example of the maximum-with-loud-fail-default discipline, complementing 7.1's minimum-not-honored worked example.

## Forward consumers

### Story 21.2 — Background-Execution Implementation OR Named Fallback (FR-P2-7)

`21-2-background-execution-implementation-or-named-fallback-per-story-21-1` (per `_bmad-output/implementation-artifacts/sprint-status.yaml`) — the primary consumer. It reads THIS spike's verdict + path + routing rule on three seams:

1. **Verdict + path** — `partially-stable` → `partial`. Story 21.2 implements the reduced surface named in `## Outcome-decision flow` § "Path `partial`": daemon-backed background-session dispatch (`claude --bg` / `claude agents`), `/bmad-automation status` reconciled against git ground-truth, and a loud-fail `background-primitive-unstable`-class marker on the unconfirmable-on-resume path. It defers the unqualified silent-survival guarantee.
2. **Named-fallback spec (ready-to-execute)** — if Story 21.2's own validation (or a future regression) downgrades the verdict to `unstable`, the `dependencies.yaml` `opt-in-skip` + `phase: "2"` entry shape and the `background-primitive-unstable` marker class are pre-specified in `## Outcome-decision flow` § "Path `named-fallback`" — no fresh design exercise.
3. **Marker enumeration regardless of path** — Story 21.2 adds the `background-primitive-unstable` marker class via a **PATCH bump** (closed-set 41 → 42) (Phase-2 epic-contract convention per `epics-phase-2.md` line 70 — same as Stories 14.x/15.x/16.x/20.x; overrides the taxonomy-header MINOR default) "so the surface is wired for future activation" per its AC, whether the path is `partial` or `named-fallback`.

The seam is one-way: Story 21.2 reads THIS artifact + the per-convention row to compute its surface; THIS artifact does not reference Story 21.2's implementation (Story 21.2 owns the orchestrator/status/dependencies wiring). **This story does NOT transition 21.2 in sprint-status** (out of scope per AC-9).

### FR-P2-7 Phase-3 revisit — the deferred sub-capability

The `partial` path defers the unqualified "close the session and forget it; results always surface" guarantee. Its named revisit trigger (from `## Outcome-decision flow` § "Path `partial`"): when `anthropics/claude-code#63023` closes with a session-pause checkpoint / persistence guarantee, OR Claude Code publishes a stability statement for the `claude agents` / `--bg` / FleetView primitive, OR ≥2 consecutive CC minor releases ship with no background-session cross-session-survival regression fix. At that point the verdict re-audits toward `stable` and the path toward full `implement`. Because the verdict is `partially-stable` (not `unstable`), no `deferred-work.md` ledger entry is opened (AC-9); the carry lives in THIS artifact + the per-convention row's revisit conditions.

### Future spike-blockered stories — task-bounded-shape worked example #3

This is **instance #3** of the spike-with-bounded-timebox pattern (instance #1 = Story 5.7, calendar-week shape; instance #2 = Story 7.1, task-bounded shape; instance #3 = Story 21.1, task-bounded shape — the FIRST Phase-2 instance). It reuses the established shape: `docs/research-spikes/{spike-start-date}-{topic-slug}.md` path; the four canonical sections (`## Spike metadata` / `## Evidence sources reviewed` / `## Outcome-decision flow` / `## Forward consumers`) plus a `## Capabilities tested` table and a `## Timebox & convergence note`; verdict-enumeration with a named fallback documented even when it does not fire; the per-convention-row + closing-remark appends to `docs/extension-audit.md`. Per the pattern-selection decision aid (7.1 § "Forward consumers"), this spike used the **task-bounded** shape because its question was hands-on observational (it required dispatching a live background agent and reading the open issue-tracker state) — not spec-readable-upstream.
