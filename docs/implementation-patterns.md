# Implementation Patterns

This document is the **operational layer** for the seven Implementation Patterns codified in `docs/architecture.md` § "Implementation Patterns & Consistency Rules" (lines 919-1006). Architecture is the canonical-prose source-of-truth — the binding decisions live there. This doc adds rationale + scope + worked do/don't pairs + an enforcement-type tag per pattern, plus the names of the validators (when CI-enforced) or the review-discipline expectation (when review-enforced). When the two docs disagree, architecture.md wins; this doc gets fixed in a same-PR follow-up.

The architecture's "Enforcement Guidelines" (architecture.md lines 1029-1033) split the patterns between CI-enforced and review-enforced based on a tradeoff: CI catches mechanical violations cheaply but adds maintenance overhead; review catches semantic violations regex can't express but is people-expensive. This doc names the choice for each pattern explicitly so the absence of a CI gate is a documented decision rather than a missing artifact.

## Pattern 1: Casing and File-Naming Convention for YAML Artifacts

### Rationale

A consistent casing convention prevents two failure modes that humans miss in review and CI catches in milliseconds: structural keys drifting from snake_case (e.g. `MarkerClass:` instead of `marker_class:` would silently break every consumer that expects the snake_case key) and entity identifiers drifting from kebab-case (e.g. a marker class name with an underscore would no longer match the existing taxonomy's regex shape, breaking cross-doc references). The convention's job is preventing future drift, not forcing a rewrite of older artifacts that already comply (architecture.md line 955).

### Scope

**Cell-1 schema files at the inner-repo `schemas/` root** are CI-enforced via the `naming-lint` validator:

- `schemas/envelope.schema.yaml`
- `schemas/orchestrator-event.yaml`
- `schemas/marker-taxonomy.yaml`
- `schemas/dependencies.yaml`

For these four files, the validator's per-schema position-classification table (`_CASING_RULES` in `tools/loud-fail-harness/src/loud_fail_harness/naming_lint.py`) names which keys/values fall under which rule. PRD-canonical lifecycle/finding literals (e.g. `decision_needed`, `from_state` enum members, `severity: HIGH/MED/LOW`) are deliberately exempt per architecture.md line 955; OTel pass-through dotted keys (`prompt.id`, `claude_code.cost.usage`, …) are exempt per Pattern 3 / ADR-006 Consequence 5.

**Arbitrary code surfaces** (Python identifiers, log message keys, in-memory dict shapes that aren't load-bearing across processes) are review-enforced — the architecture's "field-name casing convention" line 1032 review-enforcement applies to any structural key that isn't in the four cell-1 schemas.

### Examples — do / don't

✅ Structural key (snake_case) + identifier value (kebab-case):

```yaml
markers:
  - marker_class: state-recovery-drift
    diagnostic_pointer: |
      ...
```

❌ Structural key in PascalCase + identifier value with underscores:

```yaml
markers:
  - MarkerClass: state_recovery_drift
    DiagnosticPointer: |
      ...
```

✅ Dictionary-key-as-entity-identifier (kebab-case):

```yaml
dependencies:
  claude-code:
    version_floor: "2.1.32"
  playwright-mcp:
    by_project_type:
      web:
        ...
```

❌ Entity-identifier dictionary key in snake_case:

```yaml
dependencies:
  claude_code:
    version_floor: "2.1.32"
```

### Enforcement type

**Hybrid.** Cell-1 schema files are CI-enforced via `naming-lint` (story 1.12b; runs in `.github/workflows/ci.yml` between `dependencies-validator` and `enumeration-check`). Arbitrary code surfaces are review-enforced per architecture.md line 1032's "field-name casing convention" entry.

Adding a new structural key to one of the four cell-1 schemas: register the key's parent path under `field-name` in `_CASING_RULES`. Adding a new schema file to the cell-1 set: add an entry to `_CASING_RULES` with the per-position glob list and update the codification (this section's Scope).

## Pattern 2: Marker Class Naming Convention

### Rationale

Marker class names are compared as strings by the substrate's reconciliation gates (substrate components 3, 4, 5; stories 1.4 / 1.5 / 1.7 / 1.8) and rendered as labels in PR bundles. A regex-shape rule prevents single-word names (which break the `<domain>-<state>` semantic) and silently-different shapes (`state_recovery_drift` vs. `state-recovery-drift`) that humans miss in review.

### Scope

The `marker_class:` field values plus `sub_classifications:` labels in `schemas/marker-taxonomy.yaml`. The same regex shape governs cross-references to marker class names everywhere else (envelope `findings[].marker_class`, dependency `marker_class` references, runtime emission from specialist code) but the cross-reference enforcement is the existing enumeration_check (story 1.5) cross-validating against the taxonomy — not a separate format regex.

### Examples — do / don't

✅ Marker class names (kebab-with-acronym, ≥ 2 segments):

```yaml
- marker_class: state-recovery-drift
- marker_class: cost-near-ceiling
- marker_class: LAD-skipped              # mixed-case kebab-with-acronym
- marker_class: Tier-3-not-configured    # numeric segment
```

❌ Single-word names, snake_case names, double hyphens:

```yaml
- marker_class: singleword                # < 2 segments
- marker_class: state_recovery_drift      # underscores
- marker_class: state-recovery--drift     # double hyphen
```

✅ Sub-classification labels (lowercase kebab):

```yaml
sub_classifications:
  - port-bind-failed
  - timeout-exceeded
  - otel-pipeline-unreachable
```

❌ Sub-classification labels with uppercase:

```yaml
sub_classifications:
  - Event-Log-Missing                     # uppercase letters not allowed
  - PortBindFailed                        # PascalCase not allowed
```

### Enforcement type

**CI-enforced** via the `naming-lint` validator's Pattern 2 sub-check. Two regex constants at `tools/loud-fail-harness/src/loud_fail_harness/naming_lint.py`:

- `_MARKER_CLASS_REGEX = ^[A-Za-z][A-Za-z0-9]*(-[A-Za-z0-9]+)+$` (≥ 2 segments).
- `_SUB_CLASSIFICATION_REGEX = ^[a-z][a-z0-9]*(-[a-z0-9]+)*$` (lowercase, ≥ 1 segment).

The regexes are encoded as named module-level constants with inline comments naming architecture.md lines 957-965 (Pattern 2 prose) and the AC-3 contract — preventing future contributors from "fixing" the regex to something stricter without a deliberate Pattern 2 amendment.

## Pattern 3: Orchestrator-Event Class Naming

### Rationale

Event class names follow Pattern 2's kebab-case shape (architecture.md line 967) so the cross-doc reference experience is uniform across markers and events. The `cost_event` correction in ADR-006's prose (rephrased to `cost-event` per architecture.md line 969) is an example: the convention's job is preventing future drift while leaving older prose self-correcting under the convention.

### Scope

Event class identifier values in `schemas/orchestrator-event.yaml`:

- The discriminator enum at `/properties/event_class/enum/*`.
- Each `oneOf` branch's `event_class.const` literal at `/oneOf/*/properties/event_class/const`.

OTel pass-through attribute names (`prompt.id`, `claude_code.cost.usage`, `claude_code.token.usage`, `query_source`) are external (host-Bridge per ADR-002; architecture.md line 971); they are NOT recast under our convention.

### Examples — do / don't

✅ Event class names (kebab-case, matching Pattern 2):

```yaml
event_class:
  enum:
    - specialist-dispatched
    - state-transition
    - cost-event
```

❌ Event class names in snake_case:

```yaml
event_class:
  enum:
    - specialist_dispatched              # underscores
    - state_transition
    - cost_event
```

✅ OTel pass-through attribute (dotted keys allowed; not re-cast):

```yaml
"prompt.id": {}
"claude_code.cost.usage": {}
```

### Enforcement type

**Review-enforced.** No dedicated Pattern 3 CI gate is wired in this story; review enforcement is the deliberate choice, documented per architecture.md line 1032 and per epics.md line 1107-1108.

Pattern 1's `naming-lint` gate incidentally checks event class name *casing* (kebab-case identifier values at `/properties/event_class/enum/*` and `/oneOf/*/properties/event_class/const` in `_CASING_RULES["schemas/orchestrator-event.yaml"]`). This is Pattern 1 casing enforcement, not a dedicated Pattern 3 gate. Importantly, Pattern 1's `_KEBAB_CASE_REGEX` allows single-segment names — a single-word event class like `dispatched` passes Pattern 1 — which is precisely why a dedicated Pattern 3 format-regex gate is review-enforced rather than CI-enforced: the residual gap (single-segment event class names) requires human review, not just a kebab-case check.

The cross-reference enforcement (every event class referenced in the codebase exists in `orchestrator-event.yaml`'s enumeration) is owned by `enumeration_check` (story 1.5; substrate component 4). A separate per-event-class format regex (analogous to Pattern 2's `_MARKER_CLASS_REGEX` at the marker side) is review-enforced at MVP scope: format-on-class-names is a marginal-additional-value over the kebab-case identifier-value check + the enumeration cross-reference check; a format regex would be future tightening if it earns its keep, not a pre-emptive gate. A future story that argues for a Pattern 3 CI gate amends architecture.md's enforcement matrix (line 1032) FIRST.

## Pattern 4: State Update Discipline

### Rationale

Run-state writes are the most fragile surface in the system: a partial write or non-atomic rename leaves the run-state-cache and the story-doc-canonical disagreeing, which fires `recovery-state-conflict` at SessionStart. Routing every write through the atomic-write helper (temp-file + atomic rename per NFR-R1) is the structural defense; story-doc-canonical for tiebreak (ADR-005's Reading 3) is the recovery defense.

### Scope

All run-state writes — the helper layer landing in Story 2.2; sprint-status writes to non-BMAD-native lifecycle states (the `qa` state per upstream proposal 1; ADR-005); cost-counter writes batching with other run-state writes between specialist completions (ADR-006 Consequence 2).

### Examples — do / don't

✅ Helper-routed write (signature shape lands in Story 2.2):

```python
# Hypothetical post-Story-2.2 API:
run_state_helper.write(
    story_id="1-12b",
    state=new_state,
    story_doc_callback=update_story_doc,
)
# Helper writes temp file + atomic rename + invokes story_doc_callback.
```

❌ Direct write bypassing the helper:

```python
import yaml
yaml.safe_dump(run_state, run_state_path.open("w"))   # Pattern 4 violation
```

❌ Sprint-status edit without scope check:

```python
# Sprint-status writes are scoped to the `qa` lifecycle state only
# (upstream proposal 1). Writing other states is BMAD-native and goes
# through the BMAD module's helpers, not our orchestrator.
sprint_status["development_status"][story_key] = "done"
```

### Enforcement type

**Review-enforced.** The structural enforcement is the atomic-write helper's API shape (Story 2.2's signature must require a story-doc callback so calling code that bypasses the callback is mechanically impossible). At story 1.12b's landing time, the helper does not exist yet; review enforcement is the only available mechanism for code that touches run-state. A future static-analysis gate that asserted "every YAML write to `_bmad-output/run-state/` calls the helper" would require static analysis of Python call graphs — out of scope for the substrate's five components per ADR-003. No CI gate is wired for Pattern 4; review enforcement is the deliberate choice, documented per architecture.md line 1032 and per epics.md line 1107-1108.

## Pattern 5: Error Handling Discipline

### Rationale

Loud-fail doctrine is the project-defining design principle: when in doubt, fail loudly with an explicit marker class rather than silently swallowing or papering over. Every retry, every skip, every degradation must surface a marker that lands in the PR bundle (FR30 + FR31). The taxonomy's enumeration is what makes this enforceable — the marker class is the authoritative artifact, the actionable-fix-pointer is the operator-facing remediation.

### Scope

Error / failure surfaces in:

- The harness substrate (`tools/loud-fail-harness/`) — every harness module's exit-2 paths name a marker-class-equivalent invariant in the diagnostic.
- Specialist code (`agents/`; lands in Epic 2+) — every error condition that escapes a specialist's local recovery surfaces in the envelope as a `findings[]` entry referencing a marker class.
- Hook scripts (`hooks/`; lands in Story 2.7) — non-zero exit triggers `hook-failed` with a `sub_classifications` value naming the failure mode (`non-zero-exit`, `timeout`, `missing-binary`).
- The orchestrator skill (lands in Story 2.5) — every degradation path emits the corresponding marker class.

### Examples — do / don't

✅ Surfacing a marker for a known failure class:

```python
if env_setup_failed:
    return Envelope(
        status="blocked",
        findings=[Finding(
            marker_class="env-setup-failed",
            sub_classifications=["port-bind-failed"],
            severity="HIGH",
            ...
        )],
    )
```

❌ Silent swallowing:

```python
try:
    spawn_dev_server()
except Exception:
    pass                                  # loud-fail doctrine violation
```

❌ Throwing a custom exception class with no taxonomy mapping:

```python
class MyCustomError(Exception): ...
raise MyCustomError("something broke")    # Pattern 5 violation —
                                          # no marker-class anchor
```

### Enforcement type

**Review-enforced.** The marker-taxonomy.yaml enumeration IS the operational artifact, CI-enforced via:

- `enumeration_check` (story 1.5) — cross-validates `marker_class` references in `dependencies.yaml` and elsewhere against the taxonomy.
- `fixture-coverage` (story 1.7) — every taxonomy class has ≥ 1 synthetic-story fixture.
- `fr33-fixture-gate` (story 1.8) — fixture-driven reconciliation gate.

The discipline of *using* the taxonomy correctly (every error class maps to a marker class; no silent swallowing; exception classes carry the taxonomy anchor) is review-enforced because mapping requires reading code semantics, not regex. A static-analysis gate that asserted "every Python exception class corresponds to a marker class" would require call-graph + class-hierarchy analysis (a Whole New Substrate Component); ADR-003's substrate count stays at five. No CI gate is wired for Pattern 5; review enforcement is the deliberate choice, documented per architecture.md line 1032 and per epics.md line 1107-1108.

## Pattern 6: Python Code Style (Harness Substrate)

### Rationale

The harness substrate is CI-only (View 2 distribution unit; never deployed to users). Its job is to ship robust validators with stable diagnostics; explicit choice of lint rules + formatter + type-checker + dependency manager removes the "whatever the defaults are at the harness's landing time" risk. Pinned tooling per architecture.md line 997 / Starter Template Evaluation Sub-decision 2 prevents drift between contributor environments.

### Scope

All Python code under `tools/loud-fail-harness/`. Code outside the harness (none yet at MVP; orchestrator skill lands in Epic 2+) inherits the convention by default but is not bound by `pyproject.toml`'s configuration of THIS package.

### Examples — do / don't

✅ Type-hinted public API + explicit imports + PEP 8 formatting:

```python
from __future__ import annotations
from collections.abc import Sequence
import pathlib

def lint_casing(file_key: str, raw: object) -> list[ValidationFinding]:
    """One-line summary."""
    out: list[ValidationFinding] = []
    ...
    return out
```

❌ Wildcard import + missing type hints + unused variable:

```python
from yaml import *                        # wildcard import (ruff F403)
def lint_casing(file_key, raw):           # missing type hints
    unused = 42                           # unused (ruff F841)
    ...
```

### Enforcement type

**CI-enforced** via:

- **Ruff (lint).** `[tool.ruff.lint]` `select = ["E", "W", "F"]` with `ignore = ["E501"]` — full pycodestyle errors family (E), pycodestyle warnings (W), and Pyflakes (F). E501 (line-too-long) is suppressed at the project level via `ignore` because line-length enforcement is the formatter's responsibility (`[tool.ruff.format]` + `line-length = 100`); a linter E501 check would fire on existing docstring-heavy modules that AC-9 forbids touching in this story's scope. Extending the set (I, UP, B, RUF) requires the existing harness modules to remain ruff-clean post-PR — fix-where-fixed in the same PR rather than baseline-suppression via `noqa`.
- **Ruff (format).** `[tool.ruff.format]` is present (even if with default settings) so "use Ruff's formatter with project-line-length = 100" is an explicit choice.
- **mypy (type-check).** `[tool.mypy]` runs with `strict = false` at MVP per CLAUDE.md ("mypy strict mode is off for the empty scaffold; per-component strictness lands incrementally"). Per-component strictness via `[[tool.mypy.overrides]] strict = true` lands as new modules opt-in.
- **pytest (tests).** `[tool.pytest.ini_options]` testpaths under `tests/`; the harness CI runs `uv run pytest` on every PR.
- **uv (env management).** Every harness command runs via `uv run …`; `uv.lock` is committed (Astral guidance for application/CI tooling reproducibility).

The exact rule set / strictness posture chosen is a deliberate-choice that future contributors can extend without re-litigating. The doc's rule list is kept in sync with `pyproject.toml` by being authored in the same PR (story 1.12b AC-4).

## Pattern 7: Story-Doc Section Adherence

### Rationale

Story documents are the single canonical artifact specialists read and write during the lifecycle (FR3 / FR4 / FR5 / ADR-005). A specialist that writes to an undocumented section breaks the multi-writer ownership contract (each specialist owns specific sections; cross-section writes are ambiguous-by-design and must be rejected). The runtime enforcement is `story_doc_validator` (story 1.10b) firing at specialist runtime; the authoring-time enforcement is review.

### Scope

- **Specialist runtime writes** — Dev / Review-BMAD / QA / future LAD specialists write only to the documented allowlist:
  - `## Dev Agent Record` (Dev)
  - `## Senior Developer Review (AI)` (Review-BMAD)
  - `## Review Findings` (Review-BMAD)
  - `## QA Behavioral Plan` (QA)
  - `## Review Follow-ups (AI)` (Review-BMAD's follow-up section the Dev addresses)
- **Authoring-time** — contributors writing story files manually use the same allowlist + the BMAD story template's other documented sections (`## Story`, `## Acceptance Criteria`, `## Tasks / Subtasks`, `## Dev Notes`, `## File List`, `## Change Log`). The allowlist applies to the specialist write surface; manual authoring respects the BMAD template.

### Examples — do / don't

✅ Specialist writes within its owned section:

```markdown
## Dev Agent Record

### Agent Model Used
claude-sonnet-4-6

### Completion Notes List
- Implemented Task 1 ...
- Verified Task 2 ...
```

❌ Specialist invents a new section:

```markdown
## Implementation Notes        ← undocumented section; story_doc_validator
This is where I wrote ...        rejects this with `undocumented-section-write`
```

❌ Specialist writes to another specialist's section:

```markdown
## QA Behavioral Plan          ← Dev specialist must NOT write here;
The Dev decided ...              QA owns this section
```

### Enforcement type

**Hybrid (review-enforced authoring; CI-enforced runtime).** The runtime enforcement is `story_doc_validator` (story 1.10b — library-as-CLI-aid; FR66 / NFR-S5; emits `undocumented-section-write` marker). The authoring-time discipline (contributors writing story files manually) is review-enforced because human-authored files don't go through the runtime validator at write time. The `naming-lint` gate does not enforce Pattern 7 — Pattern 7 is about section *names*, not casing.

A future story that audits manually-authored story files for undocumented sections (e.g. by running `story_doc_validator` over the committed story files in CI) would tighten this to fully-CI-enforced; it is not in story 1.12b's scope. No new CI gate is wired for Pattern 7 in this story; the authoring-time review enforcement is the deliberate choice, documented per architecture.md line 1032 and per epics.md line 1107-1108. The runtime CI enforcement via `story_doc_validator` (story 1.10b) predates this story.
