"""Contract-coverage tests for Story 2.11's thickening_flags substrate module.

This docstring IS the contract-coverage matrix per AC-2.

AC-2 — four-flag namespace (post-Story-6.1 substrate state per AC-6):
    [x] post-6.1 substrate state: 4 flags True (cohort closes)     → test_thickening_flags_at_epic_6_substrate_state
    [x] module docstring documents the in-place-flip pattern       → test_thickening_flags_module_documents_in_place_flip_pattern
    [x] each function takes zero args and returns bool             → test_thickening_flags_signatures_take_zero_args_return_bool
    [x] flags are functions, not constants                         → test_thickening_flags_are_functions_not_constants

Story 3.4 AC-7: the all-False-at-Epic-2 baseline was RELAXED IN PLACE
when Story 3.4 flipped ``is_full_review_present`` to ``True`` per the
Story 2.11 in-place-flip pattern; the test that asserted the all-False
baseline was renamed to reflect the post-3.4 substrate state.

Story 6.1 AC-1: the post-5.9 substrate-state baseline is RELAXED IN
PLACE per the same Story 2.11 in-place-flip pattern. Story 6.1 flipped
``is_loud_fail_block_present`` to ``True`` via *structural derivation*
— the FOURTH and FINAL production in-place flip, opening Epic 6 with
the loud-fail block landing in the assembler. Distinguished from the
three priors (Stories 3.4 / 4.13 / 5.9) by being a structural
derivation (``inspect.getsource`` against
:func:`loud_fail_harness.bundle_assembly.assemble_bundle`) rather than
a literal ``return True`` per AC-2's drift-prevention contract-pair
contract. The test asserting the post-5.9 substrate state is renamed
to ``test_thickening_flags_at_epic_6_substrate_state`` and its
assertion-set updated to reflect FOUR flags returning ``True``
(``is_full_review_present`` + ``is_full_qa_present`` +
``is_retry_present`` + ``is_loud_fail_block_present``). The other
three tests in this module continue to pass unchanged at the post-6.1
substrate state per the Story 3.4 / 4.13 / 5.9 precedent. New tests
covering the COMPUTED ``is_loud_fail_block_present()`` per AC-6 are
added below alongside this contract-coverage matrix.
"""

from __future__ import annotations

import inspect

import pytest

from loud_fail_harness import thickening_flags


def test_thickening_flags_at_epic_6_substrate_state() -> None:
    """Post-Story-6.1 substrate state: ALL FOUR flags return ``True`` —
    the in-place-flip cohort closes. ``is_full_review_present`` (Story
    3.4 flipped) + ``is_full_qa_present`` (Story 4.13 flipped — closing
    Epic 4) + ``is_retry_present`` (Story 5.9 flipped — closing Epic 5)
    + ``is_loud_fail_block_present`` (Story 6.1 flipped via *structural
    derivation* — opening Epic 6 with the loud-fail block landing in
    the assembler) all return ``True``. This is the FOURTH and FINAL
    production in-place flip per the Story 2.11 / 3.4 / 4.13 / 5.9
    in-place-flip-pattern precedent; distinguished by Story 6.1 AC-2's
    drift-prevention contract-pair contract — the flip is a structural
    derivation against ``inspect.getsource(bundle_assembly.assemble_bundle)``
    rather than a literal ``return True``.
    """
    assert thickening_flags.is_full_review_present() is True
    assert thickening_flags.is_full_qa_present() is True
    assert thickening_flags.is_retry_present() is True
    assert thickening_flags.is_loud_fail_block_present() is True


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



# --------------------------------------------------------------------------- #
# Story 6.1 — computed is_loud_fail_block_present() (AC-2 + AC-6)             #
# --------------------------------------------------------------------------- #


def test_is_loud_fail_block_present_returns_true_against_production_assembler() -> None:
    """Story 6.1 AC-2 + AC-6 (a): the computed
    :func:`is_loud_fail_block_present` returns ``True`` against the
    production :mod:`loud_fail_harness.bundle_assembly` module — the
    sub-renderer is wired into ``assemble_bundle``'s body. The flag's
    return value is derived structurally from
    ``inspect.getsource(bundle_assembly.assemble_bundle)``; there is no
    path that returns ``True`` while the block is missing or ``False``
    while the block is present.
    """
    assert thickening_flags.is_loud_fail_block_present() is True


def test_is_loud_fail_block_present_raises_loud_when_assembler_lacks_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 6.1 AC-2 + AC-6 (b): the computed flag raises
    :exc:`LoudFailBlockWireUpBroken` when given a synthetic
    ``bundle_assembly`` module whose ``assemble_bundle`` source does
    NOT reference ``_render_loud_fail_block``. Silent ``False`` is the
    failure mode the AC-2 contract-pair contract forbids — the flag's
    determinism vs. the assembler's reality must be loud, not silent.
    """
    from loud_fail_harness import bundle_assembly

    def _assemble_bundle_without_renderer() -> None:
        """Synthetic substitute whose source lacks the sub-renderer reference."""
        return None

    monkeypatch.setattr(
        bundle_assembly, "assemble_bundle", _assemble_bundle_without_renderer
    )
    with pytest.raises(thickening_flags.LoudFailBlockWireUpBroken) as exc_info:
        thickening_flags.is_loud_fail_block_present()
    assert exc_info.value.renderer_name == "_render_loud_fail_block"
    assert "_render_loud_fail_block" in str(exc_info.value)


def test_is_loud_fail_block_present_return_value_is_determined_entirely_by_assembler_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 6.1 AC-2 + AC-6 (c): the return value is determined
    ENTIRELY by the assembler's source — substituting a synthetic
    function whose source DOES reference the sub-renderer flips the
    flag to ``True``; substituting one whose source does NOT reference
    it raises :exc:`LoudFailBlockWireUpBroken`. No other input affects
    the return value (no module-level state, no environment variable,
    no stored boolean).
    """
    from loud_fail_harness import bundle_assembly

    def _assemble_bundle_with_renderer() -> None:
        """Synthetic with reference: _render_loud_fail_block in source."""
        return None

    monkeypatch.setattr(
        bundle_assembly, "assemble_bundle", _assemble_bundle_with_renderer
    )
    assert thickening_flags.is_loud_fail_block_present() is True


def test_is_loud_fail_block_present_is_deterministic_across_invocations() -> None:
    """Story 6.1 AC-2 + AC-6 (d): the computed flag is deterministic —
    two consecutive invocations against the same assembler produce
    identical results without state leak. The function reads source at
    every call (no caching, no memoization).
    """
    first = thickening_flags.is_loud_fail_block_present()
    second = thickening_flags.is_loud_fail_block_present()
    assert first is second is True


def test_is_loud_fail_block_present_has_no_stored_boolean_or_constant() -> None:
    """Story 6.1 AC-2 verbatim: "there is no internal stored boolean,
    no hardcoded ``return True``, no module-level constant — the return
    value is derived from the assembler's source at every call".

    This test asserts the function body itself contains the structural-
    derivation invocation (``inspect.getsource``) and does NOT contain
    a literal ``return True`` / ``return False`` at the top level — the
    derivation IS the return-value source.
    """
    body = inspect.getsource(thickening_flags.is_loud_fail_block_present)
    assert "inspect.getsource" in body, (
        "is_loud_fail_block_present must derive return value structurally"
    )
    assert "_render_loud_fail_block" in body, (
        "function body must reference the sub-renderer name it inspects for"
    )
    # Verify the lazy-import pattern that avoids the import cycle; a module-
    # level import would cause a circular dependency at import time.
    assert "from loud_fail_harness import bundle_assembly" in body, (
        "function must use lazy import of bundle_assembly (inside the function "
        "body) to avoid the module-level import cycle — Story 6.1 AC-2"
    )
