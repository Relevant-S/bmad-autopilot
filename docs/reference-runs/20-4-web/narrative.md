# Reference Run 20-4 — Epic-20 QA-Independence + Flakiness Web Reference Run (plan re-derivation cross-check + flakiness threshold) — narrative

## Reference project

Per Story 20.4 AC-1 + the AC substitution posture inherited from Stories 9.6 / 10.7 / 13.7 / 19.6: the QA surface is the **established UI-bearing e-commerce cart/checkout synthetic surface** — the same web surface the `19-6-web` / `13-7-web` runs exercised — captured here as a fresh Epic-20 run under the story id `sample-qa-coverage-001`. Per Story 20.4 Dev Notes ("Reuse a synthetic QA surface — do not invent a new app"), no new synthetic project is invented: the plan re-derivation cross-check and the flakiness accumulation are cross-AC and project-type-agnostic, applying to any story's ACs.

What matters for this witness is the **two Epic-20 envelope surfaces + the markers they drive + the committed flakiness corpus + the per-specialist cost** (AC-2 through AC-8), not a novel app. The Epic-19 QA-coverage surfaces (7-heuristic / a11y / visual regression) are carried forward structurally from `19-6-web` so the migrated "latest" pointer stays a full-capability capture; they are not re-witnessed here (`19-6-web` is preserved unmodified as the historical Epic-19 capture).

Live re-capture against a maintainer-owned external project (PRD line 815 — "practitioner-actually-useful, not synthetic demo") remains **forward-scoped**, the same substitution commitment Stories 9.6 / 10.7 / 13.7 / 19.6 made. Story 23.2 (`phase-2-completion-evidence.md`) is the forward consumer that reads this directory.

## Reference project purpose + scope

This run is the **empirical witness for FR-P2-9 (per-run plan re-derivation cross-check) and FR-P2-8 (longitudinal flakiness log + threshold)** — the two QA-independence-restoration capabilities Epic 20 landed (Stories 20.1–20.3). It is the FIRST reference run to exercise the `plan_rederivation` envelope field (on BOTH its green and drift branches) and the `flakiness_emissions` envelope array, backed by a committed flakiness-corpus snapshot.

The run preserves the LAD-enabled 4-layer review posture of the `19-6-web` baseline (Story 20.4 AC-1) so migrating the web row's `Latest Run Record` cell does not regress the latest web capture from 4-layer to 3-layer. The LAD layer is rendered as a clean representative pass — re-deriving a fresh real 12-finding `mcp__lad__code_review` capture is out of scope; the genuine-LAD-findings capture is preserved permanently at `docs/reference-runs/10-7-lad-web/`.

## Chosen story user-visible outcome

The Dev specialist had already implemented the e-commerce cart/checkout web surface (AC-1 add-to-cart, AC-2 invalid-card rejection, AC-3 order confirmation) on run-001; run-003 (the primary capture) introduces no source change. The user-visible outcome is the running product behaving correctly across the three ACs while the QA specialist exercises the Epic-20 QA-independence + flakiness surfaces against it across multiple runs.

## FR-P2-9 plan re-derivation cross-check

Story 20.1 landed `qa_plan_rederivation.surface_plan_rederivation_cross_check` — a **read-only** cross-check that ALWAYS returns a `PlanRederivationCrossCheck` with `cross_check_status ∈ {green, drift-detected}` — plus the optional top-level `plan_rederivation` envelope field, surfaced in the bundle as a `FR-P2-9 cross-check: green` line co-located with the RETAINED FR25 compromise blockquote. The cross-check compares the **persisted** `## QA Behavioral Plan` against the **re-derived** plan at the three non-AC-hash drift surfaces — `heuristic_applicability`, `flow_branches`, and the `semantic_verification_tier` pair (`semantic_verification_requirement` + `expected_evidence_tier`). `ac_hash` and `assertion_shape` are EXCLUDED — those are AC-text-derived and are FR23's channel.

**The green path (run-003 — the primary capture).** The AC text is unchanged across runs, so `ac_hash` matches the persisted plan and the QA wrapper takes the **`reuse-existing`** path (FR23's `plan_status` reset does NOT fire — that is the AC-hash channel). The wrapper re-derives the plan from the current AC list + qa-runbook state and cross-checks it: the persisted and re-derived plans agree at all three drift surfaces, so `plan_rederivation: { cross_check_status: green }` and NO `plan-rederivation-drift-detected` marker fires. The `pr-bundle.md` `## Per-AC results` section renders the `> FR-P2-9 cross-check: green` line co-located with the retained FR25 compromise blockquote.

**The AC-hash-channel distinction (why a green here is meaningful).** The cross-check fires ONLY on the `reuse-existing` path — i.e. precisely when `ac_hash` matched and FR23's AC-hash drift detector stayed silent. So any mismatch the cross-check surfaces is **necessarily "beyond AC-hash drift"**: it is plan content that drifted without the AC text changing — exactly the QA-independence gap FR-P2-9 closes (a persisted plan can silently diverge from what the current qa-runbook + AC list would re-derive). A green cross-check on the reuse-existing path is the positive witness that no such silent divergence exists this run.

**The drift path (run-004 — the supplementary follow-on, `qa-envelope-rederivation-drift.yaml`).** The cross-check is per-run state, so witnessing both branches requires two run captures. Between run-003 and run-004 the practitioner edited the qa-runbook to declare the **`rate-limit-boundary` heuristic applicable to AC-2** (it had been structurally inapplicable on every prior run — surfaced as a `heuristic-skipped: rate-limit-boundary` marker). This is the **concrete mutation that drives the drift**, reproducible by any future reader: the AC *text* is unchanged, so `ac_hash` still matches and the reuse-existing path is taken, but the re-derived plan now carries `rate-limit-boundary` in AC-2's `heuristic_applicability` while the persisted plan (written on run-001) does not. The read-only cross-check finds the mismatch at the `heuristic_applicability` drift surface and returns `plan_rederivation: { cross_check_status: drift-detected, drift_surfaces: [heuristic_applicability], drifted_ac_ids: [AC-2], story_id: sample-qa-coverage-001 }`; `plan-rederivation-drift-detected` fires. The drift-run bundle excerpt (reproduced in `pr-bundle.md` § Drift-run excerpt) carries the `### Plan re-derivation drift detected` H3 + the structured `<!-- bmad-automation:marker plan-rederivation-drift-detected -->` comment, greppable.

**The persisted plan is NOT silently overwritten (Story 20.1 AC-3).** FR-P2-9 is a read-only cross-check: it reports drift, it does not refresh the plan. FR23's `plan_status` reset on AC-hash drift remains the ONLY trigger for plan refresh — and the AC text did not change here, so no refresh occurred. The persisted `## QA Behavioral Plan` is left intact for the next run to cross-check against.

## FR-P2-8 flakiness corpus

Story 20.2 landed `schemas/qa-flakiness-log.yaml` + the gitignored `_bmad-output/qa-flakiness/<story-id>.yaml` live store (`.gitignore` line 31) + the `flakiness-log-validator` console entry. The log records, **for each AC, the ordered pass/fail history across runs** — `acs[].runs[]` with `run_id` / `timestamp` / `status` / `retry_count_within_run` / `evidence_ref`, ordered oldest→newest.

**Per-run accumulation timeline (the multi-run fixture this directory commits).** The committed snapshot `qa-flakiness-log.yaml` is the corpus state after run-003:

| run | AC-1 (control) | AC-2 (flaky) |
|---|---|---|
| run-001 (2026-06-13) | `pass`, `retry_count_within_run: 0` | `pass`, `retry_count_within_run: 2` |
| run-002 (2026-06-14) | `pass`, `retry_count_within_run: 0` | `pass`, `retry_count_within_run: 1` |
| run-003 (2026-06-15) | `pass`, `retry_count_within_run: 0` | `pass`, `retry_count_within_run: 2` |

Each run appends one record per AC. AC-2 (the invalid-card-rejection flow — its payment-gateway round-trip is the genuine source of action-level transient retries) accumulates three consecutive transient-fail records; AC-1 (add-to-cart) stays clean.

**`retry_count_within_run` is the transient signal — NOT `status` (Story 20.2/20.3 semantics).** The transient-fail predicate is purely the **action-level / Playwright-native** retry count — the "action-level" tier of the two-tier retry model (prd.md line 1044), DISTINCT from the orchestrator whole-story retry budget. A `pass` WITH a non-zero action-level retry IS a transient fail (every AC-2 record above is exactly this case: it passed, but only after action-level retries). A clean deterministic `fail` with `retry_count_within_run: 0` is NOT flakiness — that is breakage the AC verdict already surfaces. `evaluate_ac_flakiness` intentionally never consults `status`.

**Gitignored live store vs committed snapshot.** Story 20.2 made the live store gitignored (practitioner-local longitudinal signal). The reference directory therefore commits a **captured snapshot** `qa-flakiness-log.yaml` as the *record* — exactly as 19.6 cited gitignored a11y/visual baselines without committing the live binaries, except here the corpus IS the witness so its content is reproduced in the snapshot. The snapshot validates against the unmodified `schemas/qa-flakiness-log.yaml` (AC-4/AC-6) and is replayed through the real substrate (AC-7).

## Flakiness threshold exceeded

Story 20.3 landed the `flakiness-threshold-exceeded` marker (taxonomy `1.17`), the optional `flakiness_emissions` typed array on the QA envelope (`$defs/flakiness_emission`, FLAT, `required: [marker_class, ac_id]`), and `qa_flakiness_threshold.evaluate_ac_flakiness`. An AC crosses the **default** threshold IFF its trailing `threshold_consecutive_runs` (=3) records all exist AND each has `retry_count_within_run >= threshold_transient_fail_count` (=1). The default applies because the qa-runbook `flakiness:` block is **absent** (absence = defaults, NOT a marker — FR42 user-owned-file discipline).

On run-003 (the 3rd accumulating run), AC-2's trailing three records all carry `retry_count_within_run >= 1`, so its streak reaches 3 and **`flakiness-threshold-exceeded` fires for AC-2** — carried on the primary `qa-envelope.yaml` as `flakiness_emissions: [ { marker_class: flakiness-threshold-exceeded, ac_id: AC-2 } ]` and rendered in `pr-bundle.md`'s `### Flakiness threshold exceeded` H3 with the per-AC `<!-- bmad-automation:marker flakiness-threshold-exceeded -->` comment. AC-1's streak is 0, so it is **SILENT** (no `flakiness_emissions` entry, no marker — the no-marker-on-absence parity with every opt-in QA-evidence surface).

**Story-level evidence, NOT an AC gate (sensor-not-advisor).** The threshold marker does NOT flip AC-2's `pass` verdict and does NOT contribute to the wrapper-level `status` — exactly like `a11y-*` / `visual-regression-*` / `heuristic-skipped` / `plan-drift-detected`. The run still reaches `merge-ready`. The marker surfaces via the typed `flakiness_emissions` array + the bundle's per-AC marker-comment render — NOT through `run_state.active_markers` (no QA-evidence marker routes through that; the deliberate "QA-evidence orphan" pattern). Flow policy lives only in the orchestrator; the QA wrapper is a sensor.

## Substrate-replay as the non-vacuous proof (the 20.4 strengthening over 19.6)

Unlike 19.6's LLM-driven heuristic dispatch (un-replayable), the Epic-20 verdicts come from **pure, deterministic substrate**, so the captured records are CI-pinned against the real code by the NEW committed test `tools/loud-fail-harness/tests/test_reference_run_20_4.py` (AC-7 — the maintainer-ratified strengthening, 2026-06-15). The test loads the committed artifacts in this directory and replays them through the real substrate:

- the committed `qa-flakiness-log.yaml` through the real `load_flakiness_log` / `validate_flakiness_log` path AND `evaluate_ac_flakiness(history, FlakinessThresholdConfig())` → `exceeded == True`, `consecutive_transient_fail_runs >= 3` for AC-2; `exceeded == False`, streak 0 for AC-1 — and the primary envelope's `flakiness_emissions` names **exactly** the AC(s) the substrate finds exceeded;
- the FR-P2-9 cross-check over a green plan pair (identical content) → `green`, matching `qa-envelope.yaml`; and over a drift plan pair (differing only at AC-2's `heuristic_applicability`) → `drift-detected` with `drift_surfaces == ("heuristic_applicability",)` and `drifted_ac_ids == ("AC-2",)`, matching `qa-envelope-rederivation-drift.yaml`.

This makes the epic AC's "plan re-derivation cross-check fires green on a clean run and drift-detected on a fixture with mutated qa-runbook … flakiness threshold fires on a multi-run fixture" a literally-reproduced fact, not a hand-drawn claim. The test reads `docs/reference-runs/20-4-web/` as DATA — it introduces no runtime↔harness cross-reference (`pluggability-gate` stays green), modifies no existing test, and is the ONE intentional gate-input shift this story makes (a +7-case pytest witness, AC-11/AC-12).

## Deterministic-termination witness

- **Terminal state:** `merge-ready` per `_bmad/automation/run-state.yaml` post-run. Not `in-flight`, not `crashed`. Both Epic-20 markers are story-level evidence and do NOT escalate the terminal.
- **Orphan-state check:** `/bmad-automation status sample-qa-coverage-001` post-run shows `merge-ready`; no `orphan-run-state-detected` marker fired (Story 8.5 substrate).
- **Branch lifecycle:** the per-story branch `bmad-autopilot/sample-qa-coverage-001` was created cleanly via `create_story_branch` (Story 2.3); the merge-ready PR bundle was assembled.
- **Retries:** no WHOLE-STORY retries — `is_retry_present: false`; clean first-pass. AC-2's action-level transient retries are the Playwright-native tier (DISTINCT from the orchestrator whole-story retry budget, which was not consumed) — and that two-tier distinction is exactly what the flakiness signal captures.

## PR bundle surface witness

- **FR-P2-9 cross-check line:** `pr-bundle.md` § `## Per-AC results` renders `> FR-P2-9 cross-check: green` co-located with the RETAINED FR25 compromise blockquote (Story 20.1 retain-and-accompany).
- **Flakiness threshold marker:** `pr-bundle.md` § `### Flakiness threshold exceeded` carries the AC-2 diagnostic prose + the `<!-- bmad-automation:marker flakiness-threshold-exceeded -->` comment (`grep -c` → 1).
- **Drift marker:** `pr-bundle.md` § Drift-run excerpt carries the `### Plan re-derivation drift detected` H3 + the `<!-- bmad-automation:marker plan-rederivation-drift-detected -->` comment (`grep -c` → 1) + the diagnostic items (story_id / drift_surfaces / drifted_ac_ids).
- **4-layer review section preserved:** `pr-bundle.md` § `## Review summary` enumerates `blind` / `edge` / `auditor` / `lad`; `failed_layers: []`; the `lad` cost-partition row is present in `## Cost telemetry`.
- **Cost partition unchanged:** per-specialist × per-retry; total $2.39 < NFR-P1 $3; neither Epic-20 surface adds a cost row.

## Phase 1 / Phase 1.5 / Phase 2 invariants witnessed

| Invariant | Status | Evidence |
|---|---|---|
| Loud-fail doctrine (Pattern 5) | ✓ held | The two Epic-20 markers landed at their per-AC location greppably; the two `heuristic-skipped` markers in the loud-fail block. Zero silent skips. |
| Sensor-not-advisor (FR52 / FR53) | ✓ held | Both `qa-envelope*.yaml` carry no `next_action` / `recommendation` (verified by `envelope-validator` + the schema's `not.anyOf` clause); the cross-check + threshold emissions are sensor data — they do NOT flip `ac_results`. |
| Envelope schema conformance (AC-6) | ✓ held | Both QA envelopes validate against the unmodified `schemas/envelope.schema.yaml` — the primary exercises `plan_rederivation` (green) + `flakiness_emissions`; the drift envelope exercises the `$defs/plan_rederivation` conditional drift branch. `envelope-validator` reports zero errors (see Debug Log References). |
| Flakiness-log schema conformance (AC-4/AC-6) | ✓ held | `qa-flakiness-log.yaml` validates against the unmodified `schemas/qa-flakiness-log.yaml`; `flakiness-log-validator` exit 0. |
| Substrate-replay faithfulness (AC-7) | ✓ pinned | `tests/test_reference_run_20_4.py` replays the committed artifacts through `evaluate_ac_flakiness` + `surface_plan_rederivation_cross_check` + `load_flakiness_log`/`validate_flakiness_log` and reproduces the witnessed verdicts. |
| Marker-taxonomy closed-set | ✓ preserved | This story emits NO new marker class and bumps NO schema_version — `plan-rederivation-drift-detected` + `flakiness-threshold-exceeded` (taxonomy `1.17`, 41 classes) were landed by 20.1/20.3; 20.4 consumes them AS-IS. |
| Pluggability invariant (FR62) | ✓ held | The 4-layer dispatch exercises all four wrapper specialists; no specialist file references another. The one new harness test reads `docs/reference-runs/` as data — no runtime↔harness cross-reference. |
| LAD-enabled 4-layer posture preserved | ✓ held | `review-bmad-envelope.yaml` enumerates `blind` / `edge` / `auditor` / `lad`; `pr-bundle.md` carries the four-layer review section + the `lad` cost row — the `19-6-web` baseline posture is not regressed by the row migration. |

## Environment notes (Story 7.9 EnvironmentNotes shape)

```yaml
claude_code_version: "2.1.32"
os_label: "darwin-25.5.0"
hardware_tier: "developer-laptop-apple-silicon"
python_version: "3.12.5"
node_version: "22.4.1"
lad_mcp_version_floor: "bb47e9e"  # Shelpuk-AI-Technology-Consulting/lad_mcp_server short-SHA per ADR-008
lad_primary_model: "moonshotai/kimi-k2-thinking"  # default reported by the LAD MCP server
lad_secondary_model: "minimax/minimax-m2.7"  # OPENROUTER_SECONDARY_REVIEWER_MODEL default per ADR-008
lad_api_key_env_var_name: "OPENROUTER_API_KEY"  # NAME-only capture; VALUE never recorded per NFR-S1
playwright_mcp_version: "0.0.x"  # @playwright/mcp via npx-stdio
target_platform: "web (chromium via playwright-mcp default)"
```

(No `axe-core` / `pixelmatch` floors are load-bearing for the Epic-20 witness — the two Epic-20 surfaces are pure in-wrapper substrate with no new dependency. This reference-run story changes NO `dependencies.yaml` entry; the floors are recorded in `19-6-web`'s environment notes as Epic-19 context.)

## Execution notes (redaction discipline — per AC-10)

Per the NFR-S1 NAME-not-VALUE rule: the captured artifacts MAY contain the `OPENROUTER_API_KEY` env-var NAME (acceptable) but MUST NOT contain the key VALUE. The post-capture scan:

```
grep -rE "sk-or-v1-[A-Za-z0-9_-]+" docs/reference-runs/20-4-web/
```

returns zero hits. No redaction was required — the `claude mcp add` / `claude mcp list` output renders the env-var-flag literal (`-e OPENROUTER_API_KEY="$OPENROUTER_API_KEY"`) which is shell-variable-reference syntax (NAME-only, never expanded to VALUE in this captured rendering). The `qa-flakiness-log.yaml` `evidence_ref` pointers cite the gitignored `_bmad-output/qa-evidence/<story-id>/<run-id>/` tree (NFR-O3 trace linkability) without committing any evidence binary; the records honor the NFR-S2 `MaskedSelectorPolicy` posture (captured evidence flows through the existing masked-selector redaction AS-IS — no new masking surface).

## No mobile capture — the deliberate scoping decision (AC-9)

Both Epic-20 surfaces are **project-type-agnostic QA-evidence**: `qa_plan_rederivation` cross-checks the persisted-vs-re-derived `QABehavioralPlan` (identical model on web / api / mobile), and `qa_flakiness_log` / `qa_flakiness_threshold` accumulate per-AC pass/fail history regardless of driver. There is **no mobile-specific Epic-20 witness** a second directory would add — the markers, envelope fields, and substrate are byte-identical across project types. Unlike 19.6 (where a11y is web-only and the mobile heuristic subset is a genuinely distinct witness, mandating two directories), a single web reference run witnesses both FRs completely. The `mobile` row in `reference-projects.md` stays at `19-6-mobile`; the `api` row stays at `mvp-completion-evidence/journey-1`. This is recorded so a future reader does not read the single-directory capture as an omission.

## Execution date

2026-06-15 (ISO-8601; the Story 20.4 dev-completion date + the maintainer-ratification date for the committed reference-replay test).

## Discovered gaps (Story 8.7 AC-5 three-class triage discipline)

- **Missing implementation:** none. Stories 20.1–20.3 (Epic 20 QA-independence + flakiness surface) are all `done` per `_bmad-output/implementation-artifacts/sprint-status.yaml`; the prerequisite gate (Story 20.3 `done` + inner-repo CI green on the `7ab8292` merge) was confirmed before capture. The cross-check (20.1), the flakiness log (20.2), and the threshold + marker (20.3) compose cleanly.
- **Missing test:** the ONE intentional addition — `tests/test_reference_run_20_4.py` (AC-7), the maintainer-ratified reference-replay witness. Unlike 19.6's Debug-Log-only proof, the Epic-20 verdicts are deterministic substrate, so the captured records are CI-pinned. No existing test modified; no count/version assertion ripples (no `src`/schema/taxonomy/dependency/fixture changed).
- **Missing evidence capture:** the captured artifacts describe the multi-run journey conceptually and ground the Epic-20 witness in the established cart/checkout synthetic surface rather than re-capturing live subprocess streams from a maintainer-owned external project. This is the AC substitution posture (inherited through 9.6 / 10.7 / 13.7 / 19.6) — live re-capture is forward-scoped (Story 23.2 forward consumer).
- **Deferred (named-and-routed):** none. Unlike 19.6 (which renegotiated the per-heuristic cost field to `deferred-work.md`), 20.4 raises no deferral — the Epic-20 surfaces are fully landed by 20.1–20.3 and neither adds a cost partition.

## Cross-references

- `docs/reference-projects.md` — the per-project index whose web row's `Latest Run Record` cell migrates to THIS directory per Story 20.4 AC-9.
- `docs/reference-runs/19-6-web/` — the structural template for this directory's nine-file shape + the preserved historical Epic-19 QA-coverage web capture.
- `_bmad-output/implementation-artifacts/20-4-epic-20-reference-runs-flakiness-corpus-witness.md` — the story file authorizing this capture.
- `_bmad-output/implementation-artifacts/20-1-per-run-plan-re-derivation-cross-check-fr-p2-9.md` / `20-2-flakiness-log-schema-persistence-fr-p2-8.md` / `20-3-flakiness-threshold-flakiness-threshold-exceeded-marker.md` — the landed Epic-20 substrate this run witnesses.
- `_bmad-output/planning-artifacts/prd.md` — FR-P2-8 / FR-P2-9 / FR23 / FR24a / FR25 / NFR-P1 / NFR-P5 / NFR-O2 / NFR-O3 / NFR-S1 / NFR-S2 / the two-tier retry model (line 1044).
- `bmad-autopilot/schemas/envelope.schema.yaml` — the AC-6 conformance target (`plan_rederivation` + `$defs/plan_rederivation`; `flakiness_emissions` + `$defs/flakiness_emission`).
- `bmad-autopilot/schemas/qa-flakiness-log.yaml` — the AC-4/AC-6 conformance target for the committed corpus snapshot.
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/qa_plan_rederivation.py` + `qa_flakiness_log.py` + `qa_flakiness_threshold.py` — the AC-7 replay entry points.
- `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly.py` — the AC-5/AC-8 render basis (`_render_qa_plan_rederivation_line` / `_render_qa_plan_rederivation_subsection` / `_render_qa_flakiness_subsection` / `_render_cost_breakdown`).
