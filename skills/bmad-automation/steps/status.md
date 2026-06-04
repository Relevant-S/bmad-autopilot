# /bmad-automation status — single-story mid-loop inspection (read-only)

When the practitioner invokes `/bmad-automation status <story-id>`, execute the protocol below. The canonical Python composition is `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/status_command.py`'s `inspect_story` function — that function structurally encodes the run-state load + retry-round resolution + per-specialist log dir projection + payload assembly per Story 8.4 AC-1/AC-2/AC-3; this prose IS the LLM-runtime protocol that names what each step is for and what to surface to the practitioner.

## Goal

Invoke the substrate, parse the rendered output, surface to the practitioner verbatim. Status is read-only inspection ONLY — no specialist dispatch, no state mutation. The command exposes current lifecycle state, retry history, active loud-fail markers, the latest specialist envelope, the per-specialist log directory pointer, the branch name, the run-state file path, and the story-doc pointer for a single named story-id per FR48 + NFR-O4 verbatim ("without advancing state or mutating run-state").

## Substrate invocation

The substrate is invoked as a CLI from the orchestrator skill's runtime context:

```bash
uv --directory bmad-autopilot/tools/loud-fail-harness/ run bmad-automation-status <story-id> --project-root <absolute-path>
```

Optional flags:

- `--json` — emit machine-consumable JSON output instead of the human-readable render. Implies `--resolve-retry-rounds=True` per Story 8.4 AC-5 (tooling consumers want full retry-round detail).
- `--resolve-retry-rounds` — resolve every populated `RetryAttemptRef` into a fully-loaded `RetryRoundArtifacts` payload. Default OFF on the CLI per Story 8.4's cheap-default invariant: Story 8.5's no-args enumeration loop CANNOT afford per-story filesystem resolution, so the substrate is fast-by-default.
- `--run-state-path <path>` — override the default (`<project_root>/_bmad/automation/run-state.yaml`). Production runs leave this unset.
- `--qa-evidence-root <path>` — override the default (`<project_root>/_bmad-output/qa-evidence`). Production runs leave this unset.
- `--repo-root <path>` — override the default (`<project_root>`) for retry-round artifact resolution.

Exit-code semantics per Story 8.4 AC-1 / AC-12:

- **`0`** — `status-found` (silent success; the rendered inspection is printed to stdout).
- **`1`** — `status-no-run-state` (halt with named-invariant diagnostic to stderr).
- **`2`** — harness-level error inside the substrate per Pattern 5 (Pydantic validation failure, run-state access failure, recovery substrate raised an unexpected exception).

## Branch on argument presence

The slash command `/bmad-automation status [<id>] [--epic <epic-id>] [--sprint <sprint-id>]` accepts an OPTIONAL story-id argument OR an `--epic <epic-id>` flag OR a `--sprint <sprint-id>` flag. The runtime branches on argument presence:

- **With `--sprint <sprint-id>`** (sprint-scope inspection per Story 16.4) — invoke `bmad-automation-status-sprint --sprint <sprint-id>` per the `## Sprint-scope inspection protocol` section near the end of this file. The single-story + epic + no-args protocols are bypassed entirely on this branch.
- **With `--epic <epic-id>`** (epic-scope inspection per Story 15.4) — invoke `bmad-automation-status-epic --epic <epic-id>` per the `## Epic-scope inspection protocol` section near the end of this file. The single-story + no-args protocols are bypassed entirely on this branch.
- **With `<story-id>`** (single-story inspection per Story 8.4) — invoke `bmad-automation-status <story-id>` per the `## Substrate invocation` section above AND follow the `## Branch on outcome` protocol below.
- **Without any argument** (no-args multi-story listing per Story 8.5, with per-epic grouping per Story 15.4 and per-sprint grouping per Story 16.4) — invoke `bmad-automation-status-list` per the `## No-args multi-story listing protocol` section near the end of this file. The single-story protocol is bypassed entirely on this branch.

## Branch on outcome

Branch on the parsed exit code.

### `status-found` (exit 0)

The substrate has loaded the run-state from disk; the inspection succeeded; the rendered output (human or JSON depending on `--json`) is on stdout. The orchestrator skill surfaces the rendered output verbatim to the practitioner. No further action — status is read-only inspection ONLY.

The human render (default) carries six sections:

- `## Lifecycle state` — current state, branch, run_id, run_state_path, story_doc.
- `## Active loud-fail markers` — alphabetical-by-class via `marker_wiring.compute_alphabetical_marker_order`; renders `(no active markers)` placeholder when empty.
- `## Retry history` — per-round summary lines mirroring Story 5.8's escalation-bundle structure (`bundle_assembly_escalation._render_retry_history`); renders `(no retries — story has not entered the retry seam)` placeholder when empty; dangling refs surface as `(round-NN — DANGLING: <path>)` lines per Story 8.4 AC-10's structural-display discipline.
- `## Latest specialist envelope` — `dispatched_specialist`, envelope status preview, and `per_specialist_log_dir` pointer (the practitioner inspects the directory directly via the filesystem for full per-specialist envelope history; status does NOT enumerate per NFR-O4 read-only invariant).
- `## Cost-to-date by specialist` — per-specialist cost from `cost_to_date_by_specialist` (`dev`, `review-bmad`, `qa`, `lad`).

The JSON render (`--json` flag) emits the canonical `StoryInspection` model serialization via `model_dump_json(indent=2)`; field declaration order is load-bearing for byte-stable output.

### `status-no-run-state` (exit 1)

The substrate's pre-check found NO `run-state.yaml` at the resolved path; the load helper was NOT invoked. The diagnostic is the named-invariant `no-in-flight-run-found-for-story-id` (NOT a marker — per `epics.md:3322-3325` verbatim "the command halts with a named-invariant diagnostic").

Surface the diagnostic to the practitioner verbatim. The diagnostic already includes the practitioner-facing remediation pointers:

- (a) start a fresh run via `/bmad-automation run <story-id>`;
- (b) verify the story-id matches an in-flight story by listing all stories via `/bmad-automation status` (Story 8.5 — when landed).

Exit (exit code 1). Do NOT proceed to dispatch. Do NOT auto-start a fresh run — that is `/bmad-automation run`'s job (Story 2.5; `steps/run.md`), not status's.

## Loud-fail discipline

- Substrate-level errors (exit code 2 from `bmad-automation-status`) propagate the substrate's stderr text to the practitioner. The status command does NOT auto-retry on substrate-level errors. Pattern 5 chained-exception discipline is observed inside the substrate (`StatusCommandError` wraps `CrossStateRecoveryError` AND `OSError` via `from exc`).
- The status command does NOT emit orchestrator events; the substrate does NOT touch the event log.
- The status command does NOT emit any marker class. Dangling retry-round references surface as a structural field `dangling_retry_round_refs` in the inspection payload — NOT as a marker emission per Story 8.4 AC-10's no-emission discipline + NFR-O4's read-only invariant.

## No mutation invariant

Status NEVER writes run-state, NEVER commits, NEVER dispatches specialists, NEVER mutates the story-doc, NEVER mutates sprint-status, NEVER touches per-specialist logs, NEVER appends to events.jsonl, NEVER edits deferred-work.md, and NEVER touches the git working tree per NFR-O4 verbatim.

If the practitioner needs to advance state, they MUST invoke `/bmad-automation run` (fresh story-loop entry) or `/bmad-automation resume` (cross-state recovery + dispatch resumption) — the inspection surface is structurally read-only.

The substrate's `inspect_story` function does NOT invoke `cross_state_recovery.evaluate_recovery` because that function's rebuild path mutates run-state via the `run_state_writer` DI seam — even if run-state and story-doc disagree, status surfaces the run-state's recorded values WITHOUT correcting them. The recovery-on-disagreement path is `/bmad-automation resume`'s job, not `/bmad-automation status`'s.

## No-args multi-story listing protocol

When the practitioner invokes `/bmad-automation status` without a `<story-id>` argument, dispatch to the Story 8.5 multi-story enumeration substrate. THIS is structurally distinct from the single-story inspection protocol above — both surfaces share the `/bmad-automation status` slash command and dispatch on argument presence per the `## Branch on argument presence` section near the top.

### Goal

Enumerate every story with non-terminal automator state (across run-state files under `_bmad/automation/` AND non-terminal `development_status` entries in `_bmad-output/implementation-artifacts/sprint-status.yaml`); detect orphan run-state entries whose story-doc has been deleted, renamed, or moved; emit `orphan-run-state-detected` (Story 1.4 v1 27-class taxonomy entry registered at `schemas/marker-taxonomy.yaml:382`) per orphan; surface a compact per-row summary `(story_id, current_state, marker_count, last_activity_timestamp, branch_name)` per `epics.md:3342` verbatim — projecting Story 8.4's canonical `status_command.inspect_story` per enumerated story-id with NO parallel inspection logic per `epics.md:3318-3320` verbatim.

### Substrate invocation

```bash
uv --directory bmad-autopilot/tools/loud-fail-harness/ run bmad-automation-status-list --project-root <absolute-path>
```

Optional flags:

- `--json` — emit machine-consumable JSON output instead of the human-readable render. The JSON output's per-row `last_activity_timestamp` is ISO-8601 from `last_envelope.timestamp`; orphan rows carry `is_orphan: true` for tooling consumers.
- `--automation-dir <path>` — override the default (`<project_root>/_bmad/automation`). Production runs leave this unset.
- `--implementation-artifacts-dir <path>` — override the default (`<project_root>/_bmad-output/implementation-artifacts`). Production runs leave this unset.
- `--qa-evidence-root <path>` — override the default (`<project_root>/_bmad-output/qa-evidence`).
- `--repo-root <path>` — override the default (`<project_root>`).

NOTE on the cheap-default invariant: the no-args enumeration substrate invokes Story 8.4's `inspect_story` per candidate with `resolve_retry_rounds=False` per `epics.md:3320` verbatim — multi-story enumeration cannot afford per-story retry-round filesystem resolution. The JSON output does NOT include resolved retry rounds (those are accessed via `bmad-automation-status <story-id> --json` for a single named story-id).

Exit-code semantics per Story 8.5 AC-1:

- **`0`** — `listing-found` OR `listing-empty` (silent success; both are non-error outcomes; orphan emissions are conveyed through the rendered listing structurally, NOT through the exit code).
- **`2`** — harness-level error inside the substrate per Pattern 5 (Pydantic validation failure, etc.).

There is NO exit-code-1 path here — distinct from the single-story `bmad-automation-status` CLI's `status-no-run-state` halt. The multi-story enumeration has no analogous "named-story-not-found" halt; an empty listing is the steady-state outcome for a project between story loops.

### Branch on outcome

Branch on the parsed `outcome.action`:

- **`listing-found`** (exit 0) — substrate prints the rendered listing (human-readable per `render_story_listing_human` OR JSON per `render_story_listing_json` depending on `--json`); the orchestrator skill surfaces verbatim. Orphan rows have already had their `orphan-run-state-detected` markers emitted by the substrate via `marker_recorder` per AC-3; no further action.
- **`listing-empty`** (exit 0) — substrate prints the empty-listing message `(no stories with non-terminal automator state found)` via `render_listing_empty_message`; the orchestrator skill surfaces verbatim. No marker emission (no orphan ⇒ no `orphan-run-state-detected`); silent success.

### Per-epic grouping (Story 15.4 — additive)

The no-args listing additionally discovers the epic-run-state cache(s) under `_bmad/automation/` (at Epic 15 scope, the single `epic-run-state.yaml`) and GROUPS the per-story rows whose `story_id ∈ EpicRunState.story_ids` under a per-epic header surfacing the epic's `epic_id` + non-terminal `current_state` (a `## Epics` section with `### <epic-id> [<state>]` sub-headers). Per-story rows that are NOT a member of any discovered epic render UNGROUPED in the `## Stories` section exactly as before. Terminal `epic-complete` epics are omitted from the grouping headers (mirroring the per-story non-terminal filter). This is PURELY ADDITIVE: a project that never ran `run --epic` has byte-identical no-args human + JSON output (no `## Epics` section; no `epic_groups` key) — the bit-identity guard. The `orphan-run-state-detected` emission, the empty-listing steady state, and the read-only run-state invariant are UNCHANGED.

### Sprint grouping (Story 16.4 — additive)

The no-args listing ALSO discovers the sprint-run-state cache under `_bmad/automation/` (at Epic 16 scope, the single `sprint-run-state.yaml`, loaded via `epic_run_state.load_sprint_run_state`) and surfaces a per-sprint grouping ON TOP of the per-epic grouping: a `## Sprints` section with `### <sprint-id> [<state>]` sub-headers naming the member epics (which already group their own stories via the `## Epics` section). Terminal `sprint-complete` sprints are omitted (mirroring the per-epic non-terminal filter). Like the per-epic grouping, this is PURELY ADDITIVE: a project that never ran `run --sprint` has byte-identical no-args human + JSON output (no `## Sprints` section; no `sprint_groups` key) — the same bit-identity guard. The sprint-run-state file is read-only here too (the mtime + sha256 no-mutation witness is `tests/test_multi_story_status.py::test_enumerate_stories_does_not_mutate_sprint_run_state_file`).

### Loud-fail discipline

- Substrate-level errors (exit code 2) propagate to the orchestrator skill which surfaces them to the practitioner. The multi-story listing does NOT auto-retry on substrate-level errors. Pattern 5 chained-exception discipline is observed inside the substrate (`MultiStoryStatusError` analogous in shape to `StatusCommandError`).
- Orphan emission via `marker_recorder("orphan-run-state-detected", context)` is the substrate's ONLY write surface; the marker context carries `story_id`, `run_state_file_path`, `expected_story_doc_dir`, and a `remediation:` clause naming the two paths per `epics.md:3351-3355` verbatim: (a) purge orphan run-state via direct filesystem `rm <run_state_file_path>` after triage; (b) recover missing story-doc from version control (e.g., `git log --diff-filter=D` to locate the deletion commit).

### Mutation surface

The no-args listing IS a write surface for the `orphan-run-state-detected` marker class — the substrate's only write. It does NOT mutate run-state, story-doc, sprint-status, per-specialist logs, events.jsonl, deferred-work.md, or the git working tree. Orphan run-state files are NOT auto-purged per `epics.md:3351-3355` verbatim ("`/bmad-automation` does NOT auto-purge orphans — the destructive action requires explicit practitioner intent (mirroring Story 7.6's non-destructive guard pattern)") — purge requires explicit practitioner intent (`rm <orphan_run_state_path>`).

The substrate is read-only against run-state contents per AC-6: every run-state file's mtime + sha256 are byte-identical before/after `enumerate_stories` invocation (the structural witness is `tests/test_multi_story_status.py::test_enumerate_stories_does_not_mutate_run_state_files`).

## Epic-scope inspection protocol

When the practitioner invokes `/bmad-automation status --epic <epic-id>`, dispatch to the Story 15.4 epic-status substrate. THIS is structurally distinct from the single-story and no-args protocols above — all three share the `/bmad-automation status` slash command and dispatch on argument presence per the `## Branch on argument presence` section near the top.

### Goal

Surface — read-only, with NO state mutation (FR48 + NFR-O4 at epic scope; zero write surface) — the epic lifecycle state (`epic-in-progress` / `epic-paused-on-escalation` / `epic-paused-on-budget` / `epic-complete`), the per-story status list (in the epic-defined cache order), the per-epic retry-budget consumption (used / total), the per-epic `active_markers` inline, per-story marker presence (projected from Story 8.4's `status_command.inspect_story` per contained story — NFR-R8: no fourth canonical store), and pointers to the epic-run-state file + the epic-level PR bundle. The canonical Python composition is `epic_status_command.inspect_epic`; this prose IS the LLM-runtime protocol naming what each step is for.

### Substrate invocation

```bash
uv --directory bmad-autopilot/tools/loud-fail-harness/ run bmad-automation-status-epic --epic <epic-id> --project-root <absolute-path>
```

Optional flags:

- `--json` — emit the canonical `EpicInspection` model serialization (`model_dump_json(indent=2)`; field declaration order is load-bearing for byte-stable output) instead of the human-readable render.
- `--epic-run-state-path <path>` — override the default (`<project_root>/_bmad/automation/epic-run-state.yaml`). Production runs leave this unset.
- `--repo-root <path>` — override the default (`<project_root>`), used to compute the epic-PR-bundle pointer.

Exit-code semantics per Story 15.4 AC-1 / AC-6 (mirroring Story 8.4's 0/1/2 split):

- **`0`** — `epic-status-found` (silent success; the rendered inspection is printed to stdout).
- **`1`** — `epic-status-no-run-state` (no cache at the resolved path) OR `epic-id-mismatch` (the cache is for a different epic). Both are named-invariant diagnostics to stderr (`no-in-flight-epic-run-found-for-epic-id` / `epic-id-mismatch`), NOT markers.
- **`2`** — harness-level error inside the substrate per Pattern 5 (malformed cache parse, Pydantic validation failure, unexpected exception).

### Branch on outcome

- **`epic-status-found`** (exit 0) — the rendered output (human or JSON) is on stdout; surface it verbatim. The human render carries: `## Epic lifecycle state` (state + `epic_id` + `run_id`); `## Per-story status` (one row per cache `story_ids` entry — `story_id → per_story_status`, with `markers=<count>` for dispatched stories and a `(not yet dispatched — no per-story run-state)` annotation for stories the epic loop has not dispatched yet — AC-3 graceful degrade); `## Per-epic retry budget` (the consumption line `Consumed <n> of <budget> ...`); `## Active loud-fail markers` (the per-epic `active_markers` alphabetical via `marker_wiring.compute_alphabetical_marker_order`, `(no active markers)` placeholder when empty); `## Pointers` (the epic-run-state file path + the epic-level PR-bundle path). For full per-story marker/retry-history detail, drill into the epic-PR-bundle pointer (its per-story rows point to each story's own canonical artifact).
- **`epic-status-no-run-state`** / **`epic-id-mismatch`** (exit 1) — surface the named-invariant diagnostic verbatim (it already includes the remediation pointers: start a fresh epic run via `/bmad-automation run --epic <epic-id>`; list all in-flight stories/epics via no-args `/bmad-automation status`). Do NOT proceed to dispatch. Do NOT auto-start a fresh epic run — that is `/bmad-automation run --epic`'s job (`steps/run-epic.md`).

### Mutation surface

The `--epic` path has ZERO write surface — even less than the no-args listing (which emits `orphan-run-state-detected`). It NEVER writes the epic-run-state (no `advance_epic_run_state`), NEVER invokes `cross_state_recovery`, NEVER dispatches specialists, NEVER mutates story-docs / sprint-status / per-specialist logs / `events.jsonl` / `deferred-work.md`, NEVER touches the git working tree, and emits NO marker class. The per-story marker projection reuses Story 8.4's read-only `inspect_story` UNCHANGED. The structural witness asserts the epic-run-state file's mtime + sha256 are byte-identical before/after (`tests/test_epic_status_command.py::test_inspect_epic_does_not_mutate_cache`).

## Sprint-scope inspection protocol

When the practitioner invokes `/bmad-automation status --sprint <sprint-id>`, dispatch to the Story 16.4 sprint-status substrate. THIS is structurally distinct from the single-story, epic, and no-args protocols above — all four share the `/bmad-automation status` slash command and dispatch on argument presence per the `## Branch on argument presence` section near the top.

### Goal

Surface — read-only, with NO state mutation (FR48 + NFR-O4 at sprint scope; zero write surface) — the sprint-state-tree (sprint → epics → stories) with rolled-up aggregate cost, per-sprint retry-budget consumption (used / total), re-derived escalation rate, and the scoped active-markers union (sprint ∪ per-epic). The query REUSES Story 16.3's `sprint_status_artifact.build_sprint_status_artifact` aggregate read (the rollup over the sprint-run-state cache + each per-epic `EpicRunState` cache) and renders the returned model — it does NOT re-walk the caches and does NOT write the sprint-status `.md` artifact (that is 16.3's `assemble_*` at sprint close). Per-story marker drill-down is POINTED TO (`status --epic` / `status <story-id>`), not re-projected at sprint scale (NFR-R8). The canonical Python composition is `sprint_status_command.inspect_sprint`; this prose IS the LLM-runtime protocol naming what each step is for.

### Substrate invocation

```bash
uv --directory bmad-autopilot/tools/loud-fail-harness/ run bmad-automation-status-sprint --sprint <sprint-id> --project-root <absolute-path>
```

Optional flags:

- `--json` — emit the canonical `SprintStatusArtifact` model serialization (`model_dump_json(indent=2)`; field declaration order is load-bearing for byte-stable output) instead of the human-readable render.
- `--sprint-run-state-path <path>` — override the default (`<project_root>/_bmad/automation/sprint-run-state.yaml`). Production runs leave this unset.
- `--repo-root <path>` — override the default (`<project_root>`), threaded to `build_sprint_status_artifact` for per-epic cache addressing + the sprint-status-artifact pointer.

Exit-code semantics per Story 16.4 AC-1 / AC-6 (mirroring Story 15.4's 0/1/2 split):

- **`0`** — `sprint-status-found` (silent success; the rendered inspection is printed to stdout).
- **`1`** — `sprint-status-no-run-state` (no cache at the resolved path) OR `sprint-id-mismatch` (the cache is for a different sprint). Both are named-invariant diagnostics to stderr (`no-in-flight-sprint-run-found-for-sprint-id` / `sprint-id-mismatch`), NOT markers.
- **`2`** — harness-level error inside the substrate per Pattern 5 (malformed cache parse, Pydantic validation failure, naive-`generated_at`, unexpected exception).

### Branch on outcome

- **`sprint-status-found`** (exit 0) — the rendered output (human or JSON) is on stdout; surface it verbatim. The human render carries: `## Sprint lifecycle state` (state + `sprint_id` + `run_id` + `generated_at`); `## Sprint state tree` (each per-epic row — `epic_id → status`, cost, retries — with its per-story rows nested beneath, plus an `(unassigned)` group for stories with no epic); `## Aggregate cost`; `## Per-sprint retry budget` (`Used <n> of <budget>`); `## Escalation rate` (`Escalated <x> of <y> completed = <r>%`); `## Active loud-fail markers` (the scoped union inline WITH each marker's `scope` — `sprint` or `epic:<epic-id>` — `(no active markers)` placeholder when empty); `## Pointers` (the sprint-run-state file path + the sprint-status-artifact path + the AC-3 drill-down command pointers). For per-epic marker detail drill into `status --epic <epic-id>`; for per-story marker + retry-history detail drill into `status <story-id>` — the multi-scope observability chain (`status --sprint` → `status --epic` → `status <story-id>`).
- **`sprint-status-no-run-state`** / **`sprint-id-mismatch`** (exit 1) — surface the named-invariant diagnostic verbatim (it already includes the remediation pointers: start a fresh sprint run via `/bmad-automation run --sprint <sprint-id>`; list all in-flight stories/epics/sprints via no-args `/bmad-automation status`). Do NOT proceed to dispatch. Do NOT auto-start a fresh sprint run — that is `/bmad-automation run --sprint`'s job (`steps/run-sprint.md`).

### Mutation surface

The `--sprint` path has ZERO write surface — like the `--epic` path. It NEVER assembles the sprint-status `.md` artifact (no `assemble_sprint_status_artifact`), NEVER writes the sprint-run-state (no `advance_sprint_run_state`), NEVER invokes `cross_state_recovery`, NEVER dispatches the epic/story loops, NEVER mutates story-docs / sprint-status / per-epic caches / per-specialist logs / `events.jsonl` / `deferred-work.md`, NEVER touches the git working tree, and emits NO marker class. `build_sprint_status_artifact` is the pure rollup (write-free). The structural witness asserts the sprint-run-state file's AND every per-epic cache file's mtime + sha256 are byte-identical before/after (`tests/test_sprint_status_command.py::test_inspect_sprint_does_not_mutate_caches`).

## Cross-references

- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/multi_story_status.py` — the no-args multi-story enumeration substrate (Story 8.5; extended with additive per-epic grouping in Story 15.4 and per-sprint grouping in Story 16.4).
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/epic_status_command.py` — the read-only `status --epic` epic-status substrate (Story 15.4; `inspect_epic` + renderers + `bmad-automation-status-epic` CLI).
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/sprint_status_command.py` — the read-only `status --sprint` sprint-status substrate (Story 16.4; `inspect_sprint` + renderers + `bmad-automation-status-sprint` CLI; REUSES `build_sprint_status_artifact`).
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/sprint_status_artifact.py` — `build_sprint_status_artifact` (the pure rollup `status --sprint` reuses; Story 16.3) + `compute_sprint_status_artifact_path` (the `## Pointers` target).
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/epic_run_state.py` — `EpicRunState` / `SprintRunState` cache models + the read-only `load_epic_run_state` (Story 15.4) and `load_sprint_run_state` (Story 16.4) public loaders.
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly_epic.py` — `compute_epic_bundle_path` (the epic-PR-bundle pointer surfaced by `status --epic`).
- `bmad-autopilot/schemas/marker-taxonomy.yaml:382` — the `orphan-run-state-detected` marker class registration (Story 1.4 v1 27-class taxonomy).
- `_bmad-output/planning-artifacts/epics.md:3331-3363` — Story 8.5 epic AC.
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/status_command.py` — the substrate library (Story 8.4).
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/cross_state_recovery.py` — the run-state load helper consumed via private same-package import (`_load_run_state_from_disk`) per Story 8.3's Dev's-call precedent.
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/retry_history.py` — `resolve_retry_round` + `detect_dangling_refs` (Story 5.5; the retry-round resolution helpers).
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/run_state.py` — `RunState` model (the inspection-payload's source-of-truth via direct passthrough).
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/specialist_dispatch.py` — `LOG_PATH_TEMPLATE` (Story 2.6; the per-specialist log dir projection source).
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/orchestrator_run_entry.py` — `default_story_doc_resolver` (Story 2.5; the story-doc resolver consumed with graceful-degrade on failure).
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/marker_wiring.py` — `compute_alphabetical_marker_order` (the deterministic ordering invariant for the active-markers section).
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly_escalation.py` — `_render_retry_history` (Story 5.8; the human-render structure for retry-history sections THIS step's renderer mirrors).
- `_bmad-output/planning-artifacts/prd.md` line 876 — FR48 (`/bmad-automation status [story-id]`).
- `_bmad-output/planning-artifacts/prd.md` line 877 — FR48b (no-args multi-story listing — Story 8.5).
- `_bmad-output/planning-artifacts/prd.md` line 949 — NFR-R5 (retry-history preservation visibility).
- `_bmad-output/planning-artifacts/prd.md` line 983 — NFR-O4 (status command completeness — read-only invariant verbatim).
- `_bmad-output/planning-artifacts/epics.md` lines 3300-3329 — Story 8.4 epic AC.
- `_bmad-output/planning-artifacts/epics.md` lines 3331-3363 — Story 8.5 epic AC (the multi-story listing that projects from THIS substrate).

## Note on Story 8.5's projection

The status command is the canonical inspection function Story 8.5 will project from. Story 8.5's no-args listing calls `inspect_story` per enumerated story-id and projects the resulting `StoryInspection` payload to a row-summary shape (story-id, current state, marker count, last activity timestamp, branch name) per `epics.md:3342` verbatim. The inspection-payload shape declared in `status_command.py` IS the single source-of-truth — there is no parallel inspection logic in Story 8.5 per `epics.md:3318-3320` verbatim.
