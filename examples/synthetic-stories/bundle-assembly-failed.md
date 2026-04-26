---
expected_marker: bundle-assembly-failed
scenario: PR bundle assembly (FR59 Stop hook) failed due to assembler logic error (envelope shape, finding rendering, taxonomy mismatch).
---
# Synthetic story: bundle-assembly-failed

The Stop hook invokes the bundle assembler, which encounters an
internal logic error — an envelope it cannot render (unexpected
shape), a finding it cannot bucket (taxonomy mismatch with the
allowlisted finding types), or a section template it cannot
populate. The hook exits non-zero; the marker emission targets the
assembler logic surface rather than the bash script's environment
(`hook-failed`'s remediation surface).

Distinct from `hook-failed` per the remediation-shape principle:
practitioners need to know whether to inspect the bash script or
the bundle-assembly code. Markers are remediation-shaped.
