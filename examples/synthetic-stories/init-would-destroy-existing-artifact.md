---
expected_marker: init-would-destroy-existing-artifact
scenario: bmad-automation init would overwrite user-owned content; halts with this marker rather than proceeding (FR41 / FR42).
---
# Synthetic story: init-would-destroy-existing-artifact

The practitioner runs `/bmad-automation init` against an existing
project where init's scaffolding step would overwrite a file the
user authored (an existing `qa-runbook.yaml`, a hand-edited
specialist subagent definition, a config-templates symlink). The
init flow halts with this marker, lists what would be overwritten,
and does not modify any file until the practitioner chooses
explicitly to back up, merge, or accept overwrite per FR41 +
FR42's non-destructive guarantee.

Distinct from `env-setup-failed` (env present but broken) and
`story-doc-version-out-of-window` (artifact present but wrong
version) — this marker fires at install time, not lifecycle time.
