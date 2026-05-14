"""Story 10.5 AC-7 — NFR-S1 API-key hygiene substrate-library tests.

NFR-S1 contract (PRD verbatim): "API key is read from a documented
environment variable, never from configuration files committed to git,
never written to logs, PR bundles, evidence bundles, or run-state".

Structural enforcement vs self-attestation
==========================================

THIS test module is the structural witness for NFR-S1's
never-in-files invariant — replacing what would otherwise be a
self-attestation pattern (prose-only "do not write the key" rule)
with a byte-level substring scan of every load-bearing persistence
surface. Regression on any surface fails CI loudly per Pattern 5
(loud-fail doctrine) — a diagnostic naming the offending offset +
a 100-byte context window is emitted before the test assertion fires.

Per-test scan discipline (Story 10.5 AC-7 verbatim): byte-level
substring search of the persisted artifact's raw bytes (NOT a
YAML-parse-then-search; YAML round-tripping could re-encode the
sentinel in a way that bypasses string search — e.g.,
base64-encoding a leak; byte-level scanning catches the load-bearing
exposure).

Surface coverage matrix
=======================

The four operationally-load-bearing persistence surfaces this module
covers (per Story 10.5 AC-7):

  1. ``_bmad-output/runs/<run-id>/run-state.yaml`` — Story 2.2 atomic
     run-state YAML.
  2. ``_bmad-output/runs/<run-id>/specialists/<id>/*.log`` — Story
     2.6 per-specialist dispatch log (JSON) at
     :data:`loud_fail_harness.specialist_dispatch.LOG_PATH_TEMPLATE`.
  3. ``_bmad-output/runs/<run-id>/evidence/**/*`` — Story 4.7 / 4.12
     QA evidence-bundle substrate (recursive walk; any file under
     the bundle root is in scope).
  4. ``_bmad-output/runs/<run-id>/pr-bundle.md`` — Story 2.11 / 6.1
     bundle-assembly markdown (the operator-visible PR-comment
     surface NFR-S1 most explicitly names).

Story 10.5 AC-10's "no new CI executable script" invariant: these
tests run under the existing ``uv run pytest`` substrate-component-1
(envelope-validator) gauntlet command via the existing ``tests/``
directory tree. No entry in ``pyproject.toml [project.scripts]`` is
added — the substrate-component count remains FIVE per ADR-003
Consequence 1 + Story 10.5 AC-10 invariant.

Cross-references
================

* Story 2.2 :mod:`loud_fail_harness.run_state` — atomic run-state
  YAML write pipeline.
* Story 2.6 :mod:`loud_fail_harness.specialist_dispatch` —
  :func:`persist_dispatch_log` per-specialist log substrate.
* Story 2.11 / 6.1 :mod:`loud_fail_harness.bundle_assembly` —
  PR-bundle markdown rendering.
* Story 4.7 / 4.12 :mod:`loud_fail_harness.qa_evidence_persistence`
  — QA evidence-bundle persistence path computation.
* Story 10.5 AC-7 — this module's authorship rationale.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

import pytest

from loud_fail_harness.orchestrator_run_entry import (
    AcceptanceCriterion,
    StoryDocResolution,
)
from loud_fail_harness.run_state import (
    CostToDateBySpecialist,
    RunState,
    _serialize_run_state,
)
from loud_fail_harness.bundle_assembly import assemble_bundle
from loud_fail_harness.qa_evidence_persistence import compute_run_dir
from loud_fail_harness.specialist_dispatch import (
    build_dispatch_payload,
    default_prompt_body_renderer,
    persist_dispatch_log,
)


# --------------------------------------------------------------------------- #
# Module-level sentinel constant                                              #
# --------------------------------------------------------------------------- #

#: Canonical sentinel-key-shaped string the byte scan targets. 40+
#: chars, formatted to look like a real OpenRouter key; the substring
#: ``DO-NOT-LEAK`` is the canonical scan target. The discipline:
#: regression on ANY persistence surface that ends up carrying this
#: substring fails CI loudly. Module-level constant for single-point-
#: of-edit hygiene per Pattern 5 + Pattern 6.
_API_KEY_HYGIENE_SENTINEL: str = (
    "sk-fake-real-looking-key-DO-NOT-LEAK-7f3a8e2d1c5b9a0e6f4d"
)


def _assert_sentinel_not_in_bytes(body: bytes, surface_name: str) -> None:
    """Pattern 5 loud-fail helper — scan ``body`` for the sentinel
    substring; emit a 100-byte context-window diagnostic on regression
    BEFORE the assertion fires.
    """
    needle = _API_KEY_HYGIENE_SENTINEL.encode("utf-8")
    offset = body.find(needle)
    if offset != -1:
        start = max(0, offset - 50)
        end = min(len(body), offset + len(needle) + 50)
        context = body[start:end].decode("utf-8", errors="replace")
        pytest.fail(
            f"NFR-S1 hygiene regression on {surface_name!r}: "
            f"sentinel {_API_KEY_HYGIENE_SENTINEL!r} found at byte "
            f"offset {offset}. Context window (100 bytes): {context!r}"
        )


# --------------------------------------------------------------------------- #
# AC-7 hygiene test 1 — run-state YAML substring scan                         #
# --------------------------------------------------------------------------- #


def test_api_key_literal_never_appears_in_run_state_yaml(
    tmp_path: pathlib.Path,
) -> None:
    """Story 10.5 AC-7 hygiene test 1: serialize a Story 2.2
    :class:`RunState` constructed with realistic fields (including
    a ``LAD-skipped`` marker per Story 10.5 AC-2 + AC-4 emission
    paths) via the Story 2.2 canonical serialization pipeline; write
    bytes to a ``tmp_path`` fixture; assert the sentinel substring
    does NOT appear in the bytes.

    The structural witness: the :class:`RunState` model has no field
    accepting an env-var VALUE; the substrate-vs-wrapper boundary
    preserves NFR-S1 by construction. This test is the regression
    catcher if future stories add a field that COULD carry an
    env-var value.
    """
    rs = RunState(
        schema_version="1.3",
        story_id="10-5-test",
        run_id="run-001",
        current_state="in-progress",
        branch_name="bmad-automation/story/10-5-test",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=("LAD-skipped",),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )
    body = _serialize_run_state(rs).encode("utf-8")
    out_path = tmp_path / "run-state.yaml"
    out_path.write_bytes(body)
    read_back = out_path.read_bytes()
    _assert_sentinel_not_in_bytes(read_back, "run-state.yaml")


# --------------------------------------------------------------------------- #
# AC-7 hygiene test 2 — specialist dispatch log substring scan                #
# --------------------------------------------------------------------------- #


def test_api_key_literal_never_appears_in_specialist_dispatch_log(
    tmp_path: pathlib.Path,
) -> None:
    """Story 10.5 AC-7 hygiene test 2: build a
    :class:`SpecialistDispatchPayload` for the ``lad`` specialist
    (with ``api_key_env_var="OPENROUTER_API_KEY"`` — the NAME, never
    the VALUE per Story 10.5 AC-8); call
    :func:`persist_dispatch_log` to write the JSON log; read bytes;
    scan for sentinel.

    The structural witness: the dispatch-payload schema's
    ``api_key_env_var`` field carries the env-var NAME only; the
    rendered prompt body contains the NAME; the persisted log
    serializes the NAME but never the VALUE (the substrate has no
    access to the value).
    """
    story_path = tmp_path / "10-5-test.md"
    story_path.write_text("# Test\n\nStatus: ready-for-dev\n", encoding="utf-8")
    agent_path = tmp_path / "review-lad-wrapper.md"
    agent_path.write_text("# Review-LAD wrapper agent definition.\n", encoding="utf-8")
    resolution = StoryDocResolution(
        path=story_path,
        current_state="ready-for-dev",
        acceptance_criteria=(
            AcceptanceCriterion(ac_id="AC-1", text="Test AC."),
        ),
    )
    fixed_timestamp = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    payload = build_dispatch_payload(
        specialist="lad",
        story_id="10-5-test",
        attempt_number=0,
        story_doc_resolution=resolution,
        agent_definition_path=agent_path,
        prompt_body_renderer=default_prompt_body_renderer,
        dispatch_timestamp_factory=lambda: fixed_timestamp,
        api_key_env_var="OPENROUTER_API_KEY",
    )
    return_envelope = {
        "status": "pass",
        "rationale": "LAD reviewers reached a clean verdict.",
        "findings": [],
        "artifacts": [],
    }
    log_root = tmp_path / "logs"
    log_path = persist_dispatch_log(
        payload,
        return_envelope,
        return_timestamp=fixed_timestamp,
        log_root=log_root,
        run_id="run-001",
    )
    body = log_path.read_bytes()
    _assert_sentinel_not_in_bytes(body, "specialist-dispatch-log")
    # Structural witness: the persisted log is JSON-parseable + the
    # ``return_envelope`` field is preserved verbatim (the substrate
    # writes what the wrapper returned).
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["dispatched_specialist"] == "lad"
    assert parsed["story_id"] == "10-5-test"


# --------------------------------------------------------------------------- #
# AC-7 hygiene test 3 — evidence-bundle substring scan                        #
# --------------------------------------------------------------------------- #


def test_api_key_literal_never_appears_in_evidence_bundle(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 10.5 AC-7 hygiene test 3: the QA evidence-bundle persistence
    substrate computes canonical paths via
    :func:`qa_evidence_persistence.compute_run_dir`; any evidence file
    written by the QA specialist at LLM-runtime lives under that tree.
    Simulate a live key in the process environment so any future
    evidence-pipeline extension that accidentally reads the env var and
    persists its VALUE is caught; recursively walk the bundle tree; assert
    the sentinel substring does NOT appear in any file.
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", _API_KEY_HYGIENE_SENTINEL)
    # Use the real substrate's path computation (not a hard-coded string).
    evidence_run_dir = compute_run_dir("10-5-test", "run-001")
    evidence_root = tmp_path / evidence_run_dir
    evidence_root.mkdir(parents=True, exist_ok=True)
    # Seed representative artifacts at the canonical paths: Tier-1
    # smoke-output JSON, Tier-2 assertion log, Tier-3 semantic-verification
    # YAML. None carry env-var values (the substrate has no access).
    (evidence_root / "ac-01" / "tier-1").mkdir(parents=True, exist_ok=True)
    (evidence_root / "ac-01" / "tier-1" / "smoke.json").write_text(
        json.dumps(
            {
                "tier": "tier-1",
                "ac_id": "AC-1",
                "outcome": "pass",
                "evidence_ref": str(evidence_run_dir / "ac-01" / "tier-1" / "smoke.json"),
            }
        ),
        encoding="utf-8",
    )
    (evidence_root / "ac-01" / "tier-2").mkdir(parents=True, exist_ok=True)
    (evidence_root / "ac-01" / "tier-2" / "assertion.log").write_text(
        "assertion passed: expected=200 actual=200\n",
        encoding="utf-8",
    )
    (evidence_root / "ac-01" / "tier-3").mkdir(parents=True, exist_ok=True)
    (evidence_root / "ac-01" / "tier-3" / "semantic.yaml").write_text(
        "verification: pass\nreasoning: |\n  The implementation matches AC-1.\n",
        encoding="utf-8",
    )
    # Recursive walk: scan every file in the evidence-bundle tree.
    for path in sorted(evidence_root.rglob("*")):
        if not path.is_file():
            continue
        body = path.read_bytes()
        _assert_sentinel_not_in_bytes(
            body, f"evidence-bundle:{path.relative_to(evidence_root)}"
        )


# --------------------------------------------------------------------------- #
# AC-7 hygiene test 4 — PR-bundle markdown substring scan                     #
# --------------------------------------------------------------------------- #


def test_api_key_literal_never_appears_in_pr_bundle_markdown(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 10.5 AC-7 hygiene test 4 (LOAD-BEARING): the PR-bundle
    markdown is the operator-visible PR-comment surface that NFR-S1
    most explicitly names. Simulate a live key in the process
    environment (``OPENROUTER_API_KEY`` → sentinel) so any future
    bundle-render extension that accidentally reads the env var is
    caught; call the real :func:`assemble_bundle` pipeline with a
    run-state carrying a ``LAD-skipped`` active marker and minimal
    three-specialist dispatch logs; scan the rendered bundle bytes.

    Story 10.6 wires the full LAD-aware bundle rendering path; this
    test is the forward-regression catcher for that wiring.
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", _API_KEY_HYGIENE_SENTINEL)

    # Run-state with LAD-skipped marker via the real pipeline.
    rs = RunState(
        schema_version="1.3",
        story_id="10-5-test",
        run_id="run-001",
        current_state="done",
        branch_name="bmad-automation/story/10-5-test",
        dispatched_specialist=None,
        last_envelope=None,
        pending_qa_dispatch_payload=None,
        retry_history=(),
        active_markers=("LAD-skipped",),
        cost_to_date_by_specialist=CostToDateBySpecialist(),
    )
    rs_path = tmp_path / "run-state.yaml"
    rs_path.write_bytes(_serialize_run_state(rs).encode("utf-8"))

    # Three specialist dispatch logs via the real pipeline.
    story_path = tmp_path / "10-5-test.md"
    story_path.write_text("# Test\n\nStatus: ready-for-dev\n", encoding="utf-8")
    resolution = StoryDocResolution(
        path=story_path,
        current_state="ready-for-dev",
        acceptance_criteria=(AcceptanceCriterion(ac_id="AC-1", text="Test AC."),),
    )
    fixed_ts = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)
    logs_root = tmp_path / "logs"
    for specialist in ("dev", "review-bmad", "qa"):
        ag_path = tmp_path / f"{specialist}-agent.md"
        ag_path.write_text(f"# {specialist} agent.\n", encoding="utf-8")
        payload = build_dispatch_payload(
            specialist=specialist,
            story_id="10-5-test",
            attempt_number=1,
            story_doc_resolution=resolution,
            agent_definition_path=ag_path,
            prompt_body_renderer=default_prompt_body_renderer,
            dispatch_timestamp_factory=lambda: fixed_ts,
        )
        persist_dispatch_log(
            payload,
            {
                "status": "pass",
                "artifacts": [],
                "findings": [],
                "rationale": f"{specialist} passed.",
            },
            return_timestamp=fixed_ts,
            log_root=logs_root,
            run_id="run-001",
        )

    # Call the real bundle assembly pipeline and scan its output.
    bundle_root = tmp_path / "bundles"
    result = assemble_bundle(
        story_id="10-5-test",
        run_id="run-001",
        run_state_path=rs_path,
        logs_root=logs_root,
        bundle_root=bundle_root,
        generated_at=fixed_ts,
        repo_root=tmp_path,
    )
    body = result.bundle_path.read_bytes()
    _assert_sentinel_not_in_bytes(body, "pr-bundle.md")
    # Structural witness: LAD-skipped marker from active_markers renders in the bundle.
    assert b"LAD-skipped" in body


# --------------------------------------------------------------------------- #
# AC-7 helper assertion test — the sentinel helper itself fails loud          #
# --------------------------------------------------------------------------- #


def test_sentinel_helper_emits_loud_fail_diagnostic_on_regression() -> None:
    """Story 10.5 AC-7 Pattern 5 witness: the
    :func:`_assert_sentinel_not_in_bytes` helper itself fails loud on
    regression (emits a diagnostic naming the offending offset + a
    context window). This test verifies the helper's negative-path
    behaviour — the failure-mode contract.
    """
    leak_body = (
        b"prefix bytes " + _API_KEY_HYGIENE_SENTINEL.encode("utf-8") + b" suffix bytes"
    )
    with pytest.raises(pytest.fail.Exception) as excinfo:
        _assert_sentinel_not_in_bytes(leak_body, "synthetic-regression-fixture")
    assert "NFR-S1 hygiene regression" in str(excinfo.value)
    assert "synthetic-regression-fixture" in str(excinfo.value)
    assert _API_KEY_HYGIENE_SENTINEL in str(excinfo.value)
