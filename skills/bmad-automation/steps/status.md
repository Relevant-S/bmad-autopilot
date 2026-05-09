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

## Cross-references

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
