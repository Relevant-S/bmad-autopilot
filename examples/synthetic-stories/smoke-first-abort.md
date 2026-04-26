---
expected_marker: smoke-first-abort
scenario: The QA Behavioral Plan's smoke pass failed before any AC-detail tests ran; loop aborts without spending further QA effort on a known-broken surface.
---
# Synthetic story: smoke-first-abort

The QA Behavioral Plan's smoke pass (the always-first ordering
contract per the QA Behavioral Plan section) fails: a top-level
landing page returns 500, a CLI command exits non-zero on `--help`,
or an API health-check returns an error response. The orchestrator
aborts the QA dispatch without running the AC-detail tests; the
bundle surfaces the marker so reviewers see why no AC-detail
evidence is present (it isn't truncation; it's a deliberate
short-circuit).

Distinct from `env-setup-failed` (env up but smoke fails — this
marker — vs. env never came up — that marker). Practitioner
remediation: fix the smoke-failing surface, then re-run QA.
