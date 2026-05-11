"""Contract-coverage matrix for the mobile MCP driver substrate library
(Story 9.3 — Phase 1.5 mobile QA per ADR-007).

Mirrors the test-file shape established by ``test_playwright_driver.py``
(Story 4.4) and ``test_http_driver.py`` (Story 4.5) for the substrate-
library tests; extends with mobile-specific assertions on the ten-method
:class:`MobileDriver` Protocol, Tier-1 a11y-tree + Tier-2 screenshot
evidence projections, the ``mobile-blocked`` marker class linkage, and
the masked-selector substring-redaction semantics.

Test enumeration (Story 9.3 AC-9):

    1.  test_mobile_driver_protocol_has_ten_methods_per_ac2
    2.  test_mobile_driver_reexports_masked_selector_policy_from_playwright
    3.  test_mobile_driver_reexports_ac_result_from_playwright
    4.  test_mobile_blocked_marker_constant_byte_matches_taxonomy
    5.  test_verify_ac_mechanical_assertion_pass
    6.  test_verify_ac_mechanical_assertion_fail
    7.  test_verify_ac_evidence_triple_invariant_holds
    8.  test_verify_ac_captures_tier_1_a11y_tree_snapshot
    9.  test_verify_ac_captures_tier_2_screenshot
    10. test_verify_ac_emits_tier_3_not_applicable_by_default
    11. test_verify_ac_blocked_on_driver_exception
    12. test_verify_ac_propagates_mobile_mcp_unavailable_unchanged
    13. test_surface_mobile_mcp_unavailable_atomic_on_unknown_marker
    14. test_surface_mobile_mcp_unavailable_returns_emission_with_diagnostic
    15. test_evidence_capturer_redacts_a11y_label_substrings
    16. test_evidence_capturer_no_redaction_when_policy_empty
    17. test_mobile_blocked_marker_has_empty_sub_classifications
    18. test_mobile_driver_module_pluggability_clean
"""

from __future__ import annotations

import inspect
import pathlib
from typing import Any, get_args, get_origin

import pytest
import yaml

from loud_fail_harness import mobile_driver, playwright_driver
from loud_fail_harness.mobile_driver import (
    MOBILE_BLOCKED_MARKER,
    MaskedSelectorPolicy,
    MobileDriver,
    MobileDriverAssertion,
    MobileElement,
    MobileMcpUnavailable,
    MobileMcpUnavailableDiagnostic,
    MobileMcpUnavailableEmission,
    NoOpMobileDriver,
    surface_mobile_mcp_unavailable,
    verify_ac,
)
from loud_fail_harness.playwright_driver import (
    AcResult,
    EvidenceCapturer,
    NoOpEvidenceCapturer,
)
from loud_fail_harness.qa_behavioral_plan import QABehavioralPlanEntry
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _canonical_mobile_blocked_registry() -> MarkerClassRegistry:
    """Registry containing exactly the ``mobile-blocked`` marker class."""
    return MarkerClassRegistry(
        marker_classes=frozenset({MOBILE_BLOCKED_MARKER})
    )


def _empty_registry() -> MarkerClassRegistry:
    """Registry with no marker classes (consumed by atomic-on-failure tests)."""
    return MarkerClassRegistry(marker_classes=frozenset())


def _make_plan_entry(
    *,
    ac_id: str = "AC-1",
    assertion_shape: str = "verify: AC-1 holds",
) -> QABehavioralPlanEntry:
    return QABehavioralPlanEntry(
        ac_id=ac_id,
        assertion_shape=assertion_shape,
        expected_evidence_tier="tier-1-mechanical",
        semantic_verification_requirement="not_applicable",
        heuristic_applicability=(),
    )


def _load_taxonomy() -> dict[str, Any]:
    taxonomy_path = (
        pathlib.Path(__file__).resolve().parents[3]
        / "schemas"
        / "marker-taxonomy.yaml"
    )
    return yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))


# Ten canonical MobileDriver Protocol method names per AC-2.
_TEN_METHODS_PER_AC2: frozenset[str] = frozenset({
    "launch_app",
    "terminate_app",
    "tap_at_coordinates",
    "swipe",
    "type_text",
    "press_button",
    "screenshot",
    "list_elements_on_screen",
    "assert_element_present",
    "get_screen_size",
})


# --------------------------------------------------------------------------- #
# 1 — Protocol shape: exactly the ten methods enumerated in AC-2.             #
# --------------------------------------------------------------------------- #


def test_mobile_driver_protocol_has_ten_methods_per_ac2() -> None:
    """Structural invariant — drift would break the step file's mapping
    table at ``skills/bmad-automation/steps/qa-driver-mobile.md`` and the
    module docstring's mapping table at ``mobile_driver.py``.
    """
    methods = {
        name
        for name, member in inspect.getmembers(
            MobileDriver, predicate=lambda m: callable(m)
        )
        if not name.startswith("_")
    }
    assert methods == _TEN_METHODS_PER_AC2, (
        f"MobileDriver Protocol method set mismatch: "
        f"expected {sorted(_TEN_METHODS_PER_AC2)}, got {sorted(methods)}"
    )


# --------------------------------------------------------------------------- #
# 2 — Single source of truth: MaskedSelectorPolicy re-export identity.        #
# --------------------------------------------------------------------------- #


def test_mobile_driver_reexports_masked_selector_policy_from_playwright() -> None:
    """``is`` identity (not ``==``) — re-export is the single source of
    truth (drift would be caught by mypy but discipline matters)."""
    assert MaskedSelectorPolicy is playwright_driver.MaskedSelectorPolicy


# --------------------------------------------------------------------------- #
# 3 — Single source of truth: AcResult re-export identity.                    #
# --------------------------------------------------------------------------- #


def test_mobile_driver_reexports_ac_result_from_playwright() -> None:
    """``AcResult`` is re-exported from :mod:`playwright_driver` per the
    Story 9.3 AC-1 single-source-of-truth posture."""
    assert AcResult is playwright_driver.AcResult


# --------------------------------------------------------------------------- #
# 4 — MOBILE_BLOCKED_MARKER constant byte-matches the taxonomy entry.         #
# --------------------------------------------------------------------------- #


def test_mobile_blocked_marker_constant_byte_matches_taxonomy() -> None:
    """The substrate library's constant matches the canonical taxonomy
    entry byte-for-byte; drift would be a structural defect.
    """
    assert MOBILE_BLOCKED_MARKER == "mobile-blocked"
    taxonomy = _load_taxonomy()
    classes = {entry["marker_class"] for entry in taxonomy["markers"]}
    assert "mobile-blocked" in classes


# --------------------------------------------------------------------------- #
# 5 — verify_ac happy path: status="pass", ≥1 evidence_ref, observed/expected.#
# --------------------------------------------------------------------------- #


def test_verify_ac_mechanical_assertion_pass() -> None:
    elements = (
        MobileElement(
            label="acceptance text for AC-1",
            x=10,
            y=20,
            width=100,
            height=44,
            role="AXButton",
        ),
    )
    driver = NoOpMobileDriver(assert_passed=True, elements=elements)
    capturer = NoOpEvidenceCapturer()
    plan_entry = _make_plan_entry()

    result = verify_ac(
        "AC-1",
        "acceptance text for AC-1",
        plan_entry,
        driver,
        capturer,
        MaskedSelectorPolicy(),
    )

    assert result.status == "pass"
    assert len(result.assertions) >= 1
    assert len(result.evidence_refs) >= 1
    assert result.semantic_verification == "not_applicable"


# --------------------------------------------------------------------------- #
# 6 — verify_ac fail path: status="fail", evidence preserved.                 #
# --------------------------------------------------------------------------- #


def test_verify_ac_mechanical_assertion_fail() -> None:
    """`verify_ac` against an a11y-tree missing the expected element returns
    `AcResult(status="fail", ...)` with the failing assertion + Tier-1 +
    Tier-2 evidence refs."""
    driver = NoOpMobileDriver(assert_passed=False, elements=())
    capturer = NoOpEvidenceCapturer()
    plan_entry = _make_plan_entry()

    result = verify_ac(
        "AC-1",
        "acceptance text for AC-1",
        plan_entry,
        driver,
        capturer,
        MaskedSelectorPolicy(),
    )

    assert result.status == "fail"
    assert len(result.assertions) >= 1
    assert len(result.evidence_refs) >= 1
    assert result.semantic_verification == "not_applicable"


# --------------------------------------------------------------------------- #
# 7 — Evidence-triple invariant holds on BOTH pass AND fail.                  #
# --------------------------------------------------------------------------- #


def test_verify_ac_evidence_triple_invariant_holds() -> None:
    """FR19 structural witness: `assertions` ≥ 1 AND `evidence_refs` ≥ 1
    on both `pass` AND `fail` paths (parallel to Story 4.7's schema-level
    `if/then` enforcement).
    """
    plan_entry = _make_plan_entry()
    masked = MaskedSelectorPolicy()

    elements = (
        MobileElement(
            label="acceptance text for AC-1",
            x=0,
            y=0,
            width=10,
            height=10,
            role=None,
        ),
    )
    pass_result = verify_ac(
        "AC-1",
        "acceptance text for AC-1",
        plan_entry,
        NoOpMobileDriver(assert_passed=True, elements=elements),
        NoOpEvidenceCapturer(),
        masked,
    )
    assert pass_result.status == "pass"
    assert len(pass_result.assertions) >= 1
    assert len(pass_result.evidence_refs) >= 1

    fail_result = verify_ac(
        "AC-1",
        "acceptance text for AC-1",
        plan_entry,
        NoOpMobileDriver(assert_passed=False, elements=()),
        NoOpEvidenceCapturer(),
        masked,
    )
    assert fail_result.status == "fail"
    assert len(fail_result.assertions) >= 1
    assert len(fail_result.evidence_refs) >= 1


# --------------------------------------------------------------------------- #
# 8 — Tier-1 mechanical a11y-tree snapshot captured.                          #
# --------------------------------------------------------------------------- #


def test_verify_ac_captures_tier_1_a11y_tree_snapshot() -> None:
    """At least one `EvidenceRef` in the returned `evidence_refs` carries
    `tier="tier-1-mechanical"` (the a11y-tree snapshot)."""
    driver = NoOpMobileDriver(assert_passed=True, elements=())
    capturer = NoOpEvidenceCapturer()

    result = verify_ac(
        "AC-1",
        "acceptance text",
        _make_plan_entry(),
        driver,
        capturer,
        MaskedSelectorPolicy(),
    )

    tier_1_refs = [
        ref for ref in result.evidence_refs if ref.tier == "tier-1-mechanical"
    ]
    assert len(tier_1_refs) >= 1


# --------------------------------------------------------------------------- #
# 9 — Tier-2 outcome screenshot captured.                                     #
# --------------------------------------------------------------------------- #


def test_verify_ac_captures_tier_2_screenshot() -> None:
    """At least one `EvidenceRef` in the returned `evidence_refs` carries
    `tier="tier-2-outcome"` AND its `path` ends in `.png` (screenshot)."""
    driver = NoOpMobileDriver(assert_passed=True, elements=())
    capturer = NoOpEvidenceCapturer()

    result = verify_ac(
        "AC-1",
        "acceptance text",
        _make_plan_entry(),
        driver,
        capturer,
        MaskedSelectorPolicy(),
    )

    tier_2_refs = [
        ref for ref in result.evidence_refs if ref.tier == "tier-2-outcome"
    ]
    assert len(tier_2_refs) >= 1
    assert tier_2_refs[0].path.endswith(".png")
    assert "capturer-unavailable" not in tier_2_refs[0].path


# --------------------------------------------------------------------------- #
# 10 — Tier-3 semantic verification defaults to "not_applicable".             #
# --------------------------------------------------------------------------- #


def test_verify_ac_emits_tier_3_not_applicable_by_default() -> None:
    """Drivers do not run semantic verification; the wrapper does. The
    driver-projection default is `semantic_verification="not_applicable"`."""
    driver = NoOpMobileDriver(assert_passed=True, elements=())

    result = verify_ac(
        "AC-1",
        "text",
        _make_plan_entry(),
        driver,
        NoOpEvidenceCapturer(),
        MaskedSelectorPolicy(),
    )

    assert result.semantic_verification == "not_applicable"


# --------------------------------------------------------------------------- #
# 11 — verify_ac blocked-status on non-MCP exception during driver action.    #
# --------------------------------------------------------------------------- #


class _RaisingMobileDriver:
    """MobileDriver implementation whose driver action raises a non-MCP
    exception (consumed by the blocked-status test)."""

    def launch_app(self, package_name: str) -> None:
        del package_name

    def terminate_app(self, package_name: str) -> None:
        del package_name

    def tap_at_coordinates(self, x: int, y: int) -> None:
        del x, y

    def swipe(self, direction: str) -> None:
        del direction

    def type_text(self, text: str, *, submit: bool = False) -> None:
        del text, submit

    def press_button(self, button: str) -> None:
        del button

    def screenshot(self, name: str) -> str:
        del name
        return "ignored"

    def list_elements_on_screen(self) -> tuple[MobileElement, ...]:
        return ()

    def assert_element_present(self, label: str) -> MobileDriverAssertion:
        del label
        raise RuntimeError("synthetic non-MCP exception")

    def get_screen_size(self) -> tuple[int, int]:
        return (1170, 2532)


def test_verify_ac_blocked_on_driver_exception() -> None:
    """Non-MCP exception during AC verification returns AcResult with
    status="blocked" + the diagnostic captured in assertions."""
    driver = _RaisingMobileDriver()

    result = verify_ac(
        "AC-1",
        "text",
        _make_plan_entry(),
        driver,
        NoOpEvidenceCapturer(),
        MaskedSelectorPolicy(),
    )

    assert result.status == "blocked"
    assert any("blocked" in s for s in result.assertions)
    assert len(result.evidence_refs) >= 1


# --------------------------------------------------------------------------- #
# 12 — verify_ac propagates MobileMcpUnavailable unchanged.                   #
# --------------------------------------------------------------------------- #


class _McpUnavailableMobileDriver(_RaisingMobileDriver):
    """MobileDriver whose `assert_element_present` raises
    MobileMcpUnavailable — verify_ac must NOT catch it.
    """

    def assert_element_present(self, label: str) -> MobileDriverAssertion:
        del label
        emission = MobileMcpUnavailableEmission(
            marker_record=__import__(
                "loud_fail_harness.env_provisioning",
                fromlist=["MarkerEmissionRecord"],
            ).MarkerEmissionRecord(
                marker_class=MOBILE_BLOCKED_MARKER,
                sub_cause=None,
                context={
                    "story_id": "test",
                    "action_kind": "assert_element_present",
                    "prior_evidence_refs": [],
                },
            ),
            diagnostic=MobileMcpUnavailableDiagnostic(
                story_id="test",
                action_kind="assert_element_present",
                prior_evidence_refs=(),
            ),
        )
        raise MobileMcpUnavailable(emission)


def test_verify_ac_propagates_mobile_mcp_unavailable_unchanged() -> None:
    """`verify_ac` does NOT catch MobileMcpUnavailable — it propagates
    unchanged for the QA wrapper to route through
    `surface_mobile_mcp_unavailable`."""
    driver = _McpUnavailableMobileDriver()

    with pytest.raises(MobileMcpUnavailable):
        verify_ac(
            "AC-1",
            "text",
            _make_plan_entry(),
            driver,
            NoOpEvidenceCapturer(),
            MaskedSelectorPolicy(),
        )


# --------------------------------------------------------------------------- #
# 13 — surface_mobile_mcp_unavailable atomic-on-failure (registry rejection). #
# --------------------------------------------------------------------------- #


def test_surface_mobile_mcp_unavailable_atomic_on_unknown_marker() -> None:
    """Registry without `mobile-blocked` raises `UnknownMarkerClass` BEFORE
    any emission record is produced (Pattern 5 atomic-on-failure)."""
    with pytest.raises(UnknownMarkerClass):
        surface_mobile_mcp_unavailable(
            story_id="story-001",
            registry=_empty_registry(),
            action_kind="screenshot",
            prior_evidence_refs=(),
        )


# --------------------------------------------------------------------------- #
# 14 — surface_mobile_mcp_unavailable happy path returns the structured       #
#      emission carrying marker_record + diagnostic.                          #
# --------------------------------------------------------------------------- #


def test_surface_mobile_mcp_unavailable_returns_emission_with_diagnostic() -> None:
    registry = _canonical_mobile_blocked_registry()

    emission = surface_mobile_mcp_unavailable(
        story_id="story-001",
        registry=registry,
        action_kind="screenshot",
        prior_evidence_refs=("_bmad-output/qa-evidence/x.txt",),
    )

    assert emission.marker_record.marker_class == MOBILE_BLOCKED_MARKER
    assert emission.marker_record.sub_cause is None
    assert emission.diagnostic.story_id == "story-001"
    assert emission.diagnostic.action_kind == "screenshot"
    assert emission.diagnostic.prior_evidence_refs == (
        "_bmad-output/qa-evidence/x.txt",
    )


# --------------------------------------------------------------------------- #
# 15 — masked-selector redaction applied via NoOpEvidenceCapturer (single-    #
#      source-of-truth at playwright_driver's _apply_masked_selector_policy). #
# --------------------------------------------------------------------------- #


def test_evidence_capturer_redacts_a11y_label_substrings() -> None:
    """With `MaskedSelectorPolicy(masked_selectors=("password",))`, the
    NoOpEvidenceCapturer redacts the substring `"password"` in captured
    a11y-tree payloads to `[REDACTED]` per the single-source-of-truth
    redaction algorithm re-used from playwright_driver."""
    policy = MaskedSelectorPolicy(masked_selectors=("password",))
    capturer = NoOpEvidenceCapturer(masked_selectors=policy)
    elements = (
        MobileElement(
            label="password input field",
            x=0,
            y=0,
            width=10,
            height=10,
            role="AXTextField",
        ),
    )
    driver = NoOpMobileDriver(assert_passed=True, elements=elements)

    verify_ac(
        "AC-1",
        '"password" required',
        _make_plan_entry(),
        driver,
        capturer,
        policy,
    )

    # The NoOpEvidenceCapturer.recorded list carries the redacted payloads.
    # At least one redacted payload should contain the sentinel.
    assert any(
        "[REDACTED]" in redacted_payload
        for _action_kind, redacted_payload, _path in capturer.recorded
    )


def test_evidence_capturer_no_redaction_when_policy_empty() -> None:
    """Empty `masked_selectors=()` produces no redaction (verbatim
    payload passthrough)."""
    policy = MaskedSelectorPolicy(masked_selectors=())
    capturer = NoOpEvidenceCapturer(masked_selectors=policy)
    elements = (
        MobileElement(
            label="some sensitive content marker XYZ-77",
            x=0,
            y=0,
            width=10,
            height=10,
            role=None,
        ),
    )
    driver = NoOpMobileDriver(assert_passed=True, elements=elements)

    verify_ac(
        "AC-1",
        "some sensitive content marker XYZ-77",
        _make_plan_entry(),
        driver,
        capturer,
        policy,
    )

    # No payload should contain the sentinel when policy is empty.
    assert not any(
        "[REDACTED]" in redacted_payload
        for _action_kind, redacted_payload, _path in capturer.recorded
    )


# --------------------------------------------------------------------------- #
# 17 — `mobile-blocked` marker class linkage: empty sub_classifications.      #
# --------------------------------------------------------------------------- #


def test_mobile_blocked_marker_has_empty_sub_classifications() -> None:
    """Taxonomy invariant: the `mobile-blocked` entry's `sub_classifications`
    is an empty list (the marker carries no sub-classifications). Drift
    against this constraint would invalidate `surface_mobile_mcp_unavailable`'s
    `sub_cause=None` contract.
    """
    taxonomy = _load_taxonomy()
    entry = next(
        (
            marker
            for marker in taxonomy["markers"]
            if marker["marker_class"] == "mobile-blocked"
        ),
        None,
    )
    assert entry is not None, (
        "marker-taxonomy.yaml is missing the `mobile-blocked` entry"
    )
    assert entry.get("sub_classifications", []) == []


# --------------------------------------------------------------------------- #
# 18 — Pluggability invariant: mobile_driver module imports gate-safe only.   #
# --------------------------------------------------------------------------- #


def test_mobile_driver_module_pluggability_clean() -> None:
    """The `mobile_driver` module imports ONLY from substrate libraries
    (no wrapper-side cross-references). Witness: import-scan via
    `mobile_driver.__file__` source-string check that none of the
    forbidden specialist-wrapper-module names appear in import statements.
    """
    module_path = pathlib.Path(mobile_driver.__file__)
    source = module_path.read_text(encoding="utf-8")
    # Allow these forbidden patterns to appear in docstrings/comments
    # but NOT in `from ... import` or `import ...` statements. Simple
    # line-based check: a `from <forbidden>` import line.
    forbidden_imports = (
        "from loud_fail_harness.dev_wrapper",
        "from loud_fail_harness.review_bmad_wrapper",
        "from loud_fail_harness.qa_wrapper",
        "from loud_fail_harness.lad_wrapper",
        "from loud_fail_harness.bundle_assembly",
    )
    for forbidden in forbidden_imports:
        assert forbidden not in source, (
            f"mobile_driver.py imports from forbidden specialist-wrapper "
            f"surface: {forbidden!r}"
        )


# --------------------------------------------------------------------------- #
# Defensive structural boundary tests (beyond AC-9's enumerated cases).       #
# --------------------------------------------------------------------------- #


def test_mobile_driver_protocol_is_runtime_checkable() -> None:
    """`MobileDriver` is `@runtime_checkable` so `isinstance(driver,
    MobileDriver)` returns `True` for any structurally-compatible
    implementation. NoOpMobileDriver satisfies the Protocol."""
    assert isinstance(NoOpMobileDriver(), MobileDriver)


def test_mobile_element_extra_forbid_rejects_unknown_field() -> None:
    """Pydantic `extra="forbid"` ConfigDict (Epic 1 retro Action #2)
    rejects unknown fields at instantiation. Structural witness."""
    with pytest.raises(Exception):  # ValidationError (Pydantic)
        MobileElement(
            label="x",
            x=0,
            y=0,
            width=10,
            height=10,
            role=None,
            unknown_field="should-fail",  # type: ignore[call-arg]
        )


def test_mobile_driver_assertion_swipe_direction_typed_via_literal() -> None:
    """The `swipe` method's `direction` parameter is typed via Literal —
    structural witness for the MVP-Phase-1.5 narrowed-enum policy.
    """
    sig = inspect.signature(MobileDriver.swipe)
    direction_param = sig.parameters["direction"]
    # The annotation is a Literal[...]; verify the args match the AC-2 set.
    annotation = direction_param.annotation
    # Resolve string annotation under `from __future__ import annotations`.
    from typing import Literal, get_type_hints

    hints = get_type_hints(MobileDriver.swipe)
    annotation = hints["direction"]
    assert get_origin(annotation) is Literal
    assert set(get_args(annotation)) == {"up", "down", "left", "right"}


def test_mobile_mcp_unavailable_diagnostic_min_length_constraints() -> None:
    """`story_id` and `action_kind` have `min_length=1` per the parallel
    of `PlaywrightMcpUnavailableDiagnostic`. Pydantic rejects empties.
    """
    with pytest.raises(Exception):  # ValidationError
        MobileMcpUnavailableDiagnostic(
            story_id="",
            action_kind="screenshot",
            prior_evidence_refs=(),
        )
    with pytest.raises(Exception):
        MobileMcpUnavailableDiagnostic(
            story_id="story-001",
            action_kind="",
            prior_evidence_refs=(),
        )


# --------------------------------------------------------------------------- #
# Marker for the test file's evidence-capturer Protocol satisfaction.         #
# --------------------------------------------------------------------------- #


def test_no_op_evidence_capturer_satisfies_evidence_capturer_protocol() -> None:
    """NoOpEvidenceCapturer (re-exported from `playwright_driver`) is a
    structurally-compatible `EvidenceCapturer` Protocol implementation."""
    assert isinstance(NoOpEvidenceCapturer(), EvidenceCapturer)
