# Git hygiene

This document codifies the operation-scope rules and the per-story branch naming convention the BMAD Agent Development Automator follows when it touches a project's git working tree. It anchors PRD § NFR-S3 (`_bmad-output/planning-artifacts/prd.md` line 971, the canonical git-operation-scope statement), is read in conjunction with PRD § NFR-R3 (`_bmad-output/planning-artifacts/prd.md` line 947, git-operation safety), discharges the codification AC of Story 1.12a (`_bmad-output/planning-artifacts/epics.md` lines 1067-1069), and is read at branch-lifecycle implementation time by Story 2.3 (`_bmad-output/planning-artifacts/epics.md` lines 1218-1230, the per-story branch lifecycle module).

The boundary is narrow on purpose: the Automator's git surface is a small, well-known set of commands it issues against the user's local working tree. Anything outside that surface is out of scope and a violation if attempted. The Automator enforces these rules at runtime by halting with a diagnostic when an out-of-scope operation is requested; this doc is the contract that runtime behavior implements.

## NFR-S3 — Git operation scope

Quoted verbatim from `_bmad-output/planning-artifacts/prd.md` line 971:

> **Git operation scope** — Automator git operations are limited to: branch creation, checkout, commit, and local branch management. No auto-push to remote (except opt-in auto-merge in Phase 2+). No force-push ever. No operations on branches other than the story branch. No operations on `main` / `master` / `trunk`.

## Operational guidance

The verbatim scope statement above is the rule. The bullets below unpack each rule into the per-operation behavior the Automator enforces:

- **Per-story branch only.** Every git operation the Automator issues runs on the story branch (named per the convention below). Operations targeted at any other branch — even read-only ones like `git checkout` of a branch matching another story's pattern — are out of scope.
- **No operations on `main` / `master` / `trunk`.** The Automator never checks out, commits to, merges into, or otherwise modifies the project's trunk branch. Trunk integration is the practitioner's responsibility (manual merge of the story-branch PR), not the Automator's.
- **No auto-push to remote.** The Automator does not run `git push`. The story branch lives on the user's local clone until the user decides to push it. The single Phase 2+ exception is opt-in auto-merge (per NFR-S3's parenthetical), which is gated on a future story under Phase 2 and is not in MVP scope.
- **No force-push ever.** Even when opt-in auto-push lands in Phase 2+, force-push (`git push --force`, `git push --force-with-lease`, equivalent porcelain forms) is permanently out of scope. The Automator has no command path that emits force flags.
- **No operations that destroy uncommitted user work.** Per NFR-R3 (PRD line 947) and `_bmad-output/planning-artifacts/epics.md` line 1069, the Automator halts with a diagnostic on operations that would destroy uncommitted user work — `git reset --hard`, `git checkout` over modified files, `git clean -fd`, equivalent porcelain forms. The halt-with-diagnostic behavior is the Automator's enforcement of the NFR-R3 and NFR-S3 safety requirements (Story 2.3 implements the halt; this doc anchors the contract). The diagnostic surfaces a marker that lands in the PR bundle.
- **Allowed primitives.** Branch creation (`git checkout -b`, `git branch`), checkout (`git checkout` of a clean tree onto the story branch), commit (`git add` + `git commit` against story-scoped paths), local branch management (rename, delete of fully-merged local-only branches once Phase 2 lifecycle ships), and read-only introspection (`git status`, `git diff`, `git log`, `git rev-parse`, `git stash list` — needed to detect uncommitted work and verify clean-tree state before write operations). Write operations beyond the above — fetch, pull, merge, rebase, cherry-pick, tag operations, remote configuration — are out of scope at MVP.

## Branch naming convention

The canonical convention is:

```
bmad-automation/story/<story-id>
```

For example, a BMAD story whose ID is `1-12a` produces a branch named `bmad-automation/story/1-12a`. A story with ID `2-3` produces `bmad-automation/story/2-3`. The `<story-id>` placeholder is the same identifier the BMAD planning workflow assigns to the story (the `<epic>-<story>` slug used as the prefix of the story file under `_bmad-output/implementation-artifacts/`).

**Why this shape.** The `bmad-automation/` namespace prefix makes Automator-produced branches visually distinguishable from human-created branches at a glance — the same legibility rationale NFR-O6 names for commit history, applied here to branch names. The `story/<story-id>` infix scopes the branch to a single BMAD story-id so per-story branch lifecycle is unambiguous: every branch under `bmad-automation/story/` corresponds to exactly one story file, and the Automator can locate the owning story-id from the branch name without external state.

**Documented, not invented.** The convention is documented here (this section) so Story 2.3's per-story branch lifecycle module reads it from a single source rather than inventing one inline. Per `_bmad-output/planning-artifacts/epics.md` line 1228 ("the branch name follows a documented convention (e.g., `bmad-automation/story/<story-id>` — exact convention codified in `docs/git-hygiene.md` per Story 1.12a)"), Story 2.3 cites this document as the canonical answer.

**Phase 2+ extensions.** Future stories that extend the branch lifecycle (Phase 2 branch deletion after auto-merge, opt-in auto-merge per NFR-S3's exception clause) read the same canonical source. Additional branch-naming conventions (hotfix branches, retry-mode branches, draft branches) are not in MVP scope; if a future story discovers the need for one, that story extends this section. The MVP ships the v1 convention only.

## Source authorities

- **PRD § NFR-S3** (`_bmad-output/planning-artifacts/prd.md` line 971) — the verbatim git-operation-scope statement above.
- **PRD § NFR-R3** (`_bmad-output/planning-artifacts/prd.md` line 947 — git-operation safety) — the primary mandate for the halt-with-diagnostic rule ("Git operations that would destroy uncommitted user work halt with a diagnostic rather than proceeding"); read together with NFR-S3 for the complete git-operation contract.
- **PRD § NFR-O6** (`_bmad-output/planning-artifacts/prd.md` operability NFR section, commit-history-legibility) — the legibility rationale applied to branch names in the section above.
- **Epics.md § Story 1.12a AC** (`_bmad-output/planning-artifacts/epics.md` lines 1067-1069) — the codification AC this document discharges, including the destructive-operation halt-with-diagnostic guidance.
- **Epics.md § Story 2.3** (`_bmad-output/planning-artifacts/epics.md` lines 1218-1230) — the per-story branch lifecycle module that consumes the convention codified in `## Branch naming convention` above.
