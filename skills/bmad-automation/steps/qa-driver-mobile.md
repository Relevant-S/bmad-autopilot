# Step: QA driver — Mobile MCP (Story 9.3 — mobile project type, FR17 + ADR-002 graceful-degrade + ADR-007 server selection)

## Purpose

Encode the LLM-runtime protocol for invoking the substrate's `MobileDriver` Protocol against the Claude Code `mobile_*` mobile-mcp tool surface at AC-iteration time for `mobile` project types per FR17 (`_bmad-output/planning-artifacts/prd.md` line 851 — "QA drives the running product independently — via mobile MCP for mobile project types per ADR-007 / Phase 1.5") + FR-P1.5-2 (`prd.md` line 928 — Mobile QA via mobile MCP). The Python substrate at `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/mobile_driver.py` is pure and CANNOT itself invoke MCP tools — that is structurally an LLM-runtime concern bound to the QA wrapper's prompt-execution context per ADR-004's substrate-vs-LLM-runtime split. THIS prose IS the binding contract that names the ten `MobileDriver` Protocol methods ↔ `mobile_*` MCP tool mappings + the provisioner runtime bindings + the failure-mode procedures.

This sub-step file is composed BY the QA wrapper (Story 4.13 + Story 9.3 thickening) AT AC-iteration time AFTER the orchestrator's env-provisioning seam (`steps/env-provisioning.md`) has produced the `provisioned_env` carrier with `env_kind="mobile"`. The mobile MCP itself is an out-of-band npx-stdio process Claude Code manages (ADR-007 Consequence 6) — NOT an Automator-spawned dev-server subprocess; THIS step's binding contract therefore does not include a `DevServerRunner` analog (parallel to how `qa-driver-http.md` does not own dev-server teardown for ephemeral test envs).

## Pre-condition

The orchestrator's env-provisioning seam (Story 4.3's `steps/env-provisioning.md`, Story 9.3 extension) has produced the `provisioned_env` carrier with `env_kind="mobile"` AND the QA dispatch payload has been delivered to the QA wrapper. Before invoking THIS step's procedure, the QA wrapper MUST have:

- A loaded `MarkerClassRegistry` carrying the `mobile-blocked` marker class (from `loud_fail_harness.specialist_dispatch.load_marker_class_registry`; consumed AS-IS from `schemas/marker-taxonomy.yaml` line 114 — Phase 1 taxonomy v1 closed-set member).
- The dispatched `provisioned_env` from the dispatch payload's `provisioned_env` carrier (Story 4.3's seam contract; for mobile the shape is `{env_kind: "mobile", port: 0, pid: 0, started_at: ..., health_url: null}` — `port`/`pid` are not-applicable sentinels because the mobile MCP is npx-stdio-managed by Claude Code, not Automator-spawned).
- The story's `ac_list` from the dispatch payload (FR16 — the single QA-side input channel).
- The parsed `QABehavioralPlan` from the story doc's `## QA Behavioral Plan` section (Story 4.1's `persist_or_reuse_plan` output; consumed verbatim).
- The `qa-runbook.yaml` stub at `_bmad/automation/qa-runbook.yaml` (Story 7.5 + Story 9.3 extension). The wrapper reads the `mobile_app_package_name` field at provision-time (consumed by the `MobileDriver.launch_app` call at AC-iteration start — REQUIRED for `mobile` project type; the practitioner sets this once per project per Story 9.3 AC-8) and the `masked_selectors` field at AC-iteration time (consumed by the mobile-specific `MaskedSelectorPolicy` runtime binding below).
- A constructed `EvidenceCapturer` rooted at `_bmad-output/qa-evidence/{story-id}/{run-id}/` per FR49 (Story 4.12 owns the evidence-persistence size budgets; THIS step writes the evidence verbatim — a11y-tree JSON snapshots + screenshot binary).

## Procedure — MobileDriver Protocol ↔ MCP tool mappings

The ten `MobileDriver` Protocol methods ↔ mobile-mcp v0.0.54 tool surface bindings the QA wrapper composes against at AC-iteration time:

| MobileDriver method                                                                                        | mobile-mcp tool                                          |
|------------------------------------------------------------------------------------------------------------|----------------------------------------------------------|
| `launch_app(package_name)`                                                                                 | `mobile_launch_app`                                      |
| `terminate_app(package_name)`                                                                              | `mobile_terminate_app`                                   |
| `tap_at_coordinates(x, y)`                                                                                 | `mobile_click_on_screen_at_coordinates`                  |
| `swipe(direction)` where `direction ∈ {up, down, left, right}`                                             | `mobile_swipe_on_screen`                                 |
| `type_text(text, *, submit=False)`                                                                         | `mobile_type_keys`                                       |
| `press_button(button)` where `button ∈ {HOME, BACK, ENTER, VOLUME_UP, VOLUME_DOWN}`                        | `mobile_press_button`                                    |
| `screenshot(name)`                                                                                         | `mobile_take_screenshot`                                 |
| `list_elements_on_screen()` → `tuple[MobileElement, ...]`                                                  | `mobile_list_elements_on_screen`                         |
| `assert_element_present(label)` → `MobileDriverAssertion`                                                  | `mobile_list_elements_on_screen` + textual comparison    |
| `get_screen_size()` → `tuple[int, int]`                                                                    | `mobile_get_screen_size`                                 |

The mapping table is BYTE-IDENTICAL with the `mobile_driver.py` module docstring's mapping table per the Story 9.3 AC-2 drift-prevention rule (mirroring Story 4.4's `qa-driver-playwright.md` + Story 4.5's `qa-driver-http.md` convention). The `assert_element_present` method composes the `mobile_list_elements_on_screen` call + a substring-match against the returned `MobileElement.label` field; the comparison result is recorded in a `MobileDriverAssertion(passed=..., observed=..., expected=...)` instance returned to the caller. Mobile's primary interaction modality is coordinate-based — the wrapper resolves coordinates via `list_elements_on_screen` AND THEN dispatches `tap_at_coordinates(element.x + element.width // 2, element.y + element.height // 2)` for centered taps.

Methods NOT exposed are **deliberately deferred** (not "missing"): `mobile_install_app`, `mobile_uninstall_app`, `mobile_open_url`, `mobile_list_apps`, `mobile_list_available_devices`, `mobile_get_orientation`, `mobile_set_orientation`, `mobile_double_tap_on_screen`, `mobile_long_press_on_screen_at_coordinates`, `mobile_save_screenshot`. The narrowing parallels FR22's three-heuristic narrowing rationale — the wrapper composes against a small stable verb set; future reference-project gaps trigger additions in a future story, NOT silent inclusion at first cut.

## Procedure — provisioner runtime bindings

The `MobileMcpAvailabilityProbe` Protocol runtime binding the orchestrator skill composes at provision-time (BEFORE QA dispatch):

- **`MobileMcpAvailabilityProbe.is_available()`** — one MCP-tool ping. The orchestrator MUST perform a single trivial call to a no-side-effect mobile-mcp tool (e.g., `mobile_get_screen_size()` — a read-only no-side-effect tool that succeeds iff a device is connected AND the mobile MCP is reachable). On any tool-error, tool-absence, or timeout, return `False`. On clean tool-call return, return `True`.

- **`MobileMcpProvisioner.provision()`** — DOES NOT spawn a dev-server subprocess (mobile MCP is npx-stdio-managed by Claude Code per ADR-007 Consequence 6). The Provisioner returns a `ProvisionedEnv(env_kind="mobile", port=0, pid=0, started_at=<utc-now>, health_url=None)` shape (port/pid are zero-sentinels by design; the mobile MCP exposes no HTTP health endpoint). On probe-`False` raises `MobileMcpLaunchFailed(failure_step="mobile-mcp-init-unreachable")` which Story 4.3's `provision_env` catches via `getattr(exc, "failure_step", "dev-server-not-ready")` and routes through `surface_env_setup_failure(sub_cause="mobile-mcp-init-unreachable")` per the extended `EnvSetupFailureSubCause` enum (Story 9.3 AC-6).

- **`MobileMcpTeardown.teardown(provisioned_env)`** — a NO-OP. The npx-stdio mobile MCP process is Claude-Code-managed, NOT Automator-spawned, so there is no Automator-side process termination to perform.

## Failure mode — mobile-mcp-unavailable mid-run

When any `mobile_*` tool-call raises during AC verification (e.g., the MCP tool surface becomes unreachable mid-AC-iteration; the connected device disconnects; the mobile MCP process exits), the QA wrapper MUST follow the failure-mode protocol:

- **Catch the tool-call exception.** Wrap each `mobile_*` invocation inside the AC-iteration loop in a try/except that catches the underlying tool-error.

- **Surface via the substrate library.** Call `surface_mobile_mcp_unavailable(story_id, registry, action_kind=<failed-action>, prior_evidence_refs=<already-captured>)` from `loud_fail_harness.mobile_driver`. The `<failed-action>` argument is the action name the wrapper was performing when the exception fired (one of `launch_app | terminate_app | tap_at_coordinates | swipe | type_text | press_button | screenshot | list_elements_on_screen | assert_element_present | get_screen_size`). The `<already-captured>` argument is the tuple of repo-relative evidence_ref paths the `EvidenceCapturer` had already produced for the current AC BEFORE the unavailability fired — preserved per the mobile-parallel of the verbatim epic AC at epics.md line 1912 ("evidence already captured is preserved").

- **Marker class.** The substrate's `surface_mobile_mcp_unavailable` validates the `MOBILE_BLOCKED_MARKER` (`"mobile-blocked"` from `schemas/marker-taxonomy.yaml` line 114) against the registry FIRST (atomic-on-failure per Pattern 5; registry rejection raises `UnknownMarkerClass` BEFORE any partial state). On success, the function returns a `MobileMcpUnavailableEmission` carrying the `MarkerEmissionRecord` + the `MobileMcpUnavailableDiagnostic` with `(story_id, action_kind, prior_evidence_refs)`. The marker carries `sub_classifications: [init-unavailable, mid-run-unavailable]` per taxonomy v1.5 (Story 9.5). The mid-run path emits `sub_classification: mid-run-unavailable` via `MOBILE_BLOCKED_MID_RUN_SUB_CLASSIFICATION`; the init-time path emits `sub_classification: init-unavailable` via the `dependencies.yaml` declaration. Unlike `playwright-mcp-unavailable`, `mobile-blocked` has two distinct sub_classifications.

- **Abort the current AC's verification.** Set the AC's `AcResult.status` to `"blocked"` AND populate the `evidence_refs` tuple with the `prior_evidence_refs` that were already captured. The `assertions` tuple records the diagnostic ("mobile-mcp-unavailable mid-run during action_kind=<X>"). The wrapper continues to the next AC (or aborts the iteration loop entirely per Story 4.6's plan-driven AC iteration policy).

- **Forward the structured emission.** Surface the `MobileMcpUnavailableEmission` via the existing terminal-stream + bundle-render paths so Story 4.10's escalation routing consumes it. The substrate library does NOT itself emit to the terminal; the QA wrapper or downstream Story 4.10 consumes the emission and routes through the verification-fail / env-setup-fail escalation contracts. THIS step's responsibility ends at producing the structured emission; Story 4.10 routes it.

## Failure mode — mobile-mcp-init-unreachable at provisioning

When `MobileMcpProvisioner.provision` raises `MobileMcpLaunchFailed` AT init-time-of-provisioning (i.e., the `MobileMcpAvailabilityProbe.is_available()` returned `False` BEFORE any AC verification), the routing chain is:

- **`MobileMcpLaunchFailed.failure_step`.** The exception's `failure_step` attribute equals the literal string `"mobile-mcp-init-unreachable"` byte-for-byte (mirroring `schemas/marker-taxonomy.yaml`'s `env-setup-failed.sub_classifications` enum member appended by Story 9.3).

- **Story 4.3's `provision_env` catches it.** The wrapper at `loud_fail_harness.env_provisioning.provision_env` reads the `failure_step` attribute via `getattr(exc, "failure_step", "dev-server-not-ready")` and routes through `surface_env_setup_failure` with `sub_cause="mobile-mcp-init-unreachable"` per Story 4.3's `EnvSetupFailureSubCause` enum (Story 9.3 extension).

- **The orchestrator stays at `current_state="review"`.** Per Story 4.3's `steps/env-provisioning.md` § Failure mode — env-setup-fail (the verbatim epic AC at epics.md line 1881 — "the story does NOT enter the `qa` state — remains in `review`"); `commit_transition` is NEVER called on this branch. The QA wrapper is NEVER dispatched on this branch — the failure surfaces at the orchestrator side BEFORE QA receives the dispatch payload.

This routing chain is structurally distinct from the mid-run unavailability failure mode above: AT-INIT-time goes through `env-setup-failed.mobile-mcp-init-unreachable` (Story 9.3's marker sub-classification); MID-RUN goes through `mobile-blocked` (Story 9.3's marker class). The two are deliberately separate per the marker-taxonomy entries to reflect the differing remediation paths (init: mobile-MCP installation / device-connection issue → setup pointer at `docs/mobile-mcp-setup.md`, landed by Story 9.5; mid-run: transient connectivity loss).

Distinct from the **`mobile-blocked.init-unavailable`** path landed by Story 9.5 — that path fires at `/bmad-automation init` time (or run-start init re-probing) when `run_init_preconditions._dispatch_total_block` reads `schemas/dependencies.yaml`'s mobile-mcp mobile-init `total-block` profile and the probe returns `available=False`; the marker carries `sub_classification="init-unavailable"` per the marker-taxonomy 1.5 closed-set. The `env-setup-failed.mobile-mcp-init-unreachable` path above is the QA-dispatch-time provisioner failure, structurally downstream of the init-time precondition check — the two paths cover different lifecycle points and have different remediation paths.

## MaskedSelectorPolicy runtime application

Before persisting a11y-tree snapshots / screenshots, the `EvidenceCapturer` MUST redact content matching any selector in the `MaskedSelectorPolicy` with `MASKED_REDACTION_SENTINEL` (`"[REDACTED]"`) per the mobile-parallel of the verbatim epic AC at epics.md line 1917 ("evidence files respect masked-selector configuration if present in qa-runbook.yaml"). The mobile-specific runtime binding:

- **Read the policy at AC-iteration startup.** Read the `masked_selectors` array from `_bmad/automation/qa-runbook.yaml`; construct a `MaskedSelectorPolicy(masked_selectors=tuple(...))`. The `MaskedSelectorPolicy` class is re-exported from `mobile_driver` (single source of truth at `playwright_driver` per Story 9.3 AC-1). Empty array means "no redaction"; the substrate library short-circuits and persists payloads verbatim.

- **Mobile-specific selector semantics.** Mobile a11y trees do NOT use CSS selectors. The `masked_selectors` entries are interpreted as **a11y-label substrings**: the redaction algorithm substring-matches each selector entry against the `label` field on each `MobileElement` returned by `mobile_list_elements_on_screen` AND against any textual rendering of the a11y-tree snapshot (the JSON-serialized payload). Matched substrings are replaced with `MASKED_REDACTION_SENTINEL` BEFORE the payload is persisted under `_bmad-output/qa-evidence/{story-id}/{run-id}/`. **Matching is case-sensitive** (Python `str.replace` semantics) — practitioners must use the exact casing of the a11y label as returned by `mobile_list_elements_on_screen`; a selector of `"Password"` will NOT redact `"password input field"`.

- **Screenshot redaction.** Screenshots are binary PNG payloads — substring matching does not apply directly. THIS step's MVP-Phase-1.5 binding does NOT redact screenshot content (no OCR-based redaction at first cut); the wrapper relies on the practitioner setting up the device's screen so sensitive content is masked at the source. Future stories MAY add OCR-based screenshot redaction; revisit when reference-project flows demonstrate the need.

- **The sentinel is `"[REDACTED]"`.** The sentinel string is re-exported from `mobile_driver.MASKED_REDACTION_SENTINEL` (single source of truth at `playwright_driver`); recorded in `docs/extension-audit.md` per the no-introductions principle. Story 4.12's evidence-persistence size budgets read the post-redaction output; the sentinel is short enough that redaction does not inflate evidence size meaningfully.

## Composed substrate primitives

- `loud_fail_harness.mobile_driver.MobileMcpProvisioner` (Story 9.3)
- `loud_fail_harness.mobile_driver.MobileMcpTeardown` (Story 9.3)
- `loud_fail_harness.mobile_driver.verify_ac` (Story 9.3)
- `loud_fail_harness.mobile_driver.surface_mobile_mcp_unavailable` (Story 9.3)
- `loud_fail_harness.mobile_driver.MOBILE_BLOCKED_MARKER` (Story 9.3)
- `loud_fail_harness.mobile_driver.MaskedSelectorPolicy` + `AcResult` + `EvidenceCapturer` + `MASKED_REDACTION_SENTINEL` — RE-EXPORTED from `playwright_driver` (single source of truth per Story 9.3 AC-1).
- `loud_fail_harness.env_provisioning.provision_env` (Story 4.3) — composed by the orchestrator skill at provision-time WITH a `MobileMcpProvisioner` instance from THIS module.
- `loud_fail_harness.env_provisioning.teardown_env` (Story 4.3) — composed by the orchestrator skill at teardown-time WITH a `MobileMcpTeardown` no-op instance from THIS module.
- `loud_fail_harness.env_provisioning.surface_env_setup_failure` (Story 4.3) — receives the `MobileMcpLaunchFailed` exception via `provision_env`'s catch path on the AT-INIT-time failure; routes with `sub_cause="mobile-mcp-init-unreachable"`.
- `loud_fail_harness.specialist_dispatch.MarkerClassRegistry` + `validate_marker_emission` (Story 2.6) — composed by `surface_mobile_mcp_unavailable` for atomic-on-failure registry validation.
- `loud_fail_harness.qa_behavioral_plan.QABehavioralPlanEntry` (Story 4.1) — consumed by `verify_ac` as the per-AC plan entry carrying `assertion_shape` + `expected_evidence_tier`.

The library reads ONLY the AC + plan-entry from its `verify_ac` arguments + `qa-runbook.yaml`'s `mobile_app_package_name` / `masked_selectors` fields (consumed AT THIS step's runtime binding, NOT by the substrate library) + the running mobile product. Driver code does NOT read TEA test files, dev tests, review findings, or commit diffs (FR16 invariant; structurally encoded by the substrate library's argument lists).

The driver substrate references ONLY `loud_fail_harness.playwright_driver` (for re-exported primitives) + `loud_fail_harness.specialist_dispatch` + `loud_fail_harness.env_provisioning` + `loud_fail_harness.qa_behavioral_plan` + `loud_fail_harness.qa_evidence_tier` + Pydantic v2 + Python stdlib. NO references to Dev or Review-BMAD or future LAD specialist code (FR62 pluggability invariant; substrate-library-to-substrate-library imports are gate-safe per Story 1.10a `pluggability_gate.py` Rule 1).

## Forward consumers

- **Story 9.4 (LANDED) — mobile exploratory heuristics (three MVP-parity heuristics with `heuristic-skipped` emission)** composes against THIS story's `mobile_driver` substrate landing at AC-iteration time per the mobile-specific scenario rebinding at `skills/bmad-automation/steps/qa-mobile-heuristics.md` (Story 9.4). The `HeuristicKind` Literal is reused AS-IS; marker taxonomy v1 closed-set is preserved.
- **Story 9.5 (LANDED) — init-time + mid-run `mobile-blocked` paths** consumes the structured `MobileMcpUnavailableEmission` produced by `surface_mobile_mcp_unavailable` (which now stamps `sub_cause="mid-run-unavailable"` via `MOBILE_BLOCKED_MID_RUN_SUB_CLASSIFICATION`) AND wires the init-time emission path via `init_preconditions._dispatch_total_block` (which stamps `sub_classification="init-unavailable"` from `schemas/dependencies.yaml`'s mobile-mcp mobile-init declaration). The diagnostic-pointer destination is `docs/mobile-mcp-setup.md`, authored by THIS story.
- **Story 9.6 — reference mobile-project fixture end-to-end run** composes against THIS step's protocol end-to-end, exercising the full ten-method MobileDriver Protocol against a reference mobile project (the QA wrapper's procedural-composition end-to-end).
- **Epic 11 — Phase 1.5 completion evidence** references THIS step as the FR-P1.5-2 evidence in `phase-1.5-completion-evidence.md` (Story 11.1's deliverable).
