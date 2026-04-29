---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-04-25'
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/product-brief-bmad_automation.md
  - _bmad-output/planning-artifacts/product-brief-bmad_automation-distillate.md
  - _bmad-output/brainstorming/brainstorming-session-2026-04-24-1446.md
contextMemory:
  - memory/reference_lad.md
  - memory/project_tea_findings.md
  - memory/project_bmad_conventions.md
  - memory/project_phase1_architecture.md
  - memory/project_bmad_automator.md
  - memory/user_role.md
  - memory/feedback_rejected_ideas_pattern.md
workflowType: 'architecture'
project_name: 'bmad_automation'
user_name: 'Auto'
date: '2026-04-25'
---

# Architecture Decision Document — bmad_automation

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Architectural Decisions

### ADR-001: Orchestrator Implementation Primitive

**Status:** Decided.
**Date:** 2026-04-25.

#### Context

The Orchestrator is the seam-transition state machine across BMAD lifecycle states (`ready-for-dev → in-progress → review → qa → done`) and owns all flow policy: retry budgets, escalation routing, env lifecycle, scope-assertion enforcement. The PRD names it "main session + skill" (Developer-Tool Requirements → Project-Type Overview); the brainstorm named "Option D: main session + ≤3 hooks + subagents." Neither source decides *how the orchestrator is structurally bound to the main session*. Three primitive options exist:

- **A — Skill in main session.** The orchestrator's prompt is a skill loaded into the main Claude Code session; flow policy executes inside the main session's reasoning loop.
- **B — Long-lived subagent.** The orchestrator is its own subagent, invoked once per story run, internally dispatching specialist subagents and returning at terminal seams.
- **C — Hybrid (skill loaded into a subagent runtime).** Skill provides prompt content; subagent provides execution boundary.

The decision cascades into where flow policy lives, how `status`/`resume`/SessionStart reattachment work, how per-seam streaming behaves under NFR-O1, and how cleanly the portability principle holds.

**Option C (Hybrid) is dismissed before the matrix.** It combines both Claude-Code-shape couplings (skill-loading mechanism + subagent-runtime mechanism) without unique advantages: every axis on Hybrid collapses to either A's or B's profile, and on no axis does Hybrid win. The matrix below evaluates A vs B only.

#### Trade-off Matrix

| Axis | A: Skill in main session | B: Long-lived subagent (or re-invoke-per-seam) |
|---|---|---|
| **Flow-policy contract (sensor-not-advisor schema-symmetry)** | Asymmetric in pure form; resolvable by enforcing envelope-shaped output at CI for orchestrator-emitted seam events. Mitigation reuses specialist-envelope CI machinery. | Native — every subagent return is envelope-shaped. |
| **Reattachment (NFR-R2, NFR-R7)** | File-driven via SessionStart hook + run-state.yaml + git branch. | Same — file-driven. Process boundary is convenience, not load-bearing. |
| **Streaming (NFR-O1: per-seam live in main session)** | Native to main session; no relay needed. | Either depends on Claude Code's subagent-output relay (primitive-shape leak — contradicts portability) or re-invokes per seam (token cost penalty). |
| **Cost (NFR-P1: <$3 target / <$5 ceiling)** | ~1 skill load + N specialist invocations = N+1 context entries on happy path. | Long-lived: comparable to A (N+1). Re-invoke-per-seam: ~2N entries — 50–100% penalty against $3 target. |
| **Portability** | Skill-load is Claude-Code-shape; portable surface is `(orchestrator-prompt-logic + run-state.yaml schema + event protocol)`. | Subagent runtime is Claude-Code-shape; portable surface is `(orchestrator-prompt-logic + run-state.yaml)`. Equivalent leak; cleaner only if the target host has a similar subagent primitive. |
| **Implementation simplicity** | No exotic primitive use; skill loading is documented and stable at MVP floor (Claude Code v2.1.32+). | Long-lived requires recursive subagent dispatch (orchestrator-subagent invokes specialist-subagents) — pattern not documented at MVP floor; may require workarounds. |

#### Decision

**Option A — Orchestrator as a skill loaded into the main Claude Code session, paired with an envelope-shaped output protocol enforced at CI for orchestrator-emitted seam events.**

The skill defines the orchestrator's prompt logic. The orchestrator's runtime is the main session's reasoning loop. State persists in `_bmad/automation/run-state.yaml`. At every seam transition (specialist dispatched, specialist returned, retry triggered, escalation triggered, merge-ready), the orchestrator emits a schema-validated event matching `orchestrator-event.yaml`. CI validates orchestrator-emitted events at seam boundaries against the schema; the same enforcement machinery that protects specialist-envelope schema-symmetry covers the orchestrator.

#### Rationale

- **Schema-asymmetry is resolvable without changing primitive.** Envelope-shaped output protocol enforced at CI makes sensor-not-advisor symmetric across orchestrator and specialists. Primitive (skill) is decoupled from the invariant's enforcement (CI schema check).
- **Streaming (NFR-O1) is decisive.** Live per-seam main-session streaming is an explicit NFR. Options B and C either leak the subagent-output relay mechanism (contradicting the portability principle) or pay a 50–100% per-story cost penalty. Option A streams natively.
- **Cost (NFR-P1) realistic case favors A.** B-long-lived is theoretically cost-comparable but requires recursive subagent dispatch — undocumented at MVP floor. Falling back to B-re-invoke-per-seam puts the $3 target and $5 ceiling at material risk.
- **Reattachment is file-driven, not process-driven.** SessionStart hook + run-state.yaml + git branch makes reattachment work for any primitive. This axis doesn't discriminate.
- **Portability is cleanest as logic + state file + protocol.** Option A makes this articulation natural: skill is the *binding* to Claude Code; the portable surface is `(orchestrator-prompt-logic.md, run-state.yaml schema, orchestrator-event.yaml, specialist envelope schema)`. Future ports rebind to other host runtimes.
- **Implementation simplicity at MVP matters.** Option A uses documented stable primitives. Option B requires investigating recursive dispatch.
- **Consistency with brainstorm Option D.** "Main session + ≤3 hooks + subagents" placed orchestrator in main session; Option A is the structural realization of that placement.

#### Consequences

This decision commits the architecture to:

1. **An `orchestrator-event.yaml` artifact** parallel to the specialist envelope schema, enforced by the same CI mechanism (sensor-not-advisor schema enforcement covers both).
2. **Orchestrator-emitted seam events are first-class** — every transition produces a schema-validated event written to run-state, surfaced in the main-session terminal stream, and aggregated into the PR bundle's "what happened" summary.
3. **The orchestrator skill is the binding** to Claude Code's skill primitive. The portable orchestrator surface is `(orchestrator-prompt-logic + run-state.yaml schema + orchestrator-event schema + specialist envelope schema)`.
4. **`status` and `resume` commands operate on the run-state file directly** — file-driven, no live-orchestrator requirement.
5. **Loud-fail markers emitted by orchestrator decisions** (retry-budget-exhausted, escalation, hook-failed) ride the same envelope/event substrate.

This decision *does not* commit to:

- Specialist dispatch mechanism (Task tool vs. Agent Teams primitive — separate decision).
- Schema enforcement technology (ADR-003 territory).
- Repo layout (downstream of plugin-primitive stability).

#### Revisit Conditions

- **Claude Code ships first-class recursive-dispatch + bi-directional streaming for subagents** with documented stability at our supported floor. Cost/streaming axes flip; primitive choice should be re-evaluated.
- **Per-story cost on reference projects exceeds $5 ceiling** with Option A on reasonable story sizes. Investigate whether B-long-lived with recursive dispatch is cheaper.
- **Schema-asymmetry concerns surface during implementation** — i.e., enforcing envelope-output protocol at CI for the orchestrator proves materially harder than specialist envelope validation. Asymmetry is hiding a real gap; Option B earns reconsideration.
- **A credible port is proposed to a runtime that exposes a subagent primitive but no skill primitive (or vice versa).** Portability re-prioritizes; primitive binding is rebuilt for the target.
- *(added per ADR-003)* **Hook out-of-band-failure burden becomes a recurring maintenance signal.** Clusters of A.4-class failures (terminal hook failures, hook-orchestrator observation gaps) consume disproportionate harness-maintenance effort. Signal that ADR-001's Option A primitive choice should be re-evaluated against the cost of harness load it produces.

### ADR-002: Portability Boundary — Host-Runtime and Methodology Axes

**Status:** Decided.
**Date:** 2026-04-25.

#### Context

ADR-001 named the orchestrator's portable surface as `(orchestrator-prompt-logic + run-state.yaml schema + orchestrator-event schema + specialist envelope schema)` without specifying the axis on which "portable" was being claimed. Reading the PRD's portability principle (Carry-to-Architecture: "MVP is Claude Code-native, but specialist envelope schema and hook contracts are designed to be re-implementable on other primitives") and the long-term vision ("seam-discipline pattern influences how other methodology frameworks are extended into implementation") together makes the under-specification visible: the project commits to portability across **two distinct axes**, and ADR-001's portable-surface statement was implicitly host-axis-scoped only.

This ADR makes both axes explicit, classifies every architectural component on the resulting 3×3 grid, and names the host-capability requirement that any port must satisfy regardless of axis.

ADR-001 stands as written. Its claim — that the named surface is portable on the host-runtime axis — is correct. ADR-002 supplements (does not contradict) ADR-001 by adding the methodology-axis classification of the same items and clarifying that the original statement was scoped to one axis. Future readers should compose the two ADRs: ADR-001 names the host-axis surface; ADR-002 names both axes' surfaces. Retroactive editing of ADR-001 is deliberately avoided — the discovery that the original statement was one-axis-implicit is an architectural finding worth preserving in the ADR record.

#### The Two Axes

- **Host-runtime axis** — port from Claude Code to a different host runtime (Codex, Cursor, etc.) while staying in BMAD. Three positions:
  - **Portable** — copies unchanged to the new host. No host-runtime coupling.
  - **Bridge** — thin adapter rewritten for the target host's primitives. The capability described is portable; the binding to a specific host primitive is not.
  - **Bound** — provided by the host runtime; the new host provides its own equivalent (or doesn't, in which case the architecture isn't hostable there — see Portability Precondition).
- **Methodology axis** — port from BMAD to a different methodology while staying in Claude Code (or both axes, for the maximal port). Three positions:
  - **Portable** — copies unchanged to the new methodology. No methodology coupling.
  - **Methodology-Bridge** — content rewritten for the target methodology. The structural shape is portable; the methodology-specific content (state names, target skill names, taxonomy buckets) is not.
  - **Methodology-Bound** — replaced wholesale. The component exists *because* of the source methodology; in a different methodology it has no analog.

The axes are independent: a component's host-axis position does not predict its methodology-axis position. This is the load-bearing finding; the original three-tier model (host-axis only) collapsed both axes into one, hiding methodology-coupled artifacts inside what looked like a clean portable surface.

#### Component Classification — 3×3 Matrix

|  | **Methodology-Portable** | **Methodology-Bridge** | **Methodology-Bound** |
|---|---|---|---|
| **Host-Portable** | **(1) Architectural core.** Specialist envelope schema; orchestrator-event schema; run-state.yaml schema; marker taxonomy; configuration schemas (`config.yaml`, `qa-runbook.yaml`); three failure profiles (total-block / graceful-degrade / opt-in-skip); three-tier evidence hierarchy; AC-assertion-evidence triple structure; hook **purpose** descriptions; slash command **capability** descriptions; 20-lines-of-bash **principle**. | **(2)** Orchestrator prompt logic (logic ports; references to lifecycle state names, target skill names, and escalation-artifact references rebuild per methodology — but flow-policy *structure* (retry budgets, sensor-not-advisor pattern, seam-transition orchestration) is cell-1 substructure that survives the rebuild); specialist envelope **content** (shape is cell 1; semantic content per methodology is cell 2 — e.g., what `proposed_commit_message` carries); finding taxonomy (`decision_needed | patch | defer | dismiss` is BMAD's; target methodology may classify differently). | **(3)** Story-doc section read/write contract (story doc is BMAD's canonical artifact); BMAD-extension audit format; lifecycle state set (`backlog → ready-for-dev → in-progress → review → qa → done`); `qa` lifecycle state upstream proposal; `## QA Behavioral Plan` upstream proposal. |
| **Host-Bridge** | **(4)** Orchestrator skill binding (per ADR-001); hook trigger primitives (`SubagentStop` / `Stop` / `SessionStart` event names + bash-script runtime); slash command invocation primitive (`/bmad-automation X` syntax); PR bundle **rendering** (markup + assembly via Stop hook); bash **specifically** (the language; the principle is cell 1). | **(5)** Specialist wrapper **binding** — binds Claude Code subagent dispatch primitive AND the methodology-specific target skill (`bmad-dev-story`, `bmad-code-review`). The only resident of this cell. Most expensive to port: rewrites on either axis. | **(6) Empty by design discipline.** Methodology-specificity should flow through bridges as configuration, not be embedded in bridges as code. A hook firing on a methodology-specific transition like `review → qa` belongs in cell 4 (Methodology-Portable) when its transition name is read from configuration; it would only land here if the transition name were hardcoded into the bridge. A component genuinely landing in cell 6 means methodology-specificity has been embedded in code rather than expressed as configuration — a structural signal that the design has chosen the wrong abstraction layer. |
| **Host-Bound** | **(7)** Claude Code plugin install primitive; main-session reasoning loop; subagent primitive (Agent Teams, Task tool); `.claude/skills/` directory convention. | **(8) Empty by current host design.** Host runtimes today are methodology-agnostic; populating cell 8 would require a host to ship a methodology-specific primitive whose behavior is methodology-bridge per target methodology. Plausible but not currently observed. Most plausible scenario: BMAD-core upstream-absorption into Claude Code primitives. See Revisit Conditions. | **(9) Empty by current host design.** Same reasoning as cell 8, both dimensions; would require a host to ship a primitive whose existence and behavior are both methodology-bound. Most plausible scenario: a host that absorbs a methodology so deeply that the primitive itself encodes methodology-specific behavior (the upstream-absorption case taken to its limit). Currently not observed; revisitable. |

##### Architectural Core (Cell 1 — prose supplement)

The eight residents of cell 1 form the architectural core: the surface that copies unchanged to *any* compliant host running *any* compatible methodology. It deserves prose, not just a cell.

The core is what the project's long-term vision rests on. When the brief says "the layer dissolves into the methodology it extends; what remains is the architectural pattern that made it work," the architectural pattern *is* the cell-1 surface. This is also what an upstream RFC to BMAD-METHOD or any successor methodology would carry forward — the schemas, taxonomies, hierarchies, and contracts that make seam-transition orchestration with sensor-not-advisor specialists work, independent of any particular host or methodology.

Cell 1's stability is therefore an architectural commitment, not a happy outcome. Future contributors should treat changes to cell-1 components as schema-versioned, breaking-change-classified events — the same discipline applied to the specialist envelope schema in ADR-001 applies uniformly to the rest of the cell.

##### Rebuild-Cost Peak (Cell 5 — prose supplement)

Cell 5 holds a single resident — specialist wrapper binding — and is the diagonal-asymmetry residence point: the position where both axes' Bridges intersect. Components classified here rewrite on host-axis ports *and* on methodology-axis ports. Cell 5 therefore identifies the rebuild-cost peak: the most expensive component to port, regardless of which axis triggers the port. Naming it explicitly lets future port effort budget for the rewrite at planning time, rather than discovering the cost mid-port.

#### Portability Precondition (promotion candidate)

Scenario 2 (Cursor + BMAD) surfaced that not every host can host this architecture. Independent of the axes, every host runtime must provide four primitive capabilities:

1. **Prompt-loading** — some mechanism for loading orchestrator/specialist prompts into the host's reasoning context.
2. **Tool-invocation-with-return** — synchronous tool call with structured return that the orchestrator can read.
3. **Multi-step orchestration with persistent state** — the host must support a sequence of tool invocations that share state across steps (the orchestrator reads `run-state.yaml` between steps).
4. **At least one lifecycle hook for terminal-event triggering** — required for the Stop hook's PR bundle assembly. Without a terminal-event trigger, PR assembly has to land on a manual invocation, which violates the seam-transition automation the project commits to.

Hosts failing any of the four cannot host the substrate without rebuilding it; they are out-of-scope for the portability principle as the project understands it.

**Promotion candidate.** The precondition is ADR-shaped content — an architectural commitment that constrains every future host-port decision. It lives inside ADR-002 for now to avoid YAGNI cost. Promotion triggers (any one fires reconsideration): a future port surfaces a host that fails one of the four capabilities and a partial-port pattern emerges; the precondition list grows beyond five capabilities; the precondition becomes contested across contributors. Promotion route: lift the precondition into its own ADR (proposed `ADR-host-capability-requirement`), with ADR-002 retaining a pointer.

#### Decision

The portability boundary is articulated across two independent axes (host-runtime, methodology), each with three positions (Portable, Bridge / Methodology-Bridge, Bound / Methodology-Bound). Every architectural component is classified on both axes. The 3×3 matrix above is the canonical classification; future components are added by classifying them on both axes and entering them into the appropriate cell. Empty cells (6, 8, 9) carry their reasons; a future component landing in any of those cells is a structural finding requiring review.

The portable surface is restated explicitly across both axes:

- **Host-axis portable surface** (per ADR-001, restated with full population): everything in the top row of the matrix (cells 1, 2, 3) — including the architectural core, the methodology-bridge content, and the methodology-bound items, all of which are unchanged on a host-axis port.
- **Methodology-axis portable surface** (added by ADR-002): everything in the left column of the matrix (cells 1, 4, 7) — including the architectural core, the host-bridges, and the host-bound items, all of which are unchanged on a methodology-axis port.
- **Architectural core** (the intersection): cell 1 — components that port both axes simultaneously. Eight residents.

The host-port admissibility test is the four-capability precondition. Methodology ports do not have an analogous precondition at this time; if one emerges from a real methodology port, ADR-002 is revisited.

#### Rationale

- **The methodology axis is real.** Scenario 3 (Claude Code + non-BMAD methodology) demonstrated that a substantial portion of the architecture is methodology-coupled — story-doc contract, BMAD-extension audit, lifecycle state set, the upstream proposals — and must rebuild on a methodology port. Conflating these with host-runtime portability would have hidden the rebuild cost and weakened the long-term-vision commitment to methodology-port readiness.
- **The two axes are independent.** A component's host position does not predict its methodology position. The matrix's distribution (six populated cells, three empty for principled reasons) is evidence of independence; correlated axes would have clustered components on the diagonal.
- **Empty cells are findings, not gaps.** Cell 6 empty-by-discipline tells the architecture: keep methodology awareness out of the host-bridging layer; if a future component lands there, it's a smell. Cells 8 and 9 empty-by-abstraction tell the architecture: hosts must remain methodology-agnostic; if that abstraction breaks, the model needs revision.
- **The architectural core is identifiable and load-bearing.** Cell 1's eight residents are the substrate that survives both axes of port. Naming the core makes it possible to schema-version it, treat changes as breaking, and aim upstream RFCs at it.
- **Cell 5 carries known port cost.** Specialist wrapper binding is the single resident at host-Bridge / methodology-Bridge — rewrites on either axis. Identifying it explicitly lets future port effort budget for it; hiding it inside a flatter "Bridge" tier would have understated the cost. (This is the cost-asymmetry note Q1 asked for, landed in the matrix rather than as a separate sub-tier.)
- **The precondition is separate from the axes.** A host that fails the four-capability requirement isn't somewhere on the host-axis spectrum; it's outside the architecture's reach. Calling this out as a precondition prevents the model from being stretched to cover hosts it shouldn't cover.
- **ADR-001 stands; ADR-002 supplements.** The default project pattern: *later ADRs refine earlier ADRs by extension when the earlier ADR's flaw is omission (incomplete-but-true).* ADR-001's flaw was omission — host-axis-correct, methodology-axis-silent — so supplement-don't-contradict is the right response. ADRs found to contain genuine **errors** (incorrect rationale, not just incompleteness) get a different response: they are edited in place with a visible "corrected:" marker, or formally superseded by a follow-up ADR with explicit deprecation. Conflating omission and error would either erase design history (treating omissions as errors) or preserve incorrect reasoning (treating errors as omissions); both fail differently and need to be distinguished.

#### Consequences

This decision commits the architecture to:

1. **Two-axis classification is the canonical portability vocabulary.** New components are classified on both axes at introduction; the BMAD-extension audit document (per FR65) records the classification alongside the convention itself.
2. **Cell 1 (architectural core) is schema-versioned.** Changes to cell-1 components are major-version events — the same discipline ADR-001 applied to the specialist envelope schema applies to all of cell 1.
3. **Cell 5 (specialist wrapper binding) carries known port cost.** Future host or methodology ports budget for this component's rewrite explicitly; it is not a "Bridge — thin" item.
4. **Empty cells are checked, not assumed.** When a new component is classified, if it lands in cell 6, 8, or 9, it triggers structural review (smell or abstraction-break, per the cell's reason).
5. **The portability precondition is the host-port admissibility test.** Before committing to a host-axis port, the host is checked against the four capabilities; failure halts the port-discussion at the precondition, not at the axes.
6. **PR bundle UX divergence stays cosmetic.** PR bundle rendering is host-Bridge (cell 4); the structural contract (cell 1) is rich enough that two hosts implementing the same structural contract produce semantically identical PR bundles, even when the markup differs slightly. UX divergence per host is acceptable as long as it remains cosmetic.
7. **20-lines-of-bash is decomposed.** The principle is cell 1 (double-portable); bash specifically is cell 4 (host-Bridge). On a non-bash host, the principle ports as "thin host-trigger layer with deterministic-only constraint, sized so it cannot grow into judgment-bearing logic" — calibrated to the target language's natural unit of complexity rather than re-using the literal 20-line count.
8. **ADR-001 stands; ADR composition pattern is supplement-for-omission, edit-or-supersede-for-error.** ADR-001's flaw was omission, so it stands unchanged with ADR-002 supplementing. Future ADRs found to contain genuine errors are edited in place (with a visible "corrected:" marker) or superseded by follow-up ADRs with explicit deprecation. Read together, ADR-001 and ADR-002 specify the project's portability boundary; in isolation, ADR-001 specifies one axis.
9. **The precondition is a promotion candidate.** If precondition-related complexity surfaces (per the trigger conditions named in the Precondition section), ADR-002's precondition block is promoted to its own ADR.

#### Revisit Conditions

- **A port surfaces a substantial mis-classification** — a component classified Portable on an axis turns out to require rewrite on that axis, or a component classified Bridge turns out to be Bound (or vice versa). The matrix is updated; the discrepancy is named in a follow-up ADR.
- **A host fails the portability precondition** but the project commits to the port anyway. The four-capability requirement is wrong; ADR-002's precondition is revised, possibly via promotion to its own ADR.
- **A new cell becomes populated.** A future component lands in cell 6, 8, or 9. The cell's empty reason is re-examined; either the reason was wrong (the model is updated) or the new component is in the wrong place (the component's classification is revisited).
- **Methodology coupling proves deeper than `(state-name rewrite + target-skill rewrite)`.** Scenario 3's methodology bridge predicted that orchestrator prompt logic ports as logic + state-name-substitution. If a real methodology port surfaces deeper coupling — methodology-specific control flow, methodology-specific event semantics — the methodology-axis tiering needs revision (e.g., a fourth methodology-axis position for "structurally re-shaped per methodology").
- **A component crosses cells over time.** A component classified Portable on both axes drifts into Methodology-Bridge as its content takes on methodology-specific references. The drift is detected via the BMAD-extension audit's classification consistency check; if drift is systematic, the architecture re-examines whether cell-1 stability is real or aspirational.
- **A host ships methodology-specific primitives.** Most plausible scenario: BMAD-core upstream-absorption into Claude Code primitives. Cells 8 and 9 populate; the architecture's binding to those primitives is rebuilt; cell-1 components stay stable, but the matrix's overall classification is updated to reflect the new host shape. This is also a strong promotion-trigger candidate for the precondition (since absorption changes which capabilities a host's primitives provide methodology-specifically vs. methodology-agnostically).

**Matrix-completeness clarification.** The matrix populates components known at ADR-002's writing. New components introduced by subsequent ADRs and SDNs (e.g., `cost-event` class via ADR-006, `dependencies.yaml` via SDN-001, OTel metric/attribute names via ADR-006) are classified per the two-axis model and recorded in their introducing artifact's Consequences — not retroactively in this matrix. The matrix is **prescriptive** (it tells you how to classify) but not **exhaustive** (it doesn't enumerate every component that ever exists). This convention preserves the supplement-by-extension discipline and avoids ADR-002 becoming a registry that must be touched on every new artifact.

### ADR-003: Schema Enforcement and Loud-Fail Harness Reconciliation

**Status:** Decided.
**Date:** 2026-04-25.

#### Context

The PRD names two CI-enforced invariants whose enforcement the architecture has not yet specified: sensor-not-advisor schema validation on specialist envelopes (FR53) and loud-fail marker completeness via harness reconciliation (FR33). Both are first-class engineering work — explicitly *not* lint rules per Success Criteria → Technical Success — and both run in CI. The natural design question: do they share a substrate, and how does the substrate handle the harder half?

The two halves have asymmetric difficulty:

- **Schema enforcement** is well-trodden. JSON Schema or equivalent validators run in CI; envelopes containing forbidden fields (`next_action`, `recommendation`, anything implying flow policy) fail validation. The choice is mostly tooling — language and library — not architecture.
- **Harness reconciliation** is the design problem. FR33 requires the harness to detect skip events on reference-project runs *independently* of the marker system, then reconcile detected skips against emitted markers. If the harness derives "what skipped" from "what markers were emitted," the check is tautological (`markers == markers` always passes). Real reconciliation requires an independent skip-event source. The design question: what *is* the independent source, and is it complete-by-construction under blocking commitment?

**Commitment level — PRD-ratified blocking, not best-effort.** FR33 says "any skip event detected by the harness on reference-project runs that does not emit a corresponding PR-bundle marker fails CI." NFR Loud-Fail Marker Completeness specifies "100% of detected skips produce PR-bundle marker." Success Criteria → Technical Success enumerates loud-fail marker completeness as a CI-enforced invariant. ADR-003 ratifies blocking commitment explicitly: best-effort is not on the table. This reshapes the option-space evaluation — primary skip-event sources must be complete-by-construction over the *known* skip-class set, not best-on-average across options.

**Relationship to FR65 (BMAD-extension audit).** FR65 specifies the audit doc's existence and convention-classification scope. ADR-003 elaborates the operational workflow for one specific class of audit additions — skip-class recognition. This is architectural elaboration of FR65's existing scope, not PRD drift; the audit doc gains a skip-class-recognition subsection, not a new responsibility surface.

**Cross-reference to ADR-001.** ADR-001's Option A (orchestrator as skill in main session) makes hooks out-of-band of the orchestrator's reasoning loop. The orchestrator cannot directly observe hook failures except via post-hoc state reads. This is a structural property of ADR-001, not a flaw — and it's the property that gives Layer B (runtime-state inspection) its primary purpose. ADR-003 acknowledges the coupling and flags ADR-001 for a follow-up revisit-condition addition (see Consequences).

#### The Independent Skip-Event Source — Three Layers

The architecture commits to **three layers of skip-event detection**, each layer bounded structurally differently. Each layer catches what the layers above it cannot — not by redundancy, but because each layer's bound has a different shape.

- **Layer A — Orchestrator-events.** Every orchestrator decision point that involves a skip emits a schema-validated event recorded in run-state. The harness reads run-state's event log + PR-bundle markers; reconciles "for every skip-class event in log, is there a matching marker in bundle?" Reuses ADR-001's `orchestrator-event.yaml` (cell-1 architectural-core artifact per ADR-002). Non-tautological — events emit at orchestrator decision time, markers emit at PR-bundle assembly time, different code paths and temporal sources.
- **Layer B — Runtime-state inspection.** The harness inspects post-run state (file presence, dependency availability, hook exit codes recorded in run-state, env state, git branch state) and independently infers what *should have* skipped. Encodes skip-detection logic separately from the orchestrator's awareness.
- **Layer C — Reference-project run fixtures + synthetic stories.** Each reference project carries an expected skip-profile; the harness compares actual markers against the fixture's expected profile. Synthetic test stories in `examples/` (per FR Reference Artifacts) trigger skip-classes that real reference projects don't naturally exercise.

**Each layer's structural bound:**

- **Layer A** is bounded by what the orchestrator is *aware of*. Cannot catch skips at decision points the schema doesn't recognize, nor skips that happen below the orchestrator's reasoning loop (hook failures, specialist process crashes, mid-decision crashes).
- **Layer B** is bounded by what *manifests as observable runtime state*. Cannot catch skips that leave no state divergence (heuristic skipped because AC didn't trigger it, semantic verification not configured, internal heuristic timeout).
- **Layer C** is bounded by *what's been pinned as a regression scenario*. Cannot catch novel skip-class combinations beyond fixture coverage, nor skip-classes recognized too recently to have fixtures yet.

The three layers' bounds are structurally different. A's bound is "orchestrator awareness." B's bound is "state observability." C's bound is "fixture coverage." Gaps in one layer don't cascade into another's because the bounds don't overlap in shape — A's residuals are in B's bound; B's residuals are in A's or C's bound; C's residuals are partially in A's and B's bounds. Defense-in-depth holds.

**Defense-in-depth framing scoped locally.** This framing is descriptive of *this* harness, where the layers genuinely have different structural bounds. ADR-003 does not promote defense-in-depth as a project-level discipline; the framing is local to the harness-reconciliation design.

#### Failure Mode Analysis (load-bearing findings)

The full FMA is captured in the architectural-elicitation transcript; the load-bearing findings:

- **Layer A's mitigations** are two CI checks beyond envelope/event schema validation:
  - **Enumeration-equivalence reconciliation** between `marker-taxonomy.yaml` and `orchestrator-event.yaml` — every skip-class in one must exist in the other (closes "skip-class added without emission slot" gap).
  - Schema validation requires non-empty skip-class field on skip-emission events.
- **Layer A's residuals** route to:
  - **B** — terminal hook failures, mid-decision crash + resume bugs, timeout-firing logic broken.
  - **C** — wrong-class assignment (logic bug emitting `mobile-blocked` when it should be `Tier-3-not-configured`), prompt drift dropping emission instructions.
- **Layer B is bounded coverage by construction** — never primary, only gap-filler. Catches what manifests as state divergence (hook out-of-band failures, specialist crashes that bypass orchestrator awareness, run-state seam-incomplete signatures).
- **Layer C is regression pinning + orchestrator-internal-drift backstop.** Beyond pinning known scenarios, C catches A's silent failure modes B cannot see (wrong-class assignment, prompt drift). Requires a CI **fixture-coverage check** — every skip-class in `marker-taxonomy.yaml` has ≥1 fixture covering it.
- **One structural hole survives all three layers — unknown-unknown skip-classes** (skips no one has yet recognized as skip-classes). Routed out of harness to FR65's BMAD-extension audit (review-enforced) — not to a hypothetical fourth layer.

#### Decision

**Three-layer defense-in-depth (A + B + C) with explicit roles, blocking commitment over the known skip-class set, unknown-unknown skip-classes routed to FR65's audit, and a single CI substrate housing both schema enforcement and harness reconciliation.**

**Layer roles:**

- **A — primary.** Orchestrator-events as primary skip-event source. Complete-by-construction at the orchestrator level given enumeration-equivalence between marker-taxonomy and event-schema.
- **B — below-orchestrator gap-filler.** Catches hook out-of-band failures, specialist process crashes, mid-decision crash + resume bugs, terminal hook failures.
- **C — regression pinning + orchestrator-internal-drift backstop.** Catches wrong-class assignment, prompt drift silently dropping emission, novel-but-pinned regression scenarios.

**Substrate composition (five components):**

1. Specialist envelope schema validation
2. Orchestrator-event schema validation
3. Skip-event-to-marker reconciliation
4. Marker-taxonomy ↔ event-schema enumeration-equivalence reconciliation
5. Marker-taxonomy ↔ fixture-coverage enumeration

(1) and (2) are the easy half — schema validation. (3) is the load-bearing reconciliation logic (Layer A's primary mechanism). (4) is the consistency invariant on cell-1 artifacts that makes Layer A complete-by-construction. (5) is the consistency invariant on Layer C's coverage.

**Substrate language:** Python is the default starting choice — Pydantic + jsonschema cover schema validation cleanly; reconciliation logic is non-trivial and Python's ergonomics suit it; BMAD core is methodology-agnostic about language. TypeScript is a viable alternative if MCP-future considerations dominate. Language is the most easily-revised piece of this decision; not over-specified in the ADR by design.

**Unknown-unknown skip-classes routing:**

The harness is CI-enforced over the *known* skip-class set. Skip-classes newly recognized after MVP enter the harness via the BMAD-extension audit (FR65) workflow — an explicit, review-enforced step. The audit doc gains a skip-class-recognition subsection committing to the workflow:

```
newly recognized skip-class →
  add to marker-taxonomy.yaml →
  add to orchestrator-event.yaml →
  add fixture / synthetic story →
  re-run CI checks (3), (4), (5) →
  merge
```

This is the **CI-vs-review split for the harness**: Layers A/B/C and the five substrate components are CI-enforced; skip-class recognition is review-enforced. The harness completeness invariant is over the known skip-class set under CI; the unknown-unknown layer is review-enforced via audit. Pretending CI could catch unknown-unknowns would be the silent-degradation failure mode the loud-fail doctrine exists to prevent — the harness's structural limit is named honestly, not papered over.

#### Rationale

- **Three layers, not one or two.** FMA demonstrated no single source is complete-by-construction over the full skip-class space, and that A's residuals fall into structurally different categories. A's "terminal hook failure" residual (caught by B) and A's "wrong-class assignment" residual (caught by C) cannot share a layer — they have different observability shapes (state divergence vs. coded-but-incorrect emission). Compressing them would hide the shape difference and weaken the defense.
- **Blocking commitment is PRD-ratified.** FR33, NFR loud-fail completeness, and Technical Success criteria all specify blocking. ADR-003 ratifies what the PRD already committed to and uses blocking as the evaluation frame. Best-effort over conceivable skip-classes would be unenforceable; blocking over the *known* skip-class set is enforceable.
- **Defense-in-depth here, not project-wide.** The framing is descriptive: A, B, and C have genuinely different structural bounds. Promoting defense-in-depth as a project-level discipline would create pressure toward "we should add a fourth layer for completeness" or "every architectural component should be three-layered" — over-formalization the framing wasn't designed to bear. Local to this harness only.
- **C's expanded role is honest.** "Regression pinning, not gap-filling" is correct *for the orchestrator-vs-below-orchestrator axis* but undercounts C's role as backstop for orchestrator-internal failures (prompt drift, wrong-class assignment) that B's state-observability bound cannot see. Reframing C as both regression pinning *and* orchestrator-internal-drift backstop is a finding from FMA, not redefinition.
- **Unknown-unknown route-out is the loud-fail doctrine applied to the harness's own architecture.** The structural limit (no source is complete over conceivable skip-classes) is acknowledged explicitly and routed to a review-enforced mechanism, rather than hidden behind a fourth-layer-that-wouldn't-work. The CI-vs-review split is the operationalization of "honest about enforcement mechanism" — same discipline applied to the 9-invariant split in Success Criteria.
- **Co-versioning of marker-taxonomy and orchestrator-event-schema makes Layer A complete-by-construction.** Both are cell-1 architectural-core artifacts (per ADR-002). Treating them as co-versioned isn't process overhead — it's an architectural commitment that prevents the most plausible Layer A failure mode.
- **FR65 elaboration, not PRD drift.** FR65 specifies the audit's existence and convention-classification scope. Skip-class recognition is a class of convention; the recognition workflow is the *how* of conventions getting added. ADR-003 elaborates the workflow without expanding FR65's responsibility surface.
- **Substrate language under-specified deliberately.** Schema validation is well-trodden in any modern language; reconciliation is logic where Python's ergonomics suit but isn't load-bearing on language. Locking the language at architecture time would over-specify or constrain implementation prematurely. Naming Python as starting choice + TS as alternative + "easily revised" framing is the right discipline.
- **Hook out-of-band-ness is downstream of ADR-001 Option A.** The structural property that hooks run outside the orchestrator's reasoning loop creates the recurring gap Layer B exists to close. ADR-003 acknowledges the coupling and flags ADR-001 for a follow-up revisit-condition addition — keeping cross-ADR coupling visible without retroactive editing in this fork.

#### Consequences

This decision commits the architecture to:

1. **Five-component CI substrate** for schema enforcement + harness reconciliation:
   - Specialist envelope schema validator
   - Orchestrator-event schema validator
   - Skip-event-to-marker reconciler (Layer A's primary mechanism)
   - Marker-taxonomy ↔ event-schema enumeration-equivalence checker (Layer A's completeness mitigation) *(extended per SDN-001: substrate component 4's enumeration-equivalence check now covers a third reconciliation pair — `marker-taxonomy.yaml ↔ dependencies.yaml` — with component count staying at five and the consumer set growing to two.)*
   - Marker-taxonomy ↔ fixture-coverage enumerator (Layer C's completeness mitigation)
2. **Co-versioning of `marker-taxonomy.yaml` and `orchestrator-event.yaml` — local exception, not generalized cell-1 model.** These two cell-1 components are co-versioned because the harness's enumeration-equivalence check (substrate component 4) requires consistency between them; schema-version bumps on either trigger reconciliation review. **This coupling is local to the harness's substrate; it does not generalize to all cell-1 components.** Other cell-1 components (run-state schema, specialist envelope schema) remain independently versioned per ADR-002, because no runtime invariant requires their cross-component consistency. If a future component introduces a similar runtime invariant tying it to another cell-1 schema, the same justification pattern (named runtime invariant requiring cross-component consistency) is reused; absent such an invariant, the marker/event coupling stays the only exception. ADR-002's per-component versioning remains the cell-1 default.
3. **Audit doc gains a skip-class-recognition workflow subsection.** Concrete deliverable, MVP-scope. Specifies the workflow (recognize → add to taxonomy → add to event-schema → add fixture → re-run CI checks → merge) and names skip-class recognition as a review-enforced convention-addition class within FR65's scope.
4. **CI-vs-review split for harness completeness is explicit.** Layers A/B/C and substrate components 1–5 are CI-enforced. Skip-class recognition is review-enforced. **The 5/4 invariant count in the PRD (Success Criteria → Technical Success) is canonical; ADR-003's 6/5 reflects elaboration of FR33 and FR65 into harness-specific sub-invariants, not addition to the canonical count.** Harness completeness over known skip-classes elaborates FR33 (CI-enforced); skip-class recognition elaborates FR65 (review-enforced). Future readers comparing PRD invariants to architecture should treat ADR-003's enumeration as sub-items of the canonical 5/4, not as new invariants. Promoting these to canonical-count items would require a PRD edit, which is out of scope for ADR-003.
5. **Synthetic test stories live in `examples/`** per FR Reference Artifacts and are required to cover every skip-class in the marker taxonomy (Layer C's completeness mitigation). Adding a skip-class without a synthetic story fails CI.
6. **Hook out-of-band-ness is acknowledged as structural to ADR-001 Option A** and is the gap Layer B closes. ADR-003 flags ADR-001 for a follow-up revisit-condition addition: *"Hook out-of-band-failure burden becomes a recurring maintenance signal — clusters of A.4-class failures (terminal hook failures, hook-orchestrator observation gaps) consume disproportionate harness-maintenance effort."* This addition is scheduled to happen as a supplement-by-extension to ADR-001 (per ADR-002's omission-vs-error framing — the addition is a new finding, not a correction). It is not retroactively edited into ADR-001 in this fork; the flag here documents the cross-ADR coupling and the planned edit.
7. **Defense-in-depth framing is scoped to this harness.** Project-level discipline is not implied. Future harnesses or enforcement mechanisms classify their layering needs from their own structural-bound analysis, not by analogy to ADR-003.
8. **Substrate language is Python (starting choice).** TypeScript is a documented alternative for MCP-future scenarios. Language change is a minor-version revision, not a major-version event — the substrate's contracts (the five components and their inputs/outputs) are what the architecture commits to, not the language hosting them.
9. **Unknown-unknown skip-classes are an explicit out-of-CI residual** routed to review via FR65. This is the loud-fail doctrine applied to the harness's own architecture — the structural limit is named, not hidden.

#### Revisit Conditions

- **Unknown-unknown rate elevates** — newly recognized skip-classes accumulate faster than the audit can process them, or skip-classes are recognized only after they've caused production-merge regressions. The review-enforced layer is failing; ADR-003's CI-vs-review split needs revision (e.g., promote some recognition-detection patterns to CI).
- **Hook-out-of-band-burden signal flows back to ADR-001.** A.4-class failures cluster as a recurring maintenance burden; ADR-001's revisit-condition addition (per Consequence 6) fires; ADR-001's Option A primitive choice is re-evaluated against the cost of harness load it produces.
- **Layer A's mitigations don't hold.** Co-versioning of marker-taxonomy and event-schema proves harder to maintain than predicted (e.g., contributors regularly add to one without the other despite CI checks); enumeration-equivalence becomes a contention point. Layer A's completeness-by-construction claim weakens; revisit whether Layer A primary status is justified.
- **Layer B's coverage assumption is wrong.** State divergence patterns surface that B's runtime-state inspection cannot observe (e.g., hook failures leaving no observable git or filesystem trace). B's bound is wider than predicted; either B's inspection logic needs expanding or another mechanism (not in the current model) is needed.
- **Layer C's fixture maintenance burden exceeds capacity.** Maintaining synthetic stories per skip-class proves ergonomically expensive; fixture drift accumulates faster than C's versioning catches. Revisit whether C's role as orchestrator-internal-drift backstop should be replaced by a CI-enforced mechanism, narrowing C to pure regression pinning.
- **Substrate language proves wrong.** Python ergonomics fail for the reconciliation logic, or TypeScript becomes more aligned with future MCP integrations. Language migration is a minor-version revision; revisit when ergonomics or downstream integrations require it.
- **The unknown-unknown route-out doesn't operationalize.** The audit doc's skip-class-recognition workflow exists on paper but isn't actually used (skip-classes still get recognized in code reviews without going through the workflow). The workflow needs revision to match how recognition actually happens, or its review-enforced status needs strengthening (e.g., a CI check blocking merges that add skip-classes without audit-doc updates).

### ADR-004: Specialist Dispatch Mechanism

**Status:** Decided.
**Date:** 2026-04-25.

#### Context

ADR-001 placed the orchestrator as a skill in the main Claude Code session and committed to envelope-shaped output protocol enforcement. It deferred *how* the orchestrator invokes specialist subagents (Dev, Review-BMAD, QA, and Phase 1.5 Review-LAD) — the dispatch mechanism. ADR-005 made this deferral concrete by naming `specialist-crash-mid-execution` as a marker class whose detection mechanism is ADR-004's responsibility. ADR-004 picks the dispatch primitive and commits to the detection mechanism.

**Primitive landscape — verification finding (April 2026).** The brainstorm session (2026-04-24) and the PRD's Runtime Compatibility Matrix both reference **"Agent Teams (v2.1.32+)"** as the multi-agent primitive informing the MVP version floor. Verification searches against current Anthropic documentation surface a different landscape: **Task tool is the canonical multi-agent dispatch primitive in Claude Code today**, with OpenTelemetry instrumentation built into the Claude Code platform layer (subagent spans nest under parent `claude_code.tool` spans; token counts, cost, and timing exposed as OTel metrics and traces). **"Agent Teams" does not appear as a distinct primitive name in current Anthropic docs.** The primitive landscape evolved between brainstorm research (late 2025) and architecture verification (April 2026); whether "Agent Teams" was renamed, subsumed into Task tool's capabilities, or never canonical externally is unclear from verification alone.

**Documentation drift signal (non-blocking for ADR-004).** The PRD's Runtime Compatibility Matrix names "v2.1.32+ (Agent Teams primitive)" under Claude Code dependency. ADR-004's verification finding indicates this entry should be updated to reflect the current canonical primitive (Task tool) when convenient. This is a separate documentation-drift task — not blocking for ADR-004 — and should be tracked alongside FR43-style version-tolerance hygiene. The PRD's framing was honest for its research date; the current architecture surfaces the divergence rather than absorbing it silently.

#### Option Space

The five-requirement evaluation framework (from fork-elicitation):

| # | Requirement | Source |
|---|---|---|
| 1 | Structured-input dispatch | ADR-001 + FR1–FR7 |
| 2 | Structured-output return (envelope-validatable) | ADR-003 + FR51 |
| 3 | Specialist-crash detection | ADR-005 marker `specialist-crash-mid-execution` |
| 4 | Timeout enforcement | NFR-P2 (default 15min/specialist) |
| 5 | Cost-telemetry exposure | Carry-forward to ADR-006 |

**Options considered post-verification:**

- **Task tool — in-session canonical primitive.** Multi-agent coordination via parent-spawned subagents; structured input via prompt; return text parsed against envelope schema; OTel spans nested under parent `claude_code.tool` span.
- **Agent SDK (programmatic harness).** Runs Claude Code CLI as a child process; provides Python and TypeScript bindings. **Rejected** — incompatible with ADR-001's orchestrator-as-skill choice. The orchestrator lives *inside* a Claude Code session; the SDK is for invoking Claude Code from *outside*. Architecture mismatch.
- **"Agent Teams" — brainstorm-era framing.** Does not appear as a distinct primitive in current docs. Either subsumed into Task tool or never canonical externally. **Not a viable evaluation candidate** post-verification.

**Hybrid is dead-letter** — there is only one viable in-session primitive (Task tool); nothing to hybridize with.

**Option space collapsed.** Task tool is the only viable primitive for the orchestrator-as-skill architecture. The decision is mechanical given ADR-001's prior commitment.

#### Decision

**Task tool with orchestrator-implemented dispatch coordination.**

- **Sequential dispatch per seam.** Dev → Review-BMAD → QA per seam-transition orchestration (ADR-001). Pluggability invariant (ADR-002 cell 1 / no-cross-references) prevents specialist-to-specialist parallelism; the orchestrator dispatches one specialist per seam transition.
- **Dispatch-time crash detection (three sub-causes for `specialist-crash-mid-execution` marker):**
  1. **`tool-level-error`** — Task tool's own dispatch failed (subagent process crash, primitive-level error). Detection: Task tool returns error rather than agent output.
  2. **`silent-corruption`** — specialist returned text but the text doesn't parse to envelope or fails schema validation per ADR-003. Detection: orchestrator's envelope-parse step (substrate component 1) fails.
  3. **`timeout-exceeded`** — wall-clock budget exhausted (NFR-P2's 15-min default, configurable per specialist via `_bmad/automation/config.yaml`). Detection: orchestrator wraps each Task tool dispatch with a wall-clock timer; cancels and emits if exceeded. Task tool itself does not expose native per-call timeout that orchestrator can rely on.
- **Cost-telemetry exposure: native via Claude Code's OpenTelemetry instrumentation** (`claude_code.interaction` / `claude_code.llm_request` / `claude_code.tool` spans; subagent spans nested under parent tool span; token-count and cost metrics emitted as OTel signals). ADR-004 commits to *exposure availability*; ADR-006 will choose the consumption path (OTel direct, orchestrator-owned counters, or hybrid).

#### Cross-Coupling to ADR-005

ADR-005's `specialist-crash-mid-execution` marker class accommodates two detection paths:

- **Dispatch-time detection (ADR-004's territory).** Three sub-causes committed in ADR-004 above (`tool-level-error`, `silent-corruption`, `timeout-exceeded`).
- **Recovery-time detection (ADR-005's territory).** ADR-005's recovery algorithm may surface additional sub-causes when SessionStart resume detects "specialist dispatched but no return event" patterns. ADR-004 does not pre-name these — they belong to ADR-005's recovery scope. If recovery-time `specialist-crash-mid-execution` detection surfaces as a thing ADR-005 needs to elaborate, that's a future ADR-005 supplement-by-extension or emergence-driven addition.

The marker class supports both detection paths; the sub-field `cause` distinguishes which path detected the crash. ADR-004 owns dispatch-time cause values; ADR-005 owns recovery-time cause values.

#### Carry-Forward to ADR-006

ADR-004 surfaces what the dispatch primitive *exposes* for cost-accounting; ADR-006 will choose the consumption path:

- **OTel availability.** Claude Code's platform-layer OpenTelemetry exports include token counts (input/output, by model), cost counters, and span hierarchy with subagent nesting. Configurable via `CLAUDE_CODE_ENABLE_TELEMETRY=1` + OTLP exporter env vars.
- **Span hierarchy for per-subagent attribution.** Subagent invocations via Task tool produce nested spans (`claude_code.llm_request` and `claude_code.tool` under parent's `claude_code.tool` span), making per-specialist cost attribution structurally available.
- **Per-retry breakdown — TBD by ADR-006's verification.** Whether OTel's span-level instrumentation supports per-retry distinction (e.g., spans tagged with retry-attempt number, separate trace IDs per retry) requires verification in ADR-006's prep step. If OTel is insufficient for per-retry resolution, orchestrator-owned counters become the primary path; if sufficient, OTel direct consumption is viable.

ADR-004 does not constrain ADR-006's choice. The exposure surface is documented; the consumption decision is open.

#### Rationale

- **The verified primitive landscape leaves no alternative for in-session dispatch.** Task tool is the canonical multi-agent primitive in Claude Code; the Agent SDK doesn't compose with the orchestrator-as-skill architecture (ADR-001); "Agent Teams" framing didn't survive verification. Option space collapsed; decision is mechanical.
- **The brainstorm/PRD's primitive reference reflected an earlier landscape.** Surfacing the divergence in Context (rather than silently substituting Task tool) preserves design history and flags the documentation-drift signal for separate resolution. Aligns with ADR-002's omission-vs-error pattern: the PRD's reference is omission (incomplete-as-of-verification-date), not error.
- **Three dispatch-time sub-causes are operationally distinct.** Each maps to a different remediation path: `tool-level-error` suggests retry or platform-issue escalation; `silent-corruption` suggests prompt or schema-drift investigation; `timeout-exceeded` suggests context-size or environmental analysis. Collapsing them would lose remediation signal.
- **OTel as cost-telemetry surface aligns with the platform's commitments.** Claude Code's observability is OpenTelemetry-native; building cost-accounting on OTel composes with the platform's own instrumentation choices rather than fighting them. Whether to consume directly or via orchestrator-owned aggregation is ADR-006's choice; ADR-004 commits only to availability.
- **Sequential dispatch is forced by the pluggability invariant.** Specialists cannot reference each other (ADR-002 cell-1 invariant); cross-specialist parallelism would require cross-references or shared state. Per-seam sequential dispatch is the only shape that preserves pluggability.

#### Consequences

This decision commits the architecture to:

1. **Task tool's prompt format is the dispatch contract surface.** Each specialist invocation includes structured prompt content (story-id, retry context, scope-lock on retries, per-specialist instruction). Envelope schema is the return contract per ADR-003.
2. **Orchestrator owns timeout enforcement.** Wall-clock timeout wraps each Task tool dispatch; cancels the dispatch if exceeded; emits `specialist-crash-mid-execution: timeout-exceeded`. Default 15 min per NFR-P2; per-specialist override via config.yaml.
3. **OTel configuration becomes part of the orchestrator's runtime setup.** `CLAUDE_CODE_ENABLE_TELEMETRY=1` + OTLP exporter env vars are part of the operator-facing setup if ADR-006 chooses OTel-direct consumption. Implementation detail at runtime; configured in `_bmad/automation/config.yaml` or via init-time scaffolding.
4. **`specialist-crash-mid-execution` marker carries `cause` sub-field with three dispatch-time values** (`tool-level-error`, `silent-corruption`, `timeout-exceeded`). Per ADR-003's enumeration-equivalence reconciliation requirement, these are added to `marker-taxonomy.yaml` and `orchestrator-event.yaml`. Synthetic test stories must cover each sub-cause.
5. **PRD Runtime Compatibility Matrix update is queued as a separate documentation task.** Non-blocking for ADR-004; the matrix entry "v2.1.32+ (Agent Teams primitive)" should update to reflect Task tool as the canonical primitive when convenient. Future readers comparing PRD to ADR-004 see the divergence acknowledged in ADR-004's Context.
6. **Task tool's return-text-only shape is acceptable for envelope handling.** Envelopes are YAML or JSON parseable from text; binary or structured return is not required. If a future specialist requires non-text return (binary artifacts, large file handles), the dispatch contract evolves — see Revisit Conditions.
7. **Per-retry cost-attribution detail is ADR-006's verification surface.** ADR-004 commits OTel exposure; ADR-006 verifies whether OTel's span-level instrumentation supports per-retry resolution and chooses consumption path accordingly.

#### Revisit Conditions

- **Anthropic ships a new primitive that supersedes Task tool** for multi-agent dispatch. The primitive landscape evolves again; ADR-004 revisits the dispatch choice.
- **OTel instrumentation changes shape in Claude Code.** Span names, attributes, or hierarchy change — coordinate with ADR-006's consumption path.
- **Agent SDK becomes viable for in-session orchestration.** Currently rejected because the SDK runs Claude Code as a child process (incompatible with orchestrator-as-skill); if a future SDK variant supports in-session use, hybrid host model may earn re-evaluation.
- **Task tool's return-text-only shape proves insufficient.** A specialist requires non-text return (binary artifacts, structured handles, streaming output); dispatch contract needs to support richer return types. ADR-004 revisits.
- **"Agent Teams" returns as a distinct primitive.** Anthropic ships a primitive under that name (or an evolved equivalent) with capabilities that materially exceed Task tool's. The verification finding's basis dissolves; ADR-004 revisits.
- **Wall-clock-timeout enforcement at the orchestrator layer proves unreliable.** Edge cases surface where the orchestrator can't reliably cancel a long-running Task tool dispatch (process management gaps, primitive-level lifecycle issues). May require migrating timeout enforcement to a deeper layer or accepting reduced timeout reliability.

### ADR-005: Cross-State Consistency Protocol

**Status:** Decided.
**Date:** 2026-04-25.

#### Context

The PRD's NFR-R8 names the cross-state consistency policy: story-doc canonical, run-state cache, story-doc writes complete before run-state advance, recovery on disagreement uses story-doc as source of truth. ADR-005 operationalizes this — specifying the recovery algorithm, the canonicality model, and the write-ordering protocol.

**Three factual resolutions land in Context before option analysis (verifying assumptions surfaced during fork elicitation):**

1. **Multi-writer is real, not collapsible.** Specialists (Dev, Review-BMAD, QA) write story-doc sections directly during their own execution — `bmad-dev-story` writes `## Dev Agent Record`; `bmad-code-review` writes `## Senior Developer Review (AI)` and `## Review Findings`; QA writes `## QA Behavioral Plan` (per FR23). The Automator's wrappers invoke these BMAD-core skills and observe returns; they do *not* buffer-and-write-through-orchestrator. Buffering would override BMAD-core's existing behavior and violate BMAD-extension discipline. **Conclusion: story-doc has multiple writers (one per specialist subagent); the orchestrator is not among them.**
2. **The orchestrator is a pure run-state writer plus sprint-status writer (for non-BMAD-native transitions); never a story-doc writer.** FR23's `## QA Behavioral Plan` is QA's write, not the orchestrator's. The orchestrator emits orchestrator-events to its own event log and updates run-state.yaml; for the new `qa` lifecycle state (per upstream proposal 1, since BMAD-core's existing skills don't cover the `review → qa` transition), the orchestrator writes sprint-status.yaml. **Conclusion: clean separation of writers — specialists own story-doc, orchestrator owns run-state and the `qa` sprint-status transition; BMAD-core skills own the rest of sprint-status.**
3. **Sprint-status.yaml is a third state store, not just a derived projection.** BMAD-core skills (bmad-dev-story step 4, bmad-code-review step 6) write sprint-status during their normal flow; the orchestrator writes it for non-BMAD-native transitions. NFR-R8's "story-doc canonical, run-state cache" framing was implicitly two-store; sprint-status enters as a third store with its own canonicality. **Conclusion: cross-state consistency is a three-store problem, not two-store.**

These resolutions reshape the option space into three composing sub-decisions: **(a) recovery sources** (which stores does recovery consume, at what tier), **(b) canonicality model** (when stores disagree on recovery, who wins), **(c) recovery algorithm** (how does the orchestrator handle each crash class).

#### Sub-decision (a) — Recovery Sources

| Source | Role |
|---|---|
| `story-doc` | BMAD-domain canonical for specialist outputs; multi-writer (specialists). |
| `sprint-status.yaml` | BMAD-domain canonical for lifecycle state name; multi-writer (BMAD-core skills + orchestrator for `qa` transition). |
| `run-state.yaml` | Orchestrator-domain canonical for flow control (cache; reconstructable from other sources). |
| Orchestrator-event log | Audit trail; primary for state recovery if available; reconstructable cache otherwise. Reuses ADR-003's cell-1 artifact. |
| Git state | **Diagnostic probe only** — not a recovery source; commit-verification probe. |

#### Sub-decision (b) — Canonicality Model

Three readings considered:

- **Reading 1 — pure multi-domain canonicality.** Each store canonical in its own domain; no tiebreak on disagreement. **Rejected** — Scenario 7 (sprint-status disagrees with story-doc-implied state) leaves recovery underspecified.
- **Reading 2 — pure story-doc canonical for everything.** Sprint-status is derived projection. **Rejected** — BMAD-core skills write sprint-status during normal flow; treating those writes as drift violates BMAD-extension discipline.
- **Reading 3 (chosen) — domain-canonical in normal flow; story-doc-wins-tiebreak in recovery disagreement.** Each store is canonical for its own domain during normal operation (BMAD-core's sprint-status writes are respected; story-doc sections are specialist truth). On recovery disagreement, story-doc wins.

**Why story-doc wins the tiebreak (durability rationale, not stipulation):** story-doc section presence is durable and unambiguously machine-readable — specialists' completion artifacts persist as named sections testable for existence with no ambiguity. Sprint-status is mutable scalar state stored in a single small YAML file; mid-write corruption or partial updates are more likely than story-doc section ambiguity. Story-doc isn't canonical *because we say so*; it wins recovery tiebreak because it is the more durable, harder-to-corrupt source. If a future scenario surfaces sprint-status as more reliable than story-doc, the rule revisits.

#### Sub-decision (c) — Recovery Algorithm

Three viable options; FMA per crash scenario produced clear discrimination.

- **A — Story-doc-only reconstruction.** No event log dependency. **Rejected as default** — fails Scenario 1 (specialist crash mid-execution; can't disambiguate partial Dev Agent Record from complete) and loses orchestrator-internal flow control state in Scenario 2.
- **B — Story-doc + event log reconstruction.** Event log primary; story-doc canonical for tiebreak. Disambiguates Scenario 1. **Brittle in Scenario 6** (event log missing/corrupted; pure B fails recovery entirely).
- **B-with-A-fallback (chosen).** Event log primary when present and valid; story-doc-only reconstruction when event log missing/corrupted, with fallback-mode conservatism (ambiguous cases escalate to human rather than auto-resume); git as diagnostic probe for commit verification.

#### Decision

**Recovery algorithm: B-with-A-fallback + git-probe-diagnostic.**

- Event log primary; story-doc-only fallback when event log missing/corrupted, with fallback-mode conservatism.
- Git probe diagnostic-only for commit verification; emits `dangling-uncommitted-work` markers on commit-state mismatch; **does not gate recovery** (visibility over enforcement, consistent with loud-fail doctrine).
- Drift-handling: auto-rebuild run-state + emit marker for normal post-crash drift; fallback-mode ambiguous cases (partial story-doc section without event log signal) escalate to human.

**Canonicality model: Reading 3.** Domain-canonical in normal flow; story-doc-wins-tiebreak in recovery disagreement (durability-based directionality).

**Marker classes added to taxonomy (5):**

1. `specialist-crash-mid-execution` — event log shows specialist dispatched but no return; story-doc partial. Detection mechanism is **ADR-004's responsibility** (cross-coupling noted in Consequences); ADR-005 commits to the marker class existing and to the recovery response (re-dispatch or escalate per orchestrator policy).
2. `state-recovery-drift` — run-state and event-log-replay disagreement; auto-rebuild from story-doc + event log.
3. `state-recovery-degraded` (sub-field `cause`: `event-log-missing` | `event-log-corrupted` | `ambiguous-partial-section-in-fallback`) — fallback-mode active; conservative recovery.
4. `state-recovery-sprint-status-resync` — sprint-status rewritten to match story-doc-implied-state during recovery tiebreak.
5. `dangling-uncommitted-work` — git probe detected commit-field expectation mismatch; visibility-only, not flow-blocking.

#### Rationale

- **Three-store problem, not two.** The factual resolution that sprint-status is a third state store reshapes NFR-R8's two-store framing. Pure Reading 1 has no tiebreak (Scenario 7 underspecified); pure Reading 2 violates BMAD-extension discipline. Reading 3 handles both constraints.
- **Tiebreak directionality is durability-based, not stipulated.** Story-doc wins because section presence is harder to corrupt than scalar YAML state — not because we say so. Reformulating this way leaves the door open for revisit if a future scenario surfaces sprint-status as more reliable.
- **B-with-A-fallback handles pure B's brittleness.** Pure B fails when event log is missing/corrupted; fallback to story-doc-only reconstruction with degraded marker preserves recovery while making the degradation visible. Fallback-mode conservatism (escalate ambiguous cases) prevents B-with-A-fallback from silently degrading into A's failure mode.
- **Git probe is diagnostic, not gating, because of the loud-fail doctrine.** The doctrine says "absence is as visible as presence; user decides." Auto-halting on every git anomaly would treat detection as failure — the inverse posture. Markers handle visibility; user decides resolution. `dangling-uncommitted-work` matches the response shape of `LAD-skipped` and `Tier-3-not-configured`: visible, actionable, not flow-blocking.
- **Drift-handling: auto-rebuild + marker is the doctrine-aligned default.** Drift is *expected* in recovery (post-crash state always has minor inconsistencies); halt-and-surface for every drift event would erode trust-earned-automation by treating every recovery as suspect. The trust-earned-automation commitment is "visibility over enforcement"; halt-and-surface is enforcement, which is reserved for cases where visibility itself is degraded (the fallback-mode carve-out).
- **The architectural commitment underlying Reading 3: story-doc section presence is a load-bearing state oracle for recovery.** "Dev Agent Record present" implies in-progress was reached; "Senior Developer Review (AI) present" implies review was reached; "QA Behavioral Plan + completion markers" imply qa was reached. This isn't a PRD invariant currently; ADR-005 creates it. See Consequence 1.
- **Specialist crash detection cross-couples to ADR-004.** The marker class `specialist-crash-mid-execution` exists at ADR-005's level; the *trigger* (timeout? exit code? heartbeat absence?) is ADR-004's responsibility. ADR-005 doesn't pre-couple ADR-004; it specifies the recovery response and notes the dependency.

#### Consequences

1. **Story-doc section presence becomes a load-bearing state oracle for recovery.** The mapping from section-presence-to-lifecycle-state is a new contract, part of the cell-1 portable surface (per ADR-002). Requirements:
   - Documentation of which sections imply which lifecycle states.
   - Mapping artifact location: `_bmad/automation/config.yaml` or a dedicated schema file (provisional; final placement gated on the still-open repo-layout decision per Project Context Analysis).
   - Schema validation in the harness substrate (per ADR-003 — substrate component 4 may extend to cover the section-presence contract's consistency).
   - **Coordination with FR43 (story-doc version tolerance):** when BMAD changes section names or adds intermediate sections, the state-derivation logic in the orchestrator's recovery algorithm must update. FR43 currently focuses on *reading* docs across versions; ADR-005 extends the concern to *state-derivation correctness* across versions. The mapping artifact is versioned with the BMAD template version it targets.
   - **Post-recovery state shape is a schema commitment, not just skill-prose behavior.** The recovery algorithm's *outputs* (the run-state structure produced after recovery completes) are part of the run-state schema contract. Layer A's reconciliation depends on this post-recovery shape — if recovery produces an unexpected run-state shape, Layer A's enumeration-equivalence check may fail or false-pass. The schema commitment binds: the post-recovery run-state must conform to the same schema that pre-crash run-state conforms to, with the same field invariants. This makes the recovery algorithm's outputs validatable rather than purely behavioral.
2. **Recovery algorithm sketch lands as orchestrator skill prompt instructions** (per ADR-001 — orchestrator skill is host-Bridge per ADR-002 cell 4):
   ```
   SessionStart hook recovery sequence:
   1. Precondition revalidation (per ADR-002 four-capability requirement).
   2. Read all stores: sprint-status / story-doc / run-state / event log / git state.
   3. If event log present and valid:
      a. Replay events to compute expected run-state.
      b. If actual run-state disagrees: rebuild from story-doc + event log; emit state-recovery-drift.
   4. If event log missing or corrupted:
      a. Reconstruct run-state from story-doc only; emit state-recovery-degraded with cause.
      b. For ambiguous partial-section cases: escalate to human; do not auto-resume.
   5. Cross-check sprint-status vs story-doc-implied-state; if disagree, story-doc wins; rewrite sprint-status; emit state-recovery-sprint-status-resync.
   6. Git diagnostic probe for commit verification; emit dangling-uncommitted-work on mismatch.
   7. Terminal-state branch: if state terminal and PR bundle missing/partial, re-run Stop hook.
   8. Resume execution at next seam after last completed.
   ```
3. **Five new marker classes added to the marker taxonomy.** Per ADR-003's enumeration-equivalence reconciliation requirement, these are added to `marker-taxonomy.yaml` with corresponding decision-points in `orchestrator-event.yaml`. CI checks (substrate components 4 and 5 from ADR-003) enforce consistency. Synthetic test stories cover each class.
4. **`specialist-crash-mid-execution` cross-couples to ADR-004.** This ADR commits to the marker class and recovery response (re-dispatch or escalate per orchestrator policy); ADR-004 commits to the detection mechanism (timeout, exit code, heartbeat absence — TBD in ADR-004). The dependency is documented; the two ADRs compose at integration time.
5. **NFR-R8's two-store framing extends to three-store recovery.** ADR-005 elaborates NFR-R8: the policy "story-doc canonical, run-state cache, story-doc-wins-on-disagreement" applies, and the elaboration is that sprint-status is a third store with the same recovery-tiebreak rule. Architectural elaboration of NFR-R8 (parallel to ADR-003's elaboration of FR33/FR65), not PRD drift.
6. **Atomic write protocol (NFR-R1) covers all three stores.** Run-state.yaml, sprint-status.yaml (where orchestrator writes for `qa` transition), and orchestrator-event log entries all use temp-file-plus-atomic-rename. Standard Python pathlib + os.replace covers it; implementation detail.
7. **Defense-in-depth framing from ADR-003 does not extend to ADR-005.** ADR-005's recovery uses three sources but isn't structured as defense-in-depth — sources are *ranked* (event log primary, story-doc canonical for tiebreak, git diagnostic-only), not layered with structurally different bounds. The framing stays local to ADR-003's harness reconciliation, per that ADR's Consequence 7.

#### Revisit Conditions

- **Story-doc section structure changes in BMAD.** If BMAD renames sections or adds intermediate sections, the section-presence-to-state mapping updates. Coordinate with FR43; ensure the mapping is versioned with the BMAD template version it targets.
- **Drift events become frequent on reference-project runs.** If `state-recovery-drift` fires on >X% of resumes (specific threshold TBD post-release), it signals that auto-rebuild is masking a real inconsistency bug. Halt-and-surface may need to replace auto-rebuild; revisit the drift-handling sub-decision.
- **Event log corruption becomes recurring.** If `state-recovery-degraded: event-log-corrupted` fires regularly, investigate root cause (atomic-write failures, disk full, concurrent process interference); the architecture's atomic-write assumption may be violated in practice.
- **Sprint-status semantics change in BMAD.** If BMAD-core changes sprint-status structure (new fields, new lifecycle changes affecting `qa` transition), the canonicality model's domain-canonical-normal-flow assumption needs revisiting.
- **Future scenario surfaces sprint-status as more durable than story-doc.** Hard to imagine; if it occurs, the tiebreak directionality rule revisits with new rationale.
- **Specialist-crash detection mechanism (ADR-004) doesn't compose cleanly.** If ADR-004 lands a detection mechanism that doesn't map cleanly to `specialist-crash-mid-execution` marker class (too noisy; or doesn't differentiate crash from slow-but-alive), revisit ADR-005's marker definition.
- **Git probe produces too many false positives.** If `dangling-uncommitted-work` fires on legitimate git state regularly (user manual amendments, branch state drift for non-error reasons), the probe's detection logic may be too conservative; revisit threshold or scope.
- **BMAD-core adds intermediate story-doc sections that don't map to lifecycle states.** The section-presence-implies-state oracle's correctness depends on a stable mapping from sections to states. If BMAD's template evolves to include sections written mid-state (e.g., a `## Pre-Review Notes` section written before review completes), the oracle's correctness is affected. Revisit the section-to-state mapping artifact (per Consequence 1) to either incorporate the new sections or explicitly exclude them from state derivation. This is a more plausible scenario than "sprint-status more durable than story-doc" and complements FR43's reading-tolerance with state-derivation-correctness.

### ADR-006: Per-Story Cost Telemetry Source

**Status:** Decided.
**Date:** 2026-04-25.

#### Context

NFR-P5 requires per-specialist × per-retry cost breakdown in the PR bundle. NFR-O8 requires in-flight cost observability streamed to terminal at each specialist completion, with `cost-near-ceiling` warning when running cost crosses 75% of the per-story ceiling (i.e., $3.75 against the MVP $5 ceiling). Per-retry partitioning is load-bearing — retry-budget-exhaustion debugging requires per-retry cost resolution, not total deltas. **NFR-O8's granularity is between-specialist** (at each specialist completion), not real-time mid-specialist.

ADR-004 surfaced that Claude Code exposes OpenTelemetry instrumentation natively (`claude_code.cost.usage` and `claude_code.token.usage` metrics; `query_source` attribute distinguishing `main` / `subagent` / `auxiliary`; span hierarchy nesting subagent spans under parent `claude_code.tool` span). ADR-006 chooses the consumption path.

**Verification (April 2026) surfaced three load-bearing findings:**

1. **Source choice is forced — OTel is the only programmatic cost-tracking path for in-session orchestrators.** The `/usage` slash command is interactive-only (not callable from skill code). Agent SDK's `total_cost_usd` API applies to programmatic SDK consumers, not in-session skills (orchestrator-as-skill per ADR-001). `claude --cost` doesn't exist as a queryable interface. Task tool's return is text-only with no token-count metadata exposed to in-session code. OTel platform-layer instrumentation is the path.

2. **OTel does NOT know about orchestrator-level retry attempts.** OTel's `attempt` attribute on `claude_code.api_request` counts API-level retries (Claude Code's automatic retry on transient errors), not orchestrator-level specialist retries (per FR8's whole-story retry budget). Two different retry concepts. Per-retry attribution at NFR-P5's granularity requires an orchestrator-side mechanism.

3. **A3-cull correction during matrix evaluation.** Initial fork-elicitation provisionally culled A3 (post-event `prompt.id` correlation) as NFR-O8-violating; matrix re-evaluation revealed A3 satisfies NFR-O8 at the between-specialist granularity NFR-O8 specifies. The earlier framing was too narrow on what NFR-O8 requires; A3 (renamed A3' for clarity in this ADR) is viable. This is a within-fork judgment refinement during evaluation, not retroactive supplementation of a prior ADR — surfaced explicitly so future readers see the correction happened before this ADR landed, not after.

#### Decision

**Combo 3 — A3' + B1 + C3:**

- **Attribution (A3') — orchestrator-owned `prompt.id` correlation.** Orchestrator records `(prompt.id, retry_attempt, specialist)` mapping in run-state per-dispatch. Between specialist completions, orchestrator reads OTel events filtered by `prompt.id`; aggregates per-specialist × per-retry totals; checks against 75% ceiling and emits `cost-near-ceiling` if crossed.
- **Deployment (B1) — operator-managed OTLP backend.** Operator runs OTLP-compatible backend; typical setup is a local OTLP collector writing telemetry to known files for orchestrator consumption. `/bmad-automation init` scaffolds collector configuration and OTel environment variables (`CLAUDE_CODE_ENABLE_TELEMETRY=1`, exporter targets, endpoints).
- **Persistence (C3) — hybrid.** Run-state caches in-flight cost counters for `cost-near-ceiling` decisions; OTel backend stores full historical detail for PR bundle assembly's per-specialist × per-retry breakdown. Run-state's role is bounded (in-flight totals only); backend handles long-form reporting.

**Source choice is committed as forced**, not as a fork. OTel is the only programmatic in-session cost-tracking path verified to exist. Future architectural changes that break OTel availability trigger ADR-006 revisit at source-choice level, not just sub-decision level (see Revisit Conditions).

#### Rationale

- **Source choice is forced by the platform.** Verified primitive landscape (April 2026) leaves no alternative for in-session cost-tracking from an orchestrator-as-skill. ADR-006 commits to OTel because no other path satisfies NFR-P5 / NFR-O8 from this architecture.
- **A3' over A1.** A1 (resource-attribute injection per-dispatch via `OTEL_RESOURCE_ATTRIBUTES`) was explored but carries an implementation viability gap: setting environment variables from skill code (via Bash tool or otherwise) does not reliably propagate to Task-tool-spawned subagent processes given Claude Code's process model — Task tool spawns from the main session, not from Bash subshells, and verification did not surface a clean workaround for skill-level env-var injection that propagates to Task-spawned subagents. A3' avoids this gap entirely by keeping attribution orchestrator-internal: the orchestrator owns the `prompt.id → (retry_attempt, specialist)` mapping in its own run-state, decoupled from any platform-feature dependency.
- **C3 over C1 and C2.** C1 (run-state-only) requires run-state to carry full historical per-retry × per-specialist breakdown, which bloats run-state's role beyond the in-flight cache it should be. C2 (OTel-backend-only) couples reliability of in-flight `cost-near-ceiling` observability to backend availability — backend unreachable mid-run forces a hard fail rather than a graceful marker. C3 (hybrid) divides responsibility cleanly: run-state cache is bounded and tolerant of backend outages; OTel backend is queried only at PR bundle assembly time for historical detail.
- **NFR-O8's between-specialist granularity is sufficient.** NFR-O8 specifies cost visibility "at each specialist completion." The orchestrator reads OTel data after each specialist completes, before dispatching the next. Real-time mid-specialist observability is neither required nor compatible with the orchestrator's loop structure.
- **Composition with ADR-005's three-store model.** Run-state-cached cost counters are orchestrator-domain canonical (per ADR-005's domain-canonical-in-normal-flow framing). NFR-R1's atomic-write protocol applies; ADR-005's recovery algorithm gains a cost-counter rebuild path via event log replay (see Consequences).

#### Consequences

This decision commits the architecture to:

1. **Run-state gains a cost-counter section.** Specific schema fields are TBD at implementation time, but the section's role is fixed: cache running per-specialist × per-retry cost totals plus last-updated `prompt.id` for in-flight `cost-near-ceiling` decisions. Section is bounded — only what's needed for the in-flight 75%-of-ceiling check, not full historical detail. Full detail lives in the OTel backend (per C3).
2. **Cost-counter writes batch with other run-state writes between specialist completions.** Cost-counter updates happen at the same orchestrator decision points as other run-state updates (advancing seam state, recording specialist returns). Per ADR-005's atomic-write protocol, these are batched into a single atomic write per seam — not per individual cost event. This bounds atomic-write frequency to seam-transition rate, not API-call rate.
3. **ADR-003's substrate gains a new event class.** Cost events (e.g., `cost-event` with `prompt.id`, `retry_attempt`, `specialist`, `cost_delta`) need event-log entries for ADR-005's recovery reconstruction (run-state cost counters must be rebuildable from event log replay). This is a new entry in `orchestrator-event.yaml` requiring marker-taxonomy ↔ event-schema enumeration-equivalence coverage per ADR-003 substrate component 4. **Cross-coupling: ADR-003's enumeration-equivalence check expands to include cost-event classes; synthetic test fixtures must cover them per substrate component 5.**
4. **New marker classes added to the taxonomy:**
   - `cost-near-ceiling` (already named in NFR-O8) — running cost crossed 75% of per-story ceiling.
   - `cost-tracking-degraded` — OTel backend unreachable at PR bundle assembly time; bundle includes in-flight cost data from run-state but historical per-retry × per-specialist detail is missing.
   - `cost-counter-rebuild` — run-state cost counters were rebuilt from event log replay during recovery (per ADR-005 recovery algorithm).
5. **OTel metric and attribute names are host-Bridge per ADR-002's two-axis classification.** Names like `claude_code.cost.usage`, `claude_code.token.usage`, `query_source`, `prompt.id` are Claude-Code-specific identifiers. On a host-axis port (Codex, Cursor) to a runtime that doesn't expose equivalent OTel instrumentation, the cost-tracking layer rebuilds against the new host's telemetry primitives. **The portable surface is the `(specialist, retry_attempt) → cost` attribution model and run-state's cost-counter section structure; the binding to specific OTel metric/attribute names is the bridge layer.** ADR-002's matrix gains an entry for this dependency at host-Bridge / methodology-Portable (cell 4).
6. **`/bmad-automation init` scaffolds OTel telemetry setup.** Init writes environment variable configuration and a minimal OTLP collector configuration. NFR-P3 5-minute onboarding is satisfied by init-time automation rather than manual operator setup. If the operator already has an OTLP backend (Honeycomb, Datadog, local OTel Collector), init prompts for credentials/endpoint instead of bundling a default.
7. **Source-choice-forced commitment.** Future architectural changes that break OTel availability — port to a host without OTel platform instrumentation, Anthropic deprecating Claude Code's OTel instrumentation, or a credible alternative cost-tracking primitive emerging — trigger ADR-006 revisit at source-choice level, not at sub-decision level. The decision's forced-source framing makes this revisit pathway explicit.

#### Revisit Conditions

- **OTel availability changes (source-level revisit).** Claude Code deprecates its OTel instrumentation, a future host doesn't expose equivalent telemetry, or Anthropic ships a different cost-tracking primitive that supersedes OTel for in-session use.
- **Anthropic ships skill-level env-var injection capability.** If `OTEL_RESOURCE_ATTRIBUTES` (or equivalent) becomes settable from skill code with reliable propagation to Task-spawned subagents, A1 becomes viable; revisit attribution mechanism. A3''s orchestrator-internal approach is functional but more complex than A1's resource-attribute pattern would be if usable.
- **Per-retry granularity in OTel becomes native.** If a future Claude Code version adds an `orchestrator_retry_attempt` attribute (or similar) to OTel events natively, the orchestrator's `prompt.id` correlation becomes redundant. Revisit attribution.
- **Backend unavailability rate elevated.** If `cost-tracking-degraded` fires regularly on reference-project runs, C3's reliance on backend for historical detail at PR bundle time is bottlenecked. Revisit persistence — possibly C1 (run-state-only with bounded historical detail) becomes preferable if backend availability is unreliable.
- **OTLP collector setup overhead exceeds NFR-P3.** If init-time OTel scaffolding can't reliably bring operators to a working setup in 5 minutes, persistence model needs revisiting. Possible graceful degradation: estimate-only cost tracking with `cost-tracking-degraded: no-backend-configured` marker as the loud-fail signal.
- **Cost-event class drift in event log.** If cost events are added to the event log without corresponding marker-taxonomy entries (ADR-003 substrate component 4 violation), revisit how cost-events are integrated with the marker taxonomy. The enumeration-equivalence check should catch drift; if it doesn't, the substrate's coverage rule needs strengthening.

## Schema Design Notes

Schema artifacts referenced by ADRs but not requiring full ADR ceremony. Each note documents an architectural commitment to a specific schema artifact — its purpose, structure, consumers, and cross-references — at appropriate altitude (lighter than ADR, heavier than implementation detail). Schema-design notes sit at the same architectural altitude as ADRs for purposes of cell-1 portability classification (per ADR-002) and substrate enumeration-equivalence (per ADR-003).

### SDN-001: Dependency Failure-Profile Schema (`_bmad/automation/dependencies.yaml`)

**Status:** Specified.
**Date:** 2026-04-25.

#### Purpose

Authoritative declaration of every external dependency the Automator interacts with, its supported version range, and its failure profile per lifecycle phase. Consumed by `/bmad-automation init` for precondition checks (per FR37/FR38), at runtime by the orchestrator skill for graceful-degrade handling (per NFR-I3), and by PR bundle assembly for marker emission (per FR30). Aligned with the PRD's Runtime Compatibility Matrix.

#### Why a schema-design note rather than an ADR

Option analysis at fork-#7 elicitation surfaced no architectural fork — schema design is mechanical given the six concrete dependencies in the PRD's Runtime Compatibility Matrix and the three failure-profile classes (`total-block`, `graceful-degrade`, `opt-in-skip`). The three "where this could be wrong" criteria from the collapse-check (cross-dependency constraints, additional lifecycle phases beyond init/runtime, fourth profile class) did not fire on any of the six MVP-and-Phase-1.5 dependencies. Two known schema-depth requirements emerged (project-type-conditional profiles for Playwright MCP and mobile MCP; opt-in-skip sub-states for LAD) but both have one obvious mechanical expression and no real fork. Running full ADR ceremony on the schema design would be ritual, not architecture.

#### Schema (canonical structure)

```yaml
# _bmad/automation/dependencies.yaml
# Authoritative dependency manifest. Cell-1 portable artifact (per ADR-002).
# Schema-version bumps require reconciliation review (per cell-1 discipline).

schema_version: "1.0"

dependencies:
  claude-code:
    version_floor: "2.1.32"
    version_ceiling_policy: "tracked-against-current-releases; primitive-deprecation triggers version-pin review"
    profiles:
      init:
        profile: total-block
        diagnostic: "Claude Code v2.1.32+ required. Run `claude --version` to check."
      runtime:
        profile: total-block

  bmad-core:
    version_floor: "6.0"
    version_ceiling_policy: "tracked-against-bmad-releases; upstream-absorption event triggers version-pin review"
    profiles:
      init:
        profile: total-block
        diagnostic: "BMAD core v6.0+ required."
      runtime:
        profile: total-block

  tea-module:
    version_policy: "version-agnostic; detected at init"
    profiles:
      init:
        profile: total-block
        diagnostic: "TEA module not installed. Run `/bmad:install tea` and re-run `/bmad-automation init`."
      runtime:
        profile: total-block

  playwright-mcp:
    version_floor: "officially-supported-as-of-mvp-release"
    by_project_type:
      web:
        profiles:
          init:
            profile: total-block
            diagnostic: "Playwright MCP unreachable. Required for web QA. See docs/playwright-mcp-setup.md."
          runtime:
            profile: graceful-degrade
            marker_class: env-setup-failed
            diagnostic_pointer: "Playwright MCP unavailable mid-run; QA phase skipped with marker."
      api:
        profiles:
          init:
            profile: opt-in-skip
          runtime:
            profile: opt-in-skip
      mobile:
        profiles:
          init:
            profile: opt-in-skip
          runtime:
            profile: opt-in-skip

  mobile-mcp:
    phase: "1.5"
    version_floor: "TBD-at-Phase-1.5-design-time"
    by_project_type:
      mobile:
        profiles:
          init:
            profile: total-block
            diagnostic: "Mobile MCP required for mobile projects. See docs/mobile-mcp-setup.md."
          runtime:
            profile: graceful-degrade
            marker_class: mobile-blocked
            diagnostic_pointer: "Mobile MCP unavailable mid-run; mobile QA phase skipped."
      web:
        profiles:
          init:
            profile: opt-in-skip
          runtime:
            profile: opt-in-skip
      api:
        profiles:
          init:
            profile: opt-in-skip
          runtime:
            profile: opt-in-skip

  lad:
    phase: "1.5"
    version_floor: "latest-at-phase-1.5-design-time"
    profiles:
      init:
        profile: opt-in-skip
        sub_classifications:
          - condition: configured-but-api-key-missing
            emits_marker: LAD-skipped
            diagnostic_pointer: "LAD configured but `LAD_API_KEY` env var missing. Set the env var or disable LAD in config.yaml."
          - condition: unconfigured
            silent: true
      runtime:
        profile: opt-in-skip
        sub_classifications:
          - condition: configured-but-api-key-missing
            emits_marker: LAD-skipped
          - condition: unconfigured
            silent: true
```

#### Consumers

- **`/bmad-automation init` (precondition checks per FR37/FR38).** Reads the schema; for each dependency, evaluates `init.profile` against the operator's environment. `total-block` halts init with the named diagnostic; `graceful-degrade` emits the named marker but proceeds; `opt-in-skip` stays silent unless a `configured-but-missing` sub-classification fires.
- **Orchestrator skill (runtime degradation handling per NFR-I3).** Reads `runtime.profile`; on dependency unavailability mid-run, emits marker per `marker-class` field and continues per profile policy.
- **PR bundle assembly (per FR30 / FR32 / FR33).** Marker emissions from runtime degradation flow through ADR-003's substrate component 3 (skip-event reconciliation) and component 4 (marker-taxonomy ↔ event-schema enumeration-equivalence).
- **BMAD-extension audit (per FR65).** New dependencies added to this schema are classified via the audit's standard convention process (automator-internal / upstream-proposal / research-needed).

#### Cross-References

- **ADR-002 portability classification.** This schema is **cell 1 (Host-Portable / Methodology-Portable)** — failure profiles are policy taxonomy, primitive-agnostic, and methodology-agnostic. Same architectural altitude as `marker-taxonomy.yaml` and `orchestrator-event.yaml`. ADR-002's matrix gains an entry for this schema at cell 1 (architectural core).
- **ADR-003 substrate.** `marker_class` fields in this schema (e.g., values `env-setup-failed`, `mobile-blocked`, `LAD-skipped`) must match entries in `marker-taxonomy.yaml`. **Substrate component 4 (marker-taxonomy ↔ event-schema enumeration-equivalence) extends to cover this schema's marker-class references — every marker-class named here must exist in the marker taxonomy.** Drift between this schema and the taxonomy fails CI. This is a third enumeration-equivalence check that ADR-003's substrate handles, in addition to the marker-taxonomy ↔ event-schema and marker-taxonomy ↔ fixture-coverage checks.
- **ADR-005 cross-state consistency.** Init-time precondition state (which dependencies passed) is recorded in run-state per the standard schema; recovery uses this for resume-time precondition revalidation. Not a separate consistency model; reuses run-state's existing structure.
- **ADR-006 cost-tracking.** OTel availability is implicit in the Claude Code dependency entry (version-floor 2.1.32 covers OTel instrumentation availability). If a future Claude Code version drops OTel, the version-floor bumps and the source-choice-forced commitment in ADR-006 fires.
- **PRD Runtime Compatibility Matrix (Developer-Tool Specific Requirements).** This schema is the operational form of the PRD's compatibility matrix. The matrix's per-dependency rows map directly to entries in this schema; the matrix's "failure profile" column maps to per-phase profile fields here. Drift between PRD matrix and this schema is a documentation-drift signal (similar to ADR-004's flagged matrix drift on the Agent-Teams primitive entry).

#### Versioning Discipline

This schema is a cell-1 architectural-core artifact. Per ADR-002's discipline:

- **Schema-structure changes** (adding a profile class, adding a lifecycle phase, changing field semantics) are **major-version events** — schema-version bumps with CI consistency review and downstream consumer updates.
- **Adding a new dependency entry** is a **minor-version event** — additive, backward-compatible.
- **Updating a dependency's profile** (e.g., Playwright MCP changes from graceful-degrade to total-block at runtime) is a **minor-version event** with explicit migration guidance for operators.
- **Co-versioning with marker-taxonomy.yaml.** Marker-class additions/removals affect both this schema and the marker taxonomy; reconciliation review covers both per ADR-003 substrate component 4 (extended).
- **Marker-taxonomy bump rule.** `schemas/marker-taxonomy.yaml`'s header documents the per-marker bump rule (any addition or removal of a marker class bumps the minor version; renames or removed `diagnostic_pointer` fields bump the major version). Co-versioned with `orchestrator-event.yaml` per ADR-003 Consequence 2; substrate component 4 (story 1.5's `enumeration_check`) enforces consistency between them at CI.

#### Open Items

- **Optional `phase` field semantics.** The `phase` field appears on `mobile-mcp` and `lad` entries to declare post-MVP scope. Field is optional; **absence means MVP-scope; non-MVP values declare the phase in which the dependency activates** (e.g., `phase: "1.5"` for Phase 1.5 dependencies). Schema-loading code in the harness should treat absence as MVP rather than as missing data.
- **Final filename.** `dependencies.yaml` is the proposed name; collision check against BMAD's existing conventions worth doing at implementation time.
- **Project-type detection mechanism.** The schema references `by-project-type` keys but the actual project-type detection (how `/bmad-automation init` knows whether the user's project is web/API/mobile) is implementation logic, not schema. Out of scope for this note.
- **PRD documentation drift.** The PRD's Runtime Compatibility Matrix entry for Claude Code says "v2.1.32+ (Agent Teams primitive)" — per ADR-004's verification finding, this should update to reflect Task tool as the canonical primitive. The schema's `version-floor: "2.1.32"` for Claude Code stands; the parenthetical primitive-name update is a separate documentation task tracked alongside ADR-004's flagged drift.
- **`schema-version` semantic.** The schema's own `schema-version` field starts at `"1.0"`; bumping policy is per the Versioning Discipline section above. Whether this matches the broader Automator's semver (per Developer-Tool Requirements → Versioning & Deprecation) or has its own version-track is an implementation-time decision.

## Project Context Analysis

_Drafted during step-02 elicitation; supporting material for the ADRs above. Open Architectural Questions are annotated with their resolution ADR or "OPEN" status as of close of step-02._

### Requirements Overview

**Functional Requirements.** 67 MVP FRs organized into 9 capability areas, plus 12 post-MVP FRs:

1. **Story Loop Execution** (FR1–FR7) — slash-command entry, per-seam state streaming, orchestrated specialist dispatch, per-story branch lifecycle, BMAD lifecycle-state transitions, env lifecycle ownership.
2. **Retry & Scope Discipline** (FR8–FR15) — whole-story retry budget, structured-action-item routing (never prose), capability-level fix-only constraint on Dev retries, `scope_expanded_to` declaration + post-return diff verification, retry history per round, escalation bundle on exhaustion.
3. **Behavioral Verification (QA)** (FR16–FR25) — AC-only input boundary, independent product driving via Playwright MCP (web) / HTTP (API), per-AC assertion-evidence triples, three-tier evidence hierarchy (mechanical / outcome / semantic), three MVP exploratory heuristics, AC-numbering smoke-first ordering, AC-hash plan-drift detection, two distinct escalation classes (verification-fail vs env-setup-fail), plan-persistence-compromise visibility.
4. **Code Review (Adversarial)** (FR26–FR29) — wraps BMAD's 3-layer parallel pass, adopts existing taxonomy (`decision_needed | patch | defer | dismiss`), graceful degradation via `failed_layers`, LAD as 4th layer in P1.5.
5. **Loud-Fail Surface** (FR30–FR34) — authoritative marker taxonomy in reference artifacts, actionable pointer per marker, PR-bundle loud-fail block, harness reconciliation CI check (not a lint rule), first-run TEA-boundary orientation message.
6. **Installation & Initialization** (FR35–FR44) — plugin-primary + git-clone fallback, precondition checks with named-invariant diagnostics, hard-dep blocking, sample-story scaffold, config stubs, non-destructive on existing projects, N-2 BMAD-template tolerance, 5-min first-loop target.
7. **State & Resumability** (FR45–FR50) — ephemeral run-state (gitignored, auto-cleaned on success, preserved on escalation), SessionStart reattachment, `resume` + `status` commands, per-run evidence persistence, Dev-semantic + hook-mechanical commit authorship.
8. **Specialist Contracts & Schema Enforcement** (FR51–FR56) — uniform envelope (`status`, `artifacts`, `findings`, `rationale`) + specialist extensions, CI-enforced forbidden fields (`next_action`, `recommendation`), specialist-specific extension schemas.
9. **Hooks & Architectural Invariants** (FR57–FR66) — exactly 3 hooks, CI-enforced ≤3 hooks / 20-lines-of-bash / pluggability no-cross-refs / extension-discipline audit, story-doc section write-scope constraint.

**Architectural reading.** FRs are unusually contract-heavy: the specialist return envelope (area 8) is the linchpin other FRs reference; hooks (area 9) are the mechanical-side-effect boundary; loud-fail markers (area 5) are the cross-cutting visibility substrate that every skip-path terminates into. The architecture's primary work is hardening those three surfaces and the machinery that enforces them.

**Non-Functional Requirements.** 33 NFRs across 5 themes:

- **Performance & Cost (P1–P6)** — per-story cost target <$3 / ceiling <$5; per-specialist timeout default 15 min; first-loop ≤5 min; context-near-limit markers; per-specialist × per-retry cost observability in PR bundle; evidence size budget.
- **Reliability & Durability (R1–R8)** — atomic run-state writes; crash recovery without duplicate state advance; strict git-operation scope; evidence durability across runs; retry history preservation on exhaustion; hook-failure surface as distinct marker; **cross-state consistency protocol (NFR-R8): story-doc canonical, run-state cache, story-doc write completes before run-state advance.**
- **Integration & Volatility (I1–I6)** — dependency range declaration + init-time enforcement; version-pin deprecation triggers; per-failure-profile degradation; BMAD-core-absorption migration pathway; N-2 story-doc template tolerance; MCP breaking-change turnaround target ≤2 weeks.
- **Security & Safety (S1–S6)** — LAD API-key env-var-only; git ops scope-locked to per-story branch; hook trust via public-repo visibility + 20-line CI-enforced bound; story-doc write-scope contract-enforced; env provisioning ephemeral + orphan-process cleanup.
- **Observability & Diagnosability (O1–O8)** — terminal streaming per-seam live; human-readable YAML run-state; per-specialist structured logs; `status` command inspect-without-mutate; named-invariant diagnostics; per-commit `[bmad-automation story/<id>]` tag; evidence-ref linkability with dangling-ref marker; **in-flight cost observability with 75%-of-ceiling `cost-near-ceiling` warning (visibility, not auto-halt).**

**Architectural reading.** NFRs concentrate in three areas that force design choices: cost/latency observability requires per-specialist × per-retry cost accounting → instrumentation layer; cross-state consistency forces a specific write-ordering protocol and recovery algorithm → state-management design; failure-profile asymmetry (init vs runtime on Playwright MCP) forces per-lifecycle-phase dependency-management design.

**Invariants (9 named).** Five CI-enforced (≤3 hooks, 20-lines-of-bash, sensor-not-advisor schema, loud-fail marker completeness, pluggability no-cross-refs); four review-enforced (BMAD-extension discipline, QA independence from TEA artifacts, context firewalling at retry boundaries, QA plan-persistence-compromise documented). The split is deliberate honesty about which invariants can silently erode. ADR-003 elaborates harness-completeness (sub-item of FR33's CI-enforced invariant) and skip-class recognition (sub-item of FR65's review-enforced invariant); the canonical 5/4 count is unchanged.

**Scale & Complexity.**

- Primary domain: developer tooling — AI-agent runtime extending Claude Code + BMAD. Not a typical app; the artifact is agents, hooks, contracts, and a run-state file. No UI shell, no HTTP service, no DB.
- Complexity level: medium domain, high architectural (per PRD classification). Surface is small (5 agents, 3 hooks); concept density is high.
- Estimated architectural components at MVP: 1 orchestrator + 4 specialist subagents + 3 hooks + 1 run-state store + 1 evidence store + 1 config + 1 qa-runbook + 1 marker taxonomy + 1 extension-audit doc + 1 loud-fail harness + 4 slash commands — ~18 first-class components, each with a documented contract.

### Technical Constraints & Dependencies

**Runtime primitives (Claude Code).** v2.1.32+ — Task tool is canonical multi-agent dispatch primitive *(updated per ADR-004 verification; previous "Agent Teams primitive" framing was outdated)* — total-block. All invocation is slash-command; no programmatic SDK, no CLI binary, no HTTP API, no direct specialist invocation. Hook scripts are bash-only (≤20 lines each).

**Methodology dependency (BMAD core).** v6.0+ — total-block. The Automator extends, doesn't fork. Two upstream proposals drafted (`qa` lifecycle state, `## QA Behavioral Plan` story-doc section) + seam-transition pattern itself.

**Test-architecture dependency (TEA).** Hard total-block at `init`. Unchanged by Automator. Boundary: TEA validates tests; Automator exercises product. QA reads AC only — never TEA test files.

**MCP dependencies.** Playwright MCP (graceful-degrade at runtime, total-block at init for web QA); mobile MCP (opt-in-skip, P1.5); LAD external LLM (opt-in-skip, P1.5).

**Platform.** macOS + Linux first-class; Windows via WSL inherited but not MVP-validated.

**Version-tolerance window.** N-2 minor versions of BMAD story-doc template (default, revisit-conditioned). Out-of-window → loud-fail marker.

**Explicit non-constraints.** No programmatic SDK surface, no CLI binary, no HTTP API/webhook, no direct specialist invocation, no 4th hook ever (budget is a cap). No i18n/localization (English-only, explicitly scoped).

### Cross-Cutting Concerns Identified

1. **Contract integrity across specialists.** Uniform envelope shape with forbidden-field enforcement — schema is the sensor-not-advisor invariant's mechanism. **Resolved by ADR-003** (substrate component 1).
2. **Loud-fail surface as a substrate.** Every skip/failure/absence emits a marker; harness reconciles detected skips against emitted markers (not a tautological "marker exists → pass" lint); PR bundle has dedicated top-of-bundle block. **Resolved by ADR-003** (three-layer defense-in-depth, with unknown-unknown routed out via FR65).
3. **State management — dual-store with explicit canonical/cache split.** Story-doc (BMAD-native, human-readable, canonical) + run-state.yaml (ephemeral, machine-only, cache). Write-ordering: story-doc first, run-state second. Recovery: run-state reconstructed from story-doc on disagreement. NFR-R8 fixes the protocol; specific schema-versioned format is implementation work.
4. **Context firewalling at retry boundaries.** Concrete mechanism (prompt-prefix wrapper producing structured action items + scope lock, paired with post-return `scope_expanded_to` diff verification). Cross-cuts Dev retries and orchestrator-level scope-assertion enforcement.
5. **Pluggability enforcement.** Specialists cannot import/reference each other (CI-enforced). Removal of one specialist is O(1).
6. **Failure-profile asymmetry.** Three profiles (total-block / graceful-degrade / opt-in-skip) with init-vs-runtime variance on at least one dep (Playwright MCP). Architecture needs a dependency declaration shape that expresses per-lifecycle-phase behavior.
7. **BMAD-extension discipline as a first-class artifact.** Public audit document classifying every new convention. **Workflow expanded by ADR-003** to include skip-class recognition as an explicit subsection.
8. **Portability principle — primitive-agnostic surfaces.** **Resolved by ADR-002** (two-axis model: host-runtime × methodology, 3×3 matrix, four-capability precondition).
9. **Evidence integrity.** AC-assertion-evidence triples (structurally required), three-tier hierarchy with Tier 3 default `not_configured` surfaced as a marker, evidence normalization contract.
10. **BMAD-core-absorption migration pathway.** First-class architectural commitment. Every upstream-proposal classification includes a migration plan (acknowledgment → adapter window → deprecation → removal).

### Architectural Questions Identified — Status as of close of step-02

| Question | Status | Resolution |
|---|---|---|
| Orchestrator implementation primitive | **RESOLVED** | ADR-001 (skill in main session + envelope-shaped output protocol enforced at CI) |
| Portability boundary — host-axis vs methodology-axis | **RESOLVED** | ADR-002 (two-axis 3×3 model + four-capability precondition) |
| Schema enforcement technology | **RESOLVED** | ADR-003 (Python starting choice; Pydantic + jsonschema; substrate reused for harness reconciliation) |
| Loud-fail harness implementation | **RESOLVED** | ADR-003 (three-layer defense-in-depth: orchestrator-events / runtime-state / fixtures+synthetic stories; unknown-unknown routed to FR65) |
| Subagent dispatch mechanism (Task tool vs Agent Teams primitive) | **OPEN** | Downstream of repo-layout decision. |
| Run-state file format | **PARTIALLY RESOLVED** | YAML confirmed (NFR-O2); schema-versioned per ADR-002/003; specific schema definition is implementation work. |
| Repo layout (plugin-primitive-ready vs `.claude/skills/` vs both) | **OPEN** | Tracks against plugin-primitive stability research blocker. |
| State-streaming mechanism | **OPEN** | How main-session output streams per-seam transitions; implications for `status` command consistency. |
| Extension-audit doc location and format | **PARTIALLY RESOLVED** | ADR-003 names skip-class-recognition workflow as a required subsection; full doc location/format/cadence is downstream work. |
| Cost-accounting mechanism | **OPEN** | Per-specialist × per-retry cost breakdown source (NFR-P5). Token telemetry, orchestrator-owned counters, or hybrid. |

### Research Blockers Still Open

- **`deferred-work.md` format spec** — blocks loud-fail handling for `defer`-bucket findings.
- **TEA API surface for orchestrator handoff** — does orchestrator await TEA completion; what TEA artifacts does QA ignore vs. consume; how does the boundary surface in run-state.
- **Upstream proposal format for BMAD-METHOD** — blocks submission of `qa` lifecycle state and `## QA Behavioral Plan` proposals.
- **Claude Code plugin primitive name and stability** — shapes install path (primary vs fallback) and repo layout.

## Starter Template Evaluation

The standard starter-template question doesn't fit this project's shape. This project distributes as a Claude Code plugin (when the primitive stabilizes) or `.claude/skills/` git-clone-symlink (fallback) — not a Next.js / NestJS / CLI-tool starter. The "starter" question decomposes into three sub-decisions: two answered by following existing BMAD conventions (no template selection needed), one earning the step's discipline of layout decision + version verification.

### Sub-decision 1 — Plugin / `.claude/skills/` Layout

**Follow existing BMAD skill-bundle conventions.** Direct evidence in this repo: `_bmad/bmm/`, `_bmad/tea/`, `_bmad/wds/` use a consistent layout pattern (`config.yaml` at module root, sub-folders for workflow groups, step-file architecture inside each workflow). The Automator's `.claude/skills/bmad-automation/` (and its sub-skills for Orchestrator, Dev wrapper, Review wrapper, QA) inherit this layout.

**No starter template required.** Plugin-primitive layout (target: `/plugin install bmad-automation`) tracks against the open research blocker on plugin-primitive stability; layout adapts when the primitive stabilizes.

### Sub-decision 3 — BMAD Skill Scaffolding

**Follow existing BMAD skill conventions.** Pattern visible in `_bmad/bmm/3-solutioning/bmad-create-architecture/` (the skill running this workflow): `SKILL.md` + `workflow.md` + `steps/` directory containing per-step micro-files + `data/` directory for CSVs. The Automator's new skills (orchestrator, specialist wrappers, possibly auxiliary) follow this exact pattern.

**No starter template required.** BMAD's existing skills are the canonical reference.

### Sub-decision 2 — Python Harness Substrate Layout

Per ADR-003, the substrate is small — five components (envelope schema validator + orchestrator-event schema validator + skip-event-to-marker reconciler + marker-taxonomy ↔ event-schema enumeration-equivalence checker + marker-taxonomy ↔ fixture-coverage enumerator). No web surface, no framework, no service. Layout decision reduces to a small list of well-trodden picks.

**Scope of this sub-decision:** the harness's *layout contents* — what's in it, library picks, dev tooling. The substrate's *location in the repo* is downstream of the plugin-primitive-stability research blocker (OPEN per Project Context Analysis) and lands when the repo-layout decision is taken. Provisional candidates for location: `tools/loud-fail-harness/` or `_bmad/automation/harness/` adjacent to the skill bundles. This separation matters: contents (decided here) carry over regardless of where the substrate ultimately sits.

#### Layout Pattern

- **`pyproject.toml`-based packaging with `src/` layout.** Settled Python convention; no alternative worth evaluating for a CI tool of this size.

#### Library Picks (current versions verified 2026-04-25)

- **Schema validation — Pydantic v2.** Latest stable: **2.13.3** (released 2026-04-20). v3 not yet announced; v2 is the current recommended default for new projects. Pydantic v1 remains in maintenance under the `pydantic.v1` namespace (1.10.26) for backward compatibility — not relevant here.
- **JSON Schema validation — `jsonschema` package** (current: 4.26.0). The ecosystem has consolidated: `jsonschema` is the primary library and uses the newer `referencing` library *internally* for `$ref` resolution. These compose rather than compete; for this project's substrate, use `jsonschema` directly. The `referencing` package is invoked explicitly only for custom reference-resolution behavior, which is out of scope.
- **Lint + format — Ruff.** Universal current recommendation; subsumes flake8 + black + isort + most equivalents into a single tool. No alternative worth evaluating.

#### Type Checker — Open Landscape, Conservative Default

The Python type-checker landscape is in flux as of April 2026:

- **mypy** — slow but reference implementation; mature; PyPI-installable; fits CI cleanly.
- **pyright / basedpyright** — fast, accurate; pyright is npm-distributed (basedpyright wraps it for PyPI).
- **ty** (Astral) — Beta release; Astral recommends for "motivated users for production use"; stable release expected 2026-late or 2027-early. Designed as the eventual replacement for mypy/pyright across the Astral toolchain (uv + ruff + ty).

**Decision: start with mypy.** Reasoning:
- The harness is small and CI-only; speed is not load-bearing (mypy's slowness shows up on large codebases or editor latency, neither applies).
- mypy's PyPI-installability and reference-implementation status make it the lowest-friction integration with `pyproject.toml` + uv-managed dev dependencies.
- Type-checker swap is a minor-version revision per ADR-003's "language is the most easily-revised piece" framing — the substrate's contracts (the five components) are the architectural commitment; the type checker isn't.

**Revisit when:**
- Astral's `ty` reaches stable release. The Astral toolchain (uv + ruff + ty) is the natural composition for a project already using uv + ruff; `ty` becomes the default once stable.
- Type-checking ergonomics on the harness specifically prove worse than predicted (e.g., reconciliation logic surfaces type complexity mypy doesn't handle well).

#### Dev & Build Tooling

- **`pytest`** for tests. Settled.
- **`uv`** for Python version management + virtual env + dependency install. Astral toolchain composes (already using ruff; uv is the natural complement).
- **CI integration:** harness invoked via `uv run`-style commands in CI; standard `pyproject.toml` `[tool.ruff]` and `[tool.mypy]` sections configure lint and type check.

#### Revisit Conditions (composing with ADR-003)

- **Substrate scope grows beyond the five components.** Per ADR-003, the substrate is bounded; if scope creeps (a sixth component, a substantial new responsibility), re-evaluate whether the layout still suits — a larger substrate may warrant restructuring (e.g., splitting validators from reconcilers as sub-packages).
- **Pydantic v3 lands and reaches stable release.** Evaluate migration cost against the substrate's pinned version. Pydantic's v1 → v2 migration was substantial (breaking API changes for validators, model config, settings). v2 → v3 may be similar or lighter; decision is a minor-version revision per ADR-003.
- **JSON Schema ecosystem shifts.** If `jsonschema` deprecates or fragments further, revisit. Currently consolidated; not expected to shift in the MVP horizon.
- **Type checker default flips to `ty`** when stable. Per the decision above; minor-version revision.
- **Substrate language flips to TypeScript** per ADR-003's documented alternative (MCP-future scenario). The library picks here become irrelevant; the architectural contracts (five components) carry over.

**Note:** Project initialization for the harness substrate (creating `pyproject.toml`, scaffolding `src/`, configuring CI) should be the first implementation story for the harness — per the step's standard discipline.

## Implementation Patterns & Consistency Rules

The standard step-05 pattern categories assume a typical app architecture (database, API, frontend, state management, loading UIs). Most don't apply to this project — there's no database (state in YAML files), no HTTP API, no frontend, no state-management store, no loading UIs. The categories that genuinely apply are recast around the project's actual surface area: schema/event/marker identifier conventions, state-update discipline (per ADR-005), error-handling discipline (per the loud-fail doctrine), and code style for the harness substrate (per Starter Template Evaluation).

This section is mostly **consolidation** — the binding decisions live in upstream ADRs / SDN-001 / PRD; this section references them rather than re-deriving them. One genuine fork (casing and file-naming convention for YAML artifacts) is decided here for the first time.

### Pattern 1: Casing and File-Naming Convention for YAML Artifacts

**Status:** Decided.
**Date:** 2026-04-25.

**Convention:**

> **Field names** (structural keys describing a payload's structure) → **snake_case**.
> **Identifiers of named entities** (class names, enum values, opaque labels — anything compared as a string by reconciliation checks or rendered as a label in PR bundles) → **kebab-case**.

Dictionary keys naming opaque entities follow the identifier side and stay kebab-case (e.g., `claude-code` in `dependencies.yaml`'s dependency map; `total-block` as a profile enum value; `LAD-skipped` as a marker class). Generic structural keys (e.g., `version_floor`, `by_project_type`) are field names and use snake_case. The dictionary-key-as-entity-identifier boundary is intentional — opaque entity names read more naturally as kebab-case in cross-doc references; preserving the entity-vs-field distinction at the dictionary-key level keeps those references readable.

**Considered and rejected: all-uniform-snake_case for dictionary keys.** Total structural uniformity is appealing, but cross-doc references to entities like `playwright-mcp` or `LAD-skipped` read more naturally as kebab-case opaque identifiers. The boundary refinement is the deliberate trade.

**File naming.** `<kebab-name>.yaml`. We do not use the `.schema.yaml` infix convention common in JSON Schema ecosystems because our cell-1 artifacts are uniformly schemas — there's no schema/instance disambiguation to do. If future work introduces instance files in the same directories that would require disambiguation, revisit.

**Final cell-1 file set:**

- `marker-taxonomy.yaml`
- `orchestrator-event.yaml` (renamed from `orchestrator-event.schema.yaml`)
- `run-state.yaml`
- `dependencies.yaml`
- `_bmad/automation/config.yaml`
- `_bmad/automation/qa-runbook.yaml`

**Retroactive updates applied (this turn):**

- **SDN-001's structural keys updated to snake_case** — `version-floor` → `version_floor`; `version-ceiling-policy` → `version_ceiling_policy`; `version-policy` → `version_policy`; `by-project-type` → `by_project_type`; `marker-class` → `marker_class`; `diagnostic-pointer` → `diagnostic_pointer`; `emits-marker` → `emits_marker`; `sub-classifications` → `sub_classifications`; `schema-version` → `schema_version`.
- **`orchestrator-event.schema.yaml` references renamed** to `orchestrator-event.yaml` throughout the architecture document.
- **Identifiers stay kebab-case** in SDN-001 (dependency keys, profile enum values, sub-classification labels, marker class references).
- **Older artifacts already matching the convention** (marker class names from ADR-003 / 005 / 006, lifecycle state names from PRD) are left as-is. Retroactive updates kept minimal — the convention's job is to prevent future drift, not to force a rewrite of existing artifacts that already comply.

### Pattern 2: Marker Class Naming Convention

Per Pattern 1: kebab-case for marker class names. Already established across ADR-003 / ADR-005 / ADR-006:

- Format: `<domain>-<state>` (e.g., `state-recovery-drift`, `cost-near-ceiling`, `LAD-skipped`).
- Optional sub-classification via `: <cause>` suffix (e.g., `state-recovery-degraded: event-log-missing`, `specialist-crash-mid-execution: timeout-exceeded`).
- Authoritative enumeration in `marker-taxonomy.yaml`. Substrate component 4 reconciliation (per ADR-003, extended per SDN-001) enforces consistency across consumers.

This section consolidates rather than re-derives.

### Pattern 3: Orchestrator-Event Class Naming

Per Pattern 1: kebab-case for event class names (matching marker class convention). The reference to `cost_event` in ADR-006's prose is corrected under this convention to `cost-event`; field names within events stay snake_case (`retry_attempt`, `specialist`, `cost_delta`).

**OTel-derived attributes are external** — `prompt.id`, `claude_code.cost.usage`, `query_source` follow Claude Code's OTel naming conventions and are host-Bridge per ADR-002. Pass-through; don't re-cast under our convention.

### Pattern 4: State Update Discipline

This section consolidates rather than re-derives; the binding decisions live in ADR-005.

- All run-state writes go through atomic-write helpers (temp-file-plus-atomic-rename per NFR-R1).
- No direct writes to `run-state.yaml` outside the helper layer.
- Story-doc canonical for tiebreak on recovery disagreement (per ADR-005's Reading 3).
- Sprint-status writes scoped to non-BMAD-native transitions (specifically the `qa` state per upstream proposal 1).
- Cost-counter writes batch with other run-state writes between specialist completions (per ADR-006 Consequence 2).

#### Pattern 4 (cont.) — `advance_run_state` API surface

Story 2.2 (`_bmad-output/implementation-artifacts/2-2-run-state-schema-atomic-write-helper-layer-with-enforced-write-ordering.md`) operationalizes this pattern. The helper module lives at `tools/loud-fail-harness/src/loud_fail_harness/run_state.py` (substrate library; NOT a sixth substrate component per ADR-003 closure). Public function signature:

```python
def advance_run_state(
    run_state_path: pathlib.Path,
    next_state: RunState,
    *,
    story_doc_callback: Callable[[], StoryDocCallbackResult],
) -> AdvanceResult: ...
```

Structural enforcement: `story_doc_callback` is keyword-only (the `*,` separator) AND non-defaulted. Omitting it raises `TypeError` at call time; mypy strict mode catches the omission at type-check time. There is no API path that writes run-state without a callback — Pattern 4's "story-doc canonical write before run-state advance" invariant is encoded in the type signature, not in a docstring a future contributor can ignore.

Execution order: callback first → on success, atomic-rename run-state second; on callback failure, no run-state mutation, raise `RunStateAdvanceBlocked` carrying the upstream cause and the attempted next-state. Canonical caller-side integration with `loud_fail_harness.story_doc_validator.validate_section_write()` is documented in `run_state.py`'s module docstring.

### Pattern 5: Error Handling Discipline

This section consolidates rather than re-derives; the binding decisions live in the loud-fail doctrine (PRD-level invariant) and ADR-003's marker taxonomy enforcement.

- Every error class corresponds to a marker class in `marker-taxonomy.yaml`.
- Every marker emission includes an actionable-fix-pointer (per FR31).
- Silent error swallowing is forbidden — loud-fail doctrine.
- Errors flow into PR bundle via Stop hook assembly (per ADR-001, ADR-003).
- Three-layer defense-in-depth catches pattern-mismatched errors (per ADR-003 Layer A / B / C, scoped local to that harness).

### Pattern 6: Python Code Style (Harness Substrate)

Reference: Starter Template Evaluation → Sub-decision 2.

PEP 8 + `ruff` (lint + format) + `mypy` (type checking) + `pytest` (tests) + `uv` (env management) + Pydantic v2 (schema validation) + `jsonschema` 4.26.0 (JSON Schema validation). No additional patterns beyond what Starter Template Evaluation specifies.

### Pattern 7: Story-Doc Section Adherence

Reference: FR66 + BMAD story template convention.

- Read/write only documented sections: `## Dev Agent Record`, `## Senior Developer Review (AI)`, `## Review Findings`, `## QA Behavioral Plan` (new — upstream proposal 2), `## Review Follow-ups (AI)`.
- Writes to undocumented sections fail contract validation per FR66 / NFR-S5 and emit `undocumented-section-write` marker.
- Specialists own their respective sections (per ADR-005's multi-writer finding); the orchestrator never writes story-doc sections directly.

### Project Organization (Partial)

Standard step-05 categories on project organization (test location, component grouping, file structure) apply only partially:

- **BMAD skill conventions** for Automator skills — established by reference to `_bmad/bmm/`, `_bmad/tea/`, `_bmad/wds/` directory patterns (per Starter Template Eval Sub-decision 1 + 3).
- **Python `src/` layout** for harness substrate — established (per Starter Template Eval Sub-decision 2).
- **Repo layout itself** — OPEN per Project Context Analysis, gated on plugin-primitive stability research blocker.

No additional consistency rules required at this layer — the questions that matter are answered by Starter Template Evaluation; the questions that remain are gated on external research.

### Categories That Don't Apply

For traceability:

- **Database / table / column naming** — no database.
- **REST endpoint / API path / response wrapper / error format** — no HTTP API.
- **Frontend component / route / state-store / action / selector naming** — no frontend.
- **Loading state patterns** — terminal streaming per NFR-O1 is the equivalent; stream-based, not state-based.
- **Date / time format conventions** — OTel events use ISO 8601; our own events follow OTel's lead. No additional convention required.

These exclusions match the discipline of the PRD's "Not claimed as innovation" and "Not exposed" subsections — explicit non-applicability is evidence of scope discipline.

### Enforcement Guidelines

- **CI-enforced patterns:** marker class enumeration-equivalence (per ADR-003 + SDN-001); orchestrator-event class enumeration-equivalence (per ADR-003); envelope schema-validation (per ADR-003); specialist no-cross-references (per FR62); 20-lines-of-bash hook size limit (per FR61); ≤3 hooks budget (per FR60); `undocumented-section-write` story-doc constraint (per FR66 / NFR-S5).
- **Review-enforced patterns:** field-name casing convention (per Pattern 1); state-update discipline through atomic-write helpers (per Pattern 4); error-handling discipline (per Pattern 5); story-doc section adherence (per Pattern 7).
- **Drift detection:** the BMAD-extension audit (per FR65) catches new conventions; existing patterns referenced here are reviewed for drift each release.

## Project Structure & Boundaries

Standard step-06 expects a single project tree, API/component/data boundaries, and a build/deployment process. None of those map cleanly. This project has **two distribution units** (the Automator runtime and the harness substrate) and a structural picture that requires **three views** to represent honestly: the source repo (what contributors see), the distribution unit (what gets shipped), and the user's filesystem after install (what the user runs against).

### Two Distribution Units (architectural observation)

The project comprises two distinct distribution units with different lifecycles, audiences, and deployment paths:

- **Automator runtime distribution.** Skill bundles, subagent definitions, hook scripts, cell-1 schema files, and config templates. Installs into user BMAD projects via `/plugin install bmad-automation` (target) or git-clone-symlink fallback. Read by the orchestrator and hooks during story loops. Versioned per Developer-Tool Requirements semver policy.
- **Harness substrate (CI tooling).** Python package implementing the five-component substrate per ADR-003. Runs in the Automator's *own development CI* against schemas and reference projects. **Not deployed to user installations** — never appears in a user's BMAD project filesystem. Lifecycle is Automator-development-internal.

This distinction is load-bearing for understanding the project structure: the harness substrate is **at repo root** (`tools/loud-fail-harness/`), not inside `_bmad/automation/`, because `_bmad/automation/` is runtime-deployed-to-users and the harness is not. The lifecycle/audience/deployment mismatch makes colocation incorrect even though both are Automator-internal.

### View 1: Automator Source Repo (what contributors see)

```
bmad-automation/                          # Automator's own repo
├── .git/
├── README.md
├── LICENSE
├── docs/
│   ├── architecture.md                   # ADRs, SDN-001, Implementation Patterns, this section
│   ├── extension-audit.md                # FR65 — BMAD-extension audit; ADR-003 skip-class workflow
│   ├── tea-vs-automator.md               # FR34 — TEA-boundary orientation
│   ├── git-hygiene.md                    # NFR-S3 — git operation safety guidance
│   ├── playwright-mcp-setup.md           # SDN-001 reference
│   └── mobile-mcp-setup.md               # SDN-001 reference (Phase 1.5)
├── skills/
│   └── bmad-automation/                  # Orchestrator skill bundle (ADR-001)
│       ├── SKILL.md                      # BMAD skill convention
│       ├── workflow.md                   # Orchestrator flow logic
│       ├── steps/                        # Step-file architecture
│       └── data/
├── agents/                               # Subagent definitions (ADR-004 dispatch via Task tool)
│   ├── dev-wrapper.md                    # Wraps bmad-dev-story
│   ├── review-bmad-wrapper.md            # Wraps bmad-code-review
│   ├── qa.md                             # Behavioral verification (FR16–FR25)
│   └── lad-wrapper.md                    # Phase 1.5 — opt-in 4th-layer reviewer
├── hooks/                                # ≤3 hooks per FR60
│   ├── subagent-stop.sh                  # FR58 — Dev commit handler
│   ├── stop.sh                           # FR59 — PR bundle assembly
│   └── session-start.sh                  # FR46 — resumability
├── schemas/                              # Cell-1 portable contracts (per ADR-002)
│   ├── envelope.schema.yaml              # Specialist envelope schema (ADR-003)
│   ├── orchestrator-event.yaml           # Orchestrator event schema (ADR-003)
│   ├── marker-taxonomy.yaml              # Authoritative marker enumeration (ADR-003)
│   └── dependencies.yaml                 # Dependency manifest (SDN-001)
├── tools/
│   └── loud-fail-harness/                # CI substrate (ADR-003) — not deployed to users
│       ├── pyproject.toml
│       ├── src/
│       │   └── loud_fail_harness/
│       │       ├── __init__.py
│       │       ├── envelope_validator.py     # Substrate component 1
│       │       ├── event_validator.py        # Substrate component 2
│       │       ├── reconciler.py             # Substrate component 3
│       │       ├── enumeration_check.py      # Substrate component 4
│       │       └── fixture_coverage.py       # Substrate component 5
│       └── tests/
├── examples/                             # Reference artifacts (PRD)
│   ├── envelopes/                        # Canonical envelope examples (per FR Reference Artifacts)
│   ├── pr-bundles/                       # Canonical PR bundle examples
│   ├── synthetic-stories/                # ADR-003 Layer C fixtures (one per skip-class)
│   ├── sample-story-auto-001.md          # FR39 — init-scaffolded sample
│   └── bmad-extension-audit-entry.md     # FR65 — audit entry template
├── config-templates/                     # Defaults shipped with distribution
│   ├── config.yaml.template
│   └── qa-runbook.yaml.template
├── .github/
│   └── workflows/
│       └── ci.yml                        # Runs harness + lint + type-check + reference-project gates
└── .gitignore
```

### View 2: Distribution Unit (what gets shipped)

What `/plugin install bmad-automation` (or git-clone-symlink) lands in a user's BMAD project. **Subset of View 1** — excludes the harness substrate, ADRs, examples-as-development-fixtures, and `.github/`.

```
bmad-automation/                          # Plugin distribution unit
├── plugin.json                           # Claude Code plugin manifest (or equivalent)
├── skills/
│   └── bmad-automation/
│       ├── SKILL.md
│       ├── workflow.md
│       ├── steps/
│       └── data/
├── agents/
│   ├── dev-wrapper.md
│   ├── review-bmad-wrapper.md
│   ├── qa.md
│   └── lad-wrapper.md                    # Phase 1.5
├── hooks/
│   ├── subagent-stop.sh
│   ├── stop.sh
│   └── session-start.sh
├── schemas/                              # Cell-1 contracts shipped as installed defaults
│   ├── envelope.schema.yaml              # Header: "Contract validated by CI; modify with care."
│   ├── orchestrator-event.yaml
│   ├── marker-taxonomy.yaml
│   └── dependencies.yaml
└── config-templates/
    ├── config.yaml.template
    └── qa-runbook.yaml.template
```

**Comment header on installed schema files.** Per the user-customization-discipline calibration: the three contract-bearing schemas (`marker-taxonomy.yaml`, `orchestrator-event.yaml`, `dependencies.yaml`) include a header comment in their installed form indicating "This file encodes a contract validated by CI; modify with care. Customization may break harness reconciliation checks." Distinguishes user-customizable config (`config.yaml`, `qa-runbook.yaml`) from cross-validated contracts.

### View 3: User's BMAD Project Filesystem After Install (what the user runs against)

The merge of View 2's distribution unit (rendered into `.claude/`) plus runtime artifacts that get created and updated during use (under `_bmad/automation/` and `_bmad-output/`).

```
my-bmad-project/                          # User's BMAD project
├── .claude/
│   ├── skills/
│   │   └── bmad-automation/              # Installed via plugin or symlinked
│   │       ├── SKILL.md
│   │       ├── workflow.md
│   │       └── (...)
│   ├── agents/
│   │   ├── dev-wrapper.md
│   │   ├── review-bmad-wrapper.md
│   │   ├── qa.md
│   │   └── lad-wrapper.md                # Phase 1.5
│   └── hooks/                            # Or referenced from settings.json
│       ├── subagent-stop.sh
│       ├── stop.sh
│       └── session-start.sh
├── _bmad/
│   ├── automation/
│   │   ├── config.yaml                   # User-customizable (init scaffolds default)
│   │   ├── qa-runbook.yaml               # User-customizable (init scaffolds default)
│   │   ├── marker-taxonomy.yaml          # Contract — modify with care
│   │   ├── orchestrator-event.yaml       # Contract — modify with care
│   │   ├── dependencies.yaml             # Contract — modify with care
│   │   └── run-state.yaml                # Gitignored — ephemeral cache (ADR-005)
│   ├── bmm/                              # BMAD core module (existing)
│   ├── tea/                              # TEA module (existing — required per FR38)
│   └── ...                               # Other BMAD modules
└── _bmad-output/
    ├── implementation-artifacts/
    │   ├── sample-auto-001.md            # FR39 — init-scaffolded; story-doc files live here
    │   ├── sprint-status.yaml            # BMAD-existing
    │   ├── deferred-work.md              # BMAD-existing
    │   └── (other story files)
    ├── qa-evidence/                      # Gitignored (NFR-P6 size budget; auto-cleaned per FR45)
    │   └── {story-id}/{run-id}/
    └── planning-artifacts/
        └── (...)                         # Existing BMAD outputs
```

### Architectural Boundaries (recast)

Standard API / component / data boundaries don't apply (no HTTP API, no traditional component layer, no database). The integration boundaries that *do* matter for this project:

- **Specialist envelope contract** (per ADR-003) — the load-bearing integration boundary. Every specialist returns this shape; orchestrator parses against schema. Boundary enforcement: harness substrate component 1.
- **Orchestrator-event contract** (per ADR-001 + ADR-003) — the orchestrator's emission boundary. Events flow into run-state and into the harness pipeline. Boundary enforcement: harness substrate component 2.
- **Hook contract** (per ADR-001 + FR57–FR61) — the mechanical-side-effect boundary. Orchestrator emits events; hooks observe and act. Three hooks, ≤20 lines of bash each, CI-enforced.
- **Run-state contract** (per ADR-005) — the orchestrator-domain canonical state. Specialists never write run-state directly; only orchestrator + (some) BMAD-core skills do.
- **Story-doc section contract** (per FR66 + Pattern 7) — the BMAD-canonical artifact boundary. Specialists write their respective sections; orchestrator never writes story-doc directly (per ADR-005's multi-writer finding).
- **Sprint-status contract** (per ADR-005) — the BMAD-lifecycle-state boundary. Multi-writer: BMAD-core skills handle most transitions; orchestrator handles the new `qa` transition (per upstream proposal 1).
- **OTel telemetry pipeline** (per ADR-006) — the cost-tracking boundary. Consumed via prompt.id correlation; orchestrator-owned attribution mapping.
- **Cell-1 schema contract** (per ADR-002 + Pattern 1 + SDN-001) — cross-component consistency boundary. Enforced by harness substrate components 4 and 5 (enumeration-equivalence and fixture-coverage reconciliations).

### Requirements-to-Location Mapping (FR Categories → Structure)

| Capability area | Primary location |
|---|---|
| **Story Loop Execution** (FR1–FR7) | Orchestrator skill (`skills/bmad-automation/workflow.md` + step-files) + run-state.yaml |
| **Retry & Scope Discipline** (FR8–FR15) | Orchestrator skill (retry policy logic) + Dev wrapper agent (`agents/dev-wrapper.md`) |
| **Behavioral Verification (QA)** (FR16–FR25) | QA agent (`agents/qa.md`) + `## QA Behavioral Plan` story-doc section spec |
| **Code Review (Adversarial)** (FR26–FR29) | Review-BMAD wrapper (`agents/review-bmad-wrapper.md`); LAD wrapper at Phase 1.5 |
| **Loud-Fail Surface** (FR30–FR34) | `schemas/marker-taxonomy.yaml` + `tools/loud-fail-harness/` + orchestrator-event emission logic |
| **Installation & Initialization** (FR35–FR44) | Orchestrator skill's `init` slash-command logic + `examples/sample-story-auto-001.md` + config-templates |
| **State & Resumability** (FR45–FR50) | run-state.yaml + `hooks/session-start.sh` + orchestrator skill's `resume`/`status` slash-command logic |
| **Specialist Contracts & Schema Enforcement** (FR51–FR56) | `schemas/envelope.schema.yaml` + harness substrate components 1, 4, 5 |
| **Hooks & Architectural Invariants** (FR57–FR66) | `hooks/*.sh` + harness substrate (CI-enforced invariants) + `docs/extension-audit.md` |

### File Organization Patterns (consolidation)

References Pattern 1 (casing + file naming) for naming conventions. Beyond that:

- **Configuration files** ship as templates in `config-templates/` (View 2); init scaffolds them into `_bmad/automation/{config,qa-runbook}.yaml` (View 3) with documented defaults.
- **Cell-1 schema files** ship as installed defaults in `schemas/` (View 2); land in `_bmad/automation/{marker-taxonomy,orchestrator-event,dependencies}.yaml` (View 3) with contract-header comments.
- **Test fixtures** live in `examples/synthetic-stories/` (View 1) for ADR-003 Layer C coverage; one fixture per skip-class per the substrate component 5 enumeration check.
- **Static assets / public files** — N/A (no UI shell).

### Categories That Don't Apply

For traceability:

- **API endpoints / external service URLs / authentication boundaries** — no HTTP API; no external service surface beyond Claude Code platform integrations (catalogued in `dependencies.yaml`, not as standalone boundaries).
- **Database schema boundaries / data access layer / caching layer** — no database; YAML files are state.
- **Frontend component communication / state-management boundaries** — no frontend.
- **Build process structure / dist directories / static asset organization** — no traditional build for skills (markdown/YAML files); harness substrate has a standard Python package build but trivially conventional.
- **Deployment topology / cloud provider configuration / container orchestration** — local execution within Claude Code; no deployment surface beyond plugin install.

These exclusions match the discipline applied in step-03 and step-05 — explicit non-applicability is evidence of scope discipline, not gaps.

### Development Workflow Integration

- **Development server structure** — N/A. The Automator runs inside Claude Code; "development" is iterating on skill prompts, agent definitions, and harness code in the source repo (View 1) and validating against reference-project runs.
- **Build process** — Python harness substrate builds via `uv build` per Starter Template Eval. Skills/agents/hooks/schemas don't build; they're installed as-is.
- **CI pipeline** (`.github/workflows/ci.yml`) — runs harness substrate components against the source repo's schemas + reference-project fixtures; lint/format/type-check the harness Python; gate releases on harness component checks plus reference-project runs (per Success Criteria → Technical Success).
- **Distribution path** — `/plugin install bmad-automation` (target) or git-clone-symlink fallback. Initialization via `/bmad-automation init` per FR35–FR44.

## Architecture Validation & Completion

Step-07 is a validation pass over the architecture as a whole — coherence, coverage, readiness, gaps. No new architectural content; this section inventories what's done, what's gated on external resolution, and what's correctly deferred to implementation.

The validation applies the same honesty discipline that produced the ADRs: explicit gaps are findings, not failures; gated items have architectural answers contingent on external state; implementation TBDs are scope-correctly-deferred and not architectural gaps.

### Coherence Validation

**Cross-ADR couplings resolved.** Walking the existing artifacts:

- **ADR-001 ↔ ADR-005.** ADR-001's Option A places hooks out-of-band of the orchestrator's reasoning loop; ADR-005's Layer B is architected specifically to close the resulting visibility gap. Cross-coupling explicit in both directions (ADR-001 has the `(added per ADR-003)` revisit condition for hook-out-of-band-burden; ADR-005 names hook-out-of-band-ness as structural).
- **ADR-003 ↔ SDN-001.** ADR-003's substrate component 4 (marker-taxonomy ↔ event-schema enumeration-equivalence) extends to a third reconciliation pair (marker-taxonomy ↔ dependencies.yaml) per SDN-001's marker-class references. Annotation `(extended per SDN-001)` lands inline on ADR-003 Consequence 1; component count stays at five with consumer set growing to two.
- **ADR-004 ↔ ADR-005.** ADR-004 commits to three dispatch-time sub-causes for `specialist-crash-mid-execution` (`tool-level-error`, `silent-corruption`, `timeout-exceeded`); ADR-005's marker class accommodates both dispatch-time (ADR-004) and recovery-time (ADR-005) detection paths. Ownership boundary explicit.
- **ADR-006 ↔ ADR-003.** ADR-006's `cost-event` class extends ADR-003's substrate component 4 to cover cost events in the orchestrator-event log; cross-coupling flagged in ADR-006 Consequence 3.
- **ADR-002 ↔ all schemas.** All cell-1 portable artifacts (envelope schema, orchestrator-event, marker-taxonomy, dependencies.yaml) classified per ADR-002's two-axis matrix at cell 1 (architectural core).
- **Pattern 1 ↔ SDN-001.** Casing convention retroactively applied to SDN-001 structural keys (snake_case) while preserving entity-identifier kebab-case.
- **Step-06 Project Structure ↔ SDN-001 + Starter Template Eval.** Substrate location at `tools/loud-fail-harness/` (repo root) per the lifecycle-distinction reasoning; runtime artifacts at `_bmad/automation/` per the deployed-to-users distinction.

**Pattern consistency.** Implementation Patterns section consolidates rather than re-derives; binding decisions live in upstream ADRs/SDN-001/PRD; no contradictions between patterns and decisions.

**Structure alignment.** Project structure (View 1/2/3) supports all architectural decisions. Cell-1 schemas live in `schemas/` (View 1) and ship as installed defaults in `_bmad/automation/` (View 3) with contract-header comments. Hooks at exactly three (`subagent-stop.sh`, `stop.sh`, `session-start.sh`) per FR60 ≤3 budget.

**Coherence: GREEN.** No contradictions surfaced.

### Requirements Coverage Validation

**Functional Requirements (67 MVP + 12 post-MVP).** Mapped per step-06's FR-to-location table; every capability area has architectural support:

- Story Loop Execution (FR1–FR7) → orchestrator skill + run-state.yaml
- Retry & Scope Discipline (FR8–FR15) → orchestrator skill + Dev wrapper
- Behavioral Verification (FR16–FR25) → QA agent + QA Behavioral Plan section
- Code Review (FR26–FR29) → Review-BMAD wrapper; LAD wrapper at P1.5
- Loud-Fail Surface (FR30–FR34) → marker-taxonomy.yaml + harness substrate + orchestrator-event
- Installation & Initialization (FR35–FR44) → orchestrator skill `init` logic + sample story
- State & Resumability (FR45–FR50) → run-state.yaml + SessionStart hook + resume/status commands
- Specialist Contracts & Schema Enforcement (FR51–FR56) → envelope schema + harness substrate components 1, 4, 5
- Hooks & Architectural Invariants (FR57–FR66) → 3 hook scripts + harness CI checks + extension-audit doc

**Non-Functional Requirements (33 NFRs across 5 themes).** Coverage per theme:

- **Performance & Cost (P1–P6)** — covered by ADR-006 (per-story cost telemetry, OTel pipeline, hybrid persistence). NFR-P4 (context efficiency) relies on Claude Code's compaction primitive; not architectural.
- **Reliability & Durability (R1–R8)** — covered by ADR-005 (cross-state consistency protocol, recovery algorithm, three-store model with story-doc-wins-tiebreak). NFR-R1 atomic-write protocol named; helper API specifics implementation-deferred.
- **Integration & Volatility (I1–I6)** — covered by SDN-001 (per-dependency failure profiles, project-type conditional, opt-in-skip sub-states) + ADR-002 (BMAD-core-absorption migration pathway).
- **Security & Safety (S1–S6)** — narrowly scoped per PRD; S1 (LAD API key handling) covered by SDN-001 sub-classification; S5 (story-doc write scope) covered by Pattern 7 + FR66; S2/S3/S4/S6 noted in PRD with implementation-deferred specifics.
- **Observability & Diagnosability (O1–O8)** — covered by ADR-006 (OTel) + loud-fail markers + ADR-003 substrate. NFR-O1 (terminal streaming) relies on Claude Code's streaming primitive; mechanism gated (see Gap Analysis).

**Coverage: GREEN, with TBD-at-implementation items explicitly carved out (see implementation-deferred category in Gap Analysis).**

### Implementation Readiness Validation

Per-component readiness assessment:

- **Harness substrate** (`tools/loud-fail-harness/`) — GREEN. All architectural commitments made (substrate composition, language choice, reconciliation algorithm, schema enforcement). No external gates. Implementable immediately.
- **Cell-1 schema artifacts** (envelope, orchestrator-event, marker-taxonomy, dependencies) — GREEN. Schemas specified at appropriate altitude; field definition specifics implementation-deferred.
- **Orchestrator skill (content)** (`skills/bmad-automation/`) — GREEN for content. Workflow logic, recovery algorithm, retry policy, dispatch protocol all specified per ADR-001/004/005/006.
- **Specialist subagents** (Dev / Review-BMAD / QA wrappers) — GREEN for content. Wrapper logic, envelope contract, return shape specified.
- **Hook scripts** — GREEN. Three hooks named with purpose and bash size constraint.
- **Skill-bundle install path** — GATED on plugin-primitive stability. Architectural commitments made (plugin-primary + git-clone-symlink fallback per FR35/FR36); finalization of *specifics* awaits primitive stabilization.
- **Repo layout finalization** — GATED on plugin-primitive stability. Step-06 used provisional layout; finalization deferred.
- **State-streaming mechanism** — GATED on Claude Code streaming primitive design. NFR-O1 names the requirement; implementation surface within the streaming primitives is not yet decided.

### Gap Analysis (three-tier yellow, zero red)

**GREEN — architecturally complete:**

- All 6 ADRs (001–006) with revisit conditions
- SDN-001 (dependency failure-profile schema)
- Implementation Patterns (Pattern 1 elicited; Patterns 2–7 consolidated)
- Project Structure (three views with concrete tree)
- Cross-couplings resolved between all artifacts
- Cell-1 portable surface classified
- Substrate composition specified
- Recovery algorithm specified
- Cost-tracking source-and-mechanism committed

**YELLOW — gated (architecturally specified; finalization awaits external state):**

- **Repo layout finalization** — gated on Claude Code plugin-primitive stability. Step-06 used provisional placements with documented assumptions.
- **State-streaming mechanism design** — gated on Claude Code streaming-primitive design surface. NFR-O1 named the requirement.
- **Extension-audit doc location and format** — partially resolved by ADR-003's skip-class-recognition workflow subsection; full doc location/format/cadence is provisionally `docs/extension-audit.md` (View 1) but final placement gated on repo-layout decision.
- **`deferred-work.md` format spec** — research blocker per Project Context Analysis; affects loud-fail handling for `defer`-bucket findings.
- **TEA API surface for orchestrator handoff** — research blocker; affects QA's TEA-boundary observation specifics.
- **Upstream proposal format for BMAD-METHOD** — research blocker; affects how `qa` lifecycle state and `## QA Behavioral Plan` proposals are submitted.
- **Claude Code plugin primitive name and stability** — research blocker; overlaps with repo layout finalization.

**YELLOW — implementation-deferred (architecturally complete; specific values land at implementation time):**

- Specific schema field definitions within run-state, orchestrator-event, envelope (formats specified at altitude; field-by-field specs at implementation)
- Specific budget numbers (evidence size budget, refined cost ceiling per reference-project data)
- Per-specialist timeout overrides (default 15-min specified per NFR-P2; per-specialist tuning at implementation)
- Atomic-write helper API specifics (NFR-R1 names policy; helper interface at implementation)
- Per-story branch naming convention details
- Retry budget configuration model details (default 2 per FR8; configuration schema at implementation)
- QA Behavioral Plan section structure details (drift-detection mechanism specified; format details at implementation)
- Evidence bundle structure details (location and size budget specified; sub-folder organization at implementation)

**RED — architectural gaps that should be filled at architecture phase but weren't: NONE.**

The distinction between yellow-gated and yellow-implementation-deferred matters operationally: gated items have architectural answers contingent on external state (we can't proceed past a certain boundary without external resolution); implementation-deferred items can proceed (details land at the right altitude during implementation work).

### Architecture Completeness Checklist

**Requirements Analysis:** GREEN
- [x] Project context analyzed (Project Context Analysis section)
- [x] Scale and complexity assessed (medium domain, high architectural)
- [x] Technical constraints identified (Runtime Compatibility per SDN-001)
- [x] Cross-cutting concerns mapped (10 concerns enumerated; all addressed)

**Architectural Decisions:** GREEN
- [x] Critical decisions documented (6 ADRs + SDN-001)
- [x] Technology stack specified (Python harness, Pydantic v2, jsonschema, ruff, mypy, pytest, uv per Starter Template Eval)
- [x] Integration patterns defined (envelope contract, hook contract, run-state contract per Boundaries)
- [x] Performance considerations addressed (ADR-006 cost telemetry; NFR-P band; OTel pipeline)

**Implementation Patterns:** GREEN
- [x] Naming conventions established (Pattern 1 — casing + file naming)
- [x] Structure patterns referenced (Pattern 7 — story-doc adherence; Pattern 6 — Python style; project structure in step-06)
- [x] Communication patterns specified (Pattern 3 — orchestrator-event class naming; Pattern 2 — marker class naming)
- [x] Process patterns documented (Pattern 4 — state update; Pattern 5 — error handling via loud-fail)

**Project Structure:** GREEN with provisional locations
- [x] Complete directory structure defined (three views — source / distribution / user filesystem)
- [x] Component boundaries established (Boundaries section recast around envelope/hook/state-store contracts)
- [x] Integration points mapped (specialist envelope, orchestrator-event, hook contracts, OTel pipeline)
- [x] Requirements-to-structure mapping complete (FR-to-location table covering 9 capability areas)
- 🟡 GATED: repo layout finalization pending plugin-primitive stability

### Architecture Readiness Assessment

**Overall status:**
- **READY for harness substrate** (the unblocked MVP path) — `tools/loud-fail-harness/` scaffolding can begin immediately with no architectural blockers.
- **READY for cell-1 schema concretization** — schemas specified; field-level definitions at implementation.
- **READY for skill-bundle content development** (orchestrator skill prompt, specialist wrappers, hook scripts) — content can be developed in parallel with the harness substrate; only install/distribution finalization is gated.
- **GATED for skill-bundle install path finalization** — architecturally specified (plugin-primary + fallback); awaits Claude Code plugin-primitive stabilization for finalization.

**Confidence level:**
- **High** for the architectural-core (cell-1 surface, contracts, substrate composition)
- **High** for the harness substrate's implementation path
- **Medium** for the skill-bundle install layer (gated on plugin primitive)

**Key strengths:**
- Cross-ADR coherence with explicit cross-couplings (no implicit dependencies)
- Honest treatment of architectural gaps (yellow-gated and yellow-implementation-deferred carved out distinctly)
- Two-axis portability classification (host-runtime + methodology) with structural test
- Loud-fail doctrine applied to architecture's own gaps (unknown-unknown route-out, supplement-by-extension pattern)
- Cell-1 portable surface identified and committed to schema-versioned discipline

**Areas for future enhancement:**
- Plugin-primitive stabilization triggers repo layout + extension-audit-doc location finalization
- Phase 1.5 work (mobile MCP, Review-LAD) operationalizes opt-in dependency entries in SDN-001
- Phase 2 work (epic/sprint orchestration, parallel stories, auto-merge) extends the orchestrator's seam-transition model upward

### Implementation Handoff

**The architecture document is the implementation handoff substrate.** The disciplined work across the seven steps — ADRs with revisit conditions, supplement-by-extension cross-coupling, loud-fail honesty about gaps — is what makes this document usable as a reference during implementation. Future contributors and future LLM passes during implementation compose against this document without re-deriving every decision; the discipline wasn't ceremony, it was building the artifact that prevents re-derivation.

**AI agent guidelines:**

- Follow architectural decisions exactly as documented in ADRs/SDN-001/Patterns.
- When a decision-relevant question arises, locate the ADR/SDN/Pattern that bounds it; if the decision is implementation-deferred, take the decision at implementation altitude with rationale recorded in code review.
- When an architectural question arises that *isn't* bounded by an existing artifact, that's a new fork — surface it as a candidate ADR per the BMAD-extension audit (FR65) workflow rather than deciding silently.
- Respect cell-1 portability classification — changes to cell-1 artifacts (schemas, taxonomies, hierarchies) are major-version events.
- Loud-fail discipline applies to architecture itself: if you discover an architectural gap during implementation, the right response is supplement-by-extension (per ADR-002's omission-vs-error pattern), not silent patching.

**Implementation order (dependency-respecting sequence):**

1. **Harness substrate scaffolding** — `tools/loud-fail-harness/pyproject.toml`, `src/loud_fail_harness/` skeleton, CI integration scaffold. Unblocked; can start immediately.
2. **Cell-1 schema concretization** — `schemas/{envelope.schema.yaml, orchestrator-event.yaml, marker-taxonomy.yaml, dependencies.yaml}` with field-level definitions at implementation altitude. Unblocked; can run parallel to or after step 1.
3. **Schema validation + reconciliation logic** — substrate components 1, 2, 3, 4, 5 implemented in `tools/loud-fail-harness/`. Depends on steps 1+2.
4. **Skill-bundle content development** — orchestrator skill (`skills/bmad-automation/workflow.md`, step-files), specialist agents (`agents/dev-wrapper.md`, `review-bmad-wrapper.md`, `qa.md`), config templates. **Depends on steps 2 and 3** for schema concretization (the orchestrator skill's workflow logic and specialist wrappers reference the envelope, orchestrator-event, and run-state schemas). Content development unblocked once schemas land; install/distribution finalization gated on plugin primitive.
5. **Hook scripts** — `hooks/{subagent-stop.sh, stop.sh, session-start.sh}` per the ≤20-lines-of-bash discipline. Depends on steps 2 and 4 (schema concretization for what hooks consume from run-state, and skill-bundle contract for hook-to-orchestrator integration).
6. **End-to-end on reference projects** — Layer C synthetic stories per ADR-003; reference-project gates per Success Criteria → Technical Success. Depends on steps 1–5.

**First implementation priority: step 1 (harness substrate scaffolding).** This is the unblocked MVP path with the shortest dependency chain to validating the architectural-core (cell-1 schemas + reconciliation) end-to-end.

**Out-of-implementation-order items** (gated; awaiting external resolution):

- Final repo layout (post-plugin-primitive)
- Final install path semantics (post-plugin-primitive)
- Extension-audit doc location finalization (post-repo-layout)
- `deferred-work.md` format alignment (post-research)
- TEA API surface integration specifics (post-research)
- Upstream proposal submissions to BMAD core (post-RFC-format research)

These items are tracked as their respective revisit conditions in the relevant ADRs/SDN; implementation proceeds on the unblocked path while these resolve.

## Acceptance Auditor — Epic 2 Single-Layer Rationale (Story 2.9)

This addendum clarifies the existing FR26 / FR28 architecture for the Code Review (Adversarial) capability area (FR26–FR29 at line 776; Requirements-to-Location Mapping row at line 1224). It records WHY the Acceptance Auditor is the chosen single layer at Epic 2 scope; it is not a new architectural decision and does not introduce or renumber any ADR.

**Epic 2 wraps only the Acceptance Auditor layer of `bmad-code-review`'s three-layer adversarial pass.** The Review-BMAD wrapper at `agents/review-bmad-wrapper.md` (Story 2.9) dispatches a single layer; Epic 3's Story 3.1 thickens the wrapper IN PLACE (same agent identity, same envelope contract) to dispatch all three layers (Blind Hunter + Edge Case Hunter + Acceptance Auditor) in parallel. The wrapper's Epic-2 single-layer scope is a walking-skeleton commitment, not a final shape.

**Two reasons the Acceptance Auditor is the right single layer at Epic 2 scope:**

1. **Traceability to acceptance criteria.** The Acceptance Auditor's findings are most directly traceable to story acceptance criteria. This matches Epic 2's AC-1-only QA scope from Story 2.10 (the QA specialist at Epic 2 scope verifies AC-1 only). A single-layer minimum that lines up with AC-driven verification produces an end-to-end loop that exercises the same AC-traceability seam at both the review stage and the QA stage.

2. **Seam-contract churn minimization at Epic 3 thickening.** The Acceptance Auditor's output shape is closest to the eventual three-layer aggregated output. Picking it as the Epic-2 layer minimizes seam-contract churn when Epic 3's Story 3.1 thickens the wrapper to all three layers — the envelope shape (`status`, `artifacts`, `findings`, `rationale`, `failed_layers`) does not change, only the wrapper's internal coverage thickens.

**Contract-violation-not-silent-assumption posture.** If either rationale above is invalidated by Epic 3's discoveries — e.g., the Acceptance Auditor's single-layer behavior conflicts with how it composes into the three-layer parallel pass, or the aggregated-output assumption breaks because cross-layer deduplication reshapes the finding set — the team treats this as a discoverable contract violation rather than a silent assumption. Epic 3 flags it explicitly and swaps to a different layer choice if needed. This posture is the load-bearing reason this rationale is recorded HERE (in the architecture doc) rather than only in the wrapper prose: a future re-implementation that inherits the wrapper but discards the wrapper's prose still inherits the rationale (and the explicit invalidation contract) from this architectural addendum.

**Cross-references.**

- The same rationale (in 2-3-line summary form) is documented in `agents/review-bmad-wrapper.md` under the "Why Acceptance Auditor at Epic 2 scope" heading, with a forward pointer to this addendum.
- FR26 (PRD line 845) and FR28 (PRD line 847) are the bounding requirements; this addendum is a clarification of their Epic-2 surface, not an extension.
- Epic 3's Story 3.1 (epics.md lines 1612-1648) owns the three-layer thickening; Story 3.3 (epics.md lines 1672-1700) owns the orchestrator-side `review-layer-failed` marker emission consuming the wrapper's `failed_layers` declaration.

## QA — Epic 2 AC-1-Only Tier-1-Evidence-Only Rationale (Story 2.10)

This addendum clarifies the existing FR16-FR25 architecture for the Behavioral Verification (QA) capability area (anchored at the Requirements-to-Location Mapping row "Behavioral Verification (QA) (FR16–FR25) | QA agent (`agents/qa.md`) + `## QA Behavioral Plan` story-doc section spec"). It records WHY the QA wrapper at Epic 2 scope verifies AC-1 only at Tier-1 mechanical evidence only; it is not a new architectural decision and does not introduce or renumber any ADR.

**Epic 2 wraps QA at AC-1-only Tier-1-evidence-only minimum.** The QA wrapper at `agents/qa.md` (Story 2.10) verifies the first acceptance criterion only, captures only mechanical Tier-1 evidence (the action happened — HTTP 2xx, element click registered, CLI exit 0), and emits the literal string `"not_applicable"` for `semantic_verification`. Epic 4's Stories 4.1 / 4.2 / 4.6 / 4.7 / 4.8 / 4.9 / 4.13 thicken the wrapper IN PLACE (same agent identity at the same agent-definition file, same envelope contract) to the full FR16-FR25 surface — plan-driven AC iteration across the full AC list, the QA Behavioral Plan generation and persistence, AC-hash drift detection, the three exploratory heuristics, Tier-2 outcome verification, Tier-3 semantic verification where configured, and the env-provisioning lifecycle. The wrapper's Epic-2 minimal scope is a walking-skeleton commitment, not a final shape.

**Three reasons the AC-1-only Tier-1-evidence-only minimum is the right Epic-2 scope:**

1. **Walking-skeleton coherence with the Acceptance-Auditor-only Review-BMAD scope and the single-AC sample-story fixture.** AC-1-only QA scope matches Story 2.9's Acceptance-Auditor-only Review-BMAD scope (the Acceptance Auditor's findings are most directly traceable to acceptance criteria — the same AC-traceability seam) and Story 2.13's single-AC walking-skeleton sample-story fixture (the end-to-end loop is exercised against a single mechanically-verifiable AC). The three together exercise the Epic-2 seam contracts end-to-end without bleeding Epic 4's full QA surface (plan-driven iteration + heuristics + Tier-2 + env-provisioning) into Epic 2.

2. **Endogenous behavior preserved by Tier-1-only scope.** Tier-1-evidence-only scope keeps the wrapper endogenous (no upstream BMAD-core skill composition) and avoids the env-provisioning lifecycle that Tier-2 outcome verification would require. Epic 4's Story 4.3 owns the orchestrator-owned env-provisioning lifecycle per FR7; pulling that surface into Epic 2 would prematurely commit the env-startup/teardown protocol and create env-setup-fail handling Story 4.10 owns. Tier-1 mechanical evidence (request/response traces, DOM snapshots, stdout captures) is producible without env-provisioning machinery — the walking-skeleton sample-story fixture from Story 2.13 will be small enough that env provisioning is trivial or out-of-band.

3. **Epic 4 thickening posture: same agent identity, same envelope contract; only internal coverage thickens.** The wrapper's seam contracts (the dispatch payload conforming to `tea-handoff-contract.yaml`; the envelope conforming to `envelope.schema.yaml` with `ac_results` per FR55) do NOT change at Epic 4. The envelope shape (`status`, `artifacts`, `findings`, `rationale`, `ac_results`) stays put; only the wrapper's internal coverage thickens — `ac_results` cardinality grows from exactly-one to full-AC-list, `semantic_verification` thickens from the literal string `"not_applicable"` to the object form `{tier: 3, status: configured | not_configured}`, and the procedure section grows the three exploratory heuristics + the QA Behavioral Plan persistence + the env-provisioning lifecycle.

**Contract-violation-not-silent-assumption posture.** If any of the three rationales above is invalidated by Epic 4's discoveries — e.g., the AC-1-only minimum proves insufficient to expose a class of failure mode that only emerges at full-AC-list iteration, or the Tier-1-only-without-env-provisioning scope masks an env-binding fragility, or the same-agent-identity thickening posture conflicts with how Epic 4's Story 4.13 wants to restructure the wrapper's internal procedure — the team treats this as a discoverable contract violation rather than a silent assumption. Epic 4 flags the invalidation explicitly and adjusts the seam contract or thickening posture as needed (with the corresponding ADR amendment if the change is non-revisitable). This posture is the load-bearing reason this rationale is recorded HERE (in the architecture doc) rather than only in the wrapper prose: a future re-implementation that inherits the wrapper but discards the wrapper's prose still inherits the rationale (and the explicit invalidation contract) from this architectural addendum.

**Cross-references.**

- The same rationale (in 2-3-line summary form, plus the three named clauses) is documented in `agents/qa.md` under the "Why AC-1 only at Epic 2 scope" heading, with a forward pointer to this addendum.
- FR16 (PRD line 830), FR17 (PRD line 831), FR18 (PRD line 832), FR19 (PRD line 833), FR20 (PRD line 834), FR49 (PRD line 878), and FR55 (PRD line 887) are the bounding requirements; this addendum is a clarification of their Epic-2 surface, not an extension. The full FR16-FR25 surface is owned by Epic 4.
- Epic 4's Stories 4.1 (QA Behavioral Plan section creation), 4.2 (AC-hash drift detection), 4.3 (env-provisioning lifecycle), 4.6 (plan-driven AC iteration), 4.7 (assertion-evidence triple structural enforcement), 4.8 (three-tier evidence hierarchy), 4.9 (three exploratory heuristics), 4.10 (two-escalation-class contracts), 4.12 (evidence persistence size budget), and 4.13 (QA wrapper thickening completion) own the thickening surfaces; the wrapper-side declarations of `status: fail` (verification-fail) and `status: blocked` (env-setup-fail) at THIS story's landing are the seam contracts Story 4.10's escalation-marker emission consumes.
- Story 2.13 (epics.md lines 1559-1590) owns the walking-skeleton sample-story fixture that exercises this wrapper end-to-end against a single-AC mechanically-verifiable AC.

## Bundle Assembly — cell-1 contract / cell-4 host-Bridge boundary (Story 2.11)

This addendum clarifies the existing FR59 / FR50 / FR55 / FR56 architecture for the PR Bundle Assembly capability area (anchored at architecture.md line 130's ADR-002 cell 4 row 4 — "PR bundle **rendering** (markup + assembly via Stop hook)" — and line 189's "PR bundle UX divergence stays cosmetic. PR bundle rendering is host-Bridge (cell 4); the structural contract (cell 1) is rich enough that two hosts implementing the same structural contract produce semantically identical PR bundles"). It records WHY the bundle assembler is a cell-1 portable contract while the bash Stop hook is the cell-4 host-Bridge invocation seam; it is not a new architectural decision and does not introduce or renumber any ADR.

**Epic 2's Story 2.11 lands `bundle_assembly.py` as a substrate Python module composed by the Stop hook via `python3 -m`.** The bundle-assembly substrate at `tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py` (Story 2.11) is the rendering algorithm; the bash Stop hook at `hooks/stop.sh` is a thin invocation seam that parses run-state, computes correlation identifiers, and invokes the substrate via `python3 -m loud_fail_harness.bundle_assembly` exclusively. Epic 5's Story 5.8 + Epic 6's Story 6.1 + Epic 6's Stories 6.4-6.5 thicken the assembler IN PLACE (same module identity at the same `bundle_assembly.py` file, same `assemble_bundle` API signature) to surface escalation variants, the dedicated loud-fail block, and per-specialist × per-retry cost breakdown.

**Five reasons the assembler-as-cell-1 / Stop-hook-as-cell-4 boundary is the right Epic-2 commitment:**

1. **Cell-1 = portable rendering algorithm.** Per architecture.md line 130 + ADR-002 cell 4 row 4: the rendering algorithm IS the cell-1 portable contract. Two hosts implementing the same cell-1 contract MUST produce semantically identical bundles (line 189). Putting the rendering in Python keeps it portable across hosts; the bash Stop hook differs across hosts (Claude Code's hook semantics may differ from another host's) but the rendering does not.

2. **Cell-4 = host-Bridge invocation seam; bash IS the language.** Per ADR-002 cell 4 row 4: bash IS the language; the principle is cell 1. The Stop hook composes the assembler — it does NOT inline rendering decisions in bash. There is no API path through the hook that routes around the assembler's rendering choices (e.g., a bash flag that toggles which sections render, an env-var-driven section ordering). Such a path would couple the rendering to the host-Bridge layer and break the cell-1 portability invariant.

3. **Four thickening flags as functions, not constants.** The four thickening flags (`is_full_review_present`, `is_full_qa_present`, `is_retry_present`, `is_loud_fail_block_present` per `thickening_flags.py`) are **functions** (zero-arg, returning `bool`) rather than module-level constants. The function shape is forward-compatibility scaffolding: downstream-epic thickening MAY add substrate-state probes that depend on filesystem state at orchestrator runtime (e.g., `is_full_review_present()` could probe a review-layer-aggregator artifact's existence; `is_loud_fail_block_present()` could probe the assembler's own section-emission registry) without breaking the call sites in `bundle_assembly.py`. This mirrors the runtime-load-not-compile-time-bake posture established by Story 2.6's `load_marker_class_registry`.

4. **Marker-emission rule is structural, NOT era-based.** The `walking-skeleton-bundle` marker (`schemas/marker-taxonomy.yaml` lines 210-216) emits if and only if `is_loud_fail_block_present()` returns `False` — per the verbatim epic AC at epics.md Story 2.11 lines 1527-1528 + the taxonomy entry's diagnostic_pointer prose "absent loud-fail block triggers the marker, NOT 'Epic 2 era triggers the marker' (rule clarified by Epic 6)". The rule is structural: predicated on the flag's return value, NOT on a hardcoded "if Epic == 2" check. Epic 6's Story 6.1 lands the loud-fail block; its arrival flips the flag in place, which inverts emission without any edit to `bundle_assembly.py`.

5. **Pre-emission registry validation closes Story 2.6's PRE-emission gap.** The assembler resolves `walking-skeleton-bundle` against Story 2.6's runtime `MarkerClassRegistry` BEFORE writing the bundle — registry rejection raises `UnknownMarkerClass` per Pattern 5; defense-in-depth complements Story 1.5's `enumeration_check` (POST-emission validation). The bundle assembler is THIS module's first marker-class emission site; the registry-rejection failure surface is structurally aligned with Story 2.6's dispatch wrapper.

**Contract-violation-not-silent-assumption posture.** If any of the five rationales above is invalidated by Epic 3 / Epic 4 / Epic 5 / Epic 6 discoveries — e.g., the cell-1 portability assumption breaks because a host's hook system requires inline rendering decisions, or the structural-not-era-based marker rule conflicts with how Epic 6's Story 6.1 wants to compose the loud-fail block, or the four-flag-as-functions posture conflicts with how Epic 4 wants to communicate full-QA-presence — the team treats this as a discoverable contract violation rather than a silent assumption. The downstream epic flags the invalidation explicitly and adjusts the boundary (with the corresponding ADR amendment if the change is non-revisitable). This posture is the load-bearing reason this rationale is recorded HERE (in the architecture doc) rather than only in the assembler module's docstring: a future re-implementation that inherits the assembler but discards the docstring still inherits the rationale (and the explicit invalidation contract) from this architectural addendum.

**Cross-references.**

- The same rationale (in 2-3-line summary form, plus the named clauses) is documented in `tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py`'s module docstring under the "Cell-1 contract / cell-4 host-Bridge boundary" heading, with a forward pointer to this addendum.
- architecture.md line 130 (ADR-002 cell 4 row 4) and line 189 (UX divergence stays cosmetic) are the bounding cells; this addendum is a clarification of their Story-2.11 surface, not an extension.
- epics.md Story 2.11 lines 1521-1530 (the four-flag dynamic header rendering + the structural-not-era-based marker emission rule) and `schemas/marker-taxonomy.yaml` lines 210-216 (the `walking-skeleton-bundle` marker class with its rule-clarified-by-Epic-6 diagnostic_pointer) are the verbatim source of the rendering rules this addendum codifies.
- Epic 5's Story 5.8 (escalation-bundle variant) + Epic 6's Story 6.1 (loud-fail block) + Epic 6's Stories 6.4-6.5 (per-specialist × per-retry cost breakdown) own the assembler thickening surfaces; each thickens `bundle_assembly.py` IN PLACE — same module identity, same `assemble_bundle` API signature — only the rendering thickens.

## State-streaming mechanism (Story 2.12 resolution)

This addendum **resolves the OPEN gap-analysis entry at line 843** ("State-streaming mechanism | OPEN | How main-session output streams per-seam transitions; implications for `status` command consistency") by committing the Epic-2 implementation surface for NFR-O1 (terminal streaming) + NFR-O3 (per-specialist diagnostic logs). The OPEN entry stays in the table as historical record per Story 1.4's marker-permanence convention; the gated reference at line 1318 ("State-streaming mechanism — GATED on Claude Code streaming primitive design") also stays — Epic 2's commitment is a sufficient stdout-print-line baseline that survives until the host primitive matures, NOT a final answer to the gating question.

**Epic 2's Story 2.12 lands `event_streaming.py` as a substrate library composing the caller-injected `EventLogAppender` callable (Story 2.4's type alias at `lifecycle_state_machine.py` line 309) with two writes per event in load-bearing order — JSONL persistence FIRST to `_bmad-output/qa-evidence/{story_id}/{run_id}/events.jsonl`, then a single-line render to `sys.stdout` SECOND.** The substrate at `tools/loud-fail-harness/src/loud_fail_harness/event_streaming.py` exports `make_event_log_appender(event_log_path, *, stream=sys.stdout, fsync=True)` (the appender factory), `format_event_for_stream(event)` (the pure renderer), and `default_event_log_path(qa_evidence_root, story_id, run_id)` (the canonical path resolver). The orchestrator skill at `skills/bmad-automation/steps/run.md` step (e) constructs the appender ONCE per `/bmad-automation run` invocation and reuses the closure at every subsequent seam (state-transition, dispatch, return) so all events flow into a single events.jsonl file AND a single terminal stream. Epic 6's Stories 6.5 + 6.7 thicken the streaming format with marker emissions (cost-near-ceiling, specialist-timeout, etc.) by ADDING new dispatch-table branches to `format_event_for_stream`'s `_BRIEF_DETAIL_RENDERERS`; existing branches are NOT touched. Per-specialist log persistence (NFR-O3) is the additive `runtime_duration_ms` field on Story 2.6's `persist_dispatch_log` JSON payload — additive only; existing readers (Story 2.11's `bundle_assembly.assemble_bundle` per its AC-5) are unaffected.

**Five reasons the JSONL-on-disk-plus-stdout-print baseline is the right Epic-2 commitment:**

1. **Cell-1 algorithm = JSONL serialization + per-class brief-detail dispatch.** Per ADR-002 cell 4 row 4: the rendering algorithm IS the cell-1 portable contract. The `format_event_for_stream` pure function + the `_BRIEF_DETAIL_RENDERERS` dispatch table are the algorithm; they are testable, deterministic given input, and would render identically under any host. The `stream` parameter (defaulting to `sys.stdout`) is the cell-4 host-Bridge seam — a future host with a richer streaming primitive swaps the sink without touching the substrate's contract.

2. **JSONL FIRST / terminal SECOND is the durability invariant.** Per ADR-005 Sub-decision (c)'s recovery-algorithm contract: the orchestrator-event log is the canonical record from which run-state can be reconstructed. A crash between the two writes leaves the events.jsonl line on disk (the canonical record Story 8.1 will replay) even if the practitioner missed the terminal line. The reverse ordering (terminal first, persist later) would create a window where the practitioner sees "seam advanced" but the recovery machinery has no record — a silent durability violation forbidden by the loud-fail doctrine.

3. **Append-only single-writer log = `open("a")` per event, NOT `tempfile` + `os.replace`.** Per ADR-001 Consequence 1: the orchestrator emits one event at every seam transition. The events.jsonl file is APPEND-ONLY single-writer; the per-line append is atomic at the OS layer for sub-PIPE_BUF write sizes; the rename-after-write protocol used by `persist_dispatch_log` (which REPLACES the per-specialist log on each call) would be both overkill and break the append semantics. Pattern 4's atomic-write discipline is honored at the per-line granularity, NOT per-file. The fsync per event is the durability cadence — when the orchestrator advances a seam, the practitioner expects the on-disk record to be durable BEFORE the next dispatch; the fsync makes that guarantee structural.

4. **Sensor-not-advisor: the appender does NOT re-validate events.** Pattern 5 + Epic 1 retro Insight #4 (the 3-caller rule): the upstream emitters (`commit_transition`, `make_specialist_dispatched_event`, `make_specialist_returned_event`) already validate against `schemas/orchestrator-event.yaml`. The streaming substrate trusts the input is schema-valid; double-validation is waste and creates a feedback loop where THIS substrate would catch upstream bugs the upstream tests would miss. The substrate's own diagnostic surface is `OSError` propagation — disk-full / permission-denied / etc. surface unchanged to the caller per Pattern 5.

5. **Forward-compat with Epic 6 marker thickening is structural.** Per the verbatim epic AC at epics.md Story 2.12 lines 1551-1553, "Epic 2's streaming events do NOT include marker emissions beyond what Story 2.6 emits structurally"; Epic 6's Story 6.5 + 6.7 thicken the streaming format with marker emissions via additive dispatch-table entries. The unknown-event-class fallback in `format_event_for_stream` (which renders `[<event_class>] <event_id>` for any class not yet in the dispatch table) IS the forward-compat extension point — Epic 6's wiring extends the table with a per-class branch; existing branches stay verbatim. The forward-compat is structural (a dispatch-table extension), NOT temporal (a "wait until Epic 6" check inside the renderer).

**Contract-violation-not-silent-assumption posture.** If any of the five rationales above is invalidated by Epic 5 / Epic 6 / Epic 8 discoveries — e.g., the cell-1 portability assumption breaks because a host's streaming primitive requires bidirectional dialogue (not just a one-way write to a sink), or the append-only single-writer assumption breaks because a future story adds a second event-emitter that races against the orchestrator's appender, or the fsync-per-event cadence proves too slow at production seam-transition rates — the team treats this as a discoverable contract violation rather than a silent assumption. The downstream story flags the invalidation explicitly and adjusts the boundary (with the corresponding ADR amendment if non-revisitable).

**Cross-references.**

- The same rationale (in 2-3-line summary form, plus the named clauses) is documented in `tools/loud-fail-harness/src/loud_fail_harness/event_streaming.py`'s module docstring under the "Why JSONL `open(\"a\")` (not `tempfile` + `os.replace`)" + "Why the closure does NOT re-validate events" headings, with a forward pointer to this addendum.
- architecture.md line 843 (the OPEN gap-analysis entry) + line 1318 (the gated reference) stay verbatim — they are the historical record this addendum resolves; future readers see both the gap and the resolution.
- epics.md Story 2.12 lines 1532-1557 (the four-AC verbatim source) and `schemas/orchestrator-event.yaml` lines 86-95 + 113-243 (the closed `event_class` enum + the four per-class branches the dispatch table covers at Epic 2) are the verbatim source of the rendering rules this addendum codifies.
- Story 8.1 (SessionStart reattachment full implementation per FR46 + ADR-005 Sub-decision (c)) will replay events.jsonl line-by-line to reconstruct in-flight run-state on recovery; the canonical events.jsonl path THIS addendum commits to is the input contract for that replay.
- Epic 6's Story 6.4 (per-specialist × per-retry cost telemetry) consumes the existing `(prompt_id, retry_attempt, specialist)` correlation triple in the per-class event branches; Story 6.5 (cost streaming + cost-near-ceiling 75% threshold) extends the dispatch table with the `cost-event` branch; Story 6.7 (specialist-timeout / hook-failed / context-near-limit markers fully wired into PR bundle) extends the dispatch table with marker-bearing event-class branches. None of these touch existing branches — all are additive per the forward-compat clause above.
