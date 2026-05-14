# LAD MCP Setup

Operator-facing setup guide for the LAD (LLM-Adversarial-Diff) MCP server the BMAD Agent Development Automator drives via the Review-LAD specialist on opt-in 4th-layer adversarial code-review (Phase 1.5 — ADR-008, see `_bmad-output/planning-artifacts/architecture.md` lines 661–734). The LAD MCP itself is `Shelpuk-AI-Technology-Consulting/lad_mcp_server` at version_floor `bb47e9e` (Apache-2.0 licensed; the upstream `code_review` MCP tool surface that runs two OpenRouter-backed reviewers in parallel).

If `/bmad-automation init` halted on `LAD-skipped` (sub_cause `init-api-key-missing` OR `init-mcp-unavailable`) and the verbatim diagnostic `"LAD MCP unavailable at init; 4th-layer review skipped."` (or the runtime variant `"LAD MCP unavailable mid-run; 4th-layer review skipped."`), follow this guide to install the LAD MCP, set the `OPENROUTER_API_KEY` env var, and re-run `init`.

## Prerequisites

The LAD MCP runs as a `uvx`-managed stdio process Claude Code launches on demand; it does NOT spawn a separate dev server. The operator-side prerequisites:

- **`uv` ≥ 0.4** (`uvx` is the `uv tool run` companion; bundled with uv). Check with `uv --version`. Install per [uv documentation](https://docs.astral.sh/uv/getting-started/installation/) if missing.
- **An OpenRouter account with credits.** The LAD MCP backs both reviewers through OpenRouter. Sign up at [openrouter.ai](https://openrouter.ai) and provision an API key. Credits must be available for at least one full review pass (typically $0.20–$0.80 per LAD invocation depending on diff size + the OpenRouter model pair's per-token pricing).
- **`OPENROUTER_API_KEY` env var set in your shell.** Per ADR-008's NAME-not-VALUE discipline (NFR-S1), the BMAD Automator reads only the env-var NAME via the substrate's wrapper-side presence check; the VALUE is consumed exclusively by the upstream `lad_mcp_server` process via the `claude mcp add ... -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY"` install handle. Do NOT commit the VALUE to any file; do NOT echo it into shell scripts; do NOT include it in `_bmad/automation/config.yaml` (the config carries only the NAME `api_key_env_var: OPENROUTER_API_KEY`).

## Install + connect

Install via the canonical Claude Code MCP-add command (per architecture.md line 674 / ADR-008 — verbatim):

```
claude mcp add --transport stdio lad -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" -- uvx --from git+https://github.com/Shelpuk-AI-Technology-Consulting/lad_mcp_server lad-mcp-server
```

This registers the LAD MCP with Claude Code over stdio (the default transport). The `-e OPENROUTER_API_KEY="$OPENROUTER_API_KEY"` flag passes the env var's VALUE through Claude Code to the spawned `lad-mcp-server` process at server-startup time (the shell expansion happens at the time of the `claude mcp add` invocation; the resulting Claude Code MCP registration carries the VALUE in Claude Code's internal MCP-server config — NEVER reproduce that file unsealed in version control). The `--from git+...` fragment pins to the upstream repo HEAD; `uvx` resolves a specific commit at first invocation and caches the resolved environment locally (architecture.md line 695 — "30–60s as `uvx` builds the tool environment" — is the documented cold-start cost; subsequent invocations reuse the cached environment and are structurally faster).

### Model-pair selection

ADR-008 documents the dual-reviewer pair defaults as `OPENROUTER_PRIMARY_REVIEWER_MODEL=moonshotai/kimi-k2-thinking` + `OPENROUTER_SECONDARY_REVIEWER_MODEL=minimax/minimax-m2.7`. Both are operator-tunable at runtime via env vars without schema bumps (the upstream `lad_mcp_server` reads them at server startup; pass them via additional `-e MODEL=...` flags on the `claude mcp add` line if you want non-default models). **These model identifiers reflect the upstream `lad_mcp_server` defaults at ADR-008 authorship time — check the upstream repo for the current defaults before assuming the model pair is stable across server versions.**

**Single-reviewer-mode escape (ADR-008 Consequence vii):** Set `OPENROUTER_SECONDARY_REVIEWER_MODEL=0` to disable the secondary reviewer, halving the per-pass cost AND the per-pass latency at the cost of losing the dual-reviewer parallelism that gives LAD its sycophancy-escape property. Use this only under explicit cost-envelope or rate-limit constraints.

The substrate's wrapper handles a *natural* single-reviewer-mode fallback automatically when the OpenRouter secondary reviewer times out (organic upstream flakiness). See Troubleshooting § `LAD-skipped: mid-run-mcp-unavailable` below for the signature.

### Verify the install

Confirm registration:

```
claude mcp list
```

Expected output line:

```
lad: uvx --from git+https://github.com/Shelpuk-AI-Technology-Consulting/lad_mcp_server lad-mcp-server - ✓ Connected
```

If the line shows `! Needs authentication`, the `OPENROUTER_API_KEY` value passed via `-e` was empty or invalid — re-export the env var with a valid value and re-run `claude mcp add` (the registration is idempotent; re-running replaces).

Optionally, invoke the no-side-effect smoke probe `mcp__lad__code_review` with a minimal-path fixture from a Claude Code session to verify the MCP-tool surface is reachable end-to-end. A clean tool-call return verifies the setup.

## Configure the Automator for LAD-enabled runs

Edit `_bmad/automation/config.yaml` (or run `/bmad-automation init` to scaffold it on a fresh project) and ensure the `review_lad` section reads:

```yaml
review_lad:
  enabled: true
  api_key_env_var: OPENROUTER_API_KEY
```

The `api_key_env_var` value carries the env-var NAME (default `OPENROUTER_API_KEY` per ADR-008 line 681; the Phase-1-era placeholder `LAD_API_KEY` is NOT an acceptable alias per ADR-008 Consequence 3 — verify the config file at run time matches the corrected name). The Automator's substrate reads only the NAME (NFR-S1); the upstream `lad_mcp_server` reads the VALUE at server startup time via the install handle's `-e OPENROUTER_API_KEY="$OPENROUTER_API_KEY"` flow.

## Re-run `bmad-automation init`

With the LAD MCP installed, the `OPENROUTER_API_KEY` env var set, and `_bmad/automation/config.yaml#review_lad.enabled: true`, re-run `/bmad-automation init` from the project root. The init flow's precondition substrate (Story 7.3's `run_init_preconditions` + Story 10.5's `lad_precondition_probe_factory`) re-probes the LAD MCP reachability + env-var-presence. On a clean probe-True return, the `LAD-skipped: init-api-key-missing` / `init-mcp-unavailable` emissions do NOT fire; init proceeds and `review_lad.enabled: true` is preserved in the rewritten config. The Automator is then ready to run LAD-enabled loops via `/bmad-automation run <story-id>`.

## Troubleshooting

### `LAD-skipped: init-api-key-missing` despite the install succeeding

Likely cause: the `OPENROUTER_API_KEY` env var is unset in the current shell (the `claude mcp add` ran in a prior shell session, then the env var was unset; OR the env var was set with a different NAME).

Fix:
1. `echo $OPENROUTER_API_KEY` — if blank, re-export with `export OPENROUTER_API_KEY="<your-key>"` from a startup file (e.g., `~/.zshenv` or `~/.bashrc`) so the var is set in every shell.
2. Confirm `_bmad/automation/config.yaml#review_lad.api_key_env_var` literally reads `OPENROUTER_API_KEY` (NOT the Phase-1-era placeholder `LAD_API_KEY`; per ADR-008 Consequence 3 no alias).
3. Re-run `/bmad-automation init`.

### `LAD-skipped: init-mcp-unavailable` despite the env var being set

Likely cause: the `lad` MCP server is not registered in this Claude Code installation, OR the registration failed health-check at probe time (uvx cold-start exceeded the probe timeout).

Fix:
1. `claude mcp list | grep lad` — if absent, re-run the install command from § Install + connect above.
2. If listed but health-check shows `✗ Failed to connect`, warm-start the uvx environment by invoking the install command standalone in a terminal (it pre-populates the uvx cache); the next `claude mcp list` should show `✓ Connected`.
3. Re-run `/bmad-automation init`.

### `LAD-skipped: mid-run-mcp-unavailable` mid-run despite init having succeeded

Likely cause: the LAD MCP became unavailable mid-run (typical: OpenRouter rate-limit hit; the `lad-mcp-server` process crashed and was not restarted; the secondary-reviewer model is temporarily unavailable at OpenRouter).

Distinguished sub-cases (per the captured `pr-bundle.md` loud-fail block — the diagnostic context names the sub-cause):
- **Secondary-reviewer timeout** — the substrate handled it cleanly via the ADR-008 single-reviewer-mode-fallback escape; the LAD layer completed with the primary reviewer's verdict and the marker did NOT fire. If you see no marker but the bundle's review section names "single-reviewer-mode synthesis", this is expected behavior.
- **Primary-reviewer timeout** — the substrate emits `LAD-skipped: mid-run-mcp-unavailable` because the dual-reviewer pass cannot synthesize without at least the primary verdict. Reduce diff size if possible; switch the primary model via `OPENROUTER_PRIMARY_REVIEWER_MODEL`; retry.
- **MCP process crash** — re-register via `claude mcp remove lad && claude mcp add ...` and retry.
- **Both reviewers unavailable** — typically OpenRouter outage; check [openrouter.ai/status](https://openrouter.ai/status); retry when upstream is healthy.

The Automator's mid-run handling is **graceful-degrade**: the orchestrator continues with the 3-layer review output, the `LAD-skipped` marker lands in the PR bundle's loud-fail block, and the merge-ready bundle is assembled minus the LAD layer's findings. This is the loud-fail doctrine in action — the failure is visible, not silently swallowed.

### LAD review takes longer than expected (NFR-P3 5-min budget exceeded)

Likely causes:
- **First LAD-enabled run on this machine** — uvx cold-start contributes 30–60s of one-time latency (per architecture.md line 695). Subsequent runs reuse the cached uvx environment.
- **OpenRouter secondary-reviewer timeout** — the OpenRouter request-timeout budget is 295s; if the secondary reviewer hangs, the wrapper waits the full budget before falling back to single-reviewer-mode synthesis. This pushes total LAD-pass latency up to ~5 minutes.
- **Large diff under review** — pass-time scales with diff size + the model pair's per-token throughput. Consider scoping the dispatch payload's `paths` array narrower at the orchestrator side (Phase-2 surface).

If the duration overage is structurally driven by upstream OpenRouter latency rather than substrate regression, this is the expected H3 housekeeping surface per Story 10.7 AC-7(c) — `deferred-work.md` should record the overage and the diagnosed component for Phase 2 NFR-P3-budget refinement.

## Cross-references

- `_bmad-output/planning-artifacts/architecture.md#ADR-008` (lines 661-734) — the load-bearing ADR for LAD MCP selection, env-var contract, dual-reviewer parallelism, install handle, and the dual-reviewer-fallback escape.
- `bmad-autopilot/agents/review-lad-wrapper.md` — the Phase 1.5 Review-LAD specialist (Story 10.2 + Story 10.5) that drives `mcp__lad__code_review` at LLM-runtime.
- `bmad-autopilot/schemas/dependencies.yaml` — the `lad` entry's `init.diagnostic_pointer` + `runtime.sub_classifications[].diagnostic_pointer` literals (the strings the orchestrator surfaces when a `LAD-skipped` marker fires).
- `bmad-autopilot/docs/mobile-mcp-setup.md` — Story 9.5's structural-template precedent (the same per-MCP operator-walkthrough shape applied to the mobile MCP).
- `bmad-autopilot/docs/reference-runs/10-7-lad-web/` — the Phase 1.5 LAD-enabled reference run record (Story 10.7) demonstrating an end-to-end happy path AND the natural OpenRouter-secondary-timeout fallback path.
