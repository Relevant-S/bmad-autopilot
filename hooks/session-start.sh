#!/usr/bin/env bash
# session-start (FR46): SessionStart reattachment + schema-version handling (Story 8.1).
# Heavy lifting in tools/loud-fail-harness/src/loud_fail_harness/session_start_reattach.py
# (substrate library; FR61 keeps this hook thin per architecture.md line 1232).
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
HARNESS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../tools/loud-fail-harness" && pwd)"
exec uv --directory "$HARNESS" run session-start-reattach --project-root "$ROOT"
