---
expected_marker: undocumented-section-write
scenario: A specialist attempted to write to a story-doc section not in the documented allowlist.
---
# Synthetic story: undocumented-section-write

A Dev or Review specialist's envelope declares a write to a
story-doc section outside the canonical allowlist (the allowed
sections are `## Dev Agent Record`, `## Senior Developer Review (AI)`,
`## Review Findings`, `## QA Behavioral Plan`, and
`## Review Follow-ups (AI)`). The orchestrator's contract enforcement
intercepts the envelope before the write lands; the marker emission
records the attempted section name so the practitioner can decide
whether to amend the allowlist or route the write to a documented
section.

Practitioner remediation: route the write to a documented section
OR amend the allowlist via the upstream-proposal workflow. Note: the
contract is contract-enforced, NOT filesystem-permission-enforced.
