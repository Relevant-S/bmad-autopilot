---
expected_marker: orphan-process-cleanup
scenario: Env teardown discovered a process that should have been cleaned up by an earlier teardown; cleaned up implicitly and surfaced in the bundle.
---
# Synthetic story: orphan-process-cleanup

The orchestrator's QA env-teardown logic discovers a process bound
to a port the next env-provisioning attempt expects to be free
(e.g., a zombie dev-server from a crashed prior run, or a Playwright
browser process orphaned by an aborted QA dispatch). The teardown
reaps the orphan implicitly so the next run can succeed; the marker
emission preserves visibility so practitioners can investigate the
root cause of the earlier teardown's incompleteness.

Practitioner remediation: review the env-teardown logic for the
specific provisioning path — orphans are loud-fail signals, not
silent recoveries.
