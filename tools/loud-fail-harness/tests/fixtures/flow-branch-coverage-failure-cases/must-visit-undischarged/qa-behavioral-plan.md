> **Plan-persistence compromise note (FR25):**
>
> This plan is persisted across runs for resumability.
> Persistence is a known compromise: full QA independence would re-derive the plan every run.
> See `docs/extension-audit.md` and FR-P2-9 (Story 20.1, LANDED — accompanies this note with per-run plan re-derivation cross-check).

<!-- plan_status: generated -->
<!-- ac_hash: b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1 -->

### AC-1

- assertion_shape: verify: a user can sign in with valid credentials
- expected_evidence_tier: tier-1-mechanical
- semantic_verification_requirement: not_applicable
- heuristic_applicability: []
- flow_branches:
  - branch_id: valid-credentials
    description: signing in with a correct email and password
    disposition: must-visit
  - branch_id: locked-account
    description: signing in to an account locked after repeated failures
    disposition: must-visit
