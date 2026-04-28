# /bmad-automation resume — STUB (Epic 8 thickening)

Full implementation lands in Story 8.3 (`/bmad-automation resume <story-id>` — explicit resume command per FR47); mid-loop reattachment via the `SessionStart` hook lands in Story 8.1 (full implementation replaces the literal-stub from Story 2.7's hook scaffold).

Until then, when invoked, this command emits the message:

> `/bmad-automation resume` is not yet implemented. Story-loop reattachment arrives in Epic 8 (Stories 8.1 + 8.3). For now, if a previous run is in flight, manually inspect `_bmad/automation/run-state.yaml` (per NFR-O2) and complete the loop directly, OR reset the story-doc Status field to `ready-for-dev` and remove the run-state file before re-running with `/bmad-automation run <story-id>`.

The stub contains zero functional logic — no run-state file read, no story-doc consistency check, no recovery-mode dispatch.
