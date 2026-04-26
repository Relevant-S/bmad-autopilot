---
expected_marker: playwright-mcp-unavailable
scenario: Runtime unavailability of Playwright MCP for a web-project QA dispatch surfaces this marker and skips the dependent phase rather than killing the loop.
---
# Synthetic story: playwright-mcp-unavailable

A QA dispatch against a web-project AC where the orchestrator's
runtime cannot reach the Playwright MCP server (per FR17 + ADR-002's
graceful-degrade dependency profile for `playwright-mcp`). The QA
specialist returns an envelope whose evidence section explains the
phase was skipped due to MCP unreachability; the marker emission
gives the practitioner the actionable signal that their QA run was
non-comprehensive, not that the AC failed.

Per the marker's diagnostic_pointer, this is graceful degradation —
not a loop-killing error. Practitioner remediation: restore
Playwright MCP availability, then re-run QA.
