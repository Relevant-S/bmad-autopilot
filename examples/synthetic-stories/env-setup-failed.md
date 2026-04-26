---
expected_marker: env-setup-failed
scenario: Env provisioning (dev server start, port-binding, Playwright launch) failed; QA phase skips with this marker.
---
# Synthetic story: env-setup-failed

The orchestrator's QA env-provisioning lifecycle (dev server start +
port-binding + Playwright MCP launch) fails before QA assertions can
run. The QA specialist returns an envelope whose evidence section
points at the env-setup logs under
`_bmad-output/qa-evidence/{story-id}/{run-id}/`; the marker
distinguishes provisioning failure from smoke-pass failure
(`smoke-first-abort`).

Sub_classifications carry the specific provisioning step
(`port-bind-failed`, `playwright-launch-failed`,
`dev-server-not-ready`) — story 1.8 will assert on those; this story
exercises the parent class only.
