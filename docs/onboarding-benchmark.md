# Onboarding Benchmark (NFR-P3 / FR44)

Authoritative landing: Story 7.9 (5-min first-loop target validation + benchmark artifact). Substrate references: FR44 (`prd.md:869` — first-run loop ≤ 5 minutes on a typical developer laptop), NFR-P3 (`prd.md:936` — ≤ 5 minutes from `init` completion to first successful sample-story loop merge-ready), Pattern 5 (loud-fail / named-invariant exit-code dispatch), Pattern 6 (strict-typed substrate library + dependency injection), Pattern 7 (story-doc adherence).

This artifact is the canonical longitudinal record of the Automator's first-loop performance against NFR-P3's published 5-minute commitment. Each release adds ONE row capturing date, version, environment notes (Claude Code version, OS, hardware tier, Python), the seven-component timing breakdown, the end-to-end total, the target-met verdict, and (on missed-target rows) the diagnosed missed component plus a remediation or deferral note. Rows are append-only between the `<!-- benchmark-rows:begin -->` / `<!-- benchmark-rows:end -->` anchor markers — a new row is inserted IMMEDIATELY before the end marker; existing rows are NEVER reordered. The append-only discipline mirrors `docs/marker-coverage-audit.md` (Story 6.3) and the per-convention table at `docs/extension-audit.md` (Story 1.11).

Cross-reference: `docs/extension-audit.md` § Contributor-discipline notes carries the per-release-update discipline (every release adds a row; missed-target releases include remediation note OR deferral entry pointing at the follow-up issue) AND the regeneration command. The benchmark fixture is Story 7.4's canonical `_data/sample-auto-001.md` (loaded via `loud_fail_harness.sample_story_scaffold.load_sample_story_content`).

## Methodology

### Seven-component breakdown

Aggregate-only timings are REJECTED as deliverables (AC-2 verbatim). Per-component breakdown lets release managers diagnose missed targets to the SPECIFIC component that blew the budget rather than triaging the entire 5-minute path. The component fields below mirror Story 6.4's per-specialist × per-retry cost-telemetry partitioning.

- `install_seconds` — Story 7.2 install (git-clone-symlink OR plugin install).
- `init_precondition_check_seconds` — Story 7.3 `run_init_preconditions`.
- `init_scaffold_seconds` — Story 7.4 `scaffold_sample_story` (proceed-fresh branch).
- `init_stub_generation_seconds` — Story 7.5 `scaffold_config_qa_runbook_stubs` + Story 7.8 `emit_orientation_if_first_run` aggregated (`init.md` step 4 + step 5).
- `first_specialist_dispatch_seconds` — orchestrator startup + Dev dispatch latency.
- `dev_runtime_seconds` / `review_bmad_runtime_seconds` / `qa_runtime_seconds` — per-specialist seam-to-seam totals.
- `bundle_assembly_seconds` — Story 2.11 + Story 6.1 bundle-assembler runtime (final seam from QA-done to merge-ready PR-bundle persistence).

### Environment-notes columns

Environment variability is CAPTURED in the artifact rather than silently normalised. Hardware-tier is the only column requiring explicit caller declaration (CLI `--hardware-tier`); the rest are auto-probed at run-time.

- `Claude Code Version` — `claude --version` capture (Story 7.3 `_probe_claude_code_version` precedent).
- `OS` — `platform.system().lower() + '-' + platform.release()`.
- `Hardware Tier` — coarse human-judgment label: `developer-laptop`, `ci-runner-standard`, `ci-runner-large`, `other`.
- `Python` — `platform.python_version()`.

### Missed-target diagnostic

On rows where `Target Met` is ❌, the `Missed Component` column names the field with the largest contribution to the overage (argmax over the seven measured components). When the argmax-component is itself within its historical-mean budget (death-by-a-thousand-cuts), the field name is suffixed with `+aggregate-overage` so the release manager sees that no single phase is the culprit. The `Notes` column carries either a one-line remediation summary OR a deferral entry pointing at the follow-up issue per AC-4 verbatim.

Comparative-analysis use-case: read each row in chronological order (rows are append-only) and observe per-component trends. The most-likely-to-drift columns are the per-specialist runtimes (`Dev`, `Review-BMAD`, `QA`, `Bundle`) — specialist-runtime drift is the expected source of Phase-2 onboarding-time regressions, ahead of install or init.

## Per-release rows

| Date | Version | Claude Code Version | OS | Hardware Tier | Python | Install | Init: Precond | Init: Scaffold | Init: Stub-gen | First Dispatch | Dev | Review-BMAD | QA | Bundle | Total | Target Met | Missed Component | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
<!-- benchmark-rows:begin -->
<!-- benchmark-rows:end -->

## Regeneration

Append a new row when: (a) a new Automator release lands (per-release-row discipline); (b) a missed-target re-investigation produces an updated remediation note; (c) the environment baseline shifts (e.g., a new Claude Code MAJOR bump invalidates prior-row comparability). The fixture-equivalence reproducibility contract (AC-5) means modifications to `_data/sample-auto-001.md` invalidate prior-row comparability — fixture changes require explicit versioning of the fixture and a notes-column annotation on the first post-bump row.

```
cd bmad-autopilot/tools/loud-fail-harness
uv run onboarding-benchmark --hardware-tier <tier> --version <release>
```

The `onboarding-benchmark` entry point is library-as-CLI-aid invoked from `.github/workflows/release-benchmark.yml` once per release (release branches and tags ONLY — NOT per PR per AC-5's release-cadence cost-vs-coverage tradeoff). Mirrors `marker-coverage-audit`'s posture per `pyproject.toml` lines 70-74.

## Cross-references

- [`docs/mvp-completion-evidence.md`](mvp-completion-evidence.md) (Story 8.7) — the per-FR/NFR coverage matrix at the MVP cut. THIS benchmark and the MVP completion evidence are complementary per `epics.md:3437-3438` verbatim ("complementary (onboarding-time benchmark covers NFR-P3 longitudinally; MVP completion evidence covers all FRs/NFRs once at MVP close)"). The seed row in the per-release table above IS the evidence link cited by `NFR-P3`'s row in `docs/mvp-completion-evidence.md` — the cross-reference is bidirectional.
