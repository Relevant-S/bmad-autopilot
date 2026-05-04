# Deferred-work.md format spec audit (Story 5.7)

> Spike-with-bounded-timebox instance #1 of the pattern named at `docs/extension-audit.md` § "Research-blocker handling — the spike-with-bounded-timebox pattern" (Story 1.11). Discharges research blocker #1 from `_bmad-output/planning-artifacts/architecture.md` line 849 + line 1322. Backs FR15's escalation-bundle pointer (`prd.md` line 826). The pattern's reusable shape (this file's path layout, sectioning, named-fallback discipline) is the template Story 7.1 (plugin-primitive-stability spike) and any future spike-blockered story instantiates.

## Spike metadata

| Field | Value |
|---|---|
| Spike-start date | 2026-05-04 |
| Spike-end date | 2026-05-04 |
| Timebox duration | 1 calendar week (per `epics.md` line 2442; named at `docs/extension-audit.md` § "Research-blocker handling" principle paragraph) |
| Fallback-fired | **false** — outcome 1 (adopt existing) converged within hours; the BMAD-METHOD convention was discoverable AND already exercised by Story 5.2's runtime emitter |
| Selected outcome | **1 — Adopt existing** (BMAD-existing convention used as-is) |
| Evidence-source enumeration count | 4 (per AC-1 of Story 5.7) |
| Per-convention-table-row backreference | `docs/extension-audit.md` § "Per-convention table" — the most recently appended row (the seventh Epic-5 landing, immediately following Story 5.6's row); classification `automator-internal` |
| FR15 anchor | `_bmad-output/planning-artifacts/prd.md` line 826 ("Orchestrator assembles an escalation bundle … contains retry history, outstanding findings, rationale, and a pointer to `deferred-work.md`") |
| Research-blocker source | `_bmad-output/planning-artifacts/architecture.md` lines 849-852 (the four-blocker enumeration; this spike discharges blocker #1 at line 849) + line 1322 (second occurrence of blocker #1) |
| Epics anchor | `_bmad-output/planning-artifacts/epics.md` lines 2424-2458 (Story 5.7's full epic text) |
| Forward consumers | Story 5.8 (escalation-bundle assembler — FR15 pointer); Story 7.1 (plugin-primitive-stability spike — pattern reuse) |

## Evidence sources reviewed

Four sources audited per AC-1. Each source's contribution to outcome 1 is named below.

### 1. BMAD-METHOD upstream — `_bmad/bmm/4-implementation/bmad-code-review/steps/step-04-present.md` line 32

The canonical authored format spec, verbatim:

> "Also append each `defer` finding to `{deferred_work_file}` under a heading `## Deferred from: code review ({date})`. If `{spec_file}` is set, include its basename in the heading (e.g., `code review of story-3.3 (2026-03-18)`). One bullet per finding with description."

**Kind:** BMAD-METHOD upstream-authored convention (the `bmad-code-review` step's `defer`-classification routing, Step 04 "Present" phase).

**Contribution to outcome 1:** the format is AUTHORED upstream — this is the primary evidence that an existing format exists. The spec names the section-heading shape (`## Deferred from: code review ({date})`), the optional basename-inclusion conditional (`If {spec_file} is set...`), and the bullet shape ("One bullet per finding with description"). Story 5.2's `record_defer_findings` adopts this format with the `{spec_file}` conditional satisfied (the basename is the `story_id` slug, e.g. `code review of 5-1-whole-story-retry-budget-configuration-enforcement (2026-05-03)`).

### 2. BMAD-METHOD quick-dev — `_bmad/bmm/4-implementation/bmad-quick-dev/step-{01,02,04,oneshot}.md`

All four `bmad-quick-dev` step files reference the deferred-work file as a runtime-config field with a stable key:

- `step-01-clarify-and-route.md` line 3: `deferred_work_file: '{implementation_artifacts}/deferred-work.md'` (frontmatter); line 51 names the append-on-defer semantics ("Append deferred goals to `{deferred_work_file}`").
- `step-02-plan.md` line 3: `deferred_work_file: '{implementation_artifacts}/deferred-work.md'` (frontmatter); line 22 names the append-on-defer semantics ("Append deferred goals to `{deferred_work_file}`").
- `step-04-review.md` line 2: `deferred_work_file: '{implementation_artifacts}/deferred-work.md'` (frontmatter); line 44 names append-on-defer in the classification flow ("**defer** — Append to `{deferred_work_file}`.").
- `step-oneshot.md` line 2: `deferred_work_file: '{implementation_artifacts}/deferred-work.md'` (frontmatter); line 27 names append-on-defer ("**defer** — pre-existing issue not caused by this change. Append to `{deferred_work_file}`.").

**Kind:** BMAD-METHOD upstream module config + runtime-flow references.

**Contribution to outcome 1:** confirms the convention is broadly upstream (not a single-step accident) — the same `deferred_work_file: '{implementation_artifacts}/deferred-work.md'` config and append-on-defer semantics are referenced from four independent quick-dev step files, indicating a stable convention worth adopting. Confirms the canonical filesystem path: `{implementation_artifacts}/deferred-work.md`.

### 3. On-disk live exemplar — `_bmad-output/implementation-artifacts/deferred-work.md`

The repo's own running deferred-work artifact, 423 lines as of 2026-05-04.

- **Line 1:** `# Deferred Work` (the document title — H1).
- **Section count:** **47 sections** matching `^## Deferred from:` (counted via `grep -c`). Far exceeds the AC-1 floor of "9+ sections" — the format is in continuous active use across this repo's full code-review history.
- **Representative section header (line 3):** `## Deferred from: code review of 5-1-whole-story-retry-budget-configuration-enforcement (2026-05-03)` — matches Story 5.2's runtime emitter byte-for-byte.
- **Representative bullet (line 5):** `` - **`_make_run_state(**overrides)` silently clobbers `retry_history_length` intent** [`tools/loud-fail-harness/tests/test_retry_budget.py:84`] — `base.update(overrides)` runs after the history tuple is built... `` — matches Story 5.2's runtime bullet shape `- **<finding_id>** [\`<location>\`] — <description>` byte-for-byte.

**Kind:** on-disk live exemplar (the BMAD-METHOD convention as actually written by this repo's own workflows including Stories 3.3 / 3.4 / 3.5 / 4.1 / 4.3 / 4.6 / 4.7 / 4.12 / 5.1 review cycles).

**Contribution to outcome 1:** validates that the BMAD-METHOD convention is REAL (not just authored) — 47 sections of evidence, a continuously-used file. Confirms adoptability: the format has not been reported as inadequate during any of the 47+ section appends, so the escalation-bundle pointer use case (file existence + named-section discoverability + per-finding bullets) is a strict subset of what's already proven workable.

### 4. Implicit prior-art validation — `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/retry_router.py` `record_defer_findings` + `tests/test_retry_router.py`

Story 5.2's runtime emitter and tests structurally enforce the format this audit ratifies.

- `tools/loud-fail-harness/src/loud_fail_harness/retry_router.py` `record_defer_findings` (function body lines 628-732 1-based; 627-731 0-based per Serena):
  - Document title literal: `existing = "# Deferred Work\n\n"` (when file is missing or empty).
  - Section header f-string: `f"## Deferred from: code review of {story_id} ({date_stamp})\n"`.
  - Bullet f-string: `` f"- **{item.finding_id}** [`{item.location}`] — {item.description}\n" ``.
  - Date stamp: `clock().strftime("%Y-%m-%d")`.
  - Section terminator: trailing `"\n"` appended to `section_lines` so the next section starts after one blank line.
- `tools/loud-fail-harness/tests/test_retry_router.py` `test_record_defer_findings_*` (10 cases starting at line 685): structural enforcement of the format-MVP; relevant cases:
  - `test_record_defer_findings_creates_file_when_missing` (line 685) — asserts `# Deferred Work\n\n` document title.
  - `test_record_defer_findings_appends_to_existing_file` (line 707) — asserts the section header is appended at file tail.
  - `test_record_defer_findings_renders_correct_bullet_format` (line 735) — asserts the bullet f-string shape byte-for-byte.
  - `test_record_defer_findings_uses_clock_for_date_stamp` (line 758) — asserts `%Y-%m-%d` stamping.
  - plus six other cases covering empty-input handling, idempotency, double-append boundary, count return, error path.

**Kind:** implicit prior-art validation (the ALREADY-LANDED implementation that mirrors the BMAD-METHOD format byte-for-byte; the structural test suite that enforces the format).

**Contribution to outcome 1:** Story 5.2 already chose outcome 1 implicitly by writing the BMAD-METHOD format byte-for-byte. THIS audit RATIFIES that implicit decision — the audit is documentation, not behavior change. AC-5's byte-for-byte verification (this file's `## Outcome-decision flow` § "Outcome 1") confirms the audit-recorded format matches the runtime emitter without divergence.

## Outcome-decision flow

Three named outcomes per AC-2. Each is evaluated against the AC-1 evidence above; the selected outcome is named first.

### Outcome 1: Adopt existing — **SELECTED**

> "An existing format is found and adoptable as-is — Story 5.8 references it directly; classification recorded in `docs/extension-audit.md` per the row schema with `automator-internal` classification AND a rationale field naming '**BMAD-existing convention used as-is**'." (per `_bmad-output/planning-artifacts/epics.md` line 2436 verbatim — the canonical classification language for outcome 1.)

**Fires because:**

- The BMAD-METHOD format IS authored upstream at `_bmad/bmm/4-implementation/bmad-code-review/steps/step-04-present.md` line 32 (evidence source #1).
- The format is referenced by four quick-dev step files (evidence source #2), indicating a broadly-stable convention.
- The format is in continuous active use on disk — 47 sections across 423 lines (evidence source #3) — without any reported inadequacy.
- Story 5.2's `record_defer_findings` already adopted the format byte-for-byte (evidence source #4) — the structural enforcement is in place via `test_record_defer_findings_*`.

**Byte-for-byte verification against Story 5.2's runtime (per Story 5.7 AC-5):**

| Format element | Audit-recorded | `record_defer_findings` runtime | Match |
|---|---|---|---|
| Document title | `# Deferred Work\n\n` | line ~700: `existing = "# Deferred Work\n\n"` | ✓ |
| Section header | `## Deferred from: code review of <story_id> (<YYYY-MM-DD>)` | line ~717: `f"## Deferred from: code review of {story_id} ({date_stamp})\n"` | ✓ |
| Bullet shape | `- **<finding_id>** [\`<location>\`] — <description>\n` | line ~723: `` f"- **{item.finding_id}** [`{item.location}`] — {item.description}\n" `` | ✓ |
| Date format | `<YYYY-MM-DD>` | line ~715: `clock().strftime("%Y-%m-%d")` | ✓ |
| Section terminator | `\n` (one blank line after the last bullet) | line ~725: `section_lines.append("\n")` | ✓ |

The BMAD-METHOD upstream format at `step-04-present.md` line 32 is a SUPERSET: the upstream spec mentions optional `{spec_file}` basename inclusion in the section header. Story 5.2's choice uses `story_id` per its routing-time data (e.g. `5-1-whole-story-retry-budget-configuration-enforcement`) — which satisfies the BMAD spec's branch where `{spec_file}` IS set, with the basename being the story-id slug. No divergence; no ratification gap.

**Classification:** `automator-internal` (BMAD-existing convention used as-is). See per-convention-table row at `docs/extension-audit.md` § "Per-convention table" (the most recently appended row (immediately following Story 5.6's row).

**No behavior change to `record_defer_findings` is needed** — the audit is read-only verification. AC-10's `git diff --stat` enforces that the substrate source tree is untouched.

### Outcome 2: Extend existing — REJECTED

> "An existing format exists but is inadequate for the Automator's escalation-bundle pointer use case — extension is proposed; classification recorded as `upstream-proposal` with migration plan per NFR-I4 (`prd.md` line 961 verbatim — `acknowledgment → adapter window → deprecation → removal`)." (per `_bmad-output/planning-artifacts/epics.md` line 2437 verbatim.)

**Rejected because the BMAD-METHOD format is sufficient for FR15's escalation-bundle pointer use case.** FR15 needs only:

1. **File existence** — a known canonical path so the pointer can be emitted; satisfied by `{implementation_artifacts}/deferred-work.md` per the four quick-dev step references.
2. **Named-section discoverability** — a stable section-header shape so a future reader can locate the per-story defer record; satisfied by `## Deferred from: code review of <story_id> (<YYYY-MM-DD>)`.
3. **Per-finding bullet shape** — a stable bullet format so individual defers can be enumerated; satisfied by `- **<finding_id>** [\`<location>\`] — <description>`.

All three needs are met by the BMAD-METHOD convention without extension. Adding fields the escalation-bundle pointer doesn't need (e.g. severity classification, retry-round backreference, machine-readable companion) would over-fit the pointer use case at the cost of upstream-proposal latency (NFR-I4's adapter-window discipline) and would require changes to BMAD-METHOD modules that downstream consumers have already adopted as-is.

**No upstream proposal authored.** The migration-plan template that would have applied (NFR-I4: acknowledgment → adapter window → deprecation → removal) is named here for completeness; no entry is opened against it.

### Outcome 3: Define our own — REJECTED (named fallback)

> "No existing format found — Automator defines its own format; classification recorded as `automator-internal` with revisit condition '**if BMAD core adopts a deferred-work convention, reconcile**'." (per `_bmad-output/planning-artifacts/epics.md` line 2438 verbatim — the canonical classification language for outcome 3 + named-fallback structure.)

**Rejected because an existing format DOES exist** (evidence sources #1, #2, #3, #4 above).

**Named-fallback structure** (documented for the pattern's reusability per AC-3 + AC-7 even though the fallback didn't fire): had the bounded timebox (1 calendar week from spike-start `2026-05-04`) expired without convergence on outcome 1 or 2, this spike would have:

1. Defined a deferred-work format internal to the Automator (file path, section-header shape, bullet shape — likely mirroring the existing on-disk artifact's shape since it's the only data point).
2. Added a per-convention-row to `docs/extension-audit.md` with classification `automator-internal` and rationale "no existing BMAD-METHOD convention found within timebox".
3. Recorded the revisit condition verbatim from `epics.md` line 2438: "**if BMAD core adopts a deferred-work convention, reconcile**".
4. Documented the migration path back to outcome 1 (if BMAD core later authors the convention) as an in-place rationale update (the classification remains `automator-internal`; only the rationale changes from "no existing BMAD-METHOD convention found within timebox" to "BMAD-existing convention used as-is") — no schema bump, no source-tree change, since the format is already markdown.

The fallback's named structure is preserved here so a future spike-blockered story has a documented worked example of what the fallback path would have looked like — Story 7.1 (plugin-primitive-stability spike) is the first downstream consumer of this pattern.

## Forward consumers

Three named consumers per AC-7 item 4. Each is named explicitly so the convention reuse is discoverable from THIS artifact (not just from the consumer's own text when it lands).

### Story 5.8 — Escalation-bundle assembly mechanism (FR15)

`5-8-escalation-bundle-assembly-mechanism-consumes-epic-4-contracts-5-6-5-7` (per `_bmad-output/implementation-artifacts/sprint-status.yaml` line 116) — consumes THIS spike's outcome on two seams:

1. **Per-convention-row classification** — Story 5.8's bundle assembler emits the FR15 pointer to `deferred-work.md` knowing the format is `automator-internal` (so no upstream-proposal latency gates the bundle assembly). The pointer targets the same file Story 5.2's `record_defer_findings` writes to — `{implementation_artifacts}/deferred-work.md` per the BMAD-METHOD canonical path.
2. **Runtime emitter Story 5.2's `record_defer_findings`** — the assembler can compose against the existing emitter's output without per-bundle format validation; the format is RATIFIED, so the bundle's pointer can name the file directly with a static path expression rather than a runtime-discovered shape.

The seam is one-way: Story 5.8 reads THIS artifact + the per-convention-row to compute the pointer; THIS artifact does not reference Story 5.8's bundle shape (Story 5.8 owns the bundle's content).

### Story 7.1 — Claude Code plugin-primitive-stability spike

`7-1-claude-code-plugin-primitive-stability-spike-task-bounded-with-named-fallback` (per `_bmad-output/implementation-artifacts/sprint-status.yaml` line 135) — REUSES THIS story's pattern shape:

- **Same evidence-artifact subdirectory:** `bmad-autopilot/docs/research-spikes/{spike-start-date}-{topic-slug}.md` — Story 7.1 lands `bmad-autopilot/docs/research-spikes/<7.1-spike-start-date>-claude-code-plugin-primitive-stability.md` (or equivalent topic slug).
- **Same four-section evidence-artifact shape:** `## Spike metadata` / `## Evidence sources reviewed` / `## Outcome-decision flow` / `## Forward consumers`.
- **Same three-outcome decision flow with named fallback:** Story 7.1's three named outcomes will be domain-specific (e.g. "adopt official primitive / use git-clone-symlink fallback / wait for primitive stabilization"); the named-fallback discipline mirrors THIS story's outcome 3 structure.
- **Same per-convention-row append:** Story 7.1 appends a row to `docs/extension-audit.md` § "Per-convention table" with classification per its outcome.
- **Same closing-remark sub-paragraph append:** Story 7.1 appends a closing-remark sub-paragraph to `docs/extension-audit.md` § "Research-blocker handling" immediately after its blocker's "Discharged by Story 7.1" anchor (line 169 at this story's landing time).

THIS artifact's existence as a worked example IS the structural enforcement that Story 7.1 has a template to follow; the principle paragraph at `docs/extension-audit.md` § "Research-blocker handling" line 158 cites Story 5.7 verbatim ("Worked example: Epic 5 Story 5.7 audits the `deferred-work.md` format..."). After THIS story lands, that aspirational pointer is backed by an actual story-close record.

### Future spike-blockered stories (any post-MVP research blocker)

The spike-with-bounded-timebox pattern named at `docs/extension-audit.md` § "Research-blocker handling" expects any future research blocker to surface as a story in its dependent epic with the three components: defined exit criterion, bounded timebox, named fallback. Future spike-blockered stories instantiate the same shape THIS story commits — the canonical worked example.
