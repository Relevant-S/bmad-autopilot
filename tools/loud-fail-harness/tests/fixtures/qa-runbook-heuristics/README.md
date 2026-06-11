# qa-runbook-heuristics fixtures (Story 19.1; FR-P2-5 / ADR-010)

Non-vacuous corpus for `qa_runbook_heuristics_validator`. Each invalid fixture
isolates EXACTLY ONE of the four AC-5 rejection classes so the test can assert
the *specific* finding, not merely a nonzero exit (Story 24.3 retro flagged
vacuous fixtures — avoid).

| Fixture | Intent | Expected |
|---|---|---|
| `valid/qa-runbook.yaml` | All three project types declared (web/api/mobile), mixed `enabled`/`disabled`, one per-AC `heuristic_opt_out`, plus an unrelated `masked_selectors` key the validator must ignore. | 0 findings (exit 0). |
| `invalid/unknown-heuristic-name.yaml` | AC-5(a): a heuristic name not in `FROZEN_HEURISTIC_NAMES` under `heuristics.web`. | finding at `/heuristics/web/<bogus>`; "unknown heuristic name". |
| `invalid/bad-enablement-value.yaml` | AC-5(b): an enablement value outside `{enabled, disabled}`. | finding at `/heuristics/api/empty-state`; "enablement value … not in {enabled, disabled}". |
| `invalid/unknown-project-type.yaml` | AC-5(c): a project-type key under `heuristics:` that is not web/api/mobile. | finding at `/heuristics/desktop`; "unknown project-type key". |
| `invalid/opt-out-unknown-name.yaml` | AC-5(d): a `heuristic_opt_out` entry not in `FROZEN_HEURISTIC_NAMES`. | finding at `/behavioral_plan_overrides/<story>/ac_1/heuristic_opt_out/0`; "not in FROZEN_HEURISTIC_NAMES". |

`FROZEN_HEURISTIC_NAMES` (the closed 7-set, ADR-010): `empty-state`,
`error-state`, `auth-boundary`, `rate-limit-boundary`, `locale-i18n-edge`,
`large-input-boundary`, `permission-boundary`.
