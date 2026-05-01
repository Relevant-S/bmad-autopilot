"""Contract-coverage matrix for the env-provisioning library (Story 4.3).

Mirrors the test-file shape established by ``test_qa_plan_drift.py``
(Story 4.2 — pure-library two-channel atomic emission)
+ ``test_review_layer_failure.py`` (Story 3.3 — three-channel atomic
emission) + ``test_lifecycle_state_machine.py`` (Story 2.4 — substrate
library consumed by the orchestrator skill at the seam).

Test enumeration (Story 4.3 AC-9 — 18 tests):
    1.  test_allocate_ephemeral_port_returns_valid_tcp_port
    2.  test_allocate_ephemeral_port_consecutive_calls
    3.  test_provision_env_happy_path
    4.  test_provision_env_provisioner_failure_routes_to_surface_env_setup_failure
    5.  test_teardown_env_happy_path
    6.  test_teardown_env_does_not_touch_evidence_root
    7.  test_cleanup_orphan_processes_happy_path
    8.  test_cleanup_orphan_processes_empty_probe
    9.  test_cleanup_orphan_processes_atomic_on_registry_rejection
    10. test_surface_env_setup_failure_with_canonical_registry
    11. test_surface_env_setup_failure_atomic_on_registry_rejection
    12. test_run_state_schema_accepts_populated_provisioned_env_field
    13. test_run_state_schema_rejects_malformed_provisioned_env_field
    14. test_env_provisioning_fixtures_validate_against_event_schema
    15. test_orchestrator_remains_in_review_on_env_provisioning_failed
    16. test_env_provisioning_module_has_lf_line_endings
    17. test_env_provisioning_module_all_exports
    18. test_step_file_env_provisioning_md_exists_with_required_sections
"""

from __future__ import annotations

import pathlib
import time
import unittest.mock
from datetime import datetime, timezone
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from loud_fail_harness import env_provisioning
from loud_fail_harness._shared import find_repo_root, load_schema
from loud_fail_harness.env_provisioning import (
    ENV_SETUP_FAILED_MARKER,
    ORPHAN_PROCESS_CLEANUP_MARKER,
    EnvProvisioningFailed,
    EnvSetupFailureDiagnostic,
    EnvSetupFailureEmission,
    NoOpProvisioner,
    ProvisionedEnv,
    allocate_ephemeral_port,
    cleanup_orphan_processes,
    provision_env,
    surface_env_setup_failure,
    teardown_env,
)
from loud_fail_harness.event_validator import validate_event
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
    load_marker_class_registry,
)


# --------------------------------------------------------------------------- #
# Fixtures (resolution at fixture-time only — Epic 1 retro Action #1)         #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def repo_root() -> pathlib.Path:
    """Module-scoped repo-root fixture (Epic 1 retro Action #1: never call
    ``find_repo_root`` at module top-level)."""
    return find_repo_root()


@pytest.fixture(scope="module")
def event_schema(repo_root: pathlib.Path) -> dict[str, Any]:
    """Module-scoped orchestrator-event schema."""
    return load_schema(repo_root / "schemas" / "orchestrator-event.yaml")


@pytest.fixture(scope="module")
def run_state_schema(repo_root: pathlib.Path) -> dict[str, Any]:
    """Module-scoped run-state schema (post-Story-4.3 bump)."""
    return load_schema(repo_root / "schemas" / "run-state.yaml")


@pytest.fixture(scope="module")
def envelope_schema(repo_root: pathlib.Path) -> dict[str, Any]:
    """Module-scoped envelope schema (referenced by run-state via $ref)."""
    return load_schema(repo_root / "schemas" / "envelope.schema.yaml")


@pytest.fixture(scope="module")
def tea_handoff_schema(repo_root: pathlib.Path) -> dict[str, Any]:
    """Module-scoped TEA handoff schema (referenced by run-state via $ref)."""
    return load_schema(repo_root / "schemas" / "tea-handoff-contract.yaml")


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    """Module-scoped registry loaded from the canonical taxonomy."""
    return load_marker_class_registry()


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _canonical_env_setup_failed_registry() -> MarkerClassRegistry:
    """Registry containing exactly the ``env-setup-failed`` marker class.

    Test surface independent of the on-disk taxonomy per Story 1.4's
    enumeration test discipline.
    """
    return MarkerClassRegistry(
        marker_classes=frozenset({ENV_SETUP_FAILED_MARKER})
    )


def _canonical_orphan_cleanup_registry() -> MarkerClassRegistry:
    """Registry containing exactly the ``orphan-process-cleanup`` marker class."""
    return MarkerClassRegistry(
        marker_classes=frozenset({ORPHAN_PROCESS_CLEANUP_MARKER})
    )


def _seed_run_state(
    run_state_path: pathlib.Path,
    *,
    story_id: str = "story-4-3-test",
    current_state: str = "review",
) -> None:
    """Seed a minimal run-state YAML at ``run_state_path`` matching the
    Story 2.2 schema's required field set.

    The seed mirrors the run-state.yaml schema's required fields per
    AC-1's enumeration. The ``provisioned_env`` field is intentionally
    absent to mirror the typical pre-provisioning state.
    """
    data = {
        "schema_version": "1.1",
        "story_id": story_id,
        "run_id": "run-4-3-test-0001",
        "current_state": current_state,
        "branch_name": "story/4-3-test",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": [],
        "active_markers": [],
        "cost_to_date_by_specialist": {},
    }
    run_state_path.write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )


def _read_run_state_dict(run_state_path: pathlib.Path) -> dict[str, Any]:
    """Read run-state.yaml and return the dict body."""
    raw = yaml.safe_load(run_state_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _make_collector_appender() -> tuple[list[dict[str, Any]], Any]:
    """Build a deterministic event-log appender that collects events
    in-memory for assertion."""
    collected: list[dict[str, Any]] = []

    def appender(event: dict[str, Any]) -> None:
        collected.append(event)

    return collected, appender


class _RaisingProvisioner:
    """Provisioner that always raises a custom exception with a
    ``failure_step`` attribute for the exception-routing path test."""

    def __init__(self, *, failure_step: str = "port-bind-failed") -> None:
        self._failure_step = failure_step

    def provision(
        self,
        story_id: str,
        project_type: str,
        port: int,
    ) -> ProvisionedEnv:
        exc = RuntimeError(
            f"port {port} bound by stale process; cannot launch dev server"
        )
        # Attribute mirrored on the exception per provision_env's getattr
        # contract.
        exc.failure_step = self._failure_step  # type: ignore[attr-defined]
        raise exc


class _RecordingTeardown:
    """Teardown impl that records invocations for assertion."""

    def __init__(self) -> None:
        self.calls: list[ProvisionedEnv] = []

    def teardown(self, provisioned_env: ProvisionedEnv) -> None:
        self.calls.append(provisioned_env)


class _StaticOrphanProbe:
    """OrphanProbe returning a fixed list of (port, pid) pairs."""

    def __init__(self, orphans: tuple[tuple[int, int], ...]) -> None:
        self._orphans = orphans

    def probe(self) -> tuple[tuple[int, int], ...]:
        return self._orphans


class _RecordingOrphanTerminator:
    """OrphanTerminator that records every (port, pid) call."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def terminate(self, port: int, pid: int) -> None:
        self.calls.append((port, pid))


def _build_run_state_validator(
    run_state_schema: dict[str, Any],
    envelope_schema: dict[str, Any],
    tea_handoff_schema: dict[str, Any],
) -> Draft202012Validator:
    """Build a Draft 2020-12 validator with a $ref registry for the
    envelope + tea-handoff sub-schemas (mirrors the canonical pattern
    from `test_run_state.py`)."""
    registry = Registry().with_resources(
        [
            (
                "envelope.schema.yaml",
                Resource(contents=envelope_schema, specification=DRAFT202012),
            ),
            (
                "tea-handoff-contract.yaml",
                Resource(
                    contents=tea_handoff_schema, specification=DRAFT202012
                ),
            ),
        ]
    )
    return Draft202012Validator(run_state_schema, registry=registry)


# --------------------------------------------------------------------------- #
# AC-2 — allocate_ephemeral_port                                              #
# --------------------------------------------------------------------------- #


# 1
def test_allocate_ephemeral_port_returns_valid_tcp_port() -> None:
    """AC-2 + AC-9 #1 — returned int is in [1, 65535]; > 1023 (above the
    privileged-port range; OS-empirical assertion)."""
    port = allocate_ephemeral_port()
    assert 1 <= port <= 65535
    # OS empirically returns a port above the privileged range; THIS
    # function trusts the OS, but the test verifies the empirical
    # invariant that the OS does in fact stay above the reserved range.
    assert port > 1023


# 2
def test_allocate_ephemeral_port_consecutive_calls() -> None:
    """AC-9 #2 — two consecutive calls return distinct ports OR may
    document same-port-returnable behavior per OS-portability discipline.

    On POSIX systems the kernel typically rotates through its ephemeral
    range; immediate re-use of the just-released port is rare but legal.
    The test asserts both calls return valid ephemeral ports and
    documents the OS-portability behavior in the test name + assertion.
    """
    port_a = allocate_ephemeral_port()
    port_b = allocate_ephemeral_port()
    # Both calls return valid ephemeral ports.
    assert 1024 < port_a <= 65535
    assert 1024 < port_b <= 65535
    # The OS-portability discipline: distinctness is typical but not
    # guaranteed. If they ARE distinct, that's the typical Linux/macOS
    # behavior. If they're equal, that's the legal-but-rare same-port-
    # immediately-after-close path. Either is acceptable per AC-2's
    # documented race-condition window.
    assert isinstance(port_a, int) and isinstance(port_b, int)


# --------------------------------------------------------------------------- #
# AC-3 — provision_env                                                        #
# --------------------------------------------------------------------------- #


# 3
def test_provision_env_happy_path(tmp_path: pathlib.Path) -> None:
    """AC-9 #3 — `provision_env` with `NoOpProvisioner`: run-state's
    `provisioned_env` field is populated; one `env-provisioned` event
    is emitted."""
    run_state_path = tmp_path / "run-state.yaml"
    _seed_run_state(run_state_path, story_id="story-4-3-happy")
    registry = _canonical_env_setup_failed_registry()
    collected, appender = _make_collector_appender()
    fixed_now = datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc)

    provisioned = provision_env(
        story_id="story-4-3-happy",
        project_type="web",
        provisioner=NoOpProvisioner(),
        port=51234,
        run_state_path=run_state_path,
        registry=registry,
        event_appender=appender,
        timestamp_factory=lambda: fixed_now,
    )

    # Run-state's provisioned_env field is populated with the four required fields.
    state = _read_run_state_dict(run_state_path)
    assert "provisioned_env" in state
    pe = state["provisioned_env"]
    assert pe["env_kind"] == "web"
    assert pe["port"] == 51234
    assert pe["pid"] == NoOpProvisioner._DUMMY_PID
    assert "started_at" in pe

    # One env-provisioned event was appended.
    assert len(collected) == 1
    event = collected[0]
    assert event["event_class"] == "env-provisioned"
    assert event["env_kind"] == "web"
    assert event["port"] == 51234
    assert event["pid"] == NoOpProvisioner._DUMMY_PID
    assert event["story_id"] == "story-4-3-happy"

    # Sanity: provisioner's return value is also returned.
    assert isinstance(provisioned, ProvisionedEnv)
    assert provisioned.env_kind == "web"
    assert provisioned.port == 51234


# 4
def test_provision_env_provisioner_failure_routes_to_surface_env_setup_failure(
    tmp_path: pathlib.Path,
) -> None:
    """AC-9 #4 — provisioner that raises with `failure_step="port-bind-failed"`:
    EnvProvisioningFailed is raised; emission carries the canonical marker
    class + sub_cause; run-state is NOT mutated; event log is empty."""
    run_state_path = tmp_path / "run-state.yaml"
    _seed_run_state(run_state_path, story_id="story-4-3-fail")
    registry = _canonical_env_setup_failed_registry()
    collected, appender = _make_collector_appender()

    raising_provisioner = _RaisingProvisioner(failure_step="port-bind-failed")

    with pytest.raises(EnvProvisioningFailed) as excinfo:
        provision_env(
            story_id="story-4-3-fail",
            project_type="web",
            provisioner=raising_provisioner,  # type: ignore[arg-type]
            port=51234,
            run_state_path=run_state_path,
            registry=registry,
            event_appender=appender,
        )

    emission = excinfo.value.emission
    assert emission.marker_record.marker_class == "env-setup-failed"
    assert emission.marker_record.sub_cause == "port-bind-failed"
    assert emission.diagnostic.story_id == "story-4-3-fail"
    assert emission.diagnostic.project_type == "web"
    assert emission.diagnostic.failure_step == "port-bind-failed"

    # Run-state's provisioned_env field is NOT populated (atomic-on-failure).
    state = _read_run_state_dict(run_state_path)
    assert "provisioned_env" not in state

    # Event log carries NO env-provisioned event (atomic-on-failure).
    assert collected == []


# --------------------------------------------------------------------------- #
# AC-4 — teardown_env                                                         #
# --------------------------------------------------------------------------- #


# 5
def test_teardown_env_happy_path(tmp_path: pathlib.Path) -> None:
    """AC-9 #5 — `teardown_env` with a no-op Teardown: teardown is
    invoked exactly once; run-state's provisioned_env is cleared; one
    `env-torn-down` event with `outcome="clean"` is emitted."""
    run_state_path = tmp_path / "run-state.yaml"
    _seed_run_state(run_state_path, story_id="story-4-3-teardown")

    # Pre-populate the provisioned_env field as if provision_env had run.
    pe_state = _read_run_state_dict(run_state_path)
    pe_state["provisioned_env"] = {
        "env_kind": "web",
        "port": 51234,
        "pid": 99999,
        "started_at": "2026-04-30T10:00:00+00:00",
    }
    run_state_path.write_text(
        yaml.safe_dump(pe_state, sort_keys=False), encoding="utf-8"
    )

    registry = _canonical_env_setup_failed_registry()
    collected, appender = _make_collector_appender()
    teardown_fn = _RecordingTeardown()
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    fixed_now = datetime(2026, 4, 30, 10, 5, 0, tzinfo=timezone.utc)

    pe = ProvisionedEnv(
        env_kind="web",
        port=51234,
        pid=99999,
        started_at=datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc),
    )

    teardown_env(
        provisioned_env=pe,
        teardown_fn=teardown_fn,  # type: ignore[arg-type]
        run_state_path=run_state_path,
        evidence_root=evidence_root,
        registry=registry,
        event_appender=appender,
        story_id="story-4-3-teardown",
        timestamp_factory=lambda: fixed_now,
    )

    # Teardown invoked exactly once with the same provisioned env.
    assert len(teardown_fn.calls) == 1
    assert teardown_fn.calls[0] == pe

    # Run-state's provisioned_env field is cleared (key removed per the
    # dev's-call YAML idiom recorded in extension-audit.md).
    state = _read_run_state_dict(run_state_path)
    assert "provisioned_env" not in state

    # One env-torn-down event with outcome="clean" was emitted.
    assert len(collected) == 1
    event = collected[0]
    assert event["event_class"] == "env-torn-down"
    assert event["outcome"] == "clean"
    assert event["env_kind"] == "web"
    assert event["story_id"] == "story-4-3-teardown"


# 6
def test_teardown_env_does_not_touch_evidence_root(
    tmp_path: pathlib.Path,
) -> None:
    """AC-9 #6 — sentinel file at evidence_root has byte-for-byte
    unchanged content + mtime after teardown_env. The verbatim epic AC
    at epics.md line 1872 invariant: 'evidence already captured by QA
    is preserved'."""
    run_state_path = tmp_path / "run-state.yaml"
    _seed_run_state(run_state_path)

    # Pre-populate provisioned_env so teardown has something to clear.
    pe_state = _read_run_state_dict(run_state_path)
    pe_state["provisioned_env"] = {
        "env_kind": "web",
        "port": 51234,
        "pid": 99999,
        "started_at": "2026-04-30T10:00:00+00:00",
    }
    run_state_path.write_text(
        yaml.safe_dump(pe_state, sort_keys=False), encoding="utf-8"
    )

    # Sentinel file in the evidence root with known content + mtime.
    evidence_root = tmp_path / "evidence" / "story-4-3-test" / "run-0001"
    evidence_root.mkdir(parents=True)
    sentinel = evidence_root / "ac-1-screenshot.png"
    sentinel_content = b"\x89PNG\r\n\x1a\n--captured-by-QA"
    sentinel.write_bytes(sentinel_content)
    expected_mtime_ns = sentinel.stat().st_mtime_ns

    # Sleep briefly so any accidental write would be detectable via mtime.
    time.sleep(0.01)

    pe = ProvisionedEnv(
        env_kind="web",
        port=51234,
        pid=99999,
        started_at=datetime(2026, 4, 30, 10, 0, 0, tzinfo=timezone.utc),
    )
    _, appender = _make_collector_appender()

    teardown_env(
        provisioned_env=pe,
        teardown_fn=_RecordingTeardown(),  # type: ignore[arg-type]
        run_state_path=run_state_path,
        evidence_root=evidence_root,
        registry=_canonical_env_setup_failed_registry(),
        event_appender=appender,
        story_id="story-4-3-test",
    )

    # Sentinel file's content + mtime are byte-for-byte unchanged.
    assert sentinel.read_bytes() == sentinel_content
    assert sentinel.stat().st_mtime_ns == expected_mtime_ns


# --------------------------------------------------------------------------- #
# AC-5 — cleanup_orphan_processes                                             #
# --------------------------------------------------------------------------- #


# 7
def test_cleanup_orphan_processes_happy_path(tmp_path: pathlib.Path) -> None:
    """AC-9 #7 — orphan_probe returns two (port, pid) pairs;
    orphan_terminator.terminate is invoked twice; two MarkerEmissionRecord
    are returned with marker_class='orphan-process-cleanup'; ONE
    env-torn-down sweep summary event is emitted."""
    run_state_path = tmp_path / "run-state.yaml"
    _seed_run_state(run_state_path)

    registry = _canonical_orphan_cleanup_registry()
    collected, appender = _make_collector_appender()
    probe = _StaticOrphanProbe(orphans=((51234, 99999), (51235, 99998)))
    terminator = _RecordingOrphanTerminator()

    emissions = cleanup_orphan_processes(
        run_state_path=run_state_path,
        orphan_probe=probe,  # type: ignore[arg-type]
        orphan_terminator=terminator,  # type: ignore[arg-type]
        registry=registry,
        event_appender=appender,
        story_id="story-4-3-orphans",
        env_kind="web",
    )

    # Terminator invoked once per orphan in probe order.
    assert terminator.calls == [(51234, 99999), (51235, 99998)]

    # Two MarkerEmissionRecord returned with the canonical class.
    assert len(emissions) == 2
    assert all(
        rec.marker_class == "orphan-process-cleanup" for rec in emissions
    )
    assert emissions[0].context["port"] == 51234
    assert emissions[0].context["pid"] == 99999
    assert emissions[1].context["port"] == 51235
    assert emissions[1].context["pid"] == 99998

    # Single sweep-summary env-torn-down event (NOT one per orphan).
    env_torn_down = [
        e for e in collected if e["event_class"] == "env-torn-down"
    ]
    assert len(env_torn_down) == 1
    assert env_torn_down[0]["outcome"] == "orphan-process-cleanup"


# 8
def test_cleanup_orphan_processes_empty_probe(tmp_path: pathlib.Path) -> None:
    """AC-9 #8 — empty probe: zero terminator calls, zero markers, zero
    events; function returns an empty tuple."""
    run_state_path = tmp_path / "run-state.yaml"
    _seed_run_state(run_state_path)

    registry = _canonical_orphan_cleanup_registry()
    collected, appender = _make_collector_appender()
    probe = _StaticOrphanProbe(orphans=())
    terminator = _RecordingOrphanTerminator()

    emissions = cleanup_orphan_processes(
        run_state_path=run_state_path,
        orphan_probe=probe,  # type: ignore[arg-type]
        orphan_terminator=terminator,  # type: ignore[arg-type]
        registry=registry,
        event_appender=appender,
        story_id="story-4-3-empty",
        env_kind="web",
    )

    assert emissions == ()
    assert terminator.calls == []
    assert collected == []


# 9
def test_cleanup_orphan_processes_atomic_on_registry_rejection(
    tmp_path: pathlib.Path,
) -> None:
    """AC-9 #9 — registry without 'orphan-process-cleanup' raises
    UnknownMarkerClass BEFORE any side effect: no terminator calls, no
    markers, no events."""
    run_state_path = tmp_path / "run-state.yaml"
    _seed_run_state(run_state_path)

    empty_registry = MarkerClassRegistry(marker_classes=frozenset())
    collected, appender = _make_collector_appender()
    probe = _StaticOrphanProbe(orphans=((51234, 99999),))
    terminator = _RecordingOrphanTerminator()

    with pytest.raises(UnknownMarkerClass):
        cleanup_orphan_processes(
            run_state_path=run_state_path,
            orphan_probe=probe,  # type: ignore[arg-type]
            orphan_terminator=terminator,  # type: ignore[arg-type]
            registry=empty_registry,
            event_appender=appender,
            story_id="story-4-3-rejected",
            env_kind="web",
        )

    # Atomic-on-failure: no terminator calls, no markers constructed, no
    # events emitted.
    assert terminator.calls == []
    assert collected == []


# --------------------------------------------------------------------------- #
# AC-1 — surface_env_setup_failure                                            #
# --------------------------------------------------------------------------- #


# 10
def test_surface_env_setup_failure_with_canonical_registry(
    runtime_marker_registry: MarkerClassRegistry,
) -> None:
    """AC-9 #10 — surface_env_setup_failure with the canonical registry
    returns a successful EnvSetupFailureEmission with the five-field
    diagnostic + the marker_record carrying the canonical marker class."""
    result = surface_env_setup_failure(
        story_id="story-4-3-canonical",
        project_type="web",
        failure_step="playwright-launch-failed",
        failure_diagnostic="Playwright MCP server not reachable on stdin",
        qa_runbook_pointer="_bmad/automation/qa-runbook.yaml",
        registry=runtime_marker_registry,
    )

    assert isinstance(result, EnvSetupFailureEmission)
    assert result.marker_record.marker_class == "env-setup-failed"
    assert result.marker_record.sub_cause in (
        "port-bind-failed",
        "playwright-launch-failed",
        "dev-server-not-ready",
    )
    assert result.marker_record.sub_cause == "playwright-launch-failed"

    diag = result.diagnostic
    assert isinstance(diag, EnvSetupFailureDiagnostic)
    assert diag.story_id == "story-4-3-canonical"
    assert diag.project_type == "web"
    assert diag.failure_step == "playwright-launch-failed"
    assert diag.failure_diagnostic.startswith("Playwright")
    assert diag.qa_runbook_pointer == "_bmad/automation/qa-runbook.yaml"


# 11
def test_surface_env_setup_failure_atomic_on_registry_rejection() -> None:
    """AC-9 #11 — registry without 'env-setup-failed' raises
    UnknownMarkerClass; no partial emission constructed."""
    empty_registry = MarkerClassRegistry(marker_classes=frozenset())

    with pytest.raises(UnknownMarkerClass):
        surface_env_setup_failure(
            story_id="story-4-3-rejected",
            project_type="api",
            failure_step="dev-server-not-ready",
            failure_diagnostic="HTTP server did not bind to localhost:51235",
            qa_runbook_pointer="_bmad/automation/qa-runbook.yaml",
            registry=empty_registry,
        )


# --------------------------------------------------------------------------- #
# AC-6 — run-state schema bump                                                #
# --------------------------------------------------------------------------- #


# 12
def test_run_state_schema_accepts_populated_provisioned_env_field(
    run_state_schema: dict[str, Any],
    envelope_schema: dict[str, Any],
    tea_handoff_schema: dict[str, Any],
) -> None:
    """AC-9 #12 — positive case for AC-6: run-state with non-null
    provisioned_env validates against the bumped schema."""
    validator = _build_run_state_validator(
        run_state_schema, envelope_schema, tea_handoff_schema
    )
    state = {
        "schema_version": "1.1",
        "story_id": "story-4-3-positive",
        "run_id": "run-positive-0001",
        "current_state": "review",
        "branch_name": "story/4-3-positive",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": [],
        "active_markers": [],
        "cost_to_date_by_specialist": {},
        "provisioned_env": {
            "env_kind": "web",
            "port": 51234,
            "pid": 99999,
            "started_at": "2026-04-30T10:00:00+00:00",
        },
    }
    errors = list(validator.iter_errors(state))
    assert errors == []


# 13
def test_run_state_schema_rejects_malformed_provisioned_env_field(
    run_state_schema: dict[str, Any],
    envelope_schema: dict[str, Any],
    tea_handoff_schema: dict[str, Any],
) -> None:
    """AC-9 #13 — negative case for AC-6: run-state with malformed
    provisioned_env (extra unknown field) fails validation per
    `additionalProperties: false`."""
    validator = _build_run_state_validator(
        run_state_schema, envelope_schema, tea_handoff_schema
    )
    state = {
        "schema_version": "1.1",
        "story_id": "story-4-3-negative",
        "run_id": "run-negative-0001",
        "current_state": "review",
        "branch_name": "story/4-3-negative",
        "dispatched_specialist": None,
        "last_envelope": None,
        "pending_qa_dispatch_payload": None,
        "retry_history": [],
        "active_markers": [],
        "cost_to_date_by_specialist": {},
        "provisioned_env": {
            "env_kind": "web",
            "port": 51234,
            "pid": 99999,
            "started_at": "2026-04-30T10:00:00+00:00",
            "unexpected_field": "should-be-rejected",
        },
    }
    errors = list(validator.iter_errors(state))
    assert errors != []

    # Negative case 2: missing port (required field).
    state["provisioned_env"] = {
        "env_kind": "web",
        "pid": 99999,
        "started_at": "2026-04-30T10:00:00+00:00",
    }
    errors_missing = list(validator.iter_errors(state))
    assert errors_missing != []


# --------------------------------------------------------------------------- #
# AC-8 — canonical event fixtures                                             #
# --------------------------------------------------------------------------- #


# 14
def test_env_provisioning_fixtures_validate_against_event_schema(
    repo_root: pathlib.Path,
    event_schema: dict[str, Any],
) -> None:
    """AC-9 #14 — each of the four AC-8 fixtures validates via Story 1.3's
    `validate_event`."""
    fixtures_dir = repo_root / "examples" / "orchestrator-events"
    expected = [
        "env-provisioned-web.yaml",
        "env-provisioned-api.yaml",
        "env-torn-down-clean.yaml",
        "env-torn-down-orphan-cleanup.yaml",
    ]
    for fixture_name in expected:
        fixture_path = fixtures_dir / fixture_name
        assert fixture_path.exists(), f"missing fixture: {fixture_name}"
        event = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
        errors = validate_event(event, event_schema)
        assert errors == [], f"{fixture_name} failed validation: {errors}"


# --------------------------------------------------------------------------- #
# AC-7 — orchestrator preserves current_state="review" on env-setup-fail      #
# --------------------------------------------------------------------------- #


# 15
def test_orchestrator_remains_in_review_on_env_provisioning_failed(
    tmp_path: pathlib.Path,
) -> None:
    """AC-9 #15 — integration-level: a provisioner that raises causes
    EnvProvisioningFailed; current_state REMAINS at 'review'; no state
    transition occurs; the env-setup-failed marker is surfaced in the
    emission."""
    run_state_path = tmp_path / "run-state.yaml"
    _seed_run_state(
        run_state_path, story_id="story-4-3-stays-review", current_state="review"
    )
    registry = _canonical_env_setup_failed_registry()
    collected, appender = _make_collector_appender()

    raising_provisioner = _RaisingProvisioner(failure_step="dev-server-not-ready")

    with unittest.mock.patch(
        "loud_fail_harness.lifecycle_state_machine.commit_transition"
    ) as mock_commit, pytest.raises(EnvProvisioningFailed) as excinfo:
        provision_env(
            story_id="story-4-3-stays-review",
            project_type="api",
            provisioner=raising_provisioner,  # type: ignore[arg-type]
            port=51234,
            run_state_path=run_state_path,
            registry=registry,
            event_appender=appender,
        )

    # commit_transition MUST NOT have been called on the failure path.
    mock_commit.assert_not_called()

    # current_state REMAINS at 'review' (NEVER advances to 'qa').
    state = _read_run_state_dict(run_state_path)
    assert state["current_state"] == "review"

    # provisioned_env field is NOT populated.
    assert "provisioned_env" not in state

    # No env-provisioned event was appended.
    assert collected == []

    # The env-setup-failed marker is surfaced in the emission.
    emission = excinfo.value.emission
    assert emission.marker_record.marker_class == "env-setup-failed"


# --------------------------------------------------------------------------- #
# Discipline tests                                                            #
# --------------------------------------------------------------------------- #


# 16
def test_env_provisioning_module_has_lf_line_endings(
    repo_root: pathlib.Path,
) -> None:
    """AC-9 #16 — no `\\r` characters in env_provisioning.py source bytes
    (parallel to the cross-story discipline test from Stories 2.8 / 2.9 /
    3.5 / 4.1 / 4.2)."""
    module_path = (
        repo_root
        / "tools"
        / "loud-fail-harness"
        / "src"
        / "loud_fail_harness"
        / "env_provisioning.py"
    )
    raw = module_path.read_bytes()
    assert b"\r" not in raw


# 17
def test_env_provisioning_module_all_exports() -> None:
    """AC-9 #17 — env_provisioning.__all__ contains at minimum the
    public-API symbols enumerated in AC-1."""
    expected_symbols = {
        "ProvisionedEnv",
        "EnvSetupFailureDiagnostic",
        "EnvSetupFailureEmission",
        "EnvSetupFailureSubCause",
        "EnvProvisioningFailed",
        "Provisioner",
        "Teardown",
        "OrphanProbe",
        "OrphanTerminator",
        "NoOpProvisioner",
        "allocate_ephemeral_port",
        "provision_env",
        "teardown_env",
        "cleanup_orphan_processes",
        "surface_env_setup_failure",
        "ENV_SETUP_FAILED_MARKER",
        "ORPHAN_PROCESS_CLEANUP_MARKER",
    }
    actual = set(env_provisioning.__all__)
    missing = expected_symbols - actual
    assert missing == set(), f"missing __all__ exports: {missing}"


# 18
def test_step_file_env_provisioning_md_exists_with_required_sections(
    repo_root: pathlib.Path,
) -> None:
    """AC-9 #18 — steps/env-provisioning.md exists with the seven
    structural section headings; LF line endings."""
    step_file = (
        repo_root
        / "skills"
        / "bmad-automation"
        / "steps"
        / "env-provisioning.md"
    )
    assert step_file.exists(), f"missing step file: {step_file}"

    raw = step_file.read_bytes()
    assert b"\r" not in raw, "step file must use LF line endings"

    text = raw.decode("utf-8")
    required_sections = [
        "# Step: Env provisioning",
        "## Purpose",
        "## Pre-condition",
        "## Procedure",
        "## Failure mode — env-setup-fail",
        "## Composed substrate primitives",
        "## Forward consumers",
    ]
    for heading in required_sections:
        assert heading in text, f"step file missing section: {heading!r}"

    # The Procedure section names each composed primitive by symbol name.
    for symbol in (
        "cleanup_orphan_processes",
        "allocate_ephemeral_port",
        "provision_env",
        "teardown_env",
        "surface_env_setup_failure",
    ):
        assert symbol in text, f"step file missing primitive: {symbol}"
