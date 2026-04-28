#!/usr/bin/env bash
# stop (FR59): write walking-skeleton merge-ready PR bundle to documented path.
set -euo pipefail
RS="_bmad/automation/run-state.yaml"
PY='import yaml,sys; d=yaml.safe_load(open(sys.argv[1])) or {}; sys.stdout.write("\x1f".join([d.get("story_id") or "",d.get("branch_name") or "",d.get("current_state") or ""]))'
IFS=$'\x1f' read -r SID BR ST <<< "$(python3 -c "$PY" "$RS")"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
BUNDLE="_bmad-output/pr-bundles/${SID}/${RUN_ID}.md"
mkdir -p "$(dirname "$BUNDLE")"
cat > "$BUNDLE" <<EOF
# PR bundle — story ${SID} (run ${RUN_ID})

Branch: ${BR}
Final state: ${ST}
Generated: ${RUN_ID}

## ⚠️ Walking Skeleton Mode

Placeholder bundle from Story 2.7. Story 2.11 thickens this with rich per-AC results, findings, dynamic header, and structural marker emission.

<!-- walking-skeleton-bundle: marker_class -->
EOF
