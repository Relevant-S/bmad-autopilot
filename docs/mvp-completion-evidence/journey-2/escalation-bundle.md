# PR Bundle: sample-story-retry-budget-exhaustion (ESCALATION)

<!-- bundle-mode: escalation; is_retry_present: true -->

## Loud-fail block

- **retry-budget-exhausted** — retry budget (2/2) consumed without convergence.
  How to enable: review the QA Behavioral Plan and the failing AC; either
  fix the implementation OR open a `correct-course` ticket to renegotiate
  the AC. See `deferred-work.md` for the parked-work record.

## Escalation rationale

The story's AC-1 ("response shape matches contract") could not be satisfied
within the retry budget. Two retry rounds attempted; both QA verifications
returned `fail` on the same assertion. Human triage is required to determine
whether the issue is implementation drift, AC ambiguity, or a missing
contract spec.

## Retry history

| Round | Outcome | Diff scope | Findings |
|---|---|---|---|
| 1 | qa-fail | initial implementation | "shape mismatch on /hello" |
| 2 | qa-fail | scope_expanded_to=[src/greeter.py] | "still mismatching after fix-only retry" |

## Preserved artifacts

- Branch: `bmad-autopilot/sample-story-retry-budget-exhaustion` (PRESERVED)
- Run-state: `_bmad/automation/run-state.yaml` (PRESERVED)
- Per-seam logs: `_bmad-output/specialist-logs/.../`
- QA evidence: `_bmad-output/qa-evidence/sample-story-retry-budget-exhaustion/run-001/`

## Pointer to `deferred-work.md`

The unfinished work is recorded at
`_bmad-output/implementation-artifacts/deferred-work.md` per Story 5.7.

## Cost telemetry (NFR-P5)

| Specialist | Round 1 | Round 2 | Total |
|---|---|---|---|
| Dev | $0.42 | $0.39 | $0.81 |
| Review-BMAD | $0.31 | — (skipped on retry) | $0.31 |
| QA | $0.51 | $0.48 | $0.99 |
| **Total** | **$1.24** | **$0.87** | **$2.11** |

Cost ceiling: NFR-P1 $5; this run is $2.11.
