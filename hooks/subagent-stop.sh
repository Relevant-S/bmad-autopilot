#!/usr/bin/env bash
# subagent-stop (FR58/FR50/NFR-O6/FR12): commit Dev's proposed_commit_message; verify scope assertion (Story 5.4).
set -euo pipefail
RS="$(git rev-parse --show-toplevel)/_bmad/automation/run-state.yaml"
PY='import yaml,sys; d=yaml.safe_load(open(sys.argv[1])) or {}; e=d.get("last_envelope") or {}; sys.stdout.write("\x1f".join([d.get("dispatched_specialist") or "",d.get("branch_name") or "",d.get("story_id") or "",e.get("proposed_commit_message") or ""]))'
IFS=$'\x1f' read -r SPEC BR SID MSG <<< "$(python3 -c "$PY" "$RS")"
[[ "$SPEC" != "dev" ]] && exit 0
[[ -z "$MSG" ]] && { echo "subagent-stop: hook-failed: missing proposed_commit_message in last_envelope (see schemas/envelope.schema.yaml lines 75-77; FR50/FR54)" >&2; exit 1; }
case "$BR" in main|master|trunk) echo "subagent-stop: hook-failed: refusing to commit on trunk branch ($BR); see NFR-R3/NFR-S3" >&2; exit 1;; esac
HEAD_BR="$(git rev-parse --abbrev-ref HEAD)"
[[ "$HEAD_BR" != "$BR" ]] && { echo "subagent-stop: hook-failed: branch mismatch HEAD=$HEAD_BR run-state.branch_name=$BR" >&2; exit 1; }
git commit --allow-empty -m "$MSG [bmad-automation story/$SID]"
HARNESS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../tools/loud-fail-harness" && pwd)"
uv --directory "$HARNESS" run scope-assertion-verify --run-state "$RS" --repo-root "$(git rev-parse --show-toplevel)" || exit 1
