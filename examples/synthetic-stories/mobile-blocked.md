---
expected_marker: mobile-blocked
scenario: Mobile QA is a Phase 1.5 capability; requesting QA on a mobile project at MVP surfaces this marker and halts the QA phase.
---
# Synthetic story: mobile-blocked

The orchestrator dispatches QA against a story whose project type is
`mobile`. Per SDN-001's `mobile-mcp` dependency profile and the MVP
runtime compatibility matrix, mobile is a Phase 1.5 surface and is not
runnable at MVP. QA returns immediately with the `mobile-blocked`
marker; the loop preserves run-state for resumption once Phase 1.5
lands.

Practitioner remediation: wait for Phase 1.5 OR mark the AC as
web/api/manual.
