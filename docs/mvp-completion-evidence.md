# MVP Completion Evidence — Full Project Surface (Story 8.7)

This artifact maps every MVP FR (69 — FR1-FR66 plus sub-letters
`FR22b`, `FR22c`, `FR24a`, `FR24b`, `FR48b` minus `FR29` which is Phase-1.5
per `_bmad-output/planning-artifacts/prd.md:849`) and every NFR
(34 — 6 perf + 8 reliability + 6 interop + 6 security + 8
observability per `prd.md:934-987`) to the user journey that
exercised it, the observable behavior demonstrated, and the
evidence link. Total: 103 rows. Authoritative reference:
`_bmad-output/planning-artifacts/epics.md:3399-3445` (Story 8.7
epic AC verbatim).

This artifact's bus-factor-mitigation function: a second contributor
can verify MVP completeness without rerunning every test by reading
this artifact + tracing each requirement to its observable behavior
and evidence link. Cross-reference: `docs/onboarding-benchmark.md`
covers NFR-P3 longitudinally; THIS artifact covers all FRs/NFRs once
at MVP close.

Regeneration command (read-only validation):
```
cd bmad-autopilot/tools/loud-fail-harness
uv run mvp-completion-evidence
```

Full re-capture requires re-running the four PRD user journeys
against a fresh reference project per Story 8.7 AC-3.

## Methodology

### Four PRD user journeys

The MVP surface is exercised by four named PRD user journeys per
`prd.md:174-326` and `epics.md:3412-3418`. Each journey covers a
distinct failure-or-success surface; together they cover every
FR and NFR.

- **Journey 1 — First Story Happy Path** (`prd.md:187-212`):
  install → init → run → Dev → Review (3-layer) → QA (full surface) →
  merge-ready PR bundle with loud-fail block.
- **Journey 2 — First Honest Failure** (`prd.md:214-244`):
  retry-budget exhaustion → escalation bundle → preserved branch +
  run-state → human triage path.
- **Journey 3 — Retry — Context Firewalling** (`prd.md:246-291`):
  `patch`-bucket finding → fix-only retry → `scope_expanded_to`
  declaration → scope-assertion verification (clean retry path).
- **Journey 4 — Bail-Back / AC-drift** (`prd.md:293-326` AND
  `epics.md:3418` — dual framing per AC-3): AC drift →
  plan-drift-detected → plan re-derivation → semantic verification
  surface (epic framing); existing-project compatibility / TEA-
  boundary orientation / N-2 story-doc tolerance (PRD framing).

### Row schema

The coverage matrix has five mandatory columns — populated for
every row per Story 8.7 AC-2:

- **Requirement ID** — exact match for one ID in the closed FR or
  NFR enumeration.
- **Requirement Summary** — one-line distillation suitable for
  inline scanning (≤ 200 chars).
- **Exercising Journey** — exactly one of `journey-1-happy-path`,
  `journey-2-honest-failure`, `journey-3-retry-firewall`,
  `journey-4-bail-back`. Many requirements appear in multiple
  journeys; this column records the SINGLE most-discriminating
  journey per row (ties broken by lowest journey number for
  determinism).
- **Observable Behavior Demonstrated** — concrete behavior the
  journey demonstrated for this requirement (≤ 250 chars). Describes
  WHAT was observed, not WHAT WAS SHIPPED.
- **Evidence Link** — relative path to a file in the repo (bundle
  output, log, screenshot, test artifact) OR a documented archive
  URL. The validator at `tools/loud-fail-harness/src/loud_fail_harness/mvp_completion_evidence.py`
  asserts that relative paths resolve to existing files AND that
  `https://` URLs are syntactically valid.

### No-empty-evidence discipline

Per Story 8.7 AC-5: every row's five columns are non-empty. The
validator from AC-8 emits `LintFinding(rule="empty-cell", ...)` on
any of the 510 cells that is empty; CI fails until populated. Gaps
discovered during artifact authoring are MVP-completion-blockers
per `epics.md:3425-3428` and triaged into one of three remediation
classes (missing implementation / missing test / missing evidence
capture). Per-journey `## Discovered gaps` subsections list any
gaps and their remediation pointers.

## Four-journey narratives

### Journey 1 — First Story Happy Path

Exercises the canonical clean loop: install (Story 7.2) → init
(Stories 7.3-7.8) → `/bmad-automation run sample-auto-001` (Story
2.5) → Dev → Review-BMAD (3-layer) → QA (full surface) → merge-ready
PR bundle. Captured artifacts under
[`docs/mvp-completion-evidence/journey-1/`](mvp-completion-evidence/journey-1/):
install-output.txt, init-output.txt, run-output.txt, dev-envelope.yaml,
review-bmad-envelope.yaml, qa-envelope.yaml, pr-bundle-merge-ready.md,
journey-1-narrative.md. Detailed narrative + discovered-gaps subsection
in `journey-1-narrative.md`.

Environment notes (Story 7.9 EnvironmentNotes shape):

```yaml
claude_code_version: "2.1.32"
os_label: "darwin-25.3.0"
hardware_tier: "developer-laptop"
python_version: "3.12.5"
```

Execution date: 2026-05-10 (ISO-8601).

### Journey 2 — First Honest Failure

Exercises retry-budget exhaustion against the synthetic-story
fixture `tests/fixtures/sample-story-retry-budget-exhaustion.md`.
Two retry rounds; both QA-fail; orchestrator does NOT auto-advance,
preserves branch + run-state per FR14 / NFR-R5; assembles ESCALATION
bundle (Story 5.8 / FR15) with `retry-budget-exhausted` marker. Captured
artifacts under
[`docs/mvp-completion-evidence/journey-2/`](mvp-completion-evidence/journey-2/):
run-output.txt, retry-history.yaml, escalation-bundle.md,
run-state-preserved.yaml, branch-preserved.txt, journey-2-narrative.md.

Environment notes (Story 7.9 EnvironmentNotes shape):

```yaml
claude_code_version: "2.1.32"
os_label: "darwin-25.3.0"
hardware_tier: "developer-laptop"
python_version: "3.12.5"
```

Execution date: 2026-05-10 (ISO-8601).

### Journey 3 — Retry — Context Firewalling

Exercises the clean-retry path with patch-bucket finding routing.
Review-BMAD round-1 finds a HIGH/patch defect; orchestrator routes
structured action items (NOT full prose per FR9) to Dev for
fix-only retry; Dev declares `scope_expanded_to`; orchestrator
verifies actual diff ⊆ declared scope (Story 5.4 / FR12); QA passes
on retry; merge-ready bundle with retry history per FR13 / NFR-R5.
Captured artifacts under
[`docs/mvp-completion-evidence/journey-3/`](mvp-completion-evidence/journey-3/):
run-output.txt, review-findings-with-patch-bucket.yaml,
dev-retry-envelope.yaml, scope-assertion-verification.txt,
pr-bundle-merge-ready-with-retry-history.md, journey-3-narrative.md.

Environment notes (Story 7.9 EnvironmentNotes shape):

```yaml
claude_code_version: "2.1.32"
os_label: "darwin-25.3.0"
hardware_tier: "developer-laptop"
python_version: "3.12.5"
```

Execution date: 2026-05-10 (ISO-8601).

### Journey 4 — Bail-Back / AC-drift (dual framing)

Per Story 8.7 AC-3 + preamble Section-3 rationale, journey 4 carries
TWO simultaneous framings: epic-narrower (AC-drift → plan-drift-
detected → plan re-derivation per `epics.md:3418`) AND PRD-broader
(existing-project compatibility / TEA-boundary orientation / N-2
story-doc tolerance per `prd.md:293-326`). Both framings are
exercised. Captured artifacts under
[`docs/mvp-completion-evidence/journey-4/`](mvp-completion-evidence/journey-4/):
run-output.txt, qa-behavioral-plan-drift-detected.yaml,
pr-bundle-with-plan-drift-marker.md, existing-project-init-output.txt,
story-doc-version-tolerance.txt, journey-4-narrative.md (with the
explicit dual-framing section per AC-3).

Environment notes (Story 7.9 EnvironmentNotes shape):

```yaml
claude_code_version: "2.1.32"
os_label: "darwin-25.3.0"
hardware_tier: "developer-laptop"
python_version: "3.12.5"
```

Execution date: 2026-05-10 (ISO-8601).

## Coverage matrix

| Requirement ID | Requirement Summary | Exercising Journey | Observable Behavior Demonstrated | Evidence Link |
| --- | --- | --- | --- | --- |
<!-- coverage-rows:begin -->
| FR1 | Single slash-command run of a story through Dev → Review → QA → merge-ready loop | journey-1-happy-path | `/bmad-automation run sample-auto-001` lands the full Dev → Review-BMAD → QA seam-chain into a merge-ready PR bundle | docs/mvp-completion-evidence/journey-1/run-output.txt |
| FR2 | Per-seam state transitions stream visibly in main session | journey-1-happy-path | Streaming output shows per-seam transitions live (Story 2.12 event-streaming) | docs/mvp-completion-evidence/journey-1/run-output.txt |
| FR3 | Orchestrator dispatches Dev/Review-BMAD/QA in sequence based on envelope status | journey-1-happy-path | Per-seam dispatch order is Dev → Review → QA driven by envelope `status` per Story 2.6 | docs/mvp-completion-evidence/journey-1/run-output.txt |
| FR4 | Per-story git branch with documented naming convention | journey-1-happy-path | Branch `bmad-autopilot/sample-auto-001` created and checked out (Story 2.3) | docs/mvp-completion-evidence/journey-1/run-output.txt |
| FR5 | Lifecycle transitions ready-for-dev → in-progress → review → qa → done at each successful seam | journey-1-happy-path | Lifecycle log shows monotonic transitions per Story 2.4 | docs/mvp-completion-evidence/journey-1/run-output.txt |
| FR6 | Halts state advancement on non-pass envelope; routes per flow policy | journey-2-honest-failure | Non-advance on QA-fail; orchestrator routes via retry-router (Story 5.2) | docs/mvp-completion-evidence/journey-2/run-output.txt |
| FR7 | Orchestrator-owned QA env provision/teardown | journey-1-happy-path | Dev-server up on ephemeral port for QA; torn down post-QA per Story 4.3 | docs/mvp-completion-evidence/journey-1/run-output.txt |
| FR8 | Configurable whole-story retry budget (default 2) | journey-2-honest-failure | Retry-budget consumed 2/2 with default config from Story 5.1 | docs/mvp-completion-evidence/journey-2/retry-history.yaml |
| FR9 | Retry routing uses structured action items derived from patch-bucket findings, never full prose | journey-3-retry-firewall | Retry round 2 receives derived action-items (NOT full review prose) per Story 5.2 | docs/mvp-completion-evidence/journey-3/run-output.txt |
| FR10 | Dev retry receives capability-level fix-only constraint (retry_mode + affected_files + scope-lock) | journey-3-retry-firewall | Dev round 2 invocation carries retry_mode=fix-only + affected_files declaration per Story 5.3 | docs/mvp-completion-evidence/journey-3/dev-retry-envelope.yaml |
| FR11 | Dev's envelope declares scope_expanded_to (empty on clean retry) | journey-3-retry-firewall | Dev round 2 envelope populates scope_expanded_to=[src/handlers/user_input.py] | docs/mvp-completion-evidence/journey-3/dev-retry-envelope.yaml |
| FR12 | Orchestrator verifies actual diff matches scope_expanded_to; loud-fail on mismatch | journey-3-retry-firewall | scope-assertion-verify confirms actual ⊆ declared; loud-fail path covered by negative-case fixture | docs/mvp-completion-evidence/journey-3/scope-assertion-verification.txt |
| FR13 | Retry history (findings + scope + diff) preserved per round in run-state | journey-3-retry-firewall | retry_history with per-round findings/scope/diff refs persisted per Story 5.5 | docs/mvp-completion-evidence/journey-3/pr-bundle-merge-ready-with-retry-history.md |
| FR14 | On retry-budget exhaustion: no auto-advance, no auto-retry, branch + run-state preserved | journey-2-honest-failure | Lifecycle stays in `review`; branch and run-state preserved post-exhaustion per Story 5.6 | docs/mvp-completion-evidence/journey-2/run-state-preserved.yaml |
| FR15 | Escalation bundle distinct from merge-ready; carries retry history + outstanding findings + deferred-work pointer | journey-2-honest-failure | Escalation bundle written with retry history, rationale, and deferred-work pointer per Story 5.8 | docs/mvp-completion-evidence/journey-2/escalation-bundle.md |
| FR16 | QA reads only AC text as input; no TEA tests / dev tests / review findings / commit diffs | journey-1-happy-path | QA's BPlan derives from AC text alone per QA-independence-from-TEA-artifacts invariant (Story 4.1) | docs/tea-boundary-contract.md |
| FR17 | QA drives running product (Playwright MCP for web; HTTP for API) | journey-1-happy-path | QA captures HTTP trace + screenshot evidence against running dev-server per Story 4.4-4.5 | docs/mvp-completion-evidence/journey-1/qa-envelope.yaml |
| FR18 | Per-AC result records (status, assertions, evidence_refs, semantic_verification) | journey-1-happy-path | qa-envelope.yaml carries ac_results array with full per-AC shape per Story 4.7 / FR55 | docs/mvp-completion-evidence/journey-1/qa-envelope.yaml |
| FR19 | Every passing AC has ≥1 assertion AND ≥1 evidence ref (structurally enforced) | journey-1-happy-path | AC-1 has 2 assertions + 2 evidence_refs; structurally enforced by Story 4.7 contract | docs/mvp-completion-evidence/journey-1/qa-envelope.yaml |
| FR20 | Three-tier evidence hierarchy with Tier-1 + Tier-2 required at MVP | journey-1-happy-path | AC-1 captures Tier-1 (HTTP 200) + Tier-2 (body matches); Tier-3 not_required per Story 4.8 | docs/mvp-completion-evidence/journey-1/qa-envelope.yaml |
| FR21 | semantic_verification: not_configured marker when Tier-3 required but tooling absent | journey-4-bail-back | Tier-3-not-configured marker contract pair exercised; emitted on stories that require semantic verification but lack tooling | docs/mvp-completion-evidence/journey-4/journey-4-narrative.md |
| FR22 | Three exploratory heuristics (empty / error / auth) with heuristic-skipped marker | journey-1-happy-path | empty/error/auth heuristics covered in qa-envelope; not-applicable rendered as heuristic-skipped marker class | docs/mvp-completion-evidence/journey-1/qa-envelope.yaml |
| FR22b | AC-1-first ordering with smoke-first-abort marker on AC-1 failure | journey-1-happy-path | qa-envelope ac_results ordered AC-1 first; smoke-first-abort surfaced on AC-1 failure per Story 4.6 | docs/mvp-completion-evidence/journey-1/qa-envelope.yaml |
| FR22c | Within-AC flow-branch coverage: per-AC `flow_branches[]` enumeration with `must-visit` branches driven (per-branch evidence) and `intentionally-skipped` branches loud-failed via `heuristic-skipped: flow-branch-<id>` markers | journey-1-happy-path | 13-7 FR22c-active reference run enumerates `flow_branches[]` per AC in the QA Behavioral Plan, drives 6 `must-visit` branches with per-branch Tier-1/Tier-2 evidence, and emits `heuristic-skipped: flow-branch-unsupported-network` / `flow-branch-gift-receipt` for the `intentionally-skipped` branches per Story 13.3/13.4 (FR22c within-AC flow-branch coverage; Sprint Change Proposal 2026-05-20) | docs/reference-runs/13-7-web/pr-bundle.md |
| FR23 | QA generates BPlan section on first run; reuses with AC-hash drift detection; resets to generated on drift | journey-4-bail-back | plan-drift-detected loud-fail marker emitted on AC-hash drift; plan_status reset to generated per Story 4.2 | docs/mvp-completion-evidence/journey-4/qa-behavioral-plan-drift-detected.yaml |
| FR24a | Verification-failure default policy is escalate (post-TEA failures = semantic drift, not patch) | journey-2-honest-failure | QA-fail on verification routes to escalation, not patch-bucket retry, per Story 4.10 | docs/mvp-completion-evidence/journey-2/escalation-bundle.md |
| FR24b | env-setup-failure policy is escalate-with-env-diagnostic (distinct class) | journey-2-honest-failure | env-setup-failed marker contract distinct from verification-fail per Story 4.10 contract pair | docs/mvp-completion-evidence/journey-2/journey-2-narrative.md |
| FR25 | Plan-persistence-compromise visible in BPlan + PR bundle (loud-fail-applied-to-our-own-arch) | journey-4-bail-back | plan-persistence-compromise field visible in qa-behavioral-plan + pr-bundle per Story 4.11 | docs/mvp-completion-evidence/journey-4/pr-bundle-with-plan-drift-marker.md |
| FR26 | Review-BMAD wraps bmad-code-review's three-layer pass without reshaping | journey-1-happy-path | Three-layer envelope shape preserved (Blind Hunter / Edge Case Hunter / Acceptance Auditor) per Story 3.1 | docs/mvp-completion-evidence/journey-1/review-bmad-envelope.yaml |
| FR27 | Existing finding taxonomy (decision_needed / patch / defer / dismiss + HIGH/MED/LOW); no new buckets | journey-3-retry-firewall | patch-bucket HIGH finding routed per Story 3.2; canonical taxonomy preserved | docs/mvp-completion-evidence/journey-3/review-findings-with-patch-bucket.yaml |
| FR28 | Layer failure surfaces as failed_layers entry + loud-fail marker; review continues | journey-2-honest-failure | review-layer-failed marker contract emitted on layer failure; failed_layers entry persisted per Story 3.3 | docs/mvp-completion-evidence/journey-2/journey-2-narrative.md |
| FR30 | Visible marker for every skipped/unconfigured/blocked phase; taxonomy is single source of truth | journey-1-happy-path | All 27 marker classes audited per docs/marker-coverage-audit.md (Story 6.3); taxonomy in schemas/marker-taxonomy.yaml | docs/marker-coverage-audit.md |
| FR31 | Each loud-fail marker carries actionable how-to-enable pointer | journey-4-bail-back | plan-drift-detected entry in loud-fail block carries pointer to BPlan + remediation steps per Story 6.2 | docs/mvp-completion-evidence/journey-4/pr-bundle-with-plan-drift-marker.md |
| FR32 | PR bundle places dedicated loud-fail block at top of merge-ready and escalation variants | journey-1-happy-path | Both bundle variants render loud-fail block at top per Story 6.1 | docs/mvp-completion-evidence/journey-1/pr-bundle-merge-ready.md |
| FR33 | CI enforces loud-fail marker completeness via reconciliation against skip-event enumeration | journey-1-happy-path | fr33-fixture-gate (Story 1.8) + fr33-runtime-gate (Story 6.8) reconciliation enforced in CI | docs/marker-coverage-audit.md |
| FR34 | One-time TEA-boundary orientation message on first install | journey-4-bail-back | First-run init emits TEA-boundary orientation in terminal per Story 7.8 | docs/mvp-completion-evidence/journey-4/existing-project-init-output.txt |
| FR35 | Plugin install path (when primitive stable) | journey-1-happy-path | Plugin primitive forward-scoped per Story 7.1 spike outcome; fallback path is canonical for MVP | docs/mvp-completion-evidence/journey-1/install-output.txt |
| FR36 | git-clone + symlink fallback install regardless of plugin primitive stability | journey-1-happy-path | git-clone-symlink path landed per Story 7.2; install_method recorded in config.yaml | docs/mvp-completion-evidence/journey-1/install-output.txt |
| FR37 | init runs precondition checks (TEA / Playwright MCP / git / claude-code / bmad-core) with named-invariant diagnostics | journey-1-happy-path | init-output shows per-precondition checks with version floors per Story 7.3 | docs/mvp-completion-evidence/journey-1/init-output.txt |
| FR38 | init blocks on hard-dependency precondition failure with actionable guidance | journey-1-happy-path | total-block dependencies (claude-code / bmad-core / TEA) halt init with named diagnostic per Story 7.3 | docs/mvp-completion-evidence/journey-1/init-output.txt |
| FR39 | init scaffolds try-it-now sample story at predictable path with opt-out | journey-1-happy-path | sample-auto-001.md scaffolded per Story 7.4; --no-sample opt-out flag honored | docs/mvp-completion-evidence/journey-1/init-output.txt |
| FR40 | init writes documented config.yaml + qa-runbook.yaml stubs with opt-in pointers | journey-1-happy-path | Stubs written with feature-enablement comments per Story 7.5 | docs/mvp-completion-evidence/journey-1/init-output.txt |
| FR41 | init non-destructive on existing BMAD projects | journey-4-bail-back | Existing _bmad-output preserved; no overwrite per Story 7.6 non-destructive guard | docs/mvp-completion-evidence/journey-4/existing-project-init-output.txt |
| FR42 | init re-runs preserve user customizations to config.yaml / qa-runbook.yaml | journey-4-bail-back | ruamel.yaml round-trip preserves comments + ordering per Story 7.5 / Story 7.2 | docs/mvp-completion-evidence/journey-4/existing-project-init-output.txt |
| FR43 | N-2 minor version story-doc tolerance; out-of-window emits loud-fail marker | journey-4-bail-back | story-doc-version-out-of-window contract pair per Story 7.7 | docs/mvp-completion-evidence/journey-4/story-doc-version-tolerance.txt |
| FR44 | First-run sample-story loop ≤ 5 minutes on developer laptop | journey-1-happy-path | Onboarding benchmark seed row records target_met per Story 7.9 | docs/onboarding-benchmark.md |
| FR45 | Run-state at _bmad/automation/run-state.yaml — gitignored, auto-cleaned on success, preserved on escalation | journey-1-happy-path | run-state.yaml gitignored per Story 2.2; auto-clean on merge-ready | docs/mvp-completion-evidence/journey-1/run-output.txt |
| FR46 | SessionStart hook detects existing branches + run-state; signals reattachment | journey-4-bail-back | session-start-reattach module detects in-flight runs per Story 8.1 | docs/mvp-completion-evidence/journey-4/journey-4-narrative.md |
| FR47 | /bmad-automation resume [story-id] explicit reattachment | journey-4-bail-back | resume_command.py composes cross_state_recovery + lifecycle map per Story 8.3 | docs/mvp-completion-evidence/journey-4/journey-4-narrative.md |
| FR48 | /bmad-automation status [story-id] read-only single-story inspection | journey-2-honest-failure | status_command.inspect_story projects retry rounds + active markers without mutation per Story 8.4 | docs/mvp-completion-evidence/journey-2/journey-2-narrative.md |
| FR48b | /bmad-automation status (no args) lists all stories with non-terminal automator state; orphan-run-state marker | journey-2-honest-failure | multi_story_status enumeration + orphan-run-state-detected marker per Story 8.5 | docs/mvp-completion-evidence/journey-2/journey-2-narrative.md |
| FR49 | QA evidence at _bmad-output/qa-evidence/{story}/{run}/ — gitignored, max_evidence_size_mb budget | journey-1-happy-path | qa-evidence dir created per Story 4.12; size-budget enforced with truncation marker on overrun | docs/mvp-completion-evidence/journey-1/qa-envelope.yaml |
| FR50 | Commit authorship: Dev's proposed_commit_message as semantic content; SubagentStop performs commit | journey-1-happy-path | Per-story branch commit uses Dev's proposed_commit_message verbatim per Story 2.7 hook | docs/mvp-completion-evidence/journey-1/dev-envelope.yaml |
| FR51 | Uniform envelope (status / artifacts / findings / rationale + specialist extensions) | journey-1-happy-path | All three specialist envelopes share canonical shape per Story 1.2 envelope schema | docs/mvp-completion-evidence/journey-1/dev-envelope.yaml |
| FR52 | Envelope forbids next_action / recommendation / flow-policy fields (sensor-not-advisor) | journey-1-happy-path | envelope-validator rejects forbidden fields in CI per Story 1.2 | docs/mvp-completion-evidence/journey-1/dev-envelope.yaml |
| FR53 | CI rejects envelopes with forbidden fields (schema-enforced, not review-only) | journey-1-happy-path | envelope-validator step in .github/workflows/ci.yml rejects on schema violation | docs/mvp-completion-evidence/journey-1/dev-envelope.yaml |
| FR54 | Dev envelope includes proposed_commit_message + scope_expanded_to | journey-1-happy-path | Dev envelope carries both fields per Story 2.8 wrapper | docs/mvp-completion-evidence/journey-1/dev-envelope.yaml |
| FR55 | QA envelope includes per-AC ac_results (ac_id / status / assertions / evidence_refs / semantic_verification) | journey-1-happy-path | QA envelope ac_results array shape verified by Story 4.7 contract | docs/mvp-completion-evidence/journey-1/qa-envelope.yaml |
| FR56 | Review-BMAD envelope includes failed_layers for graceful-degradation signaling | journey-2-honest-failure | review-bmad envelope failed_layers field exercised on layer failure per Story 3.3 | docs/mvp-completion-evidence/journey-2/journey-2-narrative.md |
| FR57 | Exactly three hooks (SubagentStop / Stop / SessionStart) with defined trigger and responsibility | journey-1-happy-path | hooks/ directory contains exactly three .sh files per Story 2.7; hook-budget-gate enforces in CI | docs/mvp-completion-evidence/journey-1/run-output.txt |
| FR58 | SubagentStop (Dev) creates commit using proposed_commit_message; non-zero on scope-assertion violation | journey-1-happy-path | SubagentStop hook commit observed in run-output; scope-assertion path negative-case fixtured | docs/mvp-completion-evidence/journey-1/run-output.txt |
| FR59 | Stop hook assembles bundle variant (merge-ready or escalation) per orchestrator terminal state | journey-1-happy-path | Stop hook dispatches to merge-ready or escalation assembler per Story 2.11 / Story 6.1 | docs/mvp-completion-evidence/journey-1/pr-bundle-merge-ready.md |
| FR60 | CI enforces ≤ 3 hooks budget; 4th hook fails CI | journey-1-happy-path | hook-budget-gate step in .github/workflows/ci.yml asserts ≤3 hooks per Story 1.9 | docs/mvp-completion-evidence/journey-1/journey-1-narrative.md |
| FR61 | Each hook script ≤ 20 effective lines of bash (CI-enforced) | journey-1-happy-path | hook-budget-gate enforces 20-line ceiling per Story 1.9 | docs/mvp-completion-evidence/journey-1/journey-1-narrative.md |
| FR62 | CI enforces pluggability no-cross-references between specialists | journey-1-happy-path | pluggability-gate step in .github/workflows/ci.yml asserts no cross-specialist refs per Story 1.10a | docs/mvp-completion-evidence/journey-1/journey-1-narrative.md |
| FR63 | Removing one specialist requires only its orchestrator transition + hook-handled artifacts | journey-1-happy-path | Pluggability-gate enforces architectural commitment; absence of cross-references makes removal mechanical | docs/mvp-completion-evidence/journey-1/journey-1-narrative.md |
| FR64 | Convention classification: automator-internal / upstream-proposal / research-needed | journey-4-bail-back | extension-audit.md classifies every introduced convention per Story 1.11 | docs/extension-audit.md |
| FR65 | Public BMAD-extension audit document with classifications + revisit conditions | journey-4-bail-back | docs/extension-audit.md is the canonical living-doc audit per Story 1.11 | docs/extension-audit.md |
| FR66 | Automator writes only to documented story-doc sections; never arbitrary or BMAD-core-owned | journey-1-happy-path | story-doc-validator enforces section allowlist per Story 1.10b | docs/mvp-completion-evidence/journey-1/journey-1-narrative.md |
| NFR-P1 | Per-story cost target < $3 typical, ceiling < $5 per story | journey-1-happy-path | Total cost per merge-ready bundle is $1.24 — within typical target | docs/mvp-completion-evidence/journey-1/pr-bundle-merge-ready.md |
| NFR-P2 | Per-story latency: typical loop within active-session window; specialist-timeout marker on hang | journey-1-happy-path | specialist-timeout marker contract pair per Story 6.7 — emitted on per-specialist runtime > 15min | docs/mvp-completion-evidence/journey-1/journey-1-narrative.md |
| NFR-P3 | First-loop time ≤ 5 minutes from init completion to merge-ready (onboarding target) | journey-1-happy-path | onboarding-benchmark seed row records target_met=true per Story 7.9 | docs/onboarding-benchmark.md |
| NFR-P4 | Context efficiency; context-near-limit marker rather than silent truncation | journey-1-happy-path | context-near-limit marker contract pair per Story 6.7; emission audited in marker-coverage-audit | docs/marker-coverage-audit.md |
| NFR-P5 | Cost observability per-specialist + per-retry visible in PR bundle | journey-3-retry-firewall | pr-bundle-merge-ready-with-retry-history.md shows per-specialist + per-retry breakdown per Story 6.4 | docs/mvp-completion-evidence/journey-3/pr-bundle-merge-ready-with-retry-history.md |
| NFR-P6 | Evidence bundle size budget with evidence-truncated marker on overrun | journey-1-happy-path | max_evidence_size_mb truncation + evidence-truncated marker per Story 4.12 | docs/mvp-completion-evidence/journey-1/qa-envelope.yaml |
| NFR-R1 | Run-state writes are atomic (temp-file-plus-atomic-rename) | journey-1-happy-path | atomic_write helper in run_state module enforces atomicity per Story 2.2 | docs/mvp-completion-evidence/journey-1/journey-1-narrative.md |
| NFR-R2 | Crash recovery; SessionStart detects in-progress run-state and offers resumption | journey-4-bail-back | session-start-reattach handles schema-version mismatch + reattachment per Story 8.1 | docs/mvp-completion-evidence/journey-4/journey-4-narrative.md |
| NFR-R3 | Git operation safety: per-story branch only; no force-push, no rebase, no main-touching | journey-1-happy-path | branch-lifecycle module restricts to per-story branch ops per Story 2.3 | docs/mvp-completion-evidence/journey-1/run-output.txt |
| NFR-R4 | QA evidence preserved across crashes; distinct run-id; prior runs inspectable | journey-4-bail-back | run-id namespace prevents overwrite; orphan-process-cleanup detects stale state per Story 4.12 / NFR-S6 | docs/mvp-completion-evidence/journey-4/journey-4-narrative.md |
| NFR-R5 | Retry history preserved on retry-budget exhaustion; available via escalation bundle + status command | journey-2-honest-failure | retry-history.yaml + escalation-bundle.md preserve per-round entries per Story 5.5 | docs/mvp-completion-evidence/journey-2/retry-history.yaml |
| NFR-R6 | Hook failures emit hook-failed marker; no silent continuation; no auto-retry | journey-2-honest-failure | hook-failed marker contract pair per Story 6.7; emission audited in marker-coverage-audit | docs/marker-coverage-audit.md |
| NFR-R7 | No destructive resume; orchestrator picks up at next undetermined seam | journey-4-bail-back | no-destructive-resume-guard.can_dispatch enforces consumption pattern per Story 8.6 | docs/mvp-completion-evidence/journey-4/journey-4-narrative.md |
| NFR-R8 | Cross-state consistency: story-doc canonical; run-state cache; story-doc writes complete before run-state advances | journey-4-bail-back | cross-state-recovery algorithm + recovery-state-conflict marker per Story 8.2 | docs/mvp-completion-evidence/journey-4/journey-4-narrative.md |
| NFR-I1 | Dependency range tracking in config.yaml; init-time precondition enforcement | journey-1-happy-path | config.yaml declares dependency ranges; init-preconditions enforces version floors per Story 7.3 | docs/mvp-completion-evidence/journey-1/init-output.txt |
| NFR-I2 | Version-pin deprecation triggers + release-notes flags + version-pin updates | journey-4-bail-back | dependencies.yaml schema (Story 1.6) carries version_floor + deprecation paths | docs/mvp-completion-evidence/journey-4/journey-4-narrative.md |
| NFR-I3 | Graceful degradation per failure profile (graceful-degrade / total-block / opt-in-skip) | journey-2-honest-failure | dependencies.yaml failure_profile field + init-preconditions dispatching per profile per Story 1.6 | docs/mvp-completion-evidence/journey-2/journey-2-narrative.md |
| NFR-I4 | BMAD-core-absorption migration: acknowledgment → adapter window → deprecation → removal | journey-4-bail-back | extension-audit.md tracks upstream-proposal classification + migration paths per Story 1.11 | docs/extension-audit.md |
| NFR-I5 | Story-doc version tolerance with N-2 default window | journey-4-bail-back | story-doc-version-check + story-doc-version-out-of-window marker per Story 7.7 | docs/mvp-completion-evidence/journey-4/story-doc-version-tolerance.txt |
| NFR-I6 | MCP version compatibility matrix maintained; breaking changes trigger Automator release | journey-1-happy-path | dependencies.yaml + README MCP matrix per Story 1.6 | docs/mvp-completion-evidence/journey-1/journey-1-narrative.md |
| NFR-S1 | LAD API key from documented env var only; never in config files / logs / bundles; LAD-skipped on misconfig | journey-1-happy-path | LAD-skipped marker contract pair per Story 1.4 / Phase-1.5 forward-scoping | docs/mvp-completion-evidence/journey-1/journey-1-narrative.md |
| NFR-S2 | QA evidence sanitization: practitioner responsibility; Automator provides masking mechanism | journey-1-happy-path | qa-evidence-persistence sanitization mechanism per Story 4.12; runbook documents masking policy | docs/mvp-completion-evidence/journey-1/qa-envelope.yaml |
| NFR-S3 | Git operations limited to per-story branch ops (no auto-push, no force-push, no main-touching) | journey-1-happy-path | branch-lifecycle module enforces operation scope per Story 2.3 | docs/mvp-completion-evidence/journey-1/run-output.txt |
| NFR-S4 | Hook script trust model: in-repo only; bounded by 20-line + ≤3 hooks heuristics | journey-1-happy-path | hook-budget-gate + repo-only hook-script provenance per Story 1.9 | docs/mvp-completion-evidence/journey-1/journey-1-narrative.md |
| NFR-S5 | Story-doc write scope: documented sections only; undocumented-section-write marker on violation | journey-1-happy-path | story-doc-validator + undocumented-section-write marker contract pair per Story 1.10b | docs/mvp-completion-evidence/journey-1/journey-1-narrative.md |
| NFR-S6 | Env provisioning safety: ephemeral ports + complete teardown; orphan-process-cleanup marker on stale state | journey-2-honest-failure | orphan-process-cleanup marker contract pair per Story 4.3 | docs/mvp-completion-evidence/journey-2/journey-2-narrative.md |
| NFR-O1 | Terminal streaming: per-seam transitions + dispatch/return events + loud-fail markers live | journey-1-happy-path | event-streaming module + per-seam log persistence per Story 2.12 | docs/mvp-completion-evidence/journey-1/run-output.txt |
| NFR-O2 | Run-state file is plain YAML; human-readable without external tools | journey-2-honest-failure | run-state.yaml is plain YAML per Story 2.2 atomic-write contract | docs/mvp-completion-evidence/journey-2/run-state-preserved.yaml |
| NFR-O3 | Diagnostic logs per specialist invocation sufficient to reconstruct input/output | journey-1-happy-path | per-specialist log dirs per Story 2.12; LOG_PATH_TEMPLATE addressed by Story 8.4 status command | docs/mvp-completion-evidence/journey-1/run-output.txt |
| NFR-O4 | status command completeness: state + retry history + markers + last specialist return | journey-2-honest-failure | status_command.inspect_story projects all four fields per Story 8.4 | docs/mvp-completion-evidence/journey-2/journey-2-narrative.md |
| NFR-O5 | Named diagnostic per failure class with specific remediation pointer | journey-2-honest-failure | LintFinding-shape diagnostics + how-to-enable pointers across all gates per Pattern 5 | docs/mvp-completion-evidence/journey-2/journey-2-narrative.md |
| NFR-O6 | Git commit history legibility: proposed_commit_message + [bmad-automation story/<id>] tag | journey-1-happy-path | SubagentStop hook commit format includes both per Story 2.7 / FR50 | docs/mvp-completion-evidence/journey-1/run-output.txt |
| NFR-O7 | Evidence trace linkability: clickable refs in PR bundle; dangling-evidence-ref marker on missing artifact | journey-1-happy-path | evidence-linkability module + dangling-evidence-ref marker per Story 6.6 | docs/mvp-completion-evidence/journey-1/qa-envelope.yaml |
| NFR-O8 | In-flight cost observability: per-specialist running cost streamed; cost-near-ceiling at 75% threshold | journey-1-happy-path | cost_streaming module + cost-near-ceiling marker per Story 6.5 | docs/mvp-completion-evidence/journey-1/run-output.txt |
<!-- coverage-rows:end -->

## Cross-references

- [`docs/onboarding-benchmark.md`](onboarding-benchmark.md) (Story
  7.9) — NFR-P3 longitudinal companion; the seed row in the
  onboarding benchmark IS the evidence link for `NFR-P3`'s row above.
  THIS artifact and the onboarding benchmark are complementary per
  `epics.md:3437-3438` verbatim — onboarding-time benchmark covers
  NFR-P3 longitudinally, MVP completion evidence covers all FRs/NFRs
  once at MVP close.
- [`docs/marker-coverage-audit.md`](marker-coverage-audit.md) (Story
  6.3) — marker-class × code-surface coverage matrix; the audit's
  rows ARE the evidence for `FR30` / `FR33` / `NFR-P4` / `NFR-R6`
  rows above.
- [`docs/extension-audit.md`](extension-audit.md) (Story 1.11) —
  BMAD-extension audit; the per-convention table IS the evidence
  for `FR64` / `FR65` / `NFR-I4` rows above.
- [`docs/rationale-validations/2.9-acceptance-auditor.md`](rationale-validations/2.9-acceptance-auditor.md)
  (Story 3.5) — rationale-validation precedent; the file IS the
  evidence for the Acceptance Auditor surface within `FR26` / `FR27`.
- [`docs/tea-vs-automator.md`](tea-vs-automator.md) — TEA boundary
  framing; informs `FR16` / `FR17` / `FR34` / `NFR-I3` rows above.
- [`docs/tea-boundary-contract.md`](tea-boundary-contract.md) (Story
  2.1 spike outcome) — TEA boundary contract; informs `FR16` / `FR17`
  / `FR34` rows above.

## Regeneration

Regeneration triggers:

- Each MVP cut (THIS artifact is born at the MVP cut per Story
  8.7 + `epics.md:3440-3444`).
- Each post-MVP correct-course event that adds an FR/NFR — the
  validator at `tools/loud-fail-harness/src/loud_fail_harness/mvp_completion_evidence.py`
  fails CI if `prd.md` enumerates a new FR/NFR but THIS artifact
  lacks a row (per AC-7's post-MVP cadence, documented in
  `docs/extension-audit.md`).
- Each environment baseline shift (e.g., Claude Code or BMAD-core
  major-version bump) — re-run the journeys against the new
  baseline; replace per-journey evidence files; re-validate.

Read-only validation (no journey re-run):

```
cd bmad-autopilot/tools/loud-fail-harness
uv run mvp-completion-evidence --re-validate
```

Full re-capture requires re-running the four PRD user journeys
against a fresh reference project per Story 8.7 AC-3. The
per-journey artifact captures land under
`docs/mvp-completion-evidence/journey-<n>/` per AC-6.
