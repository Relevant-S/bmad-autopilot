# /bmad-automation resume — story-loop reattachment + dispatch-resumption protocol

When the practitioner invokes `/bmad-automation resume <story-id>`, execute the protocol below. The canonical Python composition is `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/resume_command.py`'s `evaluate_resume` function — that function structurally encodes the recovery delegation + next-specialist determination + halt-vs-advance routing per Story 8.3 AC-1/AC-2/AC-3/AC-4; this prose IS the LLM-runtime protocol that names what each step is for and what to surface to the practitioner.

## Goal

Invoke the substrate, parse the directive, dispatch the next specialist OR halt with the diagnostic. Resume re-attaches to an existing in-flight story; it does NOT auto-start a fresh run (`/bmad-automation run` owns the entry sequence per Story 2.5 — `steps/run.md`). Resume is reattachment + dispatch-only.

## Substrate invocation

The substrate is invoked as a CLI from the orchestrator skill's runtime context:

```bash
uv --directory bmad-autopilot/tools/loud-fail-harness/ run bmad-automation-resume <story-id> --project-root <absolute-path>
```

Optional flag: `--run-state-path <path>` to override the default (`<project_root>/_bmad/automation/run-state.yaml`); production runs leave this unset.

Exit-code semantics per Story 8.3 AC-1 / AC-10:

- **`0`** — `resume-dispatch` OR `resume-already-terminal` (silent successes from a flow-control perspective).
- **`1`** — `resume-conflict-halt` OR `resume-no-run-state` (both halts; do NOT proceed to dispatch).
- **`2`** — harness-level error inside the substrate per Pattern 5 (Pydantic validation failure, recovery substrate raised an unexpected exception, etc.).

Stderr-line parsing protocol — the substrate emits structured single-line diagnostics with the `resume:` prefix per Pattern 5's machine-parseable-diagnostic discipline:

- `resume: resume-dispatch: next_specialist=<dev|review-bmad|qa>; current_state=<state>; story_id=<story-id>` — parse `next_specialist` for the dispatch step.
- `resume: resume-already-terminal: story_id=<story-id> is already at <terminal-state>; nothing to do`.
- `resume: recovery-state-conflict: ...` — Story 8.2's marker diagnostic propagated verbatim through the resume substrate.
- `resume: no-in-flight-run-found-for-story-id: <story-id>; probed run-state path: <path>; remediation: ...; for inspection of all in-flight stories, run /bmad-automation status (Story 8.5 — when landed)`.

## Branch on outcome

Branch on the parsed exit code + the `resume:` prefix that follows.

### `resume-dispatch`

The substrate has run `cross_state_recovery.evaluate_recovery` (Story 8.2) against the on-disk `run-state.yaml`; recovery succeeded (`recovery-clean` OR `recovery-rebuilt`) and `final_run_state.current_state` is non-terminal. Read the printed `next_specialist` field from the substrate's stderr output.

Thread through to `steps/dispatch.md`'s LLM-runtime protocol with:

- `specialist=<next_specialist>` (one of `"dev"`, `"review-bmad"`, `"qa"` per the Story 8.3 AC-4 closed map).
- `story_id=<story-id>`.
- `run_state_path=<resolved>` (the same path the substrate read from).
- The post-recovery `final_run_state` is on disk; `steps/dispatch.md`'s pre-dispatch step (build the payload via `build_dispatch_payload`) reads it through the canonical run-state loader.

Construct the `event_log_appender` for THIS resume-induced dispatch by reusing the existing per-run events.jsonl path: `event_log_path = default_event_log_path(qa_evidence_root=pathlib.Path("_bmad-output/qa-evidence"), story_id=story_id, run_id=<final_run_state.run_id>)` (Story 2.12's `loud_fail_harness.event_streaming` substrate). The `run_id` comes from the post-recovery `final_run_state.run_id` field — NOT a fresh `run_id` factory — so the resume-induced dispatch APPENDS to the existing per-run events.jsonl, preserving the per-run audit trail per Story 2.12's durability invariant.

Once the dispatch returns, surface the `specialist-returned` event id + envelope status to the practitioner per Story 2.5's run-summary discipline. The orchestrator's flow-policy decision (advance vs. retry vs. escalate) is driven by the envelope's `status` field via `evaluate_envelope` at the orchestrator's next-step-loop site (NOT inside the dispatch callback — sensor-not-advisor).

### `resume-already-terminal`

The substrate has determined the story is at `done` or `escalated`. Surface a one-line summary to the practitioner:

> `resume: story <story-id> is already at <terminal-state>; nothing to do. To inspect details, run /bmad-automation status <story-id> (Story 8.4 — when landed).`

Exit cleanly (exit code 0). Do NOT proceed to dispatch. Do NOT emit additional orchestrator events.

### `resume-conflict-halt`

The substrate's delegated `cross_state_recovery.evaluate_recovery` returned `recovery-conflict-halt`; the `recovery-state-conflict` marker IS in `final_run_state.active_markers` per Story 8.2's emission. The substrate's stderr line is already prefixed `resume: recovery-state-conflict: ...` (Story 8.2's diagnostic format propagated unchanged).

Surface the diagnostic to the practitioner verbatim. The orchestrator skill MAY also surface the practitioner-facing remediation pointer:

> The `recovery-state-conflict` marker has been recorded in run-state; manual triage is required before re-running resume. See `schemas/marker-taxonomy.yaml:372-380` for marker-class details and the `recovery-state-conflict` diagnostic for which stores disagreed.

Exit (exit code 1). Do NOT proceed to dispatch. Do NOT re-emit the marker — it is already recorded by Story 8.2's `record_marker_with_context` invocation per Story 8.2 AC-7.

### `resume-no-run-state`

The substrate's pre-check found NO `run-state.yaml` at the resolved path; `evaluate_recovery` was NOT invoked. The diagnostic is the named-invariant `no-in-flight-run-found-for-story-id` (NOT a marker — per `epics.md:3288` verbatim "halts with a named-invariant diagnostic").

Surface the diagnostic to the practitioner verbatim. The diagnostic already includes the remediation pointer to `/bmad-automation run <story-id>` for fresh-start AND a pointer to `sprint-status.yaml` for verifying the story-id matches an in-flight story.

Exit (exit code 1). Do NOT proceed to dispatch. Do NOT auto-start a fresh run — that is `/bmad-automation run`'s job (Story 2.5; `steps/run.md`), not resume's.

## Loud-fail discipline

- Substrate-level errors (exit code 2 from `bmad-automation-resume`) propagate the substrate's stderr text to the practitioner. The resume command does NOT auto-retry on substrate-level errors. Pattern 5 chained-exception discipline is observed inside the substrate (`ResumeCommandError` wraps `CrossStateRecoveryError` via `from exc`).
- Dispatch-induced events (`specialist-dispatched`, `specialist-returned`, `state-transition`) are emitted by `steps/dispatch.md`'s LLM-runtime protocol — same code path as `/bmad-automation run`'s step (f). The resume substrate ITSELF does NOT emit orchestrator events; substrate output is the directive (`ResumeOutcome`), the skill's runtime threads through to the dispatch step on `resume-dispatch`.
- The resume command does NOT modify the practitioner's working tree, does NOT commit changes, does NOT advance lifecycle state outside what `cross_state_recovery.evaluate_recovery`'s rebuild path does (NFR-R7 + NFR-R8 per Story 8.3 AC-1).

## Cross-references

- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/resume_command.py` — the substrate library (Story 8.3).
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/cross_state_recovery.py` — the consumed recovery substrate (Story 8.2); `evaluate_recovery` is the canonical recovery decision.
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/lifecycle_state_machine.py` — `LIFECYCLE_TRANSITIONS` + `TERMINAL_STATES` (the AC-4 next-specialist closed map's source-of-truth).
- `skills/bmad-automation/steps/dispatch.md` — the LLM-runtime dispatch protocol the resume command threads through to on `resume-dispatch`.
- `bmad-autopilot/schemas/marker-taxonomy.yaml` lines 372-380 — `recovery-state-conflict` marker class declaration.
- `_bmad-output/planning-artifacts/prd.md` line 881 — FR47 (`/bmad-automation resume [story-id]`).
- `_bmad-output/planning-artifacts/prd.md` line 951 — NFR-R7 (no destructive resume).
- `_bmad-output/planning-artifacts/prd.md` line 952 — NFR-R8 (cross-state consistency).
- `_bmad-output/planning-artifacts/prd.md` line 946 — NFR-R2 (crash recovery).
- `_bmad-output/planning-artifacts/epics.md` lines 3272-3298 — Story 8.3 epic AC.
- `_bmad-output/planning-artifacts/architecture.md` ADR-005 (cross-state consistency protocol).
