---
expected_marker: walking-skeleton-bundle
scenario: PR bundles produced by a substrate that lacks the loud-fail block carry this marker; emission rule is "absent loud-fail block triggers the marker," not "Epic 2 era triggers the marker."
---
# Synthetic story: walking-skeleton-bundle

A bundle assembled by the orchestrator before Epic 6's full
loud-fail block thickening lands. The bundle assembler detects that
the loud-fail block section is structurally empty (no markers, no
how-to-enable pointers, no per-specialist failure surfaces) and
emits the `walking-skeleton-bundle` marker so reviewers know the
bundle is from a thin-signals era substrate, not a fully-thickened
loud-fail surface. Per Epic 6's clarification, the rule is
"absent loud-fail block triggers the marker," not "Epic 2 era
triggers the marker" — Epic 6's flag-flip removes the marker once
the block becomes present.
