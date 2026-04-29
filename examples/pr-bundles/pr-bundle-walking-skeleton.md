<!--
Canonical example PR bundle fixture — Story 2.11 (basic merge-ready PR bundle assembly).

Source story: bmad-autopilot/_bmad-output/implementation-artifacts/2-11-basic-merge-ready-pr-bundle-assembly-with-machine-readable-walking-skeleton-header.md
Source envelopes (canonical corpus):
  - examples/envelopes/dev-pass.yaml         (Story 1.2)
  - examples/envelopes/review-pass-acceptance-auditor.yaml (Story 2.9)
  - examples/envelopes/qa-pass-ac1-tier1.yaml             (Story 2.10)
Assembler module: tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py

This fixture is a regression baseline. Subsequent epics (3 / 4 / 5 / 6)
regenerate this fixture in place when bundle rendering thickens —
review the diff before committing the regenerated fixture.
-->
# PR bundle — story sample-auto-001 (run run-2026-04-29-001)

Branch: bmad-automation/story/sample-auto-001
Final state: done
Generated: 2026-04-29T12:00:00+00:00

## ⚠️ Walking Skeleton Mode

This PR bundle is a walking-skeleton — it enumerates the structural shape of the BMAD automation loop while the following thickenings remain unfinished:

- Tier-1 evidence only (Epic 4 thickens to Tier-2 + Tier-3-where-configured).
- Single-layer review (Epic 3 thickens to 3-layer adversarial pass).
- No retry (Epic 5 thickens with whole-story retry budget + bucket-driven action item derivation).
- No loud-fail block (Epic 6 thickens with the dedicated top-of-bundle loud-fail block + per-specialist × per-retry cost breakdown + actionable how-to-enable pointers).

## Per-AC results

### AC-1 — status: `pass`

**Assertions:**
- HTTP POST /healthz returned status code 200

**Evidence:**
- `_bmad-output/qa-evidence/sample-001/run-2026-04-29-001/ac1-http-200.log`

**Semantic verification:** `not_applicable`

## Review findings

- **review-001** — Story doc references epics.md line numbers verbatim _(bucket: `defer`, severity: `LOW`)_

Failed layers: (none)

## Dev

**Proposed commit message:**

```
feat(harness): land envelope schema + validator (substrate component 1)
```

Scope expanded to: (none)


<!-- bmad-automation:marker walking-skeleton-bundle -->
