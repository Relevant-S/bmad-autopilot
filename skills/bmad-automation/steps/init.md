# /bmad-automation init — STUB (Epic 7 thickening)

[Story 7.2 landed (2026-05-07): the install-path-priority module + plugin manifest at `.claude-plugin/plugin.json` are now available at `tools/loud-fail-harness/src/loud_fail_harness/install_path.py`; full `/bmad-automation init` flow still arrives in Stories 7.3-7.9. Story 7.2 does NOT thicken this stub's runtime behavior.]
[Story 7.3 landed (2026-05-08): the init-precondition module at `tools/loud-fail-harness/src/loud_fail_harness/init_preconditions.py` is now available (typed Pydantic API: `run_init_preconditions`, `format_init_diagnostic`); the full `/bmad-automation init` flow still arrives in Stories 7.4-7.9. Story 7.3 does NOT thicken this stub's runtime behavior.]

Full implementation spans Stories 7.1-7.9: plugin-install primitive spike (7.1) and install path (7.2), precondition checks (7.3), sample-story scaffold (7.4), config + qa-runbook stubs (7.5), non-destructive guard (7.6), `bmad` story-doc version-tolerance contract (7.7), TEA-boundary first-run orientation (7.8), and the 5-min first-loop benchmark (7.9).

Until then, when invoked, this command emits the message:

> `/bmad-automation init` is not yet implemented. The first-run installation experience arrives in Epic 7 (Stories 7.1-7.9). For now, the BMAD Agent Development Automator must be wired manually: ensure `_bmad-output/implementation-artifacts/` contains your story files and `sprint-status.yaml`; then run `/bmad-automation run <story-id>` against a `ready-for-dev` story.

The stub contains zero functional logic — no precondition checks, no plugin-install hooks, no sample-scaffold writes, no config-stub generation, no non-destructive guard, no TEA-boundary orientation, no benchmark instrumentation.
