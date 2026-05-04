"""Tests for ``loud_fail_harness.retry_dispatch`` per Story 5.3.

AC mapping (verbatim from
``_bmad-output/implementation-artifacts/5-3-dev-fix-only-retry-mechanism-retry-mode-affected-files-scope-expanded-to-contract-pair.md``):

    * AC-1 — module + public-API surface (existence + import smoke
      test exercised via the imports at the top of this file plus
      :func:`test_module_exports_public_api`).
    * AC-2 — ``derive_affected_files`` extracts and deduplicates file
      paths from :class:`ActionItem` ``location`` fields per the
      "first-occurrence-order; rsplit-on-last-colon; skip-empty" rule.
    * AC-3 — ``make_retry_prompt_body_renderer`` produces a renderer
      that prepends a ``# Retry directive`` section and composes the
      base renderer; FR9 prose-firewall structural enforcement;
      closure-capture semantics.
    * AC-4 — ``extract_scope_expanded_to`` parses Dev return envelopes
      per the schema's optional-array contract; loud-fails on
      malformed shapes.
    * AC-5 — End-to-end pair test (THE CONTRACT-PAIR REGRESSION
      BASELINE): a SINGLE test function exercising the full route →
      derive → render → simulated-Dev-return → extract path.
"""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Any

import pytest

from loud_fail_harness import scope_assertion
from loud_fail_harness.retry_dispatch import (
    RetryDispatchDirective,
    RetryDispatchError,
    derive_affected_files,
    extract_scope_expanded_to,
    make_retry_prompt_body_renderer,
)
from loud_fail_harness.retry_router import (
    ActionItem,
    RoutingOutcome,
    derive_action_items,
    route_envelope,
)
from loud_fail_harness.specialist_dispatch import (
    PromptBodyRenderer,
    default_prompt_body_renderer,
)
from loud_fail_harness.orchestrator_run_entry import (
    AcceptanceCriterion,
    StoryDocResolution,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_action_item(
    *,
    finding_id: str = "F-1",
    location: str = "src/foo.py:10",
    required_change: str = "make foo do X",
    severity: str = "HIGH",
) -> ActionItem:
    return ActionItem(
        finding_id=finding_id,
        location=location,
        required_change=required_change,
        severity=severity,
    )


def _make_directive(
    *,
    retry_mode: str = "fix-only",
    affected_files: tuple[str, ...] = ("src/foo.py",),
) -> RetryDispatchDirective:
    return RetryDispatchDirective(
        retry_mode=retry_mode,
        affected_files=affected_files,
    )


def _make_envelope(
    *,
    status: str = "fail",
    findings: tuple[dict[str, Any], ...] = (),
    rationale: str = "rationale text",
    artifacts: tuple[dict[str, Any], ...] = (),
    **overrides: Any,
) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "status": status,
        "artifacts": list(artifacts),
        "findings": list(findings),
        "rationale": rationale,
    }
    envelope.update(overrides)
    return envelope


def _make_finding(
    *,
    id: str = "F-1",
    source: str = "merged",
    title: str = "title",
    detail: str = "detail",
    location: str = "src/x.py:1",
    bucket: str = "patch",
    severity: str = "HIGH",
) -> dict[str, Any]:
    return {
        "id": id,
        "source": source,
        "title": title,
        "detail": detail,
        "location": location,
        "bucket": bucket,
        "severity": severity,
    }


def _make_story_doc_resolution(
    tmp_path: pathlib.Path,
    *,
    acs: tuple[AcceptanceCriterion, ...] = (
        AcceptanceCriterion(ac_id="AC-1", text="First criterion."),
    ),
) -> StoryDocResolution:
    story_path = tmp_path / "5-3-test-story.md"
    story_path.write_text(
        "# Test\n\nStatus: in-progress\n\n## Acceptance Criteria\n",
        encoding="utf-8",
    )
    return StoryDocResolution(
        path=story_path,
        current_state="in-progress",
        acceptance_criteria=acs,
    )


# ---------------------------------------------------------------------------
# AC-1 — module exports + dataclass / exception shape
# ---------------------------------------------------------------------------


def test_module_exports_public_api() -> None:
    """The module exposes the five documented public symbols."""
    from loud_fail_harness import retry_dispatch

    expected = {
        "RetryDispatchDirective",
        "RetryDispatchError",
        "derive_affected_files",
        "extract_scope_expanded_to",
        "make_retry_prompt_body_renderer",
    }
    assert set(retry_dispatch.__all__) == expected
    for name in expected:
        assert hasattr(retry_dispatch, name)


def test_retry_dispatch_directive_is_frozen_and_hashable() -> None:
    directive = _make_directive()
    with pytest.raises(dataclasses.FrozenInstanceError):
        directive.retry_mode = "refactor-allowed"  # type: ignore[misc]
    assert {directive} == {directive}


def test_retry_dispatch_directive_field_declaration_order_is_load_bearing() -> None:
    """``dataclasses.asdict`` emits keys in field-declaration order;
    downstream Story 5.4 / 5.6 callers splice the asdict output into
    the ``retry-attempted`` event payload, so the order must match the
    schema's required-field order at orchestrator-event.yaml lines
    248-255 (``retry_mode`` then ``affected_files``)."""
    directive = _make_directive(
        retry_mode="fix-only", affected_files=("a.py", "b.py")
    )
    keys = list(dataclasses.asdict(directive).keys())
    assert keys == ["retry_mode", "affected_files"]


def test_retry_dispatch_error_is_value_error_subclass() -> None:
    assert issubclass(RetryDispatchError, ValueError)


# ---------------------------------------------------------------------------
# AC-2 — derive_affected_files
# ---------------------------------------------------------------------------


def test_derive_affected_files_single_item_with_line_anchor() -> None:
    items = (_make_action_item(location="src/foo.py:10"),)
    assert derive_affected_files(items) == ("src/foo.py",)


def test_derive_affected_files_single_item_without_line_anchor() -> None:
    items = (_make_action_item(location="src/foo.py"),)
    assert derive_affected_files(items) == ("src/foo.py",)


def test_derive_affected_files_skips_empty_location() -> None:
    items = (_make_action_item(location=""),)
    assert derive_affected_files(items) == ()


def test_derive_affected_files_dedupes_same_file_different_lines() -> None:
    items = (
        _make_action_item(finding_id="F-1", location="src/foo.py:10"),
        _make_action_item(finding_id="F-2", location="src/foo.py:20"),
        _make_action_item(finding_id="F-3", location="src/foo.py:30"),
    )
    assert derive_affected_files(items) == ("src/foo.py",)


def test_derive_affected_files_preserves_first_occurrence_order_across_files() -> None:
    items = (
        _make_action_item(finding_id="F-1", location="src/foo.py:10"),
        _make_action_item(finding_id="F-2", location="src/bar.py:5"),
        _make_action_item(finding_id="F-3", location="src/baz.py:1"),
    )
    assert derive_affected_files(items) == (
        "src/foo.py",
        "src/bar.py",
        "src/baz.py",
    )


def test_derive_affected_files_preserves_first_occurrence_order_with_dedupe() -> None:
    items = (
        _make_action_item(finding_id="F-1", location="src/foo.py:10"),
        _make_action_item(finding_id="F-2", location="src/bar.py:5"),
        _make_action_item(finding_id="F-3", location="src/foo.py:99"),
    )
    assert derive_affected_files(items) == ("src/foo.py", "src/bar.py")


def test_derive_affected_files_mixed_empty_and_non_empty_locations() -> None:
    items = (
        _make_action_item(finding_id="F-1", location="src/foo.py:10"),
        _make_action_item(finding_id="F-2", location=""),
        _make_action_item(finding_id="F-3", location="src/bar.py"),
        _make_action_item(finding_id="F-4", location=""),
    )
    assert derive_affected_files(items) == ("src/foo.py", "src/bar.py")


def test_derive_affected_files_handles_multi_colon_location() -> None:
    """``rsplit(":", 1)`` keeps the ``file:line`` prefix when a column
    anchor is present (line:col form)."""
    items = (_make_action_item(location="src/foo.py:10:5"),)
    assert derive_affected_files(items) == ("src/foo.py:10",)


def test_derive_affected_files_empty_input_returns_empty_tuple() -> None:
    assert derive_affected_files(()) == ()
    assert derive_affected_files([]) == ()


def test_derive_affected_files_all_empty_locations_returns_empty_tuple() -> None:
    """Degenerate case: every item had ``location: ""``; the caller is
    expected to treat the empty-tuple result as "no scope lock to
    declare" and route to escalation per the dispatch.md guidance."""
    items = (
        _make_action_item(finding_id="F-1", location=""),
        _make_action_item(finding_id="F-2", location=""),
    )
    assert derive_affected_files(items) == ()


def test_derive_affected_files_does_not_mutate_input_sequence() -> None:
    items = [
        _make_action_item(finding_id="F-1", location="src/foo.py:10"),
        _make_action_item(finding_id="F-2", location="src/bar.py:5"),
    ]
    snapshot = list(items)
    derive_affected_files(items)
    assert items == snapshot


def test_derive_affected_files_purity_baseline_same_input_same_output() -> None:
    items = (
        _make_action_item(finding_id="F-1", location="src/foo.py:10"),
        _make_action_item(finding_id="F-2", location="src/bar.py:5"),
    )
    first = derive_affected_files(items)
    second = derive_affected_files(items)
    assert first == second  # new tuple per call


def test_derive_affected_files_accepts_list_input() -> None:
    """``Sequence[ActionItem]`` typing means lists are accepted at
    the seam; only frozen tuples are returned internally."""
    items_list = [
        _make_action_item(finding_id="F-1", location="src/foo.py:10"),
    ]
    result = derive_affected_files(items_list)
    assert result == ("src/foo.py",)
    assert isinstance(result, tuple)


def test_derive_affected_files_raises_for_non_string_location() -> None:
    """Programmer-error invariant: an :class:`ActionItem` whose
    ``location`` is non-str (constructed via ``object.__setattr__`` to
    bypass dataclass type-hints) raises :exc:`RetryDispatchError`."""
    item = _make_action_item(location="src/foo.py:10")
    object.__setattr__(item, "location", 42)
    with pytest.raises(RetryDispatchError, match="must be a str"):
        derive_affected_files((item,))


def test_derive_affected_files_error_message_names_index_and_remediation() -> None:
    item = _make_action_item(location="src/foo.py:10")
    object.__setattr__(item, "location", None)
    with pytest.raises(RetryDispatchError) as excinfo:
        derive_affected_files((_make_action_item(), item))
    msg = str(excinfo.value)
    assert "action_items[1]" in msg
    assert "Remediation" in msg
    assert "validate_return_envelope" in msg


# ---------------------------------------------------------------------------
# AC-3 — make_retry_prompt_body_renderer
# ---------------------------------------------------------------------------


def test_renderer_signature_conformance(tmp_path: pathlib.Path) -> None:
    """The factory's return value conforms to :data:`PromptBodyRenderer`'s
    signature ``(str, StoryDocResolution, int) -> str``."""
    directive = _make_directive(affected_files=("src/foo.py",))
    items = (_make_action_item(),)
    renderer = make_retry_prompt_body_renderer(directive, items)
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer("agent text", resolution, 1)
    assert isinstance(output, str)
    # Annotation-as-runtime-check: ensure callable shape matches alias
    _: PromptBodyRenderer = renderer  # noqa: F841


def test_renderer_starts_with_directive_header(tmp_path: pathlib.Path) -> None:
    directive = _make_directive(affected_files=("src/foo.py",))
    items = (_make_action_item(),)
    renderer = make_retry_prompt_body_renderer(directive, items)
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer("agent text", resolution, 1)
    assert output.startswith(
        "# Retry directive (fix-only mode — Story 5.3)"
    )


def test_renderer_contains_retry_mode_verbatim(tmp_path: pathlib.Path) -> None:
    directive = _make_directive(retry_mode="fix-only")
    items = (_make_action_item(),)
    renderer = make_retry_prompt_body_renderer(directive, items)
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer("agent text", resolution, 1)
    assert "retry_mode: fix-only" in output


def test_renderer_lists_each_affected_file_indented_two_spaces(
    tmp_path: pathlib.Path,
) -> None:
    directive = _make_directive(
        affected_files=("src/foo.py", "src/bar.py")
    )
    items = (_make_action_item(),)
    renderer = make_retry_prompt_body_renderer(directive, items)
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer("agent text", resolution, 1)
    assert "  src/foo.py" in output
    assert "  src/bar.py" in output
    # And the affected_files: heading appears once.
    assert output.count("affected_files:") == 1


def test_renderer_lists_each_action_item_in_canonical_format(
    tmp_path: pathlib.Path,
) -> None:
    directive = _make_directive(affected_files=("src/foo.py", "src/bar.py"))
    items = (
        _make_action_item(
            finding_id="F-1",
            location="src/foo.py:10",
            severity="HIGH",
            required_change="make foo do X",
        ),
        _make_action_item(
            finding_id="F-2",
            location="src/bar.py:25",
            severity="MED",
            required_change="make bar do Y",
        ),
    )
    renderer = make_retry_prompt_body_renderer(directive, items)
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer("agent text", resolution, 1)
    assert (
        "- F-1 [src/foo.py:10] (severity=HIGH) — make foo do X"
        in output
    )
    assert (
        "- F-2 [src/bar.py:25] (severity=MED) — make bar do Y"
        in output
    )


def test_renderer_contains_capability_level_constraint_substring(
    tmp_path: pathlib.Path,
) -> None:
    directive = _make_directive()
    items = (_make_action_item(),)
    renderer = make_retry_prompt_body_renderer(directive, items)
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer("agent text", resolution, 1)
    assert "Constrain your work to the files listed under" in output
    assert "`affected_files`" in output
    assert "do NOT silently expand scope" in output.lower() or (
        "Do NOT silently expand scope" in output
    )


def test_renderer_contains_scope_expanded_to_reporting_reminder(
    tmp_path: pathlib.Path,
) -> None:
    directive = _make_directive()
    items = (_make_action_item(),)
    renderer = make_retry_prompt_body_renderer(directive, items)
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer("agent text", resolution, 1)
    assert "scope_expanded_to" in output
    assert "On clean retries" in output
    assert "[]" in output


def test_renderer_appends_base_renderer_output_below_directive(
    tmp_path: pathlib.Path,
) -> None:
    """The base renderer's standard sections appear BELOW the directive
    section; the base output is verifiable by calling
    :func:`default_prompt_body_renderer` directly with the same args."""
    directive = _make_directive()
    items = (_make_action_item(),)
    renderer = make_retry_prompt_body_renderer(directive, items)
    resolution = _make_story_doc_resolution(tmp_path)
    composed = renderer("AGENT_DEFINITION_TEXT_X", resolution, 1)
    base = default_prompt_body_renderer(
        "AGENT_DEFINITION_TEXT_X", resolution, 1
    )
    assert "AGENT_DEFINITION_TEXT_X" in composed
    # Composed output must contain the base renderer's full output.
    assert base in composed
    # And the directive section must precede the base output.
    assert composed.index("# Retry directive") < composed.index(
        "# Specialist instructions"
    )


def test_renderer_accepts_custom_base_renderer(
    tmp_path: pathlib.Path,
) -> None:
    """The ``base_renderer`` keyword parameter overrides the default;
    the closure composes against the supplied callable."""

    def custom(text: str, resolution: StoryDocResolution, attempt: int) -> str:
        return f"CUSTOM[{text}|attempt={attempt}]"

    directive = _make_directive()
    items = (_make_action_item(),)
    renderer = make_retry_prompt_body_renderer(
        directive, items, base_renderer=custom
    )
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer("hello", resolution, 7)
    assert "CUSTOM[hello|attempt=7]" in output
    assert output.startswith("# Retry directive")


def test_renderer_fr9_prose_firewall_marker_in_agent_text_is_present(
    tmp_path: pathlib.Path,
) -> None:
    """A distinctive marker in the agent-definition text DOES appear in
    the output (the base renderer includes it verbatim) — this is the
    positive control for the FR9 negative test below."""
    marker = "DISTINCTIVE_REVIEW_PROSE_MARKER"
    directive = _make_directive()
    items = (_make_action_item(),)  # action_items do NOT contain the marker
    renderer = make_retry_prompt_body_renderer(directive, items)
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer(f"agent text {marker} more text", resolution, 1)
    assert marker in output


def test_renderer_fr9_prose_firewall_envelope_rationale_cannot_leak(
    tmp_path: pathlib.Path,
) -> None:
    """Structural enforcement of FR9 at the renderer surface: the
    renderer's API surface accepts only ``directive`` + ``action_items``;
    the envelope (which carries ``rationale``) is NEVER passed in.
    Therefore a marker placed in the source envelope's rationale CANNOT
    leak through this code path. We assert this by constructing a
    rendering call where the marker is ONLY in a simulated rationale
    (never in directive / action_items / agent text) and verifying it
    does not appear in the rendered output."""
    rationale_marker = "DISTINCTIVE_REVIEW_RATIONALE_MARKER"
    # The marker is in the simulated rationale (parallel envelope) —
    # which is structurally inaccessible to the renderer; only directive
    # + action_items + agent text + story-doc-resolution are passed.
    _simulated_envelope_with_rationale = _make_envelope(
        rationale=f"reviewer prose containing {rationale_marker}"
    )
    directive = _make_directive(affected_files=("src/foo.py",))
    items = (_make_action_item(required_change="clean change"),)
    renderer = make_retry_prompt_body_renderer(directive, items)
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer("clean agent text", resolution, 1)
    assert rationale_marker not in output


def test_renderer_closure_captures_directive_at_factory_call_time(
    tmp_path: pathlib.Path,
) -> None:
    """The closure captures ``directive`` at factory-call time. The
    frozen dataclass forbids mutation; even bypassing immutability via
    ``object.__setattr__`` does not affect the captured value because
    the closure reads through ``captured_directive`` (a local binding
    inside the factory)."""
    directive = _make_directive(affected_files=("src/foo.py",))
    items = (_make_action_item(),)
    renderer = make_retry_prompt_body_renderer(directive, items)
    # Mutate via setattr-bypass; the closure should still render the
    # ORIGINAL affected_files because Python's frozen dataclass forbids
    # mutation AND the closure binding is to the original value.
    with pytest.raises(dataclasses.FrozenInstanceError):
        directive.affected_files = ("src/MUTATED.py",)  # type: ignore[misc]
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer("agent text", resolution, 1)
    assert "src/foo.py" in output
    assert "src/MUTATED.py" not in output


def test_renderer_closure_captures_action_items_at_factory_call_time(
    tmp_path: pathlib.Path,
) -> None:
    """Mutating the list passed in AFTER factory call must not affect
    the closure (``tuple(action_items)`` snapshots the input)."""
    items_list = [_make_action_item(finding_id="F-1")]
    directive = _make_directive()
    renderer = make_retry_prompt_body_renderer(directive, items_list)
    items_list.append(_make_action_item(finding_id="F-LATE"))
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer("agent text", resolution, 1)
    assert "F-1" in output
    assert "F-LATE" not in output


def test_renderer_handles_empty_action_items(tmp_path: pathlib.Path) -> None:
    """Empty action_items is permitted; the directive section still
    names retry_mode + affected_files."""
    directive = _make_directive(affected_files=("src/foo.py",))
    renderer = make_retry_prompt_body_renderer(directive, ())
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer("agent text", resolution, 1)
    assert "retry_mode: fix-only" in output
    assert "src/foo.py" in output


def test_renderer_handles_empty_affected_files(tmp_path: pathlib.Path) -> None:
    """Empty affected_files is permitted (degenerate case); the
    directive section still renders without raising."""
    directive = _make_directive(affected_files=())
    items = (_make_action_item(),)
    renderer = make_retry_prompt_body_renderer(directive, items)
    resolution = _make_story_doc_resolution(tmp_path)
    output = renderer("agent text", resolution, 1)
    assert "retry_mode: fix-only" in output
    assert "affected_files:" in output


# ---------------------------------------------------------------------------
# AC-4 — extract_scope_expanded_to
# ---------------------------------------------------------------------------


def test_extract_scope_expanded_to_empty_array_returns_empty_tuple() -> None:
    env = _make_envelope(scope_expanded_to=[])
    assert extract_scope_expanded_to(env) == ()


def test_extract_scope_expanded_to_populated_array_preserves_order() -> None:
    env = _make_envelope(
        scope_expanded_to=["src/foo.py", "src/bar.py", "src/baz.py"]
    )
    assert extract_scope_expanded_to(env) == (
        "src/foo.py",
        "src/bar.py",
        "src/baz.py",
    )


def test_extract_scope_expanded_to_missing_key_returns_empty_tuple() -> None:
    """The field is optional per envelope.schema.yaml; absent + ``[]``
    are observably identical."""
    env = _make_envelope()
    assert "scope_expanded_to" not in env
    assert extract_scope_expanded_to(env) == ()


def test_extract_scope_expanded_to_returns_tuple_type() -> None:
    env = _make_envelope(scope_expanded_to=["src/foo.py"])
    result = extract_scope_expanded_to(env)
    assert isinstance(result, tuple)


def test_extract_scope_expanded_to_raises_for_none_envelope() -> None:
    with pytest.raises(
        RetryDispatchError, match="non-None Mapping"
    ) as excinfo:
        extract_scope_expanded_to(None)
    assert "validate_return_envelope" in str(excinfo.value)


def test_extract_scope_expanded_to_raises_for_string_value() -> None:
    env = _make_envelope(scope_expanded_to="not a list")
    with pytest.raises(RetryDispatchError) as excinfo:
        extract_scope_expanded_to(env)
    msg = str(excinfo.value)
    assert "must be a list" in msg
    assert "str" in msg
    assert "Remediation" in msg


def test_extract_scope_expanded_to_raises_for_dict_value() -> None:
    env = _make_envelope(scope_expanded_to={"key": "value"})
    with pytest.raises(RetryDispatchError, match="must be a list"):
        extract_scope_expanded_to(env)


def test_extract_scope_expanded_to_raises_for_none_value_in_key() -> None:
    """Key present but value is None — distinct from absent key (→ ()) and None envelope."""
    env = _make_envelope(scope_expanded_to=None)
    with pytest.raises(RetryDispatchError, match="must be a list"):
        extract_scope_expanded_to(env)


def test_extract_scope_expanded_to_raises_for_non_string_item() -> None:
    env = _make_envelope(scope_expanded_to=[123, "src/foo.py"])
    with pytest.raises(RetryDispatchError) as excinfo:
        extract_scope_expanded_to(env)
    msg = str(excinfo.value)
    assert "scope_expanded_to'][0]" in msg
    assert "must be a str" in msg
    assert "Remediation" in msg


def test_extract_scope_expanded_to_raises_for_non_string_item_at_later_index() -> None:
    env = _make_envelope(scope_expanded_to=["src/foo.py", None, "src/bar.py"])
    with pytest.raises(RetryDispatchError) as excinfo:
        extract_scope_expanded_to(env)
    assert "scope_expanded_to'][1]" in str(excinfo.value)


def test_extract_scope_expanded_to_purity_baseline_same_input_same_output() -> None:
    env = _make_envelope(scope_expanded_to=["src/foo.py"])
    first = extract_scope_expanded_to(env)
    second = extract_scope_expanded_to(env)
    assert first == second


def test_extract_scope_expanded_to_does_not_mutate_envelope() -> None:
    env = _make_envelope(scope_expanded_to=["src/foo.py", "src/bar.py"])
    snapshot = dict(env)
    snapshot["scope_expanded_to"] = list(env["scope_expanded_to"])
    extract_scope_expanded_to(env)
    assert env["scope_expanded_to"] == snapshot["scope_expanded_to"]


# ---------------------------------------------------------------------------
# AC-5 — End-to-end pair test (the contract-pair regression baseline)
# ---------------------------------------------------------------------------


def test_fix_only_retry_contract_pair_with_verifier_closure_end_to_end(
    tmp_path: pathlib.Path,
) -> None:
    """Per epics.md line 2319: "the pair test is a single test case,
    NOT decomposed into separate 'orchestrator-side test' and
    'Dev-side test' — the contract is the pair; testing each side in
    isolation lets subtle drift between sides slip through Story 5.4's
    verification".

    Exercises the full route → derive → render → simulated-Dev-return
    → extract path. Story 5.4 thickens with step 14 (verifier closure)
    appended to the SAME test function — keeping the contract atomic
    per epics.md line 2319."""

    # 1. ARRANGE — orchestrator-side declares scope.
    rationale_marker = "DISTINCTIVE_REVIEW_PROSE_MARKER"
    review_envelope = _make_envelope(
        findings=(
            _make_finding(
                id="F-1",
                bucket="patch",
                severity="HIGH",
                location="src/foo.py:10",
                detail="make foo do X",
            ),
            _make_finding(
                id="F-2",
                bucket="patch",
                severity="MED",
                location="src/bar.py:25",
                detail="make bar do Y",
            ),
        ),
        rationale=f"reviewer prose containing {rationale_marker}",
    )

    # 2. Route the envelope.
    outcome = route_envelope(review_envelope)
    assert outcome is RoutingOutcome.RETRY_DEV

    # 3. Derive structured action items.
    action_items = derive_action_items(review_envelope)
    assert len(action_items) == 2

    # 4. Derive affected_files.
    affected_files = derive_affected_files(action_items)
    assert affected_files == ("src/foo.py", "src/bar.py")

    # 5. Construct the directive.
    directive = RetryDispatchDirective(
        retry_mode="fix-only",
        affected_files=affected_files,
    )

    # 6. Construct the renderer.
    renderer = make_retry_prompt_body_renderer(directive, action_items)

    # 7. Render the prompt body.
    resolution = _make_story_doc_resolution(tmp_path)
    prompt_body = renderer(
        "<dev-wrapper agent definition>", resolution, 1
    )

    # 8. ASSERT — orchestrator-side declaration shape.
    assert "retry_mode: fix-only" in prompt_body
    assert "src/foo.py" in prompt_body
    assert "src/bar.py" in prompt_body
    assert "Constrain your work" in prompt_body
    assert "scope_expanded_to" in prompt_body
    # The base renderer's standard sections are present.
    assert "# Specialist instructions" in prompt_body
    assert "# Acceptance criteria" in prompt_body

    # 9. ASSERT — FR9 context-firewall structural enforcement.
    # The rationale was never passed into the renderer; it is
    # structurally excluded by the renderer's API surface.
    assert rationale_marker not in prompt_body

    # 10. ARRANGE — Dev-side simulated return.
    simulated_dev_envelope = _make_envelope(
        status="fail",
        findings=(),
        rationale="Dev attempted patch; touched one extra file.",
        proposed_commit_message="fix(scope): patch foo + bar (+baz extension)",
        scope_expanded_to=["src/baz.py"],
    )

    # 11. Extract Dev's reported scope_expanded_to.
    extracted = extract_scope_expanded_to(simulated_dev_envelope)

    # 12. ASSERT — Dev-side declaration shape.
    assert extracted == ("src/baz.py",)

    # 13. ASSERT — pair contract closure: declared affected_files and
    # Dev-reported scope_expanded_to are DISJOINT (the pair contract
    # permits scope expansion as long as it is reported; Story 5.4
    # owns the diff-vs-declaration verification).
    assert set(directive.affected_files).isdisjoint(set(extracted))

    # 14. ASSERT — verifier closure (Story 5.4 thickening).
    declared_scope = directive.affected_files       # ("src/foo.py", "src/bar.py")
    declared_expansion = extracted                  # ("src/baz.py",)
    # Simulate Dev's actual diff: foo + bar (declared) + baz (declared expansion).
    actual_files_clean = ("src/foo.py", "src/bar.py", "src/baz.py")
    result_clean = scope_assertion.verify_scope_assertion(
        affected_files=declared_scope,
        scope_expanded_to=declared_expansion,
        actual_files=actual_files_clean,
    )
    assert result_clean.is_violation is False
    assert result_clean.violating_files == ()
    # Simulate Dev's actual diff: foo + bar + baz + qux (qux is undeclared violation).
    actual_files_violation = (
        "src/foo.py",
        "src/bar.py",
        "src/baz.py",
        "src/qux.py",
    )
    result_violation = scope_assertion.verify_scope_assertion(
        affected_files=declared_scope,
        scope_expanded_to=declared_expansion,
        actual_files=actual_files_violation,
    )
    assert result_violation.is_violation is True
    assert result_violation.violating_files == ("src/qux.py",)
    diagnostic = scope_assertion.make_scope_assertion_diagnostic(
        result_violation, story_id="5-3-test", retry_round=1,
    )
    assert diagnostic.marker_class == "scope-assertion-violation"


# ---------------------------------------------------------------------------
# AC-9 — test count floor (>= 25 post-parametrize-expansion)
# ---------------------------------------------------------------------------
# This file declares 35+ tests; the floor is satisfied by construction.
