---
expected_marker: plan-rederivation-drift-detected
scenario: A QA run on the `reuse-existing` plan path (persisted plan present, `ac_hash` unchanged) re-derived the QA Behavioral Plan from the current AC + qa-runbook state and cross-checked it against the persisted plan; the two differed at a non-AC-hash drift surface (a changed heuristic list / flow-branch enumeration / semantic-verification tier), so the read-only cross-check surfaced `plan-rederivation-drift-detected` (FR-P2-9) as evidence — without overwriting the persisted plan.
---
# Synthetic story: plan-rederivation-drift-detected

A QA dispatch hit the `reuse-existing` plan path: a `## QA Behavioral Plan`
was already persisted and its `ac_hash` still matched the current AC text, so
FR23's AC-hash drift channel (`plan-drift-detected`) did NOT fire. But the
qa-runbook / derivation state had changed between runs, so when the QA wrapper
re-derived the plan from the **current** AC list + qa-runbook state and
cross-checked it against the persisted plan (FR-P2-9 / Story 20.1), the two
diverged at one of the three non-AC-hash drift surfaces — the per-AC
`heuristic_applicability` list, the within-AC `flow_branches` enumeration, or
the `semantic_verification_tier` pair (`semantic_verification_requirement` +
`expected_evidence_tier`). Those fields are deliberately OUT of
`compute_ac_hash` (it hashes AC text only), so the drift is invisible to FR23
and is exactly the gap FR-P2-9 closes.

The cross-check is **read-only and additive** (sensor-not-advisor): it emits
`plan-rederivation-drift-detected` with a `diagnostic_pointer` naming the
drift surface(s), but it does NOT overwrite the persisted plan and does NOT
regenerate it — FR23's `plan_status` reset remains the only trigger for plan
refresh. The marker rides as evidence so the practitioner can decide whether
the derivation-state change was intentional (then refresh the plan, e.g. via an
AC-text touch that triggers FR23 re-derivation) or treat the persisted plan as
authoritative.

The PR bundle renders a `FR-P2-9 cross-check: drift detected` line co-located
with the retained FR25 plan-persistence compromise note (retain-and-accompany,
not remove) plus a `### Plan re-derivation drift detected` H3 sub-section. This
is a **QA-runtime evidence marker** (orphan, tolerated by enumeration-check),
emitted by `qa_plan_rederivation.surface_plan_rederivation_cross_check`.
