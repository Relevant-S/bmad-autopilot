---
expected_marker: reconciler-mismatch-runtime
scenario: Runtime reconciler detected a skip-event without a matching marker emission (FR33 runtime variant via Epic 6's runtime gate).
---
# Synthetic story: reconciler-mismatch-runtime

A reference-project run produced an orchestrator-event log entry
declaring a skip (e.g., heuristic-skipped, env-setup-failed) that
the runtime marker emission missed — the substrate component 3
reconciler running in Epic 6's runtime gate detects the asymmetry
and emits this marker. Distinct from CI fixture-driven gate
failures (which surface as the harness exit codes 1 / 2 in story
1.8): runtime mismatch indicates a real-flow gap in marker emission,
remediated against the specialist or hook that missed the event,
not the synthetic fixture corpus.
