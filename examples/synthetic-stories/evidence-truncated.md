---
expected_marker: evidence-truncated
scenario: QA evidence (screenshot / DOM / HTTP log) exceeded max_evidence_size_mb and was truncated for the bundle.
---
# Synthetic story: evidence-truncated

The QA specialist captures behavioral evidence (a Playwright trace,
a network log, or an MCP screenshot) that exceeds the configured
`max_evidence_size_mb` budget for the PR bundle. The orchestrator
truncates the artifact for inclusion and persists the full artifact
on disk under `_bmad-output/qa-evidence/{story-id}/{run-id}/`; the
bundle's evidence section emits the `evidence-truncated` marker plus
the on-disk path so reviewers can fetch the full artifact when they
need it.

Practitioner remediation: inspect the truncated artifact at its
on-disk path; revisit `max_evidence_size_mb` if truncation is too
aggressive for the project's evidence shapes.
