"""Contract-coverage tests for Story 2.11's thickening_flags substrate module.

This docstring IS the contract-coverage matrix per AC-2.

AC-2 — four-flag namespace at Epic 2 substrate state:
    [x] all four flags return False                                → test_thickening_flags_all_return_false_at_epic_2_substrate_state
    [x] module docstring documents the in-place-flip pattern       → test_thickening_flags_module_documents_in_place_flip_pattern
    [x] each function takes zero args and returns bool             → test_thickening_flags_signatures_take_zero_args_return_bool
    [x] flags are functions, not constants                         → test_thickening_flags_are_functions_not_constants
"""

from __future__ import annotations

import inspect

from loud_fail_harness import thickening_flags


def test_thickening_flags_all_return_false_at_epic_2_substrate_state() -> None:
    assert thickening_flags.is_full_review_present() is False
    assert thickening_flags.is_full_qa_present() is False
    assert thickening_flags.is_retry_present() is False
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
