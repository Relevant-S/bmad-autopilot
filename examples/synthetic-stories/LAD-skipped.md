---
expected_marker: LAD-skipped
scenario: LAD MCP unavailable or API key absent during code review; loop continues without the 4th adversarial layer.
---
# Synthetic story: LAD-skipped

A code-review specialist dispatch where the optional LAD MCP path
(Phase 1.5 / 4th adversarial layer per `bmad-code-review`) cannot be
exercised because the LAD MCP server is unreachable or no API key is
configured. The Review specialist completes with the three core
adversarial layers; the envelope's review-section emits the
`LAD-skipped` marker rather than blocking the loop.

Practitioner remediation per the marker's diagnostic_pointer:
configure LAD MCP + API key, OR accept the 3-layer review.
