> **Plan-persistence compromise note (FR25):**
>
> This plan is persisted across runs for resumability.
> Persistence is a known compromise: full QA independence would re-derive the plan every run.
> See `docs/extension-audit.md` and FR-P2-9 (Phase 2 upgrade replacing this with per-run plan re-derivation cross-check).

<!-- plan_status: generated -->
<!-- ac_hash: 33b0405cb09c0ed899cf6d585f27925660b27c57ebfd01dad059bc4c6d2bcaaf -->

### AC-1

- assertion_shape: verify: user registration form submits and persists
- expected_evidence_tier: tier-1-mechanical
- semantic_verification_requirement: not_applicable
- heuristic_applicability: []

### AC-2

- assertion_shape: verify: invalid-email submission surfaces inline error
- expected_evidence_tier: tier-2-outcome
- semantic_verification_requirement: required
- heuristic_applicability: [empty-state, error-state]

### AC-3

- assertion_shape: verify: unauthenticated /dashboard redirects to /login
- expected_evidence_tier: tier-3-semantic
- semantic_verification_requirement: optional
- heuristic_applicability: [auth-boundary]
