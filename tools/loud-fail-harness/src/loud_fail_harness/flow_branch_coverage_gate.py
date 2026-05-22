"""FR22c within-AC flow-branch coverage CI gate (Story 13.5).

Architectural placement:
    This module is a CI **gate** — structurally a sibling of the fixture-
    driven gates ``fr33_fixture_gate`` (Story 1.8) and ``fixture_coverage``
    (Story 1.7), and it is NOT a substrate component. It *consumes* the
    Story 13.2 plan parser, the Story 13.3 ``surface_flow_branch_skipped``
    emission helper, and the Story 13.6 v1.6 marker taxonomy to enforce the
    FR22c within-AC flow-branch coverage contract against a gate-internal
    fixture corpus. It modifies none of them.

What this gate enforces:
    FR22c / Sprint Change Proposal 2026-05-20, Story 4.6 erratum:

        "For each AC, iterate over flow_branches[] and produce evidence per
        branch (Tier-1 + Tier-2 minimum) OR emit
        heuristic-skipped: flow-branch-<branch-id> for intentionally-skipped
        branches. A must-visit branch with no evidence and no marker is a
        contract violation (CI fixture catches it)."

    This gate is the "(CI fixture catches it)" clause. Per fixture case it
    reconciles, per AC and per enumerated flow branch:

    * ``must-visit`` → discharged by a recorded per-branch evidence outcome
      (``flow-branch-outcomes.yaml``). An undischarged ``must-visit`` branch
      — no evidence record and (by construction) no marker — is the FR22c
      contract violation.
    * ``intentionally-skipped`` → discharged by replaying the real
      ``surface_flow_branch_skipped`` and reconciling the resulting
      ``flow-branch`` sub-classification against the v1.6 marker taxonomy.

    It is the Story-1.7/1.8-pattern blocking CI enforcement of the contract
    scaffolded by Stories 13.2 (the ``flow_branches[]`` schema), 13.3 (the
    iteration contract) and 13.4 (the ``agents/qa.md`` wrapper prompt) — the
    structural-enforcement counterweight to the sensor-not-advisor invariant
    named by Architecture Pattern 8.

Pure fixture-driven reconciler:
    The gate does NOT run a QA agent, invoke ``iterate_acs``, drive a
    product, or emit production markers to any orchestrator-event log. It
    parses a fixture plan, replays the deterministic skip-emission path
    through the real ``surface_flow_branch_skipped``, reconciles against the
    real taxonomy, reconciles ``must-visit`` branches against a recorded-
    outcome artifact, and reports — exactly the posture ``fr33-fixture-gate``
    takes by replaying ``reconciler.reconcile`` without being a
    reconciliation surface.

Loud-fail discipline (Pattern 5):
    Exit codes distinguish failure classes so CI logs are diagnosable.
        0 — every branch of every fixture case reconciled cleanly: every
            must-visit branch discharged by evidence, every
            intentionally-skipped branch's flow-branch sub-classification
            reconciled; no findings of any category.
        1 — at least one fixture-side finding (``must-visit-undischarged``
            OR ``outcome-declaration-error``) AND no harness-level error.
            Recoverable by fixing the fixture's plan or its
            ``flow-branch-outcomes.yaml``.
        2 — a harness-level error: the fixtures directory is missing /
            unreadable; a fixture's ``qa-behavioral-plan.md`` is
            unparseable; a ``flow-branch-outcomes.yaml`` is malformed; the
            marker taxonomy is unreadable / malformed; or ``flow-branch`` is
            not declared under ``heuristic-skipped`` in the taxonomy. The
            harness or its precondition is broken.

    Mixed-category precedence: the two exit-1 categories are equivalent
    fixture-side invariant-tier signals — no intra-exit-1 precedence; both
    fire as exit 1. A harness-level error takes precedence over any exit-1
    finding (exit 2 wins). Harness-level errors are an exit-2 stderr path —
    NOT a ``BranchFinding`` category.

Sensor-not-advisor (PRD-level invariant):
    The gate REPORTS per-branch reconciliation outcomes with one-line
    remediation pointers; it does NOT auto-repair fixtures, auto-generate
    ``flow-branch-outcomes.yaml``, or rewrite plans. Same posture as every
    harness gate 1.4 through 6.9.

Cross-component reuse posture:
    * :func:`loud_fail_harness.qa_behavioral_plan.parse_plan_section` —
      REUSED for plan parsing; the gate does NOT re-implement frontmatter or
      ``flow_branches[]`` parsing.
    * :func:`loud_fail_harness.qa_ac_iteration.surface_flow_branch_skipped`
      — REUSED (replayed) for ``intentionally-skipped`` reconciliation; the
      gate does NOT re-derive the ``heuristic-skipped: flow-branch-<id>``
      token from scratch.
    * :func:`loud_fail_harness.reconciler.load_marker_taxonomy` — REUSED for
      the marker-class set that backs the :class:`MarkerClassRegistry`.
    * :class:`loud_fail_harness.specialist_dispatch.MarkerClassRegistry` —
      REUSED as the registry ``surface_flow_branch_skipped`` validates
      against.
    * :func:`loud_fail_harness._shared.find_repo_root` — REUSED for default-
      path resolution.

Determinism:
    All output lists are sorted by ``(case, ac_id, branch_id)`` (parallel to
    ``fr33_fixture_gate``'s ``(file_path, marker_class)`` sort). No
    ``uuid4()``, no ``datetime.now()``, no ``random``. ``GateResult`` and
    ``BranchFinding`` are Pydantic v2 frozen models; field declaration order
    is load-bearing for byte-stable ``model_dump_json()``.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections.abc import Sequence
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from loud_fail_harness._shared import find_repo_root
from loud_fail_harness.qa_ac_iteration import (
    HEURISTIC_SKIPPED_MARKER,
    surface_flow_branch_skipped,
)
from loud_fail_harness.qa_behavioral_plan import QABehavioralPlan, parse_plan_section
from loud_fail_harness.reconciler import load_marker_taxonomy
from loud_fail_harness.specialist_dispatch import (
    MarkerClassRegistry,
    UnknownMarkerClass,
)

#: The taxonomy sub-classification token the gate reconciles against. Story
#: 13.6 declares it under ``heuristic-skipped`` -> ``sub_classifications`` in
#: ``schemas/marker-taxonomy.yaml`` (schema_version 1.6). Consumed AS-IS.
FLOW_BRANCH_SUB_CLASSIFICATION: str = "flow-branch"

#: The two canonical fixture-case file names. Each case directory under the
#: fixtures dir carries exactly these two paired artifacts.
_PLAN_FILENAME: str = "qa-behavioral-plan.md"
_OUTCOMES_FILENAME: str = "flow-branch-outcomes.yaml"

#: AC-6 remediation pointer for an undischarged ``must-visit`` branch.
_MUST_VISIT_UNDISCHARGED_REMEDIATION: str = (
    "(per FR22c / Sprint Change Proposal 2026-05-20 Story 4.6 erratum: "
    "either drive this must-visit branch with per-branch evidence and record "
    "it in flow-branch-outcomes.yaml as evidence_present: true, OR — if the "
    "branch is genuinely out of scope — change its plan disposition to "
    "intentionally-skipped with a non-empty skip_rationale)"
)

#: AC-7 remediation pointer for a drifted ``flow-branch-outcomes.yaml``.
_OUTCOME_DECLARATION_REMEDIATION: str = (
    "(per Story 13.5 AC-2: flow-branch-outcomes.yaml must carry exactly one "
    "must_visit_evidence record per must-visit branch in the paired plan and "
    "none for intentionally-skipped or non-enumerated branches — fix the "
    "recorded-outcome artifact to match the plan)"
)


class OutcomeRecord(BaseModel):
    """One ``must_visit_evidence`` record parsed from a case's
    ``flow-branch-outcomes.yaml`` (AC-2).

    Declares whether one ``must-visit`` flow branch's run was discharged by
    recorded per-branch evidence. Frozen for determinism; field declaration
    order is load-bearing for byte-stable ``model_dump_json()``.
    """

    model_config = ConfigDict(frozen=True)

    ac_id: str
    branch_id: str
    evidence_present: bool


class ParsedCase(BaseModel):
    """One fully-parsed fixture case: its plan plus its recorded outcomes.

    Produced by :func:`_load_cases` (the file-I/O boundary) and consumed by
    the pure :func:`reconcile_case`. Frozen for determinism.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    plan: QABehavioralPlan
    outcomes: list[OutcomeRecord]


class BranchReference(BaseModel):
    """A cleanly-reconciled per-branch reference (a passing branch).

    Frozen for determinism; field declaration order is load-bearing for
    byte-stable JSON dumps. A ``must-visit`` reference was discharged by a
    recorded ``evidence_present: true`` outcome; an ``intentionally-skipped``
    reference was discharged by a clean ``surface_flow_branch_skipped``
    replay reconciling against the v1.6 taxonomy.
    """

    model_config = ConfigDict(frozen=True)

    case: str
    ac_id: str
    branch_id: str
    disposition: Literal["must-visit", "intentionally-skipped"]


class BranchFinding(BaseModel):
    """A single per-branch fixture-side finding.

    NFR-O5 named-invariant diagnostic shape: every finding names the
    offending entity (``case`` / ``ac_id`` / ``branch_id``) and carries a
    one-line remediation pointer.

    * ``case``        — the fixture case-directory name (e.g. ``clean``).
    * ``ac_id``       — the parsed per-AC identifier the branch belongs to.
    * ``branch_id``   — the offending flow branch's id.
    * ``category``    — the closed finding-category (AC-8).
    * ``message``     — the distinct-shape diagnostic prose.
    * ``remediation`` — the one-line NFR-O5 remediation pointer.

    Frozen for determinism; field declaration order is load-bearing for
    byte-stable JSON dumps.
    """

    model_config = ConfigDict(frozen=True)

    case: str
    ac_id: str
    branch_id: str
    category: Literal["must-visit-undischarged", "outcome-declaration-error"]
    message: str
    remediation: str


class GateResult(BaseModel):
    """Partitioned flow-branch coverage gate output.

    * ``passing`` — per-branch references whose reconciliation was clean.
      One :class:`BranchReference` per branch; sorted by
      ``(case, ac_id, branch_id)``.
    * ``must_visit_undischarged`` — a ``must-visit`` branch with no recorded
      evidence and no marker (the FR22c contract violation). FAIL exit 1.
    * ``outcome_declaration_error`` — a ``flow-branch-outcomes.yaml``
      ``must_visit_evidence`` record that drifts from the paired plan
      (dangling or duplicate). FAIL exit 1.

    Field declaration order matches Pydantic v2's JSON-serialization order
    (load-bearing for byte-stable dumps).
    """

    model_config = ConfigDict(frozen=True)

    passing: list[BranchReference]
    must_visit_undischarged: list[BranchFinding]
    outcome_declaration_error: list[BranchFinding]


class _HarnessError(Exception):
    """Internal signal for an exit-2 harness-level precondition failure.

    Carries a single NFR-O5 named-invariant diagnostic string. Caught at the
    :func:`main` boundary, printed to stderr, and mapped to exit code 2 — it
    is never a :class:`BranchFinding` (AC-8: harness-level errors are an
    exit-2 stderr path, not a finding category).
    """


def _render_flow_branch_marker(branch_id: str) -> str:
    """Compose the FR22c-canonical skipped-branch marker token.

    Renders ``heuristic-skipped: flow-branch-<branch_id>`` from the marker
    class + the ``flow-branch`` sub-classification + the branch id. Used only
    for diagnostic prose — the gate does not emit markers or render PR-bundle
    comment markup (that is ``bundle_assembly.py`` territory).
    """
    return (
        f"{HEURISTIC_SKIPPED_MARKER}: "
        f"{FLOW_BRANCH_SUB_CLASSIFICATION}-{branch_id}"
    )


def _parse_outcomes(path: pathlib.Path, case_name: str) -> list[OutcomeRecord]:
    """Structurally parse a case's ``flow-branch-outcomes.yaml`` (AC-2).

    Raises :class:`_HarnessError` (exit 2) when the file is unreadable, not
    valid YAML, or not a mapping carrying exactly the single list-valued
    ``must_visit_evidence`` key whose records each carry exactly ``ac_id``
    (str) / ``branch_id`` (str) / ``evidence_present`` (bool). A malformed
    *fixture* is a corpus-author bug, surfaced loudly.

    Semantic drift of a structurally-valid artifact (a record naming a
    non-``must-visit`` branch, a duplicate pair) is NOT detected here — it is
    a fixture-side ``outcome-declaration-error`` finding raised by
    :func:`reconcile_case`.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _HarnessError(
            f"harness-level error: case '{case_name}' flow-branch-outcomes.yaml "
            f"unreadable: {path}: {exc}"
        ) from exc
    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise _HarnessError(
            f"harness-level error: case '{case_name}' flow-branch-outcomes.yaml "
            f"is not valid YAML: {path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise _HarnessError(
            f"harness-level error: case '{case_name}' flow-branch-outcomes.yaml "
            f"top level is not a YAML mapping ({path})"
        )
    if set(data.keys()) != {"must_visit_evidence"}:
        raise _HarnessError(
            f"harness-level error: case '{case_name}' flow-branch-outcomes.yaml "
            f"must carry exactly the single top-level key 'must_visit_evidence' "
            f"({path}); got keys: {sorted(map(str, data.keys()))}"
        )
    records_raw = data["must_visit_evidence"]
    if not isinstance(records_raw, list):
        raise _HarnessError(
            f"harness-level error: case '{case_name}' flow-branch-outcomes.yaml "
            f"'must_visit_evidence' must be a list ({path})"
        )

    records: list[OutcomeRecord] = []
    for index, item in enumerate(records_raw):
        if not isinstance(item, dict):
            raise _HarnessError(
                f"harness-level error: case '{case_name}' "
                f"flow-branch-outcomes.yaml must_visit_evidence record {index} "
                f"is not a mapping ({path})"
            )
        if set(item.keys()) != {"ac_id", "branch_id", "evidence_present"}:
            raise _HarnessError(
                f"harness-level error: case '{case_name}' "
                f"flow-branch-outcomes.yaml must_visit_evidence record {index} "
                f"must carry exactly ac_id, branch_id, evidence_present ({path}); "
                f"got keys: {sorted(map(str, item.keys()))}"
            )
        ac_id = item["ac_id"]
        branch_id = item["branch_id"]
        evidence_present = item["evidence_present"]
        if not isinstance(ac_id, str):
            raise _HarnessError(
                f"harness-level error: case '{case_name}' "
                f"flow-branch-outcomes.yaml must_visit_evidence record {index} "
                f"ac_id must be a string ({path}); got: {ac_id!r}"
            )
        if not isinstance(branch_id, str):
            raise _HarnessError(
                f"harness-level error: case '{case_name}' "
                f"flow-branch-outcomes.yaml must_visit_evidence record {index} "
                f"branch_id must be a string ({path}); got: {branch_id!r}"
            )
        if not isinstance(evidence_present, bool):
            raise _HarnessError(
                f"harness-level error: case '{case_name}' "
                f"flow-branch-outcomes.yaml must_visit_evidence record {index} "
                f"evidence_present must be a boolean ({path}); got: "
                f"{evidence_present!r}"
            )
        records.append(
            OutcomeRecord(
                ac_id=ac_id,
                branch_id=branch_id,
                evidence_present=evidence_present,
            )
        )
    return records


def _load_one_case(case_dir: pathlib.Path) -> ParsedCase:
    """Parse one fixture case directory into a :class:`ParsedCase`.

    Raises :class:`_HarnessError` (exit 2) when either paired file is
    missing / unreadable, or when ``qa-behavioral-plan.md`` is not a
    parseable QA Behavioral Plan section. Story 13.2's
    :func:`parse_plan_section` returns ``None`` (rather than raising) on a
    structurally-malformed plan; the gate maps that ``None`` — and any
    defensive parser raise — to a harness-level error.
    """
    name = case_dir.name
    plan_path = case_dir / _PLAN_FILENAME
    outcomes_path = case_dir / _OUTCOMES_FILENAME
    if not plan_path.is_file():
        raise _HarnessError(
            f"harness-level error: case '{name}' is missing "
            f"{_PLAN_FILENAME} ({plan_path})"
        )
    if not outcomes_path.is_file():
        raise _HarnessError(
            f"harness-level error: case '{name}' is missing "
            f"{_OUTCOMES_FILENAME} ({outcomes_path})"
        )
    try:
        plan_text = plan_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _HarnessError(
            f"harness-level error: case '{name}' {_PLAN_FILENAME} "
            f"unreadable: {plan_path}: {exc}"
        ) from exc
    try:
        plan = parse_plan_section(plan_text)
    except Exception as exc:  # defensive — parse_plan_section is documented never to raise
        raise _HarnessError(
            f"harness-level error: case '{name}' {_PLAN_FILENAME} raised while "
            f"parsing ({plan_path}): {exc}"
        ) from exc
    if plan is None:
        raise _HarnessError(
            f"harness-level error: case '{name}' {_PLAN_FILENAME} is not a "
            f"parseable QA Behavioral Plan section ({plan_path}) — a malformed "
            f"fixture plan is a corpus-author bug"
        )
    outcomes = _parse_outcomes(outcomes_path, name)
    return ParsedCase(name=name, plan=plan, outcomes=outcomes)


def _load_cases(
    fixtures_dir: pathlib.Path,
) -> tuple[list[ParsedCase], list[str]]:
    """Discover and parse every case directory under ``fixtures_dir``.

    A case directory is any direct, non-dotfile subdirectory of
    ``fixtures_dir`` (the corpus ``README.md`` is a file and is skipped).
    Returns ``(parsed_cases, harness_errors)`` — every harness-level error
    encountered is COLLECTED (not fail-fast) so a corpus with several broken
    fixtures surfaces all of them in one CI run. A non-empty
    ``harness_errors`` list maps to exit 2 at the :func:`main` boundary.
    """
    if not fixtures_dir.is_dir():
        return (
            [],
            [
                "harness-level error: flow-branch-coverage fixtures directory "
                f"is missing or unreadable: {fixtures_dir}"
            ],
        )
    case_dirs = sorted(
        p
        for p in fixtures_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    if not case_dirs:
        return (
            [],
            [
                "harness-level error: flow-branch-coverage corpus is empty — "
                f"no case directories found under {fixtures_dir}"
            ],
        )
    cases: list[ParsedCase] = []
    errors: list[str] = []
    for case_dir in case_dirs:
        try:
            cases.append(_load_one_case(case_dir))
        except _HarnessError as exc:
            errors.append(str(exc))
    return (cases, errors)


def _load_heuristic_skipped_sub_classifications(
    taxonomy_path: pathlib.Path,
) -> set[str]:
    """Read the marker-taxonomy YAML and return the ``sub_classifications``
    set declared under the ``heuristic-skipped`` marker class.

    Reuses :func:`loud_fail_harness.reconciler.load_marker_taxonomy` for the
    class-level set elsewhere; that loader does not expose sub-classifications,
    so this function reads the YAML directly for the sub-list (AC-5 sanctions
    exactly this split). Raises :class:`_HarnessError` (exit 2) when the file
    is unreadable / malformed, or when ``heuristic-skipped`` is not declared
    at all.
    """
    try:
        raw_text = taxonomy_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _HarnessError(
            f"harness-level error: marker-taxonomy unreadable: "
            f"{taxonomy_path}: {exc}"
        ) from exc
    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise _HarnessError(
            f"harness-level error: marker-taxonomy YAML parse failure: "
            f"{taxonomy_path}: {exc}"
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("markers"), list):
        raise _HarnessError(
            f"harness-level error: marker-taxonomy at {taxonomy_path} is "
            f"malformed: expected a top-level mapping with a 'markers' list"
        )
    for entry in data["markers"]:
        if (
            isinstance(entry, dict)
            and entry.get("marker_class") == HEURISTIC_SKIPPED_MARKER
        ):
            subs = entry.get("sub_classifications")
            if not isinstance(subs, list):
                raise _HarnessError(
                    f"harness-level error: marker-taxonomy at {taxonomy_path} "
                    f"declares '{HEURISTIC_SKIPPED_MARKER}' with a non-list "
                    f"sub_classifications value"
                )
            return {sub for sub in subs if isinstance(sub, str)}
    raise _HarnessError(
        f"harness-level error: marker-taxonomy at {taxonomy_path} does not "
        f"declare the '{HEURISTIC_SKIPPED_MARKER}' marker class — the "
        f"flow-branch-coverage gate's precondition is broken"
    )


def _resolve_default_fixtures_dir(repo_root: pathlib.Path) -> pathlib.Path:
    """Resolve the default flow-branch-coverage fixtures root.

    The fixtures live at
    ``<repo-root>/tools/loud-fail-harness/tests/fixtures/flow-branch-coverage/``;
    the gate is canonically invoked from ``<repo-root>/tools/loud-fail-harness/``
    per ``.github/workflows/ci.yml``. Mirrors ``fr33_runtime_gate``'s
    ``_resolve_default_captures_root``.
    """
    return (
        repo_root
        / "tools"
        / "loud-fail-harness"
        / "tests"
        / "fixtures"
        / "flow-branch-coverage"
    )


def reconcile_case(
    case: ParsedCase, registry: MarkerClassRegistry
) -> tuple[list[BranchReference], list[BranchFinding]]:
    """Reconcile one parsed fixture case; return ``(references, findings)``.

    Pure: no file I/O, no ``print``. Per-branch contract violations are
    RETURNED as :class:`BranchFinding` objects, never raised. (The function
    may propagate an exception from the real
    :func:`surface_flow_branch_skipped` substrate — that is a substrate
    regression, a harness-level error, not a per-branch contract violation;
    it is caught at the :func:`main` boundary and mapped to exit 2.)

    The two reconciliation halves:

    * ``must-visit`` → looked up in the case's ``flow-branch-outcomes.yaml``.
      A record present with ``evidence_present: true`` discharges the branch;
      a record absent OR ``evidence_present: false`` is a
      ``must-visit-undischarged`` finding (AC-6).
    * ``intentionally-skipped`` → replayed through the real
      :func:`surface_flow_branch_skipped` against ``registry``; the returned
      record's ``marker_class`` / ``sub_classification`` are asserted to be
      ``heuristic-skipped`` / ``flow-branch`` (AC-5).

    Then the recorded outcomes are cross-validated against the plan: a record
    naming a non-enumerated or ``intentionally-skipped`` branch, or a
    duplicate ``(ac_id, branch_id)`` pair, is an ``outcome-declaration-error``
    finding (AC-7).
    """
    references: list[BranchReference] = []
    findings: list[BranchFinding] = []
    story_id = f"13.5-flow-branch-{case.name}"

    branch_dispositions: dict[tuple[str, str], str] = {}
    for entry in case.plan.entries:
        for branch in entry.flow_branches:
            branch_dispositions[(entry.ac_id, branch.branch_id)] = (
                branch.disposition
            )

    outcomes_index: dict[tuple[str, str], OutcomeRecord] = {}
    seen_outcome_keys: set[tuple[str, str]] = set()
    for record in case.outcomes:
        key = (record.ac_id, record.branch_id)
        if key in seen_outcome_keys:
            findings.append(
                BranchFinding(
                    case=case.name,
                    ac_id=record.ac_id,
                    branch_id=record.branch_id,
                    category="outcome-declaration-error",
                    message=(
                        f"Duplicate outcome declaration: case '{case.name}' "
                        f"flow-branch-outcomes.yaml lists more than one "
                        f"must_visit_evidence record for AC '{record.ac_id}' "
                        f"branch '{record.branch_id}' — each (ac_id, branch_id) "
                        f"pair must appear at most once."
                    ),
                    remediation=_OUTCOME_DECLARATION_REMEDIATION,
                )
            )
            continue
        seen_outcome_keys.add(key)
        outcomes_index[key] = record

    for entry in case.plan.entries:
        for branch in entry.flow_branches:
            key = (entry.ac_id, branch.branch_id)
            if branch.disposition == "must-visit":
                matched = outcomes_index.get(key)
                if matched is not None and matched.evidence_present:
                    references.append(
                        BranchReference(
                            case=case.name,
                            ac_id=entry.ac_id,
                            branch_id=branch.branch_id,
                            disposition="must-visit",
                        )
                    )
                else:
                    reason = (
                        "no flow-branch-outcomes.yaml must_visit_evidence "
                        "record"
                        if matched is None
                        else "a flow-branch-outcomes.yaml record declaring "
                        "evidence_present: false"
                    )
                    findings.append(
                        BranchFinding(
                            case=case.name,
                            ac_id=entry.ac_id,
                            branch_id=branch.branch_id,
                            category="must-visit-undischarged",
                            message=(
                                f"Undischarged must-visit flow branch: case "
                                f"'{case.name}' AC '{entry.ac_id}' branch "
                                f"'{branch.branch_id}' is a must-visit "
                                f"obligation with {reason}, and a must-visit "
                                f"branch carries no marker by construction — "
                                f"this is the FR22c contract violation: a "
                                f"must-visit branch with no evidence and no "
                                f"marker."
                            ),
                            remediation=_MUST_VISIT_UNDISCHARGED_REMEDIATION,
                        )
                    )
            else:
                emission = surface_flow_branch_skipped(
                    story_id, entry.ac_id, branch, registry
                )
                marker_record = emission.marker_record
                # Replay check — couples the gate to Story 13.3's emission
                # contract. An explicit raise (not `assert`) so it survives
                # `python -O`; the ValueError is caught in `main` and mapped
                # to exit 2 as a Story-13.3 emission-regression harness error.
                if marker_record.marker_class != HEURISTIC_SKIPPED_MARKER:
                    raise ValueError(
                        f"surface_flow_branch_skipped returned marker_class "
                        f"'{marker_record.marker_class}', expected "
                        f"'{HEURISTIC_SKIPPED_MARKER}'"
                    )
                if (
                    marker_record.sub_classification
                    != FLOW_BRANCH_SUB_CLASSIFICATION
                ):
                    raise ValueError(
                        f"surface_flow_branch_skipped returned "
                        f"sub_classification "
                        f"'{marker_record.sub_classification}', expected "
                        f"'{FLOW_BRANCH_SUB_CLASSIFICATION}'"
                    )
                references.append(
                    BranchReference(
                        case=case.name,
                        ac_id=entry.ac_id,
                        branch_id=branch.branch_id,
                        disposition="intentionally-skipped",
                    )
                )

    for (ac_id, branch_id), record in outcomes_index.items():
        disposition = branch_dispositions.get((ac_id, branch_id))
        if disposition is None:
            findings.append(
                BranchFinding(
                    case=case.name,
                    ac_id=ac_id,
                    branch_id=branch_id,
                    category="outcome-declaration-error",
                    message=(
                        f"Dangling outcome declaration: case '{case.name}' "
                        f"flow-branch-outcomes.yaml records must_visit_evidence "
                        f"for AC '{ac_id}' branch '{branch_id}', but the paired "
                        f"qa-behavioral-plan.md enumerates no such flow branch."
                    ),
                    remediation=_OUTCOME_DECLARATION_REMEDIATION,
                )
            )
        elif disposition != "must-visit":
            findings.append(
                BranchFinding(
                    case=case.name,
                    ac_id=ac_id,
                    branch_id=branch_id,
                    category="outcome-declaration-error",
                    message=(
                        f"Dangling outcome declaration: case '{case.name}' "
                        f"flow-branch-outcomes.yaml records must_visit_evidence "
                        f"for AC '{ac_id}' branch '{branch_id}', but that "
                        f"branch's plan disposition is intentionally-skipped — "
                        f"its discharge is the "
                        f"'{_render_flow_branch_marker(branch_id)}' marker, not "
                        f"a recorded-evidence declaration."
                    ),
                    remediation=_OUTCOME_DECLARATION_REMEDIATION,
                )
            )

    return (references, findings)


def run_flow_branch_coverage_gate(
    parsed_cases: list[ParsedCase], registry: MarkerClassRegistry
) -> GateResult:
    """Reconcile every parsed case; partition results into the buckets.

    Iterates ``parsed_cases`` in input order, calls :func:`reconcile_case`,
    and partitions every reference / finding into the :class:`GateResult`
    buckets. NEVER bails after the first finding within a category — every
    category is collected end-to-end before output (the 1.5 / 1.7 / 1.8
    discipline).

    Sorted-output discipline: ``passing`` and the two finding lists are each
    sorted by ``(case, ac_id, branch_id)``.
    """
    passing: list[BranchReference] = []
    must_visit_undischarged: list[BranchFinding] = []
    outcome_declaration_error: list[BranchFinding] = []

    for case in parsed_cases:
        references, findings = reconcile_case(case, registry)
        passing.extend(references)
        for finding in findings:
            if finding.category == "must-visit-undischarged":
                must_visit_undischarged.append(finding)
            else:
                outcome_declaration_error.append(finding)

    def _ref_key(ref: BranchReference) -> tuple[str, str, str]:
        return (ref.case, ref.ac_id, ref.branch_id)

    def _finding_key(finding: BranchFinding) -> tuple[str, str, str]:
        return (finding.case, finding.ac_id, finding.branch_id)

    passing.sort(key=_ref_key)
    must_visit_undischarged.sort(key=_finding_key)
    outcome_declaration_error.sort(key=_finding_key)

    return GateResult(
        passing=passing,
        must_visit_undischarged=must_visit_undischarged,
        outcome_declaration_error=outcome_declaration_error,
    )


def format_findings(
    result: GateResult,
    *,
    fixtures_dir: str,
    taxonomy_path: str,
) -> str:
    """Render a :class:`GateResult` for stdout.

    Header naming the fixtures dir + taxonomy path; a passing-summary line;
    per-bucket finding lists with the AC-8 distinct-shape diagnostics; a
    footer Summary line. Mirrors the "name the offending entity + remediation
    pointer" discipline of ``fr33_fixture_gate``. The Summary footer's bucket
    order matches :class:`GateResult`'s field declaration order.
    """
    lines: list[str] = []
    lines.append("QA within-AC flow-branch coverage gate (Story 13.5; FR22c)")
    lines.append(f"  fixtures dir: {fixtures_dir}")
    lines.append(f"  taxonomy:     {taxonomy_path}")
    lines.append("")

    has_findings = bool(
        result.must_visit_undischarged or result.outcome_declaration_error
    )
    passing_prefix = "PARTIAL" if has_findings else "OK"
    passing_line = (
        f"{passing_prefix}: {len(result.passing)} flow branch(es) "
        f"reconciled cleanly"
    )
    if has_findings:
        passing_line += " (but findings below)"
    lines.append(passing_line + ".")

    if result.must_visit_undischarged:
        lines.append("")
        lines.append(
            f"FAIL: {len(result.must_visit_undischarged)} "
            "must-visit-undischarged finding(s)."
        )
        for finding in result.must_visit_undischarged:
            lines.append(f"  - {finding.message} {finding.remediation}")

    if result.outcome_declaration_error:
        lines.append("")
        lines.append(
            f"FAIL: {len(result.outcome_declaration_error)} "
            "outcome-declaration-error finding(s)."
        )
        for finding in result.outcome_declaration_error:
            lines.append(f"  - {finding.message} {finding.remediation}")

    lines.append("")
    lines.append(
        f"Summary: {len(result.passing)} passing branch(es), "
        f"{len(result.must_visit_undischarged)} must-visit-undischarged "
        f"finding(s), {len(result.outcome_declaration_error)} "
        f"outcome-declaration-error finding(s)."
    )
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flow-branch-coverage-gate",
        description=(
            "FR22c within-AC flow-branch coverage CI gate (Story 13.5). "
            "Reconciles, per AC and per enumerated flow branch, the within-AC "
            "branch-coverage contract over a gate-internal fixture corpus: "
            "every must-visit branch discharged by recorded evidence, every "
            "intentionally-skipped branch discharged by a taxonomy-reconciling "
            "heuristic-skipped: flow-branch-<id> marker."
        ),
    )
    parser.add_argument(
        "--fixtures-dir",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to the flow-branch-coverage fixtures dir (default: "
            "<repo-root>/tools/loud-fail-harness/tests/fixtures/"
            "flow-branch-coverage/). Test-injection flag; CI invocations omit "
            "it."
        ),
    )
    parser.add_argument(
        "--taxonomy-path",
        type=pathlib.Path,
        default=None,
        help=(
            "Override path to marker-taxonomy.yaml (default: "
            "<repo-root>/schemas/marker-taxonomy.yaml). Test-injection flag; "
            "CI invocations omit it."
        ),
    )
    return parser


def _display_path(
    path: pathlib.Path, repo_root: Optional[pathlib.Path] = None
) -> str:
    """Render ``path`` relative to repo root if possible; absolute otherwise.

    Mirrors ``fr33_fixture_gate._display_path`` so canonical CI invocations
    produce stable diff-friendly relative paths and ``tmp_path`` invocations
    fall back to absolute.
    """
    try:
        root = repo_root if repo_root is not None else find_repo_root()
        return str(path.resolve().relative_to(root.resolve()))
    except (RuntimeError, ValueError):
        return str(path.resolve())


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    fixtures_dir: pathlib.Path
    taxonomy_path: pathlib.Path
    repo_root: Optional[pathlib.Path] = None
    if args.fixtures_dir is None or args.taxonomy_path is None:
        try:
            repo_root = find_repo_root()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        fixtures_dir = args.fixtures_dir or _resolve_default_fixtures_dir(
            repo_root
        )
        taxonomy_path = (
            args.taxonomy_path or repo_root / "schemas" / "marker-taxonomy.yaml"
        )
    else:
        fixtures_dir = args.fixtures_dir
        taxonomy_path = args.taxonomy_path

    try:
        taxonomy_classes = load_marker_taxonomy(taxonomy_path)
    except RuntimeError as exc:
        print(
            f"harness-level error: marker-taxonomy malformed: "
            f"{taxonomy_path}: {exc}",
            file=sys.stderr,
        )
        return 2
    except OSError as exc:
        print(
            f"harness-level error: marker-taxonomy unreadable: "
            f"{taxonomy_path}: {exc}",
            file=sys.stderr,
        )
        return 2
    except yaml.YAMLError as exc:
        print(
            f"harness-level error: marker-taxonomy YAML parse failure: "
            f"{taxonomy_path}: {exc}",
            file=sys.stderr,
        )
        return 2

    try:
        declared_sub_classifications = (
            _load_heuristic_skipped_sub_classifications(taxonomy_path)
        )
    except _HarnessError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if FLOW_BRANCH_SUB_CLASSIFICATION not in declared_sub_classifications:
        print(
            f"harness-level error: marker-taxonomy at {taxonomy_path} does not "
            f"declare the '{FLOW_BRANCH_SUB_CLASSIFICATION}' sub-classification "
            f"under the '{HEURISTIC_SKIPPED_MARKER}' marker class — Story "
            f"13.6's v1.6 PATCH bump is missing or was reverted; the "
            f"flow-branch-coverage gate's precondition is broken.",
            file=sys.stderr,
        )
        return 2

    registry = MarkerClassRegistry(
        marker_classes=frozenset(taxonomy_classes)
    )

    parsed_cases, harness_errors = _load_cases(fixtures_dir)
    if harness_errors:
        for message in harness_errors:
            print(message, file=sys.stderr)
        return 2

    try:
        result = run_flow_branch_coverage_gate(parsed_cases, registry)
    except (UnknownMarkerClass, ValidationError, ValueError) as exc:
        print(
            f"harness-level error: flow-branch skip-emission replay failed "
            f"against the real surface_flow_branch_skipped substrate — Story "
            f"13.3's emission contract may have regressed: {exc}",
            file=sys.stderr,
        )
        return 2

    print(
        format_findings(
            result,
            fixtures_dir=_display_path(fixtures_dir, repo_root),
            taxonomy_path=_display_path(taxonomy_path, repo_root),
        )
    )

    if result.must_visit_undischarged or result.outcome_declaration_error:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
