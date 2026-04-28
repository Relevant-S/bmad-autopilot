#!/usr/bin/env bash
# subagent-stop (FR58/FR50/NFR-O6): commit Dev's proposed_commit_message on per-story branch.
set -euo pipefail
RS="_bmad/automation/run-state.yaml"
PY='import yaml,sys; d=yaml.safe_load(open(sys.argv[1])) or {}; e=d.get("last_envelope") or {}; sys.stdout.write("\x1f".join([d.get("dispatched_specialist") or "",d.get("branch_name") or "",d.get("story_id") or "",e.get("proposed_commit_message") or "",str(len(e.get("scope_expanded_to") or []))]))'
IFS=$'\x1f' read -r SPEC BR SID MSG SCOPE <<< "$(python3 -c "$PY" "$RS")"
[[ "$SPEC" != "dev" ]] && exit 0
[[ -z "$MSG" ]] && { echo "subagent-stop: hook-failed: missing proposed_commit_message in last_envelope (see schemas/envelope.schema.yaml lines 75-77; FR50/FR54)" >&2; exit 1; }
[[ "$SCOPE" != "0" ]] && { echo "subagent-stop: scope-assertion-violation: Dev declared scope_expanded_to=$SCOPE entries on attempt 1 of story $SID; Epic 5 Story 5.4 full diff-vs-declaration verification not yet wired (see schemas/envelope.schema.yaml lines 79-81, schemas/marker-taxonomy.yaml lines 234-242, epics.md Story 5.4)" >&2; exit 1; }
case "$BR" in main|master|trunk) echo "subagent-stop: hook-failed: refusing to commit on trunk branch ($BR); see NFR-R3/NFR-S3" >&2; exit 1;; esac
HEAD_BR="$(git rev-parse --abbrev-ref HEAD)"
[[ "$HEAD_BR" != "$BR" ]] && { echo "subagent-stop: hook-failed: branch mismatch HEAD=$HEAD_BR run-state.branch_name=$BR" >&2; exit 1; }
git commit --allow-empty -m "$MSG [bmad-automation story/$SID]"
