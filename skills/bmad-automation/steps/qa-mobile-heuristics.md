# Step: QA mobile-heuristic driving (Story 9.4 — mobile project type exploratory heuristics, FR22 + ADR-007)

## Purpose

Encode the LLM-runtime binding contract for driving the mobile-applicable exploratory heuristics against the running mobile app at step-8 dispatch time for `mobile` project types per FR22 (`_bmad-output/planning-artifacts/prd.md` line 836) + FR-P1.5-2 (`prd.md` line 928) + FR-P2-5 / ADR-010 (the seven-heuristic sweep; Story 19.2) + ADR-007 (mobile-mcp v0.0.54 server selection). Mobile drives **six of the seven** heuristics — `empty-state` / `error-state` / `auth-boundary` (the Story 4.9 MVP trio) + `large-input-boundary` / `locale-i18n-edge` / `permission-boundary` (the Story 19.2 additions) — with `rate-limit-boundary` EXCLUDED per the ADR-010 matrix (silent exclusion, no marker). The Python substrate at `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/mobile_heuristic_spec.py` is pure DATA — the closed six-entry `MOBILE_HEURISTIC_SPECS` table re-binds mobile-specific scenarios to `HeuristicKind` AS-IS. THIS prose IS the binding contract that documents the per-kind mobile driving procedure the QA wrapper composes at AC-iteration-completion time AGAINST Story 9.3's ten-method `MobileDriver` Protocol surface.

This sub-step file is composed BY the QA wrapper (Story 4.13 + Story 9.3 + Story 9.4 thickening) AT step-8 dispatch time AFTER the per-AC `iterate_acs` loop (step 6) has completed AND the per-AC tier-decision (step 7) has been emitted. Heuristics fire ONLY when the plan declares them applicable per `evaluate_heuristic_applicability` from Story 4.9; the structurally-inapplicable branch surfaces `heuristic-skipped: <kind>` via `surface_heuristic_skipped` AS-IS — the substrate is project-type-agnostic by Story 4.9 design.

## Pre-condition

The QA wrapper has dispatched through `agents/qa.md` step 6's mobile branch (Story 9.3) AND the per-AC `iterate_acs` loop has completed AND the wrapper has reached step 8's heuristic dispatch. Before invoking THIS step's procedure, the QA wrapper MUST have:

- A loaded `MarkerClassRegistry` carrying the `heuristic-skipped` marker class (from `loud_fail_harness.specialist_dispatch.load_marker_class_registry`; consumed AS-IS from `schemas/marker-taxonomy.yaml` line 108 — Phase 1 taxonomy v1 closed-set member).
- The parsed `QABehavioralPlan` from the story doc's `## QA Behavioral Plan` section (Story 4.1's `persist_or_reuse_plan` output) — `evaluate_heuristic_applicability` reads ONLY `plan.entries[*].heuristic_applicability`.
- A `MobileDriver` Protocol implementation (Story 9.3's `mobile_driver.MobileDriver`) per `iterate_acs`'s driver-dispatch surface; reused AS-IS for the verb-level heuristic driving.
- A constructed `EvidenceCapturer` rooted at `_bmad-output/qa-evidence/{story-id}/{run-id}/` (Story 4.12) — heuristic-finding evidence (a11y-tree JSON snapshots + screenshot binary) persists via the same `EvidenceCapturer` the AC-iteration loop uses.

## Procedure — HeuristicKind ↔ mobile scenario mappings

The six-row mapping table (six of seven — `rate-limit-boundary` excluded on mobile per ADR-010) the QA wrapper consumes at step-8 dispatch time. BYTE-IDENTICAL with the `mobile_heuristic_spec.MOBILE_HEURISTIC_SPECS` constant per the Story 9.4 AC-5 drift-prevention rule (extended at Story 19.2; mirroring Story 9.3 AC-2's ten-method ↔ MCP-tool mapping byte-identicality).

| HeuristicKind | mobile scenario label | driver methods used |
|---|---|---|
| `auth-boundary` | session-expiry boundary | `launch_app`, `press_button`, `screenshot`, `assert_element_present` |
| `empty-state` | empty-list state | `launch_app`, `tap_at_coordinates`, `list_elements_on_screen`, `assert_element_present` |
| `error-state` | network-error state | `launch_app`, `tap_at_coordinates`, `screenshot`, `assert_element_present` |
| `large-input-boundary` | large-input boundary state | `launch_app`, `tap_at_coordinates`, `type_text`, `screenshot`, `assert_element_present` |
| `locale-i18n-edge` | locale/i18n edge state | `launch_app`, `tap_at_coordinates`, `screenshot`, `assert_element_present` |
| `permission-boundary` | permission-denied boundary | `launch_app`, `tap_at_coordinates`, `screenshot`, `assert_element_present` |

`rate-limit-boundary` is the seventh exploratory heuristic (ADR-010 / FR-P2-5); it is **EXCLUDED on mobile** per the ADR-010 applicability matrix — rapid-request driving is impractical through the mobile-MCP v0.0.54 UI verb surface (no rapid-request primitive in the ten-method `MobileDriver` Protocol). The exclusion is a SILENT matrix exclusion (NO `heuristic-skipped` emission), so `MOBILE_HEURISTIC_SPECS` carries six entries (six of seven), not seven.

The `auth-boundary` row binds to **session-expiry** rather than **biometric-auth-boundary** because mobile-mcp v0.0.54's ten-method verb set (Story 9.3 AC-2) does not expose a biometric-prompt verb (Touch ID / Face ID / Android Biometric prompts require simulator-specific commands outside the mobile-mcp tool surface). Session-expiry is observable via the `screenshot` + `assert_element_present` pair AND is a higher-empirical-value coverage target per the web-research notes at story-create time 2026-05-11. The decision is recorded in the `mobile_heuristic_spec.py` module docstring's "Heuristic-binding rationale" sub-section.

## Procedure — per-kind driving outlines

### Empty-list state

Launch the app via launch_app to a list-bearing screen; navigate to the empty-state condition (cleared filters / no records) via tap_at_coordinates; capture the a11y tree via list_elements_on_screen and verify the empty-state UI's accessible label is present via assert_element_present.

### Network-error state

Launch the app via launch_app to a network-dependent screen; provoke the network-error path by interacting via tap_at_coordinates while the device is offline (practitioner toggles airplane mode out-of-band — see qa-mobile-heuristics.md); capture the post-failure screenshot via screenshot and verify the error-state UI's accessible label is present via assert_element_present.

The out-of-band airplane-mode toggling is required because the mobile-mcp v0.0.54 verb set does NOT expose a `mobile_set_network_state` analog per the deliberately-deferred-methods list at `qa-driver-mobile.md` line 39. The practitioner toggles the device's network state via OS-level controls (iOS Control Center / Android Quick Settings on a connected device; `xcrun simctl status_bar booted override --dataNetwork wifi --wifiBars 0` or equivalent on iOS Simulator; `adb shell svc data disable && adb shell svc wifi disable` on Android emulators) BEFORE the wrapper invokes the heuristic.

### Session-expiry boundary

Launch the app via launch_app to a route requiring an authenticated session; force session-expiry by pressing the HOME button via press_button then re-foregrounding after the configured session-TTL; capture the post-expiry screenshot via screenshot and verify the session-expiry UI's accessible label is present via assert_element_present.

The session-TTL is configured by the practitioner in the runbook-or-app-config; the wrapper does NOT discover or alter the TTL — heuristic driving observes the post-TTL UI state via the `screenshot` + `assert_element_present` pair. The re-foregrounding step composes the same `launch_app` method to bring the app back to foreground AFTER the configured TTL has elapsed.

### Large-input boundary state

Launch the app via launch_app to a screen bearing a free-text input; focus the field via tap_at_coordinates and enter a very large input string via type_text that exceeds the field's expected bound; capture the post-entry screenshot via screenshot and verify the large-input-boundary handling UI (length-cap or validation affordance) accessible label is present via assert_element_present.

### Locale/i18n edge state

Launch the app via launch_app after the practitioner sets a non-default device locale out-of-band (see qa-mobile-heuristics.md); navigate to a locale-sensitive screen via tap_at_coordinates; capture the localized-layout screenshot via screenshot and verify the locale/i18n edge UI (translated string or RTL mirroring) accessible label is present via assert_element_present.

The non-default locale is set out-of-band because the mobile-mcp v0.0.54 verb set does NOT expose a locale-switching analog. The practitioner sets the device/simulator locale via OS-level controls (Settings → General → Language & Region on iOS; `adb shell am broadcast … com.android.intent.action.SET_LOCALE` / Settings on Android) BEFORE the wrapper invokes the heuristic.

### Permission-denied boundary

Launch the app via launch_app to a screen whose primary action requires a runtime OS permission the practitioner has denied out-of-band (see qa-mobile-heuristics.md); invoke the permission-gated action via tap_at_coordinates; capture the post-denial screenshot via screenshot and verify the permission-denied fallback UI's accessible label is present via assert_element_present.

The permission grant/denial is set out-of-band because the mobile-mcp v0.0.54 verb set does NOT expose a permission-toggling analog. The practitioner denies the relevant runtime permission via OS-level controls (Settings → Privacy on iOS; `adb shell pm revoke <pkg> <permission>` on Android) BEFORE the wrapper invokes the heuristic.

## Procedure — applicability gating + skip emission

For each mobile-applicable `HeuristicKind` ∈ `{empty-state, error-state, auth-boundary, large-input-boundary, locale-i18n-edge, permission-boundary}` (the six of seven mobile drives — `rate-limit-boundary` is matrix-excluded per ADR-010, a SILENT exclusion with NO `heuristic-skipped` emission), the wrapper calls `evaluate_heuristic_applicability(plan, kind)` from `loud_fail_harness.qa_exploratory_heuristics` (Story 4.9). The function reads ONLY `plan.entries[*].heuristic_applicability` — same logic for web/api/mobile per FR16 invariant; mobile dispatch does NOT alter the decision semantics.

On the structurally-inapplicable branch (return `False`), the wrapper calls `surface_heuristic_skipped(story_id, heuristic_kind, registry)` from Story 4.9's `qa_exploratory_heuristics.py` — the same Pattern-5 atomic-on-failure helper produces a `HeuristicSkippedEmission` carrying the marker record (canonical marker class `"heuristic-skipped"` + `sub_classification` matching the kind label) + diagnostic context (`story_id` + `heuristic_kind`). The emission rides on the envelope's `heuristic_skipped_emissions` array per `agents/qa.md`'s envelope contract. NO mobile-specific emission helper exists — the substrate is project-type-agnostic by Story 4.9 design (the mobile-scenario rebinding is documented in `MobileHeuristicSpec.mobile_scenario_label`, NOT in the marker sub-classification taxonomy).

## Procedure — applicable-branch finding construction

When `evaluate_heuristic_applicability` returns `True` for a given kind, the wrapper drives the heuristic per the per-kind procedural outline above:

1. **Execute the `procedural_outline` against the `MobileDriver` Protocol surface.** Drive the heuristic per the `MobileHeuristicSpec.procedural_outline` prose for the matching kind — the prose is authoritative for call order and out-of-band steps (e.g., the second `launch_app` re-foregrounding call in the session-expiry boundary). `MobileHeuristicSpec.driver_methods_used` is a membership declaration (the distinct Protocol methods involved), not an invocation sequence. For example, for `empty-state`: `launch_app(package_name)` → `tap_at_coordinates(x, y)` (navigate to empty state) → `list_elements_on_screen()` → `assert_element_present(label)`. The wrapper composes against `MobileDriver` AS-IS — the same Protocol surface `iterate_acs` already uses at step 6 for per-AC verification.

2. **Observe heuristic-relevant deviations.** On observation of a deviation (e.g., the empty-state UI lacks an accessible-label; the network-error UI surfaces no retry affordance; the session-expiry UI fails to redirect to the auth route), the wrapper constructs a finding dict carrying the deviation. Finding shape conforms to `$defs/finding` at `schemas/envelope.schema.yaml` (id, source, title, detail, location, bucket, severity); `source: "qa"`, `bucket: "decision_needed"` per FR24a's verification-fail routing (heuristic findings imply semantic drift, not localized fix-targets), severity `MED` (heuristic findings are exploratory; AC-driven findings carry the smoke-first HIGH severity).

3. **Tag with the `verification_mode` discriminator.** Call `tag_heuristic_finding(finding)` from Story 4.9's `qa_exploratory_heuristics.py` — sets `verification_mode: "exploratory-heuristic"` per the cell-1 schema bump from Story 4.9 AC-1 (the discriminator the bundle assembler partitions on). The function is project-type-agnostic; no mobile-specific tagging behavior.

4. **Append to the envelope's TOP-LEVEL `findings` array.** Heuristic findings DO NOT pollute `ac_results[i].findings` — they are story-level not AC-level per FR22 + the verbatim epic AC at `epics.md` line 2079; the bundle assembler's `### Exploratory heuristic findings` H3 sub-section partitions on `verification_mode` AS-IS per Story 4.9 AC-9. Mobile findings flow through identically to web/api findings — no envelope-shape divergence.

## Failure mode — mobile-mcp-unavailable mid-heuristic

When any `MobileDriver` method invocation during the heuristic's driving raises `MobileMcpUnavailable` (Story 9.3's exception type), the wrapper follows the SAME failure-mode protocol as `qa-driver-mobile.md` § Failure mode — mobile-mcp-unavailable mid-run:

- **Catch the exception.** Wrap each `MobileDriver` method invocation inside the heuristic's driving in a try/except that catches `MobileMcpUnavailable`.

- **Surface via the substrate library.** Call `surface_mobile_mcp_unavailable(story_id, registry, action_kind=<failed-driver-method-name>, prior_evidence_refs=<already-captured>)` from `loud_fail_harness.mobile_driver`. The `<failed-driver-method-name>` is the action the wrapper was performing when the exception fired (one of `launch_app | tap_at_coordinates | press_button | screenshot | list_elements_on_screen | assert_element_present`). The `<already-captured>` argument is the tuple of repo-relative evidence_ref paths the `EvidenceCapturer` had already produced for the current heuristic BEFORE the unavailability fired.

- **Forward the structured emission.** The structured `MobileMcpUnavailableEmission` rides on the envelope's `marker_emissions` array per `agents/qa.md` step 6's marker-flow protocol; the bundle assembler's QA-section render surfaces the `<!-- bmad-automation:marker mobile-blocked -->` comment + the diagnostic prose co-located.

- **Abort the current heuristic; proceed to the next applicable heuristic.** The heuristic is aborted and contributes no finding. The wrapper proceeds to the next applicable heuristic kind (does NOT abort the entire step-8 dispatch). NO smoke-first-abort for heuristics — the FR22b smoke-first-abort discipline applies to AC iteration in step 6, NOT to heuristic execution in step 8; heuristic-level mid-run unavailability surfaces the `mobile-blocked` marker via the AC-iteration seam already (Story 9.3 owns the marker class linkage).

## AC-22b smoke-first-abort discipline (witness)

THIS step's procedure is invoked AFTER `iterate_acs` returns from step 6 — i.e., if AC-1 fails, the wrapper aborts at step 6 BEFORE reaching step 8; the heuristics are NEVER driven on a smoke-first-aborted run (parallel to web/api). The witness cross-reference: `agents/qa.md` step 6's smoke-first-abort surface + the Story 4.6 `surface_smoke_first_abort` emission helper (which emits the `smoke-first-abort: AC-1-failed` marker AT the AC-iteration seam BEFORE step-8 dispatch reaches THIS step). Mobile heuristic execution respects this invariant by construction; no mobile-specific smoke-first-abort variant exists.

## Composed substrate primitives

- `loud_fail_harness.mobile_heuristic_spec.MOBILE_HEURISTIC_SPECS` (Story 9.4)
- `loud_fail_harness.mobile_heuristic_spec.MobileHeuristicSpec` (Story 9.4)
- `loud_fail_harness.mobile_heuristic_spec.get_mobile_heuristic_spec` (Story 9.4)
- `loud_fail_harness.qa_exploratory_heuristics.evaluate_heuristic_applicability` (Story 4.9)
- `loud_fail_harness.qa_exploratory_heuristics.surface_heuristic_skipped` (Story 4.9)
- `loud_fail_harness.qa_exploratory_heuristics.tag_heuristic_finding` (Story 4.9)
- `loud_fail_harness.qa_exploratory_heuristics.HeuristicKind` (Story 4.9 — single source of truth)
- `loud_fail_harness.qa_exploratory_heuristics.EXPLORATORY_HEURISTIC_VERIFICATION_MODE` (Story 4.9)
- `loud_fail_harness.qa_exploratory_heuristics.HEURISTIC_SKIPPED_MARKER` (Story 4.9)
- `loud_fail_harness.mobile_driver.MobileDriver` (Story 9.3 — ten-method Protocol surface)
- `loud_fail_harness.mobile_driver.MOBILE_BLOCKED_MARKER` (Story 9.3)
- `loud_fail_harness.mobile_driver.surface_mobile_mcp_unavailable` (Story 9.3 — mid-heuristic failure mode)
- `loud_fail_harness.specialist_dispatch.MarkerClassRegistry` + `validate_marker_emission` (Story 2.6 — consumed by `surface_heuristic_skipped` for atomic-on-failure registry validation)
- `loud_fail_harness.qa_behavioral_plan.QABehavioralPlan` + `QABehavioralPlanEntry` (Story 4.1 — the plan structure `evaluate_heuristic_applicability` reads)

## Forward consumers

- **Story 9.5 (LANDED) — init-time + mid-run `mobile-blocked` paths.** Consumes the `MobileMcpUnavailableEmission` surfaced when a heuristic's driver invocation fails mid-run (the emission carries `sub_cause="mid-run-unavailable"` per the marker-taxonomy 1.5 closed-set). The diagnostic-pointer destination at `docs/mobile-mcp-setup.md` is now landed.
- **Story 9.6 — reference mobile-project fixture end-to-end run.** Composes against THIS step's six-heuristic mobile protocol end-to-end on a real reference mobile project; exercises the full per-kind driving procedure against the running app.
- **Epic 11 — Phase 1.5 completion evidence.** References THIS step as the FR-P1.5-2 + FR22 mobile-extension evidence in `phase-1.5-completion-evidence.md` (Story 11.1's deliverable).
