> **Plan-persistence compromise note (FR25):**
>
> This plan is persisted across runs for resumability.
> Persistence is a known compromise: full QA independence would re-derive the plan every run.
> See `docs/extension-audit.md` and FR-P2-9 (Story 20.1, LANDED — accompanies this note with per-run plan re-derivation cross-check).

<!-- plan_status: generated -->
<!-- ac_hash: c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2 -->

### AC-1

- assertion_shape: verify: a search returns results for a known query
- expected_evidence_tier: tier-2-outcome
- semantic_verification_requirement: required
- heuristic_applicability: [empty-state]
- flow_branches:
  - branch_id: present-branch
    description: searching for a query with at least one matching record
    disposition: must-visit
  - branch_id: skipped-branch
    description: searching with a query containing emoji characters
    disposition: intentionally-skipped
    skip_rationale: emoji-query handling is out of MVP scope
