# Journey 4 — Bail-Back / AC-drift (dual framing)

Per Story 8.7 AC-3 verbatim, this journey carries BOTH framings:
- **Epic framing** (`epics.md:3418`): "AC drift → plan-drift-detected →
  plan re-derivation → semantic verification surface"
- **PRD framing** (`prd.md:293-326`): existing-project compatibility /
  TEA-boundary orientation / N-2 story-doc tolerance

Per AC-3 the epic's narrower AC-drift framing is the canonical row-level
discriminator AND the PRD's broader Bail-Back framing is exercised as a
secondary sub-narrative for FR34 / FR43 / FR65 / NFR-I5 row-coverage.

## Artifacts

| File | Description |
|---|---|
| [`run-output.txt`](run-output.txt) | Per-seam stream including AC-drift detection |
| [`qa-behavioral-plan-drift-detected.yaml`](qa-behavioral-plan-drift-detected.yaml) | QA Behavioral Plan with `plan_status: generated` after AC-hash drift (Story 4.2) |
| [`pr-bundle-with-plan-drift-marker.md`](pr-bundle-with-plan-drift-marker.md) | PR bundle's loud-fail block listing `plan-drift-detected` (Story 4.2) |
| [`existing-project-init-output.txt`](existing-project-init-output.txt) | Init's first-run TEA-boundary orientation message (Story 7.8) AND non-destructive guard verdict on existing-project install (Story 7.6) |
| [`story-doc-version-tolerance.txt`](story-doc-version-tolerance.txt) | N-2 version-tolerance probe output on older story-doc (Story 7.7) |
| [`journey-4-narrative.md`](journey-4-narrative.md) | Narrative + environment notes + execution date + dual-framing note + discovered-gaps |
