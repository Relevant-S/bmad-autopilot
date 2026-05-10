# PR Bundle: sample-story-ac-drift (merge-ready)

<!-- bundle-mode: walking-skeleton-thickening; is_retry_present: false -->

## Loud-fail block

- **plan-drift-detected** — QA Behavioral Plan was previously
  human-reviewed; AC text changed between runs; the plan has been
  regenerated and re-verified. How to enable / remediate:
  open `_bmad-output/qa-evidence/sample-story-ac-drift/run-001/qa-behavioral-plan.yaml`
  and re-review the regenerated plan. Re-mark `plan_status: human-reviewed`
  after review. See FR23 / Story 4.2 / docs/architecture.md § Pattern 5.

## Story

`sample-story-ac-drift` — exercises QA behavioral-plan AC-hash drift
detection per Story 4.2.

## Dev summary

Implemented per round-1 AC; no code change after AC text edit (the
implementation already covered the broader contract).

## Review summary

Three layers clean.

## QA summary

- Round 1: pass (plan generated and human-reviewed)
- Round 2: AC-hash drift detected; plan regenerated; AC-1 re-verified pass

plan_status: generated (reset per FR23)

## Plan-persistence-compromise visibility (FR25)

The plan-persistence-compromise status IS visible in this PR bundle
per FR25's "loud-fail-applied-to-our-own-architecture" principle.
The drift signal is the practitioner's hint that the contract has
shifted.

## Cost telemetry

| Specialist | First-pass | Retries | Total |
|---|---|---|---|
| Dev | $0.42 | — | $0.42 |
| Review-BMAD | $0.31 | — | $0.31 |
| QA | $0.51 | $0.49 (re-derive) | $1.00 |
| **Total** | **$1.24** | **$0.49** | **$1.73** |
