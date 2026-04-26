---
expected_marker: review-layer-failed
scenario: A review layer (Blind Hunter, Edge Case Hunter, Acceptance Auditor, or LAD) failed during the parallel review pass.
---
# Synthetic story: review-layer-failed

The Review specialist dispatches three (optionally four with LAD)
parallel adversarial layers, and one of them fails: the Blind Hunter
sub-prompt exceeds its context budget, the Edge Case Hunter's MCP
tool returns an unrecoverable error, or the LAD MCP server
disconnects mid-session. The Review envelope's `failed_layers` field
(per FR56) names the failed layer; the marker emission tells the
orchestrator the review pass is partial. Per Epic 3 Story 3.3, the
practitioner sees both the marker (for tooling) and a
`decision_needed: HIGH` finding (for the human reviewer).
