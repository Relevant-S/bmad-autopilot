"""Tests for the FR22c flow-branch-coverage CI gate (Story 13.5).

Covers the canonical pass corpus, the three negative-corpus cases, the
taxonomy-regression and unparseable-plan harness-error paths, the genuine
replay of the real ``surface_flow_branch_skipped`` substrate, determinism of
``GateResult.model_dump_json()``, sorted-output discipline, and the
``format_findings`` renderer.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest

from loud_fail_harness import flow_branch_coverage_gate as gate
from loud_fail_harness.flow_branch_coverage_gate import (
    BranchFinding,
    BranchReference,
    GateResult,
    format_findings,
    main,
    reconcile_case,
    run_flow_branch_coverage_gate,
)
from loud_fail_harness.qa_ac_iteration import surface_flow_branch_skipped
from loud_fail_harness.qa_behavioral_plan import parse_plan_section
from loud_fail_harness.reconciler import load_marker_taxonomy
from loud_fail_harness.specialist_dispatch import MarkerClassRegistry

_TESTS_DIR = pathlib.Path(__file__).resolve().parent
_HARNESS_ROOT = _TESTS_DIR.parent
_REPO_ROOT = _HARNESS_ROOT.parent.parent
_CANONICAL_CORPUS = _TESTS_DIR / "fixtures" / "flow-branch-coverage"
_FAILURE_CASES = _TESTS_DIR / "fixtures" / "flow-branch-coverage-failure-cases"
_TAXONOMY = _REPO_ROOT / "schemas" / "marker-taxonomy.yaml"


def _build_registry() -> MarkerClassRegistry:
    return MarkerClassRegistry(
        marker_classes=frozenset(load_marker_taxonomy(_TAXONOMY))
    )


def _run_gate(fixtures_dir: pathlib.Path) -> GateResult:
    cases, errors = gate._load_cases(fixtures_dir)
    assert errors == [], f"unexpected harness errors: {errors}"
    return run_flow_branch_coverage_gate(cases, _build_registry())


def _isolate(tmp_path: pathlib.Path, case_name: str) -> pathlib.Path:
    """Copy one failure-case directory into a fresh single-case fixtures dir."""
    fixtures_dir = tmp_path / "flow-branch-coverage"
    fixtures_dir.mkdir()
    shutil.copytree(_FAILURE_CASES / case_name, fixtures_dir / case_name)
    return fixtures_dir


def _main_args(fixtures_dir: pathlib.Path, taxonomy: pathlib.Path) -> list[str]:
    return [
        "--fixtures-dir",
        str(fixtures_dir),
        "--taxonomy-path",
        str(taxonomy),
    ]


# --- AC-9 case 1: canonical clean corpus -----------------------------------


def test_clean_corpus_main_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(_main_args(_CANONICAL_CORPUS, _TAXONOMY))
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "reconciled cleanly" in out


def test_clean_corpus_gate_result_has_empty_finding_buckets() -> None:
    result = _run_gate(_CANONICAL_CORPUS)
    assert result.must_visit_undischarged == []
    assert result.outcome_declaration_error == []


def test_clean_corpus_passing_covers_every_branch() -> None:
    result = _run_gate(_CANONICAL_CORPUS)
    # 3 ACs of the clean plan: 3 + 3 + 2 = 8 enumerated flow branches.
    assert len(result.passing) == 8
    dispositions = sorted(ref.disposition for ref in result.passing)
    assert dispositions.count("must-visit") == 6
    assert dispositions.count("intentionally-skipped") == 2


# --- AC-9 case 2: must-visit-undischarged ----------------------------------


def test_must_visit_undischarged_finding_shape() -> None:
    parsed = gate._load_one_case(_FAILURE_CASES / "must-visit-undischarged")
    _references, findings = reconcile_case(parsed, _build_registry())
    undischarged = [
        f for f in findings if f.category == "must-visit-undischarged"
    ]
    assert len(undischarged) == 1
    finding = undischarged[0]
    assert finding.case == "must-visit-undischarged"
    assert finding.ac_id == "1"
    assert finding.branch_id == "locked-account"
    assert "must-visit" in finding.message
    assert finding.remediation


def test_must_visit_undischarged_main_exits_one(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures_dir = _isolate(tmp_path, "must-visit-undischarged")
    exit_code = main(_main_args(fixtures_dir, _TAXONOMY))
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "must-visit-undischarged finding(s)" in out
    assert "locked-account" in out


def test_must_visit_undischarged_via_evidence_present_false(
    tmp_path: pathlib.Path,
) -> None:
    """A must-visit branch with a record present but ``evidence_present: false``
    is undischarged just like a missing record — the distinct reason branch in
    ``reconcile_case`` (Story 13.5 review patch)."""
    fixtures_dir = tmp_path / "flow-branch-coverage"
    case_dir = fixtures_dir / "evidence-false"
    case_dir.mkdir(parents=True)
    shutil.copyfile(
        _FAILURE_CASES / "must-visit-undischarged" / "qa-behavioral-plan.md",
        case_dir / "qa-behavioral-plan.md",
    )
    (case_dir / "flow-branch-outcomes.yaml").write_text(
        "must_visit_evidence:\n"
        '  - ac_id: "1"\n'
        "    branch_id: valid-credentials\n"
        "    evidence_present: true\n"
        '  - ac_id: "1"\n'
        "    branch_id: locked-account\n"
        "    evidence_present: false\n",
        encoding="utf-8",
    )
    parsed = gate._load_one_case(case_dir)
    _references, findings = reconcile_case(parsed, _build_registry())
    undischarged = [
        f for f in findings if f.category == "must-visit-undischarged"
    ]
    assert len(undischarged) == 1
    assert undischarged[0].branch_id == "locked-account"
    assert "evidence_present: false" in undischarged[0].message


# --- AC-9 case 3: dangling outcome declaration -----------------------------


def test_dangling_outcome_finding_shape() -> None:
    parsed = gate._load_one_case(_FAILURE_CASES / "dangling-outcome")
    _references, findings = reconcile_case(parsed, _build_registry())
    errors = [f for f in findings if f.category == "outcome-declaration-error"]
    assert {f.branch_id for f in errors} == {"ghost-branch", "skipped-branch"}
    for finding in errors:
        assert finding.case == "dangling-outcome"
        assert finding.ac_id == "1"
        assert finding.remediation


def test_dangling_outcome_main_exits_one(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures_dir = _isolate(tmp_path, "dangling-outcome")
    exit_code = main(_main_args(fixtures_dir, _TAXONOMY))
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "outcome-declaration-error finding(s)" in out
    assert "ghost-branch" in out


# --- AC-9 case 4: malformed flow-branch-outcomes.yaml ----------------------


def test_malformed_outcomes_main_exits_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures_dir = _isolate(tmp_path, "malformed-outcomes")
    exit_code = main(_main_args(fixtures_dir, _TAXONOMY))
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "harness-level error" in err
    assert "evidence_present" in err


# --- AC-9 case 5: unparseable qa-behavioral-plan.md ------------------------


def test_unparseable_plan_main_exits_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures_dir = tmp_path / "flow-branch-coverage"
    case_dir = fixtures_dir / "broken-plan"
    case_dir.mkdir(parents=True)
    (case_dir / "qa-behavioral-plan.md").write_text(
        "this is not a QA Behavioral Plan section at all\n", encoding="utf-8"
    )
    (case_dir / "flow-branch-outcomes.yaml").write_text(
        "must_visit_evidence: []\n", encoding="utf-8"
    )
    exit_code = main(_main_args(fixtures_dir, _TAXONOMY))
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "harness-level error" in err
    assert "qa-behavioral-plan.md" in err


# --- AC-9 case 6: taxonomy regression (flow-branch undeclared) -------------


def test_taxonomy_regression_missing_flow_branch_exits_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    regressed_taxonomy = tmp_path / "marker-taxonomy.yaml"
    regressed_taxonomy.write_text(
        'schema_version: "1.5"\n'
        "markers:\n"
        "  - marker_class: heuristic-skipped\n"
        "    sub_classifications:\n"
        "      - empty-state\n"
        "      - error-state\n"
        "      - auth-boundary\n"
        "  - marker_class: LAD-skipped\n"
        "    sub_classifications: []\n",
        encoding="utf-8",
    )
    exit_code = main(_main_args(_CANONICAL_CORPUS, regressed_taxonomy))
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "harness-level error" in err
    assert "flow-branch" in err


# --- AC-9 case 7: genuine replay of the real substrate ---------------------


def test_replays_real_surface_flow_branch_skipped() -> None:
    plan = parse_plan_section(
        (_CANONICAL_CORPUS / "clean" / "qa-behavioral-plan.md").read_text(
            encoding="utf-8"
        )
    )
    assert plan is not None
    registry = _build_registry()
    skipped = [
        (entry.ac_id, branch)
        for entry in plan.entries
        for branch in entry.flow_branches
        if branch.disposition == "intentionally-skipped"
    ]
    assert skipped, "clean corpus must enumerate intentionally-skipped branches"
    for ac_id, branch in skipped:
        emission = surface_flow_branch_skipped(
            "13.5-replay-test", ac_id, branch, registry
        )
        assert emission.marker_record.marker_class == "heuristic-skipped"
        assert emission.marker_record.sub_classification == "flow-branch"


# --- AC-9 case 8: determinism + sorted output ------------------------------


def test_gate_result_json_byte_stable() -> None:
    first = _run_gate(_CANONICAL_CORPUS)
    second = _run_gate(_CANONICAL_CORPUS)
    assert first.model_dump_json() == second.model_dump_json()


def test_findings_sorted_by_case_ac_branch() -> None:
    parsed = gate._load_one_case(_FAILURE_CASES / "dangling-outcome")
    cases = [parsed]
    result = run_flow_branch_coverage_gate(cases, _build_registry())
    keys = [
        (f.case, f.ac_id, f.branch_id)
        for f in result.outcome_declaration_error
    ]
    assert keys == sorted(keys)
    passing_keys = [(r.case, r.ac_id, r.branch_id) for r in result.passing]
    assert passing_keys == sorted(passing_keys)


# --- AC-9 case 9: format_findings renderer ---------------------------------


def test_format_findings_mixed_result() -> None:
    result = GateResult(
        passing=[
            BranchReference(
                case="demo",
                ac_id="1",
                branch_id="happy",
                disposition="must-visit",
            )
        ],
        must_visit_undischarged=[
            BranchFinding(
                case="demo",
                ac_id="2",
                branch_id="stranded",
                category="must-visit-undischarged",
                message="Undischarged must-visit flow branch: case 'demo' ...",
                remediation="(per FR22c ...)",
            )
        ],
        outcome_declaration_error=[
            BranchFinding(
                case="demo",
                ac_id="3",
                branch_id="phantom",
                category="outcome-declaration-error",
                message="Dangling outcome declaration: case 'demo' ...",
                remediation="(per Story 13.5 AC-2 ...)",
            )
        ],
    )
    rendered = format_findings(
        result, fixtures_dir="fixtures/x", taxonomy_path="schemas/y.yaml"
    )
    assert "flow-branch coverage gate (Story 13.5; FR22c)" in rendered
    assert "fixtures/x" in rendered
    assert "schemas/y.yaml" in rendered
    assert "1 must-visit-undischarged finding(s)" in rendered
    assert "1 outcome-declaration-error finding(s)" in rendered
    assert "Summary: 1 passing branch(es)" in rendered


# --- extra robustness: a case directory missing a paired file --------------


def test_missing_paired_file_exits_two(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures_dir = tmp_path / "flow-branch-coverage"
    case_dir = fixtures_dir / "incomplete"
    case_dir.mkdir(parents=True)
    (case_dir / "qa-behavioral-plan.md").write_text(
        "placeholder\n", encoding="utf-8"
    )
    exit_code = main(_main_args(fixtures_dir, _TAXONOMY))
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "flow-branch-outcomes.yaml" in err
