---
name: bmad-automation
description: 'Orchestrator skill for the BMAD Agent Development Automator. Routes the four slash commands (run, status, resume, init) through the orchestrator workflow. Use when the user types `/bmad-automation run <story-id>`, `/bmad-automation run --epic <epic-id>` (epic-level sequential dispatch), `/bmad-automation run --sprint <sprint-id>` (sprint-level sequential dispatch over epics + unassigned stories; at sprint close writes a structured `_bmad-output/sprints/sprint-status-artifact-<sprint-id>.md` — the objective input for the user-run `/retrospective`, NOT a retrospective itself), `/bmad-automation status [story-id]`, `/bmad-automation resume [story-id]`, or `/bmad-automation init`.'
---

Follow the instructions in ./workflow.md.
