# Flow-branch-coverage fixture corpus (Story 13.5)

Authoritative landing: Story 13.5 (FR22c within-AC flow-branch coverage CI gate). Substrate references: FR22c (within-AC flow-branch enumeration with skip-with-marker discipline), Pattern 8 (within-AC flow-branch enumeration — QA), Pattern 5 (loud-fail / named-invariant discipline). Sibling-in-posture to `tests/fixtures/runtime-captures/` (Story 6.8's `fr33-runtime-gate` input).

## Purpose

Gate-internal corpus for the `flow-branch-coverage-gate` CI gate (`flow_branch_coverage_gate.py`). Each case is a synthetic QA Behavioral Plan paired with a recorded per-branch run outcome; the gate reconciles, per AC and per enumerated flow branch, the FR22c within-AC branch-coverage contract:

- every `must-visit` branch is discharged by recorded per-branch evidence;
- every `intentionally-skipped` branch is discharged by a `heuristic-skipped: flow-branch-<branch-id>` marker that reconciles against the landed v1.6 marker taxonomy;
- a `must-visit` branch with neither evidence nor a marker is a contract violation the gate catches in CI.

This corpus is **not** placed under `examples/synthetic-stories/` — that corpus is keyed by marker *class* and governed by `fixture-coverage` / `fr33-fixture-gate`. A flow-branch case has no standalone meaning outside this gate, so it is gate-internal corpus, mirroring the `runtime-captures/` precedent.

## Case structure

The CI gate (`uv run flow-branch-coverage-gate`) globs every direct subdirectory of THIS directory. Each case directory carries TWO paired files:

### `qa-behavioral-plan.md`

A QA Behavioral Plan section-content fixture in the exact format Story 13.2's plan-section parser (`qa_behavioral_plan.parse_plan_section`) consumes — the format of the checked-in `examples/qa-behavioral-plans/qa-behavioral-plan-flow-branches.md`:

- the FR25 persistence-note blockquote;
- a `<!-- plan_status: ... -->` comment;
- a `<!-- ac_hash: [0-9a-f]{64} -->` comment (need only be *syntactically* valid — the gate does not perform `ac_hash` drift detection);
- `### AC-<id>` entries, each with the four scalar fields (`assertion_shape`, `expected_evidence_tier`, `semantic_verification_requirement`, `heuristic_applicability`) and, where branches exist, a `- flow_branches:` block.

Note: `### AC-1` parses to a per-AC `ac_id` of `"1"` — the parser strips the `AC-` prefix.

### `flow-branch-outcomes.yaml`

The recorded per-branch run-outcome artifact. A YAML mapping with a single top-level key `must_visit_evidence`, whose value is a list of records — one per `must-visit` branch the case's run discharged with evidence:

```yaml
must_visit_evidence:
  - ac_id: "1"            # parsed per-AC id (string; `### AC-1` -> "1")
    branch_id: empty-cart-add
    evidence_present: true
```

Each record carries exactly `ac_id` (str), `branch_id` (str), and `evidence_present` (bool). `intentionally-skipped` branches are **NOT** listed here — their discharge is the gate-derived `heuristic-skipped: flow-branch-<branch-id>` marker, not a recorded-evidence declaration. A record naming an `intentionally-skipped` branch (or a branch absent from the plan) is an outcome-declaration error the gate catches.

This artifact is the deliberate resolution of the unlabeled-per-branch-evidence problem (Story 13.4 routed it here): the CI gate reconciles `must-visit` coverage against an explicit, `branch_id`-keyed recorded outcome rather than against unlabeled `evidence_refs` — the same posture `fr33-fixture-gate` takes by reconciling against synthetic declared frontmatter. Real-run unlabeled-evidence reconciliation remains review-enforced via the PR bundle's `flow_branch_coverage.must_visit_branch_ids` checklist (Story 13.4).

## Corpus layout — happy-path vs. failure-case split

The corpus is split across TWO sibling directories so the CI step's glob stays green:

- `tests/fixtures/flow-branch-coverage/` — **happy-path corpus** (THIS directory). Globbed by the CI step's `uv run flow-branch-coverage-gate` invocation. Every case under this root MUST reconcile cleanly (the gate exits 0 against it). This `README.md` is a file, not a case directory, and is skipped by the glob.
- `tests/fixtures/flow-branch-coverage-failure-cases/` — **known-failure corpus**. NOT globbed by the CI step; referenced explicitly by `tests/test_flow_branch_coverage_gate.py`. Cases here exercise the gate's exit-1 / exit-2 paths.

This split mirrors Story 6.8's `runtime-captures/` ↔ `runtime-captures-failure-cases/` posture.

## Adding a new happy-path case

1. Create a directory `tests/fixtures/flow-branch-coverage/<case-slug>/` (kebab-case slug).
2. Add `qa-behavioral-plan.md` in the format above — at least one AC with a non-empty `flow_branches[]`.
3. Add `flow-branch-outcomes.yaml` with one `must_visit_evidence` record (`evidence_present: true`) per `must-visit` branch in the plan, and none for `intentionally-skipped` branches.
4. The CI glob picks the directory up automatically — no gate or test code change is required for a happy-path case.
5. Confirm green: `uv run flow-branch-coverage-gate` exits 0.

## MVP cases

### `flow-branch-coverage/clean/`

The canonical pass corpus: 3 ACs, each carrying 2–3 flow branches. AC-1's branches are all `must-visit`; AC-2 and AC-3 mix `must-visit` and `intentionally-skipped`. Every `must-visit` branch is discharged by an `evidence_present: true` record; every `intentionally-skipped` branch reconciles cleanly through `surface_flow_branch_skipped` against the v1.6 taxonomy. Exercises the gate's exit-0 path.

## See also

- `docs/architecture.md` § QA Within-AC Flow-Branch Coverage CI Gate (FR22c / Story 13.5).
- `docs/extension-audit.md` § the `flow-branch-coverage-gate` per-convention row.
- `tests/fixtures/runtime-captures/README.md` — sibling-in-posture gate-internal corpus for the FR33 runtime gate.
