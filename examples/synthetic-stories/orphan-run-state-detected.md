---
expected_marker: orphan-run-state-detected
scenario: bmad-automation status enumerator found run-state entries for stories whose story-doc has been deleted, renamed, or moved (FR48b).
---
# Synthetic story: orphan-run-state-detected

The practitioner invokes `/bmad-automation status` (no args, the
multi-story listing variant per FR48b). The enumerator reads the
run-state cache and discovers entries for story-ids whose
corresponding story-doc has been deleted, renamed, or moved out of
the `_bmad-output/implementation-artifacts/` directory. The marker
surfaces in the listing so the practitioner can decide to purge the
orphan run-state OR recover the missing story-doc.

Distinct from `recovery-state-conflict` (state inconsistency for a
*known* story) and from `dangling-evidence-ref` (story-doc is the
canonical anchor, not evidence). Conflating these semantics is
forbidden per the marker's diagnostic_pointer.
