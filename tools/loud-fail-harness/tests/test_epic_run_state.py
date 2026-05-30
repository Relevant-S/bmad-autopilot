"""Contract-coverage matrix for the epic-/sprint-run-state schemas +
per-worktree run-state addressing (story 14.4).

This docstring IS the contract-coverage checklist. Reviewers verify every row
maps to at least one passing test (review-enforced, parallel to
``test_run_state.py``).

Schema-shape (AC-1):
    [x] schemas/epic-run-state.yaml meta-validates as JSON-Schema-2020-12   → test_epic_run_state_schema_meta_validates
    [x] schemas/sprint-run-state.yaml meta-validates as JSON-Schema-2020-12 → test_sprint_run_state_schema_meta_validates

Fixture validation (AC-5):
    [x] valid epic-run-state fixture accepted                               → test_valid_epic_run_state_fixture_accepted
    [x] valid sprint-run-state fixture accepted                             → test_valid_sprint_run_state_fixture_accepted
    [x] valid per-worktree run-state fixture accepted (UNCHANGED schema)    → test_valid_worktree_run_state_fixture_accepted
    [x] invalid epic-run-state fixture rejected (out-of-enum current_state) → test_invalid_epic_run_state_fixture_rejected
    [x] invalid epic-run-state fixture rejected (additionalProperties)      → test_invalid_epic_run_state_additional_property_rejected
    [x] invalid sprint-run-state fixture rejected (additionalProperties)    → test_invalid_sprint_run_state_fixture_rejected
    [x] invalid per-worktree run-state fixture rejected (missing field)     → test_invalid_worktree_run_state_fixture_rejected

Model ↔ schema agreement (AC-4):
    [x] EpicRunState model_dump_json round-trips through JSON Schema        → test_epic_run_state_model_round_trips_through_schema
    [x] SprintRunState model_dump_json round-trips through JSON Schema      → test_sprint_run_state_model_round_trips_through_schema

Frozen-tuple immutability (AC-3; Pattern 4 + Epic 1 retro Action #2):
    [x] EpicRunState is frozen (reassignment raises)                       → test_epic_run_state_is_frozen
    [x] SprintRunState is frozen (reassignment raises)                     → test_sprint_run_state_is_frozen
    [x] story_ids / active_markers are tuple-typed (no .append)            → test_epic_run_state_sequence_fields_are_tuples
    [x] epic_ids / unassigned_story_ids / active_markers tuple-typed       → test_sprint_run_state_sequence_fields_are_tuples

Closed-Literal lifecycle enums (AC-3):
    [x] EpicCurrentState members match the schema enum exactly             → test_epic_current_state_is_closed_literal
    [x] SprintCurrentState members match the schema enum exactly           → test_sprint_current_state_is_closed_literal
    [x] PerStoryStatus members match the schema enum exactly               → test_per_story_status_is_closed_literal

Per-worktree addressing (AC-2):
    [x] path derivation from explicit repo_root                            → test_worktree_run_state_path_derivation
    [x] path derivation from explicit worktrees_root                       → test_worktree_run_state_path_explicit_worktrees_root
    [x] empty story_id raises ValueError                                   → test_worktree_run_state_path_empty_story_id_raises
    [x] repo_root=None resolves lazily via _default_repo_root              → test_worktree_run_state_path_repo_root_none_resolves_lazily

Module discipline (AC-3; Epic 1 retro Action #1):
    [x] find_repo_root NOT called at module import time                    → test_find_repo_root_not_called_at_import
    [x] __all__ exports the AC-3 public surface in alphabetical order      → test_module_all_exports
"""

from __future__ import annotations

import importlib
import json
import pathlib
from typing import Any, get_args
from unittest import mock

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError
from pydantic import ValidationError as PydanticValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from loud_fail_harness import epic_run_state as epic_run_state_module
from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.epic_run_state import (
    EpicCurrentState,
    EpicRunState,
    PerEpicCostPartition,
    PerEpicRetryBudget,
    PerSprintRetryBudget,
    PerStoryStatus,
    SprintCurrentState,
    SprintRunState,
    worktree_run_state_path,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def repo_root() -> pathlib.Path:
    """``find_repo_root()`` at fixture-setup time, NOT module import time
    (Epic 1 retro Action #1)."""
    return find_repo_root()


def _load_schema(repo_root: pathlib.Path, name: str) -> dict[str, Any]:
    return yaml.safe_load(
        (repo_root / "schemas" / name).read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def epic_schema(repo_root: pathlib.Path) -> dict[str, Any]:
    return _load_schema(repo_root, "epic-run-state.yaml")


@pytest.fixture(scope="module")
def sprint_schema(repo_root: pathlib.Path) -> dict[str, Any]:
    return _load_schema(repo_root, "sprint-run-state.yaml")


@pytest.fixture(scope="module")
def run_state_validator(repo_root: pathlib.Path) -> Draft202012Validator:
    """Validator over the UNCHANGED ``schemas/run-state.yaml`` with the cell-1
    ``$ref`` registry populated (the per-worktree run-state reuses this schema
    verbatim; AC-2 + AC-4)."""
    registry = Registry().with_resources(
        [
            (
                "envelope.schema.yaml",
                Resource(
                    contents=_load_schema(repo_root, "envelope.schema.yaml"),
                    specification=DRAFT202012,
                ),
            ),
            (
                "tea-handoff-contract.yaml",
                Resource(
                    contents=_load_schema(repo_root, "tea-handoff-contract.yaml"),
                    specification=DRAFT202012,
                ),
            ),
        ]
    )
    return Draft202012Validator(
        _load_schema(repo_root, "run-state.yaml"), registry=registry
    )


def _load_fixture(*parts: str) -> dict[str, Any]:
    return yaml.safe_load(FIXTURES.joinpath(*parts).read_text(encoding="utf-8"))


def _epic_run_state() -> EpicRunState:
    return EpicRunState(
        schema_version="1.0",
        epic_id="epic-15",
        run_id="run-epic-15-001",
        current_state="epic-in-progress",
        story_ids=("15-1-foo", "15-2-bar"),
        per_story_status={"15-1-foo": "in-progress", "15-2-bar": "ready-for-dev"},
        per_epic_retry_budget=PerEpicRetryBudget(
            multiplier=2, story_count=2, effective_budget=4, consumed=1
        ),
        per_epic_cost_partition=PerEpicCostPartition(
            per_story_cost={"15-1-foo": 1.25, "15-2-bar": 0.0},
            epic_cost_total=1.25,
        ),
        active_markers=(),
    )


def _sprint_run_state() -> SprintRunState:
    return SprintRunState(
        schema_version="1.0",
        sprint_id="sprint-phase-2",
        run_id="run-sprint-phase-2-001",
        current_state="sprint-in-progress",
        epic_ids=("epic-15", "epic-16"),
        per_epic_status={"epic-15": "epic-in-progress", "epic-16": "epic-complete"},
        unassigned_story_ids=("14-6-ref",),
        per_sprint_retry_budget=PerSprintRetryBudget(
            multiplier=2, epic_count=2, effective_budget=4, consumed=0
        ),
        active_markers=(),
    )


# ---------------------------------------------------------------------------
# Schema-shape tests (AC-1)
# ---------------------------------------------------------------------------


def test_epic_run_state_schema_meta_validates(epic_schema: dict[str, Any]) -> None:
    Draft202012Validator.check_schema(epic_schema)
    assert epic_schema.get("$schema", "").endswith("/draft/2020-12/schema")
    assert epic_schema.get("$id", "").endswith("schemas/epic-run-state.yaml")
    assert epic_schema.get("schema_version") == "1.0"
    assert epic_schema.get("type") == "object"
    assert epic_schema.get("additionalProperties") is False


def test_sprint_run_state_schema_meta_validates(
    sprint_schema: dict[str, Any],
) -> None:
    Draft202012Validator.check_schema(sprint_schema)
    assert sprint_schema.get("$schema", "").endswith("/draft/2020-12/schema")
    assert sprint_schema.get("$id", "").endswith("schemas/sprint-run-state.yaml")
    assert sprint_schema.get("schema_version") == "1.0"
    assert sprint_schema.get("type") == "object"
    assert sprint_schema.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# Fixture-validation tests (AC-5)
# ---------------------------------------------------------------------------


def test_valid_epic_run_state_fixture_accepted(epic_schema: dict[str, Any]) -> None:
    payload = _load_fixture("epic-run-state", "valid-epic-run-state.yaml")
    assert list(Draft202012Validator(epic_schema).iter_errors(payload)) == []


def test_valid_sprint_run_state_fixture_accepted(
    sprint_schema: dict[str, Any],
) -> None:
    payload = _load_fixture("sprint-run-state", "valid-sprint-run-state.yaml")
    assert list(Draft202012Validator(sprint_schema).iter_errors(payload)) == []


def test_valid_worktree_run_state_fixture_accepted(
    run_state_validator: Draft202012Validator,
) -> None:
    payload = _load_fixture(
        "worktree-run-state", "14-4-epic-scope-run-state-schema", "run-state.yaml"
    )
    assert list(run_state_validator.iter_errors(payload)) == []


def test_invalid_epic_run_state_fixture_rejected(
    epic_schema: dict[str, Any],
) -> None:
    payload = _load_fixture("epic-run-state", "invalid-current-state.yaml")
    with pytest.raises(ValidationError):
        Draft202012Validator(epic_schema).validate(payload)


def test_invalid_epic_run_state_additional_property_rejected(
    epic_schema: dict[str, Any],
) -> None:
    payload = _load_fixture("epic-run-state", "invalid-additional-property.yaml")
    with pytest.raises(ValidationError):
        Draft202012Validator(epic_schema).validate(payload)


def test_invalid_sprint_run_state_fixture_rejected(
    sprint_schema: dict[str, Any],
) -> None:
    payload = _load_fixture("sprint-run-state", "invalid-additional-property.yaml")
    with pytest.raises(ValidationError):
        Draft202012Validator(sprint_schema).validate(payload)


def test_invalid_worktree_run_state_fixture_rejected(
    run_state_validator: Draft202012Validator,
) -> None:
    payload = _load_fixture("worktree-run-state", "invalid-missing-branch-name.yaml")
    with pytest.raises(ValidationError):
        run_state_validator.validate(payload)


# ---------------------------------------------------------------------------
# Model ↔ schema agreement (AC-4)
# ---------------------------------------------------------------------------


def test_epic_run_state_model_round_trips_through_schema(
    epic_schema: dict[str, Any],
) -> None:
    payload = json.loads(_epic_run_state().model_dump_json())
    assert list(Draft202012Validator(epic_schema).iter_errors(payload)) == []


def test_sprint_run_state_model_round_trips_through_schema(
    sprint_schema: dict[str, Any],
) -> None:
    payload = json.loads(_sprint_run_state().model_dump_json())
    assert list(Draft202012Validator(sprint_schema).iter_errors(payload)) == []


# ---------------------------------------------------------------------------
# Frozen-tuple immutability (AC-3)
# ---------------------------------------------------------------------------


def test_epic_run_state_is_frozen() -> None:
    state = _epic_run_state()
    with pytest.raises(PydanticValidationError):
        state.current_state = "epic-complete"  # type: ignore[misc]


def test_sprint_run_state_is_frozen() -> None:
    state = _sprint_run_state()
    with pytest.raises(PydanticValidationError):
        state.current_state = "sprint-complete"  # type: ignore[misc]


def test_epic_run_state_sequence_fields_are_tuples() -> None:
    state = _epic_run_state()
    assert isinstance(state.story_ids, tuple)
    assert isinstance(state.active_markers, tuple)
    with pytest.raises(AttributeError):
        state.story_ids.append("15-3-baz")  # type: ignore[attr-defined]


def test_sprint_run_state_sequence_fields_are_tuples() -> None:
    state = _sprint_run_state()
    assert isinstance(state.epic_ids, tuple)
    assert isinstance(state.unassigned_story_ids, tuple)
    assert isinstance(state.active_markers, tuple)
    with pytest.raises(AttributeError):
        state.epic_ids.append("epic-17")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Closed-Literal lifecycle enums (AC-3)
# ---------------------------------------------------------------------------


def test_epic_current_state_is_closed_literal(epic_schema: dict[str, Any]) -> None:
    members = set(get_args(EpicCurrentState))
    assert members == {
        "epic-in-progress",
        "epic-paused-on-escalation",
        "epic-paused-on-budget",
        "epic-complete",
    }
    assert members == set(epic_schema["properties"]["current_state"]["enum"])


def test_sprint_current_state_is_closed_literal(
    sprint_schema: dict[str, Any],
) -> None:
    members = set(get_args(SprintCurrentState))
    assert members == {
        "sprint-in-progress",
        "sprint-paused-on-escalation",
        "sprint-paused-on-budget",
        "sprint-complete",
    }
    assert members == set(sprint_schema["properties"]["current_state"]["enum"])


def test_per_story_status_is_closed_literal(epic_schema: dict[str, Any]) -> None:
    members = set(get_args(PerStoryStatus))
    assert members == {
        "ready-for-dev",
        "in-progress",
        "review",
        "qa",
        "done",
        "escalated",
        "merge-ready",
    }
    assert members == set(
        epic_schema["properties"]["per_story_status"]["additionalProperties"]["enum"]
    )


# ---------------------------------------------------------------------------
# Per-worktree addressing (AC-2)
# ---------------------------------------------------------------------------


def test_worktree_run_state_path_derivation(tmp_path: pathlib.Path) -> None:
    assert worktree_run_state_path("14-4-foo", repo_root=tmp_path) == (
        tmp_path / "_bmad" / "automation" / "worktrees" / "14-4-foo" / "run-state.yaml"
    )


def test_worktree_run_state_path_explicit_worktrees_root(
    tmp_path: pathlib.Path,
) -> None:
    worktrees_root = tmp_path / "custom-worktrees"
    assert worktree_run_state_path("14-4-foo", worktrees_root=worktrees_root) == (
        worktrees_root / "14-4-foo" / "run-state.yaml"
    )


def test_worktree_run_state_path_empty_story_id_raises(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        worktree_run_state_path("", repo_root=tmp_path)


def test_worktree_run_state_path_repo_root_none_resolves_lazily(
    tmp_path: pathlib.Path,
) -> None:
    with mock.patch.object(
        epic_run_state_module, "_default_repo_root", return_value=tmp_path
    ):
        result = worktree_run_state_path("14-4-foo")
    assert result == (
        tmp_path / "_bmad" / "automation" / "worktrees" / "14-4-foo" / "run-state.yaml"
    )


# ---------------------------------------------------------------------------
# Module discipline (AC-3)
# ---------------------------------------------------------------------------


def test_find_repo_root_not_called_at_import() -> None:
    """Re-import the module with ``find_repo_root`` patched to raise; if the
    module called it at import time, the import would fail."""
    with mock.patch(
        "loud_fail_harness._shared.find_repo_root",
        side_effect=RuntimeError("must not be called at import"),
    ):
        importlib.reload(epic_run_state_module)
    importlib.reload(epic_run_state_module)


def test_module_all_exports() -> None:
    expected = [
        "EpicCurrentState",
        "EpicRunState",
        "PerEpicCostPartition",
        "PerEpicRetryBudget",
        "PerSprintRetryBudget",
        "PerStoryStatus",
        "SprintCurrentState",
        "SprintRunState",
        "worktree_run_state_path",
    ]
    assert epic_run_state_module.__all__ == expected
    assert epic_run_state_module.__all__ == sorted(epic_run_state_module.__all__)
