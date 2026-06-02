#!/usr/bin/env bash
# stop (FR59): invoke the bundle-assembly substrate (Story 2.11) to render the
# merge-ready PR bundle to the canonical path. Story 2.7 scaffolded the hook
# with a literal placeholder; Story 2.11 thickens it to invoke the substrate
# exclusively. Epic 5 + Epic 6 thicken the assembler IN PLACE — same
# `python3 -m loud_fail_harness.bundle_assembly` invocation at this hook.
# The orchestrator-domain run_id is sourced from run-state.yaml (ADR-005
# Consequence 1). Story 15.3 adds an EPIC-SCOPE dispatch branch (no 4th hook):
# when an epic-run-state.yaml cache is present (the epic loop writes it; a
# per-story-only `run <story-id>` invocation never creates it) the hook
# ADDITIONALLY renders the running/final epic-level PR bundle. All bundle-
# assembly logic lives in the substrate (FR61); the hook only dispatches.
set -euo pipefail
RS="_bmad/automation/run-state.yaml"
PY='import yaml,sys; d=yaml.safe_load(open(sys.argv[1])) or {}; sys.stdout.write("\x1f".join([d.get(sys.argv[2]) or "",d.get(sys.argv[3]) or ""]))'
IFS=$'\x1f' read -r SID RID <<< "$(python3 -c "$PY" "$RS" story_id run_id)"
python3 -m loud_fail_harness.bundle_assembly --story-id "$SID" --run-id "$RID" --run-state-path "$RS" --logs-root _bmad-output/qa-evidence --bundle-root _bmad-output/pr-bundles
ERS="_bmad/automation/epic-run-state.yaml"
[[ -f "$ERS" ]] || exit 0
IFS=$'\x1f' read -r EID ERID <<< "$(python3 -c "$PY" "$ERS" epic_id run_id)"
exec python3 -m loud_fail_harness.bundle_assembly_epic --epic-id "$EID" --run-id "$ERID" --epic-run-state-path "$ERS" --bundle-root _bmad-output/epic-pr-bundles
