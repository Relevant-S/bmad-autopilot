---
expected_marker: story-doc-version-out-of-window
scenario: An out-of-window story-doc template version surfaces this marker plus upgrade guidance, rather than failing hard.
---
# Synthetic story: story-doc-version-out-of-window

The orchestrator picks up a story-doc whose template version is
older than the supported tolerance window (FR43: N-2 minor versions;
NFR-I5: tolerance behavior). Rather than refusing to run, the
orchestrator emits the marker into the run-state, leaves the story
in `proposed-qa` (or whatever lifecycle state was current), and
surfaces an upgrade-guidance pointer in the bundle so the
practitioner knows to migrate the story-doc before retrying.

Practitioner remediation: regenerate the story-doc against the
current template, OR explicitly waive the tolerance window if the
template change is content-only.
