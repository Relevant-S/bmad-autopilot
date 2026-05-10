# Journey 3 — Retry — Context Firewalling

Per Story 8.7 AC-3 verbatim (`epics.md:3417`): "`patch`-bucket finding
→ fix-only retry → `scope_expanded_to` declaration → scope-assertion
verification (clean retry path)".

## Artifacts

| File | Description |
|---|---|
| [`run-output.txt`](run-output.txt) | Per-seam stream including the retry round |
| [`review-findings-with-patch-bucket.yaml`](review-findings-with-patch-bucket.yaml) | Review-BMAD return envelope with `patch`-bucket finding (Story 5.2) |
| [`dev-retry-envelope.yaml`](dev-retry-envelope.yaml) | Dev's retry-mode return envelope with populated `scope_expanded_to` (Story 5.3) |
| [`scope-assertion-verification.txt`](scope-assertion-verification.txt) | Scope-verification module asserting actual diff matches `scope_expanded_to` (Story 5.4) |
| [`pr-bundle-merge-ready-with-retry-history.md`](pr-bundle-merge-ready-with-retry-history.md) | Merge-ready PR bundle with retry history (clean-retry resolution per `prd.md:267-268`) |
| [`journey-3-narrative.md`](journey-3-narrative.md) | Narrative + environment notes + execution date + discovered-gaps |
