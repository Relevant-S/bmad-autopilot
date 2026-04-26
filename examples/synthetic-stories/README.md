# Synthetic-story fixtures (ADR-003 Layer C completeness mitigation)

This directory holds one synthetic-story fixture per marker class enumerated
in [`schemas/marker-taxonomy.yaml`](../../schemas/marker-taxonomy.yaml). Each
fixture is the minimal scenario that exercises that marker class's emission
path — providing the closure proof that every marker class has at least one
fixture exercising it before runtime markers exist.

These fixtures are CI-only — `tools/loud-fail-harness/` (substrate component
5, [`fixture_coverage.py`](../../tools/loud-fail-harness/src/loud_fail_harness/fixture_coverage.py))
consumes this directory and asserts the taxonomy ↔ fixture-set bijection per
ADR-003 Layer C. Story 1.8's FR33 fixture-driven gate (lands later in Epic 1)
will replay each fixture's `expected_marker` through `reconciler.py` to assert
the reconciliation matches the declared expectation.

## Fixture index

| Fixture file | Expected marker class | Scenario summary |
|---|---|---|
| `LAD-skipped.md` | `LAD-skipped` | LAD MCP unavailable / API key absent during code review; loop continues without 4th adversarial layer. |
| `Tier-3-not-configured.md` | `Tier-3-not-configured` | QA Tier-3 (semantic verification) not configured for an AC; verification proceeds with Tier-1/Tier-2 only. |
| `bundle-assembly-failed.md` | `bundle-assembly-failed` | PR bundle assembly (Stop hook) failed due to assembler logic error (envelope shape, finding rendering, taxonomy mismatch). |
| `context-near-limit.md` | `context-near-limit` | Specialist's working context approaching the model's context budget; signals retry should be fix-only. |
| `cost-near-ceiling.md` | `cost-near-ceiling` | In-flight cost-telemetry approaching budget ceiling (default 75%); signal before exhaustion. |
| `cost-telemetry-unavailable.md` | `cost-telemetry-unavailable` | OTel cost-event pipeline failed; cost data unavailable; loop continues with marker rather than fabricated zeros. |
| `dangling-evidence-ref.md` | `dangling-evidence-ref` | PR bundle contains an evidence reference path that does not resolve to an on-disk artifact. |
| `env-setup-failed.md` | `env-setup-failed` | Env provisioning (dev server / port-binding / Playwright launch) failed; QA phase skips with this marker. |
| `evidence-truncated.md` | `evidence-truncated` | QA evidence exceeded `max_evidence_size_mb` and was truncated for the bundle. |
| `heuristic-skipped.md` | `heuristic-skipped` | Exploratory heuristic (empty / error / auth) does not apply to this AC's input or UI surface. |
| `hook-failed.md` | `hook-failed` | A hook's exit code is non-zero; remediation targets the bash script's environment. |
| `init-would-destroy-existing-artifact.md` | `init-would-destroy-existing-artifact` | `init` halts when it would overwrite user-owned content (FR41 / FR42). |
| `mobile-blocked.md` | `mobile-blocked` | Mobile QA is a Phase 1.5 capability; MVP halts with this marker for mobile project type. |
| `orphan-process-cleanup.md` | `orphan-process-cleanup` | Env teardown discovered a process that should have been cleaned up; reaped implicitly + surfaced for visibility. |
| `orphan-run-state-detected.md` | `orphan-run-state-detected` | `status` enumerator found run-state for stories whose story-doc has been deleted, renamed, or moved (FR48b). |
| `plan-drift-detected.md` | `plan-drift-detected` | AC hash diverges between Plan creation and current AC text; Plan status resets and triggers re-derivation. |
| `playwright-mcp-unavailable.md` | `playwright-mcp-unavailable` | Runtime unavailability of Playwright MCP for a web-project QA dispatch; phase skipped, loop continues. |
| `recovery-state-conflict.md` | `recovery-state-conflict` | SessionStart reattachment found run-state and story-doc disagree; cannot reconcile cleanly (NFR-R8). |
| `reconciler-mismatch-runtime.md` | `reconciler-mismatch-runtime` | Runtime reconciler detected a skip-event without a matching marker emission (FR33 runtime variant). |
| `retry-budget-exhausted.md` | `retry-budget-exhausted` | Whole-story retry budget exhausted (FR8); non-advance + state preservation + escalation bundle. |
| `review-layer-failed.md` | `review-layer-failed` | A review layer (Blind Hunter / Edge Case Hunter / Acceptance Auditor / LAD) failed during the parallel pass. |
| `scope-assertion-violation.md` | `scope-assertion-violation` | Dev's diff at envelope return touched files outside declared `affected_files` scope (FR10 fix-only). |
| `smoke-first-abort.md` | `smoke-first-abort` | QA Behavioral Plan's smoke pass failed before AC-detail tests; loop aborts to avoid wasted effort. |
| `specialist-timeout.md` | `specialist-timeout` | A Task-tool-dispatched specialist exceeded the orchestrator's per-specialist timeout budget. |
| `story-doc-version-out-of-window.md` | `story-doc-version-out-of-window` | Out-of-window story-doc template version surfaces marker + upgrade guidance (FR43 / NFR-I5). |
| `undocumented-section-write.md` | `undocumented-section-write` | A specialist attempted to write to a story-doc section not in the documented allowlist. |
| `walking-skeleton-bundle.md` | `walking-skeleton-bundle` | PR bundles produced by a substrate that lacks the loud-fail block carry this marker. |

## Frontmatter shape (validated by `fixture_coverage.py`)

Each fixture file MUST begin with a YAML frontmatter delimited by exactly two
`---` lines. The frontmatter is a YAML mapping with these keys:

- `expected_marker: <string>` — required; the canonical `marker_class`
  identifier this fixture exercises. MUST match an entry in
  `schemas/marker-taxonomy.yaml`.
- `scenario: <string>` — required; one-line plain-English description of what
  story-doc shape would trigger this skip-class at runtime.
- `expected_sub_classification: <string>` — optional; reserved for
  story 1.8's reconciler-replay gate.
- `expected_event_class: <string>` — optional; reserved for story 1.8.
- `notes: <string>` — optional; free-form narrative.

No other top-level keys are permitted.

## How to add a new fixture

When the marker taxonomy gains a new class (per the FR65 / ADR-003
skip-class-recognition workflow), this directory MUST gain a corresponding
fixture. The CI gate (`fixture-coverage`) will fail the build until the
fixture is added. The full workflow:

1. Add the marker class to `schemas/marker-taxonomy.yaml` (per
   marker-taxonomy.yaml's bump rule).
2. Add a fixture file `<marker-class>.md` here, with frontmatter
   `expected_marker: <marker-class>` + `scenario: <one-line description>`,
   plus a 1–3 paragraph markdown body describing the synthetic scenario.
3. Update this README's Fixture index table to add the new row.
4. Re-run `uv run fixture-coverage` locally to confirm the gate passes;
   re-run `uv run enumeration-check` to confirm the broader marker_class
   reference enumeration is consistent.
5. The fixture corpus is co-versioned with `schemas/marker-taxonomy.yaml`'s
   `schema_version`. Fixture-set deltas follow the same bump rule:
   adding a fixture (paired with a new marker class) → MINOR;
   removing a fixture (paired with a marker class removal) → MINOR;
   renaming a fixture (paired with a `marker_class` rename) → MAJOR.

## Versioning + co-version

The corpus is co-versioned with `schemas/marker-taxonomy.yaml` per ADR-003
Consequence 2 (the marker-taxonomy ↔ fixture-coverage co-versioning is
local-exception scope, parallel to the marker-taxonomy ↔ orchestrator-event
co-versioning). Substrate component 5 (this gate) is the CI mechanism that
enforces consistency between them.
