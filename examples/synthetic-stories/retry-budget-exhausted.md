---
expected_marker: retry-budget-exhausted
scenario: The whole-story retry budget (FR8) is exhausted; non-advance with run-state preservation (FR14) and escalation bundle (FR15).
---
# Synthetic story: retry-budget-exhausted

The orchestrator has executed the configured number of whole-story
retries (per FR8 budget) without reaching a terminal advance state.
The loop halts non-destructively: run-state is preserved per FR14;
the FR15 escalation bundle is assembled with retry history,
deferred-work pointers, and the last specialist envelopes; the
marker emission distinguishes "budget exhausted" from "specialist
failed" so the practitioner sees this as a normal-flow halt event,
not a substrate failure.

Not a failure of any single specialist per the marker's
diagnostic_pointer — it is the policy-level halt that triggers
human escalation.
