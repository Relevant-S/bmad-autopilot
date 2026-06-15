---
expected_marker: flakiness-threshold-exceeded
scenario: A QA run appended this run's per-AC record into the Story 20.2 flakiness log, then evaluated the per-AC threshold against the now-updated log; an AC's most-recent `threshold_consecutive_runs` records (default 3) each carried an action-level `retry_count_within_run >= threshold_transient_fail_count` (default 1) — a transient retry on the same AC across that many consecutive runs — so the longitudinal flakiness surfaced `flakiness-threshold-exceeded` (FR-P2-8) as story-level evidence with a `diagnostic_pointer` to the flakiness-log entry.
---
# Synthetic story: flakiness-threshold-exceeded

On this QA run the wrapper appended the run's per-AC pass/fail record into the
gitignored flakiness log at `_bmad-output/qa-flakiness/<story-id>.yaml` (Story
20.2), then evaluated the longitudinal threshold per AC against the now-updated
log (FR-P2-8 / Story 20.3). For one AC, the most-recent
`threshold_consecutive_runs` run records (default `3`) each carried an
action-level `retry_count_within_run >= threshold_transient_fail_count` (default
`1`) — i.e. the same AC needed a Playwright-native transient retry across that
many consecutive runs.

That is **intermittency, not breakage**: the transient-fail predicate is purely
the action-level `retry_count_within_run` (the field Story 20.2 built precisely
as the transient-flakiness signal — a `pass` with a non-zero retry IS a
flakiness signal), so a clean deterministic fail (`retry_count_within_run: 0`)
does NOT qualify a run. With the most-recent three runs all transient-failing,
the AC crossed the threshold and the QA wrapper surfaced
`flakiness-threshold-exceeded` for that AC, carrying a `diagnostic_pointer` to
the flakiness-log entry and the current trailing transient-fail streak.

The marker is **story-level evidence** (sensor-not-advisor): it does NOT flip
the AC's pass/fail verdict and does NOT contribute to the wrapper-level
`status` — the orchestrator's flow policy decides what a fired marker means.
Absence of the `flakiness:` qa-runbook block means "defaults apply", NOT a
marker; the log accumulates on every run and the marker fires only on a
crossing. This is a **QA-runtime evidence marker** (orphan, tolerated by
enumeration-check), emitted by
`qa_flakiness_threshold.surface_flakiness_threshold_exceeded`.
