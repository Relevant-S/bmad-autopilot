"""Contract-coverage matrix for the plan-driven AC iteration framework
(Story 4.6).

Mirrors the test-file shape established by ``test_http_driver.py``
(Story 4.5), ``test_playwright_driver.py`` (Story 4.4), and
``test_qa_plan_drift.py`` (Story 4.2) for the emission-helper +
substrate-library tests; extends with the iteration-composition
test surface.

Test enumeration (Story 4.6 AC-9 — 20 tests):
    1.  test_module_all_exports
    2.  test_smoke_first_abort_marker_constant_byte_for_byte
    3.  test_surface_smoke_first_abort_atomic_on_failure
    4.  test_surface_smoke_first_abort_happy_path
    5.  test_iterate_acs_happy_path_web_three_acs
    6.  test_iterate_acs_happy_path_api_three_acs
    7.  test_iterate_acs_ac1_fail_smoke_first_abort
    8.  test_iterate_acs_ac2_fail_continues_iteration
    9.  test_iterate_acs_ac1_blocked_no_smoke_first_abort
    10. test_iterate_acs_plan_none_raises
    11. test_iterate_acs_plan_empty_entries_raises
    12. test_iterate_acs_plan_ac_list_mismatch_raises
    13. class TestMobileDispatch (Story 9.3 — supersedes the prior
        slot's ``test_iterate_acs_project_type_mobile_raises_value_error``)
    14. test_iterate_acs_project_type_web_with_none_driver_raises
    15. test_iterate_acs_project_type_api_with_none_driver_raises
    16. test_ac_iteration_result_is_frozen_and_byte_stable
    17. test_qa_ac_iteration_fixtures_validate_against_envelope_schema
    18. test_qa_ac_iteration_module_has_lf_line_endings
    19. test_qa_ac_iteration_module_pluggability_clean
    20. test_iterate_acs_preserves_story_doc_order_with_non_numeric_ac_ids
"""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
import yaml
from pydantic import ValidationError
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from loud_fail_harness import qa_ac_iteration
from loud_fail_harness._shared import find_repo_root, load_schema
from loud_fail_harness.http_driver import (
    ApiAssertion,
    ApiServiceBroken,
    HttpResponse,
    NetworkTraceRecord,
    NoOpApiDriver,
)
from loud_fail_harness.mobile_driver import (
    MobileElement,
    NoOpMobileDriver,
)
from loud_fail_harness.playwright_driver import (
    MaskedSelectorPolicy,
    NetworkRequest,
    NoOpEvidenceCapturer,
    NoOpWebDriver,
    PlaywrightMcpUnavailable,
    WebDriverAssertion,
    surface_playwright_mcp_unavailable,
)
from loud_fail_harness.qa_ac_iteration import (
    SMOKE_FIRST_ABORT_MARKER,
    AcIterationResult,
    PlanAbsentForIteration,
    ProjectType,
    SmokeFirstAbortDiagnosticContext,
    SmokeFirstAbortEmission,
    SmokeFirstAbortEmissionRecord,
    iterate_acs,
    surface_smoke_first_abort,
)
from loud_fail_harness.qa_behavioral_plan import (
    AcEntry,
    QABehavioralPlan,
    QABehavioralPlanEntry,
)
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
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


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _make_registry() -> MarkerClassRegistry:
    """Registry containing exactly the ``smoke-first-abort`` marker class
    (consumed by the abort-path tests)."""
    return MarkerClassRegistry(marker_classes=frozenset({"smoke-first-abort"}))


def _empty_registry() -> MarkerClassRegistry:
    """Registry with no marker classes (consumed by the atomic-on-failure
    test)."""
    return MarkerClassRegistry(marker_classes=frozenset())


def _make_plan_entry(ac_id: str) -> QABehavioralPlanEntry:
    """Build a deterministic plan entry."""
    return QABehavioralPlanEntry(
        ac_id=ac_id,
        assertion_shape=f"verify: {ac_id}",
        expected_evidence_tier="tier-1-mechanical",
        semantic_verification_requirement="not_applicable",
        heuristic_applicability=(),
    )


def _make_plan(ac_ids: tuple[str, ...]) -> QABehavioralPlan:
    """Build a deterministic plan with one entry per AC id."""
    return QABehavioralPlan(
        plan_status="generated",
        ac_hash="0" * 64,
        entries=tuple(_make_plan_entry(ac_id) for ac_id in ac_ids),
    )


def _make_ac_list(ac_ids: tuple[str, ...]) -> tuple[AcEntry, ...]:
    """Build a deterministic ac_list aligned with the plan."""
    return tuple(
        AcEntry(ac_id=ac_id, ac_text=f"acceptance text for {ac_id}")
        for ac_id in ac_ids
    )


def _make_ac1_fail_result() -> Any:
    """Build a deterministic AC-1 fail AcResult for the
    surface_smoke_first_abort tests (uses the AcResult class re-exported
    from playwright_driver). Story 4.8 transitive shim: evidence_refs
    items are wrapped as ``EvidenceRef(path=..., tier="tier-1-mechanical")``
    per the bumped ``$defs/evidence_ref`` shape.
    """
    from loud_fail_harness.playwright_driver import AcResult
    from loud_fail_harness.qa_evidence_tier import EvidenceRef

    return AcResult(
        ac_id="AC-1",
        status="fail",
        assertions=("verify: AC-1", "observed='x' expected='y'"),
        evidence_refs=(
            EvidenceRef(
                path="_bmad-output/qa-evidence/sample/run/ac1-snapshot.txt",
                tier="tier-1-mechanical",
            ),
        ),
        semantic_verification="not_applicable",
    )


class _SequenceWebDriver:
    """A WebDriver Protocol stub returning a sequence of pre-canned
    :class:`WebDriverAssertion` records (one per call). Records every
    call's arguments for assertion. Optional per-call exceptions raise
    on the matching call.
    """

    def __init__(
        self,
        assertions: list[WebDriverAssertion],
        action_exceptions: list[BaseException | None] | None = None,
    ) -> None:
        self._assertions = list(assertions)
        self._action_exceptions = list(
            action_exceptions or [None] * len(assertions)
        )
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self._index = 0

    def _maybe_raise(self) -> None:
        if self._index < len(self._action_exceptions):
            exc = self._action_exceptions[self._index]
            if exc is not None:
                raise exc

    def navigate(self, url: str) -> None:
        self.calls.append(("navigate", (url,)))

    def click(self, selector: str) -> None:
        self.calls.append(("click", (selector,)))

    def type_text(self, selector: str, text: str) -> None:
        self.calls.append(("type_text", (selector, text)))

    def hover(self, selector: str) -> None:
        self.calls.append(("hover", (selector,)))

    def drag(self, source_selector: str, target_selector: str) -> None:
        self.calls.append(("drag", (source_selector, target_selector)))

    def screenshot(self, name: str) -> str:
        self.calls.append(("screenshot", (name,)))
        return f"_bmad-output/qa-evidence/seq/{name}.png"

    def assert_dom_text(
        self, selector: str, expected: str
    ) -> WebDriverAssertion:
        current_index = self._index
        try:
            self._maybe_raise()
        except Exception:
            self._index += 1
            raise
        self.calls.append(("assert_dom_text", (selector, expected)))
        assertion = self._assertions[current_index]
        self._index += 1
        return assertion

    def inspect_network(self) -> tuple[NetworkRequest, ...]:
        self.calls.append(("inspect_network", ()))
        return ()


class _SequenceApiDriver:
    """An ApiDriver Protocol stub returning a sequence of pre-canned
    :class:`ApiAssertion` records (one per ``assert_status`` call) with
    a fixed :class:`HttpResponse` shape returned from ``request``.
    """

    def __init__(
        self,
        assertions: list[ApiAssertion],
        action_exceptions: list[BaseException | None] | None = None,
    ) -> None:
        self._assertions = list(assertions)
        self._action_exceptions = list(
            action_exceptions or [None] * len(assertions)
        )
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self._index = 0

    def _maybe_raise(self) -> None:
        if self._index < len(self._action_exceptions):
            exc = self._action_exceptions[self._index]
            if exc is not None:
                raise exc

    def request(
        self, method: str, url: str, **_: Any
    ) -> HttpResponse:
        try:
            self._maybe_raise()
        except Exception:
            self._index += 1
            raise
        self.calls.append(("request", (method, url)))
        return HttpResponse(
            status=200,
            headers=(("Content-Type", "text/plain"),),
            body="ok",
        )

    def assert_status(
        self, response: HttpResponse, expected: int
    ) -> ApiAssertion:
        del response
        current_index = self._index
        try:
            self._maybe_raise()
        except Exception:
            self._index += 1
            raise
        self.calls.append(("assert_status", (str(expected),)))
        assertion = self._assertions[current_index]
        self._index += 1
        return assertion

    def assert_body(
        self, response: HttpResponse, expected: Any
    ) -> ApiAssertion:
        del response, expected
        return self._assertions[max(self._index - 1, 0)]

    def assert_header(
        self, response: HttpResponse, name: str, expected: str
    ) -> ApiAssertion:
        del response, name, expected
        return self._assertions[max(self._index - 1, 0)]

    def inspect_network_trace(self) -> tuple[NetworkTraceRecord, ...]:
        return ()


# --------------------------------------------------------------------------- #
# AC-1 — module shape                                                         #
# --------------------------------------------------------------------------- #


# 1
def test_module_all_exports() -> None:
    """AC-9 #1 — `qa_ac_iteration.__all__` carries the public-API
    symbols enumerated in AC-1.
    """
    expected_symbols = {
        "SMOKE_FIRST_ABORT_MARKER",
        "ProjectType",
        "SmokeFirstAbortDiagnosticContext",
        "SmokeFirstAbortEmissionRecord",
        "SmokeFirstAbortEmission",
        "AcIterationResult",
        "MobileDriver",
        "PlanAbsentForIteration",
        "surface_smoke_first_abort",
        "iterate_acs",
    }
    actual = set(qa_ac_iteration.__all__)
    missing = expected_symbols - actual
    extra = actual - expected_symbols
    assert missing == set(), f"missing __all__ exports: {missing}"
    assert extra == set(), f"unexpected __all__ exports: {extra}"


# 2
def test_smoke_first_abort_marker_constant_byte_for_byte() -> None:
    """AC-9 #2 — `SMOKE_FIRST_ABORT_MARKER == "smoke-first-abort"`
    byte-for-byte (consumed AS-IS from `marker-taxonomy.yaml` line 188).
    """
    assert SMOKE_FIRST_ABORT_MARKER == "smoke-first-abort"


# --------------------------------------------------------------------------- #
# AC-7 — surface_smoke_first_abort atomic-on-failure + happy path             #
# --------------------------------------------------------------------------- #


# 3
def test_surface_smoke_first_abort_atomic_on_failure() -> None:
    """AC-9 #3 — registry rejection raises `UnknownMarkerClass` BEFORE
    any partial state is constructed.
    """
    registry = _empty_registry()
    ac1_result = _make_ac1_fail_result()
    with pytest.raises(UnknownMarkerClass):
        surface_smoke_first_abort(
            story_id="story-001",
            registry=registry,
            ac1_result=ac1_result,
        )


# 4
def test_surface_smoke_first_abort_happy_path() -> None:
    """AC-9 #4 — happy-path returns a `SmokeFirstAbortEmission` with
    assertions / evidence_refs copied verbatim from the input
    AcResult."""
    registry = _make_registry()
    ac1_result = _make_ac1_fail_result()
    emission = surface_smoke_first_abort(
        story_id="story-001",
        registry=registry,
        ac1_result=ac1_result,
    )
    assert isinstance(emission, SmokeFirstAbortEmission)
    assert emission.marker_record.marker_class == "smoke-first-abort"
    assert emission.diagnostic_context.story_id == "story-001"
    assert emission.diagnostic_context.failed_ac_id == "AC-1"
    # Verbatim copy from the input AcResult.
    assert emission.diagnostic_context.failed_assertions == ac1_result.assertions
    # Story 4.8 transitive update: AcResult.evidence_refs is now
    # tuple[EvidenceRef, ...] but SmokeFirstAbortDiagnosticContext.
    # failed_evidence_refs remains tuple[str, ...] (Story 4.6 surface).
    # surface_smoke_first_abort projects path strings out of the tier-aware
    # refs; assert against the same projection on the source AcResult.
    assert (
        emission.diagnostic_context.failed_evidence_refs
        == tuple(ref.path for ref in ac1_result.evidence_refs)
    )
    # Co-exposure: marker_record.diagnostic_context is the same payload.
    assert (
        emission.marker_record.diagnostic_context
        == emission.diagnostic_context
    )


# --------------------------------------------------------------------------- #
# AC-2 — happy-path semantics                                                 #
# --------------------------------------------------------------------------- #


# 5
def test_iterate_acs_happy_path_web_three_acs() -> None:
    """AC-9 #5 — `project_type="web"`, 3 ACs all pass → 3-entry result,
    `smoke_first_abort is None`, `project_type == "web"`.
    """
    plan = _make_plan(("AC-1", "AC-2", "AC-3"))
    ac_list = _make_ac_list(("AC-1", "AC-2", "AC-3"))
    web_driver = NoOpWebDriver(
        assertion=WebDriverAssertion(passed=True, observed="ok", expected="ok")
    )
    capturer = NoOpEvidenceCapturer()
    policy = MaskedSelectorPolicy()
    registry = _make_registry()

    result = iterate_acs(
        plan=plan,
        ac_list=ac_list,
        project_type="web",
        story_id="story-001",
        registry=registry,
        web_driver=web_driver,
        evidence_capturer=capturer,
        masked_selectors=policy,
    )

    assert isinstance(result, AcIterationResult)
    assert len(result.ac_results) == 3
    assert [r.ac_id for r in result.ac_results] == ["AC-1", "AC-2", "AC-3"]
    assert all(r.status == "pass" for r in result.ac_results)
    assert result.smoke_first_abort is None
    assert result.project_type == "web"


# 6
def test_iterate_acs_happy_path_api_three_acs() -> None:
    """AC-9 #6 — `project_type="api"`, 3 ACs all pass → 3-entry result,
    `smoke_first_abort is None`, `project_type == "api"`.
    """
    plan = _make_plan(("AC-1", "AC-2", "AC-3"))
    ac_list = _make_ac_list(("AC-1", "AC-2", "AC-3"))
    api_driver = NoOpApiDriver()
    capturer = NoOpEvidenceCapturer()
    policy = MaskedSelectorPolicy()
    registry = _make_registry()

    result = iterate_acs(
        plan=plan,
        ac_list=ac_list,
        project_type="api",
        story_id="story-001",
        registry=registry,
        api_driver=api_driver,
        evidence_capturer=capturer,
        masked_selectors=policy,
    )

    assert len(result.ac_results) == 3
    assert [r.ac_id for r in result.ac_results] == ["AC-1", "AC-2", "AC-3"]
    assert all(r.status == "pass" for r in result.ac_results)
    assert result.smoke_first_abort is None
    assert result.project_type == "api"


# --------------------------------------------------------------------------- #
# AC-3 — smoke-first abort semantics                                          #
# --------------------------------------------------------------------------- #


# 7
def test_iterate_acs_ac1_fail_smoke_first_abort() -> None:
    """AC-9 #7 — AC-1 fail triggers smoke-first abort; AC-2 / AC-3
    `verify_ac` is NOT called.
    """
    plan = _make_plan(("AC-1", "AC-2", "AC-3"))
    ac_list = _make_ac_list(("AC-1", "AC-2", "AC-3"))
    failing = WebDriverAssertion(
        passed=False, observed="500 error", expected="acceptance text"
    )
    passing = WebDriverAssertion(
        passed=True, observed="ok", expected="ok"
    )
    web_driver = _SequenceWebDriver(
        assertions=[failing, passing, passing]
    )
    capturer = NoOpEvidenceCapturer()
    policy = MaskedSelectorPolicy()
    registry = _make_registry()

    result = iterate_acs(
        plan=plan,
        ac_list=ac_list,
        project_type="web",
        story_id="story-001",
        registry=registry,
        web_driver=web_driver,
        evidence_capturer=capturer,
        masked_selectors=policy,
    )

    assert len(result.ac_results) == 1
    assert result.ac_results[0].ac_id == "AC-1"
    assert result.ac_results[0].status == "fail"
    assert isinstance(
        result.smoke_first_abort, SmokeFirstAbortEmissionRecord
    )
    assert result.smoke_first_abort.marker_class == "smoke-first-abort"
    assert (
        result.smoke_first_abort.diagnostic_context.failed_ac_id
        == "AC-1"
    )
    # AC-2 and AC-3's verify_ac MUST NOT have been called — only ONE
    # assert_dom_text call (AC-1) appears in the driver's call log.
    assert_dom_text_calls = [
        call for call in web_driver.calls if call[0] == "assert_dom_text"
    ]
    assert len(assert_dom_text_calls) == 1


# 8
def test_iterate_acs_ac2_fail_continues_iteration() -> None:
    """AC-9 #8 — non-AC-1 failure does NOT trigger smoke-first abort;
    iteration continues through all entries.
    """
    plan = _make_plan(("AC-1", "AC-2", "AC-3"))
    ac_list = _make_ac_list(("AC-1", "AC-2", "AC-3"))
    passing = WebDriverAssertion(passed=True, observed="ok", expected="ok")
    failing = WebDriverAssertion(
        passed=False, observed="bad", expected="ok"
    )
    web_driver = _SequenceWebDriver(
        assertions=[passing, failing, passing]
    )
    capturer = NoOpEvidenceCapturer()
    policy = MaskedSelectorPolicy()
    registry = _make_registry()

    result = iterate_acs(
        plan=plan,
        ac_list=ac_list,
        project_type="web",
        story_id="story-001",
        registry=registry,
        web_driver=web_driver,
        evidence_capturer=capturer,
        masked_selectors=policy,
    )

    assert len(result.ac_results) == 3
    assert [r.status for r in result.ac_results] == [
        "pass",
        "fail",
        "pass",
    ]
    assert result.smoke_first_abort is None
    # All three assert_dom_text calls happened.
    assert_dom_text_calls = [
        call for call in web_driver.calls if call[0] == "assert_dom_text"
    ]
    assert len(assert_dom_text_calls) == 3


# 9
def test_iterate_acs_ac1_blocked_no_smoke_first_abort() -> None:
    """AC-9 #9 — AC-1 status `blocked` does NOT trigger smoke-first
    abort; iteration continues through AC-2 / AC-3.
    """
    plan = _make_plan(("AC-1", "AC-2", "AC-3"))
    ac_list = _make_ac_list(("AC-1", "AC-2", "AC-3"))
    passing = WebDriverAssertion(
        passed=True, observed="ok", expected="ok"
    )
    # First call raises a non-MCP exception → verify_ac returns blocked.
    web_driver = _SequenceWebDriver(
        assertions=[passing, passing, passing],
        action_exceptions=[
            RuntimeError("transient driver glitch"),
            None,
            None,
        ],
    )
    capturer = NoOpEvidenceCapturer()
    policy = MaskedSelectorPolicy()
    registry = _make_registry()

    result = iterate_acs(
        plan=plan,
        ac_list=ac_list,
        project_type="web",
        story_id="story-001",
        registry=registry,
        web_driver=web_driver,
        evidence_capturer=capturer,
        masked_selectors=policy,
    )

    assert result.ac_results[0].status == "blocked"
    assert len(result.ac_results) == 3
    assert result.smoke_first_abort is None


# --------------------------------------------------------------------------- #
# AC-5 — plan-absent / plan-ac-list-mismatch loud-fail                        #
# --------------------------------------------------------------------------- #


# 10
def test_iterate_acs_plan_none_raises() -> None:
    """AC-9 #10 — `plan is None` raises `PlanAbsentForIteration` with
    the canonical diagnostic.
    """
    ac_list = _make_ac_list(("AC-1",))
    with pytest.raises(PlanAbsentForIteration) as exc_info:
        iterate_acs(
            plan=None,
            ac_list=ac_list,
            project_type="web",
            story_id="story-001",
            registry=_make_registry(),
            web_driver=NoOpWebDriver(),
            evidence_capturer=NoOpEvidenceCapturer(),
            masked_selectors=MaskedSelectorPolicy(),
        )
    assert exc_info.value.failure_diagnostic == (
        "plan absent: parsed_plan is None"
    )


# 11
def test_iterate_acs_plan_empty_entries_raises() -> None:
    """AC-9 #11 — `plan.entries == ()` raises `PlanAbsentForIteration`
    with the empty-entries diagnostic.
    """
    plan = QABehavioralPlan(
        plan_status="generated",
        ac_hash="0" * 64,
        entries=(),
    )
    ac_list = _make_ac_list(("AC-1",))
    with pytest.raises(PlanAbsentForIteration) as exc_info:
        iterate_acs(
            plan=plan,
            ac_list=ac_list,
            project_type="web",
            story_id="story-001",
            registry=_make_registry(),
            web_driver=NoOpWebDriver(),
            evidence_capturer=NoOpEvidenceCapturer(),
            masked_selectors=MaskedSelectorPolicy(),
        )
    assert exc_info.value.failure_diagnostic == (
        "plan absent: parsed_plan.entries is empty"
    )


# 12
def test_iterate_acs_plan_ac_list_mismatch_raises() -> None:
    """AC-9 #12 — plan ac_ids differ from ac_list ac_ids → raises
    `PlanAbsentForIteration` with the structured mismatch diagnostic.
    """
    plan = _make_plan(("AC-1", "AC-2"))
    ac_list = _make_ac_list(("AC-1", "AC-2", "AC-3"))
    with pytest.raises(PlanAbsentForIteration) as exc_info:
        iterate_acs(
            plan=plan,
            ac_list=ac_list,
            project_type="web",
            story_id="story-001",
            registry=_make_registry(),
            web_driver=NoOpWebDriver(),
            evidence_capturer=NoOpEvidenceCapturer(),
            masked_selectors=MaskedSelectorPolicy(),
        )
    diag = exc_info.value.failure_diagnostic
    assert diag.startswith("plan-ac-list-mismatch:")
    assert "AC-1" in diag and "AC-2" in diag and "AC-3" in diag


# --------------------------------------------------------------------------- #
# AC-6 — project_type / driver-presence validation                            #
# --------------------------------------------------------------------------- #


# 13 — Story 9.3: replaced by class TestMobileDispatch below. The
# pre-Phase-1.5 rejection of project_type="mobile" was the very
# rejection Story 9.3 repairs (per the AC-3 wording: "The existing
# rejection on `project_type='mobile'` ... is REMOVED — it is the
# very rejection this story repairs."). See `class TestMobileDispatch`
# for the Phase-1.5 mobile-dispatch tests that supersede this slot.
class TestMobileDispatch:
    """Story 9.3 AC-3 — `iterate_acs` dispatches to
    :func:`mobile_driver.verify_ac` on the new ``project_type='mobile'``
    branch.

    The four tests (parallel to the existing web/api dispatch tests):

        * ``test_iterate_acs_mobile_happy_path`` — happy-path
          three-AC dispatch through :class:`NoOpMobileDriver`.
        * ``test_iterate_acs_mobile_missing_driver_raises`` —
          ``project_type='mobile'`` with ``mobile_driver=None``
          raises ``ValueError`` naming the missing-driver branch.
        * ``test_iterate_acs_mobile_smoke_first_abort_on_ac1_fail``
          — smoke-first abort fires on AC-1 fail; AC-2 is never
          dispatched.
        * ``test_project_type_enum_extended_to_three_members`` —
          literal-args structural invariant
          ``typing.get_args(ProjectType) == ("web", "api", "mobile")``.
    """

    def test_iterate_acs_mobile_happy_path(self) -> None:
        """``project_type='mobile'`` + ``NoOpMobileDriver`` runs all
        ACs through ``mobile_driver.verify_ac``; every AcResult has
        ``status='pass'`` on the synthetic NoOp path."""
        plan = _make_plan(("AC-1", "AC-2", "AC-3"))
        ac_list = _make_ac_list(("AC-1", "AC-2", "AC-3"))
        elements = (
            MobileElement(
                label=ac_list[0].ac_text,
                x=10,
                y=20,
                width=100,
                height=44,
                role="AXButton",
            ),
            MobileElement(
                label=ac_list[1].ac_text,
                x=10,
                y=80,
                width=100,
                height=44,
                role="AXButton",
            ),
            MobileElement(
                label=ac_list[2].ac_text,
                x=10,
                y=140,
                width=100,
                height=44,
                role="AXButton",
            ),
        )
        mobile_driver = NoOpMobileDriver(
            assert_passed=True, elements=elements
        )
        capturer = NoOpEvidenceCapturer()
        registry = _make_registry()

        result = iterate_acs(
            plan=plan,
            ac_list=ac_list,
            project_type="mobile",
            story_id="story-001",
            registry=registry,
            mobile_driver=mobile_driver,
            evidence_capturer=capturer,
            masked_selectors=MaskedSelectorPolicy(),
        )

        assert len(result.ac_results) == 3
        for ac_result in result.ac_results:
            assert ac_result.status == "pass"
            # FR19 evidence-triple invariant: ≥ 1 evidence_ref on every AC.
            assert len(ac_result.evidence_refs) >= 1
        assert result.smoke_first_abort is None
        assert result.project_type == "mobile"

    def test_iterate_acs_mobile_missing_driver_raises(self) -> None:
        """``project_type='mobile'`` with ``mobile_driver=None``
        raises ``ValueError`` naming the missing-driver branch
        (parallel to the existing web/api missing-driver tests)."""
        plan = _make_plan(("AC-1",))
        ac_list = _make_ac_list(("AC-1",))
        with pytest.raises(
            ValueError, match=r"project_type='mobile' requires mobile_driver"
        ):
            iterate_acs(
                plan=plan,
                ac_list=ac_list,
                project_type="mobile",
                story_id="story-001",
                registry=_make_registry(),
                mobile_driver=None,
                evidence_capturer=NoOpEvidenceCapturer(),
                masked_selectors=MaskedSelectorPolicy(),
            )

    def test_iterate_acs_mobile_smoke_first_abort_on_ac1_fail(self) -> None:
        """AC-1 fail triggers ``surface_smoke_first_abort`` exactly
        like web/api; the result carries a single AC-1 entry with
        ``status='fail'`` AND a ``smoke_first_abort`` record AND no
        AC-2 dispatch."""
        plan = _make_plan(("AC-1", "AC-2"))
        ac_list = _make_ac_list(("AC-1", "AC-2"))
        # NoOpMobileDriver with assert_passed=False makes
        # assert_element_present return passed=False -> AC fails.
        mobile_driver = NoOpMobileDriver(assert_passed=False, elements=())
        capturer = NoOpEvidenceCapturer()
        registry = _make_registry()

        result = iterate_acs(
            plan=plan,
            ac_list=ac_list,
            project_type="mobile",
            story_id="story-001",
            registry=registry,
            mobile_driver=mobile_driver,
            evidence_capturer=capturer,
            masked_selectors=MaskedSelectorPolicy(),
        )

        assert len(result.ac_results) == 1
        assert result.ac_results[0].ac_id == "AC-1"
        assert result.ac_results[0].status == "fail"
        assert result.smoke_first_abort is not None
        assert (
            result.smoke_first_abort.marker_class == SMOKE_FIRST_ABORT_MARKER
        )
        assert result.project_type == "mobile"
        # AC-2 was never dispatched (smoke-first abort).
        recorded_actions = [
            entry[0] for entry in mobile_driver.recorded
        ]
        # Exactly one assert_element_present call (AC-1 only).
        assert recorded_actions.count("assert_element_present") == 1

    def test_project_type_enum_extended_to_three_members(self) -> None:
        """``typing.get_args(qa_ac_iteration.ProjectType) ==
        ("web", "api", "mobile")`` — the literal-args structural
        invariant locking in the enum widening (parallel to how
        Story 9.2 AC-8 locks in ``_PROJECT_TYPES`` invariance)."""
        from typing import get_args

        assert get_args(ProjectType) == ("web", "api", "mobile")


# 14
def test_iterate_acs_project_type_web_with_none_driver_raises() -> None:
    """AC-9 #14 — `project_type="web"` with `web_driver=None` raises
    `ValueError("project_type='web' requires web_driver")`.
    """
    plan = _make_plan(("AC-1",))
    ac_list = _make_ac_list(("AC-1",))
    with pytest.raises(
        ValueError, match=r"project_type='web' requires web_driver"
    ):
        iterate_acs(
            plan=plan,
            ac_list=ac_list,
            project_type="web",
            story_id="story-001",
            registry=_make_registry(),
            web_driver=None,
            evidence_capturer=NoOpEvidenceCapturer(),
            masked_selectors=MaskedSelectorPolicy(),
        )


# 15
def test_iterate_acs_project_type_api_with_none_driver_raises() -> None:
    """AC-9 #15 — `project_type="api"` with `api_driver=None` raises
    `ValueError("project_type='api' requires api_driver")`.
    """
    plan = _make_plan(("AC-1",))
    ac_list = _make_ac_list(("AC-1",))
    with pytest.raises(
        ValueError, match=r"project_type='api' requires api_driver"
    ):
        iterate_acs(
            plan=plan,
            ac_list=ac_list,
            project_type="api",
            story_id="story-001",
            registry=_make_registry(),
            api_driver=None,
            evidence_capturer=NoOpEvidenceCapturer(),
            masked_selectors=MaskedSelectorPolicy(),
        )


# --------------------------------------------------------------------------- #
# AC-1 / AC-2 — frozen + byte-stable model_dump_json                          #
# --------------------------------------------------------------------------- #


# 16
def test_ac_iteration_result_is_frozen_and_byte_stable() -> None:
    """AC-9 #16 — `AcIterationResult` is frozen + `model_dump_json()` is
    byte-stable across two dumps.
    """
    diagnostic = SmokeFirstAbortDiagnosticContext(
        story_id="story-001",
        failed_ac_id="AC-1",
        failed_assertions=("verify: AC-1",),
        failed_evidence_refs=("_bmad-output/qa-evidence/x.txt",),
    )
    record = SmokeFirstAbortEmissionRecord(
        marker_class=SMOKE_FIRST_ABORT_MARKER,
        diagnostic_context=diagnostic,
    )
    from loud_fail_harness.playwright_driver import AcResult
    from loud_fail_harness.qa_evidence_tier import EvidenceRef

    result = AcIterationResult(
        ac_results=(
            AcResult(
                ac_id="AC-1",
                status="fail",
                assertions=("verify: AC-1",),
                evidence_refs=(
                    EvidenceRef(
                        path="_bmad-output/qa-evidence/x.txt",
                        tier="tier-1-mechanical",
                    ),
                ),
                semantic_verification="not_applicable",
            ),
        ),
        smoke_first_abort=record,
        project_type="web",
    )

    # Frozen — assignment to a field raises ValidationError.
    with pytest.raises(ValidationError):
        result.project_type = "api"  # type: ignore[misc]

    dump_a = result.model_dump_json()
    dump_b = result.model_dump_json()
    assert dump_a == dump_b


# --------------------------------------------------------------------------- #
# AC-8 — three envelope fixtures                                              #
# --------------------------------------------------------------------------- #


# 17
def test_qa_ac_iteration_fixtures_validate_against_envelope_schema(
    repo_root: pathlib.Path,
    envelope_schema: dict[str, Any],
) -> None:
    """AC-9 #17 — each of the three AC-8 fixtures validates against the
    envelope schema."""
    fixtures_dir = repo_root / "examples" / "envelopes"
    expected = [
        "qa-fail-smoke-first-abort.yaml",
        "qa-fail-mid-iteration-continue.yaml",
        "qa-pass-multi-ac.yaml",
    ]
    registry = Registry().with_resources(
        [
            (
                "envelope.schema.yaml",
                Resource(
                    contents=envelope_schema, specification=DRAFT202012
                ),
            ),
        ]
    )
    validator = Draft202012Validator(envelope_schema, registry=registry)
    for fixture_name in expected:
        fixture_path = fixtures_dir / fixture_name
        assert fixture_path.exists(), f"missing fixture: {fixture_name}"
        envelope = yaml.safe_load(
            fixture_path.read_text(encoding="utf-8")
        )
        errors = list(validator.iter_errors(envelope))
        assert errors == [], (
            f"{fixture_name} failed validation: {errors}"
        )


# --------------------------------------------------------------------------- #
# Discipline tests                                                            #
# --------------------------------------------------------------------------- #


# 18
def test_qa_ac_iteration_module_has_lf_line_endings(
    repo_root: pathlib.Path,
) -> None:
    """AC-9 #18 — no `\\r` characters in qa_ac_iteration.py source bytes."""
    module_path = (
        repo_root
        / "tools"
        / "loud-fail-harness"
        / "src"
        / "loud_fail_harness"
        / "qa_ac_iteration.py"
    )
    assert b"\r" not in module_path.read_bytes()


# 19
def test_qa_ac_iteration_module_pluggability_clean(
    repo_root: pathlib.Path,
) -> None:
    """AC-9 #19 — the `qa_ac_iteration.py` source does NOT contain
    references to dev-wrapper / review-bmad-wrapper specialist files
    (FR62 pluggability gate compliance verified at the module level).
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
        / "qa_ac_iteration.py"
    )
    module_text = module_path.read_text(encoding="utf-8")
    for token in forbidden:
        assert token not in module_text, (
            f"FR62 pluggability violation: {token!r} appears in "
            "qa_ac_iteration.py"
        )


# --------------------------------------------------------------------------- #
# AC-2 — story-doc-order preservation regression guard                        #
# --------------------------------------------------------------------------- #


# 20
def test_iterate_acs_preserves_story_doc_order_with_non_numeric_ac_ids() -> None:
    """AC-9 #20 — 5-AC plan with AC-id ordering NOT in numeric order
    (e.g., shuffled-internally) but plan.entries order matches ac_list
    order; assert AcResult order in `ac_results` equals plan/ac_list
    order (regression guard against accidental reordering by
    iterating sorted plan_ac_ids set).
    """
    # Story-doc order intentionally NOT numerically sorted.
    ac_ids = ("AC-3", "AC-1", "AC-5", "AC-2", "AC-4")
    plan = _make_plan(ac_ids)
    ac_list = _make_ac_list(ac_ids)
    web_driver = NoOpWebDriver(
        assertion=WebDriverAssertion(
            passed=True, observed="ok", expected="ok"
        )
    )
    capturer = NoOpEvidenceCapturer()
    policy = MaskedSelectorPolicy()
    registry = _make_registry()

    result = iterate_acs(
        plan=plan,
        ac_list=ac_list,
        project_type="web",
        story_id="story-001",
        registry=registry,
        web_driver=web_driver,
        evidence_capturer=capturer,
        masked_selectors=policy,
    )

    assert [r.ac_id for r in result.ac_results] == list(ac_ids)


# --------------------------------------------------------------------------- #
# Bonus: PlaywrightMcpUnavailable + ApiServiceBroken propagate UNCHANGED      #
# --------------------------------------------------------------------------- #


def test_iterate_acs_propagates_playwright_mcp_unavailable_unchanged() -> None:
    """Bonus — Stories 4.4 / 4.5 design contract: mid-run
    `PlaywrightMcpUnavailable` propagates through `iterate_acs` UNCHANGED;
    the iteration framework does NOT catch the exception (the QA
    wrapper's responsibility per Story 4.4 / 4.5 design + Story 4.10
    routing).
    """
    plan = _make_plan(("AC-1",))
    ac_list = _make_ac_list(("AC-1",))
    mcp_registry = MarkerClassRegistry(
        marker_classes=frozenset({"playwright-mcp-unavailable"})
    )
    emission = surface_playwright_mcp_unavailable(
        story_id="story-001",
        registry=mcp_registry,
        action_kind="click",
        prior_evidence_refs=(),
    )
    web_driver = _SequenceWebDriver(
        assertions=[
            WebDriverAssertion(passed=True, observed="ok", expected="ok")
        ],
        action_exceptions=[PlaywrightMcpUnavailable(emission)],
    )
    capturer = NoOpEvidenceCapturer()
    policy = MaskedSelectorPolicy()
    registry = _make_registry()

    with pytest.raises(PlaywrightMcpUnavailable):
        iterate_acs(
            plan=plan,
            ac_list=ac_list,
            project_type="web",
            story_id="story-001",
            registry=registry,
            web_driver=web_driver,
            evidence_capturer=capturer,
            masked_selectors=policy,
        )


def test_iterate_acs_propagates_api_service_broken_unchanged() -> None:
    """Bonus — `ApiServiceBroken` raised by `request` propagates through
    `iterate_acs` UNCHANGED.
    """
    plan = _make_plan(("AC-1",))
    ac_list = _make_ac_list(("AC-1",))
    api_driver = _SequenceApiDriver(
        assertions=[
            ApiAssertion(
                passed=True, observed="200", expected="200", kind="status"
            )
        ],
        action_exceptions=[
            ApiServiceBroken(
                failure_diagnostic="connection refused at port 8000",
            )
        ],
    )
    capturer = NoOpEvidenceCapturer()
    policy = MaskedSelectorPolicy()
    registry = _make_registry()

    with pytest.raises(ApiServiceBroken):
        iterate_acs(
            plan=plan,
            ac_list=ac_list,
            project_type="api",
            story_id="story-001",
            registry=registry,
            api_driver=api_driver,
            evidence_capturer=capturer,
            masked_selectors=policy,
        )
