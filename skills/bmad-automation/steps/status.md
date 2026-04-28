# /bmad-automation status — STUB (Epic 8 thickening)

Full implementation lands in Stories 8.4 (`/bmad-automation status <story-id>` — single-story inspection per FR48) and 8.5 (`/bmad-automation status` — multi-story listing per FR48b).

Until then, when invoked, this command emits the message:

> `/bmad-automation status` is not yet implemented. Story-loop inspection capability arrives in Epic 8 (Stories 8.4-8.5). For now, inspect run-state directly at `_bmad/automation/run-state.yaml` (per NFR-O2 — plain YAML, human-readable).

The stub contains zero functional logic — no run-state file read, no sprint-status walk, no orphan detection.
