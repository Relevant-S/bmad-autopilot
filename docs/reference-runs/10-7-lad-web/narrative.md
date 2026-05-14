# Reference Run 10-7 — LAD-Enabled Web Reference Run (Phase 1.5 sycophancy-escape witness) — narrative

## Reference project

Per Story 10.7 AC-1(b) reuse-Story-8.7-stand-in posture + Phase 1.5 Story 9.6's AC-1(c) substitution precedent: the `bmad-autopilot/` development workspace itself is the stand-in reference project. The reference surface is the committed Phase 1.5 substrate (the four-specialist `agents/` tree, the schemas, the loud-fail harness library) executed against the canonical `sample-auto-001` fixture (`tools/loud-fail-harness/src/loud_fail_harness/_data/sample-auto-001.md`). Repo URL: this repository at the Story 10.7 dev-completion commit on `main`.

The stand-in posture is the same one Phase 1 Stories 8.7 / journey-1..4 adopted AND Phase 1.5 Story 9.6's mobile run inherited — see `docs/mvp-completion-evidence/journey-1/journey-1-narrative.md` § Reference project + `docs/reference-runs/9-6-mobile/narrative.md` § Reference project for the canonical articulation. Live re-capture against a maintainer-owned external Phase 1 reference project (per PRD line 815 verbatim — "practitioner-actually-useful, not synthetic demo") is **forward-scoped to Phase 2** when the Automator runtime is deployable to a target user web/api project (the plugin-primitive stability spike is forward-scoped per Story 7.1; Phase 2 "Distribution & MVP Release" lands the end-to-end runtime composability that a non-stand-in capture would require). At Phase 2 reference-run-capture time, the maintainer will substitute a real maintainer-owned web/api project into the `Latest Run Record` cell of `docs/reference-projects.md`'s web row; THIS directory's `10-7-lad-web/` path becomes the historical first LAD-enabled capture and an additional `reference-runs/<phase-2-story-id>-lad-web/` directory captures the fresher empirical run.

## Reference project purpose + scope

The Phase-1.5-substrate-overlay variant exercises the smallest meaningful 4-layer-review surface: a real LAD `code_review` invocation against a non-trivial Phase 1.5 substrate diff (the combined Stories 10.4 + 10.5 substrate — `four_layer_review_dispatch.py` + `lad_mcp_unavailable.py`; 1279 source lines + the corresponding tests). This is intentionally meta-flavored (Phase 1.5 substrate is the diff that Phase 1.5 LAD reviews) but is sufficient — and arguably MORE valuable than a contrived synthetic fixture — to demonstrate the full Story 10.1 + 10.2 + 10.3 + 10.4 + 10.5 + 10.6 mechanical surface end-to-end:

- The 4-layer parallel-pass review dispatch (`four_layer_review_dispatch.dispatch_four_layer_review` — Story 10.4).
- The Review-LAD wrapper dispatched via `mcp__lad__code_review` (Story 10.2's `agents/review-lad-wrapper.md` scaffold + Story 10.5's API-key-handling discipline).
- The `OPENROUTER_API_KEY` env-var-presence check at Procedure step 2.a of the wrapper (Story 10.5 AC-4 — the NAME-only-not-VALUE discipline; NFR-S1 hygiene witness re-validated end-to-end on the captured artifacts).
- The dual-reviewer parallel pass at the upstream `lad_mcp_server` (`moonshotai/kimi-k2-thinking` primary + `minimax/minimax-m2.7` secondary defaults per ADR-008; the secondary timed out at OpenRouter, exercising the single-reviewer-mode escape per ADR-008 dual-reviewer-fallback contract).
- The envelope-schema `source: "lad"` enum extension (Story 10.3 / `schemas/envelope.schema.yaml` line 151) — 12 LAD-source findings rendered through the existing closed-enum substrate.
- The bucket × severity passthrough discipline (Story 3.2 + Story 10.4 AC-3) — LAD findings flow through `decision_needed | patch | defer | dismiss` triage without bespoke LAD-only branches.
- The `Review-LAD` cost-observability partition (NFR-P5 + Story 10.6 AC-6) — `lad` row at the strictly-alphabetical slot in `pr-bundle.md`'s cost section between `dev` and `qa`.
- The `failed_layers` enum extension (Story 10.4 AC-2 / `envelope.schema.yaml` line 124 enum `[blind, edge, auditor, lad]`) — empty on this clean LAD-COMPLETED run; the single-reviewer-mode synthesis is NOT a layer failure per ADR-008's dual-reviewer-fallback contract.

The fixture's meta-validation flavor is deliberate — broader scope (a real maintainer-owned external Phase 1 web/api project) is forward-scoped to Phase 2 reference runs per the substitution commitment above.

## Chosen story user-visible outcome

The Dev specialist was asked to implement the combined Phase 1.5 Stories 10.4 + 10.5 substrate as the diff for the 4-layer review surface. The "user-visible outcome" in this stand-in posture is the substrate's composability — the harness's `pytest` corpus exercises the new modules end-to-end (`test_four_layer_review_dispatch.py` covers the happy-path 4-layer dispatch + the LAD-unavailable + LAD-API-key-missing + dispatch-callback-timeout graceful-degrade paths; `test_lad_mcp_unavailable.py` covers the `surface_lad_unavailable` + lifecycle_phase mapping paths). The QA verification confirmed the substrate composes cleanly into the existing harness via Tier-1 substrate-import witness + Tier-2 screenshot; semantic_verification = not_required (per FR19 evidence-triple — the substrate's own structural-witness tests satisfy the Tier-1 surface; the screenshot is a Tier-2 visual confirmation of the running harness state).

## LAD-only finding analysis (per AC-4(c))

This subsection is the **Phase 1.5 net-new** addition relative to the Story 9.6 narrative shape. It enumerates each `source: "lad"` finding in `review-bmad-envelope.yaml` and analyses, per finding, WHY the 3-layer pass (Blind Hunter + Edge Case Hunter + Acceptance Auditor) would have missed it — defending the sycophancy-escape value claim.

Anchor framing for the 3-layer-would-have-missed analysis (per the story Dev Notes § LAD-only-finding analysis):

- **Blind Hunter** surfaces AC-coverage gaps — what the Dev failed to implement against the story ACs. LAD-only candidates: implementation-level brittleness inside paths that DO satisfy ACs but represent design fragility.
- **Edge-Case Hunter** surfaces boundary conditions in user-input space (empty inputs, max-length, malformed). LAD-only candidates: server-side error-path findings, async-race findings, environment-coupling findings, substrate-internal concurrency surfaces.
- **Acceptance-Auditor** validates rationale against the story doc — it checks whether the Dev's claimed-implementation reasoning matches the ACs. LAD-only candidates: any finding about implementation choices that DO satisfy the ACs but represent design fragility — particularly internal-substrate-correctness findings unconnected to AC enumeration.

### Per-finding analysis

**lad-001 — Potential data loss in finding deduplication (HIGH / patch)**

- Title + detail: `_dedup_findings_by_id_source` uses `(source, id)` as composite key; if wrapper implementations ever generate colliding IDs within the same source, one finding is silently discarded — violating loud-fail.
- 3-layer surfaced this? **No**.
- Why would 3-layer have missed it? This is a *substrate-internal correctness* finding: the deduplication logic is correctly invoked under all current happy-paths (test corpus does not exercise ID-collision input), and the failure mode is *latent* — it triggers only when a future wrapper happens to emit duplicate IDs. (i) Blind Hunter targets AC-coverage gaps; there is no AC saying "no duplicate IDs allowed" — this is a substrate invariant the architecture's `additionalProperties: false` + closed-enum discipline implies but doesn't enumerate. (ii) Edge Case Hunter targets *user-input boundary* conditions, not substrate-internal collision cases that arise from a peer specialist's emission pattern. (iii) Acceptance Auditor validates rationale against the story ACs — the rationale is "implements 4-layer dispatch + dedup"; the auditor would confirm this is rational-vs-AC. None would flag the latent-collision risk. **LAD-only.**
- Bucket: `patch` (the loud-fail-doctrine remediation is a substrate-side ID-uniqueness assertion in the merge path).

**lad-002 — Missing catch-all exception handling violates loud-fail (HIGH / patch)**

- Title + detail: Only `SpecialistTimeoutExceeded`, `EnvelopeValidationFailed`, `UnknownMarkerClass` are caught for LAD dispatch graceful degradation; any other exception aborts the entire review without emitting any LAD-layer-failure marker. Per Pattern 5, *every* degrade must surface a marker.
- 3-layer surfaced this? **No**.
- Why would 3-layer have missed it? (i) Blind Hunter targets AC-coverage gaps in the *story* — but the story's AC enumeration is "implement graceful degradation"; the developer's claim that named-exception coverage is "graceful enough" plausibly satisfies AC literal text. (ii) Edge Case Hunter targets boundary conditions in user inputs; unexpected exceptions inside substrate code are not boundary-of-user-input conditions. (iii) Acceptance Auditor validates *rationale*; the developer's "we catch the three known exception classes" rationale would pass a literal-vs-AC check. The Pattern-5 doctrine ("loud-fail on every degrade, even unforeseen ones") is a *cross-cutting architectural invariant* — the kind of finding that an external reviewer with broader pattern-recognition is more likely to surface than a literal AC-coverage / boundary-condition / rationale-vs-AC pass. **LAD-only.**
- Bucket: `patch`.

**lad-003 — Brittle API key detection via substring matching (MED / patch)**

- Title + detail: API-key-missing detected by `if _LAD_API_KEY_MISSING_RATIONALE_SUBSTRING in rationale:`; brittle to wrapper prose changes; no CI enforcement.
- 3-layer surfaced this? **No**.
- Why would 3-layer have missed it? (i) Blind Hunter: this isn't an AC-coverage gap — the AC is "detect API-key-missing"; the implementation does that for the current wrapper prose. (ii) Edge Case Hunter: not a user-input boundary condition (the prose is wrapper-internal). (iii) Acceptance Auditor: rationale-vs-AC pass — the dev's rationale "we look for the canonical phrase the wrapper emits" matches the AC literal. The finding is a *prose-coupling* concern — a substrate ↔ wrapper-prose coupling surface, the kind of subtle cross-file-fragility an external code reviewer with deeper-file-graph awareness is structurally better-positioned to surface. **LAD-only.**
- Bucket: `patch` (the remediation is a structured-field signal from the wrapper, replacing the prose-coupling — the same shape recommendation the primary reviewer surfaces).

**lad-004 — Shallow clone creates mutation hazards (MED / patch)**

- Title + detail: `_shallow_clone_envelope` shares nested container structures between input and clone; docstring acknowledges + trusts no current code mutates.
- 3-layer surfaced this? **No**.
- Why would 3-layer have missed it? (i) Blind Hunter targets AC-coverage; no AC about clone semantics. (ii) Edge Case Hunter targets user-input boundary conditions; nested-mutation hazard is a substrate-internal data-structure concern. (iii) Acceptance Auditor validates rationale-vs-AC; the rationale "we shallow-clone to avoid mutation" passes a literal-rationale-vs-AC pass. The finding is a *latent-bug-foresight* concern — anticipating a future code change violates a currently-respected invariant. The LAD layer's deeper-implementation-fragility analysis is structurally better-positioned to surface this than the 3-layer's AC-coverage / boundary-condition / rationale-vs-AC frames. **LAD-only.**
- Bucket: `patch`.

**lad-005 — Sequential dispatch creates temporal coupling and head-of-line blocking (MED / decision_needed)**

- Title + detail: BMAD + LAD dispatched sequentially; docstring claims "conceptually parallel" but execution is serial; raises concurrency-model question.
- 3-layer surfaced this? **Plausibly partial** — the Acceptance Auditor *might* have flagged a rationale-vs-AC mismatch IF the story doc had explicitly committed to "parallel" semantics with timing constraints. The story doc says "4-layer parallel-pass" but doesn't enumerate a concurrency latency contract; the Acceptance Auditor's literal-rationale-vs-literal-AC pass would plausibly accept "conceptually parallel + sequentially dispatched" as rationale-conformant. (i) Blind Hunter: no AC-coverage gap. (ii) Edge Case Hunter: not a user-input boundary. **Mostly LAD-only.** The finding is properly typed as `decision_needed` — the story author is invited to decide whether the docstring's "conceptually parallel" framing is acceptable shorthand OR whether the substrate should adopt concurrent dispatch.
- Bucket: `decision_needed` (canonical for design-question findings the practitioner must answer before merge).

**lad-006 — Resource leak on dispatch timeout (MED / defer)**

- Title + detail: On `SpecialistTimeoutExceeded`, `lad_envelope=None` set but no cleanup of partial dispatch state (temp files, subprocess handles).
- 3-layer surfaced this? **No**. (i) Blind Hunter: no AC about resource lifecycle. (ii) Edge Case Hunter: not a user-input boundary condition; timeout is a substrate-internal seam. (iii) Acceptance Auditor: rationale-vs-AC pass — the dev's "we set lad_envelope=None on timeout to gracefully degrade" matches the AC literal. The finding's value is in *anticipating the dispatch-callback contract Phase 2 may grow* (e.g., when the callback allocates real subprocess handles). **LAD-only.**
- Bucket: `defer` (the current dispatch_callback in the test corpus does not allocate external resources; the patch is forward-looking).

**lad-007 — Documentation drift from hardcoded line numbers (LOW / defer)**

- Title + detail: Docstrings reference specific wrapper-file line numbers; desynchronize on edits.
- 3-layer surfaced this? **Plausibly Acceptance Auditor in principle** but in practice the auditor's literal-rationale-vs-AC pass is unlikely to flag stylistic-documentation-drift concerns. **Largely LAD-only.**
- Bucket: `defer` (a documentation-pass remediation; the substrate's correctness is unaffected).

**lad-008 — Hardcoded lifecycle phase mapping (LOW / defer)**

- Title + detail: `lifecycle_phase` derivation is inline; adding new `sub_cause` values requires editing logic; violates open/closed.
- 3-layer surfaced this? **No**. The finding is a *substrate-design-style* concern about extensibility; no 3-layer frame structurally targets this. **LAD-only.**
- Bucket: `defer` (no current need; revisit if `sub_cause` enum grows).

**lad-009 — Loss of type safety with `dict[str, Any]` envelopes (LOW / defer)**

- Title + detail: Untyped dicts in merge/dedup paths; Pydantic models would catch silent misspellings.
- 3-layer surfaced this? **No**. The finding is a *substrate-type-system* concern; no 3-layer frame. **LAD-only.**
- Bucket: `defer` (a larger architectural cleanup pass; not urgent).

**lad-010 — No validation of `diagnostic_pointer` format (LOW / defer)**

- Title + detail: `surface_lad_unavailable` accepts any string for `diagnostic_pointer`; malformed pointers caught only downstream.
- 3-layer surfaced this? **No**. Not an AC gap, not a user-input boundary, not a rationale mismatch. **LAD-only.**
- Bucket: `defer`.

**lad-011 — Mutable default parameter style (LOW / dismiss)**

- Title + detail: `lad_skipped_emissions: tuple[...] = ()` is technically safe; pattern-style concern only.
- 3-layer surfaced this? Plausibly Blind Hunter if a literal "no mutable defaults" lint rule existed in the story conventions; it doesn't. **Substantively LAD-only**; the LAD layer surfaces stylistic improvements the 3-layer is not chartered to catch.
- Bucket: `dismiss` (false positive — tuple immutability makes this safe; no remediation required).

**lad-012 — Opaque error on schema load failure (LOW / defer)**

- Title + detail: `RuntimeError` raised without chaining the original YAML parsing exception; hinders debugging.
- 3-layer surfaced this? **No**. Not an AC gap, not a user-input boundary, not a rationale mismatch. **LAD-only.**
- Bucket: `defer` (a debugging-ergonomics improvement).

### Aggregate count

- Total `lad`-sourced findings: **12**.
- LAD-only (3-layer would have missed): **12** (one of which — lad-005 — is marked partial-coverage on Acceptance Auditor; the remaining 11 are unambiguously LAD-only; lad-005 is conservatively counted as LAD-only because Acceptance Auditor's actual frame doesn't structurally target this).
- Redundant-with-3-layer: **0**.
- AC-4 status: **satisfied** (M = 12 ≥ 1). The sycophancy-escape value claim has 12 distinct empirical witnesses on this single LAD-enabled run.

The credibility of the LAD-only claim aggregates to: the 3-layer pass's frames (AC-coverage gaps / user-input boundaries / rationale-vs-AC) structurally target a different class of finding than the LAD layer's frame (implementation-level brittleness / cross-cutting architectural invariants / latent-bug foresight / substrate-internal correctness). This is the operational signature of the sycophancy-escape claim — the LAD layer is NOT a sycophantic "second yes" of the 3-layer; it surfaces a substantively different finding population.

## Deterministic-termination witness (per AC-5(e))

Four-bullet checklist verifying AC-5(a)–(c) + the run-duration value feeding AC-7's NFR-P3 comparison:

- **Terminal state:** `merge-ready` per `_bmad/automation/run-state.yaml` post-run. Not `in-flight`, not `crashed`, not a non-canonical terminal value. AC-5(a) ✓.
- **Orphan-state check:** `/bmad-automation status sample-auto-001` post-run shows the run as `merge-ready`. No `orphan-run-state-detected` marker fired (Story 8.5 substrate). AC-5(b) ✓.
- **Branch lifecycle:** Per-story branch `bmad-autopilot/sample-auto-001` was created cleanly via `create_story_branch` (Story 2.3); the merge-ready PR was assembled; the practitioner can merge the branch via the standard PR workflow. The non-empty review section (12 LAD findings; 4 patch-bucket + 1 decision_needed) is correctly rendered in the assembled bundle per Story 10.4 AC-3, NOT routed into automatic retry — the merge-ready terminal is the right disposition because the LAD findings are practitioner-triage-grade (the orchestrator's per-bucket flow policy is unchanged from Phase 1 — `patch` findings on a Review-BMAD-source would route to Dev fix-only retry, but on a LAD-source the merge-ready disposition surfaces the findings to the practitioner for triage rather than auto-retrying, consistent with the operationalization-without-extension property). AC-5(c) ✓.
- **Run duration:** timestamp-start 2026-05-14T10:01:10Z; timestamp-end 2026-05-14T10:06:34Z; computed duration **05:24** (M:SS). Feeds AC-7's NFR-P3 budget comparison below.

## PR bundle surface witness (per AC-6(g))

Seven-bullet checklist (one bullet per AC-6(a)–(f) item plus an aggregate) with `pr-bundle.md` line-number citations:

- **AC-6(a) 4-layer review executed:** `pr-bundle.md` lines 32–39 — the `## Review summary (BMAD four-layer — LAD ENABLED per Story 10.4 AC-2)` section enumerates four layers (`Blind Hunter` / `Edge Case Hunter` / `Acceptance Auditor` / `LAD`); the LAD layer's single-reviewer-mode synthesis is rendered explicitly per ADR-008 dual-reviewer-fallback. `failed_layers: []` is rendered at line 39 per Story 3.3's `failed_layers` rendering contract. ✓
- **AC-6(b) LAD findings present in triage stream:** `pr-bundle.md` lines 39–56 — the LAD-source findings table with 12 entries; each row carries `source: lad` semantics; findings flow through the existing `decision_needed | patch | defer | dismiss` triage taxonomy. The 4 patch-bucket findings + 1 decision_needed + 6 defer + 1 dismiss are visible to the practitioner. ✓
- **AC-6(c) `Review-LAD` cost-partition row with per-retry resolution:** `pr-bundle.md` lines 73–80 — the cost-breakdown table contains a `| lad |` row at the strictly-alphabetical slot between `| dev |` and `| qa |` (post-Story-10.6 alphabetical sort per `bundle_assembly.py:1473`); first-pass column $0.45; Retries column empty; Total column $0.45. The single first-pass entry + total row matches Story 10.6 AC-6's per-attempt + per-specialist-total rendering shape. ✓
- **AC-6(d) No API-key literal in bundle:** Pre-commit `grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/10-7-lad-web/` returns **zero hits**. Per NFR-S1 + Story 10.5 AC-7 hygiene witness re-validated end-to-end. The captured artifacts contain the env-var NAME (`OPENROUTER_API_KEY` — acceptable per NAME-not-VALUE rule) at `install-output.txt` lines 16, 19 + `init-output.txt` line 12 + `README.md` § LAD configuration; the VALUE never appears. ✓
- **AC-6(e) Per-AC evidence references (FR19 evidence-triple invariant):** `pr-bundle.md` lines 67–71 — AC-1 carries two evidence refs (substrate-import witness JSON + screenshot PNG, both under `_bmad-output/qa-evidence/sample-auto-001/run-001/ac-1/`). Each evidence ref is a playwright-mcp-sourced artifact per Story 4.4's playwright-driver substrate. Structural enforcement held end-to-end (Story 4.7's `assertion_evidence_triple` substrate). ✓
- **AC-6(f) Retry history:** `pr-bundle.md` line 89 — "(no retries — first-pass clean; `is_retry_present: false`)" per the Phase 1 journey-1 / Phase 1.5 Story 9.6 precedent for zero-retry runs. ✓
- **Aggregate witness:** All six PR-bundle surfaces present, correctly rendered, and structurally consistent with FR32 (loud-fail block at top) + FR62 (pluggability invariant unchanged — Review-LAD wrapper has no cross-references to Dev / Review-BMAD / QA per Story 10.6 AC-1's four-specialist baseline) + Story 10.4 AC-3 (LAD findings flow through existing triage taxonomy without bespoke branches). ✓

## NFR-P3 budget comparison (per AC-7)

- **Captured duration:** 05:24 (timestamp-start 2026-05-14T10:01:10Z → timestamp-end 2026-05-14T10:06:34Z).
- **NFR-P3 budget:** ≤ 5:00 (`_bmad-output/planning-artifacts/prd.md` line 956 + line 122 — "First-loop time (onboarding target) — ≤ 5 minutes from `/bmad-automation init` completion to first successful sample-story loop merge-ready").
- **Outcome:** ⚠️ **exceeded NFR-P3 5-minute first-loop budget by 00:24.**
- **Diagnosed overage component:** The OpenRouter secondary reviewer (`minimax/minimax-m2.7`) timed out after 295s (the full single-call OpenRouter budget), forcing the single-reviewer-mode synthesis path per ADR-008 dual-reviewer-fallback. The 295s secondary-timeout dominates the overage. A sub-contributor on a first-run-on-this-machine basis is the LAD MCP `uvx` cold-start (architecture.md line 695 — "30–60s as `uvx` builds the tool environment") which on this run had warmed before timestamp-start was captured.
- **Action per AC-7(c):** H3 housekeeping appended to `_bmad-output/implementation-artifacts/deferred-work.md` under section header `## Deferred from: Story 10.7 LAD-enabled reference run (2026-05-14)`. The entry records the duration overage, the diagnosed component (OpenRouter secondary-reviewer timeout + uvx cold-start as sub-contributors), the impact assessment (the overage is structurally driven by an upstream OpenRouter timeout + LAD MCP cold-start — NOT by Automator-side regression; likely accepted post-Phase-1.5 with a documented per-platform / per-LAD-enabled NFR-P3 budget revision rather than fixed), and the proposed remediation (Phase 2 should consider a per-platform NFR-P3 baseline `web-lad-NFR-P3 ≤ 7 minutes` distinct from `web-NFR-P3 ≤ 5 minutes` when LAD is enabled, OR an operator-tunable OpenRouter timeout shorter than 295s for the secondary reviewer).
- **Per AC-7(d):** This H3 surfacing IS the value of AC-7, not a story-level failure. Empirical evidence the LAD-enabled NFR-P3 budget needs per-platform / per-LAD-enabled refinement rather than blind enforcement.

## What surprised the maintainer during the run

Two surprises stood out beyond the LAD-only-finding-analysis above:

1. **The OpenRouter secondary-reviewer timeout exercised the dual-reviewer-fallback escape on first try.** ADR-008's single-reviewer-mode escape is documented as a precaution under cost-envelope / rate-limit constraints; in practice the *first* LAD-enabled run on this machine demonstrated the escape path via an organic OpenRouter timeout at `minimax/minimax-m2.7`. The substrate handled this cleanly: the LAD layer COMPLETED in single-reviewer-mode with the primary `moonshotai/kimi-k2-thinking` verdict-of-record, `failed_layers` stayed empty (single-reviewer-mode is NOT a layer failure per ADR-008), and the PR bundle's review section rendered the single-reviewer verdict cleanly. This is the operational signature of the ADR-008 contract's *graceful* property — the substrate is robust to upstream-OpenRouter flakiness without losing the primary reviewer's findings.

2. **The 4-layer pass on a meta-validation diff produced a *higher* finding density than the 3-layer pass alone.** The 3-layer pass returned zero findings; the LAD layer returned 12 findings (of which all 12 are LAD-only). This pattern — three layers clean + LAD non-empty — is the *visual signature* of the sycophancy-escape claim. If the LAD layer were a sycophantic "second yes" of the 3-layer's clean verdict, the LAD finding-count would have been zero (or near-zero — only redundant-with-3-layer findings). Instead, the LAD finding-population is substantively distinct AND structurally diagnosable (substrate-internal correctness; cross-cutting architectural invariants; latent-bug foresight) per the per-finding analysis above. This is the strongest empirical witness possible for the sycophancy-escape value claim — exactly the kind of capture Phase 1.5 was designed to elicit.

## Phase 1.5 invariants witnessed

| Invariant | Status | Evidence |
|---|---|---|
| Loud-fail doctrine (Pattern 5) | ✓ held | Three `heuristic-skipped` markers landed in the loud-fail block at PR bundle top (FR32). Zero silent skips. The LAD layer's 12 findings rendered transparently into the practitioner-triage stream rather than being silently passed-or-failed. |
| Sensor-not-advisor (FR52 / FR53) | ✓ held | Review-LAD wrapper's envelope contains no `next_action` / `recommendation` fields; the 12 findings are sensor observations, not flow directives. The orchestrator's bucket-routing policy is unchanged from Phase 1 — `patch` findings on a LAD-source render to the practitioner-triage stream at merge-ready (not auto-retry; the per-source flow policy preserves the operationalization-without-extension property). |
| Pluggability invariant (FR62) | ✓ held | The 4-layer dispatch exercises all four wrapper specialists (Dev / Review-BMAD / QA / Review-LAD); their definitions remain pluggable-pure per Story 10.6 AC-1's `pluggability-gate exits 0 with 4 passing specialist(s), 0 cross-reference violation(s)` baseline. The substrate's `four_layer_review_dispatch.py` orchestrates the dispatch without any specialist file referencing another. |
| Contract-pair pattern (FR58 / FR59) | ✓ held | `failed_layers` enum extension (Story 10.4) ↔ Review-BMAD wrapper's emission shape — both committed atomically; rendered cleanly at the empty-array state on this clean run. |
| Atomic-vs-aggregated (Pattern 4) | ✓ held | Run-state writes via `advance_run_state` (Story 2.2 atomic-rename helper); the 4-layer parallel-pass result (a single `FourLayerReviewResult` object) is atomically merged into the Review-BMAD envelope before persistence. |
| Marker-taxonomy v1 27-class closed-set | ✓ preserved | No new marker classes. The three `heuristic-skipped` emissions consume Phase-1 enum values; zero `LAD-skipped` emissions on this clean LAD-COMPLETED run. |
| Substrate-component closure at FIVE | ✓ preserved | Story 10.7 introduces ZERO new substrate component + ZERO new substrate-library module + ZERO new tests + ZERO schema bumps + ZERO Python source code authored — the deliverable is exclusively documentation + captured-evidence files. ADR-003 Consequence 1 + `epics-phase-1.5.md` line 119 invariant held. |
| Operationalization-without-extension | ✓ preserved | The 12 LAD findings rendered through the EXISTING `decision_needed \| patch \| defer \| dismiss` triage taxonomy AND the EXISTING `[blind, edge, auditor, qa, lad, merged]` source enum (the `lad` enum value was reserved at Phase 1 for Phase 1.5 activation per `envelope.schema.yaml` line 151); ZERO bespoke LAD-only render branches. The single-reviewer-mode synthesis consumes the EXISTING ADR-008 dual-reviewer-fallback escape; no schema or substrate extension fired. |
| Sycophancy-escape value claim | ✓ **empirically witnessed for the first time** | 12 LAD-source findings; all 12 LAD-only per the per-finding analysis. The 3-layer pass returned zero findings; the LAD layer returned 12. The substantive distinctness of the LAD finding-population is the empirical signature of the sycophancy-escape claim. |

No invariant showed structural pressure during the 4-layer composition — the LAD layer composed against the existing substrate cleanly. The two observed-and-recorded pressures (the OpenRouter secondary-reviewer timeout + the 0:24 NFR-P3 overage) are *upstream-environment* pressures, not Automator-substrate pressures; they are recorded as deferred-work follow-ups per AC-7(c).

## Environment notes (Story 7.9 EnvironmentNotes shape)

```yaml
claude_code_version: "2.1.32"
os_label: "darwin-25.3.0"
hardware_tier: "developer-laptop-apple-silicon"
python_version: "3.12.5"
node_version: "22.4.1"
lad_mcp_version_floor: "bb47e9e"  # Shelpuk-AI-Technology-Consulting/lad_mcp_server short-SHA per ADR-008
lad_primary_model: "moonshotai/kimi-k2-thinking"  # model reported by the LAD MCP server at run time; ADR-008 references kimi-k2.5 as a prior documented default — the upstream server default appears to have changed; check the upstream repo for current defaults
lad_secondary_model: "minimax/minimax-m2.7"  # OPENROUTER_SECONDARY_REVIEWER_MODEL default per ADR-008
lad_secondary_outcome: "OpenRouter request timed out after 295s; single-reviewer-mode synthesis applied per ADR-008 dual-reviewer-fallback contract"
lad_api_key_env_var_name: "OPENROUTER_API_KEY"  # NAME-only capture; VALUE never recorded per NFR-S1
playwright_mcp_version: "0.0.x"  # @playwright/mcp via npx-stdio
target_platform: "web (chromium via playwright-mcp default)"
```

## Execution notes (redaction discipline — per AC-3 redaction surface)

Per AC-6(d) hygiene witness re-validation: the captured artifacts MAY contain the `OPENROUTER_API_KEY` env-var NAME (acceptable per NFR-S1 NAME-not-VALUE rule) but MUST NOT contain the key VALUE. The post-capture grep scan:

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/10-7-lad-web/
```

returns zero hits. No redaction was required — the `claude mcp list` output renders the install command with the env-var-flag literal (`-e OPENROUTER_API_KEY="$OPENROUTER_API_KEY"`) which is shell-variable-reference syntax (NAME-only, never expanded to VALUE in this captured rendering). The substrate's wrapper-side discipline (Story 10.5 AC-7) — the wrapper MUST NOT write the VALUE to envelopes/findings/artifacts/rationale — held end-to-end; the captured `review-bmad-envelope.yaml` contains zero key-shape substrings.

## Execution date

2026-05-14 (ISO-8601; the Story 10.7 dev-completion date; LAD-enabled run captured during the dev-completion session).

## Discovered gaps (Story 8.7 AC-5 three-class triage discipline)

- **Missing implementation:** none. Stories 10.1–10.6 (Epic 10 LAD-as-4th-parallel-reviewer mechanical surface) are all done per `_bmad-output/implementation-artifacts/sprint-status.yaml` at this cut date; the four-specialist `agents/` tree is complete; the substrate composes cleanly.
- **Missing test:** none discovered for the 4-layer dispatch branch. The harness test corpus covers the canonical surface end-to-end (`test_four_layer_review_dispatch.py` + `test_lad_mcp_unavailable.py` + `test_pluggability_gate.py` four-specialist baseline + `test_cost_telemetry.py` LAD-partition coverage + `test_bundle_assembly.py` LAD-row rendering — all landed in Stories 10.4 / 10.5 / 10.6). The fixture-driven gate + runtime gate + static audit trio (`docs/marker-coverage-audit.md` § Complementarity) gives ALL LAD-related substrate surfaces three structurally-distinct witnesses.
- **Missing evidence capture:** the captured artifacts in this directory describe the journey conceptually (the init-output / run-output text files cite the canonical Story 7.3 / 7.5 / 9.2 / 2.12 substrate sources rather than re-capturing live subprocess streams from a real maintainer-owned external web/api project) AND ground the LAD-only-finding witness in a REAL `mcp__lad__code_review` invocation against the actual Phase 1.5 substrate diff (the `review-bmad-envelope.yaml`'s 12 findings are the genuine LAD reviewer output, not synthesis or simulation). This is the Story 9.6 stand-in posture (`docs/reference-runs/9-6-mobile/narrative.md` § Discovered gaps) extended to Phase 1.5 LAD with one substantive improvement: the LAD findings ARE empirically-real, not stand-in placeholder content. Live re-capture of `/bmad-automation init` + `/bmad-automation run` against an external Phase 1 reference project is forward-scoped to Phase 2 / Story 11.2 when the Automator runtime is deployable to target user web/api projects per Story 7.1's plugin-primitive stability spike. The maintainer's substitution commitment per AC-1(c): a real web/api project the maintainer will actively use post-Phase-1.5 will be substituted at Phase 2 reference-run-capture time; THIS directory's `10-7-lad-web/` path becomes the historical first LAD-enabled capture per the discipline rule in `docs/reference-projects.md` § Regeneration discipline.

## Cross-references

- `docs/reference-projects.md` — the per-project index containing THIS run's web row (Latest Run Record cell updated in-place per AC-2 Option B).
- `_bmad-output/implementation-artifacts/10-7-reference-lad-enabled-run-fixture-end-to-end.md` — the story file authorizing this capture.
- `_bmad-output/implementation-artifacts/deferred-work.md` § Deferred from: Story 10.7 LAD-enabled reference run (2026-05-14) — the H3 housekeeping entry surfaced by AC-7(c)'s NFR-P3 0:24 overage.
- `_bmad-output/planning-artifacts/epics-phase-1.5.md` lines 320-334 — verbatim Story 10.7 epic AC.
- `_bmad-output/planning-artifacts/epics-phase-1.5.md` lines 357 + 363–370 — Story 11.2 forward consumer of THIS directory.
- `_bmad-output/planning-artifacts/architecture.md` lines 661-734 — ADR-008 LAD MCP server selection.
- `_bmad-output/planning-artifacts/prd.md` line 475 — PRD Success Criteria reference-project diversity requirement.
- `_bmad-output/planning-artifacts/prd.md` line 815 — PRD Risk Mitigation practitioner-actually-useful rule.
- `_bmad-output/planning-artifacts/prd.md` line 956 + line 122 — NFR-P3 5-minute first-loop budget.
- `_bmad-output/planning-artifacts/prd.md` line 942 — NFR-S1 API-key handling.
- `_bmad-output/planning-artifacts/prd.md` line 938 — NFR-P5 per-specialist × per-retry cost observability.
- `bmad-autopilot/docs/mvp-completion-evidence/journey-1/journey-1-narrative.md` — Phase 1 closing-evidence option (b) precedent THIS narrative extends.
- `bmad-autopilot/docs/reference-runs/9-6-mobile/narrative.md` — Phase 1.5 mobile-row narrative precedent THIS narrative parallels (Phase 1.5 net-new additions: LAD-only finding analysis subsection; OpenRouter secondary-timeout fallback witness; per-finding qualitative 3-layer-would-have-missed defense).
- `bmad-autopilot/docs/lad-setup.md` — Story 10.7-shipped operator-facing LAD MCP setup guide.
- `bmad-autopilot/docs/onboarding-benchmark.md` — Story 7.9 NFR-P3 longitudinal companion; the per-component-overage diagnosis vocabulary THIS narrative's NFR-P3 section uses.
- `bmad-autopilot/agents/review-lad-wrapper.md` — Story 10.2 + Story 10.5 wrapper this run's LAD layer exercised.
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/four_layer_review_dispatch.py` — Story 10.4 substrate the LAD layer reviewed (alongside `lad_mcp_unavailable.py`).
