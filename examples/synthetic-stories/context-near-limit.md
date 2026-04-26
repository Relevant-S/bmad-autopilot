---
expected_marker: context-near-limit
scenario: A specialist's working context is approaching the model's context budget; signals to the orchestrator that retry should be fix-only rather than from-scratch.
---
# Synthetic story: context-near-limit

The Dev specialist's envelope reports it is within a configured
threshold of the model's context budget at the time of return. The
marker is a degradation signal, not a terminal failure: the
orchestrator routes the next retry as `retry-mode: fix-only` (rather
than `from-scratch`) so the specialist can respond to action items
without rebuilding the whole context.

Not a terminal failure per the marker's diagnostic_pointer — a
degradation signal feeding retry-routing policy.
