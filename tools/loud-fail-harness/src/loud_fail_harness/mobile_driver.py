"""Mobile MCP driver substrate library (Story 9.3 — Phase 1.5 mobile QA).

ADR-007 — mobile-next/mobile-mcp (`@mobilenext/mobile-mcp` v0.0.54),
cross-platform unified API for iOS + Android, simulators + emulators
+ real devices. Web-research-validated against
https://github.com/mobile-next/mobile-mcp/blob/main/README.md and
``npm view @mobilenext/mobile-mcp version`` at story-creation time
2026-05-11.

FR17 driver-selection surface widening (``{web, api}`` →
``{web, api, mobile}``) + FR19 evidence-triple invariant + FR20
three-tier evidence (Tier-1 mechanical = a11y-tree snapshot;
Tier-2 outcome = screenshot) + FR62 pluggability invariant
preservation. The QA envelope shape (FR51) is unchanged — only the
``ac_results[i].evidence_refs`` MCP-source widens.

Architectural placement (substrate library NOT a sixth substrate
component): THIS module is a pure-library sibling of Story 4.4's
:mod:`loud_fail_harness.playwright_driver` and Story 4.5's
:mod:`loud_fail_harness.http_driver`. ADR-003 enumerates exactly
five substrate components (architecture.md lines 311-315);
``epics-phase-1.5.md`` line 119 ratifies the closure-at-FIVE rule
("Phase 1.5 must not introduce a sixth substrate component. New
harness checks land as substrate-libraries within existing
components.").

LLM-runtime binding contract: see
``skills/bmad-automation/steps/qa-driver-mobile.md`` for the ten
:class:`MobileDriver` Protocol methods ↔ ``mobile_*`` MCP tool
mappings + provisioner runtime bindings + failure-mode procedures +
the masked-selector policy application algorithm.

``MobileDriver`` method ↔ mobile-mcp v0.0.54 tool surface mapping
(BYTE-IDENTICAL with the step file's mapping table — drift is the
defect):

    +----------------------------+---------------------------------------------+
    | MobileDriver method        | mobile-mcp tool                             |
    +============================+=============================================+
    | launch_app                 | mobile_launch_app                           |
    +----------------------------+---------------------------------------------+
    | terminate_app              | mobile_terminate_app                        |
    +----------------------------+---------------------------------------------+
    | tap_at_coordinates         | mobile_click_on_screen_at_coordinates       |
    +----------------------------+---------------------------------------------+
    | swipe                      | mobile_swipe_on_screen                      |
    +----------------------------+---------------------------------------------+
    | type_text                  | mobile_type_keys                            |
    +----------------------------+---------------------------------------------+
    | press_button               | mobile_press_button                         |
    +----------------------------+---------------------------------------------+
    | screenshot                 | mobile_take_screenshot                      |
    +----------------------------+---------------------------------------------+
    | list_elements_on_screen    | mobile_list_elements_on_screen              |
    +----------------------------+---------------------------------------------+
    | assert_element_present     | mobile_list_elements_on_screen + textual    |
    |                            | comparison                                  |
    +----------------------------+---------------------------------------------+
    | get_screen_size            | mobile_get_screen_size                      |
    +----------------------------+---------------------------------------------+

Deliberately deferred (parallel to FR22's three-heuristic narrowing
rationale — the wrapper composes against a small stable verb set;
future reference-project gaps trigger additions in future stories,
NOT silent inclusion at first cut): ``mobile_install_app``,
``mobile_uninstall_app``, ``mobile_open_url``, ``mobile_list_apps``,
``mobile_list_available_devices``, ``mobile_get_orientation``,
``mobile_set_orientation``, ``mobile_double_tap_on_screen``,
``mobile_long_press_on_screen_at_coordinates``,
``mobile_save_screenshot``.

Rationale for ``env_kind="mobile"`` :class:`ProvisionedEnv` shape
(``port=0``, ``pid=0``, ``health_url=None``):

    * The mobile MCP is an out-of-band npx-stdio process Claude
      Code manages (ADR-007 Consequence 6) — NOT an Automator-
      spawned dev-server subprocess.
    * ``port=0`` and ``pid=0`` reflect "not-applicable" sentinels;
      there is no orchestrator-owned listening socket or process to
      reference.
    * ``health_url=None`` reflects that mobile-mcp exposes no HTTP
      health endpoint — availability is checked via a probe call
      to a cheap MCP tool (e.g. ``mobile_get_screen_size``).
    * The :class:`MobileMcpTeardown` is a NO-OP: the Claude-Code-
      managed npx-stdio process has no Automator-side teardown to
      perform (parallel to :mod:`http_driver` not owning dev-server
      teardown for ephemeral test envs).

Marker class semantics:

    * ``mobile-blocked`` — top-level marker class consumed AS-IS
      from ``schemas/marker-taxonomy.yaml`` line 114 (Phase 1
      taxonomy v1 closed-set; NO MAJOR bump per
      ``epics-phase-1.5.md`` line 120). ``sub_classifications: []``;
      empty.
    * ``mobile-mcp-init-unreachable`` — a SUB-classification of the
      top-level ``env-setup-failed`` marker (NOT a top-level
      class). Mirrors the precedent of
      ``playwright-mcp-init-unreachable``. Story 9.3 MINOR-bumps
      the marker-taxonomy.yaml schema_version to record the
      addition.

Pluggability invariant (FR62 + Story 1.10a gate):

    THIS module imports ONLY from substrate libraries:

        * stdlib (``typing``, ``datetime``)
        * third-party (``pydantic``)
        * :mod:`loud_fail_harness.env_provisioning` (Story 4.3)
        * :mod:`loud_fail_harness.playwright_driver` (Story 4.4 —
          for ``MaskedSelectorPolicy`` + ``AcResult`` +
          ``EvidenceCapturer`` + ``MASKED_REDACTION_SENTINEL``
          re-exports; single source of truth)
        * :mod:`loud_fail_harness.qa_behavioral_plan` (Story 4.1)
        * :mod:`loud_fail_harness.qa_evidence_tier` (Story 4.8)
        * :mod:`loud_fail_harness.specialist_dispatch` (Story 2.6)

    NO imports from ``dev_wrapper``, ``review_bmad_wrapper``,
    ``lad_wrapper`` (future Epic 10), ``bundle_assembly``, or any
    module whose name suggests a wrapper-side surface. The Story
    1.10a pluggability gate fires only on ``agents/<slug>...``
    constructs — substrate-library-to-substrate-library imports
    are gate-safe by construction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Final, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from loud_fail_harness.env_provisioning import (
    EnvKind,
    MarkerEmissionRecord,
    ProvisionedEnv,
)
from loud_fail_harness.playwright_driver import (
    MASKED_REDACTION_SENTINEL,
    AcResult,
    EvidenceCapturer,
    MaskedSelectorPolicy,
)
from loud_fail_harness.qa_behavioral_plan import QABehavioralPlanEntry
from loud_fail_harness.qa_evidence_tier import EvidenceRef
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    validate_marker_emission,
)


# --------------------------------------------------------------------------- #
# Module-level constants                                                      #
# --------------------------------------------------------------------------- #

#: The marker-class string identifier emitted on mid-run mobile MCP
#: unavailability (consumed AS-IS from ``schemas/marker-taxonomy.yaml``
#: line 114 — Phase 1 taxonomy v1 closed-set member). Mirrors Story
#: 4.4's :data:`PLAYWRIGHT_MCP_UNAVAILABLE_MARKER` constant pattern.
MOBILE_BLOCKED_MARKER: Literal["mobile-blocked"] = "mobile-blocked"

#: The ``sub_classification`` value stamped onto the mid-run
#: ``mobile-blocked`` emission by
#: :func:`surface_mobile_mcp_unavailable` (Story 9.5 — narrows the
#: pre-edit ``sub_cause=None`` to the taxonomy 1.5 closed-set member
#: ``"mid-run-unavailable"``). Co-versioned with
#: ``schemas/marker-taxonomy.yaml``'s
#: ``mobile-blocked.sub_classifications`` enumeration (1.4 → 1.5 bump
#: per Story 9.5 added BOTH this value AND ``"init-unavailable"``).
#: The init-time counterpart (``"init-unavailable"``) is consumed by
#: :mod:`loud_fail_harness.init_preconditions` via the
#: ``dependencies.yaml`` ``sub_classification`` declaration on
#: ``mobile-mcp.by_project_type.mobile.profiles.init``, NOT exported
#: here (init-precondition substrate owns its own value resolution
#: via the schema-driven dispatch contract at
#: ``init_preconditions._dispatch_total_block``).
MOBILE_BLOCKED_MID_RUN_SUB_CLASSIFICATION: Final[str] = "mid-run-unavailable"

#: The ``failure_step`` value mirroring the
#: ``env-setup-failed.sub_classifications`` enum member at
#: ``schemas/marker-taxonomy.yaml`` byte-for-byte. Story 4.3's
#: :func:`provision_env` reads this attribute via
#: ``getattr(exc, "failure_step", "dev-server-not-ready")`` and
#: routes through :func:`surface_env_setup_failure` with the value
#: as ``sub_cause``. Parallel to Story 4.4's
#: ``_PLAYWRIGHT_LAUNCH_FAILED_STEP`` precedent.
_MOBILE_MCP_INIT_UNREACHABLE_STEP: Literal["mobile-mcp-init-unreachable"] = (
    "mobile-mcp-init-unreachable"
)


def _apply_masked_selector_policy_mobile(
    text: str,
    policy: MaskedSelectorPolicy,
) -> str:
    """Apply mobile-specific :class:`MaskedSelectorPolicy` redaction.

    Distinct from :func:`playwright_driver._apply_masked_selector_policy`
    in that mobile a11y trees do NOT use CSS selectors — the selector
    entries are interpreted as **a11y-label substrings** (per the step
    file at ``skills/bmad-automation/steps/qa-driver-mobile.md`` §
    ``## MaskedSelectorPolicy runtime application``). The algorithm is
    deliberately simpler than the web-DOM heuristic: plain literal
    substring replacement on the textual rendering of the payload.

    Empty :attr:`MaskedSelectorPolicy.masked_selectors` returns the
    text verbatim (no redaction).

    .. warning::
        Matching is **case-sensitive** (Python ``str.replace``
        semantics). A selector of ``"Password"`` will NOT redact
        ``"password input field"``. Practitioners must match the
        exact casing of the a11y label returned by
        ``mobile_list_elements_on_screen``.
    """
    if not policy.masked_selectors:
        return text
    redacted = text
    for selector in policy.masked_selectors:
        if not selector:
            continue
        redacted = redacted.replace(selector, MASKED_REDACTION_SENTINEL)
    return redacted


# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class MobileDriverAssertion(BaseModel):
    """One assertion-record returned by
    :meth:`MobileDriver.assert_element_present`.

    Frozen for hashability + determinism per Epic 1 retro Action #2.
    Field declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.

    Field semantics (parallel to :class:`WebDriverAssertion`):
        * ``passed`` — bool; ``True`` iff the assertion held.
        * ``observed`` — the actual a11y-label observed on the
          screen (joined comma-separated list of present labels
          when no exact match; empty string when the a11y-tree
          carries no labels at all).
        * ``expected`` — the a11y-label substring the assertion
          required.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    observed: str
    expected: str


class MobileElement(BaseModel):
    """One a11y-tree element record returned by
    :meth:`MobileDriver.list_elements_on_screen`.

    Mirrors the ``mobile_list_elements_on_screen`` tool's per-element
    payload shape: ``{label, x, y, width, height, role}``. The
    ``label`` and ``role`` fields are :data:`None` when the mobile
    a11y tree does NOT carry them — typical for ProseMirror /
    canvas / image-only views; per the mobile-mcp README "uses
    native accessibility trees for most interactions, or screenshot
    based coordinates where a11y labels are not available."

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``label`` — optional human-readable a11y-label string;
          :data:`None` when absent.
        * ``x``, ``y`` — pixel coordinates of the element's
          top-left corner relative to the device screen origin.
        * ``width``, ``height`` — pixel dimensions of the element's
          bounding box.
        * ``role`` — optional a11y-role string (e.g.,
          ``"AXButton"`` on iOS, ``"android.widget.Button"`` on
          Android); :data:`None` when absent.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str | None
    x: int
    y: int
    width: int
    height: int
    role: str | None


class MobileMcpUnavailableDiagnostic(BaseModel):
    """The structured diagnostic context carried on the
    ``mobile-blocked`` marker emission AND surfaced through Story
    4.10's escalation routing.

    Parallel to :class:`PlaywrightMcpUnavailableDiagnostic` byte-
    for-byte in shape (three required fields with the same types
    and the same min-length constraints).

    Frozen for hashability + determinism. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``story_id`` — the BMAD story identifier the QA dispatch
          is scoped to.
        * ``action_kind`` — the failed driver-action name (one of
          ``launch_app | terminate_app | tap_at_coordinates |
          swipe | type_text | press_button | screenshot |
          list_elements_on_screen | assert_element_present |
          get_screen_size``); free-form string at the substrate
          layer to avoid coupling to the ten-method enum (the
          LLM-runtime protocol owns the enum closure; the
          substrate accepts the failed-action name from the
          wrapper).
        * ``prior_evidence_refs`` — tuple of repo-relative paths
          for evidence the QA wrapper had already captured BEFORE
          the mid-run unavailability fired. Preserved per the
          mobile-parallel of the verbatim epic AC at epics.md line
          1912 ("evidence already captured is preserved").
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    story_id: str = Field(min_length=1)
    action_kind: str = Field(min_length=1)
    prior_evidence_refs: tuple[str, ...]


class MobileMcpUnavailableEmission(BaseModel):
    """The two-channel atomic-emission return shape of
    :func:`surface_mobile_mcp_unavailable`.

    Channels are paired by construction — both ``marker_record`` and
    ``diagnostic`` are present on a successful unavailability
    emission; registry rejection raises
    :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
    BEFORE either is constructed (atomic-on-failure per Pattern 5;
    mirrors Story 4.4's :class:`PlaywrightMcpUnavailableEmission`
    verbatim).

    Frozen for determinism + hashability. Field declaration order is
    load-bearing for byte-stable ``model_dump_json()`` output.

    Field semantics:
        * ``marker_record`` — the
          :class:`loud_fail_harness.env_provisioning.MarkerEmissionRecord`
          carrying ``marker_class="mobile-blocked"`` +
          ``sub_cause=MOBILE_BLOCKED_MID_RUN_SUB_CLASSIFICATION``
          (``"mid-run-unavailable"`` per taxonomy v1.5 — Story 9.5
          closed ``mobile-blocked.sub_classifications`` to
          ``[init-unavailable, mid-run-unavailable]``) + the
          diagnostic-projected ``context``.
        * ``diagnostic`` — the
          :class:`MobileMcpUnavailableDiagnostic` carrying the
          three-field structured context. Co-exposed for ergonomic
          access without unwrapping ``marker_record``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    marker_record: MarkerEmissionRecord
    diagnostic: MobileMcpUnavailableDiagnostic


# --------------------------------------------------------------------------- #
# Protocols                                                                   #
# --------------------------------------------------------------------------- #


@runtime_checkable
class MobileMcpAvailabilityProbe(Protocol):
    """Project-type-specific mobile MCP availability probe.

    Production binds to a mobile-MCP-tool-call probe at the LLM-
    runtime layer per the
    ``skills/bmad-automation/steps/qa-driver-mobile.md`` step file
    (one MCP-tool ping — e.g., ``mobile_get_screen_size()``; on
    tool-error / tool-absence / timeout return ``False``; on clean
    tool-call return ``True``); tests use
    :class:`NoOpMobileMcpAvailabilityProbe`.
    """

    def is_available(self) -> bool:
        """Return ``True`` iff mobile MCP is reachable; ``False``
        otherwise (including any tool-error or absence condition).
        """


@runtime_checkable
class MobileDriver(Protocol):
    """The ten driver-action abstraction the QA wrapper composes
    against the running mobile app per Story 9.3 AC-2.

    Production implementations bind each method to the corresponding
    ``mobile_*`` MCP tool at the LLM-runtime layer per the step file
    at ``skills/bmad-automation/steps/qa-driver-mobile.md``; tests
    use :class:`NoOpMobileDriver`.

    Narrow choice (MVP-Phase-1.5 minimum slice; parallel to FR22's
    three-heuristic narrowing rationale): ten methods is the
    minimum needed to compose against typical mobile-app QA flows
    (launch → interact → assert → screenshot); ``mobile_install_app``
    / ``mobile_uninstall_app`` / ``mobile_open_url`` / ``mobile_list_apps``
    / ``mobile_list_available_devices`` / orientation /
    double-tap / long-press / ``mobile_save_screenshot`` are
    deliberately deferred (recorded in the module docstring above).

    Method ↔ tool surface mapping (recorded byte-for-byte in the
    module docstring above and the step file's
    ``## Procedure — MobileDriver Protocol ↔ MCP tool mappings``
    section).
    """

    def launch_app(self, package_name: str) -> None:
        """Launch the app identified by Android package name or iOS
        bundle identifier ``package_name``. Required to bring the
        app under test to foreground at AC-iteration start;
        parallel to :meth:`WebDriver.navigate`.
        """

    def terminate_app(self, package_name: str) -> None:
        """Terminate the running app identified by ``package_name``.
        Required for teardown-between-ACs (when the plan declares
        so); NOT called by default.
        """

    def tap_at_coordinates(self, x: int, y: int) -> None:
        """Tap the device screen at pixel coordinates ``(x, y)``.

        Mobile's ``click`` analog. Coordinates because mobile-mcp's
        primary interaction modality is coordinate-based —
        accessibility labels are not always available; the wrapper
        resolves coordinates via :meth:`list_elements_on_screen`.
        """

    def swipe(self, direction: Literal["up", "down", "left", "right"]) -> None:
        """Swipe the device screen in ``direction``. Mobile's
        gesture surface; no web analog.
        """

    def type_text(self, text: str, *, submit: bool = False) -> None:
        """Type ``text`` into the currently-focused element on the
        device. Depends on a focused element (typically following
        :meth:`tap_at_coordinates` on an input field). On
        ``submit=True`` send the platform's submit keycode after
        the text.
        """

    def press_button(
        self,
        button: Literal["HOME", "BACK", "ENTER", "VOLUME_UP", "VOLUME_DOWN"],
    ) -> None:
        """Press the hardware ``button`` on the device. The
        narrowed enum captures the buttons MVP-Phase-1.5 reference
        flows need; future stories may extend.
        """

    def screenshot(self, name: str) -> str:
        """Capture a screenshot named ``name``; return the repo-
        relative evidence_ref path the screenshot was persisted to
        (parallel to :meth:`WebDriver.screenshot`).
        """

    def list_elements_on_screen(self) -> tuple[MobileElement, ...]:
        """Return the tuple of :class:`MobileElement` records the
        mobile a11y tree carries for the current screen. THIS is
        the Tier-1 mechanical evidence surface (FR20) — the
        structured a11y-tree snapshot.
        """

    def assert_element_present(self, label: str) -> MobileDriverAssertion:
        """Compare the a11y-tree's element labels against
        ``label``; return the :class:`MobileDriverAssertion`
        record. Mobile's ``assert_dom_text`` analog.
        """

    def get_screen_size(self) -> tuple[int, int]:
        """Return the device screen's ``(width, height)`` in
        pixels. Required for coordinate-resolution sanity checks
        (e.g., a tap at ``(-1, -1)`` is structurally invalid);
        useful at provision-time to confirm a device is connected.
        """


# --------------------------------------------------------------------------- #
# Exceptions                                                                  #
# --------------------------------------------------------------------------- #


class MobileMcpLaunchFailed(Exception):
    """Raised by :meth:`MobileMcpProvisioner.provision` when the
    injected :class:`MobileMcpAvailabilityProbe` returns ``False``
    AT init-time-of-provisioning.

    Pattern 5 named-invariant diagnostic. The ``failure_step``
    attribute mirrors the
    ``env-setup-failed.sub_classifications`` enum member at
    ``schemas/marker-taxonomy.yaml`` byte-for-byte (added by Story
    9.3 alongside this exception); Story 4.3's
    :func:`provision_env` reads the attribute via
    ``getattr(exc, "failure_step", "dev-server-not-ready")`` and
    routes through
    :func:`loud_fail_harness.env_provisioning.surface_env_setup_failure`
    with ``sub_cause="mobile-mcp-init-unreachable"``.

    Distinct from :exc:`MobileMcpUnavailable` which surfaces
    MID-RUN MCP unavailability AFTER provisioning succeeded;
    :exc:`MobileMcpLaunchFailed` is the AT-INIT-time variant that
    flows through the env-setup-failed marker class instead.
    """

    failure_step: Literal["mobile-mcp-init-unreachable"] = (
        _MOBILE_MCP_INIT_UNREACHABLE_STEP
    )


class MobileMcpUnavailable(Exception):
    """Raised by the QA wrapper on a mid-run mobile MCP tool-call
    exception.

    Pattern 5 named-invariant diagnostic. Carries the structured
    :class:`MobileMcpUnavailableEmission` so the LLM-runtime
    protocol's catch site has the marker_record + diagnostic in
    hand for Story 4.10's escalation routing without unwrapping the
    exception further.

    Distinct from :exc:`MobileMcpLaunchFailed` which fires AT-INIT-
    time-of-provisioning; this exception fires MID-RUN AFTER
    provisioning succeeded but before AC verification completed.

    Attributes:
        emission: The :class:`MobileMcpUnavailableEmission`
            carrying the marker_record + diagnostic.
    """

    def __init__(self, emission: MobileMcpUnavailableEmission) -> None:
        self.emission: MobileMcpUnavailableEmission = emission
        super().__init__(
            f"mobile MCP unavailable mid-run: action_kind="
            f"{emission.diagnostic.action_kind!r}; "
            f"prior_evidence_refs="
            f"{emission.diagnostic.prior_evidence_refs!r}"
        )


# --------------------------------------------------------------------------- #
# No-op test doubles                                                          #
# --------------------------------------------------------------------------- #


class NoOpMobileMcpAvailabilityProbe:
    """Reference :class:`MobileMcpAvailabilityProbe` implementation
    for the test suite ONLY.

    Returns the constructor-supplied ``available`` boolean from
    every :meth:`is_available` call. Accepts the ergonomic
    ``returns_false=True`` alias used by the Story 9.3 AC-7 tests.

    NOT for production use — the LLM-runtime protocol at
    ``skills/bmad-automation/steps/qa-driver-mobile.md`` ships the
    real MCP-tool-ping binding.
    """

    def __init__(
        self, *, available: bool = True, returns_false: bool = False
    ) -> None:
        self._available = available and not returns_false

    def is_available(self) -> bool:
        return self._available


class NoOpMobileDriver:
    """Reference :class:`MobileDriver` implementation for the test
    suite ONLY.

    Records every action invocation in :attr:`recorded` (list of
    ``(action_kind, args, kwargs)`` tuples) and returns deterministic
    synthetic responses parallel to :class:`NoOpWebDriver`. The
    constructor-supplied ``assert_passed`` flag controls the
    ``passed`` field of
    :meth:`assert_element_present`'s returned
    :class:`MobileDriverAssertion`; the ``elements`` tuple controls
    :meth:`list_elements_on_screen`'s return.

    NOT for production use — the LLM-runtime protocol at
    ``skills/bmad-automation/steps/qa-driver-mobile.md`` ships the
    real ``mobile_*`` MCP tool bindings.
    """

    def __init__(
        self,
        *,
        assert_passed: bool = True,
        elements: tuple[MobileElement, ...] = (),
        screen_size: tuple[int, int] = (1170, 2532),
    ) -> None:
        self._assert_passed = assert_passed
        self._elements = elements
        self._screen_size = screen_size
        self.recorded: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def launch_app(self, package_name: str) -> None:
        self.recorded.append(("launch_app", (package_name,), {}))

    def terminate_app(self, package_name: str) -> None:
        self.recorded.append(("terminate_app", (package_name,), {}))

    def tap_at_coordinates(self, x: int, y: int) -> None:
        self.recorded.append(("tap_at_coordinates", (x, y), {}))

    def swipe(self, direction: Literal["up", "down", "left", "right"]) -> None:
        self.recorded.append(("swipe", (direction,), {}))

    def type_text(self, text: str, *, submit: bool = False) -> None:
        self.recorded.append(("type_text", (text,), {"submit": submit}))

    def press_button(
        self,
        button: Literal["HOME", "BACK", "ENTER", "VOLUME_UP", "VOLUME_DOWN"],
    ) -> None:
        self.recorded.append(("press_button", (button,), {}))

    def screenshot(self, name: str) -> str:
        self.recorded.append(("screenshot", (name,), {}))
        return f"_bmad-output/qa-evidence/noop-mobile/{name}.png"

    def list_elements_on_screen(self) -> tuple[MobileElement, ...]:
        self.recorded.append(("list_elements_on_screen", (), {}))
        return self._elements

    def assert_element_present(self, label: str) -> MobileDriverAssertion:
        self.recorded.append(("assert_element_present", (label,), {}))
        observed = ",".join(
            element.label for element in self._elements if element.label is not None
        )
        return MobileDriverAssertion(
            passed=self._assert_passed,
            observed=observed,
            expected=label,
        )

    def get_screen_size(self) -> tuple[int, int]:
        self.recorded.append(("get_screen_size", (), {}))
        return self._screen_size


# --------------------------------------------------------------------------- #
# Provisioner + Teardown                                                      #
# --------------------------------------------------------------------------- #


class MobileMcpProvisioner:
    """Project-type-specific (mobile) :class:`Provisioner` Protocol
    implementation.

    Composes the injected :class:`MobileMcpAvailabilityProbe` to
    surface AT-init-time availability of the mobile MCP. Distinct
    from :class:`PlaywrightProvisioner` and :class:`HttpProvisioner`
    in that NO dev-server subprocess is spawned — the mobile MCP is
    an out-of-band npx-stdio process Claude Code manages (ADR-007
    Consequence 6).

    Behavior:

        1. Call ``self._availability_probe.is_available()``; on
           ``False``, raise :exc:`MobileMcpLaunchFailed` carrying
           ``failure_step="mobile-mcp-init-unreachable"`` so Story
           4.3's :func:`provision_env` catches it via
           ``getattr(exc, "failure_step", "dev-server-not-ready")``
           and routes through
           :func:`loud_fail_harness.env_provisioning.surface_env_setup_failure`
           with ``sub_cause="mobile-mcp-init-unreachable"``.
        2. On availability ``True``, construct and return a
           :class:`ProvisionedEnv` carrying ``env_kind="mobile"``
           + ``port=0`` + ``pid=0`` (not-applicable sentinels —
           there is no orchestrator-owned listening socket or
           process) + a non-null timezone-aware UTC ``started_at``
           timestamp + ``health_url=None`` (mobile-mcp exposes no
           HTTP health endpoint).

    The class structurally satisfies Story 4.3's
    :class:`Provisioner` Protocol —
    ``isinstance(provisioner, Provisioner)`` returns ``True``
    because :class:`Provisioner` is ``@runtime_checkable``. The
    ``provision(self, story_id, project_type, port)`` signature
    accepts default values so callers may also invoke
    ``provisioner.provision()`` directly (the Story 9.3 AC-7 test
    convention).

    Atomic-on-failure: the probe fires BEFORE any
    :class:`ProvisionedEnv` is constructed; on probe-false the
    return-path is NEVER entered — verified by AC-7's
    ``test_mobile_provisioner_probe_false_raises_launch_failed``.
    """

    def __init__(self, probe: MobileMcpAvailabilityProbe) -> None:
        self._availability_probe = probe

    def provision(
        self,
        story_id: str = "",
        project_type: EnvKind = "mobile",
        port: int = 0,
    ) -> ProvisionedEnv:
        """Compose the project-type-specific (mobile) provisioning.

        Args:
            story_id: BMAD story identifier (signature-symmetric
                with Story 4.3's :class:`Provisioner` Protocol;
                threaded through for downstream visibility — but
                the mobile provisioner has no log-side use for it).
                Default empty string for direct-call ergonomics.
            project_type: ``"mobile"`` (default); accepted for
                Provisioner-Protocol signature symmetry. The
                returned :class:`ProvisionedEnv` always carries
                ``env_kind="mobile"`` regardless of the input —
                this Provisioner is mobile-specific.
            port: Ignored (mobile MCP exposes no port). Default 0.
                Accepted for Provisioner-Protocol signature
                symmetry.

        Returns:
            :class:`ProvisionedEnv` carrying ``env_kind="mobile"``,
            ``port=0``, ``pid=0``, ``started_at`` non-null
            timezone-aware UTC datetime, ``health_url=None``.

        Raises:
            :exc:`MobileMcpLaunchFailed`: the availability probe
                returned ``False``; the ``failure_step`` attribute
                is ``"mobile-mcp-init-unreachable"`` byte-for-byte.
        """
        _ = story_id  # Sensor-not-advisor: signature-symmetric with the protocol.
        _ = project_type  # Mobile provisioner always emits env_kind="mobile".
        _ = port  # Mobile MCP is npx-stdio-managed; no port.
        if not self._availability_probe.is_available():
            raise MobileMcpLaunchFailed(
                "Mobile MCP unavailable at provisioning time"
            )
        return ProvisionedEnv(
            env_kind="mobile",
            port=0,
            pid=0,
            started_at=datetime.now(timezone.utc),
            health_url=None,
        )


class MobileMcpTeardown:
    """Project-type-specific (mobile) :class:`Teardown` Protocol
    implementation.

    A NO-OP: the Claude-Code-managed npx-stdio mobile MCP process
    has no Automator-side teardown to perform (parallel to how
    :mod:`http_driver` does not own dev-server teardown for
    ephemeral test envs the orchestrator did not spawn).

    The class structurally satisfies Story 4.3's :class:`Teardown`
    Protocol.
    """

    def teardown(self, provisioned_env: ProvisionedEnv) -> None:
        """Return immediately — Mobile MCP is Claude-Code-managed
        (NOT Automator-spawned), so there is no Automator-side
        process to terminate.
        """
        _ = provisioned_env  # Sensor-not-advisor: no teardown side-effects.
        return None


# --------------------------------------------------------------------------- #
# verify_ac                                                                   #
# --------------------------------------------------------------------------- #


def verify_ac(
    ac_id: str,
    ac_text: str,
    plan_entry: QABehavioralPlanEntry,
    driver: MobileDriver,
    evidence_capturer: EvidenceCapturer,
    masked_selectors: MaskedSelectorPolicy,
    /,
) -> AcResult:
    """Compose the per-AC verification primitive for ``project_type="mobile"``.

    Behavior (parallel to Story 4.4's
    :func:`loud_fail_harness.playwright_driver.verify_ac`):

        * Dispatch the appropriate :class:`MobileDriver` action per
          the plan entry's ``assertion_shape``. THIS story's MVP
          placeholder dispatch routes every plan entry through
          :meth:`MobileDriver.assert_element_present` against the
          AC text (parallel to web's
          :meth:`WebDriver.assert_dom_text` dispatch); Story 9.4 +
          future iterations thicken the dispatcher with a richer
          ``assertion_shape``-driven router.
        * Capture mechanical Tier-1 evidence (a11y-tree snapshot)
          AND outcome Tier-2 evidence (screenshot) via
          ``evidence_capturer.capture(action_kind, payload)`` —
          mobile is the FIRST driver to capture two evidence tiers
          at the substrate layer (FR20). The web/api drivers
          capture only Tier-1; their Tier-2 elevation is wrapper-
          composed.
        * Construct and return the :class:`AcResult` per the
          ``$defs/ac_result`` envelope shape:
            - ``status="pass"`` iff the dispatched assertion held
              AND ≥ 1 evidence_ref was captured.
            - ``status="fail"`` if the assertion did NOT hold.
            - ``status="blocked"`` if the dispatched action raised a
              non-:exc:`MobileMcpUnavailable` exception (mid-run
              MCP unavailability is the QA wrapper's responsibility
              to catch and route through
              :func:`surface_mobile_mcp_unavailable`; THIS
              function does not catch it).

    The function does NOT itself emit markers, write to
    ``run-state.yaml``, or read TEA artifacts (FR16 invariant;
    structurally encoded by the function's argument list excluding
    TEA-related shapes).

    Args:
        ac_id: The AC identifier (e.g., ``"AC-1"``); written
            verbatim to the returned :class:`AcResult.ac_id`.
        ac_text: The AC's verbatim text from the dispatch payload's
            ``ac_list``; used at the MVP placeholder dispatcher as
            the ``label`` argument to
            :meth:`MobileDriver.assert_element_present`.
        plan_entry: The
            :class:`loud_fail_harness.qa_behavioral_plan.QABehavioralPlanEntry`
            for THIS AC; carries the ``assertion_shape`` +
            ``expected_evidence_tier`` (consumed by future stories
            for richer dispatch; THIS MVP dispatcher reads the
            ``assertion_shape`` for the human-readable assertion
            string only).
        driver: The :class:`MobileDriver` Protocol implementation;
            production binds to the ``mobile_*`` MCP tool surface
            per the step file at
            ``skills/bmad-automation/steps/qa-driver-mobile.md``;
            tests use :class:`NoOpMobileDriver`.
        evidence_capturer: The :class:`EvidenceCapturer` Protocol
            implementation; production writes to disk under
            ``_bmad-output/qa-evidence/{story-id}/{run-id}/``;
            tests use :class:`NoOpEvidenceCapturer`.
        masked_selectors: The :class:`MaskedSelectorPolicy` consumed
            by the :class:`EvidenceCapturer` to redact sensitive
            content. Threaded through so the ``verify_ac`` signature
            structurally encodes the redaction commitment.

    Returns:
        :class:`AcResult` whose ``model_dump()`` JSON projection
        mirrors ``schemas/envelope.schema.yaml`` ``$defs/ac_result``
        byte-for-byte.
    """
    # Mobile-specific masked-selector redaction is applied at THIS layer
    # (distinct from web's CSS-DOM heuristic) per the step file's
    # ``## MaskedSelectorPolicy runtime application`` section — selectors
    # are interpreted as a11y-label substrings, and substring matches in
    # the textual payload are redacted BEFORE the payload reaches the
    # EvidenceCapturer. The capturer may apply additional redaction
    # idempotently.
    assertion_str = (
        plan_entry.assertion_shape
        if plan_entry.assertion_shape
        else f"verify: {ac_text}"
    )

    try:
        assertion = driver.assert_element_present(ac_text)
    except MobileMcpUnavailable:
        # Mid-run MCP unavailability is the QA wrapper's responsibility
        # to catch and route through surface_mobile_mcp_unavailable.
        # THIS function does NOT catch it — propagate unchanged.
        raise
    except Exception as exc:
        # Non-MCP exception during AC verification — verification cannot
        # complete; status="blocked" with the exception's diagnostic
        # captured for downstream visibility. Guard against the
        # capturer itself raising so the original driver error is
        # preserved in the assertions tuple.
        try:
            evidence_ref = evidence_capturer.capture(
                "blocked-diagnostic",
                f"verify_ac aborted on driver action: {exc!r}",
            )
        except Exception:
            evidence_ref = (
                f"_bmad-output/qa-evidence/capturer-unavailable/{ac_id}.txt"
            )
        return AcResult(
            ac_id=ac_id,
            status="blocked",
            assertions=(assertion_str, f"blocked: {exc!r}"),
            evidence_refs=(
                EvidenceRef(path=evidence_ref, tier="tier-1-mechanical"),
            ),
            semantic_verification="not_applicable",
        )

    # Capture mechanical Tier-1 evidence (a11y-tree snapshot) AND
    # outcome Tier-2 evidence (screenshot) regardless of pass/fail so
    # the ac_results record always carries ≥ 1 evidence_ref per the
    # FR19 triple-invariant.
    a11y_payload = _apply_masked_selector_policy_mobile(
        f"observed={assertion.observed!r} expected={assertion.expected!r}",
        masked_selectors,
    )
    try:
        a11y_ref = evidence_capturer.capture("a11y-tree-snapshot", a11y_payload)
    except Exception:
        a11y_ref = (
            f"_bmad-output/qa-evidence/capturer-unavailable/{ac_id}-a11y.txt"
        )
    try:
        screenshot_ref = driver.screenshot(f"{ac_id}-screenshot")
    except Exception:
        screenshot_ref = (
            f"_bmad-output/qa-evidence/capturer-unavailable/{ac_id}.png"
        )

    evidence_refs = (
        EvidenceRef(path=a11y_ref, tier="tier-1-mechanical"),
        EvidenceRef(path=screenshot_ref, tier="tier-2-outcome"),
    )

    if assertion.passed:
        return AcResult(
            ac_id=ac_id,
            status="pass",
            assertions=(assertion_str,),
            evidence_refs=evidence_refs,
            semantic_verification="not_applicable",
        )

    return AcResult(
        ac_id=ac_id,
        status="fail",
        assertions=(
            assertion_str,
            f"observed={assertion.observed!r} expected={assertion.expected!r}",
        ),
        evidence_refs=evidence_refs,
        semantic_verification="not_applicable",
    )


# --------------------------------------------------------------------------- #
# surface_mobile_mcp_unavailable                                              #
# --------------------------------------------------------------------------- #


def surface_mobile_mcp_unavailable(
    story_id: str,
    registry: MarkerClassRegistry,
    *,
    action_kind: str,
    prior_evidence_refs: tuple[str, ...],
) -> MobileMcpUnavailableEmission:
    """Surface mid-run mobile MCP unavailability across both channels
    atomically.

    THIS function is the SINGLE source-of-truth emission path for
    the two-channel projection of a mid-run mobile MCP unavailability
    event (FR17 + ADR-002 graceful-degrade + ADR-007 server
    selection). Composes Story 2.6's
    :func:`validate_marker_emission`. Pure: no file I/O, no run-
    state writes, no event emissions (the marker record is data the
    caller consumes; it is NOT emitted to the orchestrator-event log
    by THIS function).

    Behavior (parallel to Story 4.4's
    :func:`loud_fail_harness.playwright_driver.surface_playwright_mcp_unavailable`
    verbatim):

        * **Step 1 — Validate marker emission FIRST.** Calls
          :func:`validate_marker_emission(registry,
          MOBILE_BLOCKED_MARKER)`. On registry rejection
          :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`
          propagates per Pattern 5; NO partial state is constructed
          (atomic-on-failure; mirrors Stories 3.3 / 4.2 / 4.3 / 4.4).
        * **Step 2 — Construct the diagnostic context** carrying
          the three required fields ``(story_id, action_kind,
          prior_evidence_refs)``.
        * **Step 3 — Construct the marker emission record** with
          ``marker_class="mobile-blocked"``,
          ``sub_cause=MOBILE_BLOCKED_MID_RUN_SUB_CLASSIFICATION``
          (``"mid-run-unavailable"`` per taxonomy v1.5; Story 9.5
          closed ``mobile-blocked.sub_classifications`` to
          ``[init-unavailable, mid-run-unavailable]``), and the
          diagnostic-projected ``context``.
        * **Step 4 — Return the** :class:`MobileMcpUnavailableEmission`
          carrying both projections.

    Args:
        story_id: BMAD story identifier (mirrors Story 4.4's
            :func:`surface_playwright_mcp_unavailable` parameter;
            threaded into the diagnostic context).
        registry: The runtime :class:`MarkerClassRegistry` from
            :func:`loud_fail_harness.specialist_dispatch.load_marker_class_registry`;
            must contain the ``mobile-blocked`` marker class.
        action_kind: The failed driver-action name (one of
            ``launch_app | terminate_app | tap_at_coordinates |
            swipe | type_text | press_button | screenshot |
            list_elements_on_screen | assert_element_present |
            get_screen_size``). Free-form string at the substrate
            layer to avoid coupling to the ten-method enum (the
            LLM-runtime protocol owns the enum closure).
        prior_evidence_refs: Tuple of repo-relative evidence-path
            strings the QA wrapper had already captured BEFORE the
            mid-run unavailability fired. Preserved verbatim.

    Returns:
        :class:`MobileMcpUnavailableEmission` carrying
        ``marker_record`` + ``diagnostic``.

    Raises:
        :exc:`loud_fail_harness.specialist_dispatch.UnknownMarkerClass`:
            registry does not contain ``"mobile-blocked"``.
    """
    validate_marker_emission(registry, MOBILE_BLOCKED_MARKER)
    diagnostic = MobileMcpUnavailableDiagnostic(
        story_id=story_id,
        action_kind=action_kind,
        prior_evidence_refs=prior_evidence_refs,
    )
    marker_record = MarkerEmissionRecord(
        marker_class=MOBILE_BLOCKED_MARKER,
        sub_cause=MOBILE_BLOCKED_MID_RUN_SUB_CLASSIFICATION,
        context=diagnostic.model_dump(mode="json"),
    )
    return MobileMcpUnavailableEmission(
        marker_record=marker_record,
        diagnostic=diagnostic,
    )


__all__ = [
    "MASKED_REDACTION_SENTINEL",
    "MOBILE_BLOCKED_MARKER",
    "MOBILE_BLOCKED_MID_RUN_SUB_CLASSIFICATION",
    "AcResult",
    "EvidenceCapturer",
    "MaskedSelectorPolicy",
    "MobileDriver",
    "MobileDriverAssertion",
    "MobileElement",
    "MobileMcpAvailabilityProbe",
    "MobileMcpLaunchFailed",
    "MobileMcpProvisioner",
    "MobileMcpTeardown",
    "MobileMcpUnavailable",
    "MobileMcpUnavailableDiagnostic",
    "MobileMcpUnavailableEmission",
    "NoOpMobileDriver",
    "NoOpMobileMcpAvailabilityProbe",
    "surface_mobile_mcp_unavailable",
    "verify_ac",
]
