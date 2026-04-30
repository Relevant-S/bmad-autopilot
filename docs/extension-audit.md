# BMAD-extension audit

This document is the public audit surface that operationalizes the BMAD-extension discipline for the Automator. Its source authorities are FR64 (`_bmad-output/planning-artifacts/prd.md` line 899 — convention classification), FR65 (line 900 — public audit document maintenance), NFR-I4 (line 961 — BMAD-core-absorption migration behavior), ADR-002 (`_bmad-output/planning-artifacts/architecture.md` lines 99-204 — the 3×3 portability matrix that informs the `upstream-proposal` vs `automator-internal` boundary at the architectural level), ADR-003 (architecture.md lines 205-334 — and specifically the "Unknown-unknown skip-classes routing" elaboration at lines 279-292, which delegates the operational workflow this doc owns), and Pattern 7 (architecture.md lines 999-1005 — story-doc section adherence, which names `## QA Behavioral Plan` as an upstream-proposal story-doc section).

This doc IS authoritative for: the per-convention table; the five canonical principle paragraphs (epic-close marker sweep, remediation-shape, spike-with-bounded-timebox, atomic-vs-aggregated, finding-taxonomy bumps — the no-introductions principle); the skip-class recognition workflow; the per-convention-add procedure. This doc does NOT enumerate every marker class in `schemas/marker-taxonomy.yaml` (the taxonomy is the authoritative enumeration; this doc lists conventions, not markers); it does NOT re-derive ADR-002's 3×3 classification matrix (architecture.md is canonical for that); it does NOT specify implementation details for any individual convention (those live in the conventions' implementing FRs/NFRs).

The doc is **review-enforced**, not CI-enforced (per ADR-003 line 292) — it is a contributor-discipline artifact, not a CI gate.

---

## Classification taxonomy

Per FR64, every Automator-introduced convention must carry exactly one of three classifications. Multi-value, novel-value, and unclassified entries are forbidden — the extension-purity anti-metric (`_bmad-output/planning-artifacts/prd.md` line 103 — "≤ 20% automator-internal without an explicit revisit condition") measures against this single-value column.

- **`automator-internal`** — an implementation detail that lives at the Automator's wrapper layer (orchestrator, hook scripts, run-state schema, envelope fields) and does NOT extend the BMAD-core lifecycle, story-doc template, or upstream conventions. Choose this when the convention is private to the Automator's mechanism and would have no meaning outside it. Examples: orchestrator wrapper flags, internal envelope fields that wrap (without reshaping) existing BMAD-core taxonomies, run-state field naming. Migration plan: `N/A — internal-only`. NFR-I4 does not apply (the convention is never absorbed upstream because it has no upstream-relevant surface).
- **`upstream-proposal`** — an extension that reshapes a BMAD-core surface (lifecycle states, story-doc sections, architectural patterns) and is a candidate for upstream RFC submission to BMAD core. Choose this when the convention WOULD have meaning in BMAD core and where the architectural pathway is "ship in the Automator first; if BMAD core absorbs it, follow NFR-I4's migration." Migration plan: populated per NFR-I4's four-stage flow — **acknowledgment** (BMAD core ships an equivalent feature) → **adapter window** (both paths work simultaneously) → **deprecation** (the Automator's path is marked deprecated with a release-notes flag) → **removal** (the Automator's path is removed in a subsequent minor release).
- **`research-needed`** — the classification is genuinely undecided pending upstream decision, primitive stability, or community input. Choose this when neither `automator-internal` nor `upstream-proposal` is honest yet and the team has bounded the research via the spike-with-bounded-timebox pattern (see § Research-blocker handling). Migration plan: `pending research conclusion`. The classification MUST resolve to one of the other two before MVP close — see the per-release re-audit cadence in § Skip-class recognition workflow.

The choice constrains future migration behavior per NFR-I4: classifying a convention as `upstream-proposal` is a commitment to ship adapter behavior when BMAD core absorbs the equivalent feature; classifying as `automator-internal` is a commitment that the convention is never absorbed (and so misclassifying an absorbable convention as `automator-internal` traps the project on a forked path). Honest classification at introduction time is therefore a load-bearing engineering decision, not a documentation chore.

---

## Per-convention table

The five MVP-close seed entries are listed in chronological-introduction order (the order they were named in the architecture / PRD). Routine adds to this table are append-only — existing rows are not reordered, so the diff history doubles as the audit trail and PR review remains tractable. Each entry carries a single classification value drawn from the 3-tier set; entries are NEVER classified with multiple values, NEVER classified with novel values, NEVER left unclassified.

| Convention name | Classification | Rationale | Migration plan | Revisit conditions |
|---|---|---|---|---|
| `qa` lifecycle state (between `review` and `done`) | `upstream-proposal` | Behavioral verification is a load-bearing seam between code review and merge — not a sub-state of `review`. The `qa` lifecycle state is named in PRD FR23 (`_bmad-output/planning-artifacts/prd.md` line 838) and consumed by Story 2.4. If BMAD core absorbs the lifecycle extension, the Automator follows NFR-I4. | Per NFR-I4: **acknowledgment** — BMAD core ships a `qa` (or equivalently-named) lifecycle state in the canonical state machine; **adapter window** — the Automator's orchestrator accepts both the BMAD-core state name and the Automator's, normalizing on read; **deprecation** — the Automator's standalone state is flagged in release notes with the BMAD-core mapping; **removal** — the standalone state is removed once users have migrated within the documented adapter window. | BMAD core ships a `qa` (or equivalently-named) lifecycle state (NFR-I4 acknowledgment trigger); or upstream RFC is rejected (classification flips to `automator-internal` with a documented forked-path commitment). |
| `## QA Behavioral Plan` story-doc section | `upstream-proposal` | Plan-driven AC iteration with persistence (PRD FR23, line 838) needs a documented story-doc section so the plan survives across re-runs and AC-hash drift detection has a stable target. Pattern 7 (architecture.md lines 999-1005) names this section as an upstream proposal. If BMAD core adopts the section, the Automator follows NFR-I4. | Per NFR-I4: **acknowledgment** — BMAD core's story-doc template adds the section; **adapter window** — the Automator writes/reads at both the BMAD-core-canonical heading and its own; **deprecation** — the Automator-canonical heading is flagged with mapping notes; **removal** — the Automator-canonical heading is removed once usage migrates. | BMAD core's story-doc template adds the section (NFR-I4 acknowledgment trigger); or upstream RFC is rejected. |
| `retry_mode: fix-only` Dev invocation flag | `automator-internal` | An implementation-detail flag living at the orchestrator-Dev wrapper layer (PRD FR10, line 821 — Orchestrator applies a capability-level fix-only constraint to Dev's invocation). It is NOT a BMAD-core lifecycle change; it is mechanism, not contract. | N/A — internal-only. | BMAD core ships an equivalent retry-scope mechanism. |
| Seam-transition orchestrator pattern (sensor-not-advisor envelopes + flow-policy-in-orchestrator) | `upstream-proposal` | The architectural pattern that makes multi-specialist coordination work without shared state — specialists return schema-validated envelopes describing what they did/saw; the orchestrator owns flow policy. Long-term-vision candidate for upstream RFC per ADR-002's cell-1 stability commitment (architecture.md lines 99-204). | Per NFR-I4: **acknowledgment** — BMAD core ships a canonical seam-transition pattern; **adapter window** — the Automator's orchestrator can both produce and consume BMAD-core's canonical envelopes; **deprecation** — the Automator's standalone envelope shape is flagged with mapping notes; **removal** — the Automator's standalone shape is removed once consumers migrate. | BMAD core ships a canonical seam-transition pattern (NFR-I4 acknowledgment trigger); or upstream RFC is rejected. |
| `failed_layers` graceful-degradation field on Review-BMAD envelope | `automator-internal` | Wraps `bmad-code-review`'s existing 3-layer taxonomy (Blind Hunter / Edge Case Hunter / Acceptance Auditor) per PRD FR28 (line 847) without reshaping it. The field is mechanism for the Automator's per-layer failure surface, not an extension of BMAD-core's review contract. | N/A — internal-only. | BMAD core ships a layer-failure-tracking field on the review envelope. |
| `meta: review-completeness` field on Review-BMAD synthetic findings | `automator-internal` | Story 3.3 (`failed_layers` graceful-degradation three-channel atomic emission per FR28 + FR56) pairs each failed review layer with one synthetic `decision_needed: HIGH` finding emitted by `surface_failed_layers` so the human reviewer at PR-bundle reading time sees the per-layer failure alongside the `failed_layers` envelope-field declaration AND the `review-layer-failed` marker comment. The `meta` field is the wrapper-layer-only discriminator that distinguishes wrapper-generated meta-findings (whose presence signals review incompleteness) from layer-produced content findings (whose presence signals AC violations); without the discriminator, downstream tooling (Story 3.4's PR-bundle review-section rendering at epics.md line 1729) cannot filter the two finding kinds apart. The field is mechanism for the Automator's per-layer failure surface — by analogy to the `failed_layers` row above — not an extension of BMAD-core's review contract; BMAD core has no upstream-relevant analogue at MVP. The schema enum is intentionally narrow (`[review-completeness]` — single value); future meta-finding kinds (e.g., the Story 4.9 `verification_mode: exploratory-heuristic` precedent at epics.md line 2068) extend the enum via a follow-on schema bump recorded as a new row below this one per the append-only discipline. | N/A — internal-only. | BMAD core ships an equivalent meta-finding mechanism on the review envelope, OR BMAD core's review surface adopts the synthetic-finding pattern for failed-layer surfacing. |

The column ordering above (convention name / classification / rationale / migration plan / revisit conditions) is the canonical layout — preserved across edits so PR diffs remain tractable. New rows are appended below the existing five (chronological-introduction order, append-only); existing rows are NEVER reordered. The append-only discipline IS the audit trail — git history is the per-row introduction log.

Per FR65, every entry has an explicit revisit condition in the "Revisit conditions" column: `upstream-proposal` entries name the NFR-I4 acknowledgment trigger and the RFC-rejection fallback; `automator-internal` entries name the BMAD-core feature whose arrival would reopen the classification; `research-needed` entries name their bounding spike per § Research-blocker handling.

---

## Skip-class recognition workflow

This subsection elaborates ADR-003 (architecture.md lines 205-334) and specifically codifies the operational workflow for the unknown-unknown skip-class routing path delegated to this doc by ADR-003 lines 279-292.

A newly-recognized skip-class — i.e., a runtime skip event the FRs/NFRs did not anticipate at MVP-design time — flows through the four-step process below (verbatim from ADR-003):

```
newly recognized skip-class →
  add to marker-taxonomy.yaml →
  add to orchestrator-event.yaml →
  add fixture / synthetic story →
  re-run CI checks (3), (4), (5) →
  merge
```

The cadence: **the audit doc is reviewed at the close of every epic** (per § Marker taxonomy vs. audit doc — known-knowns / unknown-unknowns split, where the epic-close marker sweep procedural step lives) **and at every release** (per FR65's "with revisit conditions where applicable" framing combined with the extension-purity anti-metric's per-release measurement cadence at PRD line 103). The two cadences compose: epic-close sweeps catch convention drift produced inside the just-finished epic; per-release sweeps catch drift accumulated across multiple epics and any `research-needed` entries whose timebox has expired without resolution.

The routing decision is explicit:

- **Known skip-classes** — those named by FRs / NFRs already in scope at MVP-design time — flow through `schemas/marker-taxonomy.yaml` (Story 1.4) + `schemas/orchestrator-event.yaml` (Story 1.3) + the harness fixture corpus (Story 1.7). These three sources are CI-enforced via the substrate components landed in stories 1.5 (`enumeration_check`) and 1.8 (`fr33-fixture-gate`). The known-skip-class set is reconciled by code at every PR.
- **Unknown-unknown skip-classes** — drift the FRs/NFRs didn't anticipate — flow through this doc and are added to the per-convention table per the append-only discipline above. The audit step is review-enforced, not CI-enforced; reviewers verify the classification is honest and the rationale is load-bearing.

The CI-vs-review split per ADR-003 line 292:

> "Layers A/B/C and the five substrate components are CI-enforced; skip-class recognition is review-enforced. The harness completeness invariant is over the known skip-class set under CI; the unknown-unknown layer is review-enforced via audit."

This is the architectural commitment that makes the audit doc load-bearing rather than aspirational: code reading text catches known drift; humans reading code catch unknown drift; the harness's structural limit is named honestly rather than papered over.

---

## How to add a new convention

A contributor adding a new Automator-introduced convention follows this procedure:

1. **Read the classification taxonomy** (this doc § Classification taxonomy) — confirm you understand what each of the three classifications means and how the choice constrains future migration behavior per NFR-I4.
2. **Read the existing per-convention table** (this doc § Per-convention table) — confirm your convention isn't already enumerated. If it is, the existing entry's classification governs; propose an edit only if the classification is dishonest under new evidence.
3. **Copy `examples/bmad-extension-audit-entry.md`** as the entry template — it shows the canonical shape (convention name / classification / rationale / migration plan / revisit conditions) with a worked example you can pattern-match.
4. **Classify your convention** per the 3-tier taxonomy. The classification is a load-bearing engineering decision, not a documentation chore — misclassifying an upstream-relevant convention as `automator-internal` traps the project on a forked path; misclassifying an internal mechanism as `upstream-proposal` floods upstream with non-load-bearing RFCs.
5. **For `upstream-proposal` classifications, draft the migration plan** per NFR-I4's four-stage flow (acknowledgment → adapter window → deprecation → removal). For `automator-internal`, write `N/A — internal-only`. For `research-needed`, write `pending research conclusion` AND name the bounding spike per § Research-blocker handling.
6. **Append the new row at the bottom of the per-convention table** — existing rows are never reordered. Then submit the PR; the audit doc is review-enforced, not CI-gated, so the reviewer's job is to assess that the classification is honest, the rationale is load-bearing, and the migration plan (if applicable) is realistic.

The contributor-onboarding entry point is `CONTRIBUTING.md`, which references this doc and walks the contributor through the same steps.

---

## Marker taxonomy vs. audit doc — the known-knowns / unknown-unknowns split

This subsection states the canonical principle governing the boundary between the v1 marker taxonomy (`schemas/marker-taxonomy.yaml`) and this audit doc, and codifies the epic-close marker sweep that operationalizes the principle.

> **"If a marker class is required by a named FR or NFR already in scope, it belongs in the v1 taxonomy (`marker-taxonomy.yaml`) — added proactively at epic-close, not discovered at runtime. The audit doc's job is unknown-unknowns: convention drifts the team didn't anticipate, classifications that emerged during implementation, and skip-classes the FRs/NFRs didn't name. Known-knowns travel through the taxonomy bump rule (Story 1.4); unknown-unknowns travel through this audit doc."**

### Epic-close marker sweep

At the close of every epic, the team sweeps that epic's FRs/NFRs for marker classes the requirements name (or imply via dependency-failure profiles in `dependencies.yaml` per SDN-001). Each named-or-implied class is confirmed present in `schemas/marker-taxonomy.yaml`. Missing classes are added BEFORE the epic merges — proactively, at epic-close, not reactively at downstream-epic runtime.

**Worked example — Epic 4's `playwright-mcp-unavailable` proactive add (per FR17 + ADR-002):**

PRD FR17 (`_bmad-output/planning-artifacts/prd.md` line 831 — "QA drives the running product independently — via Playwright MCP for web project types, via HTTP for API project types — against each acceptance criterion") combined with ADR-002's graceful-degrade dependency profile (architecture.md lines 99-204) names a Playwright-MCP-unavailability skip-class. Story 4.4 (Epic 4) is where this skip-class will run in production — but the marker class `playwright-mcp-unavailable` was added to `schemas/marker-taxonomy.yaml` at the close of Epic 1's taxonomy story (Story 1.4), NOT discovered at Epic 4's runtime. The taxonomy entry is verifiable today at `schemas/marker-taxonomy.yaml` lines 216-222 — sweep performed proactively per the principle above.

The worked example demonstrates the sweep IN this doc: the FR-to-marker mapping is named (FR17 + ADR-002 → `playwright-mcp-unavailable`); the existing taxonomy entry is pointed to as the "this is what proactive-add looks like" instance. Future epics' sweeps will produce similar mappings — written into this section at epic close so the audit trail accumulates rather than being re-derived.

---

## Marker class boundaries — the remediation-shape principle

> **"Markers are remediation-shaped, not emission-point-shaped. Two events that share an emission point but require different remediation paths get distinct marker classes — the reconciler routes by class, and routing by sub-classification fields breaks the flat-routing abstraction. Worked example: `hook-failed` and `scope-assertion-violation` share the SubagentStop hook's non-zero exit path but differ in remediation (fix the hook script vs review Dev's actual diff against declared scope), so they are distinct classes. Same pattern for `review-layer-failed` (Epic 3) which is distinct from `hook-failed` for the same reason."**

**Contributor-discipline checklist item:** *Does this marker have a remediation path distinct from existing classes? If yes → distinct class. If no → sub-classification of the existing class.*

The principle is verifiable against the existing taxonomy: `hook-failed`, `scope-assertion-violation`, and `review-layer-failed` are all enumerated in `schemas/marker-taxonomy.yaml` as distinct classes precisely because their remediation paths differ — fix the hook script (`hook-failed`); review Dev's actual diff against the declared scope (`scope-assertion-violation`); investigate the failed review layer's specific failure mode (`review-layer-failed`). The reconciler routes by class; emission-point-based grouping would have collapsed these into a single marker and lost the remediation-routing signal.

---

## Marker class boundaries — the atomic-vs-aggregated principle

> **"Markers represent atomic failure surfaces, not aggregated conditions across multiple atomic failures. If an event can be decomposed into existing markers, decompose it. New marker classes earn their place by representing a remediation surface that doesn't already have one — not by aggregating multiple existing classes under a new umbrella name. Worked example: Epic 7's `init` precondition checks could be aggregated under a hypothetical `init-precondition-failed` umbrella, but each underlying failure (TEA missing, Playwright MCP unavailable, BMAD core wrong version, git unexpected state) maps to existing markers (`env-setup-failed`, `playwright-mcp-unavailable`, etc.) — so `init`'s diagnostic layer aggregates the existing markers in named-invariant diagnostic output (per NFR-O5) rather than introducing a new aggregator class. The diagnostic layer's job is aggregation; the marker taxonomy's job is atomic surfaces."**

**Contributor-discipline checklist item:** *Can this event be decomposed into existing markers? If yes → use existing markers + diagnostic-layer aggregation. If no → new class with distinct remediation surface.*

**Apply together with the remediation-shape principle.** A proposed new marker class earns its place ONLY when (i) its remediation path is distinct from existing classes (the remediation-shape principle above) AND (ii) it is not decomposable into a combination of existing classes (this principle). Failing test (i), the proposal routes to sub-classification of an existing class. Failing test (ii), the proposal routes to diagnostic-layer aggregation per NFR-O5. Only when both tests pass is a new marker class warranted.

---

## Finding-taxonomy bumps — the no-introductions principle

> **"BMAD core's finding taxonomy is the canonical source for `bucket` ∈ `{decision_needed, patch, defer, dismiss}` and `severity` ∈ `{HIGH, MED, LOW}` per FR27. The Automator does NOT fork this taxonomy. ANY proposed addition of a bucket value, severity value, or finding classification field is a BMAD-extension event recorded here per FR64 / FR65; the default classification is `upstream-proposal` (BMAD core's review surface is the natural home for the addition). `automator-internal` applies ONLY when justification proves the bump is scoped strictly to the Automator's wrapper layer with no upstream-relevant surface — by analogy to the `failed_layers` graceful-degradation field at the per-convention table. The forward-compatibility loud-fail path at `validate_return_envelope` is the architectural backstop that makes silent drift impossible: a finding carrying an out-of-enum bucket or severity value, or an extra classification field, is rejected at the substrate seam — the bump must travel through this audit doc and `envelope.schema.yaml` BEFORE it can survive the gate."**

**Contributor-discipline checklist item:** *Is this a new bucket value, severity value, or finding classification field on the Review-BMAD envelope's `findings`? If yes → record the BMAD-extension event in this section's audit trail BEFORE bumping `envelope.schema.yaml`'s enum or `$defs/finding` shape; default classification is `upstream-proposal` unless the convention is provably wrapper-layer-only.*

The principle is verifiable against the existing artifacts: `envelope.schema.yaml` `$defs/finding` already declares `bucket` and `severity` as strict `bucket` enum (line 129) and `severity` enum (line 132) and `additionalProperties: false` on findings (line 110); the Review-BMAD wrapper at `agents/review-bmad-wrapper.md` documents the bucket × severity passthrough invariant as a named contract section (Story 3.2's "Finding-taxonomy passthrough discipline"); the substrate's `validate_return_envelope` rejects any envelope whose findings violate the schema. The three artifacts agree at MVP scope. Epic 3 introduces ZERO new taxonomy values — the no-introductions invariant is established structurally by the wrapper's passthrough section + the schema's enum constraint, and operationally by THIS subsection (what to do IF a future contributor or upstream release proposes a bump). The per-convention table at lines 27-34 is NOT modified at this story; the existing five seed entries remain in their chronological-introduction order; the append-only discipline holds.

The forward-compatibility loud-fail ordering is **record first, bump second**: when upstream `bmad-code-review` legitimately introduces a new bucket or severity value (e.g., a future `improvement` bucket), the operational response is (1) record the BMAD-extension event in the per-convention table per § How to add a new convention, (2) bump `envelope.schema.yaml`'s enum to include the new value, (3) re-run the harness CI sweep so the substrate seam now accepts the new value structurally, (4) update `_CANONICAL_BUCKETS` / `_CANONICAL_SEVERITIES` in `tools/loud-fail-harness/tests/test_review_bmad_wrapper.py` to include the new value. Skipping step (1) is a documented contract violation: the audit trail loses its load-bearing record of when and why the taxonomy bumped. Step (1) is review-enforced — the audit trail is not CI-gated but is a mandatory code-review requirement before any schema enum bump merges; the substrate-seam loud-fail prevents envelopes carrying the new value from surviving validation until step (2) completes, but does NOT block a schema bump from landing without an audit-doc entry.

---

## Research-blocker handling — the spike-with-bounded-timebox pattern

> **"A research blocker that gates downstream work must surface as a story in its dependent epic with: (a) a defined exit criterion enumerating the plausible outcomes, (b) a bounded timebox, (c) a named fallback outcome that ships if the timebox expires without convergence. Without these three, 'parallel with explicit dependency' becomes 'indefinite stall.' Worked example: Epic 5 Story 5.7 audits the `deferred-work.md` format with three named outcomes (adopt existing / extend existing / define our own), 1-week timebox, fallback to outcome 3 (define our own, classify as `automator-internal`). Apply this pattern to Epic 7's plugin-primitive-stability spike and to any future spike-blockered story."**

The pattern's fully-compliant instances at MVP scope (each has a defined exit criterion, a bounded timebox, and a named fallback):

- **Story 5.7** (`5-7-deferred-work-md-format-spec-audit-integration-research-blocker-spike-bounded-with-named-fallback`) — audits the `deferred-work.md` format spec; the canonical worked example above.
- **Story 7.1** (`7-1-claude-code-plugin-primitive-stability-spike-task-bounded-with-named-fallback`) — Claude Code plugin primitive name and stability; per epics.md the spike is bounded with a named fallback.

The four open research blockers from architecture.md lines 847-852, listed verbatim, with the discharging story per the spike-with-bounded-timebox pattern:

- **`deferred-work.md` format spec** — blocks loud-fail handling for `defer`-bucket findings. Discharged by Story 5.7.
- **TEA API surface for orchestrator handoff** — does orchestrator await TEA completion; what TEA artifacts does QA ignore vs. consume; how does the boundary surface in run-state. Discharged by Story 2.1.
- **Upstream proposal format for BMAD-METHOD** — blocks submission of `qa` lifecycle state and `## QA Behavioral Plan` proposals. **Intentionally unbounded at Epic 1 close**: no dedicated discharging story exists in the current epic plan because the upstream RFC track for BMAD-METHOD depends on BMAD core's public RFC process being established, which is not yet determined. This blocker will be formally bounded with a discharging story at Epic 1 retrospective or when Epic 6+ planning names the RFC preparation story. The `qa` and `## QA Behavioral Plan` table entries remain `upstream-proposal` with their migration plans intact regardless of this blocker's open status.
- **Claude Code plugin primitive name and stability** — shapes install path (primary vs fallback) and repo layout. Discharged by Story 7.1.

A `research-needed` classification entry on the per-convention table MUST name its bounding spike from this list (or a successor entry added as research blockers accumulate). Without a bounding spike, the classification has no exit criterion and the convention drifts into the indefinite-stall failure mode the principle exists to prevent.

---

## Marker emission rules — the structural-not-era-based principle (Story 3.4 worked instance)

> **"The `walking-skeleton-bundle` marker emission rule is structural — predicated on whether `is_loud_fail_block_present()` returns `False` — NOT era-based — predicated on a hardcoded 'if Epic == 2' check. Epic 3 retains the marker emission rule unchanged. The marker continues to emit because `is_loud_fail_block_present()` continues to return `False` at Epic 3 substrate state; Epic 3 is NOT the era that triggers suppression. Epic 6 / Story 6.1 owns the loud-fail block landing that flips the predicating flag, at which point emission inverts without any edit to the bundle-assembly rendering code."**

The principle is verifiable against the existing artifacts: `schemas/marker-taxonomy.yaml` lines 210-216's `walking-skeleton-bundle` `diagnostic_pointer` prose names the rule ("absent loud-fail block triggers the marker, NOT 'Epic 2 era triggers the marker' (rule clarified by Epic 6).") AND `tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py`'s module docstring at lines 41-52 re-states it AND the runtime predicate at `_emit_walking_skeleton_marker` (lines 680-698) consults `thickening_flags.is_loud_fail_block_present()` directly. Story 3.4 is the first downstream test of the rule: at Epic 3 substrate state the renderer surfaces a thickened review-section bucket × severity grouping AND the `is_full_review_present` flag flips to `True`, but the `walking-skeleton-bundle` marker continues to emit because the predicating flag (`is_loud_fail_block_present`) stays `False`. The companion regression test `test_walking_skeleton_marker_still_emitted_at_epic_3_substrate_state` in `tests/test_bundle_assembly.py` is the baseline guard against accidental Epic-3 / 4 / 5 pre-emption of Epic 6's responsibility; the Story 2.11 AC-4 test `test_walking_skeleton_marker_suppressed_when_loud_fail_block_present` (which substitutes a stub flag namespace) is the structural witness that the inversion fires correctly when Epic 6 lands the production flag flip.

---

## Contributor-discipline notes

This subsection holds append-only contributor-discipline notes — fixture/file location invariants, naming overlaps to avoid, and similar review-time conventions that are NOT BMAD-extension classification events (those go in the per-convention table above). These notes are review-enforced per `extension-audit.md`'s overall posture (ADR-003 line 292), NOT CI-enforced; reviewers verify the discipline at PR review time.

### Epic 2 walking-skeleton smoke fixture vs. Epic 7 user-facing onboarding sample (Story 2.13 resolution)

Two artifacts share a "sample story" surface concept but live at structurally different filesystem locations and serve fundamentally different audiences. Conflating them is the most plausible drift the smoke fixture's "test infrastructure only" identity exists to prevent.

- **Epic 2 smoke fixture** — `bmad-autopilot/tools/loud-fail-harness/tests/fixtures/sample-story-walking-skeleton.md`. Audience: Epic 2 maintainers running the harness's CI smoke suite. Lifecycle: CI-only; never user-visible; loaded by `tests/test_walking_skeleton_smoke.py` via `find_repo_root` + relative path. Distribution: per architecture.md View 2 lines 1109–1141, `tools/` is excluded from the shipped distribution unit, so the fixture is structurally guaranteed to be CI-only.
- **Epic 7 user-facing FR39 sample** — `_bmad-output/implementation-artifacts/sample-auto-001.md` (inside the user's BMAD project). Audience: practitioners onboarding to BMAD. Lifecycle: scaffolded once at install time by Epic 7's `init`; user-visible; lives under the user's BMAD project filesystem (View 3 line 1171), NOT inside the `bmad-autopilot/` source repo.

The structural separation invariant: the Epic 2 smoke fixture is NEVER `init`-scaffolded. Epic 7's init code MUST NOT discover, copy, symlink, or reference `tools/loud-fail-harness/tests/fixtures/sample-story-walking-skeleton.md`. The View 2 distribution-unit boundary makes this structurally guaranteed; this note records the discipline explicitly so future contributors see the rationale.

Review-time enforcement contract — a PR is a contract violation flagged at code review if it:

- moves the smoke fixture under `bmad-autopilot/examples/` (e.g., `examples/sample-stories/...` or `examples/synthetic-stories/...`);
- references the smoke fixture from `init`, from the user-facing onboarding-sample scaffolding, or from any deployed runtime artifact (skills, agents, hooks, schemas);
- renames the smoke fixture to overlap with `sample-auto-001.md` (e.g., `sample-walking-skeleton-001.md` is fine; `sample-auto-001-skeleton.md` is not — the `sample-auto-` prefix belongs to the Epic 7 user-facing-sample namespace).

The contributor-discipline note is review-enforced per `extension-audit.md`'s overall posture (ADR-003 line 292): there is no harness gate for this fixture-location invariant; the discipline lives in this document and in PR review.
