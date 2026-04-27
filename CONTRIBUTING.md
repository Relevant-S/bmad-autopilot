# Contributing to the BMAD Agent Development Automator

The Automator is greenfield code inside a brownfield ecosystem. The BMAD methodology, story-doc conventions, and lifecycle states predate this project; the Automator extends them but does not invent atop them by default. As stated in the PRD's brief invariant (`_bmad-output/planning-artifacts/prd.md` line 82): "Greenfield for the Automator inside a brownfield ecosystem (BMAD methodology, conventions, and artifacts). 'No invention by default' and the BMAD-extension audit (automator-internal / upstream-proposal / research-needed) are load-bearing constraints, not stylistic preferences." Every PR that introduces a new convention is held to that discipline.

## Adding a new convention

If your change introduces a new convention — a new lifecycle state, a new story-doc section, a new envelope field, a new orchestrator pattern, a new retry flag, anything that didn't exist in BMAD core before — it must be classified per the BMAD-extension audit before merging.

Follow these four steps:

1. **Open `docs/extension-audit.md`** and read the `## Classification taxonomy` section. The three classifications are `automator-internal`, `upstream-proposal`, and `research-needed`. Confirm you understand which one fits your convention and how the choice constrains future migration behavior per NFR-I4 (`_bmad-output/planning-artifacts/prd.md` line 961 — BMAD-core-absorption migration behavior).
2. **Add a row to the per-convention table** in `docs/extension-audit.md`. First verify your convention isn't already enumerated — duplicate entries are forbidden; if it exists, the existing classification governs. Use the canonical column layout: convention name / classification / rationale / migration plan / revisit conditions. Append your row at the bottom; existing rows are never reordered (the table is append-only so the diff history doubles as the audit trail).
3. **Classify your convention** using the `## Classification taxonomy` in `docs/extension-audit.md`. Choose exactly one of `automator-internal`, `upstream-proposal`, or `research-needed`. The classification is a load-bearing engineering decision — misclassifying an upstream-relevant convention as `automator-internal` traps the project on a forked path.
4. **Fill in the migration plan per NFR-I4** if you classified the convention as `upstream-proposal` (acknowledgment → adapter window → deprecation → removal). For `automator-internal`, write `N/A — internal-only`. For `research-needed`, write `pending research conclusion` and name the bounding spike per `docs/extension-audit.md` § Research-blocker handling.

## Audit entry template

Use `examples/bmad-extension-audit-entry.md` as the canonical entry template. It shows a worked example you can pattern-match — the canonical shape includes convention name, classification (with the 3-tier choice space called out), rationale (with 1-3 sentence guidance), migration plan per NFR-I4, and revisit conditions per FR65.
