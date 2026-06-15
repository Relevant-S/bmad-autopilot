> **Plan-persistence compromise note (FR25):**
>
> This plan is persisted across runs for resumability.
> Persistence is a known compromise: full QA independence would re-derive the plan every run.
> See `docs/extension-audit.md` and FR-P2-9 (Story 20.1, LANDED — accompanies this note with per-run plan re-derivation cross-check).

<!-- plan_status: generated -->
<!-- ac_hash: a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90 -->

### AC-1

- assertion_shape: verify: a logged-in user can add an item to the cart
- expected_evidence_tier: tier-1-mechanical
- semantic_verification_requirement: not_applicable
- heuristic_applicability: []
- flow_branches:
  - branch_id: empty-cart-add
    description: adding the first item to a previously empty cart
    disposition: must-visit
  - branch_id: increment-existing
    description: adding an item already in the cart increments its quantity
    disposition: must-visit
  - branch_id: max-quantity
    description: adding an item already at the per-line quantity ceiling
    disposition: must-visit

### AC-2

- assertion_shape: verify: the checkout form rejects an invalid payment card
- expected_evidence_tier: tier-2-outcome
- semantic_verification_requirement: required
- heuristic_applicability: [error-state]
- flow_branches:
  - branch_id: expired-card
    description: submitting a card past its expiry date
    disposition: must-visit
  - branch_id: wrong-cvc
    description: submitting a card with an incorrect CVC
    disposition: must-visit
  - branch_id: unsupported-network
    description: submitting a card from an unsupported card network
    disposition: intentionally-skipped
    skip_rationale: card-network gating is out of MVP scope

### AC-3

- assertion_shape: verify: an order confirmation page renders after a successful purchase
- expected_evidence_tier: tier-3-semantic
- semantic_verification_requirement: optional
- heuristic_applicability: [empty-state]
- flow_branches:
  - branch_id: guest-checkout
    description: confirmation render for a guest (non-logged-in) purchase
    disposition: must-visit
  - branch_id: gift-receipt
    description: confirmation render with the gift-receipt option enabled
    disposition: intentionally-skipped
    skip_rationale: gift-receipt rendering is deferred to a Phase 2 story
