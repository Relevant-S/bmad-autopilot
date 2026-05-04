"""Contract-coverage tests for Story 2.11's thickening_flags substrate module.

This docstring IS the contract-coverage matrix per AC-2.

AC-2 — four-flag namespace (post-Story-5.9 substrate state per AC-6):
    [x] post-5.9 substrate state: 3 flags True + 1 flag False      → test_thickening_flags_at_epic_5_substrate_state
    [x] module docstring documents the in-place-flip pattern       → test_thickening_flags_module_documents_in_place_flip_pattern
    [x] each function takes zero args and returns bool             → test_thickening_flags_signatures_take_zero_args_return_bool
    [x] flags are functions, not constants                         → test_thickening_flags_are_functions_not_constants

Story 3.4 AC-7: the all-False-at-Epic-2 baseline was RELAXED IN PLACE
when Story 3.4 flipped ``is_full_review_present`` to ``True`` per the
Story 2.11 in-place-flip pattern; the test that asserted the all-False
baseline was renamed to reflect the post-3.4 substrate state.

Story 5.9 AC-1: the post-4.13 substrate-state baseline is RELAXED IN
PLACE per the same Story 2.11 in-place-flip pattern. Story 5.9 flipped
``is_retry_present`` to ``True`` (the third production in-place flip
closing Epic 5 after Stories 5.1-5.8 collectively delivered the full
FR12-FR15 + FR59 retry + escalation surface — whole-story retry budget
+ bucket-driven action-item derivation + Dev fix-only retry contract
pair + scope-assertion verification + externalized retry history +
retry-budget-exhaustion non-advance + ``deferred-work.md`` format spec
+ escalation-bundle assembly); the test asserting the post-4.13
substrate state is renamed to
``test_thickening_flags_at_epic_5_substrate_state`` and its
assertion-set updated to reflect THREE flags returning ``True``
(``is_full_review_present`` + ``is_full_qa_present`` +
``is_retry_present``) and ONE flag continuing to return ``False``
(``is_loud_fail_block_present`` — Epic 6 owns). The other three tests
in this module continue to pass unchanged at the post-5.9 substrate
state per the Story 3.4 / 4.13 precedent.
"""

from __future__ import annotations

import inspect

from loud_fail_harness import thickening_flags


def test_thickening_flags_at_epic_5_substrate_state() -> None:
    """Post-Story-5.9 substrate state: ``is_full_review_present`` (Story
    3.4 flipped) + ``is_full_qa_present`` (Story 4.13 flipped — closing
    Epic 4) + ``is_retry_present`` (Story 5.9 flipped — closing Epic 5
    after Stories 5.1-5.8 collectively delivered the full FR12-FR15 +
    FR59 retry + escalation surface) return ``True``;
    ``is_loud_fail_block_present`` (Epic 6 owns) continues to return
    ``False``. This is the third production in-place flip per the
    Story 2.11 / 3.4 / 4.13 in-place-flip-pattern precedent.
    """
    assert thickening_flags.is_full_review_present() is True
    assert thickening_flags.is_full_qa_present() is True
    assert thickening_flags.is_retry_present() is True
    assert thickening_flags.is_loud_fail_block_present() is False


def test_thickening_flags_module_documents_in_place_flip_pattern() -> None:
    doc = thickening_flags.__doc__ or ""
    for epic in ("Epic 3", "Epic 4", "Epic 5", "Epic 6"):
        assert epic in doc, f"thickening_flags module docstring must reference {epic}"
    for fn_name in (
        "is_full_review_present",
        "is_full_qa_present",
        "is_retry_present",
        "is_loud_fail_block_present",
    ):
        assert fn_name in doc, f"docstring must name {fn_name}"
    assert "flip in place" in doc or "flips the corresponding flag" in doc, (
        "docstring must document the in-place-flip pattern"
    )


def test_thickening_flags_signatures_take_zero_args_return_bool() -> None:
    for fn_name in (
        "is_full_review_present",
        "is_full_qa_present",
        "is_retry_present",
        "is_loud_fail_block_present",
    ):
        fn = getattr(thickening_flags, fn_name)
        sig = inspect.signature(fn)
        assert len(sig.parameters) == 0, (
            f"{fn_name} must take zero positional arguments; got {sig}"
        )
        # `from __future__ import annotations` renders annotations as strings;
        # the canonical surface MUST be `bool` (NOT `Literal[False]` — Epic 3+
        # thickening must be permitted to return True).
        annotations = inspect.get_annotations(fn, eval_str=True)
        assert annotations.get("return") is bool, (
            f"{fn_name} must annotate `-> bool` (not Literal[False]); "
            f"got {annotations.get('return')!r}"
        )


def test_thickening_flags_are_functions_not_constants() -> None:
    for fn_name in (
        "is_full_review_present",
        "is_full_qa_present",
        "is_retry_present",
        "is_loud_fail_block_present",
    ):
        attr = getattr(thickening_flags, fn_name)
        assert callable(attr), f"{fn_name} must be a function (forward-compat with substrate probes)"
