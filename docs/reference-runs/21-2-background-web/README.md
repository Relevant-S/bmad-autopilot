# Reference Run 21-2 — Epic-21 Background-Execution Web Reference Run (daemon-backed dispatch + git-ground-truth-reconciled status + loud-fail marker)

Captured artifacts for the Epic-21 web reference run per Story 21.2 (`_bmad-output/implementation-artifacts/21-2-background-execution-implementation-or-named-fallback-per-story-21-1.md`) — the witness of the reduced **`partial`** surface the Story 21.1 spike selected (verdict `partially-stable` → path `partial`; `docs/research-spikes/2026-06-17-background-primitive-stability.md`). This directory parallels the Epic-20 per-run directory shape (`docs/reference-runs/20-4-web/`) — see `docs/reference-projects.md`'s web row (`Latest Run Record` pointer migrated here per Story 21.2 AC-8).

- **Reference project:** the established UI-bearing e-commerce cart/checkout synthetic surface (the same web surface the `20-4-web` / `19-6-web` runs exercised, reused per the AC-1 substitution posture inherited from Stories 9.6 / 10.7 / 13.7 / 19.6 / 20.4 — do not invent a new app).
- **Project type:** `web` (driver `playwright` per Story 4.4) — though the Story 21.2 surface is **project-type-agnostic** (background dispatch + status reconciliation are orchestrator/status concerns, not QA-driver concerns).
- **Net-new witness:** the three Story-21.2 `partial`-surface deliverables — (1) `background_execution`-gated dispatch via the **daemon-backed** primitive (`claude --bg`), (2) `/bmad-automation status` surfacing background runs **reconciled against git ground-truth**, (3) the loud-fail **`background-primitive-unstable`** marker on the unconfirmable-on-resume path.
- **Stand-in posture (READ THIS):** this is a **stand-in capture**, not a live-daemon round-trip. Per the 20.4 reference-run disclosure discipline, the *dispatch-seam construction + reconciliation classification + marker emission* are **genuinely witnessed** (by `tests/test_epic_21_background_reference_run_fixture.py`, driving the real `make_git_ground_truth_probe` against a real `tmp_path` git repo with injected loop/launcher stubs); a live `claude --bg` daemon round-trip is **NOT** witnessed (and is out of scope for a deterministic CI fixture). See `narrative.md` § Stand-in disclosure.
- **Terminal state:** N/A for the dispatch surface (background dispatch is non-blocking — the run loop runs in the detached child). The `background-primitive-unstable` marker is **story-level runtime evidence**: sensor-not-advisor, it never flips `ac_results` / wrapper `status` / run lifecycle state.

## Artifacts

| File | Description |
|---|---|
| [`run-output.txt`](run-output.txt) | `/bmad-automation run sample-bg-001` output with `background_execution: true` — the pre-flight background branch, the built `claude --bg` argv (NOT the in-session `Agent run_in_background` path), and the non-blocking confirmation; plus the `background_execution: false` contrast showing bit-identical foreground behavior. |
| [`status-output.txt`](status-output.txt) | `/bmad-automation status sample-bg-001 --background-agents-json …` output — the single-story inspection PLUS the net-new `## Background runs` section reconciling three background runs (in-flight / completed-confirmed / unconfirmable) with the greppable `background-primitive-unstable` marker on the unconfirmable run. |
| [`narrative.md`](narrative.md) | The full narrative: reference project, stand-in disclosure, the genuinely-witnessed background-dispatch + reconciliation behavior, the deferral + named revisit trigger, and the boundaries held. |

## Provenance / reproduction

The rendered outputs in `run-output.txt` / `status-output.txt` are produced by the Story 21.2 substrate (`tools/loud-fail-harness/src/loud_fail_harness/background_dispatch.py`): `build_background_dispatch_command` / `build_background_dispatch_confirmation` (dispatch) and `reconcile_background_runs` / `render_background_runs_section` (status). The behavior is exercised end-to-end by:

- `tests/test_epic_21_background_reference_run_fixture.py` — the reference fixture (real git repo, injected stubs).
- `tests/test_background_dispatch.py` — the unit corpus.
- `tests/test_status_command.py::test_main_background_agents_json_renders_section_with_marker` — the `/bmad-automation status --background-agents-json` CLI surface.
