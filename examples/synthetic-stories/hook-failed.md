---
expected_marker: hook-failed
scenario: A hook's exit code is non-zero; remediation targets the bash script's environment.
---
# Synthetic story: hook-failed

A SubagentStop / Stop / SessionStart hook returns a non-zero exit
status during the orchestrator loop. Distinct from
`bundle-assembly-failed` (assembler logic) and
`scope-assertion-violation` (Dev diff vs. declared scope): the
remediation surface for `hook-failed` is the bash script itself —
its dependencies, its assumed binaries on PATH, its expected env
vars, or a wall-clock timeout in the script's body.

Sub_classifications distinguish the failure mode (`non-zero-exit`,
`timeout`, `missing-binary`); story 1.8's reconciler-replay gate
will exercise those specifically.
