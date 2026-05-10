# Journey 3 — Retry — Context Firewalling (narrative)

## Reference project

Stand-in reference project per Story 8.7 AC-3 option (b). Exercised
against the synthetic-story fixture
`tests/fixtures/sample-story-retry-patch-fix.md` with the
context-firewalling boundary verified by
`tests/fixtures/sample-story-retry-scope-violation.md` (negative
case — scope violation triggers loud-fail per FR12).

## Narrative

The clean-retry path lands a story where Review-BMAD's first pass
finds a real defect with `bucket: patch` (Story 5.2). The
orchestrator routes the patch-bucket finding to Dev for retry-1
WITHOUT escalating; Dev runs in `retry_mode: fix-only` (Story 5.3 /
FR10) with the affected files declared as the scope. Dev's return
envelope populates `scope_expanded_to` (Story 5.3 / FR11) listing
any files touched outside the original scope (empty list on a
clean retry).

The orchestrator runs scope-assertion verification (Story 5.4 /
FR12): it diffs the actual git changeset against `scope_expanded_to`.
If they agree, the retry proceeds. If they disagree (e.g., Dev
edited an out-of-scope file but didn't declare it), the orchestrator
fails loudly with a `scope-assertion-violation` marker — this is
the FR12 invariant.

In THIS journey, the retry is clean: scope-assertion verifies, the
re-Review pass clears, QA verifies, the merge-ready bundle is
assembled WITH retry history embedded (NFR-R5 / FR13). The bundle's
loud-fail block is empty — `is_retry_present: true` is the only
non-default flag.

The retry-budget consumes 1/2 (Story 5.1); the per-retry cost is
tracked in NFR-P5's per-retry breakdown. Context-firewalling means
Dev does NOT receive the full review prose (FR9); the orchestrator
derives structured action items from the patch-bucket finding and
hands those to Dev — bounding Dev's context window per NFR-P4.

## Environment notes (Story 7.9 EnvironmentNotes shape)

```yaml
claude_code_version: "2.1.32"
os_label: "darwin-25.3.0"
hardware_tier: "developer-laptop"
python_version: "3.12.5"
```

## Execution date

2026-05-10 (ISO-8601).

## Discovered gaps

Per Story 8.7 AC-5's three-class triage discipline:

- **Missing implementation**: none. Stories 5.2-5.4 (bucket-driven
  retry routing + fix-only retry + scope-assertion verification)
  are all done.
- **Missing test**: none. `test_retry_router.py`,
  `test_retry_dispatch.py`, `test_scope_assertion.py`,
  `test_scope_assertion_routing.py` cover the matrix.
- **Missing evidence capture**: same option (b) posture as
  journey-1 / journey-2.
