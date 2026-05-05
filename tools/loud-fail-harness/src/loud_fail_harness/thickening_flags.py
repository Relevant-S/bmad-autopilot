"""Walking-skeleton thickening-status flag namespace (Story 2.11 AC-2).

Four boolean-returning functions naming the four thickening features
that downstream Epics flip in place as their thickenings land.
Post-Story-6.1 substrate state: FOUR flags return ``True`` — the
in-place-flip cohort closes (:func:`is_full_review_present` flipped at
Story 3.4 — the first production in-place flip; :func:`is_full_qa_present`
flipped at Story 4.13 — the second production in-place flip closing
Epic 4; :func:`is_retry_present` flipped at Story 5.9 — the third
production in-place flip closing Epic 5; :func:`is_loud_fail_block_present`
flipped at Story 6.1 — the FOURTH and FINAL production in-place flip
opening Epic 6, distinguished from the three priors by being a
*structural derivation* rather than a literal ``return True`` per
AC-2's drift-prevention contract-pair pattern). The Story 3.4 + Story
4.13 + Story 5.9 + Story 6.1 relaxations confirm the in-place-flip
pattern's structural posture: each Epic flips its corresponding flag
in this same module (same module identity, same function signatures),
only the function bodies thicken:

    * Epic 3 (3-layer adversarial review) flips :func:`is_full_review_present`.
    * Epic 4 (full QA specialist with Tier-2 + Tier-3 evidence + plan
      drift detection) flips :func:`is_full_qa_present`.
    * Epic 5 (whole-story retry budget + bucket-driven action item
      derivation) flips :func:`is_retry_present`.
    * Epic 6 (loud-fail block + per-specialist × per-retry cost
      breakdown + actionable how-to-enable pointers) flips
      :func:`is_loud_fail_block_present`.

The verbatim epic AC at ``epics.md`` Story 2.11 lines 1521-1522 mandates
this in-place flip pattern: "the assembler renders the header text by
enumerating which thickening features are still missing" + "each
downstream epic flips its corresponding flag when its thickening
lands". The flag identifiers and their Epic-2-era ``False`` returns are
mandated verbatim by the same epic AC.

Why functions, not constants? Forward-compatibility with substrate-state
probes that depend on filesystem state at orchestrator runtime. The
Epic-2 implementation uses static ``False`` literals because all four
flags are unconditionally False at Epic 2 substrate state, but the
function shape preserves the option for downstream epics to add
substrate-state probes (e.g. ``is_full_review_present()`` could probe
the existence of a review-layer-aggregator artifact, or
``is_loud_fail_block_present()`` could probe the assembler's own
section-emission registry) without breaking the call sites in
:mod:`loud_fail_harness.bundle_assembly`. This mirrors the
runtime-load-not-compile-time-bake posture established by Story 2.6's
:func:`loud_fail_harness.specialist_dispatch.load_marker_class_registry`.
Story 6.1 IS the production landing of this forward-compat posture —
:func:`is_loud_fail_block_present` reads the assembler's source via
:func:`inspect.getsource` to derive its return value structurally.

The marker-emission rule the assembler (Story 2.11) implements is
predicated on :func:`is_loud_fail_block_present` per the verbatim epic
AC at lines 1527-1528: the ``walking-skeleton-bundle`` marker emits if
and only if :func:`is_loud_fail_block_present` returns ``False``. The
rule is structural, NOT era-based — the assembler does not check the
current Epic; it consults this module. Epic 6 flips the flag in place,
which inverts emission without any assembler edit.

Architectural placement: substrate library at
``tools/loud-fail-harness/src/loud_fail_harness/`` (parallel to
:mod:`loud_fail_harness.specialist_dispatch` +
:mod:`loud_fail_harness.run_state`). Outside the FR62
:mod:`loud_fail_harness.pluggability_gate` scope by construction
(``agents/*.md`` only). Substrate-shared library, NOT a sixth substrate
component beyond ADR-003's enumerated five.
"""

from __future__ import annotations

import inspect

from loud_fail_harness.exceptions import ContractViolation


#: The name of the loud-fail-block sub-renderer Story 6.1 wires into
#: :func:`loud_fail_harness.bundle_assembly.assemble_bundle`. Used by
#: :func:`is_loud_fail_block_present`'s structural-derivation path to
#: assert the assembler's source references the sub-renderer.
_LOUD_FAIL_BLOCK_RENDERER_NAME: str = "_render_loud_fail_block"


class LoudFailBlockWireUpBroken(ContractViolation):
    """Raised by :func:`is_loud_fail_block_present` when the assembler's
    source does NOT reference the loud-fail-block sub-renderer.

    Pattern 5 named-invariant diagnostic per the Story 6.1 AC-2
    drift-prevention contract-pair contract. The computed flag and the
    assembler's render path are a contract pair (Story 5.3 precedent +
    Story 2.2 atomic-write-helper precedent) — when the contract is
    broken, the failure mode is loud, NOT silently-``False``. Silent
    ``False`` would be a structural drift that subsequent Epic-6 stories
    (6.2 actionable pointers, 6.3 coverage audit, 6.7 timeout/hook-failed
    wiring, 6.9 bundle-assembly-failed marker) would build atop without
    notice.

    Attributes:
        renderer_name: The sub-renderer identifier the flag expected to
            find in the assembler's source.
        assembler_qualname: The qualified name of the assembler function
            whose source was inspected.
    """

    def __init__(
        self,
        *,
        renderer_name: str,
        assembler_qualname: str,
    ) -> None:
        self.renderer_name = renderer_name
        self.assembler_qualname = assembler_qualname
        super().__init__(
            f"LoudFailBlockWireUpBroken: assembler {assembler_qualname!r} "
            f"source does not reference {renderer_name!r}; "
            "is_loud_fail_block_present() refuses to silently return False "
            "(Story 6.1 AC-2 contract-pair invariant — Pattern 5 loud-fail "
            "doctrine: the flag and the assembler's render path are a "
            "contract pair per Story 5.3 / Story 2.2 precedent). "
            "Remediation: re-wire the loud-fail block sub-renderer into "
            "the assembler's body, OR remove the call site for "
            "is_loud_fail_block_present."
        )


def is_full_review_present() -> bool:
    """``True`` — Epic 3's three-layer adversarial review pass HAS LANDED.

    Post-Story-3.4 substrate state: returns ``True``. Epic 3's Stories
    3.1 (three-layer parallel-pass wiring) + 3.2 (finding-taxonomy
    passthrough + bucket-driven retry-router prep) + 3.3 (failed_layers
    graceful-degradation three-channel atomic emission) + 3.4 (PR-bundle
    review-section bucket × severity rendering + this in-place flip)
    collectively delivered the full three-layer adversarial review
    surface; the flag flips per the in-place-flip pattern Story 2.11
    AC-2 ratified (epics.md lines 1521-1522: "each downstream epic flips
    its corresponding flag when its thickening lands"). The flip
    cascades automatically through ``_render_walking_skeleton_header``
    in :mod:`loud_fail_harness.bundle_assembly` — the
    "Single-layer review (Epic 3 thickens to 3-layer adversarial pass)"
    sentence is now omitted from the dynamic header body.
    """
    return True


def is_full_qa_present() -> bool:
    """``True`` — Epic 4's full QA specialist surface HAS LANDED.

    Post-Story-4.13 substrate state: returns ``True``. Epic 4's Stories
    4.1 (plan creation + persistence) + 4.2 (AC-hash drift detection +
    plan_status reset) + 4.3 (full env provisioning lifecycle —
    orchestrator-owned) + 4.4 (Playwright MCP driver for ``web``) + 4.5
    (HTTP driver for ``api``) + 4.6 (plan-driven AC iteration with
    smoke-first ordering) + 4.7 (AC-assertion-evidence triple structural
    enforcement) + 4.8 (three-tier evidence hierarchy + Tier-3
    not-configured marker) + 4.9 (three exploratory heuristics with
    verification-mode discriminator) + 4.10 (two escalation contracts —
    verification-fail + env-setup-fail) + 4.11 (plan-persistence-
    compromise visibility note) + 4.12 (evidence persistence + size
    budget + sanitization) + 4.13 (this wrapper-thickening flip)
    collectively delivered the full FR16-FR25 QA surface; the flag flips
    per the in-place-flip pattern Story 2.11 AC-2 ratified — epics.md
    lines 1521-1522: "each downstream epic flips its corresponding flag
    when its thickening lands". The flip cascades automatically through
    ``_render_walking_skeleton_header`` in
    :mod:`loud_fail_harness.bundle_assembly` — the "Tier-1 evidence
    only (Epic 4 thickens to Tier-2 + Tier-3-where-configured)."
    sentence is now omitted from the dynamic header body.
    """
    return True


def is_retry_present() -> bool:
    """``True`` — Epic 5's whole-story retry + escalation surface HAS LANDED.

    Post-Story-5.9 substrate state: returns ``True``. Epic 5's Stories
    5.1 (whole-story retry budget configuration + enforcement) + 5.2
    (bucket-driven action-item derivation + retry routing) + 5.3 (Dev
    fix-only retry mechanism + ``retry_mode`` + ``affected_files`` scope
    expanded to contract pair) + 5.4 (scope-assertion verification +
    violation loud-fail) + 5.5 (externalized retry history + run-state
    references) + 5.6 (retry-budget-exhaustion non-advance + state
    preservation marker) + 5.7 (``deferred-work.md`` format spec audit
    + integration + research-blocker spike bounded with named fallback)
    + 5.8 (escalation-bundle assembly mechanism consuming Epic-4
    contracts + Stories 5.6-5.7) + 5.9 (this epic-close in-place flip)
    collectively delivered the full FR12-FR15 + FR59 retry + escalation
    surface; the flag flips per the in-place-flip pattern Story 2.11
    AC-2 ratified: "each downstream epic flips its corresponding flag
    when its thickening lands". This is
    the third production in-place flip, mirroring Story 3.4
    (:func:`is_full_review_present`) and Story 4.13
    (:func:`is_full_qa_present`) verbatim. The flip cascades
    automatically through ``_render_walking_skeleton_header`` in
    :mod:`loud_fail_harness.bundle_assembly` — the "No retry (Epic 5
    thickens with whole-story retry budget + bucket-driven action item
    derivation)." sentence is now omitted from the dynamic header body.
    """
    return True


def is_loud_fail_block_present() -> bool:
    """``True`` once Epic 6's dedicated top-of-bundle loud-fail block
    section has landed in the assembler.

    Post-Story-6.1 substrate state: returns ``True`` via *structural
    derivation*. The function imports
    :mod:`loud_fail_harness.bundle_assembly` lazily (avoids import-cycle
    with the assembler), reads
    ``inspect.getsource(bundle_assembly.assemble_bundle)``, and returns
    ``True`` iff the assembler's source references the
    ``_render_loud_fail_block`` sub-renderer. There is no internal
    stored boolean, no hardcoded ``return True``, no module-level
    constant — the return value is derived from the assembler's source
    at every call.

    This is the drift-prevention contract-pair pattern Story 5.3
    ratified for ``affected_files / scope_expanded_to`` (where the
    scope assertion is structurally verified, not stored as a separate
    flag) and Story 2.2 ratified for atomic-write ordering (where the
    write order is enforced by the helper's signature, not by external
    orchestration). The flag and the assembler's render path form a
    contract pair: the function literally returns ``True`` if and only
    if the bundle assembler emits the loud-fail block; there is no path
    that returns ``True`` while the block is missing or ``False`` while
    the block is present.

    Loud-fail discipline (Pattern 5): if the assembler exists but the
    sub-renderer is not wired into it, the function raises
    :exc:`LoudFailBlockWireUpBroken` — a named-invariant
    :exc:`ContractViolation`-class diagnostic — rather than silently
    returning ``False``. Silent ``False`` would be a structural drift
    that subsequent Epic-6 stories (6.2 actionable pointers, 6.3
    coverage audit, 6.7 timeout/hook-failed wiring, 6.9 bundle-
    assembly-failed marker) would build atop without notice.

    The flag's return value is derived from
    :func:`inspect.getsource` ``(bundle_assembly.assemble_bundle)``;
    there is no path that returns ``True`` while the block is missing
    or ``False`` while the block is present — the function and the
    assembler's render path are a contract pair per Story 5.3's
    ``affected_files / scope_expanded_to`` precedent and Story 2.2's
    atomic-write-helper precedent.
    """
    # Lazy import: avoid a module-import-time cycle between
    # ``thickening_flags`` and ``bundle_assembly`` (the assembler
    # imports this module at the top level).
    from loud_fail_harness import bundle_assembly

    try:
        source = inspect.getsource(bundle_assembly.assemble_bundle)
    except (OSError, TypeError) as exc:
        raise LoudFailBlockWireUpBroken(
            renderer_name=_LOUD_FAIL_BLOCK_RENDERER_NAME,
            assembler_qualname=bundle_assembly.assemble_bundle.__qualname__,
        ) from exc
    if _LOUD_FAIL_BLOCK_RENDERER_NAME in source:
        return True
    raise LoudFailBlockWireUpBroken(
        renderer_name=_LOUD_FAIL_BLOCK_RENDERER_NAME,
        assembler_qualname=bundle_assembly.assemble_bundle.__qualname__,
    )
