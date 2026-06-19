# Reference Run 22-7 — Auto-Merge draft→ready Round-Trip Web Reference Run (the FIRST genuine landed-commit witness)

Captured artifacts for the Story 22.7 auto-merge reference run (`_bmad-output/implementation-artifacts/22-7-auto-merge-draft-to-ready-handling-epic-17-retro-action-1.md`) — the witness AC-7 requires: an armed `enabled AND gate-green AND done` conjunction landing a **real squashed commit on `main`** via `gh pr ready <branch>` → `gh pr merge --squash <branch>`, the precondition for an honest Epic 23 Phase-2 auto-merge completion claim. This directory parallels the established per-run directory shape (`docs/reference-runs/21-2-background-web/`) — see `docs/reference-projects.md`'s web row (`Latest Run Record` pointer migrated here per Story 22.7 AC-7).

- **Reference project:** a throwaway GitHub repo created per capture (the auto-merge witness is a *remote-mutation* surface — unlike every prior reference run, it cannot be witnessed against the in-repo synthetic surface; it needs a real `gh`-authenticated remote with a real draft PR to mark ready and merge).
- **Project type:** `web` (the auto-merge surface is **project-type-agnostic** — `gh pr ready`/`gh pr merge` are orchestrator-domain GitHub-side operations, not QA-driver concerns; the `web` row simply carries the latest Phase-2 reference pointer).
- **Net-new witness:** the Story 22.7 readiness mechanism — `gh pr ready` fired BEFORE `gh pr merge --squash` on the per-story branch, turning a Phase-1 **draft** PR into a mergeable one so the actuator actually lands a commit instead of always skipping with `auto-merge-skipped: merge-failed`.
- **Stand-in posture (READ THIS):** per the 20.4 / 21.2 reference-run disclosure discipline, this record separates two portions:
  - **Genuinely witnessed (the AC-7 requirement):** the real `gh pr ready` → `gh pr merge --squash` round-trip against a real remote, landing a real commit on `main` — captured verbatim in `run-output.txt` by `capture-real-round-trip.sh`, which runs the EXACT two `gh` invocations `attempt_auto_merge` issues, in order, on the explicit per-story branch.
  - **Staged (unit-tested, not re-witnessed live):** the orchestrator-domain *arming decision* (`auto_merge.enabled` AND gate-green AND `current_state == "done"`) that gates whether the actuator is reached. That conjunction is exhaustively pinned by `tests/test_auto_merge_execution.py` (`test_main_enabled_green_done_*`) and is NOT re-driven through `bundle_assembly.main()` against the live remote here — the live witness is scoped to the actuator's two `gh` calls, which is precisely what Epic 17's injected-runner transcript could not prove.
- **Execution status:** `run-output.txt` is **maintainer-executed** (Project-Lead decision 2026-06-19 — the maintainer runs `capture-real-round-trip.sh` against their own `gh` account and commits the verbatim output). Until that transcript is committed, **Epic 23 must NOT harvest this as the genuine witness** (AC-7 is explicit: injected-runner-only is rejected). The script + this record are the committed, reproducible scaffold; the genuine landed-commit transcript is the one remaining maintainer step.

## Artifacts

| File | Description |
|---|---|
| [`capture-real-round-trip.sh`](capture-real-round-trip.sh) | The runnable, self-contained capture script. Creates a throwaway repo, opens a real **draft** PR, runs `gh pr ready <branch>` then `gh pr merge --squash <branch>` (the actuator's exact two calls, same order, explicit branch), captures the pre-draft / post-ready / post-merge PR state + the landed `main` commit, and tears the repo down. Run `./capture-real-round-trip.sh 2>&1 \| tee run-output.txt`. |
| `run-output.txt` | The verbatim capture of the genuine round-trip (produced by the script). **Maintainer-executed — pending commit; see Execution status above.** |
| [`narrative.md`](narrative.md) | The full narrative: why this surface needs a real remote, the genuinely-witnessed vs staged split, the exact actuator-call correspondence, the taxonomy `ready-failed` sub-classification, and the boundaries held. |

## Provenance / reproduction

The two `gh` invocations captured by `capture-real-round-trip.sh` are byte-for-byte the ones the Story 22.7 actuator issues — `auto_merge_execution.py` `attempt_auto_merge` runs `["pr", "ready", <branch>]` (via `_attempt_pr_ready`) then `["pr", "merge", "--squash", <branch>]`, both through the frozen `_GhRunner` DI seam (Pattern 6). The behavior is exercised deterministically in CI by:

- `tests/test_auto_merge_execution.py::test_success_returns_merged_and_runs_ready_then_squash_on_branch` — the unit witness of the two-call `[pr ready] [pr merge --squash]` argv sequence on the happy path.
- `tests/test_auto_merge_execution.py::test_main_enabled_green_done_merges_no_skip_marker` — the end-to-end `bundle_assembly.main()` witness (injected runner) of the armed conjunction firing the two-call sequence with NO skip marker.
- `tests/test_auto_merge_execution.py::test_main_enabled_green_done_ready_fails_emits_skip_no_merge` — the loud-fail witness: a `gh pr ready` failure surfaces `auto-merge-skipped: ready-failed` and the merge is NOT attempted.
