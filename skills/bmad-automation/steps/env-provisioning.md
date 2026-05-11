# Step: Env provisioning (Story 4.3 — orchestrator-owned env lifecycle, FR7 + NFR-S6)

## Purpose

Encode the LLM-runtime protocol for the orchestrator-owned env-provisioning seam at the `review → qa` BMAD-lifecycle transition. The Python substrate at `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/env_provisioning.py` provides the structural primitives (ephemeral port allocation, atomic provisioning, teardown, orphan cleanup, env-setup-failure emission). This prose IS the LLM-runtime contract that names how to compose those primitives at the seam — three concerns the substrate Python cannot natively express because env-provisioning is bound to the orchestrator skill's BMAD-lifecycle position (NOT a Python API; FR7 explicitly places env-lifecycle ownership at the orchestrator's `review → qa` boundary).

This sub-step file is invoked by `steps/run.md`'s seam-loop BEFORE the QA dispatch path; it is the binding point Stories 4.4 / 4.5 (project-type-specific provisioners) and Story 4.10 (escalation routing) compose against at runtime. The QA wrapper at `agents/qa.md` is NOT modified by this story — its `status: blocked` declaration on env-setup precondition violations stays at the Story 2.10 surface; FR7's invariant that env lifecycle is orchestrator-owned (NOT QA-owned) is preserved structurally by this protocol's placement at the orchestrator-side seam.

## Pre-condition

The orchestrator has reached `current_state="review"` AND the latest specialist envelope's `status="pass"` — the BMAD-lifecycle precondition for `review → qa` that Story 2.4's `evaluate_envelope` returns as the `advance` decision. Before invoking THIS step's procedure, the orchestrator MUST have:

- A loaded `MarkerClassRegistry` carrying both `env-setup-failed` and `orphan-process-cleanup` marker classes (from `loud_fail_harness.specialist_dispatch.load_marker_class_registry`).
- A constructed `EventLogAppender` callable for the current run (from `loud_fail_harness.event_streaming.make_event_log_appender`).
- A resolved `run_state_path` pointing at the in-flight run-state YAML.
- The story's `project_type` value read from `_bmad/automation/config.yaml` (the `project_type: web | api | mobile` field; Story 9.2 wires Story 7.5's init-time detection that writes this field to config.yaml per FR-P1.5-2 — `mobile` was added in Phase 1.5 per ADR-007).
- A constructed `evidence_root` path at `_bmad-output/qa-evidence/{story-id}/{run-id}/` per FR49 (Story 4.12 owns the evidence-root persistence; THIS step asserts non-touching only).

## Procedure

The seven-step composition the orchestrator follows BEFORE invoking the QA dispatch callback:

(i) **Read project_type from the project config.** Read `_bmad/automation/config.yaml`'s `project_type` field as a string in `{"web", "api", "mobile"}` (the `mobile` member was added in Phase 1.5 per ADR-007). Story 9.2 wires the init-time detection that writes this field; the substrate library does NOT read the config (FR16 invariant — env provisioning reads ONLY the project type from the config + the run-state's `story_id`; it does NOT read TEA test files, dev tests, review findings, or commit diffs). The LLM-runtime protocol owns this read so the substrate stays pure.

(ii) **Sweep stale orphans BEFORE fresh provisioning.** Call `cleanup_orphan_processes(run_state_path, orphan_probe, orphan_terminator, registry, event_appender, story_id=..., env_kind=project_type)`. This composes Story 4.3's project-type-agnostic orphan-detection seam — `orphan_probe.probe()` returns the list of `(port, pid)` pairs from prior crashed runs; `orphan_terminator.terminate(port, pid)` is invoked per pair; one `MarkerEmissionRecord` per orphan is constructed with `marker_class="orphan-process-cleanup"` + `context={"port": port, "pid": pid}` per the verbatim epic AC at epics.md line 1878; one `env-torn-down` summary event is emitted with `outcome="orphan-process-cleanup"`. On `UnknownMarkerClass` (registry-rejection), the function is atomic-on-failure — no terminator calls happen, no markers are constructed, no events are emitted; the rejection propagates to the orchestrator skill prompt.

(iii) **Allocate a fresh ephemeral port.** Call `allocate_ephemeral_port()`. The function performs a single `socket.bind(("127.0.0.1", 0))` + `getsockname` + `close` sequence; it returns an integer in `[1, 65535]` from the OS's ephemeral range. The race-condition window between port-release and provisioner-bind is inherent to ephemeral allocation; the provisioner is expected to handle "port suddenly bound" by raising an exception that flows through `surface_env_setup_failure` with `sub_cause="port-bind-failed"` (handled by step (v) below).

(iv) **Provision the env.** Call `provision_env(story_id, project_type, provisioner, port, run_state_path, registry, event_appender)`. The `provisioner` argument is a `Provisioner` Protocol implementation dispatched per `project_type`: Story 4.4 ships the web `PlaywrightProvisioner`; Story 4.5 ships the API `HttpProvisioner`; **when `project_type == "mobile"`, dispatch `MobileMcpProvisioner` from `loud_fail_harness.mobile_driver` per Story 9.3 / ADR-007** — the mobile provisioner is npx-stdio-aware (no dev-server subprocess) and returns `ProvisionedEnv(env_kind="mobile", port=0, pid=0, ...)` per Story 9.3 AC-7; tests use `NoOpProvisioner`. On success the run-state's `provisioned_env` field is populated atomically (via the tempfile + `os.replace` discipline mirroring Story 2.2's `advance_run_state` pattern byte-for-byte) AND an `env-provisioned` event is appended to the events log. The function is atomic-on-failure — see step (v).

(v) **On `EnvProvisioningFailed`, halt at `review`.** When the provisioner raises any exception, `provision_env` catches it, derives the `failure_step` from a `failure_step` attribute on the exception (or defaults to `"dev-server-not-ready"`), calls `surface_env_setup_failure` to construct the structured `EnvSetupFailureEmission`, and re-raises as `EnvProvisioningFailed(emission)`. The orchestrator MUST catch this exception and:

  - Leave `current_state` at `"review"` per the verbatim epic AC at epics.md line 1881 ("the story does NOT enter the `qa` state — remains in `review`"); `commit_transition` is NEVER called.
  - Surface the `env-setup-failed` marker via the existing terminal-stream + bundle-render paths (the substrate library does NOT emit to the terminal; the orchestrator skill or downstream Story 4.10 consumes the `EnvSetupFailureEmission`).
  - Forward the structured `EnvSetupFailureEmission` (carrying `marker_record` + `diagnostic`) to Story 4.10's escalation contract — Story 4.10 owns the routing of `verification-fail` and `env-setup-fail` escalation classes; THIS story produces the structured emission, that story routes it.

  The orchestrator does NOT proceed to step (vi) on this branch; flow control returns to the practitioner via NFR-O1's terminal stream + the next-action diagnostic.

(vi) **On success, surface `provisioned_env` into the QA dispatch payload.** Read the freshly-persisted `provisioned_env` field from `run-state.yaml` and inject it into the QA dispatch payload (the existing Story 2.6 `make_task_tool_dispatch_callback` path consumes the dispatch payload). QA observes the env it has been handed via the dispatch payload's `provisioned_env` carrier; QA NEVER provisions the env itself — preserving FR7's invariant that env lifecycle is orchestrator-owned, NOT QA-owned. Then dispatch QA via the existing Story 2.6 path.

(vii) **After QA return, tear down unconditionally.** When the QA Task-tool invocation returns (regardless of envelope `status` ∈ `{pass, fail, decision-needed, blocked}`), the orchestrator MUST call `teardown_env(provisioned_env, teardown_fn, run_state_path, evidence_root, registry, event_appender, story_id=...)` BEFORE making the next BMAD-lifecycle decision. Teardown is unconditional after QA completion per epics.md line 1869 — even on QA `fail` / `blocked` paths, the env is torn down BEFORE the orchestrator routes to retry / escalation. The teardown invariant: `teardown_fn.teardown(provisioned_env)` is invoked once; the run-state's `provisioned_env` field is cleared (the dev's-call YAML idiom is REMOVAL of the key per the extension-audit.md row); the `env-torn-down` event is emitted with `outcome="clean"`; the `evidence_root` directory and its contents are NEVER opened, listed, mutated, or referenced (Story 4.12 owns evidence persistence).

## Failure mode — env-setup-fail

When `provision_env` raises `EnvProvisioningFailed`, the orchestrator MUST follow the failure-mode protocol:

- **Pre-call registry guard.** If the registry does not contain `"env-setup-failed"`, `provision_env` raises `UnknownMarkerClass` BEFORE any provisioner call or state change. The orchestrator treats this as a configuration error; `current_state` remains at `"review"` for the same reason as the env-setup-fail path below.

- **Run-state preservation invariant.** Leave `current_state` at `"review"`; `loud_fail_harness.lifecycle_state_machine.commit_transition` is NEVER called on this branch. The verbatim epic AC at epics.md line 1881 is the load-bearing commitment ("the story does NOT enter the `qa` state — remains in `review`"); the substrate library structurally enforces this invariant by raising the exception BEFORE any state advance.

- **Marker class.** The `env-setup-failed` marker class (from `schemas/marker-taxonomy.yaml` line 102) is the canonical surface; the marker's `sub_cause` is one of the values from `schemas/marker-taxonomy.yaml`'s `env-setup-failed.sub_classifications` list (`port-bind-failed`, `playwright-launch-failed`, `dev-server-not-ready`, Story 7.3's four init-phase sub-causes, and — per Story 9.3 / ADR-007 — `mobile-mcp-init-unreachable` for the AT-INIT-time mobile MCP probe-False path; the latter routes through `MobileMcpLaunchFailed.failure_step` consumed by `provision_env`'s existing `getattr(exc, "failure_step", ...)` pattern AS-IS).

- **Story 4.10 forward-pointer — escalation routing.** The `EnvSetupFailureEmission` carries the `MarkerEmissionRecord` + the five-field `EnvSetupFailureDiagnostic` (story_id, project_type, failure_step, failure_diagnostic, qa_runbook_pointer); Story 4.10 consumes this structure and routes it through the verification-fail / env-setup-fail escalation-class contracts. THIS step's responsibility ends at producing the structured emission; the routing is Story 4.10's surface.

- **Wrapper-side surface preserved.** The QA wrapper's `status: blocked` declaration on env-setup precondition violations stays at Story 2.10's existing surface (`agents/qa.md`); the wrapper-side env-receives-from-orchestrator boundary is preserved. The orchestrator-side escalation routing in Story 4.10 thickens visibility further without modifying the wrapper.

## Composed substrate primitives

- `loud_fail_harness.env_provisioning.allocate_ephemeral_port` (Story 4.3)
- `loud_fail_harness.env_provisioning.provision_env` (Story 4.3)
- `loud_fail_harness.env_provisioning.teardown_env` (Story 4.3)
- `loud_fail_harness.env_provisioning.cleanup_orphan_processes` (Story 4.3)
- `loud_fail_harness.env_provisioning.surface_env_setup_failure` (Story 4.3)
- `loud_fail_harness.env_provisioning.NoOpProvisioner` (Story 4.3 — test-only reference impl)
- `loud_fail_harness.specialist_dispatch.MarkerClassRegistry` + `validate_marker_emission` (Story 2.6) — composed by `surface_env_setup_failure` and `cleanup_orphan_processes` for atomic-on-failure registry validation.
- `loud_fail_harness.run_state.advance_run_state` (Story 2.2) — pattern (NOT direct call) the substrate library's `_set_provisioned_env` / `_clear_provisioned_env` mirrors byte-for-byte.
- `loud_fail_harness.event_validator.validate_event` (Story 1.3) — composed by the `make_env_provisioned_event` and `make_env_torn_down_event` helpers for defensive event-validation.
- `loud_fail_harness.event_streaming.make_event_log_appender` (Story 2.12) — caller-injected appender consumed by every event-emission seam.

## Forward consumers

- **Story 4.4 — web Playwright provisioner** implements the `Provisioner` Protocol against the actual `subprocess.Popen`-of-dev-server + Playwright-MCP-availability-check path; sibling pure-library module under `loud_fail_harness/`.
- **Story 4.5 — API HTTP provisioner** implements the `Provisioner` Protocol against the actual `subprocess.Popen`-of-API-server + HTTP-availability-check path; sibling pure-library module.
- **Story 9.3 — mobile MCP provisioner** implements the `Provisioner` Protocol against the mobile-mcp npx-stdio probe (NO dev-server subprocess); the `MobileMcpProvisioner` returns a `ProvisionedEnv(env_kind="mobile", port=0, pid=0, health_url=None)` shape; sibling pure-library module at `loud_fail_harness.mobile_driver`. The LLM-runtime binding contract is `skills/bmad-automation/steps/qa-driver-mobile.md`.
- **Story 4.10 — env-setup-fail escalation routing** consumes the `EnvSetupFailureEmission` and routes through the verification-fail / env-setup-fail escalation-class contracts.
- **Story 4.12 — evidence-persistence size budgets** reads the `evidence_root` directory after QA return to enforce truncation and persistence; the `teardown_env`-NEVER-touches-evidence invariant from Story 4.3 is what makes Story 4.12's composition possible without ordering risk.
