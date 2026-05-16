# Phase 1.5 Retrospective — Review-LAD + Mobile QA (Two-Epic Phase Close)

- **Date:** 2026-05-14
- **Facilitator:** Bob (Scrum Master)
- **Project Lead:** Auto
- **Scope chosen:** Phase 1.5 phase-level synthesis (Epics 9 + 10 + 11 closing)
- **Format:** Party-mode condensed; structural-table emphasis per Phase 1 retro precedent (`_bmad-output/implementation-artifacts/epic-8-retro-2026-05-10.md`)

## Phase Summary

| Metric | Value |
|---|---|
| Phase span | 2026-05-11 (start, per memory PHASE STATUS) → 2026-05-14 (retro date) |
| Epics closed | 2 fully closed + 1 closing in progress (Epic 9 done 2026-05-12; Epic 10 done 2026-05-14; Epic 11 in-flight at retro — 11.1/11.2 done, 11.3 self-referential, 11.4 backlog) |
| Stories completed | Epic 9: 6/6; Epic 10: 7/7; Epic 11: 2/4 in-flight at retro time (11.3 in review, 11.4 backlog) → 15/17 at retro; 17/17 at phase close |
| Test growth | 2280 → 2464 passing (+184 net across phase); 1 skipped throughout. Epic 9: 2280 → 2381 (+101); Epic 10: 2381 → 2444 (+63, incl. Story 10.1 baseline); Stories 11.1+11.2: 2444 → 2464 (+20) |
| New marker classes | 0 net-new (`mobile-blocked` + `LAD-skipped` + `heuristic-skipped` reused from Phase 1 v1 27-class closed-set) |
| Marker-taxonomy bumps | 1.3 → 1.4 → 1.5 in Epic 9 (sub_classification additions); 0 in Epic 10. All PATCH-level. |
| Dependencies-schema bumps | 1.1 → 1.2 → 1.3 → 1.4 (three PATCH versions: 9.1 mobile-mcp; 9.5 mobile sub_classification; 10.1 lad activation) |
| Envelope-schema shape | byte-stable (Story 10.3 prose-only; `failed_layers` enum 3 → 4 in Story 10.4 is closed-allowlist extension within byte-stable shape) |
| `failed_layers` enum | 3 → 4 (`[blind \| edge \| auditor \| lad]`) |
| ADRs added | 2 (ADR-007 mobile-mcp; ADR-008 lad) |
| 27-class top-level closed-set | ✅ PRESERVED |
| Substrate-component count | FIVE — held (ADR-003 Consequence 1) |
| New substrate-libraries | 4 (Epic 9: `mobile_driver.py` + `project_type_detection.py` + `mobile_heuristic_spec.py`; Epic 10: 0; Story 11.1: `phase_1_5_completion_evidence.py`) |
| New CI gates | 1 (`phase-1.5-completion-evidence` from Story 11.1); Epic 9 + Epic 10 added 0 new gates — extensions only |
| Pluggability-gate state | 3 → 4 specialists (Story 10.6); 0 cross-reference violations end-of-phase |
| Production incidents | 0 |
| Architectural blockers for Phase 2 | 0 |

## Per-Epic Highlights

### Epic 9 — Mobile QA via Mobile MCP

Closed 2026-05-12. Six stories shipped mobile-MCP integration to first-honest-failure parity with web/api: ADR-007 + `dependencies.yaml` activation (9.1); top-level-precedence project-type detection with halt-on-ambiguous (9.2); `mobile_driver.py` 10-method Protocol + QA wrapper integration (9.3); three FR22-parity exploratory heuristics with `MOBILE_HEURISTIC_SPECS` closed-set (9.4); `mobile-blocked` marker emission via pre-prepared substrate (9.5 — zero Python edit required); 9-artifact mobile reference-run with option-(b) stand-in (9.6). Three substrate-libraries added; substrate-component count held at FIVE; PATCH-level taxonomy bumps only. Full per-story breakdown lives in `_bmad-output/implementation-artifacts/epic-9-retro-2026-05-12.md`.

### Epic 10 — Review-LAD as Opt-In 4th Parallel Reviewer

Closed 2026-05-14. Seven stories shipped LAD as the opt-in 4th parallel reviewer: ADR-008 + `lad` activation via `phase: "1.5"` removal (10.1 — validator UNTOUCHED, second SDN-001 witness); pluggability-compliant `review-lad-wrapper.md` (10.2 — `SpecialistId` Literal pre-included `lad`); prose-only envelope schema extension (10.3 — `source: lad` enum already permitted); `failed_layers` enum 3 → 4 + strict-superset graceful-degradation (10.4 — AC-6(v) explicit witness); `OPENROUTER_API_KEY` env-var handling + `LAD-skipped` marker emission (10.5); pluggability-gate 3 → 4 specialists + cost-partition extension (10.6 — H7 retired); reference LAD-enabled run on `bmad-autopilot/` development workspace (10.7 — 12 LAD-only findings on 1279-line diff, the FR-P1.5-2 empirical witness). Zero new substrate-libraries; zero new CI gates; zero marker-taxonomy bumps. Full per-story breakdown lives in `_bmad-output/implementation-artifacts/epic-10-retro-2026-05-14.md`.

### Epic 11 — Phase 1.5 Completion Evidence & Retro (Closing)

In-flight at retro authorship time. Story 11.1 landed the 11-row `phase-1.5-completion-evidence.md` scaffold + validator + CI gate (2026-05-14 — sibling to Phase 1's Story 8.7 mvp-completion-evidence). Story 11.2 enriched reference-run citations + flipped forward-pointers to LANDED (2026-05-14). Story 11.3 is THIS phase retro (self-referential at authorship time). Story 11.4 (still backlog) closes the phase via `sprint-status.yaml` epic transitions + PRD overlay flip + auto-memory PHASE STATUS update. One new substrate-library (`phase_1_5_completion_evidence.py` — sibling, not sixth component); one new CI gate (`phase-1.5-completion-evidence`); zero schema / taxonomy / agent edits. Per-story implementation artifacts under `_bmad-output/implementation-artifacts/11-*-*.md`.

## Phase 1 Invariants Under Phase 1.5 Pressure

| Invariant | Status in Phase 1.5 | Pressure Witness (Epic 9 + Epic 10) | Verdict |
|---|---|---|---|
| Loud-fail doctrine | held | mobile-mcp absence → `mobile-blocked` init-time + mid-run paths (9.5); mobile project ambiguous → halt (9.2); LAD-enabled + key-unset → `LAD-skipped` init-time (10.5); LAD-MCP mid-run failure → `LAD-skipped` runtime (10.5). All four surfaces emit markers with diagnostic_pointer. | ✅ HELD |
| Sensor-not-advisor | held | `detect_project_type` returns DetectionOutcome; orchestrator owns write/preserve/append (9.2). LAD wrapper returns FR51 envelope with `source: "lad"` findings; no recommended next actions; bucket × severity passthrough (10.2 + 10.3). | ✅ HELD |
| Contract-pair pattern | held + extended | Stories 9.1 / 9.4 / 9.5 shipped schema + validator + fixture in single commits (Phase 1 reflex held); 10.1 / 10.3 / 10.4 likewise. **New validator-untouched variant** ratified: Stories 9.1 / 10.1 / 10.3 — closed-set discipline carried activation without validator edit. Pressure-tested for structural completeness; corpus clarified the invariant from operational to structural. | ✅ HELD + EXTENDED |
| Atomic-vs-aggregated | held | Mobile sub_cause narrowed via single `Final[str]` constant inside existing `mobile_driver.py` (9.5); LAD-skipped narrowed via existing `diagnostic_pointer` surface (10.5); Story 11.1 validator emits NO runtime markers — release-time evidence is CI-level not atomic loud-fail (architecture.md Pattern 1 ratified in Story 8.7 AC-4, re-ratified in 11.1). | ✅ HELD |
| Substrate-component closure at FIVE | held | Epic 9 added 3 substrate-libraries without spinning a 6th component; Epic 10 added 0 substrate-libraries (LAD handled inside existing wrapper + dispatch + merge substrate); Story 11.1 added `phase_1_5_completion_evidence.py` as sibling of `mvp_completion_evidence.py` (substrate-library, not sixth component, mirrored shape). | ✅ HELD |
| Marker-taxonomy v1 27-class closed-set | held | PATCH bumps only — 1.3 → 1.4 → 1.5 in Epic 9 (sub_classifications for mobile); 0 bumps in Epic 10 (`LAD-skipped` Phase-1-pre-enumerated). ZERO top-level class additions across full Phase 1.5. Closed-set discipline pressure-tested by per-marker sub_classification authoring; held. | ✅ HELD |

**No invariant violations recorded across Phase 1.5.** Story 11.4 AC `:400` "no Phase 1 commitments … have been violated by Phase 1.5" attestation is empirically backed by the six rows above.

## Phase 1.5 Synthesis (Patterns Ratified Across Epics 9 + 10)

- **Pre-prepared substrate pattern, first-class status.** Epic 9.5's witness (Story 7.3's `_dispatch_total_block` already threading sub_classification — zero Python edit required) joined by three Epic 10 witnesses (Stories 10.2 `SpecialistId` Literal pre-included `lad` + envelope `source` enum pre-included `lad`; 10.3 envelope shape pre-permitted activation; 10.6 pluggability-gate Rule 1 + Rule 2 covered Review-LAD by construction at Story 1.10a landing). Four independent witnesses in 13 stories = first-class, no longer anecdotal. **Reflex carried into Phase 2:** before writing extension code for a closed-set member, audit the substrate for pre-prepared seams. Source of pre-preparedness is closed-set discipline applied at substrate-design time — closed-set discipline pays the labour-forward, labour-saved tax across phase boundaries.

- **Validator-untouched contract-pair variant.** Stories 9.1 / 10.1 / 10.3 corpus. The contract-pair pattern's load-bearing invariant is **single-commit landing of all surfaces affected**, NOT four-artifact edit. Validator-untouched contract-pairs ship the same single-commit discipline with a smaller diff when prior closed-set discipline + free-form-string fields handle activation without semantic widening. Phase 1's contract-pair definition was operational; Phase 1.5 corpus clarified the structural definition.

- **Cross-schema enumeration-equivalence axis pattern.** Story 9.5 added a third equivalence axis (`dependencies-schema sub_classification ⊆ marker-taxonomy sub_classifications`) inside substrate component 4 — extended the invariant surface without growing the component count. New equivalence axes land as additional structural tests inside existing substrate components, not as new components.

- **Reference-run option-(b) stand-in extended to mobile + run-against-self.** Phase 1 Story 8.7 AC-3 option-(b) precedent carried forward to Story 9.6 mobile (live re-capture forward-scoped to Phase 2 pending plugin-primitive deployability). Story 10.7 used a different mechanism — run against the development workspace itself — achieving the same 9-artifact target shape. Stand-in posture is not exotic; it is the operating mode while plugin-primitive runtime remains forward-scoped.

- **Dev's-call deviation disclosure standard.** Epic 9 produced 8 documented deviations across Stories 9.3 / 9.4 / 9.6; Epic 10 produced 3 (Stories 10.2 / 10.3 / 10.6). All disclosed in Completion Notes per Phase 1 standard (alternative-precedent-revisit). House style intact across the phase.

- **Drop-by-accumulation pattern travels twice.** Epic 9 retro (`:89-91`) + Epic 10 retro (`:197`). Zero `architecture.md` addendums authored across the entirety of Phase 1.5; codification carried by the retro corpus. The Phase 1 meta-lesson "prose action items don't land — only structural enforcement / story-AC does" empirically re-validated across two consecutive epics. This phase retro is the THIRD consecutive retro-corpus drop (Epic 8 origin → Epic 9 carry → Epic 10 second-witness → this phase-level synthesis).

## Housekeeping Debt Reconciliation (H1–H11 Cross-Phase Ledger)

| # | Item (short) | Origin | Status at Phase 1.5 Close | Next Trigger |
|---|---|---|---|---|
| H1 | `_atomic_write_text` promotion to `_shared.py` + `_NEXT_SPECIALIST_BY_STATE` consolidation | Phase 1 (Epic 8 retro) | NOT TRIGGERED (no 4th-consumer; no cleanup window opened) | 4th consumer OR cleanup window — carry into Phase 2 |
| H2 | Cross-major delta tripwire (5.9 → 6.0 OR BMM 6.10) | Phase 1 (Epic 8 retro) | NOT TRIGGERED (no BMM major movement) | BMM ≥ 6.10 OR Automator targets 6.0 — carry |
| H3 | NFR-P3 5-min first-loop empirical witness | Phase 1 (Epic 8 retro) | TRIGGERED + WITNESSED (twice — independent causes). Mobile: Story 9.6 captured 07:32 (mobile-mcp cold-start + iOS Simulator boot). LAD-enabled: Story 10.7 captured 05:24 (OpenRouter secondary-reviewer 295s timeout + uvx cold-start sub-contributor). **Forward implication for Phase 2: NFR-P3 articulation should be per-mode (web/api / mobile / LAD-enabled / LAD+mobile).** | Phase 2 deployment OR additional reference-run records |
| H4 | Story 8.1 deferred review patches (8 items) | Phase 1 (Epic 8 retro) | NOT TRIGGERED (Phase 1.5 active; cleanup window not opened) | Post-Phase-1.5 cleanup window — carry |
| H5 | Story 8.1 untested defensive WARN-log branch | Phase 1 (Epic 8 retro) | NOT TRIGGERED (no mock-injection PR; no real disagreement observed) | Mock-injection lands OR real disagreement — carry |
| H6 | Forward-pointer drift unified gate | Phase 1 (Epic 8 retro) | NOT TRIGGERED (forward-pointer LANDED flips handled manually across 9.4 / 9.5 / 9.6 / 10.x / 11.2 without significant pain). **Priority signal:** volume of manual flips in Phase 1.5 raises the signal; H6 should be re-evaluated if Phase 2 adds 5+ more retros / reference-run records without lands. | Phase 2 doc drift becomes pain — carry with raised priority |
| H7 | Pluggability-gate (FR62) 3 → 4 specialists | Epic 9 retro (new) | **TRIGGERED + RESOLVED** in Story 10.6 (structural witness + 4-specialist baseline). Retired. ✅ | (closed) |
| H8 | Live mobile reference-project re-capture against real maintainer-owned mobile app | Epic 9 retro (new) | NOT TRIGGERED (Phase 2 / runtime-deployable trigger; Story 7.1 plugin-primitive forward-scoping persists) | Phase 2 plugin-primitive deployability — carry |
| H9 | Pre-existing pytest count drift root-cause | Epic 9 retro (new) | NOT TRIGGERED (Epic 10 deltas all accountable per Epic 10 retro `:128`; Story 11.2 +1 re-baseline accountable per its AC-5 escape clause) | Drift recurrence in Phase 2 — carry |
| H10 | LAD dual-reviewer-fallback ADR-008 supplement (single-reviewer-mode codification) | Epic 10 retro (new) | ONE OBSERVATION (Story 10.7 — OpenRouter secondary-reviewer 295s timeout produced single-reviewer-mode synthesis per ADR-008's documented fallback). Codification trigger is second observation. | Second observation in any reference run — carry |
| H11 | Story 10.7 reference-run pattern (run-against-development-workspace) as opt-in OR CI gate | Epic 10 retro (new) | NOT TRIGGERED (open question for Phase 2 planning — whether to make the run-against-self feedback loop a CI gate or keep as opt-in) | Phase 2 planning — carry |

**Net Phase 1.5 delta:** `+5 added` (H7 + H8 + H9 + H10 + H11) `−1 retired` (H7) = `+4 net items carried into Phase 2`. H1–H6 carry UNCHANGED from Phase 1 close — none of the six pre-existing housekeeping items triggered during Phase 1.5. H3 received a Phase-1.5 supplement (per-mode-articulation context from Stories 9.6 + 10.7 dual-overage). Practical Phase 2 baseline is H1–H6 + H8 / H9 / H10 / H11 = 10 named-trigger items.

## Cross-Phase Continuity (Phase 1 → Phase 1.5)

| Dimension | Phase 1 Close | Phase 1.5 Close | Delta |
|---|---|---|---|
| Substrate-component count | 5 | 5 | 0 |
| Marker-taxonomy top-level classes | 27 | 27 | 0 |
| Marker-taxonomy MAJOR version | v1 | v1 | 0 MAJOR bumps |
| Dependencies-schema version | 1.1 | 1.4 | +0.3 (three PATCH-level bumps) |
| Envelope-schema shape | Phase 1 baseline | byte-stable | 0 |
| `failed_layers` enum | 3 | 4 | +1 (`lad`) |
| ADRs | 6 | 8 | +2 (ADR-007 mobile-mcp + ADR-008 lad) |
| Substrate-libraries | Phase 1 baseline | +4 | +4 (3 mobile + 1 phase-1.5-completion-evidence) |
| CI gates | 17 | 18 | +1 (`phase-1.5-completion-evidence`) |
| Specialists | 3 (dev / review-bmad / qa) | 4 (+ review-lad) | +1 |
| Reference-projects in index | 2 (web + api) | 3 (+ mobile) | +1 |
| Pluggability-gate specialist count | 3 | 4 | +1 |
| Production incidents | 0 | 0 | 0 |
| Architectural blockers | 0 | 0 | 0 |

Every additive delta column is positive or zero; no regression dimensions. The "no Phase 1 commitments violated" attestation Story 11.4 AC `:400` cites is mechanically verifiable against this table.

## Action Items

### Ratifications (codification confirmed; no work)

- Pre-prepared substrate pattern as first-class — four independent witnesses across 13 stories; substrate-audit-before-extension is house style.
- Validator-untouched contract-pair variant — single-commit-landing-of-affected-surfaces is the load-bearing invariant; not four-artifact-edit.
- Cross-schema enumeration-equivalence axis pattern — new axes land as structural tests inside existing substrate components.
- Reference-run option-(b) stand-in for mobile + run-against-self pattern — stand-in is operating mode pending plugin-primitive deployability.
- Dev's-call disclosure discipline — alternative-precedent-revisit format, in Completion Notes; standard across the phase.
- Drop-by-accumulation pattern — now confirmed across THREE retros (Epic 8 origin → Epic 9 carry → Epic 10 second-witness) + this phase-level synthesis; retro corpus is load-bearing alongside ADRs.

### Phase 2 Housekeeping Debt (land as story-AC at trigger time)

| # | Item | Trigger | Owner |
|---|---|---|---|
| H1 | Promote `_atomic_write_text` to `_shared.py`; consolidate `_NEXT_SPECIALIST_BY_STATE` | 4th consumer OR cleanup window | Dev |
| H2 | Cross-major delta tripwire (5.9 → 6.0 OR BMM 6.10) | BMM ≥ 6.10 OR Automator targets 6.0 | Dev |
| H3 | NFR-P3 per-mode articulation (web/api / mobile / LAD-enabled / LAD+mobile) | Phase 2 deployment OR additional reference-run records | Auto + Dana |
| H4 | Story 8.1 deferred review patches (8 items) | Post-Phase-1.5 cleanup window | Dev |
| H5 | Story 8.1 untested defensive WARN-log branch | Mock-injection PR OR real disagreement observed | QA |
| H6 | Forward-pointer drift unified gate (priority raised by Phase 1.5 manual-flip volume) | Phase 2 doc drift becomes pain OR 5+ further retros/reference-runs without lands | Dev |
| H8 | Live mobile reference-project re-capture | Phase 2 / runtime deployable to target projects | Auto + Dev |
| H9 | Pytest count drift root-cause | Drift recurrence in Phase 2 | Dev |
| H10 | LAD dual-reviewer-fallback ADR-008 supplement | Second observation of single-reviewer fallback | Dev |
| H11 | Story 10.7 run-against-self pattern as opt-in OR CI gate | Phase 2 planning | Auto |

### Team Agreements (carry into Phase 2)

- Phase 1 + Phase 1.5 invariants are house style — no re-litigation in Phase 2 stories.
- Specialist-specific algorithms (mobile-mcp / playwright / HTTP / LAD) live in their wrapper + substrate-library, not in shared dispatcher / merge / triage modules.
- Capability is config-opt-in; LAD-disabled / mobile-disabled state is bit-identical to Phase 1 + earlier-Phase-1.5 at dispatcher / cost-partition / marker / pluggability surfaces (NFR-I3 structurally enforced).
- Contract-pair pattern accepts validator-untouched commits when prior closed-set discipline carries activation; single-commit landing of affected surfaces is the load-bearing invariant.
- Pre-prepared substrate audit precedes extension-code authorship.

## Phase 2 Readiness Assessment

| Dimension | Status |
|---|---|
| All Phase 1.5 stories done (status as of retro) | 🟡 13/15 — Story 11.3 self-referential at authorship; 11.4 still backlog |
| All CI gates green | ✅ (ruff / mypy / pytest / mvp-completion-evidence / phase-1.5-completion-evidence / pluggability-gate (now 4-specialist) / no-destructive-resume-lint / naming-lint / fr33-fixture-gate / fr33-runtime-gate / hook-budget-gate / review-layer-failure-emission-gate / bundle-assembly-failure-emission-gate / dependencies-validator / enumeration-check / fixture-coverage / envelope-validator / event-validator) |
| Marker taxonomy stable for Phase 2 | ✅ v1 27-class closed-set preserved across full Phase 1.5 |
| Substrate-component count | ✅ FIVE (held across full Phase 1.5) |
| Pluggability-gate 4-specialist | ✅ (H7 closed in Story 10.6) |
| Dependencies-schema | ✅ `schema_version 1.4`; both `mobile-mcp` and `lad` activated |
| Envelope-schema | ✅ shape byte-stable across Phase 1.5; `failed_layers` enum at 4 values |
| Reference-run records produced | ✅ Story 9.6 (mobile) + Story 10.7 (LAD-web) both 9-artifact records; both cited in `phase-1.5-completion-evidence.md` |
| Architectural blockers for Phase 2 | ✅ NONE |
| Phase 1 + Phase 1.5 invariants violated | ✅ NONE |
| Known dark corners | ⚠️ H3 per-mode budget + H8 live mobile re-capture + H10 LAD dual-reviewer-fallback supplement + H11 run-against-self gate question — all cataloged + named-trigger |
| Production incidents | ✅ 0 across full Phase 1.5 |

**Verdict:** Phase 1.5 close (Story 11.4) clear to land. Phase 2 has a green runway.

## Significant Discoveries

- **Sycophancy-escape value claim empirically witnessed (Story 10.7).** 3-layer pass returned 0 findings against a 1279-line Stories-10.4+10.5 diff; LAD layer returned 12 substantively distinct findings, each defendable against blind/edge/auditor framings. The FR-P1.5-2 reference evidence Phase 1.5 was designed to produce. Carries into `phase-1.5-completion-evidence.md` FR-P1.5-2 row as `delivered`.
- **Pre-prepared substrate pattern reaches first-class via four independent witnesses.** Story 9.5 + Stories 10.2 / 10.3 / 10.6 — four witnesses in 13 stories is no longer anecdotal. Closed-set discipline at substrate-design time pays compound interest at activation time, including across phase boundaries.
- **Validator-untouched contract-pair variant clarifies the structural definition.** Stories 9.1 / 10.1 / 10.3 — contract-pair is single-commit landing of affected surfaces, not four-artifact edit. Phase 1's operational definition narrows to a structural one without weakening.
- **H3 NFR-P3 needs per-mode articulation.** Two independent overage causes (mobile cold-start dominated vs. OpenRouter secondary-reviewer timeout dominated) make the Phase-1-shape 5:00 budget mode-specific by construction. Phase 2 NFR articulation should split per mode.
- **Drop-by-accumulation travels twice within Phase 1.5.** Zero `architecture.md` addendums authored across the entire phase; codification carried by per-epic retros + this phase-level synthesis. The "prose action items don't land" meta-lesson holds for a third consecutive epic boundary.

## Closing

**Bob:** "Phase 1.5 closes cleanly. Two opt-in capabilities (mobile QA + Review-LAD) ship behind the same loud-fail / sensor-not-advisor / closed-set substrate that carried Phase 1; six invariants attest HELD; one housekeeping item (H7) retires; four new items catalog into Phase 2 with named triggers. The sycophancy-escape value claim is now empirically witnessed; the pre-prepared substrate pattern is first-class. Story 11.4 has the runway it needs."

**Auto (Project Lead):** "Drop-by-accumulation travels three retros deep. Closed-set discipline pays compound interest across phases. The substrate is structurally load-bearing for Phase 2. Onward."
