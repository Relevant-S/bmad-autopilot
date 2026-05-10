# Journey 1 — First Story Happy Path

Captured artifacts indexed below. Per Story 8.7 AC-3 verbatim
(`epics.md:3415`): "install → init → run → Dev → Review (3-layer) →
QA (full surface) → merge-ready PR bundle with loud-fail block".

## Artifacts

| File | Description |
|---|---|
| [`install-output.txt`](install-output.txt) | Story 7.2 install path output (git-clone-symlink fallback chosen — plugin primitive forward-scoped per Story 7.1 spike outcome) |
| [`init-output.txt`](init-output.txt) | `bmad-automation init` output covering precondition checks (Story 7.3), sample-story scaffold (Story 7.4), config + qa-runbook stub generation (Story 7.5), TEA-boundary first-run orientation (Story 7.8) |
| [`run-output.txt`](run-output.txt) | `/bmad-automation run sample-auto-001` per-seam streaming output (Story 2.12) culminating in merge-ready completion |
| [`dev-envelope.yaml`](dev-envelope.yaml) | Dev's return envelope — uniform shape per FR51 + Story 2.8 wrapper |
| [`review-bmad-envelope.yaml`](review-bmad-envelope.yaml) | Review-BMAD's three-layer return envelope (Blind Hunter + Edge Case Hunter + Acceptance Auditor) per FR26 + FR56 + Story 2.9 |
| [`qa-envelope.yaml`](qa-envelope.yaml) | QA's per-AC return envelope with AC-1 first ordering per FR22b + Story 2.10 |
| [`pr-bundle-merge-ready.md`](pr-bundle-merge-ready.md) | Assembled merge-ready PR bundle (Story 2.11 + Story 6.1) with loud-fail block at top per FR32 |
| [`journey-1-narrative.md`](journey-1-narrative.md) | Narrative + environment notes + execution date + discovered-gaps triage |
