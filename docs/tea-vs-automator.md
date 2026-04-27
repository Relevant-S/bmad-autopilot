# TEA vs. Automator boundary

This document anchors the boundary between the **Test Architect (TEA)** module and the **BMAD Agent Development Automator**. Both run per BMAD story; they don't overlap. The boundary is named in PRD § What Makes This Special (`_bmad-output/planning-artifacts/prd.md` line 69, the behavioral-verification gap framing), operationalized by PRD § FR16-FR25 (`_bmad-output/planning-artifacts/prd.md` lines 829-840, the QA behavioral verification scope), surfaced at install time per PRD § FR34 (line 856) and PRD § FR38 (line 863, TEA hard-dependency at `init`), and locked at the architectural level in architecture.md's Technical Constraints & Dependencies section (`_bmad-output/planning-artifacts/architecture.md` line 809, the total-block dependency declaration that names TEA as a hard dependency and codifies the QA-AC-only rule).

The `## First-Run Orientation Message` section below is read at runtime by Story 7.8 (`init` precondition diagnostic flow). Edits to that section's text propagate to runtime emissions on the next install. See `## Notes for contributors editing this section` near the end of this document before changing it.

## What TEA does vs. what the Automator does

The two specialists divide work along a clean asymmetry — they look at different artifacts, answer different questions, and produce different evidence.

**TEA — Test Architect.** TEA's scope is the **test suite**: the test files in your repo, the coverage data those tests produce, and the AC-derived acceptance tests TEA generates from a story's Acceptance Criteria. TEA validates *the tests themselves*: it runs the suite, assesses coverage, generates new acceptance tests when AC drift is detected, and reports on suite health. TEA reads test files. TEA does not exercise the running product.

**Automator — BMAD Agent Development Automator.** The Automator's scope is the **running application**: the UI surface, the API surface, and the behavioral evidence produced by driving those surfaces against the story's AC. The QA specialist inside the Automator drives Playwright MCP for web project types and HTTP for API project types (per PRD FR16-FR25), produces per-AC behavioral evidence (assertions, screenshots, HTTP traces, logs), and grades the running system against the AC. The Automator does **not** read test files; the QA specialist reads only the AC.

This asymmetry is what the next section's verbatim boundary statement names. Reading it the wrong way (e.g., "TEA also exercises the product" or "the Automator's QA also reads test files") collapses the gap that motivates having both specialists in the BMAD stack.

## The boundary statement

Quoted verbatim from `_bmad-output/planning-artifacts/architecture.md` line 809 (Technical Constraints & Dependencies section):

> **TEA validates tests; Automator exercises product. QA reads AC only — never TEA test files.**

The "QA reads AC only — never TEA test files" half is the load-bearing operational rule: the Automator's QA specialist is forbidden from reading TEA's test files because doing so lets QA inadvertently grade-its-own-test-suite — re-running assertions TEA already validated and reporting them as behavioral evidence. The boundary forces QA to derive evidence from the running product against the AC text directly, which is the only way the QA specialist's verdict is independent of the test-suite's own claims.

## First-Run Orientation Message

This section is the canonical orientation-message text emitted at runtime by `/bmad-automation init` on first successful install (per PRD FR34, PRD line 305).

> ✅ TEA detected. Quick note: **TEA validates your test suite** (runs your tests, assesses coverage, generates acceptance tests from AC). **The Automator exercises your running product** (drives the UI/API against AC, produces behavioral evidence). Both run per story; they don't overlap. Full boundary in `docs/tea-vs-automator.md`.

## Notes for contributors editing this section

The `## First-Run Orientation Message` section above is **read at runtime by Story 7.8** during `/bmad-automation init`. Any edit to that section's text propagates to runtime emissions on the next install. Treat it as code, not docs:

- Do not rewrap, rephrase, or "improve" the orientation text without an explicit FR-level ask. The text is byte-identical to PRD line 305; PR review compares the section body against PRD line 305 to detect drift.
- The section heading is exactly `## First-Run Orientation Message` — two `#` characters, four hyphenated/spaced words, no trailing punctuation, no emoji prefix. Story 7.8's runtime extractor parses on this exact heading.
- Keep the section body to the orientation text only. Commentary inside the section leaks into the runtime emission. Notes about the runtime contract live here, in this trailing section, not above.
- Future revisions to the orientation message are a PR against this file's `## First-Run Orientation Message` section, not against `init`'s code. The doc is the source of truth; the code reads from the doc.
