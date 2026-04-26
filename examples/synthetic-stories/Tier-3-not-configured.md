---
expected_marker: Tier-3-not-configured
scenario: QA Tier-3 (semantic verification) not configured for this AC; verification proceeds with Tier-1/Tier-2 evidence only.
---
# Synthetic story: Tier-3-not-configured

A QA specialist dispatch against an AC whose `qa-runbook.yaml` has not
opted into Tier-3 semantic verification. QA proceeds with Tier-1
(structural) + Tier-2 (behavioral) evidence; the QA Behavioral Plan's
section emits the `Tier-3-not-configured` marker so the practitioner
sees the lower-tier evidence is intentional, not a coverage gap.

Practitioner remediation: configure semantic verification per
`qa-runbook.yaml`, OR accept the lower-tier evidence as sufficient
for this AC.
