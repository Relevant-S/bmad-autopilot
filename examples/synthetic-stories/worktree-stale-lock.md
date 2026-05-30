---
expected_marker: worktree-stale-lock
scenario: Per-story file-lock at `_bmad/automation/locks/<story-id>.lock` left by a crashed worktree is detected as stale on SessionStart resume (Story 14.3) — either the holding PID is no longer alive (`pid-not-alive` sub-classification) OR the record age exceeded the staleness threshold (`age-exceeded`, default 3600s) OR the lock file is corrupted (`corrupted-lock-file`).
---
# Synthetic story: worktree-stale-lock

A previous Automator session was running under Phase 2 parallel mode
(Epic 18 / FR-P2-4) OR a per-story worktree (Epic 14 / Story 14.2)
when the host process crashed mid-flight. The crash left an orphaned
lock file at `_bmad/automation/locks/<story-id>.lock` carrying the
crashed process's PID + ISO-8601 timestamp + worktree path + hostname.

On the next Claude Code session start, the `SessionStart` hook
(Story 8.1 + Story 14.3) calls
`session_start_reattach.evaluate_reattach`, which composes the per-
story file-lock probe via `story_file_lock.inspect_lock` +
`story_file_lock.is_stale`. The probe identifies the lock as stale
under one of three discriminators:

* `pid-not-alive` — `os.kill(pid, 0)` raises `ProcessLookupError`
  (the holding PID is gone).
* `age-exceeded` — the lock's `started_at` field is more than
  `DEFAULT_STALE_THRESHOLD_SECONDS` (3600s) older than the current
  UTC clock.
* `corrupted-lock-file` — the on-disk YAML body fails to parse OR
  fails `LockRecord` Pydantic validation; the file is on-disk but is
  not a valid lock record.

SessionStart emits the `worktree-stale-lock` marker via
`record_marker_with_context` carrying `{story_id}` as
`pointer_context_fields`. The substrate does NOT auto-clear the
stale lock — operator-decided remediation mirrors Story 14.2's no-
auto-`--force` posture (NFR-R3 + NFR-R7 + Pattern 5 loud-fail
doctrine).

Practitioner remediation: the operator inspects the lock file at
`_bmad/automation/locks/<story-id>.lock`, confirms the holding PID
is no longer alive (e.g., via `ps -p <pid>`), then either invokes
the future `/bmad-automation cleanup <story-id>` command (Story 14.6
forward-pointer) OR deletes the lock file manually with `rm`.

The marker is observability-only at the SessionStart altitude per
Story 8.1's "No state-advancing actions" contract — the orchestrator
skill consumes the marker at the next `/bmad-automation` invocation
and the recovery path proceeds with operator-confirmed remediation.

Per NFR-R2 (PRD line 946) + NFR-R7 (PRD line 951) + NFR-R8 (PRD line
952), the locking primitive enforces single-write coordination
across parallel worktrees (story-doc canonical, run-state cache,
lock file = filesystem-coordination-primitive above both) without
introducing destructive resume semantics.
