---
expected_marker: heuristic-skipped
scenario: An exploratory heuristic (empty / error / auth) does not apply to this AC's input or UI surface.
---
# Synthetic story: heuristic-skipped

A QA dispatch where the empty-state heuristic does not apply to the
AC's UI surface (e.g., a CLI command with no list output, or an API
endpoint whose response schema cannot be empty by contract). The QA
Behavioral Plan's `verification_mode` field documents the skipped
heuristic; the marker emission distinguishes "structurally
inapplicable" from "skipped due to time pressure" or "broken".

Not a failure — a structural-bound case per the marker's
diagnostic_pointer.
