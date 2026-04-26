---
expected_marker: cost-near-ceiling
scenario: In-flight cost-telemetry shows a story-run is approaching its cost budget (default 75% of ceiling); signal to the practitioner before exhaustion.
---
# Synthetic story: cost-near-ceiling

The orchestrator's per-specialist cost-telemetry emission (per Epic 6
specialist boundary cadence) reports a cumulative spend at or above
the configured fraction of the story-run's cost ceiling (default
75%). The loop continues — `cost-near-ceiling` is a degradation
signal, not a halt — but the marker surfaces in the bundle so
practitioners can monitor or interrupt before the budget exhausts.

Distinct from `retry-budget-exhausted` (the *retry-count* budget,
not the cost-spend budget): different invariants, different
remediation surfaces.
