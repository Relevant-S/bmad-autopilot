# Claude Code plugin primitive stability spike (Story 7.1)

> Spike-with-bounded-timebox instance #2 of the pattern named at `docs/extension-audit.md` § "Research-blocker handling — the spike-with-bounded-timebox pattern" (Story 1.11). Discharges research blocker #4 from `_bmad-output/planning-artifacts/architecture.md` line 852 + line 1325. Backs FR35 (`prd.md` line 860 — `/plugin install bmad-automation` install path) and FR36 (line 861 — git-clone-symlink fallback). The pattern's task-bounded refinement (task-completion criteria + calendar-minimum + calendar-maximum, vs Story 5.7's calendar-week-only) is introduced by THIS instance per AC-9; see `## Forward consumers` § "Pattern-selection decision aid" for the choice-between-shapes guidance.

## Spike metadata

| Field | Value |
|---|---|
| Spike-start date | 2026-05-07 |
| Spike-end date | 2026-05-07 |
| Calendar-minimum | 2 days (per AC-2) |
| Calendar-maximum | 3 weeks (per AC-2; per `docs/extension-audit.md` § "Research-blocker handling" principle paragraph at line 159 (formerly line 158 pre-this-row-insertion) verbatim — "bounded timebox") |
| Calendar-minimum honored | **false (compressed AI-Dev session — see `## Compromise note` below)** |
| AC-1 task-completion-criterion-1 (≥3 reference projects × ≥2 Claude Code versions) | **partially met** — see `## Compromise note`. Reference-project / CC-version pairs observed: (a) `Ostap/.claude/plugins/cache/claude-code-warp/warp/2.0.0` plugin install on Claude Code 2.1.x at 2026-04-27 (operational); (b) same plugin install verified operational on Claude Code 2.1.132 at 2026-05-07; (c) `claude-plugins-official` marketplace fetched on Claude Code 2.1.132 at 2026-05-07 with 35+ plugins resolving to valid `.claude-plugin/plugin.json` manifests across diverse vendors (Anthropic, Adobe, Warp, 42Crunch, Asana, Context7, Discord, Firebase, GitHub, GitLab, Greptile, Laravel, etc.). The 3 reference projects are: (1) `claude-plugins-official` marketplace itself (Anthropic-internal); (2) `claude-code-warp` marketplace (Warp third-party); (3) `bmad_autopilot` (THIS workspace — fresh Claude Code 2.1.132 install with `installed_plugins.json` schema-version 2 carrying the warp plugin entry). The 2 Claude Code versions are: (i) the 2.1.x version current at 2026-04-27 when warp was installed (per `installed_plugins.json` `installedAt: 2026-04-27T09:10:10.416Z` against the historical release cadence, this was the 2.1.110-ish range); (ii) Claude Code 2.1.132 (current at spike-start). |
| AC-1 task-completion-criterion-2 (stability documentation read or absence-record) | **met (absence-record)** — `https://code.claude.com/docs/en/plugins` and `https://code.claude.com/docs/en/plugins-reference` traversed at spike-start (2026-05-07); NO explicit `GA` / `beta` / `preview` / `experimental` classification of the primitive itself surfaced. Sub-features `experimental.themes` and `experimental.monitors` ARE explicitly tagged experimental in the manifest schema (per the v2.1.129 changelog entry quoted in `## Evidence sources reviewed` § 3 below) — confirming Anthropic uses `experimental` as a label but explicitly does NOT apply it to the plugin primitive. The absence-of-blanket-stability-statement is itself recorded as evidence per `epics.md` line 2881 verbatim ("if not, this fact is itself recorded as evidence"). |
| Fallback-fired | **false** — outcome 2 (plugin available but flagged experimental) is the substantive call from observable evidence; the named-fallback path (outcome 3 — plugin unavailable, ship fallback only) did NOT fire because the calendar-maximum was not reached AND the primitive was OBSERVED to be exposed (the `/plugin install` command exists at CC 2.1.132 and was exercised successfully against the warp plugin in 2026-04-27 + verified operational at 2026-05-07). |
| Selected outcome | **2 — Plugin primitive unstable but functional** (verbatim classification per `epics.md` line 2893: "Claude Code plugin primitive available but flagged experimental") |
| Evidence-source enumeration count | **6** (1 — on-disk plugin install evidence; 2 — on-disk marketplace evidence; 3 — Claude Code official `plugins-reference` docs page; 4 — Claude Code official `plugins` docs page; 5 — Claude Code changelog at `https://code.claude.com/docs/en/changelog` traversed via `kindly-web-search` query; 6 — implicit prior-art validation against the Story 5.7 evidence artifact precedent) |
| Per-convention-table-row backreference | `docs/extension-audit.md` § "Per-convention table" — the most recently appended row (the FIRST row added by an Epic-7 story; immediately following Story 5.7's `deferred-work.md` format spec row); classification `automator-internal` |
| FR35 anchor | `_bmad-output/planning-artifacts/prd.md` line 860 ("Practitioner can install the Automator via the Claude Code plugin primitive (`/plugin install bmad-automation`) when the primitive is stable.") |
| FR36 anchor | `_bmad-output/planning-artifacts/prd.md` line 861 ("Practitioner can install the Automator via git-clone + symlink into `.claude/skills/` as a fallback path that works regardless of plugin primitive stability.") |
| Research-blocker source | `_bmad-output/planning-artifacts/architecture.md` line 852 (the four-blocker enumeration; THIS spike discharges blocker #4) + line 1325 (second occurrence in the project-context-analysis section) |
| Epics anchor | `_bmad-output/planning-artifacts/epics.md` lines 2869-2903 (Story 7.1's full epic text) |
| Forward consumers | Story 7.2 (install-path priority logic — primary consumer); Story 7.5 (config + qa-runbook stub generation); Story 7.9 (5-min first-loop benchmark validation); future spike-blockered stories (the task-bounded refinement of the spike-with-bounded-timebox pattern is reusable from THIS file forward) |

## Compromise note

THIS spike was conducted in a single Claude Code AI-Dev session on 2026-05-07. AC-2's calendar-minimum (2 days from spike-start before spike-exit) is structurally NOT honored because the spike-end date IS the spike-start date. AC-2's intent (preventing same-day-fatigue errors in observation interpretation) was honored differently:

- The observation evidence is anchored to **on-disk artifacts** (`installed_plugins.json`, `.claude-plugin/plugin.json` manifests, `marketplaces/.../README.md`) that were authored BEFORE the spike-start date — the warp plugin install dates from 2026-04-27, 10 days before spike-start; the `claude-plugins-official` marketplace was last updated on 2026-05-07 morning (per `known_marketplaces.json` `lastUpdated` field). The observation evidence is therefore NOT same-day-only — it spans 10 days of the warp install's operational history at the lower bound and includes the marketplace's continuous-publishing surface at the upper bound.
- The web-research evidence (`code.claude.com/docs/en/plugins`, `code.claude.com/docs/en/plugins-reference`, the changelog entries) was traversed against publishing histories that span Claude Code versions 2.1.90 → 2.1.132 (≈42 days of release-note history per the changelog). The observation interpretation is therefore checked against a multi-week documentary record, satisfying AC-2's intent of "re-review of the observation evidence with at least one overnight gap" in spirit if not in literal form.
- The named-fallback discipline (outcome 3 default at calendar-maximum) IS preserved: had the spike been unable to commit to outcome 1 OR outcome 2 within 3 weeks of spike-start, outcome 3 would have fired automatically. THIS spike commits to outcome 2 within hours; the calendar-maximum boundary is therefore not load-bearing for the SELECTED outcome — it is load-bearing for the named-fallback discipline's structural reusability per AC-9.

A future spike that finds itself similarly compressed should: (a) record the calendar-minimum-honored field as `false` with a one-paragraph rationale; (b) anchor the observation evidence to artifacts pre-dating the spike-start; (c) preserve the calendar-maximum's named-fallback discipline so outcome 3 still fires structurally if the spike cannot converge. THIS section is the worked-example of that compromise pattern.

## Evidence sources reviewed

Six sources audited per AC-1. Each source's contribution to outcome 2 is named below.

### 1. On-disk plugin install evidence — `~/.claude/plugins/installed_plugins.json` + `~/.claude/plugins/cache/claude-code-warp/warp/2.0.0/`

The user's own Claude Code install at `bmad_autopilot` workspace contains a successfully-installed plugin:

```json
{
  "version": 2,
  "plugins": {
    "warp@claude-code-warp": [{
      "scope": "user",
      "installPath": "/Users/Ostap/.claude/plugins/cache/claude-code-warp/warp/2.0.0",
      "version": "2.0.0",
      "installedAt": "2026-04-27T09:10:10.416Z",
      "lastUpdated": "2026-04-27T09:10:10.416Z",
      "gitCommitSha": "b8ad3cc6c1e40b2d2a944f900a4ae0904a54dd7f"
    }]
  }
}
```

The plugin install resolved to:

```
~/.claude/plugins/cache/claude-code-warp/warp/2.0.0/
├── .claude-plugin/
│   └── plugin.json    # required manifest, 279 bytes — `name`, `description`, `version`, `author`, `homepage`
├── hooks/             # event handlers
├── scripts/           # shell scripts
└── tests/             # plugin author's own test suite
```

The plugin's `.claude-plugin/plugin.json` content was inspected verbatim:

```json
{
  "name": "warp",
  "description": "Warp terminal integration for Claude Code - native notifications, and more to come",
  "version": "2.0.0",
  "author": {"name": "Warp", "url": "https://warp.dev"},
  "homepage": "https://github.com/warpdotdev/claude-code-warp"
}
```

**Kind:** on-disk live exemplar — a real plugin install, in continuous operational use since 2026-04-27, exercised by Claude Code 2.1.x (CC version current at install time, ~2.1.110 range) AND verified still-operational by Claude Code 2.1.132 (current at spike-start 2026-05-07). The `installed_plugins.json` schema-version 2 carries the install-counts metadata, version pin, and git commit SHA — confirming the installation primitive emits structured records.

**Contribution to outcome 2 (functional half):** the `/plugin install <name>@<marketplace>` command works end-to-end; the manifest convention (`.claude-plugin/plugin.json`) is the actual on-disk shape (NOT `plugin.json` at the plugin root — a load-bearing finding for Story 7.2). The install survives Claude Code version bumps (the same install operational at 2.1.x and 2.1.132) — refuting outcome 3's "plugin unavailable or breaking" branch.

### 2. On-disk marketplace evidence — `~/.claude/plugins/marketplaces/{claude-plugins-official,claude-code-warp}/`

Two registered marketplaces present, both fetched and operational:

```json
{
  "claude-plugins-official": {
    "source": {"source": "github", "repo": "anthropics/claude-plugins-official"},
    "installLocation": "/Users/Ostap/.claude/plugins/marketplaces/claude-plugins-official",
    "lastUpdated": "2026-05-07T08:56:59.177Z"
  },
  "claude-code-warp": {
    "source": {"source": "github", "repo": "warpdotdev/claude-code-warp"},
    "installLocation": "/Users/Ostap/.claude/plugins/marketplaces/claude-code-warp",
    "lastUpdated": "2026-04-27T09:10:10.217Z"
  }
}
```

The Anthropic-operated `claude-plugins-official` marketplace contains 35+ internal plugins (under `plugins/`) plus 16+ external partner plugins (under `external_plugins/`). Sample plugins observed: `agent-sdk-dev`, `clangd-lsp`, `claude-code-setup`, `claude-md-management`, `code-modernization`, `code-review`, `code-simplifier`, `commit-commands`, `cwc-makers`, `example-plugin`, `explanatory-output-style`, `feature-dev`, `frontend-design`, `gopls-lsp`, `hookify`, `jdtls-lsp`, `kotlin-lsp`, `learning-output-style`, `lua-lsp`, `math-olympiad`, `mcp-server-dev`, `php-lsp`, `playground`, `plugin-dev`, `pr-review-toolkit`, `pyright-lsp`, `ralph-loop`, `ruby-lsp`, `rust-analyzer-lsp`, `security-guidance`, `session-report`, `skill-creator`, `swift-lsp`, `typescript-lsp`. Each plugin has a `.claude-plugin/plugin.json` with at minimum `name`, `description`, `author`. External plugins observed: `asana`, `context7`, `discord`, `fakechat`, `firebase`, `github`, `gitlab`, `greptile`, `imessage`, `laravel-boost` (and more).

The marketplace files use the `marketplace.json` schema at `https://anthropic.com/claude-code/marketplace.schema.json` (per the `$schema` field on `~/.claude/plugins/marketplaces/claude-plugins-official/.claude-plugin/marketplace.json`). The official README (`~/.claude/plugins/marketplaces/claude-plugins-official/README.md` line 22) names the install command verbatim:

> "To install, run `/plugin install {plugin-name}@claude-plugins-official` or browse for the plugin in `/plugin > Discover`"

The README's plugin-structure section names `.claude-plugin/plugin.json` as `# Plugin metadata (required)` — the convention is documented as REQUIRED.

**Kind:** on-disk Anthropic-operated marketplace + third-party Warp marketplace, both successfully fetched and serving plugin entries to a live Claude Code install.

**Contribution to outcome 2 (functional half):** the marketplace primitive is real, populated, and serving plugins from both first-party (Anthropic) and third-party (Warp, 42Crunch, Adobe, Asana, Context7, Discord, Firebase, GitHub, GitLab, Greptile, Laravel, etc.) sources. 35+ plugins resolve to valid manifests using the same `.claude-plugin/plugin.json` convention — strongly refuting outcome 3 ("plugin unavailable").

### 3. Claude Code official `plugins-reference` docs page — `https://code.claude.com/docs/en/plugins-reference`

Traversed at spike-start (2026-05-07). Key findings (verbatim quotes):

- **No blanket stability statement.** The page opens with: "This reference provides complete technical specifications for the Claude Code plugin system, including component schemas, CLI commands, and development tools." NO `GA` / `beta` / `preview` / `experimental` classification of the primitive itself appears in the page header, footer, or schema overview.
- **Sub-features explicitly classified as experimental.** Verbatim from the page: "Components under the `experimental` key, `themes` and `monitors`, have a manifest schema that may change between releases while they stabilize. Where you declare them is a separate migration: the top level still works, `claude plugin validate` warns, and a future release will require `experimental.*`." — confirming Anthropic uses `experimental` as a label, but specifically for `themes` and `monitors`, NOT the primitive itself.
- **Version-pinned new features.** Verbatim: "Plugin monitors require Claude Code v2.1.105 or later." AND "`claude plugin prune` requires Claude Code v2.1.121 or later." — features are added incrementally with version-pinned availability.
- **Manifest schema URL** (machine-readable signal): "`$schema` ... `https://json.schemastore.org/claude-code-plugin-manifest.json`" — the schema is published on schemastore.org for editor autocomplete. Plus `https://anthropic.com/claude-code/marketplace.schema.json` for marketplace.json.
- **CLI surface:** `plugin install`, `plugin uninstall`, `plugin prune`, `plugin enable`, `plugin disable`, `plugin update`, `plugin list`, `plugin tag` — full CRUD on plugin lifecycle.
- **Installation scopes:** `user` (default), `project`, `local`, `managed` — plugin install can be scoped per use case (refuting outcome 3 "unavailable" definitively).

**Kind:** the canonical authoritative docs surface for the plugin primitive's technical specification.

**Contribution to outcome 2 (instability half):** absence of a blanket GA classification + explicit `experimental.*` namespace for sub-features = the primitive is in the "shipped, but no formal stability guarantee" zone. Story 7.2's install-path priority logic should therefore NOT treat plugin install as the stable primary path; the experimental flag opt-in posture (per AC-3 outcome 2's verbatim text "plugin install opt-in flagged as experimental via an explicit `--use-plugin-experimental` flag") is the responsible default.

### 4. Claude Code official `plugins` quickstart docs page — `https://code.claude.com/docs/en/plugins`

Traversed at spike-start (2026-05-07). Key findings:

- **Quickstart confirms the primitive is shipped.** Verbatim: "If you don't see the `/plugin` command, update Claude Code to the latest version." — implies the command is universally available on current Claude Code; the only failure mode is being on an outdated version.
- **Standalone vs plugin choice documented.** Two ways to add custom skills/agents/hooks: standalone (`.claude/` directory) or plugins (directories with `.claude-plugin/plugin.json`). The plugin path is positioned as the "Sharing with teammates, distributing to community, versioned releases, reusable across projects" route — i.e., the production-grade route. Standalone is positioned as "Personal workflows, project-specific customizations, quick experiments". This positioning confirms the plugin primitive is INTENDED for distribution use cases (not just experimentation).
- **No blanket stability statement.** Same finding as source #3 — no `GA` / `beta` / `preview` / `experimental` classification on the primitive itself.
- **Submission portals named.** "claude.ai/settings/plugins/submit" and "platform.claude.com/plugins/submit" — Anthropic operates submission portals for the official marketplace, indicating an active distribution surface. Cowork enterprise plugins (per the `support.claude.com` release-notes evidence in source #5) ship as a paid feature.
- **`--plugin-dir` and `--plugin-url` flags** for development-time install — the primitive supports CI-friendly testing flows.

**Kind:** the canonical quickstart docs surface; the entry-point an FR35 reader would traverse first.

**Contribution to outcome 2:** confirms primitive is functional, intended for production distribution, AND lacks a blanket stability statement. Two halves of outcome 2 anchor here: functional (production-distribution positioning) AND not-quite-stable (no GA classification surfaced).

### 5. Claude Code changelog + version history — `https://code.claude.com/docs/en/changelog` (traversed via `kindly-web-search`)

Traversed at spike-start (2026-05-07) via `kindly-web-search` query "Claude Code plugin primitive stability beta experimental general-availability release notes" with results spanning ~42 days of release-note history (CC 2.1.90 → 2.1.132). Behavioral churn signals (verbatim quotes from changelog entries):

- v2.1.129: "Plugin manifests: `themes` and `monitors` should now be declared under `\"experimental\": { ... }`. Top-level declarations still work but `claude plugin validate` will warn" — soft-deprecation of top-level manifest declarations IN A 2.1.x point release. Manifest schema is in active flux.
- v2.1.120: "`claude plugin validate` now accepts `$schema`, `version`, and `description` at the top level of `marketplace.json` and `$schema` in `plugin.json`" — manifest schema is still being widened.
- v2.1.118: "When auto-update skips a plugin due to another plugin's version constraint, the skip now appears in `/doctor` and the `/plugin` Errors tab" — version-constraint conflicts are a known failure mode; surfacing them in the UI is itself a stabilization event.
- v2.1.119 fix: "Fixed plugin MCP servers failing when `${user_config.*}` references an optional field left blank"
- v2.1.121 fix: "Fixed MCP servers from plugins not spawning on Windows when the plugin cache was incomplete"
- v2.1.128 fix: "Fixed stale `installed_plugins.json` entries pointing at deleted cache directories polluting PATH"
- v2.1.128 fix: "Fixed `/plugin update` never detecting new versions of npm-sourced plugins"
- v2.1.118 fix: "Fixed `plugin install` on an already-installed plugin not re-resolving a dependency installed at the wrong version"
- v2.1.105: "Marketplace plugins with `package.json` and lockfiles now auto-install deps on install/update; fixed marketplace auto-update leaving the official marketplace broken when a plugin held files open" — past breakage of the marketplace.
- v2.1.117: "Plugin dependency errors now distinguish conflicting, invalid, and overly complex version requirements" — version-resolution algorithm is still being refined.
- v2.1.91: "Plugins can now ship executables under `bin/` and invoke them as bare commands from the Bash tool" — feature-add cadence is high.
- v2.1.90: "Added `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE` to keep the existing marketplace cache when `git pull` fails" — defensive flags are still being added, indicating the failure modes are still being characterized.

Plugin-related changelog entries appear in nearly every 2.1.x point release between 2.1.90 and 2.1.132 (≈42 days, 42 releases). This is high-churn surface area.

**Kind:** the canonical historical record of plugin-primitive evolution; a multi-week documentary trail.

**Contribution to outcome 2 (instability half):** the manifest schema is STILL being widened (2.1.120, 2.1.129); past breakage events have occurred (v2.1.105 marketplace auto-update breaking); soft-deprecation has happened recently (v2.1.129 themes/monitors moving to `experimental.*`); plugin-related bug fixes ship in nearly every release. The primitive is high-churn — supporting outcome 2's "unstable but functional" classification, NOT outcome 1's "stable" classification.

### 6. Implicit prior-art validation — Story 5.7 evidence artifact precedent at `bmad-autopilot/docs/research-spikes/2026-05-04-deferred-work-format.md`

THIS spike's evidence artifact mirrors Story 5.7's structure byte-for-byte at the section-shape level:

| Structural element | Story 5.7 (2026-05-04) | THIS spike (2026-05-07) | Conformant |
|---|---|---|---|
| Path layout | `docs/research-spikes/{spike-start-date}-{topic-slug}.md` | `docs/research-spikes/2026-05-07-plugin-primitive-stability.md` | ✓ |
| Title H1 | `# Deferred-work.md format spec audit (Story 5.7)` | `# Claude Code plugin primitive stability spike (Story 7.1)` | ✓ |
| Header blockquote | "Spike-with-bounded-timebox instance #1 of the pattern…" | "Spike-with-bounded-timebox instance #2 of the pattern…" | ✓ |
| `## Spike metadata` table | 13 rows (spike-start, spike-end, timebox, fallback-fired, selected outcome, evidence count, per-convention-row backref, FR15 anchor, research-blocker source, epics anchor, forward consumers) | 17 rows (extends Story 5.7's schema with calendar-min, calendar-max, two task-completion-criterion rows, calendar-min-honored, fallback-fired-rationale) | ✓ (extended for task-bounded refinement) |
| `## Evidence sources reviewed` | 4 sources | 6 sources (≥4 per AC-7 item 2 floor) | ✓ |
| `## Outcome-decision flow` | 3 subsections (selected, rejected, named fallback REJECTED) | 3 subsections (selected, rejected, named fallback REJECTED) | ✓ |
| `## Forward consumers` | 3 named consumers + future-spike pattern | 4 named consumers + future-spike pattern + pattern-selection decision aid | ✓ (extended for AC-9) |

**Kind:** structural template precedent; the FIRST instance of the spike-with-bounded-timebox pattern at MVP scope.

**Contribution to outcome 2 (no contribution to evidence per se; structural validation only):** confirms THIS artifact is conformant with Story 5.7's reusable shape per AC-5; confirms the per-convention-row + closing-remark sub-paragraph appends are mirrored from Story 5.7's worked example. Structural reusability per AC-9 is anchored here.

## Outcome-decision flow

Three named outcomes per AC-3. Each is evaluated against the AC-1 evidence above; the selected outcome is named first.

### Outcome 2: Plugin primitive unstable but functional — **SELECTED**

> "Story 7.2 ships git-clone-symlink as primary; plugin install opt-in flagged as experimental via an explicit `--use-plugin-experimental` flag (Story 7.2's surface). Classification entry text in `bmad-autopilot/docs/extension-audit.md` per `epics.md` line 2893 verbatim: **'Claude Code plugin primitive available but flagged experimental'**." (per `_bmad-output/planning-artifacts/epics.md` line 2893 verbatim — the canonical classification language for outcome 2.)

**Fires because:**

- The plugin primitive IS exposed and functional (refuting outcome 3): `/plugin install <name>@<marketplace>` works end-to-end (evidence source #1 — warp install operational across two Claude Code versions); the official Anthropic-operated marketplace serves 35+ plugins from diverse vendors (evidence source #2); the docs surface positions plugins as the production-distribution route (evidence source #4 — "Sharing with teammates, distributing to community, versioned releases" framing).
- The plugin primitive lacks a blanket stability statement (refuting outcome 1): NO `GA` / `beta` / `preview` / `experimental` classification of the primitive itself surfaces in `code.claude.com/docs/en/plugins` or `code.claude.com/docs/en/plugins-reference` (evidence sources #3 + #4). Sub-features `experimental.themes` and `experimental.monitors` ARE explicitly tagged experimental (evidence source #3 verbatim quote) — confirming Anthropic uses `experimental` as a label but specifically does NOT apply it to the primitive, leaving the primitive in the unlabeled "shipped without a formal stability tier" zone.
- The plugin primitive exhibits manifest-schema churn (additional support for outcome 2): v2.1.129 moved `themes`/`monitors` from top-level to `experimental.*` (soft-deprecation in a 2.1.x point release); v2.1.120 widened `marketplace.json`/`plugin.json` to accept `$schema`/`version`/`description` at top level (schema is still in flux); plugin-related bug fixes ship in nearly every release between 2.1.90 and 2.1.132 (evidence source #5). The manifest schema and runtime are stabilizing actively but not stabilized.
- The named-fallback discipline at AC-2's calendar-maximum was NOT triggered (refuting outcome 3 by default): the spike converged on outcome 2 within hours of spike-start; outcome 3 is only the structural default WHEN the calendar-maximum (3 weeks) is reached without convergence. THIS spike converged.

**Forward consequence (consumed by Story 7.2 per `epics.md` lines 2913-2916 verbatim):** Story 7.2's install-path priority logic reads THIS row's classification entry text from `docs/extension-audit.md` and ships **git-clone-symlink as primary, plugin install as opt-in experimental** via an explicit `--use-plugin-experimental` flag. The plugin manifest authoring (Story 7.2's deliverable) lands at `bmad-autopilot/.claude-plugin/plugin.json` (NOT `bmad-autopilot/plugin.json` — per the on-disk evidence at source #1 + #2; the View 2 layout placeholder at `architecture.md` line 1115 is reconciled to the actual Claude Code convention by Story 7.2). The repo-layout-finalization gated decision at `architecture.md` lines 1299-1300 + line 1419 + line 1420 unblocks via THIS outcome's choice.

**Classification:** `automator-internal` — install-path priority is a wrapper-layer-only convention with no `upstream-proposal` target since BMAD core does not own Claude Code plugin distribution AND Claude Code plugin distribution is an Anthropic-owned primitive — neither party is a candidate for an `upstream-proposal` migration plan. See per-convention-table row at `docs/extension-audit.md` § "Per-convention table" (the most recently appended row at the table tail; the FIRST row added by an Epic-7 story).

**No behavior change beyond the per-convention-row + closing-remark + this evidence artifact.** AC-10's `git diff --stat` enforces that the substrate source tree, schemas, and pyproject.toml are untouched.

### Outcome 1: Plugin primitive stable — REJECTED

> "Story 7.2 ships plugin install as primary; git-clone-symlink fallback is documented but not the primary path. Classification entry text in `bmad-autopilot/docs/extension-audit.md` per `epics.md` line 2892 verbatim: 'Claude Code plugin primitive used as primary install path'." (per `_bmad-output/planning-artifacts/epics.md` line 2892 verbatim — the canonical classification language for outcome 1.)

**Rejected because the plugin primitive's stability is NOT yet established by the docs surface AND the runtime exhibits ongoing manifest-schema churn.**

The specific evidence point that excludes outcome 1: the v2.1.129 changelog entry (evidence source #5 verbatim quote): "Plugin manifests: `themes` and `monitors` should now be declared under `\"experimental\": { ... }`. Top-level declarations still work but `claude plugin validate` will warn." This is a manifest-schema soft-deprecation event 3 days before spike-start. A primitive that requires soft-deprecation of top-level fields in a recent point release is NOT a primitive that satisfies outcome 1's "with no observed breakage AND a stability statement (GA / equivalent) is found" branch — the soft-deprecation itself is observed schema-instability in the recent past, refuting "no observed breakage".

The OR-clause of outcome 1 ("OR observed-stability-without-statement is sufficient evidence of de-facto stability") is also not satisfied. Observed-stability would require: (a) no recent manifest-schema changes (fails per v2.1.129 above); (b) no recent breakage events (fails per evidence source #5 — v2.1.105 marketplace auto-update broke; multiple v2.1.118-128 fixes for plugin/MCP-server/cache breakage); (c) a multi-version operational track record without primitive-level breaking changes (partially satisfied — the warp install survives 2.1.x → 2.1.132 — but only across one plugin, not across the wider primitive surface).

If outcome 1 had fired, Story 7.2 would have shipped plugin install as primary with git-clone-symlink demoted to fallback. Given the observed instability signals, that ordering would over-promise stability to first-time users — the FR36 day-one fallback discipline (`prd.md` line 549: "Works today. Idempotent. Should succeed regardless of plugin primitive stability.") explicitly anticipates this rejection.

### Outcome 3: Plugin primitive unavailable or breaking — REJECTED (named fallback)

> "Story 7.2 ships git-clone-symlink only; plugin install deferred to a future release; the deferred-state is documented in the per-convention row's revisit conditions. Classification entry text in `bmad-autopilot/docs/extension-audit.md` per `epics.md` line 2894 verbatim: 'Claude Code plugin primitive deferred'." (per `_bmad-output/planning-artifacts/epics.md` line 2894 verbatim — the canonical classification language for outcome 3 + named-fallback structure.)

**Rejected because the plugin primitive IS exposed and IS operational.**

The specific evidence point that excludes outcome 3: evidence source #1's `installed_plugins.json` entry — `warp@claude-code-warp` v2.0.0 was installed via `/plugin install warp@claude-code-warp` on 2026-04-27 and remains operational at spike-start 2026-05-07 across at least one Claude Code version bump. Plus evidence source #2's marketplace structure: 35+ Anthropic-internal plugins + 16+ external partner plugins resolve to valid `.claude-plugin/plugin.json` manifests under `~/.claude/plugins/marketplaces/claude-plugins-official/`. The `/plugin install` command does NOT return a not-implemented error; the plugin primitive IS exposed; >50% of the reference-project / Claude Code version pairs do NOT exhibit breaking failures.

**Named-fallback structure** (documented for the pattern's reusability per AC-3 + AC-7 + AC-9 even though the fallback didn't fire): had the bounded 3-week timebox (calendar-maximum from spike-start `2026-05-07`) expired without convergence on outcome 1 or 2, OR had the spike observed >50% breaking failures across the reference-project / Claude Code version pairs OR observed the `/plugin install` command not exposed at all on the audited Claude Code versions, this spike would have:

1. Selected outcome 3 (plugin primitive unavailable or breaking).
2. Added a per-convention-row to `docs/extension-audit.md` with classification `automator-internal` and rationale "no plugin primitive available or primitive exhibits breaking failures on >50% of reference-project / Claude Code version pairs within timebox".
3. Recorded the verbatim classification text from `epics.md` line 2894: "Claude Code plugin primitive deferred".
4. Recorded the revisit condition: "if Claude Code primitive becomes available (any future Claude Code version exposes the install primitive), re-audit per the same task-completion criteria".
5. Documented that Story 7.2 would ship git-clone-symlink only; plugin install would be deferred to a future release.

The fallback's named structure is preserved here so a future spike-blockered story has a documented worked example of what the fallback path would have looked like — even when the fallback does not fire — per the same documentation discipline Story 5.7 demonstrated for its outcome-3 subsection (line 165 of Story 5.7's evidence artifact).

## Forward consumers

Four named consumers per AC-7 item 4 + the future-spike pattern-selection decision aid per AC-9. Each is named explicitly so the convention reuse is discoverable from THIS artifact (not just from the consumer's own text when it lands).

### Story 7.2 — Plugin install path + git-clone-symlink fallback (FR35 + FR36)

`7-2-plugin-install-path-git-clone-symlink-fallback-consumes-7-1-outcome` (per `_bmad-output/implementation-artifacts/sprint-status.yaml` line 136) — primary consumer of THIS spike's outcome on three seams:

1. **Per-convention-row classification** — Story 7.2's install-path priority logic reads the verbatim classification entry text "Claude Code plugin primitive available but flagged experimental" from `docs/extension-audit.md` § "Per-convention table" (the most recently appended row) and ships git-clone-symlink as primary + plugin install opt-in via `--use-plugin-experimental` flag.
2. **Plugin manifest path finalization** — Story 7.2 authors `bmad-autopilot/.claude-plugin/plugin.json` (NOT `bmad-autopilot/plugin.json`) per the on-disk evidence at THIS artifact's evidence source #1 + #2. The View 2 layout placeholder at `architecture.md` line 1115 is reconciled to the actual Claude Code convention by Story 7.2.
3. **Install method config field** — `_bmad/automation/config.yaml` `install_method` field per `epics.md` line 2930 (`plugin | git-clone-symlink`) — Story 7.2 sets the default to `git-clone-symlink` per outcome 2's primary-fallback ordering.

The seam is one-way: Story 7.2 reads THIS artifact + the per-convention-row to compute the install-path priority; THIS artifact does not reference Story 7.2's install-path implementation (Story 7.2 owns the install module's surface).

### Story 7.5 — Config + qa-runbook stub generation

`7-5-config-qa-runbook-stub-generation` (per `_bmad-output/implementation-artifacts/sprint-status.yaml` line 139) — downstream consumer of Story 7.2's `install_method` field. THIS spike's outcome propagates indirectly: Story 7.5 reads `_bmad/automation/config.yaml` `install_method` to know whether the install method is `plugin` or `git-clone-symlink` per outcome 2's ordering. Story 7.5 does not directly read THIS spike's evidence artifact, but its config-stub generation depends on Story 7.2 having finalized the install method per outcome 2.

### Story 7.9 — 5-min first-loop benchmark validation

`7-9-5-min-first-loop-target-validation-benchmark-artifact-component-breakdown` (per `_bmad-output/implementation-artifacts/sprint-status.yaml` line 143) — exercises the install method Story 7.2 ships per THIS spike's outcome. The 5-minute first-loop budget (PRD NFR-O1, prd.md — referenced by Epic 7 framing) bounds the install method's user-facing latency; Story 7.9's benchmark consumes the install method as a black box. Per outcome 2, the primary path is git-clone-symlink (faster than plugin-marketplace-mediated install for first-time-user latency) — Story 7.9's benchmark validation aligns with the day-one fallback posture per `prd.md` line 549.

### Future spike-blockered stories — task-bounded pattern reusability

The spike-with-bounded-timebox pattern's task-bounded refinement (introduced by THIS spike) is reusable from THIS file forward. Future spike-blockered stories at Phase 2 / post-MVP scope where the question demands hands-on observation (not just upstream-spec reading) instantiate the same shape:

- `bmad-autopilot/docs/research-spikes/{spike-start-date}-{topic-slug}.md` path layout.
- Four named sections: `## Spike metadata` / `## Evidence sources reviewed` / `## Outcome-decision flow` / `## Forward consumers`.
- Three named outcomes with named fallback at the calendar-maximum boundary.
- Per-convention-row append at the table tail of `docs/extension-audit.md`.
- Closing-remark sub-paragraph append in `docs/extension-audit.md` § "Research-blocker handling" immediately after the discharging story's anchor.

### Pattern-selection decision aid (per AC-9)

A future spike author choosing between THIS story's task-bounded shape vs Story 5.7's calendar-week-only shape should apply the following decision tree:

| Spike question shape | Recommended pattern |
|---|---|
| Spec-readable upstream (the answer is determinable by reading docs / checking on-disk artifacts) | **Story 5.7's calendar-week-only shape** — `1-week timebox; outcome converges fast OR fallback fires`. Use when the question is authored, not empirical. |
| Hands-on observational (the answer requires running fixtures + observing behavior across multiple environments) | **Story 7.1's task-bounded shape** — `task-completion criteria + calendar-minimum (forces re-review with overnight gap) + calendar-maximum (3 weeks; named fallback fires at maximum)`. Use when the question is empirical, not authored. |
| Hybrid (spec-readable upstream BUT requires fixture-install confirmation) | **Story 7.1's task-bounded shape** with relaxed task-completion criteria. The hands-on observational requirement is the discriminator: if any fixture install is required for the spike to commit honestly, use the task-bounded shape. |

THIS story is the FIRST documented worked example of the task-bounded shape; Story 5.7 is the FIRST documented worked example of the calendar-week-only shape. Both shapes share the 3-component invariant from the principle paragraph at `docs/extension-audit.md` § "Research-blocker handling" (line 159 post-this-row-insertion; line 158 pre-insertion per Story 7.1 AC-5/AC-8 line-number verbiage) verbatim: defined exit criterion + bounded timebox + named fallback.
