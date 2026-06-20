# Phase 2 Completion Evidence (Story 23.1)

This artifact maps every Phase 2 requirement to its ship `Status`,
observable `Evidence`, and outstanding `Findings` count. The row set is
the closed Phase 2 enumeration defined at
`_bmad-output/planning-artifacts/epics-phase-2.md:999` verbatim — 10
net-new Phase 2 FRs (FR-P2-1 … FR-P2-10) + 7 Phase 2 NFR extensions
(NFR-P3 per-mode, NFR-P5 / NFR-R1 / NFR-R3 / NFR-R8 / NFR-S3 / NFR-I3 at
new scopes) + 12 Phase 2-touched MVP FRs (FR3 / FR4 / FR5 / FR6 / FR7 /
FR8 / FR15 / FR22 / FR23-25 / FR30 / FR45 / FR48). Total: 29 rows.
Authoritative reference: `_bmad-output/planning-artifacts/epics-phase-2.md:989-1002`
(Story 23.1 epic AC verbatim) and `epics-phase-2.md:999-1000` (the
closed row enumeration + the four-value status vocabulary).

Status vocabulary per `epics-phase-2.md:1000` verbatim:
`delivered` | `partial` | `not-shipped` | `deferred-to-phase-3`. This
extends the Phase 1.5 three-value vocabulary with `deferred-to-phase-3`
(a requirement whose surface intentionally carries to Phase 3). At THIS
artifact's landing (2026-06-20, Phase 2 cut after Epics 14–22 close per
`_bmad-output/implementation-artifacts/sprint-status.yaml:209-325`), 27
of 29 rows carry `Status: delivered` and `Findings: 0` — every Phase 2
substrate has shipped and each row's `Evidence` cell points at a
committed story-doc and (where applicable) the Phase 2 reference-run
record under `docs/reference-runs/`. The two non-`delivered` rows at
landing time, with their one-line rationale per AC-5:

- **FR-P2-7: `partial`** — reduced surface shipped. Story 21.1's spike
  verdict was `partially-stable`; Story 21.2 shipped in-session
  background dispatch; the cross-session fire-and-forget capability
  carries to Phase 3. `Findings: 1`,
  `(carries-to-phase-3: cross-session fire-and-forget)`. Story 23.3's
  retro records the explicit Phase-2-close disposition.
- **NFR-P3: `partial` pending Story 23.2 LAD+mobile budget witness** —
  the per-mode budget structure is canonical and landed (Story 22.1)
  but the `LAD+mobile ≤ 13 min` budget is un-witnessed at Phase-2 close
  per `sprint-status.yaml:31` + `:328-332`. `Findings: 1`,
  `(blocked-on: Story 23.2)`. The empirical witness is owned by Story
  23.2's reference-run consolidation + H8 live-mobile re-capture.

No row carries `not-shipped` or `deferred-to-phase-3` at THIS landing —
both values are wired into the validator vocabulary for Story 23.2 /
23.3 to apply if the Phase-2-close determination so warrants.

Phase 1 sibling: `bmad-autopilot/docs/mvp-completion-evidence.md`
(Story 8.7 — 102-row full-MVP-surface artifact). Phase 1.5 sibling:
`bmad-autopilot/docs/phase-1.5-completion-evidence.md` (Story 11.1 —
11-row additive-feature artifact). Phase 2 is a sibling artifact of the
same shape, NOT an extension of either; the three share row-schema
spirit (five columns) and differ only in the additive surface they close.

Regeneration command (read-only validation):
```
cd bmad-autopilot/tools/loud-fail-harness
uv run phase-2-completion-evidence
```

## Methodology

### Phase 2 row enumeration source

The 29 rows of the coverage matrix below are the closed enumeration
defined at `_bmad-output/planning-artifacts/epics-phase-2.md:999`
verbatim ("one row per Phase 2 FR (FR-P2-1 through FR-P2-10), per
Phase 2 NFR extension (NFR-P3 per-mode reframing from Story 22.1,
NFR-P5 per-epic / per-sprint / per-worktree partitions, NFR-R1 / R3 / R8
at new scopes, NFR-S3 auto-merge surface, NFR-I3 a11y / visual-regression
/ background dependencies), and per Phase 2-touched MVP FR (FR3 / FR4 /
FR5 / FR6 / FR7 / FR8 / FR15 / FR22 / FR23-25 / FR30 / FR45 / FR48)").
Row ordering is deterministic: Phase 2 net-new FRs in numeric order,
then Phase 2 NFR extensions in the planning-text order, then Phase
2-touched MVP FRs in the planning-text order.

`FR23-25` is ONE row, not three — the planning-text closed enumeration
lists `FR23-25` as a single slash-delimited token (the QA-Behavioral-Plan
FR cluster: FR23 persistence + FR24 retry policy + FR25 documented
compromise), all three touched as a unit by FR-P2-9's per-run plan
re-derivation. Likewise `FR30` is ONE row (the Phase 2 token does not
sub-classify it, unlike Phase 1.5's `FR30-LAD-skipped` /
`FR30-mobile-blocked` split).

Phase 1 / Phase 1.5 MVP FRs that did NOT extend in Phase 2 are OUT OF
SCOPE. The validator (`phase_2_completion_evidence.py`) rejects any row
whose ID is not in `PHASE_2_ROW_IDS` with the diagnostic
`unknown-requirement-id`, preventing Phase-2 / prior-phase row drift.

### Row schema

Each row carries five required columns in left-to-right order:

1. `Requirement ID` — exact match for one ID in the 29-element closed
   enumeration.
2. `Requirement Summary` — one-line summary (≤ 200 chars; pure prose;
   NOT verbatim from `prd.md` — clarifying summary suitable for inline
   scanning).
3. `Status` — exactly one of `delivered` | `partial` | `not-shipped` |
   `deferred-to-phase-3`.
4. `Evidence` — non-empty pointer (story-doc path, commit SHA + short
   title, test path or pytest test ID, or reference-run record path
   under `docs/reference-runs/`). Multiple pointers MAY be
   comma-separated within the single cell. The validator does NOT
   resolve `Evidence` cells against the filesystem — deliberate
   divergence from Phase 1's `evidence-link-not-resolved` rule (Phase 2
   evidence includes git-commit SHA strings and pytest test IDs that
   are not always filesystem paths), inherited from the Phase 1.5
   module.
5. `Findings` — non-negative base-10 integer count of outstanding
   findings. `0` is REQUIRED for `delivered` rows; values `> 0` are
   admissible for `partial` / `deferred-to-phase-3` rows. A `delivered`
   row carrying `Findings > 0` triggers the validator's
   `delivered-row-with-open-findings` rule — the integrity invariant
   "a row is not delivered while findings remain."

### `partial` + `deferred-to-phase-3` status discipline (AC-5 three-class triage)

At Story 23.1's landing, two rows carry `Status: partial` (FR-P2-7,
NFR-P3); zero carry `deferred-to-phase-3`. When a row is non-`delivered`,
the dev triages the gap into exactly one of three classes:

- **Evidence-forward-deferred** — implementation `done` per
  `sprint-status.yaml` but the definitive reference-run / H8 evidence
  capture is owned by Story 23.2. Remediation: row flips to `delivered`
  when Story 23.2 populates the evidence pointer. THIS is the class for
  `NFR-P3` at landing.
- **Reduced-surface-shipped** — a Phase 2 requirement shipped a
  deliberately reduced surface with the remainder carrying to a later
  phase (FR-P2-7's in-session background dispatch shipped; cross-session
  fire-and-forget carries to Phase 3 per the `partially-stable` spike
  verdict). Remediation: status stays `partial` until Story 23.3's retro
  records the explicit Phase-2-close disposition; MAY become
  `deferred-to-phase-3` if the close determination so rules.
- **Documentation-partial** — implementation + tests shipped but the
  row's `Evidence` cell cannot yet point at a stable artifact (e.g., a
  Story 23.3 retro doc). Remediation: row stays `partial` until the
  cited doc lands.

The validator does NOT structurally distinguish the three classes (the
dev triages manually in this preamble); it DOES structurally enforce the
`delivered-row-with-open-findings` invariant for `delivered` rows AND
exempts `partial` / `not-shipped` / `deferred-to-phase-3` rows from it.

## Coverage matrix

| Requirement ID | Requirement Summary | Status | Evidence | Findings |
| --- | --- | --- | --- | --- |
<!-- phase-2-coverage-rows:begin -->
| FR-P2-1 | Epic-level orchestration: sequential N-story dispatch with per-epic retry budget and a running epic-level PR bundle | delivered | _bmad-output/implementation-artifacts/15-1-bmad-automation-run-epic-entry-point-epic-lifecycle-module.md, bmad-autopilot/docs/reference-runs/15-5-epic-web/ | 0 |
| FR-P2-2 | Sprint-level orchestration: sprint-order processing with progress visibility and escalation-rate signaling; retrospective stays human-owned | delivered | _bmad-output/implementation-artifacts/16-1-bmad-automation-run-sprint-entry-point-sprint-lifecycle-module.md, bmad-autopilot/docs/reference-runs/16-4-sprint-web/ | 0 |
| FR-P2-3 | Auto-merge: configurable flag default-off, gated on reference-project adoption conditions; the first remote-push actuator surface | delivered | _bmad-output/implementation-artifacts/17-2-gate-condition-evaluator-auto-merge-gate-not-met-marker.md, _bmad-output/implementation-artifacts/22-7-auto-merge-draft-to-ready-handling-epic-17-retro-action-1.md, bmad-autopilot/docs/reference-runs/22-7-auto-merge-web/ | 0 |
| FR-P2-4 | Parallel stories: per-story worktree isolation, story-file locking protocol, and cross-story state-pollution detection | delivered | _bmad-output/implementation-artifacts/18-1-parallel-dispatch-substrate-parallel-stories-config-flag.md, bmad-autopilot/docs/reference-runs/18-4-parallel-web/ | 0 |
| FR-P2-5 | Full 7-heuristic exploratory QA sweep (cross-AC drift); orthogonal to FR22c within-AC flow-branch coverage | delivered | _bmad-output/implementation-artifacts/19-2-full-7-heuristic-sweep-implementation-heuristic-skipped-sub-classification.md, bmad-autopilot/docs/reference-runs/19-6-web/ | 0 |
| FR-P2-6 | Accessibility audit: opt-in default-defer baseline-delta mode wired into the QA runbook | delivered | _bmad-output/implementation-artifacts/19-4-a11y-audit-runtime-opt-in-integration.md, bmad-autopilot/docs/reference-runs/19-6-web/ | 0 |
| FR-P2-7 | Background / fire-and-forget orchestrator execution; in-session dispatch shipped (carries-to-phase-3: cross-session fire-and-forget) per the partially-stable spike verdict | partial | _bmad-output/implementation-artifacts/21-2-background-execution-implementation-or-named-fallback-per-story-21-1.md, bmad-autopilot/docs/reference-runs/21-2-background-web/ | 1 |
| FR-P2-8 | Flakiness log: longitudinal per-AC pass/fail history with a configurable threshold marker | delivered | _bmad-output/implementation-artifacts/20-2-flakiness-log-schema-persistence-fr-p2-8.md, bmad-autopilot/docs/reference-runs/20-4-web/ | 0 |
| FR-P2-9 | Per-run plan re-derivation cross-check; closes FR25's MVP plan-persistence compromise | delivered | _bmad-output/implementation-artifacts/20-1-per-run-plan-re-derivation-cross-check-fr-p2-9.md, bmad-autopilot/docs/reference-runs/20-4-web/ | 0 |
| FR-P2-10 | Visual regression snapshotting: opt-in baseline plus delta via the QA runbook | delivered | _bmad-output/implementation-artifacts/19-5-visual-regression-snapshotting-substrate-opt-in-integration.md, bmad-autopilot/docs/reference-runs/19-6-web/ | 0 |
| NFR-P3 | First-loop onboarding time budgeted per mode (web/api 5m, mobile 10m, LAD 8m, LAD+mobile 13m); LAD+mobile budget un-witnessed at close (blocked-on: Story 23.2) | partial | _bmad-output/implementation-artifacts/22-1-h3-nfr-p3-per-mode-budget-articulation.md | 1 |
| NFR-P5 | Cost-observability partitions extend to per-epic, per-sprint, and per-worktree scopes | delivered | _bmad-output/implementation-artifacts/15-5-epic-15-reference-run-fixture-per-epic-cost-partition-witness.md, bmad-autopilot/docs/reference-runs/16-4-sprint-web/ | 0 |
| NFR-R1 | Run-state atomic-write contract extends to epic-run-state and per-worktree run-state | delivered | _bmad-output/implementation-artifacts/14-4-epic-scope-run-state-schema-per-worktree-run-state-addressing.md, _bmad-output/implementation-artifacts/16-5-sprint-resume-budget-reconstruction-production-epic-loop-runner-adapter.md | 0 |
| NFR-R3 | Git operation safety (no main mutation, no force-push, no destructive cleanup) holds under parallel-worktree mode | delivered | _bmad-output/implementation-artifacts/14-2-per-story-worktree-lifecycle-module-substrate-library.md, _bmad-output/implementation-artifacts/18-1-parallel-dispatch-substrate-parallel-stories-config-flag.md | 0 |
| NFR-R8 | Cross-state consistency (story-doc canonical) extends to epic, sprint, and per-worktree run-state | delivered | _bmad-output/implementation-artifacts/14-5-parallel-story-state-pollution-marker-pre-provision-cross-state-consistency-extension.md, _bmad-output/implementation-artifacts/18-2-cross-story-state-pollution-detection-marker-emission.md | 0 |
| NFR-S3 | Git operation scope extends to remote push plus PR merge under opt-in auto-merge with gate diagnostics | delivered | _bmad-output/implementation-artifacts/17-3-auto-merge-execution-via-stop-hook-no-4th-hook.md, bmad-autopilot/docs/reference-runs/22-7-auto-merge-web/ | 0 |
| NFR-I3 | New Phase 2 dependencies (a11y audit, visual-regression, background primitive) declared with explicit failure profiles in dependencies.yaml | delivered | _bmad-output/implementation-artifacts/19-3-a11y-audit-tool-selection-adr-dependencies-yaml-activation.md, _bmad-output/implementation-artifacts/21-1-claude-code-background-agent-primitive-stability-spike-bounded-named-fallback.md | 0 |
| FR3 | Specialist dispatch sequence extends from per-story to per-epic and per-sprint scope | delivered | _bmad-output/implementation-artifacts/15-1-bmad-automation-run-epic-entry-point-epic-lifecycle-module.md, _bmad-output/implementation-artifacts/16-1-bmad-automation-run-sprint-entry-point-sprint-lifecycle-module.md | 0 |
| FR4 | Per-story branch lifecycle extends to a per-story-worktree lifecycle under parallel mode | delivered | _bmad-output/implementation-artifacts/14-2-per-story-worktree-lifecycle-module-substrate-library.md, bmad-autopilot/docs/reference-runs/18-4-parallel-web/ | 0 |
| FR5 | Lifecycle state transitions extend to per-epic and per-sprint scope | delivered | _bmad-output/implementation-artifacts/15-1-bmad-automation-run-epic-entry-point-epic-lifecycle-module.md, _bmad-output/implementation-artifacts/16-1-bmad-automation-run-sprint-entry-point-sprint-lifecycle-module.md | 0 |
| FR6 | Flow-policy halt/route extends to per-epic and per-sprint scope | delivered | _bmad-output/implementation-artifacts/15-2-per-epic-retry-budget-epic-budget-exhausted-marker.md, _bmad-output/implementation-artifacts/16-2-per-sprint-retry-budget-escalation-rate-threshold-marker.md | 0 |
| FR7 | Orchestrator-owned env lifecycle supports concurrent provisioning under parallel stories | delivered | _bmad-output/implementation-artifacts/18-3-concurrent-env-provisioning-discipline-fr7-extension.md, bmad-autopilot/docs/reference-runs/18-4-parallel-web/ | 0 |
| FR8 | Whole-story retry budget gains companion per-epic and per-sprint budgets | delivered | _bmad-output/implementation-artifacts/15-2-per-epic-retry-budget-epic-budget-exhausted-marker.md, _bmad-output/implementation-artifacts/16-2-per-sprint-retry-budget-escalation-rate-threshold-marker.md | 0 |
| FR15 | Escalation bundle gains per-epic and per-sprint variants | delivered | _bmad-output/implementation-artifacts/15-3-running-epic-level-pr-bundle-assembly.md, _bmad-output/implementation-artifacts/16-3-sprint-status-artifact-generated-at-sprint-close-not-a-retrospective.md | 0 |
| FR22 | Exploratory heuristics extend from 3 to 7; FR22c within-AC flow-branch coverage stays orthogonal and unchanged | delivered | _bmad-output/implementation-artifacts/19-1-full-7-heuristic-sweep-heuristic-selection-adr-qa-runbook-schema-extension.md, bmad-autopilot/docs/reference-runs/19-6-web/ | 0 |
| FR23-25 | QA Behavioral Plan persistence plus retry policy plus documented compromise cluster; the FR25 compromise is closed by FR-P2-9 per-run re-derivation | delivered | _bmad-output/implementation-artifacts/20-1-per-run-plan-re-derivation-cross-check-fr-p2-9.md, bmad-autopilot/docs/reference-runs/20-4-web/ | 0 |
| FR30 | Marker taxonomy extends with Phase 2 marker classes via PATCH/MINOR bumps only (no MAJOR); closed-set held at 44 at Epic 22 close | delivered | _bmad-output/implementation-artifacts/sprint-status.yaml:31, _bmad-output/implementation-artifacts/22-5-h1-h2-h4-h5-h9-trigger-time-landings-audit.md | 0 |
| FR45 | Run-state schema gains epic-run-state.yaml and sprint-run-state.yaml variants plus per-worktree addressing | delivered | _bmad-output/implementation-artifacts/14-4-epic-scope-run-state-schema-per-worktree-run-state-addressing.md, _bmad-output/implementation-artifacts/16-1-bmad-automation-run-sprint-entry-point-sprint-lifecycle-module.md | 0 |
| FR48 | /bmad-automation status extends to epic-scope and sprint-scope queries | delivered | _bmad-output/implementation-artifacts/15-4-bmad-automation-status-epic-query.md, _bmad-output/implementation-artifacts/16-4-bmad-automation-status-sprint-query-sprint-level-reference-run-fixture.md | 0 |
<!-- phase-2-coverage-rows:end -->

## Cross-references

- `bmad-autopilot/docs/phase-1.5-completion-evidence.md` — Phase 1.5
  sibling (Story 11.1). Same five-column row schema; three-value
  `Status` discriminator (`delivered` | `partial` | `not-shipped`).
  Phase 2 extends that vocabulary with `deferred-to-phase-3`; otherwise
  the validator shape is identical (anchor-bounded parse, nine lint
  rules, Pattern 5 exit-code dispatch).
- `bmad-autopilot/docs/mvp-completion-evidence.md` — Phase 1 sibling
  (Story 8.7). 102-row full-MVP-surface artifact; the full-surface
  predecessor. Different discriminator column (`Exercising Journey`)
  and an `evidence-link-not-resolved` rule that Phase 1.5 + Phase 2
  deliberately do NOT inherit.
- `bmad-autopilot/docs/reference-projects.md` — Story 23.2
  reference-project index. Source-of-truth for the Phase 2 reference-run
  discovery; the `Evidence` cell for reference-run-backed rows cites the
  per-run directories below directly until Story 23.2 consolidates the
  index.
- Phase 2 reference-run records under `bmad-autopilot/docs/reference-runs/`:
  `15-5-epic-web/`, `16-4-sprint-web/`, `18-4-parallel-web/`,
  `19-6-web/`, `19-6-mobile/`, `20-4-web/`, `21-2-background-web/`,
  `22-7-auto-merge-web/`. Each carries the narrative + PR bundle +
  envelope captures for the FR/NFR rows it exercises.
- `_bmad-output/planning-artifacts/epics-phase-2.md` — Phase 2 epic
  breakdown. Authoritative source for the closed 29-row enumeration at
  `epics-phase-2.md:999` and the four-value status vocabulary at `:1000`.
- Story 23.2 (`epics-phase-2.md:1004-1017`) — the forward consumer that
  flips the two `partial` rows (FR-P2-7, NFR-P3) toward `delivered` (or
  records their Phase-2-close disposition) once the reference-run
  consolidation + H8 live-mobile re-capture land.

## Regeneration

This artifact is regenerated under three triggers:

- **Phase 2 close.** Story 23.2 populates the reference-run + H8
  evidence; the dev verifies the closed enumeration at
  `epics-phase-2.md:999` still matches the row set and resolves the two
  `partial` rows per the Story 23.3 retro disposition.
- **Each post-Phase-2 correct-course event that adds a Phase 2 FR / NFR.**
  The dev adds the new row at the correct enumeration position AND adds
  the corresponding entry to `PHASE_2_ROW_IDS` in
  `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/phase_2_completion_evidence.py`.
  The validator's closed-set audit fails loudly until both surfaces are
  updated in sync — by-design.
- **Each `partial` → `delivered` transition** when Story 23.2 lands
  reference-run + H8 evidence for a previously-deferred row. The dev
  updates the `Status` cell AND decrements / zeroes the `Findings` cell;
  the validator's `delivered-row-with-open-findings` rule guards against
  accidental skew.

Regeneration command (read-only validation; the validator is read-only
by construction — it parses the artifact + audits against the closed
enumeration but does NOT auto-edit cell contents):

```
cd bmad-autopilot/tools/loud-fail-harness
uv run phase-2-completion-evidence
```

CI enforces the gate per `.github/workflows/ci.yml` step
`Phase 2 completion evidence validator (story 23.1)`. Exit 0 iff every
cell is populated, every Status is in `STATUS_VALUES`, every Findings
parses as a non-negative integer, no `delivered` row carries open
findings, and the row count matches the closed 29-row enumeration.
