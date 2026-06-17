---
expected_marker: background-primitive-unstable
scenario: "A story loop was dispatched as a detached daemon-backed background session (`claude --bg`, gated on `background_execution: true`); on a later `/bmad-automation status` the reconciler cross-checked the `claude agents --json` registry against git ground-truth and found a run the registry reported `completed` whose per-story branch/PR could NOT be confirmed landed — the `#63023`/`#68117` silent-loss signature — so it surfaced `background-primitive-unstable` (FR-P2-7) as story-level runtime evidence."
---
# Synthetic story: background-primitive-unstable

With `background_execution: true` set in `_bmad/automation/config.yaml`,
`/bmad-automation run <story-id>` dispatched the whole story loop as a detached,
daemon-backed Claude Code background session (`claude --bg` — NOT the in-session
`Agent run_in_background` subagent path that loses work silently on session
pause per `anthropics/claude-code#63023`), per the Story 21.1 spike verdict
`partially-stable` → path `partial` (FR-P2-7 / Story 21.2).

On a later `/bmad-automation status`, the reconciler
(`background_dispatch.reconcile_background_runs`) consumed the parsed
`claude agents --json --all` output as injected data and cross-checked each
background run against **git ground-truth** (per-story branch existence + landed
commits, read-only). One run was reported `completed` by the agents registry,
but git showed no landed branch — the cross-session-survival silent-loss
signature (`#63023` / `#68117`). The run was classified **`unconfirmable`** and
the QA/status surface emitted `background-primitive-unstable`, inverting the
primitive's silent failure mode into a loud, greppable marker (loud-fail
doctrine).

The marker is **story-level runtime evidence** (sensor-not-advisor): it
SURFACES the unconfirmable run; it does NOT auto-recover, re-dispatch, or flip
any `ac_results`, the wrapper `status`, or the run lifecycle state. The status
surface stays read-only against run-state contents — the emission is a
discovery-surface emission (the Story 8.5 `orphan-run-state-detected` pattern),
not a run-state write. This is a **runtime-evidence marker** (orphan, tolerated
by enumeration-check — no orchestrator-event / dependency counterpart), emitted
by `background_dispatch.reconcile_background_runs`.
