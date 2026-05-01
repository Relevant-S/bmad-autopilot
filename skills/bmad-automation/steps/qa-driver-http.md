# Step: QA driver — HTTP (Story 4.5 — api project type, FR17)

## Purpose

Encode the LLM-runtime protocol for invoking the substrate's `ApiDriver` Protocol against Python's stdlib `http.client` at AC-iteration time for `api` project types per FR17 (`_bmad-output/planning-artifacts/prd.md` line 831 — "QA drives the running product independently — via Playwright MCP for web project types, via HTTP for API project types"). The Python substrate at `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/http_driver.py` is pure and the substrate library IS allowed to invoke stdlib HTTP; the step file remains the canonical binding contract for the QA wrapper's prompt-execution context per ADR-004's substrate-vs-LLM-runtime split applied to driver dispatch policy. This prose IS the binding contract that names how to compose the substrate `ApiDriver` Protocol's four primitives (plus `inspect_network_trace`) against Python stdlib AT runtime + the provisioner runtime bindings + the failure-mode procedures.

This sub-step file is composed BY the QA wrapper (Story 4.13 forthcoming wrapper thickening) AT AC-iteration time AFTER the orchestrator's env-provisioning seam (`steps/env-provisioning.md`) has produced the `provisioned_env` carrier with `env_kind="api"`. It is the binding point Stories 4.6 (plan-driven AC iteration) / 4.10 (escalation routing) / 4.12 (evidence persistence) compose against at runtime. The QA wrapper at `agents/qa.md` is NOT modified by this story — Story 4.13 owns wrapper thickening; the seam contract is preserved structurally by THIS step's placement at the wrapper-side AC-iteration point.

## Pre-condition

The orchestrator's env-provisioning seam (Story 4.3's `steps/env-provisioning.md`) has produced the `provisioned_env` carrier with `env_kind="api"` AND the QA dispatch payload has been delivered to the QA wrapper. Before invoking THIS step's procedure, the QA wrapper MUST have:

- A loaded `MarkerClassRegistry` carrying the `env-setup-failed` marker class (from `loud_fail_harness.specialist_dispatch.load_marker_class_registry`) — re-used AS-IS for the mid-run "API broken" path; no new marker class is introduced by this story.
- The dispatched `provisioned_env` from the dispatch payload's `provisioned_env` carrier (Story 4.3's seam contract).
- The story's `ac_list` from the dispatch payload (FR16 — the single QA-side input channel).
- The parsed `QABehavioralPlan` from the story doc's `## QA Behavioral Plan` section (Story 4.1's `persist_or_reuse_plan` output; consumed verbatim).
- The `qa-runbook.yaml` stub at `_bmad/automation/qa-runbook.yaml` (Story 7.5 will scaffold; until then the practitioner maintains it manually). The wrapper reads the `api_server_command` field at provision-time (consumed by the `ApiServerRunner` runtime binding below) and the `masked_selectors` field at AC-iteration time (consumed by the `MaskedSelectorPolicy` runtime binding below).
- A constructed `EvidenceCapturer` rooted at `_bmad-output/qa-evidence/{story-id}/{run-id}/` per FR49 (Story 4.12 owns the evidence-persistence size budgets; THIS step writes the evidence verbatim).

## Procedure — ApiDriver Protocol ↔ stdlib mappings

The four `ApiDriver` Protocol primitives (plus `inspect_network_trace`) ↔ Python-stdlib `http.client` surface bindings the QA wrapper composes against at AC-iteration time:

| ApiDriver method                            | stdlib binding                                                         |
|---------------------------------------------|------------------------------------------------------------------------|
| `request(method, url, *, headers, body, timeout)` | `http.client.HTTPConnection.request` + `getresponse` + `response.read` |
| `assert_status(response, expected)`         | in-Python comparison against `HttpResponse.status`                     |
| `assert_body(response, expected)`           | in-Python equality / substring / structural-Mapping match against `HttpResponse.body` |
| `assert_header(response, name, expected)`   | in-Python case-insensitive lookup against `HttpResponse.headers`        |
| `inspect_network_trace()`                   | reads the per-driver-instance trace buffer the `request` method appends to |

The body-matching algorithm in `assert_body`: if `expected` is a `str`, dispatch to equality first AND substring-containment fallback when full equality fails; if `expected` is a `Mapping`, parse `response.body` as JSON via `json.loads` AND check that every `(key, value)` pair in `expected` is present in the parsed body (structural subset match). Numeric / null / nested-object JSON values follow the same subset semantics. Production `request` impls MUST raise `loud_fail_harness.http_driver.ApiServiceBroken` on `ConnectionRefusedError` / `socket.timeout` / 5xx-unrelated-to-AC-content conditions; tests' `NoOpApiDriver` accepts a configured exception via the `action_exception` constructor argument.

## Procedure — provisioner runtime bindings

The `ApiAvailabilityProbe` and `ApiServerRunner` Protocol runtime bindings the orchestrator skill composes at provision-time (BEFORE QA dispatch):

- **`ApiAvailabilityProbe.is_available()`** — one stdlib HTTP GET against `http://localhost:{port}/` with a 2-second timeout. Choose a payload that produces zero observable side effects (a bare `GET /` is the canonical choice; if the application's root path has side effects, the practitioner overrides via the runbook stub — Story 7.5 scaffolds). On `ConnectionRefusedError`, `socket.timeout`, `http.client.HTTPException`, or any other non-HTTP-response condition, return `False`. On clean tool-call return (any 1xx / 2xx / 3xx / 4xx response counts as "the API is up"), return `True`.

- **`ApiServerRunner.start(port)`** — `subprocess.Popen` of the api-server command. The orchestrator MUST read the api-server command from `_bmad/automation/qa-runbook.yaml`'s `api_server_command` field (a single string command line — Story 7.5 will scaffold the stub; until then the practitioner maintains it manually) AND spawn it bound to `port` via `subprocess.Popen` with the canonical `start_new_session=True` posture (so the child becomes its own process group leader and SIGTERM during teardown reaches it cleanly — the cross-driver convention Story 4.4 codified). The runner returns the spawned process's PID. Any `subprocess.SubprocessError` propagates unchanged so Story 4.3's `provision_env` routes via the default `failure_step="dev-server-not-ready"`.

The provisioner ordering is `runner.start(port)` BEFORE `availability_probe.is_available()` per `HttpProvisioner.provision`'s AC-2 contract: the API server itself must be up before the smoke probe can succeed. On probe-false, the provisioner performs a best-effort `os.kill(pid, signal.SIGTERM)` cleanup of the orphan PID (swallowing `ProcessLookupError` / `PermissionError`) BEFORE raising `ApiServerNotReady`. This ordering asymmetry vs Story 4.4's `PlaywrightProvisioner` (which probes BEFORE running) is recorded in the substrate library's docstring + `docs/extension-audit.md`.

## Failure mode — API broken mid-run

When any `ApiDriver.request` call raises `ApiServiceBroken` during AC verification (the production impl raises this on `ConnectionRefusedError` / `socket.timeout` / 5xx-unrelated-to-AC-content from the underlying stdlib `http.client.HTTPConnection.request`), the QA wrapper MUST follow the failure-mode protocol:

- **Catch the exception.** Wrap `verify_ac(...)` in a `try / except ApiServiceBroken as exc` clause inside the AC-iteration loop. The substrate's `verify_ac` re-raises `ApiServiceBroken` UNCHANGED — does NOT swallow, does NOT construct an `AcResult`. The wrapper-side handler is the routing site.

- **Surface via the substrate library — AS-IS reuse.** Call `loud_fail_harness.env_provisioning.surface_env_setup_failure(story_id, registry, project_type="api", failure_step=exc.failure_step, failure_diagnostic=exc.failure_diagnostic, qa_runbook_pointer="_bmad/automation/qa-runbook.yaml")` AS-IS reusing Story 4.3's existing helper. THIS story does NOT introduce a new emission helper because the marker class re-used is the existing `env-setup-failed` from Story 1.4 / Story 4.3, NOT a new class. The asymmetry vs Story 4.4 — which DID introduce `surface_playwright_mcp_unavailable` because its mid-run path needed a structurally distinct `playwright-mcp-unavailable` marker class (the remediation differs: "transient MCP-tool-surface connectivity loss" vs "API server not responding") — is recorded in the substrate library's docstring + `docs/extension-audit.md`.

- **Marker class.** The substrate's `surface_env_setup_failure` validates the `env-setup-failed` marker class against the registry FIRST (atomic-on-failure per Pattern 5; registry rejection raises `UnknownMarkerClass` BEFORE any partial state). On success, the function returns an `EnvSetupFailureEmission` carrying a `MarkerEmissionRecord` with `marker_class="env-setup-failed"` AND `sub_cause="dev-server-not-ready"` AND the diagnostic-projected `context`.

- **Abort the current AC's verification.** Set the AC's `AcResult.status` to `"blocked"` AND populate the `evidence_refs` tuple with prior captures (request/response trace records the `EvidenceCapturer` had already produced for the current AC BEFORE the unavailability fired). The `assertions` tuple records the diagnostic ("api service broken: <exc.failure_diagnostic>"). The wrapper continues to the next AC (or aborts the iteration loop entirely per Story 4.6's plan-driven AC iteration policy, when that lands).

- **Forward the structured emission.** Surface the `EnvSetupFailureEmission` via the existing terminal-stream + bundle-render paths so Story 4.10's escalation routing consumes it. The substrate library does NOT itself emit to the terminal; the QA wrapper or downstream Story 4.10 consumes the emission and routes through the verification-fail / env-setup-fail escalation contracts. THIS step's responsibility ends at producing the structured emission via the AS-IS `surface_env_setup_failure` reuse; Story 4.10 routes it.

## Failure mode — dev-server-not-ready at provisioning

When `HttpProvisioner.provision` raises `ApiServerNotReady` AT init-time-of-provisioning (i.e., the `ApiAvailabilityProbe.is_available()` returned `False` AFTER the `ApiServerRunner.start(port)` call but BEFORE the smoke probe could reach the service), the routing chain is:

- **`ApiServerNotReady.failure_step`.** The exception's `failure_step` attribute equals the literal string `"dev-server-not-ready"` byte-for-byte (mirroring `schemas/marker-taxonomy.yaml` line 112's `env-setup-failed.sub_classifications` enum member).

- **Story 4.3's `provision_env` catches it.** The wrapper at `loud_fail_harness.env_provisioning.provision_env` reads the `failure_step` attribute via `getattr(exc, "failure_step", "dev-server-not-ready")` and routes through `surface_env_setup_failure` with `sub_cause="dev-server-not-ready"` per Story 4.3's `EnvSetupFailureSubCause` enum at `env_provisioning.py` lines 287-291.

- **The orchestrator stays at `current_state="review"`.** Per Story 4.3's `steps/env-provisioning.md` § Failure mode — env-setup-fail (the verbatim epic AC at epics.md line 1881 — "the story does NOT enter the `qa` state — remains in `review`"); `commit_transition` is NEVER called on this branch. The QA wrapper is NEVER dispatched on this branch — the failure surfaces at the orchestrator side BEFORE QA receives the dispatch payload.

- **Best-effort orphan PID cleanup.** Per `HttpProvisioner.provision`'s AC-2 contract, the provisioner calls `os.kill(pid, signal.SIGTERM)` (swallowing `ProcessLookupError` / `PermissionError`) on the spawned PID BEFORE raising the exception so the orphan-process surface does not accumulate.

This routing chain is structurally distinct from the mid-run service-broken failure mode above only at the wrapper-side trigger surface — both end up routing through `surface_env_setup_failure` with the same `sub_cause="dev-server-not-ready"`. The shared sub_cause is intentional per the remediation-shape principle in `docs/extension-audit.md` § Marker class boundaries: both AT-INIT and MID-RUN paths share the same remediation surface ("the underlying server process is not responding"). Adding a distinct `api-service-unreachable` marker class would violate the remediation-shape principle by emission-point-shaping the taxonomy rather than remediation-shaping it.

## Failure mode — AC verification-fail

When an `ApiDriver` assertion method (`assert_status` / `assert_body` / `assert_header`) returns an `ApiAssertion` with `passed=False`, the routing surface is structurally distinct from the API-broken paths above:

- **`AcResult.status="fail"`.** The substrate's `verify_ac` constructs an `AcResult` with `status="fail"` carrying the failed `ApiAssertion`'s human-readable rendering (`f"{kind}: observed={observed!r} expected={expected!r} passed={passed}"`) in the `assertions` tuple AND the captured request/response trace in the `evidence_refs` tuple. NO marker emission — the wrapper-side `status: fail` envelope is the verification-fail signal Story 4.10 routes per FR24a.

- **FR24a verification-fail vs FR24b env-setup-fail distinction.** The two escalation classes are structurally separate per the verbatim epic AC at epics.md lines 1945-1948 ("the driver distinguishes 'API broken' (env-setup-fail per Story 4.10) from 'AC unverified' (verification-fail per Story 4.10) ... the diagnostic surfaces the distinction clearly (separate code paths, separate envelopes)"). The wrapper-side rendering for the verification-fail envelope produces a `findings` entry with `bucket=decision_needed` + `severity=HIGH` carrying the failed-assertion detail; Story 4.10 routes the bucket. THIS story does NOT itself construct the finding — Story 4.13 owns the wrapper-side finding construction; THIS story's deliverable is the `AcResult.status="fail"` shape that Story 4.13 builds upon.

## MaskedSelectorPolicy runtime application

Before persisting request/response trace excerpts, the `EvidenceCapturer` MUST redact content matching any selector in the `MaskedSelectorPolicy` with `MASKED_REDACTION_SENTINEL` (`"[REDACTED]"`) per the verbatim epic AC at epics.md line 1942 ("request/response traces (with optional sensitive-field masking per Story 4.12's `masked_selectors`) are persisted"). The api-side runtime binding extends Story 4.4's CSS-selector matching with HTTP header / query-string / JSON-body matching:

- **Read the policy at AC-iteration startup.** Read the `masked_selectors` array from `_bmad/automation/qa-runbook.yaml`; construct a `MaskedSelectorPolicy(masked_selectors=tuple(...))`. Empty array means "no redaction"; the substrate's `_apply_api_masked_selector_policy` short-circuits and returns the payload unchanged.

- **Apply redaction BEFORE persisting.** The substrate's `_apply_api_masked_selector_policy` algorithm:
  1. First, delegate to Story 4.4's `_apply_masked_selector_policy` for the CSS-selector branches (`input[type=password]` etc.).
  2. Then, for each non-CSS plain-text selector, apply api-specific redaction:
     - **HTTP header pattern** — `<selector>: <value>` (case-insensitive on the selector-name match): redact `<value>` (rest of line until newline or end-of-string) with `MASKED_REDACTION_SENTINEL`. Example: selector `Authorization` redacts the `Bearer eyJh...` token in `Authorization: Bearer eyJh...`.
     - **JSON body pattern** — `"<selector>": "<value>"`: redact the quoted `<value>` with `MASKED_REDACTION_SENTINEL`. Example: selector `password` redacts `"hunter2"` in `"password": "hunter2"`.
     - **Query-string pattern** — `<selector>=<value>` (where `<value>` is bounded by `&`, whitespace, or end-of-string): redact `<value>`. Example: selector `api_key` redacts the secret in `?api_key=abc123`.

- **The sentinel is `"[REDACTED]"`.** The dev's-call sentinel string is consumed AS-IS from Story 4.4's `MASKED_REDACTION_SENTINEL` constant; recorded in `docs/extension-audit.md` per the no-introductions principle. Story 4.12's evidence-persistence size budgets read the post-redaction output.

The substrate library at THIS story does NOT modify Story 4.4's algorithm; instead it builds an api-side wrapper that delegates to Story 4.4's helpers for the CSS-selector branch AND adds plain-text-selector matching for the api-specific surfaces.

## Composed substrate primitives

- `loud_fail_harness.http_driver.HttpProvisioner` (Story 4.5)
- `loud_fail_harness.http_driver.HttpTeardown` (Story 4.5)
- `loud_fail_harness.http_driver.verify_ac` (Story 4.5)
- `loud_fail_harness.http_driver.ApiServerNotReady` + `ApiServiceBroken` (Story 4.5)
- `loud_fail_harness.http_driver.ApiDriver` Protocol + `HttpResponse` + `ApiAssertion` + `NetworkTraceRecord` (Story 4.5)
- `loud_fail_harness.http_driver.API_SERVER_NOT_READY_STEP` (Story 4.5)
- `loud_fail_harness.playwright_driver.AcResult` + `MaskedSelectorPolicy` + `MASKED_REDACTION_SENTINEL` + `EvidenceCapturer` + `NoOpEvidenceCapturer` — AS-IS reuse from Story 4.4 (project-type-agnostic primitives whose canonical declaration site is `playwright_driver.py` because Story 4.4 landed first in build order; re-exported via direct import from `http_driver.py`).
- `loud_fail_harness.env_provisioning.provision_env` (Story 4.3) — composed by the orchestrator skill at provision-time WITH an `HttpProvisioner` instance from THIS module.
- `loud_fail_harness.env_provisioning.teardown_env` (Story 4.3) — composed by the orchestrator skill at teardown-time WITH an `HttpTeardown` instance from THIS module.
- `loud_fail_harness.env_provisioning.surface_env_setup_failure` (Story 4.3) — receives the `ApiServerNotReady` exception via `provision_env`'s catch path on the AT-INIT-time failure AND the `ApiServiceBroken` exception via the wrapper's mid-run catch site AS-IS (no new emission helper).
- `loud_fail_harness.specialist_dispatch.MarkerClassRegistry` + `validate_marker_emission` (Story 2.6) — composed by `surface_env_setup_failure` for atomic-on-failure registry validation.
- `loud_fail_harness.qa_behavioral_plan.QABehavioralPlanEntry` (Story 4.1) — consumed by `verify_ac` as the per-AC plan entry carrying `assertion_shape` + `expected_evidence_tier`.

The library reads ONLY the AC + plan-entry from its `verify_ac` arguments + `qa-runbook.yaml`'s `api_server_command` / `masked_selectors` fields (consumed AT THIS step's runtime binding, NOT by the substrate library directly) + the running API product. Driver code does NOT read TEA test files, dev tests, review findings, or commit diffs (FR16 invariant; structurally encoded by the substrate library's argument lists).

The driver substrate references ONLY `loud_fail_harness.specialist_dispatch` + `loud_fail_harness.env_provisioning` + `loud_fail_harness.playwright_driver` (for AS-IS reuse of project-type-agnostic primitives) + `loud_fail_harness.qa_behavioral_plan` + Pydantic v2 + Python stdlib (`http.client`, `subprocess`, `os`, `signal`, `time`, `datetime`). NO references to Dev or Review-BMAD specialist code (FR62 pluggability invariant).

## Forward consumers

- **Story 4.6 — plan-driven AC iteration framework** consumes `verify_ac` at iteration time across the full `QABehavioralPlan.entries` tuple for `api` project types (the smoke-first ordering routes AC-1 through AC-N through the per-AC primitive THIS story ships).
- **Story 4.7 — AC-assertion-evidence triple structural enforcement** lifts the schema-level invariant; THIS story produces `AcResult` records that conform to the existing `$defs/ac_result` shape byte-for-byte.
- **Story 4.8 — three-tier evidence hierarchy** thickens the `expected_evidence_tier` semantics; THIS story emits Tier-1 mechanical evidence only (Tier-2 outcome and Tier-3 semantic are downstream).
- **Story 4.9 — three exploratory heuristics (empty / error / auth)** thickens the per-AC verification with the `verification_mode` field; THIS story's `verify_ac` produces the mechanical baseline.
- **Story 4.10 — env-setup-fail / verification-fail escalation routing** consumes the `EnvSetupFailureEmission` (mid-run service-broken path AS-IS via `surface_env_setup_failure`) AND the wrapper-side `status: fail` envelope (verification-fail path) and routes both through the verification-fail / env-setup-fail escalation-class contracts.
- **Story 4.11 — plan-persistence-compromise PR-bundle visibility** renders the structured emissions in the PR bundle; THIS story produces the data, that story renders it.
- **Story 4.12 — evidence-persistence size budgets + truncation markers** reads the `EvidenceCapturer`'s on-disk output to enforce truncation; THIS story's `EvidenceCapturer` Protocol surface is the binding point AND the per-trace-record `_TRACE_BODY_EXCERPT_MAX_CHARS` constant is the per-record body excerpt bound (distinct from the file-level size budget Story 4.12 owns).
- **Story 4.13 — QA wrapper completion** thickens `agents/qa.md` to compose THIS step file's protocol at AC-iteration time for `api` project types, replacing Story 2.10's "drive the HTTP surface per FR17" stub line at `agents/qa.md` line 31 with the full procedural composition.
