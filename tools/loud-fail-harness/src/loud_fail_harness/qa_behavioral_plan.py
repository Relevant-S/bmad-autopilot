"""QA Behavioral Plan generation + reuse library (story 4.1). FR23 + FR16.

Architectural placement (parallel to ``story_doc_validator`` from story
1.10b): this module is structurally a pure-library sibling of the substrate-
component modules and the prior CI gates. It is **NOT a sixth substrate
component** (ADR-003 enumerates exactly five substrate components at
architecture.md lines 311-315). It is a pure library consumed by the QA
specialist wrapper at ``bmad-autopilot/agents/qa.md`` to satisfy FR23's
"QA generates a ``## QA Behavioral Plan`` section in the story doc on first
run and persists it; subsequent runs reuse the plan with AC-hash drift
detection" commitment (PRD line 838). Story 4.1 lands plan creation +
reuse; story 4.2 lands drift detection on top of the third action token
exposed here.

What this library owns:
    * ``QABehavioralPlan`` Pydantic v2 model carrying the six required fields
      named verbatim by the epic AC at ``epics.md`` line 1818 + 1822-1823.
    * ``PlanPersistAction`` Literal enumerating exactly three action tokens
      ``{write-new, reuse-existing, drift-suspected}``. The third value is a
      forward-pointer to story 4.2's drift-detection surface — story 4.1 does
      NOT emit the ``plan-drift-detected`` marker.
    * ``compute_ac_hash`` — deterministic SHA-256-over-canonical-form hash of
      the AC list. Stability guarantees recorded in detail in this docstring
      under "AC-hash function" below + in ``docs/architecture.md``'s story-4.1
      addendum per AC-7.
    * ``generate_plan`` — first-run plan generator producing the four required
      per-AC fields (MVP placeholder defaults — stories 4.8 / 4.9 thicken).
    * ``render_plan_section`` / ``parse_plan_section`` — lossless round-trip
      between the Pydantic model and a markdown body suitable for writing
      under the ``## QA Behavioral Plan`` H2 header (the H2 prefix is added
      by the wrapper's section-allowlist write path; the body is what this
      function produces).
    * ``persist_or_reuse_plan`` — pure orchestration entry point composing the
      four primitives. Returns a ``(plan, action_token)`` tuple; performs no
      file I/O; does NOT call ``validate_section_write``; does NOT emit any
      marker. The wrapper's procedural step is responsible for the actual
      story-doc write through the story 1.10b validator AFTER inspecting the
      action token.

Marker-class linkage (FORWARD-POINTER):
    The ``plan-drift-detected`` marker class exists in
    ``schemas/marker-taxonomy.yaml`` from story 1.4's proactive add. THIS
    module does NOT consume the marker class. Story 4.2's drift-detection
    surface consumes the ``drift-suspected`` action token returned here and
    emits the ``plan-drift-detected`` marker on top — without redefining the
    action enum or this module's public API.

Section-allowlist linkage (sensor-not-advisor split):
    ``story_doc_validator.ALLOWED_SECTIONS[3]`` is the literal string
    ``"## QA Behavioral Plan"`` (story 1.10b). The wrapper's procedural step
    calls ``validate_section_write("## QA Behavioral Plan")`` BEFORE writing
    the rendered body to the story doc. THIS module does NOT call the
    validator itself — same posture story 1.10b's docstring established for
    the validator's caller-emits-marker pattern.

In-place-thickening linkage (epic 3 retro Insight #1 — second confirmation):
    ``agents/qa.md`` is the wrapper composing this library. The wrapper's
    Procedure step 6 changes from a "Do NOT generate or persist a
    ``## QA Behavioral Plan`` section" forbid (story 2.10's AC-1-only
    baseline) to a "DO" affirmative procedural step naming this library's
    ``persist_or_reuse_plan`` + ``story_doc_validator.validate_section_write``
    composition (story 4.1's AC-8 surface). Same agent identity, same
    envelope contract — only the wrapper's internal coverage thickens.

Cross-component reuse posture (story 1.10b precedent):
    * Python stdlib ``hashlib`` (SHA-256) — REUSED. No new runtime dependency.
    * Python stdlib ``re`` — REUSED for whitespace-normalization +
      section-extraction regex.
    * ``pydantic.BaseModel`` + ``pydantic.ConfigDict`` — REUSED (already pinned
      by stories 1.1 / 1.2 / 1.10b).
    * ``loud_fail_harness._shared.find_repo_root`` — NOT used by the library's
      pure path. The library does not read or write files itself; file I/O is
      the wrapper's procedural-step responsibility (mirrors story 1.10b's
      no-file-I/O posture).
    * ``loud_fail_harness.qa_plan_persistence_compromise.render_compromise_blockquote``
      — REUSED by ``render_plan_section`` (Story 4.11 / FR25): every rendered
      plan body PREPENDS the canonical Plan-persistence-compromise blockquote
      at the very top, sourced from the single-source-of-truth constant in
      that module. The compromise blockquote is fixed-text decoration NOT
      round-tripped through ``parse_plan_section`` as structured data — it is
      regenerated on every render call. ``parse_plan_section``'s regex anchors
      already operate in MULTILINE mode so the leading blockquote does not
      perturb plan_status / ac_hash / per-AC-entry extraction.

AC-hash function — canonical normalization rules (AC-2 + AC-7):
    The hash is computed over a canonical normalized string representation
    of the AC list. The normalization rules are:

    1. For each AC entry, extract ``ac_text`` only. The ``ac_id`` is the
       index, NOT the content — only the AC text contributes to the hash.
       This makes AC reordering with the same text content yield the same
       hash (the order-stable property per epics.md line 1855).
    2. Normalize each ``ac_text``: collapse internal whitespace runs to a
       single space (``re.sub(r"\\s+", " ", text)``); strip leading/trailing
       whitespace (``text.strip()``). This is the whitespace-stability
       property per epics.md line 1832.
    3. Sort the normalized AC texts lexicographically. This is the order-
       stable choice per epics.md line 1855: AC reordering with the same
       content does NOT trigger drift. The dev-call recommendation in the
       story Dev Notes selected order-stable; the architecture.md addendum
       records the rationale.
    4. Join the sorted normalized texts with a single newline ``\\n`` as
       separator.
    5. Encode UTF-8.
    6. Compute ``hashlib.sha256(...).hexdigest()`` — returns the full
       64-character hex digest for collision-resistance margin.

    Determinism: two calls with the same ``ac_list`` content yield the same
    digest (test ``test_compute_ac_hash_deterministic``).

    Whitespace stability: two calls with whitespace-only-different
    ``ac_list`` yield the same digest (test
    ``test_compute_ac_hash_whitespace_stable``).

    Content discrimination: two calls with substantively-different
    ``ac_list`` (single non-whitespace character change) yield different
    digests (test ``test_compute_ac_hash_content_discriminates``).

    Order stability: two calls with the same ACs in different ordering
    yield the same digest (test ``test_compute_ac_hash_order_treatment``).

Flow-branch enumeration (FR22c — Story 13.2):
    ``QABehavioralPlanEntry`` carries an optional ``flow_branches`` field —
    a ``tuple[FlowBranch, ...]`` enumerating the optional / branching steps
    *within* a single AC's flow. Each ``FlowBranch`` carries ``branch_id``,
    ``description``, ``disposition`` (``"must-visit"`` default, or
    ``"intentionally-skipped"`` — which requires a one-line
    ``skip_rationale``), and ``skip_rationale``. The field is additive and
    optional with an empty-tuple default: a plan authored before FR22c
    parses unchanged (``flow_branches == ()``), and ``generate_plan``
    leaves it empty at MVP.

    ``flow_branches`` is deliberately OUT of ``compute_ac_hash`` scope. The
    hash is a pure function of the input AC *text* (``AcEntry.ac_text``);
    ``flow_branches`` is QA-agent-authored *plan content*, not an input AC,
    and is structurally outside the hash's input domain. Therefore an
    operator editing ``flow_branches`` (e.g. flipping a ``disposition``)
    does NOT change ``ac_hash`` and does NOT trigger story 4.2's
    ``plan-drift-detected``. This module renders/parses ``flow_branches``
    losslessly; branch *visitation* at run time is Story 13.3's iteration
    contract and branch *enumeration* at plan-generation time is Story
    13.4's wrapper prompt.

Sensor-not-advisor (PRD-level invariant + Pattern 5):
    The library RETURNS the parsed plan + the action token; it does NOT
    emit markers, does NOT auto-correct AC text, does NOT write to the
    story doc, does NOT call ``validate_section_write``, does NOT log,
    does NOT print. Same posture as 1.4 / 1.5 / 1.6 / 1.7 / 1.8 / 1.9 /
    1.10a / 1.10b.

QA-independence-from-TEA-artifacts invariant (FR16, PRD line 830):
    Plan generation reads ONLY the ``ac_list`` from the dispatch payload
    (which itself is constrained by ``tea-handoff-contract.yaml`` lines
    173-187's ``tea_artifacts_consumed: maxItems: 0``). Plan generation
    does NOT read TEA test files, dev tests, review findings, or commit
    diffs. The invariant is structurally encoded by the dispatch payload
    contract; this library's pure-function signatures preserve it.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from loud_fail_harness.qa_plan_persistence_compromise import (
    render_compromise_blockquote,
)

#: ``PlanPersistAction`` is a Literal carrying exactly three values. The
#: third value ``"drift-suspected"`` is a forward-pointer to story 4.2's
#: drift-detection surface; story 4.1 does NOT emit the
#: ``plan-drift-detected`` marker. The wrapper integration on
#: ``"drift-suspected"`` in story 4.1 treats it as if no plan exists
#: (regenerate fresh + write) WITH a TODO-comment cross-reference to
#: story 4.2 — when story 4.2 lands, the wrapper's ``"drift-suspected"``
#: branch thickens to emit the marker + reset ``plan_status`` without
#: changing the action enum or this module's public API.
PlanPersistAction = Literal["write-new", "reuse-existing", "drift-suspected"]

#: Allowed values for ``QABehavioralPlanEntry.expected_evidence_tier``
#: (verbatim per epics.md line 1818).
ExpectedEvidenceTier = Literal[
    "tier-1-mechanical", "tier-2-outcome", "tier-3-semantic"
]

#: Allowed values for ``QABehavioralPlanEntry.semantic_verification_requirement``
#: (verbatim per epics.md line 1818). The ``not_applicable`` value uses
#: snake_case rather than kebab-case to mirror agents/qa.md line 64's
#: ``semantic_verification: "not_applicable"`` literal at story 2.10.
SemanticVerificationRequirement = Literal[
    "required", "optional", "not_applicable"
]

#: Allowed values for ``FlowBranch.disposition`` (FR22c / Story 13.2).
#: ``"must-visit"`` is the default disposition for an enumerated within-AC
#: flow branch; ``"intentionally-skipped"`` is opt-in per-branch and requires
#: a one-line ``skip_rationale``.
FlowBranchDisposition = Literal["must-visit", "intentionally-skipped"]

#: Allowed values for ``QABehavioralPlanEntry.heuristic_applicability`` list
#: elements (verbatim per epics.md line 497).
HeuristicApplicability = Literal["empty-state", "error-state", "auth-boundary"]

#: Allowed values for the header-level ``plan_status`` field.
#: ``"generated"`` is the initial first-run state per epics.md line 1822;
#: ``"human-reviewed"`` is the post-review state preserved across reuse per
#: epics.md line 1828.
PlanStatus = Literal["generated", "human-reviewed"]


class AcEntry(BaseModel):
    """A single acceptance-criterion entry from the dispatch payload's
    ``ac_list``. Mirrors the shape produced by the orchestrator's
    ``default_story_doc_resolver`` (story 2.5) parsing the story-doc's
    ``## Acceptance Criteria`` section.

    Frozen for hashability + determinism (parallel to story 1.10b's
    ``ValidationResult`` discipline).
    """

    model_config = ConfigDict(frozen=True)

    ac_id: str
    ac_text: str


class FlowBranch(BaseModel):
    """A single within-AC flow branch enumerated in a per-AC plan entry
    (FR22c / Story 13.2).

    A flow branch is an optional or branching step *inside* an AC's flow —
    the path the QA agent reliably under-tests when it covers only the AC's
    main flow. Story 4.1's per-AC entry had no structural slot for these;
    this model is that slot.

    Frozen for hashability + determinism — same discipline as ``AcEntry`` /
    ``QABehavioralPlanEntry`` / ``QABehavioralPlan``.

    ``disposition`` defaults to ``"must-visit"`` per FR22c ("the default
    disposition for an enumerated branch is ``must-visit``"). An
    ``"intentionally-skipped"`` branch requires a non-empty one-line
    ``skip_rationale``; a ``"must-visit"`` branch must NOT carry one (a
    rationale on a must-visit branch is a contradiction). The cross-field
    conditional rule is enforced by the ``_check_skip_rationale``
    ``@model_validator(mode="after")`` — a ``@field_validator`` cannot
    enforce required-when-absent because it does not fire when the field is
    omitted from input.
    """

    model_config = ConfigDict(frozen=True)

    # branch_id enters the marker-key domain in Story 13.3 — it is the
    # `<branch-id>` component of the `heuristic-skipped: flow-branch-
    # <branch-id>` marker. The pattern rejects leading AND trailing
    # whitespace (and newlines) so the rendered marker key is well-formed
    # (FR22c / Story 13.3 AC-9, resolving deferred-work.md line 5).
    branch_id: str = Field(min_length=1, pattern=r"^\S$|^\S.*\S$")
    description: str = Field(min_length=1, pattern=r"^\S[^\n]*$")
    disposition: FlowBranchDisposition = "must-visit"
    skip_rationale: str | None = None

    @model_validator(mode="after")
    def _check_skip_rationale(self) -> FlowBranch:
        if self.disposition == "intentionally-skipped":
            if (
                self.skip_rationale is None
                or not self.skip_rationale.strip()
            ):
                raise ValueError(
                    "intentionally-skipped flow branch requires a "
                    "non-empty skip_rationale"
                )
            if "\n" in self.skip_rationale:
                raise ValueError(
                    "skip_rationale must not contain newlines"
                )
        elif self.skip_rationale is not None:
            raise ValueError(
                "must-visit flow branch must not carry a skip_rationale"
            )
        return self


class QABehavioralPlanEntry(BaseModel):
    """A per-AC plan entry carrying the four required per-AC fields named
    verbatim by the epic AC at epics.md line 1818, the ``ac_id``
    cross-reference field, and the FR22c ``flow_branches`` within-AC
    branch enumeration.

    Frozen for hashability + determinism. Field declaration order is load-
    bearing for byte-stable ``model_dump_json()`` output; ``flow_branches``
    is appended LAST so every pre-existing field keeps its byte position.

    ``flow_branches`` (FR22c / Story 13.2) is the per-AC enumeration of the
    optional / branching steps *within* an AC's flow — the slot Story 4.1's
    entry lacked. It is optional with an empty-tuple default:

    * The MVP ``generate_plan`` path leaves it empty. Populating it at
      plan-generation time is the Story 13.4 wrapper-prompt's responsibility
      (FR22c's "MUST enumerate" is a directive on that prompt, not a
      non-empty-cardinality constraint on this model).
    * Visiting each ``must-visit`` branch at run time — or emitting a
      ``heuristic-skipped: flow-branch-<branch-id>`` marker for an
      ``intentionally-skipped`` one — is Story 13.3's iteration-contract
      surface.
    * ``flow_branches`` is QA-authored plan content and is deliberately OUT
      of ``compute_ac_hash`` scope (the hash is a pure function of AC text);
      see the module docstring's "Flow-branch enumeration" section.
    """

    model_config = ConfigDict(frozen=True)

    ac_id: str
    assertion_shape: str
    expected_evidence_tier: ExpectedEvidenceTier
    semantic_verification_requirement: SemanticVerificationRequirement
    heuristic_applicability: tuple[HeuristicApplicability, ...] = Field(
        default_factory=tuple
    )
    flow_branches: tuple[FlowBranch, ...] = Field(default_factory=tuple)


class QABehavioralPlan(BaseModel):
    """The QA Behavioral Plan model.

    Carries the two header-level fields named verbatim by the epic AC at
    epics.md lines 1822-1823 (``plan_status`` + ``ac_hash``) plus the
    per-AC ``entries`` list. Frozen for hashability + determinism; field
    declaration order is load-bearing for byte-stable ``model_dump_json()``.

    The MVP defaults for the four per-AC fields are placeholder values
    that stories 4.8 + 4.9 thicken:

    * ``expected_evidence_tier`` defaults to ``tier-1-mechanical`` (Story
      2.10 AC-1-only / Tier-1-only Epic-2 baseline). Story 4.8 thickens to
      per-AC derivation.
    * ``semantic_verification_requirement`` defaults to ``not_applicable``.
      Story 4.8 thickens to per-AC derivation.
    * ``heuristic_applicability`` defaults to the empty tuple ``()``.
      Story 4.9 thickens to per-AC derivation from AC text patterns.
    * ``assertion_shape`` is a placeholder declarative pattern derived
      from the AC text (literal echo at MVP — stories 4.6 / 4.7 thicken).
    * ``flow_branches`` defaults to the empty tuple ``()`` (FR22c / Story
      13.2). The MVP ``generate_plan`` path leaves it empty; Story 13.4's
      wrapper prompt populates it at plan-generation time.
    """

    model_config = ConfigDict(frozen=True)

    plan_status: PlanStatus
    ac_hash: str
    entries: tuple[QABehavioralPlanEntry, ...]


# ---------------------------------------------------------------------------
# AC-hash function (AC-2 + AC-7)
# ---------------------------------------------------------------------------


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_ac_text(ac_text: str) -> str:
    """Apply the canonical normalization rules to a single AC text:
    collapse internal whitespace runs to a single space; strip leading/
    trailing whitespace. UTF-8 encoding is applied at hash-input time
    (Python ``str`` is already Unicode; encoding happens at digest input).
    """
    return _WHITESPACE_RE.sub(" ", ac_text).strip()


def compute_ac_hash(ac_list: list[AcEntry] | tuple[AcEntry, ...]) -> str:
    """Return the deterministic SHA-256 hex digest of ``ac_list`` per the
    canonical normalization rules documented in this module's docstring.

    Stability guarantees:

    * Determinism: same input yields the same digest across runs.
    * Whitespace stability: whitespace-only differences in ``ac_text``
      yield the same digest (epics.md line 1832).
    * Content discrimination: any non-whitespace AC-text difference yields
      a different digest.
    * Order stability: AC reordering with the same content yields the same
      digest (epics.md line 1855). Achieved by sorting the normalized AC
      texts lexicographically before joining.

    Returns the full 64-character SHA-256 hex digest for collision-
    resistance margin.

    The function is pure: no global state mutation, no I/O.
    """
    normalized = sorted(
        _normalize_ac_text(entry.ac_text) for entry in ac_list
    )
    canonical = "\n".join(normalized).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


# ---------------------------------------------------------------------------
# generate_plan (AC-3)
# ---------------------------------------------------------------------------


def generate_plan(
    story_id: str, ac_list: list[AcEntry] | tuple[AcEntry, ...]
) -> QABehavioralPlan:
    """Produce a fresh first-run ``QABehavioralPlan`` for ``ac_list``.

    The ``story_id`` is accepted for forward-compatibility with story 4.6's
    plan-driven AC iteration framework (which may use ``story_id`` to scope
    fixture lookups) and to mirror the dispatch-payload signature; the
    current MVP placeholder derivation does not read it.

    Each AC entry yields a corresponding ``QABehavioralPlanEntry`` carrying
    MVP placeholder defaults (see ``QABehavioralPlan`` docstring). The
    header-level ``plan_status`` is initialized to ``"generated"`` (epics.md
    line 1822); the header-level ``ac_hash`` is ``compute_ac_hash(ac_list)``.

    The function is pure.
    """
    del story_id  # MVP: not used; reserved for story 4.6 surface
    entries = tuple(
        QABehavioralPlanEntry(
            ac_id=entry.ac_id,
            assertion_shape=_default_assertion_shape(entry.ac_text),
            expected_evidence_tier="tier-1-mechanical",
            semantic_verification_requirement="not_applicable",
            heuristic_applicability=(),
        )
        for entry in ac_list
    )
    return QABehavioralPlan(
        plan_status="generated",
        ac_hash=compute_ac_hash(ac_list),
        entries=entries,
    )


def _default_assertion_shape(ac_text: str) -> str:
    """MVP placeholder derivation: collapse whitespace and prefix with
    ``"verify: "``. Stories 4.6 / 4.7 thicken to AC-text-pattern-based
    derivation. Always returns a non-empty string (the AC entry's required
    field).
    """
    normalized = _normalize_ac_text(ac_text)
    if not normalized:
        normalized = "<empty AC text>"
    return f"verify: {normalized}"


# ---------------------------------------------------------------------------
# render / parse round-trip (AC-4)
# ---------------------------------------------------------------------------


_PLAN_STATUS_COMMENT_RE = re.compile(
    r"^<!-- plan_status: (?P<status>generated|human-reviewed) -->$",
    re.MULTILINE,
)
_AC_HASH_COMMENT_RE = re.compile(
    r"^<!-- ac_hash: (?P<hash>[0-9a-f]{64}) -->$",
    re.MULTILINE,
)
_ENTRY_HEADER_RE = re.compile(r"^### AC-(?P<ac_id>.+)$", re.MULTILINE)
_FIELD_LINE_RE = re.compile(
    r"^- (?P<key>[a-z_]+): (?P<value>.+)$", re.MULTILINE
)
#: ``flow_branches`` serialization regexes (FR22c / Story 13.2). Matched
#: line-by-line with ``.match()`` so no MULTILINE flag is needed. The header
#: line ``- flow_branches:`` has no value after ``: `` so it does NOT match
#: ``_FIELD_LINE_RE``; the indented record lines are not column-0 anchored so
#: they do not pollute the four-scalar-field ``fields`` dict either.
_FLOW_BRANCH_HEADER_RE = re.compile(r"^- flow_branches:$")
_FLOW_BRANCH_RECORD_RE = re.compile(r"^  - branch_id: (?P<branch_id>.+)$")
_FLOW_BRANCH_SUBFIELD_RE = re.compile(
    r"^    (?P<key>[a-z_]+): (?P<value>.+)$"
)
_FLOW_BRANCH_SUBFIELD_KEYS = frozenset(
    {"description", "disposition", "skip_rationale"}
)
# ``branch_id`` is intentionally absent: it is extracted via
# ``_FLOW_BRANCH_RECORD_RE`` (the ``  - branch_id: …`` line) and stored
# directly, not as a four-space-indented sub-field.


def render_plan_section(plan: QABehavioralPlan) -> str:
    """Render ``plan`` to a markdown body suitable for writing under a
    ``## QA Behavioral Plan`` H2 header. The H2 header itself is NOT
    included — the section-allowlist write path adds it.

    Canonical shape (documented in module docstring; round-trip-stable
    with ``parse_plan_section``):

    * The Story-4.11 plan-persistence-compromise blockquote at the very
      top — fixed-text decoration sourced from
      :func:`loud_fail_harness.qa_plan_persistence_compromise.render_compromise_blockquote`
      on every render call. The blockquote is NOT round-tripped through
      :func:`parse_plan_section` as structured data; it is regenerated
      on every render (single-source-of-truth invariant per FR25).
    * One blank line.
    * Two HTML-comment metadata lines for ``plan_status`` and ``ac_hash``
      — machine-parseable, invisible to most markdown renderers,
      regex-extractable.
    * One blank line.
    * Per-AC entries under ``### AC-{ac_id}`` H3 headers, each followed
      by four ``- key: value`` lines for the four required per-AC fields,
      then — only when the entry's ``flow_branches`` tuple is non-empty —
      a ``- flow_branches:`` block enumerating the FR22c within-AC
      branches (the block is OMITTED ENTIRELY when ``flow_branches`` is
      empty, so a pre-FR22c plan stays byte-identical under render).
    * Entries separated by blank lines.

    The output ends with a trailing newline so downstream concatenation
    under the H2 header produces well-formed markdown.
    """
    parts: list[str] = []
    parts.append(render_compromise_blockquote().rstrip("\n"))
    parts.append("")
    parts.append(f"<!-- plan_status: {plan.plan_status} -->")
    parts.append(f"<!-- ac_hash: {plan.ac_hash} -->")
    parts.append("")
    for entry in plan.entries:
        parts.append(f"### AC-{entry.ac_id}")
        parts.append("")
        parts.append(f"- assertion_shape: {entry.assertion_shape}")
        parts.append(
            f"- expected_evidence_tier: {entry.expected_evidence_tier}"
        )
        parts.append(
            "- semantic_verification_requirement: "
            f"{entry.semantic_verification_requirement}"
        )
        parts.append(
            "- heuristic_applicability: "
            f"{_render_heuristic_list(entry.heuristic_applicability)}"
        )
        parts.extend(_render_flow_branches(entry.flow_branches))
        parts.append("")
    return "\n".join(parts).rstrip("\n") + "\n"


def _render_heuristic_list(
    items: tuple[HeuristicApplicability, ...],
) -> str:
    """Render the ``heuristic_applicability`` list as ``[a, b, c]`` for
    non-empty lists or ``[]`` for empty. Stable, parser-friendly form.
    """
    if not items:
        return "[]"
    return "[" + ", ".join(items) + "]"


def _render_flow_branches(
    branches: tuple[FlowBranch, ...],
) -> list[str]:
    """Render the ``flow_branches`` tuple (FR22c) as a ``- flow_branches:``
    header line followed by one indented record per branch. Returns the
    EMPTY LIST when ``branches`` is empty so :func:`render_plan_section`
    omits the block entirely — the omit-when-empty rule that keeps a
    pre-FR22c plan byte-identical under render. Inverse of
    :func:`_parse_flow_branches`.

    Each record renders as a two-space-indented ``- branch_id: …`` line
    followed by four-space-indented ``description`` / ``disposition`` lines
    and — only when ``skip_rationale is not None`` — a ``skip_rationale``
    line. Indented record lines do not match the
    column-0-anchored ``_FIELD_LINE_RE``, so they do not perturb the
    four-scalar-field extraction in :func:`parse_plan_section`.
    """
    if not branches:
        return []
    lines = ["- flow_branches:"]
    for branch in branches:
        lines.append(f"  - branch_id: {branch.branch_id}")
        lines.append(f"    description: {branch.description}")
        lines.append(f"    disposition: {branch.disposition}")
        if branch.skip_rationale is not None:
            lines.append(f"    skip_rationale: {branch.skip_rationale}")
    return lines


def parse_plan_section(section_body: str) -> QABehavioralPlan | None:
    """Parse a previously-rendered plan-section body back into a
    ``QABehavioralPlan``. Returns ``None`` if ``section_body`` does not
    contain the canonical render shape (defensive — never raises; the
    wrapper's procedural step treats ``None`` as "no plan exists,
    generate fresh").

    Round-trip discipline: ``parse_plan_section(render_plan_section(plan))``
    equals ``plan`` for any well-formed plan — including plans whose
    entries carry populated ``flow_branches`` with mixed dispositions. An
    entry block with no ``- flow_branches:`` block (the pre-FR22c shape)
    parses to ``flow_branches == ()`` and MUST NOT raise (back-compat).
    """
    if not isinstance(section_body, str):
        return None

    status_match = _PLAN_STATUS_COMMENT_RE.search(section_body)
    hash_match = _AC_HASH_COMMENT_RE.search(section_body)
    if status_match is None or hash_match is None:
        return None

    plan_status_value = status_match.group("status")
    ac_hash_value = hash_match.group("hash")

    entries: list[QABehavioralPlanEntry] = []
    header_positions = list(_ENTRY_HEADER_RE.finditer(section_body))
    for idx, header in enumerate(header_positions):
        ac_id = header.group("ac_id").strip()
        block_start = header.end()
        block_end = (
            header_positions[idx + 1].start()
            if idx + 1 < len(header_positions)
            else len(section_body)
        )
        block = section_body[block_start:block_end]
        fields = {
            m.group("key"): m.group("value").strip()
            for m in _FIELD_LINE_RE.finditer(block)
        }
        try:
            entry = QABehavioralPlanEntry(
                ac_id=ac_id,
                assertion_shape=fields["assertion_shape"],
                expected_evidence_tier=fields["expected_evidence_tier"],  # type: ignore[arg-type]
                semantic_verification_requirement=fields[
                    "semantic_verification_requirement"
                ],  # type: ignore[arg-type]
                heuristic_applicability=_parse_heuristic_list(
                    fields["heuristic_applicability"]
                ),
                flow_branches=_parse_flow_branches(block),
            )
        except (KeyError, ValueError):
            return None
        entries.append(entry)

    if not entries:
        return None

    try:
        return QABehavioralPlan(
            plan_status=plan_status_value,  # type: ignore[arg-type]
            ac_hash=ac_hash_value,
            entries=tuple(entries),
        )
    except ValueError:
        return None


def _parse_heuristic_list(
    rendered: str,
) -> tuple[HeuristicApplicability, ...]:
    """Inverse of ``_render_heuristic_list``. Accepts ``[]`` or
    ``[a, b, c]``. Raises ``ValueError`` on malformed input or unknown
    heuristic names so the parser can return ``None`` cleanly.
    """
    body = rendered.strip()
    if not (body.startswith("[") and body.endswith("]")):
        raise ValueError(f"malformed heuristic list: {rendered!r}")
    inner = body[1:-1].strip()
    if not inner:
        return ()
    items = [item.strip() for item in inner.split(",") if item.strip()]
    valid: set[str] = {"empty-state", "error-state", "auth-boundary"}
    for item in items:
        if item not in valid:
            raise ValueError(f"unknown heuristic: {item!r}")
    typed: tuple[HeuristicApplicability, ...] = tuple(
        item for item in items  # type: ignore[misc]
    )
    return typed


def _parse_flow_branches(block: str) -> tuple[FlowBranch, ...]:
    """Inverse of :func:`_render_flow_branches`. Scan a per-AC entry
    ``block`` for the ``- flow_branches:`` header line and parse the
    indented branch records that follow it into a ``tuple[FlowBranch, ...]``.

    Returns the EMPTY TUPLE when no ``- flow_branches:`` header is present
    (the pre-FR22c shape) — this is the back-compat contract: a plan
    authored before FR22c parses to ``flow_branches == ()`` and does NOT
    raise.

    Raises ``ValueError`` on malformed input (an unparseable line, a
    sub-field before any branch record, an unknown or duplicate sub-field
    key, a duplicate ``branch_id``, a missing required sub-field, an
    invalid ``disposition`` value, or a header declared with no records)
    so :func:`parse_plan_section` can return ``None`` cleanly — same
    defensive-parser discipline as :func:`_parse_heuristic_list`.
    """
    lines = block.splitlines()
    header_idx: int | None = None
    for idx, line in enumerate(lines):
        if _FLOW_BRANCH_HEADER_RE.match(line):
            header_idx = idx
            break
    if header_idx is None:
        return ()

    records: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    seen_ids: set[str] = set()
    for line in lines[header_idx + 1 :]:
        if not line.strip():
            break
        record_match = _FLOW_BRANCH_RECORD_RE.match(line)
        if record_match is not None:
            branch_id = record_match.group("branch_id")
            if branch_id in seen_ids:
                raise ValueError(
                    f"duplicate flow_branches branch_id: {branch_id!r}"
                )
            seen_ids.add(branch_id)
            current = {"branch_id": branch_id}
            records.append(current)
            continue
        subfield_match = _FLOW_BRANCH_SUBFIELD_RE.match(line)
        if subfield_match is None:
            raise ValueError(f"malformed flow_branches line: {line!r}")
        if current is None:
            raise ValueError(
                f"flow_branches sub-field before any branch record: {line!r}"
            )
        key = subfield_match.group("key")
        if key not in _FLOW_BRANCH_SUBFIELD_KEYS:
            raise ValueError(f"unknown flow_branches sub-field: {key!r}")
        if key in current:
            raise ValueError(f"duplicate flow_branches sub-field: {key!r}")
        current[key] = subfield_match.group("value")

    if not records:
        raise ValueError(
            "flow_branches header declared with no branch records"
        )

    branches: list[FlowBranch] = []
    for record in records:
        disposition = record.get("disposition", "must-visit")
        if disposition not in ("must-visit", "intentionally-skipped"):
            raise ValueError(
                f"invalid flow_branches disposition: {disposition!r}"
            )
        branches.append(
            FlowBranch(
                branch_id=record["branch_id"],
                description=record["description"],
                disposition=cast(FlowBranchDisposition, disposition),
                skip_rationale=record.get("skip_rationale"),
            )
        )
    return tuple(branches)


# ---------------------------------------------------------------------------
# persist_or_reuse_plan (AC-5)
# ---------------------------------------------------------------------------


_QA_BEHAVIORAL_PLAN_HEADER_RE = re.compile(
    r"^## QA Behavioral Plan\s*$", re.MULTILINE
)
_NEXT_H2_RE = re.compile(r"^## ", re.MULTILINE)


def _extract_qa_behavioral_plan_section(story_doc_text: str) -> str | None:
    """Return the body of the ``## QA Behavioral Plan`` section bounded by
    the next H2 (``^## ``) or end-of-file. Returns ``None`` if no such
    section is present. Pure regex; no file I/O.
    """
    header_match = _QA_BEHAVIORAL_PLAN_HEADER_RE.search(story_doc_text)
    if header_match is None:
        return None
    body_start = header_match.end()
    next_h2 = _NEXT_H2_RE.search(story_doc_text, pos=body_start)
    body_end = next_h2.start() if next_h2 is not None else len(story_doc_text)
    return story_doc_text[body_start:body_end]


def persist_or_reuse_plan(
    story_doc_text: str,
    story_id: str,
    ac_list: list[AcEntry] | tuple[AcEntry, ...],
) -> tuple[QABehavioralPlan, PlanPersistAction]:
    """Detect an existing plan in ``story_doc_text`` and route to one of
    three actions:

    * ``("reuse-existing")`` — existing plan present AND its ``ac_hash``
      matches ``compute_ac_hash(ac_list)``. Returns the parsed plan with
      ``plan_status`` PRESERVED EXACTLY as found (whether ``generated`` or
      ``human-reviewed`` per epics.md line 1828).
    * ``("write-new")`` — no existing plan. Returns
      ``generate_plan(story_id, ac_list)`` with ``plan_status="generated"``.
    * ``("drift-suspected")`` — existing plan present but its ``ac_hash``
      does NOT match ``compute_ac_hash(ac_list)``. Returns the parsed plan
      UNCHANGED — no ``plan_status`` reset, no marker emission. Story 4.2
      consumes this token and adds reset + ``plan-drift-detected`` marker
      emission on top.

    Pure: no file I/O, no validator call, no marker emission. The wrapper's
    procedural step is responsible for the actual story-doc write through
    ``story_doc_validator.validate_section_write`` AFTER inspecting the
    action token.
    """
    section_body = _extract_qa_behavioral_plan_section(story_doc_text)
    parsed = parse_plan_section(section_body) if section_body is not None else None
    if parsed is None:
        return (generate_plan(story_id, ac_list), "write-new")
    expected_hash = compute_ac_hash(ac_list)
    if parsed.ac_hash == expected_hash:
        return (parsed, "reuse-existing")
    return (parsed, "drift-suspected")


__all__ = [
    "AcEntry",
    "ExpectedEvidenceTier",
    "FlowBranch",
    "FlowBranchDisposition",
    "HeuristicApplicability",
    "PlanPersistAction",
    "PlanStatus",
    "QABehavioralPlan",
    "QABehavioralPlanEntry",
    "SemanticVerificationRequirement",
    "compute_ac_hash",
    "generate_plan",
    "parse_plan_section",
    "persist_or_reuse_plan",
    "render_plan_section",
]
