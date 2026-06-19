# Story 22.7 — Auto-Merge draft→ready Round-Trip: Reference-Run Narrative

## Why this surface needs a real remote (it is unlike every prior reference run)

Every Phase-1 / Phase-1.5 / Phase-2 reference run before this one was witnessed against the in-repo synthetic `sample-auto-001` surface (or the development workspace itself), because every prior specialist/evaluator is **sensor-not-advisor** — it returns a structured observation that can be exercised deterministically in `tmp_path`. Auto-merge (Epic 17) is the system's **first actuator** and **first remote-mutating surface**: its terminal act is `gh pr merge`, a GitHub-side mutation. There is no honest way to witness "a commit actually landed on `main`" without a real `gh`-authenticated remote and a real PR. Epic 17 shipped with that witness existing **only** through the injected `_GhRunner` / a fixture transcript — never against a real remote (`epic-17-retro-2026-06-18.md` § Significant Discovery).

Worse, there was a **structural** reason an armed auto-merge could never land on a real project: Phase-1 leaves PRs in **draft** pending human approval, and `gh pr merge` on a draft PR exits non-zero → the actuator classifies it `auto-merge-skipped: merge-failed`. So on a real project an armed auto-merge would attempt and **always skip** — safe (loud-fail, never silent) but end-to-end unproven. Story 22.7 closes that gap by inserting the ratified `gh pr ready <branch>` draft→ready transition BEFORE the merge.

## What this run witnesses

1. **The genuine `gh pr ready` → `gh pr merge --squash` round-trip (AC-7).** `capture-real-round-trip.sh` creates a throwaway repo, opens a real **draft** PR (captured pre-state: `isDraft: true`), runs `gh pr ready <branch>` (post-state: `isDraft: false`), then `gh pr merge --squash <branch>`, and shows the resulting **real squashed commit on `main`**. These are the EXACT two `gh` invocations `attempt_auto_merge` issues, in the same order, on the same explicit per-story branch — the live witness Epic 17's injected-runner transcript could not provide.

2. **The readiness step is loud-fail (AC-2).** A `gh pr ready` non-zero exit (or absent `gh` / timeout / missing `repo_root`) returns `auto-merge-skipped: ready-failed` and the merge is **NOT** attempted afterward — never a silent drop, never a misleading `merge-failed` stacked on top of the real readiness cause. The `gh` exit code + stderr ride along verbatim in `gh_detail`. (Witnessed deterministically by `test_ready_*` + `test_main_enabled_green_done_ready_fails_emits_skip_no_merge`.)

## Exact actuator-call correspondence

| Actuator (`auto_merge_execution.py`) | Capture script (`capture-real-round-trip.sh`) |
|---|---|
| `_attempt_pr_ready` → `_invoke_gh(["pr","ready",branch], …)` | `gh pr ready "${BRANCH}"` |
| `attempt_auto_merge` → `_invoke_gh(["pr","merge","--squash",branch], …)` | `gh pr merge --squash "${BRANCH}"` |

Both run through the frozen `_GhRunner` DI seam in production (`capture_output=True`, `text=True`, `check=False`, `timeout`, `stdin=DEVNULL`, never raises on non-zero). The script invokes the same `gh` subcommands directly so the captured transcript IS the production command surface.

## Stand-in disclosure (per the 20.4 / 21.2 reference-run discipline)

- **Genuinely witnessed (live, against a real remote):** the `gh pr ready` → `gh pr merge --squash` round-trip landing a real commit on `main`. This is the AC-7-mandated portion and it is NOT a stand-in.
- **Staged (unit-tested, not re-driven live):** the orchestrator-domain arming *decision* — the `auto_merge.enabled` AND gate-green AND `current_state == "done"` conjunction in `bundle_assembly.main()` that gates whether the actuator is reached. That logic is exhaustively pinned by `tests/test_auto_merge_execution.py` (`test_main_enabled_green_done_*`, `test_main_disabled_default_no_merge_no_marker`, `test_main_not_merge_ready_no_merge`, `test_main_enabled_gate_not_met_done_emits_skip_gate_not_met`) and is sensor-free of the live `gh` round-trip. The live witness is deliberately scoped to the actuator's two `gh` calls — exactly the seam the injected-runner transcript could not prove.

Per AC-7, the genuinely-witnessed portion **includes the real `gh pr ready` + `gh pr merge` round-trip landing a commit**, not merely the injected-runner seam. Until `run-output.txt` (the maintainer-executed transcript) is committed, this record's genuine portion is **pending** and Epic 23 must not harvest it as the witness.

## Taxonomy: the `ready-failed` sub-classification

Story 22.7 adds `ready-failed` as a sub-classification under the **existing** `auto-merge-skipped` class (`schemas/marker-taxonomy.yaml`), a PATCH bump `1.20 → 1.21` (the 44-class top-level closed-set is preserved — no new top-level class). It names the **readiness step** as the failure site so the human's remediation is honest (check draft-PR permissions / plan tier / branch state), distinct from a merge-step `merge-failed`. The PATCH classification follows the file's own documented bump rule ("adding a sub_classification under an existing class") and the 7.3 / 9.5 / 13.6 precedent; the file rule supersedes the epics-phase-2.md:981 parenthetical "MINOR" wording exactly as the 17.2/17.3 entries record for the inverse case. (Maintainer-ratified disposition recorded in the story's Dev Agent Record.)

## Boundaries held (AC-4 / AC-6)

- **No-push / git-scope invariant.** `gh pr ready` and `gh pr merge` are GitHub-side PR mutations (`markPullRequestReadyForReview` / squash-merge) on the branch's own PR — NO `git push` of the merge, no `--force`, no `--rebase`, no `--delete-branch`, no branch ops outside the named per-story branch, and `main`/trunk is never a direct write target (NFR-S3 / NFR-R3). `branch_lifecycle.py` is untouched.
- **Closed-set boundaries.** 4 specialists / 3 hooks / 5 substrate components held; no 4th hook; the actuator still runs inside `bundle_assembly.main()`; the closed-set top-level marker-class count stays 44.
- **`enabled: false` (shipped default) stays completely silent.** No readiness transition, no merge attempt, no marker — bit-identical to today's default install (pinned by `test_main_disabled_default_no_merge_no_marker`).
- **Sensor-not-advisor.** The marker is INFORMATIONAL — emitting it does not flip a wrapper status, change `current_state` (the story is already `done`), or itself retry.

## Forward consumer

Story 23.2 (`phase-2-completion-evidence.md`, the Phase-2 reference-project run records) — which must read the **committed `run-output.txt`** (the genuine landed-commit transcript), NOT the injected-runner seam, as the Phase-2 auto-merge completion witness.
