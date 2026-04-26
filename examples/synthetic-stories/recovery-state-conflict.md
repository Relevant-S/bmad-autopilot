---
expected_marker: recovery-state-conflict
scenario: SessionStart reattachment found run-state and story-doc disagree, and the recovery algorithm cannot reconcile cleanly (NFR-R2 / NFR-R8 / Epic 8).
---
# Synthetic story: recovery-state-conflict

A practitioner reattaches to a story whose run-state cache says
`status: in-progress` but whose story-doc says `Status: review` (or
vice versa) — and the cross-state consistency recovery algorithm
(NFR-R8 + Epic 8 Story 8.2) cannot determine which representation
reflects reality without human input. The reattachment surfaces the
marker plus a triage prompt; no destructive action is taken until
the practitioner specifies which state to accept.

Practitioner remediation: human triage of which state representation
reflects reality, then explicit reconciliation. Loud-fail: the
substrate refuses to guess.
