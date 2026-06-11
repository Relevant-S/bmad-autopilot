"""Story 9.4 — Mobile exploratory-heuristic specification table.

The pure-library substrate module owning the closed six-spec mobile-
heuristic specification (FR22 mobile-parity extension + FR-P1.5-2;
expanded 3 → 6 at Story 19.2 per the ADR-010 / FR-P2-5 applicability
matrix). Each spec re-binds a mobile-specific scenario to one of the
:data:`loud_fail_harness.qa_exploratory_heuristics.HeuristicKind` Literal
values. Mobile drives SIX of the seven heuristics:
``rate-limit-boundary`` is EXCLUDED on mobile per the ADR-010 matrix —
rapid-request driving is impractical through the mobile-MCP v0.0.54 UI
verb surface (there is no rapid-request primitive in the ten-method
:class:`MobileDriver` Protocol), so its omission is a SILENT matrix
exclusion (NO ``heuristic-skipped`` emission), NOT a structural skip.
The marker-taxonomy ``heuristic-skipped.sub_classifications`` PATCH-bumps
1.12 → 1.13 for the four additions (Story 19.2); the top-level marker-
class closed-set is preserved.

The spec is *data*: an immutable six-entry table consumed by the QA
wrapper at AC-iteration time per the LLM-runtime binding contract at
``skills/bmad-automation/steps/qa-mobile-heuristics.md``. Verb-level
heuristic driving (clicking the empty-state UI, forcing the
network-error state, exercising the session-expiry boundary) composes
against Story 9.3's ten-method
:class:`loud_fail_harness.mobile_driver.MobileDriver` Protocol surface
AS-IS; THIS module exposes only the substrate-data primitive.

Sources:
    * Verbatim epic AC at ``_bmad-output/planning-artifacts/epics-phase-1.5.md``
      lines 176-189 (Story 9.4 AC source).
    * PRD FR22 (line 836) — three MVP exploratory heuristics.
    * PRD FR-P1.5-2 (line 928) — Mobile QA via mobile MCP + mobile-
      specific exploratory heuristics.
    * ADR-007 (``architecture.md`` lines 604-659) — mobile MCP server
      selection (mobile-mcp v0.0.54) + the ten-method verb set the
      :class:`MobileDriver` Protocol surface in Story 9.3 declares.

Cross-references (AS-IS reuse targets):
    * :mod:`loud_fail_harness.qa_exploratory_heuristics` — Story 4.9's
      substrate-side decision/emission primitives
      (:func:`evaluate_heuristic_applicability` /
      :func:`surface_heuristic_skipped` / :func:`tag_heuristic_finding`)
      consumed by the wrapper-side composition; THIS module is the
      first mobile-side consumer of the
      :data:`HeuristicKind` Literal.
    * ``skills/bmad-automation/steps/qa-mobile-heuristics.md`` — the
      new LLM-runtime binding step file (Story 9.4 AC-3) documenting
      the per-kind mobile driving procedure; parallel in shape to
      Story 9.3's ``qa-driver-mobile.md``.
    * :mod:`loud_fail_harness.mobile_driver` — Story 9.3's ten-method
      :class:`MobileDriver` Protocol surface the wrapper composes
      against; NOT imported here (avoid circular-import risk; the
      Protocol method names are inlined into
      :data:`_MOBILE_DRIVER_METHOD_NAMES` and the byte-equality drift
      catcher at ``tests/test_mobile_heuristic_spec.py`` asserts
      equality via :func:`inspect.getmembers` at test time).

Heuristic-binding rationale:

    The verbatim epic AC at ``epics-phase-1.5.md`` line 186 offers two
    candidate mobile scenarios for ``auth-boundary``: "biometric-auth-
    boundary or session-expiry — exact trio decided in the story".
    THIS story chooses session-expiry over biometric-auth-boundary for
    three reasons recorded here for downstream auditors:

    1. **mobile-mcp v0.0.54 verb-set bounds.** Story 9.3 AC-2's
       ten-method :class:`MobileDriver` Protocol exposes ``launch_app``
       / ``terminate_app`` / ``tap_at_coordinates`` / ``swipe`` /
       ``type_text`` / ``press_button`` / ``screenshot`` /
       ``list_elements_on_screen`` / ``assert_element_present`` /
       ``get_screen_size``. None of these can trigger a biometric
       prompt — Touch ID / Face ID / Android Biometric prompts are
       OS-level UI surfaces that require simulator-specific commands
       (``xcrun simctl io booted matchBiometric`` on iOS Simulator;
       ``adb shell ime`` workarounds on Android emulators) that are
       not part of the mobile-mcp tool surface.
    2. **Coverage value.** Session-expiry is a higher-empirical-value
       heuristic (per the web-research at story-create time
       2026-05-11); session-token-expiry bugs are common in mobile
       apps and are observable via the ``screenshot`` +
       ``assert_element_present`` pair.
    3. **Reproducibility.** Session-expiry can be triggered
       deterministically by HOME-button-pressing + re-foregrounding
       after the configured session-TTL elapses. Biometric prompts
       cannot be triggered reproducibly via the Protocol surface
       (simulator quirks; device-specific behavior).

    The :data:`HeuristicKind` Literal is reused BYTE-FOR-BYTE — the
    same six mobile-applicable kind labels (``empty-state`` /
    ``error-state`` / ``auth-boundary`` MVP trio + ``large-input-boundary``
    / ``locale-i18n-edge`` / ``permission-boundary`` Story 19.2 additions)
    name the mobile scenarios via the closed six-entry
    :data:`MOBILE_HEURISTIC_SPECS` table; ``rate-limit-boundary`` is
    EXCLUDED on mobile per the ADR-010 matrix (silent exclusion — no
    ``heuristic-skipped`` emission). The marker-taxonomy
    ``heuristic-skipped.sub_classifications`` was PATCH-bumped 1.12 →
    1.13 (Story 19.2) for the four additions; the top-level marker-class
    closed-set is preserved. Single-responsibility convention: the
    ``heuristic-skipped`` marker's exploratory sub-classifications name
    the conceptual heuristic kinds; the per-project-type rendition is
    documented in the step file's mapping table + the
    :attr:`MobileHeuristicSpec.mobile_scenario_label` field.

Substrate-component closure: THIS module is a substrate-library NOT a
sixth substrate component. The substrate-component count remains FIVE
per ADR-003 Consequence 1 (architecture.md lines 311–315) + the Epic 8
ratified rule per ``epics-phase-1.5.md`` line 119 ("Phase 1.5 must not
introduce a sixth substrate component. New harness checks land as
substrate-libraries within existing components.").
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Story 9.4 — mobile-heuristic-spec consumer of Story 4.9's HeuristicKind
from loud_fail_harness.qa_exploratory_heuristics import HeuristicKind

# --------------------------------------------------------------------------- #
# Module-private invariants                                                   #
# --------------------------------------------------------------------------- #

#: The byte-stable frozenset of the ten Story 9.3 :class:`MobileDriver`
#: Protocol method names. Single source of truth for the
#: :class:`MobileHeuristicSpec` validator gates; a contract test at
#: ``tests/test_mobile_heuristic_spec.py`` asserts byte-equality with
#: :func:`inspect.getmembers(MobileDriver, predicate=callable)` minus
#: dunders (drift catcher — adding a method to the Protocol without
#: updating this frozenset, or vice versa, breaks the test).
_MOBILE_DRIVER_METHOD_NAMES: Final[frozenset[str]] = frozenset(
    {
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
    }
)


# --------------------------------------------------------------------------- #
# Pydantic models                                                             #
# --------------------------------------------------------------------------- #


class MobileHeuristicSpec(BaseModel):
    """The mobile-specific scenario re-binding for a single
    :data:`HeuristicKind` value.

    Field semantics:
        * ``heuristic_kind`` — the canonical :data:`HeuristicKind` label;
          the spec re-binds the mobile-specific scenario to one of the
          six mobile-applicable values (every kind except
          ``rate-limit-boundary``, ADR-010 matrix-excluded on mobile).
        * ``mobile_scenario_label`` — the mobile-specific scenario name
          (e.g., ``"empty-list state"`` / ``"network-error state"`` /
          ``"session-expiry boundary"``); appears in diagnostic prose
          surfaced by the wrapper at finding-construction time and in
          the step file's mapping table.
        * ``procedural_outline`` — short prose (one-to-two-sentence
          outline) describing the per-kind mobile driving procedure.
          The prose names ONLY :class:`MobileDriver` Protocol method
          identifiers from Story 9.3 — no MCP-tool-name references
          (LLM-runtime binding via the step file at AC-3). Plain text;
          not backtick-quoted. The prose is authoritative for call
          order and out-of-band steps (e.g., TTL waiting for the
          session-expiry boundary); see :attr:`driver_methods_used`
          for the validated membership declaration.
        * ``driver_methods_used`` — the distinct set of
          :class:`MobileDriver` Protocol method names this heuristic's
          procedure exercises (membership declaration — not an
          invocation sequence; the :attr:`procedural_outline` prose is
          authoritative for call order and repetition); entries are
          byte-restricted to the ten-method set from Story 9.3;
          enforced at construction time by
          :meth:`_driver_methods_used_in_protocol`.

    Frozen for hashability + determinism; ``extra="forbid"`` per Epic 1
    retro Action #2 + Story 1.10b structural enforcement. Field
    declaration order is load-bearing for byte-stable
    ``model_dump_json()`` output.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    heuristic_kind: HeuristicKind
    mobile_scenario_label: str = Field(min_length=1)
    procedural_outline: str = Field(min_length=1)
    driver_methods_used: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _driver_methods_used_in_protocol(self) -> "MobileHeuristicSpec":
        """Every entry in :attr:`driver_methods_used` is a member of
        :data:`_MOBILE_DRIVER_METHOD_NAMES` (drift catcher)."""
        unknown = tuple(
            method
            for method in self.driver_methods_used
            if method not in _MOBILE_DRIVER_METHOD_NAMES
        )
        if unknown:
            raise ValueError(
                "MobileHeuristicSpec.driver_methods_used contains entries not in "
                f"MobileDriver Protocol surface: {unknown!r}. Expected subset of "
                f"{sorted(_MOBILE_DRIVER_METHOD_NAMES)!r}."
            )
        return self


# --------------------------------------------------------------------------- #
# Closed six-spec table                                                       #
# --------------------------------------------------------------------------- #

#: The closed six-spec mobile-heuristic specification (Story 19.2 — six
#: of seven; ``rate-limit-boundary`` matrix-excluded on mobile per
#: ADR-010). Declaration order load-bearing — alphabetical by
#: ``heuristic_kind`` for byte-stable diffs. The table is BYTE-IDENTICAL
#: with the step file's
#: ``## Procedure — HeuristicKind ↔ mobile scenario mappings`` table at
#: ``skills/bmad-automation/steps/qa-mobile-heuristics.md``; a parity
#: test at ``tests/test_mobile_heuristic_spec.py`` asserts byte-equality
#: (drift catcher — maintainers updating one must update the other in
#: the same commit, OR the test fails and CI rejects the commit).
MOBILE_HEURISTIC_SPECS: Final[
    tuple[
        MobileHeuristicSpec,
        MobileHeuristicSpec,
        MobileHeuristicSpec,
        MobileHeuristicSpec,
        MobileHeuristicSpec,
        MobileHeuristicSpec,
    ]
] = (
    MobileHeuristicSpec(
        heuristic_kind="auth-boundary",
        mobile_scenario_label="session-expiry boundary",
        procedural_outline=(
            "Launch the app via launch_app to a route requiring an authenticated "
            "session; force session-expiry by pressing the HOME button via "
            "press_button then re-foregrounding after the configured session-TTL; "
            "capture the post-expiry screenshot via screenshot and verify the "
            "session-expiry UI's accessible label is present via "
            "assert_element_present."
        ),
        driver_methods_used=(
            "launch_app",
            "press_button",
            "screenshot",
            "assert_element_present",
        ),
    ),
    MobileHeuristicSpec(
        heuristic_kind="empty-state",
        mobile_scenario_label="empty-list state",
        procedural_outline=(
            "Launch the app via launch_app to a list-bearing screen; navigate to "
            "the empty-state condition (cleared filters / no records) via "
            "tap_at_coordinates; capture the a11y tree via list_elements_on_screen "
            "and verify the empty-state UI's accessible label is present via "
            "assert_element_present."
        ),
        driver_methods_used=(
            "launch_app",
            "tap_at_coordinates",
            "list_elements_on_screen",
            "assert_element_present",
        ),
    ),
    MobileHeuristicSpec(
        heuristic_kind="error-state",
        mobile_scenario_label="network-error state",
        procedural_outline=(
            "Launch the app via launch_app to a network-dependent screen; provoke "
            "the network-error path by interacting via tap_at_coordinates while "
            "the device is offline (practitioner toggles airplane mode out-of-band "
            "— see qa-mobile-heuristics.md); capture the post-failure screenshot "
            "via screenshot and verify the error-state UI's accessible label is "
            "present via assert_element_present."
        ),
        driver_methods_used=(
            "launch_app",
            "tap_at_coordinates",
            "screenshot",
            "assert_element_present",
        ),
    ),
    MobileHeuristicSpec(
        heuristic_kind="large-input-boundary",
        mobile_scenario_label="large-input boundary state",
        procedural_outline=(
            "Launch the app via launch_app to a screen bearing a free-text "
            "input; focus the field via tap_at_coordinates and enter a very "
            "large input string via type_text that exceeds the field's expected "
            "bound; capture the post-entry screenshot via screenshot and verify "
            "the large-input-boundary handling UI (length-cap or validation "
            "affordance) accessible label is present via assert_element_present."
        ),
        driver_methods_used=(
            "launch_app",
            "tap_at_coordinates",
            "type_text",
            "screenshot",
            "assert_element_present",
        ),
    ),
    MobileHeuristicSpec(
        heuristic_kind="locale-i18n-edge",
        mobile_scenario_label="locale/i18n edge state",
        procedural_outline=(
            "Launch the app via launch_app after the practitioner sets a "
            "non-default device locale out-of-band (see qa-mobile-heuristics.md); "
            "navigate to a locale-sensitive screen via tap_at_coordinates; "
            "capture the localized-layout screenshot via screenshot and verify "
            "the locale/i18n edge UI (translated string or RTL mirroring) "
            "accessible label is present via assert_element_present."
        ),
        driver_methods_used=(
            "launch_app",
            "tap_at_coordinates",
            "screenshot",
            "assert_element_present",
        ),
    ),
    MobileHeuristicSpec(
        heuristic_kind="permission-boundary",
        mobile_scenario_label="permission-denied boundary",
        procedural_outline=(
            "Launch the app via launch_app to a screen whose primary action "
            "requires a runtime OS permission the practitioner has denied "
            "out-of-band (see qa-mobile-heuristics.md); invoke the "
            "permission-gated action via tap_at_coordinates; capture the "
            "post-denial screenshot via screenshot and verify the "
            "permission-denied fallback UI's accessible label is present via "
            "assert_element_present."
        ),
        driver_methods_used=(
            "launch_app",
            "tap_at_coordinates",
            "screenshot",
            "assert_element_present",
        ),
    ),
)


# --------------------------------------------------------------------------- #
# Public lookup                                                               #
# --------------------------------------------------------------------------- #


def get_mobile_heuristic_spec(heuristic_kind: HeuristicKind) -> MobileHeuristicSpec:
    """Return the :class:`MobileHeuristicSpec` matching ``heuristic_kind``.

    Pure lookup over :data:`MOBILE_HEURISTIC_SPECS`. Mirrors
    :func:`loud_fail_harness.qa_behavioral_plan._render_heuristic_list`'s
    defensive-resolution pattern — the runtime guard cannot fire at
    static-type-check time per the :data:`HeuristicKind` Literal
    narrowing, but the :exc:`KeyError` raise on miss is a
    defense-in-depth witness.

    Args:
        heuristic_kind: One of the six mobile-applicable
            :data:`HeuristicKind` values (every kind except
            ``rate-limit-boundary``, which is matrix-excluded on mobile
            per ADR-010).

    Returns:
        The matching :class:`MobileHeuristicSpec`.

    Raises:
        :exc:`KeyError`: ``heuristic_kind`` is not in the closed
            six-entry table (notably ``rate-limit-boundary``, which has
            no mobile spec by the ADR-010 matrix).
    """
    for spec in MOBILE_HEURISTIC_SPECS:
        if spec.heuristic_kind == heuristic_kind:
            return spec
    raise KeyError(
        f"MOBILE_HEURISTIC_SPECS does not contain spec for heuristic_kind="
        f"{heuristic_kind!r}"
    )


__all__ = (
    "MOBILE_HEURISTIC_SPECS",
    "MobileHeuristicSpec",
    "get_mobile_heuristic_spec",
)
