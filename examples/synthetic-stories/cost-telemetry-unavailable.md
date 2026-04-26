---
expected_marker: cost-telemetry-unavailable
scenario: ADR-006 OTel cost-event pipeline failed; cost data unavailable for the run; loop continues with a marker rather than fabricated zeros.
---
# Synthetic story: cost-telemetry-unavailable

The orchestrator's per-specialist cost-telemetry boundary (per
ADR-006) cannot reach its OTel collector or cannot correlate the
prompt-id pairs the spend records require. The bundle's
cost-breakdown section emits the `cost-telemetry-unavailable`
marker rather than zeros (which would be indistinguishable from
"actually free"). Loop continues — graceful-degrade per NFR-P5.

Sub_classifications distinguish whether the OTel pipeline itself is
unreachable (`otel-pipeline-unreachable`) or whether the
correlation key is missing
(`prompt-id-correlation-missing`); story 1.8 will exercise those
specifically.
