#!/usr/bin/env bash
# stop (FR59): invoke the bundle-assembly substrate (Story 2.11) to render the
# merge-ready PR bundle to the canonical path. Story 2.7 scaffolded the hook
# with a literal placeholder; Story 2.11 thickens it to invoke the substrate
# exclusively. Epic 5 + Epic 6 thicken the assembler IN PLACE — same
# `python3 -m loud_fail_harness.bundle_assembly` invocation at this hook;
# no flag changes here at Epic 2. The orchestrator-domain run_id is sourced
# from run-state.yaml (ADR-005 Consequence 1) so the run_id correlates with
# Story 2.6's dispatch logs at _bmad-output/qa-evidence/{story-id}/{run-id}/.
set -euo pipefail
RS="_bmad/automation/run-state.yaml"
PY='import yaml,sys; d=yaml.safe_load(open(sys.argv[1])) or {}; sys.stdout.write("\x1f".join([d.get("story_id") or "",d.get("run_id") or ""]))'
_RS_FIELDS="$(python3 -c "$PY" "$RS")"
IFS=$'\x1f' read -r SID RID <<< "$_RS_FIELDS"
exec python3 -m loud_fail_harness.bundle_assembly \
    --story-id "$SID" \
    --run-id "$RID" \
    --run-state-path "$RS" \
    --logs-root _bmad-output/qa-evidence \
    --bundle-root _bmad-output/pr-bundles
