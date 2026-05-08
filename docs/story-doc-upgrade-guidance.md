# Story-doc upgrade guidance

## What this doc is

This document is the diagnostic-pointer target for the
`story-doc-version-out-of-window` marker (Story 1.4 v1 closed taxonomy
— `schemas/marker-taxonomy.yaml` lines 352-358). When the Automator
detects a BMAD story-doc template version older than the configured
tolerance window, the runtime emits the marker AND interpolates a
reference to a specific section of this doc into the marker's
`diagnostic_pointer`. Updating this doc updates the marker's
actionable guidance without code changes.

The contract is bidirectional: the marker is the loud-fail signal
that something is out-of-window; this doc is the remediation. They
ship as a contract pair (Story 7.7) — `_bmad-output/planning-artifacts/epics.md`
lines 3094-3097 verbatim. Cross-references:

- **FR43** — `_bmad-output/planning-artifacts/prd.md` line 868: "Automator
  reads story docs written in BMAD story-doc template formats up to
  N-2 minor versions old without failing; out-of-window versions
  produce a loud-fail marker with upgrade guidance."
- **NFR-I5** — `_bmad-output/planning-artifacts/prd.md` line 962:
  "Story-doc version tolerance — Automator tolerates BMAD story-doc
  template formats within the configured window... out-of-window
  produces a loud-fail marker with upgrade guidance, not a hard
  failure."

## Why story-doc template versions matter

BMAD's `bmm` module ships a story-doc template
(`_bmad/bmm/4-implementation/bmad-create-story/template.md`) that
the `bmad-create-story` skill expands into the per-story files the
Automator's specialists read at every dispatch. Across BMAD minor
releases the template evolves: sections are added, renamed, or
restructured. The Automator's runtime parses fields out of these
files (Status line, Acceptance Criteria block, sections enumerated
in `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/story_doc_validator.py`).
A template-version drift between what the Automator was built against
and what the practitioner's `_bmad/` install produces can break a
mid-loop dispatch silently.

The N-2 default exists because BMAD upgrades happen mid-project: a
practitioner who runs `bmm:install --upgrade` between story 1.5 and
1.6 should not have story 1.6 fail because the Automator's parser
suddenly disagrees with the new template. The marker (rather than a
hard failure) is the deliberate posture from `prd.md` line 566 —
"the cohort that 'widely bailed on' BMAD because mid-loop friction
is what loses adopters."

## Detecting the in-use version

The Automator's runtime detects the template version via two tiers
(see `tools/loud-fail-harness/src/loud_fail_harness/story_doc_version_check.py`
for the implementation):

1. **Inline marker** — an HTML comment on the first 20 lines of the
   story doc: `<!-- bmm-template-version: X.Y -->`. The current BMM
   6.2 template carries no inline marker; this tier is forward-
   compatible (future BMM versions OR the Automator's own
   `create-story` workflow MAY emit one on doc generation).
2. **Manifest fallback** — `_bmad/_config/manifest.yaml`'s `modules`
   list, where the entry `name: bmm` carries `version: X.Y.Z`. This
   is the steady-state production path at Story 7.7's landing.

To check the version yourself, look at `_bmad/_config/manifest.yaml`
under your project root. The `modules` list contains an entry like:

```yaml
- name: bmm
  version: 6.2.2
```

The Automator normalizes that to minor-version granularity (`6.2.2`
→ `6.2`).

## Upgrading from version 6.0

At Story 7.7's landing, BMAD has not published a public 6.0 → 6.1
changelog accessible from this repository. Practitioners on BMM 6.0
who hit this marker should:

1. Inspect `_bmad/bmm/4-implementation/bmad-create-story/template.md`
   in their install and compare the H2 section list against
   the current 6.2 template (sections: Story / Acceptance Criteria
   / Tasks-Subtasks / Dev Notes / Dev Agent Record / File List /
   Change Log).
2. Re-run `bmad-create-story` for any in-progress story whose file
   pre-dates the upgrade — the new file inherits the current
   template's section structure.
3. Cross-check `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/story_doc_validator.py`'s
   `ALLOWED_SECTIONS` constant against your story doc's H2
   headings; any unrecognized section is a write-time
   `undocumented-section-write` marker target (Story 1.10b).
4. Consult the BMAD upstream — `https://github.com/bmad-org/bmad`
   release notes (when published) and migration guides per upstream
   convention.

If you have a complete BMM 6.0 → 6.1 changelog and want to extend
this section, see `## Reference` below for the contributor pointer.

## Upgrading from version 6.1

Same posture as 6.0 above: at Story 7.7's landing there is no public
BMM 6.1 → 6.2 changelog accessible from this repository. The pragmatic
upgrade path is:

1. Run `bmm:install --upgrade` (or the equivalent for your install
   method) and let BMAD's installer manage the migration.
2. Run `bmad-create-story` for in-progress stories to regenerate
   their files against the 6.2 template.
3. The Automator's runtime should silently tolerate 6.1 doc reads
   until the practitioner re-creates them — the tolerance window is
   `2` by default.

## Older versions (catch-all)

For any BMM version below `6.0` (or any version-without-a-specific-
section above), the upgrade story is structurally similar:

1. **Verify your BMAD install is on a supported major version.**
   Major-version mismatch is OUT OF SCOPE for this marker — it is a
   total-block at `init` time per Story 7.3
   (`bmad-core: version_floor: "6.0"` in `schemas/dependencies.yaml`).
2. **Bring your BMAD install up to a recent minor.** The Automator
   tolerates N-2 minor versions back from the current
   Automator-supported version (see
   `loud_fail_harness.story_doc_version_check.SUPPORTED_BMM_TEMPLATE_VERSION`
   for the canonical "N").
3. **Regenerate in-progress story docs** via `bmad-create-story`
   so they inherit the current template structure.
4. **If upgrading is not feasible right now**, you can widen the
   tolerance window temporarily — see `## Adjusting the tolerance
   window` below — to suppress the marker. This is a deliberate
   stop-gap, not a fix; the underlying drift remains.

If your version is significantly behind (e.g., a 5.x release several
minors back), expect the section structure of your story docs to
diverge from what the Automator's parser expects; the marker is a
warning that this drift exists. The runtime PROCEEDS with the read
(not a hard failure) — but the practitioner should treat the marker
as a prompt to upgrade.

## Adjusting the tolerance window

The tolerance window is configured by the
`story_doc_version_tolerance_window` field in
`_bmad/automation/config.yaml` (Story 7.5). The shipped default is
`2`; widening to `3` or `4` accepts more drift before the marker
fires; narrowing to `1` or `0` makes the runtime stricter.

```yaml
# _bmad/automation/config.yaml
story_doc_version_tolerance_window: 2
```

The PRD's revisit condition (`prd.md` lines 673-674 verbatim) reads:
"if ≥ 2 BMAD story template changes in a 6-month window produce
loud-fail markers on the Automator's reference projects, the window
tightens to N-1, paired with one Automator release that re-pins the
'N' constant before the BMAD release that would otherwise tip it
out-of-window."

Do not edit the `SUPPORTED_BMM_TEMPLATE_VERSION` constant in
`tools/loud-fail-harness/src/loud_fail_harness/story_doc_version_check.py`
to silence this marker — that constant tracks the Automator's
supported "N" and is bumped per Automator release, not per
practitioner-project.

## Reference

- **FR43** — `_bmad-output/planning-artifacts/prd.md` line 868
  (N-2 default + configurable window + marker-with-upgrade-guidance
  behavior).
- **NFR-I5** — `_bmad-output/planning-artifacts/prd.md` line 962
  (story-doc version tolerance — "not a hard failure").
- **Versioning & Deprecation** —
  `_bmad-output/planning-artifacts/prd.md` lines 660-674 (semver
  policy + N-2 default rationale + revisit condition).
- **ADR-005** — `_bmad-output/planning-artifacts/architecture.md`
  lines 508 / 534 (state-derivation correctness across versions;
  coordination with FR43).
- **Story 1.4 marker-class declaration** —
  `bmad-autopilot/schemas/marker-taxonomy.yaml` lines 352-358 (v1
  closed taxonomy; consumed AS-IS by Story 7.7).
- **Story 7.7 implementation surface** —
  `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/story_doc_version_check.py`
  (the detection function + the upgrade-guidance loader).
- **Story 7.5 config-field shape** —
  `bmad-autopilot/tools/loud-fail-harness/src/loud_fail_harness/_data/config.yaml.template`
  lines 58-67 (the canonical default + comment block).
- **Story 1.10a pluggability gate** — classifies
  `story_doc_version_check` as shared substrate; specialists may
  import it without violating the gate.
- **Story 1.12a doc-promotion-boundary** — the doc shape (H2
  sections structured for runtime extraction) follows the precedent
  set in `docs/tea-vs-automator.md` and `docs/extension-audit.md`.

To extend a version-specific upgrade section, edit the corresponding
`## Upgrading from version X.Y` heading body. The runtime extraction
(see `load_upgrade_guidance` in `story_doc_version_check.py`) is
heading-line-aware via regex; preserve the heading shape verbatim.
