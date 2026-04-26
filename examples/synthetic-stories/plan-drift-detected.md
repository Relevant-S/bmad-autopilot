---
expected_marker: plan-drift-detected
scenario: AC hash diverges between Plan creation and current AC text; Plan status resets and re-derivation triggers on next QA dispatch.
---
# Synthetic story: plan-drift-detected

A QA dispatch where the QA Behavioral Plan was generated against a
prior version of the AC text, then the AC was edited (typo fix,
clarification, or scope adjustment) before the Plan was consumed. The
AC-hash check at the start of QA detects the divergence; the Plan
status resets to `pending-rederivation`; the next QA dispatch
regenerates the Plan against the current AC text. The marker surfaces
in the bundle so the practitioner knows the previous Plan was
invalidated by a real AC change (not a false positive).

Practitioner remediation: review the AC change to confirm the new
Plan reflects intent; rare false positives are acceptable per
loud-fail discipline.
