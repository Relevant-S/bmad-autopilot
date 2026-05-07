"""Canonical-fixture regression test for the Story 6.9 fallback-diagnostic
output (AC-6 fixture clause).

The fixture at `examples/assembly-failures/sample-assembly-failure.log`
is byte-identical to the post-6.9 `surface_assembly_failure` output for
a seeded `envelope-mismatch` failure, with the `generated_at` timestamp
normalized to a fixed test value. The test re-runs the canonical
emission with the same inputs and asserts byte-identity after the
timestamp normalization. Mirrors Story 6.1's
`test_canonical_walking_skeleton_bundle_fixture_matches_assembler_output`
precedent.
"""

from __future__ import annotations

import io
import pathlib
import re

import pytest

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.bundle_assembly import EnvelopeReValidationFailed
from loud_fail_harness.bundle_assembly_failure import surface_assembly_failure
from loud_fail_harness.run_state import (
    CostToDateBySpecialist,
    RunState,
    _serialize_run_state,
)


CANONICAL_GENERATED_AT_LITERAL: str = "2026-05-07T00:00:00Z"

#: Pattern that matches any ISO-8601 UTC timestamp emitted by
#: `surface_assembly_failure` (`%Y-%m-%dT%H:%M:%SZ`).
_GENERATED_AT_RE: re.Pattern[str] = re.compile(
    r"^generated_at: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
    re.MULTILINE,
)


def _normalize_generated_at(body: str) -> str:
    """Replace the runtime `generated_at:` line with the canonical literal."""
    return _GENERATED_AT_RE.sub(
        f"generated_at: {CANONICAL_GENERATED_AT_LITERAL}", body
    )


@pytest.fixture(scope="module")
def canonical_fixture_path() -> pathlib.Path:
    return (
        find_repo_root()
        / "examples"
        / "assembly-failures"
        / "sample-assembly-failure.log"
    )


def test_canonical_fixture_exists(canonical_fixture_path: pathlib.Path) -> None:
    """The canonical fixture must exist on disk so contributors can grep
    for the format without rebuilding it from the substrate.
    """
    assert canonical_fixture_path.exists(), (
        f"canonical fixture missing at {canonical_fixture_path}"
    )


def test_canonical_fixture_byte_matches_surface_assembly_failure_output(
    canonical_fixture_path: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """Witnesses Story 6.9 AC-6 byte-identity — re-running
    `surface_assembly_failure` with the seeded `envelope-mismatch`
    inputs and normalizing the `generated_at` timestamp produces output
    byte-identical to the canonical fixture.
    """
    rs_path = tmp_path / "run-state.yaml"
    rs = RunState(
        schema_version="1.3",
        story_id="auto-001",
        run_id="run-fixture-001",
        current_state="done",
        branch_name="bmad-automation/story/auto-001",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=(),
        marker_contexts={},
        cost_to_date_by_specialist=CostToDateBySpecialist(),
        last_retry_directive=None,
    )
    rs_path.write_text(_serialize_run_state(rs), encoding="utf-8")
    bundle_root = tmp_path / "pr-bundles"

    # Synthetic exception WITHOUT __traceback__ → format_exception emits
    # only the class+message line, keeping the fixture stable.
    exc = EnvelopeReValidationFailed(
        specialist="dev",
        diagnostic="envelope shape mismatch — required field missing",
    )
    record = surface_assembly_failure(
        story_id="auto-001",
        run_id="run-fixture-001",
        run_state_path=rs_path,
        bundle_root=bundle_root,
        exc=exc,
        failed_step="envelope-mismatch",
        registry=None,
        stderr=io.StringIO(),
    )

    runtime_body = record.fallback_diagnostic_path.read_text(encoding="utf-8")
    normalized = _normalize_generated_at(runtime_body)
    expected = canonical_fixture_path.read_text(encoding="utf-8")

    assert normalized == expected
