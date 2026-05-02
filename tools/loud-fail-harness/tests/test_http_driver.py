"""Contract-coverage matrix for the HTTP api-driver library
(Story 4.5).

Mirrors the test-file shape established by ``test_playwright_driver.py``
(Story 4.4), ``test_env_provisioning.py`` (Story 4.3), and
``test_qa_plan_drift.py`` (Story 4.2).

Test enumeration (Story 4.5 AC-9 — 22+ tests):
    1.  test_http_provisioner_satisfies_provisioner_protocol
    2.  test_http_provisioner_provision_happy_path
    3.  test_http_provisioner_raises_api_server_not_ready_on_probe_false
    4.  test_http_provisioner_cleans_up_orphan_pid_on_probe_false
    5.  test_http_provisioner_routes_through_env_provisioning_provision_env
    6a. test_http_teardown_satisfies_teardown_protocol
    6b. test_http_teardown_sigterm_then_clean_exit
    6c. test_http_teardown_sigkill_on_bounded_wait_expiry
    6d. test_http_teardown_process_already_gone_on_sigterm
    7.  test_api_driver_protocol_is_runtime_checkable
    8.  test_http_response_and_api_assertion_record_shapes
    9.  test_verify_ac_envelope_projection_round_trip
    10. test_verify_ac_pass_path
    11. test_verify_ac_fail_path
    12. test_verify_ac_blocked_on_driver_exception
    13. test_verify_ac_reraises_api_service_broken
    14. test_api_service_broken_carries_failure_step_and_diagnostic
    15. test_masked_selector_policy_redacts_authorization_header
    16. test_masked_selector_policy_redacts_json_body_field
    17. test_masked_selector_policy_empty_no_redaction
    18. test_http_driver_fixtures_validate_against_envelope_schema
    19. test_http_driver_module_has_lf_line_endings
    20. test_http_driver_module_all_exports
    21. test_step_file_qa_driver_http_md_exists_with_required_sections
    22. test_http_driver_module_pluggability_clean
"""

from __future__ import annotations

import copy
import pathlib
import signal
import unittest.mock as mock
from datetime import datetime, timezone
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from loud_fail_harness import http_driver
from loud_fail_harness._shared import find_repo_root, load_schema
from loud_fail_harness.env_provisioning import (
    EnvProvisioningFailed,
    Provisioner,
    ProvisionedEnv,
    Teardown,
    provision_env,
)
from loud_fail_harness.http_driver import (
    API_SERVER_NOT_READY_STEP,
    ApiAssertion,
    ApiAvailabilityProbe,
    ApiDriver,
    ApiServerNotReady,
    ApiServerRunner,
    ApiServiceBroken,
    HttpClient,
    HttpProvisioner,
    HttpResponse,
    HttpTeardown,
    NetworkTraceRecord,
    NoOpApiAvailabilityProbe,
    NoOpApiDriver,
    NoOpApiServerRunner,
    NoOpHttpClient,
    _apply_api_masked_selector_policy,
    verify_ac,
)
from loud_fail_harness.playwright_driver import (
    MASKED_REDACTION_SENTINEL,
    MaskedSelectorPolicy,
    NoOpEvidenceCapturer,
)
from loud_fail_harness.qa_behavioral_plan import QABehavioralPlanEntry
from loud_fail_harness.specialist_dispatch import MarkerClassRegistry


# --------------------------------------------------------------------------- #
# Fixtures (resolution at fixture-time only — Epic 1 retro Action #1)         #
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def repo_root() -> pathlib.Path:
    """Module-scoped repo-root fixture (Epic 1 retro Action #1: never call
    ``find_repo_root`` at module top-level)."""
    return find_repo_root()


@pytest.fixture(scope="module")
def envelope_schema(repo_root: pathlib.Path) -> dict[str, Any]:
    """Module-scoped envelope schema."""
    return load_schema(repo_root / "schemas" / "envelope.schema.yaml")


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _canonical_env_setup_failed_registry() -> MarkerClassRegistry:
    """Registry containing exactly the ``env-setup-failed`` marker class
    (consumed by the integration-level routing test).
    """
    return MarkerClassRegistry(marker_classes=frozenset({"env-setup-failed"}))


def _make_plan_entry(
    *,
    ac_id: str = "AC-1",
    assertion_shape: str = "verify: AC-1 returns 200 with expected body",
) -> QABehavioralPlanEntry:
    """Build a deterministic plan entry for verify_ac tests."""
    return QABehavioralPlanEntry(
        ac_id=ac_id,
        assertion_shape=assertion_shape,
        expected_evidence_tier="tier-1-mechanical",
        semantic_verification_requirement="not_applicable",
        heuristic_applicability=(),
    )


def _make_ac_result_validator(
    envelope_schema: dict[str, Any],
) -> Draft202012Validator:
    """Build a Draft 2020-12 validator scoped to the ``$defs/ac_result``
    sub-schema (mirrors `test_playwright_driver.py`'s helper byte-for-byte).

    Story 4.8: ``$defs/ac_result.evidence_refs.items`` references
    ``#/$defs/evidence_ref`` which lives at the parent envelope-schema's
    ``$defs`` level. The scoped sub-schema gets a ``$defs`` sibling
    inlined from the parent so the relative ``$ref`` resolves locally.
    """
    registry = Registry().with_resources(
        [
            (
                "envelope.schema.yaml",
                Resource(contents=envelope_schema, specification=DRAFT202012),
            ),
        ]
    )
    ac_result_schema = dict(envelope_schema["$defs"]["ac_result"])
    ac_result_schema["$defs"] = copy.deepcopy(envelope_schema["$defs"])
    return Draft202012Validator(ac_result_schema, registry=registry)


class _RaisingApiDriver:
    """ApiDriver impl whose driver action raises a non-ApiServiceBroken
    exception (consumed by the blocked-status test).
    """

    def request(
        self,
        method: str,
        url: str,
        **_: Any,
    ) -> HttpResponse:
        del method, url
        raise RuntimeError("simulated mid-run driver error (NOT api-service-broken)")

    def assert_status(
        self, response: HttpResponse, expected: int
    ) -> ApiAssertion:
        del response, expected
        return ApiAssertion(passed=True, observed="", expected="", kind="status")

    def assert_body(
        self, response: HttpResponse, expected: Any
    ) -> ApiAssertion:
        del response, expected
        return ApiAssertion(passed=True, observed="", expected="", kind="body")

    def assert_header(
        self, response: HttpResponse, name: str, expected: str
    ) -> ApiAssertion:
        del response, name, expected
        return ApiAssertion(passed=True, observed="", expected="", kind="header")

    def inspect_network_trace(self) -> tuple[NetworkTraceRecord, ...]:
        return ()


class _IncompleteApiDriver:
    """A class missing one ApiDriver method — used by the negative
    runtime_checkable assertion to verify the protocol catches missing
    methods.
    """

    def request(
        self,
        method: str,
        url: str,
        **_: Any,
    ) -> HttpResponse:
        del method, url
        return HttpResponse(status=200, headers=(), body="")

    def assert_status(
        self, response: HttpResponse, expected: int
    ) -> ApiAssertion:
        del response, expected
        return ApiAssertion(passed=True, observed="", expected="", kind="status")

    def assert_body(
        self, response: HttpResponse, expected: Any
    ) -> ApiAssertion:
        del response, expected
        return ApiAssertion(passed=True, observed="", expected="", kind="body")

    # Missing assert_header + inspect_network_trace on purpose.


# --------------------------------------------------------------------------- #
# AC-2 — HttpProvisioner.provision                                            #
# --------------------------------------------------------------------------- #


# 1
def test_http_provisioner_satisfies_provisioner_protocol() -> None:
    """AC-9 #1 — `HttpProvisioner` structurally satisfies Story 4.3's
    `Provisioner` Protocol (`@runtime_checkable`).
    """
    provisioner = HttpProvisioner(
        NoOpApiAvailabilityProbe(available=True),
        NoOpApiServerRunner(pid=12345),
    )
    assert isinstance(provisioner, Provisioner)


# 2
def test_http_provisioner_provision_happy_path() -> None:
    """AC-9 #2 — `provision` happy path returns a `ProvisionedEnv` with
    the expected env_kind / port / pid / non-null started_at; runner
    invoked exactly once with the expected port; probe invoked AFTER
    runner."""
    runner = NoOpApiServerRunner(pid=12345)
    probe = NoOpApiAvailabilityProbe(available=True)
    provisioner = HttpProvisioner(probe, runner)
    env = provisioner.provision("story-4-5-happy", "api", 8000)
    assert env.env_kind == "api"
    assert env.port == 8000
    assert env.pid == 12345
    assert env.started_at is not None
    # Runner invoked exactly once with the expected port.
    assert runner.call_count == 1
    assert runner.last_port == 8000
    # Probe was invoked (AFTER the runner per the AC-2 ordering).
    assert probe.call_count == 1


# 3
def test_http_provisioner_raises_api_server_not_ready_on_probe_false() -> None:
    """AC-9 #3 — probe-false raises `ApiServerNotReady` with
    `failure_step="dev-server-not-ready"`. Runner WAS invoked (probe
    AFTER runner per AC-2 ordering — opposite of Story 4.4)."""
    runner = NoOpApiServerRunner(pid=99999)
    provisioner = HttpProvisioner(
        NoOpApiAvailabilityProbe(available=False), runner
    )
    # Patch os.kill so the orphan-cleanup branch does not interact with
    # an actual PID at test time.
    with mock.patch("loud_fail_harness.http_driver.os.kill"):
        with pytest.raises(ApiServerNotReady) as excinfo:
            provisioner.provision("story-4-5-fail", "api", 8000)
    assert excinfo.value.failure_step == "dev-server-not-ready"
    # Runner MUST have been invoked (probe AFTER runner).
    assert runner.call_count == 1


# 4
def test_http_provisioner_cleans_up_orphan_pid_on_probe_false() -> None:
    """AC-9 #4 — orphan-PID cleanup on probe-false: `os.kill(pid,
    SIGTERM)` invoked exactly once; `ProcessLookupError` /
    `PermissionError` swallowed silently (idempotent cleanup).
    """
    runner = NoOpApiServerRunner(pid=99999)
    provisioner = HttpProvisioner(
        NoOpApiAvailabilityProbe(available=False), runner
    )

    # Case A: os.kill returns cleanly — single SIGTERM call.
    with mock.patch("loud_fail_harness.http_driver.os.kill") as mk:
        mk.return_value = None
        with pytest.raises(ApiServerNotReady):
            provisioner.provision("story-4-5-orphan-a", "api", 8001)
    assert mk.call_count == 1
    assert mk.call_args_list[0] == mock.call(99999, signal.SIGTERM)

    # Case B: os.kill raises ProcessLookupError — swallowed.
    with mock.patch("loud_fail_harness.http_driver.os.kill") as mk:
        mk.side_effect = ProcessLookupError("gone")
        with pytest.raises(ApiServerNotReady):
            provisioner.provision("story-4-5-orphan-b", "api", 8002)
    assert mk.call_count == 1

    # Case C: os.kill raises PermissionError — swallowed.
    with mock.patch("loud_fail_harness.http_driver.os.kill") as mk:
        mk.side_effect = PermissionError("not allowed")
        with pytest.raises(ApiServerNotReady):
            provisioner.provision("story-4-5-orphan-c", "api", 8003)
    assert mk.call_count == 1


# --------------------------------------------------------------------------- #
# AC-2 routing chain — integration-level                                      #
# --------------------------------------------------------------------------- #


# 5
def test_http_provisioner_routes_through_env_provisioning_provision_env(
    tmp_path: pathlib.Path,
) -> None:
    """AC-9 #5 — `provision_env(... HttpProvisioner(probe-false), ...)`
    raises `EnvProvisioningFailed` whose emission carries
    `marker_class="env-setup-failed"` AND
    `sub_cause="dev-server-not-ready"` byte-for-byte (verifies the
    AC-2 routing chain end-to-end).
    """
    run_state_path = tmp_path / "run-state.yaml"
    run_state_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.1",
                "story_id": "story-4-5-routing",
                "run_id": "run-4-5-routing-0001",
                "current_state": "review",
                "branch_name": "story/4-5-routing",
                "dispatched_specialist": None,
                "last_envelope": None,
                "pending_qa_dispatch_payload": None,
                "retry_history": [],
                "active_markers": [],
                "cost_to_date_by_specialist": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    registry = _canonical_env_setup_failed_registry()
    appended: list[dict[str, Any]] = []

    provisioner = HttpProvisioner(
        NoOpApiAvailabilityProbe(available=False),
        NoOpApiServerRunner(pid=12345),
    )

    # Patch os.kill so the orphan-cleanup branch is harmless.
    with mock.patch("loud_fail_harness.http_driver.os.kill"):
        with pytest.raises(EnvProvisioningFailed) as excinfo:
            provision_env(
                story_id="story-4-5-routing",
                project_type="api",
                provisioner=provisioner,
                port=51234,
                run_state_path=run_state_path,
                registry=registry,
                event_appender=appended.append,
            )

    emission = excinfo.value.emission
    assert emission.marker_record.marker_class == "env-setup-failed"
    assert emission.marker_record.sub_cause == "dev-server-not-ready"
    # No event was appended on the failure path.
    assert appended == []


# --------------------------------------------------------------------------- #
# AC-3 — HttpTeardown                                                         #
# --------------------------------------------------------------------------- #


# 6a
def test_http_teardown_satisfies_teardown_protocol() -> None:
    """AC-9 #6 — `HttpTeardown` structurally satisfies Story 4.3's
    `Teardown` Protocol.
    """
    assert isinstance(HttpTeardown(), Teardown)


# 6b
def test_http_teardown_sigterm_then_clean_exit() -> None:
    """AC-9 #6b — SIGTERM sent; process exits within bounded wait;
    SIGKILL is NOT sent (liveness-check raises ProcessLookupError on
    first poll).
    """
    env = ProvisionedEnv(
        env_kind="api",
        port=8080,
        pid=12345,
        started_at=datetime.now(timezone.utc),
    )
    with mock.patch("loud_fail_harness.http_driver.os.kill") as mk:
        mk.side_effect = [None, ProcessLookupError("gone")]
        HttpTeardown().teardown(env)

    assert mk.call_count == 2
    assert mk.call_args_list[0] == mock.call(12345, signal.SIGTERM)
    assert mk.call_args_list[1] == mock.call(12345, 0)


# 6c
def test_http_teardown_sigkill_on_bounded_wait_expiry() -> None:
    """AC-9 #6c — bounded wait expires without clean exit; SIGKILL is sent."""
    env = ProvisionedEnv(
        env_kind="api",
        port=8080,
        pid=12345,
        started_at=datetime.now(timezone.utc),
    )
    with (
        mock.patch("loud_fail_harness.http_driver.os.kill") as mk,
        mock.patch(
            "loud_fail_harness.http_driver.time.monotonic",
            side_effect=[0.0, 1.0, 10.0],
        ),
        mock.patch("loud_fail_harness.http_driver.time.sleep"),
    ):
        mk.return_value = None
        HttpTeardown().teardown(env)

    assert mk.call_count == 3
    assert mk.call_args_list[0] == mock.call(12345, signal.SIGTERM)
    assert mk.call_args_list[1] == mock.call(12345, 0)  # liveness check in loop body
    assert mk.call_args_list[2] == mock.call(12345, signal.SIGKILL)


# 6d
def test_http_teardown_process_already_gone_on_sigterm() -> None:
    """AC-9 #6d — ProcessLookupError on SIGTERM: idempotent, SIGKILL never sent."""
    env = ProvisionedEnv(
        env_kind="api",
        port=12345,
        pid=99999,
        started_at=datetime.now(timezone.utc),
    )
    with mock.patch("loud_fail_harness.http_driver.os.kill") as mk:
        mk.side_effect = ProcessLookupError("gone")
        result = HttpTeardown().teardown(env)

    assert result is None
    assert mk.call_count == 1
    assert mk.call_args_list[0] == mock.call(99999, signal.SIGTERM)


# --------------------------------------------------------------------------- #
# AC-1 — ApiDriver Protocol runtime_checkable                                 #
# --------------------------------------------------------------------------- #


# 7
def test_api_driver_protocol_is_runtime_checkable() -> None:
    """AC-9 #7 — a class implementing all five ApiDriver methods passes
    `isinstance(driver, ApiDriver)`. A class missing one method does NOT
    pass `isinstance`.
    """
    # Positive case: NoOpApiDriver implements all five methods.
    assert isinstance(NoOpApiDriver(), ApiDriver)
    # Negative case: incomplete impl missing assert_header + inspect_network_trace.
    assert not isinstance(_IncompleteApiDriver(), ApiDriver)
    # Bonus: the other Protocols are also runtime_checkable.
    assert isinstance(NoOpApiAvailabilityProbe(), ApiAvailabilityProbe)
    assert isinstance(NoOpApiServerRunner(), ApiServerRunner)
    assert isinstance(NoOpHttpClient(), HttpClient)


# 8
def test_http_response_and_api_assertion_record_shapes() -> None:
    """AC-9 #8 — record shapes; both frozen.
    """
    response = HttpResponse(
        status=200, headers=(("Content-Type", "text/plain"),), body="hello"
    )
    assertion = ApiAssertion(
        passed=True, observed="200", expected="200", kind="status"
    )
    # Three-tuple shape for HttpResponse.
    assert response.status == 200
    assert response.headers == (("Content-Type", "text/plain"),)
    assert response.body == "hello"
    # Four-tuple shape for ApiAssertion.
    assert assertion.passed is True
    assert assertion.observed == "200"
    assert assertion.expected == "200"
    assert assertion.kind == "status"
    # Both frozen.
    assert response.model_config.get("frozen") is True
    assert assertion.model_config.get("frozen") is True
    # ApiAssertion strict shape (extra="forbid").
    with pytest.raises(Exception):
        ApiAssertion(
            passed=True,
            observed="x",
            expected="y",
            kind="status",
            extra_field="boom",  # type: ignore[call-arg]
        )


# --------------------------------------------------------------------------- #
# AC-4 — verify_ac envelope projection + pass / fail / blocked paths          #
# --------------------------------------------------------------------------- #


# 9
def test_verify_ac_envelope_projection_round_trip(
    envelope_schema: dict[str, Any],
) -> None:
    """AC-9 #9 — `AcResult.model_dump(mode="json")` validates against
    `schemas/envelope.schema.yaml` `$defs/ac_result` byte-for-byte; the
    `semantic_verification` field equals the literal string
    `"not_applicable"`.
    """
    plan_entry = _make_plan_entry()
    driver = NoOpApiDriver()
    capturer = NoOpEvidenceCapturer()
    result = verify_ac(
        ac_id="AC-1",
        ac_text="endpoint returns 200",
        plan_entry=plan_entry,
        driver=driver,
        evidence_capturer=capturer,
        masked_selectors=MaskedSelectorPolicy(),
    )
    assert result.semantic_verification == "not_applicable"
    validator = _make_ac_result_validator(envelope_schema)
    errors = list(validator.iter_errors(result.model_dump(mode="json")))
    assert errors == [], f"AcResult dump failed schema validation: {errors}"


# 10
def test_verify_ac_pass_path() -> None:
    """AC-9 #10 — passing assertion → `status="pass"`, ≥ 1 entry in
    `assertions`, ≥ 1 entry in `evidence_refs`."""
    plan_entry = _make_plan_entry()
    driver = NoOpApiDriver(
        assertion=ApiAssertion(
            passed=True, observed="200", expected="200", kind="status"
        )
    )
    capturer = NoOpEvidenceCapturer()
    result = verify_ac(
        ac_id="AC-1",
        ac_text="endpoint returns 200",
        plan_entry=plan_entry,
        driver=driver,
        evidence_capturer=capturer,
        masked_selectors=MaskedSelectorPolicy(),
    )
    assert result.status == "pass"
    assert len(result.assertions) >= 1
    assert len(result.evidence_refs) >= 1


# 11
def test_verify_ac_fail_path() -> None:
    """AC-9 #11 — failing assertion → `status="fail"`; the failed
    assertion's observed-vs-expected detail is captured in `assertions`.
    """
    plan_entry = _make_plan_entry()
    driver = NoOpApiDriver(
        assertion=ApiAssertion(
            passed=False, observed="500", expected="200", kind="status"
        )
    )
    capturer = NoOpEvidenceCapturer()
    result = verify_ac(
        ac_id="AC-1",
        ac_text="endpoint returns 200",
        plan_entry=plan_entry,
        driver=driver,
        evidence_capturer=capturer,
        masked_selectors=MaskedSelectorPolicy(),
    )
    assert result.status == "fail"
    # observed-vs-expected is captured.
    joined = " ".join(result.assertions)
    assert "500" in joined
    assert "200" in joined
    # An evidence_ref capturing the request/response trace is recorded.
    assert len(result.evidence_refs) >= 1


# 12
def test_verify_ac_blocked_on_driver_exception() -> None:
    """AC-9 #12 — non-`ApiServiceBroken` driver exception →
    `status="blocked"`; the exception's diagnostic is captured.
    """
    plan_entry = _make_plan_entry()
    driver = _RaisingApiDriver()
    capturer = NoOpEvidenceCapturer()
    result = verify_ac(
        ac_id="AC-1",
        ac_text="endpoint returns 200",
        plan_entry=plan_entry,
        driver=driver,
        evidence_capturer=capturer,
        masked_selectors=MaskedSelectorPolicy(),
    )
    assert result.status == "blocked"
    joined = " ".join(result.assertions)
    assert "blocked" in joined.lower() or "RuntimeError" in joined
    assert len(result.evidence_refs) >= 1


# 13
def test_verify_ac_reraises_api_service_broken() -> None:
    """AC-9 #13 — `verify_ac` re-raises `ApiServiceBroken` UNCHANGED.
    """
    api_exc = ApiServiceBroken("connection refused")
    driver = NoOpApiDriver(action_exception=api_exc)
    plan_entry = _make_plan_entry()
    capturer = NoOpEvidenceCapturer()

    with pytest.raises(ApiServiceBroken) as excinfo:
        verify_ac(
            ac_id="AC-1",
            ac_text="endpoint returns 200",
            plan_entry=plan_entry,
            driver=driver,
            evidence_capturer=capturer,
            masked_selectors=MaskedSelectorPolicy(),
        )
    assert excinfo.value is api_exc
    assert excinfo.value.failure_step == "dev-server-not-ready"
    assert excinfo.value.failure_diagnostic == "connection refused"


# --------------------------------------------------------------------------- #
# AC-6 — ApiServiceBroken carries failure_step + failure_diagnostic           #
# --------------------------------------------------------------------------- #


# 14
def test_api_service_broken_carries_failure_step_and_diagnostic() -> None:
    """AC-9 #14 — `ApiServiceBroken("timeout after 5s")` has the
    expected `failure_step` + `failure_diagnostic` byte-for-byte;
    `ApiServerNotReady` likewise carries `failure_step`.
    """
    exc = ApiServiceBroken("timeout after 5s")
    assert exc.failure_step == "dev-server-not-ready"
    assert exc.failure_diagnostic == "timeout after 5s"
    # The class-level constant matches the marker-taxonomy enum.
    assert API_SERVER_NOT_READY_STEP == "dev-server-not-ready"
    # ApiServerNotReady ALSO carries the same failure_step.
    nr = ApiServerNotReady("nope")
    assert nr.failure_step == "dev-server-not-ready"


# --------------------------------------------------------------------------- #
# AC-5 — MaskedSelectorPolicy api-side redaction                              #
# --------------------------------------------------------------------------- #


# 15
def test_masked_selector_policy_redacts_authorization_header() -> None:
    """AC-9 #15 — api-side wrapper redacts an `Authorization: Bearer
    <token>` header value; the captured payload contains
    `[REDACTED]` substituting for the token.
    """
    policy = MaskedSelectorPolicy(masked_selectors=("Authorization",))
    payload = (
        "GET /api/users -> 200\n"
        ">  Authorization: Bearer eyJhSecretToken123\n"
        ">  Accept: application/json\n"
        "<  Content-Type: application/json\n"
    )
    redacted = _apply_api_masked_selector_policy(payload, policy)
    assert MASKED_REDACTION_SENTINEL in redacted
    assert "eyJhSecretToken123" not in redacted
    # Adjacent non-masked headers are preserved verbatim.
    assert "Accept: application/json" in redacted
    assert "Content-Type: application/json" in redacted

    # Round-trip through NoOpEvidenceCapturer wired with the api-side wrapper:
    # the capturer's recorded payload (which is the input it received) is
    # the post-wrapper redacted text.
    capturer = NoOpEvidenceCapturer()
    capturer.capture("network-trace", redacted)
    assert capturer.recorded
    recorded_payload = capturer.recorded[0][1]
    assert MASKED_REDACTION_SENTINEL in recorded_payload
    assert "eyJhSecretToken123" not in recorded_payload


# 16
def test_masked_selector_policy_redacts_json_body_field() -> None:
    """AC-9 #16 — JSON body field redaction: selector `password`
    redacts the value following `"password":` in JSON-body excerpts.
    """
    policy = MaskedSelectorPolicy(masked_selectors=("password",))
    payload = (
        'POST /login -> 200\n'
        '>  body: {"user": "alice", "password": "hunter2"}\n'
    )
    redacted = _apply_api_masked_selector_policy(payload, policy)
    assert MASKED_REDACTION_SENTINEL in redacted
    assert "hunter2" not in redacted
    # The non-masked field is preserved.
    assert "alice" in redacted


# 17
def test_masked_selector_policy_empty_no_redaction() -> None:
    """AC-9 #17 — empty `masked_selectors` → payload unchanged."""
    policy = MaskedSelectorPolicy(masked_selectors=())
    payload = (
        "GET /api/users -> 200\n"
        ">  Authorization: Bearer eyJhSecretToken123\n"
    )
    redacted = _apply_api_masked_selector_policy(payload, policy)
    assert redacted == payload
    assert "eyJhSecretToken123" in redacted
    assert MASKED_REDACTION_SENTINEL not in redacted


# --------------------------------------------------------------------------- #
# AC-8 — canonical envelope fixtures                                          #
# --------------------------------------------------------------------------- #


# 18
def test_http_driver_fixtures_validate_against_envelope_schema(
    repo_root: pathlib.Path,
    envelope_schema: dict[str, Any],
) -> None:
    """AC-9 #18 — each of the three AC-8 fixtures validates against the
    envelope schema."""
    fixtures_dir = repo_root / "examples" / "envelopes"
    expected = [
        "qa-pass-api-http-ac1.yaml",
        "qa-fail-api-http-status-mismatch.yaml",
        "qa-blocked-api-service-broken.yaml",
    ]
    validator = Draft202012Validator(envelope_schema)
    for fixture_name in expected:
        fixture_path = fixtures_dir / fixture_name
        assert fixture_path.exists(), f"missing fixture: {fixture_name}"
        envelope = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
        errors = list(validator.iter_errors(envelope))
        assert errors == [], f"{fixture_name} failed validation: {errors}"


# --------------------------------------------------------------------------- #
# Discipline tests                                                            #
# --------------------------------------------------------------------------- #


# 19
def test_http_driver_module_has_lf_line_endings(
    repo_root: pathlib.Path,
) -> None:
    """AC-9 #19 — no `\\r` characters in http_driver.py source bytes
    AND no `\\r` characters in the new step file source bytes."""
    module_path = (
        repo_root
        / "tools"
        / "loud-fail-harness"
        / "src"
        / "loud_fail_harness"
        / "http_driver.py"
    )
    assert b"\r" not in module_path.read_bytes()

    step_file = (
        repo_root
        / "skills"
        / "bmad-automation"
        / "steps"
        / "qa-driver-http.md"
    )
    assert b"\r" not in step_file.read_bytes()


# 20
def test_http_driver_module_all_exports() -> None:
    """AC-9 #20 — `http_driver.__all__` contains at minimum the 17
    public-API symbols enumerated in AC-1.
    """
    expected_symbols = {
        "API_SERVER_NOT_READY_STEP",
        "HttpResponse",
        "ApiAssertion",
        "NetworkTraceRecord",
        "ApiServerNotReady",
        "ApiServiceBroken",
        "ApiAvailabilityProbe",
        "ApiServerRunner",
        "HttpClient",
        "ApiDriver",
        "HttpProvisioner",
        "HttpTeardown",
        "NoOpApiAvailabilityProbe",
        "NoOpApiServerRunner",
        "NoOpApiDriver",
        "NoOpHttpClient",
        "verify_ac",
    }
    actual = set(http_driver.__all__)
    missing = expected_symbols - actual
    assert missing == set(), f"missing __all__ exports: {missing}"
    assert len(expected_symbols) == 17


# 21
def test_step_file_qa_driver_http_md_exists_with_required_sections(
    repo_root: pathlib.Path,
) -> None:
    """AC-9 #21 — `steps/qa-driver-http.md` exists with the nine
    structural section headings; LF line endings; names each of the
    four ApiDriver Protocol methods + `inspect_network_trace`
    byte-for-byte; references `surface_env_setup_failure` AS-IS reuse
    AND records the no-new-emission-helper structural choice.
    """
    step_file = (
        repo_root
        / "skills"
        / "bmad-automation"
        / "steps"
        / "qa-driver-http.md"
    )
    assert step_file.exists(), f"missing step file: {step_file}"

    raw = step_file.read_bytes()
    assert b"\r" not in raw, "step file must use LF line endings"

    text = raw.decode("utf-8")
    required_sections = [
        "# Step: QA driver — HTTP",
        "## Purpose",
        "## Pre-condition",
        "## Procedure — ApiDriver Protocol ↔ stdlib mappings",
        "## Procedure — provisioner runtime bindings",
        "## Failure mode — API broken mid-run",
        "## Failure mode — dev-server-not-ready at provisioning",
        "## Failure mode — AC verification-fail",
        "## MaskedSelectorPolicy runtime application",
        "## Composed substrate primitives",
        "## Forward consumers",
    ]
    for heading in required_sections:
        assert heading in text, f"step file missing section: {heading!r}"

    # The four ApiDriver Protocol methods + inspect_network_trace named
    # byte-for-byte.
    for name in (
        "request",
        "assert_status",
        "assert_body",
        "assert_header",
        "inspect_network_trace",
    ):
        assert name in text, f"step file missing method name: {name!r}"

    # AS-IS reuse of surface_env_setup_failure named.
    assert "surface_env_setup_failure" in text
    assert "AS-IS" in text
    # No-new-emission-helper structural choice recorded.
    assert "no new emission helper" in text or "NO new emission helper" in text or "does NOT introduce a new emission helper" in text
    # The forward-pointer to Story 4.10 named.
    assert "Story 4.10" in text
    # The dev-server-not-ready sub_cause named.
    assert "dev-server-not-ready" in text
    # The api_server_command runbook field named.
    assert "api_server_command" in text


# 22
def test_http_driver_module_pluggability_clean(
    repo_root: pathlib.Path,
) -> None:
    """AC-9 #22 — the `http_driver.py` source AND the
    `qa-driver-http.md` step file source do NOT contain references to
    `dev-wrapper`, `review-bmad-wrapper`, or any literal
    `agents/{slug}.md` path-form citation (FR62 pluggability gate
    compliance verified at the module + step-file level).
    """
    forbidden = (
        "dev-wrapper",
        "review-bmad-wrapper",
        "agents/dev-wrapper.md",
        "agents/review-bmad-wrapper.md",
    )
    module_path = (
        repo_root
        / "tools"
        / "loud-fail-harness"
        / "src"
        / "loud_fail_harness"
        / "http_driver.py"
    )
    module_text = module_path.read_text(encoding="utf-8")
    for token in forbidden:
        assert token not in module_text, (
            f"FR62 pluggability violation: {token!r} appears in http_driver.py"
        )
    step_file = (
        repo_root
        / "skills"
        / "bmad-automation"
        / "steps"
        / "qa-driver-http.md"
    )
    step_text = step_file.read_text(encoding="utf-8")
    for token in forbidden:
        assert token not in step_text, (
            f"FR62 pluggability violation: {token!r} appears in qa-driver-http.md"
        )
