---
expected_marker: git-uncommitted-work-detected
scenario: Per-story branch lifecycle (Story 2.3) detects uncommitted user work in the working tree and halts pre-branch-creation per NFR-R3 / NFR-S3 / NFR-O5.
---
# Synthetic story: git-uncommitted-work-detected

A practitioner runs `/bmad-automation run <story-id>` while the
working tree has uncommitted changes — perhaps an in-flight refactor
in another file, a half-staged feature, or stash-worthy scratch work
the practitioner forgot about. Story 2.3's `branch_lifecycle.create_
story_branch` invokes the injected `WorkingTreeProbe` (default:
wraps `git status --porcelain`); the probe returns
`WorkingTreeProbeResult(clean=False, uncommitted_paths=(...))`; the
helper raises `GitUncommittedWorkDetected` BEFORE any `git checkout`
runs. The orchestrator's wrapper emits this marker into its envelope
per Pattern 5, and the practitioner's terminal stream surfaces the
diagnostic with the uncommitted-path count + a remediation pointer
to `docs/git-hygiene.md`.

Practitioner remediation: stash, commit, or abort. The Automator
does NOT auto-stash or auto-commit on the practitioner's behalf
(epics.md line 1242). Loud-fail: the substrate refuses to risk
destroying user work.

Distinct from `dangling-uncommitted-work` (the ADR-005 git probe
diagnostic emitted at recovery-time on commit-state mismatch —
visibility-only, not flow-blocking); this marker is a write-time
halt, fired BEFORE any branch-creation operation runs.
