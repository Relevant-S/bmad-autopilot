<!--
Pre-Epic-6 PR-bundle snapshot — Story 6.1 permanence-rule witness per
Story 1.4 + Story 6.1 AC-4. This file is a frozen snapshot of the
``pr-bundle-walking-skeleton.md`` fixture taken IMMEDIATELY BEFORE
Story 6.1's loud-fail-block landing flipped the
``walking-skeleton-bundle`` marker emission rule. The snapshot's
content is UNCHANGED post-6.1 — the
``<!-- bmad-automation:marker walking-skeleton-bundle -->`` comment
is preserved as a provenance signal of the pre-Epic-6 era.

NO TEST, NO REGENERATION, NO MIGRATION SCRIPT TOUCHES THIS FILE. The
permanence rule per Story 1.4 + Story 6.1 AC-4 is enforced by
*absence of edit*, not by an active guard. The post-6.1-regenerated
fixtures live alongside this snapshot at
``pr-bundle-walking-skeleton.md`` and ``pr-bundle-plan-drift.md``.

Source story: bmad-autopilot/_bmad-output/implementation-artifacts/6-1-loud-fail-block-pr-bundle-structure-computed-flag-marker-emission-inversion.md
Snapshot taken from: pr-bundle-walking-skeleton.md (post-Story-5.9 era;
ONE flag False — ``is_loud_fail_block_present()``)
-->
# PR bundle — story sample-auto-001 (run run-2026-04-29-001)

Branch: bmad-automation/story/sample-auto-001
Final state: done
Generated: 2026-04-29T12:00:00+00:00

## ⚠️ Walking Skeleton Mode

This PR bundle is a walking-skeleton — it enumerates the structural shape of the BMAD automation loop while the following thickenings remain unfinished:

- No loud-fail block (Epic 6 thickens with the dedicated top-of-bundle loud-fail block + per-specialist × per-retry cost breakdown + actionable how-to-enable pointers).

## Per-AC results

> **Plan-persistence compromise note (FR25):**
>
> This plan is persisted across runs for resumability.
> Persistence is a known compromise: full QA independence would re-derive the plan every run.
> See `docs/extension-audit.md` and FR-P2-9 (Story 20.1, LANDED — accompanies this note with per-run plan re-derivation cross-check).

### AC-1 — status: `pass`

**Assertions:**
- HTTP POST /healthz returned status code 200

**Evidence:**
- `_bmad-output/qa-evidence/sample-001/run-2026-04-29-001/ac1-http-200.log`

**Semantic verification:** `not_applicable`

## Review findings

### bucket: defer

**MED:**
- [blind] `review-001` — Diff-only adversarial pass surfaced no contract violations (`bmad-autopilot/agents/review-bmad-wrapper.md:1`)

**LOW:**
- [edge] `review-002` — Boundary condition on partial layer failure shape covered by fixtures (`bmad-autopilot/agents/review-bmad-wrapper.md:55`)
- [auditor] `review-003` — Story doc references epics.md line numbers verbatim (`bmad-autopilot/_bmad-output/implementation-artifacts/3-1-three-layer-parallel-pass-wiring.md:1`)
- [merged] `review-004` — Wrapper prose explicitly names all three layer identifiers (`bmad-autopilot/agents/review-bmad-wrapper.md:25`)

Failed layers: (none)

## Dev

**Proposed commit message:**

```
feat(harness): land envelope schema + validator (substrate component 1)
```

Scope expanded to: (none)


<!-- bmad-automation:marker walking-skeleton-bundle -->
