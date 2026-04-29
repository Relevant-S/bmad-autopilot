"""Contract-coverage matrix for the specialist-dispatch substrate library
(story 2.6).

This docstring IS the contract-coverage checklist required by AC-9.
Reviewers verify every row maps to at least one passing test in this
module. The matrix is review-enforced, NOT CI-enforced (parallel to
1.2 / 2.2 / 2.3 / 2.4 / 2.5 AC discipline).

AC-1 module-shape (5):
    [x] intra-package imports match documented allowlist
        → test_module_intra_package_imports_are_substrate_only
    [x] forbidden surfaces absent
        → test_module_does_not_import_forbidden_surfaces[*]
    [x] no module top-level find_repo_root() call
        → test_no_module_top_level_find_repo_root_call
    [x] __all__ enumerates documented exports
        → test_all_enumerates_documented_exports[*]
    [x] no specialist-import strings
        → test_no_specialist_import_strings[*]

AC-2 marker-class registry (≥7):
    [x] default-path loads live taxonomy
        → test_load_marker_class_registry_default_path_loads_live_taxonomy
    [x] explicit-path overrides default
        → test_load_marker_class_registry_explicit_path_overrides_default
    [x] validate_marker_emission known-class returns None
        → test_validate_marker_emission_known_class_returns_none
    [x] validate_marker_emission unknown-class raises
        → test_validate_marker_emission_unknown_class_raises
    [x] UnknownMarkerClass.marker_class is None
        → test_unknown_marker_class_carries_null_marker_class
    [x] registry tracks taxonomy mutation
        → test_registry_reflects_taxonomy_mutation
    [x] no inline taxonomy literal
        → test_no_inline_taxonomy_literal
    [x] MarkerClassRegistry frozen
        → test_marker_class_registry_is_frozen

AC-3 dispatch payload (≥6):
    [x] build_dispatch_payload happy path
        → test_build_dispatch_payload_happy_path_constructs_valid_model
    [x] reads agent file as data
        → test_build_dispatch_payload_reads_agent_file_as_data
    [x] propagates FileNotFoundError
        → test_build_dispatch_payload_propagates_file_not_found_error
    [x] uses caller-supplied renderer
        → test_build_dispatch_payload_uses_caller_supplied_renderer
    [x] dispatch_timestamp_factory injection
        → test_build_dispatch_payload_dispatch_timestamp_factory_injection
    [x] default_prompt_body_renderer canonical shape
        → test_default_prompt_body_renderer_returns_canonical_shape
    [x] payload frozen
        → test_specialist_dispatch_payload_is_frozen
    [x] acceptance_criteria is tuple (Epic 1 retro Action #2)
        → test_specialist_dispatch_payload_acceptance_criteria_is_tuple
    [x] naive dispatch_timestamp raises AssertionError (P1 review patch)
        → test_build_dispatch_payload_rejects_naive_dispatch_timestamp
    [x] prompt_id unique per call (D1 review fix)
        → test_build_dispatch_payload_prompt_id_is_unique_per_call

AC-4 log persistence (≥6):
    [x] LOG_PATH_TEMPLATE value verbatim
        → test_log_path_template_value
    [x] writes JSON to canonical path
        → test_persist_dispatch_log_writes_json_to_canonical_path
    [x] creates missing parent dirs
        → test_persist_dispatch_log_creates_missing_parent_dirs
    [x] log shape carries NFR-O3 fields
        → test_persist_dispatch_log_log_shape_carries_nfr_o3_fields[*]
    [x] naive datetime assertion fires
        → test_persist_dispatch_log_naive_datetime_assertion_fires
    [x] propagates OSError unchanged
        → test_persist_dispatch_log_propagates_oserror_unchanged
    [x] atomic write — no partial file on rename failure
        → test_persist_dispatch_log_atomic_write_no_partial_file

AC-5 envelope validation (≥5):
    [x] happy path returns valid=True
        → test_validate_return_envelope_happy_path_returns_valid_true
    [x] invalid returns valid=False with errors
        → test_validate_return_envelope_invalid_returns_valid_false_with_errors[*]
    [x] strict variant raises EnvelopeValidationFailed
        → test_validate_return_envelope_strict_raises_envelope_validation_failed
    [x] composes envelope_validator exclusively
        → test_validate_return_envelope_composes_envelope_validator_exclusively
    [x] EnvelopeValidationFailed.marker_class is None
        → test_envelope_validation_failed_carries_null_marker_class

AC-6 timeout exception (≥5):
    [x] marker_class Literal["specialist-timeout"]
        → test_specialist_timeout_exceeded_carries_marker_class_literal
    [x] sub_cause Literal["timeout-exceeded"]
        → test_specialist_timeout_exceeded_carries_sub_cause_literal
    [x] marker_class is in live registry
        → test_specialist_timeout_exceeded_marker_class_in_registry
    [x] sub_cause is in taxonomy entry's sub_classifications
        → test_specialist_timeout_exceeded_sub_cause_in_taxonomy_sub_classifications
    [x] __str__ form carries Pattern 5 diagnostic
        → test_specialist_timeout_exceeded_str_form_carries_pattern_5_diagnostic

AC-7 event emission (≥8):
    [x] make_specialist_dispatched_event canonical shape
        → test_make_specialist_dispatched_event_canonical_shape
    [x] dispatched event validates against schema
        → test_make_specialist_dispatched_event_validates_against_schema
    [x] dispatched event with dispatch_seq includes field
        → test_make_specialist_dispatched_event_with_dispatch_seq_includes_field
    [x] make_specialist_returned_event canonical shape
        → test_make_specialist_returned_event_canonical_shape
    [x] returned event validates against schema
        → test_make_specialist_returned_event_validates_against_schema
    [x] returned event with status="decision-needed" validates (AC-8 regression)
        → test_make_specialist_returned_event_with_decision_needed_status_validates
    [x] returned event with envelope_artifact_path includes field
        → test_make_specialist_returned_event_with_envelope_artifact_path_includes_field
    [x] default_event_id_factory returns unique ids
        → test_default_event_id_factory_returns_unique_ids
    [x] EventConstructionFailed.marker_class is None
        → test_event_construction_failed_carries_null_marker_class
    [x] invalid payload raises EventConstructionFailed
        → test_make_specialist_dispatched_event_invalid_payload_raises_event_construction_failed
    [x] event_id_factory is caller-injected
        → test_event_id_factory_is_caller_injected
    [x] dispatched and returned events share prompt_id (D1 review fix)
        → test_dispatched_and_returned_events_share_prompt_id

AC-8 schema-bump (≥3):
    [x] orchestrator-event schema_version is 1.2
        → test_orchestrator_event_schema_version_is_1_2
    [x] specialist-returned status enum includes decision-needed
        → test_specialist_returned_status_enum_includes_decision_needed
    [x] specialist-returned status enum order matches last_envelope_status
        → test_specialist_returned_status_enum_order_matches_last_envelope_status

AC-10 callback factory (≥4):
    [x] returned callable matches Protocol
        → test_make_task_tool_dispatch_callback_returns_callable_matching_protocol
    [x] returned callable matches DispatchCallback signature
        → test_make_task_tool_dispatch_callback_returned_callable_matches_dispatch_callback_signature
    [x] default timeout 900s
        → test_make_task_tool_dispatch_callback_default_timeout_is_900_seconds
    [x] caller-overridden timeout accepted
        → test_make_task_tool_dispatch_callback_accepts_caller_overridden_timeout
"""

from __future__ import annotations

import ast
import inspect
import json
import pathlib
import re
from collections.abc import Callable
from datetime import datetime, timezone
from unittest import mock

import pytest
import yaml
from pydantic import ValidationError

from loud_fail_harness import specialist_dispatch
from loud_fail_harness._shared import find_repo_root, load_schema
from loud_fail_harness.orchestrator_run_entry import (
    AcceptanceCriterion,
    DispatchCallbackResult,
    StoryDocResolution,
)
from loud_fail_harness.specialist_dispatch import (
    LOG_PATH_TEMPLATE,
    EnvelopeValidationFailed,
    EventConstructionFailed,
    MarkerClassRegistry,
    SpecialistDispatchPayload,
    SpecialistTimeoutExceeded,
    TaskToolDispatchCallback,
    UnknownMarkerClass,
    build_dispatch_payload,
    default_event_id_factory,
    default_prompt_body_renderer,
    load_marker_class_registry,
    make_specialist_dispatched_event,
    make_specialist_returned_event,
    make_task_tool_dispatch_callback,
    persist_dispatch_log,
    validate_marker_emission,
    validate_return_envelope,
    validate_return_envelope_strict,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def repo_root() -> pathlib.Path:
    """Resolve repo root at fixture-setup time (Epic 1 retro Action #1)."""
    return find_repo_root()


@pytest.fixture
def live_taxonomy_path(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "schemas" / "marker-taxonomy.yaml"


@pytest.fixture
def live_event_schema_path(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "schemas" / "orchestrator-event.yaml"


@pytest.fixture
def live_envelope_schema_path(repo_root: pathlib.Path) -> pathlib.Path:
    return repo_root / "schemas" / "envelope.schema.yaml"


@pytest.fixture
def fixed_timestamp() -> datetime:
    return datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def acceptance_criteria() -> tuple[AcceptanceCriterion, ...]:
    return (
        AcceptanceCriterion(ac_id="AC-1", text="First acceptance criterion."),
        AcceptanceCriterion(ac_id="AC-2", text="Second acceptance criterion."),
    )


@pytest.fixture
def story_doc_resolution(
    tmp_path: pathlib.Path, acceptance_criteria: tuple[AcceptanceCriterion, ...]
) -> StoryDocResolution:
    story_path = tmp_path / "2-6-test-story.md"
    story_path.write_text("# Test\n\nStatus: ready-for-dev\n\n## Acceptance Criteria\n", encoding="utf-8")
    return StoryDocResolution(
        path=story_path,
        current_state="ready-for-dev",
        acceptance_criteria=acceptance_criteria,
    )


@pytest.fixture
def agent_definition_path(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "dev-wrapper.md"
    p.write_text("# Dev specialist instructions\n\nDo the work.\n", encoding="utf-8")
    return p


@pytest.fixture
def dispatch_payload(
    fixed_timestamp: datetime,
    story_doc_resolution: StoryDocResolution,
    agent_definition_path: pathlib.Path,
) -> SpecialistDispatchPayload:
    return build_dispatch_payload(
        specialist="dev",
        story_id="2.6",
        attempt_number=0,
        story_doc_resolution=story_doc_resolution,
        agent_definition_path=agent_definition_path,
        prompt_body_renderer=default_prompt_body_renderer,
        dispatch_timestamp_factory=lambda: fixed_timestamp,
    )


@pytest.fixture
def deterministic_event_id_factory() -> Callable[[], str]:
    counter = {"n": 0}

    def factory() -> str:
        counter["n"] += 1
        return f"ev-test-{counter['n']:04d}"

    return factory


# --------------------------------------------------------------------------- #
# AC-1 module-shape tests                                                     #
# --------------------------------------------------------------------------- #


_INTRA_PACKAGE_IMPORT_ALLOWLIST = frozenset(
    {
        "loud_fail_harness._shared",
        "loud_fail_harness.envelope_validator",
        "loud_fail_harness.event_validator",
        "loud_fail_harness.orchestrator_run_entry",
        "loud_fail_harness.reconciler",
    }
)


def _collect_intra_package_imports(module_source: str) -> set[str]:
    """Walk the module's AST and collect ``from loud_fail_harness.X import ...`` source modules."""
    tree = ast.parse(module_source)
    sources: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("loud_fail_harness"):
                sources.add(module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("loud_fail_harness"):
                    sources.add(alias.name)
    return sources


def test_module_intra_package_imports_are_substrate_only() -> None:
    """AC-1: the module's intra-package imports match the documented allowlist."""
    source = inspect.getsource(specialist_dispatch)
    sources = _collect_intra_package_imports(source)
    assert sources == _INTRA_PACKAGE_IMPORT_ALLOWLIST, (
        f"intra-package import drift: got {sources}, "
        f"expected {_INTRA_PACKAGE_IMPORT_ALLOWLIST}"
    )


@pytest.mark.parametrize(
    "forbidden_module",
    ["subprocess", "requests", "httpx", "claude", "claude_code"],
)
def test_module_does_not_import_forbidden_surfaces(forbidden_module: str) -> None:
    """AC-1: forbidden import surfaces are absent."""
    source = inspect.getsource(specialist_dispatch)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith(forbidden_module), (
                    f"forbidden import: {alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith(forbidden_module), (
                f"forbidden from-import: {module}"
            )


def test_module_does_not_import_agents_namespace() -> None:
    """AC-1 + AC-3: no imports from the agents.* namespace."""
    source = inspect.getsource(specialist_dispatch)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("agents."), (
                    f"forbidden import from agents namespace: {alias.name}"
                )
                assert alias.name != "agents", "forbidden import: agents"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("agents."), (
                f"forbidden from-import from agents namespace: {module}"
            )
            assert module != "agents", "forbidden from-import: agents"


def test_no_module_top_level_find_repo_root_call() -> None:
    """AC-1 + Epic 1 retro Action #1: ``find_repo_root()`` is not called at module top level."""
    source = inspect.getsource(specialist_dispatch)
    tree = ast.parse(source)
    for node in tree.body:
        # Only top-level statements; nested function bodies are fine.
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "find_repo_root"
                and isinstance(node, (ast.Expr, ast.Assign, ast.AnnAssign))
            ):
                pytest.fail(
                    f"find_repo_root() called at module top level: line {sub.lineno}"
                )


_DOCUMENTED_EXPORTS = [
    "MarkerClassRegistry",
    "load_marker_class_registry",
    "validate_marker_emission",
    "UnknownMarkerClass",
    "SpecialistDispatchPayload",
    "build_dispatch_payload",
    "LOG_PATH_TEMPLATE",
    "persist_dispatch_log",
    "ReturnEnvelopeValidation",
    "validate_return_envelope",
    "EnvelopeValidationFailed",
    "SpecialistTimeoutExceeded",
    "make_specialist_dispatched_event",
    "make_specialist_returned_event",
    "default_event_id_factory",
    "TaskToolDispatchCallback",
    "make_task_tool_dispatch_callback",
]


@pytest.mark.parametrize("export_name", _DOCUMENTED_EXPORTS)
def test_all_enumerates_documented_exports(export_name: str) -> None:
    """AC-1: ``__all__`` enumerates the 17 documented exports."""
    assert export_name in specialist_dispatch.__all__
    assert hasattr(specialist_dispatch, export_name)


def test_all_enumerates_exactly_seventeen_names() -> None:
    """AC-1: the ``__all__`` set is exactly the 17 documented names (no drift)."""
    assert set(specialist_dispatch.__all__) == set(_DOCUMENTED_EXPORTS)


@pytest.mark.parametrize(
    "forbidden_string",
    ["from agents.", "import agents."],
)
def test_no_specialist_import_strings(forbidden_string: str) -> None:
    """AC-1 + AC-3: the module text does not contain forbidden specialist-import literals."""
    source = inspect.getsource(specialist_dispatch)
    assert forbidden_string not in source


# --------------------------------------------------------------------------- #
# AC-2 marker-class registry tests                                            #
# --------------------------------------------------------------------------- #


def test_load_marker_class_registry_default_path_loads_live_taxonomy(
    live_taxonomy_path: pathlib.Path,
) -> None:
    """AC-2: default-path resolution loads the live ``marker-taxonomy.yaml``."""
    registry = load_marker_class_registry()
    raw = yaml.safe_load(live_taxonomy_path.read_text(encoding="utf-8"))
    expected_classes = {entry["marker_class"] for entry in raw["markers"]}
    assert registry.marker_classes == frozenset(expected_classes)


def test_load_marker_class_registry_explicit_path_overrides_default(
    tmp_path: pathlib.Path,
) -> None:
    """AC-2: explicit ``taxonomy_path`` overrides the default resolution."""
    synth_path = tmp_path / "synthetic-taxonomy.yaml"
    synth_path.write_text(
        "schema_version: \"1.0\"\n"
        "markers:\n"
        "  - marker_class: synthetic-marker-A\n"
        "    diagnostic_pointer: 'test'\n"
        "    sub_classifications: []\n",
        encoding="utf-8",
    )
    registry = load_marker_class_registry(taxonomy_path=synth_path)
    assert registry.marker_classes == frozenset({"synthetic-marker-A"})


def test_validate_marker_emission_known_class_returns_none() -> None:
    """AC-2: known marker class returns ``None`` (success is absence of exception)."""
    registry = MarkerClassRegistry(marker_classes=frozenset({"specialist-timeout"}))
    result = validate_marker_emission(registry, "specialist-timeout")
    assert result is None


def test_validate_marker_emission_unknown_class_raises() -> None:
    """AC-2: unknown marker class raises ``UnknownMarkerClass``."""
    registry = MarkerClassRegistry(marker_classes=frozenset({"specialist-timeout"}))
    with pytest.raises(UnknownMarkerClass) as excinfo:
        validate_marker_emission(registry, "totally-not-a-real-marker")
    assert excinfo.value.marker_class_name == "totally-not-a-real-marker"
    assert excinfo.value.known_classes == frozenset({"specialist-timeout"})


def test_unknown_marker_class_carries_null_marker_class() -> None:
    """AC-2 + Pattern 5: ``UnknownMarkerClass.marker_class is None``."""
    assert UnknownMarkerClass.marker_class is None


def test_registry_reflects_taxonomy_mutation(tmp_path: pathlib.Path) -> None:
    """AC-2: registry tracks on-disk taxonomy mutations across reloads."""
    path = tmp_path / "synthetic-taxonomy.yaml"
    path.write_text(
        "schema_version: \"1.0\"\n"
        "markers:\n"
        "  - marker_class: synthetic-marker-class-A\n"
        "    diagnostic_pointer: 'test'\n"
        "    sub_classifications: []\n",
        encoding="utf-8",
    )
    registry_v1 = load_marker_class_registry(taxonomy_path=path)
    assert "synthetic-marker-class-A" in registry_v1
    assert "synthetic-marker-class-B" not in registry_v1

    path.write_text(
        "schema_version: \"1.0\"\n"
        "markers:\n"
        "  - marker_class: synthetic-marker-class-A\n"
        "    diagnostic_pointer: 'test'\n"
        "    sub_classifications: []\n"
        "  - marker_class: synthetic-marker-class-B\n"
        "    diagnostic_pointer: 'test'\n"
        "    sub_classifications: []\n",
        encoding="utf-8",
    )
    registry_v2 = load_marker_class_registry(taxonomy_path=path)
    assert "synthetic-marker-class-B" in registry_v2
    assert registry_v1 != registry_v2


def test_no_inline_taxonomy_literal() -> None:
    """AC-2: the substrate's source text does NOT contain a literal taxonomy mirror."""
    source = inspect.getsource(specialist_dispatch)
    # The regex looks for marker_classes assigned to a literal collection containing
    # one of four sentinel marker class names sampled from the live taxonomy.
    pattern = re.compile(
        r"\bmarker_classes\s*[:=]\s*(?:frozenset|set|\{|\[)\s*\{?\s*"
        r"['\"](?:LAD-skipped|specialist-timeout|env-setup-failed|cost-near-ceiling)['\"]"
    )
    match = pattern.search(source)
    assert match is None, (
        f"inline taxonomy literal detected at offset {match.start() if match else -1}: "
        f"{match.group(0) if match else ''}"
    )


def test_marker_class_registry_is_frozen() -> None:
    """AC-2: ``MarkerClassRegistry`` is frozen (attribute reassignment raises)."""
    registry = MarkerClassRegistry(marker_classes=frozenset({"a", "b"}))
    with pytest.raises(ValidationError):
        registry.marker_classes = frozenset({"c"})  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# AC-3 dispatch payload tests                                                 #
# --------------------------------------------------------------------------- #


def test_build_dispatch_payload_happy_path_constructs_valid_model(
    fixed_timestamp: datetime,
    story_doc_resolution: StoryDocResolution,
    agent_definition_path: pathlib.Path,
    acceptance_criteria: tuple[AcceptanceCriterion, ...],
) -> None:
    """AC-3: happy path constructs a valid payload model."""
    payload = build_dispatch_payload(
        specialist="dev",
        story_id="2.6",
        attempt_number=0,
        story_doc_resolution=story_doc_resolution,
        agent_definition_path=agent_definition_path,
        prompt_body_renderer=default_prompt_body_renderer,
        dispatch_timestamp_factory=lambda: fixed_timestamp,
    )
    assert payload.specialist == "dev"
    assert payload.story_id == "2.6"
    assert payload.attempt_number == 0
    assert payload.acceptance_criteria == acceptance_criteria
    assert payload.agent_definition_path == agent_definition_path
    assert payload.dispatch_timestamp == fixed_timestamp
    assert "Dev specialist instructions" in payload.prompt_body
    assert payload.prompt_id.startswith("prompt-2.6-dev-0-")


def test_build_dispatch_payload_reads_agent_file_as_data(
    story_doc_resolution: StoryDocResolution,
    agent_definition_path: pathlib.Path,
    fixed_timestamp: datetime,
) -> None:
    """AC-3: the substrate reads the agent file via ``Path.read_text`` (data, not import)."""
    with mock.patch.object(
        pathlib.Path, "read_text", autospec=True, return_value="STUBBED"
    ) as mock_read:
        payload = build_dispatch_payload(
            specialist="dev",
            story_id="2.6",
            attempt_number=0,
            story_doc_resolution=story_doc_resolution,
            agent_definition_path=agent_definition_path,
            prompt_body_renderer=default_prompt_body_renderer,
            dispatch_timestamp_factory=lambda: fixed_timestamp,
        )
    assert mock_read.called
    assert "STUBBED" in payload.prompt_body


def test_build_dispatch_payload_propagates_file_not_found_error(
    tmp_path: pathlib.Path,
    story_doc_resolution: StoryDocResolution,
    fixed_timestamp: datetime,
) -> None:
    """AC-3: ``FileNotFoundError`` propagates unchanged from missing agent file."""
    missing = tmp_path / "does-not-exist.md"
    with pytest.raises(FileNotFoundError):
        build_dispatch_payload(
            specialist="dev",
            story_id="2.6",
            attempt_number=0,
            story_doc_resolution=story_doc_resolution,
            agent_definition_path=missing,
            prompt_body_renderer=default_prompt_body_renderer,
            dispatch_timestamp_factory=lambda: fixed_timestamp,
        )


def test_build_dispatch_payload_uses_caller_supplied_renderer(
    story_doc_resolution: StoryDocResolution,
    agent_definition_path: pathlib.Path,
    fixed_timestamp: datetime,
) -> None:
    """AC-3: the renderer is caller-injected (sensor-not-advisor)."""
    seen: dict[str, object] = {}

    def custom_renderer(text: str, resolution: StoryDocResolution, attempt: int) -> str:
        seen["text"] = text
        seen["resolution"] = resolution
        seen["attempt"] = attempt
        return "CUSTOM"

    payload = build_dispatch_payload(
        specialist="dev",
        story_id="2.6",
        attempt_number=3,
        story_doc_resolution=story_doc_resolution,
        agent_definition_path=agent_definition_path,
        prompt_body_renderer=custom_renderer,
        dispatch_timestamp_factory=lambda: fixed_timestamp,
    )
    assert payload.prompt_body == "CUSTOM"
    assert seen["resolution"] is story_doc_resolution
    assert seen["attempt"] == 3
    assert isinstance(seen["text"], str)
    assert "Dev specialist instructions" in seen["text"]  # type: ignore[operator]


def test_build_dispatch_payload_dispatch_timestamp_factory_injection(
    story_doc_resolution: StoryDocResolution,
    agent_definition_path: pathlib.Path,
) -> None:
    """AC-3: the dispatch_timestamp_factory injects deterministic timestamps."""
    captured = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    payload = build_dispatch_payload(
        specialist="dev",
        story_id="2.6",
        attempt_number=0,
        story_doc_resolution=story_doc_resolution,
        agent_definition_path=agent_definition_path,
        prompt_body_renderer=default_prompt_body_renderer,
        dispatch_timestamp_factory=lambda: captured,
    )
    assert payload.dispatch_timestamp == captured


def test_default_prompt_body_renderer_returns_canonical_shape(
    story_doc_resolution: StoryDocResolution,
) -> None:
    """AC-3: the default renderer returns the four canonical section headings."""
    rendered = default_prompt_body_renderer(
        "AGENT_TEXT", story_doc_resolution, attempt_number=0
    )
    assert "# Specialist instructions" in rendered
    assert "# Story context" in rendered
    assert "# Acceptance criteria" in rendered
    assert "# Return contract" in rendered
    assert "AGENT_TEXT" in rendered


def test_specialist_dispatch_payload_is_frozen(
    dispatch_payload: SpecialistDispatchPayload,
) -> None:
    """AC-3: ``SpecialistDispatchPayload`` is frozen (attribute reassignment raises)."""
    with pytest.raises(ValidationError):
        dispatch_payload.story_id = "different"  # type: ignore[misc]


def test_specialist_dispatch_payload_acceptance_criteria_is_tuple(
    dispatch_payload: SpecialistDispatchPayload,
) -> None:
    """AC-3 + Epic 1 retro Action #2: the field is a ``tuple``, not a ``list``."""
    assert isinstance(dispatch_payload.acceptance_criteria, tuple)


def test_build_dispatch_payload_rejects_naive_dispatch_timestamp(
    story_doc_resolution: StoryDocResolution,
    agent_definition_path: pathlib.Path,
) -> None:
    """AC-3: naive dispatch_timestamp raises AssertionError — programmer-error invariant."""
    naive = datetime(2026, 4, 29, 12, 0, 0)  # no tzinfo
    with pytest.raises(AssertionError, match="timezone-aware"):
        build_dispatch_payload(
            specialist="dev",
            story_id="2.6",
            attempt_number=0,
            story_doc_resolution=story_doc_resolution,
            agent_definition_path=agent_definition_path,
            prompt_body_renderer=default_prompt_body_renderer,
            dispatch_timestamp_factory=lambda: naive,
        )


def test_build_dispatch_payload_prompt_id_is_unique_per_call(
    story_doc_resolution: StoryDocResolution,
    agent_definition_path: pathlib.Path,
    fixed_timestamp: datetime,
) -> None:
    """AC-3: each call to ``build_dispatch_payload`` generates a distinct ``prompt_id``."""
    kwargs: dict[str, object] = dict(
        specialist="dev",
        story_id="2.6",
        attempt_number=0,
        story_doc_resolution=story_doc_resolution,
        agent_definition_path=agent_definition_path,
        prompt_body_renderer=default_prompt_body_renderer,
        dispatch_timestamp_factory=lambda: fixed_timestamp,
    )
    p1 = build_dispatch_payload(**kwargs)  # type: ignore[arg-type]
    p2 = build_dispatch_payload(**kwargs)  # type: ignore[arg-type]
    assert p1.prompt_id != p2.prompt_id


# --------------------------------------------------------------------------- #
# AC-4 log persistence tests                                                  #
# --------------------------------------------------------------------------- #


def test_log_path_template_value() -> None:
    """AC-4: ``LOG_PATH_TEMPLATE`` matches the verbatim NFR-O3 path."""
    assert LOG_PATH_TEMPLATE == "{story_id}/{run_id}/logs/{specialist}-{attempt_number}.log"


def test_persist_dispatch_log_writes_json_to_canonical_path(
    tmp_path: pathlib.Path,
    dispatch_payload: SpecialistDispatchPayload,
    fixed_timestamp: datetime,
) -> None:
    """AC-4: ``persist_dispatch_log`` writes JSON to the canonical NFR-O3 path."""
    log_root = tmp_path / "logs"
    return_envelope = {"status": "pass", "rationale": "ok"}
    log_path = persist_dispatch_log(
        dispatch_payload,
        return_envelope,
        return_timestamp=fixed_timestamp,
        log_root=log_root,
        run_id="run-001",
    )
    expected = log_root / "2.6" / "run-001" / "logs" / "dev-0.log"
    assert log_path == expected
    assert log_path.exists()
    body = json.loads(log_path.read_text(encoding="utf-8"))
    assert body["dispatched_specialist"] == "dev"
    assert body["story_id"] == "2.6"


def test_persist_dispatch_log_creates_missing_parent_dirs(
    tmp_path: pathlib.Path,
    dispatch_payload: SpecialistDispatchPayload,
    fixed_timestamp: datetime,
) -> None:
    """AC-4: the helper creates missing parent dirs idempotently (mkdir parents=True)."""
    log_root = tmp_path / "deeply" / "nested" / "logs"
    log_path = persist_dispatch_log(
        dispatch_payload,
        {"status": "pass", "rationale": "ok"},
        return_timestamp=fixed_timestamp,
        log_root=log_root,
        run_id="run-001",
    )
    assert log_path.exists()
    assert log_path.parent.is_dir()


@pytest.mark.parametrize(
    "field",
    [
        "dispatched_specialist",
        "story_id",
        "attempt_number",
        "agent_definition_path",
        "acceptance_criteria",
        "dispatch_timestamp",
        "return_timestamp",
        "return_envelope",
        # Story 2.12 AC-5: additive runtime_duration_ms field.
        "runtime_duration_ms",
    ],
)
def test_persist_dispatch_log_log_shape_carries_nfr_o3_fields(
    field: str,
    tmp_path: pathlib.Path,
    dispatch_payload: SpecialistDispatchPayload,
    fixed_timestamp: datetime,
) -> None:
    """AC-4 + Story 2.12 AC-5: every NFR-O3 field is present in the persisted JSON."""
    log_root = tmp_path / "logs"
    log_path = persist_dispatch_log(
        dispatch_payload,
        {"status": "pass", "rationale": "ok"},
        return_timestamp=fixed_timestamp,
        log_root=log_root,
        run_id="run-001",
    )
    body = json.loads(log_path.read_text(encoding="utf-8"))
    assert field in body


def test_persist_dispatch_log_includes_runtime_duration_ms(
    tmp_path: pathlib.Path,
    story_doc_resolution: StoryDocResolution,
    agent_definition_path: pathlib.Path,
) -> None:
    """Story 2.12 AC-5: ``runtime_duration_ms`` = (return - dispatch) in milliseconds.

    Constructs a payload with dispatch_timestamp = 2026-04-29T12:00:00Z;
    invokes persist_dispatch_log with return_timestamp = 2026-04-29T12:00:01.500Z
    (1.5 seconds later); asserts ``payload["runtime_duration_ms"] == 1500``.
    """
    dispatch_ts = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
    return_ts = datetime(2026, 4, 29, 12, 0, 1, 500_000, tzinfo=timezone.utc)
    payload = build_dispatch_payload(
        specialist="dev",
        story_id="2.12",
        attempt_number=0,
        story_doc_resolution=story_doc_resolution,
        agent_definition_path=agent_definition_path,
        prompt_body_renderer=default_prompt_body_renderer,
        dispatch_timestamp_factory=lambda: dispatch_ts,
    )
    log_root = tmp_path / "logs"
    log_path = persist_dispatch_log(
        payload,
        {"status": "pass", "rationale": "ok"},
        return_timestamp=return_ts,
        log_root=log_root,
        run_id="run-001",
    )
    body = json.loads(log_path.read_text(encoding="utf-8"))
    assert body["runtime_duration_ms"] == 1500


def test_persist_dispatch_log_runtime_duration_ms_is_integer(
    tmp_path: pathlib.Path,
    story_doc_resolution: StoryDocResolution,
    agent_definition_path: pathlib.Path,
) -> None:
    """Story 2.12 AC-5: ``runtime_duration_ms`` is always ``int`` (NOT float).

    Millisecond resolution matches diagnostic-correlation precision;
    sub-millisecond precision is noise. A sub-millisecond duration
    truncates to 0; a multi-second duration carries the full integer
    millisecond count.
    """
    dispatch_ts = datetime(2026, 4, 29, 12, 0, 0, 0, tzinfo=timezone.utc)
    # Sub-millisecond duration: 100 microseconds → 0 ms (truncation).
    submilli_return = datetime(2026, 4, 29, 12, 0, 0, 100, tzinfo=timezone.utc)
    payload = build_dispatch_payload(
        specialist="dev",
        story_id="2.12",
        attempt_number=0,
        story_doc_resolution=story_doc_resolution,
        agent_definition_path=agent_definition_path,
        prompt_body_renderer=default_prompt_body_renderer,
        dispatch_timestamp_factory=lambda: dispatch_ts,
    )
    log_root = tmp_path / "logs"
    log_path = persist_dispatch_log(
        payload,
        {"status": "pass", "rationale": "ok"},
        return_timestamp=submilli_return,
        log_root=log_root,
        run_id="run-001",
    )
    body = json.loads(log_path.read_text(encoding="utf-8"))
    assert isinstance(body["runtime_duration_ms"], int)
    # Multi-second duration: 5.250 seconds → 5250 ms.
    multisec_return = datetime(2026, 4, 29, 12, 0, 5, 250_000, tzinfo=timezone.utc)
    log_path2 = persist_dispatch_log(
        payload,
        {"status": "pass", "rationale": "ok"},
        return_timestamp=multisec_return,
        log_root=log_root / "second",
        run_id="run-002",
    )
    body2 = json.loads(log_path2.read_text(encoding="utf-8"))
    assert body2["runtime_duration_ms"] == 5250
    assert isinstance(body2["runtime_duration_ms"], int)


def test_persist_dispatch_log_rejects_negative_runtime_duration(
    tmp_path: pathlib.Path,
    story_doc_resolution: StoryDocResolution,
    agent_definition_path: pathlib.Path,
) -> None:
    """Story 2.12 review patch: negative ``runtime_duration_ms`` is loud-fail rejected.

    Pattern 5 doctrine: a negative duration (return_timestamp before
    dispatch_timestamp) means clock skew / NTP backwards step / VM
    time-warp — a programmer-error invariant violation, not a value
    to silently clamp. ``persist_dispatch_log`` raises ``ValueError``
    instead of writing the corrupted log.
    """
    dispatch_ts = datetime(2026, 4, 29, 12, 0, 5, tzinfo=timezone.utc)
    # Return BEFORE dispatch — clock skewed backwards.
    return_ts = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)
    payload = build_dispatch_payload(
        specialist="dev",
        story_id="2.12",
        attempt_number=0,
        story_doc_resolution=story_doc_resolution,
        agent_definition_path=agent_definition_path,
        prompt_body_renderer=default_prompt_body_renderer,
        dispatch_timestamp_factory=lambda: dispatch_ts,
    )
    log_root = tmp_path / "logs"
    with pytest.raises(ValueError, match="negative runtime_duration_ms"):
        persist_dispatch_log(
            payload,
            {"status": "pass", "rationale": "ok"},
            return_timestamp=return_ts,
            log_root=log_root,
            run_id="run-skew",
        )
    # No log file should have been written when the guard fires.
    assert not any(log_root.rglob("*.log")), (
        "persist_dispatch_log must NOT write a log when the negative-duration "
        "guard rejects the inputs"
    )


def test_persist_dispatch_log_naive_datetime_assertion_fires(
    tmp_path: pathlib.Path,
    dispatch_payload: SpecialistDispatchPayload,
) -> None:
    """AC-4: naive ``return_timestamp`` triggers the defensive assertion."""
    naive = datetime(2026, 4, 29, 12, 0, 0)  # no tzinfo
    log_root = tmp_path / "logs"
    with pytest.raises(AssertionError):
        persist_dispatch_log(
            dispatch_payload,
            {"status": "pass", "rationale": "ok"},
            return_timestamp=naive,
            log_root=log_root,
            run_id="run-001",
        )


def test_persist_dispatch_log_propagates_oserror_unchanged(
    tmp_path: pathlib.Path,
    dispatch_payload: SpecialistDispatchPayload,
    fixed_timestamp: datetime,
) -> None:
    """AC-4: ``OSError`` from ``os.replace`` propagates unchanged (Pattern 5)."""
    log_root = tmp_path / "logs"
    with mock.patch("loud_fail_harness.specialist_dispatch.os.replace", side_effect=OSError("boom")):
        with pytest.raises(OSError, match="boom"):
            persist_dispatch_log(
                dispatch_payload,
                {"status": "pass", "rationale": "ok"},
                return_timestamp=fixed_timestamp,
                log_root=log_root,
                run_id="run-001",
            )


def test_persist_dispatch_log_atomic_write_no_partial_file(
    tmp_path: pathlib.Path,
    dispatch_payload: SpecialistDispatchPayload,
    fixed_timestamp: datetime,
) -> None:
    """AC-4: on rename failure, the temp file is cleaned up + dest does not exist."""
    log_root = tmp_path / "logs"
    expected_dest = log_root / "2.6" / "run-001" / "logs" / "dev-0.log"
    with mock.patch(
        "loud_fail_harness.specialist_dispatch.os.replace",
        side_effect=OSError("simulated rename failure"),
    ):
        with pytest.raises(OSError):
            persist_dispatch_log(
                dispatch_payload,
                {"status": "pass", "rationale": "ok"},
                return_timestamp=fixed_timestamp,
                log_root=log_root,
                run_id="run-001",
            )
    assert not expected_dest.exists()
    # Temp file cleanup — no .tmp file in the parent dir.
    leftover_temp_files = list(expected_dest.parent.glob("*.tmp*"))
    assert leftover_temp_files == []


# --------------------------------------------------------------------------- #
# AC-5 envelope validation tests                                              #
# --------------------------------------------------------------------------- #


def test_validate_return_envelope_happy_path_returns_valid_true(
    repo_root: pathlib.Path,
) -> None:
    """AC-5: valid envelope returns ``valid=True`` with empty errors."""
    fixture = repo_root / "examples" / "envelopes" / "dev-pass.yaml"
    envelope = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    result = validate_return_envelope(envelope)
    assert result.valid is True
    assert result.errors == ()
    assert result.validated_envelope == envelope


@pytest.mark.parametrize(
    "envelope_dict",
    [
        # FR52 forbidden-flow-policy field
        {
            "status": "pass",
            "artifacts": [],
            "findings": [],
            "rationale": "ok",
            "next_action": "retry",
        },
        # missing required field
        {
            "status": "pass",
            "artifacts": [],
            "findings": [],
        },
        # additional property
        {
            "status": "pass",
            "artifacts": [],
            "findings": [],
            "rationale": "ok",
            "totally_made_up_field": True,
        },
    ],
)
def test_validate_return_envelope_invalid_returns_valid_false_with_errors(
    envelope_dict: dict,
) -> None:
    """AC-5: invalid envelopes return ``valid=False`` with error messages."""
    result = validate_return_envelope(envelope_dict)
    assert result.valid is False
    assert len(result.errors) >= 1
    assert result.validated_envelope is None


def test_validate_return_envelope_strict_raises_envelope_validation_failed() -> None:
    """AC-5: the strict variant raises ``EnvelopeValidationFailed``."""
    bad = {"status": "pass", "artifacts": [], "findings": []}  # missing rationale
    with pytest.raises(EnvelopeValidationFailed) as excinfo:
        validate_return_envelope_strict(bad)
    assert len(excinfo.value.errors) >= 1
    assert excinfo.value.envelope_dict == bad


def test_validate_return_envelope_composes_envelope_validator_exclusively(
    repo_root: pathlib.Path,
) -> None:
    """AC-5: the substrate composes ``validate_envelope`` + ``format_errors`` exclusively."""
    fixture = repo_root / "examples" / "envelopes" / "dev-pass.yaml"
    envelope = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    with mock.patch(
        "loud_fail_harness.specialist_dispatch.validate_envelope",
        return_value=[],
    ) as mock_validate:
        result = validate_return_envelope(envelope)
    assert result.valid is True
    assert mock_validate.call_count == 1
    args, _ = mock_validate.call_args
    assert args[0] == envelope


def test_envelope_validation_failed_carries_null_marker_class() -> None:
    """AC-5 + Pattern 5: ``EnvelopeValidationFailed.marker_class is None``."""
    assert EnvelopeValidationFailed.marker_class is None


# --------------------------------------------------------------------------- #
# AC-6 timeout exception tests                                                #
# --------------------------------------------------------------------------- #


def test_specialist_timeout_exceeded_carries_marker_class_literal() -> None:
    """AC-6: ``SpecialistTimeoutExceeded.marker_class == 'specialist-timeout'`` (Literal)."""
    assert SpecialistTimeoutExceeded.marker_class == "specialist-timeout"


def test_specialist_timeout_exceeded_carries_sub_cause_literal() -> None:
    """AC-6: ``SpecialistTimeoutExceeded.sub_cause == 'timeout-exceeded'`` (Literal)."""
    assert SpecialistTimeoutExceeded.sub_cause == "timeout-exceeded"


def test_specialist_timeout_exceeded_marker_class_in_registry() -> None:
    """AC-6: the marker class identifier is present in the live taxonomy registry."""
    registry = load_marker_class_registry()
    assert SpecialistTimeoutExceeded.marker_class in registry


def test_specialist_timeout_exceeded_sub_cause_in_taxonomy_sub_classifications(
    live_taxonomy_path: pathlib.Path,
) -> None:
    """AC-6: the sub_cause is in the marker entry's ``sub_classifications`` list."""
    raw = yaml.safe_load(live_taxonomy_path.read_text(encoding="utf-8"))
    timeout_entry = next(
        e for e in raw["markers"] if e["marker_class"] == "specialist-timeout"
    )
    assert SpecialistTimeoutExceeded.sub_cause in timeout_entry["sub_classifications"]


def test_specialist_timeout_exceeded_str_form_carries_pattern_5_diagnostic() -> None:
    """AC-6: the ``__str__`` form names the marker class + sub_cause + actionable pointer."""
    exc = SpecialistTimeoutExceeded(
        timeout_seconds=900,
        specialist="dev",
        story_id="2.6",
        attempt_number=0,
    )
    s = str(exc)
    assert "SpecialistTimeoutExceeded" in s
    assert "specialist-timeout" in s
    assert "timeout-exceeded" in s
    assert "900" in s
    assert "marker-taxonomy.yaml" in s


# --------------------------------------------------------------------------- #
# AC-7 event emission tests                                                   #
# --------------------------------------------------------------------------- #


def test_make_specialist_dispatched_event_canonical_shape(
    dispatch_payload: SpecialistDispatchPayload,
    deterministic_event_id_factory,
) -> None:
    """AC-7: ``make_specialist_dispatched_event`` returns the documented canonical shape."""
    event = make_specialist_dispatched_event(
        dispatch_payload, event_id_factory=deterministic_event_id_factory
    )
    assert event["event_class"] == "specialist-dispatched"
    assert event["event_id"] == "ev-test-0001"
    assert event["timestamp"] == dispatch_payload.dispatch_timestamp.isoformat()
    assert event["story_id"] == dispatch_payload.story_id
    assert event["specialist"] == dispatch_payload.specialist
    assert event["retry_attempt"] == dispatch_payload.attempt_number
    assert event["prompt_id"] == dispatch_payload.prompt_id
    assert "dispatch_seq" not in event


def test_make_specialist_dispatched_event_validates_against_schema(
    dispatch_payload: SpecialistDispatchPayload,
    deterministic_event_id_factory,
    live_event_schema_path: pathlib.Path,
) -> None:
    """AC-7: the constructed event passes ``event_validator.validate_event``."""
    from loud_fail_harness.event_validator import validate_event

    event = make_specialist_dispatched_event(
        dispatch_payload, event_id_factory=deterministic_event_id_factory
    )
    schema = load_schema(live_event_schema_path)
    errors = validate_event(event, schema)
    assert errors == []


def test_make_specialist_dispatched_event_with_dispatch_seq_includes_field(
    dispatch_payload: SpecialistDispatchPayload,
    deterministic_event_id_factory,
) -> None:
    """AC-7: ``dispatch_seq`` is included when supplied."""
    event = make_specialist_dispatched_event(
        dispatch_payload,
        event_id_factory=deterministic_event_id_factory,
        dispatch_seq=5,
    )
    assert event["dispatch_seq"] == 5


def test_make_specialist_returned_event_canonical_shape(
    dispatch_payload: SpecialistDispatchPayload,
    deterministic_event_id_factory,
    fixed_timestamp: datetime,
) -> None:
    """AC-7: ``make_specialist_returned_event`` returns the documented canonical shape."""
    return_envelope = {"status": "pass", "rationale": "ok"}
    event = make_specialist_returned_event(
        dispatch_payload,
        return_envelope,
        event_id_factory=deterministic_event_id_factory,
        return_timestamp=fixed_timestamp,
    )
    assert event["event_class"] == "specialist-returned"
    assert event["status"] == "pass"
    assert event["timestamp"] == fixed_timestamp.isoformat()
    assert "envelope_artifact_path" not in event


def test_dispatched_and_returned_events_share_prompt_id(
    dispatch_payload: SpecialistDispatchPayload,
    deterministic_event_id_factory,
    fixed_timestamp: datetime,
) -> None:
    """ADR-006 Combo 3 / A3': dispatched and returned events for the same dispatch
    carry the identical ``prompt_id`` correlation key."""
    dispatched = make_specialist_dispatched_event(
        dispatch_payload, event_id_factory=deterministic_event_id_factory
    )
    returned = make_specialist_returned_event(
        dispatch_payload,
        {"status": "pass", "rationale": "ok"},
        event_id_factory=deterministic_event_id_factory,
        return_timestamp=fixed_timestamp,
    )
    assert dispatched["prompt_id"] == returned["prompt_id"]
    assert dispatched["prompt_id"] == dispatch_payload.prompt_id


def test_make_specialist_returned_event_validates_against_schema(
    dispatch_payload: SpecialistDispatchPayload,
    deterministic_event_id_factory,
    fixed_timestamp: datetime,
    live_event_schema_path: pathlib.Path,
) -> None:
    """AC-7: the constructed returned-event passes the schema validator."""
    from loud_fail_harness.event_validator import validate_event

    event = make_specialist_returned_event(
        dispatch_payload,
        {"status": "fail", "rationale": "ok"},
        event_id_factory=deterministic_event_id_factory,
        return_timestamp=fixed_timestamp,
    )
    schema = load_schema(live_event_schema_path)
    errors = validate_event(event, schema)
    assert errors == []


def test_make_specialist_returned_event_with_decision_needed_status_validates(
    dispatch_payload: SpecialistDispatchPayload,
    deterministic_event_id_factory,
    fixed_timestamp: datetime,
    live_event_schema_path: pathlib.Path,
) -> None:
    """AC-7 + AC-8 regression: ``status='decision-needed'`` validates post-bump."""
    from loud_fail_harness.event_validator import validate_event

    event = make_specialist_returned_event(
        dispatch_payload,
        {"status": "decision-needed", "rationale": "ok"},
        event_id_factory=deterministic_event_id_factory,
        return_timestamp=fixed_timestamp,
    )
    assert event["status"] == "decision-needed"
    schema = load_schema(live_event_schema_path)
    errors = validate_event(event, schema)
    assert errors == []


def test_make_specialist_returned_event_with_envelope_artifact_path_includes_field(
    dispatch_payload: SpecialistDispatchPayload,
    deterministic_event_id_factory,
    fixed_timestamp: datetime,
    tmp_path: pathlib.Path,
) -> None:
    """AC-7: ``envelope_artifact_path`` is included when supplied."""
    artifact = tmp_path / "envelope.yaml"
    artifact.write_text("status: pass\n", encoding="utf-8")
    event = make_specialist_returned_event(
        dispatch_payload,
        {"status": "pass", "rationale": "ok"},
        event_id_factory=deterministic_event_id_factory,
        return_timestamp=fixed_timestamp,
        envelope_artifact_path=artifact,
    )
    assert event["envelope_artifact_path"] == str(artifact)


def test_default_event_id_factory_returns_unique_ids() -> None:
    """AC-7: the default factory returns unique ids across calls."""
    ids = {default_event_id_factory() for _ in range(10)}
    assert len(ids) == 10
    for eid in ids:
        assert eid.startswith("ev-2-6-dispatch-")


def test_event_construction_failed_carries_null_marker_class() -> None:
    """AC-7 + Pattern 5: ``EventConstructionFailed.marker_class is None``."""
    assert EventConstructionFailed.marker_class is None


def test_make_specialist_dispatched_event_invalid_payload_raises_event_construction_failed(
    story_doc_resolution: StoryDocResolution,
    agent_definition_path: pathlib.Path,
) -> None:
    """AC-7 defensive path: an invalid payload triggers ``EventConstructionFailed``.

    Construct a payload manually that bypasses Pydantic's defensive validation,
    then mock ``validate_event`` to surface a synthetic error so the helper's
    defensive validation pass surfaces the failure mode.
    """
    payload = build_dispatch_payload(
        specialist="dev",
        story_id="2.6",
        attempt_number=0,
        story_doc_resolution=story_doc_resolution,
        agent_definition_path=agent_definition_path,
        prompt_body_renderer=default_prompt_body_renderer,
        dispatch_timestamp_factory=lambda: datetime(
            2026, 4, 29, tzinfo=timezone.utc
        ),
    )

    class FakeError:
        message = "synthetic validation error"

    with mock.patch(
        "loud_fail_harness.specialist_dispatch.validate_event",
        return_value=[FakeError()],
    ):
        with pytest.raises(EventConstructionFailed) as excinfo:
            make_specialist_dispatched_event(
                payload, event_id_factory=default_event_id_factory
            )
    assert excinfo.value.event_class_name == "specialist-dispatched"


def test_event_id_factory_is_caller_injected(
    dispatch_payload: SpecialistDispatchPayload,
) -> None:
    """AC-7: the helper invokes the caller-supplied factory, NOT a hardcoded uuid."""
    factory_calls = {"n": 0}

    def factory() -> str:
        factory_calls["n"] += 1
        return f"ev-injected-{factory_calls['n']}"

    event = make_specialist_dispatched_event(dispatch_payload, event_id_factory=factory)
    assert event["event_id"] == "ev-injected-1"
    assert factory_calls["n"] == 1


# --------------------------------------------------------------------------- #
# AC-8 schema-bump tests                                                      #
# --------------------------------------------------------------------------- #


def test_orchestrator_event_schema_version_is_1_2(
    live_event_schema_path: pathlib.Path,
) -> None:
    """AC-8: ``schema_version: '1.2'`` post-bump."""
    schema = yaml.safe_load(live_event_schema_path.read_text(encoding="utf-8"))
    assert schema["schema_version"] == "1.2"


def test_specialist_returned_status_enum_includes_decision_needed(
    live_event_schema_path: pathlib.Path,
) -> None:
    """AC-8: the ``specialist-returned`` branch's ``status`` enum includes ``decision-needed``."""
    schema = yaml.safe_load(live_event_schema_path.read_text(encoding="utf-8"))
    branches = schema["oneOf"]
    returned_branch = next(
        b
        for b in branches
        if b["properties"]["event_class"].get("const") == "specialist-returned"
    )
    enum = returned_branch["properties"]["status"]["enum"]
    assert "decision-needed" in enum


def test_specialist_returned_status_enum_order_matches_last_envelope_status(
    live_event_schema_path: pathlib.Path,
) -> None:
    """AC-8: the enum order matches the ``last_envelope_status`` enum verbatim."""
    schema = yaml.safe_load(live_event_schema_path.read_text(encoding="utf-8"))
    branches = schema["oneOf"]
    returned_branch = next(
        b
        for b in branches
        if b["properties"]["event_class"].get("const") == "specialist-returned"
    )
    halted_branch = next(
        b
        for b in branches
        if b["properties"]["event_class"].get("const") == "state-transition-halted"
    )
    returned_enum = returned_branch["properties"]["status"]["enum"]
    halted_enum = halted_branch["properties"]["last_envelope_status"]["oneOf"][0]["enum"]
    assert returned_enum == halted_enum
    assert returned_enum == ["pass", "fail", "decision-needed", "blocked"]


# --------------------------------------------------------------------------- #
# AC-10 callback factory tests                                                #
# --------------------------------------------------------------------------- #


def test_make_task_tool_dispatch_callback_returns_callable_matching_protocol(
    tmp_path: pathlib.Path,
) -> None:
    """AC-10: returned closure is structurally compatible with the runtime-checkable Protocol."""
    registry = MarkerClassRegistry(marker_classes=frozenset({"specialist-timeout"}))
    callback = make_task_tool_dispatch_callback(
        registry=registry,
        log_root=tmp_path / "logs",
        agent_definition_dir=tmp_path / "agents",
    )
    assert isinstance(callback, TaskToolDispatchCallback)


def test_make_task_tool_dispatch_callback_returned_callable_matches_dispatch_callback_signature(
    tmp_path: pathlib.Path,
    story_doc_resolution: StoryDocResolution,
) -> None:
    """AC-10: the closure accepts Story 2.5's dispatch keyword-only argument set."""
    registry = MarkerClassRegistry(marker_classes=frozenset({"specialist-timeout"}))
    callback = make_task_tool_dispatch_callback(
        registry=registry,
        log_root=tmp_path / "logs",
        agent_definition_dir=tmp_path / "agents",
    )
    sig = inspect.signature(callback)
    expected_kwargs = {
        "specialist",
        "story_id",
        "run_state_path",
        "story_doc_resolution",
        "event_log_appender",
    }
    assert set(sig.parameters.keys()) == expected_kwargs
    for name, param in sig.parameters.items():
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
            f"parameter {name} is not keyword-only"
        )

    # And the closure raises NotImplementedError if invoked from pure Python
    # (substrate-vs-LLM-runtime boundary marker per AC-10).
    def _appender(_event: dict) -> None:
        return None

    with pytest.raises(NotImplementedError, match="Task tool"):
        callback(
            specialist="dev",
            story_id="2.6",
            run_state_path=tmp_path / "run-state.yaml",
            story_doc_resolution=story_doc_resolution,
            event_log_appender=_appender,
        )

    # The closure's return annotation references DispatchCallbackResult (string-form
    # under `from __future__ import annotations`).
    assert sig.return_annotation in (DispatchCallbackResult, "DispatchCallbackResult")


def test_make_task_tool_dispatch_callback_default_timeout_is_900_seconds() -> None:
    """AC-10 + NFR-P2: the factory's default ``timeout_seconds`` is 900 (15 min)."""
    sig = inspect.signature(make_task_tool_dispatch_callback)
    assert sig.parameters["timeout_seconds"].default == 900


def test_make_task_tool_dispatch_callback_accepts_caller_overridden_timeout(
    tmp_path: pathlib.Path,
) -> None:
    """AC-10: the timeout parameter is configurable per-callable at construction time."""
    registry = MarkerClassRegistry(marker_classes=frozenset({"specialist-timeout"}))
    # Verify construction succeeds with a non-default timeout.
    callback = make_task_tool_dispatch_callback(
        registry=registry,
        log_root=tmp_path / "logs",
        agent_definition_dir=tmp_path / "agents",
        timeout_seconds=60,
    )
    assert callable(callback)
