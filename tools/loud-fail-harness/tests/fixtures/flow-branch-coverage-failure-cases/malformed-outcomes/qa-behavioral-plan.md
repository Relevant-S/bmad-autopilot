> **Plan-persistence compromise note (FR25):**
>
> This plan is persisted across runs for resumability.
> Persistence is a known compromise: full QA independence would re-derive the plan every run.
> See `docs/extension-audit.md` and FR-P2-9 (Story 20.1, LANDED — accompanies this note with per-run plan re-derivation cross-check).

<!-- plan_status: generated -->
<!-- ac_hash: d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3 -->

### AC-1

- assertion_shape: verify: a profile page renders the user's display name
- expected_evidence_tier: tier-1-mechanical
- semantic_verification_requirement: not_applicable
- heuristic_applicability: []
- flow_branches:
  - branch_id: own-profile
    description: rendering the profile page for the logged-in user
    disposition: must-visit
