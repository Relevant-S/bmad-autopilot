# Step: QA driver — Playwright MCP (Story 4.4 — web project type, FR17 + ADR-002 graceful-degrade)

## Purpose

Encode the LLM-runtime protocol for invoking the substrate's `WebDriver` Protocol against the Claude Code `mcp__playwright__browser_*` tool surface at AC-iteration time for `web` project types per FR17 (`_bmad-output/planning-artifacts/prd.md` line 831 — "QA drives the running product independently — via Playwright MCP for web project types"). The Python substrate at `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/playwright_driver.py` is pure and CANNOT itself invoke MCP tools — that is structurally an LLM-runtime concern bound to the QA wrapper's prompt-execution context per ADR-004's substrate-vs-LLM-runtime split. This prose IS the binding contract that names the seven `WebDriver` Protocol methods ↔ `mcp__playwright__browser_*` tool mappings + the provisioner runtime bindings + the failure-mode procedures.

This sub-step file is composed BY the QA wrapper (Story 4.13 forthcoming wrapper thickening) AT AC-iteration time AFTER the orchestrator's env-provisioning seam (`steps/env-provisioning.md`) has produced the `provisioned_env` carrier with `env_kind="web"`. It is the binding point Stories 4.6 (plan-driven AC iteration) / 4.10 (escalation routing) / 4.12 (evidence persistence) compose against at runtime. The QA wrapper at `agents/qa.md` is NOT modified by this story — Story 4.13 owns wrapper thickening; the seam contract is preserved structurally by THIS step's placement at the wrapper-side AC-iteration point.

## Pre-condition

The orchestrator's env-provisioning seam (Story 4.3's `steps/env-provisioning.md`) has produced the `provisioned_env` carrier with `env_kind="web"` AND the QA dispatch payload has been delivered to the QA wrapper. Before invoking THIS step's procedure, the QA wrapper MUST have:

- A loaded `MarkerClassRegistry` carrying the `playwright-mcp-unavailable` marker class (from `loud_fail_harness.specialist_dispatch.load_marker_class_registry`).
- The dispatched `provisioned_env` from the dispatch payload's `provisioned_env` carrier (Story 4.3's seam contract).
- The story's `ac_list` from the dispatch payload (FR16 — the single QA-side input channel).
- The parsed `QABehavioralPlan` from the story doc's `## QA Behavioral Plan` section (Story 4.1's `persist_or_reuse_plan` output; consumed verbatim).
- The `qa-runbook.yaml` stub at `_bmad/automation/qa-runbook.yaml` (Story 7.5 will scaffold; until then the practitioner maintains it manually). The wrapper reads the `dev_server_command` field at provision-time (consumed by the `DevServerRunner` runtime binding below) and the `masked_selectors` field at AC-iteration time (consumed by the `MaskedSelectorPolicy` runtime binding below).
- A constructed `EvidenceCapturer` rooted at `_bmad-output/qa-evidence/{story-id}/{run-id}/` per FR49 (Story 4.12 owns the evidence-persistence size budgets; THIS step writes the evidence verbatim).

## Procedure — WebDriver Protocol ↔ MCP tool mappings

The seven `WebDriver` Protocol methods ↔ `mcp__playwright__browser_*` tool surface bindings the QA wrapper composes against at AC-iteration time:

| WebDriver method                            | MCP tool name                              |
|---------------------------------------------|--------------------------------------------|
| `navigate(url)`                             | `mcp__playwright__browser_navigate`        |
| `click(selector)`                           | `mcp__playwright__browser_click`           |
| `type_text(selector, text)`                 | `mcp__playwright__browser_type`            |
| `hover(selector)`                           | `mcp__playwright__browser_hover`           |
| `drag(source_selector, target_selector)`    | `mcp__playwright__browser_drag`            |
| `screenshot(name)`                          | `mcp__playwright__browser_take_screenshot` |
| `assert_dom_text(selector, expected)`       | `mcp__playwright__browser_snapshot` + textual comparison |
| `inspect_network()`                         | `mcp__playwright__browser_network_requests` |

The Python protocol method `type_text` corresponds to the verbatim epic AC vocabulary `type` (epics.md line 1904); the rename avoids shadowing Python's built-in `type` and is documented in the substrate library's docstring at `playwright_driver.py`. The textual-comparison step in `assert_dom_text` extracts the textual content of the element at `selector` from the snapshot output AND compares it (string equality) against `expected`; the comparison result is recorded in a `WebDriverAssertion(passed=..., observed=..., expected=...)` instance returned to the caller.

## Procedure — provisioner runtime bindings

The `PlaywrightAvailabilityProbe` and `DevServerRunner` Protocol runtime bindings the orchestrator skill composes at provision-time (BEFORE QA dispatch):

- **`PlaywrightAvailabilityProbe.is_available()`** — one MCP-tool ping. The orchestrator MUST perform a single trivial call to a no-side-effect Playwright tool (e.g., `mcp__playwright__browser_navigate("about:blank")` followed by `mcp__playwright__browser_close()` — choose a payload that produces zero observable side effects). On any tool-error, tool-absence, or timeout, return `False`. On clean tool-call return, return `True`.

- **`DevServerRunner.start(port)`** — `subprocess.Popen` of the dev-server command. The orchestrator MUST read the dev-server command from `_bmad/automation/qa-runbook.yaml`'s `dev_server_command` field (a single string command line — Story 7.5 will scaffold the stub; until then the practitioner maintains it manually) AND spawn it bound to `port` via `subprocess.Popen` with the canonical `start_new_session=True` posture (so the child becomes its own process group leader and SIGTERM during teardown reaches it cleanly). The runner returns the spawned process's PID. Any `subprocess.SubprocessError` propagates unchanged so Story 4.3's `provision_env` routes via the default `failure_step="dev-server-not-ready"`.

## Failure mode — playwright-mcp-unavailable mid-run

When any `mcp__playwright__browser_*` tool-call raises during AC verification (e.g., the MCP tool surface becomes unreachable mid-AC-iteration), the QA wrapper MUST follow the failure-mode protocol:

- **Catch the tool-call exception.** Wrap each `mcp__playwright__browser_*` invocation inside the AC-iteration loop in a try/except that catches the underlying tool-error.

- **Surface via the substrate library.** Call `surface_playwright_mcp_unavailable(story_id, registry, action_kind=<failed-action>, prior_evidence_refs=<already-captured>)` from `loud_fail_harness.playwright_driver`. The `<failed-action>` argument is the action name the wrapper was performing when the exception fired (one of `navigate | click | type_text | hover | drag | screenshot | assert_dom_text | inspect_network`). The `<already-captured>` argument is the tuple of repo-relative evidence_ref paths the `EvidenceCapturer` had already produced for the current AC BEFORE the unavailability fired — preserved per the verbatim epic AC at epics.md line 1912 ("evidence already captured is preserved").

- **Marker class.** The substrate's `surface_playwright_mcp_unavailable` validates the `PLAYWRIGHT_MCP_UNAVAILABLE_MARKER` (`"playwright-mcp-unavailable"` from `schemas/marker-taxonomy.yaml` line 226) against the registry FIRST (atomic-on-failure per Pattern 5; registry rejection raises `UnknownMarkerClass` BEFORE any partial state). On success, the function returns a `PlaywrightMcpUnavailableEmission` carrying the `MarkerEmissionRecord` + the `PlaywrightMcpUnavailableDiagnostic`.

- **Abort the current AC's verification.** Set the AC's `AcResult.status` to `"blocked"` AND populate the `evidence_refs` tuple with the `prior_evidence_refs` that were already captured. The `assertions` tuple records the diagnostic ("playwright-mcp-unavailable mid-run during action_kind=<X>"). The wrapper continues to the next AC (or aborts the iteration loop entirely per Story 4.6's plan-driven AC iteration policy, when that lands).

- **Forward the structured emission.** Surface the `PlaywrightMcpUnavailableEmission` via the existing terminal-stream + bundle-render paths so Story 4.10's escalation routing consumes it. The substrate library does NOT itself emit to the terminal; the QA wrapper or downstream Story 4.10 consumes the emission and routes through the verification-fail / env-setup-fail escalation contracts. THIS step's responsibility ends at producing the structured emission; Story 4.10 routes it.

## Failure mode — playwright-launch-failed at provisioning

When `PlaywrightProvisioner.provision` raises `PlaywrightLaunchFailed` AT init-time-of-provisioning (i.e., the `PlaywrightAvailabilityProbe.is_available()` returned `False` BEFORE the dev-server runner was invoked), the routing chain is:

- **`PlaywrightLaunchFailed.failure_step`.** The exception's `failure_step` attribute equals the literal string `"playwright-launch-failed"` byte-for-byte (mirroring `schemas/marker-taxonomy.yaml` line 111's `env-setup-failed.sub_classifications` enum member).

- **Story 4.3's `provision_env` catches it.** The wrapper at `loud_fail_harness.env_provisioning.provision_env` reads the `failure_step` attribute via `getattr(exc, "failure_step", "dev-server-not-ready")` and routes through `surface_env_setup_failure` with `sub_cause="playwright-launch-failed"` per Story 4.3's `EnvSetupFailureSubCause` enum at `env_provisioning.py` lines 287-291.

- **The orchestrator stays at `current_state="review"`.** Per Story 4.3's `steps/env-provisioning.md` § Failure mode — env-setup-fail (the verbatim epic AC at epics.md line 1881 — "the story does NOT enter the `qa` state — remains in `review`"); `commit_transition` is NEVER called on this branch. The QA wrapper is NEVER dispatched on this branch — the failure surfaces at the orchestrator side BEFORE QA receives the dispatch payload.

This routing chain is structurally distinct from the mid-run unavailability failure mode above: AT-INIT-time goes through `env-setup-failed` (Story 4.3's marker class); MID-RUN goes through `playwright-mcp-unavailable` (Story 4.4's marker class). The two are deliberately separate per the marker-taxonomy.yaml entries at lines 102 + 226 to reflect the differing remediation paths (init: dev-server / Playwright-MCP-installation issue; mid-run: transient connectivity loss).

## MaskedSelectorPolicy runtime application

Before persisting screenshots / DOM snapshots / network traces, the `EvidenceCapturer` MUST redact content matching any selector in the `MaskedSelectorPolicy` with `MASKED_REDACTION_SENTINEL` (`"[REDACTED]"`) per the verbatim epic AC at epics.md line 1917 ("evidence files respect masked-selector configuration if present in qa-runbook.yaml"). The runtime binding:

- **Read the policy at AC-iteration startup.** Read the `masked_selectors` array from `_bmad/automation/qa-runbook.yaml`; construct a `MaskedSelectorPolicy(masked_selectors=tuple(...))`. Empty array means "no redaction"; the substrate library's `_apply_masked_selector_policy` short-circuits and returns the payload unchanged.

- **Apply redaction BEFORE persisting.** The reference `NoOpEvidenceCapturer` shows the algorithm: for each selector, scan the textual rendering of the payload (decoded as UTF-8 with `errors="replace"` if bytes) for the selector's content (e.g., `input[type=password]` matches the value attribute substring typically rendered as `value="<secret>"` in DOM snapshots) AND replace matched substrings with `MASKED_REDACTION_SENTINEL`. Production `EvidenceCapturer` implementations bind the same algorithm BEFORE writing the redacted output to disk under `_bmad-output/qa-evidence/{story-id}/{run-id}/`.

- **The sentinel is `"[REDACTED]"`.** The dev's-call sentinel string is recorded in `docs/extension-audit.md` per the no-introductions principle. Story 4.12's evidence-persistence size budgets read the post-redaction output; the sentinel is short enough that redaction does not inflate evidence size meaningfully.

## Composed substrate primitives

- `loud_fail_harness.playwright_driver.PlaywrightProvisioner` (Story 4.4)
- `loud_fail_harness.playwright_driver.PlaywrightTeardown` (Story 4.4)
- `loud_fail_harness.playwright_driver.verify_ac` (Story 4.4)
- `loud_fail_harness.playwright_driver.surface_playwright_mcp_unavailable` (Story 4.4)
- `loud_fail_harness.playwright_driver.MaskedSelectorPolicy` (Story 4.4)
- `loud_fail_harness.playwright_driver.AcResult` + `WebDriverAssertion` + `NetworkRequest` (Story 4.4)
- `loud_fail_harness.playwright_driver.PLAYWRIGHT_MCP_UNAVAILABLE_MARKER` + `MASKED_REDACTION_SENTINEL` (Story 4.4)
- `loud_fail_harness.env_provisioning.provision_env` (Story 4.3) — composed by the orchestrator skill at provision-time WITH a `PlaywrightProvisioner` instance from THIS module.
- `loud_fail_harness.env_provisioning.teardown_env` (Story 4.3) — composed by the orchestrator skill at teardown-time WITH a `PlaywrightTeardown` instance from THIS module.
- `loud_fail_harness.env_provisioning.surface_env_setup_failure` (Story 4.3) — receives the `PlaywrightLaunchFailed` exception via `provision_env`'s catch path on the AT-INIT-time failure.
- `loud_fail_harness.specialist_dispatch.MarkerClassRegistry` + `validate_marker_emission` (Story 2.6) — composed by `surface_playwright_mcp_unavailable` for atomic-on-failure registry validation.
- `loud_fail_harness.qa_behavioral_plan.QABehavioralPlanEntry` (Story 4.1) — consumed by `verify_ac` as the per-AC plan entry carrying `assertion_shape` + `expected_evidence_tier`.

The library reads ONLY the AC + plan-entry from its `verify_ac` arguments + `qa-runbook.yaml`'s `dev_server_command` / `masked_selectors` fields (consumed AT THIS step's runtime binding, NOT by the substrate library) + the running web product. Driver code does NOT read TEA test files, dev tests, review findings, or commit diffs (FR16 invariant; structurally encoded by the substrate library's argument lists).

The driver substrate references ONLY `loud_fail_harness.specialist_dispatch` + `loud_fail_harness.env_provisioning` + `loud_fail_harness.qa_behavioral_plan` + Pydantic v2 + Python stdlib. NO references to Dev or Review-BMAD specialist code (FR62 pluggability invariant).

## Forward consumers

- **Story 4.6 — plan-driven AC iteration framework** consumes `verify_ac` at iteration time across the full `QABehavioralPlan.entries` tuple (the smoke-first ordering routes AC-1 through AC-N through the per-AC primitive THIS story ships).
- **Story 4.7 — AC-assertion-evidence triple structural enforcement** lifts the schema-level invariant; THIS story produces `AcResult` records that conform to the existing `$defs/ac_result` shape byte-for-byte.
- **Story 4.8 — three-tier evidence hierarchy** thickens the `expected_evidence_tier` semantics; THIS story emits Tier-1 mechanical evidence only (Tier-2 outcome and Tier-3 semantic are downstream).
- **Story 4.9 — three exploratory heuristics (empty / error / auth)** thickens the per-AC verification with the `verification_mode` field; THIS story's `verify_ac` produces the mechanical baseline.
- **Story 4.10 — env-setup-fail / verification-fail escalation routing** consumes the `PlaywrightMcpUnavailableEmission` (mid-run path) AND the `EnvSetupFailureEmission` carrying `sub_cause="playwright-launch-failed"` (init-time path) and routes both through the verification-fail / env-setup-fail escalation-class contracts.
- **Story 4.11 — plan-persistence-compromise PR-bundle visibility** renders the structured emissions in the PR bundle; THIS story produces the data, that story renders it.
- **Story 4.12 — evidence-persistence size budgets + truncation markers** reads the `EvidenceCapturer`'s on-disk output to enforce truncation; THIS story's `EvidenceCapturer` Protocol surface is the binding point.
- **Story 4.13 — QA wrapper completion** thickens `agents/qa.md` to compose THIS step file's protocol at AC-iteration time for `web` project types, replacing Story 2.10's "use Playwright MCP per FR17" stub line at `agents/qa.md` line 30 with the full procedural composition.
