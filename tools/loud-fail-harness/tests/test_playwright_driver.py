"""Contract-coverage matrix for the Playwright web-driver library
(Story 4.4).

Mirrors the test-file shape established by ``test_env_provisioning.py``
(Story 4.3 — substrate library composed by the orchestrator skill at
the seam), ``test_qa_plan_drift.py`` (Story 4.2 — pure-library two-
channel atomic emission), and ``test_review_layer_failure.py``
(Story 3.3 — three-channel atomic emission).

Test enumeration (Story 4.4 AC-9 — 19 tests):
    1.  test_playwright_provisioner_satisfies_provisioner_protocol
    2.  test_playwright_provisioner_provision_happy_path
    3.  test_playwright_provisioner_raises_playwright_launch_failed_on_probe_false
    4.  test_playwright_teardown_satisfies_teardown_protocol
    5.  test_playwright_provisioner_routes_through_env_provisioning_provision_env
    6.  test_web_driver_protocol_is_runtime_checkable
    7.  test_verify_ac_envelope_projection_round_trip
    8.  test_verify_ac_pass_path
    9.  test_verify_ac_fail_path
    10. test_verify_ac_blocked_on_driver_exception
    11. test_masked_selector_policy_redacts_password_input
    12. test_masked_selector_policy_empty_no_redaction
    13. test_surface_playwright_mcp_unavailable_happy_path
    14. test_surface_playwright_mcp_unavailable_atomic_on_registry_rejection
    15. test_playwright_driver_fixtures_validate_against_envelope_schema
    16. test_playwright_driver_module_has_lf_line_endings
    17. test_playwright_driver_module_all_exports
    18. test_step_file_qa_driver_playwright_md_exists_with_required_sections
    19. test_playwright_driver_module_pluggability_clean
"""

from __future__ import annotations

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

from loud_fail_harness import playwright_driver
from loud_fail_harness._shared import find_repo_root, load_schema
from loud_fail_harness.env_provisioning import (
    EnvProvisioningFailed,
    Provisioner,
    ProvisionedEnv,
    Teardown,
    provision_env,
)
from loud_fail_harness.playwright_driver import (
    MASKED_REDACTION_SENTINEL,
    PLAYWRIGHT_MCP_UNAVAILABLE_MARKER,
    MaskedSelectorPolicy,
    NetworkRequest,
    NoOpAvailabilityProbe,
    NoOpDevServerRunner,
    NoOpEvidenceCapturer,
    NoOpWebDriver,
    PlaywrightLaunchFailed,
    PlaywrightMcpUnavailable,
    PlaywrightMcpUnavailableDiagnostic,
    PlaywrightMcpUnavailableEmission,
    PlaywrightProvisioner,
    PlaywrightTeardown,
    WebDriver,
    WebDriverAssertion,
    surface_playwright_mcp_unavailable,
    verify_ac,
)
from loud_fail_harness.qa_behavioral_plan import QABehavioralPlanEntry
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
def envelope_schema(repo_root: pathlib.Path) -> dict[str, Any]:
    """Module-scoped envelope schema."""
    return load_schema(repo_root / "schemas" / "envelope.schema.yaml")


@pytest.fixture(scope="module")
def runtime_marker_registry() -> MarkerClassRegistry:
    """Module-scoped registry loaded from the canonical taxonomy."""
    return load_marker_class_registry()


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _canonical_playwright_unavailable_registry() -> MarkerClassRegistry:
    """Registry containing exactly the ``playwright-mcp-unavailable`` marker
    class.

    Test surface independent of the on-disk taxonomy per Story 1.4's
    enumeration test discipline.
    """
    return MarkerClassRegistry(
        marker_classes=frozenset({PLAYWRIGHT_MCP_UNAVAILABLE_MARKER})
    )


def _canonical_env_setup_failed_registry() -> MarkerClassRegistry:
    """Registry containing exactly the ``env-setup-failed`` marker class
    (consumed by the integration-level routing test).
    """
    return MarkerClassRegistry(marker_classes=frozenset({"env-setup-failed"}))


def _make_plan_entry(
    *,
    ac_id: str = "AC-1",
    assertion_shape: str = "verify: AC-1 holds",
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
    sub-schema with the envelope schema's ``$defs`` registered for $ref
    resolution (mirrors the canonical pattern from `test_env_provisioning.py`'s
    `_build_run_state_validator`).
    """
    registry = Registry().with_resources(
        [
            (
                "envelope.schema.yaml",
                Resource(contents=envelope_schema, specification=DRAFT202012),
            ),
        ]
    )
    ac_result_schema = envelope_schema["$defs"]["ac_result"]
    return Draft202012Validator(ac_result_schema, registry=registry)


class _RaisingDriver:
    """WebDriver impl whose driver action raises a non-MCP exception
    (consumed by the blocked-status test).
    """

    def navigate(self, url: str) -> None:
        del url

    def click(self, selector: str) -> None:
        del selector

    def type_text(self, selector: str, text: str) -> None:
        del selector, text

    def hover(self, selector: str) -> None:
        del selector

    def drag(self, source_selector: str, target_selector: str) -> None:
        del source_selector, target_selector

    def screenshot(self, name: str) -> str:
        del name
        return ""

    def assert_dom_text(
        self, selector: str, expected: str
    ) -> WebDriverAssertion:
        del selector, expected
        raise RuntimeError("simulated mid-run driver error (NOT mcp)")

    def inspect_network(self) -> tuple[NetworkRequest, ...]:
        return ()


class _IncompleteWebDriver:
    """A class missing one WebDriver method — used by the negative
    runtime_checkable assertion to verify the protocol catches missing
    methods.
    """

    def navigate(self, url: str) -> None:
        del url

    def click(self, selector: str) -> None:
        del selector

    def type_text(self, selector: str, text: str) -> None:
        del selector, text

    def hover(self, selector: str) -> None:
        del selector

    def drag(self, source_selector: str, target_selector: str) -> None:
        del source_selector, target_selector

    def screenshot(self, name: str) -> str:
        del name
        return ""

    # Missing assert_dom_text + inspect_network on purpose.


# --------------------------------------------------------------------------- #
# AC-2 — PlaywrightProvisioner.provision                                      #
# --------------------------------------------------------------------------- #


# 1
def test_playwright_provisioner_satisfies_provisioner_protocol() -> None:
    """AC-9 #1 — `PlaywrightProvisioner` structurally satisfies Story 4.3's
    `Provisioner` Protocol (`@runtime_checkable`).
    """
    provisioner = PlaywrightProvisioner(
        NoOpAvailabilityProbe(available=True),
        NoOpDevServerRunner(pid=12345),
    )
    assert isinstance(provisioner, Provisioner)


# 2
def test_playwright_provisioner_provision_happy_path() -> None:
    """AC-9 #2 — `provision` happy path returns a `ProvisionedEnv` with
    the expected env_kind / port / pid / non-null started_at."""
    runner = NoOpDevServerRunner(pid=12345)
    provisioner = PlaywrightProvisioner(
        NoOpAvailabilityProbe(available=True), runner
    )
    env = provisioner.provision("story-4-4-happy", "web", 8000)
    assert env.env_kind == "web"
    assert env.port == 8000
    assert env.pid == 12345
    assert env.started_at is not None
    # Runner was invoked exactly once with the expected port.
    assert runner.call_count == 1
    assert runner.last_port == 8000


# 3
def test_playwright_provisioner_raises_playwright_launch_failed_on_probe_false() -> None:
    """AC-9 #3 — probe-false raises `PlaywrightLaunchFailed`; runner is
    NOT invoked (atomic-on-failure: probe before runner)."""
    runner = NoOpDevServerRunner(pid=99999)
    provisioner = PlaywrightProvisioner(
        NoOpAvailabilityProbe(available=False), runner
    )
    with pytest.raises(PlaywrightLaunchFailed) as excinfo:
        provisioner.provision("story-4-4-fail", "web", 8000)
    assert excinfo.value.failure_step == "playwright-launch-failed"
    # Runner MUST NOT have been invoked.
    assert runner.call_count == 0


# --------------------------------------------------------------------------- #
# AC-3 — PlaywrightTeardown                                                   #
# --------------------------------------------------------------------------- #


# 4
def test_playwright_teardown_satisfies_teardown_protocol() -> None:
    """AC-9 #4 — `PlaywrightTeardown` structurally satisfies Story 4.3's
    `Teardown` Protocol.
    """
    assert isinstance(PlaywrightTeardown(), Teardown)


# --------------------------------------------------------------------------- #
# AC-2 routing chain — integration-level                                      #
# --------------------------------------------------------------------------- #


# 5
def test_playwright_provisioner_routes_through_env_provisioning_provision_env(
    tmp_path: pathlib.Path,
) -> None:
    """AC-9 #5 — `provision_env(... PlaywrightProvisioner(probe-false), ...)`
    raises `EnvProvisioningFailed` whose emission carries
    `marker_class="env-setup-failed"` AND
    `sub_cause="playwright-launch-failed"` byte-for-byte (verifies the
    AC-2 routing chain end-to-end).
    """
    run_state_path = tmp_path / "run-state.yaml"
    run_state_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.1",
                "story_id": "story-4-4-routing",
                "run_id": "run-4-4-routing-0001",
                "current_state": "review",
                "branch_name": "story/4-4-routing",
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

    provisioner = PlaywrightProvisioner(
        NoOpAvailabilityProbe(available=False),
        NoOpDevServerRunner(pid=99999),
    )

    with pytest.raises(EnvProvisioningFailed) as excinfo:
        provision_env(
            story_id="story-4-4-routing",
            project_type="web",
            provisioner=provisioner,
            port=51234,
            run_state_path=run_state_path,
            registry=registry,
            event_appender=appended.append,
        )

    emission = excinfo.value.emission
    assert emission.marker_record.marker_class == "env-setup-failed"
    assert emission.marker_record.sub_cause == "playwright-launch-failed"
    # No event was appended on the failure path.
    assert appended == []


# --------------------------------------------------------------------------- #
# AC-1 — WebDriver Protocol runtime_checkable                                 #
# --------------------------------------------------------------------------- #


# 6
def test_web_driver_protocol_is_runtime_checkable() -> None:
    """AC-9 #6 — a class implementing all seven WebDriver methods passes
    `isinstance(driver, WebDriver)`. A class missing one method does NOT
    pass `isinstance`.
    """
    # Positive case: NoOpWebDriver implements all seven methods.
    assert isinstance(NoOpWebDriver(), WebDriver)
    # Negative case: incomplete impl missing assert_dom_text + inspect_network.
    assert not isinstance(_IncompleteWebDriver(), WebDriver)


# --------------------------------------------------------------------------- #
# AC-4 — verify_ac envelope projection + pass / fail / blocked paths          #
# --------------------------------------------------------------------------- #


# 7
def test_verify_ac_envelope_projection_round_trip(
    envelope_schema: dict[str, Any],
) -> None:
    """AC-9 #7 — `AcResult.model_dump(mode="json")` validates against
    `schemas/envelope.schema.yaml` `$defs/ac_result` byte-for-byte; the
    `semantic_verification` field equals the literal string
    `"not_applicable"`.
    """
    plan_entry = _make_plan_entry()
    driver = NoOpWebDriver(
        assertion=WebDriverAssertion(
            passed=True, observed="hello", expected="hello"
        )
    )
    capturer = NoOpEvidenceCapturer()
    result = verify_ac(
        ac_id="AC-1",
        ac_text="hello",
        plan_entry=plan_entry,
        driver=driver,
        evidence_capturer=capturer,
        masked_selectors=MaskedSelectorPolicy(),
    )
    assert result.semantic_verification == "not_applicable"

    validator = _make_ac_result_validator(envelope_schema)
    errors = list(validator.iter_errors(result.model_dump(mode="json")))
    assert errors == [], f"AcResult dump failed schema validation: {errors}"


# 8
def test_verify_ac_pass_path() -> None:
    """AC-9 #8 — passing assertion → `status="pass"`, ≥ 1 entry in
    `assertions`, ≥ 1 entry in `evidence_refs`."""
    plan_entry = _make_plan_entry()
    driver = NoOpWebDriver(
        assertion=WebDriverAssertion(
            passed=True, observed="hello", expected="hello"
        )
    )
    capturer = NoOpEvidenceCapturer()
    result = verify_ac(
        ac_id="AC-1",
        ac_text="hello",
        plan_entry=plan_entry,
        driver=driver,
        evidence_capturer=capturer,
        masked_selectors=MaskedSelectorPolicy(),
    )
    assert result.status == "pass"
    assert len(result.assertions) >= 1
    assert len(result.evidence_refs) >= 1


# 9
def test_verify_ac_fail_path() -> None:
    """AC-9 #9 — failing assertion → `status="fail"`; the failed
    assertion's observed-vs-expected detail is captured in `assertions`.
    """
    plan_entry = _make_plan_entry()
    driver = NoOpWebDriver(
        assertion=WebDriverAssertion(
            passed=False, observed="goodbye", expected="hello"
        )
    )
    capturer = NoOpEvidenceCapturer()
    result = verify_ac(
        ac_id="AC-1",
        ac_text="hello",
        plan_entry=plan_entry,
        driver=driver,
        evidence_capturer=capturer,
        masked_selectors=MaskedSelectorPolicy(),
    )
    assert result.status == "fail"
    # observed-vs-expected is captured in assertions.
    joined = " ".join(result.assertions)
    assert "goodbye" in joined
    assert "hello" in joined
    # An evidence_ref capturing the expected-vs-actual evidence is recorded.
    assert len(result.evidence_refs) >= 1


# 10
def test_verify_ac_blocked_on_driver_exception() -> None:
    """AC-9 #10 — non-`PlaywrightMcpUnavailable` driver exception →
    `status="blocked"`; the exception's diagnostic is captured in
    `assertions` + `evidence_refs`.
    """
    plan_entry = _make_plan_entry()
    driver = _RaisingDriver()
    capturer = NoOpEvidenceCapturer()
    result = verify_ac(
        ac_id="AC-1",
        ac_text="hello",
        plan_entry=plan_entry,
        driver=driver,
        evidence_capturer=capturer,
        masked_selectors=MaskedSelectorPolicy(),
    )
    assert result.status == "blocked"
    # The diagnostic is captured.
    joined = " ".join(result.assertions)
    assert "blocked" in joined.lower() or "RuntimeError" in joined
    assert len(result.evidence_refs) >= 1


# --------------------------------------------------------------------------- #
# AC-5 — MaskedSelectorPolicy redaction                                       #
# --------------------------------------------------------------------------- #


# 11
def test_masked_selector_policy_redacts_password_input() -> None:
    """AC-9 #11 — `NoOpEvidenceCapturer` configured with
    `MaskedSelectorPolicy(masked_selectors=("input[type=password]",))`
    produces a captured payload containing `"[REDACTED]"` substituting
    for `"hunter2"`.
    """
    policy = MaskedSelectorPolicy(masked_selectors=("input[type=password]",))
    capturer = NoOpEvidenceCapturer(policy)
    payload = (
        '<form><input type="password" name="pw" value="hunter2"></form>'
    )
    capturer.capture("dom-snapshot", payload)
    assert capturer.recorded, "expected one recorded entry"
    redacted_payload = capturer.recorded[0][1]
    assert MASKED_REDACTION_SENTINEL in redacted_payload
    assert "hunter2" not in redacted_payload


# 12
def test_masked_selector_policy_empty_no_redaction() -> None:
    """AC-9 #12 — empty `masked_selectors` → payload persisted unchanged
    (no redaction)."""
    capturer = NoOpEvidenceCapturer(MaskedSelectorPolicy(masked_selectors=()))
    payload = '<form><input type="password" value="hunter2"></form>'
    capturer.capture("dom-snapshot", payload)
    assert capturer.recorded, "expected one recorded entry"
    recorded_payload = capturer.recorded[0][1]
    # No redaction → exact byte equality with the input.
    assert recorded_payload == payload
    assert "hunter2" in recorded_payload
    assert MASKED_REDACTION_SENTINEL not in recorded_payload


# --------------------------------------------------------------------------- #
# AC-6 — surface_playwright_mcp_unavailable                                   #
# --------------------------------------------------------------------------- #


# 13
def test_surface_playwright_mcp_unavailable_happy_path() -> None:
    """AC-9 #13 — registry with `playwright-mcp-unavailable` →
    emission carrying the canonical marker class + `sub_cause is None`
    + the `prior_evidence_refs` preserved verbatim in the diagnostic.
    """
    registry = _canonical_playwright_unavailable_registry()
    emission = surface_playwright_mcp_unavailable(
        story_id="story-1",
        registry=registry,
        action_kind="click",
        prior_evidence_refs=("path/screenshot.png",),
    )
    assert isinstance(emission, PlaywrightMcpUnavailableEmission)
    assert emission.marker_record.marker_class == "playwright-mcp-unavailable"
    assert emission.marker_record.sub_cause is None
    # The marker_record.context equals the diagnostic.model_dump() payload.
    assert emission.marker_record.context == emission.diagnostic.model_dump(
        mode="json"
    )
    assert emission.diagnostic.prior_evidence_refs == (
        "path/screenshot.png",
    )
    # The diagnostic is the expected shape.
    assert isinstance(emission.diagnostic, PlaywrightMcpUnavailableDiagnostic)


# 14
def test_surface_playwright_mcp_unavailable_atomic_on_registry_rejection() -> None:
    """AC-9 #14 — registry without `playwright-mcp-unavailable` raises
    `UnknownMarkerClass`; NO partial state.
    """
    empty_registry = MarkerClassRegistry(marker_classes=frozenset())
    with pytest.raises(UnknownMarkerClass):
        surface_playwright_mcp_unavailable(
            story_id="story-1",
            registry=empty_registry,
            action_kind="click",
            prior_evidence_refs=(),
        )


# --------------------------------------------------------------------------- #
# AC-8 — canonical envelope fixtures                                          #
# --------------------------------------------------------------------------- #


# 15
def test_playwright_driver_fixtures_validate_against_envelope_schema(
    repo_root: pathlib.Path,
    envelope_schema: dict[str, Any],
) -> None:
    """AC-9 #15 — each of the two AC-8 fixtures validates against the
    envelope schema."""
    fixtures_dir = repo_root / "examples" / "envelopes"
    expected = [
        "qa-pass-web-playwright-ac1.yaml",
        "qa-blocked-playwright-mcp-unavailable.yaml",
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


# 16
def test_playwright_driver_module_has_lf_line_endings(
    repo_root: pathlib.Path,
) -> None:
    """AC-9 #16 — no `\\r` characters in playwright_driver.py source bytes
    (parallel to the cross-story discipline test from Stories 2.8 / 2.9 /
    3.5 / 4.1 / 4.2 / 4.3)."""
    module_path = (
        repo_root
        / "tools"
        / "loud-fail-harness"
        / "src"
        / "loud_fail_harness"
        / "playwright_driver.py"
    )
    raw = module_path.read_bytes()
    assert b"\r" not in raw


# 17
def test_playwright_driver_module_all_exports() -> None:
    """AC-9 #17 — `playwright_driver.__all__` contains at minimum the 22
    public-API symbols enumerated in AC-1.
    """
    expected_symbols = {
        "PLAYWRIGHT_MCP_UNAVAILABLE_MARKER",
        "MASKED_REDACTION_SENTINEL",
        "WebDriverAssertion",
        "NetworkRequest",
        "MaskedSelectorPolicy",
        "AcResult",
        "PlaywrightMcpUnavailableDiagnostic",
        "PlaywrightMcpUnavailableEmission",
        "PlaywrightMcpUnavailable",
        "PlaywrightLaunchFailed",
        "PlaywrightAvailabilityProbe",
        "DevServerRunner",
        "WebDriver",
        "EvidenceCapturer",
        "PlaywrightProvisioner",
        "PlaywrightTeardown",
        "NoOpAvailabilityProbe",
        "NoOpDevServerRunner",
        "NoOpWebDriver",
        "NoOpEvidenceCapturer",
        "verify_ac",
        "surface_playwright_mcp_unavailable",
    }
    actual = set(playwright_driver.__all__)
    missing = expected_symbols - actual
    assert missing == set(), f"missing __all__ exports: {missing}"
    # Sanity bound — we declared exactly 22 symbols.
    assert len(expected_symbols) == 22


# 18
def test_step_file_qa_driver_playwright_md_exists_with_required_sections(
    repo_root: pathlib.Path,
) -> None:
    """AC-9 #18 — `steps/qa-driver-playwright.md` exists with the eight
    structural section headings; LF line endings; names each of the eight
    `mcp__playwright__browser_*` tool names byte-for-byte.
    """
    step_file = (
        repo_root
        / "skills"
        / "bmad-automation"
        / "steps"
        / "qa-driver-playwright.md"
    )
    assert step_file.exists(), f"missing step file: {step_file}"

    raw = step_file.read_bytes()
    assert b"\r" not in raw, "step file must use LF line endings"

    text = raw.decode("utf-8")
    required_sections = [
        "# Step: QA driver — Playwright MCP",
        "## Purpose",
        "## Pre-condition",
        "## Procedure — WebDriver Protocol ↔ MCP tool mappings",
        "## Procedure — provisioner runtime bindings",
        "## Failure mode — playwright-mcp-unavailable mid-run",
        "## Failure mode — playwright-launch-failed at provisioning",
        "## MaskedSelectorPolicy runtime application",
        "## Composed substrate primitives",
        "## Forward consumers",
    ]
    for heading in required_sections:
        assert heading in text, f"step file missing section: {heading!r}"

    # The seven mcp__playwright__browser_* tool names are named byte-for-byte.
    for tool_name in (
        "mcp__playwright__browser_navigate",
        "mcp__playwright__browser_click",
        "mcp__playwright__browser_type",
        "mcp__playwright__browser_hover",
        "mcp__playwright__browser_drag",
        "mcp__playwright__browser_take_screenshot",
        "mcp__playwright__browser_snapshot",
        "mcp__playwright__browser_network_requests",
    ):
        assert tool_name in text, f"step file missing tool name: {tool_name!r}"

    # The failure mode prose names the symbol/marker-class/forward-pointer.
    assert "surface_playwright_mcp_unavailable" in text
    assert "PLAYWRIGHT_MCP_UNAVAILABLE_MARKER" in text
    assert "prior_evidence_refs" in text
    assert "Story 4.10" in text
    assert "PlaywrightLaunchFailed" in text
    assert 'failure_step="playwright-launch-failed"' in text or (
        "playwright-launch-failed" in text
    )


# 19
def test_playwright_driver_module_pluggability_clean(
    repo_root: pathlib.Path,
) -> None:
    """AC-9 #19 — the `playwright_driver.py` source does NOT contain
    references to `dev-wrapper`, `review-bmad-wrapper`, or any literal
    `agents/{slug}.md` path-form citation (FR62 pluggability gate
    compliance verified at the module level).
    """
    module_path = (
        repo_root
        / "tools"
        / "loud-fail-harness"
        / "src"
        / "loud_fail_harness"
        / "playwright_driver.py"
    )
    text = module_path.read_text(encoding="utf-8")
    forbidden = (
        "dev-wrapper",
        "review-bmad-wrapper",
        "agents/dev-wrapper.md",
        "agents/review-bmad-wrapper.md",
    )
    for token in forbidden:
        assert token not in text, (
            f"FR62 pluggability violation: {token!r} appears in playwright_driver.py"
        )


# --------------------------------------------------------------------------- #
# Review-patch tests (added post-review; F-4 + F-5)                          #
# --------------------------------------------------------------------------- #


# 20 (F-4)
def test_verify_ac_reraises_playwright_mcp_unavailable() -> None:
    """Review F-4 — `verify_ac` re-raises `PlaywrightMcpUnavailable` unchanged
    (AC-4: 'does NOT catch PlaywrightMcpUnavailable').
    """
    registry = _canonical_playwright_unavailable_registry()
    emission = surface_playwright_mcp_unavailable(
        story_id="story-f4",
        registry=registry,
        action_kind="click",
        prior_evidence_refs=(),
    )
    mcp_exc = PlaywrightMcpUnavailable(emission)
    driver = NoOpWebDriver(action_exception=mcp_exc)
    plan_entry = _make_plan_entry()
    capturer = NoOpEvidenceCapturer()

    with pytest.raises(PlaywrightMcpUnavailable) as excinfo:
        verify_ac(
            ac_id="AC-1",
            ac_text="hello",
            plan_entry=plan_entry,
            driver=driver,
            evidence_capturer=capturer,
            masked_selectors=MaskedSelectorPolicy(),
        )
    assert excinfo.value is mcp_exc


# 21 (F-5a)
def test_playwright_teardown_sigterm_then_clean_exit() -> None:
    """Review F-5 — SIGTERM sent; process exits within bounded wait; SIGKILL
    is NOT sent (liveness-check raises ProcessLookupError on first poll).
    """
    env = ProvisionedEnv(
        env_kind="web",
        port=8080,
        pid=12345,
        started_at=datetime.now(timezone.utc),
    )
    with mock.patch("loud_fail_harness.playwright_driver.os.kill") as mk:
        mk.side_effect = [None, ProcessLookupError("gone")]
        PlaywrightTeardown().teardown(env)

    assert mk.call_count == 2
    assert mk.call_args_list[0] == mock.call(12345, signal.SIGTERM)
    assert mk.call_args_list[1] == mock.call(12345, 0)


# 22 (F-5b)
def test_playwright_teardown_sigkill_on_bounded_wait_expiry() -> None:
    """Review F-5 — bounded wait expires without clean exit; SIGKILL is sent."""
    env = ProvisionedEnv(
        env_kind="web",
        port=8080,
        pid=12345,
        started_at=datetime.now(timezone.utc),
    )
    # monotonic returns: first call (deadline=base+5), second call (base+10 > deadline)
    # so the while-loop body never executes and we go straight to SIGKILL.
    with (
        mock.patch("loud_fail_harness.playwright_driver.os.kill") as mk,
        mock.patch(
            "loud_fail_harness.playwright_driver.time.monotonic",
            side_effect=[0.0, 10.0],
        ),
        mock.patch("loud_fail_harness.playwright_driver.time.sleep"),
    ):
        mk.return_value = None
        PlaywrightTeardown().teardown(env)

    assert mk.call_count == 2
    assert mk.call_args_list[0] == mock.call(12345, signal.SIGTERM)
    assert mk.call_args_list[1] == mock.call(12345, signal.SIGKILL)


# 23 (F-5c)
def test_playwright_teardown_process_already_gone_on_sigterm() -> None:
    """Review F-5 — ProcessLookupError on SIGTERM: idempotent, SIGKILL never sent."""
    env = ProvisionedEnv(
        env_kind="web",
        port=12345,
        pid=99999,
        started_at=datetime.now(timezone.utc),
    )
    with mock.patch("loud_fail_harness.playwright_driver.os.kill") as mk:
        mk.side_effect = ProcessLookupError("gone")
        result = PlaywrightTeardown().teardown(env)

    assert result is None
    assert mk.call_count == 1
    assert mk.call_args_list[0] == mock.call(99999, signal.SIGTERM)
