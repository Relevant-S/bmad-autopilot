# Test fixture — Story 7.1 outcome AMBIGUOUS (audit-doc-drift; two canonical outcome strings present)

This fixture deliberately contains TWO of the three canonical outcome strings
to exercise `parse_spike_outcome`'s multiple-match loud-fail per AC-1 + AC-7
item 6 (an audit-doc-drift scenario where a partial edit left both strings).

## Per-convention table

| Convention name | Classification | Rationale | Migration plan | Revisit conditions |
|---|---|---|---|---|
| Install-path priority — Claude Code plugin primitive available but flagged experimental | `automator-internal` | Outcome 2 row (current). | Outcome 2 plan. | Outcome 2 revisit. |
| Install-path priority — Claude Code plugin primitive deferred | `automator-internal` | Outcome 3 row (stale; not yet removed). | Outcome 3 plan. | Outcome 3 revisit. |
