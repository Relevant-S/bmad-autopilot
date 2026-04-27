# TEA-handoff boundary contract

This document is the **architectural contract** (audience: orchestrator, QA-wrapper, and run-state implementers reading at code-write time; purpose: machine-checkable boundary that the schema fragment at [`schemas/tea-handoff-contract.yaml`](../schemas/tea-handoff-contract.yaml) encodes structurally) for the orchestrator-to-QA dispatch seam — distinct from the sibling [`docs/tea-vs-automator.md`](./tea-vs-automator.md), which is the **user-facing educational doc** (audience: practitioners; purpose: orientation, FR34 first-run message text source, whose `## First-Run Orientation Message` section is read at runtime by Story 7.8). Two docs about the same boundary topic, two distinct consumption paths — editing one does not require editing the other. The four spike questions below correspond verbatim to the open research blocker at architecture.md line 850 ("TEA API surface for orchestrator handoff") plus the question (d) addition framed in epics.md line 1159; each section carries a one-sentence load-bearing answer, rationale cited by line number, and trace evidence.

## Question A — Does the orchestrator await TEA completion before dispatching QA?

### Answer

No. The orchestrator does **not** coordinate per-story with TEA at runtime: TEA workflows are practitioner-invoked skills that operate on the test suite; the orchestrator's per-story loop dispatches Dev → Review-BMAD → QA with no awaited TEA seam between Review-BMAD and QA.

### Rationale

- architecture.md line 809 — "TEA validates tests; Automator exercises product. QA reads AC only — never TEA test files." names the boundary with no phrase suggesting orchestrator/TEA per-story coordination.
- PRD FR3 (line 811) and FR5 (line 813) enumerate the orchestrator's specialist sequence as Dev → Review-BMAD → QA across the lifecycle states `ready-for-dev → in-progress → review → qa → done`; TEA is absent from this sequence.
- PRD FR38 (line 863) and `schemas/dependencies.yaml` lines 90–97 declare TEA as `total-block` at `init` and `total-block` at `runtime`, meaning TEA's *presence* is enforced (the Automator will not run without TEA installed), but the runtime block is on absence-of-the-module, not on awaiting per-story TEA output.
- ADR-005 line 441 — "the orchestrator is a pure run-state writer plus sprint-status writer (for non-BMAD-native transitions); never a story-doc writer" — and line 440 — "the Automator's wrappers invoke these BMAD-core skills and observe returns; they do *not* buffer-and-write-through-orchestrator" — together establish that the orchestrator's runtime concerns are run-state, sprint-status, and event-log writes; per-specialist coordination is BMAD-skill-mediated, not TEA-mediated.

### Trace evidence

- `_bmad/tea/workflows/testarch/bmad-testarch-atdd/SKILL.md` — practitioner-invoked workflow ("Use when the user says 'lets write acceptance tests'"); no orchestrator-callable surface.
- `_bmad/tea/workflows/testarch/bmad-testarch-automate/SKILL.md` — practitioner-invoked workflow ("Use when user says 'lets expand test coverage'"); no orchestrator-callable surface.
- `_bmad/tea/workflows/testarch/bmad-testarch-trace/SKILL.md` — practitioner-invoked workflow ("Use when the user says 'lets create traceability matrix'"); no orchestrator-callable surface.
- `_bmad/tea/workflows/testarch/bmad-testarch-test-design/SKILL.md`, `bmad-testarch-test-review/SKILL.md`, `bmad-testarch-framework/SKILL.md`, `bmad-testarch-ci/SKILL.md`, `bmad-testarch-nfr/SKILL.md` — all eight TEA workflows are slash-command-invoked skills triggered by practitioner phrasing, not by orchestrator dispatch primitives.
- REJECTED: any per-story TEA-orchestrator coupling. Each TEA workflow's `customize.toml` activation surface is for the practitioner-driven invocation lifecycle; the orchestrator has no API into TEA.
- KEPT (orchestrator-side concern): TEA *presence* check via `dependencies.yaml`'s `total-block` profile is consumed by Story 7.3's `init` precondition flow, not by the per-story dispatch boundary this contract encodes.

## Question B — What TEA artifacts does QA ignore vs consume?

### Answer

QA consumes **zero** TEA artifacts: every output of every TEA workflow is REJECTED as a QA-consumable input; QA's verification input is the story's acceptance criteria text only, sourced from the story doc.

### Rationale

- PRD FR16 (line 830) — "QA reads only the story's acceptance criteria as its verification input; it does not read TEA test files, dev tests, review findings, or commit diffs (QA-independence-from-TEA-artifacts invariant)."
- architecture.md line 809's "QA reads AC only — never TEA test files." compresses the same invariant into the architectural boundary statement.
- PRD line 752 names "QA independence from TEA artifacts" as one of the four review-enforced invariants; this contract MOVES that invariant from review-enforced to schema-enforced (at the dispatch surface) by structurally constraining `tea_artifacts_consumed` to the empty array.
- The architectural reason for the invariant: if QA reads TEA's test files, QA inadvertently grades-its-own-test-suite — re-running assertions TEA already validated and reporting them as behavioral evidence (per `docs/tea-vs-automator.md` line 23 — the load-bearing operational rule).

### Trace evidence

The eight TEA workflows produce the following artifact families. All are REJECTED as QA-consumable per FR16.

| TEA workflow | Goal (per `SKILL.md`) | Artifact families produced | Disposition |
|---|---|---|---|
| `atdd` | Generate red-phase acceptance test scaffolds (TDD red-green-refactor) | Red-phase test files, AC-derived test stubs | REJECTED — these ARE TEA test files; FR16 forbids QA reading them. |
| `automate` | Expand test automation coverage / generate test suite | Test files (unit, integration, e2e) | REJECTED — TEA test files. |
| `trace` | Generate traceability matrix + quality gate decision (PASS/CONCERNS/FAIL/WAIVED) | Traceability matrix; quality-gate verdict | REJECTED — quality-gate verdict is TEA's grade of the test suite, not QA's verdict on the running product; mixing them collapses the gap FR16 names. |
| `test-design` | Produce epic-level test plan grounded in risk and testability | Test plan document | REJECTED — test plan is TEA's design; QA's behavioral plan (FR23, written by QA itself) is the QA-side analog and is independently authored. |
| `test-review` | Review test quality using best-practices validation | Test-quality findings | REJECTED — findings about the test suite, not about the running product. |
| `framework` | Initialize test framework (Playwright/Cypress) with fixtures, helpers, config | Test framework scaffolding | REJECTED — framework configuration is for TEA's test runner, not for QA's drive of the running product (QA uses Playwright MCP per FR17, not Playwright-as-a-framework). |
| `ci` | Scaffold CI/CD quality pipeline with test execution, burn-in loops, artifact collection | CI pipeline configs, burn-in loop scripts | REJECTED — CI pipeline runs TEA's tests; QA's per-story dispatch is orthogonal. |
| `nfr` | Assess NFRs (performance, security, reliability, maintainability) before release | NFR assessment reports | REJECTED — NFR reports are pre-release release-readiness artifacts; QA's per-story behavioral verification operates inside the per-story loop. |

KEPT as orchestrator-side dispatch context (i.e., what QA RECEIVES at dispatch — none of which is a TEA artifact):

- The story's acceptance criteria text (sourced from the story-doc's `## Acceptance Criteria` section — a BMAD-core-owned section, not a TEA artifact).
- The `story_id` (BMAD-domain identifier).
- The `run_id` (orchestrator-domain identifier; correlates with run-state.yaml entries per ADR-005).
- The `project_type` (one of `web`, `api`, `mobile` — selects the QA driver per FR17).
- The structurally-empty `tea_artifacts_consumed` array (encoding the FR16 invariant as a schema property).

The dispatch payload's content is the schema fragment's Question (d) answer below; none of its fields name a TEA workflow output.

## Question C — How does the boundary surface in run-state?

### Answer

The dispatch payload conforming to this contract is written to `run-state.yaml` by the orchestrator immediately before QA dispatch, atomically per NFR-R1, as a non-canonical cache record; recovery on disagreement reconstructs the payload from the story doc's AC list and the orchestrator-event log per ADR-005's three-store recovery model.

### Rationale

- ADR-005 lines 441–442 — the orchestrator owns run-state.yaml writes; the dispatch payload (a flow-control input that QA reads) is run-state-domain because it's "orchestrator-domain canonical for flow control."
- ADR-005 line 509 — "the post-recovery run-state must conform to the same schema that pre-crash run-state conforms to, with the same field invariants" — the dispatch payload is a field of run-state at QA-dispatch time; this contract's schema fragment is the structural commitment ADR-005 references.
- PRD NFR-R1 (atomic-write protocol via temp-file-plus-atomic-rename per ADR-005 Consequence 6) covers run-state.yaml writes; the dispatch payload write follows the same protocol.
- PRD NFR-R8 (line 952) — "story-doc canonical, run-state cache; story-doc writes complete before run-state advances." The story-doc's AC list (which the dispatch payload's `ac_list` field copies from) is canonical; run-state's cached copy is a derived projection that recovery reconstructs from the canonical source.
- Per ADR-005's recovery algorithm (Consequence 2 lines 510–525): on session start, if event log is present and shows QA was dispatched but run-state.yaml is missing or partial, the orchestrator reconstructs from story-doc's AC list + the event log's dispatch event; the run-state copy is reproducible.

### Trace evidence

- The schema fragment at `schemas/tea-handoff-contract.yaml` is a standalone JSON-Schema-2020-12 document; Story 2.2's run-state schema imports this fragment by `$ref` per the AC-4 forward-compatibility commitment, embedding the contract as a sub-shape of the broader run-state structure.
- The dispatch payload's per-field invariants (notably `tea_artifacts_consumed: maxItems: 0`) carry into the run-state copy unchanged; a non-empty `tea_artifacts_consumed` field in run-state would fail the same schema validation, propagating the FR16 invariant to the cache surface as well as the dispatch surface.
- KEPT in run-state: the dispatch payload (cache, schema-validatable, recoverable from canonical sources). REJECTED from run-state: TEA workflow outputs of any kind (consistent with Question B's per-workflow rejection table).

## Question D — What does QA need to receive at dispatch beyond the AC list?

### Answer

At MVP scope (Story 2.10 minimal QA wrapper at AC-1-only Tier-1 evidence), QA needs the AC list plus four contextual fields: `story_id` (for traceability and PR-bundle anchoring), `run_id` (for run-state correlation per ADR-005), `project_type` (selects the QA driver per FR17), and the structurally-empty `tea_artifacts_consumed` array (encodes the FR16 invariant as a schema property); env-handle and qa-runbook references are deferred to Story 4.3 / 4.6 via additive MINOR bumps when full Epic-4 QA wrapper lands.

### Rationale

- PRD FR16 (line 830) — `ac_list` is QA's verification input source; no other dispatch field can substitute.
- PRD FR17 (line 831) — "QA drives the running product independently — via Playwright MCP for web project types, via HTTP for API project types" — `project_type` is the discriminator that selects driver behavior.
- PRD FR3 (line 811) and FR4 (line 812) — `story_id` is the per-story identifier that anchors the orchestrator's per-story branch and PR bundle assembly; QA's per-AC result records (`ac_results` per FR18, structurally enforced by `envelope.schema.yaml`) reference the story by id.
- ADR-005 line 441 — `run_id` is the orchestrator-domain identifier that correlates dispatch with run-state.yaml's stored run record; required for recovery semantics (per Consequence 1 line 509).
- PRD FR16 again — `tea_artifacts_consumed` is the structural encoding of the QA-independence-from-TEA-artifacts invariant; its presence in the schema with `maxItems: 0` makes a future violation a schema-validation failure rather than a runtime-discipline lapse.
- PRD FR7 (line 815) — orchestrator-owned env provisioning is a real concern, but the env *handle* (port, dev server URL, MCP endpoint) is Story 4.3's full FR7 deliverable; Story 2.10's minimal QA wrapper consumes Tier-1 evidence on AC-1 only and does not require env-handle at dispatch. Adding `env_handle` now would over-engineer the contract relative to Story 2.10's scope; the schema's additive-MINOR-bump discipline (per the contract-header) supports adding it cleanly when 4.3 lands.
- PRD FR23 (line 838) — `## QA Behavioral Plan` is QA-WRITTEN (QA's first-run output), not dispatch-CONSUMED; the schema deliberately does not include a `qa_plan_to_consume` field because the plan is constructed from the AC list, not handed to QA.
- PRD FR24a/FR24b (lines 839–840) — escalation classes are QA's *return* envelope concern (per `envelope.schema.yaml`'s `findings.bucket` field), not dispatch-CONSUMED.
- PRD NFR-O3 (line 982) — structured per-specialist log; the dispatch event itself goes into the orchestrator-event log with timestamp, but `dispatch_timestamp` does not need to be part of the dispatch payload (QA does not read it; the orchestrator-event log carries it independently).

### Trace evidence

- KEPT (dispatch payload required fields): `story_id`, `run_id`, `project_type`, `ac_list`, `tea_artifacts_consumed`. Justified per the rationale citations above.
- REJECTED (not in MVP dispatch payload): `env_handle` (Story 4.3 owns full FR7; additive when needed), `qa_runbook_ref` (Story 4.x consumes via QA Behavioral Plan, not via dispatch), `dispatch_timestamp` (NFR-O3 covers this in the event log; not dispatch-consumed), `qa_plan_to_consume` (FR23 plan is QA-written, not dispatch-consumed), `commit_sha` / `parent_run_id` / `dispatch_user_id` (no FR/NFR/ADR justification at this story; would be unjustified field-set inflation per Dev Notes do-not-do row 9).
- Schema-fragment encoding decision: `additionalProperties: false` at the top level — Story 2.6's dispatch wrapper cannot silently introduce additional fields without an explicit schema bump (per AC-2's closed-by-default discipline). The contract's drift-resistance is the structural property `additionalProperties: false`, not a documentation rule.

## Schema fragment cross-reference

The operational encoding of the four answers above lives at [`schemas/tea-handoff-contract.yaml`](../schemas/tea-handoff-contract.yaml) — a standalone JSON-Schema-2020-12 fragment with a stable `$id` (`https://bmad-autopilot.local/schemas/tea-handoff-contract.yaml`), `additionalProperties: false`, and the load-bearing structural constraints:

- `required: [story_id, run_id, project_type, ac_list, tea_artifacts_consumed]` — the minimum dispatch surface per Question D.
- `tea_artifacts_consumed: { type: array, maxItems: 0, items: { type: string } }` — the FR16 invariant encoded as a schema property; non-empty fails validation.
- `project_type: { type: string, enum: [web, api, mobile] }` — closed enum matching `dependencies.yaml`'s `by_project_type` keys (lines 101, 117, 127, 138 of `schemas/dependencies.yaml`).

The doc-vs-schema split is deliberate: this doc carries the prose answers and trace evidence; the schema carries the structurally-validatable shape. **Drift between the two is a review-time finding** — if this doc says "field X is required" but the schema does not list X under `required:`, or vice versa, the inconsistency is caught at code review and reconciled by editing the more-out-of-date side. Both files version-bump together when the contract changes (see the schema's contract-header comment for the bump-rule discipline mirrored from `marker-taxonomy.yaml` lines 30–36).

## Consumers

The downstream stories that consume this contract — directly by reading the schema, indirectly by inheriting its boundary, or by referencing it for orientation:

- **Story 2.2** (run-state schema; epics.md lines 1183–1217). The run-state schema imports this fragment by `$ref` (relative path `tea-handoff-contract.yaml#` for the whole-schema reference idiom, or `tea-handoff-contract.yaml#/$defs/<name>` if `$defs` are introduced by future contract bumps; the absolute-URI form `https://bmad-autopilot.local/schemas/tea-handoff-contract.yaml#…` is equivalent). Story 2.2 is unblocked from scaffolding its broader run-state schema with a placeholder before this story finishes; the placeholder swap to the real `$ref` is mechanical.
- **Story 2.6** (Task-tool dispatch wrapper; epics.md lines 1309–1345). The wrapper marshals the dispatch payload conforming to this schema and serializes it into the Task-tool prompt's structured-input section per ADR-004 Consequence 1. The schema's `additionalProperties: false` ensures the wrapper cannot silently introduce additional fields without an explicit schema bump.
- **Story 2.10** (Epic-2-minimal QA wrapper; epics.md lines 1454–1481). The wrapper consumes the dispatch payload at QA invocation and validates against this schema. Per epics.md line 1464: "it consumes the QA-dispatch input per Story 2.1's TEA-handoff contract — reads AC-1 only from the story doc and ignores TEA test files (FR16 invariant honored from day one)."
- **Story 4.3** (full env-provisioning lifecycle; epics.md lines 1858–1892). Inherits this contract without redefinition per epics.md lines 1174–1177; full FR7 env provisioning may add an optional `env_handle` field via additive MINOR schema bump when implemented.
- **Story 4.6** (plan-driven AC iteration framework; epics.md lines 1958–1994). Inherits this contract without redefinition; full FR23 plan-driven AC iteration consumes the same `ac_list` shape this fragment defines.
- **Stories 4.1, 4.2, 4.7–4.13** (full Epic 4 QA wrapper FR16–FR25; epics.md). Each inherits this contract; any drift between Epic 4's behavior and this contract is a contract-violation finding, not a re-litigation (per epics.md line 1177).
- **Story 7.8** (FR34 first-run TEA-boundary orientation message; epics.md lines 3108–3136). Reads `docs/tea-vs-automator.md`'s `## First-Run Orientation Message` section at runtime, not this file. This contract is referenced by Story 7.8's orientation text only as the architectural anchor practitioners can inspect if they want the contract-level detail behind the orientation message; no runtime extraction.

### TEA-related skip class assessment (per AC-5)

The spike considered whether a previously-unenumerated TEA-related skip class is justified. **No new skip class is surfaced by this spike.** Rationale:

- A non-empty `tea_artifacts_consumed` array fails the schema's `maxItems: 0` constraint at validation time. The dispatch-payload validator (Story 2.6 / 2.10, which validates instances against `tea-handoff-contract.yaml`) surfaces this as a JSON-Schema-2020-12 per-field diagnostic; the `envelope_validator` (substrate component 1, story 1.2) is a distinct validator for specialist envelopes and does not validate dispatch payloads.
- Skip-class semantics in `marker-taxonomy.yaml` are reserved for *absences/degradations* (e.g. `LAD-skipped`, `Tier-3-not-configured`, `env-setup-failed`, `heuristic-skipped`) — runtime conditions where a phase or capability is unavailable but the loop continues. A schema-validation failure of `tea_artifacts_consumed` is a contract bug (the dispatch wrapper produced an invalid payload), not a skip; treating it as a skip class would conflate validation failures with phase absence.
- TEA itself has a `total-block` profile at runtime per `dependencies.yaml` line 96; if TEA disappears mid-run, the existing `total-block` enforcement halts the flow. No new skip class is needed for the TEA-disappears case either.

Conclusion: the existing marker taxonomy at 27 entries (post-Epic-1) is sufficient; this story does NOT propose a follow-up PR against `schemas/marker-taxonomy.yaml`. If a future story (Story 2.10's QA wrapper, Story 4.x's full QA) surfaces a runtime condition where a TEA-related skip would be informative, the bump rule (Story 1.4) is the route for adding it then.
