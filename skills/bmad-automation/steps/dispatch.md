# /bmad-automation specialist dispatch — LLM-runtime protocol

## Goal

Encode the LLM-runtime protocol for the Task-tool-backed specialist-dispatch seam with marker emission sourced from the canonical taxonomy per ADR-004. The Python substrate at `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/specialist_dispatch.py` provides the structural primitives (registry validation, payload construction, log persistence, envelope validation, event emission). This prose IS the LLM-runtime contract that names how to compose those primitives around a Task-tool invocation + wall-clock timer + return-text parsing — three concerns the substrate Python cannot natively express because Task tool is a Claude-Code-skill primitive (NOT a Python API; ADR-004 explicitly rejects the Agent SDK route as "incompatible with orchestrator-as-skill").

This sub-step file is invoked by `steps/run.md`'s step (f); it is also the binding point Stories 2.7 / 2.8 / 2.9 / 2.10 / 2.11 / 2.12 / 2.13 compose against at runtime.

## Pre-dispatch (Python substrate)

Before invoking the Task tool, compose the substrate primitives in this load-bearing order:

1. **Construct the dispatch payload.** Invoke `build_dispatch_payload(specialist="dev", story_id=..., attempt_number=0, story_doc_resolution=..., agent_definition_path=..., prompt_body_renderer=default_prompt_body_renderer)`. The substrate reads `agent_definition_path` AS DATA via `Path.read_text(encoding="utf-8")` (NEVER via `import` — FR62 + ADR-004's pluggability invariant). The renderer composes the agent-definition text + story context + AC list into the canonical Task-tool prompt body.

2. **Emit the `specialist-dispatched` orchestrator-event.** Invoke `event_log_appender(make_specialist_dispatched_event(payload, event_id_factory=default_event_id_factory))`. The helper validates the constructed event structurally against `schemas/orchestrator-event.yaml` BEFORE returning; an `EventConstructionFailed` exception (with `marker_class: ClassVar[None] = None`) means the substrate has a bug, NOT the caller — file an issue.

The substrate at this point owns: the registry-validatable payload + the schema-valid `specialist-dispatched` event in the orchestrator-event log. It does NOT own: the Task-tool invocation itself (next section).

## Dispatch (Task tool)

Invoke the Claude Code Task tool with `payload.prompt_body` as the prompt. Monitor wall-clock time vs. the `timeout_seconds` parameter (default 900s / 15min per NFR-P2; configurable per-callable via `make_task_tool_dispatch_callback(..., timeout_seconds=...)` at construction time, NOT per-call).

**Timeout protocol — load-bearing per AC-6 of Story 2.6:**

If the wall-clock timer exceeds the budget BEFORE the Task tool returns, execute these steps in order:

(a) Raise `SpecialistTimeoutExceeded(timeout_seconds=..., specialist=..., story_id=..., attempt_number=...)`. The exception carries `marker_class: ClassVar[Literal["specialist-timeout"]] = "specialist-timeout"` and `sub_cause: ClassVar[Literal["timeout-exceeded"]] = "timeout-exceeded"`, both sourced VERBATIM from `schemas/marker-taxonomy.yaml` entry 7.

(b) Call `validate_marker_emission(registry, SpecialistTimeoutExceeded.marker_class)` per AC-2 — fail-fast at runtime if the registry doesn't carry the marker class (which would only happen if the taxonomy was tampered with mid-run).

(c) Construct a synthetic `specialist-returned` event with `status="fail"` via `make_specialist_returned_event(payload, return_envelope={"status": "fail", "rationale": str(timeout_exception)}, event_id_factory=default_event_id_factory, return_timestamp=datetime.now(timezone.utc))`. The synthetic envelope's `rationale` field carries the timeout diagnostic; the substrate provides no helper for synthesizing a richer envelope shape — it's the caller's call.

(d) Emit the synthetic `specialist-returned` event via `event_log_appender(...)`.

(e) Propagate or convert the exception per the orchestrator's flow policy (NOT the substrate's — sensor-not-advisor; the substrate's exception is the structural identifier; flow-policy decisions live in the orchestrator skill prompt + downstream Epic 5 stories).

THIS story emits ONLY `timeout-exceeded`; the `context-budget-exceeded` sub-cause from `marker-taxonomy.yaml` entry 7's `sub_classifications: [timeout-exceeded, context-budget-exceeded]` is reserved for context-tracking work in Epic 6 / Story 6.7 — NOT this story.

## Post-dispatch (Python substrate)

When the Task tool returns within the timeout budget, parse the return text as a YAML envelope dict, then compose the substrate primitives in this load-bearing order:

1. **Validate the return envelope.** Invoke `validate_return_envelope(envelope_dict)` (or the strict variant `validate_return_envelope_strict(envelope_dict)` for exception-based flow). The substrate composes `loud_fail_harness.envelope_validator.validate_envelope` + `format_errors` exclusively — no reimplementation. On `valid=False`, the orchestrator MUST halt at the seam and surface the `EnvelopeValidationFailed` diagnostic via NFR-O1's terminal stream; the exception carries `marker_class: ClassVar[None] = None` (envelope-validation failures are NOT loud-fail markers at MVP per AC-5).

2. **Persist the diagnostic log.** Invoke `persist_dispatch_log(payload, return_envelope=validated_envelope, return_timestamp=datetime.now(timezone.utc), log_root=..., run_id=...)`. The log is JSON-serialized at `<log_root>/{story_id}/{run_id}/logs/{specialist}-{attempt_number}.log` per NFR-O3; the on-disk path resolution composes `LOG_PATH_TEMPLATE`. Atomic write via `tempfile` + `os.replace` mirrors Story 2.2's `advance_run_state` precedent verbatim.

3. **Emit the `specialist-returned` orchestrator-event.** Invoke `event_log_appender(make_specialist_returned_event(payload, return_envelope=validated_envelope, event_id_factory=default_event_id_factory, return_timestamp=..., envelope_artifact_path=log_path))`. The `envelope_artifact_path` field points at the on-disk artifact Story 2.7's SubagentStop hook reads from `RunState.last_envelope` per the schemas/run-state.yaml + schemas/orchestrator-event.yaml co-versioning contract.

The substrate at this point owns: the validated envelope (in-memory) + the persisted log (on-disk) + the schema-valid `specialist-returned` event in the orchestrator-event log. The orchestrator skill at runtime owns: the next-state decision via `evaluate_envelope` (Story 2.4's helper), driven by the envelope's `status` field per FR51 / FR52.

## Loud-fail discipline

Errors at every step surface via named-invariant exceptions; the substrate does NOT silently swallow:

- **`SpecialistTimeoutExceeded`** — carries `marker_class="specialist-timeout"` per Pattern 5 (loud-fail marker at runtime; surfaces in PR bundle's loud-fail block per Story 6.7).
- **`UnknownMarkerClass`** — carries `marker_class: ClassVar[None] = None` per AC-2 (programmer-error invariant; the substrate that VALIDATES marker emissions cannot itself emit a marker because the registry it depends on hasn't loaded the would-be marker class). Surfaces in NFR-O1's terminal stream, NOT the PR bundle's loud-fail block.
- **`EnvelopeValidationFailed`** — carries `marker_class: ClassVar[None] = None` per AC-5 (up-front validation diagnostic; maps to ADR-004's `silent-corruption` sub-cause but the current `marker-taxonomy.yaml` 1.1 enumeration does NOT include a `specialist-envelope-invalid` marker class; future Stories 6.x or an Epic-3 marker-bump may add one). Surfaces in NFR-O1's terminal stream.
- **`EventConstructionFailed`** — carries `marker_class: ClassVar[None] = None` per AC-7 (programmer-error invariant; the substrate built an invalid event, indicating a substrate bug). Surfaces in NFR-O1's terminal stream; file an issue.

The asymmetric `marker_class` posture encodes the architectural distinction between runtime degradation markers (loud-fail doctrine; PR bundle's loud-fail block) and programmer-or-state-misalignment diagnostics (orchestrator's terminal stream; no PR bundle).

## Cross-references

- **Canonical Python composition**: `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/specialist_dispatch.py`
- **Architectural commitment**: `bmad-autopilot/docs/architecture.md#ADR-004` (Specialist Dispatch Mechanism — Task tool as the canonical multi-agent dispatch primitive in Claude Code; three sub-causes for `specialist-crash-mid-execution` enumerated)
- **Registry source-of-truth**: `bmad-autopilot/schemas/marker-taxonomy.yaml` (entry 7 — `specialist-timeout` with `sub_classifications: [timeout-exceeded, context-budget-exceeded]`)
- **Event schema**: `bmad-autopilot/schemas/orchestrator-event.yaml` (schema_version 1.2 per Story 2.6's AC-8 — `specialist-returned` branch's `status` enum includes `decision-needed`)
- **Envelope schema**: `bmad-autopilot/schemas/envelope.schema.yaml` (the canonical FR51 / FR52 contract that `validate_return_envelope` enforces)
- **Composed substrate primitives**: `loud_fail_harness.envelope_validator.validate_envelope` (Story 1.2), `loud_fail_harness.event_validator.validate_event` (Story 1.3), `loud_fail_harness.reconciler.load_marker_taxonomy` (Story 1.4)
- **Orchestrator entry**: `bmad-autopilot/skills/bmad-automation/steps/run.md` (step (f) invokes this protocol)
- **Forward consumers**: Stories 2.7 (SubagentStop hook reads `last_envelope`), 2.8 / 2.9 / 2.10 (specialist wrappers supply `agents/{dev,review-bmad,qa}-wrapper.md` files), 2.11 (PR bundle assembly reads the events), 2.12 (per-seam streaming thickens `event_log_appender`), 6.4 (cost telemetry hooks the `(prompt_id, retry_attempt, specialist)` correlation triple per ADR-006), 6.7 (specialist-timeout markers in PR bundle).
