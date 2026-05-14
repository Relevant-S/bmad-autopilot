# Phase 1.5 Completion Evidence (Story 11.1)

This artifact maps every Phase 1.5 requirement (2 net-new Phase 1.5
FRs + 5 Phase 1.5-touched MVP FRs — with `FR30` sub-classified
adjacently per marker class — + 3 Phase 1.5 NFR extensions) to its
ship `Status`, observable `Evidence`, and outstanding `Findings`
count. Total: 11 rows. Authoritative reference:
`_bmad-output/planning-artifacts/epics-phase-1.5.md:340-355` (Story
11.1 epic AC verbatim) and `_bmad-output/planning-artifacts/epics-phase-1.5.md:352-353`
(the closed row enumeration).

Status vocabulary per `epics-phase-1.5.md:353` verbatim:
`delivered` | `partial` | `not-shipped`. At THIS artifact's landing
(2026-05-14, sprint cut after Epic 9 + Epic 10 close), ALL eleven
rows carry `Status: delivered` and `Findings: 0` — every Phase 1.5
substrate has shipped per `_bmad-output/implementation-artifacts/sprint-status.yaml:152-171`,
every row's `Evidence` cell points at a committed story-doc and (for
LAD + mobile rows) the reference-run record captured by Story 10.7 /
Story 9.6. Story 11.2 will not need to flip any `partial → delivered`
transition; if a future correct-course adds a Phase-1.5-touched FR or
NFR, this artifact's regeneration discipline (see below) will pick
it up. Story 11.2 (`epics-phase-1.5.md:357-370`) has landed: the
`FR-P1.5-1` / `FR-P1.5-2` / `FR30-LAD-skipped` / `FR30-mobile-blocked`
/ `NFR-S1` / `NFR-P5` rows' `Evidence` cells were enriched at 11.2
landing time to cite the reference-run records
(`docs/reference-runs/9-6-mobile/` + `docs/reference-runs/10-7-lad-web/`)
alongside the story-doc pointers, completing the empirical-witness-pointer
contract per `epics-phase-1.5.md:368`.

Phase 1 sibling: `bmad-autopilot/docs/mvp-completion-evidence.md`
(Story 8.7 — 102-row full-MVP-surface artifact). The two artifacts
share row-schema spirit; they differ in the discriminator column —
Phase 1's `Exercising Journey` vs. Phase 1.5's `Status` — because
Phase 1.5 is scoped to two additive features inheriting Phase 1's
substrate, not a full-surface walkthrough against four named
journeys.

Regeneration command (read-only validation):
```
cd bmad-autopilot/tools/loud-fail-harness
uv run phase-1-5-completion-evidence
```

## Methodology

### Phase 1.5 row enumeration source

The 11 rows of the coverage matrix below are the closed enumeration
defined at `_bmad-output/planning-artifacts/epics-phase-1.5.md:352-353`
verbatim ("one row per Phase 1.5 FR (FR-P1.5-1, FR-P1.5-2) and per
Phase 1.5 NFR extension (NFR-S1, NFR-P5 Phase 1.5 extension, NFR-I3
Phase 1.5 activations) and per Phase 1.5-touched MVP FR (FR29, FR30
markers, FR51, FR56, FR62)"). `FR30` is sub-classified into two rows
adjacent to one another (`FR30-LAD-skipped` for Story 10.5's marker
class activation, `FR30-mobile-blocked` for Story 9.5's marker class
activation) because the two activations exercise distinct surfaces;
combining them into a single `FR30` row would mask one of the two
markers' Phase 1.5 landing.

Phase 1 MVP FRs that did NOT extend in Phase 1.5 are OUT OF SCOPE.
The validator (`phase_1_5_completion_evidence.py`) rejects any row
whose ID is not in `PHASE_1_5_ROW_IDS` with the diagnostic
`unknown-requirement-id`, preventing Phase-1.5 / Phase-1 row drift.

### Row schema

Each row carries five required columns in left-to-right order:

1. `Requirement ID` — exact match for one ID in the 11-element
   closed enumeration.
2. `Requirement Summary` — one-line summary (≤ 200 chars; pure
   prose; NOT verbatim from `prd.md` — clarifying summary suitable
   for inline scanning).
3. `Status` — exactly one of `delivered` | `partial` | `not-shipped`.
4. `Evidence` — non-empty pointer (story-doc path, commit SHA + short
   title, test path or pytest test ID, reference-run record path, or
   Phase 1 mvp-completion-evidence sub-path). Multiple pointers MAY be
   comma-separated within the single cell. The validator does NOT
   resolve `Evidence` cells against the filesystem — deliberate
   divergence from Phase 1's `evidence-link-not-resolved` rule
   because Phase 1.5 evidence includes git-commit SHA strings and
   pytest test IDs that are not always filesystem paths.
5. `Findings` — non-negative base-10 integer count of outstanding
   findings. `0` is REQUIRED for `delivered` rows; values `> 0` are
   admissible for `partial` rows. A `delivered` row carrying
   `Findings > 0` triggers the validator's
   `delivered-row-with-open-findings` rule — the integrity invariant
   "a row is not delivered while findings remain."

### `partial` status discipline (AC-5 three-class triage)

At Story 11.1's landing, ZERO rows carry `Status: partial` — all
Phase 1.5 substrate has shipped per `sprint-status.yaml:152-171` AS
OF 2026-05-14, and the reference-run capture for both Phase 1.5
features lives at `docs/reference-runs/9-6-mobile/` (Story 9.6) and
`docs/reference-runs/10-7-lad-web/` (Story 10.7). If a future
correct-course event introduces a `partial` row, the dev triages
into one of three classes:

- **Evidence-forward-deferred** — implementation `done` per
  `sprint-status.yaml` but the reference-run capture is owned by
  Story 11.2 (mobile + LAD reference-project run records). Remediation:
  row flips to `delivered` automatically when Story 11.2 populates
  the reference-run pointer.
- **Implementation-partial** — a Phase 1.5 requirement is partially
  implemented (e.g., a heuristic shipped without one of three
  sub-cases). Remediation: open a correct-course story to complete
  the implementation; row stays `partial` until then.
- **Documentation-partial** — implementation + tests shipped but
  the row's `Evidence` cell cannot yet point at a stable artifact
  (e.g., a published-evidence-doc Story 11.3 will write). Remediation:
  row stays `partial` until the cited doc lands.

The validator does NOT structurally distinguish the three classes
(the dev triages manually in this preamble); it DOES structurally
enforce the `Findings > 0` invariant for `partial` rows AND the
`delivered-row-with-open-findings` invariant for `delivered` rows.

## Coverage matrix

| Requirement ID | Requirement Summary | Status | Evidence | Findings |
| --- | --- | --- | --- | --- |
<!-- phase-1-5-coverage-rows:begin -->
| FR-P1.5-1 | Review-LAD as opt-in 4th parallel reviewer layer (post-MVP traceability) | delivered | _bmad-output/implementation-artifacts/10-2-lad-wrapper-subagent-scaffold-pluggability-compliant.md, bmad-autopilot/docs/reference-runs/10-7-lad-web/ | 0 |
| FR-P1.5-2 | Mobile QA via mobile MCP + mobile-specific exploratory heuristics (post-MVP traceability) | delivered | _bmad-output/implementation-artifacts/9-3-qa-wrapper-mobile-mcp-integration-mobile-appropriate-evidence.md, bmad-autopilot/docs/reference-runs/9-6-mobile/ | 0 |
| FR29 | LAD as 4th parallel reviewer inside bmad-code-review (Phase 1.5 activation of the MVP FR) | delivered | _bmad-output/implementation-artifacts/10-2-lad-wrapper-subagent-scaffold-pluggability-compliant.md, _bmad-output/implementation-artifacts/10-4-failed-layers-enum-extension-bmad-code-review-4-layer-integration.md | 0 |
| FR30-LAD-skipped | LAD-skipped marker class activation (Story 10.5 — API key env-var-only handling, marker emission when key unset) | delivered | _bmad-output/implementation-artifacts/10-5-api-key-env-var-handling-lad-skipped-marker-emission.md, bmad-autopilot/docs/reference-runs/10-7-lad-web/ | 0 |
| FR30-mobile-blocked | mobile-blocked marker class activation (Story 9.5 — init-time and mid-run paths) | delivered | _bmad-output/implementation-artifacts/9-5-mobile-blocked-marker-emission-init-time-and-mid-run-paths.md, bmad-autopilot/docs/reference-runs/9-6-mobile/ | 0 |
| FR51 | Specialist-envelope uniformity extends to Review-LAD (schema extension + contract pair + validator fixture) | delivered | _bmad-output/implementation-artifacts/10-3-lad-envelope-schema-extension-contract-pair-schema-validator-fixture.md | 0 |
| FR56 | failed_layers enum extends from [blind, edge, auditor] to [blind, edge, auditor, lad] (bmad-code-review 4-layer integration) | delivered | _bmad-output/implementation-artifacts/10-4-failed-layers-enum-extension-bmad-code-review-4-layer-integration.md | 0 |
| FR62 | Pluggability no-cross-references CI gate extends to Review-LAD specialist code (Story 10.6) | delivered | _bmad-output/implementation-artifacts/10-6-pluggability-ci-gate-extension-to-review-lad-cost-observability-partition-extension.md | 0 |
| NFR-S1 | LAD API key env-var-only handling (no checked-in keys; LAD-skipped marker emitted when env var absent) | delivered | _bmad-output/implementation-artifacts/10-5-api-key-env-var-handling-lad-skipped-marker-emission.md, bmad-autopilot/docs/reference-runs/10-7-lad-web/ | 0 |
| NFR-P5 | Cost-partition extends to Review-LAD (per-specialist OTel partition includes the lad partition value) | delivered | _bmad-output/implementation-artifacts/10-6-pluggability-ci-gate-extension-to-review-lad-cost-observability-partition-extension.md, bmad-autopilot/docs/reference-runs/10-7-lad-web/ | 0 |
| NFR-I3 | mobile-mcp + lad dependencies.yaml opt-in-skip activation (Stories 9.1 + 10.1 — ADR + dependencies.yaml entries) | delivered | _bmad-output/implementation-artifacts/9-1-mobile-mcp-server-selection-adr-dependencies-yaml-mobile-mcp-activation.md, _bmad-output/implementation-artifacts/10-1-lad-mcp-server-selection-adr-dependencies-yaml-lad-activation.md | 0 |
<!-- phase-1-5-coverage-rows:end -->

## Cross-references

- `bmad-autopilot/docs/mvp-completion-evidence.md` — Phase 1 sibling
  (Story 8.7). 102-row full-MVP-surface artifact. Same row-schema
  spirit; different discriminator column (`Exercising Journey`
  instead of `Status`) because Phase 1 exercised four closed
  journeys end-to-end against a real reference project, whereas
  Phase 1.5 closes evidence on two additive features inheriting
  Phase 1's substrate.
- `bmad-autopilot/docs/reference-projects.md` — reference-project
  index maintained by Story 10.7 + Story 11.2. Source-of-truth for
  the LAD-enabled web reference run + the mobile reference run that
  the FR-P1.5-1 / FR-P1.5-2 / NFR-S1 / NFR-P5 / NFR-I3 rows' `Evidence`
  cells cite.
- `bmad-autopilot/docs/reference-runs/9-6-mobile/` — Phase 1.5 mobile
  substrate evidence (Story 9.6). Carries `narrative.md` + `pr-bundle.md`
  + envelope captures for the mobile project type.
- `bmad-autopilot/docs/reference-runs/10-7-lad-web/` — Phase 1.5 LAD
  substrate evidence (Story 10.7). Carries the LAD-enabled run record
  with 12 LAD-source findings against the Stories 10.4 + 10.5 substrate
  — the empirical witness for the LAD opt-in 4th-reviewer value claim
  per `docs/reference-projects.md`.
- `_bmad-output/planning-artifacts/epics-phase-1.5.md` — Phase 1.5
  epic breakdown. Authoritative source for the closed 11-row
  enumeration at `epics-phase-1.5.md:352-353`.
- `_bmad-output/planning-artifacts/epics-phase-1.5.md:357-370` —
  Story 11.2 (mobile + LAD reference-project run records populated).
  Forward consumer (LANDED 2026-05-14; commit `<sha7>`) that enriched
  the `FR-P1.5-1` / `FR-P1.5-2` / `FR30-LAD-skipped` /
  `FR30-mobile-blocked` / `NFR-S1` / `NFR-P5` rows' `Evidence` cells
  with reference-run-record pointers; will additionally flip any
  `partial → delivered` if a future correct-course introduces a
  `partial` row.

## Regeneration

This artifact is regenerated under three triggers:

- **Each Phase 1.5 epic close.** Stories 9.x / 10.x / 11.x close;
  the dev verifies the closed enumeration at `epics-phase-1.5.md:352-353`
  still matches the row set + populates any `Evidence` pointers that
  were forward-deferred at the prior landing.
- **Each post-Phase-1.5 correct-course event that adds a Phase 1.5
  FR / NFR.** The dev adds the new row at the correct enumeration
  position AND adds the corresponding entry to `PHASE_1_5_ROW_IDS`
  in `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/phase_1_5_completion_evidence.py`.
  The validator's closed-set audit will fail loudly until both
  surfaces are updated in sync — by-design.
- **Each `partial → delivered` transition** when Story 11.2 lands
  reference-run evidence for a previously-deferred row. The dev
  updates the `Status` cell AND decrements / zeroes the `Findings`
  cell; the validator's `delivered-row-with-open-findings` rule
  guards against accidental skew.

Regeneration command (read-only validation; the validator is read-only
by construction — it parses the artifact + audits against the closed
enumeration but does NOT auto-edit cell contents):

```
cd bmad-autopilot/tools/loud-fail-harness
uv run phase-1-5-completion-evidence
```

CI enforces the gate per `.github/workflows/ci.yml` step
`Phase 1.5 completion evidence validator (story 11.1)`. Exit 0 iff
every cell is populated, every Status is in `STATUS_VALUES`, every
Findings parses as a non-negative integer, no `delivered` row carries
open findings, and the row count matches the closed enumeration.
