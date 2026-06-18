"""Parser unit tests for the forward-pointer-drift library (Story 22.4).

Covers the two machine-checkable surfaces (annotation + conservative inline),
the deliberate non-matching of phase-level / soft prose (no false positives),
the pending-status gating, prefix-aware done resolution, and the loud-fail
sprint-status parse boundary.
"""

from __future__ import annotations

import pytest

from loud_fail_harness.forward_pointer_drift import (
    ForwardPointerDriftError,
    iter_carry_pointers,
    iter_done_story_keys,
    resolve_done_target,
    KNOWN_FLIPPED_STATUSES,
)


# --------------------------------------------------------------------------- #
# iter_done_story_keys                                                         #
# --------------------------------------------------------------------------- #


def test_iter_done_story_keys_filters_to_done_story_keys() -> None:
    text = (
        "development_status:\n"
        "  epic-18: done\n"
        "  18-3-concurrent-env: done\n"
        "  18-4-parallel-fixture: review\n"
        "  epic-18-retrospective: done\n"
        "  1-10a-pluggability: done\n"
    )
    assert iter_done_story_keys(text) == ["18-3-concurrent-env", "1-10a-pluggability"]


def test_iter_done_story_keys_raises_on_non_yaml() -> None:
    with pytest.raises(ForwardPointerDriftError) as exc:
        iter_done_story_keys("development_status:\n  - [unbalanced\n")
    assert exc.value.reason == "sprint-status-not-valid-yaml"


def test_iter_done_story_keys_raises_on_missing_development_status() -> None:
    with pytest.raises(ForwardPointerDriftError) as exc:
        iter_done_story_keys("other_key: 1\n")
    assert exc.value.reason == "development-status-missing"


def test_iter_done_story_keys_raises_on_null_development_status() -> None:
    # P7: `development_status:` key exists but is null — wrong to call it "missing"
    with pytest.raises(ForwardPointerDriftError) as exc:
        iter_done_story_keys("development_status:\n")
    assert exc.value.reason == "development-status-null"


def test_iter_done_story_keys_raises_on_non_scalar_status_value() -> None:
    # P8: a status value that is a mapping instead of a string
    text = "development_status:\n  18-3-x:\n    foo: bar\n"
    with pytest.raises(ForwardPointerDriftError) as exc:
        iter_done_story_keys(text)
    assert exc.value.reason == "non-scalar-status-value"


def test_iter_done_story_keys_raises_on_scalar_document() -> None:
    with pytest.raises(ForwardPointerDriftError) as exc:
        iter_done_story_keys("just a string")
    assert exc.value.reason == "sprint-status-not-a-mapping"


# --------------------------------------------------------------------------- #
# iter_carry_pointers — annotation surface                                     #
# --------------------------------------------------------------------------- #


def test_annotation_pending_is_parsed() -> None:
    line = "- foo <!-- forward-pointer: target=18-3-concurrent-env; status=pending -->"
    pointers = iter_carry_pointers(line)
    assert len(pointers) == 1
    assert pointers[0].target_key == "18-3-concurrent-env"
    assert pointers[0].source_kind == "annotation"
    assert pointers[0].status == "pending"


def test_annotation_target_is_lowercased() -> None:
    # P1: mixed-case target must be lowercased so resolve_done_target hits the done key
    line = "<!-- forward-pointer: target=18-3-Concurrent-Env; status=pending -->"
    pointers = iter_carry_pointers(line)
    assert pointers[0].target_key == "18-3-concurrent-env"


def test_annotation_status_whitespace_is_tolerated() -> None:
    # P4: `status= pending` (space after `=`) must not silently drop the annotation
    line = "<!-- forward-pointer: target=18-3-x; status= pending -->"
    pointers = iter_carry_pointers(line)
    assert len(pointers) == 1
    assert pointers[0].status == "pending"


def test_annotation_unknown_status_raises_loud_fail() -> None:
    # P5: typo'd status must be a loud-fail error, not a silent skip
    line = "<!-- forward-pointer: target=18-3-x; status=pendnig -->"
    with pytest.raises(ForwardPointerDriftError) as exc:
        iter_carry_pointers(line)
    assert exc.value.reason == "unknown-annotation-status"


def test_annotation_malformed_target_raises_loud_fail() -> None:
    # P6: target that does not look like a story-key must raise, not silently pass
    line = "<!-- forward-pointer: target=http://example.com; status=pending -->"
    with pytest.raises(ForwardPointerDriftError) as exc:
        iter_carry_pointers(line)
    assert exc.value.reason == "annotation-target-malformed"


def test_annotation_landed_status_is_skipped() -> None:
    # A flipped pointer (status in KNOWN_FLIPPED_STATUSES) is not drift — not parsed.
    line = "<!-- forward-pointer: target=18-3-concurrent-env; status=landed -->"
    assert iter_carry_pointers(line) == []


def test_annotation_all_known_flipped_statuses_are_skipped() -> None:
    for flipped in KNOWN_FLIPPED_STATUSES:
        line = f"<!-- forward-pointer: target=18-3-x; status={flipped} -->"
        assert iter_carry_pointers(line) == [], f"status={flipped!r} should be skipped"


def test_annotation_status_is_case_insensitive() -> None:
    line = "<!-- Forward-Pointer: target=14-3-locking; status=Carries -->"
    pointers = iter_carry_pointers(line)
    assert len(pointers) == 1
    assert pointers[0].status == "carries"


# --------------------------------------------------------------------------- #
# iter_carry_pointers — inline carry-binding surface                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "phrase",
    [
        "deferred to 18-3-concurrent-env",
        "carries to 18-3-concurrent-env",
        "carry to 18-3-concurrent-env",
        "lands in 18-3-concurrent-env",
        "resolved by 18-3-concurrent-env",
        "trigger-armed for 18-3-concurrent-env",
        "deferred to Story 18-3-concurrent-env",
    ],
)
def test_inline_binding_verbs_match(phrase: str) -> None:
    pointers = iter_carry_pointers(f"- some carry {phrase} per the retro")
    assert len(pointers) == 1
    assert pointers[0].target_key == "18-3-concurrent-env"
    assert pointers[0].source_kind == "inline"
    assert pointers[0].status == "carries"


def test_inline_accepts_prefix_target_token() -> None:
    pointers = iter_carry_pointers("- deferred to 18-3 per the retro")
    assert pointers[0].target_key == "18-3"


def test_multiple_inline_bindings_on_same_line_all_captured() -> None:
    # P2: finditer must emit ALL inline bindings on a line, not just the first
    line = "- deferred to 14-3-locking and also carries to 18-3-concurrent-env"
    pointers = [p for p in iter_carry_pointers(line) if p.source_kind == "inline"]
    targets = {p.target_key for p in pointers}
    assert targets == {"14-3-locking", "18-3-concurrent-env"}


def test_inline_binding_word_boundary_prevents_undeferred_match() -> None:
    # P3: `\b` before phrase prevents "undeferred to" from matching "deferred to"
    assert iter_carry_pointers("undeferred to 18-3-concurrent-env") == []


@pytest.mark.parametrize(
    "soft_line",
    [
        "- carries to Phase 3 unchanged; trigger remains armed",
        "- Story 14.3 is the natural resolution point for this",
        "- Epic 18 Story 18.2 will exercise them when building the detector",
        "- route to triage as a standalone docs-and-test maintenance item",
        "- the natural resolution point is a future consistency pass",
    ],
)
def test_phase_level_and_soft_prose_do_not_match(soft_line: str) -> None:
    # The whole anti-false-positive point: phase pointers + soft suggestions
    # carry no machine-checkable story-key binding, so they must NOT match.
    assert iter_carry_pointers(soft_line) == []


def test_annotation_and_inline_on_same_line_both_emit() -> None:
    line = (
        "- deferred to 14-3-locking "
        "<!-- forward-pointer: target=18-3-x; status=pending -->"
    )
    pointers = iter_carry_pointers(line)
    assert {p.source_kind for p in pointers} == {"inline", "annotation"}


def test_line_numbers_are_one_indexed() -> None:
    text = "line one\n- deferred to 18-3-concurrent-env\nline three\n"
    pointers = iter_carry_pointers(text)
    assert pointers[0].line_number == 2


# --------------------------------------------------------------------------- #
# resolve_done_target — prefix-aware resolution                                #
# --------------------------------------------------------------------------- #


def test_resolve_exact_match() -> None:
    done = frozenset({"18-3-concurrent-env"})
    assert resolve_done_target("18-3-concurrent-env", done) == "18-3-concurrent-env"


def test_resolve_prefix_match() -> None:
    done = frozenset({"18-3-concurrent-env-provisioning-discipline"})
    assert (
        resolve_done_target("18-3", done)
        == "18-3-concurrent-env-provisioning-discipline"
    )


def test_resolve_prefix_respects_hyphen_boundary() -> None:
    # `1-1` must NOT bind `1-10a-…` — the hyphen boundary prevents it.
    done = frozenset({"1-10a-pluggability"})
    assert resolve_done_target("1-1", done) is None


def test_resolve_returns_none_when_absent() -> None:
    assert resolve_done_target("99-9", frozenset({"18-3-x"})) is None
