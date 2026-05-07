# Bundle-assembly-failure fixtures

Canonical reference artifacts for the Story 6.9 fallback-diagnostic-file format
emitted by `surface_assembly_failure` (at
`tools/loud-fail-harness/src/loud_fail_harness/bundle_assembly_failure.py`)
across Channel 1 of the three reinforcing channels (FR59 + NFR-O5).

## Format

Each `*.assembly-failure.log` file is plain UTF-8 structured-text (NOT
JSON). Practitioners scanning shell logs grep for the canonical header
to find the marker. Fields are emitted in the documented order so
layouts stay consistent across runs.

```
=== bundle-assembly-failed ===
story_id: <story-id>
run_id: <run-id>
failed_step: <one-of-the-five-AssemblyFailureStep-values>
exception_type: <unqualified-class-name>
exception_message: <str(exc)>
generated_at: <ISO-8601 UTC; e.g., 2026-05-07T00:00:00Z>
partial_bundle_path: <on-disk path OR `<none>`>

traceback:
<full Python traceback as rendered by traceback.format_exception>
```

## Files

- `sample-assembly-failure.log` — canonical envelope-mismatch failure (a
  Dev envelope re-validation failure caught by the assembler's outer
  try/except and routed through `surface_assembly_failure`). Used by
  `tests/test_bundle_assembly_failure_fixture.py` as the byte-identity
  golden for the post-6.9 emission output. The `generated_at` timestamp
  is normalized to a fixed test value (`2026-05-07T00:00:00Z`) in the
  fixture-comparison helper so the canonical file is byte-stable across
  runs while the runtime emission still records the actual generation
  time.

## Five `AssemblyFailureStep` sub-classifications

The five enumerated failure modes (epics.md line 2818 verbatim) are:

1. `envelope-mismatch` — `EnvelopeReValidationFailed` raised when an
   envelope recovered from a dispatch log fails re-validation.
2. `missing-finding-fields` — `KeyError` raised from a finding-rendering
   helper (e.g., `_render_finding_bullet`) accessing a required field.
3. `taxonomy-unresolved` — `UnknownMarkerClass` raised from the
   marker-class registry when a marker reference is absent.
4. `finding-render-crash` — non-`KeyError` exception raised from any
   rendering helper while a partial bundle is on disk.
5. `internal-exception` — generic exception (default fallback) when
   none of the above patterns match.

The assembler's classification logic is in `classify_assembly_failure`
(at `bundle_assembly_failure.py`). See `docs/architecture.md`
"Bundle-assembly failure detection" for the full three-channel
emission contract.
