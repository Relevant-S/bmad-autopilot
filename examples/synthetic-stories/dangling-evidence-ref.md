---
expected_marker: dangling-evidence-ref
scenario: A PR bundle contains an evidence reference path that does not resolve to an on-disk artifact.
---
# Synthetic story: dangling-evidence-ref

The PR bundle assembler emits a reference to a QA evidence artifact
(e.g., `_bmad-output/qa-evidence/{story-id}/{run-id}/screenshot.png`)
that was promised by the QA specialist's envelope but is missing on
disk at bundle-assembly time — perhaps deleted between QA emission
and bundle assembly, perhaps never written due to an evidence-pipe
race. The marker emission alerts reviewers that the bundle's
evidence section has a broken pointer.

Distinct from `orphan-run-state-detected` (run-state for a deleted
*story-doc*) — `dangling-evidence-ref` is about evidence-file
disappearance for a known story.
