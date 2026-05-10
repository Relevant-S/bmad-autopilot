# MVP completion evidence archive (Story 8.7)

This directory holds the per-journey artifact captures referenced by the
coverage-matrix rows in [`../mvp-completion-evidence.md`](../mvp-completion-evidence.md).

## Four-journey decomposition

The MVP surface is exercised by four named PRD user journeys per
`_bmad-output/planning-artifacts/prd.md:174-326` and `epics.md:3412-3418`.
Each journey covers a distinct failure-or-success surface; together they
cover every MVP FR and NFR.

| Journey | Subdirectory | Surface |
|---|---|---|
| 1 — First Story Happy Path | [`journey-1/`](journey-1/) | install → init → run → Dev → Review (3-layer) → QA (full surface) → merge-ready PR bundle |
| 2 — First Honest Failure | [`journey-2/`](journey-2/) | retry-budget exhaustion → escalation bundle → preserved branch + run-state → human triage |
| 3 — Retry — Context Firewalling | [`journey-3/`](journey-3/) | `patch`-bucket finding → fix-only retry → `scope_expanded_to` declaration → scope-assertion verification |
| 4 — Bail-Back / AC-drift | [`journey-4/`](journey-4/) | AC drift → plan-drift-detected → plan re-derivation; existing-project compatibility / TEA-boundary / N-2 story-doc tolerance |

## Per-journey artifact taxonomy

Each `journey-<n>/` directory contains the artifacts named in Story 8.7
AC-3 verbatim:

- `run-output.txt` — captured per-seam streaming output (Story 2.12)
- `<specialist>-envelope.yaml` — Dev / Review-BMAD / QA return envelopes
- `pr-bundle-<variant>.md` — merge-ready or escalation PR bundle
- supplementary captures specific to the journey (retry-history, run-state,
  scope-assertion verification, plan-drift YAML)
- `journey-<n>-narrative.md` — prose narrative + EnvironmentNotes (Story 7.9 shape) +
  execution date + `## Discovered gaps` triage subsection per AC-5
- `README.md` — per-journey artifact index with one-line descriptions

## Reference-project posture

Per Story 8.7 AC-3 the reference project may be either (a) a fresh
project scaffolded specifically for the MVP-cut journey runs OR
(b) a stand-in reference project the maintainer has used historically
for end-to-end testing. THIS MVP cut uses option (b): the
`bmad-autopilot/` development workspace itself is the stand-in
reference project. Its harness test corpus, synthetic-story fixtures,
schema fixtures, and committed story-implementation artifacts form
the de-facto reference-project surface. The choice is documented per
AC-3 verbatim — "the chosen project's repo URL or scaffold-recipe is
recorded in the artifact's per-journey narrative AND in the evidence
archive's `journey-<n>/README.md` per-journey index file".

## Regeneration triggers

Per `mvp-completion-evidence.md` § Regeneration: regenerate this
archive on each MVP cut, on each post-MVP correct-course event that
adds an FR/NFR, and on each environment baseline shift. Read-only
validation runs via `uv run mvp-completion-evidence` from
`tools/loud-fail-harness/`; full re-capture requires re-running the
four journeys.

## CI gate

The CI gate at `.github/workflows/ci.yml` invokes
`uv run mvp-completion-evidence` per Story 8.7 AC-8. The gate exits
non-zero on any missing row, empty cell, invalid journey value, or
unresolved evidence link — Epic 8's `done` transition cannot ship
until the gate passes.
