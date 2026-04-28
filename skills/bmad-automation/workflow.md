# BMAD Automator Orchestrator Workflow

## Goal

Orchestrate the seam-transition flow for the BMAD Agent Development Automator: route the practitioner's four slash commands (`run`, `status`, `resume`, `init`) through the appropriate sub-step, compose the substrate-shared Python helpers (Story 2.2's `advance_run_state`, Story 2.3's `create_story_branch`, Story 2.4's `commit_transition`, Story 2.5's `run_story_loop_entry`) at each lifecycle seam, and emit schema-validated orchestrator events to the run-state log without ever bypassing the helper layer.

## Subcommand routing

The skill dispatches to one of four sub-step files based on the slash command the practitioner typed. Sub-step files contain the per-command prose the LLM follows at runtime; only `run` is fully thickened at this story's landing — `status`, `resume`, and `init` are literal stubs whose full implementations land in later epics.

| Slash command                      | Sub-step file        | Status (epic 2.5 landing)                           | Full implementation owner       |
| ---------------------------------- | -------------------- | --------------------------------------------------- | ------------------------------- |
| `/bmad-automation run <story-id>`  | `steps/run.md`       | Thickened — six-step entry sequence per AC-2        | This story (Story 2.5)          |
| `/bmad-automation status [<id>]`   | `steps/status.md`    | Literal stub — emits not-yet-implemented diagnostic | Stories 8.4 + 8.5               |
| `/bmad-automation resume [<id>]`   | `steps/resume.md`    | Literal stub — emits not-yet-implemented diagnostic | Story 8.3 (mid-loop = Story 8.1) |
| `/bmad-automation init`            | `steps/init.md`      | Literal stub — emits not-yet-implemented diagnostic | Stories 7.1-7.9                 |

When dispatching, read the matching sub-step file in full BEFORE executing any of its instructions. The stub files explicitly forbid functional logic — do not infer behavior from the heading alone.

## Cross-references

The canonical Python composition for the `run` subcommand's six-step entry sequence is `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/orchestrator_run_entry.py`'s `run_story_loop_entry` function. The substrate helper structurally encodes the locate → validate → branch → init run-state → commit transition → dispatch ordering; `steps/run.md` is the prose protocol the LLM follows when invoking the helper at runtime.

The specialist-dispatch seam at `steps/run.md`'s step (f) is owned by Story 2.6's substrate library `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/specialist_dispatch.py` (registry validation, payload construction, log persistence, envelope validation, event emission, Task-tool dispatch callback factory). The LLM-runtime protocol the dispatch callback executes — Task-tool invocation, wall-clock timeout monitoring, return-envelope parsing — lives at `steps/dispatch.md` per ADR-004's substrate-vs-LLM-runtime split. Read `steps/dispatch.md` in full before executing the dispatch step.

The architectural commitment that the orchestrator is implemented as a Claude Code skill (rather than as a custom CLI, an external service, or an Agent SDK harness) is `bmad-autopilot/docs/architecture.md#ADR-001` (Orchestrator Implementation Primitive). The skill bundle's portable surface — `(orchestrator-prompt-logic.md, run-state.yaml schema, orchestrator-event.yaml, specialist-envelope schema)` per ADR-001 line 71 — has its first concrete `orchestrator-prompt-logic.md` artifact in this skill's `workflow.md` + `steps/run.md` per the View 1 source-repo location at `bmad-autopilot/docs/architecture.md`'s "View 1" section. The portability classification is `bmad-autopilot/docs/architecture.md#ADR-002` (cell 4 / Host-Bridge — the binding rebuilds when porting to a non-Claude-Code host; the structural commitment is cell-1 portable).

The substrate-library classification (this skill is the orchestrator-binding artifact, NOT a sixth substrate component) is `bmad-autopilot/docs/architecture.md#ADR-003` (substrate-component closure at FIVE). The FR62 pluggability gate at `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/pluggability_gate.py` does NOT scan this `skills/bmad-automation/` directory — the gate's no-cross-references rule applies to `agents/*.md` only (specialist subagents).
