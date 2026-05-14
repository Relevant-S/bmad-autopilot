"""Pluggability no-cross-references CI gate (story 1.10a). FR62 + FR63.

Architectural placement (story 1.8 + story 1.9 precedent — story 1.10a Dev
Notes "Do not add a 6th substrate component slot"): this module is
structurally a sibling of the five substrate-component modules
(envelope_validator, event_validator, reconciler, enumeration_check,
fixture_coverage) and the prior CI gates (fr33_fixture_gate from story 1.8,
hook_budget_gate from story 1.9) but it is **NOT a sixth substrate
component**. ADR-003 Consequence 1 enumerates exactly five substrate
components (architecture.md line 311-315); this gate is a CI **gate** that
enforces FR62 against the inner repo's ``agents/`` directory. The substrate-
component count stays at FIVE; the harness gate count grows to EIGHT at this
story's landing (envelope-validator, event-validator, dependencies-validator,
enumeration-check, fixture-coverage, fr33-fixture-gate, hook-budget-gate,
pluggability-gate).

What this gate enforces:
    * **FR62** (PRD line 897; architecture.md line 1031) — "CI enforces
      pluggability no-cross-references — specialist code (Dev, Review-BMAD,
      QA, Review-LAD) cannot import or reference another specialist." This
      gate IS the FR62 enforcement mechanism. In this architecture's
      specialist representation (markdown agent definitions per ADR-004
      dispatch via Task tool — architecture.md line 1068), "code" includes
      the agent-definition markdown that is treated as the specialist's
      executable instructions.
    * **FR63** (PRD line 898) — "Removing one specialist (e.g., QA)
      requires removing only its orchestrator state transition and its
      hook-handled artifacts; no other specialist requires modification."
      The gate operationally underwrites FR63 by preventing the cross-
      references that would force cascading edits on other specialists.

Cell-1 invariant linkage (ADR-002 architecture.md line 129; line 374; line
406): the pluggability invariant is part of the cell-1 architectural-core
surface. Specialists are independently rebuildable; specialist-to-specialist
cross-references would collapse cell-5's port-cost analysis into a higher
cost cell (because removing one specialist would require editing other
specialists). Per ADR-004 (architecture.md line 374, line 406): "Sequential
dispatch is forced by the pluggability invariant. Specialists cannot
reference each other (ADR-002 cell-1 invariant); cross-specialist
parallelism would require cross-references or shared state. Per-seam
sequential dispatch is the only shape that preserves pluggability." This
gate is the CI-level enforcement of the invariant ADR-004's dispatch logic
depends on.

Cross-story seam contracts (1.10a is invariant-pinned BEFORE downstream
specialist files land):
    * Story 2.4 (state machine doesn't import specialists);
    * Story 2.5 (orchestrator skill doesn't reference specialists);
    * Story 2.6 (specialist dispatch wrapper treats agent files as data,
      not as code — the wrapper lives outside ``agents/`` and is therefore
      substrate by construction);
    * Story 2.8 lands ``agents/dev-wrapper.md`` (the FIRST specialist file);
    * Story 2.9 lands ``agents/review-bmad-wrapper.md`` (FIRST point at
      which Rule 2 can fire — two specialists with multi-hyphen slugs);
    * Story 2.10 lands ``agents/qa.md`` (FIRST point at which Rule 1 can
      fire on ``agents/qa.md`` references; Rule 2 does not fire on ``qa``
      per the deliberate-asymmetry exclusion);
    * Story 2.11 (bundle assembler is single source of truth for header
      text; lives in substrate, not ``agents/``);
    * Story 3.2 (Review-BMAD wrapper PR — gate fires non-trivially);
    * Stories 4.x (QA elaboration must not reference Dev or Review-BMAD);
    * Stories 10.x (Review-LAD Phase 1.5 must not reference any other
      specialist — Story 10.6 lands the explicit FR62 structural witness).
The baseline-zero pass (no ``agents/`` directory at story 1.10a's landing
time) is the gate's correct posture: 0 specialists = 0 possible cross-
references, exit 0.

Loud-fail discipline (Pattern 5):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — full pass: ``cross_reference_violation`` empty. Includes the
            baseline-zero case (``agents/`` does not exist OR contains
            zero ``.md`` files at the top level) and the all-clean-
            specialist case (every discovered specialist has zero outgoing
            cross-references).
        1 — invariant violation: ``cross_reference_violation`` non-empty.
            Recoverable by EITHER (a) removing the cross-reference
            (refactor the offending specialist to NOT reference the other
            specialist by slug or path), OR (b) extracting the shared
            logic into a substrate location (``tools/loud-fail-harness/``,
            ``schemas/``, or a shared-helpers module — see story 2.2's
            atomic-write helper, story 2.11's bundle assembler, and story
            1.10b's section-allowlist library for precedents on "shared
            substrate that specialists may consume"), OR (c) treating
            the referenced agent file as DATA via the orchestrator's
            dispatch wrapper, NOT as code (per epics.md story 2.6). Per
            FR62 + ADR-002 cell-1, the invariant is non-revisitable as a
            relaxation; a PRD/architecture amendment is the only route to
            change the rule.
        2 — harness-level error: ``agents_dir`` exists but is unreadable
            (permission-denied), OR a discovered ``.md`` file is
            unreadable, OR a discovered ``.md`` file is non-UTF-8.
            Practitioners disambiguate via the stderr prefix
            ``"harness-level error: ..."``.

    No mixed-finding precedence is needed — there is only one violation
    bucket; multiple findings within the bucket all produce exit 1 with no
    precedence promotion.

Sensor-not-advisor (PRD-level invariant):
    The gate REPORTS per-file cross-references with remediation pointers;
    it does NOT auto-edit specialist files, suggest specific refactors,
    rewrite the slug list, or add/modify ``agents/`` contents. Same
    posture as 1.4 / 1.5 / 1.6 / 1.7 / 1.8 / 1.9.

Cross-component reuse posture (story 1.10a do-not-do matrix
"do not import from other validator/gate modules"):
    * :func:`loud_fail_harness._shared.find_repo_root` — REUSED for
      default-path resolution (the canonical ``agents/`` directory under
      the inner repo root). NO other substrate-component imports —
      cross-reference detection is a text-scan operation over markdown
      files, not a schema- or fixture-driven operation.

Detection rules (canonical algorithm — co-located with the implementation):

    Rule 1 (path-form): for each pair (file_F, file_G) where F ≠ G in
        ``discover_specialists(agents_dir)``: the regex
        ``\\bagents/<G.name>(?!\\w|[.]\\w)`` is searched against
        ``file_F``'s text. Each match emits one
        ``CrossReferenceFinding`` with ``rule="path-form"``. The
        leading ``\\b`` anchors the start (prevents matching
        ``myagents/<G.name>``). The trailing ``(?!\\w|[.]\\w)``
        (negative lookahead) blocks a word character immediately after
        the filename OR a dot followed by a word character, so
        ``agents/dev-wrapper.md`` matches inside
        ``Use agents/dev-wrapper.md for handoff.`` AND inside
        ``[link](agents/dev-wrapper.md)`` AND when followed by a
        sentence-ending period (the period is not followed by a word
        char), but NOT inside ``agents/dev-wrapper.mds`` (trailing
        ``s`` is a word char) AND NOT inside
        ``agents/dev-wrapper.md.bak`` (dot followed by word char).
        Self-references are excluded (``G == F``); a specialist file
        may name its own path freely.

    Rule 2 (slug-form): for each pair (file_F, file_G) where F ≠ G AND
        ``G.stem`` contains AT LEAST ONE HYPHEN: the regex
        ``\\b<G.stem>\\b`` is searched against ``file_F``'s text. Each
        match emits one ``CrossReferenceFinding`` with ``rule="slug-form"``.
        Self-references are excluded. **Path-prefix suppression**: a
        slug-form match preceded by the literal string ``agents/`` is
        suppressed — such an occurrence is part of a path-form construct
        (whose detection is Rule 1's responsibility). This prevents
        double-counting (e.g., ``agents/dev-wrapper.md`` would otherwise
        trigger BOTH Rule 1 on the full path AND Rule 2 on the embedded
        slug; the suppression keeps the rule count at one finding per
        cross-reference) AND ensures the AC-9 "substring superset" row
        (``agents/dev-wrapper.mds``) produces zero findings even though
        the slug ``dev-wrapper`` is word-bounded inside it.

The single-hyphen-minimum filter on Rule 2 is the **deliberate asymmetry**
that prevents false positives: single-word tokens like ``qa``, ``dev``,
``review``, ``lad`` collide with marker classes (``qa-failed``,
``dev-completed``), lifecycle states (``qa``, ``review``), section names
(``## QA Behavioral Plan``, ``## Senior Developer Review (AI)``), envelope
fields (``qa_results``, ``ac_results``), and free-text references.
Including them in Rule 2 would fire on every legitimate marker emission —
making the gate unusable. Path-form Rule 1 is the ONLY mechanism that
catches QA cross-references — a specialist referencing ``qa`` as a bare
token is NOT flagged; a specialist referencing ``agents/qa.md`` IS flagged.
This is a feature, not a bug.

Allowlist (enforced by construction, NOT by an explicit deny-list):
    * Rule 1 only fires on the ``agents/`` prefix — anything outside
      ``agents/`` (``tools/``, ``schemas/``, ``skills/``, ``hooks/``,
      ``_bmad/``, ``examples/``, ``config-templates/``, ``docs/``) is by
      construction outside the trigger.
    * Rule 2 only fires on the discovered specialist set's multi-hyphen
      slugs — anything not in that set (``bmad-dev-story``,
      ``bmad-code-review``, ``bmad-create-story`` — BMAD-core skill names
      per FR40 + architecture.md lines 1205-1207; ``loud-fail-harness``,
      ``enumeration-check``, ``fixture-coverage`` — substrate identifiers)
      is by construction outside the trigger.
    * Section names (``## QA Behavioral Plan``), marker class identifiers
      (``qa-failed``, ``dev-completed``), lifecycle states
      (``ready-for-dev``, ``in-progress``, ``review``, ``qa``, ``done``),
      run-state field names (``qa_results``, ``ac_results``), and hook-as-
      data references all pass by construction.

The simplicity of the rules is load-bearing: a code reviewer can verify the
rules by inspection in under 30 seconds, AND a practitioner debugging a CI
failure can apply the rules to their specialist file in under 60 seconds.
ANY additional rule complexity (markdown AST parsing, allowlist deny-
listing, natural-language detection) would defeat the audit-by-inspection
property AND would require justification against the false-positive cost.

Determinism (parallel to 1.4 / 1.5 / 1.6 / 1.7 / 1.8 / 1.9):
    * ``discover_specialists`` returns a list sorted by
      ``pathlib.Path.name`` — explicit sort, never relying on filesystem
      iteration order.
    * ``GateResult.passing`` is sorted by ``specialist_slug``;
      ``GateResult.cross_reference_violation`` is sorted by
      ``(offending_specialist, referenced_specialist, line_number, rule)``.
    * ``GateResult`` is a Pydantic v2 frozen model with field-declaration-
      order JSON serialization (load-bearing for byte-stable
      ``model_dump_json()``).
    * No use of ``set`` for stdout-observed collections.

Phase-1.5 four-specialist coverage (Story 10.6): the gate's discovery +
Rule 1 + Rule 2 already covered Review-LAD by construction at Story
1.10a's landing time (top-level ``agents/*.md`` glob, no specialist
allowlist; ``"-" in stem`` multi-hyphen filter admits
``review-lad-wrapper`` automatically). Story 10.6 lands the explicit structural-
witness tests at ``test_pluggability_gate.py`` covering all six cross-
direction edges between Review-LAD and ``{Dev, Review-BMAD, QA}``, the
four-specialist clean-baseline witness against the production
``agents/`` tree, and the deliberate-asymmetry-on-bare-``qa`` witness
codifying that Rule 2's single-word-slug exclusion is load-bearing.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections.abc import Sequence
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from loud_fail_harness._shared import find_repo_root

#: AC-7 remediation pointer (verbatim per the validator-contract table in
#: story 1.10a's Dev Notes). Single string used for both rule="path-form"
#: and rule="slug-form" findings — both rules enforce the same FR62 +
#: ADR-002 cell-1 invariant, so the remediation pointer is shared.
_VIOLATION_REMEDIATION: str = (
    "(per FR62 + ADR-002 cell-1 invariant: specialist-to-specialist "
    "references break pluggability — removing one specialist must require "
    "touching only its orchestrator state transition + hook artifacts, not "
    "other specialists. Remediation: (a) remove the reference, (b) extract "
    "shared logic into substrate (tools/loud-fail-harness/, schemas/, or a "
    "shared-helpers module — see story 2.2's atomic-write helper for "
    "precedent), or (c) treat the referenced agent file as DATA via the "
    "orchestrator's dispatch wrapper, NOT as code (per epics.md story 2.6).)"
)


class Reference(BaseModel):
    """A passing specialist file (zero outgoing cross-references).

    Frozen for hashability + determinism; field declaration order is load-
    bearing for byte-stable JSON dumps. Mirrors story 1.7 / 1.8 / 1.9's
    :class:`Reference` shape; declared locally per the within-module-only-
    coupling discipline (DO NOT import cross-module Pydantic models).

    The ``scanned_line_count`` field carries the number of lines in the
    specialist file scanned — included for renderer transparency and so
    debugging output makes the file-scope visible (parallel to 1.7's
    ``Reference`` shape carrying the file name + 1.9's ``Reference`` shape
    carrying the effective_line_count).
    """

    model_config = ConfigDict(frozen=True)

    specialist_slug: str
    file_name: str
    scanned_line_count: int


class CrossReferenceFinding(BaseModel):
    """A FR62 specialist-to-specialist cross-reference violation finding.

    One ``CrossReferenceFinding`` per detected cross-reference; multiple
    findings per offending file are emitted (do-not-bail-after-first per
    AC-3 / AC-4). Sorted by ``(offending_specialist, referenced_specialist,
    line_number, rule)`` at the gate level.

    The ``rule`` field uses ``typing.Literal`` for type-safe enumeration
    (parallel to 1.5 / 1.7 / 1.8 / 1.9 discipline). Discriminated unions
    would be over-engineering for a two-element enumeration with a shared
    finding shape.
    """

    model_config = ConfigDict(frozen=True)

    offending_file: str
    offending_specialist: str
    referenced_specialist: str
    matched_text: str
    line_number: int
    rule: Literal["path-form", "slug-form"]


class GateResult(BaseModel):
    """Two-bucket pluggability gate output.

    * ``passing`` — specialists with zero outgoing cross-references. One
      :class:`Reference` per such specialist; sorted by
      ``specialist_slug``. Empty when ``agents/`` does not exist, has zero
      ``.md`` files, OR every discovered specialist has at least one
      outgoing cross-reference.
    * ``cross_reference_violation`` — one
      :class:`CrossReferenceFinding` per detected cross-reference;
      sorted by ``(offending_specialist, referenced_specialist,
      line_number, rule)``. Empty when no cross-references detected OR
      when ``agents/`` does not exist.

    Field declaration order matches Pydantic v2's JSON-serialization order
    (load-bearing for byte-stable ``model_dump_json()``; parallel to 1.4 /
    1.5 / 1.6 / 1.7 / 1.8 / 1.9).

    Classification completeness: every discovered specialist file appears
    in EITHER ``passing`` (zero outgoing cross-references) OR generates
    one-or-more entries in ``cross_reference_violation`` (one per detected
    cross-reference). A specialist with at least one cross-reference is
    NOT in ``passing`` even if some of its references are permitted — the
    ``passing`` bucket means "ZERO outgoing cross-references".
    """

    model_config = ConfigDict(frozen=True)

    passing: list[Reference]
    cross_reference_violation: list[CrossReferenceFinding]


def discover_specialists(agents_dir: pathlib.Path) -> list[pathlib.Path]:
    """Return a sorted list of ``.md`` files at the top level of ``agents_dir``.

    Top-level only: ``agents/subdir/foo.md`` is NOT discovered. Per
    architecture.md lines 1068-1072 + 1122-1126 + 1155-1159 the canonical
    specialist layout is at the TOP LEVEL of ``agents/``. Recursive
    discovery would (a) silently allow practitioners to "hide" specialists
    in subdirectories to evade the gate, AND (b) discover unrelated ``.md``
    files (e.g., per-specialist-docs subfolders) that aren't ever invoked
    as specialists. The top-level-only rule mirrors the View 2 distribution-
    unit layout AND mirrors story 1.9's hook-discovery discipline.

    Returns ``[]`` if ``agents_dir`` does not exist OR exists but contains
    zero matching ``.md`` files (the baseline-zero pass case at story
    1.10a's landing time, before stories 2.8 / 2.9 / 2.10 / 4.x land
    specialist files). Raises ``RuntimeError`` (wrapping ``OSError``) on
    permission-denied or other filesystem errors distinct from
    ``FileNotFoundError`` — the caller surfaces those as harness-level
    errors (exit 2).
    """
    if not agents_dir.exists():
        return []
    discovered: list[pathlib.Path] = []
    try:
        for entry in agents_dir.glob("*.md"):
            # Defensive: glob may include directories whose names happen to
            # end in `.md` on some filesystems. The top-level-only rule is
            # also enforced by `glob` (vs. `rglob`).
            if entry.is_file():
                discovered.append(entry)
    except OSError as exc:
        raise RuntimeError(
            f"agents/ directory unreadable: {agents_dir}: {exc}"
        ) from exc
    discovered.sort(key=lambda p: p.name)
    return discovered


def _line_number_for_match_start(file_text: str, match_start: int) -> int:
    """Return the 1-indexed line number containing offset ``match_start``.

    Implementation: count newlines in ``file_text[:match_start]``, add 1.
    A match at offset 0 lives on line 1; a match immediately after the
    first ``\\n`` lives on line 2.
    """
    return file_text[:match_start].count("\n") + 1


def read_specialist_text(path: pathlib.Path) -> tuple[str, int]:
    """Read ``path`` as UTF-8; return ``(text, line_count)``.

    ``line_count`` is ``len(text.splitlines())`` — the splitlines count
    of the scanned file, surfaced via :class:`Reference.scanned_line_count`
    for renderer transparency.

    Raises ``RuntimeError`` if the file is unreadable (``OSError``) or
    not valid UTF-8 (``UnicodeDecodeError``); the caller surfaces these
    as harness-level errors (exit 2). Same posture as story 1.9's
    ``count_effective_lines``.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"agent file not UTF-8: {path}") from exc
    except OSError as exc:
        raise RuntimeError(f"agent file unreadable: {path}") from exc
    return text, len(text.splitlines())


def find_cross_references_path_form(
    file_path: pathlib.Path,
    file_text: str,
    specialist_set: list[pathlib.Path],
) -> list[CrossReferenceFinding]:
    """Apply Rule 1 (path-form) over ``file_text``.

    For each OTHER specialist ``other`` in ``specialist_set`` (where
    ``other.name != file_path.name``), construct the regex
    ``\\bagents/<other.name>(?!\\w|[.]\\w)`` and emit one
    :class:`CrossReferenceFinding` per match. Self-references are
    excluded — a specialist file may name its own path freely.

    Returns findings sorted by ``(referenced_specialist, line_number,
    rule)`` for determinism within a single file.
    """
    findings: list[CrossReferenceFinding] = []
    for other in specialist_set:
        if other.name == file_path.name:
            continue
        pattern = re.compile(
            r"\bagents/" + re.escape(other.name) + r"(?!\w|[.]\w)"
        )
        for match in pattern.finditer(file_text):
            findings.append(
                CrossReferenceFinding(
                    offending_file=file_path.name,
                    offending_specialist=file_path.stem,
                    referenced_specialist=other.stem,
                    matched_text=match.group(0),
                    line_number=_line_number_for_match_start(
                        file_text, match.start()
                    ),
                    rule="path-form",
                )
            )
    findings.sort(key=lambda f: (f.referenced_specialist, f.line_number, f.rule))
    return findings


#: Path-form prefix used to suppress slug-form matches that are part of
#: an ``agents/<slug>...`` path construct. Path-form references are Rule
#: 1's responsibility; firing Rule 2 on the embedded slug would
#: double-count the same reference.
_PATH_FORM_PREFIX: str = "agents/"


def find_cross_references_slug_form(
    file_path: pathlib.Path,
    file_text: str,
    specialist_set: list[pathlib.Path],
) -> list[CrossReferenceFinding]:
    """Apply Rule 2 (slug-form) over ``file_text``.

    For each OTHER specialist ``other`` in ``specialist_set`` (where
    ``other.name != file_path.name``) whose ``.stem`` contains AT LEAST
    ONE hyphen (``"-" in stem``), construct the word-bounded regex
    ``\\b<other.stem>\\b`` and emit one :class:`CrossReferenceFinding`
    per match. Single-word slugs (``qa``, ``dev``, ``review``, ``lad``)
    are deliberately excluded — see the module docstring's "deliberate
    asymmetry" rationale. Self-references are excluded.

    Path-prefix suppression: a slug-form match preceded by the literal
    string ``agents/`` at a word boundary is suppressed (the slug is
    inside a path-form construct whose detection is Rule 1's
    responsibility). The word-boundary check ensures that ``agents/`` is
    not the suffix of a longer identifier (e.g., ``myagents/dev-wrapper``
    must NOT be suppressed — ``myagents/`` is not ``agents/``). This
    keeps the finding count at one per cross-reference for the canonical
    ``agents/<slug>.md`` shape AND ensures the AC-9 "substring superset"
    case (``agents/dev-wrapper.mds`` — Rule 1 doesn't match because of
    the trailing ``s``; we want Rule 2 not to match either, so the net
    finding count is zero, matching the deliberate-NO-match expectation).

    Returns findings sorted by ``(referenced_specialist, line_number,
    rule)`` for determinism within a single file.
    """
    findings: list[CrossReferenceFinding] = []
    prefix_len = len(_PATH_FORM_PREFIX)
    for other in specialist_set:
        if other.name == file_path.name:
            continue
        slug = other.stem
        if "-" not in slug:
            # Single-word slugs are deliberately excluded from Rule 2 to
            # avoid colliding with marker classes / lifecycle states /
            # section names. Path-form Rule 1 is the only mechanism that
            # catches single-word-slug cross-references.
            continue
        pattern = re.compile(r"\b" + re.escape(slug) + r"\b")
        for match in pattern.finditer(file_text):
            start = match.start()
            preceding = file_text[max(0, start - prefix_len):start]
            if preceding == _PATH_FORM_PREFIX:
                # Only suppress when `agents/` is at a word boundary —
                # i.e., NOT preceded by a word character (which would
                # make it part of a longer name like `myagents/`).
                prefix_start = start - prefix_len
                if prefix_start == 0 or not re.match(
                    r"\w", file_text[prefix_start - 1]
                ):
                    continue
            findings.append(
                CrossReferenceFinding(
                    offending_file=file_path.name,
                    offending_specialist=file_path.stem,
                    referenced_specialist=slug,
                    matched_text=match.group(0),
                    line_number=_line_number_for_match_start(
                        file_text, match.start()
                    ),
                    rule="slug-form",
                )
            )
    findings.sort(key=lambda f: (f.referenced_specialist, f.line_number, f.rule))
    return findings


def run_pluggability_gate(agents_dir: pathlib.Path) -> GateResult:
    """Execute the gate over ``agents_dir`` and produce a :class:`GateResult`.

    Discovers specialists, reads each, applies Rule 1 + Rule 2, partitions
    results into the two buckets per AC-5. Never bails after the first
    finding within a category (parallel to 1.5 / 1.6 / 1.7 / 1.8 / 1.9).

    Raises ``RuntimeError`` if any discovered ``.md`` file is unreadable
    or non-UTF-8 (propagated from :func:`read_specialist_text`); the
    caller surfaces this as exit 2. ``OSError`` from a permission-denied
    ``agents_dir`` is also propagated for the same reason.
    """
    discovered = discover_specialists(agents_dir)

    passing: list[Reference] = []
    violations: list[CrossReferenceFinding] = []

    for specialist_path in discovered:
        text, line_count = read_specialist_text(specialist_path)
        per_file_findings = find_cross_references_path_form(
            specialist_path, text, discovered
        ) + find_cross_references_slug_form(
            specialist_path, text, discovered
        )
        if per_file_findings:
            violations.extend(per_file_findings)
        else:
            passing.append(
                Reference(
                    specialist_slug=specialist_path.stem,
                    file_name=specialist_path.name,
                    scanned_line_count=line_count,
                )
            )

    passing.sort(key=lambda r: r.specialist_slug)
    violations.sort(
        key=lambda f: (
            f.offending_specialist,
            f.referenced_specialist,
            f.line_number,
            f.rule,
        )
    )

    return GateResult(
        passing=passing,
        cross_reference_violation=violations,
    )


def format_findings(result: GateResult, *, agents_dir: str) -> str:
    """Render a :class:`GateResult` for stdout.

    Header naming inputs (3 lines per AC-7); per-violation finding lines
    with AC-7 distinct-shape diagnostics; remediation pointer per finding;
    footer Summary line. Mirrors the "name the offending entity +
    remediation pointer" discipline from 1.5 / 1.6 / 1.7 / 1.8 / 1.9.
    """
    lines: list[str] = []
    lines.append("Pluggability gate (story 1.10a; FR62)")
    lines.append(f"  agents dir: {agents_dir}")
    lines.append(
        "  rules: Rule 1 (path-form: agents/<other>.md) + Rule 2 "
        "(slug-form: multi-hyphen specialist slugs only)"
    )
    lines.append("")

    for cf in result.cross_reference_violation:
        message = (
            f"Pluggability violation: {cf.offending_file} "
            f"(specialist {cf.offending_specialist}) cross-references "
            f"specialist {cf.referenced_specialist} via rule "
            f'{cf.rule}: matched "{cf.matched_text}" at line '
            f"{cf.line_number}."
        )
        lines.append(message)
        lines.append(_VIOLATION_REMEDIATION)
        lines.append("")

    distinct_offenders = len(
        {cf.offending_specialist for cf in result.cross_reference_violation}
    )
    lines.append(
        f"Summary: {len(result.passing)} passing specialist(s), "
        f"{len(result.cross_reference_violation)} cross-reference "
        f"violation(s) across {distinct_offenders} specialist file(s)."
    )
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pluggability-gate",
        description=(
            "Pluggability no-cross-references CI gate (story 1.10a). "
            "Enforces FR62 (specialist code cannot reference another "
            "specialist by path-form `agents/<other>.md` per Rule 1, or "
            "by multi-hyphen slug-form per Rule 2). Single-word slugs "
            "(qa, dev, review, lad) are deliberately excluded from Rule 2 "
            "to avoid colliding with marker classes, lifecycle states, "
            "and section names — see the module docstring for the full "
            "rationale. ADR-002 cell-1 + ADR-004 + FR62 + FR63."
        ),
    )
    parser.add_argument(
        "--agents-dir",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to agents/ directory (default: <repo-root>/agents/). "
            "Test-injection flag; CI invocations omit it."
        ),
    )
    return parser


def _display_path(
    path: pathlib.Path, repo_root: Optional[pathlib.Path] = None
) -> str:
    """Render ``path`` relative to repo root if possible; absolute otherwise.

    Mirrors the pattern in ``hook_budget_gate._display_path`` /
    ``fr33_fixture_gate._display_path`` / ``fixture_coverage._display_path``
    so canonical CI invocations produce stable diff-friendly relative paths
    and ``tmp_path`` invocations fall back to absolute (still informative
    in stdout).
    """
    try:
        rr = repo_root if repo_root is not None else find_repo_root()
        return str(path.resolve().relative_to(rr.resolve()))
    except (RuntimeError, ValueError):
        return str(path.resolve())


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    agents_dir: pathlib.Path
    repo_root: Optional[pathlib.Path] = None
    if args.agents_dir is None:
        try:
            repo_root = find_repo_root()
        except RuntimeError as exc:
            print(f"harness-level error: {exc}", file=sys.stderr)
            return 2
        agents_dir = repo_root / "agents"
    else:
        agents_dir = args.agents_dir

    # Guard the readability of `agents_dir` BEFORE the gate runs so a
    # permission-denied directory surfaces as exit 2 with a precise
    # message — distinct from `discover_specialists`'s graceful-absence
    # path (returning [] for non-existent dirs is exit 0, not exit 2).
    if agents_dir.exists():
        try:
            next(iter(agents_dir.iterdir()), None)
        except PermissionError as exc:
            print(
                "harness-level error: agents/ directory unreadable: "
                f"{agents_dir}: {exc}",
                file=sys.stderr,
            )
            return 2
        except OSError as exc:
            print(
                "harness-level error: agents/ directory unreadable: "
                f"{agents_dir}: {exc}",
                file=sys.stderr,
            )
            return 2

    try:
        result = run_pluggability_gate(agents_dir)
    except RuntimeError as exc:
        # Loud-fail (Pattern 5): unreadable / non-UTF-8 specialist files
        # surface as exit 2 with a `harness-level error:` stderr prefix
        # mirroring 1.5 / 1.6 / 1.7 / 1.8 / 1.9.
        print(f"harness-level error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        # Defensive: a permission-denied iteration mid-discover would
        # propagate here even after the upfront iterdir check above (e.g.
        # a TOCTOU window). Surface identically to the upfront check.
        print(
            "harness-level error: agents/ directory unreadable: "
            f"{agents_dir}: {exc}",
            file=sys.stderr,
        )
        return 2

    print(
        format_findings(
            result,
            agents_dir=_display_path(agents_dir, repo_root=repo_root),
        )
    )

    if result.cross_reference_violation:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
