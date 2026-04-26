---
expected_marker: scope-assertion-violation
scenario: Dev's diff at envelope return time touched files outside the declared affected_files scope (FR10 fix-only constraint violation).
---
# Synthetic story: scope-assertion-violation

A `retry-mode: fix-only` Dev dispatch where the Dev specialist's
returned envelope claims to have addressed action items but the
working-tree diff includes file modifications outside the contracted
`affected_files` scope (per FR10 + FR12 + FR58). The
SubagentStop hook's scope-assertion check fires non-zero; the marker
distinguishes this contract violation from a generic `hook-failed`
because remediation differs: review Dev's diff against declared
scope, possibly tighten the retry's `affected_files` declaration
rather than fix the bash script.

Markers are remediation-shaped, not emission-point-shaped — same
hook can fire either marker depending on what failed.
