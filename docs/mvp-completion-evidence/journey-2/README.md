# Journey 2 — First Honest Failure

Per Story 8.7 AC-3 verbatim (`epics.md:3416`): "retry-budget exhaustion
→ escalation bundle → preserved branch + run-state → human triage path".

## Artifacts

| File | Description |
|---|---|
| [`run-output.txt`](run-output.txt) | Per-seam stream culminating in retry-budget-exhaustion |
| [`retry-history.yaml`](retry-history.yaml) | Per-round retry-history entries (Story 5.5 externalized references resolved) |
| [`escalation-bundle.md`](escalation-bundle.md) | Escalation PR bundle (Story 5.8) |
| [`run-state-preserved.yaml`](run-state-preserved.yaml) | Preserved run-state (Story 5.6 non-advance state preservation) |
| [`branch-preserved.txt`](branch-preserved.txt) | `git branch --show-current` output proving per-story branch is preserved |
| [`journey-2-narrative.md`](journey-2-narrative.md) | Narrative + environment notes + execution date + discovered-gaps |

Expected loud-fail markers visible in escalation bundle: `retry-budget-exhausted` (Story 5.6).
