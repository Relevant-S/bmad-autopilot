---
expected_marker: trunk-branch-write-rejected
scenario: Per-story branch lifecycle (Story 2.3) rejects an attempted operation against a branch in the trunk-name allowlist (`main` / `master` / `trunk` by default) before invoking any git command per NFR-S3.
---
# Synthetic story: trunk-branch-write-rejected

A misconfigured `_bmad/automation/config.yaml` overrides the default
`trunk_allowlist` with an empty tuple — OR a story_id is passed that
derives a branch name colliding with the project's trunk (e.g., a
story_id literally named `main`, or a future bypass that replaces
`branch_lifecycle._branch_name_for_story` returning `"trunk"`).
Story 2.3's `branch_lifecycle.create_story_branch` consults the
configured `trunk_allowlist` BEFORE running any `git checkout`-form
command; the would-be branch name matches an allowlist entry; the
helper raises `TrunkBranchWriteRejected` at module level. No git
command is executed against the protected branch — the rejection is
purely structural, not a post-`git`-failure recovery.

Practitioner remediation: review the project's actual trunk branch
name and the orchestrator's `trunk_allowlist` configuration in
`_bmad/automation/config.yaml`. If the project's trunk has a non-
standard name (`develop`, `mainline`, `release`), the user adds it
to the allowlist; if the trunk name is correct and the collision
arose from a malformed story_id, the user fixes the story_id.

Per NFR-S3 (PRD line 971), the Automator NEVER targets `main` /
`master` / `trunk` branches under any operation; the loud-fail at
this layer makes the violation visible at the orchestration boundary
rather than as a downstream `git` accident.
