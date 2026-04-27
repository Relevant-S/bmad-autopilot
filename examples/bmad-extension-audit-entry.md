# Audit entry template — `examples/bmad-extension-audit-entry.md`

This is the canonical per-convention entry template referenced by `docs/extension-audit.md` § How to add a new convention and by `CONTRIBUTING.md`. Copy the worked example below and edit each field for your new convention; submit the result as a new row in `docs/extension-audit.md` § Per-convention table.

The worked example uses the `qa` lifecycle state because it is canonical at MVP close (it is the first seed entry in the per-convention table) and its classification, rationale, migration plan, and revisit condition are all real — a contributor can pattern-match against it without needing additional context.

---

## Worked example: `qa` lifecycle state

**Convention name:** `qa` lifecycle state (between `review` and `done`).

The convention name is kebab-case for entity identifiers per Implementation Pattern 1 (`_bmad-output/planning-artifacts/architecture.md` lines 925-966). Use the canonical spelling from the source FR/NFR/ADR/Pattern (here: `qa`, lowercase, as named in PRD FR23 at `_bmad-output/planning-artifacts/prd.md` line 838). When the convention is a story-doc section heading, quote it exactly including the `## ` prefix (e.g., `## QA Behavioral Plan`). When it is an envelope field, use the field's exact spelling (e.g., `failed_layers`, `retry_mode: fix-only`).

**Classification:** `upstream-proposal`.

<!--
Choose exactly one from the 3-tier choice space:
  - automator-internal   — implementation detail at the wrapper layer; no upstream-relevant surface; migration plan is "N/A — internal-only".
  - upstream-proposal    — extends a BMAD-core surface; candidate for upstream RFC; migration plan per NFR-I4.
  - research-needed      — classification undecided pending bounded spike; migration plan is "pending research conclusion"; MUST name a bounding spike.
Multi-value, novel-value, and unclassified entries are forbidden per FR64.
-->

**Rationale:**

Behavioral verification is a load-bearing seam between code review and merge — not a sub-state of `review`. The `qa` lifecycle state is named in PRD FR23 (`_bmad-output/planning-artifacts/prd.md` line 838) and consumed by Story 2.4. If BMAD core absorbs the lifecycle extension, the Automator follows NFR-I4. The `upstream-proposal` classification is honest because the convention WOULD have meaning in BMAD core: any consumer of the BMAD lifecycle benefits from a dedicated behavioral-verification state, not just the Automator's specific specialist composition.

<!--
Rationale guidance:
  - One to three sentences naming WHY the classification was chosen.
  - State explicitly what makes the convention `upstream-proposal`-shaped (would have meaning in BMAD core; reshapes a BMAD-core surface)
    versus `automator-internal`-shaped (lives at the wrapper layer; would have no meaning outside the Automator).
  - Cite the source FR / NFR / ADR / Pattern that introduces or formalizes the convention.
-->

**Migration plan (per NFR-I4):**

- **Acknowledgment** — BMAD core ships a `qa` (or equivalently-named) lifecycle state in the canonical state machine.
- **Adapter window** — the Automator's orchestrator accepts both the BMAD-core state name and the Automator's, normalizing on read; both paths work simultaneously.
- **Deprecation** — the Automator's standalone state is flagged in release notes with the BMAD-core mapping; users receive an upgrade pointer.
- **Removal** — the Automator's standalone state is removed in a subsequent minor release once users have migrated within the documented adapter window.

<!--
Migration plan guidance per NFR-I4 (`_bmad-output/planning-artifacts/prd.md` line 961):
  - For `upstream-proposal`: populate the four stages (acknowledgment → adapter window → deprecation → removal) with concrete-as-possible language for THIS convention.
  - For `automator-internal`: write "N/A — internal-only" — NFR-I4 does not apply because the convention has no upstream-relevant surface.
  - For `research-needed`: write "pending research conclusion" — populate after the bounding spike resolves and the classification is reclassified.
-->

**Revisit conditions (per FR65):**

The classification is reopened if BMAD core ships an equivalent feature (NFR-I4 acknowledgment trigger), if the upstream RFC submission is rejected and the classification therefore needs to flip to `automator-internal` with a documented forked-path commitment, or if the seam between behavioral verification and code review is restructured upstream (e.g., BMAD core absorbs both `qa` and `review` into a unified specialist-driven phase).

<!--
Revisit-conditions guidance per FR65 ("with revisit conditions where applicable"):
  - Name the trigger that should reopen the classification.
  - For `upstream-proposal`: BMAD-core absorption (acknowledgment) and upstream rejection are the two natural triggers.
  - For `automator-internal`: name the BMAD-core feature whose arrival would reopen the classification (e.g., "BMAD core ships an equivalent retry-scope mechanism").
  - For `research-needed`: the bounding spike's resolution is the trigger.
-->

---

## Submission checklist

Before opening the PR adding your convention's row to `docs/extension-audit.md`:

- [ ] Convention name uses canonical spelling from the source FR / NFR / ADR / Pattern.
- [ ] Classification is exactly one of `automator-internal | upstream-proposal | research-needed`.
- [ ] Rationale is one to three sentences and cites the source FR / NFR / ADR / Pattern.
- [ ] Migration plan matches the classification's discipline (NFR-I4 four-stage flow / "N/A — internal-only" / "pending research conclusion").
- [ ] Revisit conditions name the trigger that should reopen the classification.
- [ ] The row is appended at the bottom of the per-convention table; no existing rows were reordered.
