"""Walking-skeleton thickening-status flag namespace (Story 2.11 AC-2).

Four boolean-returning functions naming the four thickening features the
Epic-2 substrate intentionally omits. At Epic 2 substrate state every
function returns ``False`` unconditionally; downstream epics flip in
place — each Epic flips the corresponding flag in this same module
(same module identity, same function signatures), only the function
bodies thicken:

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


def is_full_review_present() -> bool:
    """``True`` once Epic 3's three-layer adversarial review pass lands.

    Epic 2 substrate state: returns ``False`` unconditionally — the
    Epic-2-era Review-BMAD wrapper (Story 2.9) ships a single-layer
    Acceptance Auditor only. Epic 3's Story 3.1 lands the parallel
    Blind Hunter + Edge Case Hunter + Acceptance Auditor wiring, at
    which point this function flips in place.
    """
    return False


def is_full_qa_present() -> bool:
    """``True`` once Epic 4's full QA specialist (Tier-2 + Tier-3
    evidence, behavioral plan, plan-drift detection) lands.

    Epic 2 substrate state: returns ``False`` unconditionally — the
    Epic-2-era QA wrapper (Story 2.10) ships AC-1-only Tier-1-evidence-
    only verification. Epic 4's Stories 4.1-4.13 thicken the QA
    specialist with the behavioral plan, full env provisioning, the
    Playwright MCP / HTTP drivers, and the three-tier evidence
    hierarchy, at which point this function flips in place.
    """
    return False


def is_retry_present() -> bool:
    """``True`` once Epic 5's whole-story retry budget + bucket-driven
    action item derivation + Dev fix-only retry mechanism lands.

    Epic 2 substrate state: returns ``False`` unconditionally — the
    Epic-2-era walking-skeleton runs straight through dev → review →
    qa with no retry path. Epic 5's Stories 5.1-5.8 land the retry
    machinery, at which point this function flips in place.
    """
    return False


def is_loud_fail_block_present() -> bool:
    """``True`` once Epic 6's dedicated top-of-bundle loud-fail block
    section + per-specialist × per-retry cost breakdown + actionable
    how-to-enable pointer enrichment lands.

    Epic 2 substrate state: returns ``False`` unconditionally — the
    Epic-2-era PR bundle does NOT include a ``## Loud-fail`` H2 section
    (the absence is structural, NOT a placeholder), and the
    ``walking-skeleton-bundle`` marker emits unconditionally per AC-4
    of Story 2.11. Epic 6's Story 6.1 lands the loud-fail block, at
    which point this function flips in place AND the marker emission
    rule (predicated on this flag in :mod:`loud_fail_harness.bundle_assembly`)
    inverts: the marker stops emitting.
    """
    return False
