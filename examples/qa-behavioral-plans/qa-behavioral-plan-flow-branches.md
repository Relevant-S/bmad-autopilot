> **Plan-persistence compromise note (FR25):**
>
> This plan is persisted across runs for resumability.
> Persistence is a known compromise: full QA independence would re-derive the plan every run.
> See `docs/extension-audit.md` and FR-P2-9 (Story 20.1, LANDED — accompanies this note with per-run plan re-derivation cross-check).

<!-- plan_status: generated -->
<!-- ac_hash: 09c3bf1898bc622d109e5ee0f40fb0f492da72382515f4b4f437f53bce59a13f -->

### AC-1

- assertion_shape: verify: user can register with a valid email
- expected_evidence_tier: tier-1-mechanical
- semantic_verification_requirement: not_applicable
- heuristic_applicability: []

### AC-2

- assertion_shape: verify: registration form rejects invalid input
- expected_evidence_tier: tier-2-outcome
- semantic_verification_requirement: required
- heuristic_applicability: [empty-state, error-state]
- flow_branches:
  - branch_id: blank-email
    description: submitting with the email field left blank
    disposition: must-visit
  - branch_id: malformed-email
    description: submitting an email missing the @ symbol
    disposition: must-visit
  - branch_id: duplicate-email
    description: resubmitting an email already registered
    disposition: intentionally-skipped
    skip_rationale: covered by AC-3's uniqueness assertion

### AC-3

- assertion_shape: verify: unauthenticated access to /dashboard redirects to /login
- expected_evidence_tier: tier-3-semantic
- semantic_verification_requirement: optional
- heuristic_applicability: [auth-boundary]
- flow_branches:
  - branch_id: expired-session
    description: accessing /dashboard with an expired session cookie
    disposition: must-visit
  - branch_id: deep-link
    description: deep-linking to /dashboard/settings while unauthenticated
    disposition: intentionally-skipped
    skip_rationale: deep-link redirect parity is out of MVP scope
