"""Contract-coverage matrix for the mobile-heuristic specification
substrate library (Story 9.4 — Phase 1.5 mobile-parity exploratory
heuristics per FR22 + FR-P1.5-2 + ADR-007).

Mirrors the test-file shape established by ``test_qa_exploratory_heuristics.py``
(Story 4.9) and ``test_mobile_driver.py`` (Story 9.3) for the
substrate-library tests; extends with the mobile-spec-table closed-
three-entry contract, the ``_MOBILE_DRIVER_METHOD_NAMES`` ↔
:class:`MobileDriver` Protocol byte-equality drift catcher, and the
step-file ↔ spec-table parity drift catcher.

Test enumeration (Story 9.4 AC-5 + AC-7 — ≥ 14 logical tests):

MobileHeuristicSpec Pydantic model:
    1.  test_spec_is_frozen
    2.  test_spec_rejects_extra_fields
    3.  test_spec_rejects_unknown_heuristic_kind
    4.  test_spec_rejects_empty_mobile_scenario_label
    5.  test_spec_rejects_empty_procedural_outline
    6.  test_spec_rejects_empty_driver_methods_used
    7.  test_spec_rejects_driver_method_not_in_protocol

_MOBILE_DRIVER_METHOD_NAMES drift catcher:
    8.  test_method_names_frozenset_matches_mobile_driver_protocol

MOBILE_HEURISTIC_SPECS closed-table contract:
    9.  test_specs_table_has_exactly_six_entries
    10. test_specs_table_covers_mobile_applicable_kinds_only
    11. test_specs_table_alphabetical_by_heuristic_kind

get_mobile_heuristic_spec lookup:
    12. test_get_spec_returns_matching_entry
    13. test_get_spec_returns_distinct_scenario_labels
    14. test_get_spec_raises_key_error_for_unknown_kind

Step-file ↔ spec-table drift catcher:
    15. test_step_file_table_matches_specs_table

LF line endings:
    16. test_module_has_lf_line_endings_only

Marker taxonomy + envelope schema byte-stable witnesses (AC-7):
    17. test_heuristic_skipped_sub_classifications_unchanged_for_phase_1_5
    18. test_envelope_schema_verification_mode_enum_unchanged_for_phase_1_5

Public symbol surface:
    19. test_module_all_exports
"""

from __future__ import annotations

import inspect
import pathlib
import re
from typing import get_args

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness import mobile_heuristic_spec
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.mobile_driver import MobileDriver
from loud_fail_harness.mobile_heuristic_spec import (
    MOBILE_HEURISTIC_SPECS,
    MobileHeuristicSpec,
    get_mobile_heuristic_spec,
)
from loud_fail_harness.mobile_heuristic_spec import (
    _MOBILE_DRIVER_METHOD_NAMES,
)
from loud_fail_harness.qa_exploratory_heuristics import HeuristicKind

REPO_ROOT = find_repo_root()
MODULE_PATH = (
    REPO_ROOT
    / "tools"
    / "loud-fail-harness"
    / "src"
    / "loud_fail_harness"
    / "mobile_heuristic_spec.py"
)
STEP_FILE_PATH = (
    REPO_ROOT
    / "skills"
    / "bmad-automation"
    / "steps"
    / "qa-mobile-heuristics.md"
)
MARKER_TAXONOMY_PATH = REPO_ROOT / "schemas" / "marker-taxonomy.yaml"
ENVELOPE_SCHEMA_PATH = REPO_ROOT / "schemas" / "envelope.schema.yaml"

#: Story 19.2 — mobile drives SIX of the seven ``HeuristicKind`` values;
#: ``rate-limit-boundary`` is matrix-excluded on mobile per ADR-010. This is the
#: single test-side mirror of that exclusion (used to invert the Story 9.4
#: coverage invariant from "every kind" to "every kind except rate-limit-boundary").
_RATE_LIMIT_BOUNDARY = "rate-limit-boundary"
_MOBILE_APPLICABLE_KINDS: tuple[str, ...] = tuple(
    k for k in get_args(HeuristicKind) if k != _RATE_LIMIT_BOUNDARY
)


def _make_spec(**overrides: object) -> dict[str, object]:
    """Default valid spec kwargs; override per-test as needed."""
    base: dict[str, object] = {
        "heuristic_kind": "empty-state",
        "mobile_scenario_label": "empty-list state",
        "procedural_outline": "outline prose",
        "driver_methods_used": ("launch_app",),
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# 1. MobileHeuristicSpec Pydantic model                                       #
# --------------------------------------------------------------------------- #


def test_spec_is_frozen() -> None:
    spec = MobileHeuristicSpec(**_make_spec())  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        spec.mobile_scenario_label = "other"  # type: ignore[misc]


def test_spec_rejects_extra_fields() -> None:
    kwargs = _make_spec()
    kwargs["extra"] = "x"
    with pytest.raises(ValidationError):
        MobileHeuristicSpec(**kwargs)  # type: ignore[arg-type]


def test_spec_rejects_unknown_heuristic_kind() -> None:
    kwargs = _make_spec(heuristic_kind="speculative-mutation")
    with pytest.raises(ValidationError):
        MobileHeuristicSpec(**kwargs)  # type: ignore[arg-type]


def test_spec_rejects_empty_mobile_scenario_label() -> None:
    kwargs = _make_spec(mobile_scenario_label="")
    with pytest.raises(ValidationError):
        MobileHeuristicSpec(**kwargs)  # type: ignore[arg-type]


def test_spec_rejects_empty_procedural_outline() -> None:
    kwargs = _make_spec(procedural_outline="")
    with pytest.raises(ValidationError):
        MobileHeuristicSpec(**kwargs)  # type: ignore[arg-type]


def test_spec_rejects_empty_driver_methods_used() -> None:
    kwargs = _make_spec(driver_methods_used=())
    with pytest.raises(ValidationError):
        MobileHeuristicSpec(**kwargs)  # type: ignore[arg-type]


def test_spec_rejects_driver_method_not_in_protocol() -> None:
    kwargs = _make_spec(driver_methods_used=("not_a_mobile_driver_method",))
    with pytest.raises(ValidationError):
        MobileHeuristicSpec(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 2. _MOBILE_DRIVER_METHOD_NAMES drift catcher                                #
# --------------------------------------------------------------------------- #


def test_method_names_frozenset_matches_mobile_driver_protocol() -> None:
    """Byte-equality contract: drift between the Protocol surface and
    the frozenset breaks loudly. Mirrors Story 9.3 AC-2's
    ``test_mobile_driver_protocol_has_ten_methods_per_ac2`` pattern.
    """
    protocol_methods = {
        name
        for name, _ in inspect.getmembers(
            MobileDriver, predicate=lambda m: callable(m)
        )
        if not name.startswith("_")
    }
    assert protocol_methods == _MOBILE_DRIVER_METHOD_NAMES, (
        f"MobileDriver Protocol ↔ _MOBILE_DRIVER_METHOD_NAMES drift: "
        f"protocol={sorted(protocol_methods)} "
        f"frozenset={sorted(_MOBILE_DRIVER_METHOD_NAMES)}"
    )


# --------------------------------------------------------------------------- #
# 3. MOBILE_HEURISTIC_SPECS closed-table contract                             #
# --------------------------------------------------------------------------- #


def test_specs_table_has_exactly_six_entries() -> None:
    assert len(MOBILE_HEURISTIC_SPECS) == 6


def test_specs_table_covers_mobile_applicable_kinds_only() -> None:
    """Story 19.2 inverts the Story 9.4 coverage invariant: the mobile spec set
    covers every ``HeuristicKind`` EXCEPT ``rate-limit-boundary`` (matrix-excluded
    on mobile per ADR-010), each exactly once (NO duplication, NO missing kind,
    and NOT every kind)."""
    spec_kinds = {spec.heuristic_kind for spec in MOBILE_HEURISTIC_SPECS}
    assert spec_kinds == set(_MOBILE_APPLICABLE_KINDS)
    assert spec_kinds == set(get_args(HeuristicKind)) - {_RATE_LIMIT_BOUNDARY}
    assert _RATE_LIMIT_BOUNDARY not in spec_kinds


def test_specs_table_alphabetical_by_heuristic_kind() -> None:
    """Declaration-order invariant for byte-stable diffs per AC-1(e)."""
    kinds_in_order = [spec.heuristic_kind for spec in MOBILE_HEURISTIC_SPECS]
    assert kinds_in_order == sorted(kinds_in_order)


# --------------------------------------------------------------------------- #
# 4. get_mobile_heuristic_spec lookup                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kind", _MOBILE_APPLICABLE_KINDS)
def test_get_spec_returns_matching_entry(kind: HeuristicKind) -> None:
    # Resolves deferred-work.md (the 9.4 review item): parametrize over the
    # live mobile-applicable subset (`get_args(HeuristicKind)` minus
    # `rate-limit-boundary`) instead of a hardcoded kind list, so a future
    # kind-set change is covered automatically.
    spec = get_mobile_heuristic_spec(kind)
    assert spec.heuristic_kind == kind


def test_get_spec_returns_distinct_scenario_labels() -> None:
    labels = {
        get_mobile_heuristic_spec(kind).mobile_scenario_label
        for kind in _MOBILE_APPLICABLE_KINDS
    }
    assert len(labels) == 6


def test_get_spec_raises_key_error_for_unknown_kind() -> None:
    """Defense-in-depth witness against the Literal-narrowing escape."""
    with pytest.raises(KeyError):
        get_mobile_heuristic_spec("speculative-mutation")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 5. Step-file ↔ spec-table drift catcher                                     #
# --------------------------------------------------------------------------- #


_TABLE_ROW_RE = re.compile(
    r"^\|\s*`(?P<kind>[^`]+)`\s*\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<methods>[^|]+?)\s*\|\s*$"
)


def _parse_step_file_mapping_table(text: str) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Parse the step file's ``## Procedure — HeuristicKind ↔ mobile
    scenario mappings`` table. Returns ``{kind: (label, methods)}``.
    """
    rows: dict[str, tuple[str, tuple[str, ...]]] = {}
    in_table = False
    for line in text.splitlines():
        if line.startswith("## Procedure — HeuristicKind"):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        if not in_table:
            continue
        match = _TABLE_ROW_RE.match(line)
        if match is None:
            continue
        kind = match["kind"].strip()
        label = match["label"].strip()
        methods_cell = match["methods"].strip()
        methods = tuple(
            entry.strip().strip("`")
            for entry in methods_cell.split(",")
        )
        rows[kind] = (label, methods)
    return rows


def test_step_file_table_matches_specs_table() -> None:
    """Drift catcher: the step file's mapping table cells are
    byte-identical with the ``MOBILE_HEURISTIC_SPECS`` table cells
    (mobile_scenario_label + driver_methods_used) per AC-5."""
    step_text = STEP_FILE_PATH.read_text(encoding="utf-8")
    parsed = _parse_step_file_mapping_table(step_text)
    assert set(parsed.keys()) == set(_MOBILE_APPLICABLE_KINDS)
    for spec in MOBILE_HEURISTIC_SPECS:
        label, methods = parsed[spec.heuristic_kind]
        assert label == spec.mobile_scenario_label, (
            f"step file ↔ spec drift on {spec.heuristic_kind!r}: "
            f"step={label!r} spec={spec.mobile_scenario_label!r}"
        )
        assert methods == spec.driver_methods_used, (
            f"step file ↔ spec drift on {spec.heuristic_kind!r}: "
            f"step={methods!r} spec={spec.driver_methods_used!r}"
        )


# --------------------------------------------------------------------------- #
# 6. LF line endings                                                          #
# --------------------------------------------------------------------------- #


def test_module_has_lf_line_endings_only() -> None:
    raw = pathlib.Path(MODULE_PATH).read_bytes()
    assert b"\r" not in raw


# --------------------------------------------------------------------------- #
# 7. Marker taxonomy + envelope schema byte-stable witnesses (AC-7)           #
# --------------------------------------------------------------------------- #


def test_heuristic_skipped_sub_classifications_unchanged_for_phase_1_5() -> None:
    """No marker-taxonomy bump in Phase 1.5: ``heuristic-skipped`` still
    leads with the Story 4.9 exploratory-heuristic trio (``empty-state`` /
    ``error-state`` / ``auth-boundary``) in their original order. The
    post-Phase-1.5 ``flow-branch`` entry (Epic 13 / Story 13.6, FR22c
    within-AC flow-branch coverage — a Phase 1 patch, not Phase 1.5) is
    deliberately outside this Phase-1.5 no-bump witness; its presence is
    pinned by ``test_marker_taxonomy.py``'s
    ``test_heuristic_skipped_declares_flow_branch_sub_classification``.
    """
    taxonomy = yaml.safe_load(MARKER_TAXONOMY_PATH.read_text(encoding="utf-8"))
    heuristic_entry = next(
        entry
        for entry in taxonomy["markers"]
        if entry["marker_class"] == "heuristic-skipped"
    )
    assert heuristic_entry["sub_classifications"][:3] == [
        "empty-state",
        "error-state",
        "auth-boundary",
    ]


def test_envelope_schema_verification_mode_enum_unchanged_for_phase_1_5() -> None:
    """No envelope-schema bump in Phase 1.5: ``verification_mode``
    enum continues to carry only ``exploratory-heuristic``."""
    schema = yaml.safe_load(ENVELOPE_SCHEMA_PATH.read_text(encoding="utf-8"))
    enum_values = schema["$defs"]["finding"]["properties"]["verification_mode"][
        "enum"
    ]
    assert enum_values == ["exploratory-heuristic"]


# --------------------------------------------------------------------------- #
# 8. Public symbol surface                                                    #
# --------------------------------------------------------------------------- #


def test_module_all_exports() -> None:
    assert set(mobile_heuristic_spec.__all__) == {
        "MOBILE_HEURISTIC_SPECS",
        "MobileHeuristicSpec",
        "get_mobile_heuristic_spec",
    }
