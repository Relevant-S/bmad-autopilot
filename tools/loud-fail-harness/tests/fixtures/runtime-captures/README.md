# Runtime-capture fixture corpus (Story 6.8)

Authoritative landing: Story 6.8 (FR33 runtime reconciliation gate). Substrate references: FR33 (runtime variant), Pattern 5 (loud-fail / named-invariant discipline), ADR-003 (substrate-component-3 reconciler reuse). Sibling corpus to `examples/synthetic-stories/` (Story 1.7 / 1.8's fixture-driven gate input).

## Purpose

Captures of representative reference-project runs, minimized to the shape the FR33 runtime reconciliation gate (`fr33_runtime_gate.py`) consumes. Each capture directory carries TWO files: `events.jsonl` and `run-state.yaml`. The runtime gate's default-glob (`tests/fixtures/runtime-captures/*/`) picks up every direct subdirectory automatically — adding a new capture is "create directory + drop two files" with no test code change.

## Canonical files

### `events.jsonl` (per Story 2.12)

JSON Lines format; one orchestrator-event entry per line. Canonical shape per `schemas/orchestrator-event.yaml` (Story 1.3) at the user-runtime resolved path `_bmad-output/qa-evidence/<story_id>/<run_id>/events.jsonl` (Story 2.12's `default_event_log_path`).

Each entry carries the four common required fields (per `schemas/orchestrator-event.yaml` lines 80-111):

- `event_class` — kebab-case identifier from the canonical event-class enum.
- `event_id` — opaque per-event identifier.
- `timestamp` — ISO 8601 string.
- `story_id` — bound story identifier.

**Skip-event entries additionally carry:**

- `marker_class` (REQUIRED for skip-events) — kebab-case Pattern 2 marker-class identifier (e.g. `LAD-skipped`, `Tier-3-not-configured`). Sourced from `schemas/marker-taxonomy.yaml` (Story 1.4). Entries WITHOUT `marker_class` are non-skip events (state-transition / specialist-dispatched / etc.) and are filtered out of reconciler input by the runtime gate.
- `emission_site` (OPTIONAL) — free-form code-surface string (e.g. `agents/lad-wrapper.md:1`, `tools/loud-fail-harness/src/loud_fail_harness/qa_evidence_tier.py:354`). Used by the AC-2 verbatim diagnostic template's `{code_surface}` placeholder. Absent → the rendered diagnostic substitutes `<unknown-surface>` with a documented annotation.

**Capture-format extension:** `marker_class` and `emission_site` are extension fields beyond the canonical orchestrator-event schema (which declares `additionalProperties: false`). Promoting them to canonical fields is a Phase 2 thickening tracked in `deferred-work.md` (per Story 6.8 Dev Notes "Non-trivial design decisions" #2). At MVP, the runtime gate validates SHAPE (the four common required fields) rather than calling `validate_event` against the strict canonical schema — strict validation would loud-fail on every skip-event entry.

### `run-state.yaml` (per Story 2.2)

Canonical shape per `schemas/run-state.yaml` (Story 2.2's atomic run-state schema; schema_version 1.3 post-Story-6.2). The runtime gate consumes the captured run's `active_markers` tuple as the runtime marker source — ZERO new fields added by Story 6.8. Each entry in `active_markers` is a kebab-case Pattern 2 marker-class identifier (optionally with the `: <sub-classification>` suffix; the matching key in `reconciler.reconcile` is base-class only).

## Synthesis convention (contributor extension)

To extend the runtime gate's coverage with a new capture scenario:

1. **Capture** a real reference-project run's `events.jsonl` from `_bmad-output/qa-evidence/<story_id>/<run_id>/events.jsonl` AND the corresponding `run-state.yaml` from the run's snapshot at completion.
2. **Minimize** by removing non-skip events (state-transition, specialist-dispatched, etc.) from `events.jsonl` while preserving:
   - At least the four common required fields on every retained entry.
   - Every entry whose `marker_class` field declares a skip-class (DO NOT drop these).
   - One or two surrounding `state-transition` entries for narrative context (optional but recommended for human readability — the runtime gate filters them out).
3. **Add a `marker_class` field** to skip-event entries that originated from a skip-classifying specialist envelope — the field is populated at capture-synthesis time, NOT during the original run (the canonical schema doesn't carry it at MVP per the design decision above).
4. **Add an `emission_site` field** to skip-event entries when the originating code surface is known — recommended for diagnostic clarity in CI output.
5. **Place under the appropriate corpus** — happy-path captures go under `tests/fixtures/runtime-captures/<scenario-slug>/` (default-globbed by CI; capture MUST reconcile cleanly); known-failure captures go under `tests/fixtures/runtime-captures-failure-cases/<scenario-slug>/` (NOT default-globbed; referenced by unit tests). The slug should be a kebab-case identifier describing the scenario (e.g. `clean`, `missing-emission`, `cost-near-ceiling-runtime`).
6. **Default-glob picks up happy-path captures only** — the gate's `tests/fixtures/runtime-captures/*/` invocation iterates every direct subdirectory of the happy-path corpus; no test code change required when adding a happy-path capture.
7. **Add a unit test** in `tests/test_fr33_runtime_gate.py` if the new capture exercises a new failure mode (otherwise the existing tests cover the canonical cases via the existing `clean/` and `missing-emission/` fixtures).

## Corpus layout — happy-path vs. failure-case split

The runtime-capture corpus is split across TWO sibling directories so the CI step's default-glob remains green per AC-7's "CI step exits 0 on green build" requirement:

- `tests/fixtures/runtime-captures/` — **happy-path corpus** (THIS directory). Default-globbed by the CI step's `uv run fr33-runtime-gate` invocation. Every capture under this root MUST reconcile cleanly. Contributors adding new captures should drop them here only when the capture is known to pass.
- `tests/fixtures/runtime-captures-failure-cases/` — **known-failure corpus**. NOT default-globbed; referenced explicitly by unit tests (`tests/test_fr33_runtime_gate.py`). Captures here exercise the gate's exit-1 / exit-2 paths and witness the AC-2 verbatim diagnostic shape.

This split mirrors Story 1.8's posture: the canonical synthetic-stories corpus at `examples/synthetic-stories/` contains only fixtures whose `expected_marker` reconciles cleanly; failing cases are constructed in `tmp_path` during tests OR live in a sibling location.

## MVP captures

### `runtime-captures/clean/`

A representative reference-project capture where TWO declared skip-events (`LAD-skipped` per Story 4.7 / Phase-1.5; `Tier-3-not-configured` per Story 4.8) reconcile cleanly to TWO matching markers in `active_markers`. Exercises the gate's exit-0 path. Both skip-classes are MVP-canonical optional-tool skips with stable runtime emission.

### `runtime-captures-failure-cases/missing-emission/`

Same shape as `clean/` but the captured `run-state.yaml`'s `active_markers` is missing one marker (`Tier-3-not-configured`) — the runtime gate detects the unreconciled skip-event and emits a `runtime-reconciliation-mismatch` finding carrying the AC-2 verbatim diagnostic. Exercises the gate's exit-1 path. Lives in the failure-cases sibling so the CI step's default-glob does NOT pick it up.

## See also

- `docs/architecture.md` § FR33 runtime reconciliation gate — shared reconciler component, runtime-shape diagnostic, captured-input contract (Story 6.8 resolution).
- `docs/extension-audit.md` § FR33 runtime reconciliation gate (Story 6.8 close).
- `examples/synthetic-stories/README.md` — sibling fixture corpus for Story 1.8's fixture-driven gate (different inputs; same reconciler component per Story 6.8 AC-1).
