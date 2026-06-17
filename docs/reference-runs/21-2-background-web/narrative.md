# Epic-21 Background-Execution Web Reference Run — Narrative (Story 21.2)

This narrative documents the Epic-21 web reference run: the witness of the reduced **`partial`** surface for FR-P2-7 (background / fire-and-forget orchestrator execution) that Story 21.1's stability spike selected.

## What this run witnesses

The Story 21.1 spike (`docs/research-spikes/2026-06-17-background-primitive-stability.md`, Status: done) assessed Claude Code 2.1.179's daemon-backed background-session primitive and reached verdict **`partially-stable`** → recommended path **`partial`**. Story 21.2 implements that surface. This reference run witnesses its three user-visible deliverables:

1. **`background_execution`-gated dispatch via the daemon-backed primitive.** With `background_execution: true` in `_bmad/automation/config.yaml`, `/bmad-automation run <story-id>` does NOT run the inline six-step foreground loop; it builds a `claude --bg …` argv and dispatches the whole story loop as a detached, daemon-backed background session, returning a non-blocking confirmation (see `run-output.txt`). The dispatched child re-enters `/bmad-automation run <story-id> --foreground`; the `--foreground` re-entrancy sentinel forces the real foreground loop in the child so the detached session executes the story loop and does not recurse. With `background_execution: false` (the default), the path is **bit-identical** to the pre-Story-21.2 foreground loop.
2. **Git-ground-truth-reconciled `/bmad-automation status`.** `status --background-agents-json <file>` reads the captured `claude agents --json --all` output and cross-checks each background run against git ground-truth (per-story branch existence + landed commits), classifying each `in-flight` / `completed-confirmed` / `unconfirmable` and rendering a `## Background runs` section (see `status-output.txt`).
3. **The loud-fail `background-primitive-unstable` marker.** For every background run that **cannot be confirmed landed** on resume (the agents registry says completed but git shows no landed branch — the `#63023` / `#68117` silent-loss signatures), the status surface emits the greppable `background-primitive-unstable` marker. This inverts the primitive's silent cross-session-survival failure mode into a loud, greppable one (loud-fail doctrine).

## CRITICAL: the in-session `Agent run_in_background` path is NOT used

The dispatch uses ONLY the **daemon-backed** `claude --bg` / `claude agents` surface the spike verified functional at 2.1.179. It does **not** use the in-session `Agent run_in_background` subagent path — that is the `anthropics/claude-code#63023` silent-data-loss path (background agents terminated on session pause with no completion notification, uncommitted worktree work permanently lost) the spike rejected. The substrate module (`background_dispatch.py`) never references the Agent tool.

## Stand-in disclosure (per the 20.4 reference-run discipline)

This is a **stand-in capture**, NOT a live-daemon round-trip:

- **Genuinely witnessed** (by `tests/test_epic_21_background_reference_run_fixture.py` + `tests/test_background_dispatch.py`, deterministic CI): the dispatch-seam construction (`build_background_dispatch_command` produces a well-formed `claude --bg` argv; the inline foreground loop is NOT taken when background is on; the foreground path is bit-identical when background is off); the reconciliation classification driven through the **real** `make_git_ground_truth_probe` against a **real** `tmp_path` git repo (a landed per-story branch → `completed-confirmed`; an absent branch → `unconfirmable`); and the `background-primitive-unstable` marker emission firing **exactly** on the unconfirmable case (silent otherwise), validate-first against the registry (Pattern 5).
- **NOT witnessed:** a live `claude --bg` daemon round-trip (dispatch → detached execution → cross-session resume → surface). The launcher and the `claude agents --json` registry are **injected seams** in the fixture (the launcher records the argv; the agents-json is synthetic data) — exactly how Story 18.4 witnesses parallel concurrency via injected runners rather than real Claude Code sessions. A live daemon round-trip is non-deterministic and out of scope for a CI fixture.

The rendered `run-output.txt` / `status-output.txt` excerpts are produced by the real Story-21.2 substrate functions over representative inputs.

## Deferral + named revisit trigger (Story 21.2 AC-7)

This story does **not** promise the unqualified "close the session and forget it; results always surface" guarantee. That sub-capability depends on `#63023`'s proposed `session_pause` checkpoint hook (does not yet exist) and the resolution of the cross-session-survival churn. Because the spike verdict is `partially-stable` (not `unstable`), **no `deferred-work.md` ledger entry is opened**: the deferred sub-capability + its named revisit trigger live in the spike artifact (`## Forward consumers` → "FR-P2-7 Phase-3 revisit") and the `docs/extension-audit.md` background-primitive row's revisit condition.

**Named revisit trigger:** when `anthropics/claude-code#63023` closes with a session-pause checkpoint / persistence guarantee, OR Claude Code publishes a stability statement for the `claude agents` / `--bg` / FleetView primitive, OR ≥2 consecutive Claude Code minor releases ship with no background-session cross-session-survival regression fix. At that point the verdict re-audits toward `stable` and the path toward full `implement`.

## Boundaries held (Story 21.2 AC-9)

- FOUR specialists / THREE hooks / FIVE substrate components — UNCHANGED. `background_dispatch.py` is a new harness **module**, not a sixth substrate component, not a specialist, not a hook.
- NO `schemas/envelope.schema.yaml` change; NO new envelope field. NO `schemas/orchestrator-event.yaml` change — `background-primitive-unstable` is an enumeration-check-tolerated **orphan** class (no orchestrator-event counterpart), exactly like the QA-evidence markers `flakiness-threshold-exceeded` / `a11y-*` / `visual-regression-*` (co-versioned ≠ co-bumped).
- `dependencies.yaml` MINOR bump (`1.7` → `1.8`) for the `background-primitive` opt-in-skip entry; `marker-taxonomy.yaml` PATCH bump (`1.17` → `1.18`, closed-set 41 → 42).
- **Sensor-not-advisor:** the marker is runtime evidence — it surfaces, it NEVER flips `ac_results`, the wrapper `status`, or the run lifecycle state.
- **Read-only status (NFR-O4):** the reconciliation reads `claude agents --json` (injected) + git (read-only `rev-parse` / `rev-list`); it does NOT mutate run-state contents — the marker is a discovery-surface emission (the Story 8.5 `orphan-run-state-detected` pattern), not a run-state write.
- **Pluggability gate green:** the new module lives in the harness; it imports nothing across the runtime↔harness boundary.
