---
expected_marker: specialist-timeout
scenario: A Task-tool-dispatched specialist exceeded the orchestrator's per-specialist timeout budget; envelope is treated as failed.
---
# Synthetic story: specialist-timeout

The orchestrator dispatches the Dev specialist via the Task tool with
a per-specialist timeout budget; the Dev specialist either runs out
of wall-clock time (`timeout-exceeded`) or runs out of context budget
(`context-budget-exceeded`) before producing an envelope. The
orchestrator treats the missing-envelope condition as failure and
emits the `specialist-timeout` marker; remediation targets the
specialist's prompt or its evidence size, not the harness.

Sub_classifications distinguish wall-clock from context-budget
timeouts; story 1.8's reconciler-replay gate will exercise those
specifically.
